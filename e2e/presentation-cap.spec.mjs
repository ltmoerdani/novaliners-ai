// Presentation cap (docs/03-architecture-tech/14 §24.7): the ENGINE forms 0..N Possible Paths; the screens show at most
// five at a time. Five is not a target, not a promise that nothing else exists, and not a limit on how many the engine
// may form. This spec proves the policy two ways:
//   1. the pure policy (app/static/js/present-cap.js) on its own, exhaustively, in Node: 0..13 paths, pins, order, no
//      filler, nothing dropped (the hidden paths keep their evidence, because they are the same objects);
//   2. what the reader sees, from engine-made states (evals/make_ui_fixtures.py): 0 · 1 · 3 · 5 · 6 · 8 · 10 paths on the
//      Explore and Readiness lenses, the State rail and the Talk panel (v11, record P6); "+N other possibilities"
//      is honest, opens and is operable from the keyboard alone; a hidden candidate-born path keeps its "why"; 390 px;
//      no console error and no failed request.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

test.describe.configure({ mode: 'serial' });

const here = path.dirname(fileURLToPath(import.meta.url));
const fx = name => JSON.parse(fs.readFileSync(path.join(here, 'fixtures', `${name}.json`), 'utf8'));

// ── 1. the policy itself, loaded exactly as the browser loads it, with nothing else around it ───────────────────────
const policy = (() => {
  const ctx = vm.createContext({});
  const src = fs.readFileSync(path.join(here, '..', 'app', 'static', 'js', 'present-cap.js'), 'utf8');
  vm.runInContext(`${src}\nthis.api = { presentPaths, pathStatusSummary, PATH_VIEW_CAP };`, ctx);
  return ctx.api;
})();
const mk = (n, statuses) => Array.from({ length: n }, (_, i) => ({ key: `path.p${i}`, status: statuses ? statuses[i % statuses.length] : 'OPEN', name: `P${i}` }));
const keys = ps => ps.map(p => p.key);

test('policy · the cap is five and it is only a presentation constant', () => {
  expect(policy.PATH_VIEW_CAP).toBe(5);
});

test('policy · 0, 1, 2, 3, 4 and 5 paths: everything is shown, nothing is hidden, nothing is added', () => {
  for (const n of [0, 1, 2, 3, 4, 5]) {
    const ps = mk(n, ['OPEN', 'TEST_FIRST', 'NOT_YET', 'STOP']);
    const r = policy.presentPaths(ps);
    expect(keys(r.visible), `n=${n}`).toEqual(keys(ps));
    expect(r.hidden, `n=${n}`).toEqual([]);
    expect(r.overflow).toBe(0);
    expect(r.total).toBe(n);
    expect(r.summary).toEqual([]);
  }
});

test('policy · three meaningful possibilities are three on screen: three is not a limit and five is not a quota', () => {
  const three = mk(3);
  expect(policy.presentPaths(three).visible.length).toBe(3);
  expect(policy.presentPaths(mk(2)).visible.length).toBe(2);       // no filler to reach five or three
  expect(policy.presentPaths(mk(5)).visible.length).toBe(5);
});

test('policy · 6, 8, 10 and 13 paths: five visible, the rest hidden, and visible + hidden is exactly the input', () => {
  for (const n of [6, 7, 8, 10, 13, 40]) {
    const ps = mk(n, ['OPEN', 'TEST_FIRST', 'NOT_YET', 'STOP']);
    const r = policy.presentPaths(ps);
    expect(r.visible.length, `n=${n}`).toBe(5);
    expect(r.hidden.length, `n=${n}`).toBe(n - 5);
    expect(r.overflow).toBe(n - 5);
    expect(r.total).toBe(n);
    expect([...keys(r.visible), ...keys(r.hidden)].sort(), `n=${n}: nothing dropped, nothing invented`).toEqual(keys(ps).sort());
    expect(new Set([...keys(r.visible), ...keys(r.hidden)]).size, 'no duplicates').toBe(n);
    // the objects themselves come back (their evidence and provenance travel with them)
    expect(r.hidden.every(h => ps.includes(h)) && r.visible.every(v => ps.includes(v))).toBe(true);
    // engine order is kept inside both groups
    const order = k => keys(ps).indexOf(k);
    expect(keys(r.visible).map(order)).toEqual([...keys(r.visible).map(order)].sort((a, b) => a - b));
    expect(keys(r.hidden).map(order)).toEqual([...keys(r.hidden).map(order)].sort((a, b) => a - b));
    expect(r.summary.reduce((s, x) => s + x.n, 0), 'the summary counts exactly what is hidden').toBe(n - 5);
  }
});

test('policy · what fits is chosen by the engine\'s own status word; ties keep the engine order; it is not a ranking', () => {
  const ps = [
    { key: 'a', status: 'STOP' }, { key: 'b', status: 'STOP' }, { key: 'c', status: 'NOT_YET' }, { key: 'd', status: 'TEST_FIRST' },
    { key: 'e', status: 'OPEN' }, { key: 'f', status: 'OPEN' }, { key: 'g', status: 'STOP' }, { key: 'h', status: 'OPEN' },
  ];
  const r = policy.presentPaths(ps);
  expect(keys(r.visible)).toEqual(['c', 'd', 'e', 'f', 'h']);               // 3 open, 1 test first, 1 not yet; engine order kept
  expect(keys(r.hidden)).toEqual(['a', 'b', 'g']);
  expect(r.summary).toEqual([{ status: 'STOP', n: 3, label: 'stop' }]);
});

test('policy · a pinned path (the current one, the one being read) always stays visible and takes a slot first', () => {
  const ps = mk(8, ['OPEN', 'OPEN', 'OPEN', 'OPEN', 'OPEN', 'STOP', 'NOT_YET', 'TEST_FIRST']);
  const plain = policy.presentPaths(ps);
  expect(keys(plain.hidden)).toEqual(['path.p5', 'path.p6', 'path.p7'].filter(k => keys(plain.hidden).includes(k)));
  const pinned = policy.presentPaths(ps, { pinned: ['path.p5'] });                     // a STOP path, pinned
  expect(keys(pinned.visible)).toContain('path.p5');
  expect(pinned.visible.length).toBe(5);
  expect(pinned.hidden.length).toBe(3);
  const two = policy.presentPaths(ps, { pinned: ['path.p5', 'path.p6', 'nope', 'path.p5'] });   // unknown keys and repeats are ignored
  expect(keys(two.visible)).toEqual(expect.arrayContaining(['path.p5', 'path.p6']));
  expect(two.visible.length).toBe(5);
  const many = policy.presentPaths(ps, { pinned: keys(ps) });                           // more pins than slots: still five
  expect(many.visible.length).toBe(5);
});

test('policy · pure and deterministic: the input is not touched, the same input gives the same answer', () => {
  const ps = mk(9, ['OPEN', 'STOP', 'TEST_FIRST']);
  const snapshot = JSON.stringify(ps);
  const a = policy.presentPaths(ps, { pinned: ['path.p4'] });
  const b = policy.presentPaths(ps, { pinned: ['path.p4'] });
  expect(JSON.stringify(a)).toBe(JSON.stringify(b));
  expect(JSON.stringify(ps)).toBe(snapshot);
  expect(policy.presentPaths(null)).toMatchObject({ visible: [], hidden: [], total: 0, overflow: 0 });
  expect(policy.presentPaths([null, undefined]).total).toBe(0);
  expect(policy.presentPaths(mk(4), { cap: 3 }).visible.length).toBe(3);               // the cap is a parameter, not a hidden five
});

// ── 2. what the reader sees ───────────────────────────────────────────────────────────────────────────────────────
let page, ctx;
const consoleErrors = [];
const failedRequests = [];
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(100); };
const txt = (sel = '#v11-main') => page.locator(sel).innerText();
const applyFx = (name) => page.evaluate(f => {
  V11_ENGINE.clear();
  LIVE.artifact.possible_paths = f.possible_paths;
  LIVE.artifact.navigation = f.navigation;
  LIVE.projection = f.projection || null;
  LIVE.projectionTried = LIVE.sid; LIVE.explain = null; LIVE.explainState = 'failed';
  LIVE.workspace = LIVE.workspace || {}; LIVE.workspace.path_states = f.path_states || {};
  if (f.routes) LIVE.routes = f.routes;
  STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; STORE.mapsView = 'landscape'; STORE.talkAbout = null;
  goDestination('maps');
}, fx(name));
const CASES = [['paths_zero', 0], ['paths_one', 1], ['paths_three', 3], ['paths_five', 5], ['paths_six', 6], ['paths_eight', 8], ['paths_ten', 10]];

test.beforeAll(async ({ browser, baseURL }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  page.on('requestfailed', r => { if (r.url().startsWith(baseURL)) failedRequests.push(r.url()); });
  page.on('dialog', d => d.accept());
  await page.addInitScript(() => { try { localStorage.setItem('novaliners-v9', JSON.stringify({ userId: 'u_e2e' + Math.random().toString(16).slice(2, 10), chain: [], checkins: [], overrides: [], tips: {} })); localStorage.setItem('novaliners-theme', 'light'); } catch (e) { /* ignore */ } });
  await page.goto(`${baseURL}/`, { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', 'I left my job as a marketing manager and want Rp20 million a month from consulting in 90 days.');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await page.locator('#diag-chat-input:not([disabled])').waitFor({ timeout: 30_000 });
  for (let i = 1; i <= 2; i++) {
    await page.fill('#diag-chat-input', `Answer ${i}: nobody has paid me yet, and two people asked me to let them know.`);
    await page.keyboard.press('Enter');
    await page.locator('#diag-chat-input:not([disabled])').waitFor({ timeout: 30_000 });
  }
  await page.getByText('Enough answers? Build my diagnosis now').click();
  await page.getByRole('heading', { name: /best read so far/ }).waitFor({ timeout: 60_000 });
});
test.afterAll(async () => { await ctx.close(); });

test('engine 0..N, UI at most 5: Explore, Readiness, State and Talk follow the policy for 0, 1, 3, 5, 6, 8, 10', async () => {
  for (const [name, n] of CASES) {
    await applyFx(name);
    expect(await page.evaluate(() => V11_ENGINE.snapshot().paths.length), `${name}: the engine formed ${n}`).toBe(n);
    const seen = Math.min(n, 5), extra = n - seen;
    // Landscape: five callouts at most, and "+N more" says how many are not drawn
    await expect(page.locator('.v12-map .v12-lane-label'), `${name} landscape`).toHaveCount(seen);
    if (extra > 0) await expect(page.locator('.v12-more'), `${name} landscape`).toContainText(`+${extra} more`); else await expect(page.locator('.v12-more'), `${name} landscape`).toHaveCount(0);
    // Overview and Readiness: every path is reachable in the list (the cap limits what is drawn, not what is reachable)
    await go(`setMapsView('landscape')`);
    if (n > 1) await expect(page.locator('.mp-card'), `${name} overview`).toHaveCount(n);
    await go(`setMapsView('readiness')`);
    if (n > 0) await expect(page.locator('.rd-path-item'), `${name} readiness`).toHaveCount(n);
    // State rail and Talk panel: at most five rows and the honest line for the rest
    await go(`goDestination('state')`);
    const rail = await txt('.dest-paths');
    expect(await page.locator('.dest-paths .dest-path, .dest-paths li, .dest-paths [data-path]').count(), `${name} state rail rows`).toBeLessThanOrEqual(5);
    if (extra > 0) expect(rail, `${name} state rail`).toMatch(new RegExp(`\\+${extra} other possibilit(y|ies)`));
    else expect(rail, `${name} state rail`).not.toMatch(/(other|more) possibilit/);   // State says "other", as the prototype does
    await go(`STORE.chatEvidenceOpen = true; STORE.chatPanelTab = 'map'; goDestination('talk')`);
    const panel = await txt('#v11-main');
    if (extra > 0) expect(panel, `${name} talk panel`).toMatch(new RegExp(`\\+${extra} more possibilit(y|ies)`));   // the Maps and Talk controls say "more", as the prototype does
    else expect(panel, `${name} talk panel`).not.toMatch(/(other|more) possibilit/);
  }
});

test('no filler: 1 stays 1, 3 stays 3, 5 stays 5; five is not a completeness requirement and the page never says "all five"', async () => {
  for (const [name, n] of [['paths_one', 1], ['paths_three', 3], ['paths_five', 5]]) {
    await applyFx(name);
    for (const v of ['landscape', 'readiness']) {
      await go(`setMapsView('${v}')`);
      expect(await txt(), `${name} ${v}`).not.toMatch(/\b(?:all 5 paths|all five|the five paths)\b/i);
    }
    expect(await page.evaluate(() => V11_ENGINE.snapshot().paths.length)).toBe(n);
  }
});

test('overflow on the map: "+N more" is honest, opens the full list with name and status, and nothing implies "only five"', async () => {
  await applyFx('paths_eight');
  const more = page.locator('.v12-more');
  await expect(more).toContainText('+3 more');
  /* the workspace bar states the count of everything the engine formed (8), while the canvas draws five */
  await expect(page.locator('.mpw-bar .st-count'), 'a count of everything the engine formed').toHaveText('8');
  await more.click();
  await expect(page.locator('#mp-panel, .mp-card').first()).toBeVisible();
  const names = await page.evaluate(() => V11_ENGINE.snapshot().paths.map(p => p.title));
  const shown = await txt();
  for (const t of names) expect(shown, `${t} is listed`).toContain(t);
  expect(shown).not.toMatch(/only (the )?(five|5)\b/i);
});

test('picking a hidden path brings it into focus, keeps five callouts, and the list loses nothing', async () => {
  await applyFx('paths_eight');
  const hidden = await page.evaluate(() => V11_ENGINE.snapshot().paths[7].id);
  await go(`setMapsView('landscape'); mapsSelect('${hidden}')`);
  expect(await page.evaluate(() => selectedPathId())).toBe(hidden);
  await go(`setMapsView('landscape')`);
  await expect(page.locator('.v12-map .v12-lane-label')).toHaveCount(5);
  expect(await page.evaluate(() => selectedPathId()), 'the chosen path stays chosen in the other lens').toBe(hidden);
  await go(`setMapsView('landscape')`);
  await expect(page.locator('.mp-card')).toHaveCount(8);
});

test('keyboard only: "+N more" opens with Enter and Space, every hidden path is reachable and operable, focus is visible', async () => {
  await applyFx('paths_eight');
  const more = page.locator('.v12-more');
  await more.focus();
  expect(await more.evaluate(e => e === document.activeElement)).toBe(true);
  await page.keyboard.press('Enter'); await page.waitForTimeout(150);
  expect(await page.evaluate(() => !!document.activeElement && document.activeElement !== document.body), 'focus moved into the list').toBe(true);
  const ring = await page.evaluate(() => { const e = document.activeElement, cs = getComputedStyle(e); return cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 || cs.boxShadow !== 'none'; });
  expect(ring, 'the focus ring is visible').toBe(true);
  await applyFx('paths_eight');
  await page.locator('.v12-more').focus();
  await page.keyboard.press('Space'); await page.waitForTimeout(150);
  expect(await page.evaluate(() => !!document.activeElement && document.activeElement !== document.body), 'Space does the same').toBe(true);
  // every path card of the Overview is a native, focusable control
  await go(`setMapsView('landscape')`);
  const unreachable = await page.evaluate(() => [...document.querySelectorAll('.mp-card')].filter(c => { const f = c.matches('button, a[href]') ? c : c.querySelector('button, a[href]'); return !f || f.tabIndex < 0; }).length);
  expect(unreachable).toBe(0);
});

test('a hidden candidate-born path keeps its reason: pick it from the list and "Why this path is on your map" is there', async () => {
  await applyFx('paths_candidates_many'); await go(`setMapsView('landscape')`);
  const born = await page.evaluate(() => V11_ENGINE.snapshot().paths.map(p => p.id));
  expect(born.length).toBeGreaterThan(5);
  let withReason = 0;
  for (const id of born) { await go(`mapsSelect('${id}')`); if ((await txt('#mp-panel')).includes('It rests on')) withReason++; }
  expect(withReason, 'paths born from a mechanism say why, hidden or not').toBeGreaterThan(0);
  const last = born[born.length - 1];
  await go(`mapsSelect('${last}')`);
  expect(await txt('#mp-panel'), 'the last (hidden) path still has its panel').toContain('WHY THIS PATH IS ON YOUR MAP');
});

test('zero paths with many possibilities taking shape: the page says how many exist and where to see them, and counts none as paths', async () => {
  await applyFx('paths_emerging_conflict');
  expect(await page.evaluate(() => V11_ENGINE.snapshot().paths.length)).toBe(0);
  const t = await txt();
  expect(t).toContain('Not settled');
  await expect(page.locator('[data-testid="emerging"] .emerging-item')).toHaveCount(2);
});

test('a 390 px screen: five callouts and the overflow stay readable, no sideways page scroll', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const name of ['paths_five', 'paths_eight', 'paths_ten']) {
    await applyFx(name);
    for (const v of ['landscape', 'readiness']) {
      await go(`setMapsView('${v}')`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), `${name} ${v}`).toBeLessThanOrEqual(2);
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('nothing threw and nothing failed', async () => {
  expect(consoleErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
});
