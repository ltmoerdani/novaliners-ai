import { chromium } from '@playwright/test';
const ctx = await chromium.launch().then(b => b.newContext({ viewport: { width: 1440, height: 900 } }));
const page = await ctx.newPage();
page.on('crash', () => console.log('*** PAGE CRASHED ***'));
page.on('pageerror', e => console.log('PAGE ERROR:', e.message.slice(0, 300)));
console.log('goto');
await page.goto('http://127.0.0.1:8765/', { waitUntil: 'networkidle' });
console.log('fill');
await page.fill('#start-textarea', 'I left my job as a marketing manager. I want Rp20 million a month from consulting within 90 days. I have no clients yet.');
await page.getByRole('button', { name: /Start my diagnosis/ }).click();
console.log('waiting for engine');
for (let i = 0; i < 24; i++) {
  await page.waitForTimeout(5000);
  const st = await page.evaluate(() => ({ hash: location.hash, busy: !!window.LIVE && LIVE.busy, artifact: !!(window.LIVE && LIVE.artifact), explain: window.LIVE ? LIVE.explainState : null })).catch(e => ({ err: String(e).slice(0, 120) }));
  console.log(i, JSON.stringify(st));
  if (st.artifact) break;
}
await page.evaluate(() => renderScreen('03'));
await page.waitForTimeout(1000);
console.log('URL:', page.url());
console.log('buttons:', await page.evaluate(() => [...document.querySelectorAll('button')].map(b => b.textContent.trim()).slice(0, 18)));
await ctx.close();
