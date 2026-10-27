"""
THE REFIT PORT -- one parametric builder, nine modules.

`live3d/design/FIX_UPLOAD.md` is the design.  This file is the part of it that
gets written once: a hexagonal brass access port with a six-leaf iris cover,
bolted to the SHIP STRUCTURE beside an instrument, never onto its faceplate.
Every dimension is a fraction of W, the port's width across flats, so the same
call serves all nine modules at their own size and their own anchor.

    from refit_port import solve_anchor, build, export
    A = solve_anchor("KVS", px=364, py=700, port_px=56)   # no bpy needed
    P = build("kvs_refit", A["frame_blender"], A["W_m"])   # needs bpy
    export("KVS", A, P)                                    # glb + scene.json

THREE HALVES, AND ONLY ONE OF THEM NEEDS BLENDER
------------------------------------------------
* `solve_anchor()` and everything above it is **pure stdlib**.  It reads the
  module's shipped `scene.json` + `depth.bin` and answers, for a target pixel:
  where is that in world space, what is the carrier's own surface normal there,
  how big is the port in metres, and does it clear every hotspot and every
  declared readout rect.  Run it with plain `python3` while you are choosing an
  anchor; it prints its own evidence.
* `build()` needs `bpy`.  It returns a dict of Blender objects and a manifest.
* `export()` writes `<CODE>/refit.glb` and merges a `"refit"` block into that
  module's `scene.json`.  **It re-renders nothing.**  That is decision 3 of
  FIX_UPLOAD section 0 and it is the reason no module's recorded evidence moves.

CONVENTIONS  (they are `cockpit/dressing/kit.py`'s, deliberately)
----------------------------------------------------------------
* The port is authored in its own frame: local +X = `u` (across the port,
  screen-rightish), +Y = `v` (up the carrier), +Z = `n` (out of the carrier,
  toward the camera).  `PortFrame.to_world()` is the only place that mapping
  lives.
* Every builder returns a list of objects; every object and material is
  prefixed `rp_`.
* NEVER a float in an object name -- Blender parses `.NNN` as a duplicate
  suffix.  Indices only.
* Fractions of W are module-level constants in `GEO`, not magic numbers.

FIVE THINGS THAT WILL BITE, ALL OF THEM MEASURED
------------------------------------------------
1. **`ubias_m`.**  The depth composite is `if (vLinDepth > baked - uBias)
   discard`.  A live surface standing less proud of the baked plate than the
   module's own `ubias_m` is deleted silently (CONVERSION_BRIEF trap 24; it
   cost PKT 5.7 rms).  So EVERY surface of this port stands proud, and
   `GEO["z_floor"]` is clamped against `scene.json -> ubias_m` at build time.
   FIX_UPLOAD section 1.1 wants a well "~10 % of W deep" under a frame standing
   "5.5 % of W proud"; a well cut BELOW the mounting surface is entirely behind
   the baked plate and would be discarded in full.  The port is therefore built
   as a raised boss: the frame face stands `z_face` proud and the throat floor
   stands `z_floor` proud, and the well is the difference.  See NOTES.
2. **Trap 21: `dress()` forces `THREE.FrontSide`.**  A one-sided Blender face
   is deleted with no error and an empty `auditScene()`.  An iris leaf is
   exactly the single-triangle shape the trap names, so every leaf here is a
   CLOSED PRISM, not a triangle -- the port survives FrontSide by construction.
   The one deliberately one-sided surface is the throat wall, which is wound
   INWARD because the inside of a well is what you look at.  Run
   `facingAudit(camera)` anyway; that is what it is for.
3. **The carrier is not the faceplate and does not share its normal.**
   FIX_UPLOAD section 3.1 says the port takes "the module's own working-face
   normal".  Measured on KVS, the carrier named in the placement table (the
   front deck) sits **37 deg** off the console face normal and at **49 deg**
   obliquity to the close camera, not 12.35.  A port on the console normal
   would stand 15 mm off the deck on one edge.  `solve_anchor()` therefore
   measures the CARRIER's own normal out of `depth.bin` and offers both, and
   says which is which.  Do not assume.
4. **Root scale, and it is 1.0 on the path you are actually on.**  DNSM 0.78,
   MQB 0.70, PKT 1.15.  Geometry authored inside a scaled root comes out
   scaled; pass `root_scale=` and the builder divides every dimension by it,
   so `W` is always the WORLD size you asked for.  Give `build()` a frame in
   the same space you are authoring in.
   **BUT: the `refit` / `mast` entry points CLEAR THE SCENE and build in WORLD
   coordinates from the solver's own world-space frame, so on that path there
   is no root to be inside and `root_scale` MUST STAY 1.0.**  MQB was told to
   pass 0.70 there and correctly refused: it would have shipped the port
   1.43x too big with nothing printed and nothing failing.  `build()` now
   REFUSES a non-unit `root_scale` in an empty scene and prints the
   authoring-space and world sizes either way -- `check_root_scale()`.
5. **Six-fold symmetry hides a 60 deg step.**  The ratchet in FIX_UPLOAD
   section 5.3 steps 60 deg per phase around a six-fold-symmetric ring, which
   is invisible.  The ring built here carries ONE index tooth so the step can
   be seen.

WHAT THIS FILE DELIBERATELY DOES NOT DO
---------------------------------------
No readout plane, no `text_planes` entry, no baked pixel, no re-render.  All of
the port's text is a screen-space DOM docket (`live3d/refit.js`), which is why
`check_text.py`, `verify_assets.py`'s type audit and `check_occlusion.py`'s
question 5 are NOT ENGAGED by this component rather than merely satisfied.
Keep it that way.
"""
import json
import math
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)


# ===========================================================================
# GEOMETRY TABLE -- every dimension as a fraction of W (width across flats).
# Anything you would otherwise type as a number in build() belongs here.
# ===========================================================================
GEO = {
    # --- radii, as circumradius multiples of W.  A regular hexagon of
    #     across-flats W has circumradius W / sqrt(3) = 0.57735 W.
    "r_out":      0.57735,   # frame outer circumradius  (across flats = 1.00 W)
    "r_lip":      0.53000,   # top-face chamfer
    "r_in":       0.41570,   # throat mouth              (across flats = 0.72 W)
    "r_leaf":     0.42200,   # leaves reach just past the throat mouth
    # THE STAR.  Six leaves that exactly tile a hexagon have no seams and read
    # as one flat plate -- measured, not guessed: the first build looked like a
    # lid.  A 3 deg gap each side of every leaf opens a full-depth slot down to
    # the dark throat, and the six slots meeting at a small hub ARE the
    # six-pointed star FIX_UPLOAD 1.1 calls the port's identity.
    "leaf_gap_deg": 3.4,
    "leaf_hub":     0.070,   # the leaves stop short of the centre
    "leaf_bevel":   0.022,   # top face inset, so every seam has a lit edge

    # --- heights along +n, as multiples of W, measured from the CARRIER plane.
    #     Nothing may be at or below 0 + ubias_m; see note 1 in the docstring.
    "z_rail":     0.028,     # service-rail top
    "z_seat":     0.058,     # port body underside / throat floor
    "z_leaf":     0.130,     # iris leaves
    "z_face":     0.158,     # frame face.  well depth = z_face - z_seat = 0.10 W
    "t_leaf":     0.016,     # leaf thickness
    "t_ratchet":  0.011,     # ratchet ring thickness

    # --- the ratchet.  ONE INDEX TOOTH, no ring.  Three measured reasons, all
    # of them found by building it:
    #   * a ring INSIDE the well is seen edge-on at any obliquity and reads as
    #     a bar across the aperture -- it destroyed KVS's open state at 57 deg;
    #   * a ring ON the face has to be 12-sided to look turned, and a 12-sided
    #     ring on a 6-sided frame turns the port into a dodecagon.  The
    #     hexagonal silhouette is the whole recognition claim (FIX_UPLOAD 1.2:
    #     there is no hexagon anywhere else in the fleet) and the ring ate it;
    #   * a six-fold-symmetric ring stepping 60 deg per phase is
    #     indistinguishable from a ring that has not moved.
    # One mark that moves 60 deg is the entire readable content of the idea, at
    # 12 triangles.  FIX_UPLOAD 9 lists the ratchet ring as the second thing to
    # cut; this cuts the ring and keeps the read.
    "r_ratchet_o": 0.52000,
    "r_ratchet_i": 0.44000,
    "z_ratchet":   0.000,    # relative to the frame FACE

    # --- rails inside the throat ("says something goes in here")
    "rail_u":     0.130,     # +/- offset across the throat
    "rail_w":     0.017,     # half-width
    "rail_v":     0.200,     # +/- length up the throat
    "rail_h":     0.013,     # height above the floor

    # --- the state jewel, on the frame's lower facet
    "jewel_v":   -0.455,     # centre, in W units, on the frame face
    "jewel_r":    0.048,
    "jewel_h":    0.030,

    # --- the tally flag, lower-right facet, flips up once a refit APPLIES
    "tally_u":    0.330,
    "tally_v":   -0.330,
    "tally_w":    0.075,
    "tally_h":    0.115,
    "tally_t":    0.012,

    # --- the shared brass SERVICE RAIL (FIX_UPLOAD section 4).  The port
    #     claims the first 1.3 W; the telltale mast mounts at 1.5 W.
    "srail_half":  0.650,    # the port's claim, +/- along u
    "srail_v":     0.075,    # half-thickness across       (0.15 W thick)
    "srail_claim": 1.300,    # what the port claims, in W
    "srail_free":  1.500,    # where the other half may start, in W

    # --- optional riveted sub-base, for featureless bulkhead (LOG, MTA)
    "base_hw":    0.650,
    "base_hh":    0.550,
    "base_t":     0.018,
    "rivet_r":    0.038,
    "rivet_in":   0.090,     # inset from the sub-base edge

    # --- the iris gesture.  Rotate each leaf about its own OUTER CORNER and
    #     shrink it toward that corner; at these values the leaf tucks inside
    #     the frame ring (max radius 0.565 W against r_out 0.577 W) and its tip
    #     stops just inside the throat mouth, where the throat light catches it.
    # SOLVED, not chosen.  The leaf's far corner is a full hexagon side from
    # its pivot, so after scaling by s about that pivot the leaf reaches
    # r_leaf * (1 + s) from the port centre.  Anything past r_out pokes THROUGH
    # the frame and shows as six dark spikes around the rim -- which the first
    # build did.  s <= (r_out - r_leaf) / r_leaf = 0.367 keeps every leaf inside
    # the ring, and the leaves' inner tips still reach into the lit aperture,
    # which is where the throat light catches them.
    "open_deg":  -60.0,
    "open_scale": 0.36,
}

MATS = {
    #  name         base rgb                 metal rough  emission            str
    "brass":     ((0.400, 0.320, 0.160), 0.85, 0.44, None, 0.0),
    "brass_dk":  ((0.250, 0.198, 0.098), 0.85, 0.54, None, 0.0),
    # Gunmetal, not bright steel.  The CLOSED state is the port's identity and
    # it is read as a dark six-pointed star inside a brass hexagon; pale leaves
    # against a dark throat invert that and the star disappears.  Measured on
    # KVS at 65 x 44 px: base 0.215 renders as pale grey glass and the seams
    # vanish, 0.105 reads.
    "steel":     ((0.105, 0.112, 0.126), 0.88, 0.34, None, 0.0),
    # The bore is EMISSIVE TOO, at a fraction of the floor.  three.js emissive
    # illuminates nothing, so a lit floor in a dark well renders as a white
    # hole punched in the port -- which is precisely the failure the sketches
    # found (FIX_UPLOAD 1.4: "a hexagon that lost its star").  Lighting the
    # wall is the cheap fake that makes it read as a lit recess.  The frontend
    # drives both from one factor so they can never disagree.
    "throat":    ((0.070, 0.072, 0.078), 0.00, 0.62, (0.62, 0.70, 0.85), 0.0),
    # The open state FAILS if the throat is not genuinely lit -- the sketches
    # read it as "a hexagon that lost its star", a hole rather than an
    # invitation (FIX_UPLOAD 1.4).  This face is emissive, cold white, and the
    # frontend drives its intensity.
    "glow":      ((0.300, 0.330, 0.380), 0.00, 0.34, (0.78, 0.84, 0.95), 1.60),
    # WHITE FAMILY ONLY.  All colour and every health semantic belongs to the
    # telltale mast; see FIX_UPLOAD section 4 and STATUS_AT_A_GLANCE 11.2.
    "jewel":     ((0.155, 0.168, 0.190), 0.00, 0.14, (0.90, 0.93, 1.00), 0.0),
    "ink":       ((0.055, 0.050, 0.052), 0.00, 0.62, None, 0.0),
}


# ===========================================================================
# PURE STDLIB -- vectors, the camera, and the anchor solver.  No bpy below
# this line until the BLENDER section.
# ===========================================================================
def _sub(a, b): return [a[i] - b[i] for i in range(3)]
def _add(a, b): return [a[i] + b[i] for i in range(3)]
def _mul(a, s): return [a[i] * s for i in range(3)]
def _dot(a, b): return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    ln = math.sqrt(_dot(a, a))
    return [x / ln for x in a]


def to_blender(v):
    """three.js / glTF Y-up -> Blender Z-up.  Inverse of transliterate.to3()."""
    return [v[0], -v[2], v[1]]


def to_three(v):
    """Blender Z-up -> three.js / glTF Y-up.  Same map transliterate.to3() uses."""
    return [v[0], v[2], -v[1]]


class Camera:
    """The shipped close camera, rebuilt from `scene.json`, in three.js world.

    Round-trips the exporter's own `text_plane.corners_px` to ~2e-4 px on KVS,
    which is the same figure `occlusion.js:cornersPx()` reports from the live
    page.  If that number is ever large, the camera, the plane or the
    Z-up -> Y-up map is wrong -- not this class.
    """

    def __init__(self, S):
        c = S["camera"]
        self.W, self.H = S["render"]["w"], S["render"]["h"]
        self.pos = list(c["pos"])
        fwd = _norm(c["forward"])
        up = _norm(c["up"])
        self.zc = _mul(fwd, -1.0)
        self.xc = _norm(_cross(up, self.zc))
        self.yc = _cross(self.zc, self.xc)
        self.tan_y = math.tan(math.radians(c["fov_y_deg"]) / 2.0)
        self.asp = self.W / float(self.H)

    def project(self, P):
        """world -> (px, py, linear view depth in metres)"""
        d = _sub(P, self.pos)
        x, y, z = _dot(d, self.xc), _dot(d, self.yc), _dot(d, self.zc)
        D = -z
        return (((x / D) / (self.tan_y * self.asp) * 0.5 + 0.5) * self.W,
                (0.5 - (y / D) / self.tan_y * 0.5) * self.H, D)

    def ray(self, px, py):
        """unit direction through a pixel centre, in world space"""
        nx = px / self.W * 2.0 - 1.0
        ny = 1.0 - py / self.H * 2.0
        return _norm(_add(_mul(self.xc, nx * self.tan_y * self.asp),
                          _add(_mul(self.yc, ny * self.tan_y),
                               _mul(self.zc, -1.0))))

    def unproject(self, px, py, D):
        nx = px / self.W * 2.0 - 1.0
        ny = 1.0 - py / self.H * 2.0
        return _add(self.pos,
                    _add(_mul(self.xc, nx * self.tan_y * self.asp * D),
                         _add(_mul(self.yc, ny * self.tan_y * D),
                              _mul(self.zc, -D))))

    def hit_plane(self, px, py, o, n):
        d = self.ray(px, py)
        den = _dot(d, n)
        t = _dot(_sub(o, self.pos), n) / den
        return _add(self.pos, _mul(d, t))


class PortFrame:
    """origin + orthonormal (u, v, n) -- the port's own authoring space.

    `u` runs across the port, `v` up the carrier, `n` out of it toward the
    camera.  Everything `build()` does is expressed in this frame and mapped
    once, here, so the port is coordinate-system agnostic and the same call
    works in Blender Z-up or three.js Y-up.
    """

    def __init__(self, origin, u, v, n):
        self.o, self.u, self.v, self.n = (list(origin), _norm(u),
                                          _norm(v), _norm(n))

    def to_world(self, x, y, z):
        return [self.o[i] + self.u[i] * x + self.v[i] * y + self.n[i] * z
                for i in range(3)]

    def blender(self):
        return PortFrame(to_blender(self.o), to_blender(self.u),
                         to_blender(self.v), to_blender(self.n))

    def json(self):
        return {"origin": [round(x, 9) for x in self.o],
                "u": [round(x, 9) for x in self.u],
                "v": [round(x, 9) for x in self.v],
                "n": [round(x, 9) for x in self.n]}


def hex_corners(R, spin_deg=0.0):
    """Six corners of a regular hexagon of circumradius R, in the port plane.

    `spin_deg` 0 puts a vertex at +u, so the FLATS are top and bottom -- the
    flat-topped frame FIX_UPLOAD 1.1 draws.  30 puts a vertex at +v (point-up),
    which is what an obliquely-viewed carrier wants: the foreshortening squashes
    the screen-vertical axis, and a point-up hexagon is 1.155 W tall before it
    is squashed where a flat-topped one is 1.0 W.
    """
    a0 = math.radians(spin_deg)
    return [(R * math.cos(a0 + k * math.pi / 3.0),
             R * math.sin(a0 + k * math.pi / 3.0)) for k in range(6)]


def load_module(code):
    A = os.path.join(LIVE3D, "assets", code)
    S = json.load(open(os.path.join(A, "scene.json")))
    return A, S


def read_depth(A, S):
    W, H = S["render"]["w"], S["render"]["h"]
    raw = open(os.path.join(A, S["depth"]["file"]), "rb").read()
    return struct.unpack("<%df" % (W * H), raw[:W * H * 4]), W, H


def fit_carrier_plane(cam, dep, W, H, x0, x1, y0, y1, far=1e9):
    """Least-squares plane through the baked depth over a pixel window.

    Returns (centroid, unit normal facing the camera, sorted |residuals|).
    This is how the carrier's OWN normal is measured rather than assumed; see
    note 3 in the module docstring.
    """
    pts = []
    for yy in range(max(0, y0), min(H, y1 + 1)):
        row = yy * W
        for xx in range(max(0, x0), min(W, x1 + 1)):
            d = dep[row + xx]
            if d < far:
                pts.append(cam.unproject(xx + 0.5, yy + 0.5, d))
    if len(pts) < 16:
        raise ValueError("carrier window has %d usable depth samples; the "
                         "anchor is off the module's silhouette" % len(pts))
    c = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
    C = [[0.0] * 3 for _ in range(3)]
    for p in pts:
        q = _sub(p, c)
        for i in range(3):
            for j in range(3):
                C[i][j] += q[i] * q[j]
    tr = C[0][0] + C[1][1] + C[2][2]
    # smallest eigenvector of C == largest of (trace*I - C); power-iterate that
    M = [[(tr if i == j else 0.0) - C[i][j] for j in range(3)] for i in range(3)]
    b = [0.3, 0.5, 0.81]
    for _ in range(400):
        b = _norm([sum(M[i][j] * b[j] for j in range(3)) for i in range(3)])
    if _dot(b, _sub(cam.pos, c)) < 0:
        b = _mul(b, -1.0)
    res = sorted(abs(_dot(_sub(p, c), b)) for p in pts)
    return c, b, res


# ===========================================================================
# IS `ubias_m` A GAP, OR JUST A NUMBER?  -- the stand-off floor
# ===========================================================================
# `seat_margin` and `lift_margin` are expressed in MULTIPLES OF `ubias_m`, and
# that is only a stand-off where `ubias_m` is itself a stand-off.  It usually
# is: `ubias.py` derives it as 0.70 x the ERODED MINIMUM live-to-baked gap, so
# a multiple of it is a multiple of a measured clearance.  It is not always.
#
# FMM ships `ubias_m` = **1e-06** -- that module's own `__occ.ubias` SWEEP
# OPTIMUM, not a measured gap, because FMM is `ubias.py`'s EMERGING case where
# the recipe degenerates.  At the shared default of 2.5 the port would have been
# seated 0.059 mm off the fascia OF WHICH 2.5 MICRONS IS MARGIN, and the mast
# would have answered `lift 0.0`.  Every printed ratio would have said "2.5x"
# and looked healthy, because the ratio is dimensionless and hides the size.
#
# Two independent measurements say 2.5 microns is not enough there, and only one
# of them is available to a pure-stdlib solver:
#
#   * THE RASTERISER.  The depth composite compares the live fragment's depth
#     against `depth.bin` at the pixel it lands on.  Half a pixel of
#     disagreement between the rasteriser that WROTE `depth.bin` and the one
#     drawing the fitting therefore costs half a pixel of the carrier's own
#     depth GRADIENT.  On FMM's fascia that gradient is 0.104 mm PER SCREEN
#     PIXEL, so a 2.5 micron margin is 1/40 of one pixel and bands of the
#     fitting are deleted silently.  Trap 24.  This is measurable from
#     `depth.bin` alone and is what the floor below tests.
#   * TRAP 24's OTHER HALF.  `live_depth.py` globs every `.glb`, so a fitting
#     seated below the module's ERODED MINIMUM becomes the new minimum of the
#     set `ubias_m` is re-derived from -- KVS's flush rail moved it from
#     0.000565 to 0.000034.  That number needs numpy and Blender's python and
#     is NOT available here; the refusal below says so and names the file.
#
# THE FLOOR: the margin must be worth at least half a pixel of the carrier's
# own depth gradient.  Measured across the fleet at the shipped settings --
# KVS port 2.2 px, MQB port (an exact plane, no gradient to lose), MTA port
# 4.6 px, MTA mast 4.7 px, OTA port 31 px, OTA mast 2.4 px, FMM port and mast
# 11.6 px at the 1200 it shipped -- against 0.02 px for FMM at the default.
# The tightest shipping module is 4.5x above the floor and the failing case is
# 20x below it, which is what makes 0.5 px a threshold and not a coin toss.


class ThinMargin(ValueError):
    """The stand-off is a multiple of a `ubias_m` that is not a gap.

    Carries the solved dict on `.anchor` (or `.mast`), so a REPORT -- a
    `--sweep-y` band, a `--sweep-px` table -- can still print the row it was
    going to print and flag it, while a BUILD refuses.
    """

    def __init__(self, msg, solved=None):
        ValueError.__init__(self, msg)
        self.anchor = solved
        self.mast = solved


MARGIN_FLOOR_PX = 0.5


def carrier_gradient(dep, W, H, x0, x1, y0, y1, far=1e9):
    """How fast the baked depth moves, in metres per SCREEN PIXEL.

    The p50 of |depth[x+1] - depth[x]| and |depth[y+1] - depth[y]| over the
    window.  The median rather than the max, because one depth STEP inside the
    window (a frame rail, a moulding) is not what a fitting sitting on the flat
    has to clear -- and rather than the mean, because a step would drag that
    too.  Returns (p50, p95, max, n); all zero on a window that is an exact
    plane, which is a real answer (MQB's apron) and not a failure.
    """
    gs = []
    x0 = max(0, int(x0)); x1 = min(W - 1, int(x1))
    y0 = max(0, int(y0)); y1 = min(H - 1, int(y1))
    for y in range(y0, y1):
        row = y * W
        nxt = (y + 1) * W
        for x in range(x0, x1):
            c = dep[row + x]
            if c >= far:
                continue
            a = dep[row + x + 1]
            if a < far:
                gs.append(abs(a - c))
            b = dep[nxt + x]
            if b < far:
                gs.append(abs(b - c))
    if not gs:
        return 0.0, 0.0, 0.0, 0
    gs.sort()
    return (gs[len(gs) // 2], gs[min(len(gs) - 1, int(len(gs) * 0.95))],
            gs[-1], len(gs))


def margin_report(dep, W, H, window, ub, margin, floor_px=MARGIN_FLOOR_PX):
    """Everything the floor test needs, as numbers, whether or not it fires."""
    g50, g95, gmax, n = carrier_gradient(dep, W, H, *window)
    margin_m = margin * ub
    px = (margin_m / g50) if g50 > 0 else float("inf")
    need = (floor_px * g50 / ub) if (g50 > 0 and ub > 0) else 0.0
    return {"grad_m_per_px": g50, "grad_p95_m_per_px": g95,
            "grad_max_m_per_px": gmax, "grad_n": n,
            "margin_m": margin_m, "margin_px": px,
            "floor_px": floor_px, "margin_for_floor": need,
            "thin": px < floor_px}


def margin_message(code, what, flag, ub, margin, rep):
    return (
        "%s: %s = %g x ubias_m = %g m is a %.7f m stand-off, and the baked "
        "carrier under this window moves %.7f m PER SCREEN PIXEL -- so the "
        "margin is worth %.3f of one pixel of depth gradient, against a floor "
        "of %.2f.\n"
        "  `ubias_m` is only a stand-off where it is a measured GAP.  Where it "
        "is a module's own occlusion SWEEP OPTIMUM (FMM ships 1e-06) a "
        "multiple of it is not a clearance, and every printed ratio still says "
        "'%gx' and looks healthy because the ratio is dimensionless.\n"
        "  Read pipeline/live_depth.py's DISTRIBUTION for this module -- the "
        "raw AND the eroded minimum -- and seat the fitting against that.  "
        "%s %.0f (%.7f m) is the smallest that clears the half-pixel floor "
        "here; a fitting must ALSO stand clear of the eroded minimum or it "
        "becomes the new minimum `ubias_m` is re-derived from (trap 24, and it "
        "fired on KVS).  Pass %s, or seat_margin=/lift_margin= from the "
        "exporter."
        % (code, what, margin, ub, rep["margin_m"], rep["grad_m_per_px"],
           rep["margin_px"], rep["floor_px"], margin,
           flag, math.ceil(rep["margin_for_floor"]), rep["margin_for_floor"] * ub,
           flag))


def _seat_samples(W_m, spin, sub_base=False, service_rail=True, geo=None):
    """(a, b, z) over the WHOLE ASSEMBLY, height included -- not just the foot.

    THE PORT IS 0.158 W TALL AND IT USED TO BE SEATED AS IF IT WERE FLAT.
    `_solve_seat()` projected the base hexagon's corners, its half-radius
    points, the centre and the rail's footprint -- ALL AT z = 0 -- and took the
    worst `D - baked`.  On an oblique carrier the frame FACE, which stands
    0.158 W proud, projects well UP-SCREEN of the foot: on PKT the difference
    is 11 px.  So a port whose foot is on clean carrier and whose face
    overhangs something nearer was accepted with a healthy-looking seat, and
    the overhanging part was silently deleted by the depth composite -- trap 24
    arriving on the axis nothing was looking at.  Constructed on PKT:

        refit_port.py PKT 339 690 56 --window 309,369,674,710

    solved at a seat of 5.31 mm with its frame face 1.5 mm BEHIND the baked
    lip at (356, 664).  PKT NOTES 14 item 1.

    This is `envelope_px()`'s point set with the foot's own denser sampling
    kept: corners, half-radius points and the centre at each of the three
    heights the silhouette reaches, plus the rail and the optional sub-base.
    Heights are RELATIVE TO THE CARRIER at seat = 0, because the seat lifts the
    whole assembly rigidly along n -- exactly the approximation the foot-only
    version already made for the foot.

    Adding samples can only RAISE the worst `D - baked`, never lower it, so a
    port whose foot is the closest thing to the plate -- which is every one of
    the seven shipped fittings -- keeps the seat it had.
    """
    G = dict(GEO)
    if geo:
        G.update(geo)
    R = W_m / math.sqrt(3.0)
    flat = []
    for (a, bq) in hex_corners(R, spin):
        flat += [(a, bq), (a * 0.5, bq * 0.5)]
    flat.append((0.0, 0.0))
    out = []
    for z in (0.0, G["z_face"] * W_m, (G["z_face"] + G["tally_h"]) * W_m):
        for (a, bq) in flat:
            out.append((a, bq, z))
    if service_rail:
        rl, rv = G["srail_half"] * W_m, G["srail_v"] * W_m
        for z in (0.0, G["z_rail"] * W_m):
            for t in (-1.0, -0.5, 0.0, 0.5, 1.0):
                out += [(rl * t, rv, z), (rl * t, -rv, z)]
    if sub_base:
        bw, bh = G["base_hw"] * W_m, G["base_hh"] * W_m
        for z in (0.0, G["base_t"] * W_m):
            for (a, bq) in ((-bw, -bh), (bw, -bh), (bw, bh), (-bw, bh),
                            (0.0, -bh), (0.0, bh), (-bw, 0.0), (bw, 0.0)):
                out.append((a, bq, z))
    return out


def _solve_seat(cam, frame, dep, W, H, W_m, spin, ub, margin,
                sub_base=False, service_rail=True, geo=None):
    """How far above the carrier the port must sit to clear the baked plate.

    Trap 24 applied to a carrier that is a FIT rather than a plane: a live
    surface standing less proud than `ubias_m` is discarded silently.  Sampled
    over the WHOLE ASSEMBLY -- foot, frame face, tally height, service rail and
    the optional sub-base -- because the face is what overhangs.  See
    `_seat_samples()`.
    """
    worst = 0.0
    for (a, bq, z) in _seat_samples(W_m, spin, sub_base=sub_base,
                                    service_rail=service_rail, geo=geo):
        ppx, ppy, D = cam.project(frame.to_world(a, bq, z))
        if not (0 <= ppx < W and 0 <= ppy < H):
            continue
        baked = dep[int(ppy) * W + int(ppx)]
        if baked >= 1e9:
            continue
        worst = max(worst, D - baked)      # >0 = the port is BEHIND the plate
    return worst + margin * ub


class Overhang(ValueError):
    """The seated assembly is behind the baked plate somewhere.

    Carries the solved dict on `.anchor`, so a REPORT -- a `--sweep-y` band --
    can still print the row it was going to print and flag it, exactly as
    `ThinMargin` does.
    """

    def __init__(self, msg, solved=None):
        ValueError.__init__(self, msg)
        self.anchor = solved


def verify_seat(cam, frame, dep, W, H, W_m, spin,
                sub_base=False, service_rail=True, geo=None):
    """AT THE SOLVED SEAT: the closest the assembly comes to the baked plate.

    Returns (metres, (px, py, z_mm)).  Positive is IN FRONT of the plate and
    therefore drawn; the depth composite is `if (vLinDepth > baked - uBias)
    discard`, so anything at or below `ubias_m` here is deleted SILENTLY.

    WHY THIS IS A SEPARATE PASS AND NOT A BETTER `_solve_seat()`.  The seat is
    a FIRST-ORDER step -- `worst(D - baked) at seat 0` plus the margin -- and
    two things it ignores make it approximate rather than wrong: the lift is
    along `n`, so it buys only `cos(obliquity)` of depth, and every sample's
    PIXEL MOVES up-screen as the assembly rises, onto baked depth that may be
    nothing like the depth under the foot.  Re-solving to a fixed point is what
    `status_mast._solve_lift()`'s docstring warns about (it converged to
    19.6 mm on KVS against a true requirement of 4.6) AND it would move all
    seven shipped seats, every one of which is a published number.
    So the seat is left exactly as it was and the RESULT is checked.

    On PKT's constructed case -- `PKT 339 690 56 --window 309,369,674,710` --
    the foot lands on the brass lip and the first-order seat of 5.31 mm looks
    healthy, while the frame face, 0.158 W proud and 11 px up-screen, ends up
    BEHIND the lip's crown and is deleted.  Nothing said so.  PKT NOTES 14
    item 1.
    """
    worst, where = 1e9, None
    for (a, bq, z) in _seat_samples(W_m, spin, sub_base=sub_base,
                                    service_rail=service_rail, geo=geo):
        ppx, ppy, D = cam.project(frame.to_world(a, bq, z))
        if not (0 <= ppx < W and 0 <= ppy < H):
            continue
        baked = dep[int(ppy) * W + int(ppx)]
        if baked >= 1e9:
            continue
        if baked - D < worst:
            worst, where = baked - D, (round(ppx, 1), round(ppy, 1),
                                       round(z * 1000, 2))
    if where is None:
        return None, None
    return worst, where


def overhang_message(code, ub, clear, where, seat, margin_m):
    return (
        "%s: the port is SEATED at %.4f m and the closest point of the whole "
        "assembly still comes within %.7f m of the baked plate, at pixel "
        "(%.1f, %.1f) %0.2f mm above the carrier -- against `ubias_m` = "
        "%.7f m.  The depth composite is `if (vLinDepth > baked - uBias) "
        "discard`, so that part of the fitting is DELETED, silently.\n"
        "  The seat solve samples the assembly at the carrier and lifts it "
        "along n; it does not know that a sample's PIXEL MOVES up-screen as "
        "the fitting rises.  The frame FACE stands 0.158 W proud and on an "
        "oblique carrier that is about 11 px of travel -- enough to leave "
        "clean carrier and arrive on something nearer.  The foot being on "
        "clean carrier is NOT the question; what the port OVERHANGS is.  "
        "PKT NOTES 14 item 1 and 2.\n"
        "  The seat's own margin here is %.7f m.  Move the anchor off "
        "whatever is above it, drop port_px, or pin a spin_deg whose face "
        "does not reach it -- `--sweep-y` walks the column and shows the band."
        % (code, seat, clear, where[0], where[1], where[2], ub, margin_m))


def _bbox_px(cam, frame, R, spin, z=0.0):
    """Screen bbox of the frame hexagon, at height `z` above the carrier."""
    xs, ys = [], []
    for (a, bb) in hex_corners(R, spin):
        px, py, _ = cam.project(frame.to_world(a, bb, z))
        xs.append(px)
        ys.append(py)
    return min(xs), max(xs), min(ys), max(ys)


def envelope_px(cam, frame, W_m, spin, seat, sub_base=False,
                service_rail=True, geo=None):
    """Screen bbox of the WHOLE ASSEMBLY, height included.

    NOT the same rectangle as `_bbox_px`, and the difference is not small.  The
    frame face stands 0.158 W proud and the service rail runs to 0.65 W across,
    so on an oblique carrier the drawn silhouette reaches well outside the base
    hexagon: measured on KVS, the base-hexagon rect was 331..396 x 671..715
    while the port actually paints 325..400 x 660..707 -- 10 px short at the
    top and 6 px short on the left.  A hotspot built from the base hexagon does
    not cover the thing the player is pointing at, and a keep-out check built
    from it is measuring the wrong rectangle.
    """
    G = dict(GEO)
    if geo:
        G.update(geo)
    s = W_m
    zf = seat + G["z_face"] * s
    pts = []
    for z in (seat, zf, seat + (G["z_face"] + G["tally_h"]) * s):
        for (a, bb) in hex_corners(G["r_out"] * s, spin):
            pts.append((a, bb, z))
    if service_rail:
        rh, rv = G["srail_half"] * s, G["srail_v"] * s
        for z in (0.0, seat + G["z_rail"] * s):
            for (a, bb) in ((-rh, -rv), (rh, -rv), (rh, rv), (-rh, rv)):
                pts.append((a, bb, z))
    if sub_base:
        bw, bh = G["base_hw"] * s, G["base_hh"] * s
        for z in (0.0, seat):
            for (a, bb) in ((-bw, -bh), (bw, -bh), (bw, bh), (-bw, bh)):
                pts.append((a, bb, z))
    xs, ys = [], []
    for (a, bb, z) in pts:
        px, py, _ = cam.project(frame.to_world(a, bb, z))
        xs.append(px)
        ys.append(py)
    return min(xs), max(xs), min(ys), max(ys)


def solve_anchor(code, px, py, port_px, spin_deg=None, carrier_window=None,
                 normal="carrier", seat_margin=2.5, seat_cap=0.12,
                 sub_base=False, service_rail=True, verbose=True):
    """Turn a target PIXEL into everything `build()` and `export()` need.

    This is FIX_UPLOAD section 3.5 done as code instead of as prose, and it is
    the part every one of the nine modules needs identically.

    px, py       target centre, in the module's own 1280x720 close frame
    port_px      the design's screen size across flats for this module
    spin_deg     in-plane rotation; None picks the one whose projected bbox is
                 closest to square, which is what an oblique carrier needs
    normal       "carrier" (measured from depth.bin, the honest one) or
                 "face" (the module's declared text_plane normal)
    seat_margin  how many multiples of `ubias_m` the closest point of the port
                 must clear the baked carrier by

    Returns a dict; `frame` is in three.js world, `frame_blender` is the same
    frame mapped for authoring.  Prints its own evidence when `verbose`.
    """
    A, S = load_module(code)
    cam = Camera(S)
    dep, W, H = read_depth(A, S)
    ub = float(S.get("ubias_m") or 0.0005)

    if carrier_window is None:
        h = port_px / 2.0
        carrier_window = (int(px - h), int(px + h), int(py - h), int(py + h))
    x0, x1, y0, y1 = carrier_window
    c, n_carrier, res = fit_carrier_plane(cam, dep, W, H, x0, x1, y0, y1)

    tp = (S.get("text_planes") or [S.get("text_plane")])[0]
    n_face = _norm(tp["n"]) if tp else n_carrier
    n = n_carrier if normal == "carrier" else n_face

    # v runs up the carrier: the in-plane direction closest to world up as the
    # camera sees it, so "below the instrument" means below on screen too.
    up_ref = cam.yc
    v = _norm(_sub(up_ref, _mul(n, _dot(up_ref, n))))
    u = _norm(_cross(v, n))
    origin = cam.hit_plane(px, py, c, n)
    frame = PortFrame(origin, u, v, n)

    # --- size: hold the SCREEN size, derive the physical one (FIX_UPLOAD 2).
    # The reference envelope is what a 56 px flat-topped hexagon occupies when
    # it is not foreshortened: 1.1547 x 1.000 port_px.  Scale so the projected
    # bbox touches that envelope in its dominant axis and never exceeds it.
    env_w, env_h = port_px * 2.0 / math.sqrt(3.0), float(port_px)
    spins = ([spin_deg] if spin_deg is not None
             else [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    best = None
    for sp in spins:
        # ITERATE.  Projection is not linear in size, and a first guess solved
        # against a 1 m hexagon 1 m from the lens is nonsense -- it subtends
        # most of the frame and the scale factor it implies is wrong by tens of
        # per cent.  Four passes converge to under 0.01 px on every module.
        Wm = env_w / 1500.0
        for _ in range(12):
            zf = GEO["z_face"] * Wm            # the face, not the base
            bx0, bx1, by0, by1 = _bbox_px(cam, frame, Wm / math.sqrt(3.0),
                                          sp, zf)
            k = min(env_w / (bx1 - bx0), env_h / (by1 - by0))
            Wm *= k
            if abs(k - 1.0) < 1e-9:
                break
        bx0, bx1, by0, by1 = _bbox_px(cam, frame, Wm / math.sqrt(3.0), sp,
                                      GEO["z_face"] * Wm)
        bw, bh = bx1 - bx0, by1 - by0
        squareness = min(bw / env_w, bh / env_h)
        st = _solve_seat(cam, frame, dep, W, H, Wm, sp, ub, seat_margin,
                         sub_base=sub_base,
                         service_rail=service_rail)
        # An auto spin may not push the port off the frame -- a cropped port is
        # not a port -- and it may not buy apparent size with stand-off.  A big
        # spin reads rounder but reaches further up an uneven carrier, and the
        # seat that has to clear it is a visible float: on KVS, spin 30 is 5 px
        # taller than spin 15 and costs 2.4 mm (4.4 px) more stand-off.  Cap
        # the seat as a fraction of W and let squareness win under it.  An
        # EXPLICIT spin_deg is honoured as given and reported instead.
        # Test the WHOLE envelope, not the frame hexagon: the port is 0.158 W
        # tall and its rail is 1.3 W across, and on an oblique carrier that is
        # the difference between "fits" and "the tally flag is cropped".
        ex0, ex1, ey0, ey1 = envelope_px(cam, frame, Wm, sp, st,
                                         sub_base=sub_base,
                                         service_rail=service_rail)
        fits = (ex0 >= 0 and ex1 < cam.W and ey0 >= 0 and ey1 < cam.H
                and st <= seat_cap * Wm)
        if spin_deg is None and not fits:
            continue
        if best is None or squareness > best[0]:
            best = (squareness, sp, Wm, bw, bh)
    if best is None:
        # Say WHICH constraint bit.  "off the frame" and "the carrier is too
        # uneven here" want different fixes and the message used to claim the
        # first for both.
        diag = []
        for sp in spins:
            Wm = env_w / 1500.0
            for _ in range(12):
                bx0, bx1, by0, by1 = _bbox_px(cam, frame,
                                              Wm / math.sqrt(3.0), sp,
                                              GEO["z_face"] * Wm)
                k = min(env_w / (bx1 - bx0), env_h / (by1 - by0))
                Wm *= k
            st = _solve_seat(cam, frame, dep, W, H, Wm, sp, ub, seat_margin,
                             sub_base=sub_base,
                             service_rail=service_rail)
            ex0, ex1, ey0, ey1 = envelope_px(cam, frame, Wm, sp, st,
                                             sub_base=sub_base,
                                             service_rail=service_rail)
            off = not (ex0 >= 0 and ex1 < cam.W
                       and ey0 >= 0 and ey1 < cam.H)
            diag.append("spin %.0f: %s%s" % (
                sp, "OFF FRAME " if off else "",
                "seat %.1f mm > cap %.1f mm" % (st * 1000, seat_cap * Wm * 1000)
                if st > seat_cap * Wm else ("ok" if not off else "")))
        raise ValueError(
            "no in-plane rotation works at (%s, %s): %s.  Move the anchor, "
            "drop port_px, raise seat_cap, or pin spin_deg."
            % (px, py, "; ".join(diag)))
    squareness, spin, W_m, bbox_w, bbox_h = best

    # --- seat: lift the assembly along n until its whole footprint clears the
    # baked carrier by seat_margin * ubias_m.  This is trap 24 applied to a
    # curved carrier: the fitted plane is a fit, and the deck deviates from it.
    seat = _solve_seat(cam, frame, dep, W, H, W_m, spin, ub, seat_margin,
                       sub_base=sub_base, service_rail=service_rail)
    frame = PortFrame(frame.to_world(0.0, 0.0, seat), u, v, n)

    # --- IS THE MARGIN A MARGIN?  See THE STAND-OFF FLOOR above.  Solved
    # first, so the exception can carry the whole dict and a REPORT can still
    # print the row it was going to print.
    mrep = margin_report(dep, W, H, carrier_window, ub, seat_margin)

    out = {
        "code": code, "anchor_px": [px, py], "port_px": port_px,
        "frame": frame, "frame_blender": frame.blender(),
        "W_m": W_m, "spin_deg": spin, "seat_m": seat, "ubias_m": ub,
        "bbox_px": [bbox_w, bbox_h],
        "carrier_normal": n_carrier, "face_normal": n_face,
        "normal_used": normal,
        "carrier_resid_p50": res[len(res) // 2],
        "carrier_resid_p95": res[int(len(res) * 0.95)],
        "carrier_resid_max": res[-1],
        "obliq_carrier": math.degrees(math.acos(
            max(-1.0, min(1.0, _dot(n_carrier, _mul(cam.zc, 1.0)))))),
        "obliq_face": math.degrees(math.acos(
            max(-1.0, min(1.0, _dot(n_face, _mul(cam.zc, 1.0)))))),
        "normal_split_deg": math.degrees(math.acos(
            max(-1.0, min(1.0, _dot(n_carrier, n_face))))),
    }
    out.update(clearance_report(code, S, cam, frame, W_m, spin, dep, W, H,
                                sub_base=sub_base, service_rail=service_rail))
    out["margin"] = mrep

    # --- AND IS IT ACTUALLY CLEAR?  The seat above is a first-order step over
    # the assembly's own hull; `verify_seat()` asks the seated fitting whether
    # any part of it is still inside the depth composite's discard band.  This
    # measures the RESULT and changes no shipped seat: all seven come out at
    # 1.12 .. 3.66 mm of clearance, 0.98 .. 1.15 x their own intended margin.
    a_clear, a_where = verify_seat(cam, frame, dep, W, H, W_m, spin,
                                   sub_base=sub_base,
                                   service_rail=service_rail)
    out["assembly_clear_m"] = a_clear
    out["assembly_clear_at"] = a_where
    out["assembly_clear_over_margin"] = (
        None if a_clear is None or not mrep["margin_m"]
        else a_clear / mrep["margin_m"])
    if mrep["thin"]:
        raise ThinMargin(margin_message(code, "seat_margin", "--seat-margin",
                                        ub, seat_margin, mrep), out)
    if a_clear is not None and a_clear < ub:
        raise Overhang(overhang_message(code, ub, a_clear, a_where, seat,
                                        mrep["margin_m"]), out)
    if verbose:
        print_anchor(out)
    return out


def clearance_report(code, S, cam, frame, W_m, spin, dep, W, H,
                     seat=0.0, sub_base=False, service_rail=True):
    """0 % overlap with any control hotspot, 0 % with any declared readout
    rect, 100 % solid carrier -- FIX_UPLOAD section 3.2's three claims, proved
    for THIS anchor rather than inherited from the table."""
    bx0, bx1, by0, by1 = envelope_px(cam, frame, W_m, spin, seat,
                                     sub_base=sub_base,
                                     service_rail=service_rail)
    hot = [bx0 - 4, bx1 + 4, by0 - 4, by1 + 4]

    def ov(a, b):
        return (max(0.0, min(a[1], b[1]) - max(a[0], b[0])) *
                max(0.0, min(a[3], b[3]) - max(a[2], b[2])))

    def gap(a, b):
        return max(0.0, max(b[0] - a[1], a[0] - b[1], b[2] - a[3], a[2] - b[3]))

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
    clear = [{"what": nm, "overlap_px2": ov(hot, r), "gap_px": gap(hot, r)}
             for nm, r in rects]

    solid = tot = 0
    for yy in range(int(by0), int(by1) + 1):
        for xx in range(int(bx0), int(bx1) + 1):
            if 0 <= xx < W and 0 <= yy < H:
                tot += 1
                if dep[yy * W + xx] < 1e9:
                    solid += 1
    depths = [dep[yy * W + xx]
              for yy in range(int(by0), int(by1) + 1)
              for xx in range(int(bx0), int(bx1) + 1)
              if 0 <= xx < W and 0 <= yy < H and dep[yy * W + xx] < 1e9]
    return {"bbox": [bx0, bx1, by0, by1],
            # clamped: the 4 px pad may run off the frame edge on a module
            # whose carrier reaches it (KVS's deck does).  A hotspot rect is
            # not geometry and a clamped one behaves identically.
            "hotspot": {"x": round(max(0.0, hot[0]), 2),
                        "y": round(max(0.0, hot[2]), 2),
                        "w": round(min(cam.W, hot[1]) - max(0.0, hot[0]), 2),
                        "h": round(min(cam.H, hot[3]) - max(0.0, hot[2]), 2)},
            "clearances": clear,
            "carrier_solid_pct": 100.0 * solid / max(1, tot),
            "carrier_depth_m": [min(depths), max(depths)] if depths else None,
            "off_frame": not (0 <= bx0 and bx1 < W and 0 <= by0 and by1 < H)}


def print_anchor(A):
    print("REFIT PORT anchor -- %s" % A["code"])
    print("  target pixel            (%s, %s)   port_px %s"
          % (A["anchor_px"][0], A["anchor_px"][1], A["port_px"]))
    print("  W (across flats)        %.4f m   spin %.1f deg   seat %.4f m"
          % (A["W_m"], A["spin_deg"], A["seat_m"]))
    print("  projected bbox          %.1f x %.1f px   (envelope %.1f x %.1f)"
          % (A["bbox_px"][0], A["bbox_px"][1],
             A["port_px"] * 2 / math.sqrt(3), A["port_px"]))
    print("  normal used             %s" % A["normal_used"])
    print("  obliquity, carrier      %.2f deg   (declared face %.2f deg, "
          "they differ by %.2f deg)"
          % (A["obliq_carrier"], A["obliq_face"], A["normal_split_deg"]))
    print("  carrier flatness        |resid| p50 %.5f  p95 %.5f  max %.5f m"
          % (A["carrier_resid_p50"], A["carrier_resid_p95"],
             A["carrier_resid_max"]))
    print("  carrier solid behind    %.1f %%   depth %.4f .. %.4f m"
          % (A["carrier_solid_pct"], A["carrier_depth_m"][0],
             A["carrier_depth_m"][1]))
    M = A.get("margin")
    if M:
        # THE RATIO IS NOT THE NUMBER.  "2.5x ubias" reads healthy at 2.5
        # microns; what says whether the seat survives the depth composite is
        # the margin measured in PIXELS OF THE CARRIER'S OWN DEPTH GRADIENT.
        print("  carrier depth gradient  %.7f m/px (p50 over %d samples, "
              "p95 %.7f)" % (M["grad_m_per_px"], M["grad_n"],
                             M["grad_p95_m_per_px"]))
        print("  stand-off margin        %.7f m = %s px of that gradient  "
              "(floor %.2f)%s"
              % (M["margin_m"],
                 "inf" if M["margin_px"] == float("inf")
                 else "%.2f" % M["margin_px"],
                 M["floor_px"], "   <-- !! THIN" if M["thin"] else ""))
    print("  seat clears ubias_m     %.6f m seat vs %.6f m ubias  (%.1fx)"
          % (A["seat_m"], A["ubias_m"], A["seat_m"] / A["ubias_m"]))
    # THE SEAT IS NOT THE CLEARANCE.  The seat is what was ADDED; this is what
    # the SEATED assembly -- foot, frame face, tally height, rail -- actually
    # has, measured at its own worst point.  A port whose foot is on clean
    # carrier can still overhang something nearer with its face.  See
    # `verify_seat()`.
    if A.get("assembly_clear_m") is not None:
        w = A["assembly_clear_at"]
        print("  assembly really clears  %.6f m at (%.1f, %.1f), %.2f mm above "
              "the carrier  (%.2f x the seat's own margin)%s"
              % (A["assembly_clear_m"], w[0], w[1], w[2],
                 A["assembly_clear_over_margin"] or 0.0,
                 "   <-- !! DELETED" if A["assembly_clear_m"] < A["ubias_m"]
                 else ""))
    print("  hotspot                 %s" % (A["hotspot"],))
    print("  off frame               %s" % A["off_frame"])
    for c in A["clearances"]:
        print("    vs %-14s overlap %7.0f px2   gap %6.1f px  %s"
              % (c["what"], c["overlap_px2"], c["gap_px"],
                 "" if c["overlap_px2"] == 0 else "<-- !! TOUCHES"))


# ===========================================================================
# BLENDER -- everything below needs bpy.  Import is deferred so the solver
# above runs under plain python3.
# ===========================================================================
def _bpy():
    import bpy
    return bpy


# ---------------------------------------------------------------------------
# ROOT SCALE -- the silent 1.43x, and why this refuses instead of trusting you
# ---------------------------------------------------------------------------
def check_root_scale(root_scale, who, dim_name="W", dim_m=None):
    """Validate `root_scale` against the scene it is about to be used in.

    THE RULE IS "PASS THE SCALE OF THE ROOT YOU ARE AUTHORING *INSIDE*", and
    the trap is that on the entry point everybody actually uses, you are inside
    NOTHING.  `export_<code>.py -- refit` and `-- mast` both CLEAR THE SCENE
    and build the fitting alone, in WORLD coordinates, from the solver's own
    world-space frame.  There is no module root in the file, so `root_scale`
    must stay 1.0 there -- even though the same module's `main()` authors
    everything inside `mod.SCALE = 0.70` and FIX_UPLOAD 12.14 item 4 lists MQB
    at 0.70 for that reason.

    Passing 0.70 on the empty-scene path divides every dimension by 0.70 and
    ships the fitting **1.43x too big, with nothing printed and nothing
    failing**.  MQB was told to pass 0.70 and correctly refused; DNSM (0.78)
    and PKT (1.15) are next and would each have had to work it out again.

    So:
      * scene EMPTY and root_scale != 1.0  ->  refuse.  You cannot be inside a
        root that is not in the file.  This is exactly the failing path.
      * scene NOT empty and no object at that world scale  ->  print a
        WARNING naming the factor, and go on.  A `main()` may legitimately
        build parts before it parents them to a root.
      * a match  ->  say which object, so the number is CONFIRMED and not
        merely accepted.

    Returns the validated float.  `dim_m` is the world dimension being scaled,
    printed so the consequence is on screen either way.
    """
    try:
        rs = float(root_scale)
    except (TypeError, ValueError):
        raise SystemExit("%s: root_scale must be a number, got %r"
                         % (who, root_scale))
    if not (rs > 0.0):
        raise SystemExit("%s: root_scale must be > 0, got %r" % (who, rs))

    def _say(extra):
        if dim_m is None:
            print("  %s: root_scale %.4f -- %s" % (who, rs, extra))
        else:
            print("  %s: root_scale %.4f -> authoring-space %s = %.6f m for a "
                  "WORLD %s of %.6f m.  %s"
                  % (who, rs, dim_name, dim_m / rs, dim_name, dim_m, extra))

    if abs(rs - 1.0) < 1e-9:
        _say("world coordinates, nothing divided out.")
        return rs

    try:
        bpy = _bpy()
        objs = list(bpy.context.scene.objects)
    except Exception:                      # no bpy: the solver half, nothing
        _say("NOT CHECKED -- no Blender scene to look in.")
        return rs

    if not objs:
        raise SystemExit(
            "%s: root_scale=%s in an EMPTY SCENE.\n"
            "\n"
            "  The rule is 'the scale of the root you are authoring INSIDE'.\n"
            "  This scene has no objects at all, so there is no root to be\n"
            "  inside and every dimension would be divided by %s -- the\n"
            "  fitting would ship %.3fx its intended world size, silently.\n"
            "\n"
            "  The `refit` / `mast` entry points CLEAR THE SCENE and build in\n"
            "  WORLD coordinates from the solver's own world-space frame.  On\n"
            "  that path root_scale is 1.0, whatever `main()` uses.  MQB is\n"
            "  0.70 in main() and 1.0 here; DNSM 0.78 and PKT 1.15 are the\n"
            "  same.  Pass root_scale=1.0 (or leave it out).\n"
            "\n"
            "  If you really are authoring inside a scaled root, create that\n"
            "  root BEFORE calling this and the check will find it."
            % (who, rs, rs, 1.0 / rs))

    hits = []
    for ob in objs:
        try:
            sc = ob.matrix_world.to_scale()
        except Exception:
            continue
        if max(abs(c - rs) for c in sc) < 1e-4:
            hits.append(ob.name)
    if hits:
        _say("authoring inside %r." % hits[0])
    else:
        print("  %s: *** WARNING *** root_scale %.4f, but NO object in this "
              "scene has that world scale (%d object(s) checked).  If you are "
              "not authoring inside a %.4f root, every dimension is about to "
              "be divided by %.4f and the fitting will be %.3fx too big.  See "
              "check_root_scale() in refit_port.py."
              % (who, rs, len(objs), rs, rs, 1.0 / rs))
        _say("proceeding on your word.")
    return rs



def _material(name, spec):
    """A Principled material with SCALAR inputs only.

    Deliberately not node-driven: `transliterate.materials_json()` exists
    because Blender's glTF exporter drops roughnessFactor/metallicFactor
    whenever the Principled input is a node (CONVERSION_BRIEF trap 2, worth
    8.212 vs 4.832 rms on KVS).  Keeping these scalar means the port's
    materials survive the round trip on their own and NOTHING has to be added
    to any module's shipped `materials.json` -- which is a shipped asset this
    component must not touch.
    """
    bpy = _bpy()
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    base, metal, rough, em, st = spec
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (base[0], base[1], base[2], 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if em is not None:
        b.inputs["Emission Color"].default_value = (em[0], em[1], em[2], 1.0)
        b.inputs["Emission Strength"].default_value = st
    return m


def _mesh(name, verts, faces, mat, smooth=False):
    bpy = _bpy()
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if mat:
        ob.data.materials.append(mat)
    if smooth:
        for p in ob.data.polygons:
            p.use_smooth = True
    return ob


def _shell(name, frame, profile, mat, spin=0.0, sides=6, smooth=False,
           closed=True):
    """Sweep a closed (radius-multiplier, height) profile around a polygon.

    The workhorse: the frame ring, the throat wall and the ratchet are all one
    call each.  `profile` is a CLOSED loop in the (r, z) cross-section; with
    `sides=6` each profile step traces a regular hexagon, so the result is a
    faceted brass fitting rather than a turned one.

    WINDING.  The surface normal of the quad (i,j)(i+1,j)(i+1,j+1)(i,j+1) is
    d/dtheta x d/dt = (dz * radial, -dr).  So a loop that runs UP the outer
    wall, INWARD across the top, DOWN the inner wall and OUTWARD across the
    bottom has outward normals on the outside and inward normals in the bore --
    which is what you want, and which is why this is generated rather than
    typed.  Trap 21: FrontSide deletes anything wound the other way, silently.
    """
    n = len(profile)
    ring = hex_corners(1.0, spin) if sides == 6 else [
        (math.cos(2 * math.pi * k / sides), math.sin(2 * math.pi * k / sides))
        for k in range(sides)]
    vs = []
    for (cx, cy) in ring:
        for (r, z) in profile:
            vs.append(frame.to_world(cx * r, cy * r, z))
    fs = []
    m = n if closed else n - 1
    for i in range(sides):
        a, b = i * n, ((i + 1) % sides) * n
        for j in range(m):
            k = (j + 1) % n
            fs.append((a + j, b + j, b + k, a + k))
    return _mesh(name, vs, fs, mat, smooth)


def _cap(name, frame, R, z, mat, spin=0.0, sides=6, up=True):
    """A polygonal disc facing +n (or -n).  Triangle fan, so `sides` tris."""
    ring = hex_corners(R, spin) if sides == 6 else [
        (R * math.cos(2 * math.pi * k / sides), R * math.sin(2 * math.pi * k / sides))
        for k in range(sides)]
    vs = [frame.to_world(0.0, 0.0, z)] + [frame.to_world(a, b, z) for a, b in ring]
    fs = [(0, 1 + i, 1 + (i + 1) % sides) if up
          else (0, 1 + (i + 1) % sides, 1 + i) for i in range(sides)]
    return _mesh(name, vs, fs, mat)


def _prism(name, frame, poly, z0, z1, mat):
    """A closed solid from a CCW polygon in the port plane, extruded along +n.

    Closed, so `THREE.FrontSide` cannot delete it.  Every leaf, rail, rivet
    plate and tally flag in this file is one of these, for exactly that reason
    (trap 21: a single-triangle pip is the shape that trap names).
    """
    k = len(poly)
    vs = ([frame.to_world(a, b, z0) for a, b in poly] +
          [frame.to_world(a, b, z1) for a, b in poly])
    fs = [tuple(range(k - 1, -1, -1)), tuple(range(k, 2 * k))]
    for i in range(k):
        j = (i + 1) % k
        fs.append((i, j, k + j, k + i))
    return _mesh(name, vs, fs, mat)


def _prism_bevel(name, frame, poly, z0, z1, inset, mat):
    """A prism whose top face is inset toward the polygon's centroid.

    The chamfer is not decoration: it puts a lit edge on both sides of every
    iris seam, which is what makes a 2 px slot read at 44 px.  Same triangle
    count as a plain prism.
    """
    k = len(poly)
    cx = sum(p[0] for p in poly) / k
    cy = sum(p[1] for p in poly) / k
    top = []
    for (a, b) in poly:
        dx, dy = a - cx, b - cy
        ln = math.hypot(dx, dy) or 1.0
        top.append((a - dx / ln * inset, b - dy / ln * inset))
    vs = ([frame.to_world(a, b, z0) for a, b in poly] +
          [frame.to_world(a, b, z1) for a, b in top])
    fs = [tuple(range(k - 1, -1, -1)), tuple(range(k, 2 * k))]
    for i in range(k):
        j = (i + 1) % k
        fs.append((i, j, k + j, k + i))
    return _mesh(name, vs, fs, mat)


def _dome(name, frame, cx, cy, r, z, h, mat, seg=10, rings=3):
    """A hemispherical lens / rivet head.  Closed at the base."""
    vs, fs = [], []
    for ri in range(rings + 1):
        t = ri / float(rings)
        rr = r * math.cos(t * math.pi / 2.0)
        zz = z + h * math.sin(t * math.pi / 2.0)
        for i in range(seg):
            a = 2 * math.pi * i / seg
            vs.append(frame.to_world(cx + rr * math.cos(a),
                                     cy + rr * math.sin(a), zz))
    for ri in range(rings):
        for i in range(seg):
            a, b = ri * seg + i, ri * seg + (i + 1) % seg
            fs.append((a, b, b + seg, a + seg))
    base = len(vs)
    vs.append(frame.to_world(cx, cy, z))
    for i in range(seg):
        fs.append((base, (i + 1) % seg, i))
    return _mesh(name, vs, fs, mat, smooth=True)


def build(name, frame, W, root_scale=1.0, spin_deg=0.0, seat=0.0,
          label="REFIT", mark=None, sub_base=False, service_rail=True,
          ratchet=True, tally=True, jewel=True, geo=None):
    """The port itself.  Returns {objects, parts, manifest}.

    name         object-name prefix, e.g. "kvs_refit"
    frame        PortFrame in the space you are authoring in.  Its origin is on
                 the CARRIER surface; the port is seated `seat` above it.
    W            width across flats, in WORLD metres
    root_scale   the scale of the root you are authoring INSIDE.  DNSM 0.78,
                 MQB 0.70, PKT 1.15 -- pass it and W stays the world size you
                 asked for.  This is FIX_UPLOAD's section 2 trap.
                 IT IS 1.0 ON THE `-- refit` ENTRY POINT, which clears the
                 scene and authors in world coordinates: there is no root to
                 be inside.  `check_root_scale()` refuses a non-unit value in
                 an empty scene rather than shipping a 1/0.70 = 1.43x port.
    seat         how far above the carrier the port's underside sits, from
                 `solve_anchor()`.  The SERVICE RAIL spans it, so the assembly
                 touches down however uneven the carrier is.
    sub_base     the riveted plate.  Optional where there is structure nearby
                 (FIX_UPLOAD 1.4); wanted on featureless bulkhead -- LOG, MTA.

    THE LEAVES ARE SOLIDS, NOT TRIANGLES.  See trap 21 in the module docstring.
    THE THROAT IS LIT.  The sketches say the open state fails otherwise
    (FIX_UPLOAD 1.4): it reads as "a hexagon that lost its star", a hole rather
    than an invitation.  `rp_glow` is emissive and the frontend drives it.
    """
    G = dict(GEO)
    if geo:
        G.update(geo)
    # REFUSES A root_scale THAT HAS NO ROOT -- see check_root_scale().
    root_scale = check_root_scale(root_scale, "refit_port.build", "W", W)
    s = W / float(root_scale)          # authoring-space W
    seat_s = seat / float(root_scale)

    def M(k):
        return _material("rp_" + k, MATS[k])

    # EVERY height is `seat` PLUS its GEO fraction of W.  Writing z_seat as the
    # bare seat put the throat floor BELOW the service rail's top face and the
    # rail was visible straight through the open port, as a brass bar across
    # the lit aperture.  It looked like a design decision.  The invariant is
    # z_rail < z_seat < z_leaf < z_face, asserted below.
    z_seat = seat_s + G["z_seat"] * s
    z_face = seat_s + G["z_face"] * s
    z_leaf = seat_s + G["z_leaf"] * s
    z_rail = seat_s + G["z_rail"] * s
    assert z_rail < z_seat < z_leaf < z_face, (
        "refit port height stack is out of order: rail %.5f seat %.5f leaf "
        "%.5f face %.5f -- the rail must be UNDER the throat floor, the leaves "
        "under the frame face" % (z_rail, z_seat, z_leaf, z_face))

    objs, parts = [], {}

    # ------------------------------------------------------------- the frame
    # Closed cross-section loop: up the outside, in across the face with a
    # chamfer, down the bore, out along the underside.
    prof = [(G["r_out"] * s, z_seat),
            (G["r_out"] * s, z_face - 0.030 * s),
            (G["r_lip"] * s, z_face),
            (G["r_in"] * s, z_face),
            (G["r_in"] * s, z_seat)]
    ring = _shell(name + "_frame", frame, prof, M("brass"), spin_deg)
    objs.append(ring)
    parts["frame"] = ring.name

    # ------------------------------------------------- the throat and its light
    wall = _shell(name + "_throat", frame,
                  [(G["r_in"] * s, z_face), (G["r_in"] * 0.97 * s, z_seat)],
                  M("throat"), spin_deg, closed=False)
    # The bore is looked at from INSIDE, so its normals point at the axis.  The
    # generated winding is outward; flip it.  This is the one deliberately
    # one-sided surface in the port and the reason facingAudit() must be run.
    wall.data.flip_normals() if hasattr(wall.data, "flip_normals") else None
    for p in wall.data.polygons:
        p.flip()
    wall.data.update()
    objs.append(wall)
    parts["throat"] = wall.name

    floor = _cap(name + "_glow", frame, G["r_in"] * 0.97 * s, z_seat,
                 M("glow"), spin_deg)
    objs.append(floor)
    parts["glow"] = floor.name

    # guide rails inside the throat -- "something goes in here", without a card
    for i, sgn in ((0, -1.0), (1, 1.0)):
        u0 = sgn * G["rail_u"] * s
        poly = [(u0 - G["rail_w"] * s, -G["rail_v"] * s),
                (u0 + G["rail_w"] * s, -G["rail_v"] * s),
                (u0 + G["rail_w"] * s, G["rail_v"] * s),
                (u0 - G["rail_w"] * s, G["rail_v"] * s)]
        o = _prism("%s_guide_%d" % (name, i), frame, poly,
                   z_seat, z_seat + G["rail_h"] * s, M("brass_dk"))
        objs.append(o)
    parts["guides"] = 2

    # ------------------------------------------------------------- the iris
    # Six leaves.  Closed they tile the throat mouth exactly and their seams
    # radiate from the centre -- that is the six-pointed star, and it is the
    # port's identity (FIX_UPLOAD 1.2: the CLOSED state is the one the player
    # learns).  Each leaf is a PRISM.
    Rl = G["r_leaf"] * s
    Rh = G["leaf_hub"] * s
    gap = math.radians(G["leaf_gap_deg"])
    leaves, pivots = [], []
    for i in range(6):
        a0 = math.radians(spin_deg + i * 60.0) + gap
        a1 = math.radians(spin_deg + (i + 1) * 60.0) - gap
        # a hexagon EDGE, not an arc: the leaf's outer edge is the chord
        # between two hexagon corners, so the closed iris is a hexagon.
        def edge(t):
            c0 = (Rl * math.cos(math.radians(spin_deg + i * 60.0)),
                  Rl * math.sin(math.radians(spin_deg + i * 60.0)))
            c1 = (Rl * math.cos(math.radians(spin_deg + (i + 1) * 60.0)),
                  Rl * math.sin(math.radians(spin_deg + (i + 1) * 60.0)))
            return (c0[0] + (c1[0] - c0[0]) * t, c0[1] + (c1[1] - c0[1]) * t)
        f = gap / math.radians(60.0)
        poly = [(Rh * math.cos(a0), Rh * math.sin(a0)),
                edge(f), edge(1.0 - f),
                (Rh * math.cos(a1), Rh * math.sin(a1))]
        o = _prism_bevel("%s_leaf_%d" % (name, i), frame, poly,
                         z_leaf - G["t_leaf"] * s / 2,
                         z_leaf + G["t_leaf"] * s / 2,
                         G["leaf_bevel"] * s, M("steel"))
        leaves.append(o)
        objs.append(o)
        pivots.append(edge(0.0))     # the OUTER CORNER, in port-local (u, v)
    parts["leaves"] = [o.name for o in leaves]

    # ----------------------------------------------------------- the ratchet
    # ONE index tooth.  A six-fold-symmetric ring stepping 60 deg per phase is
    # indistinguishable from a ring that has not moved -- FIX_UPLOAD 5.3 asks
    # for exactly that and it cannot be read.  See note 5 in the docstring.
    if ratchet:
        z_r = z_face + G["z_ratchet"] * s
        ri, ro = G["r_ratchet_i"] * s, G["r_ratchet_o"] * s
        tooth = _prism(name + "_detent", frame,
                       [(ri, -0.040 * s), (ro, -0.030 * s),
                        (ro, 0.030 * s), (ri, 0.040 * s)],
                       z_r, z_r + G["t_ratchet"] * s * 2.2,
                       M("brass_dk"))
        objs.append(tooth)
        parts["ratchet"] = [tooth.name]

    # ------------------------------------------------------------- the jewel
    # WHITE FAMILY ONLY.  It says one thing: did the last refit you commanded
    # go in.  Every colour and every health statement is the telltale mast's.
    if jewel:
        j = _dome(name + "_jewel", frame, 0.0, G["jewel_v"] * s,
                  G["jewel_r"] * s, z_face - 0.012 * s, G["jewel_h"] * s,
                  M("jewel"), seg=10, rings=3)
        objs.append(j)
        parts["jewel"] = j.name

    # --------------------------------------------------------- the tally flag
    if tally:
        tu, tv = G["tally_u"] * s, G["tally_v"] * s
        tw, th = G["tally_w"] * s, G["tally_h"] * s
        t = _prism(name + "_tally", frame,
                   [(tu - tw, tv), (tu + tw, tv), (tu + tw, tv + th),
                    (tu - tw, tv + th)],
                   z_face, z_face + G["tally_t"] * s, M("brass"))
        objs.append(t)
        parts["tally"] = t.name
        parts["tally_hinge"] = [tu, tv]

    # -------------------------------------------------------- the service rail
    # FIX_UPLOAD section 4 / STATUS_AT_A_GLANCE 11.2.  The port claims the
    # first 1.3 W and the telltale mast mounts at 1.5 W.  BUILD ONLY THIS HALF.
    # It also spans `seat`, so the assembly touches the carrier whatever the
    # carrier is doing underneath.
    if service_rail:
        rh, rv = G["srail_half"] * s, G["srail_v"] * s
        o = _prism(name + "_srail", frame,
                   [(-rh, -rv), (rh, -rv), (rh, rv), (-rh, rv)],
                   0.0, z_rail, M("brass_dk"))
        objs.append(o)
        parts["service_rail"] = o.name

    # ------------------------------------------------------------ the sub-base
    if sub_base:
        bw, bh = G["base_hw"] * s, G["base_hh"] * s
        o = _prism(name + "_base", frame,
                   [(-bw, -bh), (bw, -bh), (bw, bh), (-bw, bh)],
                   0.0, z_seat, M("brass"))
        objs.append(o)
        parts["sub_base"] = o.name
        ins = G["rivet_in"] * s
        for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
            objs.append(_dome("%s_rivet_%d" % (name, i), frame,
                              sx * (bw - ins), sy * (bh - ins),
                              G["rivet_r"] * s, z_seat, G["rivet_r"] * s * 0.6,
                              M("brass"), seg=8, rings=2))
        parts["rivets"] = 4

    # ------------------------------------------------------------- the label
    if label:
        objs.append(_engrave(name + "_label", frame, label,
                             0.0, 0.470 * s, z_face, 0.070 * s, M("ink"),
                             spin_deg))
        parts["label"] = label
    if mark:
        objs.append(_engrave(name + "_mark", frame, mark,
                             -0.330 * s, -0.330 * s, z_face, 0.060 * s,
                             M("ink"), spin_deg))
        parts["mark"] = mark

    tris, per = 0, {}
    for o in objs:
        o.data.calc_loop_triangles()
        t = len(o.data.loop_triangles)
        per[o.name] = t
        tris += t
    print("  refit port: %d tris over %d objects" % (tris, len(objs)))
    for k in sorted(per, key=lambda k: -per[k]):
        print("      %-26s %5d" % (k, per[k]))

    return {"objects": objs, "parts": parts, "tris": tris, "tris_per": per,
            "W": W, "seat": seat, "spin_deg": spin_deg,
            "leaf_pivots": pivots,
            "z": {"seat": G["z_seat"], "face": G["z_face"],
                  "leaf": G["z_leaf"], "rail": G["z_rail"]},
            "open": {"deg": G["open_deg"], "scale": G["open_scale"]}}


def _engrave(name, frame, body, x, y, z, size, mat, spin_deg=0.0,
             extrude=0.00025):
    """Stamped lettering on a facet, converted to MESH.

    This is STAMPED type -- a nameplate, the same class as KVS's baked drawer
    labels -- and NOT content text.  Content text on this component is the
    screen-space docket and there is none in geometry, which is why
    `check_text.py` is not engaged.  Do not put a value here.
    """
    bpy = _bpy()
    fonts = ("/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
             "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
             "/System/Library/Fonts/Menlo.ttc")
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    # A FONT curve tessellates at resolution_u 12 by default and `REFIT` alone
    # comes out at ~6,800 triangles -- four times the whole port's budget, for
    # lettering that is 6 px of cap height on screen.  2 is indistinguishable
    # at 56 px and costs ~1/8 of it.  FIX_UPLOAD 8.2 quotes 600-1,400 tris for
    # this and that figure is only reachable with the resolution turned down.
    cu.resolution_u = 2
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.extrude = extrude
    for p in fonts:
        if os.path.exists(p):
            try:
                cu.font = bpy.data.fonts.load(p)
                break
            except Exception:                                   # noqa: BLE001
                pass
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    # place it in the port plane: columns u, v, n
    from mathutils import Matrix, Vector
    B = Matrix(((frame.u[0], frame.v[0], frame.n[0], 0.0),
                (frame.u[1], frame.v[1], frame.n[1], 0.0),
                (frame.u[2], frame.v[2], frame.n[2], 0.0),
                (0.0, 0.0, 0.0, 1.0)))
    R = Matrix.Rotation(math.radians(spin_deg), 4, 'Z')
    o.matrix_world = (Matrix.Translation(Vector(frame.to_world(x, y, z)))
                      @ B @ R)
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target='MESH')
    return bpy.data.objects.get(name) or o


def export_glb(objs, path):
    """Selection-only GLB, +Y up, materials on.

    Identical flags to `transliterate.export_glb()` so the port lands in the
    same world the module's own props land in.  `export_yup=True` is the
    Blender Z-up -> three Y-up map, which is `to3()` and its inverse
    `to_blender()` above.
    """
    bpy = _bpy()
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.hide_render = o.hide_viewport = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB',
                              use_selection=True, export_apply=True,
                              export_yup=True, export_materials='EXPORT',
                              export_cameras=False, export_lights=False)
    print("  glb    ->", os.path.basename(path), os.path.getsize(path), "B")


def export(code, A, P, glb="refit.glb", label="REFIT"):
    """Write `<CODE>/refit.glb` and merge a `"refit"` block into `scene.json`.

    RE-RENDERS NOTHING.  `plate.png`, `depth.bin`, every `gt_*.png`,
    `materials.json` and the module's own `.glb` files are not opened for
    writing, and `scene.json` is edited key-wise rather than rewritten from a
    fresh export.  That is what keeps every number in `live3d/RESULTS.md`
    reproducible -- FIX_UPLOAD section 0, decision 3.

    NOTE FOR THE FAN-OUT: `pipeline/live_depth.py` globs *every* `.glb` in the
    asset folder, so adding one changes what `ubias.py` is measured on.  Re-run
    `live_depth.py <CODE>` after this and confirm the module's shipped
    `ubias_m` has not moved.
    RUN IT WITH BLENDER'S PYTHON, NOT THE SYSTEM ONE: `live_depth.py` needs
    numpy and `/usr/bin/python3` does not have it --
    `/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13
    live3d/pipeline/live_depth.py <CODE>`.  This file and `status_mast.py` are
    pure stdlib and run under plain `python3`; that one is not.  It should not: the port stands proud of its
    carrier by design, so it adds only large gaps.  Confirm it anyway.
    """
    Adir = os.path.join(LIVE3D, "assets", code)
    export_glb(P["objects"], os.path.join(Adir, glb))

    sp = os.path.join(Adir, "scene.json")
    S = json.load(open(sp))
    fr = A["frame"]
    Wm = P["W"]

    def w3(x, y, z):
        return [round(t, 9) for t in fr.to_world(x, y, z)]

    zs = P["z"]
    leaf = []
    for i, (a, b) in enumerate(P["leaf_pivots"]):
        leaf.append({"node": P["parts"]["leaves"][i],
                     "pivot": w3(a, b, zs["leaf"] * Wm + P["seat"])})
    S["refit"] = {
        "glb": glb,
        "label": label,
        "kind": "iris_port",
        "code": code,
        "anchor_px": A["anchor_px"],
        "port_px": A["port_px"],
        "W_m": round(Wm, 9),
        "seat_m": round(P["seat"], 9),
        "spin_deg": P["spin_deg"],
        "root_scale": 1.0,
        "frame": fr.json(),
        "centre": w3(0.0, 0.0, zs["face"] * Wm + P["seat"]),
        "axis": [round(t, 9) for t in fr.n],
        "hotspot": A["hotspot"],
        "parts": P["parts"],
        "leaves": leaf,
        "open": {"deg": P["open"]["deg"], "scale": P["open"]["scale"],
                 "ms": 420, "close_ms": 160},
        "ratchet": {"pivot": w3(0.0, 0.0, zs["seat"] * Wm + P["seat"]),
                    "step_deg": 60.0, "phases": 6},
        "tally": ({"hinge": w3(P["parts"]["tally_hinge"][0],
                               P["parts"]["tally_hinge"][1],
                               zs["face"] * Wm + P["seat"]),
                   # +78, not -78.  Rotating a point at +v about +u by a
                   # NEGATIVE angle sends it to -n, i.e. the flag flips DOWN
                   # INTO the port and is never seen.  Right-hand rule.
                   "axis": [round(t, 9) for t in fr.u], "up_deg": 78.0}
                  if "tally" in P["parts"] else None),
        # The shared brass service rail.  The port claims the first 1.3 W; the
        # telltale mast mounts at 1.5 W, leaving 0.2 W of clear rail between
        # them.  STATUS_AT_A_GLANCE 11.2 accepted this; these are the numbers.
        "service_rail": {
            "origin": w3(0.0, 0.0, 0.0),
            "dir": [round(t, 9) for t in fr.u],
            "claimed_half_m": round(GEO["srail_half"] * Wm, 9),
            "thick_m": round(2 * GEO["srail_v"] * Wm, 9),
            "proud_m": round(GEO["z_rail"] * Wm + P["seat"], 9),
            "free_from_m": round(GEO["srail_free"] * Wm, 9)},
        # the evidence, so nobody has to take the placement on trust
        "evidence": {
            "tris": P["tris"],
            "bbox_px": [round(t, 3) for t in A["bbox"]],
            "projected_px": [round(A["bbox_px"][0], 2),
                             round(A["bbox_px"][1], 2)],
            "carrier_solid_pct": round(A["carrier_solid_pct"], 2),
            "carrier_depth_m": [round(A["carrier_depth_m"][0], 5),
                                round(A["carrier_depth_m"][1], 5)],
            "carrier_resid_max_m": round(A["carrier_resid_max"], 6),
            "obliq_carrier_deg": round(A["obliq_carrier"], 3),
            "obliq_declared_face_deg": round(A["obliq_face"], 3),
            "normal_used": A["normal_used"],
            "seat_over_ubias": round(A["seat_m"] / A["ubias_m"], 2),
            # THE RATIO ABOVE IS NOT THE NUMBER.  "2.5x ubias" reads healthy at
            # 2.5 microns; these two say whether the seat survives the depth
            # composite.  See THE STAND-OFF FLOOR at the top of this file.
            "carrier_grad_m_per_px": round(A["margin"]["grad_m_per_px"], 9),
            "seat_margin_px_of_gradient": (
                None if A["margin"]["margin_px"] == float("inf")
                else round(A["margin"]["margin_px"], 3)),
            "clearances": A["clearances"]},
    }
    with open(sp, "w") as f:
        json.dump(S, f, indent=1)
    print("  scene.json <- refit block (%d tris, %d parts)"
          % (P["tris"], len(P["parts"])))
    return S["refit"]


# ===========================================================================
# CLI -- anchor selection, with no Blender in the loop.
#
#     python3 live3d/pipeline/refit_port.py KVS 364 697 56
#     python3 live3d/pipeline/refit_port.py KVS 364 697 56 --window 332,396,682,718
#     python3 live3d/pipeline/refit_port.py KVS 364 697 56 --normal face
#     python3 live3d/pipeline/refit_port.py KVS 364 685 56 --sweep-y 680,706
#
# Choosing an anchor is measurement, not modelling, and it is where the fan-out
# will spend its time: it wants the carrier's real normal, the real flatness,
# the real clearances and the real stand-off BEFORE anything is built.
# ===========================================================================
# CLI examples, all pure stdlib, no Blender:
#
#     python3 live3d/pipeline/refit_port.py KVS 364 700 56 --window 332,396,682,718
#     python3 live3d/pipeline/refit_port.py FMM 359 677 57 --sweep-y 600,714
#     python3 live3d/pipeline/refit_port.py MTA 123 584 56 --sub-base --window 75,171,552,616
#
# `--seat-margin` is in MULTIPLES OF `ubias_m` and is needed wherever `ubias_m`
# is not a gap -- see THE STAND-OFF FLOOR above.  FMM ships 1200:
#
#     python3 live3d/pipeline/refit_port.py FMM 600 681 57 \
#             --window 556,646,655,705 --seat-margin 1200
#
def _cli(argv):
    USAGE = ("usage: refit_port.py CODE PX PY PORT_PX [--window x0,x1,y0,y1] "
             "[--spin DEG] [--normal carrier|face] [--sub-base] [--no-rail] "
             "[--seat-margin N] [--seat-cap F] [--sweep-y y0,y1]")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.split("THREE HALVES")[0])
        print(USAGE)
        return 0
    if len(argv) < 4:
        raise SystemExit("refit_port.py: CODE PX PY PORT_PX are all required\n"
                         + USAGE)
    code = argv[0]
    px, py, port_px = int(argv[1]), int(argv[2]), int(argv[3])
    opts, i = {}, 4
    kw = dict(spin_deg=None, carrier_window=None, normal="carrier",
              sub_base=False, service_rail=True)

    def val(k, flag):
        """The argument after `flag`, or a loud failure.

        `refit_port.py KVS 364 700 56 --window` used to raise a bare IndexError
        from inside the scan.  A missing value is a typo and the message should
        say which flag lost its number.  Same helper, same reason, as
        `status_mast.py`'s.
        """
        if k + 1 >= len(argv):
            raise SystemExit("refit_port.py: %s needs a value" % flag)
        return argv[k + 1]

    while i < len(argv):
        a = argv[i]
        if a == "--window":
            kw["carrier_window"] = tuple(int(t) for t in val(i, a).split(","))
            if len(kw["carrier_window"]) != 4:
                raise SystemExit("refit_port.py: --window wants x0,x1,y0,y1")
            i += 1
        elif a == "--spin":
            kw["spin_deg"] = float(val(i, a)); i += 1
        elif a == "--normal":
            kw["normal"] = val(i, a); i += 1
        elif a == "--sub-base":
            kw["sub_base"] = True
        elif a == "--no-rail":
            kw["service_rail"] = False
        elif a == "--seat-margin":
            # MULTIPLES OF `ubias_m`, and the CLI had no flag for it at all --
            # so `export_fmm.py`'s shipped `seat_margin=1200` could not be
            # reproduced from the command line and the documented commands
            # printed the 0.059 mm seat the module explicitly rejected.
            # FMM NOTES 15.
            kw["seat_margin"] = float(val(i, a)); i += 1
        elif a == "--seat-cap":
            kw["seat_cap"] = float(val(i, a)); i += 1
        elif a == "--sweep-y":
            opts["sweep"] = tuple(int(t) for t in val(i, a).split(","))
            if len(opts["sweep"]) != 2:
                raise SystemExit("refit_port.py: --sweep-y wants y0,y1")
            i += 1
        else:
            # LOUD, NOT IGNORED.  This scan used to fall through on an
            # unrecognised token, so `--sub_base` (underscore) or `--seat-margin`
            # (before it existed) were discarded silently along with their
            # values and the tool printed a confident table for the DEFAULTS.
            # `status_mast.py` fixed the same defect after MQB; this is the
            # other half of it.  There is no positional argument after PORT_PX.
            raise SystemExit("refit_port.py: unknown argument %r\n%s"
                             % (a, USAGE))
        i += 1
    if "sweep" in opts:
        y0, y1 = opts["sweep"]
        print("%-5s %-7s %-8s %-16s %-8s %s"
              % ("y", "spin", "W (mm)", "bbox px", "seat mm", "seat/ubias"))
        for y in range(y0, y1 + 1, 2):
            A = None
            try:
                A = solve_anchor(code, px, y, port_px, verbose=False, **kw)
            except ThinMargin as e:
                # A SWEEP IS A REPORT, NOT A BUILD.  The floor depends on the
                # module and the window, not on `y`, so refusing every row
                # would delete the band the sweep exists to show.  Print the
                # row AND the flag.
                A = e.anchor
            except Overhang as e:
                # Same rule: a sweep exists to SHOW which rows overhang.
                A = e.anchor
            except ValueError as e:
                print("%-5d  -- %s" % (y, str(e).split("\n")[0]))
                continue
            M = A.get("margin") or {}
            print("%-5d %-7.1f %-8.2f %6.1f x %-7.1f %-8.3f %.1fx%s"
                  % (y, A["spin_deg"], A["W_m"] * 1000, A["bbox_px"][0],
                     A["bbox_px"][1], A["seat_m"] * 1000,
                     A["seat_m"] / A["ubias_m"],
                     ("   !! MARGIN %.2f px < %.2f -- see --seat-margin"
                      % (M["margin_px"], M["floor_px"])) if M.get("thin")
                     else (("   !! OVERHANGS -- the assembly comes within "
                            "%.4f mm of the plate at (%.0f, %.0f), %.1f mm up"
                            % (A["assembly_clear_m"] * 1000,
                               A["assembly_clear_at"][0],
                               A["assembly_clear_at"][1],
                               A["assembly_clear_at"][2]))
                           if (A.get("assembly_clear_m") is not None
                               and A["assembly_clear_m"] < A["ubias_m"])
                           else "")))
        return 0
    solve_anchor(code, px, py, port_px, **kw)
    return 0


if __name__ == "__main__":
    import sys as _sys
    try:
        raise SystemExit(_cli(_sys.argv[1:]))
    except ThinMargin as _e:
        # A REFUSAL, NOT A CRASH.  The traceback is noise -- the message is
        # the whole point -- and the exit code has to be non-zero, because a
        # batch that reports rc=0 for twelve steps while producing wrong
        # output is how this class of defect ships.
        _sys.stderr.write("refit_port.py REFUSES this stand-off:\n%s\n" % _e)
        raise SystemExit(2)
    except Overhang as _e:
        _sys.stderr.write("refit_port.py REFUSES this seat:\n%s\n" % _e)
        raise SystemExit(2)
    except ValueError as _e:
        _sys.stderr.write("refit_port.py: %s\n" % _e)
        raise SystemExit(2)
