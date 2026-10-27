# DNS Module (DNSM)

DNSM is a small **authoritative DNS server** that speaks the real RFC 1035 wire
format. It loads a zone file at startup and answers queries for names it is
authoritative for over **UDP**, with **TCP** fallback on the same port for
large answers and for **AXFR** full zone transfers. Names outside its zone are
resolved by **forwarding** to an upstream resolver and relaying the reply. A
small **HTTP admin side-channel** on a separate port lets operators reload the
zone and import zone updates (from a URL or a named file in the zone
directory).

It is written in C with hand-rolled binary message parsing, in the spirit of
classic name servers (djbdns/NSD/BIND-style), for a security course.

> ⚠️ **This service is deliberately, intentionally vulnerable.** It parses
> attacker-controlled binary DNS messages by hand in C with compiler
> mitigations turned off. It exists to be attacked in a lab. **Do not deploy it
> on any network you do not fully control.** This document describes only the
> *intended* functionality.

## Connection

| Property        | Value                                                            |
|-----------------|------------------------------------------------------------------|
| DNS transport   | UDP and TCP on `DNSM_PORT` (default `8053`)                       |
| Admin transport | HTTP on `DNSM_ADMIN_PORT` (default `8080`)                        |
| Wire format     | RFC 1035 (12-byte header, question + RR sections, label encoding)|
| Record types    | `A`, `AAAA`, `CNAME`, `TXT`, `NS`, `MX` (plus `SOA` at the apex)  |
| Query types     | the above + `AXFR` (252) and `ANY` (255)                         |
| Concurrency     | thread-per-request (UDP datagram / TCP connection)               |
| Upstream        | `DNSM_UPSTREAM` (`host:port`) for out-of-zone recursion           |

### Configuration (environment variables)

| Variable            | Default                | Meaning                                            |
|---------------------|------------------------|----------------------------------------------------|
| `DNSM_PORT`         | `8053`                 | UDP + TCP DNS listen port                          |
| `DNSM_ADMIN_PORT`   | `8080`                 | HTTP admin listen port                             |
| `DNSM_FORWARD_PORT` | `8054`                 | source port used for upstream queries              |
| `DNSM_UPSTREAM`     | `8.8.8.8:53`           | upstream resolver for out-of-zone names            |
| `DNSM_ZONE_FILE`    | `./zones/example.zone` | zone file loaded at startup / on reload            |
| `DNSM_ZONE_DIR`     | `./zones`              | base directory for admin file import               |

## Zone file format

A simplified master-file format (see [`zones/example.zone`](zones/example.zone)):

```
$ORIGIN example.com.
$TTL 300
@     SOA   ns1.example.com. hostmaster.example.com. 2026072201 3600 600 1209600 300
@     NS    ns1.example.com.
@     A     192.0.2.10
www   A     192.0.2.10
www   AAAA  2001:db8::10
@     MX    10 mail.example.com.
ftp   CNAME www.example.com.
info  TXT   "some text" "more text"
```

Names without a trailing dot are relative to `$ORIGIN`; `@` is the origin
itself. Lines beginning with `;` are comments.

## DNS query behaviour

For a standard query (`QR=0`, one question):

- **In-zone name, records exist** → `NOERROR` response with `AA=1` and the
  matching records in the answer section. `CNAME`s are followed and both the
  `CNAME` and the target's records are returned. An `ANY` (255) query returns
  all record types for the name.
- **In-zone name, no matching records** → `NXDOMAIN` (`RCODE=3`), no answers.
- **Out-of-zone name** → the query is forwarded to `DNSM_UPSTREAM` and the
  reply is relayed back (recursion). If forwarding fails → `SERVFAIL`
  (`RCODE=2`).
- **UDP vs TCP**: identical query semantics. Use TCP (2-byte length prefix, per
  RFC 1035 §4.2.2) for large answers.
- **AXFR (252), TCP only** → the full zone is streamed back (SOA, every record,
  SOA) in the answer section.

### RCODE summary

| RCODE | Name     | When                                                    |
|-------|----------|---------------------------------------------------------|
| 0     | NOERROR  | in-zone name with matching records, or a relayed answer |
| 2     | SERVFAIL | out-of-zone name whose upstream forward failed          |
| 3     | NXDOMAIN | in-zone name with no matching records                   |

## Admin HTTP API

| Method    | Path                              | Effect                                                        |
|-----------|-----------------------------------|--------------------------------------------------------------|
| GET       | `/health`                         | liveness probe → `200 ok`                                     |
| GET       | `/zone?name=<name>`               | return the text of `<DNSM_ZONE_DIR>/<name>` (public, no token) |
| POST      | `/admin/reload`                   | reload the zone from `DNSM_ZONE_FILE` (full replace)         |
| GET/POST  | `/admin/import?source_url=<url>`  | fetch a zone from a URL and merge it in                       |
| GET/POST  | `/admin/import?path=<name>`       | read a zone from `<DNSM_ZONE_DIR>/<name>` and merge it in     |
| POST      | `/admin/import` (body)            | merge the zone text in the request body                       |

Admin responses are `text/plain` and report how many records the zone holds
after the operation.

| Status                     | When                                             |
|----------------------------|--------------------------------------------------|
| `200 OK`                   | operation succeeded                              |
| `400 Bad Request`          | `/admin/import` with no url, path, or body       |
| `404 Not Found`            | unknown endpoint, or import path file not found  |
| `405 Method Not Allowed`   | wrong verb for the route (see the table above)   |
| `502 Bad Gateway`          | `/admin/import?source_url=` fetch failed         |

## Minimal client session

Using `dig` against a locally-run server (`./dnsm`, then from another shell):

```
$ dig @127.0.0.1 -p 8053 www.example.com A +short
192.0.2.10

$ dig @127.0.0.1 -p 8053 example.com MX +short
10 mail.example.com.

$ dig @127.0.0.1 -p 8053 +tcp example.com AXFR        # full zone transfer
...all records...

$ curl -s http://127.0.0.1:8080/health
ok
$ curl -s -X POST http://127.0.0.1:8080/admin/reload
reloaded 23 records from ./zones/example.zone
```

Or purely with Python stdlib (no `dig` needed) — see
[`unit_tests/test_dnsm.py`](unit_tests/test_dnsm.py) for a complete
UDP/TCP/HTTP client the tests drive it with.

## Build & run

```
make                       # builds ./dnsm (mitigations deliberately disabled)
./dnsm                     # UDP+TCP :8053, admin :8080

# or in Docker, off the host:
./unit_tests/run-in-docker.sh
```
