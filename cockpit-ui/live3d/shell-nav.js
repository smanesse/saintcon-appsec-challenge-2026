/* SAINTCON 2026 — COCKPIT SHELL NAVIGATION (T1a).
 *
 * One small, module-agnostic thing: how a player LEAVES a close-up (or the
 * standings overlay) and how the browser's own Back/Forward buttons take part.
 * app.js owns the dive; this file owns the way out.
 *
 * THE RULES
 * ---------
 *  - ONE history entry per open.  Opening from the wide shot pushes exactly one
 *    marker entry ({ckpNav:'module'|'board', code}).  The URL never changes, so
 *    nothing about leaderboard/auth/dev query flags is touched.
 *  - Every way out CONSUMES that entry.  X, Escape, the bottom back button and
 *    the test hooks all end in app.js `left()` / `closeBoard()`, which call
 *    `closed()` here; if the marker is still the current entry that is a
 *    `history.back()`.  The browser Back button gets there first (popstate) and
 *    then there is nothing left to consume.  So cycles never inflate history:
 *    the entry above the base is pushed, popped, and the next open overwrites
 *    the forward entry.
 *  - Reload on a marker entry lands on the wide cockpit: the marker is cleared
 *    at boot (the old document's open module cannot be resumed).
 *  - Forward onto a marker entry re-opens that module through the normal
 *    openModule() dive.  If it cannot (something is moving / another overlay is
 *    up) it steps straight back, so the page and the entry never disagree.
 *  - A running FILE RETURN is not silently abandoned: a leave request first
 *    asks (non-blocking card, "Stay here" / "Leave anyway").  The job is
 *    server-side, so leaving does not cancel it; reopening the module and
 *    opening its panel again picks it up (refit.js re-attaches to the last
 *    submission when the panel opens); the card says exactly that.  A declined browser Back re-pushes the marker, so the entry
 *    stack is exactly as it was.
 *  - No focus traps.  The card takes focus on "Stay here" (Escape also means
 *    stay); it is not modal and Tab is never captured.
 *
 * No innerHTML: every string reaches the page through textContent.
 */
const KEY = 'ckpNav';

const mark = (kind, code) => { const s = {}; s[KEY] = kind; s.code = code || null; return s; };
const isMark = s => !!(s && typeof s === 'object' && s[KEY]);

/* o = {
 *   isOpen()      -> 'module' | 'board' | null
 *   isClosing()   -> true while the way-out animation is already running
 *   current()     -> the open module code, or null
 *   closeNow(kind)   perform the close (app.js closeModule / closeBoard)
 *   reopen(state)    -> true if the marker's module/board could be opened
 *   busy()        -> null, or a short noun phrase for what leaving would interrupt
 *   closeBtn, card   elements }
 */
export function createShellNav(o) {
  const card = o.card;
  const qs = sel => card.querySelector(sel);
  const stayBtn = qs('button.stay'), leaveBtn = qs('button.leave');
  let pendingBack = false, pendingTimer = null;
  let asking = null;                       // {kind} while the leave card is up

  /* A reload (or Forward into an old document) arrives on a marker entry whose
   * close-up no longer exists.  Make it an ordinary wide-shot entry. */
  if (isMark(history.state)) {
    try { history.replaceState(null, '', location.href); } catch (e) { /* ignore */ }
  }

  function expectBack() {
    pendingBack = true;
    clearTimeout(pendingTimer);
    pendingTimer = setTimeout(() => { pendingBack = false; }, 700);
  }
  function popped() { pendingBack = false; clearTimeout(pendingTimer); }

  function hideAsk(returnFocus) {
    if (!asking) return;
    asking = null;
    card.hidden = true;
    if (returnFocus && o.closeBtn && o.closeBtn.offsetParent !== null) {
      try { o.closeBtn.focus(); } catch (e) { /* ignore */ }
    }
  }
  function ask(kind, what) {
    asking = { kind };
    qs('.lc-title').textContent = 'A ' + what + ' is still in progress.';
    qs('.lc-msg').textContent =
      'Leaving closes this view. The grader keeps working on it. Reopen this '
      + 'module and open the same panel again to see the result.';
    card.hidden = false;
    try { stayBtn.focus(); } catch (e) { /* ignore */ }
  }

  /* A way out that a PLAYER asked for (X, Escape, bottom back button). */
  function request() {
    const kind = o.isOpen();
    if (!kind || o.isClosing()) return;
    const what = o.busy();
    if (what) { ask(kind, what); return; }
    o.closeNow(kind);
  }
  /* Escape: dismiss the leave card first, otherwise it is a leave request. */
  function escape() {
    if (asking) { hideAsk(true); return; }
    request();
  }

  stayBtn.addEventListener('click', () => hideAsk(true));
  leaveBtn.addEventListener('click', () => {
    const a = asking;
    hideAsk(false);
    if (a && o.isOpen() && !o.isClosing()) o.closeNow(o.isOpen());
  });
  if (o.closeBtn) o.closeBtn.addEventListener('click', request);

  /* app.js calls these two. */
  function opened(kind, code) {
    try {
      if (isMark(history.state)) history.replaceState(mark(kind, code), '', location.href);
      else history.pushState(mark(kind, code), '', location.href);
    } catch (e) { /* history unavailable: the close-up still works, Back just will not close it */ }
  }
  function closed() {
    hideAsk(false);
    if (isMark(history.state)) {
      expectBack();
      history.back();                      // consume the entry we pushed
    }
  }

  addEventListener('popstate', () => {
    popped();
    const s = history.state;
    const kind = o.isOpen();
    if (isMark(s)) {
      if (!kind) {                         // Forward onto a marker: re-open cleanly
        if (!o.reopen(s)) { expectBack(); history.back(); }
      }
      return;                              // marker while something is open: already consistent
    }
    if (!kind || o.isClosing()) return;    // nothing to close / already closing
    const what = o.busy();
    if (what) {
      /* Back already moved the history; put the entry back so the stack is
       * exactly what it was, then ask. */
      try { history.pushState(mark(kind, o.current()), '', location.href); } catch (e) { /* ignore */ }
      ask(kind, what);
      return;
    }
    o.closeNow(kind);
  });

  return {
    request, escape, opened, closed,
    settling: () => pendingBack,
    asking: () => !!asking,
  };
}
