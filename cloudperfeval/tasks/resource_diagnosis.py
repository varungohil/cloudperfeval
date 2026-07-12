"""Resource diagnosis: identify the bottleneck resource and affected service(s).

Under sustained load the agent must determine whether the root cause is CPU,
memory, network, or disk pressure, and localize it to the relevant service.
For single-request workloads the agent is given a specific Jaeger trace ID.
For network bottlenecks the agent submits the starting and ending services on
the congested path (source and destination).
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from cloudperfeval.config import config
from cloudperfeval.evaluators.resource import eval_resource_diagnosis
from cloudperfeval.tasks.base import PerformanceTask

if TYPE_CHECKING:
    from cloudperfeval.evaluators.bottleneck import GroundTruth
    from cloudperfeval.suites.base import SuiteSpec
    from cloudperfeval.workload.generator import WorkloadResult, WorkloadSpec

RESOURCE_SUBMIT_SCHEMA = textwrap.dedent("""\
    For CPU, memory, or disk bottlenecks:
    submit({
      "resource": "cpu|mem|disk",
      "service": "<service-name>",
      "reason": "<short evidence-based explanation>"
    })

    For network bottlenecks (congestion between two services):
    submit({
      "resource": "network",
      "from_service": "<starting-service>",
      "to_service": "<ending-service>",
      "reason": "<short evidence-based explanation>"
    })""")


class ResourceDiagnosis(PerformanceTask):
    task_type = "resource_diagnosis"

    def __init__(self, endpoint: str, baseline_p95_ms: float | None = None, jaeger=None):
        super().__init__(jaeger=jaeger)
        self.endpoint = endpoint
        self.baseline_p95_ms = baseline_p95_ms

    def get_task_description(self, workload_result: "WorkloadResult",
                             stack_name: str, multi_fault: bool = False,
                             suite: "SuiteSpec | None" = None,
                             workload: "WorkloadSpec | None" = None) -> str:
        target_name = suite.description if suite else "a microservice application"
        goal = textwrap.dedent("""\
            Goal:
              Investigate traces, metrics, and logs to identify:
                1. Which resource is the bottleneck: cpu, mem, network, or disk
                2. Where it applies:
                   - for cpu, mem, or disk: the affected microservice
                   - for network: the starting and ending services on the
                     congested path (from_service -> to_service)
            """)
        submit_block = textwrap.dedent(f"""\
            When confident, submit using one of the schemas below:

            ```
            {RESOURCE_SUBMIT_SCHEMA}
            ```
            """)

        if workload and workload.mode == "single":
            trace_id = workload_result.primary_trace_id() or "(no trace captured)"
            p95 = workload_result.p95_ms
            p95_str = f"{p95:.0f}ms" if p95 is not None else "elevated"
            multi_note = (
                "\n              Note: More than one resource or service may show "
                "elevated latency; identify the primary bottleneck on the critical "
                "path for this trace."
                if multi_fault else ""
            )
            return textwrap.dedent(f"""\
                You are an expert SRE debugging a latency anomaly in
                {target_name} deployed on a Docker Swarm stack named "{stack_name}".
                Telemetry is available via Prometheus (node/host metrics) and Jaeger
                (distributed traces).

                Symptom:
                  A request recorded as Jaeger trace {trace_id} exhibits elevated
                  end-to-end latency (observed p95 across recent traffic ~ {p95_str}).{multi_note}

                {goal}
                {submit_block}
                """)

        p95 = workload_result.p95_ms
        p95_str = f"{p95:.0f}ms" if p95 is not None else "significantly elevated"
        baseline = (
            f" (healthy baseline is ~{self.baseline_p95_ms:.0f}ms)"
            if self.baseline_p95_ms is not None else ""
        )
        target = workload.target_url(config.get("frontend_url", ""))
        multi_note = (
            "\n              Note: More than one resource or service may show stress; "
            "identify the primary bottleneck on the critical path."
            if multi_fault else ""
        )
        start_ts = workload_result.load_start_ts
        end_ts = workload_result.load_end_ts
        if start_ts is not None and end_ts is not None:
            window_note = (
                "\n              The load ran during this window (epoch seconds):"
                f"\n                start_ts={start_ts:.0f}  end_ts={end_ts:.0f}"
                "\n              Use query_metric_range(promql, start_ts, end_ts) or"
                " get_traces(service, start_ts, end_ts) to inspect metrics and"
                " traces over exactly this interval.\n"
            )
        else:
            window_note = ""
        return textwrap.dedent(f"""\
            You are an expert SRE debugging a performance regression in
            {target_name} deployed on a Docker Swarm stack named "{stack_name}".
            Telemetry is available via Prometheus (node/host metrics) and Jaeger
            (distributed traces).

            Symptom:
              Under load, the URL {target} is slow: observed p95
              end-to-end latency is ~ {p95_str}{baseline}.{multi_note}

            {goal}{window_note}
            {submit_block}
            """)

    def get_instructions(self) -> str:
        return (
            "Investigate using the read-only observability APIs (traces, metrics, "
            "logs, service/node state). Do NOT modify the cluster. When confident, "
            f"submit your diagnosis:\n\n```\n{RESOURCE_SUBMIT_SCHEMA}\n```\n"
        )

    def eval(self, soln, trace: list[dict], duration: float, *,
             ground_truth: "GroundTruth",
             workload_result: "WorkloadResult") -> dict:
        results = eval_resource_diagnosis(soln, ground_truth)
        results["task_type"] = self.task_type
        results["steps"] = sum(1 for m in trace if m.get("role") == "assistant")
        results["duration_sec"] = round(duration, 2)
        results["fault_type"] = ground_truth.fault_type
        results["workload_p95_ms"] = workload_result.p95_ms
        results["reference_trace_ids"] = ground_truth.reference_trace_ids
        if ground_truth.fault_targets:
            results["fault_targets"] = ground_truth.fault_targets
        return results
