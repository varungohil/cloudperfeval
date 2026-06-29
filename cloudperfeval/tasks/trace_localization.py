"""Trace-localization task: given one slow trace, name the bottleneck service."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from cloudperfeval.tasks.base import SUBMIT_SCHEMA, PerformanceTask

if TYPE_CHECKING:
    from cloudperfeval.suites.base import SuiteSpec
    from cloudperfeval.workload.generator import WorkloadResult


class TraceLocalizationTask(PerformanceTask):
    task_type = "trace_localization"

    def get_task_description(self, workload_result: "WorkloadResult",
                             stack_name: str, multi_fault: bool = False,
                             suite: "SuiteSpec | None" = None, **_) -> str:
        trace_id = workload_result.primary_trace_id() or "(no trace captured)"
        p95 = workload_result.p95_ms
        p95_str = f"{p95:.0f}ms" if p95 is not None else "elevated"
        multi_note = (
            "\n              Note: More than one service may show elevated latency; "
            "identify the primary bottleneck on the critical path for this trace."
            if multi_fault else ""
        )
        target_name = suite.description if suite else "a microservice application"
        return textwrap.dedent(f"""\
            You are an expert SRE debugging a latency anomaly in
            {target_name} deployed on a Docker Swarm stack named "{stack_name}".
            Telemetry is available via Prometheus (node/host metrics) and Jaeger
            (distributed traces).

            Symptom:
              A request recorded as Jaeger trace {trace_id} exhibits elevated
              end-to-end latency (observed p95 across recent traffic ~ {p95_str}).{multi_note}

            Goal:
              Identify the single microservice that is the primary bottleneck
              for this trace — the service where the time is actually being
              spent (not merely a caller that is waiting on a downstream).

            Start by fetching the trace:

            ```
            get_trace_by_id("{trace_id}")
            ```

            When confident, submit:

            ```
            {SUBMIT_SCHEMA}
            ```
            """)
