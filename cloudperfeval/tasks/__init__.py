"""Task types: prompt + expected submission schema + eval()."""

from cloudperfeval.tasks.base import PerformanceTask
from cloudperfeval.tasks.endpoint_diagnosis import EndpointDiagnosisTask
from cloudperfeval.tasks.trace_localization import TraceLocalizationTask

__all__ = ["PerformanceTask", "EndpointDiagnosisTask", "TraceLocalizationTask"]
