"""Service diagnosis: identify the bottleneck microservice.

For single-request workloads the agent is given a specific Jaeger trace ID.
Under sustained load the agent must explore traces, metrics, and logs to
localize the offending service.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from cloudperfeval.config import config
from cloudperfeval.tasks.base import SUBMIT_SCHEMA, PerformanceTask

if TYPE_CHECKING:
    from cloudperfeval.suites.base import SuiteSpec
    from cloudperfeval.workload.generator import WorkloadResult, WorkloadSpec


class ServiceDiagnosis(PerformanceTask):
    task_type = "service_diagnosis"

    def __init__(self, endpoint: str = "", baseline_p95_ms: float | None = None,
                 jaeger=None):
        super().__init__(jaeger=jaeger)
        self.endpoint = endpoint
        self.baseline_p95_ms = baseline_p95_ms

    def get_task_description(self, workload_result: "WorkloadResult",
                             stack_name: str, multi_fault: bool = False,
                             suite: "SuiteSpec | None" = None,
                             workload: "WorkloadSpec | None" = None) -> str:
        target_name = suite.description if suite else "a microservice application"
        goal_single = textwrap.dedent("""\
            Goal:
              Identify the single microservice that is the primary bottleneck
              for this trace — the service where the time is actually being
              spent (not merely a caller that is waiting on a downstream).
            """)
        goal_sustained = textwrap.dedent("""\
            Goal:
              Investigate traces, metrics, and logs to identify the single
              microservice that is the root-cause bottleneck for this slowdown.
            """)
        submit_block = textwrap.dedent(f"""\
            When confident, submit:

            ```
            {SUBMIT_SCHEMA}
            ```
            """)

        if workload and workload.mode == "single":
            trace_id = workload_result.primary_trace_id() or "(no trace captured)"
            p95 = workload_result.p95_ms
            p95_str = f"{p95:.0f}ms" if p95 is not None else "elevated"
            multi_note = (
                "\n              Note: More than one service may show elevated latency; "
                "identify the primary bottleneck on the critical path for this trace."
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

                {goal_single}
                {submit_block}
                """)

        p95 = workload_result.p95_ms
        p95_str = f"{p95:.0f}ms" if p95 is not None else "significantly elevated"
        baseline = (
            f" (healthy baseline is ~{self.baseline_p95_ms:.0f}ms)"
            if self.baseline_p95_ms is not None else ""
        )
        target = (
            workload.target_url(config.get("frontend_url", ""))
            if workload else self.endpoint
        )
        multi_note = (
            "\n              Note: More than one service may be under stress; "
            "identify the primary bottleneck on the critical path."
            if multi_fault else ""
        )
        start_ts = workload_result.load_start_ts
        end_ts = workload_result.load_end_ts
        if start_ts is not None and end_ts is not None:
            window_note = (
                "\n              The load ran during this window (epoch seconds):"
                f"\n                start_ts={start_ts:.0f}  end_ts={end_ts:.0f}"
                "\n              Use get_traces(service, start_ts, end_ts) or"
                " query_metric_range(promql, start_ts, end_ts) over this interval.\n"
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

            {goal_sustained}{window_note}
            {submit_block}
            """)
