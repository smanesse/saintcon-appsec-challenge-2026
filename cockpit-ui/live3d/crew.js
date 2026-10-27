/* SAINTCON 2026 — HARNESS CHROME on the cockpit sill.
 *
 * Who you are, whether the scoring uplink exists, whether organizers are
 * accepting returns, and how many challenges the harness currently lists.
 * Diegetic-or-chrome: this paints `#crew` in the open person menu.  It does not
 * cover the nine modules, the masts, or the STANDINGS plate, and it does not
 * write into `leaderboard.json`.
 *
 * NO innerHTML.  Every string reaches the page through textContent.
 * NO fail().  A dead bridge is fail-safe copy on the strip; the ship still
 * flies.  Same-origin `/api/harness` + `/api/challenges` only — the browser
 * never calls HARNESS_URL, and there is no shared api.js to import.
 *
 * Cadence matches leaderboard.js / mast.js (POLL_MS 5 s, STALE_MS 4 min)
 * without importing either file.  `setCrew` is the analogue of `setStatus`:
 * inject a document, skip the network, repaint so every copy-table row is
 * screenshottable without a live harness.
 */

const POLL_MS = 5000;
const STALE_MS = 4 * 60 * 1000;

/* DEV / ADMIN SWITCH (owner-fixes T1b).  The same explicit opt-in the rest of the
 * cockpit uses: the cockpit's own URL must carry `?dev=1`.  Nothing is stored and
 * nothing else turns it on.  For a player the strip shows who they are and whether
 * returns are open, and NOTHING else: no admin UPDATE chip, no commit subjects, no
 * environment-variable names, no challenge list. */
const DEV = /(^|[?&])dev=1(&|$)/.test(String(location.search || '').slice(1));

function el(id) {
  return document.getElementById(id);
}

function whitelist(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const c of list) {
    if (!c || typeof c !== 'object') continue;
    out.push({
      id: c.id == null ? '' : String(c.id),
      name: c.name == null ? '' : String(c.name),
      path: c.challenge_path == null
        ? (c.path == null ? '' : String(c.path))
        : String(c.challenge_path),
    });
  }
  return out;
}

/* Hover text for a signed-in player: what the strip already says, in words.  It
 * deliberately does NOT list challenge names (that would reveal the list and its
 * size). */
function listTitle(rows, closed) {
  if (closed) return 'Returns are closed by organizers.';
  return rows.length ? 'Returns are open.' : 'No returns can be sent yet.';
}

async function read(url) {
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error('http ' + r.status);
  const d = await r.json();
  if (!d || typeof d !== 'object') throw new Error('bad');
  return d;
}

export function bootCrew() {
  const state = {
    answered: false,
    uplinkDead: false,
    configured: null,
    loggedIn: false,
    username: '',
    submissionsOpen: null,
    haveReturns: false,
    challenges: [],
    aliens: [],
    challengeCount: 0,
    lastOkAt: 0,
    forceStale: false,
    line: ['UPLINK ...', '', ''],
    stale: false,
    lastListTitle: '',
    updates: null,
  };

  let injected = false;
  let inflight = false;
  let pollTimer = null;

  function snapshot() {
    const ch = [];
    for (const c of state.challenges) {
      ch.push({ id: c.id, name: c.name, path: c.path });
    }
    return {
      configured: state.configured,
      loggedIn: state.loggedIn,
      username: state.username,
      submissionsOpen: state.submissionsOpen,
      challengeCount: state.challengeCount,
      challenges: ch,
      line: [state.line[0], state.line[1], state.line[2]],
      stale: state.stale,
    };
  }

  function computeStale(now) {
    if (state.forceStale) return true;
    if (!state.lastOkAt) return false;
    return (now - state.lastOkAt) > STALE_MS;
  }

  const WHO_PX_PER_S = 24;
  const WHO_PAUSE_MS = 2000;

  function scrollWho(whoEl, name) {
    let run = whoEl.querySelector('.who-run');
    if (!run) {
      run = document.createElement('span');
      run.className = 'who-run';
      whoEl.replaceChildren(run);
    }
    run.textContent = name || '';
    const width = whoEl.clientWidth;
    const extra = run.offsetWidth - width;
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!name || width < 1 || extra <= 1 || still) {
      whoEl.classList.remove('is-scroll');
      run._whoKey = '';
      run.getAnimations().forEach(a => a.cancel());
      return;
    }
    const key = String(extra);
    if (run._whoKey === key && run.getAnimations().length) return;
    run.getAnimations().forEach(a => a.cancel());
    run._whoKey = key;
    whoEl.classList.add('is-scroll');
    const travel = (extra / WHO_PX_PER_S) * 1000;
    const total = WHO_PAUSE_MS + travel + WHO_PAUSE_MS + travel;
    const hold = WHO_PAUSE_MS / total;
    const leg = travel / total;
    run.animate([
      { transform: 'translateX(0px)', offset: 0 },
      { transform: 'translateX(0px)', offset: hold },
      { transform: 'translateX(' + (-extra) + 'px)', offset: hold + leg },
      { transform: 'translateX(' + (-extra) + 'px)', offset: hold + leg + hold },
      { transform: 'translateX(0px)', offset: 1 },
    ], { duration: total, iterations: Infinity, easing: 'linear' });
  }

  function paint() {
    const whoEl = el('crewWho');
    const sepEl = el('crewSep');
    const retEl = el('crewRet');
    const nEl = el('crewN');
    const uEl = el('crewUpd');
    const crewEl = el('crew');
    if (!whoEl || !sepEl || !retEl || !nEl || !crewEl) return;

    const now = Date.now();
    const stale = computeStale(now);
    let who = '', ret = '', n = '', upd = '', title = '', tone = '';

    if (!state.answered) {
      who = 'UPLINK ...';
      tone = 'dead';
    } else if (state.uplinkDead) {
      who = 'UPLINK DEAD';
      title = DEV ? 'bridge did not answer'
        : 'The scoring service did not answer, so returns cannot be sent right now.';
      tone = 'dead';
    } else if (!state.configured) {
      who = 'HARNESS NOT CONFIGURED';
      title = DEV ? 'set HARNESS_URL on the console'
        : 'Scoring is not connected on this machine. Ask an organizer.';
      tone = 'dead';
    } else if (!state.loggedIn) {
      who = 'NOT SIGNED IN';
      title = 'Not signed in. Use identify to sign in and send returns.';
    } else {
      who = state.username ? state.username : 'CREW';
      if (state.haveReturns) {
        const open = state.submissionsOpen === true;
        ret = open ? 'RETURNS OPEN' : 'RETURNS CLOSED';
        tone = open ? '' : 'closed';
        /* Presence / names only — no N SHIPS score-ratio chrome. */
        const count = state.challenges.length;
        n = count > 0 ? 'MODULES' : '';
        /* No campaign door here: PKT (Signal Harpoon) is reached only by
         * clicking its own module in the cockpit.  Owner-fixes T1a. */
        title = (state.username ? 'Signed in as ' + state.username + '. ' : 'Signed in. ')
          + listTitle(state.challenges, !open);
      } else {
        ret = 'RETURNS UNKNOWN';
        tone = 'dead';
        title = (state.username ? 'Signed in as ' + state.username + '. ' : 'Signed in. ')
          + (state.lastListTitle || 'Could not check whether returns are open.');
      }
    }

    if (stale) n = n ? (n + ' STALE') : 'STALE';

    if (DEV && state.updates && state.updates.enabled !== false && state.updates.isRepo !== false
        && state.updates.updateAvailable) {
      upd = 'UPDATE';
      const subs = (state.updates.commits || []).map((c) => c.subject || c.sha).slice(0, 4);
      title = (title ? title + '\n' : '') + (subs.length ? subs.join('\n') : 'release update available');
    }

    scrollWho(whoEl, who);
    retEl.textContent = ret;
    nEl.textContent = n;
    if (uEl) {
      uEl.textContent = upd;
      uEl.title = upd ? 'Click to apply release update (confirmation required)' : '';
    }
    sepEl.hidden = !(ret || n || upd);
    crewEl.title = title;
    retEl.classList.toggle('closed', tone === 'closed');
    retEl.classList.toggle('dead', tone === 'dead');

    state.line = [who, ret, n, upd];
    state.stale = stale;
  }

  function applyHarness(h) {
    state.configured = !!h.configured;
    state.loggedIn = !!h.loggedIn;
    state.username = typeof h.username === 'string' ? h.username : '';
    state.uplinkDead = false;
    state.answered = true;
    state.lastOkAt = Date.now();
    state.forceStale = false;
  }

  function applyChallenges(c) {
    if (!c || c.ok !== true) return false;
    /* Never paint RETURNS OPEN from a document whose ok is false; this
     * branch only runs when ok is true. */
    state.challenges = whitelist(c.challenges);
    state.aliens = whitelist(c.aliens);
    state.challengeCount = state.challenges.length;
    state.submissionsOpen = c.submissions_open === true;
    state.haveReturns = true;
    state.lastListTitle = listTitle(
      state.challenges, state.submissionsOpen === false);
    return true;
  }

  async function refreshUpdates() {
    if (!DEV) return;                       // player notice is branch-notice.js; this chip applies
    try {
      const u = await read('/api/updates');
      state.updates = u && typeof u === 'object' ? u : null;
    } catch (e) {
      /* updates optional — leave last good */
    }
  }

  async function onUpdateClick(ev) {
    if (ev) ev.preventDefault();
    const u = state.updates;
    if (!u || !u.updateAvailable) return;
    const n = u.behind != null ? u.behind : ((u.commits && u.commits.length) || '?');
    const ok = window.confirm(
      'Apply ' + n + ' release update(s) to the challenge checkout?\n'
      + 'This changes local files. Auto-apply is disabled in the cockpit.');
    if (!ok) return;
    try {
      const r = await fetch('/api/updates/apply', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Bridge-Update-Apply': '1',
        },
        body: '{}',
      });
      const d = await r.json();
      const res = (d && d.result) || d || {};
      if (res.ok && res.applied > 0) {
        window.alert('Applied ' + res.applied + ' commit(s)'
          + (res.method ? ' via ' + res.method : '') + '.');
      } else if (res.ok && res.upToDate) {
        window.alert('Already up to date.');
      } else {
        window.alert('Update failed: ' + (res.message || res.error || 'unknown'));
      }
    } catch (e) {
      window.alert('Update request failed.');
    }
    await refreshUpdates();
    paint();
  }

  async function refresh() {
    if (injected) return;
    try {
      const h = await read('/api/harness');
      applyHarness(h);
      if (h.configured === true) {
        try {
          const c = await read('/api/challenges');
          if (!applyChallenges(c) && !state.haveReturns) {
            state.lastListTitle = 'Could not check whether returns are open.';
          }
        } catch (e) {
          if (!state.haveReturns) state.lastListTitle = 'Could not check whether returns are open.';
        }
      } else {
        state.haveReturns = false;
        state.submissionsOpen = null;
        state.challenges = [];
        state.aliens = [];
        state.challengeCount = 0;
        state.lastListTitle = '';
      }
      await refreshUpdates();
    } catch (e) {
      state.answered = true;
      state.uplinkDead = true;
    }
    paint();
  }

  function tick() {
    if (injected || inflight) return;
    if (document.visibilityState === 'hidden') return;
    inflight = true;
    refresh().finally(() => { inflight = false; });
  }

  function crew() {
    return snapshot();
  }

  function setCrew(doc) {
    injected = true;
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    const d = (doc && typeof doc === 'object') ? doc : {};
    state.answered = true;
    state.forceStale = !!d.stale;
    state.lastOkAt = d.stale ? (Date.now() - STALE_MS - 1) : Date.now();

    if (doc == null || d.unreachable || d.dead) {
      state.uplinkDead = true;
      if (typeof d.username === 'string') state.username = d.username;
      paint();
      return snapshot();
    }

    state.uplinkDead = false;
    state.configured = !!d.configured;
    state.loggedIn = !!(d.loggedIn || d.logged_in);
    state.username = typeof d.username === 'string' ? d.username : '';

    const open = d.submissionsOpen !== undefined
      ? d.submissionsOpen
      : d.submissions_open;
    const listed = Array.isArray(d.challenges);
    if (d.ok === false && !listed) {
      state.haveReturns = false;
      state.challenges = [];
      state.challengeCount = 0;
      state.submissionsOpen = null;
      state.lastListTitle = 'Could not check whether returns are open.';
    } else if (listed || open === true || open === false) {
      state.challenges = whitelist(d.challenges);
      state.challengeCount = typeof d.challengeCount === 'number'
        ? d.challengeCount
        : state.challenges.length;
      state.submissionsOpen = open === true;
      state.haveReturns = true;
      state.lastListTitle = listTitle(
        state.challenges, state.submissionsOpen === false);
    } else {
      state.haveReturns = false;
      state.challenges = [];
      state.challengeCount = 0;
      state.submissionsOpen = null;
      state.lastListTitle = '';
    }

    paint();
    return snapshot();
  }

  /* The admin UPDATE chip exists only under `?dev=1`; for a player there is no
   * element to click.  Applying is still never automatic (confirm first, and the
   * bridge keeps apply disabled). */
  if (DEV) {
    const host = el('crew');
    if (host && !el('crewUpd')) {
      const chip = document.createElement('span');
      chip.id = 'crewUpd';
      host.appendChild(chip);
    }
    const updEl = el('crewUpd');
    if (updEl) updEl.addEventListener('click', onUpdateClick);
  }

  paint();
  const whoBox = el('crewWho');
  if (whoBox && typeof ResizeObserver !== 'undefined') {
    const watch = new ResizeObserver(() => {
      const run = whoBox.querySelector('.who-run');
      if (run) scrollWho(whoBox, run.textContent);
    });
    watch.observe(whoBox);
  }
  tick();
  pollTimer = setInterval(tick, POLL_MS);
  addEventListener('visibilitychange', tick);
  addEventListener('pageshow', tick);

  return { crew, setCrew };
}
