"""CLI fallback for coding agents: python -m cloudperfeval.tools.call <action> ..."""

from __future__ import annotations

import argparse
import json
import os
import sys

from cloudperfeval.tools.dispatch import ACTION_NAMES, dispatch_action, load_tool_runtime_config


def available_actions() -> tuple[str, ...]:
    disabled = {
        item.strip()
        for item in os.environ.get("CPE_DISABLED_ACTIONS", "").split(",")
        if item.strip()
    }
    return tuple(name for name in ACTION_NAMES if name not in disabled)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m cloudperfeval.tools.call",
        description="Invoke a CloudPerfEval SwarmActions tool (coding-agent primary interface).",
    )
    p.add_argument(
        "action",
        nargs="?",
        choices=available_actions(),
        help="Action name. Omit with --list to print actions.",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List available actions and exit",
    )
    p.add_argument(
        "--json",
        dest="json_args",
        type=str,
        default=None,
        help='JSON object of kwargs, e.g. \'{"service":"frontend-service"}\'',
    )
    p.add_argument(
        "--arg",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Keyword argument (repeatable). Values are JSON-decoded when possible.",
    )
    return p.parse_args(argv)


def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list or not args.action:
        for name in available_actions():
            print(name)
        return 0 if args.list else 2

    # Gateway clients only proxy; host config is applied by the privileged server.
    if not os.environ.get("CPE_TOOL_SOCKET"):
        load_tool_runtime_config()
    kwargs: dict = {}
    if args.json_args:
        parsed = json.loads(args.json_args)
        if not isinstance(parsed, dict):
            print("Error: --json must be a JSON object", file=sys.stderr)
            return 2
        kwargs.update(parsed)
    for item in args.arg:
        if "=" not in item:
            print(f"Error: --arg must be KEY=VALUE, got {item!r}", file=sys.stderr)
            return 2
        key, value = item.split("=", 1)
        kwargs[key] = _parse_value(value)

    print(dispatch_action(args.action, **kwargs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
