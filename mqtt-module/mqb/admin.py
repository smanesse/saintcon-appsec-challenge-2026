from __future__ import annotations

import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .broker import Broker, retained_path
from .config import Config


class _Handler(BaseHTTPRequestHandler):
    broker: Broker = None
    cfg: Config = None

    def log_message(self, fmt, *args):
        pass

    def _send(self, status: int, body: bytes, content_type: str = "text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send(200, b"ok\n")
            return

        if parsed.path == "/admin/stats":
            self._send(200, json.dumps(self.broker.stats()).encode() + b"\n", "application/json")
            return

        if parsed.path == "/admin/retained":
            self._send(200, json.dumps(self.broker.retained_list()).encode() + b"\n", "application/json")
            return

        if parsed.path == "/admin/retained/export":
            topics = qs.get("topic")
            if not topics:
                self._send(400, b"missing ?topic=\n")
                return
            topic = topics[0]
            if self.broker.is_reserved(topic):
                # The broker-owned control namespace is never exported, just
                # as it is never delivered over MQTT (see Broker.is_reserved).
                self._send(404, b"no persisted retained message for that topic\n")
                return
            # retained_path() is the same helper the broker writes with, and
            # it maps every topic to a hashed filename inside MQB_RETAIN_DIR,
            # so no topic can reach a file outside it.
            path = retained_path(self.cfg.retain_dir, topic)
            if not os.path.isfile(path):
                self._send(404, b"no persisted retained message for that topic\n")
                return
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError as e:
                self._send(500, f"read error: {e}\n".encode())
                return
            self._send(200, data, "application/octet-stream")
            return

        self._send(404, b"not found\n")

    def do_POST(self):
        self.do_GET() if self.path == "/health" else self._send(404, b"not found\n")


def start_admin_server(broker: Broker, cfg: Config) -> ThreadingHTTPServer:
    handler_cls = type("BoundHandler", (_Handler,), {"broker": broker, "cfg": cfg})
    httpd = ThreadingHTTPServer((cfg.admin_host, cfg.admin_port), handler_cls)
    thread = threading.Thread(target=httpd.serve_forever, name="mqb-admin", daemon=True)
    thread.start()
    return httpd
