"""
Set-dressing TIER 2 -- "the big empty quadrants, and the FMM/MTA close-up fix".

DRESSING_PLAN.md section 6, tier 2, in the plan's own priority order:

  6. F1  atmosphere plant                -- bottom-left anchor
  7. F5  main bus board                  -- bottom-right anchor, balances F1
  8. H1  caution-advisory annunciator    -- top-centre, frames the reserved band
  9. D1  flight & trim sub-panel         -- sits beside FMM

Items 6, 7 and 9 are placed adjacent to FMM and MTA specifically: MERGE_NOTES
records both close-ups as "floating on flat grey", and plan section 0.2 argues
that pulling those cameras back only helps if there is something to pull back
*to*. This tier is that content.

Contract (DRESSING_BRIEF.md): geometry only. No render, no camera, no scene
settings, NO LIGHTS, no manifest, no glow mask, no hotspots.

    from dressing import tier2
    tier2.add_tier2(P, mats)   ->  {"dress": [objects]}

Curvature note
--------------
The fascia and the hull wall are CYLINDERS and the dash is a raked cone. A flat
0.42 m plate tangent to the fascia has its ends 10 mm nearer the wall than its
centre; a flat 0.72 m plate on the dash, 25 mm. So every *backing* surface here
is built as a real arc band (`_cyl_band` / `_dash_band`) and every *part* gets
its own placement frame at its own angle (`_ff` / `_df` / `_wf`), which is what
keeps rivet rows and toggle banks sitting flat on a curved console.

Emissive note
-------------
Plan section 5.2 caps ALL dressing emissive area at 15% of the eight heroes'
(measured: heroes 0.3455 m2, so the whole dressing set gets 0.0518 m2). Tier 1
spent zero. H1's three lit legend cells are the only significant spend in this
tier and they use a single-quad lit face rather than a solid emissive block --
a lens front IS a single face, and a 0.19 x 0.056 solid block per cell would
have eaten 86% of the whole set's budget on three lamps. See `_lit_face`.
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


# ------------------------------------------------------- tier-2 materials
# Two materials the kit does not carry, both derived with the plan's own
# section 5.1 fallback rule (same hue, S x0.72, V x0.68) and both chosen to
# defend the section 5.4 saturation assertion, which the first tier-2 build
# failed at -25%.
#
#  dr_console  the big backing panels -- half of every tier-2 pixel on screen.
#  dr_opal     an UNLIT annunciator lens.  Plan 5.2 says dressing "screens"
#              are "unlit ground glass" -- which is also what a real legend
#              cell is: an opal lens that takes its colour from the bulb
#              behind it.  `amber_off` is (0.138,0.090,0.030), saturation
#              0.78, and twenty large lenses of it is a lot of orange.
#
# Both are deliberately COOL greys, and that is the whole trick behind passing
# section 5.4 down here.  Six of the shell's seven area lights are warm
# (1.00, 0.85, 0.66); the fascia and dash sit right under the warmest of them.
# A neutral-albedo panel therefore RENDERS at saturation ~0.32 no matter how
# grey its base colour is -- which is why the first attempt at this got
# *worse* when the backings were switched from `hull_l` to a neutral grey.
# Biasing the albedo blue by roughly the illuminant's own red/blue ratio makes
# the rendered pixel neutral, which is what the assertion actually measures and
# what "console, not object" actually looks like.
def _grey():
    m = bpy.data.materials.get("dr_console")
    return m or shell.material("dr_console", (0.052, 0.062, 0.083, 1), 0.14,
                               0.54)


def _opal():
    m = bpy.data.materials.get("dr_opal")
    return m or shell.material("dr_opal", (0.092, 0.103, 0.120, 1), 0.0, 0.62)


def _dark():
    """Same story as `_grey`, for the recessed near-black: kerbs, instrument
    cans and the fuse bay.  Matches `kit.mat("case")` in value; blue-biased so
    it renders neutral under the shell's warm key instead of tan."""
    m = bpy.data.materials.get("dr_recess")
    return m or shell.material("dr_recess", (0.036, 0.042, 0.056, 1), 0.10,
                               0.56)


def _annunciator(name, pos, w, h, legend, lit, kind, depth=0.012,
                 text_size=0.019, frame=True):
    """A legend cell whose UNLIT lens is neutral ground glass and whose lettering
    is drawn here: `kit.lampcell` puts near-black ink on the lens, which is
    invisible on a dark cell.  Pale on dark, dark on lit."""
    objs = kit.lampcell(name, pos, w=w, h=h, legend="", lit=False, kind=kind,
                        depth=depth, frame=frame)
    for o, mm in ((objs[0], _dark()), (objs[1], _opal())):
        o.data.materials.clear()
        o.data.materials.append(mm)
    if lit:
        objs += _lit_face(f"{name}_lf",
                          (pos[0], pos[1], pos[2] + depth * 0.868),
                          w * 0.86, h * 0.55, kind=kind)
    if legend:
        objs.append(kit.text(f"{name}_tx", legend, text_size,
                             kit.mat("ink") if lit else kit.mat("paper"),
                             (pos[0], pos[1], pos[2] + depth * 0.95)))
    return objs


# ------------------------------------------------------------- placements
# F1 -- fascia -39.0, z 0.19..0.71, 0.42 x 0.52 (plan section 3)
F1_A, F1_Z, F1_W, F1_H = -39.0, 0.45, 0.420, 0.520
# F5 -- fascia +34.0, z 0.22..0.68.  The placement table says 0.40 wide but
# section 4 ("too crowded -- flagged risks") explicitly asks for 0.36 first:
# MTA + F4 + F5 + F6 share 26 deg of arc with KVS directly above.  Built at
# 0.36; it does not read thin against KVS, so it stays there and F4/F6 inherit
# 1.5 deg and 2.3 deg of gutter instead of 1.0 and 1.8.
F5_A, F5_Z, F5_W, F5_H = 34.0, 0.45, 0.360, 0.460
# H1 -- wallband -27..+18.  The plan says z 1.96..2.13; tier 1's H2 junction
# boxes bottom out at z 2.126 at -33/+6/+34 deg, so the whole strip drops
# 15 mm to 1.950..2.115 and clears them by 11 mm.  Everything else is as spec.
H1_A0, H1_A1 = -27.0, 18.0
H1_Z0, H1_Z1 = 1.950, 2.115
H1_RAIL = 0.013
# section 7.1: continue the frame rail past the +/-46 deg frame edge so a wider
# plate never reveals a hard stop.  Held clear of tier 1's C-11 / C-14 wall
# stencils (z 1.960..2.061) by running the continuation rails slimmer and lower.
H1_CONT = 52.0
# D1 -- dash, t 0.06..0.86, spanning -33.0 .. -17.0.  Right edge lands at
# -17.0 deg and the RESERVED packet band starts at -16.0: 1.0 deg, about
# 45 mm.  DO NOT WIDEN.  Per plan section 4 D1 gets NO outer brass frame -- it
# is a recess in the dash face, so FMM's brass frame 6 px to its left stays
# unique.
#
# NOT IN THE PLAN, found on the first render: COLUMN 0 STANDS IN THE MIDDLE OF
# D1.  Its axis is at dash -27.0 deg and shell.py itself notes "the dash face
# crosses the columns at z 0.861", so between t 0.29 and t 0.55 the dash face
# is genuinely INSIDE the 0.075 m column -- and tier 1's P3a cast skirt flares
# out to 0.108 m from that axis.  A single -33..-17 panel would bury two
# toggles inside the column and clash with P3a's skirt.
#
# So D1 is built as it would really be built: a narrow OUTRIGGER WING outboard
# of the column and the MAIN BLOCK inboard of it, with the column and its
# skirt passing through the gutter between them.  0.108 m of skirt at r 2.57
# needs 2.63 deg of angular clearance, so the gutter is -29.7 .. -24.3.
# Overall footprint is unchanged at -33.0 .. -17.0.
D1_T = 0.46
D1_T0, D1_T1 = 0.06, 0.86
D1_WING = (-33.00, -29.70)          # outboard of column 0
D1_MAIN = (-24.30, -17.00)          # inboard of column 0, up to the gutter

FACE_LEN = math.hypot(0.57, 0.28)          # along-rake length of the dash face


# =========================================================== frame helpers
def _fascia_r(P, lift=0.0):
    return P["radius"] - P["dash_run"] - 0.025 - lift


def _dash_r(P, t):
    r_near = P["radius"] - P["dash_run"]
    return r_near + ((P["radius"] - 0.05) - r_near) * t


def _wall_r(P, lift=0.0):
    return P["radius"] - 0.02 - lift


def _ff(P, made, name, a_c, z_c, x, y, lift):
    """A placement frame at local (x, y) of a FASCIA panel centred (a_c, z_c).

    Each part gets its own frame so it sits flat on the cylinder instead of
    being cantilevered off one frame at the panel centre.
    """
    ang = a_c + math.degrees(x / _fascia_r(P, lift))
    loc, eul = slots.fascia(P, ang, z_c + y, lift=lift)
    e = kit.frame_empty(name, loc, eul)
    made.append(e)
    return e


def _df(P, made, name, a_c, t_c, x, y, lift):
    """A placement frame at local (x, y) of a DASH panel centred (a_c, t_c).
    `y` is metres along the rake (+ = toward the window)."""
    t = t_c + y / FACE_LEN
    ang = a_c + math.degrees(x / _dash_r(P, t))
    loc, eul = slots.dash(P, ang, t, lift=lift)
    e = kit.frame_empty(name, loc, eul)
    made.append(e)
    return e


def _wf(P, made, name, a_c, x, z, lift):
    """A placement frame at local x / height z of a hull WALLBAND strip."""
    ang = a_c + math.degrees(x / _wall_r(P, lift))
    loc, eul = slots_ext.wallband(P, ang, z, lift=lift)
    e = kit.frame_empty(name, loc, eul)
    made.append(e)
    return e


def _put(frame, objs, out):
    kit.parent_to(objs, frame)
    out += objs
    return objs


# ------------------------------------------------------------- arc bands
def _cyl_band(name, a0, a1, r_out, depth, z0, z1, m, seg=None, bevel=0.0):
    """A solid band following a vertical cylinder (fascia or hull wall).

    r_out is the radius of the BACK face (against the surface); the band grows
    inward toward the pilot by `depth`, so its front face is at r_out - depth.
    """
    n = seg if seg is not None else max(6, int(math.ceil(abs(a1 - a0) / 1.5)))
    r_in = r_out - depth
    ring = ((r_out, z0), (r_out, z1), (r_in, z1), (r_in, z0))
    verts, faces = [], []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        s, c = math.sin(a), math.cos(a)
        for r, z in ring:
            verts.append((r * s, r * c, z))
    for i in range(n):
        b0, b1 = i * 4, (i + 1) * 4
        for k in range(4):
            k2 = (k + 1) % 4
            faces.append((b0 + k, b0 + k2, b1 + k2, b1 + k))
    faces.append((3, 2, 1, 0))
    faces.append((n * 4, n * 4 + 1, n * 4 + 2, n * 4 + 3))
    o = shell.mesh_from(name, verts, faces, m)
    if bevel:
        b = o.modifiers.new("bev", 'BEVEL')
        b.width, b.segments = bevel, 2
    return o


def _dash_band(P, name, a0, a1, t0, t1, l0, l1, m, seg=None, bevel=0.0):
    """A solid band following the RAKED dash face, between two `t` rails and
    two lift heights.  Cross-section corners are (t, lift) pairs."""
    n = seg if seg is not None else max(6, int(math.ceil(abs(a1 - a0) / 1.5)))
    ring = ((t0, l0), (t1, l0), (t1, l1), (t0, l1))
    verts, faces = [], []
    for i in range(n + 1):
        ang = a0 + (a1 - a0) * i / n
        for t, l in ring:
            verts.append(tuple(slots.dash(P, ang, t, lift=l)[0]))
    for i in range(n):
        b0, b1 = i * 4, (i + 1) * 4
        for k in range(4):
            k2 = (k + 1) % 4
            faces.append((b0 + k, b0 + k2, b1 + k2, b1 + k))
    faces.append((3, 2, 1, 0))
    faces.append((n * 4, n * 4 + 1, n * 4 + 2, n * 4 + 3))
    o = shell.mesh_from(name, verts, faces, m)
    if bevel:
        b = o.modifiers.new("bev", 'BEVEL')
        b.width, b.segments = bevel, 2
    return o


# --------------------------------------------------------- small builders
def _bezel(name, pos, r, bez_h=0.0062, glassy=True, screws=0):
    """The turned bezel ring + convex glass from `kit.gauge`, on its own, for
    the three D1 instruments that are not needle gauges."""
    x, y, z = pos
    br = kit.mat("brass")
    out = [kit.revolve(f"{name}_bez",
                       [(r * 0.82, 0.0), (r * 0.82, bez_h * 0.72),
                        (r * 0.865, bez_h), (r * 0.945, bez_h * 0.94),
                        (r * 1.000, bez_h * 0.50), (r * 1.000, -0.0025)],
                       br, center=(x, y, z), verts=36, cap=False)]
    if glassy:
        cap = []
        for i in range(5):
            t = i / 4.0
            cap.append((r * 0.82 * math.cos(t * math.pi / 2),
                        z + bez_h * 0.30
                        + r * 0.17 * math.sin(t * math.pi / 2)))
        out.append(kit.revolve(f"{name}_glass", cap, kit.mat("glass"),
                               center=(x, y, 0.0), verts=28, cap=False))
    for i in range(screws):
        a = math.radians(-138 + 276.0 * i / max(1, screws - 1))
        rr = r * 0.935
        out += kit.screw(f"{name}_scr_{i}",
                         (x + rr * math.sin(a), y + rr * math.cos(a),
                          z + bez_h * 0.46), 0.0026)
    return out


def _lit_face(name, pos, w, h, kind="amber"):
    """A single-quad lit lens face.

    A lens front is one face; modelling it as a solid block would have this
    tier's three lit annunciator cells account for 86% of the WHOLE dressing
    set's section 5.2 emissive-area budget, purely from back faces buried
    inside their own cans.  One quad, front-facing, is both honest and cheap.
    """
    x, y, z = pos
    vs = [(x - w / 2, y - h / 2, z), (x + w / 2, y - h / 2, z),
          (x + w / 2, y + h / 2, z), (x - w / 2, y + h / 2, z)]
    return [shell.mesh_from(name, vs, [(0, 1, 2, 3)],
                            kit.lamp_mat(kind, True))]


def _halfdisc(name, pos, r, y0, m, seg=22):
    """The dark 'ground' half of an artificial horizon: a disc segment whose
    straight edge is a chord at local height `y0`."""
    x, y, z = pos
    k = math.asin(max(-0.98, min(0.98, y0 / r)))
    a0, a1 = math.pi - k, 2 * math.pi + k
    verts = [(x, y + y0, z)]
    for i in range(seg + 1):
        a = a0 + (a1 - a0) * i / seg
        verts.append((x + r * math.cos(a), y + r * math.sin(a), z))
    faces = [(0, i + 1, i + 2) for i in range(seg)]
    return shell.mesh_from(name, verts, faces, m)


def _rotary(name, pos, r=0.026, positions=8, pointer=-52.0, legend=None):
    """A rotary breaker selector: engraved dial, knurled brass knob, pointer."""
    x, y, z = pos
    br, ink = kit.mat("brass"), kit.mat("ink")
    out = [kit.cyl(f"{name}_dial", (x, y, z + 0.0018), r, 0.0036,
                   kit.mat("ivory"), verts=32, smooth=False)]
    out.append(kit.tube(f"{name}_ring", (x, y, z + 0.0022), r, r * 0.90,
                        0.0026, br, verts=32))
    for i in range(positions):
        a = math.radians(-140 + 280.0 * i / (positions - 1))
        rr = r * 0.74
        out.append(kit.box(f"{name}_tk_{i}",
                           (x + rr * math.sin(a), y + rr * math.cos(a),
                            z + 0.0040),
                           (0.0016, r * 0.17, 0.0012), ink, rot=(0, 0, -a)))
        if i % 2 == 0:
            rr = r * 0.52
            out.append(kit.text(f"{name}_n_{i}", str(i + 1), r * 0.24, ink,
                                (x + rr * math.sin(a), y + rr * math.cos(a),
                                 z + 0.0040)))
    # knurled knob: a low-vertex cylinder reads as milled at this scale
    out.append(kit.cyl(f"{name}_knurl", (x, y, z + 0.0080), r * 0.42, 0.0070,
                       br, verts=16, smooth=False, bevel=0.0008))
    out.append(kit.cyl(f"{name}_cap", (x, y, z + 0.0125), r * 0.30, 0.0028,
                       br, verts=18, bevel=0.0006))
    pa = math.radians(pointer)
    pr = r * 0.62
    out.append(kit.box(f"{name}_ptr",
                       (x + (pr / 2) * math.sin(pa), y + (pr / 2) * math.cos(pa),
                        z + 0.0125),
                       (0.0030, pr, 0.0022), br, rot=(0, 0, -pa),
                       bevel=0.0005))
    if legend:
        out.append(kit.text(f"{name}_lg", legend, 0.0072, ink,
                            (x, y - r - 0.0082, z + 0.0016)))
    return out


def _fuse(name, pos, length=0.048, r=0.0080):
    """A ceramic cartridge fuse in its clips, standing vertically.

    Built opaque on purpose: at 4 px wide a glass envelope renders as nothing
    at all and the fuse reads as a floating bead on a wire.  A buff ceramic
    barrel with brass ferrules reads as a fuse from across the room.
    """
    x, y, z = pos
    br = kit.mat("brass")
    out = [kit.cyl(f"{name}_body", (x, y, z + r), r, length * 0.62,
                   kit.mat("slate"), rot=(math.pi / 2, 0, 0), verts=14,
                   smooth=False, bevel=0.0008)]
    out.append(kit.box(f"{name}_lbl", (x, y, z + r + r * 0.72),
                       (r * 1.30, length * 0.26, r * 0.20), kit.mat("ink")))
    for i, s_ in enumerate((-1, 1)):
        yy = y + s_ * (length * 0.155 + length * 0.095)
        out.append(kit.cyl(f"{name}_fer_{i}", (x, yy, z + r), r * 1.10,
                           length * 0.19, br, rot=(math.pi / 2, 0, 0),
                           verts=14, smooth=False, bevel=0.0006))
        out.append(kit.box(f"{name}_clip_{i}",
                           (x, y + s_ * (length / 2 - 0.0030), z + r * 0.30),
                           (r * 2.05, 0.0055, r * 0.75), br, bevel=0.0006))
    return out


def _rivet_arc(P, name, pts, r=0.0032, m=None):
    """Domed rivets at a list of world points -- spheres need no orientation,
    so they can follow an arc without a frame each."""
    mm = m or kit.mat("brass")
    return [kit.sphere(f"{name}_{i}", tuple(p), r, mm, scale=(1, 1, 0.55),
                       seg=10, ring=6) for i, p in enumerate(pts)]


def _fascia_pts(P, a_c, z_c, x, y0, y1, n, lift):
    ang = a_c + math.degrees(x / _fascia_r(P, lift))
    out = []
    for i in range(n):
        y = y0 + (y1 - y0) * (i / max(1, n - 1))
        out.append(slots.fascia(P, ang, z_c + y, lift=lift)[0])
    return out


# ================================================= 6. F1 ATMOSPHERE PLANT
def _f1(P, made):
    """Life support: O2, CO2 scrubber, cabin pressure.  The flagship of the
    lower-left corner and the biggest dressing prop in the plan.

    Three tall sight glasses with float balls at different heights, two ivory
    needle gauges, a bank of six bat toggles under a hinged guard bar, a red
    guarded PURGE switch under a wire cage, a ribbed cast blower with a mesh
    intake, and a stencilled skirt.  ZERO lit lamps (plan section 5.2).
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")
    hw, hh = F1_W / 2, F1_H / 2
    z0, z1 = F1_Z - hh, F1_Z + hh
    r_back = _fascia_r(P) + 0.002                 # 2 mm into the fascia
    face_lift = 0.020                             # panel front face
    r_face = _fascia_r(P) - face_lift
    half_deg = math.degrees(hw / r_face)
    a0, a1 = F1_A - half_deg, F1_A + half_deg

    # ---- backing panel, frame rails, cheeks
    out.append(_cyl_band("dr_f1_back", a0, a1, r_back, 0.022, z0, z1,
                         _grey()))
    # Panel FRAMES are steel, not brass.  Plan section 4 already asks D1 to drop
    # its brass frame so FMM's stays unique; the same argument applies to the
    # whole tier -- and structurally it is also just true, consoles of this era
    # were steel frames carrying brass instrument furniture.  Brass is spent on
    # bezels, nameplates, switch strips, inlay, knobs and rivets instead, where
    # it reads.  Measurably: brass fell from 22% of tier-2 screen area to 9%,
    # which is what carries the section 5.4 saturation assertion.
    st = kit.mat("steel")
    for k, (zz0, zz1) in enumerate(((z0, z0 + 0.013), (z1 - 0.013, z1))):
        out.append(_cyl_band(f"dr_f1_rail_{k}", a0, a1, r_back - 0.022, 0.014,
                             zz0, zz1, st))
        out.append(_cyl_band(f"dr_f1_bead_{k}", a0, a1, r_back - 0.030, 0.005,
                             zz0 + (0.0 if k else 0.011),
                             zz0 + (0.004 if k else 0.015), br))
    for k, aa in enumerate((a0, a1)):
        a = math.radians(aa)
        rr = r_face - 0.008
        out.append(kit.box(f"dr_f1_cheek_{k}",
                           (rr * math.sin(a), rr * math.cos(a), F1_Z),
                           (0.011, 0.014, F1_H), st, rot=(0, 0, -a),
                           bevel=0.0016))
    for k, sx in enumerate((-1, 1)):
        out += _rivet_arc(P, f"dr_f1_riv_{k}",
                          _fascia_pts(P, F1_A, F1_Z, sx * (hw - 0.008),
                                      -hh + 0.030, hh - 0.030, 13,
                                      face_lift + 0.016))

    # ---- header: nameplate, inspection stamp, caution triangle
    f = _ff(P, made, "dr_f1_hdr", F1_A, F1_Z, -0.058, 0.226, face_lift)
    _put(f, kit.nameplate("dr_f1_np", "LIFE SUPPORT", (0, 0, 0), h=0.024,
                          size=0.0110), out)
    f = _ff(P, made, "dr_f1_stamp", F1_A, F1_Z, 0.088, 0.226, face_lift)
    _put(f, kit.inspection_stamp("dr_f1_ins", (0, 0, 0), "9-A", r=0.011), out)
    f = _ff(P, made, "dr_f1_warn", F1_A, F1_Z, 0.156, 0.226, face_lift)
    _put(f, kit.warn_triangle("dr_f1_wt", (0, 0, 0), 0.030), out)

    # ---- three tall sight glasses.  Different fill heights on purpose:
    # perfect symmetry is the amateur-3D tell (plan section 5.3).
    for i, (x, fill, lab) in enumerate(((-0.160, 0.72, "O2"),
                                        (-0.108, 0.41, "N2"),
                                        (-0.056, 0.58, "CO2"))):
        f = _ff(P, made, f"dr_f1_sgf_{i}", F1_A, F1_Z, x, 0.116, face_lift)
        _put(f, kit.sightglass(f"dr_f1_sg_{i}", (0, 0, 0), length=0.130,
                               r=0.0105, fill=fill, grads=8), out)
        f = _ff(P, made, f"dr_f1_sglf_{i}", F1_A, F1_Z, x, 0.202, face_lift)
        _put(f, kit.stencil(f"dr_f1_sgl_{i}", lab, (0, 0, 0), 0.012, m=ink),
             out)

    # ---- two needle gauges, pale ivory faces
    f = _ff(P, made, "dr_f1_g0f", F1_A, F1_Z, 0.055, 0.118, face_lift)
    _put(f, kit.gauge("dr_f1_g0", (0, 0, 0), r=0.042, ticks=9,
                      redline=(86, 125), needle_deg=-36.0, label="mm Hg",
                      sub="CABIN"), out)
    f = _ff(P, made, "dr_f1_g1f", F1_A, F1_Z, 0.152, 0.118, face_lift)
    _put(f, kit.gauge("dr_f1_g1", (0, 0, 0), r=0.042, ticks=7,
                      needle_deg=11.0, label="PPM CO2", sub="SCRB"), out)
    f = _ff(P, made, "dr_f1_glf", F1_A, F1_Z, 0.104, 0.196, face_lift)
    _put(f, kit.stencil("dr_f1_gl", "PRESSURE  /  SCRUBBER", (0, 0, 0),
                        0.0105, m=ink), out)

    # ---- divider rails
    for k, zz in enumerate((F1_Z + 0.030, F1_Z - 0.086)):
        out.append(_cyl_band(f"dr_f1_div_{k}", a0 + 0.4, a1 - 0.4,
                             r_face + 0.002, 0.007, zz - 0.0026, zz + 0.0026,
                             br))

    # ---- milled brass switch strip + six bat toggles under a hinged guard
    strip_lift = face_lift + 0.006
    sa0 = F1_A + math.degrees(-0.196 / r_face)
    sa1 = F1_A + math.degrees(0.058 / r_face)
    out.append(_cyl_band("dr_f1_strip", sa0, sa1, r_face + 0.001, 0.007,
                         F1_Z - 0.046, F1_Z + 0.004, br, bevel=0.0015))
    legs = ("O2", "N2", "SCRB", "FAN", "HTR", "VLV")
    tilts = (18.0, -20.0, 22.0, 19.0, -21.0, 17.0)
    for i in range(6):
        x = -0.170 + i * 0.040
        f = _ff(P, made, f"dr_f1_tgf_{i}", F1_A, F1_Z, x, -0.020, strip_lift)
        _put(f, kit.toggle(f"dr_f1_tg_{i}", (0, 0, 0), kind="bat",
                           pos_deg=tilts[i], legend=legs[i], legend_w=0.032),
             out)
    # hinged guard bar across the bank
    f = _ff(P, made, "dr_f1_gb", F1_A, F1_Z, -0.070, 0.002, strip_lift)
    gb = [kit.box("dr_f1_gbar", (0.0, 0.0, 0.021), (0.242, 0.011, 0.005), br,
                  rot=(math.radians(-22), 0, 0), bevel=0.0010)]
    for k, sx in enumerate((-1, 1)):
        gb.append(kit.box(f"dr_f1_gbchk_{k}", (sx * 0.124, -0.006, 0.010),
                          (0.006, 0.020, 0.020), br, bevel=0.0010))
        gb += kit.hexbolt(f"dr_f1_gbb_{k}", (sx * 0.124, -0.012, 0.019),
                          0.0030, 0.0035)
    _put(f, gb, out)

    # ---- PURGE: caged red-guarded switch.  One of the whole set's THREE
    # rationed reds, and it is painted, never lit (plan section 5.2).
    f = _ff(P, made, "dr_f1_pgf", F1_A, F1_Z, 0.136, -0.018, face_lift)
    pg = [kit.box("dr_f1_pgpl", (0.0, 0.0, 0.0028), (0.062, 0.062, 0.0055),
                  kit.mat("red_paint"), bevel=0.0012)]
    pg += kit.toggle("dr_f1_pgt", (0.0, 0.006, 0.0055), kind="caged",
                     pos_deg=-26.0)
    pg.append(kit.tube("dr_f1_pgring", (0.0, 0.006, 0.0090), 0.0180, 0.0140,
                       0.0050, kit.mat("red_paint"), verts=20))
    _put(f, pg, out)
    f = _ff(P, made, "dr_f1_pglf", F1_A, F1_Z, 0.136, -0.062, face_lift)
    _put(f, [kit.box("dr_f1_pgleg", (0, 0, 0.0016), (0.062, 0.016, 0.0032),
                     kit.mat("red_paint"), bevel=0.0006),
             kit.text("dr_f1_pgtx", "PURGE", 0.0092, kit.mat("ivory"),
                      (0, 0, 0.0034))], out)

    # ---- ribbed cast blower housing
    f = _ff(P, made, "dr_f1_blf", F1_A, F1_Z, -0.106, -0.164, face_lift)
    #  a stepped cast volute, not a spoked wheel: concentric ribs read as
    #  cast iron where long radial ones read as a ship's helm.
    bl = [kit.cyl("dr_f1_blflg", (0, 0, 0.005), 0.062, 0.010,
                  kit.mat("slate"), verts=32, bevel=0.0018, smooth=False)]
    bl.append(kit.cyl("dr_f1_bldrum", (0, 0, 0.019), 0.050, 0.028,
                      _grey(), verts=32, bevel=0.0020,
                      smooth=False))
    for i, (rr, zz) in enumerate(((0.0455, 0.0330), (0.0355, 0.0380),
                                  (0.0255, 0.0424))):
        bl.append(kit.tube(f"dr_f1_blrib_{i}", (0, 0, zz), rr, rr - 0.0060,
                           0.0060, kit.mat("slate"), verts=28))
        bl.append(kit.cyl(f"dr_f1_blstp_{i}", (0, 0, zz + 0.0028),
                          rr - 0.0060, 0.0056, _grey(), verts=28,
                          smooth=False))
    bl.append(kit.cyl("dr_f1_blhub", (0, 0, 0.0472), 0.0135, 0.0080, br,
                      verts=20, bevel=0.0012))
    for i in range(4):
        a = 2 * math.pi * i / 4 + math.pi / 4
        bl += kit.hexbolt(f"dr_f1_blb_{i}",
                          (0.056 * math.sin(a), 0.056 * math.cos(a), 0.010),
                          0.0042, 0.0040)
    # outlet duct leaving the volute up toward the toggle strip
    bl.append(kit.box("dr_f1_bldct", (0.044, 0.050, 0.016),
                      (0.030, 0.052, 0.030), kit.mat("slate"),
                      rot=(0, 0, math.radians(-22)), bevel=0.0020))
    bl.append(kit.tube("dr_f1_bldctf", (0.058, 0.070, 0.016), 0.020, 0.014,
                       0.008, br, rot=(0, 0, math.radians(-22)), verts=16))
    _put(f, bl, out)

    # ---- mesh intake grille
    f = _ff(P, made, "dr_f1_grf", F1_A, F1_Z, 0.098, -0.166, face_lift)
    gr = kit.bez_frame("dr_f1_grbz", 0.0, 0.0, 0.140, 0.104, 0.0, 0.010, br,
                       bar=0.007)
    gr += kit.grille("dr_f1_gr", (0, 0, 0.001), 0.126, 0.090, 8, 6, depth=0.005)
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        gr += kit.hexbolt(f"dr_f1_grb_{i}",
                          (sx * 0.0665, sy * 0.0485, 0.010), 0.0040, 0.0038)
    _put(f, gr, out)

    # ---- stencilled skirt
    f = _ff(P, made, "dr_f1_sk0", F1_A, F1_Z, -0.058, -0.234, face_lift)
    _put(f, kit.stencil("dr_f1_skt0", "ATMOS PLANT", (0, 0, 0), 0.0165), out)
    f = _ff(P, made, "dr_f1_sk1", F1_A, F1_Z, 0.120, -0.234, face_lift)
    _put(f, kit.stencil("dr_f1_skt1", "FRAME 9", (0, 0, 0), 0.0145,
                        worn=True), out)
    made.extend(out)


# =================================================== 7. F5 MAIN BUS BOARD
def _f5(P, made):
    """Reactor output and power distribution.  The bottom-right anchor that
    balances F1: a brass single-line bus mimic on black bakelite, three rotary
    breaker selectors, a big centre-zero LOAD BALANCE galvanometer, a
    MAIN/AUX/EMERG transfer switch, and eight cartridge fuses behind a hinged
    glass door with a brass hasp.  Two lit node lamps out of seven.
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")
    hw, hh = F5_W / 2, F5_H / 2
    z0, z1 = F5_Z - hh, F5_Z + hh
    r_back = _fascia_r(P) + 0.002
    face_lift = 0.020
    r_face = _fascia_r(P) - face_lift
    half_deg = math.degrees(hw / r_face)
    a0, a1 = F5_A - half_deg, F5_A + half_deg

    out.append(_cyl_band("dr_f5_back", a0, a1, r_back, 0.022, z0, z1,
                         _grey()))
    st = kit.mat("steel")
    for k, (zz0, zz1) in enumerate(((z0, z0 + 0.012), (z1 - 0.012, z1))):
        out.append(_cyl_band(f"dr_f5_rail_{k}", a0, a1, r_back - 0.022, 0.014,
                             zz0, zz1, st))
        out.append(_cyl_band(f"dr_f5_bead_{k}", a0, a1, r_back - 0.030, 0.005,
                             zz0 + (0.0 if k else 0.010),
                             zz0 + (0.004 if k else 0.014), br))
    for k, aa in enumerate((a0, a1)):
        a = math.radians(aa)
        rr = r_face - 0.008
        out.append(kit.box(f"dr_f5_cheek_{k}",
                           (rr * math.sin(a), rr * math.cos(a), F5_Z),
                           (0.011, 0.014, F5_H), st, rot=(0, 0, -a),
                           bevel=0.0016))
    for k, sx in enumerate((-1, 1)):
        out += _rivet_arc(P, f"dr_f5_riv_{k}",
                          _fascia_pts(P, F5_A, F5_Z, sx * (hw - 0.008),
                                      -hh + 0.026, hh - 0.026, 12,
                                      face_lift + 0.016))

    # ---- single-line bus mimic on a black bakelite ground.  Built in two
    # halves on their own frames so the brass inlay follows the fascia arc
    # instead of sinking its ends into the panel.
    out.append(_cyl_band("dr_f5_mimg", a0 + 0.6, a1 - 0.6, r_face + 0.001,
                         0.006, F5_Z + 0.104, F5_Z + 0.208,
                         kit.mat("ebonite")))
    mim_lift = face_lift + 0.005
    GY = 0.156                       # ground centre, in panel-local y
    BUS = 0.006                      # bus bar height within the ground
    SRC = (-0.090, 0.096)            # generator risers
    DRP = (-0.118, -0.060, -0.002, 0.056, 0.114)
    for half, (mx, seg) in enumerate(((-0.080, (-0.152, 0.000)),
                                      (0.080, (0.000, 0.152)))):
        f = _ff(P, made, f"dr_f5_mimf_{half}", F5_A, F5_Z, mx, GY, mim_lift)
        objs = kit.mimic_strip(f"dr_f5_bus_{half}",
                               [(seg[0] - mx, BUS), (seg[1] - mx, BUS)],
                               width=0.0115, z=0.0, thickness=0.0040)
        objs += kit.mimic_strip(f"dr_f5_tie_{half}",
                                [(seg[0] - mx, -0.030), (seg[1] - mx, -0.030)],
                                width=0.0055, z=0.0, thickness=0.0028)
        for j, dx in enumerate(DRP):
            if seg[0] <= dx < seg[1]:
                objs += kit.mimic_strip(f"dr_f5_dr_{half}_{j}",
                                        [(dx - mx, BUS), (dx - mx, -0.026)],
                                        width=0.0050, z=0.0, thickness=0.0030)
                #  an in-line breaker symbol on every feeder
                objs.append(kit.box(f"dr_f5_brk_{half}_{j}",
                                    (dx - mx, BUS - 0.011, 0.0022),
                                    (0.0130, 0.0090, 0.0044), br,
                                    bevel=0.0008))
                objs.append(kit.box(f"dr_f5_brki_{half}_{j}",
                                    (dx - mx, BUS - 0.011, 0.0046),
                                    (0.0090, 0.0050, 0.0016),
                                    kit.mat("ebonite")))
        for j, rx in enumerate(SRC):
            if seg[0] <= rx < seg[1]:
                objs += kit.mimic_strip(f"dr_f5_rs_{half}_{j}",
                                        [(rx - mx, BUS), (rx - mx, 0.026)],
                                        width=0.0050, z=0.0, thickness=0.0030)
        _put(f, objs, out)
    # node lamps: seven, TWO lit -- exactly what plan 5.2 allots F5.
    nodes = [(x, -0.030, "amber", False) for x in DRP]
    nodes += [(x, 0.030, "green", False) for x in SRC]
    nodes[1] = (nodes[1][0], nodes[1][1], "amber", True)
    nodes[5] = (nodes[5][0], nodes[5][1], "green", True)
    for i, (nx, ny, knd, lit) in enumerate(nodes):
        f = _ff(P, made, f"dr_f5_ndf_{i}", F5_A, F5_Z, nx, GY + ny, mim_lift)
        objs = kit.lampcell(f"dr_f5_nd_{i}", (0, 0, 0), w=0.015, h=0.015,
                            lit=lit, kind=knd, depth=0.007, frame=False,
                            round_lens=True)
        _put(f, objs, out)
    f = _ff(P, made, "dr_f5_mimtx", F5_A, F5_Z, 0.0, GY + 0.045, mim_lift)
    _put(f, kit.stencil("dr_f5_mimt", "MAIN BUS  440 V  3 PH", (0, 0, 0),
                        0.0090), out)
    for i, (nx, lab) in enumerate(zip(DRP, ("DRIVE", "LIFE", "COMMS",
                                            "GYRO", "AUX"))):
        f = _ff(P, made, f"dr_f5_ldf_{i}", F5_A, F5_Z, nx, GY - 0.044,
                mim_lift)
        _put(f, kit.stencil(f"dr_f5_ld_{i}", lab, (0, 0, 0), 0.0068,
                            worn=(i == 3)), out)

    for k, zz in enumerate((F5_Z + 0.096, F5_Z - 0.094)):
        out.append(_cyl_band(f"dr_f5_div_{k}", a0 + 0.4, a1 - 0.4,
                             r_face + 0.002, 0.007, zz - 0.0026, zz + 0.0026,
                             br))

    # ---- LOAD BALANCE centre-zero galvanometer
    f = _ff(P, made, "dr_f5_gvf", F5_A, F5_Z, -0.100, 0.006, face_lift)
    _put(f, kit.gauge("dr_f5_gv", (0, 0, 0), r=0.066, ticks=9, sweep_deg=118.0,
                      needle_deg=7.0, label="LOAD BAL", sub="KW",
                      depth=0.020, bezel_screws=4), out)

    # ---- three rotary breaker selectors
    for i, (x, ptr, lg) in enumerate(((0.022, -64.0, "BUS A"),
                                      (0.086, 18.0, "BUS B"),
                                      (0.150, -122.0, "TIE"))):
        f = _ff(P, made, f"dr_f5_rtf_{i}", F5_A, F5_Z, x, 0.052, face_lift)
        _put(f, _rotary(f"dr_f5_rt_{i}", (0, 0, 0), r=0.025, positions=8,
                        pointer=ptr, legend=lg), out)

    # ---- MAIN / AUX / EMERG transfer switch, heavy bakelite handle
    f = _ff(P, made, "dr_f5_tsf", F5_A, F5_Z, 0.088, -0.048, face_lift)
    ts = [kit.box("dr_f5_tspl", (0, 0, 0.0022), (0.150, 0.052, 0.0044),
                  br, bevel=0.0010)]
    ts += kit.bez_frame("dr_f5_tsbz", 0.0, 0.0, 0.150, 0.052, 0.0, 0.007, br,
                        bar=0.0040)
    for j, lab in enumerate(("MAIN", "AUX", "EMERG")):
        ts.append(kit.text(f"dr_f5_tsl_{j}", lab, 0.0078, ink,
                           (-0.050 + j * 0.050, 0.016, 0.0048)))
        ts.append(kit.box(f"dr_f5_tsd_{j}", (-0.050 + j * 0.050, 0.001, 0.0050),
                          (0.0018, 0.010, 0.0014), ink))
    hb = math.radians(-19.0)
    hl = 0.052
    ts.append(kit.cyl("dr_f5_tspiv", (0.0, -0.018, 0.0090), 0.0092, 0.010, br,
                      verts=18, bevel=0.0010))
    ts.append(kit.cone("dr_f5_tshdl",
                       (-math.sin(hb) * 0.0 + math.sin(hb) * (hl / 2) * -1,
                        -0.018 + math.cos(hb) * (hl / 2) * 0.0
                        + (hl / 2) * math.cos(hb),
                        0.0140),
                       0.0080, 0.0052, hl, kit.mat("ebonite"),
                       rot=(math.pi / 2, 0, hb), verts=14))
    ts.append(kit.sphere("dr_f5_tsknb",
                         (math.sin(hb) * -hl, -0.018 + math.cos(hb) * hl,
                          0.0140), 0.0090, kit.mat("ebonite"), seg=14, ring=9))
    _put(f, ts, out)

    # ---- eight cartridge fuses behind a hinged glass door with a brass hasp
    out.append(_cyl_band("dr_f5_bay", a0 + 0.8, a1 - 0.8, r_face + 0.001,
                         0.005, F5_Z - 0.220, F5_Z - 0.104, _dark()))
    bay_lift = face_lift + 0.004
    for i in range(8):
        x = -0.126 + i * 0.036
        f = _ff(P, made, f"dr_f5_fzf_{i}", F5_A, F5_Z, x, -0.152, bay_lift)
        _put(f, _fuse(f"dr_f5_fz_{i}", (0, 0, 0), length=0.048, r=0.0078), out)
        f = _ff(P, made, f"dr_f5_fzlf_{i}", F5_A, F5_Z, x, -0.196, bay_lift)
        _put(f, kit.stencil(f"dr_f5_fzl_{i}", str(i + 1), (0, 0, 0), 0.0090,
                            m=ink), out)
    f = _ff(P, made, "dr_f5_dr", F5_A, F5_Z, 0.0, -0.161, face_lift)
    dr = kit.bez_frame("dr_f5_drbz", 0.0, 0.0, 0.298, 0.116, 0.026, 0.036,
                       kit.mat("steel"), bar=0.0060)
    dr.append(kit.box("dr_f5_drgl", (0, 0, 0.031), (0.285, 0.103, 0.0030),
                      kit.mat("glass")))
    for j, sy in enumerate((-1, 1)):                       # hinge knuckles
        dr.append(kit.cyl(f"dr_f5_drhg_{j}", (-0.151, sy * 0.038, 0.031),
                          0.0055, 0.016, br, rot=(math.pi / 2, 0, 0),
                          verts=12))
    dr.append(kit.box("dr_f5_drhsp", (0.156, 0.0, 0.033), (0.024, 0.020,
                                                           0.0040), br,
                      bevel=0.0008))
    dr.append(kit.cyl("dr_f5_drstp", (0.164, 0.0, 0.036), 0.0035, 0.012, br,
                      verts=10))
    dr.append(kit.text("dr_f5_drtx", "FUSES  1-8   FRAME 15", 0.0092, ink,
                       (-0.030, 0.0480, 0.0375)))
    _put(f, dr, out)
    made.extend(out)


# ========================================== 8. H1 CAUTION ANNUNCIATOR STRIP
H1_LEGENDS_TOP = ("FIRE", "LOW O2", "CO2 HIGH", "BUS FAULT",
                  "HULL", "CRYO", "GRAV", "RAD")
H1_LEGENDS_BOT = ("WATER", "COOLANT", "DOOR", "TRIM",
                  "GYRO", "RELAY", "TAPE", "MASTER")


def _h1(P, made):
    """Master warning system.  A continuous brass-framed strip on the hull wall
    above the window header spanning 45 deg of arc: a padlocked breaker box at
    the left end (correctly half-clipped by column 0), 16 engraved legend cells
    in two rows of eight, and a PRESS TO TEST bezel plus a dimmer knob at the
    right end.

    Only THREE of the 16 cells are lit, and dimly (plan section 5.2).
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")
    r_back = _wall_r(P) + 0.008
    back_depth = 0.024
    face_lift = _wall_r(P) - (r_back - back_depth)     # ~0.016
    zc = (H1_Z0 + H1_Z1) / 2.0

    out.append(_cyl_band("dr_h1_back", H1_A0 - 0.5, H1_A1 + 0.5, r_back,
                         back_depth, H1_Z0, H1_Z1, _grey()))
    # frame rails, and their low-detail continuation past the frame edge
    for k, (zz0, zz1) in enumerate(((H1_Z0, H1_Z0 + H1_RAIL),
                                    (H1_Z1 - H1_RAIL, H1_Z1))):
        out.append(_cyl_band(f"dr_h1_rail_{k}", H1_A0 - 0.5, H1_A1 + 0.5,
                             r_back - back_depth, 0.018, zz0, zz1,
                             br if k else kit.mat("steel")))
    for k, (ca0, ca1) in enumerate(((-H1_CONT, H1_A0 - 0.5),
                                    (H1_A1 + 0.5, H1_CONT))):
        out.append(_cyl_band(f"dr_h1_cont_{k}", ca0, ca1, r_back, 0.016,
                             2.020, 2.056, _grey()))
        #  slim, and plain steel rather than brass: every pixel of these sits
        #  behind MQB / DNSM or off frame (plan 4, "still empty, honestly" 4),
        #  so they are insurance for a wider plate, not decoration.
        out.append(_cyl_band(f"dr_h1_crt_{k}", ca0, ca1, r_back - 0.016, 0.010,
                             2.106, 2.115, kit.mat("steel")))
        out.append(_cyl_band(f"dr_h1_crb_{k}", ca0, ca1, r_back - 0.016, 0.010,
                             1.941, 1.950, kit.mat("steel")))
    # end brackets where the full-height strip lands on the continuation
    for k, aa in enumerate((H1_A0 - 0.5, H1_A1 + 0.5)):
        a = math.radians(aa)
        rr = r_back - back_depth - 0.010
        out.append(kit.box(f"dr_h1_brk_{k}",
                           (rr * math.sin(a), rr * math.cos(a), zc),
                           (0.014, 0.020, H1_Z1 - H1_Z0), br, rot=(0, 0, -a),
                           bevel=0.0016))

    # ---- 16 legend cells, two rows of eight, -20..+12 deg
    # Three lit out of sixteen -- the plan's 1-in-5 rule, at its limit.
    lit = {("t", 2), ("b", 1), ("b", 5)}
    for row, (tag, legs, z) in enumerate((("t", H1_LEGENDS_TOP, 2.062),
                                          ("b", H1_LEGENDS_BOT, 2.000))):
        for i, leg in enumerate(legs):
            ang = -20.0 + 4.0 * (i + 0.5)
            loc, eul = slots_ext.wallband(P, ang, z, lift=face_lift)
            f = kit.frame_empty(f"dr_h1_cf_{row}_{i}", loc, eul)
            made.append(f)
            on = (tag, i) in lit
            kind = "green" if (tag, i) == ("b", 5) else "amber"
            #  the legend is drawn here rather than by `lampcell` so a DARK
            #  cell gets PALE lettering (ink on unlit amber is invisible) and a
            #  lit cell gets dark lettering over the glow, which is how a
            #  back-illuminated legend actually reads.
            _put(f, _annunciator(f"dr_h1_c_{row}_{i}", (0, 0, 0), 0.190,
                                 0.056, leg, on, kind), out)

    # ---- left end: cast breaker box, hinged door, padlock hasp, circuit list
    f = _wf(P, made, "dr_h1_bxf", -23.75, 0.0, 2.036, face_lift)
    bx = [kit.box("dr_h1_bx", (0, 0, 0.022), (0.300, 0.140, 0.044),
                  kit.mat("slate"), bevel=0.0035)]
    bx += kit.bez_frame("dr_h1_bxbz", 0.0, 0.0, 0.300, 0.140, 0.040, 0.050,
                        kit.mat("steel"), bar=0.0060)
    bx.append(kit.box("dr_h1_bxdr", (0.006, 0.0, 0.046), (0.276, 0.118,
                                                          0.0055),
                      _grey(), bevel=0.0018))
    for j in range(3):                                     # hinge knuckles
        bx.append(kit.cyl(f"dr_h1_bxhg_{j}", (-0.146, -0.048 + j * 0.048,
                                              0.046), 0.0060, 0.020, br,
                          rot=(math.pi / 2, 0, 0), verts=12))
    bx.append(kit.box("dr_h1_bxhsp", (0.132, 0.0, 0.050), (0.044, 0.020,
                                                           0.0045), br,
                      bevel=0.0008))
    bx.append(kit.tube("dr_h1_bxlock", (0.150, 0.0, 0.058), 0.0090, 0.0055,
                       0.0060, kit.mat("steel"), rot=(0, math.pi / 2, 0),
                       verts=12))
    bx += kit.rivet_row("dr_h1_bxrv", (-0.140, -0.064, 0.0495),
                        (0.140, -0.064, 0.0495), 8, r=0.0026)
    for j, ln in enumerate(("1  MAIN BUS TIE", "2  ANNUN SUPPLY",
                            "3  GYRO 400 CY", "4  SCRUBBER FAN")):
        bx.append(kit.text(f"dr_h1_bxls_{j}", ln, 0.0105, ink,
                           (-0.008, 0.036 - j * 0.024, 0.0495), align='LEFT'))
    _put(f, bx, out)

    # ---- right end: PRESS TO TEST, and a dimmer with an engraved scale
    f = _wf(P, made, "dr_h1_ptf", 14.3, 0.0, 2.052, face_lift)
    pt = [kit.cyl("dr_h1_ptcan", (0, 0, 0.006), 0.0230, 0.012,
                  kit.mat("case"), verts=24, bevel=0.0012)]
    pt += _bezel("dr_h1_pt", (0, 0, 0.012), 0.0250, bez_h=0.0058, glassy=False,
                 screws=3)
    pt.append(kit.cyl("dr_h1_ptbtn", (0, 0, 0.0150), 0.0165, 0.0080,
                      kit.mat("ebonite"), verts=22, bevel=0.0016))
    _put(f, pt, out)
    f = _wf(P, made, "dr_h1_ptlf", 14.3, 0.0, 2.014, face_lift)
    _put(f, kit.stencil("dr_h1_ptl", "PRESS TO TEST", (0, 0, 0), 0.0092,
                        m=ink), out)

    f = _wf(P, made, "dr_h1_dmf", 16.7, 0.0, 2.052, face_lift)
    dm = [kit.cyl("dr_h1_dmpl", (0, 0, 0.0018), 0.0270, 0.0036,
                  kit.mat("ivory"), verts=28, smooth=False)]
    for j in range(6):
        a = math.radians(-118 + 236.0 * j / 5.0)
        rr = 0.0205
        dm.append(kit.box(f"dr_h1_dmtk_{j}",
                          (rr * math.sin(a), rr * math.cos(a), 0.0040),
                          (0.0015, 0.0055, 0.0012), ink, rot=(0, 0, -a)))
    dm.append(kit.cyl("dr_h1_dmknb", (0, 0, 0.0090), 0.0135, 0.0110, br,
                      verts=14, smooth=False, bevel=0.0008))
    dm.append(kit.box("dr_h1_dmptr", (0.0, 0.0090, 0.0146),
                      (0.0026, 0.0180, 0.0020), br, bevel=0.0005))
    _put(f, dm, out)
    f = _wf(P, made, "dr_h1_dmlf", 16.7, 0.0, 2.014, face_lift)
    _put(f, kit.stencil("dr_h1_dml", "DIM   BRT", (0, 0, 0), 0.0092, m=ink),
         out)

    # ---- strip nameplate, tucked under the left cell block
    f = _wf(P, made, "dr_h1_npf", -19.0, 0.0, 1.958, face_lift + 0.020)
    _put(f, kit.stencil("dr_h1_np", "CAUTION - ADVISORY", (0, 0, 0), 0.0090,
                        m=ink), out)
    made.extend(out)


# ============================================ 9. D1 FLIGHT & TRIM SUB-PANEL
def _dash_pts_a(P, ang, t0, t1, n, lift):
    return [slots.dash(P, ang, t0 + (t1 - t0) * (i / max(1, n - 1)),
                       lift=lift)[0] for i in range(n)]


def _d1_recess(P, made, out, tag, a0, a1):
    """The recess itself: a hull-grey ground inside a near-black kerb, and
    rivet rows down both cheeks.  NO brass -- see the D1 docstring."""
    kerb = _dark()
    out.append(_dash_band(P, f"dr_d1_gnd_{tag}", a0, a1, D1_T0, D1_T1, 0.001,
                          0.012, _grey()))
    for k, (tt0, tt1) in enumerate(((D1_T0, D1_T0 + 0.017),
                                    (D1_T1 - 0.017, D1_T1))):
        out.append(_dash_band(P, f"dr_d1_kerb_{tag}_{k}", a0, a1, tt0, tt1,
                              0.001, 0.020, kerb))
    for k, aa in enumerate((a0, a1)):
        loc, eul = slots.dash(P, aa, (D1_T0 + D1_T1) / 2.0, lift=0.010)
        out.append(kit.box(f"dr_d1_kerbs_{tag}_{k}", tuple(loc),
                           (0.011, (D1_T1 - D1_T0) * FACE_LEN, 0.020), kerb,
                           rot=eul, bevel=0.0016))
    for k, aa in enumerate((a0 + 0.17, a1 - 0.17)):
        out += _rivet_arc(P, f"dr_d1_riv_{tag}_{k}",
                          _dash_pts_a(P, aa, D1_T0 + 0.03, D1_T1 - 0.03, 13,
                                      0.021))


def _d1_switch_strip(P, made, out, tag, a0, a1, legs, tilts, angs):
    """A milled brass switch strip carrying bat toggles with engraved bakelite
    legend plates.  `pos_deg` is varied per switch on purpose (plan 5.3)."""
    out.append(_dash_band(P, f"dr_d1_strip_{tag}", a0, a1, 0.262, 0.338, 0.011,
                          0.018, kit.mat("brass"), bevel=0.0018))
    for i, ang in enumerate(angs):
        loc, eul = slots.dash(P, ang, 0.30, lift=0.018)
        f = kit.frame_empty(f"dr_d1_tgf_{tag}_{i}", loc, eul)
        made.append(f)
        _put(f, kit.toggle(f"dr_d1_tg_{tag}_{i}", (0, 0, 0), kind="bat",
                           pos_deg=tilts[i], legend=legs[i],
                           legend_w=0.038 if tag == "m" else 0.030), out)


def _d1_horizon(name, br, ink):
    """Artificial horizon: a black/ivory tumbling ball behind convex glass."""
    ah = [kit.cyl(f"{name}_can", (0, 0, 0.009), 0.0450, 0.018,
                  kit.mat("case"), verts=28, bevel=0.0015, smooth=False)]
    ah.append(kit.cyl(f"{name}_sky", (0, 0, 0.0190), 0.0378, 0.0040,
                      kit.mat("ivory"), verts=32, smooth=False))
    grd = _halfdisc(f"{name}_gnd", (0, 0, 0.0212), 0.0378, -0.0050,
                    kit.mat("ebonite"))
    grd.rotation_euler = (0, 0, math.radians(-7.0))
    ah.append(grd)
    ah.append(kit.box(f"{name}_hz", (0.0, -0.0036, 0.0224),
                      (0.0720, 0.0016, 0.0012), kit.mat("paper"),
                      rot=(0, 0, math.radians(-7.0))))
    for j, sx in enumerate((-1, 1)):              # the fixed aircraft symbol
        ah.append(kit.box(f"{name}_w_{j}", (sx * 0.0200, 0.0, 0.0240),
                          (0.0200, 0.0026, 0.0018), br))
    ah.append(kit.cyl(f"{name}_dot", (0, 0, 0.0242), 0.0030, 0.0022, br,
                      verts=10))
    for j in range(5):                            # bank scale
        a = math.radians(-40 + 20.0 * j)
        rr = 0.0342
        ah.append(kit.box(f"{name}_bk_{j}",
                          (rr * math.sin(a), rr * math.cos(a), 0.0224),
                          (0.0016, 0.0058, 0.0012), ink, rot=(0, 0, -a)))
    ah += _bezel(name, (0, 0, 0.0155), 0.0460, bez_h=0.0066, screws=3)
    return ah


def _d1_turnbank(name, br, ink):
    """Turn-and-bank: a real steel ball rolling in a curved glass tube under a
    rate-of-turn pointer."""
    tb = [kit.box(f"{name}_c", (0, 0, 0.0055), (0.1180, 0.0760, 0.0110),
                  kit.mat("case"), bevel=0.0018)]
    tb.append(kit.box(f"{name}_fa", (0, 0, 0.0122), (0.1050, 0.0630, 0.0035),
                      kit.mat("ivory"), bevel=0.0006))
    arc = []
    for j in range(13):
        u = -1.0 + 2.0 * j / 12.0
        arc.append((u * 0.0420, -0.0155 + 0.0105 * (u * u), 0.0158))
    tb.append(kit.sweep(f"{name}_tube", arc, 0.0058, kit.mat("glass"),
                        sections=8))
    tb.append(kit.sphere(f"{name}_ball", (0.0072, -0.0152, 0.0158), 0.0042,
                         kit.mat("steel"), seg=14, ring=9))
    for j, sx in enumerate((-1, 1)):
        tb.append(kit.box(f"{name}_ix_{j}", (sx * 0.0068, -0.0152, 0.0146),
                          (0.0014, 0.0130, 0.0012), ink))
    for j in range(7):
        a = math.radians(-36 + 12.0 * j)
        rr = 0.0250
        tb.append(kit.box(f"{name}_tk_{j}",
                          (rr * math.sin(a), 0.0075 + rr * math.cos(a),
                           0.0142), (0.0016, 0.0062, 0.0012), ink,
                          rot=(0, 0, -a)))
    pa = math.radians(9.0)
    tb.append(kit.box(f"{name}_ndl",
                      (0.0100 * math.sin(pa), 0.0075 + 0.0100 * math.cos(pa),
                       0.0150), (0.0026, 0.0210, 0.0016), ink,
                      rot=(0, 0, -pa)))
    tb.append(kit.cyl(f"{name}_hub", (0.0, 0.0075, 0.0154), 0.0040, 0.0026,
                      br, verts=12))
    tb += kit.bez_frame(f"{name}_bz", 0.0, 0.0, 0.1180, 0.0760, 0.0110,
                        0.0190, br, bar=0.0060)
    tb.append(kit.box(f"{name}_gl", (0, 0, 0.0175), (0.1060, 0.0640, 0.0026),
                      kit.mat("glass")))
    tb.append(kit.text(f"{name}_l", "TURN & BANK", 0.0068, ink,
                       (0.0, -0.0272, 0.0136)))
    return tb


def _d1_chrono(name, br, ink, R=0.0660):
    """The master clock: an engraved 24-hour outer ring, a 12-hour inner
    chapter, hour and minute hands and a sweep-seconds sub-dial."""
    ch = [kit.cyl(f"{name}_can", (0, 0, 0.010), R * 0.92, 0.020,
                  kit.mat("case"), verts=30, bevel=0.0015, smooth=False)]
    ch.append(kit.cyl(f"{name}_face", (0, 0, 0.0202), R * 0.84, 0.0040,
                      kit.mat("ivory"), verts=36, smooth=False))
    ch.append(kit.tube(f"{name}_ring", (0, 0, 0.0226), R * 0.840, R * 0.700,
                       0.0022, kit.mat("ebonite"), verts=36))
    for j in range(24):
        a = math.radians(360.0 * j / 24.0)
        rr = R * 0.775
        ch.append(kit.box(f"{name}_tk_{j}",
                          (rr * math.sin(a), rr * math.cos(a), 0.0240),
                          (R * 0.030, R * (0.10 if j % 2 else 0.15), 0.0012),
                          kit.mat("paper"), rot=(0, 0, -a)))
        if j % 3 == 0:
            rr = R * 0.640
            ch.append(kit.text(f"{name}_n_{j}", f"{j:02d}", R * 0.115,
                               kit.mat("paper"),
                               (rr * math.sin(a), rr * math.cos(a), 0.0240)))
    for j in range(12):
        a = math.radians(360.0 * j / 12.0)
        rr = R * 0.560
        ch.append(kit.box(f"{name}_m_{j}",
                          (rr * math.sin(a), rr * math.cos(a), 0.0230),
                          (R * 0.026, R * 0.070, 0.0012), ink, rot=(0, 0, -a)))
    ch.append(kit.cyl(f"{name}_sd", (0.0, -0.0235, 0.0232), 0.0155, 0.0018,
                      kit.mat("paper"), verts=24, smooth=False))
    ch.append(kit.tube(f"{name}_sdr", (0.0, -0.0235, 0.0238), 0.0158, 0.0140,
                       0.0016, br, verts=24))
    for j in range(4):
        a = math.radians(90.0 * j)
        rr = 0.0116
        ch.append(kit.box(f"{name}_sdt_{j}",
                          (rr * math.sin(a), -0.0235 + rr * math.cos(a),
                           0.0244), (0.0013, 0.0042, 0.0010), ink,
                          rot=(0, 0, -a)))
    sa = math.radians(214.0)
    ch.append(kit.box(f"{name}_sdn",
                      (0.0056 * math.sin(sa), -0.0235 + 0.0056 * math.cos(sa),
                       0.0248), (0.0012, 0.0122, 0.0010), ink,
                      rot=(0, 0, -sa)))
    for j, (ang, ln, wd) in enumerate(((-64.0, R * 0.44, 0.0044),
                                       (128.0, R * 0.66, 0.0030))):
        a = math.radians(ang)
        ch.append(kit.box(f"{name}_hand_{j}",
                          ((ln / 2) * math.sin(a), (ln / 2) * math.cos(a),
                           0.0252 + j * 0.0012), (wd, ln, 0.0014), ink,
                          rot=(0, 0, -a)))
    ch.append(kit.cyl(f"{name}_hub", (0, 0, 0.0276), 0.0050, 0.0030, br,
                      verts=14))
    ch.append(kit.text(f"{name}_l", "SHIP TIME", 0.0080, ink,
                       (0.0, 0.0300, 0.0240)))
    ch += _bezel(name, (0, 0, 0.0182), R, bez_h=0.0086, screws=4)
    return ch


def _d1(P, made):
    """Attitude control, gyros, master clock.  Sits 6 px to FMM's right, so per
    plan section 4 it gets NO outer brass frame -- it reads as a RECESS in the
    dash face (dark kerb, hull-grey ground) and FMM's brass frame stays unique.

    Built in two blocks around column 0 (see the D1_WING / D1_MAIN note above).

    WING  (-33.0..-29.7): artificial horizon over a rate-of-climb, two bat
                          toggles, one engraved nameplate.
    MAIN  (-24.3..-17.0): turn-and-bank with a real steel ball in a curved
                          glass tube, the 24-hour chronometer, four UNLIT
                          annunciator lenses, six bat toggles, one nameplate.

    Four instruments, eight toggles, four annunciators, two nameplates and
    rivet rows down every cheek -- the plan's spec, rearranged around a column
    it did not know was there.  Zero lit lamps.
    """
    out = []
    br, ink = kit.mat("brass"), kit.mat("ink")

    # =============================================================== WING
    wa0, wa1 = D1_WING
    wc = (wa0 + wa1) / 2.0
    _d1_recess(P, made, out, "w", wa0, wa1)

    loc, eul = slots.dash(P, wc, 0.725, lift=0.012)
    f = kit.frame_empty("dr_d1_ahf", loc, eul)
    made.append(f)
    _put(f, _d1_horizon("dr_d1_ah", br, ink), out)
    loc, eul = slots.dash(P, wc, 0.545, lift=0.012)
    f = kit.frame_empty("dr_d1_ahlf", loc, eul)
    made.append(f)
    _put(f, kit.stencil("dr_d1_ahl", "HORIZON", (0, 0, 0), 0.0088, m=ink), out)

    loc, eul = slots.dash(P, wc, 0.470, lift=0.012)
    f = kit.frame_empty("dr_d1_rcf", loc, eul)
    made.append(f)
    _put(f, kit.gauge("dr_d1_rc", (0, 0, 0), r=0.0420, ticks=9,
                      sweep_deg=300.0, needle_deg=-24.0, label="M/SEC",
                      sub="CLIMB", depth=0.018, bezel_screws=3), out)

    _d1_switch_strip(P, made, out, "w", wa0 + 0.25, wa1 - 0.25,
                     ("GYRO", "ERCT"), (20.0, -22.0), (wc - 0.62, wc + 0.62))

    loc, eul = slots.dash(P, wc, 0.130, lift=0.012)
    f = kit.frame_empty("dr_d1_np0f", loc, eul)
    made.append(f)
    _put(f, kit.nameplate("dr_d1_np0", "FLIGHT & TRIM", (0, 0, 0), h=0.024,
                          size=0.0105), out)

    # =============================================================== MAIN
    ma0, ma1 = D1_MAIN
    mc = (ma0 + ma1) / 2.0
    _d1_recess(P, made, out, "m", ma0, ma1)

    loc, eul = slots.dash(P, -22.33, 0.700, lift=0.012)
    f = kit.frame_empty("dr_d1_tbf", loc, eul)
    made.append(f)
    _put(f, _d1_turnbank("dr_d1_tb", br, ink), out)

    loc, eul = slots.dash(P, -18.93, 0.700, lift=0.012)
    f = kit.frame_empty("dr_d1_chf", loc, eul)
    made.append(f)
    _put(f, _d1_chrono("dr_d1_ch", br, ink), out)

    for i, (ang, leg) in enumerate(((-23.15, "GYRO"), (-21.48, "TRIM"),
                                    (-19.82, "PITOT"), (-18.15, "A/P"))):
        loc, eul = slots.dash(P, ang, 0.500, lift=0.012)
        f = kit.frame_empty(f"dr_d1_anf_{i}", loc, eul)
        made.append(f)
        _put(f, _annunciator(f"dr_d1_an_{i}", (0, 0, 0), 0.064, 0.024, leg,
                             False, "amber", depth=0.010, text_size=0.0080),
             out)

    _d1_switch_strip(P, made, out, "m", ma0 + 0.30, ma1 - 0.30,
                     ("CAGE", "TRM", "YAW", "ROLL", "PTCH", "MSTR"),
                     (18.0, 21.0, -19.0, 22.0, 18.0, -20.0),
                     (-23.51, -22.37, -21.22, -20.08, -18.93, -17.79))

    loc, eul = slots.dash(P, mc - 0.45, 0.130, lift=0.012)
    f = kit.frame_empty("dr_d1_np1f", loc, eul)
    made.append(f)
    _put(f, kit.nameplate("dr_d1_np1", "ATTITUDE REF", (0, 0, 0), h=0.024,
                          size=0.0105), out)
    loc, eul = slots.dash(P, ma0 + 0.85, 0.205, lift=0.012)
    f = kit.frame_empty("dr_d1_wtf", loc, eul)
    made.append(f)
    _put(f, kit.warn_triangle("dr_d1_wt", (0, 0, 0), 0.026), out)
    loc, eul = slots.dash(P, -17.85, 0.130, lift=0.012)
    f = kit.frame_empty("dr_d1_insf", loc, eul)
    made.append(f)
    _put(f, kit.inspection_stamp("dr_d1_ins", (0, 0, 0), "D-1", r=0.011), out)

    made.extend(out)


# ==================================================================== entry
def add_tier2(P, mats):
    """Add tier 2's dressing geometry to the CURRENT scene.

    P    : shell PARAMS (already built)
    mats : {"brass":..., "hull":..., "hull_d":...}  -- the shell's own hero
           materials.  Dressing does NOT use them; `kit.mat()` supplies the
           desaturated set from DRESSING_PLAN.md section 5.1.
    Returns: {"dress": [list of created objects]}
    """
    made = []
    _f1(P, made)          # 6  atmosphere plant       -- bottom-left anchor
    _f5(P, made)          # 7  main bus board         -- bottom-right anchor
    _h1(P, made)          # 8  caution annunciator    -- top-centre
    _d1(P, made)          # 9  flight & trim panel    -- beside FMM

    meshes = [o for o in made if o.type == 'MESH']
    em = kit.emissive_area(meshes)
    print(f"TIER2: {len(meshes)} meshes, {len(made) - len(meshes)} empties; "
          f"emissive area {em:.6f} m2 "
          f"(budget for ALL dressing is 0.0518 m2)")
    return {"dress": made}


if __name__ == "__main__":
    P = dict(shell.PARAMS)
    P["exterior"] = 1
    shell.build(P)
    add_tier2(P, {"brass": bpy.data.materials["brass"],
                  "hull": bpy.data.materials["hull"],
                  "hull_d": bpy.data.materials["hull_d"]})
    bpy.context.scene.render.filepath = os.path.join(HERE, "out",
                                                     "_tier2_only.png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", bpy.context.scene.render.filepath)
