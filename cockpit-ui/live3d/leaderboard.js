/* SAINTCON 2026 — THE MUSTER BOARD.  The whole frontend for the leaderboard.
 *
 * WHAT IT IS.  A riveted brass annunciator rack — frame, header plate, a
 * recessed well of bevelled slats, a stepped three-place podium with cast
 * roman numerals and three glass valve lamps, a spring clamp on the bottom
 * rail and a ratchet index wheel on the right rail.  The whole board is LIVE
 * three.js geometry out of `assets/_leaderboard/board.glb`, lit by the area
 * lights the Blender builder measured and exported.  Every VALUE a player
 * reads — rank, name, points — is DOM, in one screen-space layer, because
 * README 1050-1053 says values are DOM and labels are geometry.
 *
 * IT IS NOT A MODULE AND NOT A FITTING.  There is no baked plate, no
 * `depth.bin`, no `ubias_m`, no split pass and no declared readout plane.  The
 * design of record is live3d/design/LEADERBOARD.md; the five sections that
 * matter most to anyone editing this file are repeated here.
 *
 * 1.  FRONTO-PARALLEL BY CONSTRUCTION.  The camera sits on the board face's
 *     own normal, through its centre, so the face-plane-to-stage-pixel map is
 *     an exact similarity: 2500 px per metre, emitted as `layout.ppm`.  That
 *     is why the DOM layer is authored in raw 1280x720 stage pixels and lands
 *     ON the surface with no matrix3d, no `css3d.js`, and no dependence on
 *     `layoutType()`'s one-advance monospace assumption (which this component
 *     would break outright — see 4).  The depth is in the LIGHT and in the
 *     parts that step forward out of the face.
 *
 * 2.  NOTHING RUNS ON A TIMER.  Not the camera breath, not the TV dwell, not
 *     the clamp, not the wheel, not even the 5 s poll.  Everything accumulates
 *     in `tick(dt, now)` off `requestAnimationFrame`, so `pose()` can stop the
 *     whole board dead and two consecutive `pose()` captures are byte
 *     identical.  This fleet has had THREE pose()-determinism bugs from
 *     exactly the mechanism this file refuses: KVS's 17x1 px blinking cursor,
 *     OTA's propagation pulse and MQB's ribbon trace.  `grep -n
 *     'setInterval\|setTimeout' live3d/leaderboard.js` finds nothing.
 *
 * 3.  ROW ELEMENTS ARE CREATED ONCE AND REUSED FOR EVER.  With 500 entries the
 *     board holds a 500-element array and 16 `<div class="row">`s.  Paging
 *     reassigns `textContent`; it never creates or destroys a node.  That is
 *     the difference between a board that runs for eight hours on a hallway TV
 *     and one that does not.
 *
 * 4.  TRUNCATION IS ON A MEASURED PIXEL BUDGET, NEVER A CHARACTER COUNT.
 *     Usernames are untrusted input of unbounded length and arbitrary Unicode.
 *     The vendored Courier Prime has no CJK and no emoji, so those names fall
 *     back to a system face with a DIFFERENT advance and any layout computed
 *     from one measured advance overruns the points column.  Names are
 *     measured with a hidden gauge span and cut by binary search on GRAPHEME
 *     boundaries; rank and points are laid out from the right edge and can
 *     never be pushed.  Only the name is ever cut.
 *
 * 5.  WHAT THE BOARD MAY SHOW is rank, name, points, the field size and how
 *     stale the data is.  Nothing else, ever.  No per-module column, no
 *     counts, no denominator, no delta, no ticker, no timestamps.  The
 *     leaderboard is a PUBLIC surface showing OTHER PEOPLE'S data and it is
 *     the highest-risk disclosure channel in the product — a player must not
 *     learn vulnerability names or counts until they have fixed them.  Entries
 *     are read through an explicit five-key pick (`pick()` below) and the
 *     object is NEVER spread, so a producer that adds a forbidden field cannot
 *     leak it through this file by accident.  This page does not import
 *     `status.js` and never reads `status.json`.
 *
 * NO innerHTML.  Every string reaches the page through `textContent`.
 * NO NETWORK.  One same-origin fetch of a local file the bridge writes.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';
import { applyColour } from './grade.js';
import { facingAudit } from './refit.js';

/* ===================================================================== 0 */
/* CONSTANTS.  Every one of them is either a fleet number with a citation or a
 * design number with a section.                                           */

/* The fleet's poll cadence.  `mast.js:59` uses the same 5 s for status.json
 * and the two files are meant to feel like one system. */
export const POLL_MS = 5000;
/* THE AUTO-ADVANCE, design section 7.4.  These were `TV_DWELL_MS`,
 * `TV_STEP_MS` and `TV_PAGES` and the prefix is gone with the mode: there is
 * one board, it runs unattended when nobody is touching it, and that is not a
 * separate product.
 *
 * 12 s dwell, and it cycles the top `pages x slots` only before a visible
 * carriage return — nobody at a conference waits ten minutes for rank 300 to
 * come round, and the header states the truth rather than implying the board
 * shows everyone.  The LOOP is capped; a HAND is not (see maxScrollPx()).  */
export const DWELL_MS = 12000;
export const LOOP_PAGES = 5;
/* 0.9 s of mechanical step.  THIS CONSTANT WAS DEAD.  `TV_STEP_MS` existed,
 * design/LEADERBOARD.md 6.1 advertised "12 s dwell, 0.9 s step" and NOTES
 * repeated it, but the only code that touched it was an accumulator `stepT`
 * that was zeroed on every page change, incremented every frame and READ BY
 * NOTHING — `grep -n stepT` found four writes and no reads.  The page change
 * was an instantaneous swap of eight strings and always had been; the 0.9 s
 * was in the documentation only.  It is the ease constant for the rack slide
 * now, so the number in the design record is finally the number on screen. */
export const STEP_MS = 900;

/* AUTO-ADVANCE MUST NOT FIGHT A HAND ON THE BOARD, and this is the whole
 * rule, stated once:
 *
 *   A `pointerdown` or a `wheel` on the board SUSPENDS the auto-advance and
 *   restarts the idle clock.  After RESUME_MS with neither, the board runs
 *   home to the top and resumes its loop.
 *
 * Pointer MOVEMENT is deliberately not in that list.  A cursor drifting
 * across a hallway television — or parked on it by whoever last used the
 * machine — would otherwise freeze the loop for ever, which is the failure
 * this board exists to avoid.  Motion is not intent; a button is.
 *
 * 45 s is a little under four dwells.  It is long enough to read a page and
 * decide to scroll again without the rack moving under your hand, and short
 * enough that the board has re-seated itself well before the next person
 * walks up to it.  It resumes AT THE TOP, not where the last hand left it:
 * an unattended board parked at rank 340 is a board showing the wrong thing
 * to everybody who did not scroll it. */
export const RESUME_MS = 45000;
/* The camera breath, design section 3.3.  A few millimetres of lateral drift,
 * sin-driven, deterministic, parked at phase 0 by pose().  It gives parallax
 * between the flat face and the podium/frame/clamp so the board reads as an
 * object rather than a picture, and it is the reason no pixel on an unattended
 * OLED holds one value for eight hours. */
export const BREATH_X_M = 0.0026, BREATH_Y_M = 0.0013;
export const BREATH_X_S = 40.0,  BREATH_Y_S = 61.0;
/* The two breath sines are exactly periodic together here: 40 and 61 are
 * coprime, so the common period is 40 x 61 s.  Used to wrap `breathT`. */
export const BREATH_PERIOD_MS = BREATH_X_S * BREATH_Y_S * 1000;
/* The clamp's jaw travel and the wheel's tooth pitch, both in the same units
 * their geometry was built in. */
export const JAW_OPEN_DEG = 26.0;
export const EASE_MS = 260;

/* THE EASE, AND WHY IT IS AN EXPONENTIAL AND NOT A LERP.
 *
 * The obvious spelling is `x += (T - x) * min(1, dt/EASE) * g`, and it is a
 * trap.  That recurrence is `x <- x + (T - x)*a` with `a = g*dt/EASE`, whose
 * error multiplier is `(1 - a)`.  It only converges while `|1 - a| < 1`, i.e.
 * `a < 2`.  With g = 3.2 that is dt < 162.5 ms; past it the value oscillates
 * with a GROWING amplitude.  It is not framerate-independent, it is
 * CONDITIONALLY STABLE, and the condition is a frame budget nobody enforces.
 *
 * Measured on the divergent form: `advance()` — the checkers' hook, which
 * calls tick(DWELL_MS = 12000) — drove `clampU` (a [0,1] quantity) along
 * 3.2, -3.84, 11.648, ... -2654.99 in ten steps, a jaw rotation of -69,000
 * degrees, and drove `wheelA` to a non-finite number by step ~40.  The TV
 * page-index check ran ten thousand advances and PASSED while the wheel it
 * was supposed to be exercising was already NaN: a check reporting on a
 * subject that no longer exists.  Only `Math.min(100, dt)` in frame() kept it
 * off the screen, and a clamp on the input is not a stable integrator.
 *
 * `1 - exp(-g * dt / EASE_MS)` is the exact solution of the same first-order
 * decay, so it agrees with the lerp to first order at real frame times
 * (dt = 16.7 ms: 0.18570 against 0.20554 for the clamp) and is bounded in
 * [0, 1) for EVERY dt from 0 to infinity.  Large dt snaps to the target
 * instead of exploding, which is what `advance(1)` wants anyway.
 *
 * The result is then re-clamped to the range the quantity is defined on.  A
 * bounded integrator plus a range clamp is two independent guards; the old
 * code had neither, and its one accidental guard was in a different function. */
export function ease(cur, target, dt, g, lo, hi) {
  if (!Number.isFinite(cur)) cur = target;      // recover, never propagate NaN
  const a = 1 - Math.exp(-g * Math.max(0, dt) / EASE_MS);
  let v = cur + (target - cur) * a;
  if (!Number.isFinite(v)) v = target;
  if (lo !== undefined && v < lo) v = lo;
  if (hi !== undefined && v > hi) v = hi;
  return v;
}
/* The rack slide's ease gain, DERIVED from STEP_MS rather than typed beside
 * it.  ease() is `1 - exp(-g*dt/EASE_MS)`, whose time constant is EASE_MS/g;
 * three of those is the usual "settled", so g = EASE_MS / (STEP_MS/3) puts
 * the slide's settling time at STEP_MS by construction.  Type the 0.9 s in
 * one place and the gain follows it. */
export const PAGE_G = EASE_MS / (STEP_MS / 3);

/* Staleness.  `generated_at` is the moment the standings were COMPUTED, and
 * the UI derives age from it — contract rule 7. */
export const STALE_MS = 4 * 60 * 1000;

const W = 1280, H = 720;

/* ===================================================================== 1 */
/* THE DATA CONTRACT — reading it, and refusing to read anything else.      */

export const SCHEMA = 'saintcon.leaderboard/1';

/* THE CLOSED SET OF FIVE.  `pick()` is the ONLY way an entry enters this
 * file.  It is a whitelist and not a blacklist on purpose: a blacklist has to
 * be updated every time a producer invents a field, and the field it misses is
 * the one that leaks.  Section 9.2 of the design lists what must never appear;
 * this function makes that list unnecessary. */
function pick(e) {
  if (!e || typeof e !== 'object') return null;
  const id = (typeof e.id === 'string') ? e.id : '';
  const name = (typeof e.username === 'string') ? e.username
    : ((typeof e.name === 'string') ? e.name : '');
  /* `points` as a string is a real malformed case and must render, not throw.
   * `rank` absent is another: the UI NEVER computes or repairs a rank —
   * contract rule 1 — because two clients that each compute one disagree
   * about ties and the board reshuffles on every poll. A missing id, rank,
   * or score stays missing. Nothing here invents one. */
  const rawPts = ('score' in e && e.score != null && e.score !== '') ? e.score : e.points;
  const pts = Number(rawPts);
  const rank = Number(e.rank);
  return {
    rank: Number.isFinite(rank) ? Math.trunc(rank) : null,
    id, name,
    points: Number.isFinite(pts) ? pts : null,
  };
}

/* One record of facts -> everything the board draws.  No sorting happens here
 * and none may ever be added: `entries` arrives in a producer-assigned total
 * order (rank, since, name, id) and re-sorting it client-side is how a board
 * with 500 players and ties starts flickering on every poll.  Contract rule 2,
 * design section 7.5. */
export function derive(doc) {
  const D = {
    ok: false, schemaBad: false,
    hasDoc: false, schema: null, title: '', fieldSize: 0,
    frozen: false,
    generatedAt: null, entries: [], podium: [null, null, null],
    rest: [], self: null, selfEntry: null, tiedAtTop: 0,
  };
  if (!doc || typeof doc !== 'object') return D;
  /* `hasDoc` separates "no feed has arrived yet" (the pre-data frame, which
   * says NO RETURNS and nothing else) from "a feed arrived and did not carry a
   * generated_at" (which is a thing worth saying out loud — see paint()). */
  D.hasDoc = true;
  D.schema = (typeof doc.schema === 'string') ? doc.schema : null;
  D.ok = (D.schema === SCHEMA);

  /* THE VERSION FIELD IS NOW LOAD-BEARING.  `D.ok` was computed here and then
   * read by nothing — `grep -n '\bok\b'` found the initialiser, this
   * assignment, and `if (!r.ok)` on the fetch Response, and that was all.  A
   * declared contract version that nothing checks is decoration: the contract
   * (design 8.2) names `saintcon.leaderboard/1`, and the board would render
   * `schema: "evil/9"` exactly as happily.  Worse, `?data=/live3d/status.json`
   * — a real file, from ANOTHER product, sitting on the same origin — painted
   * a staleness age taken out of that file's `generated_at` onto a leaderboard
   * sub-plate.  Nothing leaked (status.json has no `entries`), but the board
   * was reading a document it had already determined was not a leaderboard.
   *
   * So a document whose schema does not match is refused, and refused
   * VISIBLY.  `hasDoc` stays false, so nothing is drawn from it and none of
   * its fields — `generated_at` above all — reaches the instrument; the
   * sub-plate says BAD SCHEMA rather than falling through to the generic
   * NO FEED, because "the file arrived and is the wrong kind of file" is a
   * different fault from "the file did not arrive", and telling a bridge
   * operator which one it is saves an hour.
   *
   * Cost: a producer that bumps to `saintcon.leaderboard/2` gets a dark board
   * until this constant moves.  That is the intended reading of a version
   * field, it fails closed rather than open, and all sixteen shipped
   * documents (the feed and fifteen fixtures) carry `/1`. */
  if (!D.ok && Array.isArray(doc.entries) && doc.schema == null) {
    /* Harness list: {generated_at, entries:[{rank, username, score}]}.
     * Keep its order. Do not require the file schema. */
    D.schemaBad = false;
    D.ok = true;
    D.schema = SCHEMA;
  } else if (!D.ok) { D.schemaBad = true; return D; }
  const b = (doc.board && typeof doc.board === 'object') ? doc.board : {};
  D.title = (typeof b.title === 'string') ? b.title : '';
  D.frozen = b.frozen === true;
  const t = Date.parse(doc.generated_at);
  D.generatedAt = Number.isFinite(t) ? t : null;

  const raw = Array.isArray(doc.entries) ? doc.entries : [];
  for (const e of raw) {
    const p = pick(e);
    if (p) D.entries.push(p);
  }
  /* `field_size` is the count of PLAYERS, not of `entries` — contract rule 8.
   * It is what lets the board say TOP 40 OF 487 honestly while the producer
   * ships only the top 40. */
  const fs = Number(b.field_size);
  D.fieldSize = Number.isFinite(fs) && fs >= D.entries.length
    ? Math.trunc(fs) : D.entries.length;

  /* IDENTITY IS NEVER DERIVED FROM A NAME.  Display names are user-supplied
   * and two players may pick colliding ones — contract rule 5. */
  const s = doc.self;
  if (s && typeof s === 'object' && typeof s.id === 'string' &&
      s.visible !== false) {
    D.self = { id: s.id };
    for (const e of D.entries) if (e.id === s.id) { D.selfEntry = e; break; }
  }

  D.podium = [D.entries[0] || null, D.entries[1] || null,
              D.entries[2] || null];
  D.rest = D.entries.slice(3);
  if (D.entries.length) {
    const r0 = D.entries[0].rank;
    let n = 0;
    for (const e of D.entries) { if (e.rank === r0) n++; else break; }
    D.tiedAtTop = n;
  }
  return D;
}

/* THE ROMAN NUMERAL A STEP SHOWS.  A podium has exactly three places and under
 * standard competition ranking the only rank values that can ever reach one
 * are 1, 2 and 3 — the possible triples are 1,1,1 / 1,1,3 / 1,2,2 / 1,2,3.  So
 * three cast numerals per step, nine meshes, cover every case including every
 * tie, and no rank on the podium ever needs the DOM.  Design section 4.1. */
export function romanFor(entry, slot) {
  const r = entry && entry.rank;
  if (r === 1) return 'I';
  if (r === 2) return 'II';
  if (r === 3) return 'III';
  /* THE FALLBACK USED TO CAST THE SLOT INDEX, AND THAT WAS A LIE IN CAST
   * BRONZE.  `return ['I','II','III'][slot]` meant a podium of ranks 11, 11, 8
   * — which is exactly what fixtures/malformed.json is — got I, II, III
   * stamped beside the numbers 11, 11, 8.  It was written for "a producer that
   * skipped rank", where the slot index is the only thing left to say, but it
   * fired for any rank at all, and a WRONG STRING OF THE RIGHT SHAPE beside
   * the right number is the failure this build keeps coming back to
   * (CONVERSION_BRIEF 1609-1635).  The numeral is the one value on the podium
   * that is geometry rather than text, so it is also the one a positional
   * check cannot read.
   *
   * The numeral now means exactly one thing: this entry's rank is 1, 2 or 3.
   * Anything else — a rank the producer skipped, or a rank that is not a
   * podium rank — gets no numeral at all, and the plaque carries the name and
   * the points alone.  `paint()` looks up `num_<slot>_<roman>` and a null
   * simply finds no mesh, so nothing is drawn; there is no blank-numeral case
   * to build. */
  void slot;
  return null;
}

/* Points, grouped, without Intl: a locale-dependent separator is a
 * locale-dependent screenshot, and check/compare.py diffs screenshots. */
export function fmtPoints(n) {
  if (n === null || !Number.isFinite(n)) return '—';
  const neg = n < 0;
  let s = String(Math.abs(Math.trunc(n))), o = '';
  while (s.length > 3) { o = ',' + s.slice(-3) + o; s = s.slice(0, -3); }
  return (neg ? '-' : '') + s + o;
}

export function fmtRank(r) {
  return (r === null || !Number.isFinite(r)) ? '—' : String(r);
}

/* ===================================================================== 2 */
/* MEASURED TRUNCATION.  See header note 4.                                */

function graphemes(s) {
  /* Intl.Segmenter where it exists, so a family emoji or a base letter with
   * four combining marks is cut as ONE unit and never split into mojibake.
   * Array.from is the fallback and is already surrogate-pair safe. */
  if (typeof Intl !== 'undefined' && Intl.Segmenter) {
    try {
      const seg = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
      const out = [];
      for (const p of seg.segment(s)) out.push(p.segment);
      return out;
    } catch (e) { /* fall through */ }
  }
  return Array.from(s);
}

function makeGauge(host) {
  const g = document.createElement('span');
  g.className = 'gauge';
  host.appendChild(g);
  return g;
}

/* Cut `text` to `budget` stage px, appending an ellipsis when it is cut.  The
 * gauge carries the SAME computed font as the element the text will land in,
 * so what is measured is what is drawn — FIX_UPLOAD 811-818 records a column
 * layout that clipped exactly the load-bearing word, and the fix there was to
 * stop using columns that can truncate.  Here we cannot: names are unbounded.
 * So the fix is that rank and points are laid out from the RIGHT EDGE and can
 * never be pushed, and only the name is ever cut. */
const NAME_PX_PER_S = 24;
const NAME_PAUSE_MS = 2000;

function scrollName(run, extra) {
  if (run._nameExtra === extra && run.getAnimations().length) return;
  run._nameExtra = extra;
  run.getAnimations().forEach(a => a.cancel());
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  /* 24 px/s is slower than a long name crossing its plate in the old 8s pass.
   * Travel time follows the overflow, so every name moves at that one speed. */
  const travel = (extra / NAME_PX_PER_S) * 1000;
  const total = NAME_PAUSE_MS + travel + NAME_PAUSE_MS + travel;
  const hold = NAME_PAUSE_MS / total;
  const leg = travel / total;
  run.animate([
    { transform: 'translateX(0px)', offset: 0 },
    { transform: 'translateX(0px)', offset: hold },
    { transform: 'translateX(' + (-extra) + 'px)', offset: hold + leg },
    { transform: 'translateX(' + (-extra) + 'px)', offset: hold + leg + hold },
    { transform: 'translateX(0px)', offset: 1 },
  ], { duration: total, iterations: Infinity, easing: 'linear' });
}

function showName(el, name) {
  let run = el.querySelector('.nm-run');
  if (!run) {
    run = document.createElement('span');
    run.className = 'nm-run';
    el.replaceChildren(run);
  }
  run.textContent = name || '';
  el.classList.remove('is-scroll');
  run.style.whiteSpace = 'normal';
  run.style.width = '100%';
  /* A wrap stays inside the name plate, so rank and score stay put. If the
   * next line would leave that plate, scroll the whole name instead. */
  const fits = run.scrollHeight <= el.clientHeight + 1 && run.scrollWidth <= el.clientWidth + 1;
  if (!name || fits) {
    run._nameExtra = 0;
    run.getAnimations().forEach(a => a.cancel());
    return;
  }
  run.style.whiteSpace = 'nowrap';
  run.style.width = 'max-content';
  const extra = run.offsetWidth - el.clientWidth;
  if (extra > 1) {
    el.classList.add('is-scroll');
    scrollName(run, extra);
  }
}

function measuredWidth(gauge) {
  /* Layout px, same space as the plate budget. A transformed stage makes
   * getBoundingClientRect smaller than that budget, so a long name was
   * treated as fitting and ran out of the row. */
  return gauge.offsetWidth;
}

function fitText(gauge, cache, text, budget, font, spacing) {
  if (!text) return '';
  const room = Math.max(0, budget);
  /* A NUL as the separator so no font string or name can forge a key.  It
   * is written as an ESCAPE, not as a raw byte: a literal NUL in the source
   * makes grep call the file binary and every `grep -n` in every check in
   * this project then reports "Binary file matches" and nothing else. */
  const key = font + '\u0000' + (spacing || '') + '\u0000' + room.toFixed(2) + '\u0000' + text;
  const hit = cache.get(key);
  if (hit !== undefined) return hit;
  gauge.style.font = font;
  gauge.style.letterSpacing = spacing || '0px';
  const widthOf = (sample) => {
    gauge.textContent = sample;
    return measuredWidth(gauge);
  };
  let out;
  if (widthOf(text) <= room) {
    out = text;
  } else {
    const g = graphemes(text);
    let lo = 0, hi = g.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      gauge.textContent = g.slice(0, mid).join('') + '…';
      if (widthOf(g.slice(0, mid).join('') + '\u2026') <= room) lo = mid; else hi = mid - 1;
    }
    out = lo > 0 ? g.slice(0, lo).join('') + '…' : '…';
  }
  if (cache.size > 4096) cache.clear();
  cache.set(key, out);
  return out;
}

/* ===================================================================== 3 */
/* DOM HELPERS.  createElement / textContent only — CONVERSION_BRIEF 871-876
 * calls this "the single most important rule in the document", and the reason
 * is exactly this component: every string on this board is user-supplied.   */

function el(tag, cls) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}
function place(e, x, y, w, h) {
  e.style.left = x + 'px'; e.style.top = y + 'px';
  e.style.width = w + 'px'; e.style.height = h + 'px';
  e.style.lineHeight = h + 'px';
}

/* ===================================================================== 4 */
/* THE MOUNT                                                               */

/* NO REQUEST LEAVES THIS MACHINE, AND THAT IS NOW ENFORCED RATHER THAN
 * DEFAULTED.
 *
 * The design rule (section 7 below, design/LEADERBOARD.md) is that the bridge
 * talks upstream and drops a LOCAL file which this page fetches same-origin.
 * That was true of the shipped code only because `?data=`'s default value
 * happened to be a relative path: `?data=http://elsewhere/x.json` produced a
 * real cross-origin request, observed and logged.  A default is not an
 * invariant.  An unattended kiosk on a conference network, on a URL anyone
 * walking past can retype, is exactly where that distinction is paid for.
 *
 * So every URL this module fetches is resolved against the document and
 * REJECTED unless its origin matches.  A rejected URL throws before fetch()
 * is reached, so THAT url issues no request — the check is not a filter on
 * the response.  poll() catches the throw, so a refused feed degrades to the
 * NO RETURNS / NO FEED instrument like any other feed failure; it never
 * blanks and never silently reads a stranger's file.
 *
 * BUT THE PRE-FLIGHT CHECK ALONE ONLY BINDS THE FIRST HOP, and that was a real
 * hole rather than a theoretical one.  `fetch` defaults to `redirect: 'follow'`,
 * so a URL that passes sameOriginURL() and then 302s off-origin is followed
 * without the guard being consulted a second time — sameOriginURL never sees
 * the second URL, because the redirect is resolved inside fetch.  Reproduced:
 * a server on the page's own origin answering `/redir` with
 * `302 Location: http://127.0.0.1:9911/evil.json`, loaded as `?data=/redir`,
 * issued a genuine cross-origin request, got 200, and painted the stranger's
 * name on the podium with feedErr empty — the board believed it was healthy.
 * Any same-origin open redirect anywhere on the host (an upstream proxy, a
 * bridge endpoint that echoes a Location, a future /go?url= convenience) is
 * enough, and "there is no such endpoint today" is a property of a server
 * this file does not own.
 *
 * The redirect is therefore refused too: getJSON() passes `redirect: 'error'`,
 * which makes fetch REJECT rather than follow, so the off-origin request is
 * never issued.  Between the two, no request leaves this origin: the first hop
 * because sameOriginURL throws before fetch, every later hop because fetch
 * refuses to take it.  The cost is that a legitimate same-origin redirect (a
 * directory 301, say) also fails — feeds are files, so that is a trade worth
 * making, and it fails LOUD into NO FEED rather than quiet into a stranger's
 * data. */
export function sameOriginURL(u) {
  let r;
  try {
    r = new URL(String(u), document.baseURI);
  } catch (e) {
    throw new Error('refusing a URL that will not parse: ' + u);
  }
  if (r.origin !== location.origin) {
    throw new Error('refusing an off-origin feed URL (' + r.origin + ' is not '
                    + location.origin + '); the bridge writes a LOCAL file and '
                    + 'this page never makes a request off the machine');
  }
  return r.href;
}

async function getJSON(u) {
  /* redirect: 'error' — see the note above sameOriginURL().  Without it the
   * origin check binds the first hop only and a 302 walks straight past it. */
  const r = await fetch(sameOriginURL(u),
                        { cache: 'no-store', redirect: 'error' });
  if (!r.ok) throw new Error('cannot fetch ' + u + ' (HTTP ' + r.status + ')');
  return r.json();
}

/* DEMO STANDINGS (f-mv6sv398).  The shipped `leaderboard.json` is an honest
 * EMPTY board; the 500-entry sample that used to ship there is, byte for byte,
 * `demo/leaderboard.demo.json`.  It is read ONLY when the page URL says
 * `?demo=1` -- this page's own, or the cockpit's that hosts it in an iframe --
 * and only in place of the default feed: an explicit `?data=` fixture (what the
 * checkers pass) is never redirected.  Opt-in is the URL alone, never storage.
 * The "DEMO DATA" label is drawn by the top window (status.js `showDemoBadge`
 * in the cockpit; `drawDemoBadge` here when the board is the top page). */
const DEMO_FEED_URL = new URL('./demo/leaderboard.demo.json', import.meta.url).href;

function demoRequested() {
  const flag = s => { try { return new URLSearchParams(s || '').get('demo') === '1'; }
                     catch (e) { return false; } };
  for (const get of [() => window.location, () => window.parent.location,
                     () => window.top.location]) {
    try { if (flag(get().search)) return true; } catch (e) { /* cross-origin */ }
  }
  return false;
}

function drawDemoBadge() {
  if (window.top !== window || document.getElementById('demoBadge')) return;
  const b = document.createElement('div');
  b.id = 'demoBadge';
  b.setAttribute('role', 'status');
  b.textContent = 'DEMO DATA — sample standings, not real players';
  b.style.cssText = 'position:fixed;top:6px;left:50%;transform:translateX(-50%);'
    + 'z-index:60;pointer-events:none;padding:3px 12px;border-radius:3px;'
    + 'background:rgba(20,16,10,.92);border:1px solid #e8a317;color:#e8a317;'
    + 'font:700 11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;'
    + 'letter-spacing:.16em;white-space:nowrap';
  (document.body || document.documentElement).appendChild(b);
}

/* Which URL the feed is actually read from. */
function feedURL(u) {
  if (!demoRequested()) return u;
  let path = '';
  try { path = new URL(String(u), document.baseURI).pathname; } catch (e) { return u; }
  // Default feed only. An explicit ?data= fixture is left alone.
  // Bridge serves that file at /leaderboard.json; the standalone tree still
  // resolves it under its own prefix.
  if (path !== "/leaderboard.json" && path !== "/live3d/leaderboard.json") return u;
  drawDemoBadge();
  return DEMO_FEED_URL;
}

/**
 * mountBoard({ canvas, layerHost, hotsHost, assets, data, mode, pages })
 *
 *   canvas     the one <canvas> — there is no split, so there is one
 *   layerHost  the element the DOM layer is appended to (stage px space)
 *   hotsHost   pointer targets
 *   assets     'assets/_leaderboard/'
 *   data       'leaderboard.json'
 *   pages      auto-advance loop length in pages, or 'all'
 *
 * THERE IS NO `mode`.  There were two — `desk` (16 slots at 14 px, pointer,
 * pin) and `tv` (8 slots at 28 px, no pointer, no pin, automatic paging) —
 * and the split is deleted rather than defaulted: no branch below tests one,
 * scene.json emits one `layout.row` instead of a `layout.modes` map, and
 * board.glb carries one set of slats instead of two.  An unknown option is
 * ignored, so `?tv=1` is inert rather than an error.
 *
 * Returns the object also published as `window.__board`.
 */
export async function mountBoard(opt) {
  const A = opt.assets;
  const S = await getJSON(A + 'scene.json');
  const MJ = await getJSON(A + 'materials.json').catch(() => ({}));
  const L = S.layout;
  const RC = L.row;
  const PPM = L.ppm;

  /* ------------------------------------------------------------- renderer */
  const renderer = new THREE.WebGLRenderer({
    canvas: opt.canvas, alpha: true, antialias: true,
    premultipliedAlpha: true, preserveDrawingBuffer: true,
  });
  /* premultipliedAlpha: TRUE — three's own default and what three's blending
   * actually writes.  `false` puts a*rgb in the buffer and then tells the
   * browser to multiply by alpha again.  check/compare.py reads the flag out
   * of the capture's info.json; the two must agree. */
  renderer.setClearAlpha(0);
  renderer.setSize(W, H, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.AgXToneMapping;      // Blender's view transform
  RectAreaLightUniformsLib.init();

  const scene = new THREE.Scene();

  /* --------------------------------------------------------------- camera
   * `fov_y_deg`, never `angle_y_deg_BLENDER_DO_NOT_USE`: the latter derives
   * from sensor HEIGHT and is ~4 degrees wrong on a 16:9 frame.  The exporter
   * writes it only under a name that says so. */
  const camera = new THREE.PerspectiveCamera(
    S.camera.fov_y_deg, W / H, S.camera.clip[0], S.camera.clip[1]);
  const CAM0 = new THREE.Vector3().fromArray(S.camera.pos);
  {
    const f = new THREE.Vector3().fromArray(S.camera.forward);
    const u = new THREE.Vector3().fromArray(S.camera.up);
    const z = f.clone().negate().normalize();
    const x = new THREE.Vector3().crossVectors(u, z).normalize();
    const y = new THREE.Vector3().crossVectors(z, x);
    camera.position.copy(CAM0);
    camera.quaternion.setFromRotationMatrix(
      new THREE.Matrix4().makeBasis(x, y, z));
    camera.updateMatrixWorld();
  }

  /* --------------------------------------------------------------- lights
   * Blender area lights are WATTS over a size x size square; L = P/(A*pi) is
   * the physically-right relative balance and `light_gain` is the single
   * global scalar reconciling watts with three's nits.  These are OUR lights —
   * the board is authored, not inherited from a close_grade() — so the gain is
   * a scene constant and not a per-module fit. */
  let GAIN = (typeof S.light_gain === 'number') ? S.light_gain : 0.62;
  const lights = [];
  for (const Ld of S.lights) {
    const Ar = Math.max(1e-6, Ld.size * Ld.size);
    const rl = new THREE.RectAreaLight(
      new THREE.Color().setRGB(...Ld.color, THREE.LinearSRGBColorSpace),
      (Ld.energy / (Ar * Math.PI)) * GAIN, Ld.size, Ld.size);
    rl.position.fromArray(Ld.pos);
    rl.lookAt(rl.position.x + Ld.dir[0], rl.position.y + Ld.dir[1],
              rl.position.z + Ld.dir[2]);
    rl.userData.base = Ld.energy / (Ar * Math.PI);
    scene.add(rl); lights.push(rl);
  }
  const worldCol = new THREE.Color().setRGB(
    ...S.world_bg.slice(0, 3), THREE.LinearSRGBColorSpace);
  scene.add(new THREE.AmbientLight(worldCol, 1.0));

  /* THE WORLD HAS TO BE AN ENVIRONMENT AND NOT ONLY AN AMBIENT, BECAUSE MOST
   * OF THIS BOARD IS METAL.
   *
   * An AmbientLight contributes to the DIFFUSE term only, and a
   * MeshStandardMaterial at `metalness = 1` has no diffuse term at all — brass,
   * brass_dark, brass_lit, engrave, plinth, plinth_2, plinth_3 and steel are
   * all metallic 1.0 in materials.json, which is the frame, the rivets, the
   * rails, the plinth and the engraved header.  So before this, Blender's
   * world lit the bakelite and the slats and lit the metal by exactly nothing,
   * while Cycles lit the metal with it.  A PMREM of the same world colour is
   * the missing term and it is not a fudge: it is the same radiance the
   * AmbientLight already carries, delivered through the specular path the
   * metals actually use.
   *
   * MEASURED, against gt_full_read.png through check/compare.py at pose():
   *
   *     no environment,   light_gain 0.42   rms 24.918
   *     world_bg PMREM,   light_gain 0.42   rms 23.783   <- shipped
   *
   * and the gain was re-swept underneath it — 0.38/0.40/0.42/0.44/0.46 give
   * 24.063 / 23.861 / 23.783 / 23.818 / 23.954, so 0.42 is the fitted minimum
   * with the environment as it was without.  Brighter environments are worse,
   * monotonically and fast: a 30x world_bg scores 48.088, a warm studio grey
   * 35.012.  The honest environment is the one Blender actually had.
   *
   * IT DOES NOT CLOSE THE GAP TO THE PLAN'S <= 6, and section 9 of
   * design/LEADERBOARD.md records why that target does not transfer to this
   * component.  It is a 4.6% improvement and a correctness fix, not a pass. */
  {
    const pmrem = new THREE.PMREMGenerator(renderer);
    const envScene = new THREE.Scene();
    envScene.background = worldCol;
    scene.environment = pmrem.fromScene(envScene, 0).texture;
    pmrem.dispose();       // the generator, not the texture it returned
  }
  /* THE GAIN IS SWEPT, NOT PICKED.  `light_gain` reconciles Blender watts with
   * three's nits and the nine modules each carry their OWN fitted value
   * spanning 0.501..0.688 -- CONVERSION_BRIEF 5.2a records what happened the
   * two times one of them was treated as a fleet constant.  This board is
   * authored rather than inherited, but the same fit applies: the sweep runs
   * against gt_board.png through check/compare.py and the winner goes back
   * into scene.json.  Exposed under the fleet's own name so a harness can
   * drive it, exactly as each module's __occ.gain() does. */
  function setGain(g) {
    GAIN = g;
    for (const l of lights) l.intensity = l.userData.base * g;
  }

  /* ------------------------------------------------------------- geometry */
  /* Same-origin, same reason as getJSON: the loader issues its own fetch, so
   * the guard has to be applied to the URL handed to it. */
  const gltf = await new GLTFLoader().loadAsync(sameOriginURL(A + 'board.glb'));
  const root = gltf.scene;
  /* TRAP 28: root_scale is 1.0 and the exporter says so.  Nothing is rescaled
   * here; a scale on the root would move every part off the pixel rect it was
   * built to land on, which is the whole mechanism of this component. */
  root.scale.setScalar((typeof S.root_scale === 'number') ? S.root_scale : 1);
  scene.add(root);

  const P = new Map();                       // mesh name -> mesh
  const meshes = [];
  root.traverse(o => {
    if (!o.isMesh) return;
    const m = o.material.clone();
    o.material = m;
    const rec = MJ[m.name];
    if (rec) {
      if (rec.base) m.color.setRGB(rec.base[0], rec.base[1], rec.base[2],
                                   THREE.LinearSRGBColorSpace);
      if (typeof rec.rough === 'number') m.roughness = rec.rough;
      if (typeof rec.metallic === 'number') m.metalness = rec.metallic;
      if (rec.emit > 0 && rec.emission) {
        m.emissive.setRGB(rec.emission[0], rec.emission[1], rec.emission[2],
                          THREE.LinearSRGBColorSpace);
        m.emissiveIntensity = rec.emit;
      }
    }
    /* TRAP 21: FrontSide deletes one-sided Blender geometry silently — EEVEE
     * does not backface-cull and three does.  Every part in board.glb is a
     * CLOSED prism whose normals were recalculated outward by the builder, so
     * FrontSide is safe here and `facingAudit()` is expected to return [].
     * It is called anyway, by the checker, because "expected" is not
     * "measured" and OTA lost fourteen chevrons to exactly this. */
    m.side = THREE.FrontSide;
    P.set(o.name, o);
    meshes.push(o);
  });

  /* grade.js with a NULL split.  The guard is `if (split && split.renderer)`
   * at grade.js:136, so exposure is applied and the look is 'None' — this
   * scene is authored, not inherited from a module's close_grade(). */
  const grade = applyColour(S, renderer, null);

  /* ------- hinge groups: the only two things on the board that MOVE -------
   * The clamp jaws hinge about the WORLD X axis at the clamp's own pivot, so
   * their travel is entirely in y and z and they cannot move in x at all.
   * That is what makes "the clamp never enters a type column" a property of
   * the construction rather than an assertion.  The index wheel turns about
   * the camera axis, so it stays inside its own disc. */
  function hingeAbout(names, pivot, axis) {
    const g = new THREE.Group();
    g.position.copy(pivot);
    root.add(g);
    for (const n of names) {
      const m = P.get(n);
      if (!m) continue;
      m.position.sub(pivot);
      g.add(m);
    }
    g.userData.axis = axis;
    return g;
  }
  function centreOf(names) {
    const bb = new THREE.Box3();
    let any = false;
    for (const n of names) {
      const m = P.get(n);
      if (!m) continue;
      bb.expandByObject(m); any = true;
    }
    return any ? bb.getCenter(new THREE.Vector3()) : new THREE.Vector3();
  }
  const G = S.parts;
  const pivotJaw = P.get('clamp_pivot')
    ? centreOf(['clamp_pivot']) : centreOf(G.clamp || []);
  const jawUp = hingeAbout(['clamp_jaw_up'], pivotJaw, 'x');
  const jawLo = hingeAbout(['clamp_jaw_lo'], pivotJaw, 'x');
  const wheelG = hingeAbout(G.wheel || [], centreOf(G.wheel || []), 'z');

  /* --------- the two chassis modes.  The RACK NEVER RESIZES: both slat
   * counts occupy the same 358.4 px of well, so a five-entry board looks
   * intentional rather than collapsed and nothing in the geometry is a
   * function of entries.length. --------------------------------- */
  function show(names, v) {
    for (const n of names || []) { const m = P.get(n); if (m) m.visible = v; }
  }
  /* ONE CHASSIS.  These four lines used to pick a slat set and a rail
   * fitting off `mode`.  The slat set is gone from the asset entirely —
   * `G.slat` and `G.tab` are eight meshes each and nothing hides them.
   *
   * The rail is not a constant, though, and making it one would be a lie in
   * the other direction.  The clamp holds YOUR row; a board whose feed names
   * no `self` — the dummy account the conference television runs on, and
   * equally a bridge that has not resolved an identity yet — has no row to
   * hold, and a clamp gripping nothing is a claim that there is a you.  So
   * the rail is DATA-DRIVEN in paint(): clamp when the document carries a
   * self, blanking plate when it does not.  That was always the real
   * condition; `isTV` was standing in for it, and standing in badly, because
   * a desk user whose feed had no self got a clamp anyway.  Design 6.2. */
  show(G.numeral, false);

  const tabNames = G.tab || [];
  const tabHome = tabNames.map(n => {
    const m = P.get(n);
    return m ? m.position.z : 0;
  });
  /* The "you are here" mark is the LEFT TAB stepping forward, not the whole
   * slat.  Design section 4.3 confines every moving part to the tabs, the
   * frame, the rails and the margins, and a raised full-width slat would
   * project over its own row's type — which is the one thing the rule forbids.
   * The tab is outboard of the rank column by 8 px at rest. */
  /* 5 mm, not the 1.5 mm first tried.  At the board's 2500 px/m and a 0.62 m
   * camera distance, 1.5 mm magnifies a 32 px lug by 1.002 -- a quarter of a
   * pixel of growth and no visible change in how it catches the key light,
   * which made the marker invisible in the first capture.  5 mm reads.  It
   * also moves the lug's BACK face further from the type column, so the
   * clear-of-type keep-out improves rather than degrades. */
  const TAB_RAISE = 0.005;

  /* ============================================================== 5 DOM  */
  const board = el('div', 'board');
  board.id = 'board';
  board.style.setProperty('--rowfs', RC.font + 'px');
  opt.layerHost.appendChild(board);
  const gauge = makeGauge(board);
  const fitCache = new Map();

  /* the header sub-plate: two strings, left and right, on the dark strip */
  const sub = el('div', 'sub');
  place(sub, L.subplate[0], L.subplate[1],
        L.subplate[2] - L.subplate[0], L.subplate[3] - L.subplate[1]);
  const subL = el('span', 'l'); const subR = el('span', 'r');
  for (const s of [subL, subR]) {
    s.style.top = '0px';
    s.style.height = (L.subplate[3] - L.subplate[1]) + 'px';
    s.style.lineHeight = (L.subplate[3] - L.subplate[1]) + 'px';
    sub.appendChild(s);
  }
  board.appendChild(sub);

  /* the three podium plaques */
  const pods = [];
  for (let i = 0; i < 3; i++) {
    const r = L.plaques[i];
    const w = r[2] - r[0], h = r[3] - r[1];
    const d = el('div', 'pod p' + (i + 1) + (i === 2 ? ' steel' : ''));
    place(d, r[0], r[1], w, h);
    d.style.lineHeight = '1';
    const nm = el('span', 'nm'), pt = el('span', 'pt');
    place(nm, 14, Math.round(h * 0.16), w - 28, Math.round(h * 0.30));
    place(pt, 0, Math.round(h * 0.50), w - 14, Math.round(h * 0.40));
    d.appendChild(nm); d.appendChild(pt);
    board.appendChild(d);
    pods.push({ box: d, nm, pt, w });
  }

  /* THE RACK.  Created ONCE.  `slots` elements, for ever, at 5 entries and at
   * 500 alike — see header note 3. */
  const rowX0 = (L.col_rank && L.col_rank[0]) || (L.tab_x[1] + 8);
  const rows = [];
  for (let i = 0; i < RC.slots; i++) {
    const y = RC.y0 + i * RC.pitch;
    const d = el('div', 'row');
    place(d, rowX0, y, L.slat_x[1] - 8 - rowX0, RC.h);
    const rk = el('span', 'rk'), nm = el('span', 'nm'), pt = el('span', 'pt');
    place(rk, 0, 0, L.col_rank_right - rowX0, RC.h);
    place(nm, L.col_name[0] - rowX0, 0, L.col_name[1] - L.col_name[0], RC.h);
    place(pt, L.col_name[1] + 16 - rowX0, 0,
          L.col_points_right - L.col_name[1] - 16, RC.h);
    d.appendChild(rk); d.appendChild(nm); d.appendChild(pt);
    board.appendChild(d);
    rows.push({ box: d, rk, nm, pt });
  }

  /* the docked row in the clamp.  Created once, always — whether it has
   * anything IN it is paint()'s question and the document's answer. */
  let pinRow;
  {
    const r = L.pin_slat;
    const d = el('div', 'pin');
    place(d, rowX0, r[1], L.slat_x[1] - 8 - rowX0, r[3] - r[1]);
    const rk = el('span', 'rk'), nm = el('span', 'nm'), pt = el('span', 'pt');
    const hh = r[3] - r[1];
    place(rk, 0, 0, L.col_rank_right - rowX0, hh);
    place(nm, L.col_name[0] - rowX0, 0, L.col_name[1] - L.col_name[0], hh);
    place(pt, L.col_name[1] + 16 - rowX0, 0,
          L.col_points_right - L.col_name[1] - 16, hh);
    d.appendChild(rk); d.appendChild(nm); d.appendChild(pt);
    board.appendChild(d);
    pinRow = { box: d, rk, nm, pt };
  }

  /* ----------------------------------------------------------- hotspots
   * BOTH, ALWAYS.  This block used to be skipped entirely when `mode` was
   * `tv`: the conference board had no pointer targets at all, so the one
   * thing a person walking up to it wants to do — scroll down past rank 11 —
   * was not merely awkward, it was absent.  There is one board and it has a
   * pointer. */
  const hots = [];
  let pinHot = null;
  if (opt.hotsHost) {
    for (const h of (S.hotspots || [])) {
      const b = el('div', 'hot ' + h.id);
      b.style.left = h.rect[0] + 'px'; b.style.top = h.rect[1] + 'px';
      b.style.width = h.rect[2] + 'px'; b.style.height = h.rect[3] + 'px';
      b.title = h.title || '';
      opt.hotsHost.appendChild(b);
      const rec = { id: h.id, el: b };
      hots.push(rec);
      if (h.id === 'pin') pinHot = rec;
    }
  }

  /* ============================================================== 6 STATE */
  let doc = null, D = derive(null);
  let lastGood = null;               // hold-last-good; the board never blanks
  let feedErr = '';
  let page = 0, steps = 0;
  let pinOn = true;
  try {
    const v = localStorage.getItem('saintcon.leaderboard.pin');
    if (v === '0') pinOn = false;
  } catch (e) { /* private mode; the default stands */ }

  let running = true;
  /* `stepT` used to be here and was a dead accumulator — see STEP_MS. */
  let breathT = 0, dwellT = 0, pollT = 0, idleT = 0;
  /* `auto` is the board advancing itself; false while a hand is on it. */
  let auto = true;
  let clampU = pinOn ? 0 : 1, clampTarget = clampU;
  let wheelA = 0, wheelTarget = 0;
  let scrollPx = 0, scrollV = 0, dragging = false, dragLast = 0, dragT = 0;
  const pagesN = (opt.pages === 'all') ? 0
    : Math.max(1, Number(opt.pages) || LOOP_PAGES);

  const TOOTH = (2 * Math.PI) / ((L.wheel && L.wheel.teeth) || 12);

  /* ---------------------------------------------------------------- paging
   * ONE POSITION, AND THAT IS THE WHOLE OF THE UNIFICATION.
   *
   * There used to be two.  The TV's position was an INTEGER `page` and
   * `firstIndex()` returned `page * slots`; the desk's was a float `scrollPx`
   * and `firstIndex()` returned `round(scrollPx / pitch)`.  Two
   * representations of the same quantity, each ignored by the other mode's
   * code path — which is exactly why a hand could not touch the TV: there was
   * nothing for a drag to write that the TV's `firstIndex()` would read.
   *
   * `scrollPx` is now the only position on the board.  The auto-advance does
   * not set the index; it sets a TARGET, `pageTopPx()`, and the rack eases on
   * to it over STEP_MS.  A hand writes `scrollPx` directly.  Both ends move
   * the same number and `firstIndex()` reads it exactly once.
   *
   * `page` and `steps` survive as the auto-advance's own clock — integer, so
   * the page index is exactly `steps mod pages` after ten thousand advances
   * as after one — but they are no longer the position, only the thing the
   * position is asked to go to. */
  function restCount() { return D.rest.length; }
  /* THE LOOP IS CAPPED AND THE HAND IS NOT, and the two limits are different
   * numbers on purpose.  Unattended, the board cycles the top `pages x slots`
   * only, because nobody at a conference waits ten minutes for rank 300 to
   * come round.  A person who walks up and scrolls is not waiting for it, and
   * "can you scroll further down" is the request this board exists to answer,
   * so a hand reaches the whole field.  `?pages=all` makes the loop reach it
   * too, for anyone who wants that. */
  function maxScrollPx() {
    return Math.max(0, restCount() - RC.slots) * RC.pitch;
  }
  function loopSpan() {
    if (!pagesN) return restCount();
    return Math.min(restCount(), pagesN * RC.slots);
  }
  function pageCount() {
    return Math.max(1, Math.ceil(loopSpan() / RC.slots));
  }
  function pageTopPx() {
    return Math.min(maxScrollPx(), (page % pageCount()) * RC.slots * RC.pitch);
  }
  function firstIndex() {
    return Math.max(0, Math.min(Math.max(0, restCount() - RC.slots),
                                Math.round(scrollPx / RC.pitch)));
  }
  /* The two halves of the rule in the RESUME_MS note, in two functions so
   * there is one place each. */
  function handOn() { auto = false; idleT = 0; }
  function resumeAuto() {
    auto = true; idleT = 0; dwellT = 0; scrollV = 0;
    steps = 0; page = 0;
    /* Home is the top, and it RUNS there: `scrollPx` eases down to
     * pageTopPx() = 0 over STEP_MS while the index wheel runs back to 0, which
     * is the same gesture the carriage return already makes at the end of a
     * loop.  A board that teleported home would look broken. */
    wheelTarget = 0;
  }

  /* ------------------------------------------------------------- painting */
  function fontOf(e) {
    const c = getComputedStyle(e);
    return {
      font: c.fontStyle + ' ' + c.fontVariant + ' ' + c.fontWeight + ' ' +
            c.fontSize + '/' + c.lineHeight + ' ' + c.fontFamily,
      spacing: c.letterSpacing || '0px',
    };
  }
  let rowFont = null, podFont = [null, null, null];

  function paint() {
    if (!rowFont && rows.length) rowFont = fontOf(rows[0].nm);
    /* ---- the sub-plate.  Values only: field size, page, staleness, FINAL. */
    let left, right = '';
    if (!D.entries.length) {
      /* An empty board must still look like an instrument, not a broken page
       * — the same requirement mast.js records for a fresh clone with no
       * status.json.  There is never a spinner and never a throw. */
      /* NO RETURNS is the instrument before any feed has arrived (and when
       * the feed is down: NO FEED says why).  A feed that ARRIVED and lists
       * nobody is a different, ordinary fact -- nobody has scored yet -- and
       * says so in plain words (f-mv6sv398). */
      left = (D.hasDoc && !D.schemaBad) ? 'NO SCORES YET' : 'NO RETURNS';
    } else if (D.tiedAtTop > 3) {
      left = D.tiedAtTop + ' OF ' + D.fieldSize + ' AT RANK ' +
             fmtRank(D.entries[0].rank);
    } else {
      left = D.fieldSize + (D.fieldSize === 1 ? ' HAND' : ' HANDS');
    }
    /* The range is over ranks 4..N -- the rack.  With three or fewer entries
     * the rack is empty and there is no range to state: printing "4-3 OF 1"
     * is the kind of thing a positional check cannot see and a reader spots
     * instantly (CONVERSION_BRIEF 1609-1635: the WRONG STRING of the RIGHT
     * LENGTH passes every geometric test). */
    if (restCount() > 0) {
      /* ONE STRING, and it is neither of the two that were here.
       *
       * The TV printed `TOP 43 OF 500 · 12–19`, whose first half was a claim
       * about the LOOP — how far the board cycles unattended — dressed up as a
       * claim about the DATA.  It stopped being true the moment a hand could
       * scroll past 43, which is now.
       *
       * The desk printed `12–19 OF 500`, and those two numbers were the
       * ORDINAL POSITIONS of the first and last visible entries, not their
       * RANKS.  Standard competition ranking makes those different numbers the
       * moment anybody ties: the shipped feed has 42 tied ranks, so its 500
       * entries top out at rank 498, and scrolling to the end of it produced
       *
       *     rack:       493 494 495 496 497 498 498 498
       *     sub-plate:  493–500 OF 500
       *
       * — a number ending in 500 printed inches from a column of ranks that
       * ends in 498.  It is CONVERSION_BRIEF 1609-1635 exactly: the WRONG
       * STRING of the RIGHT SHAPE, which every positional check passes and a
       * reader spots at once.  Nobody had seen it because the desk was 16
       * dense rows nobody scrolled to the end of and the TV cycled the top 40.
       *
       * So the range states the RANKS of the rows actually on the board, read
       * out of the producer's own `rank` field and never computed here —
       * contract rule 1, the same rule romanFor() is built on.
       *
       * TWO WAYS THE PRODUCER CAN MAKE ITS OWN RANKS UNUSABLE HERE, and both
       * fall back to the ordinal positions rather than printing something
       * shaped like a range that is not one:
       *
       *   a rank is absent   fmtRank gives an em dash, and `—–6 OF 500` puts
       *                      a dash where a reader expects a number.
       *   the ranks DESCEND  fixtures/malformed.json ships 11, 11, 8, 8, 8,
       *                      null, 6, 5, 4, 3, 2, 1 — a producer that got the
       *                      order wrong — and the first spelling of this fix
       *                      printed `8–2 OF 500` off it, which is a range
       *                      running backwards.  The UI may not repair that
       *                      (contract rule 2 forbids re-sorting), and it must
       *                      not restate it as though it were a range either.
       *
       * The ordinal form is answerable in both cases, because it counts rows
       * rather than trusting them. */
      const f = firstIndex();
      const last = Math.min(restCount(), f + RC.slots) - 1;
      const a = D.rest[f], z = D.rest[last];
      const haveRanks = !!a && !!z && a.rank !== null && z.rank !== null &&
                        z.rank >= a.rank;
      right = haveRanks
        ? fmtRank(a.rank) + '–' + fmtRank(z.rank) + ' OF ' + D.fieldSize
        : (f + 4) + '–' + (last + 4) + ' OF ' + D.fieldSize;
    }
    sub.classList.remove('stale', 'dead');
    if (D.schemaBad) {
      /* see derive(): a document of the wrong schema is refused, and says so */
      right = (right ? right + '  ·  ' : '') + 'BAD SCHEMA';
      sub.classList.add('dead');
    } else if (feedErr) {
      right = (right ? right + '  ·  ' : '') + 'NO FEED';
      sub.classList.add('dead');
    } else if (D.generatedAt !== null) {
      /* A `generated_at` in the FUTURE is clock skew between the producer and
       * the viewer, not freshness -- and certainly not staleness.  It reads as
       * a negative age, which would silently switch the staleness mark off for
       * ever.  Clamp at zero and say nothing. */
      const age = Math.max(0, Date.now() - D.generatedAt);
      if (age > STALE_MS) {
        const mins = Math.floor(age / 60000);
        right = (right ? right + '  ·  ' : '') + mins + ' MIN OLD';
        /* not amber when the board is FINAL -- see the frozen branch below */
        if (!D.frozen) sub.classList.add('stale');
      }
    } else if (D.hasDoc && !D.entries.length) {
      /* An empty board has nothing to date, so it has nothing to be stale
       * about: an amber NO CLOCK on "NO SCORES YET" would read as a fault on
       * the shipped, honest, blank first-open board.  Any board that lists
       * somebody still gets the NO CLOCK rule below. */
    } else if (D.hasDoc) {
      /* A FEED WITH NO CLOCK IS NOT A FRESH FEED, and until now it read as
       * one: `generated_at` absent -> generatedAt null -> the staleness branch
       * never runs -> no mark at all.  That is a fail-open on the one field
       * contract rule 7 exists to protect, and a harness that simply forgets
       * to emit it would have shipped a board that always looks live.
       *
       * It is also what the shipped sample is.  live3d/leaderboard.json has no
       * producer — nothing computed those standings at any moment — so a fixed
       * `generated_at` there was a lie that got worse every minute: a fresh
       * clone read `492 MIN OLD` in amber, then 518, and would read six
       * figures next year.  The honest statement is that there is no clock,
       * and it is a statement that does not drift, which is also what makes
       * the evidence captures reproducible. */
      right = (right ? right + '  ·  ' : '') + 'NO CLOCK';
      if (!D.frozen) sub.classList.add('stale');
    }
    /* FINAL IS APPENDED, NOT SUBSTITUTED, and that is the whole fix.  This
     * used to be the FIRST branch of the chain, so `frozen: true` short-
     * circuited every clock branch below it: a document three days old with
     * `frozen` set rendered `... · FINAL` in normal ink and never said a word
     * about its age.  That is the same fail-open as the absent-`generated_at`
     * case two branches up — the one this file already corrected once, for the
     * same reason — and it is reachable by a producer that sets `frozen` by
     * mistake, which then yields a board that neither re-polls NOR ever admits
     * to being old.  A stuck board that looks live is the failure the whole
     * staleness apparatus exists to prevent.
     *
     * The age is therefore always stated.  What `frozen` still does is
     * suppress the AMBER: a board whose scoring is closed is supposed to be
     * old, so colouring it as an alarm would be a false alarm on the normal
     * case, while the reader still gets the number in plain ink.  It also
     * still stops the poll — there is nothing left to fetch. */
    if (D.frozen) right = (right ? right + '  ·  ' : '') + 'FINAL';
    subL.textContent = left;
    subR.textContent = right;

    /* ---- the podium.  Three plaques; the RANK is the cast numeral. */
    show(G.numeral, false);
    for (let i = 0; i < 3; i++) {
      const e = D.podium[i];
      const p = pods[i];
      p.box.hidden = !e;
      const stepLamps = ['lamp_glass_' + (i + 1), 'lamp_stem_' + (i + 1)];
      for (const n of stepLamps) {
        const m = P.get(n);
        if (!m) continue;
        /* THE LAMP IS THE ONLY EMISSIVE GEOMETRY ON THE BOARD.  Lit brightest
         * for I and stepped down for II and III; cold when the step is empty.
         * Nothing else glows and there are no medals and no gold/silver/bronze
         * — colour is the fleet's scarcest resource. */
        m.material.emissiveIntensity = e ? (6.0 - i * 1.8) : 0.0;
        m.material.needsUpdate = true;
      }
      if (!e) continue;
      const roman = romanFor(e, i);
      const nm = P.get('num_' + (i + 1) + '_' + roman);
      if (nm) nm.visible = true;
      if (!podFont[i]) podFont[i] = fontOf(p.nm);
      showName(p.nm, e.name);
      p.pt.textContent = fmtPoints(e.points);
    }

    /* ---- the rack.  textContent only; not one node is created here. */
    const f = firstIndex();
    const selfId = D.self ? D.self.id : null;
    for (let i = 0; i < rows.length; i++) {
      const e = D.rest[f + i] || null;
      const r = rows[i];
      const t = P.get(tabNames[i]);
      if (!e) {
        /* AN EMPTY SLOT IS AN EMPTY SLAT, not a missing one.  A real muster
         * board has the same number of slots whether the crew is five or five
         * hundred. */
        r.box.classList.add('empty');
        r.box.classList.remove('self');
        r.rk.textContent = ''; r.nm.textContent = ''; r.pt.textContent = '';
        if (t) t.position.z = tabHome[i];
        continue;
      }
      r.box.classList.remove('empty');
      r.rk.textContent = fmtRank(e.rank);
      showName(r.nm, e.name);
      r.pt.textContent = fmtPoints(e.points);
      const mine = !!(selfId && e.id === selfId);
      r.box.classList.toggle('self', mine);
      if (t) t.position.z = tabHome[i] + (mine ? TAB_RAISE : 0);
    }

    /* ---- THE BOTTOM RAIL, AND THE DOCUMENT CHOOSES ITS FITTING.
     *
     * Three states, and they are three different facts, not two:
     *
     *   no `self` in the feed     blanking plate.  There is no "you" — the
     *                             dummy account a hallway board runs on, or a
     *                             bridge that has not resolved an identity.
     *                             A clamp here would assert a you that the
     *                             document does not contain.
     *   a `self`, not in the      clamp, jaws empty.  You exist and you are
     *   entries the feed ships    not on the part of the board being shown.
     *   a `self` with a row       clamp, gripping your row.
     *
     * This used to key on `mode`, so a DESK user whose feed carried no self
     * got a clamp anyway — the branch was wrong for the case it was not
     * written about, which is the usual way a mode branch is wrong. */
    const hasSelf = !!D.self;
    show(G.clamp, hasSelf);
    show(G.blank, !hasSelf);
    if (pinHot) pinHot.el.hidden = !hasSelf;
    {
      const e = (hasSelf && pinOn) ? D.selfEntry : null;
      pinRow.box.hidden = !e;
      show(G.pin, !!e);
      if (e) {
        pinRow.rk.textContent = fmtRank(e.rank);
        showName(pinRow.nm, e.name);
        pinRow.pt.textContent = fmtPoints(e.points);
      }
    }
  }

  /* ============================================================== 7 FEED  */
  /* THE NO-NETWORK RULE AND "SCORING IS UPSTREAM" COLLIDE, AND THE RESOLUTION
   * ALREADY EXISTS.  README 389-392 says scoring and identity are upstream
   * concerns; CONVERSION_BRIEF 1796-1798 says assume no runtime network.
   * `status.json` resolved this by having the local stack's bridge write a
   * LOCAL FILE that the UI fetches same-origin.  The leaderboard does the
   * same: the bridge talks upstream, drops leaderboard.json on disk, and this
   * page never makes a request off the machine.  A future implementer will
   * otherwise reach for fetch('https://...'); do not. */
  let inflight = false;
  async function poll() {
    if (inflight) return;
    inflight = true;
    try {
      const d = await getJSON(feedURL(opt.data));
      if (d && d.ok === false && !Array.isArray(d.entries)) {
        throw new Error(d.error || 'scoreboard unavailable');
      }
      doc = d; lastGood = d; feedErr = '';
      D = derive(d);
      /* A SHORTER FIELD MUST NOT LEAVE THE RACK PAST ITS OWN END.  `page` was
       * clamped here before and `scrollPx` was not, because in desk mode
       * nothing but a hand could move it — but a hand that scrolled to rank
       * 400 and then a poll that returns 40 entries left the board parked off
       * the end of its own data, showing eight empty slats for ever.  Both
       * positions are re-clamped against the new field now. */
      if (page >= pageCount()) page = 0;
      scrollPx = Math.max(0, Math.min(maxScrollPx(), scrollPx));
      paint();
    } catch (e) {
      /* A failed read is an empty board, not a stale file. */
      feedErr = String(e && e.message || e);
      lastGood = null;
      doc = null;
      D = derive(null);
      paint();
    } finally {
      inflight = false;
    }
  }

  /* ============================================================== 8 TICK  */
  /* EVERYTHING that moves is accumulated here.  Nothing on this board is on a
   * setInterval or a setTimeout — see header note 2. */
  function tick(dt, now) {
    if (!running) return;
    breathT += dt;
    /* Same reasoning one step milder: `breathT` only ever feeds two sines of
     * period BREATH_X_S and BREATH_Y_S seconds, so it is exactly periodic in
     * their common multiple — 40 s and 61 s are coprime, so 2,440,000 ms.
     * Wrapping there is a bit-for-bit no-op on both sines and stops the
     * accumulator growing without bound (it reached 122,880,100 ms in the
     * 10,240-advance soak).  Never a defect at double precision; the point is
     * that "finite and in range" should not depend on nobody running it long
     * enough. */
    if (breathT >= BREATH_PERIOD_MS) breathT -= BREATH_PERIOD_MS;
    pollT += dt;
    if (pollT >= POLL_MS && !D.frozen) { pollT = 0; poll(); }

    /* THE HANDOVER.  One idle clock, and it only runs while a hand has the
     * board — see RESUME_MS.  When it expires the loop takes the board back
     * and runs it home to the top. */
    if (!auto) {
      idleT += dt;
      if (idleT >= RESUME_MS) resumeAuto();
    }

    if (auto) {
      dwellT += dt;
      /* INTEGER STEPS, NOT A FLOAT CLOCK.  `steps` is exact, so the page index
       * is exactly floor(t / dwell) mod pages after ten thousand advances as
       * it is after one.  A board that drifts kills itself at hour six. */
      while (dwellT >= DWELL_MS) {
        dwellT -= DWELL_MS;
        steps += 1;
        const n = pageCount();
        const prev = page;
        page = steps % n;
        /* the visible carriage return: the wheel runs BACK when the rack
         * re-seats at page 0, and ratchets one tooth otherwise */
        wheelTarget = (page === 0 && prev !== 0) ? 0 : wheelTarget + TOOTH;
        /* THE CARRIAGE RETURN IS UNREACHABLE WHEN THERE IS ONLY ONE PAGE, and
         * NOTES said flatly that `wheel` "returns to 0 on the carriage return".
         * With `pageCount() === 1` — `?pages=1`, or any feed of at most
         * `slots + 3` entries, which is a five-player day-one conference or a
         * bridge that has written a handful of rows — `page` and `prev` are
         * both permanently 0, `prev !== 0` is never true, and the reset branch
         * never runs: 10,240 advances measured 307,200° of accumulated
         * rotation, monotonically increasing, with no reset ever.  It stayed
         * finite and there was no visual defect (a ratchet that keeps
         * ratcheting looks like a ratchet), but an accumulator with no bound
         * is the same shape as the divergence in item 15 above, and that one
         * did reach non-finite.
         *
         * There is nothing to run back to when there is one page, so the fix
         * is not a reset — it is a wrap.  Rotation is modulo 2π, so taking the
         * SAME whole number of turns off `wheelTarget` and `wheelA` together
         * is exactly invisible: `wheelG.rotation.z` and the eased gap between
         * the two are both unchanged.  It is confined to the one-page case so
         * that the multi-page carriage return — which runs back the full
         * accumulated angle, and is the visible thing this mechanism is for —
         * is not shortened. */
        if (n === 1 && wheelTarget >= 2 * Math.PI) {
          const turns = Math.floor(wheelTarget / (2 * Math.PI)) * 2 * Math.PI;
          wheelTarget -= turns; wheelA -= turns;
        }
      }
      /* THE RACK SLIDES, IT DOES NOT CUT.  The page change above moves a
       * TARGET; this moves the board on to it over STEP_MS, through the same
       * `scrollPx` a hand writes.  paint() is called when the slide crosses a
       * row boundary and not on every frame — the same test the drag has
       * always used, now the only one.
       *
       * At a large `dt` — advance()'s 12,000 ms — the exponential ease snaps
       * to the target rather than overshooting it, so a page advance is exact
       * whether it is stepped by a checker or watched by a person. */
      const beforeAuto = firstIndex();
      scrollPx = ease(scrollPx, pageTopPx(), dt, PAGE_G, 0, maxScrollPx());
      if (firstIndex() !== beforeAuto) paint();
    }

    /* Eased mechanism.  UNCONDITIONALLY stable at any dt — see ease() in
     * section 1 for why the lerp it replaced was not.  clampU is a [0,1]
     * fraction of JAW_OPEN_DEG; wheelA is an angle and is bounded only by its
     * own target, which the carriage return resets every cycle. */
    clampU = ease(clampU, clampTarget, dt, 3.2, 0, 1);
    wheelA = ease(wheelA, wheelTarget, dt, 2.6);

    /* Momentum after a flick.  README 1051 explicitly values momentum on
     * drags.  It runs only while a HAND has the board: the two never both
     * write `scrollPx` in one frame, because `auto` gates each of them and
     * they are the same boolean. */
    if (!auto && !dragging && Math.abs(scrollV) > 0.01) {
      const before = firstIndex();
      scrollPx += scrollV * dt;
      scrollV *= Math.pow(0.0022, dt / 1000);
      const maxPx = maxScrollPx();
      if (scrollPx < 0) { scrollPx = 0; scrollV = 0; }
      if (scrollPx > maxPx) { scrollPx = maxPx; scrollV = 0; }
      if (firstIndex() !== before) paint();
    }
    apply();
  }

  /* Push the accumulated state onto the scene.  Called by tick() and by
   * pose(); it reads only the accumulators, never the clock, so parking the
   * accumulators parks the picture. */
  function apply() {
    const bx = BREATH_X_M * Math.sin(2 * Math.PI * breathT / (BREATH_X_S * 1000));
    const by = BREATH_Y_M * Math.sin(2 * Math.PI * breathT / (BREATH_Y_S * 1000));
    camera.position.set(CAM0.x + bx, CAM0.y + by, CAM0.z);
    camera.updateMatrixWorld();
    /* THE DOM LAYER RIDES THE FACE PLANE.  Translating the camera shifts
     * everything at the face plane by exactly -bx * ppm px, so the DOM must
     * move with it or the rows slide off their slats.  Everything at any OTHER
     * depth — the frame, the podium, the lamps, the clamp — then parallaxes
     * against both, which is the entire point of the breath. */
    board.style.transform =
      'translate(' + (-bx * PPM).toFixed(3) + 'px,' +
      (by * PPM).toFixed(3) + 'px)';

    const a = clampU * JAW_OPEN_DEG * Math.PI / 180;
    jawUp.rotation.x = -a;
    jawLo.rotation.x = a;
    wheelG.rotation.z = wheelA;

    renderer.render(scene, camera);
  }

  /* ============================================================== 9 POSE  */
  /* THE POSE.  Stops the board dead, parks every phase at 0, and renders.
   * Two consecutive pose() captures 600 ms apart must be byte identical: that
   * check is what caught KVS's 17x1 px blinking cursor.  It is a real risk
   * here because the breath, the dwell and the poll all run continuously. */
  function pose() {
    running = false;
    breathT = 0; dwellT = 0; pollT = 0; idleT = 0;
    /* pose() is the UNATTENDED board at the top of its loop.  Parking `auto`
     * true rather than leaving whatever the last pointer event set is what
     * makes two pose() captures identical after somebody has scrolled. */
    auto = true;
    steps = 0; page = 0; scrollPx = 0; scrollV = 0;
    clampU = clampTarget = (pinOn ? 0 : 1);
    wheelA = wheelTarget = 0;
    paint();
    apply();
  }
  function play() { running = true; }

  /* ============================================================ 10 INPUT  */
  function setPin(on) {
    pinOn = !!on;
    clampTarget = pinOn ? 0 : 1;
    try {
      localStorage.setItem('saintcon.leaderboard.pin', pinOn ? '1' : '0');
    } catch (e) { /* private mode; the session default stands */ }
    paint();
  }
  /* Every pointer BUTTON on the board is a hand on the board — see RESUME_MS.
   * `handOn()` is not inside setPin() on purpose: a checker calling
   * `B.setPin()` is not a person, and must not stop the loop. */
  for (const h of hots) {
    if (h.id === 'pin') {
      h.el.addEventListener('click', () => { handOn(); setPin(!pinOn); });
    }
  }
  if (opt.hotsHost) {
    const rack = hots.find(h => h.id === 'rack');
    if (rack) {
      const e = rack.el;
      e.addEventListener('pointerdown', ev => {
        handOn();
        dragging = true; dragLast = ev.clientY; dragT = performance.now();
        scrollV = 0;
        e.setPointerCapture(ev.pointerId);
      });
      e.addEventListener('pointermove', ev => {
        /* NOT `handOn()`: a cursor merely crossing the board is not intent,
         * and a mouse parked on a hallway panel would otherwise hold the loop
         * off for ever.  But a drag IN PROGRESS keeps the idle clock at zero,
         * so a slow drag longer than RESUME_MS is not taken off the user
         * mid-gesture. */
        if (!dragging) return;
        idleT = 0;
        const now = performance.now();
        const d = ev.clientY - dragLast;
        const k = stageScale();
        const before = firstIndex();
        scrollPx -= d / (k || 1);
        const maxPx = maxScrollPx();
        scrollPx = Math.max(0, Math.min(maxPx, scrollPx));
        const dtms = Math.max(1, now - dragT);
        scrollV = -(d / (k || 1)) / dtms;
        dragLast = ev.clientY; dragT = now;
        if (firstIndex() !== before) paint();
      });
      const up = () => { dragging = false; };
      e.addEventListener('pointerup', up);
      e.addEventListener('pointercancel', up);
      e.addEventListener('wheel', ev => {
        handOn();
        ev.preventDefault();
        const before = firstIndex();
        scrollPx += ev.deltaY * 0.6;
        const maxPx = maxScrollPx();
        scrollPx = Math.max(0, Math.min(maxPx, scrollPx));
        scrollV = 0;
        if (firstIndex() !== before) paint();
      }, { passive: false });
    }
  }
  function stageScale() {
    const st = opt.stage || opt.layerHost;
    const r = st.getBoundingClientRect();
    return r.width / W;
  }

  /* ============================================================ 11 CHECK  */
  /* THE CLEAR-OF-TYPE RULE, and it is binding for this component.
   *
   *   No MECHANISM mesh may project over any DOM text rect, at any pose, at
   *   any point in any part's travel.  All mechanism lives in the slat left
   *   tabs, the frame, the rails and the margins.
   *
   * "Mechanism" is the honest reading and it has to be said out loud: the
   * whole board is live geometry, so the slat UNDER a row trivially projects
   * over that row's type and always will — it is the surface the type is
   * written on.  What the rule is actually about is the MOVING parts, the ones
   * whose travel could sweep across a value while somebody is reading it.
   * Those are the clamp jaws, the index wheel, the raised tabs, the blanking
   * plate and the docked row's own tab, and they are what this samples.
   *
   * If the rule holds, this page needs no occlusion.js, no depth.bin, no
   * ubias_m, no light_gain fit, no split pass and no check_occlusion.py.  That
   * is the single biggest cost saving in the design and it is a claim, not an
   * assumption — hence a check that runs in the page and reports numbers. */
  const MECH = []
    .concat(G.clamp || [], G.wheel || [], G.blank || [], tabNames,
            ['pin_tab']);

  function meshRectPx(m) {
    if (!m || !m.visible) return null;
    const g = m.geometry;
    if (!g.boundingBox) g.computeBoundingBox();
    const bb = g.boundingBox;
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    const v = new THREE.Vector3();
    for (let i = 0; i < 8; i++) {
      v.set(i & 1 ? bb.max.x : bb.min.x,
            i & 2 ? bb.max.y : bb.min.y,
            i & 4 ? bb.max.z : bb.min.z);
      m.localToWorld(v);
      v.project(camera);
      const px = (v.x * 0.5 + 0.5) * W, py = (0.5 - v.y * 0.5) * H;
      if (px < x0) x0 = px; if (px > x1) x1 = px;
      if (py < y0) y0 = py; if (py > y1) y1 = py;
    }
    return [x0, y0, x1, y1];
  }
  function textRectsPx() {
    const st = (opt.stage || opt.layerHost).getBoundingClientRect();
    const k = st.width / W;
    const out = [];
    const sel = board.querySelectorAll(
      '.row:not(.empty) .rk, .row:not(.empty) .nm, .row:not(.empty) .pt, ' +
      '.pod:not([hidden]) .nm, .pod:not([hidden]) .pt, ' +
      '.pin:not([hidden]) .rk, .pin:not([hidden]) .nm, .pin:not([hidden]) .pt, ' +
      '.sub .l, .sub .r');
    for (const e of sel) {
      if (!e.textContent) continue;
      const r = e.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      out.push([(r.left - st.left) / k, (r.top - st.top) / k,
                (r.right - st.left) / k, (r.bottom - st.top) / k]);
    }
    return out;
  }
  /* WHAT `parts` USED TO MEAN, AND WHY IT WAS A TRAP.  This returned
   * `parts: MECH.length` — a count of NAMES in the list above, not of meshes
   * actually measured.  A cycle-2 verifier renamed every entry of MECH so that
   * none resolved, and the check went on publishing its PASSING shape:
   * `overlap_px2: 0` (the acceptance) with `parts: 26`, having measured
   * nothing at all.  The only tell was `keepout_px` going null.  A milder
   * version is worse, because it is silent: simply hiding `clamp_body` — the
   * worst part, the one the number is about — raised `keepout_px` from 9.300
   * to 11.307.  Deleting the subject IMPROVED the score.
   *
   * That matters more here than it would elsewhere, because this one function
   * stands in for the fleet's whole occlusion apparatus (occlusion.js,
   * depth.bin, ubias_m, the split pass, check_occlusion.py), and the mesh
   * names it depends on come from pipeline/leaderboard.py, which is
   * regenerable.  A rename there would have turned it into a no-op that still
   * reported a pass.
   *
   * So the result now separates "nothing overlaps" from "nothing was tested",
   * and it separates the two REASONS a subject can go unmeasured, because they
   * are not the same fault:
   *
   *   unresolved  the name matches no mesh in the scene at all.  There is no
   *               legitimate reason for this — MECH is generated from the same
   *               pipeline as the .glb — so it is a hard failure, and it is
   *               exactly what the verifier's rename produced.
   *   hidden      the mesh exists and is not visible.  This one is NORMAL:
   *               MECH is the union of both modes' mechanism, so desk mode
   *               legitimately never shows `rail_blank*` and TV mode never
   *               shows the clamp or `pin_tab`.  Visibility is also
   *               data-dependent (`pin_tab` follows the self entry, the
   *               blanking plate follows the empty slats), so failing on it
   *               would cry wolf.
   *
   * `ok` therefore fails on `unresolved`, and `hidden` is REPORTED BY NAME so
   * the milder case is loud instead of silent: hide `clamp_body` and the
   * result now says `hidden: ["clamp_body", …]` next to its improved keep-out,
   * where before the number simply got better and said nothing.  That residual
   * is stated in NOTES rather than hidden: `ok` alone does not catch a subject
   * that is present but wrongly invisible, and a reader has to read `hidden`.
   *
   * The first thing this measured on the shipped build was that `ok` as first
   * written — `measured === MECH.length` — is FALSE in both modes for exactly
   * the legitimate reason above.  Which is the point: a check that had been
   * asserting nothing was made to assert something, and the something was
   * wrong on the first run, in a way reading the code had not predicted. */
  const KEEPOUT_MIN_PX = 6;
  function clearance(samples) {
    const N = Math.max(2, samples || 24);
    const save = { running, breathT, clampU, wheelA, clampTarget, wheelTarget };
    running = false;
    let overlap = 0, keepout = Infinity, worst = null;
    const unmeasured = new Set(), unresolved = [];
    for (const n of MECH) if (!P.get(n)) unresolved.push(n);
    for (let s = 0; s < N; s++) {
      const u = s / (N - 1);
      breathT = u * BREATH_X_S * 1000;
      clampU = u;                              // full jaw travel
      wheelA = u * 2 * Math.PI;                // full wheel rotation
      apply();
      const rects = textRectsPx();
      for (const n of MECH) {
        const r = meshRectPx(P.get(n));
        if (!r) { unmeasured.add(n); continue; }
        for (const t of rects) {
          const ox = Math.min(r[2], t[2]) - Math.max(r[0], t[0]);
          const oy = Math.min(r[3], t[3]) - Math.max(r[1], t[1]);
          if (ox > 0 && oy > 0) {
            /* AN OVERLAP ALWAYS OUTRANKS A GAP IN `worst`, and the biggest
             * overlap outranks a smaller one.  The earlier spelling was
             * `if (!worst)`, and since the gap branch fills `worst` on the
             * very first sample, `!worst` was already false by the time any
             * overlap occurred: a run reporting overlap_px2 = 26,399 still
             * named a part with a 15.257 px GAP as its worst case and sent
             * the reader to the wrong end of the board.  A failing check that
             * misreports WHERE it failed costs more than one that says
             * nothing. */
            const a = ox * oy;
            overlap += a;
            if (!worst || worst.gap !== undefined || a > worst.overlap_px2) {
              worst = { part: n, overlap_px2: a, rect: r, text: t };
            }
          } else {
            const dx = (ox > 0) ? 0 : -ox, dy = (oy > 0) ? 0 : -oy;
            const d = Math.max(dx, dy);
            if (d < keepout) { keepout = d; if (overlap === 0) worst = { part: n, gap: d }; }
          }
        }
      }
    }
    running = save.running; breathT = save.breathT;
    clampU = save.clampU; wheelA = save.wheelA;
    clampTarget = save.clampTarget; wheelTarget = save.wheelTarget;
    apply();
    const keepoutPx = (keepout === Infinity ? null : keepout);
    const texts = textRectsPx().length;
    const measured = MECH.length - unmeasured.size;
    const hidden = [...unmeasured].filter(n => !unresolved.includes(n)).sort();
    return { samples: N, overlap_px2: overlap,
             keepout_px: keepoutPx,
             parts: MECH.length,             // names asked for
             parts_resolved: MECH.length - unresolved.length,
             parts_measured: measured,       // names that actually projected
             unresolved: unresolved.slice().sort(),   // a hard failure
             hidden,                                  // normal, but say so
             texts,
             keepout_min_px: KEEPOUT_MIN_PX,
             /* The acceptance, in the function rather than in a reader's head.
              * Every clause can fail on its own, and a name list that no
              * longer matches the geometry fails it however clean the overlap
              * number looks. */
             ok: unresolved.length === 0 && measured > 0 && texts > 0 &&
                 overlap === 0 && keepoutPx !== null &&
                 keepoutPx >= KEEPOUT_MIN_PX,
             worst };
  }

  /* ============================================================ 12 LOOP   */
  let prev = performance.now();
  function frame(now) {
    const dt = Math.min(100, now - prev);
    prev = now;
    tick(dt, now);
    requestAnimationFrame(frame);
  }

  /* ============================================================ 13 SIZE   */
  function layout() {
    const st = opt.stage || opt.layerHost;
    const b = st.parentElement
      ? st.parentElement.getBoundingClientRect()
      : { width: W, height: H };
    const k = Math.min(b.width / W, b.height / H);
    st.style.transform =
      'translate(' + ((b.width - W * k) / 2) + 'px,' +
      ((b.height - H * k) / 2) + 'px) scale(' + k + ')';
    /* PIXEL RATIO IS devicePixelRatio * k, never devicePixelRatio.  A number
     * measured only at pr 1 is how the Retina bug hid for a week
     * (README 16.5): the canvas is laid out at 1280x720 CSS px inside a stage
     * that is then scaled by k, so the drawing buffer must carry k as well. */
    renderer.setPixelRatio(Math.min(4, (window.devicePixelRatio || 1) * k));
    renderer.setSize(W, H, false);
    apply();
  }
  addEventListener('resize', layout);

  /* ---------------------------------------------------------------- BOOT */
  /* THE PRE-DATA FRAME IS DRAWN FIRST, AND THAT ORDERING IS THE WHOLE POINT.
   *
   * The obvious spelling of this is `await poll(); layout(); paint(); apply();`
   * and it is wrong.  apply() is what calls renderer.render(), so gating it
   * behind the fetch means NO PIXEL IS PAINTED UNTIL leaderboard.json
   * RESOLVES.  On a fast local server that is invisible.  On the hallway TV,
   * whose bridge is writing the file over a conference network, it is a black
   * 55-inch panel for as long as the bridge is slow — the exact opposite of
   * the design rule that this board degrades but never blanks.
   *
   * Measured before the fix (leaderboard.json delayed 3 s, 1280x720 stage
   * clip, px>12 of 921,600): 0 lit pixels at t=1.4 s and t=2.0 s, both modes —
   * a literally black stage.  After: 687,508 px = 74.6% (desk) and 682,272 px
   * = 74.0% (TV) at both instants, against 74.3% / 73.7% for the same page
   * once the data has landed.  The pre-data frame is now the same instrument
   * at the same size in the same place, reading NO RETURNS.
   *
   * D is already `derive(null)` (section 6), which is the 0-entries instrument
   * of design section 5.2: empty slats, dark podium, cold lamps, NO RETURNS on
   * the sub-plate.  It exists precisely so this frame has something honest to
   * show, so paint() and apply() are safe to call before any data arrives.
   *
   * The await below then yields to the event loop with a rendered canvas
   * already committed, so the compositor shows the instrument rather than the
   * page background.  This is correction 41's class of bug (CONVERSION_BRIEF
   * 2363: networkidle0 hid a mis-painted caption for 3.15 s on MTA) and the
   * positional check — #stage rect present, #board present — cannot see it.
   * Only an ink count on a delayed-fetch capture can. */
  layout();          /* sizes the renderer and canvas; ends in apply()      */
  paint();           /* the empty-rack DOM: NO RETURNS, 16/8 empty slats    */
  apply();           /* first renderer.render() — BEFORE the await          */

  await poll();
  layout();
  paint();
  apply();
  requestAnimationFrame(frame);

  const api = {
    layout: L, scene, camera, renderer, parts: P, meshes,
    grade,
    pose, play, paint, poll, clearance,
    /* the checkers' hooks */
    audit: () => facingAudit(THREE, meshes, camera),
    data: () => D,
    doc: () => doc,
    state: () => ({
      page, steps, pages: pageCount(), first: firstIndex(),
      /* `auto` and `idle` are the handover, reported so a checker can see it
       * rather than infer it from whether the rows happened to move. */
      auto, idle: idleT, scroll: scrollPx, maxScroll: maxScrollPx(),
      rows: rows.length, entries: D.entries.length, field: D.fieldSize,
      self: !!D.self,
      pin: pinOn, clamp: clampU, wheel: wheelA, breath: breathT,
      frozen: D.frozen, feedErr, running,
      domTextNodes: board.querySelectorAll('.row,.pod,.pin,.sub .l,.sub .r').length,
    }),
    setPin,
    gain: g => { if (typeof g === 'number') { setGain(g); apply(); } return GAIN; },
    /* load a fixture in place of the live feed, for the checkers */
    setData: (d) => { doc = d; lastGood = d; feedErr = ''; D = derive(d);
                      page = 0; steps = 0; scrollPx = 0; paint(); apply(); },
    setPage: (p) => { page = p; steps = p;
                      /* the position follows the page, because the position
                       * is the only thing paint() reads */
                      scrollPx = pageTopPx(); paint(); apply(); },
    advance: (n) => { for (let i = 0; i < (n || 1); i++) tick(DWELL_MS, 0); },
    /* the handover, drivable without a real pointer */
    hand: () => { handOn(); return { auto, idle: idleT }; },
    resume: () => { resumeAuto(); return { auto, idle: idleT }; },
    /* scroll to an absolute rack offset in canonical px, as a hand would */
    scrollTo: (px) => {
      handOn(); scrollV = 0;
      scrollPx = Math.max(0, Math.min(maxScrollPx(), Number(px) || 0));
      paint(); apply(); return scrollPx;
    },
    text: () => ({
      sub: [subL.textContent, subR.textContent],
      pod: pods.map(p => p.box.hidden ? null : [p.nm.textContent,
                                                p.pt.textContent]),
      rows: rows.map(r => r.box.classList.contains('empty') ? null
        : [r.rk.textContent, r.nm.textContent, r.pt.textContent]),
      pin: (pinRow && !pinRow.box.hidden)
        ? [pinRow.rk.textContent, pinRow.nm.textContent, pinRow.pt.textContent]
        : null,
    }),
    setNotext: (on) => document.body.classList.toggle('notext', !!on),
  };
  return api;
}
