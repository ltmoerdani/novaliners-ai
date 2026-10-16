// Copy and slop guard for the demo (every parity scene, light and dark) plus the vocabulary the docs lock.
// Live flow: live.spec.mjs runs the same scan at every screenshot step.
import { test, expect } from '@playwright/test';
import { scenes } from './scenes.mjs';
import { scanCopy } from './copy-guard.mjs';

test.describe.configure({ mode: 'serial' });
let page, ctx;
test.beforeAll(async ({ browser, baseURL }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('dialog', d => d.dismiss());
  await page.goto(`${baseURL}/?demo=1`, { waitUntil: 'networkidle' });
  await page.evaluate(() => { const w = document.getElementById('proto-widget'); if (w) w.style.display = 'none'; });
});
test.afterAll(async () => { await ctx.close(); });

test('copy · every demo scene is clean (vocabulary, no emoji, no exclamation marks, English only)', async () => {
  const bad = {};
  for (const [name, js] of scenes) {
    if (/^(theme-reset)/.test(name)) continue;
    await page.evaluate(js);
    await page.waitForTimeout(40);
    const v = await scanCopy(page);
    if (v.length) bad[name] = v;
  }
  expect(bad).toEqual({});
});

test('copy · the Start page names the product and carries the signature (docs vocabulary lock)', async () => {
  await page.evaluate(`setTheme('light'); resetSimulation(true); renderScreen('01')`);
  await expect(page.getByText('Revenue Navigation Map', { exact: true })).toBeVisible();
  await expect(page.getByText('GO. STOP. OR DO SOMETHING ELSE.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Start my diagnosis/ })).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/AI REVENUE NAVIGATOR/i);
  expect(await page.title()).toBe('Novaliners · Revenue Navigation Map');
  expect(await page.evaluate(() => document.documentElement.lang)).toBe('en');
});

test('copy · the four path words are the only path statuses: the decision spectrum scene is not part of the product', async () => {
  await page.evaluate(`resetSimulation(true); goDestination('maps'); setMapsView('landscape')`);
  await page.waitForTimeout(200);
  const words = await page.locator('#v11-main .status-pill').allTextContents();
  for (const w of words) expect(w.trim().replace(/\s+/g, ' '), 'status word').toMatch(/^(OPEN|TEST FIRST|NOT YET|STOP)( · [A-Z ]+)?$/);
  await expect(page.locator('#v11-main')).not.toContainText(/GO SMALL|SCALE\b/);
});
