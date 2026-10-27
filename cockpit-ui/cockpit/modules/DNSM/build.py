"""
DNSM -- dns-module  ->  NAV BEACON / STAR CHARTS
Cockpit control for the SAINTCON 2026 AppSec Challenge UI.

Slot: the CEILING -- the prop hangs overhead, and slots.place() hands back a
frame whose local +Z is straight DOWN.  A panel built flat on that frame is
seen by the pilot camera at 73 degrees off its own normal (cos 0.29): legible
area collapses to a third and the thing reads as a sliver.  So the prop is a
YOKE-MOUNTED SCOPE HEAD: a housing hung from a ceiling plate on two brass
arms, whose working face is canted 60 degrees about local X so its normal
swings from "straight down" round to "down and at the pilot".  Measured
against the real camera ray that leaves 13 degrees off-normal -- effectively
face-on -- while the yoke, the stalks and the overhang keep it reading as a
thing that hangs from the roof rather than a panel stuck to it.

The face carries the navigator's instruments:

    SWEEP    (rotate)  -- the radar scope.  A phosphor wedge with a ten-step
                          decaying tail, rendered once pointing up the face and
                          spun in CSS about its projected centre.
                                                    -> the beacon, live
    QTYPE    (states)  -- what the scope is showing.  Contacts (blips) light up
                          on the plot and one record-type lamp burns in the row
                          along the bottom, with a readout across the top.
                          A / AAAA / CNAME / TXT / MX / NS, plus AXFR (the whole
                          catalogue lights up) and NXDOMAIN (nothing out there,
                          red lamp).            -> A/AAAA/TXT/MX/NS/CNAME,
                                                   NXDOMAIN, AXFR
    CHART    (frames)  -- the coordinate lookup wheel: a six-facet drum behind a
                          window in the face, each facet a page of the zone
                          printed as real geometry.  Roll it to read the
                          catalogue.                 -> the zone file / AXFR
    COURIER  (states)  -- the chart-courier slot: a chart card in the mouth,
                          pushed home (import running, lamp lit), gone.
                                                    -> POST /admin/import,
                                                       ?source_url= / ?path=

Run standalone:
    /Applications/Blender.app/Contents/MacOS/Blender --background --python build.py
"""
import bpy, math, os, sys, json
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
COCKPIT = os.path.abspath(os.path.join(HERE, "..", ".."))
if COCKPIT not in sys.path:
    sys.path.insert(0, COCKPIT)
import shell                                                   # noqa: E402
import slots                                                   # noqa: E402

CODE = "DNSM"
NAME = "Nav Beacon"
SURFACE = slots.SLOTS[CODE]["surface"]
OUT = os.path.join(HERE, "out")

# --------------------------------------------------------------- the frame
# Slot-local: +X right across the surface, +Y toward the pilot, +Z straight
# down.  The working face gets its own frame, tilted about X.
TILT = math.radians(-60.0)      # face normal -> (0, .866, .5): pilot + down
FROT = (TILT, 0.0, 0.0)
# SIZE.  The ceiling props sit ~2.1 m from the pilot against ~2.9 m for the
# dash, so perspective inflated them: this prop's far hotspot was 244 px wide
# against 160-221 px for every dash/fascia control, and it ran off the top of
# frame.  SCALE shrinks the whole prop uniformly via root.scale.  The two
# ABSOLUTE anchors (FACE_C and CEIL_Z) are pre-divided by SCALE, so the scaling
# happens ABOUT THE FACE CENTRE: the face keeps its world position, its 60 deg
# tilt and its ceiling mount -- only the size changes, and the yoke arms and
# conduit stretch to make up the difference.
SCALE = 0.78
FACE_C = Vector((0.0, 0.100, 0.055)) / SCALE
                                        # face centre, slot-local (hangs low
                                        # enough to clear the frame top)
FACE_UP = Vector((0.0, math.cos(TILT), math.sin(TILT)))
FACE_N = Vector((0.0, -math.sin(TILT), math.cos(TILT)))

HW, HL = 0.240, 0.175           # face half-width / half-length
PLATE_T = 0.012                 # face plate thickness
BODY_D = 0.150                  # housing depth behind the face
CEIL_Z = -0.340 / SCALE         # slot-local Z of the cockpit ceiling

# --- scope
SC_U, SC_V = -0.086, 0.020
SC_R = 0.112
SC_H = 0.021                    # phosphor plane, PROUD of the face plate:
                                # a scope can bolted through the panel, not a
                                # recess (a recess would sit behind the plate
                                # and vanish)
SWEEP_STEPS = 10
SWEEP_ARC = 34.0                # degrees of decaying tail

# --- chart drum + its window in the face plate
WU0, WU1 = 0.062, 0.222
WV0, WV1 = 0.044, 0.100
DR_U, DR_V, DR_H = 0.142, 0.072, -0.076
DR_R = 0.062                    # facet radius
DR_FACETS = 6
DR_LEN = 0.190

# --- courier slot
CO_U, CO_V = 0.142, -0.070
CARD_H = 0.064

# --- record-type lamp row
LAMP_V = -0.128
LABEL_V = -0.152
QTYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "AXFR", "NX"]
QLABELS = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "AXFR", "NXDOM"]
QREADOUT = {
    "A":     "QT A      192.0.2.10",
    "AAAA":  "QT AAAA   2001:DB8::10",
    "CNAME": "QT CNAME  FTP > WWW",
    "TXT":   "QT TXT    2 STRINGS",
    "MX":    "QT MX     10 MAIL",
    "NS":    "QT NS     NS1 . NS2",
    "AXFR":  "AXFR TCP  ZONE 23 RR",
    "NX":    "NXDOMAIN  RCODE 3",
}
# contacts on the plot: (bearing deg, radius fraction).  0 deg = up the face.
QBLIPS = {
    "A":     [(38, 0.54)],
    "AAAA":  [(38, 0.54), (44, 0.82)],
    "CNAME": [(-64, 0.40), (-28, 0.70)],
    "TXT":   [(122, 0.48), (131, 0.61), (140, 0.50)],
    "MX":    [(-148, 0.44), (-139, 0.68)],
    "NS":    [(-6, 0.86), (172, 0.80)],
    "AXFR":  [],                       # filled in below: the whole catalogue
    "NX":    [],
}
for _i in range(23):
    _b = -175.0 + 351.0 * ((_i * 7) % 23) / 22.0
    _r = 0.24 + 0.62 * (((_i * 11) % 17) / 16.0)
    QBLIPS["AXFR"].append((_b, _r))

COURIER_STATES = ["chart", "import", "empty"]

CHART_PAGES = [
    ["@     SOA  NS1 2026072201", "@     NS   NS1.EXAMPLE.", "@     A    192.0.2.10"],
    ["WWW   A    192.0.2.10", "WWW   AAAA 2001:DB8::10", "FTP   CNAME WWW.EXAMPLE."],
    ["@     MX   10 MAIL.EXAM.", "MAIL  A    192.0.2.25", "INFO  TXT  SECTOR 7G"],
    ["NS1   A    192.0.2.53", "NS2   A    192.0.2.54", "BEACON A   192.0.2.99"],
    ["PLOT  A    192.0.2.71", "DOCK  CNAME WWW.EXAMPLE.", "CHART TXT  GRID 44-12"],
    ["-- AXFR 23 RR END --", "SOA SERIAL 2026072201", "TTL 300   AA=1"],
]


# ---------------------------------------------------------------- utilities
def fp(u, v, h=0.0):
    """Face coords (across, up the face, out along its normal) -> slot-local."""
    return FACE_C + Vector((u, 0.0, 0.0)) + FACE_UP * v + FACE_N * h


def _mat(name, *a, **kw):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    return shell.material(name, *a, **kw)


def _box(name, center, size, mat, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = size
    if bevel:
        m = o.modifiers.new("bev", 'BEVEL')
        m.width, m.segments = bevel, 2
    o.data.materials.append(mat)
    return o


def _cyl(name, center, r, d, mat, rot=(0, 0, 0), verts=32, smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, vertices=verts,
                                        location=center, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(mat)
    if smooth:
        for f in o.data.polygons:
            f.use_smooth = True
    return o


def _sphere(name, loc, r, mat, scale=(1, 1, 1), rot=(0, 0, 0), seg=18, ring=10):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg,
                                         ring_count=ring, location=loc,
                                         rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    o.data.materials.append(mat)
    for f in o.data.polygons:
        f.use_smooth = True
    return o


def _ring(name, loc, major, minor, mat, rot=(0, 0, 0), seg=44, mseg=8):
    bpy.ops.mesh.primitive_torus_add(location=loc, rotation=rot,
                                     major_radius=major, minor_radius=minor,
                                     major_segments=seg, minor_segments=mseg)
    o = bpy.context.object
    o.name = name
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
    child.parent = parent
    child.matrix_parent_inverse.identity()


def _strut(name, p0, p1, w, mat, bevel=0.0):
    """A square bar spanning slot-local p0 -> p1."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    ln = d.length
    rot = d.to_track_quat('Z', 'Y').to_euler()
    return _box(name, (p0 + p1) / 2, (w, w, ln), mat, rot=rot, bevel=bevel)


_FONT = [None]


def _font():
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


def _text(name, body, size, mat, loc, rot=(0, 0, 0), align='LEFT'):
    """Legible type as real geometry, converted to a mesh so every consumer of
    add_props() (which may only walk MESH objects) still sees it."""
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.extrude = 0.0004
    f = _font()
    if f:
        cu.font = f
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat)
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.object
    o.name = name
    return o


def _sector(name, r0, r1, a0, a1, mat, loc, rot, seg=10):
    """An annular wedge in the face plane, a0/a1 in degrees (0 = up the face)."""
    verts, faces = [], []
    for i in range(seg + 1):
        a = math.radians(a0 + (a1 - a0) * i / seg)
        s, c = math.sin(a), math.cos(a)
        verts.append((r0 * s, r0 * c, 0.0))
        verts.append((r1 * s, r1 * c, 0.0))
    for i in range(seg):
        b = i * 2
        faces.append((b, b + 2, b + 3, b + 1))
    o = shell.mesh_from(name, verts, faces, mat)
    o.location = loc
    o.rotation_euler = rot
    return o


# ------------------------------------------------------------------- build
def add_props(P, mats):
    """Add the DNSM nav-beacon scope head to the CURRENT scene.

    P    : the shell PARAMS dict (already built)
    mats : {"brass":..., "hull":..., "hull_d":...}
    Returns {"far": [...], "plate": [...], "root": obj, "controls": {...}}
    """
    brass = mats["brass"]
    hull = mats["hull"]
    hull_d = mats["hull_d"]

    panel = _mat("dnsm_panel", (0.021, 0.026, 0.032, 1), 0.14, 0.50)
    case = _mat("dnsm_case", (0.044, 0.048, 0.058, 1), 0.18, 0.46)
    well = _mat("dnsm_well", (0.006, 0.026, 0.014, 1), 0.02, 0.80,
            emission=(0.02, 0.20, 0.09, 1), emit_strength=0.30)
    core = _mat("dnsm_core", (0.014, 0.016, 0.020, 1), 0.02, 0.80)
    ink = _mat("dnsm_ink", (0.046, 0.044, 0.040, 1), 0.0, 0.80)
    paper = _mat("dnsm_paper", (0.868, 0.845, 0.762, 1), 0.0, 0.66)
    grid = _mat("dnsm_grid", (0.10, 0.42, 0.24, 1), 0.0, 0.55,
                emission=(0.10, 0.62, 0.30, 1), emit_strength=0.9)
    glyph = _mat("dnsm_glyph", (0.42, 0.94, 0.58, 1), 0.0, 0.42,
                 emission=(0.26, 1.0, 0.46, 1), emit_strength=2.4)
    blip = _mat("dnsm_blip", (0.42, 0.96, 0.56, 1), 0.0, 0.30,
                emission=(0.22, 1.0, 0.40, 1), emit_strength=1.8)
    lamp_off = _mat("dnsm_lamp_off", (0.055, 0.130, 0.080, 1), 0.0, 0.40)
    lamp_on = _mat("dnsm_lamp_on", (0.40, 1.0, 0.56, 1), 0.0, 0.28,
                   emission=(0.22, 1.0, 0.40, 1), emit_strength=1.6)
    lamp_amb = _mat("dnsm_lamp_amber", (1.0, 0.74, 0.26, 1), 0.0, 0.30,
                    emission=(1.0, 0.56, 0.12, 1), emit_strength=1.5)
    lamp_red = _mat("dnsm_lamp_red", (1.0, 0.28, 0.22, 1), 0.0, 0.30,
                    emission=(1.0, 0.14, 0.08, 1), emit_strength=1.9)

    root = _empty("dnsm_root", (0, 0, 0))
    far, plate = [], []

    def keep(o, parent=None, static=True):
        _adopt(o, parent or root)
        far.append(o)
        if static:
            plate.append(o)
        return o

    # ------------------------------------------- ceiling mount + yoke arms
    keep(_box("dnsm_mount", (0.0, 0.020, CEIL_Z + 0.010), (0.330, 0.150, 0.014),
              brass, bevel=0.003))
    keep(_box("dnsm_mount_pad", (0.0, 0.020, CEIL_Z + 0.024), (0.240, 0.110,
                                                               0.016),
              hull, bevel=0.004))
    for i, sx in enumerate((-1, 1)):
        trunnion = fp(sx * 0.256, 0.0, -0.100)
        anchor = Vector((sx * 0.150, 0.020, CEIL_Z + 0.030))
        keep(_strut(f"dnsm_yoke_{i}", anchor, trunnion, 0.026, brass,
                    bevel=0.004))
        keep(_cyl(f"dnsm_trunnion_{i}", trunnion, 0.030, 0.026, brass,
                  rot=(0, math.pi / 2, 0), verts=24))
        keep(_cyl(f"dnsm_trunnion_cap_{i}", fp(sx * 0.268, 0.0, -0.100), 0.013,
                  0.012, hull_d, rot=(0, math.pi / 2, 0), verts=16))
    # a slim cable conduit up to the roof, so it does not read as floating
    keep(_strut("dnsm_conduit", fp(-0.06, 0.150, -0.185),
                Vector((-0.05, 0.020, CEIL_Z + 0.026)), 0.014, hull_d))

    # ------------------------------------------------- housing (open front)
    keep(_box("dnsm_body_back", fp(0, 0, -BODY_D + 0.006),
              (2 * HW + 0.026, 2 * HL + 0.026, 0.012), case, rot=FROT,
              bevel=0.004))
    for i, (cu, cv, su, sv) in enumerate((
            (0.0, HL + 0.0075, 2 * HW + 0.026, 0.015),
            (0.0, -HL - 0.0075, 2 * HW + 0.026, 0.015),
            (-HW - 0.0075, 0.0, 0.015, 2 * HL + 0.026),
            (HW + 0.0075, 0.0, 0.015, 2 * HL + 0.026))):
        keep(_box(f"dnsm_body_wall_{i}", fp(cu, cv, -BODY_D / 2),
                  (su, sv, BODY_D), case, rot=FROT, bevel=0.004))
        keep(_box(f"dnsm_rim_{i}", fp(cu, cv, 0.014),
                  (su, sv, 0.016), brass, rot=FROT, bevel=0.003))

    for i in range(5):
        keep(_box(f"dnsm_vent_{i}", fp(-0.130 + 0.065 * i, -HL - 0.014,
                                       -BODY_D / 2),
                  (0.048, 0.008, BODY_D - 0.030), brass, rot=FROT, bevel=0.002))

    # ---------------------------------- face plate, with a hole for the drum
    for nm, cu, cv, su, sv in (
            ("left",  (-HW + WU0) / 2, 0.0, WU0 + HW, 2 * HL),
            ("right", (WU1 + HW) / 2, 0.0, HW - WU1, 2 * HL),
            ("under", (WU0 + WU1) / 2, (-HL + WV0) / 2, WU1 - WU0, WV0 + HL),
            ("over",  (WU0 + WU1) / 2, (WV1 + HL) / 2, WU1 - WU0, HL - WV1)):
        keep(_box(f"dnsm_face_{nm}", fp(cu, cv, 0.0), (su, sv, PLATE_T), panel,
                  rot=FROT, bevel=0.002))
    for i, (sx, sy) in enumerate(((-1, 1), (1, 1), (-1, -1), (1, -1))):
        keep(_box(f"dnsm_screw_{i}", fp(sx * (HW - 0.014), sy * (HL - 0.013),
                                        0.007),
                  (0.010, 0.010, 0.006), brass, rot=FROT, bevel=0.0015))

    # ------------------------------------------------------------- the scope
    # Everything phosphor lives PROUD of the face plate (front at h=+0.006):
    # the scope is a can bolted through the panel, not a recess.
    keep(_cyl("dnsm_scope_can", fp(SC_U, SC_V, SC_H - 0.014), SC_R + 0.014,
              0.022, hull_d, rot=FROT, verts=64))
    keep(_cyl("dnsm_scope_well", fp(SC_U, SC_V, SC_H - 0.0015), SC_R + 0.004,
              0.003, well, rot=FROT, verts=64))
    keep(_ring("dnsm_scope_bezel", fp(SC_U, SC_V, SC_H - 0.002), SC_R + 0.014,
               0.0065, brass, rot=FROT, seg=64))
    for i, f_ in enumerate((0.30, 0.56, 0.82)):
        keep(_ring(f"dnsm_scope_ring_{i}", fp(SC_U, SC_V, SC_H + 0.0012),
                   SC_R * f_, 0.0010, grid, rot=FROT, seg=64, mseg=6))
    for i in range(24):
        th = math.radians(i * 15.0)
        long_ = (i % 6 == 0)
        rr = SC_R * (0.895 if long_ else 0.938)
        ln = SC_R * (0.098 if long_ else 0.052)
        keep(_box(f"dnsm_scope_tick_{i}",
                  fp(SC_U + math.sin(th) * (rr + ln / 2),
                     SC_V + math.cos(th) * (rr + ln / 2), SC_H + 0.0012),
                  (0.0036 if long_ else 0.0024, ln, 0.0016), grid,
                  rot=(TILT, 0, -th)))
        if long_:
            keep(_box(f"dnsm_scope_spoke_{i}",
                      fp(SC_U + math.sin(th) * SC_R * 0.16,
                         SC_V + math.cos(th) * SC_R * 0.16, SC_H + 0.0012),
                      (0.0016, SC_R * 0.22, 0.0014), grid, rot=(TILT, 0, -th)))
    for lab, th in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
        t = math.radians(th)
        keep(_text(f"dnsm_scope_card_{lab}", lab, 0.0110, grid,
                   fp(SC_U + math.sin(t) * SC_R * 0.695,
                      SC_V + math.cos(t) * SC_R * 0.695, SC_H + 0.0016),
                   rot=FROT, align='CENTER'))
    keep(_cyl("dnsm_scope_hub", fp(SC_U, SC_V, SC_H + 0.004), 0.0068, 0.008,
              brass, rot=FROT, verts=20))

    # ------------------------------------------------- chart drum + window
    for i, (cu, cv, su, sv) in enumerate((
            ((WU0 + WU1) / 2, WV1 + 0.006, WU1 - WU0 + 0.024, 0.012),
            ((WU0 + WU1) / 2, WV0 - 0.006, WU1 - WU0 + 0.024, 0.012),
            (WU0 - 0.006, (WV0 + WV1) / 2, 0.012, WV1 - WV0 + 0.024),
            (WU1 + 0.006, (WV0 + WV1) / 2, 0.012, WV1 - WV0 + 0.024))):
        keep(_box(f"dnsm_win_trim_{i}", fp(cu, cv, 0.008), (su, sv, 0.010),
                  brass, rot=FROT, bevel=0.002))
    keep(_text("dnsm_win_label", "STAR CATALOGUE", 0.0088, brass,
               fp((WU0 + WU1) / 2, WV1 + 0.021, 0.007), rot=FROT,
               align='CENTER'))

    drum_piv = _empty("dnsm_drum_pivot", fp(DR_U, DR_V, DR_H))
    drum_piv.rotation_euler = FROT
    _adopt(drum_piv, root)
    drum_objs = []

    def drum(o, theta):
        """Place an object built at (x, y, z) in the facet-0 frame onto facet
        `theta`, then hang it off the drum pivot."""
        x, y, z = o.location
        c, s = math.cos(theta), math.sin(theta)
        o.location = (x, y * c - z * s, y * s + z * c)
        rx, ry, rz = o.rotation_euler
        o.rotation_euler = (rx + theta, ry, rz)
        _adopt(o, drum_piv)
        drum_objs.append(o)
        far.append(o)
        return o

    drum(_cyl("dnsm_drum_core", (0, 0, 0), DR_R - 0.014, DR_LEN - 0.010, core,
              rot=(0, math.pi / 2, 0), verts=DR_FACETS * 4), 0.0)
    for i, sx in enumerate((-1, 1)):
        drum(_cyl(f"dnsm_drum_cap_{i}", (sx * (DR_LEN / 2 + 0.005), 0, 0),
                  DR_R + 0.004, 0.010, brass, rot=(0, math.pi / 2, 0),
                  verts=DR_FACETS * 4), 0.0)
        drum(_cyl(f"dnsm_drum_hub_{i}", (sx * (DR_LEN / 2 + 0.014), 0, 0),
                  0.012, 0.020, hull_d, rot=(0, math.pi / 2, 0), verts=14), 0.0)
    chord = 2 * DR_R * math.sin(math.pi / DR_FACETS)
    for k in range(DR_FACETS):
        th = 2 * math.pi * k / DR_FACETS
        drum(_box(f"dnsm_chart_page_{k}", (0, 0, DR_R - 0.002),
                  (DR_LEN, chord, 0.004), paper), th)
        for j, line in enumerate(CHART_PAGES[k]):
            drum(_text(f"dnsm_chart_txt_{k}_{j}", line, 0.0076, ink,
                       (-0.070, 0.0185 - 0.0185 * j, DR_R + 0.001)), th)
        drum(_box(f"dnsm_chart_rule_{k}", (0, -chord / 2 + 0.004,
                                           DR_R + 0.0005),
                  (DR_LEN - 0.020, 0.0014, 0.0014), ink), th)

    # ------------------------------------------------- courier slot + card
    keep(_box("dnsm_slot_body", fp(CO_U, CO_V - 0.014, 0.014),
              (0.176, 0.040, 0.026), hull_d, rot=FROT, bevel=0.003))
    keep(_box("dnsm_slot_lip", fp(CO_U, CO_V + 0.004, 0.022),
              (0.176, 0.012, 0.016), brass, rot=FROT, bevel=0.002))
    keep(_text("dnsm_slot_label", "CHART COURIER", 0.0082, brass,
               fp(CO_U, CO_V - 0.030, 0.028), rot=FROT, align='CENTER'))
    keep(_cyl("dnsm_courier_cup", fp(CO_U + 0.100, CO_V + 0.002, 0.007), 0.011,
              0.008, brass, rot=FROT, verts=16))
    courier_dome = _sphere("dnsm_courier_dome", fp(CO_U + 0.100, CO_V + 0.002,
                                                   0.013),
                           0.0088, lamp_off, scale=(1, 1, 0.60), rot=FROT)
    _adopt(courier_dome, root)
    far.append(courier_dome)

    card_piv = _empty("dnsm_card_pivot", fp(CO_U, CO_V, 0.006))
    card_piv.rotation_euler = FROT
    _adopt(card_piv, root)
    card_objs = []

    def card(o):
        _adopt(o, card_piv)
        card_objs.append(o)
        far.append(o)
        return o

    card(_box("dnsm_card", (0, 0, 0), (0.140, CARD_H, 0.0032), paper))
    card(_box("dnsm_card_edge", (0, CARD_H / 2 - 0.004, 0.0019),
              (0.140, 0.005, 0.0016), ink))
    card(_text("dnsm_card_head", "CHART 44-12", 0.0072, ink,
               (-0.060, CARD_H / 2 - 0.015, 0.0022)))
    for j in range(3):
        w = 0.046 + 0.028 * (0.5 + 0.5 * math.sin(j * 1.9))
        card(_box(f"dnsm_card_txt_{j}", (-0.060 + w / 2,
                                         0.004 - 0.011 * j, 0.0019),
                  (w, 0.0046, 0.0016), ink))
    for j in range(3):
        card(_box(f"dnsm_card_punch_{j}", (0.040 + 0.013 * j,
                                           CARD_H / 2 - 0.016, 0.0019),
                  (0.007, 0.007, 0.0018), core))

    # ------------------------------------------ record-type lamps + labels
    lamp_domes, lamp_us = [], []
    for i, q in enumerate(QTYPES):
        u = -0.203 + 0.058 * i
        lamp_us.append(u)
        keep(_cyl(f"dnsm_lamp_cup_{i}", fp(u, LAMP_V, 0.007), 0.0125, 0.008,
                  brass, rot=FROT, verts=18))
        d = _sphere(f"dnsm_lamp_dome_{i}", fp(u, LAMP_V, 0.0125), 0.0098,
                    lamp_off, scale=(1, 1, 0.60), rot=FROT)
        _adopt(d, root)
        far.append(d)
        lamp_domes.append(d)
        keep(_text(f"dnsm_lamp_label_{i}", QLABELS[i], 0.0092, brass,
                   fp(u, LABEL_V, 0.006), rot=FROT, align='CENTER'))
    keep(_box("dnsm_lamp_rail", fp(0.0, LAMP_V - 0.020, 0.005),
              (0.446, 0.0026, 0.004), brass, rot=FROT))

    # ------------------------------------------------ titles + the readout
    keep(_text("dnsm_title", "NAV BEACON", 0.0122, brass,
               fp(-HW + 0.014, HL - 0.019, 0.007), rot=FROT, align='LEFT'))
    keep(_text("dnsm_subtitle", "DNSM  AUTH  UDP/TCP 8053", 0.0072, grid,
               fp(-HW + 0.014, HL - 0.038, 0.006), rot=FROT, align='LEFT'))
    readouts = {}
    for q in QTYPES:
        t = _text(f"dnsm_readout_{q.lower()}", QREADOUT[q], 0.0098, glyph,
                  fp(HW - 0.014, HL - 0.021, 0.007), rot=FROT, align='RIGHT')
        _adopt(t, root)
        far.append(t)
        readouts[q] = t

    # ----------------------------------------------------------- the blips
    blips = {}
    for q in QTYPES:
        objs = []
        for j, (bear, rf) in enumerate(QBLIPS[q]):
            th = math.radians(bear)
            bu = SC_U + math.sin(th) * SC_R * rf
            bv = SC_V + math.cos(th) * SC_R * rf
            rad = 0.0044 if q == "AXFR" else 0.0060
            o = _cyl(f"dnsm_blip_{q.lower()}_{j}", fp(bu, bv, SC_H + 0.0035),
                     rad, 0.0022, blip, rot=FROT, verts=14)
            _adopt(o, root)
            far.append(o)
            objs.append(o)
        blips[q] = objs

    # ----------------------------------------------------------- the sweep
    sweep_objs = []
    for i in range(SWEEP_STEPS):
        a1 = -SWEEP_ARC * i / SWEEP_STEPS
        a0 = -SWEEP_ARC * (i + 1) / SWEEP_STEPS
        f_ = 1.0 - i / SWEEP_STEPS
        m = _mat(f"dnsm_sweep_{i}", (0.10 + 0.26 * f_, 0.34 + 0.44 * f_,
                                     0.16 + 0.26 * f_, 1), 0.0, 0.40,
                 emission=(0.14, 0.92, 0.34, 1),
                 emit_strength=0.20 + 2.2 * f_ * f_)
        o = _sector(f"dnsm_sweep_sec_{i}", 0.004, SC_R * 0.930, a0, a1, m,
                    fp(SC_U, SC_V, SC_H + 0.0026), FROT, seg=6)
        _adopt(o, root)
        far.append(o)
        sweep_objs.append(o)
    edge = _mat("dnsm_sweep_edge", (0.52, 0.98, 0.62, 1), 0.0, 0.30,
                emission=(0.30, 1.0, 0.46, 1), emit_strength=2.2)
    o = _box("dnsm_sweep_edge", fp(SC_U, SC_V + SC_R * 0.465, SC_H + 0.0030),
             (0.0030, SC_R * 0.930, 0.0018), edge, rot=FROT)
    _adopt(o, root)
    far.append(o)
    sweep_objs.append(o)

    # ---------------------------------------------------------- rest poses
    for k, d in enumerate(lamp_domes):
        d.data.materials[0] = lamp_on if k == 0 else lamp_off
    for q, objs in blips.items():
        for o in objs:
            o.hide_render = (q != QTYPES[0])
    for q, t in readouts.items():
        t.hide_render = (q != QTYPES[0])
    card_piv.location = fp(CO_U, CO_V + 0.042, 0.006)
    bpy.context.view_layer.update()

    # ----------------------------------------------------------- placement
    loc, eul = slots.place(P, CODE)
    root.location = loc
    root.rotation_euler = eul
    root.scale = (SCALE, SCALE, SCALE)      # see SCALE, above
    bpy.context.view_layer.update()

    rest = [o for o in far if not o.hide_render]
    for o in far:
        o.hide_render = False

    return {
        "far": rest,          # what belongs in the wide shot, at rest
        "all": far,           # every object this module created
        "plate": plate,
        "root": root,
        "controls": {
            "sweep": {"objs": sweep_objs, "pivot": None, "kind": "rotate",
                      "label": "BEACON SWEEP", "range": [-180.0, 180.0],
                      "anchor": root.matrix_world @ fp(SC_U, SC_V, SC_H),
                      "scope": (SC_U, SC_V, SC_R)},
            "qtype": {"objs": [o for q in QTYPES for o in blips[q]] +
                              lamp_domes + list(readouts.values()),
                      "pivot": None, "kind": "states", "label": "QUERY TYPE",
                      "states": list(QTYPES), "blips": blips,
                      "domes": lamp_domes, "readouts": readouts,
                      "lamp_us": lamp_us,
                      "mats": {"off": lamp_off, "on": lamp_on,
                               "amber": lamp_amb, "red": lamp_red}},
            "chart": {"objs": drum_objs, "pivot": drum_piv, "kind": "frames",
                      "label": "STAR CHART", "frames": DR_FACETS,
                      "window": (WU0, WV0, WU1, WV1)},
            "courier": {"objs": card_objs + [courier_dome], "pivot": card_piv,
                        "kind": "states", "label": "CHART COURIER",
                        "states": list(COURIER_STATES), "card": card_objs,
                        "dome": courier_dome,
                        "mats": {"off": lamp_off, "on": lamp_amb}},
        },
    }


# ----------------------------------------------------- standalone renderer
def renderables(scene):
    return [o for o in scene.objects
            if o.type in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}]


def render_to(scene, path, visible, holdout=()):
    """Render only `visible`.  `holdout` objects stay in the depth buffer but
    punch alpha, so a sprite is correctly clipped by the static panel it lives
    behind (the chart drum behind its window, the card inside its slot)."""
    saved, hsave = {}, {}
    vis = set(o.name for o in visible)
    hold = set(o.name for o in holdout) - vis
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


def pts_rect(scene, cam, root, pts, pad=4):
    xs, ys = [], []
    for q in pts:
        x, y = project(scene, cam, root.matrix_world @ Vector(q))
        xs.append(x)
        ys.append(y)
    return {"x": round(min(xs) - pad), "y": round(min(ys) - pad),
            "w": round(max(xs) - min(xs) + 2 * pad),
            "h": round(max(ys) - min(ys) + 2 * pad)}


def clamp_rect(r, w, h):
    """Keep a hotspot inside the canvas -- the yoke runs up out of frame."""
    x0, y0 = max(0, r["x"]), max(0, r["y"])
    x1, y1 = min(w, r["x"] + r["w"]), min(h, r["y"] + r["h"])
    return {"x": x0, "y": y0, "w": max(0, x1 - x0), "h": max(0, y1 - y0)}


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
    """Close-up camera looking straight down the canted face normal, plus
    local fill lights.  Everything is parented into the prop frame."""
    bpy.ops.object.camera_add(location=(0, 0, 0))
    cam = bpy.context.object
    cam.name = "dnsm_closecam"
    cam.data.lens = 50.0
    _adopt(cam, root)
    cam.location = fp(0.0, 0.004, 1.10)
    cam.rotation_euler = FROT              # +Z = face normal, +Y = face up

    lights = []
    for i, (u, v, h, aim_u, aim_v, energy, size, col) in enumerate([
        (-0.34, 0.30, 0.34, -0.10, 0.05, 2.4, 0.30, (1.0, 0.90, 0.76)),
        (0.40, 0.16, 0.36, 0.12, 0.04, 1.5, 0.32, (0.74, 0.84, 1.0)),
        (0.02, -0.34, 0.30, 0.02, -0.13, 1.2, 0.26, (1.0, 0.86, 0.66)),
        (-0.10, 0.40, 0.22, -0.02, 0.14, 0.9, 0.24, (1.0, 0.84, 0.64)),
    ]):
        bpy.ops.object.light_add(type='AREA', location=(0, 0, 0))
        L = bpy.context.object
        L.name = f"dnsm_light_{i}"
        # root.scale pulls these lights SCALE x closer to the (now smaller)
        # face, so energy falls with the square of the distance -- otherwise the
        # close-up would brighten by 1/SCALE**2.
        L.data.energy, L.data.size = energy * SCALE ** 2, size
        L.data.color = col
        _adopt(L, root)
        L.location = fp(u, v, h)
        _aim(L, fp(aim_u, aim_v, 0.0))
        lights.append(L)
    return cam, lights


def glow_render(scene, path, objs):
    """Flat white emissive silhouette for the hover glow."""
    g = _mat("dnsm_glow", (1, 1, 1, 1), 0.0, 0.5,
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
    try:
        scene.view_settings.view_transform = vt
        scene.view_settings.look = look
    except Exception:
        pass
    for o in objs:
        for i, m in enumerate(saved[o.name]):
            o.data.materials[i] = m


HTML = """<!doctype html>
<meta charset="utf-8">
<title>DNSM - Nav Beacon / Star Charts</title>
<style>
 body{margin:0;background:#080b0a;color:#9fd8b2;
      font:13px/1.5 ui-monospace,Menlo,monospace}
 header{padding:14px 18px;border-bottom:1px solid #1d2a22}
 h1{margin:0;font-size:15px;letter-spacing:.18em;color:#7ef0a6}
 header p{margin:6px 0 0;color:#6d8478;max-width:76ch}
 code{color:#cbb48a}
 #stage{margin:14px 18px;overflow:hidden}
 #wrap{position:relative;width:1280px;height:720px;transform-origin:top left}
 #wrap img{position:absolute;left:0;top:0;width:1280px;height:720px}
 .hot{position:absolute;border:1px solid rgba(126,240,166,0);cursor:pointer}
 .hot:hover{border-color:rgba(126,240,166,.5);
            background:rgba(126,240,166,.05)}
 .hot span{position:absolute;left:0;top:-17px;font-size:10px;
           letter-spacing:.14em;color:#7ef0a6;opacity:0;white-space:nowrap}
 .hot:hover span{opacity:1}
 #hud{margin:0 18px 24px;padding:10px 14px;border:1px solid #1d2a22;
      display:inline-block;white-space:pre}
</style>
<header>
 <h1>DNSM &middot; NAV BEACON / STAR CHARTS</h1>
 <p>Yoke-mounted scope head hanging off the cockpit roof, its face canted
    60&deg; so it looks the pilot in the eye. The <b>sweep</b> spins on its
    own &mdash; drag it to slew the beacon by hand. Click the scope's
    <b>lamp row</b> to change query type: contacts appear on the plot, one
    record-type lamp burns, and the readout changes. <code>AXFR</code> paints
    the whole catalogue; <code>NXDOMAIN</code> paints nothing. Drag the
    <b>star chart</b> drum to roll through the zone. Click the
    <b>chart courier</b> slot to feed a chart in &mdash;
    <code>POST /admin/import</code>.</p>
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
      bits.push(c.label + ': ' + (state[id]+1) + '/' + c.frames.length);
    } else if (c.kind === 'rotate'){
      layers[id].style.transform = 'rotate(' + state[id].toFixed(1) + 'deg)';
      bits.push(c.label + ': ' + Math.round((state[id]+360)%360) + '\\u00b0');
    } else {
      layers[id].src = BASE + c.states[state[id]];
      bits.push(c.label + ': ' + state[id].toUpperCase());
    }
  }
  hud.textContent = bits.join('   |   ');
}

let SC = 1, spin = true;
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
      // 0deg = the sweep pointing up the face
      state[id] = -Math.atan2(ev.clientX - px, ev.clientY - py) * 180/Math.PI
                  + 180;
      if (state[id] > 180) state[id] -= 360;
      draw();
    };
    h.onmousedown = e => { spin = false; set(e); h.onmousemove = set; };
    h.onmouseup = h.onmouseleave = () => { h.onmousemove = null; };
    h.ondblclick = () => { spin = true; };
  }
}

// the beacon turns by itself until you grab it; double-click to let it go
const SWEEP = 'sweep';
function tick(){
  if (spin && SWEEP in state){
    state[SWEEP] = ((state[SWEEP] + 1.6 + 180) % 360) - 180;
    draw();
  }
  requestAnimationFrame(tick);
}

const stage = document.getElementById('stage');
function fit(){
  SC = Math.min(1, (window.innerWidth - 44) / 1280);
  wrap.style.transform = 'scale(' + SC + ')';
  stage.style.width = (1280 * SC) + 'px';
  stage.style.height = (720 * SC) + 'px';
}
window.addEventListener('resize', fit); fit();
draw(); tick();
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
    far_objs = res["all"]
    rest_far = res["far"]
    ctl = res["controls"]
    root = res["root"]
    shell_meshes = [o for o in renderables(scene) if o not in far_objs]

    # ------------------------------------------------------------ far shot
    render_to(scene, os.path.join(OUT, "far_prop.png"), rest_far)
    far_hot = clamp_rect(bbox_rect(scene, far_cam, rest_far, pad=8),
                         scene.render.resolution_x, scene.render.resolution_y)
    glow_render(scene, os.path.join(OUT, "far_glow.png"), rest_far)
    render_to(scene, os.path.join(OUT, "_shell_plate.png"), shell_meshes)

    # ---------------------------------------------------------- close shot
    cam, _lights = close_rig(root)
    scene.camera = cam
    bpy.context.view_layer.update()

    clip = res["plate"]                 # static prop parts that occlude sprites
    render_to(scene, os.path.join(OUT, "close_plate.png"), shell_meshes + clip)

    controls = {}

    # --- BEACON SWEEP: rendered once pointing up, spun in CSS -------------
    c = ctl["sweep"]
    render_to(scene, os.path.join(OUT, "close_sweep.png"), c["objs"],
              holdout=clip)
    px, py = project(scene, cam, c["anchor"])
    su, sv, sr = c["scope"]
    ring = [fp(su + math.sin(math.radians(a)) * (sr + 0.014),
               sv + math.cos(math.radians(a)) * (sr + 0.014), SC_H)
            for a in range(0, 360, 15)]
    controls["sweep"] = {"kind": "rotate", "label": "BEACON SWEEP",
                         "image": "close_sweep.png",
                         "pivot": {"x": round(px, 1), "y": round(py, 1)},
                         "range": [-180.0, 180.0], "spin": 1.6,
                         "hotspot": pts_rect(scene, cam, root, ring, pad=2)}

    # --- QUERY TYPE: contacts + one lamp + the readout --------------------
    c = ctl["qtype"]
    states, rects = {}, []
    for i, q in enumerate(c["states"]):
        lit = c["mats"]["red"] if q == "NX" else (
            c["mats"]["amber"] if q == "AXFR" else c["mats"]["on"])
        for k, d in enumerate(c["domes"]):
            on = (k == i) or (q == "AXFR" and QTYPES[k] != "NX")
            d.data.materials[0] = lit if on else c["mats"]["off"]
        vis = c["blips"][q] + c["domes"] + [c["readouts"][q]]
        bpy.context.view_layer.update()
        fn = f"close_qtype_{q.lower()}.png"
        render_to(scene, os.path.join(OUT, fn), vis, holdout=clip)
        states[q] = fn
        rects.append(bbox_rect(scene, cam, vis, pad=6))
    for k, d in enumerate(c["domes"]):
        d.data.materials[0] = c["mats"]["on"] if k == 0 else c["mats"]["off"]
    # The grab area is the LAMP ROW only.  The scope itself belongs to the
    # sweep (a bigger qtype rect would sit on top of it in the DOM and eat the
    # drag), and the lamps are the natural affordance for picking a record type.
    hot_pts = [fp(u + du, v, h) for u in c["lamp_us"] for du in (-0.026, 0.026)
               for v, h in ((LABEL_V - 0.010, 0.006), (LAMP_V + 0.013, 0.014))]
    controls["qtype"] = {"kind": "states", "label": "QUERY TYPE",
                         "states": states,
                         "hotspot": pts_rect(scene, cam, root, hot_pts, pad=3)}

    # --- STAR CHART: the lookup drum, one frame per facet -----------------
    c = ctl["chart"]
    piv = c["pivot"]
    frames = []
    for i in range(c["frames"]):
        piv.rotation_euler = (TILT - 2 * math.pi * i / c["frames"], 0, 0)
        bpy.context.view_layer.update()
        fn = f"close_chart_{i}.png"
        render_to(scene, os.path.join(OUT, fn), c["objs"], holdout=clip)
        frames.append(fn)
    piv.rotation_euler = FROT
    bpy.context.view_layer.update()
    wu0, wv0, wu1, wv1 = c["window"]
    win = [fp(wu0, wv0, 0.0), fp(wu1, wv0, 0.0),
           fp(wu0, wv1, 0.0), fp(wu1, wv1, 0.0)]
    controls["chart"] = {"kind": "frames", "label": "STAR CHART",
                         "frames": frames,
                         "hotspot": pts_rect(scene, cam, root, win, pad=4)}

    # --- CHART COURIER: card in the mouth / pushed home / gone ------------
    c = ctl["courier"]
    poses = {"chart": (0.042, "off"), "import": (-0.006, "on"),
             "empty": (None, "off")}
    states, rects = {}, []
    for nm in c["states"]:
        dv, lit = poses[nm]
        vis = [c["dome"]]
        if dv is not None:
            c["pivot"].location = fp(CO_U, CO_V + dv, 0.006)
            vis = c["card"] + [c["dome"]]
        c["dome"].data.materials[0] = c["mats"][lit]
        bpy.context.view_layer.update()
        fn = f"close_courier_{nm}.png"
        render_to(scene, os.path.join(OUT, fn), vis, holdout=clip)
        states[nm] = fn
    # from the slot geometry, not the bbox union: the swallowed card reaches
    # down behind the panel and would drag the rect into the lamp row
    rects = [pts_rect(scene, cam, root,
                      [fp(CO_U + du, CO_V + dv, 0.006)
                       for du in (-0.092, 0.092) for dv in (-0.022, 0.086)],
                      pad=3)]
    c["pivot"].location = fp(CO_U, CO_V + 0.042, 0.006)
    c["dome"].data.materials[0] = c["mats"]["off"]
    bpy.context.view_layer.update()
    controls["courier"] = {"kind": "states", "label": "CHART COURIER",
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

    print("DNSM far hotspot", json.dumps(far_hot))
    for k, v in controls.items():
        print("DNSM close", k, v["kind"], json.dumps(v["hotspot"]))
    print("DNSM OK ->", OUT)


if __name__ == "__main__":
    main()
