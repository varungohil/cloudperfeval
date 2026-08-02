# Sandbox Eval Summary: Accuracy, Duration, and Cost

_Generated from `results/sandbox_*` with setup failures replaced by `*_setup_rerun` · 2026-07-29_

Each model was evaluated on **57** social-network diagnosis problems. When a problem failed due to a harness setup error (Pumba netem / Jaeger trace capture), the result from the corresponding `*_setup_rerun` directory is used instead.

## Solved problems

| Model | Solved | Failed | Total | Accuracy | Setup faults replaced |
|---|---:|---:|---:|---:|---:|
| Claude Code Opus 5 | 52 | 5 | 57 | 91.2% | 4 |
| Codex GPT-5.6 Sol | 48 | 9 | 57 | 84.2% | 4 |
| Claude Code Sonnet 5 | 45 | 12 | 57 | 78.9% | 4 |
| Codex GPT-5.6 Luna | 45 | 12 | 57 | 78.9% | 5 |
| Codex GPT-5.6 Terra | 38 | 19 | 57 | 66.7% | 5 |

## Duration

Duration is wall-clock `duration_sec` per problem (agent run time). Stats are over all problems with a recorded duration after setup-rerun merge.

| Model | Total | Mean | Median | Max | Min |
|---|---:|---:|---:|---:|---:|
| Claude Code Opus 5 | 6.33 h | 6.7 min | 6.0 min | 18.4 min | 2.3 min |
| Codex GPT-5.6 Sol | 2.74 h | 2.9 min | 2.6 min | 6.1 min | 1.4 min |
| Claude Code Sonnet 5 | 5.19 h | 5.5 min | 5.5 min | 12.2 min | 1.5 min |
| Codex GPT-5.6 Luna | 2.53 h | 2.7 min | 2.4 min | 7.5 min | 1.1 min |
| Codex GPT-5.6 Terra | 1.51 h | 1.6 min | 1.6 min | 3.7 min | 43.4 s |

### Duration (seconds)

| Model | Total (s) | Mean (s) | Median (s) | Max (s) | Min (s) |
|---|---:|---:|---:|---:|---:|
| Claude Code Opus 5 | 22804.2 | 400.1 | 358.9 | 1106.1 | 136.4 |
| Codex GPT-5.6 Sol | 9848.6 | 175.9 | 154.8 | 363.8 | 84.8 |
| Claude Code Sonnet 5 | 18701.9 | 328.1 | 331.8 | 732.6 | 91.1 |
| Codex GPT-5.6 Luna | 9098.5 | 162.5 | 144.1 | 452.3 | 67.1 |
| Codex GPT-5.6 Terra | 5419.0 | 96.8 | 95.1 | 224.6 | 43.4 |

## Monetary cost

Cost is computed from reported `input_tokens` / `output_tokens` using standard API list prices (USD per million tokens). Cached-input discounts are **not** applied because the summaries do not break out cache hits (including GPT/Codex runs).

### Pricing used

| Model | Input ($/MTok) | Output ($/MTok) | Source |
|---|---:|---:|---|
| Claude Code Opus 5 (`Claude Opus 5`) | $5.00 | $25.00 | Anthropic Claude Opus 5 standard API |
| Codex GPT-5.6 Sol (`gpt-5.6-sol`) | $5.00 | $30.00 | OpenAI gpt-5.6-sol standard short-context |
| Claude Code Sonnet 5 (`Claude Sonnet 5`) | $2.00 | $10.00 | Anthropic Claude Sonnet 5 introductory pricing (through Aug 31, 2026) |
| Codex GPT-5.6 Luna (`gpt-5.6-luna`) | $1.00 | $6.00 | OpenAI gpt-5.6-luna standard short-context |
| Codex GPT-5.6 Terra (`gpt-5.6-terra`) | $2.50 | $15.00 | OpenAI gpt-5.6-terra standard short-context |

Sources: [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), [OpenAI pricing](https://developers.openai.com/api/docs/pricing).

| Model | Total cost | Mean | Median | Max | Min | Total input tokens | Total output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Code Opus 5 | $377.41 | $6.62 | $6.25 | $17.68 | $2.27 | 69,058,894 | 1,284,741 |
| Codex GPT-5.6 Sol | $285.19 | $5.09 | $4.69 | $12.04 | $1.61 | 53,697,561 | 556,753 |
| Claude Code Sonnet 5 | $220.58 | $3.87 | $3.87 | $7.42 | $1.13 | 104,337,416 | 1,190,525 |
| Codex GPT-5.6 Luna | $130.95 | $2.34 | $1.80 | $7.31 | $0.7548 | 125,860,126 | 847,592 |
| Codex GPT-5.6 Terra | $110.61 | $1.98 | $1.86 | $4.95 | $0.7593 | 41,729,764 | 419,139 |

## Combined overview

| Model | Solved / Total | Accuracy | Total duration | Mean duration | Total cost | Mean cost |
|---|---:|---:|---:|---:|---:|---:|
| Claude Code Opus 5 | 52/57 | 91.2% | 6.33 h | 6.7 min | $377.41 | $6.62 |
| Codex GPT-5.6 Sol | 48/57 | 84.2% | 2.74 h | 2.9 min | $285.19 | $5.09 |
| Claude Code Sonnet 5 | 45/57 | 78.9% | 5.19 h | 5.5 min | $220.58 | $3.87 |
| Codex GPT-5.6 Luna | 45/57 | 78.9% | 2.53 h | 2.7 min | $130.95 | $2.34 |
| Codex GPT-5.6 Terra | 38/57 | 66.7% | 1.51 h | 1.6 min | $110.61 | $1.98 |

## Failed problems by model

Failures below use setup-rerun results when the main run hit a harness setup error. Residual setup failures (rerun also failed) are listed with predicted/actual as `—`.

### Claude Code Opus 5

**5 failed** / 57 total · passed 52 · accuracy 91.2%

| # | Problem | Predicted fault | Actual fault | Why wrong |
|---:|---|---|---|---|
| 1 | `frontend_cpu_and_home_post_storage_delay_sustainedreq` | network: home-timeline-service → post-storage-service | cpu @ frontend; network: home-timeline-service → post-storage-service | Missing: cpu @ frontend |
| 2 | `frontend_read_user_timeline_cpu-resource-1` | network @ None | cpu @ frontend-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected frontend-service |
| 3 | `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | network: frontend-service → home-timeline-service | cpu @ home-timeline-service; network: frontend → home-timeline-service | Missing: cpu @ home-timeline |
| 4 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | network @ None | cpu @ home-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected home-timeline-service |
| 5 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | network: frontend-service → home-timeline-service; network: frontend-service → user-timeline-service; cpu @ home-timeline-service | cpu @ home-timeline-service; network: frontend → user-timeline-service | Extra: network: frontend → home-timeline |

### Codex GPT-5.6 Sol

**9 failed** / 57 total · passed 48 · accuracy 84.2%

| # | Problem | Predicted fault | Actual fault | Why wrong |
|---:|---|---|---|---|
| 1 | `home_and_user_timeline_cpu_disclose_home_sustainedreq` | network @ None | cpu @ home-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected home-timeline-service |
| 2 | `home_and_user_timeline_cpu_disclose_user_sustainedreq` | network @ None | cpu @ user-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected user-timeline-service |
| 3 | `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | network: frontend-service → home-timeline-service | cpu @ home-timeline-service; network: frontend → home-timeline-service | Missing: cpu @ home-timeline |
| 4 | `home_timeline_cpu_and_memcached_delay_sustainedreq` | cpu @ home-timeline-service; network: frontend-service → home-timeline-service | cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached | Missing: network: post-storage → post-storage-memcached. Extra: network: frontend → home-timeline |
| 5 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | network @ None | cpu @ home-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected home-timeline-service |
| 6 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | cpu @ home-timeline-service; network: frontend-service → home-timeline-service; network: frontend-service → user-timeline-service | cpu @ home-timeline-service; network: frontend → user-timeline-service | Extra: network: frontend → home-timeline |
| 7 | `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | network @ None | cpu @ home-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected home-timeline-service |
| 8 | `post_storage_to_memcached_read_user_timeline_delay_singlereq` | — | — | Setup failure: Jaeger trace capture failed; agent never ran |
| 9 | `user_timeline_cpu_and_memcached_delay_sustainedreq` | cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached; network: user-timeline-service → frontend-service | cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached | Extra: network: user-timeline → frontend |

### Claude Code Sonnet 5

**12 failed** / 57 total · passed 45 · accuracy 78.9%

| # | Problem | Predicted fault | Actual fault | Why wrong |
|---:|---|---|---|---|
| 1 | `frontend_to_home_timeline_delay_singlereq` | network: home-timeline-service → post-storage-service | network: frontend-service → home-timeline-service | Wrong edge source: predicted home-timeline-service, expected frontend-service. Wrong edge target: predicted post-storage-service, expected home-timeline-service |
| 2 | `frontend_to_user_timeline_delay_singlereq` | network: user-timeline-service → post-storage-service | network: frontend-service → user-timeline-service | Wrong edge source: predicted user-timeline-service, expected frontend-service. Wrong edge target: predicted post-storage-service, expected user-timeline-service |
| 3 | `home_and_user_timeline_cpu_disclose_user_sustainedreq` | network @ None | cpu @ user-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected user-timeline-service |
| 4 | `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | network: frontend-service → home-timeline-service | cpu @ home-timeline-service; network: frontend → home-timeline-service | Missing: cpu @ home-timeline |
| 5 | `home_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | cpu @ home-timeline-service | cpu @ home-timeline-service; network: frontend → home-timeline-service | Missing: network: frontend → home-timeline |
| 6 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | network @ None | cpu @ home-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected home-timeline-service |
| 7 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | cpu @ home-timeline-service; network: frontend-service → home-timeline-service | cpu @ home-timeline-service; network: frontend → user-timeline-service | Missing: network: frontend → user-timeline. Extra: network: frontend → home-timeline |
| 8 | `home_timeline_to_post_storage_conn_backpressure` | (invalid: no_service_in_submission) | service=post-storage-service | Invalid submission: no_service_in_submission |
| 9 | `post_storage_cpu_and_home_redis_delay_sustainedreq` | network: home-timeline-service → home-timeline-redis | cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis | Missing: cpu @ post-storage |
| 10 | `post_storage_to_memcached_delay_sustainedreq` | cpu @ None | network: post-storage-service → post-storage-memcached | Wrong resource: predicted cpu, expected network. Wrong edge source: predicted None, expected post-storage-service. Wrong edge target: predicted None, expected post-storage-memcached |
| 11 | `user_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | cpu @ user-timeline-service | cpu @ user-timeline-service; network: frontend → user-timeline-service | Missing: network: frontend → user-timeline |
| 12 | `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | cpu @ user-timeline-service; network: user-timeline-service → post-storage-service; network: frontend-service → user-timeline-service | cpu @ user-timeline-service; network: user-timeline-service → post-storage-service | Extra: network: frontend → user-timeline |

### Codex GPT-5.6 Luna

**12 failed** / 57 total · passed 45 · accuracy 78.9%

| # | Problem | Predicted fault | Actual fault | Why wrong |
|---:|---|---|---|---|
| 1 | `home_and_user_timeline_cpu_disclose_user_sustainedreq` | cpu @ user-timeline-service; network: frontend-service → user-timeline-service | cpu @ user-timeline-service | Extra: network: frontend → user-timeline |
| 2 | `home_and_user_timeline_cpu_sustainedreq` | cpu @ user-timeline-service; network: frontend-service → user-timeline-service | cpu @ home-timeline-service; cpu @ user-timeline-service | Missing: cpu @ home-timeline. Extra: network: frontend → user-timeline |
| 3 | `home_cpu_and_frontend_delay_with_user_decoy_sustainedreq` | network: frontend-service → home-timeline-service | cpu @ home-timeline-service; network: frontend → home-timeline-service | Missing: cpu @ home-timeline |
| 4 | `home_timeline_cpu_and_memcached_delay_sustainedreq` | cpu @ home-timeline-service; network: home-timeline-service → post-storage-service | cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached | Missing: network: post-storage → post-storage-memcached. Extra: network: home-timeline → post-storage |
| 5 | `home_timeline_cpu_and_post_storage_delay_sustainedreq` | cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached | cpu @ home-timeline-service; network: home-timeline-service → post-storage-service | Missing: network: home-timeline → post-storage. Extra: network: post-storage → post-storage-memcached |
| 6 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | network @ None | cpu @ home-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected home-timeline-service |
| 7 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | cpu @ home-timeline-service; network: frontend-service → home-timeline-service; cpu @ jaeger-spark-dependencies | cpu @ home-timeline-service; network: frontend → user-timeline-service | Missing: network: frontend → user-timeline. Extra: cpu @ jaeger-spark-dependencies; network: frontend → home-timeline |
| 8 | `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | cpu @ home-timeline-service; cpu @ user-timeline-service | cpu @ home-timeline-service | Extra: cpu @ user-timeline |
| 9 | `home_timeline_to_post_storage_conn_backpressure` | (invalid: no_service_in_submission) | service=post-storage-service | Invalid submission: no_service_in_submission |
| 10 | `post_storage_cpu_and_home_redis_delay_sustainedreq` | cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis; network: home-timeline-service → post-storage-service | cpu @ post-storage-service; network: home-timeline-service → home-timeline-redis | Extra: network: home-timeline → post-storage |
| 11 | `post_storage_to_memcached_delay_singlereq` | — | — | Setup failure: Jaeger trace capture failed; agent never ran |
| 12 | `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | cpu @ user-timeline-service; network: frontend-service → user-timeline-service; network: user-timeline-service → post-storage-service | cpu @ user-timeline-service; network: user-timeline-service → post-storage-service | Extra: network: frontend → user-timeline |

### Codex GPT-5.6 Terra

**19 failed** / 57 total · passed 38 · accuracy 66.7%

| # | Problem | Predicted fault | Actual fault | Why wrong |
|---:|---|---|---|---|
| 1 | `frontend_cpu_and_user_post_storage_delay_sustainedreq` | cpu @ frontend-service | cpu @ frontend; network: user-timeline-service → post-storage-service | Missing: network: user-timeline → post-storage |
| 2 | `home_and_user_timeline_cpu_disclose_home_sustainedreq` | network @ None | cpu @ home-timeline-service | Wrong resource: predicted network, expected cpu. Wrong service: predicted None, expected home-timeline-service |
| 3 | `home_and_user_timeline_cpu_sustainedreq` | network: frontend-service → home-timeline-service; cpu @ home-timeline-service; cpu @ user-timeline-service | cpu @ home-timeline-service; cpu @ user-timeline-service | Extra: network: frontend → home-timeline |
| 4 | `home_timeline_cpu_and_frontend_delay_sustainedreq` | cpu @ home-timeline-service; cpu @ post-storage-service; network: frontend-service → home-timeline-service | cpu @ home-timeline-service; network: frontend → home-timeline-service | Extra: cpu @ post-storage |
| 5 | `home_timeline_cpu_and_frontend_delay_sustainedreq_svc_drop` | cpu @ home-timeline-service | cpu @ home-timeline-service; network: frontend → home-timeline-service | Missing: network: frontend → home-timeline |
| 6 | `home_timeline_cpu_and_memcached_delay_sustainedreq` | cpu @ home-timeline-service | cpu @ home-timeline-service; network: post-storage-service → post-storage-memcached | Missing: network: post-storage → post-storage-memcached |
| 7 | `home_timeline_cpu_and_post_storage_delay_sustainedreq` | cpu @ home-timeline-service | cpu @ home-timeline-service; network: home-timeline-service → post-storage-service | Missing: network: home-timeline → post-storage |
| 8 | `home_timeline_cpu_and_user_frontend_delay_disclose_home_sustainedreq` | cpu @ home-timeline-service; network: home-timeline-service → post-storage-service | cpu @ home-timeline-service | Extra: network: home-timeline → post-storage |
| 9 | `home_timeline_cpu_and_user_frontend_delay_sustainedreq` | cpu @ home-timeline-service | cpu @ home-timeline-service; network: frontend → user-timeline-service | Missing: network: frontend → user-timeline |
| 10 | `home_timeline_cpu_with_user_timeline_decoy_sustainedreq` | cpu @ home-timeline-service; cpu @ user-timeline-service | cpu @ home-timeline-service | Extra: cpu @ user-timeline |
| 11 | `home_timeline_to_post_storage_conn_backpressure` | (invalid: no_service_in_submission) | service=post-storage-service | Invalid submission: no_service_in_submission |
| 12 | `home_timeline_to_post_storage_delay_singlereq_drop_redis_find_client` | network: home-timeline-service → post-storage-service; network: home-timeline-service → home-timeline-redis | network: home-timeline-service → post-storage-service | Extra: network: home-timeline → home-timeline-redis |
| 13 | `post_storage_cpu_and_user_redis_delay_sustainedreq` | cpu @ post-storage-service | cpu @ post-storage-service; network: user-timeline-service → user-timeline-redis | Missing: network: user-timeline → user-timeline-redis |
| 14 | `post_storage_to_memcached_delay_singlereq` | — | — | Setup failure: Jaeger trace capture failed; agent never ran |
| 15 | `post_storage_to_memcached_delay_sustainedreq` | network: home-timeline-service → post-storage-service | network: post-storage-service → post-storage-memcached | Wrong edge source: predicted home-timeline-service, expected post-storage-service. Wrong edge target: predicted post-storage-service, expected post-storage-memcached |
| 16 | `post_storage_to_memcached_read_user_timeline_delay_sustainedreq` | network: user-timeline-service → post-storage-service | network: post-storage-service → post-storage-memcached | Wrong edge source: predicted user-timeline-service, expected post-storage-service. Wrong edge target: predicted post-storage-service, expected post-storage-memcached |
| 17 | `user_timeline_cpu_and_memcached_delay_sustainedreq` | cpu @ user-timeline-service | cpu @ user-timeline-service; network: post-storage-service → post-storage-memcached | Missing: network: post-storage → post-storage-memcached |
| 18 | `user_timeline_cpu_and_post_storage_delay_sustainedreq_svc_drop` | cpu @ user-timeline-service | cpu @ user-timeline-service; network: user-timeline-service → post-storage-service | Missing: network: user-timeline → post-storage |
| 19 | `user_timeline_cpu_with_home_timeline_decoy_sustainedreq` | cpu @ user-timeline-service; cpu @ home-timeline-service | cpu @ user-timeline-service | Extra: cpu @ home-timeline |

## Notes

- **Setup-rerun merge:** A main-run row is treated as a setup failure when it has an `error` and no `duration_sec` / token counts (agent never executed). Those rows are replaced by the matching `problem_id` from `*_setup_rerun/bench_summary.json`.
- **Residual setup (Codex GPT-5.6 Sol):** `post_storage_to_memcached_read_user_timeline_delay_singlereq` still failed in setup_rerun (Jaeger/Pumba). Counted unsolved; excluded from duration/cost averages.
- **Residual setup (Codex GPT-5.6 Luna):** `post_storage_to_memcached_delay_singlereq` still failed in setup_rerun (Jaeger/Pumba). Counted unsolved; excluded from duration/cost averages.
- **Residual setup (Codex GPT-5.6 Terra):** `post_storage_to_memcached_delay_singlereq` still failed in setup_rerun (Jaeger/Pumba). Counted unsolved; excluded from duration/cost averages.
- **Claude Sonnet 5 pricing:** Uses introductory rates ($2 / $10 per MTok) in effect through August 31, 2026; standard rates after that are $3 / $15.
- **OpenAI long-context rates:** Not applied; token totals are billed at short-context standard rates.
- **Prompt caching:** Not reflected; only base input + output token rates are used. Cached tokens are not present in `bench_summary.json` for Claude or GPT/Codex runs.
