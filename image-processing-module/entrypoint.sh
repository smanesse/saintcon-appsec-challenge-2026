#!/bin/sh
set -eu

SECRET_PATH="${IPM_SECRET:-/home/ctf/ipm/secret/flag.txt}"
mkdir -p "$(dirname "$SECRET_PATH")"

FLAG_VALUE="${IPM_FLAG:-}"
if [ -z "$FLAG_VALUE" ]; then
    FLAG_VALUE='FLAG{local-dev-default}'
fi
printf '%s\n' "$FLAG_VALUE" > "$SECRET_PATH"

exec ./ota-agent.sh "$@"
