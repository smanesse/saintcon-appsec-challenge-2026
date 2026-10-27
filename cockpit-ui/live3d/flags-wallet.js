/* Captured A.L.I.E.N. flag wallet.
 *
 * A menu-bar button (#bFlags) opens a panel (#flagsPanel) listing every static
 * reward flag the signed-in contestant has earned by boarding a ship. The data
 * comes from the bridge `GET /api/flags`, which proxies the harness flags API
 * and additively persists what it returns, so the wallet survives reloads and a
 * briefly-unreachable harness (such a stale read is flagged in the note).
 *
 * The same flags also surface inline on a successful alien submission
 * (alien-submit.js); this is the always-available collected view. A captured-
 * count badge rides on the button.
 *
 * NO innerHTML: every string reaches the page through textContent.
 */
import { getFlags } from './api.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

export function bootFlagsWallet(doc) {
  const document_ = doc || document;
  const btn = document_.getElementById('bFlags');
  const panel = document_.getElementById('flagsPanel');
  if (!btn || !panel) {
    return { refresh() {}, open() {}, close() {}, isOpen: () => false };
  }
  const view = document_.defaultView || window;
  const countBadge = btn.querySelector('[data-flags-count]');
  const note = panel.querySelector('[data-flags-note]');
  const list = panel.querySelector('[data-flags-list]');
  const closeBtn = panel.querySelector('[data-flags-close]');

  let generation = 0;

  function setCount(n) {
    if (!countBadge) return;
    countBadge.textContent = String(n);
    countBadge.hidden = n <= 0;
  }

  function render(result) {
    const flags = (result && Array.isArray(result.flags)) ? result.flags : [];
    setCount(flags.length);
    if (list) list.replaceChildren();
    if (!flags.length) {
      if (note) {
        note.textContent = result && result.ok === false && result.loggedIn === false
          ? 'Sign in to see the flags you have captured.'
          : 'No flags captured yet. Board a ship to earn one.';
        note.removeAttribute('data-stale');
      }
      return;
    }
    if (note) {
      if (result && result.stale) {
        note.textContent = 'Harness unreachable — showing the flags kept on this console.';
        note.setAttribute('data-stale', 'yes');
      } else {
        note.textContent = '';
        note.removeAttribute('data-stale');
      }
    }
    if (!list) return;
    for (const f of flags) {
      if (!f || typeof f !== 'object' || !f.flag) continue;
      const item = el('li', 'fp-item');
      const label = (f.name != null && f.name !== '') ? String(f.name)
        : (f.challenge_path != null ? String(f.challenge_path)
          : (f.alien != null ? String(f.alien) : 'Ship'));
      item.appendChild(el('span', 'fp-ship', label));
      item.appendChild(el('code', 'fp-flag', String(f.flag)));
      list.appendChild(item);
    }
  }

  async function refresh() {
    const mine = ++generation;
    let result;
    try { result = await getFlags({ cache: 'no-store' }); }
    catch (_) { result = { ok: false, flags: [], stale: true }; }
    if (mine !== generation) return;   // a newer refresh superseded this one
    render(result);
  }

  function isOpen() {
    return btn.getAttribute('aria-expanded') === 'true';
  }

  function open() {
    panel.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    refresh();
  }

  function close() {
    panel.hidden = true;
    btn.setAttribute('aria-expanded', 'false');
  }

  function toggle() {
    if (isOpen()) close();
    else open();
  }

  btn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggle();
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      close();
    });
  }

  view.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen()) close();
  });

  // A boarded result (alien-submit), any submission change, a fresh sign-in, or
  // the menu opening can all change the earned set: keep the wallet current.
  document_.addEventListener('flagschange', () => refresh());
  document_.addEventListener('submissionchange', () => refresh());
  view.addEventListener('focus', () => refresh());
  view.addEventListener('cockpit-person-open', () => refresh());

  refresh();
  return { refresh, open, close, isOpen };
}
