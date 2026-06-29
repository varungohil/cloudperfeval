#!/usr/bin/env python3
"""Batch-run the benchmark over many problems and print a summary."""

import argparse
import asyncio
import json
from pathlib import Path

from cloudperfeval.agents.factory import AGENT_CHOICES, create_agent
from cloudperfeval.config import config
from cloudperfeval.orchestrator import Orchestrator
from cloudperfeval.problems.registry import ProblemRegistry


def parse_args():
    p = argparse.ArgumentParser(description="Run the cloudperfeval benchmark suite")
    p.add_argument("--agent", type=str, default="llm", choices=AGENT_CHOICES)
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
    p.add_argument("--out", type=str, default=None, help="Write summary JSON here")
    return p.parse_args()


async def run_one(problem_id: str, agent_type: str, model: str | None, max_steps: int) -> dict:
    agent = create_agent(agent_type, model=model)
    orch = Orchestrator()
    orch.register_agent(agent, name=f"{agent_type}-agent")
    try:
        task_desc, instructions, apis = orch.init_problem(problem_id)
        agent.init_context(task_desc, instructions, apis)
        out = await orch.run(max_steps=max_steps)
        return out["results"]
    finally:
        orch.save_session()


async def main():
    args = parse_args()
    if args.config:
        config.reload(args.config)
    if args.stack_name:
        config.set("stack_name", args.stack_name)

    registry = ProblemRegistry()
    if args.problem_ids:
        problem_ids = args.problem_ids
    else:
        problem_ids = registry.get_problem_ids(task_type=args.filter, suite=args.suite)

    rows = []
    for pid in problem_ids:
        print("\n" + "#" * 70)
        print(f"# {pid}")
        print("#" * 70)
        try:
            results = await run_one(pid, args.agent, args.model, args.max_steps)
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
    out_path = Path(args.out) if args.out else (
        Path(config.get("results_dir", "./results")) / "bench_summary.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Summary written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
