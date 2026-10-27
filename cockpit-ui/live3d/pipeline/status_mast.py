"""
THE TELLTALE MAST, CLOSE-UP HALF -- one parametric builder, nine modules.

`live3d/design/STATUS_AT_A_GLANCE.md` is the design; section 6 is this half and
section 6.4 is the rule that makes it safe: ONE derivation (`live3d/status.js`),
two renderers.  This file is the geometry renderer's builder.  `live3d/mast.js`
is the frontend, and it consumes `derive()` / `INK` / `statusLine()` from
`status.js` -- it never re-derives display state and it never re-types a colour.

    from status_mast import solve_mast, build, export
    A = solve_mast("KVS", mast_px=190)          # no bpy needed
    P = build("kvs_mast", A["frame_blender"], A["L_m"], m=6)   # needs bpy
    export("KVS", A, P)                          # glb + scene.json

THREE HALVES, AND ONLY ONE OF THEM NEEDS BLENDER
------------------------------------------------
Deliberately the same shape as `pipeline/refit_port.py`, because the fan-out
that follows will be reading both:

* `solve_mast()` and everything above it is **pure stdlib**.  It answers, for
  one module: where on the refit port's service rail does the mast mount, what
  is the carrier's own measured normal there, how big is the mast in metres if
  it is to be N pixels long, how far must it stand off to survive the depth
  composite, and does its envelope clear every control hotspot and every
  declared readout rect.  It prints its own evidence.
* `build()` needs `bpy`.  It returns a dict of Blender objects and a manifest.
* `export()` writes `<CODE>/mast.glb` and merges a `"mast"` block into that
  module's `scene.json`.  **It re-renders nothing.**

IT DOES NOT SOLVE THE ANCHOR TWICE
----------------------------------
`refit_port.solve_anchor()` already turns a target pixel into a world frame, a
MEASURED carrier normal, a physical size, a stand-off that clears `ubias_m` and
a 0-overlap proof against every hotspot and readout rect.  This file imports it
and its parts (`Camera`, `PortFrame`, `fit_carrier_plane`, `_prism`, `_dome`,
`_shell`, `_material`, `export_glb`) rather than writing a second one.  What is
new here is only what the mast needs and the port did not:

  1. **The mount is not a pixel, it is a seam.**  FIX_UPLOAD 12.13: the port
     publishes `scene.json -> refit.service_rail` with `origin`, `dir`,
     `claimed_half_m`, `thick_m`, `proud_m` and **`free_from_m` = 1.5 W**, and
     that is where this fitting may start.  On KVS `free_from_m` is 0.0457 m.
     `solve_mast()` reads it and mounts there; the pixel is derived, not
     chosen.  A module whose port is not built yet can still be solved by
     passing `px=`/`py=` and the carrier is measured exactly as the port's is.
  2. **THE RAKE.**  This is the one measurement that changed the design.  On
     KVS the carrier (the front deck) is at 57.3 deg obliquity to the close
     camera, and the deck's own two in-plane axes project at 1.846 px/mm along
     the rail but only 1.290 px/mm up the deck -- and `v` (up the carrier) and
     `n` (out of it) project to within 7.6 deg of the SAME screen direction, so
     a fitting lying flat on the deck has no readable second axis at all.
     A face raked `rake_deg` off the carrier toward `-v` fixes it: at 45 deg
     KVS's mast face sits at **12.5 deg** obliquity -- the same as KVS's own
     console face, 12.35 -- and its two axes project at 1.846 and 1.872 px/mm,
     i.e. the fitting is not foreshortened in either direction.  The rake is an
     AUTHORED CONSTANT, not a camera solve: it is a raked instrument face on a
     bracket, and it does not track the camera.  `--rakes` prints the table for
     any module so the fan-out picks its own rather than inheriting KVS's.

FOUR THINGS THAT WILL BITE, ALL OF THEM MEASURED
------------------------------------------------
1. **Trap 21: `dress()` forces `THREE.FrontSide`** and deletes one-sided
   Blender geometry with no error and an empty `auditScene()`.  The listed
   casualties are "swept ribbons, FLAGS, tape, curtains, single-quad labels",
   and OTA lost 14 single-triangle chevrons this way.  **THE VANE IS EXACTLY
   THAT SHAPE.**  Every part in this file is a CLOSED SOLID -- the vane, the
   hazard chevrons, the stale scrim bars and the hatch bars included -- so the
   mast survives FrontSide by construction.  There is no deliberately
   one-sided surface here at all.  Run `facingAudit(camera)` anyway.
2. **Trap 24: `ubias_m`.**  `pipeline/live_depth.py` globs EVERY `.glb` in the
   asset folder, so adding `mast.glb` changes what `ubias.py` is measured on --
   the refit port hit this and cleared it.  Every surface here stands proud:
   `_solve_lift()` raises the whole assembly until its closest point clears the
   baked carrier by `lift_margin * ubias_m`, sampled over the real vertices and
   not over a bounding box.  Re-run `live_depth.py <CODE>` afterwards and
   confirm the module's shipped `ubias_m` has not moved.
3. **NO DECLARED READOUT PLANE.**  All of the mast's words are a screen-space
   HUD in `live3d/mast.js`, the same class of thing as KVS's two `.hud` panels
   and the refit port's docket.  So `check_occlusion.py`'s question 5 ("no
   declared rect may project over another readout's carrier" -- the check that
   caught LOG shipping four blank readouts while everything passed), the
   dial-face rule and `check_text.py` are **NOT ENGAGED** by this component
   rather than merely satisfied.  `MAX_PLANES` is untouched and every module's
   plane count is unchanged.  Keep it that way.
4. **The page must rest posed.**  `mast.js`'s `pose()` HIDES the mast, exactly
   as `refit.js`'s does, so every recorded number reproduces byte-identically
   and the replacement check is a re-shoot with the mast forced visible.  The
   sweep animation and the vane easing run off the module's own frame loop and
   own no timer, so there is nothing for `pose()` to `clearInterval`.

PKT IS NOT PRECLUDED
--------------------
`kind="offensive"` swaps the graduated tube for the notched brass tally stick
of section 8, drops the vane and turns the cap bead into the ARM lamp.  It is
implemented and it is NOT integrated on PKT -- nothing here has been looked at
on that module and its anchor has not been solved.  It exists so the fan-out
inherits the shape rather than having to re-cut this file.

CONVENTIONS  (they are `refit_port.py`'s, deliberately)
-------------------------------------------------------
* The mast is authored in its own frame: local +X = `A` (along the mast, away
  from the port), +Y = `B` (across it; +B is the side the vane flies to), +Z =
  `C` (out of the mast's raked face, toward the reader).  This is exactly
  section 2.2's mast-local (A, B) with a third axis for thickness.
* Every dimension is a fraction of **L**, the mast's length along A, and the
  fractions are section 2.2's own wide-shot pixel table divided by 78.  The
  wide-shot number is in the comment beside every one of them, so the close-up
  and the wide shot can be diffed by eye.
* `root_scale` is divided out of every dimension, so `L` is always the WORLD
  size you asked for.  DNSM 0.78, MQB 0.70, PKT 1.15 -- **but it is 1.0 on the
  `-- mast` entry point**, which clears the scene and authors in world
  coordinates.  There is no root to be inside there.  `build()` refuses a
  non-unit value in an empty scene rather than shipping a 1.43x mast.
* NEVER a float in an object name -- Blender parses `.NNN` as a duplicate
  suffix.  Indices only.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import refit_port as RP                                          # noqa: E402
from refit_port import (Camera, PortFrame, load_module, read_depth,   # noqa
                        fit_carrier_plane, _add, _cross, _dot, _mul,
                        _norm, _sub, to_blender, to_three,
                        ThinMargin, margin_report, margin_message)


# ===========================================================================
# GEOMETRY TABLE -- every dimension as a fraction of L, the mast's length
# along A.  The comment on each line is STATUS_AT_A_GLANCE section 2.2's own
# wide-shot pixel, so the close-up fitting and the DOM mast can be diffed by
# eye rather than by trust.  78 px of wide-shot mast == 1.000 L.
# ===========================================================================
GEO = {
    # ---------------------------------------------------------------- along A
    "collar_a0":  0.0256,   # A  2   COLLAR   <- the seam with the refit port
    "collar_a1":  0.1538,   # A 12
    "rod_a0":     0.1538,   # A 12   ROD
    "rod_a1":     1.0000,   # A 78
    "bezel_a0":   0.2051,   # A 16   TUBE BEZEL
    "bezel_a1":   0.8205,   # A 64
    "bore_a0":    0.2308,   # A 18   BORE -- the security axis lives here
    "bore_a1":    0.7949,   # A 62
    "cap_a":      0.8718,   # A 68   CAP BEAD centre (A 64-72)
    "knob_a0":    0.9231,   # A 72   HEAD KNOB
    "knob_a1":    1.0000,   # A 78
    "vane_a":     0.8974,   # A 70   VANE pivot

    # ---------------------------------------------------------------- across B
    "collar_b":   0.0641,   # B +/- 5
    "rod_b":      0.0256,   # B +/- 2
    "bezel_b":    0.0769,   # B +/- 6
    "bore_b":     0.0513,   # B +/- 4
    "seg_b":      0.0449,   # the fill sits inside the bore wall
    "cap_r":      0.0513,   # d8
    "knob_r":     0.0321,   # d5
    "vane_len":   0.2051,   # B +16  the flying pennant's reach
    "vane_w":     0.0641,   # its chord along A
    "vane_t":     0.0140,   # THICKNESS.  Trap 21: a vane is the shape the trap
                            # names.  It is a closed prism, never a quad.

    # THE PILOT-LAMP ROW -- section 6.1's "row of M numbered pilot lamps, in
    # CATALOGUE order".  The tube is sorted by state; this row is sorted by
    # identity, because in the close-up you are choosing WHICH vuln to work on.
    #
    # ABOVE the tube, on its own strip, and both halves of that are corrections
    # to the first build.  Below the tube at B -0.0705 the lamps were INSIDE
    # the bezel's lower rim (which spans -0.0769..-0.0513 at every C the lamps
    # occupy) and rendered half-buried; moving them clear below would have put
    # the row at B -0.108 and pushed the envelope 26 px further down the frame,
    # off the bottom of KVS's.  Above, the row lands inside the envelope the
    # VANE already claims (+0.205), so it costs no screen space at all.
    "lamp_b":     0.1080,
    "lamp_r":     0.0240,
    "lampbar_b":  0.0820,   # the strip they are mounted on
    "lampbar_b1": 0.1340,
    "num_b":      0.1550,   # engraved number centre, if `numbers=True`
    "num_h":      0.0450,

    # ------------------------------------------------- out of the face, along C
    # C = 0 is the BACK of the plate.  Everything is positive, so the whole
    # fitting is a solid standing off its bracket.
    "c_rod":      0.0500,
    "c_collar":   0.0750,
    "c_bezel":    0.1050,   # the bezel rim's face: the opaque hardware
    "c_floor":    0.0450,   # the bore's floor: the well is 0.060 L deep
    "c_seg":      0.0850,   # the fill's top, RECESSED below the rim by 0.020 L
    "c_hatch":    0.0970,   # the inconclusive bar, standing over the fill
    "c_haz":      0.1180,   # hazard chevrons, standing over the rim
    "c_scrim":    0.1260,   # the STALE scrim, over everything

    # ------------------------------------------------------------- the bracket
    # A raked face needs something to hold it up.  The foot is built in the
    # CARRIER frame, not the mast frame, so it always touches the rail however
    # the rake is set.
    "foot_a0":   -0.0300,
    "foot_a1":    0.1900,
    "foot_w":     0.0450,   # half-width across the rail, in L

    # ------------------------------------------------------- the service rail
    # The port builds only its own half (FIX_UPLOAD 12.13 / KVS NOTES 12): its
    # `_srail` runs +/- `claimed_half_m` = 0.65 W.  This builder continues the
    # SAME section from where the port's ends to past the mast's far end, so
    # the fiction reads as one rail with a fitting at each end rather than as
    # two lugs.  Its cross-section is read from the port's own published
    # `service_rail` block, never re-derived.
    "rail_pad":   0.1200,   # how far past the mast's ends the rail runs, in L

    # ----------------------------------------------------------------- details
    "grad_t":     0.0060,   # graduation rib half-width along A
    "haz_n":      7,        # hazard chevrons across the bezel
    "haz_w":      0.0230,   # each chevron's half-width along A
    "scrim_n":    5,        # STALE scrim bars over bezel + cap
    "scrim_w":    0.0060,
    "sweep_a":    0.1000,   # the running sweep band's length along A

    # ------------------------------------------------------- the TALLY STICK
    # section 8: PKT gets different hardware on the same fittings.  Notched
    # brass, not glass, so nobody reads it as a thermometer, and it fills the
    # other way as GOOD news.  INTEGRATED 2026-09-06 -- PKT ships it, and is
    # the only module that does; see section 18.4.
    "tally_b":    0.0641,   # +/- 5, slimmer than the bezel
    "tally_n":    12,       # chevron notches cut into the stick
    "c_tally":    0.0900,
    "c_notch":    0.0620,

    # ------------------------------------------------------------- THE RAKE
    # The face leans back off the carrier toward -v, so it faces the reader.
    # See note 2 in the module docstring; `--rakes` prints the measurement.
    "rake_deg":  45.0,
}

# Materials are authored with SCALAR Principled inputs only, for the same
# reason `refit_port.MATS` is: Blender's glTF exporter drops
# roughnessFactor/metallicFactor whenever the input is node-driven, and these
# must survive the round trip on their own because the mast's materials are
# NOT in any module's `materials.json` and must never be added to it -- that
# file is a shipped asset `verify_assets.py` reads.
#
# THE COLOURS ARE PLACEHOLDERS AND `mast.js` OVERWRITES THEM.  Every hex in
# the design lives in `status.js -> INK` and nowhere else (section 9.3), and a
# second copy baked into a `.glb` is a second source of truth that a later edit
# could desynchronise.  `mast.js` sets `.color` and `.emissive` from `INK` on
# every material below.  What the exporter's values buy is a sane-looking glb
# in a viewer and correct roughness/metalness, which JS does NOT set.
MATS = {
    #  name        base rgb                metal rough  emission      str
    "brass":    ((0.400, 0.320, 0.160), 0.85, 0.44, None,          0.0),
    "brass_dk": ((0.145, 0.113, 0.055), 0.85, 0.52, None,          0.0),
    # the bezel: OPAQUE HARDWARE.  Section 4.4 is the load-bearing decision in
    # the whole visual -- no status colour ever touches the plate, so every
    # coloured pixel sits inside this.
    # ROUGHNESS 1.0, METALNESS 0, and both are measured rather than styled.
    # KVS lights the close-up with ten area lights and the mast's face is at
    # 12.5 deg obliquity -- it stares straight into them.  At roughness 0.6 the
    # dielectric specular lobe alone lifts this material from luma 0.070 to
    # 0.315 on the real page and the bezel stops being dark hardware; at 1.0 it
    # renders 0.165, which is the best a black surface can do under this rig
    # and still leaves 0.41 of separation to the landing red.  Swept on the
    # page, not chosen.
    "bezel":    ((0.004, 0.005, 0.007), 0.00, 1.00, None,          0.0),
    # the fill.  One material, cloned per mesh by the module's own dress(), so
    # the six segments swap state independently.  Emissive is authored non-zero
    # because a Blender material with Emission Strength 0 round-trips through
    # glTF as emissive BLACK and driving emissiveIntensity on black multiplies
    # zero -- the refit port's throat and jewel stayed dark at every intensity
    # and it looked like the state machine was not firing (FIX_UPLOAD 12.8).
    "fill":     ((0.180, 0.030, 0.022), 0.00, 0.90, (0.85, 0.30, 0.20), 0.6),
    "glass":    ((0.010, 0.014, 0.021), 0.00, 1.00, None,          0.0),
    "grad":     ((0.150, 0.175, 0.200), 0.10, 0.60, None,          0.0),
    "hazard":   ((0.760, 0.480, 0.040), 0.10, 0.45, None,          0.0),
    "green":    ((0.040, 0.520, 0.320), 0.00, 0.35, (0.20, 0.90, 0.60), 0.6),
    # the pilot lamps and the cap bead are LENSES and stay glossy; the tube's
    # fill is a column of lit glass seen through a well and is matte, or the
    # specular lobe eats the state it is supposed to be showing.
    "lens":     ((0.180, 0.030, 0.022), 0.00, 0.30, (0.85, 0.30, 0.20), 0.6),
    # THE TALLY STICK'S NOTCHES ARE CUT INTO BRASS, NOT SET INTO IT.  They were
    # built with `lens` -- roughness 0.30, the pilot lamps' material -- and PKT
    # is the first module that ever rendered them: under ten area lights the
    # UNLIT notches came out LIGHTER than the stick they are cut into, so the
    # fitting read as a pale comb with red teeth rather than as a stick with
    # notches in it.  It is the same specular-lobe effect the bezel was swept
    # for (luma 0.070 -> 0.315 at roughness 0.6, 0.165 at 1.0), and the answer
    # is the same: roughness 1.0, metalness 0.  The LIT notches are painted
    # `INK.tallyOn` by `mast.js` and are unaffected -- the red/not-red
    # discrimination was never in doubt; what was lost was "cut INTO brass".
    # PKT NOTES 13, the judgement item.
    "notch":    ((0.030, 0.021, 0.014), 0.00, 1.00, (0.85, 0.30, 0.20), 0.6),
    "ink":      ((0.055, 0.050, 0.052), 0.00, 0.62, None,          0.0),
}


# ===========================================================================
# PURE STDLIB -- the mount, the rake, the size, the stand-off, the clearances.
# No bpy below this line until the BLENDER section.
# ===========================================================================
def mast_frame(u, v, n, rake_deg):
    """The mast's own (A, B, C) axes, from the carrier's (u, v, n).

    A = u                              along the rail, away from the port
    B = v cos(rho) + n sin(rho)        up the RAKED face
    C = n cos(rho) - v sin(rho)        out of the raked face, toward the reader

    rho = 0 lays the fitting flat on the carrier (B = v, C = n).  rho = 90
    stands it up as a fin perpendicular to the carrier.  Neither is what a
    raked deck wants; see note 2 in the module docstring.
    """
    r = math.radians(rake_deg)
    cs, sn = math.cos(r), math.sin(r)
    B = _norm([v[i] * cs + n[i] * sn for i in range(3)])
    C = _norm([n[i] * cs - v[i] * sn for i in range(3)])
    return _norm(list(u)), B, C


def rake_table(cam, u, v, n, rakes=(0, 15, 30, 45, 57, 60, 75, 90)):
    """For each candidate rake: the face's obliquity to the close camera and
    the px/m of both of its axes at 1 m.  THIS is the number the fan-out picks
    its rake from, and it is different on every module."""
    look = cam.zc                       # unit, surface -> camera
    out = []
    for rd in rakes:
        A, B, C = mast_frame(u, v, n, rd)
        ob = math.degrees(math.acos(max(-1.0, min(1.0, _dot(C, look)))))
        out.append({"rake_deg": float(rd), "obliq_deg": ob,
                    "cosA": abs(_dot(A, look)), "cosB": abs(_dot(B, look))})
    return out


def axis_px_per_m(cam, origin, axis, d=0.001):
    """Screen px per metre of a world direction at a world point."""
    p0 = cam.project(origin)
    p1 = cam.project([origin[i] + axis[i] * d for i in range(3)])
    return math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / d


def _hull_samples(G, m, kind, numbers):
    """(A, B, C) corners of everything the mast actually paints.

    NOT a bounding box.  The stand-off solve and the envelope both run on
    these, for the same reason `refit_port.envelope_px()` exists: the port's
    base hexagon was 5-7 px short of the pixels it painted on every side, and a
    hotspot or a keep-out built from the wrong rectangle is measuring the wrong
    thing (FIX_UPLOAD 12.4).
    """
    pts = []

    def box(a0, a1, b0, b1, c0, c1):
        for a in (a0, a1):
            for b in (b0, b1):
                for c in (c0, c1):
                    pts.append((a, b, c))

    box(G["collar_a0"], G["collar_a1"], -G["collar_b"], G["collar_b"],
        0.0, G["c_collar"])
    box(G["rod_a0"], G["rod_a1"], -G["rod_b"], G["rod_b"], 0.0, G["c_rod"])
    box(G["bezel_a0"], G["bezel_a1"], -G["bezel_b"], G["bezel_b"],
        0.0, G["c_scrim"])
    box(G["cap_a"] - G["cap_r"], G["cap_a"] + G["cap_r"],
        -G["cap_r"], G["cap_r"], 0.0, G["c_rod"] + G["cap_r"])
    box(G["knob_a0"], G["knob_a1"], -G["knob_r"], G["knob_r"], 0.0, G["c_rod"])
    if kind == "defensive":
        # the vane, in BOTH poses -- flying (+B) and furled (along +A).  The
        # swept envelope is the union, and a hotspot that only covers one of
        # them stops covering the fitting the moment the service breaks.
        box(G["vane_a"] - G["vane_w"], G["vane_a"] + G["vane_w"],
            0.0, G["vane_len"], 0.0, G["c_rod"] + G["vane_t"])
        box(G["vane_a"], G["vane_a"] + G["vane_len"],
            -G["vane_w"], G["vane_w"], 0.0, G["c_rod"] + G["vane_t"])
        box(G["bore_a0"], G["bore_a1"], G["lampbar_b"],
            G["lamp_b"] + G["lamp_r"], 0.0, G["c_rod"] + G["lamp_r"])
        if numbers:
            box(G["bore_a0"], G["bore_a1"], G["num_b"] - G["num_h"],
                G["num_b"] + G["num_h"], 0.0, G["c_rod"])
    return pts


def _clearance(cam, O_rail, u, n, A_ax, B_ax, C_ax, L, dep, W, H, hull,
               lift, start_m):
    """min over the hull of (baked depth - the mast's own depth), in metres.

    Positive is IN FRONT of the baked plate and therefore drawn; the depth
    composite is `if (vLinDepth > baked - uBias) discard`, so anything at or
    below `ubias_m` here is deleted silently.  Trap 24.
    """
    worst = 1e9
    for (a, b, c) in hull:
        P = [O_rail[i] + u[i] * start_m + n[i] * lift
             + A_ax[i] * (a * L) + B_ax[i] * (b * L) + C_ax[i] * (c * L)
             for i in range(3)]
        px, py, D = cam.project(P)
        if not (0 <= px < W and 0 <= py < H):
            continue
        baked = dep[int(py) * W + int(px)]
        if baked >= 1e9:
            continue
        worst = min(worst, baked - D)
    return 0.0 if worst > 1e8 else worst


class Cantilever(ValueError):
    """Nothing is behind this fitting within reach of it.

    Carries the solved dict on `.mast` (and `.anchor`, for symmetry with
    `refit_port.ThinMargin`), so a REPORT -- a `--sweep-px` table, a `--rakes`
    table -- can still print the row it was going to print and flag it, while a
    BUILD refuses.
    """

    def __init__(self, msg, solved=None):
        ValueError.__init__(self, msg)
        self.mast = solved
        self.anchor = solved


# THE CANTILEVER FLOOR, as a fraction of L.  The CLOSEST point of the whole
# assembly to the baked plate is what says whether the fitting is standing on
# anything: a seated one touches down at its stand-off margin and no further.
# Measured across the seven shipped fittings the closest point is
#
#   MTA 0.0088 L   FMM 0.0128 L   PKT 0.0137 L   OTA 0.0159 L
#   MQB 0.0167 L   KVS 0.0208 L   IPM 0.0249 L
#
# -- all under 0.025 L -- and the two rail routes that were rejected by eye
# read 1.00 L (IPM, over the floor behind the column) and 2.24 L (OTA, over
# starfield).  0.25 L is ten times the worst shipping figure and four times
# under the failing one, which is what makes it a threshold and not a guess.
CANTILEVER_L = 0.25


def _stand_off_range(cam, O, A_ax, B_ax, C_ax, L, dep, W, H, hull):
    """(closest, furthest) `baked - D` over the hull, in metres, at the final
    pose.  Positive is IN FRONT of the baked plate.

    `_clearance()` answers only the MINIMUM, because the minimum is what the
    depth composite deletes.  The MAXIMUM is the number that says whether the
    fitting is standing ON its carrier or hanging in front of it -- and nothing
    in this file measured it, which is how IPM's rail-mounted mast reported
    `carrier_solid_pct 100.0` and `lift 0.0x ubias` over a floor 190 to 310 mm
    BEHIND the port's own carrier: a quarter-metre cantilever off the side of a
    column that passed every printed clearance.  See CANTILEVER in
    `solve_mast()`.  IPM NOTES 13 item 2.
    """
    lo, hi = 1e9, -1e9
    for (a, b, c) in hull:
        P = [O[i] + A_ax[i] * (a * L) + B_ax[i] * (b * L) + C_ax[i] * (c * L)
             for i in range(3)]
        px, py, D = cam.project(P)
        if not (0 <= px < W and 0 <= py < H):
            continue
        baked = dep[int(py) * W + int(px)]
        if baked >= 1e9:
            continue
        lo = min(lo, baked - D)
        hi = max(hi, baked - D)
    if hi < -1e8:
        return None, None
    return lo, hi


def cantilever_message(code, mount, L, C):
    port = ""
    if C["port_carrier_depth_m"]:
        port = ("  The REFIT PORT's own carrier is at %.4f .. %.4f m and what "
                "is behind this mast is at %.4f .. %.4f m -- %+.4f m behind "
                "it.  Read `carrier_depth_m` BESIDE `carrier_solid_pct`, "
                "never instead of it.\n"
                % (C["port_carrier_depth_m"][0], C["port_carrier_depth_m"][1],
                   C["carrier_depth_m"][0], C["carrier_depth_m"][1],
                   C["behind_port_carrier_m"]))
    return (
        "%s: the CLOSEST point of the whole assembly stands %.4f m in front of "
        "the baked plate -- %.2f x its own length L (%.4f m), against a floor "
        "of %.2f L.  Nothing is behind this fitting within reach of it: it is "
        "a cantilever, not a mounting.\n"
        "  `carrier_solid_pct` CANNOT SEE THIS.  It answers 'is there anything "
        "behind every pixel', and over a deep floor the answer is 100 %% while "
        "the fitting hangs a quarter of a metre in front of it.  OTA's rail "
        "landed on starfield (2.3 %%) and MTA's ran off a panel edge; both were "
        "caught by the percentage.  IPM's reported 100.0 %%, every clearance "
        "0 px2 and lift 0.0 x ubias, and was a 250 px cantilever off the side "
        "of a column.  IPM NOTES 13 item 2.\n"
        "%s"
        "  mount: %s.  Move it along the rail (--start-w), shrink it (--px), "
        "or take the `--at PX,PY` route and mount it on the surface that is "
        "actually there."
        % (code, C["stand_off_m"][0], C["stand_off_over_L"], L,
           C["floor_L"], port, mount))


def _solve_lift(cam, O_rail, u, v, n, A_ax, B_ax, C_ax, L, dep, W, H, ub,
                margin, G, m, kind, numbers, start_m):
    """The SMALLEST lift along the carrier normal at which nothing is deleted.

    Trap 24 applied to a fitting that does not lie in the carrier plane.  This
    is a SCAN, not a Newton step, and that is deliberate: the first version
    added `(worst + margin * ub) / (dn/dD)` once per iteration and the pixel
    each sample lands on moves as the assembly rises, so every pass found a
    new, nearer baked surface and added again.  It converged -- to 19.6 mm on
    KVS, against a true requirement of 4.6 mm.  A fitting standing 15 mm
    further off its bracket than it needs to is a visible float, and nothing
    in the output said so.  Scan, and take the first lift that clears.
    """
    hull = _hull_samples(G, m, kind, numbers)
    target = margin * ub
    step = max(ub * 0.5, 1e-5)
    lift = 0.0
    for _ in range(4000):
        c = _clearance(cam, O_rail, u, n, A_ax, B_ax, C_ax, L, dep, W, H,
                       hull, lift, start_m)
        if c >= target:
            # confirm it STAYS clear for the next few steps, so a single
            # sample landing in a depth crack cannot be mistaken for a
            # solution
            if all(_clearance(cam, O_rail, u, n, A_ax, B_ax, C_ax, L, dep, W,
                              H, hull, lift + step * k, start_m) >= target
                   for k in (1, 2, 3)):
                return lift
        lift += step
        if lift > 0.75 * L:
            raise ValueError(
                "no lift under 0.75 L clears the baked carrier at this "
                "anchor: the mast's envelope is over something much nearer "
                "the camera than its mount.  Move it along the rail "
                "(--start-w), shrink it (--px), or pick another carrier.")
    return lift


def envelope_px(cam, O, A_ax, B_ax, C_ax, L, G, m, kind, numbers):
    """Screen bbox of the WHOLE ASSEMBLY, thickness and both vane poses
    included.  See `_hull_samples`."""
    xs, ys = [], []
    for (a, b, c) in _hull_samples(G, m, kind, numbers):
        P = [O[i] + A_ax[i] * (a * L) + B_ax[i] * (b * L) + C_ax[i] * (c * L)
             for i in range(3)]
        px, py, _ = cam.project(P)
        xs.append(px)
        ys.append(py)
    return min(xs), max(xs), min(ys), max(ys)


def _rects(S):
    """Every control hotspot and every declared readout rect, in close-frame
    px.  Exactly what `refit_port.clearance_report()` collects, so the two
    components are measured against the same list."""
    rects = []
    for k, p in (S.get("props") or {}).items():
        r = p.get("hotspot")
        if r:
            rects.append(("hotspot " + k,
                          [r["x"], r["x"] + r["w"], r["y"], r["y"] + r["h"]]))
    for i, tp in enumerate(S.get("text_planes") or [S.get("text_plane")]):
        if not tp or not tp.get("corners_px"):
            continue
        c = tp["corners_px"]
        rects.append(("readout %d" % i,
                      [min(c[k]["x"] for k in c), max(c[k]["x"] for k in c),
                       min(c[k]["y"] for k in c), max(c[k]["y"] for k in c)]))
    R = S.get("refit")
    if R and R.get("hotspot"):
        h = R["hotspot"]
        rects.append(("refit port",
                      [h["x"], h["x"] + h["w"], h["y"], h["y"] + h["h"]]))
    return rects


def solve_mast(code, mast_px=190, m=None, kind="defensive", rake_deg=None,
               start_w=None, px=None, py=None, carrier_window=None,
               lift_margin=2.5, numbers=False, geo=None, verbose=True):
    """Turn the refit port's published seam into everything build/export need.

    code          module code; reads `live3d/assets/<CODE>/scene.json`
    mast_px       the mast's LENGTH ALONG A, in the module's own 1280x720 close
                  frame.  Hold the screen size, derive the physical one --
                  the same rule `refit_port.solve_anchor()` follows, and the
                  reason a 30 mm port and a 100 mm mast read at comparable
                  sizes on nine differently-scaled modules.
    m             graduations / PoC count.  None reads it from `status.json`.
    kind          "defensive" (tube + vane) or "offensive" (tally stick, PKT).
    rake_deg      the face's rake off the carrier.  None uses GEO's 45.
    start_w       where along the rail the mast's A=0 sits, in PORT widths.
                  None uses the port's own published `free_from_m` (1.5 W),
                  which is the seam STATUS_AT_A_GLANCE 11.2 accepted.
    px, py        FALLBACK for a module whose refit port is not built yet: the
                  carrier is measured at this pixel exactly as the port's is,
                  and `u`/`v`/`n` come from the fit instead of from the port.
    lift_margin   how many multiples of `ubias_m` the closest point of the
                  assembly must clear the baked carrier by.

    Returns a dict; `frame` is in three.js world, `frame_blender` is the same
    frame mapped for authoring.  Prints its own evidence when `verbose`.
    """
    G = dict(GEO)
    if geo:
        G.update(geo)
    if rake_deg is None:
        rake_deg = G["rake_deg"]

    Adir, S = load_module(code)
    cam = Camera(S)
    dep, W, H = read_depth(Adir, S)
    ub = float(S.get("ubias_m") or 0.0005)

    R = S.get("refit")
    if R and R.get("service_rail") and px is None:
        sr = R["service_rail"]
        fr = R["frame"]
        u, v, n = _norm(fr["u"]), _norm(fr["v"]), _norm(fr["n"])
        O_rail = list(sr["origin"])
        start_m = (sr["free_from_m"] if start_w is None
                   else start_w * R["W_m"])
        mount = "refit.service_rail"
        rail = {"claimed_half_m": sr["claimed_half_m"],
                "thick_m": sr["thick_m"], "proud_m": sr["proud_m"],
                "free_from_m": sr["free_from_m"]}
        n_carrier, resid = n, None
        if carrier_window:
            x0, x1, y0, y1 = carrier_window
            _c, n_carrier, resid = fit_carrier_plane(cam, dep, W, H,
                                                     x0, x1, y0, y1)
    else:
        # No port on this module yet -- measure the carrier ourselves, with the
        # port's own solver, and invent a rail.
        if px is None or py is None:
            raise ValueError(
                "%s has no refit.service_rail in scene.json.  Either build the "
                "refit port first (pipeline/refit_port.py) or pass px=/py= and "
                "the carrier will be measured at that pixel instead." % code)
        if carrier_window is None:
            carrier_window = (int(px - 40), int(px + 40),
                              int(py - 24), int(py + 24))
        x0, x1, y0, y1 = carrier_window
        c, n, resid = fit_carrier_plane(cam, dep, W, H, x0, x1, y0, y1)
        up_ref = cam.yc
        v = _norm(_sub(up_ref, _mul(n, _dot(up_ref, n))))
        u = _norm(_cross(v, n))
        O_rail = cam.hit_plane(px, py, c, n)
        start_m = 0.0
        mount = "measured carrier at (%s, %s)" % (px, py)
        rail = None
        n_carrier = n

    A_ax, B_ax, C_ax = mast_frame(u, v, n, rake_deg)

    # ---- size: hold the SCREEN length along A, derive L in metres.
    # Projection is not linear in size, so iterate; four passes are under
    # 0.01 px on KVS.  Measured on the A axis at the mount, because A is the
    # axis the tube's fill is read along and the one that must be right.
    O0 = [O_rail[i] + u[i] * start_m for i in range(3)]
    L = mast_px / max(1e-6, axis_px_per_m(cam, O0, A_ax))
    for _ in range(12):
        p0 = cam.project(O0)
        p1 = cam.project([O0[i] + A_ax[i] * L for i in range(3)])
        got = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        k = mast_px / got
        L *= k
        if abs(k - 1.0) < 1e-9:
            break

    if m is None:
        m = _poc_count(code)

    lift = _solve_lift(cam, O_rail, u, v, n, A_ax, B_ax, C_ax, L,
                       dep, W, H, ub, lift_margin, G, m, kind, numbers,
                       start_m)
    O = [O_rail[i] + u[i] * start_m + n[i] * lift for i in range(3)]
    frame = PortFrame(O, A_ax, B_ax, C_ax)

    bx0, bx1, by0, by1 = envelope_px(cam, O, A_ax, B_ax, C_ax, L, G, m,
                                     kind, numbers)
    # THE BRACKET IS PART OF THE FITTING and it is built in the CARRIER frame,
    # so it is not in the mast-local hull.  Left out of the envelope it pokes
    # 6 px past the declared hotspot on KVS -- which is exactly the 40 px the
    # "every differing pixel is inside a declared rect" proof came up short by
    # the first time it was run.  Union it in.  (The RAIL is deliberately NOT
    # in here: it is shared structure running 1.9 L back to the port, and a
    # 350 px pointer target on it would collide with everything.  Its own span
    # is published separately as `evidence.rail_bbox_px`.)
    # ---------------------------------------------------------- THE RAIL RAMP
    # THE DECK IS NOT FLAT OVER 0.19 m AND A FLUSH RAIL SINKS INTO IT.
    #
    # The port's own rail spans +/- 0.65 W = 40 mm and never had to care.  This
    # one runs nearly five times that, and measured against `depth.bin` the
    # KVS deck rises 7 mm toward the camera across it: a rail lying in the
    # port's fitted carrier plane clears by 2.3 mm at the port end, by 0.25 mm
    # at the mast's bracket and is 0.9 mm BEHIND the baked plate at its far
    # end -- where the depth composite deletes it, silently, trap 24.
    #
    # Worse, and this is the part that does not show on screen: a bar whose
    # underside CROSSES the carrier has a zero-gap curve running along it, and
    # `pipeline/live_depth.py` measures the whole asset folder.  Built flush,
    # KVS's eroded minimum gap fell from 0.000808 m to 0.000049 m and
    # `ubias.py` would have re-derived the module's shipped `ubias_m` from
    # 0.000565 to 0.000034 -- a number this component is not allowed to move.
    #
    # So the rail is a STRAIGHT BAR THAT IS NOT PARALLEL TO THE FITTED PLANE:
    # one linear ramp, solved so its worst point clears by the same margin
    # everything else does.  Flush with the port's rail at the joint, rising
    # to meet the deck as the deck rises.  A rail bolted across a curved deck
    # does exactly this; a rail that ignores the curve is the thing that would
    # need explaining.
    rail_ramp = [0.0, 0.0]
    if rail:
        r0 = rail["claimed_half_m"]
        r1 = start_m + (G["rod_a1"] + G["rail_pad"]) * L
        th = rail["thick_m"] / 2.0
        drop = max(1e-3, _dot(n, cam.zc))
        need0, slope = 0.0, 0.0
        for i in range(41):
            uu = r0 + (r1 - r0) * i / 40.0
            worst = -1e9
            for vv in (-th, 0.0, th):
                Pw = [O_rail[k] + u[k] * uu + v[k] * vv for k in range(3)]
                ppx, ppy, D = cam.project(Pw)
                if not (0 <= ppx < W and 0 <= ppy < H):
                    continue
                baked = dep[int(ppy) * W + int(ppx)]
                if baked >= 1e9:
                    continue
                worst = max(worst, (D - baked + lift_margin * ub) / drop)
            if worst < -1e8:
                continue
            if i == 0:
                need0 = max(0.0, worst)
            elif uu > r0:
                slope = max(slope, (worst - need0) / (uu - r0))
        rail_ramp = [need0, need0 + slope * (r1 - r0)]

    foot_top = lift + (-G["collar_b"] * L) * math.sin(math.radians(rake_deg))
    for uu in (start_m + G["foot_a0"] * L, start_m + G["foot_a1"] * L):
        for vv in (-G["foot_w"] * L, G["foot_w"] * L):
            for nn in (0.0, max(foot_top, 0.0)):
                Pw = [O_rail[i] + u[i] * uu + v[i] * vv + n[i] * nn
                      for i in range(3)]
                fx, fy, _ = cam.project(Pw)
                bx0, bx1 = min(bx0, fx), max(bx1, fx)
                by0, by1 = min(by0, fy), max(by1, fy)
    hot = [bx0 - 4, bx1 + 4, by0 - 4, by1 + 4]

    def ov(a, b):
        return (max(0.0, min(a[1], b[1]) - max(a[0], b[0])) *
                max(0.0, min(a[3], b[3]) - max(a[2], b[2])))

    def gap(a, b):
        return max(0.0, max(b[0] - a[1], a[0] - b[1], b[2] - a[3], a[2] - b[3]))

    clear = [{"what": nm, "overlap_px2": ov(hot, r), "gap_px": gap(hot, r)}
             for nm, r in _rects(S)]

    solid = tot = 0
    depths = []
    for yy in range(int(by0), int(by1) + 1):
        for xx in range(int(bx0), int(bx1) + 1):
            if 0 <= xx < W and 0 <= yy < H:
                tot += 1
                d = dep[yy * W + xx]
                if d < 1e9:
                    solid += 1
                    depths.append(d)

    # ---- IS THE MARGIN A MARGIN?  See THE STAND-OFF FLOOR in refit_port.py.
    # `lift_margin` is in multiples of `ubias_m` exactly as the port's
    # `seat_margin` is, and on a module whose `ubias_m` is a sweep optimum
    # rather than a gap it is not a stand-off at all -- FMM's default 2.5
    # answers `lift 0.0` and every printed ratio still reads healthy.  The
    # window is the one that was passed if there was one, and otherwise the
    # patch of carrier the fitting actually covers, which is the honest answer
    # to "whose gradient".
    mwin = carrier_window or (int(bx0), int(bx1), int(by0), int(by1))
    mrep = margin_report(dep, W, H, mwin, ub, lift_margin)

    # ============================================================= CANTILEVER
    # `carrier_solid_pct` CANNOT SEE A RAIL THAT HAS LEFT ITS CARRIER.
    #
    # Two rails in the fan-out were caught by that percentage -- OTA's landed
    # on starfield (2.3 % solid) and MTA's ran off a panel edge -- and the
    # third was not.  IPM's rail-mounted mast reports 100.0 % solid, every
    # clearance 0 px^2 and `lift 0.0` while hanging in the PORT's plane over a
    # FLOOR 190 to 310 mm behind it: a 250 px cantilever off the side of a
    # column, a quarter of a metre in front of everything under it.  Every
    # printed number passed.
    #
    # The reason is that `_solve_lift()` only ever asks the MINIMUM question --
    # "is any part of this behind the baked plate?" -- because that is the one
    # the depth composite acts on.  Nothing asked how far in FRONT the fitting
    # is, and "in front" has no upper bound in a solver that seats things by
    # lifting them.
    #
    # So the maximum is measured too, and it is compared with the PORT's own
    # carrier depth, which is exactly what IPM NOTES 13 item 2 asks for.  Both
    # are reported on every route; the REFUSAL is scoped to the rail route,
    # where the mast lies in the port's frame and therefore has no carrier of
    # its own -- on the `--at` route the fitting is seated on the surface it
    # was measured against, and a mast on a different, deeper carrier than the
    # port is a normal, shipped answer (OTA, MTA, IPM all take it).
    so_lo, so_hi = _stand_off_range(cam, O, A_ax, B_ax, C_ax, L, dep, W, H,
                                    _hull_samples(G, m, kind, numbers))
    port_depth = None
    if R and R.get("evidence") and R["evidence"].get("carrier_depth_m"):
        port_depth = list(R["evidence"]["carrier_depth_m"])
    cantilever = None
    if so_hi is not None:
        cantilever = {
            "stand_off_m": [so_lo, so_hi],
            "stand_off_over_L": so_lo / L if L else 0.0,
            "stand_off_max_over_L": so_hi / L if L else 0.0,
            "floor_L": CANTILEVER_L,
            "carrier_depth_m": [min(depths), max(depths)] if depths else None,
            "port_carrier_depth_m": port_depth,
            "behind_port_carrier_m": (
                None if port_depth is None or not depths
                else min(depths) - port_depth[0]),
            "cantilever": (so_lo / L if L else 0.0) > CANTILEVER_L,
        }

    look = cam.zc
    out = {
        "code": code, "kind": kind, "mount": mount,
        "mast_px": mast_px, "m": m, "numbers": bool(numbers),
        "L_m": L, "lift_m": lift, "start_m": start_m, "rake_deg": rake_deg,
        "ubias_m": ub,
        "frame": frame, "frame_blender": frame.blender(),
        "carrier": {"u": list(u), "v": list(v), "n": list(n),
                    "origin": list(O_rail)},
        "carrier_blender": PortFrame(O_rail, u, v, n).blender(),
        "rail": rail,
        "rail_ramp": rail_ramp,
        "bbox": [bx0, bx1, by0, by1],
        "hotspot": {"x": round(max(0.0, hot[0]), 2),
                    "y": round(max(0.0, hot[2]), 2),
                    "w": round(min(cam.W, hot[1]) - max(0.0, hot[0]), 2),
                    "h": round(min(cam.H, hot[3]) - max(0.0, hot[2]), 2)},
        "clearances": clear,
        "carrier_solid_pct": 100.0 * solid / max(1, tot),
        "carrier_depth_m": [min(depths), max(depths)] if depths else None,
        "off_frame": not (0 <= bx0 and bx1 < W and 0 <= by0 and by1 < H),
        "obliq_face": math.degrees(math.acos(
            max(-1.0, min(1.0, _dot(C_ax, look))))),
        "obliq_carrier": math.degrees(math.acos(
            max(-1.0, min(1.0, _dot(n, look))))),
        "px_per_m_A": axis_px_per_m(cam, O, A_ax),
        "px_per_m_B": axis_px_per_m(cam, O, B_ax),
        "px_per_m_carrier_v": axis_px_per_m(cam, O, v),
        "px_per_m_carrier_n": axis_px_per_m(cam, O, n),
        "rakes": rake_table(cam, u, v, n),
        "carrier_resid": ([resid[len(resid) // 2], resid[-1]]
                          if resid else None),
        "lift_over_ubias": lift / ub if ub else 0.0,
        # what one graduation is worth on screen -- the "can you count them"
        # number, and the only one that says whether M is buildable at all
        "grad_px": (G["bore_a1"] - G["bore_a0"]) * L
                   * axis_px_per_m(cam, O, A_ax) / max(1, m),
        "margin": mrep,
        "cantilever": cantilever,
        "carrier_window": list(mwin),
    }
    if mrep["thin"]:
        raise ThinMargin(margin_message(code, "lift_margin", "--lift-margin",
                                        ub, lift_margin, mrep), out)
    if cantilever and cantilever["cantilever"]:
        raise Cantilever(cantilever_message(code, mount, L, cantilever), out)
    if verbose:
        print_mast(out)
    return out


def _poc_count(code):
    """M -- the PoC count, from `live3d/status.json` if it is there.

    `total` is the count of `vuln_tests/NN_*.py` and NEVER `max(NN)`; the
    numbering has gaps (FMM has no 03 or 06, IPM no 05, OTA no 08) and
    `max(NN)` draws graduations that can never fill.  section 9.4 rule 4.
    """
    try:
        d = json.load(open(os.path.join(LIVE3D, "status.json")))
        rec = (d.get("modules") or {}).get(code) or {}
        v = rec.get("vulns") or {}
        items = v.get("items") or []
        return max(int(v.get("total") or 0), len(items)) or 6
    except Exception:                                           # noqa: BLE001
        return 6


def print_mast(A):
    print("TELLTALE MAST anchor -- %s  (%s)" % (A["code"], A["kind"]))
    print("  mount                   %s" % A["mount"])
    if A["rail"]:
        print("  rail                    free_from %.4f m  thick %.4f m  "
              "proud %.4f m" % (A["rail"]["free_from_m"],
                                A["rail"]["thick_m"], A["rail"]["proud_m"]))
        print("  rail ramp               underside %.4f m at the port end -> "
              "%.4f m at the far end" % (A["rail_ramp"][0], A["rail_ramp"][1]))
    print("  L (along A)             %.4f m  for %d px   graduations %d "
          "(%.1f px each)" % (A["L_m"], A["mast_px"], A["m"], A["grad_px"]))
    print("  rake                    %.1f deg off the carrier" % A["rake_deg"])
    print("  obliquity, mast face    %.2f deg   (the carrier itself is "
          "%.2f deg)" % (A["obliq_face"], A["obliq_carrier"]))
    print("  px/m  A %.1f   B %.1f      (carrier v %.1f   n %.1f)"
          % (A["px_per_m_A"], A["px_per_m_B"],
             A["px_per_m_carrier_v"], A["px_per_m_carrier_n"]))
    M = A.get("margin")
    if M:
        # THE RATIO IS NOT THE NUMBER -- see print_anchor()'s twin.
        print("  carrier depth gradient  %.7f m/px (p50 over %d samples, "
              "p95 %.7f)" % (M["grad_m_per_px"], M["grad_n"],
                             M["grad_p95_m_per_px"]))
        print("  stand-off margin        %.7f m = %s px of that gradient  "
              "(floor %.2f)%s"
              % (M["margin_m"],
                 "inf" if M["margin_px"] == float("inf")
                 else "%.2f" % M["margin_px"],
                 M["floor_px"], "   <-- !! THIN" if M["thin"] else ""))
    print("  lift over the carrier   %.6f m vs %.6f m ubias  (%.1fx)"
          % (A["lift_m"], A["ubias_m"], A["lift_over_ubias"]))
    print("  envelope                %.1f..%.1f x %.1f..%.1f px  (%.1f x %.1f)"
          % (A["bbox"][0], A["bbox"][1], A["bbox"][2], A["bbox"][3],
             A["bbox"][1] - A["bbox"][0], A["bbox"][3] - A["bbox"][2]))
    print("  hotspot                 %s" % (A["hotspot"],))
    print("  off frame               %s" % A["off_frame"])
    if A["carrier_depth_m"]:
        print("  carrier solid behind    %.1f %%   depth %.4f .. %.4f m"
              % (A["carrier_solid_pct"], A["carrier_depth_m"][0],
                 A["carrier_depth_m"][1]))
    # READ THIS BESIDE THE PERCENTAGE, NEVER INSTEAD OF IT.  100 % solid says
    # there is something behind every pixel of the fitting; it does not say the
    # fitting is anywhere near it.  IPM NOTES 13 item 2.
    C = A.get("cantilever")
    if C:
        print("  stand-off, min .. max   %.4f .. %.4f m  (closest point "
              "%.3f x L, floor %.2f)%s"
              % (C["stand_off_m"][0], C["stand_off_m"][1],
                 C["stand_off_over_L"], C["floor_L"],
                 "   <-- !! CANTILEVER" if C["cantilever"] else ""))
        if C["port_carrier_depth_m"]:
            print("  vs the PORT's carrier   %.4f .. %.4f m   this one is "
                  "%+.4f m behind it"
                  % (C["port_carrier_depth_m"][0], C["port_carrier_depth_m"][1],
                     C["behind_port_carrier_m"]))
    for c in A["clearances"]:
        print("    vs %-16s overlap %7.0f px2   gap %6.1f px  %s"
              % (c["what"], c["overlap_px2"], c["gap_px"],
                 "" if c["overlap_px2"] == 0 else "<-- !! TOUCHES"))
    print("  rake table (pick yours, do not inherit KVS's):")
    print("      %-8s %-10s %s" % ("rake", "obliquity", "note"))
    for r in A["rakes"]:
        print("      %-8.0f %-10.2f %s"
              % (r["rake_deg"], r["obliq_deg"],
                 "<-- shipped" if abs(r["rake_deg"] - A["rake_deg"]) < 0.5
                 else ""))


# ===========================================================================
# BLENDER -- everything below needs bpy.  Import is deferred so the solver
# above runs under plain python3.
# ===========================================================================
def _M(k):
    return RP._material("sm_" + k, MATS[k])


def _plate(name, F, poly, c0, c1, mat):
    """A closed solid from a CCW (A, B) polygon, extruded along +C.

    CLOSED, so `THREE.FrontSide` cannot delete it.  Every part of this mast is
    one of these or a `_dome`/`_shell`; there is no single-quad anything.
    Trap 21.
    """
    return RP._prism(name, F, poly, c0, c1, mat)


def _bar(name, F, a0, a1, b0, b1, c0, c1, mat):
    return _plate(name, F, [(a0, b0), (a1, b0), (a1, b1), (a0, b1)],
                  c0, c1, mat)


def _slant(name, F, a_lo, a_hi, b0, b1, skew, c0, c1, mat):
    """A parallelogram leaning by `skew` in A across the B span -- one hazard
    chevron, one hatch bar, one scrim bar.  Closed prism, 12 tris."""
    return _plate(name, F,
                  [(a_lo, b0), (a_hi, b0), (a_hi + skew, b1), (a_lo + skew, b1)],
                  c0, c1, mat)


def build(name, F_mast, F_carrier, L, m=6, kind="defensive", root_scale=1.0,
          numbers=False, rail=None, ramp=None, rail_from=None, rail_to=None,
          geo=None):
    """The mast itself.  Returns {objects, parts, manifest}.

    name         object-name prefix, e.g. "kvs_mast"
    F_mast       PortFrame(origin, A, B, C) in the space you are authoring in
    F_carrier    PortFrame(rail origin, u, v, n) -- the bracket and the rail
                 extension are built in THIS frame, so they touch the carrier
                 whatever the rake is
    L            the mast's length along A, in WORLD metres
    m            graduations = PoC count.  section 9.4 rule 4: the count of
                 `vuln_tests/NN_*.py`, never `max(NN)`.
    kind         "defensive" (tube + vane) or "offensive" (tally stick, PKT)
    root_scale   the scale of the root you are authoring INSIDE.  DNSM 0.78,
                 MQB 0.70, PKT 1.15 -- pass it and L stays the world size you
                 asked for.
                 IT IS 1.0 ON THE `-- mast` ENTRY POINT, which clears the
                 scene and authors in world coordinates: there is no root to
                 be inside.  `refit_port.check_root_scale()` REFUSES a
                 non-unit value in an empty scene rather than shipping a
                 1/0.70 = 1.43x mast, and prints the authoring-space and world
                 lengths either way.
    rail         the port's published `service_rail` dict, so the extension is
                 built to the SAME cross-section rather than to a second guess

    EVERY PART IS A CLOSED SOLID.  Trap 21 names "swept ribbons, FLAGS, tape,
    curtains, single-quad labels" and OTA lost 14 single-triangle chevrons to
    it with `auditScene()` still reporting `[]`.  The vane, the hazard
    chevrons, the hatch bars and the scrim bars are all exactly that shape and
    all of them are prisms here.
    """
    G = dict(GEO)
    if geo:
        G.update(geo)
    # REFUSES A root_scale THAT HAS NO ROOT.  The `-- mast` entry point clears
    # the scene and builds in WORLD coordinates, so root_scale is 1.0 there
    # whatever the module's own main() uses; passing MQB's 0.70 would have
    # shipped the mast 1.43x too big with nothing printed.  See
    # `refit_port.check_root_scale()`.
    root_scale = RP.check_root_scale(root_scale, "status_mast.build", "L", L)
    s = L / float(root_scale)              # authoring-space L
    objs, parts = [], {}
    F, K = F_mast, F_carrier

    def P(k):
        return G[k] * s

    # ---------------------------------------------------------- the bracket
    # Built in the CARRIER frame: from the carrier plane (so it spans whatever
    # the rail's seat is) up to the mast's own back face.  A raked face needs
    # something under it; without this the plate's lower edge floats.
    if K is not None:
        parts.update(_build_foot(name, F, K, s, G, objs))

        # ------------------------------------------------- the service rail
        # Continue the PORT's rail from where it stops.  Same cross-section,
        # read from its own published block; FIX_UPLOAD 12.13 / KVS NOTES 12.
        if rail:
            # where the mast's A = 0 sits along the rail, from the frames
            # themselves rather than from a number passed in twice
            u0 = _dot(_sub(F.to_world(0.0, 0.0, 0.0), K.o), K.u)
            r0 = rail_from if rail_from is not None else rail["claimed_half_m"]
            r1 = (rail_to if rail_to is not None
                  else u0 + s * (G["rod_a1"] + G["rail_pad"]))
            th, pd = rail["thick_m"] / 2.0, rail["proud_m"]
            z0, z1 = (ramp or (0.0, 0.0))
            # A SLANTED BAR, not a flush one.  See THE RAIL RAMP in
            # solve_mast(): the deck is not flat over this run and a rail
            # lying in the fitted plane is deleted at its far end AND moves
            # the module's ubias_m.  Eight vertices, one solid, closed.
            vs = []
            for (uu, zz) in ((r0, z0), (r1, z1)):
                for (vv, nn) in ((-th, zz), (th, zz), (th, zz + pd),
                                 (-th, zz + pd)):
                    vs.append(K.to_world(uu, vv, nn))
            fs = [(0, 3, 2, 1), (4, 5, 6, 7),
                  (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
            o = RP._mesh(name + "_srail", vs, fs, _M("brass_dk"))
            objs.append(o)
            parts["service_rail"] = o.name
            parts["service_rail_span_m"] = [r0, r1]
            parts["service_rail_ramp_m"] = [z0, z1]

    # ------------------------------------------------- collar, rod, head knob
    objs.append(_bar(name + "_collar", F, P("collar_a0"), P("collar_a1"),
                     -P("collar_b"), P("collar_b"), 0.0, P("c_collar"),
                     _M("brass")))
    parts["collar"] = objs[-1].name
    objs.append(_bar(name + "_rod", F, P("rod_a0"), P("rod_a1"),
                     -P("rod_b"), P("rod_b"), 0.0, P("c_rod"), _M("brass")))
    parts["rod"] = objs[-1].name
    objs.append(_bar(name + "_knob", F, P("knob_a0"), P("knob_a1"),
                     -P("knob_r"), P("knob_r"), 0.0, P("c_rod"),
                     _M("brass_dk")))
    parts["knob"] = objs[-1].name

    if kind == "offensive":
        parts.update(_build_tally(name, F, s, G, objs))
    else:
        parts.update(_build_tube(name, F, s, G, m, objs, numbers))
        parts.update(_build_vane(name, F, s, G, objs))

    parts.update(_build_cap(name, F, s, G, objs, kind))

    # ------------------------------------------- STALE -- section 7, and 14.4
    # Scoped to the BEZEL AND CAP, not the whole envelope.  Built envelope-wide
    # first in the wide shot and it painted diagonals across bare plate and
    # read as somebody having hatched the dash.  Every scrim bar here is on
    # opaque hardware, which is the same rule section 4.4 imposes on colour.
    #
    # AND SIZED TO THE HARDWARE THIS VARIANT ACTUALLY BUILDS.  The bars used to
    # span `bezel_a0 .. cap_a + cap_r` at +/- `bezel_b` (0.0769 L) with a skew
    # of 1.6 x that, on BOTH variants.  The offensive fitting has no bezel: its
    # tally stick is only +/- `tally_b` (0.0641 L, a 1.6x skew on the wrong
    # number), it ends at 0.8205 L, and between there and the cap bead there is
    # no hardware at all -- so five long diagonals overhung the fitting top,
    # bottom and right and landed on the DASH, visible at pixelRatio 1.  That
    # is precisely the failure section 6.5 item 7 records for the wide shot
    # ("it painted diagonals across bare plate and read as somebody having
    # hatched the dash") arriving again on the close-up's offensive branch.
    # Latent on PKT's shipped record -- its `status.json` carries no
    # `source_rev`, so `stale` is false -- and one field away.  PKT NOTES 13
    # item 4.
    #
    # So the scrim is scoped to what is under it: `scrim_b` and the A span come
    # from the variant, and the cap bead gets its OWN bar sized to the bead
    # instead of a bezel-width diagonal reaching past it.  The DEFENSIVE path
    # is unchanged to the vertex -- same five bars, same numbers -- because six
    # defensive masts are built and on record.
    scr = []
    off = (kind == "offensive")
    sw = P("scrim_w")
    if off:
        # OFFENSIVE: the bars go on the STICK, at the stick's own half-width,
        # and the SWEPT parallelogram is contained -- `_slant` leans by `skew`
        # in A across the whole B span, so an uncentred bar reaches `skew`
        # past its own end.  Centre the lean and inset the run by half of it,
        # and every vertex is over brass.
        sb = G["tally_b"] * s
        a0, a1 = G["bezel_a0"] * s, G["bezel_a1"] * s
        skew = sb * 1.6
        lo, hi = a0 + sw + skew / 2.0, a1 - sw - skew / 2.0
        for i in range(G["scrim_n"]):
            t = lo + (hi - lo) * (i + 0.5) / G["scrim_n"]
            o = _slant("%s_scrim_%d" % (name, i), F,
                       t - sw - skew / 2.0, t + sw - skew / 2.0,
                       -sb, sb, skew,
                       P("c_haz"), P("c_scrim"), _M("grad"))
            scr.append(o.name)
            objs.append(o)
        # STALE still has to reach the CAP -- section 14.4 scopes it to "bezel
        # AND CAP", and on this variant the cap is the ARM lamp.  One bar
        # across the bead, sized to the BEAD (the stick has already ended):
        # half-width 0.72 x cap_r, lean centred, inside the disc.
        cr, ca = G["cap_r"] * s, G["cap_a"] * s
        cskew = cr * 0.56
        o = _slant("%s_scrim_%d" % (name, G["scrim_n"]), F,
                   ca - sw - cskew / 2.0, ca + sw - cskew / 2.0,
                   -cr * 0.72, cr * 0.72, cskew,
                   P("c_rod") + cr * 0.55, P("c_rod") + cr * 1.05, _M("grad"))
        scr.append(o.name)
        objs.append(o)
    else:
        # DEFENSIVE: UNCHANGED, to the vertex.  Six defensive masts are built
        # and on record and two more are about to be; this branch is exactly
        # the code that built them.  (Its last bar leans past the cap bead by
        # about 0.06 L for the same `_slant` reason -- reported in
        # STATUS_AT_A_GLANCE section 17, not changed here.)
        a0, a1 = G["bezel_a0"] * s, (G["cap_a"] + G["cap_r"]) * s
        span = a1 - a0
        for i in range(G["scrim_n"]):
            t = a0 + span * (i + 0.5) / G["scrim_n"]
            o = _slant("%s_scrim_%d" % (name, i), F,
                       t - sw, t + sw,
                       -P("bezel_b"), P("bezel_b"), P("bezel_b") * 1.6,
                       P("c_haz"), P("c_scrim"), _M("grad"))
            scr.append(o.name)
            objs.append(o)
    parts["scrim"] = scr

    tris, per = 0, {}
    for o in objs:
        o.data.calc_loop_triangles()
        t = len(o.data.loop_triangles)
        per[o.name] = t
        tris += t
    print("  telltale mast: %d tris over %d objects" % (tris, len(objs)))
    for k in sorted(per, key=lambda k: -per[k])[:12]:
        print("      %-28s %5d" % (k, per[k]))

    return {"objects": objs, "parts": parts, "tris": tris, "tris_per": per,
            "L": L, "m": m, "kind": kind, "geo": G}


def _build_foot(name, F, K, s, G, objs):
    """The bracket, built in the CARRIER frame so it always touches down.

    A raked face needs something under it.  The plinth runs from the carrier
    plane (so it spans whatever seat the rail sits at) up to the mast plate's
    own lower-back edge, and that edge's height is COMPUTED from the two
    frames rather than typed -- the rake is a parameter, and a typed height
    would be wrong the moment anyone changed it.
    """
    # the plate's lower-back edge, expressed in the carrier's (u, v, n)
    lo = F.to_world(0.0, -G["collar_b"] * s, 0.0)
    d = _sub(lo, K.o)
    u0, n0 = _dot(d, K.u), _dot(d, K.n)
    top = max(n0, 1e-4)
    poly = [(u0 + G["foot_a0"] * s, -G["foot_w"] * s),
            (u0 + G["foot_a1"] * s, -G["foot_w"] * s),
            (u0 + G["foot_a1"] * s, G["foot_w"] * s),
            (u0 + G["foot_a0"] * s, G["foot_w"] * s)]
    o = _plate(name + "_foot", K, poly, 0.0, top, _M("brass_dk"))
    objs.append(o)
    return {"foot": o.name, "foot_top_m": top,
            "foot_u_m": [poly[0][0], poly[1][0]]}


def _build_tube(name, F, s, G, m, objs, numbers):
    """The security axis -- section 2.3.  A real glass tube in a brass bezel.

    THE COLOUR IS INSIDE THE BEZEL, ALWAYS.  Section 4.4 measured that
    `#D9342B` has a minimum luma delta of 0.00 against LOG's and MTA's hull;
    the whole design survives that by never letting a status colour touch the
    plate.  In geometry that becomes: the fill sits in a WELL 0.060 L deep, its
    top face recessed 0.020 L below the bezel rim, so the rim's own shadow
    frames every coloured pixel from three sides at any camera.
    """
    parts = {}

    def P(k):
        return G[k] * s

    a0, a1 = P("bore_a0"), P("bore_a1")
    bb, bo = P("bezel_b"), P("bore_b")

    # the bezel: four rim bars and a floor, not a shell.  Closed solids, and
    # the two long rims are the parts the hazard stripes land on.
    objs.append(_bar(name + "_bezel_t", F, P("bezel_a0"), P("bezel_a1"),
                     bo, bb, 0.0, P("c_bezel"), _M("bezel")))
    objs.append(_bar(name + "_bezel_b", F, P("bezel_a0"), P("bezel_a1"),
                     -bb, -bo, 0.0, P("c_bezel"), _M("bezel")))
    objs.append(_bar(name + "_bezel_l", F, P("bezel_a0"), a0, -bb, bb,
                     0.0, P("c_bezel"), _M("bezel")))
    objs.append(_bar(name + "_bezel_r", F, a1, P("bezel_a1"), -bb, bb,
                     0.0, P("c_bezel"), _M("bezel")))
    parts["bezel"] = [o.name for o in objs[-4:]]
    objs.append(_bar(name + "_bore", F, a0, a1, -bo, bo, 0.0, P("c_floor"),
                     _M("glass")))
    parts["bore"] = objs[-1].name

    # M cells, one per PoC.  The tube is ALWAYS the same length and always
    # carries exactly M graduations, so a 4-PoC module and an 8-PoC one stay
    # comparable by fraction and countable by tick (section 2.2).
    seg = []
    step = (a1 - a0) / float(max(1, m))
    for k in range(m):
        o = _bar("%s_seg_%d" % (name, k), F,
                 a0 + step * k + P("grad_t"), a0 + step * (k + 1) - P("grad_t"),
                 -P("seg_b"), P("seg_b"), P("c_floor"), P("c_seg"), _M("fill"))
        seg.append(o.name)
        objs.append(o)
        # the 45-degree HATCH bar -- section 2.3's `inconclusive`.  A hatch
        # PATTERN is unreadable at one cell's width; one diagonal bar standing
        # over the cell is the same read and survives being small.
        o = _slant("%s_hatch_%d" % (name, k), F,
                   a0 + step * k + step * 0.22, a0 + step * k + step * 0.48,
                   -P("seg_b"), P("seg_b"), step * 0.34,
                   P("c_seg") + 0.002 * s, P("c_hatch"), _M("grad"))
        objs.append(o)
    parts["segments"] = seg
    parts["hatch"] = [name + "_hatch_%d" % k for k in range(m)]

    # graduations: m - 1 interior ribs, flush with the rim.  UNTESTED hides
    # them -- "no scale on the instrument" is the untested tell and it is a
    # second mark on top of the cap bead, deliberately (section 2.3).
    gr = []
    for k in range(1, m):
        o = _bar("%s_grad_%d" % (name, k), F,
                 a0 + step * k - P("grad_t"), a0 + step * k + P("grad_t"),
                 -bo, bo, P("c_floor"), P("c_bezel"), _M("grad"))
        gr.append(o.name)
        objs.append(o)
    parts["grads"] = gr

    # the RUNNING sweep -- section 2.3.  One band, translated along A by the
    # frontend off the module's own frame loop.  It rests at A = bore_a0 and
    # `pose()` parks it there, so there is no timer and no drift.
    o = _bar(name + "_sweep", F, a0, a0 + P("sweep_a"),
             -P("seg_b"), P("seg_b"), P("c_seg"), P("c_seg") + 0.010 * s,
             _M("fill"))
    objs.append(o)
    parts["sweep"] = o.name
    parts["sweep_travel_m"] = (a1 - a0) - P("sweep_a")

    # HAZARD STRIPES on the bezel -- section 2.4's loud mark, the one that has
    # to out-shout a full red tube.  Chevrons standing 0.013 L over the rim, so
    # they read as a striped SLEEVE over the bezel and not as paint on it.
    # ON THE RIMS, NOT ACROSS THE BORE, and that is not a detail.  The wide
    # shot's `hazardBezel()` draws its chevrons over the 12 x 48 bezel and then
    # draws the BORE ON TOP of them, so the tube stays readable underneath;
    # built across the whole bezel in 3D the stripes hid the fill completely
    # and "made it worse" lost its security axis -- the one cell where BOTH
    # axes have to be read at once.  Two chevrons per index, one on each rim.
    haz = []
    span = P("bezel_a1") - P("bezel_a0")
    rim = bb - bo
    for i in range(G["haz_n"]):
        t = P("bezel_a0") + span * (i + 0.5) / G["haz_n"]
        for j, (r0, r1) in enumerate(((bo, bb), (-bb, -bo))):
            o = _slant("%s_haz_%d_%d" % (name, i, j), F,
                       t - P("haz_w"), t + P("haz_w"), r0, r1, rim * 1.7,
                       P("c_bezel"), P("c_haz"), _M("hazard"))
            haz.append(o.name)
            objs.append(o)
    parts["hazard"] = haz

    # THE PILOT-LAMP ROW, in CATALOGUE order -- section 6.1.  This is where the
    # ordering flips from "sorted by state" (the tube) to "sorted by identity",
    # because in the close-up you are choosing WHICH vuln to work on.
    lamps = []
    objs.append(_bar(name + "_lampbar", F, a0 - P("grad_t"), a1 + P("grad_t"),
                     P("lampbar_b"), P("lampbar_b1"), 0.0, P("c_rod"),
                     _M("brass_dk")))
    parts["lampbar"] = objs[-1].name
    for k in range(m):
        c = a0 + step * (k + 0.5)
        o = RP._dome("%s_lamp_%d" % (name, k), F, c, P("lamp_b"), P("lamp_r"),
                     P("c_rod"), P("lamp_r") * 0.85, _M("lens"), seg=8, rings=2)
        lamps.append(o.name)
        objs.append(o)
    parts["lamps"] = lamps

    if numbers:
        # STAMPED type, the same class as KVS's baked drawer labels -- not
        # content text.  Off by default and the reason is measured, in the
        # design's section 6 build note.
        nums = []
        for k in range(m):
            c = a0 + step * (k + 0.5)
            o = RP._engrave("%s_num_%d" % (name, k), F, "%02d" % (k + 1),
                            c, P("num_b"), P("c_rod"), P("num_h"), _M("ink"))
            nums.append(o.name)
            objs.append(o)
        parts["numbers"] = nums
    return parts


def _build_vane(name, F, s, G, objs):
    """The function axis -- section 2.4.  Binary, so a SHAPE, not a bar.

    TRAP 21 LIVES HERE.  `dress()` forces `THREE.FrontSide` and deletes
    one-sided Blender geometry with no error and an empty `auditScene()`; the
    trap's own list of casualties is "swept ribbons, FLAGS, tape, curtains,
    single-quad labels" and OTA lost 14 single-triangle chevrons to it.  A vane
    is exactly that shape.  This one is a CLOSED PRISM with real thickness, so
    it survives FrontSide by construction rather than by a `DoubleSide` that a
    later edit could drop.
    """
    def P(k):
        return G[k] * s
    va, vw, vl = P("vane_a"), P("vane_w"), P("vane_len")
    # a taut pennant: full chord at the mast, tapering to a point at the fly
    poly = [(va - vw * 0.5, 0.0), (va + vw * 0.5, 0.0),
            (va + vw * 0.15, vl), (va - vw * 0.15, vl)]
    o = _plate(name + "_vane", F, poly, P("c_rod") - P("vane_t") / 2,
               P("c_rod") + P("vane_t") / 2, _M("brass"))
    objs.append(o)
    return {"vane": o.name, "vane_pivot_ab": [va, 0.0],
            "vane_pivot_c": G["c_rod"] * s}


def _build_cap(name, F, s, G, objs, kind):
    """The cap bead -- section 2.5, the cell that matters.

    "Fixed it by breaking it" is NOT left to be inferred from two independent
    marks.  It gets a third, and in geometry it gets four physically different
    objects rather than four colours of one, because at this size a colour swap
    on an 8 px disc is the weakest discrimination in the design:

      bead              the win / anything else       (colour, from status.js)
      ring              the vuln axis is UNTESTED     (a hollow annulus)
      stripes           HOLLOW VICTORY                (chevrons cut across it)
      cross             the HARNESS failed, not you   (section 7)

    On PKT (`kind="offensive"`) the same bead is the ARM lamp: dark = SAFE,
    steady = ARMED, striped = INTERLOCK.  Same hardware, different meaning,
    which is section 8's whole argument.
    """
    def P(k):
        return G[k] * s
    ca, cr = P("cap_a"), P("cap_r")
    parts = {}
    o = RP._dome(name + "_cap", F, ca, 0.0, cr, P("c_rod"), cr * 0.95,
                 _M("green"), seg=12, rings=3)
    objs.append(o)
    parts["cap"] = o.name

    # the hollow ring: a flat annulus around the bead
    ringF = PortFrame(F.to_world(ca, 0.0, 0.0), F.u, F.v, F.n)
    o = RP._shell(name + "_capring", ringF,
                  [(cr * 1.00, P("c_rod")), (cr * 1.34, P("c_rod")),
                   (cr * 1.34, P("c_rod") + cr * 0.30),
                   (cr * 1.00, P("c_rod") + cr * 0.30)],
                  _M("grad"), sides=12)
    objs.append(o)
    parts["cap_ring"] = o.name

    st = []
    # THE CHEVRONS OVERHUNG THE BEAD TO THE RIGHT, and `_slant` is why: it
    # leans by `skew` in A across the WHOLE B span, so a bar authored at
    # `ca + t +/- 0.16 cr` with `skew = 0.9 cr` actually reaches
    # `ca + t + 1.06 cr` at its top edge -- 1.66 cr for the outermost of three.
    # The bead's radius is cr.  On the DEFENSIVE variant these are HOLLOW
    # VICTORY's stripes and six masts are built with them, so that branch is
    # untouched; on the OFFENSIVE variant they are the ARM lamp's INTERLOCK
    # mark, PKT is the first render, and they painted on bare dash.  PKT NOTES
    # 13 item 4.  The lean is CENTRED and the run inset so every vertex is
    # inside the bead: worst corner 0.97 cr from its centre against 1.66 cr.
    if kind == "offensive":
        skew = cr * 0.38
        for i in range(3):
            t = -cr * 0.30 + cr * 0.30 * i
            o = _slant("%s_capstripe_%d" % (name, i), F,
                       ca + t - cr * 0.12 - skew / 2.0,
                       ca + t + cr * 0.12 - skew / 2.0,
                       -cr * 0.75, cr * 0.75, skew,
                       P("c_rod") + cr * 0.55, P("c_rod") + cr * 0.95,
                       _M("hazard"))
            st.append(o.name)
            objs.append(o)
    else:
        for i in range(3):
            t = -cr * 0.6 + cr * 0.6 * i
            o = _slant("%s_capstripe_%d" % (name, i), F,
                       ca + t - cr * 0.16, ca + t + cr * 0.16, -cr, cr,
                       cr * 0.9,
                       P("c_rod") + cr * 0.55, P("c_rod") + cr * 0.95,
                       _M("hazard"))
            st.append(o.name)
            objs.append(o)
    parts["cap_stripes"] = st

    cx = []
    o = _bar(name + "_capcross_0", F, ca - cr * 1.15, ca + cr * 1.15,
             -cr * 0.13, cr * 0.13, P("c_rod") + cr * 0.9,
             P("c_rod") + cr * 1.05, _M("grad"))
    cx.append(o.name)
    objs.append(o)
    o = _bar(name + "_capcross_1", F, ca - cr * 0.13, ca + cr * 0.13,
             -cr * 1.15, cr * 1.15, P("c_rod") + cr * 0.9,
             P("c_rod") + cr * 1.05, _M("grad"))
    cx.append(o.name)
    objs.append(o)
    parts["cap_cross"] = cx
    return parts


def _build_tally(name, F, s, G, objs):
    """PKT -- section 8.  INTEGRATED 2026-09-06; PKT is the only module.

    A notched brass tally stick, not a glass tube: different material,
    different silhouette, so nobody reads it as a thermometer.  It fills the
    other way, as GOOD news -- "distinct fleet vulns PKT has personally
    confirmed landing this session" -- and that inversion is exactly why it
    must not look like a tube.
    """
    def P(k):
        return G[k] * s
    a0, a1 = P("bore_a0"), P("bore_a1")
    tb = P("tally_b")
    objs.append(_bar(name + "_tally", F, P("bezel_a0"), P("bezel_a1"),
                     -tb, tb, 0.0, P("c_tally"), _M("brass_dk")))
    notches = []
    n = G["tally_n"]
    step = (a1 - a0) / float(n)
    for k in range(n):
        c = a0 + step * (k + 0.5)
        o = _slant("%s_notch_%d" % (name, k), F,
                   c - step * 0.22, c + step * 0.22, -tb * 0.8, tb * 0.8,
                   step * 0.30, P("c_notch"), P("c_tally") + 0.0015 * s,
                   _M("notch"))
        notches.append(o.name)
        objs.append(o)

    # THE RUNNING SWEEP, ON THIS VARIANT TOO -- and it had none.
    #
    # The band lives in `_build_tube()`, which the offensive branch never
    # calls, so `parts["sweep"]` did not exist, `mast.js`'s `sweepMesh` was
    # null, and a record with `run.state === "running"` rendered IDENTICALLY to
    # `idle`: the caption was the only thing that changed.  Section 7 says the
    # telltale's job in that state is to say *something is happening here*, and
    # on the offensive fitting it did not say it at all.  PKT NOTES 13 item 3.
    #
    # Same shape as the tube's, sized to the STICK rather than to the bore:
    # one bar the width of the notches, riding 0.010 L over the stick's face
    # and translated along +A by the frontend off the module's own frame loop.
    # It rests at A = bore_a0 and `pose()` parks it there, so there is no timer
    # and no drift.  Its C span is inside the bezel box `_hull_samples()`
    # already claims, so the envelope, the hotspot and the lift do not move.
    # NARROWER IN B THAN THE NOTCHES (0.35 tb against their 0.8), so the band
    # crossing a lit notch does not erase it: two thirds of every notch stays
    # visible past it and the count survives the sweep.  The tube's band can be
    # full-width because it runs inside a dark WELL and reads as a glow; this
    # one rides on the lit face of a brass stick, where a full-width block of
    # `INK.sweepCore` reads as a hole punched in the tally.  Looked at, at
    # pixelRatio 2, before and after.
    o = _bar(name + "_sweep", F, a0, a0 + P("sweep_a"),
             -tb * 0.35, tb * 0.35,
             P("c_tally") + 0.0015 * s, P("c_tally") + 0.0115 * s,
             _M("fill"))
    objs.append(o)
    return {"tally": name + "_tally", "notches": notches, "tally_n": n,
            "sweep": o.name, "sweep_travel_m": (a1 - a0) - P("sweep_a")}


# ===========================================================================
# EXPORT -- glb + a "mast" block merged into scene.json.  RE-RENDERS NOTHING.
# ===========================================================================
def export(code, A, P, glb="mast.glb", out_dir=None):
    """Write `<CODE>/mast.glb` and merge a `"mast"` block into `scene.json`.

    `out_dir` REDIRECTS BOTH WRITES and opens nothing in `assets/<CODE>/` for
    writing: the module's own `scene.json` is still READ, the new block is
    merged into a copy, and the copy plus the `.glb` land in `out_dir`.  That
    is how a change to `build()` gets rendered and looked at on the real page
    -- via a route override in the harness -- without touching seven modules
    whose numbers are on record.  It is the only way this pass could render the
    offensive tally stick's new sweep band at all.

    `plate.png`, `depth.bin`, every `gt_*.png`, `materials.json` and the
    module's own `.glb` files are not opened for writing, and `scene.json` is
    edited key-wise rather than rewritten from a fresh export.  That is what
    keeps every number in `live3d/RESULTS.md` and `modules/<CODE>/NOTES.md`
    reproducible -- FIX_UPLOAD section 0 decision 3, applied a second time.

    AFTERWARDS, ALWAYS: `pipeline/live_depth.py <CODE>` globs EVERY `.glb` in
    the asset folder, so this file changes what `ubias.py` is measured on.
    Re-run it and confirm the shipped `ubias_m` has not moved.

    RUN IT WITH BLENDER'S PYTHON, NOT THE SYSTEM ONE: `live_depth.py`
    needs numpy and `/usr/bin/python3` does not have it --
    `/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13
    live3d/pipeline/live_depth.py <CODE>`.  This file and `refit_port.py` are
    pure stdlib and run under plain `python3`; that one is not.
    `ubias_m` should not move -- the mast stands proud of its carrier by
    construction -- but it DID on KVS's first mast build (0.000565 ->
    0.000034, a flush rail crossing a deck that rises 7 mm across its run).
    Confirm it anyway.
    """
    Adir = os.path.join(LIVE3D, "assets", code)
    dst = out_dir or Adir
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    RP.export_glb(P["objects"], os.path.join(dst, glb))

    sp = os.path.join(Adir, "scene.json")
    S = json.load(open(sp))
    F = A["frame"]
    L = P["L"]
    G = P["geo"]

    def w3(a, b, c):
        return [round(t, 9) for t in F.to_world(a, b, c)]

    def d3(vec):
        return [round(t, 9) for t in vec]

    pk = P["parts"]

    # THE RAIL EXTENSION'S OWN SCREEN SPAN, published separately.
    #
    # The mast's hotspot deliberately does NOT cover it: the rail runs 1.9 L
    # back toward the refit port and a 350 px pointer target on shared
    # structure would collide with everything.  But the rail IS in `mast.glb`,
    # so it IS part of what appears when the mast is shown, and the
    # "every differing pixel is inside a declared rect" proof that replaces
    # `check_occlusion.py`'s section 0 needs it named.  Without this the proof
    # comes up 1,485 px short at pixelRatio 1 and the pixels are all on the
    # rail.
    cam = Camera(S)
    C = A["carrier"]
    # NO RAIL MEANS `null`, NOT A ZERO-AREA RECT AT THE ANCHOR.
    #
    # `build()` only writes `service_rail_span_m` when it actually built a
    # rail.  On the `--at` route there is no rail at all, and this used to
    # default the span to [0.0, 0.0] with a zero thickness and a zero proud
    # height, project eight coincident points, and publish
    # `[px, px, py, py]` -- a degenerate rectangle sitting on the anchor.
    # Harmless to look at and wrong to use: a consumer that unions
    # `rail_bbox_px` into a keep-out set gets a point in the middle of the
    # fitting and quietly biases every solver that reads it.  MTA NOTES
    # section 10 item 9.
    if pk.get("service_rail") is None:
        rail_bbox = None
    else:
        r0, r1 = pk["service_rail_span_m"]
        th = (A["rail"] or {}).get("thick_m", 0.0) / 2.0
        pr = (A["rail"] or {}).get("proud_m", 0.0)
        rxs, rys = [], []
        # THE RAMP THAT WAS BUILT, not the one solve_mast() proposed -- see
        # `rail_ramp_m` below, which had the same bug and is the one that
        # shipped wrong.
        ramp = pk.get("service_rail_ramp_m", [0.0, 0.0])
        for uu, zz in ((r0, ramp[0]), (r1, ramp[1])):
            for vv in (-th, th):
                for nn in (zz, zz + pr):
                    Pw = [C["origin"][i] + C["u"][i] * uu + C["v"][i] * vv
                          + C["n"][i] * nn for i in range(3)]
                    x, y, _ = cam.project(Pw)
                    rxs.append(x)
                    rys.append(y)
        rail_bbox = ([round(min(rxs), 2), round(max(rxs), 2),
                      round(min(rys), 2), round(max(rys), 2)] if rxs else None)

    block = {
        "glb": glb,
        "kind": "telltale_mast",
        "code": code,
        "variant": P["kind"],
        "mount": A["mount"],
        "m": P["m"],
        "L_m": round(L, 9),
        "mast_px": A["mast_px"],
        "rake_deg": A["rake_deg"],
        # THE RAMP THAT WAS BUILT, and it is not always the one solve_mast()
        # published.  `solve_mast()` solves the rail's underside as ONE
        # straight line over [claimed_half_m, far end] -- the WHOLE run from
        # the port -- and puts its endpoint heights in `A["rail_ramp"]`.  A
        # module that passes `rail_from=` (a stub, because a continuous rail
        # would cross something: MQB's baked nameplate) re-solves the ramp over
        # the STUB's own span and hands it to `build()` as `ramp=`.  Both were
        # then published, and they disagreed: `parts.service_rail_ramp_m` and
        # `evidence.rail_bbox_px` were right and this top-level key was the
        # whole-run line -- 0.0000 -> 0.0051 m against a built 0.0000 ->
        # 0.0000 on MQB, which is a 5.1 mm lie about where the rail is.  MQB
        # corrected it in its own exporter after `export()` returned; this is
        # the fix in the shared file.  MQB NOTES section 13 item 7.
        "rail_ramp_m": pk.get("service_rail_ramp_m",
                              A.get("rail_ramp") if pk.get("service_rail")
                              else None),
        "lift_m": round(A["lift_m"], 9),
        "start_m": round(A["start_m"], 9),
        "root_scale": 1.0,
        "frame": F.json(),
        "carrier": {"origin": d3(A["carrier"]["origin"]),
                    "u": d3(A["carrier"]["u"]), "v": d3(A["carrier"]["v"]),
                    "n": d3(A["carrier"]["n"])},
        # the three world vectors the frontend actually needs, so it never has
        # to reconstruct a basis from the frame block
        "axis_a": d3(F.u), "axis_b": d3(F.v), "axis_c": d3(F.n),
        "centre": w3((G["bezel_a0"] + G["bezel_a1"]) / 2 * L, 0.0,
                     G["c_bezel"] * L),
        "hotspot": A["hotspot"],
        "parts": pk,
        # the sweep is TRANSLATED along +A by the frontend, off the module's
        # own frame loop.  No timer, so `pose()` has nothing to clear.
        "sweep": {"node": pk.get("sweep"),
                  "travel_m": round(pk.get("sweep_travel_m", 0.0), 9),
                  "ms": 1400},
        # the vane ROTATES ABOUT THE FACE NORMAL, not about the mast axis.
        # About the mast axis a furled vane goes edge-on and disappears; about
        # the face normal it swings from standing out (+B) to lying alongside
        # the head (+A), which is the wide shot's own read.
        "vane": ({"node": pk.get("vane"),
                  "pivot": w3(pk["vane_pivot_ab"][0], pk["vane_pivot_ab"][1],
                              pk["vane_pivot_c"]),
                  "axis": d3(F.n),
                  "flying_deg": 0.0, "half_deg": -45.0, "furled_deg": -90.0}
                 if pk.get("vane") else None),
        "evidence": {
            "tris": P["tris"],
            "bbox_px": [round(t, 3) for t in A["bbox"]],
            "envelope_px": [round(A["bbox"][1] - A["bbox"][0], 2),
                            round(A["bbox"][3] - A["bbox"][2], 2)],
            "rail_bbox_px": rail_bbox,
            "grad_px": round(A["grad_px"], 2),
            "obliq_face_deg": round(A["obliq_face"], 3),
            "obliq_carrier_deg": round(A["obliq_carrier"], 3),
            "px_per_m": [round(A["px_per_m_A"], 1), round(A["px_per_m_B"], 1)],
            "px_per_m_carrier": [round(A["px_per_m_carrier_v"], 1),
                                 round(A["px_per_m_carrier_n"], 1)],
            # THE RATIO IS NOT THE NUMBER -- see refit_port.py's twin.
            "carrier_grad_m_per_px": round(A["margin"]["grad_m_per_px"], 9),
            "lift_margin_px_of_gradient": (
                None if A["margin"]["margin_px"] == float("inf")
                else round(A["margin"]["margin_px"], 3)),
            "carrier_solid_pct": round(A["carrier_solid_pct"], 2),
            "carrier_depth_m": ([round(A["carrier_depth_m"][0], 5),
                                 round(A["carrier_depth_m"][1], 5)]
                                if A["carrier_depth_m"] else None),
            "lift_over_ubias": round(A["lift_over_ubias"], 2),
            "clearances": A["clearances"],
            "rakes": [{"rake_deg": r["rake_deg"],
                       "obliq_deg": round(r["obliq_deg"], 2)}
                      for r in A["rakes"]],
        },
    }
    S["mast"] = block
    with open(os.path.join(dst, "scene.json"), "w") as f:
        json.dump(S, f, indent=1)
    print("  scene.json <- mast block (%d tris, %d parts)"
          % (P["tris"], len(pk)))
    return block


# ===========================================================================
# CLI -- placement, with no Blender in the loop.
#
#     python3 live3d/pipeline/status_mast.py KVS
#     python3 live3d/pipeline/status_mast.py KVS --px 190 --rake 45
#     python3 live3d/pipeline/status_mast.py KVS --rakes
#     python3 live3d/pipeline/status_mast.py KVS --sweep-px 140,240
#
# PASS --window ON EVERY MODULE.  It is not only for anchors near an edge: it
# decides the fitted NORMAL on a frame rail (MTA, 32.56 deg against a correct
# 20.84), the SEAT on a cylinder (OTA), and how far you are extrapolating a
# plane on a carrier that looks flat (FMM: 3e-7 m of residual over 90 px,
# 2.3e-4 m over 220 px, 7 mm over 600).  Without it, OTA's shipped mast cannot
# be expressed here at all -- the default window makes _solve_lift() refuse:
#
#     python3 live3d/pipeline/status_mast.py OTA --at 760,672 \
#             --window 752,962,644,702 --rake 57 --m 8 --px 180
#
# AND --lift-margin WHERE `ubias_m` IS NOT A GAP.  See THE STAND-OFF FLOOR in
# refit_port.py; the solver refuses rather than answering `lift 0.0`:
#
#     python3 live3d/pipeline/status_mast.py FMM --rake 0 --m 8 --px 180 \
#             --window 674,885,648,700 --lift-margin 1200
# ===========================================================================
def _cli(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.split("THREE HALVES")[0])
        print("usage: status_mast.py CODE [--px MAST_PX] [--rake DEG] "
              "[--start-w W] [--m M] [--kind defensive|offensive] "
              "[--numbers] [--window x0,x1,y0,y1] [--lift-margin N] "
              "[--rakes] [--sweep-px lo,hi] [--at PX,PY]")
        return 0
    code = argv[0]
    kw = dict(mast_px=190, rake_deg=None, start_w=None, m=None,
              kind="defensive", numbers=False, carrier_window=None)
    sweep = None
    rakes = False
    i = 1

    def val(k, flag):
        """The argument after `flag`, or a loud failure.

        `status_mast.py MTA --at` used to raise a bare IndexError from inside
        the scan.  A missing value is a typo and the message should say which
        flag lost its number.
        """
        if k + 1 >= len(argv):
            raise SystemExit("status_mast.py: %s needs a value" % flag)
        return argv[k + 1]

    while i < len(argv):
        a = argv[i]
        if a == "--px":
            kw["mast_px"] = int(val(i, a)); i += 1
        elif a == "--rake":
            kw["rake_deg"] = float(val(i, a)); i += 1
        elif a == "--start-w":
            kw["start_w"] = float(val(i, a)); i += 1
        elif a == "--m":
            kw["m"] = int(val(i, a)); i += 1
        elif a == "--kind":
            kw["kind"] = val(i, a); i += 1
        elif a == "--numbers":
            kw["numbers"] = True
        elif a == "--window":
            # `solve_mast()` HAS ALWAYS TAKEN `carrier_window=` AND THE CLI HAD
            # NO FLAG FOR IT.  `refit_port.py` has one; `export_mta.py` and
            # `export_ota.py` both pass the keyword; the task brief and the
            # docs both listed it among this tool's flags.  It was not there,
            # and since an unknown token now raises it was a hard error rather
            # than a silent no-op -- so on OTA, where the DEFAULT window makes
            # `_solve_lift()` refuse, THE DOCUMENTED COMMAND LINE COULD NOT
            # REPRODUCE THE SHIPPED MAST AT ALL and the only route was a
            # `python3 -c` import.  On MTA the default window gave a wrong
            # answer you could still get a number out of (32.56 deg and a
            # 66.9 mm lift against 20.84 and 1.66).  OTA NOTES 13 item 4.
            w = tuple(int(t) for t in val(i, a).split(","))
            if len(w) != 4:
                raise SystemExit("status_mast.py: --window wants x0,x1,y0,y1")
            kw["carrier_window"] = w
            i += 1
        elif a == "--lift-margin":
            # Multiples of `ubias_m`, and the CLI had no flag for this either,
            # so `export_fmm.py`'s shipped `lift_margin=1200` could not be
            # reproduced from the command line.  FMM NOTES 15.
            kw["lift_margin"] = float(val(i, a)); i += 1
        elif a == "--at":
            xy = val(i, a).split(",")
            if len(xy) != 2:
                raise SystemExit("status_mast.py: --at wants PX,PY")
            kw["px"], kw["py"] = int(xy[0]), int(xy[1])
            i += 1
        elif a == "--sweep-px":
            sweep = [int(t) for t in val(i, a).split(",")]
            if len(sweep) != 2:
                raise SystemExit("status_mast.py: --sweep-px wants lo,hi")
            i += 1
        elif a == "--rakes":
            # A FLAG, NOT AN ACTION.  It used to SOLVE AND RETURN from inside
            # this scan, at its own position, so every argument after it was
            # never parsed at all: `status_mast.py MTA --rakes --at 123,584`
            # raised "MTA has no refit.service_rail" while
            # `--at 123,584 --rakes` worked, and nothing said why.  Order
            # independence is the fix; MTA NOTES section 10 item 6.
            rakes = True
        else:
            # LOUD, NOT IGNORED.  An unrecognised token used to fall through
            # this scan silently -- `--start_w 12.2` (underscore) discarded
            # both the flag and the number and the tool printed a confident
            # table for the DEFAULT start.  There is no positional argument
            # after CODE, so anything unmatched here is a mistake.
            raise SystemExit(
                "status_mast.py: unknown argument %r\n"
                "usage: status_mast.py CODE [--px MAST_PX] [--rake DEG] "
                "[--start-w W] [--m M] [--kind defensive|offensive] "
                "[--numbers] [--window x0,x1,y0,y1] [--lift-margin N] "
                "[--rakes] [--sweep-px lo,hi] [--at PX,PY]" % a)
        i += 1

    # --rakes and --sweep-px are REPORTS: they run after the whole command line
    # has been read, so they see every other flag whatever the order.
    def report_solve(**over):
        """Solve for a REPORT -- a rake table, a size sweep.

        A report is not a build, and the stand-off floor depends on the module
        and the window rather than on the row: refusing would delete the table
        the flag exists to print.  So the row is printed and FLAGGED, exactly
        as `refit_port.py --sweep-y` does it."""
        kw2 = dict(kw); kw2.update(over)
        try:
            return solve_mast(code, verbose=False, **kw2), ""
        except ThinMargin as e:
            M = e.mast["margin"]
            return e.mast, ("   !! MARGIN %.2f px < %.2f -- see --lift-margin"
                            % (M["margin_px"], M["floor_px"]))
        except Cantilever as e:
            C = e.mast["cantilever"]
            return e.mast, ("   !! CANTILEVER closest point %.2f L > %.2f -- "
                            "nothing is behind it"
                            % (C["stand_off_over_L"], C["floor_L"]))

    if rakes:
        A, flag = report_solve()
        print("%s rake table -- obliquity of the mast FACE to the close "
              "camera%s" % (code, flag))
        print("  the carrier itself is at %.2f deg" % A["obliq_carrier"])
        for r in A["rakes"]:
            print("    rake %5.1f deg -> face obliquity %6.2f deg"
                  % (r["rake_deg"], r["obliq_deg"]))
        if sweep:
            print("")
    if sweep:
        print("%-8s %-9s %-22s %-9s %s"
              % ("mast_px", "L (mm)", "envelope px", "grad px", "worst gap px"))
        for p in range(sweep[0], sweep[1] + 1, 10):
            try:
                A, flag = report_solve(mast_px=p)
            except ValueError as e:
                print("%-8d  -- %s" % (p, str(e).split("\n")[0]))
                continue
            worst = min([c["gap_px"] for c in A["clearances"]] or [0])
            print("%-8d %-9.2f %6.1f..%6.1f %5.1f..%5.1f %-9.1f %.1f%s%s"
                  % (p, A["L_m"] * 1000, A["bbox"][0], A["bbox"][1],
                     A["bbox"][2], A["bbox"][3], A["grad_px"], worst,
                     "   OFF FRAME" if A["off_frame"] else "", flag))
        return 0
    if rakes:
        return 0
    solve_mast(code, **kw)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_cli(sys.argv[1:]))
    except ThinMargin as _e:
        # A REFUSAL, NOT A CRASH, and never rc=0.  See refit_port.py's twin.
        sys.stderr.write("status_mast.py REFUSES this stand-off:\n%s\n" % _e)
        raise SystemExit(2)
    except Cantilever as _e:
        sys.stderr.write("status_mast.py REFUSES this mounting:\n%s\n" % _e)
        raise SystemExit(2)
    except ValueError as _e:
        sys.stderr.write("status_mast.py: %s\n" % _e)
        raise SystemExit(2)
