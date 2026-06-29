"""Prometheus access over HTTP.

The Swarm stack publishes Prometheus on a host port. The agent queries it only
for *historical* (range) data over a time window via ``query_range_window``.
"""

from __future__ import annotations

from datetime import datetime

import requests

def _node_short(node) -> str:
    """Normalize a node reference (short name or FQDN) to its short label form."""
    return str(node).split(".")[0]


def major_range_queries(node: str | None = None):
    """Major host/node metrics, summarized over a window by get_metrics_range().

    Rates use a [1m] window; grouped by `node` to keep cardinality manageable.
    When ``node`` is given, every selector is scoped to ``node="<short>"`` so the
    result contains that node only.
    """
    # `sel` is appended inside an existing label set (e.g. {mode='idle'}); `bare`
    # is a standalone label set for metrics that otherwise have none.
    if node:
        short = _node_short(node)
        sel = f',node="{short}"'
        bare = f'{{node="{short}"}}'
    else:
        sel = ""
        bare = "{}"
    return [
        ("cpu_util_pct",
         f"100 * (1 - avg by (node)(rate(node_cpu_seconds_total{{mode='idle'{sel}}}[1m])))"),
        ("mem_used_pct",
         f"100 * (1 - avg by (node)(node_memory_MemAvailable_bytes{bare} "
         f"/ node_memory_MemTotal_bytes{bare}))"),
        ("load1", f"avg by (node)(node_load1{bare})"),
        ("net_rx_bytes_per_sec",
         f"sum by (node)(rate(node_network_receive_bytes_total{bare}[1m]))"),
        ("net_tx_bytes_per_sec",
         f"sum by (node)(rate(node_network_transmit_bytes_total{bare}[1m]))"),
        ("disk_io_time_frac",
         f"sum by (node)(rate(node_disk_io_time_seconds_total{bare}[1m]))"),
    ]


class PrometheusAPI:
    def __init__(self, url: str):
        self.url = (url or "").rstrip("/")

    def query_range_window(
        self,
        promql: str,
        start_ts: float | None = None,
        end_ts: float | None = None,
        minutes: int = 10,
        step: int = 15,
    ) -> dict:
        """Range query over an absolute window, or the last ``minutes`` if omitted."""
        end = end_ts if end_ts is not None else datetime.now().timestamp()
        start = start_ts if start_ts is not None else end - minutes * 60
        if start >= end:
            return {"error": "start_ts must be before end_ts"}
        return self._query_range(promql, start, end, step)

    def _query_range(self, promql: str, start: float, end: float, step: int) -> dict:
        try:
            resp = requests.get(
                f"{self.url}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start,
                    "end": end,
                    "step": max(1, int(step)),
                },
                timeout=60,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") != "success":
                return {"error": payload.get("error", "query failed")}
            return payload["data"]
        except requests.RequestException as e:
            return {"error": f"Prometheus request failed: {e}"}

    def range_snapshot(
        self,
        start_ts: float | None = None,
        end_ts: float | None = None,
        minutes: int = 10,
        step: int = 15,
        node: str | None = None,
        queries=None,
    ) -> str:
        """Summarize the major host metrics over a window (one block per metric).

        When ``node`` is given, queries are scoped to that node only.
        """
        queries = queries or major_range_queries(node)
        blocks = []
        for label, promql in queries:
            data = self.query_range_window(
                promql, start_ts=start_ts, end_ts=end_ts, minutes=minutes, step=step
            )
            blocks.append(f"### {label}\n{self.format_range(data)}")
        return "\n\n".join(blocks)

    @staticmethod
    def format_range(data: dict, node: str | None = None) -> str:
        """Summarize matrix (range) results per series: min/avg/max/last + samples.

        When ``node`` is given, only series carrying a matching ``node`` label are
        kept (the query must preserve that label, e.g. aggregate ``by (node)``).
        """
        if "error" in data:
            return f"error: {data['error']}"
        results = data.get("result", [])
        if node:
            short = _node_short(node)
            results = [
                s for s in results
                if _node_short(s.get("metric", {}).get("node", "")) == short
            ]
            if not results:
                return f"(no data for node {short}; ensure the query keeps the `node` label)"
        if not results:
            return "(no data)"
        lines = ["SERIES\tMIN\tAVG\tMAX\tLAST\tSAMPLES"]
        for series in results:
            metric = series.get("metric", {})
            labels = ", ".join(f"{k}={v}" for k, v in metric.items() if k != "__name__")
            values = []
            for _ts, raw in series.get("values", []):
                try:
                    values.append(float(raw))
                except (TypeError, ValueError):
                    continue
            if not values:
                lines.append(f"{labels or '(no labels)'}\t-\t-\t-\t-\t0")
                continue
            avg = sum(values) / len(values)
            lines.append(
                f"{labels or '(no labels)'}\t"
                f"{min(values):.3f}\t{avg:.3f}\t{max(values):.3f}\t"
                f"{values[-1]:.3f}\t{len(values)}"
            )
        return "\n".join(lines)
