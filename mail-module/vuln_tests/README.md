# MTA - complete vulnerability list & PoCs

All seven PoCs below were run against the current `src/` and confirmed
working, including through the Docker compose network split (PoCs #2, #4 and
#8 all point MTA's webhook callback at the shared metadata service on a
`backend` network the PoC container cannot otherwise reach, and read the
disclosed `MTA_FLAG` back through the admin API - #2 via a hidden CRLF-injected
header, #4 via an ordinary visible one smuggled entirely pre-TLS, #8 via an
ordinary visible one over a normal session). Each script
takes `host`/`port` (and, where relevant, `admin_port`) from `argv` with
sane localhost defaults, drives the bug purely over the network, and prints
`[+]` on confirmed success or `[-]` on failure.

## Run it all in Docker

The compose file brings up `mta` (with a small, fixed-size tmpfs queue disk
so PoC #1 has a real quota to exhaust), the shared
`metadata` service (the SSRF target, on a `backend` network the attacker
can't reach - see ../../metadata-service), and a `poc` runner. The default
`poc` command runs PoC #1 (the relay disk-exhaustion DoS):

```
docker compose -f vuln_tests/docker-compose.yml run --build --rm poc
```

Run any other PoC by overriding the command (service name `mta`, SMTP port
`2525`, admin port `8081`):

```
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 02_header_injection_webhook_redirect.py mta 2525 8081
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 03_bounce_command_injection.py             mta 2525 8081 mta.local /home/ctf/mta/queue
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 04_starttls_smuggling.py                   mta 2525 8081
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 05_unbounded_data_dos.py                   mta 2525 8081
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 07_queue_path_traversal.py                 mta 2525 8081
docker compose -f vuln_tests/docker-compose.yml run --rm poc python3 08_webhook_ssrf.py                         mta 2525 8081 http://metadata:9000/secret/mta
```

When you're done: `docker compose -f vuln_tests/docker-compose.yml down`.

Or point a script at an already-running MTA directly:

```
python3 vuln_tests/01_relay_disk_exhaustion.py [host] [port] [admin_port]   # defaults 127.0.0.1 2525 8081
```

PoCs #2, #4, and #8 authenticate with `MTA_TEST_AUTH_USER`/`MTA_TEST_AUTH_PASS`
(env, falling back to the zero-setup local-dev default `relay`/`relay123` if
unset) - a session that already has valid credentials, "credentialed the
normal way".

## The list

| # | Vulnerability | Location | PoC |
|---|---|---|---|
| 1 | Open relay, no per-sender/global volume cap → exhausts the shared queue disk, crashing the process for everyone | `SmtpSession.onRcptTo()` + `queue.writeMessage()` in `src/smtp.js`/`src/queue.js` | `01_relay_disk_exhaustion.py` |
| 2 | CRLF header injection via the ESMTP `AUTH=` xtext parameter, forging a hidden `X-Notify-Webhook:` header that redirects the real delivery-status callback at the internal metadata service → discloses `MTA_FLAG` | `decodeXtext()` in `src/xtext.js`, sunk in `finishData()` in `src/smtp.js` | `02_header_injection_webhook_redirect.py` |
| 3 | Command injection in the bounce-notify hook via the raw envelope sender → RCE `cat`s the runtime flag file, disclosing `MTA_FLAG` | `sendBounceNotification()` in `src/bounce.js`, invoked from `finishData()` | `03_bounce_command_injection.py` |
| 4 | STARTTLS buffering bug - pre-handshake plaintext bytes bypass a real TLS-only trust check on the `AUTH=` claim, smuggling #2's webhook forgery → discloses `MTA_FLAG` | `drain()` + `onStartTls()` + `finishData()` in `src/smtp.js` | `04_starttls_smuggling.py` |
| 5 | Unbounded DATA size / no per-line length cap → memory-exhaustion DoS | `onDataLine()` in `src/smtp.js` | `05_unbounded_data_dos.py` |
| 7 | Path traversal in the queue filename, derived from the client-supplied `Message-ID` header, escaping `MTA_QUEUE_DIR` both ways → runtime flag disclosure | `deriveFilename()` + `queueFilePath()` in `src/queue.js` (shared by the admin read-back endpoint in `src/admin.js`) | `07_queue_path_traversal.py` |
| 8 | SSRF via the `X-Notify-Webhook` delivery-status callback, no scheme/host allow-list | `fireWebhook()` in `src/webhook.js`, invoked from `finishData()` | `08_webhook_ssrf.py` |

## How the two DoS PoCs (#1, #5) confirm - by bystander liveness

Both DoS PoCs prove denial of service the same way, and deliberately do NOT
infer success from the attack session's own fate (a slow, dropped, or errored
attack request only proves that one request suffered - not that the service
was denied to anyone else). Each one instead: (0) baselines a SEPARATE
ordinary client - a full normal SMTP transaction plus the admin `/health`
endpoint - and refuses to proceed unless that bystander is served; (1) runs
the attack; (2) re-probes the same separate bystander, and reports success
ONLY if it is now denied (SMTP + `/health` both stop answering), else prints
`[-] not a full DoS` and exits non-zero. Because MTA has no restart supervisor
(`entrypoint.sh` just `exec`s node, and the compose file sets no `restart:`
policy), the crash is a *permanent* outage - the re-probe sees connection
refused, not a transient blip. This mirrors IPM's
`07_billion_laughs.py` liveness template.

**PoC #1** uses a small, fixed-size tmpfs (`vuln_tests/docker-compose.yml`)
as `MTA_QUEUE_DIR` so the "shared disk" it exhausts is a few megabytes
instead of a real production volume - the bug (no cap anywhere in the
relay/queue path) and its consequence (an uncaught `ENOSPC` from
`fs.writeFileSync()` crashing the whole Node process, taking every
in-flight connection down with it - see the PoC's own docstring) are both
100% real; only the quota size is scaled down for a fast, CI-friendly
demonstration. The flood fills the ~24m tmpfs after a handful of oversized
messages, the uncaught `ENOSPC` crashes node, and the re-probe confirms the
separate bystander is refused.

**PoC #5** streams a few hundred MB of DATA-phase body with no terminating
`.`, so it is never written to disk - it just accumulates in
`this.dataLines`/`this.buffer` in memory (VULN #5: no total-size or per-line
cap). Node auto-sizes V8's old-space heap to the container's `mem_limit`
(512m in the compose file), so the uncapped buffer crosses that ceiling and
node aborts with a fatal "JavaScript heap out of memory" reproducibly at
~240MB of buffered DATA. The `mem_limit` is the load-bearing knob that turns
the unbounded buffering into an *observable* outage (an unconstrained host has
effectively infinite headroom); no swap tuning is needed, because node's heap
ceiling tracks the memory limit rather than host swap, so the abort fires the
same with or without host swap. As with #1, the re-probe confirms a separate
bystander is refused after the abort - and with no restart, it stays refused.

## A note on PoC #4's simplification

**PoC #4**: a complete demonstration of the STARTTLS buffering bug needs a
genuine man-in-the-middle splicing bytes into someone else's plaintext
connection at exactly the STARTTLS boundary - a legitimate client would
never pipeline commands ahead of its own STARTTLS. `04_starttls_smuggling.py`
instead plays both roles in one connection: it authenticates for real, then
pipelines a complete malicious transaction immediately after `STARTTLS`, all
in the SAME write, before performing its own TLS handshake, then sends a
second, entirely separate transaction over the genuinely-encrypted channel
afterward. The bug itself - `drain()` never stopping or clearing
`this.buffer` when it processes a `STARTTLS` line, so pre-handshake commands
are consumed and acted on as if they arrived after the socket became
"encrypted" - is 100% real code, exercised over a real TLS handshake on the
real network stack; only the "attacker relays into a victim's session" framing
is simplified down to "attacker supplies both halves of one connection" so the
PoC is self-contained. The malicious transaction carries an ordinary visible
`X-Notify-Webhook` header (NOT a CRLF-injected one - that is VULN #2's
construction, kept separate so a #2 fix can't flip #4), so the scored
disclosure turns on the buffering bug alone.

## Notes on how these interact

- **#1 is why almost nothing else here needs privilege to reach.** Every
  other PoC (except #4, which is about the TLS mechanism itself) starts from an ordinary, unauthenticated `MAIL FROM`/`RCPT TO`
  that #1's missing checks let through unconditionally - and #1 itself
  turns that same missing check into a DoS: nothing stops an anonymous
  client from pushing enough accepted mail to fill the shared queue disk,
  and the server has no graceful handling for the write failure that
  follows. Fixing #1's relay-acceptance half alone (requiring AUTH before
  relaying, and only to allow-listed domains) would not fix #2, #3, #5, or
  #7 - it would just mean an attacker needs valid credentials first.

- **#2 and #4 are deliberately kept on DIFFERENT sinks so neither fix flips
  the other.** Both are about honoring an `X-Notify-Webhook` callback, but they
  reach it two different ways: #2 forges a HIDDEN one by CRLF-injecting through
  the `AUTH=` xtext (recorded as `X-Original-Auth` when `this.tlsActive`); #4
  carries an ORDINARY, visible `X-Notify-Webhook` header in a transaction
  smuggled entirely before the TLS handshake (honored because the session
  authenticated, VULN #8's sink). An earlier #4 PoC reused #2's exact CRLF
  construction, so fixing #2 (rejecting decoded CR/LF/NUL in `AUTH=`) silently
  made #4 report "fixed" while the STARTTLS buffering bug was untouched - a
  genuine incomplete-fix trap. #4 now uses no CRLF trick at all, so its pass/
  fail turns on the buffering bug alone: fixing #2 does not affect it, and
  fixing #4 (discarding `this.buffer` at STARTTLS) correctly flips it because
  the whole pre-handshake transaction - visible webhook and all - is discarded.
  (#4's disclosure now rides #8's webhook-SSRF channel, so an #8 fix that
  allow-lists the callback host would also close #4's exfil - a defensible,
  real disclosure-channel fix, unlike the old silent #2 coupling.)

- **#2 and #3 are two independent injection sinks with the same root
  cause: an envelope field that was never re-validated after being
  transformed.** #2's `authParam` is the result of *decoding* (xtext →
  raw bytes, and the decode step is exactly what RFC 3461 says must be
  followed by a CR/LF/NUL rejection - skipped here). #3's `envelopeFrom` is
  used completely raw, with no transformation at all, straight into a shell
  string. They don't share a sink (one writes into a header a downstream
  worker re-reads, the other execs a shell) and fixing one does nothing for
  the other, but both are instances of "we validated the common/expected
  path (plain `sanitizeAddr()` on ordinary addresses) and missed an
  adjacent one."

- **#3 and #7 both reach the runtime flag, but by entirely different
  routes - one is the point.** #3's injected command (`cp <flag-file>
  .../new/<file>`) and #7's traversal-derived filename both end up creating
  files under/near `MTA_QUEUE_DIR`, but #3 gets there via arbitrary shell
  execution (it runs as the `ctf` user that owns the flag file, so it simply
  `cat`/`cp`s `MTA_SECRET` into a served queue file) while #7 gets there via a
  single, narrow, unsanitized `path.join()` that reaches *outside*
  `MTA_QUEUE_DIR` in both directions (write AND read). Both disclose the same
  minted `MTA_FLAG`; a fix for #7 (containment-check the queue path) does
  nothing about #3's much broader RCE capability, and vice versa.

- **#5 is the only bug here that's purely about scale, not trust - #1 is a
  second, sharper flavor of the same class.** #5 needs no envelope tricks,
  no auth bypass, nothing malformed - just a client willing to send more
  bytes than a well-behaved one would, exhausting per-connection memory.
  #1 is the same absence-of-a-cap idea applied to the shared queue *disk*
  instead of one connection's memory, which is why it's the one that
  actually takes the whole process down rather than just one session.

## Fix directions (brief - save the detail for when they ask)

1. **Relay disk-exhaustion DoS:** require successful `AUTH` before accepting
   `RCPT TO` for any domain other than `MTA_DOMAIN`, and/or maintain an
   explicit relay-domain allow-list; separately (and regardless of auth),
   enforce a per-sender and global cap on queued volume/message count, and
   handle a full-disk write failure gracefully (reject with `452`/`552`)
   instead of letting it propagate as an uncaught exception.
2. **CRLF header injection / webhook redirect:** after `decodeXtext()`,
   reject (don't just ignore) any decoded value containing CR, LF, or NUL
   before it is used anywhere - exactly what RFC 3461 §4 requires and what
   `sanitizeAddr()` already does for the plain envelope addresses.
3. **Bounce command injection:** never build a shell command string from
   attacker-controlled data; use `execFile()`/`spawn()` with an argument
   array (no shell interpolation at all) instead of `exec()`.
4. **STARTTLS buffering / trust-check bypass:** clear `this.buffer` (and
   stop the current `drain()` pass) the instant `STARTTLS` is handled, and
   discard - never process - anything that arrived before the TLS handshake
   completes; that alone also closes the `this.tlsActive` bypass, since the
   flag and genuine encryption provenance can no longer diverge.
5. **Unbounded DATA:** enforce a maximum line length (RFC 5321 §4.5.3.1.6,
   1000 octets) and a maximum total message size (advertise and enforce the
   `SIZE` extension, RFC 1870), rejecting with `500`/`552` before buffering
   further, not after.
7. **Queue path traversal:** derive the queue filename from a server-
   generated identifier only (never trust `Message-ID` for a filesystem
   path), or at minimum canonicalize and prefix-check the resolved path
   against `MTA_QUEUE_DIR/new` before every read and write.
8. **Webhook SSRF:** allow-list schemes (`https:` only) and hosts/IP ranges
   (block loopback, link-local, and RFC 1918 ranges) before `fireWebhook()`
   issues any request; better still, require the callback host to be
   pre-registered by an operator rather than supplied per-message.
