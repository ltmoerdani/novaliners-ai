// Goal-Relative Path State E2E (docs/02-product-concept/09 §6; GR-26..GR-30, UC-01..UC-09 workflows).
// Live UI against the real API with the mock LLM provider. Screenshots for visual QA are written to
// e2e/__visual__/goal-relative/ (inspected manually; they are not committed baselines).
//
// Contract guards here (mandate §12):
//   WF-A1 : a PURE non-revenue goal — no revenue target is ever typed; the UI must not borrow
//           revenue values/targets for the leads goal (A-01/A-02/A-03), and emerging paths carry
//           an EXPLICIT UNKNOWN_RELATION to the goal (A-05/A-07), never a silent relevance claim.
//   WF-A2 : an explicit revenue goal keeps the legacy revenue wording (A-29).
//   WF-E  : two goals in one workspace — outcome reporting is ASSERTED (never a swallowed error),
//           switching is explicit (activate + session rebind), destinations follow, and each
//           goal keeps its own history (A-19/A-21/A-22/A-17).
//   WF-G  : TALK answers from the ACTIVE goal and session (metric + target named; no context from
//           other sessions); a fact statement does not revise the record; an explicit revision is
//           recorded as an event with a new version (A-23/A-24/A-25).
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { scanCopy } from './copy-guard.mjs';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test.describe.configure({ mode: 'serial', timeout: 240_000 });

const here = path.dirname(fileURLToPath(import.meta.url));
const VISUAL = path.join(here, '__visual__', 'goal-relative');
fs.mkdirSync(VISUAL, { recursive: true });

let page, ctx;
const consoleErrors = [];
const UID = 'u_e2e_goal_' + Math.random().toString(16).slice(2, 8);
const PORT = 'http://127.0.0.1:' + (process.env.E2E_PORT || 8765);
const go = async (js) => { await page.evaluate(js); await page.waitForTimeout(150); };
// axe (WCAG 2 A/AA) + the copy guard on a screen that carries the new relation markers
const a11yCopy = async (where) => {
  const freeze = await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; }' });
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  await freeze.evaluate(el => el.remove());
  expect(r.violations.map(v => `${v.id} x${v.nodes.length}: ` + v.nodes.map(n => (n.any[0] && n.any[0].message || '') + ' @ ' + n.target.join(' ')).join(' | ')), `a11y on ${where}`).toEqual([]);
  expect(await scanCopy(page, { live: true }), `copy on ${where}`).toEqual([]);
};
const shot = async (name) => {
  await page.mouse.move(760, 880);   // no hover tooltip from a rail tile in the picture
  await expect(page.locator('#app-toast.show')).toHaveCount(0, { timeout: 8000 });
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(VISUAL, name + '.png'), fullPage: false });
};
const api = (p, init) => page.request.fetch(PORT + p, init);
const apiJson = async (p, init) => { const r = await api(p, init); return { status: r.status(), body: await r.json() }; };
// Build-the-diagnosis button: the chat re-renders after every answer, so the node can be
// replaced between locate and click. Clicking through the live handler is stable.
const buildDiagnosis = async () => {
  await page.waitForTimeout(400);
  await page.evaluate(() => {
    if (typeof finalizeEarly === 'function') { finalizeEarly(); return; }
    const el = [...document.querySelectorAll('a,button')].find(b => /Build my diagnosis/i.test(b.textContent || ''));
    if (el) el.click();
  });
  try {
    await page.waitForURL(/#\/diagnosis\/(provisional|result)|#\/state/, { timeout: 90_000 });
  } catch {
    test.info().annotations.push({ type: 'url-wait', description: 'at ' + page.url() });
  }
  await page.waitForTimeout(1500);
  test.info().annotations.push({ type: 'after-build', description: 'url=' + page.url() });
};
const startMap = async (goalText) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', goalText);
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page).toHaveURL(/#\/diagnosis$/);
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
};

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  const now = new Date();
  await page.clock.setFixedTime(new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0));
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  // Every fresh navigation starts as a new visitor of this user id. A test that wants a real browser RELOAD (what the
  // app saved stays) sets the sessionStorage flag first, so the app's own boot path restores the open map (WF-E).
  await page.addInitScript((uid) => {
    try {
      if (sessionStorage.getItem('e2e-keep-ls')) { sessionStorage.removeItem('e2e-keep-ls'); return; }
      localStorage.setItem('novaliners-v9', JSON.stringify({ userId: uid, chain: [], checkins: [], overrides: [], tips: {} }));
    } catch (e) { /* ignore */ }
  }, UID);
});

test.afterAll(async () => { await ctx.close(); });

// ── Workflow C + D: ambiguous "traction" and a valid zero-path goal ──────────────────────────
test('WF-C/D · traction desire stays a desire; a valid leads goal with no evidence shows an honest zero map', async () => {
  await startMap('The business is not moving. I need traction.');
  await expect(page.getByText(/clear goal|What do you want to reach/i).first()).toBeVisible({ timeout: 15_000 });
  await shot('wf-c-traction-clarification');
  await page.fill('#diag-chat-input', 'What I mean by traction: three qualified leads in 14 days. A qualified lead is a B2B owner with budget who books a discovery call.');
  await page.keyboard.press('Enter');
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  await buildDiagnosis();
  await go("goDestination('state')");
  await expect(page.locator('.dest-hero, #v11-main').first()).toContainText(/qualified leads/i);
  await expect(page.locator('#dest-rail')).toContainText('Qualified leads now');
  await shot('wf-d-state-leads-goal');
  const railNumbers = await page.locator('#dest-rail .dest-numbers').innerText();
  expect(railNumbers, 'A-03: unmeasured leads stay unknown').toMatch(/Qualified leads now/i);
  expect(railNumbers).toMatch(/Not set/i);
  expect(railNumbers, 'A-02: no revenue unit in the leads figures').not.toMatch(/a month/i);
  await go("goDestination('maps')");
  await expect(page.locator('#v11-main')).toContainText(/No path is shown|Not enough is known|No path applies|not defined enough|cannot evaluate yet/i);
  await expect(page.locator('#v11-main')).toContainText(/3 qualified leads in\s+14 days/i);   // the goal chip may wrap onto two lines
  await shot('wf-d-maps-zero-paths');
  expect(consoleErrors).toEqual([]);
});

// ── Workflow A1: a PURE non-revenue goal reaches real paths with an explicit relation ─────────
let sidA;
test('WF-A1 · evidence opens paths for the leads goal; paths admit UNKNOWN relation; Moves and Journey stay honest', async () => {
  // A fresh map whose stated goal is already typed: 3 qualified leads in 14 days. Income is
  // stated as a FACT (real context) but NO revenue target is ever added — the old test typed
  // "My target is to grow to Rp60 juta per month", which mixed goals and proved nothing about
  // a non-revenue goal (mandate §12.1).
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', 'I need three qualified leads in the next 14 days for my consulting service.');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page).toHaveURL(/#\/diagnosis$/);
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  sidA = await page.evaluate(() => LIVE.sid);
  await page.fill('#diag-chat-input', 'A qualified lead is a B2B owner with budget who books a discovery call. I currently earn Rp30 juta per month from 3 retainer clients, and replies are slow lately.');
  await page.keyboard.press('Enter');
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  await buildDiagnosis();
  await go("goDestination('maps')");
  await page.waitForTimeout(800);
  const snapPaths = await page.evaluate(() => (V11_ENGINE.snapshot().paths || []).length);
  test.info().annotations.push({ type: 'wf-a1', description: 'paths after evidence: ' + snapPaths });
  expect(snapPaths, 'evidence opened real paths for the leads goal').toBeGreaterThan(0);
  await shot('wf-a-maps-with-paths');
  // A-05/A-07: every emerging path states its relation to the leads goal — revenue-conditioned
  // emergence alone is NOT claimed as goal-relevant (no silent metadata relevance).
  const fin = await (await api('/session/' + sidA + '/diagnosis')).json();
  const ppPaths = ((fin.possible_paths || {}).paths) || [];
  expect(ppPaths.length, 'diagnosis carries the path set').toBeGreaterThan(0);
  expect(ppPaths.every(p => p.goal_relation === 'UNKNOWN_RELATION'),
    'A-05: paths admit UNKNOWN_RELATION to the leads goal').toBe(true);
  expect(ppPaths[0].goal_relation_note || '').toMatch(/Knowledge/i);
  // F-01: the relation survives response → snapshot → view-model, and is SPOKEN in user language
  const snapRel = await page.evaluate(() => (V11_ENGINE.snapshot().paths || []).map(p => p.goal_relation));
  expect(snapRel.length, 'snapshot paths carry relation').toBeGreaterThan(0);
  expect(snapRel.every(r => r === 'UNKNOWN_RELATION'), 'F-01: snapshot keeps UNKNOWN_RELATION').toBe(true);
  const relModels = await page.evaluate(() => livePathModels().map(p => ({ id: p.key, rel: p.goalRelation, line: p.relationLine })));
  expect(relModels.length, 'view-model paths').toBeGreaterThan(0);
  expect(relModels.every(x => x.rel === 'UNKNOWN_RELATION'), 'F-01: view-model keeps UNKNOWN_RELATION').toBe(true);
  expect(relModels.every(x => /Hypothesis for your goal/.test(x.line)), 'F-01: relation spoken as a hypothesis').toBe(true);
  // visible on the selected path detail (Maps), and marked in the STATE rail
  const firstKey = await page.evaluate(() => (livePathModels()[0] || {}).key);
  await page.evaluate((k) => openMapsAt(k), firstKey);
  await page.waitForTimeout(600);
  await expect(page.locator('#v11-main'), 'F-01: hypothesis note visible on the path detail')
    .toContainText('Hypothesis for your goal');
  await shot('wf-a-maps-with-paths');
  // STATE rail: goal is still the leads goal; the revenue FACT never becomes the goal's number
  await go("goDestination('state')");
  await page.waitForTimeout(500);
  await expect(page.locator('#dest-rail')).toContainText('Qualified leads now');
  // F-14: the MAIN narrative serves the active goal too (not a canned revenue story)
  const stateText = await page.locator('#v11-main').innerText();
  expect(stateText, 'F-14: no foreign revenue target in the narrative').not.toContain('Rp20');
  expect(stateText, 'F-14: narrative names the active goal measure').toMatch(/qualified leads/i);
  expect(stateText, 'F-14: parsed target stays a recorded intention').toMatch(/not yet confirmed|recorded/i);
  await expect(page.locator('#dest-rail'), 'F-01: hypothesis marked in the STATE rail')
    .toContainText('· hypothesis');
  const railNumbers = await page.locator('#dest-rail .dest-numbers').innerText();
  expect(railNumbers, 'A-01: the goal figure is the leads goal').toContain('3 qualified leads in 14 days');
  expect(railNumbers, 'A-02: measured income never renders as qualified leads')
    .not.toMatch(/a month/i);
  await shot('wf-a-state-with-paths');
  await go("goDestination('moves')");
  await page.waitForTimeout(400);
  const moveText = await page.locator('#v11-main').innerText();
  expect(moveText, 'Moves says doing is not proving').toMatch(/does not say it worked|Any order works/i);
  await shot('wf-a-moves');
  // An action completed via the API leaves the goal trajectory honestly unknown (GR-22/A-26)
  const firstAction = (fin.day_by_day || [])[0];
  if (firstAction) {
    const rep = await api('/session/' + sidA + '/action/0/report', { method: 'POST', data: { status: 'DONE' } });
    expect(rep.status(), 'action report is asserted, not assumed').toBeLessThan(500);
  }
  const goalsView = await apiJson('/workspace/' + UID + '/goals');
  const leadsGoal = (goalsView.body.goals || []).find(g => g.metric_id === 'qualified_leads');
  expect(leadsGoal, 'the workspace has the leads goal').toBeTruthy();
  const traj = await apiJson('/workspace/' + UID + '/goals/' + leadsGoal.goal_id + '/trajectory');
  expect(traj.body.goal_trajectory.status, 'GR-22: action DONE did not fake an outcome').toBe('INSUFFICIENT_DATA');
  await go("goDestination('journey')");
  await page.waitForTimeout(500);
  const journeyText = await page.locator('#v11-main').innerText();
  expect(journeyText, 'A-27: Journey does not declare the leads goal achieved').not.toMatch(/goal (is )?(reached|achieved|done)/i);
  expect(journeyText, 'Journey names the active goal measure').toMatch(/qualified leads/i);
  await shot('wf-f-journey-honest');
  // Phase 5: the plain-language explanation serves THIS goal. It is the mock's own output (derived from the pack),
  // checked by the server's goal guard; no scenario fact from another session may appear.
  const ex = await (await api('/session/' + sidA + '/explain?refresh=true')).json();
  const exText = JSON.stringify([ex.summary, ex.blocking_title, ex.blocking_body, ex.do_title, ex.do_why, ex.done_when,
    ex.hold_title, ex.hold_body, ex.why, (ex.paths || []).map(p => [p.why, p.next, p.opening, p.supported, p.holding, p.unclear])]);
  expect(exText, 'PlainExplain names the leads goal').toMatch(/qualified leads/i);
  expect(exText, 'PlainExplain has no foreign scenario fact').not.toMatch(/8 years|marketing manager|Rp20|one-page service offer/i);
  expect(ex.guard.goal.checked, 'the goal guard ran').toBe(true);
  expect(ex.guard.goal.violations_after_repair, 'nothing contradicting the goal is shown').toEqual([]);
  expect(ex.summary.join(' '), 'unmeasured stays unmeasured, not zero').toMatch(/no measurement of/i);
  expect(ex.summary.join(' '), 'a parsed target is not a confirmed one').toMatch(/not yet confirmed/i);
  await go("renderScreen('17')");   // no session reload: the transient next-move headline must survive for WF-R
  await page.waitForTimeout(1200);
  const diagText = await page.locator('#v11-main, body').first().innerText();
  expect(diagText, 'Diagnosis screen has no foreign scenario fact').not.toMatch(/8 years of|marketing manager|Rp20 million/i);
  await shot('wf-p5-diagnosis-explain');
});

// ── Phase 4 (ronde 4): UNKNOWN_RELATION is visible on EVERY Maps surface, not only in the detail panel ──
test('WF-R · the unknown relation shows on cards, canvas, Explore, Readiness and Moves; status words stay the evidence\'s', async () => {
  const STATUS = ['OPEN', 'TEST FIRST', 'NOT YET', 'STOP'];
  await go("goDestination('maps')");
  const paths = await page.evaluate(() => (V11_ENGINE.snapshot().paths || []).map(p => ({ id: p.id, status: p.status_display, rel: p.goal_relation })));
  expect(paths.length, 'the leads map has paths').toBeGreaterThan(0);
  expect(paths.every(p => p.rel === 'UNKNOWN_RELATION'), 'every path of the leads goal is a hypothesis').toBe(true);
  expect(paths.every(p => STATUS.includes(p.status)), 'status words are the evidence\'s, never "hypothesis"').toBe(true);
  const n = paths.length;
  const lensRendered = async (view) => { await go(`setMapsView('${view}')`); await page.waitForTimeout(500); };

  // LANDSCAPE · cards in the list
  await lensRendered('landscape');
  if (n > 1) {
    const cards = page.locator('#mp-list .mp-card');
    expect(await cards.count(), 'cards for the visible paths').toBeGreaterThan(0);
    for (let i = 0; i < await cards.count(); i++) {
      const c = cards.nth(i);
      await expect(c.locator('.mp-rel'), 'card ' + i + ' carries the hypothesis chip').toHaveText('Hypothesis');
      await expect(c.locator('[data-testid=card-relation]'), 'card ' + i + ' states the link to the goal').toContainText(/Not shown yet/);
      expect(await c.locator('.mp-state').innerText(), 'the status word on the card is the evidence\'s').toMatch(/^(OPEN|TEST FIRST|NOT YET|STOP)/);
    }
  }
  // LANDSCAPE · canvas (the flat map is the only canvas — 3D removed, owner 18 Oct): the label itself
  // says hypothesis (screen readers get it too)
  await go("goDestination('maps'); STORE.mapsView = 'landscape'"); await page.waitForTimeout(400);
  const lanes = page.locator('.v12-lane-label');
  expect(await lanes.count(), '2D lane labels').toBeGreaterThan(0);
  for (let i = 0; i < await lanes.count(); i++) {
    expect(await lanes.nth(i).getAttribute('aria-label'), '2D lane ' + i + ' accessible name').toMatch(/hypothesis/);
    expect(await lanes.nth(i).textContent(), '2D lane ' + i + ' visible label').toMatch(/hypothesis/);
  }
  await a11yCopy('WF-R landscape 2D');
  await shot('wf-r-landscape-2d');
  /* the 3D leg was removed with the isometric view (owner, 18 Oct; doc 15 GAP-05) */
  // LANDSCAPE · selection strip
  const firstId = paths[0].id;
  await go(`mapsSelect('${firstId}')`); await page.waitForTimeout(400);
  await expect(page.locator('#mp-panel [data-testid=path-relation]'), 'selection strip sentence').toContainText('Hypothesis for your goal');
  await expect(page.locator('[data-testid=legend-hypothesis]').first()).toBeAttached();

  // EXPLORE · cards and the selection strip (the old Overview lens was merged into Explore: UX v11, doc 16 G-34)
  await lensRendered('landscape');
  if (n > 1) {
    const cards = page.locator('#mp-list .mp-card');
    for (let i = 0; i < await cards.count(); i++) {
      await expect(cards.nth(i).locator('.mp-rel'), 'explore card ' + i).toHaveText('Hypothesis');
    }
  }
  await go(`mapsSelect('${firstId}')`); await page.waitForTimeout(400);
  await expect(page.locator('#mp-panel [data-testid=path-relation]'), 'Explore panel sentence').toContainText('Hypothesis for your goal');
  await expect(page.locator('#mp-panel .mp-statusline .mp-rel'), 'Explore panel chip').toHaveText('Hypothesis');
  await a11yCopy('WF-R explore cards');
  await shot('wf-r-explore-cards');

  // READINESS · list and detail
  await lensRendered('readiness');
  const items = page.locator('.rd-path-item');
  expect(await items.count(), 'readiness path list').toBe(n);
  for (let i = 0; i < n; i++) await expect(items.nth(i).locator('.mp-rel'), 'readiness item ' + i).toHaveText('Hypothesis');
  await expect(page.locator('#rd-detail [data-testid=path-relation]'), 'readiness detail sentence').toContainText('Hypothesis for your goal');
  await a11yCopy('WF-R readiness');
  await shot('wf-r-readiness');

  // MOVES · only elements that are BOUND to a path carry the relation (also-ready rows, the evidence ask of the
  // engine's next move, route tasks). The plan's own steps come from the diagnosis, not from a path: no claim there.
  await go("goDestination('moves')"); await page.waitForTimeout(500);
  const alsoRows = page.locator('.moves-q-row:has(.moves-q-link[onclick*="openMapsAt"])');
  const alsoN = await alsoRows.count();
  for (let i = 0; i < alsoN; i++) await expect(alsoRows.nth(i).locator('.mp-rel'), 'Moves: also-ready row ' + i).toHaveText('Hypothesis');
  const routeRows = page.locator('.route-task');
  for (let i = 0; i < await routeRows.count(); i++) await expect(routeRows.nth(i).locator('.mp-rel'), 'Moves: route task ' + i).toHaveText('Hypothesis');
  const asksPath = await page.evaluate(() => { const n = V11_ENGINE.snapshot().nextmove; const p = n && n.path_id && (V11_ENGINE.snapshot().paths || []).find(x => x.id === n.path_id); return p ? p.goal_relation : null; });
  const asksChip = await page.locator('.moves-q:has(.section-meta-label:text("NEEDS EVIDENCE")) .mp-rel').count();
  expect(asksChip, 'Moves: the evidence ask carries the chip exactly when its path is a hypothesis').toBe(asksPath === 'UNKNOWN_RELATION' ? 1 : 0);
  expect(await page.locator('[data-testid=move-relation]').count(), 'Moves: no blanket claim that the plan step belongs to a path').toBe(0);
  test.info().annotations.push({ type: 'wf-r-moves', description: `also-ready rows=${alsoN}, route tasks=${await routeRows.count()}, ask path relation=${asksPath}` });
  expect(alsoN + await routeRows.count() + asksChip, 'Moves shows at least one path-bound element in this scenario').toBeGreaterThan(0);
  await a11yCopy('WF-R moves');
  await shot('wf-r-moves');

  // MOBILE 390 · the marker stays visible and nothing overflows
  await page.setViewportSize({ width: 390, height: 844 });
  for (const view of ['landscape', 'readiness']) {
    await go("goDestination('maps')");
    await lensRendered(view);
    const probe = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth;
      const chips = [...document.querySelectorAll('#v11-main .mp-rel')];
      return { overflow: document.documentElement.scrollWidth - vw, chips: chips.length,
        outside: chips.filter(c => { const r = c.getBoundingClientRect(); return r.right > vw + 1 || r.left < -1; }).length };
    });
    expect(probe.overflow, 'no horizontal overflow on mobile ' + view).toBeLessThanOrEqual(1);
    expect(probe.chips, 'hypothesis marker present on mobile ' + view).toBeGreaterThan(0);
    expect(probe.outside, 'hypothesis marker inside the viewport on mobile ' + view).toBe(0);
    await a11yCopy('WF-R mobile ' + view);
    await shot('wf-r-mobile-' + view);
    if (view === 'landscape') { await page.locator('#mp-list').scrollIntoViewIfNeeded(); await shot('wf-r-mobile-cards'); }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  expect(consoleErrors).toEqual([]);
});

// ── Workflow A2: an explicit revenue goal keeps the revenue contract (backward compat) ───────
test('WF-A2 · explicit revenue goal keeps revenue wording end to end', async () => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', 'We currently make Rp30 million per month and want to reach Rp60 million per month within 90 days.');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page).toHaveURL(/#\/diagnosis$/);
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  const sidR = await page.evaluate(() => LIVE.sid);
  await buildDiagnosis();
  await go("goDestination('state')");
  await page.waitForTimeout(500);
  const rail = await page.locator('#dest-rail').innerText();
  expect(rail, 'A-29: revenue goal keeps Income now + revenue unit').toMatch(/Income now/i);
  expect(rail, 'the value keeps its revenue unit (a month / monthly revenue)').toMatch(/a month|monthly revenue/i);
  expect(rail).toMatch(/Rp60/i);
  const stateText = await page.locator('#v11-main').innerText();
  expect(stateText, 'F-14: revenue narrative serves ITS OWN goal (Rp60), not a canned one').toContain('Rp60');
  expect(stateText, 'F-14: no foreign canned target').not.toContain('Rp20');
  const fin = await (await api('/session/' + sidR + '/diagnosis')).json();
  const pp = ((fin.possible_paths || {}) || {});
  expect(((pp.context || {}).goal || {}).metric_id).toBe('revenue_monthly');
  if ((pp.paths || []).length) {
    expect(pp.paths.every(x => x.goal_relation === 'DIRECT_CONTRIBUTION'),
      'revenue goal: DIRECT_CONTRIBUTION in the revenue space').toBe(true);
  }
  await shot('wf-a2-state-revenue');
  // Phase 4: the revenue space keeps its definitional relation; no hypothesis marker where none applies
  await go("goDestination('maps')"); await page.waitForTimeout(600);
  const revPaths = await page.evaluate(() => (V11_ENGINE.snapshot().paths || []).map(p => p.goal_relation));
  if (revPaths.length) {
    expect(revPaths.every(r => r === 'DIRECT_CONTRIBUTION'), 'revenue goal: DIRECT_CONTRIBUTION on every path').toBe(true);
    expect(await page.locator('#v11-main .mp-rel').count(), 'no hypothesis chip on a revenue map').toBe(0);
  }
});

// ── Workflow E: two goals, isolation and switching through the product surface, ALL FIVE destinations ──
// Goal A = 3 qualified leads in 14 days (session sidA, created in WF-A1). Goal B = close rate 25% in 60 days.
// Switching is done the way a person does it: the map tile in the left rail (and a full reload), plus the explicit
// activation contract of the API (workspace-level vs session rebind). After EVERY switch, the five destinations are
// read for the goal that is supposed to be on screen, and every screenshot is taken only after the screen was proven
// to belong to the goal in its name. Authoritative state (outcome, measurement, trajectory) is read back from the
// API, never inferred from the HTTP status.
let sidB, gidA, gidB, pathOnA;
const GOAL = {
  A: { own: [/qualified leads/i], foreign: [/close rate/i, /\b25 ?%/i], metric: 'qualified_leads', rail: 'Qualified leads now', label: 'QUALIFIED LEADS' },
  B: { own: [/close rate/i], foreign: [/qualified leads/i, /retainer/i], metric: 'close_rate', rail: 'Close rate now', label: 'CLOSE RATE' },
};
const sidOf = (k) => (k === 'A' ? sidA : sidB);
const hashes = {};
const sha = (buf) => crypto.createHash('sha1').update(buf).digest('hex');
const expectNoForeign = (text, k, where) => {
  for (const re of GOAL[k].foreign) expect(text, `${where}: nothing of the other goal (${re}) is on the ${k} screen`).not.toMatch(re);
};
// prove the screen belongs to goal k BEFORE reading or photographing it
const assertScreenIs = async (k, where) => {
  const probe = await page.evaluate(() => ({ sid: LIVE.sid, metric: ((V11_ENGINE.snapshot().goal || {}).metric || {}).id || null }));
  expect(probe.sid, `${where}: the open session is ${k}'s`).toBe(sidOf(k));
  expect(probe.metric, `${where}: the engine's goal context is ${k}'s metric`).toBe(GOAL[k].metric);
};
const snapshotShot = async (k, dest, tag) => {
  await assertScreenIs(k, `${tag} ${dest}`);
  // no hover tooltip from the rail click and no "Opening that map…" toast in the picture
  await page.mouse.move(760, 880);
  await expect(page.locator('#app-toast.show')).toHaveCount(0, { timeout: 8000 });
  await page.waitForTimeout(250);
  const buf = await page.screenshot({ path: path.join(VISUAL, `wf-e-${tag}-${dest}.png`), fullPage: false });
  hashes[`${tag}:${dest}`] = sha(buf);
};
const openDest = async (d) => { await go(`goDestination('${d}')`); await page.waitForTimeout(500); };
const waitMapLoaded = async (sid) => {
  await page.waitForFunction((x) => typeof LIVE !== 'undefined' && LIVE.sid === x && !!LIVE.artifact && !!LIVE.state, sid, { timeout: 30_000 });
  await page.waitForTimeout(600);
};
// switch the way a person does: the other map's tile in the left rail
const switchViaRail = async (k) => {
  const name = k === 'A' ? /I need three qualified leads/i : /Our close rate/i;
  await page.getByRole('button', { name }).first().click();
  await waitMapLoaded(sidOf(k));
};
// the five destinations, read for goal k
async function verifyFiveDestinations(k, tag, { measured, stopped, openStratIdOnB }) {
  const g = GOAL[k];
  // STATE
  await openDest('state');
  await expect(page.locator('#dest-rail'), `${tag} STATE rail names the goal`).toContainText(g.rail);
  const rail = await page.locator('#dest-rail .dest-numbers').innerText();
  if (measured != null) {
    expect(rail, `${tag} STATE: the workspace measurement is the value now`).toMatch(new RegExp(`\\b${measured}\\b`));
    expect(rail, `${tag} STATE: measured, so not "Not set"`).not.toMatch(/Not set/i);
  } else {
    expect(rail, `${tag} STATE: nothing measured stays unmeasured, never zero`).toMatch(/Not set/i);
  }
  const stateText = await page.locator('#v11-main').innerText();
  for (const re of g.own) expect(stateText, `${tag} STATE narrative serves ${k}`).toMatch(re);
  expectNoForeign(rail + ' ' + stateText, k, `${tag} STATE`);
  await snapshotShot(k, 'state', tag);

  // MAPS
  await openDest('maps');
  await go("setMapsView('landscape')"); await page.waitForTimeout(400);
  const paths = await page.evaluate(() => (V11_ENGINE.snapshot().paths || []).map(p => ({ id: p.id, status: p.status_display, rel: p.goal_relation, stop: p.stop_source })));
  if (k === 'A') expect(paths.length, `${tag} MAPS: A has paths`).toBeGreaterThan(0);
  expect(paths.every(p => p.rel === 'UNKNOWN_RELATION'), `${tag} MAPS: ${k}'s paths (if any) are hypotheses for ${k}`).toBe(true);
  const mapsText = await page.locator('#v11-main').innerText();
  for (const re of g.own) expect(mapsText, `${tag} MAPS names the goal (${paths.length} paths)`).toMatch(re);
  if (!paths.length) {
    // an honest zero map: it says why there is no path and names THIS goal, never another
    expect(mapsText, `${tag} MAPS: zero-path screen states the reason`).toMatch(/No path|Not enough is known|not defined enough|cannot evaluate yet/i);
  }
  const head = await page.locator('.mp-head, .v11-page-head').first().innerText();
  expect(head, `${tag} MAPS header carries nothing of the other goal`).not.toMatch(g.foreign[0]);
  const stoppedRow = paths.find(p => p.id === pathOnA);
  if (stopped === true) {
    expect(stoppedRow && stoppedRow.status, `${tag} MAPS: the path A stopped is STOP on A`).toBe('STOP');
  } else if (stopped === false && stoppedRow) {
    expect(stoppedRow.status, `${tag} MAPS: STOP on A does not block the same path on B (GR-19)`).not.toBe('STOP');
  }
  if (paths.length) await expect(page.locator('#v11-main .mp-rel').first(), `${tag} MAPS shows the relation as a hypothesis`).toBeVisible();
  await snapshotShot(k, 'maps', tag);

  // MOVES
  await openDest('moves');
  const movesText = await page.locator('#v11-main').innerText();
  expect(movesText, `${tag} MOVES: the plan serves ${k}'s measure`).toMatch(g.own[0]);
  expectNoForeign(movesText, k, `${tag} MOVES`);
  expect(movesText, `${tag} MOVES: a share is told as a percent, never as "0.25 ratio"`).not.toMatch(/0\.25 ratio/);
  expect(movesText, `${tag} MOVES: doing is not proving`).toMatch(/does not say it worked|Any order works/i);
  const alsoTitles = await page.locator('.moves-q:has(.section-meta-label:text("ALSO READY")) .moves-q-row span').allInnerTexts();
  if (stopped === true && stoppedRow) {
    const t = await page.evaluate((id) => { const p = (V11_ENGINE.snapshot().paths || []).find(x => x.id === id); return p ? p.title : ''; }, pathOnA);
    expect(alsoTitles.join(' '), `${tag} MOVES: the stopped path is not offered as ready`).not.toContain(t);
  }
  await snapshotShot(k, 'moves', tag);

  // JOURNEY
  await openDest('journey');
  const journeyText = await page.locator('#v11-main').innerText();
  expect(journeyText, `${tag} JOURNEY: the tracked measure is ${k}'s`).toContain(g.label);
  if (measured != null) {
    expect(journeyText, `${tag} JOURNEY: shows the measurement the workspace holds`).not.toMatch(/Not measured yet/i);
  } else {
    expect(journeyText, `${tag} JOURNEY: unmeasured stays "Not measured yet"`).toMatch(/Not measured yet/i);
  }
  expectNoForeign(journeyText, k, `${tag} JOURNEY`);
  expect(journeyText, `${tag} JOURNEY: no goal declared achieved by a finished step`).not.toMatch(/goal (is )?(reached|achieved|done)/i);
  await snapshotShot(k, 'journey', tag);

  // TALK
  await openDest('talk');
  await page.locator('#talk-ongoing-input').fill('Remind me which goal this map is about.');
  await page.keyboard.press('Enter');
  await expect(page.locator('#v11-main'), `${tag} TALK answered from the goal record`).toContainText(/your goal on record/i, { timeout: 30_000 });
  const talkText = await page.locator('#v11-main').innerText();
  expect(talkText, `${tag} TALK names ${k}'s goal`).toMatch(g.own[0]);
  expectNoForeign(talkText, k, `${tag} TALK`);
  await snapshotShot(k, 'talk', tag);
}

test('WF-E · outcome and measurement asserted from authoritative state; switching A→B→A across all five destinations', async () => {
  // ── Goal B arrives through the product (UI), Goal A already exists from WF-A1 ──
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', 'Our close rate is about 15%. I want 25% in 60 days.');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page).toHaveURL(/#\/diagnosis$/);
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  sidB = await page.evaluate(() => LIVE.sid);
  await page.fill('#diag-chat-input', 'We won 3 of 20 opportunities last quarter.');
  await page.keyboard.press('Enter');
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  await buildDiagnosis();
  await go("goDestination('state')");
  await expect(page.locator('#dest-rail')).toContainText('Close rate now');

  const goalsView = await apiJson('/workspace/' + UID + '/goals');
  // the workspace may hold several leads goals (WF-C/D made one too): A's id comes from A's own session
  const stA = (await apiJson('/session/' + sidA + '/state')).body;
  const stB = (await apiJson('/session/' + sidB + '/state')).body;
  gidA = stA.goal.goal_id;
  gidB = stB.goal.goal_id;
  expect(gidA, 'goal A id').toBeTruthy();
  expect(gidB, 'goal B id').toBeTruthy();
  expect(gidA).not.toBe(gidB);
  expect(stA.goal.metric_id, 'session A serves the leads goal').toBe('qualified_leads');
  expect(stB.goal.metric_id, 'session B serves the close rate goal').toBe('close_rate');
  expect(goalsView.body.goals.map(g => g.goal_id), 'both goals are in the workspace').toEqual(expect.arrayContaining([gidA, gidB]));
  expect(stA.goal_measured, 'nothing measured yet on A: null, never zero').toBeNull();
  expect(stB.goal_measured, 'nothing measured yet on B: null, never zero').toBeNull();

  // ── B first: all five destinations, nothing measured ──
  await verifyFiveDestinations('B', 'b1', { measured: null, stopped: null });

  // ── Goal A actions through the API, asserted against authoritative state ──
  const gA = goalsView.body.goals.find(g => g.goal_id === gidA);
  const evTs = Math.floor(Date.now() / 1000) - 2 * 86400;
  const body = { kind: 'event', event_id: 'lead-e2e-1', event_ts: evTs, qualified: true };
  const m1 = await apiJson('/workspace/' + UID + '/goals/' + gidA + '/measurements', { method: 'POST', data: body });
  expect(m1.status, 'valid measurement accepted').toBe(200);
  const m2 = await apiJson('/workspace/' + UID + '/goals/' + gidA + '/measurements', { method: 'POST', data: body });
  expect(m2.status, 'the same event reported twice is accepted').toBe(200);
  const wrongKind = await apiJson('/workspace/' + UID + '/goals/' + gidA + '/measurements',
    { method: 'POST', data: { kind: 'rate', numerator: 1, denominator: 2 } });
  expect(wrongKind.status, 'a rate on a count goal is rejected at the boundary').toBe(422);
  const trajA0 = (await apiJson('/workspace/' + UID + '/goals/' + gidA + '/trajectory')).body;
  expect(trajA0.goal_trajectory.counted, 'A-19: read back: one qualified lead counted once (event_id idempotent)').toBe(1);
  // below target: OFF_TRACK (one observation) or INSUFFICIENT_DATA (two observations, count flat) - never a direction
  expect(['OFF_TRACK', 'INSUFFICIENT_DATA'], 'one lead of three: factual, no direction claimed').toContain(trajA0.goal_trajectory.status);
  expect((m1.body.measurements || []).every(m => m.goal_version === gA.version), 'A-17: measurements carry goal_version').toBe(true);
  const trajB0 = (await apiJson('/workspace/' + UID + '/goals/' + gidB + '/trajectory')).body;
  expect(trajB0.goal_trajectory.status, 'A\'s measurement never enters B\'s trajectory').toBe('INSUFFICIENT_DATA');
  const finA = await (await api('/session/' + sidA + '/diagnosis')).json();
  const ka = (finA.knowledge_activation || {});
  const iid = ((ka.nba_grounding || {}).intervention_ids || [])[0]
    || (ka.interventions || [])[0]?.id
    || ((finA.day_by_day || []).find(a => a.intervention_id) || {}).intervention_id || 'PR-I02';
  pathOnA = (((finA.possible_paths || {}).paths) || [])[0]?.path_id;
  expect(pathOnA, 'map A has a path to report on').toBeTruthy();
  const rep = await apiJson('/session/' + sidA + '/nba_report', { method: 'POST', data: { intervention_id: iid, outcome: 'regret', path: pathOnA } });
  expect(rep.status, 'F-18: outcome report accepted (exact contract)').toBe(200);
  const readA = await (await api('/session/' + sidA + '/readiness')).json();
  expect(((readA.paths || []).find(p => p.path_id === pathOnA) || {}).lifecycle, 'F-18: persisted STOPPED read back on A').toBe('STOPPED');
  const readB = await (await api('/session/' + sidB + '/readiness')).json();
  const sameOnB = (readB.paths || []).find(p => p.path_id === pathOnA);
  if (sameOnB) expect(sameOnB.lifecycle, 'GR-19: the same path on B is NOT stopped').not.toBe('STOPPED');

  // explicit activation contract: workspace-level only (no session) does not move any session silently
  const actNoSession = await apiJson('/workspace/' + UID + '/goals/' + gidA + '/activate', { method: 'POST' });
  expect(actNoSession.status).toBe(200);
  expect(actNoSession.body.rebound, 'A-21: no session given → nothing rebound').toEqual({});
  expect((await apiJson('/session/' + sidB + '/state')).body.goal.goal_id, 'session B keeps goal B after an unrelated workspace activation').toBe(gidB);
  expect((await apiJson('/workspace/' + UID + '/goals')).body.active_goal_id, 'workspace default is now A').toBe(gidA);

  // ── Switch to A: explicit rebind, then the person opens A from the rail ──
  const actA = await apiJson('/workspace/' + UID + '/goals/' + gidA + '/activate?session_id=' + sidA, { method: 'POST' });
  expect(actA.status, 'activate A with session rebind').toBe(200);
  expect(actA.body.rebound.goal.goal_id).toBe(gidA);
  await switchViaRail('A');
  await verifyFiveDestinations('A', 'a1', { measured: 1, stopped: true });

  // ── Back to B (rail): B is clean, A's STOP and measurement did not travel ──
  const actB = await apiJson('/workspace/' + UID + '/goals/' + gidB + '/activate?session_id=' + sidB, { method: 'POST' });
  expect(actB.status, 'activate B with session rebind').toBe(200);
  expect(actB.body.rebound.goal.goal_id).toBe(gidB);
  await switchViaRail('B');
  await verifyFiveDestinations('B', 'b2', { measured: null, stopped: false });
  const goalsNow = (await apiJson('/workspace/' + UID + '/goals')).body;
  expect(goalsNow.goals.find(g => g.goal_id === gidB).status, 'B is not ACHIEVED by A\'s data').not.toBe('ACHIEVED');

  // ── A again after a FULL RELOAD: the session is restored through the app's own boot path ──
  await apiJson('/workspace/' + UID + '/goals/' + gidA + '/activate?session_id=' + sidA, { method: 'POST' });
  await switchViaRail('A');
  await page.evaluate(() => sessionStorage.setItem('e2e-keep-ls', '1'));
  await page.reload({ waitUntil: 'networkidle' });
  await waitMapLoaded(sidA);
  await verifyFiveDestinations('A', 'a2', { measured: 1, stopped: true });
  const trajA1 = (await apiJson('/workspace/' + UID + '/goals/' + gidA + '/trajectory')).body;
  expect(trajA1.goal_trajectory.counted, 'A keeps its measurement after the round trip').toBe(1);
  expect((await apiJson('/workspace/' + UID + '/goals/' + gidB + '/trajectory')).body.goal_trajectory.status, 'B still unmeasured').toBe('INSUFFICIENT_DATA');
  const readA2 = await (await api('/session/' + sidA + '/readiness')).json();
  expect(((readA2.paths || []).find(p => p.path_id === pathOnA) || {}).lifecycle, 'A\'s STOP survived the round trip').toBe('STOPPED');

  // ── screenshots prove what they claim: A and B differ on every destination; nothing was reused ──
  for (const d of ['state', 'maps', 'moves', 'journey', 'talk']) {
    expect(hashes[`a1:${d}`], `A and B look different on ${d}`).not.toBe(hashes[`b1:${d}`]);
    expect(hashes[`a2:${d}`], `A (after reload) and B look different on ${d}`).not.toBe(hashes[`b2:${d}`]);
  }
  // within one pass the five destinations are five different screens (no screenshot was reused for another screen)
  for (const tag of ['a1', 'b1', 'a2', 'b2']) {
    const five = ['state', 'maps', 'moves', 'journey', 'talk'].map(d => hashes[`${tag}:${d}`]);
    expect(new Set(five).size, `${tag}: five destinations, five different images`).toBe(5);
  }
  // the same goal looks the same after a round trip: A before and after the reload shows the same state screen
  expect(hashes['a2:state'], 'A is restored exactly: same state screen before and after the reload').toBe(hashes['a1:state']);
  // WF-G continues on map B: leave B open, the way a person would
  await switchViaRail('B');
  expect(consoleErrors).toEqual([]);
});

// ── Programmatic visual checks (DOM geometry): the goal surfaces must not clip, overlap or overflow ──
test('visual · desktop geometry: goal surfaces stay inside the viewport, nothing clipped or overlapped', async () => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const checkGeometry = async (where) => {
    const problems = await page.evaluate(() => {
      const out = [];
      const vw = document.documentElement.clientWidth;
      if (document.documentElement.scrollWidth > vw + 1) out.push('horizontal-overflow ' + document.documentElement.scrollWidth + '>' + vw);
      document.querySelectorAll('#dest-rail .dest-figure b, .dest-rail .dest-figure b').forEach(el => {
        const cs = getComputedStyle(el);
        if (el.scrollWidth > el.clientWidth + 2 && cs.overflow !== 'visible') out.push('clipped-text: ' + (el.textContent || '').slice(0, 40));
      });
      document.querySelectorAll('#dest-rail *, .dest-rail *').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width && r.right > vw + 2) out.push('rail-past-viewport: ' + (el.className || el.tagName));
      });
      return out;
    });
    expect(problems, 'geometry problems on ' + where).toEqual([]);
  };
  await go("goDestination('state')"); await page.waitForTimeout(400); await checkGeometry('state');
  await go("goDestination('maps')"); await page.waitForTimeout(500); await checkGeometry('maps');
  await go("goDestination('moves')"); await page.waitForTimeout(400); await checkGeometry('moves');
  await go("goDestination('journey')"); await page.waitForTimeout(400); await checkGeometry('journey');
  await go("goDestination('talk')"); await page.waitForTimeout(400); await checkGeometry('talk');
});

// ── GR-30: mobile viewport, zero and many paths stay readable ────────────────────────────────
test('GR-30 · mobile 390px: the same goal reads true with zero and multiple paths', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await go("goDestination('maps')");
  await page.waitForTimeout(500);
  const overflowX = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflowX, 'no horizontal overflow at 390px on Maps').toBeLessThanOrEqual(1);
  await shot('gr-30-mobile-maps');
  await go("goDestination('state')");
  await page.waitForTimeout(400);
  const overflowS = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflowS, 'no horizontal overflow at 390px on State').toBeLessThanOrEqual(1);
  await shot('gr-30-mobile-state');
  await page.setViewportSize({ width: 1440, height: 900 });
});

// ── Workflow G: TALK grounded in the ACTIVE goal and session; record changes only on request ──
test('WF-G · Talk names the active goal; a fact changes nothing; an explicit revision is an event', async () => {
  // session B (close rate goal) is the open map after WF-E
  await go("goDestination('talk')");
  await expect(page.locator('#v11-main h1').first()).toContainText(/talk/i);
  const input = page.locator('#talk-ongoing-input');
  await input.fill('What is my goal right now?');
  await page.keyboard.press('Enter');
  // deterministic wait: the answer's goal line (mock AskReply names the recorded goal)
  await expect(page.locator('#v11-main'), 'the talk page answered with the goal line')
    .toContainText(/your goal on record/i, { timeout: 30_000 });
  const talkText = await page.locator('#v11-main').innerText();
  expect(talkText.length, 'the talk page answered').toBeGreaterThan(40);
  // semantic assertions, not just length (A-23): the answer names THIS goal and its target
  expect(talkText, 'A-23: answer names the active metric').toMatch(/close rate/i);
  expect(talkText, 'A-23: answer names the active target').toMatch(/25/);
  expect(talkText, 'A-23: no context from session A leaks in').not.toMatch(/retainer/i);
  expect(talkText, 'A-23: no other goal named as active').not.toMatch(/qualified leads/i);
  await shot('wf-g-talk-grounded');
  // A-24: stating a FACT (not asking for a goal change) must not revise the record
  const goals0 = await apiJson('/workspace/' + UID + '/goals');
  const gidB = goals0.body.goals.find(g => g.metric_id === 'close_rate').goal_id;
  const before = goals0.body.goals.find(g => g.goal_id === gidB);
  await page.locator('#talk-ongoing-input').fill('For context: our team is four people and we sell to clinics.');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(2500);
  const after = (await apiJson('/workspace/' + UID + '/goals')).body.goals.find(g => g.goal_id === gidB);
  expect(after.target, 'A-24: a fact statement did not change the target').toBe(before.target);
  expect(after.version, 'A-24: a fact statement created no revision').toBe(before.version);
  // A-25: an EXPLICIT goal revision is recorded as an event with version + effective time
  const rev = await apiJson('/workspace/' + UID + '/goals/' + gidB + '/revise',
    { method: 'POST', data: { target: 0.3 } });
  expect(rev.body.changed, 'explicit revision applies').toBe(true);
  expect(rev.body.goal.version).toBe(before.version + 1);
  expect(rev.body.goal.effective_ts).toBeGreaterThan(0);
  const hist = (await apiJson('/workspace/' + UID + '/goals')).body.history
    .filter(h => h.goal_id === gidB && h.type === 'GOAL_REVISED');
  expect(hist.length, 'A-25: GOAL_REVISED event recorded').toBeGreaterThanOrEqual(1);
  expect(hist[hist.length - 1].goal.target).toBe(0.3);
  // a revision of B's target never touches A (separate goals, separate versions)
  const aAfter = (await apiJson('/workspace/' + UID + '/goals')).body.goals.find(g => g.goal_id === gidA);
  expect(aAfter.target, 'revising B left A\'s target at 3').toBe(3);
  expect(consoleErrors).toEqual([]);
});
