import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { scoreReadText } from './api.js';

const blank = { points: '?', vulns: '?', ships: '?' };

test('a signed-in score is shown as returned', () => {
  assert.deepEqual(scoreReadText({ ok: true, score: 7, vulns: 3, ships: 1 }), {
    points: '7', vulns: '3', ships: '1',
  });
  assert.deepEqual(scoreReadText({ ok: true, score: 0, vulns: 0, ships: 0 }), {
    points: '0', vulns: '0', ships: '0',
  });
});

test('a missing sign-in or a failed read stays unknown', () => {
  assert.deepEqual(scoreReadText(null), blank);
  assert.deepEqual(scoreReadText({ ok: false, loggedIn: false }), blank);
  assert.deepEqual(scoreReadText({ ok: false, error: 'harness unreachable' }), blank);
  assert.deepEqual(scoreReadText({ ok: true }), blank);
});

test('the person menu score still comes from GET /api/score', () => {
  const panel = readFileSync(new URL('./grade-panel.js', import.meta.url), 'utf8');
  assert.match(panel, /getMyScore\(/);
  assert.match(panel, /\/api\/scoreboard\?all=1/);
  assert.doesNotMatch(panel, /listedScore/);
});
