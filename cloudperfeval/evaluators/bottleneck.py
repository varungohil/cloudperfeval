"""Bottleneck localization scoring.

The primary score is an exact match of the agent's `root_cause_service` against
the ground-truth bottleneck. As a cross-check we also run a programmatic
trace oracle (largest exclusive span time in the reference trace) so a run can
pass if the agent agrees with the observed data even when ground-truth naming
differs slightly.

Ground truth is never shown to the agent — it lives on the Problem and is only
consumed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cloudperfeval.observer.traces import JaegerAPI


@dataclass
class GroundTruth:
    bottleneck_service: str           # primary bottleneck (graded answer)
    fault_type: str                   # "delay" | "cpu" | "delay+cpu" for multi
    fault_target: str                 # primary fault target (backward compat)
    endpoint: str
    reference_trace_ids: list[str] = field(default_factory=list)
    fault_targets: list[str] = field(default_factory=list)  # all injected services
    aliases: list[str] = field(default_factory=list)


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


def _accepted_names(gt: GroundTruth) -> set[str]:
    names = {gt.bottleneck_service, *gt.aliases}
    return {normalize_service(n) for n in names if n}


def eval_localization(soln, gt: GroundTruth) -> dict:
    """Exact-match the agent's predicted service against ground truth."""
    if isinstance(soln, dict):
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
    """Exact match plus a trace-oracle cross-check; success if either agrees."""
    result = eval_localization(soln, gt)

    oracle_service = None
    if gt.reference_trace_ids:
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
