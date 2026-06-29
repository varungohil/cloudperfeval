"""Base class for performance-debugging tasks.

A task owns the *agent-facing* contract for a problem:
  - get_task_description(): the symptom prompt (built from the workload result)
  - get_instructions(): response-format instructions
  - submission schema (documented in the prompt)
  - eval(): grade the agent's submission against ground truth

Tasks are stateless w.r.t. the cluster; the Problem injects fault/load and
passes the resulting `WorkloadResult` + `GroundTruth` into the task at prompt-
build and eval time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cloudperfeval.observer.traces import JaegerAPI

if TYPE_CHECKING:
    from cloudperfeval.evaluators.bottleneck import GroundTruth
    from cloudperfeval.workload.generator import WorkloadResult, WorkloadSpec
    from cloudperfeval.suites.base import SuiteSpec


SUBMIT_SCHEMA = (
    'submit({"root_cause_service": "<service-name>", '
    '"reason": "<short evidence-based explanation>"})'
)


class PerformanceTask:
    task_type: str = "performance"

    def __init__(self, jaeger: JaegerAPI | None = None):
        self.jaeger = jaeger or JaegerAPI("")

    # ---- prompt ----------------------------------------------------------
    def get_task_description(self, workload_result: "WorkloadResult",
                             stack_name: str, multi_fault: bool = False,
                             suite: "SuiteSpec | None" = None,
                             workload: "WorkloadSpec | None" = None) -> str:
        raise NotImplementedError

    def get_instructions(self) -> str:
        return (
            "Investigate using the read-only observability APIs (traces, metrics, "
            "logs, service/node state). Do NOT modify the cluster. When confident, "
            f"submit your diagnosis:\n\n```\n{SUBMIT_SCHEMA}\n```\n"
        )

    # ---- grading ---------------------------------------------------------
    def eval(self, soln, trace: list[dict], duration: float, *,
             ground_truth: "GroundTruth",
             workload_result: "WorkloadResult") -> dict:
        from cloudperfeval.evaluators.bottleneck import eval_with_trace_oracle

        results = eval_with_trace_oracle(soln, ground_truth, self.jaeger)
        results["task_type"] = self.task_type
        results["steps"] = sum(1 for m in trace if m.get("role") == "assistant")
        results["duration_sec"] = round(duration, 2)
        results["fault_type"] = ground_truth.fault_type
        results["workload_p95_ms"] = workload_result.p95_ms
        results["reference_trace_ids"] = ground_truth.reference_trace_ids[:3]
        return results
