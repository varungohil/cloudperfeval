"""Social Network suite (DeathStarBench socialNetwork-tail)."""

from cloudperfeval.suites.base import SuiteSpec
from cloudperfeval.suites.socialnet.problems import build_problems

SOCIALNET = SuiteSpec(
    suite_id="socialnet",
    name="Social Network",
    description="DeathStarBench Social Network (socialNetwork-tail)",
    entry_trace_service="frontend-service",
)

__all__ = ["SOCIALNET", "build_problems"]
