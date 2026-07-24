"""Unit tests for multi-fault set-match grading."""

from __future__ import annotations

import unittest

from cloudperfeval.evaluators.bottleneck import GroundTruth, eval_with_trace_oracle
from cloudperfeval.evaluators.faults import eval_faults_set, fault_identity
from cloudperfeval.evaluators.resource import eval_resource_diagnosis
from cloudperfeval.observer.traces import JaegerAPI


def _gt(**kwargs) -> GroundTruth:
    defaults = dict(
        bottleneck_service="home-timeline-service",
        fault_type="cpu+delay",
        fault_target="home-timeline-service",
        endpoint="/wrk2-api/home-timeline/read",
        expected_faults=[
            {"resource": "cpu", "service": "home-timeline-service"},
            {
                "resource": "network",
                "from_service": "frontend-service",
                "to_service": "home-timeline-service",
            },
        ],
        fault_targets=["home-timeline-service", "frontend"],
        bottleneck_resource="cpu",
    )
    defaults.update(kwargs)
    return GroundTruth(**defaults)


class FaultIdentityTests(unittest.TestCase):
    def test_cpu_and_network_keys(self):
        self.assertEqual(
            fault_identity({"resource": "cpu", "service": "home-timeline-service"}),
            ("cpu", "home-timeline", ""),
        )
        self.assertEqual(
            fault_identity({
                "resource": "network",
                "from_service": "frontend-service",
                "to_service": "home-timeline-service",
            }),
            ("network", "frontend", "home-timeline"),
        )


class EvalFaultsSetTests(unittest.TestCase):
    def test_exact_set_match_order_irrelevant(self):
        gt = _gt()
        soln = {
            "faults": [
                {
                    "resource": "network",
                    "from_service": "frontend",
                    "to_service": "home-timeline",
                    "reason": "delay",
                },
                {
                    "resource": "cpu",
                    "service": "home-timeline-service",
                    "reason": "hot",
                },
            ]
        }
        result = eval_faults_set(soln, gt)
        self.assertTrue(result["success"])
        self.assertTrue(result["faults_exact"])
        self.assertEqual(result["missing_faults"], [])
        self.assertEqual(result["extra_faults"], [])

    def test_partial_answer_fails(self):
        gt = _gt()
        soln = {
            "faults": [
                {"resource": "cpu", "service": "home-timeline-service", "reason": "x"},
            ]
        }
        result = eval_faults_set(soln, gt)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["missing_faults"]), 1)

    def test_extra_fault_fails(self):
        gt = _gt()
        soln = {
            "faults": [
                {"resource": "cpu", "service": "home-timeline-service"},
                {
                    "resource": "network",
                    "from_service": "frontend-service",
                    "to_service": "home-timeline-service",
                },
                {"resource": "cpu", "service": "post-storage-service"},
            ]
        }
        result = eval_faults_set(soln, gt)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["extra_faults"]), 1)


class ResourceDiagnosisMultiTests(unittest.TestCase):
    def test_multi_uses_set_match(self):
        gt = _gt()
        soln = {
            "faults": [
                {"resource": "cpu", "service": "home-timeline-service"},
                {
                    "resource": "network",
                    "from_service": "frontend-service",
                    "to_service": "home-timeline-service",
                },
            ]
        }
        result = eval_resource_diagnosis(soln, gt)
        self.assertTrue(result["success"])
        self.assertTrue(result["faults_exact"])

    def test_single_legacy_schema_still_works(self):
        gt = GroundTruth(
            bottleneck_service="home-timeline-service",
            fault_type="cpu",
            fault_target="home-timeline-service",
            endpoint="/x",
            bottleneck_resource="cpu",
            expected_faults=[
                {"resource": "cpu", "service": "home-timeline-service"},
            ],
        )
        soln = {
            "resource": "cpu",
            "service": "home-timeline-service",
            "reason": "high cpu",
        }
        result = eval_resource_diagnosis(soln, gt)
        self.assertTrue(result["success"])
        self.assertTrue(result["resource_exact"])
        self.assertTrue(result["service_exact"])


class ServiceDiagnosisMultiTests(unittest.TestCase):
    def test_multi_skips_trace_oracle(self):
        gt = _gt()
        soln = {
            "faults": [
                {"resource": "cpu", "service": "home-timeline-service"},
                {
                    "resource": "network",
                    "from_service": "frontend-service",
                    "to_service": "home-timeline-service",
                },
            ]
        }
        result = eval_with_trace_oracle(soln, gt, JaegerAPI(""))
        self.assertTrue(result["success"])
        self.assertNotIn("trace_oracle_match", result)


class DecoyFaultTests(unittest.TestCase):
    def test_decoy_excluded_from_expected(self):
        from cloudperfeval.fault.pumba import FaultSpec
        from cloudperfeval.problems.base import PerformanceProblem
        from cloudperfeval.tasks.resource_diagnosis import ResourceDiagnosis
        from cloudperfeval.workload.generator import WorkloadResult, WorkloadSpec

        problem = PerformanceProblem(
            problem_id="test-decoy",
            workload=WorkloadSpec(
                mode="sustained",
                endpoint="/x",
                trace_service="frontend",
            ),
            task=ResourceDiagnosis(endpoint="/x"),
            bottleneck_service="home-timeline-service",
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=20),
                FaultSpec(
                    "cpu", "user-timeline-service", cpu_workers=20, decoy=True
                ),
            ],
        )
        self.assertFalse(problem.multi_fault)
        self.assertTrue(problem.has_decoy)
        self.assertEqual(len(problem.graded_faults), 1)
        problem.workload_result = WorkloadResult(
            spec_summary="test",
            p50_ms=1.0,
            p95_ms=2.0,
        )
        problem._build_ground_truth()
        gt = problem.ground_truth
        assert gt is not None
        self.assertEqual(
            gt.expected_faults,
            [{"resource": "cpu", "service": "home-timeline-service"}],
        )
        self.assertEqual(gt.fault_targets, ["home-timeline-service"])
        self.assertEqual(gt.decoy_targets, ["user-timeline-service"])

    def test_reporting_decoy_fails_set_match(self):
        gt = GroundTruth(
            bottleneck_service="home-timeline-service",
            fault_type="cpu",
            fault_target="home-timeline-service",
            endpoint="/x",
            bottleneck_resource="cpu",
            expected_faults=[
                {"resource": "cpu", "service": "home-timeline-service"},
            ],
            decoy_targets=["user-timeline-service"],
        )
        # Reporting the decoy as well should fail (extra fault).
        # But with only 1 expected, resource eval uses single path unless
        # faults list has wrong cardinality — use eval_faults_set directly.
        soln = {
            "faults": [
                {"resource": "cpu", "service": "home-timeline-service"},
                {"resource": "cpu", "service": "user-timeline-service"},
            ]
        }
        result = eval_faults_set(soln, gt)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["extra_faults"]), 1)


if __name__ == "__main__":
    unittest.main()
