"""
LIVE-3D EXPORT -- LOG close-up  (Black Box / Flight Recorder).

A thin layer over three-exploration/pipeline/transliterate.py, following
live3d/CONVERSION_BRIEF.md.  The module's REAL build.py is imported in place by
live3d/pipeline/module_loader.py, so there is no LOG snapshot to go stale.

LOG is the fleet's hardest occlusion case (live3d/audit/OCCLUSION_AUDIT.md,
"OCCLUDED -- the worst in the fleet"):

    * the SEARCH LENS sweeps straight across the chart window, up to 61 of 224
      samples at once, standing 64-66 mm proud.  It is the ONLY moving occluder
      over a readout anywhere in the fleet.
    * the RIBBON IS LONGER THAN ITS APERTURE -- 350 mm of paper through a
      180 mm window -- so 104/224 samples are behind log_face_mid /
      log_win_trim_* / log_face_top / log_nameplate at rest.
    * the TEAR-OFF TAIL is a NON-PLANAR carrier: seven flat facets at
      10/18/26/32/28/18/6 degrees, clipped at the top by log_slot_lip_a.
    * the whole ribbon is a MOVING readout plane: the tape translates and the
      plane and the DOM element ride with it, re-placed every frame.

    plate.png     shell + LOG's static parts MINUS the seven log_tail_txt_*
                  ink bars.  LOG returns NO R["static"] and NO R["all"]; it
                  returns R["plate"], the WIDE-SHOT list.  Here the two
                  coincide -- keep() appends to `plate` for every static prop
                  and every control object bypasses it -- but that is DERIVED
                  and ASSERTED below, never assumed (BRIEF step 1,
                  correction 3).

    tape.glb      the ribbon, its ruled lines, its perforations and the red pen
                  trace.  `tape` ships as kind: frames, and BRIEF step 2 says
                  to read the setter before assuming N meshes: build.py's own
                  main() does `piv.location = (0, -TRAVEL*t, 0)` and
                  `sp.rotation_euler = (0,0,-off/SPOOL_R)`, i.e. ONE object set
                  driven by a single continuous parameter, exactly like PKT's
                  three frame controls.  So the eight frames are samples of a
                  translation, and the live conversion is one glb plus a number.
    spool0/1.glb  the two paper rolls; they turn with the tape.
    lens.glb      the magnifier: arm, grip, ring and glass (alpha 0.10)
    source.glb    the rotary selector's pointer and knob
    srclamps.glb  its four lamp domes -- rule 3, the control declares
                  mats {off: log_lamp_off, on: log_lamp_amber}
    wipe.glb      the break-glass lever (shaft + knob)
    wipeglass.glb the pane and the five shards -- alternative states
    wipelamp.glb  the WIPE lamp dome (off / log_lamp_red)

    NOT EXPORTED AT ALL: 35 ink bars.  log_txt_a_* / log_txt_b_* (28, on the
    ribbon, control-owned) and log_tail_txt_* (7, on the tail, in `plate`) are
    this module's baked stand-in for content text -- the audit names exactly
    those objects as LOG's content -- so they are excluded from plate.png, from
    depth.bin and from every glb, and their lines become DOM.  The ruled lines
    (log_rule_*, log_tail_rule_*) and the perforations are STATIONERY and stay
    geometry, as do the nameplate bars and the hazard stripes.

    text_planes   EIGHT rects.  One rides the ribbon; seven are the tail's
                  facets.  MAX_PLANES is 12 for exactly this reason.

    gt_platen0    LOG authors NO type (no text(), no mono_font()), so this file
                  defines the fleet-standard pair and CREATES the type after
                  plate.png / depth.bin / every glb are written.  IT IS
                  RENDERED WITH THE BAKED PLATE AS A HOLDOUT -- see
                  render_type() -- because on a carrier longer than its aperture
                  "the type rendered ALONE" contains lines that are behind the
                  panel on the real page and check_text.py then reports
                  "NO DOM INK IN THESE ROWS" for every one of them.

Run:
    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python live3d/pipeline/export_log.py

    LOG_GAIN=<f>          override the measured light_gain (default below)
    LOG_CONTROL_PLANE=1   also write assets/LOG/scene_control.json (§5.5 of
                          NOTES) -- the tape plane pushed BEHIND the ribbon's
                          own ruled lines so the plane CUTS the live carrier.
"""
import bpy, math, os, sys, json, collections
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE3D = os.path.dirname(HERE)
ROOT = os.path.dirname(LIVE3D)
EXPL = os.path.join(ROOT, "three-exploration")
sys.path.insert(0, os.path.join(EXPL, "pipeline"))
sys.path.insert(0, os.path.join(EXPL, "src"))
sys.path.insert(0, HERE)

import transliterate as T                                        # noqa: E402
import typemetrics as TM                                         # noqa: E402
import ubias                                                     # noqa: E402
from module_loader import load_module, check_snapshots           # noqa: E402
from nnscale import decode                                       # noqa: E402

shell = T.shell
CODE = "LOG"
OUT = os.path.join(LIVE3D, "assets", CODE)

# MEASURED (BRIEF 5.2a), not chosen, and the SECOND measurement is the one
# shipped.  0.05-grid sweep on the real page, scored with compare.py:
#
#   gain            0.45    0.50    0.55    0.60    0.65    0.70    0.75
#   rms, frame     12.223  11.764  11.451  11.269  11.169  11.138  11.168
#   -> parabola through the last three fits 0.700, which is OUTSIDE the
#      fleet's measured 0.506..0.685.  BRIEF 5.2a: "that is a signal, not a
#      licence".  It is: LOG has the fleet's first TRANSPARENT live props (the
#      magnifier glass, alpha 0.10, and the break-glass pane, 0.30) and both
#      composite ~30 levels too dark because the renderers are created
#      `premultipliedAlpha: false` while three writes premultiplied rgb
#      (NOTES 8.1).  The gain was being asked to cancel a compositing error,
#      exactly as FMM's was being asked to cancel an unmodelled grade.
#
#   the same sweep with those two props' 26,254 px masked out:
#   gain            0.55    0.60    0.65    0.70    0.75
#   rms, live set  17.184  16.646  16.698  17.199  17.990
#   -> parabola 0.6206, INSIDE the fleet range and next to KVS 0.621,
#      MQB 0.612, PKT 0.611, IPM 0.610; and the live-set rms falls from
#      33.2 to 16.6, i.e. into the fleet's 15.6..24.6 band.
LIGHT_GAIN = float(os.environ.get("LOG_GAIN", "0.62"))

# ------------------------------------------------------------- THE POSE
# The one resting state the whole verification chain is scored in.  It must be
# identical here, in gt_full_read.png and in module.js's poseForCapture().
#
# THE LENS IS OVER THE TAPE, AND THAT IS DELIBERATE.  BRIEF 5.3: "do NOT park
# your live geometry off your readouts in pose()" -- LOG is the module that
# rule was written for.  -34 deg CSS puts the magnifier on the printed lines,
# which is what a recorder looks like while somebody is reading it, and it is
# what makes check_occlusion.py's LIVE half a measurement instead of an empty
# set.  Parking would be moving it OFF; this is the opposite.
# 0.037 m of travel, NOT build.py's own 3/7 rest (0.030), and the 7 mm is a
# PRODUCT fix of exactly PKT's shape.  The rows are on a 24 mm pitch and the
# window holds only 156 mm of clear paper: `log_win_trim_*` closes it at panel
# y 0.140, `log_pen_rail` -- BAKED, 8 mm tall, the FULL WIDTH of the aperture --
# crosses it at 0.116..0.124, and the trim closes it again at -0.040.
#
# At 3/7 a row lands at 0.141, straddling the trim, and another at 0.117 under
# the rail: their glyphs are half-cut, so verify_assets.py's 3 px ring measures
# BRASS instead of deck and the `tape` plane read contrast 10.49 with worst
# line 56.32.  At 0.027 that was fixed but a row still sat 1.4 mm above the
# trim edge, leaving a THREE-PIXEL antialias fringe of an otherwise-hidden line
# -- and check_text.py scored that 3 px band as a row, `worst row dy 1.000`,
# which is not < 1.0.  FAIL on three pixels.
#
# 0.037 solves it properly.  The row grid is chosen so that EVERY row is at
# least 3.4 mm clear of all three edges and the two rows that are hidden are 18
# mm past them, so there is no fringe to score: rows land at 0.134, 0.110,
# 0.086, 0.062, 0.038, 0.014, -0.010, -0.034 (eight visible) with 0.158 fully
# above the trim and -0.058 fully below it.  Lines still cross those edges as
# the tape RUNS -- that is the whole point of a moving readout -- they just do
# not do it in the one frame the verification chain is scored in.
POSE_TAPE_T = 0.037 / 0.070    # build.py's own rest is 3/7 = 0.030 m
# -45 deg, not -34: MEASURED.  At -34 the glass disc hangs 17 mm BELOW the
# aperture, into the band where log_face_mid is in front of the tape rect and
# the front pass therefore redraws the plate -- and a TRANSPARENT live prop
# cannot be in that band (modules/LOG/NOTES.md 8.1).  At -45 the whole disc is
# inside the window, the brass RING, ARM and GRIP still cross four rows of
# type, and the search reads as a search.
POSE_LENS_DEG = -45.0          # CSS degrees, build.py's convention
POSE_SOURCE = 0                # SRC_STATES[0] = "all"
POSE_WIPE = "sealed"

# ------------------------------------------------------- THE READOUT PLANES
# All lengths are module-local metres (root scale is 1, asserted below).
#
# Z / STAND-OFF, measured off build.py's own constants rather than a render:
#   log_ribbon          local z 0.0025 .. 0.0055     the paper
#   log_rule_*          local z 0.0050 .. 0.0066     ruled lines + perforations
#   log_trace_*         local z 0.0056 .. 0.0072     the red pen trace
#   -> the tape plane at 0.0080 is 0.8 mm in front of the trace, 1.4 mm in
#      front of the rules and 2.5 mm in front of the paper.  The shader's
#      epsilon is RELATIVE (s > 1.0001), which at LOG's 1.274 m close camera is
#      0.127 mm, so the tightest of those clears it by 6.3x and no ruled line
#      lands in the front half.
#
# X: the RECT is the whole ribbon width -- it is the occlusion boundary as well
# as the element, and the magnifier has to be able to cross ANY of it -- but the
# TYPE only fills the left half, because the ribbon carries printed lines on the
# left and the RED PEN TRACE on the right (build.py's _trace_x runs x -0.008 ..
# 0.098; its own ink bars sit at x -0.086 .. -0.002).  A 19-column line from
# x -0.100 leaves the trace alone; a full-width one would lay DOM type over it.
#
# Y: THE RECT'S BOTTOM IS NOT THE RIBBON'S BOTTOM, AND THAT IS MEASURED.  A
# first export ran the rect down the ribbon's whole 350 mm, and the TAIL --
# which is baked paper standing 20-60 mm in front of the ribbon -- is then "in
# front of a readout", so the front pass redrew the tail's own paper OVER the
# tail's own DOM lines and four of the seven tear-off readouts were blank on the
# page.  `occInFrontOfText()` is a UNION over the declared planes: it has no way
# to know that a fragment in front of plane A is the CARRIER of plane B.  So the
# tape rect stops above the tail at every tape position: bottom = ribbon y
# -0.026, which is panel y -0.096 at full travel, screen row 427 against the
# tail_0 rect's top at 433.
# The half-extents are 0.5 mm off the round numbers ON PURPOSE.  At half_w
# 0.10400 the rect's left edge passed through buffer pixel (518,378)'s CENTRE
# to 1e-7 m -- 6e-4 of a pixel -- so the GPU's float32 and the checker's
# float64 disagreed about that one fragment and check 4 reported
# `outside every rect 1 -> FAIL`.  An edge is a step in PASS ASSIGNMENT, not an
# antialiased boundary, so it must not land on a sample centre.  NOTES 8.2.
TAPE_CX, TAPE_HW = 0.000, 0.1035          # x -0.1035 .. 0.1035  (1035 el px)
TAPE_CY, TAPE_HH = 0.0908, 0.1168         # y -0.026 .. 0.2076   (1168 el px)
TAPE_Z = 0.0080
TAPE_LEAD = 0.024                         # build.py's own row pitch
TAPE_LINES = 10                           # what a 234 mm rect can hold at 24 mm
TAPE_ROW0_Y = 0.195                       # top row: RIB_Y0 + 0.023 + 0.024*13

# One type size for the whole module: it is one printout, on the ribbon and on
# the piece already torn off.  `span` is the width n_cols must fill, which is
# what SOLVES FONT.size -- the carrier's geometry chooses the type size.
SPAN, NCOLS = 0.100, 19                   # -> cap 5.19 mm = 6.1 px on screen
# THE TAPE'S FIRST COLUMN CLEARS THE SPROCKET HOLES, AND THAT IS MEASURED.
# `log_perf_*` is a 7 mm square of `well_m` punched at ribbon x -0.1035..-0.0965
# on every third row -- AT THE TEXT ROW'S OWN y (build.py puts it at
# `ry + 0.009`, the same offset as its ink bars).  It is LIVE and it is BEHIND
# the readout plane, so it does not occlude anything; it is simply a luma-82
# square on luma-217 paper directly under the first character.  check_text.py
# reads the DOM ink as a shown/hidden screenshot DIFFERENCE, so dark ink on a
# dark perforation falls under its 8-level threshold: the whole first glyph
# vanished from the DOM set (17 px against Blender's 26) and that band's
# centroid read 2.391 px against 0.25..0.93 on every other line in the module.
# Starting the tape's columns at -0.0930 puts them 3.5 mm (4 px) clear of the
# sprocket column.  The TAIL keeps the full 19 columns from -0.100: it has no
# perforations and no pen trace.
TAPE_LEFT, TAPE_NCOLS = -0.0930, 17

# The tail: seven facets, build.py's own droop angles.  A plane per facet, each
# with its own basis, because a CSS3D element is flat whatever you do.
TAIL_PHI = (10.0, 18.0, 26.0, 32.0, 28.0, 18.0, 6.0)
TAIL_LN = 0.026
# THE TAIL RECT IS 20 mm ON A 26 mm FACET, AND THE 6 mm GAP IS LOAD-BEARING.
# `.readout` carries `overflow:hidden` (the shared template's CSS), and Chrome
# will SILENTLY DROP ONE of seven near-coplanar 3D-transformed readout layers
# when they are this tall and this close: at half_h 0.01147 (114.688 el px)
# tail_4 did not paint at pixelRatio 1 and did at 2; at 0.0115 (115 px) tail_3
# did not paint at EITHER ratio.  Measured on the page -- the element lays out,
# getBoundingClientRect is right, computed style is identical to its
# neighbours', a solid background on it does not paint, re-appending it in the
# DOM does not help, and giving it a NEIGHBOUR'S transform does not help.
# `overflow:visible` paints all eight; `overflow:clip`, `clip-path:inset(0)`,
# `contain:paint`, `will-change` and `isolation` all reproduce the drop, so it
# is the PAINT CLIP and not the flattening.  A 100 px element paints all eight
# with the clip left alone.  Shared-code report in NOTES 8.3; the fix HERE is
# geometry, which is mine.
TAIL_HW, TAIL_HH = 0.1035, 0.0110         # -> 1035 x 110 element px, integers
TAIL_STANDOFF = 0.0042                    # along the facet normal, from centre
# The text row, along the facet's own +v, relative to its ruled line at v = 0.
# +7.6 mm puts it above the rule, exactly where build.py's own log_tail_txt_*
# bars are -- EXCEPT on facet 0, where it cannot go.  MEASURED: log_slot_lip_a
# (y -0.106..-0.098, z 0.023..0.033) swallows everything above v ~ +2 mm on
# that facet -- the 11x11 probe reads 45/121 covered and a first export put
# SEVEN ink pixels on screen out of ~230 -- so facet 0's line hangs BELOW its
# rule instead.  The audit's "the tear-off tail is clipped by log_slot_lip_a
# (8/56, 2.9 mm)" is that same finding at a coarser grid.
# 6.2 mm above the ruled line, not 6.8: at 6.8 the ROUND-GLYPH OVERSHOOT
# (typemetrics' cap is measured off "M", and "0" rides ~1.5% of an em higher)
# put 74 of 4460 glyph pixels OUTSIDE the declared rect, on the top row of
# tail_1 and tail_2 -- verify_assets.py's "a glyph outside its own plane means
# the plane is wrong".  6.2 mm with a 11 mm half-height leaves 1.8 mm of
# headroom over the overshoot and still clears the ruled line by 3.6 mm, which
# is more than the checker's own 3 px ring.
TAIL_TOP = [-0.0070, 0.0062, 0.0062, 0.0062, 0.0062, 0.0062, 0.0062]

INK_MAT = "log_ink"

# THE STRINGS THE CAPTURE POSE PAINTS.  Data: the exporter renders
# gt_platen0.png from exactly these and module.js's pose() paints exactly
# these, so check_text.py compares like with like.  Newest first: the pen
# writes at the TOP of the window and the paper travels DOWN and out of the
# slot, so the ribbon's top row is the newest line and the tail's last facet is
# the oldest.
TAPE_TEXT = [
    "0941 SRC=ALL",
    "0940 GET /logs",
    "0940  200 4.2 KB",
    "0939 WIPE SEALED",
    "0938 GET /search",
    "0938  q=timeout",
    "0937  14 HITS",
    "0936 MTA RETRY 3",
    "0935 NAV FIX LOCK",
    "0934 KVS TX ACK",
]
TAIL_TEXT = [
    "0933 GET /logs/mta",
    "0932  200 9.8 KB",
    "0931 SRC=NAV",
    "0930 BOOT OK",
    "0929 LINK UP",
    "0928 AUTH ok pilot",
    "0927 -- TEAR OFF --",
]


# ------------------------------------------------ the type LOG does not have
# LOG has neither text() nor mono_font(), so typemetrics.py RAISES rather than
# silently measuring Blender's default face (which returns ratio 0.781 against
# the true 0.310667 -- 2.51x too wide, and entirely plausible).  This is the
# fleet-standard pair, the same one every other module's build.py carries.
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


def text(name, body, size, mat, loc, align='LEFT', to_mesh=True):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body, cu.size = body, size
    cu.align_x, cu.align_y = align, 'CENTER'
    cu.extrude = 0.0004
    f = mono_font()
    if f:
        cu.font = f
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.data.materials.append(mat)
    if to_mesh:
        try:
            bpy.ops.object.select_all(action='DESELECT')
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.object.convert(target='MESH')
            o = bpy.data.objects.get(name) or o
        except Exception:
            pass
    return o


def dirn(m3, v):
    return (m3 @ Vector(v)).normalized()


def clamp_rect(r, W, H):
    x0, y0 = max(0, r["x"]), max(0, r["y"])
    x1, y1 = min(W, r["x"] + r["w"]), min(H, r["y"] + r["h"])
    return {"x": x0, "y": y0, "w": max(1, x1 - x0), "h": max(1, y1 - y0)}


def median_ink(path, amin=0.5):
    """MEDIAN over alpha > 0.5, no colour transform, off the PNG BYTES with the
    stdlib decoder -- never bpy's image.pixels, which is already display-encoded
    (BRIEF section 7 rule 7; MTA's trap)."""
    w, h, nch, rows = decode(path)
    chans = [[], [], []]
    for y in range(h):
        r = rows[y]
        for x in range(w):
            a = r[x * nch + 3] if nch == 4 else 255
            if a <= amin * 255:
                continue
            for c in range(3):
                chans[c].append(r[x * nch + c])
    if not chans[0]:
        return None, 0
    return [sorted(chans[c])[len(chans[c]) // 2] for c in range(3)], len(chans[0])


def render_type(scene, path, visible, holdout):
    """Render `visible` with `holdout` punching alpha but keeping its depth.

    WHY THIS IS NOT `render_colour(visible=type)`.  BRIEF step 3 defines
    gt_platen0.png as "your content type rendered ALONE", which silently assumes
    every glyph is on screen.  LOG's ribbon is 350 mm of paper behind a 180 mm
    window: six of its fourteen lines are BEHIND log_face_top / log_face_mid on
    the real page and correctly invisible.  Rendered alone they are all there,
    and check_text.py -- which takes the DOM ink from a shown/hidden screenshot
    difference, so it can only see what the front pass lets through -- reports
    `NO DOM INK IN THESE ROWS  <- FAIL` for every hidden line.

    So the plate is a HOLDOUT: it occludes the type exactly as it does on the
    page, and punches alpha where it is the visible surface, so gt_platen0.png
    is still "the type alone" everywhere it exists.  This is build.py's own
    `render_to(..., holdout=clip)` recipe, which the module already uses to clip
    its sprites to the panel.  LIVE occluders are deliberately NOT holdouts --
    see NOTES 8.x.
    """
    saved = {o.name: o.hide_render for o in T.renderables(scene)}
    vis, hsave = set(visible), {}
    hold = [o for o in holdout if o not in vis]
    for o in T.renderables(scene):
        o.hide_render = not (o in vis or o in set(hold))
    for o in hold:
        hsave[o.name] = o.is_holdout
        o.is_holdout = True
    scene.use_nodes = False
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in hold:
        o.is_holdout = hsave[o.name]
    T.restore(scene, saved)
    print("  colour ->", os.path.basename(path), "(plate as holdout)")


def main():
    os.makedirs(OUT, exist_ok=True)
    bad = check_snapshots()
    assert not bad, "snapshot check failed: %s" % bad

    P = dict(shell.PARAMS)
    P["exterior"] = 0
    print("raytrace =", P.get("raytrace"))
    assert P.get("raytrace") == 1, "shell_snapshot.py is stale: no raytrace"

    scene = shell.build(P)
    scene.render.film_transparent = True
    W, H = scene.render.resolution_x, scene.render.resolution_y
    mats = {k: bpy.data.materials[k] for k in ("brass", "hull", "hull_d")}

    mod = load_module(CODE)
    mod.text, mod.mono_font = text, mono_font
    FONT = mono_font()
    assert FONT is not None, "no mono face on this machine"

    before = set(bpy.data.objects)
    R = mod.add_props(P, mats)
    mine = [o for o in bpy.data.objects
            if o not in before
            and o.type in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}]
    ctrl, root = R["controls"], R["root"]

    rs = root.matrix_world.to_scale()
    assert max(abs(rs.x - 1), abs(rs.y - 1), abs(rs.z - 1)) < 1e-6, \
        "root is scaled: every local length in this file needs multiplying"

    # ------------------------------------------------ the live / baked split
    # LOG returns neither R["all"] nor R["static"].  `all` is the scene diff
    # across add_props(); `static` is all - control-owned; and R["plate"] is
    # then ASSERTED to be that same set rather than trusted (BRIEF step 1).
    tape_all = list(ctrl["tape"]["objs"])
    lens_objs = list(ctrl["lens"]["objs"])
    src_domes = list(ctrl["source"]["domes"])
    src_objs = [o for o in ctrl["source"]["objs"] if o not in set(src_domes)]
    wipe_lever = list(ctrl["wipe"]["lever"])
    wipe_pane = ctrl["wipe"]["pane"]
    wipe_shards = list(ctrl["wipe"]["shards"])
    wipe_dome = ctrl["wipe"]["dome"]
    live = (tape_all + lens_objs + src_domes + src_objs + wipe_lever
            + [wipe_pane] + wipe_shards + [wipe_dome])
    static = [o for o in mine if o not in set(live)]
    assert not (set(live) & set(static))
    assert set(static) == set(R["plate"]), \
        "R['plate'] is NOT this module's static set -- re-derive it"
    assert set(R["far"]) <= set(live) | set(static)

    # CONTENT TEXT.  The audit names exactly these: "log_txt_a_* / log_txt_b_*,
    # the printed lines on the strip-chart ribbon, and log_tail_txt_* on the
    # tear-off paper below.  (Both are ink bars, not type -- LOG has no text
    # geometry either.)"  28 of them are control-owned and 7 are in `static`,
    # which is why BOTH lists have to be filtered: MTA found three content FONT
    # objects inside its own clean `static` and this module has seven.
    tape_txt = [o for o in tape_all
                if o.name.startswith(("log_txt_a_", "log_txt_b_"))]
    tail_txt = [bpy.data.objects["log_tail_txt_%d" % i] for i in range(7)]
    content = tape_txt + tail_txt
    assert len(tape_txt) == 28 and len(tail_txt) == 7, (len(tape_txt),
                                                        len(tail_txt))
    assert set(tail_txt) <= set(static), "the tail bars should be static"
    assert set(tape_txt) <= set(live), "the ribbon bars should be tape-owned"

    spool_pivs = list(ctrl["tape"]["spools"])
    spool_grp = [[o for o in tape_all if o.parent is sp] for sp in spool_pivs]
    ribbon = [o for o in tape_all
              if o not in set(tape_txt) and not any(o in g for g in spool_grp)]
    assert len(ribbon) + len(tape_txt) + sum(len(g) for g in spool_grp) \
        == len(tape_all)

    shell_meshes = [o for o in T.renderables(scene) if o not in set(mine)]
    plate = shell_meshes + [o for o in static if o not in set(tail_txt)]
    live_geo = [o for o in live if o not in set(tape_txt)]
    assert not (set(content) & set(plate))
    assert not (set(content) & set(live_geo))
    print("split: %d plate objects (%d shell + %d module static - 7 tail bars),"
          " %d live (%d ribbon, %d spools, %d lens, %d source, %d wipe), "
          "%d content -> DOM"
          % (len(plate), len(shell_meshes), len(static), len(live_geo),
             len(ribbon), sum(len(g) for g in spool_grp), len(lens_objs),
             len(src_objs) + len(src_domes),
             len(wipe_lever) + 1 + len(wipe_shards) + 1, len(content)))

    def tris(objs):
        n = 0
        dg = bpy.context.evaluated_depsgraph_get()
        for o in objs:
            if o.type not in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}:
                continue
            ev = o.evaluated_get(dg)
            try:
                me = ev.to_mesh()
            except Exception:
                continue
            me.calc_loop_triangles()
            n += len(me.loop_triangles)
            ev.to_mesh_clear()
        return n
    tri_live, tri_static = tris(live_geo), tris(static)
    print("tris: live %d  static %d  content(dropped) %d"
          % (tri_live, tri_static, tris(content)))

    # ---------------------------------------------------- the close-up rig
    # LOG has close_rig(root) and build.py's main() calls it straight after
    # add_props() with no pre-state at all (unlike OTA, which raises its
    # cartridge first), so reproducing the call is the whole of it.
    cam, close_lights = mod.close_rig(root)
    scene.camera = cam
    bpy.context.view_layer.update()
    close_tags = {L.name: "close" for L in close_lights}
    # LOG has NO close_grade() -- checked across all nine build.py files, only
    # FMM has one -- so `colour` reads AgX / None / 0.0 and grade.js is a no-op
    # here.  It is wired in anyway: "eight modules read None" is exactly the
    # reasoning that left `colour` unread on all nine.  BRIEF 5.2b.
    print("colour: view_transform=%s look=%s exposure=%+.3f"
          % (scene.view_settings.view_transform, scene.view_settings.look,
             scene.view_settings.exposure))

    rm3 = root.matrix_world.to_3x3()
    ux = dirn(rm3, (1, 0, 0))
    uv = dirn(rm3, (0, 1, 0))
    un = dirn(rm3, (0, 0, 1))
    cfwd = dirn(cam.matrix_world.to_3x3(), (0, 0, -1))
    obliq = math.degrees(math.acos(max(-1.0, min(1.0, (-cfwd).dot(un)))))
    print("OBLIQ panel face normal vs close-cam view axis %.4f deg" % obliq)
    assert (-cfwd).dot(un) > 0, "n must point AT the camera"

    # ------------------------------------------------ plate + the depth pass
    # Both at the module's own rest state; neither contains anything live, so
    # neither depends on the capture pose.
    T.render_colour(scene, os.path.join(OUT, "plate.png"), visible=plate)
    dep = T.render_depth(scene, os.path.join(OUT, "depth.bin"),
                         hide=live + content)

    # ------------------------------------------------------------ geometry
    # exported at a ZERO reference so the frontend applies an absolute
    # transform rather than a delta from build.py's rest pose.
    tape_piv = ctrl["tape"]["pivot"]
    lens_piv = ctrl["lens"]["pivot"]
    src_piv = ctrl["source"]["pivot"]
    wipe_piv = ctrl["wipe"]["pivot"]
    tape_piv.location = (0, 0, 0)
    for sp in spool_pivs:
        sp.rotation_euler = (0, 0, 0)
    lens_piv.rotation_euler = (0, 0, 0)
    src_piv.rotation_euler = (0, 0, 0)
    wipe_piv.rotation_euler = (0, 0, 0)
    lamp_off = ctrl["source"]["mats"]["off"]
    for d in src_domes:
        d.data.materials[0] = lamp_off
    wipe_dome.data.materials[0] = ctrl["wipe"]["mats"]["off"]
    bpy.context.view_layer.update()

    T.export_glb(ribbon, os.path.join(OUT, "tape.glb"))
    for i, g in enumerate(spool_grp):
        T.export_glb(g, os.path.join(OUT, "spool%d.glb" % i))
    T.export_glb(lens_objs, os.path.join(OUT, "lens.glb"))
    T.export_glb(src_objs, os.path.join(OUT, "source.glb"))
    T.export_glb(src_domes, os.path.join(OUT, "srclamps.glb"))
    T.export_glb(wipe_lever, os.path.join(OUT, "wipe.glb"))
    T.export_glb([wipe_pane] + wipe_shards, os.path.join(OUT, "wipeglass.glb"))
    T.export_glb([wipe_dome], os.path.join(OUT, "wipelamp.glb"))

    # ---------------------------------------------------------- the anchors
    # NO module declares `axis` on a `rotate` control -- all eight lack it, and
    # NOTES.md names LOG as "the known example" when it is universal.  LOG has
    # NO face helper: the working face IS the slot plane, so there is no rake
    # and every rotation is about the root's own local +Z.
    #
    # EMITTED NEGATED (MQB's and PKT's convention) so that a POSITIVE angle is
    # CLOCKWISE on screen, which is the direction build.py's own demo runs its
    # CSS `rotate(a deg)`.  build.py sets rotation_euler.z = radians(-a) for a
    # CSS angle a, i.e. a rotation of -a about +n == +a about -n.
    spin_axis = [-c for c in T.to3(un)]
    lens_hub = lens_piv.matrix_world.translation.copy()
    spool_hubs = [sp.matrix_world.translation.copy() for sp in spool_pivs]
    src_hub = src_piv.matrix_world.translation.copy()
    wipe_hub = wipe_piv.matrix_world.translation.copy()
    travel_axis = T.to3(-uv)          # build.py: piv.location = (0, -off, 0)

    # ------------------------------------------------------ THE CAPTURE POSE
    off = mod.TAPE_TRAVEL * POSE_TAPE_T
    tape_piv.location = (0, -off, 0)
    for sp in spool_pivs:
        sp.rotation_euler = (0, 0, -off / mod.SPOOL_R)
    lens_piv.rotation_euler = (0, 0, math.radians(-POSE_LENS_DEG))
    src_piv.rotation_euler = (0, 0, -math.radians(mod.SRC_ANGLES[POSE_SOURCE]))
    for k, d in enumerate(src_domes):
        d.data.materials[0] = ctrl["source"]["mats"][
            "on" if k == POSE_SOURCE else "off"]
    wipe_piv.rotation_euler = (0, 0, 0)
    wipe_dome.data.materials[0] = ctrl["wipe"]["mats"]["off"]
    bpy.context.view_layer.update()
    # at `sealed` the glass is whole: the shards do not exist yet
    live_rest = [o for o in live_geo if o not in set(wipe_shards)]

    # ------------------------------------------------------ the text planes
    unit_adv = TM.measure_type(mod, 1.0, font=FONT)["adv"]
    size = (SPAN / NCOLS) / unit_adv
    m1 = TM.measure_type(mod, size, font=FONT)
    print("TYPE  one size for the module: FONT.size %.6f -> adv %.6f "
          "(ratio %.6f)  cap %.6f  base %+.6f"
          % (size, m1["adv"], m1["ratio"], m1["cap"], m1["base"]))

    planes = []

    # ---- 1. THE TAPE.  A MOVING PLANE: the rect rides the ribbon, so its
    # origin is emitted BOTH at the capture pose (which is what corners_px is
    # defined against, BRIEF step 4) and at the tape's zero reference, which is
    # the frame module.js translates every frame.
    tb = TM.type_block(mod, size, lead_m=TAPE_LEAD,
                       left_m=TAPE_LEFT, top_m=TAPE_ROW0_Y - TAPE_CY,
                       n_lines=TAPE_LINES, scale=1.0, align="left", font=FONT)
    tb["n_cols"] = TAPE_NCOLS
    zero_local = Vector((TAPE_CX, TAPE_CY, TAPE_Z))
    pose_local = zero_local + Vector((0, -off, 0))
    o_pose = root.matrix_world @ pose_local
    planes.append({
        "name": "tape",
        "origin": T.to3(o_pose), "u": T.to3(ux), "v": T.to3(uv), "n": T.to3(un),
        "half_w": TAPE_HW, "half_h": TAPE_HH, "type": tb,
        "local": list(pose_local), "local_tape0": list(zero_local),
        "origin_tape0": T.to3(root.matrix_world @ zero_local),
        "rides": "tape", "ink_mat": INK_MAT,
        "corners_px": {
            k: dict(zip(("x", "y"), mod.project(
                scene, cam, o_pose + ux * (TAPE_HW * sx) + uv * (TAPE_HH * sy))))
            for k, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                              ("bl", -1, -1), ("br", 1, -1))}})

    # ---- 2..8. THE TAIL.  Seven flat facets: build.py walks a point down the
    # console front, turning by phi at each step, so the carrier is genuinely
    # non-planar and a CSS3D element is flat whatever you do.  Each facet gets
    # its own plane and its own DOM element (BRIEF step 4, "Non-planar
    # carriers"; MAX_PLANES is 12 for exactly this).
    py, pz = mod.SLOT_Y0 + 0.002, mod.FACE_Z + 0.006
    tail_local = []
    for i, phi in enumerate(TAIL_PHI):
        f = math.radians(phi)
        dy, dz = -math.cos(f), math.sin(f)
        cy, cz = py + dy * TAIL_LN / 2, pz + dz * TAIL_LN / 2
        py, pz = py + dy * TAIL_LN, pz + dz * TAIL_LN
        # the facet's own basis.  build.py rotates the box by (180-phi) about
        # X, which puts its +Z face DOWN-AND-BACK; the outward normal -- the
        # one that must point AT the camera -- is (0, sin phi, cos phi).
        ln_ = Vector((0.0, math.sin(f), math.cos(f)))
        lv = Vector((0.0, math.cos(f), -math.sin(f)))
        loc = Vector((0.0, cy, cz)) + ln_ * TAIL_STANDOFF
        tail_local.append((loc, lv, ln_))
        wu, wv, wn = ux, dirn(rm3, lv), dirn(rm3, ln_)
        assert (-cfwd).dot(wn) > 0, "tail %d: n must point AT the camera" % i
        tt = TM.type_block(mod, size, lead_m=min(size, 1.6 * TAIL_HH),
                           left_m=-0.100, top_m=TAIL_TOP[i], n_lines=1,
                           scale=1.0, align="left", font=FONT)
        tt["n_cols"] = NCOLS
        og = root.matrix_world @ loc
        planes.append({
            "name": "tail_%d" % i,
            "origin": T.to3(og), "u": T.to3(wu), "v": T.to3(wv), "n": T.to3(wn),
            "half_w": TAIL_HW, "half_h": TAIL_HH, "type": tt,
            "local": list(loc), "phi_deg": phi, "ink_mat": INK_MAT,
            "obliquity_deg": math.degrees(math.acos(
                max(-1.0, min(1.0, (-cfwd).dot(wn))))),
            "corners_px": {
                k: dict(zip(("x", "y"), mod.project(
                    scene, cam,
                    og + wu * (TAIL_HW * sx) + wv * (TAIL_HH * sy))))
                for k, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                                  ("bl", -1, -1), ("br", 1, -1))}})

    POSE_TEXT = {"tape": list(TAPE_TEXT)}
    for i in range(7):
        POSE_TEXT["tail_%d" % i] = [TAIL_TEXT[i]]

    print("PLANES  8 declared (1 tape + 7 tail facets):")
    for p in planes:
        t, c = p["type"], p["corners_px"]
        ppm = math.hypot(c["tr"]["x"] - c["tl"]["x"],
                         c["tr"]["y"] - c["tl"]["y"]) / (2 * p["half_w"])
        print("   %-7s half %.4f x %.4f  %2d lines x %d cols  %.1f px/m -> "
              "cap %.2f px, line %.1f px  obliq %.2f"
              % (p["name"], p["half_w"], p["half_h"], t["n_lines"],
                 t["n_cols"], ppm, t["cap_m"] * ppm,
                 t["n_cols"] * t["adv_m"] * ppm,
                 p.get("obliquity_deg", obliq)))
        need_h = (t["n_lines"] - 1) * t["lead_m"] / 2 + t["cap_m"] / 2
        assert p["half_h"] >= need_h - 1e-9, (p["name"], p["half_h"], need_h)
        assert p["half_w"] >= t["n_cols"] * t["adv_m"] / 2 - 1e-9, p["name"]
        # the element must CONTAIN its glyphs: `top_m` is the first line's
        # origin above the rect centre, and the block hangs down from it.
        assert abs(t["top_m"]) + t["cap_m"] / 2 <= p["half_h"] + 1e-9, p["name"]
        assert (t["top_m"] - (t["n_lines"] - 1) * t["lead_m"]
                - t["cap_m"] / 2) >= -p["half_h"] - 1e-9, p["name"]
        assert t["left_m"] >= -p["half_w"] - 1e-9, p["name"]
        assert (t["left_m"] + t["n_cols"] * t["adv_m"]
                <= p["half_w"] + 1e-9), p["name"]
        assert len(POSE_TEXT[p["name"]]) == t["n_lines"]
        for s in POSE_TEXT[p["name"]]:
            assert len(s) <= t["n_cols"], (p["name"], s, len(s))

    # ---- uBias: the depth pass AGAIN, at the capture pose, with the LIVE
    # objects VISIBLE.  live3d/pipeline/ubias.py, not min(gaps): the raw
    # minimum lands on a SILHOUETTE pixel and was 11x wrong on IPM, and LOG's
    # live set is nothing but silhouettes (a 26-segment pen trace, two 40-sided
    # rolls, a torus, four domes seated in their cups).
    tmpb = os.path.join(OUT, "_depth_live.bin")
    liv = T.render_depth(scene, tmpb, hide=content + wipe_shards)
    os.remove(tmpb)
    U = ubias.measure([float(v) for v in dep.ravel()],
                      [float(v) for v in liv.ravel()], W, H)
    ubias.report(U)
    UBIAS = U["ubias_m"]

    # -------------------------------------- the type, AFTER everything above
    # plate.png, depth.bin and every glb are already written, so this type can
    # appear in NONE of them (asserted).  BRIEF step 3, "a readout with no
    # baked type: make the type, in Blender, after everything else".
    ink_m = bpy.data.materials[INK_MAT]
    stand_ins, per_plane = [], {}
    for p in planes:
        t = p["type"]
        objs = []
        if p["name"] == "tape":
            cx, cy, cz = p["local"]
            for i, body in enumerate(POSE_TEXT["tape"]):
                o = text("log_dom_tape_%d" % i, body, t["size_m"], ink_m,
                         (cx + t["left_m"], cy + t["top_m"] - i * t["lead_m"],
                          cz), align='LEFT')
                o.parent = root
                o.matrix_parent_inverse.identity()
                objs.append(o)
        else:
            loc, lv, ln_ = tail_local[int(p["name"][-1])]
            # the facet is tilted, so the line's origin is loc + lv*top_m and
            # the object has to be rotated into the facet's own basis
            o = text("log_dom_%s" % p["name"], POSE_TEXT[p["name"]][0],
                     t["size_m"], ink_m, (0, 0, 0), align='LEFT')
            o.location = loc + lv * t["top_m"] + Vector((t["left_m"], 0, 0))
            # rotate about +X by -phi: that maps the FONT object's local +Y
            # onto the facet's own `lv` and its +Z onto the facet normal.
            o.rotation_euler = (math.radians(-p["phi_deg"]), 0, 0)
            o.parent = root
            o.matrix_parent_inverse.identity()
            objs.append(o)
        stand_ins += objs
        per_plane[p["name"]] = objs
    bpy.context.view_layer.update()
    assert not (set(stand_ins) & set(plate)) and not (set(stand_ins) & set(live))

    # per-readout type renders -> each readout's OWN measured ink colour
    # THE HOLDOUT SET IS THE PLATE **PLUS THE OPAQUE LIVE OCCLUDERS**.
    # check_text.py takes the DOM ink from a shown/hidden screenshot difference,
    # so it can only ever see what the front pass lets through -- and on LOG the
    # magnifier's brass ARM, GRIP and RING are in front of the tape readout at
    # the capture pose and correctly hide part of four lines.  Rendered without
    # them, gt_platen0.png carries ink the page cannot show, `col_bands` pairs
    # a full Blender glyph band with a half-covered DOM one, and the worst
    # per-glyph dx reads 4.904 px on rows the placement is actually exact on.
    # The GLASS is deliberately NOT a holdout: it is alpha 0.10, the page shows
    # the type straight through it, and `is_holdout` would wrongly cut it out.
    occluders = plate + [o for o in lens_objs if o.name != "log_lens_glass"]
    inks = {}
    for p in planes:
        fn = os.path.join(OUT, "gt_type_%s.png" % p["name"])
        render_type(scene, fn, per_plane[p["name"]], occluders)
        col, cnt = median_ink(fn)
        inks[p["name"]] = col or [122, 113, 107]
        p["ink"] = inks[p["name"]]
        print("INK   %-7s median rgb%s over %d covered px  (material %s)"
              % (p["name"], tuple(inks[p["name"]]), cnt, INK_MAT))
    render_type(scene, os.path.join(OUT, "gt_platen0.png"), stand_ins, occluders)

    # THE FRAME compare.py SCORES: exactly what the browser draws live, in
    # exactly the state __occ.pose() puts the page in.
    for o in stand_ins:
        o.hide_render = True
    T.render_colour(scene, os.path.join(OUT, "gt_live_read.png"),
                    visible=live_rest)
    T.render_colour(scene, os.path.join(OUT, "gt_full_read.png"),
                    visible=plate + live_rest)

    # ---- MEASURED: what crosses each declared rect, live or baked, across the
    # module's WHOLE range.  The audit's harness was not kept (BRIEF correction
    # 11); this rebuilds the useful half of it, and it is what turns "the lens
    # sweeps the tape" into a number this export can be checked against.
    dg = bpy.context.evaluated_depsgraph_get()
    liveset = set(o.name for o in live_geo)
    cam_o = cam.matrix_world.translation
    for o in stand_ins:
        o.hide_render = True          # the DOM type is not an occluder
    # scene.ray_cast reads hide_VIEWPORT, not hide_render, so the ink bars this
    # export drops would otherwise report themselves as occluders of the very
    # readouts that replace them (measured: "baked log_tail_txt_2: 9").
    for o in content + stand_ins + wipe_shards:
        o.hide_viewport = True
    bpy.context.view_layer.update()

    def probe_plane(p, lens_deg, tape_t, N=11):
        lens_piv.rotation_euler = (0, 0, math.radians(-lens_deg))
        oz = mod.TAPE_TRAVEL * tape_t
        tape_piv.location = (0, -oz, 0)
        for sp in spool_pivs:
            sp.rotation_euler = (0, 0, -oz / mod.SPOOL_R)
        bpy.context.view_layer.update()
        if p["name"] == "tape":
            base = Vector(p["local_tape0"]) + Vector((0, -oz, 0))
            uu, vv = Vector((1, 0, 0)), Vector((0, 1, 0))
        else:
            loc, lv, _n = tail_local[int(p["name"][-1])]
            base, uu, vv = loc, Vector((1, 0, 0)), lv
        cov, hits = 0, collections.Counter()
        for i in range(N):
            for j in range(N):
                s = base + uu * (p["half_w"] * (2 * i / (N - 1) - 1)) \
                         + vv * (p["half_h"] * (2 * j / (N - 1) - 1))
                w = root.matrix_world @ s
                d = w - cam_o
                ok, loc2, nrm, idx, ob, mw = scene.ray_cast(
                    dg, cam_o, d.normalized(), distance=d.length - 0.001)
                if ok and ob is not None:
                    cov += 1
                    hits[("LIVE " if ob.name in liveset else "baked ")
                         + ob.name] += 1
        return cov, hits

    print("PROBE  11x11 ray-cast per declared rect, close cam, over the "
          "lens's WHOLE range and the tape's:")
    probe_rows = []
    LENS_POSES = [mod.LENS_RANGE[0] + (mod.LENS_RANGE[1] - mod.LENS_RANGE[0])
                  * i / 8.0 for i in range(9)]
    for p in planes:
        worst, agg, worst_live, at = 0, collections.Counter(), 0, None
        for ld in LENS_POSES:
            for tt in (0.0, POSE_TAPE_T, 1.0):
                cov, hits = probe_plane(p, ld, tt)
                nl = sum(v for k, v in hits.items() if k.startswith("LIVE"))
                if cov > worst:
                    worst = cov
                if nl > worst_live:
                    worst_live, at = nl, (ld, tt)
                for k, v in hits.items():
                    agg[k] = max(agg[k], v)
        probe_rows.append({"rect": p["name"], "worst_covered": worst, "of": 121,
                           "worst_live": worst_live,
                           "worst_live_at": {"lens_deg": at[0],
                                             "tape_t": at[1]} if at else None,
                           "hits": dict(agg.most_common(8))})
        print("   %-7s worst %3d/121 covered   worst LIVE %3d/121 %s   %s"
              % (p["name"], worst, worst_live,
                 ("at lens %+.1f deg, tape %.2f" % at) if at else "",
                 dict(agg.most_common(4))))

    for o in content + stand_ins + wipe_shards:
        o.hide_viewport = False
    # restore the capture pose
    lens_piv.rotation_euler = (0, 0, math.radians(-POSE_LENS_DEG))
    tape_piv.location = (0, -off, 0)
    for sp in spool_pivs:
        sp.rotation_euler = (0, 0, -off / mod.SPOOL_R)
    bpy.context.view_layer.update()

    # ------------------------------------------------------------- depth QA
    # every probe on a VISIBLE STATIC surface (BRIEF trap 7): an interior point
    # or one on a LIVE object records whatever is behind it in depth.bin.
    rows = T.verify_depth(scene, cam, dep, [
        ("panel face (mid)", root.matrix_world @ Vector((0.0, -0.060, 0.026))),
        ("panel face (top)", root.matrix_world @ Vector((0.0, 0.160, 0.026))),
        # log_win_trim_0's FRONT FACE, not 4 mm in front of it: the first
        # version of this probe read err +0.0039, which is the probe point
        # floating off the surface, not an export error.  BRIEF trap 7.
        ("window trim top", root.matrix_world @ Vector((0.0, 0.146, 0.032))),
        ("deck behind tape", root.matrix_world @ Vector((0.06, 0.100, -0.003))),
        ("slot lip a", root.matrix_world @ Vector((0.0, -0.102, 0.033))),
        # the tail facet's own paper surface, OFF ITS RULED LINE.  Probing the
        # facet centre reads err -0.00296, which is log_tail_rule_3 standing
        # 3.0 mm proud of the paper there -- trap 7 again, and the same shape
        # as PKT's aperture back wall: the point was on a visible surface, it
        # was just not the surface the camera sees.
        ("tail facet 3", root.matrix_world
         @ (Vector(tail_local[3][0]) - tail_local[3][2] * (TAIL_STANDOFF - 0.0011)
            - tail_local[3][1] * 0.007)),
    ])
    print("  DEPTH VERIFY (close)")
    for nm, want, got, err in rows:
        print("    %-20s want %.5f  got %.5f  err %+.6f" % (nm, want, got, err))

    # ------------------------------------------------------------ hotspots
    def bb(objs, pad=8):
        return clamp_rect(mod.bbox_rect(scene, cam, objs, pad=pad), W, H)

    rects = []
    for a in LENS_POSES:
        lens_piv.rotation_euler = (0, 0, math.radians(-a))
        bpy.context.view_layer.update()
        rects.append(mod.bbox_rect(scene, cam, lens_objs, pad=8))
    hs_lens = clamp_rect(mod.union(rects), W, H)
    lens_piv.rotation_euler = (0, 0, math.radians(-POSE_LENS_DEG))
    bpy.context.view_layer.update()
    # the tape hotspot is the WINDOW plus the two spool ports, as build.py's own
    # main() computes it -- not the ribbon's mostly-hidden full extent
    pad = 0.014
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            pts.append((sx * (mod.APX + pad),
                        mod.APY0 if sy < 0 else mod.APY1, mod.FACE_Z))
            pts.append((sx * mod.SPOOL_X + sx * 0.078,
                        mod.SPOOL_Y + sy * 0.078, mod.FACE_Z + 0.03))
    xs, ys = [], []
    for q in pts:
        x, y = mod.project(scene, cam, root.matrix_world @ Vector(q))
        xs.append(x); ys.append(y)
    hs_tape = clamp_rect({"x": round(min(xs)), "y": round(min(ys)),
                          "w": round(max(xs) - min(xs)),
                          "h": round(max(ys) - min(ys))}, W, H)
    hs_src = bb([bpy.data.objects["log_src_bezel"]] + src_objs + src_domes,
                pad=8)
    hs_wipe = bb([bpy.data.objects["log_wipe_frame_%d" % i] for i in range(4)],
                 pad=4)

    def names(objs):
        return [o.name for o in objs]

    # ---------------------------------------------------------- scene.json
    j = {
        "render": {"w": W, "h": H},
        "camera": T.cam_json(scene, cam),
        "lights": T.lights_json(scene, close_tags),
        "world_bg": list(scene.world.node_tree.nodes["Background"]
                         .inputs[0].default_value),
        "colour": {"view_transform": scene.view_settings.view_transform,
                   "look": scene.view_settings.look,
                   "exposure": scene.view_settings.exposure},
        "light_gain": LIGHT_GAIN,
        "env_intensity": 0.0,
        "raytrace": 1,
        "scale": 1.0,
        "ubias_m": UBIAS,
        "obliquity_deg": obliq,
        "depth": {"file": "depth.bin", "format": "float32-le",
                  "layout": "top-down rows, 1 value per pixel",
                  "meaning": "linear view depth in metres along -Z_cam",
                  "background": 1e10},
        "face": {"u": T.to3(ux), "v": T.to3(uv), "n": T.to3(un),
                 "origin": T.to3(root.matrix_world @ Vector((0, 0, 0))),
                 "spin_axis": spin_axis,
                 "spin_note": "rotate by a POSITIVE angle about spin_axis for "
                              "a CLOCKWISE turn on screen; build.py's CSS "
                              "convention"},
        "props": {
            "tape": {
                "glb": "tape.glb", "kind": "advance",
                "label": ctrl["tape"]["label"],
                "nodes": names(ribbon),
                "travel_m": mod.TAPE_TRAVEL, "travel_axis": travel_axis,
                "frames": ctrl["tape"]["frames"],
                "rest_t": POSE_TAPE_T,
                "row_pitch_m": TAPE_LEAD,
                "spools": [{"glb": "spool%d.glb" % i,
                            "nodes": names(spool_grp[i]),
                            "hub": T.to3(spool_hubs[i]),
                            "axis": spin_axis,
                            "rad_per_m": 1.0 / mod.SPOOL_R} for i in range(2)],
                "hotspot": hs_tape},
            "lens": {
                "glb": "lens.glb", "kind": "rotate",
                "label": ctrl["lens"]["label"],
                "nodes": names(lens_objs),
                "hub": T.to3(lens_hub), "axis": spin_axis,
                "range": list(ctrl["lens"]["range"]),
                "rest_deg": POSE_LENS_DEG,
                "arm_m": mod.LENS_ARM,
                "pivot_px": dict(zip(("x", "y"),
                                     mod.project(scene, cam, lens_hub))),
                "hotspot": hs_lens},
            "source": {
                "glb": "source.glb", "lamps_glb": "srclamps.glb",
                "kind": "states",
                "label": ctrl["source"]["label"],
                "states": list(ctrl["source"]["states"]),
                "angles": list(ctrl["source"]["angles"]),
                "nodes": names(src_objs), "domes": names(src_domes),
                "hub": T.to3(src_hub), "axis": spin_axis,
                "mats": {k: m.name for k, m in ctrl["source"]["mats"].items()},
                "hotspot": hs_src},
            "wipe": {
                "glb": "wipe.glb", "glass_glb": "wipeglass.glb",
                "lamp_glb": "wipelamp.glb", "kind": "states",
                "label": ctrl["wipe"]["label"],
                "states": list(ctrl["wipe"]["states"]),
                "nodes": names(wipe_lever),
                "pane": wipe_pane.name, "shards": names(wipe_shards),
                "dome": wipe_dome.name,
                "hub": T.to3(wipe_hub), "axis": spin_axis,
                "throw_deg": ctrl["wipe"]["throw"],
                "mats": {k: m.name for k, m in ctrl["wipe"]["mats"].items()},
                "hotspot": hs_wipe},
        },
        "text_planes": planes,
        "ink": inks,
        "readout_text": [POSE_TEXT[p["name"]] for p in planes],
        "capture_pose": {"tape_t": POSE_TAPE_T, "tape_off_m": off,
                         "lens_deg": POSE_LENS_DEG, "source": POSE_SOURCE,
                         "wipe": POSE_WIPE},
        "tris": {"live": tri_live, "static": tri_static},
        "depth_verify": [{"name": a, "analytic": b, "baked": c, "err": dd}
                         for a, b, c, dd in rows],
        "rect_probe": probe_rows,
        "ubias_detail": {k: U[k] for k in
                         ("n_raw", "n_inner", "raw_min", "min", "p1", "p5",
                          "median", "max", "plateau", "plateau_frac",
                          "emerging", "ubias_m", "ubias_p1_m")},
    }
    with open(os.path.join(OUT, "scene.json"), "w") as f:
        json.dump(j, f, indent=1)
    with open(os.path.join(OUT, "materials.json"), "w") as f:
        json.dump(T.materials_json(), f, indent=1)

    # ------------------------------------------------- the plane-cut control
    # LOG's shipped tape plane sits 0.8 mm IN FRONT of the pen trace, so it
    # does not cut the carrier.  This second scene.json puts it at 0.0064 --
    # inside the trace slabs and inside the ruled lines -- so the plane CUTS
    # live geometry and check_occlusion.py's `plane cut` allowance (PKT NOTES
    # 8.2, added for exactly this module) is exercised on real geometry.  It is
    # a separate FILE; nothing shipping is mutated.
    if os.environ.get("LOG_CONTROL_PLANE") == "1":
        jc = json.loads(json.dumps(j))
        p0 = jc["text_planes"][0]
        cut = Vector((TAPE_CX, TAPE_CY - off, 0.0064))
        o2 = root.matrix_world @ cut
        p0["name"] = "tape_cut_control"
        p0["local"] = list(cut)
        p0["origin"] = T.to3(o2)
        p0["corners_px"] = {
            k: dict(zip(("x", "y"), mod.project(
                scene, cam, o2 + ux * (TAPE_HW * sx) + uv * (TAPE_HH * sy))))
            for k, sx, sy in (("tl", -1, 1), ("tr", 1, 1),
                              ("bl", -1, -1), ("br", 1, -1))}
        with open(os.path.join(OUT, "scene_control.json"), "w") as f:
            json.dump(jc, f, indent=1)
        print("CONTROL -> scene_control.json (the tape plane at z 0.0064, "
              "INSIDE the ruled lines and the pen trace)")

    print("EXPORT OK ->", OUT)


# ===========================================================================
# THE REFIT PORT -- a SECOND entry point, deliberately separate from main().
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_log.py -- refit
#
# main() above rebuilds the shell and RE-RENDERS plate.png, depth.bin and all
# ten gt_*.png.  Running it would invalidate every number in live3d/RESULTS.md
# and modules/LOG/NOTES.md.  This entry point does none of that: it builds the
# port alone in an empty scene, writes assets/LOG/refit.glb, and merges a
# "refit" block into the existing scene.json.  Nothing else in assets/LOG/ is
# opened for writing.  FIX_UPLOAD.md section 0, decision 3.
#
# ROOT_SCALE IS NOT PASSED, AND MUST NOT BE.  FIX_UPLOAD 12.15 item 2: on this
# entry point you are inside NOTHING -- the scene is cleared and the port is
# built in WORLD coordinates from the solver's own frame.  LOG's own main()
# builds inside a root at scale 1.0 anyway, but `check_root_scale()` refuses a
# non-unit value in an empty scene whatever the module's main() uses.
#
# THE ANCHOR IS THE DESIGN'S OWN, MIRRORED ACROSS THE RECORDER BY THE DOCKET.
# FIX_UPLOAD 3.3 tables (270, 661) at 56 px, "fascia bulkhead".  Unlike four of
# the seven tabled anchors before it, LOG's tabled CARRIER is right and its
# SIZE is right: the console fascia below the recorder's frame is dead flat
# over the port's own footprint (plane-fit |resid| p50 0.0000000 m, max
# 0.0000200 m over an 80 x 70 px window), 100 % solid, and
# `refit_port.py LOG 270 661 56 --sub-base --sweep-y 600,719` accepts an
# unbroken band from y 608 to y 686 -- 78 px of clean bulkhead against a 56 px
# envelope.  Above y 606 the port's foot climbs the instrument's brass lower
# frame rail and the solver refuses (seat 32.5 mm against a 5.7 mm cap); below
# y 686 the envelope leaves the frame.  Nothing about the CARRIER moved this.
#
# WHAT MOVED IT: THE DOCKET, AND THE DOCKET HAS TWO HEIGHTS.
# FIX_UPLOAD 12.16 item 5 and 12.17 item 5 say to solve the docket on the
# RUNNING PAGE before fixing the anchor.  Done, with a real pointer, and the
# fleet's instruction is one measurement short:
#
#     state                                 docket
#     sealed / queued / building / running  520 x 317.9
#     APPLIED  (a ceremony has finished)    520 x 410.2   <-- 92.3 px taller
#
# `paintPhases()` gains the PROVE and ASSAY result lines when the refit lands,
# so the docket a player is looking at 3 s after pressing FORCE REFIT is not
# the docket that was measured, and `placeDocket()` re-solves for the new
# height on the next frame.  Every module's NOTES record ONE figure.
#
# At the TABLED (270, 661) the IDLE docket already lands at (12, 390) --
# x 12..532, y 390..708 -- which contains the WHOLE port hotspot; a real
# pointer at the port's own centre returned a docket button.  Nudging 15 px
# down to (270, 676) fixes the idle case (16.8 % covered, centre clear) and
# does NOT fix the applied one: at 410.2 px tall the winning candidate clamps
# to (12, 298) and covers 91.9 % of the port, centre included.
#
# Walking the whole sill against BOTH heights (`placeDocket()` reproduced in
# stdlib, checked against the real page and agreeing to the pixel):
#
#     port anchor      idle 317.9         applied 410.2
#     140..460 x 662   ( 12, 323)  17 %   ( 12, 298)  100 %  BURIED
#     140..460 x 676   ( 12, 337)  17 %   ( 12, 298)   92 %  BURIED
#     140..460 x 686   ( 12, 347)  18 %   ( 12, 298)   82 %  BURIED
#     600 x 682        ( 40, 390) 0.3 %   ( 40, 298)  0.3 %  ok
#     820..1140 x 676  (748, 337)  17 %   (748, 245)   18 %  ok
#
# The whole PORT half of the fascia is buried in the applied state at every y,
# and the STARBOARD half is clear in both.  So the port mirrors the tabled
# column across the recorder -- 270 -> 1010, a 740 px move, which is PKT's
# 660 px for the same reason one level deeper.  The band at x 1010 is y
# 608..686, 78 px, exactly the band at x 270: it is the same fascia.
#
# The one other clean answer, (600, 682) directly under the tear-off tail, was
# rejected on room: at x 600 the accepting band is only y 676..686, hemmed by
# the tail above (y 664 is REFUSED by `verify_seat()` -- the port's foot is on
# clean sill and its FACE reaches up onto the tail, coming within 1.108 mm of
# the baked plate at (564, 677); FIX_UPLOAD 12.17 item 1's new Overhang check
# firing on a ninth module) and by the frame below (y 688 is off-frame), and
# its hotspot is clipped by the bottom of the frame.
#
# WHAT IT COSTS, SAID OUT LOUD.  `WIPE`'s centre is inside the docket at every
# anchor on this half of the fascia, as `SOURCE`'s is at every anchor on the
# other half: a 520 px docket on a 1280 px stage with its y clamped cannot miss
# both of LOG's bottom controls (x 361 and x 921).  One buried control centre
# is the minimum available and it is KVS's finding again -- what is different
# here is that the PORT is not the thing being buried.  And the docket's bottom
# edge is always `cy - 26`, so it lies over the top 8.8 px of the port's own
# 63 px envelope -- the frame's top rim.  The iris, the throat, the jewel, the
# tally and the whole gesture are clear in both docket states.
#
# obliquity  the carrier fits at 9.46 deg against LOG's declared face normal at
#            5.00 -- the two NORMALS are 8.04 deg apart, so this is a genuinely
#            different plane that happens to be at a similar rake to the
#            camera.  Built on the carrier's, per FIX_UPLOAD 12.2.  Fleet
#            normal split: KVS 45.08, PKT 31.52, MTA 8.73, LOG 8.04,
#            FMM 0.07, MQB 0.00.
# W          0.0477 m across flats, not the ~35 mm section 2's table implies:
#            the table takes px/m at the READOUT plane (1.24-1.26 m here) and
#            this carrier is at 1.30-1.32 m.  FIX_UPLOAD 12.5, on a ninth
#            module and in the same direction as all eight before it.
# sub_base   ON, and LOG is one of the two modules 12.14 item 3 names.  The
#            fascia below the recorder's frame is featureless bulkhead: the
#            nearest structure is the frame rail ~70 px above the envelope's
#            top edge, 1.5 W away and outside the "~1 W" the rule draws the
#            line at, and the 1.3 W footprint has nothing to climb -- the 78 px
#            flat band is the check that says so.
# mark       None.  532 triangles for a 3 px smear; FIX_UPLOAD 12.9.
LOG_REFIT = dict(px=1010, py=676, port_px=56,
                 # THE PORT'S OWN ENVELOPE ON CLEAN BULKHEAD, and passed
                 # explicitly on the instruction of FIX_UPLOAD 12.15 item 8.
                 # It is load-bearing here for the FIFTH reason 12.17 item 1
                 # adds to the list -- how far you are EXTRAPOLATING.  LOG's
                 # fascia is a CYLINDER: `depth.bin` along row 675 runs
                 # 1.2635 m at x 0 to 1.3294 m at x 640 and back to 1.2707 m at
                 # x 1240, so a plane fitted over 250 px of it has a max
                 # residual of 1.64 mm against 0.02 mm over the port's own
                 # 80 x 70 px window.
                 carrier_window=(970, 1050, 643, 713),
                 label="REFIT", mark=None,
                 sub_base=True, service_rail=True)


def refit():
    import refit_port as RP
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(LOG_REFIT)
    A = RP.solve_anchor(CODE, K["px"], K["py"], K["port_px"],
                        carrier_window=K["carrier_window"],
                        sub_base=K["sub_base"],
                        service_rail=K["service_rail"])
    P = RP.build("log_refit", A["frame_blender"], A["W_m"],
                 spin_deg=A["spin_deg"], seat=A["seat_m"],
                 label=K["label"], mark=K["mark"],
                 sub_base=K["sub_base"], service_rail=K["service_rail"])
    RP.export(CODE, A, P, label=K["label"])
    print("REFIT PORT OK -> %s  (%d tris)" % (OUT, P["tris"]))


# ===========================================================================
# THE TELLTALE MAST -- a THIRD entry point, on the same terms as `refit`.
#
#     /Applications/Blender.app/Contents/MacOS/Blender --background \
#         --python live3d/pipeline/export_log.py -- mast
#
# Like `refit`, and for the same reason: main() re-renders plate.png, depth.bin
# and all ten gt_*.png and would invalidate every number in live3d/RESULTS.md
# and modules/LOG/NOTES.md.  This entry point builds the mast alone in an empty
# scene, writes assets/LOG/mast.glb, and merges a "mast" block into the
# existing scene.json.  Nothing else in assets/LOG/ is opened for writing.
# `root_scale` is not passed here either -- FIX_UPLOAD 12.15 item 2.
#
# WHY IT IS *NOT* ON THE REFIT PORT'S SERVICE RAIL.  STATUS_AT_A_GLANCE 11.2
# mounts this fitting on the port's rail and says to "solve the rail first".
# Solved first, at BOTH anchors LOG's port could have taken, and it cannot
# carry a fleet-sized mast at either.
#
#   * AT THE SHIPPED ANCHOR the rail runs OFF THE FRAME.  The rail runs along
#     the carrier's `u`, which is screen-RIGHT, and the port is 230 px from the
#     right edge.  `status_mast.py LOG --m 4 --rake 0 --sweep-px 80,240`:
#
#         mast_px   envelope px                        note
#           150     1090.7..1266.5 657.5..703.4
#           160     1090.4..1278.4 656.3..705.4        1.6 px to the frame edge
#           170     1090.1..1289.6 654.3..706.5        OFF FRAME
#           180     1089.8..1301.3 652.9..708.1        OFF FRAME
#
#     That is MTA's failure exactly (MTA NOTES 10 item 2): a port on a strip of
#     structure whose `u` runs out before 1.5 W + L does.
#
#   * AT THE TABLED ANCHOR (270, 661) it is worse, and it is worth recording
#     because it is the reason the design's own placement could not have been
#     rescued by leaving the port where it was.  240 px to that port's right the
#     TEAR-OFF TAIL hangs out of the slot standing 95 mm PROUD of the fascia
#     (`depth.bin` reads 1.2169 m over x 512..790, y <= 646 against the fascia's
#     1.3128 m), and the rail runs straight at it:
#
#         mast_px   envelope px                   lift       worst gap
#           140     346.8.. 506.7 646.2..693.1     9.28 mm     2.0 px
#           150     346.4.. 518.0 644.2..694.5    10.05 mm     0.0 TOUCHES
#           160     346.0.. 529.2 642.1..695.9    10.82 mm     0.0 TOUCHES
#           170     344.3.. 542.4 647.1..705.4    34.01 mm     0.0 TOUCHES
#           180     343.4.. 554.6 647.2..709.5    41.74 mm     0.0 TOUCHES
#           200     341.8.. 579.3 647.2..717.4    REFUSED, CANTILEVER 0.26 L
#
#     Three refusals from one tail: from 150 px the envelope OVERLAPS the
#     declared readout rect `tail_6` (x 512..767, y 618..645) -- 146 px2 at 160,
#     93 at 180; between 160 and 170 px the LIFT CLIFFS from 10.8 mm to 34.0 mm
#     because the hull's top edge crosses the tail and `_solve_lift()` correctly
#     stops clearing the fascia and starts clearing something 95 mm nearer the
#     camera (FIX_UPLOAD 12.16 item 6's FMM cliff on a second module, and 4x its
#     size); and at 200 px STATUS_AT_A_GLANCE 18.5's 0.25 L cantilever floor
#     fires outright.  Every `--at` position between that port and the tail is
#     refused for the same readout-rect reason: (400, 680) 203 px2 on `tail_6`,
#     (420, 680) 224 px2, (440, 684) 122 px2.
#
# WHERE IT WENT INSTEAD, AND WHY EXACTLY THERE.  `status_mast.py`'s SECOND
# documented route, `--at PX,PY`, which builds STATUS_AT_A_GLANCE 6.1's ORIGINAL
# device -- "a small brass status sub-plate bolted to the panel" -- that 11.2's
# rail was an upgrade to and not a replacement for.  It goes on the PORT side of
# the same fascia sill, mirroring the refit port across the recorder, which is
# MTA's answer on the module MTA NOTES 10 item 2 was written for.  Both fittings
# are then bolted to the same wall at the same height (port envelope
# y 648.3..703.6, mast 636.9..696.2) and at a similar rake (carrier 9.46 deg to
# starboard, 11.86 to port).
#
# The exact x is decided by the DOCKET and by the CAPTION, both measured on the
# running page:
#   * with the port to starboard the docket owns x 748..1268 in BOTH its heights
#     (520 x 317.9 idle, 520 x 410.2 applied -- see LOG_REFIT), so everything
#     left of x 748 is clear of it and the mast is 0 % covered with the port
#     open, which is STATUS_AT_A_GLANCE 6.5 item 4's entire point.
#   * `mast.js`'s caption solver takes its FIRST candidate, "starboard, on the
#     sill", and that puts the caption 12 px to the mast's right.  The tear-off
#     tail's last line is inked from x 517 to x 645, so where the mast sits
#     decides whether the caption lands on it:
#
#         --at x    caption            px2 of the tail's INK covered
#           40      (253.5, 626)        0
#           60      (273.5, 626)      225
#           80      (293.6, 626)      611
#          120      (333.7, 626)    1,380
#
#     40 is the largest x that clears the tail's type completely, and it still
#     leaves 33 px of bare fascia between the mast's envelope and the left frame
#     edge (MTA ships 18 px).  The caption is 255 x 86 px of bare sill with
#     0 px2 on either fitting, sealed and open.
#
# THE FOUR DECISIONS (KVS NOTES 15.6), all four measured:
#   --rakes    RAKE 0.  The table is monotonic from the carrier's own 11.86 deg
#              and every rake makes it worse:
#                  rake     0    15    30    45    57    60    75    90
#                  obliq 11.86 22.56 36.35 50.77 62.47 65.40 80.11 94.84
#              and obliquity is not the criterion anyway (STATUS_AT_A_GLANCE
#              17.5).  The criterion is `px_per_m_carrier`, v against n:
#              v 1153.9 against n 424.7, a ratio of 2.72x, further from 1 than
#              MTA's 2.05x and nothing like KVS's 1.44 or PKT's 1.56.  There is
#              no second axis to recover here, and at rake 0 the mast's own two
#              axes project at A 1248.0 and B 1153.9 px/m -- a ratio of 1.08,
#              unforeshortened in both directions, which is what KVS's 45 deg
#              was buying.
#              Fleet: KVS 45, MQB 0, MTA 0, OTA 57, FMM 0, IPM 54, PKT 45,
#              LOG 0.
#
#              STATUS_AT_A_GLANCE 6.5 item 3 says "LOG's deck at (500, 640)
#              comes out at 100.5 deg at KVS's 45".  (500, 640) IS THE TEAR-OFF
#              TAIL -- a non-planar carrier hanging 95 mm proud of the fascia,
#              not a deck, and not a carrier either fitting can use.  On the
#              fascia the mast is actually bolted to, rake 45 is 50.77 deg and
#              rake 90 is 94.84.  The 100.5 deg figure does not reproduce
#              anywhere on LOG's sill and should not be inherited.
#   --px 180   swept 120..240 with `--sweep-px`.  There is NO cliff on this
#              carrier -- the lift is 5.41 mm flat across the whole sweep -- so
#              the size is a free choice and 180 is the fleet's.  It gives 4
#              graduations of 26.0 px, the roomiest in the fleet (KVS 18.0 for
#              six, MTA 12.5 for eight).
#   --m 4      the COUNT of log-module/vuln_tests/NN_*.py, never max(NN)
#              (STATUS_AT_A_GLANCE 9.4 rule 4).  01, 02, 03, 04 -- no gaps, and
#              LOG is the one module whose README vuln count and shipped PoC
#              count already agreed.  `refit.js`'s FLEET table says 4 as well.
#   numbers    OFF, as on all eight.  26.0 px of pitch is the roomiest in the
#              fleet and the engraved digits would still land at ~10 px of cap
#              height -- KVS cut them at 9 px (STATUS_AT_A_GLANCE 6.5 item 6)
#              and the fleet has been consistent since.  The catalogue list in
#              the hover panel carries the identity instead, in the same order
#              as the lamps.
LOG_MAST = dict(mast_px=180, rake_deg=0.0, m=4, kind="defensive",
                numbers=False, at=(40, 676),
                # THE MAST'S OWN FOOTPRINT ON CLEAN SILL, and it is worth 2x
                # the lift.  The DEFAULT window (px +/- 40, py +/- 24) is 80 px
                # wide for a 205 px fitting, and on this cylinder of a fascia --
                # 1.2635 m at x 0, 1.3294 m at x 640, 1.2707 m at x 1240 along
                # row 675 -- extrapolating an 80 px plane over 205 px answers a
                # lift of 10.82 mm where the fitting's own footprint answers
                # 5.41 mm.  FIX_UPLOAD 12.16 item 4 and MTA NOTES 10 item 1, on
                # a ninth module.
                carrier_window=(32, 247, 645, 704))


def mast():
    import status_mast as SMT
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    K = dict(LOG_MAST)
    A = SMT.solve_mast(CODE, mast_px=K["mast_px"], rake_deg=K["rake_deg"],
                       m=K["m"], kind=K["kind"], numbers=K["numbers"],
                       px=K["at"][0], py=K["at"][1],
                       carrier_window=K["carrier_window"])
    P = SMT.build("log_mast", A["frame_blender"], A["carrier_blender"],
                  A["L_m"], m=A["m"], kind=K["kind"], numbers=K["numbers"],
                  rail=A["rail"], ramp=A["rail_ramp"])
    SMT.export(CODE, A, P)
    print("TELLTALE MAST OK -> %s  (%d tris)" % (OUT, P["tris"]))


if __name__ == "__main__":
    _argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "refit" in _argv:
        refit()
    elif "mast" in _argv:
        mast()
    else:
        main()
