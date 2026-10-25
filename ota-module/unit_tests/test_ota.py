#!/usr/bin/env python3
"""
Functional tests for the OTA fleet update server - NOT security tests.
These drive the documented protocol from README.md (publish/poll/download,
device register/report) and check the golden path plus the documented error
replies.

Configuration (env vars):
    OTA_HOST        host to connect to (default 127.0.0.1)
    OTA_PORT        port to connect to (default 8090)
    OTA_NO_LAUNCH   if set, never launch a server - connect to OTA_HOST/PORT
    OTA_BINARY      path to a prebuilt `ota` binary to launch locally

Run against an already-running server (e.g. a container on the compose
network):
    OTA_HOST=ota OTA_PORT=8090 OTA_NO_LAUNCH=1 python3 -m unittest test_ota -v

Or let it launch a local binary (build with `go build -o ota .` first):
    python3 -m unittest test_ota -v
"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid

HOST = os.environ.get("OTA_HOST", "127.0.0.1")
PORT = int(os.environ.get("OTA_PORT", "8090"))
BASE = f"http://{HOST}:{PORT}"
# Set by a harness that generated a real credential (see
# ../../generate-secrets.sh); falls back to the compiled-in default key,
# matching today's behavior with no local setup. `or` (not the two-arg
# os.environ.get form) so an *empty* value -- e.g. docker-compose's
# `${OTA_API_KEY:-}` passthrough when the host var is unset -- falls back
# too, matching the server's own envOr() in main.go which treats "" as
# unset the same way.
API_KEY = os.environ.get("OTA_API_KEY") or "ota-default-key-2024"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_server_proc = None
_server_tmpdir = None


def _server_is_up(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_until_up(host, port, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_is_up(host, port):
            return True
        time.sleep(0.1)
    return False


def _find_binary():
    candidate = os.environ.get("OTA_BINARY")
    if candidate and os.path.isfile(candidate):
        return candidate
    candidate = os.path.join(PROJECT_ROOT, "ota")
    if os.path.isfile(candidate):
        return candidate
    return None


def setUpModule():
    global _server_proc, _server_tmpdir

    if _server_is_up(HOST, PORT):
        return

    if os.environ.get("OTA_NO_LAUNCH"):
        if _wait_until_up(HOST, PORT, 30.0):
            return
        raise unittest.SkipTest(f"No server reachable on {HOST}:{PORT} and OTA_NO_LAUNCH is set")

    binary = _find_binary()
    if not binary:
        raise unittest.SkipTest(
            "No running server and no ota binary found to launch "
            "(set OTA_BINARY or run `go build -o ota .` in the project root)"
        )

    _server_tmpdir = tempfile.mkdtemp(prefix="ota_test_")
    env = dict(os.environ)
    env["OTA_PORT"] = str(PORT)
    env["OTA_DATA_DIR"] = os.path.join(_server_tmpdir, "data")

    _server_proc = subprocess.Popen(
        [os.path.abspath(binary)],
        cwd=_server_tmpdir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + 10.0
    while time.time() < deadline:
        if _server_proc.poll() is not None:
            raise unittest.SkipTest("Server process exited during startup")
        if _server_is_up(HOST, PORT):
            return
        time.sleep(0.1)
    raise unittest.SkipTest(f"Server did not come up on {HOST}:{PORT} in time")


def tearDownModule():
    global _server_proc, _server_tmpdir
    if _server_proc is not None:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
        _server_proc = None
    if _server_tmpdir is not None:
        shutil.rmtree(_server_tmpdir, ignore_errors=True)
        _server_tmpdir = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def multipart(fields, filename=None, file_bytes=None):
    boundary = "----otaTest" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                  f'name="{name}"\r\n\r\n{value}\r\n').encode()
    if filename is not None:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                  f'name="package"; filename="{filename}"\r\n'
                  "Content-Type: application/gzip\r\n\r\n").encode()
        body += file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return boundary, body


def request(method, path, body=None, headers=None):
    req = urllib.request.Request(f"{BASE}{path}", data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def publish(module, version, payload, post_install="none", api_key=API_KEY, extra_headers=None):
    sha = hashlib.sha256(payload).hexdigest()
    manifest = {"module": module, "version": version, "sha256": sha, "post_install": post_install}
    boundary, body = multipart({"manifest": json.dumps(manifest)}, "pkg.tar.gz", payload)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if api_key is not None:
        headers["X-OTA-Api-Key"] = api_key
    if extra_headers:
        headers.update(extra_headers)
    status, body = request("POST", "/publish", body, headers)
    return status, json.loads(body)


def register_device(module):
    status, body = request("POST", "/devices/register", json.dumps({"module": module}).encode(),
                            {"Content-Type": "application/json"})
    return status, json.loads(body)


class HealthTests(unittest.TestCase):
    def test_health_ok(self):
        status, body = request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})


class PublishAndDownloadTests(unittest.TestCase):
    def test_publish_then_latest_then_download_roundtrip(self):
        module = "fmm"
        version = f"1.0.0-{uuid.uuid4().hex[:8]}"
        payload = b"a perfectly ordinary update package\n"

        status, body = publish(module, version, payload)
        self.assertEqual(status, 201, body)
        self.assertEqual(body["manifest"]["module"], module)
        self.assertEqual(body["manifest"]["version"], version)
        self.assertEqual(body["size"], len(payload))

        status, body = request("GET", f"/updates/{module}/latest")
        self.assertEqual(status, 200)
        latest = json.loads(body)
        self.assertEqual(latest["manifest"]["version"], version)

        status, body = request("GET", f"/updates/{module}/{version}/package")
        self.assertEqual(status, 200)
        self.assertEqual(body, payload)

    def test_publish_missing_fields_is_400(self):
        boundary, body = multipart({"manifest": json.dumps({"module": "fmm"})}, "pkg.tar.gz", b"x")
        status, resp = request("POST", "/publish", body,
                                {"Content-Type": f"multipart/form-data; boundary={boundary}",
                                 "X-OTA-Api-Key": API_KEY})
        self.assertEqual(status, 400)

    def test_publish_unknown_module_is_400(self):
        status, body = publish("not-a-real-module", "1.0.0", b"x")
        self.assertEqual(status, 400, body)

    def test_publish_checksum_mismatch_is_400(self):
        manifest = {"module": "fmm", "version": "1.0.0", "sha256": "0" * 64, "post_install": "none"}
        boundary, body = multipart({"manifest": json.dumps(manifest)}, "pkg.tar.gz", b"actual bytes")
        status, resp = request("POST", "/publish", body,
                                {"Content-Type": f"multipart/form-data; boundary={boundary}",
                                 "X-OTA-Api-Key": API_KEY})
        self.assertEqual(status, 400)

    def test_publish_without_api_key_is_401(self):
        status, body = publish("fmm", f"1.0.0-{uuid.uuid4().hex[:6]}", b"x", api_key=None)
        self.assertEqual(status, 401, body)

    def test_publish_wrong_method_is_405(self):
        status, body = request("GET", "/publish")
        self.assertEqual(status, 405)

    def test_latest_for_unpublished_module_is_404(self):
        # A freshly-started server (or a module nobody's published for yet
        # in this run) has no advertised latest version.
        status, body = request("GET", "/updates/ipm/latest")
        self.assertIn(status, (200, 404))

    def test_download_missing_version_is_404(self):
        status, body = request("GET", "/updates/fmm/999.999.999-does-not-exist/package")
        self.assertEqual(status, 404)


class DeviceTests(unittest.TestCase):
    def test_register_then_report_roundtrip(self):
        status, dev = register_device("log")
        self.assertEqual(status, 201, dev)
        self.assertTrue(dev["id"])
        self.assertTrue(dev["token"])
        self.assertEqual(dev["module"], "log")

        status, body = request("POST", f"/devices/{dev['id']}/report",
                                json.dumps({"version": "1.0.0", "status": "applied"}).encode(),
                                {"Content-Type": "application/json",
                                 "Authorization": f"Bearer {dev['token']}"})
        self.assertEqual(status, 200, body)

    def test_sync_merges_self_reported_fields(self):
        # /sync accepts a broader, free-form body than /report; this drives
        # the intended "extra self-reported metadata" use case.
        status, dev = register_device("ipm")
        self.assertEqual(status, 201, dev)

        status, body = request("POST", f"/devices/{dev['id']}/sync",
                                json.dumps({"version": "2.3.1", "status": "syncing metadata"}).encode(),
                                {"Content-Type": "application/json",
                                 "Authorization": f"Bearer {dev['token']}"})
        self.assertEqual(status, 200, body)
        updated = json.loads(body)
        self.assertEqual(updated["version"], "2.3.1", updated)
        self.assertEqual(updated["status"], "syncing metadata", updated)
        self.assertEqual(updated["id"], dev["id"], updated)

    def test_sync_wrong_token_is_401(self):
        status, dev = register_device("ipm")
        self.assertEqual(status, 201)
        status, body = request("POST", f"/devices/{dev['id']}/sync",
                                json.dumps({"status": "x"}).encode(),
                                {"Content-Type": "application/json",
                                 "Authorization": "Bearer not-the-real-token"})
        self.assertEqual(status, 401)

    def test_sync_unknown_device_is_404(self):
        status, body = request("POST", "/devices/device-does-not-exist/sync",
                                json.dumps({"status": "x"}).encode(),
                                {"Content-Type": "application/json",
                                 "Authorization": "Bearer whatever"})
        self.assertEqual(status, 404)

    def test_report_wrong_token_is_401(self):
        status, dev = register_device("log")
        self.assertEqual(status, 201)
        status, body = request("POST", f"/devices/{dev['id']}/report",
                                json.dumps({"version": "1.0.0", "status": "applied"}).encode(),
                                {"Content-Type": "application/json",
                                 "Authorization": "Bearer not-the-real-token"})
        self.assertEqual(status, 401)

    def test_report_unknown_device_is_404(self):
        status, body = request("POST", "/devices/device-does-not-exist/report",
                                json.dumps({"version": "1.0.0", "status": "applied"}).encode(),
                                {"Content-Type": "application/json",
                                 "Authorization": "Bearer whatever"})
        self.assertEqual(status, 404)

    def test_register_missing_module_is_400(self):
        status, body = request("POST", "/devices/register", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 400)

    def test_devices_list_requires_api_key(self):
        status, body = request("GET", "/devices")
        self.assertEqual(status, 401)

        status, body = request("GET", "/devices", headers={"X-OTA-Api-Key": API_KEY})
        self.assertEqual(status, 200)
        self.assertIsInstance(json.loads(body), list)


if __name__ == "__main__":
    unittest.main()
