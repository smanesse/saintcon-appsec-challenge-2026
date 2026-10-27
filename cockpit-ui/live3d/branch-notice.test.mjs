import test from 'node:test';
import assert from 'node:assert/strict';
import { noticeKind } from './branch-notice.js';

test('an off update check is Up to date, not hidden', () => {
  assert.equal(noticeKind({ enabled: false }), 'current');
  assert.equal(noticeKind({ ok: true, enabled: false, applyEnabled: false }), 'current');
  assert.equal(noticeKind({ enabled: false, isRepo: false }), 'current');
});

test('a checkout that is not a repo still shows Up to date', () => {
  assert.equal(noticeKind({ enabled: true, isRepo: false }), 'current');
});

test('current and behind stay distinct', () => {
  assert.equal(noticeKind({ enabled: true, isRepo: true, behind: 0 }), 'current');
  assert.equal(noticeKind({ enabled: true, isRepo: true, behind: 2 }), 'behind');
  assert.equal(noticeKind({ enabled: true, isRepo: true, updateAvailable: true, behind: 0 }), 'behind');
});

test('a dead read does not become Up to date', () => {
  assert.equal(noticeKind(null), 'keep');
  assert.equal(noticeKind(undefined), 'keep');
});
