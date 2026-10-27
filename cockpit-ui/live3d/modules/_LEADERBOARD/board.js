/* SAINTCON 2026 — the muster board page.  Thin on purpose.
 *
 * Everything that is the board lives in live3d/leaderboard.js, which is one
 * file for one component the way refit.js and mast.js are one file for all
 * nine modules.  What is here is what a PAGE owns: the DEV toolbar, the #note
 * line, and the `window.__loaded` flag every capture harness in this fleet
 * waits on.
 *
 * THE URL NO LONGER SELECTS A BOARD.  It used to: `?tv=1` gave you a
 * different chassis, a different type size, no pointer and no clamp.  There is
 * one board now and every URL below draws the same one --
 *
 *     .../modules/_LEADERBOARD/            the board
 *     .../modules/_LEADERBOARD/?tv=1       the board.  Accepted, inert.
 *     .../modules/_LEADERBOARD/?embed=1    the board, transparent, for the
 *                                          cockpit's overlay iframe
 *     .../modules/_LEADERBOARD/?dev=1      the board, plus the dev toolbar
 *
 * -- and `?pages=N` still sets how far the UNATTENDED loop cycles before its
 * carriage return.  It does not limit a hand, which reaches the whole field.
 *
 * `window.__board` is the checkers' hook, in the same class as each module's
 * `window.__occ`: pose(), clearance(), audit(), state(), text(), setData().
 */
import { mountBoard } from '../../leaderboard.js';

const $ = id => document.getElementById(id);

function fail(msg) {
  const e = $('err');
  e.style.display = 'block';
  e.textContent = msg;
  throw new Error(msg);
}
addEventListener('error', ev => {
  const e = $('err'); e.style.display = 'block';
  e.textContent = 'PAGE ERROR: ' + ev.message;
});

const Q = new URLSearchParams(location.search);
const PAGES = Q.get('pages') || undefined;
/* `?tv=1` IS KEPT AND DOES NOTHING, deliberately.  It is printed on things,
 * bookmarked on the machine that drives the hallway panel, and pasted into
 * notes; making it 404 or throw would break those for no gain, and making it
 * mean something again would be the two-mode build coming back.  It is read
 * here only so that this comment has somewhere to live. */
void Q.get('tv');

let B;
try {
  B = await mountBoard({
    canvas: $('gl'),
    stage: $('stage'),
    layerHost: $('stage'),
    hotsHost: $('hots'),
    assets: '../../assets/_leaderboard/',
    /* SAME ORIGIN, LOCAL FILE.  The bridge writes it; this page never makes a
     * request off the machine.  live3d/leaderboard.js section 7. */
    data: (Q.get('data') || '/api/scoreboard?all=1'),
    pages: PAGES,
  });
} catch (e) {
  fail('The muster board could not start.\n\n' + (e && e.message || e) +
       '\n\nServe the REPO ROOT, not this folder:\n' +
       '    cd <repo>/2026 && ./live3d/run.sh');
}
window.__board = B;

/* ------------------------------------------------------------------ chrome */
let wantText = true, wantDbg = false;
$('bText').addEventListener('click', function () {
  wantText = !wantText;
  this.classList.toggle('on', wantText);
  this.textContent = wantText ? 'dom text' : 'dom text: off';
  B.setNotext(!wantText);
});
$('bDbg').addEventListener('click', function () {
  wantDbg = !wantDbg;
  this.classList.toggle('on', wantDbg);
  document.body.classList.toggle('debug', wantDbg);
});
/* The clamp toggle.  It is a DEV convenience only: the affordance a player
 * uses is the clamp itself, which is a hotspot on the board (scene.json ->
 * hotspots, id `pin`) and is there whether this toolbar is or not.  Whether
 * there is a clamp to toggle at all is the FEED's question — a document with
 * no `self` puts a blanking plate on the rail and this button has nothing to
 * grip. */
const bp = $('bPin');
bp.addEventListener('click', function () {
  const on = !B.state().pin;
  B.setPin(on);
  this.classList.toggle('on', on);
});
bp.classList.toggle('on', B.state().pin);

function note() {
  const s = B.state();
  $('note').textContent =
    s.entries + ' of ' + s.field + ' · ' +
    s.rows + ' slots · rows ' + (s.first + 4) + '+ · page ' +
    (s.page + 1) + '/' + s.pages +
    (s.auto ? ' · auto' : ' · HAND') +
    (s.frozen ? ' · FINAL' : '') + (s.feedErr ? ' · NO FEED' : '');
}
note();
/* The note is refreshed off the same rAF the board runs on, not a timer:
 * nothing on this page may be on setInterval — live3d/leaderboard.js note 2. */
let lastNote = '';
(function loop() {
  const s = B.state();
  const k = s.entries + '/' + s.field + '/' + s.page + '/' + s.frozen +
            '/' + s.feedErr + '/' + s.pin + '/' + s.auto + '/' + s.first;
  if (k !== lastNote) { lastNote = k; note(); }
  requestAnimationFrame(loop);
})();

window.__loaded = true;
