"""
LIVE-3D EXPORT — PKT close-up  ("The Signal Harpoon", packet transmitter).

A thin layer on top of three-exploration/pipeline/transliterate.py, following
live3d/CONVERSION_BRIEF.md.  The module's REAL build.py is imported in place by
live3d/pipeline/module_loader.py, so there is no PKT snapshot to go stale.

PKT is the fleet's first OCCLUDED module (live3d/audit/OCCLUSION_AUDIT.md):
every one of its readouts is cropped by STATIC baked geometry, and nothing that
moves ever crosses one.  That is precisely what the split pass is for, and this
export is what makes the split non-vacuous:

    verdict rect   49/49 audit samples behind pkt_hdr_bar (2.4 mm)
    catch rect     13/49 behind the aperture rails pkt_ap_rail_1/2 (18.7 mm)
    target rect    12/49 behind pkt_scope_bezel / pkt_scope_inlay (10-12 mm)
    payload name   10/10 behind pkt_breech_frame (1.1 mm) -- INVISIBLE today

    plate.png       shell + PKT STATIC parts.  R["static"] exists on PKT and
                    partitions cleanly (survey: static n control-owned = 0), and
                    unlike MTA it contains NO content type, so no subtraction is
                    needed -- but it is asserted rather than assumed.
                    R["far_only"] (the seven pkt_farticks_* printed-tape bars)
                    is in neither `static` nor any control and is FAR-VIEW ONLY:
                    build.py's own close shot drops it, and so does this.

    target.glb      the knurled azimuth hand-wheel + index pointer  -- rotates
    payload.glb     the 8-chamber munition drum                     -- rotates
    charge.glb      capacitor lever + 4 vacuum tubes + 5 redline pips
    arm.glb         break-glass cage + master-arm toggle + 2 lamps
    fire.glb        the plunger, and the muzzle flash
    catch.glb       the return-line platen + two spools             -- advances
    verdict.glb     3 IMPACT lamps + the tinted header bar

    All seven controls become LIVE.  Three of them ship as `kind: frames` --
    payload, charge, catch -- and BRIEF step 2 rule 1 is explicit that frames
    are a baked approximation of movement.  Here they are not even N discrete
    meshes (MQB's scope, MTA's capsule): all three frame sets are ONE object set
    driven by a single continuous parameter (a drum angle, a lever slide, a
    paper advance), so the conversion is exact rather than a cycle of stills.

    NOT EXPORTED AT ALL: the content type.  8 FONT objects,
    pkt_payload_txt_<0..7>, the munition class in the breech window, are values
    a player reads, so per README section 12 they become DOM and are excluded
    from the plate, from the depth pass and from every glb.  STAMPED lettering
    stays geometry: the nameplate, the PKT codeplate, CONTACTS, AZIMUTH,
    CHARGE, CAPACITOR BANK, EMITTER, ARM, ARMED, INTLK, FIRE, IMPACT, TEAR OFF
    and RETURN LINE.

    text_planes     FOUR readout rects.  Three of them are the module's own
                    declared `overlay_pts` quads (target / catch / verdict) and
                    the fourth is the payload drum's munition class, which the
                    audit says has no declared home.  ALL FOUR ARE PUSHED PROUD
                    of their carriers -- see PLANES below; the verdict and
                    payload ones are pushed IN FRONT OF AN OCCLUDER, which is
                    the authoring error the audit found made visible and then
                    fixed (BRIEF step 4: "nudge the plane forward, do not
                    disable the split").

    gt_platen0.png  Blender's own render of the four readouts' type.  THREE OF
                    THE FOUR HAVE NO BAKED TYPE AT ALL -- build.py leaves the
                    aperture, the designation band and the header bar
                    deliberately empty because their content is unknown at
                    render time -- so this export CREATES those FONT objects,
                    with the module's own text() helper, its own font, its own
                    materials and the sizes declared below, purely to render
                    them.  They are made AFTER plate.png / depth.bin / the glbs
                    and are in none of them.  That is what gives check_text.py
                    and verify_assets.py something to score on all four planes,
                    and it is how each readout's ink colour is MEASURED off
                    Blender rather than picked (BRIEF section 7 rule 7).

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_pkt.py

    PKT_CONTROL_PLANE=1 additionally writes assets/PKT/scene_control.json, a
    byte-for-byte copy of scene.json carrying ONE extra readout plane at the
    verdict rect's ORIGINAL, un-nudged position -- i.e. inside the LIVE
    pkt_hdr_bar.  Swapping it in exercises check_occlusion.py's LIVE half with
    real module geometry rather than a synthetic control plane.  See NOTES.md.
"""
import bpy, math, os, sys, json, collections
import numpy as np
from mathutils import Vector

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
CODE = "PKT"
OUT = os.path.join(LIVE3D, "assets", CODE)

# --------------------------------------------------------------- THE POSE
# The one resting state the whole verification chain is scored in.  It must be
# identical here, in gt_full_read.png and in module.js's poseForCapture(), or
# check/compare.py measures the mismatch instead of the renderer.
#
# It is a console after ONE completed engagement, deliberately, so that all
# four readouts carry a real value: MTA rests with five envelopes queued and
# KVS rests with a printed transcript for the same reason.  An empty aperture
# and an empty header would make check_text.py a test of two planes.
POSE_BEARING = -21.0        # deg; the wheel is at the LISTENING POST contact
POSE_PAYLOAD = 0            # drum index -> PAYLOADS[0]
POSE_CHARGE = 0             # capacitor bank idling
POSE_ARM = "safe"
POSE_FIRE = "ready"
POSE_CATCH = 0              # paper advance frame
POSE_VERDICT = "hit"

# -------------------------------------------------- THE FOUR READOUT PLANES
# Everything below is in the module's PLAN units (build.py section "layout
# table"); mod.F(x, y, h) and mod.K(len) apply the module's own S = 1.15 to get
# world metres, so nothing here has to know about the scale.
#
# `h` is the stand-off along the raked face normal, and every one of the four is
# chosen against a MEASURED carrier front face rather than guessed:
#
#   target   pkt_scope_readout   top face h = 0.0090   -> plane 0.0094  (+0.46 mm)
#   payload  pkt_breech_frame  front face h = 0.0150   -> plane 0.0158  (+0.92 mm)
#            (the type itself is authored at h = 0.0135, i.e. INSIDE that solid
#             box and inside pkt_breech_well as well -- which is exactly why the
#             module's own baked sprite close_payload_4.png shows a drum face
#             with no text on it, and why the audit reads 10/10 occluded)
#   catch    pkt_platen        front face h = 0.0172   -> plane 0.0215 (+4.9 mm,
#            the module's own declared ap_pts stand-off, kept)
#   verdict  pkt_hdr_bar       front face h = 0.0350   -> plane 0.0356 (+0.69 mm)
#            (the module declares 0.0330, which is INSIDE the bar: BRIEF step 4)
#
# The shader's epsilon is RELATIVE (s > 1.0001), which at PKT's ~1.4 m close
# camera is 0.14 mm, so every one of these clears it by at least 3x.
# `top` is the FIRST LINE'S ORIGIN above the rect centre, in plan units.  It is
# explicit rather than "centre the block" for the catch aperture, because the
# aperture is NOT uniform: `pkt_ap_shade`, the dark strip where the paper
# recedes into the machine under the top rail, occupies plan y 0.022..0.040 and
# takes the plate there from luma 191 down to 57.  A block centred in the rect
# puts its first line straight across that edge -- legible-ish, but it also
# makes verify_assets.py's local ink/paper ring read -13.2 luma levels on that
# one line (measured) purely from the plate's own hard feature.  So the block is
# hung from plan y 0.000 instead and every line lands on flat paper.
PLAN = [
    # name       cx        cy        h       half_w  half_h  size    lead    top    lines cols align
    ("target",  -0.310,   -0.112,   0.0094,  0.059,  0.010,  0.0215, 0.0,    None,   1,  14, "center"),
    ("payload", -0.090,   -0.030,   0.0158,  0.064,  0.012,  0.0270, 0.0,    None,   1,  12, "center"),
    ("catch",    0.264,   -0.030,   0.0215,  0.104,  0.070,  0.0200, 0.0107, 0.030,  9,  28, "left"),
    ("verdict",  0.264,    0.074,   0.0356,  0.104,  0.010,  0.0195, 0.0,    None,   1,  12, "center"),
]
# which module material each readout's ink is, and therefore what Blender
# renders it as.  MEASURED off gt_type_<name>.png, never chosen.
INK_MAT = {"target": "phosphor", "payload": "hazard",
           "catch": "ink", "verdict": "ink"}


def dirn(m3, v):
    """Transform a DIRECTION by a rotation matrix and normalise."""
    return (m3 @ Vector(v)).normalized()


def median_ink(path):
    """The ink colour, measured off Blender's own render of THIS module's type.

    MEDIAN over alpha > 0.5, with NO colour transform (BRIEF section 7 rule 7).
    Blender hands `image.pixels` back ALREADY DISPLAY-ENCODED for an 8-bit sRGB
    PNG, so an sRGB encode on top returns a plausible-looking wrong colour; and
    on small type nothing is fully opaque, so a "most common fully opaque pixel"
    rule returns the empty set.  Cross-checked against the PNG bytes below."""
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
    main_cam = scene.camera
    scene.render.film_transparent = True
    W, H = scene.render.resolution_x, scene.render.resolution_y
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    mod = load_module(CODE)
    R = mod.add_props(P, mats)
    mine, ctrl, root = R["all"], R["controls"], R["root"]
    shell_meshes = [o for o in T.renderables(scene) if o not in set(mine)]

    # ------------------------------------------------------- close-up rig
    # PKT DOES have a close_rig(), contrary to the BRIEF's fleet table, which
    # lists KVS/MTA/PKT as "builds the camera inline in main()".  What is true
    # is that its signature is close_rig(scene, root, objs, main_cam) -- it
    # needs the object list and the WIDE camera, because the close camera is
    # placed along the pilot's own sight-line -- so survey_modules.py cannot
    # call it and falls back to the +-3 deg wide-ray estimate.  Called here
    # exactly as build.py's main() calls it, at the module's REST state, so the
    # close-up frames the console identically to the shipped baked close plate.
    close_objs = [o for o in R["far"] if o not in set(R["far_only"])]
    cc, close_lights = mod.close_rig(scene, root, close_objs, main_cam)
    close_tags = {L.name: "close" for L in close_lights}
    scene.camera = cc
    bpy.context.view_layer.update()

    # ------------------------------------------- the live / baked split
    tgt = list(ctrl["target"]["objs"])
    pay = list(ctrl["payload"]["drum"])
    chg = list(ctrl["charge"]["objs"])
    arm = list(ctrl["arm"]["objs"])
    fir = list(ctrl["fire"]["objs"])
    cat = list(ctrl["catch"]["objs"])
    vrd = list(ctrl["verdict"]["objs"])
    live = tgt + pay + chg + arm + fir + cat + vrd
    content = list(ctrl["payload"]["texts"])          # the 8 munition classes
    far_only = list(R["far_only"])                    # printed tape, FAR ONLY
    static_geo = list(R["static"])
    plate = shell_meshes + static_geo

    # BRIEF: "R['static'] existing is not the same as R['static'] being safe."
    # MTA's clean `static` still held three content-text FONT objects.  PKT's
    # does not -- asserted, not assumed.
    stray = [o for o in static_geo if o.type == 'FONT'
             and o.name.startswith("pkt_payload_txt")]
    assert not stray, "content type inside R['static']: %s" % stray
    assert not (set(live) & set(plate)), "a live object is also in the plate"
    assert not (set(content) & set(plate)), "content type is in the plate"
    assert not (set(far_only) & set(plate)), "far-only tape is in the plate"
    assert not (set(live) & set(content))
    assert set(live) | set(content) | set(far_only) | set(static_geo) \
        == set(mine), "the live/content/far-only/static split is not a partition"
    print("split: %d plate objects (%d shell + %d static), %d live "
          "(%d target, %d payload, %d charge, %d arm, %d fire, %d catch, "
          "%d verdict), %d content type, %d far-view-only"
          % (len(plate), len(shell_meshes), len(static_geo), len(live),
             len(tgt), len(pay), len(chg), len(arm), len(fir), len(cat),
             len(vrd), len(content), len(far_only)))

    hide_from_depth = live + content + far_only

    # ----- the plate and the depth pass, both at the module's OWN rest state
    # (every set_*() is at its rest when add_props returns), so plate.png shows
    # what is BEHIND every live object.
    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"),
                         hide=hide_from_depth)

    # ------------------------------------------------------------ anchors
    rm3 = root.matrix_world.to_3x3()
    ux = dirn(rm3, (1, 0, 0))                  # face RIGHT (the slot's +X)
    uv = dirn(rm3, mod.UPV)                    # face UP,     raked 44 deg
    un = dirn(rm3, mod.NRM)                    # face NORMAL, at the pilot
    # No module declares `axis` on a `rotate` control, and FOUR modules rake
    # their working face off the slot plane -- PKT by 44 deg -- so rotating
    # about root +Z sweeps a cone.  Every PKT rotation is about the face normal
    # (build.py's spin(e,'z',..) puts Matrix.Rotation(Z) inside the pivot's
    # FACE_ROT basis, and FACE_ROT maps local +Z onto NRM), except the arm
    # cage/toggle hinges, which are spin(e,'x',..) and commute with the rake,
    # so they turn about root +X.
    #
    # EMITTED NEGATED, MQB's convention: a POSITIVE angle is then clockwise on
    # screen, which is the direction build.py's own bearing arc and its demo's
    # CSS `rotate(bear deg)` both run.
    spin_axis = [-c for c in T.to3(un)]

    def hub(piv):
        return root.matrix_world @ Vector(tuple(piv["rest_loc"]))

    wheel_hub = hub(ctrl["target"]["pivot"])
    drum_hub = hub(ctrl["payload"]["pivot"])
    cage_hinge = hub(ctrl["arm"]["cage_piv"])
    tog_hinge = hub(ctrl["arm"]["tog_piv"])
    spool_hubs = [hub(p) for p in ctrl["catch"]["spool_pivots"]]

    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-dirn(
        cc.matrix_world.to_3x3(), (0, 0, -1))).dot(un)))))
    print("OBLIQ panel face normal vs close-cam view axis %.3f deg  "
          "(survey's wide-ray estimate: 10.777)" % obliq)

    # --------------------------------------------------- the readout planes
    planes = []
    for (nm, cx, cy, h, hw, hh, size, lead, top, nl, ncols, align) in PLAN:
        SZ = mod.K(size)                       # Blender FONT.size, world metres
        # a single-line readout has no line PITCH; the value only sets the CSS
        # line-height, and layoutType() measures the browser's baseline inside
        # a box of exactly that height, so placement is independent of it.
        # Kept under 1.6 x half_h so the line box cannot overflow the element.
        LEAD = mod.K(lead) if lead else min(SZ, 1.6 * mod.K(hh))
        tb = TM.type_block(mod, SZ,
                           lead_m=LEAD,
                           left_m=(-ncols * TM.measure_type(mod, SZ)["adv"] / 2
                                   if align == "left" else -mod.K(hw)),
                           top_m=(mod.K(top) if top is not None
                                  else LEAD * (nl - 1) / 2.0),
                           n_lines=nl, scale=1.0, align=align)
        tb["n_cols"] = ncols
        origin = root.matrix_world @ mod.F(cx, cy, h)
        rec = {"name": nm,
               "origin": T.to3(origin), "u": T.to3(ux), "v": T.to3(uv),
               "n": T.to3(un),
               "half_w": mod.K(hw), "half_h": mod.K(hh),
               "type": tb,
               "plan": [cx, cy, h],
               "local": list(mod.F(cx, cy, h)),
               "corners_px": {
                   k: dict(zip(("x", "y"), mod.project(
                       scene, cc,
                       origin + ux * (mod.K(hw) * sx) + uv * (mod.K(hh) * sy))))
                   for k, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                                     ("bl", -1, -1), ("br", 1, -1))}}
        planes.append(rec)

    print("TYPE  metrics measured in Blender (FONT.size is NOT an em):")
    for p in planes:
        t = p["type"]
        c = p["corners_px"]
        ppm = (math.hypot(c["tr"]["x"] - c["tl"]["x"],
                          c["tr"]["y"] - c["tl"]["y"]) / (2 * p["half_w"]))
        print("   %-8s size %.5f -> adv %.6f m (ratio %.6f)  cap %.6f  "
              "base %.6f   %.1f px/m -> cap %.2f px, %d cols = %.1f px"
              % (p["name"], t["size_m"], t["adv_m"], t["adv_m"] / t["size_m"],
                 t["cap_m"], t["base_m"], ppm, t["cap_m"] * ppm,
                 t["n_cols"], t["n_cols"] * t["adv_m"] * ppm))
        # the element must be able to contain the glyphs it is given
        need_h = (t["n_lines"] - 1) * t["lead_m"] / 2 + t["cap_m"] / 2
        assert p["half_h"] >= need_h - 1e-9, (p["name"], p["half_h"], need_h)
        assert p["half_w"] >= t["n_cols"] * t["adv_m"] / 2 - 1e-9, p["name"]

    # ---- MEASURED: what actually crosses a declared rect, and is it live?
    # The audit's harness was not kept (BRIEF correction 11), so this rebuilds
    # the useful half of it.  What matters for check_occlusion.py check 4 is the
    # live/baked split of the occluders: baked ones are in depth.bin and so in
    # its offline ground truth, LIVE ones are not.
    dg = bpy.context.evaluated_depsgraph_get()
    liveset = set(o.name for o in live)
    cam_o = cc.matrix_world.translation

    def probe(p, n=11):
        origin = Vector(root.matrix_world @ mod.F(*p["plan"]))
        hits = collections.Counter()
        for i in range(n):
            for j in range(n):
                s = origin + ux * (p["half_w"] * (2 * i / (n - 1) - 1)) \
                           + uv * (p["half_h"] * (2 * j / (n - 1) - 1))
                v = s - cam_o
                d = v.length
                ok, loc, nrm, idx, ob, mw = scene.ray_cast(
                    dg, cam_o, v.normalized(), distance=d - 0.001)
                if ok and ob is not None:
                    hits[("LIVE " if ob.name in liveset else "baked ")
                         + ob.name] += 1
        return hits

    print("PROBE  11x11 ray-cast per declared rect, close cam, EXPORT pose:")
    live_hits, probe_json = 0, {}
    for p in planes:
        h = probe(p)
        n_live = sum(v for k, v in h.items() if k.startswith("LIVE"))
        live_hits += n_live
        probe_json[p["name"]] = {"covered": sum(h.values()), "of": 121,
                                 "live": n_live, "by": dict(h.most_common(6))}
        print("   %-8s %3d/121 covered   live %d   %s"
              % (p["name"], sum(h.values()), n_live,
                 dict(h.most_common(4)) if h else "clear"))
    print("   LIVE geometry in front of a declared rect: %d  (PKT is OCCLUDED "
          "but STATIC-ONLY; the audit says this must be 0)" % live_hits)

    # The SAME probe at the stand-offs the module itself declares, so the value
    # of the nudge is a measurement rather than an assertion.  `payload` has no
    # declared quad at all -- 0.0135 is where build.py puts the FONT object.
    AS_AUTHORED = {"target": 0.0090, "payload": 0.0135,
                   "catch": 0.0210, "verdict": 0.0330}
    print("   the same rects AS THE MODULE DECLARES THEM (before the nudge):")
    authored = {}
    for p in planes:
        q = dict(p)
        q["plan"] = [p["plan"][0], p["plan"][1], AS_AUTHORED[p["name"]]]
        h = probe(q)
        n_live = sum(v for k, v in h.items() if k.startswith("LIVE"))
        authored[p["name"]] = {"h": AS_AUTHORED[p["name"]],
                               "covered": sum(h.values()), "of": 121,
                               "live": n_live, "by": dict(h.most_common(6))}
        print("     %-8s h %.4f  %3d/121 covered   live %d   %s"
              % (p["name"], AS_AUTHORED[p["name"]], sum(h.values()), n_live,
                 dict(h.most_common(3)) if h else "clear"))

    # ------------------------------------------------------------ geometry
    # exported at the module's REST state, so every runtime transform is a
    # delta from a known zero.
    T.export_glb(tgt, os.path.join(OUT, "target.glb"))
    T.export_glb(pay, os.path.join(OUT, "payload.glb"))
    T.export_glb(chg, os.path.join(OUT, "charge.glb"))
    T.export_glb(arm, os.path.join(OUT, "arm.glb"))
    T.export_glb(fir, os.path.join(OUT, "fire.glb"))
    T.export_glb(cat, os.path.join(OUT, "catch.glb"))
    T.export_glb(vrd, os.path.join(OUT, "verdict.glb"))

    # ------------------------------------------------ THE CAPTURE POSE
    # Everything from here on is rendered in the pose module.js rests in.
    mod.set_payload(ctrl["payload"], POSE_PAYLOAD)
    mod.set_charge(ctrl["charge"], POSE_CHARGE)
    mod.set_arm(ctrl["arm"], POSE_ARM)
    mod.set_fire(ctrl["fire"], POSE_FIRE)
    mod.set_catch(ctrl["catch"], POSE_CATCH)
    mod.set_verdict(ctrl["verdict"], POSE_VERDICT)
    # the wheel: spin_deg = -bearing, because a positive bearing is CLOCKWISE on
    # screen and a positive rotation about the face normal (which points at the
    # camera) is counter-clockwise.  This is the sign check: get it backwards
    # and compare.py against gt_full_read.png spikes.
    mod.spin(ctrl["target"]["pivot"], 'z', -POSE_BEARING)
    bpy.context.view_layer.update()

    # ------------------------------- the readout STRINGS, and their type
    # Three of the four readouts have NO baked type: build.py authors the
    # aperture, the designation band and the header bar deliberately empty.  So
    # the type is created here, with the module's own text() helper, at the
    # declared plane, in the pose's own strings -- and rendered, and then it
    # exists nowhere else.  (The payload class IS authored, at h = 0.0135, i.e.
    # buried inside pkt_breech_frame; it is re-made on the plane too, so that
    # gt_platen0.png is Blender's render of the type WHERE THE FIX PUTS IT
    # rather than where the authoring error left it.)
    TEXT = {
        "target": ["LISTENING POST"],
        "payload": [mod.PAYLOADS[POSE_PAYLOAD]],
        "catch": [
            "SIGNAL HARPOON // RETURN",
            "target : LISTENING POST",
            "class  : INJECTION",
            "exit   : 0",
            "------------------------",
            "$ cat /srv/ops/flag.txt",
            "SAINTCON{h4rp00n_br1ngs_",
            "1t_b4ck}",
            "[line spent - 412 bytes]",
        ],
        "verdict": ["IMPACT"],
    }
    stand_ins, per_plane = [], {}
    for p in planes:
        t = p["type"]
        cx, cy, h = p["plan"]
        objs = []
        for i, body in enumerate(TEXT[p["name"]]):
            if not body:
                continue
            # plan-space y of line i's ORIGIN, from top_m and lead_m
            py = cy + (t["top_m"] - i * t["lead_m"]) / mod.S
            px = cx + (t["left_m"] / mod.S if t["align"] == "left" else 0.0)
            o = mod.text("pkt_dom_%s_%d" % (p["name"], i), body, t["size_m"],
                         bpy.data.materials["pkt_" + INK_MAT[p["name"]]],
                         mod.F(px, py, h), mod.FACE_ROT,
                         align='LEFT' if t["align"] == "left" else 'CENTER')
            o.parent = root
            objs.append(o)
        stand_ins += objs
        per_plane[p["name"]] = objs
    bpy.context.view_layer.update()
    assert not (set(stand_ins) & set(plate)) and not (set(stand_ins) & set(live))

    # per-readout type renders -> each readout's OWN measured ink colour
    inks = {}
    for p in planes:
        fn = os.path.join(OUT, "gt_type_%s.png" % p["name"])
        T.render_colour(scene, fn, visible=per_plane[p["name"]])
        inks[p["name"]], n = median_ink(fn)
        p["ink"] = inks[p["name"]]
        print("INK   %-8s median rgb%s over %d covered px  (material pkt_%s)"
              % (p["name"], tuple(inks[p["name"]]), n, INK_MAT[p["name"]]))
    # the type ALONE: its covered pixels are exactly the glyph coverage, which
    # is what check/verify_assets.py takes its footprint from and what
    # check/check_text.py scores the DOM against.
    T.render_colour(scene, os.path.join(OUT, "gt_platen0.png"),
                    visible=stand_ins)

    # THE ONE compare.py SCORES: exactly the objects the browser renders live,
    # in exactly the state __occ.pose() puts the page in.  The muzzle flash is
    # live geometry but fire is "ready" at rest, so it is not drawn -- and
    # export_glb() has just cleared its hide_render, which is why this is an
    # explicit visible= list and not a "everything live" one.
    live_rest = [o for o in live if o not in set(ctrl["fire"]["flash"])]
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"),
                    visible=live_rest)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + live_rest)

    # ---------------------------------------------------------- scene.json
    # every probe on a VISIBLE STATIC surface (BRIEF trap 7): an interior point
    # or a point on a LIVE object records whatever is behind it in depth.bin.
    rows = T.verify_depth(scene, cc, dep, [
        ("send field face", root.matrix_world @ mod.F(-0.380, 0.130, 0.004)),
        ("scope readout face", root.matrix_world @ mod.F(-0.310, -0.112, 0.0090)),
        ("breech frame face", root.matrix_world @ mod.F(-0.090, -0.014, 0.0150)),
        # NOT pkt_ap_back (h 0.0070): pkt_prn_bezel is a SOLID slab across the
        # whole printer footprint whose front face is at h 0.0100, so the
        # aperture's visible back wall is the bezel, 3.45 mm nearer.  Probing
        # 0.0070 reports err -0.00345, which is the bezel, not an export error
        # -- BRIEF trap 7, "a depth probe point must be on a VISIBLE surface".
        ("aperture back face", root.matrix_world @ mod.F(0.264, -0.030, 0.0100)),
        ("header frame face", root.matrix_world @ mod.F(0.264, 0.074, 0.0340)),
    ])
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-20s want %.5f  got %.5f  err %+.5f"
              % (nm, want, got, err))

    def rect(objs, pad=8):
        return mod.clamp_rect(mod.bbox_rect(scene, cc, objs, pad=pad), W, H)

    def names(objs):
        return [o.name for o in objs]

    j = {
        "render": {"w": W, "h": H},
        "camera": T.cam_json(scene, cc),
        "lights": T.lights_json(scene, close_tags),
        "world_bg": list(scene.world.node_tree.nodes["Background"]
                         .inputs[0].default_value),
        "colour": {"view_transform": scene.view_settings.view_transform,
                   "look": scene.view_settings.look,
                   "exposure": scene.view_settings.exposure},
        "light_gain": 0.65,      # measurements.txt tuned close_rt = 0.65
        "env_intensity": 0.0,    # measured optimum, monotonically; do not add
        "raytrace": 1,
        "scale": mod.S,
        "rake_deg": math.degrees(mod.RAKE),
        "obliquity_deg": obliq,
        "glow_tint": "red",      # PKT is the one module with .glow.tint-red
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "panel": {"u": T.to3(ux), "v": T.to3(uv), "n": T.to3(un),
                  "origin": T.to3(root.matrix_world @ Vector((0, 0, 0))),
                  "spin_axis": spin_axis,
                  "spin_note": "rotate by a POSITIVE angle about spin_axis for "
                               "a CLOCKWISE turn on screen"},
        "props": {
            "target": {
                "glb": "target.glb", "kind": "rotate",
                "label": ctrl["target"]["label"],
                "hub": T.to3(wheel_hub), "axis": spin_axis,
                "pivot_px": dict(zip(("x", "y"),
                                     mod.project(scene, cc, wheel_hub))),
                "range": list(ctrl["target"]["range"]),
                "hotspot": rect(ctrl["target"]["hotspot_objs"], pad=6)},
            "payload": {
                "glb": "payload.glb", "kind": "rotate",
                "label": ctrl["payload"]["label"],
                "hub": T.to3(drum_hub), "axis": spin_axis,
                "pivot_px": dict(zip(("x", "y"),
                                     mod.project(scene, cc, drum_hub))),
                "labels": list(ctrl["payload"]["labels"]),
                "deg_per_step": 45.0,
                "hotspot": rect(ctrl["payload"]["hotspot_objs"], pad=6)},
            "charge": {
                "glb": "charge.glb", "kind": "slide",
                "label": ctrl["charge"]["label"],
                "up_axis": T.to3(uv), "throw_m": ctrl["charge"]["throw"],
                "steps": ctrl["charge"]["frames"],
                "lever": names(ctrl["charge"]["lever"]),
                "tubes": names(ctrl["charge"]["tubes"]),
                "tube_mats": [m.name for m in ctrl["charge"]["tube_lv"]],
                "pips": names(ctrl["charge"]["pips"]),
                "pip_off": [m.name for m in ctrl["charge"]["pip_off"]],
                "pip_on": [m.name for m in ctrl["charge"]["pip_on"]],
                "hotspot": rect(ctrl["charge"]["hotspot_objs"], pad=6)},
            "arm": {
                "glb": "arm.glb", "kind": "states",
                "label": ctrl["arm"]["label"],
                "order": list(ctrl["arm"]["order"]),
                "hinge_axis": T.to3(ux),
                "cage": names(ctrl["arm"]["cage"]),
                "cage_hinge": T.to3(cage_hinge),
                "toggle": names(ctrl["arm"]["toggle"]),
                "toggle_hinge": T.to3(tog_hinge),
                # build.py's set_arm: spin(cage,'x',-cage_ang), spin(tog,'x',ang)
                "cage_deg": {"safe": 0.0, "armed": -78.0, "interlock": 0.0},
                "toggle_deg": {"safe": -34.0, "armed": 30.0,
                               "interlock": -30.0},
                "lamps": names(ctrl["arm"]["lamps"]),
                "lamp_off": [m.name for m in ctrl["arm"]["off"]],
                "lamp_on": [m.name for m in ctrl["arm"]["on"]],
                "lit": {"safe": [0, 0], "armed": [1, 0], "interlock": [0, 1]},
                "hotspot": rect(ctrl["arm"]["hotspot_objs"], pad=6)},
            "fire": {
                "glb": "fire.glb", "kind": "states",
                "label": ctrl["fire"]["label"],
                "order": list(ctrl["fire"]["order"]),
                "plunger": names(ctrl["fire"]["plunger"]),
                "flash": names(ctrl["fire"]["flash"]),
                "normal_axis": T.to3(un), "drop_m": ctrl["fire"]["drop"],
                "hotspot": rect(ctrl["fire"]["hotspot_objs"], pad=6)},
            "catch": {
                "glb": "catch.glb", "kind": "advance",
                "label": ctrl["catch"]["label"],
                "up_axis": T.to3(uv), "advance_m": ctrl["catch"]["advance"],
                "steps": ctrl["catch"]["frames"],
                "platen": names(ctrl["catch"]["platen"]),
                "spools": [names(g) for g in ctrl["catch"]["spools"]],
                "spool_hubs": [T.to3(p) for p in spool_hubs],
                "spool_axis": spin_axis,
                "spool_deg_per_step": [-34.0, 34.0],
                "hotspot": rect(ctrl["catch"]["hotspot_objs"], pad=6)},
            "verdict": {
                "glb": "verdict.glb", "kind": "states",
                "label": ctrl["verdict"]["label"],
                "order": list(ctrl["verdict"]["order"]),
                "lamps": names(ctrl["verdict"]["lamps"]),
                "lamp_off": [m.name for m in ctrl["verdict"]["off"]],
                "lamp_on": [m.name for m in ctrl["verdict"]["on"]],
                "lit": {"idle": -1, "hit": 0, "refused": 1, "deflected": 2},
                "hdr": ctrl["verdict"]["hdr"].name,
                "hdr_mats": {k: m.name for k, m
                             in ctrl["verdict"]["hdr_mats"].items()},
                "hotspot": rect(ctrl["verdict"]["hotspot_objs"], pad=6)},
        },
        "text_planes": planes,
        "ink": inks,
        # the pose, so module.js and this exporter cannot drift apart
        "pose": {"bearing": POSE_BEARING, "payload": POSE_PAYLOAD,
                 "charge": POSE_CHARGE, "arm": POSE_ARM, "fire": POSE_FIRE,
                 "catch": POSE_CATCH, "verdict": POSE_VERDICT},
        "readout_text": [TEXT[p["name"]] for p in planes],
        "depth_verify": [{"name": n_, "analytic": w, "baked": g, "err": e}
                         for n_, w, g, e in rows],
        "probe": probe_json,
        "probe_as_authored": authored,
        "probe_live_hits": live_hits,
    }
    with open(os.path.join(OUT, "scene.json"), "w") as f:
        json.dump(j, f, indent=1)
    with open(os.path.join(OUT, "materials.json"), "w") as f:
        json.dump(T.materials_json(), f, indent=1)

    # ------------------------------------------------ the LIVE-half control
    # PKT ships with nothing live in front of a readout, which is the audit's
    # verdict and is correct -- so check_occlusion.py's LIVE half would be
    # exercised only by an empty set.  This second scene.json puts ONE extra
    # plane back at the verdict rect's originally-declared h = 0.0330, which is
    # INSIDE the live pkt_hdr_bar, so the bar is genuinely in front of a
    # declared readout.  It is a separate FILE, so nothing shipping is mutated.
    if os.environ.get("PKT_CONTROL_PLANE") == "1":
        p0 = [p for p in planes if p["name"] == "verdict"][0]
        cx, cy, _h = p0["plan"]
        ctlp = json.loads(json.dumps(p0))
        ctlp["name"] = "verdict_control"
        ctlp["plan"] = [cx, cy, 0.0330]
        o2 = root.matrix_world @ mod.F(cx, cy, 0.0330)
        ctlp["origin"] = T.to3(o2)
        ctlp["local"] = list(mod.F(cx, cy, 0.0330))
        ctlp["corners_px"] = {
            k: dict(zip(("x", "y"), mod.project(
                scene, cc, o2 + ux * (p0["half_w"] * sx)
                + uv * (p0["half_h"] * sy))))
            for k, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                              ("bl", -1, -1), ("br", 1, -1))}
        jc = json.loads(json.dumps(j))
        jc["text_planes"] = jc["text_planes"] + [ctlp]
        jc["readout_text"] = jc["readout_text"] + [["IMPACT"]]
        with open(os.path.join(OUT, "scene_control.json"), "w") as f:
            json.dump(jc, f, indent=1)
        print("CONTROL -> scene_control.json (5 planes; the 5th is inside the "
              "LIVE pkt_hdr_bar)")

    print("EXPORT OK ->", OUT)


# ===========================================================================
# THE REFIT PORT -- a SECOND entry point, deliberately separate from main().
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_pkt.py -- refit
#
# main() re-renders plate.png, depth.bin and all six gt_*.png and would
# invalidate every number in NOTES.md sections 1-9 and in live3d/RESULTS.md.
# This entry point does none of that: it builds the port ALONE IN AN EMPTY
# SCENE, writes assets/PKT/refit.glb and merges one "refit" key into the
# existing scene.json.  Nothing else in assets/PKT/ is opened for writing.
# FIX_UPLOAD section 0, decision 3.
#
# ROOT SCALE IS 1.0 HERE AND main()'s 1.15 IS IRRELEVANT.  FIX_UPLOAD 12.14
# item 4 lists PKT at 1.15, and that is right for main(), which authors INSIDE
# a scaled root.  This entry point clears the scene and builds in WORLD
# coordinates, so there is no root to be inside; passing 1.15 would ship the
# port 1/1.15 = 0.87x and its rail's span unchanged.  `check_root_scale()`
# REFUSES a non-unit value in an empty scene (FIX_UPLOAD 12.15 item 2) and
# prints the authoring-space and world sizes either way.
#
# ------------------------------------------------------------------ THE ANCHOR
# FIX_UPLOAD 3.3 tables (339, 685) at 56 px, "dash lip in front of the raked
# panel", baked depth 1.731..1.772 m.  THE CARRIER IS RIGHT -- the shipped port
# sits at 1.727..1.781 m, inside the tabled range -- AND THE TABLED ROW IS NOT
# BUILDABLE, for a reason 3.3 does not record:
#
#   A ROUNDED BRASS LIP -- A BARREL -- RUNS ACROSS THE WHOLE DASH AND STANDS
#   ~14.7 mm PROUD OF THE DESK BEHIND IT.  Reading depth.bin down x = 340:
#       y 648  1.7861 (the lip's top face)
#       y 657  1.7646 (the lip's crown -- NEAREST)
#       y 669  1.7718
#       y 672  1.7668 (clean desk starts, and runs -0.00082 m/px)
#   The desk plane extrapolated up to y 657 is 1.7793, so the lip is 14.7 mm in
#   front of it.  A 56 px port centred at y 685 puts its own FOOT samples on
#   the lip and `solve_anchor()` refuses at every in-plane rotation:
#       seat 9.8..12.7 mm against a cap of 6.5 mm.
#   `refit_port.py PKT 339 685 56 --sweep-y 600,715` walks the whole column;
#   the handful of accepting rows are windows that straddle the lip and fit a
#   plane through both surfaces, not places to bolt a port.
#
# CLEAN DESK IS y 672..719 AND THE FRAME ENDS AT 720 -- a 47 px band for a
# fitting whose envelope is 52..56 px tall.  So the port drops below the lip
# and one size, to 52 px: MQB's 62 -> 48 arriving on a sixth module.
#
# ------------------------------------------------- AND IT MOVES ACROSS, 660 PX
# FIX_UPLOAD 12.16 item 5: solve the DOCKET before fixing the anchor.  PKT is
# the module that finding was written for.  The docket is 520 x 317.9 px
# (measured on the running page) and its `y` is CLAMPED to `H - h - 12` = 390,
# so a docket beside a port at the BOTTOM of the frame always reaches to
# y = 708 -- straight over the port it came out of.  Walking the anchor across
# the whole dash with `refit.js`'s own solver reproduced in stdlib and checked
# against the real page:
#
#   port x    docket           px2 of the PORT covered   control CENTRES buried
#   120..250  (12, 390)              ~5,000  (76 %)      target
#   260..350  (cx+40, 390)              171  (2.6 %)     payload, fire, verdict
#   360       (12, 390)               4,901  (76 %)      target
#   380..840  -- not buildable: the lip sits lower on screen there and the
#                envelope is cropped by the bottom of the frame
#   860..940  (cx-560, 390)             158               payload, fire, verdict
#   960..1160 (748, 344)               ~980  (15 %)      catch, verdict
#
# The tabled column costs THREE control centres -- `payload` and `fire` 100 %
# covered, `verdict` 92 % -- which is exactly the defect FIX_UPLOAD 12.15
# item 3 exists to prevent, and unlike KVS ("cannot be helped") PKT can be
# helped.  Only the right-hand band gets the docket ABOVE the port instead of
# beside it: there the docket's own anchor is `cy - h - 26`, so its bottom edge
# is pinned at y 659.5 AT EVERY DOCKET SIZE, which leaves the whole dash shelf
# below it free for the port, the mast AND the mast's caption.  Shipped at
# (1000, 692).  FMM moved 241 px in x for the same reason and this is 660.
#
# WHAT IT COSTS, SAID OUT LOUD: the port leaves the fleet's bottom-LEFT corner
# (7 of the 9 tabled anchors are left of centre) and `catch` + `verdict` still
# lose their centres while the docket is open.  There is no anchor on this
# module that buries nothing -- a 520 px docket on a 1280 px stage over a panel
# with seven controls cannot miss them all, which is KVS's finding again.  Two
# is the minimum and the port stays visible; three was the alternative.
#
# --------------------------------------------------------------- THE NUMBERS
#   * `--window 964,1037,676,716` IS THE PORT'S OWN FOOT ON CLEAN DESK, and it
#     is load-bearing.  A window that reaches the lip (the two-pass
#     "whole envelope" window) fits a plane through both surfaces: obliquity
#     42.7 deg, residual max 0.0095 m.  On clean desk only: 45.52 deg, residual
#     p50 0.00007 m, max 0.00033 m.  FIX_UPLOAD 12.16 item 4.
#   * THE CARRIER IS 45.52 deg OBLIQUE and PKT's declared face is 14.31; they
#     differ by 31.52 deg.  FIX_UPLOAD 12.2's "the carrier is 45 deg off the
#     declared face" is a KVS fact, and PKT is the second module where it is
#     nearly true.  Fleet: KVS 45.08, PKT 31.52, MTA 8.73, FMM 0.07, MQB 0.00.
#   * W = 54.0 mm, not the ~35 mm section 2's table implies: the table takes
#     px/m at the READOUT plane (1.84..1.87 m) and this carrier is at
#     1.727..1.781 m.  FIX_UPLOAD 12.5, on a sixth module and in the same
#     direction as MTA's, OTA's and FMM's.
#   * SEAT 2.488 mm = 3.0 x ubias_m, and the margin is 3.99 px of the carrier's
#     own depth gradient (floor 0.50).  FIX_UPLOAD 12.16 item 2.  PKT's
#     `ubias_m` is 0.000840 and is a real measured gap (`live_depth.py` eroded
#     min 0.001200), not FMM's degenerate 1e-06, so the shared default of 2.5
#     is a stand-off here and no `--seat-margin` is needed.
#   * sub_base=False.  The lip is ~16 px above the envelope's top edge, well
#     inside the "~1 W" FIX_UPLOAD 12.14 item 3 draws the line at, and it is
#     exactly the structure section 1.4 says the sub-base substitutes for.  A
#     1.3 W footprint is 68 px tall against a 47 px band and would climb it.
#   * mark=None.  532 triangles for a 3 px smear; cut on every module so far.
#   * label "REFIT", not FIX_UPLOAD section 7's proposed "FLEET".  Section 7's
#     own headline is "PKT carries the IDENTICAL port"; the fleet-wide-refit
#     question is still open (refit.js's FLEET table carries `fleet: true` and
#     the docket says so in words), and words are cheap to change while an
#     engraving is not.  REPORTED, not decided.
#
# A NOTE ON `_solve_seat()` THAT IS NOT PKT-SPECIFIC -- see NOTES.md section 14
# item 1.  `refit_port._solve_seat()` samples the foot at z = 0 only, so a port
# whose RAISED FACE (0.158 W proud, and up-screen on an oblique carrier)
# projects onto something nearer than its own carrier is NOT refused.  At
# (339, 690) the tabled column solves at a seat of 5.31 mm and the frame face
# is then 1.5 mm BEHIND the lip at (356, 664) -- silently deleted by the depth
# composite.  Every anchor here was additionally checked against the WHOLE
# assembly hull; this one clears the baked plate by 2.38 mm everywhere.
#
# Sweep any of it yourself, with no Blender in the loop:
#
#   python3 live3d/pipeline/refit_port.py PKT 339 685 56                # refused
#   python3 live3d/pipeline/refit_port.py PKT 339 685 56 --sweep-y 600,715
#   python3 live3d/pipeline/refit_port.py PKT 1000 692 52 --window 964,1037,676,716
PKT_REFIT = dict(px=1000, py=692, port_px=52,
                 carrier_window=(964, 1037, 676, 716),
                 label="REFIT", mark=None,
                 sub_base=False, service_rail=True)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(PKT_REFIT)
    A = RP.solve_anchor(CODE, K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"])
    P = RP.build("pkt_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export(CODE, A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))


# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_pkt.py -- mast
#
# Builds the mast ALONE IN AN EMPTY SCENE, in WORLD coordinates (root_scale
# 1.0, for the same reason it is 1.0 for the port -- PKT's own main() is 1.15
# and it is irrelevant here), writes assets/PKT/mast.glb and merges one "mast"
# key into the existing scene.json.  Nothing else in assets/PKT/ is opened for
# writing.
#
# ------------------------------------------------------- kind = "offensive"
# STATUS_AT_A_GLANCE section 8.  PKT is the offensive panel: no `unit_tests/`,
# no `vuln_tests/`, and `bridge/data/catalog.json` does not list it, so NEITHER
# AXIS OF THE EIGHT DEFENSIVE MASTS EXISTS FOR IT.  It must not simply have no
# telltale -- eight masts and one bare module reads as a missing indicator --
# so it gets DIFFERENT HARDWARE ON THE SAME FITTING:
#
#   * the graduated glass tube is replaced by a NOTCHED BRASS TALLY STICK,
#     12 notches, `INK.tally` #3A2E18 with `INK.tallyOn` #C0392B filled;
#   * it FILLS UPWARD AS GOOD NEWS -- distinct fleet vulns PKT has confirmed
#     landing this session, `confirmed / 54` -- which is the opposite of the
#     eight defensive tubes, and is exactly why it must not look like one;
#   * the cap bead becomes the ARM LAMP: dark = SAFE, steady #C0392B = ARMED,
#     hazard-striped = INTERLOCK;
#   * NO VANE.  PKT does not "still work" in the sense the eight do.
#
# `status_mast.py` has carried `kind="offensive"` since KVS ("BUILT BUT NOT
# INTEGRATED", STATUS_AT_A_GLANCE 6.5 "What is NOT built").  PKT is the first
# module to ship it, and `status.js` already branches on the RECORD's own
# `kind` and never on `code === 'PKT'` (DEFAULT_KIND is the fallback);
# live3d/status.json already carries PKT's `{kind, tally:{11,54}, arm:"armed"}`.
#
# --------------------------------------------------------------- THE MOUNT
# NOT ON THE PORT'S SERVICE RAIL, and that is measured.  Walking the port's own
# fitted plane along +/-u and reading depth.bin at every step (the port at its
# earlier trial anchor, x 340, where the walk covers the whole dash):
#
#     u_mm    -280   -140      0    +140   +200   +260   +300
#     mm in front of baked
#             -8.31  +0.78  +3.05  -0.82  -3.85  -8.91  -12.45
#
# The dash lip CROWNS near the middle of the frame and falls away both ways, so
# a rail lying in the port's own plane is behind the baked plate -- and deleted
# by the depth composite -- past about 140 mm either side.  The published
# `free_from_m` is 1.5 W = 81 mm and a 180 px mast from there runs to u ~ 260
# mm, ~9 mm behind the plate at its far end.  That is FMM's convex-fascia
# finding with the curvature reversed, and it is the cantilevered shelf MTA
# rejected.  `solve_mast()` would ramp it; a 9 mm ramp is not a rail.
#
# So PKT takes `status_mast.py`'s second documented route, `--at PX,PY`, with
# the carrier measured at that pixel -- STATUS_AT_A_GLANCE 6.1's ORIGINAL
# "small brass status sub-plate bolted to the panel", which 11.2's rail was an
# upgrade to and not a replacement for.  Fleet: KVS rail 3.2 W, MQB rail
# 12.2 W, MTA `--at`, OTA `--at`, FMM rail 1.5 W, PKT `--at`.
#
# WHERE: the same dash shelf as the port and immediately to its PORT side, so
# the two still read as one installation running along the lip.
#
#     mast envelope   754.5.. 942.6 x 672.6..706.1   hotspot 750.5..946.6
#     port hotspot    959.8..1040.9 x 652.1..720.0
#     gutter 13.2 px, 0 px2 either way
#
# and both clear the docket, which is the point of putting the port on the
# right at all: with the docket ABOVE the port its bottom edge is pinned at
# y 659.5 whatever its height, and the mast's hotspot starts at y 668.6.
# STATUS_AT_A_GLANCE 6.5 item 4 -- reading the mast WHILE THE PORT IS OPEN is
# the entire reason the close-up half exists.  It also leaves the caption's
# second candidate ("to port, on the sill", x 478.5..738.5) on bare dash,
# clear of the mast, the port and the docket at once.
#
# RAKE 45, and it is KVS's case on a sixth module.  The dash's own two in-plane
# directions project at v 867.6 and n 555.9 px/m -- a ratio of 1.56, near
# enough the same rate that a fitting LYING on it is one-dimensional on screen,
# which is the condition STATUS_AT_A_GLANCE 16.2 says to rake for (KVS 1.44,
# and FMM's 34x is the opposite extreme, where a rake can only spend the one
# axis that works).  Raked 45 the face sits at 2.87 deg with its axes at
# A 1015.1 and B 1006.2 px/m, unforeshortened in both.  The obliquity minimum
# is at 45 deg here, which 17.5 warns is a coincidence and not the criterion.
# Fleet: KVS 45, MQB 0, MTA 0, OTA 57, FMM 0, PKT 45.  Run `--rakes`.
#
# 180 px is the largest that keeps the gutter: `--sweep-px 120,240` shows the
# worst gap to another hotspot going 13.9 px at 180, 3.8 px at 190 and 0 at
# 200.  There is no LIFT cliff on this carrier (FIX_UPLOAD 12.16 item 6): the
# lift is 14.28 mm, 17.0 x `ubias_m`, flat across the whole sweep.
#
# `--window 665,855,678,714` is the mast's own footprint on CLEAN DASH.  The
# default window (px +/- 40, py +/- 24) is 80 px wide for a 188 px fitting and
# extrapolates a plane over twice its own length across a convex lip;
# FIX_UPLOAD 12.16 item 4 / STATUS_AT_A_GLANCE 17.7.
#
# M = 12 IS INERT ON THIS VARIANT and is set to the notch count so that nothing
# reads as inconsistent.  `m` means "the count of `vuln_tests/NN_*.py`" and PKT
# has no `vuln_tests/` at all; the offensive builder never uses it (the tally's
# 12 notches come from `GEO['tally_n']`, and `_hull_samples()` branches on
# `kind` before it touches `m`), and `mast.js` only re-publishes it.  What the
# fitting actually shows is `tally.confirmed / tally.of` = 11 / 54, and 54 is
# `status.js -> FLEET_VULN_TOTAL`, counted across the EIGHT DEFENSIVE modules
# and overridable by `status.json -> fleet.vuln_total`.
#
#   python3 live3d/pipeline/status_mast.py PKT --at 760,694 \
#           --window 665,855,678,714 --rakes
#   python3 live3d/pipeline/status_mast.py PKT --at 760,694 \
#           --window 665,855,678,714 --kind offensive --m 12 --rake 45 \
#           --sweep-px 120,240
#   python3 live3d/pipeline/status_mast.py PKT --at 760,694 \
#           --window 665,855,678,714 --kind offensive --m 12 --rake 45 --px 180
PKT_MAST = dict(mast_px=180, rake_deg=45.0, m=12, kind="offensive",
                numbers=False,
                at=(760, 694),
                carrier_window=(665, 855, 678, 714))


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(PKT_MAST)
    A = SMT.solve_mast(CODE, mast_px=K["mast_px"], rake_deg=K["rake_deg"],
                       m=K["m"], kind=K["kind"], numbers=K["numbers"],
                       px=K["at"][0], py=K["at"][1],
                       carrier_window=K["carrier_window"])
    P = SMT.build("pkt_mast", A["frame_blender"], A["carrier_blender"],
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
