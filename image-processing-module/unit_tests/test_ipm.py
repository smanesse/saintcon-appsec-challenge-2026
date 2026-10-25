#!/usr/bin/env python3
"""
HTTP-based unit tests for the Image Processing Module (IPM / ipm).

These tests exercise the *basic, intended functionality* of the API described
in ../README.md — health, converting an upload to a standard PNG, storing and
retrieving it through the sibling FMM, converting from a URL, batch (zip)
conversion, SVG metadata reflection, and error replies. They are functional
tests, not security tests.

Everything is driven purely over HTTP.

Usage
-----
    python3 -m unittest test_ipm                 # connect to IPM_HOST/PORT
    python3 test_ipm.py                          # same, via unittest.main()

Point the tests at a running service:

    IPM_HOST=127.0.0.1 IPM_PORT=8080 IPM_NO_LAUNCH=1 python3 -m unittest test_ipm

Environment variables
---------------------
    IPM_HOST        host to connect to (default 127.0.0.1)
    IPM_PORT        port to connect to (default 8080)
    IPM_NO_LAUNCH   if set, never launch a server — connect to IPM_HOST/PORT
                    (this service is a Spring Boot jar + native ImageMagick, so
                    the tests do not self-launch; run it via docker-compose)
"""

import base64
import io
import os
import socket
import threading
import time
import unittest
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

HOST = os.environ.get("IPM_HOST", "127.0.0.1")
PORT = int(os.environ.get("IPM_PORT", "8080"))
BASE = f"http://{HOST}:{PORT}"

# A minimal but valid 1x1 PNG, used as a real image payload for uploads.
ONE_PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ"
    "/pLvAAAAAElFTkSuQmCC"
)


# ---------------------------------------------------------------------------
# Tiny HTTP client helper
# ---------------------------------------------------------------------------
class IpmClient:
    """A thin wrapper over requests for the IPM HTTP API."""

    def __init__(self, base=BASE, timeout=30.0):
        self.base = base
        self.timeout = timeout

    def health(self):
        return requests.get(f"{self.base}/health", timeout=self.timeout)

    def convert(self, data=ONE_PX_PNG, filename="upload.png", params=None):
        files = {"image": (filename, data, "application/octet-stream")}
        return requests.post(f"{self.base}/convert", files=files,
                             params=params or {}, timeout=self.timeout)

    def convert_url(self, url, params=None):
        p = dict(params or {})
        p["url"] = url
        return requests.post(f"{self.base}/convert-url", params=p, timeout=self.timeout)

    def convert_batch(self, archive_bytes, filename="images.zip"):
        files = {"archive": (filename, archive_bytes, "application/zip")}
        return requests.post(f"{self.base}/convert-batch", files=files, timeout=self.timeout)

    def image(self, name):
        return requests.get(f"{self.base}/image/{name}", timeout=self.timeout)


def make_zip(members):
    """Build an in-memory zip from {name: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Module-level lifecycle
# ---------------------------------------------------------------------------
def _service_is_up():
    try:
        r = requests.get(f"{BASE}/health", timeout=2.0)
        return r.status_code == 200
    except requests.RequestException:
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
    if os.environ.get("IPM_NO_LAUNCH"):
        # A service is expected elsewhere (e.g. a container on the compose
        # network). ImageMagick + JVM startup can be slow — wait generously.
        if _wait_until_up(60.0):
            return
        raise unittest.SkipTest(
            f"No IPM reachable on {HOST}:{PORT} and IPM_NO_LAUNCH is set"
        )
    # This service is not self-launchable from Python (Spring Boot jar + native
    # ImageMagick); run it via unit_tests/run-in-docker.sh.
    if _wait_until_up(60.0):
        return
    raise unittest.SkipTest(
        f"No IPM reachable on {HOST}:{PORT}; start it (see unit_tests/run-in-docker.sh)"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class IpmTestBase(unittest.TestCase):
    def setUp(self):
        self.c = IpmClient()


class HealthTests(IpmTestBase):
    def test_health_ok(self):
        r = self.c.health()
        self.assertEqual(r.status_code, 200)
        self.assertIn("ok", r.text)


class ConvertTests(IpmTestBase):
    def test_convert_returns_stored_json(self):
        r = self.c.convert()
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("stored"), body)
        self.assertTrue(body.get("name", "").endswith(".png"), body)
        self.assertGreater(body.get("bytes", 0), 0, body)

    def test_convert_with_explicit_name_and_size(self):
        name = f"kitten_{uuid.uuid4().hex[:8]}.png"
        r = self.c.convert(params={"name": name, "width": "64", "height": "64"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("name"), name, body)
        self.assertTrue(body.get("stored"), body)

    def test_convert_missing_image_is_error(self):
        # No file part at all -> framework rejects with a 4xx.
        r = requests.post(f"{BASE}/convert", timeout=30)
        self.assertGreaterEqual(r.status_code, 400)
        self.assertLess(r.status_code, 500)

    def test_convert_garbage_is_bad_request(self):
        # Not an image -> ImageMagick fails -> 400 with a JSON error body.
        r = self.c.convert(data=b"this is definitely not an image", filename="junk.png")
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("error", r.json())


class RoundTripTests(IpmTestBase):
    def test_stored_image_is_retrievable(self):
        name = f"round_{uuid.uuid4().hex[:8]}.png"
        r = self.c.convert(params={"name": name})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("stored"), r.text)

        got = self.c.image(name)
        self.assertEqual(got.status_code, 200, got.text)
        # FMM transfers are byte-exact over the data connection, so the
        # retrieved payload is the stored PNG unchanged (PNG magic intact).
        self.assertTrue(got.content.startswith(b"\x89PNG"), got.content[:16])

    def test_missing_image_is_404(self):
        got = self.c.image(f"nope_{uuid.uuid4().hex}.png")
        self.assertEqual(got.status_code, 404, got.text)

    def test_jpeg_format_round_trips_with_correct_content_type(self):
        # format=jpg produces real JPEG bytes; both the retrieval
        # Content-Type and the magic bytes should say so, not PNG.
        name = f"round_{uuid.uuid4().hex[:8]}.jpg"
        r = self.c.convert(params={"name": name, "format": "jpg"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("stored"), r.text)

        got = self.c.image(name)
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(got.headers.get("Content-Type"), "image/jpeg", got.headers)
        self.assertTrue(got.content.startswith(b"\xff\xd8\xff"), got.content[:16])


class ConvertUrlTests(IpmTestBase):
    """Serve a PNG from this container and have IPM fetch it back."""

    @classmethod
    def setUpClass(cls):
        payload = ONE_PX_PNG

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        # The address IPM should use to reach us across the compose network.
        cls.myhost = socket.gethostname()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_convert_from_url(self):
        url = f"http://{self.myhost}:{self.port}/source.png"
        try:
            r = self.c.convert_url(url)
        except requests.RequestException as e:
            self.skipTest(f"convert-url request failed: {e}")
            return
        if r.status_code != 200:
            self.skipTest(f"IPM could not fetch {url} (status {r.status_code}): {r.text}")
            return
        body = r.json()
        self.assertTrue(body.get("stored"), body)
        self.assertGreater(body.get("bytes", 0), 0, body)


class BatchTests(IpmTestBase):
    def test_convert_batch_zip(self):
        archive = make_zip({
            "a.png": ONE_PX_PNG,
            "b.png": ONE_PX_PNG,
        })
        r = self.c.convert_batch(archive)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("count"), 2, body)
        stored = [x for x in body.get("results", []) if x.get("stored")]
        self.assertEqual(len(stored), 2, body)
        # Each member must have actually been converted, not just flagged
        # stored: real PNG output means a non-empty byte count. This pins the
        # shared convert pipeline so a "return stored:true with no output"
        # shortcut can't pass.
        for x in stored:
            self.assertGreater(x.get("bytes", 0), 0, body)


class SvgMetadataTests(IpmTestBase):
    def test_svg_declared_size_is_reflected(self):
        svg = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="123" height="45">'
            '<rect width="123" height="45" fill="blue"/></svg>'
        ).encode()
        r = self.c.convert(data=svg, filename="drawing.svg")
        if r.status_code != 200:
            # The bundled ImageMagick may lack an SVG delegate in some builds;
            # the metadata parse still happened, but conversion failed.
            self.skipTest(f"SVG conversion unavailable (status {r.status_code}): {r.text}")
            return
        body = r.json()
        self.assertIn("svg", body, body)
        self.assertEqual(body["svg"].get("width"), "123", body)
        self.assertEqual(body["svg"].get("height"), "45", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
