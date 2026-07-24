# Design: Tool-less Agent Scratch Sandbox

**Status:** Implemented behind `agent_sandbox.enabled`  
**Date:** 2026-07-18

## Summary

Run autonomous Claude Code and Codex agents in a Docker filesystem jail where
they can create and execute scripts, but cannot use CloudPerfEval actions. The
experiment measures how agents diagnose faults using only:

- Bash and agent-authored scripts
- direct Prometheus and Jaeger HTTP APIs
- direct read-only Docker Swarm state
- a read-only application source tree

The sandbox prompt contains no CPE action list or action descriptions.

## Security and capability contract

| Capability | Access |
|---|---|
| `/scratch` | Read/write; scripts, agent state, and final submission |
| `/tmp` | Private writable tmpfs; discarded on exit |
| `/opt/app-source` | Read-only application source |
| Prometheus | Direct URL in `CPE_PROMETHEUS_URL` |
| Jaeger | Direct URL in `CPE_JAEGER_URL` |
| Docker Swarm | Docker CLI through a GET/HEAD-only API proxy |
| CloudPerfEval tools | Unavailable |
| Raw Docker socket | Unavailable |
| Repository, ground truth, prior runs | Unavailable |
| Host filesystem | Unavailable except the current run's scratch bind |

The container runs non-root with:

- `--read-only`
- `--cap-drop=ALL`
- `--security-opt=no-new-privileges`
- CPU, memory, and PID limits
- a private `/tmp`
- only the current run's `/scratch` writable

## Execution architecture

```text
Host orchestrator
├── injects fault, runs workload, and grades result
├── starts per-run GET-only Docker API proxy
│    └── forwards allowed reads to /var/run/docker.sock
└── starts sandbox container
     ├── codex exec / claude
     ├── /scratch                    RW
     ├── /opt/app-source             RO
     ├── /run/cpe/docker.sock        RO proxy socket
     ├── CPE_PROMETHEUS_URL
     ├── CPE_JAEGER_URL
     └── CPE_STACK_NAME
```

The proxy is not the host Docker socket. It parses every HTTP request and only
allows `GET` and `HEAD` for these state endpoints:

- `/_ping`, `/version`, `/info`
- `/services` and `/services/<id>` (including logs)
- `/tasks` and `/tasks/<id>`
- `/nodes` and `/nodes/<id>`
- container listing, inspection, and logs
- network listing and inspection

POST, PUT, PATCH, and DELETE are rejected. Secret/config/image export endpoints
are not allowlisted.

## Agent workflow

The agent can run commands such as:

```bash
docker stack services "$CPE_STACK_NAME"
docker service ps sn_frontend --no-trunc
docker service inspect sn_frontend
docker service logs --tail 200 sn_frontend
docker node ls

curl "$CPE_PROMETHEUS_URL/api/v1/query?query=..."
curl "$CPE_JAEGER_URL/api/services"

cat /opt/app-source/config/service-config.json
python /scratch/analyze.py
```

It cannot invoke `python -m cloudperfeval.tools.call`: the CPE package is not
present in the sandbox image and no tool gateway is mounted.

## Submission

There is no `submit` tool. The agent writes one JSON object to:

```text
/scratch/submission.json
```

After the container exits, the host reads
`results/agent_workdirs/<run>/scratch/submission.json` and grades it.

Examples:

```json
{"root_cause_service":"compose-post-service","reason":"..."}
```

```json
{"resource":"cpu","service":"home-timeline-service","reason":"..."}
```

## Configuration

Build the image:

```bash
docker build -f docker/agent-sandbox/Dockerfile \
  -t cpe-agent-sandbox:latest .
```

Enable it:

```yaml
agent_sandbox:
  enabled: true
  runtime: docker
  image: cpe-agent-sandbox:latest
  cpus: 2
  memory_limit: 4g
  pids_limit: 512
  network: bridge
```

Tool-less mode currently requires `manager_host: localhost`, because the
read-only proxy forwards to the local manager's Docker socket.

Use `--no-agent-sandbox` only as a debugging escape hatch.

## Threat model and residual risks

Protected:

- host and repository writes
- benchmark ground-truth disclosure through filesystem mounts
- Docker/Swarm mutation through the provided socket
- access to other run workdirs

Residual:

- outbound bridge networking remains available for model and telemetry APIs
- container isolation depends on the host kernel and Docker runtime
- Docker adds future read endpoints over time; the proxy remains safe by using
  an explicit path allowlist rather than allowing every GET
- Prometheus and Jaeger availability still depends on network routing from the
  container

## Verification

Tests cover:

- writes under `/scratch` succeed
- writes to rootfs and app source fail
- symlink writes cannot escape scratch
- no raw Docker socket is mounted
- CPE package and tool descriptions are absent
- Docker service/node reads succeed through the proxy
- Docker POST requests return HTTP 403
- submission loads from `/scratch/submission.json`

Run:

```bash
CPE_RUN_DOCKER_SANDBOX_TESTS=1 \
  python -m unittest discover -s tests -v
```
