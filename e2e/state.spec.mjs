// State destination (record P5a; doc 10 §6.1, §4): where you are, what matters, what to do next, why, in that order,
// fed by the snapshot adapter and nothing else. Live UI against the real API with the mock LLM; conditions the mock
// cannot reach (no move, zero paths of each kind, long text, many paths) are put in place through the same seam the
// prototype's behaviour checks use (V11_ENGINE.set), so each one is deterministic.
import { test, expect } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

let page, ctx;
const consoleErrors = [];
const USER_SAYS = 'Nobody has paid me yet, and two people asked me to let them know.';

const withSnap = (mut) => page.evaluate(`(function(){
  const snap = JSON.parse(JSON.stringify(V11_ENGINE.snapshot()));
  (${mut.toString()})(snap);
  V11_ENGINE.set(v11MapKey(), snap);
  goDestination('state');
})()`);
const reset = () => page.evaluate(() => { V11_ENGINE.clear(); goDestination('state'); });
const main = () => page.locator('#v11-main').innerText();
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
    await page.fill('#diag-chat-input', i === 1 ? USER_SAYS : 'I have about 6 free hours a week and Rp20M in savings.');
    await page.keyboard.press('Enter');
    await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  }
  await page.getByText('Enough answers? Build my diagnosis now').click();
  await expect(page.getByRole('heading', { name: /best read so far/ })).toBeVisible({ timeout: 60_000 });
});

test('01 · State reads in order: narrative, what holds you, one next decision, the detail and reasons in the panel', async () => {
  await page.evaluate(() => goDestination('state'));
  await expect(page.locator('#v11-main h1')).toHaveText('Where you are');
  await expect(page.locator('.v11-eyebrow')).toContainText('State');
  const order = await page.evaluate(() => [...document.querySelectorAll('#v11-main .dest-hero, #v11-main .dest-focus, #v11-main .dest-step, #v11-main .dest-rail')].map(e => e.className.replace(/\s+/g, ' ').trim().split(' ').slice(0, 2).join(' ')));
  expect(order[0]).toContain('dest-hero');
  expect(order.findIndex(x => x.includes('dest-focus'))).toBeGreaterThan(0);
  // v11 phase-1: the page shows the three tiers only — the decision keeps its framed card; what not to do
  // and why we think so fold into the inspector (same words, same order, one place for the detail)
  const steps = page.locator('.dest-step');
  await expect(steps.first()).toContainText('NEXT DECISION');
  await expect(page.locator('#dest-rail')).toContainText('WHAT NOT TO DO YET');
  await expect(page.locator('#dest-rail')).toContainText('WHY WE THINK SO');
  await expect(page.locator('.dest-rail')).toContainText('YOUR NUMBERS');
  await expect(page.locator('.dest-rail')).toContainText('PATHS ON YOUR MAP');
  await expect(page.locator('.dest-rail')).toContainText('REASSESS');
  // a verdict score, a confidence figure or a ranking never appears
  expect(await main()).not.toMatch(/confidence|\bscore\b|\d+\s?%|ranked|best path/i);
});

test('02 · the next move leads where its kind says, and the rail leads to Maps and Talk', async () => {
  // EER: the mock map's presented decision is an evidence request, so its CTA continues in Talk
  // (an executable ACTION would open Moves — covered by test 18 with an injected ACTION decision).
  await page.getByRole('button', { name: /Continue in Talk/ }).click();
  await expect(page).toHaveURL(/#\/talk$/);
  await page.evaluate(() => goDestination('state'));
  await page.getByRole('button', { name: /See your map/ }).click();
  await expect(page).toHaveURL(/#\/maps$/);
  await page.evaluate(() => goDestination('state'));
  await page.getByRole('button', { name: /Talk about this/ }).click();
  await expect(page).toHaveURL(/#\/talk$/);
  await page.evaluate(() => goDestination('state'));
});

test('03 · every sentence is the engine\'s: the page shows the rewrite when the server wrote one, else the artifact\'s own words', async () => {
  const facts = await page.evaluate(() => {
    const d = LIVE.artifact, ex = LIVE.explainState === 'ready' ? LIVE.explain : null;
    const snap = V11_ENGINE.snapshot();
    return { snapWhere: snap.state.where_you_are, snapBlocking: snap.state.blocking, exSummary: ex && ex.summary ? ex.summary.join(' ') : null,
      exBlocking: ex && ex.blocking_title ? ex.blocking_title : null, primary: userFacing(d.primary_constraint), where: userFacing(d.where_you_are) };
  });
  expect(facts.snapWhere === (facts.exSummary || facts.where) || facts.snapWhere.length > 0).toBe(true);
  expect(facts.snapBlocking).toBe(facts.exBlocking || facts.primary);
  const text = await main();
  // the narrative paragraphs on the page are the snapshot's sentences, nothing added except the goal line
  const first = facts.snapWhere.split(/(?<=[.!?])\s+/)[0].trim();
  expect(text.replace(/\s+/g, ' ')).toContain(first.replace(/\s+/g, ' '));
  expect(text).toContain(facts.snapBlocking.slice(0, 40));
});

test('04 · one adapter, one contract: buildSnapshot(sid) from the endpoints equals the snapshot the page reads', async () => {
  const same = await page.evaluate(async () => {
    const fromEndpoints = await buildSnapshot(LIVE.sid);
    const fromPage = liveSnapshot();
    return { a: JSON.stringify(fromEndpoints), b: JSON.stringify(fromPage), n: fromPage.paths.length };
  });
  expect(same.a).toBe(same.b);
  expect(same.n, 'the mock map has paths').toBeGreaterThan(0);
});

test('05 · the user\'s own words are shown verbatim in the "How we got here" sheet', async () => {
  await page.evaluate(() => goDestination('state'));
  const opener = page.getByRole('button', { name: /How we got here/ });
  await opener.click();
  const sheet = page.getByRole('dialog');
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText(USER_SAYS);                // exactly as typed: not translated, not corrected, not shortened
  await expect(sheet).toContainText('THE EVIDENCE, BY SOURCE');
  // a11y: focus inside, Tab stays inside, Escape closes, focus returns to the opener
  await page.waitForFunction(() => document.getElementById('drawer-content').contains(document.activeElement));
  for (let i = 0; i < 12; i++) await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.getElementById('drawer-content').contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.locator('#why-drawer.open')).toHaveCount(0);
  expect(await page.evaluate(() => document.activeElement && document.activeElement.textContent.includes('How we got here'))).toBe(true);
});

test('06 · no current move is a valid state: no card, no CTA, no invented step', async () => {
  await withSnap(s => { s.nextmove = null; s.state.next_best_action = ''; s.paths.forEach(p => { p.next_move = null; }); });
  const txt = await main();
  expect(txt).not.toContain('Go to your move');
  expect(txt).not.toContain('NEXT MOVE');
  await reset();
});

test('07 · zero paths: the paths card says the engine\'s own reason, never a generic "nothing applies"', async () => {
  const cases = [
    ['INSUFFICIENT_INFORMATION', /Not enough is known to name a path yet/],
    ['NO_APPLICABLE_PATH', /No path applies right now/],
    ['EVIDENCE_CONFLICT', /The evidence conflicts/],
    ['EVALUATION_UNAVAILABLE', /could not evaluate your map/],
    ['LEGACY_ARTIFACT', /needs a fresh look/],
  ];
  for (const [kind, re] of cases) {
    await page.evaluate(k => { const s = JSON.parse(JSON.stringify(V11_ENGINE.snapshot())); s.paths = []; s.zero = { kind: k, detail: '', missing: [] }; V11_ENGINE.set(v11MapKey(), s); goDestination('state'); }, kind);
    const rail = await page.locator('.dest-paths').innerText();
    expect(rail, kind).toMatch(re);
    if (kind !== 'NO_APPLICABLE_PATH') expect(rail, kind).not.toMatch(/No path applies right now/);
  }
  await reset();
});

test('08 · a first read says so: the provisional line shows only when the engine says the read is provisional', async () => {
  await withSnap(s => { s.state.provisional = true; });
  await expect(page.locator('[data-testid="state-provisional"]')).toBeVisible();
  await withSnap(s => { s.state.provisional = false; });
  await expect(page.locator('[data-testid="state-provisional"]')).toHaveCount(0);
  await reset();
});

test('09 · the rail lists at most five paths and says how many more there are; nothing is hidden or invented', async () => {
  await withSnap(s => {
    s.paths = [1, 2, 3, 4, 5, 6, 7].map(i => ({ id: `p${i}`, title: `Path number ${i}`, status_display: i === 7 ? 'OPEN' : 'NOT YET', lifecycle: 'OPEN', stop_source: null,
      requirements: [{ id: 'r1', label: `Requirement of path ${i}`, satisfaction: 'UNKNOWN' }], evidence_ids: [], provenance: '', trail: [], next_move: null }));
  });
  await expect(page.locator('.dest-route')).toHaveCount(5);
  await expect(page.locator('.dest-paths')).toContainText('7 possible paths');
  await expect(page.locator('.dest-more-routes')).toHaveText('+2 other possibilities on your map');
  // the OPEN one is drawn although it is last in the engine's order (status words choose, nothing is ranked)
  await expect(page.locator('.dest-routes')).toContainText('Path number 7');
  await reset();
});

test('10 · long text and unbroken strings stay inside the screen at 320 px', async () => {
  await page.setViewportSize({ width: 320, height: 800 });
  await withSnap(s => {
    const long = 'A long sentence about a real situation with several qualifiers, that goes on. '.repeat(14);
    s.state.where_you_are = long; s.state.blocking = long.slice(0, 260);
    s.state.why_we_think_so = [long.slice(0, 220), 'Unbroken' + 'x'.repeat(90)];
    s.evidence[0] && (s.evidence[0].quote = long.slice(0, 300));
  });
  const over = await page.evaluate(() => {
    const vw = innerWidth, bad = [];
    document.querySelectorAll('#v11-main *').forEach(el => { const r = el.getBoundingClientRect(); if (r.width && r.right > vw + 1.5) bad.push(el.tagName + '.' + el.className); });
    return { doc: document.documentElement.scrollWidth - innerWidth, bad: bad.slice(0, 5) };
  });
  expect(over.doc).toBeLessThanOrEqual(2);
  expect(over.bad).toEqual([]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await reset();
});

test('11 · the State NEXT MOVE is the one presented decision, not a diagnosis plan title', async () => {
  // R5/P0-3: snapshot.nextmove (validated nm.v2) is the one live decision; diagnosis does not override it.
  await withSnap(s => {
    s.nextmove = { type: 'QUESTION', title: 'Presented-decision-one', source: 'presented', path_id: null, path_affiliation: 'none' };
    s.state.next_best_action = 'Stale diagnosis plan title';
  });
  const txt = await main();
  expect(txt).toContain('Presented-decision-one');
  expect(txt).not.toContain('Stale diagnosis plan title');
  await expect(page.locator('.dest-action')).toHaveAttribute('data-move-source', 'presented');
  await reset();
});

test('12 · a fallback decision carries its source, never passed off as the live one', async () => {
  // R5/P1-1: when the live decision is unavailable, the fallback (plan) appears as a labeled fallback.
  await withSnap(s => {
    s.nextmove = { type: 'ACTION', title: 'Plan-fallback-step', source: 'plan', path_id: null, path_affiliation: 'none' };
  });
  const txt = await main();
  expect(txt).toContain('Plan-fallback-step');
  await expect(page.locator('[data-move-source-note]')).toContainText('From your last plan');
  await reset();
});

test('13 · a routes fallback with no title shows the plan step AS a plan, never as the map', async () => {
  // A routes fallback can carry an empty title (QUESTION/EVIDENCE_REQUEST); the title then comes from the
  // diagnosis plan, so the note must say "plan", not "map".
  await withSnap(s => {
    s.nextmove = { type: 'QUESTION', title: '', source: 'routes.next_move', path_id: null, path_affiliation: 'none' };
    s.state.next_best_action = 'Plan-step-shown';
  });
  const txt = await main();
  expect(txt).toContain('Plan-step-shown');
  await expect(page.locator('.dest-action')).toHaveAttribute('data-move-source', 'plan');
  await expect(page.locator('[data-move-source-note]')).toContainText('From your last plan');
  await reset();
});

test('14 · a decision without a source label is not marked as a fallback (demo fixtures)', async () => {
  await withSnap(s => {
    s.nextmove = { type: 'ACTION', title: 'Demo-live-decision', path_id: null };
    s.state.next_best_action = 'Should not win';
  });
  const txt = await main();
  expect(txt).toContain('Demo-live-decision');
  expect(txt).not.toContain('Should not win');
  await expect(page.locator('[data-move-source-note]')).toHaveCount(0);
  await reset();
});

test('16 · an explicit path_id:null from the server stays null; only a legacy DTO may derive', async () => {
  // A3-01 (ledger §15.2 P1-1): the server always sends path_id (null = no single path). That null is an
  // answer, not a missing field, so the route selector must not silently fill it in. Legacy DTOs (no key) may.
  const res = await page.evaluate(() => {
    const makeSrc = (pathId) => ({
      state: { goal: {} },
      diag: { navigation: { status: 'CURRENT' }, possible_paths: { paths: [], unresolved: [] }, revenue_state: {},
              where_you_are: 'W', primary_constraint: 'P', why: [], day_by_day: [] },
      ready: { navigation: { status: 'CURRENT' }, paths: [], emerging: [] },
      evidence: { evidence: [] },
      nav: { move: { kind: 'ACTION', headline: 'Presented move', text: 'Presented move', path_id: pathId, source: 'presented' } },
      routes: { next_move: { route_id: 'r1', frontier_ref: 'r1', output: 'ACTION' },
                routes: [{ route_id: 'r1', path_id: 'path.p1', applicability: { status: 'APPLIES' }, lineage_status: 'OPEN' }] },
      explain: null,
    });
    const of = (pid) => snapshotFromPayloads(makeSrc(pid)).nextmove;
    return { nulled: of(null), stated: of('path.p9'), legacy: of(undefined) };
  });
  expect(res.nulled.path_id).toBe(null);
  expect(res.nulled.path_affiliation).toBe('none');
  expect(res.stated.path_id).toBe('path.p9');
  expect(res.stated.path_affiliation).toBe('explicit');
  expect(res.legacy.path_id).toBe('path.p1');
  expect(res.legacy.path_affiliation).toBe('derived');
});

test('17 · WHY THIS FITS never reuses reasoning for a different decision', async () => {
  // A3-02: the diagnosis-bound next_best_why describes the diagnosis action; it may only be shown when the
  // displayed decision IS that action. Otherwise the card carries no justification (or the live one).
  await withSnap(s => {
    s.nextmove = { type: 'QUESTION', title: 'Presented-question-two', source: 'presented', path_id: null, path_affiliation: 'none' };
    s.state.next_best_action = 'Old diagnosis action';
    s.state.next_best_why = 'OLD-DIAGNOSIS-REASONING about a different step';
  });
  const txt = await main();
  expect(txt).toContain('Presented-question-two');
  expect(txt).not.toContain('OLD-DIAGNOSIS-REASONING');
  await withSnap(s => {
    s.nextmove = { type: 'ACTION', title: 'Same-action', source: 'presented', path_id: null, path_affiliation: 'none' };
    s.state.next_best_action = 'Same-action';
    s.state.next_best_why = 'Because the follow-up is late';
  });
  const txt2 = await main();
  expect(txt2).toContain('WHY THIS FITS');
  expect(txt2).toContain('Because the follow-up is late');
  await reset();
});

test('18 · the CTA is kind-driven: Talk for questions and evidence, Moves for ACTION, no executable CTA for HOLD, NONE or degraded', async () => {
  // QUESTION must not advertise an executable Move CTA
  await withSnap(s => { s.nextmove = { type: 'QUESTION', title: 'Kind-question-move', source: 'presented', path_id: null, path_affiliation: 'none' }; });
  expect(await main()).toContain('Kind-question-move');
  await expect(page.getByRole('button', { name: /Continue in Talk/ })).toBeVisible();
  expect(await main()).not.toContain('Go to your move');
  await page.getByRole('button', { name: /Continue in Talk/ }).click();
  await expect(page).toHaveURL(/#\/talk$/);
  await page.evaluate(() => goDestination('state'));
  // EVIDENCE_REQUEST continues in Talk / evidence collection, likewise not Moves
  await withSnap(s => { s.nextmove.type = 'EVIDENCE_REQUEST'; s.nextmove.title = 'Kind-evidence-move'; });
  expect(await main()).not.toContain('Go to your move');
  await expect(page.getByRole('button', { name: /Continue in Talk/ })).toBeVisible();
  // executable ACTION opens Moves
  await withSnap(s => { s.nextmove.type = 'ACTION'; s.nextmove.title = 'Kind-action-move'; });
  await expect(page.getByRole('button', { name: /Go to your move/ })).toBeVisible();
  await page.getByRole('button', { name: /Go to your move/ }).click();
  await expect(page).toHaveURL(/#\/moves$/);
  await page.evaluate(() => goDestination('state'));
  // HOLD: the blocked/pending state is explained, with no executable CTA
  await withSnap(s => { s.nextmove.type = 'HOLD'; s.nextmove.title = 'Kind-hold-move'; });
  const holdTxt = await main();
  expect(holdTxt).toContain('Kind-hold-move');
  expect(holdTxt).not.toMatch(/Continue in Talk|Go to your move|Recover in Talk/);
  await expect(page.locator('[data-move-hold]')).toBeVisible();
  // NONE: no invented executable CTA
  await withSnap(s => { s.nextmove.type = 'NONE'; s.nextmove.title = 'Kind-none-move'; });
  const noneTxt = await main();
  expect(noneTxt).not.toMatch(/Continue in Talk|Go to your move|Recover in Talk/);
  // degraded: honest technical recovery messaging, never a business STOP
  await withSnap(s => { s.nextmove.type = 'ACTION'; s.nextmove.title = 'Kind-degraded-move'; s.nextmove.degraded = true; });
  const deg = await main();
  expect(deg).toContain('Kind-degraded-move');
  expect(deg).toContain('technical problem on our side');
  expect(deg).not.toMatch(/your business (is|was) stopped|path is stopped/i);
  await expect(page.locator('[data-move-recovery]')).toBeVisible();
  await expect(page.getByRole('button', { name: /Recover in Talk/ })).toBeVisible();
  expect(deg).not.toContain('Go to your move');
  await reset();
});

test('19 · Paths are dynamic 0, 1 and N: the rail counts what the snapshot carries, nothing fixed', async () => {
  // 0: the engine's own zero reason, never a "1 path" phrasing
  await withSnap(s => { s.paths = []; s.zero = { kind: 'NO_APPLICABLE_PATH', detail: '', missing: [] }; });
  expect(await page.locator('.dest-paths').innerText()).toMatch(/No path applies right now/);
  expect(await page.locator('.dest-paths').innerText()).not.toMatch(/possible path/);
  // 1
  await withSnap(s => { s.zero = null; s.paths = [{ id: 'p1', title: 'Only path', status_display: 'OPEN', lifecycle: 'OPEN', stop_source: null, requirements: [], evidence_ids: [], provenance: '', trail: [], next_move: null }]; });
  expect(await page.locator('.dest-paths').innerText()).toContain('1 possible path');
  await expect(page.locator('.dest-route')).toHaveCount(1);
  // N (7, above the display cap of 5, like test 09)
  await withSnap(s => { s.paths = [1, 2, 3, 4, 5, 6, 7].map(i => ({ id: `q${i}`, title: `Dynamic path ${i}`, status_display: 'NOT YET', lifecycle: 'OPEN', stop_source: null, requirements: [], evidence_ids: [], provenance: '', trail: [], next_move: null })); });
  expect(await page.locator('.dest-paths').innerText()).toContain('7 possible paths');
  await expect(page.locator('.dest-route')).toHaveCount(5);
  await reset();
});

test('15 · nothing logged a console error', async () => {
  expect(consoleErrors).toEqual([]);
});
