"""
Set-dressing PART KIT  (Tier 0 of DRESSING_PLAN.md).

The shared, parametric, reusable pieces every dressing prop is assembled from.
`lampcell`, `gauge` and `toggle` alone account for 73 of the ~160 discrete parts
in the plan, so everything downstream should be *arrangement*, not modelling.

Conventions
-----------
* Every part builder works in the `slots.py` PANEL frame:
  local +X right, +Y up, +Z out of the surface toward the pilot.
  Parts are authored around a `pos=(x, y, z)` anchor; z is the surface plane
  (usually 0.0) and parts grow toward +Z.
* Every part builder returns a **list of objects**. Callers parent them to
  whatever empty they placed with `slots.*` / `slots_ext.*`.
* A handful of builders (`conduit_arc`, `sweep`) work in WORLD space instead,
  because arcs that follow the hull are not panel-local. They say so.
* Every object and material is prefixed `dr_`.
* NEVER put a float in an object name -- Blender parses `.NNN` as a duplicate
  suffix and hard-crashes. Indices only.

What is in here
---------------
materials   mat(key)  lamp_mat(kind, lit)   -- keys in MAT_SPEC, plus the two
            node-built ones "glass" and "fluid"
primitives  box cyl cone sphere disc tube revolve sweep bundle path_frames text
fixings     hexbolt screw rivet_row bez_frame pclip tape_wrap louvre_row grille
            cage
the big 3   gauge  toggle  lampcell        (73 of the plan's ~160 parts)
signage     stencil nameplate warn_triangle arrow inspection_stamp
mechanisms  breaker sightglass vactube flipdigit mimic_strip
hull-follow wrap_collar conduit_arc conduit_tee gland loom
plumbing    parent_to frame_empty emissive_area

Materials follow DRESSING_PLAN.md section 5 exactly: same hue as the heroes,
saturation x0.75, value x0.65, roughness +0.16, metallic KEPT HIGH.
"""
import bpy
import os
import math
import sys

from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import shell                                                     # noqa: E402


# ============================================================== materials
# DRESSING_PLAN section 5.1.  Hero values are in the comments for comparison.
MAT_SPEC = {
    #  name        base rgb                      metal rough  emission  str
    "brass":     ((0.400, 0.320, 0.160), 0.85, 0.46, None, 0.0),
    "brass_dk":  ((0.250, 0.198, 0.098), 0.85, 0.56, None, 0.0),
    "steel":     ((0.215, 0.228, 0.245), 0.85, 0.48, None, 0.0),
    "hull_l":    ((0.062, 0.066, 0.077), 0.15, 0.52, None, 0.0),
    "slate":     ((0.085, 0.090, 0.100), 0.14, 0.60, None, 0.0),
    "paint":     ((0.098, 0.100, 0.104), 0.20, 0.58, None, 0.0),
    "case":      ((0.042, 0.045, 0.052), 0.10, 0.55, None, 0.0),
    "ebonite":   ((0.030, 0.030, 0.034), 0.00, 0.44, None, 0.0),
    "ivory":     ((0.720, 0.700, 0.640), 0.00, 0.72, None, 0.0),
    "paper":     ((0.735, 0.715, 0.645), 0.00, 0.84, None, 0.0),
    "ink":       ((0.055, 0.050, 0.052), 0.00, 0.62, None, 0.0),
    "rubber":    ((0.030, 0.030, 0.032), 0.00, 0.88, None, 0.0),
    "braid":     ((0.062, 0.058, 0.050), 0.00, 0.94, None, 0.0),
    "tape":      ((0.045, 0.043, 0.040), 0.00, 0.92, None, 0.0),
    "wood":      ((0.180, 0.115, 0.058), 0.00, 0.66, None, 0.0),
    # rationed: three unlit painted-red elements in the WHOLE dressing set
    # (F6 bottle, F2 SEAL handle, F1 PURGE guard). Do not spend these lightly.
    "red_paint": ((0.340, 0.075, 0.060), 0.00, 0.55, None, 0.0),
    # lamps -- OFF is x0.60 of hero OFF; ON is ~1/3 hero emission strength
    "amber_off": ((0.138, 0.090, 0.030), 0.00, 0.46, None, 0.0),
    "amber_on":  ((0.600, 0.440, 0.180), 0.00, 0.40,
                  (0.85, 0.62, 0.30), 1.90),
    "green_off": ((0.042, 0.090, 0.055), 0.00, 0.46, None, 0.0),
    "green_on":  ((0.300, 0.560, 0.360), 0.00, 0.40,
                  (0.42, 0.78, 0.50), 1.70),
    "red_off":   ((0.120, 0.030, 0.032), 0.00, 0.46, None, 0.0),
    "red_on":    ((0.560, 0.240, 0.180), 0.00, 0.42,
                  (0.80, 0.34, 0.26), 2.20),
    "white_off": ((0.190, 0.185, 0.170), 0.00, 0.50, None, 0.0),
    # flip-dot ink: readable amber, NOT emissive -- a dot matrix, not a screen
    "dot":       ((0.330, 0.215, 0.080), 0.00, 0.52, None, 0.0),
    # vacuum-tube filament: barely-there warm glow
    "filament":  ((0.320, 0.200, 0.100), 0.00, 0.50,
                  (0.80, 0.50, 0.24), 1.20),
}

LAMP_KINDS = ("amber", "green", "red", "white")


def mat(key):
    """Fetch (creating on first use) a dressing material by MAT_SPEC key.

    Idempotent across `shell.build()` calls, which wipe `bpy.data`.
    """
    name = "dr_" + key
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    if key == "glass":
        return shell.material(name, (0.62, 0.68, 0.72, 1), 0.0, 0.04,
                              transmission=0.92, alpha=0.055)
    if key == "fluid":
        # transmissive, NOT emissive (plan section 5.1)
        return shell.material(name, (0.30, 0.46, 0.42, 1), 0.0, 0.10,
                              transmission=0.85, alpha=0.55)
    base, metal, rough, em, st = MAT_SPEC[key]
    return shell.material(name, (base[0], base[1], base[2], 1), metal, rough,
                          emission=None if em is None else (em[0], em[1],
                                                            em[2], 1),
                          emit_strength=st)


def lamp_mat(kind, lit):
    """`kind` in LAMP_KINDS. Honours the 1-in-5 lit-lamp rule by being explicit."""
    if kind == "white":
        return mat("white_off") if not lit else mat("amber_on")
    return mat(f"{kind}_on" if lit else f"{kind}_off")


# ============================================================== primitives
def _finish(o, name, m, rot=(0, 0, 0), bevel=0.0, smooth=False):
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
    if m is not None:
        o.data.materials.append(m)
    return o


def box(name, center, size, m, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    o = bpy.context.object
    o.scale = size
    return _finish(o, name, m, rot, bevel)


def cyl(name, center, radius, depth, m, rot=(0, 0, 0), verts=24,
        smooth=True, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth,
                                        vertices=verts, location=center)
    return _finish(bpy.context.object, name, m, rot, bevel, smooth)


def cone(name, center, r0, r1, depth, m, rot=(0, 0, 0), verts=20, smooth=True):
    bpy.ops.mesh.primitive_cone_add(radius1=r0, radius2=r1, depth=depth,
                                    vertices=verts, location=center)
    return _finish(bpy.context.object, name, m, rot, False, smooth)


def sphere(name, center, radius, m, scale=(1, 1, 1), seg=18, ring=10,
           rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=seg,
                                         ring_count=ring, location=center)
    o = bpy.context.object
    o.scale = scale
    return _finish(o, name, m, rot, 0.0, True)


def disc(name, center, radius, m, rot=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_circle_add(radius=radius, vertices=verts,
                                      fill_type='NGON', location=center)
    return _finish(bpy.context.object, name, m, rot, 0.0, False)


def tube(name, center, r_out, r_in, depth, m, rot=(0, 0, 0), verts=40,
         smooth=True):
    """A box-section annulus built from pydata -- no boolean to fail.

    Default axis is local +Z. `rot=(pi/2,0,0)` lays it on its side, which is
    what a collar wrapping a vertical column wants in the panel frame.
    """
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
    o = shell.mesh_from(name, vs, faces, m, smooth)
    o.location = center
    o.rotation_euler = rot
    return o


def revolve(name, profile, m, center=(0, 0, 0), rot=(0, 0, 0), verts=28,
            smooth=True, cap=True):
    """Revolve a (radius, axial) profile about local +Z.

    `profile` is [(r, t), ...] ordered along the axis. This is the workhorse for
    cast fillets, flares, skirts, bottle bodies, ball tips and lamp cones --
    anything with a turned silhouette.
    """
    vs, fs = [], []
    n = len(profile)
    for i in range(verts):
        th = 2 * math.pi * i / verts
        c, s = math.cos(th), math.sin(th)
        for (r, t) in profile:
            vs.append((r * c, r * s, t))
    for i in range(verts):
        a, b = i * n, ((i + 1) % verts) * n
        for j in range(n - 1):
            fs.append((a + j, a + j + 1, b + j + 1, b + j))
    if cap:
        i0 = len(vs)
        vs.append((0.0, 0.0, profile[0][1]))
        i1 = len(vs)
        vs.append((0.0, 0.0, profile[-1][1]))
        for i in range(verts):
            a, b = i * n, ((i + 1) % verts) * n
            fs.append((i0, b, a))
            fs.append((i1, a + n - 1, b + n - 1))
    o = shell.mesh_from(name, vs, fs, m, smooth)
    o.location = center
    o.rotation_euler = rot
    return o


def path_frames(pts):
    """Parallel-transported (tangent, normal, binormal) frames along a polyline.

    Exposed because bundles, clips and tape wraps all need the same frames the
    sweep used, and recomputing them by hand is how a loom ends up twisting.
    """
    pts = [Vector(p) for p in pts]
    n = len(pts)
    if n < 2:
        raise ValueError("path_frames needs >= 2 points")
    tang = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        if t.length < 1e-9:
            t = Vector((0, 0, 1))
        tang.append(t.normalized())
    up = Vector((0, 0, 1))
    if abs(tang[0].dot(up)) > 0.92:
        up = Vector((0, 1, 0))
    nrm = (up - tang[0] * up.dot(tang[0])).normalized()
    frames = []
    for i in range(n):
        if i > 0:
            axis = tang[i - 1].cross(tang[i])
            if axis.length > 1e-9:
                ang = math.atan2(axis.length, tang[i - 1].dot(tang[i]))
                nrm = nrm.copy()
                nrm.rotate(Matrix.Rotation(ang, 3, axis.normalized()))
            nrm = (nrm - tang[i] * nrm.dot(tang[i]))
            if nrm.length < 1e-9:
                nrm = Vector((0, 0, 1))
            nrm = nrm.normalized()
        frames.append((tang[i].copy(), nrm.copy(),
                       tang[i].cross(nrm).normalized()))
    return pts, frames


def sweep(name, pts, radius, m, sections=8, radii=None, smooth=True,
          caps=True, offset=(0.0, 0.0), frames=None):
    """Sweep a circular section along a polyline. Points are in the frame the
    object will live in (world, or a parent empty's local space).

    Uses parallel transport so long runs never twist. This is the conduit /
    cable-loom / pneumatic-tube workhorse. `offset` shifts the whole section
    sideways in the local (normal, binormal) plane, which is how `bundle()`
    lays several strands into one loom.
    """
    if frames is None:
        pts, frames = path_frames(pts)
    else:
        pts = [Vector(p) for p in pts]
    n = len(pts)
    frames = [(f[1], f[2]) for f in frames]
    vs, fs = [], []
    for i, p in enumerate(pts):
        rr = radius if radii is None else radii[i]
        a, b = frames[i]
        c = p + a * offset[0] + b * offset[1]
        for k in range(sections):
            th = 2 * math.pi * k / sections
            vs.append(tuple(c + a * (rr * math.cos(th))
                            + b * (rr * math.sin(th))))
    for i in range(n - 1):
        a, b = i * sections, (i + 1) * sections
        for k in range(sections):
            k2 = (k + 1) % sections
            fs.append((a + k, a + k2, b + k2, b + k))
    if caps:
        a0, b0 = frames[0]
        a1, b1 = frames[-1]
        i0 = len(vs)
        vs.append(tuple(pts[0] + a0 * offset[0] + b0 * offset[1]))
        i1 = len(vs)
        vs.append(tuple(pts[-1] + a1 * offset[0] + b1 * offset[1]))
        last = (n - 1) * sections
        for k in range(sections):
            k2 = (k + 1) % sections
            fs.append((i0, k2, k))
            fs.append((i1, last + k, last + k2))
    return shell.mesh_from(name, vs, fs, m, smooth)


# --------------------------------------------------------------------- text
_FONT = [None, None]


def mono_font():
    """Cached monospace font, re-resolved after a factory reset wipes bpy.data."""
    f = _FONT[0]
    if f is not None and f.name in bpy.data.fonts:
        return f
    _FONT[0] = None
    for p in ("/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
              "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
              "/System/Library/Fonts/Menlo.ttc",
              "/Library/Fonts/Courier New Bold.ttf"):
        if os.path.exists(p):
            try:
                _FONT[0] = bpy.data.fonts.load(p)
                break
            except Exception:                                  # noqa: BLE001
                pass
    return _FONT[0]


def text(name, body, size, m, loc, rot=(0, 0, 0), align='CENTER',
         extrude=0.00045, to_mesh=True, spacing=1.0):
    """Engraved lettering, converted to MESH so a mesh-only combiner sees it.

    Lettering is NEVER desaturated (plan section 5.1) -- pass `mat("ink")` or
    `mat("ivory")` and leave it at that.
    """
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.extrude = extrude
    cu.space_character = spacing
    f = mono_font()
    if f:
        cu.font = f
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(m)
    if to_mesh:
        try:
            bpy.ops.object.select_all(action='DESELECT')
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.convert(target='MESH')
            o = bpy.data.objects.get(name) or o
        except Exception:                                      # noqa: BLE001
            pass
    return o


# ============================================================ small fixings
def hexbolt(name, pos, r=0.006, h=0.005, m=None):
    """A hex head standing proud of a flange."""
    return [cyl(name, (pos[0], pos[1], pos[2] + h / 2), r, h,
                m or mat("steel"), verts=6, smooth=False, bevel=0.0008)]


def screw(name, pos, r=0.0035, m=None):
    """A slotted pan-head screw: dome + slot."""
    mm = m or mat("steel")
    out = [sphere(name, (pos[0], pos[1], pos[2] + r * 0.15), r, mm,
                  scale=(1, 1, 0.48))]
    out.append(box(f"{name}_slot", (pos[0], pos[1], pos[2] + r * 0.52),
                   (r * 1.7, r * 0.30, r * 0.16), mat("ink")))
    return out


def rivet_row(name, p0, p1, n, r=0.0035, m=None, dome=0.55):
    """`n` domed rivets evenly spaced from p0 to p1 (both inclusive).

    High-frequency detail is the dressing budget (plan section 5.3) -- use this
    more than the heroes do.
    """
    mm = m or mat("brass")
    out = []
    p0, p1 = Vector(p0), Vector(p1)
    for i in range(n):
        t = 0.0 if n == 1 else i / (n - 1)
        p = p0 + (p1 - p0) * t
        out.append(sphere(f"{name}_{i}", tuple(p), r, mm,
                          scale=(1, 1, dome), seg=10, ring=6))
    return out


def bez_frame(name, cx, cy, w, h, z0, z1, m, bar=0.005):
    """Four bars forming a picture frame, so the face inside can be RECESSED."""
    zc, zd = (z0 + z1) / 2.0, z1 - z0
    return [
        box(f"{name}_t", (cx, cy + h / 2 - bar / 2, zc), (w, bar, zd), m,
            bevel=0.0012),
        box(f"{name}_b", (cx, cy - h / 2 + bar / 2, zc), (w, bar, zd), m,
            bevel=0.0012),
        box(f"{name}_l", (cx - w / 2 + bar / 2, cy, zc),
            (bar, h - 2 * bar, zd), m, bevel=0.0012),
        box(f"{name}_r", (cx + w / 2 - bar / 2, cy, zc),
            (bar, h - 2 * bar, zd), m, bevel=0.0012),
    ]


def pclip(name, pos, r, m=None, rot_z=0.0, wall=0.0035):
    """A brass P-clip: a split band gripping a cable, plus its foot and bolt."""
    mm = m or mat("brass")
    x, y, z = pos
    out = [tube(f"{name}_band", (x, y, z), r + wall, r, 0.010, mm,
                rot=(math.pi / 2, 0.0, rot_z), verts=20)]
    out.append(box(f"{name}_foot", (x, y - r - wall - 0.005, z),
                   (0.016, 0.010, 0.008), mm, bevel=0.0012))
    out += hexbolt(f"{name}_bolt", (x, y - r - wall - 0.005, z + 0.004),
                   0.0032, 0.004)
    return out


def tape_wrap(name, pts_i, pts, r, m=None, width=0.014):
    """A friction-tape band around a loom, at polyline index `pts_i`."""
    mm = m or mat("tape")
    p = Vector(pts[pts_i])
    nxt = Vector(pts[min(pts_i + 1, len(pts) - 1)])
    prv = Vector(pts[max(pts_i - 1, 0)])
    t = (nxt - prv)
    t = t.normalized() if t.length > 1e-9 else Vector((0, 0, 1))
    return [sweep(name, [p - t * (width / 2), p + t * (width / 2)],
                  r * 1.16, mm, sections=8)]


def louvre_row(name, pos, w, n, fin_h=0.006, depth=0.010, m=None,
               rot_x=-0.42):
    """A row of raked louvre fins -- the cheapest way to make a blank slab read
    as an equipment case. Fins run along local X, rake about local X."""
    mm = m or mat("hull_l")
    x, y, z = pos
    out = []
    for i in range(n):
        yy = y + (i - (n - 1) / 2.0) * (fin_h * 1.75)
        out.append(box(f"{name}_{i}", (x, yy, z + depth / 2),
                       (w, fin_h, depth), mm, rot=(rot_x, 0, 0), bevel=0.0009))
    return out


def grille(name, pos, w, h, nx, ny, m=None, depth=0.004):
    """A mesh intake grille: a recessed dark ground crossed by thin bars."""
    mm = m or mat("brass")
    x, y, z = pos
    out = [box(f"{name}_ground", (x, y, z + depth * 0.25),
               (w, h, depth * 0.5), mat("ebonite"))]
    for i in range(nx):
        xx = x + (i - (nx - 1) / 2.0) * (w / max(1, nx - 1)) * 0.96
        out.append(box(f"{name}_v_{i}", (xx, y, z + depth),
                       (0.0016, h, depth * 0.6), mm))
    for j in range(ny):
        yy = y + (j - (ny - 1) / 2.0) * (h / max(1, ny - 1)) * 0.96
        out.append(box(f"{name}_h_{j}", (x, yy, z + depth),
                       (w, 0.0016, depth * 0.6), mm))
    return out


def cage(name, pos, r, h, wires=6, m=None, ring_r=None):
    """A perforated bulb / lamp guard: bowed wires plus two hoops.

    Shared by D5's gooseneck lamp and the shell lamp cone's guard (C3).
    """
    mm = m or mat("brass")
    x, y, z = pos
    rr = ring_r if ring_r is not None else r * 0.42
    out = []
    for i in range(wires):
        th = 2 * math.pi * i / wires
        c, s = math.cos(th), math.sin(th)
        pts = [(x + r * c, y + r * s, z),
               (x + r * 1.02 * c, y + r * 1.02 * s, z - h * 0.45),
               (x + r * 0.78 * c, y + r * 0.78 * s, z - h * 0.82),
               (x + rr * c, y + rr * s, z - h)]
        out.append(sweep(f"{name}_w_{i}", pts, 0.0022, mm, sections=6))
    out.append(tube(f"{name}_hoop_0", (x, y, z), r * 1.03, r * 0.97, 0.006,
                    mm, verts=24))
    out.append(tube(f"{name}_hoop_1", (x, y, z - h * 0.55), r * 0.90,
                    r * 0.85, 0.005, mm, verts=24))
    out.append(tube(f"{name}_hoop_2", (x, y, z - h), rr * 1.30, rr * 1.10,
                    0.005, mm, verts=18))
    return out


# ============================================================ the big three
def gauge(name, pos, r=0.045, ticks=11, redline=None, needle_deg=-38.0,
          face=None, label=None, sub=None, depth=0.018, sweep_deg=250.0,
          bezel_screws=3, glassy=True):
    """A needle instrument behind a brass bezel with convex glass.

    Used by D1 x4, D4, F1 x2, F4, F5, P1, C3 -- 11 instances, the single most
    reused helper after `lampcell`.

    r          bezel OUTER radius
    ticks      major graduations across `sweep_deg`, centred on straight-up
    redline    (a0, a1) in the same needle-degree space, or None
    needle_deg needle angle; 0 = straight up, +ve = clockwise
    face       material for the dial face; defaults to aged ivory
    label      engraved unit text under the hub (e.g. "mm Hg")
    sub        small text above the hub
    """
    br = mat("brass")
    ink = mat("ink")
    fm = face or mat("ivory")
    x, y, z = pos
    out = []

    # ---- explicit z-stack, so nothing ever ends up buried inside the face
    can_z = z + depth * 0.34
    face_t = 0.0035
    face_z = z + depth * 0.62
    face_top = face_z + face_t / 2.0
    tick_z = face_top + 0.0008
    ndl_z = face_top + 0.0024
    txt_z = face_top + 0.0011
    bez_z = z + depth * 0.86
    bez_h = depth * 0.34

    # cast can behind the face
    out.append(cyl(f"{name}_can", (x, y, can_z), r * 0.92, depth * 0.68,
                   mat("case"), verts=28, bevel=0.0015, smooth=False))
    # dial face, recessed behind the bezel (FLAT shaded -- a smooth-shaded
    # cylinder cap gets a fake gradient that reads as a blown-out disc)
    out.append(cyl(f"{name}_face", (x, y, face_z), r * 0.84, face_t, fm,
                   verts=36, smooth=False))

    def _ang(d):
        return math.radians(d)

    # graduations: long majors, short minors between them
    for i in range(ticks):
        t = 0.0 if ticks == 1 else i / (ticks - 1)
        a = _ang(-sweep_deg / 2 + sweep_deg * t)
        mid = 0.695 * r
        out.append(box(f"{name}_tk_{i}",
                       (x + mid * math.sin(a), y + mid * math.cos(a), tick_z),
                       (0.052 * r, 0.20 * r, 0.0016), ink, rot=(0, 0, -a)))
        if i < ticks - 1:
            a2 = _ang(-sweep_deg / 2
                      + sweep_deg * (t + 0.5 / (ticks - 1)))
            mid = 0.740 * r
            out.append(box(f"{name}_tm_{i}",
                           (x + mid * math.sin(a2), y + mid * math.cos(a2),
                            tick_z),
                           (0.034 * r, 0.11 * r, 0.0014), ink, rot=(0, 0, -a2)))
    if redline:
        a0, a1 = redline
        n = max(2, int(abs(a1 - a0) / 5.0) + 1)
        for i in range(n):
            a = _ang(a0 + (a1 - a0) * i / (n - 1))
            mid = 0.775 * r
            out.append(box(f"{name}_rl_{i}",
                           (x + mid * math.sin(a), y + mid * math.cos(a),
                            tick_z),
                           (0.20 * r, 0.055 * r, 0.0014), mat("red_paint"),
                           rot=(0, 0, -a)))

    # needle: a tapered blade with a short counterweight tail
    na = _ang(needle_deg)
    ln = r * 0.74
    ca, sa = math.cos(na), math.sin(na)

    def _rot(px, py):
        # +needle_deg = clockwise from straight up
        return (x + px * ca + py * sa, y - px * sa + py * ca, ndl_z)

    vs = [_rot(-0.030 * r, -r * 0.20), _rot(0.030 * r, -r * 0.20),
          _rot(0.010 * r, ln), _rot(-0.010 * r, ln)]
    out.append(shell.mesh_from(f"{name}_needle", vs, [(0, 1, 2, 3)], ink))
    out.append(cyl(f"{name}_hub", (x, y, ndl_z + 0.0012), r * 0.095, 0.0035,
                   br, verts=14, smooth=False))

    if label:
        out.append(text(f"{name}_lab", label, r * 0.180, ink,
                        (x, y - r * 0.42, txt_z)))
    if sub:
        out.append(text(f"{name}_sub", sub, r * 0.150, ink,
                        (x, y + r * 0.44, txt_z)))

    # turned bezel ring (a revolve, not a slab -- it has to read as machined)
    out.append(revolve(f"{name}_bez",
                       [(r * 0.82, 0.0), (r * 0.82, bez_h * 0.72),
                        (r * 0.865, bez_h), (r * 0.945, bez_h * 0.94),
                        (r * 1.000, bez_h * 0.50), (r * 1.000, -0.0025)],
                       br, center=(x, y, bez_z), verts=36, cap=False))
    if glassy:
        cap = []
        for i in range(5):
            t = i / 4.0
            cap.append((r * 0.82 * math.cos(t * math.pi / 2),
                        bez_z + bez_h * 0.30
                        + r * 0.17 * math.sin(t * math.pi / 2)))
        out.append(revolve(f"{name}_glass", cap, mat("glass"),
                           center=(x, y, 0.0), verts=28, cap=False))
    for i in range(bezel_screws):
        a = _ang(-142 + 284.0 * i / max(1, bezel_screws - 1))
        rr = r * 0.935
        out += screw(f"{name}_scr_{i}",
                     (x + rr * math.sin(a), y + rr * math.cos(a),
                      bez_z + bez_h * 0.46), 0.0026)
    return out


def toggle(name, pos, kind="bat", pos_deg=20.0, legend=None, scale=1.0,
           legend_w=0.030, guard_up=True):
    """A bat-handle toggle switch. `kind` in {"bat", "guarded", "caged"}.

    D1 x8, F1 x6, F4 x2, F5, C1 x2 -- 19 instances. `pos_deg` is the lever tilt
    about local X; vary it between instances (plan section 5.3: perfect symmetry
    is an amateur-3D tell).
    """
    br, st = mat("brass"), mat("steel")
    s = scale
    x, y, z = pos
    out = []
    # panel bushing + hex nut
    out.append(cyl(f"{name}_nut", (x, y, z + 0.0026 * s), 0.0082 * s,
                   0.0052 * s, br, verts=6, smooth=False, bevel=0.0006))
    out.append(cyl(f"{name}_bush", (x, y, z + 0.0068 * s), 0.0052 * s,
                   0.0034 * s, br, verts=14))
    # lever
    th = math.radians(pos_deg)
    d = Vector((0.0, -math.sin(th), math.cos(th)))
    base = Vector((x, y, z + 0.0082 * s))
    ln = 0.0175 * s
    out.append(cone(f"{name}_lever", tuple(base + d * (ln / 2)),
                    0.0026 * s, 0.0016 * s, ln, st,
                    rot=(th, 0, 0), verts=10))
    out.append(sphere(f"{name}_tip", tuple(base + d * (ln + 0.0026 * s)),
                      0.0038 * s, br, seg=12, ring=8))

    if kind in ("guarded", "caged"):
        # hinged brass guard bar standing above the switch
        gy = y + 0.017 * s
        out.append(box(f"{name}_grd", (x, gy, z + 0.011 * s),
                       (0.024 * s, 0.007 * s, 0.0035 * s), br,
                       rot=(math.radians(-24 if guard_up else 62), 0, 0),
                       bevel=0.0008))
        for sx in (-1, 1):
            out.append(box(f"{name}_grdcheek_{0 if sx < 0 else 1}",
                           (x + sx * 0.0125 * s, y + 0.008 * s, z + 0.005 * s),
                           (0.0030 * s, 0.020 * s, 0.010 * s), br,
                           bevel=0.0007))
    if kind == "caged":
        out += cage(f"{name}_cage", (x, y, z + 0.030 * s), 0.014 * s,
                    0.030 * s, wires=4)
    if legend:
        out.append(box(f"{name}_plate", (x, y - 0.0135 * s, z + 0.0012 * s),
                       (legend_w, 0.0095 * s, 0.0022 * s), mat("ebonite"),
                       bevel=0.0006))
        out.append(text(f"{name}_leg", legend, 0.0052 * s, mat("ivory"),
                        (x, y - 0.0135 * s, z + 0.0026 * s)))
    return out


def lampcell(name, pos, w=0.030, h=0.016, legend="", lit=False, kind="amber",
             depth=0.010, text_size=None, frame=True, round_lens=False):
    """A back-illuminable engraved legend cell.

    H1 x16, F2 x14, F4 x6, D1 x4, C3 x3 -- 43 instances, the most reused part in
    the plan. One mesh, four scales: legend cell / recessed lens / compartment
    lamp / annunciator.

    Obey the 1-in-5 rule: pass `lit=True` on at most one cell in five.
    """
    x, y, z = pos
    out = []
    out.append(box(f"{name}_can", (x, y, z + depth * 0.30),
                   (w, h, depth * 0.60), mat("case"), bevel=0.0012))
    lm = lamp_mat(kind, lit)
    if round_lens:
        out.append(cyl(f"{name}_lens", (x, y, z + depth * 0.68),
                       min(w, h) * 0.42, depth * 0.30, lm, verts=20,
                       bevel=0.0009))
    else:
        out.append(box(f"{name}_lens", (x, y, z + depth * 0.68),
                       (w * 0.86, h * 0.72, depth * 0.34), lm, bevel=0.0016))
    if frame:
        out += bez_frame(f"{name}_bez", x, y, w, h, z + depth * 0.30,
                         z + depth * 0.86, mat("brass"),
                         bar=min(0.0032, h * 0.20))
    if legend:
        ts = text_size if text_size is not None else min(h * 0.34, w / max(
            4.0, len(legend)) * 1.30)
        out.append(text(f"{name}_txt", legend, ts, mat("ink"),
                        (x, y, z + depth * 0.86)))
    return out


# ================================================== plates, stencils, signs
def stencil(name, body, pos, size=0.020, m=None, rot=(0, 0, 0),
            align='CENTER', worn=False):
    """Sprayed hull lettering. Plan section 2/H3: the number-one era cue, and the
    cheapest thing in the document."""
    o = text(name, body, size, m or mat("ivory"), pos, rot=rot, align=align,
             extrude=0.00035)
    if worn:
        # a worn stencil sits flatter and duller -- swap to the paper material
        o.data.materials.clear()
        o.data.materials.append(mat("paper"))
    return [o]


def nameplate(name, body, pos, w=None, h=0.020, size=None, screws=True,
              sub=None, m=None):
    """An engraved brass nameplate on four screws."""
    x, y, z = pos
    ts = size if size is not None else h * 0.44
    ww = w if w is not None else max(0.028, len(body) * ts * 0.78 + 0.012)
    br = m or mat("brass")
    out = [box(f"{name}_pl", (x, y, z + 0.0016), (ww, h, 0.0032), br,
               bevel=0.0010)]
    ty = y + (h * 0.20 if sub else 0.0)
    out.append(text(f"{name}_txt", body, ts, mat("ink"), (x, ty, z + 0.0034)))
    if sub:
        out.append(text(f"{name}_sub", sub, ts * 0.78, mat("ink"),
                        (x, y - h * 0.24, z + 0.0034)))
    if screws:
        for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
            out += screw(f"{name}_s_{i}",
                         (x + sx * (ww / 2 - 0.0042),
                          y + sy * (h / 2 - 0.0042), z + 0.0030), 0.0024)
    return out


def warn_triangle(name, pos, size=0.030, glyph="!", m=None):
    """A stencilled caution triangle. Painted, never lit -- red is rationed."""
    x, y, z = pos
    s = size
    mm = m or mat("ivory")
    r = s / 2
    vs = [(x, y + r, z), (x - r * 0.92, y - r * 0.72, z),
          (x + r * 0.92, y - r * 0.72, z)]
    inn = 0.72
    vs += [(x, y + r * inn, z), (x - r * 0.92 * inn, y - r * 0.72 * inn, z),
           (x + r * 0.92 * inn, y - r * 0.72 * inn, z)]
    fs = [(0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
    out = [shell.mesh_from(name, vs, fs, mm)]
    out.append(text(f"{name}_g", glyph, s * 0.42, mm,
                    (x, y - r * 0.06, z + 0.0006)))
    return out


def arrow(name, pos, length=0.048, m=None, rot_z=0.0, thick=0.006):
    """A painted directional flow arrow -- for conduit runs and duct work."""
    x, y, z = pos
    mm = m or mat("ivory")
    L = length
    vs = [(-L / 2, -thick / 2, 0), (L * 0.16, -thick / 2, 0),
          (L * 0.16, thick / 2, 0), (-L / 2, thick / 2, 0),
          (L * 0.16, -thick * 1.6, 0), (L / 2, 0.0, 0),
          (L * 0.16, thick * 1.6, 0)]
    fs = [(0, 1, 2, 3), (4, 5, 6)]
    o = shell.mesh_from(name, vs, fs, mm)
    o.location = (x, y, z)
    o.rotation_euler = (0, 0, rot_z)
    return [o]


def inspection_stamp(name, pos, body="INSP", r=0.011, m=None):
    """A small stamped brass disc -- scatter these; they cost nothing."""
    x, y, z = pos
    mm = m or mat("brass")
    return [cyl(f"{name}_d", (x, y, z + 0.0011), r, 0.0022, mm, verts=16,
                bevel=0.0006),
            text(f"{name}_t", body, r * 0.46, mat("ink"),
                 (x, y, z + 0.0024))]


# ================================================= instruments & mechanisms
def breaker(name, pos, pulled=0.0, r=0.010, legend=None, m=None):
    """A pull-type circuit breaker with a brass mushroom head.

    C1 x20, F5 x3 (as a fuse cap at a different scale) -- 23 instances.
    `pulled` in 0..1 lifts the head out of its collar; vary it per instance.
    """
    x, y, z = pos
    br = m or mat("brass")
    lift = 0.006 * pulled
    out = [cyl(f"{name}_col", (x, y, z + 0.0022), r * 1.05, 0.0044,
               mat("case"), verts=16, bevel=0.0008)]
    out.append(cyl(f"{name}_shaft", (x, y, z + 0.0044 + lift / 2),
                   r * 0.34, 0.0044 + lift, mat("steel"), verts=10))
    prof = [(r * 0.34, 0.0), (r * 0.92, 0.0016), (r * 1.00, 0.0044),
            (r * 0.80, 0.0074), (r * 0.30, 0.0086)]
    out.append(revolve(f"{name}_head", prof, br,
                       center=(x, y, z + 0.0060 + lift), verts=18))
    if legend:
        out.append(text(f"{name}_leg", legend, 0.0050, mat("ivory"),
                        (x, y - r * 1.75, z + 0.0012)))
    return out


def sightglass(name, pos, length=0.150, r=0.011, fill=0.55, grads=8,
               float_ball=True, vertical=True):
    """A graduated sight glass with a float. F1 x3, F4, P1 x2 -- 6 instances.

    The fluid is TRANSMISSIVE, not emissive (plan section 5.1).
    """
    x, y, z = pos
    br = mat("brass")
    L = length
    out = []
    rot = (0, 0, 0) if vertical else (0, math.pi / 2, 0)
    ax = Vector((0, 1, 0)) if vertical else Vector((1, 0, 0))
    c = Vector((x, y, z + r))
    # glass tube
    out.append(cyl(f"{name}_tube", tuple(c), r, L, mat("glass"),
                   rot=(math.pi / 2, 0, 0) if vertical else (0, math.pi / 2, 0),
                   verts=18))
    # fluid column
    fl = L * max(0.02, min(0.98, fill))
    fc = c - ax * (L / 2) + ax * (fl / 2)
    out.append(cyl(f"{name}_fluid", tuple(fc), r * 0.82, fl, mat("fluid"),
                   rot=(math.pi / 2, 0, 0) if vertical else (0, math.pi / 2, 0),
                   verts=16))
    # flanges
    for i, s in enumerate((-1, 1)):
        p = c + ax * (s * L / 2)
        out.append(revolve(f"{name}_fl_{i}",
                           [(r * 1.5, -0.010), (r * 1.5, 0.0),
                            (r * 1.18, 0.002), (r * 1.18, 0.012)],
                           br, center=tuple(p),
                           rot=(math.pi / 2 if vertical else 0,
                                0 if vertical else math.pi / 2, 0)
                           if s > 0 else
                           (-math.pi / 2 if vertical else 0,
                            0 if vertical else -math.pi / 2, 0),
                           verts=18))
    # graduations on a brass strip beside the glass
    sx = r * 1.45
    off = Vector((sx, 0, 0)) if vertical else Vector((0, sx, 0))
    out.append(box(f"{name}_scale", tuple(c + off),
                   (0.006 if vertical else L, L if vertical else 0.006,
                    0.0022), br, bevel=0.0006))
    for i in range(grads):
        t = (i + 0.5) / grads
        p = c - ax * (L / 2) + ax * (L * t) + off
        out.append(box(f"{name}_g_{i}", (p.x, p.y, p.z + 0.0018),
                       (0.0050 if vertical else 0.0012,
                        0.0012 if vertical else 0.0050, 0.0010), mat("ink")))
    if float_ball:
        p = c - ax * (L / 2) + ax * (fl)
        out.append(sphere(f"{name}_float", tuple(p), r * 0.62, mat("ivory"),
                          seg=14, ring=8))
    return out


def vactube(name, pos, h=0.075, r=0.017, lit=True, pins=8, axis="y"):
    """A vacuum tube: glass envelope, bakelite base, plate stack, filament.

    P2 x4, F5 -- 5 instances. The filament glow is deliberately feeble
    (em 1.2); hero-tier glow would steal the frame.

    `axis="y"` (default) stands the tube UP on the panel, standing off by its
    own radius, which is what a rectifier cage behind a perforated guard wants.
    `axis="z"` points it out of the panel at the pilot. The parts come back
    parented to a sub-frame empty, which is the first object in the list --
    `parent_to` will adopt the empty and the rest follow.
    """
    x, y, z = pos
    if axis == "y":
        e = frame_empty(f"{name}_f", (x, y, z + r * 1.05),
                        (-math.pi / 2, 0.0, 0.0))
    else:
        e = frame_empty(f"{name}_f", (x, y, z), (0.0, 0.0, 0.0))
    out = []
    # bakelite base with pins
    out.append(cyl(f"{name}_base", (0, 0, 0.008), r * 0.98, 0.016,
                   mat("ebonite"), verts=20, bevel=0.0012))
    for i in range(pins):
        a = 2 * math.pi * i / pins
        out.append(cyl(f"{name}_pin_{i}",
                       (r * 0.62 * math.cos(a), r * 0.62 * math.sin(a),
                        -0.004), 0.0013, 0.008, mat("steel"), verts=6))
    # envelope: straight barrel with a domed crown and a pip
    body = h - 0.016
    prof = [(r * 0.99, 0.0), (r, 0.004), (r, body * 0.72)]
    for i in range(1, 6):
        t = i / 5.0
        prof.append((r * math.cos(t * math.pi / 2) * 0.995,
                     body * 0.72 + (body * 0.28) * math.sin(t * math.pi / 2)))
    out.append(revolve(f"{name}_env", prof, mat("glass"),
                       center=(0, 0, 0.016), verts=22, cap=False))
    out.append(cone(f"{name}_pip", (0, 0, 0.016 + body + 0.004),
                    0.0030, 0.0008, 0.008, mat("glass"), verts=8))
    # internal element stack -- everything inside must stay inside the glass
    out.append(box(f"{name}_plate", (0, 0, 0.016 + body * 0.48),
                   (r * 1.02, r * 0.66, body * 0.56), mat("steel"),
                   bevel=0.0008))
    out.append(cyl(f"{name}_fil", (0, 0, 0.016 + body * 0.46),
                   r * 0.16, body * 0.60,
                   mat("filament") if lit else mat("ink"), verts=8))
    for i, sgn in enumerate((-1, 1)):
        out.append(box(f"{name}_mica_{i}",
                       (0, 0, 0.016 + body * (0.20 if sgn < 0 else 0.76)),
                       (r * 1.24, r * 1.24, 0.0022), mat("paper")))
    parent_to(out, e)
    return [e] + out


def flipdigit(name, pos, ch="0", w=0.020, h=0.030, m=None, lit_ink=None):
    """One flip-dot digit cell -- copied from OTA's version board.

    A dark ground with faint dot ruling (so it reads as a dot matrix, NOT a
    phosphor screen -- plan section 5.2 forbids CRT faces anywhere), a brass
    bezel, and the character in dot-amber ink.
    """
    x, y, z = pos
    out = [box(f"{name}_face", (x, y, z + 0.005),
               (w - 0.004, h - 0.004, 0.010), mat("ebonite"))]
    out += bez_frame(f"{name}_bez", x, y, w, h, z, z + 0.011,
                     m or mat("brass"), bar=0.0026)
    for k in range(5):
        out.append(box(f"{name}_rule_{k}",
                       (x, y - h * 0.34 + k * (h * 0.17), z + 0.0102),
                       (w - 0.008, 0.0007, 0.0008), mat("case")))
    out.append(text(f"{name}_ch", ch, h * 0.62,
                    lit_ink or mat("dot"), (x, y, z + 0.0112)))
    return out


def mimic_strip(name, path, width=0.006, z=0.0, m=None, thickness=0.0035,
                closed=False, nodes=(), node_r=0.005):
    """Extrude a polyline of (x, y) points as raised brass strip on a dark
    ground -- the hull-outline mimic (F2) and the bus single-line diagram (F5).

    `nodes` are indices (or (x, y) pairs) that get a raised junction pad.
    """
    mm = m or mat("brass")
    out = []
    pts = list(path) + ([path[0]] if closed else [])
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        out.append(box(f"{name}_s_{i}",
                       ((x0 + x1) / 2, (y0 + y1) / 2, z + thickness / 2),
                       (L + width * 0.5, width, thickness), mm,
                       rot=(0, 0, math.atan2(dy, dx)), bevel=0.0008))
    for i, nd in enumerate(nodes):
        px, py = path[nd] if isinstance(nd, int) else nd
        out.append(cyl(f"{name}_n_{i}", (px, py, z + thickness * 0.9),
                       node_r, thickness * 1.2, mm, verts=12, bevel=0.0006))
    return out


# ============================================== column / hull-following bits
def wrap_collar(name, center, r_in, r_out, depth, m=None,
                rot=(math.pi / 2, 0, 0), verts=44, bolts=0, arm=None):
    """OTA's mounting collar: a band that genuinely WRAPS the column
    (inner r 0.078 against the 0.075 column) rather than a flat plate whose
    edges bury themselves 19 mm inside the cylinder.

    P1 x4, P2 x4, P3 x2 -- 10 instances. Whole-shell holdout rendering is
    required for anything that uses this: the collar's back half is BEHIND the
    column, and the column must punch a clean hole through the ring.
    """
    mm = m or mat("brass")
    out = [tube(name, center, r_out, r_in, depth, mm, rot=rot, verts=verts)]
    if arm:
        for i, s in enumerate((-1, 1)):
            out.append(box(f"{name}_arm_{i}",
                           (center[0] + s * (r_out + arm / 2), center[1],
                            center[2] + r_out * 0.0),
                           (arm, depth, r_out * 1.10), mm, bevel=0.0016))
    for i in range(bolts):
        s = -1 if i % 2 == 0 else 1
        out += hexbolt(f"{name}_b_{i}",
                       (center[0] + s * (r_out + 0.008), center[1],
                        center[2] + 0.010 * (1 if i < 2 else -1)), 0.0038,
                       0.004)
    return out


def conduit_arc(name, a0, a1, r, z, tube_r=0.025, bands=0, ribbed=False,
                m=None, seg=None, band_r=1.28, sections=10, dz=0.0):
    """A conduit run following the hull arc, in WORLD space.

    H2 and X1. `a0`/`a1` are degrees off the centreline; `r` is the radius of
    the run and `z` its height. `ribbed=True` corrugates the radius so the run
    reads as flexible duct instead of rigid pipe. `bands` adds strap clamps.
    Returns (objects, points) so callers can hang tees and drop-stubs off it.
    """
    mm = m or mat("brass")
    n = seg if seg is not None else max(12, int(abs(a1 - a0) / 2.2))
    pts, radii = [], []
    for i in range(n + 1):
        t = i / n
        a = math.radians(a0 + (a1 - a0) * t)
        pts.append((r * math.sin(a), r * math.cos(a), z + dz * t))
        if ribbed:
            radii.append(tube_r * (1.0 + 0.16 * math.sin(t * n * 1.7)))
        else:
            radii.append(tube_r)
    out = [sweep(name, pts, tube_r, mm, sections=sections,
                 radii=radii if ribbed else None)]
    for i in range(bands):
        t = (i + 0.5) / bands
        a = math.radians(a0 + (a1 - a0) * t)
        out.append(tube(f"{name}_band_{i}",
                        (r * math.sin(a), r * math.cos(a), z + dz * t),
                        tube_r * band_r, tube_r * 0.99, 0.012, mat("brass_dk"),
                        rot=(math.pi / 2, 0.0, -a), verts=18))
    return out, pts


def conduit_tee(name, pt, normal_deg, tube_r=0.025, stub=0.10, m=None,
                down=True):
    """A junction tee on a conduit run, with a short drop-stub."""
    mm = m or mat("brass")
    x, y, z = pt
    a = math.radians(normal_deg)
    out = [tube(f"{name}_body", (x, y, z), tube_r * 1.34, tube_r * 0.99, 0.030,
                mm, rot=(math.pi / 2, 0.0, -a), verts=18)]
    end = (x, y, z - stub) if down else (x + stub * math.sin(a),
                                         y + stub * math.cos(a), z)
    out.append(sweep(f"{name}_stub", [(x, y, z), end], tube_r * 0.74, mm,
                     sections=8))
    out.append(tube(f"{name}_gland", end, tube_r * 1.10, tube_r * 0.72, 0.014,
                    mat("brass_dk"), verts=16))
    return out


def gland(name, pos, r=0.014, m=None, boot=True, rot=(0, 0, 0)):
    """A cable gland with a stepped brass body and a rubber boot."""
    mm = m or mat("brass")
    x, y, z = pos
    out = [revolve(f"{name}_body",
                   [(r * 1.30, 0.0), (r * 1.30, 0.008), (r * 1.05, 0.010),
                    (r * 1.05, 0.020), (r * 0.86, 0.022), (r * 0.86, 0.030)],
                   mm, center=(x, y, z), rot=rot, verts=14)]
    if boot:
        out.append(revolve(f"{name}_boot",
                           [(r * 0.92, 0.0), (r * 0.86, 0.014),
                            (r * 0.72, 0.026), (r * 0.66, 0.040)],
                           mat("rubber"), center=(x, y, z + 0.028), rot=rot,
                           verts=14, cap=False))
    return out


def bundle(name, pts, r, m, strands=3, sections=8, jitter=0.62):
    """Several strands laid into one cable bundle along a path.

    A single smooth tube reads as chrome pipe at wide-shot scale; three strands
    of slightly different diameter read as a cloth-braided loom. Cheap, and the
    difference is the whole point of X1.
    """
    pts, frames = path_frames(pts)
    out = []
    if strands <= 1:
        return [sweep(name, pts, r, m, sections=sections, frames=frames)]
    for i in range(strands):
        th = 2 * math.pi * i / strands + 0.4
        off = r * jitter
        rr = r * (0.62 if strands > 2 else 0.72) * (1.0 + 0.13 * ((i % 3) - 1))
        out.append(sweep(f"{name}_s_{i}", pts, rr, m, sections=sections,
                         frames=frames,
                         offset=(off * math.cos(th), off * math.sin(th))))
    return out


def loom(name, pts, r=0.022, m=None, clips=(), wraps=(), sections=10,
         spur=None, strands=3):
    """A bundled cloth-braided cable loom along a polyline, in whatever frame
    the points are given. `clips` and `wraps` are indices into `pts`.

    X1's connective tissue. Add a `spur` (list of points) for the one loose
    zip-tied branch that keeps the run from looking machine-perfect.
    """
    mm = m or mat("braid")
    out = bundle(name, pts, r, mm, strands=strands, sections=sections)
    for i, k in enumerate(clips):
        out += pclip(f"{name}_clip_{i}", pts[int(k)], r)
    for i, k in enumerate(wraps):
        out += tape_wrap(f"{name}_wrap_{i}", int(k), pts, r)
    if spur:
        out += bundle(f"{name}_spur", spur, r * 0.46, mm, strands=2,
                      sections=8)
        out += tape_wrap(f"{name}_spurtie", 1, spur, r * 0.46)
    return out


# ================================================================= helpers
def parent_to(objs, empty):
    """Parent a list of objects to an empty, preserving authored local coords."""
    for o in objs:
        if o.parent is None:
            o.parent = empty
            o.matrix_parent_inverse = Matrix.Identity(4)
    return objs


def frame_empty(name, loc, eul, parent=None):
    """An empty in the slot convention. Nestable: pass another empty as parent
    and give `loc`/`eul` in that empty's local space."""
    bpy.ops.object.empty_add(location=(0.0, 0.0, 0.0))
    e = bpy.context.object
    e.name = name
    e.location = loc
    e.rotation_euler = eul
    e.empty_display_size = 0.05
    if parent is not None:
        e.parent = parent
        e.matrix_parent_inverse = Matrix.Identity(4)
    return e


def emissive_area(objs):
    """Sum the polygon area of every face carrying an emissive material.

    Plan section 5.2 asks for this at build time: the total dressing emissive
    area must stay under 15% of the eight heroes' combined emissive area, and
    21 props each with 'just a couple of lamps' is how a plate ends up looking
    like a Christmas tree.
    """
    total = 0.0
    for o in objs:
        if o.type != 'MESH' or not o.data.materials:
            continue
        emis = []
        for m in o.data.materials:
            s = 0.0
            if m and m.use_nodes:
                b = m.node_tree.nodes.get("Principled BSDF")
                if b and "Emission Strength" in b.inputs:
                    s = b.inputs["Emission Strength"].default_value
            emis.append(s > 0.01)
        if not any(emis):
            continue
        sc = o.matrix_world.to_scale()
        k = (abs(sc.x) + abs(sc.y) + abs(sc.z)) / 3.0
        for p in o.data.polygons:
            if emis[min(p.material_index, len(emis) - 1)]:
                total += p.area * k * k
    return total
