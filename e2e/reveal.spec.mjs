// Reveal = a scene owned by State INSIDE the v11 shell (EER 00 §7.3 + doc 02/08 §13/§19.2; audit RV-01..RV-04,
// 17 Oct 2026). What is tested is not just layout: the diagnosis-result page must not become an onboarding
// dead end — five destinations must exist, the conversation stays one click away, and the step-card CTA follows
// the KIND of live decision (the same source as the Next Move card in State: V11_ENGINE.snapshot().nextmove),
// not a "start this path" button that is always shown. Conditions the mock does not reach (final, every step
// kind) are injected through the same seam as the other specs (V11_ENGINE.set + STORE.forceReveal).
import { test, expect } from '@playwright/test';
import { scanCopy } from './copy-guard.mjs';

test.describe.configure({ mode: 'serial' });

let page, ctx;
const consoleErrors = [];

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/favicon/i.test(m.text())) consoleErrors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  await page.addInitScript(() => { try { localStorage.setItem('novaliners-v9', JSON.stringify({ userId: 'u_e2ereveal' + Math.random().toString(16).slice(2, 8), chain: [], checkins: [], overrides: [], tips: {} })); localStorage.setItem('novaliners-theme', 'light'); } catch (e) { /* ignore */ } });
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

test('01 · RV-01: the provisional reveal lives inside the shell, not as a standalone dead end', async () => {
  await expect(page).toHaveURL(/#\/diagnosis\/provisional|#\/diagnosis\/result/);
  // five destinations in the top bar, State marked current (the reveal is a State-family scene)
  await expect(page.locator('.v11-topnav-item')).toHaveText(['State', 'Maps', 'Moves', 'Journey', 'Talk']);
  await expect(page.locator('.v11-topnav-item[aria-current="page"]')).toHaveText('State');
  await expect(page.locator('.v11-eyebrow')).toContainText('State');
  // the conversation stays one click away (RV-04), and the map exits are visible, not buried
  await expect(page.getByText('Review the conversation')).toBeVisible();
  await expect(page.getByRole('button', { name: /See your map/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Open State/ })).toBeVisible();
  expect(await scanCopy(page, { live: true }), 'copy on the provisional reveal').toEqual([]);
});

test('02 · RV-04: "Review the conversation" returns to the interview; the where-next row routes inside the shell', async () => {
  await page.getByText('Review the conversation').click();
  await expect(page.locator('#diag-chat-input')).toBeVisible();
  await page.evaluate(() => renderScreen('13'));
  await page.getByRole('button', { name: /Open State/ }).click();
  await expect(page).toHaveURL(/#\/state$/);
  await page.evaluate(() => { STORE.forceReveal = false; location.hash = '#/diagnosis/result'; });
  await page.getByRole('button', { name: /See your map/ }).click();
  await expect(page).toHaveURL(/#\/maps/);
  await page.evaluate(() => location.hash = '#/diagnosis/result');
});

/* Full reveal (03). The mock always builds a provisional read, so a final artifact is put in place the
   same way the state spec injects conditions: through LIVE + the snapshot seam. */
const fullReveal = (nextmoveSrc) => page.evaluate(`(function(){
  const d = JSON.parse(JSON.stringify(LIVE.artifact));
  d.status = 'final';
  d.confidence_band = 'MEDIUM';
  if (!(d.constraint_map || []).some(c => c.tier !== 'UNKNOWN')) {
    d.constraint_map = (d.constraint_map || []).concat([
      { constraint_id: 'rv-c1', name: 'The one thing', tier: 'PRIMARY', score: 4, effective_score: 4 },
      { constraint_id: 'rv-c2', name: 'Another', tier: 'SECONDARY', score: 1, effective_score: 1 }
    ]);
  }
  // the reveal reads paths from the artifact's own PathSet: give a thin one when the mock built none,
  // so the paths card (and its map exit) is present for these routing checks
  if (!(((d.possible_paths || {}).paths || []).length)) {
    const rvPath = (id, title, basis) => ({ path_id: 'path.' + id, strategy_id: id, title, status: 'TEST_FIRST', feasibility: 'UNDETERMINED', lifecycle: 'OPEN', motion: null, basis, checks: [], stop_provenance: [], route_substrate: { template_ids: [], available: false }, presentation: { en: { word: title, short: title, basis } } });
    d.possible_paths = { version: 3, unresolved: [], generation: {}, paths: [
      rvPath('rv_direct_outreach', 'Winning new clients', 'People already ask about you'),
      rvPath('rv_value_repricing', 'Repricing your offer', 'Your price is not written down yet')
    ] };
  }
  LIVE.artifact = d;
  const snap = JSON.parse(JSON.stringify(V11_ENGINE.snapshot()));
  (${nextmoveSrc})
  V11_ENGINE.set(v11MapKey(), snap);
  STORE.forceReveal = true;
  renderScreen('03');
})()`);

const stepCard = () => page.locator('.card-dark');

test('03 · RV-01: the full reveal also lives inside the shell, with the plan step labelled by its source', async () => {
  await fullReveal('snap.nextmove = null');
  await expect(page.locator('.v11-topnav-item[aria-current="page"]')).toHaveText('State');
  await expect(stepCard()).toContainText('Your first step · from this diagnosis');
  // the path list card carries a visible exit to the map, not only inside the collapsed list
  await expect(page.getByText('View these paths on your map')).toBeVisible();
  // no decision on record: the legacy plan step keeps the Moves route (same rule as the State card)
  await expect(page.getByRole('button', { name: /Go to your move/ })).toBeVisible();
});

test('04 · RV-02/RV-03: the CTA follows the living decision kind (EER §7.3), never a fixed "start this path"', async () => {
  // QUESTION: conversation first; "Start this path" must NOT appear
  await fullReveal(`snap.nextmove = { type: 'QUESTION', title: 'Someone willing to pay that price', path_id: null, path_affiliation: 'none', degraded: false, move_id: null, source: 'presented' }`);
  await expect(page.getByRole('button', { name: /Answer it in Talk/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Start this path/ })).toHaveCount(0);
  await expect(stepCard()).toContainText('One question is the live step right now');
  await page.getByRole('button', { name: /Answer it in Talk/ }).click();
  await expect(page).toHaveURL(/#\/talk$/);

  // EVIDENCE_REQUEST routes the same way
  await fullReveal(`snap.nextmove = { type: 'EVIDENCE_REQUEST', title: 'A number from your records', path_id: null, path_affiliation: 'none', degraded: false, move_id: null, source: 'presented' }`);
  await expect(page.getByRole('button', { name: /Answer it in Talk/ })).toBeVisible();
  await page.getByRole('button', { name: /Answer it in Talk/ }).click();
  await expect(page).toHaveURL(/#\/talk$/);

  // ACTION: the executable move opens Moves
  await fullReveal(`snap.nextmove = { type: 'ACTION', title: 'Write the one-page offer', path_id: null, path_affiliation: 'none', degraded: false, move_id: null, source: 'presented' }`);
  await expect(page.getByRole('button', { name: /Go to your move/ })).toBeVisible();
  await page.getByRole('button', { name: /Go to your move/ }).click();
  try {
    await expect(page).toHaveURL(/#\/moves$/, { timeout: 4000 });
  } catch (e) {
    throw new Error('ACTION route failed. console: ' + consoleErrors.join(' | '));
  }

  // HOLD: nothing to run yet; the honest exit is the map, not a fabricated action
  await fullReveal(`snap.nextmove = { type: 'HOLD', title: '', path_id: null, path_affiliation: 'none', degraded: false, move_id: null, source: 'presented' }`);
  await expect(page.getByRole('button', { name: /Go to your move/ })).toHaveCount(0);
  await expect(stepCard()).toContainText('on hold until its checks pass');
  await page.getByRole('button', { name: /Explore possible paths/ }).first().click();
  await expect(page).toHaveURL(/#\/maps/);

  // NONE: the engine decided nothing is executable, so no CTA is invented
  await fullReveal(`snap.nextmove = { type: 'NONE', title: '', path_id: null, path_affiliation: 'none', degraded: false, move_id: null, source: 'presented' }`);
  await expect(page.getByRole('button', { name: /Go to your move/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Answer it in Talk/ })).toHaveCount(0);

  // degraded: technical failure is said as technical, and the recovery is Talk (CIR-INV-11)
  await fullReveal(`snap.nextmove = { type: 'QUESTION', title: 'x', path_id: null, path_affiliation: 'none', degraded: true, move_id: null, source: 'presented' }`);
  await expect(page.getByRole('button', { name: /Recover in Talk/ })).toBeVisible();
  await expect(stepCard()).toContainText('We could not finish computing the live step');
});

test('05 · the full reveal keeps the honest exits and clean copy', async () => {
  await fullReveal('snap.nextmove = null');
  await expect(page.getByRole('button', { name: /Open State/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Explore paths/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /Keep talking/ })).toBeVisible();
  await page.getByRole('button', { name: /Open State/ }).click();
  await expect(page).toHaveURL(/#\/state$/);
  await page.evaluate(() => { STORE.forceReveal = false; location.hash = '#/diagnosis/result'; });
  expect(await scanCopy(page, { live: true }), 'copy on the full reveal').toEqual([]);
  expect(consoleErrors, 'no console errors on the reveal journey').toEqual([]);
});
