#!/usr/bin/env python3
"""Cockpit origin: allowlisted static tree + reverse-proxy of /api/* to bridge.

Binds 127.0.0.1:${PORT:-8777}. Only allowlisted UI asset prefixes are served.
Private challenge sources, secrets, dotfiles, and symlink escapes are forbidden.
"""
from __future__ import annotations

import http.client
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BRIDGE_URL = (
    os.environ.get("BRIDGE_URL")
    or os.environ.get("BRIDGE_ORIGIN")
    or "http://127.0.0.1:8787"
).rstrip("/")
UNREACHABLE = json.dumps({"ok": False, "error": "coordinator unreachable"}).encode("utf-8")

_ALLOWED_PREFIXES = (
    "/live3d",
    "/cockpit",
    "/fonts",
    "/three-exploration",
    "/style",
    "/plans",
)

_DENIED_PREFIXES = (
    "/saintcon-appsec-challenge-2026-private",
    "/.git",
    "/secrets",
    "/.env",
    "/dist",
)


def _normalize_url_path(url_path: str) -> str:
    path = unquote((url_path or "/").split("?", 1)[0])
    parts = []
    for p in path.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if parts:
                parts.pop()
            continue
        parts.append(p)
    return "/" + "/".join(parts)


def _denied_static(url_path: str) -> bool:
    norm = _normalize_url_path(url_path)
    lower = norm.lower()
    for prefix in _DENIED_PREFIXES:
        if lower == prefix.lower() or lower.startswith(prefix.lower() + "/"):
            return True
    parts = [p for p in norm.split("/") if p]
    for p in parts:
        if p.startswith(".") and p != ".well-known":
            return True
    return False


def _allowed_static(url_path: str) -> bool:
    if _denied_static(url_path):
        return False
    norm = _normalize_url_path(url_path)
    if norm in ("/", ""):
        return True
    for prefix in _ALLOWED_PREFIXES:
        if norm == prefix or norm.startswith(prefix + "/"):
            return True
    # Common root demo HTML (optional)
    if norm.endswith(".html") and norm.count("/") == 1:
        return True
    return False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("[cockpit] %s - %s\n" % (self.address_string(), fmt % args))

    def _is_api(self):
        path = self.path.split("?", 1)[0]
        return path == "/api" or path.startswith("/api/")

    def _forbid(self):
        body = b'{"ok":false,"error":"forbidden"}'
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def translate_path(self, path):
        full = super().translate_path(path)
        try:
            real = os.path.realpath(full)
            root = os.path.realpath(ROOT)
        except OSError:
            return os.path.join(os.path.realpath(ROOT), ".cockpit-forbidden")
        if real != root and not real.startswith(root + os.sep):
            return os.path.join(root, ".cockpit-forbidden")
        # Block escape into denied trees even via symlink under an allowed prefix.
        rel = os.path.relpath(real, root)
        if rel.startswith(".."):
            return os.path.join(root, ".cockpit-forbidden")
        probe = "/" + rel.replace(os.sep, "/")
        # Realpath target wins: deny private/dot trees even if the URL is under
        # an allowlisted prefix (symlink escape).
        if _denied_static(probe):
            return os.path.join(root, ".cockpit-forbidden")
        url_norm = _normalize_url_path(self.path)
        if not _allowed_static(url_norm):
            return os.path.join(root, ".cockpit-forbidden")
        if (
            not _allowed_static(probe)
            and probe not in ("/", "/.")
            and not os.path.isdir(real)
        ):
            return os.path.join(root, ".cockpit-forbidden")
        return full

    def end_headers(self):
        # Static files revalidate on every load (a 304 when unchanged), so an
        # edited module page or its ES module imports inside the cockpit's
        # iframe are never served stale from the browser's heuristic cache.
        if getattr(self, "_static", False):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _static_or_forbid(self, method):
        if not _allowed_static(self.path):
            self._forbid()
            return
        # translate_path may rewrite escapes to a sentinel under ROOT.
        translated = self.translate_path(self.path)
        if translated.endswith(os.sep + ".cockpit-forbidden") or translated.endswith(
            "/.cockpit-forbidden"
        ):
            self._forbid()
            return
        self._static = True
        if method == "HEAD":
            super().do_HEAD()
        else:
            super().do_GET()

    def do_GET(self):
        if self._is_api():
            self._proxy()
        else:
            self._static_or_forbid("GET")

    def do_HEAD(self):
        if self._is_api():
            self._proxy()
        else:
            self._static_or_forbid("HEAD")

    def do_POST(self):
        self._api_or_405()

    def do_PUT(self):
        self._api_or_405()

    def do_DELETE(self):
        self._api_or_405()

    def do_PATCH(self):
        self._api_or_405()

    def _api_or_405(self):
        if self._is_api():
            self._proxy()
        else:
            self.send_error(405, "Method Not Allowed")

    def _proxy(self):
        origin = urlsplit(BRIDGE_URL)
        host = origin.hostname or "127.0.0.1"
        scheme = origin.scheme or "http"
        if origin.port:
            port = origin.port
        else:
            port = 443 if scheme == "https" else 80

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {}
        ctype = self.headers.get("Content-Type")
        if ctype:
            headers["Content-Type"] = ctype
        confirm = self.headers.get("X-Bridge-Update-Apply")
        if confirm:
            headers["X-Bridge-Update-Apply"] = confirm
        for name in ("Origin", "Sec-Fetch-Site"):
            value = self.headers.get(name)
            if value:
                headers[name] = value
        if body is not None:
            headers["Content-Length"] = str(len(body))

        try:
            if scheme == "https":
                conn = http.client.HTTPSConnection(host, port, timeout=60)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=60)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
            finally:
                conn.close()
        except (OSError, http.client.HTTPException):
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(UNREACHABLE)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(UNREACHABLE)
            return

        self.send_response(resp.status)
        rctype = resp.getheader("Content-Type")
        if rctype:
            self.send_header("Content-Type", rctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    port = int(os.environ.get("PORT", "8777"))
    httpd = Server(("127.0.0.1", port), Handler)
    sys.stderr.write("serving %s on http://127.0.0.1:%s/\n" % (ROOT, port))
    sys.stderr.write("proxy /api/* -> %s\n" % BRIDGE_URL)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nstopped\n")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
