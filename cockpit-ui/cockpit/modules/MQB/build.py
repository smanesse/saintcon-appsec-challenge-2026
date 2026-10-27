"""
MQB -- mqtt-module  ->  DRONE TELEMETRY BUS / SWITCHBOARD
Cockpit control for the SAINTCON 2026 AppSec Challenge UI.

Slot: the CEILING -- hanging watch/listen infrastructure you reach up to.

    !! THE SURFACE NOTE THAT DROVE THE WHOLE DESIGN !!
    slots.ceiling() returns euler (pi, 0, -a): local +Z (the "outward" normal)
    points STRAIGHT DOWN at the floor.  The pilot camera sits 0.66 m BELOW and
    2.27 m in FRONT of the MQB slot point, i.e. only ~16 deg above the plane of
    a flat down-facing panel -- so a flat panel on that surface is essentially
    edge-on and invisible (you can see it in renders/SLOTCHECK.png: the MQB
    marker plate is a hairline).  Happily the same euler makes local +Y point
    almost exactly horizontally AT the pilot.  So this prop is a RAKED hanging
    cabinet: the working face is tilted RAKE=18 deg off vertical, normal
    n = (0, cos R, sin R) in slot-local space, which aims within 2 deg of the
    pilot's eye.  Everything is authored in that face frame via face_pt().

The control is an operator's patch bay / switchboard:

    scope     (frames)  -- round CRT oscilloscope, green phosphor trace of live
                           bus traffic; 10 frames scroll the trace.
    patch     (states)  -- 5 labelled TOPIC jacks over 5 SUBSCRIBER jacks, and
                           real patch cords you plug between them.  The last
                           topic jack is `#` -- the PARTY LINE, red ring.
                           states: idle -> one -> two -> party
    retained  (states)  -- the lamp that STAYS LIT after the caller hangs up.
                           clear  : nothing retained
                           live   : caller on the line (green pip lit)
                           retained: caller gone (pip dark) but the lamp still
                                     burns and a brass HELD tab has dropped.
    keepalive (rotate)  -- PINGREQ keep-alive meter; one render, spun in CSS.

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

CODE = "MQB"
NAME = "Drone Telemetry Bus"
SURFACE = slots.SLOTS[CODE]["surface"]
OUT = os.path.join(HERE, "out")

# --------------------------------------------------------------- face frame
# Slot-local: +X right along the surface, +Y toward the pilot (horizontal),
# +Z straight DOWN.  The working face is raked RAKE off vertical so its normal
# points down-and-forward, at the pilot.
RAKE = math.radians(18.0)
NRM = Vector((0.0, math.cos(RAKE), math.sin(RAKE)))     # face normal
UPV = Vector((0.0, math.sin(RAKE), -math.cos(RAKE)))    # "up" along the face
# --- SIZE.  The ceiling props sit ~2.1 m from the pilot against ~2.9 m for the
# dash, so perspective inflated them: this prop's far hotspot was 278 px wide
# against 160-221 px for every dash/fascia control, and it ran off the top of
# frame.  SCALE shrinks the whole prop uniformly via root.scale.  The two
# ABSOLUTE anchors below (the face centre and the ceiling plane) are pre-divided
# by SCALE, so the scaling happens ABOUT THE FACE CENTRE: the working face keeps
# its world position, its 18 deg rake and its ceiling attachment -- only the size
# changes, and the hanger stalks stretch to make up the difference.
SCALE = 0.70
FACE_C = Vector((-0.128, 0.148, 0.095)) / SCALE         # face centre, slot-local
FACE_ROT = (RAKE - math.pi / 2, 0.0, 0.0)               # lay a +Z thing on it

PW, PH = 0.480, 0.340          # working face size
BODY_D = 0.180                 # how far the cabinet slab goes back
CEIL_Z = -0.300 / SCALE        # slot-local Z of the ceiling (drop = 0.30)

# --- scope
SC_X, SC_Y = -0.134, 0.010
SC_BEZEL, SC_FACE = 0.092, 0.076
SCOPE_FRAMES = 10

# --- patch bay
JX = [-0.012 + i * 0.056 for i in range(5)]
JY_TOP, JY_BOT = -0.032, -0.122
JY_LABEL = 0.014                # topic name strip, ABOVE the top row, so the
JY_SUBS = -0.152                # cords never cross a label
JACK_R = 0.016
TOPICS = ["drone/+", "hull/temp", "nav/fix", "will/lost", "#"]
# state -> [(topic jack, subscriber jack, cord colour)]
PATCH = {
    "idle":  [],
    "one":   [(0, 1, "red")],
    "two":   [(0, 1, "red"), (2, 4, "blue")],
    "party": [(0, 1, "red"), (2, 4, "blue"), (4, 2, "amber")],
}
PATCH_ORDER = ["idle", "one", "two", "party"]
PATCH_FAR = "party"            # what the wide shot shows

# --- retained lamp
RT_X, RT_Y = -0.010, 0.105
RETAINED_ORDER = ["clear", "live", "retained"]

# --- keep-alive meter
KA_X, KA_Y = 0.115, 0.100
KA_BEZEL, KA_FACE = 0.050, 0.042
KA_RANGE = [-118.0, 118.0]

# --- will card
WC_X, WC_Y = 0.205, 0.100


def face_pt(px, py, h=0.0):
    """A point on (or h out from) the raked working face, in slot-local space."""
    return FACE_C + Vector((px, 0.0, 0.0)) + UPV * py + NRM * h


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


def tube(name, center, r_out, r_in, depth, mat, rot=(0, 0, 0), verts=40):
    """A flat annulus ring (jack collar / instrument bezel), built from pydata
    so there is no boolean modifier to go wrong."""
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
        faces.append((a + 0, a + 1, b + 1, b + 0))   # bottom
        faces.append((a + 1, a + 2, b + 2, b + 1))   # outside
        faces.append((a + 2, a + 3, b + 3, b + 2))   # top
        faces.append((a + 3, a + 0, b + 0, b + 3))   # inside
    o = shell.mesh_from(name, vs, faces, mat, True)
    o.location = center
    o.rotation_euler = rot
    return o


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
    cu.extrude = 0.00035
    f = mono_font()
    if f:
        cu.font = f
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat)
    return o


def polytube(name, pts, radius, mat, verts=10):
    """A round tube swept along a polyline given in slot-local coordinates."""
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
    o.data.materials.append(mat)
    return o


def mat(name, base, metallic=0.0, rough=0.5, emission=None, strength=0.0):
    return shell.material("mqb_" + name, base, metallic, rough,
                          emission=emission, emit_strength=strength)


# ------------------------------------------------------------- scope signal
def bus_wave(s):
    """Deterministic MQTT-ish bus traffic: a noisy baseline with packet bursts."""
    v = 0.055 * math.sin(s * 197.0) + 0.035 * math.sin(s * 91.0 + 1.1)
    for c0, w, h in ((0.000, 0.0085, 0.74), (0.052, 0.0055, 0.42),
                     (0.081, 0.0120, 0.92), (0.139, 0.0070, 0.55),
                     (0.176, 0.0045, 0.33)):
        d = (s - c0) % 0.2200
        if d > 0.1100:
            d -= 0.2200
        if abs(d) < w:
            k = math.cos(math.pi * d / (2 * w)) ** 2
            sign = 1.0 if int(math.floor((s - c0) / 0.2200)) % 2 == 0 else -1.0
            v += h * k * sign
    return max(-0.94, min(0.94, v))


def trace_mesh(name, phase, width, mat_, h):
    """A ribbon following bus_wave(), clipped inside the CRT face circle."""
    R = SC_FACE * 0.93
    n = 150
    pts = []
    for i in range(n):
        u = -R + 2 * R * i / (n - 1)
        lim = math.sqrt(max(0.0, SC_FACE * SC_FACE - u * u)) * 0.90
        v = bus_wave(u + phase) * SC_FACE * 0.72
        pts.append((u, max(-lim, min(lim, v))))
    verts, faces = [], []
    for i, (u, v) in enumerate(pts):
        if i == 0:
            du, dv = pts[1][0] - u, pts[1][1] - v
        elif i == n - 1:
            du, dv = u - pts[-2][0], v - pts[-2][1]
        else:
            du, dv = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        L = math.hypot(du, dv) or 1.0
        nx, ny = -dv / L, du / L
        verts.append(face_pt(SC_X + u + nx * width / 2,
                             SC_Y + v + ny * width / 2, h))
        verts.append(face_pt(SC_X + u - nx * width / 2,
                             SC_Y + v - ny * width / 2, h))
    for i in range(n - 1):
        b = i * 2
        faces.append((b, b + 2, b + 3, b + 1))
    return shell.mesh_from(name, verts, faces, mat_, False)


def cord_points(i, j, n=26):
    """Cubic bezier for a patch cord: out of the panel, drooping, back in."""
    p0 = Vector((JX[i], JY_TOP, 0.020))
    p3 = Vector((JX[j], JY_BOT, 0.020))
    c1 = Vector((JX[i], JY_TOP - 0.056, 0.082))
    c2 = Vector((JX[j], JY_BOT - 0.062, 0.080))
    out = []
    for k in range(n):
        t = k / (n - 1)
        m = 1 - t
        q = (p0 * (m ** 3) + c1 * (3 * m * m * t)
             + c2 * (3 * m * t * t) + p3 * (t ** 3))
        out.append(face_pt(q.x, q.y, q.z))
    return out


# ----------------------------------------------------------------- the prop
def add_props(P, mats):
    """Add the MQB switchboard to the CURRENT scene."""
    brass = mats["brass"]
    hull = mats["hull"]
    hull_d = mats["hull_d"]

    case = mat("case", (0.048, 0.052, 0.062, 1), 0.18, 0.46)
    ebon = mat("ebon", (0.028, 0.028, 0.032, 1), 0.0, 0.32)
    ivory = mat("ivory", (0.870, 0.845, 0.755, 1), 0.0, 0.62)
    ink = mat("ink", (0.055, 0.050, 0.052, 1), 0.0, 0.62)
    crt = mat("crt", (0.020, 0.045, 0.032, 1), 0.0, 0.20)
    grat = mat("grat", (0.090, 0.230, 0.140, 1), 0.0, 0.55)
    phos = mat("phos", (0.180, 0.620, 0.260, 1), 0.0, 0.30,
               emission=(0.24, 1.0, 0.36, 1), strength=2.6)
    red_off = mat("red_off", (0.135, 0.028, 0.030, 1), 0.0, 0.42)
    red_on = mat("red_on", (0.500, 0.075, 0.052, 1), 0.0, 0.50,
                 emission=(1.0, 0.15, 0.085, 1), strength=1.2)
    grn_off = mat("grn_off", (0.035, 0.080, 0.050, 1), 0.0, 0.42)
    grn_on = mat("grn_on", (0.170, 0.560, 0.260, 1), 0.0, 0.42,
                 emission=(0.22, 1.0, 0.36, 1), strength=1.4)
    amber = mat("amber", (0.760, 0.520, 0.150, 1), 0.0, 0.30,
                emission=(1.0, 0.62, 0.18, 1), strength=1.8)
    party_m = mat("party", (0.480, 0.090, 0.070, 1), 0.42, 0.32)
    cord_c = {"red": mat("cord_red", (0.520, 0.075, 0.070, 1), 0.0, 0.42),
              "blue": mat("cord_blue", (0.110, 0.230, 0.470, 1), 0.0, 0.42),
              "amber": mat("cord_amber", (0.620, 0.400, 0.070, 1), 0.0, 0.42)}

    loc, eul = slots.place(P, CODE)
    bpy.ops.object.empty_add(location=loc)
    root = bpy.context.object
    root.name = "mqb_root"
    root.rotation_euler = eul
    root.scale = (SCALE, SCALE, SCALE)      # see SCALE, above

    made = []

    def add(o):
        made.append(o)
        return o

    # ------------------------------------------------- hangers + ceiling pad
    add(box("mqb_ceilpad", (FACE_C.x, 0.045, CEIL_Z + 0.007),
            (0.470, 0.150, 0.014), hull_d, bevel=0.004))
    for i, px in enumerate((-0.200, 0.0, 0.200)):
        t = face_pt(px, PH / 2 - 0.010, -BODY_D + 0.020)
        h = abs(t.z - CEIL_Z)
        add(box(f"mqb_stalk_{i}", (t.x, t.y, (t.z + CEIL_Z) / 2),
                (0.036, 0.036, h), hull_d, bevel=0.005))
        add(cyl(f"mqb_stalk_{i}_collar", (t.x, t.y, t.z - 0.020),
                0.028, 0.016, brass, verts=20))

    # ------------------------------------------------------ the raked slab
    add(box("mqb_cabinet", face_pt(0, 0, -BODY_D / 2 - 0.010),
            (PW + 0.020, PH + 0.020, BODY_D), case, rot=FACE_ROT, bevel=0.008))
    add(box("mqb_panel", face_pt(0, 0, -0.009),
            (PW, PH, 0.018), hull, rot=FACE_ROT, bevel=0.003))
    add(box("mqb_panel_trim", face_pt(0, 0, -0.014),
            (PW + 0.022, PH + 0.022, 0.014), brass, rot=FACE_ROT, bevel=0.003))
    # side cheeks
    for i, sx in enumerate((-1, 1)):
        add(box(f"mqb_cheek_{i}",
                face_pt(sx * (PW / 2 + 0.016), 0, -BODY_D / 2 - 0.010),
                (0.018, PH + 0.030, BODY_D + 0.010), brass, rot=FACE_ROT,
                bevel=0.003))
    # glare hood over the top, brass sill under the bottom
    add(box("mqb_hood", face_pt(0, PH / 2 + 0.020, 0.030),
            (PW + 0.036, 0.030, 0.078), brass, rot=FACE_ROT, bevel=0.004))
    add(box("mqb_sill", face_pt(0, -PH / 2 - 0.020, 0.014),
            (PW + 0.036, 0.032, 0.046), brass, rot=FACE_ROT, bevel=0.004))
    add(text("mqb_nameplate", "MQB  DRONE TELEMETRY BUS", 0.0134, ink,
             face_pt(0, -PH / 2 - 0.020, 0.0392), FACE_ROT))

    # --------------------------------------------------------- oscilloscope
    add(tube("mqb_scope_bezel", face_pt(SC_X, SC_Y, 0.002),
             SC_BEZEL, SC_FACE - 0.002, 0.026, brass, rot=FACE_ROT, verts=44))
    add(cyl("mqb_scope_face", face_pt(SC_X, SC_Y, 0.004), SC_FACE, 0.004,
            crt, rot=FACE_ROT, verts=44))
    for i in range(-3, 4):
        off = i * SC_FACE / 4.0
        halflen = math.sqrt(max(0.0, SC_FACE ** 2 - off ** 2)) * 0.985
        if halflen < 0.004:
            continue
        add(box(f"mqb_grat_h_{i + 3}", face_pt(SC_X, SC_Y + off, 0.0068),
                (halflen * 2, 0.0012, 0.0010), grat, rot=FACE_ROT))
        add(box(f"mqb_grat_v_{i + 3}", face_pt(SC_X + off, SC_Y, 0.0068),
                (0.0012, halflen * 2, 0.0010), grat, rot=FACE_ROT))
    add(text("mqb_scope_cap", "BUS TRAFFIC", 0.0125, ivory,
             face_pt(SC_X, -0.118, 0.0102), FACE_ROT))
    add(box("mqb_reg_plate", face_pt(SC_X, -0.148, 0.0100),
            (0.180, 0.024, 0.004), brass, rot=FACE_ROT, bevel=0.001))
    add(text("mqb_reg_txt", "CLIENTS 07  RETAIN 3", 0.0098, ink,
             face_pt(SC_X, -0.148, 0.0132), FACE_ROT))

    # the trace: one mesh per frame, only frame 0 is in the wide shot
    scope_frames = []
    for fi in range(SCOPE_FRAMES):
        ph = 0.2200 * fi / SCOPE_FRAMES
        t = trace_mesh(f"mqb_trace_{fi}", ph, 0.0038, phos, 0.0092)
        if fi:
            t.hide_render = True
        scope_frames.append(add(t))

    # ------------------------------------------------------------ patch bay
    # topic names go ABOVE the top row, so a patch cord never hides a label
    add(box("mqb_strip_top", face_pt(0.100, JY_LABEL, 0.0060),
            (0.278, 0.021, 0.003), ivory, rot=FACE_ROT))
    add(box("mqb_strip_bot", face_pt(0.100, JY_SUBS, 0.0080),
            (0.278, 0.020, 0.004), brass, rot=FACE_ROT, bevel=0.001))
    add(text("mqb_strip_bot_txt", "SUBSCRIBERS", 0.0105, ink,
             face_pt(0.100, JY_SUBS, 0.0110), FACE_ROT))

    jack_static = []
    for i, px in enumerate(JX):
        party = (i == len(JX) - 1)
        ring = party_m if party else brass
        for row, py in (("t", JY_TOP), ("s", JY_BOT)):
            jack_static.append(add(tube(
                f"mqb_jack_{row}_{i}", face_pt(px, py, 0.0050),
                JACK_R, JACK_R - 0.0055, 0.010,
                ring if row == "t" else brass, rot=FACE_ROT, verts=22)))
            jack_static.append(add(cyl(
                f"mqb_hole_{row}_{i}", face_pt(px, py, 0.0022),
                JACK_R - 0.0050, 0.004, ebon, rot=FACE_ROT, verts=20)))
        jack_static.append(add(text(
            f"mqb_topic_{i}", TOPICS[i], 0.0148 if party else 0.0090, ink,
            face_pt(px, JY_LABEL, 0.0086), FACE_ROT)))

    # cords, one object set per state
    patch_objs = {}
    for nm, cords in PATCH.items():
        objs = []
        for k, (ti, si, col) in enumerate(cords):
            pts = cord_points(ti, si)
            c = polytube(f"mqb_cord_{nm}_{k}", pts, 0.0052, cord_c[col])
            objs.append(c)
            for e, (px, py) in enumerate(((JX[ti], JY_TOP), (JX[si], JY_BOT))):
                objs.append(cyl(f"mqb_plug_{nm}_{k}_{e}",
                                face_pt(px, py, 0.0165),
                                JACK_R - 0.0042, 0.030, brass, rot=FACE_ROT,
                                verts=18))
                objs.append(cyl(f"mqb_plugcap_{nm}_{k}_{e}",
                                face_pt(px, py, 0.0290),
                                JACK_R - 0.0005, 0.014, ebon, rot=FACE_ROT,
                                verts=18))
        for o in objs:
            if nm != PATCH_FAR:
                o.hide_render = True
            add(o)
        patch_objs[nm] = objs

    # ----------------------------------------------------- retained-message
    add(tube("mqb_rt_ring", face_pt(RT_X, RT_Y, 0.004), 0.032, 0.024, 0.016,
             brass, rot=FACE_ROT, verts=30))
    add(text("mqb_rt_label", "RETAINED", 0.0100, ivory,
             face_pt(RT_X, RT_Y - 0.044, 0.0086), FACE_ROT))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.025, segments=22,
                                         ring_count=12,
                                         location=face_pt(RT_X, RT_Y, 0.010))
    dome = bpy.context.object
    dome.name = "mqb_rt_dome"
    dome.scale = (1.0, 1.0, 0.58)
    dome.rotation_euler = FACE_ROT
    for f in dome.data.polygons:
        f.use_smooth = True
    dome.data.materials.append(red_on)
    add(dome)

    # "caller on the line" pip -- dark once the caller hangs up
    add(tube("mqb_pip_ring", face_pt(RT_X + 0.046, RT_Y + 0.018, 0.004),
             0.0125, 0.0090, 0.010, brass, rot=FACE_ROT, verts=18))
    pip = cyl("mqb_pip", face_pt(RT_X + 0.046, RT_Y + 0.018, 0.0070),
              0.0095, 0.006, grn_off, rot=FACE_ROT, verts=18)
    add(pip)
    add(text("mqb_pip_label", "LINE", 0.0072, ivory,
             face_pt(RT_X + 0.046, RT_Y - 0.004, 0.0086), FACE_ROT))

    # the brass HELD tab: drops only when a retained message is being held
    held = []
    held.append(box("mqb_held_tab", face_pt(RT_X - 0.058, RT_Y, 0.0110),
                    (0.044, 0.024, 0.006), brass, rot=FACE_ROT, bevel=0.001))
    held.append(text("mqb_held_txt", "HELD", 0.0100, ink,
                     face_pt(RT_X - 0.058, RT_Y, 0.0152), FACE_ROT))
    for o in held:
        add(o)

    # ------------------------------------------------------ keep-alive meter
    ka_static = []
    ka_static.append(add(tube("mqb_ka_bezel", face_pt(KA_X, KA_Y, 0.003),
                              KA_BEZEL, KA_FACE - 0.002, 0.020, brass,
                              rot=FACE_ROT, verts=36)))
    ka_static.append(add(cyl("mqb_ka_face", face_pt(KA_X, KA_Y, 0.005),
                             KA_FACE, 0.004, ivory, rot=FACE_ROT, verts=36)))
    for i in range(9):
        th = math.radians(-118 + 236 * i / 8)
        rr = KA_FACE - 0.008
        ka_static.append(add(box(
            f"mqb_ka_tick_{i}",
            face_pt(KA_X + math.sin(th) * rr, KA_Y + math.cos(th) * rr, 0.0076),
            (0.0022, 0.0110, 0.0012), ink,
            rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                 @ Euler((0, 0, -th), 'XYZ').to_matrix()).to_euler())))
    ka_static.append(add(text("mqb_ka_label", "KEEP ALIVE", 0.0084, ink,
                              face_pt(KA_X, KA_Y - 0.020, 0.0080), FACE_ROT)))
    ka_static.append(add(text("mqb_ka_units", "PINGREQ", 0.0066, ink,
                              face_pt(KA_X, KA_Y - 0.032, 0.0080), FACE_ROT)))

    # needle rendered ONCE pointing straight up; the browser spins it
    needle = []
    needle.append(add(box("mqb_ka_needle",
                          face_pt(KA_X, KA_Y + 0.016, 0.0110),
                          (0.0038, 0.0340, 0.0026), red_on, rot=FACE_ROT)))
    needle.append(add(cyl("mqb_ka_hub", face_pt(KA_X, KA_Y, 0.0118),
                          0.0072, 0.0060, brass, rot=FACE_ROT, verts=16)))

    # ------------------------------------------------------------ will card
    add(box("mqb_will_back", face_pt(WC_X, WC_Y, 0.0060),
            (0.050, 0.090, 0.004), ebon, rot=FACE_ROT))
    add(box("mqb_will_card", face_pt(WC_X, WC_Y, 0.0090),
            (0.044, 0.082, 0.003), ivory, rot=FACE_ROT))
    add(box("mqb_will_band", face_pt(WC_X, WC_Y + 0.032, 0.0110),
            (0.044, 0.017, 0.002), red_off, rot=FACE_ROT))
    add(text("mqb_will_t0", "WILL", 0.0104, ivory,
             face_pt(WC_X, WC_Y + 0.032, 0.0128), FACE_ROT))
    for i, ln in enumerate(("IF THIS", "LINE", "DROPS", "PLAY", "THIS")):
        add(text(f"mqb_will_l{i}", ln, 0.0068, ink,
                 face_pt(WC_X, WC_Y + 0.013 - i * 0.0115, 0.0110), FACE_ROT))
    add(box("mqb_will_clip", face_pt(WC_X, WC_Y - 0.048, 0.0110),
            (0.028, 0.010, 0.006), brass, rot=FACE_ROT, bevel=0.001))

    # ------------------------------------------------------------ parenting
    for o in made:
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()

    moving = set(scope_frames) | set(needle) | set(held) | {dome, pip}
    for objs in patch_objs.values():
        moving |= set(objs)
    static = [o for o in made if o not in moving]
    far = static + [scope_frames[0], dome, pip] + held + needle \
        + list(patch_objs[PATCH_FAR])

    controls = {
        "scope": {"kind": "frames", "label": "BUS TRAFFIC",
                  "objs": scope_frames, "frame_objs": scope_frames,
                  "pivot": None,
                  "hotspot_pts": [face_pt(SC_X + dx * SC_BEZEL,
                                          SC_Y + dy * SC_BEZEL, 0.010)
                                  for dx in (-1, 1) for dy in (-1, 1)]},
        "patch": {"kind": "states", "label": "PATCH BAY",
                  "objs": [o for v in patch_objs.values() for o in v],
                  "state_objs": patch_objs, "order": PATCH_ORDER,
                  "pivot": None, "topics": TOPICS,
                  "hotspot_objs": jack_static},
        "retained": {"kind": "states", "label": "RETAINED MESSAGE",
                     "objs": [dome, pip] + held, "pivot": None,
                     "dome": dome, "pip": pip, "held": held,
                     "order": RETAINED_ORDER,
                     "mats": {"lamp_off": red_off, "lamp_on": red_on,
                              "pip_off": grn_off, "pip_on": grn_on}},
        "keepalive": {"kind": "rotate", "label": "KEEP ALIVE",
                      "objs": needle, "pivot": None,
                      "anchor": face_pt(KA_X, KA_Y, 0.0118),
                      "range": KA_RANGE, "hotspot_objs": ka_static},
    }
    return {"far": far, "controls": controls, "root": root,
            "static": static, "all": made, "amber": amber}


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
    g = shell.material("mqb_glowmask", (1, 1, 1, 1), 0.0, 0.5,
                       emission=(1, 1, 1, 1), emit_strength=1.0)
    saved = {}
    for o in objs:
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
        for i, m in enumerate(saved[o.name]):
            o.data.materials[i] = m


def close_rig(root):
    """Close-up camera + local lights, parented into the slot frame."""
    bpy.ops.object.camera_add(location=(0, 0, 0))
    cam = bpy.context.object
    cam.name = "mqb_closecam"
    cam.data.lens = 50.0
    cam.parent = root
    cam.matrix_parent_inverse = Matrix.Identity(4)
    # dead on the face normal: +Z along NRM means the camera looks down -NRM
    cam.location = face_pt(0.0, -0.002, 1.075)
    cam.rotation_euler = FACE_ROT

    lights = []
    for i, (fp, energy, size, col) in enumerate([
            ((-0.30, 0.26, 0.42), 0.30, 0.30, (1.00, 0.90, 0.76)),
            ((0.34, 0.14, 0.44), 0.20, 0.34, (0.72, 0.82, 1.00)),
            ((0.02, -0.30, 0.34), 0.16, 0.26, (1.00, 0.86, 0.66)),
            ((-0.02, 0.34, 0.20), 0.11, 0.22, (1.00, 0.84, 0.62))]):
        bpy.ops.object.light_add(type='AREA', location=(0, 0, 0))
        L = bpy.context.object
        L.name = f"mqb_light_{i}"
        # root.scale pulls these lights SCALE x closer to the (now smaller)
        # face, so energy has to fall with the square of the distance or the
        # close-up would brighten by 1/SCALE**2.
        L.data.energy, L.data.size = energy * SCALE ** 2, size
        L.data.color = col
        L.parent = root
        L.matrix_parent_inverse = Matrix.Identity(4)
        L.location = face_pt(*fp)
        d = face_pt(fp[0] * 0.25, fp[1] * 0.25, 0.0) - L.location
        L.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        lights.append(L)
    return cam, lights


HTML = """<!doctype html>
<meta charset="utf-8">
<title>MQB - Drone Telemetry Bus / Switchboard</title>
<style>
 body{margin:0;background:#0a0c10;color:#cbb48a;
      font:13px/1.5 ui-monospace,Menlo,monospace}
 header{padding:14px 18px;border-bottom:1px solid #2a2318}
 h1{margin:0;font-size:15px;letter-spacing:.18em;color:#e2c489}
 header p{margin:6px 0 0;color:#7d7360;max-width:80ch}
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
 <h1>MQB &middot; DRONE TELEMETRY BUS / SWITCHBOARD</h1>
 <p>Overhead patch bay, hanging from the ceiling and raked down at the pilot.
    Drag across the <b>oscilloscope</b> to run the bus trace. Click the
    <b>patch bay</b> to jack cords from a topic line into a subscriber &mdash;
    the last jack is <code>#</code>, the party line. Click <b>RETAINED</b>:
    clear &rarr; caller on the line &rarr; caller hung up and the lamp
    <i>stays lit</i>. Drag the <b>KEEP ALIVE</b> needle for PINGREQ.</p>
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
    const keys = c.order || Object.keys(c.states);
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
      // 0deg = the needle standing straight up out of its pivot
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
    far_objs = res["far"]
    ctl = res["controls"]
    root = res["root"]
    W, H = scene.render.resolution_x, scene.render.resolution_y
    shell_meshes = [o for o in renderables(scene) if o not in mine]

    # ------------------------------------------------------------- far shot
    # holdout the shell so the pillar / overhead pod in front of the prop
    # correctly clip the sprite instead of the sprite floating over them.
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

    plate = shell_meshes + res["static"]
    clip = res["static"]        # static panel geometry sprites must be cut by
    render_to(scene, os.path.join(OUT, "close_plate.png"), plate)

    controls = {}

    # --- SCOPE: a frame per phase of the trace ---------------------------
    c = ctl["scope"]
    frames = []
    for fi, o in enumerate(c["frame_objs"]):
        fn = f"close_scope_{fi}.png"
        render_to(scene, os.path.join(OUT, fn), [o], holdout=clip)
        frames.append(fn)
    controls["scope"] = {
        "kind": "frames", "label": c["label"], "frames": frames,
        "hotspot": clamp_rect(pts_rect(scene, cam, root, c["hotspot_pts"],
                                       pad=8), W, H)}

    # --- PATCH BAY: cords plugged / unplugged ----------------------------
    c = ctl["patch"]
    states, rects = {}, [bbox_rect(scene, cam, c["hotspot_objs"], pad=10)]
    for nm in c["order"]:
        objs = c["state_objs"][nm]
        fn = f"close_patch_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), objs, holdout=clip)
        states[nm] = fn
        if objs:
            rects.append(bbox_rect(scene, cam, objs, pad=8))
    controls["patch"] = {
        "kind": "states", "label": c["label"], "states": states,
        "order": c["order"], "topics": c["topics"],
        "hotspot": clamp_rect(union(rects), W, H)}

    # --- RETAINED: the lamp that stays lit -------------------------------
    c = ctl["retained"]
    M = c["mats"]
    poses = {"clear":    ("lamp_off", "pip_off", False),
             "live":     ("lamp_on", "pip_on", False),
             "retained": ("lamp_on", "pip_off", True)}
    states, rects = {}, []
    for nm in c["order"]:
        lm, pm, tab = poses[nm]
        c["dome"].data.materials[0] = M[lm]
        c["pip"].data.materials[0] = M[pm]
        vis = [c["dome"], c["pip"]] + (c["held"] if tab else [])
        fn = f"close_retained_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), vis, holdout=clip)
        states[nm] = fn
        rects.append(bbox_rect(scene, cam, vis, pad=10))
    c["dome"].data.materials[0] = M["lamp_on"]
    c["pip"].data.materials[0] = M["pip_off"]
    controls["retained"] = {
        "kind": "states", "label": c["label"], "states": states,
        "order": c["order"], "hotspot": clamp_rect(union(rects), W, H)}

    # --- KEEP ALIVE: one render, spun in CSS -----------------------------
    c = ctl["keepalive"]
    render_to(scene, os.path.join(OUT, "close_keepalive.png"), c["objs"],
              holdout=clip)
    px, py = project(scene, cam, root.matrix_world @ c["anchor"])
    controls["keepalive"] = {
        "kind": "rotate", "label": c["label"], "image": "close_keepalive.png",
        "pivot": {"x": round(px, 1), "y": round(py, 1)}, "range": c["range"],
        "hotspot": clamp_rect(
            bbox_rect(scene, cam, c["hotspot_objs"], pad=8), W, H)}

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

    print("MQB far hotspot", json.dumps(far_hot))
    for k, v in controls.items():
        print("MQB close", k, v["kind"], json.dumps(v["hotspot"]))
    print("MQB OK ->", OUT)


if __name__ == "__main__":
    main()
