/* SAINTCON 2026 — THE TELLTALE MAST, CLOSE-UP HALF.  ONE FRONTEND, NINE MODULES.
 *
 * `live3d/design/STATUS_AT_A_GLANCE.md` section 6 is the design.
 * `live3d/pipeline/status_mast.py` is the builder; this is the consumer.
 * `live3d/refit.js` is the file this is shaped like, deliberately: the fan-out
 * that follows will be reading both, and a module wires this in nine lines.
 *
 * WHAT THIS FILE IS NOT
 * ---------------------
 * It is NOT a second derivation.  Section 6.4 asks for exactly one place where
 * facts become marks, and that place is `status.js`: `derive()` for the state,
 * `INK` for every colour, `statusLine()` for the words, `moduleStatus()` for
 * the source.  This file imports all four and adds none of them.  If the wide
 * shot and the close-up ever disagree it is a bug in one consumer, not a
 * difference of opinion — and there is nothing here for them to disagree
 * about, because there is no `if` in this file that `app.js` does not also
 * take from the same object.
 *
 * NO DECLARED READOUT PLANE.  All of the mast's words are the screen-space
 * caption in `mast.css`, the same class of thing as KVS's two `.hud` panels
 * and the refit port's docket.  Section 6.2 rule 5 asked for one new
 * `text_planes` entry per module and the build did not take it: see the
 * builder's docstring and STATUS_AT_A_GLANCE section 6's build note.  The
 * consequence is that `check_occlusion.py` question 5, the dial-face rule and
 * `check_text.py` are NOT ENGAGED by this component.  Do not add a plane here
 * to save a line of layout.
 *
 * NO innerHTML.  Every node is `document.createElement` and every string
 * reaches the page through `textContent`.  CONVERSION_BRIEF section 7.
 *
 * NO TIMERS.  The sweep, the vane and the cap breath all animate off
 * `mast.tick(dt, now)`, which the module's own `onFrame()` calls.  There is
 * nothing for `pose()` to `clearInterval`, which is the failure README 16.8
 * records for a 520 ms cursor blink.  `pose()` HIDES the mast, exactly as
 * `refit.js`'s does and for exactly the same reason (FIX_UPLOAD section 0
 * decision 3): every recorded number then reproduces byte-identically and the
 * component gets its own capture instead, re-shot with it forced visible.
 *
 * NO NETWORK beyond `status.js`'s same-origin fetch of `status.json` and,
 * as a peer, `GET /api/live`.  Both are allowed to fail: `moduleStatus()`
 * resolves to the UNTESTED pose with `live: null` rather than throwing.
 * A fresh clone has no harness and no coordinator, and the module page must
 * come up looking like an instrument anyway — which is also the state a
 * checker opening the page standalone must find (section 6.2 rule 7).
 * The detail may show a read-only power word after it is opened. This file
 * does not post power, and PKT has no power row.
 */
import { derive, statusLine, moduleStatus, tallyLit, solvedIds, COULDNT_FINISH, INK }
  from './status.js';
/* The hotspot adapter, the fittings' own trap-21 audit and the one-name
 * fitting registry all live in `refit.js` because that is the file every
 * module already loads first; importing it here costs one fetch and keeps
 * ONE copy of each.  `refit.js` has no top-level side effects. */
import { wireHotspot, facingAudit, registerFitting, watchTick } from './refit.js';

const D2R = Math.PI / 180;

/* How often to re-read `status.json`.  Section 9.1 says 5 s.  A module page
 * opened standalone by a checker polls too, and that is fine: the file does
 * not change under it, `derive()` of the same record is the same object, and
 * `apply()` is a no-op when the signature has not moved. */
export const POLL_MS = 5000;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

/* `#RRGGBB` -> a 0..1 triple, IN sRGB, which is what it is.
 *
 * AND IT IS SET WITH `THREE.SRGBColorSpace`, NOT `LinearSRGBColorSpace`.
 * The modules' own `dress()` uses LinearSRGBColorSpace and is right to: the
 * numbers in `materials.json` are Blender's own LINEAR base colours.  The
 * numbers in `status.js -> INK` are DISPLAY HEXES -- `#0F1216` is what the
 * bezel must look like on screen -- and feeding a display hex in as if it were
 * linear renders it about a gamma too bright.  Measured on the first build:
 * `#0F1216` (15, 18, 22) came out as rgb(119, 119, 117) mid-grey, `#D9342B`
 * came out as rgb(228, 191, 180) pale pink, and the whole fitting read as a
 * washed-out grey box.  Section 4.4's rule -- the bezel is OPAQUE HARDWARE and
 * every coloured pixel sits inside it -- is not satisfiable by a bezel that
 * renders at luma 0.47. */
function hex3(h) {
  const v = parseInt(h.slice(1), 16);
  return [(v >> 16 & 255) / 255, (v >> 8 & 255) / 255, (v & 255) / 255];
}

/* `statusLine()` is ONE string and the wide shot's tooltip uses it verbatim;
 * the close-up caption sits beside a fitting on the bottom sill and cannot be
 * 55 characters wide there without covering the instrument.  So it is wrapped
 * on the design's own separator rather than shortened: exactly the same words,
 * in the same order, on as many lines as they need.  A second, shorter string
 * would be a second source of truth (section 6.4). */
function wrap(line, cols) {
  const out = [];
  let cur = '';
  const push = () => { if (cur) out.push(cur); cur = ''; };
  for (const bit of String(line || '').split(' · ')) {
    if (cur && (cur + ' · ' + bit).length <= cols) { cur += ' · ' + bit; continue; }
    push();
    /* a single clause can still be wider than the column -- `Check couldn't
     * finish — no result yet` is 37 -- so fall back to words.  The caption's
     * width is not a style choice: the deck between the fitting and the
     * module's own right-hand .hud panel is 260 px on KVS, which is 34
     * characters of Courier Prime at 11.5 px. */
    for (const word of bit.split(' ')) {
      if (!cur) cur = word;
      else if ((cur + ' ' + word).length <= cols) cur += ' ' + word;
      else { out.push(cur); cur = '  ' + word; }
    }
  }
  push();
  return out.join('\n');
}

/* Solved numbers listed in the hover summary before "+N more". */
const SOLVED_HOVER = 6;

/* Word for a PoC's result.  These are the design's own strings and the design
 * NEVER uses pass/fail for a PoC: `landing` / `fixed` / `inconclusive` /
 * `untested` (section 1).  A PoC printing `[+]` is BAD for the player, and
 * `vuln-console/README.md` calling that "a PASS" is the exact confusion these
 * words exist to stop. */
const RESULT_WORD = {
  landing: 'STILL LANDS',
  fixed: 'CLOSED',
  inconclusive: 'UNKNOWN',
  untested: 'NOT RUN',
};

/**
 * The only opener for the caption and the detail.
 *
 * A fitting that arrives under a stationary pointer fires enter and must
 * stay quiet. `pointerenter` / `mouseenter` only raise the arrival arm.
 * A later `pointermove` on the hotspot is the hover that reveals. Click
 * toggles the latch. Enter and Space latch open and do not toggle shut.
 * Leave hides only when the latch is off. Escape clears the latch, the
 * hover, and the arrival arm. `poll()` is what `apply()` calls on a status
 * read and it never reveals. `reset()` is `show(true)` and `show(false)`:
 * latch, hover, and the arrival arm all drop so a module return starts quiet.
 */
export function createDetailGate() {
  let latched = false;
  let hover = false;
  let arrival = false;
  let cap = null;
  let det = null;
  let onChange = null;
  let prevLatched = false;
  let prevOpen = false;
  let docFn = null;

  function isOpen() { return !!(latched || hover); }

  function state() {
    return { latched: !!latched, hover: !!hover, arrival: !!arrival, open: isOpen() };
  }

  function sync() {
    const on = isOpen();
    const latchChanged = latched !== prevLatched;
    const openChanged = on !== prevOpen;
    prevLatched = latched;
    prevOpen = on;
    if (cap) cap.hidden = !on;
    if (det) det.hidden = !on;
    if ((latchChanged || openChanged) && typeof onChange === 'function')
      onChange(state());
  }

  function onEnter() { arrival = true; }

  function onMove() {
    arrival = false;
    hover = true;
    sync();
  }

  function onLeave() {
    hover = false;
    arrival = false;
    sync();
  }

  function onClick() {
    latched = !latched;
    sync();
  }

  function onKey(ev) {
    const k = ev && ev.key;
    if (k === 'Enter' || k === ' ') {
      if (ev.preventDefault) ev.preventDefault();
      latched = true;
      sync();
      return;
    }
    if (k === 'Escape') {
      latched = false;
      hover = false;
      arrival = false;
      sync();
    }
  }

  function listen(el, type, fn) {
    if (el && typeof el.addEventListener === 'function') el.addEventListener(type, fn);
  }

  return {
    state,
    /* apply() / the 5 s poll. Never opens, never closes. */
    poll() {},
    reset() {
      latched = false;
      hover = false;
      arrival = false;
      sync();
    },
    dispose() {
      if (docFn && typeof document !== 'undefined' && document.removeEventListener)
        document.removeEventListener('keydown', docFn);
      docFn = null;
    },
    set onChange(fn) { onChange = typeof fn === 'function' ? fn : null; },
    get onChange() { return onChange; },
    bind(hot, capEl, detEl) {
      cap = capEl || null;
      det = detEl || null;
      if (cap) cap.hidden = true;
      if (det) det.hidden = true;
      prevLatched = false;
      prevOpen = false;
      if (hot) {
        try { hot.tabIndex = 0; } catch (e) { /* tiny target */ }
      }
      listen(hot, 'pointerenter', onEnter);
      listen(hot, 'mouseenter', onEnter);
      listen(hot, 'pointermove', onMove);
      listen(hot, 'pointerleave', onLeave);
      listen(hot, 'mouseleave', onLeave);
      listen(hot, 'click', onClick);
      listen(hot, 'keydown', onKey);
      if (typeof document !== 'undefined' && document.addEventListener
          && document !== hot) {
        docFn = ev => { if (ev && ev.key === 'Escape') onKey(ev); };
        document.addEventListener('keydown', docFn);
      }
    },
  };
}

export function bindStatusDetails(hot, cap, det) {
  const gate = createDetailGate();
  gate.bind(hot, cap, det);
  return gate;
}

/**
 * Mount the telltale mast on a module page.
 *
 *   mast = await mountMast({ THREE, scene, camera, split, S, code, assetBase,
 *                            load, dress, hotspot, layerHost, stageEl });
 *
 * then `mast.tick(dt, now)` in the frame loop, `mast.pose()` first thing in
 * the capture pose, and `mast.show(true)` after the load-time pose.
 *
 * Everything module-specific — the anchor, the size, the part names, the vane
 * pivot, the sweep travel and the hotspot — comes out of `scene.json -> mast`,
 * which `pipeline/status_mast.py` wrote.  There is not one module code in the
 * body of this function.
 */
export async function mountMast(o) {
  const THREE = o.THREE;
  const R = (o.S || {}).mast;
  if (!R) throw new Error('mountMast: scene.json has no "mast" block -- run '
    + 'pipeline/status_mast.py for this module first');
  const CODE = o.code || R.code;
  const W = (o.S.render && o.S.render.w) || 1280;
  const H = (o.S.render && o.S.render.h) || 720;
  const PK = R.parts || {};
  const M = R.m || 0;

  /* ================================================================ GEOMETRY */
  const gltf = await o.load(o.assetBase + R.glb);
  const root = new THREE.Group();
  root.name = CODE + '_mast';
  o.scene.add(root);

  const byName = {};
  const meshes = [];
  gltf.scene.traverse(m => { if (m.isMesh) meshes.push(m); });
  for (const m of meshes) byName[m.name] = m;

  /* Every glb in this project is exported in WORLD coordinates, so a moving
   * part is "a pivot at the hinge, with the child translated back by it".
   * Same construction as the module's own `pivotAt()` and `refit.js`'s. */
  function pivotAt(p) {
    const piv = new THREE.Object3D();
    const inner = new THREE.Object3D();
    piv.position.set(p[0], p[1], p[2]);
    inner.position.set(-p[0], -p[1], -p[2]);
    piv.add(inner);
    root.add(piv);
    return { piv, inner };
  }

  /* THE VANE.  It rotates about the mast face's NORMAL, not about the mast
   * axis: about the axis a furled vane goes edge-on and vanishes, and about
   * the normal it swings from standing out (+B, flying) to lying alongside the
   * head (+A, furled), which is the wide shot's own read.  The builder solved
   * the pivot and published it; nothing here re-derives it. */
  const vaneRec = R.vane || null;
  const vane = vaneRec && byName[vaneRec.node] ? pivotAt(vaneRec.pivot) : null;
  const vaneAxis = vaneRec
    ? new THREE.Vector3().fromArray(vaneRec.axis).normalize() : null;
  if (vane) vane.inner.add(byName[vaneRec.node]);

  /* THE SWEEP.  One band translated along +A while a run is in flight.  It is
   * a translation, not a shader, so it costs nothing and `pose()` parks it at
   * the collar end by setting the offset to 0. */
  const sweepRec = R.sweep || null;
  const sweepMesh = sweepRec && sweepRec.node ? byName[sweepRec.node] : null;
  const axisA = new THREE.Vector3().fromArray(R.axis_a || [1, 0, 0]).normalize();
  const sweepHome = sweepMesh ? sweepMesh.position.clone() : null;

  /* everything still unparented is static; it goes straight on the root */
  for (const m of meshes) if (!m.parent || m.parent === gltf.scene) root.add(m);

  /* ---- materials.  ORDER MATTERS and the module's own dress() is what
   * enforces it: it ASSIGNS the depth composite's onBeforeCompile and then
   * CHAINS attachForeground onto it.  Skipping dress() is the double-blend in
   * trap 15 and `auditScene()` names every mesh that missed it.
   *
   * TRAP 21.  dress() forces THREE.FrontSide and one-sided Blender geometry
   * does not survive it: no error, no auditScene() complaint, the prop is
   * simply not there.  OTA lost 14 single-triangle chevrons that way.  The
   * VANE is exactly the shape the trap names -- "swept ribbons, FLAGS, tape,
   * curtains, single-quad labels" -- and so are the hazard chevrons, the hatch
   * bars and the scrim bars.  `status_mast.py` builds every one of them as a
   * CLOSED PRISM, so there is nothing here to set DoubleSide on and nothing
   * for FrontSide to delete.  Run facingAudit(camera) and expect []. */
  const mats = {};
  let TRIS = 0;
  root.traverse(m => {
    if (!m.isMesh) return;
    mats[m.name] = o.dress(m);
    const g = m.geometry;
    if (g) TRIS += (g.index ? g.index.count : g.attributes.position.count) / 3;
  });

  /* THE ONE PLACE COLOUR ENTERS THE GEOMETRY, and it is `status.js -> INK`.
   *
   * The builder authors placeholder base colours so the glb looks sane in a
   * viewer; every colour that MEANS something is set here, from the one table
   * the wide shot also draws from (section 9.3).  A hex baked into an asset is
   * a second source of truth that a later edit can desynchronise, and the two
   * halves of this indicator agreeing is the whole of section 6.4.
   *
   * The emissive COLOUR is set here for a second reason, measured on the refit
   * port (FIX_UPLOAD 12.8): a Blender material with Emission Strength 0
   * round-trips through glTF as emissive BLACK, and driving emissiveIntensity
   * on black multiplies zero -- the part stays dark at every intensity and it
   * looks like the state machine is not firing. */
  function paint(name, hex, opts) {
    const mm = mats[name];
    if (!mm) return null;
    const c = hex3(hex);
    mm.color.setRGB(c[0], c[1], c[2], THREE.SRGBColorSpace);
    const e = (opts && opts.emit) || null;
    const ec = e ? hex3(e) : c;
    mm.emissive.setRGB(ec[0], ec[1], ec[2], THREE.SRGBColorSpace);
    mm.emissiveIntensity = (opts && opts.intensity) || 0;
    return mm;
  }
  const vis = (name, on) => { const m = byName[name]; if (m) m.visible = !!on; };
  const visAll = (names, on) => (names || []).forEach(n => vis(n, on));

  /* the fixed hardware.  Brass is brass whatever the service is doing; NO
   * STATUS COLOUR TOUCHES THE PLATE and none of it touches the hardware
   * either (section 4.4). */
  paint(PK.collar, INK.collar);
  paint(PK.rod, INK.rod);
  paint(PK.knob, INK.rod);
  paint(PK.foot, INK.flange);
  paint(PK.service_rail, INK.flange);
  paint(PK.lampbar, INK.flange);
  paint(PK.bore, INK.glass);
  (PK.bezel || []).forEach(n => paint(n, INK.bezel));
  (PK.grads || []).forEach(n => paint(n, INK.grad));
  (PK.hazard || []).forEach(n => paint(n, INK.hazard, { intensity: 0.18 }));
  (PK.hatch || []).forEach(n => paint(n, INK.hatch));
  (PK.scrim || []).forEach(n => paint(n, INK.grad));
  (PK.cap_stripes || []).forEach(n => paint(n, INK.hazard, { intensity: 0.18 }));
  (PK.cap_cross || []).forEach(n => paint(n, INK.hatch));
  paint(PK.cap_ring, INK.grad);
  if (PK.tally) paint(PK.tally, INK.tally);
  if (sweepMesh) paint(sweepRec.node, INK.sweepCore, { intensity: 0.9 });

  /* ================================================================ THE LAYER */
  const layer = el('div');
  layer.id = 'mast';
  (o.layerHost || document.body).appendChild(layer);
  const stageEl = o.stageEl || o.layerHost;

  const cap = el('div', 'cap');
  cap.hidden = true;
  const capHd = el('div', 'hd');
  const capSub = el('div', 'sub');
  const capWarn = el('div', 'warn');
  cap.appendChild(capHd);
  cap.appendChild(capSub);
  cap.appendChild(capWarn);
  layer.appendChild(cap);

  const det = el('div', 'det');
  det.hidden = true;
  const detT = el('div', 't', 'EXPLOIT CATALOGUE');
  det.appendChild(detT);
  /* the solved list lives in its own box so it can be bounded: a short summary
   * on hover, the full list in a scroll box once the panel is pinned (mast.css
   * `.det.pinned .list`) */
  const detRows = el('div', 'list');
  det.appendChild(detRows);
  const pwr = el('div', 'pwr');
  pwr.hidden = true;
  const pwrState = el('div', 'pwr-state');
  pwr.appendChild(pwrState);
  det.appendChild(pwr);
  const detFoot = el('div', 'foot');
  det.appendChild(detFoot);
  layer.appendChild(det);

  /* ================================================================== STATE */
  const S = {
    d: derive(null, { code: CODE }),   // the UNTESTED pose, always the start
    t: 0, sweepT: 0, vaneDeg: 0, vaneWant: 0, sig: '',
    /* capture only, never set by a page -- see settle() */
    frozen: false,
    /* not animation state: the only thing `watchTick()` in refit.js reads */
    ticks: 0,
  };
  /* Caption and detail reveal only through this gate. */
  let gate = null;

  /* ---------------------------------------------------------------- THE MAP
   * Facts (already derived) -> marks.  Nothing is computed here that
   * `derive()` did not already decide; this function only chooses which solid
   * is visible and what colour it is. */
  function apply(d) {
    S.d = d;
    const off = R.variant === 'offensive';

    if (off) {
      applyOffensive(d);
    } else {
      applyDefensive(d);
    }

    /* STALE -- section 7, scoped as section 14.4 scoped it: bezel and cap, not
     * the whole envelope.  Built envelope-wide in the wide shot first and it
     * painted diagonals over bare plate and read as somebody having hatched
     * the dash.  Every scrim bar here is on opaque hardware, which is the same
     * rule section 4.4 imposes on colour. */
    visAll(PK.scrim, d.stale);
    paintCaption(d);
    publishDirty(d);
    /* A status read never reveals. paintCaption fills text only. */
    if (gate) gate.poll();
  }

  /* ------------------------------------------------------------ DIRTY, OUT
   * SECTION 11.3's SEAM WAS WIRED NOWHERE IN THE FLEET, KVS INCLUDED.
   * `refit.js` looks for `window.__status.dirty(CODE)`, for a `status:dirty`
   * event, or for `refit.setDirty(v)` -- and nothing set any of the three, on
   * any module.  So the port held `dirtyKnown = false` and the docket said
   * `not read — REHEARSAL has no workbench`, which is the RIGHT failure for an
   * unmeasured fact, but on MTA it was said two hundred pixels away from a
   * mast that had already derived `dirty: true` from a `source_rev` that does
   * not match `current_source_rev` and was flying STALE scrim bars for it.
   * Two fittings on one panel disagreeing about one boolean.
   *
   * `derive()` returns `dirty` next to `stale` and from the same two hashes,
   * on purpose: "they are driven from one place so they can never disagree"
   * (status.js section 7).  This is the one line that connects the place they
   * are driven from to the place they are read.  It belongs here and not in
   * nine module pages -- MTA NOTES section 10 item 8.
   *
   * IT DOES NOT INVENT A VALUE.  `dirty(code)` THROWS for a code no mast has
   * derived, which is exactly what `refit.js`'s `refreshDirty()` catches to
   * stay UNKNOWN.  Unmeasured must not become `false`. */
  function publishDirty(d) {
    if (typeof window === 'undefined' || !d) return;
    let reg = window.__status;
    if (!reg || !reg.__masts) {
      /* never clobber a real cockpit's own `__status` provider */
      if (reg && typeof reg.dirty === 'function') return;
      reg = window.__status = {
        __masts: Object.create(null),
        dirty(code) {
          const v = this.__masts[code];
          if (typeof v !== 'boolean')
            throw new Error('__status.dirty: no mast has derived ' + code);
          return v;
        },
      };
    }
    const was = reg.__masts[CODE];
    reg.__masts[CODE] = !!d.dirty;
    if (was === !!d.dirty) return;
    /* push as well as publish: a docket that is ALREADY OPEN reads its
     * workbench line once, at open(), and would otherwise hold a stale one. */
    if (typeof dispatchEvent === 'function')
      dispatchEvent(new CustomEvent('status:dirty',
        { detail: { code: CODE, dirty: !!d.dirty } }));
  }

  function applyDefensive(d) {
    const segs = PK.segments || [];
    const untested = d.sec === 'untested';

    /* THE TUBE -- section 2.3.  Segments are SORTED, not in PoC order:
     * landing first, then inconclusive, then untested, then fixed, so the red
     * length reads directly as "how much work is left".  `derive()` already
     * sorted them; per-PoC identity in catalogue order is the LAMP ROW's job
     * (section 2.3's closing line, and 6.1). */
    for (let i = 0; i < segs.length; i++) {
      const it = d.segments[i] || null;
      const res = untested ? 'untested' : (it ? it.result : 'untested');
      vis(segs[i], true);
      if (res === 'landing') {
        /* the hot core of section 2.3 becomes emission on the fill itself:
         * a 2 px core is not buildable at this size, and an emissive segment
         * in a dark well is the same read and survives being small. */
        paint(segs[i], INK.landing, { emit: INK.landingCore, intensity: 0.12 });
      } else if (res === 'inconclusive') {
        paint(segs[i], INK.glass);
      } else if (res === 'fixed') {
        paint(segs[i], INK.glass);
      } else {
        paint(segs[i], INK.smoke);
      }
      /* 45-degree hatch over dark glass, section 2.3.  One diagonal bar per
       * cell rather than a hatch pattern: a pattern at one cell's width is
       * mush, and the bar is the same read. */
      vis((PK.hatch || [])[i], res === 'inconclusive');
    }

    /* "NO SCALE ON THE INSTRUMENT" is the untested tell, and it is a second
     * mark on top of the cap bead -- deliberately, because empty tube + green
     * cap and empty tube + grey ring cap would otherwise differ only by the
     * colour of one small disc, which is the weakest discrimination in the
     * design (section 2.3). */
    visAll(PK.grads, !untested);

    /* THE PILOT LAMPS, in CATALOGUE order.  `d.items` is catalogue order;
     * `d.segments` is the sorted copy.  Using the wrong one here is the single
     * most likely mistake in this file, so they are named apart. */
    const lamps = PK.lamps || [];
    for (let i = 0; i < lamps.length; i++) {
      const it = d.items[i] || null;
      const res = untested ? 'untested' : (it ? it.result : 'untested');
      if (res === 'landing') paint(lamps[i], INK.landing,
                                   { emit: INK.landingCore, intensity: 0.55 });
      else if (res === 'inconclusive') paint(lamps[i], INK.hatch,
                                             { intensity: 0.12 });
      else if (res === 'fixed') paint(lamps[i], INK.green,
                                      { emit: INK.greenCore, intensity: 0.35 });
      else paint(lamps[i], INK.smoke);
    }

    /* THE BEZEL -- section 2.4's loud mark.  "You broke the service" is the
     * highest-priority state and it must out-shout a full red tube. */
    visAll(PK.hazard, d.fn === 'fail');

    /* THE VANE -- section 2.4.  flying / furled / ABSENT, and absent is a
     * third state, not a dimmer second one. */
    if (vane) {
      const absent = d.fn === 'untested' || d.harnessError;
      vane.piv.visible = !absent;
      S.vaneWant = d.running
        ? (vaneRec.half_deg || -45)          // half-mast while a run is up
        : (d.fn === 'fail' ? (vaneRec.furled_deg || -90)
                           : (vaneRec.flying_deg || 0));
      paint(vaneRec.node, d.fn === 'fail' ? INK.hazardBg : INK.brass);
    }

    /* THE CAP BEAD -- section 2.5, the cell that matters.  FOUR PHYSICALLY
     * DIFFERENT OBJECTS, not four colours of one: at this size a colour swap
     * on a small disc is the weakest mark available, and "fixed it by breaking
     * it" is exactly the state that must never be inferred. */
    vis(PK.cap_ring, untested);
    visAll(PK.cap_stripes, d.hollowVictory);
    visAll(PK.cap_cross, d.harnessError);
    if (d.win) paint(PK.cap, INK.green, { emit: INK.greenCore, intensity: 1.1 });
    else if (untested) paint(PK.cap, INK.glass);
    else paint(PK.cap, INK.glass);
    vis(PK.cap, true);
  }

  /* PKT — section 8.  Same fittings, different hardware, and it fills UPWARD
   * as GOOD news, which is why it must not look like a tube.
   *
   * INTEGRATED 2026-09-06.  PKT ships `variant: "offensive"` and is the first
   * and only module that does.  Rendering it found five defects in this
   * function and its builder, all of them fixed and all of them invisible
   * until something drew it: STATUS_AT_A_GLANCE section 18.4, and
   * `check/shoot_tally.mjs` is the twelve-pose sheet. */
  function applyOffensive(d) {
    const n = (PK.notches || []).length;
    /* `tallyLit()`, not `Math.round(frac * n)`, and the wide shot calls the
     * SAME function -- section 6.4.  See its note in `status.js`: at 12
     * notches over 54 one notch is worth 4.5 exploits, and rounding made the
     * first two confirmed landings invisible on a fitting whose whole point is
     * filling with good news. */
    const lit = tallyLit(d, n);
    (PK.notches || []).forEach((nm, i) => paint(nm, i < lit ? INK.tallyOn
                                                            : INK.tallyOff));
    /* the cap bead is the ARM lamp: dark = SAFE, steady = ARMED,
     * striped = INTERLOCK.  Seeing from across the cockpit that the harpoon is
     * armed is worth having on its own. */
    visAll(PK.cap_stripes, d.arm === 'interlock');
    /* THE HOLLOW RING IS THE UNTESTED MARK ON THIS VARIANT TOO.  It was
     * `vis(PK.cap_ring, false)` unconditionally, so section 7's untested mark
     * never appeared on the offensive fitting and a page with no status data
     * rendered PIXEL-IDENTICALLY to a live `0 / 54, SAFE` -- section 6.2
     * rule 6 violated by one line.  `derive()` now says which it is
     * (`d.untested`); this is the same mark the tube shows, on the same part.
     * PKT NOTES 13 item 1. */
    vis(PK.cap_ring, !!d.untested);
    visAll(PK.cap_cross, d.harnessError);
    paint(PK.cap, d.arm === 'armed' ? INK.tallyOn : INK.glass,
          { intensity: d.arm === 'armed' ? 1.1 : 0 });
    if (vane) vane.piv.visible = false;      // PKT has no vane
  }

  /* ------------------------------------------------------------- THE WORDS */
  function lineOf(d) {
    /* one line: the caption wraps it for its own, narrower, column */
    return statusLine(d, { cols: 0, omitCouldntFinish: true });
  }

  function paintCaption(d) {
    capHd.textContent = CODE + ' TELLTALE';
    /* ONE string, from `status.js -> statusLine()`, so the tooltip in the wide
     * shot and the caption here can never say different things. Filling the
     * caption does not reveal it — the detail gate owns `hidden`. */
    capSub.textContent = wrap(lineOf(d), 34);
    /* `inconclusive` gets its own line and never a column.  FIX_UPLOAD 12.10
     * clipped exactly this word out of the docket's status column, and it is
     * the field that makes "break it so the exploits stop" impossible to paint
     * as clean (section 9.4 rule 1). */
    /* ONE line, and the highest-priority one, so the caption stays three or
     * four lines tall.  It has to: the mast sits on the bottom sill and the
     * caption sits beside it in the 110 px of clear deck between the fitting
     * and the module's own right-hand `.hud`; a fifth line pushes it up over a
     * control.  The full picture is in the detail panel on hover. */
    const w = [];
    /* Qualitative only — never "N inconclusive" / "N never run" counts. */
    /* The state is "a check started and could not give an answer": plain
     * words, the same sentence the wide-shot tooltip and the docket use
     * (status.js COULDNT_FINISH).  Broken at the dash, by hand, so both lines
     * sit well inside the 34-column deck instead of leaving a one-word tail. */
    const INC_LINES = COULDNT_FINISH.replace(' — ', ' —\n');
    if (d.inconclusive) w.push(INC_LINES);
    else if (d.pendingUntested) w.push('SOME PROOFS NEVER RUN');
    else if (d.stale) w.push('STALE — source edited since');
    else if (d.harnessError) w.push('HARNESS ERROR — not your patch');
    capWarn.textContent = d.inconclusive ? INC_LINES : wrap(w.join(''), 34);
    capWarn.style.display = w.length ? '' : 'none';
    paintDetail(d);
  }

  function paintDetail(d) {
    detRows.replaceChildren();
    if (d.kind === 'offensive') {
      pwr.hidden = true;
      detT.textContent = 'FLEET TALLY';
      const r = el('div', 'r');
      r.appendChild(el('span', 'n', ''));
      r.appendChild(el('span', null,
        (d.tally && d.tally.confirmed > 0)
          ? 'confirmed landing this session'
          : 'no confirmed landing this session'));
      /* Never paint confirmed/of totals (Wave 2 / W6-01). */
      r.appendChild(el('span', 's',
        (d.tally && d.tally.confirmed > 0) ? 'YES' : '—'));
      detRows.appendChild(r);
      detFoot.textContent = 'ARM ' + d.arm.toUpperCase();
      return;
    }
    pwr.hidden = false;
    paintPower(d);
    /* Solved-index only — never list unfixed PoCs or catalogue size, and never
     * a total, a remaining count or n-of-m.
     *
     * BOUNDED (f-mv6stu8x).  A module can have dozens of solved numbers, and
     * this panel is placed on the stage, so it may not grow with them:
     *   - hovering the mast shows the first SOLVED_HOVER numbers and "+N more";
     *   - a click PINS the panel (the latch that was already here) and the full
     *     list is then in a box of fixed height that scrolls.
     * Both are the REAL numbers, in numeric order. */
    detT.textContent = 'SOLVED — ' + CODE;
    const ids = solvedIds(d);
    const pinned = !!(gate && gate.state().latched);
    det.classList.toggle('pinned', pinned);
    if (!ids.length) {
      const r = el('div', 'r');
      r.appendChild(el('span', 'n', ''));
      r.appendChild(el('span', null,
        d.sec === 'untested'
          ? 'no solved proofs yet'
          : (d.landing > 0
            ? 'exploits still land — no solved index to show'
            : 'no solved proofs yet')));
      r.appendChild(el('span', 's', ''));
      detRows.appendChild(r);
    }
    const shown = (pinned || ids.length <= SOLVED_HOVER) ? ids : ids.slice(0, SOLVED_HOVER);
    for (const n of shown) {
      const r = el('div', 'r');
      r.appendChild(el('span', 'n', '#' + n));
      r.appendChild(el('span', null, 'solved #' + n));
      const s = el('span', 's', RESULT_WORD.fixed || 'fixed');
      s.style.color = INK.green;
      r.appendChild(s);
      detRows.appendChild(r);
    }
    if (shown.length < ids.length) {
      const r = el('div', 'r more');
      r.appendChild(el('span', 'n', ''));
      r.appendChild(el('span', null, '+' + (ids.length - shown.length)
        + ' more — click the mast to pin and scroll'));
      r.appendChild(el('span', 's', ''));
      detRows.appendChild(r);
    }
    const f = [];
    if (d.fn === 'fail') {
      /* section 5: the first three failed unit-test names, and how many more.
       * The names are the harness's, not ours. */
      const names = d.unitFailures.map(x => (x && (x.name || x.test)) || '')
        .filter(Boolean);
      f.push('UNIT TESTS FAILED: ' + (d.unitFailed || names.length));
      for (const nm of names.slice(0, 3)) f.push('  ' + nm);
      if (names.length > 3) f.push('  … and ' + (names.length - 3) + ' more');
    } else if (d.fn === 'pass') {
      f.push('UNIT TESTS PASS: ' + d.unitPassed);
    } else if (d.harnessError) {
      f.push('HARNESS ERROR — this is not your patch');
    } else {
      f.push('UNIT TESTS NOT RUN');
    }
    detFoot.textContent = f.join('\n');
  }

  /* ------------------------------------------------------------- PLACEMENT
   * Anchored to the fitting's own projected envelope, then nudged so it stays
   * on the stage.  The caption sits UNDER the mast and the detail panel ABOVE
   * it, because the mast is on the bottom sill of the frame on most modules
   * and the space above it is the space the player is not working in.
   *
   * Both are measured against the mast's own declared hotspot, which the
   * builder projected from the whole assembly (both vane poses included) and
   * not from a bounding box -- the refit port's base-hexagon rect was 5-7 px
   * short of the pixels it painted on every side (FIX_UPLOAD 12.4). */
  /* Everything the caption must not sit on, measured at place() time rather
   * than declared: the module's declared readout rects, its control hotspots,
   * the refit port's hotspot, and every screen-space panel already on the
   * stage -- the two `.hud` boxes and, crucially, the refit DOCKET, which is
   * 520 x 318 and only exists while the port is open.  Reading the mast WHILE
   * the port is open is the whole point of the close-up half, so the docket is
   * a live rect and not a constant. */
  function keepOut() {
    const out = [];
    const planes = (o.S.text_planes || [o.S.text_plane] || []).filter(Boolean);
    for (const t of planes) {
      if (!t.corners_px) continue;
      const c = t.corners_px, ks = Object.keys(c);
      out.push([Math.min(...ks.map(k => c[k].x)), Math.max(...ks.map(k => c[k].x)),
                Math.min(...ks.map(k => c[k].y)), Math.max(...ks.map(k => c[k].y))]);
    }
    for (const k in (o.S.props || {})) {
      const r = (o.S.props[k] || {}).hotspot;
      if (r) out.push([r.x, r.x + r.w, r.y, r.y + r.h]);
    }
    const rp = (o.S.refit || {}).hotspot;
    if (rp) out.push([rp.x, rp.x + rp.w, rp.y, rp.y + rp.h]);
    if (stageEl) {
      const st = stageEl.getBoundingClientRect();
      const k = st.width / W || 1;
      for (const e of stageEl.querySelectorAll('.hud, #refit .docket')) {
        if (e.hidden || !e.offsetWidth) continue;
        const r = e.getBoundingClientRect();
        out.push([(r.left - st.left) / k, (r.right - st.left) / k,
                  (r.top - st.top) / k, (r.bottom - st.top) / k]);
      }
    }
    return out;
  }

  /* Same solver `refit.js` uses for its docket, and for the same reason: a
   * fixed offset is right until something else moves.  The FITTING ITSELF is
   * the first thing the caption must not sit on -- a caption over the mast
   * hides the instrument the caption is about -- so it is weighted 4x, exactly
   * as the port weights its own envelope. */
  /* THE CLAMP USED TO BE THE ANSWER AND IT IS NOT AN ANSWER.
   *
   * Candidate 2 is `[hs.x - w - 12, H - 8 - h]` -- "to port, on the sill" --
   * and `clamp()` pushes x up to 8.  When the room to port is less than
   * `w + 12` that clamp SILENTLY RETURNS A RECT OVER `mine`: the caption is
   * pushed back onto the fitting it captions.  The 4x `mine` weight cannot
   * save it either, because a small overlap costs less than one rank step:
   * IPM's 362 px^2 of mast hotspot cost 4 x 362 = 1448 against the 1500 a step
   * down the candidate list costs, so the overlapping candidate WON.  IPM
   * worked it around by shipping a 170 px mast instead of 180; that workaround
   * is now redundant but is NOT removed -- 170 px is a measured, shipped
   * number with an envelope, a hotspot and a `grad_px` on record.
   *
   * The rule is a REJECTION, not a heavier weight: a caption that covers a
   * fitting is never the right answer while a candidate that covers none
   * exists.  So candidates are ranked in TWO PASSES -- the ones clear of every
   * fitting first, everything else only if there are none -- and the existing
   * cost function decides within each pass, unchanged.  If nothing is clear (a
   * genuinely constrained sill) every candidate stays in and the behaviour is
   * exactly what it was.
   *
   * TWO DETAILS, both of which cost a measured regression when they were the
   * other way round:
   *
   *   - the test is over EVERY FITTING, this one and the refit port, not just
   *     `mine`.  With only `mine` the solver escaped the mast by landing on
   *     88 % of the port's hotspot instead, which is not an improvement.
   *   - it is measured on the DRAWN hotspots, not on `mine`'s 4 px gutter.
   *     Clipping the gutter by half a pixel is not "the caption is on the
   *     instrument", and disqualifying for it hands the slot to a candidate
   *     that covers a whole fitting.  Constructed and measured on a mast
   *     anchored 4 px to port of IPM's: rejecting on the padded rect moves the
   *     caption from 0 px^2 to 4,571 px^2 of the refit port.
   *
   * The caption's width is DATA (IPM's third line used to be `1 INCONCLUSIVE —
   * the PoC could not decide`, now `Check couldn't finish — no result yet`,
   * and it is still data), so this fires on any module whose caption wraps, not
   * just on the two that have been looked at.  IPM NOTES 13 item 3.
   *
   * MEASURED, IPM's mast rebuilt at 180 px and re-anchored, `caption ∩ mast`
   * in stage px^2:
   *
   *      anchor      room to port     clamp-only     as it ships
   *      284, 685       261.8 px          0.0            0.0
   *      280, 685       257.8 px         34.6            0.0
   *      276, 685       253.7 px        296.8            0.0
   *
   * and all seven built modules' caption rects are byte-identical either way.
   */
  function best(w, h, cands, rects, mine, fittings) {
    const clamp = (x, y) => [Math.max(8, Math.min(W - w - 8, x)),
                             Math.max(8, Math.min(H - h - 8, y))];
    const cx = mine[0] + (mine[1] - mine[0]) / 2;
    const cy = mine[2] + (mine[3] - mine[2]) / 2;
    let win = null, clear = false;
    for (let i = 0; i < cands.length; i++) {
      const [x, y] = clamp(cands[i][0], cands[i][1]);
      const over = r => Math.max(0, Math.min(x + w, r[1]) - Math.max(x, r[0]))
                      * Math.max(0, Math.min(y + h, r[3]) - Math.max(y, r[2]));
      /* ON A FITTING, measured on the DRAWN rects and not on `mine`'s 4 px
       * gutter -- clipping the gutter by half a pixel is not "the caption is
       * on the instrument", and disqualifying a candidate for it would hand
       * the slot to one that covers 88 % of the refit port instead.  Measured:
       * that is exactly what happens on a mast anchored 6 px further to port
       * than IPM's. */
      let onFit = 0;
      for (const f of (fittings || [])) onFit += over(f);
      /* first candidate that covers NO fitting discards every winner found so
       * far; after that, one that covers a fitting cannot win at all.  If none
       * is clear -- a genuinely constrained sill -- every candidate stays in
       * and the cost function below decides, which is what it did before. */
      if (!onFit && !clear) { clear = true; win = null; }
      else if (onFit && clear) continue;
      let cover = 4 * over(mine);
      for (const r of rects) cover += over(r);
      /* THE RANK PENALTY IS NOT DECORATION, and it is worth saying why in
       * px^2.  Least-overlap alone put the caption straight over the console
       * face, because the console face is not a declared rect: KVS declares
       * one readout (the transcript, y 308..464) and three control hotspots,
       * and the band between the transcript and the deck is nobody's
       * rectangle even though it is the instrument.  A checker cannot see
       * that and neither can this solver.  So the candidates are ORDERED --
       * along the sill first, over the panel last -- and each step down the
       * list costs 1500 px^2, which a real overlap of any size beats and a
       * zero-overlap tie does not. */
      cover += i * 1500;
      const near = Math.hypot(x + w / 2 - cx, y + h / 2 - cy);
      if (!win || cover < win[0] - 1 || (cover < win[0] + 1 && near < win[1]))
        win = [cover, near, x, y];
    }
    return [win[2], win[3]];
  }

  function place() {
    if (!stageEl) return;
    const hs = R.hotspot;
    const mine = [hs.x - 4, hs.x + hs.w + 4, hs.y - 4, hs.y + hs.h + 4];
    const rects = keepOut();
    const cw = cap.offsetWidth || 260, ch = cap.offsetHeight || 70;
    /* ORDERED BY PREFERENCE, and the order is the sill first.  The design
     * puts the fitting on the bottom sill on eight of nine modules (section
     * 6.3), so the deck beside it is the one band of a close-up that is never
     * instrument -- and it is where a caption belongs, next to the thing it
     * captions and off the panel. */
    const cands = (w, h) => [
      [hs.x + hs.w + 12, H - 8 - h],                // starboard, on the sill
      [hs.x - w - 12, H - 8 - h],                   // to port, on the sill
      [hs.x + hs.w / 2 - w / 2, hs.y + hs.h + 10],  // directly under it
      [hs.x + hs.w + 12, hs.y - h - 10],            // starboard and above
      [hs.x - w - 12, hs.y - h - 10],               // to port and above
      [hs.x + hs.w / 2 - w / 2, hs.y - h - 10],     // over it -- last resort
    ];
    /* THE DRAWN RECTS, for the two-pass test in `best()`: this fitting's own
     * published hotspot and the refit port's, if the module has one.  A
     * caption on either hides an instrument. */
    const rp = (o.S.refit || {}).hotspot;
    const fittings = [[hs.x, hs.x + hs.w, hs.y, hs.y + hs.h]];
    if (rp) fittings.push([rp.x, rp.x + rp.w, rp.y, rp.y + rp.h]);
    const c = best(cw, ch, cands(cw, ch), rects, mine, fittings);
    cap.style.left = c[0] + 'px';
    cap.style.top = c[1] + 'px';

    if (!det.hidden) {
      /* Both panels can be open together. Keep the detail off the caption. */
      const dw = det.offsetWidth || 300, dh = det.offsetHeight || 150;
      const obstacles = cap.hidden ? rects
        : rects.concat([[c[0], c[0] + cw, c[1], c[1] + ch]]);
      const d = best(dw, dh, cands(dw, dh), obstacles, mine, fittings);
      det.style.left = d[0] + 'px';
      det.style.top = d[1] + 'px';
    }
  }

  /* ------------------------------------------------- THE DOCKET IS NOT STATIC
   * `keepOut()` has counted `#refit .docket` since it was written, but nothing
   * ever RE-RAN the solver when the docket appeared, moved or went away.  On
   * KVS that is invisible: the docket lands on the LEFT half of the frame and
   * the caption's winning slot is on the right, so the two never met.  On MQB
   * the docket's left candidate clamps to x 12 and then covers the port's own
   * envelope, which `refit.js` weights 4x, so the docket lands to the port's
   * RIGHT at (312, 390) 520 x 318 -- straight under the caption's first choice
   * ("to port, on the sill").  MQB fixed it module-side with a
   * MutationObserver; every remaining module whose docket lands right would
   * have needed one too.  MQB NOTES section 13 item 8.
   *
   * TWO SOURCES, because neither alone is enough:
   *   - `refit:docket`, which `refit.js` now emits on open, on close and on
   *     every re-place.  Works even if this mast mounted BEFORE the port.
   *   - a MutationObserver on the docket element, for a page that moves or
   *     hides the docket itself without going through `open()`/`seal()`.
   *
   * IT NEVER RUNS WHILE THE MAST IS HIDDEN.  `pose()` hides the mast and also
   * hides the docket; a re-place during a capture pose is exactly the class of
   * thing that costs a byte-identical grab, so the visibility test is the
   * guard, not a nicety.  Coalesced onto one frame so a docket that moves
   * twice in an open() does not solve the caption twice. */
  let dkEl = null, dkMo = null, dkPending = false, dkSig = '';

  /* WHAT THE DOCKET IS, RIGHT NOW, as one comparable string.  `refit.js`
   * re-runs `placeDocket()` on every frame while the port is open, and a
   * MutationObserver on `style` sees every one of those writes; re-solving the
   * caption 60 times a second is exactly the churn `refresh()`'s signature
   * check exists to avoid.  This re-places when the docket MOVED, not when it
   * was written to. */
  function docketSig() {
    const d = dkEl;
    if (!d || d.hidden || !d.offsetWidth) return 'none';
    return d.style.left + '|' + d.style.top + '|'
         + d.offsetWidth + '|' + d.offsetHeight;
  }

  function replaceSoon() {
    if (dkPending || !root.visible) return;
    const sig = docketSig();
    if (sig === dkSig) return;
    dkSig = sig;
    dkPending = true;
    const run = () => { dkPending = false; if (root.visible) place(); };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
    else run();
  }

  function bindDocket() {
    const d = stageEl && stageEl.querySelector
      ? stageEl.querySelector('#refit .docket') : null;
    if (d === dkEl) return;
    if (dkMo) { dkMo.disconnect(); dkMo = null; }
    dkEl = d;
    if (d && typeof MutationObserver === 'function') {
      dkMo = new MutationObserver(replaceSoon);
      /* `hidden` is open/close, `style` is placeDocket()'s left/top.  NOT
       * `subtree`: the docket's own contents repaint on every phase and the
       * caption does not care where a filename went. */
      dkMo.observe(d, { attributes: true,
                        attributeFilter: ['hidden', 'style', 'class'] });
    }
  }

  function onDocket(ev) {
    if (ev && ev.detail && ev.detail.code && CODE && ev.detail.code !== CODE)
      return;
    bindDocket();
    replaceSoon();
  }
  addEventListener('refit:docket', onDocket);

  /* ================================================================ HOTSPOT */
  /* `wireHotspot`, not `o.hotspot` -- MTA, PKT and IPM take a pointerdown
   * HANDLER here, FMM takes (key, label, onDown, onMove) and DNSM takes
   * {click, drag}.  See THE HOTSPOT ADAPTER in `refit.js`. */
  const hs = R.hotspot;
  /* THE TITLE SAYS WHAT THIS VARIANT ACTUALLY HAS.  It was hard-coded to "the
   * security and function axes" for every module, and the offensive fitting
   * has NEITHER -- section 8's whole premise, and `derive()` correctly returns
   * `fn: 'n/a'`, `sec: 'n/a'` for it.  A tooltip that names two axes a player
   * cannot find on the fitting is worse than no tooltip.  PKT NOTES 13
   * item 5. */
  const hot = wireHotspot(o, { x: hs.x, y: hs.y, w: hs.w, h: hs.h },
    R.variant === 'offensive'
      ? 'TELLTALE MAST — the fleet exploit tally and the arm lamp'
      : 'TELLTALE MAST — the security and function axes', h => {
      gate = bindStatusDetails(h, cap, det);
      gate.onChange = () => {
        paintDetail(S.d);
        if (root.visible) place();
      };
    });

  /* =================================================================== DATA */
  /* THE SOURCE, and its three fallbacks, in the order section 6.2 rule 7 sets:
   * the parent cockpit if there is one, else `status.json`, else the UNTESTED
   * pose.  Never a spinner, never a throw.  `moduleStatus()` in `status.js`
   * IS that ladder; this file does not reimplement it.  Live is inside that
   * same call (parent merge, or a peer fetch when standalone). */
  let poll = null;

  /* HOW MANY `status.json` / `/api/live` READS ARE IN FLIGHT.  `settled()`
   * reports a non-zero count as NOT SETTLED; see the note there.  A counter
   * and not a boolean, because `show(true)` and a 5 s poll tick can overlap. */
  let inflight = 0;
  /* Drop a fetch that landed after pose() / set() / a newer refresh. */
  let seq = 0;
  /* pose() / set() bump this so a refresh that lands late is dropped. */
  let hold = 0;

  function poweredOf(d) {
    const p = d && d.live && d.live.powered;
    return (p === 'on' || p === 'off' || p === 'unknown') ? p : null;
  }

  function releasedOf(d) {
    if (!d || !d.live) return true;
    if (d.live.released === false) return false;
    if (d.live.availability === 'not_yet_available') return false;
    return true;
  }

  /* Read-only word inside the detail. Not a button and not a post. */
  function paintPower(d) {
    const powered = poweredOf(d);
    const released = releasedOf(d);
    if (!released) pwrState.textContent = 'NOT YET AVAILABLE';
    else if (powered === 'on') pwrState.textContent = 'ON';
    else if (powered === 'off') pwrState.textContent = 'OFF';
    else if (powered === 'unknown') pwrState.textContent = 'POWER ?';
    else pwrState.textContent = '';
    pwrState.setAttribute('data-powered', released ? (powered || '') : 'locked');
    pwrState.style.opacity = released ? '' : '0.55';
  }

  async function refresh() {
    const mine = ++seq;
    let d;
    inflight++;
    try { d = await moduleStatus(CODE, o.statusUrl); }
    catch (e) { d = derive(null, { code: CODE }); }
    finally { inflight--; }
    if (mine !== seq) return S.d;
    /* Only repaint when something actually moved.  A 5 s poll that rebuilds
     * six materials and a DOM list every tick is churn the capture harness can
     * see; this makes the page byte-stable between polls. */
    /* `d.untested` IS IN HERE and it has to be.  On the offensive variant a
     * record of `0 / 54, SAFE, idle` derives every other field identically to
     * NO RECORD AT ALL, so without it the signature cannot tell the untested
     * pose from a live empty tally and `apply()` would not re-run when the
     * first real record landed on a page that had none.  Section 18.4 item 1.
     * `d.live` is the peer: TCP up/down must refresh the caption without
     * touching geometry. */
    const sig = JSON.stringify([d.fn, d.sec, d.run, d.stale, d.win,
                                d.hollowVictory, d.harnessError, d.total,
                                d.items.map(i => i.result),
                                d.segments.map(i => i.result),
                                d.arm, d.tally && d.tally.confirmed,
                                !!d.untested,
                                d.live && d.live.online, d.live && d.live.latency_ms,
                                d.live && d.live.powered]);
    if (sig === S.sig) return S.d;
    S.sig = sig;
    apply(d);
    place();
    return d;
  }

  function startPoll() {
    if (poll) return;
    poll = setInterval(() => { refresh(); }, POLL_MS);
  }
  function stopPoll() { if (poll) { clearInterval(poll); poll = null; } }

  /* The refit port's live push.  Section 11.3: `status.json` is the durable
   * record and `refit:<CODE>` is the live event; the event is a HINT TO
   * RE-READ, never the only place a result exists.  A reload must not lose
   * anything, so nothing here is stored from the event itself. */
  function onRefit(ev) {
    if (!ev || !ev.detail || ev.detail.code !== CODE) return;
    refresh();
  }
  addEventListener('refit:' + CODE, onRefit);
  addEventListener('refit', onRefit);

  /* ================================================================== FRAME */
  function tick(dt, now) {
    S.ticks++;
    if (!root.visible) return;
    S.t += dt;
    /* FROZEN, for a capture only -- see settle() below.  `S.t` and `S.sweepT`
     * drive the RUNNING sweep band and the cap bead's breath, the only two
     * things here that loop for ever; pinning both to 0 makes every frame the
     * same frame without touching a single piece of derived state.  Nothing on
     * a page a human opens ever sets this. */
    if (S.frozen) { S.t = 0; S.sweepT = 0; }

    /* THE SWEEP -- section 2.3.  A 1.4 s ease-in-out band running from the
     * collar end outward, and the ONLY animation in the whole indicator.  It
     * exists because the real thing takes minutes: `run-in-docker.sh` does a
     * `docker compose --build`. */
    if (sweepMesh) {
      const on = !!S.d.running;
      sweepMesh.visible = on;
      if (on) {
        /* `!S.frozen` IS THE WHOLE OF ISSUE 1 AND IT IS NOT COSMETIC.  The
         * freeze above pins `S.sweepT` to 0 and this line used to advance it
         * again in the same call, so under `settle(true)` the band sat at
         * THAT FRAME'S `dt` -- a function of frame time -- and jittered about
         * 0.006 px while `settled()` reported `[]` (it short-circuits on
         * `S.frozen`).  IPM is `status.json`'s only `running` module and it is
         * the module that found it: the SHOWN capture failed by 1 px at
         * pixelRatio 1 and 2 px at pixelRatio 2, every pixel on the band's
         * leading edge, and flipping `run.state` to `done` and nothing else
         * made the whole report byte-identical to the baseline.  IPM NOTES
         * 13 item 1. */
        if (!S.frozen) S.sweepT = (S.sweepT + dt) % ((sweepRec.ms || 1400) / 1000);
        const u = S.sweepT / ((sweepRec.ms || 1400) / 1000);
        const e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
        sweepMesh.position.copy(sweepHome)
          .addScaledVector(axisA, e * (sweepRec.travel_m || 0));
      } else if (sweepHome) {
        sweepMesh.position.copy(sweepHome);
        S.sweepT = 0;
      }
    }

    /* THE VANE eases to its pose rather than snapping, so a service coming
     * back up reads as the pennant filling. */
    if (vane && vaneAxis) {
      S.vaneDeg += (S.vaneWant - S.vaneDeg) * Math.min(1, dt * 7);
      vane.piv.setRotationFromAxisAngle(vaneAxis, S.vaneDeg * D2R);
    }

    /* the cap bead breathes only while a run is in flight; at rest it is a
     * steady lamp, so two successive posed captures are identical. */
    const cm = mats[PK.cap];
    if (cm && S.d.win) {
      cm.emissiveIntensity = S.d.running
        ? 0.7 + 0.4 * (0.5 + 0.5 * Math.sin(S.t * 1.4 * 2 * Math.PI)) : 1.1;
    }
  }

  /* =================================================================== POSE
   * HIDE IT, and reset to the UNTESTED pose.  Same decision as the refit
   * port's (FIX_UPLOAD section 0 decision 3) and the same reason: every number
   * in the module's NOTES was captured against Blender renders that contain no
   * mast, and hiding it reproduces all of them unchanged while re-rendering
   * nothing.  The mast's own behaviour is measured with it SHOWN --
   * `__mast.show(true)` -- which is a separate capture, not this one.
   *
   * The poll is stopped as well.  A 5 s interval that repaints between the
   * harness's two screenshots is precisely README 16.8's 520 ms cursor blink
   * wearing a different hat. */
  function pose() {
    hold++;
    seq++;
    stopPoll();
    root.visible = false;
    if (gate) gate.reset();
    S.frozen = false;
    S.t = 0; S.sweepT = 0;
    S.sig = '';
    apply(derive(null, { code: CODE }));
    if (gate) gate.reset();
    S.vaneDeg = S.vaneWant;
    if (vane && vaneAxis) vane.piv.setRotationFromAxisAngle(vaneAxis,
                                                            S.vaneDeg * D2R);
    if (sweepMesh && sweepHome) {
      sweepMesh.position.copy(sweepHome);
      sweepMesh.visible = false;
    }
    cap.hidden = true;
    det.hidden = true;
    if (hot) hot.style.display = 'none';
    layer.style.display = 'none';
  }

  /* PLACE FIRST, THEN FETCH.  This used to be `refresh().then(place)`, and the
   * caption is `position:absolute` with no `left`/`top` until `place()` has run
   * once -- so between `show(true)` and the first `status.json` response it
   * painted at its static position, THE STAGE'S TOP-LEFT CORNER: a dark
   * `<CODE> TELLTALE / UNTESTED` panel over the corner of the instrument.
   *
   * Nobody saw it on the first two modules because nobody could: the first
   * `status.json` response arrives at 126 ms on KVS and 175 ms on MQB.  It
   * arrives at 3.15 s on MTA and 3.49 s on FMM, because those two pages have
   * their own `scene.json`, a 3.7 MB `depth.bin`, `plate.png` and five or more
   * glbs ahead of it in the connection queue -- so MTA shipped with three and a
   * half seconds of caption in the corner and every checker passed, because
   * `shoot_occlusion.mjs` waits for `networkidle0` before it grabs anything and
   * the harness therefore never sees the state a human opens the page in.
   * FMM NOTES 14 item 11; measured with a route rule holding `status.json`.
   *
   * `place()` is idempotent and needs no data -- `pose()` has already applied
   * the UNTESTED pose, so the caption has its final SIZE, and the solver only
   * needs the fitting's own hotspot and the stage.  So it is called
   * SYNCHRONOUSLY here, while the layer is being un-hidden, and `refresh()`
   * re-places it when the real record lands.  FMM worked this around
   * module-side with one `mast.place()` after `mast.show(true)`; that line is
   * now redundant (it is left in place, and costs one extra solve). */
  function show(v) {
    const on = v === undefined ? true : !!v;
    root.visible = on;
    if (hot) hot.style.display = on ? '' : 'none';
    layer.style.display = on ? '' : 'none';
    /* Both directions drop latch, hover, and the arrival arm. A module
     * return starts quiet even if the pointer is already on the hotspot. */
    if (gate) gate.reset();
    if (on) { place(); refresh().then(place); startPoll(); } else { stopPoll(); }
  }

  /* ================================================================ SETTLE
   * FAST-FORWARD EVERY EASED TRANSITION, so a capture does not have to be
   * timed.  `pose()` resets to the UNTESTED pose and `show(true)` re-derives
   * from `status.json`, which gives the VANE a new target -- and the vane
   * EASES (`vaneDeg += (want - vaneDeg) * min(1, dt*7)`) rather than snapping,
   * so for about two seconds after `show(true)` the frame is still changing.
   * At `shoot_occlusion.mjs`'s default `SETTLE=400` the two back grabs are
   * taken mid-ease and `check_occlusion.py` reports it as a PARTITION FAILURE
   * with "must be 0" counters -- 7 px at pr 1 / 47 at pr 2 on FMM, every one
   * of them antialiasing on the vane's two diagonal edges.  A genuine-looking
   * FAIL from a harness setting.  FMM NOTES 10.1.
   *
   * The answer is not a bigger number.  `settle()` snaps the eased state to
   * its target and `settled()` says whether anything is still in flight, so
   * the harness can WAIT ON A PREDICATE instead of on a guess.  Neither
   * changes the derived state, the materials or the geometry: `settle()` is
   * exactly the frame the ease was heading for.
   *
   * A state that animates FOREVER -- `running`, where the sweep band runs the
   * bore and the cap bead breathes -- cannot settle, and `settled()` says so
   * rather than pretending.  That is a real property of the capture, not a
   * defect: a module whose live record is `running` has no byte-stable frame
   * and the harness should report it, not average over it. */
  function settle(freeze) {
    if (freeze !== undefined) S.frozen = !!freeze;
    let moved = 0;
    if (vane && vaneAxis && Math.abs(S.vaneWant - S.vaneDeg) > 1e-9) {
      S.vaneDeg = S.vaneWant;
      vane.piv.setRotationFromAxisAngle(vaneAxis, S.vaneDeg * D2R);
      moved++;
    }
    return moved;
  }

  function settled() {
    if (!root.visible) return true;
    /* A PENDING `status.json` READ IS AN UNSETTLED PAGE, and this is the
     * second half of what `settled()` is for.  `show(true)` is
     * `place(); refresh().then(place)`, and `pose()` has just reset the
     * caption to the UNTESTED string -- 255.2 x 49 px on PKT against 212.4 x
     * 67.4 for its live one, at a different solved x -- so between the two the
     * caption is ABOUT TO CHANGE SIZE AND MOVE.  Nothing eases on a module
     * with no vane and no sweep, so the old gate returned `[]` on the first
     * poll and the harness grabbed the untested caption at the untested
     * position: PKT's SHOWN capture failed 1 run in 4 at the default
     * SETTLE=400 with 5,594 px of section 0, every one of them on the
     * caption's own edges, and was clean 3 of 3 at 2500.  A number is a guess;
     * this is the fact.  PKT NOTES 14 item 5.
     *
     * BEFORE the `S.frozen` short-circuit, deliberately: freezing the phase
     * clocks does not make a fetch land, and a frozen capture taken over a
     * pending refresh is exactly the race this closes. */
    if (inflight > 0) return false;
    if (vane && vaneAxis && Math.abs(S.vaneWant - S.vaneDeg) > 1e-4) return false;
    if (S.frozen) return true;      /* every loop is pinned; see settle() */
    /* the sweep band and the cap breath both run off `d.running` and both
     * loop; nothing about them ever comes to rest. */
    if (S.d && S.d.running) return false;
    return true;
  }

  function dispose() {
    stopPoll();
    removeEventListener('refit:' + CODE, onRefit);
    removeEventListener('refit', onRefit);
    removeEventListener('refit:docket', onDocket);
    if (dkMo) { dkMo.disconnect(); dkMo = null; }
    if (gate) gate.dispose();
    layer.remove();
    if (hot) hot.remove();
    o.scene.remove(root);
    if (typeof window !== 'undefined' && window.__fittings)
      delete window.__fittings.mast;
  }

  pose();

  /* Trap 21, on this fitting's own meshes.  The vane, the hazard chevrons, the
   * hatch bars and the scrim bars are exactly the shapes the trap names; they
   * are built as closed prisms so it cannot bite, and this is what KNOWS. */
  const facing = () => facingAudit(THREE, meshes, o.camera);
  const facing0 = facing();
  if (facing0.length)
    console.warn('[mast:' + CODE + '] facingAudit: these mast meshes face '
      + 'AWAY from the camera and dress()\'s FrontSide is discarding them: '
      + facing0.join(', '));

  watchTick('mast', S, () => root.visible);
  bindDocket();

  const api = {
    root, tick, pose, show, dispose, refresh, place, facing, settle, settled,
    code: CODE,
    tris: TRIS,
    m: M,
    caption: cap, detail: det, hotspot: hot,
    state: () => ({ visible: root.visible,
                    open: !!(gate && gate.state().open),
                    latched: !!(gate && gate.state().latched),
                    derived: S.d, sig: S.sig }),
    /* Force a derived state without a status.json.  For the harness and for
     * looking at every state on a real screen, which is the only way any of
     * this was ever going to be checked.  It takes a RECORD, not a display
     * state, so what is exercised is `derive()` and not a second path. */
    set: rec => { hold++; seq++;
                  const d = derive(rec, { code: CODE });
                  S.sig = ''; stopPoll();
                  apply(d); place(); return d; },
    __test: { S, apply, paint, byName, mats },
  };
  registerFitting('mast', api);
  return api;
}
