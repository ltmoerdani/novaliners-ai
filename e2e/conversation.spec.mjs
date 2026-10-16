// M4 (docs/03-architecture-tech/14 §25): the conversation is a STATE LOOP, and the UI shows it. Real UI against the
// real API with the mock LLM provider (deterministic, no key, no quota). Nothing here is a phase, a step, or a script:
//
//   message -> evidence -> state -> adjudication -> paths -> planner -> next move (QUESTION | EVIDENCE_REQUEST |
//   ACTION | HOLD) -> next message -> ...
//
// What is proven in the browser (and looked at with eyes, via the committed baselines):
//   · every engine message says what kind of move it is and what it is about; the box above the input says what we are
//     asking and WHY, and the reason trail is inspectable (native <details>, keyboard only)
//   · answers may come in any order: answering something else resolves THAT need and the question changes
//   · "enough to map your options" (ACTION) shows a ready card while the conversation stays open
//   · "no safe next step" (HOLD) is said plainly, is not "finished", and new information resumes the conversation
//   · no obsolete wording (Step n/5, topics to go, Interview progress, phase) is on screen as authority
//   · light, dark and 390px; WCAG A+AA; zero console errors; the engine's own record of the move (GET /navigation)
//     agrees with what the screen shows and replays to the same decision
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { scanCopy } from './copy-guard.mjs';

test.describe.configure({ mode: 'serial' });

let page, ctx;
const consoleErrors = [];
const U = 'u_e2e' + Math.random().toString(16).slice(2, 10);

const GOAL = 'I am a marketing consultant. I want Rp20 million a month from my services within 90 days.';
const INCOME0 = 'Pendapatan saya sekarang Rp0 per bulan.';
const CAPACITY = 'Saya kerja sekitar 30 jam per minggu untuk delivery klien.';
const DEMAND = 'Ada 3 orang yang bertanya soal jasa saya bulan ini (inquiry masuk).';
const ICP = 'ICP saya berisi jenis usaha UKM, level direktur, dan peran pembeli owner.';

const a11y = async (where) => {
  const freeze = await page.addStyleTag({ content: '*, *::before, *::after { animation: none !important; transition: none !important; }' });
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  await freeze.evaluate(el => el.remove());
  expect(r.violations.map(v => `${v.id} x${v.nodes.length}: ` + v.nodes.map(n => (n.any[0] && n.any[0].message || '') + ' @ ' + n.target.join(' ')).join(' | ')), `a11y on ${where}`).toEqual([]);
};
// D9 (prototype doc 06 §12.9): pixels are advisory — same policy as live.spec. A difference above the config's
// maxDiffPixels becomes a "pixel-advisory" annotation with the count and the diff path and does not fail; a missing or
// resized baseline still fails.
const shot = async (name) => {
  expect(await scanCopy(page, { live: true }), `copy on ${name}`).toEqual([]);
  try {
    await expect(page).toHaveScreenshot(`conv-${name}.png`, { fullPage: false, stylePath: './screenshot.css' });
  } catch (e) {
    const m = String(e.message).match(/(\d+) pixels \(ratio ([\d.]+) of all image pixels\) are different/);
    if (!m) throw e;
    test.info().annotations.push({ type: 'pixel-advisory', description: `conv-${name}: ${m[1]} pixels differ (ratio ${m[2]}) — diff: ${test.info().outputPath(`conv-${name}-diff.png`)}` });
  }
};
// the wording of the OLD interview machine must never be on screen as authority
const noPhaseWords = async (where) => {
  const text = await page.evaluate(() => document.body.innerText);
  const bad = text.match(/\bStep \d\s*\/\s*5\b|\btopics? to go\b|\bInterview progress\b|\bphase\b|\bPHASE\b|\bAll topics covered\b/i);
  expect(bad && bad[0], `obsolete phase wording on ${where}`).toBeNull();
};
const lastEngine = () => page.locator('#chat-messages-container [data-move-kind]').last();
const lastEngineText = () => page.locator('#chat-messages-container [data-engine-text]').last();
async function send(text) {
  await page.fill('#diag-chat-input', text);
  await page.keyboard.press('Enter');
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
}
const nav = async () => {
  const sid = await page.evaluate(() => LIVE.sid);
  const r = await page.request.get(`/session/${sid}/navigation`);
  expect(r.ok()).toBe(true);
  return r.json();
};

// One browser identity per conversation (the teardown removes workspaces whose id starts with u_e2e)
async function openFresh(browser, userId) {
  const c = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  const p = await c.newPage();
  const now = new Date();
  await p.clock.setFixedTime(new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0));   // message times render as 00:00
  p.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  p.on('dialog', d => d.accept());
  await p.addInitScript((u) => { try { if (!localStorage.getItem('novaliners-v9')) localStorage.setItem('novaliners-v9', JSON.stringify({ userId: u, chain: [], checkins: [], overrides: [], tips: {} })); } catch (e) { /* ignore */ } }, userId);
  return { c, p };
}
test.beforeAll(async ({ browser }) => { ({ c: ctx, p: page } = await openFresh(browser, U)); });
test.afterAll(async () => { await ctx.close(); });

test('01 · the first message gets a move chosen from what the engine knows, with its reason one click away', async () => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', GOAL);
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page).toHaveURL(/#\/diagnosis$/);
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  // the goal is clear, the income is not measured: so that is what is asked (not "step 1 of 5")
  await expect(lastEngine()).toContainText('Question');
  await expect(page.getByText(/Your current income is not measured yet/).first()).toBeVisible();
  await expect(page.locator('#nav-focus')).toContainText('What we are asking about');
  await expect(page.locator('#nav-pill')).toContainText('Getting to know you');
  await noPhaseWords('first move');
  // "Why we ask this" is a native <details>: Enter opens it, no script involved
  await page.locator('.nav-why > summary').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.nav-why')).toHaveAttribute('open', '');
  await expect(page.locator('#nav-focus-text')).toContainText('No way forward is clear yet');            // the one-line reason...
  await expect(page.locator('.nav-why-list')).toContainText('You can tell us this directly');             // ...and the rest, not repeated
  await expect(page.locator('.nav-why-list')).not.toContainText('No way forward is clear yet');
  await page.locator('.nav-trail > summary').focus();
  await page.keyboard.press('Enter');
  const trail = await page.locator('.nav-trail-list').innerText();
  expect(trail).toMatch(/stage EMERGENCE/);
  expect(trail).toMatch(/input [0-9a-f]{16}/);
  // the screen agrees with the engine's own record of the move, and the engine can replay it
  const n = await nav();
  expect(trail).toContain(`input ${n.move.reason.input_digest}`);
  expect(n.last_logged.replay).toBe(true);
  expect(n.move.kind).toBe('QUESTION');
  // the digest is a hash of the planner input: verified above, then pinned for the picture so the baseline is not
  // coupled to the exact shape of that input (any additive input field would otherwise repaint 16 characters)
  await page.locator('.nav-trail-list li', { hasText: /^input [0-9a-f]{16}$/ }).evaluate(el => { el.textContent = 'input 0123456789abcdef'; });
  await a11y('01-first-move-why-open'); await shot('01-question-why-open');
});

test('02 · answering something ELSE (any order) resolves that need and the next question follows the state', async () => {
  await page.locator('.nav-why > summary').focus(); await page.keyboard.press('Enter');   // close it again
  await send(INCOME0);
  await expect(page.locator('#nav-pill')).toContainText(/Understanding your situation|Some possibilities are emerging|First picture available|Getting to know you|Technical pause/);
  const asked = await lastEngine().innerText();
  expect(asked).toContain('Question');
  // the engine asked about demand; the user answers about capacity instead (free order)
  await send(CAPACITY);
  const n = await nav();
  expect(n.requirements['delivery.capacity'].satisfaction).toBe('PRESENT');
  // capacity is now known, so it is never asked again; the same demand need is asked a second time, as a request for evidence
  await expect(lastEngineText()).not.toContainText('Hours you can spare');
  await expect(lastEngineText()).toContainText(/Demand \(leads or inquiries\)/);
  await expect(lastEngine()).toContainText('Needs evidence');
  await noPhaseWords('free-order answer');
  await shot('02-evidence-request');
  // the evidence panel counts facts and what is clear, with no progress toward a fixed list of topics
  await page.getByRole('button', { name: /What we know/ }).click();
  await expect(page.locator('#nav-counts')).toContainText(/Understanding your situation|Some possibilities are emerging|First picture available|Getting to know you/);
  await noPhaseWords('evidence panel');
  await a11y('02-evidence-panel'); await shot('02-evidence-panel');
  await page.getByRole('button', { name: 'Close summary' }).click();
});

test('03 · enough to map the options: the ready card appears, the conversation stays open, adjudication shows in the engine record', async () => {
  await send(DEMAND);
  await expect(lastEngine()).toContainText('Question');
  await expect(page.getByText(/A written ideal client/).first()).toBeVisible();   // asks for the ICP: a requirement the engine CAN settle
  await send(ICP);
  await expect(lastEngine()).toContainText('Ready');
  await expect(page.getByText(/You have enough to act on\. First step: List real people by name/)).toBeVisible();
  await expect(page.locator('#nav-focus')).toContainText('What happens next');
  await expect(page.locator('#nav-pill')).toContainText('Ready to map');
  // ready, but not closed: the card offers the diagnosis AND the box still takes more details
  // (CIR-05: the offer now comes from checkpoint_eligibility — copy "first picture", not "interview complete")
  await expect(page.getByRole('heading', { name: 'There is enough for a first read of your situation.' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Build my diagnosis/ })).toBeVisible();   // the card's button (the small link is a second, quieter way)
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible();
  await noPhaseWords('ready card');
  await a11y('03-ready'); await shot('03-ready');
  // the engine's record: the ICP was settled by a reviewed rule (not by the mapper or the model), with its evidence
  const n = await nav();
  const icp = n.requirements['access.icp'];
  expect(icp.satisfaction).toBe('PRESENT');
  // Gate A (15 Oct, P5a): the verification label = deterministic ADJUDICATOR IDENTITY (the old label
  // 'formal_rule_adjudication' was changed in commit 72a6dd4; this e2e assertion lagged behind).
  expect(icp.verification.method).toBe('deterministic_adjudicator');
  expect(icp.evidence_refs.length).toBeGreaterThan(0);
  expect(n.move.kind).toBe('ACTION');
  expect(n.last_logged.replay).toBe(true);
  // nothing the user did NOT say became a fact: no requirement is ABSENT just because it was not mentioned
  expect(Object.values(n.requirements).filter(r => r.satisfaction === 'ABSENT')).toEqual([]);
});

test('04 · after "ready" the conversation is not locked: new information is read and the move is recomputed', async () => {
  await send('Saya juga punya tiga proyek portofolio yang sudah selesai.');
  await expect(lastEngine()).toBeVisible();
  const n = await nav();
  expect(['QUESTION', 'EVIDENCE_REQUEST', 'ACTION', 'HOLD']).toContain(n.move.kind);
  expect(n.last_logged.replay).toBe(true);
  expect(await page.locator('#diag-chat-input').isEnabled()).toBe(true);
});

test('05 · reload: an open conversation restores what is being asked and why, from the server', async () => {
  await page.reload({ waitUntil: 'networkidle' });
  await expect(page.locator('#diag-chat-input')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('#nav-focus .nav-focus-label')).toHaveText(/What we are asking about|What happens next|Where this stands/);
  // earlier engine messages get their move caption back (restored from the engine's own record of what it presented)
  await expect(page.locator('#chat-messages-container [data-move-kind]').first()).toBeVisible();
  expect(await page.locator('#chat-messages-container [data-move-kind]').count()).toBeGreaterThanOrEqual(4);
  const kinds = await page.locator('#chat-messages-container [data-move-kind]').evaluateAll(els => els.map(e => e.getAttribute('data-move-kind')));
  expect(kinds).toContain('QUESTION'); expect(kinds).toContain('EVIDENCE_REQUEST'); expect(kinds).toContain('ACTION');
  await noPhaseWords('after reload');
});

test('06 · light, dark and a phone: the same conversation reads and stays accessible', async () => {
  await page.evaluate(() => setTheme('dark'));
  await a11y('06-dark'); await shot('06-dark');
  await page.evaluate(() => setTheme('light'));
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflow, 'no page-level horizontal scroll at 390px').toBe(false);
  await a11y('06-390'); await shot('06-390');
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('07 · HOLD: no safe next question is said plainly, it is not "finished", and new information resumes it', async ({ browser }) => {
  const keep = { c: ctx, p: page };
  ({ c: ctx, p: page } = await openFresh(browser, 'u_e2e' + Math.random().toString(16).slice(2, 10)));
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', 'halo apa kabar semuanya baik');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/I first need a clear goal/).first()).toBeVisible();          // goal unknown -> asked
  await send('oke terima kasih banyak ya');
  await expect(page.getByText(/I first need a clear goal/)).toHaveCount(2);               // asked a second time, then no more
  await send('sampai jumpa lagi nanti');
  await expect(lastEngine()).toContainText('On hold');
  await expect(page.getByText(/I can't point to a safe next step yet/)).toBeVisible();
  await expect(page.locator('#nav-focus')).toContainText('Where this stands');
  await expect(page.locator('#nav-pill')).toContainText('On hold');
  // HOLD is not "done": the box is still there and no diagnosis card was offered
  await expect(page.locator('#diag-chat-input:not([disabled])')).toBeVisible();
  await expect(page.getByRole('heading', { name: /That is enough to map|That is all we need|There is enough for a first read/ })).toHaveCount(0);
  await noPhaseWords('hold');
  await a11y('07-hold'); await shot('07-hold');
  const held = await nav();
  expect(held.move.kind).toBe('HOLD');
  // new information resumes the conversation (HOLD does not lock)
  await send('Saya mau Rp20 juta per bulan dari jasa dalam 90 hari. Pendapatan saya sekarang Rp0 per bulan.');
  await expect(lastEngine()).toContainText('Question');
  expect((await nav()).move.kind).toBe('QUESTION');
  await ctx.close();
  ({ c: ctx, p: page } = keep);
});

test('08 · nothing logged a console error during the whole conversation', async () => {
  expect(consoleErrors).toEqual([]);
});
