/* Daily counts come only from the authenticated admission snapshot.
 * History is paginated and does not express the admission policy.
 */
export const EMPTY = 'Unavailable';
export const NO_CAP = 'No daily cap';

export function countText(value) {
  if (value === null) return NO_CAP;
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
    ? String(value) : EMPTY;
}

/* The budget is per calendar day and always rolls over at the harness's local
 * midnight (see submissions.py). We say "today" unconditionally because the cap
 * is daily by contract, and name the reset instant from the snapshot's
 * `reset_at` when it is known, falling back to the documented midnight boundary
 * when the snapshot has not arrived yet. A track with no cap never resets. */
export function resetTimeText(resetAt) {
  if (typeof resetAt !== 'string' || resetAt === '') return 'midnight';
  const when = new Date(resetAt);
  if (Number.isNaN(when.getTime())) return 'midnight';
  return when.toLocaleTimeString([], {
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  });
}

export function noteText(valueText, resetAt) {
  if (valueText === NO_CAP) return 'No daily reset';
  return 'for today · resets ' + resetTimeText(resetAt);
}

/* Pull the reset instant out of the snapshot. Both tracks share the same daily
 * boundary, so either row answers; module first, then alien. */
export function resetFromSnapshot(snapshot) {
  if (!snapshot || snapshot.ok !== true || !snapshot.limits) return undefined;
  for (const kind of ['module', 'alien']) {
    const row = snapshot.limits[kind];
    if (row && typeof row.reset_at === 'string' && row.reset_at !== '') return row.reset_at;
  }
  return undefined;
}

export function remainingFromSnapshot(snapshot) {
  const value = kind => {
    const row = snapshot?.ok && snapshot.limits?.[kind];
    if (!row) return undefined;
    if (row.daily_limit === null && row.remaining === null) return null;
    return Number.isInteger(row.daily_limit) && row.daily_limit > 0
      && Number.isInteger(row.remaining) && row.remaining >= 0
      && row.remaining <= row.daily_limit ? row.remaining : undefined;
  };
  return {grading: value('module'), alien: value('alien')};
}

/* Remaining out of allowed, only when the snapshot names both. No cap is not a fraction. */
export function budgetUse(snapshot, kind) {
  const row = snapshot?.ok && snapshot.limits?.[kind];
  if (!row) return null;
  if (row.daily_limit === null) return { capped: false };
  if (!(Number.isInteger(row.daily_limit) && row.daily_limit > 0
      && Number.isInteger(row.remaining) && row.remaining >= 0
      && row.remaining <= row.daily_limit)) return null;
  return {
    capped: true,
    left: row.remaining,
    allowed: row.daily_limit,
    text: row.remaining + '/' + row.daily_limit,
  };
}

function paintBoxes(node, left, allowed) {
  const doc = node.ownerDocument;
  let boxes = node.querySelectorAll('.sl-box');
  if (boxes.length > allowed) {
    for (let i = boxes.length - 1; i >= allowed; i--) boxes[i].remove();
    boxes = node.querySelectorAll('.sl-box');
  }
  for (let i = boxes.length; i < allowed; i++) {
    const box = doc.createElement('span');
    box.className = 'sl-box';
    box.setAttribute('aria-hidden', 'true');
    node.appendChild(box);
  }
  boxes = node.querySelectorAll('.sl-box');
  for (let i = 0; i < boxes.length; i++) {
    boxes[i].classList.toggle('is-left', i < left);
  }
}

export function paintBudget(root, snapshot) {
  if (!root) return;
  for (const [track, kind] of [['grading', 'module'], ['alien', 'alien']]) {
    const use = budgetUse(snapshot, kind);
    root.querySelectorAll('[data-budget="' + track + '"]').forEach(node => {
      const text = !use ? EMPTY : use.capped ? use.text : NO_CAP;
      if (node.textContent !== text) node.textContent = text;
      node.classList.toggle('known', !!(use && use.capped));
    });
    root.querySelectorAll('[data-budget-boxes="' + track + '"]').forEach(node => {
      if (!use || !use.capped) {
        if (node.childElementCount) node.replaceChildren();
        return;
      }
      paintBoxes(node, use.left, use.allowed);
    });
  }
}

export function paintSubmissionsLeft(host, counts, resetAt) {
  const shown = {grading: countText(counts?.grading), alien: countText(counts?.alien)};
  for (const [track, text] of Object.entries(shown)) {
    host?.querySelectorAll('[data-track="' + track + '"]').forEach(node => {
      node.textContent = text;
      node.classList.toggle('known', text !== EMPTY);
    });
    const note = noteText(text, resetAt);
    host?.querySelectorAll('[data-track-note="' + track + '"]').forEach(node => {
      node.textContent = note;
    });
  }
  return shown;
}
