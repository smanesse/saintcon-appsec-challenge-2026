#!/usr/bin/env bash
# Start the Bridge Console, plus any modules you name. Modules can also be
# started later from the console's START buttons.
#
#   ./fleet-up.sh                       console only (fast)
#   ./fleet-up.sh fmm dnsm              console + those modules (and their dependencies)
#   ./fleet-up.sh day1|day2|day3|all    console + that release day's modules (cumulative)
#   ./fleet-up.sh --build-only [targets]  build images without starting anything
#
# Module names: fmm dnsm kvs ipm log mqb ota mail. First builds are slow.
set -euo pipefail
cd "$(dirname "$0")"

if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
COMPOSE="$DC -f fleet-compose.yml --profile day1 --profile day2 --profile day3"

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; }

day_services() {
  case "$1" in
    day1|1) echo "fmm dnsm kvs" ;;
    day2|2) echo "fmm dnsm kvs ipm log mqb" ;;
    day3|3|all) echo "fmm dnsm kvs ipm log mqb ota mail" ;;
  esac
}

BUILD_ONLY=0
SERVICES=()
FLAGS=()
KNOWN=" $($COMPOSE config --services | tr '\n' ' ') "
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --build-only) BUILD_ONLY=1 ;;
    -*) FLAGS+=("$arg") ;;
    *)
      lower=$(echo "$arg" | tr '[:upper:]' '[:lower:]')
      [[ "$lower" == "mta" ]] && lower=mail
      if [[ -n "$(day_services "$lower")" ]]; then
        read -ra day <<<"$(day_services "$lower")"
        SERVICES+=("${day[@]}")
      elif [[ "$KNOWN" == *" $lower "* ]]; then
        SERVICES+=("$lower")
      else
        echo "Unknown module or day '$arg'." >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

SECRETS_FILE="../secrets/fleet.env"
if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Generating per-deployment secrets -> secrets/fleet.env"
  mkdir -p ../secrets
  ../generate-secrets.sh > "$SECRETS_FILE"
else
  echo "Reusing existing secrets/fleet.env (delete it to rotate)"
fi
set -a; source "$SECRETS_FILE"; set +a

if (( BUILD_ONLY )); then
  echo "Building ${SERVICES[*]:-every image}. First builds can take 10+ minutes (IPM compiles ImageMagick, LOG pulls sbt)..."
  $COMPOSE build ${FLAGS[@]+"${FLAGS[@]}"} ${SERVICES[@]+"${SERVICES[@]}"}
  echo "Done. Start with ./fleet-up.sh [modules], or from the console."
  exit 0
fi

if (( ${#SERVICES[@]} )); then
  echo "Building + starting the console and: ${SERVICES[*]}"
  echo "First builds are slow (several minutes per module; IPM and LOG are the longest). Later starts reuse the images."
else
  echo "Starting the Bridge Console only. Start modules from its START buttons, or re-run with module names."
fi
$COMPOSE up --build -d ${FLAGS[@]+"${FLAGS[@]}"} bridge ${SERVICES[@]+"${SERVICES[@]}"}

echo
echo "  Bridge Console: http://127.0.0.1:${BRIDGE_PORT:-8787}"
# Mirror the compose default: unset -> public harness; empty (HARNESS_URL=) -> none.
UPLINK="${HARNESS_URL-https://saintcon.sketrik.dev}"
if [ -n "$UPLINK" ]; then
  echo "  Scoring uplink: ${UPLINK}"
else
  echo "  Scoring uplink: (disabled via HARNESS_URL=; no external harness)"
fi
echo "  Ports on 127.0.0.1: FMM 2121  DNSM 8053(+udp)/8054  KVS 6379  IPM 8080  LOG 8085"
echo "                      MQB 1883/8082  OTA 8090  MAIL 2525/8083"
echo
echo "JVM services (IPM, LOG) take 30-60s to answer after starting; then hit RESCAN"
echo "FLEET in the console. Stop everything with ./fleet-down.sh"
