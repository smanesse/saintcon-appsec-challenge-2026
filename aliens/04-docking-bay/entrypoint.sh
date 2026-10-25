#!/bin/sh
set -e

# Crew credentials are minted fresh per boot so they never live in the image.
# Both the origin and the crew bot inherit the same value from this export.
export CREW_USER="${CREW_USER:-flight-crew}"
export CREW_PASS="${CREW_PASS:-$(python3 -c 'import secrets;print(secrets.token_hex(12))')}"

# read-only rootfs: everything mutable lives on the /tmp tmpfs
export JAVA_TOOL_OPTIONS="-Xmx160m -XX:MaxMetaspaceSize=112m -XX:+UseSerialGC -Djava.io.tmpdir=/tmp"
mkdir -p /tmp/tomcat /tmp/varnish

java -jar /app/origin.jar >/tmp/origin.log 2>&1 &
ORIGIN=$!

# wait for the origin to come up on loopback before starting the edge
python3 - <<'PY'
import socket, time, sys
for _ in range(120):
    try:
        with socket.create_connection(("127.0.0.1", 9090), timeout=1):
            sys.exit(0)
    except OSError:
        time.sleep(0.5)
sys.exit(0)
PY

python3 /app/crew-bot.py >/tmp/crew-bot.log 2>&1 &
BOT=$!

trap 'kill $ORIGIN $BOT 2>/dev/null' TERM INT EXIT

exec varnishd -F \
    -f /etc/varnish/default.vcl \
    -a :8080 \
    -s malloc,48m \
    -n /tmp/varnish \
    -j none \
    -t 20
