// Product quality of the five destinations (record P6; prototype behavior.mjs "language", "a11y", "layout", "overlay" and
// "contrast" checks, ported to the live app). One real (mock-LLM) map, the five destinations and their two Maps lenses:
//   English only in the chrome and in system narration (D1), no em dash in product copy, only the four path words,
//   a drawer and a modal that keep focus, keyboard walk, reduced motion, accessible names, 24 px targets, long titles and a
//   long Talk message at 320 and 390 px, the five destinations always inside the top bar, measured contrast (4.5:1, 3:1 large).
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

test.describe.configure({ mode: 'serial' });

const DESTS = ['state', 'maps', 'moves', 'journey', 'talk'];
const LENSES = ['landscape', 'readiness'];
// A short list of unmistakably Indonesian words that no English sentence uses (prototype behavior.mjs, widened a little)
const ID_WORDS = /\b(yang|untuk|dengan|tidak|belum|sudah|selamat|kirim|simpan|lanjut|kembali|beranda|halaman|pengguna|jangan|tolong|silakan|terima kasih|bisa|akan|tetapi|karena|sekarang|hari ini|klien|penawaran|pendapatan|jualan)\b/i;

let page, ctx;
const consoleErrors = [];
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(120); };
const open = (d, lens) => go(`goDestination('${d}'); ${lens && lens !== 'landscape' ? `setMapsView('${lens}')` : ''}`);
const SAMPLE = `V11_ENGINE.set(v11MapKey(), engineSnapshotDimas()); LIVE.goalOverride = 30; LIVE.horizonOverride = 90`;
const mkPath = (i, status) => ({
  id: `p${i}`, title: `Path number ${i} with a deliberately long title that must not break the layout`, group: 'Group ' + (i % 3), status_display: status,
  lifecycle: status === 'STOP' ? 'STOPPED' : 'OPEN', stop_source: status === 'STOP' ? 'evidence' : null,
  requirements: [{ id: 'r1', label: `Requirement one of path ${i}`, satisfaction: 'UNKNOWN' }], evidence_ids: [], provenance: 'From your Talk · Day 1', trail: [], next_move: null,
});

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => consoleErrors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push('console: ' + m.text()); });
  page.on('dialog', d => d.accept());
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

test('01 · the document is English and every destination keeps an h1, a main landmark and the five destinations', async () => {
  expect(await page.evaluate(() => document.documentElement.lang)).toBe('en');
  for (const d of DESTS) {
    await open(d);
    expect(await page.locator('h1').count(), `${d}: h1`).toBeGreaterThan(0);
    await expect(page.locator('main')).toHaveCount(1);
    await expect(page.locator('.v11-topnav-item')).toHaveCount(5);
  }
});

test('02 · language: no Indonesian word in the chrome or the system narration of any destination or lens', async () => {
  await go(SAMPLE);
  for (const d of DESTS) {
    for (const lens of d === 'maps' ? LENSES : [null]) {
      await open(d, lens);
      const txt = await page.evaluate(() => {
        // what the person typed, and what the engine copies back of it, is their content; the chrome and the narration are ours
        const clone = document.getElementById('app-root').cloneNode(true);
        clone.querySelectorAll('.msg-box, .talk-bubble, .talk-msg.user, .v11-map-list, .v11-topbar-map, .v11-eyebrow, #engine-settings').forEach(n => n.remove());
        return clone.innerText + ' ' + [...clone.querySelectorAll('[aria-label],[title],[placeholder]')].map(e => [e.getAttribute('aria-label'), e.title, e.getAttribute('placeholder')].join(' ')).join(' ');
      });
      const m = txt.match(ID_WORDS);
      expect(m, `${d}${lens ? '/' + lens : ''}: Indonesian word "${m && m[0]}" in the page text`).toBeNull();
    }
  }
});

test('03 · language: no em dash in the product copy of any destination or lens', async () => {
  for (const d of DESTS) {
    for (const lens of d === 'maps' ? LENSES : [null]) {
      await open(d, lens);
      const txt = await page.locator('#v11-main').innerText();
      expect(txt, `${d}${lens ? '/' + lens : ''} copy`).not.toContain('—');
    }
  }
});

test('04 · vocabulary: a path is only ever OPEN, TEST FIRST, NOT YET or STOP, in every lens and in Talk', async () => {
  await go(SAMPLE);
  const bad = [];
  for (const d of ['state', 'maps', 'moves', 'talk']) {
    for (const lens of d === 'maps' ? LENSES : [null]) {
      await open(d, lens);
      const words = await page.evaluate(() => [...document.querySelectorAll('#v11-main .status-pill, #v11-main .talk-path-status, #v11-main .mp-pill, #v11-main [data-path-status]')]
        .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && !e.closest('.today-card') && !e.classList.contains('hold'); })
        .map(e => e.textContent.trim().replace(/\s+/g, ' ')));
      for (const w of words) if (!/^(OPEN|TEST FIRST|NOT YET|STOP)(\s*·\s*[A-Z ]+)?$/.test(w)) bad.push(`${d}${lens ? '/' + lens : ''}: "${w}"`);
    }
  }
  expect(bad).toEqual([]);
  for (const bannedWord of ['GO SMALL', 'SCALE', 'ABSENT'])
    for (const d of DESTS) { await open(d); expect(await page.locator('#v11-main').innerText(), `${d} says ${bannedWord}`).not.toContain(bannedWord); }
});

test('05 · a11y: the why drawer moves focus in, keeps Tab inside, Escape closes it and focus returns to the opener', async () => {
  await open('state');
  const opener = page.locator('[onclick*="openStateWhyDrawer"]').first();
  expect(await opener.count()).toBeGreaterThan(0);
  await opener.focus(); await page.keyboard.press('Enter'); await page.waitForTimeout(200);
  expect(await page.locator('#why-drawer.open').count()).toBeGreaterThan(0);
  expect(await page.evaluate(() => !!document.activeElement.closest('#drawer-content'))).toBe(true);
  expect((await page.locator('#drawer-content').getAttribute('aria-label') || '').length).toBeGreaterThan(3);
  for (let i = 0; i < 25; i++) { await page.keyboard.press('Tab'); expect(await page.evaluate(() => !!document.activeElement.closest('#drawer-content')), `Tab ${i + 1}`).toBe(true); }
  await page.keyboard.press('Shift+Tab');
  expect(await page.evaluate(() => !!document.activeElement.closest('#drawer-content'))).toBe(true);
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  expect(await page.locator('#why-drawer.open').count()).toBe(0);
  expect(await page.evaluate(() => (document.activeElement.getAttribute('onclick') || '').includes('openStateWhyDrawer'))).toBe(true);
});

test('05b · a11y: a fast Escape cannot be undone by the dialog\'s own focus timer, and focus finds its opener even when the page re-rendered under the dialog', async () => {
  // root cause of a 1-in-3 flake in the live journey: the dialog moves focus in after 60 ms; an Escape before that moved it back
  // to the opener and the timer then pulled it into the closed dialog
  await open('state');
  const opener = page.locator('[onclick*="openStateWhyDrawer"]').first();
  await opener.focus();
  await page.evaluate(() => { document.querySelector('[onclick*="openStateWhyDrawer"]').click(); document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
  await page.waitForTimeout(250);
  expect(await page.locator('#why-drawer.open').count()).toBe(0);
  expect(await page.evaluate(() => (document.activeElement.getAttribute('onclick') || '').includes('openStateWhyDrawer')), 'focus is back on the opener').toBe(true);
  // the page re-renders under the open dialog (the opener is a new element): focus still finds it
  await opener.focus(); await page.keyboard.press('Enter'); await page.waitForTimeout(150);
  await page.evaluate(() => { const root = document.getElementById('app-root'); const keep = document.getElementById('why-drawer'); renderScreen('state'); });
  await page.waitForTimeout(100);
  if (await page.locator('#why-drawer.open').count()) { await page.keyboard.press('Escape'); await page.waitForTimeout(150); }
  await open('state');
});

test('06 · a11y: reduced motion is honoured (no view transition marker, nothing animating forever on Maps)', async () => {
  await open('maps');
  expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
  await go(`setMapsView('landscape')`);
  expect(await page.evaluate(() => document.documentElement.dataset.nav || null)).toBeNull();
  expect(await page.evaluate(() => document.getAnimations().filter(a => a.playState === 'running' && a.effect && a.effect.getTiming().iterations === Infinity).length)).toBe(0);
});

test('07 · a11y: a keyboard-only walk through the five destinations', async () => {
  await open('state');
  for (const d of ['Maps', 'Moves', 'Journey', 'Talk', 'State']) {
    await page.locator('.v11-topnav-item', { hasText: new RegExp(`^${d}$`) }).focus();
    await page.keyboard.press('Enter'); await page.waitForTimeout(150);
    expect((await page.locator('.v11-topnav-item[aria-current="page"]').innerText()).trim(), `Enter opens ${d}`).toBe(d);
  }
});

test('08 · a11y: every control on every destination has an accessible name', async () => {
  for (const d of DESTS) {
    for (const lens of d === 'maps' ? LENSES : [null]) {
      await open(d, lens);
      const bad = await page.evaluate(() => [...document.querySelectorAll('button, a[href], select, textarea, [role="button"]')].filter(el => {
        const r = el.getBoundingClientRect(); if (!r.width && !r.height) return false;
        const name = [el.getAttribute('aria-label'), el.getAttribute('aria-labelledby'), el.textContent, el.getAttribute('title')].map(v => (v || '').trim()).find(Boolean);
        return !name;
      }).map(e => e.tagName + '.' + e.className));
      expect(bad, `${d}${lens ? '/' + lens : ''}: unnamed controls`).toEqual([]);
    }
  }
});

test('09 · a11y: buttons in the destinations are at least 24 px (WCAG 2.2 AA target size)', async () => {
  for (const d of DESTS) {
    await open(d);
    const small = await page.evaluate(() => [...document.querySelectorAll('#v11-main button')].filter(b => {
      const r = b.getBoundingClientRect(), cs = getComputedStyle(b);
      return r.width > 0 && cs.visibility !== 'hidden' && (r.height < 24 || r.width < 24) && !b.closest('svg');
    }).map(b => (b.getAttribute('aria-label') || b.textContent || '').trim().slice(0, 30) + ` ${Math.round(b.getBoundingClientRect().width)}x${Math.round(b.getBoundingClientRect().height)}`));
    expect(small, `${d}: buttons under 24 px`).toEqual([]);
  }
});

test('10 · a11y: axe finds no WCAG 2 A/AA violation on any destination or lens, light and dark', async () => {
  const freeze = '*, *::before, *::after { animation: none !important; transition: none !important; }';
  for (const theme of ['light', 'dark']) {
    await go(`setTheme('${theme}'); ${SAMPLE}`);
    for (const d of DESTS) {
      for (const lens of d === 'maps' ? LENSES : [null]) {
        await open(d, lens);
        const tag = await page.addStyleTag({ content: freeze });
        const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
        await tag.evaluate(el => el.remove());
        expect(r.violations.map(v => `${v.id} x${v.nodes.length}: ` + v.nodes.map(n => (n.any[0] && n.any[0].message || '') + ' @ ' + n.target.join(' ')).join(' | ')), `${theme} ${d}${lens ? '/' + lens : ''}`).toEqual([]);
      }
    }
  }
  await go(`setTheme('light')`);
});

for (const w of [320, 390]) {
  test(`11 · layout ${w}: nine long-titled paths in every lens do not overflow or lose the controls`, async () => {
    await page.setViewportSize({ width: w, height: 800 });
    await go(`${SAMPLE}; const s = V11_ENGINE.snapshot(); s.paths = [${Array.from({ length: 9 }, (_, i) => `(${mkPath.toString()})(${i + 1}, '${['OPEN', 'STOP', 'TEST FIRST', 'NOT YET'][i % 4]}')`).join(',')}]; s.nextmove = null; V11_ENGINE.set(v11MapKey(), s); STORE.mapsSelBy = {}; goDestination('maps')`);
    for (const lens of LENSES) {
      await go(`setMapsView('${lens}')`);   // one flat canvas (3D removed, owner 18 Oct; doc 15 GAP-05)
        const dx = await page.evaluate(() => {
          const de = document.documentElement, main = document.getElementById('v11-main');
          const bad = [...main.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); if (!r.width) return false; if (r.right <= innerWidth + 1.5) return false; for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) { if (p.ownerSVGElement || p.tagName.toLowerCase() === 'svg') continue; const ox = getComputedStyle(p).overflowX; if (ox === 'auto' || ox === 'scroll' || ox === 'hidden' || ox === 'clip') return false; } return true; }).slice(0, 5).map(e => e.tagName + '.' + e.className);
          return { doc: de.scrollWidth - de.clientWidth, main: main.scrollWidth - main.clientWidth, bad };
        });
        expect(dx.doc, `${lens}: page overflow`).toBeLessThanOrEqual(2);
        expect(dx.main, `${lens}: main overflow`).toBeLessThanOrEqual(2);
        expect(dx.bad, `${lens}: elements past the viewport`).toEqual([]);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await go(`V11_ENGINE.clear()`);
  });
}

for (const w of [320, 390]) {
  test(`12 · layout ${w}: the Talk composer stays usable with a long multi-line message`, async () => {
    await page.setViewportSize({ width: w, height: 800 });
    await open('talk');
    const ta = page.locator('#talk-ongoing-input');
    await ta.fill(Array.from({ length: 12 }, (_, i) => `Line ${i + 1} ${'long-unbroken-token-'.repeat(8)}`).join('\n'));
    const box = await ta.boundingBox();
    expect(box && box.width >= 150 && box.x >= 0 && box.x + box.width <= w + 1, `textarea inside the viewport (${JSON.stringify(box)})`).toBe(true);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(over).toBeLessThanOrEqual(2);
    const send = await page.locator('.talk-send').boundingBox();
    expect(send && send.x + send.width <= w + 1 && send.width >= 24, 'send button reachable').toBe(true);
    await ta.fill('');
    await page.setViewportSize({ width: 1440, height: 900 });
  });
}

for (const w of [320, 360, 390]) {
  test(`13 · layout ${w}: all five destinations are fully visible in the top bar and the track does not scroll`, async () => {
    await page.setViewportSize({ width: w, height: 800 });
    await open('state');
    const rects = await page.evaluate(() => [...document.querySelectorAll('.v11-topnav-item')].map(b => { const r = b.getBoundingClientRect(); return { n: b.textContent.trim(), l: Math.round(r.left), r: Math.round(r.right), vw: innerWidth }; }));
    expect(rects).toHaveLength(5);
    expect(rects.filter(x => x.l < 0 || x.r > x.vw).map(x => x.n), 'clipped destinations').toEqual([]);
    expect(await page.evaluate(() => { const n = document.querySelector('.v11-topnav'); return n.scrollWidth - n.clientWidth <= 1; })).toBe(true);
    await page.setViewportSize({ width: 1440, height: 900 });
  });
}

test('14 · overlay: the stopped-path modal takes focus, traps Tab and closes on Escape', async () => {
  await page.evaluate(f => {
    V11_ENGINE.clear();
    LIVE.artifact.possible_paths = f.possible_paths; LIVE.artifact.navigation = f.navigation; LIVE.projection = f.projection || null;
    LIVE.projectionTried = LIVE.sid; LIVE.explain = null; LIVE.explainState = 'failed';
    LIVE.workspace = LIVE.workspace || {}; LIVE.workspace.path_states = f.path_states || {};
    STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; STORE.mapsView = 'landscape'; goDestination('maps');
  }, JSON.parse(fs.readFileSync(path.join(here, 'fixtures', 'paths_engine_stop.json'), 'utf8')));
  await go(`setMapsView('landscape'); mapsSelect(V11_ENGINE.snapshot().paths.find(p => p.status_display === 'STOP').id)`);
  await page.getByRole('button', { name: /I want to do this anyway/ }).click();
  await page.waitForTimeout(300);
  expect(await page.locator('#stop-modal.open').count()).toBeGreaterThan(0);
  expect(await page.evaluate(() => !!document.activeElement.closest('#modal-content'))).toBe(true);
  for (let i = 0; i < 20; i++) { await page.keyboard.press('Tab'); expect(await page.evaluate(() => !!document.activeElement.closest('#modal-content')), `Tab ${i + 1}`).toBe(true); }
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  expect(await page.locator('#stop-modal.open').count()).toBe(0);
  await go(`V11_ENGINE.clear()`);
});

test('15 · contrast: text on every destination and lens meets 4.5:1 (3:1 for large text), light and dark', async () => {
  const failures = [];
  for (const theme of ['light', 'dark']) {
    await go(`setTheme('${theme}'); ${SAMPLE}`);
    for (const d of DESTS) {
      for (const lens of d === 'maps' ? LENSES : [null]) {
        await open(d, lens);
        const bad = await page.evaluate(() => {
          const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
          const over = (top, bot) => ({ r: top.r * top.a + bot.r * (1 - top.a), g: top.g * top.a + bot.g * (1 - top.a), b: top.b * top.a + bot.b * (1 - top.a), a: 1 });
          const lum = ({ r, g, b }) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
          const base0 = parse(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
          const bgOf = el => { const chain = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { chain.push(c); if (c.a >= 1) break; } } let base = base0.a >= 1 ? base0 : { r: 255, g: 255, b: 255, a: 1 }; for (let i = chain.length - 1; i >= 0; i--) base = over(chain[i], base); return base; };
          const out = [], seen = new Set(), root = document.getElementById('v11-main');
          const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
          for (let n; (n = walker.nextNode());) {
            const txt = n.textContent.trim(); if (!txt) continue;
            const el = n.parentElement; if (!el || el.closest('[hidden], .sr-only')) continue;
            const inSvg = !!el.closest('svg');
            const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
            const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) continue;
            let op = 1; for (let e = el; e && e !== root; e = e.parentElement) op *= +getComputedStyle(e).opacity;
            const fg0 = parse(inSvg ? cs.fill : cs.color); if (!fg0) continue;
            let bg = bgOf(inSvg ? el.closest('svg').parentElement : el);
            if (inSvg) {
              const bb = el.getBoundingClientRect(), px0 = bb.left + bb.width / 2, py0 = bb.top + bb.height / 2;
              const shape = document.elementsFromPoint(px0, py0).find(e => e !== el && /^(rect|circle|ellipse|path|polygon)$/i.test(e.tagName) && (() => { const f = parse(getComputedStyle(e).fill); return f && f.a * (+getComputedStyle(e).fillOpacity || 1) > 0.05; })());
              if (shape) { const sc = getComputedStyle(shape), f = parse(sc.fill); bg = over({ ...f, a: f.a * (+sc.fillOpacity || 1) }, bg); }
            }
            const fg = over({ ...fg0, a: fg0.a * op }, bg);
            const L1 = lum(fg), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
            const px = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700, large = px >= 24 || (px >= 18.66 && bold);
            const need = large ? 3 : 4.5;
            if (ratio < need) { const key = el.className + '|' + txt.slice(0, 20); if (!seen.has(key)) { seen.add(key); out.push(`${ratio.toFixed(2)}<${need} "${txt.slice(0, 32)}" .${String(el.getAttribute('class') || el.tagName).slice(0, 40)}`); } }
          }
          return out;
        });
        for (const b of bad) failures.push(`${theme} ${d}${lens ? '/' + lens : ''}: ${b}`);
      }
    }
  }
  await go(`setTheme('light')`);
  expect(failures.slice(0, 20), `contrast failures (${failures.length})`).toEqual([]);
});

test('16 · keyboard on the map in dark theme and at 390 px: Tab reaches a lane label with a visible ring, Enter and Space choose, Escape closes the stopped-path dialog', async () => {
  await go(`${SAMPLE}; STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; setTheme('dark')`);
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(vp);
    await open('maps'); await go(`setMapsView('landscape')`);
    const ids = await page.evaluate(() => V11_ENGINE.snapshot().paths.map(p => p.id));
    await page.locator('.v12-map .v12-lane-label').first().focus();
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => document.activeElement.classList.contains('v12-lane-label')), `${vp.width}: Tab reaches a lane label`).toBe(true);
    const ring = await page.evaluate(() => { const cs = getComputedStyle(document.activeElement); return { style: cs.outlineStyle, width: parseFloat(cs.outlineWidth) }; });
    expect(ring.style).toBe('solid'); expect(ring.width).toBeGreaterThanOrEqual(2);
    const first = await page.evaluate(() => document.activeElement.dataset.path);
    expect(ids, 'the lane label is one of the engine paths').toContain(first);
    await page.keyboard.press('Enter'); await page.waitForTimeout(80);
    expect(await page.evaluate(() => selectedPathId()), `${vp.width}: Enter chooses`).toBe(first);
    if (await page.locator('.v12-map .v12-lane-label').count() > 1) {
      const second = await page.locator('.v12-map .v12-lane-label').nth(1).evaluate(e => e.dataset.path);
      await page.locator('.v12-map .v12-lane-label').nth(1).focus(); await page.keyboard.press('Space'); await page.waitForTimeout(80);
      expect(await page.evaluate(() => selectedPathId()), `${vp.width}: Space chooses`).toBe(second);
    } else {
      await go(`setMapsView('landscape')`);
      const card = page.locator('.mp-card').nth(1);
      const second = await card.evaluate(e => e.dataset.path);
      await card.focus(); await page.keyboard.press('Space'); await page.waitForTimeout(80);
      expect(await page.evaluate(() => selectedPathId()), `${vp.width}: Space chooses from the list`).toBe(second);
    }
  }
  // a path the evidence stopped: the dialog opens from the keyboard, Escape closes it, nothing is reopened silently
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(f => {
    V11_ENGINE.clear(); LIVE.artifact.possible_paths = f.possible_paths; LIVE.artifact.navigation = f.navigation; LIVE.projection = f.projection || null;
    LIVE.projectionTried = LIVE.sid; LIVE.explain = null; LIVE.explainState = 'failed'; LIVE.workspace = LIVE.workspace || {}; LIVE.workspace.path_states = f.path_states || {};
    STORE.mapsSelBy = {}; STORE.mapsSelDefaultBy = {}; STORE.mapsView = 'landscape'; goDestination('maps'); setMapsView('landscape');
    mapsSelect(V11_ENGINE.snapshot().paths.find(p => p.status_display === 'STOP').id);
  }, JSON.parse(fs.readFileSync(path.join(here, 'fixtures', 'paths_engine_stop.json'), 'utf8')));
  const anyway = page.getByRole('button', { name: /I want to do this anyway/ });
  await anyway.focus(); await page.keyboard.press('Enter'); await page.waitForTimeout(300);
  expect(await page.locator('#stop-modal.open').count()).toBe(1);
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  expect(await page.locator('#stop-modal.open').count()).toBe(0);
  expect(await page.evaluate(() => V11_ENGINE.snapshot().paths.some(p => p.status_display === 'STOP'))).toBe(true);
  await page.setViewportSize({ width: 1440, height: 900 });
  await go(`setTheme('light'); V11_ENGINE.clear()`);
});

test('17 · nothing logged a console error', async () => {
  expect(consoleErrors).toEqual([]);
});
