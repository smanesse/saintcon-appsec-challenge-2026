/* SAINTCON 2026 — coordinator link strip (offline / error / latency).
 *
 * One mount per Document (WeakMap).  Same-origin iframes share this ES
 * module instance; a module-level toast node would point at whichever
 * window mounted last.  Callers pass already-plain `message` strings.
 *
 * NO innerHTML.  createElement + textContent only.
 */

export const SLOW_MS = 800;

const mounts = new WeakMap();
const inflight = new WeakMap();

export function trackAbort(doc, controller) {
  if (!doc || !controller) return () => {};
  let set = inflight.get(doc);
  if (!set) {
    set = new Set();
    inflight.set(doc, set);
  }
  set.add(controller);
  return () => { set.delete(controller); };
}

export function abortInflight(doc) {
  const set = doc && inflight.get(doc);
  if (!set) return;
  for (const ac of set) {
    try { ac.abort(); } catch (e) { /* already aborted */ }
  }
  set.clear();
}

function paintStrip(el, event) {
  const level = event.level || 'warn';
  el.style.pointerEvents = 'none';
  el.style.maxWidth = '72rem';
  el.style.padding = '6px 10px';
  el.style.borderRadius = '3px';
  el.style.letterSpacing = '0.08em';
  el.style.font = '11px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace';
  if (level === 'crit') {
    el.style.background = '#2a0d0d';
    el.style.border = '1px solid #a33';
    el.style.color = '#ffb4b4';
  } else if (level === 'ok') {
    el.style.background = 'rgba(4,8,16,0.92)';
    el.style.border = '1px solid #3d6a96';
    el.style.color = '#d8e8fa';
  } else {
    el.style.background = 'rgba(4,8,16,0.92)';
    el.style.border = '1px solid #c79a2e';
    el.style.color = '#f2d67a';
  }
  el.textContent = event.message || '';
}

function fallbackHost(doc) {
  const el = doc.createElement('div');
  el.id = 'linkUx';
  el.style.position = 'fixed';
  el.style.left = '0';
  el.style.right = '0';
  el.style.bottom = '38px';
  el.style.zIndex = '25';
  el.style.pointerEvents = 'none';
  el.style.display = 'flex';
  el.style.justifyContent = 'center';
  el.style.padding = '0 12px 6px';
  (doc.body || doc.documentElement).appendChild(el);
  return el;
}

export function mountLinkUx({ host, doc = document } = {}) {
  const existing = mounts.get(doc);
  if (existing) return existing;

  let created = false;
  let root = host || doc.getElementById('linkUx');
  if (!root) {
    root = fallbackHost(doc);
    created = true;
  }

  const strip = doc.createElement('div');
  strip.setAttribute('role', 'status');
  strip.setAttribute('aria-live', 'polite');
  strip.style.display = 'none';
  root.appendChild(strip);

  let timer = null;
  let disposed = false;

  function clear() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    strip.style.display = 'none';
    strip.textContent = '';
  }

  function announce(event) {
    if (disposed || !event) return;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    paintStrip(strip, event);
    strip.style.display = '';
    if (!event.persist) {
      timer = setTimeout(clear, 3000);
    }
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    clear();
    abortInflight(doc);
    if (strip.parentNode) strip.parentNode.removeChild(strip);
    if (created && root.parentNode) root.parentNode.removeChild(root);
    const view = doc.defaultView;
    if (view) view.removeEventListener('pagehide', onHide);
    mounts.delete(doc);
  }

  function onHide() { dispose(); }

  const view = doc.defaultView;
  if (view) view.addEventListener('pagehide', onHide);

  const pageAc = new AbortController();
  if (view) {
    view.addEventListener('pagehide', () => {
      try { pageAc.abort(); } catch (e) { /* ignore */ }
    });
  }

  const api = { announce, clear, dispose, signal: pageAc.signal };
  mounts.set(doc, api);
  return api;
}

export function announce(event) {
  const doc = (event && event.doc) || (typeof document !== 'undefined' ? document : null);
  const mount = doc && mounts.get(doc);
  if (mount) mount.announce(event);
}
