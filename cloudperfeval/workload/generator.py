"""Drive load against the application and capture the resulting symptoms.

Two modes:
  - "single"    : one curl request to an endpoint (good for single-request
                  service diagnosis tasks where the agent is handed a trace ID).
  - "sustained" : a wrk run for N seconds at a target rate (good for
                  sustained-request service diagnosis tasks measured by p95).

After load, wait ``jaeger_ingest_seconds`` then capture from Jaeger. For
``mode=single``, the trace ID is taken from the curl ``X-Trace-Id`` header;
if missing or not found after the wait, raises ``TraceCaptureError`` (no fallback).

Use ``defer_jaeger=True`` to send load only (curl/wrk) without sleeping or
querying Jaeger — for ``run.py --phase snapshot``.
"""

from __future__ import annotations

import os
import re
import shlex
import time
from dataclasses import dataclass, field
from typing import Literal

from cloudperfeval.config import config
from cloudperfeval.observer.traces import JaegerAPI
from cloudperfeval.shell import Shell


class TraceCaptureError(RuntimeError):
    """Single-request workload failed to capture the correlation trace in Jaeger."""


@dataclass
class WorkloadSpec:
    mode: Literal["single", "sustained"]
    endpoint: str                       # path appended to frontend_url
    method: str = "GET"
    body: str | None = None
    headers: dict = field(default_factory=dict)

    # sustained-only
    rate: int = 10                      # requests/sec (wrk2 -R)
    duration_sec: int = 30
    connections: int = 4
    threads: int = 2
    wrk_script: str | None = None       # lua script path relative to wrk_cwd on loadgen host
    wrk_url: str | None = None          # wrk target URL/path (no query string; lua adds params)

    # trace-service to query for resulting traces (the entry service)
    trace_service: str = "frontend-service"

    def summary(self) -> str:
        if self.mode == "single":
            return f"single {self.method} {self.endpoint}"
        return (f"sustained {self.method} {self.endpoint} @ {self.rate} rps "
                f"for {self.duration_sec}s")

    def target_url(self, frontend_url: str) -> str:
        """Full HTTP URL the workload generator hits (curl or wrk target)."""
        base = (frontend_url or "").rstrip("/")
        if self.mode == "single":
            path = self.endpoint
        elif self.wrk_url:
            if self.wrk_url.startswith("http"):
                return self.wrk_url.split("?", 1)[0]
            path = self.wrk_url.split("?", 1)[0]
        else:
            path = self.endpoint.split("?", 1)[0]
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"


@dataclass
class WorkloadResult:
    spec_summary: str
    trace_ids: list[str] = field(default_factory=list)
    oracle_trace_ids: list[str] = field(default_factory=list)  # slowest ~20% used by oracle
    p50_ms: float | None = None
    p95_ms: float | None = None
    sample_latencies_ms: list[float] = field(default_factory=list)
    voted_bottleneck: str | None = None      # majority-vote trace oracle (NOT shown to agent)
    raw_loadgen_output: str = ""
    correlation_trace_id: str | None = None    # from curl X-Trace-Id before Jaeger capture
    load_start_ts: float | None = None         # epoch seconds, load (curl/wrk) start
    load_end_ts: float | None = None           # epoch seconds, load end

    def primary_trace_id(self) -> str | None:
        return self.trace_ids[0] if self.trace_ids else None

    def to_public_dict(self) -> dict:
        """Symptom view safe to show the agent (no oracle hint)."""
        return {
            "workload": self.spec_summary,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "sample_trace_ids": self.trace_ids[:3],
        }


_TRACE_ID_HEADER = re.compile(
    r"^x-trace-id:\s*([0-9a-fA-F]+)\s*$", re.MULTILINE | re.IGNORECASE,
)
_CURL_META_MARKER = "\n__CPE_META__"


class WorkloadGenerator:
    def __init__(self):
        self.frontend_url = config.get("frontend_url", "").rstrip("/")
        self.jaeger = JaegerAPI(config.get("jaeger_url", ""))
        self.ingest_wait = config.get("jaeger_ingest_seconds", 8)
        self.node_host_map: dict = config.get("node_host_map", {}) or {}
        self.node_domain_suffix = config.get("node_domain_suffix", "")

    def _wrk_bin(self) -> str:
        return os.path.expanduser(config.get("wrk_bin", "wrk"))

    def _wrk_target_url(self, spec: WorkloadSpec) -> str:
        """Base wrk URL without query string (lua scripts append parameters)."""
        return spec.target_url(self.frontend_url)

    def _build_wrk_command(self, spec: WorkloadSpec) -> str:
        """DeathStarBench-style wrk2 invocation (ulimit, -D exp, lua script, -R last)."""
        parts: list[str] = []
        cwd = config.get("wrk_cwd", "")
        if cwd:
            parts.append(f"cd {shlex.quote(os.path.expanduser(cwd))}")

        ulimit_n = config.get("wrk_ulimit_n")
        if ulimit_n:
            parts.append(f"ulimit -n {int(ulimit_n)}")

        wrk = self._wrk_bin()
        dist = config.get("wrk_distribution", "exp")
        url = self._wrk_target_url(spec)
        script_flag = f"-s {spec.wrk_script} " if spec.wrk_script else ""
        parts.append(
            f"{wrk} -D {dist} -t{spec.threads} -c{spec.connections} "
            f"-d{spec.duration_sec}s -L {script_flag}{url} -R{spec.rate}"
        )
        return " && ".join(parts)

    def _resolve_host(self, host: str) -> str:
        """Map short node names (e.g. node-19) to SSH-reachable hostnames."""
        if host in ("localhost", "", None):
            return config.get("manager_host", "localhost")
        if host in self.node_host_map:
            return self.node_host_map[host]
        if self.node_domain_suffix and "." not in host:
            return f"{host}.{self.node_domain_suffix}"
        return host

    def _loadgen_host(self) -> str:
        return self._resolve_host(
            config.get("loadgen_host") or config.get("manager_host", "localhost")
        )

    @staticmethod
    def _parse_trace_id_from_curl(raw: str) -> str | None:
        match = _TRACE_ID_HEADER.search(raw)
        return match.group(1).lower() if match else None

    def _run_single(self, spec: WorkloadSpec) -> tuple[str, str | None]:
        url = f"{self.frontend_url}{spec.endpoint}"
        header_flags = " ".join(f'-H "{k}: {v}"' for k, v in spec.headers.items())
        data_flag = f"--data '{spec.body}'" if spec.body else ""
        cmd = (
            f"curl -si "
            f"-w '{_CURL_META_MARKER}http_code=%{{http_code}} time_total=%{{time_total}}s' "
            f"-X {spec.method} {header_flags} {data_flag} '{url}'"
        )
        print(f"[LOAD] curl command: {cmd}")
        raw = Shell.exec(cmd, timeout=config.get("shell_timeout", 100))
        print(f"[LOAD] curl output:\n{raw}")
        return raw, self._parse_trace_id_from_curl(raw)

    def _run_sustained(self, spec: WorkloadSpec) -> str:
        cmd = self._build_wrk_command(spec)
        node_host = self._loadgen_host()
        print(f"[LOAD] wrk node: {node_host}")
        print(f"[LOAD] wrk command: {cmd}")
        raw = Shell.exec_on_node(node_host, cmd, timeout=spec.duration_sec + 60)
        print(f"[LOAD] wrk output:\n{raw}")
        return raw

    def _capture_after_wait(
        self,
        spec: WorkloadSpec,
        raw: str,
        correlation_trace_id: str | None,
        load_start_ts: float | None = None,
        load_end_ts: float | None = None,
    ) -> dict:
        print(f"[LOAD] Waiting {self.ingest_wait}s for Jaeger ingest")
        time.sleep(self.ingest_wait)
        if spec.mode == "single":
            if correlation_trace_id:
                captured = self.jaeger.capture_trace(correlation_trace_id)
                if not captured:
                    raise TraceCaptureError(
                        f"Jaeger has no trace for X-Trace-Id {correlation_trace_id!r} "
                        f"after {self.ingest_wait}s ingest wait"
                    )
                return captured
            raise TraceCaptureError("curl response had no X-Trace-Id header")
        capture_kwargs: dict = {
            "limit": config.get("trace_capture_limit", 200),
        }
        if load_start_ts is not None and load_end_ts is not None:
            capture_kwargs["start_ts"] = load_start_ts
            capture_kwargs["end_ts"] = load_end_ts
        else:
            capture_kwargs["minutes"] = config.get("trace_lookback_minutes", 5)
        return self.jaeger.capture_recent(spec.trace_service, **capture_kwargs)

    def run(self, spec: WorkloadSpec, *, defer_jaeger: bool = False) -> WorkloadResult:
        print(f"[LOAD] Running {spec.summary()}")
        raw = ""
        correlation_trace_id: str | None = None

        load_start_ts = time.time()
        if spec.mode == "single":
            raw, correlation_trace_id = self._run_single(spec)
            if correlation_trace_id:
                print(f"[LOAD] curl X-Trace-Id: {correlation_trace_id}")
        elif spec.mode == "sustained":
            raw = self._run_sustained(spec)
        else:
            raise ValueError(f"Unknown workload mode: {spec.mode}")
        load_end_ts = time.time()
        print(f"[LOAD] window: {load_start_ts:.0f} - {load_end_ts:.0f} (epoch s)")

        if defer_jaeger:
            print("[LOAD] Deferring Jaeger capture (--phase snapshot)")
            return WorkloadResult(
                spec_summary=spec.summary(),
                raw_loadgen_output=raw,
                correlation_trace_id=correlation_trace_id,
                load_start_ts=load_start_ts,
                load_end_ts=load_end_ts,
            )

        captured = self._capture_after_wait(
            spec, raw, correlation_trace_id, load_start_ts, load_end_ts,
        )
        result = WorkloadResult(
            spec_summary=spec.summary(),
            trace_ids=captured["trace_ids"],
            oracle_trace_ids=captured["oracle_trace_ids"],
            p50_ms=captured["p50_ms"],
            p95_ms=captured["p95_ms"],
            sample_latencies_ms=captured["sample_latencies_ms"],
            voted_bottleneck=captured["voted_bottleneck"],
            raw_loadgen_output=raw,
            correlation_trace_id=correlation_trace_id,
            load_start_ts=load_start_ts,
            load_end_ts=load_end_ts,
        )
        print(f"[LOAD] Captured {len(result.trace_ids)} traces "
              f"({len(result.oracle_trace_ids)} for oracle vote); "
              f"p95={result.p95_ms}ms; oracle_hint={result.voted_bottleneck}")
        return result

    def capture_deferred(
        self, spec: WorkloadSpec, raw: str, correlation_trace_id: str | None,
        load_start_ts: float | None = None, load_end_ts: float | None = None,
    ) -> WorkloadResult:
        """Jaeger capture for a load already sent in ``--phase snapshot``."""
        captured = self._capture_after_wait(
            spec, raw, correlation_trace_id, load_start_ts, load_end_ts,
        )
        result = WorkloadResult(
            spec_summary=spec.summary(),
            trace_ids=captured["trace_ids"],
            oracle_trace_ids=captured["oracle_trace_ids"],
            p50_ms=captured["p50_ms"],
            p95_ms=captured["p95_ms"],
            sample_latencies_ms=captured["sample_latencies_ms"],
            voted_bottleneck=captured["voted_bottleneck"],
            raw_loadgen_output=raw,
            correlation_trace_id=correlation_trace_id,
            load_start_ts=load_start_ts,
            load_end_ts=load_end_ts,
        )
        print(f"[LOAD] Captured {len(result.trace_ids)} traces "
              f"({len(result.oracle_trace_ids)} for oracle vote); "
              f"p95={result.p95_ms}ms; oracle_hint={result.voted_bottleneck}")
        return result
