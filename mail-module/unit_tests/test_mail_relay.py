#!/usr/bin/env python3
"""
Functional tests for the DNS-routed outbound relay (src/delivery.js) - NOT
security tests. They prove the *functional* behaviour the fleet's DNSM
interconnection relies on, using a local fake resolver/MX (fakemx.py) instead of
DNSM so the suite stays hermetic and deterministic.

Two servers are exercised:
    MTA_RELAY_HOST   an MTA with MTA_RESOLVER set (relay ON) - the positive path
    MTA_HOST         an MTA with MTA_RESOLVER unset (relay OFF) - the gate

Config (env vars, all with sensible defaults for a compose run):
    MTA_HOST / MTA_ADMIN_PORT          resolver-less server (spool only)
    MTA_RELAY_HOST / MTA_RELAY_SMTP_PORT / MTA_RELAY_ADMIN_PORT   relay server
    MTA_TEST_AUTH_USER / MTA_TEST_AUTH_PASS   AUTH fixture credential

Run on the compose network:
    MTA_NO_LAUNCH=1 python3 -m unittest test_mail_relay -v
"""
import base64
import json
import os
import socket
import time
import unittest
import urllib.request
import uuid

RELAY_HOST = os.environ.get("MTA_RELAY_HOST", "mta-relay")
RELAY_SMTP_PORT = int(os.environ.get("MTA_RELAY_SMTP_PORT", "2525"))
RELAY_ADMIN_PORT = int(os.environ.get("MTA_RELAY_ADMIN_PORT", "8081"))

# The resolver-less server (the gate): reuse the same vars test_mail.py uses.
PLAIN_HOST = os.environ.get("MTA_HOST", "mta")
PLAIN_SMTP_PORT = int(os.environ.get("MTA_PORT", "2525"))
PLAIN_ADMIN_PORT = int(os.environ.get("MTA_ADMIN_PORT", "8081"))

AUTH_USER = os.environ.get("MTA_TEST_AUTH_USER", "test")
AUTH_PASS = os.environ.get("MTA_TEST_AUTH_PASS", "testpass1")


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
    if os.environ.get("MTA_NO_LAUNCH"):
        ok = (_wait_until_up(RELAY_HOST, RELAY_SMTP_PORT, 30.0)
              and _wait_until_up(PLAIN_HOST, PLAIN_SMTP_PORT, 30.0))
        if not ok:
            raise unittest.SkipTest("relay/plain MTA not reachable and MTA_NO_LAUNCH is set")
        return
    # This suite needs the fake resolver/MX sidecar wired via compose; there is
    # no meaningful single-process local launch, so skip when not on the net.
    if not _wait_until_up(RELAY_HOST, RELAY_SMTP_PORT, 2.0):
        raise unittest.SkipTest("no relay MTA reachable; run via unit_tests/docker-compose.yml")


def _submit(host, smtp_port, rcpt, authenticate=True):
    """Run one SMTP transaction; return the queued message name."""
    sock = socket.create_connection((host, smtp_port), timeout=10)
    sock.settimeout(10)

    def rd():
        time.sleep(0.1)
        return sock.recv(4096).decode(errors="replace")

    def cmd(line):
        sock.sendall((line + "\r\n").encode())
        return rd()

    rd()  # banner
    cmd("EHLO tester.local")
    if authenticate:
        creds = base64.b64encode(f"\0{AUTH_USER}\0{AUTH_PASS}".encode()).decode()
        cmd(f"AUTH PLAIN {creds}")
    cmd(f"MAIL FROM:<relay-test@tester.local>")
    cmd(f"RCPT TO:<{rcpt}>")
    cmd("DATA")
    token = uuid.uuid4().hex[:8]
    sock.sendall(f"Subject: relay-{token}\r\n\r\nbody {token}\r\n.\r\n".encode())
    reply = rd()
    cmd("QUIT")
    sock.close()
    assert "queued as" in reply, reply
    return reply.strip().split("queued as")[-1].strip()


def _queue_entry(admin_host, admin_port, name):
    body = urllib.request.urlopen(
        f"http://{admin_host}:{admin_port}/queue", timeout=10).read()
    for e in json.loads(body):
        if e["name"] == name:
            return e
    return None


def _await_delivery(admin_host, admin_port, name, timeout=20.0):
    """Poll the admin queue until the async relay records a delivery result."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        entry = _queue_entry(admin_host, admin_port, name)
        if entry is not None:
            last = entry
            if entry.get("delivery") is not None:
                return entry["delivery"]
        time.sleep(0.25)
    raise AssertionError(f"no delivery result recorded for {name} (last entry: {last})")


class RelayDeliveryTests(unittest.TestCase):
    def test_mx_route_delivers_to_next_hop(self):
        # sink.test has an MX (mx.sink.test) that the fake resolves to itself and
        # answers SMTP on :25 -> a real delivered outcome, routed by MX.
        name = _submit(RELAY_HOST, RELAY_SMTP_PORT, "bob@sink.test")
        results = _await_delivery(RELAY_HOST, RELAY_ADMIN_PORT, name)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["status"], "delivered", r)
        self.assertEqual(r["domain"], "sink.test")
        self.assertEqual(r["mxHost"], "mx.sink.test")

    def test_implicit_mx_falls_back_to_domain_a_record(self):
        # nomx.test has no MX; RFC 5321 implicit MX -> deliver to the domain's
        # own A record, which the fake also points at itself.
        name = _submit(RELAY_HOST, RELAY_SMTP_PORT, "carol@nomx.test")
        results = _await_delivery(RELAY_HOST, RELAY_ADMIN_PORT, name)
        r = results[0]
        self.assertEqual(r["status"], "delivered", r)
        self.assertEqual(r["mxHost"], "nomx.test")

    def test_unresolvable_domain_defers(self):
        # unresolv.test resolves to nothing -> no next hop -> deferred, not crash.
        name = _submit(RELAY_HOST, RELAY_SMTP_PORT, "dave@unresolv.test")
        results = _await_delivery(RELAY_HOST, RELAY_ADMIN_PORT, name)
        r = results[0]
        self.assertEqual(r["status"], "deferred", r)
        self.assertEqual(r["domain"], "unresolv.test")

    def test_local_domain_is_not_relayed(self):
        # A recipient in the server's own MTA_DOMAIN is delivered locally (spool),
        # never relayed: the delivery summary is present but empty.
        name = _submit(RELAY_HOST, RELAY_SMTP_PORT, "postmaster@mta.local")
        results = _await_delivery(RELAY_HOST, RELAY_ADMIN_PORT, name)
        self.assertEqual(results, [])


class RelayGateTests(unittest.TestCase):
    def test_resolver_unset_means_no_relay(self):
        # The opt-in gate: with MTA_RESOLVER unset the message is only spooled and
        # NO delivery result is ever attached. This is the contract that keeps the
        # standalone module (and every other module's tests) behaving as before.
        name = _submit(PLAIN_HOST, PLAIN_SMTP_PORT, "bob@sink.test")
        # Give any (non-existent) async work the same grace the positive tests get.
        time.sleep(3.0)
        entry = _queue_entry(PLAIN_HOST, PLAIN_ADMIN_PORT, name)
        self.assertIsNotNone(entry)
        self.assertIsNone(entry.get("delivery"),
                          f"resolver-less server must not relay; got {entry.get('delivery')}")


if __name__ == "__main__":
    unittest.main()
