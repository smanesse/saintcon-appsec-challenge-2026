#!/usr/bin/env bash
# Build the server image, run the unit tests against it entirely in Docker,
# and clean up. The vulnerable server never binds a host port.
#
# Exit code mirrors the test run.
set -euo pipefail

cd "$(dirname "$0")"

# `docker compose` (v2) or legacy `docker-compose` — support both.
if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
else
    COMPOSE=(docker-compose)
fi

cleanup() {
    "${COMPOSE[@]}" -f docker-compose.yml down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${COMPOSE[@]}" -f docker-compose.yml up \
    --build \
    --abort-on-container-exit \
    --exit-code-from tests
