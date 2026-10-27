#!/usr/bin/env python3
import copy
import glob
import io
import json
import os
import re
import stat
import urllib.error
import urllib.request
import urllib.parse
import uuid
import zipfile


# Fallback allowlist, used only if submission-policy.json can't be read. It must
# mirror that file's sourceExtensions (load_policy() REPLACES this set with the
# policy's when present). Note: NO ".sh" - shell runners/entrypoints are fixed
# infrastructure (they materialize per-deployment secrets), so submissions must
# never overlay them; vuln fixes that would otherwise live in a script (e.g.
# OTA's agent-side tar-slip / post_install) are enforced server-side in
# submittable source instead (publish.go).
DEFAULT_SOURCE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh",
    ".java",
    ".go",
    ".scala", ".sc",
    ".py",
    ".js", ".mjs",
    ".html", ".css",
}
DEFAULT_EXCLUDE_DIRS = {
    ".git", "secrets", "vendor", "node_modules", "target", ".gradle",
    "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".venv", "venv", ".idea", ".vscode", "unit_tests", "vuln_tests",
}

POLICY_FILENAME = "submission-policy.json"


def _env(name, default):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def base_url():
    url = _env("HARNESS_URL", None)
    return url.rstrip("/") if url else None


def load_policy(repo_root):
    exts = set(DEFAULT_SOURCE_EXTENSIONS)
    dirs = set(DEFAULT_EXCLUDE_DIRS)
    try:
        with open(os.path.join(repo_root, POLICY_FILENAME), "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return exts, dirs
    if isinstance(doc, dict):
        if isinstance(doc.get("sourceExtensions"), list):
            exts = {str(e).lower() for e in doc["sourceExtensions"] if isinstance(e, str)}
        if isinstance(doc.get("excludeDirs"), list):
            dirs |= {str(d) for d in doc["excludeDirs"] if isinstance(d, str)}
    return exts, dirs


def _iter_module_files(mod_root, patterns):
    seen = set()
    for pattern in patterns:
        for full in sorted(glob.glob(os.path.join(mod_root, pattern), recursive=True)):
            if not os.path.isfile(full) or os.path.islink(full):
                continue
            rel = os.path.relpath(full, mod_root).replace(os.sep, "/")
            if rel not in seen:
                seen.add(rel)
                yield rel, full


def package_challenge(repo_root, challenges):
    repo_root = os.path.abspath(repo_root)
    raw = io.BytesIO()
    total = 0
    modules = []
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in sorted(challenges, key=lambda x: x.get("challenge_path", "")):
            module_dir = c.get("challenge_path")
            patterns = c.get("allowed_files") or []
            if not module_dir:
                continue
            mod_root = os.path.join(repo_root, module_dir)
            if not os.path.isdir(mod_root):
                continue
            count = 0
            for rel, full in _iter_module_files(mod_root, patterns):
                arc = f"{module_dir}/{rel}"
                zi = zipfile.ZipInfo(arc)
                zi.compress_type = zipfile.ZIP_DEFLATED
                with open(full, "rb") as fh:
                    zf.writestr(zi, fh.read())
                count += 1
            total += count
            modules.append({"module": module_dir, "fileCount": count})

    if total == 0:
        raise ValueError("no submittable source found for any module")

    bundle = raw.getvalue()
    manifest = {"fileCount": total, "moduleCount": len(modules),
                "modules": modules, "bundleBytes": len(bundle)}
    return bundle, manifest


def _timeout():
    return float(_env("HARNESS_TIMEOUT", "30"))


def _request(method, path, data=None, ctype=None, token=None):
    base = base_url()
    if not base:
        raise RuntimeError("HARNESS_URL not configured")
    req = urllib.request.Request(base + path, data=data, method=method)
    if ctype:
        req.add_header("Content-Type", ctype)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", _env("HARNESS_USER_AGENT", "saintcon-bridge/1.0"))
    try:
        with urllib.request.urlopen(req, timeout=_timeout()) as r:
            return r.status, _decode(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _decode(e.read())


def _decode(body):
    try:
        return json.loads(body or b"{}")
    except (ValueError, TypeError):
        return None


def _json_post(path, payload, token=None):
    return _request("POST", path, json.dumps(payload).encode(), "application/json", token)


def _multipart_zip(fields, filename, zip_bytes):
    boundary = "----bridge" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f'name="{name}"\r\n\r\n{value}\r\n').encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; "
             f'name="file"; filename="{filename}"\r\n'
             f"Content-Type: application/zip\r\n\r\n").encode()
    body += zip_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return f"multipart/form-data; boundary={boundary}", body


def _wrap(status, doc):
    if doc is None:
        return {"ok": False, "error": f"harness returned non-JSON (HTTP {status})"}
    if status >= 400 and "ok" not in doc:
        doc = dict(doc)
        doc["ok"] = False
        if "error" not in doc and "message" not in doc:
            doc["error"] = f"HTTP {status}: " + str(
                doc.get("title") or doc.get("detail") or "request rejected")
    doc.setdefault("ok", status < 400)
    doc["httpStatus"] = status
    return doc


def _guard(fn):
    try:
        return _wrap(*fn())
    except RuntimeError as exc:
        return {"ok": False, "configured": False, "error": str(exc)}
    except (urllib.error.URLError, OSError) as exc:
        return {"ok": False, "error": f"harness unreachable at {base_url()}: {exc}"}


def register(name, username, password):
    return _guard(lambda: _json_post("/api/register",
                  {"name": name, "username": username, "password": password}))


def login(username, password):
    return _guard(lambda: _json_post("/api/login",
                  {"username": username, "password": password}))


def logout(token):
    return _guard(lambda: _json_post("/api/logout", {}, token=token))


def list_challenges():
    return _guard(lambda: _request("GET", "/api/challenges"))


def scoreboard(all_rows=False):
    """Public board. Without all=1 the harness keeps the top 10."""
    path = "/api/scoreboard?all=1" if all_rows else "/api/scoreboard"
    return _guard(lambda: _request("GET", path))


def my_score(token):
    """Signed-in score, solved vuln count, and solved ship count."""
    return _guard(lambda: _request("GET", "/api/score", token=token))


def earned_flags(token):
    """The caller's earned A.L.I.E.N. reward flags.

    Proxies the harness `GET /api/flags`, which returns one row per boarded ship
    that has a static reward flag configured:
    `{ok, flags:[{alien, name, challenge_path, flag}]}`. These are the stable
    tokens a contestant keeps for boarding a ship; the random flag the grader
    uses to verify a solve is never surfaced.
    """
    return _guard(lambda: _request("GET", "/api/flags", token=token))


def submission_limits(token, alien_target='all'):
    query = urllib.parse.urlencode({'alien_target': alien_target})
    return _guard(lambda: _request('GET', '/api/submission-limits?' + query, token=token))


MAX_ZIP_COMPRESSED = 4000000
MAX_ZIP_ENTRIES = 500
MAX_ZIP_EXPANDED = 20 * 1024 * 1024
_FULL_CHALLENGE_IDS = frozenset({None, "", "full", "all", "202600", 202600})


class ZipRejected(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def full_set_challenge_id(value):
    if isinstance(value, str):
        value = value.strip()
    return value in _FULL_CHALLENGE_IDS


def _glob_re(pattern):
    """Glob where * does not cross '/'. ** matches whole segments, including none."""
    index = 0
    parts = ["^"]
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:[^/]+/)*")
            index += 3
            continue
        if pattern.startswith("**", index):
            parts.append(".*")
            index += 2
            continue
        char = pattern[index]
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    parts.append("$")
    return re.compile("".join(parts))


def _glob_match(rel, pattern):
    return _glob_re(pattern).fullmatch(rel) is not None


def _zip_name_reason(name):
    if not isinstance(name, str) or name == "":
        return "not_allowlisted"
    if name.startswith("/") or name.startswith("\\"):
        return "absolute_path"
    if len(name) >= 2 and name[1] == ":":
        return "absolute_path"
    if "\\" in name:
        return "backslash"
    raw = name[:-1] if name.endswith("/") else name
    if raw.startswith("."):
        return "dot_name"
    parts = raw.split("/")
    for part in parts:
        if part == "..":
            return "traversal"
        if part.startswith("."):
            return "dot_component"
        if part == "":
            return "not_allowlisted"
    return None


def _patterns_for(entry):
    patterns = entry.get("allowed_files")
    if patterns:
        return [pat for pat in patterns if isinstance(pat, str)]
    base = (entry.get("challenge_path") or "").strip().strip("/")
    if base == "aliens" or base.startswith("aliens/"):
        return ["exploit.py"]
    return []


def _entry_allowed(name, catalog_entries):
    for entry in catalog_entries:
        base = (entry.get("challenge_path") or "").strip().strip("/")
        if not base or ".." in base.split("/"):
            continue
        prefix = base + "/"
        if not name.startswith(prefix):
            continue
        rel = name[len(prefix):]
        for pattern in _patterns_for(entry):
            if _glob_match(rel, pattern):
                return True
    return False


def preflight_full_zip(data, catalog_entries):
    """Reject a user ZIP in memory. Does not extract and does not write the repo.

    catalog_entries are challenge and alien rows (challenge_path + allowed_files).
    One disallowed entry rejects the archive.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise ZipRejected("not_a_zip")
    if len(data) > MAX_ZIP_COMPRESSED:
        raise ZipRejected("too_large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(bytes(data)))
    except zipfile.BadZipFile:
        raise ZipRejected("not_a_zip")
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise ZipRejected("too_many_entries")
        if sum(info.file_size for info in infos) > MAX_ZIP_EXPANDED:
            raise ZipRejected("expanded_too_large")
        seen = set()
        for info in infos:
            name = info.orig_filename if isinstance(getattr(info, "orig_filename", None), str) else info.filename
            if "\x00" in name:
                raise ZipRejected("nul_name")
            reason = _zip_name_reason(name)
            if reason:
                raise ZipRejected(reason)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ZipRejected("symlink")
            if info.flag_bits & 0x1:
                raise ZipRejected("encrypted")
            if name in seen:
                raise ZipRejected("duplicate")
            seen.add(name)
            if name.endswith("/"):
                continue
            if not _entry_allowed(name, catalog_entries):
                raise ZipRejected("not_allowlisted")


def submit_modules(token, zip_bytes):
    """Module track: every module's source, graded functional + security."""
    fields = {"challenge_id": "full"}
    ctype, body = _multipart_zip(fields, "modules.zip", zip_bytes)
    return _guard(lambda: _request("POST", "/api/submit", body, ctype, token))


def submit_aliens(token, zip_bytes, alien_target=None):
    """A.L.I.E.N. track: just the exploit scripts, graded against the ships."""
    fields = {}
    if alien_target not in (None, "", "all"):
        fields["alien_target"] = str(alien_target)
    ctype, body = _multipart_zip(fields, "aliens.zip", zip_bytes)
    return _guard(lambda: _request("POST", "/api/submit/alien", body, ctype, token))


def get_submission(token, job_id):
    return _guard(lambda: _request("GET", f"/api/submissions/{job_id}", token=token))


def list_submissions(token):
    return _guard(lambda: _request("GET", "/api/submissions", token=token))


# --------------------------------------------------------------------------
# Cockpit sanitizer. The grade screen lists solved vuln numbers only.
# A forwarded vuln is {n, fixed, error, skipped} for fixed===true — never a
# missed number, name, slug, title, PoC output, or module total.
# security_solved remains the fixed-only index other surfaces already read.
# --------------------------------------------------------------------------
_COUNT_KEYS = frozenset({
    "total", "fixed", "errored", "skipped", "done", "landing",
    "vulns_total", "vulns_fixed", "remaining", "vulns", "metrics",
    "of", "confirmed", "pending_untested", "inconclusive",
})

# Fail-closed allowlist for fields that may leave the bridge toward the browser.
_SUBMISSION_KEEP = frozenset({
    "job_id", "id", "challenge_id", "status", "status_name", "pending",
    "pending_seconds", "duration_seconds", "age_seconds", "passed",
    "result_summary", "security_status", "alien_status", "alien_target",
    "aliens", "created", "updated", "progress", "security_solved", "security", "kind",
    "ok", "error", "message", "httpStatus", "configured", "loggedIn",
    "packaged",
})


def _poc_index(n):
    """Return a positive int PoC index, or None if not a safe index."""
    if isinstance(n, bool):
        return None
    if isinstance(n, int):
        return n if 1 <= n <= 64 else None
    if isinstance(n, str) and n.strip().isdigit():
        v = int(n.strip())
        return v if 1 <= v <= 64 else None
    return None


def _solved_entries(security):
    out = []
    if not isinstance(security, list):
        return out
    for m in security:
        if not isinstance(m, dict):
            continue
        module = m.get("module")
        if module is None:
            continue
        module = str(module)
        for v in (m.get("vulns") or []):
            if not isinstance(v, dict):
                continue
            if v.get("fixed") is not True:
                continue
            n = _poc_index(v.get("n"))
            if n is None:
                continue
            out.append({"module": module, "n": n})
    return out


def _security_rows(security):
    """Forward solved scorer vulns only. No missed number, name, or count."""
    out = []
    if not isinstance(security, list):
        return out
    for m in security:
        if not isinstance(m, dict):
            continue
        module = m.get("module")
        if module is None:
            continue
        vulns = []
        seen = set()
        for v in (m.get("vulns") or []):
            if not isinstance(v, dict) or v.get("fixed") is not True:
                continue
            n = _poc_index(v.get("n"))
            if n is None or n in seen:
                continue
            seen.add(n)
            vulns.append({
                "n": n,
                "fixed": True,
                "error": v.get("error") is True,
                "skipped": v.get("skipped") is True,
            })
        out.append({"module": str(module), "vulns": vulns})
    return out


def _normalize_security_solved(raw):
    """Keep only {module:str, n:int}; drop ratio strings and extras."""
    if not isinstance(raw, list):
        return []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        n = _poc_index(row.get("n"))
        mod = row.get("module")
        if n is None or mod is None:
            continue
        out.append({"module": str(mod), "n": n})
    return out


def _scrub_progress(progress):
    if not isinstance(progress, dict):
        return progress
    out = {}
    if "phase" in progress:
        out["phase"] = progress["phase"]
    phases = progress.get("phases")
    if isinstance(phases, dict):
        clean = {}
        for name, phase in phases.items():
            if not isinstance(phase, dict):
                clean[name] = {}
                continue
            items = phase.get("items")
            kept_items = []
            if isinstance(items, list):
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    row = {}
                    if "name" in it:
                        row["name"] = it["name"]
                    if "state" in it:
                        row["state"] = it["state"]
                    if row:
                        kept_items.append(row)
            clean[name] = {"items": kept_items} if kept_items else {}
        out["phases"] = clean
    return out


def _scrub_aliens(aliens):
    if not isinstance(aliens, list):
        return aliens
    kept = []
    for a in aliens:
        if not isinstance(a, dict) or a.get("solved") is not True:
            continue
        row = {}
        # `alien` is the harness's ship key (its challenge_path); id/challenge_path
        # appear on richer rows. `flag` is the EARNED static reward token the
        # harness now attaches to a boarded ship (settings.ALIEN_FLAGS) — keep it
        # so the cockpit can show the contestant the flag they captured. The
        # random grading flag is never present in this payload.
        for k in ("id", "alien", "name", "challenge_path", "path", "flag"):
            if k in a and a[k] is not None:
                row[k] = a[k]
        if row:
            kept.append(row)
    return kept


def _strip_count_keys(obj):
    """Recursively drop forbidden count/total keys from dict trees."""
    if isinstance(obj, list):
        return [_strip_count_keys(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if k in _COUNT_KEYS:
            continue
        out[k] = _strip_count_keys(v)
    return out


def _sanitize_one_submission(sub):
    """Sanitize a single submission dict (returns a new allowlisted dict).

    Emit ``security_solved`` when the source has a security list or a
    ``security_solved`` key, even if that list is empty. Omit the key only
    when neither is present, so a missing report is not the same as an
    explicit empty solved list.
    """
    if not isinstance(sub, dict):
        return sub
    security = sub.get("security")
    has_security = isinstance(security, list)
    has_solved_key = "security_solved" in sub
    solved = []
    if has_security:
        solved = _solved_entries(security)
    elif has_solved_key:
        solved = _normalize_security_solved(sub.get("security_solved"))

    out = {}
    for k in _SUBMISSION_KEEP:
        if k not in sub:
            continue
        if k in ("security", "security_summary", "alien_summary"):
            continue
        if k == "security_solved":
            continue
        if k == "progress":
            out[k] = _scrub_progress(sub.get("progress"))
        elif k == "aliens":
            out[k] = _scrub_aliens(sub.get("aliens"))
        else:
            out[k] = copy.deepcopy(sub[k])
    if has_security or has_solved_key:
        out["security_solved"] = solved
    # Drop any nested count keys that slipped in via allowlisted values.
    # Attach vuln rows after that strip: their `fixed` flag is not a count.
    cleaned = _strip_count_keys(out)
    if has_security:
        cleaned["security"] = _security_rows(security)
    return cleaned


def sanitize_submission_for_cockpit(obj):
    """Walk harness submission payload(s) and redact vuln totals / ratios.

    Fail-closed for submission objects: only an allowlisted field set leaves
    toward the browser. Emits `security: [{module, vulns: [{n, fixed, error,
    skipped}]}]` when the scorer sent a security list, and
    `security_solved: [{module, n}, ...]` for fixed indexes. Missed numbers
    are omitted. Strips names,
    summaries, module counts, nested metrics, and unsolved aliens. Preserves
    passed / result_summary / status for FILE RETURN.
    """
    if obj is None or not isinstance(obj, (dict, list)):
        return obj
    doc = copy.deepcopy(obj)
    if isinstance(doc, list):
        return [_sanitize_one_submission(s) if isinstance(s, dict) else s
                for s in doc]
    if isinstance(doc.get("submissions"), list):
        doc["submissions"] = [
            _sanitize_one_submission(s) if isinstance(s, dict) else s
            for s in doc["submissions"]
        ]
    if isinstance(doc.get("submission"), dict):
        doc["submission"] = _sanitize_one_submission(doc["submission"])
    # Bare submission object (or submit response that embeds grade fields).
    if any(k in doc for k in ("security", "security_summary", "security_status",
                              "aliens", "alien_summary", "progress",
                              "security_solved", "result_summary", "status_name")):
        # Fail-closed: drop unknown top-level keys; keep only a small envelope
        # allowlist plus the rebuilt submission fields.
        cleaned = _sanitize_one_submission(doc)
        envelope_keep = frozenset({
            "ok", "error", "message", "httpStatus", "configured", "loggedIn",
            "packaged", "result", "now", "submissions", "submission", "limits",
            "available", "url", "username", "ms", "reachable",
        })
        for k in list(doc.keys()):
            if k not in envelope_keep:
                doc.pop(k, None)
        doc.update(cleaned)
    return doc
