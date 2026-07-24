#!/usr/bin/env python3
"""Batch-run the benchmark over many problems and print a summary."""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from cloudperfeval.agents.factory import AGENT_CHOICES, create_agent
from cloudperfeval.config import config
from cloudperfeval.fault import FaultInjectionError
from cloudperfeval.orchestrator import Orchestrator
from cloudperfeval.problems.registry import ProblemRegistry
from cloudperfeval.workload import TraceCaptureError

# Setup failures worth another full problem attempt (inject + load + agent).
_SETUP_RETRYABLE = (FaultInjectionError, TraceCaptureError)
_MAX_SETUP_ATTEMPTS = 3
_SETUP_RETRY_WAIT_SEC = 30


def parse_args():
    p = argparse.ArgumentParser(description="Run the cloudperfeval benchmark suite")
    p.add_argument(
        "--agent",
        type=str,
        default="llm",
        choices=AGENT_CHOICES,
        help="Agent backend: manual, llm, codex, or claude-code",
    )
    p.add_argument("--model", type=str, default=None)
    p.add_argument("--max-steps", type=int, default=15)
    p.add_argument("--config", type=str, default=None, help="Path to config YAML")
    p.add_argument(
        "--suite", "--benchmark", "--app", dest="suite", type=str, default=None,
        help="Only run problems for this suite",
    )
    p.add_argument("--stack-name", type=str, default=None)
    p.add_argument("--filter", type=str, default=None,
                   help="Only run problems whose ID contains this substring")
    p.add_argument("--problem-ids", nargs="*", default=None,
                   help="Explicit list of problem IDs to run")
    p.add_argument(
        "--outdir",
        type=str,
        default=None,
        help="Directory for summary, session JSON/logs, and agent workdirs",
    )
    p.add_argument(
        "--out",
        type=str,
        default=None,
        help="Summary JSON path (default: <outdir or results_dir>/bench_summary.json)",
    )
    p.add_argument(
        "--no-agent-sandbox",
        action="store_true",
        help="Disable the Docker filesystem jail for codex/claude-code (debug escape hatch)",
    )
    return p.parse_args()


async def run_one(problem_id: str, agent_type: str, model: str | None, max_steps: int) -> dict:
    agent = create_agent(agent_type, model=model)
    orch = Orchestrator()
    orch.register_agent(agent, name=f"{agent_type}-agent")
    try:
        try:
            task_desc, instructions, apis = orch.init_problem(problem_id)
            agent.init_context(task_desc, instructions, apis)
            out = await orch.run(max_steps=max_steps)
            return out["results"]
        except _SETUP_RETRYABLE:
            if orch.problem is not None:
                print(
                    f"[BENCH] Setup failed; recovering fault for '{problem_id}'...",
                    file=sys.stderr,
                )
                try:
                    orch.problem.teardown()
                except Exception as te:
                    print(f"[BENCH] Teardown after setup failure: {te}", file=sys.stderr)
            raise
    finally:
        orch.save_session()


async def run_one_with_setup_retries(
    problem_id: str, agent_type: str, model: str | None, max_steps: int
) -> dict:
    """Retry the full problem up to 3 times on TraceCaptureError / FaultInjectionError."""
    last_err: Exception | None = None
    for attempt in range(1, _MAX_SETUP_ATTEMPTS + 1):
        try:
            results = await run_one(problem_id, agent_type, model, max_steps)
            results["setup_attempts"] = attempt
            return results
        except _SETUP_RETRYABLE as e:
            last_err = e
            print(
                f"[BENCH] {type(e).__name__} on attempt {attempt}/{_MAX_SETUP_ATTEMPTS}: {e}",
                file=sys.stderr,
            )
            if attempt < _MAX_SETUP_ATTEMPTS:
                print(
                    f"[BENCH] Retrying '{problem_id}' in {_SETUP_RETRY_WAIT_SEC}s...",
                    file=sys.stderr,
                )
                time.sleep(_SETUP_RETRY_WAIT_SEC)
    assert last_err is not None
    return {
        "success": False,
        "error": f"{type(last_err).__name__}: {last_err}",
        "setup_attempts": _MAX_SETUP_ATTEMPTS,
    }


async def main():
    args = parse_args()
    if args.config:
        config.reload(args.config)
    if args.stack_name:
        config.set("stack_name", args.stack_name)
    if args.no_agent_sandbox:
        sandbox = dict(config.get("agent_sandbox", {}) or {})
        sandbox["enabled"] = False
        config.set("agent_sandbox", sandbox)
    if args.outdir:
        outdir = Path(args.outdir).resolve()
        outdir.mkdir(parents=True, exist_ok=True)
        config.set("results_dir", str(outdir))
        print(f"[BENCH] Writing artifacts under {outdir}")

    registry = ProblemRegistry()
    if args.problem_ids:
        problem_ids = args.problem_ids
    else:
        problem_ids = registry.get_problem_ids(task_type=args.filter, suite=args.suite)

    rows = []
    for i, pid in enumerate(problem_ids):
        if i > 0:
            print("\n[BENCH] Waiting 60s before next problem...")
            time.sleep(60)
        print("\n" + "#" * 70)
        print(f"# {pid}")
        print("#" * 70)
        try:
            results = await run_one_with_setup_retries(
                pid, args.agent, args.model, args.max_steps
            )
        except Exception as e:
            results = {"success": False, "error": f"{type(e).__name__}: {e}"}
        rows.append({"problem_id": pid, **results})

    passed = sum(1 for r in rows if r.get("success"))
    total = len(rows)
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for r in rows:
        mark = "PASS" if r.get("success") else "FAIL"
        print(f"  [{mark}] {r['problem_id']:<40} "
              f"pred={r.get('predicted_service')} exp={r.get('expected_service')} "
              f"steps={r.get('steps')}")
    print(f"\nAccuracy: {passed}/{total} = {(passed / total * 100) if total else 0:.1f}%")

    summary = {"accuracy": passed / total if total else 0, "passed": passed,
               "total": total, "rows": rows}
    results_dir = Path(config.get("results_dir", "./results"))
    out_path = Path(args.out) if args.out else (results_dir / "bench_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Summary written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
