// MAPS Landscape label readability (2D and 3D, desktop 1440x900 and phone 390x844).
// The labels on the map must not run into each other, into the 2D/3D toggle or out of the canvas, every path must stay
// reachable on the map, what the canvas cannot write out must stay readable somewhere, and the same fixture must lay out
// the same way every time. This reads the geometry of the real, rendered labels; the screenshots in
// e2e/__visual__/maps-labels/ are then looked at by eye (a geometry check says nothing about whether text is legible).
//
// Scenarios: the sample map (5 paths, nodes and a stop), 1 / 3 / 5 / 10 engine paths, 8 paths, paths born from mechanisms
// with hypothesis labels, and five paths with deliberately long titles and requirement labels.
import { test, expect } from '@playwright/test';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

test.describe.configure({ mode: 'serial', timeout: 240_000 });

const here = path.dirname(fileURLToPath(import.meta.url));
const VISUAL = path.join(here, '__visual__', 'maps-labels');
fs.mkdirSync(VISUAL, { recursive: true });
const PORT = 'http://127.0.0.1:' + (process.env.E2E_PORT || 8765);
const UID = 'u_e2e_ml_' + Math.random().toString(16).slice(2, 8);
const fx = name => JSON.parse(fs.readFileSync(path.join(here, 'fixtures', `${name}.json`), 'utf8'));

let page, ctx;
const consoleErrors = [];
const hashes = {};

const LONG = i => ({ id: 'p' + i, title: 'Path number ' + i + ' with a deliberately long title that must not break the layout',
  status_display: ['OPEN', 'NOT YET', 'TEST FIRST', 'STOP', 'OPEN'][i - 1], lifecycle: 'OPEN', stop_source: null,
  requirements: [{ id: 'r1', label: 'Requirement one of path ' + i + ' with a long label that needs room', satisfaction: 'UNKNOWN' }],
  evidence_ids: [], provenance: '', trail: [], next_move: null });

const SCENARIOS = {
  'sample-5': { kind: 'snap', run: () => { V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); }, n: 5 },
  'long-5': { kind: 'snap', n: 5, run: (mk) => { const s = JSON.parse(JSON.stringify(V11_ENGINE.snapshot())); s.paths = [1, 2, 3, 4, 5].map(i => Object.assign({}, mk(i))); V11_ENGINE.set(v11MapKey(), s); } },
  'engine-1': { kind: 'fx', fixture: 'paths_one', n: 1 },
  'engine-3': { kind: 'fx', fixture: 'paths_three', n: 3 },
  'engine-5': { kind: 'fx', fixture: 'paths_five', n: 5 },
  'engine-8': { kind: 'fx', fixture: 'paths_eight', n: 8 },
  'engine-10': { kind: 'fx', fixture: 'paths_ten', n: 10 },
  'candidates-hypothesis': { kind: 'fx', fixture: 'paths_candidates_many', n: null }
};
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };

async function apply(name) {
  const sc = SCENARIOS[name];
  await page.setViewportSize(VIEWPORTS.desktop);
  if (sc.kind === 'snap') {
    await page.evaluate(([src, mkSrc]) => { const mk = eval('(' + mkSrc + ')'); eval('(' + src + ')')(mk); }, [sc.run.toString(), LONG.toString()]);
  } else {
    await page.evaluate(f => {
      V11_ENGINE.clear();
      LIVE.artifact.possible_paths = f.possible_paths; LIVE.artifact.navigation = f.navigation; LIVE.projection = f.projection || null;
      LIVE.projectionTried = LIVE.sid; LIVE.explain = null; LIVE.explainState = 'failed';
      LIVE.workspace = LIVE.workspace || {}; LIVE.workspace.path_states = f.path_states || {};
      if (f.routes) LIVE.routes = f.routes;
    }, fx(sc.fixture));
  }
}
async function show(mode, vp) {
  await page.setViewportSize(VIEWPORTS[vp]);
  await page.evaluate(m => { STORE.mapMode = m; STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; STORE.mapsView = 'landscape'; goDestination('maps'); }, mode);
  await page.waitForFunction(m => { const h = document.getElementById('v12-map'); return h && h.dataset.mode === m && h.querySelector('.v12-stage'); }, mode, { timeout: 10_000 });
  await page.waitForTimeout(350);
}

/* geometry of every label the canvas carries, in page coordinates, rounded: stable between renders */
const geometry = () => page.evaluate(() => {
  const host = document.getElementById('v12-map');
  /* the card is the boundary now: the zoom bar and the "+N more" button are flow rows of the same card
     (phase-1 port, 18 Oct) — measuring the stage alone would flag the card's own chrome as clipped */
  const stage = host.getBoundingClientRect();
  const els = [...host.querySelectorAll('.v12-lane-label, .v12-marker, .v12-more, svg text')];
  const boxes = els.map(el => {
    const r = el.getBoundingClientRect();
    return { el, cls: (el.getAttribute('class') || el.tagName).slice(0, 24), t: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40), x0: r.left, y0: r.top, x1: r.right, y1: r.bottom };
  }).filter(b => b.x1 - b.x0 > 2 && b.y1 - b.y0 > 2 && b.t);
  const leaf = boxes.filter(a => !boxes.some(o => o !== a && o.el.contains(a.el)));
  const overlaps = [];
  for (let i = 0; i < leaf.length; i++) for (let j = i + 1; j < leaf.length; j++) {
    const a = leaf[i], c = leaf[j], w = Math.min(a.x1, c.x1) - Math.max(a.x0, c.x0), h = Math.min(a.y1, c.y1) - Math.max(a.y0, c.y0);
    if (w > 1.5 && h > 1.5) overlaps.push(`${a.t} [${a.cls}]  x  ${c.t} [${c.cls}]  ${Math.round(w)}x${Math.round(h)}`);
  }
  const vw = document.documentElement.clientWidth;
  const clipped = leaf.filter(b => b.x0 < stage.left - 1 || b.x1 > stage.right + 1 || b.y0 < stage.top - 1 || b.y1 > stage.bottom + 1 || b.x0 < -1 || b.x1 > vw + 1)
    .map(b => `${b.t} [${b.cls}]`);
  const shape = leaf.map(b => [b.cls, b.t, Math.round(b.x0), Math.round(b.y0), Math.round(b.x1), Math.round(b.y1)].join('|')).sort();
  return { n: leaf.length, overlaps, clipped, shape, overflow: document.documentElement.scrollWidth - vw };
});

const shot = async (name) => {
  await page.mouse.move(2, 2);
  const buf = await page.locator('#v12-map').screenshot({ path: path.join(VISUAL, name + '.png') });
  hashes[name] = crypto.createHash('sha1').update(buf).digest('hex');
};

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: VIEWPORTS.desktop, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  /* KNOWN NEGATIVE PROBE (D-02): GET /checkins on a session with no check-in history answers 404 and
     the client treats it as an empty history — the browser logs it, but it is not a defect. The server
     should answer 200 {checkins: []} for "none yet" (follow-up). Any other console error still fails. */
  page.on('console', m => {
    if (m.type() !== 'error') return;
    if (/Failed to load resource.*404/.test(m.text()) && !/\/(experience|diagnosis|explain)/.test(m.location()?.url || '')) return;
    consoleErrors.push('console: ' + m.text());
  });
  await page.goto('/', { waitUntil: 'networkidle' });
  const post = (p, data) => page.request.post(PORT + p, { data });
  const sid = (await (await post('/session', { user_id: UID, goal_text: 'I want Rp20 million a month from consulting in 90 days.' })).json()).session_id;
  await post('/session/' + sid + '/message', { text: 'I left my job as a marketing manager. Nobody has paid me yet and two people asked me to let them know.' });
  expect((await post('/session/' + sid + '/finalize')).status()).toBe(200);
  await page.evaluate(([u, s]) => { localStorage.setItem('novaliners-v9', JSON.stringify({ userId: u, current: s, chain: [], checkins: [], overrides: [], tips: {} })); sessionStorage.setItem('e2e-keep-ls', '1'); }, [UID, sid]);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForFunction(x => typeof LIVE !== 'undefined' && LIVE.sid === x && !!LIVE.artifact && !!LIVE.state, sid, { timeout: 30_000 });
});
test.afterAll(async () => { await ctx.close(); });

for (const name of Object.keys(SCENARIOS)) {
  for (const mode of ['2d']) {   // one canvas: the flat map (3D removed, owner 18 Oct; doc 15 GAP-05)
    test(`ML · ${name} · ${mode}: no label meets another, the toggle or the canvas edge, on desktop and on a phone; every drawn path is reachable; same fixture, same layout`, async () => {
      await apply(name);
      for (const vp of ['desktop', 'mobile']) {
        await show(mode, vp);
        const g = await geometry();
        const tag = `${name} ${mode} ${vp}`;
        expect(g.n, tag + ': there are labels to check').toBeGreaterThan(2);
        expect(g.overlaps, tag + ': labels overlapping').toEqual([]);
        expect(g.clipped, tag + ': labels outside the canvas or the screen').toEqual([]);
        expect(g.overflow, tag + ': no horizontal page overflow').toBeLessThanOrEqual(1);
        // every path drawn is a named, pressable thing on the map (never silently dropped)
        const drawn = await page.locator('.v12-lane-label').count();
        const total = await page.evaluate(() => V11_ENGINE.snapshot().paths.length);
        expect(drawn, tag + ': drawn paths = min(paths, 5)').toBe(Math.min(total, 5));
        for (const el of await page.locator('.v12-lane-label').all()) {
          expect((await el.getAttribute('aria-label')) || (await el.innerText()), tag + ': the full title stays available').toMatch(/\w{3}/);
        }
        // deterministic: a second render of the same fixture gives the same boxes
        await show(mode, vp);
        expect((await geometry()).shape, tag + ': stable between renders').toEqual(g.shape);
        await shot(`${name}-${mode}-${vp}`);
      }
      await page.setViewportSize(VIEWPORTS.desktop);
    });
  }
}

test('ML · what the canvas shortens is still readable: the long title and its requirement are in the page once the path is chosen', async () => {
  await apply('long-5');
  await show('2d', 'mobile');
  const first = page.locator('.v12-lane-label').first();
  const id = await first.getAttribute('data-v12-path');
  await first.click();
  await expect(page.locator(`.v12-lane-label[data-v12-path="${id}"]`)).toHaveAttribute('aria-pressed', 'true');
  const main = await page.locator('#v11-main').innerText();
  expect(main, 'full title in the page').toContain('with a deliberately long title that must not break the layout');
  expect(main, 'requirement of the chosen path in the page').toContain('Requirement one of path');
  // on a phone the other paths name themselves (title attribute of the marker) and keep a lane label with the status
  const lane = page.locator('.v12-lane-label').first();
  expect(await lane.getAttribute('aria-label')).toMatch(/Path number \d with a deliberately long title that must not break the layout · (OPEN|NOT YET|TEST FIRST|STOP)/);
  const laneText = await lane.evaluate(el => el.textContent);
  expect(laneText, 'a long title gives way, the status word never does').toMatch(/(OPEN|NOT YET|TEST FIRST|STOP)/);
  await page.setViewportSize(VIEWPORTS.desktop);
});

test('ML · selecting a path keeps it distinguishable and moves nothing off the map', async () => {
  await apply('sample-5');
  {
    await show('2d', 'desktop');
    const first = page.locator('.v12-lane-label').nth(1);
    await first.click();
    await expect(first).toHaveAttribute('aria-pressed', 'true');
    expect(await page.locator('.v12-lane-label[aria-pressed="true"]').count(), 'exactly one selected').toBe(1);
    expect(await page.locator('.v12-lane-label.is-dim').count(), 'the others step back').toBeGreaterThan(0);
    const g = await geometry();
    expect(g.overlaps, 'after selecting').toEqual([]);
    expect(g.clipped, 'after selecting').toEqual([]);
    await shot('sample-5-2d-desktop-selected');
  }
});

test('ML · nothing logged a console error', async () => {
  expect(consoleErrors, consoleErrors.join('\n')).toEqual([]);
  fs.writeFileSync(path.join(VISUAL, 'hashes.json'), JSON.stringify(hashes, null, 1));
});
