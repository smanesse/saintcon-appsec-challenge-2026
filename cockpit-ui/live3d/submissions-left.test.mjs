import assert from 'node:assert/strict';
import test from 'node:test';
import * as counts from './submissions-left.js';

test('history, failed reads, and absent policy never invent a budget', () => {
  for (const data of [null, {ok: false}, {ok: true, submissions: []},
    {ok: true, submissions: Array(100).fill({kind: 'alien'})}]) {
    assert.deepEqual(counts.remainingFromSnapshot(data), {grading: undefined, alien: undefined});
  }
});

test('authoritative counts support non-default caps and unlimited budgets', () => {
  assert.deepEqual(counts.remainingFromSnapshot({ok: true, limits: {
    module: {daily_limit: 9, remaining: 7}, alien: {daily_limit: null, remaining: null},
  }}), {grading: 7, alien: null});
  assert.deepEqual(counts.paintSubmissionsLeft(null, {grading: 7, alien: null}),
    {grading: '7', alien: 'No daily cap'});
});

test('invalid counts never become five or unlimited', () => {
  for (const value of [undefined, '', false, true, '3', -1, 1.5, NaN, Infinity]) {
    assert.equal(counts.countText(value), counts.EMPTY);
  }
  assert.deepEqual(counts.paintSubmissionsLeft(null), {grading: counts.EMPTY, alien: counts.EMPTY});
  assert.equal(counts.countText(0), '0');
});

test('all matching signs clear stale counts when policy cannot be read', () => {
  const grading = [{classList: {toggle() {}}}, {classList: {toggle() {}}}];
  const alien = [{classList: {toggle() {}}}];
  const host = {querySelectorAll: s => s.includes('note') ? []
    : s.includes('grading') ? grading : alien};
  counts.paintSubmissionsLeft(host, {grading: 2, alien: 0});
  assert.deepEqual(grading.map(n => n.textContent), ['2', '2']);
  assert.equal(alien[0].textContent, '0');
  counts.paintSubmissionsLeft(host);
  assert.equal(alien[0].textContent, counts.EMPTY);
});

test('the note always names today, and a reset time when the snapshot gives one', () => {
  // No snapshot yet: the daily boundary is still stated (local midnight).
  assert.equal(counts.resetFromSnapshot(null), undefined);
  assert.equal(counts.resetFromSnapshot({ok: false}), undefined);
  assert.equal(counts.noteText('3'), 'for today · resets midnight');
  // A known reset instant is formatted to a wall-clock time.
  const at = '2026-10-25T00:00:00-06:00';
  assert.equal(counts.resetFromSnapshot({ok: true, limits: {
    module: {reset_at: at}, alien: {reset_at: at}}}), at);
  assert.match(counts.noteText('3', at), /^for today · resets .+/);
  // A garbage reset_at falls back to the documented boundary, never throws.
  assert.equal(counts.noteText('3', 'not-a-date'), 'for today · resets midnight');
  // An uncapped track has no reset.
  assert.equal(counts.noteText(counts.NO_CAP, at), 'No daily reset');
});

test('a cap is remaining out of allowed, and no cap is not a fraction', () => {
  const capped = counts.budgetUse({ok: true, limits: {
    module: {daily_limit: 5, remaining: 4},
  }}, 'module');
  assert.deepEqual(capped, {capped: true, left: 4, allowed: 5, text: '4/5'});
  assert.equal(counts.budgetUse({ok: true, limits: {
    module: {daily_limit: null, remaining: null},
  }}, 'module').capped, false);
  assert.equal(counts.budgetUse({ok: true, limits: {
    module: {daily_limit: 8, remaining: 8},
  }}, 'module').text, '8/8');
  assert.equal(counts.budgetUse(null, 'module'), null);
});

test('painting writes the per-track reset note into matching nodes', () => {
  const nodes = {
    'data-track="grading"': [{classList: {toggle() {}}}],
    'data-track="alien"': [{classList: {toggle() {}}}],
    'data-track-note="grading"': [{}],
    'data-track-note="alien"': [{}],
  };
  const host = {querySelectorAll: sel => {
    for (const key of Object.keys(nodes)) if (sel.includes(key)) return nodes[key];
    return [];
  }};
  counts.paintSubmissionsLeft(host, {grading: 2, alien: null}, '2026-10-25T00:00:00-06:00');
  assert.match(nodes['data-track-note="grading"'][0].textContent, /^for today · resets /);
  assert.equal(nodes['data-track-note="alien"'][0].textContent, 'No daily reset');
});
