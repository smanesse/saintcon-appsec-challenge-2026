# MQB — complete vulnerability list & PoCs

The six PoCs below target the intentionally-vulnerable MQB broker. All are
standalone Python 3, stdlib only, and self-verifying over the network — each
proves its bug *through the protocol* (publishing/subscribing through MQB and
reading the result back through MQB or its read-only admin HTTP side-channel)
and prints `[+]` on confirmed success /
`[-]` on failure.

At startup, MQB seeds a real per-deployment secret (`MQB_FLAG`, minted by
`../../generate-secrets.sh`) two ways — as a RETAINED message on a fixed
topic (`MQB_FLAG_TOPIC`, default `fleet/control/flag`) and as a plain file at
`MQB_FLAG_FILE` (default `/home/ctf/mqb/secret/flag.txt`), outside
`MQB_RETAIN_DIR` — via `Broker.seed_startup_state()` in `mqb/broker.py`. PoCs
`#1`, `#2`, `#3`, `#4`, and `#7` target that seeded secret directly.

**Recommended: run everything in Docker.** The compose file brings up an
`mqb` instance that HAS a password configured but never enforces it (VULN #1),
not published to the host. It carries a real `MQB_REQUIREPASS`, and the `poc`
runner is given the same value so PoCs #2–#5 and #7 authenticate as legitimate
clients (their bugs are orthogonal to auth); PoC #1 ignores it to prove the
anonymous bypass.

```
# builds the images, waits for mqb, runs PoC #1 (fail-open AUTH gate):
docker compose -f vuln_tests/docker-compose.yml run --build --rm poc

# run a different PoC (images already built):
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 04_client_id_collision_hijack.py mqb 1883
```

Or point a script at an already-running MQB directly:

```
python3 vuln_tests/01_no_auth_default.py [host] [port]   # defaults 127.0.0.1 1883
```

PoCs #5 and #7 also read the admin HTTP side-channel on the same host,
default port `8081` (override with a 3rd argv if needed).

**PoC #3 is destructive by design** — it retain-PUBLISHes poison straight
over the shared `fleet/control/flag` topic, which permanently replaces the
real seeded secret for that broker's remaining uptime (until something
retain-publishes the genuine value again). If you're running multiple PoCs
against the same long-lived `mqb` container, run #3 last, or bring the
`mqb` service back down/up (`docker compose down && docker compose run ...`)
between it and PoC #2/#4, which both expect the real flag still to be there.

## The list

| # | Vulnerability | Location | PoC |
|---|---------------|----------|-----|
| 1 | Fail-open AUTH gate: a configured password is reported in the CONNACK but never enforced → discloses the seeded flag to an anonymous client | `Broker._handle_connect()` in `broker.py` | `01_no_auth_default.py` |
| 2 | `#` wildcard subscription with no ACL → discloses the seeded flag via retained delivery | `Broker._route_publish()` in `broker.py` | `02_wildcard_subscribe_no_acl.py` |
| 3 | Retained-message poisoning → overwrites the seeded flag topic | `Broker._handle_subscribe()` in `broker.py` (delivery) + `Broker._store_retained()` (storage) | `03_retained_message_poisoning.py` |
| 4 | Client-ID collision session hijack → assumes the victim's authorized identity and recovers the seeded flag off its channel | `Broker._handle_connect()` in `broker.py` | `04_client_id_collision_hijack.py` |
| 5 | Unbounded in-flight QoS-1 table → memory-exhaustion DoS | `Broker._forward_to()` in `broker.py` | `05_unbounded_inflight_dos.py` |
| 7 | Path traversal in retained-message disk persistence → discloses the seeded flag file | `retained_path()` in `broker.py` (write side, via `_store_retained()`); `/admin/retained/export` in `admin.py` (read side) | `07_retained_persistence_path_traversal.py` |

There is also a further, deliberately un-numbered issue: cross-tenant/
cross-device `PUBLISH` with no ownership check (`Broker._handle_publish()`
accepts a `PUBLISH` to any topic from any client, including another device's
control topic). On its own that's command/message-integrity spoofing —
nothing disclosed, nothing DoSed — so per this repo's scoring contract (root
`README.md`, "Vulnerability requirements") it doesn't qualify as its own
scored PoC and isn't catalogued as one here. It's still real, exploitable
code, and it's exactly the missing check that #2 (read side) and #3 (write
side) both hang off — see "Notes on how these interact" below.

## Notes on how these interact

- **#1 is the master key for #2, #3, #4, and #5.** A password *is*
  configured, but #1 (the fail-open gate) means it's never enforced, so an
  unauthenticated stranger reaches all of them exactly as if no password
  existed. Actually *enforcing* the configured password (fixing #1 by closing
  the connection on a bad CONNACK) does not, by itself, fix any of #2–#5: it
  only gates *who can open a connection at all*. Real per-topic authorization
  (an ACL keyed to Client ID / username) would still be needed to close #2 and
  the un-numbered publish-ownership issue, since MQTT credentials are a
  connection-level concept and none of these bugs check topic ownership even
  for an authenticated client.

- **The un-numbered publish-ownership issue is the read/write halves of
  the same missing check that #2 and #3 exploit.** Nothing in
  `Broker._handle_publish()` ever asks "is this client allowed to touch
  this topic" — #2 is the read side (subscribe to `#` and receive the
  seeded flag's retained delivery); #3 is the write side (retain-publish
  straight over the same flag topic). Both would be fixed by the same ACL
  layer, checked at two different call sites.

- **#3 is the persistent version of the same missing check #2 reads
  from.** A live (non-retained) spoofed publish only reaches whoever is
  subscribed *right now* and is gone the instant it's delivered — no
  disclosure, no lasting damage, which is why it isn't scored on its own
  (see the un-numbered issue above). #3's retained poisoning is different:
  it persists until someone retain-publishes the genuine value again, so it
  reaches every subscriber that *ever* subscribes to the flag topic in the
  future, including a device that hasn't connected yet — a stored/
  persistent problem in the same spirit as stored XSS, except the
  persistence and replay mechanism here is MQTT's own retained-message
  feature working exactly as designed, aimed at a topic nobody had any
  business writing to.

- **#4 (session hijack) and #5 (unbounded in-flight table) both abuse
  *session state that outlives a single TCP connection*, for opposite
  reasons.** #4 is triggered by the broker keeping subscriptions around
  across a `CleanSession=0` reconnect with no identity check on who is
  reconnecting — including the victim's authorized subscription to the seeded
  flag topic. As the impersonated (now-authorized) victim, the attacker then
  pulls the retained real `MQB_FLAG` off that channel — the scored outcome, and
  what distinguishes #4 from #2: a per-client ACL that stops #2's stranger does
  not stop a hijacker who has become the victim. The one victim connection
  getting kicked offline is
  reported as proof the takeover mechanism fired, not claimed as a second,
  independent scoreable DoS (a single-connection knockout doesn't cost the
  shared service anything — see the root README's scoring contract). #5 is
  triggered by the broker keeping per-message state (`pending_ack`) for a
  connection that never goes away and never drains its backlog. Neither fix
  touches the other: requiring the same credentials to resume a session
  fixes #4 but does nothing about an authenticated slow consumer still being
  able to grow an unbounded backlog (#5); capping in-flight messages fixes
  #5 but does nothing about identity-free session takeover (#4).

- **#5's severity is amplified by #1 and #2 together.** Because there's no
  auth (#1) and no ACL (#2), an attacker doesn't even need to know a real
  device's Client ID or topics to run this DoS — it can create its own
  throwaway subscriber, subscribe to its own throwaway topic, and flood
  itself, exhausting broker memory that's shared across every other client's
  connection.

- **#7 has two independent primitives sharing one vulnerable helper.**
  `retained_path()` computes a filesystem path directly from a client
  topic string with no containment check. The *write* side (a retained
  `PUBLISH`) turns this into an arbitrary file write; the *read* side
  (`/admin/retained/export`) turns it into an arbitrary file read that
  reaches the seeded flag file at `MQB_FLAG_FILE` — a file this module's own
  `Broker.seed_startup_state()` writes at startup, entirely outside
  `MQB_RETAIN_DIR`. They fail independently — sanitizing only the write path
  still leaves the export endpoint able to read any file the broker process
  can access, and vice versa — but because both call the same helper, the
  one-line fix (canonicalize + prefix-check inside `retained_path()`) closes
  both at once.

## Fix directions (brief — save the detail for when they ask)

1. **Fail-open AUTH gate:** actually *enforce* the credential result — in
   `Broker._handle_connect()`, when `_check_credentials()` returns False, send
   the failure CONNACK and `return None` to close the connection (MQTT-3.2.2-5),
   instead of falling through and serving the session. Reporting rc=4 while
   still honouring the session is worse than no auth: it looks protected. (And
   don't run a writable broker without a configured `MQB_REQUIREPASS` at all —
   refuse to start, or bind only to loopback, when it's unset.)
2. **No topic ACL:** add an authorization layer that maps an authenticated
   client identity to the topic filters/prefixes it may subscribe to, and
   deny `SUBSCRIBE`s (or narrow the granted filter) outside that set —
   Mosquitto's `acl_file` is the canonical version of this. This also closes
   the un-numbered publish-ownership issue (add the write-side counterpart:
   deny `PUBLISH` to a topic the client doesn't own or isn't authorized to
   command) and, combined with #3's fix below, keeps a spoofed/poisoned
   publish off `fleet/control/flag` in the first place.
3. **Retained-message poisoning:** apply the same publish-side ACL to
   retained `PUBLISH`es specifically (they're higher-value, since they
   persist), and/or cap how long a retained message survives without being
   refreshed by its legitimate owner.
4. **Session hijack:** tie session resumption to the same credential that
   authenticated the original session (not just the Client ID), and/or
   require a fresh CONNECT's identity to match the previous one via a
   pre-shared per-device secret before honoring `CleanSession=0`.
5. **Unbounded in-flight table:** enforce a small `max_inflight_messages`
   per client (Mosquitto's default is 20); once full, stop forwarding new
   QoS-1 messages to that subscriber (or disconnect it) until it PUBACKs.
7. **Path traversal:** reject any topic used to derive a retained-message
   filename if it contains `..` segments or resolves (via
   `os.path.realpath`) outside `MQB_RETAIN_DIR`; better, derive the on-disk
   filename from a hash of the topic rather than the topic text itself.
