"""Reusable workload specs for the socialnet suite."""

from __future__ import annotations

from cloudperfeval.workload.generator import WorkloadSpec

# Endpoints target the Go frontend-service (port 12345 via frontend_url).
COMPOSE_POST = dict(
    endpoint="/wrk2-api/post/compose",
    wrk_url="/wrk2-api/post/compose",
    wrk_script="./wrk2/scripts/social-network/compose-post.lua",
    method="POST",
    body="username=user_1&user_id=1&text=hello&media_ids=&media_types=&post_type=0",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    trace_service="frontend-service",
)
READ_HOME_TIMELINE = dict(
    endpoint="/wrk2-api/home-timeline/read?user_id=1&start=1&stop=20",
    wrk_url="/wrk2-api/home-timeline/read",
    wrk_script="./wrk2/scripts/social-network/read-home-timeline.lua",
    method="GET",
    trace_service="frontend-service",
)
READ_USER_TIMELINE = dict(
    endpoint="/wrk2-api/user-timeline/read?user_id=1&start=1&stop=20",
    wrk_url="/wrk2-api/user-timeline/read",
    wrk_script="./wrk2/scripts/social-network/read-user-timeline.lua",
    method="GET",
    trace_service="frontend-service",
)


def single(spec: dict) -> WorkloadSpec:
    return WorkloadSpec(mode="single", **spec)


def sustained(
    spec: dict,
    rate: int = 1000,
    duration: int = 60,
    threads: int = 100,
    connections: int = 500,
) -> WorkloadSpec:
    return WorkloadSpec(
        mode="sustained",
        rate=rate,
        duration_sec=duration,
        threads=threads,
        connections=connections,
        **spec,
    )
