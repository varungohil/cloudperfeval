# cloudperfeval

An eval benchmark for **cloud performance debugging**. Each task injects a
performance fault (network delay or CPU stress, via **Pumba**) into one
microservice of a **Docker Swarm** application, drives load (curl or wrk), then
asks an LLM agent to investigate telemetry and **localize the bottleneck
service**. The harness grades the submission against ground truth and recovers
the fault.

Repo layout separates **applications** from **eval suites**:

```text
apps/socialnet/source/     # DeathStarBench source + compose (symlink or submodule)
apps/socialnet/deploy.sh   # deploy the stack
cloudperfeval/suites/      # workloads, problems, SuiteSpec (Python package)
config/suites/             # per-suite cluster URLs
```

The first suite is **DeathStarBench Social Network** (`socialnet`).

## Design

A task is `Problem = FaultSpec + WorkloadSpec + Task + GroundTruth`:

Supports **one or more concurrent Pumba faults** per problem (`faults=[...]`),
while grading remains a **single primary bottleneck** service. Existing
single-fault problems use `fault=FaultSpec(...)`.

| Layer | File | Responsibility |
|-------|------|----------------|
| `FaultSpec` / `PumbaInjector` | `cloudperfeval/fault/pumba.py` | inject one or many faults; recover all |
| `WorkloadSpec` / `WorkloadGenerator` | `cloudperfeval/workload/generator.py` | drive load (curl/wrk), capture trace IDs + p50/p95 |
| `PerformanceTask` | `cloudperfeval/tasks/` | prompt + submission schema + `eval()` |
| `PerformanceProblem` | `cloudperfeval/problems/base.py` | compose fault+load+task, build ground truth |
| `ProblemRegistry` | `cloudperfeval/problems/registry.py` | aggregates per-suite problems |
| `SuiteSpec` + suite modules | `cloudperfeval/suites/` | workloads, problems, metadata |
| App source + deploy | `apps/<suite>/` | source tree, `deploy.sh` |
| `Orchestrator` | `cloudperfeval/orchestrator.py` | inject → load → agent loop → grade → recover |
| evaluator | `cloudperfeval/evaluators/bottleneck.py` | exact match + trace oracle |

### Execution flow

```
init_problem(id):  recover leftovers -> inject fault -> run workload
                   -> build ground truth -> return symptom prompt
run(max_steps):    agent emits one read-only API call per turn
                   -> on submit({...}) -> problem.eval(...) -> recover fault
```

Two task types ship today:

- **service-diagnosis-single-request** (`*-trace-*`): agent is handed one slow
  trace ID and must name the bottleneck service.
- **service-diagnosis-sustained-requests** (`*-open-*`): an endpoint is slow
  under load; the agent explores traces/metrics/logs to find the bottleneck.
- **resource-diagnosis** (`*-resource-*`): under load, the agent identifies
  the bottleneck resource (cpu, mem, network, or disk) and localizes it to a
  service; for network bottlenecks it also names the starting and ending
  services on the congested path.

## Submission + grading

The agent submits:

```
submit({"root_cause_service": "compose-post-service", "reason": "..."})
```

For resource-diagnosis problems:

```
submit({"resource": "cpu", "service": "home-timeline-service", "reason": "..."})
submit({"resource": "network", "from_service": "home-timeline-service",
        "to_service": "post-storage-service", "reason": "..."})
```

For service-diagnosis problems, `eval()` scores two ways and passes if **either**
agrees:

1. **Exact match** of `root_cause_service` vs the faulted service (name
   normalized; `-service` suffix and aliases tolerated).
2. **Trace oracle**: the service with the largest *exclusive* span time in the
   reference trace (`JaegerAPI.self_time_by_service`).

Resource-diagnosis grading requires an exact match on the bottleneck resource
and service localization (for network faults, both `from_service` and
`to_service` must match).

Results (per run) land in `results/<session_id>.json`:

```json
{
  "localization_exact": true,
  "predicted_service": "compose-post-service",
  "expected_service": "compose-post-service",
  "trace_oracle_service": "compose-post-service",
  "trace_oracle_match": true,
  "success": true,
  "steps": 3,
  "duration_sec": 24.1,
  "fault_type": "delay",
  "workload_p95_ms": 812.3
}
```

## Setup

```bash
cd cloudperfeval
pip install -r requirements.txt
# deploy the app (see apps/socialnet/README.md)
./apps/socialnet/deploy.sh
# edit config.yml: manager_host, suites.socialnet URLs, node SSH mapping
```

Cluster prerequisites:
- A running Swarm stack (services named `<stack>_<service>`).
- Prometheus + Jaeger reachable at the configured URLs.
- `pumba` installed on every Swarm node (with `tc`/iproute2 for netem faults).
- `wrk`/`wrk2` on the manager for sustained workloads (curl for single).

## Run

List problems (namespaced by suite):

```bash
python3 run.py --list
python3 run.py --list --suite socialnet
```

Drive one problem manually (type API calls yourself — no LLM needed):

```bash
python3 run.py --problem-id socialnet:compose_post_delay-trace-1 --agent manual
# legacy un-prefixed IDs still work when unique:
python3 run.py --problem-id compose_post_delay-trace-1 --agent manual
```

Run with an LLM agent:

```bash
export OPENAI_API_KEY=sk-...
python3 run.py --problem-id socialnet:compose_post_delay-trace-1 --agent llm --model gpt-4o
python3 run.py --problem-id socialnet:home_timeline_cpu-open-1 --agent llm --model gpt-4o --max-steps 20
```

Run the whole suite and print accuracy:

```bash
python3 bench.py --agent llm --model gpt-4o
python3 bench.py --agent llm --model gpt-4o --suite socialnet
python3 bench.py --agent llm --model gpt-4o --filter delay
```

Use a per-suite config profile:

```bash
python3 run.py --config config/suites/socialnet.yml \
  --problem-id socialnet:compose_post_delay-trace-1 --agent manual
```

## Adding an application and suite

**New application** (e.g. `hotel`):

1. Add `apps/hotel/source/` (submodule or vendored source) and `apps/hotel/deploy.sh`.
2. Add `cloudperfeval/suites/hotel/` with `workloads.py`, `problems.py`, and a
   `SuiteSpec` in `__init__.py`.
3. Register the suite in `cloudperfeval/suites/__init__.py`.
4. Add `suites.hotel` in `config.yml` (or `config/suites/hotel.yml`).

**New problem** in an existing suite — add an entry to that suite's
`problems.py`. Single fault:

```python
suite.namespaced_id("compose_post_delay-trace-1"): lambda: PerformanceProblem(
    problem_id=suite.namespaced_id("compose_post_delay-trace-1"),
    suite=suite,
    fault=FaultSpec("delay", "compose-post-service", delay_ms=500),
    workload=wl.single(wl.COMPOSE_POST),
    task=ServiceDiagnosis(),
    bottleneck_service="compose-post-service",
),
```

Multiple faults, single graded bottleneck:

```python
suite.namespaced_id("compose_multi_fault-trace-1"): lambda: PerformanceProblem(
    problem_id=suite.namespaced_id("compose_multi_fault-trace-1"),
    suite=suite,
    faults=[
        FaultSpec("delay", "compose-post-service", delay_ms=800),
        FaultSpec("delay", "post-storage-service", delay_ms=50),
        FaultSpec("cpu", "social-graph-service", cpu_workers=2),
    ],
    workload=wl.single(wl.COMPOSE_POST),
    task=ServiceDiagnosis(),
    bottleneck_service="compose-post-service",  # primary on critical path
),
```

## Notes / things to adapt to your cluster

- **Trace service names** in workload specs (e.g. `frontend-service`) must match
  what your stack reports to Jaeger. Set `entry_trace_service` on the
  suite's `SuiteSpec` for prompt hints.
- **Pumba node targeting**: `PumbaInjector` resolves the node running the
  target task and runs Pumba there. Provide `node_host_map` or
  `node_domain_suffix` in `config.yml` so worker nodes are SSH-reachable.
- **Read-only agent**: state-mutating docker commands and `pumba` are blocked
  in `actions.py`, so the agent can only observe.
- The fault is always recovered in the orchestrator's `finally` block.
