/* Minimal CSS-3D layer.
 *
 * WHY THIS FILE EXISTS.  The vendored three.js in three-exploration/vendor
 * ships build/ + a handful of examples/jsm modules; CSS3DRenderer is not among
 * them, and pulling a second copy of three from a CDN to get one 120-line file
 * is a worse trade than writing the 60 lines.  The maths below is the same
 * maths CSS3DRenderer uses, so it stays swappable.
 *
 * WHAT IT IS FOR.  Content text on the KVS console face.  That face is raked
 * 71.2 deg off horizontal (measured, see live3d/NOTES.md), so a flat DOM box
 * pinned over it in screen space reads as a sticker floating in front of the
 * panel.  Putting the SAME DOM nodes through the SAME projection the WebGL
 * camera uses makes them lie ON the panel -- still real text nodes, still
 * selectable, still updated with textContent, still resolution-independent,
 * because the browser rasterises the element AFTER the transform.
 *
 * THE CONTRACT with three.js:
 *   perspective = projectionMatrix[5] * (H/2)      (px)
 *   camera element = translateZ(perspective) * flipY(viewMatrix) * centre
 *   object element = translate(-50%,-50%) * flipYcolumn(worldMatrix)
 * The two flips are the CSS y-down / WebGL y-up reconciliation: one on the
 * view matrix's Y ROW, one on each object matrix's Y COLUMN.
 *
 * ------------------------------------------------------------------------
 * WHY THIS LAYER CULLS BACK-FACING ELEMENTS ITSELF, AND DOES NOT USE
 * `backface-visibility`.
 *
 * Every caller places a readout with the same convention (_TEMPLATE/module.js,
 * app.js and all nine modules copied from them):
 *
 *     makeBasis(u * MPP, v * MPP, n).setPosition(o)      MPP = 2e-4
 *
 * so the element's two in-plane columns are 2e-4 long -- the matrix maps
 * ELEMENT PIXELS to METRES.  Chrome decides back-facing from the sign of the
 * accumulated transform's upper-left 2x2 determinant, and with that basis the
 * determinant is ~3.1e-08.  BELOW ROUGHLY 1e-3 CHROME DECLINES TO CULL AT ALL,
 * so `backface-visibility: hidden` -- which this file used to set on every
 * element it added -- WAS COMPLETELY INERT ON EVERY READOUT IN THE FLEET.  It
 * only ever mattered on the one carrier that turns away, DNSM's chart drum,
 * which painted its back-facing facets' text, mirrored.  DNSM NOTES section 8
 * bisected the threshold on the real matrices: 2.0e-4 -> det 3.09e-08, no cull;
 * 4.0e-2 -> 1.24e-03, no cull; 1.0e-1 -> 7.72e-03, culls.
 *
 * MEASURED HERE on DNSM's own back-facing chart3 matrix (repro
 * /private/tmp/shoot/bfx/t.html, one 110x70 white box, ink px in the shot):
 *
 *     as shipped, the scale baked into the element's matrix       4262  paints
 *     `transform-style: flat` on the same element                 4262  paints
 *     NORMALISED matrix + a separate scale3d() on the SAME el     4262  paints
 *     normalised matrix on a wrapper, scale3d() on the element       0  culled
 *
 * The third row is the fix DNSM proposed and IT DOES NOT WORK: the accumulated
 * matrix is the product of the whole transform list, so moving the scale into
 * its own function changes nothing.  Only splitting the two across two
 * ELEMENTS does -- and that wrapper was measured to make Chrome silently drop
 * two of DNSM's own eight readouts (see the layer note below), so it is not
 * worth having.
 *
 * What this file does instead is decide the facing itself, every frame, and
 * hide the element with a class.  It is exact, it has no epsilon, it stays
 * right at grazing incidence where the 2x2 determinant goes to zero again, and
 * it is THE SAME DECISION occlusion.js's fragment shader makes -- which is the
 * property that actually matters, because a DOM element hidden while the GLSL
 * still routes fragments in front of it to the front pass punches a hole in the
 * near side of a drum.  `backface-visibility` is no longer set at all: setting
 * a property that does nothing is worse than not setting it.
 *
 * VERIFIED against the only module that can see it.  DNSM, with its own
 * module-side workaround neutralised at runtime, per-readout solo ink at dsf 2:
 *
 *     workaround on, no shared fix   1386 2061 1152 0    0    0 774 434
 *     workaround OFF, no shared fix  1386 2061 1152 0 1500 1157 774 434  <- bug
 *     workaround OFF, shared fix in  1386 2061 1152 0    0    0 774 434  <- fixed
 *
 * Every front-facing count byte-identical, both leaks gone.  Swept over the
 * whole drum rotation (-180..+180 in 2.5 deg steps, 145 poses x 8 elements =
 * 1160 element-poses at dsf 1 AND dsf 2, 447 culls): **0 disagreements** with
 * DNSM's own `__dnsm.backFacing()`.
 *
 * DNSM's module-side cull is therefore now REDUNDANT and should be deleted --
 * the `r.back` / `el.classList.toggle('away', ...)` lines in `r.place()` and
 * the `.readout.away{display:none}` rule in its index.html.  Its `wanted` flag
 * is NOT redundant (it carries the courier card's slide-state intent) and
 * neither are its `backFacing()` / `domCulled()` hooks.  Deleting it is not
 * required for correctness -- the two culls agree pixel for pixel -- so it is
 * left in place for whoever owns that module.
 *
 * ------------------------------------------------------------------------
 * A CHROME DEFECT THIS FILE CANNOT FIX, AND WHAT DEFENDS AGAINST IT.
 *
 * With several near-coplanar readouts on one carrier, Chrome silently DROPS
 * one of them: it lays out correctly, `getBoundingClientRect` is right, its
 * computed style is byte-identical to its neighbours', and a solid background
 * on it does not paint.  LOG NOTES 8.3 found it on the seven facets of its
 * tear-off tail and worked around it with `transform-style: flat` plus 300
 * element px of padding on each readout.
 *
 * REPRODUCED HERE on LOG's shipped page with its workaround reverted at
 * runtime (/private/tmp/shoot/logdrop.mjs), scoring each readout by ALL minus
 * ALL-BUT-ONE so a dropped layer scores exactly 0:
 *
 *   * two of eight readouts score 0, at pixelRatio 1 AND 2.
 *   * `transform-style` IS NOT THE TRIGGER.  preserve-3d and flat give
 *     byte-identical counts at both ratios.  LOG's one-line fleet fix does
 *     not work, and this file removes `preserve-3d` anyway because it is
 *     pointless: a readout is a flat quad with plain divs in it.
 *   * the trigger is a SMALL PAINT CLIP on the transformed element.  Padding
 *     the element 300 px per side and leaving the clip off restores 8/8 at
 *     both ratios; padding it 300 px and putting the ORIGINAL clip back with
 *     `clip-path: inset(300px)` drops the same two again.
 *   * BUT THE PADDING IS A LOTTERY, and that is why it is not shipped here.
 *     Swept with the clip moved to a plain inner div, 25/50/150/200/300/400/600
 *     px of padding give 8/8 at both ratios and 75/100 give 6/8 and 250 gives
 *     7/8, at pixelRatio 2.  LOG's own sweep has the same character (310 el px
 *     fails while 210 and 410 pass).  A constant that happens to work on the
 *     module it was measured on is not a fix, and restructuring the DOM under
 *     nine verified modules to install one would risk flipping a module that
 *     is currently fine -- measured: wrapping every element in a carrier drops
 *     two of DNSM's eight, and DNSM drops none today.
 *
 * So the defence is a CHECK, not a constant: `check/check_readouts.mjs` scores
 * every readout of every module this way -- ALL minus ALL-BUT-ONE, and ALONE --
 * and FAILS a zero that the DOM says should paint (the element has
 * non-whitespace text, an on-stage rect, and is not display/visibility hidden).
 * A dropped layer scores 0 BOTH ways, so the pixel count alone cannot tell it
 * from a legitimately empty readout; the DOM facts can.  A module that trips it pads its own elements, sweeps the
 * pad at BOTH pixel ratios, and records the sweep -- LOG's recipe.
 */

const e6 = n => Math.abs(n) < 1e-6 ? 0 : n;

function camMatrix(m) {                  // negate the Y ROW  (indices 1,5,9,13)
  const a = m.elements;
  return 'matrix3d(' + [
    a[0], -a[1], a[2], a[3],
    a[4], -a[5], a[6], a[7],
    a[8], -a[9], a[10], a[11],
    a[12], -a[13], a[14], a[15]].map(e6).join(',') + ')';
}

function objMatrix(m) {                  // negate the Y COLUMN (indices 4..7)
  const a = m.elements;
  return 'matrix3d(' + [
    a[0], a[1], a[2], a[3],
    -a[4], -a[5], -a[6], -a[7],
    a[8], a[9], a[10], a[11],
    a[12], a[13], a[14], a[15]].map(e6).join(',') + ')';
}

/* The back-facing cull is a CLASS rule, injected once, and deliberately not an
 * inline style: a module's `body.notext .readout{visibility:hidden}` is a class
 * rule too, and an inline style would beat it -- the exact failure DNSM already
 * recorded against its courier card.  `display:none` and not
 * `visibility:hidden` so that it cannot be un-done by an inherited value on a
 * child, which is how `backface-visibility` was suspected of failing before the
 * real cause was found. */
const BACK_CLASS = 'css3d-back';
let styleInjected = false;
function injectStyle() {
  if (styleInjected) return;
  styleInjected = true;
  const st = document.createElement('style');
  st.id = 'css3d-layer-style';
  st.appendChild(document.createTextNode('.' + BACK_CLASS + '{display:none}'));
  document.head.appendChild(st);
}

export class CSS3DLayer {
  /** @param {HTMLElement} host absolutely-positioned box, W x H stage px */
  constructor(host, W, H) {
    injectStyle();
    this.host = host;
    this.W = W; this.H = H;
    host.style.width = W + 'px';
    host.style.height = H + 'px';
    host.style.overflow = 'hidden';
    host.style.transformStyle = 'preserve-3d';
    this.cam = document.createElement('div');
    this.cam.style.cssText =
      'position:absolute;left:0;top:0;transform-style:preserve-3d;' +
      'width:' + W + 'px;height:' + H + 'px';
    host.appendChild(this.cam);
    this.objects = [];
    this._fov = -1;
  }

  /** element is placed with its CENTRE at the object matrix's origin.
   *
   *  `transform-style: preserve-3d` is deliberately NOT set: it made every
   *  readout its own 3D rendering context for no gain (a readout is a flat
   *  quad with plain divs inside it), and LOG NOTES 8.3 asked for it to go.
   *  Measured, it is not the cause of the layer drop it was blamed for -- see
   *  the file header -- but `flat` is what CSS says `overflow: hidden` should
   *  have forced anyway, so it is set explicitly rather than left to a
   *  stylesheet.
   *
   *  `backface-visibility` is NOT set either.  It was inert at this matrix
   *  scale; render() makes the decision instead. */
  add(element) {
    element.style.position = 'absolute';
    element.style.transformStyle = 'flat';
    this.cam.appendChild(element);
    const rec = { element, matrix: null, back: false };
    this.objects.push(rec);
    return rec;
  }

  render(camera) {
    camera.updateMatrixWorld();
    const fov = camera.projectionMatrix.elements[5] * (this.H / 2);
    if (fov !== this._fov) {
      this.host.style.perspective = fov + 'px';
      this._fov = fov;
    }
    this.cam.style.transform =
      'translateZ(' + e6(fov) + 'px)' + camMatrix(camera.matrixWorldInverse) +
      'translate(' + (this.W / 2) + 'px,' + (this.H / 2) + 'px)';
    /* camera world position, straight off the matrix: this file has no three.js
     * import and does not want one. */
    const cw = camera.matrixWorld.elements;
    const cx = cw[12], cy = cw[13], cz = cw[14];
    for (const o of this.objects) {
      if (!o.matrix) continue;
      const a = o.matrix.elements;
      o.element.style.transform = 'translate(-50%,-50%)' + objMatrix(o.matrix);
      /* THE FACING DECISION.  The quad's world normal is the cofactor of the
       * two in-plane columns, col0 x col1 -- which is what CSS's own back-face
       * test uses, and which for the fleet's makeBasis(u*MPP, v*MPP, n) is
       * MPP^2 * n.  Taking it from the columns rather than reading column 2
       * means a caller that puts something else in column 2 still gets the
       * face it will actually see.
       *
       * POSITION-AWARE, not the direction-only test CSS specifies, so that it
       * agrees fragment for fragment with occlusion.js's
       *     float den = dot(P, uPlaneNrm[i]);  if (den > -1e-6) continue;
       * DNSM's module-side workaround used exactly this test and agreed with
       * the pixels over 584 facet-poses. */
      const nx = a[1] * a[6] - a[2] * a[5];
      const ny = a[2] * a[4] - a[0] * a[6];
      const nz = a[0] * a[5] - a[1] * a[4];
      const back = (a[12] - cx) * nx + (a[13] - cy) * ny +
                   (a[14] - cz) * nz >= 0;
      if (back !== o.back) {
        o.back = back;
        o.element.classList.toggle(BACK_CLASS, back);
      }
    }
  }
}

/* ------------------------------------------------------------------ TYPE
 * Laying a module's DOM readout on the plane so that its glyphs land where
 * Blender's engraved type landed.  ONE implementation, shared by app.js (KVS)
 * and by modules/_TEMPLATE/module.js, because two implementations is how the
 * numbers drift.
 *
 * The exporter hands over, per plane, in METRES on the plane
 * (pipeline/typemetrics.py measures all four off Blender itself):
 *
 *   adv_m   metres per character   = bbox("MM") - bbox("M") on to_mesh()
 *   lead_m  metres per line
 *   left_m  first column, from the rect centre   (align "left")
 *   top_m   first line's ORIGIN, above the rect centre
 *   base_m  the BASELINE, signed, below that origin  (align_y='CENTER')
 *
 * and optionally `align: "center"`, and `line_adv_m` / `line_base_m` when a
 * plane's lines are not all one FONT.size.
 *
 * TWO THINGS THAT WERE WRONG BEFORE AND ARE NOT ANY MORE:
 *
 * 1. `adv_m` used to be band-detected off the type-only render.  It is 3.8%
 *    wrong that way on KVS (0.0100 against Blender's own 0.009631) and there is
 *    nothing to band-detect on a module whose type is 4 px tall.
 *
 * 2. `base_adj` used to be "the one fudge you are allowed", a constant in
 *    ELEMENT pixels.  The offset it stands for scales with font size, so one
 *    constant cannot serve a module with two type sizes (MTA's slip) let alone
 *    four (MQB).  It is replaced by measurement on both sides: Blender's
 *    `base_m`, and the browser's own baseline offset read off a zero-height
 *    inline-block strut.  `base_adj` stays in the schema, must be 0, and is
 *    added verbatim if some module really needs a nudge -- record why.
 *
 * Both probes are attached to document.body, NOT to the readout: the readout
 * lives under a matrix3d, and getBoundingClientRect reports TRANSFORMED
 * coordinates, so measuring in place returns the plane's foreshortening
 * multiplied into the metric.
 */

function probeBox(cs) {
  const d = document.createElement('div');
  d.style.cssText = 'position:absolute;left:-99999px;top:0;visibility:hidden;' +
    'white-space:pre;padding:0;margin:0;border:0;contain:layout';
  d.style.fontFamily = cs.fontFamily;
  d.style.fontWeight = cs.fontWeight;
  d.style.fontStyle = cs.fontStyle;
  d.style.fontSize = cs.fontSize;
  d.style.letterSpacing = cs.letterSpacing;
  d.style.fontKerning = 'none';
  return d;
}

/** Advance width of the resolved face, in em.  Courier New is 0.600098.
 *  MEASURE IT AFTER `await document.fonts.ready` -- before the face has loaded
 *  this returns the FALLBACK's metrics and lays the type out 21% wide
 *  (README 16.6). */
export function measureEmAdvance(styleSource) {
  const cs = getComputedStyle(styleSource);
  const d = probeBox(cs);
  d.style.fontSize = '400px';
  d.textContent = 'M'.repeat(50);
  document.body.appendChild(d);
  const em = d.getBoundingClientRect().width / 50 / 400;
  d.remove();
  return em;
}

/** Where the first baseline sits below the top of a line box, in element px,
 *  for this face at this font-size and line-height.  A zero-height
 *  inline-block's box sits ON the baseline, so its rect top IS the baseline.
 *  Chrome does not use hhea ascent for this on macOS -- it is 4 px off at
 *  font-size 83 -- which is exactly why it is measured and not modelled. */
export function baselineOffsetPx(styleSource, fontSizePx, lineHeightPx) {
  const cs = getComputedStyle(styleSource);
  const d = probeBox(cs);
  d.style.fontSize = fontSizePx + 'px';
  d.style.lineHeight = lineHeightPx + 'px';
  const s = document.createElement('span');
  s.style.cssText =
    'display:inline-block;width:0;height:0;vertical-align:baseline';
  d.appendChild(document.createTextNode(' '));
  d.appendChild(s);
  document.body.appendChild(d);
  const off = s.getBoundingClientRect().top - d.getBoundingClientRect().top;
  d.remove();
  return off;
}

/** Make sure the element's OWN face is loaded before anything is measured.
 *
 *  `await document.fonts.ready` IS NOT ENOUGH and this is not theoretical: a
 *  webfont declared with @font-face is only fetched when something on the page
 *  needs it, so `fonts.ready` can resolve while the face has never been
 *  requested, and `measureEmAdvance` then returns the FALLBACK's metrics.
 *  Measured on this page with four candidate faces injected: every one of them
 *  reported em 0.60205 -- the generic `monospace` fallback -- until this
 *  explicit `document.fonts.load()` was added.  README 16.6 records the
 *  symptom (type laid out 21% wide) without the cause. */
export async function ensureFont(el) {
  const cs = getComputedStyle(el);
  const shorthand = [cs.fontStyle, cs.fontWeight,
                     (cs.fontSize || '16px'), cs.fontFamily].join(' ');
  try {
    await document.fonts.load(shorthand, 'MM 0123456789');
  } catch (e) {
    console.warn('ensureFont: ' + e);
  }
  await document.fonts.ready;
}

/** Lay `lines` (the block that holds one <div> per line) out on plane `tp`.
 *  Returns the numbers it used, so a page can print them and a check can read
 *  them.  `lineEls` is optional and only needed for per-line font sizes. */
export async function layoutType(lines, tp, MPP, lineEls) {
  const t = tp.type;
  await ensureFont(lines);
  const em = measureEmAdvance(lines);
  const fs = t.adv_m / em / MPP;
  const lh = t.lead_m / MPP;
  lines.style.fontSize = fs.toFixed(3) + 'px';
  lines.style.lineHeight = lh.toFixed(3) + 'px';

  if ((t.align || 'left') === 'center') {
    /* Blender's align_x='CENTER' centres the ADVANCE width and so does CSS, so
     * for a monospaced face the two agree exactly and no column origin is
     * needed.  A fixed left column (`left_m` + white-space:pre) cannot serve
     * centred type whose content changes at runtime. */
    lines.style.left = '0px';
    lines.style.width = (2 * tp.half_w / MPP).toFixed(3) + 'px';
    lines.style.textAlign = 'center';
  } else {
    lines.style.left = ((tp.half_w + t.left_m) / MPP).toFixed(3) + 'px';
  }

  let top;
  const A0 = baselineOffsetPx(lines, fs, lh);
  if (t.base_m === undefined || t.base_m === null) {
    /* legacy export with no measured baseline: the old line-box-centre
     * approximation plus its fudge.  Emit base_m instead. */
    console.warn('layoutType: no base_m on plane "' + (tp.name || '?') +
                 '" -- falling back to the base_adj approximation');
    top = ((tp.half_h - t.top_m) / MPP) - lh / 2 + (t.base_adj || 0);
  } else {
    /* Blender's baseline for line 0, in element px below the rect's top edge,
     * minus where this face puts its baseline inside a line box. */
    top = (tp.half_h - t.top_m - t.base_m) / MPP - A0 + (t.base_adj || 0);
  }
  lines.style.top = top.toFixed(3) + 'px';

  /* Per-line font sizes (MTA's webhook slip: two sizes in one rect).  The line
   * PITCH is lead_m either way -- that is the line-height -- so only the
   * baseline inside each box moves, by the difference of the two measured
   * offsets plus the difference of Blender's two baselines. */
  const per = [];
  if (lineEls && t.line_adv_m) {
    for (let i = 0; i < lineEls.length; i++) {
      const a = t.line_adv_m[i];
      if (a === undefined) continue;
      const f = a / em / MPP;
      const b = (t.line_base_m && t.line_base_m[i] !== undefined)
        ? t.line_base_m[i] : t.base_m;
      const d = (t.base_m - b) / MPP + A0 - baselineOffsetPx(lines, f, lh);
      lineEls[i].style.fontSize = f.toFixed(3) + 'px';
      lineEls[i].style.position = 'relative';
      lineEls[i].style.top = d.toFixed(3) + 'px';
      per.push({ i, fontSize: f, dTop: d });
    }
  }
  return { em, fontSize: fs, lineHeight: lh, top,
           left: parseFloat(lines.style.left), baseline: A0, perLine: per };
}
