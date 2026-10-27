"""
LIVE-3D EXPORT — MTA close-up  ("Subspace Comms Relay / Message Torpedo Room").

A thin layer on top of three-exploration/pipeline/transliterate.py, following
live3d/CONVERSION_BRIEF.md.  The module's REAL build.py is imported in place by
live3d/pipeline/module_loader.py, so there is no MTA snapshot to go stale.

    plate.png       shell + MTA STATIC parts, MINUS the content type.
                    R["static"] exists on MTA and partitions cleanly (survey:
                    static n control-owned = 0, in-neither = 0) -- but it still
                    CONTAINS the webhook slip's three FONT objects, which are
                    content text, so they are subtracted here.  Everything the
                    plate must show BEHIND a live object (the pigeonhole
                    recesses behind the envelopes, the tube bed behind the
                    capsule, the wheel well behind the scrambler, the cradle
                    behind the handset) is static and stays baked.

    capsule.glb     the pneumatic message capsule   -- live, rides the tube
    envelopes.glb   ten queued envelopes            -- live, appear/disappear
    wheel.glb       the STARTTLS scrambler          -- live, rotates
    handset.glb     the comms handset               -- live, hinges

    The seven baked `capsule` frames are REPLACED by one live capsule that
    travels the rail continuously and swings nose-out of the bell.  That is the
    point of the conversion (BRIEF step 2 rule 1: "frames are a baked
    approximation of movement").

    NOT EXPORTED AT ALL: the content type.  18 FONT objects --
      mta_env_<0..9>_id     the queued message IDs
      mta_odo_<state>       the queue-depth odometer (5 coincident alternates)
      mta_slip_txt_<0..2>   the X-NOTIFY webhook delivery slip
    -- are values a player reads, so per README section 12 they become DOM and
    are excluded from the plate, from the depth pass and from every glb.
    STAMPED lettering stays geometry: the nameplate, the top plate, OUTBOUND
    QUEUE, POST, HANDSET, STARTTLS, and the scrambler's 12 rotor letters (the
    last of these ride the live wheel, in wheel.glb, and rotate with it).

    text_planes     SEVEN readout rects: one per pigeonhole COLUMN (two rows of
                    IDs each), the odometer window, and the webhook slip.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_mta.py
"""
import bpy, math, os, sys, json, collections
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
from module_loader import load_module, check_snapshots           # noqa: E402

shell = T.shell
slots = T.slots
CODE = "MTA"
OUT = os.path.join(LIVE3D, "assets", CODE)


def dirn(m3, v):
    """Transform a DIRECTION by a rotation matrix and normalise."""
    return (m3 @ Vector(v)).normalized()


def modal_ink(path):
    """The ink colour, measured off Blender's own render of THIS module's type.

    MEASURED, not assumed (BRIEF section 7 rule 7): albedo-neutral ink under
    warm area lights renders warm and must stay warm.  Two things had to be
    checked rather than copied from export_kvs:

      * Blender hands `image.pixels` back for an 8-bit sRGB PNG ALREADY
        DISPLAY-ENCODED here -- byte/255, not linear.  Re-encoding with an sRGB
        transfer function turns the true rgb(85,77,71) into rgb(157,150,146),
        which is a plausible-looking wrong answer.  Verified against the PNG
        bytes read back with the stdlib decoder.
      * MTA's type is SMALL in the close frame (a 6-char message ID is 58 px
        wide with a 10 px cap), so max alpha in gt_type_ids.png is 224/255 and
        a "most common FULLY OPAQUE pixel" rule returns nothing.  Blender writes
        STRAIGHT alpha -- confirmed: mean RGB is flat across every alpha bucket
        -- so a half-covered pixel still carries the ink's own colour.  The
        MEDIAN over alpha > 0.5 is used; the mode is unstable at these counts
        (23 px, and it picked a specular highlight)."""
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


def font_metrics(mod, size, mat):
    """MEASURE the advance, in metres, the way BRIEF section 4 demands.

    Blender's FONT.size is NOT an em (KVS: size 0.031 advances 0.0100 m, a
    ratio of 0.32), so the frontend needs the advance and solves its font-size
    from the browser face's own measured em.  bbox("M"*21) - bbox("M") is
    exactly 20 advances and needs no render to read off.  Cap height comes off
    the same bbox."""
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    tmp = []
    for n in (1, 21):
        o = mod.text("__adv%d" % n, "M" * n, size, mat, (0, 0, 0))
        tmp.append(o)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    for o, n in zip(tmp, (1, 21)):
        me = o.evaluated_get(dg).to_mesh()
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        out[n] = (max(xs) - min(xs), max(ys) - min(ys))
        o.evaluated_get(dg).to_mesh_clear()
    for o in tmp:
        bpy.data.objects.remove(o, do_unlink=True)
    adv = (out[21][0] - out[1][0]) / 20.0
    return adv, out[1][1]                    # advance, cap height of 'M'


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
    # Copied VERBATIM out of cockpit/modules/MTA/build.py main(): MTA builds
    # its close camera inline rather than in a close_rig() the survey can call,
    # and the close-up must frame the module identically to the shipped baked
    # close plate or the transition's match dissolve breaks.  Note fit_camera
    # is fed R["all"] -- including the hidden frames and the content type --
    # exactly as main() feeds it, because their bound boxes participate.
    ctr = root.matrix_world @ Vector((0.0, 0.0, mod.PZ + 0.02))
    view = (main_cam.matrix_world.translation - ctr).normalized()
    bpy.ops.object.camera_add(location=ctr + view * 0.90)
    cc = bpy.context.object
    cc.name = "mta_closecam"
    cc.data.lens = 50.0
    ctr = mod.fit_camera(scene, cc, mine, ctr, view, frac=0.94)

    up = (root.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
    right = view.cross(up).normalized()
    close_tags = {}
    for off, energy, size, col in (
            (right * 0.50 + up * 0.46 + view * 0.34, 0.62, 0.55,
             (1.0, 0.88, 0.70)),
            (-right * 0.58 + up * 0.22 + view * 0.42, 0.40, 0.70,
             (0.64, 0.78, 1.00)),
            (up * 0.30 + view * 0.46 - right * 0.05, 0.26, 0.50,
             (1.0, 0.93, 0.80)),
            (-up * 0.44 + view * 0.36, 0.20, 0.60, (1.0, 0.84, 0.62))):
        p = ctr + off
        bpy.ops.object.light_add(type='AREA', location=p)
        L = bpy.context.object
        L.data.energy, L.data.size = energy, size
        L.data.color = col
        L.rotation_euler = (ctr - p).to_track_quat('-Z', 'Y').to_euler()
        close_tags[L.name] = "close"
    scene.camera = cc
    bpy.context.view_layer.update()

    # ------------------------------------------- the live / baked split
    Q = ctrl["queue"]
    cap_frames = ctrl["capsule"]["frame_objs"]
    REST = mod.CAPSULE_REST
    cap_rest = list(cap_frames[REST])
    env_geom = [[o for o in g if not o.name.endswith("_id")]
                for g in Q["env_objs"]]
    env_ids = [o for g in Q["env_objs"] for o in g if o.name.endswith("_id")]
    digits = Q["digits"]
    slip_txt = [o for o in R["static"] if o.name.startswith("mta_slip_txt")]
    wheel = list(ctrl["scrambler"]["objs"])
    hand = list(ctrl["handset"]["objs"])
    hand_piv = ctrl["handset"]["pivot"]

    # CONTENT TEXT: values a player reads.  Excluded from plate, depth, glbs.
    content = env_ids + list(digits.values()) + slip_txt
    assert len(content) == 18, len(content)

    live = cap_rest + [o for g in env_geom for o in g] + wheel + hand
    static_geo = [o for o in R["static"] if o not in set(slip_txt)]
    plate = shell_meshes + static_geo
    assert not (set(live) & set(plate)), "a live object is also in the plate"
    assert not (set(content) & set(plate)), "content type is in the plate"
    # every capsule frame except the exported one simply does not exist in the
    # output: it is one live object that moves.
    cap_dead = [o for i, g in enumerate(cap_frames) if i != REST for o in g]
    hide_from_depth = live + content + cap_dead
    print("split: %d plate objects (%d shell + %d static), %d live "
          "(%d capsule, %d envelope, %d wheel, %d handset), %d content type"
          % (len(plate), len(shell_meshes), len(static_geo), len(live),
             len(cap_rest), sum(len(g) for g in env_geom), len(wheel),
             len(hand), len(content)))

    # rest pose for the plate / depth / ground-truth renders
    hand_piv.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()

    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"),
                         hide=hide_from_depth)

    # ------------------------------------------------------------ anchors
    rm3 = root.matrix_world.to_3x3()
    ux = dirn(rm3, (1, 0, 0))          # panel +X, along the tube rail
    uy = dirn(rm3, (0, 1, 0))          # panel +Y, up the panel
    uz = dirn(rm3, (0, 0, 1))          # panel +Z, out at the pilot
    # NO module declares `axis` on a `rotate` control (BRIEF section 4 step 1
    # finding 2).  MTA has no face helper -- the survey reports "the working
    # face IS the slot plane" -- so the scrambler's axis is the root's own +Z,
    # and there is no rake to sweep a cone about.
    wheel_hub = root.matrix_world @ ctrl["scrambler"]["anchor_local"]
    hand_hinge = hand_piv.matrix_world.translation.copy()
    cap_hub = root.matrix_world @ Vector((mod.CAPSULE_X[REST], mod.TUBE_Y,
                                          mod.PZ + 0.028))
    cap_bell = root.matrix_world @ Vector((mod.BELL_X, mod.TUBE_Y,
                                           mod.PZ + 0.078))

    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-dirn(
        cc.matrix_world.to_3x3(), (0, 0, -1))).dot(uz)))))
    print("OBLIQ panel face normal vs close-cam view axis %.3f deg" % obliq)

    # --------------------------------------------------- the readout planes
    ADV_ID, CAP_ID = font_metrics(mod, 0.0118, mats["brass"])
    ADV_ODO, CAP_ODO = font_metrics(mod, 0.0205, mats["brass"])
    ADV_SLIP, CAP_SLIP = font_metrics(mod, 0.0098, mats["brass"])
    ADV_SLIP3, _ = font_metrics(mod, 0.0086, mats["brass"])
    print("TYPE  advance/char measured in Blender (FONT.size is NOT an em):")
    for nm, s, a, c in (("env id  ", 0.0118, ADV_ID, CAP_ID),
                        ("odometer", 0.0205, ADV_ODO, CAP_ODO),
                        ("slip    ", 0.0098, ADV_SLIP, CAP_SLIP),
                        ("slip l3 ", 0.0086, ADV_SLIP3, 0)):
        print("   %s size %.4f -> adv %.6f m  (ratio %.5f)  cap %.5f"
              % (nm, s, a, a / s, c))

    # A plane must stand PROUD of its carrier: the shader's epsilon is relative
    # (s > 1.0001), which at 1.1 m is 0.11 mm, so coplanar detail lands in the
    # front half.  The env flap's top face is at PZ+0.0228, exactly the type's
    # own z, so the ID planes are pushed 0.4 mm out (BRIEF: "or add >= 0.3 mm").
    Z_ID = mod.PZ + 0.0232
    Z_ODO = mod.PZ + 0.0155
    Z_SLIP = mod.PZ + 0.0066
    ROW_Y, COL_X = mod.ROW_Y, mod.COL_X
    row_txt = [y - 0.0035 for y in ROW_Y]        # where build.py puts the type
    id_mid = (row_txt[0] + row_txt[1]) / 2
    LEAD_ID = row_txt[0] - row_txt[1]

    def plane(name, cxl, cyl, z, hw, hh, tp):
        o_local = Vector((cxl, cyl, z))
        origin = root.matrix_world @ o_local
        rec = {"name": name, "origin": T.to3(origin), "u": T.to3(ux),
               "v": T.to3(uy), "n": T.to3(uz), "half_w": hw, "half_h": hh,
               "type": tp, "local": [cxl, cyl, z],
               "corners_px": {
                   nm: dict(zip(("x", "y"), mod.project(
                       scene, cc, origin + ux * (hw * sx) + uy * (hh * sy))))
                   for nm, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                                      ("bl", -1, -1), ("br", 1, -1))}}
        return rec

    planes = []
    for c, cx in enumerate(COL_X):
        planes.append(plane(
            "queue_col%d" % c, cx, id_mid, Z_ID,
            3 * ADV_ID + 0.0021, 0.033,
            {"adv_m": ADV_ID, "lead_m": LEAD_ID,
             "left_m": -3 * ADV_ID, "top_m": row_txt[0] - id_mid,
             "base_adj": 0.0, "n_lines": 2, "n_cols": 6, "align": "center",
             "size_m": 0.0118, "cap_m": CAP_ID}))
    planes.append(plane(
        "odometer", mod.ODO_X, mod.HDR_Y, Z_ODO,
        1 * ADV_ODO + 0.0024, 0.0095,
        {"adv_m": ADV_ODO, "lead_m": 0.0205, "left_m": -1 * ADV_ODO,
         "top_m": 0.0, "base_adj": 0.0, "n_lines": 1, "n_cols": 2,
         "align": "center", "size_m": 0.0205, "cap_m": CAP_ODO}))
    SLIP_Y = [-0.172, -0.185, -0.198]
    planes.append(plane(
        "webhook_slip", 0.005, SLIP_Y[1], Z_SLIP,
        4.5 * ADV_SLIP + 0.0025, 0.018,
        {"adv_m": ADV_SLIP, "lead_m": 0.013, "left_m": -4.5 * ADV_SLIP,
         "top_m": SLIP_Y[0] - SLIP_Y[1], "base_adj": 0.0, "n_lines": 3,
         "n_cols": 9, "align": "center", "size_m": 0.0098, "cap_m": CAP_SLIP,
         "line_size_m": [0.0098, 0.0098, 0.0086],
         "line_adv_m": [ADV_SLIP, ADV_SLIP, ADV_SLIP3]}))
    for p_, k in zip(planes, ["ids"] * 5 + ["odo", "slip"]):
        p_["ink_key"] = k
    for p in planes:                      # the element must contain the glyphs
        t = p["type"]
        need = (t["n_lines"] - 1) * t["lead_m"] / 2 + t["cap_m"] / 2
        assert p["half_h"] >= need - 1e-9, (p["name"], p["half_h"], need)
        assert p["half_w"] >= t["n_cols"] * t["adv_m"] / 2 - 1e-9, p["name"]

    # ---- MEASURED: does anything cross a declared rect at the capture pose?
    # The audit says MTA is CLEAN (0/80 IDs, 0/12 odometer, 0/24 slip over 33
    # poses) but it sampled the GLYPH boxes, and these rects are bigger.  What
    # matters for check_occlusion.py check 4 is the split live/baked: baked
    # occluders are in depth.bin and therefore in its ground truth, LIVE ones
    # are not and would show up as front-canvas coverage outside the set.
    dg = bpy.context.evaluated_depsgraph_get()
    liveset = set(o.name for o in live)
    cam_o = cc.matrix_world.translation

    def probe(p, n=11):
        origin = Vector(root.matrix_world @ Vector(p["local"]))
        hits = collections.Counter()
        for i in range(n):
            for j in range(n):
                s = origin + ux * (p["half_w"] * (2 * i / (n - 1) - 1)) \
                           + uy * (p["half_h"] * (2 * j / (n - 1) - 1))
                v = s - cam_o
                d = v.length
                ok, loc, nrm, idx, ob, mw = scene.ray_cast(
                    dg, cam_o, v.normalized(), distance=d - 0.001)
                if ok and ob is not None:
                    hits[("LIVE " if ob.name in liveset else "baked ")
                         + ob.name] += 1
        return hits

    print("PROBE  11x11 ray-cast per declared rect, close cam, rest pose:")
    live_hits = 0
    for p in planes:
        h = probe(p)
        n_live = sum(v for k, v in h.items() if k.startswith("LIVE"))
        live_hits += n_live
        print("   %-12s %3d/121 covered   live %d   %s"
              % (p["name"], sum(h.values()), n_live,
                 dict(h.most_common(4)) if h else "clear"))
    print("   LIVE geometry in front of a declared rect: %d  <- must be 0"
          % live_hits)

    # ------------------------------------------------------ ground truth
    rest_n = dict(mod.QUEUE_STATES)[mod.QUEUE_REST]
    rest_env = [o for g in env_geom[:rest_n] for o in g]
    rest_ids = [o for g in Q["env_objs"][:rest_n] for o in g
                if o.name.endswith("_id")]
    live_rest = cap_rest + rest_env + wheel + hand
    # the type ALONE -> its opaque pixels are exactly the glyph coverage, which
    # is what check/verify_assets.py takes the footprint from.
    T.render_colour(scene, os.path.join(OUT, "gt_platen0.png"),
                    visible=rest_ids + [digits[mod.QUEUE_REST]] + slip_txt)
    # per-group type renders, so each readout's INK COLOUR is measured off
    # Blender's own render of that readout rather than copied from KVS.
    inks = {}
    for nm, objs in (("ids", rest_ids), ("odo", [digits[mod.QUEUE_REST]]),
                     ("slip", slip_txt)):
        fn = os.path.join(OUT, "gt_type_%s.png" % nm)
        T.render_colour(scene, fn, visible=objs)
        inks[nm], n = modal_ink(fn)
        for p_ in planes:
            if p_["ink_key"] == nm:
                p_["ink"] = inks[nm]
        print("INK   %-5s median ink rgb%s over %d covered px"
              % (nm, tuple(inks[nm]), n))
    # THE ONE THAT GETS SCORED by check/compare.py: exactly the objects the
    # browser renders live, in exactly the state __occ.pose() puts the page in
    # -- queue q5, capsule at rest stop 3, wheel at 0 deg, handset cradled.
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"),
                    visible=live_rest)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + live_rest)

    # ------------------------------------------------------------ geometry
    T.export_glb(cap_rest, os.path.join(OUT, "capsule.glb"))
    T.export_glb([o for g in env_geom for o in g],
                 os.path.join(OUT, "envelopes.glb"))
    T.export_glb(wheel, os.path.join(OUT, "wheel.glb"))
    T.export_glb(hand, os.path.join(OUT, "handset.glb"))

    # ---------------------------------------------------------- scene.json
    rows = T.verify_depth(scene, cc, dep, [
        ("panel centre", ctr),
        ("odometer plane", root.matrix_world @ Vector(planes[5]["local"])),
        ("slip plane", root.matrix_world @ Vector(planes[6]["local"])),
        ("queue col2 plane", root.matrix_world @ Vector(planes[2]["local"])),
        ("capsule hub", cap_hub)])
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-20s want %.5f  got %.5f  err %+.5f"
              % (nm, want, got, err))

    def rect(objs, pad=8):
        return mod.clamp_rect(mod.bbox_rect(scene, cc, objs, pad=pad), W, H)

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
        "obliquity_deg": obliq,
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "panel": {"u": T.to3(ux), "v": T.to3(uy), "n": T.to3(uz),
                  "origin": T.to3(root.matrix_world @ Vector((0, 0, 0)))},
        "props": {
            "capsule": {
                "glb": "capsule.glb", "kind": "rail",
                "label": ctrl["capsule"]["label"],
                "hub": T.to3(cap_hub), "axis": T.to3(ux),
                "swing_axis": T.to3(uy), "out_axis": T.to3(uz),
                # offsets along `axis` from the exported rest pose, in metres
                "stops_m": [x - mod.CAPSULE_X[REST] for x in mod.CAPSULE_X],
                "rest": REST,
                "bell": {"pos": T.to3(cap_bell), "swing_deg": -90.0,
                         "along_m": mod.BELL_X - mod.CAPSULE_X[REST],
                         "out_m": 0.050},
                "hotspot": rect(ctrl["capsule"]["hotspot_objs"], pad=4)},
            "queue": {
                "glb": "envelopes.glb", "kind": "states",
                "label": Q["label"],
                "groups": [[o.name for o in g] for g in env_geom],
                "ids": list(Q["ids"]), "to": list(Q["to"]),
                "states": [[nm, n] for nm, n in Q["states"]],
                "rest": mod.QUEUE_REST,
                "hotspot": rect(Q["hotspot_objs"], pad=4)},
            "scrambler": {
                "glb": "wheel.glb", "kind": "rotate",
                "label": ctrl["scrambler"]["label"],
                "hub": T.to3(wheel_hub), "axis": T.to3(uz),
                "pivot_px": dict(zip(("x", "y"),
                                     mod.project(scene, cc, wheel_hub))),
                "detent": 30, "letters": mod.CIPHER,
                "hotspot": rect(wheel, pad=8)},
            "handset": {
                "glb": "handset.glb", "kind": "hinge",
                "label": ctrl["handset"]["label"],
                "hinge": T.to3(hand_hinge), "axis": T.to3(ux),
                # Blender rotates local +X by these; the Z-up -> Y-up map is a
                # proper rotation, so the angle carries over unchanged about
                # the mapped axis.
                "angles": dict(ctrl["handset"]["angles"]),
                "hotspot": rect(hand, pad=8)},
        },
        "text_planes": planes,
        "ink": inks,
        # the rest content, so nothing about it is baked anywhere
        "readout_text": ([[Q["ids"][c], Q["ids"][c + 5] if rest_n > c + 5
                           else ""] for c in range(5)]
                         + [["%02d" % rest_n]]
                         + [["X-NOTIFY", "WEBHOOK", "ops@fleet"]]),
        "session": list(mod.SESSION),
        "depth_verify": [{"name": n_, "analytic": w, "baked": g, "err": e}
                         for n_, w, g, e in rows],
        "probe_live_hits": live_hits,
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
#         --python live3d/pipeline/export_mta.py -- refit
#
# main() above rebuilds the shell and RE-RENDERS plate.png, depth.bin and every
# gt_*.png.  Running it would invalidate every number in live3d/RESULTS.md and
# modules/MTA/NOTES.md.  This entry point does none of that: it builds the port
# alone in an empty scene, writes assets/MTA/refit.glb, and merges a "refit"
# block into the existing scene.json.  Nothing else in assets/MTA is opened for
# writing.  FIX_UPLOAD.md section 0, decision 3.
#
# THE ANCHOR IS THE DESIGN'S OWN, RE-SOLVED AND UNMOVED.
# FIX_UPLOAD 3.3 tables (123, 584) for MTA -- itself a FALLBACK, because 3.4
# measured MTA's below-band at 40 px of a 720 px frame and its faceplate as the
# fullest in the fleet.  KVS's tabled anchor had to move 15 px (a moulding
# fillet ran through it); MTA's does not, and that is measured rather than
# assumed.  `refit_port.py MTA 123 584 56 --sub-base --sweep-y 520,650` walks
# the whole left bulkhead and the carrier is DEAD FLAT over all of it:
# plane-fit |residual| p50 0.00000 m, max 0.00000 m at the anchor itself, and
# the required seat never leaves the 1.15-1.28 mm band (2.8-3.1 x ubias_m) over
# 130 px of travel.  There is no fillet, no depth step and no reason to nudge.
# (Run the sweep with NO --window: an explicit window is held fixed at every
# y and would report one row's fit 66 times.)
#
#   obliquity  the carrier fits at 20.44 deg, against MTA's declared face
#              normal at 18.80 deg -- but the two NORMALS are 8.73 deg apart,
#              so this is a genuinely different plane that happens to be at a
#              similar rake to the camera.  Built on the carrier's, per
#              FIX_UPLOAD 12.2.
#   W          0.0376 m across flats, NOT the 35.3 mm the section 2 table
#              predicts: the table takes px/m at the readout plane (1.111 m
#              here) and this carrier is at 1.199-1.221 m.  FIX_UPLOAD 12.5.
#   sub_base   ON.  Section 1.4 / 12.14 item 3: MTA's carrier is featureless
#              bulkhead with no structure within 1 W, so the port "looks stuck
#              on" without the riveted plate.  The 1.3 W footprint has nothing
#              to climb here -- the flatness above is the check that says so.
MTA_REFIT = dict(px=123, py=584, port_px=56,
                 # 96 px wide by 64 px tall of pure bulkhead, centred on the
                 # anchor: wide enough that the fit is not reading one port's
                 # worth of noise, narrow enough to stay clear of the panel's
                 # left frame rail, whose edge runs x 264..267 over this band.
                 carrier_window=(75, 171, 552, 616),
                 label="REFIT",
                 # The size mark is cut for the same reason KVS cut it, and
                 # harder: MTA's type renders at ~6 px cap height, the fleet's
                 # tightest (NOTES section 3).  532 triangles for a smudge.
                 mark=None,
                 sub_base=True, service_rail=True)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(MTA_REFIT)
    A = RP.solve_anchor(CODE, K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"])
    P = RP.build("mta_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export(CODE, A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))


# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_mta.py -- mast
#
# Like `refit`, and for the same reason: main() re-renders plate.png, depth.bin
# and all six gt_*.png and would invalidate every number in live3d/RESULTS.md
# and modules/MTA/NOTES.md.  This entry point builds the mast alone in an empty
# scene, writes assets/MTA/mast.glb, and merges a "mast" block into the
# existing scene.json.  Nothing else in assets/MTA/ is opened for writing.
#
# WHY IT IS *NOT* ON THE REFIT PORT'S SERVICE RAIL -- the one place MTA departs
# from the KVS pattern, and it is a measurement, not a preference.
# STATUS_AT_A_GLANCE 11.2 mounts this fitting on the port's rail and tells the
# implementer to "solve the rail first and then confirm my 260 x 92 footprint
# lands on it".  Solved first, MTA's rail cannot carry it.  The port's carrier
# is the LEFT BULKHEAD, a strip 265 px wide (the panel's left frame rail runs
# x 264..267 down this band), and the rail direction u is screen-RIGHT: the
# published `free_from_m` = 1.5 W already lands at x = 203, and the panel edge
# is 62 px further on.  `status_mast.py MTA --m 8 --rake 0 --sweep-px 60,200`
# and the full solve at each size:
#
#     mast_px   envelope px        lift        rail ramp    worst gap
#        60     202.8.. 272.2      24.2 mm     -> 28.9 mm    2.8 px
#        90     201.7.. 305.8      25.7 mm     -> 37.3 mm    0.0 px  TOUCHES
#       130     196.4.. 350.2      55.3 mm     -> 48.2 mm    0.0 px
#       190     195.2.. 419.2      49.1 mm     -> 65.2 mm    0.0 px
#
# against KVS's 9.04 mm (16.0 x ubias_m) and a 0 -> 11.0 mm ramp.  MTA's
# ubias_m is 0.000414, so 24.2 mm is 58.5 x it: `_solve_lift()` is not being
# careful, it is telling us the fitting overhangs a surface 24 mm nearer the
# camera than the one it is bolted to.  A rail whose far end stands 29-65 mm
# off its own carrier is a shelf cantilevered in front of the instrument, and
# from 90 px up the envelope also touches the HANDSET hotspot.
#
# So MTA takes `status_mast.py`'s SECOND documented route (KVS NOTES 15.6):
# `--at PX,PY`, the carrier measured at that pixel with the port's own
# `fit_carrier_plane()`, and no rail.  What that builds is
# STATUS_AT_A_GLANCE 6.1's ORIGINAL device -- "a small brass status sub-plate
# bolted to the panel" -- which 6.2 rule 4 explicitly permits ("a blank
# nameplate, a sub-plate, the bezel rim outside the needle tip, or elsewhere on
# the panel") and which 11.2's rail was an UPGRADE to, not a replacement for.
# The seam that matters is the DATA seam (11.3), and that is untouched: the
# port still emits `refit:MTA` and the mast still supplies `dirty`.
#
# WHERE IT WENT INSTEAD, AND WHY THERE.
# The RIGHT bulkhead, mirroring the port across the instrument.  Both fittings
# are then bolted to the same ship wall at the same rake (carrier obliquity
# 20.44 deg on the left, 20.84 on the right) and at the same height (the port's
# projected bbox is y 556.4..618.9, the mast's envelope y 558.4..613.3), which
# is the honest version of 11.2's fiction once the rail is gone: not one rail
# with a fitting at each end, but a matched pair of aftermarket fittings on the
# flanks of a panel that has no room for either.  MTA's port is ALREADY a
# fallback placement for exactly this reason (FIX_UPLOAD 3.4: "below is
# off-frame ... nothing on MTA's faceplate takes a 40-70 mm prop"), so the
# telltale taking the other flank is the mirror of a decision the design has
# already made on this module.
#
# The alternative -- the panel band between the pigeonhole rack and the SEND
# plate, (400, 520), which is where a screen-space search lands (
# STATUS_AT_A_GLANCE 6.3's own best-in-band for MTA is (64, 260) / (996, 616))
# -- solves cleanly at 1.24 mm of lift AND IS THEN COVERED BY THE PORT'S OWN
# DOCKET.  Measured on the page, not predicted: `refit.js`'s least-overlap
# solver puts MTA's docket deterministically at (161.4, 390) at 520 x 317.9, so
# it owns x 161..681 / y 390..708, and a mast at (400, 520) sits entirely
# inside it.  That is STATUS_AT_A_GLANCE 6.5 item 4 -- reading the mast WHILE
# the port is open is the whole reason the close-up half exists -- arriving on
# a second module by a different route.  On the right bulkhead the two are
# 373 px apart.
#
# THE FOUR DECISIONS (KVS NOTES 15.6), all four measured:
#   --rakes    RAKE 0, not KVS's 45.  MTA's carrier is a near-frontal bulkhead,
#              not a 57 deg deck, and raking it only turns it away:
#                  rake     0    15    30    45    57    60    75    90
#                  obliq  20.8  34.8  49.3  64.0  75.8  78.7  93.5 108.3
#              At rake 0 the face sits at the carrier's own 20.84 deg -- 2.0
#              deg off MTA's declared face normal, 18.796 -- and its two axes
#              project at A 1502 and B 1330 px/m, a ratio of 0.89: readable in
#              both directions with no rake at all.  KVS raked 45 because ITS
#              carrier's v and n projected within 7.6 deg of one screen
#              direction (1846 vs 1279 px/m); MTA's project 2.1x apart
#              (v 1330, n 648), so the second axis is already there.
#   --px 180   swept.  The right bulkhead is 240 px wide at this height (the
#              panel's right frame edge runs x 1041..1037 down the band) and
#              the envelope must live inside it or `_solve_lift()` starts
#              paying for the panel:
#                  mast_px   envelope px          lift          grad
#                    160     1055.1..1239.1       1.66 mm 4.0x  11.1 px
#                    170     1054.8..1250.4       1.66 mm 4.0x  11.8 px
#                    180     1054.5..1261.7       1.66 mm 4.0x  12.5 px
#                    190     1054.2..1273.0       1.86 mm 4.5x  13.2 px
#              190 leaves 7 px to the frame edge; 180 leaves 18.3 px on the
#              right and 15.5 px to the panel edge on the left, and gives 8
#              graduations of 12.5 px.  KVS ships 18.0 px, but KVS has SIX
#              graduations in 190 px and MTA has EIGHT.
#   --m 8      the count of mail-module/vuln_tests/NN_*.py, never max(NN)
#              (STATUS_AT_A_GLANCE 9.4 rule 4).  01..08, no gaps on this
#              module, but the rule is the rule.
#   numbers    OFF, and the case is stronger than KVS's.  KVS cut the engraved
#              per-lamp numbers at ~9 px of cap height; MTA's own content type
#              renders at ~6 px (NOTES section 3) and the lamp pitch here is
#              12.5 px against KVS's 18.0.  The catalogue list in the hover
#              panel carries the identity instead, in the same order.
MTA_MAST = dict(mast_px=180, rake_deg=0.0, m=8, kind="defensive",
                numbers=False, at=(1060, 587),
                # 210 x 58 px of bare bulkhead.  The DEFAULT window
                # (px +/- 40, py +/- 24) straddles the panel's right frame rail
                # at any anchor left of x = 1085 and the fit goes with it:
                # solved with the default at (1060, 575) the carrier comes out
                # at 32.56 deg instead of 20.84 and the lift at 66.9 mm instead
                # of 1.66.  FIX_UPLOAD 12.14 item 1 is right and it bites here
                # harder than it did on KVS.
                carrier_window=(1055, 1265, 558, 616))


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(MTA_MAST)
    A = SMT.solve_mast(CODE, mast_px=K["mast_px"], rake_deg=K["rake_deg"],
                       m=K["m"], kind=K["kind"], numbers=K["numbers"],
                       px=K["at"][0], py=K["at"][1],
                       carrier_window=K["carrier_window"])
    P = SMT.build("mta_mast", A["frame_blender"], A["carrier_blender"],
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
