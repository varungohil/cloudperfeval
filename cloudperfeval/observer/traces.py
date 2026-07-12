"""Jaeger access over HTTP plus trace-analysis helpers.

Beyond the agent-facing summarize/raw helpers, this module computes per-service
"self time" (exclusive span time) which the evaluator uses as a programmatic
bottleneck oracle, and captures the trace IDs/latency produced by a workload.
"""

import json
from datetime import datetime

import requests


class JaegerAPI:
    def __init__(self, base_url: str):
        self.base_url = (base_url or "").rstrip("/")

    def _get(self, path: str, params: dict | None = None, timeout: int = 60) -> dict | None:
        try:
            resp = requests.get(f"{self.base_url}{path}", params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"Jaeger request failed ({path}): {e}")
            return None

    @staticmethod
    def _format_json(data, empty_msg: str) -> str:
        if not data:
            return empty_msg
        return json.dumps(data, indent=2)

    # ---- raw access ------------------------------------------------------
    def get_services(self) -> list:
        body = self._get("/api/services", timeout=30)
        return (body or {}).get("data") or []

    def get_operations(self, service: str) -> list:
        body = self._get("/api/operations", params={"service": service}, timeout=30)
        return (body or {}).get("data") or []

    def get_traces(
        self,
        service: str,
        minutes: int = 5,
        limit: int = 1000,
        operation: str | None = None,
        min_duration_ms: float | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> list:
        time_params, _ = self.trace_time_params(
            start_ts=start_ts, end_ts=end_ts, minutes=minutes,
        )
        params: dict = {"service": service, "limit": limit, **time_params}
        if "start" not in params:
            params["lookback"] = f"{int(minutes)}m"
        if operation:
            params["operation"] = operation
        if min_duration_ms is not None:
            params["minDuration"] = f"{min_duration_ms:g}ms"
        body = self._get("/api/traces", params=params)
        traces = (body or {}).get("data") or []
        if "start" in params:
            traces = self._filter_traces_by_root_start(
                traces, params["start"], params["end"],
            )
        return traces

    def traces_above_latency(
        self,
        service: str,
        min_latency_ms: float,
        minutes: int = 5,
        limit: int = 1000,
        operation: str | None = None,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> list:
        """Traces whose end-to-end (root span) latency is >= min_latency_ms."""
        traces = self.get_traces(
            service,
            minutes=minutes,
            limit=limit,
            operation=operation,
            min_duration_ms=min_latency_ms,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        filtered = [
            t for t in traces
            if self.trace_root_duration_ms(t) >= min_latency_ms
        ]
        filtered.sort(key=self.trace_root_duration_ms, reverse=True)
        return filtered

    def get_trace_by_id(self, trace_id: str) -> list:
        body = self._get(f"/api/traces/{trace_id.strip()}")
        return (body or {}).get("data") or []

    def get_dependency_graph(self, minutes: int = 1440) -> dict:
        end_ts = int(datetime.now().timestamp() * 1000)
        params = {"endTs": end_ts, "lookback": int(minutes) * 60 * 1000}
        return self._get("/api/dependencies", params=params) or {}

    def format_raw_traces(self, traces: list, context: str = "") -> str:
        suffix = f" {context}" if context else ""
        return self._format_json(traces, f"(no traces found{suffix})")

    # ---- latency summary -------------------------------------------------
    @staticmethod
    def _percentile(values, pct):
        if not values:
            return 0.0
        values = sorted(values)
        k = max(0, min(len(values) - 1, int(round((pct / 100.0) * (len(values) - 1)))))
        return values[k]

    @staticmethod
    def _children_duration(trace: dict) -> dict[str, int]:
        children_dur: dict[str, int] = {}
        for span in trace.get("spans", []):
            for ref in span.get("references", []):
                if ref.get("refType") == "CHILD_OF":
                    parent = ref.get("spanID")
                    children_dur[parent] = children_dur.get(parent, 0) + span.get("duration", 0)
        return children_dur

    def summarize(
        self,
        service: str,
        minutes: int = 5,
        limit: int = 100,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> str:
        _, window = self.trace_time_params(
            start_ts=start_ts, end_ts=end_ts, minutes=minutes,
        )
        traces = self.get_traces(
            service,
            minutes=minutes,
            limit=limit,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        if not traces:
            return f"(no traces found for service '{service}' {window})"

        by_op: dict[str, list[int]] = {}
        by_op_self: dict[str, list[int]] = {}
        errors: dict[str, int] = {}
        for trace in traces:
            children_dur = self._children_duration(trace)
            for span in trace.get("spans", []):
                op = span.get("operationName", "unknown")
                duration = span.get("duration", 0)
                by_op.setdefault(op, []).append(duration)
                self_time = duration - children_dur.get(span["spanID"], 0)
                if self_time < 0:
                    self_time = 0
                by_op_self.setdefault(op, []).append(self_time)
                for tag in span.get("tags", []):
                    if tag.get("key") == "error" and tag.get("value") in (True, "true"):
                        errors[op] = errors.get(op, 0) + 1

        lines = [
            "OPERATION\tCOUNT\tP50_ms\tP95_ms\tP99_ms\t"
            "SELF_P50_ms\tSELF_P95_ms\tSELF_P99_ms\tERRORS"
        ]
        for op in sorted(by_op, key=lambda o: self._percentile(by_op[o], 95), reverse=True):
            durs_ms = [d / 1000.0 for d in by_op[op]]
            self_durs_ms = [d / 1000.0 for d in by_op_self.get(op, [])]
            lines.append(
                f"{op}\t{len(durs_ms)}\t"
                f"{self._percentile(durs_ms, 50):.1f}\t"
                f"{self._percentile(durs_ms, 95):.1f}\t"
                f"{self._percentile(durs_ms, 99):.1f}\t"
                f"{self._percentile(self_durs_ms, 50):.1f}\t"
                f"{self._percentile(self_durs_ms, 95):.1f}\t"
                f"{self._percentile(self_durs_ms, 99):.1f}\t"
                f"{errors.get(op, 0)}"
            )
        return "\n".join(lines)

    # ---- analysis helpers (used by workload capture + evaluator) ---------
    @staticmethod
    def _span_service_map(trace: dict) -> dict[str, str]:
        processes = trace.get("processes", {})
        out = {}
        for span in trace.get("spans", []):
            pid = span.get("processID")
            proc = processes.get(pid, {})
            out[span["spanID"]] = proc.get("serviceName", pid or "unknown")
        return out

    @classmethod
    def self_time_by_service(cls, trace: dict) -> dict[str, float]:
        """Exclusive (self) time per service in microseconds.

        self_time(span) = duration - sum(durations of its direct children).
        Aggregated by the span's service. This approximates where wall-clock
        time is actually *spent* (rather than double-counting parent spans).
        """
        spans = trace.get("spans", [])
        svc_of = cls._span_service_map(trace)

        children_dur: dict[str, int] = {}
        for span in spans:
            for ref in span.get("references", []):
                if ref.get("refType") == "CHILD_OF":
                    parent = ref.get("spanID")
                    children_dur[parent] = children_dur.get(parent, 0) + span.get("duration", 0)

        by_service: dict[str, float] = {}
        for span in spans:
            self_time = span.get("duration", 0) - children_dur.get(span["spanID"], 0)
            if self_time < 0:
                self_time = 0
            svc = svc_of.get(span["spanID"], "unknown")
            by_service[svc] = by_service.get(svc, 0.0) + self_time
        return by_service

    @classmethod
    def bottleneck_service(cls, trace: dict) -> str | None:
        """Service accounting for the largest exclusive time in a trace."""
        by_service = cls.self_time_by_service(trace)
        if not by_service:
            return None
        return max(by_service, key=by_service.get)

    @staticmethod
    def oracle_vote_count(captured: int) -> int:
        """Number of slowest traces included in the trace-oracle majority vote."""
        return max(1, captured // 5)

    @staticmethod
    def trace_root_duration_ms(trace: dict) -> float:
        """End-to-end duration of a trace = duration of its root span (ms)."""
        spans = trace.get("spans", [])
        roots = [s for s in spans if not any(
            r.get("refType") == "CHILD_OF" for r in s.get("references", [])
        )]
        if not roots:
            return 0.0
        return max(s.get("duration", 0) for s in roots) / 1000.0

    @staticmethod
    def trace_root_start_us(trace: dict) -> int | None:
        """Root span start time in microseconds, or None if no root span."""
        spans = trace.get("spans", [])
        roots = [s for s in spans if not any(
            r.get("refType") == "CHILD_OF" for r in s.get("references", [])
        )]
        if not roots:
            return None
        return min(s.get("startTime", 0) for s in roots)

    @staticmethod
    def trace_time_params(
        start_ts: float | None,
        end_ts: float | None,
        minutes: int,
    ) -> tuple[dict[str, int], str]:
        """Jaeger ``start``/``end`` (microseconds) and a human window label."""
        if start_ts is not None and end_ts is not None:
            if start_ts >= end_ts:
                raise ValueError("start_ts must be before end_ts")
            start_us = int(start_ts * 1_000_000)
            end_us = int(end_ts * 1_000_000)
            return (
                {"start": start_us, "end": end_us},
                f"with root span start in [{start_ts:.0f}, {end_ts:.0f}] (epoch s)",
            )
        if start_ts is not None or end_ts is not None:
            raise ValueError("start_ts and end_ts must both be set or both omitted")
        return ({}, f"in the last {minutes}m")

    @classmethod
    def _filter_traces_by_root_start(
        cls, traces: list, start_us: int, end_us: int,
    ) -> list:
        """Keep traces whose root span starts within [start_us, end_us]."""
        filtered = []
        for trace in traces:
            root_start = cls.trace_root_start_us(trace)
            if root_start is not None and start_us <= root_start <= end_us:
                filtered.append(trace)
        return filtered

    def capture_trace(self, trace_id: str) -> dict | None:
        """Summarize one trace by ID (e.g. from curl ``X-Trace-Id`` header)."""
        traces = self.get_trace_by_id(trace_id)
        if not traces:
            return None
        trace = traces[0]
        tid = trace.get("traceID") or trace_id.strip()
        dur = self.trace_root_duration_ms(trace)
        return {
            "trace_ids": [tid],
            "oracle_trace_ids": [tid],
            "p50_ms": dur,
            "p95_ms": dur,
            "sample_latencies_ms": [round(dur, 2)],
            "voted_bottleneck": self.bottleneck_service(trace),
        }

    def capture_recent(
        self,
        service: str,
        minutes: int = 5,
        limit: int = 200,
        start_ts: float | None = None,
        end_ts: float | None = None,
    ) -> dict:
        """Summarize traces produced by a recent workload run.

        Returns trace_ids (slowest first, up to ``limit``), oracle_trace_ids
        (slowest ~20% used for the majority-vote bottleneck), p50/p95 end-to-end
        latency in ms, and voted_bottleneck.
        """
        traces = self.get_traces(
            service,
            minutes=minutes,
            limit=limit,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        if not traces:
            return {
                "trace_ids": [],
                "oracle_trace_ids": [],
                "p50_ms": None,
                "p95_ms": None,
                "sample_latencies_ms": [],
                "voted_bottleneck": None,
            }

        rows = []
        for trace in traces:
            tid = trace.get("traceID") or (trace.get("spans") or [{}])[0].get("traceID")
            rows.append((tid, self.trace_root_duration_ms(trace), trace))
        rows.sort(key=lambda r: r[1], reverse=True)

        latencies = [r[1] for r in rows]
        vote_n = self.oracle_vote_count(len(rows))
        vote_rows = rows[:vote_n]
        votes: dict[str, int] = {}
        for _tid, _dur, trace in vote_rows:
            b = self.bottleneck_service(trace)
            if b:
                votes[b] = votes.get(b, 0) + 1

        return {
            "trace_ids": [r[0] for r in rows if r[0]],
            "oracle_trace_ids": [r[0] for r in vote_rows if r[0]],
            "p50_ms": self._percentile(latencies, 50),
            "p95_ms": self._percentile(latencies, 95),
            "sample_latencies_ms": [round(x, 2) for x in latencies[:20]],
            "voted_bottleneck": max(votes, key=votes.get) if votes else None,
        }
