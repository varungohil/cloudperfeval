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

MULTI_FAULT_SUBMIT_SCHEMA = (
    'submit({\n'
    '  "faults": [\n'
    '    {"resource": "cpu|mem|disk", "service": "<service-name>", '
    '"reason": "<short evidence-based explanation>"},\n'
    '    {"resource": "network", "from_service": "<starting-service>", '
    '"to_service": "<ending-service>", '
    '"reason": "<short evidence-based explanation>"}\n'
    '  ]\n'
    '})'
)


def resolve_disclose_url(disclose_url: str | None, frontend_url: str = "") -> str | None:
    """Turn a path or absolute URL into the absolute URL shown in the prompt."""
    if not disclose_url:
        return None
    if disclose_url.startswith("http://") or disclose_url.startswith("https://"):
        return disclose_url.split("?", 1)[0]
    base = (frontend_url or "").rstrip("/")
    path = disclose_url if disclose_url.startswith("/") else f"/{disclose_url}"
    return f"{base}{path.split('?', 1)[0]}"


def sustained_symptom_block(
    *,
    p95_str: str,
    baseline: str,
    symptom_extra: str,
    start_ts: float | None,
    end_ts: float | None,
    window_tool_hint: str,
    disclose_url: str | None = None,
) -> tuple[str, str]:
    """Return ``(symptom_paragraph, window_note)`` for sustained-load prompts.

    When ``disclose_url`` is set, the symptom names that URL as slow. When it is
    None, the symptom only states slow performance over the load-window timestamps.
    """
    has_window = start_ts is not None and end_ts is not None
    if disclose_url:
        symptom = (
            f"Under load, the URL {disclose_url} is slow: observed p95\n"
            f"              end-to-end latency is ~ {p95_str}{baseline}."
            f"{symptom_extra}"
        )
        if has_window:
            window_note = (
                "\n              The load ran during this window (epoch seconds):"
                f"\n                start_ts={start_ts:.0f}  end_ts={end_ts:.0f}"
                f"\n              {window_tool_hint}\n"
            )
        else:
            window_note = ""
        return symptom, window_note

    if has_window:
        symptom = (
            "We observed slow end-to-end performance between these timestamps "
            "(epoch seconds):\n"
            f"                start_ts={start_ts:.0f}  end_ts={end_ts:.0f}\n"
            f"              Observed p95 latency is ~ {p95_str}{baseline}."
            f"{symptom_extra}"
        )
        window_note = f"\n              {window_tool_hint}\n"
    else:
        symptom = (
            f"We observed slow end-to-end performance under load: observed p95 "
            f"latency is ~ {p95_str}{baseline}.{symptom_extra}"
        )
        window_note = ""
    return symptom, window_note


class PerformanceTask:
    task_type: str = "performance"

    def __init__(self, jaeger: JaegerAPI | None = None):
        self.jaeger = jaeger or JaegerAPI("")

    # ---- prompt ----------------------------------------------------------
    def get_task_description(self, workload_result: "WorkloadResult",
                             stack_name: str, multi_fault: bool = False,
                             suite: "SuiteSpec | None" = None,
                             workload: "WorkloadSpec | None" = None,
                             has_decoy: bool = False,
                             disclose_url: str | None = None) -> str:
        raise NotImplementedError

    def get_instructions(self) -> str:
        return (
            "Investigate using the read-only observability APIs (traces, metrics, "
            "logs, service/node state). Do NOT modify the cluster. When confident, "
            f"submit your diagnosis:\n\n```\n{SUBMIT_SCHEMA}\n```\n"
            f"For multi-fault problems use:\n\n```\n{MULTI_FAULT_SUBMIT_SCHEMA}\n```\n"
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
        results["reference_trace_ids"] = ground_truth.reference_trace_ids
        return results
