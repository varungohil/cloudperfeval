# Applications under test

This directory holds **application source code and deployment files** — the real
systems that cloudperfeval drives load against and injects faults into.

| Path | Contents |
|------|----------|
| `apps/<name>/source/` | Application source (submodule, symlink, or vendored tree) |
| `apps/<name>/deploy.sh` | How to deploy that app on your cluster |
| `cloudperfeval/suites/<name>/` | Eval definitions only (workloads, problems) |
| `config/suites/<name>.yml` | Cluster URLs and stack name for that suite |

Suite IDs match app folder names (e.g. `socialnet`).
