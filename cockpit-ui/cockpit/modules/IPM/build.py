"""
IPM -- image-processing-module  ->  OPTICAL SENSOR ARRAY / PHOTO LAB
Cockpit control for the SAINTCON 2026 AppSec Challenge UI.

Slot: the PILLAR -- inboard face of column 1 (the RIGHT column, pilot's view).

    !! THE SURFACE NOTE THAT DROVE THE DESIGN !!
    slots.pillar() puts the origin exactly on the FRONT SURFACE of a 0.075 m
    radius cylinder (column axis sits at slot-local (0, y, -0.075)), and points
    local +Z at the pilot -- measured, the face normal is within 4.4 deg of the
    camera ray, so unlike the ceiling slots a flat panel here reads dead-on and
    needs no rake.  What it DOES need is narrowness: the column is only 0.15 m
    across, so the prop is 0.156 m wide and 0.70 m tall, and it sits on a
    CURVED backing block whose rear face is the cylinder itself (see prism()
    + back_section()), so nothing floats off the column or punches through it.

    Vertical budget is fenced on both ends:
      * shell's brass column collar at world z=1.96 (slot-local Y=+0.50)
      * shell's overhead console at angle 24 deg hangs to world z=1.77 and its
        screen footprint completely covers the column -- measured, its bottom
        edge lands at screen y~182, so the prop is capped at slot-local
        Y=+0.290 (screen y~198) to stay out from under it.
      * the dash surface cuts the column at world z~0.855 (slot-local Y=-0.61).
    Everything lives in Y = +0.290 .. -0.416.

The control is the ship's photo lab, read top to bottom:

    periscope head          -- pulled-down optical head on a column bracket:
                               drum, eyepiece hood + viewport, two grip bars.
    dial      (rotate)      -- SCOPE selector.  The five detents are the real
                               /convert output modes: 256 / 512 / 1K / SVG /
                               ZIP (i.e. width-height presets, the SVG metadata
                               path, and /convert-batch).  One render, spun in
                               CSS about its projected hub.
    resolver bank           -- four glowing vacuum-tube resolvers behind a
                               brass aperture.  Static.
    capture   (states)      -- the capture plunger.  armed -> capture: the rod
                               drops into its barrel and the EXPOSE lamp lights.
    tray      (frames)      -- darkroom developing tray under the safelight.
                               8 frames; a plate emerges grain by grain in a
                               deterministic scatter, in three densities of
                               silver, until the exposure is fully developed.
    chute                   -- IPM is a CLIENT of FMM: it STORs every converted
                               plate into the file server.  So the tray drains
                               into a brass plate chute that leaves the column
                               heading down and to the pilot's LEFT -- toward
                               FMM's dash slot at -40 deg -- stencilled
                               "TO FMM HOLD".  The module dependency, physical.

Run standalone:
    /Applications/Blender.app/Contents/MacOS/Blender --background --python build.py
"""
import bpy, math, os, sys, json
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
COCKPIT = os.path.dirname(os.path.dirname(HERE))
if COCKPIT not in sys.path:
    sys.path.insert(0, COCKPIT)
import shell                                                     # noqa: E402
import slots                                                     # noqa: E402

CODE = "IPM"
NAME = "Optical Sensor Array"
SURFACE = slots.SLOTS[CODE]["surface"]
OUT = os.path.join(HERE, "out")

# --------------------------------------------------------------- geometry
PR = 0.075          # column radius (must match shell PARAMS["pillar_radius"])
HB = 0.0740         # half width of the curved backing block (< PR)
ZF = 0.0120         # backing block front face, slot-local Z
PW = 0.1560         # instrument panel width
PZ = 0.0240         # panel working surface, slot-local Z
PY0, PY1 = -0.3400, 0.2560      # panel plate vertical span
# the panel is cut around the two window frames (see add_props)
PANEL_STRIPS = [(-0.0310, 0.2560), (-0.1960, -0.1070), (-0.3400, -0.3300)]

BACK_Y0, BACK_Y1 = -0.3500, 0.2660

# --- periscope head
HEAD_Y = 0.1920
HOOD_Y = 0.1800
STUB_Y0, STUB_Y1 = 0.2400, 0.2780
YOKE_Y = 0.2780

# --- nameplate
NAME_Y = 0.1120

# --- scope selector dial
DIAL_Y = 0.0340
DIAL_BEZEL, DIAL_FACE = 0.0400, 0.0320
DIAL_LABEL_R = 0.0480
DIAL_RANGE = [-125.0, 125.0]
SCOPES = ["256", "512", "1K", "SVG", "ZIP"]

# --- resolver tube bank
RES_Y = -0.0720                  # frame centre
RES_AP_Y = -0.0660               # aperture centre
RES_AP_W, RES_AP_H = 0.1320, 0.0400

# --- capture plunger
PLG_X = -0.0440
PLG_BARREL_Y = -0.1580
PLG_UP, PLG_DOWN = -0.1200, -0.1400
LAMP_X, LAMP_Y = 0.0460, -0.1300
CAPTURE_ORDER = ["armed", "capture"]

# --- developing tray
TRAY_Y = -0.2660                 # frame centre
TRAY_AP_Y = -0.2590              # aperture centre
TRAY_AP_W, TRAY_AP_H = 0.1320, 0.0980
TILE = 0.0095
DEV_FRAMES = 8
DEV_FAR = 5                      # which frame the wide shot shows

# --- chute toward FMM (down and to the pilot's LEFT = slot-local -X)
CHUTE_A = Vector((-0.0380, -0.3340, 0.0280))
CHUTE_B = Vector((-0.1520, -0.3860, 0.0280))
TAG_X, TAG_Y = -0.0980, -0.4080

# --- close-up camera
CLOSE_D = 2.025          # 50 mm lens -> 0.82 m of frame height
CLOSE_CY = -0.0650

# the developing plate: a ringed planet and two stars, 12 x 9
BITMAP = [
    "..#.........",
    ".....###....",
    "....#####...",
    "...#######..",
    "############",
    "...#######..",
    "....#####...",
    ".....###....",
    ".#........#.",
]


# --------------------------------------------------------------- primitives
def mat(name, base, metallic=0.0, rough=0.5, emission=None, strength=0.0):
    n = "ipm_" + name
    if n in bpy.data.materials:
        return bpy.data.materials[n]
    return shell.material(n, base, metallic, rough,
                          emission=emission, emit_strength=strength)


def _finish(o, name, m, rot, bevel=0.0, smooth=False):
    o.name = name
    if tuple(o.scale) != (1.0, 1.0, 1.0):
        bpy.ops.object.transform_apply(location=False, rotation=False,
                                       scale=True)
    o.rotation_euler = rot
    if bevel:
        b = o.modifiers.new("bev", 'BEVEL')
        b.width, b.segments = bevel, 2
    if smooth:
        for f in o.data.polygons:
            f.use_smooth = True
    o.data.materials.append(m)
    return o


def box(name, center, size, m, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    o = bpy.context.object
    o.scale = size
    return _finish(o, name, m, rot, bevel)


def cyl(name, center, radius, depth, m, rot=(0, 0, 0), verts=28,
        smooth=True, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                        vertices=verts, location=center)
    return _finish(bpy.context.object, name, m, rot, bevel, smooth)


def sphere(name, center, radius, m, scale=(1, 1, 1), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=22,
                                         ring_count=12, location=center)
    o = bpy.context.object
    o.scale = scale
    return _finish(o, name, m, rot, 0.0, True)


def ring(name, center, r_out, r_in, depth, m, rot=(0, 0, 0), verts=36):
    """Flat annulus -- bezels, jack collars, lamp rings."""
    vs, faces = [], []
    for i in range(verts):
        th = 2 * math.pi * i / verts
        c, s = math.cos(th), math.sin(th)
        vs += [(r_in * c, r_in * s, -depth / 2),
               (r_out * c, r_out * s, -depth / 2),
               (r_out * c, r_out * s, depth / 2),
               (r_in * c, r_in * s, depth / 2)]
    for i in range(verts):
        a, b = i * 4, ((i + 1) % verts) * 4
        faces += [(a + 0, a + 1, b + 1, b + 0), (a + 1, a + 2, b + 2, b + 1),
                  (a + 2, a + 3, b + 3, b + 2), (a + 3, a + 0, b + 0, b + 3)]
    o = shell.mesh_from(name, vs, faces, m, True)
    o.location = center
    o.rotation_euler = rot
    return o


def prism(name, section, y0, y1, m, smooth=False):
    """Extrude a closed XZ cross-section along Y.  Used for the curved backing
    block whose rear face IS the column cylinder."""
    n = len(section)
    verts = [(x, y0, z) for (x, z) in section] + \
            [(x, y1, z) for (x, z) in section]
    faces = [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range(n, 2 * n)))
    return shell.mesh_from(name, verts, faces, m, smooth)


def back_section(zf=ZF, half=HB, seg=22):
    """Flat front face at z=zf, rear face following the column cylinder."""
    th_max = math.asin(min(0.999, half / PR))
    pts = [(-half, zf), (half, zf)]
    for i in range(seg + 1):
        th = th_max - 2 * th_max * i / seg
        pts.append((PR * math.sin(th), -PR + PR * math.cos(th)))
    return pts


def rod(name, p0, p1, radius, m, verts=14):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    rot = d.to_track_quat('Z', 'Y').to_euler()
    return cyl(name, (p0 + p1) / 2, radius, d.length, m, rot=rot, verts=verts)


_FONT = [None]


def mono_font():
    if _FONT[0] is None:
        for p in ("/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
                  "/System/Library/Fonts/Menlo.ttc"):
            if os.path.exists(p):
                try:
                    _FONT[0] = bpy.data.fonts.load(p)
                    break
                except Exception:
                    pass
    return _FONT[0]


def text(name, body, size, m, loc, rot=(0, 0, 0), align='CENTER'):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.extrude = 0.00035
    f = mono_font()
    if f:
        cu.font = f
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(m)
    return o


def polytube(name, pts, radius, m):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    cu.resolution_u = 4
    cu.use_fill_caps = True
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(m)
    return o


def aperture(prefix, ac, ap_w, ap_h, rail_t, rail_b, out_w, brass, ebon, add):
    """A dark well plus a brass frame whose aperture clips its contents.
    `ac` is the APERTURE centre in local Y; the frame spans
    ac-ap_h/2-rail_b .. ac+ap_h/2+rail_t."""
    objs = []
    hw, hh = ap_w / 2.0, ap_h / 2.0
    ow = out_w / 2.0
    full_h = ap_h + rail_t + rail_b
    objs.append(add(box(prefix + "_liner",
                        (0, ac + (rail_t - rail_b) / 2, 0.0145),
                        (out_w - 0.006, full_h - 0.006, 0.006), ebon)))
    zc = PZ + 0.004
    objs.append(add(box(prefix + "_fr_t", (0, ac + hh + rail_t / 2, zc),
                        (out_w, rail_t, 0.010), brass, bevel=0.0015)))
    objs.append(add(box(prefix + "_fr_b", (0, ac - hh - rail_b / 2, zc),
                        (out_w, rail_b, 0.010), brass, bevel=0.0015)))
    for i, sx in enumerate((-1, 1)):
        objs.append(add(box(f"{prefix}_fr_s{i}",
                            (sx * (hw + (ow - hw) / 2),
                             ac + (rail_t - rail_b) / 2, zc),
                            (ow - hw, full_h, 0.010), brass, bevel=0.0015)))
    return objs


# ------------------------------------------------------- developing plate
def dev_tiles():
    """[(col,row,appear)] for every lit tile, appear in (0,1], scattered."""
    on = []
    for r, line in enumerate(BITMAP):
        for c, ch in enumerate(line):
            if ch == '#':
                on.append((c, r))
    keyed = sorted(on, key=lambda t: ((t[0] * 73856093) ^ (t[1] * 19349663)
                                      ^ ((t[0] + t[1] * 7) * 83492791)) % 100003)
    n = len(keyed)
    return [(c, r, (i + 1) / n) for i, (c, r) in enumerate(keyed)]


def dev_mesh(name, cells, m, z):
    """One merged quad soup for every tile in `cells`."""
    if not cells:
        return None
    cols, rows = len(BITMAP[0]), len(BITMAP)
    x0 = -cols * TILE / 2
    y1 = TRAY_AP_Y + rows * TILE / 2
    verts, faces = [], []
    for (c, r) in cells:
        ax, ay = x0 + c * TILE, y1 - (r + 1) * TILE
        b = len(verts)
        verts += [(ax, ay, z), (ax + TILE, ay, z),
                  (ax + TILE, ay + TILE, z), (ax, ay + TILE, z)]
        faces.append((b, b + 1, b + 2, b + 3))
    return shell.mesh_from(name, verts, faces, m, False)


# ----------------------------------------------------------------- the prop
def add_props(P, mats):
    """Add the IPM optical array / photo lab to the CURRENT scene."""
    brass = mats["brass"]
    hull_d = mats["hull_d"]

    case = mat("case", (0.050, 0.054, 0.064, 1), 0.18, 0.46)
    panel = mat("panel", (0.072, 0.076, 0.086, 1), 0.16, 0.50)
    ebon = mat("ebon", (0.024, 0.024, 0.028, 1), 0.0, 0.34)
    ivory = mat("ivory", (0.874, 0.848, 0.756, 1), 0.0, 0.60)
    ink = mat("ink", (0.052, 0.048, 0.050, 1), 0.0, 0.62)
    optic = mat("optic", (0.030, 0.055, 0.062, 1), 0.30, 0.14)
    tube_g = mat("tube_g", (0.235, 0.180, 0.098, 1), 0.10, 0.22,
                 emission=(1.0, 0.55, 0.18, 1), strength=0.45)
    tube_f = mat("tube_f", (1.0, 0.78, 0.38, 1), 0.0, 0.30,
                 emission=(1.0, 0.70, 0.30, 1), strength=9.0)
    safelight = mat("safelight", (0.640, 0.240, 0.110, 1), 0.0, 0.34,
                    emission=(1.0, 0.32, 0.12, 1), strength=3.0)
    fluid = mat("fluid", (0.140, 0.085, 0.048, 1), 0.0, 0.16,
                emission=(0.30, 0.14, 0.05, 1), strength=0.35)
    glint = mat("glint", (0.70, 0.74, 0.80, 1), 0.0, 0.20,
                emission=(0.70, 0.76, 0.86, 1), strength=0.55)
    red_off = mat("red_off", (0.150, 0.032, 0.032, 1), 0.0, 0.42)
    red_on = mat("red_on", (0.560, 0.090, 0.060, 1), 0.0, 0.46,
                 emission=(1.0, 0.18, 0.09, 1), strength=2.2)
    knob_red = mat("knob_red", (0.360, 0.055, 0.045, 1), 0.10, 0.34)
    grip_m = mat("grip", (0.090, 0.088, 0.092, 1), 0.0, 0.55)
    plate_base = mat("plate_base", (0.720, 0.698, 0.626, 1), 0.0, 0.66)
    dens = [mat("dens0", (0.520, 0.500, 0.455, 1), 0.0, 0.62),
            mat("dens1", (0.190, 0.180, 0.170, 1), 0.0, 0.58),
            mat("dens2", (0.028, 0.027, 0.030, 1), 0.0, 0.50)]

    loc, eul = slots.place(P, CODE)
    bpy.ops.object.empty_add(location=loc)
    root = bpy.context.object
    root.name = "ipm_root"
    root.rotation_euler = eul

    made = []

    def add(o):
        made.append(o)
        return o

    # ------------------------------------------------- curved backing block
    add(prism("ipm_backing", back_section(), BACK_Y0, BACK_Y1, case, True))
    # brass banding top / bottom, cut to the same cylinder profile
    for i, (y0, y1) in enumerate(((BACK_Y1 - 0.020, BACK_Y1 + 0.006),
                                  (BACK_Y0 - 0.006, BACK_Y0 + 0.020),
                                  (-0.3480, -0.3320))):
        add(prism(f"ipm_band_{i}", back_section(zf=ZF + 0.004, half=HB + 0.003),
                  y0, y1, brass, True))

    # ------------------------------------------------------- instrument face
    # NOTE: cut into strips around the two apertures.  A single slab from
    # ZF to PZ would sit in front of everything in the wells (tubes, tray,
    # plate) and the windows would render as flat grey rectangles.
    for i, (y0, y1) in enumerate(PANEL_STRIPS):
        add(box(f"ipm_panel_{i}", (0, (y0 + y1) / 2, (ZF + PZ) / 2 + 0.001),
                (PW, y1 - y0, PZ - ZF + 0.002), panel, bevel=0.0025))
    for i, sx in enumerate((-1, 1)):
        add(box(f"ipm_rail_{i}", (sx * (PW / 2 + 0.005),
                                  (PY0 + PY1) / 2, ZF + 0.008),
                (0.012, PY1 - PY0 + 0.010, 0.024), brass, bevel=0.002))

    # --------------------------------------------------------- periscope head
    # yoke bracket clamping the column, the head hangs off it
    add(box("ipm_yoke", (0, YOKE_Y, 0.014), (0.126, 0.026, 0.104), brass,
            bevel=0.004))
    add(cyl("ipm_stub", (0, (STUB_Y0 + STUB_Y1) / 2, 0.055), 0.024,
            STUB_Y1 - STUB_Y0, brass,
            rot=(math.pi / 2, 0, 0), verts=24))
    add(cyl("ipm_stub_collar", (0, STUB_Y0 + 0.006, 0.055), 0.029, 0.011,
            brass, rot=(math.pi / 2, 0, 0), verts=24))
    add(cyl("ipm_drum", (0, HEAD_Y, 0.056), 0.046, 0.128, case,
            rot=(0, math.pi / 2, 0), verts=32))
    for i, sx in enumerate((-1, 1)):
        add(cyl(f"ipm_drum_cap_{i}", (sx * 0.066, HEAD_Y, 0.056), 0.048, 0.012,
                brass, rot=(0, math.pi / 2, 0), verts=32))
    add(box("ipm_hood", (0, HOOD_Y, 0.098), (0.084, 0.058, 0.062), case,
            bevel=0.005))
    add(ring("ipm_hood_ring", (0, HOOD_Y, 0.130), 0.032, 0.024, 0.012, brass,
             verts=32))
    add(cyl("ipm_viewport", (0, HOOD_Y, 0.128), 0.026, 0.006, optic, verts=32))
    add(cyl("ipm_viewport_glint", (0.008, HOOD_Y + 0.008, 0.1315), 0.007,
            0.002, glint, verts=14))
    for i, sx in enumerate((-1, 1)):
        add(rod(f"ipm_grip_{i}", (sx * 0.070, HOOD_Y - 0.002, 0.050),
                (sx * 0.088, 0.1320, 0.078), 0.009, brass))
        add(sphere(f"ipm_grip_end_{i}", (sx * 0.088, 0.1320, 0.078), 0.012,
                   grip_m, scale=(1, 1, 0.8)))

    # -------------------------------------------------------------- nameplate
    add(box("ipm_nameplate", (0, NAME_Y, PZ + 0.003), (PW - 0.010, 0.034,
                                                       0.006), brass,
            bevel=0.0015))
    add(text("ipm_name_a", "IPM", 0.0165, ink, (0, NAME_Y + 0.008, PZ + 0.007)))
    add(text("ipm_name_b", "OPTICAL ARRAY", 0.0105, ink,
             (0, NAME_Y - 0.009, PZ + 0.007)))

    # ------------------------------------------------------ scope select dial
    dial_static = []
    dial_static.append(add(ring("ipm_dial_bezel", (0, DIAL_Y, PZ + 0.007),
                                DIAL_BEZEL, DIAL_FACE - 0.002, 0.014, brass,
                                verts=40)))
    dial_static.append(add(cyl("ipm_dial_face", (0, DIAL_Y, PZ + 0.005),
                               DIAL_FACE, 0.006, ivory, verts=40)))
    for i, lab in enumerate(SCOPES):
        th = math.radians(DIAL_RANGE[0] + (DIAL_RANGE[1] - DIAL_RANGE[0])
                          * i / (len(SCOPES) - 1))
        tx = math.sin(th) * 0.0250
        ty = math.cos(th) * 0.0250
        dial_static.append(add(box(
            f"ipm_dial_tick_{i}", (tx, DIAL_Y + ty, PZ + 0.0100),
            (0.0022, 0.0090, 0.0014), ink,
            rot=(0, 0, -th))))
        lx = math.sin(th) * DIAL_LABEL_R
        ly = math.cos(th) * DIAL_LABEL_R
        dial_static.append(add(text(f"ipm_dial_lab_{i}", lab, 0.0130, ivory,
                                    (lx, DIAL_Y + ly, PZ + 0.0035))))
    dial_static.append(add(text("ipm_dial_cap", "SCOPE", 0.0150, ivory,
                                (0, -0.0200, PZ + 0.0035))))

    # the selector knob is rendered ONCE pointing up; the browser spins it
    knob = []
    knob.append(add(cyl("ipm_dial_hub", (0, DIAL_Y, PZ + 0.014), 0.0105, 0.010,
                        brass, verts=20)))
    knob.append(add(box("ipm_dial_bar", (0, DIAL_Y + 0.004, PZ + 0.018),
                        (0.0110, 0.0500, 0.0080), brass, bevel=0.0015)))
    knob.append(add(box("ipm_dial_index", (0, DIAL_Y + 0.0230, PZ + 0.023),
                        (0.0088, 0.0090, 0.0026), red_on)))
    DIAL_ANCHOR = Vector((0, DIAL_Y, PZ + 0.020))

    # --------------------------------------------------- vacuum-tube resolvers
    aperture("ipm_res", RES_AP_Y, RES_AP_W, RES_AP_H, 0.0150, 0.0210, PW,
             brass, ebon, add)
    add(text("ipm_res_cap", "RESOLVER", 0.0135, ink,
             (0, RES_Y - 0.0245, PZ + 0.010)))
    for i, tx in enumerate((-0.0510, -0.0170, 0.0170, 0.0510)):
        add(cyl(f"ipm_vt_socket_{i}", (tx, RES_AP_Y - 0.0165, 0.0230), 0.0120,
                0.008, brass, rot=(math.pi / 2, 0, 0), verts=18))
        add(cyl(f"ipm_vt_glass_{i}", (tx, RES_AP_Y + 0.0025, 0.0230), 0.0095,
                0.030, tube_g, rot=(math.pi / 2, 0, 0), verts=18))
        add(sphere(f"ipm_vt_dome_{i}", (tx, RES_AP_Y + 0.0175, 0.0230), 0.0095,
                   tube_g, scale=(1, 0.7, 1), rot=(math.pi / 2, 0, 0)))
        add(box(f"ipm_vt_fil_{i}", (tx, RES_AP_Y + 0.0010, 0.0310),
                (0.0022, 0.0180, 0.0022), tube_f))

    # --------------------------------------------------------- capture plunger
    add(box("ipm_plg_bracket", (PLG_X, PLG_BARREL_Y, PZ + 0.006),
            (0.052, 0.040, 0.008), brass, bevel=0.002))
    add(cyl("ipm_plg_barrel", (PLG_X, PLG_BARREL_Y, 0.040), 0.0170, 0.0340,
            case, rot=(math.pi / 2, 0, 0), verts=22))
    add(cyl("ipm_plg_collar", (PLG_X, PLG_BARREL_Y + 0.0155, 0.040), 0.0195,
            0.0090, brass, rot=(math.pi / 2, 0, 0), verts=22))
    add(text("ipm_plg_cap", "CAPTURE", 0.0120, ivory,
             (PLG_X, -0.1890, PZ + 0.0035)))
    add(ring("ipm_lamp_ring", (LAMP_X, LAMP_Y, PZ + 0.006), 0.0185, 0.0130,
             0.012, brass, verts=26))
    add(text("ipm_lamp_cap", "EXPOSE", 0.0120, ivory,
             (LAMP_X, -0.1600, PZ + 0.0035)))

    # moving parts of the plunger, parented to a slider empty
    bpy.ops.object.empty_add(location=(0, 0, 0))
    slider = bpy.context.object
    slider.name = "ipm_plunger_slider"
    plunger = []
    plunger.append(cyl("ipm_plg_rod", (PLG_X, PLG_UP - 0.0150, 0.040), 0.0068,
                       0.0300, brass, rot=(math.pi / 2, 0, 0), verts=16))
    plunger.append(sphere("ipm_plg_knob", (PLG_X, PLG_UP, 0.040), 0.0175,
                          knob_red, scale=(1, 0.62, 1),
                          rot=(math.pi / 2, 0, 0)))
    plunger.append(cyl("ipm_plg_knob_band", (PLG_X, PLG_UP - 0.0075, 0.040),
                       0.0150, 0.0050, brass, rot=(math.pi / 2, 0, 0),
                       verts=20))
    for o in plunger:
        o.parent = slider
        o.matrix_parent_inverse = Matrix.Identity(4)
    lamp = sphere("ipm_lamp_dome", (LAMP_X, LAMP_Y, PZ + 0.010), 0.0145,
                  red_off, scale=(1, 1, 0.62))
    for o in plunger + [lamp, slider]:
        add(o)

    # ------------------------------------------------------- developing tray
    aperture("ipm_tray", TRAY_AP_Y, TRAY_AP_W, TRAY_AP_H, 0.0140, 0.0220, PW,
             brass, ebon, add)
    add(text("ipm_tray_cap", "DEVELOPING", 0.0135, ink,
             (0.0300, TRAY_Y - 0.0530, PZ + 0.010)))
    add(box("ipm_tray_pan", (0, TRAY_AP_Y, 0.0205),
            (TRAY_AP_W - 0.004, TRAY_AP_H - 0.004, 0.007), brass,
            bevel=0.0015))
    add(box("ipm_tray_fluid", (0, TRAY_AP_Y, 0.0250),
            (TRAY_AP_W - 0.012, TRAY_AP_H - 0.012, 0.002), fluid))
    add(box("ipm_tray_plate", (0, TRAY_AP_Y, 0.0265),
            (0.1180, 0.0895, 0.0020), plate_base))
    # safelight above the tray, on the frame's top rail
    add(ring("ipm_safelight_ring", (0.0560, TRAY_Y + 0.0570, PZ + 0.0120),
             0.0130, 0.0090, 0.010, brass, verts=20))
    add(sphere("ipm_safelight", (0.0560, TRAY_Y + 0.0570, PZ + 0.0140), 0.0100,
               safelight, scale=(1, 1, 0.6)))
    # two thin glints so the aperture reads as glazed
    add(box("ipm_tray_glint", (-0.0480, TRAY_AP_Y + 0.0130, PZ + 0.0060),
            (0.0018, 0.0560, 0.0014), glint, rot=(0, 0, math.radians(30))))

    # the plate emerging, one merged mesh per density per frame
    cells = dev_tiles()
    dev_sets = []
    for f in range(DEV_FRAMES):
        thr = 1.55 * f / (DEV_FRAMES - 1)
        buckets = [[], [], []]
        for (c, r, a) in cells:
            d = thr - a
            if d < 0.0:
                continue
            buckets[2 if d >= 0.52 else (1 if d >= 0.24 else 0)].append((c, r))
        objs = []
        for li, cl in enumerate(buckets):
            o = dev_mesh(f"ipm_dev_{f}_{li}", cl, dens[li], 0.0285)
            if o is not None:
                objs.append(o)
        for o in objs:
            if f != DEV_FAR:
                o.hide_render = True
            add(o)
        dev_sets.append(objs)

    # ---------------------------------------------- plate chute -> FMM hold
    # IPM STORs every converted plate into the file server; the chute leaves
    # the column heading down and to the pilot's LEFT, toward FMM's dash slot.
    n = 18
    c1 = CHUTE_A + Vector((-0.030, -0.042, 0.0))
    c2 = CHUTE_B + Vector((0.052, 0.024, 0.0))
    pts = []
    for k in range(n):
        t = k / (n - 1)
        m_ = 1 - t
        pts.append(CHUTE_A * (m_ ** 3) + c1 * (3 * m_ * m_ * t)
                   + c2 * (3 * m_ * t * t) + CHUTE_B * (t ** 3))
    add(polytube("ipm_chute", pts, 0.0145, brass))
    add(box("ipm_chute_neck", (CHUTE_A.x, CHUTE_A.y + 0.010, CHUTE_A.z - 0.004),
            (0.042, 0.020, 0.030), brass, bevel=0.002))
    dv = (CHUTE_B - pts[-3])
    add(ring("ipm_chute_mouth", CHUTE_B, 0.0230, 0.0125, 0.010, brass,
             rot=dv.to_track_quat('Z', 'Y').to_euler(), verts=24))
    add(box("ipm_tag", (TAG_X, TAG_Y, 0.020), (0.070, 0.017, 0.004), brass,
            bevel=0.0012))
    add(text("ipm_tag_txt", "TO FMM HOLD", 0.0092, ink,
             (TAG_X, TAG_Y, 0.0235)))
    add(rod("ipm_tag_stem", (TAG_X + 0.012, TAG_Y + 0.007, 0.020),
            (TAG_X + 0.022, TAG_Y + 0.022, 0.024), 0.0030, brass, verts=8))

    # ------------------------------------------------------------ parenting
    for o in made:
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()

    # text/curves -> mesh so a mesh-only combiner still sees lettering
    conv = [o for o in made if o.type in ('FONT', 'CURVE')]
    if conv:
        bpy.ops.object.select_all(action='DESELECT')
        for o in conv:
            o.select_set(True)
        bpy.context.view_layer.objects.active = conv[0]
        bpy.ops.object.convert(target='MESH')
        bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.update()

    moving = set(knob) | set(plunger) | {lamp}
    for objs in dev_sets:
        moving |= set(objs)
    static = [o for o in made if o not in moving and o.type != 'EMPTY']
    far = static + knob + plunger + [lamp] + list(dev_sets[DEV_FAR])

    controls = {
        "dial": {"kind": "rotate", "label": "SCOPE SELECT", "objs": knob,
                 "pivot": None, "anchor": DIAL_ANCHOR, "range": DIAL_RANGE,
                 "detents": SCOPES, "hotspot_objs": dial_static + knob},
        "capture": {"kind": "states", "label": "CAPTURE PLUNGER",
                    "objs": plunger + [lamp], "pivot": slider,
                    "slider": slider, "lamp": lamp, "plunger": plunger,
                    "order": CAPTURE_ORDER, "travel": PLG_DOWN - PLG_UP,
                    "mats": {"off": red_off, "on": red_on}},
        "tray": {"kind": "frames", "label": "DEVELOPING TRAY",
                 "objs": [o for s in dev_sets for o in s],
                 "frame_objs": dev_sets, "pivot": None,
                 "hotspot_pts": [(dx * (TRAY_AP_W / 2 + 0.004),
                                  TRAY_AP_Y + dy * (TRAY_AP_H / 2 + 0.004),
                                  0.020)
                                 for dx in (-1, 1) for dy in (-1, 1)]},
    }
    return {"far": far, "controls": controls, "root": root,
            "static": static, "all": made}


# ======================================================== render harness
RTYPES = {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}


def renderables(scene):
    return [o for o in scene.objects if o.type in RTYPES]


def render_to(scene, path, visible, holdout=()):
    """Render only `visible`; `holdout` objects stay in the depth buffer but
    punch alpha, so a sprite is correctly clipped by geometry in front of it."""
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
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in holdout:
        if o.name in hsave:
            o.is_holdout = hsave[o.name]
    for o in renderables(scene):
        o.hide_render = saved[o.name]


def project(scene, cam, world_co):
    from bpy_extras.object_utils import world_to_camera_view
    co = world_to_camera_view(scene, cam, world_co)
    return (co.x * scene.render.resolution_x,
            (1.0 - co.y) * scene.render.resolution_y)


def bbox_rect(scene, cam, objs, pad=6):
    xs, ys = [], []
    for o in objs:
        if o.type not in RTYPES:
            continue
        for c in o.bound_box:
            x, y = project(scene, cam, o.matrix_world @ Vector(c))
            xs.append(x)
            ys.append(y)
    return {"x": round(min(xs) - pad), "y": round(min(ys) - pad),
            "w": round(max(xs) - min(xs) + 2 * pad),
            "h": round(max(ys) - min(ys) + 2 * pad)}


def pts_rect(scene, cam, root, pts, pad=6):
    xs, ys = [], []
    for p in pts:
        x, y = project(scene, cam, root.matrix_world @ Vector(p))
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


def clamp_rect(r, w, h):
    x0, y0 = max(0, r["x"]), max(0, r["y"])
    x1, y1 = min(w, r["x"] + r["w"]), min(h, r["y"] + r["h"])
    return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}


def glow_render(scene, path, objs, holdout=()):
    g = shell.material("ipm_glowmask", (1, 1, 1, 1), 0.0, 0.5,
                       emission=(1, 1, 1, 1), emit_strength=1.0)
    saved = {}
    for o in objs:
        if o.type not in RTYPES or not hasattr(o.data, "materials"):
            continue
        saved[o.name] = list(o.data.materials)
        for i in range(len(o.data.materials)):
            o.data.materials[i] = g
    vt, look = scene.view_settings.view_transform, scene.view_settings.look
    try:
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
    except Exception:
        pass
    render_to(scene, path, objs, holdout=holdout)
    try:
        scene.view_settings.view_transform = vt
        scene.view_settings.look = look
    except Exception:
        pass
    for o in objs:
        if o.name in saved:
            for i, m in enumerate(saved[o.name]):
                o.data.materials[i] = m


def close_rig(root):
    """Close-up camera + local lights, parented into the slot frame.  The slot
    normal already points at the pilot, so the camera just backs straight off
    it along local +Z; the shell (column, dash, window band, ceiling) fills the
    wide sides of the 16:9 frame, so the panel reads as part of the ship."""
    bpy.ops.object.camera_add(location=(0, 0, 0))
    cam = bpy.context.object
    cam.name = "ipm_closecam"
    cam.data.lens = 50.0
    cam.parent = root
    cam.matrix_parent_inverse = Matrix.Identity(4)
    cam.location = (0.0, CLOSE_CY, CLOSE_D)
    cam.rotation_euler = (0.0, 0.0, 0.0)

    lights = []
    for i, (lp, energy, size, col) in enumerate([
            ((-0.34, 0.22, 0.46), 0.26, 0.30, (1.00, 0.90, 0.74)),
            ((0.36, -0.02, 0.44), 0.20, 0.32, (0.74, 0.83, 1.00)),
            ((0.04, -0.40, 0.34), 0.15, 0.26, (1.00, 0.86, 0.66)),
            ((-0.06, 0.40, 0.26), 0.11, 0.24, (1.00, 0.84, 0.62))]):
        bpy.ops.object.light_add(type='AREA', location=(0, 0, 0))
        L = bpy.context.object
        L.name = f"ipm_light_{i}"
        L.data.energy, L.data.size = energy, size
        L.data.color = col
        L.parent = root
        L.matrix_parent_inverse = Matrix.Identity(4)
        L.location = lp
        d = Vector((lp[0] * 0.2, lp[1] * 0.2, 0.0)) - Vector(lp)
        L.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        lights.append(L)
    return cam, lights


HTML = """<!doctype html>
<meta charset="utf-8">
<title>IPM - Optical Sensor Array / Photo Lab</title>
<style>
 body{margin:0;background:#0a0c10;color:#cbb48a;
      font:13px/1.5 ui-monospace,Menlo,monospace}
 header{padding:14px 18px;border-bottom:1px solid #2a2318}
 h1{margin:0;font-size:15px;letter-spacing:.18em;color:#e2c489}
 header p{margin:6px 0 0;color:#7d7360;max-width:82ch}
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
 <h1>IPM &middot; OPTICAL SENSOR ARRAY / PHOTO LAB</h1>
 <p>Bracketed to the starboard column: a pulled-down periscope head over the
    ship's darkroom. Turn the <b>SCOPE</b> dial to pick the output
    mode &mdash; 256 / 512 / 1K / SVG / ZIP, i.e. the <code>/convert</code>
    size presets, the SVG metadata path and <code>/convert-batch</code>.
    Click the <b>CAPTURE</b> plunger to fire the shutter (the EXPOSE lamp
    lights). Drag down the <b>DEVELOPING TRAY</b> to bring the plate up under
    the safelight. Finished plates drain down the brass chute stencilled
    <code>TO FMM HOLD</code> &mdash; IPM STORs everything it converts into the
    Cargo Bay.</p>
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
    state[id] = c.range[0];
    const e = img(c.image, z++);
    e.style.transformOrigin = c.pivot.x + 'px ' + c.pivot.y + 'px';
    layers[id] = e;
  } else {
    const keys = c.order || Object.keys(c.states);
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
      let lab = '';
      if (c.detents){
        const f = (state[id]-c.range[0])/(c.range[1]-c.range[0]);
        lab = ' ' + c.detents[Math.round(f*(c.detents.length-1))];
      }
      bits.push(c.label + ':' + lab);
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
    const keys = c.order || Object.keys(c.states);
    h.onclick = () => { state[id] = keys[(keys.indexOf(state[id])+1)%keys.length];
                        draw(); };
  } else if (c.kind === 'frames'){
    // NOTE: the tray hotspot is wider than tall but the plate develops on a
    // VERTICAL drag; the axis is declared in the manifest, never inferred.
    const horiz = (c.axis || 'y') === 'x';
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
      let a = Math.atan2(ev.clientX - px, py - ev.clientY) * 180/Math.PI;
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
    scene = shell.build(P)                     # UNMODIFIED shell + main camera
    far_cam = scene.camera
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    res = add_props(P, mats)
    scene.render.film_transparent = True
    mine = set(res["all"])
    far_objs = [o for o in res["far"] if o.type in RTYPES]
    ctl = res["controls"]
    root = res["root"]
    W, H = scene.render.resolution_x, scene.render.resolution_y
    shell_meshes = [o for o in renderables(scene) if o not in mine]

    # ------------------------------------------------------------- far shot
    # holdout the WHOLE shell: the column collars, ceiling rib and the
    # overhead console at 24 deg all sit in front of parts of this prop, so
    # they must punch alpha out of the sprite AND out of the glow mask.
    render_to(scene, os.path.join(OUT, "far_prop.png"), far_objs,
              holdout=shell_meshes)
    far_hot = clamp_rect(bbox_rect(scene, far_cam, far_objs, pad=6), W, H)
    glow_render(scene, os.path.join(OUT, "far_glow.png"), far_objs,
                holdout=shell_meshes)
    render_to(scene, os.path.join(OUT, "_shell_plate.png"), shell_meshes)

    # ----------------------------------------------------------- close shot
    cam, _lights = close_rig(root)
    scene.camera = cam
    bpy.context.view_layer.update()

    static = [o for o in res["static"] if o.type in RTYPES]
    render_to(scene, os.path.join(OUT, "close_plate.png"),
              shell_meshes + static)
    clip = static

    controls = {}

    # --- DIAL: one render, spun in CSS about its projected hub ------------
    c = ctl["dial"]
    render_to(scene, os.path.join(OUT, "close_dial.png"), c["objs"],
              holdout=clip)
    px, py = project(scene, cam, root.matrix_world @ c["anchor"])
    controls["dial"] = {
        "kind": "rotate", "label": c["label"], "image": "close_dial.png",
        "pivot": {"x": round(px, 1), "y": round(py, 1)}, "range": c["range"],
        "detents": c["detents"],
        "hotspot": clamp_rect(bbox_rect(scene, cam, c["hotspot_objs"], pad=8),
                              W, H)}

    # --- CAPTURE PLUNGER: rod drops, EXPOSE lamp lights ------------------
    c = ctl["capture"]
    slider, lamp = c["slider"], c["lamp"]
    states, rects = {}, []
    for nm in c["order"]:
        slider.location = (0.0, c["travel"] if nm == "capture" else 0.0, 0.0)
        lamp.data.materials[0] = c["mats"]["on" if nm == "capture" else "off"]
        bpy.context.view_layer.update()
        fn = f"close_capture_{nm}.png"
        vis = c["plunger"] + [lamp]
        render_to(scene, os.path.join(OUT, fn), vis, holdout=clip)
        states[nm] = fn
        rects.append(bbox_rect(scene, cam, vis, pad=10))
    slider.location = (0.0, 0.0, 0.0)
    lamp.data.materials[0] = c["mats"]["off"]
    bpy.context.view_layer.update()
    controls["capture"] = {
        "kind": "states", "label": c["label"], "states": states,
        "order": c["order"], "hotspot": clamp_rect(union(rects), W, H)}

    # --- DEVELOPING TRAY: a frame per stage of development ---------------
    c = ctl["tray"]
    frames = []
    for fi, objs in enumerate(c["frame_objs"]):
        fn = f"close_tray_{fi}.png"
        render_to(scene, os.path.join(OUT, fn), objs, holdout=clip)
        frames.append(fn)
    controls["tray"] = {
        "kind": "frames", "label": c["label"], "frames": frames, "axis": "y",
        "hotspot": clamp_rect(pts_rect(scene, cam, root, c["hotspot_pts"],
                                       pad=8), W, H)}

    manifest = {
        "code": CODE, "name": NAME, "surface": SURFACE,
        "far": {"prop": "far_prop.png", "glow": "far_glow.png",
                "hotspot": far_hot},
        "close": {"canvas": {"w": W, "h": H}, "plate": "close_plate.png",
                  "controls": controls},
    }
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(HERE, "demo.html"), "w") as f:
        f.write(HTML.replace("__MANIFEST__", json.dumps(manifest)))

    print("IPM far hotspot", json.dumps(far_hot))
    for k, v in controls.items():
        print("IPM close", k, v["kind"], json.dumps(v["hotspot"]))
    print("IPM OK ->", OUT)


if __name__ == "__main__":
    main()
