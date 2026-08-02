# Sandbox Failure Analysis

_Generated from `results/sandbox_*/bench_summary.json` · 2026-07-28_

Each model was evaluated on **57** social-network diagnosis problems.

## Classification

| Fault class | Meaning |
|---|---|
| **Setup** | Harness failed before the agent ran (Pumba netem / Jaeger trace capture). Agent never executed. |
| **Agent** | Setup succeeded; failure is a wrong diagnosis or invalid submission. |

## Summary

| Model | Passed | Failed | Setup faults | Agent faults | Accuracy |
|---|---:|---:|---:|---:|---:|
| Claude Code Opus 5 | 48 | 9 | 4 | 5 | 84.2% |
| Claude Code Sonnet 5 | 41 | 16 | 4 | 12 | 71.9% |
| Codex GPT-5.6 Luna | 41 | 16 | 5 | 11 | 71.9% |
| Codex GPT-5.6 Sol | 45 | 12 | 4 | 8 | 79.0% |
| Codex GPT-5.6 Terra | 34 | 23 | 5 | 18 | 59.7% |

## Shared setup failures

These setup faults appear across (nearly) all model runs:

| Problem | Reason |
|---|---|
| `home_and_user_frontend_delay_disclose_home_sustainedreq` | Pumba netem failed adding `tc qdisc` on frontend → user-timeline-service (3 attempts) |
| `home_and_user_frontend_delay_disclose_user_sustainedreq` | Same Pumba / `tc qdisc` failure |
| `home_and_user_frontend_delay_sustainedreq` | Same Pumba / `tc qdisc` failure |
| `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Jaeger had no trace for the injected X-Trace-Id after 60s ingest wait |
| `post_storage_to_memcached_delay_singlereq` *(Luna, Terra)* | Same Jaeger missing-trace failure |

## Claude Code Opus 5

**9 failed** / 57 total (setup=4, agent=5) · passed 48 · accuracy 84.2%

Source directory: `results/sandbox_claudecode_opus5`

### Failure counts

| Metric | Count |
|---|---:|
| Failed problems | 9 |
| Setup faults | 4 |
| Agent faults | 5 |
| Passed | 48 |

### All failed problems

| # | Problem | Fault class | Category | Reason |
|---:|---|---|---|---|
| 1 | `frontend_cpu_and_home_post_storage_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: network: home-timeline-service → post-storage-service. Expected: cpu @ frontend; network: home-timeline-service → post-storage-service. Missing: cpu: frontend → . |
| 2 | `frontend_read_user_timeline_cpu-resource-1` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=frontend-service; expected_faults=cpu @ frontend-service. |
| 3 | `home_and_user_frontend_delay_disclose_home_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| 4 | `home_and_user_frontend_delay_disclose_user_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 5 | `home_and_user_frontend_delay_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 6 | `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | Agent | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: cpu: home-timeline → . |
| 7 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| 8 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service; network: frontend-service → user-timeline-service; cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Extra: network: frontend → home-timeline. |
| 9 | `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Setup | Trace capture failure | Jaeger has no trace for X-Trace-Id '985960cca8ae6f0657e9eeb155a7682f' after 60s ingest wait Agent never ran. |

### Setup faults

| Problem | Category | Reason |
|---|---|---|
| `home_and_user_frontend_delay_disclose_home_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_disclose_user_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Trace capture failure | Jaeger has no trace for X-Trace-Id '985960cca8ae6f0657e9eeb155a7682f' after 60s ingest wait Agent never ran. |

### Agent faults

| Problem | Category | Reason |
|---|---|---|
| `frontend_cpu_and_home_post_storage_delay_sustainedreq` | Wrong diagnosis | Predicted: network: home-timeline-service → post-storage-service. Expected: cpu @ frontend; network: home-timeline-service → post-storage-service. Missing: cpu: frontend → . |
| `frontend_read_user_timeline_cpu-resource-1` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=frontend-service; expected_faults=cpu @ frontend-service. |
| `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: cpu: home-timeline → . |
| `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service; network: frontend-service → user-timeline-service; cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Extra: network: frontend → home-timeline. |

## Claude Code Sonnet 5

**16 failed** / 57 total (setup=4, agent=12) · passed 41 · accuracy 71.9%

Source directory: `results/sandbox_claudecode_sonnet5`

### Failure counts

| Metric | Count |
|---|---:|
| Failed problems | 16 |
| Setup faults | 4 |
| Agent faults | 12 |
| Passed | 41 |

### All failed problems

| # | Problem | Fault class | Category | Reason |
|---:|---|---|---|---|
| 1 | `frontend_to_home_timeline_delay_singlereq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=network, service=home-timeline-service; expected_faults=network: frontend-service → home-timeline-service. |
| 2 | `frontend_to_user_timeline_delay_singlereq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=network, service=user-timeline-service; expected_faults=network: frontend-service → user-timeline-service. |
| 3 | `home_and_user_frontend_delay_disclose_home_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| 4 | `home_and_user_frontend_delay_disclose_user_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 5 | `home_and_user_frontend_delay_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 6 | `home_and_user_timeline_cpu_disclose_user_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=user-timeline-service; expected_faults=cpu @ user-timeline-service. |
| 7 | `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | Agent | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: cpu: home-timeline → . |
| 8 | `home_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: network: frontend → home-timeline. |
| 9 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| 10 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Missing: network: frontend → user-timeline. Extra: network: frontend → home-timeline. |
| 11 | `home_timeline_to_post_storage_conn_backpressure` | Agent | Invalid submission | Agent submission rejected: no_service_in_submission |
| 12 | `post_storage_cpu_and_home_redis_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: network: home-timeline-service → home-timeline-redis. Expected: cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis. Missing: cpu: post-storage → . |
| 13 | `post_storage_to_memcached_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=cpu, service=None; expected resource=network, service=post-storage-service; expected_faults=network: post-storage-service → post-storage-memcached. |
| 14 | `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Setup | Trace capture failure | Jaeger has no trace for X-Trace-Id '1abd0757e0700e7ac20efb36a8f58948' after 60s ingest wait Agent never ran. |
| 15 | `user_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service. Expected: cpu @ user-timeline-service; network: frontend → user-timeline-service. Missing: network: frontend → user-timeline. |
| 16 | `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: user-timeline-service → post-storage-service; network: frontend-service → user-timeline-service. Expected: cpu @ user-timeline-service; network: user-timeline-service → post-storage-service. Extra: network: frontend → user-timeline. |

### Setup faults

| Problem | Category | Reason |
|---|---|---|
| `home_and_user_frontend_delay_disclose_home_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_disclose_user_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Trace capture failure | Jaeger has no trace for X-Trace-Id '1abd0757e0700e7ac20efb36a8f58948' after 60s ingest wait Agent never ran. |

### Agent faults

| Problem | Category | Reason |
|---|---|---|
| `frontend_to_home_timeline_delay_singlereq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=network, service=home-timeline-service; expected_faults=network: frontend-service → home-timeline-service. |
| `frontend_to_user_timeline_delay_singlereq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=network, service=user-timeline-service; expected_faults=network: frontend-service → user-timeline-service. |
| `home_and_user_timeline_cpu_disclose_user_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=user-timeline-service; expected_faults=cpu @ user-timeline-service. |
| `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: cpu: home-timeline → . |
| `home_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: network: frontend → home-timeline. |
| `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Missing: network: frontend → user-timeline. Extra: network: frontend → home-timeline. |
| `home_timeline_to_post_storage_conn_backpressure` | Invalid submission | Agent submission rejected: no_service_in_submission |
| `post_storage_cpu_and_home_redis_delay_sustainedreq` | Wrong diagnosis | Predicted: network: home-timeline-service → home-timeline-redis. Expected: cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis. Missing: cpu: post-storage → . |
| `post_storage_to_memcached_delay_sustainedreq` | Wrong diagnosis | Predicted resource=cpu, service=None; expected resource=network, service=post-storage-service; expected_faults=network: post-storage-service → post-storage-memcached. |
| `user_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | Wrong diagnosis | Predicted: cpu @ user-timeline-service. Expected: cpu @ user-timeline-service; network: frontend → user-timeline-service. Missing: network: frontend → user-timeline. |
| `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: user-timeline-service → post-storage-service; network: frontend-service → user-timeline-service. Expected: cpu @ user-timeline-service; network: user-timeline-service → post-storage-service. Extra: network: frontend → user-timeline. |

## Codex GPT-5.6 Luna

**16 failed** / 57 total (setup=5, agent=11) · passed 41 · accuracy 71.9%

Source directory: `results/sandbox_codex_gpt56luna`

### Failure counts

| Metric | Count |
|---|---:|
| Failed problems | 16 |
| Setup faults | 5 |
| Agent faults | 11 |
| Passed | 41 |

### All failed problems

| # | Problem | Fault class | Category | Reason |
|---:|---|---|---|---|
| 1 | `home_and_user_frontend_delay_disclose_home_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| 2 | `home_and_user_frontend_delay_disclose_user_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 3 | `home_and_user_frontend_delay_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 4 | `home_and_user_timeline_cpu_disclose_user_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: frontend-service → user-timeline-service. Expected: cpu @ user-timeline-service. Extra: network: frontend → user-timeline. |
| 5 | `home_and_user_timeline_cpu_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: frontend-service → user-timeline-service. Expected: cpu @ home-timeline-service; cpu @ user-timeline-service. Missing: cpu: home-timeline → . Extra: network: frontend → user-timeline. |
| 6 | `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | Agent | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: cpu: home-timeline → . |
| 7 | `home_timeline_cpu_and_memcached_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: home-timeline-service → post-storage-service. Expected: cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached. Missing: network: post-storage → post-storage-memcached. Extra: network: home-timeline → post-storage. |
| 8 | `home_timeline_cpu_and_post_storage_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached. Expected: cpu @ home-timeline-service; network: home-timeline-service → post-storage-service. Missing: network: home-timeline → post-storage. Extra: network: post-storage → post-storage-memcached. |
| 9 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| 10 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: frontend-service → home-timeline-service; cpu @ jaeger-spark-dependencies. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Missing: network: frontend → user-timeline. Extra: cpu: jaeger-spark-dependencies → ; network: frontend → home-timeline. |
| 11 | `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; cpu @ user-timeline-service. Expected: cpu @ home-timeline-service. Extra: cpu: user-timeline → . |
| 12 | `home_timeline_to_post_storage_conn_backpressure` | Agent | Invalid submission | Agent submission rejected: no_service_in_submission |
| 13 | `post_storage_cpu_and_home_redis_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis; network: home-timeline-service → post-storage-service. Expected: cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis. Extra: network: home-timeline → post-storage. |
| 14 | `post_storage_to_memcached_delay_singlereq` | Setup | Trace capture failure | Jaeger has no trace for X-Trace-Id '9051ba92f4f94d14d8bb69c8e5b1c402' after 60s ingest wait Agent never ran. |
| 15 | `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Setup | Trace capture failure | Jaeger has no trace for X-Trace-Id '9cf107c4faac4be8c7f22951af72c151' after 60s ingest wait Agent never ran. |
| 16 | `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: frontend-service → user-timeline-service; network: user-timeline-service → post-storage-service. Expected: cpu @ user-timeline-service; network: user-timeline-service → post-storage-service. Extra: network: frontend → user-timeline. |

### Setup faults

| Problem | Category | Reason |
|---|---|---|
| `home_and_user_frontend_delay_disclose_home_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_disclose_user_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `post_storage_to_memcached_delay_singlereq` | Trace capture failure | Jaeger has no trace for X-Trace-Id '9051ba92f4f94d14d8bb69c8e5b1c402' after 60s ingest wait Agent never ran. |
| `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Trace capture failure | Jaeger has no trace for X-Trace-Id '9cf107c4faac4be8c7f22951af72c151' after 60s ingest wait Agent never ran. |

### Agent faults

| Problem | Category | Reason |
|---|---|---|
| `home_and_user_timeline_cpu_disclose_user_sustainedreq` | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: frontend-service → user-timeline-service. Expected: cpu @ user-timeline-service. Extra: network: frontend → user-timeline. |
| `home_and_user_timeline_cpu_sustainedreq` | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: frontend-service → user-timeline-service. Expected: cpu @ home-timeline-service; cpu @ user-timeline-service. Missing: cpu: home-timeline → . Extra: network: frontend → user-timeline. |
| `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: cpu: home-timeline → . |
| `home_timeline_cpu_and_memcached_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: home-timeline-service → post-storage-service. Expected: cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached. Missing: network: post-storage → post-storage-memcached. Extra: network: home-timeline → post-storage. |
| `home_timeline_cpu_and_post_storage_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached. Expected: cpu @ home-timeline-service; network: home-timeline-service → post-storage-service. Missing: network: home-timeline → post-storage. Extra: network: post-storage → post-storage-memcached. |
| `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: frontend-service → home-timeline-service; cpu @ jaeger-spark-dependencies. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Missing: network: frontend → user-timeline. Extra: cpu: jaeger-spark-dependencies → ; network: frontend → home-timeline. |
| `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; cpu @ user-timeline-service. Expected: cpu @ home-timeline-service. Extra: cpu: user-timeline → . |
| `home_timeline_to_post_storage_conn_backpressure` | Invalid submission | Agent submission rejected: no_service_in_submission |
| `post_storage_cpu_and_home_redis_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis; network: home-timeline-service → post-storage-service. Expected: cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis. Extra: network: home-timeline → post-storage. |
| `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: frontend-service → user-timeline-service; network: user-timeline-service → post-storage-service. Expected: cpu @ user-timeline-service; network: user-timeline-service → post-storage-service. Extra: network: frontend → user-timeline. |

## Codex GPT-5.6 Sol

**12 failed** / 57 total (setup=4, agent=8) · passed 45 · accuracy 79.0%

Source directory: `results/sandbox_codex_gpt56sol`

### Failure counts

| Metric | Count |
|---|---:|
| Failed problems | 12 |
| Setup faults | 4 |
| Agent faults | 8 |
| Passed | 45 |

### All failed problems

| # | Problem | Fault class | Category | Reason |
|---:|---|---|---|---|
| 1 | `home_and_user_frontend_delay_disclose_home_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| 2 | `home_and_user_frontend_delay_disclose_user_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 3 | `home_and_user_frontend_delay_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 4 | `home_and_user_timeline_cpu_disclose_home_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| 5 | `home_and_user_timeline_cpu_disclose_user_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=user-timeline-service; expected_faults=cpu @ user-timeline-service. |
| 6 | `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | Agent | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: cpu: home-timeline → . |
| 7 | `home_timeline_cpu_and_memcached_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached. Missing: network: post-storage → post-storage-memcached. Extra: network: frontend → home-timeline. |
| 8 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| 9 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: frontend-service → home-timeline-service; network: frontend-service → user-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Extra: network: frontend → home-timeline. |
| 10 | `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| 11 | `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Setup | Trace capture failure | Jaeger has no trace for X-Trace-Id 'fc844f31b74120fdb54febc2f24f4ded' after 60s ingest wait Agent never ran. |
| 12 | `user_timeline_cpu_and_memcached_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached; network: user-timeline-service → frontend-service. Expected: cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached. Extra: network: user-timeline → frontend. |

### Setup faults

| Problem | Category | Reason |
|---|---|---|
| `home_and_user_frontend_delay_disclose_home_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_disclose_user_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Trace capture failure | Jaeger has no trace for X-Trace-Id 'fc844f31b74120fdb54febc2f24f4ded' after 60s ingest wait Agent never ran. |

### Agent faults

| Problem | Category | Reason |
|---|---|---|
| `home_and_user_timeline_cpu_disclose_home_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| `home_and_user_timeline_cpu_disclose_user_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=user-timeline-service; expected_faults=cpu @ user-timeline-service. |
| `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: cpu: home-timeline → . |
| `home_timeline_cpu_and_memcached_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached. Missing: network: post-storage → post-storage-memcached. Extra: network: frontend → home-timeline. |
| `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: frontend-service → home-timeline-service; network: frontend-service → user-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Extra: network: frontend → home-timeline. |
| `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| `user_timeline_cpu_and_memcached_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached; network: user-timeline-service → frontend-service. Expected: cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached. Extra: network: user-timeline → frontend. |

## Codex GPT-5.6 Terra

**23 failed** / 57 total (setup=5, agent=18) · passed 34 · accuracy 59.7%

Source directory: `results/sandbox_codex_gpt56terra`

### Failure counts

| Metric | Count |
|---|---:|
| Failed problems | 23 |
| Setup faults | 5 |
| Agent faults | 18 |
| Passed | 34 |

### All failed problems

| # | Problem | Fault class | Category | Reason |
|---:|---|---|---|---|
| 1 | `frontend_cpu_and_user_post_storage_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ frontend-service. Expected: cpu @ frontend; network: user-timeline-service → post-storage-service. Missing: network: user-timeline → post-storage. |
| 2 | `home_and_user_frontend_delay_disclose_home_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| 3 | `home_and_user_frontend_delay_disclose_user_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 4 | `home_and_user_frontend_delay_sustainedreq` | Setup | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| 5 | `home_and_user_timeline_cpu_disclose_home_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| 6 | `home_and_user_timeline_cpu_sustainedreq` | Agent | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service; cpu @ home-timeline-service; cpu @ user-timeline-service. Expected: cpu @ home-timeline-service; cpu @ user-timeline-service. Extra: network: frontend → home-timeline. |
| 7 | `home_timeline_cpu_and_frontend_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; cpu @ post-storage-service; network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Extra: cpu: post-storage → . |
| 8 | `home_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: network: frontend → home-timeline. |
| 9 | `home_timeline_cpu_and_memcached_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached. Missing: network: post-storage → post-storage-memcached. |
| 10 | `home_timeline_cpu_and_post_storage_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: home-timeline-service → post-storage-service. Missing: network: home-timeline → post-storage. |
| 11 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: home-timeline-service → post-storage-service. Expected: cpu @ home-timeline-service. Extra: network: home-timeline → post-storage. |
| 12 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Missing: network: frontend → user-timeline. |
| 13 | `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ home-timeline-service; cpu @ user-timeline-service. Expected: cpu @ home-timeline-service. Extra: cpu: user-timeline → . |
| 14 | `home_timeline_to_post_storage_conn_backpressure` | Agent | Invalid submission | Agent submission rejected: no_service_in_submission |
| 15 | `home_timeline_to_post_storage_delay_singlereq_drop_redis_find_client` | Agent | Wrong diagnosis | Predicted: network: home-timeline-service → post-storage-service; network: home-timeline-service → home-timeline-redis. Expected: network: home-timeline-service → post-storage-service. Extra: network: home-timeline → home-timeline-redis. |
| 16 | `post_storage_cpu_and_user_redis_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ post-storage-service. Expected: cpu @ post-storage-service; network: user-timeline-service → user-timeline-redis. Missing: network: user-timeline → user-timeline-redis. |
| 17 | `post_storage_to_memcached_delay_singlereq` | Setup | Trace capture failure | Jaeger has no trace for X-Trace-Id '2ec266ce7e9f14f8df1acb16c7ce33a9' after 60s ingest wait Agent never ran. |
| 18 | `post_storage_to_memcached_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=network, service=post-storage-service; expected_faults=network: post-storage-service → post-storage-memcached. |
| 19 | `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Setup | Trace capture failure | Jaeger has no trace for X-Trace-Id '184a33139ba298c1806fd6e0f19bb344' after 60s ingest wait Agent never ran. |
| 20 | `post_storage_to_memcached_read_user_timeline_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted resource=network, service=None; expected resource=network, service=post-storage-service; expected_faults=network: post-storage-service → post-storage-memcached. |
| 21 | `user_timeline_cpu_and_memcached_delay_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service. Expected: cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached. Missing: network: post-storage → post-storage-memcached. |
| 22 | `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service. Expected: cpu @ user-timeline-service; network: user-timeline-service → post-storage-service. Missing: network: user-timeline → post-storage. |
| 23 | `user_timeline_cpu_with_home_timeline_decoy_sustainedreq` | Agent | Wrong diagnosis | Predicted: cpu @ user-timeline-service; cpu @ home-timeline-service. Expected: cpu @ user-timeline-service. Extra: cpu: home-timeline → . |

### Setup faults

| Problem | Category | Reason |
|---|---|---|
| `home_and_user_frontend_delay_disclose_home_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (frontend -> user-timeline-service (ingress-port=9090); tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_disclose_user_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `home_and_user_frontend_delay_sustainedreq` | Fault injection failure | Pumba netem failed after 3 setup attempts (network delay; tc qdisc add failed). Agent never ran. |
| `post_storage_to_memcached_delay_singlereq` | Trace capture failure | Jaeger has no trace for X-Trace-Id '2ec266ce7e9f14f8df1acb16c7ce33a9' after 60s ingest wait Agent never ran. |
| `post_storage_to_memcached_read_user_timeline_delay_singlereq` | Trace capture failure | Jaeger has no trace for X-Trace-Id '184a33139ba298c1806fd6e0f19bb344' after 60s ingest wait Agent never ran. |

### Agent faults

| Problem | Category | Reason |
|---|---|---|
| `frontend_cpu_and_user_post_storage_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ frontend-service. Expected: cpu @ frontend; network: user-timeline-service → post-storage-service. Missing: network: user-timeline → post-storage. |
| `home_and_user_timeline_cpu_disclose_home_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=cpu, service=home-timeline-service; expected_faults=cpu @ home-timeline-service. |
| `home_and_user_timeline_cpu_sustainedreq` | Wrong diagnosis | Predicted: network: frontend-service → home-timeline-service; cpu @ home-timeline-service; cpu @ user-timeline-service. Expected: cpu @ home-timeline-service; cpu @ user-timeline-service. Extra: network: frontend → home-timeline. |
| `home_timeline_cpu_and_frontend_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; cpu @ post-storage-service; network: frontend-service → home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Extra: cpu: post-storage → . |
| `home_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → home-timeline-service. Missing: network: frontend → home-timeline. |
| `home_timeline_cpu_and_memcached_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached. Missing: network: post-storage → post-storage-memcached. |
| `home_timeline_cpu_and_post_storage_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: home-timeline-service → post-storage-service. Missing: network: home-timeline → post-storage. |
| `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; network: home-timeline-service → post-storage-service. Expected: cpu @ home-timeline-service. Extra: network: home-timeline → post-storage. |
| `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service. Expected: cpu @ home-timeline-service; network: frontend → user-timeline-service. Missing: network: frontend → user-timeline. |
| `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | Wrong diagnosis | Predicted: cpu @ home-timeline-service; cpu @ user-timeline-service. Expected: cpu @ home-timeline-service. Extra: cpu: user-timeline → . |
| `home_timeline_to_post_storage_conn_backpressure` | Invalid submission | Agent submission rejected: no_service_in_submission |
| `home_timeline_to_post_storage_delay_singlereq_drop_redis_find_client` | Wrong diagnosis | Predicted: network: home-timeline-service → post-storage-service; network: home-timeline-service → home-timeline-redis. Expected: network: home-timeline-service → post-storage-service. Extra: network: home-timeline → home-timeline-redis. |
| `post_storage_cpu_and_user_redis_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ post-storage-service. Expected: cpu @ post-storage-service; network: user-timeline-service → user-timeline-redis. Missing: network: user-timeline → user-timeline-redis. |
| `post_storage_to_memcached_delay_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=network, service=post-storage-service; expected_faults=network: post-storage-service → post-storage-memcached. |
| `post_storage_to_memcached_read_user_timeline_delay_sustainedreq` | Wrong diagnosis | Predicted resource=network, service=None; expected resource=network, service=post-storage-service; expected_faults=network: post-storage-service → post-storage-memcached. |
| `user_timeline_cpu_and_memcached_delay_sustainedreq` | Wrong diagnosis | Predicted: cpu @ user-timeline-service. Expected: cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached. Missing: network: post-storage → post-storage-memcached. |
| `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | Wrong diagnosis | Predicted: cpu @ user-timeline-service. Expected: cpu @ user-timeline-service; network: user-timeline-service → post-storage-service. Missing: network: user-timeline → post-storage. |
| `user_timeline_cpu_with_home_timeline_decoy_sustainedreq` | Wrong diagnosis | Predicted: cpu @ user-timeline-service; cpu @ home-timeline-service. Expected: cpu @ user-timeline-service. Extra: cpu: home-timeline → . |
