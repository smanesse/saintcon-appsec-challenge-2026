#!/usr/bin/env bash
# Restart the SAINTCON AppSec fleet: stop everything, then start again.
#
#   ./restart.sh                       console only (fast)
#   ./restart.sh fmm dnsm              console + those modules (and their dependencies)
#   ./restart.sh day1|day2|day3|all    console + that release day's modules (cumulative)
#   ./restart.sh --build-only [targets]  build images without starting anything
#
# Same targets as start.sh. Stops the whole fleet first, then starts the given
# targets (console only when none are named).
set -euo pipefail
here="$(dirname "$0")"
"$here/stop.sh"
exec "$here/start.sh" "$@"
