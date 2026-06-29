"""Problem registry: maps a namespaced problem ID to a configured PerformanceProblem.

Naming convention:
    <suite-id>:<fault-summary>-<task-variant>-<n>
e.g. "socialnet:compose_post_delay-trace-1".

Legacy un-prefixed IDs (e.g. "compose_post_delay-trace-1") still resolve when
unique across registered suites.
"""

from __future__ import annotations

from typing import Callable

from cloudperfeval.config import config
from cloudperfeval.problems.base import PerformanceProblem
from cloudperfeval.suites import SUITES, problem_builders


class ProblemRegistry:
    def __init__(self):
        self.REGISTRY: dict[str, Callable[[], PerformanceProblem]] = {}
        self._legacy_aliases: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        for suite in SUITES:
            builder = problem_builders()[suite.suite_id]
            for ns_id, factory in builder(suite).items():
                self.REGISTRY[ns_id] = factory
                short_id = ns_id.split(":", 1)[1]
                if short_id in self._legacy_aliases:
                    raise ValueError(
                        f"Duplicate short problem id {short_id!r} across suites; "
                        "use namespaced ids."
                    )
                self._legacy_aliases[short_id] = ns_id

    def _canonical_id(self, problem_id: str) -> str:
        if problem_id in self.REGISTRY:
            return problem_id
        if problem_id in self._legacy_aliases:
            return self._legacy_aliases[problem_id]
        raise ValueError(
            f"Problem ID {problem_id!r} not found. "
            f"Available: {', '.join(self.get_problem_ids())}"
        )

    def _suite_id_for(self, canonical_id: str) -> str:
        if ":" not in canonical_id:
            raise ValueError(f"Problem id must be namespaced: {canonical_id!r}")
        return canonical_id.split(":", 1)[0]

    def get_problem_instance(self, problem_id: str) -> PerformanceProblem:
        canonical = self._canonical_id(problem_id)
        suite_id = self._suite_id_for(canonical)
        config.apply_suite_profile(suite_id)
        return self.REGISTRY[canonical]()

    def get_problem_ids(
        self,
        task_type: str | None = None,
        suite: str | None = None,
    ) -> list[str]:
        ids = sorted(self.REGISTRY.keys())
        if suite:
            prefix = f"{suite}:"
            ids = [i for i in ids if i.startswith(prefix)]
        if task_type:
            ids = [i for i in ids if task_type in i]
        return ids

    def get_problem_count(self) -> int:
        return len(self.REGISTRY)

    def list_suites(self) -> list[str]:
        return [s.suite_id for s in SUITES]
