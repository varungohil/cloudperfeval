#!/usr/bin/env python3
"""Run one cloudperfeval problem end-to-end."""

import argparse
import asyncio
import sys

from cloudperfeval.agents.factory import AGENT_CHOICES, create_agent
from cloudperfeval.config import config
from cloudperfeval.fault import FaultInjectionError
from cloudperfeval.orchestrator import Orchestrator
from cloudperfeval.problems.registry import ProblemRegistry
from cloudperfeval.stored_run import StoredRun
from cloudperfeval.workload import TraceCaptureError


def parse_args():
    p = argparse.ArgumentParser(description="Run a cloud performance-debugging task")
    p.add_argument("--problem-id", type=str, help="Problem ID from the registry")
    p.add_argument(
        "--agent",
        type=str,
        default="manual",
        choices=AGENT_CHOICES,
        help="Agent backend: manual, llm, codex, or claude-code",
    )
    p.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model override for llm / codex / claude-code agents",
    )
    p.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Turn budget for llm/manual; also scales timeout for codex/claude-code",
    )
    p.add_argument("--config", type=str, default=None, help="Path to config YAML")
    p.add_argument(
        "--suite", "--benchmark", "--app", dest="suite", type=str, default=None,
        help="List/filter problems for one suite",
    )
    p.add_argument("--stack-name", type=str, default=None, help="Override config stack_name")
    p.add_argument("--list", action="store_true", help="List available problem IDs and exit")
    p.add_argument(
        "--list-snapshots",
        action="store_true",
        help="List snapshots (from prior --phase snapshot) and exit",
    )
    p.add_argument(
        "--snapshot-id",
        type=str,
        default=None,
        help="Snapshot id to resume (required for --phase run)",
    )
    p.add_argument(
        "--phase",
        choices=("full", "snapshot", "run"),
        default="full",
        help=(
            "full: inject, load, Jaeger wait, agent loop (default). "
            "snapshot: inject + curl/wrk, save snapshot, recover fault, exit. "
            "run: resume a snapshot by --snapshot-id, Jaeger wait, agent loop."
        ),
    )
    p.add_argument(
        "--no-agent-sandbox",
        action="store_true",
        help="Disable the Docker filesystem jail for codex/claude-code (debug escape hatch)",
    )
    return p.parse_args()


def _apply_sandbox_cli(args) -> None:
    if not args.no_agent_sandbox:
        return
    sandbox = dict(config.get("agent_sandbox", {}) or {})
    sandbox["enabled"] = False
    config.set("agent_sandbox", sandbox)


async def main():
    args = parse_args()
    if args.config:
        config.reload(args.config)
    if args.stack_name:
        config.set("stack_name", args.stack_name)
    _apply_sandbox_cli(args)

    registry = ProblemRegistry()

    if args.list_snapshots:
        print("Snapshots:")
        print(StoredRun.format_list(problem_id=args.problem_id))
        return

    if args.list or not args.problem_id:
        print("Registered suites:", ", ".join(registry.list_suites()))
        print("Available problems:")
        for pid in registry.get_problem_ids(suite=args.suite):
            print(f"  - {pid}")
        if not args.problem_id:
            print("\nPass --problem-id <id> to run one.")
        return

    if args.phase == "run" and not args.snapshot_id:
        print("Error: --phase run requires --snapshot-id.", file=sys.stderr)
        print("Snapshots:", file=sys.stderr)
        print(StoredRun.format_list(problem_id=args.problem_id), file=sys.stderr)
        sys.exit(1)

    agent = create_agent(args.agent, model=args.model)
    orch = Orchestrator()
    orch.register_agent(agent, name=f"{args.agent}-agent")

    print("=" * 60)
    print(f"Problem : {args.problem_id}")
    print(f"Phase   : {args.phase}")
    if args.snapshot_id:
        print(f"Snapshot: {args.snapshot_id}")
    print(f"Agent   : {args.agent}" + (f" ({args.model})" if args.model else ""))
    print("=" * 60)

    setup_failed = False
    try:
        try:
            task_desc, instructions, apis = orch.init_problem(
                args.problem_id,
                phase=args.phase,
                snapshot_id=args.snapshot_id,
            )
        except (FaultInjectionError, TraceCaptureError) as e:
            setup_failed = True
            if orch.problem is not None:
                print(f"[ENV] Setup failed ({type(e).__name__}); recovering...", file=sys.stderr)
                orch.problem.teardown()
            print(f"Setup failed: {e}", file=sys.stderr)
        else:
            if args.phase == "snapshot":
                print("[ENV] Snapshot saved. Fault recovered.")
                return

            agent.init_context(task_desc, instructions, apis)

            out = await orch.run(max_steps=args.max_steps)
            print("\nFinal results:")
            for k, v in out["results"].items():
                print(f"  {k}: {v}")
    finally:
        orch.save_session()

    if setup_failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
