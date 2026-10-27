"""
Set-dressing TIER 3 -- "fill out".

DRESSING_PLAN.md section 6, tier 3, items 10-14:

  10. F2  hull integrity mimic          fascia -28.5, z 0.20-0.66, 0.32 x 0.46
  11. D3  thrust & attitude-jet quadrant dash   +22.0, t 0.06-0.86, 0.49 x 0.50
  12. F4  water & reclamation           fascia +24.5, z 0.34-0.66, 0.28 x 0.32
  13. P1  coolant riser                 pillar 0, z 1.76-1.93 / 1.99-2.11
  14. P2  rectifier tube cage           pillar 1, same split

Three things the plan's section 3 tables do not say, all found by rendering the
composite with and without this tier and differencing the plates
(`dressing/verify3.py` does exactly that and prints the numbers):

  * COLUMN 1 CROSSES D3.  The dash face meets the columns at t 0.42, so the
    +27.0 deg column stands in the outboard third of a panel centred on +22.0.
    The plate keeps the planned footprint and runs behind the column; every
    instrument is laid inboard of local X +0.10.  See D3_XMAX.
  * P2 IS INVISIBLE IN THE MAIN PLATE, and P1's upper unit nearly so.  The
    shell's own overhead console at +24 deg (`shell.OVERHEADS[3]`, r 0.78,
    w 0.44, drop 0.26) sits 0.25 m nearer the camera than column 1 and covers
    it from z 1.78 to the top collar; on column 0 the -29 deg pod does the same
    from z 1.86 up.  Measured contribution to the plate: P1a 1832 px, P1b 498,
    P2a 334, P2b 0.  Both are built to spec anyway -- they are the plan's
    shared mount, they are correct as ship structure, and they are what the
    OTA / IPM / MQB / DNSM close-up BACKGROUNDS look at (plan section 0,
    consequence 2).  If the aggregator wants P2 in the wide shot, the fix is
    in shell.py's overhead rig, not here.
  * The panel angular spans in section 3 are half-angles at the MID radius.
    A dash panel's NEAR corners sit at a smaller radius and flare ~0.5 deg
    wider; D3 is 0.492 m rather than 0.500 m so its extreme corners land inside
    the reserved band and the KVS gutter rather than 0.04 deg over.

Geometry sharing the plan asks for, and that this file actually does:

  * `_pillar_unit()` IS the shared P1/P2 mount -- the same two-unit split, the
    same four wrapping collars, the same 30 mm stand-off plate. It is called
    four times; only the `payload` callback differs (glass coolant tubes vs.
    vacuum tubes). That is the plan's `pillar_cap(payload)`.
  * F2's diagram is `kit.mimic_strip()` -- the same helper F5 uses for the bus
    single-line, here extruding the hull plan-view outline.
  * F4's and P1's sight glasses are `kit.sightglass()` at two lengths, the same
    helper F1 uses.
  * F4's totaliser is `kit.flipdigit()` x5, copied from OTA.

Contract (DRESSING_BRIEF.md): geometry only. No render, no camera, no scene
settings, NO LIGHTS, no manifest, no glow mask, no hotspots.

    from dressing import tier3
    tier3.add_tier3(P, mats)   ->  {"dress": [objects]}
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
    from dressing import kit, slots_ext                          # noqa: F401
except ImportError:                                              # pragma: no cover
    import kit                                                   # noqa: F401
    import slots_ext                                             # noqa: F401


# --------------------------------------------------------------- placement
CR = 0.075                       # column radius == P["pillar_radius"]

# F2 -- fascia -28.5 deg, z 0.20..0.66, 0.32 x 0.46.
# Right edge lands at -24.53 deg against LOG's -24.0: the plan's 0.5 deg, and
# 0.32 m is therefore a HARD width limit, not a target.  Nothing on this panel
# may grow sideways.
F2_ANG, F2_Z = -28.5, 0.43
F2_W, F2_H = 0.320, 0.460
# plan section 4 item 5: the ~120x100 px wedge below F2 gets F2's own skirt
# extended downward rather than a 22nd object.
F2_SKIRT = 0.130

# D3 -- dash +22.0 deg, t 0.06..0.86 (0.508 m of face), 0.50 wide, 0.09 proud.
# Left edge +16.49 against the RESERVED band's +16.0; right edge +27.51
# against KVS's +28.4.  Same hard-limit rule as F2.
D3_ANG, D3_T = 22.0, 0.46
# 0.492, not the plan's 0.500: the plan's +/-5.51 deg is the half-angle at the
# MID radius (2.592).  The near corners sit at r 2.364 and flare to +/-6.04 deg,
# which puts the left corner 0.04 deg inside the reserved centre band.  0.492
# lands the extreme corners at +/-5.97 deg -> +16.03 .. +27.97, inside both
# gutters.  8 mm off the spec; the alternative is closing a gutter (section 7.9).
D3_W, D3_H = 0.492, 0.500
# COLUMN 1 CROSSES D3.  The dash face meets the column at t 0.42 and the column
# (axis +27.0 deg, r 0.075, plus tier 1's P3b skirt at r 0.106) hides camera
# angles +23.8..+28.3, i.e. every part of this panel outboard of local X +0.11.
# Verified by rendering with and without tier 3 and differencing the plates.
# The plate itself is left at full width -- a console running behind a
# structural column is correct, and it holds the footprint the plan reserved --
# but every INSTRUMENT is laid inboard of X +0.10.
D3_XMAX = 0.100

# F4 -- fascia +24.5 deg, z 0.34..0.66.  Left edge +21.02 against MTA's +20.
F4_ANG, F4_Z = 24.5, 0.50
F4_W, F4_H = 0.280, 0.320

# P1/P2 -- the shared mount.  The shell's own structural collar sits at
# z 1.94..1.98, radius 0.1005 (prad * 1.34): the two units split AROUND it and
# the collar becomes the mounting band.  The shell's top collar starts at
# z 2.1175, so the upper unit stops at 2.11 with 7.5 mm to spare.
PU_A = (1.760, 1.930)
PU_B = (1.990, 2.110)
PU_W = 0.140                     # plate width (OTA's width problem: a flat
                                 # plate this wide would bury its edges 19 mm
                                 # inside a 0.075 column, hence the stand-off)
PU_STAND = 0.030                 # OTA's 30 mm stand-off, off the column SKIN
PU_RIN, PU_ROUT = 0.078, 0.094   # collar bore vs the 0.075 column


# --------------------------------------------------------- local materials
# Two additions to `kit.MAT_SPEC`'s palette, made HERE rather than in kit.py
# (which is shared and read-only to this tier).  Both follow DRESSING_PLAN 5.1's
# rule for anything not tabulated -- same hue, lower saturation and value -- and
# both exist because section 5.4's assertions are numeric:
#
#   tier 3 alone, before:  meanS 0.166 / meanV 0.421  vs limits 0.145 / 0.394
#
#   dr_gunmetal   blued steel.  kit's `steel` is the right hue but still a
#                 bright metal; at the area a set of instrument panels uses for
#                 frames, rails and guards it costs ~4% of the value budget.
#   dr_panelface  the panel grounds.  kit's `hull_l` is 19% ABOVE the shell's
#                 own fascia (`hull`, 0.052/0.056/0.066); this sits 8% below it,
#                 i.e. inside section 5.2's "+/-12% of local fascia luminance"
#                 value floor, where hull_l was not.
def _mat(name, base, metal, rough):
    m = bpy.data.materials.get(name)
    return m if m is not None else shell.material(name, base, metal, rough)


def gunmetal():
    return _mat("dr_gunmetal", (0.128, 0.136, 0.150, 1), 0.85, 0.54)


def panelface():
    return _mat("dr_panelface", (0.048, 0.051, 0.060, 1), 0.15, 0.54)


# ============================================================ 10. F2 mimic
# The ship in plan view, nose up, as raised brass strip on black bakelite.
# Authored in mimic-field-local metres; the field is 0.26 x 0.215 so the hull
# is drawn 0.148 wide and 0.196 long inside it.
_HULL_HALF = [
    (0.000, 0.098), (0.026, 0.066), (0.036, 0.018), (0.036, -0.038),
    (0.062, -0.058), (0.066, -0.080), (0.030, -0.080), (0.026, -0.098),
]


def _hull_outline():
    """Closed plan-view outline of the ship, mirrored about x = 0."""
    right = list(_HULL_HALF)
    left = [(-x, y) for (x, y) in reversed(right[1:-1])]
    return right + [(-right[-1][0], right[-1][1])] + left


# fourteen compartment lamps, laid inside the outline.  Deliberately not on a
# regular grid (plan section 5.3: perfect symmetry is the amateur-3D tell).
_F2_LAMPS = [
    (-0.014, 0.070), (0.014, 0.070),
    (-0.020, 0.040), (0.020, 0.040),
    (-0.024, 0.006), (0.000, 0.010), (0.024, 0.006),
    (-0.024, -0.026), (0.000, -0.022), (0.024, -0.026),
    (-0.050, -0.062), (-0.017, -0.058), (0.017, -0.058), (0.050, -0.062),
]
# 2 of 14 lit, and dimly (plan section 5.2 names this exact ratio for F2)
_F2_LIT = (5, 11)


def _f2(P, made):
    br, ink = kit.mat("brass"), kit.mat("ink")
    bd = gunmetal()
    # `bd` is the STRUCTURAL rank: frames, rails, guards, eyelets, rivets.
    # Steel, not brass.  DRESSING_PLAN 5.4 measured tier 3 alone at meanS 0.166
    # against a 0.145 limit, and a controlled swap (all brass -> steel) put it
    # at 0.089, so brass AREA is the entire saturation story here -- brass_dk
    # does not help, because it has the same hue ratio, only less value.
    # Bright brass is therefore rationed to the things that are ABOUT brass:
    # the mimic strip, the nameplates, the lever knobs, the detent plate, the
    # gauge bezels and the column collars.
    loc, eul = slots.fascia(P, F2_ANG, z=F2_Z)
    root = kit.frame_empty("dr_f2_root", loc, eul)
    made.append(root)
    out = []
    hw, hh = F2_W / 2, F2_H / 2

    # ---- panel body, sitting as a recess in the fascia rather than a slab
    out.append(kit.box("dr_f2_panel", (0.0, 0.0, 0.009), (F2_W, F2_H, 0.018),
                       panelface(), bevel=0.0055))
    out += kit.bez_frame("dr_f2_bez", 0.0, 0.0, F2_W, F2_H, 0.012, 0.026, bd,
                         bar=0.0090)
    for k, sx in enumerate((-1, 1)):
        out += kit.rivet_row(f"dr_f2_rv_{k}",
                             (sx * (hw - 0.0125), -hh + 0.020, 0.020),
                             (sx * (hw - 0.0125), hh - 0.020, 0.020), 11,
                             r=0.0032, m=bd)

    # ---- the mimic field: black bakelite ground behind a brass frame
    fx, fy = 0.0, 0.070
    fw, fh = 0.262, 0.216
    out.append(kit.box("dr_f2_field", (fx, fy, 0.021), (fw, fh, 0.008),
                       kit.mat("ebonite"), bevel=0.0016))
    out += kit.bez_frame("dr_f2_fieldbez", fx, fy, fw + 0.010, fh + 0.010,
                         0.018, 0.030, br, bar=0.0052)

    # the hull outline itself -- the shared mimic_strip helper (F5's is the bus
    # single-line diagram; this one is the hull)
    path = [(fx + x, fy + y) for (x, y) in _hull_outline()]
    out += kit.mimic_strip("dr_f2_hull", path, width=0.0052, z=0.025,
                           thickness=0.0032, closed=True, m=br)
    # transverse bulkheads + the spine, so it reads as compartments
    for k, (y, x1) in enumerate(((0.066, 0.026), (0.018, 0.036),
                                 (-0.038, 0.036), (-0.080, 0.066))):
        out += kit.mimic_strip(f"dr_f2_bhd_{k}",
                               [(fx - x1, fy + y), (fx + x1, fy + y)],
                               width=0.0034, z=0.025, thickness=0.0022, m=br)
    out += kit.mimic_strip("dr_f2_spine",
                           [(fx, fy + 0.090), (fx, fy - 0.092)],
                           width=0.0026, z=0.025, thickness=0.0018,
                           m=kit.mat("brass_dk"))

    # fourteen compartment lamps -- twelve dark, two dim amber
    for i, (lx, ly) in enumerate(_F2_LAMPS):
        out += kit.lampcell(f"dr_f2_lamp_{i}", (fx + lx, fy + ly, 0.027),
                            w=0.0165, h=0.0145, lit=(i in _F2_LIT),
                            kind="amber", depth=0.0075, round_lens=True,
                            frame=False)
        # a deep brass eyelet: the lens top sits at 0.0332, so a 0.005-thick
        # ring at 0.0330 shades its rim and stops a lit cell blowing to a
        # white dot at 8 px across.
        out.append(kit.tube(f"dr_f2_lampring_{i}", (fx + lx, fy + ly, 0.0330),
                            0.0088, 0.0058, 0.0050, bd, verts=12))

    out += kit.stencil("dr_f2_fieldtx", "HULL  INTEGRITY",
                       (fx, fy + fh / 2 - 0.014, 0.0305), 0.0125,
                       m=kit.mat("ivory"))
    out += kit.stencil("dr_f2_fieldsub", "PLAN  VIEW  -  FRAME 6 FWD",
                       (fx, fy - fh / 2 + 0.011, 0.0305), 0.0068,
                       m=kit.mat("paper"))

    # ---- SECTION 1-6 rotary selector, lower left
    sx, sy = -0.086, -0.128
    out.append(kit.cyl("dr_f2_seldial", (sx, sy, 0.020), 0.042, 0.004,
                       kit.mat("slate"), verts=32, smooth=False, bevel=0.0010))
    out.append(kit.tube("dr_f2_selring", (sx, sy, 0.0225), 0.0435, 0.0395,
                        0.005, bd, verts=32))
    for i in range(6):
        a = math.radians(-125 + 50.0 * i)
        rr = 0.0335
        out.append(kit.box(f"dr_f2_seltk_{i}",
                           (sx + rr * math.sin(a), sy + rr * math.cos(a),
                            0.0228), (0.0032, 0.0110, 0.0018), ink,
                           rot=(0, 0, -a)))
        out.append(kit.text(f"dr_f2_seln_{i}", str(i + 1), 0.0092, ink,
                            (sx + 0.0250 * math.sin(a),
                             sy + 0.0250 * math.cos(a), 0.0232)))
    # knurled bakelite knob with a brass pointer
    out.append(kit.cyl("dr_f2_selknob", (sx, sy, 0.0285), 0.0182, 0.0140,
                       kit.mat("ebonite"), verts=20, smooth=False,
                       bevel=0.0010))
    out.append(kit.cyl("dr_f2_selcap", (sx, sy, 0.0362), 0.0132, 0.0034, br,
                       verts=20, bevel=0.0008))
    pa = math.radians(-25.0)
    out.append(kit.box("dr_f2_selptr",
                       (sx + 0.0210 * math.sin(pa), sy + 0.0210 * math.cos(pa),
                        0.0368), (0.0052, 0.0300, 0.0026), br, rot=(0, 0, -pa),
                       bevel=0.0006))
    out += kit.stencil("dr_f2_seltx", "SECTION", (sx, sy - 0.056, 0.020),
                       0.0105)

    # ---- red T-handle pull marked SEAL, on a short brass chain.
    # Deliberately NOT a break-glass: LOG already owns that gesture.  One of
    # only three painted-red elements in the whole dressing set.
    tx, ty = 0.088, -0.118
    out.append(kit.box("dr_f2_tguard", (tx, ty, 0.019), (0.062, 0.062, 0.008),
                       panelface(), bevel=0.0022))
    out.append(kit.revolve("dr_f2_tboss",
                           [(0.0180, 0.0), (0.0180, 0.006), (0.0135, 0.009),
                            (0.0135, 0.016)], bd, center=(tx, ty, 0.023),
                           verts=18))
    out.append(kit.cyl("dr_f2_tshaft", (tx, ty, 0.046), 0.0062, 0.030, bd,
                       verts=12))
    out.append(kit.cyl("dr_f2_tbar", (tx, ty, 0.0615), 0.0088, 0.052,
                       kit.mat("red_paint"), rot=(0, math.pi / 2, 0), verts=14,
                       bevel=0.0012))
    for k, s in enumerate((-1, 1)):
        out.append(kit.sphere(f"dr_f2_tball_{k}", (tx + s * 0.026, ty, 0.0615),
                              0.0100, kit.mat("red_paint"), seg=14, ring=8))
    out += kit.stencil("dr_f2_ttx", "SEAL", (tx, ty - 0.040, 0.024), 0.0130,
                       m=kit.mat("ivory"))
    # the chain: alternating link planes so it reads as chain, not as a wire
    out.append(kit.tube("dr_f2_teye", (tx - 0.046, ty + 0.020, 0.026), 0.0062,
                        0.0040, 0.0030, bd, verts=12))
    for i in range(7):
        t = i / 6.0
        cx = tx - 0.046 + t * 0.042
        cy = ty + 0.020 - 0.030 * math.sin(t * math.pi) - t * 0.004
        out.append(kit.tube(f"dr_f2_chain_{i}", (cx, cy, 0.028), 0.0044,
                            0.0028, 0.0022, bd,
                            rot=(0, 0, 0) if i % 2 == 0 else (0, math.pi / 2,
                                                              0),
                            verts=10))

    # ---- nameplate + signage
    out += kit.nameplate("dr_f2_pl", "DAMAGE  CONTROL", (0.0, -0.203, 0.020),
                         w=0.176, h=0.026, size=0.0106, sub="MIMIC  PANEL  A")
    out += kit.inspection_stamp("dr_f2_is", (-0.128, -0.198, 0.021), "H2",
                                r=0.0092)
    out += kit.warn_triangle("dr_f2_wt", (0.132, -0.196, 0.021), 0.024)

    # ---- skirt into the dead wedge below (plan section 4 item 5)
    sy0 = -hh - F2_SKIRT / 2
    out.append(kit.box("dr_f2_skirt", (0.0, sy0, 0.006),
                       (F2_W - 0.030, F2_SKIRT, 0.012), panelface(),
                       bevel=0.0040))
    out.append(kit.box("dr_f2_skirtrail", (0.0, -hh + 0.002, 0.014),
                       (F2_W - 0.020, 0.010, 0.016), bd, bevel=0.0022))
    out += kit.louvre_row("dr_f2_skirtlv", (-0.060, sy0 + 0.006, 0.012),
                          0.088, 4, fin_h=0.008, depth=0.010)
    out += kit.stencil("dr_f2_skirttx", "FRAME 11", (0.070, sy0 + 0.014,
                                                     0.013), 0.0175)
    out += kit.stencil("dr_f2_skirtsub", "SECT 4", (0.070, sy0 - 0.018, 0.013),
                       0.0125, worn=True)
    out += kit.rivet_row("dr_f2_skirtrv", (-0.128, sy0 - 0.040, 0.013),
                         (0.128, sy0 - 0.040, 0.013), 9, r=0.0030, m=bd)

    kit.parent_to(out, root)
    made.extend(out)


# ================================================ 11. D3 thrust quadrant
def _d3(P, made):
    br, ink, st = kit.mat("brass"), kit.mat("ink"), kit.mat("steel")
    bd = gunmetal()
    # `bd` is the STRUCTURAL rank: frames, rails, guards, eyelets, rivets.
    # Steel, not brass.  DRESSING_PLAN 5.4 measured tier 3 alone at meanS 0.166
    # against a 0.145 limit, and a controlled swap (all brass -> steel) put it
    # at 0.089, so brass AREA is the entire saturation story here -- brass_dk
    # does not help, because it has the same hue ratio, only less value.
    # Bright brass is therefore rationed to the things that are ABOUT brass:
    # the mimic strip, the nameplates, the lever knobs, the detent plate, the
    # gauge bezels and the column collars.
    loc, eul = slots.dash(P, D3_ANG, D3_T)
    root = kit.frame_empty("dr_d3_root", loc, eul)
    made.append(root)
    out = []
    hw, hh = D3_W / 2, D3_H / 2

    # ---- sub-plate let into the dash face.  Low brass rails on the cheeks and
    # the near edge only: a full bezel here would merge D3 with KVS 0.9 deg
    # away, and KVS's own frame has to stay the distinctive one.
    out.append(kit.box("dr_d3_plate", (0.0, 0.0, 0.007), (D3_W, D3_H, 0.014),
                       panelface(), bevel=0.0050))
    for k, sx in enumerate((-1, 1)):
        out.append(kit.box(f"dr_d3_rail_{k}", (sx * (hw - 0.011), 0.0, 0.017),
                           (0.022, D3_H - 0.010, 0.008), bd, bevel=0.0022))
        out += kit.rivet_row(f"dr_d3_rv_{k}",
                             (sx * (hw - 0.011), -hh + 0.024, 0.021),
                             (sx * (hw - 0.011), hh - 0.024, 0.021), 12,
                             r=0.0034, m=bd)
    out.append(kit.box("dr_d3_lip", (0.0, -hh + 0.010, 0.017),
                       (D3_W - 0.014, 0.020, 0.009), bd, bevel=0.0024))

    # ---- the quadrant proper: a cast slotted housing standing proud of the
    # rake.  This is the one dressing prop with real Z-depth; it is what stops
    # the right dash reading as a flat sticker.  Pushed inboard so it clears
    # column 1 (see D3_XMAX).
    qx, qy = -0.140, 0.052
    qw, qd, qz = 0.190, 0.190, 0.066
    out.append(kit.box("dr_d3_case", (qx, qy, 0.014 + qz / 2),
                       (qw, qd, qz), panelface(), bevel=0.0055))
    # the top plate is the single largest flat brass area in the tier: a
    # machined-and-blackened plate, not a polished one.
    out.append(kit.box("dr_d3_casetop", (qx, qy, 0.014 + qz + 0.005),
                       (qw - 0.006, qd - 0.006, 0.010), bd, bevel=0.0030))
    top = 0.014 + qz + 0.010
    for k, sx in enumerate((-1, 1)):
        out += kit.rivet_row(f"dr_d3_qrv_{k}",
                             (qx + sx * (qw / 2 - 0.009), qy - qd / 2 + 0.014,
                              0.014 + qz * 0.5),
                             (qx + sx * (qw / 2 - 0.009), qy + qd / 2 - 0.014,
                              0.014 + qz * 0.5), 6, r=0.0030, m=bd)
    out += kit.louvre_row("dr_d3_qlv", (qx, qy + qd / 2 - 0.012, 0.020),
                          qw - 0.030, 3, fin_h=0.007, depth=0.009)
    # the housing's pilot-facing cheek is unlit and was reading as a black
    # rectangle (plan section 5.2: a black hole reads as a missing asset).
    # Two brass rails, a stencil and a rivet row put detail into it.
    fy_ = qy - qd / 2 - 0.0035
    for k, zz in enumerate((0.022, 0.014 + qz - 0.008)):
        out.append(kit.box(f"dr_d3_qface_{k}", (qx, fy_, zz),
                           (qw - 0.014, 0.007, 0.011), bd, bevel=0.0016))
    out.append(kit.text("dr_d3_qtx", "R C S", 0.0165, kit.mat("ivory"),
                        (qx - 0.030, fy_ - 0.0015, 0.014 + qz * 0.50),
                        rot=(math.pi / 2, 0, 0)))
    out.append(kit.text("dr_d3_qtx2", "BANK 2", 0.0110, kit.mat("paper"),
                        (qx + 0.052, fy_ - 0.0015, 0.014 + qz * 0.50),
                        rot=(math.pi / 2, 0, 0)))
    for k in range(7):
        out.append(kit.sphere(f"dr_d3_qrvf_{k}",
                              (qx - 0.076 + k * 0.0253, fy_ - 0.0030,
                               0.014 + qz * 0.86), 0.0030, bd,
                              scale=(1, 0.55, 1), seg=10, ring=6))

    # three milled slots and three brass levers on a common shaft
    lev = ((-0.056, 22.0, 0.098), (0.000, 40.0, 0.104), (0.056, 57.0, 0.094))
    out.append(kit.cyl("dr_d3_shaft", (qx, qy - 0.010, 0.014 + qz * 0.55),
                       0.0075, qw - 0.030, st, rot=(0, math.pi / 2, 0),
                       verts=12))
    for i, (dx, deg, ln) in enumerate(lev):
        out.append(kit.box(f"dr_d3_slot_{i}", (qx + dx, qy - 0.008, top),
                           (0.0105, qd * 0.60, 0.0035), kit.mat("ebonite")))
        th = math.radians(deg)
        d = Vector((0.0, -math.sin(th), math.cos(th)))
        base = Vector((qx + dx, qy - 0.010, 0.014 + qz * 0.55))
        out.append(kit.cone(f"dr_d3_lev_{i}", tuple(base + d * (ln / 2)),
                            0.0068, 0.0044, ln, br, rot=(th, 0, 0), verts=12))
        knob = base + d * (ln + 0.0128)
        out.append(kit.sphere(f"dr_d3_knob_{i}", tuple(knob), 0.0152, br,
                              seg=16, ring=10))
        out.append(kit.tube(f"dr_d3_boot_{i}",
                            tuple(base + d * (ln * 0.30)), 0.0132, 0.0072,
                            0.006, kit.mat("rubber"),
                            rot=(th + math.pi / 2, 0, 0), verts=14))

    # engraved detent plate beside the slots
    dpx = qx + 0.089
    out.append(kit.box("dr_d3_detent", (dpx, qy - 0.006, top + 0.0022),
                       (0.030, qd * 0.72, 0.0044), bd, bevel=0.0008))
    for i, body in enumerate(("RCS", "VERN", "MAIN", "LOCK")):
        yy = qy - 0.006 + (1.5 - i) * (qd * 0.72 / 4.4)
        out.append(kit.box(f"dr_d3_dtk_{i}", (dpx - 0.011, yy,
                                              top + 0.0046),
                           (0.0090, 0.0018, 0.0012), ink))
        out.append(kit.text(f"dr_d3_dtx_{i}", body, 0.0074, ink,
                            (dpx + 0.0045, yy, top + 0.0046)))

    # knurled friction wheel on the outboard flank of the housing
    wx = qx + qw / 2 + 0.008
    out.append(kit.cyl("dr_d3_fw", (wx, qy - 0.020, 0.014 + qz * 0.52),
                       0.0300, 0.0130, kit.mat("brass_dk"),
                       rot=(0, math.pi / 2, 0), verts=22, smooth=False,
                       bevel=0.0008))
    out.append(kit.cyl("dr_d3_fwhub", (wx, qy - 0.020, 0.014 + qz * 0.52),
                       0.0110, 0.0160, br, rot=(0, math.pi / 2, 0), verts=14))
    out += kit.stencil("dr_d3_fwtx", "FRICTION",
                       (wx + 0.004, qy - 0.020 - 0.038, 0.015), 0.0080)

    # ---- centre-zero galvanometer: yaw rate.  Sits in the last inboard slot
    # the column leaves free (right edge X +0.096 against D3_XMAX 0.100).
    out += kit.gauge("dr_d3_yaw", (0.038, 0.132, 0.014), r=0.0580, ticks=9,
                     needle_deg=-6.0, label="YAW RATE", sub="DEG / S",
                     depth=0.020, sweep_deg=180.0, bezel_screws=4)
    out += kit.nameplate("dr_d3_yawpl", "RATE  GYRO", (0.038, 0.052, 0.015),
                         w=0.098, h=0.019, size=0.0080, screws=False)

    # ---- a pair of guarded toggles under wire cages
    for i, (tx, deg) in enumerate(((0.008, 18.0), (0.074, -14.0))):
        out += kit.toggle(f"dr_d3_tg_{i}", (tx, -0.062, 0.014), kind="caged",
                          pos_deg=deg,
                          legend=("JET ARM", "VERN")[i], legend_w=0.034)

    # ---- signage
    out += kit.nameplate("dr_d3_pl", "THRUST  +  ATT  JETS",
                         (-0.058, -0.196, 0.015), w=0.222, h=0.026,
                         size=0.0100, sub="MANOEUVRE  QUADRANT")
    out += kit.stencil("dr_d3_tx", "RCS  BANK  2", (-0.140, -0.122, 0.015),
                       0.0135)
    out += kit.stencil("dr_d3_tx2", "JET  ARM", (0.042, -0.124, 0.015),
                       0.0105, worn=True)
    out += kit.inspection_stamp("dr_d3_is", (0.086, -0.196, 0.016), "D3",
                                r=0.0092)
    # the outboard third of the plate is behind column 1: nothing but the
    # rail, the rivets and one stencil, so the panel reads as running BEHIND
    # the column rather than as content thrown away.
    out += kit.stencil("dr_d3_txo", "FR 15", (0.180, -0.150, 0.015), 0.0140,
                       worn=True)

    kit.parent_to(out, root)
    made.extend(out)


# ============================================== 12. F4 water & reclamation
_F4_CELLS = ("PUMP", "TK A", "TK B", "FILT", "WASTE", "RECL")
_F4_LIT = 3                      # one in six -- the 1-in-5 rule, rounded down


def _f4(P, made):
    br, ink = kit.mat("brass"), kit.mat("ink")
    bd = gunmetal()
    # `bd` is the STRUCTURAL rank: frames, rails, guards, eyelets, rivets.
    # Steel, not brass.  DRESSING_PLAN 5.4 measured tier 3 alone at meanS 0.166
    # against a 0.145 limit, and a controlled swap (all brass -> steel) put it
    # at 0.089, so brass AREA is the entire saturation story here -- brass_dk
    # does not help, because it has the same hue ratio, only less value.
    # Bright brass is therefore rationed to the things that are ABOUT brass:
    # the mimic strip, the nameplates, the lever knobs, the detent plate, the
    # gauge bezels and the column collars.
    loc, eul = slots.fascia(P, F4_ANG, z=F4_Z)
    root = kit.frame_empty("dr_f4_root", loc, eul)
    made.append(root)
    out = []
    hw, hh = F4_W / 2, F4_H / 2

    out.append(kit.box("dr_f4_panel", (0.0, 0.0, 0.009), (F4_W, F4_H, 0.018),
                       panelface(), bevel=0.0055))
    out += kit.bez_frame("dr_f4_bez", 0.0, 0.0, F4_W, F4_H, 0.012, 0.026, bd,
                         bar=0.0085)
    for k, sx in enumerate((-1, 1)):
        out += kit.rivet_row(f"dr_f4_rv_{k}",
                             (sx * (hw - 0.0115), -hh + 0.016, 0.020),
                             (sx * (hw - 0.0115), hh - 0.016, 0.020), 8,
                             r=0.0030, m=bd)

    # ---- five-digit flip-dot totaliser (OTA's digit geometry, via the kit)
    out.append(kit.box("dr_f4_totbase", (-0.020, 0.104, 0.020),
                       (0.130, 0.042, 0.006), kit.mat("case"), bevel=0.0014))
    for i, ch in enumerate("04196"):
        out += kit.flipdigit(f"dr_f4_dig_{i}",
                             (-0.068 + i * 0.024, 0.104, 0.022), ch=ch,
                             w=0.0215, h=0.0300, m=bd)
    out += kit.stencil("dr_f4_tottx", "GALLONS", (0.086, 0.110, 0.020),
                       0.0105)
    out += kit.stencil("dr_f4_totsub", "TOTAL", (0.086, 0.092, 0.020), 0.0078,
                       worn=True)

    # ---- sight glass with float and a graduated brass scale.  Same helper as
    # F1's three columns and P1's coolant tubes, at a third length.
    out += kit.sightglass("dr_f4_sg", (-0.098, 0.000, 0.018), length=0.130,
                          r=0.0105, fill=0.58, grads=8)
    out += kit.stencil("dr_f4_sgtx", "TANK A", (-0.098, -0.088, 0.019),
                       0.0085)

    # ---- pressure gauge on a capillary line
    out += kit.gauge("dr_f4_pg", (0.062, 0.032, 0.018), r=0.0330, ticks=7,
                     redline=(88.0, 122.0), needle_deg=-52.0, label="PSI",
                     depth=0.014, bezel_screws=3)
    cap = [(0.062, 0.000, 0.026), (0.052, -0.018, 0.030),
           (0.036, -0.030, 0.030), (0.030, -0.048, 0.028)]
    out.append(kit.sweep("dr_f4_cap", cap, 0.0026, bd, sections=7))

    # ---- hand pump with a turned wooden grip.  The arm swings INBOARD: swung
    # outboard at the plan's length its grip reached +28.92 deg, over KVS's
    # +28.84 and 0.08 deg off F5's +29.0.
    px, py = 0.028, -0.062
    out.append(kit.box("dr_f4_pumpbody", (px, py, 0.020), (0.048, 0.026,
                                                           0.014),
                       panelface(), bevel=0.0022))
    out.append(kit.cyl("dr_f4_pumppin", (px - 0.020, py + 0.004, 0.032),
                       0.0052, 0.020, bd, rot=(0, math.pi / 2, 0), verts=12))
    la = math.radians(24.0)
    ln = 0.076
    d = Vector((math.cos(la), math.sin(la), 0.0))
    base = Vector((px - 0.020, py + 0.004, 0.032))
    out.append(kit.box("dr_f4_pumparm", tuple(base + d * (ln / 2)),
                       (ln, 0.0105, 0.0075), bd, rot=(0, 0, la), bevel=0.0012))
    grip = base + d * (ln + 0.012)
    out.append(kit.revolve("dr_f4_grip",
                           [(0.0064, -0.016), (0.0102, -0.010),
                            (0.0110, 0.008), (0.0086, 0.017),
                            (0.0064, 0.020)], kit.mat("wood"),
                           center=tuple(grip), rot=(0, math.pi / 2, la),
                           verts=16))
    out += kit.stencil("dr_f4_pumptx", "HAND", (px - 0.004, py - 0.024, 0.019),
                       0.0082)

    # ---- six legend cells, one lit
    for i, body in enumerate(_F4_CELLS):
        out += kit.lampcell(f"dr_f4_cell_{i}",
                            (-0.101 + i * 0.0405, -0.100, 0.018), w=0.0360,
                            h=0.0155, legend=body, lit=(i == _F4_LIT),
                            kind="green" if i == _F4_LIT else "amber",
                            depth=0.0090)

    # ---- two guarded toggles
    for i, (tx, deg) in enumerate(((-0.098, 22.0), (-0.050, -8.0))):
        out += kit.toggle(f"dr_f4_tg_{i}", (tx, -0.134, 0.018),
                          kind="guarded", pos_deg=deg, scale=0.85,
                          legend=("XFER", "PURGE")[i], legend_w=0.028,
                          guard_up=(i == 0))

    out += kit.nameplate("dr_f4_pl", "WATER  +  RECLAIM",
                         (0.055, -0.134, 0.019), w=0.118, h=0.019,
                         size=0.0078, screws=False)
    out += kit.inspection_stamp("dr_f4_is", (0.118, -0.062, 0.020), "W4",
                                r=0.0078)
    out += kit.stencil("dr_f4_tx", "POTABLE", (0.000, 0.142, 0.019), 0.0115)
    out += kit.warn_triangle("dr_f4_wt", (0.118, -0.100, 0.020), 0.020)

    # brass plumbing tying the tank glass to the pump: high-frequency detail is
    # where the dressing budget goes (plan section 5.3), and it fills what was
    # a bare grey band across the middle of the panel.
    run = [(-0.098, -0.070, 0.026), (-0.076, -0.078, 0.026),
           (-0.020, -0.078, 0.026), (0.004, -0.070, 0.026)]
    out.append(kit.sweep("dr_f4_pipe", run, 0.0052, bd, sections=8))
    for k, i in enumerate((1, 2)):
        out += kit.pclip(f"dr_f4_clip_{k}", run[i], 0.0052, m=bd)
    out.append(kit.tube("dr_f4_union", (-0.048, -0.078, 0.026), 0.0080,
                        0.0050, 0.010, kit.mat("brass_dk"),
                        rot=(0, math.pi / 2, 0), verts=14))

    kit.parent_to(out, root)
    made.extend(out)


# ================================ 13/14. P1 + P2 -- ONE mount, two payloads
def _pillar_unit(P, index, z0, z1, tag, payload, made, stencil_txt):
    """The shared P1/P2 mount, per unit.

    Two wrapping brass collars (inner r 0.078 against the 0.075 column) plus a
    30 mm stand-off plate on forward ears.  Called four times: P1a, P1b, P2a,
    P2b.  Only `payload` differs -- that is the plan's `pillar_cap(payload)`.

    `payload(face, half_w, half_h)` is authored in the PLATE-FACE frame, where
    z = 0 is the front of the stand-off plate.
    """
    br = kit.mat("brass")
    zc = (z0 + z1) / 2.0
    h = z1 - z0
    loc, eul = slots.pillar(P, index, z=zc)
    root = kit.frame_empty(f"dr_{tag}_root", loc, eul)
    made.append(root)
    out = []
    hh = h / 2.0
    hw = PU_W / 2.0

    # two collars that genuinely WRAP the column (OTA's finding: a flat plate
    # this wide buries its edges 19 mm inside the cylinder)
    for k, cy in enumerate((-hh + 0.014, hh - 0.014)):
        out += kit.wrap_collar(f"dr_{tag}_col_{k}", (0.0, cy, -CR),
                               PU_RIN, PU_ROUT, 0.016, br, verts=44)
        # forward ears carrying the stand-off plate
        for j, sx in enumerate((-1, 1)):
            out.append(kit.box(f"dr_{tag}_ear_{k}_{j}",
                               (sx * 0.052, cy, 0.012),
                               (0.017, 0.015, 0.030), gunmetal(),
                               bevel=0.0016))
            out += kit.hexbolt(f"dr_{tag}_earb_{k}_{j}",
                               (sx * 0.052, cy, 0.028), 0.0040, 0.0045)

    # the 30 mm stand-off plate
    out.append(kit.box(f"dr_{tag}_plate", (0.0, 0.0, PU_STAND + 0.005),
                       (PU_W, h - 0.020, 0.010), panelface(),
                       bevel=0.0030))
    out += kit.rivet_row(f"dr_{tag}_rvl", (-hw + 0.008, -hh + 0.016, 0.040),
                         (-hw + 0.008, hh - 0.016, 0.040), 5, r=0.0028,
                         m=gunmetal())
    out += kit.rivet_row(f"dr_{tag}_rvr", (hw - 0.008, -hh + 0.016, 0.040),
                         (hw - 0.008, hh - 0.016, 0.040), 5, r=0.0028,
                         m=gunmetal())

    face = kit.frame_empty(f"dr_{tag}_face", (0.0, 0.0, PU_STAND + 0.010),
                           (0.0, 0.0, 0.0), parent=root)
    made.append(face)
    po = payload(tag, hw, hh)
    kit.parent_to(po, face)
    made.extend(po)

    if stencil_txt:
        out += kit.stencil(f"dr_{tag}_tx", stencil_txt,
                           (0.0, -hh + 0.007, PU_STAND + 0.011), 0.0105)
    kit.parent_to(out, root)
    made.extend(out)


def _jumper(P, index, tag, made, m_key, r):
    """The short run crossing the shell's own collar at z 1.94-1.98, so the two
    units read as one installation split AROUND the structural band rather than
    as two unrelated boxes."""
    zc = (PU_A[1] + PU_B[0]) / 2.0
    loc, eul = slots.pillar(P, index, z=zc)
    f = kit.frame_empty(f"dr_{tag}_jroot", loc, eul)
    made.append(f)
    out = []
    span = (PU_B[0] - PU_A[1]) / 2.0 + 0.020
    for k, sx in enumerate((-0.034, 0.034)):
        out.append(kit.cyl(f"dr_{tag}_jump_{k}", (sx, 0.0, PU_STAND + 0.012),
                           r, span * 2, kit.mat(m_key),
                           rot=(math.pi / 2, 0, 0), verts=12))
        for j, sy in enumerate((-span + 0.008, span - 0.008)):
            out.append(kit.tube(f"dr_{tag}_jband_{k}_{j}",
                                (sx, sy, PU_STAND + 0.012), r * 1.45, r * 0.98,
                                0.0055, gunmetal(),
                                rot=(math.pi / 2, 0, 0), verts=14))
    kit.parent_to(out, f)
    made.extend(out)


# ---- P1 payloads: coolant riser -------------------------------------------
def _p1_lower(tag, hw, hh):
    """Two vertical glass tubes with pale coolant and bubbles frozen mid-rise."""
    out = []
    for k, (sx, fill) in enumerate(((-0.033, 0.66), (0.033, 0.48))):
        out += kit.sightglass(f"dr_{tag}_sg_{k}", (sx, 0.002, 0.000),
                              length=0.118, r=0.0092, fill=fill, grads=6)
        # bubbles: tiny glass spheres inside the fluid column
        for j in range(4):
            by = 0.002 - 0.059 + 0.118 * fill * (0.18 + 0.19 * j)
            out.append(kit.sphere(f"dr_{tag}_bub_{k}_{j}",
                                  (sx + (0.0026 if j % 2 else -0.0022), by,
                                   0.0092), 0.0022 + 0.0006 * (j % 3),
                                  kit.mat("glass"), seg=8, ring=6))
    out.append(kit.box(f"dr_{tag}_hdr", (0.0, hh - 0.018, 0.008),
                       (PU_W - 0.024, 0.016, 0.014), gunmetal(),
                       bevel=0.0018))
    return out


def _p1_upper(tag, hw, hh):
    """Pressure gauge plus a four-spoke hand valve wheel."""
    br = kit.mat("brass")
    out = kit.gauge(f"dr_{tag}_pg", (-0.036, 0.012, 0.000), r=0.0300, ticks=7,
                    redline=(84.0, 118.0), needle_deg=-30.0, label="BAR",
                    depth=0.013, bezel_screws=3)
    # valve: bonnet, stem, four-spoke wheel
    vx, vy = 0.040, 0.006
    out.append(kit.revolve(f"dr_{tag}_bonnet",
                           [(0.0165, 0.0), (0.0165, 0.008), (0.0110, 0.012),
                            (0.0110, 0.020)], gunmetal(),
                           center=(vx, vy, 0.0),
                           verts=16))
    out.append(kit.cyl(f"dr_{tag}_stem", (vx, vy, 0.028), 0.0038, 0.020,
                       kit.mat("steel"), verts=10))
    out.append(kit.tube(f"dr_{tag}_wheel", (vx, vy, 0.038), 0.0290, 0.0248,
                        0.0060, br, verts=24))
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        out.append(kit.box(f"dr_{tag}_spoke_{k}",
                           (vx + 0.0135 * math.cos(a),
                            vy + 0.0135 * math.sin(a), 0.038),
                           (0.0290, 0.0048, 0.0044), br, rot=(0, 0, a),
                           bevel=0.0008))
    out.append(kit.cyl(f"dr_{tag}_whub", (vx, vy, 0.040), 0.0070, 0.0080, br,
                       verts=12))
    return out


# ---- P2 payloads: rectifier tube cage --------------------------------------
def _p2_lower(tag, hw, hh):
    """Four vacuum tubes in a slim brass cage behind a perforated guard.

    The tubes are the most on-theme object in the plan -- the README names
    vacuum tubes as the deliberate anachronism.  Filaments are a very dim
    amber (kit's `filament`, emission 1.2): hero-tier glow would steal frame.
    """
    br = kit.mat("brass")
    out = []
    # ceramic socket block
    out.append(kit.box(f"dr_{tag}_sock", (0.0, -hh + 0.026, 0.007),
                       (PU_W - 0.022, 0.026, 0.014), kit.mat("slate"),
                       bevel=0.0016))
    ys = -hh + 0.038
    for k, sx in enumerate((-0.045, -0.015, 0.015, 0.045)):
        out += kit.vactube(f"dr_{tag}_vt_{k}", (sx, ys, 0.000), h=0.068,
                           r=0.0125, lit=True, pins=8, axis="y")
    # slim brass cage: two rails and five vertical guard wires standing off
    for k, gy in enumerate((ys + 0.008, ys + 0.062)):
        out.append(kit.box(f"dr_{tag}_rail_{k}", (0.0, gy, 0.030),
                           (PU_W - 0.014, 0.0070, 0.0070),
                           gunmetal(), bevel=0.0010))
    for k in range(5):
        gx = -0.052 + k * 0.026
        out.append(kit.box(f"dr_{tag}_wire_{k}", (gx, ys + 0.035, 0.030),
                           (0.0040, 0.062, 0.0040), gunmetal(),
                           bevel=0.0008))
    for k, sx in enumerate((-1, 1)):
        out.append(kit.box(f"dr_{tag}_cheek_{k}",
                           (sx * (hw - 0.006), ys + 0.035, 0.017),
                           (0.0090, 0.070, 0.0300), gunmetal(),
                           bevel=0.0016))
    return out


def _p2_upper(tag, hw, hh):
    """Edgewise PLATE V meter plus a ceramic terminal block."""
    br, ink = kit.mat("brass"), kit.mat("ink")
    out = []
    mx, my = -0.020, 0.010
    mw, mh = 0.078, 0.036
    out.append(kit.box(f"dr_{tag}_mcan", (mx, my, 0.008), (mw, mh, 0.016),
                       kit.mat("case"), bevel=0.0018))
    out.append(kit.box(f"dr_{tag}_mface", (mx, my, 0.017), (mw - 0.010,
                                                            mh - 0.010,
                                                            0.0035),
                       kit.mat("ivory")))
    for k in range(9):
        tx = mx - (mw - 0.018) / 2 + k * ((mw - 0.018) / 8.0)
        out.append(kit.box(f"dr_{tag}_mtk_{k}", (tx, my + 0.005, 0.0192),
                           (0.0014, 0.0090 if k % 2 == 0 else 0.0052,
                            0.0012), ink))
    out.append(kit.box(f"dr_{tag}_mndl", (mx + 0.014, my + 0.002, 0.0202),
                       (0.0022, 0.0230, 0.0014), ink, rot=(0, 0, 0.10)))
    out.append(kit.text(f"dr_{tag}_mtx", "PLATE V", 0.0062, ink,
                        (mx, my - 0.011, 0.0192)))
    out += kit.bez_frame(f"dr_{tag}_mbez", mx, my, mw, mh, 0.014, 0.022,
                         gunmetal(),
                         bar=0.0034)
    # ceramic terminal block with brass screws
    bx, by = 0.046, 0.008
    out.append(kit.box(f"dr_{tag}_tb", (bx, by, 0.008), (0.030, 0.048, 0.016),
                       kit.mat("slate"), bevel=0.0016))
    for k in range(4):
        out += kit.screw(f"dr_{tag}_tbs_{k}",
                         (bx, by - 0.017 + k * 0.0113, 0.016), 0.0038)
    return out


# ==================================================================== entry
def add_tier3(P, mats):
    """Add tier 3's dressing geometry to the CURRENT scene.

    P    : shell PARAMS (already built)
    mats : {"brass":..., "hull":..., "hull_d":...}  -- the shell's own hero
           materials.  Dressing does NOT use them; `kit.mat()` supplies the
           desaturated set from DRESSING_PLAN.md section 5.1.
    Returns: {"dress": [list of created objects]}
    """
    made = []

    # 10 -- F2 hull integrity mimic
    _f2(P, made)

    # 11 -- D3 thrust & attitude-jet quadrant
    _d3(P, made)

    # 12 -- F4 water & reclamation
    _f4(P, made)

    # 13 -- P1 coolant riser (column 0).  ONE mount, called twice.
    _pillar_unit(P, 0, PU_A[0], PU_A[1], "p1a", _p1_lower, made, "COOLANT")
    _pillar_unit(P, 0, PU_B[0], PU_B[1], "p1b", _p1_upper, made, "RISER 2")
    _jumper(P, 0, "p1", made, "brass_dk", 0.0088)

    # 14 -- P2 rectifier tube cage (column 1).  Same mount, other payload.
    _pillar_unit(P, 1, PU_A[0], PU_A[1], "p2a", _p2_lower, made, "RECT BANK")
    _pillar_unit(P, 1, PU_B[0], PU_B[1], "p2b", _p2_upper, made, "PLATE  V")
    _jumper(P, 1, "p2", made, "braid", 0.0080)

    meshes = [o for o in made if o.type == 'MESH']
    em = kit.emissive_area(meshes)
    print(f"TIER3: {len(meshes)} meshes, {len(made) - len(meshes)} empties; "
          f"emissive area {em:.6f} m2  "
          f"(F2 2/14 lamps lit, F4 1/6 cells lit, P2 4 dim filaments)")
    return {"dress": made}


if __name__ == "__main__":
    P = dict(shell.PARAMS)
    P["exterior"] = 1
    shell.build(P)
    add_tier3(P, {"brass": bpy.data.materials["brass"],
                  "hull": bpy.data.materials["hull"],
                  "hull_d": bpy.data.materials["hull_d"]})
    bpy.context.scene.render.filepath = os.path.join(HERE, "out",
                                                     "_tier3_only.png")
    bpy.ops.render.render(write_still=True)
    print("WROTE", bpy.context.scene.render.filepath)
