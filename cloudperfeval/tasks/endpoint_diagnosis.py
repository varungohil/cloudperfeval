"""Endpoint-diagnosis task: an endpoint is slow under load; find the bottleneck.

No trace ID is handed to the agent — it must explore traces, metrics, and logs
to localize the offending service.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from cloudperfeval.config import config
from cloudperfeval.tasks.base import SUBMIT_SCHEMA, PerformanceTask

if TYPE_CHECKING:
    from cloudperfeval.suites.base import SuiteSpec
    from cloudperfeval.workload.generator import WorkloadResult, WorkloadSpec


class EndpointDiagnosisTask(PerformanceTask):
    task_type = "endpoint_diagnosis"

    def __init__(self, endpoint: str, baseline_p95_ms: float | None = None, jaeger=None):
        super().__init__(jaeger=jaeger)
        self.endpoint = endpoint
        self.baseline_p95_ms = baseline_p95_ms

    def get_task_description(self, workload_result: "WorkloadResult",
                             stack_name: str, multi_fault: bool = False,
                             suite: "SuiteSpec | None" = None,
                             workload: "WorkloadSpec | None" = None) -> str:
        p95 = workload_result.p95_ms
        p95_str = f"{p95:.0f}ms" if p95 is not None else "significantly elevated"
        baseline = (
            f" (healthy baseline is ~{self.baseline_p95_ms:.0f}ms)"
            if self.baseline_p95_ms is not None else ""
        )
        if workload and workload.mode == "sustained":
            target = workload.target_url(config.get("frontend_url", ""))
            target_label = "URL"
            path_note = " for this URL"
        else:
            target = self.endpoint
            target_label = "endpoint"
            path_note = " for this endpoint"
        multi_note = (
            f"\n              Note: More than one service may be under stress; "
            f"identify the primary bottleneck on the critical path{path_note}."
            if multi_fault else ""
        )
        target_name = suite.description if suite else "a microservice application"
        entry_service = suite.entry_trace_service if suite else "frontend-service"
        start_ts = workload_result.load_start_ts
        end_ts = workload_result.load_end_ts
        if start_ts is not None and end_ts is not None:
            window_note = (
                "\n              The load ran during this window (epoch seconds):"
                f"\n                start_ts={start_ts:.0f}  end_ts={end_ts:.0f}"
                "\n              Use query_metric_range(promql, start_ts, end_ts) to"
                " inspect historical metrics over exactly this interval.\n"
            )
        else:
            window_note = ""
        return textwrap.dedent(f"""\
            You are an expert SRE debugging a performance regression in
            {target_name} deployed on a Docker Swarm stack named "{stack_name}".
            Telemetry is available via Prometheus (node/host metrics) and Jaeger
            (distributed traces).

            Symptom:
              Under load, the {target_label} {target} is slow: observed p95
              end-to-end latency is ~ {p95_str}{baseline}.{multi_note}

            Goal:
              Investigate traces, metrics, and logs to identify the single
              microservice that is the root-cause bottleneck for this slowdown.
            {window_note}
            Useful first steps:
            ```
            list_trace_services()
            ```
            then inspect per-operation latency, e.g.
            ```
            get_traces("{entry_service}")
            ```

            When confident, submit:

            ```
            {SUBMIT_SCHEMA}
            ```
            """)
