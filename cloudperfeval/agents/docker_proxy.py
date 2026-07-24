"""GET-only Unix-socket proxy for direct Docker Swarm inspection."""

from __future__ import annotations

import os
import re
import socket
import socketserver
import threading
from pathlib import Path

MAX_HEADER_BYTES = 64 * 1024
_VERSION_PREFIX = re.compile(r"^/v\d+(?:\.\d+)?")
_ALLOWED_PATHS = (
    re.compile(r"^/_ping$"),
    re.compile(r"^/version$"),
    re.compile(r"^/info$"),
    re.compile(r"^/services(?:/[^/?]+(?:/logs)?)?$"),
    re.compile(r"^/tasks(?:/[^/?]+)?$"),
    re.compile(r"^/nodes(?:/[^/?]+)?$"),
    re.compile(r"^/containers/json$"),
    re.compile(r"^/containers/[^/?]+/(?:json|logs)$"),
    re.compile(r"^/networks(?:/[^/?]+)?$"),
)


def docker_read_allowed(method: str, target: str) -> bool:
    """Return whether an HTTP request is safe for Swarm-state inspection."""
    if method.upper() not in {"GET", "HEAD"}:
        return False
    path = target.split("?", 1)[0]
    path = _VERSION_PREFIX.sub("", path) or "/"
    return any(pattern.fullmatch(path) for pattern in _ALLOWED_PATHS)


def _error_response(status: str, message: str) -> bytes:
    body = (message + "\n").encode("utf-8")
    return (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: text/plain\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii") + body


class _DockerProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, _DockerProxyServer)
        header = bytearray()
        while b"\r\n\r\n" not in header and len(header) <= MAX_HEADER_BYTES:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            header.extend(chunk)
        if len(header) > MAX_HEADER_BYTES:
            self.request.sendall(_error_response("431 Request Header Fields Too Large", "header too large"))
            return
        try:
            first_line = bytes(header).split(b"\r\n", 1)[0].decode("ascii")
            method, target, _ = first_line.split(" ", 2)
        except (UnicodeDecodeError, ValueError):
            self.request.sendall(_error_response("400 Bad Request", "invalid Docker API request"))
            return
        if not docker_read_allowed(method, target):
            self.request.sendall(
                _error_response("403 Forbidden", "Docker API operation blocked by read-only proxy")
            )
            return

        # Force one request per connection. Docker CLI transparently reconnects,
        # and this prevents an unchecked second request on a keep-alive stream.
        lines = bytes(header).split(b"\r\n")
        filtered = [line for line in lines if not line.lower().startswith(b"connection:")]
        try:
            blank = filtered.index(b"")
        except ValueError:
            blank = len(filtered)
        filtered.insert(blank, b"Connection: close")
        forwarded = b"\r\n".join(filtered)

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as backend:
            backend.connect(server.backend_socket)
            backend.sendall(forwarded)
            while True:
                data = backend.recv(64 * 1024)
                if not data:
                    break
                self.request.sendall(data)


class _DockerProxyServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, socket_path: str, backend_socket: str):
        self.backend_socket = backend_socket
        super().__init__(socket_path, _DockerProxyHandler)


class DockerReadOnlyProxy:
    """Lifecycle manager for a per-run read-only Docker API socket."""

    def __init__(
        self,
        directory: Path,
        *,
        backend_socket: str = "/var/run/docker.sock",
    ):
        self.directory = Path(directory).resolve()
        self.socket_path = self.directory / "docker.sock"
        self.backend_socket = backend_socket
        self._server: _DockerProxyServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> "DockerReadOnlyProxy":
        if not Path(self.backend_socket).is_socket():
            raise RuntimeError(f"Docker socket not found: {self.backend_socket}")
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        self._server = _DockerProxyServer(str(self.socket_path), self.backend_socket)
        os.chmod(self.socket_path, 0o600)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="cpe-docker-readonly-proxy",
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
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> "DockerReadOnlyProxy":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
