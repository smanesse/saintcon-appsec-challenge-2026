"""
OTA -- ota-module  ->  FLEET REPLICATOR GRID / DRONE BAY
Cockpit control for the SAINTCON 2026 AppSec Challenge UI.

Slot: the PILLAR -- inboard face of column 0 (the LEFT column, at -27 deg).

    !! THE SURFACE NOTE THAT DROVE THE WHOLE DESIGN !!
    slots.pillar() puts the origin exactly ON the column's inboard surface and
    aims local +Z at the pilot (measured: the slot normal is within 1.0 deg of
    the camera ray).  So unlike the ceiling slots this face is dead-on -- the
    problem is not the ANGLE, it is the WIDTH.  The column is a smooth cylinder
    of radius 0.075 m: 0.15 m across, and its surface falls away as
        z(x) = sqrt(0.075^2 - x^2) - 0.075
    so a flat plate 0.10 m wide laid on the origin plane already buries its own
    edges 19 mm inside the column.  Two ways out: curve the backing, or stand
    the backing OFF the column and carry it on clamps.  This prop does the
    second, because a drone rack should look bolted on, not painted on:

      * the working face is a flat plate at z = +0.030, i.e. 30 mm proud of the
        column's nearest point, so NOTHING intersects the cylinder;
      * it is carried by six brass collars that genuinely wrap the column
        (inner radius 0.078 vs the column's 0.075).  Four sit behind the plate
        with arms reaching out past the side cheeks as visible bolt tabs; two
        more sit on the NAKED column just above and below the plate, because
        those are the only ones the eye can actually watch grip the cylinder;
      * total width is 0.216 m against a 0.15 m column: 44% overhang, which
        reads as a rack on a post rather than a billboard;
      * height is 0.63 m, spanning world z 1.105..1.735.  The shell's brass
        collars sit at z 0.10 / 0.30 / 1.96 / 2.16, so the nearest is 0.205 m
        clear.  The dash face crosses the column at z ~0.90, well below.
      * the back halves of the clamp collars are BEHIND the column, so the
        column must occlude them -- see the holdout note in render_to().

The control is a fleet replicator / drone bay:

    cartridge (frames)  -- POST /publish.  A tape-reel cartridge is presented
                           above the replicator throat and slid DOWN into it;
                           7 frames, the last two latch and light LOADED.
    propagate (frames)  -- the update running down the rack.  14 chevrons in a
                           recessed spine channel, 9 frames, leading pip hot.
    fleet     (states)  -- the three cradles.  OTA's fleet is exactly
                           {fmm, ipm, log} (its README pins that list), so one
                           cradle each: a docked probe with a status beacon and
                           a flip-dot version board.  States roll the version
                           down the rack: stale -> roll1 -> roll2 -> synced.
    poll      (rotate)  -- POLL INTERVAL dial: how often an agent hits
                           GET /updates/{module}/latest.  One render, spun in
                           CSS about the projected hub.

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

CODE = "OTA"
NAME = "Fleet Replicator Grid"
SURFACE = slots.SLOTS[CODE]["surface"]
OUT = os.path.join(HERE, "out")

# ------------------------------------------------------------------ layout
# Local frame (slots.py convention): +X right, +Y up, +Z out at the pilot.
# The origin sits ON the column surface; the column axis is at (0, y, -CR).
CR = 0.075                 # column radius (== P["pillar_radius"])
FRONT = 0.030              # working face plane: 30 mm proud of the column
HW = 0.108                 # half width of the rack
Y_TOP, Y_BOT = 0.315, -0.315

STRAP_Y = (0.292, 0.126, -0.128, -0.300)
BARE_Y = (0.352, -0.352)   # collars on the naked column, above/below the plate

# --- replicator head (top)
HEAD_Y0, HEAD_Y1 = 0.120, 0.315
HEAD_Z = 0.062                       # front face of the head blocks
THR_X0, THR_X1 = -0.100, -0.012      # loading throat opening
THR_FLOOR = 0.190                    # cartridge rests here
CART_W, CART_H, CART_T = 0.076, 0.062, 0.020
CART_X = (THR_X0 + THR_X1) / 2
CART_SEAT_Y = THR_FLOOR + CART_H / 2
CART_LIFT = 0.140
CART_FRAMES = 7
LATCH_XY = (CART_X, 0.166)

DIAL_X, DIAL_Y = 0.050, 0.245
DIAL_BEZEL, DIAL_FACE = 0.046, 0.038
POLL_RANGE = [-125.0, 125.0]
POLL_FAR_DEG = -35.0                 # needle angle baked into the wide shot

# --- propagation spine (right edge)
SP_X, SP_W = 0.099, 0.014
CHEV_N = 14
CHEV_Y0, CHEV_Y1 = 0.100, -0.288
PROP_FRAMES = 9
PROP_FAR = 6

# --- cradles
CRADLE_Y = (0.048, -0.078, -0.204)
FLEET = ("FMM", "IPM", "LOG")        # OTA's fixed fleet: fmm / ipm / log
VER_OLD, VER_NEW = "1.4.2", "1.5.0"
FLEET_ORDER = ("stale", "roll1", "roll2", "synced")
FLEET_DONE = {"stale": 0, "roll1": 1, "roll2": 2, "synced": 3}
FLEET_FAR = "roll2"
BOARD_X, BOARD_W, BOARD_H = 0.034, 0.108, 0.056

FOOT_Y = -0.290


# --------------------------------------------------------------- primitives
def _finish(o, name, mat, rot, bevel=0.0, smooth=False):
    o.name = name
    if tuple(o.scale) != (1.0, 1.0, 1.0):
        bpy.ops.object.transform_apply(location=False, rotation=False,
                                       scale=True)
    o.rotation_euler = rot
    if bevel:
        m = o.modifiers.new("bev", 'BEVEL')
        m.width, m.segments = bevel, 2
    if smooth:
        for f in o.data.polygons:
            f.use_smooth = True
    o.data.materials.append(mat)
    return o


def box(name, center, size, mat, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    o = bpy.context.object
    o.scale = size
    return _finish(o, name, mat, rot, bevel)


def cyl(name, center, radius, depth, mat, rot=(0, 0, 0), verts=28,
        smooth=True, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                        vertices=verts, location=center)
    return _finish(bpy.context.object, name, mat, rot, bevel, smooth)


def cone(name, center, r0, r1, depth, mat, rot=(0, 0, 0), verts=20):
    bpy.ops.mesh.primitive_cone_add(radius1=r0, radius2=r1, depth=depth,
                                    vertices=verts, location=center)
    return _finish(bpy.context.object, name, mat, rot, False, True)


def sphere(name, center, radius, mat, scale=(1, 1, 1), seg=22, ring=12):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=seg,
                                         ring_count=ring, location=center)
    o = bpy.context.object
    o.scale = scale
    return _finish(o, name, mat, (0, 0, 0), 0.0, True)


def tube(name, center, r_out, r_in, depth, mat, rot=(0, 0, 0), verts=44):
    """A box-section annulus, built from pydata so there is no boolean to fail."""
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
        faces.append((a + 0, a + 1, b + 1, b + 0))
        faces.append((a + 1, a + 2, b + 2, b + 1))
        faces.append((a + 2, a + 3, b + 3, b + 2))
        faces.append((a + 3, a + 0, b + 0, b + 3))
    o = shell.mesh_from(name, vs, faces, mat, True)
    o.location = center
    o.rotation_euler = rot
    return o


def tri_down(name, cx, cy, w, h, z, mat):
    """A chevron: a small triangle pointing down the spine."""
    vs = [(cx - w / 2, cy + h / 2, z), (cx + w / 2, cy + h / 2, z),
          (cx, cy - h / 2, z)]
    return shell.mesh_from(name, vs, [(0, 1, 2)], mat, False)


def bez_frame(name, cx, cy, w, h, z0, z1, mat, bar=0.005):
    """Four brass bars forming a picture frame, so the face inside can be
    RECESSED behind it.  A solid slab bezel would simply bury the face."""
    zc, zd = (z0 + z1) / 2, z1 - z0
    out = []
    out.append(box(f"{name}_t", (cx, cy + h / 2 - bar / 2, zc),
                   (w, bar, zd), mat, bevel=0.0015))
    out.append(box(f"{name}_b", (cx, cy - h / 2 + bar / 2, zc),
                   (w, bar, zd), mat, bevel=0.0015))
    out.append(box(f"{name}_l", (cx - w / 2 + bar / 2, cy, zc),
                   (bar, h - 2 * bar, zd), mat, bevel=0.0015))
    out.append(box(f"{name}_r", (cx + w / 2 - bar / 2, cy, zc),
                   (bar, h - 2 * bar, zd), mat, bevel=0.0015))
    return out


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


def text(name, body, size, mat, loc, align='CENTER', to_mesh=True):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.extrude = 0.0004
    f = mono_font()
    if f:
        cu.font = f
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.data.materials.append(mat)
    if to_mesh:
        try:
            bpy.ops.object.select_all(action='DESELECT')
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.convert(target='MESH')
            o = bpy.data.objects.get(name) or o
        except Exception:
            pass
    return o


def mat(name, base, metallic=0.0, rough=0.5, emission=None, strength=0.0):
    return shell.material("ota_" + name, base, metallic, rough,
                          emission=emission, emit_strength=strength)


# ----------------------------------------------------------------- the prop
def add_props(P, mats):
    """Add the OTA fleet replicator rack to the CURRENT scene."""
    brass = mats["brass"]
    hull = mats["hull"]
    hull_d = mats["hull_d"]

    case = mat("case", (0.050, 0.054, 0.064, 1), 0.18, 0.46)
    ebon = mat("ebon", (0.024, 0.026, 0.030, 1), 0.0, 0.34)
    slate = mat("slate", (0.118, 0.126, 0.140, 1), 0.14, 0.50)
    ivory = mat("ivory", (0.872, 0.848, 0.760, 1), 0.0, 0.60)
    ink = mat("ink", (0.052, 0.048, 0.050, 1), 0.0, 0.62)
    steel = mat("steel", (0.300, 0.320, 0.350, 1), 0.85, 0.34)
    tape_m = mat("tape", (0.140, 0.085, 0.058, 1), 0.0, 0.62)
    glassy = mat("glassy", (0.017, 0.038, 0.030, 1), 0.0, 0.22)

    amber_off = mat("amber_off", (0.150, 0.095, 0.028, 1), 0.0, 0.42)
    amber_on = mat("amber_on", (0.720, 0.400, 0.045, 1), 0.0, 0.34,
                   emission=(1.0, 0.44, 0.03, 1), strength=0.90)
    grn_off = mat("grn_off", (0.035, 0.080, 0.050, 1), 0.0, 0.42)
    grn_on = mat("grn_on", (0.100, 0.620, 0.230, 1), 0.0, 0.38,
                 emission=(0.10, 1.0, 0.26, 1), strength=0.90)
    red_on = mat("red_on", (0.520, 0.080, 0.055, 1), 0.0, 0.44,
                 emission=(1.0, 0.18, 0.10, 1), strength=1.6)
    dot_old = mat("dot_old", (0.700, 0.380, 0.040, 1), 0.0, 0.40,
                  emission=(1.0, 0.42, 0.02, 1), strength=0.80)
    dot_new = mat("dot_new", (0.090, 0.600, 0.220, 1), 0.0, 0.40,
                  emission=(0.08, 1.0, 0.24, 1), strength=0.80)
    chev_off = mat("chev_off", (0.038, 0.033, 0.026, 1), 0.0, 0.58)
    chev_on = mat("chev_on", (0.480, 0.290, 0.060, 1), 0.0, 0.38,
                  emission=(1.0, 0.46, 0.06, 1), strength=0.95)
    chev_hot = mat("chev_hot", (0.780, 0.600, 0.230, 1), 0.0, 0.30,
                   emission=(1.0, 0.80, 0.30, 1), strength=2.1)

    loc, eul = slots.place(P, CODE)
    bpy.ops.object.empty_add(location=loc)
    root = bpy.context.object
    root.name = "ota_root"
    root.rotation_euler = eul

    made = []

    def add(o):
        made.append(o)
        return o

    # ------------------------------------------------- clamps onto the column
    # Four brass U-collars that genuinely wrap the cylinder (inner r 0.078 vs
    # the column's 0.075) with arms out to the side cheeks.  Their back halves
    # sit BEHIND the column, which is what the far-render holdout fixes.
    for i, sy in enumerate(STRAP_Y):
        add(tube(f"ota_clamp_{i}", (0.0, sy, -CR), 0.092, 0.078, 0.016,
                 brass, rot=(math.pi / 2, 0, 0), verts=44))
        for s, tag in ((-1, "l"), (1, "r")):
            add(box(f"ota_clamp_{i}_arm_{tag}", (s * 0.096, sy, -0.010),
                    (0.046, 0.017, 0.072), brass, bevel=0.002))
            add(cyl(f"ota_clamp_{i}_bolt_{tag}", (s * 0.118, sy, 0.018),
                    0.0058, 0.009, steel, rot=(math.pi / 2, 0, 0), verts=12))
    # two BARE collars just outside the plate: they are the only place the eye
    # can actually SEE the rack gripping the cylinder.
    for i, sy in enumerate(BARE_Y):
        add(tube(f"ota_bare_{i}", (0.0, sy, -CR), 0.094, 0.078, 0.020,
                 brass, rot=(math.pi / 2, 0, 0), verts=44))

    # ------------------------------------------------------- chassis + plate
    for s, tag in ((-1, "l"), (1, "r")):
        add(box(f"ota_cheek_{tag}", (s * HW, 0.0, 0.005),
                (0.010, Y_TOP - Y_BOT, 0.062), hull_d, bevel=0.002))
    add(box("ota_plate", (0.0, 0.0, FRONT - 0.009),
            (2 * HW, Y_TOP - Y_BOT, 0.018), hull, bevel=0.003))
    # a thin brass edge rail top and bottom so the plate reads as machined
    for i, ey in enumerate((Y_TOP - 0.004, Y_BOT + 0.004)):
        add(box(f"ota_rail_{i}", (0.0, ey, FRONT + 0.004),
                (2 * HW, 0.008, 0.010), brass, bevel=0.002))

    # ---------------------------------------------------- the replicator head
    hy = (HEAD_Y0 + HEAD_Y1) / 2
    hh = HEAD_Y1 - HEAD_Y0
    # dark recess behind the throat
    add(box("ota_throat_back", (CART_X, hy, FRONT + 0.002),
            (THR_X1 - THR_X0, hh, 0.006), ebon))
    # right-hand block carries the dial + checksum readout
    rb_x0, rb_x1 = THR_X1, HW
    add(box("ota_head_block", ((rb_x0 + rb_x1) / 2, hy,
                               (FRONT + HEAD_Z) / 2),
            (rb_x1 - rb_x0, hh, HEAD_Z - FRONT), case, bevel=0.003))
    # throat jambs + floor stop
    add(box("ota_throat_jamb_l", (-HW + 0.004, hy, (FRONT + HEAD_Z) / 2),
            (0.008, hh, HEAD_Z - FRONT), case, bevel=0.002))
    add(box("ota_throat_stop", (CART_X, (HEAD_Y0 + THR_FLOOR) / 2,
                                (FRONT + HEAD_Z) / 2),
            (THR_X1 - THR_X0, THR_FLOOR - HEAD_Y0, HEAD_Z - FRONT),
            case, bevel=0.002))
    # brass mouth lip along the top of the throat
    add(box("ota_throat_lip", (CART_X, HEAD_Y1 - 0.005, HEAD_Z - 0.004),
            (THR_X1 - THR_X0 + 0.020, 0.010, 0.014), brass, bevel=0.002))
    add(text("ota_lbl_publish", "PUBLISH", 0.0088, brass,
             (CART_X, 0.134, HEAD_Z + 0.001)))

    # LOADED latch lamp beside the throat floor
    add(tube("ota_latch_ring", (LATCH_XY[0], LATCH_XY[1], HEAD_Z + 0.001),
             0.0125, 0.0090, 0.005, brass, verts=20))
    latch = add(sphere("ota_latch_lamp",
                       (LATCH_XY[0], LATCH_XY[1], HEAD_Z + 0.001), 0.0092,
                       amber_off, scale=(1, 1, 0.60)))

    # checksum readout (static): what /publish carries
    add(box("ota_chk_face", (0.050, 0.150, HEAD_Z + 0.004),
            (0.094, 0.038, 0.010), glassy))
    for o in bez_frame("ota_chk_bez", 0.050, 0.150, 0.104, 0.048,
                       HEAD_Z, HEAD_Z + 0.014, brass):
        add(o)
    add(text("ota_chk_lbl", "SHA-256", 0.0072, dot_new,
             (0.050, 0.160, HEAD_Z + 0.010)))
    add(text("ota_chk_val", "9F2C41B8", 0.0082, dot_new,
             (0.050, 0.143, HEAD_Z + 0.010)))

    # POLL INTERVAL dial
    dial_static = []
    dial_static.append(add(cyl("ota_dial_bez", (DIAL_X, DIAL_Y, HEAD_Z + 0.004),
                               DIAL_BEZEL, 0.010, brass, verts=40)))
    dial_static.append(add(cyl("ota_dial_face", (DIAL_X, DIAL_Y, HEAD_Z + 0.008),
                               DIAL_FACE, 0.004, ivory, verts=40)))
    for i in range(9):
        th = math.radians(-118 + 236 * i / 8)
        rr = DIAL_FACE - 0.007
        dial_static.append(add(box(
            f"ota_dial_tick_{i}",
            (DIAL_X + math.sin(th) * rr, DIAL_Y + math.cos(th) * rr,
             HEAD_Z + 0.011),
            (0.0022, 0.0105, 0.0012), ink,
            rot=Euler((0, 0, -th), 'XYZ'))))
    dial_static.append(add(text("ota_dial_lbl", "POLL", 0.0090, ink,
                                (DIAL_X, DIAL_Y - 0.016, HEAD_Z + 0.011))))
    dial_static.append(add(text("ota_dial_unit", "SEC", 0.0068, ink,
                                (DIAL_X, DIAL_Y - 0.028, HEAD_Z + 0.011))))

    # the needle: rendered ONCE pointing up, spun by the browser.  Parented to
    # an empty at the hub so the wide shot can bake a non-zero angle.
    bpy.ops.object.empty_add(location=(0, 0, 0))
    npiv = bpy.context.object
    npiv.name = "ota_poll_pivot"
    npiv.parent = root
    npiv.matrix_parent_inverse = Matrix.Identity(4)
    npiv.location = (DIAL_X, DIAL_Y, HEAD_Z + 0.013)
    needle = []
    n0 = add(box("ota_poll_needle", (DIAL_X, DIAL_Y + 0.015, HEAD_Z + 0.014),
                 (0.0036, 0.032, 0.0026), red_on))
    n1 = add(cyl("ota_poll_hub", (DIAL_X, DIAL_Y, HEAD_Z + 0.015),
                 0.0070, 0.0060, brass, verts=16))
    for o in (n0, n1):
        o.parent = npiv
        o.matrix_parent_inverse = Matrix.Translation(
            -Vector(npiv.location))
        needle.append(o)

    # ------------------------------------------------------- the cartridge
    bpy.ops.object.empty_add(location=(0, 0, 0))
    cpiv = bpy.context.object
    cpiv.name = "ota_cart_pivot"
    cpiv.parent = root
    cpiv.matrix_parent_inverse = Matrix.Identity(4)
    cpiv.location = (0, 0, 0)

    cart = []
    cz = (FRONT + 0.008 + HEAD_Z - 0.004) / 2      # cartridge mid depth
    ct = CART_T
    cart.append(add(box("ota_cart_body", (CART_X, CART_SEAT_Y, cz),
                        (CART_W, CART_H, ct), case, bevel=0.003)))
    cart.append(add(box("ota_cart_face", (CART_X, CART_SEAT_Y, cz + ct / 2),
                        (CART_W - 0.008, CART_H - 0.008, 0.004), ebon)))
    for i, dx in ((0, -0.018), (1, 0.018)):
        cart.append(add(cyl(f"ota_cart_spool_{i}",
                            (CART_X + dx, CART_SEAT_Y + 0.006,
                             cz + ct / 2 + 0.002),
                            0.0160, 0.005, tape_m, verts=26)))
        cart.append(add(cyl(f"ota_cart_hub_{i}",
                            (CART_X + dx, CART_SEAT_Y + 0.006,
                             cz + ct / 2 + 0.005),
                            0.0072, 0.006, brass, verts=16)))
        for k in range(3):
            th = math.radians(60 * k + 18 * i)
            cart.append(add(box(
                f"ota_cart_spoke_{i}_{k}",
                (CART_X + dx, CART_SEAT_Y + 0.006, cz + ct / 2 + 0.004),
                (0.0026, 0.030, 0.0018), brass, rot=(0, 0, th))))
    cart.append(add(box("ota_cart_label",
                        (CART_X, CART_SEAT_Y - 0.021, cz + ct / 2 + 0.003),
                        (0.058, 0.014, 0.003), ivory)))
    cart.append(add(text("ota_cart_ver", VER_NEW, 0.0092, ink,
                         (CART_X, CART_SEAT_Y - 0.021, cz + ct / 2 + 0.006))))
    cart.append(add(box("ota_cart_grip",
                        (CART_X, CART_SEAT_Y + CART_H / 2 + 0.006, cz),
                        (0.032, 0.010, 0.016), brass, bevel=0.002)))
    for o in cart:
        o.parent = cpiv
        o.matrix_parent_inverse = Matrix.Identity(4)

    # ------------------------------------------------------ propagation spine
    add(box("ota_spine_chan", (SP_X, (CHEV_Y0 + CHEV_Y1) / 2 + 0.006,
                               FRONT + 0.002),
            (SP_W + 0.008, CHEV_Y0 - CHEV_Y1 + 0.024, 0.006), ebon))
    add(box("ota_spine_rail_l", (SP_X - SP_W / 2 - 0.005,
                                 (CHEV_Y0 + CHEV_Y1) / 2 + 0.006, FRONT + 0.005),
            (0.003, CHEV_Y0 - CHEV_Y1 + 0.024, 0.006), brass))
    add(box("ota_spine_rail_r", (SP_X + SP_W / 2 + 0.005,
                                 (CHEV_Y0 + CHEV_Y1) / 2 + 0.006, FRONT + 0.005),
            (0.003, CHEV_Y0 - CHEV_Y1 + 0.024, 0.006), brass))
    chevs = []
    for i in range(CHEV_N):
        t = i / (CHEV_N - 1)
        cy = CHEV_Y0 + (CHEV_Y1 - CHEV_Y0) * t
        chevs.append(add(tri_down(f"ota_chev_{i}", SP_X, cy, SP_W - 0.003,
                                  0.0095, FRONT + 0.007, chev_off)))

    # ------------------------------------------------------------- cradles
    boards, beacons, ver_old, ver_new = [], [], [], []
    for i, cy in enumerate(CRADLE_Y):
        code = FLEET[i]
        # shelf rail the probe sits on
        add(box(f"ota_shelf_{i}", (0.0, cy - 0.030, FRONT + 0.006),
                (2 * HW, 0.007, 0.016), brass, bevel=0.002))
        # cradle yokes
        for k, px in ((0, -0.070), (1, -0.032)):
            add(box(f"ota_yoke_{i}_{k}", (px, cy + 0.004, FRONT + 0.012),
                    (0.006, 0.026, 0.024), hull_d, bevel=0.001))
        # the docked probe: a torpedo lying nose-left in its cradle
        add(cyl(f"ota_probe_{i}", (-0.052, cy + 0.004, FRONT + 0.030),
                0.018, 0.052, slate, rot=(0, math.pi / 2, 0), verts=22))
        add(cone(f"ota_probe_nose_{i}", (-0.091, cy + 0.004, FRONT + 0.030),
                 0.018, 0.003, 0.026, steel, rot=(0, -math.pi / 2, 0)))
        add(tube(f"ota_probe_band_{i}", (-0.062, cy + 0.004, FRONT + 0.030),
                 0.0198, 0.0170, 0.006, brass, rot=(0, math.pi / 2, 0),
                 verts=22))
        add(box(f"ota_probe_vane_a_{i}", (-0.030, cy + 0.004, FRONT + 0.030),
                (0.014, 0.034, 0.003), hull_d))
        add(box(f"ota_probe_vane_b_{i}", (-0.030, cy + 0.004, FRONT + 0.030),
                (0.014, 0.003, 0.032), hull_d))
        # status beacon on the probe's spine, facing the pilot
        beacons.append(add(sphere(
            f"ota_beacon_{i}", (-0.052, cy + 0.004, FRONT + 0.050), 0.0105,
            amber_on, scale=(1, 1, 0.62))))
        # flip-dot version board
        add(box(f"ota_board_face_{i}", (BOARD_X, cy, FRONT + 0.007),
                (BOARD_W - 0.008, BOARD_H - 0.008, 0.014), glassy))
        boards.extend(add(o) for o in bez_frame(
            f"ota_board_bez_{i}", BOARD_X, cy, BOARD_W, BOARD_H,
            FRONT, FRONT + 0.018, brass))
        # faint flip-dot ruling so the face reads as a dot matrix, not a screen
        for k in range(4):
            add(box(f"ota_board_rule_{i}_{k}",
                    (BOARD_X, cy - 0.017 + k * 0.0115, FRONT + 0.0136),
                    (BOARD_W - 0.020, 0.0009, 0.0010), ebon))
        add(text(f"ota_board_code_{i}", code, 0.0105, brass,
                 (BOARD_X - 0.042, cy + 0.013, FRONT + 0.015), align='LEFT'))
        ver_old.append(add(text(f"ota_ver_old_{i}", VER_OLD, 0.0200, dot_old,
                                (BOARD_X, cy - 0.008, FRONT + 0.015))))
        ver_new.append(add(text(f"ota_ver_new_{i}", VER_NEW, 0.0200, dot_new,
                                (BOARD_X, cy - 0.008, FRONT + 0.015))))

    # --------------------------------------------------------------- footer
    add(box("ota_foot", (0.0, FOOT_Y, FRONT + 0.005),
            (2 * HW - 0.006, 0.048, 0.014), brass, bevel=0.002))
    add(text("ota_foot_a", "FLEET REPLICATOR", 0.0100, ink,
             (0.0, FOOT_Y + 0.009, FRONT + 0.013)))
    add(text("ota_foot_b", "GRID  OTA-90", 0.0090, ink,
             (0.0, FOOT_Y - 0.009, FRONT + 0.013)))

    # ------------------------------------------------------------ parenting
    for o in made:
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()

    # ---------------------------------------------------- rest pose (wide shot)
    cpiv.location = (0, 0, 0)                       # cartridge seated
    latch.data.materials[0] = amber_on
    npiv.rotation_euler = (0, 0, math.radians(-POLL_FAR_DEG))
    lit = chev_lit(PROP_FAR)
    for i, c in enumerate(chevs):
        c.data.materials[0] = (chev_hot if i == lit - 1 else
                               (chev_on if i < lit else chev_off))
    done = FLEET_DONE[FLEET_FAR]
    for i in range(3):
        beacons[i].data.materials[0] = grn_on if i < done else amber_on
    hidden = []
    for i in range(3):
        drop = ver_old[i] if i < done else ver_new[i]
        drop.hide_render = True
        hidden.append(drop)
    bpy.context.view_layer.update()

    moving = set(cart) | {latch} | set(chevs) | set(needle) | set(beacons) \
        | set(ver_old) | set(ver_new)
    static = [o for o in made if o not in moving]
    far = [o for o in made if o not in hidden]

    controls = {
        "cartridge": {
            "kind": "frames", "label": "PUBLISH",
            "objs": cart + [latch], "pivot": cpiv, "latch": latch,
            "cart": cart, "lift": CART_LIFT, "frames": CART_FRAMES,
            "mats": {"off": amber_off, "on": amber_on}},
        "propagate": {
            "kind": "frames", "label": "PROPAGATE",
            "objs": chevs, "pivot": None, "frames": PROP_FRAMES,
            "mats": {"off": chev_off, "on": chev_on, "hot": chev_hot}},
        "fleet": {
            "kind": "states", "label": "FLEET VERSIONS",
            "objs": beacons + ver_old + ver_new, "pivot": None,
            "order": list(FLEET_ORDER), "modules": list(FLEET),
            "beacons": beacons, "old": ver_old, "new": ver_new,
            "boards": boards,
            "mats": {"amber": amber_on, "green": grn_on}},
        "poll": {
            "kind": "rotate", "label": "POLL INTERVAL",
            "objs": needle, "pivot": npiv, "range": POLL_RANGE,
            "anchor": Vector((DIAL_X, DIAL_Y, HEAD_Z + 0.015)),
            "hotspot_objs": dial_static},
    }
    return {"far": far, "controls": controls, "root": root,
            "static": static, "all": made, "hidden": hidden}


def chev_lit(k):
    """How many chevrons are lit on propagate frame k."""
    return int(round(k * CHEV_N / float(PROP_FRAMES - 1)))


# ======================================================== render harness
RTYPES = {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}


def renderables(scene):
    return [o for o in scene.objects if o.type in RTYPES]


def render_to(scene, path, visible, holdout=()):
    """Render only `visible`; `holdout` objects stay in the depth buffer but
    punch alpha, so a sprite is correctly clipped by geometry in front of it.
    For OTA this is load-bearing in BOTH directions: the column occludes the
    back halves of the clamp collars in the far shot, and the head jambs
    occlude the cartridge as it slides into the throat in the close shot."""
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


def clamp_rect(r, w, h):
    x0, y0 = max(0, r["x"]), max(0, r["y"])
    x1, y1 = min(w, r["x"] + r["w"]), min(h, r["y"] + r["h"])
    return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}


def glow_render(scene, path, objs, holdout=()):
    g = shell.material("ota_glowmask", (1, 1, 1, 1), 0.0, 0.5,
                       emission=(1, 1, 1, 1), emit_strength=1.0)
    saved = {}
    for o in objs:
        saved[o.name] = list(o.data.materials)
        if not len(o.data.materials):
            o.data.materials.append(g)
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
        for i, m in enumerate(saved[o.name]):
            o.data.materials[i] = m


# --------------------------------------------------------------- close rig
CLOSE_YAW = math.radians(22.0)
CLOSE_PITCH = math.radians(6.0)
CLOSE_LENS = 45.0
CLOSE_FRAC = 0.93


def fit_camera(scene, cam, objs, target, view_dir, frac=0.90, iters=5):
    """Dolly + re-aim `cam` along `view_dir` until `objs` fill `frac` of frame."""
    from bpy_extras.object_utils import world_to_camera_view
    cam.rotation_euler = (target - cam.location) \
        .to_track_quat('-Z', 'Y').to_euler()
    for _ in range(iters):
        bpy.context.view_layer.update()
        xs, ys = [], []
        for o in objs:
            for c in o.bound_box:
                co = world_to_camera_view(scene, cam,
                                          o.matrix_world @ Vector(c))
                xs.append(co.x)
                ys.append(co.y)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        s = min(3.0, max(0.30, max(max(xs) - min(xs),
                                   max(ys) - min(ys)) / frac))
        dist = (cam.location - target).length
        m = cam.matrix_world.to_3x3()
        fw = 2 * dist * math.tan(cam.data.angle_x / 2)
        fh = fw * scene.render.resolution_y / scene.render.resolution_x
        target = (target + (m @ Vector((1, 0, 0))) * ((cx - 0.5) * fw)
                  + (m @ Vector((0, 1, 0))) * ((cy - 0.5) * fh))
        cam.location = target + view_dir * (dist * s)
        cam.rotation_euler = (target - cam.location) \
            .to_track_quat('-Z', 'Y').to_euler()
    bpy.context.view_layer.update()
    return target


def close_rig(scene, root, fit_objs):
    R3 = root.matrix_world.to_3x3()
    d = Vector((math.sin(CLOSE_YAW) * math.cos(CLOSE_PITCH),
                math.sin(CLOSE_PITCH),
                math.cos(CLOSE_YAW) * math.cos(CLOSE_PITCH)))
    view_dir = (R3 @ d).normalized()
    target = root.matrix_world @ Vector((0.0, 0.02, 0.045))

    bpy.ops.object.camera_add(location=target + view_dir * 1.4)
    cam = bpy.context.object
    cam.name = "ota_closecam"
    cam.data.lens = CLOSE_LENS
    fit_camera(scene, cam, fit_objs, target, view_dir, frac=CLOSE_FRAC)

    lights = []
    for i, (lp, energy, size, col) in enumerate([
            ((-0.34, 0.30, 0.52), 0.34, 0.32, (1.00, 0.90, 0.74)),
            ((0.40, 0.10, 0.50), 0.26, 0.34, (0.72, 0.82, 1.00)),
            ((0.10, -0.34, 0.44), 0.20, 0.28, (1.00, 0.86, 0.66)),
            ((-0.06, 0.40, 0.26), 0.14, 0.24, (1.00, 0.84, 0.62))]):
        bpy.ops.object.light_add(type='AREA', location=(0, 0, 0))
        L = bpy.context.object
        L.name = f"ota_light_{i}"
        L.data.energy, L.data.size = energy, size
        L.data.color = col
        L.parent = root
        L.matrix_parent_inverse = Matrix.Identity(4)
        L.location = Vector(lp)
        aim = Vector((lp[0] * 0.2, lp[1] * 0.2, 0.03)) - Vector(lp)
        L.rotation_euler = aim.to_track_quat('-Z', 'Y').to_euler()
        lights.append(L)
    return cam, lights


HTML = """<!doctype html>
<meta charset="utf-8">
<title>OTA - Fleet Replicator Grid / Drone Bay</title>
<style>
 body{margin:0;background:#080a0e;color:#cbb48a;
      font:13px/1.5 ui-monospace,Menlo,monospace}
 header{padding:14px 18px;border-bottom:1px solid #2a2318}
 h1{margin:0;font-size:15px;letter-spacing:.18em;color:#e2c489}
 header p{margin:6px 0 0;color:#7d7360;max-width:82ch}
 #stage{margin:14px 18px;overflow:hidden}
 #wrap{position:relative;width:1280px;height:720px;transform-origin:top left;
       background:radial-gradient(circle at 30% 40%,#0d1220 0%,#05070c 70%)}
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
 <h1>OTA &middot; FLEET REPLICATOR GRID / DRONE BAY</h1>
 <p>A drone rack clamped to the left column. Drag down the <b>PUBLISH</b>
    throat to load the tape-reel cartridge into the replicator
    (<code>POST /publish</code>) &mdash; it latches and lights LOADED. Drag the
    <b>PROPAGATE</b> spine to run the update down the rack. Click the
    <b>cradles</b> to roll the fleet forward: every click brings one more of
    <code>fmm</code> / <code>ipm</code> / <code>log</code> up to 1.5.0 on its
    flip-dot board (<code>POST /devices/{id}/report</code>). Drag the
    <b>POLL</b> dial for the agent's
    <code>GET /updates/{module}/latest</code> interval.</p>
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
      const f = (state[id]-c.range[0])/(c.range[1]-c.range[0]);
      bits.push(c.label + ': ' + Math.round(5 + f*115) + 's');
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
    // OTA's two frame controls BOTH move vertically; axis comes from the
    // manifest ("axis":"y"), never from the hotspot aspect ratio.
    const vert = (c.axis || 'y') === 'y';
    const set = ev => {
      const r = h.getBoundingClientRect();
      let f = vert ? (ev.clientY-r.top)/r.height : (ev.clientX-r.left)/r.width;
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
    scene = shell.build(P)                    # UNMODIFIED shell + main camera
    far_cam = scene.camera
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    res = add_props(P, mats)
    scene.render.film_transparent = True
    mine = set(res["all"])
    far_objs = res["far"]
    ctl = res["controls"]
    root = res["root"]
    W, H = scene.render.resolution_x, scene.render.resolution_y
    shell_meshes = [o for o in renderables(scene) if o not in mine]

    # ------------------------------------------------------------- far shot
    # Holdout the WHOLE shell: the clamp collars wrap BEHIND the column, so the
    # column has to punch them out of both the sprite and the glow mask.
    render_to(scene, os.path.join(OUT, "far_prop.png"), far_objs,
              holdout=shell_meshes)
    far_hot = clamp_rect(bbox_rect(scene, far_cam, far_objs, pad=6), W, H)
    glow_render(scene, os.path.join(OUT, "far_glow.png"), far_objs,
                holdout=shell_meshes)
    render_to(scene, os.path.join(OUT, "_shell_plate.png"), shell_meshes)

    # -------------------------------------------------------- close-up rig
    cart, cpiv = ctl["cartridge"]["cart"], ctl["cartridge"]["pivot"]
    npiv = ctl["poll"]["pivot"]
    npiv.rotation_euler = (0, 0, 0)           # needle rests pointing UP
    cpiv.location = (0, CART_LIFT, 0)         # include the raised cartridge
    bpy.context.view_layer.update()
    fit_objs = res["static"] + cart
    cam, _lights = close_rig(scene, root, fit_objs)
    cpiv.location = (0, 0, 0)
    scene.camera = cam
    bpy.context.view_layer.update()

    clip = res["static"]
    render_to(scene, os.path.join(OUT, "close_plate.png"),
              shell_meshes + res["static"])

    controls = {}

    # --- CARTRIDGE: a frame per step of the load ------------------------
    c = ctl["cartridge"]
    latch, M_ = c["latch"], c["mats"]
    frames, rects = [], []
    for k in range(c["frames"]):
        t = k / (c["frames"] - 1)
        cpiv.location = (0, c["lift"] * (1.0 - t), 0)
        latch.data.materials[0] = M_["on"] if k >= c["frames"] - 2 else M_["off"]
        bpy.context.view_layer.update()
        fn = f"close_cartridge_{k}.png"
        render_to(scene, os.path.join(OUT, fn), cart + [latch], holdout=clip)
        frames.append(fn)
        rects.append(bbox_rect(scene, cam, cart + [latch], pad=8))
    cpiv.location = (0, 0, 0)
    latch.data.materials[0] = M_["on"]
    bpy.context.view_layer.update()
    controls["cartridge"] = {
        "kind": "frames", "label": c["label"], "axis": "y",
        "frames": frames, "hotspot": clamp_rect(union(rects), W, H)}

    # --- PROPAGATE: the pulse running down the spine --------------------
    c = ctl["propagate"]
    chevs, M_ = c["objs"], c["mats"]
    frames = []
    for k in range(c["frames"]):
        lit = chev_lit(k)
        for i, ch in enumerate(chevs):
            ch.data.materials[0] = (M_["hot"] if i == lit - 1 else
                                    (M_["on"] if i < lit else M_["off"]))
        fn = f"close_propagate_{k}.png"
        render_to(scene, os.path.join(OUT, fn), chevs, holdout=clip)
        frames.append(fn)
    lit = chev_lit(PROP_FAR)
    for i, ch in enumerate(chevs):
        ch.data.materials[0] = (M_["hot"] if i == lit - 1 else
                                (M_["on"] if i < lit else M_["off"]))
    controls["propagate"] = {
        "kind": "frames", "label": c["label"], "axis": "y", "frames": frames,
        "hotspot": clamp_rect(bbox_rect(scene, cam, chevs, pad=10), W, H)}

    # --- FLEET: version rolling down the rack ---------------------------
    c = ctl["fleet"]
    beacons, old, new, M_ = c["beacons"], c["old"], c["new"], c["mats"]
    states, rects = {}, [bbox_rect(scene, cam, c["boards"] + beacons, pad=10)]
    for nm in c["order"]:
        done = FLEET_DONE[nm]
        vis = list(beacons)
        for i in range(3):
            beacons[i].data.materials[0] = M_["green"] if i < done \
                else M_["amber"]
            vis.append(new[i] if i < done else old[i])
        fn = f"close_fleet_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), vis, holdout=clip)
        states[nm] = fn
        rects.append(bbox_rect(scene, cam, vis, pad=8))
    done = FLEET_DONE[FLEET_FAR]
    for i in range(3):
        beacons[i].data.materials[0] = M_["green"] if i < done else M_["amber"]
    controls["fleet"] = {
        "kind": "states", "label": c["label"], "states": states,
        "order": c["order"], "modules": c["modules"],
        "hotspot": clamp_rect(union(rects), W, H)}

    # --- POLL: one render, spun in CSS ----------------------------------
    c = ctl["poll"]
    render_to(scene, os.path.join(OUT, "close_poll.png"), c["objs"],
              holdout=clip)
    px, py = project(scene, cam, root.matrix_world @ c["anchor"])
    controls["poll"] = {
        "kind": "rotate", "label": c["label"], "image": "close_poll.png",
        "pivot": {"x": round(px, 1), "y": round(py, 1)}, "range": c["range"],
        "hotspot": clamp_rect(bbox_rect(scene, cam, c["hotspot_objs"], pad=8),
                              W, H)}

    # --- keep the four rects DISJOINT so the combined frontend never has to
    # arbitrate by DOM order.  fleet's boards butt right up against the spine
    # channel and the raised cartridge overhangs the dial, so both get clipped.
    def clip_left_of(a, b):
        if a["x"] + a["w"] > b["x"] and a["x"] < b["x"]:
            a["w"] = max(1, b["x"] - a["x"] - 1)
    clip_left_of(controls["fleet"]["hotspot"],
                 controls["propagate"]["hotspot"])
    clip_left_of(controls["cartridge"]["hotspot"], controls["poll"]["hotspot"])

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

    print("OTA far hotspot", json.dumps(far_hot))
    for k, v in controls.items():
        print("OTA close", k, v["kind"], json.dumps(v["hotspot"]))
    print("OTA OK ->", OUT)


if __name__ == "__main__":
    main()
