#!/usr/bin/env bash
# Build the IPM (and FMM) images, run the IPM unit tests against them entirely
# in Docker, and clean up. Neither vulnerable service binds a host port.
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
