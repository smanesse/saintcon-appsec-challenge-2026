from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

CONNECT = 1
CONNACK = 2
PUBLISH = 3
PUBACK = 4
PUBREC = 5
PUBREL = 6
PUBCOMP = 7
SUBSCRIBE = 8
SUBACK = 9
UNSUBSCRIBE = 10
UNSUBACK = 11
PINGREQ = 12
PINGRESP = 13
DISCONNECT = 14

CONNACK_ACCEPTED = 0
CONNACK_BAD_PROTOCOL_VERSION = 1
CONNACK_IDENTIFIER_REJECTED = 2
CONNACK_SERVER_UNAVAILABLE = 3
CONNACK_BAD_USERNAME_PASSWORD = 4
CONNACK_NOT_AUTHORIZED = 5

SUBACK_FAILURE = 0x80

PROTOCOL_LEVEL_3_1_1 = 4


class MalformedPacket(Exception):
    pass



def encode_remaining_length(n: int) -> bytes:
    if n < 0 or n > 268435455:
        raise ValueError("remaining length out of range")
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


async def read_remaining_length(reader) -> int:
    multiplier = 1
    value = 0
    for _ in range(4):
        b = (await reader.readexactly(1))[0]
        value += (b & 0x7F) * multiplier
        if not (b & 0x80):
            return value
        multiplier *= 128
    raise MalformedPacket("remaining length varint too long")


def encode_utf8(s: str) -> bytes:
    data = s.encode("utf-8")
    if len(data) > 0xFFFF:
        raise ValueError("string too long for MQTT UTF-8 field")
    return struct.pack("!H", len(data)) + data


def decode_utf8(buf: bytes, offset: int) -> Tuple[str, int]:
    if offset + 2 > len(buf):
        raise MalformedPacket("truncated UTF-8 string length")
    (length,) = struct.unpack_from("!H", buf, offset)
    offset += 2
    if offset + length > len(buf):
        raise MalformedPacket("truncated UTF-8 string body")
    s = buf[offset:offset + length].decode("utf-8", errors="strict")
    return s, offset + length



@dataclass
class RawPacket:
    ptype: int
    flags: int
    body: bytes


async def read_packet(reader) -> Optional[RawPacket]:
    try:
        first = await reader.readexactly(1)
    except Exception:
        return None
    b0 = first[0]
    ptype = (b0 >> 4) & 0x0F
    flags = b0 & 0x0F
    remaining = await read_remaining_length(reader)
    body = await reader.readexactly(remaining) if remaining else b""
    return RawPacket(ptype, flags, body)


def build_fixed_header(ptype: int, flags: int, body: bytes) -> bytes:
    return bytes([(ptype << 4) | (flags & 0x0F)]) + encode_remaining_length(len(body)) + body



@dataclass
class ConnectPacket:
    protocol_name: str
    protocol_level: int
    clean_session: bool
    keep_alive: int
    client_id: str
    will_topic: Optional[str] = None
    will_message: Optional[bytes] = None
    will_qos: int = 0
    will_retain: bool = False
    username: Optional[str] = None
    password: Optional[bytes] = None


def parse_connect(body: bytes) -> ConnectPacket:
    offset = 0
    protocol_name, offset = decode_utf8(body, offset)
    if offset + 4 > len(body):
        raise MalformedPacket("truncated CONNECT variable header")
    protocol_level = body[offset]
    offset += 1
    connect_flags = body[offset]
    offset += 1
    (keep_alive,) = struct.unpack_from("!H", body, offset)
    offset += 2

    username_flag = bool(connect_flags & 0x80)
    password_flag = bool(connect_flags & 0x40)
    will_retain = bool(connect_flags & 0x20)
    will_qos = (connect_flags >> 3) & 0x03
    will_flag = bool(connect_flags & 0x04)
    clean_session = bool(connect_flags & 0x02)

    client_id, offset = decode_utf8(body, offset)

    will_topic = will_message = None
    if will_flag:
        will_topic, offset = decode_utf8(body, offset)
        if offset + 2 > len(body):
            raise MalformedPacket("truncated will message length")
        (wlen,) = struct.unpack_from("!H", body, offset)
        offset += 2
        will_message = body[offset:offset + wlen]
        offset += wlen

    username = None
    if username_flag:
        username, offset = decode_utf8(body, offset)

    password = None
    if password_flag:
        if offset + 2 > len(body):
            raise MalformedPacket("truncated password length")
        (plen,) = struct.unpack_from("!H", body, offset)
        offset += 2
        password = body[offset:offset + plen]
        offset += plen

    return ConnectPacket(
        protocol_name=protocol_name,
        protocol_level=protocol_level,
        clean_session=clean_session,
        keep_alive=keep_alive,
        client_id=client_id,
        will_topic=will_topic,
        will_message=will_message,
        will_qos=will_qos,
        will_retain=will_retain,
        username=username,
        password=password,
    )


def build_connack(session_present: bool, return_code: int) -> bytes:
    body = bytes([1 if session_present else 0, return_code])
    return build_fixed_header(CONNACK, 0, body)



@dataclass
class PublishPacket:
    topic: str
    payload: bytes
    qos: int
    retain: bool
    dup: bool
    packet_id: Optional[int] = None


def parse_publish(flags: int, body: bytes) -> PublishPacket:
    dup = bool(flags & 0x08)
    qos = (flags >> 1) & 0x03
    retain = bool(flags & 0x01)
    offset = 0
    topic, offset = decode_utf8(body, offset)
    packet_id = None
    if qos > 0:
        if offset + 2 > len(body):
            raise MalformedPacket("truncated PUBLISH packet id")
        (packet_id,) = struct.unpack_from("!H", body, offset)
        offset += 2
    payload = body[offset:]
    return PublishPacket(topic=topic, payload=payload, qos=qos, retain=retain, dup=dup, packet_id=packet_id)


def build_publish(topic: str, payload: bytes, qos: int, retain: bool, dup: bool = False,
                   packet_id: Optional[int] = None) -> bytes:
    flags = (1 if dup else 0) << 3 | (qos & 0x03) << 1 | (1 if retain else 0)
    body = bytearray(encode_utf8(topic))
    if qos > 0:
        if packet_id is None:
            raise ValueError("packet_id required for QoS > 0 PUBLISH")
        body += struct.pack("!H", packet_id)
    body += payload
    return build_fixed_header(PUBLISH, flags, bytes(body))


def build_puback(packet_id: int) -> bytes:
    return build_fixed_header(PUBACK, 0, struct.pack("!H", packet_id))


def parse_puback(body: bytes) -> int:
    if len(body) < 2:
        raise MalformedPacket("truncated PUBACK")
    (packet_id,) = struct.unpack_from("!H", body, 0)
    return packet_id



@dataclass
class SubscribePacket:
    packet_id: int
    filters: List[Tuple[str, int]] = field(default_factory=list)


def parse_subscribe(body: bytes) -> SubscribePacket:
    if len(body) < 2:
        raise MalformedPacket("truncated SUBSCRIBE")
    (packet_id,) = struct.unpack_from("!H", body, 0)
    offset = 2
    filters = []
    while offset < len(body):
        topic_filter, offset = decode_utf8(body, offset)
        if offset >= len(body):
            raise MalformedPacket("truncated SUBSCRIBE requested QoS")
        qos = body[offset] & 0x03
        offset += 1
        filters.append((topic_filter, qos))
    if not filters:
        raise MalformedPacket("SUBSCRIBE with no topic filters")
    return SubscribePacket(packet_id=packet_id, filters=filters)


def build_suback(packet_id: int, return_codes: List[int]) -> bytes:
    body = struct.pack("!H", packet_id) + bytes(return_codes)
    return build_fixed_header(SUBACK, 0, body)


@dataclass
class UnsubscribePacket:
    packet_id: int
    filters: List[str] = field(default_factory=list)


def parse_unsubscribe(body: bytes) -> UnsubscribePacket:
    if len(body) < 2:
        raise MalformedPacket("truncated UNSUBSCRIBE")
    (packet_id,) = struct.unpack_from("!H", body, 0)
    offset = 2
    filters = []
    while offset < len(body):
        topic_filter, offset = decode_utf8(body, offset)
        filters.append(topic_filter)
    return UnsubscribePacket(packet_id=packet_id, filters=filters)


def build_unsuback(packet_id: int) -> bytes:
    return build_fixed_header(UNSUBACK, 0, struct.pack("!H", packet_id))



def build_pingresp() -> bytes:
    return build_fixed_header(PINGRESP, 0, b"")



def topic_matches(topic_filter: str, topic: str) -> bool:
    if topic_filter == topic:
        return True

    f_levels = topic_filter.split("/")
    t_levels = topic.split("/")

    if t_levels and t_levels[0].startswith("$") and not (f_levels and f_levels[0].startswith("$")):
        return False

    fi = 0
    ti = 0
    while fi < len(f_levels):
        f = f_levels[fi]
        if f == "#":
            return True
        if ti >= len(t_levels):
            return False
        if f != "+" and f != t_levels[ti]:
            return False
        fi += 1
        ti += 1
    return ti == len(t_levels)
