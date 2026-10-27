"""
FMM -- file-management-module  ->  CARGO BAY / MANIFEST VAULT
Cockpit control for the SAINTCON 2026 AppSec Challenge.

The module is FTP-like: orders go down a CONTROL channel while the payload
travels on a SEPARATE DATA connection negotiated per transfer (PASV / PORT).
The panel is split to match:

    upper deck  = CONTROL CHANNEL
        * CARGO LIFT lever      (frames)  -- RETR / STOR, how hard the hoist pulls
        * HOLD gauge            (rotate)  -- hold capacity, needle spun in CSS
        * CHANNEL selector      (states)  -- PASV (server listens) / PORT (we do)
    lower deck  = DATA CHANNEL
        * DATA RAIL skid        (frames)  -- the crate itself, moving on its own
                                             rail, independent of the orders above

Run standalone:
    /Applications/Blender.app/Contents/MacOS/Blender --background --python build.py
"""
import bpy, math, os, sys, json
from mathutils import Vector, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
COCKPIT = os.path.dirname(os.path.dirname(HERE))
if COCKPIT not in sys.path:
    sys.path.insert(0, COCKPIT)
import shell                                              # noqa: E402
import slots                                              # noqa: E402

CODE = "FMM"
NAME = "Cargo Bay"
SURFACE = slots.SLOTS[CODE]["surface"]
OUT = os.path.join(HERE, "out")

# how far the whole panel is lifted off the (curved) dash face so its flat
# edges don't sink into the cone
LIFT = 0.010

LIFT_FRAMES = 6
LIFT_MIN, LIFT_MAX = 30.0, 70.0           # deg off the panel normal
LIFT_REST = 50.0                          # pose used in the wide shot
RAIL_FRAMES = 7
RAIL_X0, RAIL_X1 = -0.085, 0.195          # skid travel along the data rail
GAUGE_RANGE = [-125.0, 125.0]
SEL_ANGLE = 34.0                          # PASV / PORT pointer deflection


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


def _box(name, center, size, mat, rot=(0, 0, 0), bevel=0.0025):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    if bevel:
        m = o.modifiers.new("bev", 'BEVEL')
        m.width, m.segments = bevel, 2
    o.data.materials.append(mat)
    return o


def _sphere(name, loc, r, mat, scale=(1, 1, 1), seg=24, ring=14):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg,
                                         ring_count=ring, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
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


# ------------------------------------------------------------------- build
def add_props(P, mats):
    """Add the FMM cargo-bay control panel to the CURRENT scene.

    P    : the shell PARAMS dict (already built)
    mats : {"brass":..., "hull":..., "hull_d":...}
    Returns {"far": [...], "controls": {...}, "plate": [...], "root": obj}
    """
    brass = mats["brass"]
    hull = mats["hull"]
    hull_d = mats["hull_d"]
    ivory = _mat("fmm_ivory", (0.84, 0.80, 0.70, 1), 0.0, 0.45)
    card = _mat("fmm_card", (0.46, 0.41, 0.30, 1), 0.0, 0.62)
    ink = _mat("fmm_ink", (0.09, 0.08, 0.07, 1), 0.0, 0.70)
    crate_m = _mat("fmm_crate", (0.26, 0.18, 0.10, 1), 0.0, 0.68)
    panel_m = _mat("fmm_panel", (0.026, 0.028, 0.034, 1), 0.10, 0.55)
    well_m = _mat("fmm_well", (0.014, 0.015, 0.018, 1), 0.05, 0.70)
    needle_m = _mat("fmm_needle", (0.90, 0.22, 0.16, 1), 0.0, 0.35,
                    emission=(1.0, 0.24, 0.16, 1), emit_strength=2.2)
    lamp_off = _mat("fmm_lamp_off", (0.16, 0.11, 0.04, 1), 0.0, 0.40)
    lamp_amb = _mat("fmm_lamp_amber", (1.0, 0.72, 0.24, 1), 0.0, 0.30,
                    emission=(1.0, 0.60, 0.16, 1), emit_strength=3.2)
    lamp_cy = _mat("fmm_lamp_cyan", (0.40, 0.90, 1.0, 1), 0.0, 0.30,
                   emission=(0.22, 0.78, 1.0, 1), emit_strength=3.2)

    root = _empty("fmm_root", (0, 0, 0))

    plate, far = [], []

    def keep(o, parent=None, static=True):
        _adopt(o, parent or root)
        far.append(o)
        if static:
            plate.append(o)
        return o

    # ------------------------------------------------------------ the panel
    keep(_box("fmm_frame", (0, 0, 0.003), (0.500, 0.300, 0.009), brass,
              bevel=0.004))
    keep(_box("fmm_plate", (0, 0, 0.008), (0.478, 0.280, 0.013), panel_m,
              bevel=0.004))
    # the lower deck is a recessed tray: the DATA channel, physically separate
    keep(_box("fmm_data_tray", (0, -0.104, 0.0157), (0.462, 0.074, 0.0025),
              well_m, bevel=0.0))
    # the control / data divider: everything below this line rides its own rail
    keep(_box("fmm_divider", (0, -0.062, 0.016), (0.470, 0.005, 0.005), brass,
              bevel=0.0012))
    for i, x in enumerate((-0.232, 0.232)):
        keep(_box(f"fmm_screw_l_{i}", (x, 0.132, 0.016), (0.010, 0.010, 0.006),
                  brass, bevel=0.001))
        keep(_box(f"fmm_screw_u_{i}", (x, -0.132, 0.016), (0.010, 0.010, 0.006),
                  brass, bevel=0.001))

    # ------------------------------------------- manifest card (static deco)
    keep(_box("fmm_card_well", (-0.105, 0.102, 0.015), (0.082, 0.058, 0.006),
              hull_d, bevel=0.002))
    keep(_box("fmm_card", (-0.105, 0.102, 0.020), (0.070, 0.046, 0.004),
              card, bevel=0.001))
    for i in range(4):
        keep(_box(f"fmm_card_row_{i}", (-0.105, 0.118 - 0.010 * i, 0.023),
                  (0.052, 0.0035, 0.002), ink, bevel=0.0))

    # -------------------------------------------------- CARGO LIFT (frames)
    lx, ly = -0.170, 0.070
    keep(_box("fmm_lift_slot", (lx, 0.008, 0.017), (0.038, 0.156, 0.008),
              well_m, bevel=0.002))
    for i in range(LIFT_FRAMES):
        keep(_box(f"fmm_lift_tooth_{i}", (lx + 0.031, 0.052 - 0.0220 * i,
                                          0.019),
                  (0.020, 0.005, 0.005), brass, bevel=0.001))
    keep(_cyl("fmm_lift_boss", (lx, ly, 0.024), 0.020, 0.044, brass,
              verts=24, rot=(0, math.pi / 2, 0)))

    lift_piv = _empty("fmm_lift_pivot", (lx, ly, 0.024))
    _adopt(lift_piv, root)
    shaft = _cyl("fmm_lift_shaft", (0, 0, 0.062), 0.0085, 0.102, hull_d,
                 verts=18)
    collar = _cyl("fmm_lift_collar", (0, 0, 0.096), 0.013, 0.010, brass,
                  verts=20)
    knob = _sphere("fmm_lift_knob", (0, 0, 0.122), 0.020, brass,
                   scale=(1, 1, 0.92))
    lift_objs = [shaft, collar, knob]
    for o in lift_objs:
        _adopt(o, lift_piv)
        far.append(o)

    # ------------------------------------------------------- HOLD (rotate)
    gx, gy = 0.000, 0.062
    g_bezel = keep(_cyl("fmm_gauge_bezel", (gx, gy, 0.017), 0.076, 0.020,
                        brass, verts=48))
    g_face = keep(_cyl("fmm_gauge_face", (gx, gy, 0.028), 0.064, 0.006, ivory,
                       verts=48))
    dial = [g_bezel, g_face]
    for i in range(11):
        th = math.radians(GAUGE_RANGE[0] +
                          (GAUGE_RANGE[1] - GAUGE_RANGE[0]) * i / 10)
        major = i % 5 == 0
        r_t = 0.050
        keep(_box(f"fmm_gauge_tick_{i}",
                  (gx + math.sin(th) * r_t, gy + math.cos(th) * r_t, 0.032),
                  (0.005 if major else 0.0035,
                   0.019 if major else 0.011, 0.003),
                  ink, rot=(0, 0, -th), bevel=0.0))
    # red "hold full" arc segment near the top of the sweep
    for i in range(4):
        th = math.radians(88 + 11 * i)
        keep(_box(f"fmm_gauge_red_{i}",
                  (gx + math.sin(th) * 0.059, gy + math.cos(th) * 0.059, 0.032),
                  (0.004, 0.009, 0.003), needle_m, rot=(0, 0, -th), bevel=0.0))
    keep(_box("fmm_gauge_plate", (gx, -0.032, 0.016), (0.074, 0.013, 0.005),
              brass, bevel=0.0015))

    needle = _box("fmm_gauge_needle", (gx, gy + 0.024, 0.033),
                  (0.005, 0.050, 0.0035), needle_m, bevel=0.0)
    tail = _box("fmm_gauge_tail", (gx, gy - 0.012, 0.033),
                (0.007, 0.022, 0.0035), needle_m, bevel=0.0)
    hub = _cyl("fmm_gauge_hub", (gx, gy, 0.037), 0.011, 0.009, brass, verts=20)
    needle_objs = [needle, tail, hub]
    for o in needle_objs:
        _adopt(o, root)
        far.append(o)

    # --------------------------------------------------- CHANNEL (states)
    sx, sy = 0.170, 0.030
    keep(_cyl("fmm_sel_base", (sx, sy, 0.017), 0.033, 0.020, brass, verts=32))
    keep(_cyl("fmm_sel_face", (sx, sy, 0.028), 0.027, 0.006, hull_d, verts=32))
    for i, a in enumerate((-SEL_ANGLE, SEL_ANGLE)):
        th = math.radians(a)
        keep(_box(f"fmm_sel_stop_{i}",
                  (sx + math.sin(th) * 0.030, sy + math.cos(th) * 0.030, 0.030),
                  (0.004, 0.010, 0.003), brass, rot=(0, 0, -th), bevel=0.0))
    lamp_domes = []
    for i, px in enumerate((0.132, 0.208)):
        keep(_cyl(f"fmm_lamp_ring_{i}", (px, 0.112, 0.017), 0.021, 0.020,
                  brass, verts=28))
        d = _sphere(f"fmm_lamp_dome_{i}", (px, 0.112, 0.026), 0.016, lamp_off,
                    scale=(1, 1, 0.62), seg=20, ring=10)
        _adopt(d, root)
        far.append(d)
        lamp_domes.append(d)

    sel_piv = _empty("fmm_sel_pivot", (sx, sy, 0.031))
    _adopt(sel_piv, root)
    ptr = _box("fmm_sel_pointer", (0, 0.017, 0.004), (0.008, 0.038, 0.005),
               brass, bevel=0.001)
    grip = _cyl("fmm_sel_grip", (0, 0, 0.008), 0.013, 0.015, brass, verts=12,
                smooth=False)
    sel_objs = [ptr, grip]
    for o in sel_objs:
        _adopt(o, sel_piv)
        far.append(o)

    lift_piv.rotation_euler = (math.radians(LIFT_REST), 0, 0)
    sel_piv.rotation_euler = (0, 0, math.radians(SEL_ANGLE))
    lamp_domes[0].data.materials[0] = lamp_cy

    # ------------------------------------------------- DATA RAIL (frames)
    keep(_box("fmm_rail_bed", (0.055, -0.102, 0.020), (0.352, 0.030, 0.007),
              hull_d, bevel=0.002))
    keep(_cyl("fmm_rail_tube", (0.055, -0.102, 0.028), 0.005, 0.340, brass,
              verts=16, rot=(0, math.pi / 2, 0)))
    for i, px in enumerate((-0.119, 0.229)):
        keep(_box(f"fmm_rail_post_{i}", (px, -0.102, 0.031), (0.011, 0.032,
                                                              0.030),
                  brass, bevel=0.002))
    for i in range(8):
        keep(_box(f"fmm_rail_tick_{i}",
                  (-0.085 + 0.040 * i, -0.128, 0.0205),
                  (0.004, 0.011, 0.003), brass, bevel=0.0))

    skid_piv = _empty("fmm_skid_pivot", (0.0, -0.102, 0.028))
    _adopt(skid_piv, root)
    body = _box("fmm_skid_body", (0, 0, 0.019), (0.046, 0.034, 0.032),
                crate_m, bevel=0.003)
    skid_objs = [body]
    for i, dx in enumerate((-0.015, 0.015)):
        skid_objs.append(_box(f"fmm_skid_strap_{i}", (dx, 0, 0.019),
                              (0.006, 0.037, 0.035), brass, bevel=0.001))
    for i, dx in enumerate((-0.015, 0.015)):
        skid_objs.append(_cyl(f"fmm_skid_truck_{i}", (dx, 0, 0.001), 0.0065,
                              0.012, hull_d, verts=12,
                              rot=(0, math.pi / 2, 0)))
    for o in skid_objs:
        _adopt(o, skid_piv)
        far.append(o)

    # ------------------------------------------------------------- placement
    loc, eul = slots.place(P, CODE, lift=LIFT)
    root.location = loc
    root.rotation_euler = eul
    bpy.context.view_layer.update()

    return {
        "far": [o for o in far if o.type == 'MESH'],
        "plate": plate,
        "root": root,
        "controls": {
            "lift": {"objs": lift_objs, "pivot": lift_piv, "kind": "frames",
                     "label": "CARGO LIFT", "axis": "x", "frames": LIFT_FRAMES,
                     "range": [LIFT_MIN, LIFT_MAX]},
            "hold": {"objs": needle_objs, "pivot": None, "kind": "rotate",
                     "label": "HOLD", "dial": dial,
                     "anchor": root.matrix_world @ Vector((gx, gy, 0.037)),
                     "range": list(GAUGE_RANGE)},
            "channel": {"objs": sel_objs + lamp_domes, "pivot": sel_piv,
                        "kind": "states", "label": "CHANNEL",
                        "states": ["pasv", "port"], "domes": lamp_domes,
                        "mats": {"off": lamp_off, "pasv": lamp_cy,
                                 "port": lamp_amb},
                        "angle": SEL_ANGLE},
            "rail": {"objs": skid_objs, "pivot": skid_piv, "kind": "frames",
                     "label": "DATA RAIL", "axis": "tx", "frames": RAIL_FRAMES,
                     "range": [RAIL_X0, RAIL_X1]},
        },
    }


# ------------------------------------------------------ standalone renderer
def mesh_objects(scene):
    return [o for o in scene.objects if o.type == 'MESH']


def render_to(scene, path, visible):
    saved = {}
    vis = set(o.name for o in visible)
    for o in mesh_objects(scene):
        saved[o.name] = o.hide_render
        o.hide_render = o.name not in vis
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
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
    cam.name = "fmm_closecam"
    cam.data.lens = 42.0
    _adopt(cam, root)
    # straight down the panel normal, tilted just enough to give the lever and
    # the crate some profile. Explicit euler == guaranteed zero roll.
    cam.location = (0.0, -0.165, 0.790)
    cam.rotation_euler = (math.radians(11.8), 0.0, 0.0)

    # EXPOSURE FIX.  The first pass read mid-grey / low-contrast: these local
    # lights were too weak to model the panel, so the shell's broad fill did all
    # the work and AgX's default look lifted the near-black hull to mid-grey.
    # Energies are doubled and a small grazing KICKER (the last entry, size
    # 0.10) is added purely to put a specular streak down the brass rail and
    # bezels -- brass is metal, so it only reads if something specular is aimed
    # at it.  Paired with close_grade() below, which dims the shell fill and
    # puts a punchier look on the close camera ONLY.
    lights = []
    for i, (loc, aim, energy, size, col) in enumerate([
        ((-0.34, 0.30, 0.34), (-0.06, 0.02, 0.02), 5.2, 0.24, (1.0, 0.89, 0.74)),
        ((0.44, -0.24, 0.40), (0.08, -0.03, 0.02), 2.2, 0.32, (0.70, 0.80, 1.0)),
        ((0.04, 0.42, 0.14), (0.0, 0.03, 0.03), 2.6, 0.20, (1.0, 0.84, 0.62)),
        ((-0.02, -0.44, 0.24), (0.0, -0.08, 0.03), 1.8, 0.28, (1.0, 0.88, 0.72)),
        ((-0.10, 0.34, 0.10), (0.02, -0.02, 0.02), 1.6, 0.10, (1.0, 0.93, 0.80)),
    ]):
        bpy.ops.object.light_add(type='AREA', location=(0, 0, 0))
        L = bpy.context.object
        L.name = f"fmm_light_{i}"
        L.data.energy, L.data.size = energy, size
        L.data.color = col
        _adopt(L, root)
        L.location = loc
        _aim(L, Vector(aim))
        lights.append(L)
    return cam, lights


# The shell's own fill is tuned for the WIDE shot, where this panel is 221 px
# across.  At close-up range it floods a panel whose hull material is nearly
# black, which is what made the first close-up read mid-grey.  Dim it for the
# close camera and let close_rig()'s local lights model the panel instead.
CLOSE_SHELL_FILL = 0.45     # multiplier on every shell light
CLOSE_LOOK = "AgX - Punchy"
CLOSE_EXPOSURE = -0.20


def close_grade(scene):
    """Exposure/lighting for the CLOSE-UP RENDERS ONLY.

    Call it AFTER the far renders -- those must keep the shell's own grade so
    the prop matches the combined main plate.  Deliberately NOT a global grade:
    the per-module colour-temperature differences are correct (a ceiling panel
    should look differently lit from a dash panel); this only fixes FMM's
    genuine underexposure.
    """
    for o in scene.objects:
        if o.type == 'LIGHT' and not o.name.startswith("fmm_"):
            o.data.energy *= CLOSE_SHELL_FILL
    try:
        scene.view_settings.look = CLOSE_LOOK
    except TypeError:                       # look not available in this build
        pass
    scene.view_settings.exposure = CLOSE_EXPOSURE


def glow_render(scene, path, objs):
    """Flat white emissive silhouette for the hover glow."""
    g = _mat("fmm_glow", (1, 1, 1, 1), 0.0, 0.5,
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
    scene.view_settings.view_transform = vt
    scene.view_settings.look = look
    for o in objs:
        for i, m in enumerate(saved[o.name]):
            o.data.materials[i] = m


HTML = """<!doctype html>
<meta charset="utf-8">
<title>FMM - Cargo Bay / Manifest Vault</title>
<style>
 body{margin:0;background:#0a0c10;color:#cbb48a;
      font:13px/1.5 ui-monospace,Menlo,monospace}
 header{padding:14px 18px;border-bottom:1px solid #2a2318}
 h1{margin:0;font-size:15px;letter-spacing:.18em;color:#e2c489}
 header p{margin:6px 0 0;color:#7d7360;max-width:70ch}
 #stage{margin:14px 18px;overflow:hidden}
 #wrap{position:relative;width:1280px;height:720px;transform-origin:top left}
 #wrap img{position:absolute;left:0;top:0;width:1280px;height:720px;
           image-rendering:auto}
 .hot{position:absolute;border:1px solid rgba(226,196,137,.0);cursor:pointer}
 .hot:hover{border-color:rgba(226,196,137,.55);
            background:rgba(226,196,137,.06)}
 .hot span{position:absolute;left:0;top:-17px;font-size:10px;
           letter-spacing:.14em;color:#e2c489;opacity:0;white-space:nowrap}
 .hot:hover span{opacity:1}
 #hud{margin:0 18px 24px;padding:10px 14px;border:1px solid #2a2318;
      display:inline-block;white-space:pre}
</style>
<header>
 <h1>FMM &middot; CARGO BAY / MANIFEST VAULT</h1>
 <p>Upper deck is the <b>control channel</b> (lift lever, hold gauge,
    PASV/PORT selector). Lower deck is the <b>data channel</b> &mdash; the crate
    rides its own rail, exactly as FMM moves payload on a separate connection.
    Drag the lever or the crate, drag on the gauge, click the selector.</p>
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
      bits.push(c.label + ': step ' + (state[id]+1) + '/' + c.frames.length);
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
      let f = horiz ? (ev.clientX-r.left)/r.width : 1-(ev.clientY-r.top)/r.height;
      f = Math.max(0, Math.min(1, f));
      state[id] = Math.round(f*(c.frames.length-1)); draw();
    };
    h.onmousedown = e => { set(e); h.onmousemove = set; };
    h.onmouseup = h.onmouseleave = () => { h.onmousemove = null; };
  } else {
    const set = ev => {
      const a = Math.atan2(ev.clientX - (wrap.getBoundingClientRect().left +
                  c.pivot.x * scaleNow()),
                (wrap.getBoundingClientRect().top + c.pivot.y * scaleNow()) -
                  ev.clientY) * 180/Math.PI;
      state[id] = Math.max(c.range[0], Math.min(c.range[1], a)); draw();
    };
    h.onmousedown = e => { set(e); h.onmousemove = set; };
    h.onmouseup = h.onmouseleave = () => { h.onmousemove = null; };
  }
}

let SC = 1;
function scaleNow(){ return SC; }
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

    # ------------------------------------------------------------- far shot
    render_to(scene, os.path.join(OUT, "far_prop.png"), far_objs)
    far_hot = bbox_rect(scene, far_cam, far_objs, pad=8)
    glow_render(scene, os.path.join(OUT, "far_glow.png"), far_objs)
    # a shell-only plate, purely so compose.py can verify placement
    render_to(scene, os.path.join(OUT, "_shell_plate.png"), shell_meshes)

    # ----------------------------------------------------------- close shot
    cam, _lights = close_rig(root)
    scene.camera = cam
    close_grade(scene)                  # close-up exposure only; see above
    bpy.context.view_layer.update()

    static = shell_meshes + res["plate"]
    render_to(scene, os.path.join(OUT, "close_plate.png"), static)

    controls = {}

    # --- CARGO LIFT: a rendered frame per detent -------------------------
    piv = ctl["lift"]["pivot"]
    frames, rects = [], []
    for i in range(LIFT_FRAMES):
        t = i / (LIFT_FRAMES - 1)
        piv.rotation_euler = (math.radians(LIFT_MAX +
                                           (LIFT_MIN - LIFT_MAX) * t), 0, 0)
        bpy.context.view_layer.update()
        fn = f"close_lift_{i}.png"
        render_to(scene, os.path.join(OUT, fn), ctl["lift"]["objs"])
        frames.append(fn)
        rects.append(bbox_rect(scene, cam, ctl["lift"]["objs"]))
    piv.rotation_euler = (math.radians(LIFT_MIN), 0, 0)
    bpy.context.view_layer.update()
    controls["lift"] = {"kind": "frames", "label": "CARGO LIFT",
                        "frames": frames, "hotspot": union(rects)}

    # --- DATA RAIL: the crate translating along its own rail -------------
    sp = ctl["rail"]["pivot"]
    frames, rects = [], []
    for i in range(RAIL_FRAMES):
        t = i / (RAIL_FRAMES - 1)
        sp.location = (RAIL_X0 + (RAIL_X1 - RAIL_X0) * t, -0.102, 0.028)
        bpy.context.view_layer.update()
        fn = f"close_rail_{i}.png"
        render_to(scene, os.path.join(OUT, fn), ctl["rail"]["objs"])
        frames.append(fn)
        rects.append(bbox_rect(scene, cam, ctl["rail"]["objs"]))
    sp.location = (RAIL_X0, -0.102, 0.028)
    bpy.context.view_layer.update()
    controls["rail"] = {"kind": "frames", "label": "DATA RAIL",
                        "frames": frames, "hotspot": union(rects)}

    # --- HOLD: needle rendered once, spun in CSS -------------------------
    render_to(scene, os.path.join(OUT, "close_hold.png"), ctl["hold"]["objs"])
    px, py = project(scene, cam, ctl["hold"]["anchor"])
    controls["hold"] = {"kind": "rotate", "label": "HOLD",
                        "image": "close_hold.png",
                        "pivot": {"x": round(px, 1), "y": round(py, 1)},
                        "range": ctl["hold"]["range"],
                        "hotspot": bbox_rect(scene, cam, ctl["hold"]["dial"])}

    # --- CHANNEL: PASV / PORT, pointer + lamp material swap --------------
    c = ctl["channel"]
    states, rects = {}, []
    for name, sign, lit in (("pasv", -1, 0), ("port", 1, 1)):
        c["pivot"].rotation_euler = (0, 0, math.radians(-sign * c["angle"]))
        for i, d in enumerate(c["domes"]):
            d.data.materials[0] = c["mats"][name] if i == lit else c["mats"]["off"]
        bpy.context.view_layer.update()
        fn = f"close_channel_{name}.png"
        render_to(scene, os.path.join(OUT, fn), c["objs"])
        states[name] = fn
        rects.append(bbox_rect(scene, cam, c["objs"]))
    c["pivot"].rotation_euler = (0, 0, math.radians(c["angle"]))
    for i, d in enumerate(c["domes"]):
        d.data.materials[0] = c["mats"]["pasv"] if i == 0 else c["mats"]["off"]
    controls["channel"] = {"kind": "states", "label": "CHANNEL",
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

    print("FMM far hotspot", json.dumps(far_hot))
    for k, v in controls.items():
        print("FMM close", k, v["kind"], json.dumps(v["hotspot"]))
    print("FMM OK ->", OUT)


if __name__ == "__main__":
    main()
