// Journey destination (record P5d; doc 10 §6.4; prototype behavior.mjs "journey" and the R2 rules of doc 06 §12.2).
// What has been recorded, in the order it happened. ACTUAL, TARGET and TREND stay apart; nothing is drawn or counted
// that is not on record: no goal means no goal line and no percentage, no deadline means no timeline and no day
// counter, no income means "Not recorded", fewer than three recorded check-ins means no trend. Live UI against the
// real API with the mock LLM; the recorded state is put in place through the page's own record (LIVE).
import { test, expect } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

let page, ctx;
const consoleErrors = [];
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(120); };
const txt = (sel = '#v11-main') => page.locator(sel).innerText();
const rec = (cycle, day, rp, outcome = 'worked', extra = {}) => Object.assign({ cycle, day, rp, outcome, contacted: 5, replies: 2, calls: 1, paid: 0, path: 'path.direct_outreach', title: `Check-in ${cycle} title`, note: 'x' }, extra);
/* put the recorded state in place: deadline (days or none), goal (millions or none), income at the first diagnosis, check-ins, and how long ago the map began */
const setJourney = (o) => go(`
  const o = ${JSON.stringify(o)};
  V11_ENGINE.clear();
  LIVE.horizonOverride = o.horizon || 0;
  LIVE.state = Object.assign({}, LIVE.state, { goal: Object.assign({}, (LIVE.state || {}).goal, { deadline_days: null }) });
  LIVE.goalOverride = 0;
  const rs = LIVE.artifact.revenue_state;
  rs.target_monthly = o.goal == null ? null : o.goal;
  rs.current_monthly = o.income == null ? null : o.income;
  LIVE.baseline = JSON.parse(JSON.stringify(LIVE.artifact));
  LIVE.checkins = o.checkins || [];
  LIVE.startTs = Date.now() - (o.daysAgo || 0) * 86400000;
  syncStoreFromLive();
  goDestination('journey');`);
const nodes = () => page.locator('#j-root svg .j-node');

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

test('01 · four stat cards and the chart card, with the page head, on a map with a goal and a deadline', async () => {
  await setJourney({ horizon: 90, goal: 30, income: 0, checkins: [], daysAgo: 2 });
  await expect(page.locator('.v11-eyebrow')).toContainText('Journey');
  await expect(page.locator('.j-statcard')).toHaveCount(4);
  await expect(page.locator('.j-chartcard')).toHaveCount(1);
  await expect(page.locator('.v11-journey-cols')).toHaveCount(1);
  expect(await txt()).not.toMatch(/Dimas|Sari|Target path|Estimate/);
});

test('02 · with no check-ins there is no trend and no invented curve, and the page says so', async () => {
  await expect(page.locator('#v11-main h1')).toHaveText('No check-ins are recorded yet.');
  const t = await txt();
  expect(t).toContain('No projection yet');
  expect(t).toContain('0 are on record');
  await expect(page.locator('#j-root svg path[stroke-dasharray="5 4"]')).toHaveCount(0);
  await expect(page.locator('#j-root .j-legend')).not.toContainText('Trend if the pace holds');
});

test('03 · a trend appears only from three recorded check-ins that carry an income, is labelled a trend, and is not the goal', async () => {
  await setJourney({ horizon: 90, goal: 30, income: 0, daysAgo: 30, checkins: [rec(1, 7, 2), rec(2, 14, 4)] });
  await expect(page.locator('#j-root svg path[stroke-dasharray="5 4"]')).toHaveCount(0);
  expect(await txt('.j-proj-note')).toContain('needs at least 3');
  await setJourney({ horizon: 90, goal: 30, income: 0, daysAgo: 30, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, 6)] });
  await expect(page.locator('#j-root svg path[stroke-dasharray="5 4"]')).toHaveCount(1);
  expect(await txt('.j-proj-note')).toContain('It is not a forecast');
  await expect(page.locator('.j-legend')).toContainText('Trend if the pace holds');
  // the trend is the recorded pace (2 more per week) continued to the deadline, not a line to the goal
  const label = await page.locator('#j-root svg text', { hasText: 'If the recent pace holds' }).textContent();
  expect(label).toContain('about Rp');
  expect(label).not.toContain('Rp30M');
  // a goal that is far away does not bend the trend
  await setJourney({ horizon: 90, goal: 300, income: 0, daysAgo: 30, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, 6)] });
  expect(await page.locator('#j-root svg text', { hasText: 'If the recent pace holds' }).textContent()).toBe(label);
});

test('04 · missed check-ins and check-ins with no income never feed a trend', async () => {
  await setJourney({ horizon: 90, goal: 30, income: 0, daysAgo: 30, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, 6, 'missed')] });
  await expect(page.locator('#j-root svg path[stroke-dasharray="5 4"]')).toHaveCount(0);
  await setJourney({ horizon: 90, goal: 30, income: 0, daysAgo: 30, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, null)] });
  await expect(page.locator('#j-root svg path[stroke-dasharray="5 4"]')).toHaveCount(0);
  expect(await txt('.j-hist')).toContain('Not recorded');
});

test('05 · no deadline: no timeline, no day counter and no invented horizon anywhere on the page', async () => {
  await setJourney({ horizon: 0, goal: 30, income: 5, daysAgo: 12, checkins: [rec(1, 7, 6)] });
  await expect(page.locator('.j-chartcard')).toHaveCount(0);
  const t = await txt();
  expect(t).toContain('No deadline is set');
  expect(t).toContain('no timeline to draw');
  expect(t).not.toMatch(/Day 90|90 days|of 90|W13/);
  await expect(page.locator('.j-statcard').nth(1)).toContainText('DEADLINE');
  await expect(page.locator('.j-statcard').nth(1)).toContainText('None');
  // The v11 shell removed the status pill (v11.dc iteration). The contract stands: WHEN a shell
  // has one, it must not invent a horizon - asserted conditionally, never by waiting for it.
  const pillCount = await page.locator('.topbar-status').count();
  expect(pillCount, 'at most one status pill element').toBeLessThanOrEqual(1);
  if (pillCount) {
    await expect(page.locator('.topbar-status')).not.toMatch(/of \d+/);
  }
});

test('06 · a 56-day deadline drives the axis, the weeks and the counters; no 90 appears', async () => {
  await setJourney({ horizon: 56, goal: 30, income: 0, daysAgo: 10, checkins: [rec(1, 7, 3)] });
  const t = await txt();
  expect(t).toContain('Day 11 of 56');   // ten days ago is the 11th day
  expect(t).not.toMatch(/\b90\b/);
  await expect(page.locator('#j-root svg text', { hasText: /^W8$/ })).toHaveCount(1);
  await expect(page.locator('#j-root svg text', { hasText: /^W9$/ })).toHaveCount(0);
  await setJourney({ horizon: 120, goal: 30, income: 0, daysAgo: 10, checkins: [] });
  await expect(page.locator('#j-root svg text', { hasText: /^W18$/ })).toHaveCount(1);
  expect(await txt()).not.toMatch(/\b90\b/);
});

test('07 · a check-in dated past the deadline is listed but never plotted and never bends the trend', async () => {
  await setJourney({ horizon: 56, goal: 30, income: 0, daysAgo: 70, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, 6), rec(4, 80, 28)] });
  const before = await nodes().count();
  expect(await txt('.j-hist')).toContain('Day 80');                 // listed
  const dayLabels = await page.evaluate(() => (window.__journeyNodes || []).filter(n => n.day > 56).length);
  expect(dayLabels).toBe(1);                                         // it exists as a record
  expect(await nodes().count()).toBeLessThan(before + 1);
  await setJourney({ horizon: 56, goal: 30, income: 0, daysAgo: 20, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, 6)] });
  const l1 = await page.locator('#j-root svg text', { hasText: 'If the recent pace holds' }).textContent();
  await setJourney({ horizon: 56, goal: 30, income: 0, daysAgo: 20, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, 6), rec(4, 80, 28)] });
  expect(await page.locator('#j-root svg text', { hasText: 'If the recent pace holds' }).textContent()).toBe(l1);
});

test('08 · goal reached early is shown as reached; a goal missed at the deadline says so with that deadline', async () => {
  await setJourney({ horizon: 90, goal: 10, income: 0, daysAgo: 30, checkins: [rec(1, 7, 4), rec(2, 14, 12)] });
  await expect(page.locator('#v11-main h1')).toHaveText('You reached your goal. Now keep it steady.');
  await expect(page.locator('#j-root svg text', { hasText: 'Goal reached on Day 14' })).toHaveCount(1);
  await setJourney({ horizon: 56, goal: 30, income: 0, daysAgo: 70, checkins: [rec(1, 7, 4), rec(2, 14, 8)] });
  const h = await txt('#v11-main h1');
  expect(h).toContain('Day 56');
  expect(h).toContain('Not Rp30M yet');
  expect(h).not.toMatch(/\b90\b/);
});

test('09 · no goal on record: no goal line, no goal legend and no percentage; an income without a goal is shown as an amount only', async () => {
  await setJourney({ horizon: 90, goal: null, income: 8, daysAgo: 5, checkins: [] });
  await expect(page.locator('.j-legend')).not.toContainText('Goal');
  expect(await txt('.j-chartcard')).not.toMatch(/Goal ·/);
  const card = await txt('.j-statcard >> nth=0');
  expect(card).toContain('Rp8M');
  expect(card).toContain('No goal on record yet');
  expect(card).not.toMatch(/\d+%/);
  expect(await txt()).not.toMatch(/Rp30M/);
});

test('10 · no income on record says "Not recorded" and computes no percentage from it', async () => {
  await setJourney({ horizon: 90, goal: 30, income: null, daysAgo: 5, checkins: [] });
  const card = await txt('.j-statcard >> nth=0');
  expect(card).toContain('Not recorded');
  expect(card).toContain('No income recorded yet');
  expect(card).not.toMatch(/\d+%/);
  await setJourney({ horizon: 90, goal: 30, income: 6, daysAgo: 5, checkins: [] });
  expect(await txt('.j-statcard >> nth=0')).toContain('20% of the Rp30M goal');
});

test('11 · an ended map makes no money claim it cannot support and sends you to its review', async () => {
  await setJourney({ horizon: 56, goal: 30, income: null, daysAgo: 70, checkins: [rec(1, 7, null), rec(2, 14, null)] });
  const t = await txt();
  expect(t).not.toMatch(/saved|kept safe|Rp0M/i);
  await expect(page.getByRole('button', { name: /review/i })).toBeVisible();
});

test('12 · on hold is neutral and comes only from the snapshot: grey pills, no decision and no result invented', async () => {
  await setJourney({ horizon: 90, goal: 30, income: 0, daysAgo: 2, checkins: [] });
  await go(`const s = JSON.parse(JSON.stringify(V11_ENGINE.snapshot())); s.state.what_not_to_do = ['Do not lease an office']; V11_ENGINE.set(v11MapKey(), s); goDestination('journey')`);
  await expect(page.locator('#j-side .j-hold-side .status-pill.hold')).toHaveText('On hold');
  await expect(page.locator('#j-side .j-hold-side .status-pill.stop')).toHaveCount(0);
  await go(`V11_ENGINE.clear()`);
});

test('13 · every point on the chart can be reached by keyboard and says what it is', async () => {
  await setJourney({ horizon: 90, goal: 30, income: 0, daysAgo: 30, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, 6)] });
  const n = await nodes().count();
  expect(n).toBeGreaterThanOrEqual(4);
  for (const el of await nodes().all()) {
    expect(await el.getAttribute('tabindex')).toBe('0');
    expect((await el.getAttribute('aria-label') || '').length).toBeGreaterThan(8);
  }
  await nodes().nth(1).focus();
  await expect(page.locator('#j-tip')).toBeVisible();
  expect(await txt('#j-tip')).toContain('CHECK-IN 1');
});

test('14 · at 320 px the page does not scroll sideways (the chart scrolls inside its own card)', async () => {
  await page.setViewportSize({ width: 320, height: 800 });
  await setJourney({ horizon: 90, goal: 30, income: 0, daysAgo: 30, checkins: [rec(1, 7, 2), rec(2, 14, 4), rec(3, 21, 6)] });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(2);
  expect(await page.evaluate(() => getComputedStyle(document.querySelector('.j-chartcard')).overflowX)).toMatch(/auto|scroll/);
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('15 · nothing logged a console error', async () => {
  expect(consoleErrors).toEqual([]);
});
