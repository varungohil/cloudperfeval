"""Shared dispatch for SwarmActions used by CLI and MCP coding-agent tools."""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from cloudperfeval.actions import SwarmActions, get_actions_doc
from cloudperfeval.config import config

SUBMISSION_ENV = "CPE_SUBMISSION_PATH"
CONFIG_ENV = "CPE_CONFIG_PATH"
SUITE_ENV = "CPE_SUITE_ID"
STACK_ENV = "CPE_STACK_NAME"
TOOL_SOCKET_ENV = "CPE_TOOL_SOCKET"
TOOL_TOKEN_ENV = "CPE_TOOL_TOKEN"

ACTION_NAMES: tuple[str, ...] = tuple(sorted(get_actions_doc().keys()))


def load_tool_runtime_config() -> None:
    """Apply config overrides from the parent orchestrator via env vars."""
    cfg_path = os.environ.get(CONFIG_ENV)
    if cfg_path:
        config.reload(cfg_path)
    suite = os.environ.get(SUITE_ENV)
    if suite:
        config.apply_suite_profile(suite)
    stack = os.environ.get(STACK_ENV)
    if stack:
        config.set("stack_name", stack)


def submission_path() -> Path | None:
    raw = os.environ.get(SUBMISSION_ENV)
    return Path(raw) if raw else None


def write_submission(solution: Any) -> Path:
    path = submission_path()
    if path is None:
        raise RuntimeError(
            f"{SUBMISSION_ENV} is not set; cannot persist submission for grading"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(solution, str):
        try:
            solution = json.loads(solution)
        except json.JSONDecodeError:
            pass
    path.write_text(json.dumps(solution, indent=2, default=str), encoding="utf-8")
    return path


def read_submission(path: Path | str | None = None) -> Any | None:
    p = Path(path) if path else submission_path()
    if p is None or not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _format_result(result: Any) -> str:
    if isinstance(result, Enum):
        return result.name
    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2, default=str)
    return str(result)


def dispatch_action(name: str, *args: Any, **kwargs: Any) -> str:
    """Invoke a SwarmActions method by name and return a string result."""
    if name not in ACTION_NAMES:
        return f"Error: unknown action {name!r}. Choose from: {', '.join(ACTION_NAMES)}"

    socket_path = os.environ.get(TOOL_SOCKET_ENV)
    if socket_path:
        token = os.environ.get(TOOL_TOKEN_ENV, "")
        if not token:
            return f"Error: {TOOL_TOKEN_ENV} is required when {TOOL_SOCKET_ENV} is set"
        # Lazy import avoids a dispatch <-> gateway import cycle on the server.
        from cloudperfeval.tools.gateway import dispatch_remote

        return dispatch_remote(socket_path, token, name, args, kwargs)

    load_tool_runtime_config()
    actions = SwarmActions()
    method = getattr(actions, name)

    if name == "submit":
        solution: Any
        if args:
            solution = args[0]
        elif "solution" in kwargs:
            solution = kwargs["solution"]
        else:
            solution = kwargs
        try:
            path = write_submission(solution)
        except Exception as e:
            return f"Error writing submission: {e}"
        # Still call submit() so behavior matches the turn-based path.
        method(solution)
        return (
            f"Submission accepted and written to {path}. "
            "Stop investigating and exit."
        )

    try:
        result = method(*args, **kwargs)
    except TypeError as e:
        return f"Error calling {name}: {e}"
    except Exception as e:
        return f"Unhandled error during {name}: {e}"
    return _format_result(result)


def tool_env_for_session(
    *,
    submission_file: Path | str,
    config_path: Path | str | None = None,
    suite_id: str | None = None,
    stack_name: str | None = None,
) -> dict[str, str]:
    """Env vars the MCP/CLI child process needs to match the live eval session."""
    env = {
        SUBMISSION_ENV: str(submission_file),
        CONFIG_ENV: str(config_path or config.config_file),
    }
    suite = suite_id if suite_id is not None else config.active_suite
    if suite:
        env[SUITE_ENV] = suite
    stack = stack_name if stack_name is not None else config.get("stack_name")
    if stack:
        env[STACK_ENV] = str(stack)
    return env
