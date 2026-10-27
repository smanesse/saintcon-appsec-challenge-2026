"""
Set-dressing TIER 4 -- "accents and polish".

DRESSING_PLAN.md section 6, tier 4, items 15-21, in the plan's own order:

  15. D5a / D5b  coaming map lamps        -- riser -20 (lit) and +25 (dark)
  16. F3         chart pocket & clipboard -- fascia -0.4, between LOG and MTA
  17. F6         fire bottle & axe bracket-- fascia +43
  18. D4         radiation monitor        -- dash +42.5
  19. H3         second stencil pass      -- extends tier 1's first pass
  20. C1         overhead breaker panel   -- ceiling -20.0, rake 60
  21. C2         beacon relay head        -- ceiling +13.0, rake 58

Contract (DRESSING_BRIEF.md): geometry only. No render, no camera, no scene
settings, NO LIGHTS, no manifest, no glow mask, no hotspots.

    from dressing import tier4
    tier4.add_tier4(P, mats)   ->  {"dress": [objects]}

Why this file imports tier 2
----------------------------
Tier 2 discovered that six of the shell's seven area lights are warm
(1.00, 0.85, 0.66), so an albedo-neutral panel RENDERS at saturation ~0.32 no
matter how grey its base colour is -- its first build failed the plan section
5.4 assertion at -25%, and got WORSE when its backings were switched to a
neutral grey.  The fix is three blue-biased, idempotent, `dr_`-prefixed
materials (`dr_console`, `dr_opal`, `dr_recess`).  They are shared state, not a
recipe: defining a fourth equivalent here would double the material count and
split the console into two subtly different greys.  So tier 4 imports them,
along with tier 2's curvature helpers (`_cyl_band` / `_dash_band` / `_ff` /
`_df` / `_wf`), which is also what keeps a tier-4 rivet row sitting flat on the
same cylinder a tier-2 one does.  Tier 2's file is NOT modified.

Emissive
--------
Plan section 5.2 caps ALL dressing emissive area at 15% of the eight heroes'.
Tier 1 spent zero, tier 2 spent it on H1's three lit legend cells.  Tier 4's
entire spend is D5a's lamp mouth: ONE disc face of r 0.017 (0.00091 m2), built
with tier 2's single-face technique rather than as a solid emissive block --
three lamps built as blocks consumed 86% of the whole set's budget in tier 2's
first attempt.  D5b, C2's pointer lamp and D4's click-rate lens are all dark.

Red
---
Plan section 5.2 rations the WHOLE dressing set to three unlit painted-red
elements: F6's bottle, F2's SEAL handle (tier 3) and F1's PURGE guard
(tier 2).  F6 spends the third and last one.  Nothing else here is red.
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
    from dressing import kit, slots_ext, tier2
except ImportError:                                              # pragma: no cover
    import kit                                                   # noqa: F401
    import slots_ext                                             # noqa: F401
    import tier2                                                 # noqa: F401

# shared, idempotent, blue-biased materials + curvature helpers (see docstring)
_grey = tier2._grey
_opal = tier2._opal
_dark = tier2._dark
_cyl_band = tier2._cyl_band
_dash_band = tier2._dash_band
_ff = tier2._ff
_df = tier2._df
_wf = tier2._wf
_put = tier2._put
_bezel = tier2._bezel
_rotary = tier2._rotary
_fascia_r = tier2._fascia_r
_dash_r = tier2._dash_r
_wall_r = tier2._wall_r
_fascia_pts = tier2._fascia_pts
_rivet_arc = tier2._rivet_arc
FACE_LEN = tier2.FACE_LEN


# ------------------------------------------------------------- placements
# D5 -- riser -20.0 (lit) / +25.0 (dark), plan says z 0.94..1.24.
# MEASURED: at -20 deg the dash's far edge projects to screen y 379 and the
# riser strip behind it to y 379..405, i.e. the riser is entirely OCCLUDED by
# the dash face from the pilot's eye.  So the lamps are built from the coaming
# edge UP (z 1.06..1.23, screen y 338..379) and the cord terminates in a
# grommet at dash t 0.93 -- the bare strip between D1/D3's far edge (t 0.86)
# and the coaming.  Nothing is modelled where nothing can be seen.
#  D5b was tabled at +25.0.  MEASURED: column 1's axis is at +27.0 and at
#  r 2.57 it screens +25.33..+28.67 -- the plan's own screen rect for D5b,
#  x 898..957, is the COLUMN.  The lamp is moved to +21.5 and bends inboard
#  (both lamps bend the same way; two lamps mirrored about the centreline is
#  the symmetry tell plan 5.3 warns about), which keeps it above tier 3's D3
#  (+16.5..+27.5) exactly as plan section 4 wants and out of the column.
D5A_ANG, D5B_ANG = -20.0, 21.5
D5_Z = 1.060                       # coaming edge == P["dash_top_z"]
D5_LIFT = 0.030                    # wallband r 2.930 -> the coaming at 2.900

# F3 -- plan says fascia -1.0, 0.36 x 0.32, z 0.26..0.58.
# MEASURED hero footprints: LOG ends at -6.34 and MTA starts at +6.10, not the
# manifest's rounded -5 / +4.  Centred at -1.0 the gutters would be 0.86 deg
# left and 2.62 right; at -0.4 they are 1.46 and 2.02, both above the plan's
# 0.5-1.0 deg minimum (section 7.9) and balanced.  Width unchanged.
F3_A, F3_Z, F3_W, F3_H = -0.4, 0.420, 0.360, 0.320

# F6 -- fascia +43.0, z 0.24..0.64, 0.18 x 0.40.  Tier 2 built F5 at 0.36 wide
# rather than 0.40, so the F5/F6 gutter is 2.3 deg instead of 1.8.
F6_A, F6_Z, F6_W, F6_H = 43.0, 0.440, 0.180, 0.400

# D4 -- dash +42.5, t 0.34..0.72, 0.20 x 0.24.  KVS measures +28.84..+39.16,
# so the gutter is 1.14 deg.  87 x 49 px on screen: four features, no more.
D4_A, D4_T, D4_W, D4_H = 42.5, 0.530, 0.200, 0.240

# C1 -- plan says ceiling -19.5, r_frac 0.88, drop 0.46, rake 60, 0.32 x 0.22.
# The DEG NUMBERS IN THE PLAN'S CLEARANCE TABLE ARE WRONG, and not by a little:
# it puts the shell's oh_2 console's left edge at -16.1, computed as half its
# 0.86 m width over its centre radius.  oh_2 is a BOX, not an arc, so its NEAR
# corner sits at a smaller radius and therefore a much larger angle -- measured
# over its actual vertices, oh_2 reaches -18.74, and tier 1's C3 louvre/door
# kit on it reaches -17.62.  The other side is OTA, measured at -24.14.
#
# So the free ceiling slot here is -24.14..-18.74: 5.40 deg, which at r 2.596
# is 245 mm.  A 0.32 m panel needs 7.1 deg.  It does not fit, and at 0.32 it
# would have interpenetrated oh_2 by 1.9 deg -- the plan's own 0.1 deg
# "they nest; verify visually" caveat, resolved by the verification.
#
# Narrowed to 0.19 x 0.22 and centred at -21.4: -23.50..-19.30, leaving 0.64
# deg to OTA and 0.56 to oh_2.  That is at the plan's own 0.5-1.0 deg floor
# (7.9) and it is why C1 is 53 x 44 px rather than the tabled 87 x 43: the
# ceiling is the one surface plan 7.3 would rather under-fill than over-fill,
# so the panel shrinks instead of the gutters closing.
C1_ANG, C1_RF, C1_DROP, C1_RAKE = -21.4, 0.88, 0.46, 60.0
C1_W, C1_H = 0.190, 0.220

# C2 -- plan says ceiling +13.0, r_frac 0.86, drop 0.44, rake 58, 0.28 x 0.20.
# Same correction: oh_3 measures +15.53 at its near corner, not the tabled
# +18.5, so a 0.28 m panel at +13 overlaps it by 1.45 deg in ANGLE.  Here the
# fix is free, because oh_3 hangs at r 2.172..2.451 and this panel does not
# have to share that radius: pushing r_frac 0.86 -> 0.89 puts C2's nearest
# vertex at r 2.556, clearing oh_3 by 105 mm with the angles left alone.
# Further out is also smaller on screen, which is the direction plan 7.3 wants.
C2_ANG, C2_RF, C2_DROP, C2_RAKE = 13.0, 0.89, 0.44, 58.0
C2_W, C2_H = 0.280, 0.200


# =========================================================== frame helpers
def _rake(P):
    """The dash face's rake, by `slots.dash`'s own definition."""
    r_near, r_far = P["radius"] - P["dash_run"], P["radius"] - 0.05
    return math.atan2(P["dash_top_z"] - P["dash_near_z"], r_far - r_near)


def _cf(P, made, name, ang, r_frac, drop, rake_deg):
    """A RAKED ceiling frame.

    `slots.ceiling` returns euler (pi, 0, -a), which points local +Z straight
    at the floor -- MERGE_NOTES measures the pilot's ray hitting such a panel
    at 73.1 deg off-normal, i.e. nearly edge-on.  Substituting (pi - rake) for
    the X term tilts the working face toward the pilot; 55-65 deg is the band
    both MQB and DNSM independently landed on.  Measured off-normal here:
    C1 19.5 deg, C2 20.8 deg.
    """
    a = math.radians(ang)
    r = P["radius"] * r_frac
    z = P["ceiling"] - drop
    loc = Vector((r * math.sin(a), r * math.cos(a), z))
    e = kit.frame_empty(name, loc, (math.pi - math.radians(rake_deg), 0.0, -a))
    made.append(e)
    return e


def _rf(P, made, name, ang, z, lift):
    """A placement frame on the dash COAMING RISER, at the far edge of the
    dash face.  `slots_ext.wallband` gives exactly the frame a lamp clamped to
    a horizontal coaming lip wants: +Y up, +Z horizontally at the pilot."""
    loc, eul = slots_ext.wallband(P, ang, z, lift=lift)
    e = kit.frame_empty(name, loc, eul)
    made.append(e)
    return e


def _poly(name, pts, z, m, thick=0.0007):
    """A flat painted silhouette: one n-gon, given as panel-local (x, y)."""
    n = len(pts)
    verts = [(x, y, z) for x, y in pts] + [(x, y, z + thick) for x, y in pts]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))
    return shell.mesh_from(name, verts, faces, m)


def _helix(a, b, turns, radius, n=56, taper=0.16):
    """A coiled-cord polyline from `a` to `b`, tapering to the axis at both
    ends so it meets its terminations cleanly."""
    a, b = Vector(a), Vector(b)
    axis = b - a
    L = axis.length
    t_hat = axis / L
    ref = Vector((0, 0, 1)) if abs(t_hat.z) < 0.9 else Vector((1, 0, 0))
    u = (ref - t_hat * ref.dot(t_hat)).normalized()
    v = t_hat.cross(u)
    pts = []
    for i in range(n):
        s = i / (n - 1.0)
        env = min(1.0, s / taper, (1.0 - s) / taper)
        th = 2 * math.pi * turns * s
        pts.append(tuple(a + axis * s
                         + (u * math.cos(th) + v * math.sin(th))
                         * (radius * env)))
    return pts


# ============================================ 15. D5 COAMING MAP LAMPS x2
#  Bezier control net for the gooseneck, in the riser frame:
#  +X right along the coaming, +Y up, +Z horizontally toward the pilot.
#  `lx` is the LATERAL reach, and it is not decoration: the pilot's eye looks
#  straight down +Z, so an arch that only bends forward projects to a vertical
#  post with a blob on top -- the first build did exactly that.  The bend has
#  to have a sideways component for the S-curve to exist in screen space.
#  The end tangent lands ~57 deg below horizontal so the shade is seen from
#  behind and above, throwing light down onto the dash, rather than shining
#  its open mouth into the camera.
def _d5_bez(lx):
    return ((0.000, 0.000, 0.022), (0.15 * lx, 0.100, 0.024),
            (0.85 * lx, 0.235, 0.128), (lx, 0.130, 0.195))


def _bez(ctrl, n):
    p0, p1, p2, p3 = (Vector(c) for c in ctrl)
    out = []
    for i in range(n):
        t = i / (n - 1.0)
        u = 1.0 - t
        out.append(p0 * (u ** 3) + p1 * (3 * u * u * t)
                   + p2 * (3 * u * t * t) + p3 * (t ** 3))
    return out


def _d5(P, made, tag, ang, lit, lx):
    """A brass gooseneck map lamp clipped to the dash binnacle riser.

    Plan section 2/D5: "the only lit dressing lamps that matter -- they
    MOTIVATE the existing warm pool on the dash face, which currently comes
    from an unexplained area light".  One lit, one dark (the 1-in-5 rule at
    its most literal).  D5's perforated bulb guard is the same `kit.cage` the
    shell lamp cone uses in tier 1's C3.
    """
    out = []
    br, brd = kit.mat("brass"), kit.mat("brass_dk")
    rk = _rake(P)
    f = _rf(P, made, f"dr_d5{tag}_f", ang, D5_Z, D5_LIFT)

    # ---- saddle clamp straddling the coaming edge.  Rotating a box by
    # (rake - pi/2) about local X puts its own +Z on the dash normal, so the
    # clamp lies ON the dash face instead of hovering over the edge.
    cr = rk - math.pi / 2
    dn = Vector((0.0, math.cos(rk), math.sin(rk)))          # dash normal
    ds = Vector((0.0, -math.sin(rk), math.cos(rk)))         # down-slope
    seat = ds * 0.020 + dn * 0.0068
    out.append(kit.box(f"dr_d5{tag}_clamp", tuple(seat), (0.032, 0.046, 0.013),
                       br, rot=(cr, 0, 0), bevel=0.0016))
    seat2 = ds * 0.020 + dn * 0.0148
    out.append(kit.box(f"dr_d5{tag}_pad", tuple(seat2), (0.024, 0.030, 0.004),
                       kit.mat("rubber"), rot=(cr, 0, 0)))
    #  the back jaw hooks down behind the riser -- 4 px, but it is why the
    #  clamp reads as clamped rather than glued
    out.append(kit.box(f"dr_d5{tag}_jaw", (0.0, -0.030, -0.012),
                       (0.026, 0.048, 0.010), brd, bevel=0.0010))
    for i, sx in enumerate((-1, 1)):
        p = seat + Vector((sx * 0.019, 0.0, 0.0))
        out.append(kit.cyl(f"dr_d5{tag}_thumb_{i}", tuple(p), 0.0070, 0.0055,
                           br, rot=(0, math.pi / 2, 0), verts=10,
                           smooth=False))
    out.append(kit.cyl(f"dr_d5{tag}_knuck", tuple(dn * 0.020), 0.0085, 0.012,
                       br, verts=14, rot=(cr, 0, 0)))

    # ---- ribbed flexible gooseneck: one sweep, radii alternating, which is
    # a great deal cheaper than 30 stacked rings and reads the same at 40 px.
    path = _bez(_d5_bez(lx), 30)
    radii = [0.0052 if (i % 2) else 0.0066 for i in range(len(path))]
    out.append(kit.sweep(f"dr_d5{tag}_neck", path, 0.006, brd, sections=8,
                         radii=radii, smooth=False))

    # ---- head: focus ring, shade, reflector, guard cage.  Its own nested
    # frame, aimed along the curve's end tangent (~36 deg below horizontal).
    tip = path[-1]
    d = (path[-1] - path[-2]).normalized()
    #  euler (rx, 0, rz) whose local +Z is exactly `d`
    rx = math.acos(max(-1.0, min(1.0, d.z)))
    rz = math.atan2(d.x, -d.y) if abs(d.x) + abs(d.y) > 1e-9 else 0.0
    hf = kit.frame_empty(f"dr_d5{tag}_hf", tuple(tip), (rx, 0.0, rz),
                         parent=f)
    made.append(hf)
    hd = [kit.cyl(f"dr_d5{tag}_collar", (0, 0, 0.004), 0.0098, 0.014, br,
                  verts=14, bevel=0.0008)]
    hd.append(kit.cyl(f"dr_d5{tag}_focus", (0, 0, 0.017), 0.0142, 0.011, br,
                      verts=14, smooth=False, bevel=0.0008))
    hd.append(kit.revolve(f"dr_d5{tag}_shade",
                          [(0.0118, 0.022), (0.0146, 0.029), (0.0244, 0.052),
                           (0.0272, 0.059)], br, verts=24, cap=False))
    #  the unlit lamp gets a DARK reflector.  Dressing has no local lights, so
    #  a `paper` reflector catches the shell key and renders about as bright as
    #  the lit lamp's mouth -- which loses the entire one-lit-one-dark point.
    hd.append(kit.cone(f"dr_d5{tag}_refl", (0, 0, 0.040), 0.0108, 0.0244,
                       0.030, kit.mat("paper") if lit else kit.mat("paint"),
                       verts=22))
    if lit:
        #  ONE face.  A lens front IS one face; as a solid block three of
        #  these ate 86% of the whole set's emissive budget in tier 2.
        hd.append(kit.disc(f"dr_d5{tag}_lit", (0, 0, 0.0548), 0.0186,
                           kit.lamp_mat("amber", True), verts=20))
    else:
        hd.append(kit.sphere(f"dr_d5{tag}_bulb", (0, 0, 0.040), 0.0112,
                             kit.mat("case"), seg=14, ring=9))
    hd += kit.cage(f"dr_d5{tag}_guard", (0, 0, 0.059), 0.0268, -0.019,
                   wires=5, ring_r=0.0125)
    _put(hf, hd, out)

    # ---- coiled cloth-braided cord, into a rubber grommet in the dash face
    grom = ds * 0.070 + dn * 0.002
    coil = _helix(tuple(Vector(tip) + Vector((-0.30 * lx, -0.016, -0.014))),
                  tuple(grom + dn * 0.014), turns=4.0, radius=0.0115, n=60)
    out.append(kit.sweep(f"dr_d5{tag}_cord", coil, 0.0034, kit.mat("braid"),
                         sections=6))
    out.append(kit.cyl(f"dr_d5{tag}_grom", tuple(grom + dn * 0.0025), 0.0105,
                       0.005, kit.mat("rubber"), rot=(cr, 0, 0), verts=14))
    out.append(kit.tube(f"dr_d5{tag}_gring", tuple(grom + dn * 0.0055), 0.0118,
                        0.0098, 0.0022, br, rot=(cr, 0, 0), verts=18))
    kit.parent_to(out, f)
    made.extend(out)


# =================================== 16. F3 CHART POCKET & CLIPBOARD
def _f3(P, made):
    """The human on board.  No instruments at all -- this is the prop that
    stops the fascia reading as an unbroken grid of panels (plan section 2/F3),
    so it is deliberately the only fascia panel with no dial, no lamp and no
    switch on it: a brass-lipped pocket of rolled charts and a clipboard with a
    half-filled checklist and a pencil on a string.
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")
    hw, hh = F3_W / 2, F3_H / 2
    z0, z1 = F3_Z - hh, F3_Z + hh
    r_back = _fascia_r(P) + 0.002
    face_lift = 0.018
    r_face = _fascia_r(P) - face_lift
    half_deg = math.degrees(hw / r_face)
    a0, a1 = F3_A - half_deg, F3_A + half_deg

    out.append(_cyl_band("dr_f3_back", a0, a1, r_back, 0.020, z0, z1, _grey()))
    st = kit.mat("steel")
    for k, (zz0, zz1) in enumerate(((z0, z0 + 0.011), (z1 - 0.011, z1))):
        out.append(_cyl_band(f"dr_f3_rail_{k}", a0, a1, r_back - 0.020, 0.013,
                             zz0, zz1, st))
    out.append(_cyl_band("dr_f3_bead", a0, a1, r_back - 0.028, 0.005,
                         z1 - 0.007, z1 - 0.003, br))
    for k, aa in enumerate((a0, a1)):
        a = math.radians(aa)
        rr = r_face - 0.007
        out.append(kit.box(f"dr_f3_cheek_{k}",
                           (rr * math.sin(a), rr * math.cos(a), F3_Z),
                           (0.010, 0.013, F3_H), st, rot=(0, 0, -a),
                           bevel=0.0016))
    for k, sx in enumerate((-1, 1)):
        out += _rivet_arc(P, f"dr_f3_riv_{k}",
                          _fascia_pts(P, F3_A, F3_Z, sx * (hw - 0.007),
                                      -hh + 0.022, hh - 0.022, 9,
                                      face_lift + 0.014))

    # ---- the chart pocket: a front plate leaning out at 13 deg on two cast
    # gussets, with a brass lip along its mouth.
    PX = -0.092
    f = _ff(P, made, "dr_f3_pkf", F3_A, F3_Z, PX, -0.052, face_lift)
    tilt = 0.230
    pk = [kit.box("dr_f3_pkplate", (0.0, 0.0, 0.030), (0.168, 0.118, 0.008),
                  _dark(), rot=(tilt, 0, 0), bevel=0.0020)]
    ph = 0.059
    lipy = ph * math.cos(tilt)
    lipz = 0.030 + ph * math.sin(tilt)
    pk.append(kit.box("dr_f3_pklip", (0.0, lipy, lipz),
                      (0.176, 0.014, 0.011), br, rot=(tilt, 0, 0),
                      bevel=0.0018))
    boty = -ph * math.cos(tilt)
    botz = 0.030 - ph * math.sin(tilt)
    for i, sx in enumerate((-1, 1)):
        gx0, gx1 = sx * 0.084 - 0.0028, sx * 0.084 + 0.0028
        prof = [(0.0, 0.002), (boty, botz), (lipy, lipz), (0.0, 0.002)]
        vs, fs = [], []
        for gx in (gx0, gx1):
            for (yy, zz) in prof[:3]:
                vs.append((gx, yy, zz))
        fs.append((2, 1, 0))
        fs.append((3, 4, 5))
        for k in range(3):
            k2 = (k + 1) % 3
            fs.append((k, k2, k2 + 3, k + 3))
        pk.append(shell.mesh_from(f"dr_f3_pkgus_{i}", vs, fs,
                                  kit.mat("steel")))
    #  The plate leans 13 deg, so a fitting at plate-parameter `u` is NOT at
    #  panel (0, u, 0.034): the first build pinned its rivets to a flat z and
    #  left them floating 12 mm off the plate.  `_on` returns the point on the
    #  plate's front face at `u`, `d` proud of it.
    def _on(u, d):
        return (u * math.cos(tilt) - 0.004 * math.sin(tilt),
                0.030 + u * math.sin(tilt) + (0.004 + d) * math.cos(tilt))
    ry, rz = _on(-0.046, 0.0004)
    pk += kit.rivet_row("dr_f3_pkrv", (-0.074, ry, rz), (0.074, ry, rz), 7,
                        r=0.0028)
    #  a reinforcing band and a proper label, or the pocket front is just a
    #  black rectangle with three tubes over it
    by, bz = _on(0.018, 0.0020)
    pk.append(kit.box("dr_f3_pkbnd", (0.0, by, bz), (0.168, 0.010, 0.0040),
                      br, rot=(tilt, 0, 0), bevel=0.0008))
    ly, lz = _on(-0.024, 0.0015)
    pk.append(kit.box("dr_f3_pkhold", (-0.046, ly, lz),
                      (0.062, 0.024, 0.0030), kit.mat("paper"),
                      rot=(tilt, 0, 0)))
    pk.append(kit.text("dr_f3_pktx", "CHARTS", 0.0100, ink,
                       (-0.046, ly, lz + 0.0018)))
    pk.append(kit.text("dr_f3_pktx2", "SECT 1-6", 0.0082, kit.mat("paper"),
                       (0.048, ly, lz + 0.0006)))
    _put(f, pk, out)

    #  Three rolled charts at different heights and leans (plan 5.3: one float
    #  ball higher than the others -- perfect symmetry is the amateur tell).
    #  They LEAN WITH THE PLATE (rot_x = pi/2 + tilt), which is both what a
    #  chart resting in a pocket does and the only way to keep them BEHIND the
    #  front plate over its whole height: the plate is a wedge, shallow at the
    #  bottom, so charts held vertical punch straight through its lower half --
    #  the first build had them hanging out below the pocket floor.
    #  Three different papers, so the pocket is not one block of white.
    chart_m = (kit.mat("paper"), kit.mat("ivory"), kit.mat("slate"))
    for i, (cx, cy, lean, ln) in enumerate(((-0.054, 0.030, -6.0, 0.185),
                                            (-0.004, 0.046, 3.5, 0.196),
                                            (0.046, 0.016, 9.0, 0.170))):
        f = _ff(P, made, f"dr_f3_chf_{i}", F3_A, F3_Z, PX + cx, -0.052 + cy,
                face_lift + 0.013)
        lr = math.radians(lean)
        ax = math.pi / 2 + tilt
        ch = [kit.cyl(f"dr_f3_ch_{i}", (0, 0, 0), 0.0112, ln,
                      chart_m[i], rot=(ax, 0, lr), verts=16)]
        #  printed edge bands, spaced along the roll's own axis
        d = Vector((math.sin(lr) * math.cos(tilt), -math.cos(lr) *
                    math.cos(tilt), -math.sin(tilt)))
        for j, (byy, bm) in enumerate(((-0.052, ink), (-0.070, br),
                                       (0.034, ink))):
            ch.append(kit.cyl(f"dr_f3_chb_{i}_{j}", tuple(d * byy), 0.0118,
                              0.0050, bm, rot=(ax, 0, lr), verts=16,
                              smooth=False))
        ch.append(kit.disc(f"dr_f3_che_{i}", tuple(d * (-ln / 2)), 0.0110,
                           kit.mat("ink"), rot=(ax, 0, lr), verts=16))
        _put(f, ch, out)

    # ---- the clipboard, on a brass hook, with a pencil on a string
    CX = 0.096
    cbf = _ff(P, made, "dr_f3_cbf", F3_A, F3_Z, CX, -0.006, face_lift)
    f = cbf
    hk = [kit.sweep("dr_f3_hook",
                    [(0.0, 0.098, 0.004), (0.0, 0.098, 0.020),
                     (0.0, 0.089, 0.028), (0.0, 0.079, 0.022),
                     (0.0, 0.079, 0.012)], 0.0032, br, sections=8)]
    hk.append(kit.box("dr_f3_hookpl", (0.0, 0.100, 0.0026),
                      (0.026, 0.020, 0.0052), br, bevel=0.0008))
    _put(f, hk, out)

    lean = math.radians(3.4)
    f = kit.frame_empty("dr_f3_cbr", (0, 0, 0), (0.055, 0.0, lean),
                        parent=cbf)
    made.append(f)
    cb = [kit.box("dr_f3_cbboard", (0.0, -0.006, 0.020),
                  (0.118, 0.152, 0.0062), kit.mat("case"), bevel=0.0018)]
    cb.append(kit.box("dr_f3_cbpaper", (0.0, -0.012, 0.0245),
                      (0.102, 0.130, 0.0022), kit.mat("paper")))
    #  a half-filled checklist: seven ruled lines, four of them ticked
    for j in range(7):
        yy = 0.036 - j * 0.019
        cb.append(kit.box(f"dr_f3_cbrule_{j}", (0.006, yy, 0.0258),
                          (0.070, 0.0016, 0.0009), ink))
        cb.append(kit.box(f"dr_f3_cbbox_{j}", (-0.040, yy, 0.0258),
                          (0.0090, 0.0090, 0.0008), ink))
        if j in (0, 1, 3, 4):
            cb.append(kit.box(f"dr_f3_cbtick_{j}", (-0.040, yy, 0.0264),
                              (0.0110, 0.0022, 0.0008), ink,
                              rot=(0, 0, math.radians(38))))
    cb.append(kit.text("dr_f3_cbhead", "PRE-BURN", 0.0098, ink,
                       (0.0, 0.058, 0.0258)))
    cb.append(kit.box("dr_f3_cbclip", (0.0, 0.062, 0.0250),
                      (0.056, 0.020, 0.0080), br, bevel=0.0016))
    cb.append(kit.cyl("dr_f3_cbcam", (0.0, 0.072, 0.0290), 0.0060, 0.030, br,
                      rot=(0, math.pi / 2, 0), verts=12))
    #  pencil on a string
    cb.append(kit.sweep("dr_f3_cbstr",
                        [(0.024, 0.062, 0.030), (0.044, 0.030, 0.030),
                         (0.052, -0.010, 0.029), (0.050, -0.050, 0.028)],
                        0.0013, kit.mat("braid"), sections=6))
    cb.append(kit.cyl("dr_f3_cbpen", (0.050, -0.082, 0.028), 0.0048, 0.070,
                      kit.mat("wood"), rot=(math.pi / 2, 0, 0.10), verts=8,
                      smooth=False))
    cb.append(kit.cone("dr_f3_cbpent", (0.0535, -0.120, 0.028), 0.0048,
                       0.0008, 0.012, kit.mat("wood"),
                       rot=(math.pi / 2, 0, 0.10), verts=8))
    _put(f, cb, out)

    f = _ff(P, made, "dr_f3_ttf", F3_A, F3_Z, 0.0, hh - 0.019, face_lift)
    _put(f, kit.stencil("dr_f3_tt", "CHART  STOWAGE", (0, 0, 0), 0.0110), out)
    f = _ff(P, made, "dr_f3_ftf", F3_A, F3_Z, -0.118, -hh + 0.014, face_lift)
    _put(f, kit.stencil("dr_f3_ft", "FRAME 12", (0, 0, 0), 0.0090, worn=True),
         out)
    made.extend(out)


# ================================= 17. F6 FIRE BOTTLE & AXE BRACKET
def _f6(P, made):
    """Fire suppression.  Plan section 2/F6: "reads instantly as 'ship' from
    any distance and needs no legibility".  The bottle body spends the third
    and last of the whole dressing set's rationed unlit reds.
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")
    hw, hh = F6_W / 2, F6_H / 2
    z0, z1 = F6_Z - hh, F6_Z + hh
    r_back = _fascia_r(P) + 0.002
    face_lift = 0.016
    r_face = _fascia_r(P) - face_lift
    half_deg = math.degrees(hw / r_face)
    a0, a1 = F6_A - half_deg, F6_A + half_deg

    out.append(_cyl_band("dr_f6_back", a0, a1, r_back, 0.018, z0, z1, _grey()))
    st = kit.mat("steel")
    for k, (zz0, zz1) in enumerate(((z0, z0 + 0.010), (z1 - 0.010, z1))):
        out.append(_cyl_band(f"dr_f6_rail_{k}", a0, a1, r_back - 0.018, 0.012,
                             zz0, zz1, st))
    for k, sx in enumerate((-1, 1)):
        out += _rivet_arc(P, f"dr_f6_riv_{k}",
                          _fascia_pts(P, F6_A, F6_Z, sx * (hw - 0.008),
                                      -hh + 0.020, hh - 0.020, 8,
                                      face_lift + 0.012))

    # ---- the axe bracket, EMPTY, over a painted silhouette of the axe.
    #  A shadow board paints the tool's outline DARK, not pale: the first
    #  build used `paper` and produced a bright white blob that read as the
    #  loudest thing on the panel.  `_dark()` also keeps it out of the
    #  section 5.4 value budget.
    f = _ff(P, made, "dr_f6_axf", F6_A, F6_Z, 0.0, 0.132, face_lift)
    ax = [_poly("dr_f6_axsil",
                [(-0.058, -0.0045), (0.018, 0.0035), (0.024, 0.014),
                 (0.038, 0.020), (0.050, 0.011), (0.048, -0.008),
                 (0.034, -0.021), (0.020, -0.017), (0.016, -0.0085),
                 (-0.058, -0.0165)],
                0.0010, kit.mat("paint"))]
    for i, sx in enumerate((-1, 1)):
        ax.append(kit.box(f"dr_f6_axbk_{i}", (sx * 0.050, -0.010, 0.007),
                          (0.016, 0.022, 0.014), br, bevel=0.0016))
        ax.append(kit.sweep(f"dr_f6_axhk_{i}",
                            [(sx * 0.050, -0.020, 0.012),
                             (sx * 0.050, -0.029, 0.018),
                             (sx * 0.042, -0.034, 0.017),
                             (sx * 0.035, -0.029, 0.013)],
                            0.0030, br, sections=8))
    ax.append(kit.text("dr_f6_axtx", "AXE", 0.0095, kit.mat("paper"),
                       (0.0, -0.044, 0.0012)))
    _put(f, ax, out)

    # ---- the bottle, in a quick-release strap bracket
    BY = -0.082
    f = _ff(P, made, "dr_f6_btf", F6_A, F6_Z, 0.0, BY, face_lift)
    R = 0.0400
    body = [(0.0, -0.088), (R * 0.62, -0.092), (R * 0.96, -0.080),
            (R, -0.062), (R, 0.052), (R * 0.94, 0.072),
            (R * 0.62, 0.090), (R * 0.30, 0.098), (R * 0.22, 0.104)]
    bt = [kit.revolve("dr_f6_body", body, kit.mat("red_paint"),
                      center=(0.0, 0.0, 0.052), rot=(-math.pi / 2, 0, 0),
                      verts=26)]
    #  a brass band and a big stencil break the red up so it does not read as
    #  one saturated slab -- red is the heroes' colour, not dressing's.
    bt.append(kit.cyl("dr_f6_bband", (0.0, 0.016, 0.052), R * 1.012, 0.016,
                      br, rot=(math.pi / 2, 0, 0), verts=26))
    bt.append(kit.text("dr_f6_blbl", "CO2", 0.0165, kit.mat("paper"),
                       (0.0, -0.020, 0.052 + R * 0.99)))
    bt.append(kit.text("dr_f6_blbl2", "5 KG", 0.0105, kit.mat("paper"),
                       (0.0, -0.040, 0.052 + R * 0.99)))
    #  neck, valve, trigger, pressure gauge, lead wire seal
    bt.append(kit.cyl("dr_f6_neck", (0.0, 0.110, 0.052), 0.0130, 0.024, br,
                      rot=(math.pi / 2, 0, 0), verts=16))
    bt.append(kit.box("dr_f6_valve", (0.0, 0.132, 0.052),
                      (0.030, 0.024, 0.030), br, bevel=0.0020))
    bt.append(kit.cyl("dr_f6_trig", (0.0, 0.146, 0.052), 0.0075, 0.030, br,
                      rot=(0, math.pi / 2, 0), verts=10))
    bt.append(kit.sweep("dr_f6_seal",
                        [(0.014, 0.140, 0.056), (0.024, 0.132, 0.050),
                         (0.020, 0.120, 0.044)], 0.0012,
                        kit.mat("brass_dk"), sections=6))
    bt.append(kit.cyl("dr_f6_sealtag", (0.020, 0.118, 0.043), 0.0048, 0.0026,
                      kit.mat("steel"), rot=(0, math.pi / 2, 0), verts=10))
    #  discharge horn on a short hose, tucked against the bottle's flank so it
    #  does not read as a shadow blob beside a red cylinder
    bt.append(kit.sweep("dr_f6_hose",
                        [(0.016, 0.126, 0.062), (0.034, 0.104, 0.044),
                         (0.041, 0.062, 0.030), (0.040, 0.026, 0.026)],
                        0.0046, kit.mat("rubber"), sections=8))
    bt.append(kit.cone("dr_f6_horn", (0.040, 0.004, 0.026), 0.0052, 0.0110,
                       0.026, kit.mat("steel"), rot=(math.pi / 2, 0, -0.06),
                       verts=14))
    #  capillary from the valve out to the pressure gauge, so the gauge is on
    #  the bottle rather than floating beside it
    bt.append(kit.sweep("dr_f6_cap",
                        [(-0.014, 0.132, 0.052), (-0.024, 0.132, 0.058),
                         (-0.028, 0.130, 0.064)], 0.0022, br, sections=6))
    _put(f, bt, out)

    f = _ff(P, made, "dr_f6_gf", F6_A, F6_Z, -0.028, BY + 0.130,
            face_lift + 0.036)
    _put(f, kit.gauge("dr_f6_g", (0, 0, 0), r=0.0185, ticks=5,
                      redline=(52, 118), needle_deg=-24.0, sweep_deg=210.0,
                      depth=0.010, bezel_screws=0, label=None), out)

    #  straps: two brass bands that genuinely WRAP the bottle, on cast feet.
    #  The first build used straight bars across the front, which read as
    #  planks nailed over a bottle rather than as a quick-release bracket.
    for i, sy in enumerate((-0.050, 0.030)):
        f = _ff(P, made, f"dr_f6_stf_{i}", F6_A, F6_Z, 0.0, BY + sy,
                face_lift)
        stp = [kit.tube(f"dr_f6_st_{i}", (0.0, 0.0, 0.052), R + 0.0055, R,
                        0.020, br, rot=(math.pi / 2, 0, 0), verts=28)]
        for j, sx in enumerate((-1, 1)):
            stp.append(kit.box(f"dr_f6_stf_{i}_{j}",
                               (sx * (R + 0.011), 0.0, 0.028),
                               (0.020, 0.020, 0.056), kit.mat("steel"),
                               bevel=0.0014))
            stp += kit.hexbolt(f"dr_f6_stb_{i}_{j}",
                               (sx * (R + 0.011), 0.0, 0.056), 0.0042, 0.0038)
        stp.append(kit.box(f"dr_f6_stcam_{i}", (0.0, -0.006, 0.052 + R),
                           (0.024, 0.010, 0.011), br,
                           rot=(0, math.radians(-30), 0), bevel=0.0010))
        _put(f, stp, out)

    f = _ff(P, made, "dr_f6_ttf", F6_A, F6_Z, 0.0, -hh + 0.018, face_lift)
    _put(f, kit.stencil("dr_f6_tt", "FIRE", (0, 0, 0), 0.0155), out)
    made.extend(out)


# ============================ 18. D4 RADIATION MONITOR & DOSIMETER CLIP
def _d4(P, made):
    """Radiation safety, at the extreme right of the dash.  87 x 49 px and
    heavily foreshortened at +42.5 deg, so it carries exactly four features:
    one round meter, one dark click lens, one rotary, one dosimeter pencil.
    Everything else is cast box, bezel and rivets.
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")
    hw, hh = D4_W / 2, D4_H / 2
    t0, t1 = D4_T - hh / FACE_LEN, D4_T + hh / FACE_LEN
    half_deg = math.degrees(hw / _dash_r(P, D4_T))
    a0, a1 = D4_A - half_deg, D4_A + half_deg
    lift = 0.026

    #  The face is CONSOLE GREY, not brass.  The first build made the whole
    #  0.20 x 0.24 face a brass slab, which at +42.5 deg is a bright gold
    #  rectangle in the corner of frame -- tier 2 had already cut brass from
    #  22% to 9% of dressing screen area for exactly this reason.  Brass here
    #  is now two 4 mm beads and the gauge bezel.
    out.append(_dash_band(P, "dr_d4_case", a0, a1, t0, t1, 0.002, lift,
                          _dark(), bevel=0.0035))
    out.append(_dash_band(P, "dr_d4_face", a0 + 0.16, a1 - 0.16,
                          t0 + 0.014, t1 - 0.014, lift, lift + 0.008,
                          _grey(), bevel=0.0022))
    for k, (tt0, tt1) in enumerate(((t0 + 0.014, t0 + 0.021),
                                    (t1 - 0.021, t1 - 0.014))):
        out.append(_dash_band(P, f"dr_d4_bead_{k}", a0 + 0.16, a1 - 0.16,
                              tt0, tt1, lift + 0.008, lift + 0.011, br))
    for k, aa in enumerate((a0 + 0.25, a1 - 0.25)):
        pts = [slots.dash(P, aa, t0 + 0.028 + (t1 - t0 - 0.056) * i / 5.0,
                          lift=lift + 0.008)[0] for i in range(6)]
        out += _rivet_arc(P, f"dr_d4_riv_{k}", pts, r=0.0030)

    f = _df(P, made, "dr_d4_gf", D4_A, D4_T, -0.048, 0.022, lift)
    _put(f, kit.gauge("dr_d4_g", (0, 0, 0), r=0.0500, ticks=7,
                      redline=(74, 126), needle_deg=-64.0, sweep_deg=230.0,
                      label="mR/HR", depth=0.016, bezel_screws=3), out)

    f = _df(P, made, "dr_d4_lf", D4_A, D4_T, 0.058, 0.064, lift)
    #  a click-rate lens, UNLIT: dressing "screens" are ground glass, never
    #  phosphor (plan 5.2).  `_opal` is tier 2's neutral ground-glass grey.
    lc = kit.lampcell("dr_d4_l", (0, 0, 0), w=0.030, h=0.030, lit=False,
                      kind="amber", depth=0.010, frame=True, round_lens=True)
    lc[0].data.materials.clear()
    lc[0].data.materials.append(_dark())
    lc[1].data.materials.clear()
    lc[1].data.materials.append(_opal())
    _put(f, lc, out)
    f = _df(P, made, "dr_d4_ltf", D4_A, D4_T, 0.058, 0.036, lift + 0.004)
    _put(f, kit.stencil("dr_d4_lt", "CLICK", (0, 0, 0), 0.0080, m=ink), out)

    #  the dash rakes 26 deg and this panel is at +42.5, so `t` compresses to
    #  about a fifth on screen: the lower half of the face is a 12 px strip.
    #  Everything is pushed up and out toward the two long edges, and the
    #  three-position legend is one word rather than three.
    f = _df(P, made, "dr_d4_rf", D4_A, D4_T, 0.012, -0.048, lift)
    _put(f, _rotary("dr_d4_r", (0, 0, 0), r=0.0245, positions=3,
                    pointer=-46.0), out)
    f = _df(P, made, "dr_d4_rlf_0", D4_A, D4_T, -0.036, -0.052, lift + 0.002)
    _put(f, kit.stencil("dr_d4_rl_0", "SET  OPER  BATT", (0, 0, 0), 0.0072,
                        m=ink), out)

    #  dosimeter pencil in a spring clip, on a short brass chain
    f = _df(P, made, "dr_d4_df", D4_A, D4_T, 0.064, -0.022, lift)
    dz = [kit.cyl("dr_d4_dpen", (0, 0, 0.014), 0.0072, 0.078,
                  kit.mat("steel"), rot=(math.pi / 2, 0, 0.16), verts=12)]
    dz.append(kit.cyl("dr_d4_dwin", (0, 0.014, 0.014), 0.0076, 0.020,
                      kit.mat("ivory"), rot=(math.pi / 2, 0, 0.16), verts=12,
                      smooth=False))
    dz.append(kit.cyl("dr_d4_dcap", (-0.0062, -0.040, 0.014), 0.0080, 0.012,
                      br, rot=(math.pi / 2, 0, 0.16), verts=12))
    for j, sy in enumerate((-0.020, 0.024)):
        dz.append(kit.box(f"dr_d4_dclip_{j}", (0.0, sy, 0.0055),
                          (0.022, 0.007, 0.011), br, bevel=0.0009))
    dz.append(kit.sweep("dr_d4_dchain",
                        [(0.010, 0.030, 0.016), (0.020, 0.016, 0.010),
                         (0.026, -0.004, 0.006)], 0.0014,
                        kit.mat("brass_dk"), sections=6))
    _put(f, dz, out)

    f = _df(P, made, "dr_d4_npf", D4_A, D4_T, 0.006, 0.090, lift + 0.008)
    _put(f, kit.nameplate("dr_d4_np", "RAD MON", (0, 0, 0), h=0.0180,
                          size=0.0088, sub="TYPE 4"), out)
    made.extend(out)


# ================================== 19. H3 PLACARD & STENCIL SET, PASS 2
def _h3b(P, made):
    """Second stencil pass.  Tier 1's first pass marked the dash kick, two
    ceiling beams and two wall compartments.  This one marks the things tiers
    1-3 have since ADDED and the gaps they left: flow arrows and service
    legends on H2's three conduit runs, two more beam frame numbers, a caution
    triangle in the F5/F6 gutter (which is where a fire placard belongs), and
    inspection stamps on the dash lip.

    Everything is placed in a gutter or on tier-1 structure -- nothing here
    lands on a surface tier 2 or tier 3 owns.
    """
    out = []
    CEIL = P["ceiling"]
    ink = kit.mat("ink")

    #  H2's three runs sit at z 2.125 with tube radii 0.025 / 0.030 / 0.025,
    #  well above the 1.30 m eye, so the only face of them the pilot ever sees
    #  is the UNDERSIDE.  `slots_ext.dome` is the frame that faces down.
    for k, (rr, tr, ang, body) in enumerate(((2.20, 0.025, -21.0, "FWD"),
                                             (2.20, 0.025, 13.0, "FWD"),
                                             (2.42, 0.030, -9.0, "O2  LP"),
                                             (2.42, 0.030, 24.0, "O2  LP"),
                                             (2.70, 0.025, 2.0, "VENT"))):
        loc, eul = slots_ext.dome(P, ang, rr, 2.125 - tr - 0.0015)
        f = kit.frame_empty(f"dr_h3b_cdf_{k}", loc, eul)
        made.append(f)
        o = kit.stencil(f"dr_h3b_cdt_{k}", body, (0.0, 0.012, 0.0), 0.0150,
                        rot=(0.0, 0.0, math.pi / 2), worn=(k == 3))
        o += kit.arrow(f"dr_h3b_cda_{k}", (0.0, -0.018, 0.0), length=0.048,
                       m=kit.mat("paper"),
                       rot_z=math.pi / 2 if k % 2 else -math.pi / 2)
        kit.parent_to(o, f)
        out += o

    #  Two more radial-beam frame numbers, on beams tier 1 left bare.
    #  MEASURED: these land at screen x -7 and x 1608 -- i.e. OFF FRAME, and
    #  they stay off frame at any radius, because the camera sits within
    #  100 mm of the room's axis so a -46 deg bearing projects to x ~10
    #  whatever the distance.  They are kept anyway for the reason plan
    #  section 4 gives about this exact band: it is invisible in the main
    #  plate but it IS the background of MQB's and DNSM's close-ups, and two
    #  text meshes is a cheap price for that.  They are not main-plate content
    #  and are not counted as such.
    for k, (ang, body) in enumerate(((-46, "FR 9"), (58, "FR 18"))):
        loc, eul = slots_ext.dome(P, ang, 2.05, CEIL - 0.0985)
        f = kit.frame_empty(f"dr_h3b_beam_{k}", loc, eul)
        made.append(f)
        o = kit.stencil(f"dr_h3b_beamtx_{k}", body, (0.0, 0.0, 0.0), 0.052,
                        rot=(0.0, 0.0, math.pi / 2), worn=(k == 1))
        kit.parent_to(o, f)
        out += o

    #  fire placard in the F5 / F6 gutter (F5 ends +38.5, F6 starts +40.76)
    loc, eul = slots.fascia(P, 39.62, 0.470, lift=0.006)
    f = kit.frame_empty("dr_h3b_wtf", loc, eul)
    made.append(f)
    o = kit.warn_triangle("dr_h3b_wt", (0.0, 0.0, 0.0), 0.0330)
    o += kit.stencil("dr_h3b_wtx", "NO", (0.0, -0.030, 0.0), 0.0105,
                     m=kit.mat("paper"))
    o += kit.stencil("dr_h3b_wtx2", "WATER", (0.0, -0.043, 0.0), 0.0105,
                     m=kit.mat("paper"))
    kit.parent_to(o, f)
    out += o

    #  inspection stamps on the dash lip's brass nose, at angles no panel owns
    #  and outside the reserved -16..+16 apron (plan 7.9).
    #  `shell.dash_lip` is an arc band from (r 2.345, z 0.792) to (2.300,
    #  0.755): a wedge, not a vertical face, so a wallband-style frame would
    #  bury the stamp inside it.  Its outward normal is 39.4 deg off vertical,
    #  tilted at the pilot -- which is a frame the slot convention can express
    #  as euler (0.688, 0, -a).
    dr_ = P["radius"] - P["dash_run"]
    lip_a = math.atan2(0.045, 0.037)          # normal, off vertical
    n_r, n_z = -math.cos(lip_a), math.sin(lip_a)
    for k, (ang, body) in enumerate(((-30.0, "A7"), (-19.5, "K3"),
                                     (36.5, "A7"))):
        a = math.radians(ang)
        rr = (dr_ + 0.0075) + n_r * 0.004
        zz = (P["dash_near_z"] - 0.0065) + n_z * 0.004
        loc = Vector((rr * math.sin(a), rr * math.cos(a), zz))
        f = kit.frame_empty(f"dr_h3b_isf_{k}", loc,
                            (math.pi / 2 - lip_a, 0.0, -a))
        made.append(f)
        o = kit.inspection_stamp(f"dr_h3b_is_{k}", (0.0, 0.0, 0.0), body,
                                 r=0.0105)
        kit.parent_to(o, f)
        out += o

    #  hull data and frame numbers on the kick.  Tier 1 put NO STEP at -21 and
    #  +17; these fill between and outboard of them.  Plan section 2/H3 asks
    #  for "FRAME 9 / 12 / 15" and section 7.8 caps the kick's whole budget at
    #  lettering, which is exactly what this is.
    kick_rake = math.atan2(0.14, 0.145)
    for k, (ang, body, size, worn) in enumerate((
            (-3.0, "HULL 0x7A   YARD 2149", 0.026, True),
            (-37.0, "FR 9", 0.030, False),
            (32.0, "FR 15", 0.030, True))):
        a = math.radians(ang)
        r, z = 2.372, 0.062
        loc = Vector((r * math.sin(a), r * math.cos(a), z))
        loc += Vector((-math.sin(a) * math.sin(kick_rake) * 0.006,
                       -math.cos(a) * math.sin(kick_rake) * 0.006,
                       math.cos(kick_rake) * 0.006))
        f = kit.frame_empty(f"dr_h3b_kickf_{k}", loc, (kick_rake, 0.0, -a))
        made.append(f)
        o = kit.stencil(f"dr_h3b_kick_{k}", body, (0.0, 0.0, 0.0), size,
                        worn=worn)
        kit.parent_to(o, f)
        out += o

    made.extend(out)


# ================================== 20. C1 OVERHEAD BREAKER PANEL
#  four characters max: `kit.breaker` draws its legend at a fixed 0.0050 m and
#  the array pitch is 0.034, so a five-character legend collides with the next
#  breaker's.
C1_LEGENDS = ("GYRO", "TRIM", "RCS", "NAV", "LGT",
              "O2", "CO2", "H2O", "CRYO", "PUMP",
              "TAPE", "MAIL", "DNS", "LOG", "RLY",
              "BUSA", "BUSB", "TIE", "AUX", "EMER")
#  irregular pulled/pushed heights -- plan 5.3.  Two are half-pulled.
C1_PULL = (0.0, 0.0, 1.0, 0.0, 0.0,
           0.0, 0.45, 0.0, 0.0, 1.0,
           0.0, 0.0, 0.0, 0.0, 0.0,
           0.0, 0.0, 0.85, 0.0, 0.40)


def _c1(P, made):
    """Electrical distribution: 5 x 4 pull-type breakers with brass mushroom
    heads at irregular heights, two guarded masters, a bus selector, on two
    thin brass stalks, raked 60 deg toward the pilot.

    Plan section 7.3 argues against a third large hanging mass overhead, and
    section 6 lists C1/C2 first on the cut list.  Since that was written MQB
    and DNSM were rescaled to 0.70 / 0.78 (MERGE_NOTES) and gave the ceiling
    back real room -- but the argument still governs the SIZE: this panel is
    75 x 54 px, roughly a quarter of MQB's area, and carries no lit lamp at
    all so it cannot compete for attention with the two hero screens.
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")
    st = kit.mat("steel")
    f = _cf(P, made, "dr_c1_f", C1_ANG, C1_RF, C1_DROP, C1_RAKE)
    hw, hh = C1_W / 2, C1_H / 2

    pl = [kit.box("dr_c1_case", (0.0, 0.0, -0.022), (C1_W, C1_H, 0.044),
                  _dark(), bevel=0.0040)]
    pl.append(kit.box("dr_c1_face", (0.0, 0.0, 0.004), (C1_W, C1_H, 0.012),
                      _grey(), bevel=0.0035))
    pl += kit.bez_frame("dr_c1_bez", 0.0, 0.0, C1_W, C1_H, 0.008, 0.017, st,
                        bar=0.0075)
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        pl += kit.screw(f"dr_c1_scr_{i}",
                        (sx * (hw - 0.0075), sy * (hh - 0.0075), 0.016),
                        0.0032)
    pl += kit.rivet_row("dr_c1_rvt", (-hw + 0.016, hh - 0.0035, 0.0165),
                        (hw - 0.016, hh - 0.0035, 0.0165), 7, r=0.0024)
    pl += kit.rivet_row("dr_c1_rvb", (-hw + 0.016, -hh + 0.0035, 0.0165),
                        (hw - 0.016, -hh + 0.0035, 0.0165), 7, r=0.0024)

    #  5 x 4 breaker array, on the pitch a 0.19 m panel actually affords
    for r_ in range(4):
        for c_ in range(5):
            i = r_ * 5 + c_
            x = -0.068 + c_ * 0.034
            y = 0.056 - r_ * 0.032
            pl += kit.breaker(f"dr_c1_bk_{i}", (x, y, 0.010), r=0.0068,
                              pulled=C1_PULL[i], legend=C1_LEGENDS[i])
    #  two guarded masters and the bus selector, along the bottom
    for i, (x, tilt) in enumerate(((-0.062, 22.0), (-0.026, -16.0))):
        pl += kit.toggle(f"dr_c1_ms_{i}", (x, -0.072, 0.010), kind="guarded",
                         pos_deg=tilt, scale=0.74)
    pl.append(kit.text("dr_c1_mstx", "MASTER", 0.0060, ink,
                       (-0.044, -0.092, 0.0115)))
    pl += _rotary("dr_c1_sel", (0.048, -0.070, 0.010), r=0.0165, positions=6,
                  pointer=64.0, legend="BUS")
    pl.append(kit.text("dr_c1_tt", "CIRCUIT BREAKERS", 0.0068, ink,
                       (0.0, hh - 0.013, 0.0115)))
    _put(f, pl, out)

    #  two thin brass stalks, up to the ceiling.  World space: they must not
    #  inherit the panel's 60 deg rake or they would lean with it.
    bpy.context.view_layer.update()
    for i, sx in enumerate((-1, 1)):
        top = f.matrix_world @ Vector((sx * (hw - 0.030), hh - 0.014, -0.030))
        out.append(kit.sweep(f"dr_c1_stalk_{i}",
                             [tuple(top), (top.x, top.y, P["ceiling"] + 0.01)],
                             0.0088, br, sections=8))
        out.append(kit.tube(f"dr_c1_stcol_{i}",
                            (top.x, top.y, top.z + 0.022), 0.0135, 0.0090,
                            0.014, br, verts=14))
        out.append(kit.cyl(f"dr_c1_stpad_{i}",
                           (top.x, top.y, P["ceiling"] - 0.006), 0.0210,
                           0.012, st, verts=16, bevel=0.0012))
    made.extend(out)


# ================================== 21. C2 BEACON RELAY HEAD
def _c2(P, made):
    """Long-range comms relay: a cast housing with a round dial-scale radio
    face behind convex glass, a knurled frequency crank, and two braided
    pigtails running up into the ceiling rib and disappearing.

    Plan 7.6: a DIAL-SCALE radio, not a scope -- an engraved logarithmic
    frequency arc and a hairline cursor.  Plan 5.2: no phosphor anywhere, so
    the pointer lamp is a dark green lens, not a lit one.
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")
    st = kit.mat("steel")
    f = _cf(P, made, "dr_c2_f", C2_ANG, C2_RF, C2_DROP, C2_RAKE)
    hw, hh = C2_W / 2, C2_H / 2

    hs = [kit.box("dr_c2_case", (0.0, 0.0, -0.026), (C2_W, C2_H, 0.052),
                  kit.mat("slate"), bevel=0.0055)]
    hs.append(kit.box("dr_c2_face", (0.0, 0.0, 0.004), (C2_W, C2_H, 0.012),
                      _grey(), bevel=0.0035))
    hs += kit.bez_frame("dr_c2_bez", 0.0, 0.0, C2_W, C2_H, 0.008, 0.016, st,
                        bar=0.0070)
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        hs.append(kit.box(f"dr_c2_ct_{i}",
                          (sx * (hw - 0.011), sy * (hh - 0.011), 0.012),
                          (0.024, 0.024, 0.006), br, bevel=0.0012))
        hs += kit.screw(f"dr_c2_scr_{i}",
                        (sx * (hw - 0.011), sy * (hh - 0.011), 0.015), 0.0030)
    hs += kit.rivet_row("dr_c2_rv", (-hw + 0.026, -hh + 0.0040, 0.0155),
                        (hw - 0.026, -hh + 0.0040, 0.0155), 8, r=0.0026)

    #  the dial: engraved log frequency arc, hairline cursor, dark pointer lamp
    DR = 0.0620
    hs.append(kit.cyl("dr_c2_dcan", (-0.026, 0.006, 0.0), DR * 0.94, 0.020,
                      kit.mat("case"), verts=28, smooth=False))
    hs.append(kit.cyl("dr_c2_dface", (-0.026, 0.006, 0.0110), DR * 0.84,
                      0.0040, kit.mat("ivory"), verts=36, smooth=False))
    for j in range(11):
        #  logarithmic spacing: the whole point of a dial-scale radio face
        fr = 3.0 * (20.0 / 3.0) ** (j / 10.0)
        u = math.log10(fr / 3.0) / math.log10(20.0 / 3.0)
        a = math.radians(-118 + 236.0 * u)
        rr = DR * 0.68
        hs.append(kit.box(f"dr_c2_dtk_{j}",
                          (-0.026 + rr * math.sin(a), 0.006 + rr * math.cos(a),
                           0.0134), (0.0016, DR * (0.20 if j % 2 == 0 else
                                                   0.12), 0.0012), ink,
                          rot=(0, 0, -a)))
        if j % 2 == 0:
            rr2 = DR * 0.46
            hs.append(kit.text(f"dr_c2_dn_{j}", str(int(round(fr))),
                               DR * 0.17, ink,
                               (-0.026 + rr2 * math.sin(a),
                                0.006 + rr2 * math.cos(a), 0.0134)))
    ca = math.radians(-34.0)
    hs.append(kit.box("dr_c2_cursor",
                      (-0.026 + (DR * 0.42) * math.sin(ca),
                       0.006 + (DR * 0.42) * math.cos(ca), 0.0142),
                      (0.0011, DR * 0.86, 0.0016), br, rot=(0, 0, -ca)))
    hs.append(kit.cyl("dr_c2_hub", (-0.026, 0.006, 0.0146), 0.0068, 0.0044,
                      br, verts=16))
    hs += _bezel("dr_c2_d", (-0.026, 0.006, 0.0140), DR, bez_h=0.0080,
                 glassy=True, screws=4)
    hs.append(kit.text("dr_c2_dmc", "MC", DR * 0.15, ink,
                       (-0.026, 0.006 - DR * 0.52, 0.0134)))

    #  pointer lamp: pale green, UNLIT (plan 5.2's 1-in-5 rule and no phosphor)
    lp = kit.lampcell("dr_c2_lp", (0.062, 0.052, 0.010), w=0.024, h=0.024,
                      lit=False, kind="green", depth=0.010, frame=True,
                      round_lens=True)
    lp[0].data.materials.clear()
    lp[0].data.materials.append(_dark())
    hs += lp
    hs.append(kit.text("dr_c2_lptx", "SYNC", 0.0068, ink,
                       (0.062, 0.030, 0.0115)))

    #  knurled frequency crank on the right cheek
    hs.append(kit.cyl("dr_c2_crb", (hw + 0.006, 0.006, -0.012), 0.0110, 0.024,
                      br, rot=(0, math.pi / 2, 0), verts=14))
    hs.append(kit.cyl("dr_c2_crk", (hw + 0.022, 0.006, -0.012), 0.0175, 0.014,
                      br, rot=(0, math.pi / 2, 0), verts=12, smooth=False,
                      bevel=0.0010))
    hs.append(kit.box("dr_c2_crarm", (hw + 0.030, 0.006, -0.028),
                      (0.007, 0.008, 0.034), br, bevel=0.0008))
    hs.append(kit.sphere("dr_c2_crball", (hw + 0.030, 0.006, -0.046), 0.0090,
                         kit.mat("ebonite"), seg=14, ring=9))

    hs.append(kit.text("dr_c2_tt", "BEACON RELAY", 0.0088, ink,
                       (0.0, hh - 0.014, 0.0115)))
    hs += kit.nameplate("dr_c2_np", "TYPE 9", (0.058, -0.062, 0.0110),
                        h=0.0150, size=0.0075, screws=False)
    _put(f, hs, out)

    #  two braided pigtails up into the ceiling rib (shell rib_1 spans
    #  r 2.216..2.301 at z 2.175..2.240) -- built in world space so they do
    #  not inherit the rake.
    bpy.context.view_layer.update()
    a = math.radians(C2_ANG)
    for i, (sx, dr_, da) in enumerate(((-1, -0.150, -2.2), (1, -0.116, 1.2))):
        base = f.matrix_world @ Vector((sx * 0.052, hh - 0.020, -0.040))
        aa = a + math.radians(da)
        rr = 2.301 - 0.010
        top = Vector((rr * math.sin(aa), rr * math.cos(aa), 2.196))
        mid = base.lerp(top, 0.48) + Vector((0.0, 0.020 * sx, 0.020))
        pts = [tuple(base),
               tuple(base + Vector((0.0, 0.006, 0.040))),
               tuple(mid), tuple(top + Vector((0.0, 0.0, -0.055))),
               tuple(top)]
        out.append(kit.sweep(f"dr_c2_pig_{i}", pts, 0.0092,
                             kit.mat("braid"), sections=8))
        out.append(kit.tube(f"dr_c2_pigf_{i}", tuple(base), 0.0135, 0.0092,
                            0.014, br, verts=14))
    #  a single brass stalk carries the weight; the pigtails only look like it
    top = f.matrix_world @ Vector((0.0, hh - 0.026, -0.038))
    out.append(kit.sweep("dr_c2_stalk",
                         [tuple(top), (top.x, top.y, P["ceiling"] + 0.01)],
                         0.0098, br, sections=8))
    out.append(kit.cyl("dr_c2_stpad", (top.x, top.y, P["ceiling"] - 0.006),
                       0.0225, 0.012, st, verts=16, bevel=0.0012))
    made.extend(out)


# ==================================================================== entry
def add_tier4(P, mats):
    """Add tier 4's dressing geometry to the CURRENT scene.

    P    : shell PARAMS (already built)
    mats : {"brass":..., "hull":..., "hull_d":...}  -- the shell's own hero
           materials.  Dressing does NOT use them; `kit.mat()` supplies the
           desaturated set from DRESSING_PLAN.md section 5.1.
    Returns: {"dress": [list of created objects]}
    """
    made = []
    #  lateral reaches differ (-0.052 / -0.058) and they bend the same way,
    #  not mirrored: two identical lamps facing each other is the symmetry
    #  tell plan 5.3 warns about.
    _d5(P, made, "a", D5A_ANG, True, -0.052)     # 15  map lamp, LIT
    _d5(P, made, "b", D5B_ANG, False, -0.058)    # 15  map lamp, dark
    _f3(P, made)                         # 16  chart pocket & clipboard
    _f6(P, made)                         # 17  fire bottle & axe bracket
    _d4(P, made)                         # 18  radiation monitor
    _h3b(P, made)                        # 19  stencil pass 2
    _c1(P, made)                         # 20  overhead breaker panel
    _c2(P, made)                         # 21  beacon relay head

    meshes = [o for o in made if o.type == 'MESH']
    em = kit.emissive_area(meshes)
    print(f"TIER4: {len(meshes)} meshes, {len(made) - len(meshes)} empties; "
          f"emissive area {em:.6f} m2 "
          f"(budget for ALL dressing is 0.0518 m2)")
    return {"dress": made}


if __name__ == "__main__":
    P = dict(shell.PARAMS)
    P["exterior"] = 1
    shell.build(P)
    add_tier4(P, {"brass": bpy.data.materials["brass"],
                  "hull": bpy.data.materials["hull"],
                  "hull_d": bpy.data.materials["hull_d"]})
    bpy.context.scene.render.filepath = os.path.join(HERE, "out",
                                                     "_tier4_only.png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", bpy.context.scene.render.filepath)
