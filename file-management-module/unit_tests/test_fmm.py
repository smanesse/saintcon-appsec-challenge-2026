#!/usr/bin/env python3
"""
Network-based unit tests for the File Management Module (FMM / fmm).

These tests exercise the *basic, intended functionality* of the protocol
described in ../README.md — greeting, auth, PWD/CWD, LIST, STOR/RETR round
trips, session resume, and error replies. They are functional tests, not
security tests.

Everything is driven purely over the TCP control connection.

Usage
-----
    python3 -m unittest test_fmm                 # auto-launch a local server
    python3 test_fmm.py                          # same, via unittest.main()

Point the tests at an already-running server instead of auto-launching:

    FMM_HOST=127.0.0.1 FMM_PORT=2121 FMM_NO_LAUNCH=1 python3 -m unittest test_fmm

Environment variables
---------------------
    FMM_HOST        host to connect to (default 127.0.0.1)
    FMM_PORT        port to connect to (default 2121)
    FMM_BINARY      path to the server binary to launch (default: auto-detect
                    ./fmm next to the project root)
    FMM_NO_LAUNCH   if set, never launch a server — connect to FMM_HOST/PORT
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

HOST = os.environ.get("FMM_HOST", "127.0.0.1")
PORT = int(os.environ.get("FMM_PORT", "2121"))

# Credentials shipped with the exercise (see credentials.txt).
VALID_USER = "alice"
VALID_PASS = "password123"

# Fallback the server bakes in when FMM_FLAG is unset (DEFAULT_FLAG in
# fmm.cpp). The runtime secret is written from FMM_FLAG or this default.
DEFAULT_FLAG = "FLAG{local-dev-default}"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Populated by setUpModule when it launches its own server; None otherwise.
_server_proc = None
_server_tmpdir = None


# ---------------------------------------------------------------------------
# Tiny protocol client
# ---------------------------------------------------------------------------
class FmmClient:
    """A minimal line-oriented client for the FMM control protocol."""

    def __init__(self, host=HOST, port=PORT, timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""
        self.greeting = self.read_line()

    # --- low-level line I/O ------------------------------------------------
    def read_line(self):
        """Read one CRLF/LF-terminated line and return it without the EOL."""
        while b"\n" not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                # Connection closed with a partial (or empty) line.
                line, self._buf = self._buf, b""
                return line.decode(errors="replace").rstrip("\r")
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line.decode(errors="replace").rstrip("\r")

    def send(self, line):
        self.sock.sendall((line + "\n").encode())

    def command(self, line):
        """Send a command and return the single-line reply."""
        self.send(line)
        return self.read_line()

    def drain(self, timeout=1.0):
        """Read whatever is buffered/incoming until a short idle timeout."""
        out = self._buf
        self._buf = b""
        self.sock.settimeout(timeout)
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                out += chunk
        except socket.timeout:
            pass
        finally:
            self.sock.settimeout(5.0)
        return out.decode(errors="replace")

    # --- protocol helpers --------------------------------------------------
    def login(self, user=VALID_USER, password=VALID_PASS):
        self.command(f"USER {user}")
        return self.command(f"PASS {password}")

    def open_pasv(self):
        """Send PASV, parse the 227 reply, and return a connected data socket."""
        reply = self.command("PASV")
        if not reply.startswith("227"):
            raise AssertionError(f"PASV failed: {reply}")
        nums = reply[reply.index("(") + 1:reply.index(")")].split(",")
        host = ".".join(nums[:4])
        port = int(nums[4]) * 256 + int(nums[5])
        return socket.create_connection((host, port), timeout=5.0)

    def open_port_active(self):
        """
        Bind a listening socket on this client's own address (the same
        address the server already sees us connecting from over the control
        connection), send PORT for it, and return (listener, port_reply).
        The caller must accept() the server's incoming data connection after
        issuing the transfer command.
        """
        local_ip = self.sock.getsockname()[0]
        ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind((local_ip, 0))
        ls.listen(1)
        ls.settimeout(5.0)
        port = ls.getsockname()[1]
        p1, p2 = port >> 8, port & 0xff
        reply = self.command(f"PORT {local_ip.replace('.', ',')},{p1},{p2}")
        return ls, reply

    def retr_active(self, filename):
        """RETR a file over active-mode (PORT); returns (first_reply, body_bytes, final_line)."""
        ls, port_reply = self.open_port_active()
        try:
            if not port_reply.startswith("200"):
                return port_reply, b"", ""
            first = self.command(f"RETR {filename}")
            if not first.startswith("150"):
                return first, b"", ""
            data, _ = ls.accept()
            body = self.read_data(data)
            return first, body, self.read_line()
        finally:
            ls.close()

    def stor_active(self, filename, payload):
        """STOR a file over active-mode (PORT); returns the final reply line."""
        if not isinstance(payload, (bytes, bytearray)):
            payload = ("\n".join(payload) + "\n").encode()
        ls, port_reply = self.open_port_active()
        try:
            if not port_reply.startswith("200"):
                return port_reply
            first = self.command(f"STOR {filename}")
            if not first.startswith("150"):
                return first
            data, _ = ls.accept()
            data.sendall(payload)
            data.close()
            return self.read_line()
        finally:
            ls.close()

    def read_data(self, data_sock):
        """Read a data connection to EOF (peer close) and return raw bytes."""
        out = b""
        try:
            while True:
                chunk = data_sock.recv(65536)
                if not chunk:
                    break
                out += chunk
        except socket.timeout:
            pass
        finally:
            data_sock.close()
        return out

    def list(self):
        """LIST over a PASV data connection; returns (first, body, final)."""
        data = self.open_pasv()
        first = self.command("LIST")
        if not first.startswith("150"):
            data.close()
            return first, "", ""
        body = self.read_data(data).decode(errors="replace")
        return first, body, self.read_line()

    def retr(self, filename):
        """RETR a file over PASV; returns (first_reply, body_bytes, final_line)."""
        data = self.open_pasv()
        first = self.command(f"RETR {filename}")
        if not first.startswith("150"):
            data.close()
            return first, b"", ""
        body = self.read_data(data)
        return first, body, self.read_line()

    def stor(self, filename, payload):
        """
        STOR a file over PASV. `payload` may be bytes or an iterable of text
        lines (joined with '\\n'). Returns the final reply line.
        """
        if not isinstance(payload, (bytes, bytearray)):
            payload = ("\n".join(payload) + "\n").encode()
        data = self.open_pasv()
        first = self.command(f"STOR {filename}")
        if not first.startswith("150"):
            data.close()
            return first
        data.sendall(payload)
        data.close()
        return self.read_line()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Module-level server lifecycle
# ---------------------------------------------------------------------------
def _server_is_up(host, port):
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _wait_until_up(host, port, timeout):
    """Poll until the server accepts connections, or timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_is_up(host, port):
            return True
        time.sleep(0.2)
    return False


def _find_binary():
    if os.environ.get("FMM_BINARY"):
        return os.environ["FMM_BINARY"]
    for name in ("fmm",):
        candidate = os.path.join(PROJECT_ROOT, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def setUpModule():
    global _server_proc, _server_tmpdir

    if _server_is_up(HOST, PORT):
        return  # Reuse a server that's already listening.

    if os.environ.get("FMM_NO_LAUNCH"):
        # A server is expected elsewhere (e.g. a container on the compose
        # network). Give it a generous window to finish starting up.
        if _wait_until_up(HOST, PORT, 30.0):
            return
        raise unittest.SkipTest(
            f"No server reachable on {HOST}:{PORT} and FMM_NO_LAUNCH is set"
        )

    binary = _find_binary()
    if not binary:
        raise unittest.SkipTest(
            "No running server and no fmm binary found to launch "
            "(set FMM_BINARY or run `make` in the project root)"
        )

    # The server resolves credentials.txt and ./ftproot relative to its CWD,
    # so run it from an isolated copy to keep uploads out of the source tree.
    _server_tmpdir = tempfile.mkdtemp(prefix="fmm_test_")
    shutil.copy(os.path.join(PROJECT_ROOT, "credentials.txt"), _server_tmpdir)
    shutil.copytree(
        os.path.join(PROJECT_ROOT, "ftproot"),
        os.path.join(_server_tmpdir, "ftproot"),
    )

    _server_proc = subprocess.Popen(
        [os.path.abspath(binary)],
        cwd=_server_tmpdir,
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
# Tests
# ---------------------------------------------------------------------------
class FmmTestBase(unittest.TestCase):
    def setUp(self):
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            try:
                c.command("QUIT")
            except OSError:
                pass
            c.close()

    def new_client(self):
        c = FmmClient()
        self.clients.append(c)
        return c

    def logged_in_client(self):
        c = self.new_client()
        reply = c.login()
        self.assertTrue(reply.startswith("230"), f"login failed: {reply!r}")
        return c


class ConnectionTests(FmmTestBase):
    def test_greeting_on_connect(self):
        c = self.new_client()
        self.assertTrue(
            c.greeting.startswith("220"),
            f"expected 220 greeting, got {c.greeting!r}",
        )

    def test_unknown_command(self):
        c = self.new_client()
        self.assertTrue(c.command("FLOOP").startswith("502"))


class AuthTests(FmmTestBase):
    def test_user_prompts_for_password(self):
        c = self.new_client()
        reply = c.command(f"USER {VALID_USER}")
        self.assertTrue(reply.startswith("331"))
        self.assertIn(VALID_USER, reply)

    def test_valid_login_issues_token(self):
        c = self.new_client()
        c.command(f"USER {VALID_USER}")
        reply = c.command(f"PASS {VALID_PASS}")
        self.assertTrue(reply.startswith("230"), reply)
        self.assertIn("token=", reply)

    def test_invalid_password_rejected(self):
        c = self.new_client()
        c.command(f"USER {VALID_USER}")
        reply = c.command("PASS definitely-wrong")
        self.assertTrue(reply.startswith("530"), reply)

    def test_unknown_user_rejected(self):
        c = self.new_client()
        c.command("USER nobody")
        reply = c.command("PASS whatever")
        self.assertTrue(reply.startswith("530"), reply)

    def test_second_account_logs_in(self):
        c = self.new_client()
        c.command("USER bob")
        reply = c.command("PASS hunter2")
        self.assertTrue(reply.startswith("230"), reply)


class AuthGatingTests(FmmTestBase):
    """Commands that must reject an unauthenticated session."""

    def test_list_requires_login(self):
        c = self.new_client()
        self.assertTrue(c.command("LIST").startswith("530"))

    def test_retr_requires_login(self):
        c = self.new_client()
        self.assertTrue(c.command("RETR welcome.txt").startswith("530"))

    def test_stor_requires_login(self):
        c = self.new_client()
        self.assertTrue(c.command("STOR notes.txt").startswith("530"))

    def test_cwd_requires_login(self):
        c = self.new_client()
        self.assertTrue(c.command("CWD ftproot").startswith("530"))


class DirectoryTests(FmmTestBase):
    def test_pwd_default_root(self):
        c = self.new_client()
        reply = c.command("PWD")
        self.assertTrue(reply.startswith("257"), reply)
        self.assertIn("ftproot", reply)

    def test_list_returns_body_and_terminator(self):
        c = self.logged_in_client()
        first, body, final = c.list()
        self.assertTrue(first.startswith("150"), first)
        self.assertTrue(final.startswith("226"), final)
        self.assertIn("welcome.txt", body)

    def test_cwd_empty_arg_is_syntax_error(self):
        c = self.logged_in_client()
        self.assertTrue(c.command("CWD").startswith("501"))

    def test_cwd_nonexistent_dir_fails(self):
        c = self.logged_in_client()
        reply = c.command("CWD no_such_directory_here")
        self.assertTrue(reply.startswith("550"), reply)

    def test_cwd_into_subdir_succeeds(self):
        # A legitimate in-root subdirectory must remain reachable: CWD is
        # supposed to *confine* to the service root, not reject everything.
        # This pins the intended success path so a directory-confinement fix
        # that simply refuses every CWD would fail here.
        c = self.logged_in_client()
        reply = c.command("CWD docs")
        self.assertTrue(reply.startswith("250"), reply)
        # The working directory actually moved into the subdirectory...
        pwd = c.command("PWD")
        self.assertTrue(pwd.startswith("257"), pwd)
        self.assertIn("docs", pwd)
        # ...and LIST there returns that subdirectory's own contents.
        first, body, final = c.list()
        self.assertTrue(first.startswith("150"), first)
        self.assertTrue(final.startswith("226"), final)
        self.assertIn("note.txt", body)


class RetrieveTests(FmmTestBase):
    def test_retr_existing_file(self):
        c = self.logged_in_client()
        first, body, final = c.retr("welcome.txt")
        self.assertTrue(first.startswith("150"), first)
        self.assertTrue(final.startswith("226"), final)
        self.assertIn(b"sample file", body)

    def test_retr_missing_file(self):
        c = self.logged_in_client()
        reply = c.command(f"RETR ghost_{uuid.uuid4().hex}.txt")
        self.assertTrue(reply.startswith("550"), reply)

    def test_retr_empty_arg_is_syntax_error(self):
        c = self.logged_in_client()
        self.assertTrue(c.command("RETR").startswith("501"))

    def test_retr_active_mode_port(self):
        # Every other transfer test uses PASV; this exercises the other half
        # of the documented data-connection negotiation (client-side PORT).
        c = self.logged_in_client()
        first, body, final = c.retr_active("welcome.txt")
        self.assertTrue(first.startswith("150"), first)
        self.assertTrue(final.startswith("226"), final)
        self.assertIn(b"sample file", body)


class StoreTests(FmmTestBase):
    def test_stor_then_retr_roundtrip(self):
        c = self.logged_in_client()
        name = f"unit_{uuid.uuid4().hex[:8]}.txt"
        payload = ["line one", "line two", "line three"]

        final = c.stor(name, payload)
        self.assertTrue(final.startswith("226"), final)

        _, body, retr_final = c.retr(name)
        self.assertTrue(retr_final.startswith("226"), retr_final)
        for line in payload:
            self.assertIn(line.encode(), body)

    def test_stor_active_mode_port_then_retr(self):
        c = self.logged_in_client()
        name = f"active_{uuid.uuid4().hex[:8]}.txt"
        payload = ["active mode line one", "active mode line two"]

        final = c.stor_active(name, payload)
        self.assertTrue(final.startswith("226"), final)

        _, body, retr_final = c.retr(name)
        self.assertTrue(retr_final.startswith("226"), retr_final)
        for line in payload:
            self.assertIn(line.encode(), body)

    def test_stored_file_appears_in_listing(self):
        c = self.logged_in_client()
        name = f"listed_{uuid.uuid4().hex[:8]}.txt"
        self.assertTrue(c.stor(name, ["hi"]).startswith("226"))

        _, body, _ = c.list()
        self.assertIn(name, body)

    def test_stor_invalid_filename_rejected(self):
        c = self.logged_in_client()
        # No extension -> fails the STOR filename validator.
        reply = c.command("STOR noextension")
        self.assertTrue(reply.startswith("553"), reply)

    def test_stor_empty_arg_is_syntax_error(self):
        c = self.logged_in_client()
        self.assertTrue(c.command("STOR").startswith("501"))


class SessionResumeTests(FmmTestBase):
    def test_resume_with_valid_token(self):
        c1 = self.new_client()
        reply = c1.login()
        self.assertIn("token=", reply)
        token = reply.split("token=", 1)[1].strip()

        c2 = self.new_client()
        resumed = c2.command(f"SESS {token}")
        self.assertTrue(resumed.startswith("230"), resumed)
        # Resumed session is authenticated: a gated command now works.
        first, _, final = c2.list()
        self.assertTrue(first.startswith("150"), first)
        self.assertTrue(final.startswith("226"), final)

    def test_resume_with_unknown_token_rejected(self):
        c = self.new_client()
        reply = c.command("SESS 99999zzz-not-a-token")
        self.assertTrue(reply.startswith("530"), reply)


class FlagMaterializationTests(unittest.TestCase):
    """The runtime secret must actually be written to disk.

    Not a functional protocol test: it pins a *deployment invariant* the
    grader depends on. write_flag_files() (fmm.cpp) drops the per-deployment
    secret into three files at startup:

        secret/flag.txt            - the flag as file *content*
        secret/<flag value>        - the flag as the file *name*, outside ftproot
        ftproot/vault/manifest.dat - the flag as file *content*, inside the
                                     served root

    Removing or relocating any of them would let a submission report success
    without actually securing the service - a cheat that a network-only check
    cannot catch (by design, the secret is unreadable over the wire without
    exploiting the service). This asserts all three exist and encode the
    deployment's flag, so that cheat fails CI instead.

    Filesystem-level, so it only runs when this module launched its own server
    (we know its working directory). Against an external/containerized server
    (FMM_NO_LAUNCH), it skips - there's no local secret/ to inspect.
    """

    def test_secret_files_materialize_from_flag(self):
        if _server_tmpdir is None:
            self.skipTest(
                "server not launched by this test run; no local secret/ to "
                "inspect (reused/external server or FMM_NO_LAUNCH)"
            )
        expected = os.environ.get("FMM_FLAG") or DEFAULT_FLAG
        secret_dir = os.path.join(_server_tmpdir, "secret")

        content_file = os.path.join(secret_dir, "flag.txt")
        self.assertTrue(
            os.path.isfile(content_file),
            f"secret/flag.txt was not written under {secret_dir!r} - a "
            f"required per-deployment secret file is missing",
        )
        with open(content_file, "r", errors="replace") as f:
            self.assertEqual(
                f.read().strip(), expected,
                "secret/flag.txt content does not match this run's flag",
            )

        marker_file = os.path.join(secret_dir, expected)
        self.assertTrue(
            os.path.isfile(marker_file),
            f"secret/<flag> marker ({expected!r}) was not written - the "
            f"filename-encoded per-deployment secret marker is missing",
        )

        vault_file = os.path.join(_server_tmpdir, "ftproot", "vault", "manifest.dat")
        self.assertTrue(
            os.path.isfile(vault_file),
            f"ftproot/vault/manifest.dat was not written under {_server_tmpdir!r} "
            f"- the within-root per-deployment secret file is missing",
        )
        with open(vault_file, "r", errors="replace") as f:
            self.assertEqual(
                f.read().strip(), expected,
                "ftproot/vault/manifest.dat content does not match this run's flag",
            )


class QuitTests(FmmTestBase):
    def test_quit_says_goodbye_and_closes(self):
        c = self.new_client()
        reply = c.command("QUIT")
        self.assertTrue(reply.startswith("221"), reply)
        # After QUIT the server closes the socket; a subsequent read yields EOF.
        c.sock.settimeout(2.0)
        self.assertEqual(c.sock.recv(1024), b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
