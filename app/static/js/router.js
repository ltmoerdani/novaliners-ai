/* Screen router: renderScreen(id) is the single entry point (inline handlers call it everywhere).
 * Product destinations (record D3, D6): 'state', 'maps' (lens in STORE.mapsView), 'moves', 'journey', 'talk'.
 * The v9 numeric ids that used to be those screens are ALIASES of them, so every old call site lands on the
 * destination. The v9 screens themselves were REMOVED in the legacy cleanup (2026-10-15, record D5 successors).
 * Hash routes: #/state #/maps #/maps/overview #/maps/readiness #/moves #/journey #/talk, plus the entry flow. */
const V11_ALIAS = {
  '17': 'state', '07': 'maps', '07b': 'maps', '07c': 'maps', '18': 'maps:readiness',
  '04': 'moves', '08': 'journey', '19': 'talk'
};
const SCREEN_HASH = {
  '01': '/', '02': '/diagnosis', '03': '/diagnosis/result', '05': '/check-in',
  '06a': '/map/updated', '06b': '/map/adjusted-quiet', '12': '/map/adjusted-mixed',
  '10': '/demo/contrast', '13': '/diagnosis/provisional', '14': '/activity/welcome-back',
  '15': '/diagnosis/safety-first', '16': '/day-review',
  'state': '/state', 'maps': '/maps', 'moves': '/moves', 'journey': '/journey', 'talk': '/talk'
};
const HASH_SCREEN = Object.fromEntries(Object.entries(SCREEN_HASH).map(([k, v]) => ['#' + v, k]));
HASH_SCREEN['#/maps/overview'] = 'maps'; HASH_SCREEN['#/maps/readiness'] = 'maps';   // overview: kept only so the redirect below can resolve it
/* D6: hashes of the v9 menu redirect to their v11 destination (internal-docs §7).
 * #/journey stays. Older bookmarks (#/summary, #/today) follow the same road. */
const HASH_REDIRECT = {
  '#/activity': '#/moves', '#/diagnosis/current': '#/state', '#/map': '#/maps', '#/map/readiness': '#/maps/readiness',
  '#/ask': '#/talk', '#/summary': '#/state', '#/today': '#/moves', '#/today/welcome-back': '#/activity/welcome-back',
  '#/map/zero-open': '#/maps', '#/map/several-open': '#/maps',
  '#/maps/overview': '#/maps',  // Overview was merged into Explore (UX v11); the old address resolves there, selection kept
  /* NC-05: "Map updated" is NOT a second product. The old result pages resolve to the one Maps destination;
     the change itself is shown there as a contextual summary from the durable change_set. No specific change
     is claimed on a bare deep link (there is no accepted event reference). */
  '#/map/updated': '#/maps', '#/map/adjusted-quiet': '#/maps', '#/map/adjusted-mixed': '#/maps'
};
const NEEDS_DIAGNOSIS = ['03', '05', '06a', '06b', '09', '11', '12', '13', '14', '16', 'state', 'maps', 'moves', 'journey'];
const V11_PRODUCT = ['state', 'maps', 'moves', 'journey', 'talk'];
const MAPS_LENS_HASH = { landscape: '/maps', readiness: '/maps/readiness' };

/* Apply the redirect table to the address bar (replace, not push: Back must not return to the old address). */
function redirectOldHash() {
  const to = HASH_REDIRECT[location.hash];
  if (to) history.replaceState(null, '', to);
  return !!to;
}
function hashLens() { return location.hash === '#/maps/readiness' ? 'readiness' : (location.hash === '#/maps/overview' || location.hash === '#/maps') ? 'landscape' : null; }  // old #/maps/overview resolves to Explore
function hashFor(id) {
  if (id === 'maps') return MAPS_LENS_HASH[MAPS_VIEWS.includes(STORE.mapsView) ? STORE.mapsView : 'landscape'];
  /* NC-05: the retired result pages never write their legacy address; they resolve to Maps. */
  if (id === '06a' || id === '06b' || id === '12') return '/maps';
  return SCREEN_HASH[id];
}
function hashScreen() { redirectOldHash(); return HASH_SCREEN[location.hash] || null; }

/* Live guard: never render a screen whose data does not exist yet. */
function guardScreen(id) {
  if (IS_DEMO) return id;
  if (id === '15') return LIVE.artifact ? '03' : '01';
  if (id === 'talk') return LIVE.artifact ? 'talk' : (LIVE.sid ? '02' : '01');          // before a diagnosis, Talk is the interview
  if (NEEDS_DIAGNOSIS.includes(id) && !LIVE.artifact) return LIVE.sid ? '02' : '01';
  if (id === '02' && !LIVE.sid && !LIVE.msgs.length) return '01';
  return id;
}

function screenHtml(id) {
  const demo = IS_DEMO;
  switch (id) {
    case '01': return screen01();
    case '02': return demo ? screen02() : screen02Live();
    case '03': return demo ? screen03() : screen03Live();
    case 'state': return screenState11();
    case 'maps': return screenMaps11();
    case 'moves': return screenMoves11();
    case 'journey': return screenJourney11();
    case 'talk': return screenTalk11();
    case '05': return demo ? screen05() : screen05Live();
    case '06a': return demo ? screen06a() : screen06Live('worked');
    case '06b': return demo ? screen06b() : screen06Live('none');
    case '12': return demo ? screen12() : screen06Live('mixed');
    case '10': return screen10();
    case '13': return demo ? screen13() : screen03Live();
    case '14': return demo ? screen14() : screen14Live();
    case '15': return screen15();
    case '16': return demo ? screen16() : screen16Live();
    /* Demo backdrop of the "doing a stopped path" overlay (11): the prototype's own path map scene. */
    case '07': return screen07();
    default: return screenState11();
  }
}

function renderScreen(screenId) {
  if (V11_ALIAS[screenId]) {
    const a = V11_ALIAS[screenId];
    if (a === 'maps:readiness') { if (STORE.mapsView !== 'readiness') STORE.mapsLens = MAPS_VIEWS.includes(STORE.mapsView) && STORE.mapsView !== 'readiness' ? STORE.mapsView : 'landscape'; STORE.mapsView = 'readiness'; screenId = 'maps'; }
    else screenId = a;
  }
  screenId = guardScreen(screenId);
  if (screenId !== 'moves' && screenId !== '04') STORE.viewStep = 0;   // Moves shows the suggested step unless a checklist row was just picked
  STORE.currentScreen = screenId;
  const selEl = document.getElementById('screen-selector');
  if (selEl) {
    selEl.value = screenId === 'maps' && STORE.mapsView !== 'landscape' ? 'maps:' + STORE.mapsView : screenId;
    updateProtoWidgetLabel();
  }
  const root = document.getElementById('app-root');
  window.scrollTo({ top: 0, behavior: 'instant' });
  if (!IS_DEMO && screenId !== '09' && screenId !== '11') { closeDrawer(); closeModal(); }

  if (screenId === '09') {
    root.innerHTML = screenHtml('03');
    openDrawer();
  } else if (screenId === '11' && IS_DEMO) {   // demo study overlay only: the prototype's stop-path modal over its own map scene
    root.innerHTML = screenHtml('07');
    animateMapProgress();
    openModal();
  } else {
    root.innerHTML = screenHtml(screenId);
  }
  if (typeof v12Mount === 'function') v12Mount();
  if (STORE.restoreFocus) {
    const f = document.querySelector(STORE.restoreFocus);
    STORE.restoreFocus = null;
    if (f) f.focus({ preventScroll: true });
  }
  if (IS_DEMO && screenId === 'talk') talkAfterRender();
  if (!IS_DEMO) {
    // Shell screens already contain <main>; the onboarding canvases get the landmark instead
    if (!root.querySelector('main')) { const c = root.querySelector('.full-canvas'); if (c) c.setAttribute('role', 'main'); }
    const h = hashFor(screenId);
    if (h && location.hash !== '#' + h) history.replaceState(null, '', '#' + h);
    afterLiveRender(screenId);
  }
}

/* A render replaces the whole DOM. When the render is not the person's own action (the plain-language rewrite landing 15 to 50
 * seconds after the page opened), what they were doing must survive it: the focused control, every opened <details> (the "+N more"
 * list, "What we don't know yet"), the scroll of the page and of the main area. Without this a late rewrite closed the list a
 * keyboard user had just opened and dropped focus on <body>: the root cause of the timing-dependent presentation-cap keyboard
 * failure (1 in 15 runs on main, record §6.1). */
function uiKeyOf(el) {
  if (!el || el === document.body || !el.tagName) return null;
  if (el.id) return '#' + el.id.replace(/([^\w-])/g, '\\$1');
  const dp = el.getAttribute('data-path'), tid = el.getAttribute('data-testid'), al = el.getAttribute('aria-label');
  const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(c => '.' + c).join('') : '';
  if (dp) return `${el.tagName.toLowerCase()}${cls}[data-path="${dp.replace(/"/g, '\\"')}"]`;
  if (tid) return `[data-testid="${tid}"]`;
  if (al) return `${el.tagName.toLowerCase()}[aria-label="${al.replace(/"/g, '\\"')}"]`;
  const oc = el.getAttribute('onclick');
  if (oc && oc.length < 160) return `${el.tagName.toLowerCase()}[onclick="${oc.replace(/"/g, '\\"')}"]`;
  return null;
}
function uiSnapshot() {
  const root = document.getElementById('app-root');
  const a = document.activeElement;
  const inRoot = !!(root && a && root.contains(a));
  const main = document.getElementById('v11-main');
  return {
    focus: inRoot ? uiKeyOf(a) || (a.tagName === 'SUMMARY' && a.parentElement ? { summaryOf: uiKeyOf(a.parentElement) } : null) : null,
    open: root ? [...root.querySelectorAll('details[open]')].map(uiKeyOf).filter(Boolean) : [],
    y: window.scrollY, mainY: main ? main.scrollTop : 0
  };
}
function uiRestore(s) {
  if (!s) return;
  const root = document.getElementById('app-root');
  if (!root) return;
  for (const k of s.open) { try { const d = root.querySelector(k); if (d) d.open = true; } catch (e) { /* a selector that no longer exists is skipped */ } }
  try {
    const target = typeof s.focus === 'string' ? root.querySelector(s.focus) : (s.focus && s.focus.summaryOf ? (root.querySelector(s.focus.summaryOf) || {}).querySelector?.('summary') : null);
    if (target && target.focus) target.focus({ preventScroll: true });
  } catch (e) { /* the control is gone (the rewrite changed the page): leave focus where the render put it */ }
  window.scrollTo({ top: s.y, behavior: 'instant' });
  const main = document.getElementById('v11-main'); if (main) main.scrollTop = s.mainY;
}
function renderScreenKeepingUi(id) {
  const s = uiSnapshot();
  renderScreen(id);
  uiRestore(s);
}

/* Post-render hooks for live screens (focus, autoscroll) */
function afterLiveRender(id) {
  if (id === 'talk') {
    if (typeof talkAfterRender === 'function') talkAfterRender();
    /* NC-R9: navigation never triggers an assessment preview. Talk's preview is explicit-only
       (the "What changed?" control); committing a reassessment belongs to Maps. */
  }
  if (id === 'journey') {
    // Canonical same-session timeline (first sessions included). Read-only post-render hook so the
    // large Journey renderer stays untouched; the data comes from GET /experience.journey_events.
    if (typeof journeyEnsureTimeline === 'function') journeyEnsureTimeline();
  }
  if (id === 'maps') {
    // NC-05: the durable change summary after an accepted result, rendered inside the ONE Maps
    // destination (never a separate "Map updated" scene). Read-only post-render hook.
    if (typeof mapsEnsureChangeSummary === 'function') mapsEnsureChangeSummary();
  }
  if (id === '02') {
    const el = document.getElementById('chat-messages-container');
    if (el) el.scrollTop = el.scrollHeight;
    const input = document.getElementById('diag-chat-input');
    if (input && !LIVE.thinking && !LIVE.finalizing) input.focus();
  }
}

window.addEventListener('hashchange', () => {
  const id = hashScreen();
  if (!id || IS_DEMO) return;
  const lens = id === 'maps' ? hashLens() : null;
  const sameLens = id !== 'maps' || !lens || lens === STORE.mapsView;
  if (id !== STORE.currentScreen || !sameLens) {
    if (lens) { if (lens !== 'readiness' && STORE.mapsView === 'readiness') STORE.mapsLens = lens; STORE.mapsView = lens; }
    renderScreen(id);
  }
});

/* ── Boot ─────────────────────────────────────────────────────────────────── */
function defaultLiveScreen() {
  if (!LIVE.sid) return '01';
  if (!LIVE.artifact) return '02';
  return 'state';
}

document.addEventListener('DOMContentLoaded', async () => {
  document.body.dataset.mode = IS_DEMO ? 'demo' : 'live';
  initWidget();
  if (IS_DEMO) {
    renderScreen(hashScreen() || 'state');
    updateProtoWidgetLabel();
    return;
  }
  document.getElementById('app-root').innerHTML = '<div class="full-canvas" style="align-items:center;justify-content:center;background:var(--surface);color:var(--ink-3);font-family:var(--font-ui);font-size:13px" role="status">Loading your map…</div>';
  STORE.checkInOutcome = '';          // live: nothing is pre-selected on the check-in
  STORE.currentScreen = '';           // live: no screen is showing yet, so loading the map cannot re-render (and re-route) a default one
  loadEngine();
  await liveBoot();
  const first = hashScreen();
  if (first === 'maps' && hashLens()) STORE.mapsView = hashLens();
  renderScreen(first || defaultLiveScreen());
});
