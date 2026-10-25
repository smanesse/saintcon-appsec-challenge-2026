#!/bin/sh
set -eu

SECRET_PATH="${LOG_SECRET:-/home/ctf/log/secret/flag.txt}"
mkdir -p "$(dirname "$SECRET_PATH")"

FLAG_VALUE="${LOG_FLAG_VALUE:-}"
if [ -z "$FLAG_VALUE" ]; then
  FLAG_VALUE='FLAG{local-dev-default}'
fi
printf '%s\n' "$FLAG_VALUE" > "$SECRET_PATH"

exec ./ota-agent.sh "$@"
