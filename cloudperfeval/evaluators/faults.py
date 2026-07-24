"""Multi-fault submission parsing and set-match grading.

The agent reports every injected fault. Success requires the predicted set to
equal the expected set (order irrelevant; ``reason`` is ignored).
"""

from __future__ import annotations

from typing import Any

from cloudperfeval.evaluators.bottleneck import (
    GroundTruth,
    normalize_resource,
    normalize_service,
)


def parse_submitted_faults(soln: Any) -> list[dict] | None:
    """Normalize a submission into a list of fault dicts.

    Accepts ``{"faults": [...]}`` or a single fault object (backward compat).
    """
    if not isinstance(soln, dict):
        return None
    if "faults" in soln:
        faults = soln["faults"]
        if not isinstance(faults, list):
            return None
        return [f for f in faults if isinstance(f, dict)]
    return [soln]


def fault_identity(fault: dict) -> tuple | None:
    """Canonical identity for set membership (resource + location)."""
    resource = normalize_resource(
        fault.get("resource") or fault.get("bottleneck_resource") or ""
    )
    if not resource:
        # Service-diagnosis style entry without an explicit resource.
        service = (
            fault.get("service")
            or fault.get("root_cause_service")
            or fault.get("bottleneck_service")
        )
        from_svc = (
            fault.get("from_service")
            or fault.get("source_service")
            or fault.get("starting_service")
        )
        to_svc = (
            fault.get("to_service")
            or fault.get("destination_service")
            or fault.get("ending_service")
        )
        if from_svc or to_svc:
            return ("network", normalize_service(from_svc), normalize_service(to_svc))
        if service:
            return ("service", normalize_service(service), "")
        return None

    if resource == "network":
        from_svc = (
            fault.get("from_service")
            or fault.get("source_service")
            or fault.get("starting_service")
        )
        to_svc = (
            fault.get("to_service")
            or fault.get("destination_service")
            or fault.get("ending_service")
        )
        if from_svc or to_svc:
            return (
                "network",
                normalize_service(from_svc),
                normalize_service(to_svc),
            )
        service = (
            fault.get("service")
            or fault.get("root_cause_service")
            or fault.get("bottleneck_service")
        )
        if service:
            return ("network", normalize_service(service), "")
        return None

    service = (
        fault.get("service")
        or fault.get("root_cause_service")
        or fault.get("bottleneck_service")
    )
    if not service:
        return None
    return (resource, normalize_service(service), "")


def _fault_set(faults: list[dict]) -> set[tuple] | None:
    keys: set[tuple] = set()
    for fault in faults:
        key = fault_identity(fault)
        if key is None:
            return None
        keys.add(key)
    return keys


def public_fault(fault: dict) -> dict:
    """Strip ungraded fields for result logging."""
    resource = normalize_resource(
        fault.get("resource") or fault.get("bottleneck_resource") or ""
    )
    out: dict[str, str] = {}
    if resource:
        out["resource"] = resource
    elif fault.get("from_service") or fault.get("to_service"):
        out["resource"] = "network"

    if out.get("resource") == "network" or (
        fault.get("from_service") or fault.get("to_service")
    ):
        from_svc = (
            fault.get("from_service")
            or fault.get("source_service")
            or fault.get("starting_service")
        )
        to_svc = (
            fault.get("to_service")
            or fault.get("destination_service")
            or fault.get("ending_service")
        )
        if from_svc:
            out["from_service"] = from_svc
        if to_svc:
            out["to_service"] = to_svc
        if not from_svc and not to_svc:
            service = (
                fault.get("service")
                or fault.get("root_cause_service")
                or fault.get("bottleneck_service")
            )
            if service:
                out["service"] = service
        return out

    service = (
        fault.get("service")
        or fault.get("root_cause_service")
        or fault.get("bottleneck_service")
    )
    if service:
        out["service"] = service
    return out


def eval_faults_set(soln, gt: GroundTruth) -> dict:
    """Exact set-match of submitted faults against ``gt.expected_faults``."""
    expected = list(gt.expected_faults or [])
    predicted_list = parse_submitted_faults(soln)

    if predicted_list is None:
        return {
            "success": False,
            "faults_exact": False,
            "predicted_faults": None,
            "expected_faults": [public_fault(f) for f in expected],
            "error": "invalid_submission",
        }

    predicted_keys = _fault_set(predicted_list)
    expected_keys = _fault_set(expected)
    if predicted_keys is None:
        return {
            "success": False,
            "faults_exact": False,
            "predicted_faults": [public_fault(f) for f in predicted_list],
            "expected_faults": [public_fault(f) for f in expected],
            "error": "incomplete_fault_entry",
        }
    if expected_keys is None:
        return {
            "success": False,
            "faults_exact": False,
            "predicted_faults": [public_fault(f) for f in predicted_list],
            "expected_faults": [public_fault(f) for f in expected],
            "error": "invalid_ground_truth",
        }

    exact = predicted_keys == expected_keys
    missing = sorted(expected_keys - predicted_keys)
    extra = sorted(predicted_keys - expected_keys)
    return {
        "success": exact,
        "faults_exact": exact,
        "predicted_faults": [public_fault(f) for f in predicted_list],
        "expected_faults": [public_fault(f) for f in expected],
        "missing_faults": missing,
        "extra_faults": extra,
        # Convenience scalars for single-fault / dashboards.
        "predicted_service": (
            predicted_list[0].get("service")
            or predicted_list[0].get("root_cause_service")
            if len(predicted_list) == 1
            else None
        ),
        "expected_service": gt.bottleneck_service,
    }
