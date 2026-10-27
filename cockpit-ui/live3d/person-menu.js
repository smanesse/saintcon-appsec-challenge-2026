/* The person button replaces the bottom bar.
 *
 * It stays in a corner, including over a module close-up. A fleet tutorial
 * or module guide slides it to the bottom left, and the menu opens above
 * that corner. Opening the menu does not move the icon. The buttons
 * sit above it, and the name sits beside it inside the card. Closed,
 * only the icon shows. The slide does not close this menu.
 * Nothing here applies an update or writes cockpit.tutorial.seen.
 *
 * NO innerHTML. textContent only, and only for labels this file owns.
 */

export function bootPersonMenu(doc) {
  const document_ = doc || document;
  const fab = document_.getElementById('personFab');
  const menu = document_.getElementById('personMenu');
  if (!fab || !menu) {
    return { isOpen: () => false, open() {}, close() {}, toggle() {} };
  }
  const view = document_.defaultView || window;

  let motion = 0;

  function reduced() {
    return !!(view.matchMedia && view.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function isOpen() {
    return fab.getAttribute('aria-expanded') === 'true';
  }

  function closePanel() {
    const panel = document_.getElementById('branchPanel');
    const item = document_.getElementById('branchNotice');
    if (panel) panel.hidden = true;
    if (item) item.setAttribute('aria-expanded', 'false');
    // The flag wallet opens beside the menu like the branch panel; fold it away
    // when the menu closes.
    const flags = document_.getElementById('flagsPanel');
    const flagsBtn = document_.getElementById('bFlags');
    if (flags) flags.hidden = true;
    if (flagsBtn) flagsBtn.setAttribute('aria-expanded', 'false');
  }

  function hideNow(token) {
    if (token !== motion) return;
    if (fab.getAttribute('aria-expanded') === 'true') return;
    menu.hidden = true;
  }

  function close() {
    motion += 1;
    const token = motion;
    fab.setAttribute('aria-expanded', 'false');
    closePanel();
    if (menu.hidden) return;
    if (reduced()) {
      menu.setAttribute('data-grow', 'no');
      menu.setAttribute('data-shown', 'no');
      menu.hidden = true;
      return;
    }
    menu.setAttribute('data-shown', 'no');
    view.setTimeout(() => {
      if (token !== motion) return;
      menu.setAttribute('data-grow', 'no');
      const done = (e) => {
        if (e.target !== menu || e.propertyName !== 'transform') return;
        menu.removeEventListener('transitionend', done);
        hideNow(token);
      };
      menu.addEventListener('transitionend', done);
      view.setTimeout(() => hideNow(token), 420);
    }, 150);
  }

  function open() {
    motion += 1;
    const token = motion;
    menu.setAttribute('data-grow', reduced() ? 'yes' : 'no');
    menu.setAttribute('data-shown', reduced() ? 'yes' : 'no');
    menu.hidden = false;
    fab.setAttribute('aria-expanded', 'true');
    if (reduced()) return;
    menu.getBoundingClientRect();
    view.requestAnimationFrame(() => {
      if (token !== motion) return;
      menu.setAttribute('data-grow', 'yes');
      view.setTimeout(() => {
        if (token !== motion) return;
        menu.setAttribute('data-shown', 'yes');
      }, 180);
    });
  }

  function toggle() {
    if (isOpen()) close();
    else open();
  }

  fab.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggle();
  });

  for (const id of ['bTutorial', 'bPerf', 'gradeTell', 'bAuth', 'menuSubmit']) {
    const el = document_.getElementById(id);
    if (el) el.addEventListener('click', () => close());
  }

  document_.addEventListener('click', (e) => {
    if (!isOpen()) return;
    const t = e.target;
    if (!t) return;
    if (menu.contains(t) || fab.contains(t)) return;
    const crew = document_.getElementById('crew');
    if (crew && crew.contains(t)) return;
    const panel = document_.getElementById('branchPanel');
    const ripple = document_.getElementById('branchRipple');
    if (panel && panel.contains(t)) return;
    if (ripple && ripple.contains(t)) return;
    const flags = document_.getElementById('flagsPanel');
    if (flags && flags.contains(t)) return;
    close();
  });

  view.addEventListener('cockpit-person-open', () => open());

  return { isOpen, open, close, toggle };
}
