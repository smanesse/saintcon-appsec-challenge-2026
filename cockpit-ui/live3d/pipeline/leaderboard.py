"""
SAINTCON 2026 -- THE MUSTER BOARD.  Blender builder for live3d/modules/_LEADERBOARD/.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/leaderboard.py

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
It is NOT a module exporter.  The nine exporters under this directory take an
existing `cockpit/modules/<code>/build.py` snapshot, split it into a baked
plate plus live props, and emit a depth pass so the live geometry can be
composited into the plate.  The muster board has no snapshot, no plate and no
depth pass: the WHOLE board is live geometry, so there is nothing to composite
against and `depth.bin` / `ubias_m` / `light_gain` fitting do not arise.
live3d/design/LEADERBOARD.md section 4 is the decision and its reasoning.

It NEVER calls any `cockpit/` module's `main()` (CONVERSION_BRIEF trap 8 --
that writes `demo.html` and `out/` into a read-only tree).  It imports nothing
from `cockpit/`.  It builds a scene from nothing.

THE ONE IDEA THAT MAKES THIS WORK: FRONTO-PARALLEL BY CONSTRUCTION
------------------------------------------------------------------
The board face lies in the Blender XZ plane at y = 0.  The camera sits on the
-Y axis, looking straight down +Y, up = +Z.  So the mapping from the board's
face plane to the canonical 1280x720 stage is an exact similarity:

    px = 640 + x_m * PPM          py = 360 - z_m * PPM          (at y = 0)

with PPM = 2500 px/m.  That is why the DOM layer can be authored in raw stage
pixels and land ON the surface without css3d.js, without a declared readout
plane, and without a matrix3d.  The depth is in the LIGHT and in the parts that
step forward out of the face -- frame, podium, lamps, clamp -- not in a rake.

Every part is built so that its FRONT FACE projects to an exact stage-pixel
rectangle: a part standing `d` metres proud of the face plane is authored at
x_m = (px-640)/PPM * (D-d)/D, so it lands back on the same pixel.  Its back
face is then wider in screen space than its front, which is what makes the
inboard side walls visible and gives the board its parallax.  `LAYOUT` below is
the single source of truth for those rectangles and is emitted verbatim into
`scene.json`, so the geometry and `leaderboard.js` cannot drift apart.

TRAP 21 (`dress()` forces FrontSide and silently deletes one-sided geometry).
Every part here is a CLOSED PRISM built with bmesh and run through
`recalc_face_normals(..., outward)`.  There is not one open ribbon, one
single-quad label or one unclosed sweep in the file.  `facingAudit()` on the
live page is expected to return [].

TRAP 28: root_scale is 1.0 and is emitted as such.
TRAP 31: glTF is not byte-deterministic.  Re-running this script twice gives an
identical `scene.json` (compare it by bytes) and an identical triangle count /
accessor content in `board.glb` -- do not compare the .glb by hash.

OUTPUT -> live3d/assets/_leaderboard/
    board.glb           every part, named, one file
    scene.json          camera, lights, colour, LAYOUT, parts, hotspots
    materials.json      the Principled side channel (Blender drops these)
    gt_board.png        Blender's own render of pose(), the standard of proof
    gt_full_read.png    a copy of it under the name check/compare.py expects
    plate.png           a fully transparent 1280x720, ditto: this board has no
                        baked plate and compare.py composites canvas OVER plate
"""
import bpy, bmesh, math, os, sys, json
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)
ROOT = os.path.dirname(LIVE3D)
OUT = os.path.join(LIVE3D, "assets", "_leaderboard")
FONTS = os.path.join(ROOT, "fonts")

W, H = 1280, 720
PPM = 2500.0                 # stage px per metre ON THE FACE PLANE (y = 0)
CAM_D = 0.62                 # camera distance to the face plane, metres

# ===========================================================================
# LAYOUT -- every rectangle on the board, in canonical stage pixels.
# This dict is emitted into scene.json unchanged and read by leaderboard.js.
# Nothing in either the geometry or the DOM may retype one of these numbers.
# ===========================================================================
LAYOUT = {
    "stage": [W, H],
    "ppm": PPM,
    "cam_d": CAM_D,

    # the object
    "board":  [130, 14, 1150, 706],
    "inner":  [154, 38, 1106, 662],

    # header: engraved title (geometry) over a DOM sub-plate strip
    "header":      [154, 38, 1106, 96],
    "header_text": [172, 40, 1088, 70],
    "subplate":    [166, 74, 1094, 94],

    # the podium: three plinths, descending.  Each carries a band (cast
    # numeral left, valve lamp right) and a plaque (DOM name + points).
    "podium": [154, 102, 1106, 296],
    "steps": [[160, 102, 465, 296],
              [477, 128, 783, 296],
              [795, 154, 1100, 296]],
    "plaques": [[172, 164, 453, 290],
                [489, 190, 771, 290],
                [807, 216, 1088, 290]],
    "numerals": [[178, 108, 246, 158],
                 [495, 134, 563, 184],
                 [813, 160, 881, 210]],
    "lamps": [[404, 106, 452, 160],
              [721, 132, 769, 186],
              [1039, 158, 1087, 212]],

    # the rack.  The eight slats occupy 358.4 px of well.  That number used to
    # be shared by a SECOND, 16-slat "desk" set built on the same span, so the
    # chassis would not resize between the two modes.  There is one mode now
    # (design/LEADERBOARD.md 6.1) and the constraint it was protecting is
    # gone; what remains true, and is the reason the well is still a fixed
    # 358.4 px, is that nothing in this geometry is a function of
    # entries.length -- a five-hand board has eight slats like a five-hundred-
    # hand board does.
    "rack": [154, 300, 1106, 660],
    "slat_x": [158, 1102],
    "tab_x": [158, 190],              # the left lug: the only place mechanism
                                      # is allowed to touch a row
    # THE TYPE COLUMNS START AT 220, NOT AT THE TAB'S EDGE, AND THAT IS
    # MEASURED.  Section 4.3 requires 6 px of keep-out between any MECHANISM
    # mesh's projected bounding box and any DOM text rect.  The mechanism that
    # reaches furthest inboard is the clamp body, whose FRONT face is built to
    # land at 200 px but whose BACK face -- 15 mm further from the camera --
    # projects to 210.6 px, because a prism seen from in front shows its
    # inboard side wall.  The first attempt put the rank column at 198 and
    # window.__board.clearance() reported 26,841 px^2 of overlap over 24 poses.
    # 220 gives 9.4 px.  The number to keep clear is the BACK face, never the
    # front.
    "col_rank": [220, 268],
    "col_rank_right": 268,
    "col_name": [280, 872],
    # ...and the points column stops at 1086, not at the slat's edge, for the
    # mirror-image reason: the index wheel's own back face projects inboard to
    # 1097.3 px.  clearance() read 3.31 px of keep-out at 1094 and 11.3 at
    # 1086.  Both ends of every row are set by a MEASURED bounding box.
    "col_points_right": 1086,
    # THE ROW, AND THERE IS EXACTLY ONE.  This was `modes: {desk, tv}` -- 16
    # slots at 14 px and 8 at 28 px -- and the 14 px half does not survive
    # contact with a television.  MEASURED on a real 1920x1080 capture of the
    # running page, not derived from the font size: the 14 px row renders a
    # cap height of 8.29 canonical px against a 16 px floor, and its
    # worst-pixel legibility margin is 0.4433 against a 0.45 floor.  It failed
    # BOTH acceptances at TV size while nobody was looking, because nobody had
    # ever pointed the desk mode at a television.  The 28 px row measures
    # 17.33 canonical px and 0.4629 at the same capture.
    #
    # So the surviving row is the one that is legible at three metres, and the
    # desk pays for it in density -- eight rows at a time instead of sixteen,
    # with the pointer scrolling for the rest.  design/LEADERBOARD.md 6.1.
    "row": {"slots": 8, "y0": 300.0, "pitch": 44.8, "h": 40.0, "font": 28.0},

    # the bottom rail: the spring clamp and the docked row, or -- when the
    # FEED CARRIES NO `self` -- a blanking plate, because a clamp with nothing
    # in it is a lie about the data when there is no "you".  That used to be a
    # property of the MODE (the TV ran on a dummy account); it is a property of
    # the DOCUMENT now, which is what it was always really about.
    "rail":      [154, 662, 1106, 706],
    "pin_slat":  [158, 670, 1102, 698],
    "clamp":     [150, 664, 200, 704],
    "rail_blank": [154, 664, 232, 704],

    # the index wheel, in the right rail, out of every type column
    "wheel": {"cx": 1128.0, "cy": 480.0, "r": 17.0, "teeth": 12},
}

# depths, metres, NEGATIVE = toward the camera (proud of the face plane)
D_RACKBACK_F, D_RACKBACK_B = 0.012, 0.019
D_SLAT_F,     D_SLAT_B     = 0.000, 0.012
D_TAB_F,      D_TAB_B      = -0.002, 0.012
D_TAB_RAISED               = -0.0035          # the "you are here" lug
D_FRAME_F,    D_FRAME_B    = -0.010, 0.016
D_HEAD_F,     D_HEAD_B     = -0.012, 0.000
D_HTEXT_F                  = -0.0145
D_STEP_F                   = [-0.018, -0.014, -0.010]
D_STEP_B                   = 0.014
D_BEZEL                    = 0.0025           # plaque bezel proud of its step
D_NUM                      = 0.0020           # numeral proud of the bezel
D_SUBPLATE_F, D_SUBPLATE_B = -0.014, -0.010
D_PIN_F,      D_PIN_B      = -0.016, -0.010
D_CLAMP_F,    D_CLAMP_B    = -0.017, -0.002
D_WHEEL_F,    D_WHEEL_B    = -0.015, -0.004
D_BLANK_F,    D_BLANK_B    = -0.018, -0.010
D_BACK_F,     D_BACK_B     = 0.014, 0.021


# ------------------------------------------------------------- px <-> metres
def X(px, d):
    """Stage x px -> Blender x metres, for a face standing at depth `d`
    (negative = toward the camera), so that it projects back to `px`."""
    return (px - 640.0) / PPM * (CAM_D + d) / CAM_D


def Z(py, d):
    return (360.0 - py) / PPM * (CAM_D + d) / CAM_D


def to3(v):
    """Blender Z-up world -> three.js / glTF Y-up world.  Same map as
    three-exploration/pipeline/transliterate.py:to3, on purpose."""
    return [v[0], v[2], -v[1]]


# ------------------------------------------------------------------ materials
def mat(name, base, metallic, rough, emission=(0, 0, 0), emit=0.0, alpha=1.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (base[0], base[1], base[2], 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    b.inputs["Emission Color"].default_value = (emission[0], emission[1],
                                                emission[2], 1.0)
    b.inputs["Emission Strength"].default_value = emit
    b.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        m.blend_method = 'BLEND'
    return m


# ------------------------------------------------------------------- geometry
def prism(name, pts, d_front, d_back, material):
    """A CLOSED prism.  `pts` is a polygon in stage pixels; the front face is
    authored at depth `d_front` so it projects to exactly those pixels, and the
    prism is extruded straight back to `d_back` at constant x/z -- so the
    inboard side walls are visible and catch the raking light, which is where
    the board's depth comes from.  Normals are recalculated OUTWARD: trap 21
    deletes one-sided geometry silently and this file gives it nothing to
    delete."""
    n = len(pts)
    vs = [(X(px, d_front), d_front, Z(py, d_front)) for px, py in pts] + \
         [(X(px, d_front), d_back,  Z(py, d_front)) for px, py in pts]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], faces)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material)
    return ob


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def box(name, r, d_front, d_back, material):
    return prism(name, rect(*r), d_front, d_back, material)


def capsule(x0, y0, x1, y1, seg=8):
    """A vertical rounded-rect polygon in stage px -- the profile of a valve
    envelope.  Screen CCW is irrelevant: prism() recalculates normals."""
    r = (x1 - x0) / 2.0
    cx = (x0 + x1) / 2.0
    pts = []
    for i in range(seg + 1):                       # top dome, left -> right
        a = math.pi - math.pi * i / seg
        pts.append((cx - r * math.cos(a), y0 + r - r * math.sin(a)))
    pts.append((x1, y1))
    pts.append((x0, y1))
    return pts


def disc(name, cx, cy, r, seg, d_front, d_back, material, phase=0.0):
    pts = [(cx + r * math.cos(phase + 2 * math.pi * i / seg),
            cy + r * math.sin(phase + 2 * math.pi * i / seg))
           for i in range(seg)]
    return prism(name, pts, d_front, d_back, material)


def bevel(ob, width, segments=1):
    """A real bevel, applied.  The rivets and the slat edges are what turn one
    raking key light into the zebra banding and the frame's relief -- there is
    no CSS stripe anywhere in this component."""
    bpy.context.view_layer.objects.active = ob
    m = ob.modifiers.new("bev", 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(30)
    bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


def text_mesh(name, body, r, d_front, thick, material, bold=True):
    """A FONT object, converted to mesh, scaled so its ink bounding box fits
    the pixel rect `r`.  resolution_u = 2: FIX_UPLOAD 799-802 measured the
    default of 12 at 6,800 tris for one five-letter word against 1,096."""
    bpy.ops.object.text_add()
    ob = bpy.context.object
    ob.name = name
    ob.data.body = body
    ob.data.resolution_u = 2
    ob.data.extrude = thick * 0.5
    ob.data.align_x = 'CENTER'
    ob.data.align_y = 'CENTER'
    f = os.path.join(FONTS, "CourierPrime-Bold.ttf" if bold
                     else "CourierPrime-Regular.ttf")
    if os.path.exists(f):
        ob.data.font = bpy.data.fonts.load(f, check_existing=True)
    bpy.ops.object.convert(target='MESH')
    ob = bpy.context.object
    ob.name = name
    ob.data.name = name
    # A Blender FONT lies in its own XY plane and extrudes along +/-Z.  The
    # board face is the XZ plane and "toward the camera" is -Y, so the mesh is
    # rotated +90 deg about X FIRST -- (x,y,z) -> (x,-z,y) -- which puts the
    # cap height on world Z and the extrusion on world Y.  Measuring the bbox
    # before this rotation measures the EXTRUSION as the cap height and the
    # fit scale comes out ~40x too large; that is what the first run drew.
    ob.rotation_euler = (math.radians(90), 0.0, 0.0)
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

    # measure, then fit into the rect at the requested depth
    bb = [Vector(c) for c in ob.bound_box]
    x0 = min(c.x for c in bb); x1 = max(c.x for c in bb)
    z0 = min(c.z for c in bb); z1 = max(c.z for c in bb)
    tx0, ty0, tx1, ty1 = r
    TX0, TX1 = X(tx0, d_front), X(tx1, d_front)
    TZ1, TZ0 = Z(ty0, d_front), Z(ty1, d_front)
    s = min((TX1 - TX0) / max(1e-9, x1 - x0), (TZ1 - TZ0) / max(1e-9, z1 - z0))
    ob.scale = (s, 1.0, s)
    ob.location = ((TX0 + TX1) / 2 - (x0 + x1) / 2 * s,
                   d_front + thick * 0.5,
                   (TZ0 + TZ1) / 2 - (z0 + z1) / 2 * s)
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear()
    ob.data.materials.append(material)
    return ob


# ===========================================================================
def build():
    # a genuinely empty scene, not the startup cube
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    M = {
        "brass":       mat("brass",       (0.62, 0.44, 0.13), 1.0, 0.30),
        "brass_dark":  mat("brass_dark",  (0.30, 0.21, 0.07), 1.0, 0.46),
        "brass_lit":   mat("brass_lit",   (0.74, 0.56, 0.20), 1.0, 0.22),
        "steel":       mat("steel",       (0.42, 0.45, 0.50), 1.0, 0.34),
        "bakelite":    mat("bakelite",    (0.011, 0.010, 0.009), 0.0, 0.70),
        # THE RACK IS DARK ON PURPOSE.  The DOM rows are cream ink on these
        # slats and design section 8.3 wants a worst-PIXEL luma margin of 0.45,
        # not an average.  A mid-tone slat cannot deliver that under a raking
        # key light, because the bevel highlight is the pixel that fails.
        # 0.030 was not dark enough and the number says so: the worst
        # background pixel under a row's name came out at luma 0.4232 against
        # cream ink at 0.842, a 0.419 margin where 0.45 is required.  The
        # offending pixel is the slat's own BEVEL HIGHLIGHT at the top edge of
        # the row rect -- so the albedo comes down AND the bevel comes in.
        "slat":        mat("slat",        (0.017, 0.0145, 0.012), 0.0, 0.64),
        "slat_alt":    mat("slat_alt",    (0.012, 0.0100, 0.008), 0.0, 0.68),
        # THE PODIUM FIELD IS DARK AND ITS TYPE IS CREAM, like the rack.
        # It was the other way round first -- bright brass plates with dark
        # engraved type -- and it FAILED THE LEGIBILITY METRIC OUTRIGHT: the
        # fleet's number is the worst SINGLE background pixel under the type
        # (STATUS_AT_A_GLANCE 265-305), and a raking key light puts a
        # near-black pixel inside step II's bezel, so dark ink scored a 0.0014
        # margin there against a 0.45 requirement.  A bright plate cannot be
        # made safe for dark type under a raking light; a dark plate can be
        # made safe for light type, because the light is what is controlled.
        # The brass-to-steel ramp moves to the PLINTH, which is where a step's
        # colour belongs anyway, and the podium keeps its warm-to-cool read.
        "plaque":      mat("plaque",      (0.020, 0.017, 0.014), 0.0, 0.62),
        "plaque_2":    mat("plaque_2",    (0.017, 0.016, 0.015), 0.0, 0.64),
        "plaque_3":    mat("plaque_3",    (0.015, 0.015, 0.017), 0.0, 0.66),
        "plinth":      mat("plinth",      (0.62, 0.44, 0.13), 1.0, 0.30),
        "plinth_2":    mat("plinth_2",    (0.56, 0.45, 0.26), 1.0, 0.32),
        "plinth_3":    mat("plinth_3",    (0.50, 0.51, 0.50), 1.0, 0.34),
        "glass":       mat("glass",       (0.86, 0.80, 0.66), 0.0, 0.10,
                           emission=(1.0, 0.80, 0.46), emit=1.0),
        "filament":    mat("filament",    (1.0, 0.86, 0.55), 0.0, 0.20,
                           emission=(1.0, 0.72, 0.32), emit=6.0),
        "engrave":     mat("engrave",     (0.80, 0.66, 0.34), 1.0, 0.24),
    }
    PART = {}                      # group name -> [object names]

    def tag(group, ob):
        PART.setdefault(group, []).append(ob.name)
        return ob

    B = LAYOUT["board"]; I = LAYOUT["inner"]

    # ---------------------------------------------------------------- frame
    # A heavy mitred brass surround.  Four closed prisms, not one ring, so the
    # mitre lines are real edges the key light can catch.
    tag("frame", bevel(box("frame_top",   [B[0], B[1], B[2], I[1]],
                           D_FRAME_F, D_FRAME_B, M["brass"]), 0.0011))
    tag("frame", bevel(box("frame_bottom", [B[0], I[3], B[2], B[3]],
                           D_FRAME_F, D_FRAME_B, M["brass"]), 0.0011))
    tag("frame", bevel(box("frame_left",  [B[0], I[1], I[0], I[3]],
                           D_FRAME_F, D_FRAME_B, M["brass"]), 0.0011))
    tag("frame", bevel(box("frame_right", [I[2], I[1], B[2], I[3]],
                           D_FRAME_F, D_FRAME_B, M["brass"]), 0.0011))

    # slot-head rivets at the joints and along the rails
    rv = []
    for x in (142, 640, 1138):
        rv += [(x, 26), (x, 684)]
    for y in (140, 300, 460, 620):
        rv += [(142, y), (1128, y)]
    for i, (cx, cy) in enumerate(rv):
        ob = disc("rivet_%02d" % i, cx, cy, 7.0, 10,
                  D_FRAME_F - 0.0016, D_FRAME_F, M["brass_lit"])
        bevel(ob, 0.0004)
        tag("frame", ob)

    # ------------------------------------------------------- header + sub-plate
    tag("frame", bevel(box("header_plate", LAYOUT["header"],
                           D_HEAD_F, D_HEAD_B, M["brass_dark"]), 0.0008))
    # THE HEADER IS GEOMETRY.  It is a permanent label stamped on the ship, not
    # a value a player reads (CONVERSION_BRIEF 1786-1789), so it is cast metal.
    tag("frame", text_mesh("header_text", "SHIP'S COMPANY — STANDINGS",
                           LAYOUT["header_text"], D_HTEXT_F, 0.0018,
                           M["engrave"]))
    # The sub-plate is PROUD of the header plate, not recessed into it: it is a
    # separate dark strip screwed on, and it is the carrier for the four DOM
    # strings the header shows (field size, page, staleness, FINAL).
    # NO BEVEL ON THE SUB-PLATE.  It had one, and its highlight was the worst
    # background pixel on the whole board: luma 0.400 under the header's own
    # DOM strings, a 0.442 margin against a 0.45 requirement.  A bevel is a
    # specular line, and a specular line under type is the one place this board
    # cannot afford one.  The frame, the rails and the slats keep theirs --
    # nothing is written on those edges.
    tag("frame", box("subplate", LAYOUT["subplate"],
                     D_SUBPLATE_F, D_SUBPLATE_B, M["bakelite"]))

    # ----------------------------------------------------------------- rack
    # A back panel over the WHOLE inner opening, not just the rack: without it
    # the gaps beside the two shorter podium steps punch a hole straight
    # through the board to the page background.
    tag("rack", box("board_back", LAYOUT["inner"],
                    D_BACK_F, D_BACK_B, M["bakelite"]))
    tag("rack", box("rack_back", LAYOUT["rack"],
                    D_RACKBACK_F, D_RACKBACK_B, M["bakelite"]))

    tx0, tx1 = LAYOUT["tab_x"]
    sx0, sx1 = LAYOUT["slat_x"]
    # ONE SET OF SLATS.  This loop used to run twice -- `slat_desk_00..15` and
    # `slat_tv_00..07`, 48 meshes, of which 24 were hidden on every frame the
    # board has ever drawn.  Both sets shipped inside board.glb and the
    # frontend picked one with `show(G.slat_desk, !isTV)`.  There is one row
    # now, so there is one set, and the names lose the mode infix they no
    # longer distinguish anything by.
    cfg = LAYOUT["row"]
    for i in range(cfg["slots"]):
        y0 = cfg["y0"] + i * cfg["pitch"]
        y1 = y0 + cfg["h"]
        # alternating bevel depth gives the zebra banding out of the LIGHT
        m = M["slat"] if (i % 2 == 0) else M["slat_alt"]
        ob = box("slat_%02d" % i, [tx1 + 2, y0, sx1, y1],
                 D_SLAT_F, D_SLAT_B, m)
        bevel(ob, 0.0006 if (i % 2 == 0) else 0.00035)
        tag("slat", ob)
        # the LEFT TAB.  Every moving part on this board touches a row
        # here and nowhere else -- design section 4.3.
        t = box("tab_%02d" % i, [tx0, y0, tx1, y1],
                D_TAB_F, D_TAB_B, M["brass"])
        bevel(t, 0.0008)
        tag("tab", t)

    # --------------------------------------------------------------- podium
    plaq = [M["plaque"], M["plaque_2"], M["plaque_3"]]
    plin = [M["plinth"], M["plinth_2"], M["plinth_3"]]
    for i in range(3):
        s = LAYOUT["steps"][i]
        df = D_STEP_F[i]
        ob = box("pod_step_%d" % (i + 1), s, df, D_STEP_B, plin[i])
        bevel(ob, 0.0013)
        tag("podium", ob)
        p = LAYOUT["plaques"][i]
        ob = box("pod_bezel_%d" % (i + 1), p, df - D_BEZEL, df, plaq[i])
        bevel(ob, 0.0007)
        tag("podium", ob)

        # THE NINE NUMERALS.  A podium has exactly three places and standard
        # competition ranking admits only 1, 2, 3 on them (1,1,1 / 1,1,3 /
        # 1,2,2 / 1,2,3), so three cast numerals per step covers every case
        # including every tie.  They are permanent stamped metal and never
        # need the DOM.  design section 4.1.
        for k, roman in enumerate(("I", "II", "III")):
            r = LAYOUT["numerals"][i]
            n = text_mesh("num_%d_%s" % (i + 1, roman), roman, r,
                          df - D_BEZEL - D_NUM, 0.0016, M["engrave"])
            tag("numeral", n)

        # the valve lamp: envelope, filament stem, brass base.  The only
        # emissive geometry on the board.
        L = LAYOUT["lamps"][i]
        cx = (L[0] + L[2]) / 2.0
        tag("lamp", bevel(box("lamp_base_%d" % (i + 1),
                              [cx - 15, L[3] - 16, cx + 15, L[3]],
                              df - 0.007, df, M["brass"]), 0.0009))
        tag("lamp", prism("lamp_stem_%d" % (i + 1),
                          rect(cx - 2, L[1] + 12, cx + 2, L[3] - 15),
                          df - 0.013, df - 0.009, M["filament"]))
        g = prism("lamp_glass_%d" % (i + 1),
                  capsule(cx - 16, L[1] + 2, cx + 16, L[3] - 14, 8),
                  df - 0.017, df - 0.005, M["glass"])
        tag("lamp", g)

    # ------------------------------------------------------------ bottom rail
    # the docked row and its spring clamp, or a blanking plate when the feed
    # names no `self` -- both are built, and paint() picks on the DATA
    ob = box("pin_slat", LAYOUT["pin_slat"], D_PIN_F, D_PIN_B, M["slat"])
    bevel(ob, 0.0009)
    tag("pin", ob)
    ob = box("pin_tab", [tx0, LAYOUT["pin_slat"][1], tx1,
                         LAYOUT["pin_slat"][3]], D_PIN_F - 0.002, D_PIN_B,
             M["brass"])
    bevel(ob, 0.0008)
    tag("pin", ob)

    C = LAYOUT["clamp"]
    cmid = (C[1] + C[3]) / 2.0
    tag("clamp", bevel(box("clamp_body", [C[0], cmid - 5, C[2], cmid + 5],
                           D_CLAMP_F, D_CLAMP_B, M["steel"]), 0.0008))
    # The jaws hinge about a HORIZONTAL axis at the clamp's own left edge, so
    # their travel is entirely in z and y.  They cannot move in x, which is
    # what makes "the clamp never enters a type column" a property of the
    # construction rather than an assertion -- the rank column starts at 198 px
    # and the clamp's whole bounding box ends at 200 px minus the jaw sweep.
    tag("clamp", bevel(box("clamp_jaw_up", [C[0] + 4, C[1], C[2] - 6, cmid - 4],
                           D_CLAMP_F, D_CLAMP_B, M["steel"]), 0.0007))
    tag("clamp", bevel(box("clamp_jaw_lo", [C[0] + 4, cmid + 4, C[2] - 6, C[3]],
                           D_CLAMP_F, D_CLAMP_B, M["steel"]), 0.0007))
    tag("clamp", disc("clamp_pivot", C[0] + 9, cmid, 6.0, 10,
                      D_CLAMP_F - 0.002, D_CLAMP_B, M["brass_lit"]))

    R = LAYOUT["rail_blank"]
    tag("blank", bevel(box("rail_blank", R, D_BLANK_F, D_BLANK_B,
                           M["brass"]), 0.0011))
    tag("blank", disc("rail_blank_rivet_0", R[0] + 16, (R[1] + R[3]) / 2, 7.0,
                      10, D_BLANK_F - 0.0016, D_BLANK_F, M["brass_lit"]))
    tag("blank", disc("rail_blank_rivet_1", R[2] - 16, (R[1] + R[3]) / 2, 7.0,
                      10, D_BLANK_F - 0.0016, D_BLANK_F, M["brass_lit"]))

    # ----------------------------------------------------------- index wheel
    # A ratchet that steps one tooth per page advance and visibly runs back on
    # the carriage return.  It lives in the right rail: its bounding box ends
    # 16 px clear of the points column's right edge.
    Wl = LAYOUT["wheel"]
    n = Wl["teeth"] * 2
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = Wl["r"] if (i % 2 == 0) else Wl["r"] * 0.62
        pts.append((Wl["cx"] + rr * math.cos(a), Wl["cy"] + rr * math.sin(a)))
    tag("wheel", bevel(prism("wheel", pts, D_WHEEL_F, D_WHEEL_B, M["steel"]),
                       0.0005))
    tag("wheel", disc("wheel_hub", Wl["cx"], Wl["cy"], 5.0, 10,
                      D_WHEEL_F - 0.0018, D_WHEEL_B, M["brass_lit"]))

    return scene, PART


# ------------------------------------------------------------------- lighting
def add_lights(scene):
    """Real Blender area lights, warm, low, raking from upper left, exported
    into scene.json -> lights and rebuilt as three RectAreaLights by
    leaderboard.js.  This is where the board's 3D actually lives: the rivets
    and the slat bevels throw shadows, and the podium steps separate."""
    spec = [
        ("key",    (-0.56, -0.60,  0.46), (0.62, -0.62, -0.48), 0.50,  46.0,
         (1.00, 0.86, 0.68)),
        ("fill",   ( 0.62, -0.74,  0.06), (-0.66, -0.74, -0.10), 0.62, 13.0,
         (0.78, 0.85, 1.00)),
        ("top",    ( 0.02, -0.26,  0.52), (-0.04, -0.42, -0.92), 0.80, 17.0,
         (1.00, 0.90, 0.74)),
        ("bounce", ( 0.00, -0.40, -0.52), (0.00, -0.42,  0.90),  0.72,  6.0,
         (1.00, 0.82, 0.62)),
    ]
    L = LAYOUT["lamps"]
    for i in range(3):
        cx = (L[i][0] + L[i][2]) / 2.0
        spec.append(("valve%d" % (i + 1),
                     (X(cx, -0.03), -0.030, Z(L[i][1] + 20, -0.03)),
                     (0.0, -1.0, 0.0), 0.035, 0.55, (1.00, 0.74, 0.38)))
    for name, pos, d, size, energy, col in spec:
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(ob)
        ob.location = pos
        v = Vector(d).normalized()
        ob.rotation_euler = v.to_track_quat('-Z', 'Y').to_euler()
    scene.world = bpy.data.worlds.new("world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = \
        (0.014, 0.016, 0.024, 1.0)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0


def add_camera(scene):
    cd = bpy.data.cameras.new("cam")
    # Fronto-parallel by construction: on the -Y axis, looking straight down
    # +Y, up = +Z.  The lens is DERIVED from the pixel scale, not chosen:
    # half the frame height at the face plane must be 360/PPM metres.
    half = (H / 2.0) / PPM
    fov_y = 2 * math.atan(half / CAM_D)
    angle_x = 2 * math.atan(math.tan(fov_y / 2) * W / H)
    cd.sensor_fit = 'AUTO'
    cd.sensor_width = 36.0
    cd.lens = 18.0 / math.tan(angle_x / 2)
    cd.clip_start = 0.01
    cd.clip_end = 100.0
    ob = bpy.data.objects.new("cam", cd)
    scene.collection.objects.link(ob)
    ob.location = (0.0, -CAM_D, 0.0)
    ob.rotation_euler = (math.radians(90), 0.0, 0.0)     # -Z -> +Y, up -> +Z
    scene.camera = ob
    return ob


# ------------------------------------------------------------------- emitters
def cam_json(scene, cam):
    m = cam.matrix_world
    fov_y = math.degrees(2 * math.atan(
        math.tan(cam.data.angle_x / 2) * H / W))
    return {"lens_mm": cam.data.lens, "sensor_mm": cam.data.sensor_width,
            "sensor_fit": cam.data.sensor_fit,
            "angle_x_deg": math.degrees(cam.data.angle_x),
            "angle_y_deg_BLENDER_DO_NOT_USE": math.degrees(cam.data.angle_y),
            "fov_y_deg": fov_y,
            "clip": [cam.data.clip_start, cam.data.clip_end],
            "pos": to3(m.translation),
            "forward": to3((m.to_3x3() @ Vector((0, 0, -1))).normalized()),
            "up": to3((m.to_3x3() @ Vector((0, 1, 0))).normalized())}


def lights_json(scene):
    out = []
    for L in scene.objects:
        if L.type != 'LIGHT':
            continue
        m = L.matrix_world
        out.append({"tag": L.name, "type": L.data.type,
                    "pos": to3(m.translation),
                    "dir": to3((m.to_3x3() @ Vector((0, 0, -1))).normalized()),
                    "energy": L.data.energy,
                    "size": getattr(L.data, "size", 0.1),
                    "color": list(L.data.color)})
    out.sort(key=lambda d: d["tag"])
    return out


def materials_json():
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
        out[m.name] = {"base": val("Base Color"), "metallic": val("Metallic"),
                       "rough": val("Roughness"),
                       "emission": val("Emission Color"),
                       "emit": val("Emission Strength"),
                       "alpha": val("Alpha", 1.0),
                       "node_driven": [i.name for i in b.inputs if i.is_linked]}
    return out


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


def transparent_png(path, w, h):
    """A fully transparent w x h RGBA PNG, stdlib only.  This board has no
    baked plate; check/compare.py composites the canvas OVER a plate and this
    is the honest identity element for that composite."""
    import zlib, struct
    raw = b"".join(b"\x00" + b"\x00" * (w * 4) for _ in range(h))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I",
                                                           zlib.crc32(c))
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    open(path, "wb").write(png)


# ===========================================================================
def main():
    os.makedirs(OUT, exist_ok=True)
    scene, PART = build()
    add_lights(scene)
    cam = add_camera(scene)

    scene.render.resolution_x, scene.render.resolution_y = W, H
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = int(os.environ.get("SAMPLES", "128"))
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0.0

    meshes = [o for o in scene.objects if o.type == 'MESH']
    tris = 0
    for o in meshes:
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    print("parts %d   triangles %d" % (len(meshes), tris))

    export_glb(meshes, os.path.join(OUT, "board.glb"))

    # THE REFERENCE RENDER IS THE pose() STATE, and getting this combination
    # wrong is not a cosmetic error -- it points check/compare.py at a picture
    # the page never draws, which is a checker measuring a subject that does
    # not exist.  IT WAS WRONG.  The shipped gt_board.png was rendered with
    # the SIXTEEN desk slats visible and the eight TV slats hidden, so the
    # moment anyone opened `?tv=1` -- the mode built for the conference, the
    # one on the hallway television -- the rms number compared an 8-slat board
    # against a 16-slat render and reported on nothing.  The 23.78 in
    # design/LEADERBOARD.md 9 is a DESK number and was only ever a desk number.
    #
    # pose() now draws: the eight slats, the clamp closed on the docked row
    # (the shipped feed carries a `self`, so the clamp is what the data asks
    # for and the blanking plate is not), numerals I / II / III on steps
    # 1 / 2 / 3, index wheel and camera breath parked at phase 0.
    hide = set(PART.get("blank", []))
    for i in (1, 2, 3):
        for roman in ("II", "III"):
            if not (i == 2 and roman == "II") and not (i == 3 and roman == "III"):
                hide.add("num_%d_%s" % (i, roman))
        if i != 1:
            hide.add("num_%d_I" % i)
    for o in meshes:
        o.hide_render = o.name in hide
    gt = os.path.join(OUT, "gt_board.png")
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    scene.render.filepath = gt
    bpy.ops.render.render(write_still=True)
    for o in meshes:
        o.hide_render = False
    print("  gt     -> gt_board.png")

    # check/compare.py is module-shaped: it wants assets/<CODE>/plate.png and
    # gt_full_read.png.  Rather than fork the checker for one component, ship
    # the two names it expects -- a transparent plate (there is no baked plate)
    # and the same reference render.  `CODE=_leaderboard python3
    # live3d/check/compare.py <shot>` then works unmodified.
    import shutil
    shutil.copyfile(gt, os.path.join(OUT, "gt_full_read.png"))
    transparent_png(os.path.join(OUT, "plate.png"), W, H)

    S = {
        "schema": "saintcon.leaderboard.scene/1",
        "note": ("The muster board.  NO baked plate, NO depth pass, NO "
                 "declared readout plane: the whole board is live geometry "
                 "and the DOM layer is screen-space over a fronto-parallel "
                 "face.  live3d/design/LEADERBOARD.md."),
        "render": {"w": W, "h": H, "engine": "CYCLES",
                   "samples": scene.cycles.samples,
                   "film_transparent": True},
        "root_scale": 1.0,
        "camera": cam_json(scene, cam),
        "lights": lights_json(scene),
        "world_bg": [0.014, 0.016, 0.024, 1.0],
        "colour": {"view_transform": "AgX", "look": "None", "exposure": 0.0},
        # FITTED, NOT PICKED.  Swept 0.30..0.70 against gt_board.png through
        # check/compare.py with CANVAS_PMA=1: rms 29.36 / 27.09 / 26.17 /
        # 26.33 / 27.26 / 29.27 / 31.76 at 0.30 / 0.36 / 0.42 / 0.48 / 0.54 /
        # 0.62 / 0.70.  The minimum is 0.42, and it sits inside the nine
        # modules' own fitted spread of 0.501..0.688 only just below -- which
        # is expected, because this scene's lights were authored for Cycles
        # rather than measured off a shipped plate.
        "light_gain": float(os.environ.get("GAIN", "0.42")),
        "layout": LAYOUT,
        "parts": {k: sorted(v) for k, v in sorted(PART.items())},
        "triangles": tris,
        # BOTH HOTSPOTS EXIST ON EVERY BOARD.  This used to say "desk mode
        # only -- TV mode creates no hotspot at all", which was the whole of
        # the reason a person standing at the conference television could not
        # scroll it.  There is one board now and it has a pointer.
        "hotspots": [
            {"id": "pin", "rect": [146, 660, 62, 48],
             "title": "clamp — dock or release your own row"},
            {"id": "rack", "rect": LAYOUT["rack"][:2] +
             [LAYOUT["rack"][2] - LAYOUT["rack"][0],
              LAYOUT["rack"][3] - LAYOUT["rack"][1]],
             "title": "drag to page the rack"},
        ],
    }
    with open(os.path.join(OUT, "scene.json"), "w") as f:
        json.dump(S, f, indent=1, sort_keys=True)
    with open(os.path.join(OUT, "materials.json"), "w") as f:
        json.dump(materials_json(), f, indent=1, sort_keys=True)
    print("  json   -> scene.json, materials.json")


if __name__ == "__main__":
    main()
