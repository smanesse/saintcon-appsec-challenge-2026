"""Run a player's alien exploit.py against the LOCAL teaching ship.

The harness grades exploits in the cloud against fresh, randomly-flagged ships;
this is the local "test" counterpart for the weapons console. The server
orchestrates the ship's lifecycle (compose up -> wait -> down); this module
parses ``aliens/docker-compose.yml`` for the ship's service/port/flag and runs
``aliens/<ship>/exploit.py`` against it, grepping stdout for the flag.

Ships are independent: each has its own flag and no boarding pass, so a ship can
be tested on its own.

Loopback-only (the HTTP route sits in ``server._PRIVILEGED_POSTS``): it executes
the operator's OWN repo script on the operator's OWN machine.

**Runtime parity with grading.** The exploit does not run as the bridge's own
Python; it runs the way the harness grades it (see ``aliens/GRADING.md``): inside
a ``python:3.12-slim`` container carrying the fixed third-party allowlist
(``aliens/grader/requirements.txt``), on a ``--internal`` Docker network that can
reach the ship but not the internet, with the same ``TARGET_*`` env and ~15s
timeout. So a local pass predicts a remote pass, and an exploit that quietly
phones home fails locally too. The script is fed on stdin (``python -I -``) and
the image is built from a context-free Dockerfile, so neither needs a host-path
mount — the one path that must survive a containerized bridge talking to the
Docker host. A local test only lines up when the ships were built with the
default campaign flags (grading rebuilds each ship with a fresh random flag).
"""
import os
import re
import secrets
import shlex
import socket
import subprocess
import sys
import time

FLAG_RE = re.compile(r"SAINTCON\{[^}\n]{0,200}\}")
_SVC_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
_CTX_RE = re.compile(r"context:\s*\./(\S+)")
_PORT_RE = re.compile(r'^\s*-\s*"(\d+):(\d+)"')
_FLAG_ARG_RE = re.compile(r'FLAG:\s*"\$\{[^:}]*:-([^"]*)\}"')

MAX_OUTPUT = 4000
DEFAULT_TIMEOUT = 15.0

# The exploit runtime, matching grading: python:3.12-slim + the allowlist from
# aliens/grader/requirements.txt. Built on demand (cached) by build_grader_image.
GRADER_IMAGE = "alien-grader:local"
DEFAULT_CONTAINER_PORT = 8080  # every teaching ship listens here inside its container


def _compose_path(repo_root):
    return os.path.join(repo_root, "aliens", "docker-compose.yml")


def parse_fleet(repo_root):
    """Ordered local ships from aliens/docker-compose.yml.

    Returns ``[{service, dir, port, cport, flag}]`` by published port. Parsed
    block-by-block (stdlib only, no PyYAML): the service name is the 2-space
    key, with its build.context (``./NN-name``), published host port (``port``)
    and container port (``cport``), and FLAG build-arg default
    (``${FLAGn:-DEFAULT}``) — each ship's own flag. Ordered by port, which
    matches the ship number.
    """
    try:
        with open(_compose_path(repo_root), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    ships, cur = [], None
    for line in text.splitlines():
        sh = _SVC_RE.match(line)
        if sh:
            if cur:
                ships.append(cur)
            cur = {"service": sh.group(1), "dir": None, "port": None,
                   "cport": None, "flag": ""}
            continue
        if cur is None:
            continue
        ctx = _CTX_RE.search(line)
        if ctx and cur["dir"] is None:
            cur["dir"] = ctx.group(1).strip("/")
        pm = _PORT_RE.match(line)
        if pm and cur["port"] is None:
            cur["port"] = int(pm.group(1))
            cur["cport"] = int(pm.group(2))
        fm = _FLAG_ARG_RE.search(line)
        if fm:
            cur["flag"] = fm.group(1)
    if cur:
        ships.append(cur)
    ships = [s for s in ships if s.get("port") and s.get("dir")]
    ships.sort(key=lambda s: s["port"])
    return ships


def resolve(repo_root, challenge_path):
    """Map a catalog ``aliens/<dir>`` path to a local ship + exploit + flag.

    Ships are independent: each carries its own flag and no boarding pass.
    """
    cp = (challenge_path or "").strip().strip("/")
    parts = cp.split("/")
    if len(parts) != 2 or parts[0] != "aliens" or ".." in parts:
        return None
    wantdir = parts[1]
    ships = parse_fleet(repo_root)
    for s in ships:
        if s["dir"] != wantdir:
            continue
        exploit = os.path.abspath(os.path.join(repo_root, "aliens", wantdir, "exploit.py"))
        if not os.path.isfile(exploit):
            return None
        return {
            "service": s["service"],
            "dir": wantdir,
            "port": s["port"],
            "cport": s["cport"] or DEFAULT_CONTAINER_PORT,
            "expect_flag": s["flag"],
            "exploit": exploit,
        }
    return None


def _host_gateway():
    """Default-route gateway IP from ``/proc/net/route``, or None.

    When the bridge runs as a container this is the Docker host — the box the
    teaching ships publish their ports on. Stdlib only, little-endian hex.
    """
    try:
        with open("/proc/net/route", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    for line in lines[1:]:
        f = line.split()
        if len(f) > 2 and f[1] == "00000000":  # default route
            try:
                g = int(f[2], 16)
            except ValueError:
                continue
            return "%d.%d.%d.%d" % (g & 0xff, (g >> 8) & 0xff,
                                    (g >> 16) & 0xff, (g >> 24) & 0xff)
    return None


def reach_host(live_host, in_container=False):
    """Host to dial a ship's HOST-PUBLISHED port for the readiness probe.

    The teaching ships (``aliens/docker-compose.yml``) bind ``0.0.0.0:<port>``
    on the Docker host. When the bridge itself runs as a container, its own
    loopback is not that host, so a loopback ``live_host`` reaches nothing —
    dial the default-route gateway (the host) instead. A non-loopback
    ``live_host`` (an explicit override) is always honoured as given. (The
    exploit itself reaches the ship by container alias on the internal network,
    not through this host; this only gates "is the ship up yet".)
    """
    host = live_host or "127.0.0.1"
    if in_container and host in ("127.0.0.1", "localhost", "::1"):
        gw = _host_gateway()
        if gw:
            return gw
    return host


def _reachable(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def wait_reachable(host, port, timeout=60.0, interval=0.75):
    """Block until the ship answers on its port, or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _reachable(host, port, timeout=1.0):
            return True
        time.sleep(interval)
    return _reachable(host, port, timeout=1.0)


def _clip(s):
    s = s or ""
    return s if len(s) <= MAX_OUTPUT else s[:MAX_OUTPUT] + "\n...[truncated]"


def _text(s):
    """Normalize a subprocess stream to str. With ``text=True`` a stream is
    usually str, but ``TimeoutExpired`` may carry bytes — normalize each one
    independently so a bytes/str mix never raises on concatenation."""
    if s is None:
        return ""
    if isinstance(s, (bytes, bytearray)):
        return bytes(s).decode("utf-8", "replace")
    return s


def _captured_flag(out, expect_flag):
    """The SELECTED ship's captured flag in ``out``, or None.

    A local run counts as solved only when the ship's OWN expected flag turns
    up — not merely any ``SAINTCON{...}`` token. When the ship was built with a
    non-default flag the expected value is unknown, so fall back to the first
    flag-shaped token in the output.
    """
    if expect_flag and expect_flag in out:
        return expect_flag
    if expect_flag:
        return None
    m = FLAG_RE.search(out)
    return m.group(0) if m else None


# ---------------------------------------------------------------------------
# Grader runtime: build the image, wire an internal network, run the exploit.
# These shell out to `docker`; the pure argv/Dockerfile builders are factored
# out so they can be exercised without a daemon.
# ---------------------------------------------------------------------------

def grader_requirements(repo_root):
    """Third-party allowlist from aliens/grader/requirements.txt (comments and
    blank lines stripped). Shared with the grading harness and GRADING.md."""
    path = os.path.join(repo_root, "aliens", "grader", "requirements.txt")
    reqs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            spec = line.split("#", 1)[0].strip()
            if spec:
                reqs.append(spec)
    return reqs


def grader_dockerfile(reqs):
    """Context-free Dockerfile installing the allowlist onto python:3.12-slim.

    No COPY/ADD, so it builds from stdin with an empty context (``docker build
    -``) — no host-path translation when a containerized bridge drives the
    host Docker daemon."""
    pkgs = " ".join(shlex.quote(r) for r in reqs)
    return ("FROM python:3.12-slim\n"
            "RUN pip install --no-cache-dir " + pkgs + "\n")


def build_grader_image(repo_root, runner=subprocess.run, timeout=1800):
    """Build/refresh the ``alien-grader:local`` image. Cheap once layer-cached.

    Needs internet (to pull the base image and pip-install) — fine locally; the
    grading network builds its image out of band, never from the exploit."""
    try:
        reqs = grader_requirements(repo_root)
    except OSError as exc:
        return {"ok": False, "error": "grader_requirements_missing: %s" % exc}
    if not reqs:
        return {"ok": False, "error": "grader_requirements_empty"}
    dockerfile = grader_dockerfile(reqs)
    try:
        proc = runner(["docker", "build", "-t", GRADER_IMAGE, "-"],
                      input=dockerfile, capture_output=True, text=True,
                      timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "grader_build_timeout"}
    except OSError as exc:
        return {"ok": False, "error": "grader_build_failed: %s" % exc}
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-6:]
        return {"ok": False, "error": "grader_build_failed", "log": "\n".join(tail)}
    return {"ok": True}


def grader_run_argv(network, grader_name, target_host, target_port,
                    image=GRADER_IMAGE):
    """``docker run`` argv for one exploit: the allowlist image on an internal
    network, the ``TARGET_*`` env grading sets, reading the script from stdin.

    ``--name`` is explicit so a timed-out run can be force-removed (``--rm``
    only reaps a container that exits on its own)."""
    url = "http://%s:%d" % (target_host, target_port)
    return [
        "docker", "run", "--rm", "-i",
        "--name", grader_name,
        "--network", network,
        "--memory", "512m", "--pids-limit", "512",
        "-e", "TARGET_URL=" + url,
        "-e", "TARGET_HOST=" + target_host,
        "-e", "TARGET_PORT=" + str(target_port),
        image, "python", "-I", "-",
    ]


def _run(runner, argv, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("timeout", 30)
    return runner(argv, **kw)


def network_create(name, runner=subprocess.run):
    """Create an isolated, internet-less network for one exploit run."""
    try:
        proc = _run(runner, ["docker", "network", "create", "--internal", name])
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def network_connect(name, container, alias, runner=subprocess.run):
    try:
        proc = _run(runner, ["docker", "network", "connect",
                             "--alias", alias, name, container])
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def network_disconnect(name, container, runner=subprocess.run):
    try:
        _run(runner, ["docker", "network", "disconnect", "-f", name, container])
    except (OSError, subprocess.SubprocessError):
        pass


def network_remove(name, runner=subprocess.run):
    try:
        _run(runner, ["docker", "network", "rm", name])
    except (OSError, subprocess.SubprocessError):
        pass


def container_remove(name, runner=subprocess.run):
    try:
        _run(runner, ["docker", "rm", "-f", name])
    except (OSError, subprocess.SubprocessError):
        pass


def run_exploit(info, *, network, target_host="target", grader_name=None,
                timeout=DEFAULT_TIMEOUT, runner=subprocess.run):
    """Run the resolved ship's exploit.py in the grader container on ``network``.

    The ship must already be reachable on that network under ``target_host``
    (the caller wires it). Grades by grepping the output for the ship's flag.
    """
    try:
        with open(info["exploit"], "r", encoding="utf-8") as fh:
            src = fh.read()
    except OSError as exc:
        return {"ok": False, "error": "exploit_unreadable: %s" % exc}
    name = grader_name or ("alien-grader-" + secrets.token_hex(6))
    port = int(info.get("cport") or DEFAULT_CONTAINER_PORT)
    argv = grader_run_argv(network, name, target_host, port)
    try:
        proc = runner(argv, input=src, capture_output=True, text=True,
                      timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = _text(exc.stdout) + _text(exc.stderr)
        return {"ok": True, "ran": True, "solved": False, "timed_out": True,
                "grader": name, "output": _clip(out)}
    except OSError as exc:
        return {"ok": False, "error": "run_failed: %s" % exc, "grader": name}
    out = _text(proc.stdout)
    err = _text(proc.stderr)
    if err:
        out += ("\n" if out else "") + err
    flag = _captured_flag(out, info.get("expect_flag", ""))
    return {
        "ok": True, "ran": True, "solved": bool(flag),
        "flag": flag, "grader": name,
        "returncode": proc.returncode, "output": _clip(out),
    }


def isolated_run(info, ship_container, *, timeout=DEFAULT_TIMEOUT,
                 runner=subprocess.run):
    """Wire a one-shot internal network around an already-running ship, run the
    exploit against it under alias ``target``, then tear the network (and any
    timed-out grader) down. The ship itself is the caller's to manage."""
    net = "alien-net-" + secrets.token_hex(6)
    grader = "alien-grader-" + secrets.token_hex(6)
    if not network_create(net, runner=runner):
        return {"ok": False, "error": "network_create_failed"}
    try:
        if not network_connect(net, ship_container, "target", runner=runner):
            return {"ok": False, "error": "network_connect_failed"}
        return run_exploit(info, network=net, target_host="target",
                           grader_name=grader, timeout=timeout, runner=runner)
    finally:
        # --rm reaps a clean exit; a timed-out grader lingers and keeps a
        # network endpoint, so force-remove it before (and the ship after) the
        # network, or `network rm` would refuse while endpoints remain.
        container_remove(grader, runner=runner)
        network_disconnect(net, ship_container, runner=runner)
        network_remove(net, runner=runner)


def _ship_container(info, runner=subprocess.run):
    """Container id of a teaching ship by its published host port, or None.

    Used by the scripted run_test path; the server knows the compose project
    and resolves the id through ``docker compose ps`` instead.
    """
    try:
        proc = _run(runner, ["docker", "ps", "--filter",
                             "publish=%d" % info["port"], "--format", "{{.ID}}"])
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    ids = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return ids[0] if ids else None


def run_test(repo_root, challenge_path, live_host="127.0.0.1",
             timeout=DEFAULT_TIMEOUT, in_container=False):
    """Run against an ALREADY-RUNNING local ship (no compose lifecycle here).

    Kept for direct/scripted use and tests; the server's managed path brings
    the ship up and down around isolated_run() instead. Builds the grader image,
    finds the ship container, and runs the exploit in it on an internal network.
    """
    info = resolve(repo_root, challenge_path)
    if not info:
        return {"ok": False, "error": "unknown_ship"}
    probe = reach_host(live_host, in_container=in_container)
    if not _reachable(probe, info["port"]):
        return {"ok": True, "ran": False, "error": "ship_not_running",
                "port": info["port"]}
    build = build_grader_image(repo_root)
    if not build.get("ok"):
        return build
    cid = _ship_container(info)
    if not cid:
        return {"ok": False, "error": "ship_container_not_found"}
    return isolated_run(info, cid, timeout=timeout)
