"""Resource bottleneck scoring (CPU, mem, network, disk).

For CPU/mem/disk faults the agent submits the bottleneck resource and service.
For network faults the agent submits the resource plus a from/to service pair
(the starting and ending services on the congested path).

Multi-fault problems (``len(expected_faults) > 1``) are graded by exact set
match. Single-fault submissions keep the legacy flat schema (or a one-element
``faults`` list) and alias-aware matching.
"""

from __future__ import annotations

from cloudperfeval.evaluators.bottleneck import (
    GroundTruth,
    normalize_resource,
    normalize_service,
)
from cloudperfeval.evaluators.faults import eval_faults_set, parse_submitted_faults


def _accepted_service_names(*names: str | None, aliases: list[str] | None = None) -> set[str]:
    values = [n for n in names if n]
    if aliases:
        values.extend(aliases)
    return {normalize_service(n) for n in values if n}


def _eval_single_resource(soln: dict, gt: GroundTruth) -> dict:
    """Grade a single resource-diagnosis object against primary ground truth."""
    predicted_resource = normalize_resource(
        soln.get("resource") or soln.get("bottleneck_resource")
    )
    expected_resource = normalize_resource(gt.bottleneck_resource or "")
    resource_exact = bool(predicted_resource and predicted_resource == expected_resource)

    if expected_resource == "network":
        from_svc = (
            soln.get("from_service")
            or soln.get("source_service")
            or soln.get("starting_service")
        )
        to_svc = (
            soln.get("to_service")
            or soln.get("destination_service")
            or soln.get("ending_service")
        )
        expected_from = gt.network_from_service
        expected_to = gt.network_to_service
        from_exact = (
            bool(from_svc)
            and normalize_service(from_svc)
            in _accepted_service_names(expected_from, aliases=gt.network_from_aliases)
        )
        to_exact = (
            bool(to_svc)
            and normalize_service(to_svc)
            in _accepted_service_names(expected_to, aliases=gt.network_to_aliases)
        )
        service_exact = from_exact and to_exact
        success = resource_exact and service_exact
        return {
            "success": success,
            "resource_exact": resource_exact,
            "service_exact": service_exact,
            "from_service_exact": from_exact,
            "to_service_exact": to_exact,
            "predicted_resource": predicted_resource or None,
            "expected_resource": expected_resource or None,
            "predicted_service": None,
            "expected_service": gt.bottleneck_service,
            "predicted_from_service": from_svc,
            "expected_from_service": expected_from,
            "predicted_to_service": to_svc,
            "expected_to_service": expected_to,
        }

    predicted_service = (
        soln.get("service")
        or soln.get("root_cause_service")
        or soln.get("bottleneck_service")
    )
    service_exact = (
        bool(predicted_service)
        and normalize_service(predicted_service)
        in _accepted_service_names(gt.bottleneck_service, aliases=gt.aliases)
    )
    success = resource_exact and service_exact
    return {
        "success": success,
        "resource_exact": resource_exact,
        "service_exact": service_exact,
        "predicted_resource": predicted_resource or None,
        "expected_resource": expected_resource or None,
        "predicted_service": predicted_service,
        "expected_service": gt.bottleneck_service,
    }


def eval_resource_diagnosis(soln, gt: GroundTruth) -> dict:
    """Grade a resource-diagnosis submission against ground truth."""
    if len(gt.expected_faults) > 1:
        return eval_faults_set(soln, gt)

    if not isinstance(soln, dict):
        return {
            "success": False,
            "resource_exact": False,
            "service_exact": False,
            "predicted_resource": None,
            "expected_resource": gt.bottleneck_resource,
            "error": "invalid_submission",
        }

    faults = parse_submitted_faults(soln)
    if faults is not None and "faults" in soln:
        if len(faults) == 1:
            return _eval_single_resource(faults[0], gt)
        # Wrong cardinality for a single-fault problem — still score as set match
        # when expected_faults is available.
        if gt.expected_faults:
            return eval_faults_set(soln, gt)
        return {
            "success": False,
            "resource_exact": False,
            "service_exact": False,
            "predicted_resource": None,
            "expected_resource": gt.bottleneck_resource,
            "error": "expected_single_fault",
        }

    return _eval_single_resource(soln, gt)
