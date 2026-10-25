# Mail Module (MTA)

MTA is a small **outbound mail relay / submission agent** that speaks real
**SMTP** (RFC 5321) over a hand-rolled TCP parser - plain Node.js
`net.Socket`, no SMTP library. It accepts mail over the wire (HELO/EHLO,
MAIL FROM, RCPT TO, DATA, RSET, NOOP, AUTH, STARTTLS, QUIT) and queues each
accepted message into a maildir-style on-disk spool. A small HTTP **admin
side-channel** lets you list and inspect the queue (the equivalent of a real
MTA's `mailq`/`postqueue -p`) and view the bounce-notification log.

It is written in JavaScript for a security course.

> ⚠️ **This service is deliberately, intentionally vulnerable.** It parses a
> real wire protocol by hand with no input validation in several places, and
> disables the mitigations a production mail relay would have. It exists to
> be attacked in a lab. **Do not deploy it on any network you do not fully
> control.** This document describes only the *intended* functionality.

## Connection

| Property         | Value                                                          |
|------------------|-----------------------------------------------------------------|
| SMTP transport   | Raw TCP on `MTA_PORT` (default `2525`; `SERVER_PORT` also wins) |
| Admin transport  | HTTP on `MTA_ADMIN_PORT` (default `8081`)                       |
| Wire format      | RFC 5321 SMTP command lines (`\r\n`-terminated)                 |
| Encoding         | ASCII commands; message bodies are treated as opaque bytes      |
| Concurrency      | One session object per TCP connection                          |
| STARTTLS         | Supported (RFC 3207) - upgrades the connection in place         |
| Downstream deps  | None to run standalone. Optionally MX-routes outbound mail via a fleet DNS server (`MTA_RESOLVER`) |

### Configuration (environment variables)

| Variable            | Default                          | Meaning                                                   |
|----------------------|-----------------------------------|------------------------------------------------------------|
| `MTA_HOST`           | `0.0.0.0`                         | bind address for both SMTP and admin HTTP                  |
| `MTA_PORT`           | `2525`                            | SMTP listen port (`SERVER_PORT` overrides)                  |
| `MTA_ADMIN_PORT`     | `8081`                            | admin HTTP listen port                                     |
| `MTA_DOMAIN`         | `mta.local`                       | this server's own delivery domain                           |
| `MTA_QUEUE_DIR`      | `./queue`                         | maildir-style queue root (`<dir>/new` holds accepted mail)  |
| `MTA_LOCAL_USERS`    | `alice,bob,postmaster`            | known local mailboxes at `MTA_DOMAIN`                       |
| `MTA_AUTH_USER`      | `relay`                           | AUTH PLAIN/LOGIN username                                   |
| `MTA_AUTH_PASS`      | `relay123`                        | AUTH PLAIN/LOGIN password                                   |
| `MTA_BOUNCE_SCRIPT`  | `./scripts/notify-bounce.sh`      | script invoked on a bounce notification                     |
| `MTA_BOUNCE_LOG`     | `./data/bounces.log`              | where the bounce script logs                                |
| `MTA_TLS_KEY`/`MTA_TLS_CERT` | `./certs/dev-{key,cert}.pem` | STARTTLS certificate/key                                    |
| `MTA_WEBHOOK_TIMEOUT_MS` | `5000`                        | timeout for the notify-webhook callback                     |
| `MTA_RESOLVER`       | *(unset)*                        | fleet DNS server (`host` or `host:port`, e.g. `dnsm:8053`) for MX routing. Unset -> spool only, no outbound relay |
| `MTA_RELAY_PORT`     | `25`                             | next-hop SMTP port used when relaying a resolved message      |
| `MTA_RELAY_TIMEOUT_MS` | `8000`                         | per-delivery timeout for the outbound relay connection        |

## SMTP command reference

Connecting immediately gets a banner:

```
220 <MTA_DOMAIN> ESMTP MTA Service ready
```

| Command | Effect | Replies |
|---------|--------|---------|
| `HELO <domain>` | starts a session (basic SMTP), resets any in-progress transaction | `250 <domain> Hello <name>` |
| `EHLO <domain>` | starts a session (extended SMTP), resets any in-progress transaction | multi-line `250-...` ending `250 HELP`, advertising `PIPELINING`, `8BITMIME`, `AUTH PLAIN LOGIN`, and `STARTTLS` (while not already on TLS) |
| `MAIL FROM:<addr> [AUTH=<xtext>]` | opens a new mail transaction | `250 2.1.0 Ok`; `501 5.5.4` on bad syntax |
| `RCPT TO:<addr>` | adds a recipient to the current transaction (any destination domain is accepted - this is a relay) | `250 2.1.5 Ok`; `501 5.1.3` on bad address syntax; `503 5.5.1` if no `MAIL FROM` yet |
| `DATA` | begins the message body; reply `354`, then send headers + body, ending with a line containing only `.` | `354 End data with <CR><LF>.<CR><LF>`; `503 5.5.1` if no recipients yet; on completion, `250 2.0.0 Ok: queued as <name>` |
| `RSET` | clears the current transaction | `250 2.0.0 Ok` |
| `NOOP` | no-op | `250 2.0.0 Ok` |
| `STARTTLS` | upgrades the connection to TLS (RFC 3207) | `220 2.0.0 Ready to start TLS`, then a TLS handshake begins; `503 5.5.1` if already on TLS; `454 4.7.0` if no certificate is configured |
| `AUTH PLAIN [initial-response]` | SASL PLAIN authentication | `334 ` prompt if no initial response given, then a base64 continuation line; `235 2.7.0` on success; `535 5.7.8` on failure |
| `AUTH LOGIN` | SASL LOGIN authentication | `334 <base64 "Username:">`, then `334 <base64 "Password:">`, then `235`/`535` |
| `QUIT` | ends the session | `221 2.0.0 Bye`, then the connection closes |
| anything else | unrecognized command | `502 5.5.2 Command not recognized` |

DATA-phase lines beginning with `.` have that leading dot un-stuffed per RFC
5321 §4.5.2 (so a body line that is literally `.` doesn't end the message
early - send `..` instead).

Headers recognized out of the message body: `Message-ID` (used to name the
queued file), `Subject` (recorded in the queue listing), and
`X-Notify-Webhook: <url>` (a delivery-status callback - see below).

### Status code summary

| Code | Meaning |
|------|---------|
| `220` | greeting / ready to proceed (banner, STARTTLS) |
| `221` | closing connection |
| `235` | authentication succeeded |
| `250` | requested action completed |
| `334` | continue with the next line (AUTH challenge) |
| `354` | start message input |
| `454` | TLS temporarily unavailable |
| `501` | syntax error in parameters |
| `502` | command not recognized |
| `503` | bad sequence of commands |
| `504` | unrecognized authentication mechanism |
| `535` | authentication failed |

## Outbound relay (DNS-routed)

By default an accepted message is written to the on-disk spool and that's the
end of it (a submission agent whose downstream worker is out of scope). When
`MTA_RESOLVER` is set, the server additionally **relays** each accepted message
for a *remote* domain (anything other than `MTA_DOMAIN`): it looks up the
recipient domain's `MX` (falling back to the domain's own `A` record when there
is no `MX`) through that resolver, connects to the resulting next hop on
`MTA_RELAY_PORT`, and hands the message over with a normal SMTP transaction
(`EHLO`/`MAIL`/`RCPT`/`DATA`/`QUIT`). The outcome (next hop, `MX` host, and a
`delivered`/`deferred`/`rejected` status) is attached to the message in the
admin queue view. Relay is best-effort and asynchronous - the submitting client
still gets its `250 ... queued` as soon as the message is spooled.

In the fleet this resolver is DNSM. The server trusts whatever address DNSM
returns with no validation, which is the point of routing naming through a
single authoritative server the rest of the fleet also trusts.

## Delivery-status webhook

A message may carry `X-Notify-Webhook: <url>` in its headers. If the
session is authenticated (via `AUTH`), once the message is queued the
server POSTs a small JSON receipt (`{queued, from, to}`) to that URL and
records the response against the message. Unauthenticated senders may still
send the header; it is simply ignored.

## Admin HTTP API

| Method | Path | Effect |
|--------|------|--------|
| `GET` | `/health` | liveness probe → `200 {"status":"ok"}` |
| `GET` | `/queue` | JSON array of every queued message's metadata (`name`, `from`, `to`, `subject`, `size`, `receivedAt`, `webhook`) |
| `GET` | `/queue/<name>` | JSON metadata plus the full raw message content (`raw`) for one queued message; `404` if not found |
| `GET` | `/bounces` | plain-text bounce-notification log |

## Minimal client session

Using `nc` (or any raw TCP client) against a locally-run server:

```
$ nc 127.0.0.1 2525
220 mta.local ESMTP MTA Service ready
EHLO client.example.com
250-mta.local Hello client.example.com
250-PIPELINING
250-8BITMIME
250-AUTH PLAIN LOGIN
250-STARTTLS
250 HELP
MAIL FROM:<alice@example.com>
250 2.1.0 Ok
RCPT TO:<bob@somewhere.example>
250 2.1.5 Ok
DATA
354 End data with <CR><LF>.<CR><LF>
Subject: hello

This is the message body.
.
250 2.0.0 Ok: queued as 1732000000000.abcdef123456.eml
QUIT
221 2.0.0 Bye
```

Then, from another shell:

```
$ curl -s http://127.0.0.1:8081/queue
$ curl -s http://127.0.0.1:8081/queue/1732000000000.abcdef123456.eml
```

Or purely with Python stdlib (no `nc` needed) - see
[`unit_tests/test_mail.py`](unit_tests/test_mail.py) for a complete client
the tests drive it with.

## Build & run

```
npm install    # no dependencies - stdlib only, this is a no-op
node src/server.js     # SMTP :2525, admin :8081

# or in Docker, off the host:
docker build -t mta .
docker run --rm -p 2525:2525 -p 8081:8081 mta   # local poking only; never expose it

# functional tests, entirely in Docker (server never binds a host port):
./unit_tests/run-in-docker.sh
```
