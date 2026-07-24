"""PerformanceProblem — composition of fault(s) + workload + task + ground truth.

Lifecycle (driven by the orchestrator):
    setup()    -> recover leftovers, inject fault(s), run workload, build ground truth
    <agent investigates via SwarmActions>
    eval(soln) -> delegate to the task's evaluator (single primary bottleneck)
    teardown() -> recover all faults (always)

Supports one or more concurrent Pumba faults. Single-fault problems grade a
primary bottleneck (service and/or resource). Multi-fault problems require the
agent to report every *graded* fault; grading is an exact set match.

Faults marked ``decoy=True`` are still injected (red herrings) but are omitted
from ground truth — the agent must not report them.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from cloudperfeval.config import config
from cloudperfeval.evaluators.bottleneck import GroundTruth
from cloudperfeval.fault.pumba import FaultSpec, PumbaInjector, faults_summary
from cloudperfeval.observer.traces import JaegerAPI
from cloudperfeval.stored_run import StoredRun
from cloudperfeval.tasks.base import PerformanceTask
from cloudperfeval.workload.generator import (
    WorkloadGenerator,
    WorkloadResult,
    WorkloadSpec,
)

if TYPE_CHECKING:
    from cloudperfeval.suites.base import SuiteSpec


def _fault_type_label(faults: list[FaultSpec]) -> str:
    if not faults:
        return "none"
    types = sorted({f.fault_type for f in faults})
    return types[0] if len(types) == 1 else "+".join(types)


def _resource_from_fault(fault: FaultSpec) -> str:
    # icache thrashing presents as CPU/compute latency; grade as "cpu".
    if fault.fault_type in ("cpu", "icache", "icache_burst"):
        return "cpu"
    if fault.fault_type in ("delay", "connections"):
        return "network"
    raise ValueError(
        f"Cannot derive bottleneck resource from fault type {fault.fault_type!r}"
    )


def _expected_fault_from_spec(fault: FaultSpec) -> dict:
    """Map an injected FaultSpec to a graded fault entry (resource + location)."""
    resource = _resource_from_fault(fault)
    if resource == "network":
        if fault.peer_service:
            return {
                "resource": "network",
                "from_service": fault.target_service,
                "to_service": fault.peer_service,
            }
        return {"resource": "network", "service": fault.target_service}
    return {"resource": resource, "service": fault.target_service}


class PerformanceProblem:
    def __init__(
        self,
        problem_id: str,
        workload: WorkloadSpec,
        task: PerformanceTask,
        bottleneck_service: str,
        *,
        fault: FaultSpec | None = None,
        faults: list[FaultSpec] | None = None,
        bottleneck_aliases: list[str] | None = None,
        bottleneck_resource: str | None = None,
        network_from_service: str | None = None,
        network_to_service: str | None = None,
        network_from_aliases: list[str] | None = None,
        network_to_aliases: list[str] | None = None,
        suite: SuiteSpec | None = None,
        disclose_url: str | None = None,
    ):
        if faults is not None:
            # Empty list is allowed (e.g. deploy-time misconfig already in place).
            self.faults = list(faults)
        elif fault is not None:
            self.faults = [fault]
        else:
            raise ValueError("Provide fault= or faults= (use faults=[] for no inject)")

        self.problem_id = problem_id
        self.workload = workload
        self.task = task
        self.bottleneck_service = bottleneck_service
        self.bottleneck_aliases = bottleneck_aliases or []
        self.bottleneck_resource = bottleneck_resource
        self.network_from_service = network_from_service
        self.network_to_service = network_to_service
        self.network_from_aliases = network_from_aliases or []
        self.network_to_aliases = network_to_aliases or []
        self.suite = suite
        self.disclose_url = disclose_url

        self.injector = PumbaInjector()
        self.loadgen = WorkloadGenerator()
        self.jaeger = JaegerAPI(config.get("jaeger_url", ""))
        self.task.jaeger = self.jaeger

        self.workload_result: WorkloadResult | None = None
        self.ground_truth: GroundTruth | None = None
        self._chaos_ids: list[str] = []

    @property
    def fault(self) -> FaultSpec | None:
        """First graded fault spec (backward compatibility); None if none."""
        graded = self.graded_faults
        if graded:
            return graded[0]
        return self.faults[0] if self.faults else None

    @property
    def graded_faults(self) -> list[FaultSpec]:
        """Faults included in ground truth (excludes ``decoy=True``)."""
        return [f for f in self.faults if not f.decoy]

    @property
    def decoy_faults(self) -> list[FaultSpec]:
        return [f for f in self.faults if f.decoy]

    @property
    def multi_fault(self) -> bool:
        """True when the agent must report more than one graded fault."""
        return len(self.graded_faults) > 1

    @property
    def has_decoy(self) -> bool:
        return any(f.decoy for f in self.faults)

    def faults_summary(self) -> str:
        return faults_summary(self.faults)

    # ---- lifecycle -------------------------------------------------------
    def _build_expected_faults(
        self,
        *,
        bottleneck_resource: str | None,
        network_from: str | None,
        network_to: str | None,
    ) -> list[dict]:
        """Ground-truth fault list: one entry per graded (non-decoy) FaultSpec."""
        graded = self.graded_faults
        expected: list[dict] = []
        for fault in graded:
            entry = _expected_fault_from_spec(fault)
            # Single graded-fault problems may override names via problem kwargs.
            if len(graded) == 1:
                if bottleneck_resource:
                    entry["resource"] = bottleneck_resource
                if entry.get("resource") == "network":
                    if network_from:
                        entry["from_service"] = network_from
                        entry.pop("service", None)
                    if network_to:
                        entry["to_service"] = network_to
                        entry.pop("service", None)
                elif self.bottleneck_service:
                    entry["service"] = self.bottleneck_service
            expected.append(entry)
        if not expected and bottleneck_resource:
            # No inject (e.g. deploy-time misconfig); still grade one expected.
            if bottleneck_resource == "network":
                entry = {"resource": "network"}
                if network_from:
                    entry["from_service"] = network_from
                if network_to:
                    entry["to_service"] = network_to
                if self.bottleneck_service and not network_from:
                    entry["service"] = self.bottleneck_service
                expected.append(entry)
            else:
                expected.append({
                    "resource": bottleneck_resource,
                    "service": self.bottleneck_service,
                })
        return expected

    def _build_ground_truth(self) -> None:
        assert self.workload_result is not None
        graded = self.graded_faults
        fault_targets = [f.target_service for f in graded]
        decoy_targets = [f.target_service for f in self.decoy_faults]
        primary_fault = graded[0] if graded else None
        bottleneck_resource = self.bottleneck_resource
        network_from = self.network_from_service
        network_to = self.network_to_service
        if self.task.task_type == "resource_diagnosis":
            if bottleneck_resource is None:
                if primary_fault is None:
                    raise ValueError(
                        "resource_diagnosis with no faults requires "
                        "bottleneck_resource="
                    )
                bottleneck_resource = _resource_from_fault(primary_fault)
            if bottleneck_resource == "network" and primary_fault is not None:
                network_from = network_from or primary_fault.target_service
                network_to = network_to or primary_fault.peer_service
        elif bottleneck_resource is None and primary_fault is not None:
            bottleneck_resource = _resource_from_fault(primary_fault)
        expected_faults = self._build_expected_faults(
            bottleneck_resource=bottleneck_resource,
            network_from=network_from,
            network_to=network_to,
        )
        self.ground_truth = GroundTruth(
            bottleneck_service=self.bottleneck_service,
            fault_type=_fault_type_label(graded),
            fault_target=fault_targets[0] if fault_targets else "",
            fault_targets=fault_targets,
            decoy_targets=decoy_targets,
            endpoint=self.workload.endpoint,
            reference_trace_ids=self.workload_result.oracle_trace_ids,
            trace_oracle_service=self.workload_result.voted_bottleneck,
            aliases=self.bottleneck_aliases,
            bottleneck_resource=bottleneck_resource,
            network_from_service=network_from,
            network_to_service=network_to,
            network_from_aliases=self.network_from_aliases,
            network_to_aliases=self.network_to_aliases,
            expected_faults=expected_faults,
        )

    def _run_workload(self, *, defer_jaeger: bool = False) -> WorkloadResult:
        return self.loadgen.run(self.workload, defer_jaeger=defer_jaeger)

    def setup(self) -> WorkloadResult:
        """Recover leftovers, inject all faults, generate load, build ground truth."""
        self.injector.recover_all()
        self._chaos_ids = self.injector.inject_all(self.faults)
        self.workload_result = self._run_workload()
        self._build_ground_truth()
        return self.workload_result

    def setup_store(self) -> StoredRun:
        """Inject fault, send load, save snapshot, recover fault; skip Jaeger wait/capture."""
        self.injector.recover_all()
        self._chaos_ids = self.injector.inject_all(self.faults)
        partial = self._run_workload(defer_jaeger=True)
        stored = StoredRun(
            snapshot_id=StoredRun.new_id(self.problem_id),
            problem_id=self.problem_id,
            trace_id=partial.correlation_trace_id,
            spec_summary=partial.spec_summary,
            raw_loadgen_output=partial.raw_loadgen_output,
            recorded_at=time.time(),
            workload_mode=self.workload.mode,
            trace_service=self.workload.trace_service,
            load_start_ts=partial.load_start_ts,
            load_end_ts=partial.load_end_ts,
        )
        path = stored.save()
        print(f"[ENV] Snapshot {stored.snapshot_id!r} at {path}")
        print(f"[ENV] Recovering fault after snapshot phase")
        self.teardown()
        self._chaos_ids = []
        print(
            "[ENV] Wait for Jaeger ingest, then resume with: "
            f"python3 run.py --phase run --snapshot-id {stored.snapshot_id!r} "
            f"--problem-id {self.problem_id!r}"
        )
        return stored

    def setup_from_stored(self, stored: StoredRun) -> WorkloadResult:
        """Complete setup from a prior ``--phase snapshot`` run (Jaeger wait + capture)."""
        self._chaos_ids = []
        self.workload_result = self.loadgen.capture_deferred(
            self.workload,
            stored.raw_loadgen_output,
            stored.trace_id,
            load_start_ts=stored.load_start_ts,
            load_end_ts=stored.load_end_ts,
        )
        self._build_ground_truth()
        return self.workload_result

    def teardown(self) -> None:
        # Reverse order so short-lived overlays (e.g. pumba delay) are cleared
        # before longer-lived fault state (e.g. Swarm config / service restart).
        try:
            self.injector.recover_many(list(reversed(self._chaos_ids)))
        finally:
            self.injector.recover_all()

    # ---- agent-facing contract (delegated to the task) -------------------
    def get_task_description(self) -> str:
        assert self.workload_result is not None, "setup() must run before prompt build"
        return self.task.get_task_description(
            self.workload_result,
            config.get("stack_name", ""),
            multi_fault=self.multi_fault,
            has_decoy=self.has_decoy,
            suite=self.suite,
            workload=self.workload,
            disclose_url=self.disclose_url,
        )

    def get_instructions(self) -> str:
        return self.task.get_instructions()

    # ---- grading ---------------------------------------------------------
    def eval(self, soln, trace: list[dict], duration: float) -> dict:
        assert self.ground_truth is not None and self.workload_result is not None
        return self.task.eval(
            soln, trace, duration,
            ground_truth=self.ground_truth,
            workload_result=self.workload_result,
        )
