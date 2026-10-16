import { chromium } from '@playwright/test';
const ctx = await chromium.launch().then(b => b.newContext());
const page = await ctx.newPage();
page.on('pageerror', e => console.log('PAGE ERROR:', e.message.slice(0, 400)));
page.on('console', m => { if (m.type() === 'error') console.log('CONSOLE:', m.text().slice(0, 300)); });
page.on('requestfailed', r => console.log('REQFAIL:', r.url()));
await page.goto('http://127.0.0.1:8765/', { waitUntil: 'load' });
await page.waitForTimeout(2500);
console.log(await page.evaluate(() => ({
  renderScreen: typeof renderScreen,
  renderPathMap: typeof renderPathMap,
  screen07Live: typeof screen07Live,
  scripts: [...document.scripts].map(s => (s.src || 'inline').split('/').pop()).filter(Boolean)
})));
await ctx.close();
