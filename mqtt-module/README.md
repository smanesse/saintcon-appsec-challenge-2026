# MQB — MQTT Module

MQB is a small **MQTT 3.1.1** message broker for a fleet of IoT devices, in
the spirit of Mosquitto/HiveMQ. It speaks the real MQTT wire format — a
hand-rolled fixed-header/variable-header/payload parser and serializer over a
raw TCP socket, no MQTT client/broker library involved — and implements
CONNECT/CONNACK, PUBLISH, SUBSCRIBE/SUBACK, UNSUBSCRIBE/UNSUBACK,
PINGREQ/PINGRESP, DISCONNECT, Last Will and Testament, QoS 0 and 1, retained
messages, and the `+`/`#` topic wildcards. A small HTTP admin side-channel on
a separate port gives read-only visibility into connected clients and
retained topics.

It is written in Python (asyncio for the MQTT listener, a threaded HTTP
server for the admin side-channel), for a security course.

> ⚠️ **This service is INTENTIONALLY VULNERABLE.** It exists to be attacked in
> a course setting. It contains deliberate, planted security bugs and
> disables protections a real broker would have. **Never deploy it, expose it
> to an untrusted network, or point it at infrastructure you don't fully
> control.** This functional reference does not discuss the planted security
> issues.

## Connection

| Property        | Value                                                          |
|-----------------|-----------------------------------------------------------------|
| MQTT transport  | Raw TCP on `MQB_PORT` (default `1883`)                          |
| Admin transport | HTTP on `MQB_ADMIN_PORT` (default `8081`)                        |
| Protocol        | MQTT 3.1.1 (OASIS), protocol level `4`                           |
| QoS levels      | 0 (at most once) and 1 (at least once). QoS 2 is not implemented — a QoS-2 PUBLISH is accepted and delivered at QoS 1, and a QoS-2 SUBSCRIBE is granted at QoS 1. |
| Concurrency     | One asyncio task per connection, many simultaneous clients       |
| Authentication  | Off unless `MQB_REQUIREPASS` is set (then CONNECT must carry the matching password; any/no username is accepted) |
| Downstream deps | None — MQB is standalone                                        |

### Configuration (environment variables)

| Variable           | Default            | Meaning                                             |
|--------------------|---------------------|------------------------------------------------------|
| `MQB_HOST`         | `0.0.0.0`           | MQTT bind address                                    |
| `MQB_PORT`         | `1883`              | MQTT bind port (`SERVER_PORT` overrides)             |
| `MQB_ADMIN_HOST`   | `0.0.0.0`           | Admin HTTP bind address                              |
| `MQB_ADMIN_PORT`   | `8081`              | Admin HTTP bind port                                 |
| `MQB_REQUIREPASS`  | *(unset)*           | If set, CONNECT must supply this password             |
| `MQB_RETAIN_DIR`   | `./retained`        | Directory retained messages are persisted into, one file per topic |
| `MQB_KEEPALIVE_GRACE` | `1.5`            | Multiplier applied to a client's declared Keep Alive before the broker times it out |

Any MQTT 3.1.1 client library (paho-mqtt, mosquitto_pub/sub, etc.) can talk
to MQB directly; see [`unit_tests/test_mqb.py`](unit_tests/test_mqb.py) for a
complete hand-rolled Python client if you'd rather not pull in a dependency.

## MQTT packet reference

### CONNECT / CONNACK

A client sends CONNECT first; every other packet before a successful
CONNACK is ignored (the connection is dropped instead of accepting a
premature packet).

| CONNACK return code | Meaning                                            |
|----------------------|-----------------------------------------------------|
| `0`                  | Accepted                                            |
| `1`                  | Unacceptable protocol version (protocol level != 4) |
| `2`                  | Identifier rejected (empty Client ID with `CleanSession=0`, or Client ID already connected) |
| `4`                  | Bad username or password (only when `MQB_REQUIREPASS` is set) |

The CONNACK's Session Present flag is `1` when the client reconnected with
`CleanSession=0` and the broker still held session state (subscriptions)
for that Client ID from a previous connection; otherwise `0`.

An empty Client ID is allowed only when `CleanSession=1`, in which case the
broker assigns one (`mqb-auto-<random>`).

A CONNECT whose Client ID is already in use by a live connection is refused
with return code `2`; the existing connection is not disturbed. A stored
persistent session is resumed only by a CONNECT carrying the same username
it was created under.

Last Will and Testament (Will Topic/Message/QoS/Retain in CONNECT) is
supported: if the connection ends without a clean DISCONNECT, the Will
message is published as though the client had PUBLISHed it itself. A
graceful DISCONNECT suppresses the Will.

### PUBLISH / PUBACK

| Field    | Notes |
|----------|-------|
| Topic    | Any UTF-8 string using `/` as the level separator. `+` and `#` are wildcard characters reserved for *filters* and must not appear in a PUBLISH topic. |
| QoS      | 0 or 1 (2 is downgraded to 1; see above) |
| Retain   | If set, the payload becomes the topic's retained message (see below) |
| Payload  | Arbitrary bytes |

A QoS-1 PUBLISH is answered with PUBACK (matching Packet Identifier) once
the broker has accepted it for routing. QoS-0 PUBLISH gets no acknowledgement.
An empty payload with Retain set clears any existing retained message for
that topic.

Topics in the broker-owned control namespace (the parent of
`MQB_FLAG_TOPIC`, `fleet/control/` by default) cannot be published to: a
PUBLISH there is discarded and the client is disconnected.

### SUBSCRIBE / SUBACK, UNSUBSCRIBE / UNSUBACK

SUBSCRIBE carries one or more `(topic filter, requested QoS)` pairs; SUBACK
returns one granted-QoS byte per filter, in the same order (`0`, `1`, or
`0x80` for failure — returned for a filter that names the broker-owned
control namespace, the parent of `MQB_FLAG_TOPIC`, `fleet/control/` by
default; wildcard filters such as `#` never match topics in that namespace).
A client whose SUBSCRIBE is refused this way is disconnected after the SUBACK. Immediately after SUBACK, any currently retained message
matching the new filter is delivered as a PUBLISH.

Filters support the standard MQTT wildcards:
- `+` matches exactly one topic level (`devices/+/state` matches
  `devices/a/state` but not `devices/a/b/state`).
- `#` matches that level and everything after it, and must be the last
  character of the filter (`devices/#` matches `devices`, `devices/a`,
  `devices/a/b`, …).
- A leading `+`/`#` does not match topics whose first level starts with
  `$` unless the filter itself starts with `$` (matches real broker
  behaviour for topics like `$SYS/...`).

UNSUBSCRIBE removes one or more filters; UNSUBACK carries the matching
Packet Identifier with no payload.

### PINGREQ / PINGRESP, DISCONNECT

PINGREQ gets an immediate PINGRESP. If no packet (of any kind) arrives from
a client within `Keep Alive × MQB_KEEPALIVE_GRACE` seconds, the broker
closes the connection. DISCONNECT closes the connection cleanly (no Will is
sent).

## Admin HTTP API

| Method | Path                                | Effect                                                          |
|--------|-------------------------------------|-------------------------------------------------------------------|
| GET    | `/health`                           | liveness probe → `200 ok`                                        |
| GET    | `/admin/stats`                      | JSON: connected client count, and per-client subscriptions + in-flight (un-acked QoS-1) count |
| GET    | `/admin/retained`                   | JSON: every retained topic and its payload size                  |
| GET    | `/admin/retained/export?topic=<t>`  | Returns the raw bytes persisted on disk for retained topic `<t>` |

| Status           | When                                              |
|------------------|-----------------------------------------------------|
| `200 OK`         | Request succeeded                                  |
| `400 Bad Request`| `/admin/retained/export` with no `?topic=`         |
| `404 Not Found`  | Unknown path, or no persisted file for that topic  |

## Minimal client session

Using `mosquitto_pub`/`mosquitto_sub` against a locally-run broker:

```
$ mosquitto_sub -h 127.0.0.1 -p 1883 -t 'devices/+/telemetry' &
$ mosquitto_pub -h 127.0.0.1 -p 1883 -t 'devices/thermostat-01/telemetry' -m '{"tempC":21.4}'
{"tempC":21.4}

$ mosquitto_pub -h 127.0.0.1 -p 1883 -t 'devices/thermostat-01/config' -r -m '{"target":21.0}'
$ mosquitto_sub -h 127.0.0.1 -p 1883 -t 'devices/thermostat-01/config' -C 1
{"target":21.0}
```

Or purely with Python stdlib (no `mosquitto_pub`/`paho-mqtt` needed) — see
[`unit_tests/test_mqb.py`](unit_tests/test_mqb.py) for a complete
hand-rolled MQTT client the tests drive it with.

## Build & run

```
docker build -t mqb .
docker run --rm -p 1883:1883 -p 8081:8081 mqb   # for local poking only; never expose it

# functional tests, entirely in Docker (server never binds a host port):
./unit_tests/run-in-docker.sh
```
