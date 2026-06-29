"""Registered problem suites (workloads + problems per application)."""

from __future__ import annotations

from typing import Callable

from cloudperfeval.problems.base import PerformanceProblem
from cloudperfeval.suites.base import SuiteSpec
from cloudperfeval.suites.socialnet import SOCIALNET, build_problems as build_socialnet_problems

SUITES: list[SuiteSpec] = [SOCIALNET]


def problem_builders() -> dict[str, Callable[[SuiteSpec], dict[str, Callable[[], PerformanceProblem]]]]:
    return {
        SOCIALNET.suite_id: build_socialnet_problems,
    }


def get_suite(suite_id: str) -> SuiteSpec:
    for suite in SUITES:
        if suite.suite_id == suite_id:
            return suite
    raise KeyError(f"Unknown suite {suite_id!r}")


def list_suite_ids() -> list[str]:
    return [s.suite_id for s in SUITES]
