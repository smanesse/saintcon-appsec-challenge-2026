#!/usr/bin/env python3
"""
Functional tests for source_url resolution through a configured DNS server
(sourcefetch.go) - NOT security tests. They prove the *functional* wiring the
fleet's DNSM interconnection relies on, using a local fake resolver/origin
(fakeorigin.py) instead of DNSM so the suite is hermetic.

The fake serves a fixed package at http://origin.test/... where `origin.test`
resolves ONLY via the fake DNS. So:
    * OTA with OTA_RESOLVER set  -> can fetch origin.test        (resolver used)
    * OTA without OTA_RESOLVER   -> cannot resolve origin.test   (502, the gate)
    * OTA without OTA_RESOLVER   -> can still fetch a real Docker
                                    service name (default client works)

Config (env vars):
    OTA_HOST / OTA_PORT        resolver-less server (default client)
    OTA_RES_HOST / OTA_RES_PORT  server with OTA_RESOLVER set
    OTA_API_KEY                publish credential

Run on the compose network:
    OTA_NO_LAUNCH=1 python3 -m unittest test_ota_resolver -v
"""
import hashlib
import json
import os
import socket
import time
import unittest
import urllib.error
import urllib.request
import uuid

# Must match fakeorigin.py's PKG exactly so the manifest sha256 lines up.
PKG = b"OTA-FAKE-ORIGIN-PACKAGE-v1\n"
PKG_SHA = hashlib.sha256(PKG).hexdigest()

PLAIN_HOST = os.environ.get("OTA_HOST", "ota")
PLAIN_PORT = int(os.environ.get("OTA_PORT", "8090"))
RES_HOST = os.environ.get("OTA_RES_HOST", "ota-res")
RES_PORT = int(os.environ.get("OTA_RES_PORT", "8090"))
API_KEY = os.environ.get("OTA_API_KEY") or "ota-default-key-2024"


def _wait_until_up(host, port, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def setUpModule():
    if not os.environ.get("OTA_NO_LAUNCH"):
        raise unittest.SkipTest("needs the fake-origin sidecar; run via unit_tests/docker-compose.yml")
    if not (_wait_until_up(RES_HOST, RES_PORT, 30.0) and _wait_until_up(PLAIN_HOST, PLAIN_PORT, 30.0)):
        raise unittest.SkipTest("resolver/plain OTA not reachable and OTA_NO_LAUNCH is set")


def _publish_source(host, port, module, version, source_url):
    """POST /publish with a manifest that names a source_url (no uploaded file)."""
    manifest = {"module": module, "version": version, "sha256": PKG_SHA,
                "post_install": "none", "source_url": source_url}
    boundary = "----otaRes" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="manifest"\r\n\r\n{json.dumps(manifest)}\r\n--{boundary}--\r\n').encode()
    req = urllib.request.Request(
        f"http://{host}:{port}/publish", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "X-OTA-Api-Key": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _download(host, port, module, version):
    with urllib.request.urlopen(
            f"http://{host}:{port}/updates/{module}/{version}/package", timeout=10) as r:
        return r.read()


class SourceUrlResolverTests(unittest.TestCase):
    def test_resolver_server_fetches_via_fake_dns(self):
        # origin.test resolves ONLY through the fake DNS the resolver server is
        # pointed at, so a 201 proves OTA used that resolver for the fetch.
        version = f"1.0.0-res-{uuid.uuid4().hex[:6]}"
        status, resp = _publish_source(
            RES_HOST, RES_PORT, "fmm", version, "http://origin.test/pkg.tar.gz")
        self.assertEqual(status, 201, resp)
        self.assertEqual(_download(RES_HOST, RES_PORT, "fmm", version), PKG)

    def test_resolverless_server_cannot_resolve_fake_name(self):
        # The gate: without OTA_RESOLVER the default resolver has never heard of
        # origin.test, so the fetch fails (502) rather than silently succeeding.
        version = f"1.0.0-gate-{uuid.uuid4().hex[:6]}"
        status, resp = _publish_source(
            PLAIN_HOST, PLAIN_PORT, "fmm", version, "http://origin.test/pkg.tar.gz")
        self.assertEqual(status, 502, resp)

    def test_resolverless_server_still_fetches_real_hostname(self):
        # And the default path still works: a real Docker service name (fakeorigin)
        # resolves via the default resolver, proving the unset case is unbroken.
        version = f"1.0.0-def-{uuid.uuid4().hex[:6]}"
        status, resp = _publish_source(
            PLAIN_HOST, PLAIN_PORT, "fmm", version, "http://fakeorigin:80/pkg.tar.gz")
        self.assertEqual(status, 201, resp)
        self.assertEqual(_download(PLAIN_HOST, PLAIN_PORT, "fmm", version), PKG)


if __name__ == "__main__":
    unittest.main()
