"""
TRANSLITERATION PIPELINE — Blender scene -> everything three.js needs.

One command per module.  No hand-tuning, no per-prop steps.  Emits, for the
locked wide camera and for the module's own close-up camera:

    plate.png        the baked colour plate (what ships today)
    depth.bin        float32 LINEAR view depth, one value per pixel, top-down
    scene.json       camera + lights + colour management, already in three's
                     Y-up frame, with the CORRECT vertical FOV
    prop.glb         the interactive prop, world coords, Y-up
    materials.json   Principled scalars for EVERY material, by name.  The glTF
                     exporter silently drops roughnessFactor/metallicFactor
                     whenever those inputs are node-driven -- and since the
                     texture pass landed that is ESSENTIALLY EVERY MATERIAL.
                     This file is the side channel that makes the re-apply
                     mechanical instead of a thing someone remembers to do.
    env.bin          equirectangular float32 RGB environment probe rendered
                     FROM THE PROP'S OWN LOCATION with the prop hidden, so
                     three's metals reflect the surrounding console instead of
                     reflecting nothing.
    gt_*.png         Blender ground truth for the honest rms comparisons.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python pipeline/transliterate.py -- module=KVS [steps=all]

Everything is read from ./src/*_snapshot.py, never from the live project.
"""
import bpy, bmesh, math, os, sys, json
import numpy as np
from mathutils import Vector, Euler, Matrix

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "src")
ASSETS = os.path.join(HERE, "assets")
sys.path.insert(0, SRC)
import shell_snapshot as shell                                   # noqa: E402
import slots_snapshot as slots                                   # noqa: E402
sys.modules["shell"] = shell
sys.modules["slots"] = slots

MODULES = {"KVS": "kvs_build_snapshot"}

# The capsule flies a circular path at r=CAP_R, BEHIND the pillars (r=2.57)
# and in FRONT of the glass (r=2.95), at window-band height.  It is the
# occlusion case sprites cannot do.
CAP_R, CAP_Z = 2.75, 1.45
CAP_A0, CAP_A1 = -55.0, 55.0
# t at which the capsule is EXACTLY behind a pillar: pillars sit at -/+27 deg,
# the sweep runs CAP_A0..CAP_A1, so t = (deg - CAP_A0) / (CAP_A1 - CAP_A0).
GT_CAPSULE_T = [0.150, 0.2545, 0.360, 0.500, 0.6400, 0.7455, 0.850]
REEL_GT_DEG = [0.0, 40.0]
PROBE_FACE = 192          # cube face resolution for the env probe
PROBE_W, PROBE_H = 512, 256
CAP_SCALE = 2.0     # big enough to STRADDLE a pillar, not just hide behind it


# --------------------------------------------------------------- conversions
def to3(v):
    """Blender Z-up world -> three.js / glTF Y-up world."""
    return [v[0], v[2], -v[1]]


def fov_y_deg(cam, W, H):
    """Blender's cam.data.angle_y comes from sensor_HEIGHT (24 mm) and is NOT
    the render's vertical FOV under sensor_fit AUTO on a wide frame.  Derive
    it from angle_x and the render aspect or the prop lands ~50 px out."""
    return math.degrees(2 * math.atan(math.tan(cam.data.angle_x / 2) * H / W))


def cam_json(scene, cam):
    m = cam.matrix_world
    W, H = scene.render.resolution_x, scene.render.resolution_y
    return {"lens_mm": cam.data.lens, "sensor_mm": cam.data.sensor_width,
            "sensor_fit": cam.data.sensor_fit,
            "angle_x_deg": math.degrees(cam.data.angle_x),
            "angle_y_deg_BLENDER_DO_NOT_USE": math.degrees(cam.data.angle_y),
            "fov_y_deg": fov_y_deg(cam, W, H),
            "clip": [cam.data.clip_start, cam.data.clip_end],
            "pos": to3(m.translation),
            "forward": to3((m.to_3x3() @ Vector((0, 0, -1))).normalized()),
            "up": to3((m.to_3x3() @ Vector((0, 1, 0))).normalized())}


def lights_json(scene, tags=None):
    out = []
    for L in scene.objects:
        if L.type != 'LIGHT':
            continue
        m = L.matrix_world
        out.append({"tag": (tags or {}).get(L.name, "shell"),
                    "type": L.data.type,
                    "pos": to3(m.translation),
                    "dir": to3((m.to_3x3() @ Vector((0, 0, -1))).normalized()),
                    "energy": L.data.energy,
                    "size": getattr(L.data, "size", 0.1),
                    "color": list(L.data.color)})
    return out


def materials_json():
    """The side channel.  Every Principled scalar, by material name, so the
    frontend can put back what the glTF exporter dropped."""
    out = {}
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        b = m.node_tree.nodes.get("Principled BSDF")
        if not b:
            continue

        def val(n, d=None):
            i = b.inputs.get(n)
            if i is None:
                return d
            v = i.default_value
            try:
                return list(v)
            except TypeError:
                return v
        out[m.name] = {
            "base": val("Base Color"), "metallic": val("Metallic"),
            "rough": val("Roughness"), "emission": val("Emission Color"),
            "emit": val("Emission Strength"),
            "alpha": val("Alpha", 1.0),
            # which of them the exporter will have thrown away
            "node_driven": [i.name for i in b.inputs if i.is_linked],
        }
    return out


# ------------------------------------------------------------ render helpers
def renderables(scene):
    return [o for o in scene.objects
            if o.type in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}]


def visible_only(scene, visible):
    vis = set(visible)
    saved = {}
    for o in renderables(scene):
        saved[o.name] = o.hide_render
        o.hide_render = o not in vis
    return saved


def restore(scene, saved):
    for o in renderables(scene):
        if o.name in saved:
            o.hide_render = saved[o.name]


def render_colour(scene, path, visible=None, hide=()):
    scene.use_nodes = False
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    saved = None
    if visible is not None:
        saved = visible_only(scene, visible)
    else:
        saved = {o.name: o.hide_render for o in renderables(scene)}
        for o in hide:
            o.hide_render = True
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    restore(scene, saved)
    print("  colour ->", os.path.basename(path))


def exr_channel(path, W, H, ch=0, nch=4):
    """Load an EXR back and return channel `ch` as a top-down float32 array."""
    img = bpy.data.images.load(path, check_existing=False)
    n = W * H * img.channels
    buf = np.empty(n, dtype=np.float32)
    img.pixels.foreach_get(buf)
    a = buf.reshape(H, W, img.channels)[:, :, ch]
    bpy.data.images.remove(img)
    return np.ascontiguousarray(a[::-1])          # Blender is bottom-up


def render_depth(scene, out_bin, hide=()):
    """Blender's Z pass, written as raw little-endian float32, top-down.

    EXR is scene-referred, so no view transform touches it and the values come
    back as true LINEAR VIEW DEPTH in metres along the camera's -Z axis.  That
    is the one thing that has to be exact, and it is verified below against a
    point whose depth we know analytically."""
    vl = scene.view_layers[0]
    vl.use_pass_z = True
    # Blender 5.x replaced scene.node_tree + CompositorNodeComposite with a
    # compositing NODE GROUP whose interface carries the output socket.
    if hasattr(scene, "compositing_node_group"):
        ng = bpy.data.node_groups.get("depth_pass")
        if ng is None:
            ng = bpy.data.node_groups.new("depth_pass", "CompositorNodeTree")
            rl = ng.nodes.new('CompositorNodeRLayers')
            go = ng.nodes.new('NodeGroupOutput')
            ng.interface.new_socket('Image', in_out='OUTPUT',
                                    socket_type='NodeSocketColor')
            ng.links.new(rl.outputs['Depth'], go.inputs['Image'])
        scene.compositing_node_group = ng
        scene.use_nodes = True
    else:                                              # <= 4.x
        scene.use_nodes = True
        t = scene.node_tree
        t.nodes.clear()
        rl = t.nodes.new('CompositorNodeRLayers')
        co = t.nodes.new('CompositorNodeComposite')
        t.links.new(rl.outputs['Depth'], co.inputs['Image'])
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '32'
    scene.render.image_settings.exr_codec = 'NONE'
    tmp = out_bin.replace(".bin", "_tmp.exr")
    saved = {o.name: o.hide_render for o in renderables(scene)}
    for o in hide:
        o.hide_render = True
    scene.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    restore(scene, saved)
    W, H = scene.render.resolution_x, scene.render.resolution_y
    d = exr_channel(tmp, W, H, 0)
    os.remove(tmp)
    scene.use_nodes = False
    if hasattr(scene, "compositing_node_group"):
        scene.compositing_node_group = None
    d.astype('<f4').tofile(out_bin)
    finite = d[d < 1e9]
    print("  depth  -> %s   near %.4f  far %.4f  bg %d px"
          % (os.path.basename(out_bin), finite.min(), finite.max(),
             int((d >= 1e9).sum())))
    return d


def verify_depth(scene, cam, depth, probes):
    """The crux.  For a handful of known world points, project them and check
    the baked depth at that pixel equals the analytic view depth."""
    from bpy_extras.object_utils import world_to_camera_view
    W, H = scene.render.resolution_x, scene.render.resolution_y
    fwd = (cam.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
    rows = []
    for name, p in probes:
        co = world_to_camera_view(scene, cam, p)
        x, y = int(co.x * W), int((1 - co.y) * H)
        if not (0 <= x < W and 0 <= y < H):
            rows.append((name, None, None, None))
            continue
        want = (p - cam.matrix_world.translation).dot(fwd)
        got = float(depth[y, x])
        rows.append((name, want, got, got - want))
    return rows


# ------------------------------------------------------------- env probe
FACES = [  # (name, forward, up) in BLENDER world axes
    ("px", (1, 0, 0), (0, 0, 1)), ("nx", (-1, 0, 0), (0, 0, 1)),
    ("py", (0, 1, 0), (0, 0, 1)), ("ny", (0, -1, 0), (0, 0, 1)),
    ("pz", (0, 0, 1), (0, 1, 0)), ("nz", (0, 0, -1), (0, 1, 0)),
]


def render_probe(scene, loc, out_bin, hide=()):
    """Six 90-degree EXR renders from `loc`, resampled into a three.js-
    convention equirectangular float32 RGB map.

    Rendering six explicit perspective cameras and doing the equirect
    resample here means no cube-face orientation convention has to be
    guessed on either side -- the only convention involved is three's own
    equirectUv(), which is written out in the resample loop below."""
    W0, H0 = scene.render.resolution_x, scene.render.resolution_y
    cam0 = scene.camera
    fmt = scene.render.image_settings.file_format
    scene.render.resolution_x = scene.render.resolution_y = PROBE_FACE
    scene.use_nodes = False
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '32'
    scene.render.image_settings.exr_codec = 'NONE'
    bpy.ops.object.camera_add(location=loc)
    pc = bpy.context.object
    pc.name = "env_probe_cam"
    pc.data.sensor_fit = 'VERTICAL'
    pc.data.lens = 18.0
    pc.data.sensor_height = 36.0          # -> 90 deg square FOV
    scene.camera = pc
    saved = {o.name: o.hide_render for o in renderables(scene)}
    for o in hide:
        o.hide_render = True

    faces = {}
    for name, f, u in FACES:
        f = Vector(f).normalized()
        u = Vector(u).normalized()
        r = f.cross(u).normalized()
        M = Matrix((( r.x, u.x, -f.x), (r.y, u.y, -f.y), (r.z, u.z, -f.z)))
        pc.rotation_euler = M.to_euler()
        bpy.context.view_layer.update()
        tmp = out_bin.replace(".bin", f"_{name}.exr")
        scene.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp, check_existing=False)
        buf = np.empty(PROBE_FACE * PROBE_FACE * img.channels, dtype=np.float32)
        img.pixels.foreach_get(buf)
        a = buf.reshape(PROBE_FACE, PROBE_FACE, img.channels)[:, :, :3]
        bpy.data.images.remove(img)
        os.remove(tmp)
        faces[name] = np.ascontiguousarray(a[::-1])       # top-down
        faces[name + "_basis"] = (f, u, r)

    restore(scene, saved)
    bpy.data.objects.remove(pc, do_unlink=True)
    scene.camera = cam0
    scene.render.resolution_x, scene.render.resolution_y = W0, H0
    scene.render.image_settings.file_format = fmt

    # ---- resample to three.js equirect ----------------------------------
    # three/src/renderers/shaders/ShaderChunk/common: equirectUv( dir ) is
    #     u = atan( dir.z, dir.x ) / (2*PI) + 0.5
    #     v = asin( dir.y ) / PI + 0.5
    # DataTexture row 0 is v = 0, so we build bottom-up in v.
    j, i = np.mgrid[0:PROBE_H, 0:PROBE_W]
    u = (i + 0.5) / PROBE_W
    v = (j + 0.5) / PROBE_H
    phi = (u - 0.5) * 2 * math.pi
    th = (v - 0.5) * math.pi
    ty = np.sin(th)
    rr = np.cos(th)
    tx = rr * np.cos(phi)
    tz = rr * np.sin(phi)
    # three (X,Y,Z) -> blender (X, -Z, Y)
    bx, by, bz = tx, -tz, ty
    d = np.stack([bx, by, bz], axis=-1)

    out = np.zeros((PROBE_H, PROBE_W, 3), dtype=np.float32)
    for name, _f, _u in FACES:
        f, uu, r = faces[name + "_basis"]
        fw = d @ np.array([f.x, f.y, f.z], dtype=np.float64)
        ru = d @ np.array([r.x, r.y, r.z], dtype=np.float64)
        up = d @ np.array([uu.x, uu.y, uu.z], dtype=np.float64)
        with np.errstate(divide='ignore', invalid='ignore'):
            su = ru / fw
            sv = up / fw
        m = (fw > 1e-9) & (np.abs(su) <= 1.0000001) & (np.abs(sv) <= 1.0000001)
        px = np.clip(((su * 0.5 + 0.5) * PROBE_FACE).astype(int),
                     0, PROBE_FACE - 1)
        py = np.clip(((0.5 - sv * 0.5) * PROBE_FACE).astype(int),
                     0, PROBE_FACE - 1)
        out[m] = faces[name][py[m], px[m]]
    out.astype('<f4').tofile(out_bin)
    print("  probe  -> %s  %dx%d  max %.3f"
          % (os.path.basename(out_bin), PROBE_W, PROBE_H, float(out.max())))


# ------------------------------------------------------------- the capsule
def capsule_pos(t):
    a = math.radians(CAP_A0 + (CAP_A1 - CAP_A0) * t)
    return Vector((CAP_R * math.sin(a), CAP_R * math.cos(a), CAP_Z)), a


def add_capsule(mats):
    """A message-torpedo probe: the moving thing that must pass BEHIND the
    pillars.  Modelled at the ORIGIN, +X along travel, so three.js can place
    and aim it; Blender only ever moves it for the ground-truth renders."""
    brass = mats["brass"]
    glow = shell.material("cap_glow", (1.0, 0.55, 0.18, 1), 0.0, 0.3,
                          emission=(1.0, 0.48, 0.12, 1), emit_strength=14.0,
                          texture=False)
    shellm = shell.material("cap_shell", (0.62, 0.63, 0.66, 1), 0.85, 0.28)
    parts = []

    def mk(o, m, smooth=True):
        o.data.materials.append(m)
        if smooth:
            for f in o.data.polygons:
                f.use_smooth = True
        parts.append(o)
        return o
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.075, segments=32,
                                         ring_count=16)
    b = bpy.context.object
    b.name = "cap_body"
    b.scale = (2.05, 1.0, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    mk(b, shellm)
    for i, x in enumerate((-0.075, 0.0, 0.075)):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.079, depth=0.016,
                                            vertices=32, location=(x, 0, 0),
                                            rotation=(0, math.pi / 2, 0))
        c = bpy.context.object
        c.name = f"cap_band_{i}"
        mk(c, brass)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.042, segments=20,
                                         ring_count=10, location=(0.148, 0, 0))
    n = bpy.context.object
    n.name = "cap_nose"
    mk(n, glow)
    for i, s in enumerate((1, -1)):
        bpy.ops.mesh.primitive_cube_add(size=1,
                                        location=(-0.10, 0, 0.052 * s))
        fin = bpy.context.object
        fin.name = f"cap_fin_{i}"
        fin.scale = (0.085, 0.010, 0.055)
        bpy.ops.object.transform_apply(scale=True)
        mk(fin, brass, smooth=False)
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:
        o.select_set(True)
        o.scale = (CAP_SCALE,) * 3
        o.location = o.location * CAP_SCALE
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return parts


CAP_BASE = {}


def place_capsule(parts, t):
    p, a = capsule_pos(t)
    # +X of the model runs along travel; travel tangent at angle a is
    # (cos a, -sin a, 0) for a sweep of increasing a.
    rz = -a + math.pi / 2
    M = Matrix.Translation(p) @ Matrix.Rotation(rz, 4, 'Z')
    for o in parts:
        o.matrix_world = M @ CAP_BASE[o.name]
    bpy.context.view_layer.update()


def export_glb(objs, path):
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


# ===========================================================================
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = dict(a.split("=", 1) for a in argv if "=" in a)
    code = args.get("module", "KVS")
    steps = args.get("steps", "all")
    # EEVEE ships with use_raytracing = False, so the baked plates contain NO
    # screen-space reflections at all: metal reflects only the near-black world
    # and the area lights.  rt=1 turns it on and writes to a parallel folder,
    # so the env-probe question can be asked against BOTH kinds of plate.
    rt = args.get("rt", "0") == "1"
    mod = __import__(MODULES[code])

    P = dict(shell.PARAMS)
    P["exterior"] = 0
    scene = shell.build(P)
    wide_cam = scene.camera
    scene.render.film_transparent = True
    W, H = scene.render.resolution_x, scene.render.resolution_y
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    if rt:
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.resolution_scale = '1'
        print("EEVEE raytracing ON")
    R = mod.add_props(P, mats)
    mine, ctrl, root = R["all"], R["controls"], R["root"]

    cap = add_capsule(mats)
    for o in cap:
        CAP_BASE[o.name] = o.matrix_world.copy()
    place_capsule(cap, 0.5)

    WIDE = os.path.join(ASSETS, "wide")
    CLOSE = os.path.join(ASSETS, code, "close_rt" if rt else "close")
    os.makedirs(WIDE, exist_ok=True)
    os.makedirs(CLOSE, exist_ok=True)

    shell_meshes = [o for o in renderables(scene)
                    if o not in set(mine) and o not in set(cap)]

    # ================================================================= WIDE
    if steps in ("all", "wide"):
        print("[wide]")
        static = shell_meshes + mine          # everything baked into the plate
        render_colour(scene, os.path.join(WIDE, "plate.png"), visible=static)
        dep = render_depth(scene, os.path.join(WIDE, "depth.bin"), hide=cap)

        # --- the verification the whole technique rests on ----------------
        # Probe points must be on VISIBLE SURFACES -- an interior point of a
        # solid is not what the depth pass records.  (The rigorous check is
        # pipeline/verify_depth.py, which ray-casts a few hundred pixels.)
        eye = wide_cam.matrix_world.translation
        pillar = bpy.data.objects["column_0"]
        pc = pillar.matrix_world.translation + Vector((0, 0, 0.15))
        toeye = Vector((eye.x - pc.x, eye.y - pc.y, 0)).normalized()
        probes = [("column_0 face", pc + toeye * P["pillar_radius"]),
                  ("window (bg)", Vector((0.0, 4.0, 1.40)))]
        rows = verify_depth(scene, wide_cam, dep, probes)
        print("  DEPTH VERIFY   analytic vs baked (metres along view axis)")
        for n, want, got, err in rows:
            if want is None:
                print("    %-18s off frame" % n)
            else:
                print("    %-18s want %.5f  got %.5f  err %+.5f"
                      % (n, want, got, err))

        gt_files = []
        for t in GT_CAPSULE_T:
            place_capsule(cap, t)
            fn = "gt_capsule_%04d.png" % int(round(t * 1000))
            render_colour(scene, os.path.join(WIDE, fn), visible=static + cap)
            gt_files.append({"t": t, "file": fn})
        place_capsule(cap, 0.2545)
        render_colour(scene, os.path.join(WIDE, "gt_capsule_alone_254.png"),
                      visible=cap)


        j = {"render": {"w": W, "h": H},
             "camera": cam_json(scene, wide_cam),
             "lights": lights_json(scene),
             "world_bg": list(scene.world.node_tree.nodes["Background"]
                              .inputs[0].default_value),
             "colour": {"view_transform": scene.view_settings.view_transform,
                        "look": scene.view_settings.look,
                        "exposure": scene.view_settings.exposure},
             # measured by fitting three's render to Blender's, per view
             "light_gain": 0.45,
             "env_intensity": 0.0,
             "depth": {"file": "depth.bin", "format": "float32-le",
                       "layout": "top-down rows, 1 value per pixel",
                       "meaning": "linear view depth in metres along -Z_cam",
                       "background": 1e10},
             "env": {"file": "env.bin", "format": "float32-le RGB",
                     "w": PROBE_W, "h": PROBE_H,
                     "mapping": "EquirectangularReflectionMapping, row 0 = v0",
                     "origin": to3(capsule_pos(0.5)[0])},
             "capsule": {"glb": "capsule.glb", "r": CAP_R, "z": CAP_Z,
                         "a0": CAP_A0, "a1": CAP_A1,
                         "gt": gt_files,
                         "path_note": "blender: (r*sin a, r*cos a, z); "
                                      "three: (r*sin a, z, -r*cos a)"},
             "depth_verify": [{"name": n, "analytic": w, "baked": g,
                               "err": e} for n, w, g, e in rows]}
        with open(os.path.join(WIDE, "scene.json"), "w") as f:
            json.dump(j, f, indent=1)
        with open(os.path.join(WIDE, "materials.json"), "w") as f:
            json.dump(materials_json(), f, indent=1)

        # env probe at the middle of the capsule's flight, capsule hidden
        render_probe(scene, capsule_pos(0.5)[0],
                     os.path.join(WIDE, "env.bin"), hide=cap)
        for o in cap:
            o.matrix_world = CAP_BASE[o.name]
        bpy.context.view_layer.update()
        export_glb(cap, os.path.join(WIDE, "capsule.glb"))

        # ground truth: capsule rendered IN the scene, real occlusion

    # ================================================================ CLOSE
    if steps in ("all", "close"):
        print("[close]")
        ctr = root.matrix_world @ mod.panel_pt(0.0, 0.070, 0.010)
        view = (wide_cam.matrix_world.translation - ctr).normalized()
        bpy.ops.object.camera_add(location=ctr + view * 0.90)
        cc = bpy.context.object
        cc.name = code + "_closecam"
        cc.data.lens = 50.0
        ctr = mod.fit_camera(scene, cc, mine, ctr, view, frac=0.90)
        up = (root.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
        right = view.cross(up).normalized()
        close_tags = {}
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
            close_tags[L.name] = "close"
        scene.camera = cc
        bpy.context.view_layer.update()

        reel = ctrl["tape"]["objs"]
        plate = shell_meshes + R["static"]
        for o in cap:
            o.hide_render = True
        render_colour(scene, os.path.join(CLOSE, "plate.png"), visible=plate)
        dep = render_depth(scene, os.path.join(CLOSE, "depth.bin"),
                           hide=list(cap) + list(reel))

        hub = root.matrix_world @ ctrl["tape"]["anchor_local"]
        n_local = Euler(mod.PANEL_ROT, 'XYZ').to_matrix() @ Vector((0, 0, 1))
        axis = (root.matrix_world.to_3x3() @ n_local).normalized()
        rows = verify_depth(scene, cc, dep,
                            [("reel hub", hub),
                             ("panel centre", ctr)])
        print("  DEPTH VERIFY (close)")
        for n, want, got, err in rows:
            print("    %-18s want %.5f  got %.5f  err %+.5f"
                  % (n, want, got, err))

        export_glb(reel, os.path.join(CLOSE, "prop.glb"))
        render_probe(scene, hub, os.path.join(CLOSE, "env.bin"),
                     hide=list(cap) + list(reel))

        for deg in REEL_GT_DEG:
            rot = (Matrix.Translation(hub)
                   @ Matrix.Rotation(math.radians(deg), 4, axis)
                   @ Matrix.Translation(-hub))
            saved = {o.name: o.matrix_world.copy() for o in reel}
            for o in reel:
                o.matrix_world = rot @ saved[o.name]
            bpy.context.view_layer.update()
            render_colour(scene, os.path.join(
                CLOSE, "gt_reel_%03d.png" % round(deg)), visible=reel)
            render_colour(scene, os.path.join(
                CLOSE, "gt_reel_full_%03d.png" % round(deg)),
                visible=plate + list(reel))
            for o in reel:
                o.matrix_world = saved[o.name]
            bpy.context.view_layer.update()

        px, py = mod.project(scene, cc, hub)
        j = {"render": {"w": W, "h": H},
             "camera": cam_json(scene, cc),
             "lights": lights_json(scene, close_tags),
             "world_bg": list(scene.world.node_tree.nodes["Background"]
                              .inputs[0].default_value),
             "colour": {"view_transform": scene.view_settings.view_transform,
                        "look": scene.view_settings.look,
                        "exposure": scene.view_settings.exposure},
             "light_gain": 0.55,
             "env_intensity": 0.0,   # measured: the probe does not help, see
                                     # check/measurements.txt
             "env": {"file": "env.bin", "format": "float32-le RGB",
                     "w": PROBE_W, "h": PROBE_H,
                     "mapping": "EquirectangularReflectionMapping, row 0 = v0",
                     "origin": to3(hub)},
             "depth": {"file": "depth.bin", "format": "float32-le",
                       "meaning": "linear view depth in metres along -Z_cam",
                       "background": 1e10},
             "prop": {"glb": "prop.glb", "kind": "rotate",
                      "gt": [{"deg": d, "alone": "gt_reel_%03d.png" % round(d),
                              "full": "gt_reel_full_%03d.png" % round(d)}
                             for d in REEL_GT_DEG],
                      "label": ctrl["tape"]["label"],
                      "hub": to3(hub), "axis": to3(axis),
                      "pivot_px": {"x": px, "y": py},
                      "hotspot": mod.clamp_rect(
                          mod.bbox_rect(scene, cc, reel, pad=8), W, H),
                      "gt_deg": REEL_GT_DEG},
             "depth_verify": [{"name": n, "analytic": w, "baked": g, "err": e}
                              for n, w, g, e in rows]}
        with open(os.path.join(CLOSE, "scene.json"), "w") as f:
            json.dump(j, f, indent=1)
        with open(os.path.join(CLOSE, "materials.json"), "w") as f:
            json.dump(materials_json(), f, indent=1)

    print("TRANSLITERATE OK", code)


if __name__ == "__main__":
    main()
