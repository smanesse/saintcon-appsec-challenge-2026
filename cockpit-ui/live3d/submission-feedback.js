/* Submission feedback is advisory. Only the harness grants availability.
 * No local quota decrements, storage, wall-clock assumptions, or policy defaults.
 */
const TRACKS = { module: 'Modules', alien: 'A.L.I.E.N.' };

function duration(seconds) {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export function createFeedback({ load, render, clock = () => performance.now() }) {
  let snapshot = null;
  let received = clock();
  let phase = 'loading';
  let pending = false;
  let generation = 0;
  function paint() {
    const view = {};
    for (const [kind, label] of Object.entries(TRACKS)) {
      const row = snapshot && snapshot.limits[kind];
      view[kind] = row ? {
        state: row.reason || 'ready', canSubmit: row.can_submit === true,
        budget: row.daily_limit == null ? `${label}: no daily cap.`
          : `${label}: ${row.remaining} of ${row.daily_limit} submissions remaining today.`,
        message: row.reason === 'closed' ? 'Submissions are closed.'
          : row.reason === 'daily_limit' ? 'Daily limit reached.'
          : row.reason === 'rate_limited' ? 'Cooldown in progress.'
          : row.can_submit ? 'Ready to submit.' : 'Submission unavailable.',
        timer: row.reason === 'daily_limit'
          ? `Daily budget resets in ${duration(row.reset_after_seconds - (clock() - received) / 1000)}.`
          : row.reason === 'rate_limited' && row.retry_after_seconds > 0
            ? `Try again in ${duration(row.retry_after_seconds - (clock() - received) / 1000)}.` : '',
      } : {state: phase, canSubmit: false, budget: `${label}: limits unavailable.`,
        message: phase === 'auth' ? 'Sign in again to read submission limits.'
          : phase === 'error' ? 'Could not read submission limits. Refresh to retry.'
          : 'Checking submission limits…', timer: ''};
    }
    render(view, snapshot);
    return view;
  }
  async function refresh() {
    const request = ++generation;
    pending = true;
    snapshot = null;
    phase = 'loading';
    paint();
    try {
      const result = await load();
      if (request !== generation) return;
      if (result && (result.httpStatus === 401 || result.loggedIn === false)) {
        phase = 'auth';
      } else if (result && result.ok && !(result.httpStatus >= 400) && result.limits
        && Object.keys(TRACKS).every(kind => validRow(result.limits[kind]))) {
        snapshot = result;
      } else phase = 'error';
    } catch (_) {
      if (request !== generation) return;
      phase = 'error';
    }
    received = clock();
    pending = false;
    return paint();
  }
  function tick() {
    if (pending) return;
    const elapsed = (clock() - received) / 1000;
    if (elapsed >= 30 || snapshot && Object.values(snapshot.limits).some(row =>
      row.retry_after_seconds > 0 && elapsed >= row.retry_after_seconds
      || row.daily_limit !== null && elapsed >= row.reset_after_seconds)) {
      void refresh();
    } else paint();
  }
  paint();
  return { refresh, tick };
}

export function mountFeedback({root, load, onChange = () => {}, clock, tracks = Object.keys(TRACKS)}) {
  const doc = root.ownerDocument, win = doc.defaultView;
  const nodes = {};
  let disposed = false;
  for (const kind of tracks) {
    const label = TRACKS[kind];
    const line = root.appendChild(doc.createElement('p'));
    line.className = 'submission-limit';
    const budget = line.appendChild(doc.createElement('span'));
    const state = line.appendChild(doc.createElement('span'));
    state.setAttribute('role', 'status');
    state.setAttribute('aria-live', 'polite');
    const timer = line.appendChild(doc.createElement('span'));
    timer.setAttribute('role', 'timer');
    timer.setAttribute('aria-live', 'off');
    timer.setAttribute('aria-label', `${label} submission timer`);
    nodes[kind] = {budget, state, timer};
  }
  const updateText = (node, text) => {
    if (node.textContent !== text) node.textContent = text;
  };
  const controller = createFeedback({load, clock, render(view, snapshot) {
    if (disposed) return;
    for (const kind of tracks) {
      const row = view[kind], node = nodes[kind];
      updateText(node.budget, row.budget + ' ');
      updateText(node.state, row.message + ' ');
      updateText(node.timer, row.timer);
    }
    onChange(view, snapshot);
  }});
  const refresh = () => { if (!disposed) return controller.refresh(); };
  const retry = root.appendChild(doc.createElement('button'));
  retry.type = 'button';
  retry.className = 'submission-limits-refresh';
  retry.textContent = 'Refresh submission limits';
  retry.addEventListener('click', refresh);
  const visible = () => { if (!doc.hidden) refresh(); };
  const timer = win.setInterval(() => { if (!doc.hidden) controller.tick(); }, 1000);
  win.addEventListener('focus', refresh);
  doc.addEventListener('visibilitychange', visible);
  doc.addEventListener('submissionchange', refresh);
  function dispose() {
    disposed = true;
    win.clearInterval(timer);
    win.removeEventListener('focus', refresh);
    doc.removeEventListener('visibilitychange', visible);
    doc.removeEventListener('submissionchange', refresh);
    retry.removeEventListener('click', refresh);
  }
  return {refresh, dispose};
}

// The weapons console runs in a same-origin iframe; refresh cockpit signs too.
export function notifySubmissionChange(doc) {
  doc.dispatchEvent(new Event('submissionchange'));
  try {
    const parent = doc.defaultView?.parent?.document;
    if (parent && parent !== doc) parent.dispatchEvent(new Event('submissionchange'));
  } catch (_) { /* a standalone or cross-origin host has no cockpit to refresh */ }
}

function validRow(row) {
  const nonnegative = n => Number.isFinite(n) && n >= 0;
  return !!row && typeof row.can_submit === 'boolean'
    && nonnegative(row.retry_after_seconds) && nonnegative(row.reset_after_seconds)
    && (row.daily_limit === null && row.remaining === null
      || nonnegative(row.daily_limit) && nonnegative(row.remaining));
}
