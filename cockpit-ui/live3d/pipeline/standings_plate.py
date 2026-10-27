"""
THE STANDINGS PLATE -- the player-facing way into the muster board.

`live3d/design/STANDINGS.md` is the design.  This file is the half of it that
is measured rather than drawn: it turns a target pixel on the WIDE SHOT into a
world frame on a measured carrier, sizes a brass nameplate to a screen
rectangle, stands it off the baked geometry, proves it crosses nothing, and
renders the two sprites the cockpit composites.

    python3 live3d/pipeline/standings_plate.py                 # solve + evidence
    python3 live3d/pipeline/standings_plate.py --json OUT.json

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/standings_plate.py -- depth
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/standings_plate.py -- render

THREE HALVES, AND ONLY TWO OF THEM NEED BLENDER
-----------------------------------------------
Deliberately the same shape as `pipeline/refit_port.py` and
`pipeline/status_mast.py`, because anyone reading this will be reading those:

* `solve_plate()` and everything above it is **pure stdlib**.  It imports
  `refit_port`'s `Camera`, `PortFrame`, `fit_carrier_plane`, `read_depth`,
  `margin_report`, and `status_mast`'s `axis_px_per_m`,
  `mast_frame` and `rake_table`.  IT DOES NOT WRITE A SECOND SOLVER.  What is
  new here is only what a rectangular nameplate needs and a hexagonal port did
  not: a rectangle's hull, a size solved to TWO screen dimensions rather than
  one envelope, and a keep-out list that is the WIDE shot's nine hotspots and
  nine telltale envelopes rather than one module's controls.
* `depth` needs `bpy`.  It rebuilds the shipped cockpit scene -- `shell.build`,
  the nine `cockpit/modules/<CODE>/build.py`, the four `cockpit/dressing/tier*`
  -- exactly as `cockpit/combine.py` does, renders the Z pass, and writes
  `live3d/assets/_STANDINGS/{depth.bin,scene.json}`.  It also renders a COLOUR
  CONTROL and scores it against the shipped `cockpit/combined/main_plate.png`,
  because a depth map that does not belong to those pixels is worse than no
  depth map at all.
* `render` needs `bpy`.  It builds the nameplate at the solved frame in the
  same scene and writes `prop.png` and `glow.png` -- the same two sprites, made
  the same way, that every one of the nine modules already contributes to the
  wide shot (`cockpit/modules/<CODE>/build.py: render_to()` / `glow_render()`).

**NOTHING HERE WRITES TO `cockpit/`.**  It is read-only, it is imported, and
the shipped plate is never re-rendered: the control render goes to a scratch
path and is compared, not kept.  `transition.json`'s nine `M` values and dive
centres are normalised-cross-correlation results against exactly those pixels
and a re-bake would void all nine.

WHY A RENDERED SPRITE AND NOT A CSS3D PLANE
-------------------------------------------
The brief for this component asked for a CSS3D plane, on the reasoning that a
screen-space DOM box over a raked face reads as a sticker (`css3d.js:9-15`).
Two measurements moved that:

1. **The carrier is not raked.**  The C3 / `oh_2` console's front face is a
   VERTICAL box face at -7 deg of azimuth, seen by a camera that looks down
   3.2 deg.  Fitted through `carrier_window` on this file's own depth pass it
   is at **7.69 deg obliquity** to the wide camera.  Its two in-plane axes
   project at 249.5 and 250.5 px/m -- a ratio of 1.004, i.e. not foreshortened
   in either direction -- and the carrier normal projects at 44.5 px/m, a
   **v:n separation of 5.62**.

   THAT RATIO IS THE CRITERION, AND IT IS NOT THE TABLE MINIMUM.  `rake_table`
   below prints obliquity per candidate rake, and picking the row with the
   smallest obliquity gets the WRONG answer on three of the seven shipped
   masts: KVS ships 45 where the table minimum is 57, IPM ships 54 where it is
   60, and FMM ships 0 where it is 15.  What actually separates the fleet is
   v:n, measured on each mast's own carrier:

       raked    IPM 0.73   KVS 0.93   OTA 0.93   PKT 1.56
       flat     MTA 2.05   MQB 4.59   FMM 33.93

   The two clusters do not touch -- the gap is 1.56 to 2.05 -- and a rake is
   what you reach for when v and n project to nearly the same screen direction,
   which is what a LOW ratio means.  FMM is the case that proves the table
   wrong: the most extreme flat carrier in the fleet at 33.93, and the
   obliquity table still recommends tilting it.

   **This carrier's 5.62 lands in the flat cluster**, between MQB and FMM and
   3.6x clear of the boundary.  So: **rake 0**.  A fitting lying flat here has
   two readable axes and needs no bracket, and there is no rake for a DOM box
   to fight.  (The per-mast numbers are close-up cameras and this one is the
   wide camera, so the ratio is compared and the obliquities are not -- v:n is
   a shape of the carrier under its own camera, which is why it travels and a
   degree count does not.)
2. **There is nothing on this fitting for the DOM to carry.**  `STANDINGS` is
   a permanent label stamped on the ship, and the fleet's rule
   (`CONVERSION_BRIEF.md:1786-1789`, restated in `LEADERBOARD.md` section 3)
   is that permanent labels are GEOMETRY and only values are DOM.  The wide
   shot has no live renderer at all, so geometry there means a sprite -- and a
   sprite rendered in this scene is lit by the same seven lights, at the same
   camera, in the same view transform, as the plate it sits on.  A CSS3D plane
   would have had to SIMULATE brass under a raking key light in CSS, which is
   the sticker failure mode wearing the other hat.

The anchor solve is held to the fourteen shipped fittings' acceptance numbers
anyway, and for a real reason: the nameplate has to stand clear of the C3
dressing kit it covers, and "clear" is a measurement.

WHAT THE ubias_m COLUMN MEANS HERE, AND WHAT IT DOES NOT
--------------------------------------------------------
On the nine close-ups a fitting that stands less proud than the module's
`ubias_m` is DELETED silently by the depth composite (trap 24).  **The wide
shot has no depth composite and no split pass**, so nothing here is deleted:
Blender's own z-buffer resolves the sprite against the scene and `render_to`'s
holdout punches the alpha.  The stand-off still has to be solved, because a
plate that intersects the console it is bolted to looks like it, and because
`margin_report()`'s floor -- the margin must be worth at least half a pixel of
the carrier's own depth gradient -- is a statement about the RASTERISER and is
true whoever is compositing.  `ubias_m` is carried at the fleet's shared
default of 5e-4 m as the UNIT that floor is expressed in, and it is not a
measured bias of anything on this surface.  Said out loud because the number
looks like the seven modules' and is not the same kind of number.

CONVENTIONS (they are `refit_port.py`'s)
----------------------------------------
* The plate is authored in its own frame: local +X = `u` (across the plate,
  screen-rightish), +Y = `v` (up the carrier), +Z = `n` (out of it, toward the
  camera).  `PortFrame.to_world()` is the only place that mapping lives.
* Every object and material is prefixed `sb_`.
* NEVER a float in an object name -- Blender parses `.NNN` as a duplicate
  suffix.  Indices only.
* Fractions of the plate's own size are module-level constants in `GEO`.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)
ROOT = os.path.dirname(LIVE3D)
CK = os.path.join(ROOT, "cockpit")
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import refit_port as RP                                          # noqa: E402
from refit_port import (Camera, PortFrame, read_depth,           # noqa: E402
                        fit_carrier_plane, _add, _cross, _dot, _mul,
                        _norm, _sub, to_blender,
                        margin_report)
import status_mast as SMT                                        # noqa: E402

CODE = "_STANDINGS"
ASSET = os.path.join(LIVE3D, "assets", CODE)
PLATE_PNG = os.path.join(CK, "combined", "main_plate.png")

# ===========================================================================
# THE ANCHOR.  Copied into `check/regress_standings.py` verbatim; if it changes
# here it must change there, and a mismatch shows up as a diff, which is the
# intended failure.
# ===========================================================================
STANDINGS = dict(
    # Target centre and target SCREEN SIZE OF THE WHOLE ENVELOPE, in the wide
    # shot's canonical 1280x720 px -- the envelope and not the ground plate,
    # for the reason FIX_UPLOAD 12.4 records: a fitting's drawn silhouette is
    # not its base rectangle, and a hotspot or a keep-out built from the base
    # rectangle measures the wrong thing.
    #
    # THE DESIGN RECORD'S RECTANGLE IS (464,194)-(663,234) AND IT IS 8 px LOW.
    # Projected analytically and confirmed against this file's own depth pass,
    # the oh_2 box's FRONT FACE spans 453.7..668.7 x 182.2..229.6 -- so rows
    # 230..238 of that rectangle are the console's UNDERSIDE, a different
    # surface at a grazing angle, and a plate sized to it would have run over
    # the edge.  Inside the box's own 0.014 m bevel the clean face is about
    # 457..665 x 186..226, and this envelope is that, centred.
    px=563.3, py=208.2,
    # The GROUND PLATE's own size on screen, measured along its own two axes
    # through its centre (`_plate_chords`), not the bounding box of the
    # assembly.  The envelope that comes out of it is reported and checked
    # against the face; it is about 204 x 40 px.
    plate_px=192.0,
    plate_py=33.0,
    # The clean console face, inside the box's own 0.014 m bevel, in canonical
    # px.  The solve REFUSES if the envelope leaves it -- a nameplate whose
    # corner hangs over the edge of the thing it is bolted to is not a
    # nameplate, and a bbox that merely "looks about right" is how that ships.
    face_px=(457.0, 665.0, 186.0, 226.0),
    # The window the carrier plane is fitted through.  Well inside the box
    # face's own bevel and well above its underside, both of which are
    # different surfaces and would tilt the fit.
    carrier_window=(474, 653, 194, 222),
    label="STANDINGS",
    # Stand-off margin, in multiples of `ubias_m`.  The C3 dressing kit under
    # this plate reaches 0.0295 m proud of the box face (the padlock loop on
    # the access door), so the stand-off is dominated by THAT and not by the
    # margin; the margin is what `margin_report()` scores against the carrier's
    # own depth gradient.
    stand_margin=2.5,
)

# ===========================================================================
# GEOMETRY TABLE -- every dimension a fraction of H (the plate's height) or,
# where marked, of W (its width).  Anything you would otherwise type as a
# number in build() belongs here.
#
# THE ONE THING TO UNDERSTAND ABOUT THIS FITTING'S PROPORTIONS.  The carrier
# normal projects at 44.5 px/m.  A 10 mm step out of the face is 0.45 screen
# px, so NO RELIEF ON THIS PLATE IS VISIBLE AS PARALLAX -- the fitting is read
# entirely by how its facets take the shell's raking key light.  That is why
# the bezel is a chamfered bar rather than a thin lip, why the field is
# recessed enough to sit in its own shadow, and why the fixings are domed.
# ===========================================================================
GEO = {
    # --- the brass ground plate
    "t_plate":       0.090,   # thickness, fraction of H
    "bevel_plate":   0.022,
    # --- the recessed dark field the type is written on.  Its height is the
    # TYPE's budget: the ground plate measures 33.0 px on screen and 0.700 of
    # it is a 23.1 px field, which is a 17.0 px cap with 3 px of air above and
    # below it.  (23.0 and 17.0 are MEASURED off the field's own projection by
    # `solve_plate`, not read off this table -- see the type block there.)
    # Everything else on this
    # plate is what is left over, which is the right way round -- the word is
    # the affordance and the brass is its mounting.
    "field_h":       0.700,   # field height, fraction of H
    "field_inset_w": 0.0360,  # inset from each end, fraction of W
    "field_drop":    0.045,   # how far the field face sits below the BEZEL
                              # FACE -- not below the plate face.  See
                              # `field_face_z()`: there is no boolean in
                              # `kit.py`, so a face "recessed into" the ground
                              # plate is a solid buried inside another solid,
                              # and the only recess that can actually be built
                              # is one the BEZEL makes by standing proud.
    "t_field":       0.050,
    # --- the brass bezel around the field
    "bez_bar":       0.0714,  # bar width, fraction of H
    "bez_proud":     0.055,   # bezel face above the plate face.  This is the
                              # highest surface on the fitting and the datum
                              # `field_drop` is measured down from.
    # --- the type
    # --- THE TWO FONT RATIOS, AND THEY ARE NOT PER-EM.
    # `kit.text()` passes its `size` straight to Blender's `FONT.size`, and
    # BLENDER'S FONT.size IS NOT AN EM.  For Courier New Bold via
    # `kit.mono_font()`, one size unit is 0.51769 em -- so the face's true
    # per-em numbers (advance 1229/2048 = 0.600098 em, cap 1213/2048 =
    # 0.592285 em) are the WRONG SCALE to solve a FONT.size with.
    #
    # This table used to carry 0.5714 and 0.6000, which are per-EM numbers, and
    # the solver used them as if they were per-size.  The consequence was not a
    # refusal -- every guard passed, because the guards were checking the
    # solver's own arithmetic against itself -- it was a SILENTLY SMALL LABEL:
    # STANDINGS shipped at 0.506 of its solved width and a 9.1 px cap against a
    # 16 px legibility floor.  That is precisely the failure the `txt_min_slack`
    # message below promises will never happen quietly.
    #
    # These two are MEASURED, by `pipeline/typemetrics.py`'s stated method --
    # bbox("MM") - bbox("M") is one advance, off `to_mesh()` and not off pixels
    # -- and they reproduce that file's published constants to six places:
    #
    #     FONT.size 0.116759055 m  ->  advance 0.036273224 m,  cap 0.035800995 m
    #
    # They are a property of the FACE, not of this fitting. A build that
    # resolves a different font through `mono_font()` must re-measure.
    "cap_over_size": 0.306623,  # Courier New Bold cap height / FONT.size
    "adv_over_size": 0.310667,  # Courier New Bold advance    / FONT.size
    "txt_proud":     0.030,   # letter face above the field face
    "cap_px":        17.0,    # THE TYPE IS SOLVED TO THIS, not to the plate.
                              # 16 canonical px is the fleet's legibility floor
                              # (LEADERBOARD 6.1/9); 17 is where the muster
                              # board's own 28 px row lands, and this label is
                              # read at the same distance from the same chair.
    "txt_min_slack": 0.025,   # clear space each end of the word, as a fraction
                              # of the FIELD width.  If the solved type will
                              # not fit inside that, the solve REFUSES rather
                              # than shrinking the word below the floor.
    # --- fixings: four domed slot-head screws, in the brass at the plate's ends
    "screw_r":       0.0714,
    "screw_in_w":    0.0180,  # inset from each end, fraction of W
    "screw_in_v":    0.500,   # centred vertically -- the ends are the only
                              # brass wide enough to take a fixing
    # --- the four stand-offs the plate is bolted out on.  ENTIRELY HIDDEN BY
    # THE PLATE at this obliquity (the carrier normal projects at 44.5 px/m, so
    # the solved 30.8 mm stand-off is 1.4 screen px) and built anyway, because a
    # plate
    # bolted to nothing is not a fitting and the geometry is what the render is
    # made of.  Excluded from the stand-off scan by construction: they are
    # MEANT to touch the carrier, and a hull sample that touches by design
    # would make the scan never terminate.
    "spacer_r":      0.100,
    "spacer_in_w":   0.0400,
    "spacer_in_v":   0.300,
    # --- end lugs: the plate is let into the console's own end ribs
    "lug_w":         0.022,   # fraction of W
    "lug_h":         1.000,   # fraction of H.  FLUSH with the plate, not
                              # proud of it: the console face is 40 canonical
                              # px tall and 17 of them are spoken for by the
                              # cap height, so a lug standing 4 % above and
                              # below the plate costs 8 % of the whole vertical
                              # budget to say something the end grain already
                              # says.  It was 1.14 and the envelope check
                              # refused it.
    "t_lug":         0.055,
}


# ===========================================================================
# PURE STDLIB -- the carrier, the size, the stand-off, the clearances.
# No bpy below this line until the BLENDER section.
# ===========================================================================
def load_wide():
    """The wide shot's own scene + depth, written by the `depth` step."""
    S = json.load(open(os.path.join(ASSET, "scene.json")))
    return ASSET, S


def base_plane(cam, dep, W, H, window, tol=0.0015, passes=4, keep_q=0.15):
    """The carrier's BASE plane, measured through a DRESSED surface.

    `refit_port.fit_carrier_plane()` is a plain least-squares fit and it is the
    right tool on a module deck, which is bare.  This carrier is not bare: it
    is the C3 console face WITH the set-dressing kit that this plate covers,
    and that kit stands 2 to 29.5 mm proud of it over 62 % of the window.  A
    straight fit therefore fits the RELIEF -- measured, it lands 3.1 to 7.7 deg
    off the face depending on where the window is drawn, with a p50 residual of
    3.8 mm, and the tilt is not noise but the door and the lens cells pulling
    one half of the window forward.  A nameplate bolted to a face wants the
    FACE.

    So the fit is run repeatedly with the relief MASKED OUT, and the masking is
    by depth, not by hand: everything standing more than `tol` proud of the
    current base level is set to the depth map's own background value, which is
    the one thing `fit_carrier_plane()` already ignores.  The plane solve stays
    the fleet's, unmodified, and the only thing new here is which pixels it is
    shown.

    Measured on the shipped depth: the base level is a genuine plane, not an
    average -- 1,987 of the window's 5,220 samples sit at residual 0.0000 m
    against the console's analytic face, and the rest are the kit standing in
    front of it in discrete steps at 4, 8, 12, 14 and 16 mm.

    Returns (centroid, normal, |residuals| of the KEPT set, kept, total).
    """
    far = 1e9
    c, n, res = fit_carrier_plane(cam, dep, W, H, *window)
    x0, x1, y0, y1 = window
    idx = [yy * W + xx
           for yy in range(max(0, y0), min(H, y1 + 1))
           for xx in range(max(0, x0), min(W, x1 + 1))]
    kept = total = len(idx)
    for _ in range(passes):
        rs = []
        for i in idx:
            d = dep[i]
            if d >= far:
                continue
            P = cam.unproject((i % W) + 0.5, (i // W) + 0.5, d)
            rs.append((_dot(_sub(P, c), n), i))
        if not rs:
            break
        rs.sort()
        base = rs[int(keep_q * len(rs))][0]
        drop = set(i for r, i in rs if r > base + tol)
        if not drop:
            break
        masked = list(dep)
        for i in drop:
            masked[i] = 1e10
        c, n, res = fit_carrier_plane(cam, masked, W, H, *window)
        kept, total = len(rs) - len(drop), len(rs)
    return c, n, res, kept, total


def field_face_z(G=None):
    """The z of THE FIELD'S OWN FACE, in units of H, from the plate's BACK face.

    ONE PLACE, BECAUSE IT WAS THREE AND THEY DISAGREED.  `build()`,
    `hull_samples()` and `solve_plate()`'s type block each computed this
    independently as `t_plate - field_drop`, and that number is INSIDE THE
    GROUND PLATE: the plate spans 0..t_plate, so a field face at
    t_plate - field_drop is a solid buried in another solid.  `kit.py` has no
    boolean, so nothing cuts it out.  The render came back as a FLAT BRASS
    RECTANGLE -- no field, no lettering, no relief -- because flat brass is
    exactly what was in front.

    The recess a `bez_frame` makes is OPTICAL and it is measured DOWN FROM THE
    BEZEL, which is what `kit.bez_frame`'s own docstring means by "four bars
    forming a picture frame, so the face inside can be RECESSED".  So:

        plate face      t_plate                      0.090
        field face      t_plate + bez_proud
                                  - field_drop       0.100   <- proud of the plate
        type face       + txt_proud                  0.130
        bezel face      t_plate + bez_proud          0.145   <- the highest surface

    The field face stands 0.010 H proud of the brass and sits 0.045 H below the
    bezel; the type stands 0.030 H proud of the field and still clears under the
    bezel. That is a nameplate. The buried version was a blank.
    """
    G = G or GEO
    return G["t_plate"] + G["bez_proud"] - G["field_drop"]


def type_face_z(G=None):
    """The z of the LETTER FACES, in units of H.  `kit.text` extrudes a curve
    SYMMETRICALLY about its own plane, so a text object placed at the field
    face with `extrude = txt_proud` spans field +/- txt_proud and its face is
    `txt_proud` proud of the field.  The plane it is placed on is therefore the
    field face itself, not the field face plus anything."""
    G = G or GEO
    return field_face_z(G) + G["txt_proud"]


def hull_samples(G=None, spacers=True, hw=1.0):
    """(x, y, z) corners of everything the plate actually PAINTS, in units of
    (W, H, H) in the plate's own frame, origin at the plate centre, z = 0 at
    the plate's BACK face.

    NOT a bounding box, and not the ground plate either.  `refit_port` records
    (FIX_UPLOAD 12.4) that a hotspot or a keep-out built from a fitting's base
    rectangle measures the wrong rectangle, because the drawn silhouette is the
    whole assembly: here the end lugs stand above and below the plate and the
    bezel and the stand-offs stand in front of it.
    """
    G = G or GEO
    pts = []

    def box(x0, x1, y0, y1, z0, z1):
        for x in (x0, x1):
            for y in (y0, y1):
                for z in (z0, z1):
                    pts.append((x, y, z))

    tp = G["t_plate"]
    # the ground plate
    box(-0.5, 0.5, -0.5, 0.5, 0.0, tp)
    # the bezel, standing proud of it
    fh = G["field_h"] / 2.0
    fw = 0.5 - G["field_inset_w"]
    box(-fw - G["bez_bar"], fw + G["bez_bar"], -fh - G["bez_bar"],
        fh + G["bez_bar"], tp, tp + G["bez_proud"])
    # the type, on the recessed field.  Symmetric extrude about the field
    # face, so it reaches BACK as far as it stands proud (`type_face_z`).
    # It never governs the hull -- the bezel is higher and wider -- but a hull
    # sample that disagrees with the geometry is how the three copies of this
    # z drifted apart in the first place.
    fzf = field_face_z(G)
    box(-fw, fw, -fh, fh, fzf - G["txt_proud"], fzf + G["txt_proud"])
    # the fixings.  `hw` is H_m / W_m: every radius in GEO is a fraction of H
    # (the fitting is read vertically), and x here is in units of W, so a
    # radius crossing into x must be converted.  It was not, and the four screw
    # heads made the projected envelope 14 px wider than the plate -- a hotspot
    # and a keep-out built from that rectangle would both have been measuring
    # brass that is not there.
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx = sx * (0.5 - G["screw_in_w"])
            cy = sy * (0.5 - G["screw_in_v"])
            r = G["screw_r"]
            box(cx - r * hw, cx + r * hw, cy - r, cy + r, tp, tp + r)
    # the end lugs, which reach above and below the plate
    lh = G["lug_h"] / 2.0
    for sx in (-1, 1):
        cx = sx * 0.5
        box(cx - G["lug_w"], cx + G["lug_w"], -lh, lh, 0.0, G["t_lug"])
    # the stand-offs, BEHIND the plate.  `spacers=False` drops them, and every
    # clearance question asks with them dropped: they reach from the plate's
    # back face to the carrier BY CONSTRUCTION, so a scan that included them
    # would measure zero clearance at every stand-off and never terminate.
    if spacers:
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx = sx * (0.5 - G["spacer_in_w"])
                cy = sy * (0.5 - G["spacer_in_v"])
                r = G["spacer_r"]
                box(cx - r * hw, cx + r * hw, cy - r, cy + r,
                    -1.0, 0.0)                                  # z scaled below
    return pts


def _world(frame, W_m, H_m, stand, pt, back_depth):
    """One hull sample -> world.  `pt` is in (W, H, H) units with z = 0 at the
    plate's back face; a NEGATIVE z is a stand-off sample and is scaled by the
    stand-off itself rather than by H, so the spacers reach exactly from the
    carrier to the plate and no further."""
    x, y, z = pt
    zz = (z * H_m) if z >= 0 else (z * back_depth)
    return frame.to_world(x * W_m, y * H_m, stand + zz)


def rect_px(cam, frame, W_m, H_m, stand, a0, a1, b0, b1, z, n=9):
    """The projected bbox of one rectangle of the fitting, sampled on a grid
    rather than at its corners.

    Sampled because this is a WIDE-ANGLE frame -- 90 deg across, an 18 mm lens
    -- and the plate spans 0.71 m of it, 154 px above the principal point.
    Neither the scale nor the straightness of an edge is constant over that,
    which is exactly why the numbers below are measured off this projection and
    never computed as `metres x px_per_m`: the two disagree by 18 % on this
    fitting's own height, and taking the second was how the first draft of the
    type came out 175 px wide inside a 171 px field.
    """
    xs, ys = [], []
    for i in range(n):
        for j in range(n):
            a = a0 + (a1 - a0) * i / (n - 1.0)
            b = b0 + (b1 - b0) * j / (n - 1.0)
            px, py, _ = cam.project(frame.to_world(a * W_m, b * H_m,
                                                   stand + z * H_m))
            xs.append(px)
            ys.append(py)
    return min(xs), max(xs), min(ys), max(ys)


def envelope_px(cam, frame, W_m, H_m, stand, G=None):
    """Screen bbox of the WHOLE assembly."""
    xs, ys = [], []
    for p in hull_samples(G, hw=H_m / W_m):
        px, py, _ = cam.project(_world(frame, W_m, H_m, stand, p, stand))
        xs.append(px)
        ys.append(py)
    return min(xs), max(xs), min(ys), max(ys)


def _clearance(cam, frame, W_m, H_m, stand, dep, W, H, G=None):
    """The closest the seated plate comes to the baked geometry, in metres,
    over EVERY PIXEL IT COVERS.  Positive is in front of it.

    NOT a sample of the hull, and the difference is the whole test.  A corner
    or coarse-grid scan of this fitting clears the C3 kit's rivet rows, reports
    a healthy stand-off, and leaves the ACCESS DOOR'S PADLOCK LOOP -- 29.5 mm
    proud, 2.4 screen px across, a third of the way along the face and nowhere
    near a corner -- pushed straight through the plate.  A 6 px grid steps over
    it.  So the scan is per-pixel, which is cheap here (the footprint is about
    8,000 px) and exact.  It is the lesson `refit_port.verify_seat()` records
    for PKT's brass lip, applied before the fact instead of after it.

    Only the assembly's BACK PLANE is tested, and that is a proof rather than a
    shortcut: every other surface of this fitting -- bezel, type, screw heads,
    lug faces -- lies at z >= 0 in the plate's own frame, i.e. strictly further
    along `n` toward the camera, so its view depth is strictly smaller and its
    clearance strictly larger.  The back plane is the binding surface at every
    stand-off.  The stand-offs themselves are excluded: they reach from that
    plane to the carrier by construction (GEO).
    """
    G = G or GEO
    O = frame.to_world(0.0, 0.0, stand)
    n = frame.n
    lw, lh = G["lug_w"], G["lug_h"] / 2.0
    bx0, bx1, by0, by1 = envelope_px(cam, frame, W_m, H_m, stand, G)
    worst, where = 1e9, None
    for yy in range(max(0, int(bx0) * 0 + int(by0)), min(H, int(by1) + 2)):
        row = yy * W
        for xx in range(max(0, int(bx0)), min(W, int(bx1) + 2)):
            P = cam.hit_plane(xx + 0.5, yy + 0.5, O, n)
            d = _sub(P, O)
            a = _dot(d, frame.u) / W_m
            b = _dot(d, frame.v) / H_m
            on = (abs(a) <= 0.5 and abs(b) <= 0.5) or (
                abs(b) <= lh and (abs(a - 0.5) <= lw or abs(a + 0.5) <= lw))
            if not on:
                continue
            baked = dep[row + xx]
            if baked >= 1e9:
                continue
            D = cam.project(P)[2]
            if baked - D < worst:
                worst, where = baked - D, (xx + 0.5, yy + 0.5,
                                           round(a, 3), round(b, 3))
    if where is None:
        return None, None
    return worst, where


def solve_stand(cam, frame, W_m, H_m, dep, W, H, ub, margin, G=None):
    """The SMALLEST stand-off at which no part of the plate is behind the baked
    geometry by more than the margin allows.

    A SCAN, not a Newton step, and for the reason `status_mast._solve_lift()`
    records: every sample's pixel MOVES up-screen as the assembly rises, onto
    baked depth that may be nothing like the depth under the foot, so an
    iterated first-order step converges to the wrong answer and says nothing
    about it.  Scan, and take the first stand-off that clears and STAYS clear.
    """
    target = margin * ub
    step = max(ub * 0.5, 1e-5)
    stand = 0.0
    for _ in range(20000):
        c, _w = _clearance(cam, frame, W_m, H_m, stand, dep, W, H, G)
        if c is not None and c >= target:
            if all((_clearance(cam, frame, W_m, H_m, stand + step * k,
                               dep, W, H, G)[0] or -1) >= target
                   for k in (1, 2, 3)):
                return stand
        stand += step
        if stand > 0.5 * H_m:
            raise ValueError(
                "no stand-off under %.4f m clears the baked geometry at this "
                "anchor; the carrier here is not a plate to bolt to." % stand)
    raise ValueError("stand-off scan did not terminate")


def _plate_chords(cam, frame, W_m, H_m, stand, G=None):
    """The ground plate's own two dimensions ON SCREEN, measured along its own
    axes through its centre.  See `rect_px()` for why this is not its bbox."""
    G = G or GEO
    z = stand + G["t_plate"] * H_m

    def ch(a0, b0, a1, b1):
        p0 = cam.project(frame.to_world(a0 * W_m, b0 * H_m, z))
        p1 = cam.project(frame.to_world(a1 * W_m, b1 * H_m, z))
        return math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    return ch(-0.5, 0.0, 0.5, 0.0), ch(0.0, -0.5, 0.0, 0.5)


def _size_for(cam, frame, target_w_px, target_h_px, stand_guess, G=None):
    """Hold the SCREEN size, derive the physical one.

    Projection is not linear in size, so this iterates exactly as
    `refit_port.solve_anchor()` does.  Both dimensions are held, not one: a
    nameplate is read as a rectangle of a particular aspect and the fleet's
    one-envelope solve (which scales until the DOMINANT axis touches) would
    give away the other one.
    """
    W_m, H_m = target_w_px / 1500.0, target_h_px / 1500.0
    for _ in range(40):
        w, h = _plate_chords(cam, frame, W_m, H_m, stand_guess, G)
        kw, kh = target_w_px / w, target_h_px / h
        W_m *= kw
        H_m *= kh
        if abs(kw - 1.0) < 1e-11 and abs(kh - 1.0) < 1e-11:
            break
    return W_m, H_m


def keepouts(S):
    """Every rectangle on the wide shot this fitting must not touch: the nine
    modules' far hotspots and the nine telltale masts' envelopes, both read out
    of `scene.json` where the `depth` step published them from the SHIPPED
    `cockpit/combined/manifest.json` and `live3d/status.js`.

    Not a copy of either file.  A copy would be a fifteenth place for the
    fleet's placement numbers to live and drift.
    """
    out = []
    for k, p in sorted((S.get("props") or {}).items()):
        r = p["hotspot"]
        out.append((k, [r["x"], r["x"] + r["w"], r["y"], r["y"] + r["h"]]))
    return out


def clearance_report(S, cam, frame, W_m, H_m, stand, dep, W, H, G=None):
    """0 px^2 overlap with any module hotspot, 0 px^2 with any telltale
    envelope, 100 % solid carrier -- proved for THIS anchor rather than
    inherited from a table."""
    bx0, bx1, by0, by1 = envelope_px(cam, frame, W_m, H_m, stand, G)
    hot = [bx0 - 4, bx1 + 4, by0 - 4, by1 + 4]

    def ov(a, b):
        return (max(0.0, min(a[1], b[1]) - max(a[0], b[0])) *
                max(0.0, min(a[3], b[3]) - max(a[2], b[2])))

    def gap(a, b):
        # Chebyshev separation, which is what a rect-vs-rect keep-out is; the
        # design record's "44 px from PKT's mast" is the EUCLIDEAN corner
        # distance of the same pair and both are quoted below.
        return max(0.0, max(b[0] - a[1], a[0] - b[1], b[2] - a[3], a[2] - b[3]))

    def euclid(a, b):
        dx = max(0.0, b[0] - a[1], a[0] - b[1])
        dy = max(0.0, b[2] - a[3], a[2] - b[3])
        return math.hypot(dx, dy)

    clear = [{"what": nm, "overlap_px2": ov(hot, r), "gap_px": gap(hot, r),
              "gap_euclid_px": euclid(hot, r)}
             for nm, r in keepouts(S)]

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
    return {"bbox": [bx0, bx1, by0, by1],
            "hotspot": {"x": round(max(0.0, hot[0]), 2),
                        "y": round(max(0.0, hot[2]), 2),
                        "w": round(min(cam.W, hot[1]) - max(0.0, hot[0]), 2),
                        "h": round(min(cam.H, hot[3]) - max(0.0, hot[2]), 2)},
            "clearances": clear,
            "carrier_solid_pct": 100.0 * solid / max(1, tot),
            "carrier_depth_m": [min(depths), max(depths)] if depths else None,
            "off_frame": not (0 <= bx0 and bx1 < W and 0 <= by0 and by1 < H)}


def solve_plate(px=None, py=None, plate_px=None, plate_py=None,
                carrier_window=None, label=None, stand_margin=None,
                normal="carrier", verbose=True):
    """Turn a target pixel on the WIDE SHOT into everything `build()` needs.

    Returns a dict; `frame` is in three.js world, `frame_blender` is the same
    frame mapped for authoring.  Prints its own evidence when `verbose`.
    """
    K = dict(STANDINGS)
    for k, val in (("px", px), ("py", py), ("plate_px", plate_px),
                   ("plate_py", plate_py), ("carrier_window", carrier_window),
                   ("label", label), ("stand_margin", stand_margin)):
        if val is not None:
            K[k] = val

    A, S = load_wide()
    cam = Camera(S)
    dep, W, H = read_depth(A, S)
    ub = float(S.get("ubias_m") or 0.0005)

    x0, x1, y0, y1 = K["carrier_window"]
    c_ls, n_ls, res_ls = fit_carrier_plane(cam, dep, W, H, x0, x1, y0, y1)
    c, n_carrier, res, kept, total = base_plane(cam, dep, W, H,
                                                K["carrier_window"])
    n = n_carrier

    # v runs up the carrier: the in-plane direction closest to world up as the
    # camera sees it, so "the top of the plate" is the top on screen too.
    up_ref = cam.yc
    v = _norm(_sub(up_ref, _mul(n, _dot(up_ref, n))))
    u = _norm(_cross(v, n))
    origin = cam.hit_plane(K["px"], K["py"], c, n)
    frame = PortFrame(origin, u, v, n)

    # --- size, then stand-off, then size again.  The stand-off moves every
    # sample's pixel, so a size solved at stand 0 is a size solved against the
    # wrong projection; two passes converge to under 0.01 px.
    W_m, H_m = _size_for(cam, frame, K["plate_px"], K["plate_py"], 0.0)
    stand = solve_stand(cam, frame, W_m, H_m, dep, W, H, ub, K["stand_margin"])
    W_m, H_m = _size_for(cam, frame, K["plate_px"], K["plate_py"], stand)
    stand = solve_stand(cam, frame, W_m, H_m, dep, W, H, ub, K["stand_margin"])
    bx0, bx1, by0, by1 = envelope_px(cam, frame, W_m, H_m, stand)
    plate_w_px, plate_h_px = _plate_chords(cam, frame, W_m, H_m, stand)
    F = K.get("face_px")
    if F and not (bx0 >= F[0] and bx1 <= F[1] and by0 >= F[2] and by1 <= F[3]):
        raise ValueError(
            "the assembly's envelope (%.1f,%.1f)-(%.1f,%.1f) leaves the clean "
            "console face (%.0f,%.0f)-(%.0f,%.0f).  A nameplate whose corner "
            "hangs over the edge of the case it is bolted to is not a "
            "nameplate: shrink plate_px/plate_py or move the anchor."
            % (bx0, by0, bx1, by1, F[0], F[2], F[1], F[3]))

    # --- THE TYPE, SOLVED TO THE LEGIBILITY FLOOR AND NOT TO THE PLATE.
    # The plate is sized to the console face; the word is sized to be readable;
    # and the only question left is whether the second fits inside the first.
    # It is asked here, out loud, and refused if the answer is no -- because
    # the alternative, silently shrinking a 9-letter word until it fits, is how
    # a label ends up at 15.7 px against a 16 px floor with nothing saying so.
    #
    # Every quantity is measured off the PROJECTION of the field itself.  See
    # `rect_px()` for why a px/m at the anchor is not good enough here.
    G = GEO
    n_ch = len(K["label"])
    fa = 0.5 - G["field_inset_w"]
    fb = G["field_h"] / 2.0
    fz = field_face_z(G)          # the plane the type actually lives on
    fx0, fx1, fy0, fy1 = rect_px(cam, frame, W_m, H_m, stand,
                                 -fa, fa, -fb, fb, fz)

    def _chord(a0, b0, a1, b1):
        p0 = cam.project(frame.to_world(a0 * W_m, b0 * H_m, stand + fz * H_m))
        p1 = cam.project(frame.to_world(a1 * W_m, b1 * H_m, stand + fz * H_m))
        return math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    # ALONG THE FIELD'S OWN AXES, THROUGH ITS CENTRE -- not its bounding box.
    # The plate sits 154 px above the principal point and is tilted 7.7 deg in
    # depth, so its projection is a trapezoid: its near end rides UP the screen
    # and its far end rides DOWN, and the BBOX of that quad is 25 % taller than
    # the field is.  Sizing the type to the bbox is sizing it to a rectangle
    # that exists nowhere on the fitting.
    field_w_px = _chord(-fa, 0.0, fa, 0.0)
    field_h_px = _chord(0.0, -fb, 0.0, fb)
    field_w_m, field_h_m = 2.0 * fa * W_m, 2.0 * fb * H_m
    ppm_field_u = field_w_px / field_w_m
    ppm_field_v = field_h_px / field_h_m
    cap_px = float(G["cap_px"])
    cap_m = cap_px / ppm_field_v
    # `size_m` is BLENDER'S FONT.size, not an em -- see the two ratios in GEO.
    # It is the number `build()` hands to `kit.text()`, so it is the number the
    # solve has to produce; calling it `em_m` is what put a half-size label on
    # the ship.
    size_m = cap_m / G["cap_over_size"]
    adv_m = size_m * G["adv_over_size"]
    adv_px = adv_m * ppm_field_u      # the advance across the field's own u
    word_px = n_ch * adv_px
    slack = (field_w_px - word_px) / (2.0 * field_w_px)
    if slack < G["txt_min_slack"]:
        raise ValueError(
            "%s at %.0f px cap needs %.1f px of field width for %d characters "
            "and the field is %.1f px, leaving %.3f of slack against a floor "
            "of %.3f.  Widen the plate, shorten the word, or lower cap_px -- "
            "but not below the fleet's 16 px legibility floor."
            % (K["label"], cap_px, word_px, n_ch, field_w_px, slack,
               G["txt_min_slack"]))
    if cap_m > field_h_m * 0.86:
        raise ValueError(
            "%s at %.0f px cap is %.4f m tall in a %.4f m field -- under 7 %% "
            "of air above and below.  Raise field_h or lower cap_px."
            % (K["label"], cap_px, cap_m, field_h_m))

    mrep = margin_report(dep, W, H, K["carrier_window"], ub, K["stand_margin"])
    clear, where = _clearance(cam, frame, W_m, H_m, stand, dep, W, H)

    look = cam.zc
    out = {
        "code": CODE, "anchor_px": [K["px"], K["py"]],
        "target_px": [K["plate_px"], K["plate_py"]],
        "label": K["label"],
        "frame": frame, "frame_blender": frame.blender(),
        "W_m": W_m, "H_m": H_m, "stand_m": stand, "ubias_m": ub,
        "stand_margin": K["stand_margin"],
        "bbox_px": [bx1 - bx0, by1 - by0],
        "plate_px_measured": [plate_w_px, plate_h_px],
        "face_px": list(F) if F else None,
        "carrier_normal": n_carrier, "normal_used": normal,
        "carrier_base_kept": kept, "carrier_base_total": total,
        "obliq_carrier_plain_ls": math.degrees(math.acos(
            max(-1.0, min(1.0, _dot(n_ls, cam.zc))))),
        "base_vs_plain_ls_deg": math.degrees(math.acos(
            max(-1.0, min(1.0, _dot(n_ls, n_carrier))))),
        "carrier_resid_ls_p50": res_ls[len(res_ls) // 2],
        "carrier_resid_p50": res[len(res) // 2],
        "carrier_resid_p95": res[int(len(res) * 0.95)],
        "carrier_resid_max": res[-1],
        "obliq_carrier": math.degrees(math.acos(
            max(-1.0, min(1.0, _dot(n_carrier, look))))),
        "px_per_m_carrier_u": SMT.axis_px_per_m(cam, origin, u),
        "px_per_m_carrier_v": SMT.axis_px_per_m(cam, origin, v),
        "px_per_m_carrier_n": SMT.axis_px_per_m(cam, origin, n),
        "rakes": SMT.rake_table(cam, u, v, n),
        "size_px": size_m * ppm_field_u, "size_m": size_m, "cap_px": cap_px,
        "adv_m": adv_m,
        "cap_m": cap_m, "word_px": word_px, "txt_slack": slack,
        "field_px": [field_w_px, field_h_px],
        "field_bbox": [fx0, fx1, fy0, fy1],
        "field_m": [field_w_m, field_h_m],
        "px_per_m_field_u": ppm_field_u, "px_per_m_field_v": ppm_field_v,
        "advance_px": adv_px,
        "carrier_grad_m_per_px": mrep["grad_m_per_px"],
        "assembly_clear_m": clear, "assembly_clear_at": where,
        "margin": mrep,
    }
    # The v:n separation is the number the rake is chosen from, and it is a
    # RATIO, not a minimum.  `status_mast` picks a rake when the carrier's own
    # up-axis and its normal project to nearly the same screen direction; here
    # they do not, and this is the measurement that says so.
    out["v_over_n_px_per_m"] = (out["px_per_m_carrier_v"]
                                / max(1e-9, out["px_per_m_carrier_n"]))
    out.update(clearance_report(S, cam, frame, W_m, H_m, stand, dep, W, H))
    if verbose:
        print_plate(out)
    return out


def print_plate(A):
    print("STANDINGS PLATE anchor -- %s" % A["code"])
    print("  target pixel            (%.1f, %.1f)   target size %.0f x %.0f px"
          % (A["anchor_px"][0], A["anchor_px"][1],
             A["target_px"][0], A["target_px"][1]))
    print("  solved size             %.4f x %.4f m   stand-off %.4f m"
          % (A["W_m"], A["H_m"], A["stand_m"]))
    print("  ground plate on screen  %.1f x %.1f px   (target %.0f x %.0f)"
          % (A["plate_px_measured"][0], A["plate_px_measured"][1],
             A["target_px"][0], A["target_px"][1]))
    print("  projected envelope      %.1f x %.1f px   at (%.1f, %.1f) .. "
          "(%.1f, %.1f)   inside the face %s"
          % (A["bbox_px"][0], A["bbox_px"][1], A["bbox"][0], A["bbox"][2],
             A["bbox"][1], A["bbox"][3], A["face_px"]))
    print("  obliquity, carrier      %.2f deg" % A["obliq_carrier"])
    print("  carrier base fit        %d of %d px kept; |resid| p50 %.6f  "
          "p95 %.6f  max %.6f m"
          % (A["carrier_base_kept"], A["carrier_base_total"],
             A["carrier_resid_p50"], A["carrier_resid_p95"],
             A["carrier_resid_max"]))
    print("  ...vs a plain LS fit    obliquity %.2f deg, %.2f deg away, "
          "|resid| p50 %.6f m  (it fits the DRESSING, not the face)"
          % (A["obliq_carrier_plain_ls"], A["base_vs_plain_ls_deg"],
             A["carrier_resid_ls_p50"]))
    print("  px/m on the carrier     u %.1f   v %.1f   n %.1f   (v:n %.2f)"
          % (A["px_per_m_carrier_u"], A["px_per_m_carrier_v"],
             A["px_per_m_carrier_n"], A["v_over_n_px_per_m"]))
    print("  carrier solid behind    %.1f %%   depth %.4f .. %.4f m"
          % (A["carrier_solid_pct"], A["carrier_depth_m"][0],
             A["carrier_depth_m"][1]))
    print("  carrier depth gradient  %.6f m per screen px" %
          A["carrier_grad_m_per_px"])
    M = A["margin"]
    print("  stand-off margin        %.4f m = %.1f x ubias = %.2f px of the "
          "carrier's own gradient  (floor 0.5 px)"
          % (M["margin_m"], A["stand_margin"], M["margin_px"]))
    print("  assembly clearance      %.5f m at px %s"
          % (A["assembly_clear_m"], A["assembly_clear_at"][:2]))
    print("  field, measured         %.1f x %.1f px   (%.4f x %.4f m, "
          "%.1f / %.1f px per m)"
          % (A["field_px"][0], A["field_px"][1], A["field_m"][0],
             A["field_m"][1], A["px_per_m_field_u"], A["px_per_m_field_v"]))
    print("  type                    %s -- cap %.2f px (floor 16), FONT.size "
          "%.2f px, advance %.3f px, word %.1f px, slack %.3f (floor %.3f)"
          % (A["label"], A["cap_px"], A["size_px"], A["advance_px"],
             A["word_px"], A["txt_slack"], GEO["txt_min_slack"]))
    print("  rake table (this surface's own, not inherited):")
    print("      %-8s %-11s %s" % ("rake", "obliquity", "note"))
    for r in A["rakes"]:
        print("      %-8.0f %-11.2f %s"
              % (r["rake_deg"], r["obliq_deg"],
                 "<-- shipped (flat on the carrier)"
                 if abs(r["rake_deg"]) < 0.5 else ""))
    print("  hotspot                 x %.0f y %.0f w %.0f h %.0f"
          % (A["hotspot"]["x"], A["hotspot"]["y"],
             A["hotspot"]["w"], A["hotspot"]["h"]))
    worst = min(A["clearances"], key=lambda c: (-c["overlap_px2"], c["gap_px"]))
    print("  keep-outs               %d rects, %.0f px^2 total overlap; "
          "nearest %s at %.1f px (%.1f px euclid)"
          % (len(A["clearances"]),
             sum(c["overlap_px2"] for c in A["clearances"]),
             worst["what"], worst["gap_px"], worst["gap_euclid_px"]))
    if A["off_frame"]:
        print("  !! ENVELOPE RUNS OFF THE 1280x720 FRAME")


def anchor_json(A):
    """The published record -- every number the solver printed, so
    `check/regress_standings.py` can re-solve and diff it."""
    f = A["frame"]
    return {
        "code": A["code"], "label": A["label"],
        "anchor_px": A["anchor_px"], "target_px": A["target_px"],
        "frame": f.json(),
        "W_m": A["W_m"], "H_m": A["H_m"], "stand_m": A["stand_m"],
        "ubias_m": A["ubias_m"], "stand_margin": A["stand_margin"],
        "bbox_px": A["bbox_px"], "bbox": A["bbox"],
        "plate_px_measured": A["plate_px_measured"], "face_px": A["face_px"],
        "hotspot": A["hotspot"],
        "carrier_normal": A["carrier_normal"],
        "obliq_carrier": A["obliq_carrier"],
        "carrier_resid_p50": A["carrier_resid_p50"],
        "carrier_resid_ls_p50": A["carrier_resid_ls_p50"],
        "obliq_carrier_plain_ls": A["obliq_carrier_plain_ls"],
        "base_vs_plain_ls_deg": A["base_vs_plain_ls_deg"],
        "carrier_base_kept": A["carrier_base_kept"],
        "carrier_base_total": A["carrier_base_total"],
        "carrier_resid_p95": A["carrier_resid_p95"],
        "carrier_resid_max": A["carrier_resid_max"],
        "px_per_m_carrier_u": A["px_per_m_carrier_u"],
        "px_per_m_carrier_v": A["px_per_m_carrier_v"],
        "px_per_m_carrier_n": A["px_per_m_carrier_n"],
        "v_over_n_px_per_m": A["v_over_n_px_per_m"],
        "size_px": A["size_px"], "size_m": A["size_m"],
        "adv_m": A["adv_m"], "cap_px": A["cap_px"],
        "cap_m": A["cap_m"], "word_px": A["word_px"],
        "txt_slack": A["txt_slack"], "field_px": A["field_px"],
        "field_m": A["field_m"], "field_bbox": A["field_bbox"],
        "px_per_m_field_u": A["px_per_m_field_u"],
        "px_per_m_field_v": A["px_per_m_field_v"],
        "advance_px": A["advance_px"],
        "carrier_grad_m_per_px": A["carrier_grad_m_per_px"],
        "assembly_clear_m": A["assembly_clear_m"],
        "carrier_solid_pct": A["carrier_solid_pct"],
        "carrier_depth_m": A["carrier_depth_m"],
        "clearances": A["clearances"],
        "margin": A["margin"],
        "rakes": A["rakes"],
        "geo": GEO,
    }


# ===========================================================================
# BLENDER -- everything below needs bpy.  The import is deferred so the solver
# half runs under a plain `python3`, exactly as refit_port.py does it.
# ===========================================================================
def _bpy():
    import bpy
    return bpy


RTYPES = {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}


def renderables(scene):
    return [o for o in scene.objects if o.type in RTYPES]


def build_cockpit_scene():
    """THE SHIPPED WIDE SHOT, rebuilt.

    `cockpit/combine.py` is the file that made `combined/main_plate.png`, and
    this is its scene half, verbatim in behaviour: `shell.build(PARAMS)` with
    `exterior = 0` and the project default `raytrace`, then every
    `cockpit/modules/<CODE>/build.py`'s `add_props`, then every
    `cockpit/dressing/tier*.py`'s `add_tier*`.  It is a re-BUILD and never a
    re-BAKE: the plate is not rendered here and `cockpit/` is opened read-only.

    Whether it really is the same scene is not asserted -- the `depth` step
    renders a colour control and scores it against the shipped plate, because
    a depth map that does not belong to those pixels is worse than none.
    """
    bpy = _bpy()
    import glob
    import importlib.util
    for p in (CK, os.path.join(CK, "dressing")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import shell                                               # noqa: E402

    codes = sorted(d for d in os.listdir(os.path.join(CK, "modules"))
                   if os.path.isdir(os.path.join(CK, "modules", d))
                   and os.path.exists(os.path.join(CK, "modules", d,
                                                   "build.py")))
    P = dict(shell.PARAMS)
    P["exterior"] = 0
    P["raytrace"] = int(os.environ.get("CKPT_RAYTRACE",
                                       shell.PARAMS["raytrace"]))
    scene = shell.build(P)
    scene.render.film_transparent = True
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    def _load(path, tag):
        spec = importlib.util.spec_from_file_location(tag, path)
        m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        return m

    for code in codes:
        _load(os.path.join(CK, "modules", code, "build.py"),
              "sb_mod_" + code).add_props(P, mats)
    for tf in sorted(glob.glob(os.path.join(CK, "dressing", "tier*.py"))):
        nm = os.path.splitext(os.path.basename(tf))[0]
        _load(tf, "sb_dr_" + nm)
        getattr(sys.modules["sb_dr_" + nm], "add_" + nm)(P, mats)
    bpy.context.view_layer.update()
    return scene, P, mats, codes


def render_to(scene, path, visible, holdout=()):
    """Render only `visible`; `holdout` objects stay in the depth buffer but
    punch alpha, so a sprite is correctly clipped by geometry in FRONT of it.

    Lifted in behaviour from `cockpit/modules/OTA/build.py:591`, which is how
    every one of the nine far-shot sprites in `combined/manifest.json` was
    made.  Here it is load-bearing in one direction only -- nothing in the
    cockpit stands in front of the C3 console face -- but it is what makes the
    claim provable rather than assumed.
    """
    bpy = _bpy()
    vis = set(o.name for o in visible)
    hold = set(o.name for o in holdout) - vis
    saved, hsave = {}, {}
    for o in renderables(scene):
        saved[o.name] = o.hide_render
        o.hide_render = not (o.name in vis or o.name in hold)
    for o in holdout:
        if o.name in hold:
            hsave[o.name] = o.is_holdout
            o.is_holdout = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in holdout:
        if o.name in hsave:
            o.is_holdout = hsave[o.name]
    for o in renderables(scene):
        o.hide_render = saved[o.name]


def glow_render(scene, path, objs, holdout=()):
    """The hover mask: the same objects, white-emissive, Standard view
    transform.  `live3d/index.html`'s `.glow` rule does the tinting and the
    bloom in CSS, exactly as it does for the eight maintenance modules -- this
    file must not bake a colour into the mask.
    """
    import shell                                               # noqa: E402
    g = shell.material("sb_glowmask", (1, 1, 1, 1), 0.0, 0.5,
                       emission=(1, 1, 1, 1), emit_strength=1.0,
                       texture=False)
    saved = {}
    for o in objs:
        if o.type != 'MESH':
            continue
        saved[o.name] = list(o.data.materials)
        if not len(o.data.materials):
            o.data.materials.append(g)
        for i in range(len(o.data.materials)):
            o.data.materials[i] = g
    vt, look = scene.view_settings.view_transform, scene.view_settings.look
    try:
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
    except Exception:                                          # noqa: BLE001
        pass
    render_to(scene, path, objs, holdout=holdout)
    try:
        scene.view_settings.view_transform = vt
        scene.view_settings.look = look
    except Exception:                                          # noqa: BLE001
        pass
    for o in objs:
        if o.name in saved:
            for i, m in enumerate(saved[o.name]):
                o.data.materials[i] = m


def render_depth(scene, out_bin):
    """Blender's Z pass as raw little-endian float32, top-down.

    The same routine `three-exploration/pipeline/transliterate.py:182` uses for
    every module's `depth.bin`, so the file this writes is the same kind of
    file `refit_port.read_depth()` already reads.  EXR is scene-referred, so no
    view transform touches it and the values are true LINEAR VIEW DEPTH in
    metres along the camera's -Z.
    """
    bpy = _bpy()
    import numpy as np
    vl = scene.view_layers[0]
    vl.use_pass_z = True
    if hasattr(scene, "compositing_node_group"):
        ng = bpy.data.node_groups.get("sb_depth_pass")
        if ng is None:
            ng = bpy.data.node_groups.new("sb_depth_pass", "CompositorNodeTree")
            rl = ng.nodes.new('CompositorNodeRLayers')
            go = ng.nodes.new('NodeGroupOutput')
            ng.interface.new_socket('Image', in_out='OUTPUT',
                                    socket_type='NodeSocketColor')
            ng.links.new(rl.outputs['Depth'], go.inputs['Image'])
        scene.compositing_node_group = ng
        scene.use_nodes = True
    else:
        scene.use_nodes = True
        t = scene.node_tree
        t.nodes.clear()
        rl = t.nodes.new('CompositorNodeRLayers')
        co = t.nodes.new('CompositorNodeComposite')
        t.links.new(rl.outputs['Depth'], co.inputs['Image'])
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '32'
    scene.render.image_settings.exr_codec = 'NONE'
    tmp = out_bin.replace(".bin", "_tmp.exr")
    scene.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    W, H = scene.render.resolution_x, scene.render.resolution_y
    img = bpy.data.images.load(tmp, check_existing=False)
    buf = np.empty(W * H * img.channels, dtype=np.float32)
    img.pixels.foreach_get(buf)
    d = np.ascontiguousarray(
        buf.reshape(H, W, img.channels)[:, :, 0][::-1])       # Blender is up
    bpy.data.images.remove(img)
    os.remove(tmp)
    scene.use_nodes = False
    if hasattr(scene, "compositing_node_group"):
        scene.compositing_node_group = None
    d.astype('<f4').tofile(out_bin)
    finite = d[d < 1e9]
    print("  depth -> %s   near %.4f  far %.4f  bg %d px"
          % (os.path.basename(out_bin), float(finite.min()),
             float(finite.max()), int((d >= 1e9).sum())))
    return d


# ------------------------------------------------------------------ the kit
def build(A, scene=None):
    """The nameplate itself, at the solved frame.

    Built in the plate's OWN space -- local +X across, +Y up the carrier, +Z
    out of it -- and hung on one empty placed from the solver's world frame.
    That is `cockpit/slots.py`'s convention and `dressing/tier1.py`'s
    construction, and it is used here rather than `refit_port.build()`'s
    to_world() because every primitive this fitting is made of comes from
    `dressing/kit.py`, which is what the surface underneath is made of.
    """
    bpy = _bpy()
    from mathutils import Matrix, Vector
    for p in (CK, os.path.join(CK, "dressing")):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from dressing import kit                               # noqa: E402
    except ImportError:                                        # pragma: no cover
        import kit                                             # noqa: E402

    G = GEO
    Wm, Hm, stand = A["W_m"], A["H_m"], A["stand_m"]
    Fb = A["frame_blender"]
    M = Matrix(((Fb.u[0], Fb.v[0], Fb.n[0]),
                (Fb.u[1], Fb.v[1], Fb.n[1]),
                (Fb.u[2], Fb.v[2], Fb.n[2])))
    loc = Vector(Fb.o) + Vector(Fb.n) * stand
    root = kit.frame_empty("sb_root", loc, M.to_euler())

    br = kit.mat("brass")
    made = []
    hw, hh = Wm / 2.0, Hm / 2.0
    tp = G["t_plate"] * Hm
    # --- the four stand-offs, BEHIND the plate.  Built first because they are
    # what the plate is bolted out on, and because the gap they hold open is
    # the only part of this fitting whose depth the wide camera can resolve.
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        cx = sx * (hw - G["spacer_in_w"] * Wm)
        cy = sy * (hh - G["spacer_in_v"] * Hm)
        made.append(kit.cyl("sb_spacer_%d" % i, (cx, cy, -stand / 2.0),
                            G["spacer_r"] * Hm, stand, kit.mat("steel"),
                            verts=12, smooth=False))
    # --- the brass ground plate
    made.append(kit.box("sb_plate", (0.0, 0.0, tp / 2.0), (Wm, Hm, tp), br,
                        bevel=G["bevel_plate"] * Hm))
    # --- the end lugs: the plate is let into the console's own end ribs, so it
    # reads as installed rather than as something laid on top.
    lw, lh, lt = G["lug_w"] * Wm, G["lug_h"] * Hm, G["t_lug"] * Hm
    for i, sx in enumerate((-1, 1)):
        made.append(kit.box("sb_lug_%d" % i, (sx * hw, 0.0, lt / 2.0),
                            (2 * lw, lh, lt), br, bevel=0.0016))
        made += kit.rivet_row("sb_lugrv_%d" % i,
                              (sx * hw, -lh * 0.34, lt),
                              (sx * hw, lh * 0.34, lt), 2,
                              r=G["screw_r"] * Hm * 0.55)
    # --- the recessed dark field the type is written on
    fw = Wm - 2.0 * G["field_inset_w"] * Wm
    fh = G["field_h"] * Hm
    # The field face stands PROUD of the brass and is recessed relative to the
    # BEZEL -- see `field_face_z()`.  Its slab reaches back into the ground
    # plate, which is what a let-in panel does; only its face is ever seen.
    fz = field_face_z(G) * Hm
    made.append(kit.box("sb_field", (0.0, 0.0, fz - G["t_field"] * Hm / 2.0),
                        (fw, fh, G["t_field"] * Hm), kit.mat("case"),
                        bevel=0.0012))
    # --- the brass bezel: a chamfered bar, not a lip.  At 44.5 px/m of carrier
    # normal a lip has no parallax to read by; a bar has a facet that takes the
    # shell's key light.
    made += kit.bez_frame("sb_bez", 0.0, 0.0,
                          fw + 2.0 * G["bez_bar"] * Hm,
                          fh + 2.0 * G["bez_bar"] * Hm,
                          fz - G["t_field"] * Hm * 0.5,
                          tp + G["bez_proud"] * Hm, br,
                          bar=G["bez_bar"] * Hm)
    # --- THE WORD.  Geometry, because a permanent label stamped on the ship is
    # geometry and only values are DOM (CONVERSION_BRIEF 1786-1789).  Ivory on
    # the dark field, never dark on brass: LEADERBOARD 6.3 measured dark
    # engraved type on a bright plate at 0.0014 of luma margin under a raking
    # key, and a bright plate cannot be made safe for dark type.
    # Placed ON the field face; `kit.text` extrudes symmetrically, so the
    # letter faces land `txt_proud` proud of the field and still clear under
    # the bezel (`type_face_z`).
    made.append(kit.text("sb_txt", A["label"], A["size_m"], kit.mat("ivory"),
                         (0.0, 0.0, fz),
                         extrude=G["txt_proud"] * Hm))
    # --- domed slot-head screws through the plate ends.  ONE PER END, ON THE
    # CENTRELINE.  `screw_in_v` is 0.500 -- half of H -- so an inset measured
    # from the plate edge lands every fixing at v = 0 whatever its sign: the
    # four-corner loop this used to be placed screws 0 and 2 at the same point
    # and 1 and 3 at the other, two pairs of coincident solids z-fighting in
    # a render where a 10 mm step is 0.45 screen px and the fight would have
    # been the only thing visible of them.  The count follows the geometry
    # table rather than contradicting it: at 0.500 there is one row, not two.
    for i, sx in enumerate((-1, 1)):
        made += kit.screw("sb_scr_%d" % i,
                          (sx * (hw - G["screw_in_w"] * Wm),
                           hh - G["screw_in_v"] * Hm, tp),
                          r=G["screw_r"] * Hm)
    kit.parent_to(made, root)
    bpy.context.view_layer.update()
    return {"root": root, "objs": [o for o in made if o.type in RTYPES],
            "all": made + [root]}


# ===========================================================================
# THE KEEP-OUT LIST -- read from the two SHIPPED files, never copied into one.
# ===========================================================================
def wide_keepouts():
    """The eighteen rectangles on the wide shot this fitting must not touch.

    Nine module hover hotspots out of `cockpit/combined/manifest.json` (the
    file `app.js` itself reads, in place) and nine telltale-mast envelopes out
    of `live3d/status.js`'s `WIDE_MASTS` (the file `app.js` itself imports).
    Both are read here rather than transcribed, because a transcription is a
    nineteenth place for a placement number to live and drift, and because
    `status.js` is on this change's do-not-write list -- so reading it is the
    only honest way to know what it says.
    """
    import re
    out = {}
    MAN = json.load(open(os.path.join(CK, "combined", "manifest.json")))
    for code, m in sorted(MAN["modules"].items()):
        r = m["far"]["hotspot"]
        out["hot_" + code] = {"hotspot": {"x": r["x"], "y": r["y"],
                                          "w": r["w"], "h": r["h"]},
                              "from": "cockpit/combined/manifest.json"}
    src = open(os.path.join(LIVE3D, "status.js")).read()
    i = src.index("export const WIDE_MASTS")
    blk = src[i:src.index("};", i)]
    for m in re.finditer(r"(\w+):\s*\{[^{}]*env:\s*\[([^\]]*)\]", blk):
        e = [float(x) for x in m.group(2).split(",")]
        out["tell_" + m.group(1)] = {"hotspot": {"x": e[0], "y": e[1],
                                                 "w": e[2], "h": e[3]},
                                     "from": "live3d/status.js WIDE_MASTS"}
    if len(out) != 18:
        raise ValueError("expected 9 hotspots + 9 mast envelopes, read %d -- "
                         "one of the two shipped files has moved" % len(out))
    return out


# ===========================================================================
# THE COMMANDS
# ===========================================================================
def cmd_depth():
    """Render the wide shot's depth pass and publish the pseudo-module.

    Also renders a COLOUR CONTROL and scores it against the shipped
    `cockpit/combined/main_plate.png`.  That comparison is the whole warrant
    for this file: a depth map is only a measurement of a picture if it was
    rendered from the scene that made the picture, and nothing else here can
    tell you whether it was.
    """
    bpy = _bpy()
    import math as _m
    import numpy as np
    scene, P, mats, codes = build_cockpit_scene()
    cam = scene.camera
    W, H = scene.render.resolution_x, scene.render.resolution_y
    os.makedirs(ASSET, exist_ok=True)

    # ---- the control.  Written to a scratch path and compared, NEVER kept and
    # never written anywhere near cockpit/.
    ctrl = os.environ.get(
        "SB_CONTROL", os.path.join(os.environ.get("TMPDIR", "/tmp"),
                                   "sb_control_plate.png"))
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    scene.render.filepath = ctrl
    bpy.ops.render.render(write_still=True)
    sys.path.insert(0, CK)
    from nnscale import decode                                 # noqa: E402

    def rgba(fn):
        w, h, n, rows = decode(fn)
        if n == 4:
            return w, h, np.frombuffer(b"".join(bytes(r) for r in rows),
                                       dtype=np.uint8).reshape(h, w, 4)
        out = bytearray()
        for r in rows:
            for x in range(w):
                out += bytes(r[x * n:x * n + 3]) + b"\xff"
        return w, h, np.frombuffer(bytes(out),
                                   dtype=np.uint8).reshape(h, w, 4)
    _w, _h, A_ = rgba(ctrl)
    _w2, _h2, B_ = rgba(PLATE_PNG)
    d = A_.astype(np.float64) - B_.astype(np.float64)
    rms = float(_m.sqrt((d * d).mean()))
    mx = int(np.abs(d).max())
    x0, x1, y0, y1 = STANDINGS["carrier_window"]
    dw = d[y0:y1 + 1, x0:x1 + 1]
    print("CONTROL vs cockpit/combined/main_plate.png:")
    print("   whole frame     rms %.4f  max %d levels" % (rms, mx))
    print("   carrier window  rms %.4f  max %d levels"
          % (_m.sqrt((dw * dw).mean()), int(np.abs(dw).max())))
    if rms > 0.5 or mx > 3:
        print("   !! THE REBUILT SCENE IS NOT THE SHIPPED SCENE.  Everything "
              "below is measuring a different cockpit; stop here.")

    # ---- the depth pass
    render_depth(scene, os.path.join(ASSET, "depth.bin"))

    def to3(v):
        return [v[0], v[2], -v[1]]
    from mathutils import Vector                                # noqa: E402
    m = cam.matrix_world
    S = {
        "code": CODE,
        "what": "THE WIDE SHOT, as a pseudo-module.  Not one of the nine: no "
                "entry in cockpit/combined/manifest.json, none in "
                "transition.json, no measured M, no baked plate of its own.  "
                "It exists so pipeline/refit_port.py's solver can be pointed "
                "at the cockpit plate the same way it is pointed at a module.",
        "plate": "../../../cockpit/combined/main_plate.png",
        "plate_control_rms": rms, "plate_control_max_levels": mx,
        "render": {"w": W, "h": H},
        "camera": {"lens_mm": cam.data.lens,
                   "sensor_mm": cam.data.sensor_width,
                   "sensor_fit": cam.data.sensor_fit,
                   "angle_x_deg": _m.degrees(cam.data.angle_x),
                   "fov_y_deg": _m.degrees(
                       2 * _m.atan(_m.tan(cam.data.angle_x / 2) * H / W)),
                   "clip": [cam.data.clip_start, cam.data.clip_end],
                   "pos": to3(m.translation),
                   "forward": to3((m.to_3x3()
                                   @ Vector((0, 0, -1))).normalized()),
                   "up": to3((m.to_3x3() @ Vector((0, 1, 0))).normalized())},
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        # NOT a measured occlusion bias -- the wide shot has no depth composite
        # and no split pass.  It is the fleet's shared default, carried as the
        # UNIT the stand-off margin and margin_report()'s half-pixel floor are
        # expressed in.  See the module docstring.
        "ubias_m": 0.0005,
        "ubias_is_not_a_bias": True,
        "props": wide_keepouts(),
    }
    with open(os.path.join(ASSET, "scene.json"), "w") as f:
        json.dump(S, f, indent=1)
    print("WROTE %s" % os.path.join(ASSET, "scene.json"))


def cmd_render():
    """Build the nameplate at the solved frame and write its two sprites."""
    A = solve_plate()
    scene, P, mats, codes = build_cockpit_scene()
    before = set(o.name for o in renderables(scene))
    R = build(A)
    objs = R["objs"]

    # --- THE LOOP THE HALF-SIZE LABEL GOT THROUGH.  `solve_plate()` is pure
    # stdlib: it cannot ask Blender how big the word actually came out, so for
    # one build every guard in it was checking its own arithmetic against
    # itself and passing while the type drew at 0.506 of the solved width and a
    # 9.1 px cap against a 16 px floor.  THIS closes that loop: it measures the
    # BUILT `sb_txt` mesh and refuses if it disagrees with what was solved.
    #
    # Measured in the plate's own local frame, where the solve's metres live,
    # so it compares metres with metres and never a projection with a
    # projection.  1 % is far tighter than the 1.97x the bug was.
    txtobj = [o for o in objs if o.name == "sb_txt"]
    if not txtobj:
        raise ValueError("sb_txt was not built -- nothing to verify")
    co = [txtobj[0].matrix_local @ v.co for v in txtobj[0].data.vertices]
    drawn_w = max(c.x for c in co) - min(c.x for c in co)
    drawn_h = max(c.y for c in co) - min(c.y for c in co)
    # The drawn bbox is the INK: 9 advances less the right sidebearing of the
    # last glyph and the left of the first.  Compare against the advance run,
    # which is what the field has to hold, and allow the sidebearings.
    want_w = len(A["label"]) * A["adv_m"]
    if not (0.86 * want_w <= drawn_w <= 1.02 * want_w):
        raise ValueError(
            "THE BUILT WORD DOES NOT MATCH THE SOLVE.  `sb_txt` measures "
            "%.6f m across; the solve asked for %d advances of %.6f m = "
            "%.6f m (ratio %.4f).  The usual cause is GEO's two font ratios: "
            "`kit.text` hands `size` to Blender's FONT.size, which IS NOT AN "
            "EM (one size unit is 0.51769 em for Courier New Bold).  "
            "Re-measure with pipeline/typemetrics.py's method and fix "
            "cap_over_size / adv_over_size."
            % (drawn_w, len(A["label"]), A["adv_m"], want_w,
               drawn_w / want_w))
    # Round letters overshoot the cap line: "STANDINGS" measures 1.049 of a
    # flat-topped "M", which is the face's own overshoot and not an error.
    if not (0.94 * A["cap_m"] <= drawn_h <= 1.10 * A["cap_m"]):
        raise ValueError(
            "THE BUILT CAP HEIGHT DOES NOT MATCH THE SOLVE.  `sb_txt` "
            "measures %.6f m tall; the solve asked for a %.2f px cap = "
            "%.6f m (ratio %.4f).  See GEO's cap_over_size."
            % (drawn_h, A["cap_px"], A["cap_m"], drawn_h / A["cap_m"]))
    print("VERIFIED  built word %.6f m vs solved %.6f m (%.4f); "
          "built cap %.6f m vs solved %.6f m (%.4f)"
          % (drawn_w, want_w, drawn_w / want_w,
             drawn_h, A["cap_m"], drawn_h / A["cap_m"]))

    others = [o for o in renderables(scene) if o.name in before]
    os.makedirs(ASSET, exist_ok=True)
    render_to(scene, os.path.join(ASSET, "prop.png"), objs, holdout=others)
    print("WROTE prop.png")
    glow_render(scene, os.path.join(ASSET, "glow.png"), objs, holdout=others)
    print("WROTE glow.png")
    # THE TYPE, ALONE.  This is `gt_platen0.png`'s job on the nine
    # (`check/verify_assets.py`): a render of the lettering by itself, so its
    # covered pixels are EXACTLY the glyph coverage and the fleet's worst-pixel
    # legibility metric can be run on the RUNNING PAGE rather than on a
    # threshold guess.  It is evidence, not a shipped layer -- nothing loads it.
    txt = [o for o in objs if o.name == "sb_txt"]
    render_to(scene, os.path.join(ASSET, "gt_type.png"), txt,
              holdout=others + [o for o in objs if o.name != "sb_txt"])
    print("WROTE gt_type.png")
    rec = anchor_json(A)
    rec["drawn_word_m"] = drawn_w
    rec["drawn_cap_m"] = drawn_h
    rec["prop"] = "prop.png"
    rec["glow"] = "glow.png"
    rec["gt_type"] = "gt_type.png"
    rec["tris"] = sum(len(o.data.polygons) for o in objs
                      if getattr(o, "data", None)
                      and hasattr(o.data, "polygons"))
    with open(os.path.join(ASSET, "standings.json"), "w") as f:
        json.dump(rec, f, indent=1)
    print("WROTE standings.json   (%d meshes, %d faces)"
          % (len(objs), rec["tris"]))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else \
        sys.argv[1:]
    if "depth" in argv:
        cmd_depth()
        return 0
    if "render" in argv:
        cmd_render()
        return 0
    A = solve_plate()
    if "--json" in argv:
        out = argv[argv.index("--json") + 1]
        with open(out, "w") as f:
            json.dump(anchor_json(A), f, indent=1)
        print("WROTE %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
