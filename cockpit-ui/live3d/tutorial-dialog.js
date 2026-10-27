/* One tutorial dialog. The fleet Tutorial and every module guide mount this.
 * Content and dismissal stay with the caller. This file owns painting,
 * paging, the larger picture, focus, and the rule that only one dialog is open.
 * Strings are assigned with textContent.
 */

const registry = new Set();

function docOf(card) {
  return card.ownerDocument || globalThis.document;
}

function activeOf(doc) {
  try { return doc.activeElement || null; } catch (e) { return null; }
}

function contains(card, node) {
  if (!node || typeof card.contains !== 'function') return false;
  try { return card.contains(node); } catch (e) { return false; }
}

function stopKey(e) {
  if (e && typeof e.preventDefault === 'function') e.preventDefault();
  if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
}

/* Drawn samples, not a photo. Rings only when the sample asks for them.
 * A performance sample is a picture of the person button and the settings
 * dialog. It has no ids the real dialog reads, and it does not write settings.
 * cockpit.tutorial.seen is not touched here. */
const PERSON_NS = 'http://www.w3.org/2000/svg';
const PERSON_HEAD = 'M8.6 12.4C8.6 6.8 11.8 2.6 16 2.6s7.4 4.2 7.4 9.8V15c0 1.8-1.5 3.2-3.4 3.2h-8c-1.9 0-3.4-1.4-3.4-3.2v-2.6zM11 9.4h10c.7 0 1.3.9 1.3 2.1v1.6c0 1.1-.6 1.9-1.3 1.9H11c-.7 0-1.3-.8-1.3-1.9v-1.6c0-1.2.6-2.1 1.3-2.1z';
const PERSON_BODY = 'M7.2 29.5c.55-5.1 4-8 8.8-8s8.25 2.9 8.8 8c.08.6-.38 1.1-.98 1.1H8.18c-.6 0-1.06-.5-.98-1.1z';

function personIcon(doc) {
  const svg = doc.createElementNS(PERSON_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 32 32');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const cog = doc.createElementNS(PERSON_NS, 'path');
  cog.setAttribute('fill', 'currentColor');
  cog.setAttribute('fill-rule', 'evenodd');
  cog.setAttribute('d', PERSON_HEAD);
  const body = doc.createElementNS(PERSON_NS, 'path');
  body.setAttribute('fill', 'currentColor');
  body.setAttribute('d', PERSON_BODY);
  svg.appendChild(cog);
  svg.appendChild(body);
  return svg;
}

function paintPerson(doc, sample) {
  const wrap = doc.createElement('div');
  wrap.className = 'td-sample td-sample-person';
  const mark = doc.createElement('div');
  mark.className = 'td-person-mark';
  if (sample && sample.rings) {
    const rings = doc.createElement('span');
    rings.className = 'td-sample-rings';
    rings.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < 3; i++) {
      const ring = doc.createElement('span');
      ring.className = 'td-sample-ring';
      rings.appendChild(ring);
    }
    mark.appendChild(rings);
  }
  const btn = doc.createElement('span');
  btn.className = 'td-person-btn';
  btn.appendChild(personIcon(doc));
  mark.appendChild(btn);
  wrap.appendChild(mark);
  const menu = doc.createElement('div');
  menu.className = 'td-person-menu';
  const item = doc.createElement('span');
  item.className = 'td-person-item';
  if (sample && sample.state) item.setAttribute('data-state', sample.state);
  item.textContent = sample && sample.label ? String(sample.label) : '';
  menu.appendChild(item);
  wrap.appendChild(menu);
  return wrap;
}

function paintPerformance(doc) {
  const wrap = doc.createElement('div');
  wrap.className = 'td-sample td-sample-perf';
  const mark = doc.createElement('div');
  mark.className = 'td-person-mark';
  const opener = doc.createElement('span');
  opener.className = 'td-person-btn';
  opener.appendChild(personIcon(doc));
  mark.appendChild(opener);
  wrap.appendChild(mark);
  const menu = doc.createElement('div');
  menu.className = 'td-person-menu';
  const item = doc.createElement('span');
  item.className = 'td-person-item';
  item.textContent = 'Performance settings';
  menu.appendChild(item);
  wrap.appendChild(menu);
  const dialog = doc.createElement('div');
  dialog.className = 'td-perf-dialog';
  const head = doc.createElement('div');
  head.className = 'td-perf-head';
  const title = doc.createElement('div');
  title.className = 'td-perf-title';
  title.textContent = 'Performance';
  const close = doc.createElement('span');
  close.className = 'td-perf-x';
  close.textContent = 'Close';
  head.appendChild(title);
  head.appendChild(close);
  dialog.appendChild(head);
  for (const name of ['Dynamic stars', 'Pre-load modules on hover']) {
    const row = doc.createElement('div');
    row.className = 'td-perf-row';
    const label = doc.createElement('span');
    label.className = 'td-perf-name';
    label.textContent = name;
    const sw = doc.createElement('span');
    sw.className = 'td-perf-switch';
    sw.textContent = 'On';
    row.appendChild(label);
    row.appendChild(sw);
    dialog.appendChild(row);
  }
  wrap.appendChild(dialog);
  return wrap;
}

function paintSamples(doc, samples) {
  const stage = doc.createElement('div');
  stage.className = 'td-samples';
  for (const sample of samples) {
    if (sample && sample.kind === 'performance') {
      stage.appendChild(paintPerformance(doc));
      continue;
    }
    if (sample && sample.kind === 'person') {
      stage.appendChild(paintPerson(doc, sample));
      continue;
    }
    const wrap = doc.createElement('div');
    wrap.className = 'td-sample';
    if (sample && sample.rings) {
      const rings = doc.createElement('span');
      rings.className = 'td-sample-rings';
      rings.setAttribute('aria-hidden', 'true');
      for (let i = 0; i < 3; i++) {
        const ring = doc.createElement('span');
        ring.className = 'td-sample-ring';
        rings.appendChild(ring);
      }
      wrap.appendChild(rings);
    }
    const btn = doc.createElement('span');
    btn.className = 'td-sample-btn';
    if (sample && sample.state) btn.setAttribute('data-state', sample.state);
    const dot = doc.createElement('span');
    dot.className = 'td-sample-dot';
    dot.setAttribute('aria-hidden', 'true');
    const text = doc.createElement('span');
    text.textContent = sample && sample.label ? String(sample.label) : '';
    btn.appendChild(dot);
    btn.appendChild(text);
    wrap.appendChild(btn);
    stage.appendChild(wrap);
  }
  return stage;
}

export function mountTutorialDialog(o) {
  const card = o.card;
  const doc = docOf(card);
  const title = o.title;
  const body = o.body;
  const progress = o.progress || null;
  const prev = o.prev || null;
  const next = o.next || null;
  const done = o.done || null;
  const closeBtn = o.close || null;
  const shade = o.shade || null;
  const btn = o.btn || null;
  let token = null;
  let index = 0;
  let prevFocus = null;
  let shownImage = null;

  const cls = String(card.className || '');
  if (!cls.split(/\s+/).includes('td-dialog')) card.className = (cls + ' td-dialog').trim();
  if (shade) {
    const sc = String(shade.className || '');
    if (!sc.split(/\s+/).includes('td-shade')) shade.className = (sc + ' td-shade').trim();
  }
  card.setAttribute('data-tutorial-engine', 'shared');

  const zoom = doc.createElement('div');
  zoom.className = 'td-zoom';
  zoom.hidden = true;
  zoom.setAttribute('role', 'dialog');
  zoom.setAttribute('aria-label', 'Larger picture');
  const scroller = doc.createElement('div');
  scroller.className = 'td-zoom-scroll';
  const zoomImg = doc.createElement('img');
  zoomImg.alt = '';
  const zoomClose = doc.createElement('button');
  zoomClose.type = 'button';
  zoomClose.className = 'td-zoom-close';
  zoomClose.setAttribute('aria-label', 'Close larger picture');
  zoomClose.textContent = 'Close';
  scroller.appendChild(zoomImg);
  zoom.appendChild(scroller);
  zoom.appendChild(zoomClose);
  card.appendChild(zoom);

  const larger = doc.createElement('button');
  larger.type = 'button';
  larger.className = 'td-larger';
  larger.textContent = 'Larger';
  larger.setAttribute('aria-label', 'Show the picture larger');
  larger.hidden = true;
  const actions = (next && (next.parentElement || next.parent))
    || (prev && (prev.parentElement || prev.parent))
    || null;
  if (actions && typeof actions.insertBefore === 'function' && prev) actions.insertBefore(larger, prev);
  else if (actions && typeof actions.appendChild === 'function') actions.appendChild(larger);
  else card.appendChild(larger);

  function pagesOf(nextToken) {
    const list = o.pages(nextToken);
    return list && list.length ? list : null;
  }

  function focusPrimary() {
    const el = (next && !next.hidden) ? next : (done && !done.hidden ? done : closeBtn);
    try { if (el) el.focus(); } catch (e) { /* ignore */ }
  }

  function closeZoom() {
    zoom.hidden = true;
    if (typeof zoomImg.removeAttribute === 'function') zoomImg.removeAttribute('src');
    else zoomImg.src = '';
    zoomImg.alt = '';
  }

  function sizeZoom() {
    if (!zoomImg.naturalWidth || typeof scroller.getBoundingClientRect !== 'function') return;
    const pane = scroller.getBoundingClientRect();
    if (pane.width < 2 || pane.height < 2) return;
    const fit = Math.min(pane.width / zoomImg.naturalWidth, pane.height / zoomImg.naturalHeight);
    const scale = fit < 1 ? 1 : fit;
    zoomImg.style.width = Math.round(zoomImg.naturalWidth * scale) + 'px';
    zoomImg.style.height = Math.round(zoomImg.naturalHeight * scale) + 'px';
  }

  function openZoom() {
    if (!shownImage) return;
    zoomImg.alt = shownImage.alt || '';
    zoomImg.src = shownImage.src;
    zoom.hidden = false;
    const finish = () => { sizeZoom(); try { zoomClose.focus(); } catch (e) { /* ignore */ } };
    if (zoomImg.complete && zoomImg.naturalWidth) finish();
    else zoomImg.addEventListener('load', finish, { once: true });
  }

  function fitShown() {
    const img = shownImage;
    if (!img || !img.naturalWidth) return;
    const fig = img.parentElement || img.parent;
    if (!fig || typeof fig.clientWidth !== 'number') return;
    const paneW = fig.clientWidth;
    const paneH = fig.clientHeight;
    if (paneW < 2 || paneH < 2) return;
    const scale = Math.min(paneW / img.naturalWidth, paneH / img.naturalHeight, 1);
    img.style.width = Math.round(img.naturalWidth * scale) + 'px';
    img.style.height = Math.round(img.naturalHeight * scale) + 'px';
  }

  function paint() {
    const list = pagesOf(token);
    if (!list) return;
    const page = list[index];
    title.textContent = o.heading(token, page, index, list);
    if (progress) {
      progress.replaceChildren();
      const text = o.progressText ? o.progressText(token, page, index, list) : '';
      if (text) {
        const label = doc.createElement('span');
        label.className = 'hp-count';
        label.textContent = text;
        progress.appendChild(label);
      }
    }
    body.replaceChildren();
    closeZoom();
    shownImage = null;
    const paras = Array.isArray(page.paragraphs) ? page.paragraphs : (page.body ? [page.body] : []);
    const hasSamples = Array.isArray(page.samples) && page.samples.length > 0;
    const copy = doc.createElement('div');
    copy.className = (page.image || hasSamples) ? 'td-copy' : 'td-copy td-copy-only';
    for (const para of paras) {
      const row = doc.createElement('p');
      row.textContent = para;
      copy.appendChild(row);
    }
    if (page.image) {
      const figure = doc.createElement('div');
      figure.className = 'td-figure';
      const img = doc.createElement('img');
      img.alt = page.alt || '';
      const err = doc.createElement('p');
      err.className = 'td-img-error';
      err.hidden = true;
      err.textContent = 'The picture did not load.';
      img.addEventListener('error', () => { err.hidden = false; });
      img.addEventListener('load', () => { err.hidden = true; fitShown(); });
      img.src = page.image;
      figure.appendChild(img);
      figure.appendChild(err);
      body.appendChild(figure);
      shownImage = img;
    } else if (hasSamples) {
      body.appendChild(paintSamples(doc, page.samples));
    }
    body.appendChild(copy);
    if (typeof copy.scrollTop === 'number') copy.scrollTop = 0;
    if (typeof body.scrollTop === 'number') body.scrollTop = 0;
    if (prev) prev.hidden = index === 0;
    const last = index >= list.length - 1;
    if (o.finishOnNext) {
      if (next) {
        next.hidden = false;
        next.textContent = last ? 'Close' : 'Next';
      }
    } else if (next) {
      next.hidden = last;
    }
    if (done) {
      done.hidden = false;
      if (!done.textContent) done.textContent = 'Done';
    }
    larger.hidden = !page.image;
    if (shownImage && shownImage.complete && shownImage.naturalWidth) fitShown();
  }

  function step(by) {
    const list = pagesOf(token);
    if (!list || (zoom && !zoom.hidden)) return;
    const n = index + by;
    if (n < 0 || n >= list.length) return;
    index = n;
    paint();
    fitShown();
    focusPrimary();
  }

  function isOpen() {
    return token != null && !card.hidden;
  }

  function close(dismissed) {
    if (token == null || card.hidden) {
      token = null;
      return false;
    }
    const closed = token;
    token = null;
    index = 0;
    closeZoom();
    const activeEl = activeOf(doc);
    const hadFocus = contains(card, activeEl);
    card.hidden = true;
    if (shade) shade.hidden = true;
    card.setAttribute('aria-modal', 'false');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    if (dismissed && o.onDismiss) o.onDismiss(closed);
    if (dismissed && (hadFocus || !activeEl || activeEl === doc.body)) {
      const back = prevFocus;
      prevFocus = null;
      const ok = back && back.isConnected !== false && back.offsetParent !== null;
      const target = ok ? back : btn;
      try { if (target) target.focus(); } catch (e) { /* ignore */ }
    }
    prevFocus = null;
    return true;
  }

  function open(nextToken) {
    const list = pagesOf(nextToken);
    if (!list) return false;
    if (token === nextToken && !card.hidden && o.reopen !== 'restart') {
      focusPrimary();
      return true;
    }
    for (const other of registry) {
      if (other !== api && other.isOpen()) other.suspend();
    }
    const activeEl = activeOf(doc);
    prevFocus = (activeEl && activeEl !== doc.body && !contains(card, activeEl)) ? activeEl : null;
    token = nextToken;
    index = 0;
    paint();
    card.hidden = false;
    if (shade) shade.hidden = false;
    card.setAttribute('aria-modal', 'true');
    if (btn) btn.setAttribute('aria-expanded', 'true');
    fitShown();
    focusPrimary();
    return true;
  }
  const view = doc.defaultView;
  if (view && typeof view.addEventListener === 'function') {
    view.addEventListener('resize', () => { if (isOpen()) fitShown(); });
  }

  function shown(el) {
    if (!el || el.hidden || el.disabled) return false;
    let n = el.parentElement || el.parent || null;
    while (n && n !== card) {
      if (n.hidden) return false;
      n = n.parentElement || n.parent || null;
    }
    return true;
  }
  function focusables() {
    if (!zoom.hidden) return [zoomClose];
    const known = [larger, prev, next, done, closeBtn].filter(Boolean);
    const list = typeof card.querySelectorAll === 'function'
      ? [...card.querySelectorAll('button')]
      : known;
    return list.filter(shown);
  }

  function onKey(e) {
    if (!e || card.hidden) return;
    if (e.key === 'Escape' && !zoom.hidden) {
      stopKey(e);
      closeZoom();
      try { larger.focus(); } catch (err) { /* ignore */ }
      return;
    }
    if (e.key === 'ArrowRight') { step(1); return; }
    if (e.key === 'ArrowLeft') { step(-1); return; }
    if (e.key !== 'Tab') return;
    const list = focusables();
    if (!list.length) return;
    const first = list[0];
    const last = list[list.length - 1];
    const activeEl = activeOf(doc);
    if (e.shiftKey && (activeEl === first || !contains(card, activeEl))) {
      stopKey(e);
      try { last.focus(); } catch (err) { /* ignore */ }
    } else if (!e.shiftKey && (activeEl === last || !contains(card, activeEl))) {
      stopKey(e);
      try { first.focus(); } catch (err) { /* ignore */ }
    }
  }

  if (prev) prev.addEventListener('click', () => step(-1));
  if (next) next.addEventListener('click', () => {
    const list = pagesOf(token);
    if (!list) return;
    if (index < list.length - 1) { step(1); return; }
    if (o.finishOnNext) close(true);
  });
  if (done) done.addEventListener('click', () => close(true));
  if (closeBtn) closeBtn.addEventListener('click', () => close(true));
  larger.addEventListener('click', openZoom);
  zoomClose.addEventListener('click', () => {
    closeZoom();
    try { larger.focus(); } catch (e) { /* ignore */ }
  });
  card.addEventListener('keydown', onKey);
  if (btn) btn.addEventListener('click', () => {
    if (isOpen()) close(true);
    else {
      const nextToken = o.tokenFromButton ? o.tokenFromButton() : o.defaultToken;
      if (nextToken) open(nextToken);
    }
  });

  const api = { open, close, suspend: () => close(false), isOpen, step };
  registry.add(api);
  return api;
}
