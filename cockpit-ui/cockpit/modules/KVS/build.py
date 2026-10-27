"""
KVS — "Core Memory Banks" cockpit control (SAINTCON 2026 AppSec Challenge UI).

The one text-first module. On the dash, at slot KVS, sits a brass desktop
teletype: a raked console face carrying a PAPER PLATEN (the printed RESP
session, real rendered type) and a row of MEMORY-BANK IDIOT LIGHTS, with a
TELEGRAPH KEY on the right of the front deck and a PUNCHED PAPER TAPE reel
(that's `EVAL`) on the left.  Behind it all: a wall of magnetic-core drums,
relay cans, and brass drawer labels — the keyspace as physical drawers.

Animation techniques used (all three):
    platen -> frames   (four printed states of the paper strip)
    tape   -> rotate   (one render, spun in CSS about its projected hub)
    key    -> states   (telegraph key up / pressed)
    lamps  -> states   (idle / read / write / eval / fault lamp patterns)

Build + render everything:
    /Applications/Blender.app/Contents/MacOS/Blender --background --python build.py
"""
import bpy, math, os, sys, json
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
COCKPIT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, COCKPIT)
import shell                                                     # noqa: E402
import slots                                                     # noqa: E402

OUT = os.path.join(HERE, "out")
CODE = "KVS"
NAME = "Core Memory Banks"

# ------------------------------------------------------------------ layout
# All geometry is modelled in the slot's LOCAL frame:
#   +X right along the surface, +Y up the surface, +Z out of the surface.
RAKE = math.radians(45.0)          # console face rake off the base plate
CS, SN = math.cos(RAKE), math.sin(RAKE)
HINGE = Vector((0.0, -0.005, 0.019))   # where the console face leaves the deck
PANEL_LEN = 0.175                      # console face length, along its rake
PANEL_W = 0.400

LAMPS = ["AUTH", "CORE", "RELAY", "TTL", "SCAN", "SAVE", "EVAL", "FAULT"]
LAMP_STATES = {                    # which idiot lights burn, per bank state
    "idle":  (1, 0, 0, 0, 0, 0, 0, 0),
    "read":  (1, 1, 0, 0, 1, 0, 0, 0),
    "write": (1, 1, 1, 0, 0, 1, 0, 0),
    "eval":  (1, 1, 1, 0, 0, 0, 1, 0),
    "fault": (1, 0, 0, 1, 0, 0, 0, 1),
}
LAMP_ORDER = ["idle", "read", "write", "eval", "fault"]

DRAWERS = ["hull.integrity", "crew.roster", "nav.fixcount", "auth.token"]

# The paper strip. Four printed states; the browser advances them.
PLATEN = [
    ["KVS CORE BANK  RESP2 RDY",
     "> PING",
     "+PONG",
     "> AUTH **********",
     "+OK"],
    ["> SET hull.integrity 97",
     "+OK",
     "> TYPE hull.integrity",
     "+string",
     "> TTL hull.integrity"],
    [":-1",
     "> INCR nav.fixcount",
     ":14",
     "> KEYS hull.*",
     '1) "hull.integrity"'],
    ['> EVAL "return 6*7" 0',
     ":42",
     "> SAVE",
     "+OK  dump.kvs  812 B",
     "> _"],
]

TXT_SIZE = 0.0310
TXT_LEAD = 0.0205
TXT_LEFT = -0.1450
TXT_TOP = 0.1040           # py of the first printed line


# --------------------------------------------------------------- utilities
def panel_pt(px, py, h=0.0):
    """A point on the raked console face. px across, py up from the hinge,
    h out along the face normal."""
    return Vector((px,
                   HINGE.y + py * CS - h * SN,
                   HINGE.z + py * SN + h * CS))


PANEL_ROT = (RAKE, 0.0, 0.0)       # lay a +Z-facing thing onto the console
WALL_ROT = (math.pi / 2, 0.0, 0.0)  # lay a +Z-facing thing onto the back wall


def _finish(o, name, mat, rot, bevel=0.0, smooth=False):
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


def cyl(name, center, radius, depth, mat, rot=(0, 0, 0), verts=28,
        smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                        vertices=verts, location=center)
    return _finish(bpy.context.object, name, mat, rot, smooth=smooth)


def disc(name, center, radius, mat, rot=(0, 0, 0), verts=40):
    return cyl(name, center, radius, 0.0022, mat, rot, verts)


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


def text(name, body, size, mat, loc, rot=(0, 0, 0), align='LEFT'):
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
    return shell.material("kvs_" + name, base, metallic, rough,
                          emission=emission, emit_strength=strength)


# ----------------------------------------------------------------- the prop
def add_props(P, mats):
    """Add the KVS teletype + core-memory bank to the CURRENT scene."""
    brass = mats["brass"]
    hull = mats["hull"]
    hull_d = mats["hull_d"]

    paper = mat("paper", (0.880, 0.855, 0.760, 1), 0.0, 0.80)
    ink = mat("ink", (0.055, 0.050, 0.055, 1), 0.0, 0.62)
    case = mat("case", (0.050, 0.054, 0.064, 1), 0.20, 0.44)
    felt = mat("felt", (0.040, 0.044, 0.052, 1), 0.0, 0.78)
    ebon = mat("ebon", (0.030, 0.030, 0.034, 1), 0.0, 0.30)

    off_a = mat("amber_off", (0.230, 0.150, 0.045, 1), 0.0, 0.36)
    on_a = mat("amber_on", (1.000, 0.720, 0.240, 1), 0.0, 0.30,
               emission=(1.0, 0.66, 0.20, 1), strength=6.0)
    off_g = mat("green_off", (0.070, 0.150, 0.090, 1), 0.0, 0.36)
    on_g = mat("green_on", (0.400, 1.000, 0.560, 1), 0.0, 0.30,
               emission=(0.30, 1.0, 0.48, 1), strength=5.0)
    off_r = mat("red_off", (0.200, 0.048, 0.052, 1), 0.0, 0.36)
    on_r = mat("red_on", (1.000, 0.280, 0.240, 1), 0.0, 0.30,
               emission=(1.0, 0.22, 0.16, 1), strength=7.0)

    loc, eul = slots.place(P, CODE)
    bpy.ops.object.empty_add(location=loc)
    root = bpy.context.object
    root.name = "kvs_root"
    root.rotation_euler = eul

    made = []                       # everything, in build order

    def add(o):
        made.append(o)
        return o

    # ---------------------------------------------------------- base + case
    add(box("kvs_plinth", (0, 0.005, 0.004), (0.442, 0.328, 0.008), brass,
            bevel=0.003))
    add(box("kvs_deck", (0, 0.005, 0.011), (0.420, 0.310, 0.014), case,
            bevel=0.004))

    # ------------------------------------------- back wall: drums + relays
    add(box("kvs_wall", (0, 0.137, 0.100), (0.420, 0.030, 0.200), hull,
            bevel=0.005))
    add(box("kvs_wall_cap", (0, 0.137, 0.202), (0.432, 0.038, 0.010), brass,
            bevel=0.003))
    # magnetic-core drums lying across the top of the wall
    for i, dx in enumerate((-0.136, 0.0, 0.136)):
        add(cyl(f"kvs_drum_{i}", (dx, 0.137, 0.226), 0.019, 0.116, hull_d,
                rot=(0, math.pi / 2, 0), verts=24))
        for j, sx in enumerate((-0.048, 0.0, 0.048)):
            add(cyl(f"kvs_drum_{i}_ring_{j}", (dx + sx, 0.137, 0.226), 0.0212,
                    0.008, brass, rot=(0, math.pi / 2, 0), verts=24))
        add(cyl(f"kvs_drum_{i}_spindle", (dx, 0.137, 0.226), 0.0055, 0.132,
                brass, rot=(0, math.pi / 2, 0), verts=12))
    # relay cans in a row on the visible strip of the wall face
    for i in range(9):
        rx = -0.144 + i * 0.036
        add(cyl(f"kvs_relay_{i}", (rx, 0.114, 0.186), 0.0072, 0.016, ebon,
                rot=WALL_ROT, verts=14))
        add(cyl(f"kvs_relay_{i}_cap", (rx, 0.1065, 0.186), 0.0078, 0.003,
                brass, rot=WALL_ROT, verts=14))
    # brass drawer labels — the keyspace, as physical drawer fronts
    for i, key in enumerate(DRAWERS):
        dx = -0.1515 + i * 0.101
        add(box(f"kvs_drawer_{i}", (dx, 0.1195, 0.156), (0.096, 0.006, 0.017),
                brass, bevel=0.001))
        add(text(f"kvs_drawerlabel_{i}", key, 0.0180, ink,
                 (dx, 0.1160, 0.1565), WALL_ROT, align='CENTER'))
        add(box(f"kvs_drawer_{i}_pull", (dx, 0.1155, 0.1495),
                (0.020, 0.004, 0.003), hull_d))

    # ------------------------------------------------- raked console face
    pc = panel_pt(0.0, PANEL_LEN / 2, -0.006)
    add(box("kvs_panel", pc, (PANEL_W, PANEL_LEN, 0.012), case,
            rot=PANEL_ROT, bevel=0.003))
    # brass surround
    add(box("kvs_panel_trim", panel_pt(0, PANEL_LEN / 2, -0.0075),
            (PANEL_W + 0.014, PANEL_LEN + 0.012, 0.011), brass,
            rot=PANEL_ROT, bevel=0.002))

    # ---- paper aperture, platen roller, printed strip
    win_lo, win_hi = 0.014, 0.112
    win_mid = (win_lo + win_hi) / 2
    paper_obj = add(box("kvs_paper", panel_pt(0, win_mid, 0.0014),
                        (0.316, win_hi - win_lo, 0.0016), paper,
                        rot=PANEL_ROT))
    for i, (yy, hh) in enumerate(((win_lo - 0.005, 0.010),
                                  (win_hi + 0.005, 0.010))):
        add(box(f"kvs_paper_rail_{i}", panel_pt(0, yy, 0.0030),
                (0.336, hh, 0.006), brass, rot=PANEL_ROT, bevel=0.001))
    for i, xx in enumerate((-0.166, 0.166)):
        add(box(f"kvs_paper_side_{i}", panel_pt(xx, win_mid, 0.0030),
                (0.010, win_hi - win_lo + 0.020, 0.006), brass,
                rot=PANEL_ROT, bevel=0.001))
    # sprocket holes down both margins of the paper
    for i in range(9):
        py = win_lo + 0.006 + i * 0.0110
        for j, xx in enumerate((-0.1500, 0.1500)):
            add(cyl(f"kvs_sprocket_{i}_{j}", panel_pt(xx, py, 0.0018),
                    0.0016, 0.0016, ebon, rot=PANEL_ROT, verts=8,
                    smooth=False))
    # platen roller poking out below the paper
    add(cyl("kvs_platen_roller", panel_pt(0, win_lo - 0.014, -0.002), 0.0105,
            0.352, hull_d, rot=(0, math.pi / 2, 0), verts=24))
    for i, xx in enumerate((-0.172, 0.172)):
        add(cyl(f"kvs_platen_knob_{i}", panel_pt(xx, win_lo - 0.014, -0.002),
                0.0155, 0.012, brass, rot=(0, math.pi / 2, 0), verts=20))

    # ---- the printed lines: four frames, only frame 0 shows at rest
    platen_frames = []
    for fi, lines in enumerate(PLATEN):
        objs = []
        for li, line in enumerate(lines):
            if not line:
                continue
            t = text(f"kvs_line_f{fi}_l{li}", line, TXT_SIZE, ink,
                     panel_pt(TXT_LEFT, TXT_TOP - li * TXT_LEAD, 0.0026),
                     PANEL_ROT, align='LEFT')
            if fi:
                t.hide_render = True     # combiner renders the wide shot only
            objs.append(add(t))
        platen_frames.append(objs)

    # ------------------------------------------------ memory-bank idiot lights
    lamp_domes, lamp_static = [], []
    for i, lab in enumerate(LAMPS):
        lx = -0.140 + i * 0.040
        lamp_static.append(add(cyl(f"kvs_lampring_{i}",
                                   panel_pt(lx, 0.152, 0.0035), 0.0118, 0.007,
                                   brass, rot=PANEL_ROT, verts=20)))
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.0092, segments=18, ring_count=10,
            location=panel_pt(lx, 0.152, 0.0072))
        d = bpy.context.object
        d.name = f"kvs_lamp_{i}"
        d.scale = (1.0, 1.0, 0.62)
        d.rotation_euler = PANEL_ROT
        for f in d.data.polygons:
            f.use_smooth = True
        d.data.materials.append(off_a)
        lamp_domes.append(add(d))
        lamp_static.append(add(text(f"kvs_lamplabel_{i}", lab, 0.0125, paper,
                                    panel_pt(lx, 0.1286, 0.0026), PANEL_ROT,
                                    align='CENTER')))
    lamp_off = [off_g] + [off_a] * 6 + [off_r]
    lamp_on = [on_g] + [on_a] * 6 + [on_r]
    for d, m in zip(lamp_domes, lamp_off):
        d.data.materials[0] = m

    # ------------------------------------------------------- telegraph key
    kx, ky = 0.118, -0.086
    add(box("kvs_key_base", (kx, ky, 0.021), (0.084, 0.104, 0.008), ebon,
            bevel=0.003))
    add(box("kvs_key_plate", (kx, ky, 0.026), (0.062, 0.084, 0.003), brass,
            bevel=0.001))
    for i, sx in enumerate((-0.021, 0.021)):
        add(box(f"kvs_key_post_{i}", (kx + sx, ky + 0.030, 0.036),
                (0.010, 0.010, 0.024), brass, bevel=0.002))
    add(cyl("kvs_key_anvil", (kx, ky - 0.052, 0.030), 0.0075, 0.010, brass,
            verts=14))
    add(text("kvs_key_label", "SEND", 0.0140, paper,
             (kx, ky + 0.046, 0.0280), align='CENTER'))

    key_hinge = Vector((kx, ky + 0.030, 0.048))
    bpy.ops.object.empty_add(location=key_hinge)
    key_piv = bpy.context.object
    key_piv.name = "kvs_key_pivot"

    key_arm = box("kvs_key_arm", (kx, ky - 0.014, 0.048),
                  (0.013, 0.098, 0.007), hull_d, bevel=0.002)
    key_trunnion = cyl("kvs_key_trunnion", (kx, ky + 0.030, 0.048), 0.0062,
                       0.052, brass, rot=(0, math.pi / 2, 0), verts=16)
    key_knob = cyl("kvs_key_knob", (kx, ky - 0.052, 0.0515), 0.0195, 0.007,
                   ebon, verts=26)
    key_skirt = cyl("kvs_key_skirt", (kx, ky - 0.052, 0.0470), 0.0125, 0.006,
                    brass, verts=18)
    key_objs = [key_arm, key_trunnion, key_knob, key_skirt]
    for o in key_objs:
        add(o)
        o.parent = key_piv
        # children were modelled in ROOT-local space, so undo the pivot offset
        o.matrix_parent_inverse = Matrix.Translation(-key_hinge)
    key_piv.rotation_euler = (math.radians(-6.0), 0, 0)

    # ------------------------------------------------- punched paper tape
    tx, ty = -0.150, -0.088
    treel = Vector((tx, ty, 0.047))
    add(box("kvs_tape_bracket", (tx, ty + 0.028, 0.026),
            (0.028, 0.054, 0.024), hull, rot=(math.radians(20), 0, 0),
            bevel=0.003))
    add(cyl("kvs_tape_spindle", treel, 0.0058, 0.030, brass, rot=PANEL_ROT,
            verts=14))
    boff = Vector((0, 0, -0.008))
    boff.rotate(Euler(PANEL_ROT, 'XYZ'))
    add(cyl("kvs_tape_backplate", treel + boff, 0.0400, 0.004, felt,
            rot=PANEL_ROT, verts=36))

    # the rotating reel itself (one render, spun by CSS)
    reel_parts = []
    reel_parts.append(cyl("kvs_reel_rim", treel, 0.0375, 0.0080, brass,
                          rot=PANEL_ROT, verts=36))
    reel_parts.append(cyl("kvs_reel_web", treel, 0.0345, 0.0095, ebon,
                          rot=PANEL_ROT, verts=36))
    reel_parts.append(cyl("kvs_reel_hub", treel, 0.0110, 0.0135, brass,
                          rot=PANEL_ROT, verts=20))
    for i in range(5):
        th = 2 * math.pi * i / 5
        # the spoke's long axis is its local +Y, so the radial offset must
        # follow +Y through the same Z spin.
        off = Vector((-math.sin(th) * 0.0215, math.cos(th) * 0.0215, 0.0))
        off.rotate(Euler(PANEL_ROT, 'XYZ'))
        s_ = box(f"kvs_reel_spoke_{i}", treel + off,
                 (0.0075, 0.0330, 0.0112), brass)
        s_.rotation_euler = (Euler(PANEL_ROT, 'XYZ').to_matrix()
                             @ Euler((0, 0, th), 'XYZ').to_matrix()
                             ).to_euler()
        reel_parts.append(s_)
    # a witness pip so the spin is unmistakable
    noff = Vector((0.0, 0.0290, 0.0))
    noff.rotate(Euler(PANEL_ROT, 'XYZ'))
    reel_parts.append(cyl("kvs_reel_index", treel + noff, 0.0052, 0.0150,
                          on_a, rot=PANEL_ROT, verts=12))
    for o in reel_parts:
        add(o)

    # the tape itself: off the reel, flat across the deck, into the reader
    add(box("kvs_tape_strip", (-0.070, -0.052, 0.0192),
            (0.108, 0.026, 0.0014), paper))
    for i in range(7):
        for j in range(3):
            add(cyl(f"kvs_tape_hole_{i}_{j}",
                    (-0.116 + i * 0.0155, -0.060 + j * 0.008, 0.0200),
                    0.0016, 0.0018, ebon, verts=6, smooth=False))
    add(box("kvs_tape_reader", (-0.006, -0.052, 0.0245),
            (0.030, 0.044, 0.017), brass, bevel=0.002))
    add(box("kvs_tape_reader_slot", (-0.006, -0.052, 0.0210),
            (0.034, 0.028, 0.006), ebon))
    add(text("kvs_tape_label", "EVAL", 0.0135, ink,
             (-0.006, -0.052, 0.0332), align='CENTER'))

    # ------------------------------------------------------------ nameplate
    add(box("kvs_nameplate", (-0.020, -0.128, 0.0195), (0.164, 0.024, 0.004),
            brass, bevel=0.001))
    add(text("kvs_nameplate_txt", "KVS  CORE MEMORY", 0.0250, ink,
             (-0.020, -0.128, 0.0226), align='CENTER'))

    # ------------------------------------------------------------ parenting
    for o in made:
        if o.parent is None:
            o.parent = root
            o.matrix_parent_inverse = Matrix.Identity(4)
    key_piv.parent = root
    key_piv.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()

    far = [o for o in made]
    static = [o for o in made
              if o not in key_objs and o not in reel_parts
              and o not in lamp_domes
              and not any(o in fr for fr in platen_frames)]

    controls = {
        "platen": {"kind": "frames", "label": "TELETYPE PLATEN",
                   "objs": [o for fr in platen_frames for o in fr],
                   "frame_objs": platen_frames, "pivot": None,
                   "hotspot_objs": [paper_obj], "text": PLATEN},
        "tape": {"kind": "rotate", "label": "PUNCHED TAPE (EVAL)",
                 "objs": reel_parts, "pivot": None,
                 "anchor_local": treel.copy(), "root": root},
        "key": {"kind": "states", "label": "TELEGRAPH KEY",
                "objs": key_objs, "pivot": key_piv,
                "angles": {"up": -6.0, "down": 9.0}},
        "lamps": {"kind": "states", "label": "MEMORY BANK",
                  "objs": lamp_domes, "pivot": None,
                  "domes": lamp_domes, "off": lamp_off, "on": lamp_on,
                  "patterns": LAMP_STATES, "order": LAMP_ORDER,
                  "labels": LAMPS,
                  "hotspot_objs": lamp_domes + lamp_static},
    }
    return {"far": far, "controls": controls, "root": root, "static": static,
            "all": made}


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

    manifest = {"code": CODE, "name": NAME, "surface": slots.SLOTS[CODE]["surface"],
                "far": {}, "close": {"canvas": {"w": W, "h": H},
                                     "plate": "close_plate.png",
                                     "controls": {}}}

    # ------------------------------------------------------------- far view
    render_to(scene, os.path.join(OUT, "far_prop.png"), mine)
    far_hot = clamp_rect(bbox_rect(scene, main_cam, mine, pad=5), W, H)

    glow = shell.material("kvs_glowmask", (0, 0, 0, 1), 0.0, 1.0,
                          emission=(1, 1, 1, 1), emit_strength=4.0)
    saved_mats = {}
    for o in mine:
        saved_mats[o.name] = list(o.data.materials)
        o.data.materials.clear()
        o.data.materials.append(glow)
    render_to(scene, os.path.join(OUT, "far_glow.png"), mine)
    for o in mine:
        o.data.materials.clear()
        for m in saved_mats[o.name]:
            o.data.materials.append(m)

    manifest["far"] = {"prop": "far_prop.png", "glow": "far_glow.png",
                       "hotspot": far_hot}
    print("FAR HOTSPOT", far_hot)

    # ------------------------------------------------------- close-up rig
    ctr = root.matrix_world @ panel_pt(0.0, 0.070, 0.010)
    view = (main_cam.matrix_world.translation - ctr).normalized()
    bpy.ops.object.camera_add(location=ctr + view * 0.90)
    close_cam = bpy.context.object
    close_cam.name = "kvs_closecam"
    close_cam.data.lens = 50.0
    ctr = fit_camera(scene, close_cam, mine, ctr, view, frac=0.90)

    up = (root.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    right = view.cross(up).normalized()
    for off, energy, size, col in (
            (right * 0.52 + up * 0.46 + view * 0.34, 3.0, 0.55,
             (1.0, 0.88, 0.70)),
            (-right * 0.60 + up * 0.24 + view * 0.42, 1.6, 0.70,
             (0.66, 0.79, 1.00)),
            (up * 0.34 + view * 0.44 - right * 0.06, 0.9, 0.50,
             (1.0, 0.93, 0.80))):
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

    # --- platen: a frame per printed state -----------------------------
    frames, rects = [], []
    for fi, objs in enumerate(ctrl["platen"]["frame_objs"]):
        fn = f"close_platen_{fi}.png"
        render_to(scene, os.path.join(OUT, fn), objs)
        frames.append(fn)
        rects.append(bbox_rect(scene, close_cam, objs, pad=10))
    rects.append(bbox_rect(scene, close_cam, ctrl["platen"]["hotspot_objs"],
                           pad=4))
    C["platen"] = {"kind": "frames", "label": ctrl["platen"]["label"],
                   "frames": frames,
                   "hotspot": clamp_rect(union(rects), W, H),
                   "text": PLATEN}

    # --- tape reel: one render, CSS-rotated about its projected hub -----
    render_to(scene, os.path.join(OUT, "close_tape.png"), ctrl["tape"]["objs"])
    hub_w = root.matrix_world @ ctrl["tape"]["anchor_local"]
    px, py = project(scene, close_cam, hub_w)
    C["tape"] = {"kind": "rotate", "label": ctrl["tape"]["label"],
                 "image": "close_tape.png",
                 "pivot": {"x": round(px, 1), "y": round(py, 1)},
                 "range": [0, 1440],
                 "hotspot": clamp_rect(
                     bbox_rect(scene, close_cam, ctrl["tape"]["objs"], pad=8),
                     W, H)}

    # --- telegraph key: two rendered states ----------------------------
    piv = ctrl["key"]["pivot"]
    states, rects = {}, []
    for nm, ang in (("up", ctrl["key"]["angles"]["up"]),
                    ("down", ctrl["key"]["angles"]["down"])):
        piv.rotation_euler = (math.radians(ang), 0, 0)
        bpy.context.view_layer.update()
        fn = f"close_key_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), ctrl["key"]["objs"])
        states[nm] = fn
        rects.append(bbox_rect(scene, close_cam, ctrl["key"]["objs"], pad=8))
    piv.rotation_euler = (math.radians(ctrl["key"]["angles"]["up"]), 0, 0)
    bpy.context.view_layer.update()
    C["key"] = {"kind": "states", "label": ctrl["key"]["label"],
                "states": states, "hotspot": clamp_rect(union(rects), W, H)}

    # --- idiot lights: a render per bank pattern ------------------------
    L = ctrl["lamps"]
    states = {}
    for nm in L["order"]:
        pat = L["patterns"][nm]
        for i, d in enumerate(L["domes"]):
            d.data.materials[0] = (L["on"][i] if pat[i] else L["off"][i])
        fn = f"close_lamps_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), L["domes"])
        states[nm] = fn
    for i, d in enumerate(L["domes"]):
        d.data.materials[0] = L["off"][i]
    C["lamps"] = {"kind": "states", "label": L["label"], "states": states,
                  "order": L["order"], "lamps": L["labels"],
                  "patterns": {k: list(v) for k, v in L["patterns"].items()},
                  "hotspot": clamp_rect(
                      bbox_rect(scene, close_cam, L["hotspot_objs"], pad=8),
                      W, H)}

    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("HOTSPOTS", json.dumps(
        {k: v["hotspot"] for k, v in C.items()}, indent=1))
    print("KVS OK ->", OUT)


if __name__ == "__main__":
    main()
