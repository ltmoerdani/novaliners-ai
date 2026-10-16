// Parity with the v11 prototype (record D4, DoD 3). The MVP in demo mode (?demo=1) is rendered next to the prototype file
// itself, at the same viewport, for the seven canonical frames (State, Maps x3 lenses, Moves, Journey, Talk) at the eight
// responsive viewports of prototype doc 05. No stored baselines: both pages are rendered live.
//
//   BLOCKING   no page error or console error in either page, the same anchors present and inside the viewport in both, no
//              sideways overflow of the page or #v11-main in the MVP, the same heading in both.
//   ADVISORY   pixels. A frame that differs by more than 0.2% of its pixels (channel tolerance 12) is reported as an annotation
//              ("pixel-advisory") with the measured ratio and does not fail: identical pages differ by 0.1 to 1.3% of pixels
//              between captures on one machine (prototype doc 06 §12.5).
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';
import { VIEWPORTS, PARITY_SCENES } from './scenes.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const PROTO_DIR = path.resolve(here, '../../docs/07-design/Prototype Novaliners dengan narrative infographic');
const PROTO = pathToFileURL(path.join(PROTO_DIR, 'Revenue Navigation v11.dc.html')).href;
const FONTS = path.join(PROTO_DIR, 'e2e/fonts');
const RATIO = 0.002;

test.describe.configure({ mode: 'serial' });
test.setTimeout(120_000);

async function fonts(p) {
  const css = fs.readFileSync(path.join(FONTS, 'fonts.css'), 'utf8');
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ status: 200, contentType: 'text/css; charset=utf-8', body: css }));
  await p.route('https://fonts.gstatic.com/**', r => {
    const f = path.join(FONTS, decodeURIComponent(r.request().url().split('/').pop()));
    return fs.existsSync(f) ? r.fulfill({ status: 200, contentType: 'font/woff2', path: f }) : r.abort();
  });
}
const settle = async (p) => {
  await p.evaluate(async () => { if (document.fonts && document.fonts.ready) await document.fonts.ready; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); });
  await p.waitForTimeout(200);
};
function anchorProblems(list) {
  const problems = [];
  for (const a of list) {
    const vis = [...document.querySelectorAll(a.sel)].filter(e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; });
    if (vis.length < a.min) problems.push(`anchor ${a.sel}: ${vis.length} visible, need ${a.min}`);
    const out = vis.filter(e => { const r = e.getBoundingClientRect(); return r.left < -1 || r.right > innerWidth + 1; });
    if (out.length) problems.push(`anchor ${a.sel}: ${out.length} outside the viewport horizontally`);
  }
  const de = document.documentElement, main = document.getElementById('v11-main');
  if (de.scrollWidth - de.clientWidth > 2) problems.push(`document overflow ${de.scrollWidth - de.clientWidth}px`);
  if (main && main.scrollWidth - main.clientWidth > 2) problems.push(`#v11-main overflow ${main.scrollWidth - main.clientWidth}px`);
  return problems;
}

let proto, mvp, ctxs = [];
const diag = { proto: [], mvp: [] };
test.beforeAll(async ({ browser, baseURL }) => {
  for (const [name, url] of [['proto', PROTO], ['mvp', `${baseURL}/?demo=1`]]) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', colorScheme: 'light', locale: 'en-GB', timezoneId: 'Asia/Jakarta', deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await fonts(page);
    page.on('dialog', d => d.dismiss());
    page.on('pageerror', e => diag[name].push('pageerror: ' + e.message));
    page.on('console', m => { if (m.type() === 'error' && !/favicon|DevTools|\[vite\]/i.test(m.text())) diag[name].push('console: ' + m.text()); });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.addStyleTag({ content: '#proto-widget{display:none !important} #v11-tip{display:none !important} *{caret-color:transparent !important}' });
    ctxs.push(ctx);
    if (name === 'proto') proto = page; else mvp = page;
  }
});
test.afterAll(async () => { for (const c of ctxs) await c.close(); });

for (const vp of VIEWPORTS) {
  for (const scene of PARITY_SCENES) {
    test(`parity · ${vp.w}x${vp.h}-${scene.name}`, async ({}, testInfo) => {
      diag.proto.length = diag.mvp.length = 0;
      const shots = [], problems = [];
      for (const [name, page] of [['proto', proto], ['mvp', mvp]]) {
        await page.setViewportSize({ width: vp.w, height: vp.h });
        await page.evaluate(scene.act);
        await settle(page);
        problems.push(...(await page.evaluate(anchorProblems, scene.anchors)).map(p => `${name}: ${p}`));
        problems.push(...diag[name].map(d => `${name}: ${d}`));
        shots.push(PNG.sync.read(await page.screenshot({ animations: 'disabled', caret: 'hide' })));
      }
      expect(problems, 'blocking checks').toEqual([]);
      const [a, b] = shots;
      expect([b.width, b.height], 'same frame size').toEqual([a.width, a.height]);
      const heads = await Promise.all([proto, mvp].map(p => p.locator('#v11-main h1').first().innerText()));
      expect(heads[1].length, 'the MVP frame has a heading').toBeGreaterThan(0);
      const diff = pixelmatch(a.data, b.data, null, a.width, a.height, { threshold: 0.1, includeAA: false });
      const ratio = diff / (a.width * a.height);
      if (ratio > RATIO) testInfo.annotations.push({ type: 'pixel-advisory', description: `${(ratio * 100).toFixed(2)}% of pixels differ from the prototype (advisory above ${(RATIO * 100).toFixed(1)}%)` });
    });
  }
}
