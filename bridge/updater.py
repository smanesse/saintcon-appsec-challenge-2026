#!/usr/bin/env python3
import os
import subprocess


def _env(name, default):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def remote():
    return _env("BRIDGE_UPDATE_REMOTE", "origin")


def branch():
    return _env("BRIDGE_UPDATE_BRANCH", "main")


def enabled():
    return _truthy(_env("BRIDGE_AUTOUPDATE", "1"))


def auto_apply():
    return _truthy(_env("BRIDGE_UPDATE_AUTOAPPLY", "1"))


def apply_enabled():
    """Explicit local-operator opt-in for POST /api/updates/apply.
    Default OFF — distinct from BRIDGE_AUTOUPDATE (status/fetch) and from
    BRIDGE_UPDATE_AUTOAPPLY (mock console convenience). Contestation
    harness login is NOT this gate."""
    return _truthy(_env("BRIDGE_UPDATE_APPLY", "0"))


def _timeout():
    try:
        return float(_env("BRIDGE_UPDATE_TIMEOUT", "45"))
    except ValueError:
        return 45.0


def _git(repo, *args, timeout=None):
    return _git_raw(repo, *args, timeout=timeout)


def _identity_args(repo):
    try:
        rc, out, _ = _git_raw(repo, "config", "user.email", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    if rc == 0 and out.strip():
        return []
    name = _env("BRIDGE_UPDATE_AUTHOR_NAME", "Bridge Console")
    email = _env("BRIDGE_UPDATE_AUTHOR_EMAIL", "bridge@localhost")
    return ["-c", "user.name=" + name, "-c", "user.email=" + email]


def _git_raw(repo, *args, timeout=None):
    cmd = ["git", "-c", "safe.directory=" + os.path.abspath(repo),
           "-C", repo] + list(args)
    out = subprocess.run(cmd, capture_output=True, text=True,
                         timeout=timeout or _timeout())
    return out.returncode, (out.stdout or "").strip(), (out.stderr or "").strip()


def _git_id(repo, *args, timeout=None):
    return _git_raw(repo, *(_identity_args(repo) + list(args)), timeout=timeout)


def is_repo(repo):
    try:
        rc, _, _ = _git(repo, "rev-parse", "--git-dir", timeout=5)
        return rc == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _upstream_ref():
    return "{}/{}".format(remote(), branch())


def _current_branch(repo):
    rc, out, _ = _git(repo, "rev-parse", "--abbrev-ref", "HEAD", timeout=5)
    return out if rc == 0 else ""


def _is_dirty(repo):
    rc, out, _ = _git(repo, "status", "--porcelain", timeout=10)
    return rc == 0 and bool(out.strip())


def _short(repo, ref):
    rc, out, _ = _git(repo, "rev-parse", "--short", ref, timeout=5)
    return out if rc == 0 else ""


def _commit_is_additive(repo, sha):
    rc, out, _ = _git(repo, "show", "--no-renames", "--format=", "--name-status",
                      sha, timeout=15)
    if rc != 0:
        return False, []
    files = []
    additive = True
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        code = parts[0]
        path = parts[-1]
        files.append(path)
        if code != "A":
            additive = False
    return additive, files


def pending_commits(repo):
    ref = _upstream_ref()
    rc, out, err = _git(repo, "rev-list", "--reverse", "HEAD..{}".format(ref),
                        timeout=15)
    if rc != 0:
        return None, err or "could not list commits"
    commits = []
    for sha in out.splitlines():
        sha = sha.strip()
        if not sha:
            continue
        _rc, subject, _ = _git(repo, "show", "-s", "--format=%s", sha, timeout=10)
        additive, files = _commit_is_additive(repo, sha)
        commits.append({
            "sha": sha[:10],
            "subject": subject,
            "additive": additive,
            "fileCount": len(files),
        })
    return commits, None


def fetch(repo):
    try:
        rc, _, err = _git(repo, "fetch", "--quiet", remote(), branch())
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "fetch timed out"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}
    if rc != 0:
        return {"ok": False, "error": err or "fetch failed"}
    return {"ok": True}


def status(repo, do_fetch=True):
    if not enabled():
        return {"ok": True, "enabled": False, "applyEnabled": apply_enabled()}
    if not is_repo(repo):
        return {"ok": True, "enabled": True, "isRepo": False,
                "applyEnabled": apply_enabled(),
                "error": "not a git checkout"}
    base = {"ok": True, "enabled": True, "isRepo": True,
            "autoApply": auto_apply(), "applyEnabled": apply_enabled(),
            "branch": _current_branch(repo),
            "remote": remote(), "upstreamBranch": branch(),
            "current": _short(repo, "HEAD"), "dirty": _is_dirty(repo)}
    if do_fetch:
        f = fetch(repo)
        if not f["ok"]:
            base["fetchError"] = f["error"]
    commits, err = pending_commits(repo)
    if err is not None:
        base["error"] = err
        base["updateAvailable"] = False
        return base
    base["commits"] = commits
    base["behind"] = len(commits)
    base["updateAvailable"] = len(commits) > 0
    base["allAdditive"] = all(c["additive"] for c in commits)
    return base


def _can_fast_forward(repo):
    if _current_branch(repo) != branch():
        return False
    rc, _, _ = _git(repo, "merge-base", "--is-ancestor", "HEAD", _upstream_ref(),
                    timeout=10)
    return rc == 0


def apply(repo):
    if not enabled():
        return {"ok": False, "error": "updates are disabled"}
    if not is_repo(repo):
        return {"ok": False, "error": "not a git checkout"}
    f = fetch(repo)
    if not f["ok"]:
        return {"ok": False, "error": "fetch failed: " + f["error"]}
    commits, err = pending_commits(repo)
    if err is not None:
        return {"ok": False, "error": err}
    if not commits:
        return {"ok": True, "applied": 0, "upToDate": True,
                "current": _short(repo, "HEAD")}
    if not all(c["additive"] for c in commits):
        return {"ok": False, "error": "non_additive",
                "message": "An upstream change is not purely additive; "
                           "apply it manually after reviewing it.",
                "commits": commits}

    before = _short(repo, "HEAD")
    dirty = _is_dirty(repo)
    stashed = False
    try:
        if dirty:
            rc, _, serr = _git_id(repo, "stash", "push", "--include-untracked",
                                  "-m", "bridge-autoupdate")
            if rc != 0:
                return {"ok": False, "error": "could not stash local changes: "
                        + (serr or "unknown")}
            stashed = True

        if _can_fast_forward(repo):
            rc, _, merr = _git(repo, "merge", "--ff-only", _upstream_ref())
            if rc != 0:
                return _finish_error(repo, stashed,
                                     "fast-forward failed: " + (merr or "unknown"))
            method = "fast-forward"
        else:
            method = "cherry-pick"
            for c in commits:
                rc, _, cerr = _git_id(repo, "cherry-pick", c["sha"])
                if rc != 0:
                    _git(repo, "cherry-pick", "--abort", timeout=15)
                    return _finish_error(
                        repo, stashed,
                        "cherry-pick of {} failed: {}".format(c["sha"], cerr or "conflict"))
    except (OSError, subprocess.SubprocessError) as exc:
        return _finish_error(repo, stashed, str(exc))

    result = {"ok": True, "applied": len(commits), "method": method,
              "from": before, "to": _short(repo, "HEAD"), "commits": commits}
    if stashed:
        rc, _, perr = _git(repo, "stash", "pop")
        if rc != 0:
            result["stashWarning"] = ("Local changes are preserved in "
                                      "`git stash`; resolve and `git stash pop`.")
    return result


def _finish_error(repo, stashed, message):
    if stashed:
        _git(repo, "stash", "pop", timeout=30)
    return {"ok": False, "error": message}
