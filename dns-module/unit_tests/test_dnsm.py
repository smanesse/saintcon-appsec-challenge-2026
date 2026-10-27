#!/usr/bin/env python3
"""
Network-based unit tests for the DNS Module (DNSM / dnsm).

These tests exercise the *basic, intended functionality* of the authoritative
DNS server described in ../README.md - A/AAAA/CNAME/TXT/NS/MX lookups over UDP,
the TCP fallback, AXFR zone transfer, recursive forwarding, NXDOMAIN handling,
and the HTTP admin side-channel (health + reload). They are functional tests,
not security tests.

Everything is driven purely over the wire (UDP/TCP DNS + HTTP admin).

Usage
-----
    python3 -m unittest test_dnsm                 # auto-launch a local server
    python3 test_dnsm.py                           # same, via unittest.main()

Point the tests at an already-running server instead of auto-launching:

    DNSM_HOST=dnsm DNSM_PORT=8053 DNSM_NO_LAUNCH=1 python3 -m unittest test_dnsm

Environment variables
---------------------
    DNSM_HOST          host to connect to (default 127.0.0.1)
    DNSM_PORT          DNS UDP/TCP port (default 8053)
    DNSM_ADMIN_PORT    admin HTTP port (default 8080)
    DNSM_BINARY        path to the server binary to launch (default ../dnsm)
    DNSM_NO_LAUNCH     if set, never launch a server - use DNSM_HOST/PORT
    DNSM_HAVE_UPSTREAM if set, run the recursive-forwarding test (an upstream
                       resolver must be reachable at DNSM_UPSTREAM)
"""
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("DNSM_HOST", "127.0.0.1")
PORT = int(os.environ.get("DNSM_PORT", "8053"))
ADMIN_PORT = int(os.environ.get("DNSM_ADMIN_PORT", "8080"))
# The admin channel requires a bearer token; legitimate callers (this harness
# included) send it as X-Admin-Token. Must match what the server is launched
# with (see setUpModule / entrypoint.sh default).
ADMIN_TOKEN = os.environ.get("DNSM_ADMIN_TOKEN", "dev-admin-token")
NO_LAUNCH = bool(os.environ.get("DNSM_NO_LAUNCH"))
HAVE_UPSTREAM = bool(os.environ.get("DNSM_HAVE_UPSTREAM"))

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_server_proc = None
_upstream_proc = None

# DNS type codes
T_A, T_NS, T_CNAME, T_MX, T_TXT, T_SOA, T_AAAA, T_AXFR = 1, 2, 5, 15, 16, 6, 28, 252


# ---------------------------------------------------------------------------
# Minimal DNS client helpers
# ---------------------------------------------------------------------------
def dns_name(n):
    return b"".join(bytes([len(l)]) + l.encode() for l in n.split(".") if l) + b"\x00"


def build_query(name, qtype, txid=0x1234, rd=True):
    flags = 0x0100 if rd else 0x0000
    return struct.pack(">HHHHHH", txid, flags, 1, 0, 0, 0) + dns_name(name) + struct.pack(">HH", qtype, 1)


def udp_query(name, qtype, timeout=4.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(build_query(name, qtype), (HOST, PORT))
        data, _ = s.recvfrom(65535)
        return data
    finally:
        s.close()


def tcp_query(name, qtype, timeout=4.0):
    msg = build_query(name, qtype)
    s = socket.create_connection((HOST, PORT), timeout=timeout)
    s.settimeout(timeout)
    try:
        s.sendall(struct.pack(">H", len(msg)) + msg)
        hdr = s.recv(2)
        ln = struct.unpack(">H", hdr)[0]
        data = b""
        while len(data) < ln:
            chunk = s.recv(ln - len(data))
            if not chunk:
                break
            data += chunk
        return data
    finally:
        s.close()


def parse_answers(msg):
    """Return (rcode, list of (type, rdata_bytes)) from a DNS response."""
    rcode = msg[3] & 0x0f
    ancount = struct.unpack(">H", msg[6:8])[0]
    # skip header + question
    pos = 12
    # question name
    while msg[pos] != 0:
        if msg[pos] & 0xC0 == 0xC0:
            pos += 2
            break
        pos += 1 + msg[pos]
    else:
        pos += 1
    pos += 4  # qtype + qclass
    out = []
    for _ in range(ancount):
        # owner name (may be compressed)
        while pos < len(msg) and msg[pos] != 0:
            if msg[pos] & 0xC0 == 0xC0:
                pos += 2
                break
            pos += 1 + msg[pos]
        else:
            pos += 1
        rtype = struct.unpack(">H", msg[pos:pos + 2])[0]
        rdlen = struct.unpack(">H", msg[pos + 8:pos + 10])[0]
        rdata = msg[pos + 10:pos + 10 + rdlen]
        out.append((rtype, rdata))
        pos += 10 + rdlen
    return rcode, out


def admin_get(path, data=None, timeout=6, token=ADMIN_TOKEN):
    url = f"http://{HOST}:{ADMIN_PORT}{path}"
    headers = {"X-Admin-Token": token} if token is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout).read().decode(errors="replace")


def primary_ip():
    """Best-effort non-loopback IPv4 address of this host.

    The import-from-URL test must serve its zone over a URL the dnsm process
    will actually fetch. A hardened dnsm may refuse loopback / link-local /
    0.0.0.0 fetch targets, so a localhost URL could be rejected even though this
    is a legitimate fetch. We need a non-loopback address the fetch filter allows
    and that dnsm can reach whether it runs as a peer container (the grader /
    docker-compose suite) or as a local subprocess.

    Strategy, in order of robustness, returning the first non-loopback IPv4:
      1. gethostbyname(gethostname()). Inside a container, /etc/hosts maps the
         hostname to the container's own eth0 (an RFC1918 IP dnsm can reach over
         the compose network) and needs no routing. This is the grader path.
      2. UDP-connect to a public IP and read the chosen source address. Works on
         a dev host with a default route (local-subprocess mode, where #1 often
         yields 127.0.1.1). Guarded: an isolated/no-egress network makes connect
         raise 'Network is unreachable', so we must not depend on it.
      3. Scan getaddrinfo(gethostname()) for any non-loopback IPv4.
    No packet is actually sent by connect() on a UDP socket.
    """
    def _usable(ip):
        return bool(ip) and not ip.startswith("127.") and ip != "0.0.0.0"

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if _usable(ip):
            return ip
    except OSError:
        pass

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if _usable(ip):
            return ip
    except OSError:
        pass
    finally:
        s.close()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _usable(ip):
                return ip
    except OSError:
        pass

    raise RuntimeError("no non-loopback IPv4 address found for the import-URL test")


# ---------------------------------------------------------------------------
# Launch / teardown
# ---------------------------------------------------------------------------
def _wait_ready(timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            admin_get("/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def setUpModule():
    global _server_proc, _upstream_proc
    if NO_LAUNCH:
        if not _wait_ready():
            raise RuntimeError("DNSM not reachable and DNSM_NO_LAUNCH set")
        return

    binary = os.environ.get("DNSM_BINARY", os.path.join(PROJECT_ROOT, "dnsm"))
    if not os.path.exists(binary):
        raise RuntimeError(f"server binary not found at {binary}; run `make` first")

    env = dict(os.environ)
    env.update(DNSM_PORT=str(PORT), DNSM_ADMIN_PORT=str(ADMIN_PORT),
               DNSM_ZONE_FILE="./zones/example.zone", DNSM_ZONE_DIR="./zones",
               DNSM_ADMIN_TOKEN=ADMIN_TOKEN)
    _server_proc = subprocess.Popen([binary], cwd=PROJECT_ROOT, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not _wait_ready():
        raise RuntimeError("locally-launched DNSM did not become ready")


def tearDownModule():
    for p in (_server_proc, _upstream_proc):
        if p:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestAuthoritativeLookups(unittest.TestCase):
    def test_a_record(self):
        rcode, ans = parse_answers(udp_query("www.example.com", T_A))
        self.assertEqual(rcode, 0)
        ips = [socket.inet_ntoa(rd) for t, rd in ans if t == T_A]
        self.assertIn("192.0.2.10", ips)

    def test_aaaa_record(self):
        rcode, ans = parse_answers(udp_query("www.example.com", T_AAAA))
        self.assertEqual(rcode, 0)
        v6 = [socket.inet_ntop(socket.AF_INET6, rd) for t, rd in ans if t == T_AAAA]
        self.assertTrue(any(a.endswith("db8::10") or a == "2001:db8::10" for a in v6))

    def test_txt_record(self):
        _, ans = parse_answers(udp_query("info.example.com", T_TXT))
        blob = b"".join(rd for t, rd in ans if t == T_TXT)
        self.assertIn(b"SAINTCON AppSec DNS module", blob)

    def test_mx_record(self):
        _, ans = parse_answers(udp_query("example.com", T_MX))
        self.assertTrue(any(t == T_MX for t, _ in ans))

    def test_ns_record(self):
        _, ans = parse_answers(udp_query("example.com", T_NS))
        self.assertGreaterEqual(sum(1 for t, _ in ans if t == T_NS), 2)

    def test_cname_is_followed(self):
        # ftp is a CNAME to www; an A query should return the CNAME AND the A.
        _, ans = parse_answers(udp_query("ftp.example.com", T_A))
        types = [t for t, _ in ans]
        self.assertIn(T_CNAME, types)
        self.assertIn(T_A, types)

    def test_nxdomain(self):
        rcode, ans = parse_answers(udp_query("nope.example.com", T_A))
        self.assertEqual(rcode, 3)
        self.assertEqual(ans, [])


class TestTransport(unittest.TestCase):
    def test_tcp_fallback(self):
        rcode, ans = parse_answers(tcp_query("www.example.com", T_A))
        self.assertEqual(rcode, 0)
        ips = [socket.inet_ntoa(rd) for t, rd in ans if t == T_A]
        self.assertIn("192.0.2.10", ips)

    def test_axfr_transfer(self):
        msg = tcp_query("example.com", T_AXFR)
        rcode, ans = parse_answers(msg)
        self.assertEqual(rcode, 0)
        # A real AXFR carries the whole zone, not just a fabricated count.
        # Assert the actual transferred records, so a server that only inflates
        # ANCOUNT (or returns filler RRs) can't pass:
        #   - RFC 5936: the stream must be bookended by the zone's SOA.
        #   - the zone's own data must be present (the same A record the
        #     authoritative-lookup tests rely on), proving the real zone was
        #     serialized, not padding.
        self.assertGreater(len(ans), 10)
        self.assertEqual(ans[0][0], T_SOA, "AXFR must start with SOA")
        self.assertEqual(ans[-1][0], T_SOA, "AXFR must end with SOA")
        a_ips = {socket.inet_ntoa(rd) for t, rd in ans if t == T_A and len(rd) == 4}
        self.assertIn("192.0.2.10", a_ips)


class TestAdmin(unittest.TestCase):
    def test_health(self):
        self.assertIn("ok", admin_get("/health"))

    def test_reload(self):
        out = admin_get("/admin/reload", data=b"")
        self.assertIn("reloaded", out)

    def test_zone_read(self):
        # GET /zone?name=<name> is a public (no-token) transparency endpoint
        # that returns the text of a zone file under DNSM_ZONE_DIR.
        out = admin_get("/zone?name=example.zone", token=None)
        self.assertIn("$ORIGIN example.com.", out)
        self.assertIn("www", out)

    def test_zone_read_missing_name(self):
        # /zone with no name= is a client error, not a server read.
        with self.assertRaises(urllib.error.HTTPError) as cm:
            admin_get("/zone", token=None)
        self.assertEqual(cm.exception.code, 400)

    def test_zone_read_wrong_method(self):
        # /zone is read-only; a POST is rejected.
        with self.assertRaises(urllib.error.HTTPError) as cm:
            admin_get("/zone?name=example.zone", data=b"", token=None)
        self.assertEqual(cm.exception.code, 405)

    def test_import_from_file(self):
        # /admin/import?path=<name> reads a zone file from DNSM_ZONE_DIR and
        # merges it into the running zone (zone_clone_plus keeps the existing
        # records and appends the newly parsed ones). Each import of the same
        # file adds a constant number of records (the file's own record count),
        # so two successive imports grow the count by the same delta.
        base = int(re.search(r"reloaded (\d+) records", admin_get("/admin/reload", data=b"")).group(1))
        a = int(re.search(r"\((\d+) records total\)", admin_get("/admin/import?path=example.zone")).group(1))
        b = int(re.search(r"\((\d+) records total\)", admin_get("/admin/import?path=example.zone")).group(1))
        self.assertEqual(a - base, b - a, f"import delta not constant: base={base} a={a} b={b}")
        self.assertGreater(a, base)
        # The merged zone is still functionally correct afterward.
        rcode, ans = parse_answers(udp_query("www.example.com", T_A))
        self.assertEqual(rcode, 0)
        ips = [socket.inet_ntoa(rd) for t, rd in ans if t == T_A]
        self.assertIn("192.0.2.10", ips)

    def test_import_inline_body(self):
        # POST /admin/import with a zone-text body merges it directly, no
        # source_url or path involved.
        name = f"admin-body-{uuid.uuid4().hex[:8]}"
        body = f"{name} A 203.0.113.5\n".encode()
        out = admin_get("/admin/import", data=body)
        self.assertIn("imported inline body", out)
        rcode, ans = parse_answers(udp_query(f"{name}.example.com", T_A))
        self.assertEqual(rcode, 0)
        ips = [socket.inet_ntoa(rd) for t, rd in ans if t == T_A]
        self.assertIn("203.0.113.5", ips)

    def test_import_from_url(self):
        # /admin/import?source_url=<url> fetches zone text over HTTP and
        # merges it. Serve it from this test process itself: here the response
        # is trusted zone data proving the *intended* ops workflow. The URL
        # uses primary_ip() (not localhost/gethostname) so a hardened dnsm that
        # blocks loopback fetch targets still accepts this legitimate import.
        name = f"admin-url-{uuid.uuid4().hex[:8]}"
        body = f"{name} A 203.0.113.6\n".encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://{primary_ip()}:{port}/zone"
            out = admin_get(f"/admin/import?source_url={url}")
            self.assertIn("imported from", out)
        finally:
            server.shutdown()
            server.server_close()

        rcode, ans = parse_answers(udp_query(f"{name}.example.com", T_A))
        self.assertEqual(rcode, 0)
        ips = [socket.inet_ntoa(rd) for t, rd in ans if t == T_A]
        self.assertIn("203.0.113.6", ips)


class TestForwarding(unittest.TestCase):
    def test_recursive_forward(self):
        if not HAVE_UPSTREAM:
            self.skipTest("no upstream configured (set DNSM_HAVE_UPSTREAM)")
        rcode, ans = parse_answers(udp_query("host.outside.test", T_A))
        ips = [socket.inet_ntoa(rd) for t, rd in ans if t == T_A]
        self.assertIn("10.0.0.5", ips)


if __name__ == "__main__":
    unittest.main()
