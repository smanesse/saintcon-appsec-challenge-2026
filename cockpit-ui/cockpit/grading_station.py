"""
Grading station — a signless refit-port fitting seated on the dashboard.

The shell camera and lights come from cockpit/shell.py. The receiving dash
meshes are rendered with the station so the contact is in the pixels. A
second pass writes a white-emissive silhouette of the fitting for the page
glow. The nine instrument plates are not rebuilt. The patch is composited
onto a copy of cockpit/combined/main_plate.png. t is on the dash face, in
[0, 1].

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python cockpit/grading_station.py
"""
import array
import json
import math
import os
import sys

import bpy
from mathutils import Euler, Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PIPE = os.path.join(ROOT, "live3d", "pipeline")
for p in (HERE, PIPE):
    if p not in sys.path:
        sys.path.insert(0, p)

import shell                                          # noqa: E402
import slots                                          # noqa: E402
import refit_port as RP                               # noqa: E402

OUT_DIR = os.path.join(HERE, "grading-station")
if OUT_DIR not in sys.path:
    sys.path.insert(0, OUT_DIR)
import align_check                                     # noqa: E402
import select_plate                                    # noqa: E402
SPRITE = os.path.join(OUT_DIR, "station_sprite.png")
GLOW = os.path.join(OUT_DIR, "station_glow.png")
PLATE_SRC = os.path.join(HERE, "combined", "main_plate.png")
PLATE_OUT = os.path.join(HERE, "combined", "grading_station_plate.png")
STATION_JSON = os.path.join(OUT_DIR, "station.json")

# Slight alterations of live3d/pipeline/refit_port.py GEO. The iris stays the
# closed six-pointed star; these change the fitting enough to read as its own
# station and not a copy of a module port.
ALTERED_GEO = {
    "leaf_gap_deg": 6.2,    # was 3.4 — wider star slots, readable at wide-shot size
    "jewel_r": 0.070,       # was 0.048 — larger grade lamp
    "jewel_h": 0.042,       # was 0.030
    "z_face": 0.176,        # was 0.158 — taller bezel, still above the leaves
    "srail_half": 0.50,     # was 0.650 — rail stays inside the hex, no mast claim
    "jewel_v": -0.40,       # on the bottom flat; spin 0 has no lower point
}
SPIN_DEG = 0.0              # flat-topped, so the base edges follow the dash
# Courier New Bold, measured in standings_plate.py. FONT.size is not an em.
CAP_OVER_SIZE = 0.306623
ADV_OVER_SIZE = 0.310667
PLAQUE_WORD = "GRADING"
# Word width as a fraction of the port's across-flats width. The plaque stays
# inside the housing; it does not outgrow the port.
WORD_OF_W = 0.82
FONT_PATHS = (
    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
    os.path.join(ROOT, "fonts", "CourierPrime-Bold.ttf"),
)

# Far-view keep-outs. Module stations and their telltale masts stay clear.
MASTS = {
    "MQB": (144, 174, 22, 78),
    "OTA": (206, 204, 78, 22),
    "FMM": (199, 329, 22, 78),
    "LOG": (298, 489, 78, 22),
    "PKT": (694, 265, 22, 78),
    "MTA": (854, 494, 78, 22),
    "IPM": (823, 214, 78, 22),
    "DNSM": (1046, 74, 78, 22),
    "KVS": (999, 275, 22, 78),
}


def keepouts():
    man = json.load(open(os.path.join(HERE, "combined", "manifest.json")))
    rects = []
    for code, mod in man["modules"].items():
        h = mod["far"]["hotspot"]
        rects.append((code, h["x"], h["y"], h["w"], h["h"]))
    for code, e in MASTS.items():
        rects.append((code + "-mast", e[0], e[1], e[2], e[3]))
    sb = os.path.join(ROOT, "live3d", "assets", "_STANDINGS", "standings.json")
    if os.path.exists(sb):
        h = json.load(open(sb)).get("hotspot")
        if h:
            rects.append(("standings", h["x"], h["y"], h["w"], h["h"]))
    return rects


def overlaps(a, b):
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def hits(box, rects, pad=0):
    x, y, w, h = box
    q = (x - pad, y - pad, w + 2 * pad, h + 2 * pad)
    return [name for name, *r in rects if overlaps(q, r)]


def fascia_span(P):
    """Vertical extent of dash_fascia. t = 0 is the kick, t = 1 is under the lip."""
    z_lo = 0.14
    z_hi = P["dash_near_z"] - 0.025
    return z_lo, z_hi


def fascia_z(P, t):
    z_lo, z_hi = fascia_span(P)
    return z_lo + (z_hi - z_lo) * t


def fascia_t(P, z):
    z_lo, z_hi = fascia_span(P)
    return (z - z_lo) / (z_hi - z_lo)


def fascia_frame(P, angle_deg, z):
    """slots.fascia() axes, as a PortFrame. Local +Z points at the pilot."""
    loc, eul = slots.fascia(P, angle_deg, z, 0.0)
    M = Euler(eul, 'XYZ').to_matrix()
    origin = [float(c) for c in loc]
    u = [float(c) for c in (M @ Vector((1.0, 0.0, 0.0)))]
    v = [float(c) for c in (M @ Vector((0.0, 1.0, 0.0)))]
    n = [float(c) for c in (M @ Vector((0.0, 0.0, 1.0)))]
    return RP.PortFrame(origin, u, v, n), [float(x) for x in eul]


def project(scene, cam, co):
    p = world_to_camera_view(scene, cam, Vector(co))
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    return (p.x * rx, (1.0 - p.y) * ry, p.z)


def hex_box(scene, cam, frame, W, spin):
    R = 0.57735 * W
    a0 = math.radians(spin)
    xs, ys = [], []
    samples = []
    for k in range(6):
        a = a0 + k * math.pi / 3.0
        samples.append((R * math.cos(a), R * math.sin(a), 0.0))
        samples.append((R * math.cos(a), R * math.sin(a), ALTERED_GEO["z_face"] * W))
    samples.append((0.0, -0.52 * W, 0.20 * W))
    samples.append((0.40 * W, -0.42 * W, 0.18 * W))
    for x, y, z in samples:
        px, py, depth = project(scene, cam, frame.to_world(x, y, z))
        if depth <= 0:
            return None
        xs.append(px)
        ys.append(py)
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def separation(box, rects):
    """Pixel gap to the nearest keep-out. Negative when the boxes overlap."""
    x, y, w, h = box
    best = 1e9
    for _name, a, b, c, d in rects:
        dx = max(a - (x + w), x - (a + c), 0.0)
        dy = max(b - (y + h), y - (b + d), 0.0)
        if dx == 0.0 and dy == 0.0:
            return -1.0
        sep = math.hypot(dx, dy) if dx and dy else (dx + dy)
        if sep < best:
            best = sep
    return best


def choose(scene, cam, P, rects):
    """Rank seats on the lower-right fascia. Rows are (gap, width, angle, z, W, box)."""
    ranked = []
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    stats = {"behind": 0, "frame": 0, "off": 0, "hit": 0, "ok": 0}

    def consider(angle, z, W):
        t = fascia_t(P, z)
        if t < 0.04 or t > 0.92:
            stats["off"] += 1
            return
        # The hex has to stay on the apron, not through the lip or the kick.
        if z - W * 0.50 < 0.16 or z + W * 0.50 > fascia_span(P)[1] - 0.02:
            stats["off"] += 1
            return
        frame, _eul = fascia_frame(P, angle, z)
        box = hex_box(scene, cam, frame, W, SPIN_DEG)
        if box is None:
            stats["behind"] += 1
            return
        x, y, w, h = box
        if x < 12 or y < 12 or x + w > rx - 12 or y + h > ry - 12:
            stats["frame"] += 1
            return
        if hits(box, rects, pad=1):
            stats["hit"] += 1
            return
        stats["ok"] += 1
        gap = separation(box, rects)
        ranked.append((gap, w, angle, z, W, box))

    # The bus board and the water panel stay. The fire bottle (F6) may move.
    occupied = []
    for name, ang, zc, w, h in (
            ("F5", 34.0, 0.45, 0.36, 0.46),
            ("F4", 24.5, 0.50, 0.28, 0.32)):
        box = fascia_screen_box(scene, cam, P, ang, zc, w, h, proud=0.04)
        if box:
            occupied.append((name, box[0], box[1], box[2], box[3]))
            print("KEEP", name, tuple(round(v, 1) for v in box))
    rects = list(rects) + occupied

    # Positive angle is screen-right. Lower z is the lower apron, under the lip.
    for angle in range(40, 52):
        for z100 in range(34, 50, 2):
            z = z100 / 100.0
            for W100 in (24, 26, 28, 30):
                consider(float(angle), z, W100 / 100.0)

    print("FASCIA FILTERS", stats, "res", rx, ry)
    probe, _ = fascia_frame(P, 43.0, 0.40)
    print("PROBE fascia +43 z 0.40", tuple(round(v, 1) for v in project(scene, cam, probe.o)))
    # Rightmost legal apron first, then the lower of those.
    ranked.sort(key=lambda row: (-row[2], row[3], -row[4]))
    return ranked


def amber_jewel():
    m = bpy.data.materials.get("rp_jewel")
    if m is None:
        return
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.55, 0.28, 0.06, 1.0)
    b.inputs["Emission Color"].default_value = (1.0, 0.62, 0.16, 1.0)
    b.inputs["Emission Strength"].default_value = 7.5


def mesh_bounds(scene, cam, objs):
    """Screen box of the actual vertices. An AABB overstates a rotated hex."""
    xs, ys = [], []
    for o in objs:
        data = getattr(o, "data", None)
        verts = getattr(data, "vertices", None)
        if not verts:
            continue
        mw = o.matrix_world
        for v in verts:
            px, py, depth = project(scene, cam, mw @ v.co)
            if depth <= 0:
                continue
            xs.append(px)
            ys.append(py)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def drop_objects(objs):
    for o in list(objs):
        if o and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)


def render_sprite(scene, objs, path):
    vis = {o.name for o in objs}
    saved = {}
    for o in scene.objects:
        if o.type != 'MESH':
            continue
        saved[o.name] = o.hide_render
        o.hide_render = o.name not in vis
    scene.render.filepath = path
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    bpy.ops.render.render(write_still=True)
    for o in scene.objects:
        if o.type == 'MESH' and o.name in saved:
            o.hide_render = saved[o.name]


def alpha_over(base_path, sprite_path, out_path):
    base = bpy.data.images.load(base_path)
    over = bpy.data.images.load(sprite_path)
    bw, bh = int(base.size[0]), int(base.size[1])
    ow, oh = int(over.size[0]), int(over.size[1])
    if (bw, bh) != (ow, oh):
        raise SystemExit("sprite %sx%s does not match plate %sx%s" % (ow, oh, bw, bh))
    n = bw * bh
    bp = array.array('f', [0.0]) * (n * 4)
    op = array.array('f', [0.0]) * (n * 4)
    base.pixels.foreach_get(bp)
    over.pixels.foreach_get(op)
    # Blender stores rows bottom-up. CSS hotspot y is top-down.
    minx, miny, maxx, maxy = bw, bh, -1, -1
    for i in range(n):
        a = op[i * 4 + 3]
        if a <= 0.02:
            continue
        x = i % bw
        y = i // bw
        if x < minx:
            minx = x
        if x > maxx:
            maxx = x
        if y < miny:
            miny = y
        if y > maxy:
            maxy = y
        inv = 1.0 - a
        ba = bp[i * 4 + 3]
        for c in range(3):
            bp[i * 4 + c] = op[i * 4 + c] * a + bp[i * 4 + c] * ba * inv
        bp[i * 4 + 3] = a + ba * inv
    out = bpy.data.images.new("grading_station_plate", bw, bh, alpha=True)
    out.pixels.foreach_set(bp)
    out.filepath_raw = out_path
    out.file_format = 'PNG'
    out.save()
    if maxx < 0:
        raise SystemExit("station sprite has no opaque pixels")
    # miny/maxy are bottom-up. Top of the sprite is the larger blender y.
    css_y = bh - 1 - maxy
    return {
        "x": int(minx),
        "y": int(css_y),
        "w": int(maxx - minx + 1),
        "h": int(maxy - miny + 1),
    }


def principled(name, base, metal, rough, emission=None, strength=0.0):
    old = bpy.data.materials.get(name)
    if old is not None:
        bpy.data.materials.remove(old)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (base[0], base[1], base[2], 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emission is not None:
        b.inputs["Emission Color"].default_value = (
            emission[0], emission[1], emission[2], 1.0)
        b.inputs["Emission Strength"].default_value = strength
    return m


def basis_matrix(u, v, n):
    """Columns are the plaque axes. Local +X reads left to right on screen."""
    return Matrix((
        (u.x, v.x, n.x, 0.0),
        (u.y, v.y, n.y, 0.0),
        (u.z, v.z, n.z, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))



DASH_ONLY = os.path.join(OUT_DIR, "dash_only.png")
DASH_BOTH = os.path.join(OUT_DIR, "dash_and_station.png")
WIRE = os.path.join(ROOT, "evidence", "grading-station", "contact-wire.png")
CLOSEUP = os.path.join(ROOT, "evidence", "grading-station", "contact-center-front.png")
# The panel the station has to meet. Rendered with the fitting so the
# contact shadow is in the pixels, not painted on afterwards.
DASH_MESHES = ("dash_face", "dash_lip", "dash_fascia")
# Underside center, millimetres. Negative is into the dash, along its normal.
CENTER_TARGET_MM = -0.15


def load_font():
    for path in FONT_PATHS:
        if not os.path.exists(path):
            continue
        try:
            font = bpy.data.fonts.load(path, check_existing=True)
        except Exception:                                       # noqa: BLE001
            continue
        print("PLAQUE FONT", path)
        return font
    raise SystemExit("no monospace font for the GRADING plaque")


def frame_box(name, frame, x, y, z0, z1, hw, hh, mat):
    """A solid in the housing frame. Local Z is the housing normal."""
    u = Vector(frame.u)
    v = Vector(frame.v)
    n = Vector(frame.n)
    mid = (z0 + z1) * 0.5
    center = Vector(frame.to_world(x, y, mid))
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
    ob = bpy.context.object
    ob.name = name
    ob.data.name = name
    ob.matrix_world = (
        Matrix.Translation(center)
        @ basis_matrix(u, v, n)
        @ Matrix.Diagonal((2.0 * hw, 2.0 * hh, (z1 - z0), 1.0))
    )
    if ob.data.materials:
        ob.data.materials[0] = mat
    else:
        ob.data.materials.append(mat)
    return ob


def housing_word(name, body, size, mat, frame, x, y, z, y_scale, extrude=0.0011):
    """GRADING in the housing plane. Local +Z is the housing normal.

    y_scale lengthens the capitals along the housing so the rake does not
    squash them into an unreadable strip. The plaque normal stays the
    housing normal.
    """
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.resolution_u = 8
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.overflow = 'NONE'
    cu.extrude = extrude
    cu.font = load_font()
    if cu.text_boxes:
        cu.text_boxes[0].width = 0.0
        cu.text_boxes[0].height = 0.0
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    u = Vector(frame.u)
    v = Vector(frame.v)
    n = Vector(frame.n)
    loc = Vector(frame.to_world(x, y, z)) + n * extrude
    o.matrix_world = Matrix.Translation(loc) @ basis_matrix(u, v, n)
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target='MESH')
    word = bpy.data.objects.get(name) or o
    # Bake the stretch into the mesh. A scaled matrix_world gets decomposed
    # by the view layer and does not stay a pure housing-normal plaque.
    for vert in word.data.vertices:
        vert.co.y *= y_scale
    word.data.update()
    return word


def vec_angle_deg(a, b):
    av = Vector(a).normalized()
    bv = Vector(b).normalized()
    c = max(-1.0, min(1.0, av.dot(bv)))
    return math.degrees(math.acos(c))


def cap_screen_px(scene, cam, obj):
    """On-screen capital height, measured along the letter up-axis."""
    front = [vert for vert in obj.data.vertices if vert.co.z > 0.0002]
    if len(front) < 8:
        front = list(obj.data.vertices)
    if not front:
        return None, None
    ys = [vert.co.y for vert in front]
    y0, y1 = min(ys), max(ys)
    xs = [vert.co.x for vert in front]

    def mid_at(y_target):
        band = [vert for vert in front if abs(vert.co.y - y_target) <= 0.002]
        use = band or front
        mx = sum(vert.co.x for vert in use) / len(use)
        my = sum(vert.co.y for vert in use) / len(use)
        mz = sum(vert.co.z for vert in use) / len(use)
        return obj.matrix_world @ Vector((mx, my, mz))

    p0 = project(scene, cam, mid_at(y0))
    p1 = project(scene, cam, mid_at(y1))
    cap = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    # Screen box of the front sheet, for the crop and the hotspot notes.
    sx, sy = [], []
    mw = obj.matrix_world
    for vert in front:
        px, py, depth = project(scene, cam, mw @ vert.co)
        if depth <= 0:
            continue
        sx.append(px)
        sy.append(py)
    if not sx:
        return cap, None
    box = (min(sx), min(sy), max(sx) - min(sx), max(sy) - min(sy))
    word_w = max(xs) - min(xs)
    return cap, box, word_w


def add_housing(frame, W):
    """A dark band and brass GRADING, flush on the housing face.

    The dash is seen at about 56 degrees off its normal, which shortens
    anything lying up the rake. The capitals are cut longer along that
    axis so they still read from the pilot seat, and they stay inside the hex.
    """
    n_ch = len(PLAQUE_WORD)
    word_w = WORD_OF_W * W
    font_size = word_w / (n_ch * ADV_OVER_SIZE)
    cap_m = CAP_OVER_SIZE * font_size
    # Full-width band of a point-up hex is 0.289 W above and below centre.
    # The band half-height is about 0.72 of the stretched capital, and it
    # has to stay inside that band or the letters leave the port.
    band_limit = 0.26 * W
    y_scale = min(2.8, band_limit / (0.72 * cap_m))
    z_face = ALTERED_GEO["z_face"] * W
    band = principled(
        "gs_band", (0.025, 0.027, 0.032), 0.35, 0.48)
    brass = principled(
        "gs_letters", (0.86, 0.66, 0.26), 1.0, 0.30,
        (0.70, 0.48, 0.14), 0.8)
    rim = principled(
        "gs_band_rim", (0.42, 0.32, 0.13), 0.85, 0.40)
    word = housing_word(
        "gs_word", PLAQUE_WORD, font_size, brass, frame,
        0.0, 0.0, z_face + 0.0026, y_scale)
    xs = [vert.co.x for vert in word.data.vertices]
    ys = [vert.co.y for vert in word.data.vertices]
    y_span = max(ys) - min(ys)
    x_span = max(xs) - min(xs)
    pad_x = 0.016 * W
    pad_y = 0.22 * y_span
    hw = x_span * 0.5 + pad_x
    hh = y_span * 0.5 + pad_y
    objs = [word]
    objs.append(frame_box(
        "gs_band_rim", frame, 0.0, 0.0,
        z_face + 0.0004, z_face + 0.0018,
        hw + 0.006 * W, hh + 0.006 * W, rim))
    objs.append(frame_box(
        "gs_band", frame, 0.0, 0.0,
        z_face + 0.0016, z_face + 0.0030,
        hw, hh, band))
    return {"objects": objs, "word": word, "font_size_m": font_size,
            "cap_m": cap_m * y_scale, "y_scale": y_scale,
            "hw": hw, "hh": hh}


def mesh_signed_mm(ob, point, n_hint):
    """Millimetres from a point to dash_face. Positive is the pilot side."""
    ok, loc, normal, _idx = ob.closest_point_on_mesh(Vector(point))
    if not ok:
        return None
    n = Vector(normal)
    if n.dot(Vector(n_hint)) < 0.0:
        n = -n
    return (Vector(point) - Vector(loc)).dot(n) * 1000.0


def underside_samples(frame_ob, frame):
    """Outer bottom ring of the port, as (u, v) in the dash frame, and its height."""
    n = Vector(frame.n)
    u = Vector(frame.u)
    v = Vector(frame.v)
    o = Vector(frame.o)
    found = []
    mw = frame_ob.matrix_world
    for vert in frame_ob.data.vertices:
        p = mw @ vert.co
        rel = p - o
        found.append((rel.dot(n), rel.dot(u), rel.dot(v)))
    if not found:
        return [], None
    hmin = min(row[0] for row in found)
    ring = [(uu, vv) for h, uu, vv in found if h <= hmin + 0.0004]
    ring.sort(key=lambda row: -(row[0] * row[0] + row[1] * row[1]))
    # Six outer corners, dropping the inner bore which shares the same height.
    return ring[:6], hmin


def solve_center_height(frame, dash_ob, h_now):
    """Underside-plane height whose center is just inside dash_fascia.

    Positive height is toward the pilot from the tangent origin. The target
    signed distance is slightly negative, so the center is seated or deeper
    and the edges are free to enter the curve.
    """
    target = CENTER_TARGET_MM

    def signed(h):
        return mesh_signed_mm(dash_ob, frame.to_world(0.0, 0.0, h), frame.n)

    lo = h_now - 0.025
    hi = h_now + 0.005
    s_hi = signed(hi)
    if s_hi is None:
        return None, None
    for _ in range(8):
        if s_hi >= target:
            break
        hi += 0.008
        s_hi = signed(hi)
        if s_hi is None:
            return None, None
    else:
        return None, None
    s_lo = signed(lo)
    if s_lo is None:
        return None, None
    for _ in range(8):
        if s_lo <= target:
            break
        lo -= 0.008
        s_lo = signed(lo)
        if s_lo is None:
            return None, None
    else:
        return None, None
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        sm = signed(mid)
        if sm is None:
            return None, None
        if sm > target:
            hi = mid
        else:
            lo = mid
    h = 0.5 * (lo + hi)
    return h, signed(h)


def add_seat_plate(frame, hu, hv, z0, z1):
    """Rectangular foot. Local +Z is the housing normal. Bottom is z = 0.

    The object matrix is one rigid map from that local frame onto the dash.
    Nothing in the mesh is below the local bottom, so the foot cannot cross
    the panel when z0 is on the pilot side of the dash plane.
    """
    mat = principled("gs_seat", (0.10, 0.09, 0.07), 0.45, 0.48)
    thick = z1 - z0
    xy = ((-hu, -hv), (hu, -hv), (hu, hv), (-hu, hv))
    verts = [(x, y, 0.0) for x, y in xy] + [(x, y, thick) for x, y in xy]
    # Bottom winding is clockwise from above, so its normal points out of the
    # solid, toward the dash.
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    me = bpy.data.meshes.new("gs_seat")
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new("gs_seat", me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    origin = Vector(frame.o) + Vector(frame.n) * z0
    ob.matrix_world = Matrix.Translation(origin) @ basis_matrix(
        Vector(frame.u), Vector(frame.v), Vector(frame.n))
    return ob


def translate_objects(objs, delta):
    shift = Matrix.Translation(Vector(delta))
    for ob in objs:
        ob.matrix_world = shift @ ob.matrix_world


def render_visible(scene, names, path):
    vis = set(names)
    saved = {}
    for o in scene.objects:
        if o.type != 'MESH':
            continue
        saved[o.name] = o.hide_render
        o.hide_render = o.name not in vis
    scene.render.filepath = path
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    bpy.ops.render.render(write_still=True)
    for o in scene.objects:
        if o.type == 'MESH' and o.name in saved:
            o.hide_render = saved[o.name]
    print("WROTE", path, os.path.getsize(path))


def _load_rgba(path):
    im = bpy.data.images.load(path)
    bw, bh = int(im.size[0]), int(im.size[1])
    buf = array.array('f', [0.0]) * (bw * bh * 4)
    im.pixels.foreach_get(buf)
    bpy.data.images.remove(im)
    return bw, bh, buf


def fascia_screen_box(scene, cam, P, angle, z, width, height, proud=0.08):
    """Screen box of a fascia panel, CSS top-left, so a dressing piece can be lifted off."""
    frame, _eul = fascia_frame(P, angle, z)
    xs, ys = [], []
    for su in (-1.0, 1.0):
        for sv in (-1.0, 1.0):
            for sz in (0.0, proud):
                px, py, depth = project(scene, cam, frame.to_world(
                    su * width * 0.5, sv * height * 0.5, sz))
                if depth <= 0:
                    continue
                xs.append(px)
                ys.append(py)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def composite_contact(base_path, dash_path, both_path, station_path, out_path, clear_boxes=()):
    """Paste the station and its real contact shadow onto a copy of the plate.

    The shadow is the difference between the dash rendered alone and the dash
    rendered with the station. Pixels outside a window around the station stay
    on the shipped plate, so the instruments are not repainted.
    """
    bw, bh, base = _load_rgba(base_path)
    dw, dh, dash = _load_rgba(dash_path)
    ow, oh, both = _load_rgba(both_path)
    sw, sh, station = _load_rgba(station_path)
    if (bw, bh) != (dw, dh) or (bw, bh) != (ow, oh) or (bw, bh) != (sw, sh):
        raise SystemExit("render size does not match the plate")
    n = bw * bh
    minx, miny, maxx, maxy = bw, bh, -1, -1
    for i in range(n):
        if station[i * 4 + 3] <= 0.04:
            continue
        x = i % bw
        y = i // bw
        if x < minx:
            minx = x
        if x > maxx:
            maxx = x
        if y < miny:
            miny = y
        if y > maxy:
            maxy = y
    if maxx < 0:
        raise SystemExit("station render has no opaque pixels")
    # Lift cosmetic dressing off the apron before the port is pasted, so a
    # bottle or bracket does not show through the fitting.
    for box in clear_boxes:
        if box is None:
            continue
        cx, cy, cw, ch = box
        x0b = max(0, int(math.floor(cx)))
        x1b = min(bw - 1, int(math.ceil(cx + cw)))
        y_top = int(math.floor(cy))
        y_bot = int(math.ceil(cy + ch))
        for y_css in range(max(0, y_top), min(bh, y_bot + 1)):
            y = bh - 1 - y_css
            row = y * bw
            for x in range(x0b, x1b + 1):
                i = (row + x) * 4
                for c in range(4):
                    base[i + c] = dash[i + c]
    # Blender y is bottom-up. Expand the window so the contact shadow is kept.
    pad = 56
    x0 = max(0, minx - pad)
    x1 = min(bw - 1, maxx + pad)
    y0 = max(0, miny - pad)
    y1 = min(bh - 1, maxy + pad)
    patched = 0
    for y in range(y0, y1 + 1):
        row = y * bw
        for x in range(x0, x1 + 1):
            i = (row + x) * 4
            take = station[i + 3] > 0.20
            if not take:
                diff = max(abs(both[i + c] - dash[i + c]) for c in range(3))
                take = diff > 0.04 and both[i + 3] > 0.5
            if not take:
                continue
            for c in range(3):
                base[i + c] = both[i + c]
            base[i + 3] = 1.0
            patched += 1
    out = bpy.data.images.new("grading_station_plate", bw, bh, alpha=True)
    out.pixels.foreach_set(base)
    out.filepath_raw = out_path
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    css_y = bh - 1 - maxy
    hotspot = {
        "x": int(minx),
        "y": int(css_y),
        "w": int(maxx - minx + 1),
        "h": int(maxy - miny + 1),
    }
    print("PATCHED", patched, "HOTSPOT", hotspot)
    return hotspot


def off_frame(box, rx, ry, margin=4.0):
    if box is None:
        return True
    x, y, w, h = box
    return x < margin or y < margin or x + w > rx - margin or y + h > ry - margin


def seat_station(frame, port_objs, housing_objs):
    """Drop the visible port until its underside center meets the curved dash.

    Back and side edges may enter the panel. The witness plate is the seating
    plane, hidden from the render, and it does not hold the body up. The front
    face is checked after the drop.
    """
    dash = bpy.data.objects.get("dash_fascia")
    frame_ob = next(ob for ob in port_objs if ob.name.endswith("_frame"))
    samples, h_now = underside_samples(frame_ob, frame)
    if not samples or dash is None or h_now is None:
        return None
    height, center_mm = solve_center_height(frame, dash, h_now)
    if height is None or center_mm is None or center_mm > 1.0:
        return None
    plate = add_seat_plate(frame, 0.03, 0.03, height, height + 0.0004)
    plate.hide_render = True
    delta = Vector(frame.n) * (height - h_now)
    translate_objects(port_objs + housing_objs, delta)
    bpy.context.view_layer.update()
    return {"plate": plate, "hu": 0.03, "hv": 0.03, "height_m": height,
            "center_mm": center_mm, "delta_m": height - h_now}


def _sample_contact(frame, dash_ob):
    """Center of the underside, front-face distances, and edge distances.

    Front samples are the iris, jewel, tally, detent, and the upper frame
    and throat. The frame's bottom ring is the edge set and may be buried.
    """
    n = Vector(frame.n)
    o = Vector(frame.o)
    front_keys = ("_leaf_", "_jewel", "_tally", "_detent")
    front = []
    edge = []
    h_under = None
    frame_ob = bpy.data.objects.get("gs_frame")
    if frame_ob is not None:
        mw = frame_ob.matrix_world
        heights = [((mw @ vert.co) - o).dot(n) for vert in frame_ob.data.vertices]
        if heights:
            h_under = min(heights)
    center = None
    if h_under is not None:
        center = tuple(o + n * h_under)
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ob.name.startswith("gs"):
            continue
        if ob.name == "gs_seat" or ob.hide_render:
            continue
        mw = ob.matrix_world
        upper = ob.name in ("gs_frame", "gs_throat")
        is_front = any(key in ob.name for key in front_keys)
        for vert in ob.data.vertices:
            p = mw @ vert.co
            h = (p - o).dot(n)
            take_front = is_front or (upper and h_under is not None and h > h_under + 0.012)
            take_edge = ob.name == "gs_frame" and h_under is not None and h <= h_under + 0.0008
            if not take_front and not take_edge:
                continue
            signed = mesh_signed_mm(dash_ob, p, frame.n)
            if signed is None:
                continue
            if take_front:
                front.append(signed)
            if take_edge:
                edge.append(signed)
    return center, front, edge


def measure_alignment(frame, plate, P):
    """Seating plane from the witness plate, then center and front against the mesh."""
    bpy.context.view_layer.update()
    mw = plate.matrix_world.copy()
    ids = (0, 1, 2, 3)
    corners = []
    world = []
    for vid in ids:
        co = mw @ plate.data.vertices[vid].co
        xyz = (float(co.x), float(co.y), float(co.z))
        corners.append({"id": vid, "xyz": xyz})
        world.append(xyz)
    # Outward normal is the bottom polygon's own normal, in world space.
    bottom = next(poly for poly in plate.data.polygons if set(poly.vertices) == {0, 1, 2, 3})
    n_local = bottom.normal
    n_world = (mw.to_3x3() @ n_local).normalized()
    n_base = (float(n_world.x), float(n_world.y), float(n_world.z))
    edge = Vector(world[1]) - Vector(world[0])
    tangent = (float(edge.x), float(edge.y), float(edge.z))
    flat = [round(float(v), 6) for row in mw for v in row]
    dash = {
        "face_id": "dash_fascia",
        "origin": [float(c) for c in frame.o],
        "normal": [float(c) for c in frame.n],
        "u": [float(c) for c in frame.u],
        "v": [float(c) for c in frame.v],
        "seat_matrix": flat,
    }
    dash_ob = bpy.data.objects["dash_fascia"]
    center_xyz, front_mm, edge_mm = _sample_contact(frame, dash_ob)
    if center_xyz is None:
        center_xyz = world[0]
    center_mm = mesh_signed_mm(dash_ob, center_xyz, frame.n)
    center = {"xyz": center_xyz, "signed_mm": center_mm}
    return align_check.evaluate(dash, corners, n_base, tangent, P, center, front_mm, edge_mm)


def try_seat(scene, cam, P, rects, angle, z, W):
    t = fascia_t(P, z)
    if t < 0.02 or t > 0.98:
        print("  reject z %.3f is off the fascia (t %.3f)" % (z, t))
        return None
    frame, eul = fascia_frame(P, angle, z)
    built = RP.build(
        "gs", frame, W, root_scale=1.0, spin_deg=SPIN_DEG, seat=0.0,
        label=None, mark=None, sub_base=False, service_rail=False,
        ratchet=True, tally=True, jewel=True, geo=dict(ALTERED_GEO))
    amber_jewel()
    port_objs = list(built["objects"])
    seated = seat_station(frame, port_objs, [])
    if seated is None:
        print("  seat angle %.1f z %.2f W %.2f center did not meet the fascia" % (angle, z, W))
        drop_objects(port_objs)
        return None
    bpy.context.view_layer.update()
    box = mesh_bounds(scene, cam, port_objs)
    bad = hits(box, rects, pad=0) if box else ["no-bounds"]
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    off = off_frame(box, rx, ry, margin=8.0)
    report = measure_alignment(frame, seated["plate"], P)
    print("  seat angle %.1f z %.2f t %.2f W %.2f align %.3f deg residual %.3f mm "
          "raw %.3f center %.3f mm front %.2f mm edge %.2f mm off %s hits %s box %s"
          % (angle, z, t, W, report["angle_deg"], report["max_abs_mm"],
             report["raw_dot"],
             report["center"]["signed_mm"] if report["center"]["signed_mm"] is not None else -999.0,
             report["front_min_mm"] if report["front_min_mm"] is not None else -999.0,
             report["edge_min_mm"] if report["edge_min_mm"] is not None else -999.0,
             off, bad, tuple(round(v, 1) for v in box) if box else None))
    ok = box is not None and not off and not bad and report["ok"]
    if not ok:
        drop_objects(port_objs + [seated["plate"]])
        return None
    return {
        "frame": frame, "eul": eul, "objs": port_objs, "box": box,
        "angle": angle, "z": z, "t": t, "W": W,
        "align": report, "seat": seated,
    }


def glow_render(scene, objs, path):
    """White-emissive silhouette. The page tints it with the .glow rule."""
    white = principled(
        "gs_glow_white", (1.0, 1.0, 1.0), 0.0, 0.5, (1.0, 1.0, 1.0), 1.0)
    saved = {}
    for ob in objs:
        mats = getattr(ob.data, "materials", None)
        if not mats:
            continue
        saved[ob.name] = list(mats)
        for i in range(len(ob.data.materials)):
            ob.data.materials[i] = white
    view = scene.view_settings
    previous = (view.view_transform, view.look)
    try:
        view.view_transform = 'Standard'
        view.look = 'None'
    except (TypeError, AttributeError):
        pass
    render_visible(scene, [ob.name for ob in objs], path)
    try:
        view.view_transform, view.look = previous
    except (TypeError, AttributeError):
        pass
    for ob in objs:
        if ob.name not in saved:
            continue
        for i, mat in enumerate(saved[ob.name]):
            ob.data.materials[i] = mat


def render_contact_wire(scene, frame, names):
    """Edge-on orthographic view: the seating face against the dash profile."""
    cam_data = bpy.data.cameras.new("gs_align_cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 0.42
    cam_ob = bpy.data.objects.new("gs_align_cam", cam_data)
    bpy.context.collection.objects.link(cam_ob)
    u = Vector(frame.u)
    v = Vector(frame.v)
    n = Vector(frame.n)
    # Camera looks along -u. Up is the dash normal, so the plane is a horizontal line.
    loc = Vector(frame.o) + u * 0.85 + n * 0.02
    cam_ob.matrix_world = Matrix((
        (v.x, n.x, u.x, loc.x),
        (v.y, n.y, u.y, loc.y),
        (v.z, n.z, u.z, loc.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    old_cam = scene.camera
    old_rx = scene.render.resolution_x
    old_ry = scene.render.resolution_y
    scene.camera = cam_ob
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    os.makedirs(os.path.dirname(WIRE), exist_ok=True)
    render_visible(scene, list(DASH_MESHES) + names, WIRE)
    scene.camera = old_cam
    scene.render.resolution_x = old_rx
    scene.render.resolution_y = old_ry
    bpy.data.objects.remove(cam_ob, do_unlink=True)


def render_contact_closeup(scene, frame, names):
    """Oblique close view: underside center against the dash, front face exposed."""
    cam_data = bpy.data.cameras.new("gs_close_cam")
    cam_data.type = 'PERSP'
    cam_data.lens = 40.0
    cam_data.sensor_width = 36.0
    cam_ob = bpy.data.objects.new("gs_close_cam", cam_data)
    bpy.context.collection.objects.link(cam_ob)
    u = Vector(frame.u)
    v = Vector(frame.v)
    n = Vector(frame.n)
    o = Vector(frame.o)
    # Far enough to show the whole face and the dash around the contact,
    # from the pilot side and off the side so the center is not down the bore.
    eye = o + u * 0.34 + v * 0.07 + n * 0.50
    back = (eye - o).normalized()
    x_axis = n.cross(back).normalized()
    y_axis = back.cross(x_axis).normalized()
    cam_ob.matrix_world = Matrix((
        (x_axis.x, y_axis.x, back.x, eye.x),
        (x_axis.y, y_axis.y, back.y, eye.y),
        (x_axis.z, y_axis.z, back.z, eye.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    old_cam = scene.camera
    old_rx = scene.render.resolution_x
    old_ry = scene.render.resolution_y
    old_lens = scene.camera.data.lens
    scene.camera = cam_ob
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    os.makedirs(os.path.dirname(CLOSEUP), exist_ok=True)
    render_visible(scene, list(DASH_MESHES) + names, CLOSEUP)
    scene.camera = old_cam
    scene.render.resolution_x = old_rx
    scene.render.resolution_y = old_ry
    scene.camera.data.lens = old_lens
    bpy.data.objects.remove(cam_ob, do_unlink=True)


def main(check_only=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    if not os.path.exists(PLATE_SRC):
        raise SystemExit("missing " + PLATE_SRC)
    P = dict(shell.PARAMS)
    P["exterior"] = 0
    P["glass"] = 0
    if os.environ.get("GS_SAMPLES"):
        P["samples"] = int(os.environ["GS_SAMPLES"])
    scene = shell.build(P)
    if os.environ.get("GS_SAMPLES"):
        scene.eevee.taa_render_samples = P["samples"]
    cam = scene.camera
    bpy.context.view_layer.update()
    rects = keepouts()
    ranked = choose(scene, cam, P, rects)
    if not ranked:
        raise SystemExit("no fascia seat clears the keep-outs and the frame")
    print("FASCIA SEATS")
    for row in ranked[:8]:
        gap, width, angle, z, W, box = row
        print("  gap %.1f w %.1f angle %.1f z %.2f W %.2f box %s"
              % (gap, width, angle, z, W, tuple(round(v, 1) for v in box)))

    seated = None
    for row in ranked[:6]:
        _gap, _w, angle, z, W, _box = row
        seated = try_seat(scene, cam, P, rects, angle, z, W)
        if seated is not None:
            break
    if seated is None:
        raise SystemExit("projected fascia seats did not survive the real mesh")
    seated["choice"] = "fascia-lower-right"

    frame = seated["frame"]
    report = seated["align"]
    print("SEATED angle %.1f t %.2f W %.2f align %.4f deg residual %.4f mm "
          "raw_dot %.4f choice %s"
          % (seated["angle"], seated["t"], seated["W"],
             report["angle_deg"], report["max_abs_mm"], report["raw_dot"],
             seated["choice"]))
    code = align_check.emit(report)
    if code != 0:
        raise SystemExit("align check failed")
    if check_only:
        return 0
    if os.environ.get("GS_PROBE") == "1":
        print("PROBE STOP before render")
        return 0

    names = [o.name for o in seated["objs"]]
    if os.environ.get("GS_LOOK") == "1":
        render_visible(scene, list(DASH_MESHES) + names,
                       os.path.join(OUT_DIR, "look.png"))
        return
    render_visible(scene, names, SPRITE)
    render_visible(scene, DASH_MESHES, DASH_ONLY)
    render_visible(scene, list(DASH_MESHES) + names, DASH_BOTH)
    # F6 is the fire bottle and axe bracket on this apron. The port takes that
    # patch, so the baked dressing is replaced with the bare fascia there.
    f6 = fascia_screen_box(scene, cam, P, 43.0, 0.44, 0.22, 0.46, proud=0.12)
    if f6:
        print("MOVED DRESSING dr_f6 fire bottle off fascia box",
              tuple(round(v, 1) for v in f6))
    hotspot = composite_contact(
        PLATE_SRC, DASH_ONLY, DASH_BOTH, SPRITE, PLATE_OUT,
        clear_boxes=(f6,))
    print("WROTE", PLATE_OUT, os.path.getsize(PLATE_OUT))

    bad = hits((hotspot["x"], hotspot["y"], hotspot["w"], hotspot["h"]), rects, pad=0)
    if bad:
        raise SystemExit("hotspot covers " + ", ".join(bad))
    if seated["t"] < 0.0 or seated["t"] > 1.0:
        raise SystemExit("t %.3f is off the dash" % seated["t"])
    if not report["ok"]:
        raise SystemExit("align check failed after render")
    glow_render(scene, seated["objs"], GLOW)
    render_contact_wire(scene, frame, names)
    render_contact_closeup(scene, frame, names)

    cam_m = [float(v) for row in cam.matrix_world for v in row]
    record = {
        "plate": "combined/grading_station_plate.png",
        "sprite": "grading-station/station_sprite.png",
        "glow": "grading-station/station_glow.png",
        "sign": None,
        "source_plate": "combined/main_plate.png",
        "pixels": {"w": scene.render.resolution_x, "h": scene.render.resolution_y},
        "samples": P["samples"],
        "lens_mm": cam.data.lens,
        "sensor_width_mm": cam.data.sensor_width,
        "camera": {
            "location": [round(float(c), 6) for c in cam.location],
            "rotation_euler_rad": [round(float(c), 6) for c in cam.rotation_euler],
            "rotation_euler_deg": [round(math.degrees(float(c)), 4)
                                   for c in cam.rotation_euler],
            "matrix_world_row_major": [round(v, 6) for v in cam_m],
        },
        "mount": {
            "surface": "fascia",
            "mesh": "dash_fascia",
            "angle_deg": seated["angle"],
            "z_m": round(seated["z"], 4),
            "t": seated["t"],
            "W_m": seated["W"],
            "origin": [round(c, 6) for c in frame.o],
            "normal": [round(c, 6) for c in frame.n],
            "contact_gap_mm": report["center"]["signed_mm"],
            "bracket_intersects_dash": False,
            "contact_samples_mm": report["corner_mm"],
            "choice": seated["choice"],
            "align_angle_deg": report["angle_deg"],
            "raw_dot": report["raw_dot"],
            "roll_deg": report["roll_deg"],
            "center_mm": report["center"]["signed_mm"],
            "front_min_mm": report["front_min_mm"],
            "edge_min_mm": report["edge_min_mm"],
            "underside_height_m": round(seated["seat"]["height_m"], 5),
        },
        "align": report,
        "placement": {
            "surface": "fascia",
            "angle_deg": seated["angle"],
            "z_m": round(seated["z"], 4),
            "t": seated["t"],
            "W_m": seated["W"],
            "foreground": True,
            "spin_deg": SPIN_DEG,
            "seat_m": round(seated["seat"]["height_m"], 5),
            "euler_xyz_rad": [round(c, 6) for c in seated["eul"]],
            "origin": [round(c, 6) for c in frame.o],
            "u": [round(c, 6) for c in frame.u],
            "v": [round(c, 6) for c in frame.v],
            "n": [round(c, 6) for c in frame.n],
            "mesh_bbox_px": [round(c, 2) for c in seated["box"]],
        },
        "hotspot": hotspot,
        "alterations": {
            "geo": ALTERED_GEO,
            "spin_deg": SPIN_DEG,
            "label": None,
            "mark": None,
            "jewel": "amber emission, strength 7.5",
            "service_rail": "omitted; a wide rail on the tangent plane enters the curved dash",
            "seat": "underside center on dash_fascia; edges may enter the curve; front stays exposed",
            "sign": "removed; no plaque, band, or engraving",
            "dressing": "F6 fire bottle and axe bracket lifted off the lower-right fascia",
        },
        "shell_params_used": {
            "eye_height": P["eye_height"],
            "eye_y": P["eye_y"],
            "lens": P["lens"],
            "pitch": P["pitch"],
            "res_x": P["res_x"],
            "res_y": P["res_y"],
            "samples": P["samples"],
            "raytrace": P["raytrace"],
            "pixel": P["pixel"],
        },
    }
    with open(STATION_JSON, "w") as f:
        json.dump(record, f, indent=1)
    print("WROTE", STATION_JSON)
    select_plate.select_generated_plate(
        os.path.join(HERE, "combined", "manifest.json"),
        PLATE_OUT,
    )


if __name__ == "__main__":
    main()
