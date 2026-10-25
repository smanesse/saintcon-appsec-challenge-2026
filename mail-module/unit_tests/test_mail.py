#!/usr/bin/env python3
"""
Functional tests for the MTA mail relay - NOT security tests. These drive
the documented SMTP protocol (README.md): HELO/EHLO, MAIL FROM, RCPT TO,
DATA, RSET, NOOP, AUTH, STARTTLS, QUIT, plus the admin HTTP queue-viewer -
covering the golden path and the documented error replies.

Configuration (env vars):
    MTA_HOST         SMTP host to connect to (default 127.0.0.1)
    MTA_PORT         SMTP port to connect to (default 2525)
    MTA_ADMIN_PORT   admin HTTP port (default 8081)
    MTA_NO_LAUNCH    if set, never launch a server - connect to MTA_HOST/PORT
    MTA_TEST_AUTH_USER / MTA_TEST_AUTH_PASS
                     credential this test suite uses to exercise AUTH
                     (defaults to a throwaway test/testpass1 pair; the
                     compose fixture sets MTA_AUTH_USER/MTA_AUTH_PASS to
                     match - this is deliberately NOT the shipped default)

Run against an already-running server (e.g. a container on the compose net):
    MTA_HOST=mta MTA_NO_LAUNCH=1 python3 -m unittest test_mail -v
"""
import base64
import os
import socket
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import uuid

HOST = os.environ.get("MTA_HOST", "127.0.0.1")
PORT = int(os.environ.get("MTA_PORT", "2525"))
ADMIN_PORT = int(os.environ.get("MTA_ADMIN_PORT", "8081"))
TEST_AUTH_USER = os.environ.get("MTA_TEST_AUTH_USER", "test")
TEST_AUTH_PASS = os.environ.get("MTA_TEST_AUTH_PASS", "testpass1")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_server_proc = None


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


def setUpModule():
    global _server_proc
    if _server_is_up(HOST, PORT):
        return
    if os.environ.get("MTA_NO_LAUNCH"):
        if _wait_until_up(HOST, PORT, 30.0):
            return
        raise unittest.SkipTest(f"No server on {HOST}:{PORT} and MTA_NO_LAUNCH is set")
    env = dict(os.environ)
    env["MTA_PORT"] = str(PORT)
    env["MTA_ADMIN_PORT"] = str(ADMIN_PORT)
    env["MTA_AUTH_USER"] = TEST_AUTH_USER
    env["MTA_AUTH_PASS"] = TEST_AUTH_PASS
    try:
        _server_proc = subprocess.Popen(
            ["node", "src/server.js"], cwd=PROJECT_ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise unittest.SkipTest("No running server and no local `node` to launch one")
    if not _wait_until_up(HOST, PORT, 10.0):
        raise unittest.SkipTest(f"Server did not come up on {HOST}:{PORT}")


def tearDownModule():
    global _server_proc
    if _server_proc is not None:
        _server_proc.terminate()
        try:
            _server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _server_proc.kill()
        _server_proc = None


class SmtpClient:
    """Tiny line-oriented SMTP client for the tests below."""

    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(10)
        self.banner = self._read_reply()

    def _read_reply(self):
        buf = b""
        while True:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            # A multi-line reply's final line has a space after the code;
            # continuation lines use '-'. Stop once we see that.
            lines = buf.split(b"\r\n")
            # last element may be empty (trailing \r\n) or a partial line
            complete = [l for l in lines if l]
            if complete and len(complete[-1]) >= 4 and complete[-1][3:4] != b"-":
                if buf.endswith(b"\r\n"):
                    break
        return buf.decode(errors="replace")

    def cmd(self, line):
        self.sock.sendall((line + "\r\n").encode())
        return self._read_reply()

    def auth_plain(self, user, password):
        """SASL PLAIN with an initial response; returns the server's reply."""
        creds = base64.b64encode(f"\0{user}\0{password}".encode()).decode()
        return self.cmd(f"AUTH PLAIN {creds}")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class BasicProtocolTests(unittest.TestCase):
    def test_banner(self):
        c = SmtpClient(HOST, PORT)
        self.assertTrue(c.banner.startswith("220 "))
        c.close()

    def test_helo(self):
        c = SmtpClient(HOST, PORT)
        r = c.cmd("HELO client.example.com")
        self.assertTrue(r.startswith("250 "))
        c.close()

    def test_ehlo_lists_extensions(self):
        c = SmtpClient(HOST, PORT)
        r = c.cmd("EHLO client.example.com")
        self.assertTrue(r.startswith("250-") or r.startswith("250 "))
        self.assertIn("STARTTLS", r)
        self.assertIn("AUTH", r)
        c.close()

    def test_unknown_command(self):
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        r = c.cmd("BOGUSVERB")
        self.assertTrue(r.startswith("502"))
        c.close()

    def test_rcpt_before_mail_from_is_bad_sequence(self):
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        r = c.cmd("RCPT TO:<bob@example.com>")
        self.assertTrue(r.startswith("503"))
        c.close()

    def test_data_before_rcpt_is_bad_sequence(self):
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        c.cmd("MAIL FROM:<alice@example.com>")
        r = c.cmd("DATA")
        self.assertTrue(r.startswith("503"))
        c.close()

    def test_rcpt_bad_syntax(self):
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        c.cmd("MAIL FROM:<alice@example.com>")
        r = c.cmd("RCPT TO:not-an-address")
        self.assertTrue(r.startswith("501"))
        c.close()

    def test_rset_clears_envelope(self):
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        c.cmd("MAIL FROM:<alice@example.com>")
        r = c.cmd("RSET")
        self.assertTrue(r.startswith("250"))
        r = c.cmd("RCPT TO:<bob@example.com>")
        self.assertTrue(r.startswith("503"))
        c.close()

    def test_noop(self):
        c = SmtpClient(HOST, PORT)
        r = c.cmd("NOOP")
        self.assertTrue(r.startswith("250"))
        c.close()

    def test_quit(self):
        c = SmtpClient(HOST, PORT)
        r = c.cmd("QUIT")
        self.assertTrue(r.startswith("221"))
        c.close()


class DeliveryTests(unittest.TestCase):
    def _deliver(self, c, mail_from, rcpt_to, subject, body):
        c.cmd(f"MAIL FROM:<{mail_from}>")
        c.cmd(f"RCPT TO:<{rcpt_to}>")
        r = c.cmd("DATA")
        self.assertTrue(r.startswith("354"))
        r = c.cmd(f"Subject: {subject}\r\n\r\n{body}\r\n.")
        return r

    def test_relay_to_foreign_domain_is_accepted(self):
        # Functional behaviour: an *authenticated* client relays outbound, so
        # RCPT TO an entirely different domain than MTA_DOMAIN succeeds. We
        # authenticate first on purpose: the intended open-relay fix is to
        # require AUTH before relaying off-domain, so a correct fix must keep
        # this (submission-with-credentials) path working. A test that relayed
        # a foreign domain with no AUTH would instead be pinning the vuln, and
        # would break the moment someone closes the open relay.
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        self.assertTrue(c.auth_plain(TEST_AUTH_USER, TEST_AUTH_PASS).startswith("235"))
        token = uuid.uuid4().hex[:8]
        r = self._deliver(c, "alice@example.com", "someone@a-different-domain.example",
                           f"unit-test-{token}", "hello")
        self.assertTrue(r.startswith("250"))
        self.assertIn("queued as", r)
        c.close()

    def test_queued_message_appears_in_admin_queue(self):
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        # Authenticate before relaying off-domain, same reasoning as above: the
        # queue-visibility behaviour must survive closing the open relay.
        self.assertTrue(c.auth_plain(TEST_AUTH_USER, TEST_AUTH_PASS).startswith("235"))
        token = uuid.uuid4().hex[:8]
        subject = f"unit-test-{token}"
        r = self._deliver(c, "alice@example.com", "bob@somewhere.example", subject, "hello there")
        c.close()
        name = r.strip().split("queued as")[-1].strip()

        body = urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue", timeout=10).read()
        import json
        entries = json.loads(body)
        match = [e for e in entries if e["name"] == name]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["from"], "alice@example.com")
        self.assertIn("bob@somewhere.example", match[0]["to"])
        self.assertEqual(match[0]["subject"], subject)

        detail = json.loads(urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue/{name}", timeout=10).read())
        self.assertIn("hello there", detail["raw"])


class AdminApiTests(unittest.TestCase):
    def test_health(self):
        body = urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/health", timeout=10).read()
        self.assertIn(b"ok", body)

    def test_unknown_message_is_404(self):
        try:
            urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue/does-not-exist.eml", timeout=10)
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


class BounceTests(unittest.TestCase):
    def test_unknown_local_recipient_fires_bounce_notification(self):
        # A message to a non-existent mailbox in the server's OWN domain
        # (MTA_DOMAIN) is accepted without auth (local inbound) and fires the
        # delivery-failure notify hook, which appends a line to the bounce log
        # exposed read-only at the admin /bounces endpoint. This pins the
        # bounce-notify feature as real, intended behaviour the fix must
        # preserve: the hardened hook runs the notify script with an argument
        # vector (execFile) instead of a shell command string, so a correct
        # fix keeps the notification firing while a "fix" that simply drops the
        # hook is caught here. The sender/recipient are deliberately benign (no
        # shell metacharacters), so this is a pure functional check that passes
        # on both the vulnerable and the fixed code.
        token = uuid.uuid4().hex[:12]
        sender = f"bouncer-{token}@example.com"
        rcpt = f"nosuchuser-{token}@mta.local"

        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        c.cmd(f"MAIL FROM:<{sender}>")
        r = c.cmd(f"RCPT TO:<{rcpt}>")
        # Local-domain delivery is accepted from anyone, no AUTH required.
        self.assertTrue(r.startswith("250"), r)
        r = c.cmd("DATA")
        self.assertTrue(r.startswith("354"), r)
        r = c.cmd(f"Subject: bounce-{token}\r\n\r\nno mailbox here\r\n.")
        self.assertTrue(r.startswith("250"), r)
        c.close()

        # The notify hook runs asynchronously (the script is spawned after the
        # message is queued), so poll the admin bounce log for our marker.
        deadline = time.time() + 10
        log = ""
        while time.time() < deadline:
            log = urllib.request.urlopen(
                f"http://{HOST}:{ADMIN_PORT}/bounces", timeout=10).read().decode(errors="replace")
            if token in log:
                break
            time.sleep(0.25)
        self.assertIn(token, log,
                      "bounce-notify hook did not record the undeliverable recipient")
        self.assertIn(rcpt, log)
        self.assertIn(sender, log)


class AuthAndTlsTests(unittest.TestCase):
    def test_auth_plain_wrong_credentials_rejected(self):
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        bogus = base64.b64encode(b"\0nobody\0wrongpass").decode()
        r = c.cmd(f"AUTH PLAIN {bogus}")
        self.assertTrue(r.startswith("535"))
        c.close()

    def test_auth_plain_correct_credentials_succeeds(self):
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        creds = base64.b64encode(f"\0{TEST_AUTH_USER}\0{TEST_AUTH_PASS}".encode()).decode()
        r = c.cmd(f"AUTH PLAIN {creds}")
        self.assertTrue(r.startswith("235"), r)
        c.close()

    def test_starttls_handshake_succeeds(self):
        import ssl
        c = SmtpClient(HOST, PORT)
        c.cmd("EHLO client.example.com")
        r = c.cmd("STARTTLS")
        self.assertTrue(r.startswith("220"))
        ctx = ssl._create_unverified_context()
        tls_sock = ctx.wrap_socket(c.sock, server_hostname=HOST)
        tls_sock.sendall(b"EHLO client.example.com\r\n")
        tls_sock.settimeout(10)
        reply = tls_sock.recv(4096).decode(errors="replace")
        self.assertTrue(reply.startswith("250"))
        tls_sock.close()


if __name__ == "__main__":
    unittest.main()
