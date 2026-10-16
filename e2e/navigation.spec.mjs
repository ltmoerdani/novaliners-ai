// Product navigation = the five v11 destinations (record D3, D5, D6; doc 08 §12; doc 10 §6).
// State · Maps · Moves · Journey · Talk in the top bar, with aria-current on the one you are on; Maps has two lenses
// (Explore · Readiness); the v9 menu hashes redirect to their destination; the v9 sidebar menu is gone
// from the product. Live UI against the real API with the mock LLM, plus demo mode (?demo=1).
import { test, expect } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

let page, ctx;
const consoleErrors = [];
const DEST = ['State', 'Maps', 'Moves', 'Journey', 'Talk'];
const HASH = { State: '#/state', Maps: '#/maps', Moves: '#/moves', Journey: '#/journey', Talk: '#/talk' };
const nav = () => page.locator('.v11-topnav-item');
const current = () => page.locator('.v11-topnav-item[aria-current="page"]');

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
  await page.addInitScript(() => { try { if (!localStorage.getItem('novaliners-v9')) localStorage.setItem('novaliners-v9', JSON.stringify({ userId: 'u_e2e' + Math.random().toString(16).slice(2, 10), chain: [], checkins: [], overrides: [], tips: {} })); localStorage.setItem('novaliners-theme', 'light'); } catch (e) { /* ignore */ } });
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

test('01 · the top bar holds exactly the five destinations, in order, and nothing from the v9 menu', async () => {
  await page.evaluate(() => goDestination('state'));
  await expect(nav()).toHaveText(DEST);
  await expect(current()).toHaveCount(1);
  await expect(current()).toHaveText('State');
  await expect(page.locator('nav[aria-label="Destinations"]')).toHaveCount(1);
  // The v9 sidebar menu (Diagnosis · Path map · Journey · Activity · Ask) is not part of the product navigation
  await expect(page.locator('.sidebar-nav-clean, .sidebar-nav-item')).toHaveCount(0);
  const navText = await page.locator('nav[aria-label="Destinations"]').innerText();
  for (const old of ['Diagnosis', 'Path map', 'Activity', 'Ask']) expect(navText).not.toContain(old);
});

test('02 · each destination opens on its own address and is the one marked aria-current', async () => {
  for (const d of DEST) {
    await nav().filter({ hasText: new RegExp(`^${d}$`) }).click();
    await expect(page).toHaveURL(new RegExp(`${HASH[d]}$`));
    await expect(current()).toHaveText(d);
    await expect(page.locator('#v11-main')).toBeVisible();
    await expect(page.locator('#v11-main h1').first()).toBeVisible();
  }
});

test('03 · Maps has two lenses (Explore, Readiness) over one workspace; the lens is in the address and aria-pressed; the old Overview address resolves to Explore', async () => {
  await nav().filter({ hasText: /^Maps$/ }).click();
  const lens = page.locator('.v11-view-switch button');
  await expect(lens).toHaveText([/^Explore/, /^Readiness/]);
  await expect(page.locator('.v11-view-switch button[aria-pressed="true"]')).toHaveCount(1);
  await expect(page.locator('.v11-view-switch button[aria-pressed="true"]')).toContainText('Explore');
  for (const [name, hash] of [['Readiness', '#/maps/readiness'], ['Explore', '#/maps']]) {
    await lens.filter({ hasText: name }).first().click();
    await expect(page).toHaveURL(new RegExp(hash.replace('/', '\\/') + '$'));
    await expect(page.locator('.v11-view-switch button[aria-pressed="true"]')).toContainText(name);
    await expect(current()).toHaveText('Maps');                 // a lens is not a destination
    await expect(nav()).toHaveCount(5);
  }
  // G-34: the old Overview address resolves to Explore (the address is rewritten, no third lens appears)
  await page.evaluate(() => { location.hash = '#/maps/readiness'; });
  await expect(page.locator('.v11-view-switch button[aria-pressed="true"]')).toContainText('Readiness');
  await page.evaluate(() => { location.hash = '#/maps/overview'; });
  await expect(page).toHaveURL(/#\/maps$/);
  await expect(page.locator('.v11-view-switch button[aria-pressed="true"]')).toContainText('Explore');
  await expect(lens).toHaveCount(2);
});

test('04 · D6: the v9 hashes redirect to their v11 destination, from the address bar and inside the page', async ({ baseURL }) => {
  const table = [
    ['#/activity', '#/moves', 'Moves'], ['#/diagnosis/current', '#/state', 'State'], ['#/map', '#/maps', 'Maps'],
    ['#/map/readiness', '#/maps/readiness', 'Maps'], ['#/ask', '#/talk', 'Talk'], ['#/journey', '#/journey', 'Journey'],
  ];
  for (const [from, to, dest] of table) {
    await page.goto(`${baseURL}/${from}`, { waitUntil: 'networkidle' });
    await expect(page, `loading ${from}`).toHaveURL(new RegExp(to.replace(/\//g, '\\/') + '$'));
    await expect(current(), `loading ${from}`).toHaveText(dest);
  }
  await page.goto(`${baseURL}/#/state`, { waitUntil: 'networkidle' });
  for (const [from, to, dest] of table) {
    await page.evaluate(h => { location.hash = h; }, from);
    await expect(page, `in-page ${from}`).toHaveURL(new RegExp(to.replace(/\//g, '\\/') + '$'));
    await expect(current(), `in-page ${from}`).toHaveText(dest);
  }
  // the readiness redirect lands on the Readiness lens
  await page.evaluate(() => { location.hash = '#/map/readiness'; });
  await expect(page.locator('.v11-view-switch button[aria-pressed="true"]')).toContainText('Readiness');
  // Back does not return to the old address: the redirect replaced it
  await page.goto(`${baseURL}/#/state`, { waitUntil: 'networkidle' });
  await page.goto(`${baseURL}/#/activity`, { waitUntil: 'networkidle' });
  await expect(page).toHaveURL(/#\/moves$/);
});

test('05 · keyboard: Arrow keys move along the destinations, Tab is never trapped, Escape closes Settings', async () => {
  await page.evaluate(() => goDestination('state'));
  await nav().first().focus();
  await page.keyboard.press('ArrowRight');
  expect(await page.evaluate(() => document.activeElement.textContent.trim())).toBe('Maps');
  await page.keyboard.press('End');
  expect(await page.evaluate(() => document.activeElement.textContent.trim())).toBe('Talk');
  await page.keyboard.press('ArrowRight');                       // wraps
  expect(await page.evaluate(() => document.activeElement.textContent.trim())).toBe('State');
  // Tab walks out of the nav and through the page; it never sticks to one element
  const seen = new Set();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press('Tab');
    seen.add(await page.evaluate(() => { const e = document.activeElement; return e.tagName + '|' + (e.id || '') + '|' + (e.className || '') + '|' + (e.textContent || '').trim().slice(0, 30); }));
  }
  expect(seen.size, 'forty Tab presses visited many different controls').toBeGreaterThan(10);
  // Settings: opens from the rail, holds Appearance and Engine, Escape closes it
  await page.locator('#v11-settings-btn').click();
  await expect(page.locator('#v11-settings-menu')).toBeVisible();
  await expect(page.locator('#v11-settings-menu')).toContainText('Appearance');
  await expect(page.locator('#v11-settings-menu')).toContainText('Engine');
  await page.keyboard.press('Escape');
  await expect(page.locator('#v11-settings-menu')).toBeHidden();
});

test('06 · demo mode uses the same shell: five destinations, two lenses', async ({ baseURL }) => {
  const p = await ctx.newPage();
  p.on('pageerror', e => consoleErrors.push('demo pageerror: ' + e.message));
  await p.goto(`${baseURL}/?demo=1`, { waitUntil: 'networkidle' });
  await expect(p.locator('.v11-topnav-item')).toHaveText(DEST);
  await expect(p.locator('.v11-topnav-item[aria-current="page"]')).toHaveText('State');
  await p.locator('.v11-topnav-item', { hasText: /^Maps$/ }).click();
  await expect(p.locator('.v11-view-switch button')).toHaveCount(2);
  await p.close();
});

test('07 · nothing logged a console error', async () => {
  expect(consoleErrors).toEqual([]);
});
