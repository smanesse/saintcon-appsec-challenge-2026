/* SAINTCON 2026 — shared submission status + live-progress helpers.
 *
 * Both the cockpit grade panel (module track) and the weapons console (the
 * A.L.I.E.N. track on PKT) submit source to the same bridge endpoint and poll
 * the same sanitized submission shape. This module is the one place that turns
 * that shape into words and into the "what is being scored right now" view, so
 * the two consoles read identically.
 *
 * It mirrors the harness's own scoring view (grade_progress / display.py): a
 * phase pipeline (functional -> security, or aliens) and a per-item state. The
 * bridge forwards `progress.phase` and `progress.phases.*.items[].{name,state}`
 * with every count/ratio stripped, so NOTHING here shows totals, remaining, or
 * n/m progress — by design. Keep the state tokens in step with the harness.
 *
 * No innerHTML: every string reaches the page through textContent.
 */

const STATUS = {
  SUBMITTED: 'Waiting in line.',
  QUEUED: 'Waiting in line.',
  PENDING: 'Being graded.',
  RUNNING: 'Being graded.',
  COMPLETE: 'The grade finished.',
  FAILED: 'The grade failed.',
};
const WORD = {
  SUBMITTED: 'Waiting',
  QUEUED: 'Waiting',
  PENDING: 'Running',
  RUNNING: 'Running',
  COMPLETE: 'Finished',
  FAILED: 'Failure',
};

export function STATUS_WORDS(name) {
  return STATUS[name] || (name ? 'Waiting in line.' : 'No running grades.');
}

export function statusWord(name) {
  return WORD[name] || 'Waiting';
}

export function isTerminal(name) {
  return name === 'COMPLETE' || name === 'FAILED';
}

const PHASE_ORDER = ['functional', 'security', 'aliens'];
const PHASE_HEAD = {
  preparing: 'Preparing', functional: 'Functional tests',
  security: 'Security PoCs', aliens: 'A.L.I.E.N. ships', done: 'Finishing up',
};
const STEP_LABEL = {
  functional: 'Functional', security: 'Security', aliens: 'A.L.I.E.N.',
};
const STATE_GLYPH = {
  pending: '·', running: '⟳', pass: '✓', solved: '✓', done: '✓',
  fail: '✗', missed: '✗', error: '⚠', skipped: '⊘', 'not-attempted': '⊘',
};
const TERMINAL_ITEM = new Set([
  'pass', 'fail', 'error', 'done', 'solved', 'missed', 'skipped', 'not-attempted',
]);

/* "file-management-module" -> "file-management"; "aliens/x" -> "x". */
export function cleanItemName(name) {
  return String(name == null ? '' : name)
    .replace(/^aliens\//, '').replace(/-module$/, '');
}

/* Shape the sanitized progress object into a stepper + a chip list for the
 * phase running right now. Returns null when there is nothing live to show. */
export function progressView(sub) {
  const p = sub && sub.progress;
  if (!p || typeof p !== 'object' || !p.phase) return null;
  const phases = (p.phases && typeof p.phases === 'object') ? p.phases : {};
  const steps = [];
  for (const ph of PHASE_ORDER) {
    const rec = phases[ph];
    const present = rec && typeof rec === 'object';
    if (!present && ph !== p.phase) continue;
    const items = present && Array.isArray(rec.items) ? rec.items : [];
    let state = 'todo';
    if (p.phase === ph) state = 'current';
    else if (items.length && items.every(it => it && TERMINAL_ITEM.has(it.state))) state = 'done';
    steps.push({ name: STEP_LABEL[ph] || ph, state });
  }
  const rec = phases[p.phase];
  const curItems = rec && Array.isArray(rec.items) ? rec.items : [];
  const items = [];
  for (const it of curItems) {
    const name = cleanItemName(it && it.name);
    if (!name) continue;
    const st = it && it.state ? String(it.state) : 'pending';
    items.push({ name, state: st, glyph: STATE_GLYPH[st] || '·' });
  }
  return { phase: p.phase, label: PHASE_HEAD[p.phase] || String(p.phase), steps, items };
}

/* Compact one-line summary for the status strip tell. `active` is true only
 * while a job is non-terminal (there is something being scored to point at). */
export function tellFor(sub) {
  const name = sub && sub.status_name;
  if (!name || isTerminal(name)) return { active: false, text: '' };
  const view = progressView(sub);
  return { active: true, text: view ? ('Scoring: ' + view.label) : STATUS_WORDS(name) };
}

/* Paint the live indicator into `root`, creating a stable sp-* structure the
 * first time. Hides `root` (and returns false) when there is no live progress.
 * The caller owns `root`'s placement and its outer class; this owns its guts. */
export function renderProgress(root, sub) {
  if (!root) return false;
  let head = root.querySelector('.sp-head');
  let steps = root.querySelector('.sp-steps');
  let chips = root.querySelector('.sp-chips');
  if (!head || !steps || !chips) {
    root.replaceChildren();
    head = document.createElement('p');
    head.className = 'sp-head';
    steps = document.createElement('div');
    steps.className = 'sp-steps';
    chips = document.createElement('div');
    chips.className = 'sp-chips';
    root.append(head, steps, chips);
  }
  const view = progressView(sub);
  if (!view) {
    root.hidden = true;
    root.removeAttribute('data-phase');
    head.textContent = '';
    steps.replaceChildren();
    chips.replaceChildren();
    return false;
  }
  root.hidden = false;
  root.setAttribute('data-phase', view.phase);
  head.textContent = 'Scoring: ' + view.label;
  steps.replaceChildren();
  view.steps.forEach((s, i) => {
    if (i) {
      const sep = document.createElement('span');
      sep.className = 'sp-sep';
      sep.setAttribute('aria-hidden', 'true');
      sep.textContent = '▸';
      steps.appendChild(sep);
    }
    const el = document.createElement('span');
    el.className = 'sp-step'
      + (s.state === 'current' ? ' is-current' : s.state === 'done' ? ' is-done' : '');
    el.textContent = s.name;
    steps.appendChild(el);
  });
  chips.replaceChildren();
  for (const it of view.items) {
    const chip = document.createElement('span');
    chip.className = 'sp-chip is-' + it.state;
    const nm = document.createElement('span');
    nm.className = 'sp-chip-name';
    nm.textContent = it.name;
    const gl = document.createElement('span');
    gl.className = 'sp-chip-glyph';
    gl.setAttribute('aria-hidden', 'true');
    gl.textContent = it.glyph;
    chip.append(nm, gl);
    chips.appendChild(chip);
  }
  return true;
}
