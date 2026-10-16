// Moves destination (record P5c; doc 10 §6.3; prototype behavior.mjs "moves"): the working set of actions the plan and
// the engine support right now. One move on screen with what it needs and what done means; the other moves, the routes'
// moves, what else is ready on the map and what is on hold around it. Marking a move done records the action and claims
// neither a result nor that the map moved. Live UI against the real API with the mock LLM; the snapshot conditions the
// mock cannot reach are put in place through the seam.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test.describe.configure({ mode: 'serial' });

const here = path.dirname(fileURLToPath(import.meta.url));
const fx = name => JSON.parse(fs.readFileSync(path.join(here, 'fixtures', `${name}.json`), 'utf8'));

let page, ctx;
const consoleErrors = [];
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(100); };
const txt = (sel = '#v11-main') => page.locator(sel).innerText();
const withSnap = (mut) => go(`
  const snap = JSON.parse(JSON.stringify(V11_ENGINE.snapshot()));
  (${mut.toString()})(snap);
  V11_ENGINE.set(v11MapKey(), snap);
  goDestination('moves');`);
const reset = () => go(`V11_ENGINE.clear(); goDestination('moves')`);

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

test('01 · Moves is one move and what is around it: head, the move card with its status, what done looks like, one primary action, the queues', async () => {
  await go(`goDestination('moves')`);
  await expect(page.locator('#v11-main h1')).toHaveText(/move/i);
  await expect(page.locator('.v11-eyebrow')).toContainText('Moves');
  await expect(page.locator('.today-card')).toHaveCount(1);
  await expect(page.locator('.today-card .status-pill')).toHaveText(/READY TO MOVE/);
  await expect(page.locator('.today-card')).toContainText('What done looks like');
  await expect(page.locator('.today-actions .btn-primary')).toHaveCount(1);
  await expect(page.locator('.moves-queues')).toHaveCount(1);
  await expect(page.locator('.moves-queues')).toContainText('YOUR MOVES');
  await expect(page.locator('.step-focus, .step-row').first()).toBeVisible();
});

test('02 · no greeting by time of day, no sample name, no cycle, no universal 90 days', async () => {
  const t = await txt();
  expect(t).not.toMatch(/Good (morning|afternoon|evening)|Dimas|Sari|\bcycle\b/i);
  expect(t).not.toMatch(/Day 90|90 days/);
  expect(t).not.toMatch(/recommended|best move|top pick/i);
});

test('03 · any ready move can be opened; a move that waits says what it waits for and is WAITING, not READY', async () => {
  const rows = page.locator('.moves-list .step-row');
  const n = await rows.count();
  expect(n).toBeGreaterThan(1);
  await rows.first().click();
  await expect(page.locator('.today-card .status-pill')).toBeVisible();
  const waiting = page.locator('.moves-list .step-row.waiting').first();
  if (await waiting.count()) {
    await waiting.click();
    await expect(page.locator('.today-card .status-pill')).toHaveText(/WAITING/);
    expect(await txt('.today-actions')).toMatch(/Start with step|On hold|Report early/);
  }
  await go(`STORE.viewStep = 0; goDestination('moves')`);
});

test('04 · marking a move done records the action and claims no result and no map change', async () => {
  const before = await page.locator('.moves-list .step-row.done').count();
  await page.getByRole('button', { name: /Mark as (done|sent)/ }).click();
  const toast = page.locator('.app-toast');
  await expect(toast).toBeVisible();
  const t = await toast.innerText();
  expect(t).toContain('recorded as done');
  expect(t).not.toMatch(/map (has been )?updated|worked|success/i);
  await page.waitForTimeout(400);
  expect(await page.locator('.moves-list .step-row.done').count()).toBeGreaterThanOrEqual(before);
  expect(await txt('.moves-list')).toContain('Doing a move does not say it worked.');
});

test('05 · what is on hold is neutral: grey pills from the snapshot, never red STOP pills', async () => {
  await withSnap(s => { s.state.what_not_to_do = ['Do not lease an office', 'Do not run paid ads yet']; });
  await expect(page.locator('.moves-queues .status-pill.hold')).toHaveCount(2);
  await expect(page.locator('.moves-queues .status-pill.stop')).toHaveCount(0);
  await expect(page.locator('.moves-queues')).toContainText('ON HOLD · UNTIL THE RECORD CHANGES');
  await reset();
});

test('06 · "also ready on your map" lists open or test-first paths from the snapshot, and Open Maps lands on that path', async () => {
  await go(`V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); goDestination('moves')`);
  const rows = page.locator('.moves-q', { hasText: 'ALSO READY ON YOUR MAP' }).locator('.moves-q-row');
  expect(await rows.count()).toBeGreaterThan(0);
  expect(await rows.count()).toBeLessThanOrEqual(3);
  const first = rows.first();
  const title = (await first.locator('span').first().innerText()).split(':')[0].trim();
  await first.getByRole('button', { name: /Open Maps/ }).click();
  await expect(page).toHaveURL(/#\/maps$/);
  const sel = await page.evaluate(() => V11_ENGINE.snapshot().paths.find(p => p.id === selectedPathId()).title);
  expect(sel).toBe(title);
  await reset();
});

test('07 · when the engine\'s next move is a question, Moves says it needs evidence and sends you to Talk', async () => {
  await withSnap(s => { s.nextmove = { type: 'QUESTION', title: 'Someone willing to pay that price', path_id: null }; });
  await expect(page.locator('.moves-q', { hasText: 'NEEDS EVIDENCE' })).toContainText('Someone willing to pay that price');
  await page.getByRole('button', { name: /Answer in Talk/ }).click();
  await expect(page).toHaveURL(/#\/talk$/);
  await reset();
});

test('08 · moves from the routes are listed apart, each with its route and a button that records the action', async () => {
  const f = fx('paths_candidate_golden');
  await go(`V11_ENGINE.clear(); LIVE.routes = ${JSON.stringify(f.routes)}; goDestination('moves')`);
  const cards = page.locator('.moves-routes .route-task');
  expect(await cards.count()).toBeGreaterThan(0);
  await expect(cards.first().locator('.route-task-route')).not.toBeEmpty();
  await expect(cards.first().getByRole('button', { name: /I did this/ })).toBeVisible();
  await go(`LIVE.routes = null; goDestination('moves')`);
});

test('09 · no plan yet is a valid state: a way in through Talk, no invented move', async () => {
  await go(`const keep = LIVE.artifact.day_by_day; window.__keepPlan = keep; LIVE.artifact.day_by_day = []; LIVE.artifact.first_step_today = ''; LIVE.artifact.next_best_action = ''; syncStoreFromLive(); goDestination('moves')`);
  await expect(page.locator('#v11-main h1')).toHaveText('No move yet.');
  await expect(page.getByRole('button', { name: /Open Talk/ })).toBeVisible();
  expect(await txt()).not.toContain('Mark as');
  await go(`LIVE.artifact.day_by_day = window.__keepPlan; syncStoreFromLive(); goDestination('moves')`);
});

test('10 · long move text and many moves stay inside the screen at 320 px, with the primary action reachable', async () => {
  await page.setViewportSize({ width: 320, height: 800 });
  await go(`goDestination('moves')`);
  const dx = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth - innerWidth, bad: [...document.querySelectorAll('#v11-main *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > innerWidth + 1.5 && !e.closest('.v12-map'); }).slice(0, 5).map(e => e.tagName + '.' + e.className) }));
  expect(dx.doc).toBeLessThanOrEqual(2);
  expect(dx.bad).toEqual([]);
  const btn = page.locator('.today-actions .btn-primary').first();
  await btn.scrollIntoViewIfNeeded();
  const box = await btn.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(321);
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('11 · nothing logged a console error', async () => {
  expect(consoleErrors).toEqual([]);
});
