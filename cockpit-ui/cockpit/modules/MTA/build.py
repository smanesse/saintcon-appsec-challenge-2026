"""
MTA — "Subspace Comms Relay / Message Torpedo Room" cockpit control
(SAINTCON 2026 AppSec Challenge UI).

The mail room lives on the console FASCIA — the tall vertical front below the
dash lip, at the pilot's knee — because that is where a pneumatic terminus
belongs: the capsule has to physically ARRIVE somewhere you can reach it.

On the panel:
  * a PNEUMATIC TUBE run across the top, hooped in brass, entering through the
    left frame rail and ending in a flared BELL MOUTH aimed at the pilot.  A
    message capsule rides the tube and pops nose-first out of the bell when the
    message lands.                                       -> "frames"
  * a rack of ten PIGEONHOLES, the outbound queue.  Each hole either gapes
    empty or holds a cream envelope stamped with its queued message ID, and a
    brass odometer over the rack counts them.            -> "states"
  * the STARTTLS SCRAMBLER — a brass cipher wheel with a lettered ring, finger
    holes and an index pointer.  You throw it before you transmit. -> "rotate"
  * the COMMS HANDSET on its cradle: on-hook / off-hook.  -> "states"
  * static dressing: the POST slot you drop a composed envelope into, and the
    clipped X-Notify-Webhook delivery-receipt slip.

Build + render everything:
    /Applications/Blender.app/Contents/MacOS/Blender --background --python build.py
"""
import bpy, math, os, sys, json
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
COCKPIT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, COCKPIT)
import shell                                                     # noqa: E402
import slots                                                     # noqa: E402

OUT = os.path.join(HERE, "out")
CODE = "MTA"
NAME = "Subspace Comms Relay"
LIFT = 0.015          # stand the panel proud of the curved fascia skin

# ------------------------------------------------------------------ layout
# Everything is modelled in the slot's LOCAL frame:
#   +X right along the surface, +Y up the surface, +Z out toward the pilot.
PW, PH = 0.480, 0.420        # panel back plate (outer, with rails: .522x.454)
PZ = 0.016                   # panel front face — all detail sits on top of it

TUBE_Y = 0.150               # pneumatic tube centreline
TUBE_X0, TUBE_X1 = -0.236, 0.150
BELL_X = 0.176

HDR_Y = 0.094                # queue odometer header
ODO_X = 0.140
COL_X = (-0.156, -0.078, 0.0, 0.078, 0.156)   # pigeonhole columns
ROW_Y = (0.040, -0.012)                       # pigeonhole rows

WHEEL = Vector((0.160, -0.138, 0.0))          # STARTTLS scrambler centre
HAND_X = -0.150
HAND_PIVOT = Vector((HAND_X, -0.090, PZ + 0.018))
SLIP_Y = -0.060

# Message IDs, in the shape the module actually mints them
# (<epoch-ms>.<12 hex>.eml — the pigeonhole slip shows the short hex).
QUEUE_IDS = ["a3f1c9", "7b20de", "c41e8a", "1f9d02", "e58b47",
             "93cc10", "2dab6f", "604f3b", "b81a55", "0c7e92"]
QUEUE_TO = ["bob@somewhere.example", "alice@mta.local", "postmaster@mta.local",
            "ops@fleet.example", "relay@example.net", "bob@somewhere.example",
            "alice@mta.local", "nav@fleet.example", "hal@mta.local",
            "postmaster@mta.local"]
QUEUE_STATES = [("empty", 0), ("q2", 2), ("q5", 5), ("q8", 8), ("full", 10)]
QUEUE_REST = "q5"            # top row full — what the wide shot shows

CAPSULE_X = (-0.210, -0.146, -0.082, -0.018, 0.046, 0.110)
CAPSULE_REST = 3
CIPHER = "ABCDEFGHIJKL"      # the scrambler's letter ring

# A canned SMTP exchange the demo page replays.
SESSION = [
    "220 mta.local ESMTP MTA Service ready",
    "EHLO cockpit.fleet",
    "250-mta.local Hello cockpit.fleet",
    "250-PIPELINING",
    "250-8BITMIME",
    "250-AUTH PLAIN LOGIN",
    "250-STARTTLS",
    "250 HELP",
]


# --------------------------------------------------------------- utilities
def _finish(o, name, mat, rot=(0, 0, 0), bevel=0.0, smooth=False):
    o.name = name
    if o.scale != Vector((1, 1, 1)):
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


def cyl(name, center, radius, depth, mat, rot=(0, 0, 0), verts=26,
        smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                        vertices=verts, location=center)
    return _finish(bpy.context.object, name, mat, rot, smooth=smooth)


def cone(name, center, r1, r2, depth, mat, rot=(0, 0, 0), verts=28):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth,
                                    vertices=verts, location=center)
    return _finish(bpy.context.object, name, mat, rot, smooth=True)


def torus(name, center, major, minor, mat, rot=(0, 0, 0), mseg=22, nseg=8):
    bpy.ops.mesh.primitive_torus_add(location=center, major_radius=major,
                                     minor_radius=minor, major_segments=mseg,
                                     minor_segments=nseg)
    return _finish(bpy.context.object, name, mat, rot, smooth=True)


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


def text(name, body, size, mat, loc, rot=(0, 0, 0), align='CENTER'):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.extrude = 0.0003
    f = mono_font()
    if f:
        cu.font = f
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat)
    return o


def mat(name, base, metallic=0.0, rough=0.5, emission=None, strength=0.0):
    return shell.material("mta_" + name, base, metallic, rough,
                          emission=emission, emit_strength=strength)


# ----------------------------------------------------------------- the prop
def add_props(P, mats):
    """Add the MTA mail terminus to the CURRENT scene."""
    brass = mats["brass"]
    hull = mats["hull"]
    hull_d = mats["hull_d"]

    paper = mat("paper", (0.885, 0.862, 0.768, 1), 0.0, 0.80)
    ink = mat("ink", (0.052, 0.048, 0.052, 1), 0.0, 0.62)
    ebon = mat("ebon", (0.022, 0.024, 0.028, 1), 0.0, 0.34)
    case = mat("case", (0.052, 0.056, 0.066, 1), 0.18, 0.46)
    rackm = mat("rack", (0.135, 0.138, 0.150, 1), 0.25, 0.44)
    wax = mat("wax", (0.44, 0.055, 0.060, 1), 0.0, 0.36)
    steel = mat("steel", (0.58, 0.60, 0.65, 1), 1.0, 0.28)
    trim = mat("trim", (0.165, 0.118, 0.042, 1), 1.0, 0.58)
    port = mat("port", (0.24, 0.56, 0.66, 1), 0.0, 0.16,
               emission=(0.18, 0.62, 0.74, 1), strength=1.5)
    amber = mat("amber", (1.0, 0.72, 0.26, 1), 0.0, 0.30,
                emission=(1.0, 0.60, 0.14, 1), strength=3.2)
    green = mat("green", (0.42, 1.0, 0.58, 1), 0.0, 0.30,
                emission=(0.26, 1.0, 0.44, 1), strength=2.6)

    loc, eul = slots.place(P, CODE, LIFT)
    bpy.ops.object.empty_add(location=loc)
    root = bpy.context.object
    root.name = "mta_root"
    root.rotation_euler = eul

    made = []

    def add(o):
        made.append(o)
        return o

    # ------------------------------------------------------- panel + frame
    add(box("mta_back", (0, 0, PZ / 2), (PW, PH, PZ), case, bevel=0.002))
    for i, (cx, cy, sx, sy) in enumerate(
            ((0.0, PH / 2 + 0.008, PW + 0.042, 0.018),
             (0.0, -PH / 2 - 0.008, PW + 0.042, 0.018),
             (-PW / 2 - 0.012, 0.0, 0.018, PH + 0.036),
             (PW / 2 + 0.012, 0.0, 0.018, PH + 0.036))):
        add(box(f"mta_rail_{i}", (cx, cy, 0.011), (sx, sy, 0.022), trim,
                bevel=0.003))
    add(text("mta_nameplate", "MTA · SUBSPACE COMMS RELAY", 0.0135, brass,
             (0.0, -PH / 2 - 0.008, 0.0234)))
    add(text("mta_topplate", "MESSAGE TORPEDO ROOM · ESMTP 2525", 0.0118, brass,
             (0.0, PH / 2 + 0.008, 0.0234)))
    for i in range(6):
        ry = -0.175 + i * 0.070
        for j, rx in enumerate((-PW / 2 - 0.012, PW / 2 + 0.012)):
            add(cyl(f"mta_rivet_{i}_{j}", (rx, ry, 0.0232), 0.0032, 0.004,
                    steel, verts=10))

    # ------------------------------------------------- the pneumatic tube
    tmid = (TUBE_X0 + TUBE_X1) / 2
    tlen = TUBE_X1 - TUBE_X0
    add(box("mta_tube_bed", (tmid, TUBE_Y, PZ + 0.005), (tlen, 0.070, 0.010),
            hull_d, bevel=0.002))
    for i, sy in enumerate((-0.033, 0.033)):
        add(box(f"mta_tube_rail_{i}", (tmid, TUBE_Y + sy, PZ + 0.026),
                (tlen + 0.006, 0.010, 0.014), hull_d, bevel=0.002))
    for i in range(9):
        add(torus(f"mta_tube_hoop_{i}", (-0.226 + i * 0.0435, TUBE_Y,
                                         PZ + 0.026), 0.030, 0.0044, brass,
                  rot=(0, math.pi / 2, 0)))
    # the tube enters the panel through the left frame rail
    add(cyl("mta_tube_inlet", (-PW / 2 - 0.012, TUBE_Y, PZ + 0.026), 0.035,
            0.032, brass, rot=(0, math.pi / 2, 0), verts=26))
    add(cyl("mta_tube_gland", (-0.222, TUBE_Y, PZ + 0.026), 0.031, 0.009,
            steel, rot=(0, math.pi / 2, 0), verts=26))

    # elbow + flared bell mouth, aimed straight at the pilot
    add(box("mta_bell_elbow", (BELL_X, TUBE_Y, PZ + 0.020),
            (0.062, 0.076, 0.040), hull, bevel=0.004))
    add(cone("mta_bell", (BELL_X, TUBE_Y, PZ + 0.029), 0.030, 0.046, 0.050,
             brass))
    add(torus("mta_bell_lip", (BELL_X, TUBE_Y, PZ + 0.053), 0.045, 0.005,
              brass, mseg=32))
    # the dark throat is what makes the bell read as an open MOUTH
    add(cone("mta_bell_throat", (BELL_X, TUBE_Y, PZ + 0.036), 0.011, 0.041,
             0.042, ebon, verts=32))
    add(cyl("mta_bell_pilot", (BELL_X, TUBE_Y, PZ + 0.016), 0.010, 0.004, port,
            verts=20))

    # ---- the capsule, one group per position along the tube -------------
    def capsule(tag, center, along_z=False):
        rot = (0, 0, 0) if along_z else (0, math.pi / 2, 0)
        ax = Vector((0, 0, 1)) if along_z else Vector((1, 0, 0))
        objs = [cyl(f"mta_cap_{tag}_body", center, 0.0205, 0.050, brass,
                    rot=rot, verts=22),
                cyl(f"mta_cap_{tag}_band", center, 0.0222, 0.016, ebon,
                    rot=rot, verts=22),
                cyl(f"mta_cap_{tag}_win", center + ax * 0.013, 0.0214, 0.011,
                    port, rot=rot, verts=22)]
        for k, s in enumerate((-1, 1)):
            if along_z:
                nrot = (0, 0, 0) if s > 0 else (math.pi, 0, 0)
            else:
                nrot = (0, math.pi / 2 * s, 0)
            objs.append(cone(f"mta_cap_{tag}_nose_{k}",
                             center + ax * (s * 0.031), 0.0205, 0.008, 0.014,
                             steel, rot=nrot, verts=20))
        for o in objs:
            add(o)
        return objs

    cap_frames = []
    for i, cx in enumerate(CAPSULE_X):
        cap_frames.append(capsule(f"t{i}", Vector((cx, TUBE_Y, PZ + 0.028))))
    # the payoff frame: arrived, nose out of the bell, in the pilot's face
    cap_frames.append(capsule("arr", Vector((BELL_X, TUBE_Y, PZ + 0.078)),
                              along_z=True))

    # ------------------------------------------ queue header / odometer
    add(box("mta_hdr", (0.0, HDR_Y, PZ + 0.005), (0.404, 0.030, 0.010),
            brass, bevel=0.002))
    add(text("mta_hdr_txt", "OUTBOUND QUEUE", 0.0165, ink,
             (-0.072, HDR_Y, PZ + 0.0112)))
    add(box("mta_odo_bezel", (ODO_X, HDR_Y, PZ + 0.004), (0.074, 0.032, 0.009),
            brass, bevel=0.002))
    add(box("mta_odo", (ODO_X, HDR_Y, PZ + 0.007), (0.064, 0.024, 0.012),
            ebon, bevel=0.001))

    digits = {}
    for nm, n in QUEUE_STATES:
        digits[nm] = text(f"mta_odo_{nm}", "%02d" % n, 0.0205, amber,
                          (ODO_X, HDR_Y, PZ + 0.015))
        add(digits[nm])

    # ------------------------------------------------ pigeonhole rack
    add(box("mta_rack", (0.0, 0.014, PZ + 0.008), (0.400, 0.112, 0.016),
            rackm, bevel=0.002))
    rack_static = []
    for r, ry in enumerate(ROW_Y):
        for c, cx in enumerate(COL_X):
            # recessed a clear 7 mm behind the divider lattice, so the empty
            # holes actually read as holes
            rack_static.append(add(box(f"mta_hole_{r}_{c}", (cx, ry, PZ + 0.009),
                                       (0.070, 0.045, 0.016), ebon)))
    for i in range(6):
        edge = (i == 0 or i == 5)
        rack_static.append(add(box(f"mta_div_v_{i}", (-0.195 + i * 0.078, 0.014,
                                                      PZ + 0.016),
                                   (0.008, 0.116, 0.022),
                                   brass if edge else hull, bevel=0.0015)))
    for i, dy in enumerate((0.066, 0.014, -0.038)):
        rack_static.append(add(box(f"mta_div_h_{i}", (0.0, dy, PZ + 0.016),
                                   (0.404, 0.008, 0.022),
                                   brass if i != 1 else hull, bevel=0.0015)))

    env_objs = []
    for i in range(10):
        cx, ry = COL_X[i % 5], ROW_Y[i // 5]
        g = [box(f"mta_env_{i}_card", (cx, ry, PZ + 0.0192),
                 (0.062, 0.036, 0.005), paper, bevel=0.0012),
             box(f"mta_env_{i}_flap", (cx, ry + 0.0125, PZ + 0.0220),
                 (0.062, 0.0014, 0.0016), ink),
             cyl(f"mta_env_{i}_seal", (cx + 0.0215, ry + 0.0095, PZ + 0.0230),
                 0.0048, 0.0030, wax, verts=12),
             text(f"mta_env_{i}_id", QUEUE_IDS[i], 0.0118, ink,
                  (cx, ry - 0.0035, PZ + 0.0228))]
        for o in g:
            add(o)
        env_objs.append(g)

    # ------------------------------------------- STARTTLS scrambler wheel
    wx, wy = WHEEL.x, WHEEL.y
    add(cyl("mta_wheel_bezel", (wx, wy, PZ + 0.006), 0.068, 0.012, brass,
            verts=44))
    add(cyl("mta_wheel_well", (wx, wy, PZ + 0.008), 0.062, 0.011, ebon,
            verts=44))
    add(cone("mta_wheel_index", (wx, wy + 0.064, PZ + 0.020), 0.011, 0.0,
             0.017, brass, rot=(math.pi / 2, 0, 0), verts=16))
    add(box("mta_wheel_slip", (wx, SLIP_Y, PZ + 0.004), (0.100, 0.020, 0.008),
            trim, bevel=0.002))
    add(text("mta_wheel_txt", "STARTTLS", 0.0135, brass,
             (wx, SLIP_Y, PZ + 0.0102)))

    wheel_objs = [
        cyl("mta_wheel_ring", (wx, wy, PZ + 0.014), 0.058, 0.016, brass,
            verts=44),
        cyl("mta_wheel_face", (wx, wy, PZ + 0.0155), 0.039, 0.019, ebon,
            verts=40),
        cyl("mta_wheel_hub", (wx, wy, PZ + 0.019), 0.013, 0.024, brass,
            verts=20),
    ]
    for i in range(24):
        th = 2 * math.pi * i / 24
        wheel_objs.append(cyl(f"mta_wheel_knurl_{i}",
                              (wx + 0.0595 * math.sin(th),
                               wy + 0.0595 * math.cos(th), PZ + 0.014),
                              0.0034, 0.015, brass, verts=8, smooth=False))
    for i in range(6):
        th = 2 * math.pi * i / 6
        wheel_objs.append(cyl(f"mta_wheel_hole_{i}",
                              (wx + 0.026 * math.sin(th),
                               wy + 0.026 * math.cos(th), PZ + 0.021),
                              0.0062, 0.026, ebon, verts=12))
    for i, ch in enumerate(CIPHER):
        th = 2 * math.pi * i / len(CIPHER)
        wheel_objs.append(text(f"mta_wheel_glyph_{i}", ch, 0.0120, ink,
                               (wx + 0.0485 * math.sin(th),
                                wy + 0.0485 * math.cos(th), PZ + 0.0225),
                               rot=(0, 0, -th)))
    # a witness pip, so the throw of the wheel is unmistakable
    wheel_objs.append(cyl("mta_wheel_pip", (wx, wy + 0.0485, PZ + 0.024),
                          0.0055, 0.022, green, verts=12))
    for o in wheel_objs:
        add(o)

    # -------------------------- outbound POST slot + notify-webhook slip
    add(box("mta_post", (0.005, -0.122, PZ + 0.006), (0.096, 0.042, 0.012),
            brass, bevel=0.002))
    add(box("mta_post_slit", (0.005, -0.112, PZ + 0.010), (0.076, 0.013, 0.014),
            ebon))
    add(box("mta_post_lbl", (0.005, -0.134, PZ + 0.010), (0.078, 0.016, 0.006),
            trim, bevel=0.001))
    add(text("mta_post_txt", "POST", 0.0128, brass,
             (0.005, -0.134, PZ + 0.0135)))

    add(box("mta_slip_card", (0.005, -0.184, PZ + 0.003), (0.090, 0.046, 0.004),
            paper, bevel=0.001))
    add(box("mta_slip_clip", (0.005, -0.161, PZ + 0.006), (0.072, 0.010, 0.011),
            brass, bevel=0.002))
    for i, (t, s, y) in enumerate((("X-NOTIFY", 0.0098, -0.172),
                                   ("WEBHOOK", 0.0098, -0.185),
                                   ("ops@fleet", 0.0086, -0.198))):
        add(text(f"mta_slip_txt_{i}", t, s, ink, (0.005, y, PZ + 0.0062)))

    # ------------------------------------------------------ comms handset
    add(box("mta_cradle", (HAND_X, -0.176, PZ + 0.008), (0.160, 0.052, 0.016),
            hull_d, bevel=0.003))
    for i, hx in enumerate((HAND_X - 0.058, HAND_X + 0.058)):
        add(box(f"mta_hook_{i}", (hx, -0.176, PZ + 0.021),
                (0.022, 0.046, 0.016), brass, bevel=0.003))
    add(box("mta_hand_slip", (HAND_X, SLIP_Y, PZ + 0.004),
            (0.100, 0.020, 0.008), trim, bevel=0.002))
    add(text("mta_hand_txt", "HANDSET", 0.0135, brass,
             (HAND_X, SLIP_Y, PZ + 0.0102)))
    # coiled cord, drooping away to the left
    for i in range(7):
        add(torus(f"mta_cord_{i}", (-0.238 + i * 0.0060,
                                    -0.200 - abs(3 - i) * 0.0032, PZ + 0.013),
                  0.0092, 0.0026, ebon, rot=(0, math.pi / 2, 0), mseg=14,
                  nseg=6))

    bpy.ops.object.empty_add(location=HAND_PIVOT)
    hand_piv = bpy.context.object
    hand_piv.name = "mta_handset_pivot"

    hand_objs = [
        box("mta_hand_bar", (HAND_X, -0.148, PZ + 0.036),
            (0.116, 0.026, 0.024), ebon, bevel=0.007),
        box("mta_hand_band", (HAND_X, -0.148, PZ + 0.050),
            (0.038, 0.028, 0.005), brass, bevel=0.0015),
    ]
    # earpiece (fat) and mouthpiece (slim) flare OUT toward the pilot
    for i, (hx, rr) in enumerate(((HAND_X - 0.058, 0.028),
                                  (HAND_X + 0.058, 0.021))):
        hand_objs.append(cone(f"mta_hand_cup_{i}", (hx, -0.148, PZ + 0.040),
                              0.014, rr, 0.020, ebon, verts=22))
        hand_objs.append(cyl(f"mta_hand_grille_{i}", (hx, -0.148, PZ + 0.0505),
                             rr - 0.002, 0.004, brass, verts=22, smooth=False))
        hand_objs.append(cyl(f"mta_hand_mesh_{i}", (hx, -0.148, PZ + 0.0522),
                             rr - 0.007, 0.003, ebon, verts=22, smooth=False))
    for o in hand_objs:
        add(o)
        o.parent = hand_piv
        o.matrix_parent_inverse = Matrix.Translation(-HAND_PIVOT)
    hand_piv.rotation_euler = (0, 0, 0)

    # ------------------------------------------------------------ parenting
    for o in made:
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = Matrix.Identity(4)
    hand_piv.parent = root
    hand_piv.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()

    # ---- rest configuration: what the WIDE shot shows -------------------
    rest_env = dict(QUEUE_STATES)[QUEUE_REST]
    hidden = set()
    for i, g in enumerate(cap_frames):
        if i != CAPSULE_REST:
            hidden.update(g)
    for i, g in enumerate(env_objs):
        if i >= rest_env:
            hidden.update(g)
    for nm, _ in QUEUE_STATES:
        if nm != QUEUE_REST:
            hidden.add(digits[nm])
    for o in hidden:
        o.hide_render = True

    cap_all = [o for g in cap_frames for o in g]
    env_all = [o for g in env_objs for o in g] + list(digits.values())
    moving = set(cap_all) | set(env_all) | set(wheel_objs) | set(hand_objs)
    static = [o for o in made if o not in moving]
    far = [o for o in made if o not in hidden]

    controls = {
        "capsule": {"kind": "frames", "label": "PNEUMATIC TUBE",
                    "objs": cap_all, "frame_objs": cap_frames, "pivot": None,
                    "hotspot_objs": [o for o in static
                                     if o.name.startswith(("mta_tube",
                                                           "mta_bell"))]},
        "queue": {"kind": "states", "label": "QUEUE PIGEONHOLES",
                  "objs": env_all, "pivot": None, "env_objs": env_objs,
                  "digits": digits, "states": QUEUE_STATES,
                  "ids": QUEUE_IDS, "to": QUEUE_TO,
                  "hotspot_objs": rack_static},
        "scrambler": {"kind": "rotate", "label": "STARTTLS SCRAMBLER",
                      "objs": wheel_objs, "pivot": None,
                      "anchor_local": Vector((wx, wy, PZ + 0.020)),
                      "root": root},
        "handset": {"kind": "states", "label": "COMMS HANDSET",
                    "objs": hand_objs, "pivot": hand_piv,
                    "angles": {"cradled": 0.0, "lifted": -38.0}},
    }
    return {"far": far, "controls": controls, "root": root, "static": static,
            "all": made, "hidden": hidden}


# =========================================================== render harness
def renderables(scene):
    return [o for o in scene.objects
            if o.type in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}]


def render_to(scene, path, visible):
    vis = set(visible)
    saved = {}
    for o in renderables(scene):
        saved[o.name] = o.hide_render
        o.hide_render = o not in vis
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
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
    x = min(r["x"] for r in rects)
    y = min(r["y"] for r in rects)
    return {"x": x, "y": y,
            "w": max(r["x"] + r["w"] for r in rects) - x,
            "h": max(r["y"] + r["h"] for r in rects) - y}


def clamp_rect(r, w, h):
    x0, y0 = max(0, r["x"]), max(0, r["y"])
    x1, y1 = min(w, r["x"] + r["w"]), min(h, r["y"] + r["h"])
    return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}


def fit_camera(scene, cam, objs, target, view_dir, frac=0.90, iters=4):
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
        s = min(3.0, max(0.34, max(max(xs) - min(xs),
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


def main():
    os.makedirs(OUT, exist_ok=True)
    P = dict(shell.PARAMS)
    P["exterior"] = 0
    scene = shell.build(P)
    main_cam = scene.camera
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    R = add_props(P, mats)
    scene.render.film_transparent = True
    mine = R["all"]
    ctrl = R["controls"]
    root = R["root"]
    W, H = scene.render.resolution_x, scene.render.resolution_y

    manifest = {"code": CODE, "name": NAME,
                "surface": slots.SLOTS[CODE]["surface"],
                "far": {}, "close": {"canvas": {"w": W, "h": H},
                                     "plate": "close_plate.png",
                                     "controls": {}},
                "session": SESSION}

    # ------------------------------------------------------------- far view
    far = R["far"]
    render_to(scene, os.path.join(OUT, "far_prop.png"), far)
    far_hot = clamp_rect(bbox_rect(scene, main_cam, far, pad=5), W, H)

    glow = shell.material("mta_glowmask", (0, 0, 0, 1), 0.0, 1.0,
                          emission=(1, 1, 1, 1), emit_strength=4.0)
    saved_mats = {}
    for o in far:
        saved_mats[o.name] = list(o.data.materials)
        o.data.materials.clear()
        o.data.materials.append(glow)
    render_to(scene, os.path.join(OUT, "far_glow.png"), far)
    for o in far:
        o.data.materials.clear()
        for m in saved_mats[o.name]:
            o.data.materials.append(m)

    manifest["far"] = {"prop": "far_prop.png", "glow": "far_glow.png",
                       "hotspot": far_hot}
    print("FAR HOTSPOT", far_hot)

    # ------------------------------------------------------- close-up rig
    ctr = root.matrix_world @ Vector((0.0, 0.0, PZ + 0.02))
    view = (main_cam.matrix_world.translation - ctr).normalized()
    bpy.ops.object.camera_add(location=ctr + view * 0.90)
    close_cam = bpy.context.object
    close_cam.name = "mta_closecam"
    close_cam.data.lens = 50.0
    ctr = fit_camera(scene, close_cam, mine, ctr, view, frac=0.94)

    up = (root.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
    right = view.cross(up).normalized()
    for off, energy, size, col in (
            (right * 0.50 + up * 0.46 + view * 0.34, 0.62, 0.55,
             (1.0, 0.88, 0.70)),
            (-right * 0.58 + up * 0.22 + view * 0.42, 0.40, 0.70,
             (0.64, 0.78, 1.00)),
            (up * 0.30 + view * 0.46 - right * 0.05, 0.26, 0.50,
             (1.0, 0.93, 0.80)),
            (-up * 0.44 + view * 0.36, 0.20, 0.60, (1.0, 0.84, 0.62))):
        p = ctr + off
        bpy.ops.object.light_add(type='AREA', location=p)
        L = bpy.context.object
        L.data.energy, L.data.size = energy, size
        L.data.color = col
        L.rotation_euler = (ctr - p).to_track_quat('-Z', 'Y').to_euler()

    scene.camera = close_cam
    shell_meshes = [o for o in renderables(scene) if o not in set(mine)]
    plate = shell_meshes + R["static"]
    render_to(scene, os.path.join(OUT, "close_plate.png"), plate)

    C = manifest["close"]["controls"]

    # --- capsule: a frame per position along the tube --------------------
    frames, rects = [], []
    for fi, objs in enumerate(ctrl["capsule"]["frame_objs"]):
        fn = f"close_capsule_{fi}.png"
        render_to(scene, os.path.join(OUT, fn), objs)
        frames.append(fn)
        rects.append(bbox_rect(scene, close_cam, objs, pad=8))
    rects.append(bbox_rect(scene, close_cam, ctrl["capsule"]["hotspot_objs"],
                           pad=4))
    C["capsule"] = {"kind": "frames", "label": ctrl["capsule"]["label"],
                    "frames": frames, "rest": CAPSULE_REST,
                    "hotspot": clamp_rect(union(rects), W, H)}

    # --- queue: a render per pigeonhole occupancy ------------------------
    Q = ctrl["queue"]
    states, rects = {}, []
    for nm, n in Q["states"]:
        objs = [o for g in Q["env_objs"][:n] for o in g] + [Q["digits"][nm]]
        fn = f"close_queue_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), objs)
        states[nm] = fn
        rects.append(bbox_rect(scene, close_cam, objs, pad=6))
    rects.append(bbox_rect(scene, close_cam, Q["hotspot_objs"], pad=4))
    C["queue"] = {"kind": "states", "label": Q["label"], "states": states,
                  "order": [nm for nm, _ in Q["states"]],
                  "counts": {nm: n for nm, n in Q["states"]},
                  "rest": QUEUE_REST, "ids": Q["ids"], "to": Q["to"],
                  "hotspot": clamp_rect(union(rects), W, H)}

    # --- scrambler: one render, CSS-rotated about its projected hub -------
    render_to(scene, os.path.join(OUT, "close_scrambler.png"),
              ctrl["scrambler"]["objs"])
    hub_w = root.matrix_world @ ctrl["scrambler"]["anchor_local"]
    px, py = project(scene, close_cam, hub_w)
    C["scrambler"] = {"kind": "rotate", "label": ctrl["scrambler"]["label"],
                      "image": "close_scrambler.png",
                      "pivot": {"x": round(px, 1), "y": round(py, 1)},
                      "range": [0, 1080], "detent": 30,
                      "hotspot": clamp_rect(
                          bbox_rect(scene, close_cam,
                                    ctrl["scrambler"]["objs"], pad=8), W, H)}

    # --- handset: on-hook / off-hook -------------------------------------
    piv = ctrl["handset"]["pivot"]
    states, rects = {}, []
    for nm in ("cradled", "lifted"):
        piv.rotation_euler = (math.radians(ctrl["handset"]["angles"][nm]), 0, 0)
        bpy.context.view_layer.update()
        fn = f"close_handset_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), ctrl["handset"]["objs"])
        states[nm] = fn
        rects.append(bbox_rect(scene, close_cam, ctrl["handset"]["objs"],
                               pad=8))
    piv.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    C["handset"] = {"kind": "states", "label": ctrl["handset"]["label"],
                    "states": states, "order": ["cradled", "lifted"],
                    "rest": "cradled",
                    "hotspot": clamp_rect(union(rects), W, H)}

    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    # standalone review page, manifest INLINED (file:// blocks fetch)
    src = os.path.join(HERE, "demo.src.html")
    if os.path.exists(src):
        with open(src) as f:
            page = f.read()
        with open(os.path.join(HERE, "demo.html"), "w") as f:
            f.write(page.replace("__MANIFEST__", json.dumps(manifest)))

    print("HOTSPOTS", json.dumps(
        {k: v["hotspot"] for k, v in C.items()}, indent=1))
    print("MTA OK ->", OUT)


if __name__ == "__main__":
    main()
