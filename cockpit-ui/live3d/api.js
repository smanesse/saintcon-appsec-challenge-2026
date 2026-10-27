/* SAINTCON 2026 — coordinator client for live3d/.
 *
 * Callers pass cockpit codes (MTA, KVS, …).  This module is the only place
 * that translates to catalog codes (MAIL) for the wire.  Same-origin
 * origin-root `/api/...` — never a hardcoded :8787.
 *
 * Stateless per call.  No poll loop (02), no mast colours, no innerHTML.
 *
 * 00:  login / register / logout / getAuthStatus
 * 03:  getChallenges / submit / getSubmissions / getSubmission
 * 04:  getUpdates / applyUpdates (caller must confirm apply — never auto)
 */

import { mountLinkUx, announce, SLOW_MS, trackAbort } from './api-ux.js';

export { mountLinkUx, announce, SLOW_MS };

export const CATALOG_ALIAS = { MTA: 'MAIL' };
export const COCKPIT_OF = { MAIL: 'MTA' };

export function toCatalogCode(code) {
  if (code == null) return code;
  return CATALOG_ALIAS[code] || code;
}

export function toCockpitCode(code) {
  if (code == null) return code;
  return COCKPIT_OF[code] || code;
}

const cfg = {
  base: '',
  timeoutMs: { get: 4000, post: 15000 },
};

/* Above the bridge HARNESS_TIMEOUT (30s) so a slow accept is not aborted first. */
export const GRADE_TIMEOUT_MS = 45000;

export function configure({ base = '', timeoutMs } = {}) {
  if (base !== undefined) cfg.base = String(base).replace(/\/+$/, '');
  if (timeoutMs) {
    cfg.timeoutMs = {
      get: timeoutMs.get != null ? timeoutMs.get : cfg.timeoutMs.get,
      post: timeoutMs.post != null ? timeoutMs.post : cfg.timeoutMs.post,
    };
  }
}

function nowMs() {
  return (typeof performance !== 'undefined' && performance.now)
    ? performance.now() : Date.now();
}

function wall(t0) {
  return Math.round(nowMs() - t0);
}

function unreachableError(raw) {
  if (!raw) return 'coordinator not on this origin';
  if (typeof raw === 'string' && /unreachable/i.test(raw)) return raw;
  return 'coordinator not on this origin';
}

function isUnreachablePayload(status, data) {
  if (status === 502) return true;
  const err = data && (data.error || data.message);
  return typeof err === 'string' && /unreachable/i.test(err);
}

function failEnvelope(error, ms, extra) {
  const out = { ok: false, reachable: false, error: error || 'coordinator not on this origin', ms };
  if (extra) Object.assign(out, extra);
  return out;
}

async function request(method, path, { body, signal, timeoutMs, doc, headers, cache } = {}) {
  const t0 = nowMs();
  const url = cfg.base + path;
  const ac = new AbortController();
  const msLimit = timeoutMs != null
    ? timeoutMs
    : (method === 'GET' ? cfg.timeoutMs.get : cfg.timeoutMs.post);
  const timer = setTimeout(() => ac.abort(), msLimit);
  const untrack = trackAbort(doc, ac);

  if (signal) {
    if (signal.aborted) ac.abort();
    else signal.addEventListener('abort', () => ac.abort(), { once: true });
  }

  try {
    const init = { method, signal: ac.signal, headers: Object.assign({}, headers || {}) };
    if (cache) init.cache = cache;
    if (body !== undefined) {
      if (typeof FormData !== 'undefined' && body instanceof FormData) {
        init.body = body;
      } else {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
      }
    }
    const r = await fetch(url, init);
    const text = await r.text();
    let data = null;
    try { data = JSON.parse(text); } catch (e) { data = null; }

    if (!data || typeof data !== 'object') {
      return failEnvelope(
        r.status === 502 ? 'coordinator not on this origin' : ('HTTP ' + r.status),
        wall(t0),
      );
    }
    if (isUnreachablePayload(r.status, data)) {
      return failEnvelope(data.error || 'coordinator not on this origin', wall(t0));
    }
    return { reachable: true, status: r.status, data, ms: wall(t0) };
  } catch (e) {
    const timed = ac.signal.aborted && !(signal && signal.aborted);
    const error = timed ? 'timed out'
      : (signal && signal.aborted) ? 'aborted'
      : unreachableError(e && e.message);
    return failEnvelope(error, wall(t0));
  } finally {
    clearTimeout(timer);
    untrack();
  }
}

function needCode(fn, code) {
  if (code == null || code === '') throw new TypeError(fn + ': missing code');
}

export async function getHealth(opts) {
  const raw = await request('GET', '/api/health', opts || {});
  if (!raw.reachable) {
    return { ok: false, reachable: false, error: raw.error, ms: raw.ms };
  }
  const ok = !!(raw.data && raw.data.ok === true);
  const out = { ok, reachable: true, ms: raw.ms };
  if (!ok) out.error = (raw.data && raw.data.error) || 'health check failed';
  return out;
}

function remapSub(sub) {
  const catalogCode = sub.code;
  const row = Object.assign({}, sub);
  row.catalogCode = catalogCode;
  row.code = toCockpitCode(catalogCode);
  return row;
}

export async function getCatalog(opts) {
  const raw = await request('GET', '/api/catalog', opts || {});
  if (!raw.reachable) {
    return {
      ok: false, reachable: false, error: raw.error, ms: raw.ms,
      ship: null, subsystems: [],
    };
  }
  const ship = (raw.data && raw.data.ship) || null;
  const src = (raw.data && raw.data.subsystems) || [];
  return {
    ok: true,
    reachable: true,
    ms: raw.ms,
    ship,
    subsystems: src.map(remapSub),
  };
}

export async function getLive(opts) {
  const raw = await request('GET', '/api/live', opts || {});
  if (!raw.reachable) {
    return {
      ok: false, reachable: false, error: raw.error, ms: raw.ms,
      available: false, host: null, dockerContainers: [], systems: [], byCode: {},
    };
  }
  const systems = ((raw.data && raw.data.systems) || []).map((s) => {
    const catalogCode = s.code;
    const p = s.powered;
    const powered = (p === 'on' || p === 'off' || p === 'unknown') ? p : 'unknown';
    return Object.assign({}, s, {
      catalogCode,
      code: toCockpitCode(catalogCode),
      powered,
    });
  });
  const byCode = {};
  for (const s of systems) byCode[s.code] = s;
  return {
    ok: true,
    reachable: true,
    ms: raw.ms,
    available: !!(raw.data && raw.data.available),
    host: (raw.data && raw.data.host) || null,
    dockerContainers: (raw.data && raw.data.dockerContainers) || [],
    systems,
    byCode,
  };
}

export async function interact(code, action, params, opts) {
  needCode('interact', code);
  if (action == null || action === '') throw new TypeError('interact: missing action');
  const raw = await request('POST', '/api/interact', Object.assign({}, opts, {
    body: { code: toCatalogCode(code), action, params: params || {} },
  }));
  const result = (raw.data && raw.data.result) || {};
  const httpOk = raw.reachable && raw.status === 200;
  const ok = !!(httpOk && result.ok);
  const out = {
    ok,
    reachable: !!raw.reachable,
    ms: raw.ms,
    code,
    action,
    result,
  };
  if (!ok) {
    /* Prefer the bridge's stable token (e.g. module_powered_off) over summary. */
    out.error = (raw.data && raw.data.error)
      || result.error
      || result.summary
      || raw.error
      || 'interact failed';
    if (result.error === 'module_powered_off' || out.error === 'module_powered_off') {
      out.error = 'module_powered_off';
      out.powered = 'off';
    }
  }
  return out;
}

const POWER_OPS = { start: 1, stop: 1, restart: 1 };

export async function power(code, op, opts) {
  needCode('power', code);
  if (!POWER_OPS[op]) throw new TypeError('power: unknown op');
  if (code === 'PKT') {
    return {
      ok: false, reachable: true, error: 'PKT has no compose service', ms: 0,
      code, op, result: {},
    };
  }
  const raw = await request('POST', '/api/power', Object.assign({}, opts, {
    body: { code: toCatalogCode(code), op },
  }));
  const result = (raw.data && raw.data.result) || {};
  const httpOk = raw.reachable && raw.status === 200;
  const ok = !!(httpOk && result.ok);
  const out = {
    ok,
    reachable: !!raw.reachable,
    ms: raw.ms,
    code,
    op,
    result,
  };
  if (!ok) {
    out.error = (raw.data && raw.data.error)
      || result.error
      || result.summary
      || raw.error
      || 'power failed';
  }
  return out;
}

export async function getHarness(opts) {
  const raw = await request('GET', '/api/harness', opts || {});
  const empty = { configured: false, url: '', loggedIn: false, username: '' };
  if (!raw.reachable) {
    return Object.assign({
      ok: false, reachable: false, error: raw.error, ms: raw.ms,
    }, empty);
  }
  const d = raw.data || {};
  return {
    ok: true,
    reachable: true,
    ms: raw.ms,
    configured: !!d.configured,
    url: d.url || '',
    loggedIn: !!d.loggedIn,
    username: d.username || '',
  };
}

export async function getAuthStatus(opts) {
  const raw = await request('GET', '/api/auth/status', opts || {});
  const empty = { configured: false, url: '', loggedIn: false, username: '' };
  if (!raw.reachable) {
    return Object.assign({
      ok: false, reachable: false, error: raw.error, ms: raw.ms,
    }, empty);
  }
  const d = raw.data || {};
  return {
    ok: true,
    reachable: true,
    ms: raw.ms,
    configured: !!d.configured,
    url: d.url || '',
    loggedIn: !!d.loggedIn,
    username: d.username || '',
  };
}

function authResult(raw, failMsg) {
  const d = (raw && raw.data) || {};
  const ok = !!(raw && raw.reachable && d.ok !== false && (d.loggedIn || d.ok));
  const out = {
    ok,
    reachable: !!(raw && raw.reachable),
    ms: (raw && raw.ms) || 0,
    loggedIn: !!d.loggedIn,
    username: d.username || '',
    configured: d.configured,
  };
  if (!ok) out.error = d.error || d.message || (raw && raw.error) || failMsg;
  return out;
}

export async function login(username, password, opts) {
  const raw = await request('POST', '/api/auth/login', Object.assign({}, opts, {
    body: { username, password },
  }));
  return authResult(raw, 'login failed');
}

export async function register(name, username, password, opts) {
  const raw = await request('POST', '/api/auth/register', Object.assign({}, opts, {
    body: { name, username, password },
  }));
  return authResult(raw, 'register failed');
}

export async function logout(opts) {
  const raw = await request('POST', '/api/auth/logout', Object.assign({}, opts, {
    body: {},
  }));
  const d = (raw && raw.data) || {};
  return {
    ok: !!(raw && raw.reachable),
    reachable: !!(raw && raw.reachable),
    ms: (raw && raw.ms) || 0,
    loggedIn: false,
    error: d.error,
  };
}

export async function getScoreboard(opts) {
  const raw = await request('GET', '/api/scoreboard', opts || {});
  const d = (raw && raw.data) || {};
  return {
    ok: !!(raw && raw.reachable && raw.ok !== false && d.ok !== false),
    reachable: !!(raw && raw.reachable),
    entries: Array.isArray(d.entries) ? d.entries : [],
  };
}

function scoreCount(value) {
  if (value == null || value === '' || Number.isNaN(Number(value))) return null;
  return String(value);
}

/* Person-menu text for the signed-in score read. A missing sign-in or a
 * failed read stays unknown; a real zero is a score. */
export function scoreReadText(reading) {
  const blank = { points: '?', vulns: '?', ships: '?' };
  if (!reading || reading.ok !== true) return blank;
  const points = scoreCount(reading.score);
  if (points == null) return blank;
  const vulns = scoreCount(reading.vulns);
  const ships = scoreCount(reading.ships);
  return {
    points,
    vulns: vulns == null ? '?' : vulns,
    ships: ships == null ? '?' : ships,
  };
}

export async function getMyScore(opts) {
  const raw = await request('GET', '/api/score', opts || {});
  const d = (raw && raw.data) || {};
  if (!raw || !raw.reachable || d.ok === false || d.loggedIn === false) {
    return { ok: false, score: null, vulns: null, ships: null };
  }
  return {
    ok: true,
    score: d.score,
    vulns: d.vulns_fixed,
    ships: d.ships,
  };
}

export async function getFlags(opts) {
  const raw = await request('GET', '/api/flags', opts || {});
  const d = (raw && raw.data) || {};
  if (!raw || !raw.reachable || d.ok === false || d.loggedIn === false) {
    return { ok: false, flags: [], stale: true, loggedIn: d.loggedIn };
  }
  const flags = Array.isArray(d.flags) ? d.flags.filter(f => f && typeof f === 'object') : [];
  return { ok: true, flags, stale: d.stale === true };
}

export async function getChallenges(opts) {
  const raw = await request('GET', '/api/challenges', opts || {});
  if (!raw.reachable) {
    return {
      ok: false, reachable: false, error: raw.error, ms: raw.ms,
      submissions_open: null, challenges: [], aliens: [],
    };
  }
  const d = raw.data || {};
  return {
    ok: d.ok !== false,
    reachable: true,
    ms: raw.ms,
    submissions_open: d.submissions_open,
    challenges: d.challenges || [],
    aliens: d.aliens || [],
    configured: d.configured,
    error: d.error,
  };
}

export async function getSubmissionLimits(alienTarget = 'all', opts) {
  let path = '/api/submission-limits?alien_target=' + encodeURIComponent(alienTarget);
  if (opts && opts.fresh) path += '&_=' + Date.now();
  const raw = await request('GET', path, opts || {});
  if (!raw.reachable) return {ok: false, error: raw.error};
  return {...raw.data, httpStatus: raw.data.httpStatus || raw.status};
}

export async function submit(payload, opts) {
  const kind = (payload && payload.kind) || 'module';
  const alienTarget = payload && payload.alien_target;
  const wantsTarget = kind === 'alien' && alienTarget != null
    && alienTarget !== '' && alienTarget !== 'all';
  let body;
  if (payload && payload.file) {
    body = new FormData();
    body.append('file', payload.file);
    body.append('kind', kind);
    if (wantsTarget) body.append('alien_target', alienTarget);
  } else {
    body = { kind };
    if (wantsTarget) body.alien_target = alienTarget;
  }
  const raw = await request('POST', '/api/submit', Object.assign({ timeoutMs: GRADE_TIMEOUT_MS }, opts, { body }));
  const wrap = (raw && raw.data) || {};
  const res = wrap.result || wrap;
  const ok = !!(raw && raw.reachable && res && res.ok);
  const out = {
    ok,
    reachable: !!(raw && raw.reachable),
    ms: (raw && raw.ms) || 0,
    result: res || {},
    job_id: res && res.job_id,
    packaged: res && res.packaged,
  };
  if (!ok) out.error = (res && (res.error || res.message)) || (raw && raw.error) || 'submit failed';
  return out;
}

export async function getSubmissions(opts) {
  const raw = await request('GET', '/api/submissions', opts || {});
  if (!raw.reachable) {
    return { ok: false, reachable: false, error: raw.error, ms: raw.ms, submissions: [], now: null };
  }
  const d = raw.data || {};
  return {
    ok: d.ok !== false,
    reachable: true,
    ms: raw.ms,
    submissions: d.submissions || [],
    now: d.now || null,
    error: d.error,
  };
}

export async function getSubmission(jobId, opts) {
  if (!jobId) throw new TypeError('getSubmission: missing jobId');
  const raw = await request('GET', '/api/submissions/' + encodeURIComponent(jobId), Object.assign({ timeoutMs: GRADE_TIMEOUT_MS }, opts || {}));
  if (!raw.reachable) {
    return { ok: false, reachable: false, error: raw.error, ms: raw.ms, submission: null };
  }
  const d = raw.data || {};
  return {
    ok: d.ok !== false,
    reachable: true,
    ms: raw.ms,
    submission: d.submission || d,
    error: d.error,
  };
}

/* Local A.L.I.E.N. test: the bridge runs aliens/<ship>/exploit.py against the
 * locally-running teaching ship and greps the output for the flag. Same-origin,
 * loopback-only on the bridge. Returns the bridge's result envelope. */
export async function alienTest(challengePath, opts) {
  // The bridge brings the ship up (building the image on first use), runs the
  // exploit, then spins it down — all in this one request, so allow minutes.
  const raw = await request('POST', '/api/alien/test',
    Object.assign({ timeoutMs: 600000 }, opts, { body: { challenge_path: challengePath } }));
  if (!raw.reachable) {
    return { ok: false, reachable: false, error: raw.error, ms: raw.ms };
  }
  const d = raw.data || {};
  const res = (d && d.result) || d;
  return Object.assign({ reachable: true, ms: raw.ms }, res || {});
}

export async function getUpdates(opts) {
  const raw = await request('GET', '/api/updates', opts || {});
  if (!raw.reachable) {
    return { ok: false, reachable: false, error: raw.error, ms: raw.ms, enabled: false };
  }
  return Object.assign({ reachable: true, ms: raw.ms }, raw.data || {});
}

/** Caller MUST obtain explicit UI confirmation before calling. Never auto-invoke.
 *  Requires bridge BRIDGE_UPDATE_APPLY=1 and confirm header (set here). */
export async function applyUpdates(opts) {
  const raw = await request('POST', '/api/updates/apply', Object.assign({}, opts, {
    body: {},
    headers: { 'X-Bridge-Update-Apply': '1' },
  }));
  const wrap = (raw && raw.data) || {};
  const res = wrap.result || wrap;
  return {
    ok: !!(raw && raw.reachable && res && res.ok !== false),
    reachable: !!(raw && raw.reachable),
    ms: (raw && raw.ms) || 0,
    result: res || {},
    error: (res && (res.error || res.message)) || (raw && raw.error),
  };
}
