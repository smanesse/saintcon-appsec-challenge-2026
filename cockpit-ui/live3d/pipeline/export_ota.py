"""
LIVE-3D EXPORT -- OTA close-up  (Fleet Replicator Grid / drone bay).

Same shape as export_kvs.py / export_mqb.py: a thin layer on top of
three-exploration/pipeline/transliterate.py, which already solved the depth
pass, fov_y_deg, the Z-up -> Y-up map, materials.json and the light
description.  What this file adds is OTA's own baked/live split, its four live
controls and its FIVE readout planes -- one of which MOVES.

    plate.png       shell + OTA static parts, MINUS the content type.
                    R["static"] exists and partitions cleanly against the
                    controls (survey_modules.py: static n control-owned = 0),
                    but it CONTAINS ota_chk_val, which is content -- so it is
                    subtracted as well (the MTA finding, BRIEF section 4 step 3).

    cartridge.glb   the tape-reel cartridge -- live, rides cpiv up the throat
    spine.glb       the 14 propagation chevrons -- live, material swap
    lamps.glb       the LOADED latch lamp + the 3 cradle beacons -- live,
                    emissive swap (both controls declare the material PAIRS)
    poll.glb        the POLL INTERVAL needle + hub -- live, rotates

    NOT EXPORTED AT ALL: ota_cart_ver, ota_chk_val, ota_ver_old_0..2,
    ota_ver_new_0..2.  Eight objects that are CONTENT (the version being
    published, the SHA-256 of the payload, and each fleet member's running
    version) -> DOM.  They are excluded from the plate, from the depth pass and
    from every glb.  The STAMPED lettering -- PUBLISH, SHA-256, POLL, SEC, the
    cradle codes FMM/IPM/LOG, FLEET REPLICATOR / GRID OTA-90 -- stays baked,
    because a player does not read it for a value.

    text_planes     five rects on the pillar face (no rake: the working face IS
                    the slot plane, so u/v/n = root local X/Y/Z).  `cart_ver`
                    RIDES the cartridge: the frontend re-places it every frame.

THE DIAL-FACE RULE (CONVERSION_BRIEF section 6) applies once here and the
answer is "no plane": the POLL INTERVAL gauge.  Its needle sweeps -125..+125
across the whole face and the audit measured it crossing a dial-face candidate
4/121.  **There is no DOM copy of the poll interval anywhere on this page** --
the needle is that readout.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_ota.py
"""
import bpy, math, os, sys, json
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
from nnscale import decode                                       # noqa: E402

shell = T.shell
CODE = "OTA"
OUT = os.path.join(LIVE3D, "assets", CODE)

# ---- THE CAPTURE POSE.  poseForCapture() in modules/OTA/module.js must put
# the page in EXACTLY this state, or compare.py measures the mismatch instead
# of the renderer.
POSE_CART_T = 0.0          # 0 = seated in the throat, 1 = fully raised
POSE_LATCH = True          # LOADED lamp lit (it is seated)
POSE_PROP = 6              # propagate frame, 0..8   (= the module's PROP_FAR)
POSE_FLEET = "roll2"       # fleet state: boards 0,1 rolled to 1.5.0
POSE_POLL_DEG = -35.0      # needle angle, the module's own POLL_FAR_DEG

# content text -> DOM.  Everything else that is lettering stays geometry.
TXT_NAMES = (["ota_cart_ver", "ota_chk_val"]
             + ["ota_ver_old_%d" % i for i in range(3)]
             + ["ota_ver_new_%d" % i for i in range(3)])


def dirn(m3, v):
    """Transform a DIRECTION by a matrix's 3x3 and normalise."""
    return (m3 @ Vector(v)).normalized()


def median_ink(path, amin=0.5):
    """The ink colour Blender actually rendered, as an (r,g,b) byte triple.

    MEDIAN over alpha > 0.5, with NO colour transform, read off the PNG BYTES.
    export_kvs.py's original recipe -- "the most-common fully-opaque pixel" --
    fails twice and silently on small type (BRIEF section 7 rule 7): nothing is
    fully opaque when the type is a few px tall, and bpy hands `image.pixels`
    back ALREADY display-encoded so an sRGB encode on top gives a wrong but
    entirely plausible colour.  This reads the file with the stdlib decoder, so
    neither can happen.
    """
    w, h, n, rows = decode(path)
    chans = [[], [], []]
    for y in range(h):
        r = rows[y]
        for x in range(w):
            a = r[x * n + 3] if n == 4 else 255
            if a <= amin * 255:
                continue
            for c in range(3):
                chans[c].append(r[x * n + c])
    if not chans[0]:
        return None, 0
    out = []
    for c in range(3):
        s = sorted(chans[c])
        out.append(s[len(s) // 2])
    return tuple(out), len(chans[0])


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

    # OTA's root carries no scale (slots.place sets location + rotation only),
    # so every local length below IS a world metre and the parented close
    # lights need no size correction (cf. MQB, whose root is scaled 0.70).
    rs = root.matrix_world.to_scale()
    assert max(abs(rs.x - 1), abs(rs.y - 1), abs(rs.z - 1)) < 1e-9, \
        "root is scaled: every local length below needs multiplying by it"

    # ---------------------------------------------------- the close-up rig
    # OTA HAS a close_rig(); use it, and set up EXACTLY the state main() sets
    # up before calling it, or the framing drifts and the transition's match
    # dissolve breaks.  main() raises the cartridge for the FIT (so the raised
    # cartridge is inside the frame) and rests the needle pointing UP.
    cart_all = list(ctrl["cartridge"]["cart"])       # includes ota_cart_ver
    cpiv = ctrl["cartridge"]["pivot"]
    npiv = ctrl["poll"]["pivot"]
    npiv.rotation_euler = (0, 0, 0)
    cpiv.location = (0, mod.CART_LIFT, 0)
    bpy.context.view_layer.update()
    cam, close_lights = mod.close_rig(scene, root, static + cart_all)
    cpiv.location = (0, 0, 0)
    scene.camera = cam
    bpy.context.view_layer.update()
    close_tags = {L.name: "close" for L in close_lights}

    # ------------------------------------------------ the live / baked split
    txt = [bpy.data.objects[n] for n in TXT_NAMES]
    txtset = set(txt)
    cart = [o for o in cart_all if o not in txtset]    # cartridge minus its ver
    latch = ctrl["cartridge"]["latch"]
    chevs = list(ctrl["propagate"]["objs"])
    beacons = list(ctrl["fleet"]["beacons"])
    needle = list(ctrl["poll"]["objs"])
    lamps = [latch] + beacons
    live = cart + lamps + chevs + needle

    assert not (set(live) & set(static)), "a live object is also in the plate"
    assert not (set(live) & txtset), "content type is in a glb"
    # "R['static'] exists" is NOT "R['static'] is safe": ota_chk_val is content
    # text and it lives in static.  Subtract the content type from BOTH sides.
    in_static = [o.name for o in txt if o in set(static)]
    print("content type found inside R['static']:", in_static)
    plate = shell_meshes + [o for o in static if o not in txtset]
    print("split: %d plate objects (%d shell + %d module static - %d type), "
          "%d live (%d cartridge, %d lamps, %d chevrons, %d needle), "
          "%d content type -> DOM"
          % (len(plate), len(shell_meshes), len(static), len(in_static),
             len(live), len(cart), len(lamps), len(chevs), len(needle),
             len(txt)))

    # the plate and the depth pass are LIVE-FREE and TYPE-FREE
    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"),
                         hide=live + txt)

    # ------------------------------------------------------------ geometry
    T.export_glb(cart, os.path.join(OUT, "cartridge.glb"))
    T.export_glb(chevs, os.path.join(OUT, "spine.glb"))
    T.export_glb(lamps, os.path.join(OUT, "lamps.glb"))
    T.export_glb(needle, os.path.join(OUT, "poll.glb"))

    # ---------------------------------------------------------- the anchors
    rm3 = root.matrix_world.to_3x3()
    u = dirn(rm3, (1, 0, 0))             # face right   (module local +X)
    v = dirn(rm3, (0, 1, 0))             # face up      (module local +Y)
    n = dirn(rm3, (0, 0, 1))             # face normal, out at the pilot
    cfwd = dirn(cam.matrix_world.to_3x3(), (0, 0, -1))
    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-cfwd).dot(n)))))
    print("OBLIQ panel face normal vs close-cam view axis %.4f deg" % obliq)
    assert (-cfwd).dot(n) > 0, "n must point AT the camera"

    poll_anchor = root.matrix_world @ ctrl["poll"]["anchor"]
    # NO module declares `axis` on a rotate control (CONVERSION_BRIEF step 1).
    # OTA has NO face helper -- the working face IS the slot plane -- so there
    # is no rake and the axis is the root's own local +Z.  It is emitted
    # NEGATED so that a POSITIVE angle about it is CLOCKWISE on screen, which
    # is the direction the gauge's own -118..+118 ticks run and the direction
    # build.py's own manifest angle means (it bakes rotation_euler.z = -angle).
    poll_axis = -n
    poll_px, poll_py = mod.project(scene, cam, poll_anchor)

    # ------------------------------------------------------ the text planes
    def rect(name, lx, ly, lz, hw, hh, size, n_lines, lead=None, top=0.0,
             align="center"):
        o = root.matrix_world @ Vector((lx, ly, lz))
        return {
            "name": name,
            "origin": T.to3(o), "u": T.to3(u), "v": T.to3(v), "n": T.to3(n),
            "half_w": hw, "half_h": hh,
            "type": TM.type_block(mod, size,
                                  lead_m=(2 * hh if lead is None else lead),
                                  left_m=-hw, top_m=top, n_lines=n_lines,
                                  scale=1.0, align=align),
            "corners_px": {
                nm: dict(zip(("x", "y"), mod.project(
                    scene, cam, o + u * (hw * sx) + v * (hh * sy))))
                for nm, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                                   ("bl", -1, -1), ("br", 1, -1))},
        }

    # -- where the type actually is, straight out of build.py's own constants
    CZ = (mod.FRONT + 0.008 + mod.HEAD_Z - 0.004) / 2.0
    CART_TXT = (mod.CART_X, mod.CART_SEAT_Y - 0.021,
                CZ + mod.CART_T / 2 + 0.006)
    CHK_TXT = (0.050, 0.143, mod.HEAD_Z + 0.010)
    BOARD_TXT_DY = -0.008
    BOARD_Z = mod.FRONT + 0.015

    planes = []
    # 1  the cartridge's own version label.  A MOVING plane: it rides cpiv up
    #    the throat, so the frontend re-places o/u/v/n every frame (BRIEF step
    #    4, "moving planes").  The rect is the ivory label the type sits on
    #    (0.058 x 0.014); the type stands 1.5 mm proud of it.
    planes.append(rect("cart_ver", CART_TXT[0], CART_TXT[1], CART_TXT[2],
                       0.029, 0.007, 0.0092, 1))
    # 2  the SHA-256 value on the glassy checksum face.  A tight band around
    #    the VALUE only: the stamped "SHA-256" caption 17 mm above it is
    #    geometry and stays out of the rect.
    planes.append(rect("checksum", CHK_TXT[0], CHK_TXT[1], CHK_TXT[2],
                       0.040, 0.0090, 0.0082, 1))
    # 3..5  the three flip-dot version boards.  The rect is the WHOLE glassy
    #    board face (0.100 x 0.048), which is 1 mm wider and 1 mm taller than
    #    the brass bezel's aperture on every side -- so the bezel really does
    #    crop this readout, and the split pass has baked geometry to redraw.
    for i, cy in enumerate(mod.CRADLE_Y):
        planes.append(rect("fleet_%d" % i, mod.BOARD_X, cy, BOARD_Z,
                           0.050, 0.024, 0.0200, 1, top=BOARD_TXT_DY))

    for p in planes:
        t = p["type"]
        print("  PLANE %-9s half %.4f x %.4f m  adv %.6f  cap %.6f  "
              "base %+.6f  ratio %.6f" % (p["name"], p["half_w"], p["half_h"],
                                          t["adv_m"], t["cap_m"], t["base_m"],
                                          t["adv_m"] / t["size_m"]))

    # ------------------------------------------------------- the pose state
    FD = mod.FLEET_DONE[POSE_FLEET]
    ver_old = list(ctrl["fleet"]["old"])
    ver_new = list(ctrl["fleet"]["new"])
    Mf = ctrl["fleet"]["mats"]
    Mc = ctrl["cartridge"]["mats"]
    Mp = ctrl["propagate"]["mats"]

    def set_pose():
        cpiv.location = (0, mod.CART_LIFT * POSE_CART_T, 0)
        latch.data.materials[0] = Mc["on"] if POSE_LATCH else Mc["off"]
        lit = mod.chev_lit(POSE_PROP)
        for i, c in enumerate(chevs):
            c.data.materials[0] = (Mp["hot"] if i == lit - 1 else
                                   (Mp["on"] if i < lit else Mp["off"]))
        for i in range(3):
            beacons[i].data.materials[0] = (Mf["green"] if i < FD
                                            else Mf["amber"])
        npiv.rotation_euler = (0, 0, math.radians(-POSE_POLL_DEG))
        bpy.context.view_layer.update()

    set_pose()
    pose_txt = [bpy.data.objects["ota_cart_ver"],
                bpy.data.objects["ota_chk_val"]] + \
               [(ver_new[i] if i < FD else ver_old[i]) for i in range(3)]

    # ------------------------------------------------------- ground truth
    # gt_platen0.png: the CONTENT TYPE ALONE, in the pose that gets scored, so
    # its opaque pixels are exactly the glyph footprint verify_assets.py and
    # check_text.py need.
    T.render_colour(scene, os.path.join(OUT, "gt_platen0.png"),
                    visible=pose_txt)
    # one render per INK, because OTA has four: engraved ink on the cartridge
    # label, emissive green for the checksum and for a synced board, emissive
    # amber for a stale board.
    T.render_colour(scene, os.path.join(OUT, "gt_type_cart.png"),
                    visible=[bpy.data.objects["ota_cart_ver"]])
    T.render_colour(scene, os.path.join(OUT, "gt_type_chk.png"),
                    visible=[bpy.data.objects["ota_chk_val"]])
    T.render_colour(scene, os.path.join(OUT, "gt_type_new.png"),
                    visible=[ver_new[0]])
    T.render_colour(scene, os.path.join(OUT, "gt_type_old.png"),
                    visible=[ver_old[2]])

    inks = {}
    for key, fn in (("cart", "gt_type_cart.png"), ("chk", "gt_type_chk.png"),
                    ("ver_new", "gt_type_new.png"),
                    ("ver_old", "gt_type_old.png")):
        c, cnt = median_ink(os.path.join(OUT, fn))
        inks[key] = list(c) if c else [122, 113, 107]
        print("  INK  %-8s median rgb%s over %d covered px   %s"
              % (key, tuple(inks[key]), cnt, fn))

    # the frame that gets SCORED by compare.py
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"), visible=live)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + live)

    # sign check for the needle: a POSITIVE manifest angle about the declared
    # axis must lean RIGHT, the way the gauge's +118 tick does.
    npiv.rotation_euler = (0, 0, math.radians(-60.0))
    bpy.context.view_layer.update()
    T.render_colour(scene, os.path.join(OUT, "gt_poll_p060.png"),
                    visible=needle)
    npiv.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    T.render_colour(scene, os.path.join(OUT, "gt_poll_p000.png"),
                    visible=needle)
    set_pose()

    # ------------------------------------------------------------ hotspots
    def bb(objs, pad=8):
        return mod.clamp_rect(mod.bbox_rect(scene, cam, objs, pad=pad), W, H)

    sv = cpiv.location.copy()
    cpiv.location = (0, mod.CART_LIFT, 0)
    bpy.context.view_layer.update()
    r_up = mod.bbox_rect(scene, cam, cart, pad=8)
    cpiv.location = sv
    bpy.context.view_layer.update()
    hs_cart = mod.clamp_rect(mod.union(
        [r_up, mod.bbox_rect(scene, cam, cart + [latch], pad=8)]), W, H)
    hs_prop = bb(chevs, pad=10)
    hs_fleet = mod.clamp_rect(mod.union(
        [mod.bbox_rect(scene, cam, ctrl["fleet"]["boards"] + beacons, pad=10)]),
        W, H)
    hs_poll = bb(ctrl["poll"]["hotspot_objs"], pad=8)

    # keep the four rects DISJOINT, exactly as build.py's own manifest does, so
    # the page never has to arbitrate by DOM order.
    def clip_left_of(a, b):
        if a["x"] + a["w"] > b["x"] and a["x"] < b["x"]:
            a["w"] = max(1, b["x"] - a["x"] - 1)
    clip_left_of(hs_fleet, hs_prop)
    clip_left_of(hs_cart, hs_poll)

    # ------------------------------------------------------------- depth QA
    probes = [
        ("rack plate face",
         root.matrix_world @ Vector((-0.020, -0.250, mod.FRONT))),
        ("checksum face",
         root.matrix_world @ Vector((0.080, 0.136, mod.HEAD_Z + 0.009))),
        ("dial face",
         root.matrix_world @ Vector((mod.DIAL_X + 0.015, mod.DIAL_Y + 0.010,
                                     mod.HEAD_Z + 0.010))),
        ("board 0 face",
         root.matrix_world @ Vector((mod.BOARD_X + 0.030,
                                     mod.CRADLE_Y[0] + 0.018,
                                     mod.FRONT + 0.014))),
        ("board 2 face",
         root.matrix_world @ Vector((mod.BOARD_X + 0.030,
                                     mod.CRADLE_Y[2] + 0.018,
                                     mod.FRONT + 0.014))),
    ]
    rows = T.verify_depth(scene, cam, dep, probes)
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-22s want %.5f  got %.5f  err %+.6f" % (nm, want, got, err))

    # ---------------------------------------------------------- scene.json
    lights = T.lights_json(scene, close_tags)

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
        "scale": 1.0,
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "face": {"u": T.to3(u), "v": T.to3(v), "n": T.to3(n)},
        "props": {
            "cartridge": {
                "glb": "cartridge.glb", "kind": "frames",
                "label": ctrl["cartridge"]["label"],
                "nodes": [o.name for o in cart],
                # the cartridge translates along the face's own +v by `lift`
                "axis": T.to3(v), "lift": mod.CART_LIFT,
                "frames": ctrl["cartridge"]["frames"],
                "latch": latch.name,
                "latch_mats": {"off": Mc["off"].name, "on": Mc["on"].name},
                "hotspot": hs_cart},
            "propagate": {
                "glb": "spine.glb", "kind": "frames",
                "label": ctrl["propagate"]["label"],
                "nodes": [o.name for o in chevs],
                "frames": ctrl["propagate"]["frames"],
                "chev_n": mod.CHEV_N,
                # HOW MANY CHEVRONS ARE LIT PER FRAME, emitted rather than
                # recomputed in JS.  chev_lit() is round(k*14/8) and k=6 gives
                # exactly 10.5: Python rounds half to EVEN and returns 10,
                # JavaScript's Math.round rounds half UP and returns 11.  The
                # capture pose is frame 6, so a re-derivation in the frontend
                # would put one extra chevron on the page that is not in
                # gt_full_read.png, and compare.py would measure that.
                "lit": [mod.chev_lit(k)
                        for k in range(ctrl["propagate"]["frames"])],
                "mats": {k: m.name for k, m in Mp.items()},
                # chevrons are single triangles wound so their normal points
                # INTO the panel: FrontSide deletes them.  See NOTES.md.
                "double_sided": True,
                "hotspot": hs_prop},
            "fleet": {
                "glb": "lamps.glb", "kind": "states",
                "label": ctrl["fleet"]["label"],
                "order": list(ctrl["fleet"]["order"]),
                "modules": list(ctrl["fleet"]["modules"]),
                "done": dict(mod.FLEET_DONE),
                "beacons": [o.name for o in beacons],
                "mats": {k: m.name for k, m in Mf.items()},
                "versions": {"old": mod.VER_OLD, "new": mod.VER_NEW},
                "hotspot": hs_fleet},
            "poll": {
                "glb": "poll.glb", "kind": "rotate",
                "label": ctrl["poll"]["label"],
                "nodes": [o.name for o in needle],
                "hub": T.to3(poll_anchor), "axis": T.to3(poll_axis),
                "range": list(ctrl["poll"]["range"]),
                "pivot_px": {"x": poll_px, "y": poll_py},
                "hotspot": hs_poll},
        },
        "text_planes": planes,
        "ink": inks,
        "capture_pose": {"cart_t": POSE_CART_T, "latch": POSE_LATCH,
                         "propagate": POSE_PROP, "fleet": POSE_FLEET,
                         "poll_deg": POSE_POLL_DEG},
        "rake_deg": {"working_face_off_slot_plane": 0.0,
                     "obliquity_to_close_cam": obliq},
        "depth_verify": [{"name": n_, "analytic": w_, "baked": g_, "err": e_}
                         for n_, w_, g_, e_ in rows],
        # the default readout copy, so nothing about it is baked
        "readout_text": [[mod.VER_NEW], ["9F2C41B8"]]
                        + [[mod.VER_NEW if i < FD else mod.VER_OLD]
                           for i in range(3)],
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
#         --python live3d/pipeline/export_ota.py -- refit
#
# main() above rebuilds the shell and RE-RENDERS plate.png, depth.bin and all
# eight gt_*.png.  Running it would invalidate every number in
# live3d/RESULTS.md and in modules/OTA/NOTES.md.  This entry point does none of
# that: it builds the port ALONE IN AN EMPTY SCENE, writes assets/OTA/refit.glb
# and merges a "refit" block into the existing scene.json.  Nothing else in
# assets/OTA/ is opened for writing.  FIX_UPLOAD.md section 0, decision 3.
#
# ROOT SCALE IS 1.0 ON THIS PATH.  OTA's own root scale is 1.0 anyway
# (scene.json -> scale), but the rule that matters is the one FIX_UPLOAD 12.15
# item 2 states: both fitting entry points CLEAR THE SCENE and build in WORLD
# coordinates from the solver's own world-space frame, so there is no root to
# be inside and `root_scale` must stay 1.0 on every module.  `build()` refuses
# a non-unit value in an empty scene; let it.
#
# WHERE IT SITS, AND WHY IT IS NOT (680, 32).
# FIX_UPLOAD 3.3 tables (680, 32) at 53 px, "the column above the rack, above
# the upper collar", and 3.4 explains why OTA has no below, no left and no
# right: the rack is a 189 px column against the starfield, its left band is
# 14 % solid and its right 17.9 %, and the FLEET REPLICATOR nameplate plus the
# pillar collar leave 34 px under the instrument against a 53 px port.  All of
# that holds.  The carrier is right, the size is right, the band is right.
# The x does not, and the reason is that THE CARRIER IS A CYLINDER:
#
#   * The pillar above the collar is solid over x 594..720, y 0..62 (the collar
#     itself runs y 64..88 and stands ~19 mm proud; the rack's top plate starts
#     at y 104).  Across that 127 px face `depth.bin` reads 1.8902 m at x 594,
#     falls to a minimum of 1.8218 m at x ~658, and rises again to 1.8712 m at
#     x 718.  That is a column seen from outside, not a panel: 68 mm of sag
#     each way over 60 px.
#   * `solve_anchor()` REFUSES (680, 32) at every in-plane rotation and at
#     every port size from 46 to 62 px: 22 px off the crown the least-squares
#     carrier plane cuts the bulge and the port needs a 7.5 mm seat against a
#     6.8 mm cap (0.12 W).  The refusal is the tool working -- FIX_UPLOAD
#     12.14 item 2 -- and it is the THIRD module running whose tabled anchor is
#     not buildable as tabled (KVS's fillet, MQB's 52 px apron, this).
#   * Moved to the crown, x 658, and it solves at every size from 50 to 58 px.
#     Shipped at the TABLED 53 px: W = 59.18 mm, spin 0, seat 6.456 mm
#     (4.34 x ubias_m -- the largest seat in the fleet, and the cylinder is the
#     whole reason), envelope 624.2..692.0 x 3.2..57.8, 100 % solid carrier at
#     1.8184..1.8354 m.
#   * y = 32 IS the tabled y and it is the only band that works.  `--sweep-y`
#     with the default window builds only y 30..36: below 30 the envelope runs
#     off the top of the 720 px frame, and from y 38 the carrier window reaches
#     the collar and the seat jumps to 20.5 mm.
#
# THE CARTRIDGE'S 140 mm LIFT CORRIDOR, which nothing in the solver models.
# `props.cartridge.lift` is 0.140 m along +Y.  Projecting cartridge.glb's 968
# vertices at t = 0 and t = 1 through this module's own camera gives
# x 539.3..605.6 y 151.4..216.4 at rest and x 538.5..605.3 y 25.4..93.0 fully
# raised, so the swept corridor is x 538.5..605.6, y 25.4..216.4.  The port's
# envelope starts at x = 624.2: 18.6 px clear of the corridor and 16.2 px clear
# of the cartridge's own drag hotspot (x 529..604).  FIX_UPLOAD 3.4's "right of
# x = 604" is exactly right and the crown happens to be on the correct side of
# it.
#
# Sweep any of it yourself, with no Blender in the loop:
#
#   python3 live3d/pipeline/refit_port.py OTA 658 32 53 --window 628,688,6,58
#   python3 live3d/pipeline/refit_port.py OTA 658 32 53 --sweep-y 20,50
#   python3 live3d/pipeline/refit_port.py OTA 680 32 53 --window 640,720,6,58
OTA_REFIT = dict(px=658, py=32, port_px=53,
                 # THE PORT'S OWN PROJECTED BBOX, held fixed.  On a cylinder
                 # the window does NOT move the fitted normal -- obliquity is
                 # 5.88..5.99 deg over every window from 36 to 127 px wide --
                 # it moves the SEAT, because a least-squares plane through a
                 # convex bulge is cut by the crown.  Windows wider than the
                 # port make the solver refuse (10.5 mm at 92 px, 16.2 mm at
                 # 116 px).  This one is the patch of carrier the port actually
                 # covers, which is the honest answer to "whose normal do you
                 # trust".
                 carrier_window=(628, 688, 6, 58),
                 label="REFIT",
                 # 532 triangles for a 3 px smear; cut on KVS, MQB and MTA for
                 # the same reason (FIX_UPLOAD 12.9).  OTA is named there as
                 # one of the two "roomier" modules at a predicted 65 mm, but
                 # the measured W is 59.18 mm and the lower facet is 4 px tall.
                 mark=None,
                 # The 1.3 W sub-base is for featureless bulkhead (LOG, MTA).
                 # The pillar has its own collar 4 px below the envelope and
                 # the frame edge 3 px above it; a 1.3 W footprint is 79 px
                 # tall against a 63 px band and would climb both.  Off.
                 sub_base=False, service_rail=True)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(OTA_REFIT)
    A = RP.solve_anchor(CODE, K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"])
    P = RP.build("ota_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export(CODE, A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))


# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_ota.py -- mast
#
# Like `refit`: main() re-renders plate.png, depth.bin and all eight gt_*.png
# and would invalidate every number in live3d/RESULTS.md and
# modules/OTA/NOTES.md.  This entry point builds the mast ALONE IN AN EMPTY
# SCENE, in WORLD coordinates (root_scale 1.0, for the same reason it is 1.0
# for the port), writes assets/OTA/mast.glb and merges a "mast" block into the
# existing scene.json.
#
# IT IS NOT ON THE REFIT PORT'S SERVICE RAIL, AND THAT IS MEASURED.
# STATUS_AT_A_GLANCE 11.2 mounts this fitting on the port's rail and tells the
# implementer to "solve the rail first and then confirm my 260 x 92 footprint
# lands on it".  Solved first, OTA's rail cannot carry it, and it fails harder
# than MTA's did.  The port's carrier is the CROWN OF A COLUMN 127 px wide
# (x 594..720); the rail direction u is screen-RIGHT; the published
# free_from_m = 1.5 W = 0.0888 m already lands the mast's A = 0 past the
# column's right edge:
#
#     python3 live3d/pipeline/status_mast.py OTA --m 8 --rake 0 --px 180
#       envelope           730.7..943.0 x -11.6..42.6 px
#       carrier solid behind    2.3 %          <-- the starfield
#       off frame               True
#
# 2.3 % solid, against MTA's panel edge at least being a panel.  So OTA takes
# status_mast.py's second documented route, `--at PX,PY`, with the carrier
# measured at that pixel by the port's own fit_carrier_plane(), and no rail --
# which builds STATUS_AT_A_GLANCE 6.1's ORIGINAL device, "a small brass status
# sub-plate bolted to the panel", the thing 11.2's rail was an upgrade to.
#
# WHERE IT WENT: THE DECK AT THE FOOT OF THE COLUMN, on the column's right,
# and everywhere else was eliminated by measurement, not by taste.
#
#   * The pillar's top band (x 594..720, y 0..62) is 127 x 63 px and the refit
#     port takes x 624.2..692.0 of it.  30 px remain to the left and 28 to the
#     right; a 180 px mast's envelope is 205 x 57.
#   * The pillar BELOW the rack is x 604..716, y 676..719 -- 112 x 43 px.  A
#     mast small enough to fit is 90 px, which is 6.4 px per graduation against
#     MTA's 12.5, and MTA is already recorded as the fleet's tightest.
#   * The rack's own faceplate is 206 px wide and every clear strip on it is
#     under 40 px tall between the cartridge, the poll dial, the chevron spine,
#     the three cradles and five readout rects.
#   * The big clean slab at x 1053..1279, y 0..143 is NOT OTA's structure -- it
#     is a neighbouring console 200 mm nearer the camera -- and it is under the
#     port's own docket, which this page measures at (698.3, 12) 520 x 317.9.
#   * The DECK is 100 % solid, flat (plane-fit |residual| p50 0.00042 m, p95
#     0.00142 m over the shipped window), and is the same class of carrier as
#     KVS's own front deck.  STATUS_AT_A_GLANCE 6.3's recommended fleet shelf
#     is the bottom sill at y = 616 and its tabled best for OTA is (424, 616);
#     that slot crosses the rack's silhouette and the module's baked
#     FLEET REPLICATOR nameplate, because 6.3's search masked control hotspots
#     and readout rects and never tested the CARRIER.  Moved onto real deck at
#     the column's foot the sill survives: the shipped envelope is
#     y 633.8..690.5.
#
# LEFT OF THE COLUMN OR RIGHT OF IT -- MEASURED BOTH, AND THE RIGHT WON.
# The left deck is flatter to the camera: the best face obliquity reachable
# there is 10.94 deg at (300, 678) and 8.41 deg at (200, 678), against 21.86
# at (760, 672).  It was built and looked at, and two things decided against
# it.  (1) The caption solves to (512.8, 626) 205 x 86 there, straight over
# this module's baked FLEET REPLICATOR / GRID OTA-90 nameplate -- MQB NOTES
# item 10 arriving again -- while from the right anchor it solves to
# (973.4, 626) on bare deck and clears the nameplate entirely.  (2) On the
# right the fitting sits at the FOOT of the same column whose crown carries the
# port, 8 px off the column's own silhouette, so the two fittings read as one
# installation; on the left it is 100 px of empty deck away in the corner.
# The cost is real and it is 11 deg of face obliquity.  What buys it back is
# that 21.68 deg is within 1.1 deg of OTA'S OWN declared working-face
# obliquity, 22.76 deg -- which is what FIX_UPLOAD 3.1's original rule asked
# for and what no other module in the fan-out has managed on a raked fitting --
# and that MTA shipped its mast at 20.84 deg and recorded all ten states
# separating at pixelRatio 1.
#
# RAKE 57, AND IT IS KVS'S CASE ARRIVING ON A FOURTH MODULE.
# `--rakes` at this anchor:
#
#     the carrier itself is at 60.80 deg
#       rake  0 -> 60.80    rake 45 -> 25.26    rake 57 -> 21.68  <-- shipped
#       rake 15 -> 47.47    rake 60 -> 21.70    rake 75 -> 27.06
#       rake 30 -> 35.11                        rake 90 -> 37.70
#
# There IS a minimum and it is at 57-60 deg.  The reason is STATUS_AT_A_GLANCE
# 6.5 item 3's exactly: the deck's own two in-plane directions project at
# 539.9 and 581.2 px/m -- near enough the same rate that a fitting LYING on it
# is one-dimensional on screen, which is the condition KVS raked for.  Raked
# 57 deg the face sits at 21.68 deg with its two axes at A 718.8 and B 752.2
# px/m, unforeshortened in both.  MQB and MTA both shipped rake 0 and KVS 45;
# do not inherit any of them.
#
# THE WINDOW IS LOAD-BEARING HERE, AND HARDER THAN ON MTA.  MTA's default
# window returned a WRONG answer (32.56 deg instead of 20.84).  OTA's default
# window (px +/- 40, py +/- 24 = x 720..800, y 648..696) straddles the column's
# right edge at x = 736, fits a plane through the deck AND the column 230 mm
# apart, and then `_solve_lift()` REFUSES OUTRIGHT:
#
#     python3 live3d/pipeline/status_mast.py OTA --at 760,672 --px 180 --m 8 --rake 57
#       ValueError: no lift under 0.75 L clears the baked carrier at this
#       anchor: the mast's envelope is over something much nearer the camera
#       than its mount.
#
# The anchor is fine; the window is not.  A window reaching the column from the
# other side -- (200, 600, 620, 715), which looks like a generous patch of
# deck -- is worse and silent: carrier 91.16 deg, face 108.83 deg (facing
# AWAY), lift 0.000 mm, residual max 0.102 m.  NOTE that `status_mast.py` has
# NO `--window` FLAG, so neither of these can be fixed from the command line;
# `carrier_window=` is a `solve_mast()` keyword only.  Reported, not changed.
OTA_MAST = dict(mast_px=180, rake_deg=57.0, m=8, kind="defensive",
                # M = 8 is the COUNT of ota-module/vuln_tests/NN_*.py, never
                # max(NN): the files are 01..07 and 09, so max(NN) would say 9.
                # STATUS_AT_A_GLANCE 9.4 rule 4.
                numbers=False,
                at=(760, 672),
                carrier_window=(752, 962, 644, 702))


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(OTA_MAST)
    A = SMT.solve_mast(CODE, mast_px=K["mast_px"], rake_deg=K["rake_deg"],
                       m=K["m"], kind=K["kind"], numbers=K["numbers"],
                       px=K["at"][0], py=K["at"][1],
                       carrier_window=K["carrier_window"])
    P = SMT.build("ota_mast", A["frame_blender"], A["carrier_blender"],
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
