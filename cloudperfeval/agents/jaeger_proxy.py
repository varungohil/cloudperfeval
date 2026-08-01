"""HTTP reverse proxy that drops spans from Jaeger API responses.

Drop semantics:
- ``operations``: matching ``operationName`` spans are always removed.
- ``services``: matching ``serviceName`` spans are removed independently with a
  per-service probability. Supply either a mapping of service name -> rate
  (``{"home-timeline-service": 0.5}``) or a list of names that all use the
  shared ``drop_prob`` fallback.

For sandboxed agents, set ``jaeger_proxy=JaegerProxySpec(...)`` on a
``PerformanceProblem``. When omitted, agents hit Jaeger directly (no drops).
Host-side oracle capture always uses config ``jaeger_url`` unchanged.
"""

from __future__ import annotations

import json
import random
import re
import socket
import socketserver
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from cloudperfeval.config import config

MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 64 * 1024 * 1024
_TRACE_PATH = re.compile(r"^/api/traces(?:/[^/?]+)?$")
CONTAINER_JAEGER_HOST = "host.docker.internal"


def _normalize_name_set(names: Iterable[str] | None) -> frozenset[str] | None:
    if names is None:
        return None
    return frozenset(str(n) for n in names if str(n))


def _parse_name_list(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    if isinstance(raw, Mapping):
        return tuple(str(key).strip() for key in raw if str(key).strip())
    if isinstance(raw, (list, tuple, set, frozenset)):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    raise ValueError(f"expected list/str of names, got {type(raw).__name__}")


def _check_rate(name: str, value: Any) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"drop rate for {name!r} must be a number, got {value!r}") from exc
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"drop rate for {name!r} must be in [0, 1], got {rate!r}")
    return rate


def _parse_service_rates(raw: Any, default_prob: float) -> dict[str, float]:
    """Normalize ``services`` into ``{service_name: drop_rate}``.

    Mappings carry an explicit per-service rate. Lists/strings fall back to
    ``default_prob`` (the shared ``drop_prob``) for every listed service.
    """
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        rates: dict[str, float] = {}
        for key, value in raw.items():
            name = str(key).strip()
            if not name:
                continue
            rates[name] = _check_rate(name, value)
        return rates
    return {name: default_prob for name in _parse_name_list(raw)}


@dataclass(frozen=True)
class JaegerProxySpec:
    """Per-problem Jaeger span-drop parameters for sandboxed agents.

    Attach to ``PerformanceProblem(jaeger_proxy=...)``. When omitted (``None``),
    the sandbox talks to Jaeger directly and nothing is dropped.

    Drop rules when the proxy is started:
    - ``operations``: always removed
    - ``services``: removed with a per-service rate. Pass a mapping for explicit
      rates (``{"home-timeline-service": 0.5, "post-storage-service": 0.2}``) or
      a list of names to apply the shared ``drop_prob`` to each.
    """

    drop_prob: float = 0.0
    services: Mapping[str, float] | Iterable[str] = ()
    operations: tuple[str, ...] = ()
    seed: int | None = None
    service_rates: dict[str, float] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        drop_prob = _check_rate("drop_prob", self.drop_prob)
        object.__setattr__(self, "drop_prob", drop_prob)
        object.__setattr__(
            self, "service_rates", _parse_service_rates(self.services, drop_prob)
        )
        object.__setattr__(self, "services", _parse_name_list(self.services))
        object.__setattr__(self, "operations", _parse_name_list(self.operations))

    @classmethod
    def from_value(cls, raw: "JaegerProxySpec | dict[str, Any] | None") -> "JaegerProxySpec | None":
        """Normalize a problem kwarg into a spec, or ``None`` (no proxy / no drops)."""
        if raw is None:
            return None
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, dict):
            raise ValueError(
                f"jaeger_proxy must be JaegerProxySpec, dict, or None; "
                f"got {type(raw).__name__}"
            )
        seed_raw = raw.get("seed")
        seed = None if seed_raw is None or seed_raw == "" else int(seed_raw)
        return cls(
            drop_prob=float(raw.get("drop_prob", 0.0)),
            services=raw.get("services") or {},
            operations=_parse_name_list(raw.get("operations")),
            seed=seed,
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "drop_prob": self.drop_prob,
            "service_rates": dict(self.service_rates),
            "operations": list(self.operations),
            "seed": self.seed,
        }


def jaeger_proxy_timeout_from_config() -> float:
    """Host proxy upstream timeout; drop params come from the problem, not config."""
    sandbox = config.get("agent_sandbox", {}) or {}
    if not isinstance(sandbox, dict):
        return 60.0
    raw = sandbox.get("jaeger_proxy", {}) or {}
    if not isinstance(raw, dict):
        return 60.0
    return float(raw.get("timeout", 60.0))


# Timeout-only config helper lives above; drop params are problem-scoped.


def _span_service_name(span: Any, processes: dict[str, Any]) -> str | None:
    if not isinstance(span, dict):
        return None
    pid = span.get("processID")
    proc = processes.get(pid, {}) if isinstance(processes, dict) else {}
    if not isinstance(proc, dict):
        return None
    name = proc.get("serviceName")
    return str(name) if name is not None else None


def _span_operation_name(span: Any) -> str | None:
    if not isinstance(span, dict):
        return None
    op = span.get("operationName")
    return str(op) if op is not None else None


def drop_spans_in_response(
    body: dict[str, Any],
    drop_prob: float,
    rng: random.Random,
    *,
    services: Mapping[str, float] | Iterable[str] | None = None,
    operations: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return a copy of a Jaeger ``/api/traces`` JSON body with spans dropped.

    Drop rules (checked in order):

    1. ``operations``: spans whose ``operationName`` is in this set are **always**
       removed (ignores drop rates).
    2. ``services``: remaining spans are removed with that service's rate. Pass a
       mapping for per-service rates, or an iterable of names to apply
       ``drop_prob`` to each.
    3. All other spans are kept.

    Trace/process metadata is left intact so dangling ``CHILD_OF`` references
    are possible (incomplete telemetry).
    """
    service_rates = _parse_service_rates(services, drop_prob)
    operation_set = _normalize_name_set(operations)
    droppable_services = {n for n, rate in service_rates.items() if rate > 0}
    if not operation_set and not droppable_services:
        return body

    traces = body.get("data")
    if not isinstance(traces, list):
        return body

    mutated_traces: list[Any] = []
    for trace in traces:
        if not isinstance(trace, dict):
            mutated_traces.append(trace)
            continue
        spans = trace.get("spans")
        if not isinstance(spans, list):
            mutated_traces.append(trace)
            continue
        processes = trace.get("processes") or {}
        if not isinstance(processes, dict):
            processes = {}

        kept: list[Any] = []
        for span in spans:
            op = _span_operation_name(span)
            if operation_set is not None and op in operation_set:
                continue  # always drop
            svc = _span_service_name(span, processes)
            rate = service_rates.get(svc, 0.0) if svc is not None else 0.0
            if rate > 0 and rng.random() < rate:
                continue  # per-service probabilistic drop
            kept.append(span)
        mutated = dict(trace)
        mutated["spans"] = kept
        mutated_traces.append(mutated)

    out = dict(body)
    out["data"] = mutated_traces
    return out


def _should_mutate(method: str, path: str) -> bool:
    return method.upper() == "GET" and bool(_TRACE_PATH.fullmatch(path.split("?", 1)[0]))


def _read_headers(sock: socket.socket) -> tuple[bytearray, bytes]:
    header = bytearray()
    while b"\r\n\r\n" not in header and len(header) <= MAX_HEADER_BYTES:
        chunk = sock.recv(4096)
        if not chunk:
            break
        header.extend(chunk)
    if len(header) > MAX_HEADER_BYTES:
        raise ValueError("request header too large")
    sep = header.find(b"\r\n\r\n")
    if sep < 0:
        raise ValueError("incomplete request headers")
    return header[: sep + 4], bytes(header[sep + 4 :])


def _parse_request_line(header: bytes) -> tuple[str, str, str]:
    first = header.split(b"\r\n", 1)[0].decode("ascii")
    method, target, version = first.split(" ", 2)
    return method, target, version


def _header_map(header: bytes) -> dict[str, str]:
    lines = header.split(b"\r\n")[1:]
    out: dict[str, str] = {}
    for line in lines:
        if not line:
            break
        if b":" not in line:
            continue
        name, value = line.split(b":", 1)
        out[name.decode("latin-1").strip().lower()] = value.decode("latin-1").strip()
    return out


def _read_body(sock: socket.socket, already: bytes, headers: dict[str, str]) -> bytes:
    length = headers.get("content-length")
    if length is None:
        return already
    need = int(length)
    if need < 0 or need > MAX_BODY_BYTES:
        raise ValueError("invalid Content-Length")
    body = bytearray(already)
    while len(body) < need:
        chunk = sock.recv(min(64 * 1024, need - len(body)))
        if not chunk:
            break
        body.extend(chunk)
    if len(body) != need:
        raise ValueError("incomplete request body")
    return bytes(body)


def _http_response(status: str, body: bytes, *, content_type: str = "application/json") -> bytes:
    return (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii") + body


class _JaegerProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, _JaegerProxyServer)
        try:
            header, leftover = _read_headers(self.request)
            method, target, _version = _parse_request_line(header)
            headers = _header_map(header)
            body = _read_body(self.request, leftover, headers)
        except (UnicodeDecodeError, ValueError) as exc:
            self.request.sendall(
                _http_response(
                    "400 Bad Request",
                    f"invalid request: {exc}\n".encode("utf-8"),
                    content_type="text/plain",
                )
            )
            return

        if method.upper() not in {"GET", "HEAD"}:
            self.request.sendall(
                _http_response(
                    "405 Method Not Allowed",
                    b"only GET/HEAD are proxied\n",
                    content_type="text/plain",
                )
            )
            return

        # Preserve absolute-path targets (incl. query string).
        split = urlsplit(server.backend_url)
        backend_url = f"{split.scheme}://{split.netloc}{target}"

        try:
            req = Request(
                backend_url,
                data=body if body and method.upper() != "GET" else None,
                method=method.upper(),
                headers={
                    "Accept": headers.get("accept", "application/json"),
                    "User-Agent": headers.get("user-agent", "cpe-jaeger-proxy"),
                },
            )
            with urlopen(req, timeout=server.timeout) as resp:
                status = f"{resp.status} {getattr(resp, 'reason', '')}".strip()
                resp_body = resp.read(MAX_BODY_BYTES + 1)
                if len(resp_body) > MAX_BODY_BYTES:
                    self.request.sendall(
                        _http_response(
                            "502 Bad Gateway",
                            b"upstream response too large\n",
                            content_type="text/plain",
                        )
                    )
                    return
                content_type = resp.headers.get("Content-Type", "application/json")
        except HTTPError as exc:
            err_body = exc.read(MAX_BODY_BYTES) if exc.fp is not None else b""
            self.request.sendall(
                _http_response(
                    f"{exc.code} {exc.reason}",
                    err_body,
                    content_type=exc.headers.get("Content-Type", "text/plain")
                    if exc.headers
                    else "text/plain",
                )
            )
            return
        except URLError as exc:
            self.request.sendall(
                _http_response(
                    "502 Bad Gateway",
                    f"upstream error: {exc}\n".encode("utf-8"),
                    content_type="text/plain",
                )
            )
            return

        path = target.split("?", 1)[0]
        if _should_mutate(method, path) and resp_body:
            try:
                parsed = json.loads(resp_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict):
                with server.rng_lock:
                    mutated = drop_spans_in_response(
                        parsed,
                        server.drop_prob,
                        server.rng,
                        services=server.service_rates,
                        operations=server.operations,
                    )
                resp_body = json.dumps(mutated, separators=(",", ":")).encode("utf-8")
                content_type = "application/json"

        if method.upper() == "HEAD":
            resp_body = b""

        self.request.sendall(
            _http_response(status, resp_body, content_type=content_type)
        )


class _JaegerProxyServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        backend_url: str,
        drop_prob: float,
        rng: random.Random,
        timeout: float,
        service_rates: dict[str, float],
        operations: frozenset[str] | None,
    ):
        self.backend_url = backend_url.rstrip("/")
        self.drop_prob = drop_prob
        self.rng = rng
        self.rng_lock = threading.Lock()
        self.timeout = timeout
        self.service_rates = dict(service_rates)
        self.operations = operations
        super().__init__(server_address, _JaegerProxyHandler)


class JaegerFaultProxy:
    """Lifecycle manager for a per-run Jaeger span-dropping HTTP proxy."""

    def __init__(
        self,
        backend_url: str,
        *,
        drop_prob: float = 0.0,
        services: Mapping[str, float] | Iterable[str] | None = None,
        operations: Iterable[str] | None = None,
        seed: int | None = None,
        host: str = "0.0.0.0",
        port: int = 0,
        timeout: float = 60.0,
    ):
        drop_prob = _check_rate("drop_prob", drop_prob)
        if not backend_url:
            raise ValueError("backend_url is required")
        self.backend_url = backend_url.rstrip("/")
        self.drop_prob = float(drop_prob)
        self.service_rates = _parse_service_rates(services, self.drop_prob)
        self.services = _normalize_name_set(self.service_rates or None)
        self.operations = _normalize_name_set(operations)
        self.seed = seed
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self._server: _JaegerProxyServer | None = None
        self._thread: threading.Thread | None = None
        self._rng = random.Random(seed)

    @property
    def listen_port(self) -> int:
        if self._server is None:
            raise RuntimeError("proxy is not running")
        return int(self._server.server_address[1])

    @property
    def public_url(self) -> str:
        """URL for host-local clients (bound host/port)."""
        host = self.host if self.host not in {"0.0.0.0", "::"} else "127.0.0.1"
        return f"http://{host}:{self.listen_port}"

    def container_url(self, hostname: str = CONTAINER_JAEGER_HOST) -> str:
        """URL for Docker sandbox containers (requires host.docker.internal mapping)."""
        return f"http://{hostname}:{self.listen_port}"

    def start(self) -> "JaegerFaultProxy":
        self._server = _JaegerProxyServer(
            (self.host, self.port),
            backend_url=self.backend_url,
            drop_prob=self.drop_prob,
            rng=self._rng,
            timeout=self.timeout,
            service_rates=self.service_rates,
            operations=self.operations,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="cpe-jaeger-fault-proxy",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "JaegerFaultProxy":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
