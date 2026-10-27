"""Load a cockpit module's REAL build.py into the transliterate pipeline.

    import transliterate as T
    from module_loader import load_module, check_snapshots
    check_snapshots()                     # shell/slots snapshots vs cockpit/
    mod = load_module("FMM")              # cockpit/modules/FMM/build.py, live
    R = mod.add_props(P, mats)

WHY THIS EXISTS.  `transliterate.py` reads `three-exploration/src/*_snapshot.py`
and never the live project, on purpose -- an export must not change because
someone edited the cockpit.  The cost of that is a COPY per module, and the
project has already been bitten once by a copy going stale
(`shell_snapshot.py` was two changes behind: `detail_amt` 0.045 vs 0.081 live,
and no `raytrace` key, so every export before it was refreshed was rendered
against the wrong material amplitude).  Nine more copies is nine more chances.

So: the SHELL and SLOTS snapshots stay (they are the pipeline's own contract,
and they are verified byte-identical here before anything is generated), and
the MODULE is imported from `cockpit/modules/<CODE>/build.py` in place.  There
is no module snapshot to keep in sync, and no way for one to rot.

The trick that makes this safe is three lines: a module's build.py does
`import shell` / `import slots`, so `sys.modules` is pre-bound to the snapshot
objects transliterate already loaded.  ONE shell exists in the process, one set
of materials, one PARAMS.  Without this you get two `shell` modules, two
`bpy.data.materials["brass"]`, and a plate that does not match its own glbs.

NEVER CALL THE MODULE'S main().  It writes `demo.html` and `out/` under
cockpit/, which is read-only to live3d work.  The occlusion audit did this by
accident and had to prove the damage was nil afterwards
(live3d/audit/OCCLUSION_AUDIT.md, "One accidental write outside my area").
`add_props()` is the entry point; it builds geometry and returns the control
dict, and it renders nothing.
"""
import os, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)
ROOT = os.path.dirname(LIVE3D)
COCKPIT = os.path.join(ROOT, "cockpit")
EXPL = os.path.join(ROOT, "three-exploration")

CODES = ["DNSM", "FMM", "IPM", "KVS", "LOG", "MQB", "MTA", "OTA", "PKT"]


def check_snapshots():
    """shell/slots snapshots must be byte-identical to the live cockpit files.
    Returns a list of complaints; empty means clean.  RUN THIS BEFORE EVERY
    EXPORT -- a stale snapshot produces a plausible-looking wrong plate and the
    batch still reports rc=0."""
    bad = []
    for snap, live in (("shell_snapshot.py", "shell.py"),
                       ("slots_snapshot.py", "slots.py")):
        a = os.path.join(EXPL, "src", snap)
        b = os.path.join(COCKPIT, live)
        if not os.path.exists(a):
            bad.append("%s missing" % snap)
            continue
        if open(a, "rb").read() != open(b, "rb").read():
            bad.append("%s DIFFERS from cockpit/%s -- refresh it before "
                       "exporting (see BRIEF.md; it is the one file outside "
                       "live3d/ you are allowed to touch)" % (snap, live))
    return bad


def load_module(code):
    """Import cockpit/modules/<CODE>/build.py under the pipeline's own shell.

    Requires that `shell_snapshot` and `slots_snapshot` are already imported
    (transliterate does this at import time)."""
    if code not in CODES:
        raise ValueError("unknown module %r; expected one of %s" % (code, CODES))
    if "shell_snapshot" not in sys.modules or "slots_snapshot" not in sys.modules:
        raise RuntimeError("import transliterate first: the module's build.py "
                           "does `import shell` and must get the pipeline's "
                           "shell, not a second copy")
    # bind the names the module will ask for to the objects already loaded
    sys.modules["shell"] = sys.modules["shell_snapshot"]
    sys.modules["slots"] = sys.modules["slots_snapshot"]
    path = os.path.join(COCKPIT, "modules", code, "build.py")
    name = "cockpit_module_" + code
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)          # runs top level only; main() is guarded
    return mod
