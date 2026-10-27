#!/usr/bin/env python3
"""Build the cockpit UI from source.

Supported tools on the machine that produced the acceptance run:
  Python 3.15.0, stdlib only. This file does not import a third-party package.
  Blender 5.2.0 LTS, build hash fbe6228777e7, built 2026-07-14.
  Default binary: /Applications/Blender.app/Contents/MacOS/Blender
  Override with the BLENDER environment variable.

Machine fonts read by the generators, not files in this package:
  /System/Library/Fonts/Supplemental/Courier New Bold.ttf
  /System/Library/Fonts/Supplemental/Andale Mono.ttf
  /System/Library/Fonts/Menlo.ttc
  /Library/Fonts/Courier New Bold.ttf is checked by some generators and was
  absent on the acceptance host. Custom Courier Prime and Matrix fonts are
  not used and are not shipped.

Invocation, from any working directory:

  python3 build_ui.py

The script finds its own directory and runs every producer there. It is not
an instant build. On this host the same producer order took about 35 minutes.
Each Blender stage is allowed 45 minutes, then the build stops with exit 124.

The child environment sets HOME, TMPDIR, XDG_CACHE_HOME and XDG_CONFIG_HOME
to directories inside this tree and drops SKETCH_OUT. Blender is started
with --background --factory-startup --python-exit-code 7. Exporter modes are
arguments after a double dash: refit, then mast. There is no screenshot,
crop, or sketch stage, and no later default exporter pass.

A tree that already contains cockpit/combined/main_plate.png is refused so
a prebuilt plate cannot be mistaken for a fresh build.
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys

CODES = ["DNSM", "FMM", "IPM", "KVS", "LOG", "MQB", "MTA", "OTA", "PKT"]
BLENDER_DEFAULT = "/Applications/Blender.app/Contents/MacOS/Blender"
SENTINEL = os.path.join("cockpit", "combined", "main_plate.png")
STAGE_TIMEOUT_SECONDS = 45 * 60
TEXT_EXT = {".py", ".js", ".mjs", ".css", ".html", ".json", ".sh", ".md", ".txt"}
COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.S)
HASH_COMMENT = re.compile(r"(?m)^\s*#.*$")
SLASH_COMMENT = re.compile(r"(?m)^\s*//.*$")
ABS_PATH = re.compile(r"(?<![A-Za-z0-9])(/(?:Users|private|opt|Volumes)/[A-Za-z0-9_./+-]+)")
ALLOW_PREFIXES = (
    "/System/Library/Fonts/",
    "/Library/Fonts/",
    "/Applications/Blender.app/",
)


def stages():
    rows = []
    for code in CODES:
        rows.append({
            "id": f"build-{code}",
            "script": f"cockpit/modules/{code}/build.py",
            "args": [],
        })
    rows.append({"id": "combine", "script": "cockpit/combine.py", "args": []})
    rows.append({
        "id": "grading-station",
        "script": "cockpit/grading_station.py",
        "args": [],
    })
    for code in CODES:
        script = f"live3d/pipeline/export_{code.lower()}.py"
        rows.append({"id": f"export-{code}-main", "script": script, "args": []})
        rows.append({"id": f"export-{code}-refit", "script": script, "args": ["refit"]})
        rows.append({"id": f"export-{code}-mast", "script": script, "args": ["mast"]})
    rows.append({
        "id": "leaderboard",
        "script": "live3d/pipeline/leaderboard.py",
        "args": [],
    })
    rows.append({
        "id": "standings-depth",
        "script": "live3d/pipeline/standings_plate.py",
        "args": ["depth"],
    })
    rows.append({
        "id": "standings-render",
        "script": "live3d/pipeline/standings_plate.py",
        "args": ["render"],
    })
    rows.append({
        "id": "measure-transition",
        "script": "live3d/pipeline/measure_transition.py",
        "args": [],
    })
    return rows


def assert_inside(root, path):
    root = os.path.realpath(root)
    target = os.path.realpath(path)
    if os.path.commonpath([root, target]) != root:
        raise SystemExit(f"path escapes candidate: {target}")
    return target


def outside_paths(root):
    found = []
    root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames
            if name not in {".build-home", ".build-tmp", ".build-xdg-cache", ".build-xdg-config", "build-logs"}
        ]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in TEXT_EXT:
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
            except OSError:
                continue
            stripped = SLASH_COMMENT.sub("", HASH_COMMENT.sub("", COMMENT_BLOCK.sub("", text)))
            for match in ABS_PATH.finditer(stripped):
                value = match.group(1)
                if value.startswith(ALLOW_PREFIXES):
                    continue
                found.append(os.path.relpath(path, root) + ": " + value)
    return found


def _isolate(root, base):
    names = {
        "HOME": ".build-home",
        "TMPDIR": ".build-tmp",
        "XDG_CACHE_HOME": ".build-xdg-cache",
        "XDG_CONFIG_HOME": ".build-xdg-config",
    }
    env = dict(base)
    env.pop("SKETCH_OUT", None)
    for key, folder in names.items():
        path = assert_inside(root, os.path.join(root, folder))
        os.makedirs(path, exist_ok=True)
        env[key] = path
    return env


def command(blender, script, args):
    cmd = [
        blender,
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "7",
        "--python",
        script,
    ]
    if args:
        cmd.extend(["--", *args])
    return cmd


def run(root, blender, env=None):
    root = os.path.realpath(root)
    hits = outside_paths(root)
    if hits:
        print("refusing to build; hardcoded path outside the candidate:", file=sys.stderr)
        for hit in hits:
            print(hit, file=sys.stderr)
        return 2
    sentinel = os.path.join(root, SENTINEL)
    if os.path.exists(sentinel):
        print("refusing to build over existing " + SENTINEL, file=sys.stderr)
        return 3
    if not os.path.isfile(blender) or not os.access(blender, os.X_OK):
        print("Blender executable is missing or not executable: " + blender, file=sys.stderr)
        return 127
    child_env = _isolate(root, os.environ if env is None else env)
    log_dir = assert_inside(root, os.path.join(root, "build-logs"))
    os.makedirs(log_dir, exist_ok=True)
    for stage in stages():
        script = assert_inside(root, os.path.join(root, stage["script"]))
        if not os.path.isfile(script):
            raise SystemExit("missing producer " + stage["script"])
        cmd = command(blender, script, stage["args"])
        log_path = os.path.join(log_dir, stage["id"] + ".log")
        print("START " + stage["id"] + " " + _stamp(), flush=True)
        with open(log_path, "w", encoding="utf-8") as log:
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=root,
                    env=child_env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=STAGE_TIMEOUT_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                print("TIMEOUT " + stage["id"], flush=True)
                return 124
        print(
            "EXIT " + stage["id"] + " " + str(completed.returncode) + " " + _stamp(),
            flush=True,
        )
        if completed.returncode != 0:
            print("build stopped at " + stage["id"], file=sys.stderr)
            return completed.returncode
    print("BUILD OK", flush=True)
    return 0


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    blender = os.environ.get("BLENDER", BLENDER_DEFAULT)
    root = os.path.dirname(os.path.abspath(__file__))
    raise SystemExit(run(root, blender))


if __name__ == "__main__":
    main()
