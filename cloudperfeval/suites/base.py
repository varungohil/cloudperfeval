"""Suite metadata for problem/workload definitions.

Each suite module defines workloads + problems for one application and
registers a `SuiteSpec`. Deployment-specific values (stack name, URLs) live in
`config.yml` under `suites.<suite_id>`. Application source code lives under
`apps/<suite_id>/` at the repo root (not in this Python package).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SuiteSpec:
    suite_id: str
    name: str
    description: str
    entry_trace_service: str = "frontend-service"

    def namespaced_id(self, short_id: str) -> str:
        return f"{self.suite_id}:{short_id}"
