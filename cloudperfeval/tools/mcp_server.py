"""Optional MCP stdio server exposing SwarmActions.

Coding agents (Claude Code / Codex) use the Bash CLI path by default
(`python -m cloudperfeval.tools.call`), matching SREGym. This server remains
available if you want to attach MCP manually.
"""

from __future__ import annotations

import inspect
from typing import Any, get_args, get_origin, get_type_hints

from mcp.server.fastmcp import FastMCP

from cloudperfeval.actions import SwarmActions, get_actions_doc
from cloudperfeval.tools.dispatch import ACTION_NAMES, dispatch_action, load_tool_runtime_config

INSTRUCTIONS = """\
CloudPerfEval read-only observability tools for diagnosing a performance fault
in a Docker Swarm microservice application.

Rules:
- Use only these tools (and read-only shell via exec_shell) to investigate.
- Do not mutate Swarm/stack state.
- When ready, call submit with your diagnosis dict, then stop.
"""


def _annotation_to_schema_type(annotation: Any) -> Any:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return Any
    origin = get_origin(annotation)
    if origin is type(None):
        return Any
    args = get_args(annotation)
    if origin is not None and type(None) in args:
        # Optional[T] / T | None → expose T for MCP input
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _build_tool_fn(name: str, method):
    """Create a FastMCP-callable that matches the SwarmActions method signature."""
    docs = get_actions_doc()
    description = docs.get(name, "") or f"Call {name}"
    sig = inspect.signature(method)
    try:
        hints = get_type_hints(method)
    except Exception:
        hints = {}

    params: list[inspect.Parameter] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        annotation = _annotation_to_schema_type(hints.get(pname, param.annotation))
        if name == "submit" and pname == "solution":
            annotation = dict[str, Any]
        default = param.default
        kind = inspect.Parameter.KEYWORD_ONLY
        params.append(
            inspect.Parameter(pname, kind=kind, default=default, annotation=annotation)
        )

    def _impl(**kwargs: Any) -> str:
        return dispatch_action(name, **kwargs)

    _impl.__name__ = name
    _impl.__doc__ = description
    _impl.__signature__ = inspect.Signature(params, return_annotation=str)  # type: ignore[attr-defined]
    _impl.__annotations__ = {p.name: p.annotation for p in params}
    _impl.__annotations__["return"] = str
    return _impl


def build_server() -> FastMCP:
    load_tool_runtime_config()
    mcp = FastMCP("cpe", instructions=INSTRUCTIONS)
    actions = SwarmActions()
    for name in ACTION_NAMES:
        method = getattr(actions, name)
        mcp.add_tool(_build_tool_fn(name, method), name=name)
    return mcp


def main() -> None:
    # Quiet JSON noise on stderr can confuse some MCP hosts; keep stdout clean for stdio.
    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
