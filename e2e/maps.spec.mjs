// Maps destination (record P5b; doc 08 §6.2, doc 10 §6.2, §4; prototype behavior.mjs): one workspace with two lenses
// over one set of paths and one selection, 0..N paths with a presentation cap of five, the engine's four requirement
// words kept apart, UNKNOWN never shown as missing, a STOP that says who stopped it, the possibilities that are only
// taking shape in their own card. Two kinds of input:
//   - snapshots put in place through the seam (V11_ENGINE.set), the way the prototype's own checks do it;
//   - payloads built by the real engine (fixtures/*.json, evals/make_ui_fixtures.py) put through the real adapter.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test.describe.configure({ mode: 'serial' });

const here = path.dirname(fileURLToPath(import.meta.url));
const fx = name => JSON.parse(fs.readFileSync(path.join(here, 'fixtures', `${name}.json`), 'utf8'));

let page, ctx;
const consoleErrors = [];
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(80); };
const txt = (sel = '#v11-main') => page.locator(sel).innerText();

/* a snapshot of the page's own, mutated in the page, then the seam */
const withSnap = (mut) => go(`
  const snap = JSON.parse(JSON.stringify(V11_ENGINE.snapshot()));
  (${mut.toString()})(snap);
  V11_ENGINE.set(v11MapKey(), snap);
  STORE.mapsSelBy[v11MapKey()] = null; STORE.mapsSelDefaultBy[v11MapKey()] = null; STORE.mapsView = 'landscape'; goDestination('maps');`);
const reset = () => go(`V11_ENGINE.clear(); STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; STORE.mapsView = 'landscape'; goDestination('maps')`);
/* a path of the shape the prototype's checks use */
const PATH_SRC = `(i, status = 'NOT YET', extra = {}) => Object.assign({ id: 'p' + i, title: 'Path number ' + i + ' with a deliberately long title that must not break the layout', status_display: status,
  lifecycle: status === 'STOP' ? 'STOPPED' : 'OPEN', stop_source: status === 'STOP' ? 'evidence' : null,
  requirements: [{ id: 'r1', label: 'Requirement one of path ' + i, satisfaction: 'UNKNOWN' }], evidence_ids: [], provenance: '', trail: [], next_move: null }, extra)`;
const withPaths = (n, statuses, nextmove) => withSnap(new Function('s', `const mk = ${PATH_SRC}; s.paths = Array.from({ length: ${n} }, (_, i) => mk(i + 1, ${JSON.stringify(statuses || [])}[i] || 'NOT YET')); s.nextmove = ${JSON.stringify(nextmove || null)};`));
/* an engine-built payload through the real adapter */
const applyFx = (name) => page.evaluate(f => {
  V11_ENGINE.clear();
  LIVE.artifact.possible_paths = f.possible_paths;
  LIVE.artifact.navigation = f.navigation;
  LIVE.projection = f.projection || null;
  LIVE.projectionTried = LIVE.sid; LIVE.explain = null; LIVE.explainState = 'failed';
  LIVE.workspace = LIVE.workspace || {}; LIVE.workspace.path_states = f.path_states || {};
  if (f.routes) LIVE.routes = f.routes;
  STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; STORE.mapsView = 'landscape';
  goDestination('maps');
}, fx(name));
const lens = (v) => go(`setMapsView('${v}')`);

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  await page.addInitScript(() => { try { localStorage.setItem('novaliners-v9', JSON.stringify({ userId: 'u_e2e' + Math.random().toString(16).slice(2, 10), chain: [], checkins: [], overrides: [], tips: {} })); localStorage.setItem('novaliners-theme', 'light'); } catch (e) { /* ignore */ } });
});
test.afterAll(async () => { await ctx.close(); });

test('00 · a real (mock-LLM) map to work on', async ({ baseURL }) => {
  await page.goto(`${baseURL}/`, { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', 'I left my job as a marketing manager and want Rp20 million a month from consulting in 90 days.');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  for (let i = 1; i <= 2; i++) {
    await page.fill('#diag-chat-input', `Answer ${i}: nobody has paid me yet, and two people asked me to let them know.`);
    await page.keyboard.press('Enter');
    await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  }
  await page.getByText('Enough answers? Build my diagnosis now').click();
  await expect(page.getByRole('heading', { name: /best read so far/ })).toBeVisible({ timeout: 60_000 });
});

/* ── lenses ───────────────────────────────────────────────────────────────────────────────────────────── */
test('01 · two lenses (Explore, Readiness), each with the question it answers visible; the active question is spoken in a caption', async () => {
  await go(`V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); goDestination('maps')`);
  await expect(page.locator('.v11-view-switch button .v11-lens-name')).toHaveText(['Explore', 'Readiness']);
  await expect(page.locator('.v11-view-switch button .v11-lens-q')).toHaveText(['Where can I go, and what should I know about each path?', 'What does each path need?']);
  for (const q of await page.locator('.v11-view-switch button .v11-lens-q').all()) await expect(q).toBeVisible();
  await lens('readiness');
  await expect(page.locator('.v11-lens-caption')).toContainText('Readiness: What does each path need?');
  await lens('landscape');
});

test('02 · the map opens flat; every drawn path is a named, native, pressable lane label; the corridor line offers no click target of its own beyond the path', async () => {
  await go(`goDestination('maps')`);
  await expect(page.locator('#v12-map')).toHaveAttribute('data-mode', '2d');   // 3D removed (owner, 18 Oct; doc 15 GAP-05)
  const n = await page.evaluate(() => Math.min(V11_ENGINE.snapshot().paths.length, 5));
  const lanes = page.locator('.v12-map .v12-lane-label');
  await expect(lanes).toHaveCount(n);
  for (const c of await lanes.all()) {
    expect(await c.getAttribute('role')).toBe('button');
    expect(((await c.getAttribute('aria-label')) || '').trim().length).toBeGreaterThan(5);
    expect(await c.getAttribute('aria-pressed')).not.toBeNull();
  }
  await expect(page.locator('.v12-map svg g[style*="cursor:pointer"]')).not.toHaveCount(0);   // the design's lane cards, stations and stop ends carry the pointer (v11.dc @HEAD)
  /* The design's contract (behavior.mjs "no stray focus stops"): pressable things on the
     canvas are the lane labels (and shared requirement nodes when drawn) — nothing else. */
  await expect(page.locator('.v12-map [role="button"][tabindex]:not(.v12-lane-label):not(.v12-shared)')).toHaveCount(0);
});

test('03 · keyboard on the flat map: Tab reaches a lane label, Enter and Space select, focus stays on the chosen path, the ring is visible', async () => {
  await go(`goDestination('maps')`);
  const ids = await page.evaluate(() => V11_ENGINE.snapshot().paths.map(p => p.id));
  await page.locator('.v12-map .v12-lane-label').first().focus();
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.activeElement.classList.contains('v12-lane-label'))).toBe(true);
  await page.locator('.v12-map .v12-lane-label').first().focus();
  const ring = await page.evaluate(() => { const cs = getComputedStyle(document.activeElement); return { style: cs.outlineStyle, width: parseFloat(cs.outlineWidth) }; });
  expect(ring.style).toBe('solid'); expect(ring.width).toBeGreaterThanOrEqual(2);
  await page.keyboard.press('Enter'); await page.waitForTimeout(200);
  expect(await page.evaluate(() => selectedPathId(V11_ENGINE.snapshot()))).toBe(ids[0]);
  expect(await page.evaluate(() => document.activeElement.getAttribute('data-v12-path'))).toBe(ids[0]);
  await page.locator('.v12-map .v12-lane-label').nth(1).focus(); await page.keyboard.press('Space'); await page.waitForTimeout(200);
  expect(await page.evaluate(() => selectedPathId(V11_ENGINE.snapshot()))).toBe(ids[1]);
  await expect(page.locator('.v12-map .v12-lane-label[aria-pressed="true"]')).toHaveCount(1);
});

test('04 · the same path stays selected through a re-render, the lane labels are named and in the tab order', async () => {
  await go(`goDestination('maps')`);
  const target = await page.evaluate(() => V11_ENGINE.snapshot().paths[0].id);
  await go(`mapsSelect('${target}')`);
  await expect(page.locator('#v12-map')).toHaveAttribute('data-mode', '2d');   // 3D removed (owner, 18 Oct; doc 15 GAP-05)
  await page.locator('.v12-map .v12-lane-label').first().focus();
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.activeElement.classList.contains('v12-lane-label'))).toBe(true);
  expect(await page.evaluate(() => selectedPathId(V11_ENGINE.snapshot()))).toBe(target);
  await expect(page.locator(`.v12-lane-label[data-v12-path="${target}"][aria-pressed="true"]`)).toHaveCount(1);
  for (const l of await page.locator('.v12-lane-label').all()) { expect(await l.getAttribute('tabindex')).toBe('0'); expect((await l.getAttribute('aria-label') || '').length).toBeGreaterThan(5); }
  // the map draws order, never dates or cycle labels or invented steps
  const svgText = await page.locator('.v12-map svg').first().evaluate(n => n.textContent);
  for (const bad of ['Cycle 2', 'Write the one-page offer']) expect(svgText).not.toContain(bad);
});

test('05 · the lens switch by keyboard keeps focus on the lens you chose and never traps Tab', async () => {
  await go(`goDestination('maps')`);
  await page.locator('.v11-view-switch button', { hasText: 'Readiness' }).focus();
  await page.keyboard.press('Enter'); await page.waitForTimeout(150);
  expect(await page.evaluate(() => !!document.activeElement.closest('.v11-view-switch') && document.activeElement.textContent.includes('Readiness'))).toBe(true);
  let outside = 0;
  for (let i = 0; i < 60; i++) { await page.keyboard.press('Tab'); if (await page.evaluate(() => !document.getElementById('v11-main').contains(document.activeElement))) outside++; }
  expect(outside).toBeGreaterThan(0);
  await lens('landscape');
});

/* ── 0 / 1 / N paths ──────────────────────────────────────────────────────────────────────────────────── */
const ZERO = [['INSUFFICIENT_INFORMATION', 'not enough information'], ['NO_APPLICABLE_PATH', 'No path applies to what is on record'],
  ['EVIDENCE_CONFLICT', 'The evidence conflicts'], ['EVALUATION_UNAVAILABLE', 'We could not evaluate your map'], ['LEGACY_ARTIFACT', 'needs a fresh look']];
for (const [kind, phrase] of ZERO) {
  test(`06 · zero paths (${kind}): its own explanation in every lens, no engine vocabulary, no "0 of 0"`, async () => {
    await withSnap(new Function('s', `s.paths = []; s.zero = { kind: '${kind}', detail: '', missing: [] };`));
    for (const v of ['landscape', 'readiness']) {
      await lens(v);
      const t = await txt();
      expect(t, `${kind} in ${v}`).toContain(phrase);
      expect(t).not.toMatch(/\bengine\b|0 of 0/);
    }
    await reset();
  });
}
test('07 · zero paths with no reason on record says so and does not guess one', async () => {
  await withSnap(s => { s.paths = []; s.zero = null; s.state = { why_we_think_so: [], uncertain: [] }; });
  const t = await txt();
  expect(t).toContain('No reason for this is on record');
  expect(t).not.toContain('Nothing applies right now');
  await reset();
});
test('08 · a map with no state at all is "not enough information", derived from there being no state', async () => {
  await withSnap(s => { s.paths = []; s.zero = null; s.state = null; });
  expect(await txt()).toContain('not enough information');
  await reset();
});
for (const n of [1, 2, 5, 6, 9]) {
  test(`09 · ${n} path(s): at most five drawn, "+N more" says the rest, every path has a card and is reachable`, async () => {
    await withPaths(n);
    for (const n2 of [1]) { void n2; }   // one mode: the flat map (3D removed, owner 18 Oct)
    await expect(page.locator('.v12-lane-label')).toHaveCount(Math.min(n, 5));
    if (n > 5) {
      await expect(page.locator('.v12-more')).toHaveCount(1);
      await expect(page.locator('.v12-more')).toContainText(`+${n - 5} more`);
      expect(await txt('#mp-list')).toContain(`+${n - 5} more possibilit`);
      await go(`mapsOpenMore(); document.querySelector('.mp-card[data-path="p${n}"]').click()`);
      await expect(page.locator(`.v12-lane-label[data-v12-path="p${n}"]`)).toHaveCount(1);   // a hidden path that is chosen takes a slot
      await expect(page.locator('.v12-lane-label')).toHaveCount(5);
    } else {
      // Design @HEAD: with every path drawn, the map IS the list — the overflow card
      // list exists only for paths the canvas does not draw (v11.dc mapsMoreHtml).
      await expect(page.locator('.v12-more')).toHaveCount(0);
      await expect(page.locator('.mp-card')).toHaveCount(0);
    }
  });
}
test('10 · "+N more" is a focusable button that opens the full list and moves focus into it', async () => {
  await withPaths(7);
  await page.locator('.v12-more').focus();
  await page.keyboard.press('Enter'); await page.waitForTimeout(100);
  expect(await page.evaluate(() => document.activeElement.tagName)).toBe('SUMMARY');
  expect(await page.evaluate(() => document.getElementById('mp-more').open)).toBe(true);
  await reset();
});
test('11 · a path with no requirement and no move still has a callout and can be chosen on the map', async () => {
  await withSnap(s => { s.paths = [
    { id: 'bare', title: 'Bare path', status_display: 'NOT YET', lifecycle: 'OPEN', stop_source: null, requirements: [], evidence_ids: [], provenance: '', trail: [], next_move: null },
    { id: 'full', title: 'Full path', status_display: 'OPEN', lifecycle: 'OPEN', stop_source: null, requirements: [{ id: 'r', label: 'Something', satisfaction: 'PRESENT' }], evidence_ids: [], provenance: '', trail: [], next_move: null }]; s.nextmove = null; });
  await expect(page.locator('.v12-map .v12-lane-label')).toHaveCount(2);
  await page.locator('.v12-map .v12-lane-label[data-v12-path="bare"]').focus();
  await page.keyboard.press('Enter'); await page.waitForTimeout(80);
  expect(await page.evaluate(() => selectedPathId())).toBe('bare');
  await reset();
});

/* ── no ranking, grounded focus, one selection ────────────────────────────────────────────────────────── */
test('12 · "In focus" only follows the path the current move is recorded against, never the first OPEN path or the order', async () => {
  /* Design @HEAD: focus lives on the canvas card (a mint ring + an "IN FOCUS" status line) and
     the "Current move" badge — the old aside ("CURRENTLY IN FOCUS") and the card list are gone. */
  await withPaths(3, ['OPEN', 'OPEN', 'TEST FIRST'], null);
  await expect(page.locator('.v12-lane-label.is-focus')).toHaveCount(0);
  await expect(page.locator('.v12-here-badge')).toHaveCount(0);
  await expect(page.locator('.mp-tag')).toHaveCount(0);
  expect(await txt()).not.toContain('CURRENTLY IN FOCUS');
  await withSnap(s => {
    s.paths.forEach((p, i) => { p.status_display = ['OPEN', 'OPEN', 'TEST FIRST'][i] || 'NOT YET'; p.lifecycle = 'OPEN'; });
    s.nextmove = { type: 'ACTION', title: 'Do the thing', path_id: 'p2' };
    s.paths[1].next_move = { type: 'ACTION', title: 'Do the thing' };   // the move marker reads the path's own record
  });
  await expect(page.locator('.v12-lane-label.is-focus[data-v12-path="p2"]')).toHaveCount(1);
  await expect(page.locator('.v12-lane-label[data-v12-path="p2"]')).toContainText(/IN FOCUS/i);
  await expect(page.locator('.v12-here-badge')).toContainText(/Current move/i);
  await go(`const s = V11_ENGINE.snapshot(); s.paths.reverse(); goDestination('maps')`);
  await expect(page.locator('.v12-lane-label.is-focus[data-v12-path="p2"]')).toHaveCount(1);
  await reset();
});
test('13 · no ranking or recommendation vocabulary in any lens of any sample snapshot', async ({ baseURL }) => {
  const p = await ctx.newPage();
  await p.goto(`${baseURL}/?demo=1`, { waitUntil: 'networkidle' });
  for (const who of ['dimas', 'rina', 'arif', 'bayu']) for (const v of ['landscape', 'readiness']) {
    await p.evaluate(([w, l]) => { setPersona(w); STORE.mapsView = l; goDestination('maps'); STORE.mapsView = l; renderScreen('maps'); }, [who, v]);
    const t = (await p.locator('#v11-main').innerText()).toLowerCase();
    for (const bad of ['recommended', 'best path', 'top pick', 'confidence', 'score:', '% match']) expect(t, `${who}/${v}`).not.toContain(bad);
  }
  await p.close();
});
test('14 · one selection: the chosen path is the same in both lenses, going and coming back; the old Overview lens resolves to Explore', async () => {
  await go(`V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); STORE.mapsSelBy = {}; goDestination('maps'); mapsSelect('productized-audit')`);
  for (const v of ['overview', 'readiness', 'landscape', 'readiness', 'overview', 'landscape']) {   // 'overview' is the old name: it lands on Explore
    await lens(v);
    expect(await page.evaluate(() => selectedPathId()), `after ${v}`).toBe('productized-audit');
    if (v === 'readiness') await expect(page.locator('.rd-path-item.active')).toHaveAttribute('data-path', 'productized-audit');
    if (v === 'overview' || v === 'landscape') {
      await expect(page.locator('.v11-view-switch button[aria-pressed="true"]')).toContainText('Explore');
      await expect(page.locator('.v12-lane-label[aria-pressed="true"]')).toHaveAttribute('data-v12-path', 'productized-audit');   // the canvas card is the pressed control (design @HEAD)
    }
  }
});
test('15 · Readiness always has a subject: with no choice it is the first path, stored, and never worded as a recommendation', async () => {
  /* Design @HEAD: the default subject is stored but no longer carries the "Shown first by
     default" disclosure line (mapsDefaultLine is retired there); orientation is the canvas
     card + the readiness list. The never-a-recommendation wording stays. */
  await go(`V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; goDestination('maps'); setMapsView('readiness')`);
  const first = await page.evaluate(() => V11_ENGINE.snapshot().paths[0].id);
  expect(await page.evaluate(() => selectedPathId())).toBe(first);
  await expect(page.locator('.rd-path-item[aria-current="true"]')).toHaveAttribute('data-path', first);
  const note = await txt('#mp-panel');
  for (const bad of ['recommended', 'best', 'top pick', 'winner']) expect(note.toLowerCase()).not.toContain(bad);
  for (const v of ['landscape', 'overview', 'readiness', 'landscape']) { await lens(v); expect(await page.evaluate(() => selectedPathId())).toBe(first); }
  // an explicit choice replaces the default everywhere
  const ids = await page.evaluate(() => V11_ENGINE.snapshot().paths.map(p => p.id));
  await lens('readiness'); await go(`readinessSelect('${ids[1]}')`);
  expect(await page.evaluate(() => selectedPathId())).toBe(ids[1]);
  for (const v of ['landscape', 'readiness']) { await lens(v); expect(await page.evaluate(() => selectedPathId())).toBe(ids[1]); }
});
test('16 · HERE or the goal stay selected: Readiness shows the first path without overwriting them; zero paths store nothing', async () => {
  await go(`V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; goDestination('maps'); mapsSelect('start'); setMapsView('readiness')`);
  expect(await page.evaluate(() => STORE.mapsSelBy[v11MapKey()])).toBe('start');
  expect(await page.evaluate(() => selectedPathId())).toBeNull();
  await expect(page.locator('.rd-path-item[aria-current="true"]')).toHaveCount(1);
  await lens('landscape');
  expect(await page.evaluate(() => STORE.mapsSelBy[v11MapKey()])).toBe('start');
  await withSnap(s => { s.paths = []; s.zero = { kind: 'NO_APPLICABLE_PATH', detail: '', missing: [] }; });
  await lens('readiness');
  expect(await page.evaluate(() => STORE.mapsSelBy[v11MapKey()] ?? null)).toBeNull();
  expect(await txt()).toContain('No path applies to what is on record');
  await reset();
});

/* ── Readiness words ──────────────────────────────────────────────────────────────────────────────────── */
test('17 · Readiness: PRESENT, PARTIAL, UNKNOWN, ABSENT and "does not apply" are separate groups; the denominator leaves out what does not apply', async () => {
  await withSnap(s => { s.paths = [{ id: 'x', title: 'Mixed path', status_display: 'TEST FIRST', lifecycle: 'OPEN', stop_source: null, evidence_ids: [], provenance: '', trail: [], next_move: null,
    requirements: [{ id: 'a', label: 'Req present', satisfaction: 'PRESENT' }, { id: 'b', label: 'Req partial', satisfaction: 'PARTIAL' }, { id: 'c', label: 'Req unknown', satisfaction: 'UNKNOWN' },
      { id: 'd', label: 'Req absent', satisfaction: 'ABSENT' }, { id: 'e', label: 'Req not applicable', satisfaction: 'ABSENT', applicable: false }] }]; });
  await lens('readiness');
  const group = async (title) => page.locator('.rd-group', { has: page.locator('.rd-group-title', { hasText: new RegExp(title, 'i') }) }).innerText();
  expect(await group('Confirmed')).toContain('Req present');
  expect(await group('Partly shown')).toContain('Req partial');
  expect(await group('Not known yet')).toContain('Req unknown');
  expect(await group('Not known yet')).not.toContain('Req partial');
  expect(await group('Not in place')).toContain('Req absent');
  expect(await group('Does not apply')).toContain('Req not applicable');
  expect(await group('Not in place')).not.toContain('Req not applicable');
  expect(await txt('.rd-counts')).toContain('1 of 4');   // the denominator leaves out the not-applicable one (design: .rd-counts in .rd-header-card)
  await reset();
});
test('18 · Readiness: no requirements never reads "0 of 0"; every requirement not applicable reads "no requirements apply"', async () => {
  await withSnap(s => { s.paths = [{ id: 'z', title: 'No requirements', status_display: 'NOT YET', lifecycle: 'OPEN', stop_source: null, requirements: [], evidence_ids: [], provenance: '', trail: [], next_move: null }]; });
  for (const v of ['landscape', 'readiness']) { await lens(v); const t = await txt(); expect(t).not.toContain('0 of 0'); expect(t).not.toContain('confirm 0'); }
  expect(await txt('#rd-detail')).toContain('No requirements are recorded');
  await withSnap(s => { s.paths = [{ id: 'z', title: 'All N/A', status_display: 'OPEN', lifecycle: 'OPEN', stop_source: null, requirements: [{ id: 'a', label: 'N/A one', satisfaction: 'ABSENT', applicable: false }], evidence_ids: [], provenance: '', trail: [], next_move: null }]; });
  await lens('readiness');
  expect(await txt('#rd-detail')).toContain('No requirements apply');
  await reset();
});

/* ── the real engine, through the real adapter ────────────────────────────────────────────────────────── */
test('19 · engine fixture, zero paths: the engine\'s own reason is on the page, in every lens', async () => {
  await applyFx('paths_zero');
  for (const v of ['landscape', 'readiness']) { await lens(v); expect(await txt()).toContain('We do not yet know enough about your situation to name a way forward with confidence.'); }
  expect(await page.evaluate(() => V11_ENGINE.snapshot().zero.kind)).toBe('INSUFFICIENT_INFORMATION');
});
test('20 · engine fixture, a legacy artifact is not "no paths": the map says it needs a fresh look and draws nothing', async () => {
  await applyFx('paths_legacy_content');
  expect(await txt()).toContain('needs a fresh look');
  await expect(page.locator('.v12-lane-label, .mp-card')).toHaveCount(0);
});
test('21 · engine fixtures, 1 / 5 / 8 / 10 paths: the count the engine formed is the count on the map; five are drawn, the rest are said out loud', async () => {
  for (const [name, n] of [['paths_one', 1], ['paths_five', 5], ['paths_eight', 8], ['paths_ten', 10]]) {
    await applyFx(name);
    expect(await page.evaluate(() => V11_ENGINE.snapshot().paths.length), name).toBe(n);
    await expect(page.locator('.v12-map .v12-lane-label'), name).toHaveCount(Math.min(n, 5));
    if (n > 5) await expect(page.locator('.v12-more'), name).toContainText(`+${n - 5} more`); else await expect(page.locator('.v12-more'), name).toHaveCount(0);
    // Design @HEAD: with every path drawn the canvas is the list — card rows exist only for hidden paths
    if (n > 5) await expect(page.locator('.mp-card'), name).toHaveCount(n - 5); else await expect(page.locator('.mp-card'), name).toHaveCount(0);
    expect(await txt(), name).not.toMatch(/\b(?:all 5 paths|the five paths)\b/i);
  }
});
test('22 · engine fixtures, readiness: UNKNOWN stays "not known yet" and is never filed as missing; PARTIAL is its own word', async () => {
  await applyFx('readiness_unknown'); await lens('readiness');
  const rows = await page.locator('.rd-group').evaluateAll(gs => gs.map(g => [g.querySelector('.rd-group-title').textContent, g.querySelectorAll('.rd-item').length]));
  /* the group title carries the state mark before its label (doc 21 §4: one glyph vocabulary for both lenses),
     so the key is the label alone */
  const byTitle = Object.fromEntries(rows.map(([t, n]) => [t.replace(/^[^A-Za-z]+/, '').split(' · ')[0], n]));
  expect(byTitle['Not known yet'], JSON.stringify(rows)).toBeGreaterThan(0);
  expect(byTitle['Not in place'] || 0, 'nothing here is missing').toBe(0);
  await applyFx('readiness_partial'); await lens('readiness');
  const t = await txt('#rd-detail');
  const tl = t.toLowerCase(); expect(tl).toContain('partly shown'); expect(tl).toContain('not in place'); expect(tl).toContain('not known yet');
  expect(t, 'a group with no source in the engine shows no label').not.toContain('Other possibilities');
  // the engine's own counts are the tally
  const c = await page.evaluate(() => V11_ENGINE.snapshot().paths[0].counts);
  expect(c.total).toBe(3); expect(await txt('.rd-counts')).toContain('0 of 3');
  await applyFx('readiness_satisfied'); await lens('readiness');
  expect(await txt('#rd-detail')).not.toContain('Not in place');
});
test('23 · engine fixture, a contested reading is "not settled": counted as not known, never as met or missing, and says why', async () => {
  await applyFx('readiness_conflict'); await lens('readiness');
  const grp = await page.locator('.rd-group', { has: page.locator('.rd-group-title', { hasText: /not known yet/i }) }).innerText();
  expect(grp.toLowerCase()).toContain('not settled');
  expect(await txt('.rd-counts')).toContain('0 of 2');
  expect(await page.evaluate(() => V11_ENGINE.snapshot().paths[0].status_display)).not.toBe('STOP');
});
test('24 · engine fixtures, STOP says who stopped it: by the evidence, or by you', async () => {
  // Design @HEAD: the stop wording lives on the canvas card's status line (the old .mp-cards list is gone)
  await applyFx('paths_engine_stop'); await lens('overview');
  await expect(page.locator('.v12-map svg')).toContainText('STOP · BY THE EVIDENCE');
  await applyFx('paths_user_stop'); await lens('overview');
  await expect(page.locator('.v12-map svg')).toContainText('STOP · BY YOU');
  // by you: the panel offers the way back, by the evidence: the do-it-anyway door, and nothing is silently reopened
  const ids = await page.evaluate(() => V11_ENGINE.snapshot().paths.filter(p => p.stop_source === 'you').map(p => p.id));
  await go(`mapsSelect('${ids[0]}')`);
  await expect(page.locator('#mp-panel')).toContainText('You paused this path');
});
test('25 · engine fixtures, candidates: a path born from a mechanism carries its reason and the notes the engine keeps beside it', async () => {
  await applyFx('paths_candidate_golden'); await lens('overview');
  await go(`mapsSelect('path.simplify_onboarding')`);
  const panel = await txt('#mp-panel');
  expect(panel).toContain('Your first session is confusing, so people give up before they see value.');
  expect(panel).toContain('It rests on');
  expect(panel).not.toMatch(/candidate|mechanism|provenance|route_id|MECHANISM/i);
  await applyFx('paths_candidate_unsettled'); await lens('overview');
  const ids = await page.evaluate(() => V11_ENGINE.snapshot().paths.map(p => p.id));
  let unsettled = false;
  for (const id of ids) { await go(`mapsSelect('${id}')`); if ((await txt('#mp-panel')).includes('point in different directions')) unsettled = true; }
  expect(unsettled, 'the disagreement stays beside the reason').toBe(true);
});
test('26 · engine fixtures, possibilities that are only taking shape sit in their own card and are not counted as paths', async () => {
  await applyFx('paths_emerging_unknown'); await lens('landscape');
  await expect(page.locator('[data-testid="emerging"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="emerging"] .emerging-item')).toHaveCount(1);
  expect(await page.evaluate(() => V11_ENGINE.snapshot().paths.length)).toBe(1);
  await applyFx('paths_emerging_conflict');
  await expect(page.locator('[data-testid="emerging"] .emerging-item')).toHaveCount(2);
  expect(await txt()).toContain('Not settled');
  await expect(page.locator('.v12-lane-label, .mp-card')).toHaveCount(0);
});
test('27 · "I want to do this anyway" on a path the evidence stopped opens the dialog that logs it; nothing is reopened silently', async () => {
  await applyFx('paths_engine_stop'); await lens('overview');
  const id = await page.evaluate(() => V11_ENGINE.snapshot().paths.find(p => p.status_display === 'STOP').id);
  await go(`mapsSelect('${id}')`);
  await page.getByRole('button', { name: /I want to do this anyway/ }).click();
  await expect(page.locator('#stop-modal.open')).toHaveCount(1);
  await page.keyboard.press('Escape');
  await expect(page.locator('#stop-modal.open')).toHaveCount(0);
  expect(await page.evaluate(i => V11_ENGINE.snapshot().paths.find(p => p.id === i).status_display, id), 'closing the dialog reopens nothing').toBe('STOP');
});

test('28 · engine fixtures, 3 and 6 paths: three is three, six is five and "+1 more"; five is not a quota and nothing is added to fill', async () => {
  for (const [name, n] of [['paths_three', 3], ['paths_six', 6]]) {
    await applyFx(name);
    expect(await page.evaluate(() => V11_ENGINE.snapshot().paths.length), name).toBe(n);
    await expect(page.locator('.v12-map .v12-lane-label'), name).toHaveCount(Math.min(n, 5));
    if (n > 5) await expect(page.locator('.v12-more'), name).toContainText('+1 more'); else await expect(page.locator('.v12-more'), name).toHaveCount(0);
    /* the count moved out of the head's prose line into the workspace bar (doc 21 §4): "Possible paths" and the
       engine's own total, which is everything on the map and not only what the canvas draws */
    await expect(page.locator('.mpw-bar h2'), name).toContainText('Possible paths');
    await expect(page.locator('.mpw-bar .st-count'), name).toHaveText(String(n));
  }
});
test('29 · engine fixtures, candidates with no route: real paths, one per direction, each says why it is there, and "assumes" only where the engine assumed', async () => {
  await applyFx('paths_candidates'); await lens('overview');
  const ids = await page.evaluate(() => V11_ENGINE.snapshot().paths.map(p => p.id));
  expect(ids, 'two mechanisms that point at one direction are one path, not two').toEqual(['path.improve_activation_before_acquisition', 'path.define_aha_moment', 'path.simplify_onboarding']);
  await go(`mapsSelect('path.improve_activation_before_acquisition')`);
  let panel = await txt('#mp-panel');
  expect(panel, 'both reasons, in one sentence').toContain('Many people sign up, but too few reach the moment where the product pays off. Your first session is confusing, so people give up before they see value.');
  expect(panel).toContain('It rests on 5 things you shared, read against 2 rules from our knowledge base.');
  expect(panel).toContain('assumes nothing you told us points the other way. We have not confirmed that.');
  await go(`mapsSelect('path.simplify_onboarding')`);
  panel = await txt('#mp-panel');
  expect(panel, 'a path without that lean does not say so').not.toContain('assumes nothing you told us');
  await expect(page.locator('[data-testid="emerging"]')).toHaveCount(0);
});
test('30 · engine fixture, a candidate that has a route: the route joins it by strategy, the reason stays beside it, four identities stay four', async () => {
  await applyFx('paths_candidate_route'); await lens('readiness');
  await go(`readinessSelect('path.simplify_onboarding')`);
  await expect(page.locator('#rd-detail .rd-item')).toHaveCount(2);
  await lens('overview'); await go(`mapsSelect('path.simplify_onboarding')`);
  expect(await txt('#mp-panel'), 'the reason is on the path, beside the route').toContain('Your first session is confusing');
  const ident = await page.evaluate(() => { const pr = LIVE.projection.paths.find(p => p.key === 'path.simplify_onboarding'); return { tpl: pr.route.template_id, ids: [pr.candidate.candidate_id, pr.strategy_id, pr.path_id, pr.route.route_id] }; });
  expect(ident.tpl).toBe('simplify_onboarding_v1');
  expect(new Set(ident.ids).size, 'candidate, strategy, path and route are four different identities').toBe(4);
});
test('31 · engine fixture, seven paths of which two are born from mechanisms: only those carry a reason, a declared strategy invents no origin', async () => {
  await applyFx('paths_candidate_revenue'); await lens('overview');
  await expect(page.locator('.v12-map .v12-lane-label')).toHaveCount(5);
  await expect(page.locator('.v12-more')).toContainText('+2 more');
  expect(await page.evaluate(() => V11_ENGINE.snapshot().paths.length), 'the engine keeps all seven').toBe(7);
  await go(`mapsSelect('path.fix_response_before_more_leads')`);
  expect(await txt('#mp-panel')).toContain('Leads are reaching you, but some slip away in how they are answered and followed up.');
  expect(await txt('#mp-panel')).toContain('It rests on 1 thing you shared.');
  await go(`mapsSelect('path.value_repricing')`);
  expect(await txt('#mp-panel'), 'a path from a declared strategy has no mechanism line').not.toContain('It rests on');
  await go(`mapsSelect('path.narrow_target_before_volume')`);
  expect(await txt('#mp-panel'), 'a hidden (sixth or seventh) path keeps its reason').toContain('WHY THIS PATH IS ON YOUR MAP');
});
test('32 · engine fixture, an unsettled reading beside a reason: the disagreement stays there, and a path with nothing disputed carries no such note', async () => {
  await applyFx('paths_candidate_unsettled'); await lens('overview');
  await go(`mapsSelect('path.improve_activation_before_acquisition')`);
  const panel = await txt('#mp-panel');
  expect(panel).toContain('Your first session is confusing, so people give up before they see value.');
  expect(panel, 'the disputed reading is never narrated as a reason').not.toMatch(/sign up|pays off/i);
  expect(panel).toContain('point in different directions about activation bottleneck');
  expect(panel).toContain('not counting that as part of the reason');
  await go(`mapsSelect('path.simplify_onboarding')`);
  expect(await txt('#mp-panel')).not.toContain('point in different directions');
});
test('33 · engine fixtures, a requirement that exists only in the registry, knowledge-born paths and the five motions: readable, in the right state, no internal token anywhere', async () => {
  const RAW = /\b(?:path|access|commercial|delivery|offering|conversion|retention|gtm|experiment|sample|cand)\.[a-z][a-z_]+\b|\b(?:PRESENT|ABSENT|PARTIAL|UNKNOWN|CONFLICT|UNSUPPORTED|SUPPORTED|CONDITIONAL|CONTRADICTED|UNDETERMINED|APPLIES|NOT_APPLICABLE|MECHANISM_PATTERN|STRATEGY_DECLARED)\b|\b(?:state|mechanism|rule):[a-z_0-9]+|\bundefined\b|\bnull\b|NaN|\[object/;
  const bad = [];
  for (const name of ['paths_one', 'paths_three', 'paths_five', 'paths_eight', 'paths_ten', 'paths_zero', 'paths_knowledge', 'paths_revenue_five', 'paths_candidates', 'paths_candidates_many', 'paths_candidate_route', 'paths_candidate_golden', 'paths_candidate_revenue', 'paths_candidate_unsettled', 'paths_engine_stop', 'paths_user_stop', 'paths_legacy', 'paths_legacy_content', 'readiness_new_requirement', 'readiness_unknown', 'readiness_partial', 'readiness_satisfied', 'readiness_conflict', 'paths_emerging_unknown', 'paths_emerging_conflict', 'paths_emerging_unsupported']) {
    await applyFx(name);
    const ids = await page.evaluate(() => V11_ENGINE.snapshot().paths.map(p => p.id).slice(0, 3));
    for (const v of ['landscape', 'readiness']) {
      await lens(v);
      for (const id of ids.length ? ids : [null]) {
        if (id) await go(v === 'readiness' ? `readinessSelect('${id}')` : `mapsSelect('${id}')`);
        const t = await page.locator('#v11-main').innerText();
        const m = t.match(RAW);
        if (m) bad.push(`${name}/${v}${id ? '/' + id : ''}: "${m[0]}"`);
      }
    }
  }
  expect(bad).toEqual([]);
  await applyFx('readiness_new_requirement'); await lens('readiness');
  const rows = await page.locator('#rd-detail .rd-item').allTextContents();
  expect(rows.length).toBeGreaterThan(0);
  for (const r of rows) expect(r.trim().length, 'every requirement has a readable name').toBeGreaterThan(3);
});
test('34 · the reveal and State say how many paths there are when the engine formed more than five, and never claim "all"', async () => {
  await applyFx('paths_eight');
  await go(`goDestination('state')`);
  const t = await txt('.dest-paths');
  expect(t).toMatch(/\+3 other possibilit(y|ies)|3 more/i);
  expect(t).not.toMatch(/\ball (5|five|8|eight) paths\b/i);
  expect(await page.locator('.dest-paths .strat-row, .dest-paths li, .dest-paths [data-path]').count()).toBeLessThanOrEqual(5);
  await go(`goDestination('maps')`);
});
test('35 · a late plain-language rewrite never takes the keyboard user\'s place: the opened "+N more" list and the focus survive the re-render', async () => {
  // root cause of the timing-dependent keyboard failure of the old presentation-cap spec (1 in 15 runs): the rewrite lands 15 to 50 s
  // after the page opened, re-renders the page and used to close every opened <details> and drop focus on <body>
  await applyFx('paths_eight'); await lens('overview');
  await page.locator('.mp-more summary').focus(); await page.keyboard.press('Enter');
  expect(await page.locator('#mp-more').evaluate(d => d.open)).toBe(true);
  await page.locator('#mp-more summary').focus();
  await go(`LIVE.explainState = 'idle'`);
  await page.evaluate(() => liveEnsureExplain());
  await page.waitForFunction(() => LIVE.explainState === 'ready' || LIVE.explainState === 'failed', null, { timeout: 30_000 });
  await page.waitForTimeout(300);
  expect(await page.locator('#mp-more').evaluate(d => d.open), 'the list the person opened is still open').toBe(true);
  expect(await page.evaluate(() => document.activeElement && document.activeElement.tagName), 'focus is still on the summary').toBe('SUMMARY');
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => !!document.activeElement.closest('#mp-more')), 'Tab goes on into the hidden paths').toBe(true);
});
test('36 · nothing logged a console error', async () => {
  expect(consoleErrors).toEqual([]);
});
