#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"

VERBOSE=0
FILTERS=()
for arg in "$@"; do
  case "$arg" in
    -v|--verbose) VERBOSE=1 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) FILTERS+=("$arg") ;;
  esac
done

RUNNERS=()
while IFS= read -r r; do RUNNERS+=("$r"); done < <(find . -mindepth 3 -maxdepth 3 \
  -path './*/unit_tests/run-in-docker.sh' -type f | sort)

if [[ ${#RUNNERS[@]} -eq 0 ]]; then
  echo "No */unit_tests/run-in-docker.sh found." >&2
  exit 1
fi

LOGDIR="$(mktemp -d)"
trap 'rm -rf "$LOGDIR"' EXIT

declare -a NAMES RESULTS SECS
overall=0

for runner in "${RUNNERS[@]}"; do
  module="${runner#./}"; module="${module%%/*}"

  if [[ ${#FILTERS[@]} -gt 0 ]]; then
    keep=0
    for f in "${FILTERS[@]}"; do [[ "$module" == *"$f"* ]] && keep=1; done
    [[ $keep -eq 1 ]] || continue
  fi

  echo
  echo "==================================================================="
  echo ">>> $module"
  echo "==================================================================="
  log="$LOGDIR/$module.log"
  start=$(date +%s)
  if [[ $VERBOSE -eq 1 ]]; then
    bash "$runner" 2>&1 | tee "$log"; rc=${PIPESTATUS[0]}
  else
    bash "$runner" >"$log" 2>&1; rc=$?
  fi
  end=$(date +%s)

  NAMES+=("$module"); SECS+=("$((end - start))")
  if [[ $rc -eq 0 ]]; then
    RESULTS+=("PASS"); echo "    -> PASS ($((end - start))s)"
  else
    RESULTS+=("FAIL"); overall=1
    echo "    -> FAIL (rc=$rc, $((end - start))s)"
    [[ $VERBOSE -eq 0 ]] && { echo "    --- last 30 lines ---"; tail -n 30 "$log" | sed 's/^/    /'; }
  fi
done

echo
echo "==================================================================="
echo " SUMMARY"
echo "==================================================================="
for i in "${!NAMES[@]}"; do
  printf '  %-6s %-28s %ss\n' "${RESULTS[$i]}" "${NAMES[$i]}" "${SECS[$i]}"
done
echo
if [[ $overall -eq 0 ]]; then
  echo "All ${#NAMES[@]} module(s) passed."
else
  echo "Some modules failed. Re-run one with:  ./run-all-unit-tests.sh -v <name>"
fi
exit $overall
