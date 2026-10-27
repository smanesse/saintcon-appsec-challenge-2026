#!/usr/bin/env bash
# Stop the whole SAINTCON AppSec fleet. Thin wrapper over bridge/fleet-down.sh.
#   ./stop.sh            stop everything
#   ./stop.sh -v         also remove named volumes (passes flags through)
set -euo pipefail
exec "$(dirname "$0")/bridge/fleet-down.sh" "$@"
