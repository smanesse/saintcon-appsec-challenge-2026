#!/usr/bin/env bash
# Run each module's unit tests and vuln tests in Docker.
#
#   ./run-all-unit-tests.sh [-v] [--unit-only|--vuln-only] [name ...]
#
# Vuln tests pass when the exploit is defended: they fail on an unpatched
# module by design. Each PoC gets a fresh stack, and VULN_TIMEOUT (default 600)
# caps it in seconds. Modules run in parallel unless -v is set.
set -uo pipefail
cd "$(dirname "$0")"

VERBOSE=0
RUN_UNIT=1
RUN_VULN=1
VULN_TIMEOUT="${VULN_TIMEOUT:-600}"
FILTERS=()
for arg in "$@"; do
  case "$arg" in
    -v|--verbose) VERBOSE=1 ;;
    --unit-only) RUN_VULN=0 ;;
    --vuln-only) RUN_UNIT=0 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) FILTERS+=("$arg") ;;
  esac
done

# PoC exit codes: 0 = exploit landed, 1 = defended, anything else = could not run.
# A traceback also exits 1, so that counts as could-not-run rather than defended.
run_vuln_module() (
  # PoCs recover real per-deployment secrets, so mint them as a deployment would.
  set -a; source <(./generate-secrets.sh); set +a

  local dir="$1/vuln_tests" project="vuln-$1" compose wait_cmd target poc name out rc failed=0
  compose=(docker compose -p "$project" -f "$dir/docker-compose.yml")

  # The poc service's command is "wait for the target, then run one PoC".
  # Keep the wait and take the target host from the PoC line.
  wait_cmd="$(awk '/^ *- \|$/{f=1;next} f' "$dir/docker-compose.yml" \
    | sed -n '/^ *python3 [0-9][0-9]_/q;p' | sed 's/\$\$/$/g')"
  target="$(awk '/^ *python3 [0-9][0-9]_/{print $3}' "$dir/docker-compose.yml" | tail -n 1)"

  out="$LOGDIR/$1.poc.out"
  "${compose[@]}" build || return 1
  for poc in "$dir"/[0-9][0-9]_*.py; do
    name="$(basename "$poc")"
    "${compose[@]}" up -d --scale poc=0
    timeout "$VULN_TIMEOUT" "${compose[@]}" run --rm -T poc sh -c "$wait_cmd
exec python3 $name $target" 2>&1 | tee "$out"
    rc=${PIPESTATUS[0]}
    [[ $rc -eq 1 ]] && grep -q '^Traceback ' "$out" && rc=3
    "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1
    case "$rc" in
      1) echo "[vuln] PASS       $name" ;;
      0) echo "[vuln] VULNERABLE $name"; failed=1 ;;
      *) echo "[vuln] ERROR      $name (rc=$rc)"; failed=1 ;;
    esac
  done
  return "$failed"
)

MODULES=()
while IFS= read -r m; do MODULES+=("$m"); done < <(find . -mindepth 3 -maxdepth 3 \
  \( -path './*/unit_tests/run-in-docker.sh' -o -path './*/vuln_tests/docker-compose.yml' \) \
  -type f | cut -d/ -f2 | sort -u)

if [[ ${#MODULES[@]} -eq 0 ]]; then
  echo "No */unit_tests/run-in-docker.sh or */vuln_tests/docker-compose.yml found." >&2
  exit 1
fi

LOGDIR="$(mktemp -d)"
trap 'rm -rf "$LOGDIR"' EXIT

run_suite() {
  local label="$1"; shift
  local log="$LOGDIR/$label.log" start end rc secs result
  start=$(date +%s)
  if [[ $VERBOSE -eq 1 ]]; then
    "$@" 2>&1 | tee "$log"; rc=${PIPESTATUS[0]}
  else
    "$@" >"$log" 2>&1; rc=$?
  fi
  end=$(date +%s); secs=$((end - start))

  [[ $rc -eq 0 ]] && result=PASS || result=FAIL
  printf '%s\t%s\t%s\n' "$label" "$result" "$secs" >>"$LOGDIR/results"
  {
    echo "$result $label (${secs}s)"
    if [[ $VERBOSE -eq 0 ]]; then
      if [[ "$label" == *" vuln" ]]; then
        grep -E '^\[vuln\] ' "$log" | sed 's/^/    /'
      elif [[ $rc -ne 0 ]]; then
        tail -n 30 "$log" | sed 's/^/    /'
      fi
    fi
  } | { out="$(cat)"; printf '%s\n' "$out"; }
}

run_module() {
  local module="$1"
  export COMPOSE_PROJECT_NAME="unit-$module"
  if [[ $RUN_UNIT -eq 1 && -f "$module/unit_tests/run-in-docker.sh" ]]; then
    run_suite "$module unit" bash "$module/unit_tests/run-in-docker.sh"
  fi
  unset COMPOSE_PROJECT_NAME
  if [[ $RUN_VULN -eq 1 && -f "$module/vuln_tests/docker-compose.yml" ]]; then
    run_suite "$module vuln" run_vuln_module "$module"
  fi
}

for module in "${MODULES[@]}"; do
  if [[ ${#FILTERS[@]} -gt 0 ]]; then
    keep=0
    for f in "${FILTERS[@]}"; do [[ "$module" == *"$f"* ]] && keep=1; done
    [[ $keep -eq 1 ]] || continue
  fi

  if [[ $VERBOSE -eq 1 ]]; then
    run_module "$module"
  else
    run_module "$module" &
  fi
done
wait

echo
echo "==================================================================="
echo " SUMMARY"
echo "==================================================================="
overall=0
total=0
while IFS=$'\t' read -r label result secs; do
  printf '  %-6s %-33s %ss\n' "$result" "$label" "$secs"
  total=$((total + 1))
  [[ "$result" == PASS ]] || overall=1
done < <(sort "$LOGDIR/results")
echo
if [[ $overall -eq 0 ]]; then
  echo "All $total suite(s) passed."
else
  echo "Some suites failed. Re-run one with:  ./run-all-unit-tests.sh -v <name>"
fi
exit $overall
