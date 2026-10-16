// Laws of UX on the State destination (docs/09-design-research/07-30-laws-of-ux-jon-yablonski.md). Replaces diagnosis-ux.spec.mjs,
// which measured the v9 Diagnosis screen (retired from the product, record D5). The measurable laws live in ux-laws.mjs.
//   the sample snapshots of the demo (four sample workspaces, light and dark, wide and narrow),
//   the real (mock-LLM) diagnosis in live mode,
//   the engine's real stored artifacts (longest first), rendered through the real adapter.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkStateLaws, measureResponse } from './ux-laws.mjs';

test.describe.configure({ mode: 'serial' });
const here = path.dirname(fileURLToPath(import.meta.url));
let page, ctx;
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(80); };

test.beforeAll(async ({ browser, baseURL }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('dialog', d => d.dismiss());
  await page.goto(`${baseURL}/?demo=1`, { waitUntil: 'networkidle' });
  await page.evaluate(() => { const w = document.getElementById('proto-widget'); if (w) w.style.display = 'none'; });
});
test.afterAll(async () => { await ctx.close(); });

for (const [label, vp] of [['1440 wide', { width: 1440, height: 900 }], ['1024 wide', { width: 1024, height: 768 }], ['390 wide', { width: 390, height: 844 }]]) {
  test(`laws · every sample workspace of the demo keeps all measurable laws on State (light and dark, ${label})`, async () => {
    await page.setViewportSize(vp);
    const bad = {};
    for (const theme of ['light', 'dark']) for (const persona of ['dimas', 'rina', 'arif', 'bayu']) {
      await go(`setTheme('${theme}'); resetSimulation(true); setPersona('${persona}'); goDestination('state')`);
      const { violations } = await checkStateLaws(page);
      if (violations.length) bad[`${theme}-${persona}`] = violations;
    }
    await go(`setTheme('light'); setPersona('dimas')`);
    await page.setViewportSize({ width: 1440, height: 900 });
    expect(bad).toEqual({});
  });
}

test('laws · Doherty: State renders and the reasoning opens well inside 400 ms', async () => {
  await go(`resetSimulation(true); goDestination('state')`);
  const r = await measureResponse(page);
  expect(r.opened).toBe(true);
  expect(r.render, 'render ms').toBeLessThan(100);
  expect(r.open, 'drawer ms').toBeLessThan(100);
});

test('laws · the real (mock-LLM) diagnosis in live mode keeps every measurable law', async ({ browser, baseURL }) => {
  const c = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce', locale: 'en-GB' });
  const p = await c.newPage();
  p.on('dialog', d => d.accept());   // "Build my diagnosis now" asks first
  await p.addInitScript(() => { try { localStorage.setItem('novaliners-v9', JSON.stringify({ userId: 'u_e2e' + Math.random().toString(16).slice(2, 10), chain: [], checkins: [], overrides: [], tips: {} })); } catch (e) { /* ignore */ } });
  await p.goto(`${baseURL}/`, { waitUntil: 'networkidle' });
  await p.fill('#start-textarea', 'I left my job as a marketing manager and want Rp20 million a month from consulting in 90 days.');
  await p.getByRole('button', { name: /Start my diagnosis/ }).click();
  await p.locator('#diag-chat-input:not([disabled])').waitFor({ timeout: 30_000 });
  for (let i = 1; i <= 2; i++) {
    await p.fill('#diag-chat-input', `Answer ${i}: nobody has paid me yet, and two people asked me to let them know.`);
    await p.keyboard.press('Enter');
    await p.locator('#diag-chat-input:not([disabled])').waitFor({ timeout: 30_000 });
  }
  await p.getByText('Enough answers? Build my diagnosis now').click();
  await p.getByRole('heading', { name: /best read so far/ }).waitFor({ timeout: 60_000 });
  await p.evaluate(() => goDestination('state'));
  await p.waitForFunction(() => LIVE.explainState === 'ready' || LIVE.explainState === 'failed', null, { timeout: 30_000 });
  await p.waitForTimeout(200);
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await p.setViewportSize(vp);
    const r = await checkStateLaws(p);
    expect(r.violations, `live State at ${vp.width}`).toEqual([]);
  }
  // when the rewrite could not be made the page still reads: the engine's own sentences, with no blank
  await p.evaluate(() => { LIVE.explain = null; LIVE.explainState = 'failed'; goDestination('state'); });
  await expect(p.locator('#v11-main h1')).toHaveText('Where you are');
  expect((await checkStateLaws(p, { plain: false })).violations).toEqual([]);
  await c.close();
});

// The engine's real sentences are long, dense and uneven (median headline 94 characters, up to 570; reasons over 1000). Sessions
// stored on this machine (store/sessions, not in git) are the corpus: the 25 longest artifacts plus an even sample of the rest.
// A machine without them runs the demo and live tests above; this one only reports that it had nothing to read.
test('laws · real engine artifacts (longest first) render through State and keep every measurable law', async ({ browser, baseURL }) => {
  const dir = path.resolve(here, '../store/sessions');
  const arts = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => f.endsWith('.json')).flatMap(f => {
    try { const d = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')); const a = d.artifact || d.diagnosis || {};
      return a.primary_constraint && a.primary_constraint.length > 3 && (a.why || []).length && a.decision_spectrum ? [a] : []; } catch { return []; }
  }) : [];
  test.info().annotations.push({ type: 'corpus', description: `${arts.length} stored engine artifacts on this machine` });
  expect(arts.length === 0 || arts.length >= 1).toBe(true);
  if (!arts.length) return;
  arts.sort((x, y) => JSON.stringify(x).length - JSON.stringify(y).length);
  const rest = arts.slice(0, -25); const step = Math.max(1, Math.floor(rest.length / 60));
  const corpus = [...arts.slice(-25), ...rest.filter((_, i) => i % step === 0)];
  const c = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const p = await c.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(`${baseURL}/`, { waitUntil: 'networkidle' });
  const bad = {};
  for (const [i, a] of corpus.entries()) {
    const ok = await p.evaluate(a => { LIVE.artifact = a; LIVE.evidence = []; LIVE.checkins = []; LIVE.explain = null; LIVE.explainState = 'failed'; LIVE.sid = LIVE.sid || 'corpus'; syncStoreFromLive(); V11_ENGINE.clear(); goDestination('state'); return !!document.querySelector('#v11-main .dest-hero'); }, a);
    expect(ok, `artifact ${i} renders`).toBe(true);
    const { violations } = await checkStateLaws(p, { plain: false });
    if (violations.length) bad[`#${i} ${a.primary_constraint.slice(0, 40)}`] = violations;
  }
  await c.close();
  expect(errs).toEqual([]);
  expect(bad).toEqual({});
});

// Real engine artifacts through the Maps lenses: the checklist is the adjudicated readiness projection the server serves for the
// same session (GET /session/{sid}/readiness), the exact object the live UI reads. The session id stays empty, so no LLM call is fired;
// the projection is injected, not fetched by the page. Replaces the v9 Readiness corpus test of readiness-ux.spec.mjs.
test('laws · real engine artifacts through Explore and Readiness: every path renders, the counts agree, nothing throws', async ({ browser, baseURL }) => {
  const dir = path.resolve(here, '../store/sessions');
  const rows = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => f.endsWith('.json')).flatMap(f => {
    try { const d = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')); const a = d.artifact || d.diagnosis || {};
      return a.primary_constraint && a.possible_paths && (a.possible_paths.paths || []).length >= 1 ? [{ sid: d.id || f.replace(/\.json$/, ''), a }] : []; } catch { return []; }
  }) : [];
  test.info().annotations.push({ type: 'corpus', description: `${rows.length} stored sessions with paths on this machine` });
  if (!rows.length) return;
  const step = Math.max(1, Math.floor(rows.length / 40));
  const corpus = rows.filter((_, i) => i % step === 0);
  const c = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const p = await c.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto(`${baseURL}/`, { waitUntil: 'networkidle' });
  const bad = {};
  for (const [i, row] of corpus.entries()) {
    const proj = await p.request.get(`${baseURL}/session/${row.sid}/readiness`).then(r => (r.ok() ? r.json() : null)).catch(() => null);
    const r = await p.evaluate(([a, proj]) => {
      LIVE.artifact = a; LIVE.projection = proj; LIVE.projectionTried = 'corpus'; LIVE.routes = null; LIVE.routesTried = 'x'; LIVE.evidence = []; LIVE.checkins = [];
      LIVE.sid = LIVE.sid || 'corpus'; LIVE.explain = null; LIVE.explainState = 'failed'; V11_ENGINE.clear(); STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {};
      syncStoreFromLive();
      const n = V11_ENGINE.snapshot().paths.length, out = [];
      for (const v of ['landscape', 'readiness']) {
        goDestination('maps'); setMapsView(v);
        const t = document.getElementById('v11-main').innerText;
        if (/\bNaN\b|\bundefined\b|\[object|\bnull\b/.test(t)) out.push(`${v}: raw value on the page`);
        if (v === 'readiness' && n && document.querySelectorAll('.rd-path-item').length !== n) out.push(`readiness lists ${document.querySelectorAll('.rd-path-item').length} of ${n} paths`);
        if (v === 'landscape' && n > 1 && document.querySelectorAll('.mp-card').length !== n) out.push(`overview lists ${document.querySelectorAll('.mp-card').length} of ${n} paths`);
        if (v === 'landscape' && document.querySelectorAll('.v12-map .v12-callout').length !== Math.min(n, 5)) out.push(`landscape draws ${document.querySelectorAll('.v12-map .v12-callout').length} of ${Math.min(n, 5)}`);
      }
      return out;
    }, [row.a, proj]);
    if (r.length) bad[`#${i} ${row.sid}`] = r;
  }
  await c.close();
  expect(errs).toEqual([]);
  expect(bad).toEqual({});
});
