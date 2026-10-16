// Visual QA of the seven canonical frames (record D4, DoD 7; prototype doc 06 §12.9): State, Maps (Landscape, Overview,
// Readiness), Moves, Journey, Talk, each at the eight responsive viewports of doc 05.
//
//   BLOCKING   no page error or console error, no failed request, no sideways overflow of the page or #v11-main, an h1,
//              the canonical fonts loaded, and the anchors of the frame (the controls and regions a person needs are
//              present, visible and inside the viewport). A frame without a committed baseline also fails.
//   ADVISORY   pixels. A frame that differs from its baseline by more than 0.2% of its pixels (channel tolerance 12) is
//              reported as an annotation ("pixel-advisory") and does not fail: identical pages differ by 0.1 to 1.3% of
//              pixels between captures on one machine (prototype doc 06 §12.5).
//
//   npx playwright test visual.spec.mjs                       compare
//   UPDATE_VISUAL=1 npx playwright test visual.spec.mjs       write baselines to __visual__/ (review every frame first)
//   VISUAL_SCENE=state VISUAL_VIEWPORT=390x844 ...            narrow the matrix
//
// The frame review notes live in docs/07-design/v11/11-mvp-integration-record.md ("Visual review").
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

test.describe.configure({ mode: 'serial' });
test.setTimeout(120_000);

const here = path.dirname(fileURLToPath(import.meta.url));
const BASELINE = path.join(here, '__visual__');
const FONTS = path.resolve(here, '../../docs/07-design/Prototype Novaliners dengan narrative infographic/e2e/fonts');
const UPDATE = process.env.UPDATE_VISUAL === '1';
const RATIO = 0.002, CHANNEL = 12;

export const VIEWPORTS = [
  { w: 1440, h: 900 }, { w: 1280, h: 800 }, { w: 1180, h: 800 }, { w: 1024, h: 768 },
  { w: 900, h: 800 }, { w: 768, h: 1024 }, { w: 390, h: 844 }, { w: 320, h: 800 },
];
/* Put the sample story (the prototype's Dimas snapshot) on this map and align the browser-owned goal with it, so the shell and the page tell the same story. */
// every scene starts from the same record: no check-ins and the map beginning today (Day 1), so a scene never inherits another scene's journey
const SAMPLE = `V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); LIVE.goalOverride = 30; LIVE.horizonOverride = 90; LIVE.checkins = []; LIVE.startTs = Date.now(); syncStoreFromLive()`;
const TOP = [{ sel: '#v11-main h1', min: 1 }, { sel: '.v11-topnav-item', min: 5 }];
const MAPS = (lens) => `${SAMPLE}; STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; STORE.mapsView = 'landscape'; goDestination('maps'); ${lens === 'landscape' ? '' : `setMapsView('${lens}')`}`;
const LENS_ANCHORS = [
  { sel: '.mpw', min: 1 },                                   // the one workspace
  { sel: '.mpw-bar', min: 1 },                               // the section bar: icon, count, switch — above the stage, never inside it
  { sel: '#mpw-stage', min: 1 },                             // the only part a lens change may swap
  { sel: '.mpw-bar .v11-view-switch button', min: 2 },
  { sel: '.mpw-bar .v11-lens-name[data-label]', min: 2 },    // the reserved semibold width needs data-label
  { sel: '.v11-view-switch button', min: 2 },
  { sel: '#v12-map', min: 1 },
  { sel: '#mp-panel', min: 1 },
];
// Readiness on BOTH pages at this prototype commit shows the requirements list, not the map canvas, so the
// canvas anchor is scoped to the map lenses; it returns with the Maps phase (deferred: newer Maps work on main).
const LENS_READINESS_FRAME = LENS_ANCHORS.filter(a => a.sel !== '#v12-map');
/* the parts only Explore carries: the key under the map (inside the frame, never back in a card) */
const LENS_EXPLORE = [{ sel: '.mpw .mpr-key', min: 1 }, { sel: '.mpw-panel .mp-actions, .mpw.is-collapsed .mpw .v11-pagehead-actions', min: 0 }];
/* the parts only Readiness carries: "Requirements by state" is always open, and the evidence is a fold */
const LENS_READINESS = [{ sel: '.rd-reqs-open', min: 1 }, { sel: '.rd-reqs-open .rd-group', min: 1 }, { sel: '.rd-evidence', min: 1 }];
const SCENES = [
  { name: 'state', prep: `${SAMPLE}; goDestination('state')`, anchors: [{ sel: '.btn-primary', min: 1 }, { sel: '.dest-numbers', min: 1 }, { sel: '.dest-paths', min: 1 }] },
  { name: 'maps-landscape', prep: MAPS('landscape'), anchors: [...LENS_ANCHORS, ...LENS_EXPLORE] },
  // 'overview' is the OLD lens name: since UX v11 it resolves to Explore (G-34), so this frame equals maps-landscape
  { name: 'maps-overview', prep: MAPS('overview'), anchors: [...LENS_ANCHORS, ...LENS_EXPLORE, { sel: '.mp-card', min: 5 }] },
  { name: 'maps-readiness', prep: MAPS('readiness'), anchors: [...LENS_READINESS_FRAME, { sel: '.rd-path-item', min: 5 }, { sel: '#rd-detail', min: 1 }, ...LENS_READINESS] },
  { name: 'moves', prep: `${SAMPLE}; STORE.viewStep = 0; goDestination('moves')`, anchors: [{ sel: '.today-actions .btn-primary', min: 1 }, { sel: '.moves-queues', min: 1 }, { sel: '.mv-featured', min: 1 }, { sel: '#mv-side', min: 1 }] },
  { name: 'journey', prep: `${SAMPLE}; LIVE.startTs = Date.now() - 24 * 864e5; LIVE.checkins = [
      { cycle: 1, day: 7, rp: 2, outcome: 'worked', contacted: 5, replies: 3, calls: 2, paid: 2, path: 'advise-network', title: 'Paid result · Rp2M', note: 'x' },
      { cycle: 2, day: 14, rp: 4, outcome: 'mixed', contacted: 6, replies: 2, calls: 1, paid: 0, path: 'advise-network', title: 'Interested, but no one paid yet', note: 'x' },
      { cycle: 3, day: 21, rp: 7, outcome: 'worked', contacted: 8, replies: 4, calls: 2, paid: 3, path: 'productized-audit', title: 'Paid result · Rp3M', note: 'x' }];
      syncStoreFromLive(); goDestination('journey')`, anchors: [{ sel: '.j-statcard', min: 4 }, { sel: '.j-chartcard', min: 1 }] },
  { name: 'talk', prep: `${SAMPLE}; STORE.talkAbout = null; STORE.chatEvidenceOpen = true; STORE.chatPanelTab = 'map'; LIVE.askSid = LIVE.sid; LIVE.askThinking = false; LIVE.askThread = [
      { role: 'user', text: 'Why is this what is holding me back?' },
      { role: 'bot', text: 'What we see: people do not know exactly what they can buy from you. You have 8 years of experience, but the service is not written down on one page yet.', next: ['What should I not do yet?'] }];
      goDestination('talk')`, anchors: [{ sel: '#talk-ongoing-input', min: 1 }, { sel: '.talk-send', min: 1 }, { sel: '#chat-messages-container', min: 1 }] },
];
const only = process.env.VISUAL_SCENE, onlyVp = process.env.VISUAL_VIEWPORT;

let ctx, page;
const diag = { pageErrors: [], consoleErrors: [], failed: [] };

async function fonts(p) {
  const css = fs.readFileSync(path.join(FONTS, 'fonts.css'), 'utf8');
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ status: 200, contentType: 'text/css; charset=utf-8', body: css }));
  await p.route('https://fonts.gstatic.com/**', r => {
    const f = path.join(FONTS, decodeURIComponent(r.request().url().split('/').pop()));
    return fs.existsSync(f) ? r.fulfill({ status: 200, contentType: 'font/woff2', path: f }) : r.abort();
  });
}

test.beforeAll(async ({ browser, baseURL }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce', colorScheme: 'light', deviceScaleFactor: 1 });
  page = await ctx.newPage();
  await fonts(page);
  page.on('pageerror', e => diag.pageErrors.push(String(e.message)));
  page.on('console', m => { if (m.type() === 'error' && !/favicon/i.test(m.text())) diag.consoleErrors.push(m.text()); });
  page.on('requestfailed', r => { if (r.url().startsWith(baseURL)) diag.failed.push(r.url()); });
  page.on('dialog', d => d.accept());
  await page.addInitScript(() => { try { localStorage.setItem('novaliners-v9', JSON.stringify({ userId: 'u_e2evis' + Math.random().toString(16).slice(2, 8), chain: [], checkins: [], overrides: [], tips: {} })); localStorage.setItem('novaliners-theme', 'light'); } catch (e) { /* ignore */ } });
  // one real (mock-LLM) map: every frame is rendered from it, with the snapshot or the store set by the scene
  await page.goto(`${baseURL}/`, { waitUntil: 'networkidle' });
  await page.fill('#start-textarea', 'I left my job as a marketing manager and want Rp20 million a month from consulting in 90 days.');
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await page.locator('#diag-chat-input:not([disabled])').waitFor({ timeout: 30_000 });
  for (let i = 1; i <= 2; i++) {
    await page.fill('#diag-chat-input', `Answer ${i}: nobody has paid me yet, and two people asked me to let them know.`);
    await page.keyboard.press('Enter');
    await page.locator('#diag-chat-input:not([disabled])').waitFor({ timeout: 30_000 });
  }
  await page.getByText('Enough answers? Build my diagnosis now').click();
  await page.getByRole('heading', { name: /best read so far/ }).waitFor({ timeout: 60_000 });
});
test.afterAll(async () => { await ctx.close(); });

const settle = async () => {
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    // document.fonts.ready resolves once the faces in use are done; a later check() can still see a canonical
    // face as "not loaded" when its descriptor pair has not been requested yet (classic sequence-dependent
    // flake). Requesting the three canonical faces explicitly makes the check below deterministic without
    // weakening it: a face that really failed to load still stays unloaded.
    await Promise.all(['12px "Plus Jakarta Sans"', '12px "Source Sans 3"', '12px "Newsreader"']
      .map(f => document.fonts.load(f).catch(() => {})));
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  });
  await page.waitForTimeout(150);
};
function anchorProblems(list) {
  const problems = [];
  for (const a of list) {
    const vis = [...document.querySelectorAll(a.sel)].filter(e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; });
    if (vis.length < a.min) problems.push(`anchor ${a.sel}: ${vis.length} visible, need ${a.min}`);
    const out = vis.filter(e => { const r = e.getBoundingClientRect(); return r.left < -1 || r.right > innerWidth + 1; });
    if (out.length) problems.push(`anchor ${a.sel}: ${out.length} outside the viewport horizontally`);
  }
  return problems;
}
function layoutProblems() {
  const problems = [], de = document.documentElement, main = document.getElementById('v11-main');
  if (de.scrollWidth - de.clientWidth > 2) problems.push(`document overflow ${de.scrollWidth - de.clientWidth}px`);
  if (main && main.scrollWidth - main.clientWidth > 2) problems.push(`#v11-main overflow ${main.scrollWidth - main.clientWidth}px`);
  const bad = [];
  if (main) for (const el of main.querySelectorAll('*')) {
    const r = el.getBoundingClientRect(); if (!r.width && !r.height) continue;
    const cs = getComputedStyle(el); if (cs.position === 'fixed' || cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (r.right > innerWidth + 1.5) {
      let by = null;
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { if (p.ownerSVGElement || p.tagName.toLowerCase() === 'svg') continue; const ox = getComputedStyle(p).overflowX; if (ox === 'auto' || ox === 'scroll') { by = 'scroller'; break; } if (ox === 'hidden' || ox === 'clip') { by = 'clipped'; break; } }
      if (by !== 'scroller') bad.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className).trim().split(/\s+/).join('.'));
    }
  }
  if (bad.length) problems.push(`elements past the viewport (${bad.length}): ${bad.slice(0, 6).join(' | ')}`);
  if (!document.querySelectorAll('h1').length) problems.push('no h1');
  for (const f of ['Plus Jakarta Sans', 'Source Sans 3', 'Newsreader']) if (!document.fonts.check(`12px "${f}"`)) problems.push(`font not loaded: ${f}`);
  return problems;
}

for (const vp of VIEWPORTS) {
  for (const scene of SCENES) {
    if ((only && scene.name !== only) || (onlyVp && onlyVp !== `${vp.w}x${vp.h}`)) continue;
    const tag = `${vp.w}x${vp.h}-${scene.name}`;
    test(`frame · ${tag}`, async () => {
      diag.pageErrors.length = diag.consoleErrors.length = diag.failed.length = 0;
      await page.setViewportSize({ width: vp.w, height: vp.h });
      await page.evaluate(scene.prep);
      await settle();
      const problems = [...await page.evaluate(anchorProblems, [...TOP, ...scene.anchors]), ...await page.evaluate(layoutProblems)];
      problems.push(...diag.pageErrors.map(e => `pageerror: ${e}`), ...diag.consoleErrors.map(e => `console: ${e}`), ...diag.failed.map(e => `request failed: ${e}`));
      const buf = await page.screenshot({ animations: 'disabled', caret: 'hide', style: '.app-toast{display:none!important} #engine-settings{visibility:hidden}' });
      const file = path.join(BASELINE, `${tag}.png`);
      if (UPDATE) { fs.mkdirSync(BASELINE, { recursive: true }); fs.writeFileSync(file, buf); }
      else if (!fs.existsSync(file)) problems.push('no committed baseline for this frame');
      else {
        const a = PNG.sync.read(fs.readFileSync(file)), b = PNG.sync.read(buf);
        if (a.width !== b.width || a.height !== b.height) problems.push(`size changed: baseline ${a.width}x${a.height}, now ${b.width}x${b.height}`);
        else {
          const diff = pixelmatch(a.data, b.data, null, a.width, a.height, { threshold: CHANNEL / 255, includeAA: false });
          const ratio = diff / (a.width * a.height);
          if (ratio > RATIO) test.info().annotations.push({ type: 'pixel-advisory', description: `${tag}: ${(ratio * 100).toFixed(3)}% of pixels differ (advisory above ${(RATIO * 100).toFixed(1)}%)` });
        }
      }
      expect(problems, tag).toEqual([]);
    });
  }
}
