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

One task type is used for almost all problems:

- **resource-diagnosis**: under load (or for a single slow request), the agent
  identifies the bottleneck resource (cpu, mem, network, or disk) and localizes
  it to a service; for network bottlenecks it also names the starting and ending
  services on the congested path. Multi-fault problems require listing every
  contributing fault.

The Seer-style backpressure problem
(`home_timeline_to_post_storage_conn_backpressure`) still uses
**service-diagnosis** (name the bottleneck service only), because either side of
the constrained edge can look saturated.

## Submission + grading

The agent submits:

```
submit({"resource": "cpu", "service": "home-timeline-service", "reason": "..."})
submit({"resource": "network", "from_service": "home-timeline-service",
        "to_service": "post-storage-service", "reason": "..."})
```

Multi-fault problems:

```
submit({"faults": [
  {"resource": "cpu", "service": "home-timeline-service", "reason": "..."},
  {"resource": "network", "from_service": "...", "to_service": "...", "reason": "..."}
]})
```

Resource-diagnosis grading requires an exact match on the bottleneck resource
and service localization (for network faults, both `from_service` and
`to_service` must match). Multi-fault grading is an exact set match over the
submitted `faults` list.

Results (per run) land in `results/<session_id>.json`:

```json
{
  "success": true,
  "resource_exact": true,
  "service_exact": true,
  "predicted_resource": "cpu",
  "expected_resource": "cpu",
  "predicted_service": "compose-post-service",
  "expected_service": "compose-post-service",
  "steps": 3,
  "duration_sec": 24.1,
  "fault_type": "cpu",
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
python3 run.py --problem-id socialnet:home_timeline_cpu-resource-1 --agent manual
# legacy un-prefixed IDs still work when unique:
python3 run.py --problem-id home_timeline_cpu-resource-1 --agent manual
```

Run with an LLM agent:

```bash
export OPENAI_API_KEY=sk-...
python3 run.py --problem-id socialnet:home_timeline_cpu-resource-1 --agent llm --model gpt-4o
python3 run.py --problem-id socialnet:home_timeline_cpu-resource-1 --agent llm --model gpt-4o --max-steps 20
```

Run with Claude Code or Codex (SREGym-style coding agents):

These agents own their tool loop. They investigate via **Bash** +
`python -m cloudperfeval.tools.call` (like SREGym’s kubectl path), write
`submission.json`, then the harness grades. Auth must be available in the
same shell:

```bash
# Claude Code — needs `claude` + ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
export ANTHROPIC_API_KEY=sk-ant-...
python3 run.py --problem-id socialnet:home_timeline_cpu-resource-1 --agent claude-code
python3 run.py --problem-id socialnet:home_timeline_cpu-resource-1 --agent claude-code --model sonnet

# Codex — needs `codex` + OPENAI_API_KEY (or `codex login` / ~/.codex/auth.json)
export OPENAI_API_KEY=sk-...
python3 run.py --problem-id socialnet:home_timeline_cpu-resource-1 --agent codex
python3 run.py --problem-id socialnet:home_timeline_cpu-resource-1 --agent codex --model gpt-5
```

Optional timeout override for coding agents: `CPE_AGENT_TIMEOUT_SEC` (default scales with `--max-steps`).
Per-run artifacts land under `results/agent_workdirs/<problem>_<session>/`
(`INSTRUCTION.md`, `codex.txt` / `claude-code.txt`, `submission.json`).

To confine autonomous agents to a per-run writable `/scratch`, build the
sandbox image and enable it in `config.yml`:

```bash
docker build -f docker/agent-sandbox/Dockerfile -t cpe-agent-sandbox:latest .
# Set agent_sandbox.enabled: true in config.yml
```

The sandbox uses a read-only root filesystem and exposes no CloudPerfEval tools
or tool descriptions. Agents query Prometheus and Jaeger directly using URLs in
`CPE_PROMETHEUS_URL` / `CPE_JAEGER_URL`, inspect Swarm state with the Docker CLI
through a GET-only Unix-socket proxy, read `/opt/app-source`, and write the final
JSON diagnosis to `/scratch/submission.json`. The raw Docker socket is never
mounted. Disable for debugging with `--no-agent-sandbox`.

Run the whole suite and print accuracy:

```bash
python3 bench.py --agent llm --model gpt-4o
python3 bench.py --agent llm --model gpt-4o --suite socialnet
python3 bench.py --agent llm --model gpt-4o --filter delay
python3 bench.py --agent claude-code
python3 bench.py --agent codex
```

Use a per-suite config profile:

```bash
python3 run.py --config config/suites/socialnet.yml \
  --problem-id socialnet:home_timeline_cpu-resource-1 --agent manual
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
suite.namespaced_id("home_timeline_cpu-resource-1"): lambda: PerformanceProblem(
    problem_id=suite.namespaced_id("home_timeline_cpu-resource-1"),
    suite=suite,
    fault=FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
    workload=wl.sustained(wl.READ_HOME_TIMELINE, rate=1000, connections=100, duration=60),
    task=ResourceDiagnosis(endpoint=wl.READ_HOME_TIMELINE["endpoint"]),
    bottleneck_service="home-timeline-service",
),
```

Multiple faults (exact set-match grading):

```python
suite.namespaced_id("home_and_user_timeline_cpu_sustainedreq"): lambda: PerformanceProblem(
    problem_id=suite.namespaced_id("home_and_user_timeline_cpu_sustainedreq"),
    suite=suite,
    faults=[
        FaultSpec("cpu", "home-timeline-service", cpu_workers=30),
        FaultSpec("cpu", "user-timeline-service", cpu_workers=30),
    ],
    workload=wl.sustained(wl.READ_HOME_AND_USER_TIMELINE, rate=1000, connections=100, duration=60),
    task=ResourceDiagnosis(endpoint=wl.READ_HOME_TIMELINE["endpoint"]),
    bottleneck_service="home-timeline-service",
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
