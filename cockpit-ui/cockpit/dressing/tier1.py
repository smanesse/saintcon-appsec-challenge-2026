"""
Set-dressing TIER 1 -- "finish what already looks unfinished".

DRESSING_PLAN.md section 6, tier 1, in the plan's own priority order:

  1. P3a/P3b  column base junctions   -- the rawest intersection in the frame
  2. C3       shell-overhead face kit -- the blank grey slab at x 464..663
  3. H2       duct & conduit ring     -- cheap arc geometry, fills the top strip
  4. X1       cable loom & tube run   -- makes the eight heroes look installed
  5. H3       placard & stencil set   -- biggest era-read per hour (first pass)

Contract (DRESSING_BRIEF.md): geometry only. No render, no camera, no scene
settings, NO LIGHTS, no manifest, no glow mask, no hotspots. Tier 1 is also
very nearly zero-emissive: the only lamps it contains are C3's three recessed
lenses and they are all DARK.

    from dressing import tier1
    tier1.add_tier1(P, mats)   ->  {"dress": [objects]}
"""
import bpy
import os
import math
import sys

from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import shell                                                     # noqa: E402
import slots                                                     # noqa: E402

try:                       # importable as a package or as a bare module
    from dressing import kit, slots_ext
except ImportError:                                              # pragma: no cover
    import kit                                                   # noqa: F401
    import slots_ext                                             # noqa: F401


# --------------------------------------------------------------- geometry
CR = 0.075                       # column radius == P["pillar_radius"]

# P3 vertical budget.  The plan says z 0.88-1.07, but IPM's tray reaches down to
# world z 1.044 (local Y +0.290 at slot z 1.46) and OTA's lower bare collar to
# z 1.058, so the real ceiling for this prop is 1.03.  Below z 0.861 the column
# is buried inside the dash face.
P3_Z = 0.950                     # slot height (mid of the junction)
P3_Y0, P3_Y1 = -0.115, 0.080     # world 0.835 .. 1.030
# The dash face is RAKED: at the column it runs z 0.849 (front of the
# skirt, r 2.47) to z 0.946 (back, r 2.67). A flat skirt foot therefore
# has to start below 0.849 or its front edge floats.

# H2.  Three parallel runs.  Radii chosen against the shell's own furniture:
#   r 2.20  inboard of ceil_rib_1 (r 2.216..2.301) and 25 mm below it
#   r 2.42  clear of the columns, whose outer surface is at r 2.645
#   r 2.70  outboard of the columns, just under the cove light arc
# All at z 2.125: a 0.025 tube tops out at 2.150 against a beam bottom of
# 2.1625, i.e. 12.5 mm of clearance, exactly as the plan computed.
# NONE of the three runs is brass -- only their strap bands, tees and glands
# are. Three gold pipes across the whole top of frame is both untrue to how a
# ship routes services and, on its own, enough brass area to fail the
# section 5.4 saturation assertion (they are ~45% of all dressing pixels).
#   (radius, tube radius, ribbed, material key)
H2_Z = 2.125
H2_RUNS = ((2.20, 0.025, False, "paint"), (2.42, 0.030, True, "hull_l"),
           (2.70, 0.025, False, "slate"))
H2_A0, H2_A1 = -55.0, 55.0       # continued past the +/-46 frame edge (7.1)
H2_TEES = (-33.0, 6.0, 34.0)

# X1.  The loom rides round the BACK-OUTBOARD flank of each column (105 deg
# from the pilot-facing side) so its own column occludes all but an ~11 px
# sliver on the outboard edge.  That keeps it out of the window band and clear of OTA's
# clamp arms, which reach x = 0.119 on the column's flanks.
X1_PHI = 105.0
X1_ROFF = 0.104
X1_R = 0.018

# under-dash-lip runs.  dash_lip spans (2.345, 0.792) -> (2.300, 0.755); the
# fascia starts at r 2.305.  A 0.015 loom at r 2.292 / z 0.734 tucks into the
# shadow line right under the lip, and stays outboard of LOG (-24..-5) and
# MTA (+4..+20), and above the tier-2/3 fascia panels (all top out at z 0.71).
X1_LIP_R, X1_LIP_Z, X1_LIP_TUBE = 2.292, 0.734, 0.015
X1_LIP_LEFT = (-36.0, -25.5)
X1_LIP_RIGHT = (21.5, 36.0)


def _column(P, index):
    """World frame of a shell column: axis point plus the three unit axes of
    `slots.pillar`'s local frame (+X right along the surface, +Y up,
    +Z out toward the pilot)."""
    n = P["pillar_count"]
    spread = P["pillar_spread"]
    angs = [0.0] if n == 1 else [
        -spread + 2 * spread * i / (n - 1) for i in range(n)]
    ang = angs[index]
    a = math.radians(ang)
    r = P["radius"] - P["pillar_inset"]
    axis = Vector((r * math.sin(a), r * math.cos(a), 0.0))
    ex = Vector((math.cos(a), -math.sin(a), 0.0))
    ez = Vector((-math.sin(a), -math.cos(a), 0.0))
    return axis, ex, Vector((0.0, 0.0, 1.0)), ez, ang


def _around(axis, ex, ez, phi_deg, rad, z):
    """World point at `rad` from a column axis, `phi_deg` round from the
    pilot-facing side (+ve toward local +X)."""
    p = math.radians(phi_deg)
    v = axis + ex * (rad * math.sin(p)) + ez * (rad * math.cos(p))
    return Vector((v.x, v.y, z))


# ============================================== 1. P3 column base junctions
def _p3(P, index, made, frame_no, plate):
    """Where the column meets the dash there is currently a raw intersection
    with no transition -- the clearest 'unfinished 3D' tell in the frame.

    A cast skirt wrapping the cylinder, a bolted flange, a cable gland with a
    rubber boot, a top band, rivets and a stencilled frame number. P3a and P3b
    are the same object; only the STENCIL content is mirrored (plan section 6),
    or the asymmetry disappears.
    """
    br = kit.mat("brass")
    loc, eul = slots.pillar(P, index, z=P3_Z)
    root = kit.frame_empty(f"dr_p3_{index}_root", loc, eul)
    made.append(root)
    out = []
    sgn = -1 if index == 0 else 1        # outboard direction, in local +X
    ax = (0.0, 0.0, -CR)                 # the column axis, in the local frame

    # cast skirt: a turned fillet flaring down into the dash face
    prof = [(0.1060, 0.000), (0.1055, 0.022), (0.1030, 0.044),
            (0.0975, 0.062), (0.0918, 0.080), (0.0862, 0.098),
            (0.0830, 0.111), (0.0822, 0.117)]
    out.append(kit.revolve(f"dr_p3_{index}_skirt", prof, kit.mat("hull_l"),
                           center=(ax[0], P3_Y0, ax[2]),
                           rot=(-math.pi / 2, 0, 0), verts=40, cap=False))
    # weld bead where the skirt lands on the dash
    out.append(kit.tube(f"dr_p3_{index}_bead", (0.0, P3_Y0 + 0.030, -CR),
                        0.1075, 0.1035, 0.010, kit.mat("hull_l"),
                        rot=(math.pi / 2, 0, 0), verts=40))

    # bolted flange at the top of the skirt
    fy = P3_Y0 + 0.126
    out += kit.wrap_collar(f"dr_p3_{index}_flange", (0.0, fy, -CR),
                           0.0785, 0.1010, 0.014, br)
    for i, phi in enumerate((-58.0, -20.0, 20.0, 58.0)):
        p = math.radians(phi)
        d = Vector((math.sin(p), 0.0, math.cos(p)))
        c = Vector((0.0, fy, -CR)) + d * 0.1035
        out.append(kit.cyl(f"dr_p3_{index}_bolt_{i}", tuple(c), 0.0058, 0.007,
                           kit.mat("steel"), rot=(0, p, 0), verts=6,
                           smooth=False, bevel=0.0008))

    # top band on the naked column -- the piece the eye watches grip the tube
    out += kit.wrap_collar(f"dr_p3_{index}_band", (0.0, P3_Y1 - 0.012, -CR),
                           0.0782, 0.0905, 0.016, br)
    out += kit.rivet_row(f"dr_p3_{index}_rv",
                         (-0.058, P3_Y0 + 0.062, 0.023),
                         (0.058, P3_Y0 + 0.062, 0.023), 7, r=0.0032)

    # cable gland + rubber boot on the OUTBOARD flank
    gphi = math.radians(sgn * 60.0)
    gd = Vector((math.sin(gphi), 0.0, math.cos(gphi)))
    gc = Vector((0.0, P3_Y0 + 0.082, -CR)) + gd * 0.0885
    out += kit.gland(f"dr_p3_{index}_gland", tuple(gc), r=0.0135,
                     rot=(0, gphi, 0))

    # stencilled frame number + a data plate, mirrored in CONTENT not geometry
    out += kit.stencil(f"dr_p3_{index}_fr", frame_no,
                       (0.0, P3_Y0 + 0.100, 0.0250), 0.0185)
    out += kit.nameplate(f"dr_p3_{index}_pl", plate[0],
                         (0.0, P3_Y0 + 0.048, 0.0240), w=0.086, h=0.024,
                         size=0.0095, sub=plate[1])
    out += kit.warn_triangle(f"dr_p3_{index}_wt",
                             (sgn * -0.052, P3_Y1 - 0.030, 0.0165), 0.024)
    out += kit.inspection_stamp(f"dr_p3_{index}_is",
                                (sgn * 0.050, P3_Y1 - 0.032, 0.0170),
                                plate[2], r=0.0085)
    kit.parent_to(out, root)
    made.extend(out)


# ============================================ 2. C3 shell-overhead face kit
def _oh_geometry(P, i):
    """Recover an overhead's world placement from `shell.OVERHEADS` without
    touching shell.py. Returns (centre, size, angle_deg, rot_z)."""
    it = shell.OVERHEADS[i]
    a = math.radians(it["angle"])
    rr = P["radius"] * it["r"]
    px, py = rr * math.sin(a), rr * math.cos(a)
    zc = P["ceiling"] - it["drop"] - it["h"] / 2
    return (Vector((px, py, zc)), (it["w"], it["d"], it["h"]), it["angle"], -a)


def _c3_console(P, i, made, title, sub, lenses=3, door=True):
    """Detail one of the shell's bare grey console slabs.

    The `oh_2` box at -7 deg lands at x 464..663, y 194..234 -- dead centre-top
    of frame and, per the plan, the worst-looking object in the render. This
    adds geometry COINCIDENT with the existing box: a proper brass reader strip
    on the true front face (shell.py's own strip is offset sideways, not
    forward), a hinged access door with a hasp, recessed unlit lenses, louvre
    fins on the visible underside, rivet rows and compartment lettering.
    """
    br = kit.mat("brass")
    c, (w, d, h), ang, rz = _oh_geometry(P, i)
    boxf = kit.frame_empty(f"dr_c3_{i}_box", c, (0.0, 0.0, rz))
    made.append(boxf)
    # panel frame on the FRONT face: +X right, +Y up, +Z out at the pilot
    front = kit.frame_empty(f"dr_c3_{i}_front", (0.0, -d / 2, 0.0),
                            (math.pi / 2, 0.0, 0.0), parent=boxf)
    made.append(front)
    under = kit.frame_empty(f"dr_c3_{i}_under", (0.0, 0.0, -h / 2),
                            (math.pi, 0.0, 0.0), parent=boxf)
    made.append(under)

    hw, hh = w / 2, h / 2
    fo = []
    # brass reader strip along the bottom of the front face -- the strip
    # shell.py meant to put here (its own is offset sideways, not forward)
    # ... built as a RECESSED reader window (dark ground glass behind a brass
    # frame, engraved legend, no phosphor -- plan section 5.2), not a solid
    # brass bar: a 0.77 m blown-out slab at top-centre of frame is exactly the
    # large-scale contrast dressing is supposed to give up.
    sy, sh = -hh * 0.62, h * 0.30
    strip_top = sy + sh / 2
    fo.append(kit.box(f"dr_c3_{i}_strip", (0.0, sy, 0.006),
                      (w * 0.90, sh, 0.011), kit.mat("case"), bevel=0.0022))
    fo += kit.bez_frame(f"dr_c3_{i}_stripbez", 0.0, sy, w * 0.90, sh,
                        0.006, 0.014, br, bar=0.0055)
    for k in range(6):
        fo += kit.stencil(f"dr_c3_{i}_striptx_{k}",
                          ("CIRCUIT", "VENT", "PWR", "SIG", "AUX", "GND")[k],
                          (-w * 0.36 + k * (w * 0.144), sy, 0.013),
                          min(0.017, sh * 0.34), m=kit.mat("ivory"))
    # a raised seam between the lettering and the strip, so the face is not
    # one flat plane
    fo.append(kit.box(f"dr_c3_{i}_bead", (0.0, strip_top + 0.008, 0.004),
                      (w * 0.965, 0.006, 0.008), br, bevel=0.0015))
    # rivet rows top and bottom
    n = max(8, int(w / 0.042))
    fo += kit.rivet_row(f"dr_c3_{i}_rvt", (-hw * 0.94, hh * 0.82, 0.004),
                        (hw * 0.94, hh * 0.82, 0.004), n, r=0.0038)
    fo += kit.rivet_row(f"dr_c3_{i}_rvb", (-hw * 0.94, -hh * 0.93, 0.004),
                        (hw * 0.94, -hh * 0.93, 0.004), n, r=0.0038)
    # end ribs so the slab reads as a case with cheeks, plus mounting lugs
    # that rationalise the shell's own stray brass tab beside this box
    for k, sgn in enumerate((-1, 1)):
        fo.append(kit.box(f"dr_c3_{i}_rib_{k}", (sgn * hw * 0.965, 0.0, 0.006),
                          (0.014, h * 0.94, 0.012), kit.mat("hull_l"),
                          bevel=0.002))
        fo.append(kit.box(f"dr_c3_{i}_lug_{k}",
                          (sgn * (hw + 0.020), -hh * 0.30, 0.002),
                          (0.048, h * 0.30, 0.010), br, bevel=0.0022))
        fo += kit.rivet_row(f"dr_c3_{i}_lugrv_{k}",
                            (sgn * (hw + 0.006), -hh * 0.30, 0.008),
                            (sgn * (hw + 0.034), -hh * 0.30, 0.008), 2,
                            r=0.0032)

    if door:
        dw, dh = min(0.26, w * 0.30), h * 0.50
        dx = -hw + dw * 0.62
        dy = hh * 0.24
        fo.append(kit.box(f"dr_c3_{i}_door", (dx, dy, 0.008),
                          (dw, dh, 0.011), kit.mat("hull_l"), bevel=0.0035))
        fo += kit.bez_frame(f"dr_c3_{i}_doorbez", dx, dy, dw, dh,
                            0.008, 0.016, br, bar=0.0045)
        for k, sy in enumerate((-0.32, 0.32)):
            fo.append(kit.box(f"dr_c3_{i}_hinge_{k}",
                              (dx - dw / 2 + 0.005, dy + dh * sy, 0.014),
                              (0.022, 0.014, 0.010), br, bevel=0.002))
        # hasp + padlock loop on the far edge
        fo.append(kit.box(f"dr_c3_{i}_hasp", (dx + dw / 2 - 0.002, dy, 0.016),
                          (0.034, 0.013, 0.006), br, bevel=0.0016))
        fo.append(kit.tube(f"dr_c3_{i}_loop", (dx + dw / 2 + 0.012, dy, 0.020),
                           0.0095, 0.0068, 0.005, br, verts=16,
                           rot=(math.pi / 2, 0, 0)))
        fo += kit.stencil(f"dr_c3_{i}_dtxt", "ACCESS",
                          (dx, dy - dh * 0.34, 0.017), h * 0.100)

    # recessed unlit lenses.  ALL DARK -- the 1-in-5 rule, and nothing on a
    # dressing prop is allowed a phosphor face.
    for k in range(lenses):
        lx = hw - 0.058 - k * (min(0.052, w * 0.062))
        fo += kit.lampcell(f"dr_c3_{i}_lens_{k}", (lx, hh * 0.36, 0.004),
                           w=0.040, h=0.030, lit=False, round_lens=True,
                           kind=("amber", "green", "white")[k % 3],
                           depth=0.012)

    # compartment lettering -- the number-one era cue in the plan
    tx = -hw * 0.06 if door else 0.0
    fo += kit.stencil(f"dr_c3_{i}_t0", title, (tx, hh * 0.50, 0.004),
                      min(0.032, h * 0.185))
    fo += kit.stencil(f"dr_c3_{i}_t1", sub, (tx, hh * 0.04, 0.004),
                      min(0.022, h * 0.125))
    fo += kit.inspection_stamp(f"dr_c3_{i}_is", (hw * 0.34, hh * 0.10, 0.006),
                               "A7", r=0.010)
    kit.parent_to(fo, front)
    made.extend(fo)

    # underside: louvre fins along the front lip, plus a rivet row.  The pilot
    # sits 0.4 m below these boxes, so the underside IS in shot -- grazing, but
    # enough that ribbing reads as texture instead of blank grey.
    uo = []
    for k in range(3):
        uo += kit.louvre_row(f"dr_c3_{i}_lv_{k}",
                             (-w * 0.26 + k * (w * 0.26), d * 0.30, 0.0),
                             w * 0.20, 5, fin_h=0.007, depth=0.009)
    uo += kit.rivet_row(f"dr_c3_{i}_urv", (-w * 0.44, d * 0.42, 0.002),
                        (w * 0.44, d * 0.42, 0.002), n, r=0.0034)
    kit.parent_to(uo, under)
    made.extend(uo)


def _c3_pod(P, i, made):
    """The `oh_1` pod at -29 deg: a brass band on hex bolts, and a ribbed
    flexible hose running up into the ceiling."""
    br = kit.mat("brass")
    it = shell.OVERHEADS[i]
    a = math.radians(it["angle"])
    rr = P["radius"] * it["r"]
    px, py = rr * math.sin(a), rr * math.cos(a)
    zc = P["ceiling"] - it["drop"] - it["h"] / 2
    pr = it["w"] / 2
    out = []
    out += kit.wrap_collar("dr_c3_pod_band", (px, py, zc - it["h"] * 0.22),
                           pr * 1.01, pr * 1.19, 0.030, br, rot=(0, 0, 0),
                           verts=32)
    for k, phi in enumerate((-40.0, 0.0, 40.0)):
        p = a + math.radians(180.0 + phi)     # bolts on the pilot-facing side
        c = Vector((px + pr * 1.22 * math.sin(p), py + pr * 1.22 * math.cos(p),
                    zc - it["h"] * 0.22))
        out.append(kit.cyl(f"dr_c3_pod_bolt_{k}", tuple(c), 0.0055, 0.008,
                           kit.mat("steel"), rot=(math.pi / 2, 0, -p),
                           verts=6, smooth=False))
    # ribbed hose from the pod's outboard shoulder up into the ceiling
    sp = a + math.radians(-118.0)
    base = Vector((px + pr * 0.86 * math.sin(sp), py + pr * 0.86 * math.cos(sp),
                   zc + it["h"] * 0.40))
    top = Vector((px + pr * 1.9 * math.sin(sp), py + pr * 1.9 * math.cos(sp),
                  P["ceiling"] - 0.004))
    pts, radii = [], []
    for k in range(9):
        t = k / 8.0
        p = base.lerp(top, t)
        p.z = base.z + (top.z - base.z) * (t ** 0.72)
        pts.append(p)
        radii.append(0.0165 * (1.0 + 0.20 * math.sin(t * 11.0)))
    out.append(kit.sweep("dr_c3_pod_hose", pts, 0.0165, kit.mat("rubber"),
                         sections=10, radii=radii))
    out.append(kit.tube("dr_c3_pod_hosecuf", tuple(pts[0]), 0.0215, 0.0160,
                        0.014, br, rot=(math.pi / 2, 0, 0), verts=16))
    out += kit.stencil("dr_c3_pod_txt", "VENT",
                       (px - 0.055 * math.cos(a), py + 0.055 * math.sin(a),
                        zc - it["h"] * 0.44), 0.026,
                       rot=(math.pi, 0.0, -a))
    made.extend(out)


def _c3_lamp(P, i, made):
    """The `oh_5` lamp cone at +47 deg: a bulb guard cage and a braided cord.

    Same perforated cage mesh D5's gooseneck lamps will use (plan section 6).
    """
    br = kit.mat("brass")
    it = shell.OVERHEADS[i]
    a = math.radians(it["angle"])
    rr = P["radius"] * it["r"]
    px, py = rr * math.sin(a), rr * math.cos(a)
    zc = P["ceiling"] - it["drop"] - it["h"] / 2
    rim_z = zc - it["h"] / 2
    rrad = it["w"] / 2
    out = []
    out.append(kit.tube("dr_c3_lamp_rim", (px, py, rim_z), rrad * 1.12,
                        rrad * 0.99, 0.012, br, verts=28))
    out += kit.cage("dr_c3_lamp_cage", (px, py, rim_z - 0.004), rrad * 1.02,
                    0.082, wires=6)
    # braided cord looping from the shade up to the ceiling beside the stalk
    cs = a + math.radians(96.0)
    pts = [Vector((px + rrad * 0.9 * math.sin(cs),
                   py + rrad * 0.9 * math.cos(cs), zc + it["h"] * 0.30)),
           Vector((px + rrad * 1.5 * math.sin(cs),
                   py + rrad * 1.5 * math.cos(cs), zc + it["h"] * 0.62)),
           Vector((px + rrad * 1.2 * math.sin(cs),
                   py + rrad * 1.2 * math.cos(cs), P["ceiling"] - 0.10)),
           Vector((px + rrad * 0.5 * math.sin(cs),
                   py + rrad * 0.5 * math.cos(cs), P["ceiling"] - 0.004))]
    out.append(kit.sweep("dr_c3_lamp_cord", pts, 0.0095, kit.mat("braid"),
                         sections=8))
    out += kit.pclip("dr_c3_lamp_clip", tuple(pts[2]), 0.0095)
    made.extend(out)


# ================================================ 3. H2 duct & conduit ring
def _h2(P, made):
    """Three parallel service runs following the hull arc across the whole top
    of frame: two rigid brass-strapped conduits and one ribbed flexible duct,
    strap bands every ~0.35 m, three junction tees with runs out to the wall.

    Cheapest item in the plan by a distance: arc geometry plus an array, and it
    fills the entire top strip.
    """
    out = []
    span = abs(H2_A1 - H2_A0)
    for k, (r, tr, ribbed, mkey) in enumerate(H2_RUNS):
        arc_len = r * math.radians(span)
        bands = max(4, int(arc_len / 0.35))
        objs, pts = kit.conduit_arc(f"dr_h2_run_{k}", H2_A0, H2_A1, r, H2_Z,
                                    tube_r=tr, bands=bands, ribbed=ribbed,
                                    m=kit.mat(mkey), sections=12)
        out += objs
        # painted marker rings, so the runs read as three different services
        for j, ma in enumerate((-40.0, -12.0, 16.0, 44.0)):
            aa = math.radians(ma)
            out.append(kit.tube(f"dr_h2_mk_{k}_{j}",
                                (r * math.sin(aa), r * math.cos(aa), H2_Z),
                                tr * 1.10, tr * 0.99, 0.016,
                                kit.mat("ivory") if k != 1
                                else kit.mat("paper"),
                                rot=(math.pi / 2, 0.0, -aa), verts=16))

    # junction tees on the outer run, each with a short run out to the hull
    r_out = H2_RUNS[-1][0]
    for k, ang in enumerate(H2_TEES):
        aa = math.radians(ang)
        pt = (r_out * math.sin(aa), r_out * math.cos(aa), H2_Z)
        out += kit.conduit_tee(f"dr_h2_tee_{k}", pt, ang, tube_r=0.025,
                               stub=0.055, down=True)
        # ... and outward to a junction box on the wall, ABOVE where H1's
        # annunciator strip will land (H1 tops out at z 2.13).
        wall = P["radius"] - 0.05
        pts = [Vector((r_out * math.sin(aa), r_out * math.cos(aa), H2_Z)),
               Vector(((r_out + 0.10) * math.sin(aa),
                       (r_out + 0.10) * math.cos(aa), H2_Z + 0.014)),
               Vector((wall * math.sin(aa), wall * math.cos(aa),
                       H2_Z + 0.030)),
               Vector(((wall + 0.02) * math.sin(aa),
                       (wall + 0.02) * math.cos(aa), H2_Z + 0.032))]
        out.append(kit.sweep(f"dr_h2_drop_{k}", pts, 0.018, kit.mat("paint"),
                             sections=10))
        loc, eul = slots_ext.wallband(P, ang, H2_Z + 0.032)
        jb = kit.frame_empty(f"dr_h2_jb_{k}", loc, eul)
        made.append(jb)
        jo = [kit.box(f"dr_h2_jbox_{k}", (0.0, 0.0, 0.024),
                      (0.084, 0.062, 0.048), kit.mat("hull_l"), bevel=0.004)]
        jo += kit.bez_frame(f"dr_h2_jbez_{k}", 0.0, 0.0, 0.084, 0.062, 0.044,
                            0.052, kit.mat("brass"), bar=0.005)
        jo += kit.rivet_row(f"dr_h2_jrv_{k}", (-0.030, -0.024, 0.050),
                            (0.030, -0.024, 0.050), 4, r=0.0026)
        kit.parent_to(jo, jb)
        out += jo

        # a hanging conduit tag with a flow arrow -- H3's directional arrows,
        # readable because they sit on a flat plate rather than a curved tube
        tag_z = H2_Z - 0.055
        tl, te = slots_ext.dome(P, ang, r_out - 0.004, tag_z)
        tf = kit.frame_empty(f"dr_h2_tag_{k}", tl, te)
        made.append(tf)
        to = [kit.box(f"dr_h2_tagpl_{k}", (0.0, 0.0, 0.001),
                      (0.070, 0.030, 0.0026), kit.mat("brass"), bevel=0.0010)]
        to += kit.arrow(f"dr_h2_tagar_{k}", (0.012, 0.0, 0.0028), 0.036,
                        m=kit.mat("ink"),
                        rot_z=0.0 if ang < 0 else math.pi)
        to += kit.stencil(f"dr_h2_tagtx_{k}", ("SVC", "O2", "PWR")[k],
                          (-0.020, 0.0, 0.0028), 0.011, m=kit.mat("ink"))
        kit.parent_to(to, tf)
        out += to
    made.extend(out)


# ============================================ 4. X1 cable loom & tube run
def _x1(P, made):
    """The connective tissue: bundled cloth-braided looms from the conduit ring
    down behind each column, through the P3 glands, and along under the dash
    lip; plus a brass pneumatic tube leaving MTA's fascia panel.

    Routing note. The loom sits 105 deg round from the pilot-facing side of the
    column at r 0.104, so its own column occludes all but ~11 px on the
    outboard edge. That is deliberate: it keeps the run out of the window band (plan
    7.4) and clear of OTA's clamp arms, which reach x = 0.119 on the flanks.
    """
    out = []
    for i in (0, 1):
        axis, ex, ey, ez, ang = _column(P, i)
        sgn = -1 if i == 0 else 1
        phi = sgn * X1_PHI
        # from the inner conduit run, over the column top, down the back
        a0 = math.radians(ang)
        start = Vector((H2_RUNS[0][0] * math.sin(a0),
                        H2_RUNS[0][0] * math.cos(a0), H2_Z - 0.024))
        pts = [start,
               _around(axis, ex, ez, phi * 0.35, 0.070, P["ceiling"] - 0.020),
               _around(axis, ex, ez, phi * 0.75, 0.092, P["ceiling"] - 0.075),
               _around(axis, ex, ez, phi, X1_ROFF, 2.060),
               _around(axis, ex, ez, phi, X1_ROFF, 1.720),
               _around(axis, ex, ez, phi, X1_ROFF, 1.380),
               _around(axis, ex, ez, phi, X1_ROFF, 1.100),
               _around(axis, ex, ez, phi * 0.86, X1_ROFF, 1.020),
               _around(axis, ex, ez, sgn * 60.0, 0.104, 0.955),
               _around(axis, ex, ez, sgn * 60.0, 0.098, 0.922)]
        out += kit.loom(f"dr_x1_col_{i}", pts, r=X1_R, wraps=(4,),
                        sections=10)
        # service loop + one loose zip-tied spur on the left column only
        if i == 0:
            spur = [pts[5],
                    _around(axis, ex, ez, phi * 1.16, 0.128, 1.330),
                    _around(axis, ex, ez, phi * 1.20, 0.150, 1.245),
                    _around(axis, ex, ez, phi * 1.04, 0.120, 1.205)]
            out.append(kit.sweep("dr_x1_spur", spur, X1_R * 0.52,
                                 kit.mat("braid"), sections=8))
            out += kit.tape_wrap("dr_x1_spurtie", 2, spur, X1_R * 0.52)

    # under-lip runs, outboard of LOG and MTA
    for k, (a0, a1) in enumerate((X1_LIP_LEFT, X1_LIP_RIGHT)):
        n = 14
        pts = []
        for j in range(n + 1):
            t = j / n
            aa = math.radians(a0 + (a1 - a0) * t)
            # a shallow catenary between the two end glands
            sag = 0.010 * math.sin(t * math.pi)
            pts.append(Vector((X1_LIP_R * math.sin(aa),
                               X1_LIP_R * math.cos(aa), X1_LIP_Z - sag)))
        out += kit.loom(f"dr_x1_lip_{k}", pts, r=X1_LIP_TUBE, sections=10)
        for j, idx in enumerate((2, 7, 12)):
            aa = math.radians(a0 + (a1 - a0) * idx / n)
            p = pts[idx]
            out.append(kit.tube(f"dr_x1_lipclip_{k}_{j}", tuple(p),
                                X1_LIP_TUBE * 1.28, X1_LIP_TUBE * 0.99, 0.012,
                                kit.mat("brass"),
                                rot=(math.pi / 2, 0.0, -aa), verts=18))
            out.append(kit.box(f"dr_x1_lipfoot_{k}_{j}",
                               ((X1_LIP_R + 0.016) * math.sin(aa),
                                (X1_LIP_R + 0.016) * math.cos(aa),
                                p.z + 0.020),
                               (0.016, 0.020, 0.012), kit.mat("brass"),
                               rot=(0, 0, -aa), bevel=0.0016))
        # a gland where each run passes the column and turns up to P3
        for end_a, tag in ((a0, 0), (a1, 1)):
            aa = math.radians(end_a)
            ep = Vector((X1_LIP_R * math.sin(aa), X1_LIP_R * math.cos(aa),
                         X1_LIP_Z))
            out += kit.gland(f"dr_x1_lipgl_{k}_{tag}", tuple(ep), r=0.016,
                             rot=(math.pi / 2, 0.0, -aa), boot=False)

    # the pneumatic tube leaving MTA's panel, up to the right-hand run
    mta = []
    for j in range(9):
        t = j / 8.0
        aa = math.radians(19.4 + (X1_LIP_RIGHT[0] - 19.4) * t)
        r = 2.286 - 0.020 * math.sin(t * math.pi)
        z = 0.660 + (X1_LIP_Z - 0.660) * (t ** 0.65)
        mta.append(Vector((r * math.sin(aa), r * math.cos(aa), z)))
    out.append(kit.sweep("dr_x1_pneu", mta, 0.011, kit.mat("brass"),
                         sections=10))
    for j, idx in enumerate((0, 4)):
        aa = math.radians(19.4 + (X1_LIP_RIGHT[0] - 19.4) * (idx / 8.0))
        out.append(kit.tube(f"dr_x1_pneu_band_{j}", tuple(mta[idx]), 0.0155,
                            0.0108, 0.010, kit.mat("brass_dk"),
                            rot=(math.pi / 2, 0.0, -aa), verts=14))
    # ... and its twin off LOG's outboard corner
    logt = []
    for j in range(7):
        t = j / 6.0
        aa = math.radians(-24.6 + (X1_LIP_LEFT[1] - (-24.6)) * t)
        r = 2.286 - 0.016 * math.sin(t * math.pi)
        z = 0.690 + (X1_LIP_Z - 0.690) * (t ** 0.7)
        logt.append(Vector((r * math.sin(aa), r * math.cos(aa), z)))
    out.append(kit.sweep("dr_x1_logt", logt, 0.009, kit.mat("brass"),
                         sections=8))
    made.extend(out)


# ============================================ 5. H3 placard & stencil set
def _h3(P, made):
    """First stencil pass. Lettering is the number-one era cue available and
    the cheapest thing in the plan -- but every surface tiers 2-4 will want is
    left alone, so this pass only marks structure that already exists or that
    tier 1 itself added.
    """
    out = []
    CEIL = P["ceiling"]

    # NO STEP on the dash kick.  The kick rakes back 44 deg from horizontal
    # (r 2.305 @ z 0.14 -> r 2.45 @ z 0.0), so its normal is 44 deg off
    # vertical, tilted at the pilot.
    kick_rake = math.atan2(0.14, 0.145)
    for k, ang in enumerate((-21.0, 17.0)):
        a = math.radians(ang)
        r, z = 2.372, 0.072
        loc = Vector((r * math.sin(a), r * math.cos(a), z))
        loc += Vector((-math.sin(a) * math.sin(kick_rake) * 0.006,
                       -math.cos(a) * math.sin(kick_rake) * 0.006,
                       math.cos(kick_rake) * 0.006))
        f = kit.frame_empty(f"dr_h3_kick_{k}", loc, (kick_rake, 0.0, -a))
        made.append(f)
        o = kit.stencil(f"dr_h3_nostep_{k}", "NO  STEP", (0.0, 0.0, 0.0),
                        0.042, worn=(k == 1))
        kit.parent_to(o, f)
        out += o

    # frame numbers on the radial ceiling beam undersides.  Inboard of the
    # conduit ring (r 2.20) so the conduit does not hide them.
    for k, (ang, body) in enumerate(((-14, "FR 12"), (22, "FR 15"))):
        loc, eul = slots_ext.dome(P, ang, 2.05, CEIL - 0.0985)
        f = kit.frame_empty(f"dr_h3_beam_{k}", loc, eul)
        made.append(f)
        o = kit.stencil(f"dr_h3_beamtx_{k}", body, (0.0, 0.0, 0.0), 0.052,
                        rot=(0.0, 0.0, math.pi / 2))
        kit.parent_to(o, f)
        out += o

    # compartment numbers on the hull wall band.  These sit behind MQB's and
    # DNSM's screen footprints so they are invisible in the main plate -- but
    # they WILL appear in those two modules' close-up backgrounds, which is
    # exactly the free win the plan calls out.
    for k, (ang, body) in enumerate(((-38.0, "C-11"), (31.0, "C-14"))):
        loc, eul = slots_ext.wallband(P, ang, 2.030)
        f = kit.frame_empty(f"dr_h3_wall_{k}", loc, eul)
        made.append(f)
        o = kit.stencil(f"dr_h3_walltx_{k}", body, (0.0, 0.0, 0.0), 0.062)
        o += kit.stencil(f"dr_h3_wallsub_{k}", "COMPT", (0.0, -0.055, 0.0),
                         0.030, worn=True)
        kit.parent_to(o, f)
        out += o

    made.extend(out)


# ==================================================================== entry
def add_tier1(P, mats):
    """Add tier 1's dressing geometry to the CURRENT scene.

    P    : shell PARAMS (already built)
    mats : {"brass":..., "hull":..., "hull_d":...}  -- the shell's own hero
           materials.  Dressing does NOT use them; `kit.mat()` supplies the
           desaturated set from DRESSING_PLAN.md section 5.1.
    Returns: {"dress": [list of created objects]}
    """
    made = []

    # 1 -- P3a / P3b column base junctions.  Same object, mirrored CONTENT.
    _p3(P, 0, made, "FR 9", ("AUDITOR-7", "YARD 2149", "A7"))
    _p3(P, 1, made, "FR 15", ("HULL 0x7A", "REFIT 2158", "K3"))

    # 2 -- C3 shell-overhead face kit.  Indices are into shell.OVERHEADS:
    #      1 = pod -29, 2 = console -7 (the bad slab), 3 = console +24,
    #      4 = lamp +47.  0 (-52) and 5 (+68) project off frame.
    _c3_console(P, 2, made, "OVHD CONSOLE 2", "FRAME 12", lenses=3, door=True)
    _c3_console(P, 3, made, "RELAY BAY", "FRAME 15", lenses=2, door=True)
    _c3_pod(P, 1, made)
    _c3_lamp(P, 4, made)

    # 3 -- H2 duct & conduit ring
    _h2(P, made)

    # 4 -- X1 cable loom & pneumatic tube run
    _x1(P, made)

    # 5 -- H3 placard & stencil set, first pass
    _h3(P, made)

    meshes = [o for o in made if o.type == 'MESH']
    em = kit.emissive_area(meshes)
    print(f"TIER1: {len(meshes)} meshes, {len(made) - len(meshes)} empties; "
          f"emissive area {em:.6f} m2 "
          f"({'OK -- tier 1 is deliberately dark' if em < 1e-4 else 'CHECK'})")
    return {"dress": made}


if __name__ == "__main__":
    P = dict(shell.PARAMS)
    P["exterior"] = 1
    shell.build(P)
    add_tier1(P, {"brass": bpy.data.materials["brass"],
                  "hull": bpy.data.materials["hull"],
                  "hull_d": bpy.data.materials["hull_d"]})
    bpy.context.scene.render.filepath = os.path.join(HERE, "out",
                                                     "_tier1_only.png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", bpy.context.scene.render.filepath)
