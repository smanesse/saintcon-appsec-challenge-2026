/* THE REFIT PORT -- frontend.  One file, all nine modules.
 *
 * `live3d/design/FIX_UPLOAD.md` is the design.  `live3d/pipeline/refit_port.py`
 * is the Blender half and writes the `"refit"` block in each module's
 * `scene.json`; this file reads that block and needs to know nothing else
 * about the module.  A module wires it in nine lines:
 *
 *     import { mountRefit } from '../../refit.js';
 *     const refit = await mountRefit({
 *       THREE, scene, camera, split, S, assetBase: A, code: CODE,
 *       load, dress, hotspot, layerHost: $('stage'),
 *     });
 *     ...  refit.tick(dt, now)   from the module's own onFrame
 *     ...  refit.pose()          from the module's poseForCapture()
 *
 * ==========================================================================
 * FIVE THINGS THAT ARE LOAD-BEARING
 * ==========================================================================
 * 1. `pose()` HIDES THE PORT.  Every recorded number in `live3d/RESULTS.md`
 *    was captured from `pose()` against Blender renders that contain no port.
 *    Hiding it reproduces all of them unchanged and re-renders nothing.  That
 *    is FIX_UPLOAD section 0, decision 3, and it is the whole reason this
 *    component is cheap.  `check_occlusion.py`'s section 0 will report the
 *    port as an as-loaded/posed difference; that section is REPORTED, NOT
 *    FAILED ON, and the difference is the design rather than drift.  Prove the
 *    port's own behaviour with the port SHOWN instead -- see NOTES.
 * 2. NO TIMERS.  Not one `setInterval`, not one private `requestAnimationFrame`.
 *    Everything animates off `tick(dt, now)`, which the module's existing loop
 *    calls, so `pose()` cannot leave a clock running.  README section 16.8
 *    records a module failing a byte-identical capture for a 520 ms cursor
 *    blink that `pose()` flagged off but never `clearInterval`'d.
 * 3. EVERY MATERIAL GOES THROUGH THE MODULE'S OWN `dress()`.  That is what
 *    chains `attachDepthTest` (the baked-depth composite) and then
 *    `attachForeground` (the split).  A material that misses the second draws
 *    in BOTH passes and double-blends -- `split.auditScene()` finds it, and it
 *    looks like "the edges got slightly darker", not like an error.
 *    CONVERSION_BRIEF traps 14 and 15.
 * 4. NO `innerHTML`, ANYWHERE.  The docket renders bytes this page does not
 *    control -- filenames, build logs, test output.  `textContent`,
 *    `createTextNode` and `createElement` only.  CONVERSION_BRIEF section 4
 *    step 6; `grep -nE '\.innerHTML\s*(=|\+=)'` over this file is empty.
 * 5. THE JEWEL IS WHITE-FAMILY ONLY.  Dark, breathing, steady, double-blink.
 *    It never goes green, amber or red.  It reports ONE thing: did the last
 *    refit you commanded go in.  Every colour and every statement about
 *    whether the module is now GOOD belongs to the telltale mast.
 *    FIX_UPLOAD section 4; STATUS_AT_A_GLANCE section 11.2 accepted this.
 *    FILE RETURN does not move the jewel, the tally flag, or the ratchet.
 *
 * ==========================================================================
 * THE SEAM WITH THE TELLTALE MAST -- two values, one each way
 * ==========================================================================
 * OUT: one `refit:<CODE>` CustomEvent per state change, on `window`.
 *
 *      detail = { code, phase, state, rehearsal, cmd, ts,
 *                 tests: { unit: {pass, fail},
 *                          vuln: {fired, closed, inconclusive, total} } }
 *
 *      `state` is the mast's own enum -- idle | queued | building | running |
 *      done | error -- because it asked for that one rather than a second.
 *      `vuln.inconclusive` IS CARRIED DELIBERATELY.  A bare {fired, closed}
 *      pair is the one shape that can produce a wrong picture: it makes
 *      "break the service so the exploits stop firing" indistinguishable from
 *      "fix the service".  STATUS_AT_A_GLANCE section 9.4 rule 1.
 *      The event is a LIVE PUSH, not the durable record.  `status.json` is the
 *      record; a consumer should treat this as a hint to re-read, never as the
 *      only place a result exists, or a reload loses it.
 *
 * IN:  one boolean, `dirty` -- does the workbench source differ from the
 *      running image.  Used for exactly one thing: whether the idle jewel is
 *      dark or breathing.  Supply it with `setDirty(v)`, or leave it and this
 *      file will pick up `window.__status.dirty(code)` if the mast has landed
 *      and a `status:dirty` event if it prefers to push.  It is optional in
 *      both directions: the port works with neither.
 *
 * FILE RETURN is a sibling gesture on the same docket, not a second port.
 * Opening the iris is neither a rebuild nor a file return.  COMMIT REFIT
 * rebuilds this module locally.  FILE RETURN `POST /api/submit`s the whole
 * challenge and polls `GET /api/submissions/<id>` from `tick()`.  A
 * `file-return` event on `window` carries `{ jobId, status_name, passed,
 * rehearsal, ts }` -- no vuln titles, and never stuffed into `refit:<CODE>`.
 *
 * ==========================================================================
 * REHEARSAL, now labelled for players as "preview only"
 * ==========================================================================
 * `live3d/run.sh` is a static file server and cannot reach a Docker socket.
 * Until the cockpit is served by (or proxied to) something that can, the port
 * runs the whole ceremony and BUILDS NOTHING: it emits the event, prints the
 * exact commands it would have run, and says "Preview only -- nothing was
 * rebuilt" on the docket so nobody is misled.  Wiring this to real Docker is a
 * separate decision with real consequences and is deliberately not taken here.
 *
 * OWNER-FIXES T2 (f-mv6sv398 refit part, f-mv6tgbdh):
 *   - The sample "built 14:02 / 3 files amended / PROVE 8 of 8" fixture is
 *     DEMO DATA.  It is used only when the page URL (or its embedding cockpit
 *     page) carries exactly `?demo=1`, and the docket says DEMO DATA while it
 *     is.  Nothing is read from storage, so stale state cannot switch it on.
 *     A normal first open shows an honest empty state.
 *   - Without demo mode a rebuild is a PREVIEW: the steps animate for the
 *     ratchet, no fake pass/fail result is produced, `applied`, `dirty` and the
 *     tally flag are never touched, and the docket says so.
 *   - FILE RETURN sends `{}` (no `alien_target`): the harness then grades every
 *     module and every released ship in one job.  There is no ship picker and
 *     no link to any other module from this docket.  `api.js` `submit()` still
 *     supports a chosen `alien_target`; this file simply does not offer one.
 *
 * FILE RETURN with no coordinator on this origin does not POST.  It says
 * "Preview only -- nothing was sent".  Until the shared `/api` client is used
 * here this file uses same-origin `fetch('/api/submit')` and
 * `fetch('/api/submissions/')`.
 */

import {
  rebuildAllowed, rebuildStatusText, rebuildLogText, rebuildTerminal,
  postRebuild, getRebuild, rebuildJob, rebuildJobId,
} from './service-rebuild.js';
import { power, moduleStatus } from './status.js';

/* ------------------------------------------------------------------ fleet
 * The compose service name is NOT the module code.  MTA's service is `mail`.
 * Counts are the SHIPPED PoC counts, checked against the repo, not the
 * challenge README's -- that file's per-module numbers are wrong for six of
 * eight modules and anything sized from them draws graduations that can never
 * fill.  STATUS_AT_A_GLANCE section 12.2. */
export const FLEET = {
  KVS:  { svc: 'kvs',  dir: 'keystore-module',          title: 'CORE MEMORY BANKS',  vulns: 6 },
  FMM:  { svc: 'fmm',  dir: 'file-management-module',   title: 'FILE MANAGEMENT',    vulns: 8 },
  IPM:  { svc: 'ipm',  dir: 'image-processing-module',  title: 'IMAGE PROCESSING',   vulns: 7 },
  DNSM: { svc: 'dnsm', dir: 'dns-module',               title: 'CHART & COURSE',     vulns: 6 },
  LOG:  { svc: 'log',  dir: 'log-module',               title: "SHIP'S LOG",         vulns: 4 },
  OTA:  { svc: 'ota',  dir: 'ota-module',               title: 'FLEET REPLICATOR',   vulns: 8 },
  MQB:  { svc: 'mqb',  dir: 'mqtt-module',              title: 'MESSAGE QUEUE BUS',  vulns: 7 },
  MTA:  { svc: 'mail', dir: 'mail-module',              title: 'MAIL TRANSFER',      vulns: 8 },
  /* PKT is a cockpit module like the others but not a fleet-compose rebuild
   * target (no svc/dir).  FILE RETURN is the same whole-challenge job here as
   * on every module; do NOT invent a separate PKT submit path. */
  PKT:  { svc: null,   dir: null,                       title: 'SIGNAL HARPOON',     vulns: 0, fleet: true },
};

export const COMPOSE = 'bridge/fleet-compose.yml';

/* Six phases because there are six facets, and the ratchet steps 60 deg per
 * completed phase, so one refit is exactly one revolution and the cover comes
 * back to the orientation it started in. */
export const PHASES = [
  { n: 1, nm: 'READ',     what: 'read your changes',           state: 'queued' },
  { n: 2, nm: 'BUILD',    what: 'rebuild the service',         state: 'building' },
  { n: 3, nm: 'STOP',     what: 'stop the old one',            state: 'building' },
  { n: 4, nm: 'START',    what: 'start it, wait for a port',   state: 'running' },
  { n: 5, nm: 'CHECK',    what: 'run the standard checks',     state: 'running' },
  { n: 6, nm: 'SECURITY', what: 'run the security checks',     state: 'running' },
];

/* What the player sees: four plain steps over the six phases (the ratchet
 * still turns 60 deg per phase, so the six stay).  Rows exist only while a
 * rebuild is running. */
export const STEPS = [
  { nm: 'Read your changes',   phases: [1] },
  { nm: 'Rebuild the service', phases: [2] },
  { nm: 'Restart it',          phases: [3, 4] },
  { nm: 'Run the checks',      phases: [5, 6] },
];

/* Demo / staff mode is opt-in by URL only: exactly `?demo=1`, on this page or
 * on the cockpit page that embeds it.  No storage is read, so leftover state
 * can never switch it on. */
function demoRequested() {
  const on = w => {
    try { return new URLSearchParams(w.location.search).get('demo') === '1'; }
    catch (e) { return false; }
  };
  if (typeof window === 'undefined') return false;
  if (on(window)) return true;
  try { if (window.parent && window.parent !== window && on(window.parent)) return true; }
  catch (e) { /* cross-origin parent: no demo */ }
  return false;
}

const D2R = Math.PI / 180;

/* one element, no markup strings, ever */
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}


/* ==========================================================================
 * THE HOTSPOT ADAPTER -- five conventions across nine modules, one call site
 * ==========================================================================
 * `mountRefit()` and `mountMast()` want exactly one thing from a module's own
 * hotspot helper: a positioned `.hot` element in that module's own hotspot
 * layer, so the fitting can add its own listeners to it.  All nine modules
 * already RETURN that element.  What differs is the THIRD argument, and the
 * fleet uses four incompatible shapes of it -- read off all nine `module.js`:
 *
 *   hotspot(rect, label, wire)            KVS, MQB, OTA, LOG
 *       `wire` is a WIRER: called ONCE, SYNCHRONOUSLY, with the element.
 *   hotspot(rect, title, onDown)          MTA, PKT, IPM
 *       `onDown` is a HANDLER: called `(ev, el)` on EVERY pointerdown.
 *   hotspot(key, label, onDown, onMove)   FMM
 *       the first argument is a KEY into the module's own props table; FMM
 *       looks the rect up itself, so it cannot be handed a rect at all.
 *   hotspot(rect, label, {click, drag})   DNSM
 *       an options OBJECT; a bare function has neither key, so DNSM wires
 *       nothing and the fitting is dead with no error at all.
 *
 * Handing a wirer to the second shape mis-wires SILENTLY and then THROWS: the
 * "wirer" is invoked with `(PointerEvent, el)` on the first press and
 * `h.addEventListener` is not a method of a PointerEvent.  Handing a rect to
 * FMM's throws inside the module.  Handing one to DNSM's throws nothing and
 * wires nothing, which is worse.  MTA wrote a nine-line local `wireHotspot()`
 * rather than ship that; PKT, IPM, FMM and DNSM would each have written
 * another one.  This is that adapter, ONCE, in the shared file.  A module
 * passes its own `hotspot` exactly as the design always said it should.
 *
 * IT PREFERS THE MODULE'S OWN HELPER whenever the module uses the wirer
 * shape, so KVS, MQB, OTA and LOG produce byte-identical DOM to the builds
 * their recorded numbers came from.  For the other three shapes it builds the
 * same `.hot` element itself, in the module's own `#hots` layer -- which is
 * what MTA's local workaround does, and which is why that workaround is now
 * REMOVABLE.
 *
 * IT DOES NOT ROUTE THROUGH THE MODULE'S HANDLER WRAPPER, and that is
 * deliberate rather than lazy.  MTA's, PKT's and IPM's wrappers clear the
 * module's own `frozen` capture latch on every press; opening the refit port
 * must not restart a module's easing as a side effect.  MTA's local note says
 * so in as many words and it is right.
 *
 * DETECTION IS BEHAVIOURAL, NOT BY NAME.  Parameter names are not a contract
 * and minifiers eat them.  The probe below calls the helper once with a
 * 1 x 1 rect parked off-stage and asks one question -- was my function called
 * synchronously with an element? -- then removes whatever came back.  FMM's
 * shape is separated first, by arity, because it throws before it can answer.
 * The answer is cached per helper function, so this costs one throwaway node
 * per module page, not one per fitting.
 */
const HOTSPOT_KIND = new WeakMap();

/* The module's own hotspot layer.  Every module.js appends to `#hots`; the
 * fallbacks are for a page that renames it, and they never invent a layer with
 * different stacking than the hotspots already on the page. */
function hotsHost(o) {
  const scope = o.layerHost || o.stageEl || null;
  const q = sel => (scope && scope.querySelector && scope.querySelector(sel))
    || (typeof document !== 'undefined' && document.querySelector(sel)) || null;
  const byId = q('#hots');
  if (byId) return byId;
  const one = q('.hot');
  if (one && one.parentNode) return one.parentNode;
  return scope || (typeof document !== 'undefined' ? document.body : null);
}

/* the wirer convention, built here, in the module's own layer */
function ownHotspot(o, rect, label, wire) {
  const d = el('div', 'hot');
  d.style.left = rect.x + 'px'; d.style.top = rect.y + 'px';
  d.style.width = rect.w + 'px'; d.style.height = rect.h + 'px';
  d.title = label;                   /* textContent-safe: never innerHTML */
  const host = hotsHost(o);
  if (host) host.appendChild(d);
  wire(d);
  return d;
}

function hotspotKind(fn, o) {
  if (HOTSPOT_KIND.has(fn)) return HOTSPOT_KIND.get(fn);
  let kind = 'own';
  /* FMM: (key, label, onDown, onMove).  Arity is the only thing that
   * separates it before `P[key].hotspot` throws on a rect. */
  if (fn.length < 4) {
    let called = false, made = null;
    const probe = function (h) { if (h && h.nodeType === 1) called = true; };
    try {
      made = fn({ x: -9999, y: -9999, w: 1, h: 1 }, '', probe);
    } catch (e) { called = false; }
    /* leave nothing behind: the probe node never lived a frame */
    if (made && made.parentNode) made.parentNode.removeChild(made);
    kind = called ? 'wire' : 'own';
  }
  HOTSPOT_KIND.set(fn, kind);
  return kind;
}

/* ==========================================================================
 * TRAP 21, FOR THE FITTINGS THEMSELVES -- `auditScene()` cannot see it
 * ==========================================================================
 * `dress()` forces `THREE.FrontSide`, and a Blender face wound away from the
 * camera is then DELETED with no error and an empty `split.auditScene()`.
 * CONVERSION_BRIEF trap 21 names the exact shapes -- "swept ribbons, FLAGS,
 * tape, curtains, single-quad labels" -- and both fittings are made of them:
 * the port's six iris leaves, the mast's vane, its hazard chevrons, its hatch
 * bars and its scrim bars.  Every one of them is built as a CLOSED PRISM by
 * `refit_port.py` / `status_mast.py` precisely so FrontSide cannot bite, and
 * the only way to KNOW that on the page is a facing audit.
 *
 * The template ships `facingAudit()` and every module has one, but it only
 * ever sees the meshes THAT MODULE dressed -- and MQB and MTA both had no
 * hook on the page at all until they built these fittings, so "the module
 * will run it" was not a fleet fact.  The fittings therefore audit their OWN
 * meshes, from the shared file, with no module cooperation at all, and say so
 * loudly when the answer is not empty.  They also publish themselves on
 * `window.__fittings`, so a harness has ONE name to call across nine pages
 * instead of nine module-specific ones.
 *
 * This does NOT replace the module's own `facingAudit()` and must not be read
 * as covering the module's geometry.  It covers the two fittings.
 */
export function facingAudit(THREE, meshes, camera) {
  const out = [];
  if (!THREE || !camera || !meshes) return out;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const n = new THREE.Vector3(), e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
  for (const mesh of meshes) {
    const mat = mesh && mesh.material;
    if (!mat || mat.side !== THREE.FrontSide) continue;
    const g = mesh.geometry, pos = g && g.attributes && g.attributes.position;
    if (!pos) continue;
    const idx = g.index;
    const tri = ((idx ? idx.count : pos.count) / 3) | 0;
    let away = 0, tot = 0;
    for (let t = 0; t < tri; t += Math.max(1, (tri / 64) | 0)) {
      const i0 = idx ? idx.getX(t * 3) : t * 3;
      const i1 = idx ? idx.getX(t * 3 + 1) : t * 3 + 1;
      const i2 = idx ? idx.getX(t * 3 + 2) : t * 3 + 2;
      a.fromBufferAttribute(pos, i0).applyMatrix4(mesh.matrixWorld);
      b.fromBufferAttribute(pos, i1).applyMatrix4(mesh.matrixWorld);
      c.fromBufferAttribute(pos, i2).applyMatrix4(mesh.matrixWorld);
      n.copy(e1.subVectors(b, a)).cross(e2.subVectors(c, a));
      const area = n.length();
      if (area < 1e-12) continue;
      n.divideScalar(area);
      tot += area;
      if (n.dot(e1.subVectors(camera.position, a)) < 0) away += area;
    }
    if (tot > 0 && away / tot > 0.95) out.push(mesh.name || '(unnamed)');
  }
  return out;
}

/* One name a harness can call on any of the nine pages.  Additive: the port
 * and the mast each register, and neither clobbers the other. */
export function registerFitting(name, api) {
  if (typeof window === 'undefined') return;
  const reg = window.__fittings || (window.__fittings = {});
  reg[name] = api;
  window.__facing = () => {
    const out = [];
    for (const k in reg) {
      if (typeof reg[k].facing !== 'function') continue;
      for (const m of reg[k].facing()) out.push(k + ':' + m);
    }
    return out;
  };
  /* ONE PREDICATE THE CAPTURE HARNESS CAN WAIT ON, on any of the nine pages.
   * `shoot_occlusion.mjs`'s `SETTLE` is a fixed number of milliseconds and a
   * fixed number of milliseconds is a guess: 400 ms is plenty on a module
   * whose live record leaves the vane absent and NOT ENOUGH on one whose vane
   * has somewhere to travel to, and the failure is not a soft one -- the two
   * back grabs are taken mid-ease and `check_occlusion.py` reports a
   * partition FAIL with "must be 0" counters.  FMM NOTES 10.1.
   *
   * `__settle()` fast-forwards every eased transition both fittings own and
   * returns how many it moved.  `__settled()` returns the NAMES of the
   * fittings that are still animating -- empty means the next two frames will
   * be identical -- so a harness can loop until it is empty and record what it
   * waited for, instead of sleeping and hoping. */
  window.__settle = freeze => {
    let moved = 0;
    for (const k in reg)
      if (typeof reg[k].settle === 'function')
        moved += reg[k].settle(freeze) || 0;
    return moved;
  };
  window.__settled = () => {
    const out = [];
    for (const k in reg)
      if (typeof reg[k].settled === 'function' && !reg[k].settled()) out.push(k);
    return out;
  };
}

/* ==========================================================================
 * TRAP: `tick()` BELOW A PAUSED-AT-LOAD LOOP FREEZES BOTH FITTINGS
 * ==========================================================================
 * Neither fitting owns a timer -- that is load-bearing note 2 -- so every
 * animation either of them has runs off `tick(dt, now)` from the module's own
 * `onFrame()`.  A module whose `onFrame()` opens with `if (!running) return;`
 * or `if (frozen) return;` and calls `refit.tick` / `mast.tick` BELOW that
 * gate freezes both fittings on exactly the page a human opens: MQB's bus is
 * paused at load and paused again whenever a control is touched, so the iris
 * would stop half-open and the mast's sweep would stand still, with no error
 * anywhere.  `tick()` goes ABOVE the gate.  `pose()` is what stills the
 * fittings for a capture, and it does it by HIDING them.
 *
 * That is a documentation fix (CONVERSION_BRIEF trap 26), but it is also
 * cheaply detectable, so it is detected.  The watch below costs one rAF chain
 * per mount, warns AT MOST ONCE, and cannot fire during a capture because it
 * requires the fitting to be VISIBLE -- `pose()` hides it.
 */
export function watchTick(what, S, isVisible) {
  if (typeof requestAnimationFrame !== 'function') return;
  let frames = 0;
  const start = S.ticks;
  (function step() {
    if (S.ticks > start) return;                 /* wired: nothing to say */
    if (++frames < 90) { requestAnimationFrame(step); return; }
    if (!isVisible()) return;                    /* posed, or never shown */
    console.warn('[' + what + '] tick() has not been called in 90 frames and '
      + 'the fitting is visible.  It owns no timer, so nothing it draws will '
      + 'move.  Call ' + what + '.tick(dt, now) from onFrame() ABOVE any '
      + '"if (!running) return" / "if (frozen) return" gate -- pose() is what '
      + 'stills it for a capture, not the gate.');
  })();
}


/**
 * Create one hotspot for a fitting, in whatever convention the module uses.
 *
 * @param {object}   o      the mount options (needs `hotspot`, `layerHost`)
 * @param {object}   rect   {x, y, w, h} in 1280x720 stage pixels
 * @param {string}   label  the `title`, plain text
 * @param {function} wire   called ONCE with the element; add listeners here
 * @returns {Element} the hotspot element
 */
export function wireHotspot(o, rect, label, wire) {
  const fn = o && o.hotspot;
  if (typeof fn !== 'function') return ownHotspot(o || {}, rect, label, wire);
  if (hotspotKind(fn, o) === 'wire') {
    let seen = null, ret = null;
    try {
      ret = fn(rect, label, h => { seen = h; wire(h); });
    } catch (e) {
      /* it answered "wirer" and then threw anyway -- fall back rather than
       * leave the fitting unclickable */
      console.warn('[refit] the module hotspot helper threw; building the '
        + 'hotspot directly instead:', e && e.message);
      return ownHotspot(o, rect, label, wire);
    }
    /* the wirer's element, not the return value: a helper that wires and
     * forgets to return is still a wirer, and `wire()` has already run. */
    if (seen) return seen;
    if (ret) return ret;
  }
  return ownHotspot(o, rect, label, wire);
}

function pad(s, n) {
  s = String(s);
  return s.length >= n ? s : s + ' '.repeat(n - s.length);
}


/**
 * Mount the port on a module page.
 *
 * @param {object} o
 *   THREE, scene, camera, split   the module's own three.js objects
 *   S                             the module's parsed scene.json
 *   assetBase                     e.g. '../../assets/KVS/'
 *   code                          'KVS'
 *   load(url)                     the module's GLTF loader promise
 *   dress(mesh)                   the module's own material dressing
 *   hotspot(...)                  the module's own hotspot helper, in
 *                                 WHATEVER convention that module uses --
 *                                 see THE HOTSPOT ADAPTER above; there are
 *                                 four in the fleet and this file handles
 *                                 all of them
 *   layerHost                     the element the #refit layer is appended to
 *   stageEl                       the 1280x720 stage, for pointer maths
 *   fixture                       optional override of the REHEARSAL fixture
 *   dirty                         optional initial dirty boolean
 */
/* A follow-up read failed when it threw, returned nothing, or came back as
 * an error object.  A status record with no live peer is still a reading:
 * power is unknown, and Start stays available. */
function statusReadFailed(followup) {
  if (followup == null) return true;
  if (typeof followup !== 'object') return true;
  if (typeof followup.error === 'string' && followup.error) return true;
  if (followup.ok === false) return true;
  if (followup instanceof Error) return true;
  return false;
}

/* `start` / `stop` / `restart` are true when that button may be pressed.
 * Not released locks all three; the word is NOT YET AVAILABLE.
 * Start is withheld only while powered is on.  Stop and Restart exist only
 * while it is on.  `busy` (a rebuild) or `opInFlight` locks all three and
 * leaves the word alone. */
export function serviceOpState({ powered, released, busy, opInFlight } = {}) {
  const locked = released === false;
  const held = !!busy || !!opInFlight;
  let label = '';
  if (locked) label = 'NOT YET AVAILABLE';
  else if (powered === 'on') label = 'ON';
  else if (powered === 'off') label = 'OFF';
  else if (powered === 'unknown') label = 'POWER ?';
  if (held || locked) return { label, start: false, stop: false, restart: false };
  const on = powered === 'on';
  return { label, start: !on, stop: on, restart: on };
}

/* After STOP.  A stop that succeeded leaves Start usable even when the next
 * status read throws or returns an error.  A refused stop does not count as
 * off: while the service was on, Start stays withheld. */
export function stoppedStillStartable(previousPowered, stopResult, followup) {
  if (!stopResult || stopResult.ok !== true) return previousPowered !== 'on';
  if (statusReadFailed(followup)) return true;
  const powered = followup.live && followup.live.powered;
  return powered !== 'on';
}

/* Stoplight on the port frame.  Linear RGB, same space as
 * `emissive.setRGB(..., LinearSRGBColorSpace)`.  Green is a running
 * container, red is stopped or missing.  Anything else — including
 * `unknown` — is black at intensity 0.  Do not paint a colour for a Docker
 * state that was not read.
 *
 * Go is #007302 and stop is #b00003, both sRGB.  Starting and stopping
 * are a yellow-to-orange pulse, #f0c400 to #e07000, on the ring only.
 * The ring does not use the divided form: color and emissive are the
 * full linear hex, opaque, at intensity 1.  The divided values are only
 * for the well behind the iris.  The lamp is the frame ring.  The iris
 * is not painted.  A starting pulse does not wash the well. */
function srgbByteToLinear(byte) {
  const u = byte / 255;
  return u <= 0.04045 ? u / 12.92 : Math.pow((u + 0.055) / 1.055, 2.4);
}
const FRAME_EMIT = 6;
const PORT_ON_SOLID = {
  r: srgbByteToLinear(0x00),
  g: srgbByteToLinear(0x73),
  b: srgbByteToLinear(0x02),
};
const PORT_OFF_SOLID = {
  r: srgbByteToLinear(0xb0),
  g: srgbByteToLinear(0x00),
  b: srgbByteToLinear(0x03),
};
const PORT_ON = {
  r: PORT_ON_SOLID.r / FRAME_EMIT,
  g: PORT_ON_SOLID.g / FRAME_EMIT,
  b: PORT_ON_SOLID.b / FRAME_EMIT,
};
const PORT_OFF = {
  r: PORT_OFF_SOLID.r / FRAME_EMIT,
  g: PORT_OFF_SOLID.g / FRAME_EMIT,
  b: PORT_OFF_SOLID.b / FRAME_EMIT,
};
const PORT_DARK = { r: 0, g: 0, b: 0 };
const PORT_YELLOW = {
  r: srgbByteToLinear(0xf0),
  g: srgbByteToLinear(0xc4),
  b: srgbByteToLinear(0x00),
};
const PORT_ORANGE = {
  r: srgbByteToLinear(0xe0),
  g: srgbByteToLinear(0x70),
  b: srgbByteToLinear(0x00),
};

export function portPowerLight(powered) {
  if (powered === 'on') return { ...PORT_ON, intensity: 1 };
  if (powered === 'off') return { ...PORT_OFF, intensity: 1 };
  return { ...PORT_DARK, intensity: 0 };
}

/* In-flight Start, Stop, or Restart is yellow until the next read settles.
 * A live restarting or health-starting phase is yellow too.  A failed read
 * is not a start: callers must not pass that as phase or as a leftover op. */
export function lampPowered(powered, phase, op) {
  if (op === 'start' || op === 'stop' || op === 'restart') return 'starting';
  if (phase === 'starting') return 'starting';
  if (powered === 'on' || powered === 'off' || powered === 'unknown') return powered;
  return 'unknown';
}

function mixRgb(a, b, t) {
  const k = t < 0 ? 0 : t > 1 ? 1 : t;
  return {
    r: a.r + (b.r - a.r) * k,
    g: a.g + (b.g - a.g) * k,
    b: a.b + (b.b - a.b) * k,
  };
}

/* The frame ring is the lamp.  The floor and the bore take the divided
 * colour at a fraction so the well agrees, and they sit behind the iris.
 * The ring itself does not: running and stopped both paint color and
 * emissive with the solid hex, force the material opaque, and drop
 * metalness and roughness so the brass cannot show through.  Brass
 * returns when the light is dark.  The iris and the jewel are not passed
 * in.  `pulse` cannot invent a colour. */
function setLinear(target, rgb, colorSpace) {
  if (target && typeof target.setRGB === 'function')
    target.setRGB(rgb.r, rgb.g, rgb.b, colorSpace);
}
function rememberLamp(mm) {
  const ud = mm.userData || (mm.userData = {});
  if (mm.color && ud.color0 == null)
    ud.color0 = { r: mm.color.r, g: mm.color.g, b: mm.color.b };
  if (typeof mm.metalness === 'number' && ud.metal0 == null) ud.metal0 = mm.metalness;
  if (typeof mm.roughness === 'number' && ud.rough0 == null) ud.rough0 = mm.roughness;
  if (ud.transparent0 == null) ud.transparent0 = !!mm.transparent;
  if (typeof mm.opacity === 'number' && ud.opacity0 == null) ud.opacity0 = mm.opacity;
  return ud;
}
function restoreLampBody(mm, colorSpace) {
  const ud = mm.userData || {};
  if (mm.color && ud.color0) setLinear(mm.color, ud.color0, colorSpace);
  if (typeof mm.roughness === 'number' && ud.rough0 != null) mm.roughness = ud.rough0;
  if (ud.transparent0 != null) mm.transparent = ud.transparent0;
  if (typeof mm.opacity === 'number' && ud.opacity0 != null) mm.opacity = ud.opacity0;
  if (typeof mm.metalness === 'number' && ud.metal0 != null) mm.metalness = ud.metal0;
}
function paintSolidLamp(mm, rgb, colorSpace) {
  setLinear(mm.color, rgb, colorSpace);
  setLinear(mm.emissive, rgb, colorSpace);
  mm.emissiveIntensity = 1;
  if (typeof mm.metalness === 'number') mm.metalness = 0;
  if (typeof mm.roughness === 'number') mm.roughness = 1;
  if (mm.transparent) mm.needsUpdate = true;
  mm.transparent = false;
  mm.opacity = 1;
}
function paintLamp(mm, powered, colorSpace, ringPulse) {
  rememberLamp(mm);
  if (powered === 'on') {
    paintSolidLamp(mm, PORT_ON_SOLID, colorSpace);
    return;
  }
  if (powered === 'off') {
    paintSolidLamp(mm, PORT_OFF_SOLID, colorSpace);
    return;
  }
  if (powered === 'starting') {
    const k = ringPulse == null ? 0.5 : ringPulse;
    paintSolidLamp(mm, mixRgb(PORT_YELLOW, PORT_ORANGE, k), colorSpace);
    return;
  }
  restoreLampBody(mm, colorSpace);
  setLinear(mm.emissive, PORT_DARK, colorSpace);
  mm.emissiveIntensity = 0;
}
export function paintThroatLight(glowMats, boreMats, powered, colorSpace, pulse, lampMats, ringPulse) {
  const well = (powered === 'on' || powered === 'off') ? powered : 'unknown';
  const light = portPowerLight(well);
  const glow = light.intensity * (pulse == null ? 1 : pulse);
  const paint = (list, fallback) => {
    for (const mm of list || []) {
      setLinear(mm.emissive, light, colorSpace);
      const max = (mm.userData && mm.userData.emitMax) || fallback;
      mm.emissiveIntensity = glow * max;
    }
  };
  paint(glowMats, 2.2);
  paint(boreMats, 1.4);
  for (const mm of lampMats || []) paintLamp(mm, powered, colorSpace, ringPulse);
  return light;
}

function ensureRefitCss() {
  if (typeof document === 'undefined') return Promise.resolve();
  const links = [...document.querySelectorAll('link[rel="stylesheet"]')];
  const existing = links.find(l => (l.getAttribute('href') || '').includes('refit.css'));
  if (existing && existing.sheet) return Promise.resolve();
  const link = existing || document.createElement('link');
  if (!existing) {
    link.rel = 'stylesheet';
    link.href = new URL('./refit.css', import.meta.url).href;
    document.head.appendChild(link);
  }
  if (link.sheet) return Promise.resolve();
  return new Promise(resolve => {
    link.addEventListener('load', () => resolve(), { once: true });
    link.addEventListener('error', () => resolve(), { once: true });
  });
}

export async function mountRefit(o) {
  const cssReady = ensureRefitCss();
  const THREE = o.THREE;
  const R = (o.S || {}).refit;
  if (!R) throw new Error('mountRefit: scene.json has no "refit" block -- run '
    + 'pipeline/refit_port.py for this module first');
  const CODE = o.code || R.code;
  const FL = FLEET[CODE] || { svc: CODE.toLowerCase(), dir: null, title: CODE, vulns: 0 };
  const W = (o.S.render && o.S.render.w) || 1280;
  const H = (o.S.render && o.S.render.h) || 720;

  /* ================================================================ GEOMETRY */
  const gltf = await o.load(o.assetBase + R.glb);
  const root = new THREE.Group();
  root.name = CODE + '_refit';
  o.scene.add(root);

  const byName = {};
  const meshes = [];
  gltf.scene.traverse(m => { if (m.isMesh) meshes.push(m); });
  for (const m of meshes) byName[m.name] = m;

  /* Every glb in this project is exported in WORLD coordinates, so a moving
   * part is "a pivot at the hinge, with the child translated back by it" and
   * nothing else has to be reconciled.  Same construction as the module's own
   * pivotAt(). */
  const axis = new THREE.Vector3().fromArray(R.axis).normalize();
  function pivotAt(p) {
    const piv = new THREE.Object3D();
    const inner = new THREE.Object3D();
    piv.position.set(p[0], p[1], p[2]);
    inner.position.set(-p[0], -p[1], -p[2]);
    piv.add(inner);
    root.add(piv);
    return { piv, inner };
  }

  const leaves = (R.leaves || []).map(L => {
    const g = pivotAt(L.pivot);
    const m = byName[L.node];
    if (m) g.inner.add(m);
    return g;
  });
  const ratchet = R.ratchet ? pivotAt(R.ratchet.pivot) : null;
  if (ratchet) {
    for (const nm of (R.parts.ratchet || []))
      if (byName[nm]) ratchet.inner.add(byName[nm]);
  }
  const tally = R.tally ? pivotAt(R.tally.hinge) : null;
  const tallyAxis = R.tally
    ? new THREE.Vector3().fromArray(R.tally.axis).normalize() : null;
  if (tally && byName[R.parts.tally]) tally.inner.add(byName[R.parts.tally]);

  /* everything still unparented is static; it goes straight on the root */
  for (const m of meshes) if (!m.parent || m.parent === gltf.scene) root.add(m);

  /* ---- materials.  ORDER MATTERS: the module's dress() assigns the depth
   * composite's onBeforeCompile and then CHAINS attachForeground onto it.
   * Skipping this is the double-blend in trap 15 and auditScene() will name
   * every mesh that missed it. */
  const glowMats = [], jewelMats = [], boreMats = [], frameMats = [];
  let TRIS = 0;
  root.traverse(m => {
    if (!m.isMesh) return;
    const mat = o.dress(m);
    /* TRAP 21.  dress() forces THREE.FrontSide and one-sided Blender geometry
     * does not survive it -- no error, no auditScene() complaint, the prop is
     * simply not there.  The port is built from CLOSED solids for exactly this
     * reason, with ONE exception: the throat bore is looked at from inside, so
     * refit_port.py flips its winding and it is correctly one-sided inward.
     * facingAudit(camera) is the check; run it and expect []. */
    if (/_throat$/.test(m.name)) mat.side = THREE.DoubleSide;
    if (/_glow$/.test(m.name)) glowMats.push(mat);
    if (/_throat$/.test(m.name)) boreMats.push(mat);
    if (/_frame$/.test(m.name)) frameMats.push(mat);
    if (/_jewel$/.test(m.name)) jewelMats.push(mat);
    const g = m.geometry;
    if (g) TRIS += (g.index ? g.index.count : g.attributes.position.count) / 3;
  });
  /* THE JEWEL stays cold white, set here and not inherited.
   *   * WHITE FAMILY ONLY, in code rather than only in a Blender material, so
   *     no future asset can make the jewel green.  FIX_UPLOAD section 4.
   *     That rule is the jewel's, and it is the iris's too: the leaves are
   *     the animation and stay unpainted.  The stoplight is the frame ring
   *     (`portPowerLight`), closed and open.  The old white-only rule on
   *     the floor is superseded for that ring.
   *   * A Blender material with Emission Strength 0 round-trips through glTF
   *     as emissive BLACK.  Driving emissiveIntensity on a black emissive
   *     multiplies zero.  The jewel's colour is set here so its intensity is
   *     the only variable.  The floor and the bore start black: an unread
   *     Docker state must not inherit the asset's white, and tick() sets
   *     green or red only once `S6.power.powered` is on or off. */
  const COLD = [0.78, 0.84, 0.95];
  const setCold = mm => mm.emissive.setRGB(COLD[0], COLD[1], COLD[2],
                                           THREE.LinearSRGBColorSpace);
  const setDark = mm => mm.emissive.setRGB(0, 0, 0, THREE.LinearSRGBColorSpace);
  for (const mm of glowMats) { setDark(mm); mm.emissiveIntensity = 0; mm.userData.emitMax = 2.2; }
  /* The bore is the same colour as the floor, at a fraction, behind the
   * iris.  It is not the lamp and it is not painted onto the leaves. */
  for (const mm of boreMats) { setDark(mm); mm.emissiveIntensity = 0; mm.userData.emitMax = 1.4; }
  /* The stoplight.  The frame ring does not move and does not cover the
   * iris, so the colour stays obvious while the animation stays steel. */
  for (const mm of frameMats) {
    setDark(mm);
    mm.emissiveIntensity = 0;
    mm.userData.emitMax = FRAME_EMIT;
    mm.userData.lamp = true;
    if (typeof mm.metalness === 'number') mm.userData.metal0 = mm.metalness;
  }
  for (const mm of jewelMats) { setCold(mm); mm.emissiveIntensity = 0; }

  /* ================================================================ THE LAYER */
  await cssReady;
  const layer = el('div');
  layer.id = 'refit';
  (o.layerHost || document.body).appendChild(layer);
  const stageEl = o.stageEl || o.layerHost;

  const dk = el('div', 'docket');
  dk.hidden = true;
  layer.appendChild(dk);
  dk.appendChild(el('div', 'punch'));
  dk.appendChild(el('div', 'tag'));

  /* Demo / staff mode: sample data only, always labelled.  See demoRequested(). */
  const DEMO = demoRequested();
  const SAMPLE = DEMO || !!o.fixture;

  const h1 = el('h1');
  const hTitle = el('span', null, 'REFIT PORT');
  const hMode = el('span', 'mode', 'DEMO DATA');
  hMode.title = 'Sample numbers for staff demos — not your real results';
  hMode.hidden = !SAMPLE;
  const hNo = el('span', 'no', '');
  hNo.hidden = !SAMPLE;
  h1.appendChild(hTitle); h1.appendChild(hMode); h1.appendChild(hNo);
  dk.appendChild(h1);

  const kv = el('div', 'kv');
  dk.appendChild(kv);
  const kvVal = {}, kvLab = {};
  for (const [k, label] of [['sub', 'MODULE'], ['img', 'SERVICE'],
                            ['run', 'BUILT'], ['wb', 'CHANGES']]) {
    kvLab[k] = el('span', 'k', label);
    kv.appendChild(kvLab[k]);
    kvVal[k] = el('span', 'v', '');
    kv.appendChild(kvVal[k]);
  }
  const files = el('div', 'files');
  dk.appendChild(files);

  /* ---- REBUILD THIS SERVICE. Real POST /api/rebuild. Not a grade. */
  dk.appendChild(el('hr'));
  const rbBox = el('div', 'fr');
  rbBox.appendChild(el('div', 'sec', 'Rebuild this service'));
  const rbWarn = el('p', 'rebuild-warn', rebuildAllowed(CODE)
    ? 'Replacing this service drops data that lived only inside the container.'
    : CODE + ' has no service of its own, so there is nothing to rebuild here.');
  rbBox.appendChild(rbWarn);
  const rbStatus = el('p', 'rebuild-status', '');
  rbBox.appendChild(rbStatus);

  /* The step rows exist only while a rebuild is running (they were six
   * always-painted grey rows).  Idle, the docket shows nothing of them. */
  const phBox = el('div', 'steps');
  phBox.hidden = true;
  const phEls = STEPS.map((p, i) => {
    const row = el('div', 'ph pend');
    row.appendChild(el('span', 'n', i + 1));
    row.appendChild(el('span', 'nm', p.nm));
    const st = el('span', 'st', '');
    row.appendChild(st);
    phBox.appendChild(row);
    return { row, st };
  });
  rbBox.appendChild(phBox);

  /* Check results get their own lines rather than a right-hand column: a
   * column clipped the one word that matters ("Check couldn't finish"), which
   * is what keeps "break it so the exploits stop" from reading as clean. */
  const sum = el('div', 'files');
  sum.setAttribute('aria-live', 'polite');
  rbBox.appendChild(sum);

  const logBox = el('div', 'log');
  logBox.hidden = true;
  rbBox.appendChild(logBox);
  const jobLog = el('pre', 'log');
  jobLog.hidden = true;
  rbBox.appendChild(jobLog);
  dk.appendChild(rbBox);

  /* Grade controls are not part of this docket. File return stays unreachable. */
  const frHelp = el('div', 'help', '');
  const frLog = el('div', 'log');
  frLog.hidden = true;
  const bRet = el('button', 'ret', '');
  bRet.hidden = true;
  bRet.type = 'button';

  const btns = el('div', 'btns');
  const pwrState = el('div', 'pwr-state', '');
  const bStart = el('button', null, 'Start');
  const bStop = el('button', null, 'Stop');
  const bRestart = el('button', null, 'Restart');
  bStart.title = 'Start this service';
  bStop.title = 'Stop this service';
  bRestart.title = 'Restart this service';
  const bGo = el('button', 'go', 'Rebuild & restart');
  bGo.hidden = !rebuildAllowed(CODE);
  bGo.title = 'Replace this service. Data that lived only inside the container is dropped.';
  const bSeal = el('button', null, 'Close');
  bSeal.title = 'Close this panel (Esc)';
  for (const b of [bStart, bStop, bRestart, bGo, bSeal]) b.type = 'button';
  btns.appendChild(pwrState);
  btns.appendChild(bStart);
  btns.appendChild(bStop);
  btns.appendChild(bRestart);
  btns.appendChild(bGo);
  btns.appendChild(bSeal);
  dk.appendChild(btns);

  /* ================================================================== STATE */
  const S6 = {
    /* `dirtyKnown` is not pedantry.  Nothing on a statically-served page has
     * read the workbench, and printing "clean -- nothing to commit" would be
     * asserting a fact no one measured.  The jewel's idle breath is driven by
     * `dirty`, so an unmeasured default of `true` would also put a permanent
     * attractor on every module.  Unknown stays dark and says so. */
    open: false, phase: 0, run: null, dirty: !!o.dirty,
    dirtyKnown: typeof o.dirty === 'boolean',
    result: null, applied: false, jobs: 0, t: 0, openT: 0,
    ratchetDeg: 0, ratchetWant: 0, tallyUp: 0,
    /* capture only, never set by a page -- see settle() */
    frozen: false,
    /* not animation state: the only thing `watchTick()` reads */
    ticks: 0,
    /* sibling of `run`.  Never drives PHASES / jewel / tally / ratchet. */
    fileReturn: {
      live: false, chromeKnown: false, chromeGen: 0,
      configured: false, loggedIn: false, submissionsOpen: null,
      moduleCount: 0, jobId: null, status_name: '', packaged: null,
      submission: null, err: null, pollAcc: 0, elapsed: 0,
      fetching: false, inFlight: false, done: false, pollNow: false,
      rehearsed: false, log: [],
    },
    rebuild: {
      id: '', job: null, error: '', busy: false,
      polling: false, acc: 0, fetching: false,
    },
    /* Power word for this mounted code.  Unknown until moduleStatus answers.
     * A failed read keeps the last word; it does not lock the row. */
    power: {
      powered: 'unknown', released: true, op: null, phase: '',
      acc: 0, fetching: false, seq: 0, known: false,
    },
  };
  /* Real data path: the coordinator's `/api/...` answers and `status.json`.
   * The sample fixture below is ONLY for demo mode (or a caller's own
   * `fixture:`); normal play gets an empty one, so nothing here can paint a
   * made-up build time, file list or check result. */
  const fixture = o.fixture || (DEMO ? defaultFixture(CODE, FL) : emptyFixture());

  /* ------------------------------------------------------------ the docket */
  function paintHead() {
    if (SAMPLE) hNo.textContent = 'sample';
    kvVal.sub.textContent = CODE + '   ' + FL.title;
    const showSample = SAMPLE && fixture.image;
    kvLab.img.textContent = showSample ? 'IMAGE' : 'SERVICE';
    kvLab.run.hidden = kvVal.run.hidden = !showSample;
    if (showSample) {
      /* DEMO DATA: labelled in the heading; nothing here is measured. */
      kvVal.img.textContent = fixture.image.tag;
      kvLab.run.textContent = 'BUILT';
      kvVal.run.textContent = fixture.image.built
        + '   sha ' + fixture.image.sha
        + (fixture.running ? '' : '   (not running)');
    } else {
      /* NO SERVICE IS A REAL ANSWER, not a missing one: PKT has none in
       * `bridge/fleet-compose.yml`.  Other modules name theirs; no image tag
       * or build time is invented, because nothing here has read either. */
      kvVal.img.textContent = FL.svc
        ? FL.svc + ' (rebuilt on this machine)'
        : 'none — nothing of its own to rebuild';
    }
    /* The workbench line says only what was measured.  `dirty` comes from the
     * status record (or a `status:dirty` push); nothing else reads files.
     * DEMO DATA ignores it entirely, so sample and real state never mix. */
    const sampleFiles = SAMPLE && fixture.files.length > 0;
    if (sampleFiles) {
      kvVal.wb.textContent = fixture.files.length + ' file'
        + (fixture.files.length === 1 ? '' : 's') + ' amended (sample)';
    } else if (!S6.dirtyKnown) {
      kvVal.wb.textContent = 'No changes detected yet';
    } else {
      kvVal.wb.textContent = S6.dirty
        ? 'Changes found since the last build'
        : 'No changes since the last build';
    }
    while (files.firstChild) files.removeChild(files.firstChild);
    if (sampleFiles) {
      for (const f of fixture.files) {
        const row = el('div', 'f');
        row.appendChild(el('span', 'p', f.path));
        row.appendChild(el('span', 'add', '+' + f.add));
        row.appendChild(el('span', 'del', '-' + f.del));
        files.appendChild(row);
      }
    }
    files.hidden = !files.firstChild;
    /* Rebuilding an unchanged module is occasionally exactly what you want, so
     * it is never disabled; the label just says so.  FIX_UPLOAD 5.3. */
    if (!rebuildAllowed(CODE)) {
      bGo.hidden = true;
      bGo.disabled = true;
    } else if (S6.rebuild.busy || S6.run) {
      bGo.hidden = false;
      bGo.disabled = true;
      bGo.textContent = 'Rebuilding…';
    } else {
      bGo.hidden = false;
      bGo.disabled = false;
      bGo.textContent = 'Rebuild & restart';
    }
    paintPower();
  }

  function paintPower() {
    const st = serviceOpState({
      powered: S6.power.powered,
      released: S6.power.released,
      busy: !!(S6.rebuild.busy || S6.run),
      opInFlight: !!S6.power.op,
    });
    pwrState.textContent = st.label;
    if (S6.power.released === false) pwrState.setAttribute('data-powered', 'locked');
    else if (S6.power.powered) pwrState.setAttribute('data-powered', S6.power.powered);
    else pwrState.removeAttribute('data-powered');
    bStart.disabled = !st.start;
    bStop.disabled = !st.stop;
    bRestart.disabled = !st.restart;
  }

  function adoptPower(d) {
    const live = d && d.live;
    if (!live || typeof live !== 'object') {
      S6.power.powered = 'unknown';
      S6.power.released = true;
      S6.power.phase = '';
      return;
    }
    const p = live.powered;
    S6.power.powered = (p === 'on' || p === 'off' || p === 'unknown') ? p : 'unknown';
    S6.power.phase = live.containerPhase === 'starting' ? 'starting' : '';
    S6.power.released = !(live.released === false
      || live.availability === 'not_yet_available');
  }

  function applyStopFollowup(previousPowered, previousReleased, result, followup) {
    const startable = stoppedStillStartable(previousPowered, result, followup);
    const failedRead = statusReadFailed(followup);
    if (startable && result && result.ok === true && failedRead) {
      S6.power.powered = 'off';
      S6.power.released = previousReleased !== false;
      S6.power.phase = '';
      return;
    }
    if (startable && !failedRead) {
      adoptPower(followup);
      return;
    }
    /* Refused stop, or a follow-up that still says on.  Keep the previous
     * word when the read failed or when adopting it would paint OFF after
     * a stop the service refused. */
    if (!result || result.ok !== true) {
      S6.power.powered = previousPowered;
      S6.power.released = previousReleased;
      return;
    }
    if (!failedRead) adoptPower(followup);
  }

  function paintRebuild() {
    const rb = S6.rebuild;
    const job = rb.job;
    if (rb.error) rbStatus.textContent = rb.error;
    else if (job) rbStatus.textContent = rebuildStatusText(job);
    else rbStatus.textContent = '';
    const tail = rebuildLogText(job);
    jobLog.hidden = !tail;
    jobLog.textContent = tail;
  }

  function stepState(i) {
    const ph = STEPS[i].phases, last = ph[ph.length - 1];
    if (S6.run && ph.includes(S6.phase)) return 'run';
    if (S6.phase > last || (!S6.run && S6.phase >= last && S6.result)) {
      return S6.result && !S6.result.preview && S6.result.failedAt
        && ph.includes(S6.result.failedAt) ? 'no' : 'ok';
    }
    return 'pend';
  }

  function paintPhases() {
    /* rows only while a rebuild is running; idle shows a compact summary */
    phBox.hidden = !S6.run;
    STEPS.forEach((p, i) => {
      const e = phEls[i];
      const st = stepState(i);
      /* a preview step is never painted as a finished (green) one */
      e.row.className = 'ph ' + ((!SAMPLE && st === 'ok') ? 'prev' : st);
      e.st.textContent = stepNote(st);
    });
    while (sum.firstChild) sum.removeChild(sum.firstChild);
    const r0 = S6.result;
    if (r0 && r0.preview) {
      sum.appendChild(el('div', null,
        'Preview only — nothing was rebuilt, restarted or checked.'));
    }
    if (r0 && r0.tests) {
      const u = r0.tests.unit, v = r0.tests.vuln;
      const pre = SAMPLE ? 'DEMO DATA · ' : '';
      /* qualitative only: never paint vuln n/m, totals or remaining. */
      if (u && (u.fail > 0 || u.pass > 0)) {
        sum.appendChild(el('div', null, pre + (u.fail > 0
          ? 'Standard checks: some failed' : 'Standard checks: passed')));
      }
      if (v) {
        /* each fact on its own line: "still fires" must never hide "couldn't
         * finish", and neither may read as clean. */
        let any = false;
        const line = (text, title) => {
          const d = el('div', null, pre + text);
          if (title) d.title = title;
          sum.appendChild(d); any = true;
        };
        if (v.fired > 0) line('Security checks: some problems still show up');
        if (v.inconclusive > 0)
          line('Security checks: Check couldn\'t finish — no result yet',
            'Neither a pass nor a fail. The check ran and could not decide.');
        if (!any && v.closed > 0)
          line('Security checks: no problems showed up in this run');
        if (!any) line('Security checks: not run');
      }
    }
    logBox.hidden = !(S6.result && S6.result.log && S6.result.log.length);
    if (!logBox.hidden) {
      while (logBox.firstChild) logBox.removeChild(logBox.firstChild);
      for (const line of S6.result.log.slice(-12))
        logBox.appendChild(el('div', null, line));
    }
    sum.hidden = !sum.firstChild;
  }

  function frHelper() {
    const fr = S6.fileReturn;
    if (fr.inFlight && fr.jobId)
      return 'Job ' + fr.jobId + ' · ' + plainStatus(fr.status_name || 'QUEUED');
    if (fr.inFlight) return 'Submitting…';
    if (!fr.chromeKnown) return 'Checking the connection to the judges…';
    if (!fr.live)
      return 'Preview only — can\'t reach the judges from this page, so nothing will be sent.';
    if (!fr.configured) return 'Grading isn\'t set up on this machine.';
    if (!fr.loggedIn) return 'Sign in first to submit.';
    if (fr.submissionsOpen === false)
      return 'Submissions are closed by the organizers.';
    return 'This panel does not submit a grade.';
  }

  function frAllowed() {
    const fr = S6.fileReturn;
    if (!fr.live) return true;
    return !!(fr.configured && fr.loggedIn && fr.submissionsOpen !== false);
  }

  function frCanClick() {
    const fr = S6.fileReturn;
    if (fr.inFlight) return false;
    return frAllowed();
  }

  function paintFileReturn() {
    const fr = S6.fileReturn;
    frHelp.textContent = frHelper();
    if (fr.inFlight) {
      bRet.disabled = true;
      bRet.textContent = '';
    } else {
      bRet.disabled = true;
      bRet.textContent = '';
    }
    const lines = (fr.log || []).slice(-12);
    frLog.hidden = !lines.length;
    if (!frLog.hidden) {
      while (frLog.firstChild) frLog.removeChild(frLog.firstChild);
      for (const line of lines) frLog.appendChild(el('div', null, line));
    }
  }

  function logFr(line) {
    S6.fileReturn.log.push(String(line));
  }

  /* Right-hand note on a running step.  A preview never says "done": nothing
   * was done.  Only demo data may claim a finished step, and it is labelled. */
  function stepNote(st) {
    if (st === 'pend') return '';
    if (!SAMPLE) return st === 'run' ? 'preview…' : 'preview';
    if (st === 'run') return '…';
    return st === 'no' ? 'failed' : 'done';
  }

  /* harness status names, in words */
  function plainStatus(name) {
    return ({ SUBMITTED: 'Waiting in line', QUEUED: 'Waiting in line',
              PENDING: 'Being graded', RUNNING: 'Being graded',
              COMPLETE: 'Finished', FAILED: 'Grading error' })[name] || name;
  }

  /* --------------------------------------------------------- the docket pose */
  /* Every declared readout's screen rect, so the docket can be told to stay
   * off the instrument's own text rather than merely to stay on the stage.
   * "It is not a modal: the instrument stays visible beside it" is the design;
   * a 520 px panel dropped on the transcript is not that. */
  const RECTS = (o.S.text_planes || [o.S.text_plane] || [])
    .filter(t => t && t.corners_px)
    .map(t => {
      const c = t.corners_px, ks = Object.keys(c);
      return [Math.min(...ks.map(k => c[k].x)), Math.max(...ks.map(k => c[k].x)),
              Math.min(...ks.map(k => c[k].y)), Math.max(...ks.map(k => c[k].y))];
    });

  /* THE MODULE'S OWN CONTROL HOTSPOTS ARE KEEP-OUT TOO, and leaving them out
   * was a measured defect rather than a theoretical one.  On MQB the winning
   * candidate covered 42.2 % of the `PATCH BAY` hotspot and 28.3 % of
   * `BUS TRAFFIC`: both stayed reachable at their EDGES, but a click at the
   * CENTRE of a control -- where a player clicks -- was swallowed while the
   * port was open.  "It is not a modal: the instrument stays visible beside
   * it" has to mean OPERABLE beside it.  `mast.js`'s caption solver has
   * counted these since it was written; this one had not.  MQB NOTES 13.9.
   *
   * A COVERED CENTRE COSTS THE CONTROL'S WHOLE AREA, NOT THE OVERLAP, and
   * that is the part that actually fixes it.  Scoring controls by plain
   * overlap is not enough: measured on MQB, it moves the docket off PATCH BAY
   * and straight onto BUS TRAFFIC's centre instead, trading 42.2 % + 28.3 %
   * for 43.4 % of a different control and swallowing a centre either way.
   * Losing the middle of a control is not a fraction of a defect, so it is
   * not scored as one.  Measured on all three built modules:
   *
   *     objective            KVS            MQB            MTA
   *     readouts + port      (12,346) 1     (314,390) 1    (12,185) 0
   *     + control overlap    (12,346) 1     (12,336)  1    (12,185) 0
   *     + covered centre     (12,346) 0*    (12,390)  0    (12,185) 0
   *                          ^ unchanged    ^ fixed
   *
   *   (the trailing figure is CONTROL CENTRES SWALLOWED.  KVS is 1 under every
   *    objective and stays exactly where it was: every one of its five
   *    candidates buries one control's centre, because a 520 px docket on a
   *    1280 px stage cannot miss all three, so nothing here can help it and
   *    nothing here disturbs it.  Its `PUNCHED TAPE` was 100 % covered before
   *    this change and is 100 % covered after it.) */
  const CTRLS = [];
  for (const k in (o.S.props || {})) {
    const r = (o.S.props[k] || {}).hotspot;
    if (r) CTRLS.push([r.x, r.x + r.w, r.y, r.y + r.h]);
  }

  function placeDocket() {
    if (!stageEl) return;
    const c = new THREE.Vector3().fromArray(R.centre).project(o.camera);
    const cx = (c.x * 0.5 + 0.5) * W, cy = (0.5 - c.y * 0.5) * H;
    const w = dk.offsetWidth || 520, h = dk.offsetHeight || 420;
    const clamp = (x, y) => [Math.max(12, Math.min(W - w - 12, x)),
                             Math.max(12, Math.min(H - h - 12, y))];
    /* anchored to the port's projected centre, pushed toward frame centre --
     * then the candidate that covers the least declared readout wins, ties
     * broken by proximity to the port so the panel still reads as coming out
     * of it. */
    const cands = [[cx + 40, cy - h - 26], [cx - w - 40, cy - h - 26],
                   [cx + 40, cy - h / 2], [cx - w - 40, cy - h / 2],
                   [cx - w / 2, cy - h - 26]];
    /* The port itself is the FIRST thing the docket must not sit on: the
     * gesture the player is learning is "the star retracts and a lit throat
     * opens", and a docket over the port hides the half of it that is the
     * point.  Weighted 4x the readouts, which are merely nice to keep. */
    const PORT = [hs.x - 6, hs.x + hs.w + 6, hs.y - 6, hs.y + hs.h + 6];
    let best = null;
    for (const cand of cands) {
      const [x, y] = clamp(cand[0], cand[1]);
      const over = r => Math.max(0, Math.min(x + w, r[1]) - Math.max(x, r[0]))
                      * Math.max(0, Math.min(y + h, r[3]) - Math.max(y, r[2]));
      let cover = 4 * over(PORT);
      for (const r of RECTS) cover += over(r);
      for (const r of CTRLS) {
        const mx = (r[0] + r[1]) / 2, my = (r[2] + r[3]) / 2;
        cover += (mx >= x && mx <= x + w && my >= y && my <= y + h)
          ? (r[1] - r[0]) * (r[3] - r[2])       /* centre buried: all of it */
          : over(r);                            /* clipped: what is clipped */
      }
      const near = Math.hypot(x + w / 2 - cx, y + h - cy);
      if (!best || cover < best[0] - 1 || (cover < best[0] + 1 && near < best[1]))
        best = [cover, near, x, y];
    }
    dk.style.left = best[2] + 'px';
    dk.style.top = best[3] + 'px';
    announceDocket();
  }

  /* THE DOCKET IS A LIVE KEEP-OUT RECT FOR ANYTHING ELSE ON THE STAGE, and it
   * has to say so out loud.  `mast.js`'s `keepOut()` has always counted
   * `#refit .docket`, but nothing re-ran its solver when the docket appeared,
   * moved or went away -- invisible on KVS, where the docket lands on the LEFT
   * half and the caption on the right, and wrong on MQB, where the docket
   * lands to the port's RIGHT and the caption's first choice is underneath it.
   * MQB fixed it module-side with a MutationObserver; six more modules would
   * each have needed one.  One event, on window, from the file that owns the
   * docket.  MQB NOTES section 13 item 8. */
  let dkSig = '';
  function announceDocket() {
    if (typeof dispatchEvent !== 'function') return;
    const detail = { code: CODE, open: !dk.hidden,
                     x: parseFloat(dk.style.left) || 0,
                     y: parseFloat(dk.style.top) || 0,
                     w: dk.offsetWidth || 0, h: dk.offsetHeight || 0 };
    /* ONLY WHEN IT ACTUALLY MOVED.  `tick()` re-runs `placeDocket()` on EVERY
     * FRAME while the port is open -- the docket is anchored to a projected
     * point, so it has to -- and an event per frame would make every listener
     * pay for a solve 60 times a second.  This is the same reasoning as
     * `refresh()`'s signature check: repaint when something moved, not when
     * something might have. */
    const sig = detail.open + '|' + detail.x + '|' + detail.y + '|'
              + detail.w + '|' + detail.h;
    if (sig === dkSig) return;
    dkSig = sig;
    dispatchEvent(new CustomEvent('refit:docket', { detail }));
  }

  /* ================================================================ HOTSPOT */
  /* `wireHotspot`, not `o.hotspot` -- five conventions in the fleet and only
   * four of them are this one.  See THE HOTSPOT ADAPTER at the top. */
  const hs = R.hotspot;
  const hot = wireHotspot(o, { x: hs.x, y: hs.y, w: hs.w, h: hs.h },
    'REFIT PORT — click to open', h => {
      h.addEventListener('click', () => { toggle(); });
    });

  /* ================================================================ GESTURE */
  function toggle() { S6.open ? seal() : open(); }

  function open() {
    if (S6.open || !root.visible) return;
    S6.open = true;
    S6.openT = 0;
    refreshDirty();
    paintHead();
    paintPhases();
    paintRebuild();
    readPower();
    dk.hidden = false;
    dk.classList.add('rise');
    placeDocket();
    /* two frames, so the transition has a start value to run from */
    requestAnimationFrame(() => requestAnimationFrame(() => {
      dk.classList.remove('rise');
      placeDocket();
    }));
    emit('idle');
  }

  function seal() {
    if (!S6.open) return;
    S6.open = false;
    S6.openT = 0;
    dk.classList.add('rise');
    dk.hidden = true;
    /* closing is half of "when the docket opens or closes": a caption that
     * moved out of the docket's way has to be allowed back. */
    announceDocket();
  }

  function onKey(e) { if (e.key === 'Escape' && S6.open) seal(); }
  addEventListener('keydown', onKey);
  bSeal.addEventListener('click', () => seal());
  bGo.addEventListener('click', () => { startRebuild(); });
  bStart.addEventListener('click', () => { onPower('start'); });
  bStop.addEventListener('click', () => { onPower('stop'); });
  bRestart.addEventListener('click', () => { onPower('restart'); });

  /* The throat light reads this word while the iris is closed, so the
   * poll runs whenever the port is on screen — not only while the docket
   * is open.  moduleStatus prefers the cockpit's already-fetched status
   * (`parent.__cockpit.status`); this is not a second Docker lookup.
   * No private timer: tick() accumulates dt, same as the rebuild poll. */
  function tickPower(dt) {
    if (!root.visible || S6.power.op || S6.power.fetching) return;
    S6.power.acc += dt;
    if (S6.power.known && S6.power.acc < 5) return;
    S6.power.acc = 0;
    readPower();
  }

  async function readPower() {
    if (dead || !root.visible || S6.power.fetching || S6.power.op) return;
    S6.power.fetching = true;
    const seq = ++S6.power.seq;
    let followup;
    try {
      followup = await moduleStatus(CODE, o.statusUrl);
    } catch (e) {
      followup = e instanceof Error ? e : { error: 'status read failed' };
    } finally {
      S6.power.fetching = false;
    }
    if (dead || seq !== S6.power.seq || S6.power.op) return;
    if (statusReadFailed(followup)) {
      if (!S6.power.known) {
        S6.power.powered = 'unknown';
        S6.power.released = true;
        S6.power.phase = '';
      }
    } else {
      adoptPower(followup);
    }
    S6.power.known = true;
    if (S6.open) paintPower();
  }

  async function onPower(op) {
    if (S6.power.op || !root.visible) return;
    const gate = serviceOpState({
      powered: S6.power.powered,
      released: S6.power.released,
      busy: !!(S6.rebuild.busy || S6.run),
      opInFlight: false,
    });
    if (op === 'start' && !gate.start) return;
    if (op === 'stop' && !gate.stop) return;
    if (op === 'restart' && !gate.restart) return;
    if (op === 'restart') {
      try {
        if (!window.confirm('RESTART ' + CODE + '?')) return;
      } catch (e) { return; }
    }
    const previousPowered = S6.power.powered;
    const previousReleased = S6.power.released;
    S6.power.op = op;
    S6.power.seq++;
    paintPower();
    let result;
    try {
      result = await power(CODE, op);
    } catch (e) {
      result = { ok: false, error: 'power failed' };
    }
    /* The embedded page reads the parent cockpit's last poll. Refresh that
     * poll before adopting it, or a stop that worked still paints ON. */
    try {
      if (window.parent && window.parent !== window && window.parent.__cockpit
          && typeof window.parent.__cockpit.bumpLive === 'function')
        await window.parent.__cockpit.bumpLive();
    } catch (e) { /* no parent / cross-origin */ }
    let followup;
    try {
      followup = await moduleStatus(CODE, o.statusUrl);
    } catch (e) {
      followup = e instanceof Error ? e : { error: 'status read failed' };
    }
    if (dead || !root.visible) {
      S6.power.op = null;
      return;
    }
    S6.power.op = null;
    if (op === 'stop') {
      applyStopFollowup(previousPowered, previousReleased, result, followup);
    } else if (!statusReadFailed(followup)) {
      adoptPower(followup);
    } else {
      S6.power.phase = '';
    }
    S6.power.known = true;
    paintPower();
    if (!(result && result.ok)) return;
    dispatchEvent(new CustomEvent('live:' + CODE, { detail: { code: CODE, op } }));
  }

  async function startRebuild() {
    const rb = S6.rebuild;
    if (!rebuildAllowed(CODE) || rb.busy) return;
    rb.busy = true;
    rb.error = '';
    rb.job = null;
    rb.id = '';
    rb.polling = false;
    paintHead();
    paintRebuild();
    rbStatus.textContent = 'Sending rebuild request';
    try {
      const { res, body } = await postRebuild(CODE);
      if (dead) return;
      if (!res.ok || !body || !body.ok) {
        rb.error = (body && (body.error || body.message)) || 'Rebuild was refused';
        rb.busy = false;
        paintHead();
        paintRebuild();
        return;
      }
      const job = rebuildJob(body);
      rb.job = job;
      rb.id = rebuildJobId(body);
      if (rb.id && !rebuildTerminal(job)) {
        rb.polling = true;
        rb.acc = 1;
      } else {
        rb.busy = false;
        rb.polling = false;
      }
      paintHead();
      paintRebuild();
    } catch (err) {
      if (dead) return;
      rb.error = 'Rebuild request failed';
      rb.busy = false;
      rb.polling = false;
      paintHead();
      paintRebuild();
    }
  }

  function tickRebuild(dt) {
    const rb = S6.rebuild;
    if (!rb.polling || !rb.id || rb.fetching) return;
    rb.acc += dt;
    if (rb.acc < 1) return;
    rb.acc = 0;
    rb.fetching = true;
    const id = rb.id;
    getRebuild(id).then(({ body }) => {
      rb.fetching = false;
      if (dead || rb.id !== id) return;
      const job = rebuildJob(body);
      rb.job = job;
      if (rebuildTerminal(job)) {
        rb.polling = false;
        rb.busy = false;
      }
      if (S6.open) { paintHead(); paintRebuild(); }
    }).catch(() => { rb.fetching = false; });
  }

  /* =============================================================== THE STUB
   * The deploy is DELIBERATELY NOT WIRED.  This prints what it would run and
   * emits the event; nothing reaches Docker.  FIX_UPLOAD 5.1 assumption 1: the
   * cockpit is served by `live3d/run.sh`, a static file server, which cannot
   * reach a Docker socket.  `bridge/server.py` in the challenge repo already
   * speaks to the live fleet -- pointing this at it is a separate decision
   * with real consequences and is not taken here. */
  function commands() {
    const out = [];
    if (FL.fleet) {
      out.push('# ' + CODE + ' is not a fixable module; a FLEET refit is an '
        + 'open question for a human (FIX_UPLOAD section 7)');
      return out;
    }
    out.push('docker compose -f ' + COMPOSE + ' up --build -d ' + FL.svc);
    out.push('( cd ' + FL.dir + '/unit_tests && ./run-in-docker.sh )');
    return out;
  }

  function commit() {
    /* rebuild only.  Never POST /api/submit.  FILE RETURN is the other verb. */
    if (S6.run) return;
    S6.jobs += 1;
    S6.result = null;
    S6.phase = 0;
    S6.run = { t: 0, per: 0.42 };
    S6.ratchetWant = 0;
    const cmds = commands();
    console.info('%c[refit:' + CODE + '] PREVIEW -- no container was touched.'
      + '  These are the commands a wired port would run:', 'color:#c9a227');
    for (const c of cmds) console.info('    ' + c);
    paintHead();
    paintPhases();
    emit('queued');
  }

  function finish() {
    if (!SAMPLE) {
      /* PREVIEW: nothing was rebuilt, so there is no result to report and no
       * success to claim.  `applied`, `dirty` and the tally flag stay exactly
       * as they were; the event goes out as `idle`, never `done`. */
      S6.result = { failedAt: 0, preview: true, log: [] };
      S6.run = null;
      paintHead();
      paintPhases();
      emit('idle');
      return;
    }
    const f = fixture.result;
    S6.result = {
      failedAt: f.failedAt || 0,
      tests: f.tests,
      log: f.log || [],
    };
    S6.run = null;
    S6.applied = !f.failedAt;
    if (S6.applied) { S6.dirty = false; S6.tallyUp = 1; }
    paintHead();
    paintPhases();
    emit(S6.applied ? 'done' : 'error');
  }

  /* ========================================================== FILE RETURN
   * Whole challenge, one job.  Never calls commands().  Never steps the
   * ratchet, jewel, tally, or PHASES.  Track 01 merge: replace the
   * same-origin fetch('/api/submit') and fetch('/api/submissions/') calls
   * below with the shared client.  No api.js in this track. */
  const FR_POLL = 5;
  const FR_LIMIT = 90 * 60;
  let dead = false;

  function apiJson(url, opt) {
    return fetch(url, opt).then(async r => {
      const t = await r.text();
      try { return JSON.parse(t); }
      catch (e) { throw new Error('not json'); }
    });
  }

  function emitFileReturn() {
    const fr = S6.fileReturn;
    const sub = fr.submission;
    const detail = {
      jobId: fr.jobId,
      status_name: fr.status_name || '',
      passed: sub ? sub.passed : null,
      rehearsal: !fr.live || !!fr.rehearsed,
      ts: Date.now(),
    };
    dispatchEvent(new CustomEvent('file-return', { detail }));
    return detail;
  }

  function securityLines(s) {
    if (!s || !s.security_status || s.security_status === 'not_evaluated')
      return [];
    const solved = Array.isArray(s.security_solved) ? s.security_solved : [];
    if (s.security_status === 'error' && !solved.length)
      return ['Security checks: could not be evaluated'];
    /* Solved-index only — never paint totals, remaining, or n/m ratios. */
    const out = [];
    for (const row of solved) {
      if (!row || row.n == null) continue;
      const mod = row.module ? (row.module + ' ') : '';
      out.push(mod + 'solved #' + row.n);
    }
    return out;
  }

  function frTerminal(name) {
    return name === 'COMPLETE' || name === 'FAILED';
  }

  function applySubmission(s, quiet) {
    const fr = S6.fileReturn;
    fr.submission = s;
    fr.status_name = s.status_name || '?';
    const name = fr.status_name;
    logFr(plainStatus(name) + ' · ' + Math.floor(fr.elapsed) + 's');
    if (frTerminal(name)) {
      fr.done = true;
      fr.inFlight = false;
      const good = s.passed === true;
      const word = good ? 'Passed' : (name === 'FAILED' ? 'Grading error' : 'Not passed');
      logFr(word + (s.result_summary ? ' — ' + s.result_summary : ''));
      for (const line of securityLines(s)) logFr(line);
      if (s.alien_status && s.alien_status !== 'not_evaluated') {
        /* Bridge already filters to solved ships; list names, never ratios. */
        const names = (s.aliens || [])
          .map((a) => a && (a.name || a.challenge_path || a.path || a.id))
          .filter(Boolean);
        if (names.length) {
          /* what the harness reported for this job, nothing more */
          logFr('Ships solved: ' + names.join(', ')
            + (s.alien_target && s.alien_target !== 'all'
              ? (' · aimed at ship ' + s.alien_target) : ''));
        } else if (s.alien_target && s.alien_target !== 'all') {
          logFr('This job was aimed at ship ' + s.alien_target);
        }
      }
      if (!quiet) emitFileReturn();
    } else {
      if (s.progress && s.progress.phase) {
        logFr('Grading: ' + s.progress.phase
          + (s.pending_seconds != null
            ? (' · waiting ' + Math.floor(s.pending_seconds) + 's') : ''));
      }
      if (!quiet) emitFileReturn();
    }
    if (S6.open) paintFileReturn();
  }

  function applyLastJob(last) {
    const fr = S6.fileReturn;
    if (fr.inFlight && fr.jobId) return;
    const s = last.submission || last;
    const id = last.job_id || s.job_id || last.id;
    if (!id) return;
    fr.jobId = id;
    fr.status_name = s.status_name || last.status_name || '';
    fr.submission = s;
    fr.done = frTerminal(fr.status_name);
    fr.inFlight = !fr.done;
    /* Terminal jobs from the list already carry sanitized security_solved —
     * paint them (solved-index only) instead of leaving an empty mission log. */
    if (fr.done) {
      if (fr.log.length === 0) applySubmission(s, true);
      else paintFileReturn();
      return;
    }
    if (fr.log.length === 0 && fr.status_name)
      logFr('Job ' + id + ' · ' + plainStatus(fr.status_name));
    fr.pollNow = true;
    paintFileReturn();
  }

  function refreshFileReturnChrome() {
    const fr = S6.fileReturn;
    const gen = ++fr.chromeGen;
    apiJson('/api/auth/status').then(auth => {
      if (dead || gen !== fr.chromeGen) return;
      fr.chromeKnown = true;
      fr.live = true;
      fr.configured = !!auth.configured;
      fr.loggedIn = !!auth.loggedIn;
      if (S6.open) paintFileReturn();
      apiJson('/api/challenges').then(c => {
        if (dead || gen !== fr.chromeGen) return;
        fr.submissionsOpen = c.submissions_open;
        fr.moduleCount = Array.isArray(c.challenges) ? c.challenges.length : 0;
        if (S6.open) paintFileReturn();
      }).catch(() => {});
      if (fr.loggedIn && !(fr.inFlight && fr.jobId)) {
        apiJson('/api/submissions').then(d => {
          if (dead || gen !== fr.chromeGen) return;
          const list = d.submissions
            || (d.result && d.result.submissions) || [];
          if (list[0]) applyLastJob(list[0]);
        }).catch(() => {});
      }
    }).catch(() => {
      if (dead || gen !== fr.chromeGen) return;
      fr.chromeKnown = true;
      fr.live = false;
      if (S6.open) paintFileReturn();
    });
  }

  function pullSubmission() {
    const fr = S6.fileReturn;
    if (!fr.jobId || fr.fetching || fr.done) return;
    fr.fetching = true;
    /* Track 01 merge: api.getSubmission(fr.jobId) */
    fetch('/api/submissions/' + encodeURIComponent(fr.jobId))
      .then(r => r.text())
      .then(t => JSON.parse(t))
      .then(d => {
        fr.fetching = false;
        if (dead) return;
        const s = d.submission || (d.result && d.result.submission);
        if (d.ok && s) applySubmission(s);
      })
      .catch(() => { fr.fetching = false; });
  }

  function rehearsalReturn() {
    const fr = S6.fileReturn;
    fr.inFlight = false;
    fr.rehearsed = true;
    fr.done = true;
    fr.jobId = null;
    logFr('Preview only — nothing was sent. This page can\'t reach the judges.');
    console.info('%c[file-return] PREVIEW -- nothing was sent.'
      + '  A connected page would:', 'color:#c9a227');
    console.info('    POST /api/submit  {}');
    console.info('    GET  /api/submissions/<id>  (poll from tick, ~5s)');
    console.info('    would package every challenge_path');
    emitFileReturn();
    paintFileReturn();
  }

  function beginReturn() {
    const fr = S6.fileReturn;
    fr.inFlight = true;
    fr.done = false;
    fr.rehearsed = false;
    fr.err = null;
    fr.elapsed = 0;
    fr.pollAcc = 0;
    fr.pollNow = false;
    fr.jobId = null;
    fr.status_name = '';
    fr.packaged = null;
    fr.submission = null;
    fr.log = [];
    paintFileReturn();
  }

  /* The body is ALWAYS `{}`: no `alien_target`, so the harness grades every
   * module and every released ship in one job (its documented default; source:
   * harness `ALIEN_ALL_ALIASES = {None, '', 'all'}`).  `api.js` submit() can
   * still send a chosen `alien_target`; this docket deliberately does not offer
   * one. */
  function postSubmit() {
    const fr = S6.fileReturn;
    fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }).then(r => r.text()).then(t => JSON.parse(t)).then(d => {
      if (dead) return;
      const res = (d && d.result) || d || {};
      if (res.ok && res.job_id) {
        fr.jobId = res.job_id;
        fr.status_name = res.status_name || 'QUEUED';
        fr.packaged = res.packaged || null;
        const pk = fr.packaged || {};
        logFr('Sent as job ' + fr.jobId);
        if (pk.fileCount) logFr(pk.fileCount + ' source files packaged');
        fr.pollAcc = 0;
        emitFileReturn();
        paintFileReturn();
      } else {
        fr.inFlight = false;
        fr.done = true;
        fr.err = res.message || res.error || 'unknown error';
        logFr('Submit failed: ' + fr.err);
        emitFileReturn();
        paintFileReturn();
      }
    }).catch(() => {
      if (dead) return;
      /* The probe said a coordinator was there but the send failed: that is a
       * failure, not a preview.  Nothing was accepted. */
      fr.inFlight = false;
      fr.done = true;
      fr.err = 'could not reach the judges';
      logFr('Submit failed: could not reach the judges — nothing was sent.');
      emitFileReturn();
      paintFileReturn();
    });
  }

  function fileReturn() {
    /* This docket does not submit. */
    return;
    const fr = S6.fileReturn;
    if (fr.inFlight) return;
    if (fr.chromeKnown) {
      if (fr.live && !frAllowed()) return;
      beginReturn();
      if (!fr.live) { rehearsalReturn(); return; }
      postSubmit();
      return;
    }
    /* Not yet known whether this origin can reach /api.  Probe first so
     * rehearsal never POSTs.  Track 01 merge: api.getAuthStatus(). */
    beginReturn();
    apiJson('/api/auth/status').then(auth => {
      if (dead) return;
      fr.chromeKnown = true;
      fr.live = true;
      fr.configured = !!auth.configured;
      fr.loggedIn = !!auth.loggedIn;
      if (!frAllowed()) {
        fr.inFlight = false;
        fr.done = false;
        paintFileReturn();
        return;
      }
      postSubmit();
    }).catch(() => {
      if (dead) return;
      fr.chromeKnown = true;
      fr.live = false;
      rehearsalReturn();
    });
  }

  function tickFileReturn(dt) {
    const fr = S6.fileReturn;
    if (!fr.jobId || fr.done) return;
    fr.elapsed += dt;
    if (fr.elapsed >= FR_LIMIT) {
      fr.done = true;
      fr.inFlight = false;
      logFr('Still running — reopen this panel later to see the result.');
      if (S6.open) paintFileReturn();
      return;
    }
    if (!S6.open || fr.fetching) return;
    if (fr.pollNow) {
      fr.pollNow = false;
      fr.pollAcc = 0;
      pullSubmission();
      return;
    }
    fr.pollAcc += dt;
    if (fr.pollAcc >= FR_POLL) {
      fr.pollAcc = 0;
      pullSubmission();
    }
  }

  /* ================================================================== EVENT */
  function tests() {
    const r = S6.result;
    if (r && r.tests) return r.tests;
    return { unit: { pass: 0, fail: 0 },
             vuln: { fired: 0, closed: 0, inconclusive: 0, total: FL.vulns } };
  }

  function emit(state) {
    const detail = {
      code: CODE,
      phase: S6.phase,
      state: state,
      rehearsal: true,
      demo: SAMPLE,
      preview: !SAMPLE,
      cmd: commands(),
      dirty: S6.dirty,
      ts: Date.now(),
      tests: tests(),
    };
    /* One event, on window, per state change.  A LIVE PUSH -- the durable
     * record is status.json.  `vuln.inconclusive` is always present, never
     * undefined: a consumer that has to guess whether the field exists is back
     * to the {fired, closed} problem it was added to solve. */
    dispatchEvent(new CustomEvent('refit:' + CODE, { detail }));
    dispatchEvent(new CustomEvent('refit', { detail }));
    return detail;
  }

  /* ============================================================ DIRTY, IN */
  function refreshDirty() {
    if (typeof o.dirty === 'boolean') return;
    const st = (typeof window !== 'undefined') && window.__status;
    if (st && typeof st.dirty === 'function') {
      try { S6.dirty = !!st.dirty(CODE); S6.dirtyKnown = true; }
      catch (e) { /* the mast has not landed yet; stay unknown */ }
    }
  }
  function onDirtyEvent(e) {
    const d = e && e.detail;
    if (!d) return;
    if (typeof d === 'boolean') { S6.dirty = d; S6.dirtyKnown = true; }
    else if (d.code === CODE && typeof d.dirty === 'boolean') {
      S6.dirty = d.dirty; S6.dirtyKnown = true;
    } else if (typeof d[CODE] === 'boolean') {
      S6.dirty = d[CODE]; S6.dirtyKnown = true;
    }
    if (S6.open) paintHead();
  }
  addEventListener('status:dirty', onDirtyEvent);

  /* ================================================================== FRAME
   * NO TIMERS.  Everything here is driven by the module's own loop, so pose()
   * cannot leave a clock running and two successive sealed captures are
   * byte-identical by construction.  See note 2 at the top. */
  const openMs = (R.open && R.open.ms) || 420;
  const closeMs = (R.open && R.open.close_ms) || 160;
  const openDeg = (R.open && R.open.deg) || -60;
  const openScale = (R.open && R.open.scale) || 0.55;

  function easeOut(t) { return 1 - Math.pow(1 - t, 3); }

  function tick(dt, now) {
    S6.ticks++;
    if (!root.visible) return;
    S6.t += dt;
    /* FROZEN, for a capture only -- see settle() below.  `S6.t` drives the
     * only two things here that loop for ever (the running throat pulse and
     * the idle DIRTY jewel breath); pinning it to 0 makes every frame the
     * same frame without changing a single piece of derived state, which is
     * exactly what `pose()` does with `S6.t = 0` before it hides the port.
     * Nothing on a page a human opens ever sets this. */
    if (S6.frozen) S6.t = 0;

    /* --- the iris.  Each leaf rotates about its OWN OUTER CORNER and shrinks
     * toward it, so the swept envelope never leaves the port's own footprint
     * -- which is what a hinged flap could not do and is why the design is an
     * iris (FIX_UPLOAD 1.3). */
    const dur = (S6.open ? openMs : closeMs) / 1000;
    S6.openT = Math.max(0, Math.min(dur, S6.openT + dt));
    const raw = dur > 0 ? S6.openT / dur : 1;
    const k = S6.open ? easeOut(raw) : 1 - easeOut(raw);
    for (const L of leaves) {
      L.piv.setRotationFromAxisAngle(axis, openDeg * k * D2R);
      L.piv.scale.setScalar(1 + (openScale - 1) * k);
    }

    /* --- the stoplight.  Colour follows the container this port is
     * pointed at.  Green running, red stopped or missing, yellow while
     * Start, Stop, or Restart is in flight or Docker says restarting or
     * health-starting.  Dark if that state was not read.  The yellow pulse
     * stays on the frame ring.  NOT scaled by `k`, and NOT painted on the
     * iris: that face is the animation. */
    const lamp = lampPowered(S6.power.powered, S6.power.phase, S6.power.op);
    const pulse = S6.run ? (0.55 + 0.45 * Math.sin(S6.t * 0.8 * 2 * Math.PI)) : 1;
    const ringPulse = lamp === 'starting'
      ? 0.5 + 0.5 * Math.sin(S6.t * 0.5 * 2 * Math.PI)
      : 0;
    paintThroatLight(glowMats, boreMats, lamp,
                     THREE.LinearSRGBColorSpace, pulse, frameMats, ringPulse);

    /* --- the jewel.  WHITE FAMILY ONLY. */
    let jw = 0;
    if (S6.result && S6.result.failedAt)
      jw = (S6.t % 1 < 0.12 || (S6.t % 1 > 0.24 && S6.t % 1 < 0.36)) ? 1 : 0.05;
    else if (S6.open || S6.run) jw = 1;
    else if (S6.applied) jw = 0.9;
    else if (S6.dirty && S6.dirtyKnown) jw = 0.35 + 0.35 * (0.5 + 0.5 * Math.sin(S6.t * 0.25 * 2 * Math.PI));
    for (const mm of jewelMats) mm.emissiveIntensity = jw * 2.4;

    /* --- the ratchet.  60 deg per completed phase; one revolution per refit. */
    if (S6.run) {
      S6.run.t += dt;
      const want = Math.min(PHASES.length, Math.floor(S6.run.t / S6.run.per) + 1);
      if (want !== S6.phase) {
        S6.phase = want;
        S6.ratchetWant = (want - 1) * 60;
        paintPhases();
        emit(PHASES[Math.max(0, want - 1)].state);
      }
      if (S6.run.t >= S6.run.per * PHASES.length) {
        S6.phase = PHASES.length;
        S6.ratchetWant = 360;
        finish();
      }
    }
    if (ratchet) {
      S6.ratchetDeg += (S6.ratchetWant - S6.ratchetDeg) * Math.min(1, dt * 9);
      ratchet.piv.setRotationFromAxisAngle(axis, S6.ratchetDeg * D2R);
    }
    if (tally) {
      const want = S6.tallyUp;
      const cur = tally.piv.userData.a || 0;
      const a = cur + (want - cur) * Math.min(1, dt * 8);
      tally.piv.userData.a = a;
      tally.piv.setRotationFromAxisAngle(tallyAxis, a * (R.tally.up_deg || -78) * D2R);
    }
    /* FILE RETURN poll: accumulate dt, fire ~5 s.  No setTimeout.
     * Skipped while posed/hidden (`!root.visible` returned above).
     * Sealed docket: keep elapsed, skip fetch, pull once on next open. */
    tickRebuild(dt);
    tickFileReturn(dt);
    tickPower(dt);
    if (S6.open) placeDocket();
  }

  /* =================================================================== POSE */
  function pose() {
    /* HIDE IT.  Decision 3 of FIX_UPLOAD section 0 and the reason no recorded
     * number moves.  Everything is also reset, so a page that is posed, shown
     * and posed again is in the same state both times. */
    S6.open = false; S6.openT = 0; S6.t = 0; S6.phase = 0; S6.run = null;
    S6.result = null; S6.applied = false; S6.frozen = false;
    S6.dirty = false; S6.dirtyKnown = typeof o.dirty === 'boolean';
    S6.ratchetDeg = 0; S6.ratchetWant = 0; S6.tallyUp = 0;
    S6.power.op = null;
    S6.power.seq++;
    S6.power.powered = 'unknown';
    S6.power.phase = '';
    S6.power.released = true;
    S6.power.known = false;
    S6.power.acc = 0;
    S6.power.fetching = false;
    dk.hidden = true;
    dk.classList.add('rise');
    for (const L of leaves) {
      L.piv.setRotationFromAxisAngle(axis, 0);
      L.piv.scale.setScalar(1);
    }
    if (ratchet) ratchet.piv.setRotationFromAxisAngle(axis, 0);
    if (tally) {
      tally.piv.userData.a = 0;
      tally.piv.setRotationFromAxisAngle(tallyAxis, 0);
    }
    paintThroatLight(glowMats, boreMats, 'unknown', THREE.LinearSRGBColorSpace, 0, frameMats);
    for (const mm of jewelMats) mm.emissiveIntensity = 0;
    root.visible = false;
    if (hot) hot.style.display = 'none';
    layer.style.display = 'none';
    /* File-return jobs keep jobId in S6 and may complete while hidden.
     * Paint lives on the docket, which is display:none; jewel/tally/ratchet
     * are rebuild-only and were reset above.  No private timer to cancel. */
  }

  function show(v) {
    const on = v === undefined ? true : !!v;
    root.visible = on;
    if (hot) hot.style.display = on ? '' : 'none';
    layer.style.display = on ? '' : 'none';
    if (!on) seal();
  }

  function dispose() {
    dead = true;
    removeEventListener('keydown', onKey);
    removeEventListener('status:dirty', onDirtyEvent);
    layer.remove();
    if (hot) hot.remove();
    o.scene.remove(root);
    if (typeof window !== 'undefined' && window.__fittings)
      delete window.__fittings.refit;
  }

  pose();
  show(true);

  /* Trap 21, on this fitting's own meshes, once, at mount.  Loud if it is not
   * empty; `refit.facing()` and `window.__facing()` re-run it on demand. */
  const facing = () => facingAudit(THREE, meshes, o.camera);
  const facing0 = facing();
  if (facing0.length)
    console.warn('[refit:' + CODE + '] facingAudit: these port meshes face '
      + 'AWAY from the camera and dress()\'s FrontSide is discarding them: '
      + facing0.join(', '));

  watchTick('refit', S6, () => root.visible);

  /* ================================================================ SETTLE
   * See the block of the same name in `mast.js`.  The port's own eased state
   * is the iris (`openT` toward its duration), the ratchet and the tally
   * flag; `settle()` fast-forwards all three and re-applies the transforms
   * with a zero-length tick, so the frame is exactly the one the ease was
   * heading for.  A ceremony in flight, a blinking failure jewel and the idle
   * DIRTY breath all loop and never come to rest, and `settled()` says so
   * instead of pretending. */
  function settle(freeze) {
    if (freeze !== undefined) S6.frozen = !!freeze;
    let moved = 0;
    const dur = (S6.open ? openMs : closeMs) / 1000;
    if (S6.openT < dur) { S6.openT = dur; moved++; }
    if (Math.abs(S6.ratchetWant - S6.ratchetDeg) > 1e-9) {
      S6.ratchetDeg = S6.ratchetWant; moved++;
    }
    if (tally && Math.abs(S6.tallyUp - (tally.piv.userData.a || 0)) > 1e-9) {
      tally.piv.userData.a = S6.tallyUp; moved++;
    }
    if (moved && root.visible) tick(0, 0);
    return moved;
  }

  function settled() {
    if (!root.visible) return true;
    if (S6.run) return false;                       /* ceremony in flight */
    const dur = (S6.open ? openMs : closeMs) / 1000;
    if (S6.openT < dur - 1e-6) return false;        /* iris still moving */
    if (Math.abs(S6.ratchetWant - S6.ratchetDeg) > 1e-4) return false;
    if (tally && Math.abs(S6.tallyUp - (tally.piv.userData.a || 0)) > 1e-4)
      return false;
    if (S6.frozen) return true;      /* every loop is pinned; see settle() */
    if (S6.result && S6.result.failedAt) return false;   /* jewel blinks */
    /* THE IDLE DIRTY BREATH -- a 0.25 Hz sine on the jewel, whenever the port
     * is sealed, idle, and knows the workbench is dirty.  This is a real,
     * permanent animation on a page a human opens, and it is DELIBERATE (the
     * jewel is the attractor that says there is something to commit).  It is
     * also why `settle()` needs a freeze: a module whose live record is dirty
     * -- MTA is the fleet's only one, `source_rev sha256:0000staleexample` --
     * has NO byte-stable frame with the port shown, at any SETTLE, and
     * `check_occlusion.py` reports it as a partition FAIL with "must be 0"
     * counters (72 px at pr 2).  Nothing about that is new and nothing about
     * it is the mast's; the `dirty` seam was wired after MTA was measured. */
    if (!S6.open && !S6.applied && S6.dirty && S6.dirtyKnown) return false;
    return true;
  }

  const api = {
    root, tick, pose, show, dispose, tally, facing, settle, settled,
    code: CODE,
    tris: TRIS,
    state: () => ({ open: S6.open, phase: S6.phase, dirty: S6.dirty,
                    running: !!S6.run, applied: S6.applied,
                    visible: root.visible, docket: !dk.hidden,
                    fileReturn: { jobId: S6.fileReturn.jobId,
                      status_name: S6.fileReturn.status_name,
                      inFlight: S6.fileReturn.inFlight,
                      rehearsal: !S6.fileReturn.live
                        || !!S6.fileReturn.rehearsed } }),
    setDirty: v => { S6.dirty = !!v; S6.dirtyKnown = true;
                     if (S6.open) paintHead(); },
    open, seal, commit, fileReturn, commands, docket: dk, hotspot: hot,
    /* the harness drives THESE, so a check never has to synthesise a pointer
     * event to reach a state.  A real pointer is still the thing that must be
     * tested; this is for asserting the state machine, not for replacing it. */
    __test: { fixture, S6, emit, emitFileReturn },
  };
  registerFitting('refit', api);
  return api;
}


/* What a normal first open uses: nothing.  No build time, no file list, no
 * check result -- the docket shows an honest empty state. */
export function emptyFixture() {
  return { dirty: false, running: false, image: null, files: [],
           result: { failedAt: 0, log: [] } };
}

/* DEMO DATA.  A static stand-in for the three endpoints FIX_UPLOAD 5.1
 * proposes, so the whole ceremony can be driven and measured with no server.
 * Used ONLY under `?demo=1` (or a caller's own `fixture:`), and labelled
 * DEMO DATA on the docket whenever it is. */
export function defaultFixture(code, FL) {
  /* THE FLEET BRANCH, and `commands()` has had one since it was written.
   *
   * Without it PKT -- the only module in the table with `fleet: true`, no
   * `svc`, no `dir` and `vulns: 0` -- rendered a docket of four false
   * statements: an `IMAGE saintcon/pkt:local` for a module that has no service
   * in `bridge/fleet-compose.yml`, three amended files under a directory that
   * does not exist, `PROVE 8 of 8 unit checks passed` for a module with no
   * `unit_tests/`, and
   *
   *     ASSAY  0 proofs — 0 closed, 1 still firing, -1 inconclusive
   *
   * because `closed = max(0, 0 - 2) = 0` and `inconclusive = 0 - 0 - 1`.
   * FIX_UPLOAD 12.13 item 2 goes to some trouble to make `inconclusive` always
   * present and never `undefined`; a consumer reading -1 is worse off than one
   * reading `undefined`, and every `refit:PKT` event carried it.  PKT NOTES 14
   * item 4.
   *
   * `result.tests` is deliberately ABSENT here rather than zeroed: `tests()`
   * then answers the all-zero object with `total: FL.vulns`, so every event
   * still carries a numeric `vuln.inconclusive` (12.13 holds), and
   * `paintPhases()` prints no PROVE/ASSAY summary at all instead of a summary
   * of nothing.  What the phases MEAN for this module is in the log, in words.
   */
  if (FL.fleet) {
    return {
      dirty: false,
      running: true,
      image: null,
      files: [],
      result: {
        failedAt: 0,
        log: ['DEMO DATA: nothing was built.',
              code + ' is not a fixable module: no unit_tests, no vuln_tests, '
                + 'and no service in ' + COMPOSE + '.',
              'A FLEET refit — rebuilding every module at once — is an open '
                + 'question for a human (FIX_UPLOAD section 7).'],
      },
    };
  }
  const dir = FL.dir || code.toLowerCase();
  const total = FL.vulns || 0;
  const closed = Math.max(0, total - 2);
  return {
    dirty: true,
    running: true,
    image: { tag: 'saintcon/' + (FL.svc || code.toLowerCase()) + ':local',
             built: '14:02', sha: '8f31a2c' },
    files: [
      { path: dir + '/resp.go', add: 18, del: 4 },
      { path: dir + '/auth.go', add: 6, del: 1 },
      { path: dir + '/Dockerfile', add: 1, del: 1 },
    ],
    result: {
      failedAt: 0,
      tests: {
        unit: { pass: 8, fail: 0 },
        /* inconclusive is ALWAYS present.  STATUS_AT_A_GLANCE 9.4 rule 1. */
        vuln: { fired: 1, closed: closed, inconclusive: total - closed - 1,
                total: total },
      },
      log: ['DEMO DATA: nothing was built.',
            'the commands this port would have run are on the console'],
    },
  };
}

/* keep `pad` reachable for a module that wants the docket's column widths */
export { pad };
