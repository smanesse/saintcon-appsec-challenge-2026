#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

warm() {
    local compose="$1" project="$2"
    [ -f "$compose" ] || return 0
    echo "==> building ${compose}"
    docker compose -p "$project" -f "$compose" build
    docker compose -p "$project" -f "$compose" pull --ignore-buildable --quiet 2>/dev/null || true
}

select_modules() {
    local all=(*-module)
    if [ "$#" -eq 0 ]; then
        printf '%s\n' "${all[@]}"
        return
    fi
    local m arg
    for m in "${all[@]}"; do
        for arg in "$@"; do
            case "$m" in *"$arg"*) printf '%s\n' "$m"; break ;; esac
        done
    done
}

failed=()
while IFS= read -r module; do
    [ -d "$module" ] || continue
    slug="prewarm-${module%-module}"
    warm "${module}/unit_tests/docker-compose.yml" "${slug}-unit" || failed+=("${module}/unit_tests")
done < <(select_modules "$@")

if [ "${#failed[@]}" -gt 0 ]; then
    echo "WARNING: some suites failed to build: ${failed[*]}" >&2
    exit 1
fi
echo "==> grading image cache warmed."
