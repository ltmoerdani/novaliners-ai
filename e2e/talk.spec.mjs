// Talk destination (record P5e; doc 10 §6.5; prototype behavior.mjs "talk"): a conversation that is real. What is typed
// is read from the box, shown exactly as typed in the writer's own language, sent to the real conversation endpoint
// (POST /session/{sid}/ask) and answered by it; nothing is echoed or scripted. Empty and too-long messages are refused with a
// visible, associated error and no message; Shift+Enter is a new line; HTML is text; the draft and the transcript survive
// leaving and returning; the transcript is a polite live region that announces additions only; the side panel lists the
// same paths Maps shows. A question never changes the record. Live UI against the real API with the mock LLM.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test.describe.configure({ mode: 'serial' });

const here = path.dirname(fileURLToPath(import.meta.url));
const fx = name => JSON.parse(fs.readFileSync(path.join(here, 'fixtures', `${name}.json`), 'utf8'));

let page, ctx;
const consoleErrors = [];
const asks = [];
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(120); };
const input = () => page.locator('#talk-ongoing-input');
const mine = () => page.locator('#chat-messages-container .talk-msg.is-mine .talk-bubble');
const theirs = () => page.locator('#chat-messages-container .talk-msg:not(.is-mine) .talk-body');
const BAHASA = 'Dua orang minta dikabari kalau saya mulai. Tolong bantu saya menulis penawarannya.';

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/500 \(Internal Server Error\)|Failed to load resource/.test(m.text())) consoleErrors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  page.on('request', r => { if (/\/session\/[^/]+\/ask$/.test(r.url()) && r.method() === 'POST') asks.push(JSON.parse(r.postData() || '{}')); });
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

test('01 · Talk is a conversation frame: the destination eyebrow, what the answers are grounded in, the transcript, the composer', async () => {
  await go(`goDestination('talk')`);
  await expect(page).toHaveURL(/#\/talk$/);
  await expect(page.locator('.v11-eyebrow')).toContainText('Talk');
  await expect(page.locator('.talk-head-chip')).toContainText('Grounded in your state');
  await expect(page.locator('#chat-messages-container')).toHaveAttribute('role', 'log');
  await expect(page.locator('#chat-messages-container')).toHaveAttribute('aria-live', 'polite');
  await expect(page.locator('#chat-messages-container')).toHaveAttribute('aria-relevant', 'additions');
  await expect(input()).toBeVisible();
  await expect(page.locator('.talk-send')).toBeVisible();
  expect(await page.locator('#chat-messages-container').innerText()).toContain('A question never changes your record.');
  await expect(page.locator('.ask-chip').first()).toBeVisible();      // suggested questions from the engine's own paths
});

test('02 · typed text is read from the box, sent to the real endpoint, shown verbatim in the writer\'s language, and answered by the server', async () => {
  asks.length = 0;
  await input().fill(BAHASA);
  await page.locator('.talk-send').click();
  await expect(mine().last()).toHaveText(BAHASA);                       // not translated, not shortened, not corrected
  await expect.poll(() => asks.length).toBe(1);
  expect(asks[0].question).toBe(BAHASA);                                 // what the server received is what was typed
  await expect(theirs().last()).not.toHaveText('', { timeout: 20_000 });
  await expect(page.locator('#talk-thinking')).toHaveCount(0);
  const reply = await theirs().last().innerText();
  expect(reply.length).toBeGreaterThan(20);
  expect(reply).not.toMatch(/prototype|scripted|not analyzed/i);        // a real answer, not a stand-in
  expect(await input().inputValue()).toBe('');                           // the box is cleared once it was sent
});

test('03 · empty and whitespace-only messages are refused with a visible, associated error, and no message and no request', async () => {
  asks.length = 0;
  const before = await mine().count();
  await input().fill('   \n  ');
  await page.locator('.talk-send').click();
  await expect(page.locator('#talk-error')).toBeVisible();
  await expect(page.locator('#talk-error')).toContainText('An empty message is not sent');
  await expect(input()).toHaveAttribute('aria-invalid', 'true');
  expect(await input().getAttribute('aria-describedby')).toContain('talk-error');
  expect(await mine().count()).toBe(before);
  expect(asks.length).toBe(0);
  await input().fill('x');                                               // typing clears the error
  await expect(page.locator('#talk-error')).toBeHidden();
  await input().fill('');
});

test('04 · Shift+Enter is a new line, Enter sends, and a multi-line message is kept as written', async () => {
  asks.length = 0;
  await input().click();
  await page.keyboard.type('First line');
  await page.keyboard.press('Shift+Enter');
  await page.keyboard.type('Second line');
  expect(await input().inputValue()).toBe('First line\nSecond line');
  await page.keyboard.press('Enter');
  await expect.poll(() => asks.length).toBe(1);
  expect(asks[0].question).toBe('First line\nSecond line');
  await expect(mine().last()).toContainText('Second line');
  await expect(theirs().last()).not.toHaveText('', { timeout: 20_000 });
});

test('05 · a message over the limit is not sent, the text stays in the box, and the error says how long it is and what the limit is', async () => {
  asks.length = 0;
  const long = 'a'.repeat(2001);
  await input().fill(long);
  await page.keyboard.press('Enter');
  await expect(page.locator('#talk-error')).toContainText('2,001 characters');
  await expect(page.locator('#talk-error')).toContainText('2,000');
  expect(await input().inputValue()).toBe(long);
  expect(asks.length).toBe(0);
  await input().fill('');
});

test('06 · HTML in a message is shown as text and never executed; repeated sends accumulate in order', async () => {
  const before = await mine().count();
  await input().fill('<img src=x onerror="window.__xss=1"><b>bold</b>');
  await page.keyboard.press('Enter');
  await expect(mine().last()).toContainText('<img src=x onerror=');
  expect(await page.evaluate(() => window.__xss)).toBeUndefined();
  await expect(page.locator('#chat-messages-container .talk-bubble b')).toHaveCount(0);
  await expect(theirs().last()).not.toHaveText('', { timeout: 20_000 });
  // `theirs()` also matches the "Thinking…" indicator (.talk-body), so the line above could be
  // satisfied by the indicator itself — wait until the answer is REALLY finished before sending
  // again, otherwise sendTalkMessage refuses (askThinking) and the second message is never sent.
  await page.waitForFunction(() => !(window.LIVE && LIVE.askThinking) && !document.getElementById('talk-thinking'),
                             undefined, { timeout: 20_000 });
  await input().fill('Second message');
  await page.keyboard.press('Enter');
  await expect(mine()).toHaveCount(before + 2);
  const order = await mine().allInnerTexts();
  expect(order.slice(-2)[0]).toContain('<img src=x');
  expect(order.slice(-1)[0]).toBe('Second message');
  await expect(theirs().last()).not.toHaveText('', { timeout: 20_000 });
  await page.waitForFunction(() => !(window.LIVE && LIVE.askThinking) && !document.getElementById('talk-thinking'),
                             undefined, { timeout: 20_000 });
});

test('07 · the draft and the whole transcript survive leaving Talk and coming back', async () => {
  const n = await mine().count();
  await input().fill('A draft I did not send');
  await go(`goDestination('maps')`);
  await go(`goDestination('talk')`);
  expect(await input().inputValue()).toBe('A draft I did not send');
  expect(await mine().count()).toBe(n);
  await input().fill('');
});

test('08 · the transcript is a polite live region that gets only what is new: earlier messages are not re-created', async () => {
  await page.evaluate(() => { window.__before = [...document.querySelectorAll('#chat-messages-container .talk-msg')]; });
  await input().fill('One more question');
  await page.keyboard.press('Enter');
  await expect(theirs().last()).not.toHaveText('', { timeout: 20_000 });
  const kept = await page.evaluate(() => window.__before.every(n => document.contains(n)));
  expect(kept, 'earlier message nodes are the same nodes').toBe(true);
});

test('09 · a failed request is said plainly, nothing is invented in its place, and the message goes back into the box', async () => {
  await page.route(/\/session\/[^/]+\/ask$/, r => r.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'boom' }) }));
  const before = await theirs().count();
  await input().fill('This will fail');
  await page.keyboard.press('Enter');
  await expect(page.locator('#chat-messages-container .talk-msg.is-error')).toContainText('That did not go through');
  expect(await input().inputValue()).toBe('This will fail');
  expect(await theirs().count()).toBe(before + 1);                       // only the error, no made-up answer
  await page.unroute(/\/session\/[^/]+\/ask$/);
  await input().fill('');
});

test('10 · the side panel lists exactly the paths Maps shows, with the same status words, each opening that path in Maps', async () => {
  await go(`V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); STORE.chatEvidenceOpen = true; STORE.chatPanelTab = 'map'; goDestination('talk')`);
  const talkRows = await page.locator('.talk-paths .dest-route').evaluateAll(els => els.map(e => e.querySelector('span').textContent.replace(/\s+/g, ' ').trim().replace(' In focus', '') + '|' + e.querySelector('.dest-route-state').textContent.trim()));
  const snap = await page.evaluate(() => { const s = V11_ENGINE.snapshot(); return presentSnapshotPaths(s.paths, { pinned: [(mapsActive(s) || {}).id] }).visible.map(p => p.title + '|' + mapsStateWord(p)); });
  expect(talkRows).toEqual(snap);
  await page.locator('.talk-paths .dest-route').nth(1).click();
  await expect(page).toHaveURL(/#\/maps$/);
  expect(await page.evaluate(() => selectedPathId())).toBe(await page.evaluate(() => V11_ENGINE.snapshot().paths[1].id));
  await go(`STORE.chatEvidenceOpen = false; V11_ENGINE.clear()`);
});

test('11 · "Talk about this" from a path opens Talk with that path as its context, and the question carries it', async () => {
  // five paths the engine formed (a fixture built by the real engine), so the map has paths to talk about
  await page.evaluate(f => { V11_ENGINE.clear(); LIVE.artifact.possible_paths = f.possible_paths; LIVE.artifact.navigation = f.navigation; LIVE.projection = null; LIVE.projectionTried = LIVE.sid; STORE.talkAbout = null; }, fx('paths_five'));
  const first = await page.evaluate(() => V11_ENGINE.snapshot().paths[0]);
  expect(first, 'the fixture has paths').toBeTruthy();
  await go(`openTalkAbout('${first.id}')`);
  await expect(page).toHaveURL(/#\/talk$/);
  await expect(page.locator('.talk-about-chip')).toContainText(first.title);
  expect(await page.locator('#chat-messages-container').innerText()).toContain(`“${first.title}”`);
  asks.length = 0;
  await input().fill('What does it still need?');
  await page.keyboard.press('Enter');
  await expect.poll(() => asks.length).toBe(1);
  expect(asks[0].focus).toBe(first.title);
  await expect(theirs().last()).not.toHaveText('', { timeout: 20_000 });
});

test('13 · demo mode has no engine behind it and says so: the same frame, messages stay on the page', async ({ baseURL }) => {
  const p = await ctx.newPage();
  await p.goto(`${baseURL}/?demo=1#/talk`, { waitUntil: 'networkidle' });
  await p.evaluate(() => goDestination('talk'));
  await expect(p.locator('.talk-head-chip')).toContainText('Demo');
  await p.locator('#talk-ongoing-input').fill('Hello there');
  await p.keyboard.press('Enter');
  await expect(p.locator('#chat-messages-container .talk-msg.is-mine .talk-bubble').last()).toHaveText('Hello there');
  await expect(p.locator('#chat-messages-container')).toContainText('not analyzed, not saved to your record');
  await p.close();
});

test('14 · the composer stays usable at 320 px with a long multi-line message, and nothing scrolls sideways', async () => {
  await page.setViewportSize({ width: 320, height: 800 });
  await go(`STORE.chatEvidenceOpen = false; goDestination('talk')`);
  await input().fill('A long line of text that keeps going and going. '.repeat(8) + '\nand another line\nand another');
  const dx = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth - innerWidth, send: (() => { const r = document.querySelector('.talk-send').getBoundingClientRect(); return [r.left, r.right, r.bottom]; })() }));
  expect(dx.doc).toBeLessThanOrEqual(2);
  expect(dx.send[0]).toBeGreaterThanOrEqual(0); expect(dx.send[1]).toBeLessThanOrEqual(321); expect(dx.send[2]).toBeLessThanOrEqual(801);
  await input().fill('');
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('12 · "Update my diagnosis" is the way to record a change: it opens the follow-up where it is reported, a question does not', async () => {
  await go(`STORE.talkAbout = null; goDestination('talk')`);
  await page.getByRole('button', { name: 'Update my diagnosis' }).click();
  await expect(page).toHaveURL(/#\/diagnosis$/);
  await expect(page.locator('#diag-chat-input')).toBeVisible();
});

test('15 · nothing logged a console error', async () => {
  expect(consoleErrors).toEqual([]);
});
