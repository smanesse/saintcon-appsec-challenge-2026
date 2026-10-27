"""
LIVE-3D EXPORT — IPM close-up  ("Optical Sensor Array / Photo Lab").

A thin layer on top of three-exploration/pipeline/transliterate.py, following
live3d/CONVERSION_BRIEF.md.  The module's REAL build.py is imported in place by
live3d/pipeline/module_loader.py, so there is no IPM snapshot to go stale.

IPM is the fleet's MARGINAL module: the audit found that its only content-ish
text is the chute tag, that the scope dial's face is unusable (bezel 40/121,
pointer bar 13/121) and that **no readout home had been decided**.  Deciding it
is the whole of the design work here; NOTES.md section 3 is the argument and
the measurements.  In one line: IPM's panel is 156 mm wide and every flat area
big enough to hold a line of type is a BRASS RAIL of one of the two aperture
frames, so that is where the three readouts go --

    source    the resolver frame's TOP rail    (what is being resolved)
    output    the resolver frame's BOTTOM rail, left of the stamped RESOLVER
    develop   the tray frame's TOP rail        (what the darkroom is doing)

and two of the three are genuinely occluded, by the module's own geometry, at
the pose the harness scores:

    develop   the SAFELIGHT ring + dome, BAKED, 18/121 samples, 3.0-10.6 mm
    output    ipm_plg_knob, the capture plunger's own knob, LIVE, at the
              ARMED rest position -- and it clears the strip when the plunger
              is pressed.  This is the fleet's first module to exercise
              check_occlusion.py's LIVE half with its OWN geometry at rest
              (PKT needed a second scene.json, MQB/MTA/OTA a control rig).

    plate.png       shell + IPM STATIC parts.  R["static"] exists on IPM and
                    partitions cleanly (survey: static n control-owned = 0).
                    It contains no CONTENT type -- ipm_tag_txt ("TO FMM HOLD")
                    is a permanent destination stencil, not a value, so per
                    BRIEF section 7 rule 1 it stays geometry and stays baked.
                    Asserted, not assumed.

    dial.glb        the SCOPE selector knob: hub + bar + red index    -- rotates
    capture.glb     the capture plunger (rod, knob, band) + EXPOSE lamp
    tray.glb        the developing plate: 15 merged tile meshes, 8 frames

    All three controls become LIVE.  `tray` ships as `kind: frames` and here it
    really IS N discrete meshes (MQB's scope / MTA's capsule case, not PKT's):
    each frame is a DIFFERENT quad soup, because a tile moves between three
    silver densities as it develops, so there is no continuous parameter to
    drive.  All 15 meshes go in one glb and visibility is toggled per frame.
    `capture` is `kind: states` and declares mats off/on for the EXPOSE lamp,
    so rule 3 is satisfied and the lamp is a material swap on real geometry.

    NOT EXPORTED AT ALL: nothing.  IPM authors NO content type -- every FONT
    object in the module is a stamped label (IPM, OPTICAL ARRAY, 256/512/1K/
    SVG/ZIP, SCOPE, RESOLVER, CAPTURE, EXPOSE, DEVELOPING, TO FMM HOLD).  So
    this exporter is in PKT's position for all THREE of its readouts: it
    CREATES the type in Blender, with the module's own text() helper, its own
    font and its own ink material, at the declared planes, in the strings
    pose() paints -- AFTER plate.png, depth.bin and every glb are written, so
    it appears in none of them (asserted).  That is what gives verify_assets.py
    and check_text.py something to score on all three planes.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_ipm.py
"""
import bpy, math, os, sys, json, collections, tempfile
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)
ROOT = os.path.dirname(LIVE3D)
EXPL = os.path.join(ROOT, "three-exploration")
sys.path.insert(0, os.path.join(EXPL, "pipeline"))
sys.path.insert(0, os.path.join(EXPL, "src"))
sys.path.insert(0, HERE)

import transliterate as T                                        # noqa: E402
import typemetrics as TM                                         # noqa: E402
from module_loader import load_module, check_snapshots           # noqa: E402

shell = T.shell
CODE = "IPM"
OUT = os.path.join(LIVE3D, "assets", CODE)

# ------------------------------------------------------------- LIGHT GAIN
# NOT the fleet constant 0.65 (BRIEF 5.2a: 0.65 is nobody's optimum, it is a
# 0.1-grid artefact).  MEASURED with check/sweep_knob.mjs on the real page and
# fitted through the minimum -- NOTES.md section 5.3 has the two sweeps.
#
#   0.40   0.45   0.50   0.55   0.60   0.61   0.65   0.70   0.75   0.85
#   3.686  3.241  2.928  2.748  2.688  2.687  2.727  2.846  3.017  3.452
#
# fitted vertex 0.605, and a 0.01 grid around it reads 0.60/0.61/0.62 =
# 2.688/2.687/2.691.  SHIPPED 0.61.
#
# THE BRIEF'S PREDICTION FOR IPM IS WRONG, AND IT IS WRONG THE INTERESTING WAY.
# BRIEF 5.2a says the optimum is monotone in the module's own light share --
# "below ~10% the optimum is 0.51, above ~12% it is 0.61" -- and predicts 0.51
# for IPM, whose 7.1% is the LOWEST share in the fleet.  Measured, IPM sits at
# 0.61 with OTA (8.0% -> 0.52) and MTA (8.8% -> 0.51) below it and KVS/MQB/PKT
# (12-26% -> 0.61-0.62) beside it.  Light share does not predict this module.
# NOTES.md section 5.3 has what does.
LIGHT_GAIN = 0.61

# --------------------------------------------------------------- THE POSE
# The one resting state the whole verification chain is scored in: it must be
# identical here, in gt_full_read.png and in module.js's poseForCapture().
#
# A console mid-job, deliberately, so all three readouts carry a real value and
# the live set is on screen: the SCOPE dial at the 512 detent, the capture
# plunger back at ARMED (its own declared rest, CAPTURE_ORDER[0]) with the
# EXPOSE lamp out, and the developing tray six frames into an eight-frame
# develop.  ARMED is not a convenience: it is where the plunger rests, and it
# is what puts ipm_plg_knob across the bottom of the `output` strip.
POSE_DIAL = 1               # index into mod.SCOPES -> "512", i.e. -62.5 deg
POSE_CAPTURE = "armed"      # mod.CAPTURE_ORDER[0]
POSE_TRAY = 6               # of mod.DEV_FRAMES = 8

# ------------------------------------------------ THE THREE READOUT PLANES
# All lengths are root-local metres; IPM's root carries no scale (asserted
# below), so a local metre IS a world metre and there is no K()/S() to apply.
#
# `z` is the stand-off along the panel normal.  Every carrier front face is
# MEASURED off build.py's own constants rather than guessed:
#
#   the two aperture frames' rails are boxes of z-size 0.010 centred on
#   PZ + 0.004 = 0.028, so their front face is at z = 0.0330 exactly
#   (`aperture()`: zc = PZ + 0.004, size (..., ..., 0.010)).
#
# The planes sit at 0.0338, i.e. 0.8 mm proud.  The shader's epsilon is
# RELATIVE (s > 1.0001), which at IPM's 2.00 m close camera is 0.20 mm, so
# every plane clears it by 4x.  It is also 0.35 mm more than the extrude of
# the module's own text() helper, so the DOM sits where a stamped line would.
PZ_RAIL = 0.0330
PLANE_Z = 0.0338

#        name       cx        cy       hw      hh      size    cols align
PLAN = [
    ("source",    0.0000, -0.0385, 0.0755, 0.0060, 0.0165, 29, "center"),
    ("output",   -0.0490, -0.0965, 0.0285, 0.0098, 0.0150, 12, "center"),
    ("develop",   0.0000, -0.2030, 0.0755, 0.0055, 0.0150, 32, "left"),
]

# The strings the capture pose paints.  They are ALSO what gt_platen0.png is
# rendered from, so check_text.py scores the DOM against Blender's own raster
# of the same words in the same place.
TEXT = {
    "source":  ["NGC7293.PNG  1024x1024"],
    "output":  ["OUT 41.2 KB"],
    "develop": ["DEVELOPING PLATE 86%"],
}

# Which module material each readout's ink is.  All three planes lie on BRASS
# rails, and the module's own convention is ipm_ink for type on brass
# (ipm_name_a/b on the nameplate, ipm_res_cap, ipm_tray_cap) and ipm_ivory for
# type on the dark panel (SCOPE, CAPTURE, EXPOSE, the dial detents).  So all
# three are ink -- but the colour is still MEASURED per plane off Blender's own
# render, because the four close lights do not light the panel evenly.
INK_MAT = {"source": "ipm_ink", "output": "ipm_ink", "develop": "ipm_ink"}


def dirn(m3, v):
    """Transform a DIRECTION by a rotation matrix and normalise."""
    return (m3 @ Vector(v)).normalized()


def median_ink(path):
    """The ink colour Blender actually rendered, as an (r,g,b) byte triple.

    MEDIAN over alpha > 0.5, with NO colour transform (BRIEF section 7 rule 7).
    bpy hands `image.pixels` back ALREADY display-encoded for an 8-bit sRGB
    PNG, so an sRGB encode on top returns a plausible-looking wrong colour, and
    on small type nothing is fully opaque so a "most common fully opaque pixel"
    rule returns the empty set.  Cross-checked against the PNG bytes by
    check/verify_assets.py, which reads the same file with the stdlib decoder.
    """
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    nch = img.channels
    buf = np.empty(w * h * nch, dtype=np.float32)
    img.pixels.foreach_get(buf)
    a = buf.reshape(-1, nch)
    bpy.data.images.remove(img)
    thr = 0.5
    sel = a[a[:, 3] > thr] if nch == 4 else a
    while nch == 4 and not len(sel) and thr > 0.02:
        thr /= 2.0
        sel = a[a[:, 3] > thr]
    if not len(sel):
        return None, 0
    med = np.median(np.clip(sel[:, :3], 0, 1), axis=0) * 255.0
    return [int(round(float(c))) for c in med], int(len(sel))


def main():
    os.makedirs(OUT, exist_ok=True)
    bad = check_snapshots()
    assert not bad, "snapshot check failed: %s" % bad

    P = dict(shell.PARAMS)
    P["exterior"] = 0
    print("raytrace =", P.get("raytrace"))
    assert P.get("raytrace") == 1, "shell_snapshot.py is stale: no raytrace"

    scene = shell.build(P)
    scene.render.film_transparent = True
    W, H = scene.render.resolution_x, scene.render.resolution_y
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    mod = load_module(CODE)
    R = mod.add_props(P, mats)
    mine, ctrl, root = R["all"], R["controls"], R["root"]
    static = list(R["static"])
    shell_meshes = [o for o in T.renderables(scene) if o not in set(mine)]

    rs = root.matrix_world.to_scale()
    assert max(abs(rs.x - 1), abs(rs.y - 1), abs(rs.z - 1)) < 1e-9, \
        "root is scaled: every local length in PLAN would need multiplying"

    # ---------------------------------------------------- the close-up rig
    # IPM HAS a close_rig(root) and takes nothing else; build.py's main() calls
    # it with the module at its own rest state and changes nothing first, so
    # there is no pre-call block to copy (contrast OTA, which raises the
    # cartridge for the fit).  Called here exactly as main() calls it, so the
    # close-up frames the column identically to the shipped baked close plate
    # and the transition's match dissolve still lands.
    cam, close_lights = mod.close_rig(root)
    close_tags = {L.name: "close" for L in close_lights}
    scene.camera = cam
    bpy.context.view_layer.update()

    # ------------------------------------------- the live / baked split
    knob = list(ctrl["dial"]["objs"])              # hub + bar + index
    plunger = list(ctrl["capture"]["plunger"])     # rod + knob + band
    lamp = ctrl["capture"]["lamp"]
    slider = ctrl["capture"]["slider"]
    dev_sets = ctrl["tray"]["frame_objs"]
    dev = [o for s in dev_sets for o in s]
    live = knob + plunger + [lamp] + dev
    plate = shell_meshes + static

    # BRIEF: "R['static'] existing is not the same as R['static'] being safe."
    # MTA's clean `static` held three content-text FONT objects and OTA's held
    # its SHA-256.  IPM's holds NINE label meshes and every one of them is a
    # STAMPED label -- the test is "does a player read it for a VALUE" and the
    # answer is no for all of them, including ipm_tag_txt ("TO FMM HOLD"),
    # which is a destination stencil on a brass tag and never changes.  Listed
    # here so the decision is visible rather than implied.
    STAMPED = ["ipm_name_a", "ipm_name_b", "ipm_dial_lab_0", "ipm_dial_lab_1",
               "ipm_dial_lab_2", "ipm_dial_lab_3", "ipm_dial_lab_4",
               "ipm_dial_cap", "ipm_res_cap", "ipm_plg_cap", "ipm_lamp_cap",
               "ipm_tray_cap", "ipm_tag_txt"]
    in_static = [o.name for o in static if o.name in STAMPED]
    assert sorted(in_static) == sorted(STAMPED), \
        "the stamped-label list does not match R['static']: %s" % in_static
    assert not (set(live) & set(plate)), "a live object is also in the plate"
    assert set(live) | set(static) == set(o for o in mine if o.type != 'EMPTY'), \
        "the live/static split is not a partition of the module's geometry"
    print("split: %d plate objects (%d shell + %d static), %d live "
          "(%d dial knob, %d plunger, 1 lamp, %d tray tile meshes), "
          "0 content type (IPM authors none -- all %d labels are stamped)"
          % (len(plate), len(shell_meshes), len(static), len(live),
             len(knob), len(plunger), len(dev), len(STAMPED)))

    # ----- the plate and the depth pass, both LIVE-FREE, at the module's own
    # rest state.  Nothing static moves, so neither is pose-dependent.
    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"), hide=live)

    # ------------------------------------------------------------ geometry
    # exported at the module's REST state, so every runtime transform is a
    # delta from a known zero.  export_glb() clears hide_render, which matters
    # here: build.py leaves 14 of the 15 tray meshes hide_render=True.
    T.export_glb(knob, os.path.join(OUT, "dial.glb"))
    T.export_glb(plunger + [lamp], os.path.join(OUT, "capture.glb"))
    T.export_glb(dev, os.path.join(OUT, "tray.glb"))

    # ------------------------------------------------------------ anchors
    rm3 = root.matrix_world.to_3x3()
    u = dirn(rm3, (1, 0, 0))                   # face RIGHT (slot local +X)
    v = dirn(rm3, (0, 1, 0))                   # face UP    (slot local +Y)
    n = dirn(rm3, (0, 0, 1))                   # face NORMAL, out at the pilot
    cfwd = dirn(cam.matrix_world.to_3x3(), (0, 0, -1))
    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-cfwd).dot(n)))))
    assert (-cfwd).dot(n) > 0, "n must point AT the camera"
    print("OBLIQ panel face normal vs close-cam view axis %.4f deg" % obliq)

    # No module declares `axis` on a rotate control (BRIEF step 1).  IPM has no
    # face helper -- slots.pillar() aims local +Z at the pilot and the working
    # face IS the slot plane -- so there is no rake to sweep a cone about and
    # the axis is the root's own local +Z.  Emitted NEGATED, MQB's convention,
    # so a POSITIVE angle is CLOCKWISE on screen: that is the direction
    # build.py's own detents run (tick i is at (sin th, cos th), i.e. the "up"
    # vector turned by -th about +Z) and the direction its demo's CSS
    # `rotate(deg)` turns.  Sign-checked by gt_dial_p062.png below.
    spin_axis = [-c for c in T.to3(n)]
    dial_anchor = root.matrix_world @ Vector(ctrl["dial"]["anchor"])
    dial_px, dial_py = mod.project(scene, cam, dial_anchor)

    # --------------------------------------------------- the readout planes
    planes = []
    for (nm, cx, cy, hw, hh, size, ncols, align) in PLAN:
        adv = TM.measure_type(mod, size)["adv"]
        # a single-line readout has no line PITCH; the value only sets the CSS
        # line-height, and layoutType() measures the browser's baseline inside
        # a box of exactly that height, so placement is independent of it.
        lead = min(size, 1.6 * hh)
        tb = TM.type_block(mod, size, lead_m=lead,
                           left_m=(-ncols * adv / 2 if align == "left" else -hw),
                           top_m=0.0, n_lines=1, scale=1.0, align=align)
        tb["n_cols"] = ncols
        o0 = root.matrix_world @ Vector((cx, cy, PLANE_Z))
        planes.append({
            "name": nm,
            "origin": T.to3(o0), "u": T.to3(u), "v": T.to3(v), "n": T.to3(n),
            "half_w": hw, "half_h": hh,
            "type": tb,
            "local": [cx, cy, PLANE_Z],
            "carrier_z": PZ_RAIL,
            "standoff_m": round(PLANE_Z - PZ_RAIL, 6),
            "corners_px": {
                k: dict(zip(("x", "y"), mod.project(
                    scene, cam, o0 + u * (hw * sx) + v * (hh * sy))))
                for k, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                                  ("bl", -1, -1), ("br", 1, -1))},
        })

    print("TYPE  metrics measured in Blender (FONT.size is NOT an em):")
    for p in planes:
        t, c = p["type"], p["corners_px"]
        ppm = (math.hypot(c["tr"]["x"] - c["tl"]["x"],
                          c["tr"]["y"] - c["tl"]["y"]) / (2 * p["half_w"]))
        print("   %-8s size %.5f -> adv %.6f m (ratio %.6f)  cap %.6f  "
              "base %.6f   %.1f px/m -> cap %.2f px, %d cols = %.1f px"
              % (p["name"], t["size_m"], t["adv_m"], t["adv_m"] / t["size_m"],
                 t["cap_m"], t["base_m"], ppm, t["cap_m"] * ppm,
                 t["n_cols"], t["n_cols"] * t["adv_m"] * ppm))
        assert p["half_h"] >= t["cap_m"] / 2 - 1e-9, p["name"]
        assert p["half_w"] >= t["n_cols"] * t["adv_m"] / 2 - 1e-9, p["name"]

    # ------------------------------------------------------ THE CAPTURE POSE
    # everything from here on is rendered in the pose module.js rests in.
    knob_rest = [o.matrix_basis.copy() for o in knob]

    def set_dial(deg):
        """Turn the selector knob by `deg` CLOCKWISE on screen, about the hub.
        build.py has no set_dial(): main() renders the knob once and spins the
        SPRITE in CSS, so the rotation is reproduced here from the anchor."""
        a = Vector(ctrl["dial"]["anchor"])
        M = (Matrix.Translation(a) @ Matrix.Rotation(math.radians(-deg), 4, 'Z')
             @ Matrix.Translation(-a))
        for o, b in zip(knob, knob_rest):
            o.matrix_basis = M @ b

    def set_capture(state):
        slider.location = (0.0, ctrl["capture"]["travel"]
                           if state == "capture" else 0.0, 0.0)
        lamp.data.materials[0] = ctrl["capture"]["mats"][
            "on" if state == "capture" else "off"]

    def show_tray(frame):
        keep = set(dev_sets[frame]) if frame is not None else set(dev)
        for o in dev:
            o.hide_render = o not in keep
        return [o for o in dev if o in keep]

    dial_deg = mod.DIAL_RANGE[0] + (mod.DIAL_RANGE[1] - mod.DIAL_RANGE[0]) \
        * POSE_DIAL / (len(mod.SCOPES) - 1)
    set_dial(dial_deg)
    set_capture(POSE_CAPTURE)
    tray_vis = show_tray(POSE_TRAY)
    bpy.context.view_layer.update()
    live_rest = knob + plunger + [lamp] + tray_vis
    print("POSE  dial %+.1f deg (%s), capture %s, tray frame %d (%d meshes)"
          % (dial_deg, mod.SCOPES[POSE_DIAL], POSE_CAPTURE, POSE_TRAY,
             len(tray_vis)))

    # ------------------------------------------------------------- uBias
    # BRIEF step 3 / trap 24.  The depth composite discards any live fragment
    # within uBias of the baked surface behind it, silently.  The template's
    # old 2 mm default would have deleted IPM's ENTIRE developing plate: the
    # tiles are authored 1.0 mm proud of ipm_tray_plate.  Measured by rendering
    # the depth pass a second time with the live objects VISIBLE.
    #
    # Rendered with ALL 15 tile meshes visible (not just the posed frame), so
    # the minimum is over every state the tray can be in rather than over one.
    show_tray(None)
    bpy.context.view_layer.update()
    with tempfile.TemporaryDirectory() as td:
        liv = T.render_depth(scene, os.path.join(td, "_depth_live.bin"))
    show_tray(POSE_TRAY)
    bpy.context.view_layer.update()
    d0, d1 = dep, liv                      # both (H, W)
    g2 = d0 - d1
    m2 = (d0 < 1e9) & (d1 > 1e-6) & (g2 > 1e-6) & (g2 < 1.0)
    # EROSION, and it is not a fudge.  The raw min over `m2` is a SILHOUETTE
    # pixel: where a live object's edge partly covers a pixel, the depth buffer
    # holds one sample somewhere inside that coverage, so `baked - live` there
    # is a partial-coverage artefact and not a stand-off any prop actually has.
    # IPM's raw min is 0.090 mm against a real minimum of 1.001 mm -- an 11x
    # difference, and using it would ship a uBias 11x smaller than the module
    # needs.  Keeping only pixels whose four neighbours are ALSO live-covered
    # drops the silhouette and leaves the interiors.
    inner = m2.copy()
    inner[1:, :] &= m2[:-1, :]
    inner[:-1, :] &= m2[1:, :]
    inner[:, 1:] &= m2[:, :-1]
    inner[:, :-1] &= m2[:, 1:]
    raw = np.sort(g2[m2])
    gaps = np.sort(g2[inner])
    ubias = round(0.7 * float(gaps.min()), 6)
    print("  UBIAS live stand-offs: %d px, raw min %.6f (silhouette); "
          "%d INTERIOR px, min %.6f  p1%% %.6f  median %.6f  max %.6f "
          "-> ubias_m = 0.7 x %.6f = %.6f"
          % (len(raw), raw.min(), len(gaps), gaps.min(),
             np.percentile(gaps, 1.0), np.median(gaps), gaps.max(),
             gaps.min(), ubias))
    for lo, hi in ((0.0, 0.0005), (0.0005, 0.0009), (0.0009, 0.0011),
                   (0.0011, 0.005), (0.005, 1.0)):
        print("      gap %6.4f .. %6.4f m : raw %6d px   interior %6d px"
              % (lo, hi, int(((raw >= lo) & (raw < hi)).sum()),
                 int(((gaps >= lo) & (gaps < hi)).sum())))

    # ------------------------------- the readout STRINGS, and their type
    # IPM authors NO content type at all, so all three readouts are in PKT's
    # position: the type is created HERE, with the module's own text() helper,
    # its own font and its own ink material, at the declared plane, in the
    # pose's own strings -- and it exists nowhere else.  Made AFTER plate.png,
    # depth.bin and all three glbs, so it is in none of them (asserted).
    ink_mats = {k: bpy.data.materials[v] for k, v in INK_MAT.items()}
    stand_ins, per_plane = [], {}
    for p in planes:
        t = p["type"]
        cx, cy, _ = p["local"]
        objs = []
        for i, body in enumerate(TEXT[p["name"]]):
            if not body:
                continue
            py = cy + t["top_m"] - i * t["lead_m"]
            px = cx + (t["left_m"] if t["align"] == "left" else 0.0)
            o = mod.text("ipm_dom_%s_%d" % (p["name"], i), body, t["size_m"],
                         ink_mats[p["name"]], (px, py, PLANE_Z),
                         align='LEFT' if t["align"] == "left" else 'CENTER')
            o.parent = root
            o.matrix_parent_inverse = Matrix.Identity(4)
            objs.append(o)
        stand_ins += objs
        per_plane[p["name"]] = objs
    bpy.context.view_layer.update()
    assert not (set(stand_ins) & set(plate)) and not (set(stand_ins) & set(live))

    # ---- MEASURED: what actually crosses a declared rect, and is it live?
    # The audit's harness was not kept (BRIEF correction 11); this rebuilds the
    # useful half of it.  What matters for check_occlusion.py check 4 is the
    # LIVE/BAKED split of the occluders: baked ones are in depth.bin and so in
    # its offline ground truth, live ones are not.
    dg = bpy.context.evaluated_depsgraph_get()
    liveset = set(o.name for o in live)
    typeset = set(o.name for o in stand_ins)
    cam_o = cam.matrix_world.translation

    def probe(local, hw, hh, nn=11):
        o0 = root.matrix_world @ Vector(local)
        hits = collections.Counter()
        for i in range(nn):
            for j in range(nn):
                s = o0 + u * (hw * (2 * i / (nn - 1) - 1)) \
                       + v * (hh * (2 * j / (nn - 1) - 1))
                vv = s - cam_o
                d = vv.length
                ok, loc, nrm, idx, ob, mw = scene.ray_cast(
                    dg, cam_o, vv.normalized(), distance=d - 0.001)
                if ok and ob is not None and ob.name not in typeset:
                    hits[("LIVE " if ob.name in liveset else "baked ")
                         + ob.name] += 1
        return hits

    print("PROBE  11x11 ray-cast per declared rect, close cam, EXPORT pose:")
    probe_json, live_hits = {}, 0
    for p in planes:
        h = probe(p["local"], p["half_w"], p["half_h"])
        nl = sum(c for k, c in h.items() if k.startswith("LIVE"))
        live_hits += nl
        probe_json[p["name"]] = {"covered": sum(h.values()), "of": 121,
                                 "live": nl, "by": dict(h.most_common(6))}
        print("   %-8s %3d/121 covered   live %d   %s"
              % (p["name"], sum(h.values()), nl,
                 dict(h.most_common(4)) if h else "clear"))
    # the same probe with the plunger PRESSED, which lifts the knob off the
    # `output` strip: the live occlusion is real and it is transient.
    set_capture("capture")
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    pressed = {}
    for p in planes:
        h = probe(p["local"], p["half_w"], p["half_h"])
        pressed[p["name"]] = {"covered": sum(h.values()), "of": 121,
                              "live": sum(c for k, c in h.items()
                                          if k.startswith("LIVE")),
                              "by": dict(h.most_common(6))}
    print("   the same rects with the plunger PRESSED: %s"
          % {k: (val["covered"], val["live"]) for k, val in pressed.items()})
    set_capture(POSE_CAPTURE)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    print("   LIVE geometry in front of a declared rect at REST: %d samples"
          % live_hits)

    # ---------------------------------------------- ground-truth renders
    inks = {}
    for p in planes:
        fn = os.path.join(OUT, "gt_type_%s.png" % p["name"])
        T.render_colour(scene, fn, visible=per_plane[p["name"]])
        inks[p["name"]], cnt = median_ink(fn)
        p["ink"] = inks[p["name"]]
        print("INK   %-8s median rgb%s over %d covered px  (material %s)"
              % (p["name"], tuple(inks[p["name"]]), cnt, INK_MAT[p["name"]]))
    # the type ALONE: its opaque pixels are exactly the glyph coverage, which
    # is what verify_assets.py takes its footprint from and what check_text.py
    # scores the DOM against.
    T.render_colour(scene, os.path.join(OUT, "gt_platen0.png"),
                    visible=stand_ins)
    # THE ONE compare.py SCORES: exactly the objects the browser renders live,
    # in exactly the state __occ.pose() puts the page in.
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"),
                    visible=live_rest)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + live_rest)

    # sign check for the dial: a POSITIVE angle about the declared axis must
    # turn the index CLOCKWISE, toward the SVG detent.  Get it backwards and
    # compare.py against gt_full_read.png spikes.
    set_dial(62.5)
    bpy.context.view_layer.update()
    T.render_colour(scene, os.path.join(OUT, "gt_dial_p062.png"), visible=knob)
    set_dial(dial_deg)
    bpy.context.view_layer.update()

    # ------------------------------------------------------------- depth QA
    # every probe on a VISIBLE STATIC surface (BRIEF trap 7): an interior point
    # or a point on a LIVE object records whatever is behind it in depth.bin.
    rows = T.verify_depth(scene, cam, dep, [
        ("nameplate face",
         root.matrix_world @ Vector((-0.050, mod.NAME_Y, mod.PZ + 0.006))),
        ("resolver top rail",
         root.matrix_world @ Vector((-0.060, -0.0385, PZ_RAIL))),
        ("resolver bottom rail",
         root.matrix_world @ Vector((0.060, -0.0965, PZ_RAIL))),
        ("tray top rail",
         root.matrix_world @ Vector((-0.060, -0.2030, PZ_RAIL))),
        # the developing plate itself, seen through the tray aperture: the
        # surface the tiles stand 1.0 mm proud of.
        ("developing plate",
         root.matrix_world @ Vector((0.040, -0.2400, 0.0275))),
        ("panel face (capture strip)",
         root.matrix_world @ Vector((0.020, -0.1850, 0.0260))),
    ])
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-26s want %.5f  got %.5f  err %+.6f" % (nm, want, got, err))

    # ------------------------------------------------------------ hotspots
    def bb(objs, pad=8):
        return mod.clamp_rect(mod.bbox_rect(scene, cam, objs, pad=pad), W, H)

    hs_dial = bb(ctrl["dial"]["hotspot_objs"], pad=6)
    sv = slider.location.copy()
    slider.location = (0.0, ctrl["capture"]["travel"], 0.0)
    bpy.context.view_layer.update()
    r_dn = mod.bbox_rect(scene, cam, plunger + [lamp], pad=10)
    slider.location = sv
    bpy.context.view_layer.update()
    hs_cap = mod.clamp_rect(mod.union(
        [r_dn, mod.bbox_rect(scene, cam, plunger + [lamp], pad=10)]), W, H)
    hs_tray = mod.clamp_rect(mod.pts_rect(scene, cam, root,
                                          ctrl["tray"]["hotspot_pts"], pad=8),
                             W, H)
    # the periscope head is not a declared control -- build.py gives it no
    # manifest entry -- but the page needs somewhere to load the next plate,
    # so its bbox is emitted rather than a screen rect being guessed in JS.
    head_objs = [bpy.data.objects[n] for n in
                 ("ipm_drum", "ipm_drum_cap_0", "ipm_drum_cap_1", "ipm_hood",
                  "ipm_hood_ring", "ipm_viewport")]
    hs_head = bb(head_objs, pad=6)

    # ---------------------------------------------------------- scene.json
    def names(objs):
        return [o.name for o in objs]

    j = {
        "render": {"w": W, "h": H},
        "camera": T.cam_json(scene, cam),
        "lights": T.lights_json(scene, close_tags),
        "world_bg": list(scene.world.node_tree.nodes["Background"]
                         .inputs[0].default_value),
        "colour": {"view_transform": scene.view_settings.view_transform,
                   "look": scene.view_settings.look,
                   "exposure": scene.view_settings.exposure},
        # MEASURED on the real page, not the fleet constant.  BRIEF 5.2a.
        "light_gain": LIGHT_GAIN,
        "env_intensity": 0.0,    # measured optimum, monotonically
        "raytrace": 1,
        "scale": 1.0,
        # MEASURED off a second depth pass with the live objects visible.
        # BRIEF step 3; the 2 mm default deletes the whole developing plate.
        "ubias_m": ubias,
        "ubias_min_gap_m": round(float(gaps.min()), 6),
        "ubias_min_gap_raw_m": round(float(raw.min()), 6),
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "panel": {"u": T.to3(u), "v": T.to3(v), "n": T.to3(n),
                  "origin": T.to3(root.matrix_world @ Vector((0, 0, 0))),
                  "spin_axis": spin_axis,
                  "spin_note": "rotate by a POSITIVE angle about spin_axis "
                               "for a CLOCKWISE turn on screen"},
        "rake_deg": {"working_face_off_slot_plane": 0.0,
                     "obliquity_to_close_cam": obliq},
        "props": {
            "dial": {
                "glb": "dial.glb", "kind": "rotate",
                "label": ctrl["dial"]["label"],
                "nodes": names(knob),
                "hub": T.to3(dial_anchor), "axis": spin_axis,
                "pivot_px": {"x": dial_px, "y": dial_py},
                "range": list(ctrl["dial"]["range"]),
                "detents": list(ctrl["dial"]["detents"]),
                "hotspot": hs_dial},
            "capture": {
                "glb": "capture.glb", "kind": "states",
                "label": ctrl["capture"]["label"],
                "order": list(ctrl["capture"]["order"]),
                "plunger": names(plunger),
                "lamp": lamp.name,
                "lamp_mats": {k: m.name
                              for k, m in ctrl["capture"]["mats"].items()},
                # the slider translates along the face's own +v by `travel`
                # (build.py: slider.location = (0, travel, 0), travel < 0)
                "axis": T.to3(v), "travel_m": ctrl["capture"]["travel"],
                "hotspot": hs_cap},
            "tray": {
                "glb": "tray.glb", "kind": "frames",
                "label": ctrl["tray"]["label"],
                "frames": mod.DEV_FRAMES,
                # PER FRAME, the meshes that are visible.  These are DIFFERENT
                # meshes, not one mesh at N positions: a tile migrates through
                # three silver densities as it develops, so there is no
                # continuous parameter to drive (contrast PKT's three frame
                # controls).  Frame 0 is deliberately EMPTY -- an unexposed
                # plate -- which is why this is a list of lists and not a
                # stride.
                "frame_nodes": [names(s) for s in dev_sets],
                "nodes": names(dev),
                "axis": "y",
                "hotspot": hs_tray},
        },
        "head": {"label": "PERISCOPE HEAD", "hotspot": hs_head},
        "text_planes": planes,
        "ink": inks,
        "readout_text": [TEXT[p["name"]] for p in planes],
        "pose": {"dial": POSE_DIAL, "dial_deg": dial_deg,
                 "capture": POSE_CAPTURE, "tray": POSE_TRAY},
        "scopes": list(mod.SCOPES),
        "depth_verify": [{"name": n_, "analytic": w_, "baked": g_, "err": e_}
                         for n_, w_, g_, e_ in rows],
        "probe": probe_json,
        "probe_plunger_pressed": pressed,
        "probe_live_hits": live_hits,
        "stamped_labels": STAMPED,
    }
    with open(os.path.join(OUT, "scene.json"), "w") as f:
        json.dump(j, f, indent=1)
    with open(os.path.join(OUT, "materials.json"), "w") as f:
        json.dump(T.materials_json(), f, indent=1)
    print("EXPORT OK ->", OUT)


# ===========================================================================
# THE REFIT PORT -- a SECOND entry point, deliberately separate from main().
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_ipm.py -- refit
#
# main() above rebuilds the shell and RE-RENDERS plate.png, depth.bin and all
# seven gt_*.png.  Running it would invalidate every number in
# live3d/RESULTS.md and in modules/IPM/NOTES.md.  This entry point does none of
# that: it builds the port ALONE IN AN EMPTY SCENE, writes assets/IPM/refit.glb
# and merges a "refit" block into the existing scene.json.  Nothing else in
# assets/IPM/ is opened for writing.  FIX_UPLOAD.md section 0, decision 3.
#
# ROOT SCALE IS 1.0 ON THIS PATH AND IS NOT PASSED.  IPM's own
# `scene.json -> scale` is 1.0 anyway, but the rule that matters is
# FIX_UPLOAD 12.15 item 2's: both fitting entry points CLEAR THE SCENE and
# build in WORLD coordinates from the solver's own world-space frame, so there
# is no root to be inside.  `build()` refuses a non-unit value in an empty
# scene; let it refuse.
#
# WHERE IT SITS, AND WHY IT IS NOT (632, 686).
# FIX_UPLOAD 3.3 tables (632, 686) at 56 px, "the column, below the panel's
# bottom rail ... backing block must be curved to the column", and 8.4 names
# IPM as the module whose carrier is curved.  The carrier is right, the size is
# right, the y is right, and this is the first module in the fan-out whose
# tabled anchor is buildable AS TABLED: (632, 686) solves at 56 px with a
# 5.06 mm seat.  It is still not where the port ships, and the reason is the
# same property OTA found:
#
#   THE CARRIER IS A CYLINDER, and its crown is at x = 639.4, not 632.
#   Below the instrument the pillar is solid over x 577..702, y 638..719 and
#   its depth profile does not vary with y at all (a vertical cylinder seen by
#   a camera that looks horizontally -- `forward` has y = 0).  Across the
#   119 px face `depth.bin` reads 2.0619 m at x 584, falls to a minimum of
#   2.0251 m at x ~ 639, and rises to 2.0844 m at x 702: 59.3 mm of sag.  A
#   parabola through the profile puts the vertex at x 639.41; the axis of
#   symmetry (the x that minimises the mean |d(x-k) - d(x+k)| over k = 2..35)
#   is x 639.50, with a mean asymmetry of 51 um.  So the crown is 639, and
#   `solve_anchor()`'s fitted normal agrees: obliquity 0.57 deg at x = 639
#   against 7.37 deg at the tabled 632, because 7 px off the crown a
#   least-squares plane through the port's own footprint is TILTED by the
#   bulge.  That is an 7 px nudge, half of what FIX_UPLOAD 3.5 sanctions.
#
#   THE SEAT IS SET BY THE SAGITTA AND IS NEARLY INDEPENDENT OF THE ANCHOR.
#   Over x 636..644 it moves only 4.91 -> 5.11 mm, and over the whole y range
#   of the pillar it does not move at all.  What DOES move it is the window
#   (below).  OTA's inversion is confirmed a second time and in a new
#   direction: sweeping `port_px` at the crown with the window held at the
#   port's own bbox, EVERY size from 40 to 60 px solves (seat 3.53 -> 5.78 mm,
#   cap 0.12 W = 5.42 -> 8.17 mm, so the two scale together) and 62 px and up
#   are refused for OFF FRAME, not for the seat.  On IPM the size is bounded by
#   the 720 px frame edge, not by the cylinder.  Shipped at the TABLED 56 px.
#
#   `--window` ON A CYLINDER MOVES THE SEAT, and here it moves the NORMAL too.
#   OTA's normal was stable to 0.1 deg over every window and only the seat
#   moved; IPM's does both, because the anchor sits on the crown and a window
#   that is not centred on the crown fits a tilted plane:
#
#     window                     obliquity   seat      resid p50 / max
#     607,671,658,714 (shipped)     0.57     4.93 mm   0.00249 / 0.00658
#     port envelope 600,664,658,714 7.37     5.06 mm   0.00254 / 0.00692   (at x 632)
#     default (px+-40, py+-24)      3.29     3.72 mm   0.00166 / 0.00416   (at x 636)
#     592,672,662,710               8.01     7.11 mm   0.00410 / 0.01189   (at x 632)
#     577,703,638,719 (whole face)   --       REFUSED: seat 20.9 mm > cap 7.7 mm
#
#   The shipped window is the port's OWN PROJECTED HEXAGON BBOX -- 64.7 x 56 px
#   at (639, 686) -- which is the patch of carrier the port actually covers and
#   the honest answer to "whose normal do you trust".  Same choice as OTA.
#
# THE SERVICE CONDUIT ELBOW that FIX_UPLOAD 8.4 warns about is real and it is
# measured: a ledge at x 522..583, y 657..671 standing at 2.0030 m, i.e. 22 mm
# NEARER the camera than the crown, immediately above-left of the anchor.  The
# port's envelope starts at x = 602.6, so it clears the elbow by 19.6 px.  At
# the tabled x = 632 the clearance is 12.7 px; anywhere left of x = 612 the
# solver refuses on the seat anyway.
#
# WHAT THE PORT CROSSES: nothing.  Over its own envelope `plate.png` is luma
# mean 71.50, sd 8.16 -- the cylinder's own shading gradient and no lettering.
# IPM's nameplate is on the instrument, 500 px above.  (MQB's rail-vs-nameplate
# finding, STATUS_AT_A_GLANCE 17.6's generalisation of it.)
#
# THE STAND-OFF FLOOR (FIX_UPLOAD 12.16 item 2).  `seat_margin` is left at the
# shared default 2.5 and that is a MEASUREMENT, not an omission: IPM's
# `ubias_m` is 0.000700, derived from a real 1.001 mm eroded minimum gap, so
# 2.5 x ubias = 1.750 mm -- above the eroded minimum, and 367 px of the
# carrier's own depth gradient against a floor of 0.50.  FMM needed 1200 here
# because its `ubias_m` is 1e-06 and is not a gap at all.
#
# Sweep any of it yourself, with no Blender in the loop:
#
#   python3 live3d/pipeline/refit_port.py IPM 639 686 56 --window 607,671,658,714
#   python3 live3d/pipeline/refit_port.py IPM 632 686 56 --window 600,664,658,714
#   python3 live3d/pipeline/refit_port.py IPM 639 686 56 --window 577,703,638,719
#   python3 live3d/pipeline/refit_port.py IPM 639 686 56 --sweep-y 660,700
IPM_REFIT = dict(px=639, py=686, port_px=56,
                 # the port's own projected hexagon bbox, held fixed
                 carrier_window=(607, 671, 658, 714),
                 label="REFIT",
                 # FIX_UPLOAD 12.9 keeps `mark=` "for the roomier modules
                 # (IPM 63 mm, OTA 65 mm)".  IPM is the module that prediction
                 # is RIGHT about -- the measured W is 63.57 mm -- and the mark
                 # is STILL cut, because the mark is 0.060 W and W scales with
                 # the module's px/m: 3.81 mm at 880.9 px/m is 3.4 px on
                 # screen, the same 3 px smear it was on KVS, MQB, MTA and OTA.
                 # The mm column was never the criterion.  532 triangles saved.
                 mark=None,
                 # The 1.3 W sub-base is for a featureless bulkhead (LOG, MTA).
                 # IPM's pillar is 119 x 82 px of clean cylinder; a 1.3 W
                 # footprint is 84 x 73 px and would climb off the bottom of
                 # the frame, and the instrument's own base 20 px above the
                 # envelope is the structure the sub-base substitutes for.  Off.
                 sub_base=False, service_rail=True)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(IPM_REFIT)
    A = RP.solve_anchor(CODE, K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"])
    P = RP.build("ipm_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export(CODE, A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))


# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_ipm.py -- mast
#
# Like `refit`: main() re-renders plate.png, depth.bin and all seven gt_*.png
# and would invalidate every number in live3d/RESULTS.md and
# modules/IPM/NOTES.md.  This entry point builds the mast ALONE IN AN EMPTY
# SCENE, in WORLD coordinates (root_scale 1.0 and NOT passed, for the same
# reason it is not passed for the port), writes assets/IPM/mast.glb and merges
# a "mast" block into the existing scene.json.
#
# IT IS NOT ON THE REFIT PORT'S SERVICE RAIL, AND THAT IS MEASURED.
# STATUS_AT_A_GLANCE 11.2 mounts this fitting on the port's rail.  Solved
# first, as 11.2 instructs, IPM's rail SOLVES -- and it solves onto nothing:
#
#     python3 live3d/pipeline/status_mast.py IPM --m 7 --rake 0 --px 180
#       L 0.2045 m   envelope 717.4..923.0 x 650.3..705.5 px
#       lift over the carrier   0.000000 m vs 0.000700 m ubias  (0.0x)
#       carrier solid behind    100.0 %   depth 2.2133 .. 2.3339 m
#
# The rail direction u is screen-RIGHT and the port's carrier -- the crown of
# the column -- is at 2.0251 m, but the column's right edge is x = 703 and the
# published free_from_m = 1.5 W = 0.0954 m already lands A = 0 at x = 717.  So
# the whole fitting would hang in the PORT'S plane over a FLOOR 190 to 310 mm
# further away: 100 % "solid" behind, and 250 mm in front of all of it, on a
# 250 px cantilever off the side of a column.  That is MTA's rejected shelf and
# OTA's 2.3 %-solid rail arriving in a third form -- the solver's "solid
# behind" test cannot see it, because the pixels ARE solid.  READ THE DEPTH
# RANGE BESIDE THE PERCENTAGE, not the percentage.  Second reason, independent
# of the first: the docket lands at (678.8, 345.3) 520 x 317.9 on this page
# (measured on the running page, with a real pointer, before any of this was
# built), so the rail-mounted envelope's top 13 px -- which is exactly where
# STATUS_AT_A_GLANCE 6.5 item 9 puts the CATALOGUE LAMP ROW -- is underneath
# the docket whenever the port is open, and reading the mast while the port is
# open is the entire reason the close-up half exists.
#
# So IPM takes status_mast.py's second documented route, `--at PX,PY`, with the
# carrier measured at that pixel by the port's own fit_carrier_plane(), and no
# rail -- STATUS_AT_A_GLANCE 6.1's ORIGINAL "small brass status sub-plate
# bolted to the panel", which 11.2's rail was an upgrade to, not a replacement
# for.  `mast.rail_ramp_m`, `mast.rail_span_m` and `mast.evidence.rail_bbox_px`
# are all `null` on this route (STATUS_AT_A_GLANCE 16.1 item 5).
#
# WHERE IT WENT: THE FLOOR, LEFT OF THE COLUMN'S FOOT.  IPM has exactly two
# carriers and no third: the instrument's own faceplate (139 px wide, and the
# module's conversion already established that nothing bigger than 30 x 25 mm
# fits on it) and the FLOOR, a large shallow dish that fills y 606..719 across
# the whole frame.  Everything else was eliminated by measurement:
#
#   * The COLUMN below the panel is 119 x 82 px and the port takes
#     x 602.6..675.3 y 658.9..717.9 of it.  Nothing else goes there.
#   * The FLOOR RIGHT of the column is where the port's own docket lands.  The
#     docket's bottom edge is at y 663.2 (it is anchored at cy - 26, where cy
#     is the port's projected centre, so it is stable at any docket height),
#     and the frame ends at y 719: a 56 px slot for a 57 px fitting.  The best
#     that fits is `--at 760,710 --rake 55`, envelope 754.3..960.0 x
#     665.5..718.0 -- 2.3 px of clearance to the docket and 1.0 px to the
#     bottom of the frame.  It was built and looked at; it is not shippable
#     margin, and shrinking the mast to buy margin costs the graduation pitch
#     that is the whole reason IPM can carry seven cells at all.
#   * The FLOOR LEFT of the column is clear from x 0 to the SERVICE CONDUIT
#     ELBOW at x 493..576, y 618..671 (the same fitting FIX_UPLOAD 8.4 warns
#     the port about, standing at the instrument's own depth ~1.983 m, i.e.
#     245 mm nearer the camera than the floor behind it).  Left of x = 493 the
#     floor is 100 % solid, featureless (plate.png over the shipped envelope is
#     luma mean 64.51, sd 1.88 -- no baked lettering anywhere near it, MQB's
#     rail-vs-nameplate check) and 100 px tall.  Shipped at (290, 685),
#     envelope 284.2..477.7 x 635.9..689.7, which is 15.3 px clear of the elbow
#     and 30 px clear of the bottom of the frame.
#
# 170 px, NOT 180, AND THE CAPTION IS WHY.  The fleet ships 180; at 180 on this
# anchor everything solves (envelope 268.7..473.7, graduations 14.73 px) and the
# fitting is then partly UNDERNEATH ITS OWN CAPTION.  `mast.js`'s `place()`
# ranks "to port, on the sill" second and CLAMPS a candidate to x >= 8, so a
# caption wider than the room to port is pushed back over the fitting rather
# than rejected: IPM's caption is 262.3 px wide (it wraps
# "1 INCONCLUSIVE -- the PoC could not decide" onto two lines), the room to port
# of a 180 px mast here is 252.7 px, and the caption's right edge lands 1.5 px
# INSIDE the mast's envelope -- 362 px^2 over its hotspot, measured on the
# running page.  Nothing readable is lost (it is the outer corner of the foot
# bracket) but it is a defect and it is removable.  At 170 px the room to port
# is 268.1 px, the caption clears the fitting by 5.8 px, and one graduation is
# still 13.90 px -- the roomiest in the fan-out (MTA 12.5, OTA 12.2).  The clamp
# is shared-code behaviour and is REPORTED, NOT CHANGED.
#
# THE COST, NAMED: the mast is 116.9 px from the port instead of the 8 px OTA
# managed, and the two fittings read as two installations on one deck rather
# than as one installation running down one column.  That is the price of the
# docket owning the right-hand floor, and it was paid deliberately.
#
# RAKE 54, AND THE OBLIQUITY TABLE'S MINIMUM IS AT 63.
# STATUS_AT_A_GLANCE 17.5: `--rakes` prints OBLIQUITY and obliquity is not the
# criterion; `px_per_m_carrier`, v against n, is.  IPM's floor reads
# v 479.6 / n 653.8 px/m -- a ratio of 1.36, KVS's case (1.44), not FMM's (34x)
# -- so a fitting LYING on this floor is foreshortened to 60 % in one direction
# and a rake buys it back.  Measured at this anchor, in 1-degree steps:
#
#     rake   face obliquity   px/m A   px/m B
#      0       64.04           806.4    480.8     <- flat on the floor
#     45       20.01           808.1    797.7
#     53       12.82           808.4    807.3
#     54       11.99           808.4    807.3     <-- SHIPPED, B is maximal
#     57        9.69           808.4    806.1
#     60        7.88           808.5    802.8
#     63        6.94           808.5    797.3     <- the table's minimum
#
# B peaks at 54 and the obliquity minimum is nine degrees past it.  The two
# criteria genuinely disagree here -- FMM's warning was about a table with a
# minimum where no rake was wanted at all; this is a table with a minimum where
# a rake IS wanted and the minimum is still the wrong number.  At 54 the mast's
# own two axes project at 810.1 and 808.2 px/m, within 0.24 % of each other and
# unforeshortened in both, which is what 6.5 item 3 asked for.
# Fleet: KVS 45, MQB 0, MTA 0, OTA 57, FMM 0, IPM 54.  Do not inherit any.
#
# `--window` IS LOAD-BEARING AND IT FAILS SILENTLY HERE, exactly as on OTA.
# The default window at this anchor (px +- 40, py +- 24) reaches the elbow and
# is silently wrong: at (285, 685) it returns carrier 70.01 deg instead of
# 64.04, residual max 0.19 m, and a lift of 8.05 mm instead of 15.75 -- no
# error, no warning.  At (470, 672) it is worse and still silent: carrier
# 97.65 deg, i.e. FACING AWAY, lift 0.000 mm, residual max 0.10 m.  The shipped
# window is the fitting's own envelope band, 284,478,634,690.
#
# THE STAND-OFF FLOOR (FIX_UPLOAD 12.16 item 2), and this is the one number on
# IPM that is not comfortable.  The floor recedes 1.81 mm per screen pixel --
# by far the steepest depth gradient any fitting in the fleet has been seated
# on (KVS port 0.63, OTA mast 1.53, FMM 0.10 mm/px) -- so the shared default
# `lift_margin = 2.5` is 1.75 mm and worth only **0.97 px of that gradient**
# against a floor of 0.50.  It passes, and it would have been the tightest
# shipping figure in the fleet by a factor of two.  Shipped at
# `lift_margin = 6.0`: 4.20 mm, **2.32 px of gradient**, in the fleet's own
# band (KVS 2.23, OTA mast 2.43) and still 4.2x above IPM's 1.002 mm eroded
# minimum live-to-baked gap, so trap 24 cannot fire on it.  It costs 1.75 mm of
# lift (15.75 -> 17.50 mm) and nothing else.  FMM needed 1200 here because its
# `ubias_m` is 1e-06 and is not a gap; IPM's 0.000700 is a real 1.001 mm gap,
# so the multiplier stays small -- READ THE PIXELS OF GRADIENT, not the ratio.
#
# M = 7.  It is the COUNT of image-processing-module/vuln_tests/NN_*.py, never
# max(NN): the files are 01, 02, 03, 04, 06, 07, 08 -- there is no 05 -- so
# max(NN) would say 8.  STATUS_AT_A_GLANCE 9.4 rule 4.  `status.json ->
# IPM.vulns.total` agrees at 7.
#
# `numbers=False`: 13.9 px per graduation, the roomiest in the fan-out so far
# (MTA 12.5, OTA 12.2), and still not room for engraved digits -- ~2,600
# triangles for ~9 px lettering on a page that ships 1,762 live triangles in
# total.  The catalogue list in the hover panel carries the identity instead,
# in lamp order.  STATUS_AT_A_GLANCE 6.5 item 6.
#
# Sweep any of it yourself, with no Blender in the loop:
#
#   python3 live3d/pipeline/status_mast.py IPM --at 290,685 \
#           --window 284,478,634,690 --rake 54 --m 7 --px 170 --lift-margin 6
#   python3 live3d/pipeline/status_mast.py IPM --at 290,685 \
#           --window 284,478,634,690 --m 7 --px 170 --rakes
#   python3 live3d/pipeline/status_mast.py IPM --m 7 --rake 0 --px 170
#   python3 live3d/pipeline/status_mast.py IPM --at 285,685 --m 7 --px 170 --rake 54
IPM_MAST = dict(mast_px=170, rake_deg=54.0, m=7, kind="defensive",
                numbers=False,
                at=(290, 685),
                carrier_window=(284, 478, 634, 690),
                lift_margin=6.0)


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(IPM_MAST)
    A = SMT.solve_mast(CODE, mast_px=K["mast_px"], rake_deg=K["rake_deg"],
                       m=K["m"], kind=K["kind"], numbers=K["numbers"],
                       px=K["at"][0], py=K["at"][1],
                       carrier_window=K["carrier_window"],
                       lift_margin=K["lift_margin"])
    P = SMT.build("ipm_mast", A["frame_blender"], A["carrier_blender"],
                  A["L_m"], m=A["m"], kind=K["kind"], numbers=K["numbers"],
                  rail=A["rail"], ramp=A["rail_ramp"])
    SMT.export(CODE, A, P)
    print("TELLTALE MAST OK -> %s  (%d tris)" % (OUT, P["tris"]))


if __name__ == "__main__":
    _argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "refit" in _argv:
        refit()
    elif "mast" in _argv:
        mast()
    else:
        main()
