"""Service diagnosis: identify the bottleneck microservice.

For single-request workloads the agent is given a specific Jaeger trace ID.
Under sustained load the agent must explore traces, metrics, and logs to
localize the offending service.

Multi-fault problems require reporting every injected fault (resource +
location) via a ``faults`` list.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from cloudperfeval.config import config
from cloudperfeval.tasks.base import (
    MULTI_FAULT_SUBMIT_SCHEMA,
    SUBMIT_SCHEMA,
    PerformanceTask,
    resolve_disclose_url,
    sustained_symptom_block,
)

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
                             workload: "WorkloadSpec | None" = None,
                             has_decoy: bool = False,
                             disclose_url: str | None = None) -> str:
        target_name = suite.description if suite else "a microservice application"
        disclosed = resolve_disclose_url(
            disclose_url, config.get("frontend_url", "")
        )
        latency_ref = (
            "this endpoint's latency" if disclosed else "this slowdown"
        )
        decoy_note = (
            "\n              Note: Some services may show elevated resource use "
            f"that does not contribute to {latency_ref} — do not report "
            "those as root causes."
            if has_decoy else ""
        )
        if multi_fault:
            goal_single = textwrap.dedent("""\
                Goal:
                  Identify ALL performance faults that contribute to this
                  trace's latency. For each, report the bottleneck resource
                  (cpu, mem, network, or disk) and where it applies (service,
                  or from_service -> to_service for network).
                """)
            goal_sustained = textwrap.dedent("""\
                Goal:
                  Investigate traces, metrics, and logs to identify ALL
                  performance faults that contribute to this slowdown.
                  For each, report the bottleneck resource (cpu, mem,
                  network, or disk) and where it applies (service, or
                  from_service -> to_service for network).
                """)
            submit_block = textwrap.dedent(f"""\
                When confident, submit every contributing fault (order does
                not matter):

                ```
                {MULTI_FAULT_SUBMIT_SCHEMA}
                ```
                """)
            multi_note = ""
        else:
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
            multi_note = ""

        symptom_extra = multi_note + decoy_note

        if workload and workload.mode == "single":
            trace_id = workload_result.primary_trace_id() or "(no trace captured)"
            p95 = workload_result.p95_ms
            p95_str = f"{p95:.0f}ms" if p95 is not None else "elevated"
            return textwrap.dedent(f"""\
                You are an expert SRE debugging a latency anomaly in
                {target_name} deployed on a Docker Swarm stack named "{stack_name}".
                Telemetry is available via Prometheus (node/host metrics) and Jaeger
                (distributed traces).

                Symptom:
                  A request recorded as Jaeger trace {trace_id} exhibits elevated
                  end-to-end latency (observed p95 across recent traffic ~ {p95_str}).{symptom_extra}

                {goal_single}
                {submit_block}
                """)

        p95 = workload_result.p95_ms
        p95_str = f"{p95:.0f}ms" if p95 is not None else "significantly elevated"
        baseline = (
            f" (healthy baseline is ~{self.baseline_p95_ms:.0f}ms)"
            if self.baseline_p95_ms is not None else ""
        )
        symptom, window_note = sustained_symptom_block(
            p95_str=p95_str,
            baseline=baseline,
            symptom_extra=symptom_extra,
            start_ts=workload_result.load_start_ts,
            end_ts=workload_result.load_end_ts,
            window_tool_hint=(
                "Use get_traces(service, start_ts, end_ts) or"
                " query_metric_range(promql, start_ts, end_ts) over this interval."
            ),
            disclose_url=disclosed,
        )
        return textwrap.dedent(f"""\
            You are an expert SRE debugging a performance regression in
            {target_name} deployed on a Docker Swarm stack named "{stack_name}".
            Telemetry is available via Prometheus (node/host metrics) and Jaeger
            (distributed traces).

            Symptom:
              {symptom}

            {goal_sustained}{window_note}
            {submit_block}
            """)
