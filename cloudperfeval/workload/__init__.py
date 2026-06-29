"""Load generation (single curl request or sustained wrk) + symptom capture."""

from cloudperfeval.workload.generator import (
    WorkloadGenerator,
    WorkloadResult,
    WorkloadSpec,
)

__all__ = ["WorkloadGenerator", "WorkloadResult", "WorkloadSpec"]
