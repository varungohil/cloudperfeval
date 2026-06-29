"""Read-only observability APIs the agent invokes against the environment.

The agent emits one call per turn (e.g. `get_traces("frontend-service")`); the
orchestrator parses it and dispatches to the matching method here. Investigation
is read-only: commands that mutate Swarm/stack state are blocked so the agent
can only observe and diagnose.
"""

from __future__ import annotations

import json
import re

from cloudperfeval.app_source import AppSourceReader
from cloudperfeval.config import config
from cloudperfeval.observer.metrics import PrometheusAPI
from cloudperfeval.observer.traces import JaegerAPI
from cloudperfeval.shell import Shell
from cloudperfeval.status import SubmissionStatus
from cloudperfeval.swarm import SwarmCtl

INTERACTIVE_BLOCK_LIST: dict[str, str] = {
    "docker service logs -f": "Error: Cannot follow logs (-f). Use get_logs() or `--tail`.",
    "docker attach": "Error: `docker attach` is interactive and not supported.",
    "-it": "Error: Interactive TTY flags (-it) are not supported.",
}

STATE_MODIFY_ERROR = (
    "Error: Commands that modify Swarm or stack state are not allowed "
    "(scale, deploy, update, remove, etc). Use read-only inspection only."
)
_STATE_MODIFY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"docker\s+service\s+(scale|update|create|rm|remove|rollback)\b",
        r"docker\s+stack\s+(deploy|rm|remove)\b",
        r"docker\s+node\s+(update|rm|remove|promote|demote)\b",
        r"docker\s+swarm\s+(init|leave|join|update)\b",
        r"docker\s+(rm|stop|kill|pause|unpause|restart|prune)\b",
        r"docker\s+container\s+(run|create|rm|remove|stop|kill|update|prune)\b",
        r"docker\s+network\s+(create|rm|remove|prune|disconnect)\b",
        r"docker\s+volume\s+(create|rm|remove|prune)\b",
        r"docker\s+(secret|config)\s+(create|rm|remove)\b",
        r"docker\s+system\s+prune\b",
        r"pumba\b",
    ]
]


def _blocked_shell_command(command: str) -> str | None:
    for pattern, error in INTERACTIVE_BLOCK_LIST.items():
        if pattern in command:
            return error
    for pattern in _STATE_MODIFY_PATTERNS:
        if pattern.search(command):
            return STATE_MODIFY_ERROR
    return None


def action(method):
    method.is_action = True
    return method


def read(method):
    method.is_action = True
    method.action_type = "read"
    return method


class SwarmActions:
    """Concrete implementations of the agent-facing APIs."""

    def __init__(self):
        self.swarm = SwarmCtl()
        self.prom = PrometheusAPI(config.get("prometheus_url"))
        self.jaeger = JaegerAPI(config.get("jaeger_url"))
        self.source = AppSourceReader()

    # ---- service / node state -------------------------------------------
    @read
    def list_services(self) -> str:
        """List all services in the Swarm stack with replica counts and images."""
        return self.swarm.list_services()

    @read
    def get_service_status(self, service: str) -> str:
        """Show a service's tasks: state, node placement, and any error.

        Args:
            service (str): Short service name, e.g. "compose-post-service".
        """
        return self.swarm.service_ps(service)

    @read
    def get_service_config(self, service: str) -> str:
        """Inspect a service's config (image, replicas, limits, placement).

        Args:
            service (str): Short service name.
        """
        return self.swarm.service_inspect(service)

    @read
    def list_nodes(self) -> str:
        """List Swarm nodes and their availability/status."""
        return self.swarm.nodes()

    @read
    def get_service_node_mapping(self) -> str:
        """Show which Swarm node each service in the stack runs on."""
        return self.swarm.service_node_mapping()

    # ---- logs ------------------------------------------------------------
    @read
    def get_logs(self, service: str, tail: int = 200) -> str:
        """Collect recent logs for a service across its tasks.

        Args:
            service (str): Short service name.
            tail (int): Number of trailing log lines (default 200).
        """
        return self.swarm.service_logs(service, tail=tail)

    # ---- metrics ---------------------------------------------------------

    @read
    def get_metrics_range(
        self,
        start_ts: float | None = None,
        end_ts: float | None = None,
        minutes: int = 10,
        step: int = 15,
        node: str | None = None,
    ) -> str:
        """Summarize the major host/node metrics over a time window.

        Reports CPU util %, memory used %, load1, network rx/tx bytes/s, and disk
        I/O time fraction per node, each as min/avg/max/last over the window.
        Provide epoch-second start_ts/end_ts to target a past interval (e.g. when
        the workload ran), or omit them to look back `minutes` from now. Pass
        `node` (e.g. "node-4") to restrict the output to a single node.

        Args:
            start_ts (float): Window start, epoch seconds (optional).
            end_ts (float): Window end, epoch seconds (optional).
            minutes (int): If start/end omitted, look back this many minutes (default 10).
            step (int): Sample resolution in seconds (default 15).
            node (str): Restrict to this node, e.g. "node-4" (optional; default all nodes).
        """
        return self.prom.range_snapshot(
            start_ts=start_ts, end_ts=end_ts, minutes=minutes, step=step, node=node
        )

    @read
    def query_metric_range(
        self,
        promql: str,
        start_ts: float | None = None,
        end_ts: float | None = None,
        minutes: int = 10,
        step: int = 15,
        node: str | None = None,
    ) -> str:
        """Query Prometheus over a time range (historical data), summarized per series.

        Provide epoch-second start_ts/end_ts to inspect a past window (e.g. the
        interval when the workload ran), or omit them to look back `minutes` from
        now. Each series is summarized as min/avg/max/last over the window. Pass
        `node` (e.g. "node-4") to keep only series for that node; the query must
        preserve the `node` label (e.g. aggregate with `by (node)`).

        Args:
            promql (str): A PromQL expression, e.g. "rate(node_cpu_seconds_total[1m])".
            start_ts (float): Window start, epoch seconds (optional).
            end_ts (float): Window end, epoch seconds (optional).
            minutes (int): If start/end omitted, look back this many minutes (default 10).
            step (int): Sample resolution in seconds (default 15).
            node (str): Keep only series for this node, e.g. "node-4" (optional).
        """
        data = self.prom.query_range_window(
            promql, start_ts=start_ts, end_ts=end_ts, minutes=minutes, step=step
        )
        return self.prom.format_range(data, node=node)

    # ---- traces ----------------------------------------------------------
    @read
    def list_trace_services(self) -> str:
        """List services known to Jaeger (services emitting traces)."""
        services = self.jaeger.get_services()
        return "\n".join(services) if services else "(no trace services found)"

    @read
    def get_traces(self, service: str, duration: int = 5, limit: int = 100) -> str:
        """Summarize per-operation span latency and exclusive self-time (p50/p95/p99 ms, errors).

        Span duration (P*_ms) is inclusive of child spans. Self time (SELF_P*_ms) is
        duration minus direct children, computed per span within each trace.

        Args:
            service (str): Trace service name (see list_trace_services()).
            duration (int): Lookback window in minutes (default 5).
            limit (int): Max traces to fetch (default 100).
        """
        return self.jaeger.summarize(service, minutes=duration, limit=limit)

    @read
    def list_trace_operations(self, service: str) -> str:
        """List operation names recorded in Jaeger for a trace service.

        Args:
            service (str): Trace service name.
        """
        operations = self.jaeger.get_operations(service)
        if not operations:
            return f"(no operations found for service '{service}')"
        return "\n".join(operations)

    @read
    def get_slow_traces(
        self,
        service: str,
        min_latency_ms: float,
        duration: int = 5,
        limit: int = 100,
    ) -> str:
        """Fetch raw Jaeger traces whose end-to-end latency exceeds min_latency_ms.

        Args:
            service (str): Trace service name.
            min_latency_ms (float): Minimum end-to-end latency in milliseconds.
            duration (int): Lookback window in minutes (default 5).
            limit (int): Max traces to fetch from Jaeger before filtering (default 100).
        """
        traces = self.jaeger.traces_above_latency(
            service,
            min_latency_ms=min_latency_ms,
            minutes=duration,
            limit=limit,
        )
        return self.jaeger.format_raw_traces(
            traces,
            f"for service '{service}' in the last {duration}m "
            f"with e2e latency >= {min_latency_ms:g}ms",
        )

    @read
    def get_trace_by_id(self, trace_id: str) -> str:
        """Fetch a single trace by its Jaeger trace ID.

        Args:
            trace_id (str): The trace ID.
        """
        traces = self.jaeger.get_trace_by_id(trace_id)
        return self.jaeger.format_raw_traces(traces, f"for trace id '{trace_id}'")

    @read
    def get_dependency_graph(self, duration: int = 30) -> str:
        """Fetch the Jaeger service dependency graph (caller/callee edges).

        Args:
            duration (int): Lookback window in minutes (default 30).
        """
        graph = self.jaeger.get_dependency_graph(minutes=duration)
        if not graph:
            return f"(no dependency data found in the last {duration}m)"
        return json.dumps(graph, indent=2)

    # ---- application source ----------------------------------------------
    @read
    def list_source(self, path: str = "") -> str:
        """List files and directories in the application source tree.

        Paths are relative to apps/<suite>/source for the active problem's suite
        (e.g. "src/HomeTimelineService" for socialnet).

        Args:
            path (str): Directory path relative to the source root (default: root).
        """
        return self.source.list_dir(path)

    @read
    def read_source(
        self,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> str:
        """Read a UTF-8 source file from the application source tree.

        Args:
            path (str): File path relative to the source root, e.g.
                "src/HomeTimelineService/HomeTimelineHandler.h".
            start_line (int): First line to return, 1-based (default 1).
            end_line (int): Last line to return, inclusive (default: up to 500 lines).
        """
        return self.source.read_file(path, start_line=start_line, end_line=end_line)

    # ---- shell -----------------------------------------------------------
    @action
    def exec_shell(self, command: str, timeout: int = 30) -> str:
        """Run a read-only (non-interactive) shell command on the Swarm manager.

        You cannot scale, deploy, update, or remove services/nodes/stacks, and
        you cannot run fault-injection tools.

        Args:
            command (str): The command to run.
            timeout (int): Timeout in seconds (default 30).
        """
        blocked = _blocked_shell_command(command)
        if blocked:
            return blocked
        return Shell.exec(command, timeout=timeout)

    # ---- submit ----------------------------------------------------------
    @action
    def submit(self, solution) -> SubmissionStatus:
        """Submit your final diagnosis for evaluation.

        Args:
            solution: A dict, e.g.
                {"root_cause_service": "compose-post-service", "reason": "..."}.
        """
        return SubmissionStatus.VALID_SUBMISSION


def get_actions_doc() -> dict[str, str]:
    """Return {action_name: docstring} for every action on SwarmActions."""
    actions = {}
    for name in dir(SwarmActions):
        attr = getattr(SwarmActions, name)
        if callable(attr) and getattr(attr, "is_action", False):
            actions[name] = (attr.__doc__ or "").strip()
    return actions
