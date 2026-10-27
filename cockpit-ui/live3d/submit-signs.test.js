import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  SUBMIT_SIGN_COPY, SUBMIT_SIGNS_KEY, aimPoint, arrowGeometry,
  decideSubmitSigns, edgePoint, glyphFor, mountSubmitSigns, placeCallout,
} from './submit-signs.js';

const openTutorial = {
  remembered: false,
  dismissed: false,
  shownThisVisit: false,
  tutorialOpen: true,
  onMainCockpit: true,
};

test('signs stay hidden while the tutorial card is open', () => {
  const waiting = decideSubmitSigns(openTutorial);
  assert.equal(waiting.show, false);
  assert.equal(waiting.remember, false);
});

test('signs appear after the tutorial closes on the main cockpit', () => {
  const waiting = decideSubmitSigns(openTutorial);
  assert.equal(waiting.show, false);
  const after = decideSubmitSigns({ ...openTutorial, tutorialOpen: false });
  assert.equal(after.show, true);
  assert.equal(after.remember, true);
});

test('closing the tutorial over a module close-up does not show or remember', () => {
  const d = decideSubmitSigns({
    ...openTutorial, tutorialOpen: false, onMainCockpit: false,
  });
  assert.equal(d.show, false);
  assert.equal(d.remember, false);
});

test('a later visit does not show the signs', () => {
  const d = decideSubmitSigns({
    remembered: true, dismissed: false, shownThisVisit: false,
    tutorialOpen: false, onMainCockpit: true,
  });
  assert.equal(d.show, false);
});

test('the same visit shows them again after a close-up until dismissed', () => {
  const away = decideSubmitSigns({
    remembered: true, dismissed: false, shownThisVisit: true,
    tutorialOpen: false, onMainCockpit: false,
  });
  const back = decideSubmitSigns({ ...away, onMainCockpit: true });
  assert.equal(away.show, false);
  assert.equal(back.show, true);
  const gone = decideSubmitSigns({ ...back, dismissed: true });
  assert.equal(gone.show, false);
});

test('reopening the tutorial hides signs that are already up', () => {
  const d = decideSubmitSigns({
    remembered: true, dismissed: false, shownThisVisit: true,
    tutorialOpen: true, onMainCockpit: true,
  });
  assert.equal(d.show, false);
});

test('stylesheet hides the signs while the tutorial card is open', () => {
  const css = readFileSync(new URL('./submit-signs.css', import.meta.url), 'utf8');
  assert.match(css, /body:has\(#tutorialCard:not\(\[hidden\]\)\) #submitSigns/);
  assert.match(css, /body\.closeup #submitSigns/);
});

test('copy names the two stations and not the other way around', () => {
  assert.equal(SUBMIT_SIGN_COPY.grade, 'Submit Module Fixes Here');
  assert.equal(SUBMIT_SIGN_COPY.pkt, 'Submit Exploits Here');
});

test('the grade callout sits off the port and the arrow lands on it', () => {
  const target = { x: 980, y: 520, w: 140, h: 110 };
  const box = placeCallout({ w: 300, h: 120 }, target, { w: 1200, h: 680 }, 'above-left');
  assert.equal(overlaps(box, target), false);
  assert.ok(box.y + box.h <= target.y);
  const from = edgePoint(box, { x: target.x + target.w / 2, y: target.y + target.h / 2 });
  const to = aimPoint(target, { x: box.x + box.w / 2, y: box.y + box.h / 2 });
  assert.ok(to.x >= target.x && to.x <= target.x + target.w);
  assert.ok(to.y >= target.y && to.y <= target.y + target.h);
  const arrow = arrowGeometry(from, to);
  assert.equal(arrow.to.x, to.x);
  assert.equal(arrow.to.y, to.y);
  assert.equal(glyphFor(from, to), '↓');
});

test('the weapons callout sits off PKT and points at it', () => {
  const target = { x: 500, y: 280, w: 272, h: 178 };
  const box = placeCallout({ w: 300, h: 120 }, target, { w: 1280, h: 682 }, 'left');
  assert.equal(overlaps(box, target), false);
  assert.ok(box.x + box.w <= target.x);
  const from = edgePoint(box, { x: target.x + 10, y: target.y + target.h / 2 });
  const to = aimPoint(target, { x: box.x + box.w / 2, y: box.y + box.h / 2 });
  assert.equal(glyphFor(from, to), '→');
  assert.ok(to.x < target.x + target.w / 2);
});

test('mounted signs stay hidden until the tutorial card closes', () => {
  let tutorialOpen = true;
  const storage = memStorage();
  const first = mountSubmitSigns(mountOpts(storage, () => tutorialOpen));
  assert.equal(first.root.hidden, true);
  assert.equal(storage.getItem(SUBMIT_SIGNS_KEY), null);
  const labels = first.root.querySelectorAll('.ss-label').map(n => n.textContent);
  assert.deepEqual(labels, [SUBMIT_SIGN_COPY.pkt, SUBMIT_SIGN_COPY.grade]);

  tutorialOpen = false;
  first.sync();
  assert.equal(first.root.hidden, false);
  assert.equal(storage.getItem(SUBMIT_SIGNS_KEY), '1');
  assert.equal(first.root.querySelectorAll('.ss-sign').some(n => n.hidden), false);

  tutorialOpen = true;
  first.sync();
  assert.equal(first.root.hidden, true);

  const later = mountSubmitSigns(mountOpts(storage, () => false));
  assert.equal(later.root.hidden, true);
});

function memStorage() {
  const m = new Map();
  return {
    getItem: k => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
  };
}

function mountOpts(storage, tutorialOpen) {
  return {
    doc: fakeDoc(),
    view: { queueMicrotask: fn => fn() },
    storage,
    parent: undefined,
    tutorialOpen,
    onMainCockpit: () => true,
    targets: () => ({
      grade: { left: 900, top: 480, width: 120, height: 90 },
      pkt: { left: 420, top: 240, width: 200, height: 140 },
    }),
  };
}

function fakeDoc() {
  function el(tag) {
    const node = {
      tag, hidden: false, children: [], attrs: {}, style: {}, dataset: {},
      className: '', textContent: '', parent: null,
      setAttribute(k, v) { this.attrs[k] = String(v); },
      getAttribute(k) { return this.attrs[k]; },
      append(...kids) {
        for (const kid of kids) { kid.parent = this; this.children.push(kid); }
      },
      replaceChildren() { this.children = []; },
      addEventListener() {},
      querySelector: sel => find(node, sel),
      querySelectorAll: sel => {
        const out = [];
        walk(node, sel, out);
        return out;
      },
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 640 }),
      contains(n) {
        let p = n;
        while (p) { if (p === node) return true; p = p.parent; }
        return false;
      },
      blur() {},
    };
    Object.defineProperty(node, 'offsetWidth', { get() { return 280; } });
    Object.defineProperty(node, 'offsetHeight', { get() { return 110; } });
    return node;
  }
  function match(node, sel) {
    if (sel === 'button') return node.tag === 'button';
    if (sel === '.ss-glyph') return node.className === 'ss-glyph';
    if (sel === '.ss-label') return node.className === 'ss-label';
    if (sel === '.ss-sign') return node.className === 'ss-sign';
    return false;
  }
  function find(node, sel) {
    for (const kid of node.children) {
      if (match(kid, sel)) return kid;
      const inner = find(kid, sel);
      if (inner) return inner;
    }
    return null;
  }
  function walk(node, sel, out) {
    for (const kid of node.children) {
      if (match(kid, sel)) out.push(kid);
      walk(kid, sel, out);
    }
  }
  const body = el('body');
  return { body, activeElement: null, createElement: el, createElementNS: (_ns, tag) => el(tag) };
}

function overlaps(a, b) {
  return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
}
