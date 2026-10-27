/* Grade overview adapter. Read-only rows for the full-set panel.
 *
 * Id selection for a regular module is exclusive:
 *   COMPLETE or FAILED with a security_solved key -> that module's reported
 *     n values only (decimal strings, leading zeros stripped). Status fixed
 *     ids are not added. A missing key is unreported, not an empty success.
 *   A FAILED job is mark 'failed' for every module, including PKT.
 *   A terminal job is not overridden by a stale status run, harness error,
 *     or inconclusive item.
 *   RUNNING/PENDING/QUEUED/SUBMITTED keeps status solved ids when the record
 *     has items, else previousSolved. Those ids are not blanked.
 *   No submission keeps the status record's own mark and solved ids.
 * Harness directory names and cockpit codes both match security_solved.module.
 * The two id lists are never unioned. PKT is not a patchable module: aliens
 * are saved submission id/name rows only. A missing aliens key on a terminal
 * job is unreported.
 *
 * No innerHTML. No score math.
 */
import { derive, solvedIds } from './status.js';

export const MODULES = [
  { code: 'DNSM', name: 'Nav Beacon' },
  { code: 'FMM', name: 'Cargo Bay' },
  { code: 'IPM', name: 'Optical Sensor Array' },
  { code: 'KVS', name: 'Core Memory Banks' },
  { code: 'LOG', name: 'Black Box' },
  { code: 'MQB', name: 'Drone Telemetry Bus' },
  { code: 'MTA', name: 'Subspace Comms Relay' },
  { code: 'OTA', name: 'Fleet Replicator Grid' },
  { code: 'PKT', name: 'Signal Harpoon' },
];

const NON_TERMINAL = { RUNNING: 1, PENDING: 1, QUEUED: 1, SUBMITTED: 1 };

/* Repo directory -> cockpit code. The cockpit code itself is also accepted. */
const HARNESS_MODULE = {
  'dns-module': 'DNSM',
  'file-management-module': 'FMM',
  'image-processing-module': 'IPM',
  'keystore-module': 'KVS',
  'log-module': 'LOG',
  'mqtt-module': 'MQB',
  'mail-module': 'MTA',
  'ota-module': 'OTA',
};

function hasOwn(obj, key) {
  return !!obj && Object.prototype.hasOwnProperty.call(obj, key);
}

function cockpitModule(module) {
  const s = module == null ? '' : String(module).trim();
  if (HARNESS_MODULE[s]) return HARNESS_MODULE[s];
  for (let i = 0; i < MODULES.length; i++) {
    if (MODULES[i].code === s) return s;
  }
  return '';
}

function decimalId(n) {
  const s = String(n).trim();
  if (!s) return '';
  return s.replace(/^0+/, '') || s;
}

function unique(ids) {
  const seen = new Set();
  const out = [];
  for (const id of ids) {
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

function sortIds(ids) {
  const isNum = x => /^\d+$/.test(x);
  return ids.map((x, i) => [x, i]).sort((a, b) =>
    (isNum(a[0]) && isNum(b[0])) ? (+a[0] - +b[0]) || (a[1] - b[1]) : a[1] - b[1])
    .map(x => x[0]);
}

function asIds(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const n of list) {
    if (n == null || typeof n === 'object') continue;
    const id = decimalId(n);
    if (id) out.push(id);
  }
  return sortIds(unique(out));
}

function asAliens(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const a of list) {
    if (!a || typeof a !== 'object') continue;
    if (a.solved === false) continue;
    const id = a.id == null ? '' : String(a.id);
    const name = a.name == null ? '' : String(a.name);
    if (!id && !name) continue;
    out.push({ id, name });
  }
  return out;
}

function previousFor(previousSolved, code) {
  if (!previousSolved) return { ids: [], aliens: [] };
  if (Array.isArray(previousSolved)) {
    const row = previousSolved.find(r => r && r.code === code);
    if (!row) return { ids: [], aliens: [] };
    return { ids: asIds(row.ids), aliens: asAliens(row.aliens) };
  }
  if (typeof previousSolved === 'object') {
    const v = previousSolved[code];
    if (Array.isArray(v)) {
      if (v.some(x => x && typeof x === 'object')) return { ids: [], aliens: asAliens(v) };
      return { ids: asIds(v), aliens: [] };
    }
    if (v && typeof v === 'object') return { ids: asIds(v.ids), aliens: asAliens(v.aliens) };
  }
  return { ids: [], aliens: [] };
}

function rawItems(rec) {
  const vulns = rec && rec.vulns;
  if (!vulns || !Array.isArray(vulns.items) || !vulns.items.length) return null;
  return vulns.items;
}

function hasInconclusive(rec) {
  const vulns = rec && rec.vulns;
  const items = vulns && Array.isArray(vulns.items) ? vulns.items : [];
  return items.some(it => it && it.result === 'inconclusive');
}

function submissionIds(submission, code) {
  const rows = submission && Array.isArray(submission.security_solved) ? submission.security_solved : [];
  const ids = [];
  for (const row of rows) {
    if (!row || cockpitModule(row.module) !== code || row.n == null || row.n === '') continue;
    const id = decimalId(row.n);
    if (id) ids.push(id);
  }
  return sortIds(unique(ids));
}

function jobName(submission) {
  return submission && typeof submission.status_name === 'string' ? submission.status_name : '';
}

function isNonTerminal(job) {
  return NON_TERMINAL[job] === 1;
}

function isTerminal(job) {
  return job === 'COMPLETE' || job === 'FAILED';
}

function statusSolved(rec, derived) {
  if (!rawItems(rec)) return null;
  return solvedIds(derived);
}

function chooseIds(rec, submission, prevIds, code, derived, job) {
  if (isTerminal(job)) {
    if (!hasOwn(submission, 'security_solved')) return { ids: [], idState: 'unreported' };
    return { ids: submissionIds(submission, code), idState: 'reported' };
  }
  if (isNonTerminal(job)) {
    const fromStatus = statusSolved(rec, derived);
    if (fromStatus && fromStatus.length) return { ids: fromStatus, idState: 'status' };
    if (prevIds.length) return { ids: prevIds, idState: 'status' };
    if (fromStatus) return { ids: [], idState: 'status' };
    return { ids: [], idState: 'none' };
  }
  const fromStatus = statusSolved(rec, derived);
  if (fromStatus && fromStatus.length) return { ids: fromStatus, idState: 'status' };
  if (fromStatus) return { ids: [], idState: 'status' };
  return { ids: [], idState: 'none' };
}

function pktIdState(submission, job) {
  if (!isTerminal(job)) return 'none';
  return hasOwn(submission, 'security_solved') ? 'reported' : 'unreported';
}

function chooseAliens(submission, prevAliens, job) {
  if (isTerminal(job)) {
    if (!hasOwn(submission, 'aliens')) return { aliens: [], alienState: 'unreported' };
    const list = Array.isArray(submission.aliens) ? submission.aliens : [];
    return { aliens: asAliens(list), alienState: 'reported' };
  }
  const parsed = hasOwn(submission, 'aliens') && Array.isArray(submission.aliens)
    ? asAliens(submission.aliens) : null;
  if (parsed && parsed.length) return { aliens: parsed, alienState: 'reported' };
  if (isNonTerminal(job) && prevAliens.length) return { aliens: prevAliens, alienState: 'reported' };
  if (parsed) return { aliens: parsed, alienState: 'reported' };
  return { aliens: [], alienState: 'none' };
}

function powerNote(live) {
  if (!live || typeof live !== 'object') return null;
  if (live.released === false || live.availability === 'not_yet_available') return 'unavailable';
  if (live.powered === 'off') return 'off';
  return null;
}

function chooseMark(derived, rec, submission, job, ids, aliens, code, alienState) {
  if (job === 'FAILED') return 'failed';
  if (job === 'COMPLETE') {
    if (code === 'PKT') {
      if (alienState === 'unreported') return 'unreported';
      if (aliens.length) return 'success';
      return 'finished-empty';
    }
    if (!hasOwn(submission, 'security_solved')) return 'unreported';
    if (ids.length) return 'success';
    return 'finished-empty';
  }
  const running = !!(derived.running
    || derived.run === 'queued' || derived.run === 'building' || derived.run === 'running'
    || isNonTerminal(job));
  const error = !!(derived.harnessError || derived.run === 'error');
  if (running) return 'running';
  if (error) return 'error';
  if (hasInconclusive(rec)) return 'inconclusive';
  if (ids.length || aliens.length) return 'success';
  if (submission) return 'finished-empty';
  return 'no-results';
}

export function gradeRows({ statusDoc, liveMap, submission, previousSolved } = {}) {
  const mods = (statusDoc && statusDoc.modules && typeof statusDoc.modules === 'object')
    ? statusDoc.modules : {};
  const live = (liveMap && typeof liveMap === 'object') ? liveMap : null;
  const job = jobName(submission);
  return MODULES.map(({ code, name }) => {
    const rec = (mods[code] && typeof mods[code] === 'object') ? mods[code] : null;
    const liveEntry = (live && live[code] && typeof live[code] === 'object') ? live[code] : null;
    const derived = derive(rec, { code, live: liveEntry });
    const prev = previousFor(previousSolved, code);
    const picked = code === 'PKT'
      ? { ids: [], idState: pktIdState(submission, job) }
      : chooseIds(rec, submission, prev.ids, code, derived, job);
    const alienPick = code === 'PKT'
      ? chooseAliens(submission, prev.aliens, job)
      : { aliens: [], alienState: 'none' };
    return {
      code,
      name,
      ids: picked.ids,
      idState: picked.idState,
      mark: chooseMark(derived, rec, submission, job, picked.ids, alienPick.aliens, code, alienPick.alienState),
      power: powerNote(liveEntry),
      aliens: alienPick.aliens,
      alienState: alienPick.alienState,
    };
  });
}
