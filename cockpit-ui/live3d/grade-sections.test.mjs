import assert from 'node:assert/strict';
import test from 'node:test';
import { MODULES, moduleSections } from './grade-sections.js';

test('before any result, every section is unresolved and headed by its code', () => {
  const rows = moduleSections(null);
  assert.deepEqual(rows.map(row => row.code), MODULES.map(row => row.code));
  assert.ok(rows.every(row => row.vulns.length === 0));
  assert.deepEqual(rows.map(row => row.name), MODULES.map(row => row.name));
  assert.equal(rows.find(row => row.code === 'FMM').name, 'Cargo Bay');
  assert.ok(rows.every(row => row.broken === false));
  assert.ok(rows.every(row => !('verdict' in row)));
});

test('only a solved number is kept, with no missed number or vuln name', () => {
  const rows = moduleSections({
    passed: true,
    result_summary: 'file-management-module: PASS; ok',
    security: [{
      module: 'file-management-module',
      total: 3,
      fixed: 1,
      vulns: [
        { n: 1, fixed: true, error: false, skipped: false, slug: 'hidden', title: 'nope', output: 'flag' },
        { n: 2, fixed: false, error: false, skipped: false },
        { n: 4, fixed: false, error: true, skipped: false },
      ],
    }],
  });
  const fmm = rows.find(row => row.code === 'FMM');
  assert.deepEqual(fmm.vulns, [{ n: 1, solved: true }]);
  assert.equal(fmm.name, 'Cargo Bay');
  assert.equal('total' in fmm, false);
  assert.equal('slug' in fmm.vulns[0], false);
  assert.ok(rows.filter(row => row.code !== 'FMM').every(row => row.vulns.length === 0));
});

test('a missing security list does not invent numbers from a pass line', () => {
  const rows = moduleSections({
    passed: true,
    result_summary: 'dns-module: PASS; ok\nfile-management-module: FAIL; 1 failure',
  });
  assert.ok(rows.every(row => row.vulns.length === 0));
});

test('solved indexes alone do not invent the unsolved numbers', () => {
  const rows = moduleSections({
    security_solved: [{ module: 'dns-module', n: 3 }],
  });
  const dnsm = rows.find(row => row.code === 'DNSM');
  assert.deepEqual(dnsm.vulns, [{ n: 3, solved: true }]);
  assert.ok(rows.filter(row => row.code !== 'DNSM').every(row => row.vulns.length === 0));
});

test('a FAIL or ERROR line marks the module broken and hides its numbers', () => {
  const rows = moduleSections({
    security_status: 'not_evaluated',
    result_summary: 'file-management-module: FAIL; 1 failure\nmail-module: ERROR (ValueError); boom\n'
      + 'dns-module: PASS; ok',
    security: [
      { module: 'file-management-module', vulns: [{ n: 1, fixed: true, error: false, skipped: false }] },
      { module: 'mail-module', vulns: [{ n: 4, fixed: true, error: false, skipped: false }] },
      { module: 'dns-module', vulns: [{ n: 2, fixed: true, error: false, skipped: false }] },
    ],
  });
  const fmm = rows.find(row => row.code === 'FMM');
  const mta = rows.find(row => row.code === 'MTA');
  const dnsm = rows.find(row => row.code === 'DNSM');
  assert.equal(fmm.broken, true);
  assert.deepEqual(fmm.vulns, []);
  assert.equal(mta.broken, true);
  assert.deepEqual(mta.vulns, []);
  assert.equal(dnsm.broken, false);
  assert.deepEqual(dnsm.vulns, [{ n: 2, solved: true }]);
  assert.equal('detail' in fmm, false);
  assert.ok(!JSON.stringify(rows).includes('1 failure'));
  assert.ok(!JSON.stringify(rows).includes('ValueError'));
});

test('a reported security list is the whole set, not a union with solved indexes', () => {
  const rows = moduleSections({
    security: [{ module: 'FMM', vulns: [{ n: 2, fixed: false, error: false, skipped: true }] }],
    security_solved: [{ module: 'FMM', n: 9 }, { module: 'dns-module', n: 1 }],
  });
  const fmm = rows.find(row => row.code === 'FMM');
  assert.deepEqual(fmm.vulns, []);
  assert.ok(rows.find(row => row.code === 'DNSM').vulns.length === 0);
});
