/* SAINTCON 2026 — first-visit submit signs.
 *
 * After the tutorial card closes, two signs point at the only places a
 * submission goes: the grading port for module fixes, and the weapons
 * console (PKT) for alien exploits. They are a first visit, not a hint
 * that returns. Dismissal writes the same flag the next visit reads.
 *
 * They stay off the main cockpit's close-up, the standings board, a
 * dive, and the grading dialog. They are not shown while the tutorial
 * card is open — decideSubmitSigns is the gate, and the stylesheet
 * hides #submitSigns for the same card.
 *
 * No innerHTML: every string reaches the page through textContent.
 */

export const SUBMIT_SIGNS_KEY = 'cockpit.submit-signs.seen';

export const SUBMIT_SIGN_COPY = {
  grade: 'Submit Module Fixes Here',
  pkt: 'Submit Exploits Here',
};

const MARGIN = 12;
const GAP = 40;
const HEAD = 36;

export function readSubmitSignsSeen(storage) {
  try { return !!(storage && storage.getItem(SUBMIT_SIGNS_KEY) === '1'); }
  catch (e) { return false; }
}

export function writeSubmitSignsSeen(storage) {
  try {
    if (storage) storage.setItem(SUBMIT_SIGNS_KEY, '1');
    return true;
  } catch (e) { return false; }
}

/* show is the only path that paints. remember is written only once a
 * sign is actually on the main cockpit, so a tutorial that is still
 * open, or a close-up, does not consume the first visit. */
export function decideSubmitSigns(s) {
  if (!s || s.dismissed) return { show: false, remember: false };
  if (s.remembered && !s.shownThisVisit) return { show: false, remember: false };
  if (s.tutorialOpen) return { show: false, remember: false };
  if (!s.onMainCockpit) return { show: false, remember: false };
  return { show: true, remember: !s.remembered };
}

export function placeCallout(sign, target, bounds, prefer) {
  const sw = sign.w, sh = sign.h;
  const order = candidates(prefer, sign, target, GAP);
  for (const c of order) {
    const box = { x: c.x, y: c.y, w: sw, h: sh };
    if (!inside(box, bounds, MARGIN)) continue;
    if (overlaps(box, target, GAP)) continue;
    return box;
  }
  const first = order[0];
  const box = shoveOut({
    x: clamp(first.x, MARGIN, Math.max(MARGIN, bounds.w - sw - MARGIN)),
    y: clamp(first.y, MARGIN, Math.max(MARGIN, bounds.h - sh - MARGIN)),
    w: sw,
    h: sh,
  }, target, bounds);
  return box;
}

export function arrowGeometry(from, to) {
  const dx = to.x - from.x, dy = to.y - from.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const head = Math.min(HEAD, Math.max(18, len * 0.42));
  const wing = head * 0.62;
  const base = { x: to.x - ux * head, y: to.y - uy * head };
  const px = -uy, py = ux;
  return {
    from, to, shaftEnd: base,
    head: [
      { x: to.x, y: to.y },
      { x: base.x + px * wing, y: base.y + py * wing },
      { x: base.x - px * wing, y: base.y - py * wing },
    ],
  };
}

export function edgePoint(box, toward) {
  const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  const dx = toward.x - cx, dy = toward.y - cy;
  if (dx === 0 && dy === 0) return { x: cx, y: cy };
  const sx = dx !== 0 ? (box.w / 2) / Math.abs(dx) : Infinity;
  const sy = dy !== 0 ? (box.h / 2) / Math.abs(dy) : Infinity;
  const s = Math.min(sx, sy);
  return { x: cx + dx * s, y: cy + dy * s };
}

export function aimPoint(target, from) {
  const center = { x: target.x + target.w / 2, y: target.y + target.h / 2 };
  const edge = edgePoint(target, from);
  const dx = center.x - edge.x, dy = center.y - edge.y;
  const len = Math.hypot(dx, dy) || 1;
  const inset = Math.min(14, len);
  return { x: edge.x + (dx / len) * inset, y: edge.y + (dy / len) * inset };
}

export function glyphFor(from, to) {
  const dx = to.x - from.x, dy = to.y - from.y;
  const ax = Math.abs(dx), ay = Math.abs(dy);
  if (ax < 8 && ay < 8) return '→';
  if (ax > ay * 1.6) return dx > 0 ? '→' : '←';
  if (ay > ax * 1.6) return dy > 0 ? '↓' : '↑';
  if (dx > 0 && dy > 0) return '↘';
  if (dx < 0 && dy > 0) return '↙';
  if (dx > 0) return '↗';
  return '↖';
}

function candidates(prefer, sign, target, gap) {
  const sw = sign.w, sh = sign.h;
  const left = { x: target.x - gap - sw, y: target.y + target.h / 2 - sh / 2 };
  const right = { x: target.x + target.w + gap, y: target.y + target.h / 2 - sh / 2 };
  const above = { x: target.x + target.w / 2 - sw / 2, y: target.y - gap - sh };
  const below = { x: target.x + target.w / 2 - sw / 2, y: target.y + target.h + gap };
  const aboveLeft = { x: target.x + target.w - sw, y: target.y - gap - sh };
  const table = {
    left: [left, above, below, right],
    above: [above, left, right, below],
    'above-left': [aboveLeft, above, left, right, below],
  };
  return table[prefer] || table.left;
}

function inside(box, bounds, margin) {
  return box.x >= margin && box.y >= margin
    && box.x + box.w <= bounds.w - margin
    && box.y + box.h <= bounds.h - margin;
}

function overlaps(a, b, gap) {
  return !(a.x + a.w + gap <= b.x || b.x + b.w + gap <= a.x
    || a.y + a.h + gap <= b.y || b.y + b.h + gap <= a.y);
}

function shoveOut(box, target, bounds) {
  const next = { x: box.x, y: box.y, w: box.w, h: box.h };
  if (!overlaps(next, target, 8)) return next;
  const cx = target.x + target.w / 2, cy = target.y + target.h / 2;
  const sx = next.x + next.w / 2, sy = next.y + next.h / 2;
  if (Math.abs(sx - cx) >= Math.abs(sy - cy)) {
    next.x = sx < cx ? target.x - GAP - next.w : target.x + target.w + GAP;
  } else {
    next.y = sy < cy ? target.y - GAP - next.h : target.y + target.h + GAP;
  }
  next.x = clamp(next.x, MARGIN, Math.max(MARGIN, bounds.w - next.w - MARGIN));
  next.y = clamp(next.y, MARGIN, Math.max(MARGIN, bounds.h - next.h - MARGIN));
  return next;
}

function clamp(n, lo, hi) {
  if (hi < lo) return lo;
  return Math.max(lo, Math.min(hi, n));
}

function usable(rect) {
  return !!(rect && rect.width > 8 && rect.height > 8);
}

export function mountSubmitSigns(o) {
  const doc = o.doc;
  const view = o.view || doc.defaultView || globalThis;
  const storage = o.storage;
  const parent = o.parent || doc.body;
  const NS = 'http://www.w3.org/2000/svg';

  const root = doc.createElement('div');
  root.id = 'submitSigns';
  root.hidden = true;
  root.setAttribute('role', 'region');
  root.setAttribute('aria-label', 'Where to submit');

  const live = doc.createElement('p');
  live.className = 'ss-live';
  live.setAttribute('aria-live', 'polite');

  const svg = doc.createElementNS(NS, 'svg');
  svg.setAttribute('class', 'ss-arrows');
  svg.setAttribute('aria-hidden', 'true');

  const signs = {
    pkt: makeSign(doc, 'pkt', SUBMIT_SIGN_COPY.pkt),
    grade: makeSign(doc, 'grade', SUBMIT_SIGN_COPY.grade),
  };
  root.append(live, svg, signs.pkt, signs.grade);
  parent.append(root);

  let shownThisVisit = false;
  let dismissed = false;
  let announced = false;

  function dismiss() {
    dismissed = true;
    writeSubmitSignsSeen(storage);
    hide();
  }
  for (const sign of Object.values(signs)) {
    sign.querySelector('button').addEventListener('click', dismiss);
  }

  function hide() {
    root.hidden = true;
    const active = doc.activeElement;
    if (active && root.contains(active) && active.blur) {
      try { active.blur(); } catch (e) { /* ignore */ }
    }
  }

  function localRect(rect) {
    const host = root.getBoundingClientRect();
    return {
      x: rect.left - host.left,
      y: rect.top - host.top,
      w: rect.width,
      h: rect.height,
    };
  }

  function layout() {
    const targets = o.targets ? o.targets() : {};
    const host = root.getBoundingClientRect();
    const bounds = { w: host.width, h: host.height };
    if (!(bounds.w > 0) || !(bounds.h > 0)) return false;
    svg.setAttribute('viewBox', '0 0 ' + bounds.w + ' ' + bounds.h);
    svg.setAttribute('width', String(bounds.w));
    svg.setAttribute('height', String(bounds.h));
    svg.replaceChildren();
    let any = false;
    const prefer = { pkt: 'left', grade: 'above-left' };
    for (const key of ['pkt', 'grade']) {
      const sign = signs[key];
      const raw = targets[key];
      if (!usable(raw)) {
        sign.hidden = true;
        continue;
      }
      sign.hidden = false;
      const target = localRect(raw);
      const box = placeCallout(
        { w: sign.offsetWidth || 320, h: sign.offsetHeight || 148 },
        target, bounds, prefer[key],
      );
      sign.style.left = box.x + 'px';
      sign.style.top = box.y + 'px';
      const from = edgePoint(box, {
        x: target.x + target.w / 2,
        y: target.y + target.h / 2,
      });
      const to = aimPoint(target, { x: box.x + box.w / 2, y: box.y + box.h / 2 });
      sign.querySelector('.ss-glyph').textContent = glyphFor(from, to);
      paintArrow(doc, svg, NS, from, to);
      any = true;
    }
    return any;
  }

  function sync() {
    const decision = decideSubmitSigns({
      remembered: readSubmitSignsSeen(storage),
      dismissed,
      shownThisVisit,
      tutorialOpen: !!o.tutorialOpen(),
      onMainCockpit: !!o.onMainCockpit(),
    });
    if (!decision.show) {
      hide();
      return;
    }
    root.hidden = false;
    if (!layout()) {
      hide();
      return;
    }
    if (decision.remember) writeSubmitSignsSeen(storage);
    shownThisVisit = true;
    if (!announced) {
      announced = true;
      live.textContent = 'Two signs are on the cockpit. '
        + SUBMIT_SIGN_COPY.grade + ' points at the grading port. '
        + SUBMIT_SIGN_COPY.pkt + ' points at the weapons console.';
    }
  }

  const poke = () => {
    const run = () => sync();
    if (typeof view.queueMicrotask === 'function') view.queueMicrotask(run);
    else if (view.requestAnimationFrame) view.requestAnimationFrame(run);
    else run();
  };
  const watch = (node, filter) => {
    if (!node || typeof view.MutationObserver !== 'function') return;
    const obs = new view.MutationObserver(poke);
    obs.observe(node, { attributes: true, attributeFilter: filter });
  };
  if (o.watch) {
    for (const w of o.watch) watch(w.node, w.filter);
  }
  if (view.addEventListener) view.addEventListener('resize', sync);
  sync();
  if (view.requestAnimationFrame) view.requestAnimationFrame(sync);

  return { sync, dismiss, root };
}

function makeSign(doc, id, text) {
  const sign = doc.createElement('div');
  sign.className = 'ss-sign';
  sign.dataset.sign = id;
  sign.hidden = true;
  const row = doc.createElement('div');
  row.className = 'ss-row';
  const label = doc.createElement('p');
  label.className = 'ss-label';
  label.textContent = text;
  const glyph = doc.createElement('span');
  glyph.className = 'ss-glyph';
  glyph.setAttribute('aria-hidden', 'true');
  glyph.textContent = '→';
  row.append(label, glyph);
  const btn = doc.createElement('button');
  btn.type = 'button';
  btn.className = 'ss-dismiss';
  btn.textContent = 'Dismiss';
  btn.setAttribute('aria-label', 'Dismiss submit signs');
  sign.append(row, btn);
  return sign;
}

function paintArrow(doc, svg, NS, from, to) {
  const g = arrowGeometry(from, to);
  svg.append(
    line(doc, NS, from, g.shaftEnd, 22, '#111'),
    line(doc, NS, from, g.shaftEnd, 12, '#ffe14a'),
    polygon(doc, NS, g.head),
  );
}

function line(doc, NS, a, b, width, color) {
  const el = doc.createElementNS(NS, 'line');
  el.setAttribute('x1', String(a.x));
  el.setAttribute('y1', String(a.y));
  el.setAttribute('x2', String(b.x));
  el.setAttribute('y2', String(b.y));
  el.setAttribute('stroke', color);
  el.setAttribute('stroke-width', String(width));
  el.setAttribute('stroke-linecap', 'round');
  return el;
}

function polygon(doc, NS, points) {
  const el = doc.createElementNS(NS, 'polygon');
  el.setAttribute('points', points.map(p => p.x + ',' + p.y).join(' '));
  el.setAttribute('fill', '#ffe14a');
  el.setAttribute('stroke', '#111');
  el.setAttribute('stroke-width', '4');
  el.setAttribute('stroke-linejoin', 'round');
  return el;
}
