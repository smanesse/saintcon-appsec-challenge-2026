/* SAINTCON 2026 — module help and the fleet introduction.
 *
 * The ? button opens a multi-page beginner guide for the module that is
 * open. Page one is the real service. Later pages are the normal controls.
 * Dismissal is still `localStorage['cockpit.help.seen.<CODE>']`.
 *
 * The tutorial is a separate fleet flag, `localStorage['cockpit.tutorial.seen']`.
 * Only the value `2` counts as seen. Dismiss writes `2` and does not remove
 * any other key. A profile that still has `1` sees the welcome again.
 * `openTutorial` is what a module page calls. It uses the parent cockpit
 * hook when that hook is there.
 *
 * No innerHTML: every string reaches the page through textContent.
 */

import { MODULE_HELP } from './help-pages.js';
import { mountTutorialDialog } from './tutorial-dialog.js';

const KEY = code => 'cockpit.help.seen.' + code;
const TUTORIAL_KEY = 'cockpit.tutorial.seen';
const PAGE_WORD = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];

export { MODULE_HELP };
export const HELP = MODULE_HELP;

export const TUTORIAL = [
  {
    title: 'Welcome',
    paragraphs: [
      'Your ship’s modules run locally. Edit their source in your checkout, rebuild to test, then submit to the remote grader.',
      'For A.L.I.E.N., submit aliens/<ship>/exploit.py scripts that retrieve and print a fresh flag during grading. Local captures do not score.',
    ],
    image: '../cockpit/combined/grading_station_plate.png',
    alt: 'The cockpit wide shot, with the grading station on the front lower-right fascia',
  },
  {
    title: 'Opening an instrument',
    paragraphs: [
      'Select a station to open its controls. Use ? for station help. The person button at the bottom right reopens this guide.',
    ],
    image: 'assets/KVS/plate.png',
    alt: 'Core Memory Banks, one of the cockpit instruments',
  },
  {
    title: 'Refit port',
    paragraphs: [
      'REFIT PORT has Start, Stop, Restart, and Rebuild & restart. Rebuild replaces the local service and clears container-only data; it does not submit a grade.',
      'Signal Harpoon uses the ship roster instead.',
      'A running local container lamp is green. A stopped one is red. Yellow while starting or stopping.',
    ],
    image: 'design/fix_upload_sketches/closed_140.png',
    alt: 'The refit port fitting',
  },
  {
    title: 'Status mast',
    paragraphs: [
      'Hover over the status mast, or focus it and press Enter. Click to pin the reading; Escape clears it.',
    ],
    image: 'assets/help/IPM/mast.png',
    alt: 'The status mast',
  },
  {
    title: 'New content',
    paragraphs: [
      'New content in the person menu means this copy is behind the published branch. The item does not download it. Pull from the remote git repository.',
    ],
    samples: [
      { kind: 'person', state: 'current', label: 'Up to date' },
      { kind: 'person', state: 'behind', label: 'New content', rings: true },
    ],
  },
  {
    title: 'Performance',
    paragraphs: [
      'The person button opens Performance settings. Those can turn the moving stars off, or wait to load a module until it is clicked.',
    ],
    samples: [
      { kind: 'performance' },
    ],
  },
  {
    title: 'Grading',
    paragraphs: [
      'The grading port is the brass fitting on the front lower-right fascia. It grades modules.',
      'Alien exploits are a separate track at the Signal Harpoon.',
      'Each track starts at 5. The grade panel and the corner show both. The Signal Harpoon count shows only on Submit to remote.',
    ],
    image: 'assets/grading-station.png',
    alt: 'The grading station, a brass port on the front lower-right fascia',
  },
  {
    title: 'Leaving',
    paragraphs: [
      'Close exits this guide; Back opens the previous page. Escape closes overlays, then returns to the cockpit.',
    ],
  },
];

function tutorialSeen() {
  try { return localStorage.getItem(TUTORIAL_KEY) === '2'; }
  catch (e) { return false; }
}

function rememberTutorial() {
  try { localStorage.setItem(TUTORIAL_KEY, '2'); }
  catch (e) { /* storage denied: the tutorial can show again */ }
}

/* Module pages import this. A parent hook wins and no event is sent.
 * Without that hook, the frame and the parent both hear cockpit-tutorial. */
export function openTutorial() {
  try {
    const parent = window.parent;
    if (parent && parent !== window && typeof parent.cockpitTutorial === 'function') {
      parent.cockpitTutorial();
      return;
    }
  } catch (e) { /* cross-origin parent */ }
  window.dispatchEvent(new CustomEvent('cockpit-tutorial'));
  try {
    const parent = window.parent;
    if (parent && parent !== window) {
      parent.dispatchEvent(new CustomEvent('cockpit-tutorial'));
      parent.postMessage({ type: 'cockpit-tutorial' }, '*');
    }
  } catch (e) { /* parent is not readable */ }
}

function seenHelp(code) {
  try { return localStorage.getItem(KEY(code)) === '1'; } catch (e) { return false; }
}
function rememberHelp(code) {
  try { localStorage.setItem(KEY(code), '1'); } catch (e) { /* storage denied */ }
}

/* o = { card, btn, nameOf(code) -> string, openCode() -> code|null }
 * card: #helpCard; btn: #bHelp. Presentation is mountTutorialDialog. */
export function createHelp(o) {
  const card = o.card, btn = o.btn;
  const doc = card.ownerDocument || globalThis.document;
  const dialog = mountTutorialDialog({
    card, btn,
    shade: doc.getElementById ? doc.getElementById('helpShade') : null,
    title: card.querySelector('.hp-title'),
    body: card.querySelector('.hp-body'),
    progress: card.querySelector('.hp-progress'),
    prev: card.querySelector('button.hp-prev'),
    next: card.querySelector('button.hp-next'),
    done: card.querySelector('button.gotit'),
    close: card.querySelector('button.hp-x'),
    pages: code => {
      const h = HELP[code];
      return h && h.pages && h.pages.length ? h.pages : null;
    },
    heading: (code, page) => o.nameOf(code) + ' \u2014 ' + page.title,
    progressText: (_code, page, i) => 'Page ' + (PAGE_WORD[i] || String(i + 1)) + '. ' + page.title,
    onDismiss: rememberHelp,
    tokenFromButton: () => o.openCode(),
    reopen: 'stay',
  });
  let autoDone = false;
  return {
    auto(code) {
      if (autoDone || !code) return;
      autoDone = true;
      if (!seenHelp(code)) dialog.open(code);
    },
    open: code => dialog.open(code),
    close: dismissed => dialog.close(dismissed),
    isOpen: () => dialog.isOpen(),
    reset() { dialog.close(false); autoDone = false; },
    seen: seenHelp,
  };
}

/* o = { card:#tutorialCard, btn:#bTutorial }
 * Same dialog engine as createHelp. Content and the fleet flag stay here. */
export function createTutorial(o) {
  const card = o.card, btn = o.btn;
  const doc = card.ownerDocument || globalThis.document;
  const dialog = mountTutorialDialog({
    card, btn,
    shade: doc.getElementById ? doc.getElementById('tutorialShade') : null,
    title: card.querySelector('.tu-title'),
    body: card.querySelector('.tu-body'),
    progress: card.querySelector('.tu-progress'),
    prev: card.querySelector('button.tu-back'),
    next: card.querySelector('button.tu-next'),
    done: null,
    close: card.querySelector('button.tu-x'),
    pages: () => TUTORIAL,
    heading: (_token, page) => page.title,
    progressText: null,
    onDismiss: rememberTutorial,
    defaultToken: 'tutorial',
    finishOnNext: true,
    reopen: 'restart',
  });
  return {
    open: () => dialog.open('tutorial'),
    close: dismissed => dialog.close(dismissed),
    auto() { if (!tutorialSeen()) dialog.open('tutorial'); },
    isOpen: () => dialog.isOpen(),
    seen: tutorialSeen,
  };
}
