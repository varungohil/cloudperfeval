"""cloudperfeval — an eval benchmark for cloud performance debugging.

An LLM agent is asked to localize the bottleneck microservice in a Docker Swarm
application after a performance fault (network delay / CPU stress) is injected
with Pumba and the application is driven with load (curl / wrk).

Design layers:
  - FaultSpec + PumbaInjector  : what fault to inject and how
  - WorkloadSpec + WorkloadGenerator : how to drive load and capture symptoms
  - PerformanceTask            : prompt + expected submission + eval()
  - Problem                    : fault + workload + task + ground truth
  - ProblemRegistry            : id -> problem instance
  - Orchestrator               : inject -> load -> agent loop -> grade -> recover
"""

__version__ = "0.1.0"
