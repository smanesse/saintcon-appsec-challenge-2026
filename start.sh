#!/usr/bin/env bash
# Start the SAINTCON AppSec fleet from the repo root.
#
#   ./start.sh                       console only (fast)
#   ./start.sh fmm dnsm              console + those modules (and their dependencies)
#   ./start.sh day1|day2|day3|all    console + that release day's modules (cumulative)
#   ./start.sh --build-only [targets]  build images without starting anything
#
# Module names: fmm dnsm kvs ipm log mqb ota mail. First builds are slow.
# Thin wrapper over bridge/fleet-up.sh so you can just run ./start.sh from here.
set -euo pipefail
exec "$(dirname "$0")/bridge/fleet-up.sh" "$@"
