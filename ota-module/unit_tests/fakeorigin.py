#!/usr/bin/env python3
"""
Test fixture (NOT part of the product): a stand-in "package origin" that the
source_url resolver tests point OTA_RESOLVER at. One container runs two servers:

  * a UDP DNS server on :53 that answers A for `origin.test` with this
    container's OWN IP (nothing else resolves it - that's the point);
  * an HTTP server on :80 that serves a fixed package blob at any path.

Because only this fake DNS knows `origin.test`, a successful fetch of
http://origin.test/... by the OTA server proves the server resolved the host
through the configured resolver rather than the default one. The same container
is reachable by its compose service name (`fakeorigin`) for the control case
that exercises the default resolver. Deliberately dumb: no auth, no validation.
"""
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Fixed package bytes; the test hardcodes the same constant so it can put the
# matching sha256 in the manifest.
PKG = b"OTA-FAKE-ORIGIN-PACKAGE-v1\n"

# Host name only this fake resolves, and the IP it answers with (our own).
FAKE_HOST = "origin.test"
OWN_IP = socket.gethostbyname(socket.gethostname())


# --- DNS (A records only) ---------------------------------------------------
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
    idx += 4
    return qname, qtype, data[12:idx]


def build_response(data, qsection, answers):
    header = struct.pack(">HHHHHH",
                         struct.unpack(">H", data[:2])[0],
                         0x8180, 1, len(answers), 0, 0)
    body = header + qsection
    for rdata in answers:
        body += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, len(rdata)) + rdata
    return body


def dns_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 53))
    while True:
        try:
            data, addr = s.recvfrom(2048)
            qname, qtype, qsection = parse_question(data)
            answers = []
            if qtype == 1 and qname == FAKE_HOST:
                answers = [socket.inet_aton(OWN_IP)]
            s.sendto(build_response(data, qsection, answers), addr)
        except Exception:
            continue


# --- HTTP (serve the package blob) ------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/gzip")
        self.send_header("Content-Length", str(len(PKG)))
        self.end_headers()
        self.wfile.write(PKG)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print(f"[fakeorigin] own IP {OWN_IP}; DNS :53/udp for {FAKE_HOST}, HTTP :80", flush=True)
    threading.Thread(target=dns_server, daemon=True).start()
    HTTPServer(("0.0.0.0", 80), Handler).serve_forever()
