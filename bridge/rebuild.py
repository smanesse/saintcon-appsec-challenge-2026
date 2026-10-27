#!/usr/bin/env python3
"""Allowlisted player rebuild jobs.

The HTTP handler calls launch_rebuild with server-derived paths. A later
isolated proof can call execute_job or resolve_host_compose with a disposable
compose file and a fake or real runner. Those arguments are not HTTP fields.
"""
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid


ALLOWLIST = frozenset({
    "DNSM", "FMM", "IPM", "KVS", "LOG", "MQB", "MTA", "OTA",
})
LOG_TAIL_BYTES = 4096
BUILD_TIMEOUT = 1800
RECREATE_TIMEOUT = 300
READY_DEADLINE = 45
READY_BACKOFF = 0.25
READY_BACKOFF_CAP = 2.0

_PROFILES = {
    "dnsm": "day1",
    "fmm": "day1",
    "kvs": "day1",
    "ipm": "day2",
    "log": "day2",
    "mqb": "day2",
    "ota": "day3",
    "mail": "day3",
}
_LOCK = threading.Lock()
_THREADS = {}
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
_PUBLIC = ("id", "code", "phase", "log", "error", "ok")


def profile_for(service):
    return _PROFILES.get(service)


def acquire_fleet_lock():
    return _LOCK.acquire(blocking=False)


def release_fleet_lock():
    _LOCK.release()


def fleet_lock_held():
    return _LOCK.locked()


def validate_rebuild_body(payload):
    if not isinstance(payload, dict):
        return None, "invalid rebuild request"
    if set(payload.keys()) != {"code"}:
        return None, "unexpected field"
    code = payload.get("code")
    if not isinstance(code, str) or code not in ALLOWLIST:
        return None, "rebuild not available"
    return code, None


def in_container():
    if os.path.isfile("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as fh:
            blob = fh.read()
    except OSError:
        return False
    return "docker" in blob or "containerd" in blob or "kubepods" in blob


def _container_id():
    try:
        with open("/etc/hostname", encoding="utf-8") as fh:
            cid = fh.read().strip()
            if cid:
                return cid
    except OSError:
        pass
    return os.uname().nodename


def _join_mount(compose_path, source, mount_dest):
    """Prefix the mount source with the path under mount_dest.

    This is a prefix split on the mount point, not a global substitution of
    the destination string.
    """
    dest = mount_dest.rstrip("/")
    if compose_path == dest:
        rel = ""
    elif compose_path.startswith(dest + "/"):
        rel = compose_path[len(dest) + 1:]
    else:
        raise RuntimeError("compose path is outside the /repo mount")
    if rel == ".." or rel.startswith("../") or "/../" in rel or rel.startswith("/"):
        raise RuntimeError("compose path escapes the /repo mount")
    if rel == "":
        return source
    return os.path.join(source, rel)


def _inspect_repo_mount(runner, container_id, mount_dest):
    if mount_dest.rstrip("/") != "/repo":
        raise RuntimeError("only the /repo mount is consulted")
    fmt = '{{range .Mounts}}{{if eq .Destination "/repo"}}{{println .Source}}{{end}}{{end}}'
    argv = ["docker", "inspect", "--format", fmt, container_id]
    result = runner(argv, 10)
    if not result.get("ok"):
        raise RuntimeError("docker inspect failed")
    lines = [ln.strip() for ln in (result.get("stdout") or "").splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("/"):
        raise RuntimeError("container has no /repo mount")
    return lines[0]


def resolve_host_compose(compose_path, *, in_container, repo_mount=None, runner=None,
                         container_id=None, mount_dest="/repo"):
    if not in_container:
        return compose_path
    source = repo_mount
    if source is None:
        if runner is None:
            raise RuntimeError("repo mount unavailable")
        source = _inspect_repo_mount(runner, container_id or _container_id(), mount_dest)
    return _join_mount(compose_path, source, mount_dest)


_PROJECT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def _compose_prefix(compose_path, project_name=None, project_directory=None):
    cmd = ["docker", "compose"]
    if project_name:
        if not _PROJECT_NAME.fullmatch(project_name):
            raise ValueError("project name")
        cmd.extend(["--project-name", project_name])
    if project_directory:
        if not isinstance(project_directory, str) or not project_directory.startswith("/"):
            raise ValueError("project directory")
        cmd.extend(["--project-directory", project_directory])
    cmd.extend(["-f", compose_path])
    return cmd


def _profile_list(profile, profiles):
    """Normalize the two profile spellings to an ordered list.

    `profiles` (an iterable) wins when given; otherwise the singular
    `profile` is used. All day profiles must be active so that a
    cross-profile depends_on (e.g. ipm -> fmm) does not leave the compose
    project model invalid while building one later-day service.
    """
    if profiles is not None:
        return [p for p in profiles if p]
    return [profile] if profile else []


def build_argv(compose_path, service, profile=None, env_file=None,
               project_name=None, project_directory=None, profiles=None):
    cmd = _compose_prefix(compose_path, project_name, project_directory)
    if env_file:
        cmd.extend(["--env-file", env_file])
    for prof in _profile_list(profile, profiles):
        cmd.extend(["--profile", prof])
    cmd.extend(["build", service])
    return cmd


def recreate_argv(compose_path, service, profile=None, env_file=None,
                  project_name=None, project_directory=None, profiles=None):
    cmd = _compose_prefix(compose_path, project_name, project_directory)
    if env_file:
        cmd.extend(["--env-file", env_file])
    for prof in _profile_list(profile, profiles):
        cmd.extend(["--profile", prof])
    cmd.extend(["up", "-d", "--force-recreate", "--no-deps", service])
    return cmd


def service_argv(compose_path, service, args, *, profiles=(), env_file=None,
                 project_name=None, project_directory=None):
    """docker compose command for start, stop, or restart of one service.

    Profiles precede the env file, matching the console power command. The
    project name is included only when the caller resolved the live project.
    """
    cmd = _compose_prefix(compose_path, project_name, project_directory)
    for profile in profiles:
        cmd.extend(["--profile", profile])
    if env_file:
        cmd.extend(["--env-file", env_file])
    cmd.extend(args)
    cmd.append(service)
    return cmd


def _compose_projects(runner, basename):
    """Project name and host compose directory for one compose filename.

    A row counts when that file's basename is on the container and the
    container name starts with the project. Only a running project supplies
    a name. Exited leftovers are ignored, so they cannot hide the running
    fleet or become the target. Two running projects is an error. None
    running means the caller should omit the project name.
    """
    fmt = ("{{.Names}}\t{{.Label \"com.docker.compose.project\"}}\t"
           "{{.Label \"com.docker.compose.project.config_files\"}}\t{{.State}}")
    result = runner(["docker", "ps", "-a", "--format", fmt], 10)
    if not result.get("ok"):
        raise RuntimeError("docker ps failed")
    live = {}
    for line in (result.get("stdout") or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, project, config = (part.strip() for part in parts[:3])
        # Older rows omit State. Treat them as running so a single labeled
        # project still resolves.
        state = parts[3].strip().lower() if len(parts) > 3 and parts[3].strip() else "running"
        if not _PROJECT_NAME.fullmatch(project):
            continue
        configs = [item.strip() for item in config.split(",") if item.strip()]
        if not any(os.path.basename(item) == basename for item in configs):
            continue
        if not name.startswith(project + "-"):
            continue
        if state not in ("running", "restarting"):
            continue
        live[project] = os.path.dirname(configs[0])
    if len(live) > 1:
        raise RuntimeError("compose project is not unique")
    if not live:
        return None, None
    return next(iter(live.items()))


def _fleet_project(runner):
    """Project name from a running fleet container, plus its host directory.

    Rebuild still needs a running fleet. Power treats a missing name as the
    ordinary compose command instead.
    """
    project, host_dir = _compose_projects(runner, "fleet-compose.yml")
    if not project:
        raise RuntimeError("compose project is not unique")
    return project, host_dir


def _mounted_directory(host_dir, mounted):
    check = mounted if mounted is not None else os.path.isdir
    return host_dir if host_dir and check(host_dir) else None


def resolve_named_compose(compose_path, *, in_container, runner=None, mounted=None):
    """Compose file the CLI can read, and the live project for that file.

    Outside a container the working directory already names the project, so
    the flag is left unset. Inside, the name is the label on a running
    container created from this compose file. Nothing running means omit the
    name and use the compose file as written. Two running projects is an
    error: guessing would stop the wrong fleet.
    """
    if not in_container:
        return compose_path, None, None
    if runner is None:
        raise RuntimeError("compose project unavailable")
    project, host_dir = _compose_projects(runner, os.path.basename(compose_path))
    if not project:
        return compose_path, None, None
    return compose_path, project, _mounted_directory(host_dir, mounted)


def resolve_compose_target(compose_path, *, in_container, runner=None, mounted=None):
    """Choose the compose file the local CLI can read, and the live project.

    The host path from the /repo mount is not passed as -f. Inside the
    container the file stays at compose_path. The project name is the label
    on a fleet container. The host working directory is included only when
    that exact directory is mounted in this container.
    """
    if not in_container:
        return compose_path, None, None
    if runner is None:
        raise RuntimeError("compose project unavailable")
    project, host_dir = _fleet_project(runner)
    check = mounted if mounted is not None else os.path.isdir
    directory = host_dir if host_dir and check(host_dir) else None
    return compose_path, project, directory


def run_argv(argv, timeout):
    if isinstance(argv, (str, bytes)) or not all(isinstance(part, str) for part in argv):
        raise TypeError("argv must be a sequence of strings")
    proc = subprocess.Popen(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            out, err = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            for pipe in (proc.stdout, proc.stderr):
                if pipe:
                    pipe.close()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            out, err = b"", b""
        timed_out = True
    return {
        "ok": (not timed_out) and proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (out or b"").decode("utf-8", "replace"),
        "stderr": (err or b"").decode("utf-8", "replace"),
        "timed_out": timed_out,
    }


def _tail(stdout, stderr):
    parts = []
    for chunk in (stderr, stdout):
        if chunk:
            parts.append(chunk.strip("\n"))
    text = "\n".join(part for part in parts if part)
    if len(text) > LOG_TAIL_BYTES:
        return text[-LOG_TAIL_BYTES:]
    return text


def _save_job(state_dir, job):
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, job["id"] + ".json")
    blob = {key: job.get(key) for key in _PUBLIC}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(blob, fh)
    os.replace(tmp, path)


def load_job(state_dir, job_id):
    if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
        return None
    root = os.path.abspath(state_dir)
    path = os.path.abspath(os.path.join(root, job_id + ".json"))
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            job = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(job, dict) or job.get("id") != job_id:
        return None
    return {key: job.get(key) for key in _PUBLIC}


def public_job(job):
    return {key: job.get(key) for key in _PUBLIC}


def _fail(state_dir, job, error, log=None):
    job["phase"] = "failed"
    job["ok"] = False
    job["error"] = error
    if log is not None:
        job["log"] = log
    _save_job(state_dir, job)
    return job


def execute_job(spec):
    """Run one rebuild to a terminal phase. spec supplies the runner and paths."""
    job_id = spec.get("job_id") or uuid.uuid4().hex
    spec["job_id"] = job_id
    state_dir = spec["state_dir"]
    job = {
        "id": job_id,
        "code": spec["code"],
        "phase": "queued",
        "log": "",
        "error": None,
        "ok": None,
    }
    state = spec["status"]()
    if state not in ("on", "off"):
        return _fail(state_dir, job, "power_unknown")
    job["phase"] = "building"
    _save_job(state_dir, job)
    build = spec["runner"](
        build_argv(spec["compose_path"], spec["service"],
                   profile=spec.get("profile"), profiles=spec.get("profiles"),
                   env_file=spec.get("env_file"),
                   project_name=spec.get("project_name"),
                   project_directory=spec.get("project_directory")),
        spec.get("build_timeout", BUILD_TIMEOUT),
    )
    job["log"] = _tail(build.get("stdout"), build.get("stderr"))
    if not build.get("ok"):
        error = "timed_out" if build.get("timed_out") else "build_failed"
        return _fail(state_dir, job, error, job["log"])
    if state == "off":
        job["phase"] = "left_stopped"
        job["ok"] = True
        job["error"] = None
        _save_job(state_dir, job)
        return job
    job["phase"] = "recreating"
    _save_job(state_dir, job)
    up = spec["runner"](
        recreate_argv(spec["compose_path"], spec["service"],
                      profile=spec.get("profile"), profiles=spec.get("profiles"),
                      env_file=spec.get("env_file"),
                      project_name=spec.get("project_name"),
                      project_directory=spec.get("project_directory")),
        spec.get("recreate_timeout", RECREATE_TIMEOUT),
    )
    job["log"] = _tail(job["log"], _tail(up.get("stdout"), up.get("stderr")))
    if not up.get("ok"):
        error = "timed_out" if up.get("timed_out") else "recreate_failed"
        return _fail(state_dir, job, error, job["log"])
    if _await_ready(spec, job):
        job["phase"] = "ready"
        job["ok"] = True
        job["error"] = None
    else:
        job["phase"] = "failed"
        job["ok"] = False
        job["error"] = "not_ready"
    _save_job(state_dir, job)
    return job


def _await_ready(spec, job):
    """Probe until the port answers or the readiness deadline passes.

    The phase stays `starting` for the whole wait. Backoff grows and never
    sleeps past the deadline. A probe that raises is an operational error
    for the caller; a false result is simply not ready yet.
    """
    host = spec.get("live_host") or "127.0.0.1"
    port = spec.get("port")
    deadline = float(spec.get("ready_deadline", READY_DEADLINE))
    if deadline < 0:
        deadline = 0.0
    clock = spec.get("clock") or time.monotonic
    sleeper = spec.get("sleeper") or time.sleep
    delay = float(spec.get("ready_backoff", READY_BACKOFF))
    cap = float(spec.get("ready_backoff_cap", READY_BACKOFF_CAP))
    if delay < 0:
        delay = 0.0
    if cap < delay:
        cap = delay
    start = clock()
    job["phase"] = "starting"
    _save_job(spec["state_dir"], job)
    while True:
        if spec["probe"](host, port):
            return True
        remaining = deadline - (clock() - start)
        if remaining <= 0:
            return False
        step = min(delay, remaining)
        if step > 0:
            sleeper(step)
        delay = min(delay * 2, cap)


def _fail_internal(state_dir, job_id, code):
    """Terminal failure with no exception text. Caller still holds the lock."""
    previous = load_job(state_dir, job_id) or {}
    log = previous.get("log") if isinstance(previous.get("log"), str) else ""
    job = {
        "id": job_id,
        "code": code if isinstance(code, str) else "",
        "phase": "failed",
        "log": log,
        "error": "internal",
        "ok": False,
    }
    _save_job(state_dir, job)
    return job


def launch_rebuild(spec):
    """Start an asynchronous job. Holds the fleet lock until the job ends."""
    if not acquire_fleet_lock():
        return {"ok": False, "error": "conflict", "status": 409}
    spec = dict(spec)
    spec["_release_lock"] = True
    if not spec.get("job_id"):
        spec["job_id"] = uuid.uuid4().hex
    try:
        job = {
            "id": spec["job_id"],
            "code": spec["code"],
            "phase": "queued",
            "log": "",
            "error": None,
            "ok": None,
        }
        _save_job(spec["state_dir"], job)

        def work():
            try:
                execute_job(spec)
            except Exception:
                try:
                    _fail_internal(spec["state_dir"], spec["job_id"], spec.get("code"))
                except Exception:
                    pass
            finally:
                if spec.get("_release_lock"):
                    release_fleet_lock()
                _THREADS.pop(spec["job_id"], None)

        thread = threading.Thread(target=work, daemon=True)
        _THREADS[spec["job_id"]] = thread
        thread.start()
    except Exception:
        release_fleet_lock()
        raise
    return {
        "ok": True,
        "status": 200,
        "id": spec["job_id"],
        "code": spec["code"],
        "phase": "queued",
    }


def join_job(job_id, timeout=5):
    thread = _THREADS.get(job_id)
    if thread is None:
        return True
    thread.join(timeout)
    return not thread.is_alive()
