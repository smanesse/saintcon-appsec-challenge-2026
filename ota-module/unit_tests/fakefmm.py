#!/usr/bin/env python3
"""
Test fixture (NOT part of the product): a stand-in "fleet file server" that the
OTA->FMM source_url tests point OTA_FMM at. It speaks just enough of FMM's
FTP subset (see file-management-module/README.md) to hand OTA a package over a
passive data connection:

    220 banner -> USER/PASS (any creds accepted) -> TYPE I -> PASV -> RETR

For any RETR path it serves a fixed package blob, so a successful publish proves
OTA fetched via its FMM client. PASV advertises this container's OWN IP (the
address OTA reaches it at), mirroring how real FMM advertises its control
socket's address. Deliberately dumb: no real auth, no path handling, one client
at a time per thread.
"""
import socket
import threading

# Fixed package bytes; the test hardcodes the same constant so it can put the
# matching sha256 in the manifest.
PKG = b"OTA-FAKE-FMM-PACKAGE-v1\n"

OWN_IP = socket.gethostbyname(socket.gethostname())


def send(conn, line):
    conn.sendall((line + "\r\n").encode())


def open_pasv():
    """Bind a fresh data listener; return (socket, h1,h2,h3,h4,p1,p2 tuple)."""
    ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("0.0.0.0", 0))
    ls.listen(1)
    port = ls.getsockname()[1]
    octets = [int(x) for x in OWN_IP.split(".")]
    return ls, octets + [port >> 8, port & 0xFF]


def handle(conn):
    conn.settimeout(20)
    f = conn.makefile("rb")
    send(conn, "220 fakefmm ready")
    pasv_listener = None
    try:
        for raw in f:
            line = raw.decode("latin-1").rstrip("\r\n")
            if not line:
                break
            verb, _, arg = line.partition(" ")
            verb = verb.upper()
            if verb == "USER":
                send(conn, "331 Password required")
            elif verb == "PASS":
                send(conn, "230 Login successful token=00000")
            elif verb == "TYPE":
                send(conn, "200 Type set")
            elif verb == "PASV":
                pasv_listener, tup = open_pasv()
                send(conn, "227 Entering Passive Mode ({},{},{},{},{},{})".format(*tup))
            elif verb == "RETR":
                if pasv_listener is None:
                    send(conn, "425 Use PASV first")
                    continue
                send(conn, "150 Opening data connection")
                data, _ = pasv_listener.accept()
                data.sendall(PKG)
                data.close()
                pasv_listener.close()
                pasv_listener = None
                send(conn, "226 Transfer complete")
            elif verb == "QUIT":
                send(conn, "221 Goodbye")
                break
            else:
                send(conn, "502 Command not implemented")
    except OSError:
        pass
    finally:
        if pasv_listener is not None:
            pasv_listener.close()
        conn.close()


def main():
    print(f"[fakefmm] own IP {OWN_IP}; FTP control :2121, serving {len(PKG)}-byte package", flush=True)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 2121))
    s.listen(8)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
