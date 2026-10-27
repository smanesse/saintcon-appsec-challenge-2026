"""Blender's OWN type metrics for a module's FONT objects -- measured, exact,
and with no render in the loop.

    from typemetrics import measure_type
    m = measure_type(mod, size)          # mod = the module from load_module()
    m["adv"], m["cap"], m["base"]        # metres, in MODULE-LOCAL units

WHY THIS FILE EXISTS.  CONVERSION_BRIEF step 4 used to say "band-detect the
glyphs in your type-only render and read the advance off it".  That is how KVS
shipped `adv_m = 0.0100` for `FONT.size = 0.031`, where Blender's own advance is
**0.009631** -- 3.8% narrow, which laid KVS's own 24-character transcript line
out 15 stage px too wide (measured: DOM ink 382 px against Blender's 367 px).
Band detection also has nothing to detect on a module whose type is 4 px tall.

The exact statement is one line of geometry:

    bbox_width("MM") - bbox_width("M")   ==   one advance

for a monospaced face with no kerning, taken off `obj.to_mesh()` rather than off
pixels.  Measured for all three shipped modules, at every size each of them
uses, with LEFT and CENTER alignment:

    Courier New Bold, via every module's own text() helper
        adv  / FONT.size  = 0.310667      (constant to 6 places)
        cap  / FONT.size  = 0.306623
        base / FONT.size  = -0.137765     (baseline BELOW the object origin,
                                           for align_y='CENTER')

Cross-checked against the font file itself: Courier New Bold advances
1229/2048 = 0.600098 em and its "M" is 1213/2048 = 0.592285 em tall, a
cap/advance ratio of 0.98699; Blender reproduces 0.306623/0.310667 = 0.98698.
Blender is faithful; `FONT.size` is simply not an em (one size unit is 0.51769
em for this face).

**The ratio is a property of the FACE, not of the module.**  MTA's NOTES report
0.31067 "here" against "0.32258 on KVS" and conclude the ratio is per-module;
0.32258 is 0.0100/0.031, i.e. KVS's *wrong shipped* adv_m divided by its size,
not a measurement.  Both agents found the same defect.  Measure anyway -- a
module that loads a different face will have a different ratio -- but if your
module uses `mono_font()` and gets Courier New Bold, 0.310667 is the number and
anything else means your probe is wrong.
"""
import bpy


def measure_type(mod, size, align='LEFT', extrude=None, font=None):
    """(adv, cap, base) in module-local metres for `mod`'s own type at `size`.

    Uses the module's own `text()` helper where it has one, so any per-module
    `extrude` / `space_character` / font choice is included in the measurement
    rather than assumed away.  Builds two throwaway objects, converts them with
    `to_mesh()`, and deletes them; it renders nothing and leaves no trace in the
    scene (call it before or after add_props, it does not matter).
    """
    out = {}
    made = []
    try:
        for body in ("M", "MM"):
            o = _probe(mod, body, size, align, extrude, font)
            made.append(o)
            me = o.to_mesh()
            xs = [v.co.x for v in me.vertices]
            ys = [v.co.y for v in me.vertices]
            out[body] = (max(xs) - min(xs), min(ys), max(ys))
            o.to_mesh_clear()
    finally:
        for o in made:
            try:
                bpy.data.objects.remove(o)
            except Exception:
                pass
    adv = out["MM"][0] - out["M"][0]
    cap = out["M"][2] - out["M"][1]
    # align_y='CENTER' anchors the object origin on the line's vertical centre.
    # "M" sits ON the baseline, so the baseline is at the "M" ink's own minimum
    # y -- a NEGATIVE number, the signed offset from the origin.  This is what
    # the frontend needs to put the CSS baseline where Blender put it, and it is
    # what replaces `base_adj`: it scales with size, so a module with four type
    # sizes gets four correct offsets instead of one fudge that fits none.
    base = out["M"][1]
    return {"adv": adv, "cap": cap, "base": base,
            "ratio": adv / size, "cap_ratio": cap / size,
            "base_ratio": base / size}


class NoModuleFont(RuntimeError):
    """The module has neither a `text()` helper nor a `mono_font()`.

    RAISED RATHER THAN GUESSED.  This used to fall through to
    `bpy.data.curves.new(...)` with no `cu.font` assigned, which measures
    Blender's DEFAULT face (Bfont, a PROPORTIONAL one) and returns a plausible
    `adv_m` that is wrong by tens of percent -- silently, on exactly the three
    modules that author no type of their own (DNSM, FMM, LOG) and therefore
    have to CREATE it in the exporter (brief step 3, "a readout with no baked
    type").  FMM NOTES 8.8.

    The fix in your exporter is the same nine lines FMM wrote: resolve the
    face yourself and pass it in.

        import typemetrics as TM
        FONT = bpy.data.fonts.load("/System/Library/Fonts/Supplemental/"
                                   "Courier New Bold.ttf")   # or whatever your
                                                             # own type() uses
        m = TM.measure_type(mod, size, font=FONT)

    or give the module object a `mono_font()` before you call this.  If you
    then get a `ratio` other than 0.310667 out of Courier New Bold, the probe
    is wrong -- that is the whole point of the assertion in the docstring
    above, and it cannot do its work against a face nobody chose.
    """


def _probe(mod, body, size, align, extrude, font=None):
    fn = getattr(mod, "text", None)
    if callable(fn):
        try:
            m = bpy.data.materials.get("_typeprobe") or \
                bpy.data.materials.new("_typeprobe")
            o = fn("_typeprobe_" + body, body, size, m, (0, 0, 0), align=align)
            if extrude is not None:
                o.data.extrude = extrude
            return o
        except TypeError:
            pass                       # helper with a different signature
    f = font if font is not None else getattr(mod, "mono_font",
                                              lambda: None)()
    if f is None:
        raise NoModuleFont(
            "%s has no text() helper and no mono_font(), and no `font=` was "
            "passed to measure_type().  Refusing to measure Blender's DEFAULT "
            "font and return it as though it were your module's: the number "
            "would be plausible and wrong.  See typemetrics.NoModuleFont."
            % getattr(mod, "__name__", repr(mod)))
    cu = bpy.data.curves.new("_typeprobe", 'FONT')
    cu.body, cu.size = body, size
    cu.align_x, cu.align_y = align, 'CENTER'
    cu.extrude = 0.0003 if extrude is None else extrude
    cu.font = f
    o = bpy.data.objects.new("_typeprobe_" + body, cu)
    bpy.context.collection.objects.link(o)
    return o


def type_block(mod, size, *, lead_m, left_m, top_m, n_lines, scale=1.0,
               align="left", line_sizes=None, font=None):
    """The `text_planes[].type` dict of the schema, filled in from Blender.

    `scale` is the module root's own scale (MQB's is 0.70), so every length
    comes out in WORLD metres.  `line_sizes`, when a plane's lines are not all
    the same FONT.size (MTA's webhook slip), produces `line_adv_m` / `line_base_m`
    lists the frontend applies per line.
    """
    m = measure_type(mod, size, font=font)
    t = {"adv_m": m["adv"] * scale,
         "lead_m": lead_m * scale,
         "left_m": left_m * scale,
         "top_m": top_m * scale,
         "base_m": m["base"] * scale,
         "cap_m": m["cap"] * scale,
         "base_adj": 0.0,
         "n_lines": n_lines,
         "size_m": size,
         "align": align}
    if line_sizes:
        per = [measure_type(mod, s, font=font) for s in line_sizes]
        t["line_adv_m"] = [p["adv"] * scale for p in per]
        t["line_base_m"] = [p["base"] * scale for p in per]
    return t
