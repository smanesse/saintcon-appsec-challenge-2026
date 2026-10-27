#!/usr/bin/env python3
"""
Functional tests for the KVS key-value store - NOT security tests.
These drive the documented RESP protocol from README.md (strings, expiry,
counters, lists, hashes, keyspace scans, CONFIG/SAVE, EVAL) and check the
golden path plus the documented error replies.

Configuration (env vars):
    KVS_HOST        host to connect to (default 127.0.0.1)
    KVS_PORT        port to connect to (default 6379)
    KVS_NO_LAUNCH   if set, never launch a server - connect to KVS_HOST/PORT
    KVS_BINARY      path to a prebuilt `kvs` binary to launch locally

Run against an already-running server (e.g. a container on the compose net):
    KVS_HOST=kvs KVS_PORT=6379 KVS_NO_LAUNCH=1 python3 -m unittest test_kvs -v

Or let it launch a local binary (build with `go build -o kvs .` first):
    python3 -m unittest test_kvs -v
"""
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import uuid

HOST = os.environ.get("KVS_HOST", "127.0.0.1")
PORT = int(os.environ.get("KVS_PORT", "6379"))
# Set by a harness that generated a real credential (see
# ../../generate-secrets.sh); empty means "no auth configured", matching
# today's default and requiring no local setup.
REQUIREPASS = os.environ.get("KVS_REQUIREPASS", "")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_server_proc = None
_server_tmpdir = None


# ---------------------------------------------------------------------------
# RESP client
# ---------------------------------------------------------------------------
def encode(*parts):
    out = b"*%d\r\n" % len(parts)
    for p in parts:
        p = p.encode() if isinstance(p, str) else p
        out += b"$%d\r\n%s\r\n" % (len(p), p)
    return out


class Client:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.f = self.sock.makefile("rb")

    def cmd(self, *parts):
        self.sock.sendall(encode(*parts))
        return self._read()

    def _read(self):
        line = self.f.readline()
        if not line:
            raise ConnectionError("closed")
        t, body = line[:1], line[1:].strip()
        if t == b"+":
            return ("status", body.decode())
        if t == b"-":
            return ("error", body.decode())
        if t == b":":
            return ("int", int(body))
        if t == b"$":
            n = int(body)
            if n < 0:
                return ("bulk", None)
            data = self.f.read(n)
            self.f.read(2)
            return ("bulk", data.decode())
        if t == b"*":
            n = int(body)
            if n < 0:
                return ("array", None)
            return ("array", [self._read() for _ in range(n)])
        raise ValueError(f"bad reply {line!r}")

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


def _find_binary():
    candidate = os.environ.get("KVS_BINARY")
    if candidate and os.path.isfile(candidate):
        return candidate
    candidate = os.path.join(PROJECT_ROOT, "kvs")
    if os.path.isfile(candidate):
        return candidate
    return None


def setUpModule():
    global _server_proc, _server_tmpdir
    if _server_is_up(HOST, PORT):
        return
    if os.environ.get("KVS_NO_LAUNCH"):
        if _wait_until_up(HOST, PORT, 30.0):
            return
        raise unittest.SkipTest(f"No server on {HOST}:{PORT} and KVS_NO_LAUNCH is set")
    binary = _find_binary()
    if not binary:
        raise unittest.SkipTest("No running server and no kvs binary (set KVS_BINARY or `go build -o kvs .`)")
    _server_tmpdir = tempfile.mkdtemp(prefix="kvs_test_")
    env = dict(os.environ)
    env["KVS_PORT"] = str(PORT)
    env["KVS_DIR"] = _server_tmpdir
    _server_proc = subprocess.Popen([os.path.abspath(binary)], cwd=_server_tmpdir, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


class KVSTestCase(unittest.TestCase):
    def setUp(self):
        self.c = Client(HOST, PORT)
        if REQUIREPASS:
            self.assertEqual(self.c.cmd("AUTH", REQUIREPASS), ("status", "OK"))
        self.k = "t:" + uuid.uuid4().hex[:10]

    def tearDown(self):
        self.c.close()


class StringTests(KVSTestCase):
    def test_ping(self):
        self.assertEqual(self.c.cmd("PING"), ("status", "PONG"))
        self.assertEqual(self.c.cmd("PING", "hi"), ("bulk", "hi"))

    def test_echo(self):
        self.assertEqual(self.c.cmd("ECHO", "hello world"), ("bulk", "hello world"))
        self.assertEqual(self.c.cmd("ECHO")[0], "error")  # wrong arity

    def test_set_get(self):
        self.assertEqual(self.c.cmd("SET", self.k, "hello"), ("status", "OK"))
        self.assertEqual(self.c.cmd("GET", self.k), ("bulk", "hello"))

    def test_get_missing_is_nil(self):
        self.assertEqual(self.c.cmd("GET", self.k), ("bulk", None))

    def test_del_and_exists(self):
        self.c.cmd("SET", self.k, "v")
        self.assertEqual(self.c.cmd("EXISTS", self.k), ("int", 1))
        self.assertEqual(self.c.cmd("DEL", self.k), ("int", 1))
        self.assertEqual(self.c.cmd("EXISTS", self.k), ("int", 0))

    def test_type(self):
        self.c.cmd("SET", self.k, "v")
        self.assertEqual(self.c.cmd("TYPE", self.k), ("status", "string"))

    def test_wrong_arity(self):
        self.assertEqual(self.c.cmd("GET")[0], "error")

    def test_unknown_command(self):
        self.assertEqual(self.c.cmd("NOTACOMMAND")[0], "error")


class ExpiryTests(KVSTestCase):
    def test_expire_ttl_persist(self):
        self.c.cmd("SET", self.k, "v")
        self.assertEqual(self.c.cmd("TTL", self.k), ("int", -1))
        self.assertEqual(self.c.cmd("EXPIRE", self.k, "100"), ("int", 1))
        kind, ttl = self.c.cmd("TTL", self.k)
        self.assertEqual(kind, "int")
        self.assertTrue(0 < ttl <= 100)
        self.assertEqual(self.c.cmd("PERSIST", self.k), ("int", 1))
        self.assertEqual(self.c.cmd("TTL", self.k), ("int", -1))

    def test_ttl_missing_key(self):
        self.assertEqual(self.c.cmd("TTL", self.k), ("int", -2))

    def test_px_expires(self):
        self.c.cmd("SET", self.k, "v", "PX", "50")
        time.sleep(0.15)
        self.assertEqual(self.c.cmd("GET", self.k), ("bulk", None))

    def test_set_ex_sets_ttl(self):
        # SET ... EX <seconds> is a distinct parse branch from PX; assert the
        # TTL lands in range rather than waiting a whole second for it to lapse.
        self.assertEqual(self.c.cmd("SET", self.k, "v", "EX", "100"), ("status", "OK"))
        kind, ttl = self.c.cmd("TTL", self.k)
        self.assertEqual(kind, "int")
        self.assertTrue(0 < ttl <= 100)


class CounterTests(KVSTestCase):
    def test_incr_decr(self):
        self.assertEqual(self.c.cmd("INCR", self.k), ("int", 1))
        self.assertEqual(self.c.cmd("INCR", self.k), ("int", 2))
        self.assertEqual(self.c.cmd("DECR", self.k), ("int", 1))

    def test_incr_non_integer_errors(self):
        self.c.cmd("SET", self.k, "abc")
        self.assertEqual(self.c.cmd("INCR", self.k)[0], "error")


class ListTests(KVSTestCase):
    def test_push_range_pop(self):
        self.assertEqual(self.c.cmd("RPUSH", self.k, "a", "b", "c"), ("int", 3))
        self.assertEqual(self.c.cmd("LPUSH", self.k, "z"), ("int", 4))
        kind, items = self.c.cmd("LRANGE", self.k, "0", "-1")
        self.assertEqual(kind, "array")
        self.assertEqual([v for _, v in items], ["z", "a", "b", "c"])
        self.assertEqual(self.c.cmd("LPOP", self.k), ("bulk", "z"))
        self.assertEqual(self.c.cmd("RPOP", self.k), ("bulk", "c"))
        self.assertEqual(self.c.cmd("LLEN", self.k), ("int", 2))

    def test_pop_empty_is_nil(self):
        self.assertEqual(self.c.cmd("LPOP", self.k), ("bulk", None))

    def test_wrongtype(self):
        self.c.cmd("SET", self.k, "v")
        r = self.c.cmd("LPUSH", self.k, "x")
        self.assertEqual(r[0], "error")
        self.assertIn("WRONGTYPE", r[1])


class HashTests(KVSTestCase):
    def test_hset_hget_hgetall_hdel(self):
        self.assertEqual(self.c.cmd("HSET", self.k, "f1", "v1", "f2", "v2"), ("int", 2))
        self.assertEqual(self.c.cmd("HGET", self.k, "f1"), ("bulk", "v1"))
        kind, items = self.c.cmd("HGETALL", self.k)
        flat = [v for _, v in items]
        self.assertEqual(flat, ["f1", "v1", "f2", "v2"])
        self.assertEqual(self.c.cmd("HDEL", self.k, "f1"), ("int", 1))
        self.assertEqual(self.c.cmd("HGET", self.k, "f1"), ("bulk", None))

    def test_hget_missing(self):
        self.assertEqual(self.c.cmd("HGET", self.k, "nope"), ("bulk", None))


class KeyspaceTests(KVSTestCase):
    def test_keys_and_scan(self):
        prefix = "scan:" + uuid.uuid4().hex[:8]
        for i in range(3):
            self.c.cmd("SET", f"{prefix}:{i}", "v")
        kind, items = self.c.cmd("KEYS", f"{prefix}:*")
        self.assertEqual(kind, "array")
        self.assertEqual(len(items), 3)
        kind, arr = self.c.cmd("SCAN", "0", "MATCH", f"{prefix}:*")
        self.assertEqual(kind, "array")
        self.assertEqual(arr[0], ("bulk", "0"))  # cursor
        self.assertEqual(len(arr[1][1]), 3)


class ConfigSaveTests(KVSTestCase):
    def test_config_get_set(self):
        kind, items = self.c.cmd("CONFIG", "GET", "dir")
        self.assertEqual(kind, "array")
        self.assertEqual(items[0], ("bulk", "dir"))
        self.assertEqual(self.c.cmd("CONFIG", "SET", "dbfilename", "unit.kvs"), ("status", "OK"))
        _, items = self.c.cmd("CONFIG", "GET", "dbfilename")
        self.assertEqual(items[1], ("bulk", "unit.kvs"))

    def test_save_ok(self):
        self.c.cmd("SET", self.k, "persisted")
        self.assertEqual(self.c.cmd("SAVE"), ("status", "OK"))

    def test_save_to_unwritable_dir_errors(self):
        # SAVE surfaces write failures instead of silently succeeding. Point the
        # dump dir at a path that cannot exist/be written, SAVE, expect an error
        # reply -- proving SAVE actually performs the write (there is no
        # network-readable dump format to assert contents against benignly; the
        # only readback path is the unsandboxed EVAL io.open, which is a vuln and
        # must not be leaned on by a functional test). Restore dir afterward so
        # CONFIG is global state shared with other tests.
        _, items = self.c.cmd("CONFIG", "GET", "dir")
        orig_dir = items[1][1]
        bad = "/nonexistent-%s/nope" % uuid.uuid4().hex[:8]
        try:
            r = self.c.cmd("CONFIG", "SET", "dir", bad)
            if r[0] == "error":
                # A hardened server may allow-list the dump directory and reject
                # an arbitrary/traversing path at CONFIG SET time -- a more-
                # defended outcome that keeps this functional test green.
                # Nothing was repointed, so there is nothing further to assert.
                return
            self.assertEqual(r, ("status", "OK"))
            self.c.cmd("SET", self.k, "v")
            self.assertEqual(self.c.cmd("SAVE")[0], "error")
        finally:
            self.c.cmd("CONFIG", "SET", "dir", orig_dir)


class KeyspaceAdminTests(KVSTestCase):
    def test_dbsize_reflects_writes(self):
        # DBSIZE returns a running key count. Assert by DELTA rather than an
        # absolute value: the store may already hold keys (e.g. a startup-seeded
        # secret) and other connections are irrelevant here since we add our own.
        _, n0 = self.c.cmd("DBSIZE")
        self.assertEqual(_, "int")
        self.c.cmd("SET", self.k + ":a", "1")
        self.c.cmd("SET", self.k + ":b", "1")
        _, n1 = self.c.cmd("DBSIZE")
        self.assertEqual(n1, n0 + 2)

    def test_flushall_empties_keyspace(self):
        # FLUSHALL/FLUSHDB wipe the ENTIRE keyspace (this is destructive and
        # global -- including any startup-seeded data -- so the functional suite
        # must run against its own dedicated instance, which the unit_tests
        # compose provides, never a live scored one).
        self.c.cmd("SET", self.k, "v")
        self.assertEqual(self.c.cmd("EXISTS", self.k), ("int", 1))
        self.assertEqual(self.c.cmd("FLUSHALL"), ("status", "OK"))
        self.assertEqual(self.c.cmd("GET", self.k), ("bulk", None))
        self.assertEqual(self.c.cmd("DBSIZE"), ("int", 0))


class EvalTests(KVSTestCase):
    def test_eval_returns_argv(self):
        self.assertEqual(self.c.cmd("EVAL", "return ARGV[1]", "0", "hi"), ("bulk", "hi"))

    def test_eval_redis_call(self):
        self.c.cmd("SET", self.k, "fromlua")
        self.assertEqual(self.c.cmd("EVAL", f"return redis.call('GET', KEYS[1])", "1", self.k),
                         ("bulk", "fromlua"))

    def test_eval_returns_number(self):
        self.assertEqual(self.c.cmd("EVAL", "return 1 + 2", "0"), ("int", 3))


class AuthTests(KVSTestCase):
    def test_auth_with_wrong_value_errors(self):
        # No password configured: AUTH errors "no password set". Password
        # configured (setUp already authenticated self.c): re-AUTHing with a
        # wrong value errors "WRONGPASS". Either way, AUTH with an unknown
        # value must fail.
        r = self.c.cmd("AUTH", "definitely-wrong-value")
        self.assertEqual(r[0], "error")

    def test_auth_with_correct_password_when_configured(self):
        if not REQUIREPASS:
            self.skipTest("KVS_REQUIREPASS not set for this run")
        self.assertEqual(self.c.cmd("AUTH", REQUIREPASS), ("status", "OK"))


class ReplicationTests(KVSTestCase):
    def test_replicaof_wrong_arity_errors(self):
        self.assertEqual(self.c.cmd("REPLICAOF")[0], "error")

    def test_replicaof_no_one_ok(self):
        self.assertEqual(self.c.cmd("REPLICAOF", "NO", "ONE"), ("status", "OK"))

    def test_replica_applies_master_stream(self):
        # Functional counterpart of the documented replication feature (README:
        # "REPLICAOF host port -> the server connects as a replica and applies
        # the command stream it receives"). A KVS master does not push writes to
        # replicas, so a second KVS would propagate nothing; instead this test
        # plays a BENIGN master itself: it stands up a listener, tells the
        # server under test to REPLICAOF it, streams one ordinary SET the way a
        # master would, and then confirms over a normal client connection that
        # the replica applied it. Everything is over TCP -- the replica dials
        # back to our listener -- so this stays purely network-driven, the same
        # transport a scoring harness uses.
        key = "repl:" + uuid.uuid4().hex[:12]
        val = uuid.uuid4().hex

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", 0))
        listener.listen(1)
        my_port = listener.getsockname()[1]
        # The address the server sees us on = our client socket's local address;
        # that's the address it will dial back to when it becomes our replica.
        my_ip = self.c.sock.getsockname()[0]

        def serve_master():
            try:
                listener.settimeout(10)
                peer, _ = listener.accept()
                # Drain the replica's handshake (PING/REPLCONF/PSYNC); a benign
                # master need not answer it before streaming writes.
                peer.settimeout(1.0)
                try:
                    peer.recv(4096)
                except socket.timeout:
                    pass
                peer.sendall(encode("SET", key, val))
                time.sleep(1.0)
                peer.close()
            except OSError:
                pass

        t = threading.Thread(target=serve_master, daemon=True)
        t.start()
        try:
            self.assertEqual(self.c.cmd("REPLICAOF", my_ip, str(my_port)), ("status", "OK"))
            got = None
            deadline = time.time() + 10
            while time.time() < deadline:
                kind, v = self.c.cmd("GET", key)
                if kind == "bulk" and v == val:
                    got = v
                    break
                time.sleep(0.3)
            self.assertEqual(got, val,
                             "replica did not apply the write streamed by its master")
        finally:
            # Stop following our (now-closed) master so the link doesn't linger.
            self.c.cmd("REPLICAOF", "NO", "ONE")
            listener.close()
            t.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
