#!/usr/bin/env bash
set -euo pipefail

gen() { openssl rand -hex 24; }
flag() { printf 'FLAG{%s}' "$(openssl rand -hex 16)"; }

cat <<EOF
KVS_REQUIREPASS=$(gen)
MQB_REQUIREPASS=$(gen)
DNSM_ADMIN_TOKEN=$(gen)
OTA_API_KEY=$(gen)
FMM_FLAG=$(flag)
IPM_FLAG=$(flag)
DNSM_FLAG=$(flag)
KVS_FLAG=$(flag)
MQB_FLAG=$(flag)
MTA_FLAG=$(flag)
MTA_AUTH_PASS=$(gen)
OTA_FLAG=$(flag)
LOG_FLAG_VALUE=$(flag)
EOF
