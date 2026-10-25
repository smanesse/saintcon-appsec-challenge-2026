#!/usr/bin/env python3
"""
Test fixture (NOT part of the product): a self-contained stand-in for "the rest
of the mail world" that the relay unit tests point MTA_RESOLVER at. It runs two
tiny servers in one container so the DNS answers can name *itself* as the mail
exchanger:

  * a UDP DNS server on :53 that answers just enough for the relay path -
      sink.test      MX 10 mx.sink.test        (A of mx.sink.test -> our own IP)
      nomx.test      (no MX)                    (A of nomx.test    -> our own IP)
      *.unresolv.test / unresolv.test           (no records -> forces a deferral)
  * an SMTP sink on :25 that accepts any message and 250s it.

Because the A records resolve to this container's own address, a message the MTA
relays for sink.test / nomx.test actually lands in the sink here, so the test
can assert a real `delivered` outcome without any external network. This is a
deliberate fake with no auth and no validation - it only exists to give the
module under test something concrete and controllable to resolve and talk to.
"""
import socket
import struct
import threading

# Domains this fake is authoritative-ish for. mx.sink.test and nomx.test map to
# our own IP so the relay connects back here; unresolv.test has no A at all.
OWN_IP = socket.gethostbyname(socket.gethostname())


def enc_name(name):
    out = b""
    for part in name.split("."):
        if part:
            out += bytes([len(part)]) + part.encode()
    return out + b"\x00"


def parse_question(data):
    idx = 12
    labels = []
    while True:
        ln = data[idx]
        idx += 1
        if ln == 0:
            break
        labels.append(data[idx:idx + ln].decode("ascii", "replace"))
        idx += ln
    qname = ".".join(labels).lower()
    qtype = struct.unpack(">H", data[idx:idx + 2])[0]
    idx += 4  # skip qtype + qclass
    return qname, qtype, data[12:idx]  # raw question bytes, echoed back verbatim


def answers_for(qname, qtype):
    """Return a list of (rrtype, rdata) for the query, or [] for NODATA."""
    if qtype == 15:  # MX
        if qname == "sink.test":
            return [(15, struct.pack(">H", 10) + enc_name("mx.sink.test"))]
        return []     # nomx.test / unresolv.test -> no MX (fallback / defer)
    if qtype == 1:    # A
        if qname in ("mx.sink.test", "nomx.test"):
            return [(1, socket.inet_aton(OWN_IP))]
        return []     # mx.unresolv.test / unresolv.test -> no A -> deferral
    return []


def build_response(data, qsection, answers):
    header = struct.pack(">HHHHHH",
                         struct.unpack(">H", data[:2])[0],  # copy the query id
                         0x8180,                            # QR=1 RD=1 RA=1 NOERROR
                         1, len(answers), 0, 0)
    body = header + qsection
    for rrtype, rdata in answers:
        body += b"\xc0\x0c"                       # owner name -> pointer to the question
        body += struct.pack(">HHIH", rrtype, 1, 60, len(rdata))
        body += rdata
    return body


def dns_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 53))
    while True:
        try:
            data, addr = s.recvfrom(2048)
            qname, qtype, qsection = parse_question(data)
            s.sendto(build_response(data, qsection, answers_for(qname, qtype)), addr)
        except Exception:
            continue  # a fake: never die on a malformed packet


def smtp_sink():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 25))
    s.listen(16)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=_smtp_session, args=(conn,), daemon=True).start()


def _smtp_session(conn):
    conn.settimeout(10)
    try:
        conn.sendall(b"220 fakemx sink ready\r\n")
        in_data = False
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\r\n" in buf:
                line, buf = buf.split(b"\r\n", 1)
                if in_data:
                    if line == b".":
                        in_data = False
                        conn.sendall(b"250 2.0.0 Ok: sunk\r\n")
                    continue
                up = line.upper()
                if up.startswith((b"EHLO", b"HELO")):
                    conn.sendall(b"250 fakemx\r\n")
                elif up.startswith(b"DATA"):
                    conn.sendall(b"354 go\r\n")
                    in_data = True
                elif up.startswith(b"QUIT"):
                    conn.sendall(b"221 bye\r\n")
                    return
                else:  # MAIL/RCPT/RSET/NOOP/anything -> just accept
                    conn.sendall(b"250 ok\r\n")
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


if __name__ == "__main__":
    print(f"[fakemx] own IP {OWN_IP}; DNS :53/udp, SMTP :25", flush=True)
    threading.Thread(target=dns_server, daemon=True).start()
    smtp_sink()
