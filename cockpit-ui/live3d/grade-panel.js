/* Grade panel. Wide cockpit only. Not a per-module port.
 * Each module is a wrapping card. The three-letter code is the heading; the
 * station name already used for that code is smaller. A card lists only solved
 * vuln numbers. It does not list a missed number, a total, or "not solved".
 * Before any success, nothing is resolved. A FAIL or ERROR line means the
 * module is broken, and its vuln numbers stay hidden. Status, Submit, and the
 * remaining counts are one dashboard. No innerHTML.
 */
import { submit, getSubmission, getSubmissions, getSubmissionLimits, getMyScore, getAuthStatus, scoreReadText } from './api.js';
import { mountFeedback, notifySubmissionChange } from './submission-feedback.js';
import { loadLive, loadStatus } from './status.js';
import { moduleSections } from './grade-sections.js';
import { STATUS_WORDS as words, statusWord, isTerminal as terminal, renderProgress } from './submit-core.js';
import { paintSubmissionsLeft, paintBudget, remainingFromSnapshot, resetFromSnapshot } from './submissions-left.js';

function placeFromList(entries, username) {
  const name = String(username || '').trim();
  if (!name || !Array.isArray(entries)) return null;
  for (const row of entries) {
    if (!row || String(row.username || '').trim() !== name) continue;
    const rank = Number(row.rank);
    return Number.isFinite(rank) ? String(Math.trunc(rank)) : null;
  }
  return null;
}

function refreshMenuScore(root) {
  const doc = root && root.querySelectorAll ? root : document;
  const paint = (reading, place) => {
    const text = scoreReadText(reading);
    text.place = place == null ? '?' : place;
    doc.querySelectorAll('[data-score]').forEach(node => {
      const key = node.getAttribute('data-score');
      node.textContent = text[key] || '?';
    });
  };
  Promise.all([
    getMyScore({ cache: 'no-store' }),
    getAuthStatus({ cache: 'no-store' }),
    fetch('/api/scoreboard?all=1', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).catch(() => null),
  ]).then(([reading, who, board]) => {
    const username = who && who.loggedIn ? who.username : '';
    const entries = board && Array.isArray(board.entries) ? board.entries : null;
    paint(reading, username && entries ? placeFromList(entries, username) : null);
  }).catch(() => paint(null, null));
}

function paintScores() {
  refreshMenuScore(document);
}

function newestSubmission(list) {
  const rows = Array.isArray(list) ? list.filter(r => r && typeof r === 'object') : [];
  if (!rows.length) return null;
  let best = rows[0];
  let bestAt = Date.parse(best.created);
  if (Number.isNaN(bestAt)) bestAt = -Infinity;
  for (let i = 1; i < rows.length; i++) {
    const t = Date.parse(rows[i].created);
    const at = Number.isNaN(t) ? -Infinity : t;
    if (at >= bestAt) {
      best = rows[i];
      bestAt = at;
    }
  }
  return best;
}

function placeAfter(node, ref) {
  const parent = ref && ref.parentNode;
  if (!parent || !node) return;
  const kids = parent.children;
  let next = null;
  for (let i = 0; i < kids.length; i++) {
    if (kids[i] === ref) {
      next = kids[i + 1] || null;
      break;
    }
  }
  if (next === node) return;
  if (next) parent.insertBefore(node, next);
  else parent.appendChild(node);
}

function ensureProgress(panel) {
  let prog = panel.querySelector('.grade-progress');
  if (!prog) {
    prog = document.createElement('div');
    prog.className = 'grade-progress sp-progress';
    prog.hidden = true;
    prog.setAttribute('aria-live', 'polite');
    const status = panel.querySelector('.grade-status');
    if (status) placeAfter(prog, status);
    else panel.appendChild(prog);
  }
  return prog;
}

function paintProgress(panel, sub) {
  renderProgress(ensureProgress(panel), sub);
}

const IDLE = { word: 'Idle', detail: 'No running grades.' };

function jobLine(sub) {
  if (!sub || !sub.status_name) return IDLE;
  return { word: statusWord(sub.status_name), detail: words(sub.status_name) };
}


export function newerJobId(submissions, startedMs) {
  let best = null;
  let bestAt = startedMs;
  const rows = Array.isArray(submissions) ? submissions : [];
  for (const row of rows) {
    if (!row) continue;
    const id = row.job_id || row.id;
    const created = Date.parse(row.created);
    if (!id || Number.isNaN(created) || created < startedMs || created < bestAt) continue;
    best = String(id);
    bestAt = created;
  }
  return best;
}

export function mountGradePanel(o) {
  let btn = o.button || null;
  const panel = o.panel;
  const submitDialog = document.getElementById('gradeSubmitDialog');
  const localBtn = submitDialog && submitDialog.querySelector('button.grade-local');
  const fileInput = submitDialog && submitDialog.querySelector('input.grade-file');
  const weaponsBtn = submitDialog && submitDialog.querySelector('button.grade-to-weapons');
  const gradeBtn = submitDialog && submitDialog.querySelector('button.grade-to-grading');
  const openSubmitBtn = panel.querySelector('button.grade-open-submit');
  const submitClose = submitDialog && submitDialog.querySelector('button.grade-submit-x');
  const status = panel.querySelector('.grade-status');
  const closeBtn = panel.querySelector('button.grade-x');
  function setStatus(view, running) {
    const word = view && view.word ? view.word : 'Idle';
    const detail = view && view.detail ? view.detail : 'No running grades.';
    const label = status && status.querySelector('.grade-status-text');
    if (label) label.textContent = word;
    else if (status) status.textContent = word;
    if (status) {
      status.setAttribute('data-running', running ? 'yes' : 'no');
      status.setAttribute('data-failure', word === 'Failure' ? 'yes' : 'no');
      status.title = detail;
      status.dataset.detail = detail;
    }
  }
  function gradeRunning(sub) {
    return !!(sub && sub.status_name && !terminal(sub.status_name));
  }
  let timer = 0;
  let busy = false;
  let loadToken = 0;
  const overview = { statusDoc: null, liveMap: null, submission: null };

  let feedbackHost = panel.querySelector('#grade-submission-limits');
  if (!feedbackHost) {
    feedbackHost = document.createElement('div');
    feedbackHost.className = 'submission-feedback';
    feedbackHost.id = 'grade-submission-limits';
    const budget = panel.querySelector('.grade-budget') || panel;
    budget.appendChild(feedbackHost);
  }
  for (const control of [localBtn, fileInput]) {
    if (control) control.setAttribute('aria-describedby', feedbackHost.id);
  }

  let availability = {};
  const feedback = mountFeedback({
    root: feedbackHost, tracks: ['module'],
    load: () => getSubmissionLimits('all', { cache: 'no-store', fresh: true }),
    onChange: (view, snapshot) => {
      availability = view;
      if (snapshot && snapshot.limits) {
        paintSubmissionsLeft(panel.ownerDocument, remainingFromSnapshot(snapshot),
          resetFromSnapshot(snapshot));
        paintBudget(panel.ownerDocument || panel, snapshot);
      }
      setBusy(busy);
    },
  });

  function setBusy(on) {
    busy = on;
    const blocked = on || !availability.module?.canSubmit;
    if (localBtn) localBtn.disabled = blocked;
    if (fileInput) fileInput.disabled = blocked;
  }

  function clearNote() {
    const note = panel.querySelector('.grade-read');
    if (!note) return;
    note.textContent = '';
    note.hidden = true;
  }

  function paintModules() {
    const root = panel.querySelector('.grade-modules');
    if (!root) return;
    const rows = moduleSections(overview.submission);
    root.replaceChildren();
    for (const row of rows) {
      const section = document.createElement('section');
      section.className = 'grade-module';
      section.setAttribute('data-code', row.code);
      const heading = document.createElement('h3');
      heading.className = 'grade-module-title';
      const code = document.createElement('span');
      code.className = 'grade-module-code';
      code.textContent = row.code;
      const name = document.createElement('span');
      name.className = 'grade-module-name';
      name.textContent = row.name;
      heading.append(code, name);
      section.setAttribute('data-broken', row.broken ? 'yes' : 'no');
      if (row.broken) {
        const broken = document.createElement('p');
        broken.className = 'grade-broken';
        broken.textContent = 'Failed functionality tests.';
        const none = document.createElement('p');
        none.className = 'grade-none';
        none.textContent = 'No results';
        section.append(heading, broken, none);
        root.appendChild(section);
        continue;
      }
      const list = document.createElement('ul');
      list.className = 'grade-vulns';
      const solved = row.vulns.filter(vuln => vuln.solved);
      if (!solved.length) {
        const empty = document.createElement('li');
        empty.className = 'grade-vuln';
        empty.setAttribute('data-resolved', 'no');
        empty.textContent = 'Nothing resolved';
        list.appendChild(empty);
      } else {
        for (const vuln of solved) {
          const item = document.createElement('li');
          item.className = 'grade-vuln';
          item.setAttribute('data-resolved', 'yes');
          const num = document.createElement('span');
          num.className = 'grade-vuln-n';
          num.textContent = String(vuln.n);
          item.appendChild(num);
          list.appendChild(item);
        }
      }
      section.append(heading, list);
      root.appendChild(section);
    }
  }

  function finishRead(token, sub, failed) {
    if (token !== loadToken) return;
    const note = panel.querySelector('.grade-read');
    if (failed) {
      const had = !!(overview.submission && overview.submission.status_name);
      if (had) {
        panel.setAttribute('data-grade-read', 'stale');
        clearNote();
      } else {
        panel.setAttribute('data-grade-read', 'failed');
        setStatus({ word: 'Failure', detail: 'The latest result could not be read.' }, false);
        clearNote();
      }
      paintModules();
      paintScores();
      return;
    }
    const pending = !!(sub && sub.status_name && !terminal(sub.status_name));
    panel.setAttribute('data-grade-read', pending ? 'grading' : 'ready');
    clearNote();
    if (sub) {
      overview.submission = sub;
      if (sub.status_name) setStatus(jobLine(sub), gradeRunning(sub));
    } else if (!overview.submission) {
      setStatus(IDLE, false);
    }
    paintProgress(panel, sub || overview.submission);
    paintModules();
    paintScores();
    const jobId = sub && (sub.job_id || sub.id);
    if (pending && jobId && !timer && !busy) {
      setBusy(true);
      poll(String(jobId));
    }
  }

  function refreshOverview() {
    const token = ++loadToken;
    const had = !!(overview.submission && overview.submission.status_name);
    if (!had) {
      panel.setAttribute('data-grade-read', 'reading');
      setStatus({ word: 'Waiting', detail: 'Reading the latest result.' }, false);
      clearNote();
    } else {
      panel.setAttribute('data-grade-read', 'refreshing');
      clearNote();
    }
    paintModules();
    Promise.all([
      loadStatus('./status.json'),
      loadLive(),
      getSubmissions(),
    ]).then(async (loaded) => {
      if (token !== loadToken) return;
      if (loaded[0]) overview.statusDoc = loaded[0];
      if (loaded[1]) overview.liveMap = loaded[1];
      const listed = loaded[2];
      if (!listed || listed.ok === false) {
        finishRead(token, null, true);
        return;
      }
      const latest = newestSubmission(listed.submissions);
      let sub = latest;
      if (latest && latest.job_id) {
        try {
          const detail = await getSubmission(latest.job_id);
          if (token !== loadToken) return;
          const row = detail && detail.submission;
          if (row && typeof row === 'object' && !Array.isArray(row)
              && (row.status_name || row.job_id)) sub = row;
        } catch (e) { /* the list row remains */ }
      }
      if (token !== loadToken) return;
      finishRead(token, sub || null, false);
    }).catch(() => {
      finishRead(token, null, true);
    });
  }

  function paint(sub, err) {
    const name = sub && sub.status_name;
    setStatus(err ? { word: 'Failure', detail: 'The grade could not be read.' } : jobLine(sub), !err && gradeRunning(sub));
    paintProgress(panel, err ? null : sub);
    if (name && terminal(name)) {
      notifySubmissionChange(panel.ownerDocument);
      setBusy(false);
    }
    if (sub) {
      loadToken++;
      overview.submission = sub;
      panel.setAttribute('data-grade-read',
        (name && !terminal(name)) ? 'grading' : 'ready');
      clearNote();
      paintModules();
    }
  }

  function stop() {
    window.clearTimeout(timer);
    timer = 0;
  }

  async function poll(jobId) {
    const res = await getSubmission(jobId);
    if (!res || res.ok === false && !res.submission) {
      if (res && res.error === 'timed out') {
        setStatus({ word: 'Waiting', detail: 'Still waiting for the grade job.' }, true);
        timer = window.setTimeout(() => poll(jobId), 1000);
        return;
      }
      setStatus({ word: 'Failure', detail: 'The grade job could not be read.' }, false);
      timer = 0;
      setBusy(false);
      return;
    }
    const sub = res.submission;
    paint(sub, null);
    if (!sub || !terminal(sub.status_name)) {
      timer = window.setTimeout(() => poll(jobId), 1000);
    } else {
      timer = 0;
    }
  }

  async function send(file) {
    if (file && !busy && availability.module?.state === 'loading') {
      setStatus({ word: 'Waiting', detail: 'Checking submission limits.' }, false);
      await feedback.refresh();
    }
    if (busy || !availability.module?.canSubmit) {
      if (file) {
        setStatus({ word: 'Failure', detail: busy
          ? 'A grade job is already in progress.'
          : 'The ZIP was not sent.' }, false);
        fileInput.value = '';
      }
      return;
    }
    if (o.isWide && !o.isWide()) return;
    if (file) fileInput.value = '';
    stop();
    loadToken++;
    panel.setAttribute('data-grade-read', 'submitting');
    clearNote();
    setBusy(true);
    setStatus({ word: 'Running', detail: 'Sending your modules.' }, true);
    paintProgress(panel, null);
    const started = Date.now();
    const payload = { kind: 'module' };
    if (file) payload.file = file;
    let res;
    try {
      res = await submit(payload);
    } catch (_) {
      res = { ok: false, error: 'The submission request could not be read.' };
    } finally {
      await feedback.refresh();
    }
    if (!res.ok || !res.job_id) {
      if (res && res.error === 'timed out') {
        const listed = await getSubmissions();
        const id = newerJobId(listed && listed.submissions, started);
        if (id) {
          paint({ status_name: 'QUEUED' }, null);
          poll(id);
          return;
        }
        setStatus({ word: 'Failure', detail: 'The request timed out before a job id came back.' }, false);
        setBusy(false);
        return;
      }
      setStatus({ word: 'Failure', detail: 'The grade job was not accepted.' }, false);
      setBusy(false);
      return;
    }
    paint({ status_name: (res.result && res.result.status_name) || 'QUEUED' }, null);
    poll(res.job_id);
  }

  function submitButtons() {
    return panel.querySelectorAll('button.grade-open-submit');
  }

  function paintConsoleLinks() {
    const where = typeof o.screen === 'function' ? o.screen() : 'other';
    if (weaponsBtn) weaponsBtn.hidden = where === 'weapons';
    if (gradeBtn) gradeBtn.hidden = where === 'grade';
  }

  function openSubmit() {
    if (!submitDialog) return;
    paintConsoleLinks();
    submitDialog.hidden = false;
    submitButtons().forEach(node => node.setAttribute('aria-expanded', 'true'));
    try { localBtn.focus(); } catch (e) { /* ignore */ }
  }

  function closeSubmit() {
    if (!submitDialog || submitDialog.hidden) return;
    submitDialog.hidden = true;
    submitButtons().forEach(node => node.setAttribute('aria-expanded', 'false'));
    try { (openSubmitBtn || closeBtn).focus(); } catch (e) { /* ignore */ }
  }

  function open() {
    if (o.isWide && !o.isWide()) return;
    refreshOverview();
    feedback.refresh();
    panel.hidden = false;
    if (btn) btn.setAttribute('aria-expanded', 'true');
    const liveClose = panel.querySelector('button.grade-x');
    try { (liveClose || openSubmitBtn || localBtn).focus(); } catch (e) { /* ignore */ }
  }

  function close() {
    closeSubmit();
    panel.hidden = true;
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function toggle() {
    if (panel.hidden) open(); else close();
  }

  function attach(button) {
    btn = button;
    btn.addEventListener('click', toggle);
  }

  const statusDialog = panel.querySelector('.grade-status-dialog');
  const statusDialogText = panel.querySelector('#gradeStatusDialogText');
  const statusDialogClose = panel.querySelector('button.grade-status-x');
  function openStatus() {
    if (!statusDialog || !status) return;
    if (statusDialogText) statusDialogText.textContent = status.dataset.detail || status.title || 'Idle.';
    statusDialog.hidden = false;
    status.setAttribute('aria-expanded', 'true');
    try { (statusDialogClose || statusDialog).focus(); } catch (e) { /* ignore */ }
  }
  function closeStatus() {
    if (!statusDialog || statusDialog.hidden) return;
    statusDialog.hidden = true;
    if (status) status.setAttribute('aria-expanded', 'false');
    try { status.focus(); } catch (e) { /* ignore */ }
  }
  if (status) status.addEventListener('click', openStatus);
  if (statusDialogClose) statusDialogClose.addEventListener('click', closeStatus);
  if (btn) attach(btn);
  closeBtn.addEventListener('click', close);
  document.querySelectorAll('button.grade-dash-plus').forEach(dashPlus => {
    dashPlus.addEventListener('click', (e) => {
      e.stopPropagation();
      openSubmit();
    });
  });
  panel.querySelectorAll('button.grade-counts-refresh').forEach(node => {
    node.addEventListener('click', () => feedback.refresh());
  });
  document.querySelectorAll('button.grade-limits-refresh').forEach(refreshLimits => {
    refreshLimits.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (refreshLimits.classList.contains('is-reading')) return;
      const icon = refreshLimits.querySelector('svg');
      const turn = new Promise(resolve => {
        let settled = false;
        const finish = () => { if (settled) return; settled = true; resolve(); };
        if (icon) icon.addEventListener('animationend', finish, { once: true });
        window.setTimeout(finish, 750);
      });
      refreshLimits.classList.add('is-reading');
      refreshLimits.setAttribute('aria-busy', 'true');
      try {
        await feedback.refresh();
      } finally {
        await turn;
        refreshLimits.classList.remove('is-reading');
        refreshLimits.removeAttribute('aria-busy');
      }
    });
  });
  submitButtons().forEach(node => node.addEventListener('click', openSubmit));
  if (submitClose) submitClose.addEventListener('click', closeSubmit);
  if (localBtn) localBtn.addEventListener('click', () => send(null));
  if (fileInput) fileInput.addEventListener('change', () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    send(file);
  });
  if (weaponsBtn) {
    weaponsBtn.addEventListener('click', () => {
      closeSubmit();
      if (typeof o.toWeapons === 'function') o.toWeapons();
    });
  }
  if (gradeBtn) {
    gradeBtn.addEventListener('click', () => {
      closeSubmit();
      if (typeof o.toGrade === 'function') o.toGrade();
    });
  }
  panel.ownerDocument.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !submitDialog || submitDialog.hidden) return;
    e.preventDefault();
    e.stopPropagation();
    closeSubmit();
  }, true);

  paintModules();
  feedback.refresh();
  refreshMenuScore(panel.ownerDocument || document);

  return {
    open, close, attach,
    isOpen: () => !panel.hidden,
  };
}
