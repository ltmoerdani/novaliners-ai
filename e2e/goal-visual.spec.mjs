// Goal-Relative visual QA scenarios (ronde 4, Phase 7). Each scenario creates its own session through the API
// (mock LLM, deterministic), records measurements through the workspace API, then opens the map in the UI the way the
// app restores it, and asserts what the person SEES against the authoritative state read back from the API.
// Screenshots go to e2e/__visual__/goal-visual/ and are inspected by eye; DOM assertions never replace that.
//
//   VQ-1  rate: an invalid rate leaves the goal unmeasured; a valid one shows the rate; a bad one never replaces it
//   VQ-2  count: events that left the window are a measured ZERO (never ACHIEVED, never the old count)
//   VQ-3  revision: the historical version stays reconstructable; the current screen follows the active revision
//   VQ-4  an action marked DONE is not an outcome: nothing is achieved or measured by it
import { test, expect } from '@playwright/test';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test.describe.configure({ mode: 'serial', timeout: 240_000 });

const here = path.dirname(fileURLToPath(import.meta.url));
const VISUAL = path.join(here, '__visual__', 'goal-visual');
fs.mkdirSync(VISUAL, { recursive: true });
const PORT = 'http://127.0.0.1:' + (process.env.E2E_PORT || 8765);
const UID = 'u_e2e_vis_' + Math.random().toString(16).slice(2, 8);
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

// a session created through the API: goal + one conversational turn + synthesis (mock), returns ids
async function makeSession(body, turn) {
  const r = await apiJson('/session', { method: 'POST', data: { user_id: UID, ...body } });
  expect(r.status, 'session created').toBe(200);
  const sid = r.body.session_id;
  if (turn) {
    const m = await api('/session/' + sid + '/message', { method: 'POST', data: { text: turn } });
    expect(m.status(), 'turn accepted').toBeLessThan(300);
  }
  const f = await api('/session/' + sid + '/finalize', { method: 'POST' });
  expect(f.status(), 'diagnosis built').toBe(200);
  return { sid, gid: r.body.goal.goal_id };
}

// open a map the way the app restores one: its own boot path, from what the browser saved
async function openMap(sid, dest = 'state') {
  await page.evaluate(([uid, s]) => localStorage.setItem('novaliners-v9', JSON.stringify({ userId: uid, current: s, chain: [], checkins: [], overrides: [], tips: {} })), [UID, sid]);
  await page.evaluate(() => sessionStorage.setItem('e2e-keep-ls', '1'));
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForFunction((x) => typeof LIVE !== 'undefined' && LIVE.sid === x && !!LIVE.artifact && !!LIVE.state, sid, { timeout: 30_000 });
  await page.waitForTimeout(500);
  await page.evaluate((d) => goDestination(d), dest);
  await page.waitForTimeout(500);
}

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  await page.addInitScript(() => {
    try {
      if (sessionStorage.getItem('e2e-keep-ls')) { sessionStorage.removeItem('e2e-keep-ls'); return; }
    } catch (e) { /* ignore */ }
  });
  await page.goto('/', { waitUntil: 'networkidle' });
});
test.afterAll(async () => { await ctx.close(); });

const bothViewports = async (name, check) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(250);
  await check('desktop');
  await shot(name + '-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(350);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, name + ': no horizontal overflow at 390px').toBeLessThanOrEqual(1);
  await check('mobile');
  await shot(name + '-mobile');
  await page.setViewportSize({ width: 1440, height: 900 });
};
const railText = async () => (await page.locator('#dest-rail .dest-numbers').innerText());

// ── VQ-1 · rate ─────────────────────────────────────────────────────────────────────────────────────
test('VQ-1 · rate: an invalid rate leaves the goal unmeasured, a valid one shows, a bad one never replaces it', async () => {
  const { sid, gid } = await makeSession(
    { goal_text: 'Our close rate is about 15%. I want 25% in 60 days.', metric_id: 'close_rate', target: 0.25, measurement_window_days: 60 },
    'We won 3 of 20 opportunities last quarter.');
  const mUrl = '/workspace/' + UID + '/goals/' + gid + '/measurements';
  // 50% but with no cohort and no period: stored, never evidence
  const noScope = await apiJson(mUrl, { method: 'POST', data: { kind: 'rate', numerator: 10, denominator: 20 } });
  expect(noScope.status, 'stored as a record').toBe(200);
  expect(noScope.body.evaluation.status, 'NOT_COMPUTABLE: a number above the target is not achievement').toBe('NOT_COMPUTABLE');
  const t0 = (await apiJson('/workspace/' + UID + '/goals/' + gid + '/trajectory')).body;
  expect(t0.goal_trajectory.status).toBe('INSUFFICIENT_DATA');
  expect(t0.goal_trajectory.rejected[0].codes).toEqual(expect.arrayContaining(['RATE_COHORT_MISSING', 'RATE_PERIOD_MISSING']));
  expect((await apiJson('/session/' + sid + '/state')).body.goal_measured, 'unmeasured: null, not zero').toBeNull();
  await openMap(sid);
  await bothViewports('vq1-rate-invalid-state', async () => {
    await expect(page.locator('#dest-rail')).toContainText('Close rate now');
    expect(await railText(), 'the 50% without scope is NOT shown as the rate').toMatch(/Not set/i);
    expect(await railText()).not.toMatch(/50\s?%/);
  });
  // 6/20 = 30% is above the 25% target, but a period nobody can verify is not evidence of attainment (P1b):
  //   - a free label with no boundaries ("last quarter"): the length of the interval is unknown
  //   - a canonical label (2025-Q3 = 92 days) against a 60-day window: the interval is known and does not fit
  const unverifiable = await apiJson(mUrl, { method: 'POST', data: { kind: 'rate', numerator: 6, denominator: 20, cohort: 'inbound-q3', period: 'last quarter' } });
  expect(unverifiable.status, 'stored as a record').toBe(200);
  expect(unverifiable.body.evaluation.status, 'an unverifiable period never reaches ACHIEVED').toBe('NOT_COMPUTABLE');
  expect(unverifiable.body.evaluation.rejection_codes).toContain('RATE_PERIOD_UNVERIFIABLE');
  const wrongLength = await apiJson(mUrl, { method: 'POST', data: { kind: 'rate', numerator: 6, denominator: 20, cohort: 'inbound-q3', period: '2025-Q3' } });
  expect(wrongLength.body.evaluation.status, 'a 92-day period does not answer a 60-day window').toBe('NOT_COMPUTABLE');
  expect(wrongLength.body.evaluation.rejection_codes).toContain('RATE_PERIOD_MISMATCH');
  const t1 = (await apiJson('/workspace/' + UID + '/goals/' + gid + '/trajectory')).body.goal_trajectory;
  expect(t1.status, 'the trajectory follows the same contract').toBe('INSUFFICIENT_DATA');
  expect(t1.skipped, 'both are listed as rejected, none is dropped silently').toBeGreaterThanOrEqual(2);
  expect((await apiJson('/session/' + sid + '/state')).body.goal_measured, 'still unmeasured: null, not zero').toBeNull();
  // a valid one: 6/20 = 30% from a declared cohort and a 60-day period that has ended (window = 60)
  const periodOk = { cohort: 'inbound-q3', period: 'close-window-A', period_start_ts: nowSec() - 62 * DAY, period_end_ts: nowSec() - 2 * DAY };
  const ok = await apiJson(mUrl, { method: 'POST', data: { kind: 'rate', numerator: 6, denominator: 20, ...periodOk } });
  expect(ok.body.evaluation.status).toBe('ACHIEVED');
  expect(ok.body.evaluation.values.rate).toBe(0.3);
  // numerator above denominator: stored, rejected for evidence, the valid 30% stays
  const bad = await apiJson(mUrl, { method: 'POST', data: { kind: 'rate', numerator: 9, denominator: 3, ...periodOk } });
  expect(bad.body.evaluation.values.rate, 'the bad rate did not replace the valid one').toBe(0.3);
  expect(bad.body.evaluation.rejected_rate_measurements.items.at(-1).codes).toContain('RATE_NUMERATOR_EXCEEDS_DENOMINATOR');
  const st = (await apiJson('/session/' + sid + '/state')).body;
  expect(st.goal_measured.value).toBe(0.3);
  await openMap(sid);
  await bothViewports('vq1-rate-valid-state', async () => {
    expect(await railText(), 'the valid rate is the value now').toMatch(/30\s?%/);
    expect(await railText()).not.toMatch(/Not set/i);
  });
  await page.evaluate(() => goDestination('journey'));
  await page.waitForTimeout(600);
  expect(await page.locator('#v11-main').innerText(), 'JOURNEY shows the same rate').toMatch(/30\s?%/);
  await shot('vq1-rate-valid-journey-desktop');
});

// ── VQ-2 · count window ─────────────────────────────────────────────────────────────────────────────
let countSid, countGid;
test('VQ-2 · count: events that left the window are a measured zero, never achieved', async () => {
  ({ sid: countSid, gid: countGid } = await makeSession(
    { goal_text: 'I need three qualified leads in 14 days', success_definition: 'qualified = B2B owner who booked a discovery call', measurement_window_days: 14 },
    'A qualified lead is a B2B owner with budget who books a discovery call.'));
  const mUrl = '/workspace/' + UID + '/goals/' + countGid + '/measurements';
  for (const [i, d] of [30, 29, 28].entries()) {
    const r = await apiJson(mUrl, { method: 'POST', data: { kind: 'event', event_id: 'old-' + i, event_ts: nowSec() - d * DAY, qualified: true } });
    expect(r.status).toBe(200);
  }
  const ev = (await apiJson(mUrl, { method: 'POST', data: { kind: 'event', event_id: 'old-0', event_ts: nowSec() - 30 * DAY, qualified: true } })).body.evaluation;
  expect(ev.status, 'three events 28-30 days old, window 14: not achieved').toBe('NOT_ACHIEVED');
  expect(ev.values.counted, 'counted at evaluation time: zero').toBe(0);
  expect(ev.values.outside_window).toBe(3);
  const t = (await apiJson('/workspace/' + UID + '/goals/' + countGid + '/trajectory')).body.goal_trajectory;
  expect(t.counted).toBe(0);
  expect(['OFF_TRACK', 'INSUFFICIENT_DATA'], 'no direction claimed from expired events').toContain(t.status);
  expect((await apiJson('/session/' + countSid + '/state')).body.goal_measured.value, 'a measured zero is 0, not null').toBe(0);
  await openMap(countSid);
  await bothViewports('vq2-count-expired-state', async () => {
    await expect(page.locator('#dest-rail')).toContainText('Qualified leads now');
    const r = await railText();
    expect(r, 'the screen says 0 (measured), not "Not set"').toMatch(/\b0\b/);
    expect(r).not.toMatch(/Not set/i);
    expect(await page.locator('#v11-main').innerText(), 'nothing says the goal is reached').not.toMatch(/goal (is )?(reached|achieved)/i);
  });
});

// ── VQ-3 · revision and history ─────────────────────────────────────────────────────────────────────
test('VQ-3 · revision: history stays reconstructable, the screen follows the active revision', async () => {
  const mUrl = '/workspace/' + UID + '/goals/' + countGid + '/measurements';
  await apiJson(mUrl, { method: 'POST', data: { kind: 'event', event_id: 'new-1', event_ts: nowSec() - 2 * DAY, qualified: true } });
  const rev = await apiJson('/workspace/' + UID + '/goals/' + countGid + '/revise', { method: 'POST', data: { target: 5 } });
  expect(rev.body.changed).toBe(true);
  const v2 = rev.body.goal.version;
  expect(v2, 'a revision is a new version').toBeGreaterThan(1);
  const hist = (await apiJson('/workspace/' + UID + '/goals/' + countGid + '/trajectory?version=1')).body;
  expect(hist.historical.target, 'version 1 keeps its own target').toBe(3);
  expect(hist.historical.evaluation.evaluation_basis.mode, 'historical evaluation is its own mode').toBe('historical');
  const cur = (await apiJson('/workspace/' + UID + '/goals/' + countGid + '/trajectory')).body;
  expect(cur.goal_trajectory.target, 'the current evaluation follows the active revision').toBe(5);
  expect(cur.evaluation_basis.mode).toBe('current');
  expect(cur.excluded_incomparable, 'a target revision does not exclude any raw evidence').toBeUndefined();
  const act = await apiJson('/workspace/' + UID + '/goals/' + countGid + '/activate?session_id=' + countSid, { method: 'POST' });
  expect(act.body.rebound.goal.target, 'the session is rebound to the revised goal').toBe(5);
  expect(act.body.rebound.goal.target_origin, 'an explicit revision is the user\'s own input, not a parse').toBe('explicit_input');
  await openMap(countSid);
  await bothViewports('vq3-revised-state', async () => {
    await expect(page.locator('#dest-rail')).toContainText(/5 qualified leads/i);
    expect(await page.locator('#v11-main').innerText(), 'the revised target is no longer "not yet confirmed"').not.toMatch(/not yet confirmed/i);
    expect(await page.locator('#dest-rail').innerText(), 'the old target is not on the revised screen').not.toMatch(/\b3 qualified leads\b/i);
  });
});

// ── VQ-4 · an action DONE is not an outcome ─────────────────────────────────────────────────────────
test('VQ-4 · a finished action is not an outcome: nothing is measured or achieved by it', async () => {
  const before = (await apiJson('/workspace/' + UID + '/goals/' + countGid + '/trajectory')).body.goal_trajectory;
  const fin = await (await api('/session/' + countSid + '/diagnosis')).json();
  expect((fin.day_by_day || []).length, 'the plan has actions to mark').toBeGreaterThan(0);
  const rep = await api('/session/' + countSid + '/action/0/report', { method: 'POST', data: { status: 'DONE' } });
  expect(rep.status(), 'the report is accepted').toBe(200);
  const after = (await apiJson('/workspace/' + UID + '/goals/' + countGid + '/trajectory')).body.goal_trajectory;
  expect(after.counted, 'DONE added no measurement').toBe(before.counted);
  expect(after.status).toBe(before.status);
  const goal = (await apiJson('/workspace/' + UID + '/goals')).body.goals.find(g => g.goal_id === countGid);
  expect(goal.status, 'the goal is not achieved by a finished action').not.toBe('ACHIEVED');
  await openMap(countSid, 'journey');
  await bothViewports('vq4-action-done-journey', async () => {
    const text = await page.locator('#v11-main').innerText();
    expect(text, 'JOURNEY names the tracked measure').toContain('QUALIFIED LEADS');
    expect(text, 'no achievement is declared').not.toMatch(/goal (is )?(reached|achieved|done)/i);
  });
  expect(consoleErrors, 'no console error in any scenario').toEqual([]);
  // every screenshot is a different picture: nothing was reused as evidence for another state
  const names = Object.keys(hashes);
  expect(new Set(Object.values(hashes)).size, 'screenshots are distinct').toBe(names.length);
});
