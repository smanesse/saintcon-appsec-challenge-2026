#!/usr/bin/env python3
import http.server
import os
import re
import socketserver
import sys


def load_secrets():
    secrets = {}
    for key, val in os.environ.items():
        if key == "META_SECRET":
            secrets[""] = val
        elif key.startswith("META_SECRET_"):
            name = key[len("META_SECRET_"):].lower()
            if name:
                secrets[name] = val
    if not secrets:
        flag = next((v for k, v in os.environ.items() if k.endswith("_FLAG")), None)
        secrets[""] = flag or "FLAG{local-dev-default}"
    return secrets


SECRETS = load_secrets()
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("META_PORT", "9000"))


def render(name, value):
    label = name or "default"
    return (
        "# fleet-metadata-service :: internal-only, do not expose\n"
        f"service={label}\n"
        f"internal-secret={value}\n"
    ).encode()


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/health":
            return self._send(200, b"ok\n")
        if path == "/":
            names = ["/secret" + (("/" + n) if n else "") for n in sorted(SECRETS)]
            body = ("# fleet-metadata-service\n# available:\n"
                    + "".join(p + "\n" for p in names)).encode()
            return self._send(200, body)
        if path == "/secret":
            if "" in SECRETS:
                return self._send(200, render("", SECRETS[""]))
            return self._send(404, b"no default secret configured\n")
        m = re.fullmatch(r"/secret/([A-Za-z0-9_-]+)", path)
        if m and m.group(1).lower() in SECRETS:
            name = m.group(1).lower()
            return self._send(200, render(name, SECRETS[name]))
        return self._send(404, b"not found\n")

    def do_GET(self):
        self._route()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            self.rfile.read(length)
        self._route()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[metadata] serving {sorted(k or '(default)' for k in SECRETS)} on :{PORT}",
              flush=True)
        httpd.serve_forever()
