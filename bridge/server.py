#!/usr/bin/env python3
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

import alien_local
import harness
import interactors
import rebuild
import release
import updater

ROOT = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(ROOT, "data", "catalog.json")
COMPOSE_PATH = os.path.join(ROOT, "fleet-compose.yml")
REPO_ROOT = os.path.dirname(ROOT)
SECRETS_PATH = os.path.join(REPO_ROOT, "secrets", "fleet.env")
ALIENS_COMPOSE = os.path.join(REPO_ROOT, "aliens", "docker-compose.yml")
# Cockpit files stay on disk under cockpit-ui/live3d. Public URLs do not
# use that name: the app is served at /, sibling trees at their own prefixes.
COCKPIT_UI = os.path.join(REPO_ROOT, "cockpit-ui")
COCKPIT_APP = os.path.join(COCKPIT_UI, "live3d")
COCKPIT_INDEX = os.path.join(COCKPIT_APP, "index.html")
SIGNIN_INDEX = os.path.join(COCKPIT_APP, "auth", "index.html")
_COCKPIT_SIBLING_PREFIXES = (
    "/cockpit",
    "/fonts",
    "/three-exploration",
    "/style",
    "/plans",
)
_BLOCKED_PUBLIC = ("live3d", "static")
_COCKPIT_BASE = b'<base href="/">'
# Sign-in is the auth document, served at /. Base keeps its relative assets
# on /auth/ so the browser address never contains the on-disk app directory.
_SIGNIN_BASE = b'<base href="/auth/">'

POWER_OPS = {
    "start": ["up", "-d", "--no-recreate"],
    "stop": ["stop"],
    "restart": ["restart"],
}
POWER_TIMEOUTS = {"start": 1800}

PORT = int(os.environ.get("BRIDGE_PORT", "8787"))
HOST = os.environ.get("BRIDGE_HOST", "127.0.0.1")
LIVE_HOST = os.environ.get("BRIDGE_LIVE_HOST", "127.0.0.1")
# "host": dial LIVE_HOST on the published ports (console run on the host).
# "compose": dial each module by its compose service name on its container
# port (console running inside fleet-compose.yml, any platform).
LIVE_MODE = os.environ.get("BRIDGE_LIVE_MODE", "host")

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".bin": "application/octet-stream",
    ".wasm": "application/wasm",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def _normalize_url_path(url_path):
    """Collapse dot segments. Does not follow the filesystem."""
    path = unquote((url_path or "/").split("?", 1)[0])
    if "\x00" in path:
        return None
    parts = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def _first_segment(url_path):
    """First real path segment, or None if the path is unusable."""
    raw = unquote((url_path or "").split("?", 1)[0])
    if "\x00" in raw:
        return None
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        return part
    return ""


def _dot_denied(norm):
    if not norm:
        return True
    for part in norm.split("/"):
        if part.startswith(".") and part != ".well-known":
            return True
    return False


def _blocked_public(url_path):
    """Old console and /live3d are not addresses. No redirect."""
    first = _first_segment(url_path)
    if first is None or first.lower() in _BLOCKED_PUBLIC:
        return True
    norm = _normalize_url_path(url_path)
    if not norm:
        return True
    lower = norm.lower()
    for name in _BLOCKED_PUBLIC:
        prefix = "/" + name
        if lower == prefix or lower.startswith(prefix + "/"):
            return True
    return False


def _sibling_allowed(norm):
    if not norm or norm in ("/", "") or _dot_denied(norm):
        return False
    lower = norm.lower()
    for prefix in _COCKPIT_SIBLING_PREFIXES:
        if lower == prefix or lower.startswith(prefix + "/"):
            return True
    return False


def _app_allowed(norm):
    """A cockpit-app path served from the on-disk app tree at the site root."""
    if not norm or norm in ("/", "") or _dot_denied(norm):
        return False
    lower = norm.lower()
    for name in _BLOCKED_PUBLIC:
        prefix = "/" + name
        if lower == prefix or lower.startswith(prefix + "/"):
            return False
    if _sibling_allowed(norm):
        return False
    return True


def _wants_sibling(url_path):
    first = _first_segment(url_path)
    if first is None:
        return False
    if "/" + first.lower() in _COCKPIT_SIBLING_PREFIXES:
        return True
    norm = _normalize_url_path(url_path)
    return bool(norm) and _sibling_allowed(norm)


def _within(root, path):
    root_real = os.path.realpath(root)
    path_real = os.path.realpath(path)
    return path_real == root_real or path_real.startswith(root_real + os.sep)


def _with_base(data, base):
    """Insert a base href unless the document already has one."""
    lower = data.lower()
    if b"<base " in lower or b"<base>" in lower:
        return data
    idx = lower.find(b"<meta")
    if idx == -1:
        idx = lower.find(b"<title")
    if idx == -1:
        return base + b"\n" + data
    return data[:idx] + base + b"\n" + data[idx:]


def _read_html(path, base):
    with open(path, "rb") as fh:
        return _with_base(fh.read(), base)


def _cockpit_index_bytes():
    """Cockpit page for a signed-in GET /. Base href keeps assets on the site root."""
    return _read_html(COCKPIT_INDEX, _COCKPIT_BASE)


def _signin_index_bytes():
    """Sign-in page for an unsigned GET /. Same auth document, no live3d in the address."""
    return _read_html(SIGNIN_INDEX, _SIGNIN_BASE)


def load_catalog():
    with open(CATALOG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def tcp_probe(host, port, timeout=0.4):
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        return None


def udp_probe_dns(host, port, timeout=0.6):
    tcp = tcp_probe(host, port)
    if tcp is not None:
        return tcp
    try:
        start = time.perf_counter()
        q = (struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
             + b"\x03www\x07example\x03com\x00" + struct.pack(">HH", 1, 1))
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(q, (host, port))
        s.recvfrom(4096)
        s.close()
        return round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        return None


def docker_containers():
    """Running containers, or None when the Docker CLI is unavailable.

    None is distinct from []: empty means Docker answered and nothing is up;
    None means powered must be reported as unknown.
    """
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=4,
        )
        if out.returncode != 0:
            return None
        rows = []
        for line in out.stdout.strip().splitlines():
            parts = line.split("\t")
            while len(parts) < 4:
                parts.append("")
            rows.append({"name": parts[0], "image": parts[1], "status": parts[2], "ports": parts[3]})
        return rows
    except (OSError, subprocess.SubprocessError):
        return None


def _container_needles(sub):
    """Lowercase name/image substrings that mean this catalog row is running."""
    needles = []
    for key in ("service", "composeService", "code"):
        val = (sub.get(key) or "").lower()
        if val and val not in needles:
            needles.append(val)
    return needles


def subsystem_powered(sub, containers):
    """Container running state for one catalog row: on | off | unknown.

    Distinct from TCP/UDP probe `online`. Uses the same name/image needle as
    containerSeen: running → on; exited/missing → off; Docker missing → unknown.
    Matches service, composeService, or code (aliens: navcomputer in
    aliens-navcomputer-1). A row in `docker ps` is on, including one that is
    only restarting. The lamp reads container_phase for that case.
    """
    if containers is None:
        return "unknown"
    blob = " ".join((c["name"] + " " + c["image"]).lower() for c in containers)
    seen = any(n in blob for n in _container_needles(sub))
    return "on" if seen else "off"


def _status_is_starting(status):
    """Restarting or health-starting. A blank or failed status is not a start."""
    text = (status or "").lower()
    return "restarting" in text or "health: starting" in text


def container_phase(sub, containers):
    """starting | running | absent | unknown.

    unknown is Docker missing, not a start. absent is not in `docker ps`.
    starting is restarting or health: starting. Anything else seen is running.
    """
    if containers is None:
        return "unknown"
    needles = _container_needles(sub)
    matched = []
    for c in containers:
        blob = ((c.get("name") or "") + " " + (c.get("image") or "")).lower()
        if any(n in blob for n in needles):
            matched.append(c)
    if not matched:
        return "absent"
    for c in matched:
        if _status_is_starting(c.get("status")):
            return "starting"
    return "running"


_SERVICE_RE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
_PORT_RE = re.compile(r'^\s*-\s*"?(?:[0-9.]+:)?(\d+):(\d+)(?:/[a-z]+)?"?\s*$')


def compose_port_map(path=COMPOSE_PATH):
    """{service: {published_port: container_port}} from fleet-compose.yml."""
    ports = {}
    service = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ports
    for line in lines:
        if line and not line[0].isspace():
            service = None
            continue
        m = _SERVICE_RE.match(line)
        if m:
            service = m.group(1)
            continue
        m = _PORT_RE.match(line)
        if m and service:
            ports.setdefault(service, {})[int(m.group(1))] = int(m.group(2))
    return ports


COMPOSE_PORTS = compose_port_map()


def live_target(sub, port):
    """(host, port) the console dials to reach `port` (a published port) on `sub`."""
    if LIVE_MODE != "compose" or not port:
        return LIVE_HOST, port
    service = compose_service(sub)
    return service, COMPOSE_PORTS.get(service, {}).get(port, port)


def probe_live(catalog):
    containers = docker_containers()
    listed = containers if containers is not None else []
    blob = (" ".join((c["name"] + " " + c["image"]).lower() for c in listed)
            if containers is not None else None)
    systems = []
    any_up = False
    for sub in catalog["subsystems"]:
        port = sub.get("port")
        host, live_port = live_target(sub, port)
        if sub.get("proto") == "dns":
            latency = udp_probe_dns(host, live_port) if port else None
        else:
            latency = tcp_probe(host, live_port) if port else None
        if blob is None:
            seen = False
            powered = "unknown"
        else:
            seen = any(n in blob for n in _container_needles(sub))
            powered = "on" if seen else "off"
        online = latency is not None
        any_up = any_up or online
        avail = release.availability_for(sub, REPO_ROOT)
        systems.append({
            "code": sub["code"],
            "online": online,
            "latency_ms": latency,
            "containerSeen": seen,
            "powered": powered,
            "containerPhase": container_phase(sub, containers),
            "port": port,
            "released": avail == "available",
            "availability": avail,
        })
    return {"available": any_up,
            "host": "compose network" if LIVE_MODE == "compose" else LIVE_HOST,
            "dockerContainers": listed, "systems": systems}


def interact_module(code, action, params, sub, host=None):
    """Dispatch an interact action, or refuse when gated / powered off.

    Checkout availability first (not_yet_available), then powered-off gate.
    unknown/on still reach interactors.dispatch (MTA↔MAIL alias is
    the caller's responsibility via _subsystem).
    """
    if not release.is_released(sub, REPO_ROOT):
        return release.gate_error()
    powered = subsystem_powered(sub, docker_containers())
    if powered == "off":
        return {
            "ok": False,
            "error": "module_powered_off",
            "powered": "off",
            "summary": "module powered off — start it before interacting",
        }
    live_host, port = live_target(sub, sub.get("port"))
    _, admin_port = live_target(sub, sub.get("adminPort"))
    return interactors.dispatch(
        code, action, params,
        host=host if host is not None else live_host,
        port=port, admin_port=admin_port,
    )


# Cockpit speaks MTA; catalog / interactors / compose speak MAIL.
COCKPIT_TO_CATALOG = {"MTA": "MAIL"}


def _subsystem(catalog, code):
    """Exact catalog code, else cockpit alias (MTA finds the MAIL row)."""
    subs = catalog.get("subsystems") or []
    for s in subs:
        if s.get("code") == code:
            return s
    mapped = COCKPIT_TO_CATALOG.get(code)
    if mapped:
        for s in subs:
            if s.get("code") == mapped:
                return s
    return None


def compose_service(sub):
    return sub.get("composeService") or sub["code"].lower()


def compose_file_for(sub):
    """Resolve docker compose file for a catalog row.

    Optional composeFile is relative to REPO_ROOT (e.g. aliens/docker-compose.yml).
    Without it, use the fleet compose under the bridge directory.
    Returns (path, use_day_profiles) or (None, error_dict).
    """
    rel = (sub.get("composeFile") or "").strip()
    if rel:
        path = os.path.normpath(os.path.join(REPO_ROOT, rel))
        repo = os.path.normpath(REPO_ROOT)
        if path != repo and not path.startswith(repo + os.sep):
            return None, {"ok": False, "error": "composeFile escapes repo root"}
        if not os.path.isfile(path):
            return None, {"ok": False, "error": f"{rel} not found"}
        return path, False
    if not os.path.isfile(COMPOSE_PATH):
        return None, {"ok": False, "error": "fleet-compose.yml not found"}
    return COMPOSE_PATH, True


def power_module(sub, op):
    if not rebuild.acquire_fleet_lock():
        return {"ok": False, "error": "conflict"}
    try:
        return _power_module_unlocked(sub, op)
    finally:
        rebuild.release_fleet_lock()


def _power_module_unlocked(sub, op):
    args = POWER_OPS.get(op)
    if args is None:
        return {"ok": False, "error": f"unknown op {op!r}"}
    if not release.is_released(sub, REPO_ROOT):
        return release.gate_error()
    compose_path, profiles_or_err = compose_file_for(sub)
    if compose_path is None:
        return profiles_or_err
    use_profiles = profiles_or_err
    try:
        # Inside the console container COMPOSE_PROJECT_NAME is empty and the
        # working directory is /repo/bridge, so a bare compose stop targets
        # project "bridge" and does not stop the fleet the owner started.
        # The name is added only when that fleet is already running.
        compose_path, project_name, project_directory = rebuild.resolve_named_compose(
            compose_path,
            in_container=rebuild.in_container(),
            runner=_rebuild_runner,
        )
    except (RuntimeError, ValueError, OSError):
        return {"ok": False, "error": "compose project unavailable"}
    service = compose_service(sub)
    profiles = ("day1", "day2", "day3") if use_profiles else ()
    env_file = SECRETS_PATH if os.path.isfile(SECRETS_PATH) else None
    cmd = rebuild.service_argv(
        compose_path, service, args,
        profiles=profiles,
        env_file=env_file,
        project_name=project_name,
        project_directory=project_directory,
    )
    timeout = POWER_TIMEOUTS.get(op, 60)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{op} timed out after {timeout}s"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}
    ok = out.returncode == 0
    tail = (out.stderr or "").strip().splitlines()[-6:]
    return {
        "ok": ok,
        "op": op,
        "service": service,
        "returncode": out.returncode,
        "log": "\n".join(tail),
        "summary": (f"{op} {service}: ok" if ok
                    else f"{op} {service}: failed (rc {out.returncode})"),
    }


def _alien_cleanup_note(result, torn_down):
    """Annotate a managed-run result when its teaching ship could not be torn
    down, so a cleanup failure never reads as an unqualified success."""
    if not torn_down:
        result["cleanup"] = "failed"
        result["warning"] = ("could not tear down the local ship; "
                             "it may still be running")
    return result


def alien_local_test(challenge_path):
    """Local A.L.I.E.N. test: bring the teaching ship up, run the operator's
    exploit against it in the grader runtime (python:3.12-slim + the allowlist,
    on a private internet-less network, as grading does), then spin it down.
    Loopback-only. Holds the fleet lock across the whole op (same lock the
    power/rebuild paths use), and always attempts to remove the ship — even when
    the start times out or the exploit fails — reporting a teardown failure
    rather than leaving one running. The grader's own network and container are
    cleaned up by alien_local.isolated_run()."""
    info = alien_local.resolve(REPO_ROOT, challenge_path)
    if not info:
        return {"ok": False, "error": "unknown_ship"}
    if not os.path.isfile(ALIENS_COMPOSE):
        return {"ok": False, "error": "aliens_compose_missing"}
    if not rebuild.acquire_fleet_lock():
        return {"ok": False, "error": "conflict"}
    env_file = SECRETS_PATH if os.path.isfile(SECRETS_PATH) else None
    cmd = None
    torn_down = {"done": False}
    try:
        try:
            compose_path, project_name, project_directory = rebuild.resolve_named_compose(
                ALIENS_COMPOSE, in_container=rebuild.in_container(), runner=_rebuild_runner)
        except (RuntimeError, ValueError, OSError):
            return {"ok": False, "error": "compose project unavailable"}

        def cmd(args):  # noqa: E306  (small local closure over the resolution)
            return rebuild.service_argv(
                compose_path, info["service"], args, env_file=env_file,
                project_name=project_name, project_directory=project_directory)

        def teardown():
            """Idempotent spin-down. Returns True on a clean removal. Always
            safe to call: `rm -s -f` reconciles a container `up` may have
            created even on a failed or timed-out start."""
            if cmd is None or torn_down["done"]:
                return True
            torn_down["done"] = True
            try:
                rm = subprocess.run(cmd(["rm", "-s", "-f"]),
                                    capture_output=True, text=True, timeout=180)
                return rm.returncode == 0
            except (OSError, subprocess.SubprocessError):
                return False

        # Build the grader runtime (python:3.12-slim + the exploit allowlist)
        # before the ship, so a build failure never leaves a ship running.
        build = alien_local.build_grader_image(REPO_ROOT)
        if not build.get("ok"):
            return build

        # Build on first use; cached builds are quick on later runs.
        try:
            up = subprocess.run(cmd(["up", "-d", "--build"]),
                                capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            # The container may already exist; teardown reconciles it.
            return _alien_cleanup_note({"ok": False, "error": "ship_start_timeout"},
                                       teardown())
        except (OSError, subprocess.SubprocessError) as exc:
            return _alien_cleanup_note({"ok": False, "error": str(exc)}, teardown())
        if up.returncode != 0:
            tail = (up.stderr or "").strip().splitlines()[-6:]
            return _alien_cleanup_note(
                {"ok": False, "error": "ship_start_failed", "log": "\n".join(tail)},
                teardown())
        # The ship publishes its port on the Docker host; a containerized bridge
        # can't reach that on its own loopback, so dial the host gateway. This
        # only gates "is the ship up yet" — the exploit reaches the ship over an
        # internal network below, not through the host.
        live_host = alien_local.reach_host(LIVE_HOST, in_container=rebuild.in_container())
        if not alien_local.wait_reachable(live_host, info["port"], timeout=60):
            return _alien_cleanup_note(
                {"ok": True, "ran": False, "error": "ship_unreachable",
                 "port": info["port"]},
                teardown())
        # Resolve the live ship container so the grader can join it on a
        # private, internet-less network (mirroring how the harness grades).
        try:
            psq = subprocess.run(cmd(["ps", "-q"]),
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            return _alien_cleanup_note({"ok": False, "error": str(exc)}, teardown())
        ship_cid = next((ln.strip() for ln in (psq.stdout or "").splitlines()
                         if ln.strip()), "")
        if not ship_cid:
            return _alien_cleanup_note(
                {"ok": False, "error": "ship_container_not_found"}, teardown())
        res = alien_local.isolated_run(info, ship_cid)
        res["managed"] = True
        return _alien_cleanup_note(res, teardown())
    finally:
        # Safety net for unexpected exceptions; no-op once teardown ran.
        if cmd is not None and not torn_down["done"]:
            try:
                subprocess.run(cmd(["rm", "-s", "-f"]),
                               capture_output=True, text=True, timeout=180)
            except (OSError, subprocess.SubprocessError):
                pass
        rebuild.release_fleet_lock()


SESSION_PATH = os.environ.get(
    "BRIDGE_SESSION_FILE", os.path.join(ROOT, "data", "session.json"))


def load_session():
    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as fh:
            s = json.load(fh)
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def save_session(session):
    os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)
    tmp = SESSION_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(session, fh)
    os.replace(tmp, SESSION_PATH)


def clear_session():
    try:
        os.remove(SESSION_PATH)
    except OSError:
        pass


def current_token():
    return load_session().get("token")


# --------------------------------------------------------------------------
# Earned-flag wallet. Captured A.L.I.E.N. reward flags are persisted locally,
# keyed by username, so a contestant keeps the flags they have boarded even
# across reloads/sessions and when the harness is briefly unreachable. The
# harness remains the source of truth (GET /api/flags unions every completed
# alien grade); this just caches what it returned, additively.
# --------------------------------------------------------------------------
FLAGS_PATH = os.environ.get(
    "BRIDGE_FLAGS_FILE", os.path.join(ROOT, "data", "flags.json"))


def load_wallet():
    try:
        with open(FLAGS_PATH, "r", encoding="utf-8") as fh:
            w = json.load(fh)
        return w if isinstance(w, dict) else {}
    except (OSError, ValueError):
        return {}


def save_wallet(wallet):
    os.makedirs(os.path.dirname(FLAGS_PATH), exist_ok=True)
    tmp = FLAGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(wallet, fh)
    os.replace(tmp, FLAGS_PATH)


def _flag_key(row):
    """Stable per-ship key for a flag row: its alien id, else its path."""
    for k in ("alien", "id", "challenge_path"):
        v = row.get(k)
        if v is not None:
            return str(v)
    return None


def merge_wallet(username, rows):
    """Fold freshly-earned flag rows into the stored wallet for `username` and
    return the merged, ordered list. A row already held is left as first seen
    (keeping its earned_at); a new one is stamped with the current time."""
    wallet = load_wallet()
    held = wallet.get(username)
    if not isinstance(held, dict):
        held = {}
    changed = False
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("flag"):
            continue
        key = _flag_key(row)
        if not key:
            continue
        if key not in held:
            entry = {k: row[k] for k in ("alien", "name", "challenge_path", "flag")
                     if row.get(k) is not None}
            entry["earned_at"] = _utcnow_iso()
            held[key] = entry
            changed = True
    if changed:
        wallet[username] = held
        try:
            save_wallet(wallet)
        except OSError:
            pass
    return _ordered_wallet(held)


def stored_flags(username):
    held = load_wallet().get(username)
    return _ordered_wallet(held if isinstance(held, dict) else {})


def _ordered_wallet(held):
    def sort_key(e):
        try:
            return (0, int(e.get("alien")))
        except (TypeError, ValueError):
            return (1, str(e.get("name") or e.get("challenge_path") or ""))
    return sorted(
        [dict(v) for v in held.values() if isinstance(v, dict)], key=sort_key)


def _utcnow_iso():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def earned_flags():
    """GET /api/flags for the signed-in contestant: live rows from the harness,
    merged into the persisted wallet. If the harness is unreachable, fall back
    to the persisted wallet and mark the result stale."""
    token, err = _require_login()
    if err:
        return err
    sess = load_session()
    username = sess.get("username", "")
    res = harness.earned_flags(token)
    if res.get("ok") and isinstance(res.get("flags"), list):
        flags = merge_wallet(username, res["flags"])
        return {"ok": True, "flags": flags, "stale": False}
    # Harness unreachable or rejected: serve what we have kept locally.
    return {"ok": True, "flags": stored_flags(username), "stale": True,
            "error": res.get("error")}


def harness_config():
    url = os.environ.get("HARNESS_URL", "")
    sess = load_session()
    return {
        "configured": bool(url),
        "url": url,
        "loggedIn": bool(sess.get("token")),
        "username": sess.get("username", ""),
    }


def submission_limits(alien_target='all'):
    token, err = _require_login()
    return err if err else harness.submission_limits(token, alien_target)


def _require_login():
    token = current_token()
    if not token:
        return None, {"ok": False, "error": "not logged in", "loggedIn": False}
    return token, None


def auth_register(payload):
    r = harness.register(payload.get("name", ""), payload.get("username", ""),
                         payload.get("password", ""))
    if r.get("ok") and r.get("token"):
        save_session({"token": r["token"], "username": r.get("username", "")})
        r = {k: v for k, v in r.items() if k != "token"}
        r["loggedIn"] = True
    return r


def auth_login(payload):
    r = harness.login(payload.get("username", ""), payload.get("password", ""))
    if r.get("ok") and r.get("token"):
        save_session({"token": r["token"], "username": r.get("username", "")})
        r = {k: v for k, v in r.items() if k != "token"}
        r["loggedIn"] = True
    return r


def auth_logout():
    token = current_token()
    if token:
        harness.logout(token)
    clear_session()
    return {"ok": True, "loggedIn": False}


_LOCAL_ORIGINS = frozenset({
    "http://127.0.0.1:8777",
    "http://localhost:8777",
    "http://127.0.0.1:8787",
    "http://localhost:8787",
})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ORIGIN_LOOPBACK = re.compile(
    r"^http://(\[[0-9A-Fa-f:.]+\]|[^/:@]+)(?::(\d+))?$")
_PRIVILEGED_POSTS = frozenset({
    "/api/rebuild", "/api/power", "/api/submit", "/api/updates/apply",
    "/api/alien/test",
})
_SUBMIT_BODY_CAP = harness.MAX_ZIP_COMPRESSED + 65536


# Readiness deadline overrides, by module code. JVM services (IPM, LOG) are
# slow to accept connections after a cold recreate; the rest use the default.
_REBUILD_READY_DEADLINES = {"IPM": 120, "LOG": 120}


def _rebuild_state_dir():
    return os.environ.get(
        "BRIDGE_REBUILD_DIR", os.path.join(ROOT, "data", "rebuild"))


def _module_was_running(sub):
    return subsystem_powered(sub, docker_containers())


def _rebuild_runner(argv, timeout):
    return rebuild.run_argv(argv, timeout)


def _rebuild_probe(host, port):
    if not port:
        return False
    return tcp_probe(host, int(port), timeout=2.0) is not None


def _host_is_loopback(host):
    if not isinstance(host, str):
        return False
    host = host.strip()
    if not host or "," in host:
        return False
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return False
        name = host[1:end]
        rest = host[end + 1:]
        if rest and not rest.startswith(":"):
            return False
    elif host.count(":") > 1:
        return False
    else:
        name = host.split(":", 1)[0]
    return name in _LOOPBACK_HOSTS


def _loopback_port(host):
    """Port from a loopback Host header, or None if the host is not loopback."""
    if not _host_is_loopback(host):
        return None
    host = host.strip()
    if host.startswith("["):
        rest = host[host.find("]") + 1:]
        port = rest[1:] if rest.startswith(":") else "80"
    elif ":" in host:
        port = host.split(":", 1)[1]
    else:
        port = "80"
    if not port.isdigit():
        return None
    number = int(port)
    if number < 1 or number > 65535:
        return None
    return str(number)


def _origin_allowed(origin, host):
    """True for a loopback page on the port this request was sent to.

    The historical console ports stay allowed. Any other origin, including a
    different loopback port and every public host, stays rejected.
    """
    if origin in _LOCAL_ORIGINS:
        return True
    if not isinstance(origin, str):
        return False
    match = _ORIGIN_LOOPBACK.fullmatch(origin.strip())
    if not match:
        return False
    name = match.group(1)
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    if name not in _LOOPBACK_HOSTS:
        return False
    if match.group(2):
        number = int(match.group(2))
        if number < 1 or number > 65535:
            return False
        port = str(number)
    else:
        port = "80"
    return port == _loopback_port(host)


def local_only_violation(host, origin, sec_fetch_site):
    """Reject non-loopback Host, a foreign Origin, or Sec-Fetch-Site: cross-site."""
    if not _host_is_loopback(host):
        return "local_only"
    if origin is not None and not _origin_allowed(origin, host):
        return "local_only"
    if isinstance(sec_fetch_site, str) and sec_fetch_site.lower() == "cross-site":
        return "local_only"
    return None


def player_rebuild(payload):
    code, err = rebuild.validate_rebuild_body(payload)
    if err:
        return {"ok": False, "error": err, "status": 400}
    try:
        catalog = load_catalog()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "status": 500}
    sub = _subsystem(catalog, code)
    if not sub:
        return {"ok": False, "error": "rebuild not available", "status": 400}
    try:
        compose_path, project_name, project_directory = rebuild.resolve_compose_target(
            COMPOSE_PATH,
            in_container=rebuild.in_container(),
            runner=_rebuild_runner,
        )
    except Exception:
        return {"ok": False, "error": "rebuild unavailable", "status": 500}
    service = compose_service(sub)
    # Dial the module the same way probe_live does: in compose mode that is the
    # service name on the compose network and the in-container port, not
    # LIVE_HOST and the published port (from inside the bridge container
    # 127.0.0.1 is the bridge itself, so the readiness probe would never
    # succeed and every rebuild would end in a false not_ready).
    probe_host, probe_port = live_target(sub, sub.get("port"))
    spec = {
        "state_dir": _rebuild_state_dir(),
        "code": code,
        "compose_path": compose_path,
        "project_name": project_name,
        "project_directory": project_directory,
        "service": service,
        # Activate every day profile, like fleet-up.sh and the power path, so a
        # cross-profile depends_on (ipm->fmm, ota->fmm/dnsm, mail->dnsm) keeps
        # the compose project model valid while rebuilding one later-day module.
        # build/up still target only `service`.
        "profiles": ("day1", "day2", "day3"),
        "env_file": SECRETS_PATH if os.path.isfile(SECRETS_PATH) else None,
        "port": probe_port,
        "status": lambda sub=sub: _module_was_running(sub),
        "runner": _rebuild_runner,
        "probe": _rebuild_probe,
        "live_host": probe_host,
        "build_timeout": rebuild.BUILD_TIMEOUT,
        "recreate_timeout": rebuild.RECREATE_TIMEOUT,
        # IPM and LOG are JVM services that take 30-60s to accept connections
        # (fleet-up.sh says as much); the default 45s deadline is too tight for
        # a cold start, so give them more room before calling a rebuild
        # not_ready.
        "ready_deadline": _REBUILD_READY_DEADLINES.get(code, rebuild.READY_DEADLINE),
    }
    return rebuild.launch_rebuild(spec)


def _parse_multipart(content_type, body):
    match = re.search(r'boundary=([^;]+)', content_type or "", re.I)
    if not match:
        raise ValueError("boundary")
    boundary = match.group(1).strip().strip('"').encode("utf-8", "replace")
    parts = body.split(b"--" + boundary)
    fields = {}
    file_bytes = None
    for part in parts:
        if part.startswith(b"--"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if not part:
            continue
        header_blob, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        header = header_blob.decode("utf-8", "replace")
        name_match = re.search(r'name="([^"]*)"', header)
        file_match = re.search(r'filename="([^"]*)"', header)
        if not name_match:
            continue
        name = name_match.group(1)
        if name == "file" or file_match:
            file_bytes = data
        else:
            fields[name] = data.decode("utf-8", "replace")
    if file_bytes is None:
        raise ValueError("file")
    return fields, file_bytes


def submit_uploaded(fields, file_bytes):
    token, err = _require_login()
    if err:
        return err
    if "challenge_id" in fields and not harness.full_set_challenge_id(fields.get("challenge_id")):
        return {"ok": False, "error": "invalid_challenge_id"}
    catalog = harness.list_challenges()
    if not catalog.get("ok"):
        return catalog
    entries = list(catalog.get("challenges") or []) + list(catalog.get("aliens") or [])
    try:
        harness.preflight_full_zip(file_bytes, entries)
    except harness.ZipRejected as exc:
        return {"ok": False, "error": exc.reason}
    if (fields.get("kind") or "module") == "alien":
        result = harness.submit_aliens(
            token, file_bytes, alien_target=fields.get("alien_target"))
    else:
        result = harness.submit_modules(token, file_bytes)
    return harness.sanitize_submission_for_cockpit(result)


def submit_challenge(payload=None):
    """Dispatch to the chosen track. The two submissions are never bundled:
    `kind` 'alien' packages only the exploit scripts and hits /api/submit/alien;
    anything else packages only the module source and hits /api/submit."""
    token, err = _require_login()
    if err:
        return err
    payload = payload or {}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "bad JSON body"}
    if "challenge_id" in payload and not harness.full_set_challenge_id(payload.get("challenge_id")):
        return {"ok": False, "error": "invalid_challenge_id"}
    kind = payload.get("kind") or "module"
    catalog = harness.list_challenges()
    if not catalog.get("ok"):
        return catalog
    if kind == "alien":
        pieces = catalog.get("aliens", [])
        noun = "exploit"
    else:
        pieces = catalog.get("challenges", [])
        noun = "module"
    try:
        zip_bytes, manifest = harness.package_challenge(REPO_ROOT, pieces)
    except ValueError:
        return {"ok": False, "error": f"no submittable {noun} source found"}
    except OSError as exc:
        return {"ok": False, "error": f"could not package {noun}s: {exc}"}
    if kind == "alien":
        result = harness.submit_aliens(
            token, zip_bytes, alien_target=payload.get("alien_target"))
    else:
        result = harness.submit_modules(token, zip_bytes)
    result.setdefault("packaged", {
        "fileCount": manifest.get("fileCount"),
        "moduleCount": manifest.get("moduleCount"),
        "modules": manifest.get("modules"),
        "bundleBytes": manifest.get("bundleBytes"),
    })
    # Submit usually returns job_id only; sanitize if a grade blob is embedded.
    return harness.sanitize_submission_for_cockpit(result)


class Handler(BaseHTTPRequestHandler):
    server_version = "BridgeConsole/2.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[bridge] %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self, path, loader):
        if not os.path.isfile(path):
            self._send(404, {"error": "not found"})
            return
        try:
            data = loader()
        except OSError:
            self._send(404, {"error": "not found"})
            return
        self._send(200, data, CONTENT_TYPES[".html"])

    def _serve_cockpit_page(self):
        self._serve_html(COCKPIT_INDEX, _cockpit_index_bytes)

    def _serve_signin_page(self):
        self._serve_html(SIGNIN_INDEX, _signin_index_bytes)

    def _serve_tree(self, root, url_path, allowed):
        norm = _normalize_url_path(url_path)
        if not norm or not allowed(norm):
            self._send(404, {"error": "not found"})
            return
        rel = norm.lstrip("/")
        full = os.path.normpath(os.path.join(root, rel))
        if not _within(root, full):
            self._send(403, {"error": "forbidden"})
            return
        real = os.path.realpath(full)
        raw = unquote(url_path.split("?", 1)[0])
        if os.path.isdir(real):
            if not raw.endswith("/"):
                loc = norm + "/"
                if "?" in self.path:
                    loc += "?" + self.path.split("?", 1)[1]
                self.send_response(302)
                self.send_header("Location", loc)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            real = os.path.realpath(os.path.join(real, "index.html"))
        if not _within(root, real) or not os.path.isfile(real):
            self._send(404, {"error": "not found"})
            return
        rel_real = os.path.relpath(real, os.path.realpath(root))
        probe = "/" + rel_real.replace(os.sep, "/")
        if not allowed(probe):
            self._send(403, {"error": "forbidden"})
            return
        ext = os.path.splitext(real)[1].lower()
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        try:
            with open(real, "rb") as fh:
                data = fh.read()
        except OSError:
            self._send(404, {"error": "not found"})
            return
        self._send(200, data, ctype)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", ""):
            # Bridge login token, not a new session. Decide here so the cockpit
            # is never sent to an unsigned visitor (no flash, no client redirect).
            if current_token():
                self._serve_cockpit_page()
            else:
                self._serve_signin_page()
        elif path == "/api/catalog":
            try:
                self._send(200, load_catalog())
            except Exception as exc:
                self._send(500, {"error": str(exc)})
        elif path == "/api/live":
            try:
                self._send(200, probe_live(load_catalog()))
            except Exception as exc:
                self._send(200, {"available": False, "error": str(exc), "systems": []})
        elif path == "/api/harness":
            self._send(200, harness_config())
        elif path == "/api/auth/status":
            self._send(200, harness_config())
        elif path == "/api/challenges":
            self._send(200, harness.list_challenges())
        elif path == "/api/scoreboard":
            from urllib.parse import parse_qs, urlsplit
            flag = parse_qs(urlsplit(self.path).query).get('all', [''])[0]
            self._send(200, harness.scoreboard(flag == '1'))
        elif path == "/api/score":
            token, err = _require_login()
            self._send(200, err if err else harness.my_score(token))
        elif path == "/api/flags":
            self._send(200, earned_flags())
        elif path == "/api/submission-limits":
            from urllib.parse import parse_qs, urlsplit
            target = parse_qs(urlsplit(self.path).query).get('alien_target', ['all'])[0]
            self._send(200, submission_limits(target))
        elif path == "/api/submissions":
            token, err = _require_login()
            if err:
                self._send(200, err)
            else:
                self._send(200, harness.sanitize_submission_for_cockpit(
                    harness.list_submissions(token)))
        elif path.startswith("/api/submissions/"):
            token, err = _require_login()
            if err:
                self._send(200, err)
            else:
                job_id = path[len("/api/submissions/"):]
                self._send(200, harness.sanitize_submission_for_cockpit(
                    harness.get_submission(token, job_id)))
        elif path == "/api/updates":
            try:
                self._send(200, updater.status(REPO_ROOT))
            except Exception as exc:
                self._send(200, {"ok": False, "enabled": True, "error": str(exc)})
        elif path == "/api/health":
            self._send(200, {"ok": True})
        elif path.startswith("/api/rebuild/"):
            job = rebuild.load_job(_rebuild_state_dir(), path[len("/api/rebuild/"):])
            if not job:
                self._send(404, {"ok": False, "error": "not found"})
            else:
                self._send(200, job)
        elif _blocked_public(path):
            self._send(404, {"error": "not found"})
        elif _wants_sibling(path):
            self._serve_tree(COCKPIT_UI, path, _sibling_allowed)
        else:
            self._serve_tree(COCKPIT_APP, path, _app_allowed)

    def _post_submit_multipart(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(200, {"result": {"ok": False, "error": "bad multipart"}})
            return
        if length < 0 or length > _SUBMIT_BODY_CAP:
            self._send(200, {"result": {"ok": False, "error": "too_large"}})
            return
        raw = self.rfile.read(length) if length else b""
        try:
            fields, file_bytes = _parse_multipart(self.headers.get("Content-Type", ""), raw)
        except ValueError:
            self._send(200, {"result": {"ok": False, "error": "bad multipart"}})
            return
        self._send(200, {"result": submit_uploaded(fields, file_bytes)})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path in _PRIVILEGED_POSTS and local_only_violation(
                self.headers.get("Host"),
                self.headers.get("Origin"),
                self.headers.get("Sec-Fetch-Site")):
            self._send(403, {"ok": False, "error": "local_only"})
            return
        ctype = self.headers.get("Content-Type", "")
        if path == "/api/submit" and "multipart/form-data" in ctype.lower():
            self._post_submit_multipart()
            return
        known = ("/api/interact", "/api/power", "/api/submit",
                 "/api/auth/register", "/api/auth/login", "/api/auth/logout",
                 "/api/updates/apply", "/api/rebuild", "/api/alien/test")
        if path not in known:
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if path == "/api/rebuild" and length > 4096:
                self._send(400, {"ok": False, "error": "invalid rebuild request"})
                return
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._send(400, {"ok": False, "error": "bad JSON body"})
            return
        if path == "/api/auth/register":
            self._send(200, auth_register(payload)); return
        if path == "/api/auth/login":
            self._send(200, auth_login(payload)); return
        if path == "/api/auth/logout":
            self._send(200, auth_logout()); return
        if path == "/api/submit":
            self._send(200, {"result": submit_challenge(payload)})
            return
        if path == "/api/rebuild":
            result = player_rebuild(payload)
            status = result.pop("status", 200)
            self._send(status, result)
            return
        if path == "/api/updates/apply":
            # Conservative local-operator gate (default OFF). Not harness login.
            if not updater.apply_enabled():
                self._send(200, {"result": {
                    "ok": False,
                    "error": "apply_disabled",
                    "message": "Set BRIDGE_UPDATE_APPLY=1 to allow local operator apply",
                }})
                return
            if self.headers.get("X-Bridge-Update-Apply") != "1":
                self._send(200, {"result": {
                    "ok": False,
                    "error": "missing_confirm_header",
                    "message": "Send header X-Bridge-Update-Apply: 1 after UI confirm",
                }})
                return
            self._send(200, {"result": updater.apply(REPO_ROOT)})
            return
        if path == "/api/alien/test":
            cp = (payload.get("challenge_path") or payload.get("ship")
                  or payload.get("path"))
            self._send(200, {"result": alien_local_test(cp)})
            return
        code = payload.get("code")
        try:
            catalog = load_catalog()
        except Exception as exc:
            self._send(500, {"ok": False, "error": str(exc)})
            return
        sub = _subsystem(catalog, code)
        if not sub:
            self._send(404, {"ok": False, "error": f"unknown subsystem {code}"})
            return
        if path == "/api/power":
            result = power_module(sub, payload.get("op"))
            status = 409 if result.get("error") == "conflict" else 200
            self._send(status, {"code": code, "op": payload.get("op"), "result": result})
            return
        action = payload.get("action")
        params = payload.get("params") or {}
        result = interact_module(code, action, params, sub)
        self._send(200, {"code": code, "action": action, "result": result})


def main():
    os.chdir(ROOT)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    banner = (
        "\n"
        "  ============================================================\n"
        "   BRIDGE CONSOLE ONLINE\n"
        "   SAINTCON AppSec Challenge -- spaceship bridge demo UI\n"
        "  ------------------------------------------------------------\n"
        "   URL:        http://%s:%d\n"
        "   Live host:  %s  (real module ports)\n"
        "   Interact:   POST /api/interact  (real protocols, no simulation)\n"
        "   Submit:     POST /api/submit    (harness: %s)\n"
        "  ============================================================\n"
    ) % (HOST, PORT, "compose services" if LIVE_MODE == "compose" else LIVE_HOST, os.environ.get("HARNESS_URL") or "not configured")
    sys.stderr.write(banner)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[bridge] shutting down\n")
        httpd.shutdown()


if __name__ == "__main__":
    main()
