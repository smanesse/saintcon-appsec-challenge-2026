#!/usr/bin/env python3
"""
Test upstream resolver for DNSM's recursive-forwarding path.

This is NOT part of the vulnerable service - it is throwaway test
infrastructure. It listens on UDP (default :8053) and answers every A query
with 10.0.0.5, after a deliberate delay so that an off-path spoofer racing it
(see 06_txid_spoofing.py) reliably wins. Non-A queries get an empty NOERROR.

    python3 upstream_responder.py [port] [delay_seconds]
"""
import socket
import struct
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8053
DELAY = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
LEGIT_IP = "10.0.0.5"


def serve():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", PORT))
    print(f"[upstream] listening UDP :{PORT} delay={DELAY}s", flush=True)
    while True:
        data, addr = s.recvfrom(4096)
        threading.Thread(target=reply, args=(s, data, addr), daemon=True).start()


def reply(s, data, addr):
    if len(data) < 12:
        return
    txid = data[:2]
    # Question section starts at offset 12 and runs to end (name+qtype+qclass).
    question = data[12:]
    qtype = struct.unpack(">H", question[-4:-2])[0] if len(question) >= 4 else 1
    time.sleep(DELAY)
    if qtype == 1:  # A
        ans = (
            txid
            + struct.pack(">HHHHH", 0x8180, 1, 1, 0, 0)
            + question
            + b"\xc0\x0c"
            + struct.pack(">HHIH", 1, 1, 60, 4)
            + socket.inet_aton(LEGIT_IP)
        )
    else:
        ans = txid + struct.pack(">HHHHH", 0x8180, 1, 0, 0, 0) + question
    s.sendto(ans, addr)


if __name__ == "__main__":
    serve()
