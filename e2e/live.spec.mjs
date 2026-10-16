// Live UI against the real API with the mock LLM provider (deterministic, no key, no quota).
// One serial journey on the v11 product: start → interview → diagnosis → State → Moves → check-in → map change → follow-up,
// then the other destinations, the sidebar, Settings, the engine switch and the full-window shell. The five destinations are
// covered in depth by state / maps / moves / journey / talk / quality specs; this one proves they hold together in one session.
// Key screens are compared with committed baselines (fixed clock, masked engine section of Settings).
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { scanCopy } from './copy-guard.mjs';

test.describe.configure({ mode: 'serial' });

let page, ctx;
const consoleErrors = [];
const mask = () => [page.locator('#engine-settings')];   // Engine section of the Settings menu (shows the server's provider and commit)
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(120); };
// SVG attributes that turn into NaN only show up as a console error: catch them where they are drawn
const noNaN = async (where) => {
  const bad = await page.evaluate(() => { const h = document.getElementById('app-root').innerHTML; const i = h.indexOf('NaN'); return i < 0 ? '' : h.slice(Math.max(0, i - 160), i + 40); });
  expect(bad, `NaN rendered on ${where}`).toBe('');
};
// WCAG 2 A + AA: zero violations on every screen of the journey
const a11y = async (where) => {
  // freeze animations first: a pulsing ring passing over a label changes the computed contrast for a frame
  const freeze = await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; }' });
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  await freeze.evaluate(el => el.remove());
  expect(r.violations.map(v => `${v.id} x${v.nodes.length}: ` + v.nodes.map(n => (n.any[0] && n.any[0].message || '') + ' @ ' + n.target.join(' ')).join(' | ')), `a11y on ${where}`).toEqual([]);
};
// D9 (prototype doc 06 §12.9): pixels are advisory. A difference above the config's maxDiffPixels is reported as a
// "pixel-advisory" annotation with the pixel count and the diff path (Playwright writes actual/expected/diff into
// test-results/) and does not fail; every other failure (a missing or resized baseline) still fails. The mask and the
// committed baselines are untouched.
const shot = async (name, extraMask = []) => {
  expect(await scanCopy(page, { live: true }), `copy on ${name}`).toEqual([]);
  try {
    await expect(page).toHaveScreenshot(`live-${name}.png`, { mask: [...mask(), ...extraMask], fullPage: false, stylePath: './screenshot.css' });
  } catch (e) {
    // Playwright words a pixel difference in two ways: with a ratio (no cap configured) or as a count
    // against the configured cap ("at most 40 pixels different, but found N pixels different"). Both are a
    // pixel difference and therefore advisory (D9). A missing or resized baseline carries no such count and
    // still fails, as the policy requires.
    const msg = String(e.message);
    const byRatio = msg.match(/(\d+) pixels \(ratio ([\d.]+) of all image pixels\) are different/);
    const byCount = msg.match(/at most \d+ pixels different, but found (\d+) pixels different/);
    const m = byRatio || (byCount ? [null, byCount[1], (Number(byCount[1]) / (1440 * 900)).toFixed(4)] : null);
    if (!m) throw e;
    test.info().annotations.push({ type: 'pixel-advisory', description: `live-${name}: ${m[1]} pixels differ (ratio ${m[2]}) — diff: ${test.info().outputPath(`live-${name}-diff.png`)}` });
  }
};
// a path the evidence stopped gives the dialog a subject (the mock diagnosis has none): both layers, as one reality (doc 14 §10.1)
const forceStop = () => page.evaluate(() => {
  const p = LIVE.artifact.possible_paths.paths.find(x => x.strategy_id === 'paid_channel_test');
  p.status = 'STOP';
  const pp = LIVE.projection && LIVE.projection.paths && LIVE.projection.paths.find(x => x.key === p.path_id);
  if (pp) pp.status = 'STOP';
  V11_ENGINE.clear(); syncStoreFromLive(); STORE.mapsSelBy = {}; goDestination('maps'); setMapsView('landscape');
  mapsSelect(V11_ENGINE.snapshot().paths.find(x => x.status_display === 'STOP').id);
});
const nav = (name) => page.locator('.v11-topnav-item', { hasText: new RegExp(`^${name}$`) });

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  // The clock freezes at 00:00 TODAY so (a) every server timestamp of this run (done_at) lands inside the same frozen day (Day 1),
  // and (b) the chat's message times render the same on every run.
  const now = new Date();
  await page.clock.setFixedTime(new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0));
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  await page.addInitScript(() => { const o = Element.prototype.setAttribute; Element.prototype.setAttribute = function (k, v) { if (String(v) === 'NaN') console.error('NaN attr ' + k + ' at ' + new Error().stack.split('\n').slice(2, 6).join(' | ')); return o.call(this, k, v); }; });
  // A stable browser identity for this run; the teardown removes workspaces whose id starts with u_e2e
  await page.addInitScript(() => { try { if (!localStorage.getItem('novaliners-v9')) localStorage.setItem('novaliners-v9', JSON.stringify({ userId: 'u_e2e' + Math.random().toString(16).slice(2, 10), chain: [], checkins: [], overrides: [], tips: {} })); } catch (e) { /* ignore */ } });
});
test.afterAll(async () => {
  await ctx.close();
});

test('01 · start screen loads, names the product, and logs no console error; the interface is English', async () => {
  await page.goto('/', { waitUntil: 'networkidle' });
  expect(await page.evaluate(() => document.documentElement.lang)).toBe('en');
  await expect(page.getByRole('heading', { name: /You don't lack tactics/ })).toBeVisible();
  await expect(page.getByText('Revenue Navigation Map', { exact: true })).toBeVisible();   // product name from the docs' vocabulary lock
  await expect(page.getByText('GO. STOP. OR DO SOMETHING ELSE.', { exact: true })).toBeVisible();
  expect(await page.title()).toBe('Novaliners · Revenue Navigation Map');
  await expect(page.locator('#start-textarea')).toBeVisible();
  await expect(page.locator('#proto-widget')).toHaveCount(0);   // the engine is in Settings; nothing floats at the bottom right
  await a11y('01-start'); await shot('01-start');
});

test('02 · interview: the first message creates the map and the engine answers with the one thing it needs', async () => {
  await page.fill('#start-textarea', 'I left my job as a marketing manager. I want Rp20 million a month from consulting within 90 days. I have no clients yet.');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page).toHaveURL(/#\/diagnosis$/);
  await expect(page.getByText('I left my job as a marketing manager')).toBeVisible();
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  // M4: the next question is chosen by the engine from what it knows (not by a phase, not improvised by the model):
  // after this first message the goal is clear but the current income is not measured yet, so that is what it asks.
  await expect(page.getByText(/Your current income is not measured yet/).first()).toBeVisible();
  await expect(page.locator('.move-tag').first()).toContainText('Question');
  await expect(page.locator('#nav-focus')).toContainText('What we are asking about');
  await a11y('02-chat-first-turn'); await shot('02-chat-first-turn');
  for (let i = 1; i <= 2; i++) {
    await page.fill('#diag-chat-input', `Answer ${i}: my income now is Rp8 million a month from 2 clients, and it is steady. Two people asked me to let them know, and last year I got Rp5 million from one project.`);
    await page.keyboard.press('Enter');
    await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  }
  // the evidence panel lists real facts from the ledger
  await page.getByRole('button', { name: /What we know/ }).click();
  await expect(page.getByText('What we know so far')).toBeVisible();
  await expect(page.getByText(/facts? collected/)).toBeVisible();
  await shot('02-chat-evidence-open');
  await page.getByRole('button', { name: 'Close summary' }).click();
});

test('03 · build the diagnosis early, land on the reveal, open and close "Why?"', async () => {
  await page.getByText('Enough answers? Build my diagnosis now').click();
  await expect(page.getByRole('heading', { name: /best read so far/ })).toBeVisible({ timeout: 60_000 });
  await expect(page).toHaveURL(/#\/diagnosis\/provisional|#\/diagnosis\/result/);
  await a11y('03-reveal-provisional'); await shot('03-reveal-provisional');
  await page.getByText('Why?', { exact: true }).click();
  const drawer = page.getByRole('dialog', { name: 'Why this diagnosis?' });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText('1. What you told us')).toBeVisible();
  await expect(drawer.getByText(/Built by engine/)).toBeVisible();
  await page.waitForTimeout(450); await a11y('03-why-drawer'); await shot('03-why-drawer');
  await page.keyboard.press('Escape');
  await expect(page.locator('#why-drawer.open')).toHaveCount(0);
});

test('03b · State is the home of a map: five destinations in the top bar, State marked, the story in the person\'s own words, one way on', async () => {
  await go(`goDestination('state')`);
  await expect(page).toHaveURL(/#\/state$/);
  await expect(page.locator('.v11-topnav-item')).toHaveText(['State', 'Maps', 'Moves', 'Journey', 'Talk']);
  await expect(page.locator('.v11-topnav-item[aria-current="page"]')).toHaveText('State');
  await expect(page.locator('#v11-main h1')).toHaveText('Where you are');
  await page.waitForFunction(() => LIVE.explainState === 'ready' || LIVE.explainState === 'failed', null, { timeout: 30_000 });
  await page.waitForTimeout(200);
  // the page opens by telling the state back in the user's own words (the rewrite is checked by the server)
  await expect(page.locator('.dest-hero')).toContainText(/marketing manager/i);
  // one way on in the reading column (v11 phase-1: the inspector's foot carries its own quiet + primary CTA)
  await expect(page.locator('.ws-inner .btn-primary')).toHaveCount(1);
  await noNaN('state'); await a11y('state'); await shot('state');
  // the full reasoning is one click away (keyboard-operable, Esc closes, focus returns)
  const opener = page.locator('[onclick*="openStateWhyDrawer"]').first();
  await opener.focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#why-drawer.open')).toHaveCount(0);
  expect(await page.evaluate(() => (document.activeElement.getAttribute('onclick') || '').includes('openStateWhyDrawer'))).toBe(true);
});

test('04 · Moves: the ready moves are listed, any order works, and each one done is recorded on the server and moves the plan', async () => {
  // Reveal fix (EER §7.3, 17 Okt 2026): the reveal's CTA follows the live decision's kind, so it no longer
  // promises a fixed "Go to your move" from the provisional read (the mock's read lands here). Moves is
  // reached from the destination bar / the small-step CTA; the kind-based routing itself is covered by
  // reveal.spec.mjs.
  await nav('Moves').click();
  await expect(page).toHaveURL(/#\/moves$/);
  await expect(page.locator('.v11-topnav-item[aria-current="page"]')).toHaveText('Moves');
  await expect(page.locator('#v11-main h1')).toHaveText(/move/i);
  await expect(page.getByText('3 steps are ready. Any order works.')).toBeVisible();
  await expect(page.locator('.moves-list .step-row, .moves-list .step-focus')).toHaveCount(4);   // three moves and the report step
  await expect(page.locator('.moves-list')).toContainText('Any order works. Doing a move does not say it worked.');
  await a11y('04-moves'); await shot('04-moves');
  // the step keeps its reason: one line from the diagnosis, and the way back to State
  await expect(page.locator('.today-why')).toContainText('Why this step:');
  await page.locator('.today-why').getByText('State →').click();
  await expect(page).toHaveURL(/#\/state$/);
  await nav('Moves').click();
  await expect(page).toHaveURL(/#\/moves$/);
  // "Not today" does not dead-end: it shows another step that can be done now
  await page.getByRole('button', { name: 'Not today' }).click();
  await expect(page.getByText('This one can wait. Here is another step you can do now.')).toBeVisible();
  // Out of order: open the third step from the list. It is fully usable, not read-only.
  // (The plan content comes from the scenario-grounded mock draft — the mechanics are the contract.)
  await page.locator('.step-row', { hasText: /repeat the thing that moved/ }).click();
  await expect(page.locator('.step-row.viewing')).toHaveCount(1);
  await expect(page.locator('.today-card')).toContainText(/repeat the thing that moved/);
  await a11y('04-moves-other-step'); await shot('04-moves-other-step');
  await page.locator('#advance-btn').click();
  // finished on the real day, and the server has the time
  await expect(page.locator('.step-row.done')).toContainText('Done · Day 1');
  await expect(page.locator('.moves-list .step-row.done')).toHaveCount(1);
  const saved = await page.evaluate(() => LIVE.artifact.day_by_day.map(a => [a.status, !!a.done_at]));
  expect(saved).toEqual([['TODO', false], ['TODO', false], ['DONE', true]]);
  // A finished step can be opened again: it says when it was done and leads back to the next step
  await page.locator('.step-row.done').click();
  await expect(page.getByText('You did this on Day 1.')).toBeVisible();
  await page.getByRole('button', { name: /Back to your next step/ }).click();
  await expect(page.locator('.step-row.viewing')).toHaveCount(0);
  // Journey moved without any check-in
  await nav('Journey').click();
  await expect(page).toHaveURL(/#\/journey$/);
  await expect(page.locator('#v11-main')).toContainText(/Move \d/);
  await nav('Moves').click();
  // Two more on the same day, then the check-in opens by itself
  await page.locator('#advance-btn').click();
  await expect(page.locator('.moves-list .step-row.done')).toHaveCount(2);
  await page.locator('#advance-btn').click();
  await expect(page).toHaveURL(/#\/check-in$/);
  await expect(page.getByRole('heading', { name: /What happened this week/ })).toBeVisible();
});

test('04b · Moves: steps from your routes can be done, and then wait for proof', async () => {
  await page.getByText('← Back to Moves').click();
  const route = { route_id: 'r-1', motion: 'ACQUISITION', path_id: 'path.direct_outreach', path_title: 'Winning new clients', lineage_status: 'OPEN', applicability: { status: 'APPLIES' },
    nodes: [{ node_id: 'n-1', activity: 'Write down who you sell to: type of business, level, and buyer role', execution_view: 'NOT_STARTED' }],
    frontier: [{ kind: 'EXECUTE', route_id: 'r-1', node: 'n-1' }] };
  let posted = null;
  await page.route('**/routes/r-1/nodes/n-1/execution', async r => { posted = r.request().postDataJSON(); await r.fulfill({ json: { ok: true } }); });
  await page.route('**/session/*/routes', r => r.fulfill({ json: { routes: [posted && posted.event === 'EXECUTED'
    ? Object.assign({}, route, { frontier: [{ kind: 'VERIFY', route_id: 'r-1', node: 'n-1' }] }) : route], not_born: [], next_move: null } }));
  await page.evaluate(() => { LIVE.routes = null; return liveLoadRoutes().then(() => goDestination('moves')); });
  await expect(page.locator('.moves-routes')).toContainText(/ALSO READY · FROM YOUR ROUTES/i);
  await expect(page.locator('.route-task-route')).toHaveText('Winning new clients');
  await expect(page.getByText('Write down who you sell to: type of business, level, and buyer role')).toBeVisible();
  await a11y('04-route-ready'); await shot('04-route-ready');
  await page.getByRole('button', { name: 'I did this' }).click();
  await expect(page.getByText('PROOF NEEDED')).toBeVisible();
  expect(posted).toEqual({ event: 'EXECUTED' });
  await expect(page.getByText('You did this. It counts once evidence that it worked comes in.')).toBeVisible();
  await a11y('04-route-proof'); await shot('04-route-proof');
  await page.unroute('**/session/*/routes'); await page.unroute('**/routes/r-1/nodes/n-1/execution');
  await page.evaluate(() => { LIVE.routes = null; renderScreen('05'); });
});

test('04c · a low-confidence plan ends with a hold note: it is never a task', async () => {
  // the engine marks the hold note with the word DIGANTUNG (agents/diagnosis.py); the page keys on that marker, whatever language the rest is in
  const r = await page.evaluate(() => {
    const keep = LIVE.artifact.day_by_day;
    LIVE.artifact.day_by_day = [{ text: 'Day 1: Write the offer.', status: 'TODO' }, { text: 'Day 2: Send it to 2 contacts.', status: 'TODO' },
      { text: 'Hari 4-7 DIGANTUNG: jangan eksekusi sampai hasil Hari 1-3 mengubah prior.', status: 'TODO' }];
    const s = liveSteps();
    LIVE.artifact.day_by_day = keep;
    return s.map(x => [x.label.slice(0, 12), x.ready, !!x.hold, x.status]);
  });
  expect(r.map(x => x.slice(1))).toEqual([[true, false, 'CURRENT'], [true, false, 'UPCOMING'], [false, true, 'UPCOMING'], [false, false, 'UPCOMING']]);
  expect(r[2][0]).toMatch(/^DIGANTUNG/);
  expect(r[3][0]).toBe('Report your ');
});

test('04d · State says what the engine says when there is no rewrite: settled verdict, hold-back, and no invented blocks', async () => {
  const facts = await page.evaluate(() => {
    const keep = LIVE.artifact, keepEx = LIVE.explain, keepSt = LIVE.explainState;   // engine text only: no rewrite here
    const card = patch => {
      LIVE.artifact = Object.assign({}, keep, patch); LIVE.explain = null; LIVE.explainState = 'failed'; V11_ENGINE.clear();
      try { return JSON.parse(JSON.stringify(V11_ENGINE.snapshot().state)); } finally { LIVE.artifact = keep; LIVE.explain = keepEx; LIVE.explainState = keepSt; V11_ENGINE.clear(); }
    };
    const settled = { status: 'final', confidence_band: 'HIGH', decision_spectrum: { level: 'GO_SMALL' }, primary_constraint: 'You have no written offer yet.' };
    return {
      settled: card(Object.assign({}, settled, { do_not_detail: { text: 'Do not lease an office.', reason: 'No client has asked for one.' } })),
      nothingBlocked: card(Object.assign({}, settled, { do_not: '', do_not_detail: null })),
      held: card({ confidence_band: 'LOW', status: 'provisional' })
    };
  });
  expect(facts.settled.provisional).toBeFalsy();
  expect(JSON.stringify(facts.settled.what_not_to_do)).toContain('Do not lease an office.');
  expect(facts.nothingBlocked.what_not_to_do || [], 'no invented hold-back').toEqual([]);
  expect(facts.held.provisional, 'a low-confidence read says it is a first read').toBe(true);
});

test('04e · long plan steps keep their own words: a stop inside quotes or a decimal never leaves a stray tail as the title', async () => {
  const r = await page.evaluate(() => [
    brief("Follow up with the 2 leads who have not replied: send 1 message of 2 lines + 1 yes/no question ('shall I send 2 examples of similar online shops today?').", 68),
    brief('Write the price 8.5 million then send it to the two people who asked about this offer. After that note down their answer.', 68),
    brief('One. Two short sentences. Three short sentences too. Four is already too long to show in full here.', 68),
    brief('Short.', 68)
  ]);
  expect(r[0]).toMatch(/^Follow up with the 2 leads/);
  expect(r[1]).toMatch(/^Write the price 8\.5 million/);
  expect(r[2]).toBe('One. Two short sentences. Three short sentences too.');
  expect(r[3]).toBe('Short.');
  for (const t of r) expect(t.length).toBeGreaterThan(5);
});

test('05 · check-in: pick an outcome, numbers are optional, the map change screen explains itself', async () => {
  const submit = page.locator('#checkin-submit');
  await page.evaluate(() => renderScreen('05'));
  await submit.click();                                    // nothing picked yet
  await expect(page.locator('#checkin-err')).toContainText('Pick what happened first');
  await page.getByRole('radio', { name: /Mixed/ }).click();
  await page.fill('#checkin-contacted', '6');
  await page.fill('#checkin-replies', '3');
  await page.fill('#checkin-calls', '1');
  await a11y('05-checkin'); await shot('05-checkin');
  await submit.click();
  await expect(page).toHaveURL(/#\/map\/adjusted-mixed$/);
  await expect(page.getByRole('heading', { name: /People are interested/ })).toBeVisible();
  await expect(page.getByText('What changed on your map')).toBeVisible();
  await a11y('12-map-adjusted-mixed'); await shot('12-map-adjusted-mixed');
});

test('06 · the follow-up opens a linked interview, and going back returns to the map', async () => {
  await page.getByRole('button', { name: /Start the next week/ }).click();
  await expect(page.getByText(/Welcome back\. Tell us what happened/)).toBeVisible();
  await shot('02-followup-opener');
  await page.getByText('State', { exact: true }).first().click();      // abort: back to the map that was open
  await expect(page).toHaveURL(/#\/state$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Where you are');
});

test('07 · Maps and Journey hold the session together: the lens is in the address, the check-in is on the record', async () => {
  await nav('Maps').click();
  await expect(page).toHaveURL(/#\/maps$/);
  await expect(page.locator('.v11-view-switch button')).toHaveCount(2);
  await page.waitForFunction(() => LIVE.projection !== null);
  await page.waitForFunction(() => LIVE.explainState === 'ready' || LIVE.explainState === 'failed', null, { timeout: 30_000 });
  await page.waitForTimeout(500);
  await noNaN('maps'); await a11y('maps'); await shot('maps');
  await page.locator('.v11-view-switch button', { hasText: 'Readiness' }).click();
  await expect(page).toHaveURL(/#\/maps\/readiness$/);
  await expect(page.locator('#rd-detail')).toBeVisible();
  await noNaN('readiness'); await a11y('readiness'); await shot('readiness');
  await nav('Journey').click();
  await expect(page).toHaveURL(/#\/journey$/);
  await expect(page.locator('.j-statcard')).toHaveCount(4);
  await expect(page.locator('#v11-main')).toContainText('Interested, but no one paid yet');
  await noNaN('journey'); await a11y('journey'); await shot('journey');
});

test('07d · Talk: a proper page to talk the state through; it answers from the map and never changes it', async () => {
  await page.evaluate(() => { localStorage.removeItem('novaliners-ask'); LIVE.askSid = ''; });
  await nav('Talk').click();
  await expect(page).toHaveURL(/#\/talk$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Talk');
  await expect(page.locator('#chat-messages-container')).toContainText('A question never changes your record.');
  const chips = page.locator('.ask-chip');
  expect(await chips.count()).toBeGreaterThan(0);
  expect(await chips.count()).toBeLessThanOrEqual(4);   // starter questions, at most four (Hick)
  await a11y('talk-empty'); await shot('talk-empty');
  // pick a starter: the answer arrives from the server, with follow-up questions
  await chips.first().click();
  const theirs = page.locator('#chat-messages-container .talk-msg:not(.is-mine) .talk-body');
  await expect(theirs.last()).toContainText(/What we (can read|see)/, { timeout: 30_000 });
  await expect(page.locator('#chat-messages-container .talk-msg.is-mine .talk-bubble').first()).toHaveText('Why is this what is holding me back?');
  // write one: Enter sends, Shift+Enter does not
  await page.locator('#talk-ongoing-input').fill('What would open Paid ads?');
  await page.locator('#talk-ongoing-input').press('Enter');
  await expect(page.locator('#chat-messages-container .talk-msg.is-mine')).toHaveCount(2);
  await page.waitForFunction(() => !LIVE.askThinking, null, { timeout: 30_000 });
  await expect(theirs).toHaveCount(3);   // the opening and the two answers
  // the conversation is kept (per session) across a reload; the diagnosis behind it did not change
  const before = await page.evaluate(() => JSON.stringify(LIVE.artifact.primary_constraint_id));
  await page.reload({ waitUntil: 'networkidle' });
  await expect(page).toHaveURL(/#\/talk$/);
  await expect(page.locator('#chat-messages-container .talk-msg.is-mine')).toHaveCount(2);
  expect(await page.evaluate(() => JSON.stringify(LIVE.artifact.primary_constraint_id))).toBe(before);
  // which path the engine puts "In focus" depends on the plan's state at that moment, so the paths list is masked here (Maps and Talk specs assert it)
  expect(await page.locator('.talk-paths .mp-tag').count()).toBeLessThanOrEqual(1);
  await a11y('talk-thread'); await shot('talk-thread', [page.locator('.talk-paths-wrap')]);
});

test('08 · "do it anyway" is a real dialog: Esc closes it, a choice is logged on the Journey', async () => {
  await forceStop();
  await page.getByRole('button', { name: 'I want to do this anyway' }).click();
  const modal = page.getByRole('dialog', { name: 'Doing a stopped path anyway' });
  await expect(modal).toBeVisible();
  // a late explain response re-renders the screen; it must NEVER close a dialog the user is in
  await page.evaluate(() => { LIVE.explainState = 'idle'; return liveEnsureExplain(); });
  await expect(modal).toBeVisible();
  await page.waitForTimeout(450); await a11y('11-stop-modal'); await shot('11-stop-modal');
  await page.keyboard.press('Escape');
  await expect(page.locator('#stop-modal.open')).toHaveCount(0);
  await page.getByRole('button', { name: 'I want to do this anyway' }).click();
  await page.getByRole('radio', { name: /Run a small test instead/ }).click();
  await page.getByRole('button', { name: /Confirm choice/ }).click();
  await expect(page.getByText(/small, capped test/)).toBeVisible();
  // the decision is on the record, on the path's own trail ("Your decision, recorded here")
  const rec = await page.evaluate(() => ({ n: LIVE.overrides.length, trail: V11_ENGINE.snapshot().paths.flatMap(p => p.trail || []) }));
  expect(rec.n).toBe(1);
  expect(rec.trail.join(' ')).toContain('You chose to go ahead anyway. Your decision, recorded here');
});

test('08b · the route switcher: starting a new map never loses the current map, every way back works, and a reload stays where it is', async () => {
  const startHeading = page.getByRole('heading', { name: /You don't lack tactics/ });
  // from any screen, one visible control in the switcher's footer (not a hidden link, no confirm dialog)
  await go(`goDestination('state')`);
  await page.locator('.v11-ctx-trigger').click();
  await page.getByRole('menuitem', { name: 'Start new map' }).click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(startHeading).toBeVisible();
  // the switcher keeps your maps as history: the current one is pinned first, with its goal
  await page.locator('.v11-ctx-trigger').click();
  const current = page.locator('.v11-ctx-item.is-on');
  await expect(current).toBeVisible();
  await expect(current).toContainText(/Reach Rp20M a month/);
  await a11y('01-home'); await shot('01-start-from-app');
  // ...and the map is untouched: open it from the switcher
  await current.click();
  await expect(page).toHaveURL(/#\/state$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Where you are');
  // the brand mark is Home: the Start page, in the same v11 frame (the map stays saved)
  await page.getByRole('button', { name: /NOVALINERS, go home/ }).click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(startHeading).toBeVisible();
  // the route switcher's footer action starts a new map from any destination
  await go(`STORE.sidebarExpanded = false; goDestination('state')`);
  await page.locator('.v11-ctx-trigger').click();
  await page.locator('.v11-ctx-new').click();
  await expect(startHeading).toBeVisible();
  // ...and the saved map is one click away: the pinned current map reopens its State
  // (Start carries no destination bar, so the way back is the switcher itself)
  await page.locator('.v11-ctx-trigger').click();
  await page.locator('.v11-ctx-item.is-on').click();
  await expect(page).toHaveURL(/#\/state$/);
  // a reload on any other destination stays there
  await nav('Maps').click();
  await expect(page).toHaveURL(/#\/maps$/);
  await page.reload({ waitUntil: 'networkidle' });
  await expect(page).toHaveURL(/#\/maps$/);
  await expect(page.locator('.v11-topnav-item[aria-current="page"]')).toHaveText('Maps');
  await page.locator('.v11-ctx-trigger').click();
  await page.locator('.v11-ctx-new').click();
  // a really new map: it replaces the current one only once a goal is submitted
  await page.fill('#start-textarea', 'I run a small bakery. I sell Rp8 million a month and want Rp20 million a month within 90 days.');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page).toHaveURL(/#\/diagnosis$/);
  await expect(page.getByText('I run a small bakery')).toBeVisible();
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  // "Back" from the new interview lands on Start: the paused interview is resumable from the switcher's list
  await page.getByText('Back', { exact: true }).click();
  await expect(startHeading).toBeVisible();
  await page.locator('.v11-ctx-trigger').click();          // open the switcher so the map list is visible
  const maps = page.locator('.v11-ctx-list');
  await expect(maps.getByRole('menuitemradio', { name: /marketing manager/ })).toHaveCount(1);
  await a11y('01-home-other-maps'); await shot('01-start-other-maps');
  await maps.getByRole('menuitemradio', { name: /marketing manager/ }).click();
  await expect(page).toHaveURL(/#\/state$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Where you are');
  await expect.poll(() => page.evaluate(() => LIVE.goalText)).toContain('marketing manager');
});

test('08c · Settings: Light and Dark, remembered, on every destination, WCAG AA in both', async () => {
  const bg = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await go(`goDestination('moves')`);
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');   // Playwright's default colour scheme is light
  const lightBg = await bg();
  // Settings lives in the sidebar footer; the menu is a real popup that Esc and outside clicks close
  const settings = page.getByRole('button', { name: 'Settings' });
  await expect(settings).toHaveAttribute('aria-expanded', 'false');
  await settings.click();
  await expect(settings).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByText('Appearance')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await expect(page.getByText('Appearance')).toBeHidden();
  await settings.click();
  await page.getByRole('button', { name: 'Dark' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
  expect(await bg()).not.toBe(lightBg);
  await a11y('08c-settings-menu-dark'); await shot('08c-settings-dark');
  await page.mouse.click(700, 500);                        // outside click closes it
  await expect(page.getByText('Appearance')).toBeHidden();
  // remembered across a reload
  await page.reload({ waitUntil: 'networkidle' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  expect(await page.evaluate(() => localStorage.getItem('novaliners-theme'))).toBe('dark');
  await page.evaluate(() => document.fonts.ready);   // right after a reload: shoot once the fonts have settled, not mid-swap
  // every destination is themed, readable (axe WCAG 2 A/AA) and free of NaN
  for (const d of ['moves', 'state', 'maps', 'journey']) {
    await nav(d[0].toUpperCase() + d.slice(1)).click();
    await expect(page).toHaveURL(new RegExp(`#/${d}`));
    await page.waitForTimeout(300);
    await noNaN(`${d}-dark`); await a11y(`${d}-dark`);
  }
  await page.locator('.v11-ctx-trigger').click();
  await page.getByRole('menuitem', { name: 'Start new map' }).click();
  await expect(page.getByRole('heading', { name: /You don't lack tactics/ })).toBeVisible();
  await expect(page.getByText('Revenue Navigation Map', { exact: true })).toBeVisible();
  await a11y('01-home-dark'); await shot('01-home-dark');
  await forceStop();
  await page.getByRole('button', { name: 'I want to do this anyway' }).click();
  await page.waitForTimeout(450); await a11y('11-stop-modal-dark'); await shot('11-stop-modal-dark');
  await page.keyboard.press('Escape');
  // collapsed sidebar: the gear opens the same menu beside the rail
  await go(`STORE.sidebarExpanded = false; goDestination('moves')`);
  await page.getByRole('button', { name: 'Settings' }).click();
  await expect(page.getByText('Appearance')).toBeVisible();
  await page.getByRole('button', { name: 'Light' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  expect(await bg()).toBe(lightBg);
  expect(await page.evaluate(() => localStorage.getItem('novaliners-theme'))).toBe('light');
  await page.keyboard.press('Escape');
  await a11y('moves-back-to-light');
});

test('09 · Engine lives in Settings (no floating panel): provider and model, ready state, a failed switch changes nothing', async () => {
  await go(`STORE.sidebarExpanded = true; goDestination('moves')`);
  await expect(page.locator('#proto-widget')).toHaveCount(0);
  await page.getByRole('button', { name: 'Settings' }).click();
  const engine = page.locator('#engine-settings');
  await expect(engine.getByText('Engine', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Provider')).toHaveValue('mock');
  await expect(engine.getByText('Engine ready. New answers use this model.')).toBeVisible();
  const providers = await page.getByLabel('Provider').locator('option').allTextContents();
  expect(providers).toContain('mock');
  expect(providers.length).toBeGreaterThan(1);
  await a11y('09-settings-engine');
  // a switch the server refuses (no key for that provider): says why, the gear gets a red dot, the server's engine is unchanged
  const seen = consoleErrors.length;
  await page.route('**/admin/model', r => r.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'No API key for gemini' }) }));
  await page.getByLabel('Provider').focus();                      // as a real user: the select has focus when it changes
  await page.getByLabel('Provider').selectOption('gemini');
  await expect(engine.locator('.settings-status')).toContainText('Could not switch');
  await expect(engine.locator('.settings-status')).toContainText('No API key for gemini');
  await expect(page.locator('#v11-settings-btn')).toHaveClass(/has-alert/);
  await expect(page.getByLabel('Provider')).toBeFocused();       // the menu keeps focus while it refreshes
  expect(await page.evaluate(async () => (await (await fetch('/health')).json()).provider)).toBe('mock');
  consoleErrors.splice(seen);                                    // the browser logs the 400 we just staged on purpose: drop what was logged since
  // a switch the server accepts: the provider, its model list and the ready line follow, and the alert clears
  await page.unroute('**/admin/model');
  await page.route('**/admin/model', r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    status: 'ok', provider: 'gemini', model: 'gemini-3.5-flash', providers: ['mock', 'gemini'], models_by_provider: { mock: [], gemini: ['gemini-3.5-flash', 'gemini-3.5-flash-lite'] }, commit: 'abc1234' }) }));
  await page.getByLabel('Provider').selectOption('gemini');
  await expect(page.getByLabel('Provider')).toHaveValue('gemini');
  await expect(page.getByLabel('Model')).toHaveValue('gemini-3.5-flash');
  await expect(engine.getByText('abc1234')).toBeVisible();
  await expect(engine.getByText('Engine ready. New answers use this model.')).toBeVisible();
  await expect(page.locator('#v11-settings-btn')).not.toHaveClass(/has-alert/);
  await page.unroute('**/admin/model');
  await page.evaluate(() => loadEngine());                       // back to what the real server says (mock)
  await expect(page.getByLabel('Provider')).toHaveValue('mock');
  await page.keyboard.press('Escape');
});

test('09b · the app fills the window: no outer frame, border or gap around the sidebar and canvas', async () => {
  await go(`STORE.sidebarExpanded = false; goDestination('moves')`);
  const m = await page.evaluate(() => {
    const v = document.getElementById('app-root'), s = document.querySelector('.shell-container');
    const cs = getComputedStyle(s), r = s.getBoundingClientRect();
    return { pad: getComputedStyle(v).padding, border: cs.borderTopWidth, radius: cs.borderTopLeftRadius, shadow: cs.boxShadow,
      x: r.x, y: r.y, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight };
  });
  expect(m.pad).toBe('0px');
  expect(m.border).toBe('0px');
  expect(m.radius).toBe('0px');
  expect(m.shadow).toBe('none');
  expect([m.x, m.y, m.w, m.h]).toEqual([0, 0, m.vw, m.vh]);
});

test('10 · nothing logged a console error during the whole journey', async () => {
  expect(consoleErrors, consoleErrors.join('\n')).toEqual([]);
});
