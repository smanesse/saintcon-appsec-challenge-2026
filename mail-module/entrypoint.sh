#!/bin/sh
set -eu

SECRET_PATH="${MTA_SECRET:-/home/ctf/mta/secret/flag.txt}"
mkdir -p "$(dirname "$SECRET_PATH")"

FLAG_VALUE="${MTA_FLAG:-}"
if [ -z "$FLAG_VALUE" ]; then
  FLAG_VALUE='FLAG{local-dev-default}'
fi
printf '%s\n' "$FLAG_VALUE" > "$SECRET_PATH"

exec "$@"
