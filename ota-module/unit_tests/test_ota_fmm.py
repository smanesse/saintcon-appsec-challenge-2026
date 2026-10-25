#!/usr/bin/env python3
"""
Functional tests for fetching a manifest's package from the fleet file server
(fmmfetch.go / the OTA_FMM path) - NOT security tests. They prove the functional
wiring the OTA->FMM interconnection relies on, using a local fake FMM
(fakefmm.py) instead of the real module so the suite stays hermetic.

The fake serves a fixed package for any RETR, so:
    * OTA with OTA_FMM set    -> fmm:// source_url is fetched over FTP  (201)
    * OTA with OTA_FMM unset   -> fmm:// source_url is unsupported       (502, gate)

Config (env vars):
    OTA_FMM_HOST / OTA_FMM_PORT   server with OTA_FMM set (FMM client on)
    OTA_HOST / OTA_PORT            resolver/FMM-less server (the gate control)
    OTA_API_KEY                   publish credential

Run on the compose network:
    OTA_NO_LAUNCH=1 python3 -m unittest test_ota_fmm -v
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

# Must match fakefmm.py's PKG exactly so the manifest sha256 lines up.
PKG = b"OTA-FAKE-FMM-PACKAGE-v1\n"
PKG_SHA = hashlib.sha256(PKG).hexdigest()

PLAIN_HOST = os.environ.get("OTA_HOST", "ota")
PLAIN_PORT = int(os.environ.get("OTA_PORT", "8090"))
FMM_HOST = os.environ.get("OTA_FMM_HOST", "ota-fmm")
FMM_PORT = int(os.environ.get("OTA_FMM_PORT", "8090"))
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
        raise unittest.SkipTest("needs the fake-fmm sidecar; run via unit_tests/docker-compose.yml")
    if not (_wait_until_up(FMM_HOST, FMM_PORT, 30.0) and _wait_until_up(PLAIN_HOST, PLAIN_PORT, 30.0)):
        raise unittest.SkipTest("fmm/plain OTA not reachable and OTA_NO_LAUNCH is set")


def _publish_source(host, port, module, version, source_url):
    """POST /publish with a manifest that names a source_url (no uploaded file)."""
    manifest = {"module": module, "version": version, "sha256": PKG_SHA,
                "post_install": "none", "source_url": source_url}
    boundary = "----otaFmm" + uuid.uuid4().hex
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


class FmmSourceTests(unittest.TestCase):
    def test_default_endpoint_fetches_over_ftp(self):
        # fmm:///path uses OTA_FMM as the endpoint; a 201 + matching bytes proves
        # OTA logged in, went passive, and RETR'd the file from the fake FMM.
        version = f"1.0.0-fmm-{uuid.uuid4().hex[:6]}"
        status, resp = _publish_source(
            FMM_HOST, FMM_PORT, "fmm", version, "fmm:///builds/pkg.tar.gz")
        self.assertEqual(status, 201, resp)
        self.assertEqual(_download(FMM_HOST, FMM_PORT, "fmm", version), PKG)

    def test_explicit_host_in_url_is_honoured(self):
        # fmm://host:port/path overrides the configured default endpoint - the
        # same "no host restriction" shape the http source_url path has.
        version = f"1.0.0-fmmhost-{uuid.uuid4().hex[:6]}"
        status, resp = _publish_source(
            FMM_HOST, FMM_PORT, "fmm", version, "fmm://fakefmm:2121/pkg.tar.gz")
        self.assertEqual(status, 201, resp)
        self.assertEqual(_download(FMM_HOST, FMM_PORT, "fmm", version), PKG)

    def test_fmm_scheme_requires_gate(self):
        # The gate: without OTA_FMM the fmm:// scheme is unsupported, so the
        # publish fails (502) rather than silently doing nothing - and the
        # standalone server's behaviour is unchanged.
        version = f"1.0.0-gate-{uuid.uuid4().hex[:6]}"
        status, resp = _publish_source(
            PLAIN_HOST, PLAIN_PORT, "fmm", version, "fmm:///builds/pkg.tar.gz")
        self.assertEqual(status, 502, resp)


if __name__ == "__main__":
    unittest.main()
