/**
 * Rebuild & restart for one regular module.
 * The browser sends only the module code. Phases come from GET /api/rebuild/<id>.
 * This is not a grade. Module pages do not call mountServiceRebuild; the refit
 * fitting is the entry and uses these helpers.
 */
export const REBUILD_CODES = ['DNSM', 'FMM', 'IPM', 'KVS', 'LOG', 'MQB', 'MTA', 'OTA'];
const ALLOW = new Set(REBUILD_CODES);

export const PHASE_WORDS = {
  queued: 'Waiting to build',
  building: 'Building the image. The current service is still the one running.',
  recreating: 'Build finished. Replacing only this service.',
  starting: 'The service was replaced. Waiting for it to accept connections.',
  ready: 'The new service is up.',
  left_stopped: 'Image built. This service was stopped, so it stays stopped.',
  failed: 'Build failed. The previous service was left as it was.',
};

export const FAIL_WORDS = {
  build_failed: 'Build failed. The previous service was left as it was.',
  timed_out: 'The rebuild timed out.',
  recreate_failed: 'The image built, but replacing the service failed.',
  not_ready: 'The service was replaced, but it did not accept connections before the deadline.',
  power_unknown: 'Could not tell whether the service was running. Nothing was replaced.',
  internal: 'The rebuild stopped because of an internal error. Check the service before trying again.',
};

export function rebuildAllowed(code) {
  return ALLOW.has(code);
}

export function rebuildJob(body) {
  return (body && (body.job || body)) || {};
}

export function rebuildJobId(body) {
  if (!body) return '';
  return (body.job && body.job.id) || body.id || '';
}

export function rebuildStatusText(job) {
  const phase = job && job.phase ? job.phase : 'queued';
  const err = job && job.error;
  if (phase === 'failed' && err && FAIL_WORDS[err]) return FAIL_WORDS[err];
  return PHASE_WORDS[phase] || phase;
}

export function rebuildLogText(job) {
  if (!job) return '';
  const tail = job.logTail || job.log;
  return tail ? String(tail) : '';
}

export function rebuildTerminal(job) {
  const phase = job && job.phase;
  return phase === 'ready' || phase === 'left_stopped' || phase === 'failed';
}

export async function postRebuild(code) {
  const res = await fetch('/api/rebuild', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  let body = {};
  try { body = await res.json(); }
  catch (e) { body = {}; }
  return { res, body };
}

export async function getRebuild(id) {
  const res = await fetch('/api/rebuild/' + encodeURIComponent(id), { cache: 'no-store' });
  let body = {};
  try { body = await res.json(); }
  catch (e) { body = {}; }
  return { res, body };
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

export function mountServiceRebuild(host, code) {
  if (!ALLOW.has(code)) {
    throw new Error('rebuild is not available for ' + code);
  }
  const root = el('section', 'service-rebuild');
  root.setAttribute('data-module', code);
  const title = el('h2', 'service-rebuild-title', 'Rebuild & restart');
  const warn = el('p', 'service-rebuild-warn',
    'Replacing this service drops data that lived only inside the container. This does not submit a grade.');
  const button = el('button', 'service-rebuild-go', 'Rebuild & restart');
  button.type = 'button';
  const status = el('p', 'service-rebuild-status', 'Idle');
  const log = el('pre', 'service-rebuild-log', '');
  log.hidden = true;
  root.append(title, warn, button, status, log);
  host.appendChild(root);

  let timer = 0;

  function paint(job) {
    const phase = job && job.phase ? job.phase : 'queued';
    status.textContent = rebuildStatusText(job);
    const tail = rebuildLogText(job);
    log.hidden = !tail;
    log.textContent = tail;
    button.disabled = !rebuildTerminal({ phase });
  }

  async function poll(id) {
    const { body } = await getRebuild(id);
    const job = rebuildJob(body);
    paint(job);
    if (rebuildTerminal(job)) return;
    timer = window.setTimeout(() => poll(id), 1000);
  }

  button.addEventListener('click', async () => {
    window.clearTimeout(timer);
    button.disabled = true;
    status.textContent = 'Sending rebuild request';
    try {
      const { res, body } = await postRebuild(code);
      if (!res.ok || !body.ok) {
        status.textContent = (body && (body.error || body.message)) || 'Rebuild was refused';
        button.disabled = false;
        return;
      }
      const job = rebuildJob(body);
      paint(job);
      const jobId = rebuildJobId(body);
      if (jobId && !rebuildTerminal(job)) poll(jobId);
    } catch (err) {
      status.textContent = 'Rebuild request failed';
      button.disabled = false;
    }
  });

  return {
    root,
    close() { window.clearTimeout(timer); root.remove(); },
  };
}
