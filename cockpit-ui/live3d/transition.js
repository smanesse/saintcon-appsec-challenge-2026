/* SAINTCON 2026 — the wide-shot -> close-up move.
 *
 * WHAT WAS WRONG
 * --------------
 * The old move was `body.closeup #wide{transform:scale(2.5)}` cross-fading to
 * `#close` at scale 1.  Two separate defects, and the second is the one that
 * actually made it read cheap:
 *
 *   1. RESOLUTION.  The wide plate is 1280x720.  Filling the frame from a
 *      module hotspot is a 3.3x-5.8x upscale, so the end of every zoom is
 *      mush.  No easing curve fixes an upscale.
 *   2. GEOMETRY.  scale(2.5) is not where the close-up is.  KVS's close-up
 *      sits at 5.62x, so the cross-fade joined two pictures showing the module
 *      at less than half each other's size.  That is a DISSOLVE BETWEEN TWO
 *      SHOTS, not a move, and the eye reads it as a cut with a smear on it.
 *
 * WHAT THIS DOES INSTEAD
 * ----------------------
 * One virtual camera, both plates hung off it.  A single magnification z runs
 * 1 -> M (measured per module, live3d/transition.json).  The wide plate is
 * scaled by z; the close plate is scaled by z/M -- so at every instant BOTH
 * layers show the module at the same size in the same place, and the cross-fade
 * between them is a match dissolve inside one continuous move.
 *
 * The close plate therefore enters at 1/M and is only ever DOWNSCALED, never
 * up.  It reaches scale 1 exactly at the end, where it is the shipped plate,
 * pixel for pixel.  The blurry end of the old zoom simply does not exist any
 * more: the sharp picture takes over while the wide plate is still around 2x.
 *
 *   z = M^e         geometric, so the zoom RATE is constant to the eye
 *   pan = (1-1/z)/(1-1/M)    a straight-line camera translation, not a lerp;
 *                            it recentres early, while the move is still cheap,
 *                            and the rest is a pure dive
 *
 * Below scale 1 the close plate does not cover the frame, so the wide plate
 * fills the margin underneath it -- the same scene, softer.  Three things keep
 * that from reading as a rectangle pasted on the screen:
 *   - the close layer's edge is feathered while it is small, and unmasked by
 *     the time it lands (a mask on the resting close-up would be a defect);
 *   - the wide layer takes a real defocus AND is dimmed in step with the close
 *     plate's own opacity, landing on `dimEnd` and STAYING as the close-up's
 *     backdrop -- which is what the shipped plates expect, since they are
 *     rendered film-transparent (OTA's is 35% opaque) and cockpit/
 *     make_cockpit.py composites them over `blur(2px) brightness(.35)` of the
 *     wide shot.  Keeping it also means a hole in the middle of the plate and
 *     the margin outside it show the same thing, so the edge stops being one;
 *   - a screen-space lens vignette closes over the periphery mid-move and
 *     opens again on arrival.
 *
 * NOT every module's close camera looks the same way the pilot does.  KVS,
 * MTA, OTA and PKT dolly along the wide camera's own view ray (fit_camera);
 * DNSM, FMM, IPM and MQB aim straight down their panel's face normal instead.
 * For those four the two views differ in DIRECTION, no 2D scale is exact, and
 * the cross-fade carries a genuine perspective change.  That is a feature as
 * much as a limit -- a real move through space does change perspective -- but
 * it is why FMM and MTA have no correlation optimum at all (see
 * pipeline/measure_transition.py and check/match_handover.mjs).
 *
 * Nothing here is KVS-specific.  It runs off nothing but M and a centre.
 */

/* All tunables in one place; check/shoot_transition.mjs pokes them. */
export const CFG = {
  durIn: 820,          // ms, cockpit -> close-up
  durOut: 620,         // ms, back out (a retreat wants to be quicker)
  fadeA: 0.44,         // close plate opacity ramp, in EASED time
  fadeB: 0.90,
  blurMax: 2.80,       // px in the wide layer's own space; x z on screen
  blurA: 0.40,
  dimEnd: 0.30,        // wide-layer brightness once the close-up has landed
  featherPct: 6.0,     // close layer edge feather, % of the plate
  featherA: 0.55,      // ... ramping to zero between these
  featherB: 1.00,
  dimPow: 0.60,        // wide-layer dim vs close-plate opacity; see below
  vigMax: 0.85,        // lens vignette, screen space
  vigA: 0.14, vigB: 0.58,
  vigC: 0.86, vigD: 1.00,
};

const clamp01 = v => v < 0 ? 0 : v > 1 ? 1 : v;
const ss = v => { v = clamp01(v); return v * v * (3 - 2 * v); };
const band = (v, a, b) => ss((v - a) / (b - a));

export function createDolly({ wide, close, vig, W, H, onFrame }) {
  let M = 1, fx = W / 2, fy = H / 2;
  let u = 0, from = 0, to = 0, t0 = 0, dur = 0, running = false, done = null;

  /* u is raw progress 0..1; e is the eased progress everything else reads. */
  function apply(uu) {
    u = clamp01(uu);
    const e = ss(u);
    const z = Math.pow(M, e);
    const s = z / M;
    const p = M <= 1.0001 ? 1 : (1 - 1 / z) / (1 - 1 / M);
    /* The anchor is where the module's centre sits on screen: it starts where
     * the module already is and recentres as the camera closes in.  CLAMPED so
     * the wide plate always covers the frame: a module near an edge (MQB and
     * DNSM are at the top, FMM/LOG/MTA at the bottom) would otherwise be
     * dragged toward the middle faster than the plate grows, and the far edge
     * of the plate would lift off, leaving a black band across the top of the
     * cockpit halfway through the move.  At z=1 the interval collapses to a
     * point, i.e. no pan at all before there is any zoom to pay for it, which
     * is also exactly right; at z=M it is wide enough for the true centre in
     * every one of the nine, so the landing is untouched. */
    const cl = (v, f, span) =>
      Math.max(span - z * (span - f), Math.min(z * f, v));
    const ax = cl(fx + (W / 2 - fx) * p, fx, W);
    const ay = cl(fy + (H / 2 - fy) * p, fy, H);

    wide.style.transform =
      `translate(${(ax - z * fx).toFixed(3)}px,${(ay - z * fy).toFixed(3)}px)` +
      ` scale(${z.toFixed(5)})`;
    close.style.transform =
      `translate(${(ax - s * W / 2).toFixed(3)}px,${(ay - s * H / 2).toFixed(3)}px)` +
      ` scale(${s.toFixed(5)})`;

    const op = band(e, CFG.fadeA, CFG.fadeB);
    close.style.opacity = op.toFixed(4);

    /* THE MARGIN, and it is the artefact that had to be designed out.
     * Until the close plate reaches scale 1 it does not cover the frame, and
     * what shows around it is the wide plate at 3-4x carrying a DIFFERENT
     * exposure grade (every module's close-up has its own light rig).  A
     * sharp plate sitting on a brighter mismatched surround reads as a
     * rectangle pasted on the screen -- exactly the "overlay" look this move
     * is meant to beat.
     *
     * So the wide layer is dimmed as a function of the close plate's OWN
     * opacity.  That is exact by construction rather than by tuning: the
     * surround darkens in lockstep with the plate going solid, so a bright
     * mismatched margin can never sit beside a solid plate, and no matte
     * geometry has to be kept in sync with anything.  The exponent is below 1
     * so the mid-fade dip stays shallow.
     *
     * It lands on `dimEnd`, NOT on black, and the wide layer stays on screen
     * afterwards.  That is not decoration: the shipped close-up plates are
     * rendered film-transparent and are MEANT to composite over a darkened
     * wide shot -- cockpit/make_cockpit.py does exactly this with
     * `body.closeup #viewport{filter:blur(2px) brightness(.35)}`.  OTA's plate
     * is only 35% opaque; taken to black it opens holes straight through to
     * the page background.  Keeping the backdrop also removes the last of the
     * seam for free: a hole in the middle of the plate and the margin outside
     * it now show the SAME thing, so there is nothing for the edge to be an
     * edge between.  And the backdrop is left at magnification M, which is the
     * magnification that relates the two views in the first place, so what
     * shows through the holes is roughly the right continuation rather than a
     * jump back to the wide framing.
     *
     * Plus a real defocus: the wide plate is being magnified past its own
     * resolution, and an out-of-focus background is a thing a camera does,
     * where an upscaled one is a thing a bitmap does.  It starts only once the
     * close plate is arriving (blurA sits under fadeA) -- before that the wide
     * plate is the ONLY picture on screen and has to stay crisp. */
    const b = CFG.blurMax * band(e, CFG.blurA, 1);
    const d = CFG.dimEnd + (1 - CFG.dimEnd) * Math.pow(1 - op, CFG.dimPow);
    wide.style.filter = (b > 0.02 || d < 0.999)
      ? `blur(${b.toFixed(3)}px) brightness(${d.toFixed(4)})` : 'none';

    const f = CFG.featherPct * (1 - band(e, CFG.featherA, CFG.featherB));
    close.style.setProperty('--fx', f.toFixed(3) + '%');
    close.style.setProperty('--fy', (f * W / H).toFixed(3) + '%');

    if (vig) {
      vig.style.opacity = (CFG.vigMax * band(e, CFG.vigA, CFG.vigB)
                           * (1 - band(e, CFG.vigC, CFG.vigD))).toFixed(4);
    }
    if (onFrame) onFrame(u, e);
  }

  return {
    /* M and the centre of the wide-frame rectangle the close plate covers */
    setModule(m, cx, cy) { M = m > 1 ? m : 1; fx = cx; fy = cy; },
    get M() { return M; },
    at() { return u; },
    running() { return running; },
    apply,                                   // deterministic seek, for capture
    play(target, cb) {
      from = u; to = clamp01(target); done = cb || null;
      const span = Math.abs(to - from);
      dur = (to > from ? CFG.durIn : CFG.durOut) * (span < 1 ? Math.max(0.25, span) : 1);
      t0 = performance.now(); running = true;
      if (dur < 1) { apply(to); running = false; if (done) done(to); }
    },
    tick(now) {
      if (!running) return;
      const k = clamp01((now - t0) / dur);
      apply(from + (to - from) * k);
      if (k >= 1) { running = false; if (done) done(to); }
    },
  };
}
