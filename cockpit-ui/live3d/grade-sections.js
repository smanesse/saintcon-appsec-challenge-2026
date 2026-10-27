/* Module sections for the grading screen.
 * The scorer's vuln row is only {n, fixed, error, skipped}. The screen keeps a
 * number only when fixed === true. A result_summary line of FAIL or ERROR means
 * that module is broken: its vuln numbers stay off the card. The text after the
 * semicolon is not a field. Before any success, nothing is resolved. No innerHTML.
 */

/* Station names are the ones grade-overview.js already uses for these codes. */
export const MODULES = [
  { code: 'DNSM', name: 'Nav Beacon', harness: 'dns-module' },
  { code: 'FMM', name: 'Cargo Bay', harness: 'file-management-module' },
  { code: 'IPM', name: 'Optical Sensor Array', harness: 'image-processing-module' },
  { code: 'KVS', name: 'Core Memory Banks', harness: 'keystore-module' },
  { code: 'LOG', name: 'Black Box', harness: 'log-module' },
  { code: 'MQB', name: 'Drone Telemetry Bus', harness: 'mqtt-module' },
  { code: 'MTA', name: 'Subspace Comms Relay', harness: 'mail-module' },
  { code: 'OTA', name: 'Fleet Replicator Grid', harness: 'ota-module' },
];

const HARNESS = {};
for (const row of MODULES) {
  HARNESS[row.harness] = row.code;
  HARNESS[row.code] = row.code;
}

function cockpitModule(module) {
  const s = module == null ? '' : String(module).trim();
  return HARNESS[s] || '';
}

function vulnNumber(n) {
  if (typeof n === 'boolean' || n == null || typeof n === 'object') return null;
  const s = String(n).trim();
  if (!/^[1-9]\d*$/.test(s)) return null;
  const v = Number(s);
  return v <= 64 ? v : null;
}

function sortVulns(list) {
  return list.slice().sort((a, b) => a.n - b.n);
}

function rowsFromSecurity(security) {
  const byCode = new Map();
  if (!Array.isArray(security)) return byCode;
  for (const row of security) {
    if (!row || typeof row !== 'object') continue;
    const code = cockpitModule(row.module);
    if (!code || byCode.has(code)) continue;
    const vulns = [];
    const seen = new Set();
    const source = Array.isArray(row.vulns) ? row.vulns : [];
    for (const vuln of source) {
      if (!vuln || typeof vuln !== 'object') continue;
      if (vuln.fixed !== true) continue;
      const n = vulnNumber(vuln.n);
      if (n == null || seen.has(n)) continue;
      seen.add(n);
      vulns.push({ n, solved: true });
    }
    byCode.set(code, sortVulns(vulns));
  }
  return byCode;
}

function rowsFromSolved(solved) {
  const byCode = new Map();
  if (!Array.isArray(solved)) return byCode;
  for (const row of solved) {
    if (!row || typeof row !== 'object') continue;
    const code = cockpitModule(row.module);
    const n = vulnNumber(row.n);
    if (!code || n == null) continue;
    const list = byCode.get(code) || [];
    if (!list.some(item => item.n === n)) list.push({ n, solved: true });
    byCode.set(code, list);
  }
  for (const [code, list] of byCode) byCode.set(code, sortVulns(list));
  return byCode;
}

const LINE = /^([\w.-]+): (PASS|FAIL|ERROR)\b/gm;

function functionalOutcome(submission) {
  const found = new Map();
  const summary = submission && submission.result_summary;
  if (typeof summary !== 'string') return found;
  LINE.lastIndex = 0;
  let match;
  while ((match = LINE.exec(summary))) {
    const code = cockpitModule(match[1]);
    if (!code || found.has(code)) continue;
    found.set(code, match[2]);
  }
  return found;
}

export function moduleSections(submission) {
  const reported = !!submission && Array.isArray(submission.security);
  const byCode = reported
    ? rowsFromSecurity(submission.security)
    : rowsFromSolved(submission && submission.security_solved);
  const outcome = functionalOutcome(submission);
  return MODULES.map(row => {
    const line = outcome.get(row.code) || '';
    const broken = line === 'FAIL' || line === 'ERROR';
    return {
      code: row.code,
      name: row.name,
      broken,
      vulns: broken ? [] : (byCode.get(row.code) || []),
    };
  });
}
