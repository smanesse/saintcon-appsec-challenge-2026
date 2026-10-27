"""
SAINTCON 2026 — cockpit SHELL (architecture only, no props).

Semicircular cockpit, continuous horizontal window band, interior pillars that
stand IN FRONT of the glass (so the glass is never broken), overhead hanging
consoles, and a raked ground-level dashboard.

Everything is driven by PARAMS below. Run:
    blender --background --python shell.py -- [variant=NAME] [key=value ...]
"""
import bpy, bmesh, math, sys, os, json

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders")

PARAMS = {
    # --- room shell -------------------------------------------------------
    "radius":          2.95,  # semicircle radius
    "ceiling":         2.26,  # floor -> ceiling
    "arc_start":     -115.0,  # degrees; the curved wall spans start..end
    "arc_end":        115.0,  # >180 total, so there is room behind the pilot

    # --- window band ------------------------------------------------------
    "win_bottom":      0.92,
    "win_top":         1.90,
    "win_arc_start":  -78.0,  # glass spans a little less than the wall
    "win_arc_end":     78.0,

    # --- pillars (in front of the glass, holding the ceiling) -------------
    "pillar_count":       2,  # 2 pillars => window reads as 3 panes
    "pillar_radius":   0.075, # column radius
    "pillar_inset":    0.38,  # metres INSIDE the glass (toward pilot)
    "pillar_spread":   27.0,  # +/- degrees from centre

    # --- dashboard (rakes down & back from the window sill) --------------
    # Dash is set by explicit heights; the rake angle falls out of them.
    # dash_top_z may sit ABOVE the sill (a binnacle standing proud of the glass,
    # occluding its lowest sliver) — that's what buys a tall front AND a rake.
    "dash_top_z":      1.06,  # far edge, at the window
    "dash_near_z":     0.78,  # near edge = top of the front fascia
    "dash_run":        0.62,  # radial run of the raked face
    "dash_arc_start": -82.0,
    "dash_arc_end":    82.0,

    # --- overhead hanging consoles ---------------------------------------
    "oh_drop":         0.44,  # how far below ceiling they hang
    "oh_radius_frac":  0.72,  # how far out from centre they hang

    # --- camera (pilot POV) ----------------------------------------------
    "eye_height":      1.30,
    "eye_y":          -0.10,  # back far enough to see dash+band+overheads
    "lens":            18.0,  # wide, for the wraparound cockpit feel
    "pitch":           -3.2,  # degrees; slight downward look

    # --- render -----------------------------------------------------------
    "res_x":           1280,
    "res_y":            720,
    "samples":           32,
    "pixel":              1,  # >1 renders at 1/N and hard-disables AA, for the
                              # "render low, upscale hard" pixelated register
    "glass":              0,  # 0 = leave the window as a hole (alpha)
    "exterior":           0,  # 0 = transparent film (production plate)
                              # 1 = draw stars/planet, opaque (preview only)
    "raytrace":           1,  # 1 = EEVEE screen-space raytracing (reflections
                              # in metal). Blender 5.2 ships this OFF, which is
                              # why the plates used to have no environment
                              # response and brass rendered as flat gold paint.
                              # Measured on 2026-09-02: +10.8% highlight pixels,
                              # brass specular (35,29,14) -> (185,136,57), and
                              # NO measurable render-time cost. Set 0 to revert.
    "texture":            1,  # 1 = procedural roughness/bump on the shell
                              # materials; 0 = the old flat BSDFs (A/B only)
}

# Env override so an A/B can flip raytracing for EVERY downstream consumer
# (combine.py and all nine modules/<CODE>/build.py, which each start from
# `dict(shell.PARAMS)`) without editing ten files.
PARAMS["raytrace"] = int(os.environ.get("CKPT_RAYTRACE", PARAMS["raytrace"]))

SEG = 96  # arc tesselation

# Global gate for the procedural surface pass. `build()` sets it from
# PARAMS["texture"], and it stays set afterwards so materials created LATER by
# the hero modules and the dressing tiers (all of which route through
# `material()`) get the same treatment as the shell itself.
AUTO_TEXTURE = True

# Overhead rig. Deliberately irregular: no mirrored pairs, no even spacing,
# mixed kinds and drops, so the ceiling reads as accreted equipment rather
# than a symmetric showroom. Angles are degrees off the centreline.
OVERHEADS = [
    {"kind": "console", "angle": -52, "r": 0.88, "w": 0.62, "d": 0.34,
     "h": 0.20, "drop": 0.30, "stalks": (-0.22, 0.24)},
    {"kind": "pod",     "angle": -29, "r": 0.72, "w": 0.20, "d": 0.20,
     "h": 0.24, "drop": 0.22, "stalks": (0.0,)},
    {"kind": "console", "angle":  -7, "r": 0.92, "w": 0.86, "d": 0.36,
     "h": 0.17, "drop": 0.40, "stalks": (-0.34, -0.02, 0.36)},
    {"kind": "console", "angle":  24, "r": 0.78, "w": 0.44, "d": 0.28,
     "h": 0.23, "drop": 0.26, "stalks": (-0.15, 0.17)},
    # one deliberate low-hanger, off-centre, as an accent
    {"kind": "lamp",    "angle":  47, "r": 0.62, "w": 0.20, "d": 0.20,
     "h": 0.15, "drop": 0.50, "stalks": (0.0,)},
    {"kind": "pod",     "angle":  68, "r": 0.94, "w": 0.16, "d": 0.16,
     "h": 0.19, "drop": 0.34, "stalks": (0.0,)},
]


# ---------------------------------------------------------------- utilities
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def set_in(bsdf, name, value):
    """Set a Principled input if this Blender version has it under that name."""
    if name in bsdf.inputs:
        bsdf.inputs[name].default_value = value
        return True
    return False


def material(name, base=(0.5, 0.5, 0.5, 1), metallic=0.0, rough=0.5,
             emission=None, emit_strength=0.0, transmission=0.0, alpha=1.0,
             texture="auto"):
    """Create a Principled material.

    `texture` controls the procedural surface pass added after this file was
    first written (see `texturize`):
      "auto"  -- the default. Every opaque, non-emissive material picks up a
                 light shared roughness/bump break-up, so a prop face is never
                 perfectly uniform. Emissive, transmissive and semi-transparent
                 materials (lamps, lenses, glass, glow masks) are skipped:
                 roughness detail does nothing for them and bump would only
                 stipple a lit lens.
      False   -- leave it flat. Used by `build()` for the four shell materials,
                 which then get their own individually tuned `texturize()`.
    Albedo is never touched by any of this.
    """
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    set_in(b, "Base Color", base)
    set_in(b, "Metallic", metallic)
    set_in(b, "Roughness", rough)
    if emission is not None:
        set_in(b, "Emission Color", emission)
        set_in(b, "Emission Strength", emit_strength)
    if transmission:
        # 4.x renamed "Transmission" -> "Transmission Weight"
        if not set_in(b, "Transmission Weight", transmission):
            set_in(b, "Transmission", transmission)
    if alpha < 1.0:
        set_in(b, "Alpha", alpha)
        # EEVEE Next replaced blend_method with surface_render_method
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = 'BLENDED'
        elif hasattr(m, "blend_method"):
            m.blend_method = 'BLEND'
    if (texture == "auto" and AUTO_TEXTURE and not transmission
            and alpha >= 1.0 and not emit_strength):
        # Deliberately weaker than the shell's own surfaces: props are small and
        # already carry silhouette detail, so this only needs to stop a 200 px
        # panel ground from being one flat value.
        texturize(m, mode="arc", detail_amt=0.081, detail_scale=88.0,
                  along=0.18, mottle_amt=0.054, mottle_scale=2.6,
                  bump_amt=0.09, bump_dist=0.0022)
    return m


# ------------------------------------------------------- procedural texture
# The single biggest "this is CG" tell in the plate was uniform roughness over
# very large smooth areas -- the dash, the ceiling, the hull bands.  These
# helpers break that up procedurally.
#
# THREE RULES, and they are not negotiable:
#   1. Roughness and Normal ONLY.  Base colour is never touched: the saturation
#      budget (DRESSING_PLAN 5.4, dressing/satcheck*.py) is measured on screen
#      saturation/value and passes with under 10% headroom.
#   2. No UVs, no image maps.  Everything is driven from WORLD position
#      (Geometry > Position) or object space, so it works on every mesh with no
#      per-object setup -- and neighbouring parts share ONE continuous field,
#      which is what makes it read as "the same machine brushed this panel"
#      rather than as per-object noise.
#   3. No geometry changes.  Bump only; never displacement.
#
# Modes:
#   "arc"    cylindrical frame about the room axis -> streaks that run ALONG
#            the arc.  On the wall bands that is horizontal brushing; on the
#            raked dash it is brushing that follows the curve of the coaming.
#   "iso"    plain world-space, no direction -- for cast/painted surfaces
#            (floor, ceiling, beams) that were never brushed.
#   "axial"  object space squashed in Z -> vertical streaks up a column shaft.
def _mk(nt, kind, x, y):
    n = nt.nodes.new(kind)
    n.location = (x, y)
    return n


def _tex_value(nt, v, x, y):
    n = _mk(nt, 'ShaderNodeValue', x, y)
    n.outputs[0].default_value = v
    return n.outputs[0]


def _tex_worldpos(nt, x=-1900, y=0):
    return _mk(nt, 'ShaderNodeNewGeometry', x, y).outputs['Position']


def _tex_cyl(nt, pos, along, x=-1700, y=0):
    """World position -> (angle * along, z, radius).

    `along` under 1 stretches the noise around the arc; the smaller it is the
    longer the streaks run.  Radius rides in Z so a raked surface (where r and
    z covary) still gets variation across its run.
    """
    sep = _mk(nt, 'ShaderNodeSeparateXYZ', x, y)
    nt.links.new(pos, sep.inputs[0])
    ang = _mk(nt, 'ShaderNodeMath', x + 180, y + 170)
    ang.operation = 'ARCTAN2'
    nt.links.new(sep.outputs['X'], ang.inputs[0])
    nt.links.new(sep.outputs['Y'], ang.inputs[1])
    amul = _mk(nt, 'ShaderNodeMath', x + 360, y + 170)
    amul.operation = 'MULTIPLY'
    amul.inputs[1].default_value = along
    nt.links.new(ang.outputs[0], amul.inputs[0])
    flat = _mk(nt, 'ShaderNodeVectorMath', x + 180, y - 190)
    flat.operation = 'MULTIPLY'
    flat.inputs[1].default_value = (1.0, 1.0, 0.0)
    nt.links.new(pos, flat.inputs[0])
    rad = _mk(nt, 'ShaderNodeVectorMath', x + 360, y - 190)
    rad.operation = 'LENGTH'
    nt.links.new(flat.outputs['Vector'], rad.inputs[0])
    comb = _mk(nt, 'ShaderNodeCombineXYZ', x + 540, y)
    nt.links.new(amul.outputs[0], comb.inputs['X'])
    nt.links.new(sep.outputs['Z'], comb.inputs['Y'])
    nt.links.new(rad.outputs['Value'], comb.inputs['Z'])
    return comb.outputs['Vector']


def _tex_noise(nt, vec, scale, detail, rough, x, y):
    n = _mk(nt, 'ShaderNodeTexNoise', x, y)
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    if 'Roughness' in n.inputs:
        n.inputs['Roughness'].default_value = rough
    if vec is not None:
        nt.links.new(vec, n.inputs['Vector'])
    return n.outputs['Fac']


def _tex_remap(nt, fac, lo, hi, x, y, fmin=0.20, fmax=0.80):
    """Noise Fac (bunched around 0.5) -> a signed roughness offset."""
    mr = _mk(nt, 'ShaderNodeMapRange', x, y)
    mr.inputs['From Min'].default_value = fmin
    mr.inputs['From Max'].default_value = fmax
    mr.inputs['To Min'].default_value = lo
    mr.inputs['To Max'].default_value = hi
    nt.links.new(fac, mr.inputs['Value'])
    return mr.outputs['Result']


def _tex_add(nt, a, b, x, y, clamp=False):
    m = _mk(nt, 'ShaderNodeMath', x, y)
    m.operation = 'ADD'
    m.use_clamp = clamp
    nt.links.new(a, m.inputs[0])
    nt.links.new(b, m.inputs[1])
    return m.outputs[0]


def texturize(mat, mode="arc", detail_amt=0.07, detail_scale=58.0,
              detail_detail=2.0, along=0.22,
              mottle_amt=0.05, mottle_scale=1.7,
              grime_amt=0.0, grime_z=0.34,
              bump_amt=0.10, bump_dist=0.0035):
    """Break up a flat Principled material's roughness (and, faintly, its
    normal) with procedural noise.  Returns `mat` so calls can be chained.

    Roughness ends up base +/- (detail_amt + mottle_amt), clamped to 0..1, with
    an optional `grime_amt` lift that fades out above `grime_z` metres so dust
    reads as having settled where surfaces meet the floor.
    """
    if not mat.use_nodes:
        return mat
    nt = mat.node_tree
    b = nt.nodes.get("Principled BSDF")
    if b is None:
        b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if b is None or "Roughness" not in b.inputs:
        return mat
    r0 = b.inputs["Roughness"].default_value

    pos = _tex_worldpos(nt)
    if mode == "arc":
        dvec = _tex_cyl(nt, pos, along)
    elif mode == "axial":
        tc = _mk(nt, 'ShaderNodeTexCoord', -1700, -520)
        mp = _mk(nt, 'ShaderNodeMapping', -1500, -520)
        mp.inputs['Scale'].default_value = (1.0, 1.0, along)
        nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
        dvec = mp.outputs['Vector']
    else:
        dvec = pos

    det = _tex_noise(nt, dvec, detail_scale, detail_detail, 0.5, -1000, 300)
    acc = _tex_value(nt, r0, -1000, 560)
    if detail_amt:
        acc = _tex_add(nt, acc,
                       _tex_remap(nt, det, -detail_amt, detail_amt, -800, 300),
                       -580, 460)
    if mottle_amt:
        mot = _tex_noise(nt, pos, mottle_scale, 3.0, 0.55, -1000, 20)
        acc = _tex_add(nt, acc,
                       _tex_remap(nt, mot, -mottle_amt, mottle_amt, -800, 20),
                       -400, 380)
    if grime_amt:
        sep = _mk(nt, 'ShaderNodeSeparateXYZ', -1000, -240)
        nt.links.new(pos, sep.inputs[0])
        gz = _mk(nt, 'ShaderNodeMapRange', -800, -240)
        gz.inputs['From Min'].default_value = 0.02
        gz.inputs['From Max'].default_value = grime_z
        gz.inputs['To Min'].default_value = grime_amt
        gz.inputs['To Max'].default_value = 0.0
        nt.links.new(sep.outputs['Z'], gz.inputs['Value'])
        acc = _tex_add(nt, acc, gz.outputs['Result'], -220, 300)

    clamp = _mk(nt, 'ShaderNodeClamp', -60, 300)
    clamp.inputs['Min'].default_value = 0.03
    clamp.inputs['Max'].default_value = 1.0
    nt.links.new(acc, clamp.inputs['Value'])
    nt.links.new(clamp.outputs[0], b.inputs["Roughness"])

    if bump_amt and "Normal" in b.inputs:
        bn = _mk(nt, 'ShaderNodeBump', -220, -520)
        bn.inputs['Strength'].default_value = bump_amt
        bn.inputs['Distance'].default_value = bump_dist
        nt.links.new(det, bn.inputs['Height'])
        nt.links.new(bn.outputs['Normal'], b.inputs["Normal"])
    return mat


def mesh_from(name, verts, faces, mat=None, shade_smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if mat:
        ob.data.materials.append(mat)
    if shade_smooth:
        for p in ob.data.polygons:
            p.use_smooth = True
    return ob


def arc_band(name, r0, z0, r1, z1, a0, a1, mat, segments=SEG, smooth=True):
    """A surface swept along an arc between two (radius, height) rails."""
    verts, faces = [], []
    for i in range(segments + 1):
        t = i / segments
        a = math.radians(a0 + (a1 - a0) * t)
        s, c = math.sin(a), math.cos(a)
        verts.append((r0 * s, r0 * c, z0))
        verts.append((r1 * s, r1 * c, z1))
    for i in range(segments):
        b = i * 2
        faces.append((b, b + 2, b + 3, b + 1))
    return mesh_from(name, verts, faces, mat, smooth)


def half_disc(name, radius, z, a0, a1, mat, segments=SEG):
    verts = [(0.0, 0.0, z)]
    for i in range(segments + 1):
        a = math.radians(a0 + (a1 - a0) * i / segments)
        verts.append((radius * math.sin(a), radius * math.cos(a), z))
    faces = [(0, i + 1, i + 2) for i in range(segments)]
    return mesh_from(name, verts, faces, mat)


def box(name, center, size, mat, rot_z=0.0, bevel=0.012):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    ob = bpy.context.object
    ob.name = name
    ob.scale = size
    ob.rotation_euler = (0, 0, rot_z)
    if bevel:
        m = ob.modifiers.new("bev", 'BEVEL')
        m.width, m.segments = bevel, 2
    ob.data.materials.append(mat)
    return ob


# ---------------------------------------------------------------- the build
def build(P):
    reset()
    scene = bpy.context.scene

    R = P["radius"]
    CEIL = P["ceiling"]
    A0, A1 = P["arc_start"], P["arc_end"]

    global AUTO_TEXTURE
    AUTO_TEXTURE = bool(P.get("texture", 1))

    # texture=False on these four: they are the largest surfaces in frame and
    # get their own tuned treatment below, not the generic prop one.
    hull   = material("hull",   (0.052, 0.056, 0.066, 1), 0.15, 0.48,
                      texture=False)
    hull_d = material("hull_d", (0.030, 0.033, 0.040, 1), 0.10, 0.62,
                      texture=False)
    brass  = material("brass",  (0.62, 0.44, 0.13, 1),    1.00, 0.30,
                      texture=False)
    glass  = material("glass",  (0.55, 0.72, 0.85, 1),    0.00, 0.05,
                      transmission=1.0, alpha=0.12)
    bulb   = material("bulb",   (1.0, 0.92, 0.72, 1), 0.0, 0.4,
                      emission=(1.0, 0.86, 0.60, 1), emit_strength=18.0)
    cove   = material("cove",   (1.0, 0.85, 0.6, 1), 0.0, 0.5,
                      emission=(1.0, 0.80, 0.52, 1), emit_strength=5.5)
    # Column shafts get their OWN material purely so they can be brushed
    # vertically instead of around the arc.  Identical albedo/metallic/rough to
    # `hull` -- this is a texture split, not a colour split.
    hull_c = material("hull_c", (0.052, 0.056, 0.066, 1), 0.15, 0.48,
                      texture=False)

    # Procedural surface detail.  Roughness first (uniform roughness is the
    # loudest CG tell), bump a distant second.  See texturize() above.
    # Amplitudes were picked by rendering a 1x / 1.8x / 2.6x sweep of this shell
    # and reading it at 2x zoom: 1x was invisible on the plate, 2.6x made the
    # fascia look hammered and the ceiling look grainy.  These are the 1.8x set.
    if P.get("texture", 1):
        # Rolled/brushed sheet: dash faces, riser, fascia, hull bands, the
        # overhead consoles, and every hero/dressing panel ground that borrows
        # mats["hull"].  Streaks follow the arc; grime settles at the kick.
        texturize(hull, mode="arc", detail_amt=0.135, detail_scale=58.0,
                  along=0.22, mottle_amt=0.090, mottle_scale=1.7,
                  grime_amt=0.050, grime_z=0.34,
                  bump_amt=0.18, bump_dist=0.0063)
        # Cast/painted structure: floor, ceiling, backwall, beams, ribs, kick,
        # stalks.  No brushing -- fine speckle plus a slow mottle.
        texturize(hull_d, mode="iso", detail_amt=0.099, detail_scale=62.0,
                  detail_detail=3.0, mottle_amt=0.117, mottle_scale=2.3,
                  grime_amt=0.045, grime_z=0.30,
                  bump_amt=0.16, bump_dist=0.0054)
        # Polished brass: just enough to stop the sill/header/lip reading as a
        # perfect chrome line.  Buffed, NOT corroded -- keep these small.
        texturize(brass, mode="arc", detail_amt=0.099, detail_scale=92.0,
                  along=0.16, mottle_amt=0.063, mottle_scale=3.2,
                  bump_amt=0.09, bump_dist=0.0027)
        # Column shafts: vertical brushing.
        texturize(hull_c, mode="axial", detail_amt=0.144, detail_scale=42.0,
                  along=0.020, mottle_amt=0.072, mottle_scale=2.0,
                  grime_amt=0.045, grime_z=0.28,
                  bump_amt=0.18, bump_dist=0.0054)

    # --- floor / ceiling / back wall
    half_disc("floor",   R, 0.0,  A0, A1, hull_d)
    half_disc("ceiling", R, CEIL, A0, A1, hull_d)
    arc_band("wall_lower", R, 0.0, R, P["win_bottom"], A0, A1, hull)
    arc_band("wall_upper", R, P["win_top"], R, CEIL,   A0, A1, hull)

    # back wall (the chord of the half circle)
    x0 = R * math.sin(math.radians(A0))
    y0 = R * math.cos(math.radians(A0))
    x1 = R * math.sin(math.radians(A1))
    y1 = R * math.cos(math.radians(A1))
    mesh_from("backwall",
              [(x0, y0, 0), (x1, y1, 0), (x1, y1, CEIL), (x0, y0, CEIL)],
              [(0, 1, 2, 3)], hull_d)

    # --- window glass: ONE continuous band, never broken by structure
    if P["glass"]:
        arc_band("glass", R, P["win_bottom"], R, P["win_top"],
                 P["win_arc_start"], P["win_arc_end"], glass)

    # sill + header trim
    arc_band("sill",   R, P["win_bottom"], R - 0.07, P["win_bottom"] - 0.03,
             A0, A1, brass)
    arc_band("header", R, P["win_top"],    R - 0.07, P["win_top"] + 0.03,
             A0, A1, brass)

    # --- ceiling cove light (soft practical illumination)
    arc_band("cove", R - 0.10, CEIL - 0.05, R - 0.26, CEIL - 0.05, A0, A1, cove)

    # --- pillars: INSIDE the glass, floor to ceiling, reading as structure
    pr = R - P["pillar_inset"]
    n = P["pillar_count"]
    if n == 1:
        angles = [0.0]
    else:
        angles = [-P["pillar_spread"] + 2 * P["pillar_spread"] * i / (n - 1)
                  for i in range(n)]
    prad = P["pillar_radius"]
    for i, a in enumerate(angles):
        rad = math.radians(a)
        px, py = pr * math.sin(rad), pr * math.cos(rad)
        # the column shaft
        bpy.ops.mesh.primitive_cylinder_add(radius=prad, depth=CEIL, vertices=48,
                                            location=(px, py, CEIL / 2))
        col = bpy.context.object
        col.name = f"column_{i}"
        col.data.materials.append(hull_c)
        for f in col.data.polygons:
            f.use_smooth = True
        # brass collars top and bottom so it reads as a structural column
        for ci, (cz, ch) in enumerate(((0.10, 0.085), (CEIL - 0.10, 0.085),
                                       (0.30, 0.04), (CEIL - 0.30, 0.04))):
            bpy.ops.mesh.primitive_cylinder_add(
                radius=prad * 1.34, depth=ch, vertices=48,
                location=(px, py, cz))
            c = bpy.context.object
            c.name = f"column_{i}_collar_{ci}"
            c.data.materials.append(brass)
            b = c.modifiers.new("bev", 'BEVEL')
            b.width, b.segments = 0.008, 2

    # --- dashboard: rakes down and back from the window sill
    da0, da1 = P["dash_arc_start"], P["dash_arc_end"]
    run = P["dash_run"]
    top_z, near_z = P["dash_top_z"], P["dash_near_z"]
    dash_r = R - run
    rake = math.degrees(math.atan2(top_z - near_z, run))
    print(f"NOTE: dash rake {rake:.1f} deg from horizontal; "
          f"front fascia {near_z:.2f} m tall")
    # 1. binnacle riser: from the sill up to the dash's far edge
    if top_z > P["win_bottom"]:
        arc_band("dash_riser", R - 0.03, P["win_bottom"], R - 0.05, top_z,
                 da0, da1, hull)
    # 2. the raked working surface the instruments sit on
    arc_band("dash_face", R - 0.05, top_z, dash_r, near_z, da0, da1, hull)
    # 3. brass lip along the near edge
    arc_band("dash_lip", dash_r + 0.015, near_z + 0.012,
             dash_r - 0.030, near_z - 0.025, da0, da1, brass)
    # 4. tall vertical front, kicked back at the bottom for toe room
    arc_band("dash_fascia", dash_r - 0.025, near_z - 0.025,
             dash_r - 0.025, 0.14, da0, da1, hull)
    arc_band("dash_kick", dash_r - 0.025, 0.14, dash_r + 0.12, 0.0,
             da0, da1, hull_d)

    # --- ceiling context: radial beams + circumferential ribs
    for i, ang in enumerate((-84, -46, -14, 22, 58, 92)):
        a = math.radians(ang)
        r0, r1 = 0.30 * R, 1.00 * R
        rm = (r0 + r1) / 2
        box(f"ceil_beam_{i}", (rm * math.sin(a), rm * math.cos(a), CEIL - 0.055),
            (0.105, r1 - r0, 0.085), hull_d, rot_z=-a, bevel=0.010)
    for i, frac in enumerate((0.46, 0.78)):
        arc_band(f"ceil_rib_{i}", R * frac, CEIL - 0.02,
                 R * frac - 0.085, CEIL - 0.085, A0, A1, hull_d)

    # --- overhead rig: deliberately irregular, no mirrored pairs
    for i, it in enumerate(OVERHEADS):
        a = math.radians(it["angle"])
        rr = R * it["r"]
        px, py = rr * math.sin(a), rr * math.cos(a)
        drop, h = it["drop"], it["h"]
        zc = CEIL - drop - h / 2
        if it["kind"] == "console":
            box(f"oh_{i}", (px, py, zc), (it["w"], it["d"], h), hull,
                rot_z=-a, bevel=0.014)
            # brass reader strip on the front face
            box(f"oh_{i}_strip",
                (px - (it["d"] / 2 + 0.012) * math.cos(a),
                 py + (it["d"] / 2 + 0.012) * math.sin(a), zc - h * 0.16),
                (it["w"] * 0.86, 0.02, h * 0.26), brass, rot_z=-a, bevel=0.004)
        elif it["kind"] == "pod":
            bpy.ops.mesh.primitive_cylinder_add(
                radius=it["w"] / 2, depth=h, vertices=32, location=(px, py, zc))
            o = bpy.context.object
            o.name = f"oh_{i}"
            o.data.materials.append(hull)
            for f_ in o.data.polygons:
                f_.use_smooth = True
            bpy.ops.mesh.primitive_cylinder_add(
                radius=it["w"] / 2 * 1.18, depth=0.035, vertices=32,
                location=(px, py, zc + h / 2 - 0.02))
            c = bpy.context.object
            c.name = f"oh_{i}_collar"
            c.data.materials.append(brass)
        elif it["kind"] == "lamp":
            bpy.ops.mesh.primitive_cone_add(
                radius1=it["w"] / 2, radius2=it["w"] / 6, depth=h,
                vertices=28, location=(px, py, zc))
            o = bpy.context.object
            o.name = f"oh_{i}"
            o.data.materials.append(brass)
            for f_ in o.data.polygons:
                f_.use_smooth = True
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=it["w"] * 0.20, segments=20, ring_count=12,
                location=(px, py, zc - h / 2 + 0.02))
            g = bpy.context.object
            g.name = f"oh_{i}_bulb"
            g.data.materials.append(bulb)
        # hangers: irregular count, so nothing reads as a mirrored pair
        for si, sx in enumerate(it["stalks"]):
            box(f"oh_{i}_stalk_{si}",
                (px + sx * math.cos(a), py - sx * math.sin(a),
                 CEIL - drop / 2),
                (0.040, 0.040, drop), hull_d, rot_z=-a, bevel=0.006)

    # --- exterior.
    # Production plate: transparent film + no exterior geometry, so the window
    # is a genuine alpha hole and the WebGL starfield shows through from behind.
    # Preview mode fills it in only so the shell can be judged in isolation.
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.008, 0.012, 0.03, 1)
    bg.inputs[1].default_value = 1.0
    scene.world = world

    if not P["exterior"]:
        scene.render.film_transparent = True
    else:
        planet_m = material("planet", (0.45, 0.30, 0.16, 1), 0.0, 0.75,
                            emission=(0.55, 0.34, 0.16, 1), emit_strength=0.6)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=9.0, location=(14, 34, 3),
                                             segments=48, ring_count=24)
        bpy.context.object.name = "planet"
        bpy.context.object.data.materials.append(planet_m)
        for f_ in bpy.context.object.data.polygons:
            f_.use_smooth = True

        star_m = material("star", (1, 1, 1, 1), 0.0, 0.5,
                          emission=(0.85, 0.92, 1.0, 1), emit_strength=22.0)
        import random
        random.seed(7)
        for _ in range(90):
            a = random.uniform(-1.5, 1.5)
            h = random.uniform(-6, 14)
            d = random.uniform(28, 46)
            bpy.ops.mesh.primitive_ico_sphere_add(
                radius=random.uniform(0.03, 0.10), subdivisions=1,
                location=(d * math.sin(a), d * math.cos(a), h))
            bpy.context.object.data.materials.append(star_m)

    # --- interior lighting
    for loc, energy, size, color, rot in [
        ((0.0,  1.2, CEIL - 0.12), 70, 2.4, (1.0, 0.87, 0.68), (0, 0, 0)),
        ((-1.7, 0.0, CEIL - 0.12), 40, 1.8, (1.0, 0.82, 0.60), (0, 0, 0)),
        ((1.7,  0.0, CEIL - 0.12), 40, 1.8, (1.0, 0.82, 0.60), (0, 0, 0)),
        ((0.0, -1.0, CEIL - 0.12), 34, 2.0, (1.0, 0.84, 0.62), (0, 0, 0)),
        # cool fill washing back off the window, toward the pilot
        ((0.0,  2.5, 1.45), 52, 2.4, (0.60, 0.76, 1.0),
         (math.radians(-90), 0, 0)),
        # low fill so the dash face and fascia aren't crushed to black
        ((0.0, 0.55, 1.02), 26, 1.8, (1.0, 0.88, 0.72),
         (math.radians(62), 0, 0)),
        # uplight so the ceiling beams and ribs read instead of going black
        ((0.0, 0.30, 1.30), 34, 2.6, (1.0, 0.86, 0.66),
         (math.radians(180), 0, 0)),
    ]:
        bpy.ops.object.light_add(type='AREA', location=loc)
        L = bpy.context.object
        L.data.energy, L.data.size = energy, size
        L.data.color = color
        L.rotation_euler = rot

    # --- camera: pilot POV
    bpy.ops.object.camera_add(location=(0.0, P["eye_y"], P["eye_height"]))
    cam = bpy.context.object
    cam.data.lens = P["lens"]
    cam.rotation_euler = (math.radians(90 + P["pitch"]), 0, 0)
    scene.camera = cam

    # --- render settings
    scene.render.engine = 'BLENDER_EEVEE'
    px = max(1, int(P["pixel"]))
    scene.render.resolution_x = max(1, P["res_x"] // px)
    scene.render.resolution_y = max(1, P["res_y"] // px)
    # Hard pixel edges come from a tiny reconstruction filter, NOT from low
    # sample counts -- 1 sample just makes it noisy. And 8-bit output dither
    # (default 1.0) is invisible at full res but shreds a 320x180 plate.
    scene.render.filter_size = 0.01 if px > 1 else 1.5
    scene.render.dither_intensity = 0.0 if px > 1 else 1.0
    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = P["samples"]
        if P.get("raytrace") and hasattr(scene.eevee, "use_raytracing"):
            scene.eevee.use_raytracing = True
            rt = getattr(scene.eevee, "ray_tracing_options", None)
            if rt is not None:
                # Default is '2' = half-resolution tracing. These are stills,
                # not a realtime viewport; trace at full res. NB this is a
                # string enum ('1','2','4','8','16'), not an int.
                rt.resolution_scale = '1'
                rt.screen_trace_quality = 1.0
                # Default 0.5 stops tracing on anything rougher than half --
                # which is most of our painted metal. Trace all of it.
                rt.trace_max_roughness = 1.0
    scene.render.image_settings.file_format = 'PNG'
    return scene


def render(P, name):
    build(P)
    path = os.path.join(OUT, f"{name}.png")
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("WROTE", path)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = "shell"
    for a in argv:
        if "=" in a:
            k, v = a.split("=", 1)
            if k == "variant":
                name = v
            elif k in PARAMS:
                PARAMS[k] = type(PARAMS[k])(float(v)) if not isinstance(
                    PARAMS[k], int) else int(float(v))
    render(PARAMS, name)
