"""Bottleneck localization scoring.

Single-fault service diagnosis: exact match of `root_cause_service` against the
ground-truth bottleneck, plus a trace-oracle cross-check (majority vote over
the slowest captured traces).

Multi-fault problems: exact set match of submitted faults against
``GroundTruth.expected_faults`` (see ``evaluators.faults``); the trace oracle
is not used.

Ground truth is never shown to the agent — it lives on the Problem and is only
consumed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cloudperfeval.observer.traces import JaegerAPI


_RESOURCE_ALIASES = {
    "cpu": {"cpu"},
    "mem": {"mem", "memory", "ram"},
    "network": {"network", "net", "networking", "bandwidth"},
    "disk": {"disk", "io", "storage", "disk_io"},
}


@dataclass
class GroundTruth:
    bottleneck_service: str           # primary bottleneck (graded answer)
    fault_type: str                   # "delay" | "cpu" | "delay+cpu" for multi
    fault_target: str                 # primary fault target (backward compat)
    endpoint: str
    reference_trace_ids: list[str] = field(default_factory=list)  # slowest ~20% used by oracle
    trace_oracle_service: str | None = None   # voted_bottleneck from workload capture
    fault_targets: list[str] = field(default_factory=list)  # graded fault targets
    decoy_targets: list[str] = field(default_factory=list)  # injected but not graded
    aliases: list[str] = field(default_factory=list)
    # resource_diagnosis grading (cpu | mem | network | disk)
    bottleneck_resource: str | None = None
    network_from_service: str | None = None
    network_to_service: str | None = None
    network_from_aliases: list[str] = field(default_factory=list)
    network_to_aliases: list[str] = field(default_factory=list)
    # Graded faults for set-match (excludes decoys).
    expected_faults: list[dict] = field(default_factory=list)


def normalize_service(name) -> str:
    """Lower-case, trim, and drop a trailing '-service' for robust matching."""
    if not isinstance(name, str):
        return ""
    n = name.strip().lower()
    for suffix in ("-service", "service", "-svc"):
        if n.endswith(suffix) and len(n) > len(suffix):
            n = n[: -len(suffix)]
            break
    return n.rstrip("-_ ")


def normalize_resource(name) -> str:
    if not isinstance(name, str):
        return ""
    n = name.strip().lower().replace(" ", "_")
    for canonical, aliases in _RESOURCE_ALIASES.items():
        if n == canonical or n in aliases:
            return canonical
    return n


def _accepted_names(gt: GroundTruth) -> set[str]:
    names = {gt.bottleneck_service, *gt.aliases}
    return {normalize_service(n) for n in names if n}


def eval_localization(soln, gt: GroundTruth) -> dict:
    """Exact-match the agent's predicted service against ground truth."""
    if isinstance(soln, dict):
        if isinstance(soln.get("faults"), list) and soln["faults"]:
            first = soln["faults"][0] if isinstance(soln["faults"][0], dict) else {}
            predicted = (
                first.get("root_cause_service")
                or first.get("service")
                or first.get("bottleneck_service")
            )
        else:
            predicted = soln.get("root_cause_service") or soln.get("bottleneck_service")
    elif isinstance(soln, str):
        predicted = soln
    else:
        predicted = None

    if not predicted:
        return {
            "success": False,
            "localization_exact": False,
            "predicted_service": None,
            "expected_service": gt.bottleneck_service,
            "error": "no_service_in_submission",
        }

    exact = normalize_service(predicted) in _accepted_names(gt)
    return {
        "localization_exact": exact,
        "predicted_service": predicted,
        "expected_service": gt.bottleneck_service,
        "success": exact,
    }


def bottleneck_from_trace(jaeger: JaegerAPI, trace_id: str) -> str | None:
    traces = jaeger.get_trace_by_id(trace_id)
    if not traces:
        return None
    return jaeger.bottleneck_service(traces[0])


def eval_with_trace_oracle(soln, gt: GroundTruth, jaeger: JaegerAPI) -> dict:
    """Grade service diagnosis; multi-fault uses set match (no trace oracle)."""
    if len(gt.expected_faults) > 1:
        from cloudperfeval.evaluators.faults import eval_faults_set

        result = eval_faults_set(soln, gt)
        if gt.fault_targets:
            result["fault_targets"] = gt.fault_targets
        return result

    result = eval_localization(soln, gt)

    oracle_service = gt.trace_oracle_service
    if oracle_service is None and gt.reference_trace_ids:
        oracle_service = bottleneck_from_trace(jaeger, gt.reference_trace_ids[0])

    predicted = result.get("predicted_service")
    trace_match = bool(
        oracle_service
        and predicted
        and normalize_service(predicted) == normalize_service(oracle_service)
    )

    result["trace_oracle_service"] = oracle_service
    result["trace_oracle_match"] = trace_match
    result["success"] = bool(result.get("localization_exact")) or trace_match
    if gt.fault_targets:
        result["fault_targets"] = gt.fault_targets
    return result

