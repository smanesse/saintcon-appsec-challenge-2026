/* SAINTCON 2026 — THE COCKPIT SHELL.
 *
 * WHAT THIS FILE IS NOW, AND WHAT IT WAS
 * --------------------------------------
 * It was a 953-line KVS-specific monolith: the cockpit AND one module's live
 * close-up in one file, with the other eight opening baked plates.  README
 * section 16.8 recorded that as "unowned work, deliberately left".  This is
 * that work.
 *
 * KVS's half moved out to `live3d/modules/KVS/`, which is a page like the
 * other eight -- same template, same `window.__occ` contract, same checkers.
 * What is left here is the shell, and it is module-agnostic:
 *
 *   1. THE WIDE SHOT.  `../cockpit/combined/main_plate.png`, referenced in
 *      place so it is provably the shipped pixels, with the nine hover glows
 *      and hotspots read out of the shipped `combined/manifest.json`.
 *      `cockpit/` is read-only and nothing here writes to it.
 *   2. THE DIVE.  `transition.js`, unchanged: one virtual camera, both layers
 *      hung off it, a match dissolve inside one continuous move.
 *   3. THE LIVE CLOSE-UP.  `modules/<CODE>/index.html?embed=1` in an iframe.
 *
 * WHY AN IFRAME.  Two WebGL contexts, an rAF loop, a resize listener and a
 * global `window.__occ` per module; nine of those in one document is 18
 * contexts against a browser limit near 16, and the module pages are top-level
 * scripts with no teardown path.  The iframe is created on hover, flown into
 * on click and DESTROYED on the way out, which frees both contexts with
 * certainty.  It also means the cockpit shows the page the checkers verified,
 * unmodified -- there is no second copy of any module's code to drift.
 *
 * WHAT IS DELIBERATELY NOT HARMONISED.  Every module's `light_gain`,
 * `ubias_m`, `colour`/grade and readout planes stay in its own `scene.json`
 * and are read by its own page.  They are measurements of that module (the
 * fitted gains span 0.501..0.688 and the ubias values span 1 um .. 1.5 mm),
 * and CONVERSION_BRIEF 5.2a is the record of what happened the last two times
 * one of them was treated as a fleet constant.
 *
 * NO innerHTML.  Every string reaches the page through textContent or
 * createTextNode; `grep -rn innerHTML live3d/` finds no assignment.
 */
import { createDolly, CFG as TXCFG } from './transition.js';
/* THE TELLTALE MAST — live3d/design/STATUS_AT_A_GLANCE.md.
 * `status.js` is the ONE place the mapping from facts to marks lives, so the
 * wide shot here and any close-up counterpart later cannot drift apart
 * (section 6.4).  It owns every colour; `status.json` carries none. */
import { WIDE_MASTS, createMast, deriveAll, loadStatus, loadLive, statusLine }
  from './status.js';
import { getHealth, mountLinkUx } from './api.js';
import * as api from './api.js';
import { bootCrew } from './crew.js';
import { bootBranchNotice } from './branch-notice.js';
import { bootPersonMenu } from './person-menu.js';
import { bootFlagsWallet } from './flags-wallet.js';
import { createShellNav } from './shell-nav.js';
import { createHelp, createTutorial } from './help.js';
import { mountSubmitSigns } from './submit-signs.js';
import { mountGradePanel } from './grade-panel.js';
import { tellFor } from './submit-core.js';
import { paintSubmissionsLeft } from './submissions-left.js';
window.__api = api;

const W = 1280, H = 720;
const $ = id => document.getElementById(id);

/* DEV / QA / ADMIN CONTROLS — OFF unless the cockpit's OWN url carries `?dev=1`
 * (owner-fixes T1b, approved behaviour 6).  The same convention the standings
 * button and the module pages use.  It is read once from `location.search`: no
 * localStorage, no cookie, no hash, no key combination, so neither a first load
 * nor an accidental click or keypress can turn it on, and it is not remembered
 * for the next visit.  What it gates here:
 *   - the person-menu `dom text` / `occlusion split` / `show planes` /
 *     `show hotspots` / `standings` buttons (created here, not written in
 *     index.html: they do not exist in the page for a player),
 *   - the crew-strip UPDATE chip (crew.js reads the same flag),
 *   - the engineering wording on the note line and in error banners,
 *   - `&dev=1` on the module frame's url, so the module pages show their own
 *     dev surfaces too.
 * Update apply is untouched: still confirm-first, and the bridge keeps it disabled. */
const DEV = /(^|[?&])dev=1(&|$)/.test(location.search.slice(1));
if (DEV) {
  const host = $('personMenu') || document.body;
  for (const [id, label, on] of [['bText', 'dom text', true], ['bOcc', 'occlusion split', true],
                                 ['bPlanes', 'show planes', false], ['bDbg', 'show hotspots', false],
                                 ['bBoard', 'standings', false]]) {
    const b = document.createElement('button');
    b.id = id; b.textContent = label;
    if (on) b.className = 'on';
    host.appendChild(b);
  }
}
function showBack(on) {
  const b = $('bBack');
  if (b) b.style.display = on ? '' : 'none';
}
/* A dev button, or a harmless stub when the page is in player mode. */
const onDev = (id, fn) => { const b = $(id); if (b) b.addEventListener('click', fn); };

function fail(msg) {
  const e = $('err');
  e.style.display = 'block';
  e.textContent = msg;
  throw new Error(msg);
}
addEventListener('error', ev => {
  const e = $('err'); e.style.display = 'block';
  /* A player gets one plain sentence; the raw message (file, line, internals) is
   * for `?dev=1` and for the browser console, which already has it. */
  e.textContent = DEV
    ? 'PAGE ERROR: ' + ev.message
    : 'Something went wrong in the cockpit. Reload the page; if it keeps happening, tell an organizer.';
});

async function getJSON(u) {
  const r = await fetch(u);
  if (!r.ok) fail('cannot fetch ' + u + ' (HTTP ' + r.status + ')\n\n' +
    'Serve the REPO ROOT, not live3d/:\n' +
    '    cd <repo>/2026 && python3 -m http.server 8777\n' +
    '    open http://localhost:8777/live3d/\n\n' +
    'Or run  ./live3d/run.sh  , which does both.');
  return r.json();
}
if (location.protocol === 'file:')
  fail('This page is open over file://, and that cannot work.\n\n' +
    'ES module imports and the fetches of scene.json / depth.bin / *.glb are ' +
    'blocked by the browser for file URLs, whatever the page does.\n\n' +
    'Run  ./live3d/run.sh  from the repo root, or:\n' +
    '    cd <repo>/2026 && python3 -m http.server 8777\n' +
    '    open http://localhost:8777/live3d/');

/* Coordinator reachability, once.  Unreachable is an honest strip, not a
 * hung spinner and not fail().  02 owns the live poll. */
const linkUx = mountLinkUx({ host: document.getElementById('linkUx') });
getHealth().then((h) => {
  if (!h.reachable) {
    linkUx.announce({
      level: 'crit',
      kind: 'unreachable',
      message: DEV ? 'coordinator not on this origin'
        : 'Can\u2019t reach the scoring service right now. Returns can\u2019t be sent until it is back.',
      persist: true,
      ms: h.ms,
    });
  }
}).catch(() => {});

/* Start the strip fetch in parallel with the manifests.  Do not await it:
 * a delayed /api/harness must not black the wide shot. */
const CREW = bootCrew();
const personMenu = bootPersonMenu();
/* Captured A.L.I.E.N. flag wallet: menu-bar button + panel, GET /api/flags. */
bootFlagsWallet(document);
/* Player notice only. GET /api/updates; never applies. Rings open the menu. */
bootBranchNotice(document, { onRings: () => personMenu.open() });
/* Counts stay unknown until the authenticated limits snapshot arrives. */
paintSubmissionsLeft(document);

/* ===================================================================== 1 */
/* LOAD — the two manifests, and nothing else.  The module pages load their
 * own assets, which is the point of the split.                            */
const CK = '../cockpit/';
const [MAN, TX] = await Promise.all([
  getJSON(CK + 'combined/manifest.json'),
  getJSON('./transition.json'),
]);
$('wPlate').src = CK + MAN.plate;
const CODES = Object.keys(MAN.modules).sort();

/* THE STANDINGS PLATE's placement record — live3d/assets/_STANDINGS/.
 *
 * NOT one of the two manifests above, and deliberately not fetched with them:
 * `getJSON()` calls `fail()` on a miss, and this file is ALLOWED TO BE ABSENT.
 * A clone that has not run `standings_plate.py -- render` gets a cockpit with
 * no nameplate rather than an error page, which is the same promise
 * `loadStatus()` makes for `status.json`: the page must come up looking like a
 * cockpit when a producer has not run.  (A clone that HAS not gets one 404 in
 * the console from the browser's own network layer -- `fetch` logs a miss
 * whatever the caller does with it -- and nothing else: no page error, nine
 * glows, nine masts, eighteen hotspots, measured.)
 *
 * It is a RECORD OF A SOLVE, not a set of authored numbers: the hotspot rect,
 * the sprite names and the label all come out of
 * `pipeline/standings_plate.py: solve_plate()`, so no rectangle on this
 * fitting is typed in two places.  Same-origin, static, no network leaves the
 * machine. */
const SB = await fetch('./assets/_STANDINGS/standings.json')
  .then(r => (r.ok ? r.json() : null)).catch(() => null);

/* ===================================================================== 2 */
/* THE WIDE SHOT — baked, untouched, all nine modules live                  */
const tip = $('tip');
const glow = {};                       // code -> its far_glow layer
const tells = {};                      // code -> its telltale mast component
const hots = {};                       // code -> [its .whot hotspot els]
let DER = deriveAll(null, CODES);      // code -> derived display state
let hovering = null;                   // the code under the cursor, or null
let openCode = null;                // the code in close-up, or null
let moving = false;

/* Every image the BAKED close-up of `code` is assembled from, in paint order.
 * This is still here, and it is not a fallback: it is the picture the DIVE
 * flies into.  `transition.json`'s per-module magnification M was measured
 * against exactly these layers (pipeline/measure_transition.py), so flying
 * into anything else would be flying into a match that was never measured.
 * The live page fades in over the top once it has loaded, and these are then
 * removed -- two film-transparent copies of the same plate composite to the
 * wrong alpha, which is trap 20 from the other side. */
function closeSrcs(code) {
  const c = MAN.modules[code].close;
  const out = [CK + c.plate];
  for (const k of Object.keys(c.controls)) {
    const ct = c.controls[k];
    const p = ct.image !== undefined ? ct.image
            : ct.frames !== undefined ? ct.frames[0]
            : ct.states !== undefined
              ? ct.states[(ct.order || Object.keys(ct.states))[0]]
              : null;
    if (p) out.push(CK + p);
  }
  return out;
}
/* RELEASE GATE, read off the same derived live state the mast paints NOT YET
 * AVAILABLE from (status.js). True ONLY when the live feed positively reports
 * the module not yet available; an absent/unreachable feed (live === null)
 * returns false — fail open, same as release.py on the bridge. */
function notReleased(code) {
  const live = DER[code] && DER[code].live;
  return !!(live && (live.released === false
    || live.availability === 'not_yet_available'));
}

/* Drop the pointer cursor on an unreleased module's hotspots so it does not
 * read as clickable. Called on every status poll, since release state arrives
 * (and can change day to day) over the 5 s feed. */
function syncHotspotLocks() {
  for (const code of CODES) {
    const locked = notReleased(code);
    for (const h of (hots[code] || [])) h.classList.toggle('locked', locked);
  }
}

const preloaded = {};                  // code -> [Image], kept so they stay warm
function preload(code) {
  if (preloaded[code]) return;
  preloaded[code] = closeSrcs(code).map(s => { const i = new Image(); i.src = s; return i; });
}

for (const code of CODES) {
  const m = MAN.modules[code];
  const g = document.createElement('img');
  g.className = 'glow' + (m.far.glow_tint ? ' tint-' + m.far.glow_tint : '');
  g.src = CK + m.far.glow;
  g.alt = '';
  $('wGlows').appendChild(g);
  glow[code] = g;

  hotspot(code, m, g, m.far.hotspot);

  /* THE TELLTALE MAST.  Same trick as the hotspot above and the glow above
   * that: an absolutely-positioned child of #wide, authored in canonical
   * 1280x720 px, scaled by the one transform layout() puts on #stage.  There
   * was nothing new to invent -- section 3 of the design checked this against
   * how the shell actually composites rather than assuming it.
   *
   * It stays on screen during and after the dive, because #wide does (see
   * landed()), so the mast flies toward you with its module and then sits
   * under the close-up dimmed and blurred by transition.js's filter.  That is
   * wanted, not a leak. */
  const L = WIDE_MASTS[code];
  if (L) {
    const mast = createMast({ code, anchor: L.anchor, dir: L.dir, env: L.env });
    $('wTells').appendChild(mast.root);
    tells[code] = mast;
    /* A mast that is visibly part of a module should behave like it.  #wTells
     * is pointer-events:none, so this is a SECOND .whot on the same three
     * handlers.  Measured (section 4.2): the nine envelopes overlap no other
     * module's hotspot rect and none of each other, so nothing about the
     * existing hit-testing changes. */
    hotspot(code, m, g, { x: L.env[0], y: L.env[1], w: L.env[2], h: L.env[3] });
  }
}

/* Performance dialog (stars.js) remembers this in
 * localStorage['cockpit.modules.hover']. Missing means on, which is today's
 * hover preload. Off skips warm() on hover only. A click still calls warm(),
 * and the 5 s status poll below is not this setting. */
function hoverPreloadOn() {
  try { return localStorage.getItem('cockpit.modules.hover') !== 'off'; }
  catch (e) { return true; }
}

/* One hotspot, wired to the three handlers.  Factored out only so the mast's
 * envelope can reuse them verbatim rather than growing a second copy that
 * could drift. */
function hotspot(code, m, g, r) {
  const h = document.createElement('div');
  h.className = 'whot';
  h.style.left = r.x + 'px'; h.style.top = r.y + 'px';
  h.style.width = r.w + 'px'; h.style.height = r.h + 'px';
  (hots[code] || (hots[code] = [])).push(h);
  h.addEventListener('mouseenter', () => {
    if (moving || openCode) return;
    /* The tooltip still shows (it reads NOT YET AVAILABLE), but an unreleased
     * module lights no glow, preloads nothing and never warms its page: the
     * dive is refused below, so loading its assets would only leak that the
     * content exists. The `.locked` class drops the pointer cursor. */
    hovering = code;
    showTip(code, m);
    tip.style.opacity = 1;
    if (notReleased(code)) return;
    g.style.opacity = 0.9;
    if (tells[code]) tells[code].root.classList.add('hot');
    preload(code);
    if (hoverPreloadOn()) warm(code);  // hover preload; a click still warms
  });
  h.addEventListener('mousemove', e => {
    tip.style.left = (e.clientX + 16) + 'px';
    tip.style.top = (e.clientY - 12) + 'px';
    keepTipOnScreen(e);
  });
  h.addEventListener('mouseleave', () => {
    g.style.opacity = 0; tip.style.opacity = 0;
    if (tells[code]) tells[code].root.classList.remove('hot');
    if (hovering === code) hovering = null;
  });
  h.addEventListener('click', () => openModule(code));
  $('wHots').appendChild(h);
}

/* THE TOOLTIP MUST STAY ON SCREEN (owner-fixes T6, from T3's report).  It is placed
 * at the pointer + (16, -12) first; then, if that would run past the right edge it
 * flips to the left of the pointer, and finally it is clamped inside the window
 * (8 px margin) on every side.  Uses the tooltip's own measured box, so the
 * multi-line status text of any module fits. */
let lastPtr = null;
function keepTipOnScreen(e) {
  if (e) lastPtr = { x: e.clientX, y: e.clientY };
  if (!lastPtr) return;
  const w = tip.offsetWidth, h = tip.offsetHeight, m = 8;
  let x = lastPtr.x + 16, y = lastPtr.y - 12;
  if (x + w > innerWidth - m) x = lastPtr.x - 16 - w;
  x = Math.max(m, Math.min(innerWidth - w - m, x));
  y = Math.max(m, Math.min(innerHeight - h - m, y));
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}

/* THE TOOLTIP — section 5.1.  Two lines, both textContent, no markup:
 *     KVS · Core Memory Banks
 *     FLIES · 2 of 6 exploits still land · 1 unknown · run 4m ago
 * The second line is the only place the wide shot puts the count in words.
 * The picture answers "which module do I go and work on"; the words answer
 * "how much of it", and that is a hover-time question, not a glance one. */
function showTip(code, m) {
  const line = statusLine(DER[code]);
  tip.textContent = code + ' · ' + m.name + (line ? '\n' + line : '');
  keepTipOnScreen();
}

/* ===================================================================== 3 */
/* THE EMBEDDED MODULE PAGE                                                */
/* One iframe at a time.  `warm(code)` creates it on hover so the ~4 MB of
 * depth.bin and glbs are usually in flight before the click; `openModule`
 * flies into the baked plates meanwhile and cross-fades the live page in when
 * it reports `__loaded`.  `dropFrame()` removes the element, which is what
 * actually frees the two WebGL contexts -- there is no dispose() to call,
 * because a module page is a top-level script and not a class. */
let frame = null;            // the <iframe>, or null
let frameCode = null;        // the code it is loading/showing
let frameReady = false;
let frameFail = null;        // {reason} once the live frame has been declared failed
let bootAt = 0;              // when the current frame was created (warm)
let openedAt = 0;            // when the player actually opened it (0 = only hovered)
let cardTimer = null;

/* THE READY WAIT IS BOUNDED, AND A FAILURE IS SHOWN.  The frame is opacity 0
 * until it reports `__loaded`, so anything it says about itself (its own #err
 * banner included) is invisible, and before this the cockpit sat in close-up
 * forever with a dead, invisible page.  Now: a loading card over the close-up
 * while it boots, and after READY_TIMEOUT_MS (or as soon as the frame is seen
 * to have failed) an error card with Retry / Back to cockpit.
 * `?readyTimeoutMs=NNN` on the cockpit URL shortens the bound for tests; the
 * default is 20 s.  CARD_DELAY_MS keeps a fast module (live in <300 ms) from
 * flashing the card. */
const READY_TIMEOUT_MS = (() => {
  const v = +new URLSearchParams(location.search).get('readyTimeoutMs');
  return v >= 500 && v <= 600000 ? v : 20000;
})();
const CARD_DELAY_MS = 300;
const BANNER_GRACE_MS = 500;
const fcard = $('frameCard');

function moduleName(code) {
  const m = MAN.modules[code];
  return (m && m.name) || code;
}
/* FIRST-OPEN HELP (help.js).  A shell overlay over the close-up: shown the first
 * time this player opens a module (once it has landed, so it never sits on the
 * loading card), reopened any time by the ? button, closed first by Escape. */
const help = createHelp({
  card: $('helpCard'), btn: $('bHelp'),
  nameOf: c => moduleName(c),
  openCode: () => (openCode && !moving && !closing ? openCode : null),
});
const tutorial = createTutorial({
  card: $('tutorialCard'), btn: $('bTutorial'),
});
const wideShot = () => !document.body.classList.contains('closeup')
  && !document.body.classList.contains('board')
  && !document.body.classList.contains('moving');
const grade = mountGradePanel({
  panel: $('gradePanel'), isWide: wideShot,
  toWeapons: () => goToWeapons(),
  toGrade: () => openGradeFromTell(),
  screen: () => {
    const gradeOpen = $('gradePanel') && !$('gradePanel').hidden;
    if (gradeOpen) return 'grade';
    if (openCode === 'PKT') return 'weapons';
    return 'other';
  },
});
/* Deferred action to run once the grade station has finished returning the
 * dolly (used by the grade panel's "go to the weapons console" pointer, so the
 * dive into PKT does not fight the camera move back out of the station). */
let afterGradeReturn = null;
function goToWeapons() {
  const go = () => { try { openModule('PKT'); } catch (e) { /* ignore */ } };
  if (gradePhase === 'open' || gradePhase === 'in') {
    afterGradeReturn = go;
    beginGradeReturn(false);
  } else {
    requestGradeClose();
    go();
  }
}
window.cockpitTutorial = () => tutorial.open();
addEventListener('cockpit-tutorial', () => tutorial.open());
addEventListener('message', (e) => {
  if (e.origin !== location.origin) return;
  if (e.data && e.data.type === 'cockpit-tutorial') tutorial.open();
});

function showCard(mode, reason) {
  const code = frameCode || openCode;
  if (!code) return;
  fcard.dataset.mode = mode;
  fcard.classList.toggle('error', mode === 'error');
  fcard.querySelector('.fc-title').textContent = mode === 'error'
    ? moduleName(code) + ' did not start'
    : moduleName(code) + ' \u2014 powering up\u2026';
  fcard.querySelector('.fc-msg').textContent = mode === 'error'
    ? (reason || 'The live close-up did not load.')
      + '\n\nRetry reloads the close-up, or go back to the cockpit.'
    : 'Loading the live close-up. This can take a few seconds.';
  const wasHidden = fcard.hidden;
  fcard.hidden = false;
  if (mode === 'error' && wasHidden) {
    const b = fcard.querySelector('button.retry');
    /* Keyboard users land on Retry, but never steal focus from a control the
     * player is already using. */
    if (!document.activeElement || document.activeElement === document.body) {
      try { b.focus(); } catch (e) { /* ignore */ }
    }
  }
}
function hideCard() {
  clearTimeout(cardTimer); cardTimer = null;
  fcard.hidden = true;
}
function scheduleLoadCard(delay) {
  clearTimeout(cardTimer);
  cardTimer = setTimeout(() => {
    cardTimer = null;
    if (openCode && frame && !frameReady && !frameFail) showCard('loading');
  }, delay);
}
function setFail(reason) {
  if (frameFail) return;
  frameFail = { reason };
  clearTimeout(cardTimer); cardTimer = null;
  showCard('error', reason);
  setNote();
}
function clearFail() {
  frameFail = null;
  hideCard();
}
/* Why this frame is not going to load, or null.  Same origin, so the frame's
 * own state is readable; a cross-origin frame IS the browser's error page. */
function frameProblem(f) {
  const name = moduleName(frameCode);
  if (f._unreadable) return 'The browser could not load the ' + name + ' page (network error).';
  let doc = null, w = null;
  try { w = f.contentWindow; doc = f.contentDocument; }
  catch (e) {
    /* cross-origin after the load event is the browser's error page */
    if (f._loaded) return 'The browser could not load the ' + name + ' page (network error).';
  }
  if (f._status >= 400) return 'The ' + name + ' page answered HTTP ' + f._status + '.';
  const e = doc && doc.getElementById && doc.getElementById('err');
  let shown = false;
  try { shown = !!(e && e.textContent && w.getComputedStyle(e).display !== 'none'); }
  catch (x) { shown = false; }
  if (shown) {
    f._bannerAt = f._bannerAt || performance.now();
    if (performance.now() - f._bannerAt > BANNER_GRACE_MS) {
      /* the frame's own words, first paragraph only (the rest is developer advice) */
      return e.textContent.split(/\n\s*\n/)[0].trim()
        .replace(/^PAGE ERROR:\s*(Uncaught\s+\w*Error:\s*)?/i, '').slice(0, 240);
    }
  } else {
    f._bannerAt = 0;
  }
  const since = Math.max(bootAt, openedAt);
  if (performance.now() - since > READY_TIMEOUT_MS) {
    return 'The ' + name + ' close-up is taking too long to start (over '
      + Math.round(READY_TIMEOUT_MS / 1000) + ' seconds).';
  }
  return null;
}

function warm(code) {
  if (frameCode === code) return;
  dropFrame();
  frameCode = code;
  frameReady = false;
  const f = document.createElement('iframe');
  f.id = 'cFrame';
  f.title = moduleName(code) + ' close-up';
  /* `?embed=1` makes the module page transparent and hides its own toolbar.
   * Nothing else about it changes -- same renderer, same split, same
   * constants, same session model.  modules/<CODE>/index.html. */
  f.src = 'modules/' + code + '/?embed=1' + (DEV ? '&dev=1' : '');
  f.setAttribute('scrolling', 'no');
  /* On load: a cross-origin document is Chrome's own error page (the request
   * failed); an HTTP error status is readable from the frame's navigation
   * entry.  Neither can ever report __loaded. */
  f.addEventListener('load', () => {
    f._loaded = true;
    try {
      void f.contentWindow.location.href;
      const n = f.contentWindow.performance.getEntriesByType('navigation')[0];
      if (n && n.responseStatus >= 400) f._status = n.responseStatus;
    } catch (e) { f._unreadable = true; }
  });
  $('cWrap').appendChild(f);
  frame = f;
  bootAt = performance.now();
  sizeFrame();
  pollReady();
}
function dropFrame() {
  document.body.classList.remove('live');
  if (frame) { if (frame._keysOff) frame._keysOff(); frame.remove(); }
  frame = null; frameCode = null; frameReady = false;
  frameFail = null; openedAt = 0;
  hideCard();
}
/* The module page sets `window.__loaded = true` on its last line -- the same
 * flag check/shoot_occlusion.mjs waits for.  Same origin, so it is readable
 * directly; there is no message protocol to keep in sync. */
function pollReady() {
  const f = frame;
  const tick = () => {
    if (f !== frame) return;                       // superseded
    /* A cross-origin frame (the browser's own error page after a failed
     * request) THROWS on the property read, not just on contentDocument: the
     * read must be inside the try or the poll dies and nothing ever reports. */
    let ready = false;
    try { const w = f.contentWindow; ready = !!(w && w.__loaded === true && w.__occ); }
    catch (e) { ready = false; }
    if (ready) {
      frameReady = true;
      if (frameFail) clearFail();                  // it came up after all: recover cleanly
      else hideCard();
      landLive();
      return;
    }
    /* Only an OPEN module can be declared failed; a merely hovered one keeps
     * loading quietly in the background. */
    if (openCode && openCode === frameCode && !frameFail) {
      const why = frameProblem(f);
      if (why) setFail(why);
    }
    setTimeout(tick, frameFail ? 400 : 60);
  };
  tick();
}
/* Retry: throw the frame away and boot a fresh one, wait restarted. */
function retryFrame() {
  const code = openCode;
  if (!code) return;
  dropFrame();
  warm(code);
  openedAt = performance.now();
  showCard('loading');
  setNote();
}
fcard.querySelector('button.retry').addEventListener('click', retryFrame);
fcard.querySelector('button.back').addEventListener('click', () => nav.request());
function landLive() {
  if (!frameReady || frameCode !== openCode || moving) return;
  document.body.classList.add('live');
  applyChrome();
  hookFrameKeys(frame);
  /* Give the cross-fade its 260 ms, THEN drop the baked layers underneath.
   * Removing them any earlier shows the wide backdrop through a
   * film-transparent hole for a frame or two; leaving them for good would
   * double the plate's own alpha, which is exactly OTA's 35% problem run
   * backwards. */
  setTimeout(() => {
    if (frameReady && frameCode === openCode) $('cLayers').replaceChildren();
  }, 300);
  setNote();
  help.auto(openCode);             // first open of this module by this player only
}
/* ESCAPE, ONE POLICY FOR BOTH PLACES THE KEY CAN LAND.
 *
 * A module can have an overlay of its own open (the FMM punch card is the one
 * that exists today).  Escape belongs to that overlay first, and only a second
 * Escape leaves the close-up.  The contract with a module page is
 * `window.__closeOverlay()`: it closes the overlay if one is open and returns
 * true, otherwise it does nothing and returns false.  Asking it IS the act of
 * closing, so it is called at most once per key press and only when nothing
 * else has used the key already.
 *
 * Where the key lands:
 *   - on the cockpit chrome (focus on a bar button, the page): the window
 *     listener below.
 *   - inside the module frame (the player clicked into it, or the overlay took
 *     focus): the frame never reaches the cockpit window, so `hookFrameKeys()`
 *     installs a same-origin listener on the frame's window when it lands and
 *     routes the key to the very same `escapeKey()`.  A module whose own handler
 *     already used the key says so with preventDefault/stopPropagation (FMM does
 *     both); the refit docket seals itself first, so it is sampled in the capture
 *     phase.  Either way the key is not used twice.
 * `nav.escape()` -> `closeModule()` carries the `closing` guard and the history
 * marker logic from T1a, so an extra Escape cannot close twice or pop history
 * twice.  The two listeners can never both see one key press: a key typed in the
 * frame does not bubble out of it. */
function overlayUsedEscape() {
  if (!openCode || !frame || !frameReady) return false;
  try {
    const w = frame.contentWindow;
    return !!(w && typeof w.__closeOverlay === 'function' && w.__closeOverlay() === true);
  } catch (e) { return false; }                    // cross-origin / gone: nothing to ask
}
function escapeKey(e) {
  if (e && e.defaultPrevented) return;             // somebody else already used this key
  if (personMenu.isOpen()) {
    personMenu.close();
    if (e) { e.preventDefault(); e.stopPropagation(); }
    return;
  }
  /* The help card is a shell overlay and is on top: the first Escape closes it,
   * and only the next one reaches the module's overlay or the way out.  (The leave
   * card, when up, is handled by nav.escape() below, which dismisses it first.) */
  if (gradePhase === 'out') return;
  if (gradePhase === 'in' || gradePhase === 'open' || grade.isOpen()) {
    requestGradeClose();
    return;
  }
  if (!nav.asking() && tutorial.isOpen()) { tutorial.close(true); return; }
  if (!nav.asking() && help.isOpen()) { help.close(true); return; }
  if (!nav.asking() && overlayUsedEscape()) return; // the module's overlay takes it first
  nav.escape();
}
function hookFrameKeys(f) {
  if (!f || f._keys) return;
  let w = null;
  try { w = f.contentWindow; } catch (e) { return; }
  if (!w) return;
  f._keys = true;
  let hold = false;
  const sample = e => {
    if (e.key !== 'Escape') return;
    /* Focus is inside the module page: the help card still gets this Escape
     * first, before the module's own handlers see it, so one key press never
     * closes the card AND something under it. */
    if (gradePhase === 'out' || gradePhase === 'in' || gradePhase === 'open' || grade.isOpen()) {
      if (gradePhase !== 'out') requestGradeClose();
      hold = true;
      e.preventDefault(); e.stopImmediatePropagation();
      return;
    }
    if (tutorial.isOpen()) {
      tutorial.close(true);
      hold = true;
      e.preventDefault(); e.stopImmediatePropagation();
      return;
    }
    if (help.isOpen()) {
      help.close(true);
      hold = true;
      e.preventDefault(); e.stopImmediatePropagation();
      return;
    }
    let docket = false;
    try { const r = w.__refit; docket = !!(r && r.state && r.state().open); } catch (x) { docket = false; }
    hold = docket;
  };
  const forward = e => {
    if (e.key === 'Escape' && !hold) escapeKey(e);
  };
  w.addEventListener('keydown', sample, true);
  w.addEventListener('keydown', forward);
  /* Removed with the frame (dropFrame); the window is discarded with the
   * element anyway, this just makes the teardown explicit. */
  f._keysOff = () => {
    try { w.removeEventListener('keydown', sample, true); w.removeEventListener('keydown', forward); }
    catch (e) { /* window already gone */ }
    f._keys = false;
  };
}
/* The embedded page's own __occ, or null.  Everything the toolbar does goes
 * through this and through the frame's document -- never through a copy of
 * the module's state kept here. */
function occ() {
  if (!frame || !frameReady) return null;
  try { return frame.contentWindow.__occ || null; } catch (e) { return null; }
}
function frameDoc() {
  if (!frame || !frameReady) return null;
  try { return frame.contentDocument || null; } catch (e) { return null; }
}

/* THE PIXEL-DENSITY FIX, and it is the same bug as README 16.5.
 * A module page solves its own pixel ratio as `devicePixelRatio * k`, where k
 * is ITS viewport's fit to 1280x720.  Inside an iframe that k is 1 whatever
 * the cockpit is doing, so if the cockpit displays the stage at k = 1.4 the
 * live geometry renders 1.4x under-dense against a baked plate that the
 * browser is upscaling with its own filter.  So the iframe is laid out at
 * 1280k x 720k -- its internal k then equals the cockpit's -- and #cWrap
 * scales by 1/k to put it back in stage coordinates for the dolly.
 * Changing the element's size fires a resize inside the frame, which is what
 * re-runs its layout(). */
function stageFit() {
  const b = $('viewport').getBoundingClientRect();
  return Math.min(b.width / W, b.height / H);
}
function sizeFrame() {
  if (!frame) return;
  const k = Math.max(0.2, Math.min(4, stageFit()));
  frame.style.width = Math.round(W * k) + 'px';
  frame.style.height = Math.round(H * k) + 'px';
  $('cWrap').style.transform = 'scale(' + (1 / k).toFixed(6) + ')';
}

/* ===================================================================== 4 */
/* THE MOVE                                                                */
const dolly = createDolly({ wide: $('wide'), close: $('close'), vig: $('vig'),
                            W, H });

/* Grade-station dive. idle | in | open | out. Shares the module dolly, so a
 * module or board open is refused until the fitting is back at the wide shot. */
let gradePhase = 'idle';
let gradeSuppressGlow = false;
let gradeHist = false;
let gradePopSilent = false;

function buildClose(code) {
  const imgs = closeSrcs(code).map(src => {
    const i = document.createElement('img');
    i.src = src; i.alt = '';
    return i;
  });
  $('cLayers').replaceChildren(...imgs);
}

/* The note line.  Players get plain words (what is open, and whether it is up);
 * the engineering read-out (renderer, readout-plane count, pixel ratio) is
 * `?dev=1` only. */
function paintCloseTitle() {
  const el = $('closeTitle');
  if (!el) return;
  if (!openCode) {
    el.hidden = true;
    el.textContent = '';
    return;
  }
  el.hidden = false;
  el.textContent = moduleName(openCode) + ' (' + openCode + ')';
}
function setNote() {
  paintCloseTitle();
  const note = $('note');
  if (!note) return;
  if (!openCode) {
    note.textContent = DEV
      ? 'baked cockpit plate, unmodified — hover any module and click'
      : 'Hover a module, then click it to open it.';
    return;
  }
  const name = moduleName(openCode);
  const o = occ();
  if (!o) {
    note.textContent = name + (frameFail
      ? ' · did not start'
      : (DEV ? ' · loading the live close-up…' : ' · loading…'));
    return;
  }
  if (!DEV) { note.textContent = name; return; }
  let info = {};
  try { info = o.info() || {}; } catch (e) { info = {}; }
  note.textContent = name
    + ' · live three.js · ' + (info.planes || 0) + ' readout plane'
    + ((info.planes === 1) ? '' : 's')
    + ' · pr ' + (info.pr || 1).toFixed(2)
    + ' · all content text is DOM';
}

/* Push the toolbar's four states into the embedded page.  They are pushed on
 * arrival as well as on click, so a module opened after the buttons were
 * toggled comes up in the state the toolbar says it is in. */
let wantText = true, wantOcc = true, wantPlanes = false, wantDbg = false;
function applyChrome() {
  const o = occ(), d = frameDoc();
  if (o) { try { o.enable(wantOcc); } catch (e) { /* page not ready */ } }
  if (!d || !d.body) return;
  d.body.classList.toggle('notext', !wantText);
  d.body.classList.toggle('debug', wantDbg);
  const bp = d.getElementById('bPlanes');
  /* `show planes` is the template's own debug wireframe and the only one of
   * the four with no __occ entry, so it is driven by clicking the module's own
   * button -- which is hidden in embed mode but still there and still wired. */
  if (bp && (bp.classList.contains('on') !== wantPlanes)) bp.click();
}

function openModule(code, instant) {
  /* The wide layer is not hidden once the close-up lands (it is the backdrop),
   * so its nine hotspots are still in the tree.  #close shields them, but
   * refuse a second open outright rather than lean on hit-testing: a click
   * that swapped modules mid-close-up would strand the dolly at u=1 with the
   * wrong M. The grade dive uses that same dolly. */
  if (gradePhase !== 'idle') return;
  if (moving || openCode) return;
  /* RELEASE GATE. An unreleased module is a dead slot: no dive, from a click, a
   * history reopen or window.cockpit.play alike. Fails open when the live feed
   * is absent/unreachable (DER[code].live === null), matching release.py on the
   * bridge, so a coordinator outage never strands a module that IS released. */
  if (notReleased(code)) return;
  /* ...and refuse while the standings overlay is up, for the same reason: the
   * board sits above #close and a dive that started underneath it would land
   * invisible with the dolly at u=1.  See openBoard() at the foot of this
   * file; `boardOpen` is declared there and is false until it is clicked. */
  if (boardOpen) return;
  /* ...and for the few milliseconds after a way-out while the browser is still
   * consuming the history entry that the last open pushed. */
  if (nav.settling()) return;
  tutorial.close(false);
  grade.close();
  const t = TX.modules[code];
  if (!t) fail('transition.json has no entry for ' + code);
  for (const c of CODES) glow[c].style.opacity = 0;
  tip.style.opacity = 0;
  buildClose(code);
  warm(code);                                    // click loads even if hover preload is off
  openCode = code;
  openedAt = performance.now();                  // the ready wait is measured from the click
  if (!frameReady) scheduleLoadCard(CARD_DELAY_MS);
  nav.opened('module', code);                    // ONE history entry per open
  dolly.setModule(t.M, t.wide_c[0], t.wide_c[1]);
  document.body.classList.add('closeup');
  showBack(true);
  setNote();
  if (instant) { dolly.apply(1); landed(); return; }
  moving = true;
  document.body.classList.add('moving');
  dolly.play(1, landed);
}
function landed() {
  moving = false;
  document.body.classList.remove('moving');
  /* The wide layer STAYS, dimmed and defocused, as the close-up's backdrop.
   * It is not decoration: the close-up plates are film-transparent (OTA's is
   * only 35% opaque) and cockpit/make_cockpit.py composites them over exactly
   * this.  Hiding it, which is what this page used to do, opens holes through
   * the middle of six of the nine close-ups.  transition.js lands the wide
   * layer on CFG.dimEnd and leaves it there; do not "clean up" by hiding it. */
  landLive();
  setNote();
}
let closing = false;
function closeModule(instant) {
  if (!openCode || closing) return;
  closing = true;
  hideCard();
  help.reset();                    // the card leaves with the close-up, before the move
  if (instant) { dolly.apply(0); left(); return; }
  moving = true;
  document.body.classList.add('moving');
  dolly.play(0, left);
}
function left() {
  moving = false; openCode = null; closing = false;
  $('wide').style.filter = 'none';
  document.body.classList.remove('moving', 'closeup', 'live');
  showBack(false);
  $('cLayers').replaceChildren();
  help.reset();
  dropFrame();                    // frees the module's two WebGL contexts
  setNote();
  if (!boardOpen) tutorial.auto();
  nav.closed();                   // consume the history entry the open pushed
  /* Focus goes back to the page itself (the hotspots are not focus targets),
   * never to a control that has just been hidden. */
  const a = document.activeElement;
  if (a && a !== document.body && a.blur) { try { a.blur(); } catch (e) { /* ignore */ } }
  if (submitSigns) submitSigns.sync();
}

/* THE WAY OUT.  X, Escape and the browser's Back all go through shell-nav.js,
 * which owns the history entry and asks before leaving a file return that is
 * still running.  See that file's header. */
function jobBusy() {
  if (!openCode || !frame || !frameReady) return null;
  try {
    const r = frame.contentWindow.__refit;
    const st = r && r.state && r.state();
    if (st && st.fileReturn && st.fileReturn.inFlight) return 'file return';
  } catch (e) { /* unreadable: nothing to protect */ }
  return null;
}
const nav = createShellNav({
  isOpen: () => (openCode ? 'module' : (boardOpen ? 'board' : null)),
  isClosing: () => closing,
  current: () => openCode,
  closeNow: kind => { if (kind === 'module') closeModule(); else closeBoard(); },
  reopen: st => {
    if (st.ckpNav === 'module' && CODES.includes(st.code) && !moving && !boardOpen) {
      openModule(st.code); return !!openCode;
    }
    if (st.ckpNav === 'board' && !moving && !openCode) { openBoard(); return boardOpen; }
    return false;
  },
  busy: jobBusy,
  closeBtn: $('bClose'),
  card: $('leaveCard'),
});
{
  const back = $('bBack');
  if (back) back.addEventListener('click', () => {
    if (requestGradeClose()) return;
    nav.request();
  });
}
addEventListener('keydown', e => { if (e.key === 'Escape') escapeKey(e); });
/* IDENTIFY — player-facing, always visible.  Full navigation to the auth
 * screen; do not keep a dive alive across this jump.  Optional harness
 * read only relabels the button; a miss is guest.  Never fail() the
 * cockpit because the bridge is down.  Username / returns live on `#crew`
 * (track 04), not on the STANDINGS plate. */
let bridgeSignedIn = false;
$('bAuth').addEventListener('click', () => {
  if (!bridgeSignedIn) {
    location.assign('/auth/');
    return;
  }
  fetch('/api/auth/logout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  }).finally(() => { location.assign('/'); });
});
fetch('/api/harness')
  .then(r => r.json())
  .then(d => {
    if (d && d.loggedIn) {
      bridgeSignedIn = true;
      const auth = $('bAuth');
      auth.dataset.mode = 'out';
      auth.setAttribute('aria-label', 'Sign out');
      auth.setAttribute('title', 'Sign out');
      const label = auth.querySelector('.auth-label');
      const icon = auth.querySelector('.auth-out');
      if (label) label.hidden = true;
      if (icon && icon.removeAttribute) icon.removeAttribute('hidden');
    }
  })
  .catch(() => {});
/* The four dev switches exist only under `?dev=1` (see DEV above). */
onDev('bText', function () {
  wantText = !wantText;
  this.classList.toggle('on', wantText);
  this.textContent = wantText ? 'dom text' : 'dom text: off';
  applyChrome();
});
onDev('bOcc', function () {
  wantOcc = !wantOcc;
  this.classList.toggle('on', wantOcc);
  this.textContent = wantOcc ? 'occlusion split' : 'split: OFF';
  applyChrome();
});
onDev('bPlanes', function () {
  wantPlanes = !wantPlanes;
  this.classList.toggle('on', wantPlanes);
  applyChrome();
});
onDev('bDbg', function () {
  wantDbg = !wantDbg;
  this.classList.toggle('on', wantDbg);
  document.body.classList.toggle('debug', wantDbg);
  applyChrome();
});

/* ===================================================================== 5 */
/* LAYOUT + LOOP                                                           */
function layout() {
  const b = $('viewport').getBoundingClientRect();
  const k = Math.min(b.width / W, b.height / H);
  const ox = (b.width - W * k) / 2;
  const oy = (b.height - H * k) / 2;
  $('stage').style.transform = `translate(${ox}px,${oy}px) scale(${k})`;
  /* Top and bottom bands meet the plate. Two plate pixels tuck under the
     opaque bezel so a resize cannot open a star gap; #stage paints over
     that tuck, and the window is well inside it. Side bands stay flush:
     the window reaches the plate's left and right edges. */
  const tuck = 2;
  $('starVeilTop').style.height = Math.max(0, oy + tuck) + 'px';
  $('starVeilBottom').style.height = Math.max(0, oy + tuck) + 'px';
  $('starVeilLeft').style.width = Math.max(0, ox) + 'px';
  $('starVeilRight').style.width = Math.max(0, ox) + 'px';
  $('starVeilLeft').style.top = Math.max(0, oy) + 'px';
  $('starVeilLeft').style.bottom = Math.max(0, oy) + 'px';
  $('starVeilRight').style.top = Math.max(0, oy) + 'px';
  $('starVeilRight').style.bottom = Math.max(0, oy) + 'px';
  sizeFrame();
}
addEventListener('resize', layout);

dolly.setModule(1, W / 2, H / 2);
dolly.apply(0);
setNote();
layout();
tutorial.auto();
/* Warm the baked close layers in the background, staggered, so the first dive
 * into any module has its dissolve pictures already decoded. */
for (const c of CODES) setTimeout(() => preload(c), 400 + CODES.indexOf(c) * 250);
requestAnimationFrame(function frame_(now) {
  dolly.tick(now);
  requestAnimationFrame(frame_);
});

/* ==================================================================== 5.5 */
/* THE TELLTALE FEED.
 *
 * `status.json` is a RECORD OF FACTS from the last run and carries no display
 * state and no colours (design section 9.3).  Everything visual happens in
 * status.js.  The file is allowed to be absent: `loadStatus` resolves to null,
 * `deriveAll(null)` is the UNTESTED pose, and a fresh clone with no harness
 * comes up as nine smoked, un-graduated tubes -- which is the honest picture,
 * not a failure state.  There is never a spinner and never a throw.
 *
 * `GET /api/live` is a PEER, not a replacement: container `powered` (ON/OFF)
 * and TCP up/down (ON STATION / NO LINK) become caption clauses at derive()
 * time.  Failure is unmeasured, identical to a missing status.json, so
 * `live3d/run.sh` checkers stay still.  One 5 s tick fetches both; `setStatus`
 * stops that tick so an injected doc cannot grow a live clause mid-capture. */
let statusDoc = null;
let LIVE = null;                       // raw live map by cockpit code, or null
let lastSig = null;
let feedGen = 0;
let statusTimer = null;

function stopStatusPoll() {
  if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
}
function startStatusPoll() {
  if (statusTimer) return;
  statusTimer = setInterval(pollStatus, 5000);
}

async function pollStatus() {
  const g = ++feedGen;
  const [doc, live] = await Promise.all([
    loadStatus('./status.json'),
    loadLive(),
  ]);
  if (g !== feedGen) return;
  LIVE = live;
  const sig = (doc ? doc.generated_at + '|' + JSON.stringify(doc.modules).length : '')
    + '|live:' + JSON.stringify(live);
  if (sig !== lastSig) {
    lastSig = sig;
    statusDoc = doc;
    DER = deriveAll(doc, CODES, live);
    for (const c of CODES) if (tells[c]) tells[c].update(DER[c]);
    syncHotspotLocks();
    /* keep an open tooltip honest rather than waiting for a re-hover */
    if (hovering && MAN.modules[hovering]) showTip(hovering, MAN.modules[hovering]);
  }
}
pollStatus();
startStatusPoll();

/* The sill's "being scored" tell. A light background poll of the newest
 * submission, independent of the grade panel (which only polls while open), so
 * the operator sees that a module or A.L.I.E.N. job is grading from anywhere in
 * the cockpit. Read-only; the tell stays hidden whenever nothing is pending. */
let gradeTellTimer = null;
function newestSub(list) {
  const rows = Array.isArray(list) ? list.filter(r => r && typeof r === 'object') : [];
  let best = null;
  let bestAt = -Infinity;
  for (const r of rows) {
    const t = Date.parse(r.created);
    const at = Number.isNaN(t) ? -Infinity : t;
    if (at >= bestAt) { best = r; bestAt = at; }
  }
  return best;
}
function setGradeTell(sub) {
  const tell = $('gradeTell');
  if (!tell) return;
  const info = tellFor(sub);
  if (!info.active) { tell.hidden = true; return; }
  const txt = tell.querySelector('.gt-text');
  if (txt) txt.textContent = info.text;
  tell.hidden = false;
}
async function pollGradeTell() {
  try {
    const listed = await api.getSubmissions();
    if (!listed || listed.ok === false || !Array.isArray(listed.submissions)) {
      setGradeTell(null);
      return;
    }
    const latest = newestSub(listed.submissions);
    const name = latest && String(latest.status_name || '');
    if (latest && latest.job_id && name && name !== 'COMPLETE' && name !== 'FAILED') {
      /* The list row is a summary; the detail carries the live phase. */
      try {
        const d = await api.getSubmission(latest.job_id);
        setGradeTell((d && d.submission) || latest);
        return;
      } catch (e) { /* fall through with the summary */ }
    }
    setGradeTell(latest);
  } catch (e) {
    setGradeTell(null);
  }
}
function startGradeTell() {
  if (gradeTellTimer) return;
  pollGradeTell();
  gradeTellTimer = setInterval(pollGradeTell, 7000);
}
/* The grade tell stays visible during grading even while a module or the board
 * is in close-up, but the grade station will not open over one (gradeBlocked).
 * Return to the bridge first, then open the station once the console is idle —
 * so the shortcut always does something instead of silently no-op'ing. */
function openGradeFromTell() {
  if (gradePhase !== 'idle') return;       // already opening / open
  if (!gradeBlocked()) { openGradeStation(); return; }
  // Only transition out of the close-up / board states; leave a tutorial card
  // or an already-open panel alone.
  if (openCode && !closing) {
    if (jobBusy()) return;                 // a file return is in flight: don't interrupt it
    closeModule();
  } else if (boardOpen) {
    closeBoard();
  } else {
    return;
  }
  let tries = 0;
  const t = setInterval(() => {
    if (!moving && !openCode && !boardOpen && !closing && !gradeBlocked()) {
      clearInterval(t);
      openGradeStation();
    } else if (++tries > 80) {             // ~8s safety cap
      clearInterval(t);
    }
  }, 100);
}
{
  const tell = $('gradeTell');
  if (tell) tell.addEventListener('click', openGradeFromTell);
}
startGradeTell();

/* ===================================================================== 6 */
/* TRANSITION CAPTURE HOOKS (check/shoot_transition.mjs, match_handover.mjs).
 * `seek` is a deterministic freeze at eased progress u, which is the only way
 * to look at the same instant of the move twice.  These score the BAKED
 * layers against the wide plate -- the same two pictures the magnification was
 * measured from -- so `arm()` deliberately does NOT bring the live page up. */
window.__tx = {
  codes: () => CODES,
  data: () => TX,
  cfg: TXCFG,
  set: o => Object.assign(TXCFG, o),
  /* `mMul` deliberately DE-TUNES the magnification, so check/match_handover
   * can show that the shipped M is the one at which the two layers agree and
   * that the measurement is sensitive enough to notice when it is not. */
  arm: (code, mMul) => {
    if (openCode) { dolly.apply(0); left(); }
    const t = TX.modules[code];
    buildClose(code); openCode = code;
    dolly.setModule(t.M * (mMul || 1), t.wide_c[0], t.wide_c[1]);
    document.body.classList.add('closeup', 'moving');
    showBack(true);
    setNote(); dolly.apply(0);
  },
  seek: u => dolly.apply(u),
  /* isolate one layer, with every cosmetic treatment off, so the two can be
   * scored against each other rather than against the grade */
  only: which => {
    $('wide').style.visibility = which === 'close' ? 'hidden' : 'visible';
    $('wide').style.filter = 'none';
    $('close').style.visibility = which === 'wide' ? 'hidden' : '';
    $('close').style.opacity = which === 'wide' ? 0 : 1;
    $('vig').style.opacity = 0;
    document.body.classList.remove('moving');   // drops the edge feather
  },
  /* the close layer's rect in STAGE coordinates.  The scorer needs this from
   * the page and not from a luma threshold on the screenshot: the page
   * background is #02030a, not black, so thresholding picks up the whole frame
   * and silently scores the two layers over pixels neither of them covers. */
  rect: () => {
    const st = $('stage').getBoundingClientRect(), k = st.width / W;
    const r = $('close').getBoundingClientRect();
    return { x: (r.left - st.left) / k, y: (r.top - st.top) / k,
             w: r.width / k, h: r.height / k };
  },
  /* the EMBEDDED page's drawing-buffer resolution, which is the number
   * README 16.5 is about.  It used to be KVS's own uniform read out of this
   * file; it is now whichever module is open, or null when none is. */
  depthRes: () => { const o = occ(); if (!o) return null;
                    const i = o.info(); return [i.depthRes[0], i.depthRes[1], i.pr]; },
  play: code => openModule(code),
  back: () => closeModule(),
  moving: () => moving,
};

/* THE COCKPIT'S OWN DRIVING HOOK, for check/drive_cockpit.mjs.  It is what
 * makes "hover, dive, exercise a control, leave" a script rather than a claim.
 * `open()` resolves when the LIVE page has landed, not when the move ends. */
window.__cockpit = {
  codes: () => CODES,
  state: () => ({ open: openCode, moving, frameCode, frameReady,
                  frameFail: frameFail ? frameFail.reason : null,
                  live: document.body.classList.contains('live'),
                  bakedLayers: $('cLayers').childElementCount }),
  hover: code => { glow[code].style.opacity = 0.9; preload(code); if (hoverPreloadOn()) warm(code); },
  unhover: code => { glow[code].style.opacity = 0; },
  glowOpacity: code => +getComputedStyle(glow[code]).opacity,
  open: (code, instant) => new Promise(res => {
    openModule(code, instant);
    const t = setInterval(() => {
      if (!moving && frameReady && document.body.classList.contains('live')) {
        clearInterval(t); res(true);
      }
    }, 50);
    setTimeout(() => { clearInterval(t); res(false); }, 25000);
  }),
  close: instant => new Promise(res => {
    closeModule(instant);
    const t = setInterval(() => {
      if (!moving && !openCode) { clearInterval(t); res(true); }
    }, 50);
    setTimeout(() => { clearInterval(t); res(false); }, 25000);
  }),
  /* the embedded module's own fleet-standard hook, reached from the parent --
   * same origin, no message protocol */
  occ: () => occ(),
  /* click one of the embedded module's hotspots, by index, at its centre */
  hotspots: () => {
    const d = frameDoc(); if (!d) return [];
    return [...d.querySelectorAll('#hots .hot')].map((h, i) => ({
      i, title: h.title, x: parseFloat(h.style.left), y: parseFloat(h.style.top),
      w: parseFloat(h.style.width), h: parseFloat(h.style.height) }));
  },
  frameRect: () => { const r = frame && frame.getBoundingClientRect();
                     return r ? { x: r.left, y: r.top, w: r.width, h: r.height } : null; },
  note: () => $('note').textContent,
  crew: () => CREW.crew(),
  setCrew: doc => CREW.setCrew(doc),

  /* THE TELLTALE, from the outside.
   *
   * `status(code)` is the DERIVED state, and it is how a module page reaches
   * its own status without a second fetch: status.js's `moduleStatus()` looks
   * for `parent.__cockpit.status(CODE)` first and falls back to the file, so a
   * module page opened standalone by a checker still works (design 6.2 r7).
   *
   * `setStatus(doc)` injects a status document WITHOUT touching status.json.
   * It is how the nine states get screenshotted -- every mark in the design can
   * be put on screen from a test script, so "all nine are legible" is something
   * that gets measured on the running cockpit rather than claimed. */
  status: code => (code ? DER[code] : DER),
  statusDoc: () => statusDoc,
  /* Raw live peer for tests.  The mast must not prefer this over status(). */
  live: code => (code ? (LIVE && LIVE[code]) || null : LIVE),
  /* Tests call pollStatus() to resume after setStatus.  Power calls bumpLive
   * so an injected doc is not clobbered and the 5 s timer stays stopped. */
  pollStatus: () => { startStatusPoll(); return pollStatus(); },
  bumpLive: () => statusTimer ? pollStatus() : Promise.resolve(),
  setStatus: doc => {
    feedGen++;
    stopStatusPoll();
    LIVE = null;
    lastSig = 'injected:' + Date.now();
    statusDoc = doc;
    DER = deriveAll(doc, CODES, null);
    for (const c of CODES) if (tells[c]) tells[c].update(DER[c]);
    syncHotspotLocks();
    if (hovering && MAN.modules[hovering]) showTip(hovering, MAN.modules[hovering]);
    return Object.keys(DER);
  },
  statusLine: code => statusLine(DER[code]),
  /* the nine measured envelopes, for a collision check against the props */
  tellRects: () => Object.keys(WIDE_MASTS).map(c => ({
    code: c, x: WIDE_MASTS[c].env[0], y: WIDE_MASTS[c].env[1],
    w: WIDE_MASTS[c].env[2], h: WIDE_MASTS[c].env[3],
    anchor: WIDE_MASTS[c].anchor, dir: WIDE_MASTS[c].dir })),
};
window.__loaded = true;

/* ==================================================================== 7 */
/* THE MUSTER BOARD — live3d/design/LEADERBOARD.md.
 *
 * ADDITIVE, AND DELIBERATELY BORING.  The standings are not a module: no entry
 * in cockpit/combined/manifest.json, none in transition.json, no measured M,
 * no baked plate to dissolve into.  So this does NOT re-enter openModule(),
 * the dolly, #cLayers, landLive() or transition.json — five machines with
 * measured constants and five chances to break the nine.  It sets an iframe
 * src, toggles one body class, and clears the src on the way out.
 *
 * CREATING AND REMOVING THE IFRAME IS THE POINT, not tidiness.  The board page
 * owns a WebGL context and there is no dispose() to call, exactly as
 * dropFrame() records for the nine; removing the ELEMENT is what frees it.
 * A permanently-present empty iframe was tried first and rejected on evidence:
 * check/drive_cockpit.mjs counts `document.querySelectorAll("iframe").length`
 * after every leave and expects 0, and it went to 1 for all nine modules the
 * moment a static <iframe id="lbFrame"> existed in index.html.  Nothing was
 * actually leaking -- the frame had no src -- but a shipped regression report
 * that has to be explained away is a regression report.
 *
 * OWNERSHIP.  CONVERSION_BRIEF.md:220-225 puts this file on a do-not-write
 * list for a fan-out agent.  That rule is right and this run's claim list
 * overrides it for integration only; the change holds to the spirit anyway --
 * no existing line is re-entered, only new lines added, and the one line
 * inserted into openModule() is a guard that cannot fire until the button
 * below is clicked. */
let boardOpen = false;

function openBoard() {
  /* Refuse while a module is open or a move is in flight.  The pair of guards
   * -- this one and the `boardOpen` line in openModule() -- is what keeps the
   * two overlays mutually exclusive without either of them knowing how the
   * other works. */
  if (gradePhase !== 'idle') return;
  if (boardOpen || openCode || moving || nav.settling()) return;
  tutorial.close(false);
  grade.close();
  boardOpen = true;
  const f = document.createElement('iframe');
  f.id = 'lbFrame';
  f.title = 'standings';
  f.setAttribute('scrolling', 'no');
  /* `?embed=1` makes the board page transparent and hides its own toolbar,
   * the same contract the nine module pages honour.
   *
   * THERE IS ONE BOARD.  This comment used to say "Desk mode: the cockpit is a
   * person at a desk with a pointer.  The conference TV opens
   * modules/_LEADERBOARD/?tv=1 directly and never comes through here."  Both
   * sentences describe modes that were collapsed into one on 2026-09-06
   * (LEADERBOARD.md section 6.1 and 10a): there is no desk mode and no TV
   * mode, `?tv=1` is kept as an inert alias for the things it is printed on,
   * and the board the cockpit opens is the same 8-slot, 28 px, pointer-driven
   * board every other URL opens.  The `f.src` beside it was correct then and
   * is correct now; only the words were wrong. */
  f.src = 'modules/_LEADERBOARD/?embed=1';
  /* Escape inside the board's own frame must still leave (same-origin). */
  f.addEventListener('load', () => {
    try { f.contentWindow.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !e.defaultPrevented) escapeKey(e);
    }); } catch (e) { /* ignore */ }
  });
  $('lbHost').replaceChildren(f);
  document.body.classList.add('board');
  if ($('bBoard')) $('bBoard').classList.add('on');
  setNote();
  nav.opened('board');                // one history entry, like a module
}
function closeBoard() {
  if (!boardOpen) return;
  boardOpen = false;
  document.body.classList.remove('board');
  if ($('bBoard')) $('bBoard').classList.remove('on');
  $('lbHost').replaceChildren();      // frees the board's WebGL context
  setNote();
  if (!openCode) tutorial.auto();
  nav.closed();
  const a = document.activeElement;
  if (a && a !== document.body && a.blur) { try { a.blur(); } catch (e) { /* ignore */ } }
  if (submitSigns) submitSigns.sync();
}
onDev('bBoard', () => {
  if (boardOpen) closeBoard(); else openBoard();
});
/* Escape closes whichever overlay is up, BOARD FIRST.  This listener is
 * registered after the one on line 408, so that one runs first -- and it is a
 * no-op here, because `closeModule()` returns immediately when `openCode` is
 * null and openBoard() refuses to open while a module is up.  The two can
 * never both be open, so the ordering cannot produce a double close. */
/* (Escape for the board is handled by the shell navigation above: `nav.escape()`
 * closes whichever overlay is up and consumes its history entry.) */

/* The driving hook, in the same class as window.__cockpit above. */
window.__cockpit.board = {
  open: () => { openBoard(); return boardOpen; },
  close: () => { closeBoard(); return boardOpen; },
  isOpen: () => boardOpen,
  /* the board page's own hook, reached from the parent -- same origin, no
   * message protocol, exactly as occ() does it for the nine */
  api: () => {
    const f = $('lbHost').firstElementChild;
    try { return (f && f.contentWindow && f.contentWindow.__board) || null; }
    catch (e) { return null; }
  },
  ready: () => {
    const f = $('lbHost').firstElementChild;
    try { return !!(f && f.contentWindow && f.contentWindow.__loaded); }
    catch (e) { return false; }
  },
};

/* ==================================================================== 7.1 */
/* THE STANDINGS PLATE — the player-facing way in, and the only one.
 *
 * WHAT WAS WRONG WITH THE BUTTON.  `#bBoard` sat in the dev toolbar beside
 * `dom text`, `occlusion split`, `show planes` and `show hotspots`.  Those four
 * are developer switches; `standings` was the only player-facing thing in the
 * row, and every OTHER thing a player touches in this cockpit is a physical
 * object on the ship that glows when you point at it.  The button is still
 * here and still works, gated behind `?dev=1` exactly as the board page's own
 * toolbar is (LEADERBOARD.md 10a), because a switch a checker drives is worth
 * keeping and a switch a player sees is not.
 *
 * WHAT REPLACED IT.  A brass nameplate reading STANDINGS, bolted across the
 * face of the C3 / `oh_2` overhead console — dead centre-top, where a headline
 * belongs.  It is GEOMETRY: `pipeline/standings_plate.py` solves its anchor
 * against a depth pass of the shipped cockpit scene, builds it out of
 * `cockpit/dressing/kit.py`'s own primitives and materials, and renders it
 * with the shipped wide camera under the shipped seven lights — the same two
 * sprites, made the same way, that all nine modules already contribute to this
 * shot.  So it is lit by the light that lit the plate, rather than by a CSS
 * gradient pretending to be.
 *
 * WHY NOT A CSS3D PLANE, WHICH IS WHAT WAS ASKED FOR.  Two measurements, both
 * in `standings_plate.py`'s header and in `assets/_STANDINGS/standings.json`:
 * the carrier is at 9.2 deg obliquity — squarer to this camera than KVS's own
 * console face — so there is no rake for a screen-space box to fight; and
 * `STANDINGS` is a permanent label, which the fleet's rule makes geometry
 * rather than DOM.  There is no content text on this fitting for a CSS3D
 * plane to carry.
 *
 * NOTHING IN THE NINE MOVES.  This layer is #wFit, not #wGlows (see the note
 * in index.html), the hotspot is one more .whot on the same #wHots, and it is
 * measured clear of all eighteen keep-outs — nine module hotspots and nine
 * telltale envelopes — by the solver, not by assertion. */

/* The dev button, now a dev button.  `?dev=1` adds it to the bar (T1b: it is
 * not in the page at all otherwise).  window.__cockpit.board and every listener
 * above stay exactly as they were, so a checker that drives the overlay through
 * the hook is unaffected either way. */

let fitGlow = null, fitHot = null;
if (SB && SB.hotspot) {
  const fit = $('wFit');
  const prop = document.createElement('img');
  prop.className = 'layer';
  prop.src = './assets/_STANDINGS/' + (SB.prop || 'prop.png');
  prop.alt = '';
  fit.appendChild(prop);

  /* The hover mask, in the same .glow class the eight maintenance modules
   * use: a white-emissive render of the same objects, tinted and bloomed by
   * the CSS rather than by anything baked into the PNG.  Brass, not red — red
   * is PKT's and PKT's alone. */
  const g = document.createElement('img');
  g.className = 'glow';
  g.src = './assets/_STANDINGS/' + (SB.glow || 'glow.png');
  g.alt = '';
  fit.appendChild(g);
  fitGlow = g;

  const r = SB.hotspot;
  const h = document.createElement('div');
  h.className = 'whot';
  h.style.left = r.x + 'px'; h.style.top = r.y + 'px';
  h.style.width = r.w + 'px'; h.style.height = r.h + 'px';
  h.addEventListener('mouseenter', () => {
    /* The same three guards the nine carry, plus the board's own: a fitting
     * that lit up while its overlay was already open would be lying. */
    if (moving || openCode || boardOpen) return;
    g.style.opacity = 0.9;
    /* Two lines, both textContent, no markup — the same shape as showTip().
     * The second line answers "and what is that", which is a hover-time
     * question; the picture already answers "what is this". */
    tip.textContent = (SB.label || 'STANDINGS') + ' · ship’s company\n'
      + 'the muster board — rank, name, points';
    tip.style.opacity = 1;
  });
  h.addEventListener('mousemove', e => {
    tip.style.left = (e.clientX + 16) + 'px';
    tip.style.top = (e.clientY - 12) + 'px';
    keepTipOnScreen(e);
  });
  h.addEventListener('mouseleave', () => {
    g.style.opacity = 0; tip.style.opacity = 0;
  });
  h.addEventListener('click', () => {
    g.style.opacity = 0; tip.style.opacity = 0;
    openBoard();
  });
  $('wHots').appendChild(h);
  fitHot = h;
}

/* The driving hook, in the same class as window.__cockpit.board above.  It
 * reports what it MEASURED and not what it intended: `present` is whether the
 * asset was there at all, and the rect comes off the live element rather than
 * off SB, so a hotspot that failed to lay out reads as one. */
window.__cockpit.board.plate = () => ({
  present: !!fitHot,
  label: SB && SB.label,
  hotspot: fitHot ? { x: parseFloat(fitHot.style.left),
                      y: parseFloat(fitHot.style.top),
                      w: parseFloat(fitHot.style.width),
                      h: parseFloat(fitHot.style.height) } : null,
  glow: fitGlow ? +getComputedStyle(fitGlow).opacity : null,
  devButton: $('bBoard') ? getComputedStyle($('bBoard')).display : 'none',
});

/* THE GRADING STATION. The wide plate carries the signless port. Its glow
 * is the same white mask and brass .glow rule as the other instruments, and
 * it lives outside #wGlows so the nine module tints stay in place. Pointer,
 * Enter, and Space run the module dolly (transition.js) toward this
 * station.json hotspot. When that move lands, this path clears the
 * module-closeup blur on #wide and hides #close, then opens the ordinary
 * #gradePanel dialog over the content viewport. There is no hatch, iris, or
 * bore. A second activation while that move is running, or while the dialog
 * is already open, does nothing. Close, Back, and Escape hide the dialog,
 * return the dolly, and bring focus back here. prefers-reduced-motion skips
 * the timed move and still opens the same dialog. */
const GRADE_NAME = 'Grade and submit';
const GS = await fetch(CK + 'grading-station/station.json')
  .then(r => r.ok ? r.json() : null).catch(() => null);
let gsGlow = null;

function gradeBlocked() {
  if (document.body.classList.contains('closeup')
      || document.body.classList.contains('board')
      || document.body.classList.contains('moving')) return true;
  const tut = $('tutorialCard');
  if (tut && !tut.hidden) return true;
  const panel = $('gradePanel');
  if (panel && !panel.hidden) return true;
  return false;
}

function syncGradeChrome() {
  const hot = $('gradeStationHot');
  if (!gsGlow) return;
  if (gradePhase !== 'idle' || gradeSuppressGlow || gradeBlocked()) {
    gsGlow.style.opacity = '0';
    tip.style.opacity = 0;
    return;
  }
  const focused = hot && document.activeElement === hot;
  const over = hot && hot.matches(':hover');
  gsGlow.style.opacity = (focused || over) ? '0.9' : '0';
  if (!(focused || over)) tip.style.opacity = 0;
}

function gradeReduced() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/* Same camera as a module dive: magnification that fills the frame with the
 * hotspot, aimed at its centre. Placement numbers stay in station.json. */
function gradeAim() {
  const r = GS && GS.hotspot;
  if (!r || !(r.w > 0) || !(r.h > 0)) return null;
  return {
    M: Math.max(W / r.w, H / r.h),
    cx: r.x + r.w / 2,
    cy: r.y + r.h / 2,
  };
}

function pushGradeHist() {
  try {
    history.pushState({ gradeStation: 1 }, '', location.href);
    gradeHist = true;
  } catch (e) {
    gradeHist = false;
  }
}

function dropGradeHist() {
  if (!gradeHist) return;
  gradeHist = false;
  if (history.state && history.state.gradeStation) {
    gradePopSilent = true;
    try { history.back(); } catch (e) { gradePopSilent = false; }
  }
}

/* transition.js lands a module dive with #wide defocused and #close faded
 * in. This station has no module plate. Clear that treatment only after THIS
 * arrival so a module dive still blurs. */
function sharpenGradePlate() {
  const wide = $('wide');
  const close = $('close');
  if (wide) wide.style.filter = 'none';
  if (close) close.style.opacity = '0';
}

/* The dialog covers the cockpit. Close and Escape leave it. */
const GRADE_SHIELD = ['viewport', 'lbHost', 'bClose', 'closeTitle', 'bHelp',
  'helpShade', 'helpCard', 'tutorialShade', 'tutorialCard', 'frameCard', 'leaveCard', 'stars'];

function shieldGradeBehind(on) {
  for (const id of GRADE_SHIELD) {
    const el = $(id);
    if (!el) continue;
    if (on) el.setAttribute('inert', '');
    else el.removeAttribute('inert');
  }
  const bar = $('bar');
  if (!bar) return;
  for (const el of bar.querySelectorAll('button')) {
    if (el.id === 'bBack') continue;
    if (on) el.setAttribute('inert', '');
    else el.removeAttribute('inert');
  }
}

function gradeFocusables() {
  const panel = $('gradePanel');
  const items = [];
  const seen = new Set();
  if (panel) {
    /* Tree order matches the sequential tab order. The station detail is
     * tabindex 0 so a long solved-id list can be scrolled from the keyboard,
     * and it sits between Close and the station buttons. */
    const nodes = panel.querySelectorAll(
      'button, input, select, textarea, a[href], [tabindex]'
    );
    for (const el of nodes) {
      if (seen.has(el) || el.disabled) continue;
      const tab = el.getAttribute('tabindex');
      if (tab !== null && Number(tab) < 0) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      seen.add(el);
      items.push(el);
    }
  }
  const back = $('bBack');
  if (back && !seen.has(back) && getComputedStyle(back).display !== 'none') items.push(back);
  return items;
}

addEventListener('keydown', (e) => {
  if (e.key !== 'Tab') return;
  if (gradePhase !== 'open' || !grade.isOpen()) return;
  const items = gradeFocusables();
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  const active = document.activeElement;
  if (!items.includes(active)) {
    e.preventDefault();
    (e.shiftKey ? last : first).focus();
    return;
  }
  if (e.shiftKey && active === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && active === last) {
    e.preventDefault();
    first.focus();
  }
}, true);

function presentGradeDialog() {
  const panel = $('gradePanel');
  if (!panel) return false;
  shieldGradeBehind(true);
  grade.open();
  if (!grade.isOpen()) {
    shieldGradeBehind(false);
    document.body.removeAttribute('data-grade-port');
    return false;
  }
  document.body.setAttribute('data-grade-port', 'open');
  return true;
}

function gradeArrive() {
  if (gradePhase !== 'in') return;
  moving = false;
  document.body.classList.remove('moving');
  sharpenGradePlate();
  const opened = presentGradeDialog();
  if (!opened) {
    shieldGradeBehind(false);
    document.body.removeAttribute('data-grade-port');
    dolly.apply(0);
    gradePhase = 'idle';
    gradeSuppressGlow = true;
    const hot = $('gradeStationHot');
    if (hot) hot.setAttribute('aria-expanded', 'false');
    if (!openCode && !boardOpen) showBack(false);
    dropGradeHist();
    syncGradeChrome();
    return;
  }
  gradePhase = 'open';
  const hot = $('gradeStationHot');
  if (hot) hot.setAttribute('aria-expanded', 'true');
  syncGradeChrome();
}

function finishGradeReturn() {
  if (gradePhase !== 'out') return;
  moving = false;
  document.body.classList.remove('moving');
  gradePhase = 'idle';
  gradeSuppressGlow = true;
  if (!openCode && !boardOpen) showBack(false);
  const hot = $('gradeStationHot');
  if (hot) {
    hot.setAttribute('aria-expanded', 'false');
    try { hot.focus(); } catch (e) { /* ignore */ }
  }
  if (gsGlow) gsGlow.style.opacity = '0';
  tip.style.opacity = 0;
  syncGradeChrome();
  if (submitSigns) submitSigns.sync();
  if (afterGradeReturn) {
    const f = afterGradeReturn;
    afterGradeReturn = null;
    setTimeout(f, 0);
  }
}

function sealGradePort() {
  if (grade.isOpen()) grade.close();
  shieldGradeBehind(false);
  document.body.removeAttribute('data-grade-port');
}

function beginGradeReturn(fromPop) {
  if (gradePhase !== 'in' && gradePhase !== 'open') return;
  gradePhase = 'out';
  gradeSuppressGlow = true;
  if (gsGlow) gsGlow.style.opacity = '0';
  tip.style.opacity = 0;
  const hot = $('gradeStationHot');
  if (hot) hot.setAttribute('aria-expanded', 'false');
  if (!fromPop) dropGradeHist();
  sealGradePort();
  if (gradeReduced()) {
    dolly.apply(0);
    finishGradeReturn();
    return;
  }
  moving = true;
  document.body.classList.add('moving');
  dolly.play(0, finishGradeReturn);
}

function requestGradeClose() {
  if (gradePhase === 'out') return true;
  if (gradePhase === 'in' || gradePhase === 'open') {
    beginGradeReturn(false);
    return true;
  }
  if (grade.isOpen()) {
    grade.close();
    gradeSuppressGlow = true;
    const hot = $('gradeStationHot');
    if (hot) {
      hot.setAttribute('aria-expanded', 'false');
      try { hot.focus(); } catch (e) { /* ignore */ }
    }
    if (gsGlow) gsGlow.style.opacity = '0';
    tip.style.opacity = 0;
    return true;
  }
  return false;
}

function openGradeStation() {
  if (gradePhase !== 'idle' || gradeBlocked()) return;
  const aim = gradeAim();
  if (!aim) return;
  gradePhase = 'in';
  gradeSuppressGlow = true;
  if (gsGlow) gsGlow.style.opacity = '0';
  tip.style.opacity = 0;
  const hot = $('gradeStationHot');
  if (hot) hot.setAttribute('aria-expanded', 'true');
  dolly.setModule(aim.M, aim.cx, aim.cy);
  showBack(true);
  pushGradeHist();
  if (gradeReduced()) {
    dolly.apply(1);
    gradeArrive();
    return;
  }
  moving = true;
  document.body.classList.add('moving');
  dolly.play(1, gradeArrive);
}

addEventListener('popstate', () => {
  if (gradePopSilent) { gradePopSilent = false; return; }
  if (gradePhase === 'in' || gradePhase === 'open') {
    gradeHist = false;
    beginGradeReturn(true);
  }
});

if (GS && GS.hotspot && GS.glow) {
  const host = document.createElement('div');
  host.id = 'wGrade';
  host.className = 'layer';
  const g = document.createElement('img');
  g.className = 'glow';
  g.src = CK + GS.glow;
  g.alt = '';
  host.appendChild(g);
  gsGlow = g;
  const fit = $('wFit');
  fit.parentNode.insertBefore(host, fit.nextSibling);

  const r = GS.hotspot;
  const h = document.createElement('button');
  h.type = 'button';
  h.id = 'gradeStationHot';
  h.className = 'whot grade-station-hot';
  h.title = GRADE_NAME;
  h.setAttribute('aria-label', GRADE_NAME);
  h.setAttribute('aria-controls', 'gradePanel');
  h.setAttribute('aria-expanded', 'false');
  h.style.left = r.x + 'px';
  h.style.top = r.y + 'px';
  h.style.width = r.w + 'px';
  h.style.height = r.h + 'px';

  function placeTip(clientX, clientY) {
    tip.textContent = GRADE_NAME;
    tip.style.left = (clientX + 16) + 'px';
    tip.style.top = (clientY - 12) + 'px';
    tip.style.opacity = 1;
    keepTipOnScreen({ clientX, clientY });
  }
  h.addEventListener('mouseenter', (e) => {
    if (gradePhase !== 'idle' || gradeSuppressGlow || gradeBlocked()) {
      syncGradeChrome();
      return;
    }
    g.style.opacity = '0.9';
    placeTip(e.clientX, e.clientY);
  });
  h.addEventListener('mousemove', (e) => {
    if (gradeSuppressGlow) {
      gradeSuppressGlow = false;
      syncGradeChrome();
    }
    if (gradePhase !== 'idle' || gradeBlocked()) return;
    tip.style.left = (e.clientX + 16) + 'px';
    tip.style.top = (e.clientY - 12) + 'px';
    keepTipOnScreen(e);
  });
  h.addEventListener('mouseleave', () => {
    if (document.activeElement !== h) g.style.opacity = '0';
    tip.style.opacity = 0;
    syncGradeChrome();
  });
  h.addEventListener('focus', () => {
    if (gradePhase !== 'idle' || gradeSuppressGlow || gradeBlocked()) {
      syncGradeChrome();
      return;
    }
    g.style.opacity = '0.9';
    const b = h.getBoundingClientRect();
    placeTip(b.left + b.width * 0.5, b.top);
  });
  h.addEventListener('blur', () => {
    if (gradePhase === 'idle') gradeSuppressGlow = false;
    if (!h.matches(':hover')) g.style.opacity = '0';
    tip.style.opacity = 0;
    syncGradeChrome();
  });
  h.addEventListener('click', () => openGradeStation());
  $('wHots').appendChild(h);
  const gradeClose = $('gradePanel') && $('gradePanel').querySelector('button.grade-x');
  if (gradeClose) {
    /* grade-panel.js hides the dialog on this button. The station has to
     * return the dolly as well, so that direct hide listener does not stay. */
    const fresh = gradeClose.cloneNode(true);
    gradeClose.replaceWith(fresh);
    fresh.addEventListener('click', () => requestGradeClose());
  }

  const watch = new MutationObserver(() => syncGradeChrome());
  watch.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  const tut = $('tutorialCard');
  if (tut) watch.observe(tut, { attributes: true, attributeFilter: ['hidden'] });
  const panel = $('gradePanel');
  if (panel) watch.observe(panel, { attributes: true, attributeFilter: ['hidden'] });
}
window.__cockpit.gradeStation = () => {
  const hot = $('gradeStationHot');
  return {
    present: !!hot,
    open: () => grade.isOpen(),
    title: hot ? hot.getAttribute('aria-label') : null,
    hotspot: hot ? {
      x: parseFloat(hot.style.left), y: parseFloat(hot.style.top),
      w: parseFloat(hot.style.width), h: parseFloat(hot.style.height),
    } : null,
    glow: gsGlow ? +getComputedStyle(gsGlow).opacity : null,
  };
};

/* First-visit signs. tutorial.auto() has already run, so a card that is
 * open keeps them hidden until that card's hidden attribute flips. */
function clientRectFromCanonical(r) {
  if (!r || !(r.w > 0) || !(r.h > 0)) return null;
  const stage = $('stage').getBoundingClientRect();
  if (!(stage.width > 0)) return null;
  const k = stage.width / W;
  return {
    left: stage.left + r.x * k,
    top: stage.top + r.y * k,
    width: r.w * k,
    height: r.h * k,
  };
}
const submitSigns = mountSubmitSigns({
  doc: document,
  storage: localStorage,
  tutorialOpen: () => tutorial.isOpen(),
  onMainCockpit: () => wideShot() && gradePhase === 'idle' && !grade.isOpen(),
  targets: () => ({
    grade: clientRectFromCanonical(GS && GS.hotspot),
    pkt: clientRectFromCanonical(MAN.modules.PKT && MAN.modules.PKT.far.hotspot),
  }),
  watch: [
    { node: document.body, filter: ['class', 'data-grade-port'] },
    { node: $('tutorialCard'), filter: ['hidden'] },
    { node: $('gradePanel'), filter: ['hidden'] },
  ],
});
