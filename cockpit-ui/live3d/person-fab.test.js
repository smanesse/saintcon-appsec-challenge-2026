import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const notice = readFileSync(new URL('./branch-notice.js', import.meta.url), 'utf8');
const menu = readFileSync(new URL('./person-menu.js', import.meta.url), 'utf8');

test('the person button slides left while a tutorial or module guide is open', () => {
  assert.match(html, /#personDock\{position:fixed;right:16px;bottom:16px/);
  assert.match(html, /#personDock\{[^}]*transition:right \.55s/);
  assert.match(html, /body:has\(#tutorialCard:not\(\[hidden\]\)\) #personDock,\s*body:has\(#helpCard:not\(\[hidden\]\)\) #personDock\{right:calc\(100% - 64px\)/);
  assert.match(html, /@media \(prefers-reduced-motion:reduce\)\{#personDock,#personMenu,#branchPanel\{transition:none\}\}/);
  assert.doesNotMatch(html, /body:has\(#tutorialCard:not\(\[hidden\]\)\) #personFab\{[^}]*display:\s*none/);
  assert.doesNotMatch(html, /body:has\(#tutorialCard:not\(\[hidden\]\)\) #personDock\{[^}]*display:\s*none/);
});

test('a slide does not dismiss the menu, the cog, or the rings', () => {
  assert.match(html, /#personDock\{[^}]*width:48px;height:48px/);
  assert.doesNotMatch(html, /body:has\(#personMenu:not\(\[hidden\]\)\) #personDock\{width/);
  assert.match(html, /<button id="personFab"[\s\S]*?<svg viewBox="0 0 32 32"/);
  assert.match(notice, /ripple\.hidden = false/);
  assert.match(notice, /ensureFollow\(\)/);
  assert.doesNotMatch(menu, /tutorialCard/);
  assert.doesNotMatch(menu, /helpCard/);
});

test('the icon stays at the bottom, fully inside the card', () => {
  assert.match(html, /#personMenu\{position:absolute;[^}]*right:-8px;bottom:-8px/);
  assert.match(html, /#personMenu\{[^}]*padding:10px 10px 64px/);
  assert.match(html, /body:has\(#tutorialCard:not\(\[hidden\]\)\) #personMenu,\s*body:has\(#helpCard:not\(\[hidden\]\)\) #personMenu\{\s*right:auto;left:-8px/);
  assert.match(html, /#personMenu\[hidden\]\{display:none/);
  assert.doesNotMatch(html, /margin-top:-48px/);
  assert.match(html, /M8\.6 12\.4C8\.6 6\.8/);
});

test('sign-out is opposite the icon, not beside Up to date', () => {
  const menu = html.slice(html.indexOf('id="personMenu"'), html.indexOf('id="branchPanel"'));
  const foot = menu.slice(menu.indexOf('class="menu-foot"'));
  assert.match(menu, /id="branchNotice"/);
  assert.doesNotMatch(foot, /id="branchNotice"/);
  assert.match(foot, /id="bAuth"[\s\S]*id="crew"/);
  assert.match(foot, /class="auth-label">Sign in</);
  assert.match(foot, /class="auth-out"/);
  assert.doesNotMatch(foot, />Sign out</);
  assert.match(html, /#personMenu \.menu-foot\{[^}]*height:48px/);
  assert.match(html, /body:has\(#tutorialCard:not\(\[hidden\]\)\) #personMenu \.menu-foot #bAuth,\s*body:has\(#helpCard:not\(\[hidden\]\)\) #personMenu \.menu-foot #bAuth\{order:2\}/);
  assert.match(html, /#bTutorial\{margin-top:9px;margin-bottom:9px\}/);
  assert.match(html, /#personMenu button\{[^}]*height:32px/);
  assert.match(html, /#personMenu #bAuth\[data-mode="out"\]\{width:32px;height:32px/);
});
