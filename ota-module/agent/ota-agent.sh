#!/bin/sh

set -u

OTA_SERVER="${OTA_SERVER:-http://ota:8090}"
OTA_MODULE="${OTA_MODULE:-unknown}"
OTA_INSTALL_DIR="${OTA_INSTALL_DIR:-$PWD}"
OTA_POLL_INTERVAL="${OTA_POLL_INTERVAL:-5}"

STATE_DIR="$OTA_INSTALL_DIR/.ota-tmp"
VERSION_FILE="$STATE_DIR/current_version"
RESTART_FLAG="$STATE_DIR/restart.flag"
DEVICE_FILE="$STATE_DIR/device.json"

mkdir -p "$STATE_DIR"
[ -f "$VERSION_FILE" ] || echo "0.0.0" > "$VERSION_FILE"

register_device() {
  if [ ! -f "$DEVICE_FILE" ]; then
    curl -fsS -X POST "$OTA_SERVER/devices/register" \
      -H 'Content-Type: application/json' \
      -d "{\"module\":\"$OTA_MODULE\"}" -o "$DEVICE_FILE" 2>/dev/null
  fi
}

device_id() { jq -r '.id // empty' "$DEVICE_FILE" 2>/dev/null; }
device_token() { jq -r '.token // empty' "$DEVICE_FILE" 2>/dev/null; }

report() {
  ver="$1"; status="$2"
  id=$(device_id); tok=$(device_token)
  [ -n "$id" ] && [ -n "$tok" ] || return 0
  curl -fsS -X POST "$OTA_SERVER/devices/$id/report" \
    -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
    -d "{\"version\":\"$ver\",\"status\":\"$status\"}" >/dev/null 2>&1
}

agent_loop() {
  sleep 2
  while true; do
    register_device
    latest_json=$(curl -fsS "$OTA_SERVER/updates/$OTA_MODULE/latest" 2>/dev/null)
    if [ -n "$latest_json" ]; then
      version=$(printf '%s' "$latest_json" | jq -r '.manifest.version // empty' 2>/dev/null)
      current=$(cat "$VERSION_FILE" 2>/dev/null || echo "0.0.0")
      if [ -n "$version" ] && [ "$version" != "$current" ]; then
        echo "[ota-agent] new version for $OTA_MODULE: $current -> $version"
        pkg_url="$OTA_SERVER/updates/$OTA_MODULE/$version/package"
        if curl -fsS "$pkg_url" -o "$STATE_DIR/package.tar.gz" 2>/dev/null; then
          # Extract into the module's staging directory, but only after every
          # member has been checked: regular files and directories only (no
          # symlinks, hardlinks or device nodes) whose resolved path stays
          # inside $STATE_DIR. Anything else rejects the whole package and it
          # is not applied. (This was the CVE-2007-4559-class tar-slip: a bare
          # tarfile.extractall() with no containment check at all.)
          if python3 -c "
import os, sys, tarfile
dest = os.path.realpath('$STATE_DIR')
with tarfile.open('$STATE_DIR/package.tar.gz') as tf:
    members = tf.getmembers()
    for m in members:
        target = os.path.realpath(os.path.join(dest, m.name))
        if not (m.isfile() or m.isdir()) or not (target == dest or target.startswith(dest + os.sep)):
            sys.exit('unsafe archive member: ' + m.name)
    tf.extractall(dest, members=members)
" 2>/tmp/ota-tar-err.log; then
            :
          else
            echo "[ota-agent] rejected $OTA_MODULE $version: unsafe or unreadable package (see /tmp/ota-tar-err.log)"
            echo "$version" > "$VERSION_FILE"
            report "$current" "rejected"
            sleep "$OTA_POLL_INTERVAL"
            continue
          fi

          post_install=$(printf '%s' "$latest_json" | jq -r '.manifest.post_install // empty' 2>/dev/null)
          if [ -n "$post_install" ] && [ "$post_install" != "none" ]; then
            (cd "$OTA_INSTALL_DIR" && sh -c "$post_install")
          fi

          echo "$version" > "$VERSION_FILE"
          touch "$RESTART_FLAG"
          report "$version" "applied"
        else
          report "$current" "download-failed"
        fi
      else
        report "$current" "up-to-date"
      fi
    fi
    sleep "$OTA_POLL_INTERVAL"
  done
}

agent_loop &

rm -f "$RESTART_FLAG"
while true; do
  "$@" &
  main_pid=$!
  while kill -0 "$main_pid" 2>/dev/null; do
    if [ -f "$RESTART_FLAG" ]; then
      rm -f "$RESTART_FLAG"
      echo "[ota-agent] restarting $OTA_MODULE after update"
      kill "$main_pid" 2>/dev/null
      break
    fi
    sleep 1
  done
  wait "$main_pid" 2>/dev/null
done
