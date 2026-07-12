"""Task types: prompt + expected submission schema + eval()."""

from cloudperfeval.tasks.base import PerformanceTask
from cloudperfeval.tasks.resource_diagnosis import ResourceDiagnosis
from cloudperfeval.tasks.service_diagnosis import ServiceDiagnosis

__all__ = [
    "PerformanceTask",
    "ResourceDiagnosis",
    "ServiceDiagnosis",
]
