#!/bin/sh
if [ -z "${DNSM_FLAG:-}" ]; then
    DNSM_FLAG='FLAG{local-dev-default}'
fi

export DNSM_ADMIN_TOKEN="${DNSM_ADMIN_TOKEN:-dev-admin-token}"

SECRET_PATH="/home/ctf/dnsm/secret/flag.txt"
mkdir -p "$(dirname "$SECRET_PATH")"
printf '%s' "$DNSM_FLAG" > "$SECRET_PATH"

# The per-deployment secret is written only to the file above, OUTSIDE the zone
# directory. It is never placed in the served zone, so the on-disk files under
# the zone directory stay secret-free (which is what lets /zone serve them).

./dnsm