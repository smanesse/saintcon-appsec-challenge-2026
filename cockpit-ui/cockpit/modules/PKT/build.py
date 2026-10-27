"""
PKT -- THE SIGNAL HARPOON  ->  packet transmitter / directional transceiver.
Cockpit control for the SAINTCON 2026 AppSec Challenge UI.

Slot: the DASH, dead centre (angle 0).  This is the offensive console -- the one
control that sends packets OUT INTO THE VOID at automated systems (derelicts,
unmanned relays, listening posts) and REELS BACK whatever they answer.  Every
other built control is defensive maintenance of your own hull; this is the
weapon, and it must dominate the dash.  Design authority:
    modules/PACKET_PANEL_PLAN.md   (v3, owner-reviewed -- implemented, not
                                    redesigned; deviations are listed in
                                    "PLAN DEVIATIONS" below.)

    !! WHY THIS IS A RAKED CONSOLE, NOT A FLAT PLATE !!
    slots.dash() rakes the dash only 24.3 deg off horizontal, and the pilot's
    eye sits ~58 deg off that surface normal.  A control modelled FLAT on the
    slot's XY plane -- as the plan's §3 convention literally says -- projects to
    ~192 x 42 px in the wide shot: the 0.34 m of panel height collapses to
    nothing and every instrument on it is unreadable.  So, exactly as KVS and
    MQB do on their own surfaces, the plan's §3 layout table is authored on a
    CONSOLE FACE raked RAKE=44 deg up off the dash plane (face normal lands 13
    deg off the pilot's eye).  Plan-local (x, y) map 1:1 onto that face via
    F(x, y, h); nothing in the layout moved.  The whole console is then scaled
    by S so it reads at the size §8.2 asks for.

Two lobes, seven controls, all three animation techniques:

    SEND lobe (left + centre)
      target  (rotate)  -- knurled azimuth hand-wheel + index pointer over an
                           engraved bearing arc, above a green contact scope
                           whose blips are automated systems out in the void.
      payload (frames)  -- 8-chamber munition drum, axis X; the seated shell's
                           exploit class lights in the breech window.
      charge  (frames)  -- 5 frames, axis Y; a sliding capacitor lever spools
                           the vacuum-tube bank from dim amber to white-hot and
                           walks a 5-pip ladder into the redline.
      arm     (states)  -- red break-glass cage + master-arm toggle.
                           safe / armed / interlock (arming refused).
      fire    (states)  -- ridged red plunger in a hazard-striped guard.
                           ready / fired (muzzle flash at the bore).

    CATCH lobe (right) -- a FIRST-CLASS half of the panel, not a strip
      catch   (frames + LIVE TEXT) -- the catch-printer.  4 baked motion frames
                           (twin return-line spools turn, blank platen advances)
                           carry the ACT of receiving; the returned bytes are
                           arbitrary and unknown at render time, so the aperture
                           is authored DELIBERATELY EMPTY and its rect is
                           exported in plate pixels as close.controls.catch
                           .overlay.rect for the frontend to paint live,
                           selectable monospace text into.  This is KVS's
                           baked-aperture + live-HTML-text precedent generalised
                           to runtime-unknown content.
      verdict (states)  -- idle / hit / refused / deflected.  A SMALL 3-lamp
                           column plus a tinted header bar that ANNOTATES the
                           printout.  The return is CONTENT; this is only its
                           colour.  Its header string is live too (exported as
                           verdict.overlay.rect).

PLAN DEVIATIONS (all sanctioned by the plan's own §8, all reported):
  * Raked console face instead of a flat XY plate -- see the block above.
  * Uniform scale S = 1.15 on the plan's §3 table ("Dial via face width and t",
    §8.2).  The plan's ~380-440 px far-view estimate assumed a bigger px/metre
    than the shell's 18 mm lens actually gives (234 px/m at the dash centre);
    0.82 m would land at 192 px.  S = 1.15 + the standing bore/printer masses
    give the largest silhouette on the dash without eating the canopy.
  * t = 0.40 rather than 0.50, so the console's footprint stays inside the dash
    run and its top edge only just crosses the sill line.
  * Tube bank is 4 tubes at x -0.256..-0.148 rather than 5 centred on -0.150:
    5 tubes collided with the bore yoke.  Still "flanking the bore", per §1.
  * catch overlay style is "ink" (dark type on the pale platen) rather than the
    sample JSON's "phosphor" -- §3.1 allows either and the geometry is a paper
    teleprinter.  Colour hints are exported alongside.

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

CODE = "PKT"
NAME = "Signal Harpoon"
SURFACE = "dash"
OUT = os.path.join(HERE, "out")

# --------------------------------------------------------------- placement
# No "PKT" row exists in slots.SLOTS yet and module agents may not edit
# slots.py, so we call the public slots.dash() directly.  A human should add
#     "PKT": {"surface": "dash", "angle": 0.0, "t": 0.40}
# and this build then becomes slots.place(P, "PKT") with no other change.
SLOT_ANGLE = 0.0
SLOT_T = 0.40

# ------------------------------------------------------------- face frame
# Slot-local: +X right along the dash, +Y up the dash slope, +Z out of it.
# The console face is raked RAKE off that plane and leans away from the pilot
# at the top, so its normal aims at the eye.
RAKE = math.radians(44.0)
FCOS, FSIN = math.cos(RAKE), math.sin(RAKE)
FACE_ROT = (RAKE, 0.0, 0.0)            # lay a +Z-facing thing onto the face
UP_ROT = (RAKE - math.pi / 2, 0.0, 0.0)   # stand a +Z-axis thing UP the face
S = 1.15                               # uniform scale on the plan's §3 table
HY = 0.170                             # plan y == 0  ->  face py = 0.170
FACE_W, FACE_H = 0.820, 0.340          # plan §3 working face
HINGE = Vector((0.0, -0.150 * S, 0.014 * S))   # where the face leaves the deck

# face basis in slot-local space
NRM = Vector((0.0, -FSIN, FCOS))       # face normal, toward the pilot
UPV = Vector((0.0, FCOS, FSIN))        # "up" along the face


def K(*v):
    """Scale plan-space lengths by S."""
    return tuple(x * S for x in v) if len(v) > 1 else v[0] * S


def fp(px, py, h=0.0):
    """A point on (or h out from) the raked console face, face-frame units."""
    return Vector((px,
                   HINGE.y + py * FCOS - h * FSIN,
                   HINGE.z + py * FSIN + h * FCOS))


def F(x, y, h=0.0):
    """A point at the PLAN's local (x, y), h out along the face normal."""
    return fp(x * S, (y + HY) * S, h * S)


# ------------------------------------------------------------ layout table
# Plan §3 coordinates, verbatim except where the deviation list says otherwise.
SCOPE_X, SCOPE_Y, SCOPE_R = -0.310, -0.055, 0.072      # contact scope face
SCOPE_BEZ = 0.082                                      # bearing rose lives here
WHEEL_X, WHEEL_Y, WHEEL_R = -0.318, 0.088, 0.046       # azimuth hand-wheel
WHEEL_PTR = 0.060                                      # index pointer reach
TARGET_RANGE = [-140.0, 140.0]

BORE_X, BORE_Y = -0.090, 0.060                         # emitter trunnion
BORE_R, BORE_LEN = 0.025, 0.320                        # barrel radius / length
BORE_ELEV = math.radians(29.0)                         # above the DASH plane
BORE_STAND = 0.072                                     # trunnion height off face

# the capacitor bank: exposed tubes STANDING UP the face off a chassis rail, so
# they break the panel line and silhouette next to the bore (they read as
# lamp-ends, not tubes, if they point out along the face normal).
TUBE_Y, TUBE_R = 0.112, 0.0105                         # rail height / envelope
TUBE_X = [-0.240, -0.216, -0.192, -0.168]
TUBE_H = 0.062

CHG_X, CHG_Y, CHG_THROW = -0.190, 0.020, 0.100         # capacitor lever
CHARGE_FRAMES = 5

DRUM_X, DRUM_Y, DRUM_R = -0.090, -0.104, 0.046         # munition drum
BREECH_X, BREECH_Y = -0.090, -0.030                    # lit breech window
BREECH_W, BREECH_H = 0.128, 0.024
PAYLOADS = ["INJECTION", "OVERFLOW", "TRAVERSAL", "SSRF",
            "AUTH-BYPASS", "RESOURCE-DoS", "RCE", "SUPPLY-CHAIN"]

ARM_X, ARM_Y = 0.040, 0.100                            # caged master arm
ARM_ORDER = ["safe", "armed", "interlock"]
FIRE_X, FIRE_Y = 0.032, -0.062                         # fire plunger
FIRE_ORDER = ["ready", "fired"]

PRN_X, PRN_Y = 0.249, 0.006                            # catch-printer chassis
PRN_W, PRN_H = 0.298, 0.292
AP_X, AP_Y = 0.2640, -0.030                            # glass aperture
AP_W, AP_H = 0.208, 0.140
HDR_Y, HDR_H = 0.074, 0.020                            # verdict header bar
SPOOL_Y, SPOOL_R = 0.118, 0.026
SPOOL_X = [0.206, 0.336]
TEAR_Y = -0.122
CATCH_FRAMES = 4

VRD_X, VRD_Y = 0.129, -0.030                           # IMPACT lamp column
VRD_DY = 0.040
VERDICT_ORDER = ["idle", "hit", "refused", "deflected"]

# the engraved nameplate lives on the bottom chrome rail, clear of the scope
# and the munition drum -- the only strip that spans the whole console.
NAME_X, NAME_Y = 0.186, -0.159
NAMEPLATE = "SIGNAL HARPOON · DIRECTIONAL TRANSCEIVER"

# contact blips on the scope face: (dx, dy, brightness) in scope-face units
BLIPS = [(-0.030, 0.032, 1.0), (0.041, 0.018, 1.0), (0.014, -0.044, 1.0),
         (-0.048, -0.020, 0.6), (0.055, -0.038, 0.6), (-0.008, 0.058, 0.6)]


# --------------------------------------------------------------- primitives
def _finish(o, name, mat_, rot, bevel=0.0, smooth=False):
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
    o.data.materials.append(mat_)
    return o


def box(name, center, size, mat_, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    o = bpy.context.object
    o.scale = size
    return _finish(o, name, mat_, rot, bevel)


def cyl(name, center, radius, depth, mat_, rot=(0, 0, 0), verts=28,
        smooth=True, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                        vertices=verts, location=center)
    return _finish(bpy.context.object, name, mat_, rot, bevel, smooth)


def cone(name, center, r1, r2, depth, mat_, rot=(0, 0, 0), verts=28):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth,
                                    vertices=verts, location=center)
    return _finish(bpy.context.object, name, mat_, rot, smooth=True)


def ball(name, center, radius, mat_, scale=(1, 1, 1), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=20,
                                         ring_count=12, location=center)
    o = bpy.context.object
    o.scale = scale
    return _finish(o, name, mat_, rot, smooth=True)


def tube(name, center, r_out, r_in, depth, mat_, rot=(0, 0, 0), verts=40,
         smooth=True):
    """A flat annulus (bezel / guard ring), built from pydata."""
    vs, fs = [], []
    for i in range(verts):
        th = 2 * math.pi * i / verts
        c, s = math.cos(th), math.sin(th)
        vs += [(r_in * c, r_in * s, -depth / 2), (r_out * c, r_out * s, -depth / 2),
               (r_out * c, r_out * s, depth / 2), (r_in * c, r_in * s, depth / 2)]
    for i in range(verts):
        a, b = i * 4, ((i + 1) % verts) * 4
        fs += [(a + 0, a + 1, b + 1, b + 0), (a + 1, a + 2, b + 2, b + 1),
               (a + 2, a + 3, b + 3, b + 2), (a + 3, a + 0, b + 0, b + 3)]
    o = shell.mesh_from(name, vs, fs, mat_, smooth)
    o.location = center
    o.rotation_euler = rot
    return o


def sector(name, center, r_out, r_in, depth, a0, a1, mat_, rot=(0, 0, 0),
           seg=5):
    """An annular sector -- one stripe of a hazard ring."""
    vs, fs = [], []
    for i in range(seg + 1):
        th = a0 + (a1 - a0) * i / seg
        c, s = math.cos(th), math.sin(th)
        vs += [(r_in * c, r_in * s, -depth / 2), (r_out * c, r_out * s, -depth / 2),
               (r_out * c, r_out * s, depth / 2), (r_in * c, r_in * s, depth / 2)]
    for i in range(seg):
        a, b = i * 4, (i + 1) * 4
        fs += [(a + 0, a + 1, b + 1, b + 0), (a + 1, a + 2, b + 2, b + 1),
               (a + 2, a + 3, b + 3, b + 2), (a + 3, a + 0, b + 0, b + 3)]
    n = seg * 4
    fs += [(0, 3, 2, 1), (n, n + 1, n + 2, n + 3)]
    o = shell.mesh_from(name, vs, fs, mat_, False)
    o.location = center
    o.rotation_euler = rot
    return o


def hazard_ring(prefix, center, r_out, r_in, depth, mat_a, mat_b, n=12,
                rot=(0, 0, 0), skew=0.0):
    """Alternating yellow/black stripes around a ring -- diegetic 'this
    discharges'.  `skew` shears each stripe for a chevron read."""
    out = []
    for i in range(n):
        a0 = 2 * math.pi * i / n
        a1 = 2 * math.pi * (i + 1) / n
        out.append(sector(f"{prefix}_{i}", center, r_out, r_in, depth,
                          a0 + skew, a1 + skew,
                          mat_a if i % 2 == 0 else mat_b, rot, seg=3))
    return out


def prism(name, section, x0, x1, mat_, smooth=False):
    """Extrude a (y, z) polygon along X -- the console body."""
    n = len(section)
    vs = [(x0, y, z) for (y, z) in section] + [(x1, y, z) for (y, z) in section]
    fs = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    fs.append(tuple(range(n - 1, -1, -1)))
    fs.append(tuple(range(n, 2 * n)))
    return shell.mesh_from(name, vs, fs, mat_, smooth)


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


def text(name, body, size, mat_, loc, rot=(0, 0, 0), align='CENTER'):
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
    o.data.materials.append(mat_)
    return o


def ftext(name, body, size, mat_, x, y, h=0.006, align='CENTER'):
    """Engraved lettering laid on the console face at PLAN coordinates."""
    return text(name, body, K(size), mat_, F(x, y, h), FACE_ROT, align)


def mat(name, base, metallic=0.0, rough=0.5, emission=None, strength=0.0,
        alpha=1.0):
    """Idempotent material factory -- the combiner may import us twice."""
    key = "pkt_" + name
    m = bpy.data.materials.get(key)
    if m is not None:
        return m
    return shell.material(key, base, metallic, rough, emission=emission,
                          emit_strength=strength, alpha=alpha)


# ------------------------------------------------------------- pivot rigging
def pivot(name, loc, base_rot=FACE_ROT):
    bpy.ops.object.empty_add(location=loc)
    e = bpy.context.object
    e.name = name
    e.rotation_euler = base_rot
    e["rest_loc"] = tuple(loc)
    return e


def attach(e, objs):
    """Parent objects authored in ROOT space to a pivot without moving them."""
    M = Matrix.Translation(e.location) @ \
        Euler(tuple(e.rotation_euler), 'XYZ').to_matrix().to_4x4()
    inv = M.inverted()
    for o in objs:
        o.parent = e
        o.matrix_parent_inverse = inv
    return objs


_BASE_ROT = Euler(FACE_ROT, 'XYZ').to_matrix()


def spin(e, axis, deg):
    """Rotate a face-mounted pivot about its own local axis."""
    R = {'x': Matrix.Rotation(math.radians(deg), 3, 'X'),
         'y': Matrix.Rotation(math.radians(deg), 3, 'Y'),
         'z': Matrix.Rotation(math.radians(deg), 3, 'Z')}[axis]
    e.rotation_euler = (_BASE_ROT @ R).to_euler()


def slide(e, along, dist):
    """Translate a face-mounted pivot along the face UP or NORMAL."""
    v = {'up': UPV, 'n': NRM}[along]
    e.location = Vector(e["rest_loc"]) + v * dist


# ----------------------------------------------------------------- the prop
def add_props(P, mats):
    """Add the Signal Harpoon to the CURRENT scene.  Geometry only."""
    brass = mats["brass"]
    hull_d = mats["hull_d"]

    # --- material family: blued gunmetal + chrome, saturated red/amber -----
    gun = mat("gunmetal", (0.042, 0.047, 0.060, 1), 0.62, 0.50)
    gun_d = mat("gunmetal_d", (0.020, 0.023, 0.030, 1), 0.35, 0.66)
    chrome = mat("chrome", (0.520, 0.548, 0.595, 1), 1.00, 0.20)
    chrome_d = mat("chrome_d", (0.215, 0.230, 0.262, 1), 1.00, 0.29)
    ebon = mat("ebon", (0.016, 0.017, 0.021, 1), 0.05, 0.44)
    ink = mat("ink", (0.038, 0.035, 0.033, 1), 0.0, 0.62)
    paper = mat("paper", (0.230, 0.216, 0.182, 1), 0.0, 0.88)
    steel = mat("steel", (0.150, 0.162, 0.185, 1), 0.95, 0.36)
    blued = mat("blued", (0.125, 0.136, 0.162, 1), 0.72, 0.30)
    label = mat("label", (0.860, 0.885, 0.930, 1), 0.0, 0.48,
                emission=(0.86, 0.90, 0.98, 1), strength=0.34)
    label_r = mat("label_r", (0.900, 0.230, 0.170, 1), 0.0, 0.46,
                  emission=(1.00, 0.22, 0.14, 1), strength=0.55)

    red = mat("red", (0.480, 0.030, 0.022, 1), 0.18, 0.34)
    red_dark = mat("red_dark", (0.135, 0.014, 0.012, 1), 0.12, 0.48)
    hazard = mat("hazard", (0.960, 0.720, 0.040, 1), 0.00, 0.44)
    hazard_d = mat("hazard_d", (0.026, 0.024, 0.022, 1), 0.10, 0.46)

    lamp_off_r = mat("lamp_off_r", (0.185, 0.030, 0.028, 1), 0.0, 0.38)
    lamp_on_r = mat("lamp_on_r", (1.000, 0.240, 0.180, 1), 0.0, 0.30,
                    emission=(1.0, 0.13, 0.06, 1), strength=3.2)
    lamp_off_a = mat("lamp_off_a", (0.200, 0.135, 0.035, 1), 0.0, 0.38)
    lamp_on_a = mat("lamp_on_a", (1.000, 0.700, 0.220, 1), 0.0, 0.30,
                    emission=(1.0, 0.52, 0.10, 1), strength=3.0)
    lamp_off_g = mat("lamp_off_g", (0.045, 0.135, 0.075, 1), 0.0, 0.38)
    lamp_on_g = mat("lamp_on_g", (0.360, 1.000, 0.520, 1), 0.0, 0.30,
                    emission=(0.18, 1.0, 0.36, 1), strength=3.0)

    crt = mat("crt", (0.014, 0.038, 0.026, 1), 0.0, 0.18)
    grat = mat("grat", (0.070, 0.230, 0.135, 1), 0.0, 0.55)
    phos = mat("phosphor", (0.180, 0.640, 0.280, 1), 0.0, 0.30,
               emission=(0.16, 1.0, 0.32, 1), strength=2.4)
    phos_dim = mat("phosphor_dim", (0.110, 0.380, 0.180, 1), 0.0, 0.35,
                   emission=(0.18, 0.80, 0.30, 1), strength=1.1)

    # the capacitor bank: five charge levels, dim amber -> white hot.
    # Level 0 is the IDLE glow -- the plan's "only console that looks powered
    # and hot at rest", and it is emissive in the baked far plate.
    tube_lv = [
        mat("tube_0", (0.055, 0.022, 0.008, 1), 0.0, 0.26,
            emission=(1.00, 0.13, 0.00, 1), strength=1.1),
        mat("tube_1", (0.085, 0.035, 0.012, 1), 0.0, 0.26,
            emission=(1.00, 0.17, 0.01, 1), strength=1.9),
        mat("tube_2", (0.140, 0.062, 0.020, 1), 0.0, 0.26,
            emission=(1.00, 0.24, 0.03, 1), strength=3.2),
        mat("tube_3", (0.250, 0.130, 0.050, 1), 0.0, 0.26,
            emission=(1.00, 0.42, 0.12, 1), strength=5.4),
        mat("tube_4", (0.560, 0.470, 0.380, 1), 0.0, 0.26,
            emission=(1.00, 0.80, 0.60, 1), strength=9.0),
    ]
    flash_m = mat("flash", (1.0, 0.86, 0.55, 1), 0.0, 0.30,
                  emission=(1.0, 0.60, 0.18, 1), strength=8.0)

    hdr_idle = mat("hdr_idle", (0.130, 0.140, 0.160, 1), 0.60, 0.35)
    hdr_hit = mat("hdr_hit", (0.120, 0.520, 0.230, 1), 0.10, 0.35,
                  emission=(0.20, 1.0, 0.42, 1), strength=2.4)
    hdr_ref = mat("hdr_refused", (0.560, 0.330, 0.050, 1), 0.10, 0.35,
                  emission=(1.0, 0.60, 0.12, 1), strength=2.2)
    hdr_def = mat("hdr_deflected", (0.520, 0.070, 0.050, 1), 0.10, 0.35,
                  emission=(1.0, 0.16, 0.10, 1), strength=2.2)

    # ------------------------------------------------------------ the root
    loc, eul = slots.dash(P, SLOT_ANGLE, SLOT_T)
    bpy.ops.object.empty_add(location=loc)
    root = bpy.context.object
    root.name = "pkt_root"
    root.rotation_euler = eul

    made, hidden = [], []

    def add(o):
        made.append(o)
        return o

    def addall(seq):
        for o in seq:
            made.append(o)
        return seq

    HX = K(FACE_W / 2)
    face_top = K(FACE_H)

    # ------------------------------------------------------ console body
    # A raked cabinet: front bottom, the raked face, a top deck, a back slope.
    p_hinge = (HINGE.y, HINGE.z)
    p_top = (HINGE.y + face_top * FCOS, HINGE.z + face_top * FSIN)
    section = [
        (K(-0.204), 0.0),
        (K(-0.196), K(0.026)),
        p_hinge,
        p_top,
        (p_top[0] + K(0.062), p_top[1] + K(0.004)),
        (K(0.226), K(0.120)),
        (K(0.226), 0.0),
    ]
    add(prism("pkt_body", section, -HX, HX, gun))
    # chrome skid rails down each side of the body, and a plinth on the dash
    add(box("pkt_plinth", (0, K(0.012), K(0.008)), K(FACE_W + 0.050, 0.440, 0.016),
            gun_d, bevel=K(0.004)))
    for i, sx in enumerate((-1, 1)):
        add(box(f"pkt_skid_{i}", (sx * (HX + K(0.011)), K(0.012), K(0.030)),
                K(0.014, 0.420, 0.052), chrome_d, bevel=K(0.003)))
    # a thin brass accent so the console still belongs to this ship
    add(box("pkt_brass_beam", (0, K(-0.212), K(0.013)),
            K(FACE_W + 0.040, 0.012, 0.022), brass, bevel=K(0.003)))

    # ------------------------------------------------------- the face plate
    add(box("pkt_face", fp(0, face_top / 2, K(-0.008)),
            (K(FACE_W), face_top, K(0.016)), gun, rot=FACE_ROT, bevel=K(0.002)))
    # bezel: dark gunmetal rails with a thin chrome inlay, so the console reads
    # blued rather than as a chrome tray.  The bottom rail is deep enough to
    # carry the engraved nameplate.
    for i, (cx, cy, w, h) in enumerate((
            (0.0, FACE_H / 2 + 0.008, FACE_W + 0.030, 0.016),
            (0.0, -FACE_H / 2 - 0.012, FACE_W + 0.030, 0.024),
            (-FACE_W / 2 - 0.008, 0.0, 0.016, FACE_H + 0.030),
            (FACE_W / 2 + 0.008, 0.0, 0.016, FACE_H + 0.030))):
        add(box(f"pkt_bezel_{i}", fp(K(cx), K(cy + HY), K(0.005)),
                K(w, h, 0.018), gun_d, rot=FACE_ROT, bevel=K(0.003)))
    for i, (cx, cy, w, h) in enumerate((
            (0.0, FACE_H / 2 + 0.001, FACE_W + 0.016, 0.004),
            (0.0, -FACE_H / 2 - 0.001, FACE_W + 0.016, 0.004),
            (-FACE_W / 2 - 0.001, 0.0, 0.004, FACE_H + 0.008),
            (FACE_W / 2 + 0.001, 0.0, 0.004, FACE_H + 0.008))):
        add(box(f"pkt_inlay_{i}", fp(K(cx), K(cy + HY), K(0.013)),
                K(w, h, 0.006), chrome, rot=FACE_ROT))
    # corner bolts
    for i, (cx, cy) in enumerate(((-0.398, 0.158), (0.398, 0.158),
                                  (-0.398, -0.158), (0.398, -0.158))):
        add(cyl(f"pkt_bolt_{i}", F(cx, cy, 0.009), K(0.007), K(0.006),
                chrome_d, rot=FACE_ROT, verts=8))

    # engraved nameplate, in the clear band right of the munition drum
    add(box("pkt_nameplate", F(NAME_X, NAME_Y, 0.004), K(0.436, 0.023, 0.005),
            chrome_d, rot=FACE_ROT, bevel=K(0.001)))
    add(box("pkt_nameplate_lip", F(NAME_X, NAME_Y, 0.0072),
            K(0.424, 0.017, 0.002), ebon, rot=FACE_ROT))
    add(ftext("pkt_nameplate_txt", NAMEPLATE, 0.0180, label,
              NAME_X, NAME_Y, 0.010))
    add(box("pkt_codeplate", F(-0.372, NAME_Y - 0.004, 0.005),
            K(0.062, 0.024, 0.005), brass, rot=FACE_ROT, bevel=K(0.001)))
    add(ftext("pkt_codeplate_txt", "PKT", 0.0150, ink, -0.372, NAME_Y - 0.004,
              0.009))

    # --- lobe fields: three distinct tonal zones so the transceiver reads as
    #     SEND (recessed dark) | COMMIT (red-edged) | CATCH (raised chassis).
    add(box("pkt_send_field", F(-0.208, 0.000, 0.001), K(0.392, 0.330, 0.006),
            gun_d, rot=FACE_ROT, bevel=K(0.002)))
    add(box("pkt_commit_field", F(0.036, 0.014, 0.001), K(0.106, 0.302, 0.007),
            red_dark, rot=FACE_ROT, bevel=K(0.002)))
    add(box("pkt_commit_inner", F(0.036, 0.014, 0.004), K(0.094, 0.290, 0.004),
            gun_d, rot=FACE_ROT))
    for i, yy in enumerate((0.152, -0.124)):
        for k in range(8):
            xx = -0.010 + k * 0.0116
            add(box(f"pkt_commit_hz_{i}_{k}", F(xx, yy, 0.006),
                    K(0.0090, 0.0110, 0.0020),
                    hazard if k % 2 == 0 else hazard_d,
                    rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                         @ Matrix.Rotation(math.radians(30), 3, 'Z')
                         ).to_euler()))

    # ============================================================ SEND lobe
    # ------------------------------------------------ target: contact scope
    add(tube("pkt_scope_bezel", F(SCOPE_X, SCOPE_Y, 0.008),
             K(SCOPE_BEZ + 0.012), K(SCOPE_BEZ - 0.004), K(0.020), gun_d,
             rot=FACE_ROT, verts=48))
    add(tube("pkt_scope_inlay", F(SCOPE_X, SCOPE_Y, 0.017),
             K(SCOPE_BEZ + 0.007), K(SCOPE_BEZ + 0.001), K(0.006), chrome,
             rot=FACE_ROT, verts=48))
    add(cyl("pkt_scope_hood", F(SCOPE_X, SCOPE_Y, 0.002), K(SCOPE_BEZ),
            K(0.014), gun_d, rot=FACE_ROT, verts=48))
    add(cyl("pkt_scope_face", F(SCOPE_X, SCOPE_Y, 0.006), K(SCOPE_R),
            K(0.003), crt, rot=FACE_ROT, verts=48))
    for i, rr in enumerate((0.026, 0.050, 0.072)):
        add(tube(f"pkt_scope_ring_{i}", F(SCOPE_X, SCOPE_Y, 0.0075),
                 K(rr), K(rr - 0.0018), K(0.0016), grat, rot=FACE_ROT,
                 verts=48))
    for i in range(8):
        th = math.pi * i / 8
        add(box(f"pkt_scope_cross_{i}",
                F(SCOPE_X, SCOPE_Y, 0.0075), K(0.0016, 2 * SCOPE_R, 0.0014),
                grat, rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                           @ Matrix.Rotation(th, 3, 'Z')).to_euler()))
    for i, (dx, dy, br) in enumerate(BLIPS):
        add(ball(f"pkt_blip_{i}", F(SCOPE_X + dx, SCOPE_Y + dy, 0.0085),
                 K(0.0060 if br > 0.8 else 0.0044),
                 phos if br > 0.8 else phos_dim, scale=(1, 1, 0.5),
                 rot=FACE_ROT))
    # the designation readout band -- LOCK / target id is painted live here
    add(box("pkt_scope_readout", F(SCOPE_X, SCOPE_Y - 0.057, 0.0080),
            K(0.118, 0.020, 0.002), ebon, rot=FACE_ROT))
    add(box("pkt_scope_readout_lip", F(SCOPE_X, SCOPE_Y - 0.057, 0.0072),
            K(0.126, 0.026, 0.002), chrome_d, rot=FACE_ROT))
    add(ftext("pkt_scope_label", "CONTACTS", 0.0110, label,
              SCOPE_X, -0.161, 0.007))

    # engraved bearing rose around the scope -- what the wheel's pointer reads
    for i in range(36):
        th = math.radians(i * 10.0)
        long_tick = (i % 3 == 0)
        rr = 0.086 if long_tick else 0.089
        px = SCOPE_X + math.sin(th) * rr
        py = SCOPE_Y + math.cos(th) * rr
        add(box(f"pkt_bearing_tick_{i}", F(px, py, 0.019),
                K(0.0020, 0.012 if long_tick else 0.006, 0.0016), chrome,
                rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                     @ Matrix.Rotation(-th, 3, 'Z')).to_euler()))
    # index mark the hand-wheel pointer parks against
    add(cone("pkt_wheel_index", F(WHEEL_X, WHEEL_Y + 0.072, 0.010), K(0.0075),
             K(0.0), K(0.016), label,
             rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                  @ Matrix.Rotation(math.radians(90), 3, 'X')).to_euler(),
             verts=12))
    add(ftext("pkt_wheel_label", "AZIMUTH", 0.0104, label,
              WHEEL_X - 0.010, WHEEL_Y + 0.070, 0.007))

    # ------------------------------------------- target: the azimuth wheel
    wheel_c = F(WHEEL_X, WHEEL_Y, 0.020)
    w_piv = pivot("pkt_wheel_pivot", wheel_c)
    wheel = []
    wheel.append(tube("pkt_wheel_rim", wheel_c, K(WHEEL_R), K(WHEEL_R - 0.011),
                      K(0.020), chrome, rot=FACE_ROT, verts=36))
    wheel.append(cyl("pkt_wheel_web", wheel_c, K(WHEEL_R - 0.009), K(0.008),
                     gun, rot=FACE_ROT, verts=36))
    wheel.append(cyl("pkt_wheel_hub", wheel_c, K(0.013), K(0.026), chrome,
                     rot=FACE_ROT, verts=20))
    for i in range(24):                              # knurling
        th = 2 * math.pi * i / 24
        off = Vector((math.cos(th) * K(WHEEL_R - 0.005),
                      math.sin(th) * K(WHEEL_R - 0.005), 0.0))
        off.rotate(Euler(FACE_ROT, 'XYZ'))
        wheel.append(box(f"pkt_wheel_knurl_{i}", wheel_c + off,
                         K(0.0055, 0.0055, 0.022), chrome_d,
                         rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                              @ Matrix.Rotation(th, 3, 'Z')).to_euler()))
    for i in range(3):                               # spokes
        th = 2 * math.pi * i / 3
        off = Vector((-math.sin(th) * K(WHEEL_R * 0.5),
                      math.cos(th) * K(WHEEL_R * 0.5), 0.0))
        off.rotate(Euler(FACE_ROT, 'XYZ'))
        wheel.append(box(f"pkt_wheel_spoke_{i}", wheel_c + off,
                         K(0.008, WHEEL_R, 0.016), chrome_d,
                         rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                              @ Matrix.Rotation(th, 3, 'Z')).to_euler()))
    # the index pointer -- reads the bearing arc, and makes the spin obvious
    ptr_off = Vector((0.0, K(WHEEL_PTR * 0.55), 0.0))
    ptr_off.rotate(Euler(FACE_ROT, 'XYZ'))
    wheel.append(box("pkt_wheel_pointer", wheel_c + ptr_off,
                     K(0.010, WHEEL_PTR * 1.10, 0.014), chrome,
                     rot=FACE_ROT, bevel=K(0.002)))
    tip_off = Vector((0.0, K(WHEEL_PTR * 0.96), 0.0))
    tip_off.rotate(Euler(FACE_ROT, 'XYZ'))
    wheel.append(cone("pkt_wheel_tip", wheel_c + tip_off, K(0.0090), K(0.0),
                      K(0.024), red,
                      rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                           @ Matrix.Rotation(math.radians(-90), 3, 'X')
                           ).to_euler(), verts=14))
    addall(wheel)
    attach(w_piv, wheel)

    # ------------------------------------------------ charge: lever + tubes
    add(box("pkt_chg_slot", F(CHG_X, CHG_Y, 0.004),
            K(0.020, CHG_THROW + 0.036, 0.008), ebon, rot=FACE_ROT))
    add(box("pkt_chg_slot_rim", F(CHG_X, CHG_Y, 0.002),
            K(0.032, CHG_THROW + 0.048, 0.006), chrome_d, rot=FACE_ROT,
            bevel=K(0.002)))
    for i in range(CHARGE_FRAMES):
        yy = CHG_Y - CHG_THROW / 2 + CHG_THROW * i / (CHARGE_FRAMES - 1)
        add(box(f"pkt_chg_tick_{i}", F(CHG_X - 0.024, yy, 0.006),
                K(0.012, 0.0026, 0.0016), red if i >= 3 else chrome,
                rot=FACE_ROT))
    add(ftext("pkt_chg_label", "CHARGE", 0.0104, label,
              CHG_X, CHG_Y - 0.052, 0.007))

    # the 5-pip redline ladder
    chg_pips, chg_pip_off, chg_pip_on = [], [], []
    for i in range(CHARGE_FRAMES):
        yy = CHG_Y - CHG_THROW / 2 + CHG_THROW * i / (CHARGE_FRAMES - 1)
        add(tube(f"pkt_chg_pipring_{i}", F(CHG_X + 0.022, yy, 0.006),
                 K(0.0086), K(0.0058), K(0.008), chrome_d, rot=FACE_ROT,
                 verts=14))
        p = ball(f"pkt_chg_pip_{i}", F(CHG_X + 0.022, yy, 0.0075), K(0.0056),
                 lamp_off_r if i >= 3 else lamp_off_a, scale=(1, 1, 0.6),
                 rot=FACE_ROT)
        chg_pips.append(add(p))
        chg_pip_off.append(lamp_off_r if i >= 3 else lamp_off_a)
        chg_pip_on.append(lamp_on_r if i >= 3 else lamp_on_a)

    # the sliding capacitor lever
    lev_c = F(CHG_X, CHG_Y - CHG_THROW / 2, 0.020)
    l_piv = pivot("pkt_chg_pivot", lev_c)
    lever = [box("pkt_chg_shoe", lev_c, K(0.030, 0.024, 0.026), chrome,
                 rot=FACE_ROT, bevel=K(0.003)),
             cyl("pkt_chg_stem", F(CHG_X, CHG_Y - CHG_THROW / 2, 0.036),
                 K(0.0062), K(0.030), chrome_d, rot=FACE_ROT, verts=14),
             ball("pkt_chg_knob", F(CHG_X, CHG_Y - CHG_THROW / 2, 0.054),
                  K(0.0155), red, rot=FACE_ROT)]
    addall(lever)
    attach(l_piv, lever)

    # the vacuum-tube capacitor bank -- exposed, standing up off a chassis
    # rail, and emitting even in the baked far plate
    tcx = (TUBE_X[0] + TUBE_X[-1]) / 2
    add(box("pkt_tube_rail", F(tcx, TUBE_Y - 0.012, 0.026),
            K(abs(TUBE_X[-1] - TUBE_X[0]) + 0.034, 0.024, 0.052), gun,
            rot=FACE_ROT, bevel=K(0.003)))
    add(box("pkt_tube_rail_face", F(tcx, TUBE_Y - 0.012, 0.053),
            K(abs(TUBE_X[-1] - TUBE_X[0]) + 0.026, 0.018, 0.006), chrome_d,
            rot=FACE_ROT))
    for i, sx in enumerate((-1, 1)):
        add(box(f"pkt_tube_strut_{i}",
                F(tcx + sx * (abs(TUBE_X[-1] - TUBE_X[0]) / 2 - 0.009),
                  TUBE_Y - 0.048, 0.013), K(0.014, 0.056, 0.026), gun_d,
                rot=FACE_ROT, bevel=K(0.002)))
    tubes = []
    for i, tx in enumerate(TUBE_X):
        add(cyl(f"pkt_tube_socket_{i}", F(tx, TUBE_Y + 0.005, 0.030),
                K(TUBE_R + 0.004), K(0.016), chrome, rot=UP_ROT, verts=18))
        add(cyl(f"pkt_tube_pin_{i}", F(tx, TUBE_Y + 0.017, 0.030),
                K(TUBE_R + 0.001), K(0.010), ebon, rot=UP_ROT, verts=18))
        env = cyl(f"pkt_tube_env_{i}", F(tx, TUBE_Y + 0.022 + TUBE_H / 2, 0.030),
                  K(TUBE_R), K(TUBE_H), tube_lv[0], rot=UP_ROT, verts=20)
        tubes.append(add(env))
        add(ball(f"pkt_tube_dome_{i}",
                 F(tx, TUBE_Y + 0.022 + TUBE_H, 0.030), K(TUBE_R),
                 tube_lv[0], scale=(1, 0.62, 1), rot=UP_ROT))
    add(ftext("pkt_tube_label", "CAPACITOR BANK", 0.0082, label,
              tcx, TUBE_Y - 0.030, 0.007))
    # dome objects follow the envelopes' material, so collect them too
    tube_domes = [o for o in made if o.name.startswith("pkt_tube_dome_")]

    # ------------------------------------------------------- emitter / bore
    bd = Vector((0.0, math.cos(BORE_ELEV), math.sin(BORE_ELEV)))
    bore_rot = (BORE_ELEV - math.pi / 2, 0.0, 0.0)
    trn = F(BORE_X, BORE_Y, BORE_STAND)
    blen = K(BORE_LEN)
    # yoke: two cheek plates gripping a trunnion pin, on a low pedestal
    for i, sx in enumerate((-0.052, 0.052)):
        add(box(f"pkt_yoke_{i}", F(BORE_X + sx, BORE_Y - 0.024, 0.038),
                K(0.013, 0.080, 0.084), chrome_d, rot=FACE_ROT,
                bevel=K(0.003)))
        add(cyl(f"pkt_yoke_cap_{i}", F(BORE_X + sx, BORE_Y, BORE_STAND),
                K(0.019), K(0.014), chrome, rot=(0, math.pi / 2, 0), verts=18))
    add(cyl("pkt_yoke_pin", trn, K(0.011), K(0.132), chrome_d,
            rot=(0, math.pi / 2, 0), verts=16))
    add(box("pkt_yoke_base", F(BORE_X, BORE_Y - 0.034, 0.012),
            K(0.140, 0.028, 0.026), gun, rot=FACE_ROT, bevel=K(0.003)))
    add(ftext("pkt_bore_label", "EMITTER", 0.0092, label,
              BORE_X, BORE_Y - 0.052, 0.007))
    # breech block + barrel
    add(cyl("pkt_bore_breech", trn - bd * K(0.020), K(BORE_R + 0.011),
            K(0.070), gun, rot=bore_rot, verts=28, bevel=K(0.003)))
    add(tube("pkt_bore_breech_ring", trn - bd * K(0.050), K(BORE_R + 0.015),
             K(BORE_R + 0.003), K(0.010), chrome, rot=bore_rot, verts=28))
    add(cyl("pkt_bore_barrel", trn + bd * (blen * 0.5 - K(0.008)), K(BORE_R),
            blen + K(0.016), blued, rot=bore_rot, verts=32))
    for i, fr in enumerate((0.14, 0.28, 0.88)):
        add(tube(f"pkt_bore_band_{i}", trn + bd * (blen * fr),
                 K(BORE_R + 0.006), K(BORE_R - 0.002), K(0.010), chrome,
                 rot=bore_rot, verts=32))
    # hazard chevron collar -- the diegetic "this discharges"
    addall(hazard_ring("pkt_bore_hazard", trn + bd * (blen * 0.50),
                       K(BORE_R + 0.005), K(BORE_R - 0.002), K(0.062),
                       hazard, hazard_d, n=14, rot=bore_rot,
                       skew=math.radians(7)))
    # muzzle: a plain crowned bore, not a bell -- it must stay a harpoon
    add(tube("pkt_bore_lip", trn + bd * (blen - K(0.004)), K(BORE_R + 0.004),
             K(BORE_R - 0.010), K(0.009), chrome, rot=bore_rot, verts=32))
    add(cyl("pkt_bore_mouth", trn + bd * (blen - K(0.020)), K(BORE_R - 0.011),
            K(0.040), ebon, rot=bore_rot, verts=24))
    # feed conduits from the tube bank into the breech
    for i, sx in enumerate((-0.032, 0.032)):
        add(cyl(f"pkt_bore_conduit_{i}",
                F(BORE_X + sx, BORE_Y + 0.042, 0.026), K(0.0058), K(0.076),
                chrome_d, rot=FACE_ROT, verts=12))

    # muzzle flash -- only in fire=fired
    flash = [ball("pkt_flash_core", trn + bd * (blen + K(0.004)), K(0.026),
                  flash_m, scale=(1.0, 1.0, 1.0), rot=bore_rot),
             cone("pkt_flash_cone", trn + bd * (blen + K(0.030)), K(0.012),
                  K(0.044), K(0.056), flash_m, rot=bore_rot, verts=18),
             cone("pkt_flash_tip", trn + bd * (blen + K(0.070)), K(0.044),
                  K(0.006), K(0.026), flash_m, rot=bore_rot, verts=18)]
    for o in flash:
        add(o)
        o.hide_render = True
        hidden.append(o)

    # ----------------------------------------------- payload: munition drum
    add(cyl("pkt_drum_well", F(DRUM_X, DRUM_Y, 0.004), K(DRUM_R + 0.010),
            K(0.010), ebon, rot=FACE_ROT, verts=40))
    add(tube("pkt_drum_ring", F(DRUM_X, DRUM_Y, 0.010), K(DRUM_R + 0.014),
             K(DRUM_R + 0.004), K(0.024), chrome, rot=FACE_ROT, verts=40))
    # lit breech window above the drum
    add(box("pkt_breech_frame", F(BREECH_X, BREECH_Y, 0.008),
            K(BREECH_W + 0.016, BREECH_H + 0.014, 0.014), gun_d,
            rot=FACE_ROT, bevel=K(0.002)))
    add(box("pkt_breech_well", F(BREECH_X, BREECH_Y, 0.011),
            K(BREECH_W, BREECH_H, 0.006), ebon, rot=FACE_ROT))
    add(box("pkt_breech_glow", F(BREECH_X, BREECH_Y, 0.0125),
            K(BREECH_W - 0.004, BREECH_H - 0.006, 0.002),
            mat("breech_glow", (0.35, 0.20, 0.05, 1), 0.0, 0.4,
                emission=(1.0, 0.56, 0.12, 1), strength=1.5), rot=FACE_ROT))

    drum_c = F(DRUM_X, DRUM_Y, 0.020)
    d_piv = pivot("pkt_drum_pivot", drum_c)
    drum = [cyl("pkt_drum_body", drum_c, K(DRUM_R), K(0.030), gun,
                rot=FACE_ROT, verts=40),
            cyl("pkt_drum_hub", F(DRUM_X, DRUM_Y, 0.030), K(0.011),
                K(0.014), chrome, rot=FACE_ROT, verts=16)]
    for i in range(8):
        th = 2 * math.pi * i / 8
        off = Vector((math.sin(th) * K(0.032), math.cos(th) * K(0.032), 0.0))
        off.rotate(Euler(FACE_ROT, 'XYZ'))
        drum.append(cyl(f"pkt_drum_chamber_{i}", drum_c + off, K(0.0125),
                        K(0.034), ebon, rot=FACE_ROT, verts=14))
        drum.append(cone(f"pkt_drum_shell_{i}",
                         drum_c + off + NRM * K(0.014), K(0.0105), K(0.0035),
                         K(0.016), brass, rot=FACE_ROT, verts=14))
        rib = Vector((math.sin(th + math.pi / 8) * K(DRUM_R * 0.62),
                      math.cos(th + math.pi / 8) * K(DRUM_R * 0.62), 0.0))
        rib.rotate(Euler(FACE_ROT, 'XYZ'))
        drum.append(box(f"pkt_drum_rib_{i}", drum_c + rib,
                        K(0.005, DRUM_R * 0.80, 0.032), chrome_d,
                        rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                             @ Matrix.Rotation(-(th + math.pi / 8), 3, 'Z')
                             ).to_euler()))
    idx = Vector((0.0, K(DRUM_R - 0.006), 0.0))
    idx.rotate(Euler(FACE_ROT, 'XYZ'))
    drum.append(cyl("pkt_drum_index", drum_c + idx + NRM * K(0.016), K(0.0062),
                    K(0.008), red, rot=FACE_ROT, verts=12))
    addall(drum)
    attach(d_piv, drum)

    payload_txt = []
    for i, nm in enumerate(PAYLOADS):
        t = ftext(f"pkt_payload_txt_{i}", nm, 0.0140, hazard,
                  BREECH_X, BREECH_Y, 0.0135)
        add(t)
        payload_txt.append(t)
        if i:
            t.hide_render = True
            hidden.append(t)

    # ------------------------------------------------- arm: caged master arm
    add(box("pkt_arm_plate", F(ARM_X, ARM_Y, 0.006), K(0.082, 0.086, 0.010),
            gun_d, rot=FACE_ROT, bevel=K(0.003)))
    add(box("pkt_arm_plate_lip", F(ARM_X, ARM_Y, 0.003),
            K(0.094, 0.098, 0.008), chrome_d, rot=FACE_ROT, bevel=K(0.002)))
    add(ftext("pkt_arm_label", "ARM", 0.0122, label, ARM_X, ARM_Y + 0.058,
              0.008))
    add(cyl("pkt_arm_boss", F(ARM_X, ARM_Y - 0.006, 0.012), K(0.016),
            K(0.014), chrome_d, rot=FACE_ROT, verts=20))

    arm_lamps, arm_lamp_off, arm_lamp_on = [], [], []
    for i, (lx, lab, off_m, on_m) in enumerate((
            (ARM_X - 0.024, "ARMED", lamp_off_r, lamp_on_r),
            (ARM_X + 0.024, "INTLK", lamp_off_a, lamp_on_a))):
        add(tube(f"pkt_arm_lampring_{i}", F(lx, ARM_Y - 0.056, 0.007),
                 K(0.0125), K(0.0088), K(0.010), chrome, rot=FACE_ROT,
                 verts=18))
        d = ball(f"pkt_arm_lamp_{i}", F(lx, ARM_Y - 0.056, 0.0095), K(0.0086),
                 off_m, scale=(1, 1, 0.62), rot=FACE_ROT)
        arm_lamps.append(add(d))
        arm_lamp_off.append(off_m)
        arm_lamp_on.append(on_m)
        add(ftext(f"pkt_arm_lamplab_{i}", lab, 0.0082, label, lx,
                  ARM_Y - 0.076, 0.007))

    # the master-arm toggle, on its own hinge
    tog_c = F(ARM_X, ARM_Y - 0.006, 0.016)
    t_piv = pivot("pkt_arm_toggle_pivot", tog_c)
    toggle = [cyl("pkt_arm_toggle_stem", tog_c + NRM * K(0.014), K(0.0055),
                  K(0.032), chrome, rot=FACE_ROT, verts=12),
              ball("pkt_arm_toggle_tip", tog_c + NRM * K(0.031), K(0.0092),
                   red, rot=FACE_ROT)]
    addall(toggle)
    attach(t_piv, toggle)

    # the red break-glass cage, hinged along its top edge
    cage_hinge = F(ARM_X, ARM_Y + 0.040, 0.012)
    c_piv = pivot("pkt_arm_cage_pivot", cage_hinge)
    cage = []
    for i, sx in enumerate((-0.030, 0.030)):
        cage.append(box(f"pkt_cage_side_{i}", F(ARM_X + sx, ARM_Y + 0.006, 0.030),
                        K(0.006, 0.078, 0.044), red, rot=FACE_ROT))
    for i, yy in enumerate((-0.030, 0.004, 0.032)):
        cage.append(box(f"pkt_cage_bar_{i}", F(ARM_X, ARM_Y + yy, 0.049),
                        K(0.068, 0.006, 0.006), red, rot=FACE_ROT))
    cage.append(box("pkt_cage_glass", F(ARM_X, ARM_Y + 0.004, 0.046),
                    K(0.058, 0.070, 0.003), red_dark, rot=FACE_ROT))
    cage.append(box("pkt_cage_lip", F(ARM_X, ARM_Y - 0.034, 0.040),
                    K(0.070, 0.008, 0.024), red, rot=FACE_ROT))
    addall(cage)
    attach(c_piv, cage)

    # ------------------------------------------------------- fire: plunger
    addall(hazard_ring("pkt_fire_hazard", F(FIRE_X, FIRE_Y, 0.008),
                       K(0.042), K(0.031), K(0.014), hazard, hazard_d, n=12,
                       rot=FACE_ROT))
    add(tube("pkt_fire_guard", F(FIRE_X, FIRE_Y, 0.020), K(0.033), K(0.028),
             K(0.038), chrome_d, rot=FACE_ROT, verts=28))
    add(cyl("pkt_fire_well", F(FIRE_X, FIRE_Y, 0.006), K(0.030), K(0.008),
            ebon, rot=FACE_ROT, verts=28))
    add(ftext("pkt_fire_label", "FIRE", 0.0130, label_r, FIRE_X, FIRE_Y + 0.054,
              0.008))

    fire_c = F(FIRE_X, FIRE_Y, 0.030)
    f_piv = pivot("pkt_fire_pivot", fire_c)
    plunger = [cyl("pkt_fire_stem", fire_c, K(0.025), K(0.044), red,
                   rot=FACE_ROT, verts=28),
               ball("pkt_fire_cap", F(FIRE_X, FIRE_Y, 0.052), K(0.026), red,
                    scale=(1, 1, 0.55), rot=FACE_ROT)]
    for i, hh in enumerate((0.020, 0.030, 0.040)):
        plunger.append(tube(f"pkt_fire_ridge_{i}", F(FIRE_X, FIRE_Y, hh),
                            K(0.0272), K(0.0240), K(0.006), red_dark,
                            rot=FACE_ROT, verts=24))
    addall(plunger)
    attach(f_piv, plunger)

    # ========================================================== CATCH lobe
    # A first-class second mass: chassis, twin return spools, glass aperture,
    # sprocket rails, tear-off lip.  Authored deliberately EMPTY.
    # The chassis is a FRAME, not a slab: the aperture is a genuine rectangular
    # hole, so the advancing platen behind it is clipped by the machine (LOG's
    # holdout trick) and the live text overlay has real depth behind it.
    _apl, _apr = AP_X - AP_W / 2, AP_X + AP_W / 2
    _apb, _apt = AP_Y - AP_H / 2, AP_Y + AP_H / 2
    _pl, _pr = PRN_X - PRN_W / 2, PRN_X + PRN_W / 2
    _pb, _pt = PRN_Y - PRN_H / 2, PRN_Y + PRN_H / 2
    for i, (x0, x1, y0, y1) in enumerate((
            (_pl, _pr, _apt, _pt), (_pl, _pr, _pb, _apb),
            (_pl, _apl, _apb, _apt), (_apr, _pr, _apb, _apt))):
        add(box(f"pkt_prn_chassis_{i}",
                F((x0 + x1) / 2, (y0 + y1) / 2, 0.014),
                K(x1 - x0, y1 - y0, 0.028), gun, rot=FACE_ROT, bevel=K(0.003)))
    add(box("pkt_prn_bezel", F(PRN_X, PRN_Y, 0.004), K(PRN_W + 0.014,
            PRN_H + 0.014, 0.012), chrome_d, rot=FACE_ROT, bevel=K(0.003)))
    for i, (cx, cy, w, h) in enumerate((
            (PRN_X, _pt + 0.004, PRN_W + 0.010, 0.005),
            (PRN_X, _pb - 0.004, PRN_W + 0.010, 0.005),
            (_pl - 0.004, PRN_Y, 0.005, PRN_H + 0.010),
            (_pr + 0.004, PRN_Y, 0.005, PRN_H + 0.010))):
        add(box(f"pkt_prn_inlay_{i}", F(cx, cy, 0.011), K(w, h, 0.006),
                chrome, rot=FACE_ROT))
    for i, (cx, cy) in enumerate(((PRN_X - PRN_W / 2 + 0.012, PRN_Y - PRN_H / 2 + 0.012),
                                  (PRN_X + PRN_W / 2 - 0.012, PRN_Y - PRN_H / 2 + 0.012),
                                  (PRN_X - PRN_W / 2 + 0.012, PRN_Y + PRN_H / 2 - 0.012),
                                  (PRN_X + PRN_W / 2 - 0.012, PRN_Y + PRN_H / 2 - 0.012))):
        add(cyl(f"pkt_prn_bolt_{i}", F(cx, cy, 0.030), K(0.0068), K(0.006),
                chrome, rot=FACE_ROT, verts=8))

    # aperture surround: four rails leaving a genuine rectangular hole, so the
    # advancing platen is clipped by the machine (LOG's holdout trick).
    ap_l, ap_r = AP_X - AP_W / 2, AP_X + AP_W / 2
    ap_b, ap_t = AP_Y - AP_H / 2, AP_Y + AP_H / 2
    ap_pts = [F(ap_l, ap_b, 0.021), F(ap_r, ap_b, 0.021),
              F(ap_r, ap_t, 0.021), F(ap_l, ap_t, 0.021)]
    aperture_frame = []
    for i, (cx, cy, w, h) in enumerate((
            (AP_X, ap_t + 0.009, AP_W + 0.036, 0.018),
            (AP_X, ap_b - 0.009, AP_W + 0.036, 0.018),
            (ap_l - 0.011, AP_Y, 0.022, AP_H + 0.036),
            (ap_r + 0.011, AP_Y, 0.022, AP_H + 0.036))):
        aperture_frame.append(add(box(f"pkt_ap_rail_{i}", F(cx, cy, 0.030),
                                      K(w, h, 0.014), gun_d, rot=FACE_ROT,
                                      bevel=K(0.002))))
        aperture_frame.append(add(box(f"pkt_ap_inlay_{i}", F(cx, cy, 0.038),
                                      K(w - 0.010, h - 0.010, 0.004), chrome,
                                      rot=FACE_ROT)))
    # sprocket rails down both margins, inside the aperture
    for i in range(11):
        yy = ap_b + 0.010 + i * (AP_H - 0.020) / 10.0
        for j, xx in enumerate((ap_l + 0.008, ap_r - 0.008)):
            add(cyl(f"pkt_sprocket_{i}_{j}", F(xx, yy, 0.0245), K(0.0022),
                    K(0.004), chrome_d, rot=FACE_ROT, verts=6, smooth=False))
    # the dark machine interior behind the platen
    add(box("pkt_ap_back", F(AP_X, AP_Y, 0.004), K(AP_W + 0.014,
            AP_H + 0.014, 0.006), ebon, rot=FACE_ROT))

    # the paper receding into the machine under the top rail
    add(box("pkt_ap_shade", F(AP_X, AP_Y + AP_H / 2 - 0.009, 0.0184),
            K(AP_W - 0.004, 0.018, 0.0012), gun_d, rot=FACE_ROT))
    # tear-off lip + a short scrap of tape hanging out of it
    add(box("pkt_tear_lip", F(AP_X, TEAR_Y, 0.030), K(AP_W + 0.030, 0.016,
            0.016), chrome, rot=FACE_ROT, bevel=K(0.003)))
    for i in range(14):
        add(cone(f"pkt_tear_tooth_{i}", F(ap_l + 0.008 + i * (AP_W - 0.016) / 13.0,
                                          TEAR_Y + 0.010, 0.032), K(0.0042),
                 K(0.0), K(0.010), chrome_d,
                 rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                      @ Matrix.Rotation(math.radians(90), 3, 'X')).to_euler(),
                 verts=6))
    add(box("pkt_tear_tape", F(AP_X, TEAR_Y - 0.012, 0.026),
            K(AP_W - 0.020, 0.022, 0.0016), paper, rot=FACE_ROT))
    add(ftext("pkt_tear_label", "TEAR OFF", 0.0080, label,
              AP_X, TEAR_Y + 0.021, 0.039))
    # spool hood + knurled hand-advance knob: the printer earns its parity
    add(box("pkt_prn_hood", F(PRN_X + 0.020, SPOOL_Y + 0.028, 0.040),
            K(0.206, 0.016, 0.040), gun, rot=FACE_ROT, bevel=K(0.003)))
    add(box("pkt_prn_hood_lip", F(PRN_X + 0.020, SPOOL_Y + 0.034, 0.060),
            K(0.214, 0.010, 0.006), chrome, rot=FACE_ROT))
    add(ftext("pkt_prn_hood_txt", "RETURN LINE", 0.0112, label,
              PRN_X + 0.020, SPOOL_Y + 0.028, 0.062))
    add(cyl("pkt_prn_knob", F(PRN_X + PRN_W / 2 - 0.015, -0.055, 0.032),
            K(0.014), K(0.016), chrome_d, rot=FACE_ROT, verts=24))
    for i in range(14):
        th = 2 * math.pi * i / 14
        off = Vector((math.cos(th) * K(0.0122), math.sin(th) * K(0.0122), 0.0))
        off.rotate(Euler(FACE_ROT, 'XYZ'))
        add(box(f"pkt_prn_knurl_{i}",
                F(PRN_X + PRN_W / 2 - 0.015, -0.055, 0.032) + off,
                K(0.0034, 0.0034, 0.018), chrome,
                rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                     @ Matrix.Rotation(th, 3, 'Z')).to_euler()))
    # the harpoon line coming home: a fairlead on the printer's shoulder with a
    # short length of chrome return line aimed back at the emitter.
    add(cyl("pkt_fairlead", F(PRN_X - PRN_W / 2 + 0.014, SPOOL_Y + 0.006, 0.046),
            K(0.011), K(0.024), chrome, rot=FACE_ROT, verts=18))
    add(cyl("pkt_return_lead", F(PRN_X - PRN_W / 2 - 0.008, SPOOL_Y + 0.030,
                                 0.052), K(0.0030), K(0.052), chrome,
            rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                 @ Matrix.Rotation(math.radians(58), 3, 'Y')).to_euler(),
            verts=10))

    # the verdict header bar chrome surround (the tint plate itself is a
    # `verdict` state sprite, so it is NOT in the static plate)
    add(box("pkt_hdr_frame", F(AP_X, HDR_Y, 0.028), K(AP_W + 0.028,
            HDR_H + 0.010, 0.012), gun_d, rot=FACE_ROT, bevel=K(0.002)))
    hdr_pts = [F(ap_l, HDR_Y - HDR_H / 2, 0.033), F(ap_r, HDR_Y - HDR_H / 2, 0.033),
               F(ap_r, HDR_Y + HDR_H / 2, 0.033), F(ap_l, HDR_Y + HDR_H / 2, 0.033)]

    # spool cradle + the return line running between them
    spool_objs, spool_pivots = [], []
    for si, sx in enumerate(SPOOL_X):
        add(cyl(f"pkt_spool_boss_{si}", F(sx, SPOOL_Y, 0.020),
                K(SPOOL_R + 0.005), K(0.014), gun_d, rot=FACE_ROT, verts=28))
        sc = F(sx, SPOOL_Y, 0.034)
        sp = pivot(f"pkt_spool_pivot_{si}", sc)
        parts = [tube(f"pkt_spool_rim_{si}", sc, K(SPOOL_R), K(SPOOL_R - 0.006),
                      K(0.020), chrome, rot=FACE_ROT, verts=28),
                 cyl(f"pkt_spool_web_{si}", sc, K(SPOOL_R - 0.005), K(0.008),
                     ebon, rot=FACE_ROT, verts=28),
                 cyl(f"pkt_spool_hub_{si}", sc, K(0.0085), K(0.024), chrome,
                     rot=FACE_ROT, verts=14)]
        for k in range(6):
            th = 2 * math.pi * k / 6
            off = Vector((-math.sin(th) * K(SPOOL_R * 0.5),
                          math.cos(th) * K(SPOOL_R * 0.5), 0.0))
            off.rotate(Euler(FACE_ROT, 'XYZ'))
            parts.append(box(f"pkt_spool_spoke_{si}_{k}", sc + off,
                             K(0.0055, SPOOL_R * 0.92, 0.014), chrome_d,
                             rot=(Euler(FACE_ROT, 'XYZ').to_matrix()
                                  @ Matrix.Rotation(th, 3, 'Z')).to_euler()))
        wit = Vector((0.0, K(SPOOL_R - 0.007), 0.0))
        wit.rotate(Euler(FACE_ROT, 'XYZ'))
        parts.append(cyl(f"pkt_spool_witness_{si}", sc + wit, K(0.0050),
                         K(0.022), red, rot=FACE_ROT, verts=10))
        addall(parts)
        attach(sp, parts)
        spool_objs.append(parts)
        spool_pivots.append(sp)
    add(box("pkt_return_line", F((SPOOL_X[0] + SPOOL_X[1]) / 2, SPOOL_Y + 0.026,
                                 0.032), K(abs(SPOOL_X[1] - SPOOL_X[0]), 0.004,
                                           0.004), paper, rot=FACE_ROT))

    # the platen: blank, advancing.  This is the ONLY thing behind the glass;
    # every returned byte is painted over it live by the frontend.
    plat_c = F(AP_X, AP_Y, 0.016)
    p_piv = pivot("pkt_platen_pivot", plat_c)
    platen = [box("pkt_platen", plat_c, K(AP_W + 0.006, AP_H + 0.120, 0.0024),
                  paper, rot=FACE_ROT)]
    for i in range(22):
        yy = AP_Y - (AP_H + 0.110) / 2 + i * (AP_H + 0.110) / 21.0
        for j, xx in enumerate((ap_l + 0.009, ap_r - 0.009)):
            platen.append(cyl(f"pkt_platen_hole_{i}_{j}",
                              F(xx, yy, 0.0172), K(0.0031), K(0.0022), ebon,
                              rot=FACE_ROT, verts=8, smooth=False))
    # fanfold PERFORATION lines: paper features, not content -- they are what
    # makes the advance read as motion in a deliberately blank aperture.
    for i, fy in enumerate((-0.070, 0.002, 0.074)):
        for k in range(17):
            xx = ap_l + 0.016 + k * (AP_W - 0.032) / 16.0
            platen.append(box(f"pkt_platen_perf_{i}_{k}",
                              F(xx, AP_Y + fy, 0.0174),
                              K(0.0060, 0.0016, 0.0012), gun_d, rot=FACE_ROT))
    addall(platen)
    attach(p_piv, platen)

    # a short scrap of generic printed tape, FAR VIEW ONLY, so the aperture
    # reads as a printer rather than a blank slot in the wide shot (plan §4).
    far_ticks = []
    for i in range(7):
        yy = AP_Y + AP_H / 2 - 0.017 - i * 0.019
        w = (0.170, 0.132, 0.158, 0.096, 0.144, 0.070, 0.118)[i]
        t = box(f"pkt_farticks_{i}", F(AP_X - (AP_W - 0.030 - w) / 2, yy, 0.0186),
                K(w, 0.0085, 0.0014), ink, rot=FACE_ROT)
        add(t)
        far_ticks.append(t)

    # ------------------------------------------------- verdict: IMPACT lamps
    add(box("pkt_vrd_plate", F(VRD_X, VRD_Y - 0.012, 0.030),
            K(0.048, 0.156, 0.010), gun_d, rot=FACE_ROT, bevel=K(0.002)))
    add(ftext("pkt_vrd_label", "IMPACT", 0.0090, label, VRD_X, VRD_Y + 0.052,
              0.037))
    vrd_lamps, vrd_off, vrd_on = [], [], []
    for i, (off_m, on_m) in enumerate(((lamp_off_g, lamp_on_g),
                                       (lamp_off_a, lamp_on_a),
                                       (lamp_off_r, lamp_on_r))):
        yy = VRD_Y - i * VRD_DY
        add(tube(f"pkt_vrd_ring_{i}", F(VRD_X, yy, 0.034), K(0.0136),
                 K(0.0098), K(0.010), chrome, rot=FACE_ROT, verts=18))
        d = ball(f"pkt_vrd_lamp_{i}", F(VRD_X, yy, 0.0365), K(0.0096), off_m,
                 scale=(1, 1, 0.62), rot=FACE_ROT)
        vrd_lamps.append(add(d))
        vrd_off.append(off_m)
        vrd_on.append(on_m)
    hdr_bar = add(box("pkt_hdr_bar", F(AP_X, HDR_Y, 0.033),
                      K(AP_W + 0.006, HDR_H, 0.004), hdr_idle, rot=FACE_ROT))

    # ------------------------------------------------------------ parenting
    for o in made:
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = Matrix.Identity(4)
    for e in (w_piv, l_piv, d_piv, t_piv, c_piv, f_piv, p_piv) + tuple(spool_pivots):
        e.parent = root
        e.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()

    ctrl_objs = set()
    for grp in (wheel, lever, tubes, tube_domes, chg_pips, drum, payload_txt,
                cage, toggle, arm_lamps, plunger, flash, platen, vrd_lamps,
                [hdr_bar], far_ticks, spool_objs[0], spool_objs[1]):
        ctrl_objs.update(grp)

    static = [o for o in made if o not in ctrl_objs]
    far = [o for o in made if o not in hidden and o not in set(far_ticks)] \
        + far_ticks
    far = [o for o in far if o not in set(hidden)]

    controls = {
        "target": {
            "kind": "rotate", "label": "TARGET BEARING", "objs": wheel,
            "pivot": w_piv, "anchor": F(WHEEL_X, WHEEL_Y, 0.020),
            "range": TARGET_RANGE, "snap": "blips",
            "hotspot_objs": wheel + [o for o in static
                                     if o.name.startswith("pkt_scope")
                                     or o.name.startswith("pkt_blip")
                                     or o.name.startswith("pkt_bearing")],
            "overlay_pts": [F(SCOPE_X - 0.059, SCOPE_Y - 0.067, 0.0090),
                            F(SCOPE_X + 0.059, SCOPE_Y - 0.067, 0.0090),
                            F(SCOPE_X + 0.059, SCOPE_Y - 0.047, 0.0090),
                            F(SCOPE_X - 0.059, SCOPE_Y - 0.047, 0.0090)]},
        "payload": {
            "kind": "frames", "axis": "x", "label": "PAYLOAD SELECT",
            "objs": drum + payload_txt, "pivot": d_piv, "texts": payload_txt,
            "drum": drum, "labels": PAYLOADS,
            "hotspot_objs": drum + [o for o in static
                                    if o.name.startswith("pkt_drum")
                                    or o.name.startswith("pkt_breech")]},
        "charge": {
            "kind": "frames", "axis": "y", "label": "CHARGE",
            "objs": lever + tubes + tube_domes + chg_pips, "pivot": l_piv,
            "lever": lever, "tubes": tubes + tube_domes, "tube_lv": tube_lv,
            "pips": chg_pips, "pip_off": chg_pip_off, "pip_on": chg_pip_on,
            "throw": K(CHG_THROW), "frames": CHARGE_FRAMES,
            "hotspot_objs": lever + tubes + tube_domes + chg_pips
            + [o for o in static if o.name.startswith("pkt_chg")
               or o.name.startswith("pkt_tube")]},
        "arm": {
            "kind": "states", "label": "ARM", "objs": cage + toggle + arm_lamps,
            "cage": cage, "toggle": toggle, "cage_piv": c_piv, "tog_piv": t_piv,
            "lamps": arm_lamps, "off": arm_lamp_off, "on": arm_lamp_on,
            "order": ARM_ORDER,
            "hotspot_objs": cage + toggle + arm_lamps
            + [o for o in static if o.name.startswith("pkt_arm")]},
        "fire": {
            "kind": "states", "label": "FIRE", "objs": plunger + flash,
            "plunger": plunger, "flash": flash, "piv": f_piv,
            "order": FIRE_ORDER, "drop": K(0.026),
            "hotspot_objs": plunger + [o for o in static
                                       if o.name.startswith("pkt_fire")]},
        "catch": {
            "kind": "frames", "axis": "y", "label": "RETURN LINE",
            "objs": platen + spool_objs[0] + spool_objs[1],
            "platen": platen, "platen_piv": p_piv,
            "spools": spool_objs, "spool_pivots": spool_pivots,
            "frames": CATCH_FRAMES, "advance": K(0.021),
            "overlay_pts": ap_pts,
            "hotspot_objs": platen + spool_objs[0] + spool_objs[1]
            + aperture_frame + [o for o in static
                                if o.name.startswith("pkt_prn")
                                or o.name.startswith("pkt_tear")
                                or o.name.startswith("pkt_spool")]},
        "verdict": {
            "kind": "states", "label": "IMPACT", "objs": vrd_lamps + [hdr_bar],
            "lamps": vrd_lamps, "off": vrd_off, "on": vrd_on, "hdr": hdr_bar,
            "hdr_mats": {"idle": hdr_idle, "hit": hdr_hit,
                         "refused": hdr_ref, "deflected": hdr_def},
            "order": VERDICT_ORDER, "overlay_pts": hdr_pts,
            "hotspot_objs": vrd_lamps
            + [o for o in static if o.name.startswith("pkt_vrd")]},
    }

    return {"far": far, "controls": controls, "root": root, "static": static,
            "all": made, "hidden": hidden, "far_only": far_ticks}


# =========================================================== render harness
RTYPES = {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}


def renderables(scene):
    return [o for o in scene.objects if o.type in RTYPES]


def render_to(scene, path, visible, holdout=()):
    """Render only `visible`; `holdout` objects stay in the depth buffer but
    punch alpha, so a sprite is correctly clipped by the geometry in front of
    it (LOG's trick, extended by MQB to the whole shell)."""
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


def glow_render(scene, path, objs, holdout=()):
    g = mat("glowmask", (1, 1, 1, 1), 0.0, 0.5, emission=(1, 1, 1, 1),
            strength=1.0)
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


def pts_rect(scene, cam, root, pts, pad=0):
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


def cut_left(r, x):
    """Trim a rect's LEFT edge to x (keeps the control's own art)."""
    if x <= r["x"]:
        return r
    return {"x": x, "y": r["y"], "w": max(1, r["x"] + r["w"] - x), "h": r["h"]}


def cut_right(r, x):
    if x >= r["x"] + r["w"]:
        return r
    return {"x": r["x"], "y": r["y"], "w": max(1, x - r["x"]), "h": r["h"]}


def clamp_rect(r, w, h):
    x0, y0 = max(0, r["x"]), max(0, r["y"])
    x1, y1 = min(w, r["x"] + r["w"]), min(h, r["y"] + r["h"])
    return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}


def fit_camera(scene, cam, objs, target, view_dir, frac=0.86, iters=5):
    """Dolly + re-aim along `view_dir` until `objs` fill `frac` of frame."""
    from bpy_extras.object_utils import world_to_camera_view
    cam.rotation_euler = (target - cam.location) \
        .to_track_quat('-Z', 'Y').to_euler()
    for _ in range(iters):
        bpy.context.view_layer.update()
        xs, ys = [], []
        for o in objs:
            for c in o.bound_box:
                co = world_to_camera_view(scene, cam, o.matrix_world @ Vector(c))
                xs.append(co.x)
                ys.append(co.y)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        s = min(3.0, max(0.30, max(max(xs) - min(xs), max(ys) - min(ys)) / frac))
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


# ------------------------------------------------------------ state setters
def set_charge(c, f):
    m = c["tube_lv"][f]
    for o in c["tubes"]:
        o.data.materials[0] = m
    for i, p in enumerate(c["pips"]):
        p.data.materials[0] = c["pip_on"][i] if i <= f else c["pip_off"][i]
    slide(c["pivot"], 'up', c["throw"] * f / (c["frames"] - 1))
    bpy.context.view_layer.update()


def set_payload(c, i):
    spin(c["pivot"], 'z', -45.0 * i)
    for k, t in enumerate(c["texts"]):
        t.hide_render = (k != i)
    bpy.context.view_layer.update()


def set_arm(c, name):
    cage_ang = {"safe": 0.0, "armed": 78.0, "interlock": 0.0}[name]
    tog_ang = {"safe": -34.0, "armed": 30.0, "interlock": -30.0}[name]
    lit = {"safe": (0, 0), "armed": (1, 0), "interlock": (0, 1)}[name]
    spin(c["cage_piv"], 'x', -cage_ang)
    spin(c["tog_piv"], 'x', tog_ang)
    for i, d in enumerate(c["lamps"]):
        d.data.materials[0] = c["on"][i] if lit[i] else c["off"][i]
    bpy.context.view_layer.update()


def set_fire(c, name):
    slide(c["piv"], 'n', -c["drop"] if name == "fired" else 0.0)
    bpy.context.view_layer.update()


def set_catch(c, f):
    for si, p in enumerate(c["spool_pivots"]):
        spin(p, 'z', -f * 34.0 * (1 if si == 0 else -1))
    slide(c["platen_piv"], 'up', c["advance"] * f)
    bpy.context.view_layer.update()


def set_verdict(c, name):
    lit = {"idle": None, "hit": 0, "refused": 1, "deflected": 2}[name]
    for i, d in enumerate(c["lamps"]):
        d.data.materials[0] = c["on"][i] if i == lit else c["off"][i]
    c["hdr"].data.materials[0] = c["hdr_mats"][name]
    bpy.context.view_layer.update()


def close_rig(scene, root, objs, main_cam):
    """Close-up camera along the pilot's own sight-line (so the console matches
    its far view), plus a harder, cooler key and a red under-glow from the
    tube bank -- a weapon should look harder-lit than the brass panels."""
    ctr = root.matrix_world @ F(0.03, 0.02, 0.05)
    view = (main_cam.matrix_world.translation - ctr).normalized()
    bpy.ops.object.camera_add(location=ctr + view * 1.4)
    cam = bpy.context.object
    cam.name = "pkt_closecam"
    cam.data.lens = 50.0
    ctr = fit_camera(scene, cam, objs, ctr, view, frac=0.88)

    up = (root.matrix_world.to_3x3() @ UPV).normalized()
    right = view.cross(up).normalized()
    lights = []
    for i, (off, energy, size, col) in enumerate((
            (right * 0.62 + up * 0.60 + view * 0.46, 2.4, 0.20,
             (0.80, 0.87, 1.00)),                       # hard cool key
            (-right * 0.72 + up * 0.34 + view * 0.52, 1.1, 0.55,
             (0.60, 0.70, 0.98)),                       # cool fill
            (-up * 0.30 + view * 0.26, 0.9, 0.40,
             (1.00, 0.30, 0.16)),                       # red under-glow
            (right * 0.06 + up * 0.72 + view * 0.16, 0.7, 0.45,
             (1.00, 0.66, 0.38)))):                     # warm tube spill
        p = ctr + off
        bpy.ops.object.light_add(type='AREA', location=p)
        L = bpy.context.object
        L.name = f"pkt_light_{i}"
        L.data.energy, L.data.size = energy, size
        L.data.color = col
        L.rotation_euler = (ctr - p).to_track_quat('-Z', 'Y').to_euler()
        lights.append(L)
    return cam, lights


def main():
    os.makedirs(OUT, exist_ok=True)
    P = dict(shell.PARAMS)
    scene = shell.build(P)                    # UNMODIFIED shell + main camera
    far_cam = scene.camera
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    res = add_props(P, mats)
    scene.render.film_transparent = True
    mine = set(res["all"])
    ctl = res["controls"]
    root = res["root"]
    W, H = scene.render.resolution_x, scene.render.resolution_y
    shell_meshes = [o for o in renderables(scene) if o not in mine]

    # ------------------------------------------------------------- far shot
    render_to(scene, os.path.join(OUT, "far_prop.png"), res["far"],
              holdout=shell_meshes)
    far_hot = clamp_rect(bbox_rect(scene, far_cam, res["far"], pad=6), W, H)
    glow_render(scene, os.path.join(OUT, "far_glow.png"), res["far"],
                holdout=shell_meshes)
    render_to(scene, os.path.join(OUT, "_shell_plate.png"), shell_meshes)

    # ----------------------------------------------------------- close shot
    close_objs = [o for o in res["far"] if o not in set(res["far_only"])]
    cam, _lights = close_rig(scene, root, close_objs, far_cam)
    scene.camera = cam
    bpy.context.view_layer.update()

    static = res["static"]
    clip = static + shell_meshes
    plate = shell_meshes + static
    render_to(scene, os.path.join(OUT, "close_plate.png"), plate)

    C = {}

    # --- target: one render, spun in CSS about its projected hub ----------
    c = ctl["target"]
    render_to(scene, os.path.join(OUT, "close_target.png"), c["objs"],
              holdout=clip)
    px, py = project(scene, cam, root.matrix_world @ c["anchor"])
    C["target"] = {
        "kind": "rotate", "label": c["label"], "image": "close_target.png",
        "pivot": {"x": round(px, 1), "y": round(py, 1)}, "range": c["range"],
        "snap": c["snap"],
        "overlay": {"rect": clamp_rect(pts_rect(scene, cam, root,
                                                c["overlay_pts"]), W, H),
                    "style": "phosphor", "scroll": False},
        "hotspot": clamp_rect(bbox_rect(scene, cam, c["hotspot_objs"], pad=8),
                              W, H)}

    # --- payload: 8 drum indices, axis X ----------------------------------
    c = ctl["payload"]
    frames, rects = [], [bbox_rect(scene, cam, c["hotspot_objs"], pad=8)]
    for i in range(len(PAYLOADS)):
        set_payload(c, i)
        fn = f"close_payload_{i}.png"
        render_to(scene, os.path.join(OUT, fn),
                  c["drum"] + [c["texts"][i]], holdout=clip)
        frames.append(fn)
        rects.append(bbox_rect(scene, cam, c["drum"] + [c["texts"][i]], pad=8))
    set_payload(c, 0)
    C["payload"] = {"kind": "frames", "axis": "x", "label": c["label"],
                    "frames": frames, "labels": c["labels"],
                    "hotspot": clamp_rect(union(rects), W, H)}

    # --- charge: 5 frames, axis Y -----------------------------------------
    c = ctl["charge"]
    frames, rects = [], [bbox_rect(scene, cam, c["hotspot_objs"], pad=8)]
    for f in range(c["frames"]):
        set_charge(c, f)
        fn = f"close_charge_{f}.png"
        render_to(scene, os.path.join(OUT, fn), c["objs"], holdout=clip)
        frames.append(fn)
        rects.append(bbox_rect(scene, cam, c["objs"], pad=8))
    set_charge(c, 0)
    C["charge"] = {"kind": "frames", "axis": "y", "label": c["label"],
                   "frames": frames,
                   "hotspot": clamp_rect(union(rects), W, H)}

    # --- arm: safe / armed / interlock -------------------------------------
    c = ctl["arm"]
    states, rects = {}, [bbox_rect(scene, cam, c["hotspot_objs"], pad=8)]
    for nm in c["order"]:
        set_arm(c, nm)
        fn = f"close_arm_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), c["objs"], holdout=clip)
        states[nm] = fn
        rects.append(bbox_rect(scene, cam, c["objs"], pad=8))
    set_arm(c, "safe")
    C["arm"] = {"kind": "states", "label": c["label"], "states": states,
                "order": ["safe", "armed"], "refusal": "interlock",
                "hotspot": clamp_rect(union(rects), W, H)}

    # --- fire: ready / fired ----------------------------------------------
    c = ctl["fire"]
    states, rects = {}, [bbox_rect(scene, cam, c["hotspot_objs"], pad=8)]
    for nm in c["order"]:
        set_fire(c, nm)
        vis = c["plunger"] + (c["flash"] if nm == "fired" else [])
        fn = f"close_fire_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), vis, holdout=clip)
        states[nm] = fn
        rects.append(bbox_rect(scene, cam, c["plunger"], pad=8))
    set_fire(c, "ready")
    C["fire"] = {"kind": "states", "label": c["label"], "states": states,
                 "order": c["order"],
                 "hotspot": clamp_rect(union(rects), W, H)}

    # --- catch: 4 motion frames + the LIVE TEXT aperture -------------------
    c = ctl["catch"]
    frames, rects = [], [bbox_rect(scene, cam, c["hotspot_objs"], pad=8)]
    for f in range(c["frames"]):
        set_catch(c, f)
        fn = f"close_catch_{f}.png"
        render_to(scene, os.path.join(OUT, fn), c["objs"], holdout=clip)
        frames.append(fn)
    set_catch(c, 0)
    ov = clamp_rect(pts_rect(scene, cam, root, c["overlay_pts"], pad=-4), W, H)
    C["catch"] = {
        "kind": "frames", "axis": "y", "label": c["label"], "frames": frames,
        "overlay": {"rect": ov, "style": "ink", "scroll": True,
                    "paper": "#d8d2c0", "ink": "#141210",
                    "note": "untrusted bytes from a target service -- render "
                            "as TEXT (textContent), never as HTML"},
        "hotspot": clamp_rect(union(rects), W, H)}

    # --- verdict: idle / hit / refused / deflected -------------------------
    c = ctl["verdict"]
    states = {}
    for nm in c["order"]:
        set_verdict(c, nm)
        fn = f"close_verdict_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), c["objs"], holdout=clip)
        states[nm] = fn
    set_verdict(c, "idle")
    # the tinted header bar is part of the SPRITE but not of the click target:
    # the printer body under it belongs to `catch`.
    rects = [bbox_rect(scene, cam, c["hotspot_objs"], pad=8)]
    C["verdict"] = {
        "kind": "states", "label": c["label"], "states": states,
        "order": c["order"],
        "overlay": {"rect": clamp_rect(pts_rect(scene, cam, root,
                                                c["overlay_pts"], pad=-3), W, H),
                    "style": "header", "scroll": False},
        "hotspot": clamp_rect(union(rects), W, H)}

    # ---- make the hotspots DISJOINT in code, so the combined frontend never
    # has to arbitrate by DOM order (OTA's precedent; MTA's warning).
    C["charge"]["hotspot"] = cut_left(
        C["charge"]["hotspot"], C["target"]["hotspot"]["x"]
        + C["target"]["hotspot"]["w"])
    C["payload"]["hotspot"] = cut_left(
        C["payload"]["hotspot"], C["charge"]["hotspot"]["x"]
        + C["charge"]["hotspot"]["w"])
    C["catch"]["hotspot"] = cut_left(
        C["catch"]["hotspot"], C["verdict"]["hotspot"]["x"]
        + C["verdict"]["hotspot"]["w"])
    for k in ("arm", "fire"):
        C[k]["hotspot"] = cut_right(C[k]["hotspot"],
                                    C["verdict"]["hotspot"]["x"])
    C["fire"]["hotspot"] = cut_left(
        C["fire"]["hotspot"], C["payload"]["hotspot"]["x"]
        + C["payload"]["hotspot"]["w"])

    manifest = {
        "code": CODE, "name": NAME, "surface": SURFACE,
        "slot": {"surface": "dash", "angle": SLOT_ANGLE, "t": SLOT_T},
        "far": {"prop": "far_prop.png", "glow": "far_glow.png",
                "glow_tint": "red", "hotspot": far_hot},
        "close": {"canvas": {"w": W, "h": H}, "plate": "close_plate.png",
                  "controls": C},
    }
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(HERE, "demo.html"), "w") as f:
        f.write(HTML.replace("__MANIFEST__", json.dumps(manifest)))

    print("PKT far hotspot", json.dumps(far_hot))
    for k, v in C.items():
        print("PKT close", k, v["kind"], json.dumps(v["hotspot"]),
              "overlay" if "overlay" in v else "")
    print("PKT catch overlay", json.dumps(C["catch"]["overlay"]["rect"]))
    print("PKT OK ->", OUT)


HTML = r"""<!doctype html>
<meta charset="utf-8">
<title>PKT &mdash; The Signal Harpoon</title>
<style>
 *{margin:0;padding:0;box-sizing:border-box}
 html,body{height:100%;background:#05070c;overflow:hidden;color:#9aa7b8;
   font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
 #viewport{position:fixed;inset:0;display:grid;place-items:center}
 #stage{position:relative;width:1280px;height:720px;transform-origin:0 0}
 .layer{position:absolute;left:0;top:0;width:1280px;height:720px;
   pointer-events:none;user-select:none;-webkit-user-drag:none}
 #target{transition:transform .35s cubic-bezier(.3,.8,.4,1)}
 .hot{position:absolute;border:1px solid transparent;border-radius:3px;
   cursor:pointer;transition:background .13s,border-color .13s}
 .hot:hover{background:rgba(255,60,40,.13);border-color:rgba(255,110,80,.75)}
 body.debug .hot{border-color:rgba(80,200,255,.5);background:rgba(80,200,255,.07)}
 .hot::after{content:attr(data-label);position:absolute;left:50%;top:-17px;
   transform:translateX(-50%);font-size:9px;letter-spacing:.16em;color:#ff8a6a;
   opacity:0;transition:opacity .13s;white-space:nowrap;text-shadow:0 0 6px #000}
 .hot:hover::after,body.debug .hot::after{opacity:1}

 /* ---- THE LIVE TEXT OVERLAY: arbitrary returned bytes, painted into the
    aperture rect exported by the manifest.  Never innerHTML. ---- */
 #catchtext{position:absolute;overflow:auto;white-space:pre-wrap;
   word-break:break-word;background:rgba(216,210,192,.90);color:#141210;
   font:11px/1.32 ui-monospace,SFMono-Regular,Menlo,monospace;
   padding:3px 5px;letter-spacing:.02em;
   box-shadow:inset 0 0 14px rgba(60,50,30,.45)}
 #catchtext.empty{background:transparent;box-shadow:none}
 #hdrtext{position:absolute;display:flex;align-items:center;
   justify-content:space-between;padding:0 6px;pointer-events:none;
   font-size:10px;letter-spacing:.20em;color:#05070c;font-weight:700}
 #locktext{position:absolute;display:flex;align-items:center;
   justify-content:center;pointer-events:none;font-size:10px;
   letter-spacing:.12em;color:#5dff9a;text-shadow:0 0 6px rgba(60,255,150,.7)}

 #side{position:fixed;right:0;top:0;bottom:0;width:340px;z-index:9;
   background:linear-gradient(to left,rgba(5,7,12,.96),rgba(5,7,12,.62));
   border-left:1px solid #2a1a18;padding:14px 16px;display:flex;
   flex-direction:column;gap:9px;overflow:auto}
 h1{font-size:11px;letter-spacing:.22em;color:#ff7a5c;font-weight:400}
 .sub{color:#5f6b7d;letter-spacing:.12em}
 .grp{border:1px solid #221a1a;padding:7px 8px}
 .grp>b{display:block;font-weight:400;color:#7f6a62;letter-spacing:.18em;
   font-size:9px;margin-bottom:5px}
 .row{display:flex;gap:5px;flex-wrap:wrap;align-items:center}
 button{font:inherit;letter-spacing:.12em;text-transform:uppercase;
   padding:5px 8px;background:rgba(14,18,26,.9);color:#9aa7b8;
   border:1px solid #2e3a48;cursor:pointer}
 button:hover{color:#e6eef8;border-color:#5a6b7e}
 button[aria-pressed="true"]{background:#b8331f;color:#fff;border-color:#ff7a5c}
 button.big{flex:1;padding:8px;background:#4a0f0a;color:#ffb9a6;
   border-color:#8d2417}
 button.big:disabled{background:#12161c;color:#3d4652;border-color:#232b34;
   cursor:not-allowed}
 .pill{padding:2px 6px;border:1px solid #2e3a48;color:#7f8b9c}
 .pill.on{color:#0a0d12;background:#5dff9a;border-color:#5dff9a}
 .pill.warn{color:#0a0d12;background:#ffb03c;border-color:#ffb03c}
 .pill.bad{color:#fff;background:#c9331f;border-color:#ff7a5c}
 #log{flex:1;min-height:90px;overflow:auto;background:#080b10;
   border:1px solid #1b232c;padding:7px 8px;white-space:pre-wrap;
   line-height:1.5;font-size:10px;color:#7e8b9c}
 input[type=range]{width:100%}
</style>
<div id="viewport"><div id="stage"></div></div>
<div id="side">
  <h1>PKT &middot; SIGNAL HARPOON<br>
    <span class="sub">DIRECTIONAL TRANSCEIVER</span></h1>
  <div class="grp"><b>1 &middot; TARGET BEARING</b>
    <input id="bear" type="range" min="-140" max="140" value="0">
    <div class="row"><span id="lock" class="pill">NO CONTACT</span>
      <span class="sub" id="bearv">000</span></div></div>
  <div class="grp"><b>2 &middot; PAYLOAD SELECT</b>
    <div class="row"><button id="pprev">&lt;</button>
      <span id="pname" class="pill" style="flex:1;text-align:center"></span>
      <button id="pnext">&gt;</button></div></div>
  <div class="grp"><b>3 &middot; CHARGE</b>
    <input id="chg" type="range" min="0" max="4" value="0">
    <div class="row"><span id="chgv" class="pill">0 / 4</span>
      <span class="sub">redline at 3</span></div></div>
  <div class="grp"><b>4 &middot; ARM</b>
    <div class="row"><button id="armb">throw master arm</button>
      <span id="armv" class="pill">SAFE</span></div></div>
  <div class="grp"><b>5 &middot; FIRE</b>
    <div class="row"><button id="fireb" class="big" disabled>fire</button></div>
  </div>
  <div class="grp"><b>RETURN</b>
    <div class="row"><span id="vrd" class="pill">IDLE</span>
      <span class="sub" id="vrdn">nothing reeled in</span></div></div>
  <div id="log"></div>
  <div class="row"><button id="dbg" aria-pressed="false">hotspots</button>
    <button id="rst">reset</button></div>
  <div class="sub" style="opacity:.6;line-height:1.55">
    Targets are automated systems out in the void &mdash; derelicts, unmanned
    relays, listening posts. Nothing fires back. The returned bytes are
    <b>untrusted</b> and are written with textContent, never innerHTML.
  </div>
</div>
<script>
var M = __MANIFEST__;
var C = M.close.controls, W = M.close.canvas.w, H = M.close.canvas.h;
var stage = document.getElementById("stage");
function el(t, id){var e=document.createElement(t); if(id) e.id=id;
  stage.appendChild(e); return e;}
function img(src, id){var i=el("img", id); i.className="layer";
  i.src="out/"+src; return i;}

img(M.close.plate);
var Ltarget  = img(C.target.image, "target");
var Lpayload = img(C.payload.frames[0]);
var Lcharge  = img(C.charge.frames[0]);
var Larm     = img(C.arm.states.safe);
var Lfire    = img(C.fire.states.ready);
var Lcatch   = img(C.catch.frames[0]);
var Lverdict = img(C.verdict.states.idle);
Ltarget.style.transformOrigin = C.target.pivot.x+"px "+C.target.pivot.y+"px";

function place(e, r){ e.style.cssText += ";left:"+r.x+"px;top:"+r.y+"px;width:"
  +r.w+"px;height:"+r.h+"px"; }
var catchText = el("div", "catchtext"); place(catchText, C.catch.overlay.rect);
var hdrText   = el("div", "hdrtext");   place(hdrText, C.verdict.overlay.rect);
var lockText  = el("div", "locktext");  place(lockText, C.target.overlay.rect);

/* ------------------------------------------------------- fake target list */
var CONTACTS = [
  {b:-118, id:"DERELICT LV-2277",  ok:["RCE","TRAVERSAL"]},
  {b: -74, id:"RELAY BUOY K-9",    ok:["AUTH-BYPASS"]},
  {b: -21, id:"LISTENING POST TAU",ok:["INJECTION","SSRF"]},
  {b:  33, id:"ORE HAULER (DEAD)", ok:["OVERFLOW"]},
  {b:  86, id:"BEACON GX-04",      ok:["SUPPLY-CHAIN"]},
  {b: 127, id:"SURVEY DRONE 11",   ok:["RESOURCE-DoS"]}
];
var RETURNS = {
  hit: function(t,p){ return "SIGNAL HARPOON // RETURN LINE\n"
    +"target : "+t.id+"\npayload: "+p+"\nexit   : 0\n"
    +"--------------------------------------------\n"
    +"$ cat /srv/ops/flag.txt\n"
    +"SAINTCON{h4rp00n_br1ngs_1t_b4ck}\n"
    +"$ ls -la /srv/ops\n"
    +"drwxr-xr-x  4 root root  4096 manifest.d\n"
    +"-rw-------  1 root root   118 flag.txt\n"
    +"-rw-r--r--  1 root root  9214 relay.conf\n"
    +"$ head -3 relay.conf\n"
    +"listen 0.0.0.0:7788\nauth  none   ; <-- left open\n"
    +"peers 4\n[return line spent - 412 bytes recovered]"; },
  refused: function(t,p){ return "SIGNAL HARPOON // RETURN LINE\n"
    +"target : "+t.id+"\npayload: "+p+"\nexit   : 1\n"
    +"--------------------------------------------\n"
    +"530 Not logged in.\n"
    +"the hull is hardened against "+p+".\n"
    +"try another munition class, or another contact."; },
  deflected: function(t,p){ return "SIGNAL HARPOON // RETURN LINE\n"
    +"target : "+t.id+"\npayload: "+p+"\nexit   : timeout\n"
    +"--------------------------------------------\n"
    +"connect: no route to host (after 20.0s)\n"
    +"[no effect - line reeled in empty]"; }
};
var VNAME = {idle:"", hit:"IMPACT", refused:"SHIELDED", deflected:"NO EFFECT"};

/* ------------------------------------------------------------------ state */
var st = {bear:0, lock:null, pay:0, chg:0, arm:"safe", fire:"ready",
          catch:0, verdict:"idle"};

function nearest(b){
  var best=null, d=999;
  CONTACTS.forEach(function(c){var k=Math.abs(c.b-b); if(k<d){d=k;best=c;}});
  return d<=9 ? best : null;
}
function log(s){var g=document.getElementById("log");
  g.textContent += (g.textContent?"\n":"")+s; g.scrollTop=g.scrollHeight;}

function render(){
  Ltarget.style.transform = "rotate("+st.bear.toFixed(1)+"deg)";
  Lpayload.src = "out/"+C.payload.frames[st.pay];
  Lcharge.src  = "out/"+C.charge.frames[st.chg];
  Larm.src     = "out/"+C.arm.states[st.arm];
  Lfire.src    = "out/"+C.fire.states[st.fire];
  Lcatch.src   = "out/"+C.catch.frames[st.catch];
  Lverdict.src = "out/"+C.verdict.states[st.verdict];

  lockText.textContent = st.lock ? st.lock.id : "NO CONTACT";
  lockText.style.color = st.lock ? "#5dff9a" : "#3f7a58";
  hdrText.textContent  = VNAME[st.verdict];
  hdrText.style.color  = st.verdict==="idle" ? "#5a6472" : "#05070c";

  document.getElementById("bearv").textContent =
    (st.bear<0?"-":"+")+("00"+Math.abs(Math.round(st.bear))).slice(-3);
  var lk=document.getElementById("lock");
  lk.textContent = st.lock? "LOCK" : "NO CONTACT";
  lk.className = "pill"+(st.lock?" on":"");
  document.getElementById("pname").textContent = C.payload.labels[st.pay];
  document.getElementById("chgv").textContent = st.chg+" / 4";
  var av=document.getElementById("armv");
  av.textContent = st.arm.toUpperCase();
  av.className = "pill"+(st.arm==="armed"?" bad":(st.arm==="interlock"?" warn":""));
  document.getElementById("fireb").disabled = (st.arm!=="armed");
  var vv=document.getElementById("vrd");
  vv.textContent = st.verdict.toUpperCase();
  vv.className = "pill"+({idle:"",hit:" on",refused:" warn",
                          deflected:" bad"}[st.verdict]);
  document.getElementById("vrdn").textContent =
    {idle:"nothing reeled in", hit:"secret recovered",
     refused:"target not vulnerable", deflected:"timeout / offline"}[st.verdict];
}

/* ------------------------------------------------------------- interaction */
var bear = document.getElementById("bear");
bear.addEventListener("input", function(){
  st.bear = +bear.value; st.lock = nearest(st.bear);
  if(st.arm!=="safe"){ st.arm="safe"; }
  render();
});
function setPay(d){ st.pay=(st.pay+d+C.payload.frames.length)
  %C.payload.frames.length; render(); }
document.getElementById("pprev").onclick=function(){setPay(-1);};
document.getElementById("pnext").onclick=function(){setPay(1);};
var chg = document.getElementById("chg");
chg.addEventListener("input", function(){ st.chg=+chg.value; render(); });

function doArm(){
  if(!st.lock || st.chg<3){
    st.arm="interlock";
    log("INTERLOCK: "+(!st.lock?"no target lock":"under-charged (need 3)"));
    render();
    setTimeout(function(){ st.arm="safe"; render(); }, 900);
    return;
  }
  st.arm = (st.arm==="armed") ? "safe" : "armed";
  log("master arm "+st.arm.toUpperCase());
  render();
}
document.getElementById("armb").onclick = doArm;

var busy=false;
function doFire(){
  if(st.arm!=="armed" || busy) return;
  busy=true;
  var t=st.lock, p=C.payload.labels[st.pay];
  st.fire="fired"; st.verdict="idle"; st.catch=0;
  catchText.textContent=""; catchText.className="empty";
  log("FIRE  -> "+t.id+"  ["+p+"]");
  render();
  var f=0;
  var iv=setInterval(function(){
    f++; st.catch=f%C.catch.frames.length; render();
    if(f>=9){
      clearInterval(iv);
      var v = t.ok.indexOf(p)>=0 ? "hit"
            : (Math.random()<0.25 ? "deflected" : "refused");
      st.verdict=v; st.catch=0; st.fire="ready"; st.arm="safe";
      /* UNTRUSTED CONTENT -> textContent, never innerHTML */
      catchText.textContent = RETURNS[v](t,p);
      catchText.className="";
      catchText.scrollTop=0;
      log("RETURN "+v.toUpperCase()+"  "+
          catchText.textContent.length+" bytes on the platen");
      busy=false; render();
    }
  }, 120);
}
document.getElementById("fireb").onclick = doFire;
document.getElementById("rst").onclick = function(){
  st={bear:0,lock:null,pay:0,chg:0,arm:"safe",fire:"ready",catch:0,
      verdict:"idle"};
  bear.value=0; chg.value=0; catchText.textContent="";
  catchText.className="empty";
  document.getElementById("log").textContent=""; render();
};
document.getElementById("dbg").onclick = function(){
  var on=document.body.classList.toggle("debug");
  this.setAttribute("aria-pressed", on?"true":"false");
};

/* ------------------------------ hotspots, straight from the manifest ------ */
function hotspot(name, fn){
  var r=C[name].hotspot, h=el("div"); h.className="hot";
  h.style.cssText="left:"+r.x+"px;top:"+r.y+"px;width:"+r.w+"px;height:"+r.h+"px";
  h.dataset.label=C[name].label;
  h.addEventListener("click", fn);
  return h;
}
hotspot("target", function(){
  var i=CONTACTS.indexOf(st.lock);
  st.lock = CONTACTS[(i+1)%CONTACTS.length];
  st.bear = st.lock.b; bear.value=st.bear; render();
});
hotspot("payload", function(){ setPay(1); });
hotspot("charge",  function(){ st.chg=(st.chg+1)%5; chg.value=st.chg; render(); });
hotspot("arm",     doArm);
hotspot("fire",    doFire);
hotspot("verdict", function(){ var o=C.verdict.order;
  st.verdict=o[(o.indexOf(st.verdict)+1)%o.length]; render(); });
hotspot("catch",   function(){ catchText.scrollTop += 40; });

function layout(){
  var s=Math.min((innerWidth-350)/W, innerHeight/H);
  stage.style.transform="translate("+((innerWidth-350-W*s)/2)+"px,"+
    ((innerHeight-H*s)/2)+"px) scale("+s+")";
}
addEventListener("resize", layout);
catchText.className="empty";
layout(); render();
log("SIGNAL HARPOON online. capacitor bank idling.");
</script>
"""


if __name__ == "__main__":
    main()
