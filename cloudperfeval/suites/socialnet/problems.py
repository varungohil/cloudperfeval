"""Problem definitions for the socialnet suite."""

from __future__ import annotations

from typing import Callable

from cloudperfeval.fault.pumba import FaultSpec
from cloudperfeval.problems.base import PerformanceProblem
from cloudperfeval.suites.base import SuiteSpec
from cloudperfeval.suites.socialnet import workloads as wl
from cloudperfeval.tasks.resource_diagnosis import ResourceDiagnosis
from cloudperfeval.tasks.service_diagnosis import ServiceDiagnosis


def build_problems(suite: SuiteSpec) -> dict[str, Callable[[], PerformanceProblem]]:
    def pid(name: str) -> str:
        """Namespaced problem id; ``name`` is also the result/log file prefix."""
        return suite.namespaced_id(name)

    return {
pid("home_timeline_cpu-resource"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_cpu-resource-1"),
            suite=suite,
            fault=FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=100, duration=60, threads=100),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=7
            ),
            bottleneck_service="home-timeline-service",
        ),
pid("post_storage_cpu-resource"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_cpu-resource-1"),
            suite=suite,
            fault=FaultSpec("cpu", "post-storage-service", cpu_workers=22),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=500, duration=60, threads=100),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="post-storage-service",
        ),
pid("frontend_cpu-resource"): lambda: PerformanceProblem(
            problem_id=pid("frontend_cpu-resource-1"),
            suite=suite,
            fault=FaultSpec("cpu", "frontend", cpu_workers=32),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=500, duration=60, threads=100),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="frontend-service",
        ),
pid("user_timeline_cpu-resource-1"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_cpu-resource-1"),
            suite=suite,
            fault=FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
            workload=wl.sustained(wl.READ_USER_TIMELINE, rate=1000, connections=100, duration=60, threads=100),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-service",
        ),
pid("frontend_read_user_timeline_cpu-resource-1"): lambda: PerformanceProblem(
            problem_id=pid("frontend_read_user_timeline_cpu-resource-1"),
            suite=suite,
            fault=FaultSpec("cpu", "frontend", cpu_workers=32),
            workload=wl.sustained(wl.READ_USER_TIMELINE, rate=1000, connections=500, duration=60, threads=100),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="frontend-service",
        ),
pid("frontend_to_home_timeline_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("frontend_to_home_timeline_delay_sustainedreq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "frontend",
                peer_service="home-timeline-service",
                delay_ms=20,
                jitter_ms=5,
                ingress_port=9090,
            ),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-service",
            bottleneck_aliases=["frontend-service"],
            network_from_service="frontend-service",
            network_to_service="home-timeline-service",
            network_from_aliases=["frontend"],
        ),
pid("frontend_to_home_timeline_delay_singlereq"): lambda: PerformanceProblem(
            problem_id=pid("frontend_to_home_timeline_delay_singlereq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "frontend",
                peer_service="home-timeline-service",
                delay_ms=50,
                jitter_ms=1,
                ingress_port=9090,
            ),
            workload=wl.single(wl.READ_HOME_TIMELINE),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-service",
            bottleneck_aliases=["frontend-service"],
            network_from_service="frontend-service",
            network_to_service="home-timeline-service",
            network_from_aliases=["frontend"],
        ),
pid("home_timeline_to_post_storage_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_to_post_storage_delay_sustainedreq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "home-timeline-service",
                peer_service="post-storage-service",
                delay_ms=10,
                jitter_ms=1,
                ingress_port=9090,
            ),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=10
            ),
            bottleneck_service="post-storage-service",
            bottleneck_aliases=["home-timeline-service"],
        ),
pid("home_timeline_to_post_storage_delay_singlereq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_to_post_storage_delay_singlereq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "home-timeline-service",
                peer_service="post-storage-service",
                delay_ms=50,
                jitter_ms=1,
                ingress_port=9090,
            ),
            workload=wl.single(wl.READ_HOME_TIMELINE),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="post-storage-service",
            bottleneck_aliases=["home-timeline-service"],
            network_from_service="home-timeline-service",
            network_to_service="post-storage-service",
        ),
pid("post_storage_to_memcached_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_to_memcached_delay_sustainedreq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "post-storage-service",
                peer_service="post-storage-memcached",
                delay_ms=5,
                jitter_ms=1,
                ingress_port=11211,
            ),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="post-storage-service",
            network_from_service="post-storage-service",
            network_to_service="post-storage-memcached",
        ),
pid("post_storage_to_memcached_delay_singlereq"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_to_memcached_delay_singlereq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "post-storage-service",
                peer_service="post-storage-memcached",
                delay_ms=5,
                jitter_ms=1,
                ingress_port=11211,
            ),
            workload=wl.single(wl.READ_HOME_TIMELINE),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="post-storage-service",
            network_from_service="post-storage-service",
            network_to_service="post-storage-memcached",
        ),
pid("home_timeline_to_redis_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_to_redis_delay_sustainedreq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "home-timeline-service",
                peer_service="home-timeline-redis",
                delay_ms=20,
                jitter_ms=1,
                ingress_port=6379,
            ),
            workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-redis",
            bottleneck_aliases=["home-timeline-service"],
            network_from_service="home-timeline-service",
            network_to_service="home-timeline-redis",
        ),
pid("home_timeline_to_redis_delay_singlereq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_to_redis_delay_singlereq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "home-timeline-service",
                peer_service="home-timeline-redis",
                delay_ms=50,
                jitter_ms=1,
                ingress_port=6379,
            ),
            workload=wl.single(wl.READ_HOME_TIMELINE),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-redis",
            bottleneck_aliases=["home-timeline-service"],
            network_from_service="home-timeline-service",
            network_to_service="home-timeline-redis",
        ),
pid("frontend_to_user_timeline_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("frontend_to_user_timeline_delay_sustainedreq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "frontend",
                peer_service="user-timeline-service",
                delay_ms=20,
                jitter_ms=5,
                ingress_port=9090,
            ),
            workload=wl.sustained(wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-service",
            bottleneck_aliases=["frontend-service"],
            network_from_service="frontend-service",
            network_to_service="user-timeline-service",
            network_from_aliases=["frontend"],
        ),
pid("frontend_to_user_timeline_delay_singlereq"): lambda: PerformanceProblem(
            problem_id=pid("frontend_to_user_timeline_delay_singlereq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "frontend",
                peer_service="user-timeline-service",
                delay_ms=50,
                jitter_ms=1,
                ingress_port=9090,
            ),
            workload=wl.single(wl.READ_USER_TIMELINE),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-service",
            bottleneck_aliases=["frontend-service"],
            network_from_service="frontend-service",
            network_to_service="user-timeline-service",
            network_from_aliases=["frontend"],
        ),
pid("user_timeline_to_post_storage_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_to_post_storage_delay_sustainedreq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "user-timeline-service",
                peer_service="post-storage-service",
                delay_ms=10,
                jitter_ms=1,
                ingress_port=9090,
            ),
            workload=wl.sustained(wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="post-storage-service",
            bottleneck_aliases=["user-timeline-service"],
            network_from_service="user-timeline-service",
            network_to_service="post-storage-service",
        ),
pid("user_timeline_to_post_storage_delay_singlereq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_to_post_storage_delay_singlereq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "user-timeline-service",
                peer_service="post-storage-service",
                delay_ms=50,
                jitter_ms=1,
                ingress_port=9090,
            ),
            workload=wl.single(wl.READ_USER_TIMELINE),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="post-storage-service",
            bottleneck_aliases=["user-timeline-service"],
            network_from_service="user-timeline-service",
            network_to_service="post-storage-service",
        ),
pid("user_timeline_to_redis_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_to_redis_delay_sustainedreq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "user-timeline-service",
                peer_service="user-timeline-redis",
                delay_ms=20,
                jitter_ms=1,
                ingress_port=6379,
            ),
            workload=wl.sustained(wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-redis",
            bottleneck_aliases=["user-timeline-service"],
            network_from_service="user-timeline-service",
            network_to_service="user-timeline-redis",
        ),
pid("user_timeline_to_redis_delay_singlereq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_to_redis_delay_singlereq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "user-timeline-service",
                peer_service="user-timeline-redis",
                delay_ms=50,
                jitter_ms=1,
                ingress_port=6379,
            ),
            workload=wl.single(wl.READ_USER_TIMELINE),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-redis",
            bottleneck_aliases=["user-timeline-service"],
            network_from_service="user-timeline-service",
            network_to_service="user-timeline-redis",
        ),
pid("post_storage_to_memcached_read_user_timeline_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_to_memcached_read_user_timeline_delay_sustainedreq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "post-storage-service",
                peer_service="post-storage-memcached",
                delay_ms=5,
                jitter_ms=1,
                ingress_port=11211,
            ),
            workload=wl.sustained(wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="post-storage-service",
            network_from_service="post-storage-service",
            network_to_service="post-storage-memcached",
        ),
pid("post_storage_to_memcached_read_user_timeline_delay_singlereq"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_to_memcached_read_user_timeline_delay_singlereq"),
            suite=suite,
            fault=FaultSpec(
                "delay",
                "post-storage-service",
                peer_service="post-storage-memcached",
                delay_ms=5,
                jitter_ms=1,
                ingress_port=11211,
            ),
            workload=wl.single(wl.READ_USER_TIMELINE),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="post-storage-service",
            network_from_service="post-storage-service",
            network_to_service="post-storage-memcached",
        ),
pid("home_timeline_cpu_and_frontend_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_cpu_and_frontend_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="home-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-service",
        ),
pid("home_timeline_cpu_and_post_storage_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_cpu_and_post_storage_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "home-timeline-service",
                    peer_service="post-storage-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-service",
        ),
pid("user_timeline_cpu_and_frontend_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_cpu_and_frontend_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="user-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-service",
        ),
pid("user_timeline_cpu_and_post_storage_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_cpu_and_post_storage_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "user-timeline-service",
                    peer_service="post-storage-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-service",
        ),
pid("frontend_cpu_and_home_post_storage_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("frontend_cpu_and_home_post_storage_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "frontend", cpu_workers=32),
                FaultSpec(
                    "delay",
                    "home-timeline-service",
                    peer_service="post-storage-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="frontend-service",
        ),
pid("frontend_cpu_and_user_post_storage_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("frontend_cpu_and_user_post_storage_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "frontend", cpu_workers=32),
                FaultSpec(
                    "delay",
                    "user-timeline-service",
                    peer_service="post-storage-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="frontend-service",
        ),
pid("home_timeline_cpu_and_memcached_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_cpu_and_memcached_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "post-storage-service",
                    peer_service="post-storage-memcached",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=11211,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-service",
        ),
pid("user_timeline_cpu_and_memcached_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_cpu_and_memcached_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "post-storage-service",
                    peer_service="post-storage-memcached",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=11211,
                ),
            ],
            workload=wl.sustained(
                wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-service",
        ),
pid("post_storage_cpu_and_home_redis_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_cpu_and_home_redis_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "post-storage-service", cpu_workers=22),
                FaultSpec(
                    "delay",
                    "home-timeline-service",
                    peer_service="home-timeline-redis",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=6379,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="post-storage-service",
        ),
pid("post_storage_cpu_and_user_redis_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("post_storage_cpu_and_user_redis_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "post-storage-service", cpu_workers=22),
                FaultSpec(
                    "delay",
                    "user-timeline-service",
                    peer_service="user-timeline-redis",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=6379,
                ),
            ],
            workload=wl.sustained(
                wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="post-storage-service",
        ),
pid("home_timeline_cpu_with_user_timeline_decoy_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_cpu_with_user_timeline_decoy_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec(
                    "cpu", "user-timeline-service", cpu_workers=30, decoy=True
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-service",
        ),
pid("user_timeline_cpu_with_home_timeline_decoy_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_cpu_with_home_timeline_decoy_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
                FaultSpec(
                    "cpu", "home-timeline-service", cpu_workers=30, decoy=True
                ),
            ],
            workload=wl.sustained(
                wl.READ_USER_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"], baseline_p95_ms=5
            ),
            bottleneck_service="user-timeline-service",
        ),
pid("home_frontend_delay_with_user_timeline_decoy_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_frontend_delay_with_user_timeline_decoy_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="home-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
                FaultSpec(
                    "cpu", "user-timeline-service", cpu_workers=30, decoy=True
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-service",
            network_from_service="frontend-service",
            network_to_service="home-timeline-service",
            network_from_aliases=["frontend"],
        ),
pid("home_cpu_and_frontend_delay_with_user_decoy_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_cpu_and_frontend_delay_with_user_decoy_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="home-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
                FaultSpec(
                    "cpu", "user-timeline-service", cpu_workers=30, decoy=True
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE, rate=1000, connections=100, threads=100, duration=60
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="home-timeline-service",
        ),
        # Mixed home+user timeline workload with graded faults on both request paths.
        pid("home_and_user_timeline_cpu_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_and_user_timeline_cpu_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_AND_USER_TIMELINE["endpoint"],
                baseline_p95_ms=11,
            ),
            bottleneck_service="home-timeline-service",
        ),
        # Same mixed load + both CPUs, but disclose one URL; only that path is graded.
        pid("home_and_user_timeline_cpu_disclose_home_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_and_user_timeline_cpu_disclose_home_sustainedreq"),
            suite=suite,
            disclose_url=wl.READ_HOME_TIMELINE["wrk_url"],
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec(
                    "cpu", "user-timeline-service", cpu_workers=30, decoy=True
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"],
                baseline_p95_ms=11,
            ),
            bottleneck_service="home-timeline-service",
        ),
        pid("home_and_user_timeline_cpu_disclose_user_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_and_user_timeline_cpu_disclose_user_sustainedreq"),
            suite=suite,
            disclose_url=wl.READ_USER_TIMELINE["wrk_url"],
            faults=[
                FaultSpec(
                    "cpu", "home-timeline-service", cpu_workers=30, decoy=True
                ),
                FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"],
                baseline_p95_ms=5,
            ),
            bottleneck_service="user-timeline-service",
        ),
        # Mixed home+user load: CPU on one timeline path, network delay on the other.
        pid("home_timeline_cpu_and_user_frontend_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_cpu_and_user_frontend_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="user-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_AND_USER_TIMELINE["endpoint"],
                baseline_p95_ms=11,
            ),
            bottleneck_service="home-timeline-service",
            network_from_service="frontend-service",
            network_to_service="user-timeline-service",
            network_from_aliases=["frontend"],
        ),
        pid("user_timeline_cpu_and_home_frontend_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("user_timeline_cpu_and_home_frontend_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "home-timeline-service",
                    peer_service="post-storage-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_AND_USER_TIMELINE["endpoint"],
                baseline_p95_ms=11,
            ),
            bottleneck_service="user-timeline-service",
            network_from_service="home-timeline-service",
            network_to_service="post-storage-service",
        ),
        # Mixed home+user load: network delay on both timeline paths.
        pid("home_and_user_frontend_delay_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_and_user_frontend_delay_sustainedreq"),
            suite=suite,
            faults=[
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="home-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="user-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_AND_USER_TIMELINE["endpoint"],
                baseline_p95_ms=11,
            ),
            bottleneck_service="home-timeline-service",
            network_from_service="frontend-service",
            network_to_service="home-timeline-service",
            network_from_aliases=["frontend"],
        ),
        # Disclose one URL: grade only the fault on that path; other fault is decoy.
        pid("home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid(
                "home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq"
            ),
            suite=suite,
            disclose_url=wl.READ_HOME_TIMELINE["wrk_url"],
            faults=[
                FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="user-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                    decoy=True,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"],
                baseline_p95_ms=11,
            ),
            bottleneck_service="home-timeline-service",
        ),
        pid("home_timeline_cpu_and_user_frontend_delay_disclose_user_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid(
                "home_timeline_cpu_and_user_frontend_delay_disclose_user_sustainedreq"
            ),
            suite=suite,
            disclose_url=wl.READ_USER_TIMELINE["wrk_url"],
            faults=[
                FaultSpec(
                    "cpu", "home-timeline-service", cpu_workers=30, decoy=True
                ),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="user-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"],
                baseline_p95_ms=5,
            ),
            bottleneck_service="user-timeline-service",
            network_from_service="frontend-service",
            network_to_service="user-timeline-service",
            network_from_aliases=["frontend"],
        ),
        pid("user_timeline_cpu_and_home_post_storage_delay_disclose_user_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid(
                "user_timeline_cpu_and_home_post_storage_delay_disclose_user_sustainedreq"
            ),
            suite=suite,
            disclose_url=wl.READ_USER_TIMELINE["wrk_url"],
            faults=[
                FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
                FaultSpec(
                    "delay",
                    "home-timeline-service",
                    peer_service="post-storage-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                    decoy=True,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"],
                baseline_p95_ms=5,
            ),
            bottleneck_service="user-timeline-service",
        ),
        pid("user_timeline_cpu_and_home_post_storage_delay_disclose_home_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid(
                "user_timeline_cpu_and_home_post_storage_delay_disclose_home_sustainedreq"
            ),
            suite=suite,
            disclose_url=wl.READ_HOME_TIMELINE["wrk_url"],
            faults=[
                FaultSpec(
                    "cpu", "user-timeline-service", cpu_workers=30, decoy=True
                ),
                FaultSpec(
                    "delay",
                    "home-timeline-service",
                    peer_service="post-storage-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"],
                baseline_p95_ms=11,
            ),
            bottleneck_service="home-timeline-service",
            network_from_service="home-timeline-service",
            network_to_service="post-storage-service",
        ),
        pid("home_and_user_frontend_delay_disclose_home_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_and_user_frontend_delay_disclose_home_sustainedreq"),
            suite=suite,
            disclose_url=wl.READ_HOME_TIMELINE["wrk_url"],
            faults=[
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="home-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="user-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                    decoy=True,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"],
                baseline_p95_ms=11,
            ),
            bottleneck_service="home-timeline-service",
            network_from_service="frontend-service",
            network_to_service="home-timeline-service",
            network_from_aliases=["frontend"],
        ),
        pid("home_and_user_frontend_delay_disclose_user_sustainedreq"): lambda: PerformanceProblem(
            problem_id=pid("home_and_user_frontend_delay_disclose_user_sustainedreq"),
            suite=suite,
            disclose_url=wl.READ_USER_TIMELINE["wrk_url"],
            faults=[
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="home-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                    decoy=True,
                ),
                FaultSpec(
                    "delay",
                    "frontend",
                    peer_service="user-timeline-service",
                    delay_ms=50,
                    jitter_ms=1,
                    ingress_port=9090,
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_AND_USER_TIMELINE,
                rate=1000,
                connections=100,
                threads=100,
                duration=60,
            ),
            task=ResourceDiagnosis(
                endpoint=wl.READ_USER_TIMELINE["endpoint"],
                baseline_p95_ms=5,
            ),
            bottleneck_service="user-timeline-service",
            network_from_service="frontend-service",
            network_to_service="user-timeline-service",
            network_from_aliases=["frontend"],
        ),
        # Seer (ASPLOS'19) Fig.17 Case B: limited concurrent connections + a mild
        # backend delay create upstream backpressure (frontend/home-timeline look
        # saturated while the true bottleneck is the constrained post-storage edge).
        pid("home_timeline_to_post_storage_conn_backpressure"): lambda: PerformanceProblem(
            problem_id=pid("home_timeline_to_post_storage_conn_backpressure"),
            suite=suite,
            faults=[
                FaultSpec(
                    "connections",
                    "home-timeline-service",
                    peer_service="post-storage-service",
                    connections=64,
                    # Bounce frontend after home-timeline restarts so its
                    # Thrift clients re-resolve the new task VIP.
                    also_restart=["frontend"],
                ),
            ],
            workload=wl.sustained(
                wl.READ_HOME_TIMELINE,
                rate=1000,
                connections=200,
                threads=100,
                duration=60,
            ),
            task=ServiceDiagnosis(
                endpoint=wl.READ_HOME_TIMELINE["endpoint"], baseline_p95_ms=11
            ),
            bottleneck_service="post-storage-service",
            bottleneck_aliases=["home-timeline-service", "post-storage"],
        ),
    }
