#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if docker compose version >/dev/null 2>&1; then DC=(docker compose); else DC=(docker-compose); fi
COMPOSE=(-f fleet-compose.yml)

case "${1:-up}" in
  up)
    "${DC[@]}" "${COMPOSE[@]}" up --build -d bridge
    echo
    echo "Bridge Console running (detached) at http://127.0.0.1:${BRIDGE_PORT:-8787}"
    echo "  logs:  ./start.sh logs     stop:  ./start.sh down"
    echo "  modules: START buttons in the console, or ./fleet-up.sh <modules|day1-3|all>"
    ;;
  down|stop)
    "${DC[@]}" -f fleet-compose.yml rm -sf bridge
    ;;
  logs)
    "${DC[@]}" -f fleet-compose.yml logs -f bridge
    ;;
  *)
    echo "usage: $0 [up|down|logs]" >&2
    exit 1
    ;;
esac
