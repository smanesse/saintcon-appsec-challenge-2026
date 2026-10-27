"""
LIVE-3D EXPORT — KVS close-up.

A thin layer ON TOP of three-exploration/pipeline/transliterate.py.  Everything
that pipeline already solved (linear-view-depth pass, the fov_y_deg fix, the
Blender Z-up -> three Y-up map, the materials.json side channel, the Blender
watt -> three nit light description) is imported, not re-implemented.  What
this file adds is the split the live-3d prototype needs and transliterate does
not make:

    plate.png   the baked close-up plate -- shell + KVS STATIC parts only.
                kvs_build_snapshot's R["static"] is already exactly
                "everything except the four interactive controls", so the
                plate has correct pixels BEHIND every live object (the felt
                backplate behind the reel, the lamp rings behind the domes,
                the key deck behind the key arm, the paper behind the type).

    reel.glb    the punched-tape reel      -- live, spins
    key.glb     the telegraph key arm      -- live, hinges
    lamps.glb   the eight idiot lights     -- live, emissive swap

    NOT EXPORTED AT ALL: the platen type.  Those 20 FONT objects are CONTENT
    text (a RESP session transcript, i.e. values a player reads).  Per the
    brief they become DOM.  They are excluded from the plate, from the depth
    pass and from every glb, so the claim "no content text is baked into any
    image" is enforced by the exporter, not by good intentions.  The STAMPED
    lettering -- nameplate, drawer labels, lamp captions, SEND, EVAL -- is in
    R["static"] and stays baked in geometry, as required.

    text_plane  the raked console face as an origin + orthonormal basis in
                three.js world coordinates, so the frontend can hang a real
                DOM element on it with a CSS matrix3d.  This is the number the
                brief calls the known hard case.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_kvs.py
"""
import bpy, math, os, sys, json
import numpy as np
from mathutils import Vector, Euler, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)
ROOT = os.path.dirname(LIVE3D)
EXPL = os.path.join(ROOT, "three-exploration")
sys.path.insert(0, os.path.join(EXPL, "pipeline"))
sys.path.insert(0, os.path.join(EXPL, "src"))
sys.path.insert(0, HERE)

import transliterate as T                                        # noqa: E402
shell = T.shell
slots = T.slots
import kvs_build_snapshot as mod                                 # noqa: E402
import typemetrics as TM                                          # noqa: E402

OUT = os.path.join(LIVE3D, "assets", "KVS")


def dirn(m3, v):
    """Transform a DIRECTION by a rotation matrix and normalise."""
    return (m3 @ Vector(v)).normalized()


def main():
    os.makedirs(OUT, exist_ok=True)

    P = dict(shell.PARAMS)
    P["exterior"] = 0
    print("raytrace =", P.get("raytrace"), " (0 would mean the snapshot is "
          "stale again)")
    assert P.get("raytrace") == 1, "shell_snapshot.py is stale: no raytrace"

    scene = shell.build(P)
    wide_cam = scene.camera
    scene.render.film_transparent = True
    W, H = scene.render.resolution_x, scene.render.resolution_y
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    R = mod.add_props(P, mats)
    mine, ctrl, root = R["all"], R["controls"], R["root"]
    shell_meshes = [o for o in T.renderables(scene) if o not in set(mine)]

    # ------------------------------------------------------- close-up rig
    # Byte-for-byte the same construction kvs_build_snapshot.main() and
    # transliterate.py use, so this close-up frames the module identically to
    # the shipped baked close plate.
    ctr = root.matrix_world @ mod.panel_pt(0.0, 0.070, 0.010)
    view = (wide_cam.matrix_world.translation - ctr).normalized()
    bpy.ops.object.camera_add(location=ctr + view * 0.90)
    cc = bpy.context.object
    cc.name = "KVS_closecam"
    cc.data.lens = 50.0
    ctr = mod.fit_camera(scene, cc, mine, ctr, view, frac=0.90)
    up = dirn(root.matrix_world.to_3x3(), (0, 0, 1))
    right = view.cross(up).normalized()
    close_tags = {}
    for off, energy, size, col in (
            (right * 0.52 + up * 0.46 + view * 0.34, 3.0, 0.55,
             (1.0, 0.88, 0.70)),
            (-right * 0.60 + up * 0.24 + view * 0.42, 1.6, 0.70,
             (0.66, 0.79, 1.00)),
            (up * 0.34 + view * 0.44 - right * 0.06, 0.9, 0.50,
             (1.0, 0.93, 0.80))):
        p = ctr + off
        bpy.ops.object.light_add(type='AREA', location=p)
        L = bpy.context.object
        L.data.energy, L.data.size = energy, size
        L.data.color = col
        L.rotation_euler = (ctr - p).to_track_quat('-Z', 'Y').to_euler()
        close_tags[L.name] = "close"
    scene.camera = cc
    bpy.context.view_layer.update()

    # ------------------------------------------------- the live / baked split
    reel = list(ctrl["tape"]["objs"])
    key = list(ctrl["key"]["objs"])
    key_piv = ctrl["key"]["pivot"]
    domes = list(ctrl["lamps"]["domes"])
    platen = list(ctrl["platen"]["objs"])
    live = reel + key + domes + platen
    static = R["static"]
    plate = shell_meshes + static
    assert not (set(live) & set(static)), "a live object is also in the plate"
    print("split: %d plate objects, %d live (%d reel, %d key, %d lamp, "
          "%d platen-type)" % (len(plate), len(live), len(reel), len(key),
                               len(domes), len(platen)))

    # key at rest for the plate/depth renders
    key_piv.rotation_euler = (math.radians(ctrl["key"]["angles"]["up"]), 0, 0)
    bpy.context.view_layer.update()

    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"), hide=live)

    # ------------------------------------------------------------ geometry
    T.export_glb(reel, os.path.join(OUT, "reel.glb"))
    T.export_glb(key, os.path.join(OUT, "key.glb"))
    T.export_glb(domes, os.path.join(OUT, "lamps.glb"))

    # ---------------------------------------------------------- the anchors
    rm3 = root.matrix_world.to_3x3()
    hub = root.matrix_world @ ctrl["tape"]["anchor_local"]
    n_local = Euler(mod.PANEL_ROT, 'XYZ').to_matrix() @ Vector((0, 0, 1))
    reel_axis = dirn(rm3, n_local)
    key_hinge = key_piv.matrix_world.translation.copy()
    key_axis = dirn(rm3, (1, 0, 0))          # key_piv rotates about local X

    # ---------------------------------------------- the raked text plane
    # The console face is a plane in the module's LOCAL frame:
    #   point(px, py) = panel_pt(px, py, h)
    #   u = local +X, v = local (0, cos RAKE, sin RAKE), n = u x v
    # The paper aperture is px in +/-0.158, py in [win_lo, win_hi].
    CS, SN = mod.CS, mod.SN
    WIN_LO, WIN_HI = 0.014, 0.112            # matches kvs_build_snapshot
    win_mid = (WIN_LO + WIN_HI) / 2
    TXT_H = 0.0026                           # the type's stand-off, as built
    o_local = mod.panel_pt(0.0, win_mid, TXT_H)
    origin = root.matrix_world @ o_local
    u = dirn(rm3, (1, 0, 0))
    v = dirn(rm3, (0, CS, SN))
    n = dirn(rm3, (0, -SN, CS))

    # Two rake numbers, because they are different things and the brief only
    # quotes one.  (a) the DASH surface the module is bolted to, (b) the
    # module's own console face, which rakes a further 45 deg off that.
    dash_rake = math.degrees(math.atan2(
        P["dash_top_z"] - P["dash_near_z"],
        (P["radius"] - 0.05) - (P["radius"] - P["dash_run"])))
    slot_n = dirn(rm3, (0, 0, 1))
    slot_rake = math.degrees(math.asin(max(-1.0, min(1.0, slot_n.z))))
    panel_rake = math.degrees(math.asin(max(-1.0, min(1.0, n.z))))
    print("RAKE  dash face from horizontal      %.3f deg" % dash_rake)
    print("RAKE  KVS slot normal, elev from horiz %.3f deg" % slot_rake)
    print("RAKE  KVS console face, elev from horiz %.3f deg" % panel_rake)
    print("      (console face tilts %.3f deg from the horizontal plane)"
          % (90.0 - panel_rake))

    # angle between the console face normal and the close camera's view axis
    cfwd = dirn(cc.matrix_world.to_3x3(), (0, 0, -1))
    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-cfwd).dot(n)))))
    print("OBLIQ console face normal vs close-cam view axis %.3f deg" % obliq)

    # ------------------------------------------------------ ground truth
    saved_states = {}
    for i, d in enumerate(domes):
        saved_states[d.name] = d.data.materials[0].name
    T.render_colour(scene, os.path.join(OUT, "gt_platen0.png"),
                    visible=ctrl["platen"]["frame_objs"][0])
    T.render_colour(scene, os.path.join(OUT, "gt_full.png"),
                    visible=plate + live)
    T.render_colour(scene, os.path.join(OUT, "gt_live.png"), visible=live)
    # The one that gets SCORED: exactly the objects the browser renders live,
    # in exactly the state check/compare.mjs puts the page in -- lamps on the
    # "read" pattern, key up, reel unrotated.  Anything else and the rms is
    # measuring a state mismatch instead of a rendering mismatch.
    Lc = ctrl["lamps"]
    for i, d in enumerate(Lc["domes"]):
        d.data.materials[0] = (Lc["on"][i] if Lc["patterns"]["read"][i]
                               else Lc["off"][i])
    bpy.context.view_layer.update()
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"),
                    visible=reel + key + domes)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + reel + key + domes)
    for i, d in enumerate(Lc["domes"]):
        d.data.materials[0] = Lc["off"][i]
    bpy.context.view_layer.update()
    for deg in (0.0, 40.0):
        rot = (Matrix.Translation(hub)
               @ Matrix.Rotation(math.radians(deg), 4, reel_axis)
               @ Matrix.Translation(-hub))
        sv = {o.name: o.matrix_world.copy() for o in reel}
        for o in reel:
            o.matrix_world = rot @ sv[o.name]
        bpy.context.view_layer.update()
        T.render_colour(scene, os.path.join(OUT, "gt_reel_%03d.png"
                                            % round(deg)), visible=reel)
        for o in reel:
            o.matrix_world = sv[o.name]
        bpy.context.view_layer.update()

    # ---------------------------------------------------------- scene.json
    px, py = mod.project(scene, cc, hub)
    lamp_recs = []
    for i, d in enumerate(domes):
        lamp_recs.append({"node": d.name,
                          "off": ctrl["lamps"]["off"][i].name,
                          "on": ctrl["lamps"]["on"][i].name,
                          "label": ctrl["lamps"]["labels"][i]})
    rows = T.verify_depth(scene, cc, dep,
                          [("reel hub", hub), ("panel centre", ctr),
                           ("text plane origin", origin)])
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-20s want %.5f  got %.5f  err %+.5f"
              % (nm, want, got, err))

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
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "props": {
            "reel": {"glb": "reel.glb", "kind": "rotate",
                     "label": ctrl["tape"]["label"],
                     "hub": T.to3(hub), "axis": T.to3(reel_axis),
                     "pivot_px": {"x": px, "y": py},
                     "hotspot": mod.clamp_rect(
                         mod.bbox_rect(scene, cc, reel, pad=8), W, H)},
            "key": {"glb": "key.glb", "kind": "hinge",
                    "label": ctrl["key"]["label"],
                    "hinge": T.to3(key_hinge), "axis": T.to3(key_axis),
                    # Blender rotates +X by these; three's +X rotation under
                    # (x,y,z)->(x,z,-y) has the SAME sign about the mapped
                    # axis, so the angles carry over unchanged.
                    "angles": ctrl["key"]["angles"],
                    "hotspot": mod.clamp_rect(
                        mod.bbox_rect(scene, cc, key, pad=8), W, H)},
            "lamps": {"glb": "lamps.glb", "kind": "emissive",
                      "label": ctrl["lamps"]["label"],
                      "order": ctrl["lamps"]["order"],
                      "patterns": {k: list(v) for k, v in
                                   ctrl["lamps"]["patterns"].items()},
                      "domes": lamp_recs,
                      "hotspot": mod.clamp_rect(
                          mod.bbox_rect(scene, cc,
                                        ctrl["lamps"]["hotspot_objs"], pad=8),
                          W, H)},
        },
        # ---- THE RAKED SURFACE, for the DOM overlay ----------------------
        # An orthonormal frame in three.js world coords.  A DOM element of
        # (px_w x px_h) CSS pixels laid on it with
        #   M = [u*s | v*s | n | origin]   (s = metres per CSS px)
        # lands exactly on the console face at any camera.
        "text_plane": {
            "origin": T.to3(origin),
            "u": T.to3(u), "v": T.to3(v), "n": T.to3(n),
            "half_w": 0.158, "half_h": (WIN_HI - WIN_LO) / 2,
            # size_m is Blender's FONT.size and is NOT an em: 0.031 here
            # advances 0.009631 m per character, a ratio of 0.310667.  The
            # frontend needs the ADVANCE, in metres, and solves the font-size
            # from the face's own measured em -- so adv_m is mandatory and
            # size_m is informational.
            #
            # adv_m/cap_m/base_m are MEASURED off Blender by
            # pipeline/typemetrics.py (bbox("MM") - bbox("M") on to_mesh()).
            # This file used to carry a hand-written adv_m = 0.0100, band-
            # detected off gt_platen0.png as the old brief instructed; that is
            # 3.8% wide and laid the transcript out 15 stage px too wide.
            # base_m replaces the old `base_adj = 3.2` fudge: it is Blender's
            # own baseline offset below the FONT origin, it scales with size,
            # and the frontend measures the browser's matching baseline with a
            # zero-height inline-block probe.  base_adj stays in the schema and
            # must be 0.
            "type": dict(TM.type_block(
                mod, mod.TXT_SIZE,
                lead_m=mod.TXT_LEAD, left_m=mod.TXT_LEFT,
                top_m=mod.TXT_TOP - win_mid,
                n_lines=max(len(f) for f in mod.PLATEN)), align="left"),
            "rake_deg": {"dash_face": dash_rake,
                         "slot_normal_elev": slot_rake,
                         "console_face_normal_elev": panel_rake,
                         "console_face_from_horizontal": 90.0 - panel_rake,
                         "obliquity_to_close_cam": obliq},
            # where the aperture corners land in the 1280x720 close frame --
            # the frontend asserts its DOM plane against these
            "corners_px": {
                nm: dict(zip(("x", "y"), mod.project(
                    scene, cc, origin + u * (0.158 * sx)
                    + v * (((WIN_HI - WIN_LO) / 2) * sy))))
                for nm, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                                   ("bl", -1, -1), ("br", 1, -1))},
        },
        # the sample transcript, so nothing about it is baked
        "platen_text": mod.PLATEN,
        "depth_verify": [{"name": n_, "analytic": w, "baked": g, "err": e}
                         for n_, w, g, e in rows],
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
#         --python live3d/pipeline/export_kvs.py -- refit
#
# main() above rebuilds the shell and RE-RENDERS plate.png, depth.bin and every
# gt_*.png.  Running it would invalidate every number in live3d/RESULTS.md and
# modules/KVS/NOTES.md.  This entry point does none of that: it builds the port
# alone in an empty scene, writes assets/KVS/refit.glb, and merges a "refit"
# block into the existing scene.json.  Nothing else in assets/KVS is opened for
# writing.  FIX_UPLOAD.md section 0, decision 3.
#
# The anchor is FIX_UPLOAD's placement table (364, 685) nudged 12 px down, which
# section 3.5 sanctions up to 15.  The reason is measured and recorded in
# modules/KVS/NOTES.md: KVS's console has a rounded base moulding whose fillet
# crest runs to y ~ 680, and the clean flat deck below it is only ~38 px tall.
# At (364, 685) a 56 px port straddles that fillet and needs an 8.9 mm stand-off
# to clear the depth composite; at (364, 697) it sits on flat deck (plane-fit
# residual 0.07 mm max) and needs 3.5 mm.
KVS_REFIT = dict(px=364, py=700, port_px=56,
                 carrier_window=(332, 396, 682, 718),
                 label="REFIT",
                 # The size mark (P-3, P-5) is FIX_UPLOAD 2's cover story for a
                 # port whose physical size varies across the fleet.  Measured
                 # at KVS's 65 x 44 px it is a 3 px smudge on the lower-left
                 # facet and costs 532 triangles.  Not shipped; the parameter
                 # stays for the roomier modules (IPM 63 mm, OTA 65 mm).
                 mark=None,
                 # KVS has the console's brass base moulding 25 px above the
                 # port, so there is structure for it to belong to and the
                 # riveted sub-base is not needed (FIX_UPLOAD 1.4).  It would
                 # also climb the fillet: measured, the 1.3 W square footprint
                 # reaches +8.7 mm through the deck plane at its top corners.
                 sub_base=False, service_rail=True)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(KVS_REFIT)
    A = RP.solve_anchor("KVS", K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"])
    P = RP.build("kvs_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export("KVS", A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))


# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_kvs.py -- mast
#
# Like `refit`, and for the same reason: main() re-renders plate.png, depth.bin
# and all seven gt_*.png and would invalidate every number in live3d/RESULTS.md
# and modules/KVS/NOTES.md.  This entry point builds the mast alone in an empty
# scene, writes assets/KVS/mast.glb, and merges a "mast" block into the
# existing scene.json.  Nothing else in assets/KVS/ is opened for writing.
# STATUS_AT_A_GLANCE.md section 6; FIX_UPLOAD.md section 0 decision 3.
#
# WHERE IT SITS, AND WHY IT IS NOT AT 1.5 W.
# The refit port publishes `scene.json -> refit.service_rail.free_from_m` =
# 1.5 W = 0.0457 m as the point where this fitting MAY start (FIX_UPLOAD
# 12.13 / STATUS_AT_A_GLANCE 11.2).  That is a floor, not an address, and at
# the floor the mast does not work: `refit.js`'s docket is 520 x 318 and its
# least-overlap solver puts it deterministically at (12, 345) on KVS, so at
# 1.5 W the docket covers x 12..532 over the mast's bezel from x 485 to 532 --
# the first 45 % of the tube, which is the half the LANDING segments sort
# into.  The whole point of this component is that it reads WHILE the port is
# open.  Shipped at 3.2 W = 0.0974 m, which puts the mast's envelope at
# x 548..756 with a 16 px gutter to the docket, and the rail is built
# CONTINUOUS from the port's own built end (0.65 W) so the longer offset reads
# as one rail with a fitting at each end rather than as two lugs.
#
# The other three numbers are measured and the reasons are in
# modules/KVS/NOTES.md section 15:
#   mast_px 190   the largest that keeps the envelope clear of the baked
#                 `KVS CORE MEMORY BANKS` nameplate, whose lower edge is at
#                 y = 630; at 200 px the envelope reaches y 638 and at 220 it
#                 is on it.
#   rake 45 deg   the carrier is at 57.33 deg obliquity and its two in-plane
#                 axes project to within 7.6 deg of the SAME screen direction,
#                 so a fitting lying flat on the deck has no second readable
#                 axis at all.  Raked 45 deg the face is at 12.50 deg -- KVS's
#                 own console face is 12.35 -- and both axes project at
#                 1849/1875 px/m, i.e. unforeshortened.
#   m = 6         the count of keystore-module/vuln_tests/NN_*.py, never
#                 max(NN) (STATUS_AT_A_GLANCE 9.4 rule 4).
KVS_MAST = dict(mast_px=190, start_w=3.2, rake_deg=45.0, m=6,
                kind="defensive",
                # The engraved per-lamp numbers of section 6.1 are OFF, and
                # the reason is measured rather than assumed; see NOTES 15.
                numbers=False)


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(KVS_MAST)
    A = SMT.solve_mast("KVS", mast_px=K["mast_px"], start_w=K["start_w"],
                       rake_deg=K["rake_deg"], m=K["m"], kind=K["kind"],
                       numbers=K["numbers"])
    P = SMT.build("kvs_mast", A["frame_blender"], A["carrier_blender"],
                  A["L_m"], m=A["m"], kind=K["kind"], numbers=K["numbers"],
                  rail=A["rail"], ramp=A["rail_ramp"])
    SMT.export("KVS", A, P)
    print("TELLTALE MAST OK -> %s  (%d tris)" % (OUT, P["tris"]))


if __name__ == "__main__":
    _argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "refit" in _argv:
        refit()
    elif "mast" in _argv:
        mast()
    else:
        main()
