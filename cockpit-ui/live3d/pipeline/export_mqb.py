"""
LIVE-3D EXPORT -- MQB close-up  (Drone Telemetry Bus / patch-bay switchboard).

Same shape as export_kvs.py: a thin layer on top of
three-exploration/pipeline/transliterate.py, which already solved the depth
pass, fov_y_deg, the Z-up -> Y-up map, materials.json and the light
description.  What this file adds is MQB's own baked/live split, its four live
controls and its SEVEN readout planes.

    plate.png      shell + MQB static parts, MINUS the content type.
                   R["static"] exists here and partitions cleanly against the
                   controls (survey_modules.py: static n control-owned = 0),
                   so the plate has correct pixels BEHIND every live object.

    scope.glb      the 10 phosphor trace meshes  -- live, cycled
    patch.glb      the patch cords + plugs, 4 states  -- live
    retained.glb   lamp dome, LINE pip, HELD tab  -- live (emissive swap)
    keepalive.glb  the PINGREQ needle + hub  -- live, rotates

    NOT EXPORTED AT ALL: mqb_topic_0..4, mqb_reg_txt, mqb_will_l0..4.
    Eleven FONT objects that are CONTENT (subscribed topic filters, the client
    /retained counters, the will payload) -> DOM.  They are excluded from the
    plate, from the depth pass and from every glb.  The STAMPED lettering --
    nameplate, BUS TRAFFIC, RETAINED, LINE, KEEP ALIVE, PINGREQ, SUBSCRIBERS,
    WILL, HELD -- stays baked, or (HELD) stays live geometry, because a player
    does not read it for a value.

    text_planes    seven rects on the 18-degree raked working face.

THE DIAL-FACE RULE (CONVERSION_BRIEF section 6) applies twice here and both
times the answer is "no plane": the keep-alive gauge face (bezel 40/121,
needle sweeping the middle) and the scope face (the phosphor trace itself sits
2.0 mm proud and covers up to 18/121).  MQB's values live on the topic strip,
the register plate and the will card, all of which the occlusion audit
measured CLEAN over 27 poses.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_mqb.py
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
from module_loader import load_module, check_snapshots           # noqa: E402

shell = T.shell
CODE = "MQB"
OUT = os.path.join(LIVE3D, "assets", CODE)

# ---- the capture pose.  poseForCapture() in modules/MQB/module.js must put
# the page in EXACTLY this state, or compare.py measures the mismatch instead
# of the renderer.
POSE_PATCH = "party"
POSE_RETAINED = "retained"
POSE_SCOPE = 0
POSE_KA_DEG = 60.0

# content text -> DOM.  Everything else that is lettering stays geometry.
TXT_NAMES = (["mqb_topic_%d" % i for i in range(5)]
             + ["mqb_reg_txt"]
             + ["mqb_will_l%d" % i for i in range(5)])


def dirn(m3, v):
    """Transform a DIRECTION by a matrix's 3x3 and normalise."""
    return (m3 @ Vector(v)).normalized()


def measure_type(mod, size):
    """Blender's own advance / cap height / baseline for a FONT object of this
    size, in MODULE-LOCAL metres.

    MEASURED, not derived, and measured off Blender rather than off a pixel
    render.  bbox("MM") - bbox("M") is exactly one advance for a monospaced
    face with no kerning, and it is exact rather than +/- an antialiased pixel.
    CONVERSION_BRIEF step 4 says to band-detect the glyphs in a type-only
    render instead; that is how KVS got adv_m = 0.0100 for TXT_SIZE 0.031,
    where Blender's own advance is 0.009631 -- 3.8% narrow, 12 px of drift
    over KVS's own 24-character line.  See modules/MQB/NOTES.md.
    """
    out = {}
    for body in ("M", "MM"):
        cu = bpy.data.curves.new("mqb_typeprobe", 'FONT')
        cu.body, cu.size = body, size
        cu.align_x, cu.align_y = 'LEFT', 'CENTER'
        cu.extrude = 0.00035
        f = mod.mono_font()
        if f:
            cu.font = f
        o = bpy.data.objects.new("mqb_typeprobe_" + body, cu)
        bpy.context.collection.objects.link(o)
        me = o.to_mesh()
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        out[body] = (max(xs) - min(xs), min(ys), max(ys))
        o.to_mesh_clear()
        bpy.data.objects.remove(o)
    adv = out["MM"][0] - out["M"][0]
    cap = out["M"][2] - out["M"][1]
    # align_y='CENTER' anchors on the FACE's vertical centre, not on the cap
    # centre: for "M" the ink centre lands slightly above the origin, so the
    # baseline sits BELOW it by (cap/2 - ink_centre).
    base = out["M"][1]              # baseline offset from the object origin
    return adv, cap, base


def main():
    bad = check_snapshots()
    assert not bad, bad
    os.makedirs(OUT, exist_ok=True)
    mod = load_module(CODE)

    P = dict(shell.PARAMS)
    P["exterior"] = 0
    print("raytrace =", P.get("raytrace"),
          " (0 would mean the snapshot is stale again)")
    assert P.get("raytrace") == 1, "shell_snapshot.py is stale: no raytrace"

    scene = shell.build(P)
    scene.render.film_transparent = True
    W, H = scene.render.resolution_x, scene.render.resolution_y
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    R = mod.add_props(P, mats)
    mine, ctrl, root = R["all"], R["controls"], R["root"]
    static = R["static"]
    shell_meshes = [o for o in T.renderables(scene) if o not in set(mine)]

    # ---------------------------------------------------- the close-up rig
    # MQB HAS a close_rig(); use it, so the close-up frames the module exactly
    # as the shipped baked close plate does and the match dissolve still lands.
    cam, close_lights = mod.close_rig(root)
    scene.camera = cam
    bpy.context.view_layer.update()
    close_tags = {L.name: "close" for L in close_lights}

    # ------------------------------------------------ the live / baked split
    scope = list(ctrl["scope"]["frame_objs"])          # 10 trace ribbons
    patch_state = {k: list(v) for k, v in ctrl["patch"]["state_objs"].items()}
    patch = [o for v in patch_state.values() for o in v]
    dome, pip = ctrl["retained"]["dome"], ctrl["retained"]["pip"]
    held = list(ctrl["retained"]["held"])
    retained = [dome, pip] + held
    needle = list(ctrl["keepalive"]["objs"])
    live = scope + patch + retained + needle

    txt = [bpy.data.objects[n] for n in TXT_NAMES]
    assert all(o in set(static) for o in txt), "content type is not in static"
    assert not (set(live) & set(static)), "a live object is also in the plate"
    assert not (set(live) & set(txt))

    plate = shell_meshes + [o for o in static if o not in set(txt)]
    print("split: %d plate objects (%d shell + %d module static - %d type), "
          "%d live (%d scope, %d patch, %d retained, %d needle)"
          % (len(plate), len(shell_meshes), len(static), len(txt), len(live),
             len(scope), len(patch), len(retained), len(needle)))

    # the plate and the depth pass are LIVE-FREE and TYPE-FREE
    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"),
                         hide=live + txt)

    # ------------------------------------------------------------ geometry
    T.export_glb(scope, os.path.join(OUT, "scope.glb"))
    T.export_glb(patch, os.path.join(OUT, "patch.glb"))
    T.export_glb(retained, os.path.join(OUT, "retained.glb"))
    T.export_glb(needle, os.path.join(OUT, "keepalive.glb"))

    # ---------------------------------------------------------- the anchors
    rm3 = root.matrix_world.to_3x3()
    SC = mod.SCALE                       # root.scale; LOCAL metres * SC = world
    u = dirn(rm3, (1, 0, 0))             # face right
    v = dirn(rm3, mod.UPV)               # face up
    n = dirn(rm3, mod.NRM)               # face normal, out at the camera
    cfwd = dirn(cam.matrix_world.to_3x3(), (0, 0, -1))
    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-cfwd).dot(n)))))
    print("OBLIQ face normal vs close-cam view axis %.4f deg" % obliq)
    assert (-cfwd).dot(n) > 0, "n must point AT the camera"

    ka_anchor = root.matrix_world @ ctrl["keepalive"]["anchor"]
    # NO module declares `axis` on a rotate control (CONVERSION_BRIEF step 1).
    # MQB rakes its working face 18 deg off the slot plane, so rotating about
    # the root's +Z would sweep a cone.  The axis is the FACE normal -- and it
    # is emitted NEGATED, pointing away from the camera, so that a POSITIVE
    # angle about it is clockwise on screen, which is the direction the gauge's
    # own ticks run (th = -118 deg at the left, +118 deg at the right).
    ka_axis = -n
    ka_px, ka_py = mod.project(scene, cam, ka_anchor)

    # ------------------------------------------------------ the text planes
    # local -> world: face_pt() is in module-local metres, root.scale = 0.70.
    def rect(name, px, py, h, hw, hh, size, n_lines, lead=0.0, top=0.0):
        adv, cap, base = measure_type(mod, size)
        o = root.matrix_world @ mod.face_pt(px, py, h)
        return {
            "name": name,
            "origin": T.to3(o), "u": T.to3(u), "v": T.to3(v), "n": T.to3(n),
            "half_w": hw * SC, "half_h": hh * SC,
            "type": {
                "adv_m": adv * SC,          # MEASURED, see measure_type()
                "lead_m": (lead or 2 * hh) * SC,
                "left_m": -hw * SC,         # first column = the rect's left
                                            # edge; the module centres the line
                                            # in the element (Blender's own
                                            # align_x is CENTER for all of it)
                "top_m": top * SC,          # first line's ORIGIN above centre
                "base_m": base * SC,        # baseline below that origin
                "cap_m": cap * SC,
                "base_adj": 0.0,            # computed in the frontend from the
                                            # face's real metrics; see NOTES.md
                "n_lines": n_lines,
                "size_m": size,             # INFORMATIONAL (not an em)
                "align": "center",
            },
            "corners_px": {
                nm: dict(zip(("x", "y"), mod.project(
                    scene, cam,
                    o + u * (hw * SC * sx) + v * (hh * SC * sy))))
                for nm, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                                   ("bl", -1, -1), ("br", 1, -1))},
        }

    planes = []
    # 1..5  the topic strip.  Five separate rects, one per jack column: the
    # labels are five independent values centred over five jacks, not one line.
    # Cell 0.056 wide, rects 0.054, so adjacent rects never touch.
    for i, px in enumerate(mod.JX):
        planes.append(rect("topic_%d" % i, px, mod.JY_LABEL, 0.0086,
                           0.027, 0.0092,
                           0.0148 if i == len(mod.JX) - 1 else 0.0090, 1))
    # 6  the register plate under the scope: client / retained counters
    planes.append(rect("register", mod.SC_X, -0.148, 0.0132,
                       0.070, 0.0088, 0.0098, 1))
    # 7  the will card, five lines.  Rect is centred on the TEXT BLOCK, not on
    # the card: it stops 5 mm short of the WILL band above and the clip below.
    planes.append(rect("will", mod.WC_X, mod.WC_Y - 0.010, 0.0110,
                       0.020, 0.0285, 0.0068, 5, lead=0.0115, top=0.023))

    for p in planes:
        t = p["type"]
        print("  PLANE %-9s half %.4f x %.4f m  adv %.6f  cap %.6f  "
              "base %+.6f  lines %d"
              % (p["name"], p["half_w"], p["half_h"], t["adv_m"], t["cap_m"],
                 t["base_m"], t["n_lines"]))

    # ------------------------------------------------------- ground truth
    # gt_platen0.png: the CONTENT TYPE ALONE.  verify_assets.py reads its
    # opaque pixels as the exact glyph footprint and then asks whether
    # plate.png is ink-dark there.
    T.render_colour(scene, os.path.join(OUT, "gt_platen0.png"), visible=txt)

    # the pose that gets SCORED -- must equal module.js poseForCapture()
    M = ctrl["retained"]["mats"]
    dome.data.materials[0] = M["lamp_on"]
    pip.data.materials[0] = M["pip_off"]
    pose_live = ([scope[POSE_SCOPE]] + patch_state[POSE_PATCH]
                 + [dome, pip] + held + needle)
    sv = {o.name: o.matrix_world.copy() for o in needle}
    rot = (Matrix.Translation(ka_anchor)
           @ Matrix.Rotation(math.radians(POSE_KA_DEG), 4, ka_axis)
           @ Matrix.Translation(-ka_anchor))
    for o in needle:
        o.matrix_world = rot @ sv[o.name]
    bpy.context.view_layer.update()
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"),
                    visible=pose_live)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + pose_live)
    # sign check for the needle: +60 deg about the declared axis must lean
    # RIGHT, the way the gauge's +118 tick does.
    T.render_colour(scene, os.path.join(OUT, "gt_ka_p060.png"), visible=needle)
    for o in needle:
        o.matrix_world = sv[o.name]
    bpy.context.view_layer.update()
    T.render_colour(scene, os.path.join(OUT, "gt_ka_p000.png"), visible=needle)

    # ---------------------------------------------------------- scene.json
    # Blender AREA lights scale with their object.  MQB parents its four close
    # lights to a root whose scale is 0.70, so the emitting square is really
    # 0.70 * L.data.size and the radiance is 1/0.49 of what size alone implies.
    # transliterate.lights_json() reports the unscaled size (correct for every
    # module whose lights are unparented); corrected here and A/B'd against
    # Blender in modules/MQB/NOTES.md.
    lights = T.lights_json(scene, close_tags)
    byname = {L.name: L for L in scene.objects if L.type == 'LIGHT'}
    order = [L.name for L in scene.objects if L.type == 'LIGHT']
    for rec, nm in zip(lights, order):
        s = byname[nm].matrix_world.to_scale()
        k = (abs(s.x) + abs(s.y) + abs(s.z)) / 3.0
        rec["size_blender"] = rec["size"]
        rec["obj_scale"] = k
        rec["size"] = rec["size"] * k

    probes = [("panel face", root.matrix_world @ mod.face_pt(0.0, -0.06, 0.0)),
              ("topic strip face",
               root.matrix_world @ mod.face_pt(0.100, 0.014, 0.0075)),
              ("register plate face",
               root.matrix_world @ mod.face_pt(mod.SC_X, -0.148, 0.0120)),
              ("will card face",
               root.matrix_world @ mod.face_pt(mod.WC_X, mod.WC_Y, 0.0105))]
    rows = T.verify_depth(scene, cam, dep, probes)
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-22s want %.5f  got %.5f  err %+.6f" % (nm, want, got, err))

    j = {
        "render": {"w": W, "h": H},
        "camera": T.cam_json(scene, cam),
        "lights": lights,
        "world_bg": list(scene.world.node_tree.nodes["Background"]
                         .inputs[0].default_value),
        "colour": {"view_transform": scene.view_settings.view_transform,
                   "look": scene.view_settings.look,
                   "exposure": scene.view_settings.exposure},
        "light_gain": 0.65,      # measurements.txt: tuned close_rt = 0.65
        "env_intensity": 0.0,    # measured optimum, monotonically
        "raytrace": 1,
        "scale": SC,
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "props": {
            "scope": {
                "glb": "scope.glb", "kind": "frames",
                "label": ctrl["scope"]["label"],
                "nodes": [o.name for o in scope],
                "hotspot": mod.clamp_rect(
                    mod.pts_rect(scene, cam, root,
                                 ctrl["scope"]["hotspot_pts"], pad=8), W, H)},
            "patch": {
                "glb": "patch.glb", "kind": "states",
                "label": ctrl["patch"]["label"],
                "order": list(ctrl["patch"]["order"]),
                "topics": list(ctrl["patch"]["topics"]),
                "states": {k: [o.name for o in v]
                           for k, v in patch_state.items()},
                "hotspot": mod.clamp_rect(mod.union(
                    [mod.bbox_rect(scene, cam, ctrl["patch"]["hotspot_objs"],
                                   pad=10)]
                    + [mod.bbox_rect(scene, cam, v, pad=8)
                       for v in patch_state.values() if v]), W, H)},
            "retained": {
                "glb": "retained.glb", "kind": "states",
                "label": ctrl["retained"]["label"],
                "order": list(ctrl["retained"]["order"]),
                "dome": dome.name, "pip": pip.name,
                "held": [o.name for o in held],
                # the on/off material PAIRS the module declares -- the thing
                # that makes an emissive swap possible at all
                "mats": {k: m.name for k, m in M.items()},
                # state -> (dome mat key, pip mat key, HELD tab dropped)
                "poses": {"clear": ["lamp_off", "pip_off", False],
                          "live": ["lamp_on", "pip_on", False],
                          "retained": ["lamp_on", "pip_off", True]},
                "hotspot": mod.clamp_rect(
                    mod.bbox_rect(scene, cam, retained, pad=10), W, H)},
            "keepalive": {
                "glb": "keepalive.glb", "kind": "rotate",
                "label": ctrl["keepalive"]["label"],
                "nodes": [o.name for o in needle],
                "hub": T.to3(ka_anchor), "axis": T.to3(ka_axis),
                "range": list(ctrl["keepalive"]["range"]),
                "pivot_px": {"x": ka_px, "y": ka_py},
                "hotspot": mod.clamp_rect(
                    mod.bbox_rect(scene, cam, ctrl["keepalive"]["hotspot_objs"],
                                  pad=8), W, H)},
        },
        "text_planes": planes,
        "capture_pose": {"patch": POSE_PATCH, "retained": POSE_RETAINED,
                         "scope": POSE_SCOPE, "keepalive_deg": POSE_KA_DEG},
        "rake_deg": {"working_face_off_vertical": math.degrees(mod.RAKE),
                     "obliquity_to_close_cam": obliq},
        "depth_verify": [{"name": n_, "analytic": w, "baked": g, "err": e}
                         for n_, w, g, e in rows],
        # the default readout copy, so nothing about it is baked
        "readout_text": [["drone/+"], ["hull/temp"], ["nav/fix"],
                         ["will/lost"], ["#"], ["CLIENTS 07  RETAIN 3"],
                         ["IF THIS", "LINE", "DROPS", "PLAY", "THIS"]],
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
#         --python live3d/pipeline/export_mqb.py -- refit
#
# main() above rebuilds the shell and RE-RENDERS plate.png, depth.bin and all
# five gt_*.png.  Running it would invalidate every number in
# live3d/RESULTS.md and modules/MQB/NOTES.md.  This entry point does none of
# that: it builds the port ALONE IN AN EMPTY SCENE, writes assets/MQB/refit.glb
# and merges a "refit" block into the existing scene.json.  Nothing else in
# assets/MQB/ is opened for writing.  FIX_UPLOAD.md section 0, decision 3.
#
# ROOT SCALE IS 1.0 ON THIS PATH, AND THAT IS NOT A CONTRADICTION.
# main() authors MQB inside `mod.SCALE = 0.70` and every local dimension there
# is 1/0.70 of its world size (README section 16.8, and the light-size note in
# section 5 of this file).  FIX_UPLOAD 12.14 item 4 lists MQB at 0.70 for that
# reason.  But this entry point clears the scene and builds the port in WORLD
# coordinates from `solve_anchor()`'s world-space frame -- there is no MQB root
# in the file at all -- so `root_scale` must stay 1.0.  Passing 0.70 here would
# divide every dimension by 0.70 and ship a port 1.43x too big.  The rule is
# "pass the scale of the root you are authoring INSIDE"; on the empty-scene
# path you are inside nothing.
#
# WHERE IT SITS, AND WHY IT IS NOT 62 px AT (275, 666).
# FIX_UPLOAD's placement table says (275, 666) at 62 px, "panel lower apron,
# below the register plate".  The apron is the right carrier and the reasons in
# the table hold; the size and the y do not, and both are measured:
#
#   * The apron is 52 px tall -- depth.bin has it solid and DEAD FLAT
#     (plane-fit |residual| max 0.000000 m) from y 655 to y 707, x 200..1079,
#     at a constant 0.7266 m.  Above y 655 the frame's inner return steps BACK
#     24-31 mm (the chamfer y 644..654, then the shadow groove y 637..643, then
#     the recessed strip at 0.7525 and the faceplate itself at 0.7441).  Below
#     y 707 there is no module: that is the baked silhouette's bottom edge.
#   * A port's ENVELOPE is ~1.05 x port_px tall (FIX_UPLOAD 12.4: the drawn
#     silhouette is not the base hexagon).  62 px needs 65.1 px and 56 px needs
#     58.8 px, so neither fits the 52 px apron; both would have to bridge onto
#     the frame's return, which at MQB's 0.00-degree obliquity is invisible --
#     the port occludes what is behind it exactly -- but is still a fitting
#     bolted across a 30 mm step.  48 px needs 50.4 px and is the largest that
#     lies WHOLLY on the flat apron.
#   * At (275, 666) the solver refuses outright: with the carrier window over
#     the tabled anchor it fits a plane through the chamfer as well as the
#     apron and asks for a 13.4 mm seat against a 3.1 mm cap.  That is
#     FIX_UPLOAD 12.14 item 1 -- the window matters -- and 12.3's fillet on KVS
#     again, on a second module.
#
# Shipped at (275, 679) 48 px: envelope 243.0..305.5 x 655.6..706.0, which is
# the apron edge to edge with ~1 px to spare top and bottom, W = 19.53 mm,
# seat 1.225 mm = the 2.5 x ubias_m floor, 100 % solid carrier at 0.7266 m.
# Sweep it yourself, with no Blender in the loop:
#
#   python3 live3d/pipeline/refit_port.py MQB 275 679 48 --window 240,310,662,702
#   python3 live3d/pipeline/refit_port.py MQB 275 679 48 \
#       --window 240,310,662,702 --sweep-y 660,704
MQB_REFIT = dict(px=275, py=679, port_px=48,
                 # The apron under the port, NOT the port box: the default
                 # window would reach up over the chamfer and the fitted plane
                 # would be a compromise between two surfaces 30 mm apart.
                 carrier_window=(240, 310, 662, 702),
                 label="REFIT",
                 # The size mark is 532 triangles for a 3 px smear at this
                 # size; cut on KVS for the same reason (FIX_UPLOAD 12.9).
                 mark=None,
                 # The 1.3 W sub-base is for featureless bulkhead (LOG, MTA).
                 # MQB's port has the frame's own return and the faceplate
                 # 25 px above it, and a 1.3 W footprint is 62 px tall against
                 # a 52 px apron -- it would climb the chamfer.  Off.
                 sub_base=False, service_rail=True)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(MQB_REFIT)
    A = RP.solve_anchor(CODE, K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"])
    P = RP.build("mqb_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export(CODE, A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))



# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_mqb.py -- mast
#
# Like `refit`: main() re-renders plate.png, depth.bin and all five gt_*.png
# and would invalidate every number in live3d/RESULTS.md and
# modules/MQB/NOTES.md.  This entry point builds the mast ALONE IN AN EMPTY
# SCENE, in WORLD coordinates (so `root_scale` is 1.0 here for the same reason
# it is 1.0 for the port -- see the note above MQB_REFIT), writes
# assets/MQB/mast.glb and merges a "mast" block into the existing scene.json.
# STATUS_AT_A_GLANCE.md section 6; FIX_UPLOAD.md section 0 decision 3.
#
# RAKE 0, AND THAT IS A MEASUREMENT.  `status_mast.py MQB --rakes` prints:
#
#     the carrier itself is at 0.00 deg
#       rake  0 -> face obliquity  0.00      rake 45 -> 45.00
#       rake 15 -> 15.00                     rake 57 -> 57.00
#       rake 30 -> 30.00                     rake 90 -> 90.00
#
# MQB's apron faces the close camera dead on, so the rake IS the obliquity and
# KVS's 45 degrees would foreshorten the face by 30 %.  The reason KVS needs a
# rake at all -- STATUS_AT_A_GLANCE 6.5 item 3, its carrier's two in-plane
# axes projecting within 7.6 deg of the SAME screen direction -- does not
# apply here: MQB's A and B axes project at 2450.8 px/m EACH, at 90 degrees to
# each other.  This is the case rake 0 is for.
#
# 180 px, AND WHY NOT 190.  The apron is 52 px tall (y 655..707; see the note
# above MQB_REFIT) and a rake-0 mast's envelope is ~0.31 x its length tall,
# unforeshortened.  `--sweep-px 110,240` at this start:
#
#     mast_px  envelope y        grad px   worst clearance
#     120      654.9..691.6       9.7      20.9 px
#     150      648.8..694.6      12.1      14.8 px
#     180      642.6..697.7      14.5       8.6 px   <-- shipped
#     210      636.5..700.8      16.9       2.5 px
#
# The clearance that closes is to the `patch` control's hotspot, whose lower
# edge is y 630.  180 px keeps 8.6 px of it, gives 14.5 px per graduation
# (KVS ships 18.0 at 190 px on a 6-PoC module; this is a 7-PoC one) and puts
# the fitting's top 12 px above the apron over the frame's own inner return --
# which at 0.00 deg obliquity shows no float at all, because the fitting
# occludes exactly what is behind it.
#
# 12.2 W ALONG THE RAIL, AND WHY NOT 1.5 OR 3.2.
# `free_from_m` = 1.5 W is a floor, not an address (FIX_UPLOAD 12.13).  On MQB
# `refit.js`'s docket solver lands the docket deterministically at (312, 390)
# 520 x 318 -- to the RIGHT of the port, not the left as on KVS, because the
# left candidate clamps to x 12 and then covers the port's own envelope, which
# the solver weights 4x.  So the docket takes x 312..832 and covers the apron
# under everything from 1.5 W to about 11.6 W.  Reading the mast WHILE the
# port is open is the whole point of the close-up half, so the mast starts
# past the docket's right edge: 12.2 W = 0.2383 m puts the envelope at
# x 853.1..1059.7, a 20.9 px gutter to the docket and 19 px to the apron's
# right end.
#
# THE RAIL IS A STUB, NOT CONTINUOUS, AND THAT IS THE ONE PLACE THIS BUILD
# DEPARTS FROM KVS.  STATUS_AT_A_GLANCE 6.5 item 4 builds the rail continuous
# from the port's own end so the offset reads as one rail with a fitting at
# each end.  At 12.2 W that rail would be 550 px long and would run straight
# through MQB's baked `MQB  DRONE TELEMETRY BUS` nameplate, measured at
# x 555..724, y 679..686 -- the rail's own band is y 675.5..682.5.  It would
# hide the top half of the module's own engraved lettering, which README
# section 12 keeps as geometry precisely because a player reads it.  So the
# rail is built as a stub under the fitting alone, 0.12 L past each end, the
# same cross-section and the same idea as the port's own +/- 0.65 W stub.
# `build()` takes `rail_from=` for exactly this.
MQB_MAST = dict(mast_px=180, start_w=12.2, rake_deg=0.0, m=7,
                kind="defensive",
                # Engraved per-lamp numbers: ~2,600 triangles for lettering
                # ~8 px tall, against the whole fitting's ~1,000.  Same trade
                # FIX_UPLOAD 12.9 made for the port's size mark.  Off.
                numbers=False,
                # how far past the fitting's own ends the rail stub runs, in L
                rail_lead=0.12,
                # multiples of ubias_m every surface must clear the plate by;
                # solve_mast()'s own default, repeated here because the stub's
                # ramp is solved against it too
                lift_margin=2.5)


def _stub_ramp(A, rf, r1, lift_margin, samples=200):
    """The rail stub's underside height at each end, in metres above the rail
    origin plane, so its worst point clears the baked plate by exactly
    `lift_margin` x `ubias_m`.

    This is `solve_mast()`'s THE RAIL RAMP block evaluated over a different
    interval, using status_mast's own camera, its own depth reader and its own
    clearance expression.  It exists because `solve_mast()` always starts the
    line at the port's `claimed_half_m`, and on MQB the 550 px between the port
    and the mast contain the module's baked nameplate -- see the comment in
    mast().  Returns [z0, z1] for a STRAIGHT bar, never a curve.
    """
    import status_mast as SMT
    Adir, S = SMT.load_module(CODE)
    cam = SMT.Camera(S)
    dep, W, H = SMT.read_depth(Adir, S)
    ub = float(S.get("ubias_m") or 0.0005)
    sr = S["refit"]["service_rail"]
    fr = S["refit"]["frame"]
    u, v, n = SMT._norm(fr["u"]), SMT._norm(fr["v"]), SMT._norm(fr["n"])
    O = list(sr["origin"])
    th = sr["thick_m"] / 2.0
    drop = max(1e-3, SMT._dot(n, cam.zc))
    need0, slope = 0.0, 0.0
    for i in range(samples + 1):
        uu = rf + (r1 - rf) * i / float(samples)
        worst = -1e9
        for vv in (-th, 0.0, th):
            Pw = [O[k] + u[k] * uu + v[k] * vv for k in range(3)]
            px, py, D = cam.project(Pw)
            if not (0 <= px < W and 0 <= py < H):
                continue
            baked = dep[int(py) * W + int(px)]
            if baked >= 1e9:
                continue
            worst = max(worst, (D - baked + lift_margin * ub) / drop)
        if worst < -1e8:
            continue
        if i == 0:
            need0 = max(0.0, worst)
        elif uu > rf:
            slope = max(slope, (worst - need0) / (uu - rf))
    return [need0, need0 + slope * (r1 - rf)]


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(MQB_MAST)
    A = SMT.solve_mast(CODE, mast_px=K["mast_px"], start_w=K["start_w"],
                       rake_deg=K["rake_deg"], m=K["m"], kind=K["kind"],
                       numbers=K["numbers"])
    # THE STUB, AND WHY ITS RAMP IS FLAT.
    # `solve_mast()` solves the rail's underside as ONE straight line over
    # [claimed_half_m, far end] -- the whole 550 px run -- and publishes the
    # two endpoint heights.  On MQB that line is set by the module's own baked
    # nameplate standing proud at x 555..724, 500 px from the stub, and comes
    # out 0.0000 -> 0.0051 m.  Inheriting it would stand the stub's rail 5.1 mm
    # off the origin plane, i.e. 6.9 mm proud once its own 1.8 mm section is
    # added, against the bezel face's 7.7 mm -- a brass bar in front of the
    # tube.  That is FIX_UPLOAD 12.1's first KVS build ("the rail was visible
    # straight through the open port") arriving from the other direction.
    #
    # So the ramp is solved over the STUB'S OWN SPAN, with the tool's own
    # criterion (baked depth - the rail's own depth, against lift_margin x
    # ubias_m) and the tool's own camera and depth reader.  MQB's apron is
    # dead flat, so the answer is a flat rail; it is MEASURED here rather than
    # assumed, and printed, because trap 24 is exactly the thing that does not
    # announce itself.
    L = A["L_m"]
    rf = A["start_m"] - K["rail_lead"] * L
    r1 = A["start_m"] + L * (SMT.GEO["rod_a1"] + SMT.GEO["rail_pad"])
    ramp = _stub_ramp(A, rf, r1, K["lift_margin"])
    print("  rail stub               %.4f .. %.4f m along u   ramp %.5f -> "
          "%.5f m   (the whole-run line was %.5f -> %.5f -- the nameplate)"
          % (rf, r1, ramp[0], ramp[1], A["rail_ramp"][0], A["rail_ramp"][1]))
    P = SMT.build("mqb_mast", A["frame_blender"], A["carrier_blender"],
                  L, m=A["m"], kind=K["kind"], numbers=K["numbers"],
                  rail=A["rail"], ramp=ramp, rail_from=rf)
    SMT.export(CODE, A, P)
    # `status_mast.export()` publishes `mast.rail_ramp_m` from `solve_mast()`'s
    # whole-run line rather than from the ramp `build()` was actually given, so
    # on a module that passes `rail_from=` the two disagree.  The geometry is
    # right (`mast.parts.service_rail_ramp_m` and `evidence.rail_bbox_px` are
    # both computed from what was built); only this one field is stale.  It is
    # a shared file, so it is corrected HERE rather than there, and reported.
    sp = os.path.join(OUT, "scene.json")
    S = json.load(open(sp))
    S["mast"]["rail_ramp_m"] = list(ramp)
    S["mast"]["rail_span_m"] = list(P["parts"]["service_rail_span_m"])
    S["mast"]["rail_note"] = (
        "stub, not continuous from the port: a continuous rail would cross "
        "MQB's baked nameplate at x 555..724, y 679..686.  See "
        "pipeline/export_mqb.py MQB_MAST and modules/MQB/NOTES.md.")
    with open(sp, "w") as f:
        json.dump(S, f, indent=1)
    print("  scene.json <- mast.rail_ramp_m corrected to the ramp BUILT "
          "(%.5f -> %.5f)" % (ramp[0], ramp[1]))
    print("TELLTALE MAST OK -> %s  (%d tris)" % (OUT, P["tris"]))


if __name__ == "__main__":
    _argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "refit" in _argv:
        refit()
    elif "mast" in _argv:
        mast()
    else:
        main()
