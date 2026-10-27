/* SAINTCON 2026 — A.L.I.E.N. fleet-scoring form for the weapons console.
 *
 * You edit the exploit stub on disk (aliens/<ship>/exploit.py), pick ONE ship,
 * and either:
 *   - Test locally  -> the bridge runs your exploit against the locally-running
 *                      teaching ship and reports whether it captured the flag
 *                      (POST /api/alien/test, loopback-only on the bridge).
 *   - Submit remote -> package the exploit and grade it against the released
 *                      ship in the cloud (POST /api/submit {kind:"alien"}), with
 *                      the shared live scoring indicator.
 *
 * It is wired to the Signal Harpoon: picking a ship aims the harpoon, and a
 * finished run reports a verdict (hit / deflected / refused) so the harpoon can
 * play its reel + impact animation. The PKT scene passes `onSelectShip` and
 * `onResult`, and drives this back through `selectShipByNumber` / `launch`.
 *
 * Same-origin /api/* via api.js. The live indicator/status words are the shared
 * submit-core. No innerHTML: every string reaches the page through textContent.
 */
import { submit, getSubmission, getSubmissions, getChallenges, alienTest, getSubmissionLimits } from './api.js';
import { STATUS_WORDS, isTerminal, renderProgress } from './submit-core.js';
import { notifySubmissionChange } from './submission-feedback.js';
import { paintBudget, budgetUse } from './submissions-left.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function newest(list) {
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

function isAlienRow(row) {
  if (!row || typeof row !== 'object') return false;
  // An explicit `kind` is authoritative. Module rows also carry alien_* fields
  // (alien_status, alien_target: null, aliens: []) that the bridge sanitizer
  // preserves, so the legacy shape heuristics below must only run when `kind`
  // is absent — otherwise a module grade is misclassified as an alien one.
  if (typeof row.kind === 'string' && row.kind) {
    return row.kind.toLowerCase() === 'alien';
  }
  if (Object.prototype.hasOwnProperty.call(row, 'alien_status')) return true;
  if (Object.prototype.hasOwnProperty.call(row, 'alien_target')) return true;
  if (Array.isArray(row.aliens)) return true;
  return false;
}

function shipNumFromPath(p) {
  const m = /aliens\/(\d+)/.exec(String(p || ''));
  return m ? parseInt(m[1], 10) : 0;
}

function boardedLines(sub) {
  const aliens = sub && Array.isArray(sub.aliens) ? sub.aliens : [];
  const out = [];
  for (const a of aliens) {
    if (!a || typeof a !== 'object') continue;
    const label = (a.name != null && a.name !== '') ? String(a.name)
      : (a.id != null ? String(a.id) : '');
    if (label) out.push(label + ' boarded');
  }
  return out;
}

export function mountAlienSubmit(host, opts) {
  const o = opts || {};
  host.replaceChildren();
  host.classList.add('as-root', 'ac-panel');

  const modeRow = el('div', 'as-mode');
  const localBtn = el('button', 'as-mode-btn on', 'Test locally');
  localBtn.type = 'button';
  const remoteBtn = el('button', 'as-mode-btn', 'Submit to remote');
  remoteBtn.type = 'button';
  modeRow.append(localBtn, remoteBtn);

  const shipRow = el('div', 'ac-row');
  const shipLab = el('label', null, 'Ship');
  const select = el('select', 'as-target');
  shipLab.appendChild(select);
  const actBtn = el('button', 'ac-act', 'Run against local ship');
  actBtn.type = 'button';
  actBtn.disabled = true;
  shipRow.append(shipLab, actBtn);

  const alienBox = el('div', 'as-alien-box');
  alienBox.hidden = true;
  const alienLead = el('span', 'as-alien-lead', 'Alien submissions remaining:');
  const alienCount = el('span', 'as-alien-n', 'Unavailable');
  alienCount.setAttribute('data-budget', 'alien');
  const alienBoxes = el('span', 'as-alien-boxes');
  alienBoxes.setAttribute('data-budget-boxes', 'alien');
  const alienRefresh = el('button', 'as-alien-refresh');
  alienRefresh.type = 'button';
  alienRefresh.title = 'Refresh remaining submissions';
  alienRefresh.setAttribute('aria-label', 'Refresh remaining submissions');
  const alienIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  alienIcon.setAttribute('viewBox', '0 0 16 16');
  alienIcon.setAttribute('width', '14');
  alienIcon.setAttribute('height', '14');
  alienIcon.setAttribute('aria-hidden', 'true');
  const alienPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  alienPath.setAttribute('d', 'M13.2 8a5.2 5.2 0 1 1-1.3-3.5');
  alienPath.setAttribute('fill', 'none');
  alienPath.setAttribute('stroke', 'currentColor');
  alienPath.setAttribute('stroke-width', '1.6');
  const alienArrow = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  alienArrow.setAttribute('d', 'M13.4 2.2v3.1H10.3');
  alienArrow.setAttribute('fill', 'none');
  alienArrow.setAttribute('stroke', 'currentColor');
  alienArrow.setAttribute('stroke-width', '1.6');
  alienIcon.append(alienPath, alienArrow);
  alienRefresh.appendChild(alienIcon);
  alienBox.append(alienLead, alienCount, alienBoxes, alienRefresh);

  const stub = el('p', 'as-stub');
  const status = el('p', 'ac-note', 'Edit the exploit stub on disk, then test or submit.');
  status.setAttribute('aria-live', 'polite');
  // Last remote submission for the selected ship. Hidden on Test locally, and
  // hidden until that ship has a refusal or a finished grade already on the page.
  const last = el('p', 'as-last');
  last.hidden = true;
  const lastK = el('span', 'as-last-k', 'Last submission');
  const lastV = el('span', 'as-last-v');
  lastV.setAttribute('role', 'status');
  last.append(lastK, lastV);
  const progress = el('div', 'as-progress sp-progress');
  progress.hidden = true;
  progress.setAttribute('aria-live', 'polite');
  const result = el('ul', 'as-solved');
  // The raw script output is an expandable disclosure (open by default, click
  // the label to collapse) rather than a fixed-height scroll box, with a label
  // that names it as what the exploit script printed.
  const output = el('details', 'as-output');
  const outputSummary = el('summary', 'as-output-summary', 'Output returned by your exploit');
  const outputPre = el('pre', 'as-output-pre');
  output.append(outputSummary, outputPre);
  output.hidden = true;

  host.append(modeRow, shipRow, alienBox, stub, status, last, progress, result, output);

  let budgetGen = 0;

  /* The person menu lives on the cockpit document. This form runs in the
   * weapons iframe, so paint that menu from the same snapshot when it is
   * reachable. A missing menu is not an error. */
  function paintPersonMenuAlien(snapshot) {
    const docs = [];
    const own = host.ownerDocument;
    if (own) docs.push(own);
    try {
      const parent = own && own.defaultView && own.defaultView.parent
        && own.defaultView.parent.document;
      if (parent && parent !== own) docs.push(parent);
    } catch (_) { /* a cross-origin host has no menu to paint */ }
    for (const doc of docs) {
      if (!doc || typeof doc.querySelectorAll !== 'function') continue;
      const painted = new Set();
      doc.querySelectorAll('#personMenu [data-budget="alien"]').forEach(node => {
        const root = (node.closest && node.closest('.sl-meter')) || node.parentElement || node;
        if (painted.has(root)) return;
        painted.add(root);
        paintBudget(root, snapshot);
      });
    }
  }

  /* Same fresh limits read the refresh button uses. Paint only when the
   * snapshot names a real alien budget. A failed read keeps the last numbers
   * and does not invent a cap or a local decrement. */
  async function refreshAlienBudget() {
    const gen = ++budgetGen;
    let snapshot;
    try {
      snapshot = await getSubmissionLimits('all', { cache: 'no-store', fresh: true });
    } catch (_) {
      return;
    }
    if (gen !== budgetGen) return;
    if (!budgetUse(snapshot, 'alien')) return;
    paintBudget(alienBox, snapshot);
    paintPersonMenuAlien(snapshot);
    const row = snapshot.limits.alien;
    availability = { alien: { canSubmit: row.can_submit === true } };
    setBusy(busy);
  }

  let mode = 'local';
  let timer = 0;
  let busyTick = 0;       // elapsed-time ticker for the blocking local run
  let busyStart = 0;
  let busy = false;
  let polledJob = null;   // job whose terminal we have already reported
  let runTarget = null;   // {id, name, num} the in-flight/last run is bound to
  let opGen = 0;          // bumped on each run/refresh; stale async work checks it
  let availability = {};
  // Ship id -> {kind, at, reason|boarded}. One slot for the form would show
  // ship A's refusal while ship B is selected.
  const lastByShip = new Map();
  let inflightShip = '';

  function stop() {
    if (timer) { clearTimeout(timer); timer = 0; }
    if (busyTick) { clearInterval(busyTick); busyTick = 0; }
  }
  function haveShip() { return !!(select.value && select.options.length); }
  function currentOpt() { return select.options[select.selectedIndex] || null; }
  function currentPath() { const op = currentOpt(); return op ? (op.dataset.path || '') : ''; }
  function currentNum() { const op = currentOpt(); return op ? parseInt(op.dataset.n || '0', 10) : 0; }
  function shipName() { const op = currentOpt(); return op ? op.textContent : ''; }

  function setBusy(on) {
    busy = on;
    actBtn.disabled = on || !haveShip() || (mode === 'remote' && !availability.alien?.canSubmit);
    select.disabled = on;
    localBtn.disabled = on;
    remoteBtn.disabled = on;
  }

  function paintStub() {
    const p = currentPath();
    stub.textContent = p ? ('Edit the exploit on disk: ' + p + '/exploit.py') : '';
  }

  // The status line mirrors the verdict colour: a flag-captured / ship-boarded
  // run reads green ('ok'), an unsuccessful one reads red ('fail'); any other
  // (idle, in-flight) state is neutral.
  function setStatus(text, tone) {
    status.textContent = text == null ? '' : text;
    status.classList.toggle('as-ok', tone === 'ok');
    status.classList.toggle('as-fail', tone === 'fail');
  }

  function shipKey(id) {
    if (id == null || id === '' || id === 'all') return '';
    return String(id);
  }

  function hideLast() {
    last.hidden = true;
    last.classList.remove('is-refused', 'is-boarded');
    lastV.textContent = '';
  }

  /* Newer stamp wins. An undated history row must not erase a refusal or
   * grade this page already recorded. */
  function noteLast(key, state, at) {
    if (!key || !state) return;
    const prev = lastByShip.get(key);
    if (prev && prev.at > at) return;
    lastByShip.set(key, Object.assign({ at: at }, state));
  }

  function stampOf(row) {
    const t = row && Date.parse(row.created);
    return Number.isNaN(t) ? -Infinity : t;
  }

  /* Paint only the selected ship's state, and only while Submit to remote
   * is selected. A local test must not show it, and a ship with no stored
   * result stays quiet — do not borrow another ship's line. */
  function paintLast() {
    if (mode !== 'remote') { hideLast(); return; }
    const key = shipKey(select.value);
    if (!key || inflightShip === key) { hideLast(); return; }
    const state = lastByShip.get(key);
    if (!state) { hideLast(); return; }
    if (state.kind === 'refused') {
      if (!state.reason) { hideLast(); return; }
      lastV.textContent = state.reason;
      last.classList.remove('is-boarded');
      last.classList.add('is-refused');
      last.hidden = false;
      return;
    }
    if (state.kind !== 'grade') { hideLast(); return; }
    lastV.textContent = state.boarded ? 'Boarded' : 'Not boarded';
    last.classList.remove('is-refused');
    last.classList.toggle('is-boarded', !!state.boarded);
    last.hidden = false;
  }

  function rememberRefusal(shipId, reason) {
    const key = shipKey(shipId);
    const text = typeof reason === 'string' ? reason.trim() : '';
    if (!key || !text) return;
    noteLast(key, { kind: 'refused', reason: text }, Date.now());
  }

  /* Boarded or not from the aliens list this page already has. Store the
   * word, not the flag or the script output. No list means no result. */
  function rememberGrade(shipId, sub) {
    const key = shipKey(shipId);
    if (!key || !sub || !isTerminal(sub.status_name) || !Array.isArray(sub.aliens)) return;
    const boarded = sub.aliens.some(a => a && typeof a === 'object');
    const at = stampOf(sub);
    noteLast(key, { kind: 'grade', boarded: boarded }, at === -Infinity ? Date.now() : at);
  }

  function gradeShip(sub) {
    const fromSub = sub && shipKey(sub.alien_target);
    if (fromSub) return fromSub;
    return runTarget ? shipKey(runTarget.id) : '';
  }

  function indexHistory(rows) {
    const best = new Map();
    for (const row of rows) {
      if (!isAlienRow(row)) continue;
      const key = shipKey(row.alien_target);
      if (!key) continue;
      const at = stampOf(row);
      const prev = best.get(key);
      if (!prev || at >= prev.at) best.set(key, { row: row, at: at });
    }
    for (const [key, item] of best) {
      const name = String(item.row.status_name || '');
      if (!isTerminal(name) || !Array.isArray(item.row.aliens)) continue;
      const boarded = item.row.aliens.some(a => a && typeof a === 'object');
      noteLast(key, { kind: 'grade', boarded: boarded }, item.at);
    }
  }

  /* The harness message, not a grade word. A transport failure has no such
   * body, so the widget stays quiet instead of inventing a reason. */
  function refusalReason(res) {
    const body = res && res.result;
    if (!body || typeof body !== 'object') return '';
    if (body.ok !== false && !body.error && !body.message) return '';
    const message = typeof body.message === 'string' ? body.message.trim() : '';
    if (message) return message;
    return typeof body.error === 'string' ? body.error.trim() : '';
  }

  function showOutput(text) {
    if (text) {
      outputPre.textContent = text;
      output.open = true;
      output.hidden = false;
    } else {
      hideOutput();
    }
  }

  function hideOutput() {
    output.hidden = true;
    output.open = false;
    outputPre.textContent = '';
  }

  function report(verdict, msg) {
    if (typeof o.onResult === 'function') {
      // A verdict names the ship the run was submitted for, not whatever the
      // picker happens to show now (the harpoon may have re-aimed meanwhile).
      const name = (runTarget && runTarget.name) || shipName() || 'target';
      o.onResult(verdict, 'A.L.I.E.N. // ' + name + '\n' + msg);
    }
  }

  function targetNow() {
    return { id: select.value, name: shipName() || ('Ship ' + currentNum()),
             num: currentNum() };
  }

  function optForId(id) {
    const want = String(id == null ? '' : id);
    if (!want) return null;
    for (const op of select.options) if (op.value === want) return op;
    return null;
  }

  /* A new selection invalidates the last run's verdict and output. Never runs
   * mid-run: the picker is disabled while busy and programmatic re-aims no-op. */
  function clearResults() {
    stop();
    runTarget = null;
    result.replaceChildren();
    hideOutput();
    renderProgress(progress, null);
    setStatus(mode === 'local'
      ? 'Runs your exploit against the local teaching ship (stdlib only).'
      : 'Grades your exploit against the released ship in the cloud.', null);
    paintLast();
  }

  function setMode(next) {
    mode = next;
    localBtn.classList.toggle('on', mode === 'local');
    remoteBtn.classList.toggle('on', mode === 'remote');
    localBtn.setAttribute('aria-pressed', mode === 'local' ? 'true' : 'false');
    remoteBtn.setAttribute('aria-pressed', mode === 'remote' ? 'true' : 'false');
    actBtn.textContent = mode === 'local' ? 'Run against local ship' : 'Submit for scoring';
    alienBox.hidden = mode !== 'remote';
    setBusy(busy);
    if (mode === 'remote') refreshAlienBudget();
    setStatus(mode === 'local'
      ? 'Runs your exploit against the local teaching ship (stdlib only).'
      : 'Grades your exploit against the released ship in the cloud.', null);
    stop();
    runTarget = null;
    renderProgress(progress, null);
    result.replaceChildren();
    hideOutput();
    paintLast();
  }

  /* ---- local test ---------------------------------------------------- */
  const LOCAL_ERR = {
    unknown_ship: 'This ship has no local copy to test against.',
    aliens_compose_missing: 'No local A.L.I.E.N. fleet found (aliens/docker-compose.yml).',
    ship_start_failed: 'Could not start the local ship (see the bridge logs).',
    ship_start_timeout: 'Timed out starting the local ship.',
    ship_unreachable: 'The ship started but did not answer in time.',
    conflict: 'The local fleet is busy. Try again in a moment.',
    'compose project unavailable': 'Could not start the local ship (compose unavailable).',
  };

  /* The local test is one blocking request (the bridge brings the ship up,
   * runs the exploit, then tears it down). There is no server-side progress to
   * poll, so show an indeterminate bar plus an elapsed-time tell so the console
   * reads as working, not hung. */
  function startLocalBusy() {
    busyStart = Date.now();
    progress.hidden = false;
    progress.replaceChildren();
    const bar = el('div', 'as-busy');
    bar.setAttribute('aria-hidden', 'true');
    bar.appendChild(el('span', 'as-busy-fill'));
    progress.appendChild(bar);
    const paint = () => {
      const s = Math.max(0, Math.round((Date.now() - busyStart) / 1000));
      const hint = s < 20 ? '' : s < 90
        ? ' — first run builds the ship image'
        : ' — still building/running the ship';
      setStatus('Running your exploit against the local ship (' + s + 's)' + hint + '.', null);
    };
    paint();
    if (busyTick) clearInterval(busyTick);
    busyTick = setInterval(paint, 1000);
  }

  function stopLocalBusy() {
    if (busyTick) { clearInterval(busyTick); busyTick = 0; }
    progress.hidden = true;
    progress.replaceChildren();
  }

  function paintLocal(res) {
    result.replaceChildren();
    hideOutput();
    if (!res || res.reachable === false) {
      setStatus('The bridge could not be reached.', 'fail');
      report('refused', 'UPLINK FAILED');
      return;
    }
    if (res.ok === false || res.ran === false) {
      setStatus(LOCAL_ERR[res.error] || ('Local run failed: ' + (res.error || 'unknown error')), 'fail');
      report('refused', res.error === 'unknown_ship' ? 'NO LOCAL SHIP' : 'SHIP FAILED');
      showOutput(res.output);
      return;
    }
    if (res.timed_out) {
      setStatus('Timed out (~15s). Your exploit did not finish.', 'fail');
      report('deflected', 'TIMED OUT');
    } else if (res.solved) {
      setStatus('Local run: flag captured.', 'ok');
      result.appendChild(el('li', null, res.flag || 'SAINTCON{...}'));
      report('hit', 'FLAG CAPTURED');
    } else {
      setStatus('Local run: no flag in the output yet.', 'fail');
      report('deflected', 'NO FLAG');
    }
    // Show the script's output on every run that produced one, success included.
    showOutput(res.output);
  }

  async function runLocal() {
    if (busy || !haveShip()) return;
    const path = currentPath();
    if (!path) return;
    opGen++;                 // supersede any in-flight history restore
    runTarget = targetNow(); // bind this run's verdict to the ship we launch
    setBusy(true);
    result.replaceChildren();
    hideOutput();
    startLocalBusy();
    let res;
    try { res = await alienTest(path); }
    catch (e) { res = { reachable: false }; }
    stopLocalBusy();
    paintLocal(res);
    setBusy(false);
  }

  /* ---- remote scoring ------------------------------------------------ */
  function paintSolved(sub) {
    result.replaceChildren();
    if (!sub || !isTerminal(sub.status_name)) return;
    const aliens = sub && Array.isArray(sub.aliens) ? sub.aliens : [];
    const boarded = aliens.filter(a => a && typeof a === 'object');
    if (!boarded.length) {
      result.appendChild(el('li', 'as-none', 'Ship not boarded in this result.'));
      return;
    }
    for (const a of boarded) {
      const label = (a.name != null && a.name !== '') ? String(a.name)
        : (a.id != null ? String(a.id) : 'Ship');
      const li = el('li', null);
      li.appendChild(el('span', 'as-ship', label + ' boarded'));
      // A boarded ship with a configured reward flag carries the EARNED flag
      // (the harness attaches it; the random grading flag is never surfaced).
      if (a.flag) {
        li.classList.add('as-has-flag');
        li.appendChild(el('code', 'as-flag', String(a.flag)));
      }
      result.appendChild(li);
    }
    // A fresh boarded result means a newly-earned flag may exist: let the
    // menu-bar flag wallet pick it up.
    try {
      host.ownerDocument.dispatchEvent(new Event('flagschange'));
    } catch (_) { /* no document to notify */ }
  }

  function reportRemoteTerminal(sub) {
    const job = sub && (sub.job_id || sub.id);
    if (job && job === polledJob) return;    // already reported this job
    polledJob = job || polledJob;
    if (sub && sub.status_name === 'FAILED') { report('refused', 'GRADING ERROR'); return; }
    report(boardedLines(sub).length ? 'hit' : 'deflected',
      boardedLines(sub).length ? 'SHIP BOARDED' : 'NOT BOARDED');
  }

  function paintRemote(sub, err) {
    const name = sub && sub.status_name;
    if (err) {
      setStatus(String(err), 'fail');
    } else if (name && isTerminal(name)) {
      const boarded = name !== 'FAILED' && boardedLines(sub).length > 0;
      setStatus(STATUS_WORDS(name), boarded ? 'ok' : 'fail');
    } else {
      setStatus(STATUS_WORDS(name), null);
    }
    renderProgress(progress, err ? null : sub);
    paintSolved(err ? null : sub);
    if (err || (sub && isTerminal(sub.status_name))) {
      inflightShip = '';
      if (!err) rememberGrade(gradeShip(sub), sub);
    }
    paintLast();
    if (!name || isTerminal(name)) setBusy(false);
    if (sub && isTerminal(sub.status_name)) {
      notifySubmissionChange(host.ownerDocument);
      reportRemoteTerminal(sub);
    }
  }

  async function poll(jobId) {
    let res;
    try { res = await getSubmission(jobId); }
    catch (e) { res = null; }
    if (!res || (res.ok === false && !res.submission)) {
      if (res && res.error === 'timed out') {
        setStatus('Still waiting for the grade job.', null);
        timer = setTimeout(() => poll(jobId), 1200);
        return;
      }
      setStatus((res && res.error) || 'The grade job could not be read.', 'fail');
      inflightShip = '';
      setBusy(false);
      paintLast();
      return;
    }
    const sub = res.submission;
    paintRemote(sub, null);
    if (!sub || !isTerminal(sub.status_name)) {
      timer = setTimeout(() => poll(jobId), 1200);
    }
  }

  async function submitRemote() {
    if (busy || !haveShip() || !availability.alien?.canSubmit) return;
    stop();
    opGen++;                 // supersede any in-flight history restore
    runTarget = targetNow(); // bind this submission's verdict to the picked ship
    setBusy(true);
    polledJob = null;
    renderProgress(progress, null);
    result.replaceChildren();
    hideOutput();
    inflightShip = shipKey(runTarget && runTarget.id);
    paintLast();
    setStatus('Sending your A.L.I.E.N. exploits.', null);
    let res;
    try { res = await submit({ kind: 'alien', alien_target: select.value }); }
    catch (e) { res = null; }
    notifySubmissionChange(host.ownerDocument);
    if (!res || !res.ok || !res.job_id) {
      inflightShip = '';
      const reason = refusalReason(res);
      if (reason) rememberRefusal(runTarget && runTarget.id, reason);
      // The last-submission line already shows the harness sentence. Do not
      // copy it onto the status line as well.
      const fallback = 'The grade job was not accepted.';
      const other = (res && res.error && res.error !== reason) ? res.error : '';
      setStatus(reason ? (reason === fallback ? 'Not accepted.' : fallback) : (other || fallback), 'fail');
      paintLast();
      report('refused', 'REJECTED');
      setBusy(false);
      return;
    }
    /* Accepted now: refresh the remaining count from the server. Do not wait
     * for the grade, and do not show a checking line. */
    refreshAlienBudget();
    paintRemote({ status_name: (res.result && res.result.status_name) || 'QUEUED' }, null);
    poll(res.job_id);
  }

  function act() {
    if (mode === 'local') runLocal();
    else submitRemote();
  }

  /* ---- ship list ----------------------------------------------------- */
  function loadShips() {
    getChallenges().then((res) => {
      const ships = (res && Array.isArray(res.aliens)) ? res.aliens : [];
      const current = select.value;
      select.replaceChildren();
      for (const ship of ships) {
        if (!ship || ship.id == null) continue;
        const opt = el('option', null, ship.name ? String(ship.name) : ('Ship ' + ship.id));
        opt.value = String(ship.id);
        if (ship.challenge_path != null) {
          opt.dataset.path = String(ship.challenge_path);
          opt.dataset.n = String(shipNumFromPath(ship.challenge_path));
        }
        select.appendChild(opt);
      }
      if (Array.prototype.some.call(select.options, (x) => x.value === current)) {
        select.value = current;
      }
      // Rebuilding a catalog can select a different ship without a change event.
      if (select.value !== current) refreshAlienBudget();
      setBusy(busy);
      paintStub();
      if (!ships.length) setStatus('No A.L.I.E.N. ships have been released yet.', null);
      else if (typeof o.onSelectShip === 'function' && currentNum()) o.onSelectShip(currentNum());
    }).catch(() => { /* leave the picker empty; button stays disabled */ });
  }

  /* On mount, pick up a remote job still grading so the indicator resumes. */
  function refresh() {
    const myGen = ++opGen;
    getSubmissions().then(async (listed) => {
      // A run started (or another refresh fired) while this request was in
      // flight: a stale history response must not seize the active operation.
      if (myGen !== opGen || busy) return;
      if (!listed || listed.ok === false || !Array.isArray(listed.submissions)) return;
      const aliens = listed.submissions.filter(isAlienRow);
      indexHistory(aliens);
      const latest = newest(aliens);
      if (latest) {
        const name = String(latest.status_name || '');
        if (latest.job_id && name && !isTerminal(name)) {
          setMode('remote');
          // Bind the resumed indicator to the job's own target, and aim the
          // picker/harpoon at it, not at whatever ship was last selected.
          const op = optForId(latest.alien_target);
          if (op && select.value !== op.value) {
            select.value = op.value; paintStub(); refreshAlienBudget();
          }
          runTarget = {
            id: latest.alien_target,
            name: op ? op.textContent : ('Ship ' + (latest.alien_target != null ? latest.alien_target : '?')),
            num: op ? parseInt(op.dataset.n || '0', 10) : 0,
          };
          if (op && typeof o.onSelectShip === 'function' && runTarget.num) o.onSelectShip(runTarget.num);
          setBusy(true);
          polledJob = null;
          inflightShip = shipKey(latest.alien_target);
          poll(latest.job_id);
        }
      }
      paintLast();
    }).catch(() => { /* ignore */ });
  }

  alienRefresh.addEventListener('click', async () => {
    if (alienRefresh.classList.contains('is-reading')) return;
    const turn = new Promise(resolve => {
      let settled = false;
      const finish = () => { if (settled) return; settled = true; resolve(); };
      alienIcon.addEventListener('animationend', finish, { once: true });
      window.setTimeout(finish, 750);
    });
    alienRefresh.classList.add('is-reading');
    alienRefresh.setAttribute('aria-busy', 'true');
    try {
      await refreshAlienBudget();
    } finally {
      await turn;
      alienRefresh.classList.remove('is-reading');
      alienRefresh.removeAttribute('aria-busy');
    }
  });
  localBtn.addEventListener('click', () => { if (!busy) setMode('local'); });
  remoteBtn.addEventListener('click', () => { if (!busy) setMode('remote'); });
  select.addEventListener('change', () => {
    paintStub();
    clearResults();   // a different ship: the last verdict no longer applies
    refreshAlienBudget();
    if (typeof o.onSelectShip === 'function' && currentNum()) o.onSelectShip(currentNum());
  });
  actBtn.addEventListener('click', act);

  setMode('local');
  loadShips();
  refresh();

  return {
    /* Point the picker at ship `num` (1..4) without re-aiming the harpoon
     * (the harpoon is already there). Returns true only if that ship is in the
     * released picker. Never moves the picker during an active run. */
    selectShipByNumber(num) {
      let found = null;
      for (const op of select.options) {
        if (parseInt(op.dataset.n || '0', 10) === num) { found = op; break; }
      }
      if (!found) return false;
      if (busy) return true;   // listed, but don't move it out from under a run
      if (select.value !== found.value) {
        select.value = found.value;
        paintStub();
        clearResults();        // selection changed: drop the stale verdict
        refreshAlienBudget();
      }
      return true;
    },
    /* Launch the current mode's run for ship `num` (the harpoon trigger).
     * Returns true if a run actually started. */
    launch(num) {
      // Refuse an unreleased / unlisted contact: firing anyway would spend the
      // run on whatever ship the picker still holds.
      if (num && !this.selectShipByNumber(num)) return false;
      if (busy || !haveShip() || (mode === 'remote' && !availability.alien?.canSubmit)) return false;
      act();
      return true;
    },
    refresh: () => { loadShips(); refresh(); },
    stop,
    root: host,
  };
}
