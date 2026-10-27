/* SAINTCON 2026 — player status when this checkout is behind.
 *
 * People get a cleaned-up branch. Later commits add the next day's work.
 * GET /api/updates already says whether that branch is behind
 * (updateAvailable / behind). This only paints that.
 *
 * The menu item shows the current status. It does not apply. It does not
 * call POST /api/updates/apply. It does not show commit subjects, file names,
 * or day numbers. The day schedule already lives in bridge/release.py; this
 * file does not invent one.
 *
 * The item is never hidden. A current copy, or a check that is off, says
 * Up to date. While the copy is behind, the person button carries the
 * ripple. Clicking the rings or the item does not mark the copy current.
 *
 * Item words stay under 15 characters. Do not put "updates available" on
 * the item.
 *
 * NO innerHTML. textContent only. A dead read leaves the last status.
 */

const POLL_MS = 2 * 60 * 1000;

/* Owner will revise these two. Each must stay under 15 characters. */
const LABEL_CURRENT = 'Up to date';
const LABEL_BEHIND = 'New content';

const COPY = {
  behind: {
    label: LABEL_BEHIND,
    title: 'New content is available',
    lines: [
      "A new day's challenges are available.",
      'Pull the new code from the remote git repository to see the new content.',
    ],
  },
  current: {
    label: LABEL_CURRENT,
    title: 'This copy is current',
    lines: [
      'This copy is current.',
    ],
  },
};

/** Behind check. Off, not a repo, or current all stay visible as Up to date.
 * A missing object is a dead read, not "off". */
export function noticeKind(status) {
  if (!status || typeof status !== 'object') return 'keep';
  if (status.enabled === false || status.isRepo === false) return 'current';
  const behind = Number(status.behind);
  const available = status.updateAvailable === true
    || (Number.isFinite(behind) && behind > 0);
  if (available) return 'behind';
  return 'current';
}

function fill(el, text) {
  if (el) el.textContent = text;
}

export function paintNotice(btn, panel, status, doc) {
  const kind = noticeKind(status);
  if (kind === 'keep' || !btn) return kind;
  const document_ = doc || (btn.ownerDocument || document);
  const text = btn.querySelector('.bn-text');
  const title = panel && panel.querySelector('.bn-title');
  const body = panel && panel.querySelector('.bn-body');
  if (kind === 'clear') kind = 'current';
  const copy = COPY[kind];
  fill(text, copy.label);
  btn.dataset.state = kind;
  btn.hidden = false;
  if (panel && title && body) {
    fill(title, copy.title);
    body.replaceChildren();
    for (const line of copy.lines) {
      const p = document_.createElement('p');
      p.textContent = line;
      body.appendChild(p);
    }
    panel.dataset.state = kind;
  }
  return kind;
}

export function bootBranchNotice(doc, hooks) {
  const document_ = doc || document;
  const btn = document_.getElementById('branchNotice');
  const panel = document_.getElementById('branchPanel');
  const ripple = document_.getElementById('branchRipple');
  if (!btn || !panel) return { refresh: async () => {} };

  const view = document_.defaultView || window;
  const onRings = hooks && hooks.onRings;
  let inflight = false;
  let last = null;

  function fab() {
    return document_.getElementById('personFab');
  }

  /* Rings stay on the button while it slides. A move does not hide them
     or clear the behind mark. */
  let placedLeft = NaN;
  let placedTop = NaN;
  let following = false;

  function placeRipple() {
    if (!ripple) return;
    const host = fab() || btn;
    if (!host || typeof host.getBoundingClientRect !== 'function') return;
    const r = host.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const size = ripple.offsetWidth || 220;
    const left = r.left + r.width / 2 - size / 2;
    const top = r.top + r.height / 2 - size / 2;
    if (Math.abs(left - placedLeft) < 0.5 && Math.abs(top - placedTop) < 0.5) return;
    placedLeft = left;
    placedTop = top;
    ripple.style.right = 'auto';
    ripple.style.bottom = 'auto';
    ripple.style.left = left + 'px';
    ripple.style.top = top + 'px';
  }

  function followRipple() {
    if (!following) return;
    if (!ripple || ripple.hidden) {
      following = false;
      return;
    }
    placeRipple();
    if (typeof view.requestAnimationFrame === 'function') {
      view.requestAnimationFrame(followRipple);
    } else {
      following = false;
    }
  }

  function ensureFollow() {
    if (following || !ripple || ripple.hidden) return;
    following = true;
    if (typeof view.requestAnimationFrame === 'function') {
      view.requestAnimationFrame(followRipple);
    } else {
      placeRipple();
      following = false;
    }
  }

  function syncRipple(kind) {
    const mark = fab();
    if (kind !== 'behind') {
      if (ripple) ripple.hidden = true;
      if (mark) mark.classList.remove('bn-glow');
      return;
    }
    if (ripple) ripple.hidden = false;
    if (mark) mark.classList.add('bn-glow');
    ensureFollow();
    placeRipple();
  }

  function closePanel(restoreFocus) {
    panel.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
    if (restoreFocus) {
      try { btn.focus(); } catch (e) { /* ignore */ }
    }
  }

  function openPanel() {
    const status = last || { enabled: false };
    paintNotice(btn, panel, status, document_);
    panel.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    const close = panel.querySelector('.bn-x');
    try { (close || panel).focus(); } catch (e) { /* ignore */ }
  }

  function paint(status) {
    const kind = noticeKind(status);
    if (kind === 'keep') return;
    last = status;
    const shown = paintNotice(btn, panel, status, document_);
    if (shown === 'clear') closePanel(false);
    syncRipple(shown);
  }

  async function refresh() {
    if (inflight) return;
    if (document_.visibilityState === 'hidden') return;
    inflight = true;
    try {
      const r = await view.fetch('/api/updates', { cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      paint(data);
    } catch (e) {
      /* leave the last status; a missed poll is not "up to date" */
    } finally {
      inflight = false;
    }
  }

  function onShow() {
    if (document_.visibilityState === 'hidden') return;
    refresh();
  }

  btn.addEventListener('click', (e) => {
    e.preventDefault();
    /* Does not mark the copy current and does not hide the item. */
    if (panel.hidden) openPanel();
    else closePanel(true);
  });
  if (ripple) ripple.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    /* Rings stay while the copy is behind. Opening the menu shows the item. */
    if (onRings) onRings();
    else view.dispatchEvent(new CustomEvent('cockpit-person-open'));
  });
  view.addEventListener('resize', () => {
    placeRipple();
    ensureFollow();
  });
  if (ripple && !ripple.hidden) ensureFollow();
  const close = panel.querySelector('.bn-x');
  if (close) close.addEventListener('click', () => closePanel(true));
  view.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || panel.hidden) return;
    e.preventDefault();
    e.stopPropagation();
    closePanel(true);
  });
  document_.addEventListener('click', (e) => {
    if (panel.hidden) return;
    const t = e.target;
    if (t && (panel.contains(t) || btn.contains(t))) return;
    closePanel(false);
  });

  refresh();
  const timer = view.setInterval(refresh, POLL_MS);
  view.addEventListener('visibilitychange', onShow);
  view.addEventListener('pageshow', onShow);
  view.addEventListener('pagehide', () => view.clearInterval(timer));

  return { refresh };
}
