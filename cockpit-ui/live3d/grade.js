/* SAINTCON 2026 live-3D — the module's own COLOUR MANAGEMENT, in one place.
 *
 *   import { applyColour } from '../../grade.js';
 *   applyColour(S, renderer, split);      // AFTER the split exists, BEFORE
 *                                         // any material compiles
 *
 * WHY THIS FILE EXISTS.  `three-exploration/pipeline/transliterate.py` has
 * always emitted
 *
 *     "colour": { "view_transform": "AgX", "look": "...", "exposure": 0.0 }
 *
 * into `scene.json` for ALL NINE modules, and until this pass NOTHING read any
 * of it — not app.js, not the template, not occlusion.js.  Eight modules got
 * away with that because their look is `None` and their exposure 0.
 *
 * **FMM is the ninth.**  `cockpit/modules/FMM/build.py` has a `close_grade()`
 * that applies to the CLOSE camera only: the shell's seven lights dimmed to
 * 45%, exposure −0.20 stops, and the look "AgX - Punchy".  `plate.png` is
 * rendered through it and the live half was not, so every live pixel came out
 * **+9 to +26 levels brighter than the baked panel it is bolted to** — visible,
 * not merely an rms — `compare.py` read **5.645 against 4.241**, and the
 * `light_gain` sweep had **no minimum at all**, because the gain was being
 * asked to cancel a grade rather than a lighting error.
 *
 * FMM IS THE ONLY MODULE IN THE FLEET WITH A `close_grade()`.  Checked across
 * all nine `build.py` files: only FMM assigns `view_settings.look` or
 * `view_settings.exposure` for the close render.  The other eight touch
 * `view_settings` only inside their `glow_render()` helper, which sets
 * Standard/None and RESTORES both afterwards.  In particular **DNSM and LOG do
 * not have one**, so for them this file is a no-op that costs one branch — but
 * it is wired in anyway, because "eight modules read `None` and are unaffected"
 * is exactly the reasoning that let this ship unread for nine modules.
 *
 * TWO PIECES, AND THEY ARE DIFFERENT IN KIND.
 *
 * 1. **exposure** transfers EXACTLY.  Blender multiplies scene-linear by
 *    2^exposure before the view transform, which is what three's
 *    `toneMappingExposure` is.  One line, correct for all nine, no fitting.
 *
 * 2. **the look** does not transfer at all: three ships base AgX and no looks.
 *    So it is MEASURED, not guessed.  `export_fmm.py` renders its live-only
 *    frame twice, once with the look and once with `look = 'None'`, and fits
 *    the transfer between them over every opaque pixel:
 *
 *        AgX - Punchy: per-channel POWER 1.410 in sRGB DISPLAY space,
 *                      saturation 1.000, over 26,670 px
 *        -> reproduces Blender's own Punchy render to rms 2.70 levels,
 *           against 26.09 for not modelling it at all
 *
 *    It is one `pow()` between the tone map and the output encode, applied by
 *    wrapping three's AgX shader chunk before any material compiles.
 *
 * A LOOK THIS FILE DOES NOT KNOW IS A LOUD WARNING, NOT A SILENT PASS.  The
 * whole failure mode being fixed is a grade nobody noticed, so an unmeasured
 * look says so on the console and in the returned record rather than quietly
 * rendering the live half wrong.  If you hit one: render your live-only frame
 * twice out of Blender, fit the transfer, and add a row to LOOK_TRANSFER with
 * the rms you achieved.  Do not guess a number into this table.
 */
import * as THREE from 'three';

/* MEASURED transfers, keyed by Blender's own `view_settings.look` string.
 * `pow` is per-channel in sRGB display space; `sat` is a saturation multiplier
 * about Rec.709 luma, applied after it.  `rms` is the fit residual in 8-bit
 * levels against Blender's own render, and `n` the pixel count it was fitted
 * over — quote both, so the next agent can tell a measurement from a guess. */
export const LOOK_TRANSFER = {
  'AgX - Punchy': { pow: 1.410, sat: 1.000, rms: 2.70, n: 26670, by: 'FMM' },
};

let PATCHED = null;          // which look the AgX chunk currently carries

/** Wrap three's AgX chunk with a measured look.  Idempotent, and reversible
 *  only by reload — which is fine, because a page has exactly one look. */
function patchLook(name, t) {
  if (PATCHED === name) return true;
  /* FMM applied this look from its own module.js before it lived here, by the
   * same wrapping trick under the name `fmmAgXBase`.  Wrapping again would
   * apply the power TWICE.  If you migrate a module onto grade.js, delete the
   * local wrapper -- this detects the one that exists today and stops. */
  if (THREE.ShaderChunk['tonemapping_pars_fragment']
        .indexOf('fmmAgXBase') >= 0) {
    console.warn('grade.js: the AgX chunk already carries a module-private '
      + 'look wrapper (fmmAgXBase).  NOT applying "' + name + '" on top of it '
      + '-- that would apply the transfer twice.  Remove the local wrapper.');
    return false;
  }
  if (PATCHED && PATCHED !== name) {
    console.warn('grade.js: the AgX chunk already carries the look "' + PATCHED
      + '"; refusing to stack "' + name + '" on top of it.');
    return false;
  }
  const K = 'tonemapping_pars_fragment';
  const src = THREE.ShaderChunk[K];
  const sig = 'vec3 AgXToneMapping( vec3 color ) {';
  if (!src || src.indexOf(sig) < 0) {
    console.warn('grade.js: three\'s AgX chunk does not look the way this '
      + 'expects, so the look "' + name + '" is NOT applied.  The live half '
      + 'will render against a plate.png that was graded and it was not.');
    return false;
  }
  const P = t.pow.toFixed(6), S = t.sat.toFixed(6);
  THREE.ShaderChunk[K] = src.replace(sig, 'vec3 grade_AgXBase( vec3 color ) {')
    + `
vec3 grade_enc( vec3 c ) { return mix( c * 12.92,
  1.055 * pow( max( c, vec3( 0.0 ) ), vec3( 1.0 / 2.4 ) ) - 0.055,
  step( vec3( 0.0031308 ), c ) ); }
vec3 grade_dec( vec3 c ) { return mix( c / 12.92,
  pow( ( max( c, vec3( 0.0 ) ) + 0.055 ) / 1.055, vec3( 2.4 ) ),
  step( vec3( 0.04045 ), c ) ); }
vec3 AgXToneMapping( vec3 color ) {
  vec3 lin = clamp( grade_AgXBase( color ), 0.0, 1.0 );
  vec3 d = pow( grade_enc( lin ), vec3( ${P} ) );
  float l = dot( d, vec3( 0.2126, 0.7152, 0.0722 ) );
  d = mix( vec3( l ), d, ${S} );
  return grade_dec( clamp( d, 0.0, 1.0 ) );
}`;
  PATCHED = name;
  return true;
}

/**
 * @param {object} S        the parsed scene.json
 * @param {THREE.WebGLRenderer} renderer   the BACK renderer
 * @param {OcclusionSplit} [split]         so both halves get the same exposure
 * @returns {{exposure:number, stops:number, look:string, applied:boolean,
 *            note:string}}
 */
export function applyColour(S, renderer, split) {
  const C = (S && S.colour) || {};
  const stops = (typeof C.exposure === 'number') ? C.exposure : 0;
  const exposure = Math.pow(2, stops);
  renderer.toneMappingExposure = exposure;
  /* occlusion.js re-syncs this every renderFrame() as well; setting it here
   * too means a page that grabs the front canvas before its first frame is
   * still consistent. */
  if (split && split.renderer) split.renderer.toneMappingExposure = exposure;

  const look = C.look || 'None';
  let applied = false, note = '';
  if (look && look !== 'None') {
    const t = LOOK_TRANSFER[look];
    if (t) {
      applied = patchLook(look, t);
      note = applied
        ? ('look "' + look + '" applied as pow ' + t.pow + ' / sat ' + t.sat
           + ' (measured by ' + t.by + ', rms ' + t.rms + ' levels over '
           + t.n + ' px)')
        : ('look "' + look + '" NOT applied -- see the console');
    } else {
      note = 'UNMEASURED LOOK';
      console.warn('grade.js: scene.json declares the Blender look "' + look
        + '" and no measured transfer for it exists.  plate.png was rendered '
        + 'THROUGH that look and the live half is not, so the live geometry '
        + 'will sit visibly brighter or darker than the panel it is bolted '
        + 'to (FMM measured +9..+26 levels for "AgX - Punchy" unmodelled, and '
        + 'its light_gain sweep had no minimum at all).  Render your live-only '
        + 'frame twice out of Blender -- once with the look, once with '
        + "look='None' -- fit the transfer, and add it to LOOK_TRANSFER.");
    }
  } else {
    note = 'no look (view transform ' + (C.view_transform || 'AgX') + ')';
  }
  if (stops !== 0)
    console.info('grade.js: exposure ' + stops + ' stops -> '
      + 'toneMappingExposure ' + exposure.toFixed(6) + ' on BOTH renderers');
  return { exposure, stops, look, applied, note };
}
