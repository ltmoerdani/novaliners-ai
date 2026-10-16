/* Shell helpers shared by every AppShell screen: user chip, "All maps" popover, redo diagnosis. */

function userInitial() {
  if (IS_DEMO) {
    const p = STORE.currentPersona;
    return p === 'rina' ? 'R' : (p === 'arif' ? 'A' : (p === 'bayu' ? 'B' : 'D'));
  }
  return 'Y';
}
function userName() {
  if (IS_DEMO) {
    const p = STORE.currentPersona;
    return p === 'rina' ? 'Rina W.' : (p === 'arif' ? 'Arif P.' : (p === 'bayu' ? 'Bayu K.' : 'Dimas A.'));
  }
  return 'You';
}

/* A map = the first session of a chain (follow-up cycles are linked sessions), and only this browser's own maps. */
function liveMapRoots() {
  return (LIVE.maps || []).filter(m => m.user_id === LIVE.userId && !m.prior_session_id);
}

/* "All maps" = this user's revenue maps. */
let mapsPopoverOpen = false;
function toggleMapsPopover(e) {
  if (e) e.stopPropagation();
  if (IS_DEMO) { openStartPage(); return; }
  mapsPopoverOpen = !mapsPopoverOpen;
  if (mapsPopoverOpen) liveRefreshMaps().then(() => { if (mapsPopoverOpen) renderScreen(STORE.currentScreen); });
  renderScreen(STORE.currentScreen);
}
function renderMapsPopover() {
  if (IS_DEMO || !mapsPopoverOpen) return '';
  const all = liveMapRoots();
  const inChain = m => LIVE.chain.includes(m.session_id);
  // current map first (whatever its state), then the other finished maps, newest first
  const rows = all.filter(inChain).slice(0, 1).concat(all.filter(m => !inChain(m) && m.has_diagnosis)).slice(0, 8);
  const item = m => {
    const active = LIVE.chain.includes(m.session_id);
    const title = brief(m.goal_text || 'Untitled map', 46);
    const date = new Date((m.created_ts || 0) * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    return `<button class="project-dropdown-item ${active ? 'active' : ''}" onclick="loadMapSession('${esc(m.session_id)}')">
      <span class="project-dot" style="background:${m.has_diagnosis ? 'var(--open-line)' : 'var(--notyet-line)'}"></span>
      <span style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(title)}</span>
      <span style="font-weight:500;color:var(--ink-3);font-size:11px">${esc(date)}</span>
      ${active ? '<span class="project-badge">CURRENT</span>' : ''}
    </button>`;
  };
  return `<div class="project-dropdown-menu" style="top:46px;left:96px;right:auto;width:340px" onclick="event.stopPropagation()">
    ${rows.length ? rows.map(item).join('') : '<div style="padding:8px 10px;font-size:12px;color:var(--ink-3)">No other maps yet.</div>'}
    <button class="project-dropdown-item" style="border-top:1px solid var(--border);border-radius:0 0 6px 6px;margin-top:2px" onclick="openStartPage()">+ New map</button>
  </div>`;
}

async function loadMapSession(sid) {
  mapsPopoverOpen = false;
  if (sid === LIVE.sid && LIVE.artifact) { renderScreen('state'); return; }
  showToast('Opening that map…', '', '');
  try {
    LIVE.chain = [];                       // force a fresh look-up of that map's own record
    await liveLoadSession(sid);
    renderScreen(LIVE.artifact ? 'state' : '02');
  } catch (e) {
    showToast('Could not open that map: ' + e.message, '', '', 'error');
  }
}

function startNewMap() {
  mapsPopoverOpen = false;
  liveForget();
  STORE.intakePrompt = '';
  renderScreen('01');
}

/* Start page as home. Nothing is discarded: the current map stays saved and one click away from there
   (the v11 sidebar lists it; a paused interview reopens the interview). It is only replaced once a new goal is submitted. */
function openStartPage() {
  mapsPopoverOpen = false;
  renderScreen('01');
  if (!IS_DEMO) liveRefreshMaps();   // the sidebar's map list reads LIVE.maps on the next render
}

function redoDiagnosis() {
  if (IS_DEMO) { renderScreen('02'); return; }
  openStartPage();
}

/* Close popovers when clicking elsewhere */
window.addEventListener('click', () => {
  if (mapsPopoverOpen) { mapsPopoverOpen = false; renderScreen(STORE.currentScreen); }
  if (STORE.ctxMenuOpen) setV11CtxMenu(false);
});

/* ==========================================================================
   V11 SHELL: the product navigation (internal-docs, D3 and D5).
   Five destinations in the top bar, the workspace (maps, account, settings) in the left rail, one page-header
   grammar. Ported from Revenue Navigation v11.dc.html (lines 3362-3684); the v9 sidebar shell was removed
   in the legacy cleanup (2026-10-15) — renderAppShell (ui-kit.js) now delegates here unconditionally.
   Demo mode and live mode share this code. Only the data differs (v11MapList, v11StatusParts).
   ========================================================================== */
const MAP_COLORS = ['var(--open-line)', 'var(--notyet-line)', 'var(--test-line)', 'var(--stop-fg)', 'var(--violet)', 'var(--open-line-2)', 'var(--indigo-fg)'];
const V11_ICONS = {
  state: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/></svg>',
  maps: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="5" r="2.2"/><path d="M8 17.5c6-2 4.5-7.5 8-11"/><circle cx="12.5" cy="12" r="1.4" fill="currentColor" stroke="none"/></svg>',
  moves: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><polyline points="10 8.5 15.5 12 10 15.5"/></svg>',
  journey: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 17 9 11 13 14 21 6"/><polyline points="15 6 21 6 21 12"/></svg>',
  talk: '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8.5 8.5 0 0 1-8.5 8.5c-1.6 0-3.1-.4-4.4-1.2L3 21l1.7-5.1A8.5 8.5 0 1 1 21 12z"/></svg>',
  plus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  settings: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h0a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55h0a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v0a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/></svg>',
  collapse: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/></svg>',
  expand: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg>'
};
/* A destination owns the scenes that read as its parts. The table only decides which tab is current. */
const V11_DESTINATIONS = [
  { id: 'state', label: 'State', go: "goDestination('state')", screens: ['state', '03', '03-low', '03-blocked', '10', '13', '15', '24'] },
  { id: 'maps', label: 'Maps', go: "goDestination('maps')", screens: ['maps'] },
  { id: 'moves', label: 'Moves', go: "goDestination('moves')", screens: ['moves', '05', '06a', '06b', '12', '14', '20', '22'] },
  { id: 'journey', label: 'Journey', go: "goDestination('journey')", screens: ['journey', '16', '23'] },
  { id: 'talk', label: 'Talk', go: "goDestination('talk')", screens: ['talk', '02', 'dx'] }
];
function activeDestination(screenId) {
  const s = String(screenId || '');
  const hit = V11_DESTINATIONS.find(d => d.screens.includes(s));
  if (hit) return hit.id;
  if (/^task-|^04-|^03-/.test(s)) return s.startsWith('03-') ? 'state' : 'moves';
  return null;
}
function goDestination(id) {
  const map = {
    state: () => renderScreen('state'),
    maps: () => { STORE.mapsView = 'landscape'; renderScreen('maps'); },   // entering Maps always lands on Landscape; the selected path is kept
    moves: () => renderScreen('moves'),
    journey: () => renderScreen('journey'),
    talk: () => { STORE.talkAbout = STORE.talkAboutNext || null; STORE.talkAboutNext = null; renderScreen('talk'); }
  };
  const render = map[id] || map.state;
  const from = activeDestination(STORE.currentScreen);
  // The white tab glides from where it was to where it lands (FLIP). It sits under the labels, so it never covers them.
  const old = document.querySelector('.v11-nav-pill');
  const oldBox = old ? old.getBoundingClientRect() : null;
  const go = () => {
    render();
    const now = document.querySelector('.v11-nav-pill');
    if (!oldBox || !now || !now.animate) return;
    const box = now.getBoundingClientRect();
    if (Math.abs(oldBox.left - box.left) < 1) return;
    now.animate([{ transform: `translateX(${oldBox.left - box.left}px)`, width: oldBox.width + 'px' }, { transform: 'translateX(0)', width: box.width + 'px' }],
      { duration: 380, easing: 'cubic-bezier(0.22, 0.8, 0.3, 1)' });
  };
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) { render(); return; }
  if (!document.startViewTransition || !from || from === id || !document.getElementById('v11-main')) { go(); return; }
  const order = V11_DESTINATIONS.map(d => d.id);
  const tab = (from === 'moves' && id === 'maps') || (from === 'maps' && id === 'moves');
  document.documentElement.dataset.nav = tab ? 'tab' : (order.indexOf(id) >= order.indexOf(from) ? 'fwd' : 'back');
  document.startViewTransition(go);
}
/* The rail only pushes the content above 1180; below that, expanded floats over it (≤900: a drawer). */
function v11Docked() { return window.innerWidth > 1180; }
function toggleSidebar() {
  const open = !STORE.sidebarExpanded;
  STORE.sidebarExpanded = open;
  if (v11Docked()) { try { localStorage.setItem('nova.v11.sidebar', open ? 'expanded' : 'rail'); } catch (e) { /* storage unavailable: the preference just does not persist */ } }
  if (open) STORE.settingsMenuOpen = false;
  const slot = document.getElementById('v11-side-slot');
  const side = document.getElementById('v11-sidebar');
  if (!slot || !side) return;
  slot.classList.toggle('expanded', open);
  side.classList.toggle('expanded', open);
  const set = document.getElementById('v11-settings-menu');
  if (set) { set.hidden = true; set.classList.toggle('rail', !open); }
  const sb = document.getElementById('v11-settings-btn');
  if (sb) { sb.className = (open ? 'v11-settings-item' : 'v11-rail-btn') + (ENGINE.status === 'error' ? ' has-alert' : ''); sb.setAttribute('aria-expanded', 'false'); }
  document.querySelectorAll('.v11-topbar-map').forEach(b => b.setAttribute('aria-expanded', String(open)));
  hideV11Tip();
  // Canvases refit after the width transition; keyboard focus stays on the control the user used.
  setTimeout(() => { if (typeof v12Mount === 'function') v12Mount(); }, 230);
  const next = open ? side.querySelector('.v11-side-toggle:not(.v11-only-collapsed)') : side.querySelector('.v11-side-toggle.v11-only-collapsed');
  if (next) next.focus({ preventScroll: true });
}
function toggleV11Settings(event) {
  if (event) event.stopPropagation();
  STORE.settingsMenuOpen = !STORE.settingsMenuOpen;
  hideV11Tip();
  const menu = document.getElementById('v11-settings-menu');
  if (menu) menu.hidden = !STORE.settingsMenuOpen;
  const btn = document.getElementById('v11-settings-btn');
  if (btn) btn.setAttribute('aria-expanded', String(!!STORE.settingsMenuOpen));
}
function closeV11Settings() {
  if (!STORE.settingsMenuOpen) return;
  STORE.settingsMenuOpen = false;
  const menu = document.getElementById('v11-settings-menu');
  if (menu) menu.hidden = true;
  const btn = document.getElementById('v11-settings-btn');
  if (btn) btn.setAttribute('aria-expanded', 'false');
}
window.addEventListener('click', closeV11Settings);
window.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  closeV11Settings();
  if (STORE.ctxMenuOpen) setV11CtxMenu(false, true);
});

function mapInitial(name) { return String(name || '?').trim().charAt(0).toUpperCase(); }
function escAttr(t) { return String(t).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }

/* The maps in the rail. One tile per map. Demo: the four sample workspaces of the prototype. Live: this user's own maps
   (the first session of each chain), the open one first even before its diagnosis exists. Nothing here is invented. */
const DEMO_MAPS = [
  { key: 'dimas', name: 'Brand Strategy Studio', color: 'var(--open-line)' },
  { key: 'rina', name: "Rina's Craft Studio", color: 'var(--notyet-line)' },
  { key: 'arif', name: "Arif's Brand Consulting", color: 'var(--test-line)' },
  { key: 'bayu', name: "Bayu's Design Studio", color: 'var(--stop-fg)' }
];
function v11MapList() {
  if (IS_DEMO) {
    const cur = STORE.currentPersona || 'dimas';
    return DEMO_MAPS.map(m => ({ key: m.key, name: m.name, color: m.color, current: m.key === cur, sub: m.key === cur ? v11MapSub() : '', open: `switchToMap('${m.key}')` }));
  }
  const rows = [];
  if (LIVE.sid) {
    /* Interview without an artifact = a paused interview: its tile continues the interview, not Start.
       Tile name: the map title when the artifact belongs to this session; if the artifact still belongs to another map, show the new goal text. */
    const paused = !LIVE.artifact || (LIVE.artifact.session_id && LIVE.artifact.session_id !== LIVE.sid);
    rows.push({ key: LIVE.chain[0] || LIVE.sid, name: paused ? brief(LIVE.goalText || 'New map', 38) : liveGoalTitle(), current: true, sub: v11MapSub(), open: paused ? "renderScreen('02')" : "goDestination('state')" });
  }
  liveMapRoots().filter(m => m.has_diagnosis && m.session_id !== LIVE.sid && !LIVE.chain.includes(m.session_id)).slice(0, 7).forEach(m => {
    rows.push({ key: m.session_id, name: brief(m.goal_text || 'Untitled map', 38), current: false, sub: '', open: `loadMapSession('${esc(m.session_id)}')` });
  });
  return rows.map((r, i) => Object.assign({ color: MAP_COLORS[i % MAP_COLORS.length] }, r));
}
function v11MapSub() {
  if (IS_DEMO) { const g = getActiveProjectInfo(); return g.target ? `Goal · ${g.target} a month` : 'Goal · not set yet'; }
  const g = liveGoal();
  return g.target != null ? `Goal · ${fmtM(g.target)} a month` : 'Goal · not set yet';
}
function switchToMap(key) {
  if (!v11Docked()) STORE.sidebarExpanded = false;      // a floating rail closes once it has done its job
  STORE.restoreFocus = '.v11-ctx-trigger';              // focus returns to the switcher the person used
  if (IS_DEMO) {
    STORE.currentPersona = key;
    STORE.activeProject = key;
    STORE.mapsView = 'landscape';
    const ps = document.getElementById('persona-selector');
    if (ps) ps.value = key;
  }
  renderScreen('state');   // State is the landing destination of a map (int 08 §5.1)
}
/* Status pill: reads only what the map records. "of N" appears only when a deadline is on record, the goal part only
   when a goal is. Never a default (int 10 §6.4, 06 §12.2 R2). */
function v11StatusParts() {
  if (IS_DEMO) {
    const tl = getTimeline(), rs = useRoadmapStore.getState();
    const horizon = rs.horizonDays != null ? rs.horizonDays : GOAL_DAY;
    return { day: tl.day, horizon, goal: rs.goalRp ? Number(rs.goalRp) : null, earned: rs.earned || 0 };
  }
  const g = liveGoal();
  const parsed = Number(((LIVE.state || {}).goal || {}).deadline_days);
  const horizon = Number(LIVE.horizonOverride) || (parsed >= 14 && parsed <= 120 ? parsed : null);
  const last = LIVE.checkins[LIVE.checkins.length - 1];
  const earned = last && last.rp != null ? last.rp : (g.current != null ? g.current : null);   // null = no income on record
  return { day: liveDay(), horizon, goal: g.target != null ? g.target : null, earned };   // engine amounts are millions of rupiah
}
/* v11StatusHtml (the top-bar pill) was removed on 2026-10-11 — the data lives in the State context panel (int 12). */

/* The rail (workspace / map context): brand · maps · settings. Destinations are NOT here, they belong to the top bar. */
function renderV11Sidebar() {
  const expanded = !!STORE.sidebarExpanded;
  const maps = v11MapList();
  const tile = m => `<span class="v11-map-tile" style="background:${m.color}" aria-hidden="true">${escAttr(mapInitial(m.name))}</span>`;
  const accountName = IS_DEMO ? (STORE.currentPersona === 'rina' ? 'Rina W.' : STORE.currentPersona === 'arif' ? 'Arif S.' : STORE.currentPersona === 'bayu' ? 'Bayu K.' : 'Dimas A.') : userName();
  const newMap = IS_DEMO ? 'openNewMapIntake()' : 'openStartPage()';
  const alert = ENGINE.status === 'error' ? ' has-alert' : '';
  const t = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
  const sun = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const moon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  return `
  <div class="v11-side-slot${expanded ? ' expanded' : ''}" id="v11-side-slot">
  <aside class="v11-sidebar${expanded ? ' expanded' : ''}" id="v11-sidebar" aria-label="Workspace">
    <div class="v11-side-brand">
      <button type="button" class="v11-brand" onclick="openStartPage()" aria-label="NOVALINERS, go home (start / new map)">
        <img class="v11-brand-logo v11-only-expanded" src="/static/assets/novaliners-logo.png" alt="">
        <img class="v11-brand-mark v11-only-collapsed" src="/static/assets/novaliners-mark.png" alt="">
      </button>
      <button type="button" class="v11-side-toggle v11-only-expanded" onclick="toggleSidebar()" data-tip="" aria-label="Collapse sidebar" aria-expanded="true">${V11_ICONS.collapse}</button>
      <button type="button" class="v11-side-toggle v11-only-collapsed" onclick="toggleSidebar()" data-tip="Expand sidebar" aria-label="Expand sidebar" aria-expanded="false">${V11_ICONS.expand}</button>
    </div>

    <div class="v11-section-label v11-only-expanded" id="v11-maps-label">Your maps</div>
    <div class="v11-map-list v11-only-expanded" aria-labelledby="v11-maps-label">
      ${maps.length ? maps.map(m => `
      <button type="button" class="v11-map-item${m.current ? ' active' : ''}" onclick="${m.open}" ${m.current ? 'aria-current="true"' : ''} title="${escAttr(m.name)}">
        ${tile(m)}
        <span class="v11-map-item-text"><span class="v11-map-item-name">${escAttr(m.name)}</span>${m.sub ? `<span class="v11-map-item-sub">${escAttr(m.sub)}</span>` : ''}</span>
      </button>`).join('') : '<p class="v11-map-empty">No maps yet.</p>'}
    </div>
    <button type="button" class="v11-new-map-btn v11-only-expanded" onclick="${newMap}">${V11_ICONS.plus} New map</button>

    <div class="v11-rail-maps v11-only-collapsed">
      ${maps.map(m => `
      <div class="v11-rail-item"><button type="button" class="v11-rail-btn${m.current ? ' active' : ''}" onclick="${m.open}" ${m.current ? 'aria-current="true"' : ''} data-tip="${escAttr(m.name)}" aria-label="${escAttr(m.name)}${m.current ? ' (current map)' : ''}">${tile(m)}</button></div>`).join('')}
      <div class="v11-rail-item"><button type="button" class="v11-rail-btn is-add" onclick="${newMap}" data-tip="New map" aria-label="New map">${V11_ICONS.plus}</button></div>
    </div>

    <div class="v11-side-footer">
      <button type="button" class="v11-account" onclick="toggleV11Settings(event)" aria-haspopup="true" ${expanded ? '' : 'data-tip="' + escAttr(accountName) + '"'} aria-label="Account: ${escAttr(accountName)}" title="${escAttr(accountName)}">
        <span class="v11-account-avatar" aria-hidden="true">${escAttr(mapInitial(accountName))}</span>
        <span class="v11-account-text v11-only-expanded">
          <span class="v11-account-name">${escAttr(accountName)}</span>
          <span class="v11-account-sub">${IS_DEMO ? 'Sample workspace' : 'On this device'}</span>
        </span>
      </button>
      <div class="v11-settings-row">
        <button type="button" id="v11-settings-btn" class="${expanded ? 'v11-settings-item' : 'v11-rail-btn'}${alert}" onclick="toggleV11Settings(event)" aria-haspopup="true" aria-expanded="${!!STORE.settingsMenuOpen}" aria-label="Settings" ${expanded ? '' : 'data-tip="Settings"'}>
          ${V11_ICONS.settings}<span class="v11-only-expanded">Settings</span>
        </button>
        <div class="v11-settings-menu${expanded ? '' : ' rail'}" id="v11-settings-menu" ${STORE.settingsMenuOpen ? '' : 'hidden'} role="group" aria-label="Settings" onclick="event.stopPropagation()">
          <div class="settings-title">Appearance</div>
          <div class="theme-seg" role="group" aria-label="Theme">
            <button type="button" data-theme-opt="light" aria-pressed="${t === 'light'}" onclick="setTheme('light')">${sun} Light</button>
            <button type="button" data-theme-opt="dark" aria-pressed="${t === 'dark'}" onclick="setTheme('dark')">${moon} Dark</button>
          </div>
          <div class="settings-engine" id="engine-settings">${renderEngineSettings()}</div>
          ${IS_DEMO ? `<button type="button" class="v11-settings-item" onclick="STORE.settingsMenuOpen=false;resetSimulation();showToast('Demo state reset for this map.')">Reset demo state</button>` : ''}
        </div>
      </div>
    </div>
  </aside>
  </div>
  <div class="v11-side-scrim" onclick="toggleSidebar()"></div>`;
}
/* Global destinations: the top bar's one job. Same component at every width (wraps to a second row ≤900). */
function renderV11TopNav() {
  const dest = activeDestination(STORE.currentScreen);
  return `<nav class="v11-topnav" aria-label="Destinations">
    ${V11_DESTINATIONS.map(d => `<button type="button" class="v11-topnav-item" onclick="STORE.restoreFocus='.v11-topnav-item[aria-current]';${d.go}" ${dest === d.id ? 'aria-current="page"' : ''}>${dest === d.id ? '<span class="v11-nav-pill" aria-hidden="true"></span>' : ''}${d.label}</button>`).join('')}
  </nav>`;
}
/* Page header grammar, one for every destination:
     EYEBROW (destination · current map)  /  TITLE  /  lead  /  local control (optional, below the header)
   The destination is named by the top bar; the eyebrow only echoes it and adds the map. */
function v11Eyebrow(dest, extra) {
  const cur = v11MapList().find(m => m.current);
  return `<div class="v11-eyebrow"><span>${dest}</span><span class="v11-eyebrow-sep" aria-hidden="true">·</span><span class="v11-eyebrow-map"><span class="v11-eyebrow-dot" style="background:${cur ? cur.color : 'var(--ink-muted)'}"></span>${escAttr(getActiveProjectInfo().name)}</span>${IS_DEMO ? '<span class="v11-eyebrow-sample"><span aria-hidden="true">·</span> Sample workspace</span>' : ''}${extra || ''}</div>`;
}
function v11PageHead(o) {
  /* ── ported verbatim from Revenue Navigation v11.dc.html (design @HEAD): the page head is
     title + lead only — the destination eyebrow is gone from the design (context lives in the
     top-bar route switcher), and the text is always wrapped in .v11-pagehead-text. ── */
  return `<header class="v11-pagehead">
    <div class="v11-pagehead-text">
      ${o.titleHtml || `<h1 class="serif-heading">${o.title}</h1>`}
      ${o.lead ? `<p class="v11-lead">${o.lead}</p>` : ''}
    </div>
    ${o.actions ? `<div class="v11-pagehead-actions">${o.actions}</div>` : ''}
  </header>`;
}
/* Rail panel hide/show (ala Claude/Perplexity): state persists across navigation via localStorage. */
function v11RailHidden() { try { return localStorage.getItem('v11-rail-hidden') === '1'; } catch (e) { return false; } }
function applyRailHidden() {
  document.body.classList.toggle('rail-hidden', v11RailHidden());
  const b = document.querySelector('.v11-rail-toggle');
  if (!b) return;
  b.setAttribute('aria-expanded', String(!v11RailHidden()));
  /* On narrow screens the topbar can wrap (its height changes): put the button right below it, not at a fixed offset */
  const tb = document.querySelector('.v11-topbar');
  if (tb && window.innerWidth <= 1100) b.style.top = (tb.getBoundingClientRect().bottom + 12) + 'px';
  else b.style.top = '';
}
function toggleDestRail() {
  try { localStorage.setItem('v11-rail-hidden', v11RailHidden() ? '0' : '1'); } catch (e) { /* private mode: hide for this page only */ }
  document.body.classList.toggle('rail-hidden');
  const b = document.querySelector('.v11-rail-toggle');
  if (b) { b.setAttribute('aria-expanded', String(!document.body.classList.contains('rail-hidden'))); b.setAttribute('aria-label', `${document.body.classList.contains('rail-hidden') ? 'Show' : 'Hide'} the context panel`); }
}
/* ==========================================================================
   Route switcher (phase-1 shell): the mark, a hairline and the current map live in the top bar's left
   cell; the popover carries search (⌘K), the filters, the map list and a sticky "Start new map" footer.
   This replaces the retired left rail — renderV11Sidebar() is no longer rendered (doc 21 · follow-up).
   The data is v11MapList's, so demo workspaces and this device's own maps read through one code path.
   ========================================================================== */
function v11RouteGoalShort() {
  const g = getActiveProjectInfo();
  return g.target ? `${g.target}/mo` : '';
}
function setV11CtxMenu(open, refocus) {
  STORE.ctxMenuOpen = !!open;
  if (open && STORE.settingsMenuOpen) closeV11Settings();
  const menu = document.getElementById('v11-ctx-menu');
  const trig = document.querySelector('.v11-ctx-trigger');
  if (menu) menu.hidden = !open;
  if (trig) trig.setAttribute('aria-expanded', String(!!open));
  hideV11Tip();
  if (open && menu) {
    const q = document.getElementById('v11-ctx-q');
    if (q) q.value = '';
    v11CtxApply();
    if (q) q.focus({ preventScroll: true });
  } else if (refocus && trig) trig.focus({ preventScroll: true });
}
function setV11CtxFilter(f) {
  STORE.ctxFilter = f;
  document.querySelectorAll('.v11-ctx-pill').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === f)));
  v11CtxApply();
}
/* Search and filter run on the rendered list: a row shows when it matches the text and the pill. */
function v11CtxApply() {
  const menu = document.getElementById('v11-ctx-menu');
  if (!menu) return;
  const q = ((document.getElementById('v11-ctx-q') || {}).value || '').trim().toLowerCase();
  const f = STORE.ctxFilter || 'all';
  let shown = 0;
  menu.querySelectorAll('.v11-ctx-list > .v11-ctx-item').forEach(el => {
    const ok = (f === 'all' || el.dataset.kind === f) && (!q || el.dataset.q.includes(q));
    el.hidden = !ok;
    if (ok) shown++;
  });
  const grp = menu.querySelector('[data-group="maps"]');
  if (grp) grp.hidden = !!q || f !== 'all' || !menu.querySelector('.v11-ctx-list > .v11-ctx-item:not(.is-on):not([hidden])');
  const empty = menu.querySelector('.v11-ctx-empty');
  if (empty) empty.hidden = shown > 0;
}
function renderV11ContextSwitcher(proj) {
  const maps = v11MapList();
  const cur = maps.find(m => m.current);
  const others = maps.filter(m => !m.current);
  const open = !!STORE.ctxMenuOpen;
  const goal = v11RouteGoalShort();
  /* A live interview without its own artifact is still being discovered — the record says so, not a guess. */
  const paused = !IS_DEMO && !!LIVE.sid && (!LIVE.artifact || (LIVE.artifact.session_id && LIVE.artifact.session_id !== LIVE.sid));
  const kindOf = m => (m.current ? 'active' : (IS_DEMO ? 'sample' : 'saved'));
  const wordOf = m => (m.current ? (paused ? 'In discovery' : 'Current') : (IS_DEMO ? 'Sample' : 'Evaluated'));
  const item = m => {
    const on = m.current;
    const q = `${m.name} ${m.sub || ''}`.toLowerCase();
    return `<button type="button" role="menuitemradio" aria-checked="${on}" class="v11-ctx-item${on ? ' is-on' : ''}" data-kind="${kindOf(m)}" data-q="${escAttr(q)}" onclick="event.stopPropagation();setV11CtxMenu(false);${m.open}">
      <span class="v11-ctx-dot" style="--dot:${m.color || 'var(--ink-muted)'}" aria-hidden="true"></span>
      <span class="v11-ctx-item-text"><span class="v11-ctx-item-name">${escAttr(m.name)}</span>${on && m.sub ? `<span class="v11-ctx-item-sub">${escAttr(m.sub)}</span>` : ''}</span>
      <span class="v11-ctx-badge${on ? ' is-on' : ''}">${wordOf(m)}</span>
    </button>`;
  };
  const pills = IS_DEMO
    ? [['all', 'All'], ['active', 'Active'], ['sample', 'Samples']]
    : [['all', 'All'], ['active', 'Active'], ['saved', 'Saved']];
  const pill = ([f, label]) => `<button type="button" class="v11-ctx-pill" data-filter="${f}" aria-pressed="${(STORE.ctxFilter || 'all') === f}" onclick="event.stopPropagation();setV11CtxFilter('${f}')">${label}</button>`;
  return `
  <div class="v11-ctx">
    <button type="button" class="v11-ctx-home" onclick="openStartPage()" aria-label="NOVALINERS, go home (start / new map)"><img src="/static/assets/novaliners-mark.png" alt=""></button>
    <span class="v11-ctx-slash" aria-hidden="true">/</span>
    <button type="button" class="v11-ctx-trigger" onclick="event.stopPropagation();setV11CtxMenu(!STORE.ctxMenuOpen)" aria-haspopup="menu" aria-expanded="${open}" aria-controls="v11-ctx-menu" aria-label="Map: ${escAttr(proj.name)}${goal ? ', ' + goal : ''}. Switch map">
      <span class="v11-ctx-dot" aria-hidden="true"></span>
      <span class="v11-ctx-name">${escAttr(cur ? cur.name : proj.name)}</span>${goal ? `<span class="v11-ctx-goal">· ${escAttr(goal)}</span>` : ''}
      <svg class="v11-ctx-chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
    </button>
    <div class="v11-ctx-menu" id="v11-ctx-menu" aria-label="Switch map" ${open ? '' : 'hidden'} onclick="event.stopPropagation()">
      <div class="v11-ctx-head">
        <label class="v11-ctx-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
          <input type="text" id="v11-ctx-q" placeholder="Search maps…" autocomplete="off" spellcheck="false" aria-label="Search maps" aria-controls="v11-ctx-list" oninput="v11CtxApply()">
          <kbd aria-hidden="true">⌘K</kbd>
        </label>
        <div class="v11-ctx-pills" role="group" aria-label="Filter maps">${pills.map(pill).join('')}</div>
      </div>
      <div class="v11-ctx-list" id="v11-ctx-list" role="menu" aria-label="Maps">
        ${cur ? item(cur) : ''}
        <div class="v11-ctx-group" data-group="maps" role="presentation">${IS_DEMO ? 'Sample workspaces' : 'Other maps'}</div>
        ${others.map(item).join('')}
        <p class="v11-ctx-empty" role="presentation" hidden>No maps match.</p>
        <!-- ARIA 1.2: a menuitem must live inside a menu. The footer is therefore a group inside the menu
             (it scrolls with the list; the list is short and capped at 280px). -->
        <div class="v11-ctx-foot" role="group" aria-label="Map actions">
          <button type="button" role="menuitem" class="v11-ctx-new" onclick="event.stopPropagation();setV11CtxMenu(false);${IS_DEMO ? 'openNewMapIntake()' : 'openStartPage()'}">${V11_ICONS.plus}<span>Start new map</span></button>
        </div>
      </div>
    </div>
  </div>`;
}
/* ⌘K / Ctrl+K opens the switcher on its search; the arrows walk its rows. */
document.addEventListener('keydown', e => {
  if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'k' || !document.querySelector('.v11-ctx-trigger')) return;
  e.preventDefault();
  setV11CtxMenu(!(STORE.ctxMenuOpen && document.activeElement === document.getElementById('v11-ctx-q')), true);
});
document.addEventListener('keydown', e => {
  const menu = document.getElementById('v11-ctx-menu');
  if (!menu || menu.hidden || !menu.contains(document.activeElement) || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
  if (document.activeElement.id === 'v11-ctx-q' && (e.key === 'Home' || e.key === 'End')) return;   // caret keys stay the input's
  const items = [...menu.querySelectorAll('#v11-ctx-q, .v11-ctx-list button, .v11-ctx-new')].filter(b => b.offsetParent !== null);
  const i = items.indexOf(document.activeElement);
  const n = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
  items[n].focus(); e.preventDefault();
});
/* --------------------------------------------------------------------------
   Split-pane inspector (phase-1): Hide is a 28px control at the panel's top-right; Hidden leaves a
   "Show details" pill on the page header row. The column opens and closes over 200ms and the canvases
   refit once it has settled; reduced motion skips the slide.
   -------------------------------------------------------------------------- */
const WS_PANEL_ICON = {
  close: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/><path d="m8 9 3 3-3 3"/></svg>',
  open: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/><path d="m11 9-3 3 3 3"/></svg>'
};
function wsPanelHideBtn(cls, panelId, setter, what) {
  return `<button type="button" class="ws-panel-hide ${cls}" data-panel-toggle aria-controls="${panelId}" aria-label="Hide ${what}" data-tip="Hide panel (⌘.)" title="Hide panel (⌘.)" onclick="wsPanelSlideOut(this, () => ${setter}(false))">${WS_PANEL_ICON.close}</button>`;
}
function wsPanelShowBtn(cls, panelId, setter, what) {
  return `<button type="button" class="ws-panel-show ${cls}" data-panel-toggle aria-controls="${panelId}" aria-expanded="false" aria-label="Show ${what}" data-tip="Show panel (⌘.)" data-tip-pos="below" onclick="hideV11Tip();STORE.wsPanelEnter=true;${setter}(true)">${WS_PANEL_ICON.open}<span>Show details</span></button>`;
}
/* The panel slides out, then the page re-lays without it; reduced motion skips the slide. */
function wsPanelSlideOut(btn, done) {
  hideV11Tip();
  const aside = btn.closest('aside');
  const root = aside && aside.parentElement;
  if (!aside || !root || mapsReduced() || window.innerWidth <= 1000) { done(); wsPanelRefit(); return; }
  root.classList.add('is-panel-anim');
  aside.classList.add('is-leaving');
  requestAnimationFrame(() => root.classList.add('is-panel-shut'));   // the main pane grows as the panel's column closes
  setTimeout(() => { done(); wsPanelRefit(); }, 210);
}
/* Canvases measure their host: refit them once the columns have settled. */
function wsPanelRefit() { requestAnimationFrame(() => { if (typeof v12Mount === 'function') v12Mount(); }); }
/* A panel that was just brought back slides in. */
function wsPanelMarkEnter() {
  if (!STORE.wsPanelEnter) return;
  STORE.wsPanelEnter = false;
  const btn = document.querySelector('.ws-panel-hide');
  const aside = btn && btn.closest('aside');
  const root = aside && aside.parentElement;
  if (!aside || !root || mapsReduced() || window.innerWidth <= 1000) return;
  root.classList.add('is-panel-shut');
  void root.offsetWidth;                                              // start from a closed column…
  root.classList.add('is-panel-anim');
  aside.classList.add('is-entering');
  requestAnimationFrame(() => root.classList.remove('is-panel-shut')); // …and let it open
  setTimeout(() => { root.classList.remove('is-panel-anim'); wsPanelRefit(); }, 230);
}
document.addEventListener('keydown', e => {
  if (!(e.metaKey || e.ctrlKey) || e.key !== '.') return;
  const b = document.querySelector('[data-panel-toggle]');
  if (b) { e.preventDefault(); b.click(); }
});
/* Moves' inspector: same fold as State's. renderScreen('moves') does not reset STORE.viewStep,
   so folding the panel never changes which move is on screen. */
function setMovesSide(open) {
  STORE.movesSideClosed = !open;
  STORE.restoreFocus = '.mv-side-toggle';
  renderScreen('moves');
  requestAnimationFrame(wsPanelMarkEnter);
}
function setStateSide(open) {
  STORE.stateSideClosed = !open;
  STORE.restoreFocus = '.st-side-toggle';
  renderScreen('state');
  requestAnimationFrame(wsPanelMarkEnter);
}
/* Journey's inspector, same grammar as State's (doc 21 §3): the on-hold panel folds away and leaves the
   "Show details" pill on the page header row. wsPanelMarkEnter plays the shared 200ms slide-in on return. */
function setJourneySide(open) {
  STORE.journeySideClosed = !open;
  STORE.restoreFocus = '.j-side-toggle';
  renderScreen('journey');
  requestAnimationFrame(wsPanelMarkEnter);
}
/* One avatar at the bar's far right; its menu holds the settings — there is no separate gear. */
function renderV11TopbarAccount() {
  const name = userName();
  const t = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
  const sun = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const moon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  const alert = ENGINE.status === 'error' ? ' has-alert' : '';
  return `
  <div class="v11-tb-account">
    <button type="button" id="v11-settings-btn" class="v11-tb-avatar${alert}" onclick="toggleV11Settings(event)" aria-haspopup="true" aria-expanded="${!!STORE.settingsMenuOpen}" aria-label="${escAttr(name)}, account and settings" data-tip="${escAttr(name)}">${escAttr(mapInitial(name))}</button>
    <div class="v11-settings-menu v11-tb-menu" id="v11-settings-menu" ${STORE.settingsMenuOpen ? '' : 'hidden'} role="group" aria-label="Settings" onclick="event.stopPropagation()">
      <div class="v11-profile-menu-info">
        <span class="v11-profile-menu-name">${escAttr(name)}</span>
        <span class="v11-profile-menu-sub">${IS_DEMO ? 'Sample account · no sign-in' : 'On this device'}</span>
      </div>
      <div class="v11-profile-menu-div"></div>
      <div class="settings-title">Appearance</div>
      <div class="theme-seg" role="group" aria-label="Theme">
        <button type="button" data-theme-opt="light" aria-pressed="${t === 'light'}" onclick="setTheme('light')">${sun} Light</button>
        <button type="button" data-theme-opt="dark" aria-pressed="${t === 'dark'}" onclick="setTheme('dark')">${moon} Dark</button>
      </div>
      <div class="settings-engine" id="engine-settings">${renderEngineSettings()}</div>
      ${IS_DEMO ? `<button type="button" class="v11-settings-item" onclick="STORE.settingsMenuOpen=false;resetSimulation();showToast('Demo state reset for this map.')">Reset demo state</button>` : ''}
    </div>
  </div>`;
}
/* The v11 shell around a destination's content: switcher and tabs in the bar, the account at its far right.
   Start is a moment outside the workspace, so the tabs are not shown there (int 17 · one top bar, five tabs). */
function renderAppShellV11(activeNav, screenTitle, contentHtml) {
  const proj = getActiveProjectInfo();
  requestAnimationFrame(applyRailHidden);   // sync the panel state right after the shell is attached to the DOM
  const hideTopNav = !activeNav;
  return `
  <a class="v11-skip" href="#v11-main" onclick="document.getElementById('v11-main').focus();return false">Skip to content</a>
  <div class="shell-container">
    <div class="main-canvas-full">
      <header class="app-topbar v11-topbar">
        <div class="topbar-left">${renderV11ContextSwitcher(proj)}</div>
        ${hideTopNav ? '<div class="topbar-center-empty" aria-hidden="true"></div>' : renderV11TopNav()}
        <div class="topbar-right">${renderV11TopbarAccount()}</div>
      </header>
      ${contentHtml.includes('dest-rail') && !contentHtml.includes('has-panel-hide') ? `<button type="button" class="v11-rail-toggle" onclick="toggleDestRail()" aria-expanded="${!v11RailHidden()}" aria-controls="dest-rail" aria-label="${v11RailHidden() ? 'Show' : 'Hide'} the context panel" data-tip="Context panel"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 6 15 12 9 18"/></svg></button>` : ''}
      <main class="v11-main" id="v11-main" tabindex="-1">
        ${contentHtml}
      </main>
    </div>
  </div>`;
}
/* Rail tooltips: one delegated element, so the rail's overflow never clips it */
function hideV11Tip() { const t = document.getElementById('v11-tip'); if (t) t.classList.remove('show'); }
(function initV11Interactions() {
  const showTip = el => {
    let tip = document.getElementById('v11-tip');
    if (!tip) { tip = document.createElement('div'); tip.id = 'v11-tip'; tip.setAttribute('role', 'presentation'); document.body.appendChild(tip); }
    const text = el.getAttribute('data-tip');
    if (!text || el.getAttribute('aria-expanded') === 'true') return;   // an open menu speaks for itself
    const r = el.getBoundingClientRect();
    tip.textContent = text;
    tip.classList.add('show');
    /* Position: right of the element, but clamped to the viewport — a button at the right edge (e.g. rail toggle) uses the left side */
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = r.right + 10, y = r.top + r.height / 2 - th / 2;
    if (x + tw > window.innerWidth - 8) x = Math.max(8, r.left - tw - 10);
    y = Math.min(Math.max(8, y), window.innerHeight - th - 8);
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
    tip.style.transform = 'none';
  };
  document.addEventListener('mouseover', e => { const t = e.target.closest && e.target.closest('[data-tip]'); if (t) showTip(t); });
  document.addEventListener('mouseout', e => { if (e.target.closest && e.target.closest('[data-tip]')) hideV11Tip(); });
  document.addEventListener('focusin', e => { const t = e.target.closest && e.target.closest('[data-tip]'); if (t && e.target.matches(':focus-visible')) showTip(t); });
  document.addEventListener('focusout', hideV11Tip);
  /* Arrow / Home / End move focus inside the destination nav and the Maps lens switch */
  document.addEventListener('keydown', e => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    const group = e.target.closest && e.target.closest('.v11-topnav, .v11-view-switch');
    if (!group) return;
    const items = [...group.querySelectorAll('button')];
    const i = items.indexOf(e.target);
    if (i < 0) return;
    const n = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length;
    e.preventDefault();
    items[n].focus();
  });
})();
/* New map opens the intake; the current map stays saved. */
function openNewMapIntake() {
  if (!v11Docked()) STORE.sidebarExpanded = false;
  STORE.newMapFlow = true;
  openStartPage();
}

/* ==========================================================================
   Shared helpers of the v11 destinations (ported from the prototype): the map key, escaping, the two kinds of STOP,
   and the generic "why" drawer that State, Maps and Moves open.
   ========================================================================== */
/* One key per map: the sample workspace in demo mode, the first session of the chain in live mode. */
function v11MapKey() { return IS_DEMO ? (STORE.currentPersona || 'dimas') : (LIVE.chain[0] || LIVE.sid || 'map'); }
/* ── ported from Revenue Navigation v11.dc.html lines 9601-9601 ── */
function stratEsc(v) { return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }

/* ── ported from Revenue Navigation v11.dc.html lines 9233-9238 ── */
const STOP_BY_WORD = { numbers: ' · BY THE EVIDENCE', you: ' · BY YOU', fit: " · DOESN'T FIT" };
const STOP_BY_NOTE = {
  numbers: "What you've learned so far goes against this path. Meeting what it needs would open it again. The evidence decides, not effort.",
  you: "It isn't deleted. It stays on your map with everything you learned on it.",
  fit: "This isn't about effort. The route needs buyers you don't have yet."
};

/* ── ported from Revenue Navigation v11.dc.html lines 9270-9270 ── */
const STRAT_STATUS_FROM_DISPLAY = { OPEN: 'OPEN', 'TEST FIRST': 'TEST_FIRST', 'NOT YET': 'NOT_YET', STOP: 'STOP' };

/* ── ported from Revenue Navigation v11.dc.html lines 9951-9971 ── */
function stratPill(statusDisplay, stopSource) {
  const cls = (STRAT_STATUS_FROM_DISPLAY[statusDisplay] || 'NOT_YET').toLowerCase();
  const word = statusDisplay + (stopSource ? STOP_BY_WORD[stopSource === 'you' ? 'you' : 'numbers'] : '');
  return `<span class="status-pill ${cls}">${word}</span>`;
}
function openWhyDrawer(label, title, sub, bodyHtml) {
  document.getElementById('drawer-content').innerHTML = `
    <div class="rv-sheet">
      <div class="rv-sheet-head">
        <div>
          <div class="section-meta-label">${label}</div>
          <h2 class="serif-heading">${title}</h2>
          ${sub ? `<p class="rv-sheet-lead">${sub}</p>` : ''}
        </div>
        <button class="rv-x" onclick="closeDrawer()" aria-label="Close">✕</button>
      </div>
      ${bodyHtml}
    </div>`;
  const dc = document.getElementById('drawer-content');
  dc.setAttribute('role', 'dialog'); dc.setAttribute('aria-modal', 'true'); dc.setAttribute('aria-label', String(title).replace(/<[^>]*>/g, ''));
  document.getElementById('why-drawer').classList.add('open');
  overlayOpened('why-drawer');
}
