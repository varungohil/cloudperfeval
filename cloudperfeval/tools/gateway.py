"""Per-run host tool gateway for filesystem-sandboxed coding agents."""

from __future__ import annotations

import json
import os
import secrets
import socket
import socketserver
import threading
from pathlib import Path
from typing import Any

from cloudperfeval.tools.dispatch import dispatch_action

TOOL_SOCKET_ENV = "CPE_TOOL_SOCKET"
TOOL_TOKEN_ENV = "CPE_TOOL_TOKEN"
DISABLED_ACTIONS_ENV = "CPE_DISABLED_ACTIONS"
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


def _disabled_actions(raw: str | None) -> set[str]:
    return {item.strip() for item in (raw or "").split(",") if item.strip()}


class _GatewayHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, _GatewayServer)
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            self._reply({"ok": False, "error": "request too large"})
            return
        try:
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
            if not secrets.compare_digest(str(request.get("token", "")), server.token):
                self._reply({"ok": False, "error": "unauthorized"})
                return
            name = str(request.get("action", ""))
            if name in server.disabled_actions:
                self._reply(
                    {"ok": False, "error": f"action {name!r} is disabled in sandboxed runs"}
                )
                return
            args = request.get("args", [])
            kwargs = request.get("kwargs", {})
            if not isinstance(args, list) or not isinstance(kwargs, dict):
                raise ValueError("args must be a list and kwargs must be an object")
            result = server.dispatch(name, args, kwargs)
            self._reply({"ok": True, "result": result})
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._reply({"ok": False, "error": f"invalid request: {exc}"})
        except Exception as exc:
            self._reply({"ok": False, "error": f"gateway error: {exc}"})

    def _reply(self, payload: dict[str, Any]) -> None:
        self.wfile.write((json.dumps(payload, default=str) + "\n").encode("utf-8"))


class _GatewayServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(
        self,
        socket_path: str,
        *,
        token: str,
        tool_env: dict[str, str],
        disabled_actions: set[str],
    ):
        self.token = token
        self.tool_env = dict(tool_env)
        self.disabled_actions = set(disabled_actions)
        self._dispatch_lock = threading.Lock()
        super().__init__(socket_path, _GatewayHandler)

    def dispatch(self, name: str, args: list[Any], kwargs: dict[str, Any]) -> str:
        # dispatch_action currently reads session configuration from environment.
        # Serialize calls while applying only the session variables; never expose
        # gateway client variables to the host-side dispatcher.
        with self._dispatch_lock:
            old = {key: os.environ.get(key) for key in self.tool_env}
            try:
                os.environ.update(self.tool_env)
                return dispatch_action(name, *args, **kwargs)
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


class ToolGateway:
    """Lifecycle manager for one authenticated Unix-socket tool gateway."""

    def __init__(
        self,
        directory: Path,
        tool_env: dict[str, str],
        *,
        disabled_actions: set[str] | None = None,
    ):
        self.directory = Path(directory).resolve()
        self.socket_path = self.directory / "tool.sock"
        self.token = secrets.token_urlsafe(32)
        self.tool_env = dict(tool_env)
        self.disabled_actions = set(disabled_actions or {"exec_shell"})
        self._server: _GatewayServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> "ToolGateway":
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        self._server = _GatewayServer(
            str(self.socket_path),
            token=self.token,
            tool_env=self.tool_env,
            disabled_actions=self.disabled_actions,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="cpe-tool-gateway",
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
        try:
            self.directory.rmdir()
        except OSError:
            pass

    def __enter__(self) -> "ToolGateway":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def client_env(self, *, container: bool = False) -> dict[str, str]:
        socket_path = "/run/cpe/tool.sock" if container else str(self.socket_path)
        return {
            TOOL_SOCKET_ENV: socket_path,
            TOOL_TOKEN_ENV: self.token,
            DISABLED_ACTIONS_ENV: ",".join(sorted(self.disabled_actions)),
        }


def dispatch_remote(
    socket_path: str,
    token: str,
    name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    timeout: float = 60,
) -> str:
    """Invoke an action through the host gateway."""
    request = {
        "token": token,
        "action": name,
        "args": list(args),
        "kwargs": kwargs,
    }
    payload = (json.dumps(request, default=str) + "\n").encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(socket_path)
        client.sendall(payload)
        response_file = client.makefile("rb")
        raw = response_file.readline(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        return "Error: tool gateway response too large"
    try:
        response = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"Error: invalid tool gateway response: {exc}"
    if not response.get("ok"):
        return f"Error: {response.get('error', 'tool gateway request failed')}"
    return str(response.get("result", ""))
