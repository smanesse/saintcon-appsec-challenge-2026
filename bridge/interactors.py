#!/usr/bin/env python3
"""
Real, over-the-wire interactions with the 8 challenge modules.

Every function here speaks the module's ACTUAL protocol using only the Python
standard library, modelled directly on each module's `unit_tests/test_*.py`
reference client and its README "minimal client session". Nothing here is
simulated: if a call succeeds, it is because a real service answered on the
wire. If a service isn't reachable, the call returns {"ok": False, ...} and the
console shows it as offline.

Connection details default to the host-published ports from the fleet compose
(bridge/fleet-compose.yml); a caller passes host/port/admin_port explicitly.
"""
import base64
import binascii
import hashlib
import html
import io
import json
import os
import re
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

TIMEOUT = 6.0

# Credentials/keys that ship with the exercises (see each module's test file).
FMM_USER, FMM_PASS = "alice", "password123"

# A minimal but valid 1x1 PNG (same payload the IPM tests use).
ONE_PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ"
    "/pLvAAAAAElFTkSuQmCC"
)
# SVG is the metadata-path probe from image-processing-module/unit_tests.
CANNED_SVG = (
    b'<?xml version="1.0"?>\n'
    b'<svg xmlns="http://www.w3.org/2000/svg" width="123" height="45">'
    b'<rect width="123" height="45" fill="blue"/></svg>'
)
IPM_DECK = ("NGC7293.PNG", "HELIX-02.PNG", "M87-CORE.PNG", "CRAB-N1.PNG")
_IPM_PLATES = {
    "probe": ("probe.png", ONE_PX_PNG, "image/png"),
    "svg": ("drawing.svg", CANNED_SVG, "image/svg+xml"),
    "drawing.svg": ("drawing.svg", CANNED_SVG, "image/svg+xml"),
    "ngc7293": ("NGC7293.PNG", ONE_PX_PNG, "image/png"),
    "ngc7293.png": ("NGC7293.PNG", ONE_PX_PNG, "image/png"),
    "helix-02": ("HELIX-02.PNG", ONE_PX_PNG, "image/png"),
    "helix-02.png": ("HELIX-02.PNG", ONE_PX_PNG, "image/png"),
    "m87-core": ("M87-CORE.PNG", ONE_PX_PNG, "image/png"),
    "m87-core.png": ("M87-CORE.PNG", ONE_PX_PNG, "image/png"),
    "crab-n1": ("CRAB-N1.PNG", ONE_PX_PNG, "image/png"),
    "crab-n1.png": ("CRAB-N1.PNG", ONE_PX_PNG, "image/png"),
}

_DNS_TYPES = {
    "A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "PTR": 12,
    "MX": 15, "TXT": 16, "AAAA": 28, "AXFR": 252,
}
_DNS_TYPE_NAMES = {v: k for k, v in _DNS_TYPES.items()}
_DNS_RCODES = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 5: "REFUSED"}

# Dashboard HTML is untrusted. Extract the
# inner text of each `.line` div as a string; never forward the markup.
_LINE_DIV = re.compile(r'<div\s+class=["\']line["\']>(.*?)</div>', re.I | re.S)
_DASHBOARD_CAP = 17  # tape (10) + tail (7)

# Happy-path bytes when the publisher omits source_url (unit-test style).
OTA_HAPPY_PKG = b"a perfectly ordinary update package\n"
OTA_MODULES = ("fmm", "ipm", "log")

STOR_PROBE = "cargo from auditor-7\n"
FMM_FULL_CAP = 4 * 1024 * 1024   # RETR full=1 returns at most this many bytes
_MQB_SESSIONS = {}
_MQB_SESS_LOCK = threading.Lock()
MQB_INBOX_CAP = 200

# The fleet's per-deployment secrets (generate-secrets.sh), which fleet-up.sh
# mints into secrets/fleet.env before bringing the fleet up. A caller that
# already has a var exported (e.g. the harness env) wins; otherwise we read the
# generated file. The console container mounts the repo at /repo with cwd
# /repo/bridge, and a host run of server.py runs from bridge/, so the same
# relative paths reach repo-root secrets/ in both cases. Cached once loaded;
# retried each call until the file appears, so starting the console before
# fleet-up still resolves the value without a restart.
_FLEET_SECRETS = None

def _fleet_secret(name):
    v = os.environ.get(name)
    if v:
        return v
    global _FLEET_SECRETS
    if not _FLEET_SECRETS:
        _FLEET_SECRETS = {}
        for path in ("secrets/fleet.env", "../secrets/fleet.env"):
            try:
                with open(path) as fh:
                    for raw in fh:
                        line = raw.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, _, val = line.partition("=")
                        _FLEET_SECRETS[k.strip()] = val.strip()
                break
            except OSError:
                continue
    return _FLEET_SECRETS.get(name, "")


def _http(method, url, data=None, headers=None, timeout=TIMEOUT):
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _multipart(fields, file_field=None, filename=None, file_bytes=None, file_ct="application/octet-stream"):
    boundary = "----bridge" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="{name}"\r\n\r\n{value}\r\n').encode()
    if file_field is not None:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="{file_field}"; filename="{filename}"\r\n'
                 f"Content-Type: {file_ct}\r\n\r\n").encode()
        body += file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return f"multipart/form-data; boundary={boundary}", body


def _truthy(v):
    if v is True or v == 1:
        return True
    if v is False or v is None or v == 0:
        return False
    return str(v).strip().lower() not in ("", "0", "false", "no", "off")


def _fmm_parse_pasv(reply):
    a, b = reply.find("("), reply.find(")")
    if a < 0 or b <= a:
        return None
    parts = reply[a + 1:b].split(",")
    if len(parts) != 6:
        return None
    nums = [int(p.strip()) for p in parts]
    return ".".join(str(n) for n in nums[:4]), nums[4] * 256 + nums[5]


def _fmm_parse_pwd(reply):
    if '"' in reply:
        return reply.split('"', 2)[1]
    return (reply[4:] if reply[:3].isdigit() else reply).strip()


def _fmm_token(reply):
    if "token=" not in reply:
        return None
    return reply.split("token=", 1)[1].strip() or None


def _fmm_entries(body):
    if isinstance(body, (bytes, bytearray)):
        text = body.decode(errors="replace")
    else:
        text = body or ""
    return [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln != ""]


def _fmm_preview(data, n=400):
    text = (data or b"").decode("utf-8", errors="replace").replace("\x00", "\ufffd")
    return text[:n]


def _fmm_read_data(sock):
    out = b""
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            out += chunk
    except socket.timeout:
        pass
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return out


class _FmmCtl:
    """One-shot control connection. Always QUIT in close(); never held across POSTs."""

    def __init__(self, host, port):
        self.host = host
        self.lines = []
        self.s = socket.create_connection((host, port), timeout=TIMEOUT)
        self.s.settimeout(TIMEOUT)
        try:
            self.f = self.s.makefile("rb")
            self.greeting = self._read()
        except Exception:
            try:
                self.s.close()
            except OSError:
                pass
            raise

    def _read(self):
        reply = self.f.readline().decode(errors="replace").rstrip("\r\n")
        self.lines.append(reply)
        return reply

    def cmd(self, line):
        self.s.sendall((line + "\r\n").encode())
        return self._read()

    def userpass(self, params):
        user = params.get("user") or FMM_USER
        password = params.get("pass") or FMM_PASS
        self.cmd(f"USER {user}")
        return self.cmd(f"PASS {password}")

    def sess(self, token):
        return self.cmd(f"SESS {token}")

    def resume(self, params):
        """SESS if a token is present; otherwise leave the session logged out."""
        token = (params.get("token") or "").strip()
        if not token:
            return None
        return self.sess(token)

    def enter(self, params):
        """SESS does not restore cwd. Optional params.cwd is a path from the
        default root so one-shot list/retr/stor can operate in a subdir."""
        rel = (params.get("cwd") or "").strip()
        if not rel:
            return None
        return self.cmd(f"CWD {rel}")

    def maybe_type(self, params):
        code = (params.get("type") or "").strip().upper()
        if not code:
            return None
        return self.cmd(f"TYPE {code}")

    def pwd(self):
        return self.cmd("PWD")

    def _pasv_connect(self, adv_host, adv_port):
        err = None
        seen = set()
        for h in (adv_host, self.host):
            if not h or h in seen:
                continue
            seen.add(h)
            try:
                ds = socket.create_connection((h, adv_port), timeout=TIMEOUT)
                ds.settimeout(TIMEOUT)
                return ds
            except OSError as e:
                err = e
        raise err or OSError("PASV connect failed")

    def pasv(self):
        reply = self.cmd("PASV")
        parsed = _fmm_parse_pasv(reply) if reply.startswith("227") else None
        if not parsed:
            return None, reply, None
        adv_host, adv_port = parsed
        ds = self._pasv_connect(adv_host, adv_port)
        endpoint = {"host": adv_host, "port": adv_port, "mode": "pasv"}
        return ds, reply, endpoint

    def port(self, params=None):
        local_ip = self.s.getsockname()[0]
        if local_ip in ("0.0.0.0", "::", "::ffff:0.0.0.0"):
            local_ip = self.host
        ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind((local_ip, 0))
        ls.listen(1)
        ls.settimeout(TIMEOUT)
        bound_ip, bound_port = ls.getsockname()[:2]
        p1, p2 = bound_port >> 8, bound_port & 0xFF
        reply = self.cmd(f"PORT {bound_ip.replace('.', ',')},{p1},{p2}")
        endpoint = {"host": bound_ip, "port": bound_port, "mode": "port"}
        if not reply.startswith("200"):
            ls.close()
            return None, reply, endpoint
        return ls, reply, endpoint

    def open_channel(self, params):
        self.maybe_type(params)
        channel = (params.get("channel") or "pasv").strip().lower()
        if channel == "port":
            sock, reply, endpoint = self.port(params)
            return "port", sock, reply, endpoint
        sock, reply, endpoint = self.pasv()
        return "pasv", sock, reply, endpoint

    def transfer_body(self, kind, sock, first, payload=None):
        """After LIST/RETR/STOR. payload bytes means STOR (write); else read."""
        if not first.startswith("150"):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
            return b"", first
        body = b""
        data = sock
        try:
            if kind == "port":
                data, _ = sock.accept()
                data.settimeout(TIMEOUT)
            if payload is not None:
                data.sendall(payload)
                try:
                    data.close()
                except OSError:
                    pass
                data = None
            else:
                body = _fmm_read_data(data)
                data = None
        finally:
            if data is not None:
                try:
                    data.close()
                except OSError:
                    pass
            if kind == "port" and sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        final = self._read()
        return body, final

    def list_path(self, params):
        kind, sock, chan_reply, endpoint = self.open_channel(params)
        if sock is None:
            return {"ok": False, "reply": chan_reply, "endpoint": endpoint,
                    "entries": [], "transcript": self.lines}
        first = self.cmd("LIST")
        body, final = self.transfer_body(kind, sock, first)
        pwd_reply = self.pwd()
        ok = final.startswith("226")
        return {
            "ok": ok,
            "reply": final if final else first,
            "entries": _fmm_entries(body) if ok else _fmm_entries(body),
            "cwd": pwd_reply,
            "endpoint": endpoint,
            "type": (params.get("type") or "").strip().upper() or None,
            "transcript": self.lines,
        }

    def close(self):
        try:
            self.cmd("QUIT")
        except Exception:
            pass
        try:
            self.s.close()
        except OSError:
            pass


def _fmm_run(host, port, work):
    ctl = None
    try:
        ctl = _FmmCtl(host, port)
        return work(ctl)
    except OSError as e:
        return {"ok": False, "error": str(e), "transcript": ctl.lines if ctl else []}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "transcript": ctl.lines if ctl else []}
    finally:
        if ctl is not None:
            ctl.close()


def fmm_login(host, port, params):
    user = params.get("user") or FMM_USER

    def work(ctl):
        greeting = ctl.greeting
        pass_reply = ctl.userpass(params)
        token = _fmm_token(pass_reply)
        pwd_reply = ctl.pwd()
        ok = pass_reply.startswith("230")
        return {
            "ok": ok,
            "greeting": greeting,
            "authenticated": ok,
            "session_token": token,
            "cwd": pwd_reply,
            "reply": pass_reply,
            "transcript": ctl.lines,
            "summary": (f"Authenticated as {user}; session token issued; {pwd_reply}"
                        if ok else f"Login rejected: {pass_reply}"),
        }

    return _fmm_run(host, port, work)


def fmm_sess(host, port, params):
    token = (params.get("token") or "").strip()

    def work(ctl):
        reply = ctl.sess(token) if token else ctl.cmd("SESS")
        pwd_reply = ctl.pwd()
        ok = reply.startswith("230")
        return {
            "ok": ok,
            "authenticated": ok,
            "session_token": token if ok else None,
            "cwd": pwd_reply,
            "reply": reply,
            "transcript": ctl.lines,
            "summary": (f"Session resumed; {pwd_reply}" if ok else f"SESS rejected: {reply}"),
        }

    return _fmm_run(host, port, work)


def fmm_list(host, port, params):
    def work(ctl):
        auth = ctl.resume(params)
        ctl.enter(params)
        listing = ctl.list_path(params)
        if auth and auth.startswith("530"):
            listing["ok"] = False
            listing["reply"] = auth
            listing["authenticated"] = False
        listing.setdefault("transcript", ctl.lines)
        return listing

    return _fmm_run(host, port, work)


def fmm_cwd(host, port, params):
    dirname = params.get("dir") or ""

    def work(ctl):
        auth = ctl.resume(params)
        cwd_reply = ctl.cmd(f"CWD {dirname}")
        listing = ctl.list_path(params)
        listing["ok"] = cwd_reply.startswith("250")
        listing["reply"] = cwd_reply
        if auth and auth.startswith("530"):
            listing["ok"] = False
            listing["reply"] = auth
        listing.setdefault("transcript", ctl.lines)
        return listing

    return _fmm_run(host, port, work)


def fmm_retr(host, port, params):
    filename = params.get("filename") or ""

    def work(ctl):
        auth = ctl.resume(params)
        ctl.enter(params)
        kind, sock, chan_reply, endpoint = ctl.open_channel(params)
        if sock is None:
            return {"ok": False, "reply": chan_reply or auth, "endpoint": endpoint,
                    "transcript": ctl.lines}
        first = ctl.cmd(f"RETR {filename}")
        body, final = ctl.transfer_body(kind, sock, first)
        reply = final or first
        ok = reply.startswith("226")
        return {
            "ok": ok,
            "reply": reply,
            "bytes": len(body),
            "size": len(body),
            "preview": _fmm_preview(body),
            **({"content_b64": base64.b64encode(body[:FMM_FULL_CAP]).decode(),
                "truncated": len(body) > FMM_FULL_CAP}
               if ok and _truthy(params.get("full")) else {}),
            "endpoint": endpoint,
            "type": (params.get("type") or "").strip().upper() or None,
            "filename": filename,
            "transcript": ctl.lines,
            "summary": (f"RETR {filename} {len(body)} B" if ok else f"RETR failed: {reply}"),
        }

    return _fmm_run(host, port, work)


def fmm_stor(host, port, params):
    filename = params.get("filename") or "probe.txt"
    raw = params.get("body")
    b64 = params.get("body_b64")
    if isinstance(b64, str):
        try:
            payload = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            return {"ok": False, "error": "body_b64 is not valid base64", "filename": filename}
    elif raw is None or raw == "":
        payload = STOR_PROBE.encode()
    elif isinstance(raw, (bytes, bytearray)):
        payload = bytes(raw)
    else:
        payload = str(raw).encode()

    def work(ctl):
        auth = ctl.resume(params)
        ctl.enter(params)
        kind, sock, chan_reply, endpoint = ctl.open_channel(params)
        if sock is None:
            return {"ok": False, "reply": chan_reply or auth, "endpoint": endpoint,
                    "filename": filename, "transcript": ctl.lines}
        first = ctl.cmd(f"STOR {filename}")
        _, final = ctl.transfer_body(kind, sock, first, payload=payload)
        reply = final or first
        ok = reply.startswith("226")
        return {
            "ok": ok,
            "reply": reply,
            "filename": filename,
            "bytes": len(payload),
            "size": len(payload),
            "endpoint": endpoint,
            "type": (params.get("type") or "").strip().upper() or None,
            "transcript": ctl.lines,
            "summary": (f"STOR {filename} {len(payload)} B" if ok else f"STOR failed: {reply}"),
        }

    return _fmm_run(host, port, work)


def fmm_type(host, port, params):
    code = (params.get("code") or params.get("type") or "").strip().upper()

    def work(ctl):
        auth = ctl.resume(params)
        if code:
            reply = ctl.cmd(f"TYPE {code}")
        else:
            reply = ctl.cmd("TYPE")
        if auth and auth.startswith("530") and not (reply or "").startswith("530"):
            reply = auth
        ok = reply.startswith("200")
        return {
            "ok": ok,
            "reply": reply,
            "type": code or None,
            "transcript": ctl.lines,
            "summary": reply,
        }

    return _fmm_run(host, port, work)


def _ipm_query(params, extra=None):
    q = []
    for k in ("width", "height", "format", "name", "url"):
        v = params.get(k)
        if v is None or v == "":
            continue
        q.append(f"{k}={urllib.parse.quote(str(v))}")
    if extra:
        q.extend(extra)
    return "&".join(q)


def _ipm_payload(params):
    """Canned plate / svg / probe, or cockpit-supplied image_b64."""
    raw = params.get("image_b64")
    if raw:
        data = base64.b64decode(raw)
        fname = params.get("filename") or params.get("source") or "upload.png"
        ct = "image/svg+xml" if str(fname).lower().endswith(".svg") else "image/png"
        return str(fname), data, ct
    key = str(params.get("source") or "probe").strip().lower()
    rec = _IPM_PLATES.get(key) or _IPM_PLATES.get(key.replace("_", "-"))
    if rec:
        fname, data, ct = rec
    else:
        fname, data, ct = ("probe.png", ONE_PX_PNG, "image/png")
    # Optional multipart filename override.
    override = params.get("filename")
    if override not in (None, ""):
        fname = str(override)
    return fname, data, ct


def _ipm_make_zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _ipm_retrieve(base, name):
    if not name:
        return {"retrievable": False, "retrieve_status": None}
    rstatus, rheaders, rbytes = _http(
        "GET", f"{base}/image/{urllib.parse.quote(str(name))}", timeout=30)
    retrievable = rstatus == 200
    out = {
        "retrievable": retrievable,
        "retrieve_status": rstatus,
        "content_type": rheaders.get("Content-Type") if retrievable else None,
        "byte_length": len(rbytes) if retrievable else 0,
        "magic": rbytes[:8].hex() if rbytes else None,
    }
    if retrievable:
        out["image_b64"] = base64.b64encode(rbytes).decode("ascii")
    return out


def _ipm_from_json(j, name_fallback, retrieve):
    stored_name = j.get("name", name_fallback)
    out = {
        "ok": True,
        "stored": j.get("stored"),
        "name": stored_name,
        "bytes": j.get("bytes"),
    }
    for k in ("svg", "convertError", "storeError"):
        if k in j:
            out[k] = j[k]
    out.update(retrieve)
    if retrieve.get("retrievable"):
        out["summary"] = (f"Converted -> {stored_name} ({j.get('bytes')} B), "
                          f"stored in Cargo Bay and retrieved back "
                          f"({retrieve.get('content_type')})")
    else:
        st = retrieve.get("retrieve_status")
        out["summary"] = (f"Converted -> {stored_name}, but retrieval "
                          f"returned HTTP {st}" if st is not None
                          else f"Converted -> {stored_name}")
    return out


def ipm_convert(host, port, params):
    """POST /convert. Default body is the unit-test 1x1 PNG so the mock probe
    still works. Honour name/width/height/format. Empty name is omitted so IPM
    mints img_<hex>.png. Optional canned `source` or `image_b64` from the
    cockpit. GET /image/{stored} on success."""
    base = f"http://{host}:{port}"
    fname, data, ct = _ipm_payload(params)
    q = _ipm_query(params)
    mp_ct, body = _multipart({}, "image", fname, data, ct)
    try:
        url = f"{base}/convert" + (f"?{q}" if q else "")
        status, _, resp = _http("POST", url, body, {"Content-Type": mp_ct}, timeout=30)
        if status != 200:
            return {"ok": False, "error": f"convert returned HTTP {status}",
                    "body": resp[:300].decode(errors="replace")}
        j = json.loads(resp)
        stored_name = j.get("name")
        retrieve = _ipm_retrieve(base, stored_name) if stored_name else {"retrievable": False}
        return _ipm_from_json(j, stored_name, retrieve)
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def ipm_convert_url(host, port, params):
    """POST /convert-url as form/query. `url` required. Do not scheme-check."""
    if not params.get("url"):
        return {"ok": False, "error": "url is required"}
    base = f"http://{host}:{port}"
    q = _ipm_query(params)
    try:
        status, _, resp = _http("POST", f"{base}/convert-url?{q}", b"", timeout=30)
        if status != 200:
            return {"ok": False, "error": f"convert-url returned HTTP {status}",
                    "body": resp[:300].decode(errors="replace")}
        j = json.loads(resp)
        stored_name = j.get("name")
        retrieve = _ipm_retrieve(base, stored_name) if stored_name else {"retrievable": False}
        return _ipm_from_json(j, stored_name, retrieve)
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def ipm_convert_batch(host, port, params):
    """POST /convert-batch. Catalog with no source → two 1x1 PNGs (unit-test
    shape). Cockpit `source=deck` → the four-plate zip. Optional archive_b64."""
    base = f"http://{host}:{port}"
    raw = params.get("archive_b64")
    if raw:
        archive = base64.b64decode(raw)
        zip_name = params.get("filename") or "images.zip"
    else:
        src = str(params.get("source") or "").strip().lower()
        if src in ("deck", "plates", "plates.zip"):
            archive = _ipm_make_zip({n: ONE_PX_PNG for n in IPM_DECK})
            zip_name = "plates.zip"
        else:
            archive = _ipm_make_zip({"a.png": ONE_PX_PNG, "b.png": ONE_PX_PNG})
            zip_name = "images.zip"
    mp_ct, body = _multipart({}, "archive", zip_name, archive, "application/zip")
    try:
        status, _, resp = _http(
            "POST", f"{base}/convert-batch", body, {"Content-Type": mp_ct}, timeout=30)
        if status != 200:
            return {"ok": False, "error": f"convert-batch returned HTTP {status}",
                    "body": resp[:300].decode(errors="replace")}
        j = json.loads(resp)
        results = j.get("results") or []
        first = next((x for x in results if x.get("stored") and x.get("name")), None)
        stored_n = sum(1 for x in results if x.get("stored"))
        out = {
            "ok": True,
            "count": j.get("count", len(results)),
            "results": results,
            "stored_n": stored_n,
            "name": (first or {}).get("name"),
            "bytes": (first or {}).get("bytes"),
            "stored": bool(first),
        }
        if first:
            out.update(_ipm_retrieve(base, first["name"]))
        else:
            out["retrievable"] = False
        out["summary"] = (f"Batch {out['count']} member(s), {stored_n} stored"
                          + (f"; retrieved {out['name']}" if out.get("retrievable") else ""))
        return out
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def ipm_image(host, port, params):
    """GET /image/{name}. JSON summary + image_b64 for the cockpit texture."""
    name = params.get("name")
    if not name:
        return {"ok": False, "error": "name is required"}
    base = f"http://{host}:{port}"
    try:
        retrieve = _ipm_retrieve(base, name)
        ok = bool(retrieve.get("retrievable"))
        return {
            "ok": ok,
            "name": name,
            "error": None if ok else f"image returned HTTP {retrieve.get('retrieve_status')}",
            "summary": (f"{name} {retrieve.get('byte_length')} B "
                        f"{retrieve.get('content_type')}" if ok
                        else f"{name} HTTP {retrieve.get('retrieve_status')}"),
            **retrieve,
        }
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def ipm_health(host, port, params):
    try:
        status, _, resp = _http("GET", f"http://{host}:{port}/health")
        text = resp.decode(errors="replace")
        ok = status == 200 and "ok" in text.lower()
        return {
            "ok": ok,
            "status": status,
            "body": text[:200],
            "summary": "ok" if ok else (text[:80] or f"HTTP {status}"),
        }
    except OSError as e:
        return {"ok": False, "error": str(e)}


def _dns_encode_name(n):
    return b"".join(bytes([len(l)]) + l.encode() for l in n.split(".") if l) + b"\x00"


def _dns_read_name(msg, pos):
    labels = []
    jumped = False
    start = pos
    guard = 0
    while True:
        guard += 1
        if guard > 128 or pos >= len(msg):
            break
        length = msg[pos]
        if length == 0:
            pos += 1
            break
        if length & 0xC0 == 0xC0:
            ptr = ((length & 0x3F) << 8) | msg[pos + 1]
            if not jumped:
                start = pos + 2
            pos = ptr
            jumped = True
            continue
        labels.append(msg[pos + 1:pos + 1 + length].decode(errors="replace"))
        pos += 1 + length
    return ".".join(labels), (start if jumped else pos)


def _dns_parse(msg):
    rcode = msg[3] & 0x0F
    ancount = struct.unpack(">H", msg[6:8])[0]
    pos = 12
    _, pos = _dns_read_name(msg, pos)
    pos += 4  # qtype + qclass
    answers = []
    for _ in range(ancount):
        owner, pos = _dns_read_name(msg, pos)
        rtype, _rclass, ttl, rdlen = struct.unpack(">HHIH", msg[pos:pos + 10])
        rdata = msg[pos + 10:pos + 10 + rdlen]
        val = None
        try:
            if rtype == 1:
                val = socket.inet_ntoa(rdata)
            elif rtype == 28:
                val = socket.inet_ntop(socket.AF_INET6, rdata)
            elif rtype == 16:
                parts, i = [], 0
                while i < len(rdata):
                    ln = rdata[i]
                    parts.append(rdata[i + 1:i + 1 + ln].decode(errors="replace"))
                    i += 1 + ln
                val = "".join(parts)
            elif rtype == 15:
                pref = struct.unpack(">H", rdata[:2])[0]
                name, _ = _dns_read_name(msg, pos + 12)
                val = f"{pref} {name}"
            elif rtype in (2, 5, 12):
                name, _ = _dns_read_name(msg, pos + 10)
                val = name
            elif rtype == 6:
                mname, np = _dns_read_name(msg, pos + 10)
                _rname, np = _dns_read_name(msg, np)
                if np + 4 <= pos + 10 + rdlen:
                    serial = struct.unpack(">I", msg[np:np + 4])[0]
                    val = f"{mname} {serial}"
                else:
                    val = mname
            else:
                val = rdata.hex()
        except Exception:
            val = rdata.hex()
        answers.append({
            "name": owner,
            "type": _DNS_TYPE_NAMES.get(rtype, str(rtype)),
            "ttl": ttl,
            "value": val,
        })
        pos += 10 + rdlen
    return rcode, answers


def _recvn(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def _dnsm_udp_query(host, port, query):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(TIMEOUT)
    try:
        s.sendto(query, (host, port))
        data, _ = s.recvfrom(65535)
        return data
    finally:
        s.close()


def _dnsm_tcp_query(host, port, query):
    s = socket.create_connection((host, port), timeout=TIMEOUT)
    s.settimeout(TIMEOUT)
    try:
        s.sendall(struct.pack(">H", len(query)) + query)
        hdr = _recvn(s, 2)
        if len(hdr) < 2:
            raise ConnectionError("short TCP DNS header")
        ln = struct.unpack(">H", hdr)[0]
        data = _recvn(s, ln)
        if len(data) < ln:
            raise ConnectionError("short TCP DNS body")
        return data
    finally:
        s.close()


def _dnsm_token_headers(params):
    """The console signs in with the fleet admin token unless the operator
    supplied their own."""
    token = params.get("token") or _fleet_secret("DNSM_ADMIN_TOKEN") or ""
    return {"X-Admin-Token": str(token)} if token else {}


def _dnsm_admin_result(status, raw):
    body = raw.decode(errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    summary = body.strip().split("\n", 1)[0] if body.strip() else ""
    if status == 403:
        return {"ok": False, "error": "invalid admin token", "body": body, "summary": summary or "invalid admin token"}
    if status >= 400:
        err = summary or f"HTTP {status}"
        return {"ok": False, "error": err, "body": body, "summary": err}
    return {"ok": True, "summary": summary, "body": body}


def dnsm_query(host, port, params):
    name = params.get("name") or "www.example.com"
    qtype_name = (params.get("type") or "A").upper()
    # NX is an RCODE, not a QTYPE. Defence in depth if a caller sends it.
    if qtype_name == "NX":
        qtype_name = "A"
    qtype = _DNS_TYPES.get(qtype_name, 1)
    txid = 0x1234
    flags = 0x0100  # RD=1 so out-of-zone names recurse
    query = struct.pack(">HHHHHH", txid, flags, 1, 0, 0, 0) + _dns_encode_name(name) + struct.pack(">HH", qtype, 1)
    try:
        if qtype_name == "AXFR":
            data = _dnsm_tcp_query(host, port, query)
        else:
            data = _dnsm_udp_query(host, port, query)
            if len(data) >= 4 and (struct.unpack(">H", data[2:4])[0] & 0x0200):
                data = _dnsm_tcp_query(host, port, query)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    rcode, answers = _dns_parse(data)
    rc = _DNS_RCODES.get(rcode, str(rcode))
    return {
        "ok": True,
        "query": f"{name} {qtype_name}",
        "rcode": rc,
        "answers": answers,
        "summary": (f"{name} {qtype_name} -> " + ", ".join(f"{a['type']} {a['value']}" for a in answers)
                    if answers else f"{name} {qtype_name} -> {rc} (no records)"),
    }


def dnsm_import(host, admin_port, params):
    """Merge zone text into the live zone (POST /admin/import with a body)."""
    if not admin_port:
        return {"ok": False, "error": "no admin port"}
    body = params.get("body") or ""
    if not isinstance(body, str):
        body = str(body)
    if not body.strip():
        return {"ok": False, "error": "zone text required"}
    url = f"http://{host}:{admin_port}/admin/import"
    try:
        status, _, raw = _http("POST", url, body.encode(), _dnsm_token_headers(params))
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return _dnsm_admin_result(status, raw)


def dnsm_reload(host, admin_port, params):
    if not admin_port:
        return {"ok": False, "error": "no admin port"}
    url = f"http://{host}:{admin_port}/admin/reload"
    headers = _dnsm_token_headers(params)
    try:
        status, _, raw = _http("POST", url, b"", headers)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return _dnsm_admin_result(status, raw)


def _resp_encode(parts):
    out = b"*%d\r\n" % len(parts)
    for p in parts:
        pb = p.encode() if isinstance(p, str) else p
        out += b"$%d\r\n%s\r\n" % (len(pb), pb)
    return out


def _resp_read(f):
    line = f.readline()
    if not line:
        raise ConnectionError("connection closed")
    t, body = line[:1], line[1:].strip()
    if t == b"+":
        return body.decode()
    if t == b"-":
        return "(error) " + body.decode()
    if t == b":":
        return int(body)
    if t == b"$":
        n = int(body)
        if n < 0:
            return None
        data = f.read(n)
        f.read(2)
        return data.decode(errors="replace")
    if t == b"*":
        n = int(body)
        if n < 0:
            return None
        return [_resp_read(f) for _ in range(n)]
    return line.decode(errors="replace").strip()


def _resp_format(val):
    if val is None:
        return "(nil)"
    if isinstance(val, list):
        return "[" + ", ".join(_resp_format(v) for v in val) + "]"
    return str(val)


def _eval_parts(parts, script):
    """Splice a script into EVAL as one bulk string.

    `command.split()` cannot round-trip a script with spaces, so the console
    may post `params.script` with a command of EVAL / EVAL <numkeys> [keys...]
    [args...]. Forms that omit `script` keep the plain split.
    """
    if not parts or parts[0].upper() != "EVAL":
        return parts
    rest = parts[1:]
    if not rest:
        return [parts[0], script, "0"]
    if rest[0].lstrip("+-").isdigit():
        return [parts[0], script, rest[0], *rest[1:]]
    i = 0
    while i < len(rest) and not rest[i].lstrip("+-").isdigit():
        i += 1
    if i >= len(rest):
        return [parts[0], script, "0"]
    return [parts[0], script, *rest[i:]]


KVS_MAX_ARGS = 64
KVS_MAX_ARG_BYTES = 16384


def _kvs_parts(params):
    """The argv to send: `args` verbatim when given, else `command` split on
    whitespace (with the optional EVAL `script` spliced in)."""
    args = params.get("args")
    if args is not None:
        if not isinstance(args, list) or not args:
            raise ValueError("args must be a non-empty list")
        if len(args) > KVS_MAX_ARGS:
            raise ValueError(f"at most {KVS_MAX_ARGS} args")
        parts = [a if isinstance(a, str) else str(a) for a in args]
        if any(len(a.encode()) > KVS_MAX_ARG_BYTES for a in parts):
            raise ValueError(f"an argument exceeds {KVS_MAX_ARG_BYTES} bytes")
        return parts
    command = (params.get("command") or "PING").strip() or "PING"
    parts = command.split()
    if "script" in params and parts[0].upper() == "EVAL":
        script = params.get("script")
        parts = _eval_parts(parts, "" if script is None else str(script))
    return parts


def kvs_cmd(host, port, params):
    try:
        parts = _kvs_parts(params)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    command = " ".join(parts)
    # One fresh TCP socket per call. The console signs in with the fleet
    # password unless the operator supplied their own.
    password = params.get("password") or _fleet_secret("KVS_REQUIREPASS") or None
    try:
        s = socket.create_connection((host, port), timeout=TIMEOUT)
        s.settimeout(TIMEOUT)
        f = s.makefile("rb")
        if password:
            s.sendall(_resp_encode(["AUTH", password]))
            _resp_read(f)
        s.sendall(_resp_encode(parts))
        reply = _resp_read(f)
        s.close()
        return {
            "ok": True,
            "command": command,
            "reply": _resp_format(reply),
            "value": reply,
            "summary": f"{command}  ->  {_resp_format(reply)}",
        }
    except (OSError, ConnectionError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def log_ingest(host, port, params):
    base = f"http://{host}:{port}"
    payload = {
        "source": params.get("source") or "bridge",
        "level": params.get("level") or "INFO",
        "message": params.get("message") or "console check-in",
    }
    try:
        status, _, resp = _http("POST", f"{base}/ingest", json.dumps(payload).encode(),
                                {"Content-Type": "application/json"})
        if status != 200:
            return {"ok": False, "error": f"ingest HTTP {status}", "body": resp[:300].decode(errors="replace")}
        j = json.loads(resp)
        return {"ok": True, "stored": j.get("stored"), "source": j.get("source"),
                "level": j.get("level"), "message": j.get("message"),
                "summary": f"Ingested into {j.get('source')}.log: \"{j.get('message')}\""}
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def log_search(host, port, params):
    base = f"http://{host}:{port}"
    q = urllib.parse.quote(params.get("q") or "")
    src = urllib.parse.quote(params.get("source") or "")
    path = f"/search?q={q}"
    if src:
        path += f"&source={src}"
    try:
        status, _, resp = _http("GET", f"{base}{path}")
        if status != 200:
            return {"ok": False, "error": f"search HTTP {status}"}
        j = json.loads(resp)
        matches = j.get("matches", [])
        return {"ok": True, "count": j.get("count", len(matches)), "matches": matches[:25],
                "summary": f"{j.get('count', len(matches))} match(es) for '{params.get('q')}'"}
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def _dashboard_plaintext_lines(html_text):
    """Return newest-first plaintext lines from GET /dashboard HTML.

    Inner HTML of each `.line` is unescaped and kept as a string. The
    wrapper document is
    discarded so the client never pastes `<div class="line">`.
    """
    raw = []
    for m in _LINE_DIV.finditer(html_text or ""):
        raw.append(html.unescape(m.group(1)))
    # Service renders newest last; the ribbon is newest-first.
    return list(reversed(raw))[:_DASHBOARD_CAP]


def log_download(host, port, params):
    # `name` is passed through as typed.
    name = params.get("name") or "nav.log"
    base = f"http://{host}:{port}"
    try:
        status, _, resp = _http("GET", f"{base}/logs/{name}")
        if status == 404:
            return {"ok": False, "error": f"no such log: {name}", "name": name}
        if status != 200:
            return {"ok": False, "error": f"download HTTP {status}", "name": name}
        text = resp.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return {
            "ok": True,
            "name": name,
            "lines": lines,
            "summary": f"{len(lines)} line(s) from /logs/{name}",
        }
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e), "name": name}


def log_wipe(host, port, params):
    name = params.get("name") or "nav.log"
    token = params.get("token") or _fleet_secret("LOG_OP_TOKEN") or "operator-secret-123"
    base = f"http://{host}:{port}"
    try:
        status, _, resp = _http(
            "DELETE", f"{base}/logs/{name}", None,
            {"X-Operator-Token": token},
        )
        if status != 200:
            return {"ok": False, "error": f"wipe HTTP {status}", "name": name}
        j = json.loads(resp)
        return {
            "ok": True,
            "deleted": j.get("deleted"),
            "name": j.get("name", name),
            "summary": f"Deleted /logs/{j.get('name', name)}" if j.get("deleted")
                       else f"No file /logs/{j.get('name', name)}",
        }
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e), "name": name}


def log_dashboard(host, port, params):
    base = f"http://{host}:{port}"
    try:
        status, _, resp = _http("GET", f"{base}/dashboard")
        if status != 200:
            return {"ok": False, "error": f"dashboard HTTP {status}"}
        text = resp.decode("utf-8", errors="replace")
        lines = _dashboard_plaintext_lines(text)
        return {
            "ok": True,
            "lines": lines,
            "summary": f"{len(lines)} recent line(s) from /dashboard",
        }
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def _json_body(resp):
    if not resp:
        return {}
    try:
        return json.loads(resp)
    except ValueError:
        return {}


def _ota_key_header(params):
    """X-OTA-Api-Key from a typed docket.

    Missing or blank uses the fleet's configured OTA_API_KEY.
    """
    key = params.get("api_key") or _fleet_secret("OTA_API_KEY") or ""
    if key == "":
        return {}
    return {"X-OTA-Api-Key": str(key)}


def _ota_fail(status, resp, fallback):
    j = _json_body(resp)
    out = {
        "ok": False,
        "error": j.get("error") if isinstance(j, dict) and j.get("error") else fallback,
        "http_status": status,
    }
    if isinstance(j, dict):
        for k in ("expected", "computed"):
            if k in j:
                out[k] = j[k]
    return out


def ota_status(host, port, params):
    base = f"http://{host}:{port}"
    updates = []
    try:
        _http("GET", f"{base}/health")
        for m in OTA_MODULES:
            status, _, resp = _http("GET", f"{base}/updates/{m}/latest")
            if status == 200:
                latest = _json_body(resp)
                ver = latest.get("manifest", {}).get("version") if isinstance(latest, dict) else "?"
                updates.append({"module": m, "latest": ver or "?"})
        dstatus, _, dresp = _http("GET", f"{base}/devices", headers=_ota_key_header(params))
        if dstatus == 401:
            err = _ota_fail(dstatus, dresp, "unauthorized")
            err["updates"] = updates
            err["devices"] = None
            err["device_count"] = None
            err["summary"] = "devices list unauthorized"
            return err
        if dstatus != 200:
            err = _ota_fail(dstatus, dresp, f"devices HTTP {dstatus}")
            err["updates"] = updates
            err["devices"] = None
            err["device_count"] = None
            return err
        raw = _json_body(dresp)
        devices = raw if isinstance(raw, list) else []
        slim = [{"id": d.get("id"), "module": d.get("module"),
                 "version": d.get("version"), "status": d.get("status")} for d in devices][:25]
        return {
            "ok": True,
            "updates": updates,
            "devices": slim,
            "device_count": len(devices),
            "summary": (f"{len(updates)} module(s) with published updates, "
                        f"{len(devices)} device(s) registered"),
        }
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def ota_latest(host, port, params):
    """GET /updates/{module}/latest — unauthenticated. No API key header."""
    module = str(params.get("module") or "log")
    path_mod = urllib.parse.quote(module, safe="")
    try:
        status, _, resp = _http("GET", f"http://{host}:{port}/updates/{path_mod}/latest")
        if status == 200:
            pkg = _json_body(resp)
            manifest = pkg.get("manifest") if isinstance(pkg, dict) else {}
            if not isinstance(manifest, dict):
                manifest = {}
            ver = manifest.get("version")
            return {
                "ok": True,
                "module": manifest.get("module", module),
                "version": ver,
                "sha256": manifest.get("sha256"),
                "post_install": manifest.get("post_install"),
                "source_url": manifest.get("source_url"),
                "manifest": manifest,
                "summary": f"{module} latest {ver}" if ver else f"{module} latest",
            }
        if status == 404:
            return _ota_fail(status, resp, "nothing published yet")
        return _ota_fail(status, resp, f"latest HTTP {status}")
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def ota_publish(host, port, params):
    """POST /publish. Modelled on ota-module/unit_tests/test_ota.py publish()."""
    module = str(params.get("module") or "log")
    version = str(params.get("version") or "") or ("1.0.0-" + uuid.uuid4().hex[:8])
    source_url = str(params.get("source_url") or "").strip()
    if "post_install" not in params or params.get("post_install") in (None, ""):
        post_install = "none"
    else:
        post_install = str(params.get("post_install"))
    player_sha = str(params.get("sha256") or "").strip()
    headers = dict(_ota_key_header(params))
    try:
        if source_url:
            # README: source_url is the only legal reason to omit the package
            # part.
            manifest = {
                "module": module,
                "version": version,
                "sha256": player_sha or ("0" * 64),
                "source_url": source_url,
                "post_install": post_install,
            }
            ct, body = _multipart({"manifest": json.dumps(manifest)})
        else:
            payload = OTA_HAPPY_PKG
            digest = hashlib.sha256(payload).hexdigest()
            manifest = {
                "module": module,
                "version": version,
                "sha256": player_sha or digest,
                "post_install": post_install,
            }
            ct, body = _multipart(
                {"manifest": json.dumps(manifest)},
                "package", "pkg.tar.gz", payload, "application/gzip")
        headers["Content-Type"] = ct
        status, _, resp = _http("POST", f"http://{host}:{port}/publish", body, headers)
        if status == 201:
            pkg = _json_body(resp)
            if not isinstance(pkg, dict):
                pkg = {}
            man = pkg.get("manifest") if isinstance(pkg.get("manifest"), dict) else manifest
            return {
                "ok": True,
                "manifest": man,
                "size": pkg.get("size"),
                "published_at": pkg.get("published_at"),
                "summary": f"published {man.get('module', module)} {man.get('version', version)}",
            }
        return _ota_fail(status, resp, f"publish HTTP {status}")
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def ota_sync(host, port, params):
    """POST /devices/{id}/sync with the player's body JSON passed through."""
    device_id = (params.get("device_id") or "").strip()
    token = params.get("token") or ""
    if not device_id:
        return {"ok": False, "error": "device_id required"}
    body = {}
    raw_json = params.get("body_json")
    if raw_json not in (None, ""):
        try:
            parsed = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            if isinstance(parsed, dict):
                body.update(parsed)
            else:
                return {"ok": False, "error": "body_json must be a JSON object"}
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            return {"ok": False, "error": f"bad body_json: {e}"}
    for k in ("module", "version", "status", "trusted", "last_seen"):
        if k in params and params.get(k) not in (None, ""):
            v = params.get(k)
            if k == "trusted":
                body[k] = _truthy(v) if not isinstance(v, bool) else v
            else:
                body[k] = v
    # Allow freeform extra keys via params.extra_json
    extra = params.get("extra_json")
    if extra not in (None, ""):
        try:
            parsed = json.loads(extra) if isinstance(extra, str) else extra
            if isinstance(parsed, dict):
                body.update(parsed)
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            return {"ok": False, "error": f"bad extra_json: {e}"}
    url = f"http://{host}:{port}/devices/{urllib.parse.quote(device_id)}/sync"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    try:
        status, _, resp = _http("POST", url, json.dumps(body).encode(), headers)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    j = _json_body(resp)
    if status >= 400:
        return _ota_fail(status, resp, f"sync HTTP {status}")
    out = {"ok": True, "http_status": status, "device": j if isinstance(j, dict) else None,
           "sent": body, "summary": f"sync {device_id} HTTP {status}"}
    if isinstance(j, dict) and "trusted" in j:
        out["trusted"] = j.get("trusted")
        out["summary"] += f" trusted={j.get('trusted')}"
    return out


def ota_report(host, port, params):
    device_id = str(params.get("device_id") or "")
    token = str(params.get("token") or "")
    version = str(params.get("version") or "")
    st = str(params.get("status") or "applied")
    if not device_id or not token:
        return {"ok": False, "error": "device_id and token required"}
    path_id = urllib.parse.quote(device_id, safe="")
    body = json.dumps({"version": version, "status": st}).encode()
    try:
        status, _, resp = _http(
            "POST", f"http://{host}:{port}/devices/{path_id}/report", body,
            {"Content-Type": "application/json",
             "Authorization": f"Bearer {token}"})
        if status == 200:
            return {"ok": True, "status": "recorded",
                    "summary": f"recorded {device_id}"}
        return _ota_fail(status, resp, f"report HTTP {status}")
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def _mqtt_u8(s):
    b = s.encode() if isinstance(s, str) else s
    return struct.pack("!H", len(b)) + b


def _mqtt_rl(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n > 0:
            b |= 0x80
        out.append(b)
        if n == 0:
            break
    return bytes(out)


def _mqtt_read_packet(sock, timeout=TIMEOUT):
    sock.settimeout(timeout)
    try:
        first = sock.recv(1)
    except socket.timeout:
        return None
    if not first:
        return None
    ptype = first[0] >> 4
    flags = first[0] & 0x0F
    mult, val = 1, 0
    while True:
        b = sock.recv(1)
        if not b:
            return None
        val += (b[0] & 0x7F) * mult
        if not (b[0] & 0x80):
            break
        mult *= 128
    body = b""
    while len(body) < val:
        chunk = sock.recv(val - len(body))
        if not chunk:
            break
        body += chunk
    return ptype, flags, body


def _as_bool(v, default=False):
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def _as_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _mqb_password(params):
    """The console signs in with the fleet password unless the operator
    supplied their own."""
    pw = params.get("password") if isinstance(params, dict) else None
    return (str(pw) if pw else None) or _fleet_secret("MQB_REQUIREPASS") or None


def _mqtt_bytes(v):
    if v is None:
        return b""
    if isinstance(v, bytes):
        return v
    if isinstance(v, list):
        v = "\n".join(str(x) for x in v)
    return str(v).encode()


def _mqtt_send_connect(sock, client_id, password=None, clean_session=True,
                       keep_alive=30, will_topic=None, will_message=None,
                       will_qos=0, will_retain=False, username=None):
    flags = (1 if clean_session else 0) << 1
    will_topic = will_topic or ""
    has_will = bool(will_topic)
    if has_will:
        flags |= 0x04 | ((will_qos & 3) << 3) | ((1 if will_retain else 0) << 5)
    if username is not None:
        flags |= 0x80
    if password is not None:
        flags |= 0x40
    body = _mqtt_u8("MQTT") + bytes([4, flags]) + struct.pack("!H", keep_alive)
    body += _mqtt_u8(client_id if client_id is not None else "")
    if has_will:
        body += _mqtt_u8(will_topic)
        wm = _mqtt_bytes(will_message)
        body += struct.pack("!H", len(wm)) + wm
    if username is not None:
        body += _mqtt_u8(username)
    if password is not None:
        pb = password.encode() if isinstance(password, str) else password
        body += struct.pack("!H", len(pb)) + pb
    sock.sendall(bytes([0x10]) + _mqtt_rl(len(body)) + body)
    return _mqtt_read_packet(sock)


def _mqtt_decode_publish(pkt):
    ptype, flags, body = pkt
    qos = (flags >> 1) & 0x03
    retain = bool(flags & 0x01)
    tlen = struct.unpack_from("!H", body, 0)[0]
    topic = body[2:2 + tlen].decode(errors="replace")
    offset = 2 + tlen
    packet_id = None
    if qos > 0:
        packet_id = struct.unpack_from("!H", body, offset)[0]
        offset += 2
    payload = body[offset:].decode(errors="replace")
    return {"topic": topic, "payload": payload, "qos": qos,
            "retain": retain, "packet_id": packet_id}


def _mqtt_puback(sock, packet_id):
    sock.sendall(bytes([0x40, 0x02]) + struct.pack("!H", packet_id))


def _mqtt_wait(sock, want_type, timeout=TIMEOUT):
    deadline = time.time() + timeout
    extras = []
    while time.time() < deadline:
        remain = max(0.05, deadline - time.time())
        try:
            pkt = _mqtt_read_packet(sock, timeout=remain)
        except (OSError, IndexError, struct.error):
            return None, extras
        if not pkt:
            continue
        if pkt[0] == want_type:
            return pkt, extras
        if pkt[0] == 3:
            rec = _mqtt_decode_publish(pkt)
            extras.append(rec)
            if rec.get("packet_id") is not None:
                try:
                    _mqtt_puback(sock, rec["packet_id"])
                except OSError:
                    pass
    return None, extras


def _mqtt_drain_publish(sock, timeout=0.35):
    got = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pkt = _mqtt_read_packet(sock, timeout=max(0.05, deadline - time.time()))
        except (OSError, IndexError, struct.error, socket.timeout):
            break
        if not pkt:
            break
        if pkt[0] != 3:
            break
        rec = _mqtt_decode_publish(pkt)
        got.append(rec)
        if rec.get("packet_id") is not None:
            try:
                _mqtt_puback(sock, rec["packet_id"])
            except OSError:
                pass
    return got


def _mqb_next_pid(ses):
    pid = ses.get("pkt", 1)
    ses["pkt"] = 1 if pid >= 65535 else pid + 1
    return pid


def _mqb_drop(client_id, close=True, graceful=False):
    with _MQB_SESS_LOCK:
        ses = _MQB_SESSIONS.pop(client_id, None)
    if not ses or not close:
        return ses
    sock = ses.get("sock")
    if sock:
        try:
            if graceful:
                sock.sendall(bytes([0xE0, 0x00]))
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass
    return ses


def _mqb_session(params):
    cid = params.get("client_id")
    if cid is None:
        cid = ""
    else:
        cid = str(cid)
    with _MQB_SESS_LOCK:
        ses = _MQB_SESSIONS.get(cid)
    if not ses:
        return None, cid, {"ok": False, "error": "no held session for that client_id"}
    return ses, cid, None


_MQB_CONNACK = {
    1: "refused: protocol version",
    2: "refused: client id",
    3: "refused: server unavailable",
    4: "refused: bad user name or password",
    5: "refused: not authorized",
}


def _mqb_keep(ses, recs):
    """Messages that arrived while the console waited for something else are
    kept for the next drain."""
    inbox = ses.setdefault("inbox", [])
    inbox.extend({"topic": r["topic"], "payload": r["payload"], "retain": r["retain"]}
                 for r in recs)
    del inbox[:-MQB_INBOX_CAP]


def mqb_roundtrip(host, port, params):
    topic = params.get("topic") or "bridge/telemetry"
    message = params.get("message") or "ping from bridge"
    password = _mqb_password(params)
    cid_sub = "bridge-sub-" + uuid.uuid4().hex[:8]
    cid_pub = "bridge-pub-" + uuid.uuid4().hex[:8]
    sub = pub = None
    try:
        sub = socket.create_connection((host, port), timeout=TIMEOUT)
        r = _mqtt_send_connect(sub, cid_sub, password)
        if not r or r[0] != 2 or r[2][1] != 0:
            return {"ok": False, "error": f"subscriber CONNECT refused (CONNACK={r})"}
        body = struct.pack("!H", 1) + _mqtt_u8(topic) + bytes([0])
        sub.sendall(bytes([0x82]) + _mqtt_rl(len(body)) + body)
        suback = _mqtt_read_packet(sub)
        if not suback or suback[0] != 9:
            return {"ok": False, "error": "no SUBACK from broker"}

        pub = socket.create_connection((host, port), timeout=TIMEOUT)
        r = _mqtt_send_connect(pub, cid_pub, password)
        if not r or r[0] != 2 or r[2][1] != 0:
            return {"ok": False, "error": f"publisher CONNECT refused (CONNACK={r})"}
        pbody = _mqtt_u8(topic) + message.encode()
        pub.sendall(bytes([0x30]) + _mqtt_rl(len(pbody)) + pbody)

        got = _mqtt_read_packet(sub, timeout=4.0)
        if not got or got[0] != 3:
            return {"ok": False, "error": "message not delivered back to subscriber"}
        rec = _mqtt_decode_publish(got)
        return {
            "ok": True,
            "topic": rec["topic"],
            "payload": rec["payload"],
            "summary": (f"Round-trip OK: published to '{rec['topic']}', "
                        f"subscriber received \"{rec['payload']}\""),
        }
    except (OSError, IndexError, struct.error) as e:
        return {"ok": False, "error": str(e)}
    finally:
        for sk in (sub, pub):
            if sk:
                try:
                    sk.close()
                except OSError:
                    pass


def mqb_connect(host, port, params):
    client_id = params.get("client_id")
    client_id = "" if client_id is None else str(client_id)
    password = _mqb_password(params)
    keep_alive = max(0, _as_int(params.get("keep_alive"), 30))
    will_topic = params.get("will_topic") or ""
    will_message = params.get("will_message")
    _mqb_drop(client_id, close=True, graceful=False)
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=TIMEOUT)
        r = _mqtt_send_connect(
            sock, client_id, password=password, clean_session=True,
            keep_alive=keep_alive, will_topic=will_topic, will_message=will_message)
        if not r or r[0] != 2 or len(r[2]) < 2:
            sock.close()
            return {"ok": False, "error": f"no CONNACK (got {r})",
                    "connack": None, "client_id": client_id}
        rc = r[2][1]
        if rc != 0:
            sock.close()
            return {"ok": False, "connack": rc, "client_id": client_id,
                    "error": _MQB_CONNACK.get(rc, f"CONNACK rc={rc}"),
                    "summary": f"CONNACK rc={rc} id={client_id or '(empty)'}"}
        with _MQB_SESS_LOCK:
            _MQB_SESSIONS[client_id] = {
                "sock": sock, "pkt": 1, "host": host, "port": port,
                "keep_alive": keep_alive, "inbox": [],
            }
        return {
            "ok": True,
            "connack": rc,
            "client_id": client_id,
            "summary": f"CONNACK rc=0 id={client_id or '(empty)'}",
        }
    except (OSError, IndexError, struct.error) as e:
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        return {"ok": False, "error": str(e), "client_id": client_id}


def mqb_publish(host, port, params):
    ses, cid, err = _mqb_session(params)
    if err:
        return err
    topic = params.get("topic") or ""
    message = params.get("message")
    if message is None:
        message = ""
    qos = 1 if _as_int(params.get("qos"), 0) else 0
    retain = _as_bool(params.get("retain"), False)
    payload = _mqtt_bytes(message)
    flags = (qos << 1) | (1 if retain else 0)
    sock = ses["sock"]
    try:
        body = _mqtt_u8(topic)
        pid = None
        if qos:
            pid = _mqb_next_pid(ses)
            body += struct.pack("!H", pid)
        body += payload
        sock.sendall(bytes([0x30 | flags]) + _mqtt_rl(len(body)) + body)
        puback = None
        if qos:
            pkt, extras = _mqtt_wait(sock, 4, timeout=TIMEOUT)
            _mqb_keep(ses, extras)
            if not pkt:
                return {"ok": False, "error": "no PUBACK", "topic": topic,
                        "qos": qos, "retain": retain, "client_id": cid}
            puback = struct.unpack_from("!H", pkt[2], 0)[0] if len(pkt[2]) >= 2 else pid
        out = {"ok": True, "topic": topic, "qos": qos, "retain": retain,
               "client_id": cid,
               "summary": f"PUBLISH {topic} qos={qos} retain={int(retain)} ({len(payload)} B)"}
        if puback is not None:
            out["puback"] = puback
        return out
    except (OSError, IndexError, struct.error) as e:
        _mqb_drop(cid, close=True, graceful=False)
        return {"ok": False, "error": str(e), "client_id": cid}


def mqb_subscribe(host, port, params):
    ses, cid, err = _mqb_session(params)
    if err:
        return err
    topic = params.get("topic") or ""
    qos = 1 if _as_int(params.get("qos"), 0) else 0
    sock = ses["sock"]
    try:
        pid = _mqb_next_pid(ses)
        body = struct.pack("!H", pid) + _mqtt_u8(topic) + bytes([qos])
        sock.sendall(bytes([0x82]) + _mqtt_rl(len(body)) + body)
        pkt, extras = _mqtt_wait(sock, 9, timeout=TIMEOUT)
        if not pkt:
            return {"ok": False, "error": "no SUBACK", "client_id": cid}
        granted = pkt[2][2] if len(pkt[2]) >= 3 else None
        got = extras + _mqtt_drain_publish(sock)
        out = {"ok": True, "granted_qos": granted, "client_id": cid,
               "topic": topic,
               "summary": f"SUBACK {topic} granted={granted}"}
        if got:
            out["messages"] = [{"topic": r["topic"], "payload": r["payload"],
                                "retain": r["retain"]} for r in got]
        return out
    except (OSError, IndexError, struct.error) as e:
        _mqb_drop(cid, close=True, graceful=False)
        return {"ok": False, "error": str(e), "client_id": cid}


def mqb_unsubscribe(host, port, params):
    ses, cid, err = _mqb_session(params)
    if err:
        return err
    topic = params.get("topic") or ""
    sock = ses["sock"]
    try:
        pid = _mqb_next_pid(ses)
        body = struct.pack("!H", pid) + _mqtt_u8(topic)
        sock.sendall(bytes([0xA2]) + _mqtt_rl(len(body)) + body)
        pkt, extras = _mqtt_wait(sock, 11, timeout=TIMEOUT)
        _mqb_keep(ses, extras)
        if not pkt:
            return {"ok": False, "error": "no UNSUBACK", "client_id": cid}
        return {"ok": True, "client_id": cid, "topic": topic,
                "summary": f"UNSUBACK {topic}"}
    except (OSError, IndexError, struct.error) as e:
        _mqb_drop(cid, close=True, graceful=False)
        return {"ok": False, "error": str(e), "client_id": cid}


def mqb_ping(host, port, params):
    ses, cid, err = _mqb_session(params)
    if err:
        return err
    sock = ses["sock"]
    try:
        sock.sendall(bytes([0xC0, 0x00]))
        pkt, extras = _mqtt_wait(sock, 13, timeout=TIMEOUT)
        _mqb_keep(ses, extras)
        if not pkt:
            return {"ok": False, "error": "no PINGRESP", "client_id": cid}
        return {"ok": True, "client_id": cid, "summary": "PINGRESP"}
    except (OSError, IndexError, struct.error) as e:
        _mqb_drop(cid, close=True, graceful=False)
        return {"ok": False, "error": str(e), "client_id": cid}


def mqb_disconnect(host, port, params):
    ses, cid, err = _mqb_session(params)
    if err:
        return err
    graceful = _as_bool(params.get("graceful"), True)
    sock = ses.get("sock")
    try:
        if graceful and sock:
            sock.sendall(bytes([0xE0, 0x00]))
    except OSError:
        pass
    _mqb_drop(cid, close=True, graceful=False)
    return {"ok": True, "graceful": graceful, "client_id": cid,
            "summary": "DISCONNECT" if graceful else "TCP drop (will fires)"}


def mqb_drain(host, port, params):
    """Whatever the broker has delivered to the held session since the last
    call, oldest first."""
    ses, cid, err = _mqb_session(params)
    if err:
        return err
    try:
        got = _mqtt_drain_publish(ses["sock"], timeout=0.25)
    except (OSError, IndexError, struct.error) as e:
        _mqb_drop(cid, close=True, graceful=False)
        return {"ok": False, "error": str(e), "client_id": cid}
    _mqb_keep(ses, got)
    msgs, ses["inbox"] = ses["inbox"], []
    return {"ok": True, "client_id": cid, "messages": msgs,
            "summary": f"{len(msgs)} message(s)"}


def mqb_stats(host, port, params, admin_port=None):
    if not admin_port:
        return {"ok": False, "error": "no adminPort for MQB"}
    try:
        st, _, raw = _http("GET", f"http://{host}:{admin_port}/admin/stats")
        stats = json.loads(raw) if st == 200 else {}
        clients_connected = stats.get("clients_connected")
        retained_count = stats.get("retained_topics")
        return {
            "ok": st == 200,
            "clients_connected": clients_connected,
            "retained_count": retained_count,
            "summary": f"clients={clients_connected} retained={retained_count}",
        }
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def mail_send(host, port, params, admin_port=None):
    mail_from = params.get("from") or "bridge@auditor-7.ship"
    rcpt_to = params.get("to") or "ops@station.example"
    subject = params.get("subject") or "Bridge console test"
    bodytext = params.get("body") or "Subspace relay check."
    user = params.get("user") or ""
    password = params.get("pass") or ""
    mech = (params.get("mech") or "PLAIN").strip().upper() or "PLAIN"
    webhook = params.get("webhook") or ""
    auth_param = params.get("auth_param")  # MAIL FROM AUTH=<xtext>
    message_id = params.get("message_id")  # DATA Message-ID
    want_tls = _truthy(params.get("starttls"))
    token = uuid.uuid4().hex[:8]
    transcript = []
    s = None
    try:
        s = socket.create_connection((host, port), timeout=TIMEOUT)
        s.settimeout(TIMEOUT)

        def read_reply():
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                lines = [l for l in data.split(b"\r\n") if l]
                if lines and len(lines[-1]) >= 4 and lines[-1][3:4] != b"-" and data.endswith(b"\r\n"):
                    break
            return data.decode(errors="replace").strip()

        def cmd(line):
            s.sendall((line + "\r\n").encode())
            r = read_reply()
            transcript.append(f"> {line}")
            transcript.append(r)
            return r

        banner = read_reply()
        transcript.append(banner)
        cmd("EHLO bridge.auditor-7.ship")

        if want_tls:
            tls_reply = cmd("STARTTLS")
            if not tls_reply.startswith("220"):
                try:
                    cmd("QUIT")
                except OSError:
                    pass
                return {"ok": False, "error": f"STARTTLS rejected: {tls_reply}",
                        "transcript": transcript}
            ctx = ssl._create_unverified_context()
            s = ctx.wrap_socket(s, server_hostname=host)
            s.settimeout(TIMEOUT)
            # smtp.js nulls heloName on STARTTLS — EHLO again before AUTH/MAIL.
            cmd("EHLO bridge.auditor-7.ship")

        if user and password:
            if mech == "LOGIN":
                r = cmd("AUTH LOGIN")
                if not r.startswith("334"):
                    return {"ok": False, "error": f"AUTH LOGIN rejected: {r}",
                            "transcript": transcript}
                r = cmd(base64.b64encode(user.encode()).decode())
                if not r.startswith("334"):
                    return {"ok": False, "error": f"AUTH LOGIN username rejected: {r}",
                            "transcript": transcript}
                r = cmd(base64.b64encode(password.encode()).decode())
            else:
                creds = base64.b64encode(f"\0{user}\0{password}".encode()).decode()
                r = cmd(f"AUTH PLAIN {creds}")
            if not r.startswith("235"):
                try:
                    cmd("QUIT")
                except OSError:
                    pass
                return {"ok": False, "error": f"AUTH failed: {r}",
                        "transcript": transcript}

        mail_line = f"MAIL FROM:<{mail_from}>"
        if auth_param not in (None, ""):
            mail_line += f" AUTH={auth_param}"
        cmd(mail_line)
        cmd(f"RCPT TO:<{rcpt_to}>")
        data_reply = cmd("DATA")
        if not data_reply.startswith("354"):
            try:
                cmd("QUIT")
            except OSError:
                pass
            return {"ok": False, "error": f"DATA rejected: {data_reply}", "transcript": transcript}
        # Header values are sent as typed.
        headers = f"Subject: {subject} [{token}]\r\n"
        if message_id not in (None, ""):
            headers += "Message-ID: " + str(message_id)
            if not headers.endswith("\n"):
                headers += "\r\n"
        if webhook:
            headers += "X-Notify-Webhook: " + webhook
            if not headers.endswith("\n"):
                headers += "\r\n"
        message = headers + f"\r\n{bodytext}\r\n."
        final = cmd(message)
        cmd("QUIT")
        queued_as = None
        if "queued as" in final:
            queued_as = final.split("queued as")[-1].strip()
        result = {
            "ok": final.startswith("250"),
            "queued_as": queued_as,
            "transcript": transcript,
            "summary": (f"Relayed {mail_from} -> {rcpt_to}, queued as {queued_as}"
                        if final.startswith("250") else f"Relay failed: {final}"),
        }
        if queued_as and admin_port:
            try:
                astatus, _, aresp = _http("GET", f"http://{host}:{admin_port}/queue/{queued_as}")
                if astatus == 200:
                    detail = json.loads(aresp)
                    raw = detail.get("raw", "")
                    confirmed = bodytext in raw
                    if webhook:
                        confirmed = confirmed and (webhook in raw)
                    result["admin_confirmed"] = confirmed
            except (OSError, ValueError):
                pass
        return result
    except OSError as e:
        return {"ok": False, "error": str(e), "transcript": transcript}
    finally:
        if s is not None:
            try:
                s.close()
            except OSError:
                pass


def mail_queue(host, admin_port, params):
    """Admin queue list (empty name) or GET /queue/<name> (metadata + raw)."""
    if not admin_port:
        return {"ok": False, "error": "mail admin port not configured"}
    name = params.get("name") or ""
    if name:
        url = f"http://{host}:{admin_port}/queue/{name}"
    else:
        url = f"http://{host}:{admin_port}/queue"
    try:
        status, _, resp = _http("GET", url)
        if status == 404:
            return {"ok": False, "error": "not found", "status": 404, "name": name}
        if status != 200:
            return {"ok": False, "error": f"queue lookup HTTP {status}", "status": status}
        detail = json.loads(resp)
        if name:
            return {"ok": True, "name": name, "entry": detail,
                    "raw": detail.get("raw", ""), "summary": f"queue {name}"}
        return {"ok": True, "entries": detail, "summary": f"{len(detail)} queued"}
    except (OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
# --------------------------------------------------------------------------
# A.L.I.E.N. local teaching ships (AL01–AL04) — localhost catalog ports only.
# Curriculum interact surface for the cockpit campaign UI.
# --------------------------------------------------------------------------

_ALIEN_BODY_MAX = 65536


def _alien_text(body):
    if body is None:
        return ""
    if isinstance(body, bytes):
        text = body[:_ALIEN_BODY_MAX].decode("utf-8", errors="replace")
    else:
        text = str(body)[:_ALIEN_BODY_MAX]
    return text


def _alien_base(host, port):
    return f"http://{host}:{int(port)}"


def al01_scan(host, port, params):
    coords = str(params.get("coords") or "")
    if len(coords) > 512:
        return {"ok": False, "error": "coords exceeds 512-char lab cap"}
    data = urllib.parse.urlencode({"coords": coords}).encode()
    url = _alien_base(host, port) + "/scan"
    try:
        status, _hdrs, body = _http(
            "POST", url, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=12.0)
    except (OSError, urllib.error.URLError) as e:
        return {"ok": False, "error": str(e), "summary": "navcomputer unreachable"}
    text = _alien_text(body)
    return {
        "ok": 200 <= status < 400,
        "httpStatus": status,
        "body": text,
        "summary": f"scan HTTP {status} ({len(text)} B)",
    }


def al01_health(host, port, params):
    url = _alien_base(host, port) + "/"
    try:
        status, _hdrs, body = _http("GET", url, timeout=TIMEOUT)
    except (OSError, urllib.error.URLError) as e:
        return {"ok": False, "error": str(e), "summary": "navcomputer unreachable"}
    text = _alien_text(body)
    return {
        "ok": 200 <= status < 400,
        "httpStatus": status,
        "body": text,
        "summary": f"health HTTP {status}",
    }


def al02_manifest(host, port, params):
    file_name = str(params.get("file") or "")
    if len(file_name) > 512:
        return {"ok": False, "error": "file exceeds 512-char lab cap"}
    q = urllib.parse.urlencode({"file": file_name})
    url = _alien_base(host, port) + "/manifest?" + q
    try:
        status, _hdrs, body = _http("GET", url, timeout=TIMEOUT)
    except (OSError, urllib.error.URLError) as e:
        return {"ok": False, "error": str(e), "summary": "cargo unreachable"}
    text = _alien_text(body)
    return {
        "ok": 200 <= status < 400,
        "httpStatus": status,
        "body": text,
        "summary": f"manifest HTTP {status} ({len(text)} B)",
    }


def al03_session(host, port, params):
    """Send reactor_session cookie (base64 PHP serialize) to the reactor."""
    cookie = str(params.get("cookie") or "").strip()
    payload = str(params.get("payload") or "").strip()
    if not cookie:
        if payload:
            raw = payload.encode("utf-8", errors="replace")
            try:
                # Accept already-base64 payloads (round-trip check).
                dec = base64.b64decode(payload.encode("ascii"), validate=True)
                if base64.b64encode(dec).decode("ascii") == payload.replace("\n", ""):
                    cookie = payload.strip()
                else:
                    cookie = base64.b64encode(raw).decode("ascii")
            except (binascii.Error, ValueError, UnicodeEncodeError):
                cookie = base64.b64encode(raw).decode("ascii")
        else:
            return {"ok": False, "error": "a player value is required"}
    if len(cookie) > 8192:
        return {"ok": False, "error": "cookie exceeds 8 KiB lab cap"}
    url = _alien_base(host, port) + "/"
    headers = {"Cookie": "reactor_session=" + cookie}
    try:
        status, _hdrs, body = _http("GET", url, headers=headers, timeout=TIMEOUT)
    except (OSError, urllib.error.URLError) as e:
        return {"ok": False, "error": str(e), "summary": "reactor unreachable"}
    text = _alien_text(body)
    return {
        "ok": 200 <= status < 400,
        "httpStatus": status,
        "body": text,
        "summary": f"session HTTP {status} ({len(text)} B)",
    }


def al04_get(host, port, params):
    """Plain GET against a path on the docking bay."""
    path = str(params.get("path") or "/")
    if not path.startswith("/"):
        path = "/" + path
    if "://" in path or "\n" in path or "\r" in path:
        return {"ok": False, "error": "path not allowed", "summary": "refused"}
    if len(path) > 512:
        return {"ok": False, "error": "path exceeds 512-char lab cap"}
    url = _alien_base(host, port) + path
    try:
        status, _hdrs, body = _http("GET", url, timeout=TIMEOUT)
    except (OSError, urllib.error.URLError) as e:
        return {"ok": False, "error": str(e), "summary": "docking unreachable"}
    text = _alien_text(body)
    return {
        "ok": 200 <= status < 500,
        "httpStatus": status,
        "body": text,
        "summary": f"GET {path} HTTP {status} ({len(text)} B)",
    }


def dispatch(code, action, params, host, port, admin_port=None):
    """Route (code, action) to the right protocol interactor. Returns a
    JSON-serializable dict; never raises for a service-side failure."""
    params = params or {}
    try:
        if code == "FMM" and action == "login":
            return fmm_login(host, port, params)
        if code == "FMM" and action == "sess":
            return fmm_sess(host, port, params)
        if code == "FMM" and action == "list":
            return fmm_list(host, port, params)
        if code == "FMM" and action == "cwd":
            return fmm_cwd(host, port, params)
        if code == "FMM" and action == "retr":
            return fmm_retr(host, port, params)
        if code == "FMM" and action == "stor":
            return fmm_stor(host, port, params)
        if code == "FMM" and action == "type":
            return fmm_type(host, port, params)
        if code == "IPM" and action == "convert":
            return ipm_convert(host, port, params)
        if code == "IPM" and action == "convert-url":
            return ipm_convert_url(host, port, params)
        if code == "IPM" and action == "convert-batch":
            return ipm_convert_batch(host, port, params)
        if code == "IPM" and action == "image":
            return ipm_image(host, port, params)
        if code == "IPM" and action == "health":
            return ipm_health(host, port, params)
        if code == "DNSM" and action == "query":
            return dnsm_query(host, port, params)
        if code == "DNSM" and action == "import":
            return dnsm_import(host, admin_port, params)
        if code == "DNSM" and action == "reload":
            return dnsm_reload(host, admin_port, params)
        if code == "KVS" and action == "cmd":
            return kvs_cmd(host, port, params)
        if code == "LOG" and action == "ingest":
            return log_ingest(host, port, params)
        if code == "LOG" and action == "search":
            return log_search(host, port, params)
        if code == "LOG" and action == "download":
            return log_download(host, port, params)
        if code == "LOG" and action == "wipe":
            return log_wipe(host, port, params)
        if code == "LOG" and action == "dashboard":
            return log_dashboard(host, port, params)
        if code == "OTA" and action == "status":
            return ota_status(host, port, params)
        if code == "OTA" and action == "latest":
            return ota_latest(host, port, params)
        if code == "OTA" and action == "publish":
            return ota_publish(host, port, params)
        if code == "OTA" and action == "report":
            return ota_report(host, port, params)
        if code == "OTA" and action == "sync":
            return ota_sync(host, port, params)
        if code == "MQB" and action == "roundtrip":
            return mqb_roundtrip(host, port, params)
        if code == "MQB" and action == "connect":
            return mqb_connect(host, port, params)
        if code == "MQB" and action == "publish":
            return mqb_publish(host, port, params)
        if code == "MQB" and action == "subscribe":
            return mqb_subscribe(host, port, params)
        if code == "MQB" and action == "unsubscribe":
            return mqb_unsubscribe(host, port, params)
        if code == "MQB" and action == "ping":
            return mqb_ping(host, port, params)
        if code == "MQB" and action == "disconnect":
            return mqb_disconnect(host, port, params)
        if code == "MQB" and action == "stats":
            return mqb_stats(host, port, params, admin_port=admin_port)
        if code == "MQB" and action == "drain":
            return mqb_drain(host, port, params)
        if code in ("MAIL", "MTA") and action == "send":
            return mail_send(host, port, params, admin_port=admin_port)
        if code in ("MAIL", "MTA") and action == "queue":
            return mail_queue(host, admin_port, params)
        if code == "AL01" and action == "scan":
            return al01_scan(host, port, params)
        if code == "AL01" and action == "health":
            return al01_health(host, port, params)
        if code == "AL02" and action == "manifest":
            return al02_manifest(host, port, params)
        if code == "AL03" and action == "session":
            return al03_session(host, port, params)
        if code == "AL04" and action == "get":
            return al04_get(host, port, params)
        return {"ok": False, "error": f"unknown action {code}/{action}"}
    except Exception as e:  # pragma: no cover - last-resort guard
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
