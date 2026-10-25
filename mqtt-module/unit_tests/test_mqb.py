#!/usr/bin/env python3
"""
Functional tests for MQB, the MQTT 3.1.1 broker -- NOT security tests. These
drive the documented wire protocol from README.md (CONNECT/CONNACK, PUBLISH,
SUBSCRIBE/SUBACK, UNSUBSCRIBE/UNSUBACK, PINGREQ/PINGRESP, DISCONNECT, QoS 0/1,
retained messages, +/# wildcards) and check the golden path plus the
documented error/edge-case replies.

Configuration (env vars):
    MQB_HOST         host to connect to (default 127.0.0.1)
    MQB_PORT         MQTT port to connect to (default 1883)
    MQB_ADMIN_PORT   admin HTTP port to connect to (default 8081)
    MQB_NO_LAUNCH    if set, never launch a server -- connect to MQB_HOST/PORT

Run against an already-running server (e.g. a container on the compose net):
    MQB_HOST=mqb MQB_PORT=1883 MQB_NO_LAUNCH=1 python3 -m unittest test_mqb -v

Or let it launch a local copy (runs `python3 -m mqb.server` from the module root):
    python3 -m unittest test_mqb -v
"""
import http.client
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

HOST = os.environ.get("MQB_HOST", "127.0.0.1")
PORT = int(os.environ.get("MQB_PORT", "1883"))
ADMIN_PORT = int(os.environ.get("MQB_ADMIN_PORT", "8081"))
# Set by a harness that generated a real credential (see
# ../../generate-secrets.sh); None means "no auth configured", matching
# today's default and requiring no local setup.
PASSWORD = os.environ.get("MQB_REQUIREPASS") or None
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_server_proc = None
_server_tmpdir = None


# ---------------------------------------------------------------------------
# Minimal hand-rolled MQTT 3.1.1 client (independent of mqb/packet.py on
# purpose -- these tests should catch a broker-side regression, not just
# agree with whatever the broker's own encoder currently does).
# ---------------------------------------------------------------------------

CONNACK, PUBLISH, PUBACK, SUBACK, UNSUBACK, PINGRESP = 2, 3, 4, 9, 11, 13


def _u8(s):
    b = s.encode()
    return struct.pack("!H", len(b)) + b


def _rl(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n > 0:
            b |= 0x80
        out.append(b)
        if n == 0:
            break
    return bytes(out)


class Client:
    def __init__(self, host, port, client_id=None, clean_session=1, keep_alive=30,
                 username=None, password=None, will=None, connect=True):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.client_id = client_id or ("test-" + uuid.uuid4().hex[:12])
        # Remembered so a later bare `.connect()` (the connect=False path,
        # used whenever a test wants to build the packet itself) still picks
        # up credentials passed to the constructor -- otherwise they're
        # silently dropped instead of applied.
        self._default_username = username
        self._default_password = password
        self._default_will = will
        if connect:
            self.connect(clean_session, keep_alive, username, password, will)

    def connect(self, clean_session=1, keep_alive=30, username=None, password=None, will=None):
        if username is None:
            username = self._default_username
        if password is None:
            password = self._default_password
        if will is None:
            will = self._default_will
        flags = (clean_session & 1) << 1
        if will:
            will_topic, will_message, will_qos, will_retain = will
            flags |= 0x04 | ((will_qos & 3) << 3) | ((1 if will_retain else 0) << 5)
        if username is not None:
            flags |= 0x80
        if password is not None:
            flags |= 0x40
        body = _u8("MQTT") + bytes([4, flags]) + struct.pack("!H", keep_alive) + _u8(self.client_id)
        if will:
            will_topic, will_message, will_qos, will_retain = will
            body += _u8(will_topic)
            wm = will_message.encode() if isinstance(will_message, str) else will_message
            body += struct.pack("!H", len(wm)) + wm
        if username is not None:
            body += _u8(username)
        if password is not None:
            pb = password.encode() if isinstance(password, str) else password
            body += struct.pack("!H", len(pb)) + pb
        pkt = bytes([0x10]) + _rl(len(body)) + body
        self.sock.sendall(pkt)
        return self.read_packet()

    def publish(self, topic, payload, qos=0, retain=0, packet_id=1):
        if isinstance(payload, str):
            payload = payload.encode()
        flags = (qos & 3) << 1 | (retain & 1)
        body = _u8(topic)
        if qos > 0:
            body += struct.pack("!H", packet_id)
        body += payload
        self.sock.sendall(bytes([0x30 | flags]) + _rl(len(body)) + body)

    def puback(self, packet_id):
        self.sock.sendall(bytes([0x40, 0x02]) + struct.pack("!H", packet_id))

    def subscribe(self, filters, packet_id=1):
        body = struct.pack("!H", packet_id)
        for f, q in filters:
            body += _u8(f) + bytes([q])
        self.sock.sendall(bytes([0x82]) + _rl(len(body)) + body)
        return self.read_packet()

    def unsubscribe(self, filters, packet_id=1):
        body = struct.pack("!H", packet_id)
        for f in filters:
            body += _u8(f)
        self.sock.sendall(bytes([0xA2]) + _rl(len(body)) + body)
        return self.read_packet()

    def pingreq(self):
        self.sock.sendall(bytes([0xC0, 0x00]))
        return self.read_packet()

    def disconnect(self):
        self.sock.sendall(bytes([0xE0, 0x00]))

    def read_packet(self, timeout=5.0):
        self.sock.settimeout(timeout)
        first = self.sock.recv(1)
        if not first:
            return None
        ptype = first[0] >> 4
        flags = first[0] & 0x0F
        mult, val = 1, 0
        while True:
            b = self.sock.recv(1)[0]
            val += (b & 0x7F) * mult
            if not (b & 0x80):
                break
            mult *= 128
        body = b""
        while len(body) < val:
            chunk = self.sock.recv(val - len(body))
            if not chunk:
                break
            body += chunk
        return ptype, flags, body

    def read_publish(self, timeout=5.0):
        r = self.read_packet(timeout)
        if r is None or r[0] != PUBLISH:
            return None
        ptype, flags, body = r
        qos = (flags >> 1) & 0x03
        offset = 2 + struct.unpack_from("!H", body, 0)[0]
        topic = body[2:offset].decode()
        packet_id = None
        if qos > 0:
            packet_id = struct.unpack_from("!H", body, offset)[0]
            offset += 2
        return topic, body[offset:], qos, packet_id

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


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
    global _server_proc, _server_tmpdir
    if _server_is_up(HOST, PORT):
        return
    if os.environ.get("MQB_NO_LAUNCH"):
        if _wait_until_up(HOST, PORT, 30.0):
            return
        raise unittest.SkipTest(f"No server on {HOST}:{PORT} and MQB_NO_LAUNCH is set")
    _server_tmpdir = tempfile.mkdtemp(prefix="mqb_test_")
    env = dict(os.environ)
    env["MQB_PORT"] = str(PORT)
    env["MQB_ADMIN_PORT"] = str(ADMIN_PORT)
    env["MQB_RETAIN_DIR"] = _server_tmpdir
    env["PYTHONUNBUFFERED"] = "1"
    _server_proc = subprocess.Popen(
        [sys.executable, "-m", "mqb.server"], cwd=PROJECT_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if _server_proc.poll() is not None:
            raise unittest.SkipTest("Server exited during startup")
        if _server_is_up(HOST, PORT):
            return
        time.sleep(0.1)
    raise unittest.SkipTest(f"Server did not come up on {HOST}:{PORT}")


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
        import shutil
        shutil.rmtree(_server_tmpdir, ignore_errors=True)
        _server_tmpdir = None


class MQBTestCase(unittest.TestCase):
    def setUp(self):
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()

    def new_client(self, **kwargs):
        kwargs.setdefault("password", PASSWORD)
        c = Client(HOST, PORT, connect=False, **kwargs)
        self.clients.append(c)
        return c

    def topic(self, *parts):
        return "/".join(["test", uuid.uuid4().hex[:8], *parts])


class ConnectTests(MQBTestCase):
    def test_connect_accepted(self):
        c = self.new_client()
        ptype, flags, body = c.connect()
        self.assertEqual(ptype, CONNACK)
        self.assertEqual(body[1], 0, "expected CONNACK return code 0 (accepted)")

    def test_connect_session_present_false_for_clean_session(self):
        c = self.new_client(client_id="conn-test-" + uuid.uuid4().hex[:8])
        ptype, flags, body = c.connect(clean_session=1)
        self.assertEqual(body[0], 0)

    @staticmethod
    def _password_flag_and_suffix():
        """Flag bit + payload suffix to append a password field to a
        hand-built CONNECT packet below, honoring the same harness-provided
        PASSWORD as Client -- otherwise these bypass it entirely (they write
        straight to the socket) and would misreport an unrelated auth
        rejection as a protocol/client-id failure once auth is required."""
        if PASSWORD is None:
            return 0, b""
        pb = PASSWORD.encode()
        return 0x40, struct.pack("!H", len(pb)) + pb

    def test_connect_bad_protocol_version_rejected(self):
        c = self.new_client()
        pw_flag, pw_suffix = self._password_flag_and_suffix()
        # Hand-build a CONNECT with protocol level 3 instead of 4.
        body = (_u8("MQTT") + bytes([3, 0x02 | pw_flag]) + struct.pack("!H", 30)
                + _u8("badver-client") + pw_suffix)
        c.sock.sendall(bytes([0x10]) + _rl(len(body)) + body)
        ptype, flags, rbody = c.read_packet()
        self.assertEqual(ptype, CONNACK)
        self.assertEqual(rbody[1], 1, "expected CONNACK rc=1 (unacceptable protocol version)")

    def test_empty_client_id_rejected_when_not_clean_session(self):
        c = self.new_client()
        pw_flag, pw_suffix = self._password_flag_and_suffix()
        body = _u8("MQTT") + bytes([4, 0x00 | pw_flag]) + struct.pack("!H", 30) + _u8("") + pw_suffix
        c.sock.sendall(bytes([0x10]) + _rl(len(body)) + body)
        ptype, flags, rbody = c.read_packet()
        self.assertEqual(ptype, CONNACK)
        self.assertEqual(rbody[1], 2, "expected CONNACK rc=2 (identifier rejected)")

    def test_empty_client_id_assigned_when_clean_session(self):
        c = self.new_client()
        pw_flag, pw_suffix = self._password_flag_and_suffix()
        body = _u8("MQTT") + bytes([4, 0x02 | pw_flag]) + struct.pack("!H", 30) + _u8("") + pw_suffix
        c.sock.sendall(bytes([0x10]) + _rl(len(body)) + body)
        ptype, flags, rbody = c.read_packet()
        self.assertEqual(ptype, CONNACK)
        self.assertEqual(rbody[1], 0)

    # The two negative-auth cases below are the documented complement of the
    # accepted-CONNECT tests: per README, CONNACK rc=4 ("bad username or
    # password") is returned *only when* MQB_REQUIREPASS is set. They only
    # run when a harness has actually configured a credential (PASSWORD is
    # not None); with no auth configured -- today's default and the standard
    # local run -- there is nothing to reject, so they skip. Beyond checking
    # the documented reply, they keep the suite honest once someone "enforces
    # auth" to fix the no-auth-by-default vuln: the accepted-CONNECT tests all
    # authenticate with the *configured* password, so a real enforce-auth fix
    # keeps them green, but a fake one that simply accepts every CONNECT (or
    # only compares when a password happens to be supplied -- a fail-open
    # gate) would sail past those and is caught here instead.
    def test_wrong_password_rejected_when_auth_required(self):
        if PASSWORD is None:
            self.skipTest("no MQB_REQUIREPASS configured; broker enforces no auth")
        c = self.new_client()
        ptype, flags, body = c.connect(password=PASSWORD + "-wrong")
        self.assertEqual(ptype, CONNACK)
        self.assertEqual(body[1], 4, "expected CONNACK rc=4 (bad username or password)")

    def test_missing_password_rejected_when_auth_required(self):
        if PASSWORD is None:
            self.skipTest("no MQB_REQUIREPASS configured; broker enforces no auth")
        c = self.new_client()
        # Build a CONNECT with NO password field at all -- a fail-open gate
        # that only checks a password when one is present would wrongly
        # accept this.
        body = _u8("MQTT") + bytes([4, 0x02]) + struct.pack("!H", 30) + _u8("noauth-client")
        c.sock.sendall(bytes([0x10]) + _rl(len(body)) + body)
        ptype, flags, rbody = c.read_packet()
        self.assertEqual(ptype, CONNACK)
        self.assertEqual(rbody[1], 4, "expected CONNACK rc=4 (bad username or password)")


class PubSubTests(MQBTestCase):
    def test_publish_qos0_delivered_to_subscriber(self):
        sub = self.new_client()
        sub.connect()
        topic = self.topic("qos0")
        ptype, _, _ = sub.subscribe([(topic, 0)])
        self.assertEqual(ptype, SUBACK)

        pub = self.new_client()
        pub.connect()
        pub.publish(topic, "hello-qos0", qos=0)

        got = sub.read_publish(timeout=3)
        self.assertIsNotNone(got)
        rtopic, payload, qos, packet_id = got
        self.assertEqual(rtopic, topic)
        self.assertEqual(payload, b"hello-qos0")
        self.assertEqual(qos, 0)
        self.assertIsNone(packet_id)

    def test_publish_qos1_gets_puback_and_delivers_with_packet_id(self):
        sub = self.new_client()
        sub.connect()
        topic = self.topic("qos1")
        sub.subscribe([(topic, 1)])

        pub = self.new_client()
        pub.connect()
        pub.publish(topic, "hello-qos1", qos=1, packet_id=77)
        ptype, _, body = pub.read_packet()
        self.assertEqual(ptype, PUBACK)
        self.assertEqual(struct.unpack("!H", body)[0], 77)

        rtopic, payload, qos, packet_id = sub.read_publish(timeout=3)
        self.assertEqual(rtopic, topic)
        self.assertEqual(payload, b"hello-qos1")
        self.assertEqual(qos, 1)
        self.assertIsNotNone(packet_id)
        sub.puback(packet_id)

    def test_suback_return_code_matches_requested_qos(self):
        c = self.new_client()
        c.connect()
        topic = self.topic("suback")
        ptype, _, body = c.subscribe([(topic, 1)])
        self.assertEqual(ptype, SUBACK)
        self.assertEqual(body[2], 1)

    def test_unsubscribe_stops_delivery(self):
        sub = self.new_client()
        sub.connect()
        topic = self.topic("unsub")
        sub.subscribe([(topic, 0)])
        ptype, _, _ = sub.unsubscribe([topic])
        self.assertEqual(ptype, UNSUBACK)

        pub = self.new_client()
        pub.connect()
        pub.publish(topic, "should-not-arrive", qos=0)

        sub.sock.settimeout(1.0)
        with self.assertRaises(socket.timeout):
            sub.read_publish(timeout=1.0)

    def test_plus_wildcard_matches_one_level(self):
        sub = self.new_client()
        sub.connect()
        base = self.topic("plus")
        sub.subscribe([(f"{base}/+/state", 0)])

        pub = self.new_client()
        pub.connect()
        pub.publish(f"{base}/device1/state", "on", qos=0)

        rtopic, payload, _, _ = sub.read_publish(timeout=3)
        self.assertEqual(rtopic, f"{base}/device1/state")
        self.assertEqual(payload, b"on")

    def test_plus_wildcard_does_not_match_multiple_levels(self):
        sub = self.new_client()
        sub.connect()
        base = self.topic("plusdeep")
        sub.subscribe([(f"{base}/+/state", 0)])

        pub = self.new_client()
        pub.connect()
        pub.publish(f"{base}/device1/nested/state", "should-not-match", qos=0)

        sub.sock.settimeout(1.0)
        with self.assertRaises(socket.timeout):
            sub.read_publish(timeout=1.0)

    def test_hash_wildcard_matches_all_remaining_levels(self):
        sub = self.new_client()
        sub.connect()
        base = self.topic("hash")
        sub.subscribe([(f"{base}/#", 0)])

        pub = self.new_client()
        pub.connect()
        pub.publish(f"{base}/a/b/c", "deep", qos=0)

        rtopic, payload, _, _ = sub.read_publish(timeout=3)
        self.assertEqual(rtopic, f"{base}/a/b/c")
        self.assertEqual(payload, b"deep")


class RetainedMessageTests(MQBTestCase):
    def test_retained_message_delivered_on_subscribe(self):
        topic = self.topic("retained")
        pub = self.new_client()
        pub.connect()
        pub.publish(topic, "sticky-value", qos=0, retain=1)
        time.sleep(0.2)

        sub = self.new_client()
        sub.connect()
        sub.subscribe([(topic, 0)])

        rtopic, payload, _, _ = sub.read_publish(timeout=3)
        self.assertEqual(rtopic, topic)
        self.assertEqual(payload, b"sticky-value")

    def test_empty_retained_payload_clears_it(self):
        topic = self.topic("retained-clear")
        pub = self.new_client()
        pub.connect()
        pub.publish(topic, "value", qos=0, retain=1)
        time.sleep(0.2)
        pub.publish(topic, b"", qos=0, retain=1)
        time.sleep(0.2)

        sub = self.new_client()
        sub.connect()
        sub.subscribe([(topic, 0)])

        sub.sock.settimeout(1.0)
        with self.assertRaises(socket.timeout):
            sub.read_publish(timeout=1.0)


class KeepAliveTests(MQBTestCase):
    def test_pingreq_gets_pingresp(self):
        c = self.new_client()
        c.connect()
        ptype, _, _ = c.pingreq()
        self.assertEqual(ptype, PINGRESP)


class DisconnectTests(MQBTestCase):
    def test_graceful_disconnect_suppresses_will(self):
        will_topic = self.topic("will")
        victim = self.new_client(client_id="disc-test-" + uuid.uuid4().hex[:8])
        victim.connect(will=(will_topic, "should-not-fire", 0, False))

        sub = self.new_client()
        sub.connect()
        sub.subscribe([(will_topic, 0)])

        victim.disconnect()
        victim.close()
        time.sleep(0.3)

        sub.sock.settimeout(1.0)
        with self.assertRaises(socket.timeout):
            sub.read_publish(timeout=1.0)

    def test_ungraceful_disconnect_fires_will(self):
        will_topic = self.topic("will-fire")
        victim = self.new_client(client_id="disc-test2-" + uuid.uuid4().hex[:8])
        victim.connect(will=(will_topic, "goodbye", 0, False))

        sub = self.new_client()
        sub.connect()
        sub.subscribe([(will_topic, 0)])

        victim.sock.close()  # drop the TCP connection without sending DISCONNECT
        time.sleep(0.3)

        rtopic, payload, _, _ = sub.read_publish(timeout=3)
        self.assertEqual(rtopic, will_topic)
        self.assertEqual(payload, b"goodbye")


class AdminHealthTests(unittest.TestCase):
    def test_health_endpoint(self):
        conn = http.client.HTTPConnection(HOST, ADMIN_PORT, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.read().strip(), b"ok")
        conn.close()

    def test_stats_endpoint_reports_connected_clients(self):
        c = Client(HOST, PORT, connect=False)
        c.connect(password=PASSWORD)
        try:
            conn = http.client.HTTPConnection(HOST, ADMIN_PORT, timeout=5)
            conn.request("GET", "/admin/stats")
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read())
            self.assertIn("clients_connected", data)
            self.assertGreaterEqual(data["clients_connected"], 1)
            conn.close()
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
