#!/usr/bin/env python3
"""
HTTP-based unit tests for the Log Aggregation Module (LOG / log).

These tests exercise the *basic, intended functionality* of the API described
in ../README.md — health, ingesting a record (JSON and form), searching,
downloading a raw log file, the server-rendered dashboard, wiping a log, and
error replies. They are functional tests, not security tests.

Everything is driven purely over HTTP with the Python standard library.

Usage
-----
    python3 -m unittest test_log                 # connect to LOG_HOST/PORT
    python3 test_log.py                          # same, via unittest.main()

Point the tests at a running service:

    LOG_HOST=127.0.0.1 LOG_PORT=8080 LOG_NO_LAUNCH=1 python3 -m unittest test_log

Environment variables
---------------------
    LOG_HOST        host to connect to (default 127.0.0.1)
    LOG_PORT        port to connect to (default 8080)
    LOG_NO_LAUNCH   if set, never launch a server — connect to LOG_HOST/PORT
                    (this service is a compiled JVM fat jar, so the tests do not
                    self-launch; run it via docker-compose / run-in-docker.sh)
    LOG_OP_TOKEN    operator token sent with DELETE /logs (default operator-secret)
"""

import json
import os
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid

HOST = os.environ.get("LOG_HOST", "127.0.0.1")
PORT = int(os.environ.get("LOG_PORT", "8080"))
OP_TOKEN = os.environ.get("LOG_OP_TOKEN", "operator-secret")
BASE = f"http://{HOST}:{PORT}"


# ---------------------------------------------------------------------------
# Tiny stdlib HTTP helpers
# ---------------------------------------------------------------------------
def request(method, path, data=None, headers=None):
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def get(path):
    return request("GET", path)


def ingest_json(source, message, level="INFO"):
    body = json.dumps({"source": source, "level": level, "message": message}).encode()
    return request("POST", "/ingest", data=body,
                   headers={"Content-Type": "application/json"})


def ingest_form(source, message, level="INFO"):
    body = urllib.parse.urlencode(
        {"source": source, "level": level, "message": message}).encode()
    return request("POST", "/ingest", data=body,
                   headers={"Content-Type": "application/x-www-form-urlencoded"})


# ---------------------------------------------------------------------------
# Module-level lifecycle
# ---------------------------------------------------------------------------
def _service_is_up():
    try:
        status, _, body = get("/health")
        return status == 200 and b"ok" in body
    except Exception:
        return False


def _wait_until_up(timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _service_is_up():
            return True
        time.sleep(0.5)
    return False


def setUpModule():
    if _service_is_up():
        return
    # This service is a compiled JVM fat jar; it is not self-launchable from
    # Python. Whether or not LOG_NO_LAUNCH is set, wait for a container to come
    # up (JVM startup can be slow), otherwise skip.
    if _wait_until_up(60.0):
        return
    raise unittest.SkipTest(
        f"No LOG reachable on {HOST}:{PORT}; start it (see unit_tests/run-in-docker.sh)"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class HealthTests(unittest.TestCase):
    def test_health_ok(self):
        status, _, body = get("/health")
        self.assertEqual(status, 200)
        self.assertIn(b"ok", body)


class IngestTests(unittest.TestCase):
    def test_ingest_json_returns_stored(self):
        src = f"nav_{uuid.uuid4().hex[:8]}"
        status, _, body = ingest_json(src, "engine start")
        self.assertEqual(status, 200, body)
        j = json.loads(body)
        self.assertTrue(j.get("stored"), j)
        self.assertEqual(j.get("source"), src, j)
        self.assertEqual(j.get("message"), "engine start", j)

    def test_ingest_form_returns_stored(self):
        src = f"pwr_{uuid.uuid4().hex[:8]}"
        status, _, body = ingest_form(src, "bus voltage nominal")
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body).get("stored"))

    def test_ingest_without_message_is_400(self):
        body = json.dumps({"source": "x", "level": "INFO"}).encode()
        status, _, resp = request("POST", "/ingest", data=body,
                                  headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400, resp)
        self.assertIn("error", json.loads(resp))


class SearchTests(unittest.TestCase):
    def test_search_finds_ingested_line(self):
        src = f"srch_{uuid.uuid4().hex[:8]}"
        token = "MARKER" + uuid.uuid4().hex[:8].upper()
        ingest_json(src, f"telemetry {token} ok")
        status, _, body = get(f"/search?q={token}&source={src}")
        self.assertEqual(status, 200, body)
        j = json.loads(body)
        self.assertGreaterEqual(j.get("count", 0), 1, j)
        self.assertTrue(any(token in m for m in j.get("matches", [])), j)

    def test_search_no_match_is_empty(self):
        src = f"srch_{uuid.uuid4().hex[:8]}"
        ingest_json(src, "nothing interesting here")
        status, _, body = get(f"/search?q=ZZZ{uuid.uuid4().hex}&source={src}")
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body).get("count"), 0)


class DownloadTests(unittest.TestCase):
    def test_download_returns_stored_line(self):
        src = f"dl_{uuid.uuid4().hex[:8]}"
        token = "DL" + uuid.uuid4().hex[:8].upper()
        ingest_json(src, f"payload {token}")
        status, headers, body = get(f"/logs/{src}.log")
        self.assertEqual(status, 200, body)
        self.assertIn(token.encode(), body)

    def test_download_missing_is_404(self):
        status, _, body = get(f"/logs/nope_{uuid.uuid4().hex}.log")
        self.assertEqual(status, 404, body)


class DashboardTests(unittest.TestCase):
    def test_dashboard_renders_recent_line(self):
        token = "DASH" + uuid.uuid4().hex[:8].upper()
        ingest_json(f"dash_{uuid.uuid4().hex[:8]}", f"status {token}")
        status, headers, body = get("/dashboard")
        self.assertEqual(status, 200, body)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(token.encode(), body)


class WipeTests(unittest.TestCase):
    def test_wipe_deletes_log(self):
        src = f"wipe_{uuid.uuid4().hex[:8]}"
        ingest_json(src, "to be deleted")
        # File exists.
        status, _, _ = get(f"/logs/{src}.log")
        self.assertEqual(status, 200)
        # Wipe with the operator token (harness supplies it; a fixed build
        # requires it, this build ignores it — either way this must pass).
        status, _, body = request("DELETE", f"/logs/{src}.log",
                                  headers={"X-Operator-Token": OP_TOKEN})
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body).get("deleted"), body)
        # File is gone.
        status, _, _ = get(f"/logs/{src}.log")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
