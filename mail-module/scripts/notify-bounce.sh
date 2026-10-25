#!/bin/sh
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
mkdir -p "$DIR/../data"
echo "$(date -u +%FT%TZ) BOUNCE from=[$1] rcpt=[$2] reason=[$3]" >> "$DIR/../data/bounces.log"
