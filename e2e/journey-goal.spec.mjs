// JOURNEY is the trajectory of the ACTIVE Primary Goal, in that goal's own metric and unit (doc 09 §6 JOURNEY).
// Each scenario creates its own session through the API (mock LLM), puts observations in the workspace, opens the
// map the way the app restores it, and asserts what the chart REPRESENTS (metric, unit, axis, target, dots, line),
// not a number that happens to appear somewhere on the page. Screenshots (e2e/__visual__/journey-goal/) are looked
// at by eye; DOM assertions never replace that.
//
//   JG-1  rate goal      : close rate in %, three valid dots, two bad measurements stay out, target + baseline lines
//   JG-2  count goal     : qualified leads as a count, no % and no Rp on the axis
//   JG-3  revenue goal   : keeps its monthly-income chart; no goal-relative chart is drawn over it
//   JG-4  no valid dot   : target and what is missing are said; nothing is drawn, missing is not zero
//   JG-5  one dot        : a dot, never a trend
//   JG-6  criteria goal  : judged by evidence, typed list, no axis
//   JG-7  incomparable   : evidence recorded under an earlier definition is not plotted
//   JG-10 value goal     : sales_cycle_days in days (45 -> 38, target 20, baseline 45), no income/rupiah, nothing carried over
//   JG-8  switching      : rate -> count -> revenue -> rate in one page, no dataset or axis carried over
//
// Observations are SEEDED into the workspace event log with a back-dated record time: the public API can only
// stamp "now", and a trajectory needs observations spread over time. Everything else goes through the real API.
import { test, expect } from '@playwright/test';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test.describe.configure({ mode: 'serial', timeout: 240_000 });

const here = path.dirname(fileURLToPath(import.meta.url));
const VISUAL = path.join(here, '__visual__', 'journey-goal');
fs.mkdirSync(VISUAL, { recursive: true });
const WORKSPACES = path.resolve(here, '..', 'store', 'workspaces');
const PORT = 'http://127.0.0.1:' + (process.env.E2E_PORT || 8765);
const UID = 'u_e2e_jg_' + Math.random().toString(16).slice(2, 8);
const DAY = 86400;
const nowSec = () => Math.floor(Date.now() / 1000);

let page, ctx;
const consoleErrors = [];
const api = (p, init) => page.request.fetch(PORT + p, init);
const apiJson = async (p, init) => { const r = await api(p, init); return { status: r.status(), body: await r.json() }; };
const hashes = {};
const shot = async (name) => {
  await page.mouse.move(760, 880);
  await expect(page.locator('#app-toast.show')).toHaveCount(0, { timeout: 8000 });
  await page.waitForTimeout(300);
  const buf = await page.screenshot({ path: path.join(VISUAL, name + '.png'), fullPage: false });
  hashes[name] = crypto.createHash('sha1').update(buf).digest('hex');
};

async function makeSession(body) {
  const r = await apiJson('/session', { method: 'POST', data: { user_id: UID, ...body } });
  expect(r.status, 'session created').toBe(200);
  const sid = r.body.session_id;
  const m = await api('/session/' + sid + '/message', { method: 'POST', data: { text: 'Nobody has paid me yet and two people asked me to let them know.' } });
  expect(m.status(), 'turn accepted').toBeLessThan(300);
  const f = await api('/session/' + sid + '/finalize', { method: 'POST' });
  expect(f.status(), 'diagnosis built').toBe(200);
  return { sid, gid: r.body.goal.goal_id };
}
const goalObj = async (gid) => (await apiJson('/workspace/' + UID + '/goals')).body.goals.find(g => g.goal_id === gid);
async function seed(gid, at, payload) {
  const g = await goalObj(gid);
  fs.mkdirSync(path.join(WORKSPACES, UID), { recursive: true });
  fs.appendFileSync(path.join(WORKSPACES, UID, 'goals.jsonl'),
    JSON.stringify({ type: 'GOAL_MEASURED', ts: at, goal_id: gid, version: g.version || 1, goal: g, payload }) + '\n');
}
const rateObs = (at, n, d, extra = {}) => seed(extra.gid, at, { kind: 'rate', numerator: n, denominator: d, cohort: 'inbound', period: 'w-' + at,
  period_start_ts: at - 61 * DAY, period_end_ts: at - 1 * DAY, ...extra.over });

async function openMap(sid, dest = 'journey') {
  await page.evaluate(([uid, s]) => localStorage.setItem('novaliners-v9', JSON.stringify({ userId: uid, current: s, chain: [], checkins: [], overrides: [], tips: {} })), [UID, sid]);
  await page.evaluate(() => sessionStorage.setItem('e2e-keep-ls', '1'));
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForFunction((x) => typeof LIVE !== 'undefined' && LIVE.sid === x && !!LIVE.artifact && !!LIVE.state, sid, { timeout: 30_000 });
  await page.waitForTimeout(400);
  await page.evaluate((d) => goDestination(d), dest);
  await page.waitForTimeout(500);
}
const rerender = async () => { await page.evaluate(() => goDestination('journey')); await page.waitForTimeout(450); };

/* what the chart on screen represents, read from the DOM (never from nearby prose) */
const chart = () => page.evaluate(() => {
  const card = document.querySelector('[data-j-goal-chart]');
  if (!card) return null;
  const svg = card.querySelector('svg[data-j-chart="goal"]');
  const num = el => (el ? Number(el.getAttribute('data-value')) : null);
  return {
    kind: card.getAttribute('data-j-goal-chart'), metric: card.getAttribute('data-j-metric'), unit: card.getAttribute('data-j-unit'),
    heading: (card.querySelector('.section-meta-label') || {}).textContent || '',
    hasSvg: !!svg,
    points: svg ? [...svg.querySelectorAll('[data-j-point]')].map(p => ({ v: num(p), seg: Number(p.getAttribute('data-segment')) })) : [],
    lines: svg ? svg.querySelectorAll('[data-j-line]').length : 0,
    target: svg ? num(svg.querySelector('[data-j-target]')) : null,
    baseline: svg ? num(svg.querySelector('[data-j-baseline]')) : null,
    axisText: svg ? [...svg.querySelectorAll('text')].map(t => t.textContent) : [],
    empty: (card.querySelector('[data-j-empty]') || {}).getAttribute ? card.querySelector('[data-j-empty]').getAttribute('data-j-empty') : null,
    text: card.innerText,
    assessment: (card.querySelector('[data-j-assessment]') || { getAttribute: () => null }).getAttribute('data-j-assessment'),
    limits: (card.querySelector('[data-j-limits]') || {}).textContent || '',
    tableValues: [...card.querySelectorAll('[data-j-cell-value]')].map(c => c.textContent)
  };
});
const incomeChartCount = () => page.locator('.j-chartcard:not(.j-gcard):not([data-j-lanes])').count();
const shotBoth = async (name) => {
  await page.setViewportSize({ width: 1440, height: 900 }); await rerender(); await shot(name + '-desktop');
  await page.setViewportSize({ width: 390, height: 844 }); await rerender();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, name + ': no horizontal overflow at 390px').toBeLessThanOrEqual(1);
  const target = page.locator('[data-j-goal-chart], .j-chartcard').first();
  if (await target.count()) await target.scrollIntoViewIfNeeded({ timeout: 5000 });
  await page.waitForTimeout(200);
  await shot(name + '-mobile');
  await page.setViewportSize({ width: 1440, height: 900 }); await rerender();
};

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  await page.goto('/', { waitUntil: 'networkidle' });
});
test.afterAll(async () => { await ctx.close(); });

let rate, count, revenue;

// ── JG-1 · rate goal ────────────────────────────────────────────────────────────────────────────────
test('JG-1 · rate goal: close rate in %, three valid observations, bad ones stay out, target and baseline drawn', async () => {
  rate = await makeSession({ goal_text: 'Our close rate is about 15%. I want 25% in 60 days.', metric_id: 'close_rate', target: 0.25, baseline: 0.15, measurement_window_days: 60 });
  const g = rate.gid, t = nowSec();
  await rateObs(t - 40 * DAY, 3, 20, { gid: g });
  await rateObs(t - 20 * DAY, 4, 20, { gid: g });
  await rateObs(t - 3 * DAY, 5, 20, { gid: g });
  // bad evidence: stored, never a dot. a period nobody can verify, and more won than counted
  await seed(g, t - 10 * DAY, { kind: 'rate', numerator: 9, denominator: 20, cohort: 'inbound', period: 'last quarter' });
  await seed(g, t - 6 * DAY, { kind: 'rate', numerator: 9, denominator: 3, cohort: 'inbound', period: 'w-bad', period_start_ts: t - 66 * DAY, period_end_ts: t - 6 * DAY });
  const st = (await apiJson('/session/' + rate.sid + '/state')).body;
  expect(st.goal_series.points.map(p => p.value), 'the server holds exactly the three valid observations').toEqual([0.15, 0.2, 0.25]);
  expect(st.goal_series.rejected.count).toBe(2);
  await openMap(rate.sid);
  const c = await chart();
  expect(c.kind).toBe('series');
  expect(c.metric, 'the chart is about the goal metric').toBe('close_rate');
  expect(c.unit).toBe('ratio');
  expect(c.heading).toMatch(/CLOSE RATE/i);
  expect(c.points.map(p => p.v), 'one dot per valid observation, in time order').toEqual([0.15, 0.2, 0.25]);
  expect(c.lines, 'one population: the dots are joined').toBe(1);
  expect(c.target).toBe(0.25);
  expect(c.baseline).toBe(0.15);
  expect(c.axisText.join(' '), 'the axis speaks percent').toMatch(/25%/);
  expect(c.axisText.join(' '), 'no rupiah on a rate axis').not.toMatch(/Rp/);
  expect(c.tableValues, 'the same observations as an accessible table').toEqual(['15%', '20%', '25%']);
  expect(c.limits, 'the two rejected measurements are said, not hidden').toMatch(/2 measurements recorded but not plotted/);
  expect(c.limits).toMatch(/period/);
  expect(c.assessment, 'the assessment is the server\'s').toBe(st.goal_measured.status);
  expect(await incomeChartCount(), 'no monthly-income chart stands in for the goal').toBe(0);
  expect(await page.locator('#v11-main').innerText()).not.toMatch(/MONTHLY INCOME, AND THE PATH BEHIND IT/);
  await shotBoth('jg1-rate');
});

// ── JG-2 · count goal ───────────────────────────────────────────────────────────────────────────────
test('JG-2 · count goal: qualified leads as a count, no % and no Rp on the axis', async () => {
  count = await makeSession({ goal_text: 'I need three qualified leads in 14 days', metric_id: 'qualified_leads', target: 3, measurement_window_days: 14,
    success_definition: 'qualified = B2B owner who booked a discovery call' });
  const g = count.gid, t = nowSec();
  await seed(g, t - 12 * DAY, { kind: 'event', event_id: 'a', event_ts: t - 13 * DAY, qualified: true });
  await seed(g, t - 5 * DAY, { kind: 'event', event_id: 'b', event_ts: t - 6 * DAY, qualified: true });
  await seed(g, t - 1 * DAY, { kind: 'event', event_id: 'c', event_ts: t - 2 * DAY, qualified: true });
  await openMap(count.sid);
  const c = await chart();
  expect(c.metric).toBe('qualified_leads');
  expect(c.unit).toBe('leads');
  expect(c.heading).toMatch(/QUALIFIED LEADS/i);
  expect(c.points.map(p => p.v), 'counts in the window at each observation: 1, 2, 3 (the 12-day-old one is still inside 14 days)').toEqual([1, 2, 3]);
  expect(c.target).toBe(3);
  expect(c.baseline).toBeNull();
  expect(c.axisText.join(' ')).not.toMatch(/Rp|%/);
  expect(await incomeChartCount()).toBe(0);
  await shotBoth('jg2-count');
});

// ── JG-3 · revenue goal ─────────────────────────────────────────────────────────────────────────────
test('JG-3 · revenue goal keeps its monthly-income chart and gets no second, goal-relative one', async () => {
  revenue = await makeSession({ goal_text: 'I want Rp20 million a month from consulting in 90 days.' });
  await openMap(revenue.sid);
  expect(await chart(), 'revenue goal: no goal-relative chart').toBeNull();
  await expect(page.locator('#v11-main')).toContainText('MONTHLY INCOME, AND THE PATH BEHIND IT');
  expect(await incomeChartCount()).toBe(1);
  await shotBoth('jg3-revenue');
});

// ── JG-4 · nothing valid yet ────────────────────────────────────────────────────────────────────────
test('JG-4 · no valid observation: the target and what is missing are said, nothing is drawn, missing is not zero', async () => {
  const s = await makeSession({ goal_text: 'Our close rate is about 15%. I want 25% in 60 days.', metric_id: 'close_rate', target: 0.25, measurement_window_days: 60 });
  await seed(s.gid, nowSec() - 4 * DAY, { kind: 'rate', numerator: 6, denominator: 20, cohort: 'inbound', period: 'last quarter' });
  await openMap(s.sid);
  const c = await chart();
  expect(c.empty).toBe('no-observations');
  expect(c.hasSvg, 'no axis, no dots, no line').toBe(false);
  expect(c.text).toMatch(/No valid observation of close rate yet/i);
  expect(c.text).toMatch(/Goal\s+25% or more in 60-day windows/);
  expect(c.text).toMatch(/Not measured yet/);
  expect(c.limits).toMatch(/1 measurement recorded but not plotted: the period could not be pinned to exact dates/);
  expect(c.text, 'a missing value is not zero').not.toMatch(/\b0%/);
  await shotBoth('jg4-no-valid');
});

// ── JG-5 · one observation ──────────────────────────────────────────────────────────────────────────
test('JG-5 · one valid observation is a dot: no line, no trend, and the note says why', async () => {
  const s = await makeSession({ goal_text: 'Our close rate is about 15%. I want 25% in 60 days.', metric_id: 'close_rate', target: 0.25, measurement_window_days: 60 });
  await rateObs(nowSec() - 5 * DAY, 3, 20, { gid: s.gid });
  await openMap(s.sid);
  const c = await chart();
  expect(c.points.map(p => p.v)).toEqual([0.15]);
  expect(c.lines).toBe(0);
  await expect(page.locator('[data-j-one]')).toContainText('no trend is drawn');
  await shotBoth('jg5-one-dot');
});

// ── JG-6 · criteria goal ────────────────────────────────────────────────────────────────────────────
test('JG-6 · a goal judged by evidence criteria gets a typed list and no numeric axis', async () => {
  const s = await makeSession({ goal_text: 'I want to validate that people will pay for this', metric_id: 'wtp_validated' });
  await seed(s.gid, nowSec() - 2 * DAY, { kind: 'criteria', criterion: 'paid deposit', met: true });
  await seed(s.gid, nowSec() - 1 * DAY, { kind: 'criteria', criterion: 'second purchase', met: null });
  await openMap(s.sid);
  const c = await chart();
  expect(c.kind).toBe('unsupported');
  expect(c.empty).toBe('unsupported');
  expect(c.hasSvg).toBe(false);
  expect(c.text).toMatch(/paid deposit\s+Met/);
  expect(c.text).toMatch(/second purchase\s+Not known/);
  expect(await incomeChartCount()).toBe(0);
  await shotBoth('jg6-criteria');
});

// ── JG-7 · evidence under an earlier definition ─────────────────────────────────────────────────────
test('JG-7 · evidence recorded under an earlier definition of the goal is not plotted, and that is said', async () => {
  const s = await makeSession({ goal_text: 'Our close rate is about 15%. I want 25% in 60 days.', metric_id: 'close_rate', target: 0.25, measurement_window_days: 60,
    success_definition: 'won = signed contract' });
  const g = s.gid, t = nowSec();
  await rateObs(t - 30 * DAY, 3, 20, { gid: g });
  // the meaning of "won" changes: what was measured before no longer measures the same thing
  const rev = await apiJson('/workspace/' + UID + '/goals/' + g + '/revise', { method: 'POST', data: { success_definition: 'won = first invoice paid' } });
  expect(rev.status).toBe(200);
  expect(rev.body.changed).toBe(true);
  await rateObs(t - 2 * DAY, 5, 20, { gid: g });
  await openMap(s.sid);
  const c = await chart();
  expect(c.points.map(p => p.v), 'only the evidence about the CURRENT definition is a dot').toEqual([0.25]);
  expect(c.limits).toMatch(/1 measurement recorded under an earlier definition of this goal is not plotted/);
  await shotBoth('jg7-incomparable');
});

// ── JG-8 · switching the active goal ────────────────────────────────────────────────────────────────
test('JG-8 · switching the active goal in one page: metric, unit, target and dots follow it, nothing is carried over', async () => {
  const go = async (sid) => {
    await page.evaluate((x) => loadMapSession(x), sid);
    await page.waitForFunction((x) => LIVE.sid === x && !!LIVE.state && !!LIVE.artifact, sid, { timeout: 30_000 });
    await page.evaluate(() => goDestination('journey'));
    await page.waitForTimeout(500);
  };
  await openMap(rate.sid);
  let c = await chart();
  expect([c.metric, c.unit, c.points.map(p => p.v)]).toEqual(['close_rate', 'ratio', [0.15, 0.2, 0.25]]);

  await go(count.sid);
  c = await chart();
  expect([c.metric, c.unit, c.points.map(p => p.v), c.target]).toEqual(['qualified_leads', 'leads', [1, 2, 3], 3]);
  expect(c.axisText.join(' '), 'the previous goal\'s axis did not stay').not.toMatch(/%/);
  expect(c.baseline).toBeNull();
  expect(c.heading).not.toMatch(/CLOSE RATE/i);
  await shot('jg8-switched-to-count-desktop');

  await go(revenue.sid);
  expect(await chart(), 'revenue: the goal-relative chart is gone').toBeNull();
  expect(await incomeChartCount()).toBe(1);
  await expect(page.locator('#v11-main')).not.toContainText('QUALIFIED LEADS, TOWARD YOUR GOAL');
  await shot('jg8-switched-to-revenue-desktop');

  await go(rate.sid);
  c = await chart();
  expect([c.metric, c.unit, c.points.map(p => p.v), c.target, c.baseline]).toEqual(['close_rate', 'ratio', [0.15, 0.2, 0.25], 0.25, 0.15]);
  expect(await incomeChartCount()).toBe(0);
});


// ── JG-10 · numerical value goal ────────────────────────────────────────────────────────────────────
test('JG-10 · numerical value goal: correct unit, direction, target, baseline and observations', async () => {
  // sales_cycle_days is a registry metric with value semantics: unit days, success = going DOWN to the threshold.
  const value = await makeSession({ goal_text: 'My sales cycle takes 45 days. I want it down to 20.', metric_id: 'sales_cycle_days', target: 20, baseline: 45 });
  const g = value.gid, t = nowSec();
  await seed(g, t - 9 * DAY, { kind: 'value', value: 45 });
  await seed(g, t - 2 * DAY, { kind: 'value', value: 38 });
  const st = (await apiJson('/session/' + value.sid + '/state')).body;
  expect(st.goal_series.kind, 'the server projects value semantics').toBe('value');
  expect(st.goal_series.unit).toBe('days');
  expect(st.goal_series.direction).toBe('DECREASE_TO_THRESHOLD');
  expect(st.goal_series.points.map(p => p.value), 'the server holds exactly the two observations').toEqual([45, 38]);
  await openMap(value.sid);
  const c = await chart();
  expect(c, 'a goal-relative chart is drawn').not.toBeNull();
  expect(c.kind).toBe('series');
  expect(c.metric, 'the chart is about the goal metric').toBe('sales_cycle_days');
  expect(c.unit, 'days, not rupiah, percent or a bare number').toBe('days');
  expect(c.heading).toMatch(/SALES CYCLE/i);
  expect(c.empty, 'a supported numeric goal is not shown as empty/unsupported').toBeNull();
  expect(c.hasSvg).toBe(true);
  expect(c.points.map(p => p.v), 'one dot per valid observation, in time order, as recorded').toEqual([45, 38]);
  expect(c.lines, 'one population: the dots are joined').toBe(1);
  expect(c.target).toBe(20);
  expect(c.baseline).toBe(45);
  expect(c.axisText.join(' '), 'no rupiah and no percent on a days axis').not.toMatch(/Rp|%/);
  expect(c.axisText.join(' '), 'the axis speaks days').toMatch(/days?/i);
  expect(c.tableValues.join(' '), 'the same observations as an accessible table').toMatch(/45[\s\S]*38/);
  expect(c.assessment, 'the assessment is the server\'s').toBe(st.goal_measured.status);
  expect(await incomeChartCount(), 'no monthly-income chart stands in for the goal').toBe(0);
  expect(await page.locator('#v11-main').innerText()).not.toMatch(/MONTHLY INCOME, AND THE PATH BEHIND IT/);
  await shotBoth('jg10-value');

  // leaving the value goal replaces everything: no days axis, target 20 or 45/38 dots survive on the rate goal
  await page.evaluate((x) => loadMapSession(x), rate.sid);
  await page.waitForFunction((x) => LIVE.sid === x && !!LIVE.state && !!LIVE.artifact, rate.sid, { timeout: 30_000 });
  await rerender();
  const r = await chart();
  expect([r.metric, r.unit, r.points.map(p => p.v), r.target, r.baseline]).toEqual(['close_rate', 'ratio', [0.15, 0.2, 0.25], 0.25, 0.15]);
  expect(r.axisText.join(' '), 'the days axis did not stay').not.toMatch(/\b(20|45|38) days?\b/);
});

// ── JG-8b · check-ins on a non-revenue goal ─────────────────────────────────────────────────────────
test('JG-8b · check-ins on a non-revenue goal: the path lanes get their own card and carry no income and no income value', async () => {
  await openMap(rate.sid);
  await page.evaluate(() => {
    const snap = V11_ENGINE.snapshot(), pid = (snap.paths[0] || {}).id || 'warm', t = Date.now();
    // two reported check-ins (one with an income reported, which belongs to the revenue axis and must not show here)
    LIVE.checkins = [
      { ts: t - 3 * 86400000, rp: 4, outcome: 'paid', title: 'First reply', path: pid, contacted: 5, replies: 2, calls: 1, paid: 0 },
      { ts: t - 1 * 86400000, rp: 6, outcome: 'mixed', title: 'Second round', path: pid, contacted: 4, replies: 1, calls: 0, paid: 0 }
    ];
    LIVE.startTs = t - 4 * 86400000;
    goDestination('journey');
  });
  await page.waitForTimeout(500);
  const lanes = page.locator('[data-j-lanes]');
  await expect(lanes, 'the path lanes have their own card').toHaveCount(1);
  expect(await lanes.innerText(), 'no income and no Rp inside the lanes card').not.toMatch(/Rp|income/i);
  const c = await chart();
  expect(c.kind, 'the goal chart is still the close-rate chart').toBe('series');
  expect(c.points.map(p => p.v)).toEqual([0.15, 0.2, 0.25]);
  expect(await incomeChartCount(), 'no monthly-income chart appears because check-ins exist').toBe(0);
  const hist = await page.locator('.j-hist').innerText();
  expect(hist, 'the history lists the check-ins').toMatch(/Check-in 2/);
  expect(hist, 'and shows no income value under a close-rate goal').not.toMatch(/Rp\d/);
  await lanes.scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  await shot('jg8b-checkins-non-revenue-desktop');
  // a bar of the lanes opens its check-in tip, which says nothing about income either
  const bar = page.locator('[data-j-lanes] .j-node').first();
  await bar.focus();
  await expect(page.locator('#j-tip')).toBeVisible();
  expect(await page.locator('#j-tip').innerText()).not.toMatch(/Rp|income/i);
  await page.evaluate(() => { LIVE.checkins = []; });
});

test('JG-9 · nothing logged a console error', async () => {
  expect(consoleErrors, consoleErrors.join('\n')).toEqual([]);
  fs.writeFileSync(path.join(VISUAL, 'hashes.json'), JSON.stringify(hashes, null, 1));
});
