"""
LOG -- log-module  ->  BLACK BOX / FLIGHT RECORDER
Cockpit control for the SAINTCON 2026 AppSec Challenge.

Slot: the FASCIA -- the tall vertical console front below the dash lip. That
surface was picked for LOG because a strip-chart recorder wants paper coming
physically out of the console at the pilot. So the control is a recorder deck:

    LOG TAPE   (frames)  -- ivory paper strip scrolling behind the window with a
                            red ink trace on it; the supply/take-up spools turn
                            with it, visible through two brass ports. Paper
                            leaves through a slot in the panel front and hangs
                            out over the fascia.       -> the live stream
    SEARCH LENS(rotate)  -- a magnifier on a brass arm you swing across the
                            tape.                      -> GET /search?q=
    SOURCE     (states)  -- rotary selector, one lamp per source file.
                                                       -> &source= / /logs/{name}
    WIPE       (states)  -- a lever behind a break-glass cover: sealed, glass
                            broken/armed, lever thrown. A destructive action you
                            have to deliberately reach for.
                                                       -> DELETE /logs/{name}

Run standalone:
    /Applications/Blender.app/Contents/MacOS/Blender --background --python build.py
"""
import bpy, math, os, sys, json
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
COCKPIT = os.path.dirname(os.path.dirname(HERE))
if COCKPIT not in sys.path:
    sys.path.insert(0, COCKPIT)
import shell                                              # noqa: E402
import slots                                              # noqa: E402

CODE = "LOG"
NAME = "Black Box"
SURFACE = slots.SLOTS[CODE]["surface"]
OUT = os.path.join(HERE, "out")

# stand the housing off the (curved) fascia so its flat back doesn't gap
LIFT = 0.020

# ---- panel geometry (local: +X right, +Y up, +Z out toward the pilot) ------
PW, PH = 0.660, 0.420                     # face size
HX, HY = PW / 2, PH / 2                   # +/- extents
FACE_Z = 0.020                            # front face plane
APX = 0.115                               # tape window half width
APY0, APY1 = -0.040, 0.140                # tape window bottom / top
RIB_X = 0.106                             # ribbon half width
RIB_Y0, RIB_Y1 = -0.140, 0.210            # ribbon extent at rest
SLOT_Y0, SLOT_Y1 = -0.098, -0.082         # the paper slot in the panel front
SPOOL_X, SPOOL_Y = 0.235, 0.055           # spool port centres (+/- X)
SPOOL_R = 0.046                           # paper roll radius (drives spin)
SRC_X, SRC_Y = -0.235, -0.150             # source selector centre
WIPE_X, WIPE_Y = 0.235, -0.150            # break-glass centre
LENS_X, LENS_Y = -0.150, 0.150            # magnifier arm pivot
LENS_ARM = 0.190                          # pivot -> lens centre

TAPE_FRAMES = 8
TAPE_TRAVEL = 0.070                       # metres of paper past the window
TAPE_REST = 3                             # frame used in the wide shot
LENS_RANGE = [-74.0, 6.0]                 # CSS degrees, 0 = hanging straight down
SRC_STATES = ["all", "nav", "mta", "kvs"]
SRC_ANGLES = [-78.0, -26.0, 26.0, 78.0]   # detent bearings, 0 = up
WIPE_STATES = ["sealed", "armed", "wiped"]
WIPE_THROW = -62.0                        # lever swing, degrees about local Z


# --------------------------------------------------------------- primitives
def _mat(name, *a, **kw):
    """shell.material(), but idempotent so a re-import doesn't pile up dupes."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    return shell.material(name, *a, **kw)


def _cyl(name, loc, r, d, mat, verts=32, smooth=True, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, vertices=verts,
                                        location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    if smooth:
        for f in o.data.polygons:
            f.use_smooth = True
    return o


def _box(name, center, size, mat, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    if bevel:
        m = o.modifiers.new("bev", 'BEVEL')
        m.width, m.segments = bevel, 2
    o.data.materials.append(mat)
    return o


def _sphere(name, loc, r, mat, scale=(1, 1, 1), seg=20, ring=12):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg,
                                         ring_count=ring, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    o.data.materials.append(mat)
    for f in o.data.polygons:
        f.use_smooth = True
    return o


def _ring(name, loc, major, minor, mat, seg=40, ring=10):
    bpy.ops.mesh.primitive_torus_add(location=loc, major_radius=major,
                                     minor_radius=minor,
                                     major_segments=seg, minor_segments=ring)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    for f in o.data.polygons:
        f.use_smooth = True
    return o


def _empty(name, loc):
    bpy.ops.object.empty_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.empty_display_size = 0.02
    return o


def _adopt(child, parent):
    """Parent keeping the child's .location as a LOCAL offset."""
    child.parent = parent
    child.matrix_parent_inverse.identity()


def _seg_box(name, p0, p1, z, w, mat):
    """A thin bar spanning p0->p1 in the panel plane (used for the ink trace)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    th = math.atan2(-dx, dy)
    return _box(name, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, z),
                (w, ln, 0.0016), mat, rot=(0, 0, th))


def _trace_x(i):
    """Deterministic strip-chart wiggle, kept inside the ribbon."""
    return 0.045 + 0.035 * math.sin(i * 0.9) + 0.018 * math.sin(i * 2.3 + 1.1)


# ------------------------------------------------------------------- build
def add_props(P, mats):
    """Add the LOG flight-recorder deck to the CURRENT scene.

    P    : the shell PARAMS dict (already built)
    mats : {"brass":..., "hull":..., "hull_d":...}
    Returns {"far": [...], "controls": {...}, "plate": [...], "root": obj}
    """
    brass = mats["brass"]
    hull = mats["hull"]
    hull_d = mats["hull_d"]
    panel_m = _mat("log_panel", (0.030, 0.032, 0.038, 1), 0.10, 0.55)
    well_m = _mat("log_well", (0.012, 0.013, 0.017, 1), 0.05, 0.72)
    paper = _mat("log_paper", (0.880, 0.855, 0.775, 1), 0.0, 0.62)
    paper2 = _mat("log_paper2", (0.840, 0.812, 0.726, 1), 0.0, 0.66)
    ink = _mat("log_ink", (0.040, 0.038, 0.036, 1), 0.0, 0.82)
    trace_m = _mat("log_trace", (0.60, 0.075, 0.055, 1), 0.0, 0.40,
                   emission=(0.85, 0.11, 0.07, 1), emit_strength=0.45)
    glass_m = _mat("log_glass", (0.66, 0.84, 0.94, 1), 0.0, 0.06,
                   alpha=0.10)
    # the break-glass cover reads heavier than the magnifier lens, so that
    # "sealed" vs "smashed" is unmistakable
    pane_m = _mat("log_pane", (0.70, 0.86, 0.96, 1), 0.0, 0.05, alpha=0.30)
    lamp_off = _mat("log_lamp_off", (0.15, 0.115, 0.045, 1), 0.0, 0.40)
    lamp_amb = _mat("log_lamp_amber", (1.0, 0.72, 0.24, 1), 0.0, 0.30,
                    emission=(1.0, 0.60, 0.16, 1), emit_strength=3.4)
    lamp_red = _mat("log_lamp_red", (1.0, 0.26, 0.20, 1), 0.0, 0.30,
                    emission=(1.0, 0.16, 0.10, 1), emit_strength=4.2)
    red_m = _mat("log_red", (0.36, 0.045, 0.035, 1), 0.0, 0.48)

    root = _empty("log_root", (0, 0, 0))
    plate, far = [], []

    def keep(o, parent=None, static=True):
        _adopt(o, parent or root)
        far.append(o)
        if static:
            plate.append(o)
        return o

    # ----------------------------------------------------------- the housing
    # a real box standing proud of the fascia, so the flat panel never floats
    keep(_box("log_case_back", (0, 0, -0.045), (PW + 0.026, PH + 0.026, 0.010),
              hull))
    for i, (cx, cy, sx, sy) in enumerate((
            (0.0, HY + 0.0065, PW + 0.026, 0.013),
            (0.0, -HY - 0.0065, PW + 0.026, 0.013),
            (-HX - 0.0065, 0.0, 0.013, PH + 0.026),
            (HX + 0.0065, 0.0, 0.013, PH + 0.026))):
        keep(_box(f"log_case_wall_{i}", (cx, cy, -0.012), (sx, sy, 0.076),
                  hull, bevel=0.004))
        keep(_box(f"log_bezel_{i}", (cx, cy, 0.026), (sx, sy, 0.014),
                  brass, bevel=0.003))

    # face plate built as FOUR pieces, so the tape window is a genuine hole
    keep(_box("log_face_top", (0, (APY1 + HY) / 2, FACE_Z),
              (PW, HY - APY1, 0.012), panel_m, bevel=0.002))
    # the bottom face is split again, leaving the paper slot open
    keep(_box("log_face_low", (0, (-HY + SLOT_Y0) / 2, FACE_Z),
              (PW, SLOT_Y0 + HY, 0.012), panel_m, bevel=0.002))
    keep(_box("log_face_mid", (0, (SLOT_Y1 + APY0) / 2, FACE_Z),
              (PW, APY0 - SLOT_Y1, 0.012), panel_m, bevel=0.002))
    for i, sx in enumerate((-1, 1)):
        keep(_box(f"log_face_slot_{i}",
                  (sx * (HX + 0.135) / 2, (SLOT_Y0 + SLOT_Y1) / 2, FACE_Z),
                  (HX - 0.135, SLOT_Y1 - SLOT_Y0, 0.012), panel_m))
    keep(_box("log_face_left", (-(HX + APX) / 2, (APY0 + APY1) / 2, FACE_Z),
              (HX - APX, APY1 - APY0, 0.012), panel_m, bevel=0.002))
    keep(_box("log_face_right", ((HX + APX) / 2, (APY0 + APY1) / 2, FACE_Z),
              (HX - APX, APY1 - APY0, 0.012), panel_m, bevel=0.002))

    # the well the paper runs in, behind the face
    keep(_box("log_deck", (0, 0.035, -0.006), (0.300, 0.400, 0.006), well_m))
    # brass window surround
    for i, (cx, cy, sx, sy) in enumerate((
            (0, APY1 + 0.006, 2 * APX + 0.024, 0.012),
            (0, APY0 - 0.006, 2 * APX + 0.024, 0.012),
            (-APX - 0.006, (APY0 + APY1) / 2, 0.012, APY1 - APY0 + 0.024),
            (APX + 0.006, (APY0 + APY1) / 2, 0.012, APY1 - APY0 + 0.024))):
        keep(_box(f"log_win_trim_{i}", (cx, cy, FACE_Z + 0.008),
                  (sx, sy, 0.008), brass, bevel=0.002))

    # nameplate + engraved bars (reads as lettering at cockpit distance)
    keep(_box("log_nameplate", (0, 0.180, FACE_Z + 0.007), (0.250, 0.030, 0.008),
              brass, bevel=0.002))
    for i in range(9):
        keep(_box(f"log_name_bar_{i}", (-0.100 + 0.025 * i, 0.180,
                                        FACE_Z + 0.012),
                  (0.013, 0.011, 0.003), ink))
    # corner screws
    for i, (sx, sy) in enumerate(((-1, 1), (1, 1), (-1, -1), (1, -1))):
        keep(_box(f"log_screw_{i}", (sx * (HX - 0.016), sy * (HY - 0.016),
                                     FACE_Z + 0.007),
                  (0.011, 0.011, 0.006), brass, bevel=0.0015))

    # the paper slot mouth: a dark lip the tape comes out of
    keep(_box("log_slot_lip_a", (0, SLOT_Y0 - 0.004, FACE_Z + 0.008),
              (2 * APX + 0.040, 0.008, 0.010), brass, bevel=0.002))
    keep(_box("log_slot_lip_b", (0, SLOT_Y1 + 0.004, FACE_Z + 0.008),
              (2 * APX + 0.040, 0.008, 0.010), brass, bevel=0.002))

    # ------------------------------------------- the pen carriage (static)
    keep(_box("log_pen_rail", (0, APY1 - 0.020, FACE_Z + 0.014),
              (2 * APX, 0.008, 0.008), brass, bevel=0.0015))
    keep(_box("log_pen_body", (0.045, APY1 - 0.020, FACE_Z + 0.020),
              (0.026, 0.020, 0.014), hull_d, bevel=0.002))
    keep(_box("log_pen_nib", (0.045, APY1 - 0.032, FACE_Z + 0.016),
              (0.005, 0.014, 0.005), trace_m))

    # ------------------------------------------------ LOG TAPE  (frames) ---
    tape_piv = _empty("log_tape_pivot", (0, 0, 0))
    _adopt(tape_piv, root)
    tape_objs = []

    def tape(o):
        _adopt(o, tape_piv)
        tape_objs.append(o)
        far.append(o)
        return o

    rib_h = RIB_Y1 - RIB_Y0
    tape(_box("log_ribbon", (0, (RIB_Y0 + RIB_Y1) / 2, 0.004),
              (2 * RIB_X, rib_h, 0.003), paper))
    # sprocket edge + printed rows
    n_rows = int(rib_h / 0.024)
    for i in range(n_rows):
        ry = RIB_Y0 + 0.014 + 0.024 * i
        tape(_box(f"log_rule_{i}", (0, ry, 0.0058), (2 * RIB_X - 0.010,
                                                     0.0026, 0.0016), ink))
        # two "text" runs on the left half, varying length per row
        w1 = 0.030 + 0.018 * (0.5 + 0.5 * math.sin(i * 1.7))
        w2 = 0.016 + 0.012 * (0.5 + 0.5 * math.sin(i * 2.9 + 2.0))
        tape(_box(f"log_txt_a_{i}", (-0.086 + w1 / 2, ry + 0.009, 0.0058),
                  (w1, 0.0070, 0.0016), ink))
        tape(_box(f"log_txt_b_{i}", (-0.086 + w1 + 0.008 + w2 / 2,
                                     ry + 0.009, 0.0058),
                  (w2, 0.0070, 0.0016), ink))
        if i % 3 == 0:                                   # sprocket perforation
            tape(_box(f"log_perf_{i}", (-RIB_X + 0.006, ry + 0.009, 0.0058),
                      (0.007, 0.007, 0.0016), well_m))
    # the red ink trace itself
    n_pts = 26
    pts = [(_trace_x(i), RIB_Y0 + 0.006 + (rib_h - 0.012) * i / (n_pts - 1))
           for i in range(n_pts)]
    for i in range(n_pts - 1):
        tape(_seg_box(f"log_trace_{i}", pts[i], pts[i + 1], 0.0064, 0.0058,
                      trace_m))

    # spool ports: reels turn as the paper runs
    spool_pivs = []
    for si, sx in enumerate((-SPOOL_X, SPOOL_X)):
        keep(_cyl(f"log_port_back_{si}", (sx, SPOOL_Y, FACE_Z + 0.004),
                  0.066, 0.008, well_m, verts=40))
        keep(_ring(f"log_port_ring_{si}", (sx, SPOOL_Y, FACE_Z + 0.030),
                   0.068, 0.008, brass))
        sp = _empty(f"log_spool_pivot_{si}", (sx, SPOOL_Y, 0))
        _adopt(sp, root)
        spool_pivs.append(sp)
        roll = _cyl(f"log_roll_{si}", (0, 0, FACE_Z + 0.020), SPOOL_R, 0.016,
                    paper2, verts=40)
        hubc = _cyl(f"log_hub_{si}", (0, 0, FACE_Z + 0.029), 0.017, 0.020,
                    brass, verts=24)
        flange = _cyl(f"log_flange_{si}", (0, 0, FACE_Z + 0.028), 0.029, 0.004,
                      hull_d, verts=32)
        parts = [roll, hubc, flange]
        for k in range(6):
            th = math.pi * k / 3
            parts.append(_box(f"log_spoke_{si}_{k}",
                              (math.sin(th) * 0.036, math.cos(th) * 0.036,
                               FACE_Z + 0.032),
                              (0.009, 0.046, 0.004), brass, rot=(0, 0, -th)))
        for o in parts:
            _adopt(o, sp)
            tape_objs.append(o)
            far.append(o)

    # ---------------------------- the paper already OUT of the slot (static)
    # A drooping tongue of tape hanging off the console front. Static: this is
    # the paper that has already been printed, it is always there.
    py, pz = SLOT_Y0 + 0.002, FACE_Z + 0.006
    for i, phi in enumerate((10.0, 18.0, 26.0, 32.0, 28.0, 18.0, 6.0)):
        f = math.radians(phi)
        dy, dz = -math.cos(f), math.sin(f)
        ln = 0.026
        cy, cz = py + dy * ln / 2, pz + dz * ln / 2
        keep(_box(f"log_tail_{i}", (0, cy, cz), (2 * RIB_X, ln, 0.0022),
                  paper, rot=(math.radians(180 - phi), 0, 0)))
        keep(_box(f"log_tail_rule_{i}", (0, cy, cz + 0.0022),
                  (2 * RIB_X - 0.014, 0.0016, 0.0016), ink,
                  rot=(math.radians(180 - phi), 0, 0)))
        w = 0.034 + 0.020 * math.sin(i * 1.3)
        keep(_box(f"log_tail_txt_{i}", (-0.084 + w / 2, cy + 0.006,
                                        cz + 0.0022),
                  (w, 0.0055, 0.0016), ink,
                  rot=(math.radians(180 - phi), 0, 0)))
        py, pz = py + dy * ln, pz + dz * ln

    # --------------------------------------------- SEARCH LENS  (rotate) ---
    keep(_cyl("log_lens_boss", (LENS_X, LENS_Y, FACE_Z + 0.026), 0.016, 0.042,
              brass, verts=24))
    lens_piv = _empty("log_lens_pivot", (LENS_X, LENS_Y, FACE_Z + 0.050))
    _adopt(lens_piv, root)
    lens_objs = []
    for o in (
        _box("log_lens_arm", (0, -(LENS_ARM - 0.032) / 2, 0.0),
             (0.014, LENS_ARM - 0.032, 0.009), brass, bevel=0.002),
        _box("log_lens_grip", (0, -0.052, 0.008), (0.020, 0.030, 0.010),
             hull_d, bevel=0.002),
        _ring("log_lens_ring", (0, -LENS_ARM - 0.010, 0.0), 0.041, 0.007,
              brass),
        _cyl("log_lens_glass", (0, -LENS_ARM - 0.010, 0.0), 0.040, 0.005,
             glass_m, verts=40),
    ):
        _adopt(o, lens_piv)
        lens_objs.append(o)
        far.append(o)

    # ------------------------------------------------- SOURCE  (states) ----
    keep(_cyl("log_src_face", (SRC_X, SRC_Y, FACE_Z + 0.006), 0.046, 0.010,
              hull_d, verts=40))
    keep(_ring("log_src_bezel", (SRC_X, SRC_Y, FACE_Z + 0.011), 0.049, 0.007,
               brass))
    src_domes = []
    for i, ang in enumerate(SRC_ANGLES):
        th = math.radians(ang)
        lx = SRC_X + math.sin(th) * 0.034
        ly = SRC_Y + math.cos(th) * 0.034
        keep(_cyl(f"log_src_cup_{i}", (lx, ly, FACE_Z + 0.010), 0.010, 0.008,
                  brass, verts=18))
        d = _sphere(f"log_src_dome_{i}", (lx, ly, FACE_Z + 0.015), 0.0078,
                    lamp_off, scale=(1, 1, 0.62))
        _adopt(d, root)
        far.append(d)
        src_domes.append(d)
    src_piv = _empty("log_src_pivot", (SRC_X, SRC_Y, FACE_Z + 0.014))
    _adopt(src_piv, root)
    src_objs = []
    for o in (
        _box("log_src_ptr", (0, 0.017, 0.004), (0.008, 0.032, 0.006), brass,
             bevel=0.0015),
        _cyl("log_src_knob", (0, 0, 0.008), 0.014, 0.016, brass, verts=14,
             smooth=False),
    ):
        _adopt(o, src_piv)
        src_objs.append(o)
        far.append(o)

    # --------------------------------------- WIPE / break-glass  (states) --
    # A surface-mounted break-glass unit standing proud of the face: an open
    # brass box with a red backplate, the lever inside, glass across the front.
    ww, wh = 0.112, 0.096
    keep(_box("log_wipe_back", (WIPE_X, WIPE_Y, FACE_Z + 0.0085),
              (ww, wh, 0.005), red_m))
    for i, (cx, cy, sx, sy) in enumerate((
            (WIPE_X, WIPE_Y + wh / 2 + 0.007, ww + 0.028, 0.014),
            (WIPE_X, WIPE_Y - wh / 2 - 0.007, ww + 0.028, 0.014),
            (WIPE_X - ww / 2 - 0.007, WIPE_Y, 0.014, wh + 0.028),
            (WIPE_X + ww / 2 + 0.007, WIPE_Y, 0.014, wh + 0.028))):
        keep(_box(f"log_wipe_frame_{i}", (cx, cy, FACE_Z + 0.022),
                  (sx, sy, 0.032), brass, bevel=0.002))
    # hazard stripes on the backplate
    for i in range(4):
        keep(_box(f"log_wipe_stripe_{i}", (WIPE_X - 0.036 + 0.024 * i,
                                           WIPE_Y + 0.036, FACE_Z + 0.012),
                  (0.011, 0.014, 0.003), ink, rot=(0, 0, math.radians(28))))
    # the lamp in the corner of the box
    keep(_cyl("log_wipe_cup", (WIPE_X + 0.036, WIPE_Y - 0.032, FACE_Z + 0.013),
              0.011, 0.008, brass, verts=18))
    wipe_dome = _sphere("log_wipe_dome",
                        (WIPE_X + 0.036, WIPE_Y - 0.032, FACE_Z + 0.018),
                        0.0088, lamp_off, scale=(1, 1, 0.62))
    _adopt(wipe_dome, root)
    far.append(wipe_dome)

    # the glass cover, and the shards left when it is smashed
    pane = _box("log_wipe_pane", (WIPE_X, WIPE_Y, FACE_Z + 0.034),
                (ww + 0.010, wh + 0.010, 0.003), pane_m)
    _adopt(pane, root)
    far.append(pane)
    shards = []
    for i, (dx, dy, sx, sy, rz) in enumerate((
            (-0.038, 0.036, 0.034, 0.020, 14.0),
            (0.020, 0.040, 0.038, 0.013, -9.0),
            (0.048, 0.006, 0.016, 0.046, 6.0),
            (-0.050, -0.012, 0.013, 0.040, -11.0),
            (-0.004, -0.042, 0.048, 0.013, 8.0))):
        sh = _box(f"log_shard_{i}", (WIPE_X + dx, WIPE_Y + dy, FACE_Z + 0.034),
                  (sx, sy, 0.003), pane_m, rot=(0, 0, math.radians(rz)))
        _adopt(sh, root)
        far.append(sh)
        shards.append(sh)

    wipe_piv = _empty("log_wipe_pivot", (WIPE_X - 0.040, WIPE_Y, FACE_Z + 0.018))
    _adopt(wipe_piv, root)
    wipe_objs = []
    for o in (
        _box("log_wipe_shaft", (0.026, 0, 0.0), (0.052, 0.011, 0.009), brass,
             bevel=0.002),
        _sphere("log_wipe_knob", (0.056, 0, 0.002), 0.013, red_m,
                scale=(1, 1, 0.75)),
    ):
        _adopt(o, wipe_piv)
        wipe_objs.append(o)
        far.append(o)
    keep(_cyl("log_wipe_boss", (WIPE_X - 0.040, WIPE_Y, FACE_Z + 0.009),
              0.010, 0.008, brass, verts=18))

    # ----------------------------------------------------- resting poses ---
    t_rest = TAPE_REST / (TAPE_FRAMES - 1)
    tape_piv.location = (0, -TAPE_TRAVEL * t_rest, 0)
    ang = -TAPE_TRAVEL * t_rest / (2 * math.pi * SPOOL_R) * 2 * math.pi
    for sp in spool_pivs:
        sp.rotation_euler = (0, 0, ang)
    src_piv.rotation_euler = (0, 0, -math.radians(SRC_ANGLES[0]))
    src_domes[0].data.materials[0] = lamp_amb
    bpy.context.view_layer.update()

    # ------------------------------------------------------------ placement
    loc, eul = slots.place(P, CODE, lift=LIFT)
    root.location = loc
    root.rotation_euler = eul
    bpy.context.view_layer.update()

    return {
        "far": [o for o in far if o.type == 'MESH'],
        "plate": plate,
        "root": root,
        "controls": {
            "tape": {"objs": tape_objs, "pivot": tape_piv, "kind": "frames",
                     "label": "LOG TAPE", "frames": TAPE_FRAMES,
                     "travel": TAPE_TRAVEL, "spools": spool_pivs},
            "lens": {"objs": lens_objs, "pivot": lens_piv, "kind": "rotate",
                     "label": "SEARCH LENS", "range": list(LENS_RANGE),
                     "anchor": root.matrix_world @ Vector(
                         (LENS_X, LENS_Y, FACE_Z + 0.024))},
            "source": {"objs": src_objs + src_domes, "pivot": src_piv,
                       "kind": "states", "label": "SOURCE",
                       "states": list(SRC_STATES), "angles": list(SRC_ANGLES),
                       "domes": src_domes,
                       "mats": {"off": lamp_off, "on": lamp_amb}},
            "wipe": {"objs": wipe_objs + [pane, wipe_dome] + shards,
                     "pivot": wipe_piv, "kind": "states", "label": "WIPE",
                     "states": list(WIPE_STATES), "pane": pane,
                     "shards": shards, "dome": wipe_dome, "lever": wipe_objs,
                     "mats": {"off": lamp_off, "on": lamp_red},
                     "throw": WIPE_THROW},
        },
    }


# ------------------------------------------------------ standalone renderer
def mesh_objects(scene):
    return [o for o in scene.objects if o.type == 'MESH']


def render_to(scene, path, visible, holdout=()):
    """Render only `visible`. `holdout` objects stay in the depth buffer but
    punch alpha, so a sprite is clipped by the panel it lives behind."""
    saved, hsave = {}, {}
    vis = set(o.name for o in visible)
    hold = set(o.name for o in holdout) - vis
    for o in mesh_objects(scene):
        saved[o.name] = o.hide_render
        o.hide_render = not (o.name in vis or o.name in hold)
    for o in holdout:
        if o.name in hold:
            hsave[o.name] = o.is_holdout
            o.is_holdout = True
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in holdout:
        if o.name in hsave:
            o.is_holdout = hsave[o.name]
    for o in mesh_objects(scene):
        o.hide_render = saved[o.name]


def project(scene, cam, world_co):
    from bpy_extras.object_utils import world_to_camera_view
    co = world_to_camera_view(scene, cam, world_co)
    return (co.x * scene.render.resolution_x,
            (1.0 - co.y) * scene.render.resolution_y)


def bbox_rect(scene, cam, objs, pad=6):
    xs, ys = [], []
    for o in objs:
        for c in o.bound_box:
            x, y = project(scene, cam, o.matrix_world @ Vector(c))
            xs.append(x)
            ys.append(y)
    return {"x": round(min(xs) - pad), "y": round(min(ys) - pad),
            "w": round(max(xs) - min(xs) + 2 * pad),
            "h": round(max(ys) - min(ys) + 2 * pad)}


def union(rects):
    x0 = min(r["x"] for r in rects)
    y0 = min(r["y"] for r in rects)
    return {"x": x0, "y": y0,
            "w": max(r["x"] + r["w"] for r in rects) - x0,
            "h": max(r["y"] + r["h"] for r in rects) - y0}


def _aim(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def close_rig(root):
    """Close-up camera + local lights, all parented into the panel frame."""
    bpy.ops.object.camera_add(location=(0, 0, 0))
    cam = bpy.context.object
    cam.name = "log_closecam"
    cam.data.lens = 42.0
    _adopt(cam, root)
    # straight down the panel normal, a few degrees of downward tilt so the
    # paper tongue hanging off the console front reads in profile
    cam.location = (0.0, 0.074, 1.280)
    cam.rotation_euler = (math.radians(-5.0), 0.0, 0.0)

    lights = []
    for i, (loc, aim, energy, size, col) in enumerate([
        ((-0.36, 0.34, 0.42), (-0.10, 0.06, 0.02), 2.2, 0.28, (1.0, 0.90, 0.76)),
        ((0.46, 0.10, 0.44), (0.14, -0.02, 0.02), 1.3, 0.32, (0.72, 0.82, 1.0)),
        ((0.00, -0.40, 0.34), (0.00, -0.16, 0.05), 1.1, 0.26, (1.0, 0.86, 0.66)),
        ((-0.05, 0.46, 0.16), (0.00, 0.10, 0.02), 0.9, 0.22, (1.0, 0.84, 0.62)),
    ]):
        bpy.ops.object.light_add(type='AREA', location=(0, 0, 0))
        L = bpy.context.object
        L.name = f"log_light_{i}"
        L.data.energy, L.data.size = energy, size
        L.data.color = col
        _adopt(L, root)
        L.location = loc
        _aim(L, Vector(aim))
        lights.append(L)
    return cam, lights


def glow_render(scene, path, objs):
    """Flat white emissive silhouette for the hover glow."""
    g = _mat("log_glow", (1, 1, 1, 1), 0.0, 0.5,
             emission=(1, 1, 1, 1), emit_strength=1.0)
    saved = {}
    for o in objs:
        saved[o.name] = list(o.data.materials)
        for i in range(len(o.data.materials)):
            o.data.materials[i] = g
    vt = scene.view_settings.view_transform
    look = scene.view_settings.look
    try:
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
    except Exception:
        pass
    render_to(scene, path, objs)
    try:
        scene.view_settings.view_transform = vt
        scene.view_settings.look = look
    except Exception:
        pass
    for o in objs:
        for i, m in enumerate(saved[o.name]):
            o.data.materials[i] = m


HTML = """<!doctype html>
<meta charset="utf-8">
<title>LOG - Black Box / Flight Recorder</title>
<style>
 body{margin:0;background:#0a0c10;color:#cbb48a;
      font:13px/1.5 ui-monospace,Menlo,monospace}
 header{padding:14px 18px;border-bottom:1px solid #2a2318}
 h1{margin:0;font-size:15px;letter-spacing:.18em;color:#e2c489}
 header p{margin:6px 0 0;color:#7d7360;max-width:74ch}
 #stage{margin:14px 18px;overflow:hidden}
 #wrap{position:relative;width:1280px;height:720px;transform-origin:top left}
 #wrap img{position:absolute;left:0;top:0;width:1280px;height:720px}
 .hot{position:absolute;border:1px solid rgba(226,196,137,0);cursor:pointer}
 .hot:hover{border-color:rgba(226,196,137,.55);
            background:rgba(226,196,137,.06)}
 .hot span{position:absolute;left:0;top:-17px;font-size:10px;
           letter-spacing:.14em;color:#e2c489;opacity:0;white-space:nowrap}
 .hot:hover span{opacity:1}
 #hud{margin:0 18px 24px;padding:10px 14px;border:1px solid #2a2318;
      display:inline-block;white-space:pre}
</style>
<header>
 <h1>LOG &middot; BLACK BOX / FLIGHT RECORDER</h1>
 <p>Strip-chart recorder on the console fascia. Drag the <b>tape</b> to run the
    paper past the window (the spools turn with it); the printed tongue hanging
    out of the slot is the log you have already got. Drag the <b>magnifier</b>
    across the tape to search. Click the <b>SOURCE</b> dial to pick a log file.
    Click <b>WIPE</b> three times &mdash; break the glass, then throw the lever
    &mdash; for <code>DELETE /logs/{name}</code>.</p>
</header>
<div id="stage"><div id="wrap"></div></div>
<div id="hud"></div>
<script>
const M = __MANIFEST__;
const wrap = document.getElementById('wrap');
const hud = document.getElementById('hud');
const state = {};
const BASE = 'out/';

function img(src, z){
  const e = document.createElement('img');
  e.src = BASE + src; e.style.zIndex = z; e.draggable = false;
  wrap.appendChild(e); return e;
}
img(M.close.plate, 0);

const layers = {};
let z = 1;
for (const [id, c] of Object.entries(M.close.controls)){
  if (c.kind === 'frames'){ state[id] = 0; layers[id] = img(c.frames[0], z++); }
  else if (c.kind === 'rotate'){
    state[id] = 0;
    const e = img(c.image, z++);
    e.style.transformOrigin = c.pivot.x + 'px ' + c.pivot.y + 'px';
    layers[id] = e;
  } else {
    const keys = Object.keys(c.states);
    state[id] = keys[0];
    layers[id] = img(c.states[keys[0]], z++);
  }
}

function draw(){
  const bits = [];
  for (const [id, c] of Object.entries(M.close.controls)){
    if (c.kind === 'frames'){
      layers[id].src = BASE + c.frames[state[id]];
      bits.push(c.label + ': ' + (state[id]+1) + '/' + c.frames.length);
    } else if (c.kind === 'rotate'){
      layers[id].style.transform = 'rotate(' + state[id].toFixed(1) + 'deg)';
      const f = (state[id]-c.range[0])/(c.range[1]-c.range[0]);
      bits.push(c.label + ': ' + Math.round(f*100) + '%');
    } else {
      layers[id].src = BASE + c.states[state[id]];
      bits.push(c.label + ': ' + state[id].toUpperCase());
    }
  }
  hud.textContent = bits.join('   |   ');
}

let SC = 1;
for (const [id, c] of Object.entries(M.close.controls)){
  const h = document.createElement('div');
  h.className = 'hot';
  h.style.left = c.hotspot.x+'px'; h.style.top = c.hotspot.y+'px';
  h.style.width = c.hotspot.w+'px'; h.style.height = c.hotspot.h+'px';
  h.style.zIndex = 100 + z;
  const s = document.createElement('span'); s.textContent = c.label;
  h.appendChild(s); wrap.appendChild(h);

  if (c.kind === 'states'){
    const keys = Object.keys(c.states);
    h.onclick = () => { state[id] = keys[(keys.indexOf(state[id])+1)%keys.length];
                        draw(); };
  } else if (c.kind === 'frames'){
    const horiz = c.hotspot.w > c.hotspot.h;
    const set = ev => {
      const r = h.getBoundingClientRect();
      let f = horiz ? (ev.clientX-r.left)/r.width : (ev.clientY-r.top)/r.height;
      f = Math.max(0, Math.min(1, f));
      state[id] = Math.round(f*(c.frames.length-1)); draw();
    };
    h.onmousedown = e => { set(e); h.onmousemove = set; };
    h.onmouseup = h.onmouseleave = () => { h.onmousemove = null; };
  } else {
    const set = ev => {
      const r = wrap.getBoundingClientRect();
      const px = r.left + c.pivot.x * SC, py = r.top + c.pivot.y * SC;
      // 0deg = the arm hanging straight down from its pivot
      let a = Math.atan2(ev.clientX - px, ev.clientY - py) * 180/Math.PI;
      a = -a;
      state[id] = Math.max(c.range[0], Math.min(c.range[1], a)); draw();
    };
    h.onmousedown = e => { set(e); h.onmousemove = set; };
    h.onmouseup = h.onmouseleave = () => { h.onmousemove = null; };
  }
}

const stage = document.getElementById('stage');
function fit(){
  SC = Math.min(1, (window.innerWidth - 44) / 1280);
  wrap.style.transform = 'scale(' + SC + ')';
  stage.style.width = (1280 * SC) + 'px';
  stage.style.height = (720 * SC) + 'px';
}
window.addEventListener('resize', fit); fit();
draw();
</script>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    P = dict(shell.PARAMS)
    scene = shell.build(P)                       # UNMODIFIED shell + camera
    far_cam = scene.camera
    mats = {"brass": bpy.data.materials["brass"],
            "hull": bpy.data.materials["hull"],
            "hull_d": bpy.data.materials["hull_d"]}

    res = add_props(P, mats)
    far_objs = res["far"]
    ctl = res["controls"]
    root = res["root"]
    shell_meshes = [o for o in mesh_objects(scene) if o not in far_objs]

    # the shards are only there once the glass is smashed
    rest_far = [o for o in far_objs if o not in ctl["wipe"]["shards"]]

    # ------------------------------------------------------------- far shot
    render_to(scene, os.path.join(OUT, "far_prop.png"), rest_far)
    far_hot = bbox_rect(scene, far_cam, rest_far, pad=8)
    glow_render(scene, os.path.join(OUT, "far_glow.png"), rest_far)
    render_to(scene, os.path.join(OUT, "_shell_plate.png"), shell_meshes)

    # ----------------------------------------------------------- close shot
    cam, _lights = close_rig(root)
    scene.camera = cam
    bpy.context.view_layer.update()

    static = shell_meshes + res["plate"]
    render_to(scene, os.path.join(OUT, "close_plate.png"), static)
    clip = res["plate"]              # static prop parts that must occlude sprites

    controls = {}

    # --- LOG TAPE: paper + trace translate, spools spin -------------------
    c = ctl["tape"]
    piv, spools = c["pivot"], c["spools"]
    frames, rects = [], []
    for i in range(TAPE_FRAMES):
        t = i / (TAPE_FRAMES - 1)
        off = TAPE_TRAVEL * t
        piv.location = (0, -off, 0)
        for sp in spools:
            sp.rotation_euler = (0, 0, -off / SPOOL_R)
        bpy.context.view_layer.update()
        fn = f"close_tape_{i}.png"
        render_to(scene, os.path.join(OUT, fn), c["objs"], holdout=clip)
        frames.append(fn)
    piv.location = (0, 0, 0)
    for sp in spools:
        sp.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    # the hotspot is the WINDOW + the two spool ports, not the ribbon's full
    # (mostly hidden) extent -- computed from the panel geometry, in world space
    pad = 0.014
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            pts.append((sx * (APX + pad), APY0 if sy < 0 else APY1, FACE_Z))
            pts.append((sx * SPOOL_X + sx * 0.078, SPOOL_Y + sy * 0.078,
                        FACE_Z + 0.03))
    xs, ys = [], []
    for q in pts:
        x, y = project(scene, cam, root.matrix_world @ Vector(q))
        xs.append(x)
        ys.append(y)
    tape_hot = {"x": round(min(xs)), "y": round(min(ys)),
                "w": round(max(xs) - min(xs)), "h": round(max(ys) - min(ys))}
    controls["tape"] = {"kind": "frames", "label": "LOG TAPE",
                        "frames": frames, "hotspot": tape_hot}

    # --- SEARCH LENS: rendered once at 0, swung in CSS --------------------
    c = ctl["lens"]
    c["pivot"].rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    render_to(scene, os.path.join(OUT, "close_lens.png"), c["objs"])
    px, py = project(scene, cam, c["anchor"])
    # the grab area is everywhere the arm can SWING to (CSS deg -> blender -deg)
    rects = []
    for i in range(9):
        a = c["range"][0] + (c["range"][1] - c["range"][0]) * i / 8
        c["pivot"].rotation_euler = (0, 0, math.radians(-a))
        bpy.context.view_layer.update()
        rects.append(bbox_rect(scene, cam, c["objs"], pad=8))
    c["pivot"].rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    controls["lens"] = {"kind": "rotate", "label": "SEARCH LENS",
                        "image": "close_lens.png",
                        "pivot": {"x": round(px, 1), "y": round(py, 1)},
                        "range": c["range"],
                        "hotspot": union(rects)}

    # --- SOURCE: rotary selector + one lit lamp per source ----------------
    c = ctl["source"]
    states, rects = {}, []
    for i, nm in enumerate(c["states"]):
        c["pivot"].rotation_euler = (0, 0, -math.radians(c["angles"][i]))
        for k, d in enumerate(c["domes"]):
            d.data.materials[0] = c["mats"]["on" if k == i else "off"]
        bpy.context.view_layer.update()
        fn = f"close_source_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), c["objs"])
        states[nm] = fn
        rects.append(bbox_rect(scene, cam, c["objs"]))
    c["pivot"].rotation_euler = (0, 0, -math.radians(c["angles"][0]))
    for k, d in enumerate(c["domes"]):
        d.data.materials[0] = c["mats"]["on" if k == 0 else "off"]
    controls["source"] = {"kind": "states", "label": "SOURCE",
                          "states": states, "hotspot": union(rects)}

    # --- WIPE: sealed -> glass broken -> lever thrown ---------------------
    c = ctl["wipe"]
    states, rects = {}, []
    poses = {"sealed": ([c["pane"]], 0.0, "off"),
             "armed": (c["shards"], 0.0, "on"),
             "wiped": (c["shards"], c["throw"], "on")}
    for nm in c["states"]:
        glassbits, ang, lit = poses[nm]
        c["pivot"].rotation_euler = (0, 0, math.radians(ang))
        c["dome"].data.materials[0] = c["mats"][lit]
        bpy.context.view_layer.update()
        vis = c["lever"] + [c["dome"]] + glassbits
        fn = f"close_wipe_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), vis, holdout=clip)
        states[nm] = fn
        rects.append(bbox_rect(scene, cam, vis))
    c["pivot"].rotation_euler = (0, 0, 0)
    c["dome"].data.materials[0] = c["mats"]["off"]
    controls["wipe"] = {"kind": "states", "label": "WIPE",
                        "states": states, "hotspot": union(rects)}

    manifest = {
        "code": CODE, "name": NAME, "surface": SURFACE,
        "far": {"prop": "far_prop.png", "glow": "far_glow.png",
                "hotspot": far_hot},
        "close": {"canvas": {"w": scene.render.resolution_x,
                             "h": scene.render.resolution_y},
                  "plate": "close_plate.png", "controls": controls},
    }
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(HERE, "demo.html"), "w") as f:
        f.write(HTML.replace("__MANIFEST__", json.dumps(manifest)))

    print("LOG far hotspot", json.dumps(far_hot))
    for k, v in controls.items():
        print("LOG close", k, v["kind"], json.dumps(v["hotspot"]))
    print("LOG OK ->", OUT)


if __name__ == "__main__":
    main()
