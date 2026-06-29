#!/usr/bin/env bash
# Deploy the socialnet Swarm stack from apps/socialnet/source.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="${ROOT}/source"
COMPOSE="${SOURCE}/docker-compose-swarm.yml"
STACK_NAME="${STACK_NAME:-sn}"

if [[ ! -f "${COMPOSE}" ]]; then
  echo "Missing compose file: ${COMPOSE}" >&2
  echo "Ensure apps/socialnet/source points at DeathStarBench/socialNetwork-tail." >&2
  exit 1
fi

echo "Deploying stack '${STACK_NAME}' from ${COMPOSE}"
docker stack deploy -c "${COMPOSE}" "${STACK_NAME}"
