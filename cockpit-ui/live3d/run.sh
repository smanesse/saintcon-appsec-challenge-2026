#!/bin/sh
# SAINTCON 2026 -- ONE COMMAND TO OPEN THE COCKPIT.
#
#     ./live3d/run.sh
#
# It starts a static file server on the REPO ROOT (live3d/serve.py) and opens
# the cockpit.  Ctrl-C stops the server.  Nothing is installed and nothing is
# downloaded: the whole build is vendored (three.js under
# three-exploration/vendor/, the Courier Prime face under fonts/).
#
# Static assets stay local.  Harness traffic leaves via the bridge
# (BRIDGE_URL / BRIDGE_ORIGIN, default http://127.0.0.1:8787), not the
# browser: serve.py reverse-proxies /api/* only.  This launcher does not
# start Docker.
#
# WHY A SERVER AND NOT A SINGLE FILE.  This was investigated and the honest
# answer is in live3d/RESULTS.md, "How to open it".  The short version:
#
#   * The cockpit and the nine module pages are ES modules, and a browser
#     refuses `import` over `file://` -- the origin of a file URL is opaque, so
#     the module fetch is a cross-origin request that can never be allowed.
#     Inlining the code does not help; `<script type="module">` is blocked by
#     the same rule whether the source is a URL or not.
#   * Each module fetches its own `scene.json`, a 3.7 MB `depth.bin` and up to
#     seven `.glb` files.  Those are `fetch()`/XHR, blocked over `file://` for
#     the same reason.
#   * An earlier all-inline build exists (cockpit/cockpit_demo.html, 9.6 MB of
#     data: URIs).  It predates the live three.js close-ups: it is baked plates
#     only, with no WebGL, no depth composite and no DOM readouts on the
#     instrument.  It is not this.
#
# So: one command, which works, rather than one file, which would not.
set -e
PORT="${PORT:-8777}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://localhost:$PORT/live3d/"
AUTH="http://localhost:$PORT/live3d/auth/"
BRIDGE_URL="${BRIDGE_URL:-${BRIDGE_ORIGIN:-http://127.0.0.1:8787}}"
BRIDGE_ORIGIN="${BRIDGE_ORIGIN:-$BRIDGE_URL}"
export BRIDGE_URL BRIDGE_ORIGIN

cd "$ROOT"

# Already serving?  Then just open it.  (Any static server on the repo root
# will do; this only checks that something answers with the wide plate.)
if curl -fsS -o /dev/null "http://localhost:$PORT/cockpit/combined/manifest.json" 2>/dev/null; then
  echo "a server is already answering on port $PORT -- using it"
else
  echo "serving $ROOT on port $PORT"
  python3 "$ROOT/live3d/serve.py" >/dev/null 2>&1 &
  SRV=$!
  trap 'kill $SRV 2>/dev/null || true' EXIT INT TERM
  # wait for it, rather than sleeping and hoping
  for i in $(seq 1 60); do
    if curl -fsS -o /dev/null "http://localhost:$PORT/cockpit/combined/manifest.json" 2>/dev/null; then
      break
    fi
    sleep 0.25
  done
  if ! curl -fsS -o /dev/null "http://localhost:$PORT/cockpit/combined/manifest.json" 2>/dev/null; then
    echo "the server did not come up on port $PORT.  Try:  PORT=8888 $0" >&2
    exit 1
  fi
fi

echo
echo "    COCKPIT:  $URL"
echo "    IDENTIFY: $AUTH"
echo "    coordinator expected at $BRIDGE_URL"
echo
echo "  hover any of the nine modules to see it glow, click to dive into its"
echo "  live close-up, interact, then 'back to cockpit' or Escape to leave."
echo "  The nine module pages also stand alone, e.g."
echo "      http://localhost:$PORT/live3d/modules/PKT/"
echo

if ! curl -fsS -o /dev/null "$BRIDGE_URL/api/health" 2>/dev/null; then
  echo "warning: bridge is not answering at $BRIDGE_URL/api/health" >&2
  echo "         IDENTIFY will show a transport error until the bridge is up." >&2
  echo >&2
fi

if command -v open >/dev/null 2>&1; then open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
else echo "open that URL in a browser."
fi

# Hold the server open in the foreground when we started it.
if [ -n "${SRV:-}" ]; then
  echo "Ctrl-C to stop the server."
  wait $SRV
fi
