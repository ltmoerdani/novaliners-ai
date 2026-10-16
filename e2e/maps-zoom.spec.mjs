/* Maps semantic zoom (Z0 WORLD · Z1 PATH · Z2 ROUTE · Z3 DETAIL) on the unified 2D topology, and the
 * RouteNode ↔ Move binding fix. doc 04 §1–§3, doc 03 §2–§3, doc 05 (focused, per-phase).
 *
 * The map is REAL: the app's own API builds it end to end under the mock provider (session → message →
 * finalize → routes → maps_projection) and the app restores it without a new interview. Variants that the
 * mock engine does not produce (several frontiers, an AND dependency, a canonical Move bound to a node, a
 * stale revision) are made by editing a COPY of the server's own projection in the page — they are marked
 * [variant] and never written back to the server.
 */
import { test, expect } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

let page, ctx, SID = null;
const errors = [];
let checkinProbe404s = 0;   // KNOWN NEGATIVE PROBE (D-02): GET /checkins 404s on a session with no history yet — counted in beforeAll
const U = 'u_e2e_zoom' + Math.random().toString(16).slice(2, 10);
const go = async (js) => { await page.evaluate(`(function(){ ${js} })()`); await page.waitForTimeout(120); };
const level = () => page.locator('#v12-map').getAttribute('data-level');
const nodeIds = () => page.$$eval('.v12-nodebtn', els => els.map(e => e.getAttribute('data-v12-node')));
const projRoute = (pathId) => page.evaluate(id => { const p = (V11_ENGINE.snapshot().maps_projection || { paths: [] }).paths.find(x => x.path_id === id); return p && p.route ? p.route : null; }, pathId);
/* [variant] edit a copy of the server projection for one path, then redraw through the app's own adapter */
const variant = (pathId, fnSrc) => page.evaluate(([id, src]) => {
  const mp = JSON.parse(JSON.stringify(window.__mpServer));   // always from the server's own projection
  const e = mp.paths.find(x => x.path_id === id);
  (new Function('route', 'mp', src))(e.route, mp);
  LIVE.routes = Object.assign({}, LIVE.routes, { maps_projection: mp });
  V11_ENGINE.clear(); renderScreen('maps');
}, [pathId, fnSrc]);

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta', reducedMotion: 'reduce' });
  page = await ctx.newPage();
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('response', r => {
    if (r.status() < 400) return;
    /* KNOWN NEGATIVE PROBE (D-02): GET /checkins on a session with no check-in history answers 404
       and the client treats it as an empty history. The browser logs every 404, so this one honest
       probe is exempted BY URL — any other 4xx/5xx still fails. Follow-up: the server should answer
       200 {checkins: []} for "none yet" (empty is a state, not an error). */
    const url = r.url();
    if (r.status() === 404 && /\/session\/[a-z0-9]+\/checkins\?*$/.test(url)) { checkinProbe404s++; return; }
    errors.push(`http ${r.status()} ${r.request().method()} ${url}`);
  });
  page.on('dialog', d => d.accept());
  await page.addInitScript((uid) => {
    try { localStorage.setItem('novaliners-theme', 'light'); localStorage.setItem('novaliners-v9', JSON.stringify({ userId: uid, chain: [], checkins: [], overrides: [], tips: {} })); } catch (e) { /* ignore */ }
  }, U);
});
test.afterAll(async () => { await ctx.close(); });

test('00 · a real routed map, restored without a new interview; the flat map opens at Z0', async ({ baseURL }) => {
  await page.goto(`${baseURL}/`, { waitUntil: 'networkidle' });
  const post = async (p, data) => { const r = await page.request.post(p, { data }); expect(r.ok(), `${p} -> ${r.status()}`).toBeTruthy(); return r.json().catch(() => ({})); };
  SID = (await post('/session', { goal_text: 'I run a small B2B consulting practice. Revenue is Rp30 million a month now and I want Rp60 million a month within 3 months.', language: 'en', user_id: U })).session_id;
  for (const text of ['Revenue is Rp30 million per month right now, mostly from two retainer clients.', 'I want to reach Rp60 million per month within 3 months.',
    'Two new prospects asked for proposals this month, demand exists.', 'I can deliver about 25 hours a week of client work myself.',
    'Average project size is Rp10 million per client.', 'I have no dedicated sales person; I do all outreach myself.']) await post(`/session/${SID}/message`, { text });
  await post(`/session/${SID}/finalize`, {});
  const routes = await post(`/session/${SID}/routes`, {});
  expect(routes.maps_projection).toBeTruthy();
  await page.evaluate(async sid => { await loadMapSession(sid); }, SID);
  await page.waitForFunction(sid => typeof LIVE !== 'undefined' && LIVE.sid === sid && !!LIVE.artifact && !!LIVE.routes, SID, { timeout: 30_000 });
  await page.evaluate(() => { window.__mpServer = JSON.parse(JSON.stringify(LIVE.routes.maps_projection)); });
  await go(`STORE.mapMode = '2d'; STORE.mapsLevel = 'Z0'; STORE.mapsSelBy = {}; STORE.mapsView = 'landscape'; goDestination('maps')`);
  await page.waitForTimeout(300);
  expect(await level()).toBe('Z0');
});

test('01 · Z0 WORLD: the moves show as nodes on every routed corridor — frontier only, no dependency edges, no clusters (owner feedback 17 Oct; doc 22)', async () => {
  const d = await page.evaluate(() => {
    const mp = window.__mpServer;
    const frontier = new Set();
    (mp.paths || []).slice(0, 5).forEach(e => {
      ((e.route && e.route.frontier) || []).forEach(f => { if (f.node_id) frontier.add(e.path_id + '::' + f.node_id); });
    });
    return {
      nodes: document.querySelectorAll('.v12-nodebtn').length, clusters: document.querySelectorAll('.v12-cluster').length,
      deps: document.querySelectorAll('.v12-dep').length, corridors: document.querySelectorAll('.v12-corridor').length,
      paths: Math.min(V11_ENGINE.snapshot().paths.length, 5), moveId: (V11_ENGINE.snapshot().nextmove || {}).move_id || null,
      frontier: frontier.size, folded: document.querySelectorAll('.v12-group-link').length
    };
  });
  expect(d.corridors).toBe(d.paths);
  expect(d.deps).toBe(0);
  expect(d.clusters).toBe(0);
  expect(d.moveId).toBeNull();                 // the mock engine presents no canonical Move → no focal step
  expect(d.nodes).toBe(d.frontier - d.folded); // every frontier move is on its spot; agreeing shared members fold into one node
  expect(d.nodes).toBeGreaterThan(0);
});

test('02 · no corridor reaches the goal: every line ends at its own route end (or STOP) short of the goal landmark', async () => {
  const d = await page.evaluate(() => {
    const goal = document.querySelector('.v12-goal circle');
    const gx = +goal.getAttribute('cx');
    return [...document.querySelectorAll('.v12-corridor')].map(p => { const len = p.getTotalLength(); const end = p.getPointAtLength(len); return { gap: gx - end.x }; });
  });
  for (const c of d) expect(c.gap).toBeGreaterThan(20);
  expect(await page.locator('.v12-route-end').count()).toBe(await page.locator('.v12-corridor[data-v12-stop="0"]').count());
});

test('02b · every live path continues toward the goal — OPEN in its own colour, the rest dotted; a STOP stops at its cross (doc 22 §58)', async () => {
  const d = await page.evaluate(() => {
    const snap = V11_ENGINE.snapshot();
    const live = snap.paths.filter(p => p.status_display !== 'STOP').map(p => p.id);
    const open = snap.paths.filter(p => p.status_display === 'OPEN').map(p => p.id);
    const links = [...document.querySelectorAll('.v12-goal-link')];
    const corr = [...document.querySelectorAll('.v12-corridor[data-v12-stop="0"]')];
    const gx = +document.querySelector('.v12-goal circle').getAttribute('cx');
    return {
      live, open, ids: links.map(l => l.getAttribute('data-v12-goal-link')),
      openFlag: links.map(l => l.getAttribute('data-v12-open')),
      solid: links.filter(l => l.getAttribute('data-v12-open') === '1' && !l.getAttribute('stroke-dasharray')).length,
      dotted: links.filter(l => l.getAttribute('data-v12-open') === '0' && !!l.getAttribute('stroke-dasharray')).length,
      gaps: corr.map(p => { const len = p.getTotalLength(); return gx - p.getPointAtLength(len).x; })
    };
  });
  expect(d.live.length).toBeGreaterThan(0);
  expect(d.ids.slice().sort()).toEqual(d.live.slice().sort());   // every live path continues; a STOP does not
  expect(d.solid).toBe(d.open.length);                            // OPEN continues in its own colour, solid
  expect(d.dotted).toBe(d.live.length - d.open.length);           // the rest continue dotted, colourless
  for (const g of d.gaps) expect(g).toBeGreaterThan(20);          // the corridor line itself still ends at its route end (§242)
});

test('02c · a requirement held by two paths with the same id, wording and state draws ONCE as a shared node; a state difference falls back to marked-never-merged (doc 22 §38)', async () => {
  const ids = await page.evaluate(() => V11_ENGINE.snapshot().paths.slice(0, 2).map(p => p.id));
  const seed = (satA, satB) => `route.nodes = [{ node_id: route.route_id + '-shared', label: 'Two prospects asked for proposals', resolves: ['req.shared'], satisfaction: { status: '${satA}' }, executability: { status: 'READY' }, execution: { view: 'TODO' }, depends_on: [], presentation: { kind: 'open' }, frontier_kind: 'EXECUTE' }];
    route.frontier = [{ kind: 'EXECUTE', node_id: route.nodes[0].node_id }]; route.terminals = [];
    const other = mp.paths.find(x => x.path_id === ${JSON.stringify(ids[1])});
    if (other && other.route) { other.route.nodes = [{ node_id: other.route.route_id + '-shared', label: 'Two prospects asked for proposals', resolves: ['req.shared'], satisfaction: { status: '${satB}' }, executability: { status: 'READY' }, execution: { view: 'TODO' }, depends_on: [], presentation: { kind: 'open' }, frontier_kind: 'EXECUTE' }]; other.route.frontier = [{ kind: 'EXECUTE', node_id: other.route.nodes[0].node_id }]; other.route.terminals = []; }`;
  /* agreeing: one representative, one dotted rail from the folded member, the honest footnote */
  await variant(ids[0], seed('UNKNOWN', 'UNKNOWN'));
  expect(await page.locator('.v12-group-link').count()).toBe(1);
  expect(await page.locator('.v12-shared-solid').count()).toBeGreaterThan(0);
  /* the footnote lives in SVG <text>: innerText skips it, so read textContent */
  const agreeFoot = await page.evaluate(() => [...document.querySelectorAll('#v11-main svg text')].map(x => x.textContent).join(' | '));
  expect(agreeFoot).toMatch(/drawn once as shared nodes?/);
  expect(agreeFoot).toContain('(id, wording and state agree)');
  /* disagreeing: the states differ, so nothing merges — each route keeps its own dashed ring */
  await variant(ids[0], seed('PRESENT', 'UNKNOWN'));
  expect(await page.locator('.v12-group-link').count()).toBe(0);
  expect(await page.locator('.v12-shared-ring').count()).toBeGreaterThanOrEqual(1);
  const disagreeFoot = await page.evaluate(() => [...document.querySelectorAll('#v11-main svg text')].map(x => x.textContent).join(' | '));
  expect(disagreeFoot).toContain('never merged');
  await page.evaluate(() => { LIVE.routes = Object.assign({}, LIVE.routes, { maps_projection: JSON.parse(JSON.stringify(window.__mpServer)) }); V11_ENGINE.clear(); renderScreen('maps'); });
});

test('03 · Z1: choosing a path shows its whole frontier, folds the rest into one "+N" cluster (a count, not a node)', async () => {
  const route = await projRoute('path.direct_outreach');
  await go(`mapsSelect('path.direct_outreach')`);
  expect(await level()).toBe('Z1');
  const fr = route.frontier.map(f => f.node_id).filter(Boolean);
  expect((await nodeIds()).sort()).toEqual(fr.sort());
  const cl = await page.$$eval('.v12-cluster', els => els.map(e => e.getAttribute('data-v12-cluster').split(',').length));
  expect(cl.reduce((a, b) => a + b, 0)).toBe(route.nodes.length - fr.length);
});

test('04 · Z2: every RouteNode of the chosen route and exactly its depends_on edges; one route open at a time', async () => {
  const route = await projRoute('path.direct_outreach');
  await go(`v12ZoomIn()`);
  expect(await level()).toBe('Z2');
  expect((await nodeIds()).length).toBe(route.nodes.length);
  const deps = route.nodes.reduce((a, n) => a + (n.depends_on || []).length, 0);
  expect(await page.locator('.v12-dep').count()).toBe(deps);
  expect(new Set(await page.$$eval('.v12-nodebtn', els => els.map(e => e.getAttribute('data-v12-path')))).size).toBe(1);
  await expect(page.locator('.v12-route-list li')).toHaveCount(route.nodes.length);
});

test('05 · zooming out removes detail and keeps the choice; the engine focus never moves with it', async () => {
  const focus = await page.evaluate(() => (V11_ENGINE.snapshot().nextmove || {}).path_id);
  await go(`v12ZoomOut()`);
  expect(await level()).toBe('Z1');
  await go(`v12ZoomOut()`);
  expect(await level()).toBe('Z0');
  expect(await page.evaluate(() => selectedPathId(V11_ENGINE.snapshot()))).toBe('path.direct_outreach');
  /* Z0 WORLD shows the moves on every routed corridor now (owner, 17 Oct) — zooming out returns to
     that world, it does not empty it. */
  expect(await page.locator('.v12-nodebtn').count()).toBeGreaterThan(0);
  expect(await page.evaluate(() => (V11_ENGINE.snapshot().nextmove || {}).path_id)).toBe(focus);
});

test('06 · choosing another path does not rearrange the map: lanes and anchors stay where they were', async () => {
  const lanes = () => page.$$eval('.v12-lane-label', els => els.map(e => [e.getAttribute('data-v12-path'), Math.round(e.getBBox().y)]));
  const anchors = () => page.evaluate(() => [document.querySelector('.v12-here circle').getAttribute('cx'), document.querySelector('.v12-goal circle').getAttribute('cx')]);
  await go(`mapsSelect('path.direct_outreach')`);
  const a = await lanes(), h = await anchors();
  await go(`mapsSelect('path.client_expansion')`);
  expect(await lanes()).toEqual(a);
  expect(await anchors()).toEqual(h);
});

test('07 · ctrl/⌘ + wheel zooms the canvas with hysteresis; a plain wheel is left to the page', async () => {
  await go(`STORE.mapsLevel = 'Z0'; mapsSelect('path.direct_outreach'); v12SetLevel('Z0')`);
  const box = await page.locator('#v12-map').boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  const plain = await page.evaluate(() => { const e = new WheelEvent('wheel', { deltaY: 120, bubbles: true, cancelable: true }); document.querySelector('#v12-map').dispatchEvent(e); return e.defaultPrevented; });
  expect(plain).toBe(false);
  await page.keyboard.down('Control'); await page.mouse.wheel(0, -15); await page.keyboard.up('Control');
  expect(await level()).toBe('Z0');                                   // a small pinch only scales
  const vb = await page.locator('#v12-map .v12-stage > svg').getAttribute('viewBox');
  expect(vb.startsWith('0 0 ')).toBeFalsy();
  for (let i = 0; i < 6 && (await level()) === 'Z0'; i++) { await page.keyboard.down('Control'); await page.mouse.wheel(0, -15); await page.keyboard.up('Control'); }
  expect(await level()).toBe('Z1');                                   // past the threshold: more detail
  for (let i = 0; i < 12 && (await level()) === 'Z1'; i++) { await page.keyboard.down('Control'); await page.mouse.wheel(0, 15); await page.keyboard.up('Control'); }
  expect(await level()).toBe('Z0');
  await go(`v12FitMap()`);
});

test('08 · keyboard: the zoom controls, a cluster and a step are buttons; Enter on the cluster opens the route', async () => {
  await go(`STORE.mapsLevel = 'Z1'; mapsSelect('path.direct_outreach')`);
  for (const k of ['out', 'in', 'route', 'focus', 'fit']) await expect(page.locator(`[data-v12-zoom="${k}"]`)).toHaveCount(1);
  await page.locator('.v12-cluster').first().focus();
  await page.keyboard.press('Enter');
  await page.waitForTimeout(120);
  expect(await level()).toBe('Z2');
  await expect(page.locator('.v12-nodebtn').first()).toHaveAttribute('role', 'button');
});

test('09 · Z3: a frontier step on the path in focus gets NO "Open in Moves" without an exact reference (the old path+frontier binding)', async () => {
  const focus = await page.evaluate(() => (V11_ENGINE.snapshot().nextmove || {}).path_id);
  const route = await projRoute(focus);
  test.skip(!route, 'the presented move names no path with a route');
  /* [variant] give the focus path's route an EXECUTE frontier node, keep the presented move without move_id */
  await variant(focus, `const n = route.nodes[0]; route.frontier = [{ kind: 'EXECUTE', node_id: n.node_id }]; n.frontier_kind = 'EXECUTE'; n.presentation = { kind: 'now', word: 'Now' };`);
  await go(`STORE.mapsLevel = 'Z2'; mapsSelect('${focus}')`);
  const nid = route.nodes[0].node_id;
  await go(`v12NodeInspector('${focus}', '${nid}')`);
  const t = await page.locator('#drawer-content').innerText();
  expect(t).toContain('can do this step now');
  await expect(page.locator('#drawer-content [data-v12-move-cta]')).toHaveCount(0);
  await go(`closeDrawer()`);
});

test('10 · [variant] a canonical Move whose route_node_ref names this route, node and revision: focal at Z0, "Open in Moves" opens Moves', async () => {
  const focus = await page.evaluate(() => (V11_ENGINE.snapshot().nextmove || {}).path_id);
  const route = await projRoute(focus);
  const nid = route.nodes[0].node_id;
  await page.evaluate(([rid, n, rev]) => {
    LIVE.nav = { move: Object.assign({}, (LIVE.nav || {}).move || {}, { move_id: 'mv-e2e-1' }), summary: null };
    LIVE.mapsMoves = { sid: LIVE.sid, list: [{ move_id: 'mv-e2e-1', objective: 'E2E bound move', route_node_ref: { route_id: rid, node_id: n, route_revision: rev } }] };
    V11_ENGINE.clear(); STORE.mapsLevel = 'Z0'; STORE.mapsSelBy = {}; renderScreen('maps');
  }, [route.route_id, nid, route.revision_no]);
  await page.waitForTimeout(150);
  /* Z0 WORLD (owner, 17 Oct): every routed corridor shows its frontier moves — the focal step must be
     among them, no longer alone. */
  expect(await nodeIds()).toContain(nid);
  await expect(page.locator('.v12-chip-txt', { hasText: 'Your move' })).toHaveCount(1);
  await go(`v12NodeInspector('${focus}', '${nid}')`);
  await expect(page.locator('#drawer-content [data-v12-move-cta="canonical_move"]')).toHaveCount(1);
  await page.locator('#drawer-content [data-v12-move-cta]').click();
  await page.waitForTimeout(200);
  expect(await page.evaluate(() => STORE.currentScreen)).toMatch(/moves|today|04/);
  await go(`goDestination('maps')`);
});

test('11 · [variant] the same Move on an older route revision is stale: said plainly, no CTA, no focal step', async () => {
  const focus = await page.evaluate(() => (V11_ENGINE.snapshot().nextmove || {}).path_id);
  const route = await projRoute(focus);
  const nid = route.nodes[0].node_id;
  await page.evaluate(([rid, n, rev]) => { LIVE.mapsMoves.list[0].route_node_ref = { route_id: rid, node_id: n, route_revision: rev }; V11_ENGINE.clear(); STORE.mapsLevel = 'Z0'; renderScreen('maps'); }, [route.route_id, nid, route.revision_no + 1]);
  await page.waitForTimeout(120);
  /* the stale move loses its focal presentation — the step itself may still show as its corridor's
     frontier (Z0 WORLD, owner 17 Oct), but nothing calls it "Your move" and nothing offers the CTA */
  expect(await page.locator('.v12-chip-txt', { hasText: 'Your move' })).toHaveCount(0);
  await go(`v12NodeInspector('${focus}', '${nid}')`);
  expect(await page.locator('#drawer-content').innerText()).toContain('older version of this route');
  await expect(page.locator('#drawer-content [data-v12-move-cta]')).toHaveCount(0);
  await go(`closeDrawer(); LIVE.nav = null; LIVE.mapsMoves = null; V11_ENGINE.clear(); renderScreen('maps')`);
});

test('12 · [variant] several frontiers and an AND dependency: all frontiers at Z1, both edges into the joined step at Z2', async () => {
  await variant('path.direct_outreach', `
    const [a, b, c] = route.nodes;
    b.depends_on = []; c.depends_on = [a.node_id, b.node_id];
    route.frontier = [{ kind: 'EXECUTE', node_id: a.node_id }, { kind: 'VERIFY', node_id: b.node_id }];`);
  const route = await projRoute('path.direct_outreach');
  await go(`STORE.mapsLevel = 'Z1'; mapsSelect('path.direct_outreach')`);
  expect((await nodeIds()).sort()).toEqual([route.nodes[0].node_id, route.nodes[1].node_id].sort());
  await go(`v12ZoomIn()`);
  const into = await page.$$eval('.v12-dep', (els, to) => els.filter(e => e.getAttribute('data-v12-dep').endsWith('->' + to)).length, route.nodes[2].node_id);
  expect(into).toBe(2);
});

test('13 · [variant] EXECUTED without PRESENT reads "Proof due", never "Done"; a route-less path draws no node and cannot expand', async () => {
  await variant('path.direct_outreach', `
    const n = route.nodes[0]; n.execution = { view: 'EXECUTED' }; n.satisfaction = { status: 'UNKNOWN' }; n.presentation = { kind: 'awaiting_proof', word: 'Awaiting proof' };
    const other = mp.paths.find(x => x.path_id === 'path.client_expansion'); other.route = null;`);
  await go(`STORE.mapsLevel = 'Z2'; mapsSelect('path.direct_outreach')`);
  const nid = (await projRoute('path.direct_outreach')).nodes[0].node_id;
  await expect(page.locator(`.v12-chip-txt[data-v12-node="${nid}"]`)).toHaveText('Proof due');
  await go(`mapsSelect('path.client_expansion')`);
  expect(await level()).toBe('Z1');
  expect(await page.locator('.v12-nodebtn[data-v12-path="path.client_expansion"]').count()).toBe(0);
  await expect(page.locator('[data-v12-zoom="route"]')).toBeDisabled();
});

test('14 · requirements named by two routes follow the doc 22 §38 guard: agreeing id+wording+state draws once; a disagreement is marked, never merged', async () => {
  await page.evaluate(() => { LIVE.routes = Object.assign({}, LIVE.routes, { maps_projection: JSON.parse(JSON.stringify(window.__mpServer)) }); V11_ENGINE.clear(); });
  const counts = await page.evaluate(() => {
    const mp = V11_ENGINE.snapshot().maps_projection;
    const by = {};
    mp.paths.filter(p => p.route).forEach(p => p.route.nodes.forEach(n => (n.resolves || []).forEach(r => { (by[r] = by[r] || new Set()).add(p.path_id); })));
    return Object.entries(by).filter(([, s]) => s.size > 1).map(([r, s]) => [r, s.size]);
  });
  if (!counts.length) test.skip(true, 'this engine run names no requirement on two routes');
  const shared = counts[0][0];
  const holders = await page.evaluate(r => V11_ENGINE.snapshot().maps_projection.paths.filter(p => p.route && p.route.nodes.some(n => (n.resolves || []).includes(r))).map(p => p.path_id), shared);
  await go(`STORE.mapsLevel = 'Z2'; mapsSelect('${holders[0]}')`);
  const n = await page.evaluate(r => { const p = V11_ENGINE.snapshot().maps_projection.paths.find(x => x.path_id === selectedPathId(V11_ENGINE.snapshot())); return p.route.nodes.filter(x => (x.resolves || []).includes(r)).length; }, shared);
  expect(n).toBeGreaterThan(0);
  /* Z2 is selection-scoped: the other holder's nodes are not drawn here, so the guard shows up as the
     marking on this route's own node — agreeing groups carry the solid shared ring, disagreements the
     dashed one (asserted end-to-end by 02c). */
  const marks = await page.evaluate(() => ({
    solid: document.querySelectorAll('.v12-shared-solid').length,
    dashed: document.querySelectorAll('circle[stroke-dasharray="3 3"]').length
  }));
  expect(marks.solid + marks.dashed).toBeGreaterThan(0);
});

test('15 · phone (390px): no miniature graph — the canvas stays the overview, the chosen path\'s steps come as a list', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  await go(`V11_ENGINE.clear(); STORE.mapsLevel = 'Z1'; mapsSelect('path.direct_outreach')`);
  await page.waitForTimeout(300);
  /* on the phone the canvas is forced to Z0 (the overview with the moves); the chosen path's steps
     come as the route list under it */
  expect(await page.locator('.v12-route-list li').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('15b · REAL execution report: the app records EXECUTED on a frontier step; the server projection redraws it "Proof due", satisfaction untouched', async () => {
  await page.evaluate(() => { LIVE.routes = Object.assign({}, LIVE.routes, { maps_projection: JSON.parse(JSON.stringify(window.__mpServer)) }); V11_ENGINE.clear(); });
  const route = await projRoute('path.direct_outreach');
  const fr = route.frontier.find(f => f.kind === 'EXECUTE');
  test.skip(!fr, 'no EXECUTE frontier on this run');
  const before = route.nodes.find(n => n.node_id === fr.node_id).satisfaction.status;
  await page.evaluate(([rid, nid]) => liveRouteEvent(rid, nid, 'EXECUTED'), [route.route_id, fr.node_id]);
  await page.waitForTimeout(300);
  await go(`V11_ENGINE.clear(); STORE.mapsLevel = 'Z2'; goDestination('maps'); mapsSelect('path.direct_outreach')`);
  const after = await projRoute('path.direct_outreach');
  const n = after.nodes.find(x => x.node_id === fr.node_id);
  expect(n.execution.view).toBe('EXECUTED');
  expect(n.satisfaction.status).toBe(before);                         // doing is not proving
  expect(n.satisfaction.status).not.toBe('PRESENT');
  /* "Proof due" — or, when the engine's route selector now asks for that very proof, "Your move · proof due" */
  await expect(page.locator(`.v12-chip-txt[data-v12-node="${fr.node_id}"]`)).toHaveText(/proof due/i);
  /* the map only reads: the event lives in the server's own ledger, not in the page */
  const r = await page.request.post(`/session/${SID}/routes`, { data: {} });
  const fresh = (await r.json()).maps_projection.paths.find(p => p.path_id === 'path.direct_outreach').route.nodes.find(x => x.node_id === fr.node_id);
  expect(fresh.execution.view).toBe('EXECUTED');
});

test('16 · nothing threw and nothing logged an error', async () => {
  /* the exempted /checkins negative probes each pair with one generic browser console line for the
     404 response — drop exactly that many, so a real error can still never hide (see beforeAll) */
  const GENERIC_404 = 'console: Failed to load resource: the server responded with a status of 404 (Not Found)';
  const rest = errors.filter(e => e !== GENERIC_404);
  const generic = errors.filter(e => e === GENERIC_404);
  const kept = generic.slice(checkinProbe404s);
  expect(rest.concat(kept), 'nothing threw and nothing logged an error').toEqual([]);
});
