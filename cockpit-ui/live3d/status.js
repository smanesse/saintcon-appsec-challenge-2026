/* SAINTCON 2026 — THE TELLTALE MAST.  ONE SOURCE, ONE DERIVATION, TWO RENDERERS.
 *
 * WHAT THIS FILE IS
 * -----------------
 * `live3d/design/STATUS_AT_A_GLANCE.md` section 6.4 asks for exactly one place
 * where the mapping from FACTS (status.json) to MARKS (a drawn mast) lives, so
 * that the wide shot and any close-up counterpart cannot drift apart.  This is
 * that place, and it has three parts:
 *
 *   1. `derive(record, opts)`  — facts in, display state out.  No colours.
 *   2. `createMast(...)`       — the SVG component, built with createElementNS.
 *   3. `WIDE_MASTS`            — the measured wide-shot placement table.
 *
 * `status.json` carries NO display state and NO colours (section 9.3).  Every
 * colour in the indicator is in this file and nowhere else.
 *
 * NO innerHTML.  Every node here is `document.createElementNS` and every string
 * reaches the page through `textContent`.  `grep -nE "\.innerHTML\s*(=|\+=)"`
 * over this file is empty, and CONVERSION_BRIEF section 7 is absolute about it.
 *
 * NO NETWORK beyond a same-origin fetch of `status.json` and a peer fetch of
 * `GET /api/live`.  Both are allowed to fail: `loadStatus()` / `loadLive()`
 * resolve to `null` rather than throwing, and `derive(null)` is the UNTESTED
 * pose with `live: null`.  A fresh clone with no harness and no coordinator
 * has neither file nor probe, and the cockpit must come up looking like a
 * cockpit anyway.  Live is NOT a field of `status.json` and never carries a
 * colour.  `POST /api/power` lives in the same helper; the derivation does
 * not call it.
 *
 * THE ONE RULE THE DRAWING OBEYS
 * ------------------------------
 * NO STATUS COLOUR TOUCHES THE PLATE.  Every coloured pixel sits inside the
 * opaque `#0F1216` bezel or the opaque brass hardware.  On LOG's and MTA's hull
 * the tube red `#D9342B` has a minimum luma delta of 0.00 against the plate
 * (section 4.4), which is why the bezel exists: the contrast requirement for
 * colour is against a constant, not against nine different backgrounds.
 */

import { getLive as apiGetLive, power as apiPower } from './api.js';

/* ===================================================================== 0 */
/* CONSTANTS                                                               */

export const SCHEMA = 'saintcon.status/1';

/* PKT's tally denominator.  Counted from the shipped PoCs, not from the
 * challenge README: that README's per-module counts are wrong for seven of the
 * eight modules (STATUS_AT_A_GLANCE section 12.2) and `max(NN)` is not the
 * count either, because the numbering has gaps (section 12.3).  54 is
 * DNSM 6 + FMM 8 + IPM 7 + KVS 6 + LOG 4 + MQB 7 + MTA 8 + OTA 8.
 * A status.json may override it with `fleet.vuln_total`. */
export const FLEET_VULN_TOTAL = 54;

/* Every colour in the indicator.  Exported so a close-up renderer can build
 * materials from the same numbers instead of retyping them. */
export const INK = {
  flange:   '#5A4622',
  collar:   '#5A4622',
  collarPkt:'#7A2E22',   /* PKT is the offensive panel; its glow is red-tinted */
  rod:      '#4A3A1C',
  brass:    '#CDB77E',
  bezel:    '#0F1216',
  glass:    '#1A2028',
  smoke:    '#262C34',   /* untested bore */
  grad:     '#6E7B88',
  landing:  '#D9342B',
  landingCore:'#FF9A72',
  hatch:    '#8A8578',
  green:    '#35C08A',
  greenCore:'#C7FFE6',
  hazard:   '#E8A317',
  hazardBg: '#14100A',
  sweep:    '#8A8578',
  sweepCore:'#E8E2CE',
  tally:    '#3A2E18',
  tallyOn:  '#C0392B',
  tallyOff: '#241A12',
};

/* THE MEASURED WIDE-SHOT PLACEMENTS — STATUS_AT_A_GLANCE section 4.2.
 *
 * `anchor` is the FOOT of the mast, on the module's own housing, in canonical
 * 1280x720 stage px.  `dir` is the direction +A points on screen.  `env` is the
 * 22 x 78 envelope, which is what the extra hotspot covers.
 *
 * These are NOT in `cockpit/combined/manifest.json` and must never be written
 * there: that file is read-only and its far rects are load-bearing for
 * `transition.json`'s measured magnifications (section 3.2).
 *
 * Re-verified against the shipped manifest: each envelope overlaps ONLY its own
 * module's far hotspot (110-220 px for eight of them, the collar sitting on the
 * housing, which is the point; 1232 px for PKT, whose mast now stands well
 * inside its own rect -- see below), zero px of any other module's hotspot,
 * zero px of any other envelope, and all nine are inside 1280x720.
 *
 * PKT MOVED, 2026-09-05.  It was `anchor [615, 293] / env [609, 215, 22, 78]`,
 * which measured against PKT's own far_glow alpha was not on the housing at
 * all: the panel's top rim is at y = 339 and the spike to y = 293 across
 * x = 608..624 is THE HARPOON BARREL.  The mast was bolted to the muzzle and
 * continued the barrel's line upward, its cap bead touching the overhead
 * console strip, sitting in the middle of PKT's own red hover bloom.  It now
 * stands on the flat top rim of PKT's starboard sub-panel, 72 px clear of the
 * muzzle, still rising into the 100 % alpha hole above the dash.  Background
 * under the envelope went from mean 0.102 / 15.6 % of px above luma 0.4 to
 * mean 0.022 / 0.12 %, and own-silhouette overlap from 0 px to 88 px.  The
 * fleet-worst per-pixel margin is unchanged at 0.3226 (dpr 1) / 0.3225 (dpr 2)
 * because it has never been PKT -- it is LOG and MTA on hull.  Full working,
 * the seven candidates measured, and the audit of the other eight are in
 * STATUS_AT_A_GLANCE section 15. */
export const WIDE_MASTS = {
  MQB:  { anchor: [150, 174],  dir: 'down',  env: [144, 174, 22, 78] },
  OTA:  { anchor: [284, 220],  dir: 'left',  env: [206, 204, 78, 22] },
  FMM:  { anchor: [205, 407],  dir: 'up',    env: [199, 329, 22, 78] },
  LOG:  { anchor: [376, 505],  dir: 'left',  env: [298, 489, 78, 22] },
  PKT:  { anchor: [700, 343],  dir: 'up',    env: [694, 265, 22, 78] },
  MTA:  { anchor: [854, 510],  dir: 'right', env: [854, 494, 78, 22] },
  IPM:  { anchor: [901, 230],  dir: 'left',  env: [823, 214, 78, 22] },
  DNSM: { anchor: [1046, 90],  dir: 'right', env: [1046, 74, 78, 22] },
  KVS:  { anchor: [1005, 353], dir: 'up',    env: [999, 275, 22, 78] },
};

/* WHICH MODULES ARE NOT SERVICES.
 *
 * The UI branches on a record's own `kind` and NEVER on `code === 'PKT'`
 * (section 9.2) — but when there is NO RECORD AT ALL, something has to say what
 * hardware to hang on the wall, and a fresh clone with no status.json is
 * exactly that case.  PKT is the offensive panel: it has no unit_tests, no
 * vuln_tests, and `bridge/data/catalog.json` correctly does not list it, so it
 * must show its tally stick rather than a glass tube it can never fill.
 *
 * This is the ONE place that fallback lives, and a record's own `kind` always
 * wins over it. */
export const DEFAULT_KIND = { PKT: 'offensive' };

/* Mast-local -> screen.  A runs along the mast away from the housing, B is the
 * cross axis, +B is the side the vane flies to.  Verified: `up` and `down` put
 * +B to screen right; `left` and `right` put +B to screen up, which is the
 * "vane" column of the placement table. */
export const DIR_TRANSFORM = {
  up:    'scale(1,-1)',
  down:  'rotate(180) scale(-1,-1)',
  left:  'rotate(-90) scale(1,-1)',
  right: 'rotate(90) scale(-1,-1)',
};

/* ===================================================================== 1 */
/* THE DERIVATION — section 9.5, plus two corrections found while building.   */

const RUNNING_STATES = { queued: 1, building: 1, running: 1 };
const UNIT_STATES  = { pass: 1, fail: 1, error: 1, untested: 1 };
const VULN_STATES  = { measured: 1, partial: 1, untested: 1 };
const ITEM_RESULTS = { landing: 1, fixed: 1, inconclusive: 1, untested: 1 };

/* Segment order for the tube: landing first, then inconclusive, then fixed, so
 * the red length reads directly as "how much work is left" (section 2.3).
 * Anything the harness could not classify sorts with inconclusive, because an
 * unknown is not a win. */
const SEG_ORDER = { landing: 0, inconclusive: 1, untested: 2, fixed: 3 };

function enumOr(v, table, fallback) {
  return (typeof v === 'string' && table[v] === 1) ? v : fallback;
}
function num(v) { return (typeof v === 'number' && isFinite(v)) ? v : 0; }

/* Live is a peer of the last-run record, not a field of it.  Absent or
 * malformed is unmeasured (`null`), which is not the same as `online: false`.
 * Display state keeps `{online, latency_ms, powered}`; `containerSeen` stays
 * on the raw map `__cockpit.live` reads.  `powered` is container running
 * state (on|off|unknown), distinct from TCP/UDP `online`. */
function livePeer(v) {
  if (!v || typeof v !== 'object' || typeof v.online !== 'boolean') return null;
  const ms = v.latency_ms;
  const p = v.powered;
  const powered = (p === 'on' || p === 'off' || p === 'unknown') ? p : 'unknown';
  const avail = (v.availability === 'not_yet_available')
    ? 'not_yet_available' : 'available';
  const released = v.released === false ? false : avail === 'available';
  return {
    online: v.online === true,
    latency_ms: (typeof ms === 'number' && isFinite(ms)) ? ms : null,
    powered,
    containerPhase: v.containerPhase === 'starting' ? 'starting' : '',
    released,
    availability: released ? 'available' : 'not_yet_available',
  };
}

/**
 * Facts in, display state out.  `rec` is one entry of `status.json`'s
 * `modules` object, or null/undefined for "no data at all".
 *
 * Never throws.  A malformed record degrades to the UNTESTED pose, which is
 * also the pose a module page must rest in when a checker opens it standalone
 * with no cockpit around it (section 6.2 rule 7).
 */
export function derive(rec, opts) {
  const o = opts || {};
  const r = (rec && typeof rec === 'object') ? rec : {};
  const code = typeof r.code === 'string' ? r.code : (o.code || '');

  /* Branch on `kind`, NEVER on `code === 'PKT'` (section 9.2).  A record that
   * carries a tally is offensive whether or not it says so. */
  const kind = (r.kind === 'offensive'
                || (r.kind === undefined && r.tally)
                || (r.kind === undefined && DEFAULT_KIND[code] === 'offensive'))
    ? 'offensive' : 'defensive';

  const run = (r.run && typeof r.run === 'object') ? r.run : {};
  const runState = typeof run.state === 'string' ? run.state : 'idle';
  const running = RUNNING_STATES[runState] === 1;

  /* STALE — section 7.  The generator emits both hashes so the cockpit, which
   * cannot hash a source tree from a browser, can still derive it.  This is the
   * SAME boolean the refit port's `dirty` jewel reads (section 11.3): they are
   * driven from one place so they can never disagree. */
  const was = typeof r.source_rev === 'string' ? r.source_rev : null;
  const now = typeof (o.currentRev || r.current_source_rev) === 'string'
    ? (o.currentRev || r.current_source_rev) : null;
  const stale = !!(was && now && was !== now);

  if (kind === 'offensive') {
    const hasTally = !!(r.tally && typeof r.tally === 'object');
    const t = hasTally ? r.tally : {};
    const of = num(t.of) > 0 ? num(t.of) : (num(o.fleetTotal) || FLEET_VULN_TOTAL);
    const confirmed = Math.max(0, Math.min(of, num(t.confirmed)));
    return {
      code, kind: 'offensive', run: runState, running, stale, dirty: stale,
      arm: (r.arm === 'armed' || r.arm === 'interlock') ? r.arm : 'safe',
      tally: { confirmed, of },
      /* UNTESTED IS NOT "NOTHING CONFIRMED YET", and the offensive variant had
       * no way to say which it was: a page with no `status.json` at all
       * derived `0 / 54, SAFE` and rendered PIXEL-IDENTICALLY to a live record
       * of `0 / 54, SAFE`.  Section 6.2 rule 6 requires the fitting to rest in
       * the UNTESTED pose when no status data is available, and the defensive
       * side has said so since it was written (`d.sec === 'untested'`).  A
       * record that carries no tally has an UNMEASURED tally; the mast shows
       * the hollow cap ring for it, exactly as the tube does.  PKT NOTES 13
       * item 1. */
      untested: !hasTally,
      /* the two axes do not exist for PKT and must read as absent, not as zero */
      fn: 'n/a', sec: 'n/a',
      total: 0, landing: 0, inconclusive: 0, fixed: 0, pendingUntested: 0,
      segments: [], items: [],
      win: false, hollowVictory: false, harnessError: runState === 'error',
      lastRun: run.finished_at || run.started_at || null,
      /* catalog has no offensive row; a live overlay here is ignored */
      live: null,
    };
  }

  const unit  = (r.unit  && typeof r.unit  === 'object') ? r.unit  : {};
  const vulns = (r.vulns && typeof r.vulns === 'object') ? r.vulns : {};

  const fn  = enumOr(unit.state,  UNIT_STATES, 'untested');
  let   sec = enumOr(vulns.state, VULN_STATES, 'untested');

  /* ITEMS ARE THE TRUTH.  The summary counts are a convenience and the UI
   * recomputes from `items` whenever they are present, so a producer that
   * forgets to update one of them cannot make the tube lie. */
  const rawItems = Array.isArray(vulns.items) ? vulns.items : [];
  const items = rawItems.map((it, i) => {
    const s = (it && typeof it === 'object') ? it : {};
    return {
      id: typeof s.id === 'string' ? s.id : String(i + 1),
      slug: typeof s.slug === 'string' ? s.slug : '',
      title: typeof s.title === 'string' ? s.title : '',
      result: enumOr(s.result, ITEM_RESULTS, 'untested'),
      reason: typeof s.reason === 'string' ? s.reason : '',
      verdictLine: typeof s.verdict_line === 'string' ? s.verdict_line : '',
      exitCode: (typeof s.exit_code === 'number') ? s.exit_code : null,
      scoredBy: typeof s.scored_by === 'string' ? s.scored_by : '',
    };
  });

  /* `total` is the count of `vuln_tests/NN_*.py`, NEVER `max(NN)` — section 9.4
   * rule 4.  FMM has no 03 or 06, IPM no 05, OTA no 08; deriving M from the
   * highest number draws graduations that can never fill. */
  let total = num(vulns.total);
  if (items.length) total = Math.max(total, items.length);

  let landing = 0, inconclusive = 0, fixed = 0, pendingUntested = 0;
  if (items.length) {
    for (const it of items) {
      if (it.result === 'landing') landing++;
      else if (it.result === 'inconclusive') inconclusive++;
      else if (it.result === 'fixed') fixed++;
      else pendingUntested++;
    }
  } else {
    landing = num(vulns.landing);
    inconclusive = num(vulns.inconclusive);
    fixed = num(vulns.fixed);
    pendingUntested = Math.max(0, total - landing - inconclusive - fixed);
  }
  if (sec === 'untested' && (landing || inconclusive || fixed)) sec = 'partial';
  /* section 9.2: `partial` iff any item is inconclusive or untested.  Repaired
   * here rather than trusted, because a producer that gets this wrong paints
   * unknowns as a clean win. */
  if (sec === 'measured' && (inconclusive || pendingUntested)) sec = 'partial';

  const segments = items.length
    ? items.slice().sort((a, b) =>
        (SEG_ORDER[a.result] - SEG_ORDER[b.result]) || (a.id < b.id ? -1 : 1))
    : [];

  /* THE TWO CELLS THAT MATTER — section 9.5, with one correction.
   *
   * The document's formula is `landing == 0 and inconclusive == 0`.  Built, that
   * is wrong for the `partial` case: a module with 4 fixed and 4 NEVER RUN has
   * landing 0 and inconclusive 0 and would paint as THE WIN.  An unrun PoC is an
   * unknown exactly as much as an exit-2 one is, so `pendingUntested` joins the
   * condition.  Recorded in STATUS_AT_A_GLANCE section 14. */
  const clean = landing === 0 && inconclusive === 0 && pendingUntested === 0
    && sec !== 'untested' && total > 0;

  return {
    code, kind: 'defensive', run: runState, running, stale, dirty: stale,
    fn, sec,
    total, landing, inconclusive, fixed, pendingUntested,
    items, segments,
    unitPassed: num(unit.passed), unitFailed: num(unit.failed),
    unitErrored: num(unit.errored),
    unitFailures: Array.isArray(unit.failures) ? unit.failures : [],
    win: clean && fn === 'pass',
    hollowVictory: clean && fn === 'fail',
    /* THE HARNESS's own failure, not the player's.  Draws as untested + a cross
     * through the cap ring, never as hazard stripes: accusing a player of
     * breaking a service because Docker was not running is worse than saying
     * nothing (section 7). */
    harnessError: fn === 'error' || runState === 'error',
    lastRun: run.finished_at || run.started_at || null,
    arm: null, tally: null,
    live: livePeer(o.live),
  };
}

/** Derive the whole file at once.  `doc` may be null.  `liveMap` is the peer
 * from `loadLive()` (cockpit codes), or null when unmeasured. */
export function deriveAll(doc, codes, liveMap) {
  const mods = (doc && doc.modules && typeof doc.modules === 'object') ? doc.modules : {};
  const fleetTotal = (doc && doc.fleet && num(doc.fleet.vuln_total)) || FLEET_VULN_TOTAL;
  const live = (liveMap && typeof liveMap === 'object') ? liveMap : null;
  const out = {};
  for (const c of (codes || Object.keys(mods))) {
    out[c] = derive(mods[c], { code: c, fleetTotal, live: live ? live[c] : null });
  }
  return out;
}

/* ===================================================================== 2 */
/* WORDS — the tooltip line, section 5.1.  Returned as a plain string; the
 * caller puts it on the page with textContent.                             */

function ago(iso) {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (!isFinite(t)) return null;
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 90) return Math.round(s) + 's ago';
  if (s < 5400) return Math.round(s / 60) + 'm ago';
  if (s < 172800) return Math.round(s / 3600) + 'h ago';
  return Math.round(s / 86400) + 'd ago';
}

/**
 * HOW MANY OF THE TALLY STICK'S `n` NOTCHES ARE LIT — one function, both halves.
 *
 * `Math.round(frac * n)` was the whole of this and it made ONE NOTCH WORTH
 * 4.5 EXPLOITS at PKT's 12 notches over a denominator of 54.  It was wrong at
 * BOTH ends and only the first was reported:
 *
 *   * `1 / 54` and `2 / 54` both lit ZERO, so the first two pieces of good
 *     news did not move a fitting whose entire point is filling with good
 *     news (PKT NOTES 13 item 2);
 *   * and `52 / 54` and `53 / 54` both lit TWELVE — a stick that reads
 *     unmistakably FULL with two exploits still unconfirmed, which is the
 *     same lie in the other direction and nobody had looked at it.
 *
 * `Math.ceil` fixes the first end and makes the second worse.  So both ends
 * are pinned and `ceil` covers the middle:
 *
 *   confirmed 0                 -> 0            (empty means empty)
 *   confirmed == of             -> n            (full means full)
 *   anything else               -> 1 .. n-1     (at least one, never all)
 *
 * It is here and not in either consumer because the close-up (`mast.js`) and
 * the wide shot (`drawOffensive`) drawing different counts from one record is
 * exactly the disagreement section 6.4 exists to make impossible.
 */
export function tallyLit(d, n) {
  const t = (d && d.tally) || {};
  const of = num(t.of), confirmed = num(t.confirmed);
  if (!(n > 0) || !(of > 0) || confirmed <= 0) return 0;
  if (confirmed >= of) return n;
  return Math.max(1, Math.min(n - 1, Math.ceil(confirmed / of * n)));
}

/* HOW MANY SOLVED NUMBERS THE ONE-LINE FORMS NAME.  The wide-shot tooltip sits
 * next to the pointer and the close-up caption sits on the bottom sill; neither
 * has room for a list that can run to dozens (f-mv6stu8x).  Three real numbers
 * and a "+N more" is the whole of what they say; the close-up's detail panel
 * (mast.js) is where the full list lives, in a bounded scroll box. */
export const SOLVED_SHOWN = 3;

/** The solved test numbers, as the numbers a player sees ("01" -> "1"), in
 * numeric order.  Solved-index only: never an unsolved index, a total, a
 * remaining count or an n/m ratio (Wave 2/6). */
export function solvedIds(d) {
  const ids = [];
  const items = (d && d.items) || [];
  for (const it of items) {
    if (!it || it.result !== 'fixed') continue;
    const n = String(it.id || '').replace(/^0+/, '') || it.id;
    if (n != null && n !== '') ids.push(String(n));
  }
  const isNum = x => /^\d+$/.test(x);
  return ids.map((x, i) => [x, i]).sort((a, b) =>
    (isNum(a[0]) && isNum(b[0])) ? (+a[0] - +b[0]) || (a[1] - b[1]) : a[1] - b[1])
    .map(x => x[0]);
}

/** One compact clause for the solved numbers: `solved #1 · #3 · #6 · +9 more`.
 * `max` caps how many numbers are named; the rest are only counted.  Returns
 * the clause as a one-element array (empty when nothing is solved) so it can be
 * pushed straight onto a clause list. */
export function solvedIndexBits(d, max) {
  const ids = solvedIds(d);
  if (!ids.length) return [];
  const cap = (typeof max === 'number' && max > 0) ? Math.floor(max) : SOLVED_SHOWN;
  const shown = ids.slice(0, cap).map(x => '#' + x);
  const more = ids.length - shown.length;
  return ['solved ' + shown.join(' · ') + (more > 0 ? ' · +' + more + ' more' : '')];
}

/* The plain words for a check that started but could not give an answer
 * (the service did not respond, the check crashed).  It is neither "closed" nor
 * "still lands" nor "never run", so it gets its own sentence.  T2's docket uses
 * the same phrase.  The technical term for this state stays in the data. */
export const COULDNT_FINISH = "Check couldn't finish — no result yet";

/* Lay a clause list out on lines of at most `cols` characters, breaking only
 * BETWEEN clauses (a clause is only broken inside, at a space, if it alone is
 * wider than the line).  Joined with " · ", so with `cols` of 0 the output
 * is the single line this function has always returned. */
function layoutClauses(bits, cols) {
  if (!(cols > 0)) return bits.join(' · ');
  const lines = [];
  let cur = '';
  const SEP = ' · ';
  const flush = () => { if (cur) lines.push(cur); cur = ''; };
  for (const bit of bits) {
    if (cur && (cur + SEP + bit).length <= cols) { cur += SEP + bit; continue; }
    flush();
    if (bit.length <= cols) { cur = bit; continue; }
    for (const word of bit.split(' ')) {
      if (!cur) cur = word;
      else if ((cur + ' ' + word).length <= cols) cur += ' ' + word;
      else { lines.push(cur); cur = word; }
    }
  }
  flush();
  return lines.join('\n');
}

/* Width of a tooltip line, in characters.  The wide-shot tooltip is set in 11 px
 * monospace with 0.16em tracking (index.html #tip), about 8.4 px a character,
 * so 32 characters is ~270 px.  That keeps the longest clause (the capped solved
 * list) on one line and bounds the tooltip's WIDTH; where it sits relative to
 * the window edge is app.js's job (see the T3 report: the tooltip must flip to
 * the left of the pointer near the right edge). */
export const TIP_COLS = 32;

/**
 * The status as words.  `opts.cols` is the line width: the default breaks the
 * clauses onto lines for the wide-shot tooltip (which is what app.js asks for);
 * `{ cols: 0 }` returns one line, which is what the close-up caption wants
 * because it wraps for its own, narrower, column (mast.js).  The caption also
 * states "Check couldn't finish" on a line of its own, so it passes
 * `omitCouldntFinish` and the sentence is not printed twice.
 */
export function statusLine(d, opts) {
  if (!d) return '';
  const cols = (opts && typeof opts.cols === 'number') ? opts.cols : TIP_COLS;
  const bits = [];
  if (d.kind === 'offensive') {
    /* Qualitative only — never confirmed/of totals. */
    if (d.tally && d.tally.confirmed > 0) bits.push('LANDINGS THIS SESSION');
    else bits.push('NO LANDINGS THIS SESSION');
    bits.push(d.arm.toUpperCase());
    if (d.running) bits.push('RUNNING');
    return layoutClauses(bits, cols);
  }
  if (d.running) bits.push('TESTING…');
  else if (d.harnessError) bits.push('HARNESS ERROR — NOT THE PATCH');
  else if (d.hollowVictory) bits.push("SEALED — BUT SHE WON'T FLY");
  else if (d.win) bits.push('CLEAN — SHE FLIES');
  else if (d.fn === 'fail') bits.push('SERVICE BROKEN');
  else if (d.fn === 'pass') bits.push('FLIES');
  else bits.push('UNTESTED');

  if (d.sec === 'untested') {
    bits.push('exploits never run');
  } else {
    const solved = solvedIndexBits(d);
    if (solved.length) bits.push(solved[0]);
    if (d.landing > 0) bits.push('exploits still land');
    /* inconclusive is its own sentence and is never folded into "incomplete":
     * it is the state "break it so the exploits stop" must not be able to
     * paint as clean (section 9.4 rule 1). */
    if (d.inconclusive > 0) { if (!(opts && opts.omitCouldntFinish)) bits.push(COULDNT_FINISH); }
    else if (d.landing === 0 && d.pendingUntested > 0) bits.push('security incomplete');
    else if (d.landing === 0 && d.fixed > 0) bits.push('security quiet');
  }
  if (d.fn === 'fail' && d.unitFailed) bits.push('unit tests failed');
  if (d.stale) bits.push('STALE — source edited since');
  const a = ago(d.lastRun);
  if (a) bits.push('run ' + a);
  /* LIVE is a clause on this one string, not a second colour language.
   * Release gate is first: NOT YET AVAILABLE (neutral — no spoilers).
   * Powered ON/OFF and TCP ON STATION / NO LINK are distinct from that.
   * Unmeasured live omits.  Never an INK key. */
  if (d.live) {
    if (d.live.released === false
        || d.live.availability === 'not_yet_available') {
      bits.push('NOT YET AVAILABLE');
      return layoutClauses(bits, cols);
    }
    if (d.live.powered === 'on') bits.push('ON');
    else if (d.live.powered === 'off') bits.push('OFF');
    if (d.live.powered === 'off') {
      bits.push('NO LINK');
    } else if (d.live.online === true) {
      const ms = d.live.latency_ms;
      bits.push((typeof ms === 'number' && isFinite(ms))
        ? ('ON STATION · ' + Math.round(ms) + ' ms') : 'ON STATION');
    } else if (d.live.online === false) {
      bits.push('NO LINK');
    }
  }
  return layoutClauses(bits, cols);
}

/* ===================================================================== 3 */
/* THE SVG COMPONENT.
 *
 * One `createMast()` per module.  `update(d)` rebuilds the variable parts by
 * replaceChildren + createElementNS; the skeleton (svg, defs, the transformed
 * group) is built once and never re-created, so the layer costs nine elements
 * of churn on a 5 s poll and nothing at all when the data has not changed.
 *
 * ANATOMY, mast-local, all canonical stage px (section 2.2):
 *   A  0- 2  FOOT FLANGE  14(B) x 2
 *   A  2-12  COLLAR       10(B) x10        <- the seam with the refit port
 *   A 12-78  ROD           4(B)
 *   A 16-64  TUBE BEZEL   12(B) x48        <- hazard-striped when unit tests fail
 *   A 18-62  BORE          8(B) x44        <- the security axis lives here
 *   A 64-72  CAP BEAD     d8
 *   A 72-78  HEAD KNOB    d5
 *   A 70-79  VANE                          <- the function axis
 */

const NS = 'http://www.w3.org/2000/svg';
const BORE_A0 = 18, BORE_LEN = 44, BORE_B = 4;

function el(doc, tag, attrs) {
  const n = doc.createElementNS(NS, tag);
  if (attrs) for (const k in attrs) if (attrs[k] !== null && attrs[k] !== undefined)
    n.setAttribute(k, String(attrs[k]));
  return n;
}
const f2 = v => (Math.round(v * 100) / 100);

/* THE HAZARD SLEEVE.  12 x 48 px of high-frequency amber-on-black chevrons, and
 * deliberately the loudest thing in the frame: "you broke the service" is the
 * highest-priority state and has to out-shout a full red tube (section 2.4). */
function hazardBezel(doc, g) {
  g.appendChild(el(doc, 'rect', { x: -6, y: 16, width: 12, height: 48, fill: INK.hazardBg }));
  for (let k = 0; k < 12; k++) {
    const y = 16 + k * 4;
    g.appendChild(el(doc, 'path', {
      d: `M-6,${y} L-2,${y + 2.2} L0,${y + 2.2} L-4,${y} Z`, fill: INK.hazard }));
    g.appendChild(el(doc, 'path', {
      d: `M4,${y} L8,${y + 2.2} L6,${y + 2.2} L2,${y} Z`, fill: INK.hazard }));
  }
  g.appendChild(el(doc, 'rect', { x: -6, y: 16, width: 12, height: 48,
    fill: 'none', stroke: INK.hazardBg, 'stroke-width': 0.7 }));
}

function drawDefensive(doc, g, d, ids) {
  const broken = d.fn === 'fail';
  const untestedSec = d.sec === 'untested' || d.total <= 0;

  /* ---- foot, collar, rod.  The rod is a TWO-TONE bar, and that is what buys
   * the legibility: shadow #0F1216 (luma 0.070) with a 1 px #CDB77E highlight
   * (0.720), so for every pixel under the fitting at least one tone clears the
   * margin whatever the plate is doing there (section 4.1). */
  g.appendChild(el(doc, 'rect', { x: -7, y: 0, width: 14, height: 2, fill: INK.flange }));
  g.appendChild(el(doc, 'rect', { x: -5, y: 2, width: 10, height: 10,
    fill: INK.collar, stroke: INK.bezel, 'stroke-width': 0.5 }));
  g.appendChild(el(doc, 'rect', { x: -5, y: 2, width: 1.2, height: 10,
    fill: INK.brass, opacity: 0.55, class: 'hl' }));
  g.appendChild(el(doc, 'rect', { x: -2, y: 12, width: 4, height: 66, fill: INK.rod }));
  g.appendChild(el(doc, 'rect', { x: -2, y: 12, width: 1, height: 66,
    fill: INK.brass, class: 'hl' }));

  /* ---- the bezel carries the FUNCTION axis */
  if (broken) hazardBezel(doc, g);
  else g.appendChild(el(doc, 'rect', { x: -6, y: 16, width: 12, height: 48,
    fill: INK.bezel, stroke: INK.brass, 'stroke-width': 0.7 }));

  /* ---- the bore carries the SECURITY axis */
  g.appendChild(el(doc, 'rect', { x: -BORE_B, y: BORE_A0, width: BORE_B * 2,
    height: BORE_LEN, fill: untestedSec ? INK.smoke : INK.glass }));

  /* NO SCALE ON THE INSTRUMENT is the untested tell, and it is a SECOND mark on
   * top of the cap bead — on purpose.  Empty tube + green cap (the win) and
   * empty tube + grey ring cap (never tested) would otherwise differ only by the
   * colour of one 8 px disc, the weakest discrimination in the design (2.3). */
  const M = Math.max(1, d.total);
  const seg = BORE_LEN / M;
  if (!untestedSec) for (let k = 1; k < M; k++)
    g.appendChild(el(doc, 'rect', { x: -BORE_B, y: f2(BORE_A0 + k * seg),
      width: 3, height: 0.8, fill: INK.grad }));

  if (d.running) {
    /* The only animation in the whole indicator, and it exists because the real
     * thing takes minutes: unit_tests/run-in-docker.sh does a compose --build. */
    const s = el(doc, 'g', { 'clip-path': `url(#${ids.bore})`, class: 'sweep' });
    s.appendChild(el(doc, 'rect', { x: -BORE_B, y: 18, width: BORE_B * 2, height: 9,
      fill: INK.sweep, opacity: 0.5 }));
    s.appendChild(el(doc, 'rect', { x: -BORE_B, y: 21, width: BORE_B * 2, height: 3,
      fill: INK.sweepCore, opacity: 0.85 }));
    g.appendChild(s);
  } else if (!untestedSec) {
    const hL = d.landing * seg;
    const hI = d.inconclusive * seg;
    const hU = d.pendingUntested * seg;
    /* INCONCLUSIVE first, so the landing fill can sit on top of its edge:
     * hatched dark glass, visibly NOT empty.  This is the linchpin — a PoC
     * fired at a service that no longer answers exits 2 and records here, so
     * "break it so the exploits stop" can never paint clean (2.5, 9.4 rule 1). */
    if (hI > 0) {
      const c = el(doc, 'g', { 'clip-path': `url(#${ids.inc})` });
      for (let y = -6; y < hI + BORE_LEN; y += 2)
        c.appendChild(el(doc, 'line', { x1: -BORE_B, y1: f2(BORE_A0 + hL + y),
          x2: BORE_B, y2: f2(BORE_A0 + hL + y + 5.5),
          stroke: INK.hatch, 'stroke-width': 0.7 }));
      g.appendChild(c);
    }
    /* NEVER RUN, inside a module that has been partly measured: same smoked
     * glass as a wholly untested tube, so it reads as absence, not as a result. */
    if (hU > 0) g.appendChild(el(doc, 'rect', { x: -BORE_B,
      y: f2(BORE_A0 + hL + hI), width: BORE_B * 2, height: f2(hU), fill: INK.smoke }));
    if (hL > 0) {
      g.appendChild(el(doc, 'rect', { x: -BORE_B, y: BORE_A0, width: BORE_B * 2,
        height: f2(hL), fill: INK.landing }));
      g.appendChild(el(doc, 'rect', { x: -1, y: BORE_A0, width: 2, height: f2(hL),
        fill: INK.landingCore }));
    }
  }

  /* ---- THE CAP BEAD — section 2.5.  The third mark, so "fixed it by breaking
   * it" is stated and not inferred from two independent ones. */
  let cap;
  if (untestedSec || d.harnessError)
    cap = { fill: 'none', stroke: INK.grad, 'stroke-width': 1 };
  else if (d.win)
    cap = { fill: INK.green, stroke: INK.greenCore, 'stroke-width': 0.7 };
  else if (d.hollowVictory)
    cap = { fill: INK.hazard, stroke: INK.hazardBg, 'stroke-width': 1.6,
            'stroke-dasharray': '2.2 2.2' };
  else
    cap = { fill: INK.glass, stroke: INK.brass, 'stroke-width': 0.6 };
  g.appendChild(el(doc, 'circle', Object.assign({ cx: 0, cy: 68, r: 4 }, cap)));

  /* THE HARNESS's own failure gets a cross through the ring and NO hazard
   * stripes anywhere.  Docker not running is not something the player did. */
  if (d.harnessError) {
    g.appendChild(el(doc, 'line', { x1: -3, y1: 65, x2: 3, y2: 71,
      stroke: INK.hatch, 'stroke-width': 1 }));
    g.appendChild(el(doc, 'line', { x1: -3, y1: 71, x2: 3, y2: 65,
      stroke: INK.hatch, 'stroke-width': 1 }));
  }

  g.appendChild(el(doc, 'circle', { cx: 0, cy: 75, r: 2.5, fill: INK.rod,
    stroke: INK.bezel, 'stroke-width': 0.4 }));

  /* ---- THE VANE.  Flying = taut pennant.  Furled = a dark rag along the head.
   * Absent = bare knob, nothing hoisted.  While a run is in flight it holds its
   * previous value at half-mast, because the previous result is still the best
   * information available (section 7). */
  const half = d.running && d.fn !== 'untested';
  if (d.fn === 'pass')
    g.appendChild(el(doc, 'path', { d: 'M0,71 L15,74 L2,79 Z', fill: INK.brass,
      stroke: INK.bezel, 'stroke-width': 0.4,
      transform: half ? 'rotate(-45 0 71)' : null }));
  else if (d.fn === 'fail')
    g.appendChild(el(doc, 'rect', { x: 2.5, y: 60, width: 4, height: 16,
      fill: INK.hazardBg, stroke: INK.hatch, 'stroke-width': 0.4 }));
}

/* PKT — DIFFERENT HARDWARE ON THE SAME FITTINGS (section 8).  Eight masts and
 * one bare module would read as a missing indicator, not as an exception.
 * The tally stick FILLS UPWARD AS GOOD NEWS, which is the opposite of the eight
 * defensive tubes, and that inversion is exactly why it must not look like one:
 * different material, different silhouette, chevron notches, no glass, no vane.
 *
 * NOT DRAWN, deliberately: PKT's eight payload classes.  README section 12 open
 * decision 2 records those names as the planner's groupings, unratified.  A data
 * dependency on an unratified taxonomy is how you end up re-cutting art. */
function drawOffensive(doc, g, d) {
  g.appendChild(el(doc, 'rect', { x: -7, y: 0, width: 14, height: 2, fill: INK.flange }));
  g.appendChild(el(doc, 'rect', { x: -5, y: 2, width: 10, height: 10,
    fill: INK.collarPkt, stroke: INK.bezel, 'stroke-width': 0.5 }));
  g.appendChild(el(doc, 'rect', { x: -2, y: 12, width: 4, height: 66, fill: INK.rod }));
  g.appendChild(el(doc, 'rect', { x: -2, y: 12, width: 1, height: 66,
    fill: INK.brass, class: 'hl' }));
  g.appendChild(el(doc, 'rect', { x: -5, y: 16, width: 10, height: 48,
    fill: INK.tally, stroke: INK.brass, 'stroke-width': 0.6 }));

  const n = 12, seg = 48 / n;
  /* ONE function, shared with the close-up's `applyOffensive()`. */
  const filled = tallyLit(d, n);
  for (let k = 0; k < n; k++) {
    const y = 16 + k * seg;
    g.appendChild(el(doc, 'path', {
      d: `M-4,${f2(y + 0.4)} L0,${f2(y + 1.6)} L4,${f2(y + 0.4)} L4,${f2(y + seg - 0.6)} `
       + `L0,${f2(y + seg - 1.8)} L-4,${f2(y + seg - 0.6)} Z`,
      fill: k < filled ? INK.tallyOn : INK.tallyOff }));
  }

  /* THE ARM LAMP.  Seeing from across the cockpit that the harpoon is armed is
   * worth having on its own, which is why the cap bead is spent on it. */
  let cap;
  /* UNTESTED FIRST, and it is the same hollow ring `drawDefensive()` draws for
   * `untestedSec` — section 6.4: the two halves must not be able to disagree,
   * and the close-up's `applyOffensive()` shows `cap_ring` for exactly this
   * condition.  Without it, a cockpit with no `status.json` drew PKT's mast
   * identically to a live record of `0 / 54, SAFE`.  It cannot change the
   * shipped render: PKT's record carries a tally, so `untested` is false. */
  if (d.untested) cap = { fill: 'none', stroke: INK.grad, 'stroke-width': 1 };
  else if (d.arm === 'armed') cap = { fill: INK.tallyOn, stroke: INK.landingCore, 'stroke-width': 0.7 };
  else if (d.arm === 'interlock') cap = { fill: INK.hazard, stroke: INK.hazardBg,
    'stroke-width': 1.6, 'stroke-dasharray': '2.2 2.2' };
  else cap = { fill: INK.glass, stroke: INK.brass, 'stroke-width': 0.6 };
  g.appendChild(el(doc, 'circle', Object.assign({ cx: 0, cy: 68, r: 4 }, cap)));
  g.appendChild(el(doc, 'circle', { cx: 0, cy: 75, r: 2.5, fill: INK.rod,
    stroke: INK.bezel, 'stroke-width': 0.4 }));
  /* NO VANE.  PKT does not "still work" in the sense the eight do. */
}

/**
 * Build one mast.  Returns `{ root, group, update(d) }` where `root` is an
 * `<svg>` ready to append and `update` is idempotent.
 *
 * `opts`: { code, anchor:[x,y], dir, env:[x,y,w,h], doc, pad }
 * Coordinates inside the svg are CANONICAL STAGE px, matching the viewBox, so
 * the placement table numbers appear verbatim and nothing has to be re-solved.
 */
export function createMast(opts) {
  const doc = opts.doc || document;
  const code = opts.code;
  const pad = (opts.pad === undefined) ? 6 : opts.pad;
  const [ex, ey, ew, eh] = opts.env;
  const [ax, ay] = opts.anchor;

  const svg = el(doc, 'svg', {
    class: 'tell', 'data-code': code,
    viewBox: `${ex - pad} ${ey - pad} ${ew + pad * 2} ${eh + pad * 2}`,
    width: ew + pad * 2, height: eh + pad * 2,
  });
  svg.style.left = (ex - pad) + 'px';
  svg.style.top = (ey - pad) + 'px';

  const ids = { bore: 'tellBore-' + code, inc: 'tellInc-' + code,
                scrim: 'tellScrim-' + code };
  const defs = el(doc, 'defs');
  const boreClip = el(doc, 'clipPath', { id: ids.bore });
  boreClip.appendChild(el(doc, 'rect', { x: -BORE_B, y: BORE_A0,
    width: BORE_B * 2, height: BORE_LEN }));
  const incClip = el(doc, 'clipPath', { id: ids.inc });
  const incRect = el(doc, 'rect', { x: -BORE_B, y: BORE_A0, width: BORE_B * 2, height: 0 });
  incClip.appendChild(incRect);
  /* STALE — section 7.  1 px diagonals at 6 px pitch over the WHOLE fitting, so
   * the mast reads "provisional".  Without it the cockpit confidently shows a
   * result for code that no longer exists. */
  const pat = el(doc, 'pattern', { id: ids.scrim, width: 6, height: 6,
    patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' });
  pat.appendChild(el(doc, 'rect', { x: 0, y: 0, width: 1, height: 6, fill: INK.brass }));
  defs.appendChild(boreClip); defs.appendChild(incClip); defs.appendChild(pat);
  svg.appendChild(defs);

  const group = el(doc, 'g', {
    transform: `translate(${ax},${ay}) ${DIR_TRANSFORM[opts.dir]}` });
  svg.appendChild(group);
  /* The scrim is MAST-LOCAL and covers the BEZEL AND CAP ONLY — A 14..76,
   * B -6..+6 — not the whole 22 x 78 envelope.  Two reasons, both learned by
   * looking at it on the running cockpit rather than in the sketch:
   *   1. an envelope-wide scrim paints diagonals across the bare plate in the
   *      gaps around a 4 px rod, and reads as somebody having hatched the dash;
   *   2. the same rule that keeps status colour off the plate applies to this —
   *      every scrim pixel now sits on opaque hardware.
   * It still does its job, because the thing you READ is the tube, and the tube
   * is what goes behind bars. */
  const scrim = el(doc, 'rect', { x: -6, y: 14, width: 12, height: 62,
    fill: `url(#${ids.scrim})`, opacity: 0.35 });
  /* `display` is set as an ATTRIBUTE and not through .style, because it is
   * created as a presentation attribute: clearing the inline style would fall
   * back to the attribute and the scrim would never appear. */
  scrim.setAttribute('display', 'none');

  let last = null;
  function update(d) {
    const key = JSON.stringify(d && [d.kind, d.fn, d.sec, d.total, d.landing,
      d.inconclusive, d.fixed, d.pendingUntested, d.running, d.win,
      d.hollowVictory, d.harnessError, d.stale, d.arm,
      d.tally && d.tally.confirmed, d.tally && d.tally.of,
      d.live && d.live.online, d.live && d.live.latency_ms,
      d.live && d.live.powered]);
    if (key === last) return;
    last = key;
    group.replaceChildren();
    if (!d) d = derive(null, { code });
    if (d.kind === 'offensive') drawOffensive(doc, group, d);
    else {
      const seg = BORE_LEN / Math.max(1, d.total);
      incRect.setAttribute('y', f2(BORE_A0 + d.landing * seg));
      incRect.setAttribute('height', f2(d.inconclusive * seg));
      drawDefensive(doc, group, d, ids);
    }
    scrim.setAttribute('display', d.stale ? 'inline' : 'none');
    group.appendChild(scrim);          // last, so it lies over the whole fitting
  }
  update(null);
  return { root: svg, group, update, code };
}

/* ===================================================================== 4 */
/* LOADING.  Same-origin fetches, all allowed to fail.                       */

/* ------------------------------------------------------------ DEMO MODE
 * First open is EMPTY and honest (f-mv6sv398): the shipped `status.json` is a
 * blank "nothing has been tested yet" record.  The recorded sample run that
 * used to ship in its place (IPM running, KVS/LOG/MTA/FMM/OTA with results, MQB
 * error, ...) lives, byte for byte, in `demo/status.demo.json`, and is read
 * ONLY when the page URL itself says `?demo=1`.
 *
 *   - opt-in is the URL and nothing else: not localStorage, not sessionStorage,
 *     not a cookie, not a previous visit.  A plain reload of the same profile
 *     is blank again.
 *   - it is visibly labelled: a "DEMO DATA" badge on the page, so nobody can
 *     mistake the sample for their own results.
 *   - real data is untouched: a real `status.json` (written by
 *     pipeline/make_status.py from a real run) is read exactly as before and is
 *     never labelled.
 * The frames inside the cockpit (module pages, the standings board) carry no
 * `?demo=1` of their own, so they ask their parent/top window. */
const DEMO_STATUS_URL = new URL('./demo/status.demo.json', import.meta.url).href;

function hasDemoFlag(search) {
  try { return new URLSearchParams(search || '').get('demo') === '1'; }
  catch (e) { return false; }
}

/** True only when this page, or the cockpit page that hosts it, was opened with
 * `?demo=1`.  Reads the URL; never storage. */
export function demoRequested() {
  for (const get of [() => window.location, () => window.parent.location,
                     () => window.top.location]) {
    try { if (hasDemoFlag(get().search)) return true; } catch (e) { /* cross-origin */ }
  }
  return false;
}

/** The "DEMO DATA" label.  Only the top window draws it (frames inside the
 * cockpit are covered by the cockpit's own); idempotent; textContent only. */
export function showDemoBadge() {
  try {
    if (window.top !== window) return null;
    const have = document.getElementById('demoBadge');
    if (have) return have;
    const make = () => {
      if (document.getElementById('demoBadge') || !document.body) return;
      const b = document.createElement('div');
      b.id = 'demoBadge';
      b.setAttribute('role', 'status');
      b.textContent = 'DEMO DATA';
      const sub = document.createElement('span');
      sub.textContent = ' — sample results, not yours';
      sub.style.cssText = 'font-weight:400;letter-spacing:.06em';
      b.appendChild(sub);
      b.style.cssText = 'position:fixed;top:6px;left:50%;transform:translateX(-50%);'
        + 'z-index:60;pointer-events:none;padding:3px 12px;border-radius:3px;'
        + 'background:rgba(20,16,10,.92);border:1px solid #e8a317;color:#e8a317;'
        + 'font:700 11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;'
        + 'letter-spacing:.2em;white-space:nowrap';
      document.body.appendChild(b);
    };
    if (document.body) make();
    else document.addEventListener('DOMContentLoaded', make, { once: true });
    return document.getElementById('demoBadge');
  } catch (e) { return null; }
}

/**
 * Fetch `status.json`.  Resolves to the parsed document, or to `null` if the
 * file is absent, unparseable or the wrong schema — NEVER throws and NEVER
 * shows a spinner.  A fresh clone has no harness and no status.json, and the
 * cockpit must come up in the untested pose looking like a cockpit.
 *
 * With `?demo=1` on the page URL (see DEMO MODE above) the labelled demo file
 * is read instead of `url`.
 */
export async function loadStatus(url) {
  try {
    const demo = demoRequested();
    if (demo) showDemoBadge();
    const r = await fetch(demo ? DEMO_STATUS_URL : (url || './status.json'),
                          { cache: 'no-store' });
    if (!r.ok) return null;
    const j = await r.json();
    if (!j || typeof j !== 'object') return null;
    if (typeof j.schema === 'string' && j.schema.split('/')[0] !== 'saintcon.status')
      return null;
    return j;
  } catch (e) { return null; }
}

/**
 * Fetch `GET /api/live` through api.js.  Resolves to a map keyed by cockpit
 * code `{online, latency_ms, containerSeen, powered}`, or to `null` if the
 * coordinator is down or the body is unusable — NEVER throws.  api.js already
 * remaps MAIL → MTA so this file never aliases.
 */
export async function loadLive() {
  const raw = await apiGetLive();
  if (!raw.reachable || !Array.isArray(raw.systems)) return null;
  const out = Object.create(null);
  for (const s of raw.systems) {
    if (!s || typeof s !== 'object' || typeof s.code !== 'string') continue;
    if (typeof s.online !== 'boolean') continue;
    const ms = s.latency_ms;
    const p = s.powered;
    const avail = (s.availability === 'not_yet_available')
      ? 'not_yet_available' : 'available';
    const released = s.released === false ? false : avail === 'available';
    out[s.code] = {
      online: s.online === true,
      latency_ms: (typeof ms === 'number' && isFinite(ms)) ? ms : null,
      containerSeen: !!s.containerSeen,
      powered: (p === 'on' || p === 'off' || p === 'unknown') ? p : 'unknown',
      containerPhase: s.containerPhase === 'starting' ? 'starting' : '',
      released,
      availability: released ? 'available' : 'not_yet_available',
    };
  }
  return out;
}

const POWER_OPS = { start: 1, stop: 1, restart: 1 };

/**
 * `POST /api/power` through api.js.  Callers pass a cockpit code.  Offensive
 * fittings have no compose service and never hit the wire.
 */
export async function power(code, op) {
  if (typeof op !== 'string' || POWER_OPS[op] !== 1)
    throw new TypeError('power: op must be start|stop|restart');
  if (typeof code !== 'string' || !code)
    throw new TypeError('power: missing code');
  if (DEFAULT_KIND[code] === 'offensive') {
    return { ok: false, reachable: false, error: 'no compose service',
             code, op, result: {} };
  }
  const out = await apiPower(code, op);
  return {
    ok: !!out.ok,
    reachable: !!out.reachable,
    error: out.ok ? undefined : (out.error || 'power failed'),
    code, op, result: out.result || {}, ms: out.ms || 0,
  };
}

/**
 * The source a MODULE PAGE should use — section 6.2 rule 7.  A module page is a
 * standalone page that the checkers open with no cockpit around it, so:
 * the parent cockpit if there is one, else the file, else the untested pose.
 * Live is merged here only when there is no parent: two polls of `/api/live`
 * would be two clocks.  Parent `status()` already includes the live peer.
 */
export async function moduleStatus(code, url) {
  try {
    if (window.parent && window.parent !== window && window.parent.__cockpit
        && typeof window.parent.__cockpit.status === 'function') {
      const d = window.parent.__cockpit.status(code);
      if (d) return d;
    }
  } catch (e) { /* cross-origin or no parent; fall through */ }
  const [doc, liveMap] = await Promise.all([
    loadStatus(url || '../../status.json'),
    loadLive(),
  ]);
  const live = (liveMap && liveMap[code]) || null;
  return derive(doc && doc.modules && doc.modules[code], { code, live });
}
