/* SAINTCON 2026 — harness login / register / logout.
 *
 * Same-origin /api only.  The browser never talks to the cloud harness and
 * never stores a token.  Track 01 can replace the fetch calls without
 * touching the forms.
 *
 * NO innerHTML / outerHTML / insertAdjacentHTML / document.write.
 * Every string reaches the page through textContent.
 */
const $ = id => document.getElementById(id);

function goCockpit() {
  location.assign('/');
}

function authOut(msg, cls) {
  const out = $('authOut');
  out.classList.remove('err', 'ok');
  if (!msg) {
    out.hidden = true;
    out.textContent = '';
    return;
  }
  out.hidden = false;
  if (cls) out.classList.add(cls);
  out.textContent = msg;
}

function showState(name) {
  $('stUnconfigured').hidden = name !== 'unconfigured';
  $('stGuest').hidden = name !== 'guest';
  $('stIn').hidden = name !== 'in';
}

function setTab(which) {
  $('tabLogin').classList.toggle('on', which === 'login');
  $('tabRegister').classList.toggle('on', which === 'register');
  $('loginForm').hidden = which !== 'login';
  $('registerForm').hidden = which !== 'register';
}

function dropToken(d) {
  if (d && Object.prototype.hasOwnProperty.call(d, 'token')) delete d.token;
  return d;
}

async function readJson(r) {
  try {
    return dropToken(await r.json());
  } catch (e) {
    throw new Error('transport error: ' + e);
  }
}

function transportOf(d, r) {
  const why = (d && (d.error || d.message)) || ('HTTP ' + r.status);
  return 'transport error: ' + why;
}

function render(h) {
  dropToken(h);
  $('guestUrl').textContent = h.url || '';
  $('inUrl').textContent = h.url || '';
  $('inUser').textContent = h.username || '?';
  if (!h.configured) {
    showState('unconfigured');
    authOut('');
    return;
  }
  if (h.loggedIn) {
    showState('in');
    authOut('');
    return;
  }
  showState('guest');
}

async function loadHarness() {
  try {
    const r = await fetch('/api/harness');
    const d = await readJson(r);
    /* configured is a boolean from the bridge.  A 502 / ok:false body is
       transport, not the unconfigured copy (that copy is env-unset only). */
    if (!r.ok || d.ok === false || typeof d.configured !== 'boolean') {
      showState('guest');
      authOut('> ' + transportOf(d, r), 'err');
      return;
    }
    render(d);
  } catch (e) {
    showState('guest');
    const msg = String(e);
    authOut('> ' + (msg.startsWith('transport error:') ? msg : ('transport error: ' + e)), 'err');
  }
}

async function doAuth(url, body, btn) {
  if (btn) btn.disabled = true;
  authOut('> contacting harness …');
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await readJson(r);
    if (!r.ok) {
      authOut('> ' + transportOf(d, r), 'err');
      return;
    }
    if (d.ok && d.loggedIn) {
      if (String(url).indexOf('/register') !== -1) {
        try { sessionStorage.setItem('cockpit.tutorial.arm', '1'); }
        catch (err) { /* storage denied: the cockpit still checks the seen key */ }
      }
      goCockpit();
      return;
    }
    if (d.ok) {
      await loadHarness();
    } else {
      authOut('> ' + (d.message || d.error || 'authentication failed'), 'err');
    }
  } catch (e) {
    const msg = String(e);
    authOut('> ' + (msg.startsWith('transport error:') ? msg : ('transport error: ' + e)), 'err');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function doLogout(btn) {
  if (btn) btn.disabled = true;
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
  } catch (e) { /* clear locally regardless */ }
  location.assign('/');
}

$('bEnter').addEventListener('click', goCockpit);
{
  const back = $('bBack');
  if (back) back.addEventListener('click', goCockpit);
}
addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  goCockpit();
});

$('tabLogin').addEventListener('click', () => setTab('login'));
$('tabRegister').addEventListener('click', () => setTab('register'));

const lf = $('loginForm');
lf.addEventListener('submit', e => {
  e.preventDefault();
  doAuth('/api/auth/login', {
    username: lf.username.value, password: lf.password.value,
  }, lf.querySelector('button[type="submit"]'));
});

const rf = $('registerForm');
rf.addEventListener('submit', e => {
  e.preventDefault();
  doAuth('/api/auth/register', {
    name: rf.name.value, username: rf.username.value, password: rf.password.value,
  }, rf.querySelector('button[type="submit"]'));
});

$('bLogout').addEventListener('click', () => doLogout($('bLogout')));

await loadHarness();
