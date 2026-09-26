from __future__ import annotations

import asyncio
import hmac
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from . import packet as p
from .config import Config

log = logging.getLogger("mqb")

CONNECT_TIMEOUT = 20.0
MAX_PACKET_ID = 0xFFFF


def retained_path(retain_dir: str, topic: str) -> str:
    return os.path.join(retain_dir, topic)


@dataclass
class ClientConn:
    client_id: str
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    keep_alive: int = 60
    clean_session: bool = True
    authenticated: bool = False
    username: Optional[str] = None
    subscriptions: Dict[str, int] = field(default_factory=dict)
    pending_ack: Dict[int, Tuple[str, bytes]] = field(default_factory=dict)
    next_out_packet_id: int = 1
    will_topic: Optional[str] = None
    will_message: Optional[bytes] = None
    will_qos: int = 0
    will_retain: bool = False
    last_activity: float = field(default_factory=time.monotonic)
    closing: bool = False

    def alloc_packet_id(self) -> int:
        pid = self.next_out_packet_id
        self.next_out_packet_id = (self.next_out_packet_id % MAX_PACKET_ID) + 1
        return pid

    async def force_close(self):
        self.closing = True
        try:
            self.writer.close()
        except Exception:
            pass


class Broker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.clients: Dict[str, ClientConn] = {}
        # Subscriptions of clients that connected with clean_session=False,
        # kept around after they disconnect so a later reconnect resumes
        # them, but only under the same username (see connect
        # handling below.)
        self.persisted_subs: Dict[str, Dict[str, int]] = {}
        # Username each persisted session was created under; a later CONNECT
        # only resumes it when it presents the same one.
        self.persisted_owner: Dict[str, Optional[str]] = {}
        # In-memory retained-message table: topic -> payload bytes.
        self.retained: Dict[str, bytes] = {}
        # The fleet-control namespace (the parent of cfg.flag_topic, i.e.
        # "fleet/control" by default) is broker-owned, like $SYS on a real
        # broker: its retained state is seeded by the broker itself and is
        # never delivered to MQTT clients -- see is_reserved().
        self.control_root = cfg.flag_topic.rsplit("/", 1)[0] if "/" in cfg.flag_topic else cfg.flag_topic
        os.makedirs(cfg.retain_dir, exist_ok=True)

    def seed_startup_state(self):
        self._store_retained(self.cfg.flag_topic, self.cfg.flag.encode())
        log.info("seeded startup retained flag on topic %r", self.cfg.flag_topic)

        try:
            os.makedirs(os.path.dirname(self.cfg.flag_file) or ".", exist_ok=True)
            with open(self.cfg.flag_file, "w") as f:
                f.write(self.cfg.flag + "\n")
            log.info("wrote flag file at %r", self.cfg.flag_file)
        except OSError as e:
            log.warning("failed to write flag file %r: %s", self.cfg.flag_file, e)

    def is_reserved(self, topic: str) -> bool:
        """True for a topic inside the broker-owned control namespace."""
        root = self.control_root
        return topic == root or topic.startswith(root + "/")

    def _filter_targets_reserved(self, topic_filter: str) -> bool:
        """True for a filter that names the control namespace explicitly
        (e.g. "fleet/control/flag" or "fleet/control/#"). Generic wildcard
        filters such as "#" or "fleet/#" are allowed, but never match a
        reserved topic at delivery time."""
        return self.is_reserved(topic_filter.rstrip("#").rstrip("/"))

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        conn: Optional[ClientConn] = None
        try:
            try:
                raw = await asyncio.wait_for(p.read_packet(reader), timeout=CONNECT_TIMEOUT)
            except asyncio.TimeoutError:
                log.info("connect timeout from %s", peer)
                return
            if raw is None or raw.ptype != p.CONNECT:
                log.info("expected CONNECT from %s, got %r", peer, raw)
                return

            conn = await self._handle_connect(raw, reader, writer)
            if conn is None:
                return

            await self._read_loop(conn)
        except (asyncio.IncompleteReadError, ConnectionResetError, p.MalformedPacket):
            pass
        except Exception:
            log.exception("connection handler error for %s", peer)
        finally:
            if conn is not None:
                await self._on_disconnect(conn, graceful=getattr(conn, "_graceful", False))
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_connect(self, raw: p.RawPacket, reader, writer) -> Optional[ClientConn]:
        try:
            cp = p.parse_connect(raw.body)
        except p.MalformedPacket:
            return None

        if cp.protocol_name not in ("MQTT", "MQIsdp") or cp.protocol_level != p.PROTOCOL_LEVEL_3_1_1:
            writer.write(p.build_connack(False, p.CONNACK_BAD_PROTOCOL_VERSION))
            await writer.drain()
            return None

        client_id = cp.client_id
        if not client_id:
            if cp.clean_session:
                client_id = "mqb-auto-" + uuid.uuid4().hex[:12]
            else:
                writer.write(p.build_connack(False, p.CONNACK_IDENTIFIER_REJECTED))
                await writer.drain()
                return None

        # --- Authentication ---------------------------------------------------
        # A failed credential gets the rc=4 CONNACK and the connection is
        # closed right here, per MQTT-3.2.2-5 -- no session is registered or
        # served. (VULN #1 was reporting rc=4 but then serving the session
        # anyway, so a configured MQB_REQUIREPASS was never enforced.)
        creds_ok = self._check_credentials(cp.username, cp.password)
        if not creds_ok:
            writer.write(p.build_connack(False, p.CONNACK_BAD_USERNAME_PASSWORD))
            await writer.drain()
            return None

        conn = ClientConn(
            client_id=client_id,
            reader=reader,
            writer=writer,
            keep_alive=cp.keep_alive,
            clean_session=cp.clean_session,
            authenticated=True,
            username=cp.username,
            will_topic=cp.will_topic,
            will_message=cp.will_message,
            will_qos=cp.will_qos,
            will_retain=cp.will_retain,
        )

        # --- Client-ID collision / session takeover --------------------------
        # A Client ID that is live on another connection cannot be taken over:
        # the newcomer is refused with rc=2 (identifier rejected) and the
        # existing session is left alone. Every client authenticates with the
        # same shared password, so nothing on a new CONNECT proves it is the
        # device that owns the ID; letting it evict the live connection (and
        # inherit its persistent subscriptions) handed any client that knew
        # an ID the victim's session. A device whose old TCP connection is
        # half-open reconnects once keep-alive reaps it. A stored persistent
        # session is resumed only under the username that created it. (VULN
        # #4 was a takeover with no identity check at all.)
        old_conn = self.clients.get(client_id)
        if old_conn is not None and not old_conn.closing:
            log.info("client id %r is already connected; refusing the new CONNECT", client_id)
            writer.write(p.build_connack(False, p.CONNACK_IDENTIFIER_REJECTED))
            await writer.drain()
            return None

        session_present = False
        inherited_subs: Dict[str, int] = {}
        if not cp.clean_session and client_id in self.persisted_subs \
                and self.persisted_owner.get(client_id) == cp.username:
            session_present = True
            inherited_subs = dict(self.persisted_subs[client_id])
        else:
            self.persisted_subs.pop(client_id, None)
            self.persisted_owner.pop(client_id, None)

        conn.subscriptions = inherited_subs
        self.clients[client_id] = conn

        writer.write(p.build_connack(session_present, p.CONNACK_ACCEPTED))
        await writer.drain()
        return conn

    def _check_credentials(self, username: Optional[str], password: Optional[bytes]) -> bool:
        """Answer whether the supplied credentials are valid; _handle_connect
        closes the connection when they aren't. When a password IS configured,
        the comparison here is the non-constant-time compare that is VULN #6."""
        required = self.cfg.require_pass
        if required is None:
            # No password configured at all: nothing to check, every CONNECT
            # is genuinely anonymous. A deployment that wants auth sets
            # MQB_REQUIREPASS, and _handle_connect enforces it.
            return True
        supplied = (password or b"").decode("utf-8", errors="replace")
        return hmac.compare_digest(supplied.encode(), required.encode())

    async def _read_loop(self, conn: ClientConn):
        while True:
            try:
                raw = await asyncio.wait_for(
                    p.read_packet(conn.reader), timeout=conn.keep_alive * self.cfg.keepalive_grace or None
                )
            except asyncio.TimeoutError:
                log.info("keepalive timeout for %r", conn.client_id)
                return
            if raw is None:
                return
            conn.last_activity = time.monotonic()

            if raw.ptype == p.PUBLISH:
                if not await self._handle_publish(conn, raw.flags, raw.body):
                    return  # ACL violation: drop the connection
            elif raw.ptype == p.PUBACK:
                self._handle_puback(conn, raw.body)
            elif raw.ptype == p.SUBSCRIBE:
                if not await self._handle_subscribe(conn, raw.body):
                    return  # ACL violation: drop the connection
            elif raw.ptype == p.UNSUBSCRIBE:
                await self._handle_unsubscribe(conn, raw.body)
            elif raw.ptype == p.PINGREQ:
                conn.writer.write(p.build_pingresp())
                await conn.writer.drain()
            elif raw.ptype == p.DISCONNECT:
                conn._graceful = True
                return
            else:
                log.info("unsupported/unexpected packet type %d from %r", raw.ptype, conn.client_id)
                return

    async def _on_disconnect(self, conn: ClientConn, graceful: bool):
        if self.clients.get(conn.client_id) is conn:
            del self.clients[conn.client_id]
        if not conn.clean_session:
            self.persisted_subs[conn.client_id] = dict(conn.subscriptions)
            self.persisted_owner[conn.client_id] = conn.username
        else:
            self.persisted_subs.pop(conn.client_id, None)
            self.persisted_owner.pop(conn.client_id, None)

        if not graceful and conn.will_topic is not None and not self.is_reserved(conn.will_topic):
            await self._route_publish(conn.will_topic, conn.will_message or b"", conn.will_qos, conn.will_retain)


    async def _handle_publish(self, conn: ClientConn, flags: int, body: bytes) -> bool:
        """Route one PUBLISH. Returns False if the client must be disconnected."""
        pub = p.parse_publish(flags, body)
        # Publish-side ACL: a client may not publish (retained or live) into
        # the broker-owned control namespace. MQTT 3.1.1 has no negative
        # PUBACK, so -- as HiveMQ and AWS IoT do -- the offending client is
        # disconnected and the message discarded. (VULN #3 was any client
        # being able to retain-publish over the seeded flag topic and poison
        # it for every later subscriber.) Other topics carry no per-client
        # ownership: the broker has one shared credential, not per-device
        # identities to check ownership against.
        if self.is_reserved(pub.topic):
            log.info("client %r published into reserved topic %r; disconnecting", conn.client_id, pub.topic)
            return False
        await self._route_publish(pub.topic, pub.payload, min(pub.qos, 1), pub.retain)

        if pub.qos == 1 and pub.packet_id is not None:
            conn.writer.write(p.build_puback(pub.packet_id))
            await conn.writer.drain()
        # QoS 2 is not implemented by this broker (see README); we downgrade
        # incoming QoS 2 PUBLISH to at-least-once delivery above and still
        # ack with PUBACK so QoS-2-capable clients don't hang, at the cost
        # of not honouring exactly-once semantics.
        return True

    async def _route_publish(self, topic: str, payload: bytes, qos: int, retain: bool):
        if retain:
            self._store_retained(topic, payload)

        # Topic ACL: nothing in the broker-owned control namespace is ever
        # delivered to a client subscription, whatever filter it used. (VULN
        # #2 was delivery being a pure filter match with no authorization, so
        # a bare "#" subscribe received the seeded flag.)
        if self.is_reserved(topic):
            return
        for target in list(self.clients.values()):
            for filt, granted_qos in target.subscriptions.items():
                if p.topic_matches(filt, topic):
                    await self._forward_to(target, topic, payload, min(qos, granted_qos))
                    break

    async def _forward_to(self, target: ClientConn, topic: str, payload: bytes, qos: int):
        if qos == 0:
            target.writer.write(p.build_publish(topic, payload, 0, False))
            return
        pid = target.alloc_packet_id()
        target.pending_ack[pid] = (topic, payload)
        target.writer.write(p.build_publish(topic, payload, 1, False, packet_id=pid))

    def _handle_puback(self, conn: ClientConn, body: bytes):
        try:
            pid = p.parse_puback(body)
        except p.MalformedPacket:
            return
        conn.pending_ack.pop(pid, None)

    async def _handle_subscribe(self, conn: ClientConn, body: bytes) -> bool:
        """Handle one SUBSCRIBE. Returns False if the client must be
        disconnected (it asked for the reserved control namespace)."""
        sub = p.parse_subscribe(body)
        return_codes = []
        newly_retained_deliveries = []
        for filt, req_qos in sub.filters:
            if self._filter_targets_reserved(filt):
                # Subscribing into the broker-owned control namespace is not
                # authorized for any client: SUBACK failure (0x80).
                return_codes.append(p.SUBACK_FAILURE)
                continue
            granted = min(req_qos, 1)  # this broker supports QoS 0/1 only
            conn.subscriptions[filt] = granted
            return_codes.append(granted)
            for topic, payload in self.retained.items():
                if self.is_reserved(topic):
                    continue  # never hand out control-namespace retained state
                if p.topic_matches(filt, topic):
                    newly_retained_deliveries.append((topic, payload, granted))

        conn.writer.write(p.build_suback(sub.packet_id, return_codes))
        await conn.writer.drain()
        if p.SUBACK_FAILURE in return_codes:
            # The SUBACK above tells the client which filter was refused; an
            # attempt on the control namespace then ends the session, same as
            # a denied PUBLISH.
            log.info("client %r subscribed into the reserved namespace; disconnecting", conn.client_id)
            return False
        for topic, payload, qos in newly_retained_deliveries:
            await self._forward_to(conn, topic, payload, qos)
        return True

    async def _handle_unsubscribe(self, conn: ClientConn, body: bytes):
        unsub = p.parse_unsubscribe(body)
        for filt in unsub.filters:
            conn.subscriptions.pop(filt, None)
        conn.writer.write(p.build_unsuback(unsub.packet_id))
        await conn.writer.drain()


    def _store_retained(self, topic: str, payload: bytes):
        if payload == b"":
            self.retained.pop(topic, None)
            path = retained_path(self.cfg.retain_dir, topic)
            try:
                os.remove(path)
            except OSError:
                pass
            return

        self.retained[topic] = payload
        path = retained_path(self.cfg.retain_dir, topic)
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "wb") as f:
                f.write(payload)
        except OSError as e:
            log.warning("failed to persist retained topic %r: %s", topic, e)


    def stats(self) -> dict:
        return {
            "clients_connected": len(self.clients),
            "retained_topics": len(self.retained),
            "clients": {
                cid: {
                    "subscriptions": list(c.subscriptions.keys()),
                    "inflight_out": len(c.pending_ack),
                }
                for cid, c in self.clients.items()
            },
        }

    def retained_list(self) -> dict:
        return {topic: len(payload) for topic, payload in self.retained.items()}
