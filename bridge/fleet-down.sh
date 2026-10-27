#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
$DC -f fleet-compose.yml --profile day1 --profile day2 --profile day3 down "$@"
echo "Fleet stopped."
