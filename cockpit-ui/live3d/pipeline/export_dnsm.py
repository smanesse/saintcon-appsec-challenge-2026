"""
LIVE-3D EXPORT — DNSM close-up  ("Nav Beacon / Star Charts", the DNS module).

A thin layer on top of three-exploration/pipeline/transliterate.py, following
live3d/CONVERSION_BRIEF.md.  The module's REAL build.py is imported in place by
live3d/pipeline/module_loader.py, so there is no DNSM snapshot to go stale.

DNSM is the fleet's heaviest module (521,636 tris) and the audit's OCCLUDED
verdict (live3d/audit/OCCLUSION_AUDIT.md) rests on three content surfaces:

    query readout    QT <TYPE> <ANSWER>, top right, 8 alternates in one slot
                     -- 0/10 over 55 poses, CLEAN
    star-catalogue   dnsm_chart_txt_<facet>_<line>, 18 lines over SIX FACETS of
      drum           a hexagonal drum behind a window in the face plate.
                     24 of 48 samples are behind `dnsm_face_under` at rest,
                     because THE CARRIER IS LONGER THAN ITS APERTURE.
    courier card     dnsm_card_head, "CHART 44-12", on a card that SLIDES into
      head           a slot -- a MOVING plane, 0/8 but with no margin.

    plate.png       shell + DNSM STATIC parts.  There is NO R["static"]: the
                    module returns R["plate"], which here really IS the static
                    set (a property of keep(), asserted below, not trusted).

    sweep.glb       the phosphor beacon wedge, 10 decaying sectors + edge
    qtype.glb       23+ contacts over 8 query types, 8 lamp domes
    chart.glb       the six-facet catalogue drum, MINUS its 18 lines of type
    courier.glb     the chart card, its punch holes, and the import lamp

    NOT EXPORTED AT ALL: the content type.  27 objects --
    dnsm_readout_<qtype> x8, dnsm_chart_txt_<k>_<j> x18, dnsm_card_head --
    are values a player reads, so per README section 12 they become DOM and are
    excluded from the plate, from the depth pass and from every glb.  STAMPED
    lettering stays geometry: dnsm_title, dnsm_subtitle, dnsm_win_label
    ("STAR CATALOGUE"), dnsm_slot_label ("CHART COURIER"), the eight
    dnsm_lamp_label_* and the four scope cardinals N/E/S/W.

    text_planes     EIGHT readout rects: `query`, `chart0`..`chart5`, `courier`.
                    SIX OF THEM ARE ONE CARRIER.  A CSS3D element is flat, so a
                    hexagonal drum is six flat facets, each its own DOM element
                    and its own plane -- which is why occlusion.js's MAX_PLANES
                    is 12.  Each facet plane is TANGENT to the drum at its own
                    facet, rides the drum pivot's matrixWorld every frame, and
                    is skipped by the shader's back-facing test once it turns
                    past 90 deg.  `courier` rides the card.

    scene_rot.json  the SAME export, with the drum at -30 deg (a facet EDGE
                    dead centre in the window, so TWO facets are half-cropped
                    by the aperture at once) and the courier card pushed home.
                    plate.png and depth.bin are baked-only and therefore
                    identical, so this file is only new plane frames, new
                    corners_px and a new `pose`.  It is how the drum ROTATION
                    is put through check_occlusion.py rather than only the rest
                    pose; see modules/DNSM/NOTES.md.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_dnsm.py
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
import ubias as UB                                               # noqa: E402
from module_loader import load_module, check_snapshots           # noqa: E402

shell = T.shell
CODE = "DNSM"
OUT = os.path.join(LIVE3D, "assets", CODE)

# --------------------------------------------------------------- THE POSE
# The one resting state the whole verification chain is scored in.  It must be
# identical here, in gt_full_read.png and in module.js's poseForCapture(), or
# check/compare.py measures the mismatch instead of the renderer.
#
# AXFR, deliberately: it is the state in which the beacon has just pulled the
# whole zone, so every contact on the plot is lit, seven of the eight
# record-type lamps burn amber, and the star-catalogue drum in the window is
# showing a page of the zone that was actually transferred.  An "A" rest (the
# module's own) puts ONE blip on the scope and makes compare.py a test of the
# panel rather than of the live geometry.
POSE_QTYPE = "AXFR"
POSE_CHART_DEG = 0.0        # drum rotation about its own axis; 0 = facet 0 up
POSE_COURIER = "chart"      # card in the mouth, import lamp off
POSE_SWEEP_DEG = 0.0        # the beacon wedge as built (pointing up the face)

# The second, ROTATED pose (scene_rot.json).  -30 deg puts a facet EDGE dead
# centre in the window: facet 0 rides up behind `dnsm_face_over` and facet 1
# rides up from behind `dnsm_face_under`, so two facets are half-cropped by the
# aperture simultaneously.  That is `dnsm_chart_drum_mid.png` in the audit.
ROT_CHART_DEG = -30.0
ROT_COURIER = "import"      # card pushed home -- the head at the slot lip

# --------------------------------------------------------- the eight rects
# Column counts.  Every DNSM readout is monospaced and LEFT-aligned in the DOM,
# because css3d.js's layoutType() implements Blender's align_x LEFT and CENTER
# and NOT RIGHT (see NOTES).  The query readout is authored align='RIGHT'; a
# right-aligned monospaced line is a left-aligned one padded with leading
# spaces to a fixed column, so the DOM pads with `padStart(N_QUERY)` and the
# glyphs land in the same columns.  Asserted against the authored object below.
N_QUERY = 22        # max("QT AAAA   2001:DB8::10") == 22
N_CHART = 26        # max("@     SOA  NS1 2026072201") == 25, +1 of slack
N_CARD = 11         # "CHART 44-12"

MARGIN = 0.002      # module-local metres of slack around a rect's type


def dirn(m3, v):
    """Transform a DIRECTION by a rotation matrix and normalise."""
    return (m3 @ Vector(v)).normalized()


def median_ink(path):
    """The ink colour, measured off Blender's own render of THIS module's type.

    MEDIAN over alpha > 0.5, with NO colour transform (BRIEF section 7 rule 7).
    Blender hands `image.pixels` back ALREADY DISPLAY-ENCODED for an 8-bit sRGB
    PNG, so an sRGB encode on top returns a plausible-looking wrong colour; and
    on small type nothing is fully opaque, so a "most common fully opaque
    pixel" rule returns the empty set."""
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


def bbox_world(objs):
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for o in objs:
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    return lo, hi


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
    shell_meshes = [o for o in T.renderables(scene) if o not in set(mine)]

    # ------------------------------------------------------- close-up rig
    # DNSM's close_rig takes (root) and needs NO pre-state: it reads only
    # root and the module's own fp() helper, and add_props() has already
    # placed root (slots.place + SCALE) and cleared every hide_render.  That
    # is checked rather than assumed -- BRIEF step 3, "close_rig() IS CALLED
    # FROM A STATE": build.py's main() calls it immediately after the far
    # renders, which restore hide_render themselves, so the state at the call
    # is exactly the state here.
    import inspect
    assert list(inspect.signature(mod.close_rig).parameters) == ["root"], \
        "close_rig signature changed: %s" % inspect.signature(mod.close_rig)
    cc, close_lights = mod.close_rig(root)
    close_tags = {L.name: "close" for L in close_lights}
    scene.camera = cc
    bpy.context.view_layer.update()

    # ------------------------------------------- the live / baked split
    sweep = list(ctrl["sweep"]["objs"])
    qt = ctrl["qtype"]
    domes = list(qt["domes"])
    blips = {q: list(v) for q, v in qt["blips"].items()}
    blips_all = [o for q in mod.QTYPES for o in blips[q]]
    readouts = dict(qt["readouts"])                  # CONTENT (8 alternates)

    ch = ctrl["chart"]
    drum_all = list(ch["objs"])
    chart_txt = [o for o in drum_all if o.name.startswith("dnsm_chart_txt_")]
    drum_geo = [o for o in drum_all if o not in set(chart_txt)]

    co = ctrl["courier"]
    card_all = list(co["card"])
    card_head = [o for o in card_all if o.name == "dnsm_card_head"]
    assert len(card_head) == 1
    card_geo = [o for o in card_all if o not in set(card_head)]
    cdome = co["dome"]

    content = list(readouts.values()) + chart_txt + card_head
    live = sweep + blips_all + domes + drum_geo + card_geo + [cdome]
    static_geo = list(R["plate"])
    plate = shell_meshes + static_geo

    # BRIEF step 3: "R['static'] existing is not the same as R['static'] being
    # safe", and DNSM has no R['static'] at all.  What it returns is
    # R['plate'], which the survey warns is the WIDE-SHOT list.  Here it
    # happens to be exactly `all - control-owned` -- a property of build.py's
    # keep(), which appends to `plate` only for objects no control owns -- so
    # ASSERT it rather than trust it, and assert the partition both ways.
    control_owned = set()
    for c in ctrl.values():
        control_owned |= set(c["objs"])
    derived_static = [o for o in mine if o not in control_owned]
    assert set(static_geo) == set(derived_static), (
        "R['plate'] is NOT `all - control-owned`: %d vs %d"
        % (len(static_geo), len(derived_static)))
    assert not (set(live) & set(static_geo)), "a live object is in the plate"
    assert not (set(content) & set(static_geo)), "content type is in the plate"
    assert not (set(live) & set(content))
    assert set(live) | set(content) | set(static_geo) == set(mine), \
        "the live/content/static split is not a partition of R['all']"
    # and MTA's trap: no content type hiding inside the static set
    stray = [o for o in static_geo
             if o.name.startswith(("dnsm_readout_", "dnsm_chart_txt_"))
             or o.name == "dnsm_card_head"]
    assert not stray, "content type inside the static set: %s" % stray
    print("split: %d plate objects (%d shell + %d static), %d live "
          "(%d sweep, %d blip, %d lamp, %d drum, %d card), %d content type"
          % (len(plate), len(shell_meshes), len(static_geo), len(live),
             len(sweep), len(blips_all), len(domes), len(drum_geo),
             len(card_geo) + 1, len(content)))

    def tris(objs):
        dg = bpy.context.evaluated_depsgraph_get()
        n = 0
        for o in objs:
            try:
                ev = o.evaluated_get(dg)
                me = ev.to_mesh()
            except Exception:
                continue
            if me is None:
                continue
            me.calc_loop_triangles()
            n += len(me.loop_triangles)
            ev.to_mesh_clear()
        return n

    t_all, t_static, t_live, t_content = (tris(mine), tris(static_geo),
                                          tris(live), tris(content))
    print("TRIS  all %d = static %d + live %d + content %d  (content ships as "
          "ZERO: %.1f%% of the module)"
          % (t_all, t_static, t_live, t_content,
             100.0 * t_content / max(1, t_all)))

    # ------------------------------------------------------------- render
    # plate.png and depth.bin at the module's own rest state (add_props has
    # just left every set_*() at rest), so the plate shows what is BEHIND
    # every live object -- the face plate behind the drum, the scope well
    # behind the sweep, the slot behind the card.
    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"),
                         hide=live + content)

    # ------------------------------------------------------------- uBias
    # BRIEF step 3 / trap 24, via pipeline/ubias.py -- NOT the raw min(gaps)
    # one-liner, which lands on a silhouette pixel and was 11x wrong on IPM.
    # DNSM is the module ubias.py's own docstring warns about: "a module with
    # CURVED live geometry -- DNSM's chart drum, LOG's ribbon -- has silhouette
    # pixels everywhere and should expect the raw minimum to be meaningless."
    # Rendered with every blip of all eight query types visible, so the minimum
    # is over every state the plot can be in rather than over one.
    with tempfile.TemporaryDirectory() as td:
        liv = T.render_depth(scene, os.path.join(td, "_depth_live.bin"),
                             hide=content)
    U = UB.measure(np.ascontiguousarray(dep).ravel(),
                   np.ascontiguousarray(liv).ravel(), W, H)
    UB.report(U)
    ubias_m = round(float(U["ubias_m"]), 6)

    # ------------------------------------------------------------ geometry
    T.export_glb(sweep, os.path.join(OUT, "sweep.glb"))
    # ALL FOUR lamp materials have to be IN the glb, or the frontend cannot
    # swap to them.  At the module's rest only dnsm_lamp_off and _on are
    # assigned to anything exported (the courier dome is off, and amber/red are
    # only ever reached through set_qtype), so three domes are temporarily
    # given the other states purely so the glTF exporter emits the materials.
    # Rule 3: "LIVE, *if* the module declares both materials" -- DNSM declares
    # all four, in ctrl["qtype"]["mats"], so they are modelled and not invented.
    lamp_save = [d.data.materials[0] for d in domes]
    for i, key in enumerate(("off", "on", "amber", "red")):
        domes[i].data.materials[0] = qt["mats"][key]
    T.export_glb(blips_all + domes, os.path.join(OUT, "qtype.glb"))
    for d, m in zip(domes, lamp_save):
        d.data.materials[0] = m
    T.export_glb(drum_geo, os.path.join(OUT, "chart.glb"))
    T.export_glb(card_geo + [cdome], os.path.join(OUT, "courier.glb"))

    # ------------------------------------------------------------ anchors
    rm3 = root.matrix_world.to_3x3()
    ux = dirn(rm3, (1, 0, 0))                    # face RIGHT (slot +X)
    uv = dirn(rm3, mod.FACE_UP)                  # face UP, raked 60 deg
    un = dirn(rm3, mod.FACE_N)                   # face NORMAL, at the pilot
    cfwd = dirn(cc.matrix_world.to_3x3(), (0, 0, -1))
    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-cfwd).dot(un)))))
    assert (-cfwd).dot(un) > 0, "n must point AT the camera"
    print("OBLIQ face normal vs close-cam view axis %.4f deg  (survey: 0.000)"
          % obliq)
    print("RAKE  working face off the slot plane %.1f deg"
          % abs(math.degrees(mod.TILT)))

    # No module declares `axis` on a `rotate` control, and DNSM rakes its face
    # 60 deg off the slot plane, so rotating about root +Z would sweep a cone.
    # The beacon turns about the FACE NORMAL; the drum turns about the face's
    # own +X (build.py's drum pivot carries FROT = (TILT,0,0) and every facet
    # is placed by a rotation about that pivot's local X).
    sweep_hub = Vector(ctrl["sweep"]["anchor"])          # already world
    sweep_axis = [-c for c in T.to3(un)]   # +angle => CLOCKWISE on screen
    drum_piv = ch["pivot"]
    drum_hub = drum_piv.matrix_world.translation.copy()
    drum_axis = T.to3(ux)
    card_piv = co["pivot"]

    # px/m on the working face, straight off the close camera -- BRIEF section
    # 6 step 1, "screen size, before anything else".
    p0 = mod.project(scene, cc, root.matrix_world @ mod.fp(-0.100, 0.0, 0.0))
    p1 = mod.project(scene, cc, root.matrix_world @ mod.fp(0.100, 0.0, 0.0))
    ppm = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / (0.200 * mod.SCALE)
    print("SIZE  %.1f px/m on the face; the face is %.0f x %.0f px"
          % (ppm, 2 * mod.HW * mod.SCALE * ppm, 2 * mod.HL * mod.SCALE * ppm))

    # ------------------------------------------------------- the planes
    # Blender's own advance for THIS module's face.  DNSM has neither text()
    # nor mono_font() -- its helpers are _text() and _font() -- so typemetrics
    # would RAISE (NoModuleFont) rather than silently measure Blender's default
    # face, which reads 2.51x too wide.  Pass the font in.
    FONT = mod._font()
    assert FONT is not None, "the module could not resolve its mono face"
    print("FONT  %s" % FONT.filepath)

    def adv(size):
        return TM.measure_type(mod, size, font=FONT)["adv"]

    S_QUERY, S_CHART, S_CARD = 0.0098, 0.0076, 0.0072
    A_QUERY, A_CHART, A_CARD = adv(S_QUERY), adv(S_CHART), adv(S_CARD)

    def block(size, lead, left, top, nl, ncols, align="left"):
        t = TM.type_block(mod, size, lead_m=lead, left_m=left, top_m=top,
                          n_lines=nl, scale=mod.SCALE, align=align, font=FONT)
        t["n_cols"] = ncols
        return t

    def corners(o, u, v, hw, hh):
        return {k: dict(zip(("x", "y"), mod.project(
            scene, cc, o + u * (hw * sx) + v * (hh * sy))))
            for k, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                              ("bl", -1, -1), ("br", 1, -1))}

    # ---- query: the readout strip, top right of the face plate ------------
    # dnsm_readout_* is authored at fp(HW-0.014, HL-0.021, 0.007), align RIGHT,
    # so the RIGHT edge of the advance box is the anchor.  The rect is that
    # right edge minus N_QUERY columns.  h = 0.007 is the type's own plane,
    # 1.0 mm proud of the face plate's front face at h = PLATE_T/2 = 0.006.
    Q_RIGHT = mod.HW - 0.014
    Q_V = mod.HL - 0.021
    Q_H = 0.007
    q_hw = N_QUERY * A_QUERY / 2 + MARGIN
    q_cu = Q_RIGHT - N_QUERY * A_QUERY / 2
    q_hh = 0.006
    q_origin = root.matrix_world @ mod.fp(q_cu, Q_V, Q_H)
    q_lead = min(S_QUERY, 1.6 * q_hh)
    planes_local = []          # (name, kind, payload) -- rebuilt per pose
    query_rec = {
        "name": "query", "carrier": "face plate (h 0.006) + 1.0 mm",
        "origin": T.to3(q_origin), "u": T.to3(ux), "v": T.to3(uv),
        "n": T.to3(un),
        "half_w": q_hw * mod.SCALE, "half_h": q_hh * mod.SCALE,
        "type": block(S_QUERY, q_lead, -N_QUERY * A_QUERY / 2, 0.0,
                      1, N_QUERY),
        "local": list(mod.fp(q_cu, Q_V, Q_H)),
        "corners_px": corners(q_origin, ux, uv, q_hw * mod.SCALE,
                              q_hh * mod.SCALE),
    }
    # the SAME frame in BLENDER coordinates.  `origin`/`u`/`v`/`n` above are
    # T.to3()'d into three.js's Y-up space and must never be fed back into a
    # Blender ray-cast; keeping the two apart explicitly is cheaper than
    # finding out from a probe that reports `floor` 121/121.
    BL = {"query": (q_origin, ux, uv, q_hw * mod.SCALE, q_hh * mod.SCALE)}

    # ---- chart0..chart5: SIX TANGENT PLANES ON ONE HEXAGONAL DRUM --------
    # Facet k is built in the drum pivot's local frame at (x, y, DR_R-0.002)
    # and rotated to theta_k = 2 pi k / 6 about the pivot's local +X.  Its
    # three lines are FONT objects at local z = DR_R + 0.001, y = 0.0185 -
    # 0.0185 j, x from -0.070.  The plane is laid at the type's OWN plane,
    # which is 1.0 mm proud of the paper page (top face z = DR_R) and tangent
    # to the drum: the prism is convex, so a facet's tangent plane touches only
    # that facet and no other part of the drum can be in front of it.
    C_PZ = mod.DR_R + 0.001
    C_X0 = -0.070
    C_LEAD = 0.0185
    c_hw = N_CHART * A_CHART / 2 + MARGIN
    c_hh = C_LEAD + 0.003            # 3 lines: +/- one lead, plus half a cap
    c_cx = C_X0 + N_CHART * A_CHART / 2
    print("CHART facet half-chord %.4f m vs rect half_h %.4f m  (inset %.1f mm"
          " -- BRIEF step 4, do not declare a rect flush with its carrier)"
          % (mod.DR_R * math.sin(math.pi / mod.DR_FACETS), c_hh,
             1000 * (mod.DR_R * math.sin(math.pi / mod.DR_FACETS) - c_hh)))

    def chart_plane(k, phi_deg):
        """Facet k's tangent plane at drum rotation `phi_deg`, in three world
        coordinates.  `phi` is the extra rotation about the pivot's local +X;
        facet k then sits at theta_k + phi."""
        th = 2 * math.pi * k / mod.DR_FACETS + math.radians(phi_deg)
        c, s = math.cos(th), math.sin(th)
        o_l = Vector((c_cx, 0.0 * c - C_PZ * s, 0.0 * s + C_PZ * c))
        M = drum_piv.matrix_world
        M3 = M.to_3x3()
        o = M @ o_l
        u = (M3 @ Vector((1.0, 0.0, 0.0))).normalized()
        v = (M3 @ Vector((0.0, c, s))).normalized()
        n = (M3 @ Vector((0.0, -s, c))).normalized()
        return {
            "name": "chart%d" % k, "facet": k,
            "carrier": "drum facet %d paper page + 1.0 mm (tangent)" % k,
            "origin": T.to3(o), "u": T.to3(u), "v": T.to3(v), "n": T.to3(n),
            "half_w": c_hw * mod.SCALE, "half_h": c_hh * mod.SCALE,
            "type": block(S_CHART, C_LEAD, -N_CHART * A_CHART / 2, C_LEAD,
                          3, N_CHART),
            "rest_local": [list(o_l), [1.0, 0.0, 0.0], [0.0, c, s],
                           [0.0, -s, c]],
            "corners_px": corners(o, u, v, c_hw * mod.SCALE,
                                  c_hh * mod.SCALE),
        }, (o, u, v, c_hw * mod.SCALE, c_hh * mod.SCALE)

    # ---- courier: the card head, on a plane that RIDES the card ----------
    # dnsm_card_head is at card-local (-0.060, CARD_H/2-0.015, 0.0022), align
    # LEFT.  The plane is the type's own plane, 0.6 mm proud of the card's top
    # face (z = 0.0016).  The card slides along the face's +v.
    K_X0, K_Y = -0.060, mod.CARD_H / 2 - 0.015
    K_Z = 0.0022
    k_hw = N_CARD * A_CARD / 2 + MARGIN
    k_hh = 0.005
    k_cx = K_X0 + N_CARD * A_CARD / 2
    COURIER_DV = {"chart": 0.042, "import": -0.006, "empty": None}

    def courier_plane(state):
        dv = COURIER_DV[state]
        if dv is None:
            dv = COURIER_DV["chart"]           # card gone: park the plane
        card_piv.location = mod.fp(mod.CO_U, mod.CO_V + dv, 0.006)
        bpy.context.view_layer.update()
        M = card_piv.matrix_world
        M3 = M.to_3x3()
        o = M @ Vector((k_cx, K_Y, K_Z))
        u = (M3 @ Vector((1.0, 0.0, 0.0))).normalized()
        v = (M3 @ Vector((0.0, 1.0, 0.0))).normalized()
        n = (M3 @ Vector((0.0, 0.0, 1.0))).normalized()
        return {
            "name": "courier",
            "carrier": "chart card face (local z 0.0016) + 0.6 mm",
            "origin": T.to3(o), "u": T.to3(u), "v": T.to3(v), "n": T.to3(n),
            "half_w": k_hw * mod.SCALE, "half_h": k_hh * mod.SCALE,
            "type": block(S_CARD, min(S_CARD, 1.6 * k_hh),
                          -N_CARD * A_CARD / 2, 0.0, 1, N_CARD),
            "card_local": [k_cx, K_Y, K_Z],
            "corners_px": corners(o, u, v, k_hw * mod.SCALE,
                                  k_hh * mod.SCALE),
        }, (o, u, v, k_hw * mod.SCALE, k_hh * mod.SCALE)

    def build_planes(chart_deg, courier_state, bl=None):
        ps = [dict(query_rec)]
        if bl is not None:
            bl["query"] = BL["query"]
        for k in range(mod.DR_FACETS):
            rec, b = chart_plane(k, chart_deg)
            ps.append(rec)
            if bl is not None:
                bl[rec["name"]] = b
        rec, b = courier_plane(courier_state)
        ps.append(rec)
        if bl is not None:
            bl["courier"] = b
        return ps

    BLP = {}
    planes = build_planes(POSE_CHART_DEG, POSE_COURIER, BLP)
    print("TYPE  metrics measured in Blender (FONT.size is NOT an em):")
    for p in planes:
        t = p["type"]
        c = p["corners_px"]
        pm = (math.hypot(c["tr"]["x"] - c["tl"]["x"],
                         c["tr"]["y"] - c["tl"]["y"]) / (2 * p["half_w"]))
        print("   %-8s size %.5f -> adv %.6f m (ratio %.6f)  cap %.6f  base "
              "%.6f   %.1f px/m -> cap %.2f px, %d cols = %.1f px"
              % (p["name"], t["size_m"], t["adv_m"],
                 t["adv_m"] / t["size_m"] / mod.SCALE,
                 t["cap_m"], t["base_m"], pm, t["cap_m"] * pm,
                 t["n_cols"], t["n_cols"] * t["adv_m"] * pm))
        need_h = (t["n_lines"] - 1) * t["lead_m"] / 2 + t["cap_m"] / 2
        assert p["half_h"] >= need_h - 1e-9, (p["name"], p["half_h"], need_h)
        assert p["half_w"] >= t["n_cols"] * t["adv_m"] / 2 - 1e-9, p["name"]

    # ---- MEASURED: what actually crosses a declared rect, and is it live?
    # The audit's harness was not kept (BRIEF correction 11), so this rebuilds
    # the useful half of it.  What matters for check_occlusion.py check 4 is
    # the live/baked split of the occluders: baked ones are in depth.bin and
    # therefore in its offline oracle, LIVE ones are not.
    dg = bpy.context.evaluated_depsgraph_get()
    liveset = set(o.name for o in live)
    contentset = set(o.name for o in content)
    cam_o = cc.matrix_world.translation

    def probe(bl, n=11):
        """`bl` is the BLENDER-space (origin, u, v, half_w, half_h) tuple."""
        o, u, v, hw, hh = bl
        hits = collections.Counter()
        for i in range(n):
            for j in range(n):
                s = o + u * (hw * (2 * i / (n - 1) - 1)) \
                      + v * (hh * (2 * j / (n - 1) - 1))
                d = (s - cam_o).length
                ok, loc, nrm, idx, ob, mw = scene.ray_cast(
                    dg, cam_o, (s - cam_o).normalized(), distance=d - 0.001)
                if ok and ob is not None and ob.name not in contentset:
                    hits[("LIVE " if ob.name in liveset else "baked ")
                         + ob.name] += 1
        return hits

    def facing(bl):
        """The shader's own back-facing test: `den > -1e-6 -> continue`, i.e.
        a plane whose front face is turned away carries no visible text and
        nothing can be in front of it.  css3d.js sets backface-visibility
        hidden on every element, so the DOM agrees.  Applied here so the probe
        counts what the page counts."""
        o, u, v, hw, hh = bl
        return (cam_o - o).normalized().dot(u.cross(v).normalized()) > 1e-6

    def probe_all(ps, bl, tag):
        tot = 0
        out = {}
        for p in ps:
            b = bl[p["name"]]
            fw = facing(b)
            h = probe(b)
            nl = sum(v for k, v in h.items() if k.startswith("LIVE"))
            if fw:
                tot += nl
            out[p["name"]] = {"covered": sum(h.values()), "of": 121,
                              "live": nl, "front_facing": fw,
                              "by": dict(h.most_common(6))}
            print("   %-8s %-11s %3d/121 covered   live %d   %s"
                  % (p["name"], "front-facing" if fw else "BACK-FACING",
                     sum(h.values()), nl,
                     dict(h.most_common(4)) if h else "clear"))
        print("   [%s] LIVE geometry in front of a FRONT-FACING declared "
              "rect: %d" % (tag, tot))
        return out, tot

    print("PROBE  11x11 ray-cast per declared rect, close cam, EXPORT pose:")
    probe_json, probe_live = probe_all(planes, BLP, "rest")

    # THE SAME PROBE THROUGH THE DRUM'S WHOLE TURN.  The audit says "rotating
    # the drum brings the neighbouring facet between the camera and lines that
    # are going round the back, at 1.4 mm".  Measured here against the six
    # TANGENT planes, over 24 steps of 15 deg, with the back-facing planes
    # dropped exactly as the shader drops them.
    print("PROBE  the same six facet rects through a full drum turn "
          "(24 x 15 deg), back-facing facets skipped as the shader skips "
          "them:")
    spin_json = []
    worst_live = 0
    for step in range(24):
        phi = -15.0 * step
        row = {"deg": phi, "facets": {}}
        for k in range(mod.DR_FACETS):
            p, b = chart_plane(k, phi)
            if not facing(b):
                continue                       # back-facing: shader skips it
            h = probe(b, n=9)
            nl = sum(v for kk, v in h.items() if kk.startswith("LIVE"))
            worst_live = max(worst_live, nl)
            row["facets"][p["name"]] = {"covered": sum(h.values()), "of": 81,
                                        "live": nl,
                                        "by": dict(h.most_common(3))}
        spin_json.append(row)
        print("   %+7.1f deg  %s" % (phi, "   ".join(
            "%s %d/81%s" % (nm, d["covered"],
                            " LIVE %d [%s]" % (d["live"], ",".join(
                                k[5:] for k in d["by"] if k.startswith("LIVE")))
                            if d["live"] else "")
            for nm, d in sorted(row["facets"].items()))))
    print("   worst LIVE coverage of a front-facing facet rect, over the "
          "whole turn: %d/81" % worst_live)

    # ------------------------------------------------ THE CAPTURE POSE
    # Everything from here on is rendered in the pose module.js rests in.
    lit = qt["mats"]["red"] if POSE_QTYPE == "NX" else (
        qt["mats"]["amber"] if POSE_QTYPE == "AXFR" else qt["mats"]["on"])
    qi = mod.QTYPES.index(POSE_QTYPE)
    for k, d in enumerate(domes):
        on = (k == qi) or (POSE_QTYPE == "AXFR" and mod.QTYPES[k] != "NX")
        d.data.materials[0] = lit if on else qt["mats"]["off"]
    drum_piv.rotation_euler = (mod.TILT + math.radians(POSE_CHART_DEG), 0, 0)
    card_piv.location = mod.fp(mod.CO_U,
                               mod.CO_V + COURIER_DV[POSE_COURIER], 0.006)
    cdome.data.materials[0] = qt["mats"]["off"]
    bpy.context.view_layer.update()
    live_rest = [o for o in live
                 if o not in set(blips_all) or o in set(blips[POSE_QTYPE])]
    if POSE_COURIER == "empty":
        live_rest = [o for o in live_rest if o not in set(card_geo)]

    # ------------------------------- the readout STRINGS, and their type
    # DNSM authors all three of its readouts, unlike PKT/FMM/IPM, so the
    # ground truth is the module's OWN type -- except for the query readout,
    # which is authored align='RIGHT' and is re-made here LEFT-aligned and
    # padded, because that is the model the DOM uses.  The two are asserted
    # to land in the same place below, so the substitution is MEASURED and not
    # assumed.  Made AFTER plate.png, depth.bin and every glb, so it appears
    # in none of them.
    TEXT = collections.OrderedDict()
    TEXT["query"] = [mod.QREADOUT[POSE_QTYPE].rjust(N_QUERY)]
    for k in range(mod.DR_FACETS):
        TEXT["chart%d" % k] = list(mod.CHART_PAGES[k])
    TEXT["courier"] = ["CHART 44-12"]

    q_stand = mod._text("dnsm_dom_query", TEXT["query"][0], S_QUERY,
                        bpy.data.materials["dnsm_glyph"],
                        mod.fp(q_cu - N_QUERY * A_QUERY / 2, Q_V, Q_H),
                        rot=mod.FROT, align='LEFT')
    mod._adopt(q_stand, root)
    bpy.context.view_layer.update()
    lo_a, hi_a = bbox_world([q_stand])
    lo_b, hi_b = bbox_world([readouts[POSE_QTYPE]])
    dpad = max(abs(lo_a[i] - lo_b[i]) for i in range(3))
    dpad2 = max(abs(hi_a[i] - hi_b[i]) for i in range(3))
    print("ALIGN  padded LEFT stand-in vs the module's authored align=RIGHT "
          "readout: bbox agrees to %.7f m / %.7f m  (%.4f px at %.0f px/m)"
          % (dpad, dpad2, max(dpad, dpad2) * ppm, ppm))
    assert max(dpad, dpad2) < 2e-5, "padStart() does not reproduce align RIGHT"

    per_plane = {"query": [q_stand]}
    for k in range(mod.DR_FACETS):
        per_plane["chart%d" % k] = [o for o in chart_txt
                                    if o.name.startswith("dnsm_chart_txt_%d_"
                                                         % k)]
    per_plane["courier"] = list(card_head)

    # WHICH TYPE IS ACTUALLY VISIBLE AT THE POSE.  gt_platen0.png is what
    # check_text.py takes its ROW BANDS from, and a row band with no DOM ink is
    # a FAIL -- so it must contain the type the page really paints, not every
    # string the drum carries.  At rest only ONE facet is in the window: the
    # other five are behind dnsm_face_under / dnsm_face_over, which is the
    # audit's finding and the whole reason this module is OCCLUDED.  Decided by
    # the ray-cast probe above, not by hand.
    def line_visible(bl, tp, j, body, n=7):
        """Is line `j` of this readout actually visible from the close camera?

        Sampled ON THE DECLARED PLANE, across the line's own INK columns, in
        Blender coordinates -- not at the FONT object's world bounding-box
        centre, which for a face raked 60 deg lies INSIDE the glyph solid and
        reports the paper behind it as an occluder.  Every sample must be
        clear.  This is what decides what goes into gt_platen0.png, and
        check_text.py turns a Blender row band with no DOM ink into a FAIL --
        so it is measured here, at this pose, and not judged."""
        if not facing(bl):
            return False, "back-facing"
        o, u, v, hw, hh = bl
        t = tp["type"]
        c0 = len(body) - len(body.lstrip())
        c1 = len(body.rstrip())
        if c1 <= c0:
            return False, "empty"
        y = t["top_m"] - j * t["lead_m"]
        for i in range(n):
            col = c0 + (i + 0.5) * (c1 - c0) / n
            s_ = o + u * (t["left_m"] + col * t["adv_m"]) + v * y
            d = (s_ - cam_o).length
            ok, loc, nrm, idx, ob, mw = scene.ray_cast(
                dg, cam_o, (s_ - cam_o).normalized(), distance=d - 0.0008)
            if ok and ob is not None and ob.name not in contentset:
                return False, ob.name
        return True, None

    vis_lines, hid_lines = {}, {}
    print("VISIBLE type at the pose, per LINE, by ray-cast on the plane:")
    for p in planes:
        nm = p["name"]
        objs = per_plane[nm]
        for j, body in enumerate(TEXT[nm]):
            if j >= len(objs):
                continue
            ok_, by = line_visible(BLP[nm], p, j, body)
            if ok_:
                vis_lines.setdefault(nm, []).append(objs[j].name)
            else:
                hid_lines.setdefault(nm, []).append([objs[j].name, by])
        print("   %-8s visible %d/%d   %s" % (
            nm, len(vis_lines.get(nm, [])), len(TEXT[nm]),
            "hidden by " + ", ".join(sorted({b for _, b in
                                             hid_lines.get(nm, [])}))
            if hid_lines.get(nm) else "all clear"))
    visible_planes = [p["name"] for p in planes if p["name"] in vis_lines]
    stand_ins = [o for nm in visible_planes for o in per_plane[nm]
                 if o.name in vis_lines[nm]]
    assert not (set(stand_ins) & set(plate)) and not (set(stand_ins)
                                                      & set(live))

    inks = {}
    for nm in visible_planes:
        fn = os.path.join(OUT, "gt_type_%s.png" % nm)
        T.render_colour(scene, fn, visible=per_plane[nm])
        inks[nm], cnt = median_ink(fn)
        print("INK   %-8s median rgb%s over %d covered px"
              % (nm, tuple(inks[nm]), cnt))
    # the facets that are hidden at rest carry the same ink material as the
    # facet that is not, so they take the same measured colour
    for p in planes:
        if p["name"] not in inks:
            inks[p["name"]] = inks.get("chart0") or inks["query"]
        p["ink"] = inks[p["name"]]

    T.render_colour(scene, os.path.join(OUT, "gt_platen0.png"),
                    visible=stand_ins)
    T.render_colour(scene, os.path.join(OUT, "gt_platen_all.png"),
                    visible=[o for nm in TEXT for o in per_plane[nm]])
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"),
                    visible=live_rest)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + live_rest)

    # ---------------------------------------------------------- scene.json
    # Every probe on a VISIBLE STATIC surface (BRIEF trap 7).
    rows = T.verify_depth(scene, cc, dep, [
        ("face under front", root.matrix_world @ mod.fp(0.200, -0.020, 0.006)),
        ("face left front", root.matrix_world @ mod.fp(-0.200, -0.100, 0.006)),
        ("window trim top", root.matrix_world @ mod.fp(0.142, 0.106, 0.013)),
        ("courier slot lip", root.matrix_world @ mod.fp(0.142, -0.066, 0.030)),
    ])
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-20s want %.5f  got %.5f  err %+.5f"
              % (nm, want, got, err))

    def rect(objs, pad=8):
        return mod.clamp_rect(mod.bbox_rect(scene, cc, objs, pad=pad), W, H)

    def names(objs):
        return [o.name for o in objs]

    ring = [mod.fp(mod.SC_U + math.sin(math.radians(a)) * (mod.SC_R + 0.014),
                   mod.SC_V + math.cos(math.radians(a)) * (mod.SC_R + 0.014),
                   mod.SC_H) for a in range(0, 360, 15)]
    lamp_pts = [mod.fp(u + du, v, h) for u in qt["lamp_us"]
                for du in (-0.026, 0.026)
                for v, h in ((mod.LABEL_V - 0.010, 0.006),
                             (mod.LAMP_V + 0.013, 0.014))]
    win = [mod.fp(mod.WU0, mod.WV0, 0.0), mod.fp(mod.WU1, mod.WV0, 0.0),
           mod.fp(mod.WU0, mod.WV1, 0.0), mod.fp(mod.WU1, mod.WV1, 0.0)]
    slot_pts = [mod.fp(mod.CO_U + du, mod.CO_V + dv, 0.006)
                for du in (-0.092, 0.092) for dv in (-0.022, 0.086)]

    j = {
        "render": {"w": W, "h": H},
        "camera": T.cam_json(scene, cc),
        "lights": T.lights_json(scene, close_tags),
        "world_bg": list(scene.world.node_tree.nodes["Background"]
                         .inputs[0].default_value),
        "colour": {"view_transform": scene.view_settings.view_transform,
                   "look": scene.view_settings.look,
                   "exposure": scene.view_settings.exposure},
        # MEASURED on the real page with check/sweep_knob.mjs + compare.py and
        # a three-point parabola; NOT the fleet constant 0.65, which is nobody's
        # optimum.  See modules/DNSM/NOTES.md for the sweep table.
        "light_gain": LIGHT_GAIN,
        "env_intensity": 0.0,    # measured optimum, monotonically; do not add
        "raytrace": 1,
        "scale": mod.SCALE,
        "rake_deg": abs(math.degrees(mod.TILT)),
        "obliquity_deg": obliq,
        "px_per_m": ppm,
        "ubias_m": ubias_m,
        "ubias": {"raw_min_m": round(float(U["raw_min"]), 8),
                  "eroded_min_m": round(float(U["min"]), 8),
                  "p1_m": round(float(U["p1"]), 8),
                  "median_m": round(float(U["median"]), 8),
                  "n_raw": U["n_raw"], "n_inner": U["n_inner"],
                  "plateau": U["plateau"],
                  "plateau_frac": round(float(U["plateau_frac"]), 5),
                  "emerging": bool(U["emerging"])},
        "tris": {"all": t_all, "static": t_static, "live": t_live,
                 "content": t_content},
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "panel": {"u": T.to3(ux), "v": T.to3(uv), "n": T.to3(un),
                  "origin": T.to3(root.matrix_world @ Vector((0, 0, 0)))},
        "props": {
            "sweep": {
                "glb": "sweep.glb", "kind": "rotate",
                "label": ctrl["sweep"]["label"],
                "hub": T.to3(sweep_hub), "axis": sweep_axis,
                "pivot_px": dict(zip(("x", "y"),
                                     mod.project(scene, cc, sweep_hub))),
                "range": list(ctrl["sweep"]["range"]),
                "spin_deg_s": 96.0,
                "hotspot": mod.clamp_rect(
                    mod.pts_rect(scene, cc, root, ring, pad=2), W, H)},
            "qtype": {
                "glb": "qtype.glb", "kind": "states",
                "label": qt["label"], "states": list(mod.QTYPES),
                "labels": list(mod.QLABELS),
                "readouts": {q: mod.QREADOUT[q] for q in mod.QTYPES},
                "blips": {q: names(blips[q]) for q in mod.QTYPES},
                "domes": names(domes),
                # DERIVED INTEGER STATE, emitted rather than re-derived in JS
                # (BRIEF step 2 / trap 32): which dome burns, and in which
                # material, for each query type.
                "lit": {q: [1 if (k == i or (q == "AXFR"
                                             and mod.QTYPES[k] != "NX"))
                            else 0 for k in range(len(mod.QTYPES))]
                        for i, q in enumerate(mod.QTYPES)},
                "lamp_mat": {q: ("red" if q == "NX" else
                                 ("amber" if q == "AXFR" else "on"))
                             for q in mod.QTYPES},
                "mats": {k: m.name for k, m in qt["mats"].items()},
                "hotspot": mod.clamp_rect(
                    mod.pts_rect(scene, cc, root, lamp_pts, pad=3), W, H)},
            "chart": {
                "glb": "chart.glb", "kind": "rotate",
                "label": ch["label"], "facets": mod.DR_FACETS,
                "deg_per_facet": 360.0 / mod.DR_FACETS,
                "hub": T.to3(drum_hub), "axis": drum_axis,
                "pages": [list(pg) for pg in mod.CHART_PAGES],
                "hotspot": mod.clamp_rect(
                    mod.pts_rect(scene, cc, root, win, pad=4), W, H)},
            "courier": {
                "glb": "courier.glb", "kind": "states",
                "label": co["label"], "states": list(mod.COURIER_STATES),
                "card": names(card_geo), "dome": cdome.name,
                "up_axis": T.to3(uv),
                # metres along +v from the card's EXPORTED (rest) position
                "slide_m": {k: ((v - COURIER_DV["chart"]) * mod.SCALE
                                if v is not None else None)
                            for k, v in COURIER_DV.items()},
                "lamp_mat": {"chart": "off", "import": "amber",
                             "empty": "off"},
                "mats": {k: m.name for k, m in co["mats"].items()},
                "head": "CHART 44-12",
                "hotspot": mod.clamp_rect(
                    mod.pts_rect(scene, cc, root, slot_pts, pad=3), W, H)},
        },
        "text_planes": planes,
        "ink": inks,
        "pose": {"qtype": POSE_QTYPE, "chart_deg": POSE_CHART_DEG,
                 "courier": POSE_COURIER, "sweep_deg": POSE_SWEEP_DEG},
        "readout_text": [TEXT[p["name"]] for p in planes],
        "visible_at_pose": visible_planes,
        "visible_lines": {k: list(v) for k, v in vis_lines.items()},
        "hidden_lines": {k: [list(x) for x in v]
                         for k, v in hid_lines.items()},
        "depth_verify": [{"name": n_, "analytic": w, "baked": g, "err": e}
                         for n_, w, g, e in rows],
        "probe": probe_json,
        "probe_live_hits": probe_live,
        "probe_spin": spin_json,
        "probe_spin_worst_live": worst_live,
    }
    with open(os.path.join(OUT, "scene.json"), "w") as f:
        json.dump(j, f, indent=1)
    with open(os.path.join(OUT, "materials.json"), "w") as f:
        json.dump(T.materials_json(), f, indent=1)

    # ------------------------------------------------ THE ROTATED VARIANT
    # Same plate, same depth, same glbs -- both are baked-only and the drum is
    # live -- so this is nothing but new plane frames and a new pose.  It is
    # how the DRUM ROTATION goes through check_occlusion.py:
    #   PAGE=.../modules/DNSM/?scene=scene_rot.json
    #   SCENE=scene_rot.json CODE=DNSM python3 check_occlusion.py <dir>
    rot_planes = build_planes(ROT_CHART_DEG, ROT_COURIER, {})
    for p in rot_planes:
        p["ink"] = inks[p["name"]]
    jr = json.loads(json.dumps(j))
    jr["text_planes"] = rot_planes
    jr["pose"] = {"qtype": POSE_QTYPE, "chart_deg": ROT_CHART_DEG,
                  "courier": ROT_COURIER, "sweep_deg": POSE_SWEEP_DEG}
    with open(os.path.join(OUT, "scene_rot.json"), "w") as f:
        json.dump(jr, f, indent=1)
    print("ROT   -> scene_rot.json (drum %.0f deg, courier %s)"
          % (ROT_CHART_DEG, ROT_COURIER))

    # put the pose back for anything that runs after this
    card_piv.location = mod.fp(mod.CO_U,
                               mod.CO_V + COURIER_DV[POSE_COURIER], 0.006)
    bpy.context.view_layer.update()
    print("EXPORT OK ->", OUT)


# MEASURED, not chosen: check/sweep_knob.mjs KNOB=gain over 0.40..0.85 on a
# 0.05 grid and then 0.58..0.63 on a 0.01 grid, every grab scored with
# check/compare.py, a three-point parabola through the minimum and its two
# neighbours both times:
#   0.05 grid  0.55/0.60/0.65 = 4.598/4.539/4.577  ->  vertex 0.6054
#   0.01 grid  0.59/0.60/0.61 = 4.544/4.539/4.541  ->  vertex 0.6021
# The full table is in live3d/modules/DNSM/NOTES.md section 5.3.  0.65 is a
# 0.1-grid artefact and is nobody's optimum; on DNSM it costs 0.036 rms.
LIGHT_GAIN = 0.602


# ===========================================================================
# THE REFIT PORT -- a SECOND entry point, deliberately separate from main().
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_dnsm.py -- refit
#
# main() above rebuilds the shell and RE-RENDERS plate.png, depth.bin and all
# six gt_*.png.  Running it would invalidate every number in
# live3d/RESULTS.md and in modules/DNSM/NOTES.md -- and on DNSM it would also
# re-render the 407,640 triangles of content type that ship as ZERO.  This
# entry point does none of that: it builds the port ALONE IN AN EMPTY SCENE,
# writes assets/DNSM/refit.glb and merges a "refit" block into the existing
# scene.json.  Nothing else in assets/DNSM/ is opened for writing.
# FIX_UPLOAD.md section 0, decision 3.
#
# ROOT SCALE IS 1.0 ON THIS PATH AND IS NOT PASSED, even though DNSM's own
# `scene.json -> scale` is 0.78 and main() really does author inside a 0.78
# root.  FIX_UPLOAD 12.15 item 2: both fitting entry points CLEAR THE SCENE
# and build in WORLD coordinates from the solver's own world-space frame, so
# there is no root to be inside.  Passing 0.78 here would divide every
# dimension by it and ship the port 1.282x too big with its rail's span
# unchanged.  `build()` calls `check_root_scale()`, which REFUSES a non-unit
# value in an empty scene; let it refuse.
#
# NO typemetrics ON THIS PATH.  main() resolves `mod._font()` and passes
# `font=FONT` into `TM.measure_type()` / `TM.type_block()`, because DNSM has
# neither `text()` nor `mono_font()` and typemetrics would RAISE.  The port's
# `REFIT` lettering is STAMPED type and `refit_port._engrave()` loads Courier
# New Bold itself, so this entry point never reaches typemetrics at all.
#
# WHERE IT SITS, AND WHY IT IS NOT (280, 683) AT 62 px.
# FIX_UPLOAD 3.3 tables (280, 683) at 62 px, "panel lower apron, below the
# lamp row", and flags it as the one anchor in the fleet that "straddles a
# depth step (min 0.841 vs median 1.088)".  It does, and the step is a CLIFF,
# not a fillet: `depth.bin` down x = 280 reads 0.8408 at y 656..679 and
# 1.0981 at y 680 -- a 257 mm wall between two rows.  Above it is the
# instrument's own faceplate, which the port may not bolt to; below it is a
# 40 px shelf with the 720 px frame edge under it.  Neither band takes a
# 56 px port, let alone 62, and the solver says so at every size and every
# in-plane rotation:
#
#     refit_port.py DNSM 280 683 62
#       -> OFF FRAME, seat 135.6 mm > cap 4.2 mm
#     refit_port.py DNSM 280 700 40 --window 250,310,684,716 --sweep-y 682,719
#       -> seat 252..264 mm at y 682..702 (the envelope reaches up onto the
#          faceplate, 257 mm nearer) and OFF FRAME from y 704 down.
#
# The carrier that IS buildable is the DESK the panel hangs in front of: one
# exact plane (least-squares residual p50, p95 and max all 0.00000 m) running
# from x 106..219 down the left of the frame and turning right along the sill
# under the panel.  The port goes on its vertical arm, which is the fleet's
# learned bottom-left corner, 100 % solid behind, and clear of all four of
# this module's control hotspots and all eight declared readout rects.
#
# Sweep any of it yourself, with no Blender in the loop:
#
#   python3 live3d/pipeline/refit_port.py DNSM 170 690 56 --window 140,200,662,716
#   python3 live3d/pipeline/refit_port.py DNSM 280 683 62
#   python3 live3d/pipeline/refit_port.py DNSM 170 690 56 --sweep-y 440,714
#
# AND WHY IT IS NOT y 600, WHICH IS EQUALLY BUILDABLE.
# FIX_UPLOAD 12.16 item 5 and 12.17 item 4: the docket decides.  Measured on
# the running page with a real pointer, DNSM's docket is 520 x 317.9 px and
# `placeDocket()` clamps its y to `H - h - 12` = 390.  At (170, 600) the
# winning candidate is `[cx + 40, cy - h/2]` clamped to (12, 390), which
# covers x 12..532 y 390..708 -- and measured on the page that is
# **5,680.6 px^2 of an 5,681 px^2 port hotspot: 100 % of it**, plus 71 % of
# the mast and 71 % of the caption.  At y >= 685 the winner flips to
# `[cx - w - 40, cy - h - 26]`, the ABOVE candidate, at (12, 341) -- and the
# port loses 12 %, the mast and the caption nothing, and no control centre is
# buried on either.  The flip is a 5 px cliff between y 680 and y 685 and it
# is the whole reason for this anchor.  It holds for every docket height up
# to ~320 px and reverts at ~330; DNSM's docket is 317.9 and `dirty` is false
# (`status.json -> DNSM.source_rev` is null), so that is the standing value.
DNSM_REFIT = dict(px=170, py=690, port_px=56,
                  # the port's own projected hexagon bbox, held inside the
                  # desk's left edge (x 104 at y 670) and the panel's own
                  # silhouette (x 220).  FIX_UPLOAD 12.16 item 4: the window
                  # is about HOW FAR YOU ARE EXTRAPOLATING as well as what is
                  # in it, so it is the size of the thing being built.
                  carrier_window=(140, 200, 662, 716),
                  label="REFIT",
                  # 0.060 W = 2.1 mm at 1620 px/m is 3.4 px on screen -- the
                  # same smear FIX_UPLOAD 12.9 cut on KVS, and 532 triangles.
                  mark=None,
                  # The 1.3 W sub-base is for a featureless bulkhead (LOG,
                  # MTA).  DNSM's desk arm is 107 px wide at this row and a
                  # 1.3 W footprint is 84 px; it would reach the desk's own
                  # left edge and the panel's silhouette at once.  Off.
                  sub_base=False, service_rail=True)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(DNSM_REFIT)
    A = RP.solve_anchor(CODE, K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"])
    P = RP.build("dnsm_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export(CODE, A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))


# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_dnsm.py -- mast
#
# Same contract as `refit`: an empty scene, world coordinates, root_scale 1.0
# not passed, assets/DNSM/mast.glb plus a "mast" block merged into the
# existing scene.json, and nothing else opened for writing.
#
# THE RAIL IS NOT AVAILABLE, so this takes the `--at PX,PY` route.
# STATUS_AT_A_GLANCE 11.2 hangs the mast off the port's own service rail at
# >= 1.5 W along the carrier's `u`, and `u` is screen-right.  The port sits at
# x 170 on a desk arm whose right-hand edge is the panel's silhouette at
# x 220: 1.5 W is 52 mm, which is 85 px, so the rail would run straight into
# the faceplate before the mast's own bracket started.  `--at` is a
# first-class route (STATUS_AT_A_GLANCE 16.2) and four of the seven built
# modules take it.  `mast.rail_ramp_m`, `mast.rail_span_m` and
# `mast.evidence.rail_bbox_px` are therefore all `null`, which is what
# STATUS_AT_A_GLANCE 16.1 item 5 says they must be on this route.
#
# WHERE IT SITS.  The sill arm of the same desk plane the port is on, under
# the panel, 100 % solid behind and at the same 1.09 m depth. The band is
# y 680..719 -- 40 px, with the faceplate 257 mm nearer above it and the
# frame edge below it -- and `_solve_lift()` refuses anything whose envelope
# reaches over the step, which caps the fitting at 120 px:
#
#     status_mast.py DNSM --at 240,710 --m 6 --px 140   -> REFUSED, no lift
#     status_mast.py DNSM --at 240,712 --m 6 --px 120   -> envelope to y 720.2
#
# x 240 rather than x 200: the port moved down onto the sill for the docket's
# sake (see DNSM_REFIT), and at (200, 710) the mast's hotspot and the port's
# overlapped by 771 px^2.  At 240 the gutter between the two drawn envelopes
# is 33.3 px and the two hotspots clear each other by 21.6 px.
#
# RAKE 0, AND THE MINIMUM IS THE TRAP AGAIN.  `--rakes` reads a minimum of
# 3.46 deg at rake 30 against 30.14 deg at rake 0, and STATUS_AT_A_GLANCE
# 17.5 and 18.8 both say not to take it: the criterion is the
# `px_per_m_carrier` v:n ratio.  DNSM's is 1566.6 / 534.3 = 2.93, which is
# the rake-0 band -- MTA 2.05 and MQB 4.59 both ship 0, and every module that
# rakes reads 0.74..1.57 (IPM 0.74, KVS 0.92, OTA 0.94, PKT 1.57).  The
# mast's own B axis peaks at rake 19 and the whole gain there is 5.8 %.
# See modules/DNSM/NOTES.md for the fleet regression.
DNSM_MAST = dict(mast_px=120, rake_deg=0.0, m=6, kind="defensive",
                 numbers=False,
                 at=(240, 710),
                 carrier_window=(170, 310, 692, 718))


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(DNSM_MAST)
    A = SMT.solve_mast(CODE, mast_px=K["mast_px"], rake_deg=K["rake_deg"],
                       m=K["m"], kind=K["kind"], numbers=K["numbers"],
                       px=K["at"][0], py=K["at"][1],
                       carrier_window=K["carrier_window"])
    P = SMT.build("dnsm_mast", A["frame_blender"], A["carrier_blender"],
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
