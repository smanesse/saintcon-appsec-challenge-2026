"""
LIVE-3D EXPORT -- FMM close-up  (Cargo Bay / Manifest Vault).

A thin layer over three-exploration/pipeline/transliterate.py, which already
solved the depth pass, fov_y_deg, the Z-up -> Y-up map, materials.json and the
light description.  What this file adds is FMM's own baked/live split, its four
live controls, its THREE readout planes -- and the TYPE for them, because FMM
authors none.

    plate.png     shell + FMM static parts, MINUS the four manifest-card ink
                  bars.  FMM returns NO R["static"] and NO R["all"]; it returns
                  R["plate"], the WIDE-SHOT list.  Here the two coincide --
                  keep() appends to `plate` only for static props and every live
                  object bypasses it -- but that is DERIVED and ASSERTED below,
                  never assumed (CONVERSION_BRIEF step 1, correction 3).

    lift.glb      the cargo-lift lever (shaft + collar + knob), rotates
    hold.glb      the HOLD needle + tail + hub, rotates about the face normal
    channel.glb   the PASV/PORT pointer + grip, turning about the face normal
    lamps.glb     the two lamp domes -- they never move, but the control
                  declares the material triple off/pasv/port (rule 3)
    rail.glb      the crate on the data rail, translates along the face's +u

    NOT EXPORTED AT ALL: fmm_card_row_0..3, four ruled INK BARS on the manifest
    card.  FMM authors no type anywhere -- the occlusion audit's own words are
    "the manifest card is four ruled ink bars" -- so those bars ARE this
    module's baked stand-in for content text, exactly as LOG's are.  They are
    excluded from plate.png, from depth.bin and from every glb, and the four
    manifest lines are DOM.  Everything else in FMM is unlettered metal, so
    nothing else has to be judged.

    text_planes   three rects, all with u/v/n = root local X/Y/Z (FMM has no
                  face helper: the working face IS the slot plane).
                    manifest  the manifest card face          4 lines x 16 cols
                    hold      the gauge's blank brass nameplate     1 x 13
                    data      the blank left end of the DATA tray   3 x 18

THE DIAL-FACE RULE (CONVERSION_BRIEF section 6) was measured on THIS module and
is applied here: **there is no readout plane on the HOLD dial face.**  The
11x11 ray-cast probe below finds the LIVE needle, tail and hub on that face
across the needle's range; the audit's angular scan found 171 of 360 directions
blocked with a widest clear run of 12 deg.  The gauge's numeric value goes on
its own blank nameplate, which probes 0/121 over 27 poses.

FMM HAS NO text() HELPER AND NO mono_font().  Three of nine modules author no
type at all (FMM, DNSM, LOG), so typemetrics.py's probe finds nothing and its
fallback would silently measure Blender's DEFAULT font.  The fleet-standard
pair is defined here and bound onto the module object -- the same recipe every
other module's build.py carries: Courier New Bold, extrude 0.0004, align_y
CENTER, converted to mesh.  Measured ratio 0.310667, i.e. the face's.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_fmm.py
"""
import bpy, math, os, sys, json
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
from nnscale import decode                                       # noqa: E402

shell = T.shell
CODE = "FMM"
OUT = os.path.join(LIVE3D, "assets", CODE)

# MEASURED, not chosen (brief 5.2a).  The sweep and the parabola fit are in
# modules/FMM/NOTES.md.  0.65 is nobody's optimum.
LIGHT_GAIN = float(os.environ.get("FMM_GAIN", "0.685"))

# ---- THE CAPTURE POSE.  poseForCapture() in modules/FMM/module.js must put the
# page in EXACTLY this state or compare.py measures the mismatch, not the
# renderer.  A transfer in flight: hoist at its wide-shot rest angle, hold 72%
# full, PASV negotiated, crate 62% of the way down the data rail.
POSE_LIFT_DEG = 50.0            # = build.py's LIFT_REST
POSE_HOLD_PCT = 0.72            # -> needle at -125 + 250*0.72 = +55 deg
POSE_CHANNEL = "pasv"
POSE_RAIL_T = 0.62

TXT_NAMES = ["fmm_card_row_%d" % i for i in range(4)]

# ---------------------------------------------------------------------------
# THE READOUT PLAN, in FMM's own module-local metres (root scale is 1).
#  name, cx, cy, z, half_w, half_h, n_lines, n_cols, col_span, lead, top,
#  align, ink material
# `col_span` is the width the n_cols must fill, which is what solves FONT.size
# -- the carrier's own geometry chooses the type size, not a taste.
PLAN = [
    # THE MANIFEST CARD.  The rect is the card face INSET BY 1 mm on every side
    # (brief step 4: never declare a rect flush with its carrier's silhouette --
    # PKT paid 109 px of MSAA seam for it).  The type sits exactly where the
    # four ruled bars were: 52 mm wide, line origins y = 0.118/0.108/0.098/0.088.
    # fmm_gauge_bezel crops the rect's bottom-right corner: real baked geometry
    # for the front pass to redraw, and it never reaches a glyph.
    ("manifest", -0.105, 0.102, 0.0235, 0.034, 0.022, 4, 16, 0.052,
     0.010, 0.016, "left", "fmm_ink"),
    # THE GAUGE'S BLANK BRASS NAMEPLATE.  0/18 in the audit, 0/121 over 27 poses
    # here.  This is where a gauge's number goes; the dial face is the needle's.
    ("hold", 0.000, -0.032, 0.0190, 0.033, 0.0045, 1, 13, 0.064,
     None, 0.0, "center", "fmm_ink"),
    # THE BLANK LEFT END OF THE DATA CHANNEL TRAY.  The lower deck is FMM's
    # separate data connection and carries no readout at all today.  The rect
    # runs under fmm_rail_post_0, which crops it; the type stops 7.9 mm short of
    # the post's projected edge.
    ("data", -0.176, -0.104, 0.0176, 0.050, 0.030, 3, 18, 0.0774,
     0.0135, 0.0135, "left", "fmm_ivory"),
]

# The strings the capture pose paints.  They are DATA -- the exporter renders
# gt_platen0.png from exactly these, and module.js's pose() paints exactly
# these, so check_text.py compares like with like.
POSE_TEXT = {
    "manifest": ["MANIFEST 44-12", "> CARGO.TAR.GZ",
                 "SIZE  2 211 840", "STOR  62 PCT"],
    "hold": ["1.44M / 2.00M"],
    "data": ["DATA CH       PASV", "10.14.2.9:52104", "1371340 / 2211840"],
}


# ------------------------------------------------------- the type FMM lacks
_FONT = [None]


def mono_font():
    if _FONT[0] is None:
        for p in ("/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
                  "/System/Library/Fonts/Menlo.ttc"):
            if os.path.exists(p):
                try:
                    _FONT[0] = bpy.data.fonts.load(p)
                    break
                except Exception:
                    pass
    return _FONT[0]


def text(name, body, size, mat, loc, align='CENTER', to_mesh=True):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body, cu.size = body, size
    cu.align_x, cu.align_y = align, 'CENTER'
    cu.extrude = 0.0004
    f = mono_font()
    if f:
        cu.font = f
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.data.materials.append(mat)
    if to_mesh:
        try:
            bpy.ops.object.select_all(action='DESELECT')
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.convert(target='MESH')
            o = bpy.data.objects.get(name) or o
        except Exception:
            pass
    return o


def dirn(m3, v):
    return (m3 @ Vector(v)).normalized()


def median_ink(path, amin=0.5):
    """MEDIAN over alpha > 0.5, no colour transform, off the PNG BYTES with the
    stdlib decoder (brief rule 7: bpy's image.pixels is already display-encoded
    and the mode over a few opaque px picks a specular highlight)."""
    w, h, nch, rows = decode(path)
    chans = [[], [], []]
    for y in range(h):
        r = rows[y]
        for x in range(w):
            a = r[x * nch + 3] if nch == 4 else 255
            if a <= amin * 255:
                continue
            for c in range(3):
                chans[c].append(r[x * nch + c])
    if not chans[0]:
        return None, 0
    return [sorted(chans[c])[len(chans[c]) // 2] for c in range(3)], \
        len(chans[0])


def clamp_rect(r, W, H):
    x0, y0 = max(0, r["x"]), max(0, r["y"])
    x1 = min(W, r["x"] + r["w"])
    y1 = min(H, r["y"] + r["h"])
    return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}


def main():
    bad = check_snapshots()
    assert not bad, bad
    os.makedirs(OUT, exist_ok=True)
    mod = load_module(CODE)
    mod.text, mod.mono_font = text, mono_font

    P = dict(shell.PARAMS)
    P["exterior"] = 0
    print("raytrace =", P.get("raytrace"),
          " (0 would mean the snapshot is stale again)")
    assert P.get("raytrace") == 1, "shell_snapshot.py is stale: no raytrace"

    scene = shell.build(P)
    scene.render.film_transparent = True
    W, H = scene.render.resolution_x, scene.render.resolution_y
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    before = set(bpy.data.objects)
    R = mod.add_props(P, mats)
    mine = [o for o in bpy.data.objects if o not in before]
    ctrl, root = R["controls"], R["root"]

    # ------------------------------------------------ the live / baked split
    live = []
    for k in ("lift", "hold", "channel", "rail"):
        live += [o for o in ctrl[k]["objs"] if o.type == 'MESH']
    mine_geo = [o for o in mine if o.type in {'MESH', 'CURVE', 'FONT'}]
    static = [o for o in mine_geo if o not in set(live)]
    assert not (set(live) & set(static)), "a live object is also in the plate"
    assert set(static) == set(R["plate"]), \
        "R['plate'] is NOT this module's static set -- re-derive it"
    assert set(R["far"]) == set(live) | set(static)

    txt = [bpy.data.objects[nm] for nm in TXT_NAMES]
    txtset = set(txt)
    assert txtset <= set(static), "the ink bars should be static"
    shell_meshes = [o for o in T.renderables(scene) if o not in set(mine)]
    plate = shell_meshes + [o for o in static if o not in txtset]

    rs = root.matrix_world.to_scale()
    assert max(abs(rs.x - 1), abs(rs.y - 1), abs(rs.z - 1)) < 1e-6, \
        "root is scaled: every local length in PLAN needs multiplying by it"

    lift_objs = list(ctrl["lift"]["objs"])
    hold_objs = list(ctrl["hold"]["objs"])
    domes = list(ctrl["channel"]["domes"])
    sel_objs = [o for o in ctrl["channel"]["objs"] if o not in set(domes)]
    rail_objs = list(ctrl["rail"]["objs"])
    print("split: %d plate objects (%d shell + %d module static - %d ink bars),"
          " %d live (%d lift, %d hold, %d channel, %d rail), %d content -> DOM"
          % (len(plate), len(shell_meshes), len(static), len(txt), len(live),
             len(lift_objs), len(hold_objs), len(sel_objs) + len(domes),
             len(rail_objs), len(txt)))

    # ---------------------------------------------------- the close-up rig
    # FMM HAS close_rig(root) and main() calls it from the module's as-built
    # rest state, so there is no pre-state to reproduce (cf. OTA, which raises
    # its cartridge first).  main() then calls close_grade(), which dims the
    # shell's seven lights to 45% and puts an "AgX - Punchy" look and -0.20
    # stops on the CLOSE camera only; both are reproduced here so plate.png
    # matches the module's own close_plate.png.  The exposure goes to the
    # frontend as colour.exposure (three: toneMappingExposure = 2^exposure);
    # the LOOK has no three.js equivalent -- NOTES.md section 8.
    cam, close_lights = mod.close_rig(root)
    scene.camera = cam
    mod.close_grade(scene)
    bpy.context.view_layer.update()
    close_tags = {L.name: "close" for L in close_lights}
    print("colour: view_transform=%s look=%s exposure=%+.3f"
          % (scene.view_settings.view_transform, scene.view_settings.look,
             scene.view_settings.exposure))

    rm3 = root.matrix_world.to_3x3()
    u = dirn(rm3, (1, 0, 0))
    v = dirn(rm3, (0, 1, 0))
    n = dirn(rm3, (0, 0, 1))
    cfwd = dirn(cam.matrix_world.to_3x3(), (0, 0, -1))
    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-cfwd).dot(n)))))
    print("OBLIQ panel face normal vs close-cam view axis %.4f deg" % obliq)
    assert (-cfwd).dot(n) > 0, "n must point AT the camera"

    # ------------------------------------------------ plate + the depth pass
    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"),
                         hide=live + txt)

    # ------------------------------------------------------------ geometry
    # exported at a ZERO reference so the frontend applies the plain angle, not
    # a delta.  build.py leaves the lever at LIFT_REST and the selector at
    # +SEL_ANGLE; the capture pose below puts them back.
    lp, sp, kp = (ctrl["lift"]["pivot"], ctrl["channel"]["pivot"],
                  ctrl["rail"]["pivot"])
    lp.rotation_euler = (0, 0, 0)
    sp.rotation_euler = (0, 0, 0)
    kp.location = (0.0, -0.102, 0.028)
    bpy.context.view_layer.update()
    T.export_glb(lift_objs, os.path.join(OUT, "lift.glb"))
    T.export_glb(hold_objs, os.path.join(OUT, "hold.glb"))
    # the pointer/grip TURN and the domes do NOT, so they are two glbs rather
    # than one scene the frontend has to take apart by node name.
    T.export_glb(sel_objs, os.path.join(OUT, "channel.glb"))
    T.export_glb(domes, os.path.join(OUT, "lamps.glb"))
    T.export_glb(rail_objs, os.path.join(OUT, "rail.glb"))

    # ---------------------------------------------------------- the anchors
    lift_hub = lp.matrix_world.translation.copy()
    hold_hub = root.matrix_world @ Vector((0.0, 0.062, 0.037))
    sel_hub = sp.matrix_world.translation.copy()
    # NO module declares `axis` on a rotate control.  FMM has NO face helper --
    # the working face IS the slot plane -- so there is no rake and the axis is
    # the root's own local +Z.  Emitted NEGATED so a POSITIVE angle is CLOCKWISE
    # on screen, the direction build.py's own tick scale runs (tick i sits at
    # (sin th, cos th) for th = -125..+125: lower-left -> top -> lower-right).
    # gt_hold_p000/p060.png is the check.
    hold_axis = -n
    sel_axis = n          # build.py sets rotation_euler.z directly: pasv +34
    lift_axis = u         # rotation_euler.x on the lever pivot
    rail_axis = u         # location.x on the skid pivot

    # ------------------------------------------------------ the text planes
    unit_adv = TM.measure_type(mod, 1.0)["adv"]      # advance per unit size
    planes = []
    for (nm, cx, cy, cz, hw, hh, nl, ncols, span, lead, top,
         align, inkmat) in PLAN:
        size = (span / ncols) / unit_adv
        LEAD = lead if lead else min(size, 1.6 * hh)
        tb = TM.type_block(mod, size, lead_m=LEAD,
                           left_m=(-span / 2.0 if align == "left" else -hw),
                           top_m=top, n_lines=nl, scale=1.0, align=align)
        tb["n_cols"] = ncols
        origin = root.matrix_world @ Vector((cx, cy, cz))
        planes.append({
            "name": nm,
            "origin": T.to3(origin), "u": T.to3(u), "v": T.to3(v),
            "n": T.to3(n), "half_w": hw, "half_h": hh, "type": tb,
            "local": [cx, cy, cz], "ink_mat": inkmat,
            "corners_px": {
                k: dict(zip(("x", "y"), mod.project(
                    scene, cam, origin + u * (hw * sx) + v * (hh * sy))))
                for k, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                                  ("bl", -1, -1), ("br", 1, -1))}})

    print("TYPE  metrics measured in Blender (FONT.size is NOT an em):")
    for p in planes:
        t, c = p["type"], p["corners_px"]
        ppm = math.hypot(c["tr"]["x"] - c["tl"]["x"],
                         c["tr"]["y"] - c["tl"]["y"]) / (2 * p["half_w"])
        print("   %-9s size %.6f -> adv %.6f (ratio %.6f)  cap %.6f  "
              "base %+.6f   %.1f px/m -> cap %.2f px, %d cols = %.1f px"
              % (p["name"], t["size_m"], t["adv_m"], t["adv_m"] / t["size_m"],
                 t["cap_m"], t["base_m"], ppm, t["cap_m"] * ppm,
                 t["n_cols"], t["n_cols"] * t["adv_m"] * ppm))
        need_h = (t["n_lines"] - 1) * t["lead_m"] / 2 + t["cap_m"] / 2
        assert p["half_h"] >= need_h - 1e-9, (p["name"], p["half_h"], need_h)
        assert p["half_w"] >= t["n_cols"] * t["adv_m"] / 2 - 1e-9, p["name"]
        assert len(POSE_TEXT[p["name"]]) == t["n_lines"]
        for s in POSE_TEXT[p["name"]]:
            assert len(s) <= t["n_cols"], (p["name"], s)

    # ------------------------------------------------------- THE POSE STATE
    # The needle has NO pivot in build.py -- the wide shot spins a flat sprite
    # in CSS -- so posing it means moving the three objects themselves.  They
    # are parented to `root` with an IDENTITY parent inverse, so `o.location`
    # is module-local and one 3x3 about the hub is the whole transform.  (A
    # temporary parent Empty was tried first and silently teleported the needle
    # off the panel: `npiv.matrix_world` is stale until the view layer is
    # updated, so `o.matrix_world = mw` solved against the wrong parent and
    # nothing warned.  gt_full_read.png showed an empty dial face.)
    HOLD_HUB_L = Vector((0.0, 0.062, 0.037))
    HOLD_REST = {o.name: (o.location.copy(), tuple(o.rotation_euler))
                 for o in hold_objs}

    def set_hold(deg):
        Rz = Matrix.Rotation(math.radians(-deg), 3, 'Z')
        for o in hold_objs:
            loc0, rot0 = HOLD_REST[o.name]
            o.location = Rz @ (loc0 - HOLD_HUB_L) + HOLD_HUB_L
            o.rotation_euler = (rot0[0], rot0[1],
                                rot0[2] + math.radians(-deg))

    C = ctrl["channel"]
    hold_deg = (mod.GAUGE_RANGE[0]
                + (mod.GAUGE_RANGE[1] - mod.GAUGE_RANGE[0]) * POSE_HOLD_PCT)
    rail_x = mod.RAIL_X0 + (mod.RAIL_X1 - mod.RAIL_X0) * POSE_RAIL_T

    def set_pose():
        lp.rotation_euler = (math.radians(POSE_LIFT_DEG), 0, 0)
        set_hold(hold_deg)
        sgn = -1 if POSE_CHANNEL == "pasv" else 1
        sp.rotation_euler = (0, 0, math.radians(-sgn * C["angle"]))
        lit = 0 if POSE_CHANNEL == "pasv" else 1
        for i, d in enumerate(domes):
            d.data.materials[0] = (C["mats"][POSE_CHANNEL] if i == lit
                                   else C["mats"]["off"])
        kp.location = (rail_x, -0.102, 0.028)
        bpy.context.view_layer.update()

    set_pose()

    # ---- uBias: the depth pass AGAIN, at the capture pose, with the LIVE
    # objects VISIBLE, so min(baked - live) is the smallest stand-off any live
    # prop has over the baked surface behind it.  Brief step 3 / trap 24; the
    # scratch file is deleted, it is not shipped.
    tmpb = os.path.join(OUT, "_depth_live.bin")
    liv = T.render_depth(scene, tmpb, hide=txt)
    gaps = []
    for y in range(H):
        for x in range(W):
            b = float(dep[y, x])
            if b >= 1e9:
                continue
            d = b - float(liv[y, x])
            if 1e-6 < d < 1.0:
                gaps.append(d)
    gaps.sort()
    os.remove(tmpb)
    if gaps:
        pct = lambda q: gaps[min(len(gaps) - 1, int(q * len(gaps)))]
        ubias = round(0.7 * gaps[0], 6)
        print("UBIAS  %d live-over-baked px   min %.6f  p1 %.6f  p5 %.6f  "
              "median %.6f  ->  ubias_m %.6f"
              % (len(gaps), gaps[0], pct(0.01), pct(0.05), pct(0.5), ubias))
    else:
        ubias = 0.0005
        print("UBIAS  no live-over-baked pixels; falling back to 0.0005")

    # -------------------------------------- the type, AFTER everything above
    # plate.png, depth.bin and every glb are already written, so this type can
    # appear in NONE of them (asserted).  Brief step 3, "a readout with no baked
    # type: make the type, in Blender, after everything else".
    stand_ins, per_plane = [], {}
    for p in planes:
        t = p["type"]
        cx, cy, cz = p["local"]
        objs = []
        for i, body in enumerate(POSE_TEXT[p["name"]]):
            if not body:
                continue
            py = cy + t["top_m"] - i * t["lead_m"]
            px = cx + (t["left_m"] if t["align"] == "left" else 0.0)
            o = mod.text("fmm_dom_%s_%d" % (p["name"], i), body, t["size_m"],
                         bpy.data.materials[p["ink_mat"]], (px, py, cz),
                         align=('LEFT' if t["align"] == "left" else 'CENTER'))
            o.parent = root
            objs.append(o)
        stand_ins += objs
        per_plane[p["name"]] = objs
    bpy.context.view_layer.update()
    assert not (set(stand_ins) & set(plate)) and not (set(stand_ins) & set(live))

    inks = {}
    for p in planes:
        fn = os.path.join(OUT, "gt_type_%s.png" % p["name"])
        T.render_colour(scene, fn, visible=per_plane[p["name"]])
        col, cnt = median_ink(fn)
        inks[p["name"]] = col or [122, 113, 107]
        p["ink"] = inks[p["name"]]
        print("INK   %-9s median rgb%s over %d covered px  (material %s)"
              % (p["name"], tuple(inks[p["name"]]), cnt, p["ink_mat"]))
    T.render_colour(scene, os.path.join(OUT, "gt_platen0.png"),
                    visible=stand_ins)

    # THE FRAME compare.py SCORES: exactly what the browser draws live, in
    # exactly the state __occ.pose() puts the page in.
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"), visible=live)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + live)

    # ---- SIGN CHECKS.  A wrong axis sign is silent in the export and obvious
    # in these two pairs: +60 deg must lean the needle RIGHT (the way the +125
    # tick runs), and 70 deg must drop the lever knob toward the divider.
    for tag, deg in (("p000", 0.0), ("p060", 60.0)):
        set_hold(deg)
        bpy.context.view_layer.update()
        T.render_colour(scene, os.path.join(OUT, "gt_hold_%s.png" % tag),
                        visible=hold_objs)
    for tag, deg in (("a30", 30.0), ("a70", 70.0)):
        lp.rotation_euler = (math.radians(deg), 0, 0)
        bpy.context.view_layer.update()
        T.render_colour(scene, os.path.join(OUT, "gt_lift_%s.png" % tag),
                        visible=lift_objs)
    for tag, tt in (("t0", 0.0), ("t1", 1.0)):
        kp.location = (mod.RAIL_X0 + (mod.RAIL_X1 - mod.RAIL_X0) * tt,
                       -0.102, 0.028)
        bpy.context.view_layer.update()
        T.render_colour(scene, os.path.join(OUT, "gt_rail_%s.png" % tag),
                        visible=rail_objs)
    set_pose()

    # ---- MEASURED: what crosses each declared rect, live or baked, over the
    # module's whole range.  The audit's harness was not kept (brief correction
    # 11); this rebuilds the useful half of it, and it is what says the dial
    # face is unusable and the nameplate is not.
    dg = bpy.context.evaluated_depsgraph_get()
    liveset = set(o.name for o in live)
    cam_o = cam.matrix_world.translation
    saved = {o.name: o.hide_render for o in T.renderables(scene)}
    for o in stand_ins:
        o.hide_render = True          # the DOM type is not an occluder

    def probe(cx, cy, cz, hw, hh, N=11):
        cov, hits = 0, {}
        for i in range(N):
            for jj in range(N):
                lx = cx + hw * (2 * i / (N - 1) - 1)
                ly = cy + hh * (2 * jj / (N - 1) - 1)
                p = root.matrix_world @ Vector((lx, ly, cz))
                d = p - cam_o
                ok, loc, nrm, idx, ob, mw = scene.ray_cast(
                    dg, cam_o, d.normalized(), distance=d.length - 0.001)
                if ok:
                    cov += 1
                    k = ("LIVE " if ob.name in liveset else "baked ") + ob.name
                    hits[k] = hits.get(k, 0) + 1
        return cov, hits

    POSES = [(lf, rl, hd)
             for lf in (30.0, 50.0, 70.0)
             for rl in (mod.RAIL_X0, 0.055, mod.RAIL_X1)
             for hd in (-125.0, 0.0, 125.0)]
    probe_rows = []
    targets = ([(p["name"], p["local"][0], p["local"][1], p["local"][2],
                 p["half_w"], p["half_h"]) for p in planes]
               # the plane the dial-face rule forbids, measured so the refusal
               # is a number and not an opinion
               + [("DIALFACE(not declared)", 0.0, 0.062, 0.031, 0.050, 0.050)])
    for (nm, cx, cy, cz, hw, hh) in targets:
        worst, agg = 0, {}
        for (lf, rl, hd) in POSES:
            lp.rotation_euler = (math.radians(lf), 0, 0)
            kp.location = (rl, -0.102, 0.028)
            set_hold(hd)
            bpy.context.view_layer.update()
            cov, hits = probe(cx, cy, cz, hw, hh)
            worst = max(worst, cov)
            for k, c in hits.items():
                agg[k] = max(agg.get(k, 0), c)
        anylive = any(k.startswith("LIVE") for k in agg)
        probe_rows.append({"rect": nm, "worst_covered": worst,
                           "of": 121, "live": anylive, "hits": agg})
        print("PROBE %-22s worst %3d/121 covered   live=%s  %s"
              % (nm, worst, anylive, agg))
    set_pose()
    for o in T.renderables(scene):
        if o.name in saved:
            o.hide_render = saved[o.name]
    for o in stand_ins:
        o.hide_render = True

    # ------------------------------------------------------------- depth QA
    # every probe on a VISIBLE STATIC surface (brief trap 7)
    rows = T.verify_depth(scene, cam, dep, [
        ("panel face", root.matrix_world @ Vector((0.100, -0.020, 0.0145))),
        ("manifest card face", root.matrix_world @ Vector((-0.105, 0.082, 0.022))),
        ("gauge nameplate face", root.matrix_world @ Vector((0.000, -0.032, 0.0185))),
        ("data tray face", root.matrix_world @ Vector((-0.176, -0.104, 0.01695))),
        ("gauge dial face", root.matrix_world @ Vector((0.030, 0.062, 0.031))),
    ])
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-22s want %.5f  got %.5f  err %+.6f" % (nm, want, got, err))

    # ------------------------------------------------------------ hotspots
    def bb(objs, pad=8):
        return clamp_rect(mod.bbox_rect(scene, cam, objs, pad=pad), W, H)

    rects = []
    for deg in (mod.LIFT_MIN, mod.LIFT_MAX):
        lp.rotation_euler = (math.radians(deg), 0, 0)
        bpy.context.view_layer.update()
        rects.append(mod.bbox_rect(scene, cam, lift_objs, pad=8))
    hs_lift = clamp_rect(mod.union(rects), W, H)
    rects = []
    for xx in (mod.RAIL_X0, mod.RAIL_X1):
        kp.location = (xx, -0.102, 0.028)
        bpy.context.view_layer.update()
        rects.append(mod.bbox_rect(scene, cam, rail_objs, pad=8))
    hs_rail = clamp_rect(mod.union(rects), W, H)
    set_pose()
    hs_hold = bb(ctrl["hold"]["dial"], pad=6)
    hs_chan = bb(sel_objs + domes, pad=8)

    # keep them disjoint so the page never arbitrates by DOM order
    def clip_left_of(a, b):
        if a["x"] + a["w"] > b["x"] and a["x"] < b["x"]:
            a["w"] = max(1, b["x"] - a["x"] - 1)
    clip_left_of(hs_lift, hs_hold)
    clip_left_of(hs_hold, hs_chan)

    hold_px, hold_py = mod.project(scene, cam, hold_hub)

    # ---------------------------------------------------------- scene.json
    j = {
        "render": {"w": W, "h": H},
        "camera": T.cam_json(scene, cam),
        "lights": T.lights_json(scene, close_tags),
        "world_bg": list(scene.world.node_tree.nodes["Background"]
                         .inputs[0].default_value),
        "colour": {"view_transform": scene.view_settings.view_transform,
                   "look": scene.view_settings.look,
                   "exposure": scene.view_settings.exposure},
        "light_gain": LIGHT_GAIN,
        "env_intensity": 0.0,
        "raytrace": 1,
        "scale": 1.0,
        "ubias_m": ubias,
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "face": {"u": T.to3(u), "v": T.to3(v), "n": T.to3(n)},
        "props": {
            "lift": {
                "glb": "lift.glb", "kind": "frames",
                "label": ctrl["lift"]["label"],
                "nodes": [o.name for o in lift_objs],
                "hub": T.to3(lift_hub), "axis": T.to3(lift_axis),
                "range": [mod.LIFT_MIN, mod.LIFT_MAX],
                "frames": ctrl["lift"]["frames"],
                "rest_deg": mod.LIFT_REST,
                "hotspot": hs_lift},
            "hold": {
                "glb": "hold.glb", "kind": "rotate",
                "label": ctrl["hold"]["label"],
                "nodes": [o.name for o in hold_objs],
                "hub": T.to3(hold_hub), "axis": T.to3(hold_axis),
                "range": list(ctrl["hold"]["range"]),
                "pivot_px": {"x": hold_px, "y": hold_py},
                "hotspot": hs_hold},
            "channel": {
                "glb": "channel.glb", "lamps_glb": "lamps.glb",
                "kind": "states",
                "label": ctrl["channel"]["label"],
                "states": list(ctrl["channel"]["states"]),
                "nodes": [o.name for o in sel_objs],
                "domes": [o.name for o in domes],
                "hub": T.to3(sel_hub), "axis": T.to3(sel_axis),
                # build.py: rotation_euler.z = -sign*angle, sign -1 for pasv
                "angle_deg": {"pasv": ctrl["channel"]["angle"],
                              "port": -ctrl["channel"]["angle"]},
                "lit": {"pasv": 0, "port": 1},
                "mats": {k: m.name for k, m in ctrl["channel"]["mats"].items()},
                "hotspot": hs_chan},
            "rail": {
                "glb": "rail.glb", "kind": "frames",
                "label": ctrl["rail"]["label"],
                "nodes": [o.name for o in rail_objs],
                "axis": T.to3(rail_axis), "rest_x": 0.0,
                "range": [mod.RAIL_X0, mod.RAIL_X1],
                "frames": ctrl["rail"]["frames"],
                "hotspot": hs_rail},
        },
        "text_planes": planes,
        "ink": inks,
        "readout_text": [POSE_TEXT[p["name"]] for p in planes],
        "capture_pose": {"lift_deg": POSE_LIFT_DEG, "hold_pct": POSE_HOLD_PCT,
                         "hold_deg": hold_deg, "channel": POSE_CHANNEL,
                         "rail_t": POSE_RAIL_T, "rail_x": rail_x},
        "rake_deg": {"working_face_off_slot_plane": 0.0,
                     "obliquity_to_close_cam": obliq},
        "depth_verify": [{"name": a, "analytic": b, "baked": c, "err": d}
                         for a, b, c, d in rows],
        "rect_probe": probe_rows,
        "tris": {"live": 2152, "static": 3512},
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
#         --python live3d/pipeline/export_fmm.py -- refit
#
# main() above rebuilds the shell and RE-RENDERS plate.png, depth.bin and all
# nine gt_*.png.  Running it would invalidate every number in
# live3d/RESULTS.md and modules/FMM/NOTES.md.  This entry point does none of
# that: it builds the port ALONE IN AN EMPTY SCENE, in WORLD coordinates,
# writes assets/FMM/refit.glb and merges a "refit" block into the existing
# scene.json.  Nothing else in assets/FMM/ is opened for writing.
# FIX_UPLOAD.md section 0, decision 3.
#
# root_scale IS 1.0 HERE and is not passed.  FMM's own `scale` is 1 anyway,
# but the rule is the rule: this path clears the scene and authors from
# solve_anchor()'s world-space frame, so there is no root to be inside.
# `refit_port.check_root_scale()` refuses a non-unit value in an empty scene
# (FIX_UPLOAD 12.15 item 2 -- MQB's 0.70 would have shipped the port 1.43x
# too big with nothing printed and nothing failing).
#
# THE ANCHOR: (359, 677) TABLED, (600, 681) SHIPPED -- and the 241 px is not
# a nudge, it is a different decision made on evidence the table's own sweep
# did not have.  Three measurements move it, in this order:
#
# 1. THE BAND.  `refit_port.py FMM 359 677 57 --sweep-y 600,714` refuses
#    everything from y 606 to y 670 and everything from y 692 down, and accepts
#    a continuous band from **y 672 to y 690**.  Both walls are real features:
#      * ABOVE, the DATA CHANNEL deck's brass rail bed ends in a hard depth
#        step at y = 642 -- 0.7692 m at y 640 against 0.7833 m at y 644, i.e.
#        14 mm nearer the camera over four rows.  Any anchor above y 672 puts
#        the port's own FOOT samples on the step and the solver asks for a
#        4-13 mm seat against its 3.5 mm cap.  FIX_UPLOAD 12.3's KVS fillet,
#        arriving on a fourth module as a step.
#      * BELOW, from y 692 the envelope runs off the bottom of the 720 frame.
#    y = 681 is the middle of it: the foot clears the step by 7 px and the
#    envelope's lower edge clears the frame by 10 px.  **The tabled y is
#    right and the tabled size is right** -- unlike KVS's (a fillet) and MQB's
#    (62 px on a 52 px apron), FMM's tabled anchor BUILDS AS TABLED.
#
# 2. THE CARRIER IS CONVEX IN X, AND THAT LIMITS HOW LONG THE SERVICE RAIL CAN
#    BE.  The fascia below the panel is featureless and continuous across the
#    whole 1280 px frame, so x looked free.  It is not.  Walking the port's own
#    fitted plane along +u and reading `depth.bin` at each pixel:
#
#        along +u from the anchor    0     60    120    200    300    400    600 px
#        plane in front of baked  +1.17  +1.25  +0.83  +0.37  -0.95  -2.53  -7.11 mm
#
#    A rail lying in the port's fitted plane is BEHIND the baked surface from
#    about +250 px and 7 mm behind at +600 px, where the depth composite
#    deletes it.  `solve_mast()` will ramp it -- but a rail whose far end
#    stands 6-7 mm off its own carrier is a shelf cantilevered in front of the
#    instrument, which is exactly what MTA rejected.  **So the mast has to sit
#    within roughly 250 px of the port**, and therefore the docket must not
#    land in the 250 px to the port's right.  This is
#    STATUS_AT_A_GLANCE 6.5 item 5 (the rail ramp) deciding the PORT's anchor
#    rather than the mast's, which is a seam neither document draws.
#
# 3. THE DOCKET.  `refit.js`'s solver is deterministic and cheap to
#    interrogate, so it was interrogated rather than reasoned about: the port's
#    published `centre`/`hotspot` were injected at 27 anchors from x 140 to
#    x 1140 and the real docket read off the real page at each (a 520 x 318
#    panel; its y is CLAMPED to 390 at every one of them, because the port is
#    at the bottom of the frame and the panel is 318 tall).  Abridged:
#
#      anchor   docket x   control centre buried   DATA RAIL   port covered
#        180      217.1    none                      47.6 %       3.1 %
#        340      378.1    DATA RAIL                 70.9 %       1.9 %
#      **359**    397.2    **DATA RAIL**             73.7 %       1.8 %   <- tabled
#        460      498.8    DATA RAIL                 75.3 %       1.2 %
#        540       12.0    none                      17.9 %      36.7 %
#        580       19.6    none                      19.0 %       0.0 %
#      **600**     39.7    **none**                  22.0 %       0.0 %   <- shipped
#        620       59.9    none                      24.9 %       0.1 %
#        820      748.0    DATA RAIL                 50.8 %       9.9 %
#
#    **At the tabled anchor the docket buries the centre of `DATA RAIL`** --
#    FMM's largest control, 691 x 97 px, the one carrying the crate the player
#    drags -- and 73.7 % of it.  That is precisely the defect FIX_UPLOAD 12.15
#    item 3 was written to prevent ("a control whose centre is covered costs
#    its WHOLE area"), and unlike KVS, which "cannot be helped", FMM CAN be:
#    the solver's own score flips to a clean answer once the port sits far
#    enough right that the left-hand candidate stops clamping over it, which
#    happens at cx = 572.  x = 600 is 28 px past that, on a stable plateau.
#
#    WHAT IT COSTS, SAID OUT LOUD.  With the docket on the LEFT it covers the
#    `data` readout rect (197..397 x 493..610) completely, where at the tabled
#    anchor it covered the one-line `hold` nameplate instead.  That trade is
#    the design's own and it is not close: 12.15 item 3 weights a buried
#    control CENTRE at the control's whole area and calls readouts "merely nice
#    to keep", and "the instrument stays visible beside it" was corrected to
#    "OPERABLE beside it".  With the port at 600 every one of FMM's four
#    control centres answers `document.elementFromPoint` with itself while the
#    port is open, and the crate at x 768..871 is draggable throughout.  There
#    is NO anchor that covers neither readout: the docket is 520 px wide, the
#    two rects are 180 px apart, and its y is clamped, so it always crosses
#    one of them.
#
# THE WINDOW.  90 x 50 px of pure fascia below the step.  Passed explicitly on
# the strength of FIX_UPLOAD 12.15 item 8's "pass --window on every module".
# The DEFAULT window here happens to be clean (the step is 7 px above it), but
# the carrier is CURVED IN X and that is what the window has to be kept off:
# fitted over x 556..646 the residual max is 0.0000003 m, over a window 220 px
# wide it is 0.0002310 m -- 770x -- at an anchor that looks nowhere near an
# edge.  MTA found this on a frame rail; FMM finds it on curvature.
#
# THE OBLIQUITY IS THE DECLARED ONE, ALMOST EXACTLY.  The carrier fits at
# 11.94 deg against FMM's declared face normal at 11.80 -- the two normals are
# 1.57 deg apart.  FIX_UPLOAD 12.2's "the carrier is 45 deg off the declared
# face" is a KVS fact and nothing more (MQB 0.00, MTA 8.73, FMM 1.57).
#
# W = 28.97 mm, not the ~26 mm the section 2 table implies: the table takes
# px/m at the READOUT plane and this carrier is at 0.777-0.784 m.
# FIX_UPLOAD 12.5, holding on a fourth module.
#
# ---- THE SEAT, AND THE ONE PLACE THIS MODULE BREAKS THE SHARED DEFAULT -----
# `solve_anchor(seat_margin=)` is in MULTIPLES OF `ubias_m`, and FMM's
# `ubias_m` is 1e-06 -- the fleet's smallest by 400x, and it is small because
# FMM is `ubias.py`'s EMERGING case (lamp domes seated in their brass rings,
# skid trucks running through the rail bed, so the gap sweeps continuously
# through zero and the minimum is a rim artefact).  The shipped 1e-06 is that
# module's own sweep optimum, NOT a stand-off.  At the shared default of
# 2.5 x ubias_m the port would be seated **0.059 mm** off the fascia, of which
# 2.5 MICRONS is margin.
#
# That is not enough, and it is measured rather than argued:
#   * the baked depth here changes by **0.104 mm PER SCREEN PIXEL** down the
#     fascia (0.78040 m at y 676 against 0.77958 at y 684, at x 359).  A 2.5 um
#     margin is 1/40 of ONE PIXEL of depth gradient: any half-pixel
#     disagreement between the rasteriser that wrote depth.bin and the one
#     drawing the port deletes bands of it, silently.  Trap 24.
#   * `live_depth.py FMM` reports an eroded minimum gap of **0.000681 m**.  A
#     port seated at 0.059 mm would become the new minimum of that set and
#     move the number the module's own `ubias_m` is derived from by 11x --
#     STATUS_AT_A_GLANCE 6.5 item 5's KVS rail lesson arriving through the
#     seat instead of through the ramp.
# So the seat is solved at **seat_margin = 1200**, giving **1.252 mm** -- 1.20
# of which is margin, comfortably above the eroded minimum and squarely in the
# fleet's band (KVS 1.71 mm, MQB 1.225 mm, MTA 1.15-1.28 mm).  On an 11.94 deg
# carrier that costs 0.26 mm of parallax, 0.45 px on screen.
# **The generalisation for the remaining modules: `seat_margin` and
# `lift_margin` are only stand-offs where `ubias_m` is a stand-off.  Read
# `live_depth.py`'s DISTRIBUTION first; on an EMERGING module the multiplier
# is meaningless and the shared defaults produce a micron.**
FMM_REFIT = dict(px=600, py=681, port_px=57,
                 # pure fascia below the deck step, narrow enough in x that
                 # the fascia's curvature is not in the fit -- see above
                 carrier_window=(556, 646, 655, 705),
                 label="REFIT",
                 # The size mark is 532 triangles for a ~3 px smear; cut on
                 # KVS, MQB and MTA for the same reason (FIX_UPLOAD 12.9).
                 mark=None,
                 # The 1.3 W riveted sub-base is for FEATURELESS bulkhead
                 # (LOG, MTA).  FMM's fascia IS featureless -- but the DATA
                 # CHANNEL deck's brass rail bed runs the full width 39 px
                 # above the port, which is 0.68 W, i.e. inside the "~1 W"
                 # FIX_UPLOAD 12.14 item 3 draws the line at, and it is
                 # exactly the structure section 1.4 says the sub-base
                 # substitutes for.  A 1.3 W footprint is also 74 px tall and
                 # would climb the step.  Off, as on KVS and MQB.
                 sub_base=False, service_rail=True,
                 seat_margin=1200.0)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(FMM_REFIT)
    A = RP.solve_anchor(CODE, K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"],
                        seat_margin=K["seat_margin"])
    P = RP.build("fmm_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export(CODE, A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))


# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_fmm.py -- mast
#
# Like `refit`: main() re-renders plate.png, depth.bin and all nine gt_*.png
# and would invalidate every number in live3d/RESULTS.md and
# modules/FMM/NOTES.md.  This entry point builds the mast ALONE IN AN EMPTY
# SCENE, in WORLD coordinates (so `root_scale` is 1.0 here for the same reason
# it is 1.0 for the port), writes assets/FMM/mast.glb and merges a "mast" block
# into the existing scene.json.  Nothing else in assets/FMM/ is opened for
# writing.
#
# IT IS ON THE PORT'S OWN SERVICE RAIL, CONTINUOUS, AT THE PUBLISHED FLOOR.
# STATUS_AT_A_GLANCE 11.2's seam works here unmodified, which is the first time
# in four modules: KVS had to walk out to 3.2 W and MQB to 12.2 W to get past
# their own dockets, and MTA could not use the rail at all.  On FMM the port's
# anchor was chosen so that the docket lands to the port's LEFT (see the
# 27-anchor table above FMM_REFIT), so everything from `free_from_m` = 1.5 W
# rightwards is clear structure and the mast mounts at the floor.  Measured on
# the running page with the port open: the docket owns x 39.7..559.7 and the
# mast's hotspot starts at x 673.7 -- a 114 px gutter, 0 px2 either way.
#
# WHY THE RAIL IS CONTINUOUS AND NOT A STUB.  MQB had to cut its rail to a stub
# because a continuous one crossed the module's own baked nameplate.  FMM's
# fascia carries nothing at all in the rail's band: over x 600..900, y 672..692
# `plate.png` has luma mean 69.6, sd 2.18, min 64.2, max 76.4 -- a smooth
# gradient with no lettering and no structure.  So the rail runs from the
# port's own built end and the pair reads as 11.2 intends, one rail with a
# fitting at each end.
#
# THE RAMP IS NOT FLAT, AND FMM IS THE SECOND MODULE WHERE IT FIRES.
# STATUS_AT_A_GLANCE 6.5 item 5 is a property of LONG fittings on CURVED
# carriers; it did not fire on MQB (a plane) or on MTA (no rail).  FMM's fascia
# is CONVEX in x -- walking the port's own fitted plane along +u and reading
# depth.bin, the plane is 1.17 mm in front of the baked surface at the port,
# +0.37 mm at 200 px, 0.95 mm BEHIND at 300 px and 7.1 mm behind at 600 px.
# `solve_mast()` solves one straight ramp over the run and gets
# **0.000029 -> 0.001620 m**, and that is also the measurement that decided the
# PORT's anchor (a mast 600 px down the rail would need a 6-7 mm cantilever;
# see item 2 above FMM_REFIT).
#
# THE FOUR DECISIONS, all four measured.
#
#   --rakes    RAKE 0.  FMM's rake table has a minimum at 15 deg (3.20 deg
#              face obliquity against the carrier's own 11.80) and it is a
#              trap: obliquity is not the criterion.  The criterion is
#              STATUS_AT_A_GLANCE 16.2's -- read `px_per_m_carrier`, v against
#              n.  KVS raked 45 deg because ITS carrier's v and n project
#              within 7.6 deg of one screen direction (1846 vs 1279 px/m), so
#              a fitting lying flat on it has no readable second axis.  FMM is
#              the OPPOSITE extreme: v 1959.5 px/m against n **57.8** px/m, a
#              ratio of 34x, because an 11.80 deg carrier points its normal
#              almost straight at the lens.  There is no second axis to
#              recover and a rake can only take length out of the axis that
#              works.  At rake 0 the mast's own two axes project at A 1916.2
#              and B 1959.5 px/m -- unforeshortened in both directions, which
#              is the thing KVS's 45 deg was buying.  Fleet so far: KVS 45,
#              MQB 0, MTA 0, FMM 0.
#
#   --px 180   swept, and there is a CLIFF, not a gradient:
#
#                  mast_px  envelope y      lift        grad px
#                    150    649.5..693.1    1.14 mm     10.6
#                    160    647.4..693.9    1.27 mm     11.3
#                    170    645.3..694.7    1.46 mm     12.0
#                    180    643.1..695.6    1.59 mm     12.7   <-- shipped
#                    190    640.4..696.9   17.48 mm     13.7
#                    200    638.3..697.7   17.50 mm     14.4
#
#              The DATA CHANNEL deck's brass rail bed ends at row 642 and
#              stands 0.7691 m against the fascia's 0.7845 -- 15 mm nearer the
#              camera.  At 190 px the envelope's top edge crosses it and
#              `_solve_lift()` stops being careful and starts telling us the
#              fitting overhangs something 15 mm nearer than its own mount:
#              1.59 mm -> 17.48 mm in one 10 px step.  That is MTA's 24.2 mm
#              answer arriving as a cliff instead of a slope.  180 px is the
#              largest that stays wholly on the fascia; its top edge sits
#              1.1 px below the step and every hull sample the lift solver
#              takes reads the fascia (carrier depth 0.7791..0.7860, never
#              0.769).  Verified by looking at the top edge at 6x in the
#              vane-flying pose, which is the tallest the assembly ever is.
#
#   --m 8      the COUNT of file-management-module/vuln_tests/NN_*.py, never
#              max(NN) -- STATUS_AT_A_GLANCE 9.4 rule 4, and FMM is the module
#              that rule was written for: the files are 01, 02, 04, 05, 07,
#              08, 09, 10, so there are EIGHT and max(NN) is TEN.  Gaps at 03
#              and 06.
#
#   numbers    OFF.  The lamp pitch here is 12.7 px, against KVS's 18.0 where
#              the engraved numbers were already cut for ~2,600 triangles of
#              9 px lettering.  The catalogue list in the hover panel carries
#              the identity instead, in the same order as the lamps.
#
# ---- THE LIFT, AND THE SAME ubias_m PROBLEM THE PORT'S SEAT HAS ------------
# `lift_margin` is in multiples of `ubias_m` exactly as `seat_margin` is, and
# FMM's `ubias_m` is 1e-06, so the shared default of 2.5 asks the mast to clear
# the baked fascia by **2.5 microns** -- and at 150 px it answers `lift 0.0`,
# i.e. the assembly's closest point is already within microns of the plate.
# The fascia's depth changes by 0.104 mm PER SCREEN PIXEL, so that margin is
# 1/40 of one pixel of gradient and half a pixel of rasteriser disagreement
# deletes bands of the fitting.  `lift_margin = 1200` gives **1.59 mm**, which
# is the same 1.2 mm of real margin the port's seat gets and the same band the
# rest of the fleet lands in (KVS 9.04 mm over a moulding, MQB 0.0 on a plane,
# MTA 1.66 mm).  It also keeps the mast's own underside clear of
# `live_depth.py`'s eroded minimum of 0.000681 m, so `ubias_m` does not move.
FMM_MAST = dict(mast_px=180, rake_deg=0.0, m=8, kind="defensive",
                numbers=False,
                # the mast's own footprint on the fascia, for the carrier
                # printout.  On the rail route u/v/n come from the PORT's
                # frame, so this only re-fits the reported normal -- but
                # FIX_UPLOAD 12.15 item 8 says pass it on every module and the
                # residual it prints is what says the fit is on one surface.
                carrier_window=(674, 885, 648, 700),
                # see the block above: 2.5 x 1e-06 is 2.5 microns on this
                # module and the fascia moves 104 microns per screen pixel.
                lift_margin=1200.0)


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(FMM_MAST)
    A = SMT.solve_mast(CODE, mast_px=K["mast_px"], rake_deg=K["rake_deg"],
                       m=K["m"], kind=K["kind"], numbers=K["numbers"],
                       carrier_window=K["carrier_window"],
                       lift_margin=K["lift_margin"])
    P = SMT.build("fmm_mast", A["frame_blender"], A["carrier_blender"],
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
