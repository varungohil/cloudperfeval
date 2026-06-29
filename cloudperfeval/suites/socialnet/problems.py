"""Problem definitions for the socialnet suite."""

from __future__ import annotations

from typing import Callable

from cloudperfeval.fault.pumba import FaultSpec
from cloudperfeval.problems.base import PerformanceProblem
from cloudperfeval.suites.base import SuiteSpec
from cloudperfeval.suites.socialnet import workloads as wl
from cloudperfeval.tasks.endpoint_diagnosis import EndpointDiagnosisTask
from cloudperfeval.tasks.trace_localization import TraceLocalizationTask


def build_problems(suite: SuiteSpec) -> dict[str, Callable[[], PerformanceProblem]]:
    pid = suite.namespaced_id

    return {
        pid("compose_post_delay-trace-1"): lambda: PerformanceProblem(
            problem_id=pid("compose_post_delay-trace-1"),
            suite=suite,
            fault=FaultSpec("delay", "compose-post-service", delay_ms=500, jitter_ms=50),
            workload=wl.single(wl.COMPOSE_POST),
            task=TraceLocalizationTask(),
            bottleneck_service="compose-post-service",
        ),
        pid("compose_post_delay-open-1"): lambda: PerformanceProblem(
            problem_id=pid("compose_post_delay-open-1"),
            suite=suite,
            fault=FaultSpec("delay", "compose-post-service", delay_ms=500, jitter_ms=50),
            workload=wl.sustained(wl.COMPOSE_POST),
            task=EndpointDiagnosisTask(
                endpoint=wl.COMPOSE_POST["endpoint"], baseline_p95_ms=50
            ),
            bottleneck_service="compose-post-service",
        ),
        pid("post_storage_delay-trace-1"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_delay-trace-1"),
            suite=suite,
            fault=FaultSpec("delay", "post-storage-service", delay_ms=300, jitter_ms=30),
            workload=wl.single(wl.READ_HOME_TIMELINE),
            task=TraceLocalizationTask(),
            bottleneck_service="post-storage-service",
        ),
        pid("home_timeline_post_storage_delay-trace-1"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_post_storage_delay-trace-1"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "home-timeline-service",
                peer_service="post-storage-service",
                delay_ms=50,
                jitter_ms=1,
            ),
            workload=wl.single(wl.READ_HOME_TIMELINE),
            task=TraceLocalizationTask(),
            bottleneck_service="post-storage-service",
            bottleneck_aliases=["home-timeline-service"],
        ),
        pid("home_timeline_post_storage_delay-open-1"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_post_storage_delay-open-1"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "home-timeline-service",
                peer_service="post-storage-service",
                delay_ms=50,
                jitter_ms=1,
            ),
            workload=wl.sustained(wl.READ_HOME_TIMELINE),
            task=EndpointDiagnosisTask(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=40
            ),
            bottleneck_service="post-storage-service",
            bottleneck_aliases=["home-timeline-service"],
        ),
        pid("home_timeline_cpu-open-1"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_cpu-open-1"),
            suite=suite,
            fault=FaultSpec("cpu", "home-timeline-service", cpu_workers=32),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=500, duration=60, threads=100),
            task=EndpointDiagnosisTask(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=7
            ),
            bottleneck_service="home-timeline-service",
        ),
        pid("post_storage_cpu-open-1"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_cpu-open-1"),
            suite=suite,
            fault=FaultSpec("cpu", "post-storage-service", cpu_workers=25),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=500, duration=60, threads=100),
            task=EndpointDiagnosisTask(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=12
            ),
            bottleneck_service="post-storage-service",
        ),
        pid("frontend_cpu-open-1"): lambda: PerformanceProblem(
            problem_id=pid("frontend_cpu-open-1"),
            suite=suite,
            fault=FaultSpec("cpu", "frontend-service", cpu_workers=32),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=500, duration=60, threads=100),
            task=EndpointDiagnosisTask(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=120
            ),
            bottleneck_service="frontend-service",
        ),
        pid("home_timeline_cpu-trace-1"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_cpu-trace-1"),
            suite=suite,
            fault=FaultSpec("cpu", "home-timeline-service", cpu_workers=20),
            workload=wl.single(wl.READ_HOME_TIMELINE),
            task=TraceLocalizationTask(),
            bottleneck_service="home-timeline-service",
        ),
        
        pid("social_graph_cpu-open-1"): lambda: PerformanceProblem(
            problem_id=pid("social_graph_cpu-open-1"),
            suite=suite,
            fault=FaultSpec("cpu", "social-graph-service", cpu_workers=2),
            workload=wl.sustained(wl.READ_USER_TIMELINE),
            task=EndpointDiagnosisTask(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=45
            ),
            bottleneck_service="social-graph-service",
        ),
        pid("compose_multi_fault-trace-1"): lambda: PerformanceProblem(
            problem_id=pid("compose_multi_fault-trace-1"),
            suite=suite,
            faults=[
                FaultSpec("delay", "compose-post-service", delay_ms=800, jitter_ms=50),
                FaultSpec("delay", "post-storage-service", delay_ms=50, jitter_ms=10),
                FaultSpec("cpu", "social-graph-service", cpu_workers=2),
            ],
            workload=wl.single(wl.COMPOSE_POST),
            task=TraceLocalizationTask(),
            bottleneck_service="compose-post-service",
        ),
        pid("compose_multi_fault-open-1"): lambda: PerformanceProblem(
            problem_id=pid("compose_multi_fault-open-1"),
            suite=suite,
            faults=[
                FaultSpec("delay", "compose-post-service", delay_ms=800, jitter_ms=50),
                FaultSpec("delay", "post-storage-service", delay_ms=50, jitter_ms=10),
                FaultSpec("cpu", "social-graph-service", cpu_workers=2),
            ],
            workload=wl.sustained(wl.COMPOSE_POST),
            task=EndpointDiagnosisTask(
                endpoint=wl.COMPOSE_POST["endpoint"], baseline_p95_ms=50
            ),
            bottleneck_service="compose-post-service",
        ),
    }
