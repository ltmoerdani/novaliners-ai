/* UI kit */
/* Toast: small confirmation after an action */
let toastTimer = null;
function showToast(message, actionLabel, actionScreen, kind) {
  let el = document.getElementById('app-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'app-toast';
    el.className = 'app-toast';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    document.body.appendChild(el);
  }
  el.innerHTML = `
    <span class="app-toast-icon"${kind === 'error' ? ' style="background:var(--stop-fg)"' : (kind === 'neutral' ? ' style="background:var(--ink-3)"' : '')}>${kind === 'error' ? '!' : (kind === 'neutral' ? 'i' : '✓')}</span>
    <span>${esc(message)}</span>
    ${actionLabel ? `<button class="app-toast-action" onclick="hideToast();renderScreen('${actionScreen}')">${actionLabel}</button>` : ''}`;
  el.classList.remove('show');
  void el.offsetWidth;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, kind === 'error' ? 6000 : 4000);
}
function hideToast() {
  const el = document.getElementById('app-toast');
  if (el) el.classList.remove('show');
}

function toggleSidebarCollapse() {
  STORE.sidebarCollapsed = !STORE.sidebarCollapsed;
  renderScreen(STORE.currentScreen);
}

function toggleProjectDropdown(e) {
  if (e) e.stopPropagation();
  STORE.projectDropdownOpen = !STORE.projectDropdownOpen;
  renderScreen(STORE.currentScreen);
}

function selectProject(personaKey) {
  setPersona(personaKey);
}

function startIntakeFlow() {
  const ta = document.getElementById('start-textarea');
  if (ta && ta.value.trim()) {
    STORE.intakePrompt = ta.value.trim();
  }
  if (!IS_DEMO) { liveIntakeSubmit(STORE.intakePrompt); return; }
  renderScreen('02');
}

function appendPromptTag(tagText) {
  const ta = document.getElementById('start-textarea');
  if (!ta) return;
  const current = ta.value.trim();
  if (!current) {
    ta.value = tagText + ': ';
  } else {
    ta.value = current + '\n' + tagText + ': ';
  }
  ta.focus();
}

function toggleStarterScenarios() {
  const ta = document.getElementById('start-textarea');
  if (ta) STORE.intakePrompt = ta.value;
  STORE.showStarterScenarios = !STORE.showStarterScenarios;
  renderScreen('01');
}

function selectStarterScenario(text) {
  const ta = document.getElementById('start-textarea');
  if (ta) ta.value = text;
  STORE.intakePrompt = text;
  startIntakeFlow();
}

function copyTodayMsg(btn) {
  let text = "";
  if (STORE.currentScreen === '14') {
    text = "Hi Sari, sorry it took me a while to get back to you. I have started my brand strategy business. Could I send you a one-page summary?";
  } else {
    // Copy whatever message is shown in the same box as the button
    let el = btn;
    while (el && el.parentElement && !el.querySelector('[lang]')) el = el.parentElement;
    const msg = el && el.querySelector('[lang]');
    text = msg ? msg.innerText.trim() : '';
  }
  navigator.clipboard.writeText(text);
  if (btn) {
    const originalText = btn.innerHTML;
    btn.innerHTML = '✓ Copied!';
    btn.style.background = 'var(--open-bg)';
    btn.style.color = 'var(--open-fg)';
    btn.style.borderColor = 'var(--open-border)';
    setTimeout(() => {
      btn.innerHTML = originalText;
      btn.style.background = '';
      btn.style.color = '';
      btn.style.borderColor = '';
    }, 2500);
  }
}

function advanceCycle() {
  useRoadmapStore.getState().startCycle({ cycle: 3, earned: 34.5, moneySaved: 30 });
  alert('Starting the next check-in! Your income goal is now Rp60M a month.');
  renderScreen('04');
}

/* Close dropdown when clicking outside */
window.addEventListener('click', () => {
  if (STORE.projectDropdownOpen) {
    STORE.projectDropdownOpen = false;
    renderScreen(STORE.currentScreen);
  }
});
/* SVG Path Glyph Generator */
function getPathGlyph(status) {
  if (status === 'OPEN') {
    return `<svg width="44" height="12" viewBox="0 0 44 12" style="vertical-align:middle">
      <line x1="2" y1="6" x2="42" y2="6" stroke="var(--open-line)" stroke-width="3" stroke-linecap="round"/>
    </svg>`;
  } else if (status === 'TEST_FIRST') {
    return `<svg width="44" height="12" viewBox="0 0 44 12" style="vertical-align:middle">
      <line x1="2" y1="6" x2="42" y2="6" stroke="var(--test-line)" stroke-width="2.5" stroke-dasharray="1 6" stroke-linecap="round"/>
    </svg>`;
  } else if (status === 'NOT_YET') {
    return `<svg width="44" height="12" viewBox="0 0 44 12" style="vertical-align:middle">
      <line x1="2" y1="6" x2="32" y2="6" stroke="var(--notyet-line)" stroke-width="2.5" stroke-dasharray="6 4" stroke-linecap="round"/>
      <rect x="34" y="3" width="7" height="6" rx="1.5" fill="none" stroke="var(--notyet-line)" stroke-width="1.5"/>
    </svg>`;
  } else {
    return `<svg width="44" height="12" viewBox="0 0 44 12" style="vertical-align:middle">
      <line x1="2" y1="6" x2="34" y2="6" stroke="var(--stop-line)" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="36" y1="3" x2="42" y2="9" stroke="var(--stop-line)" stroke-width="2" stroke-linecap="round"/>
      <line x1="42" y1="3" x2="36" y2="9" stroke="var(--stop-line)" stroke-width="2" stroke-linecap="round"/>
    </svg>`;
  }
}

/* Status Pill Helper */
function renderStatusPill(status, customLabel) {
  const norm = status.toLowerCase();
  const label = customLabel || status.replace('_', ' ');
  let icon = '';
  if (norm === 'open') icon = '<svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block"><circle cx="12" cy="12" r="8"/></svg>';
  else if (norm === 'test_first') icon = '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="display:inline-block"><circle cx="12" cy="12" r="8"/></svg>';
  else if (norm === 'not_yet') icon = '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';
  else if (norm === 'stop') icon = '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  return `<span class="status-pill ${norm}">${icon} ${label}</span>`;
}

/* Logo Component */
function renderLogo() {
  return `<div style="display:flex;align-items:center;cursor:pointer" onclick="goDestination('state')" title="Novaliners home">
    <img class="logo-light" src="/static/assets/novaliners-logo.png" alt="Novaliners" style="height:24px;width:auto;display:block;object-fit:contain" onerror="this.style.display='none'"><span class="logo-dark" role="img" aria-label="Novaliners"><img src="/static/assets/novaliners-mark.png" alt="" style="height:24px;width:24px;display:block;object-fit:contain"><b>NOVALINERS</b></span>
  </div>`;
}

/* Onboarding TopBar (reveal screens 03, 13, 15). v11 (prototype 3341-3356): the logo, one status pill with the map's name, and a way
   back. The three-step stepper (Diagnosis / Your map / Activity) is gone with the old menu it named. `mode` is a key of DIAG_STATUS
   (a number is the old call style: 2 means the reveal, "ready"). */
const DIAG_STATUS = { ready: 'Analysis ready', working: 'Working on it', clarify: 'Clarification needed', safety: 'Safety priority' };
function renderOnboardingTopBar(mode, rightText = "Save and exit", rightAction = "renderScreen('01')") {
  const key = DIAG_STATUS[mode] ? mode : (mode === 2 ? 'ready' : 'working');
  const name = typeof getActiveProjectInfo === 'function' ? getActiveProjectInfo().name : '';
  return `<header class="onboarding-topbar">
    ${renderLogo()}
    <span class="diag-status-pill ${key}">
      <span class="dot"></span>${DIAG_STATUS[key]}${name ? `<span class="sep">·</span><span class="proj">${esc(name)}</span>` : ''}
    </span>
    <div>
      <a onclick="${rightAction}" style="font-family:var(--font-ui);font-size:13px;font-weight:600;color:var(--ink-2);text-decoration:none;cursor:pointer">${rightText}</a>
    </div>
  </header>`;
}

/* Settings (sidebar footer): Appearance = Light | Dark. The menu is a plain hidden/shown element, so opening it
   never re-renders the screen (a typed goal on the Start page stays). */
function renderSettings(rail) {
  const t = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
  const gear = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
  const sun = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const moon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  const engineAlert = ENGINE.status === 'error' ? ' has-alert' : '';
  const btn = rail
    ? `<button type="button" id="settings-btn" class="sidebar-collapsed-icon-btn${engineAlert}" onclick="toggleSettings(event)" title="Settings" aria-label="Settings" aria-haspopup="true" aria-expanded="false">${gear}</button>`
    : `<button type="button" id="settings-btn" class="sidebar-nav-item${engineAlert}" onclick="toggleSettings(event)" aria-haspopup="true" aria-expanded="false">${gear}<span>Settings</span></button>`;
  return `<div style="position:relative;${rail ? '' : 'margin-bottom:8px'}">
    ${btn}
    <div id="settings-menu" class="settings-menu ${rail ? 'rail' : ''}" role="group" aria-label="Settings" hidden onclick="event.stopPropagation()">
      <div class="settings-title">Appearance</div>
      <div class="theme-seg" role="group" aria-label="Theme">
        <button type="button" data-theme-opt="light" aria-pressed="${t === 'light'}" onclick="setTheme('light')">${sun} Light</button>
        <button type="button" data-theme-opt="dark" aria-pressed="${t === 'dark'}" onclick="setTheme('dark')">${moon} Dark</button>
      </div>
      <div class="settings-engine" id="engine-settings">${renderEngineSettings()}</div>
    </div>
  </div>`;
}
/* Engine section of the Settings menu: provider + model, and whether the engine is ready. Refreshed in place
   (the menu stays open, the screen behind it is untouched). */
function renderEngineSettings() {
  const opts = (vals, sel) => vals.map(v => `<option value="${esc(v)}"${v === sel ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const models = ENGINE.models[ENGINE.provider] || [];
  const msg = ENGINE.status === 'ok' ? 'Engine ready. New answers use this model.' : (ENGINE.detail || (ENGINE.status === 'error' ? 'Engine not ready.' : 'Checking the engine…'));
  return `
      <div class="settings-title"><span>Engine</span>${ENGINE.commit ? `<span class="settings-chip" title="Code commit served">${esc(ENGINE.commit)}</span>` : ''}</div>
      <label class="settings-label" for="engine-provider">Provider</label>
      <select id="engine-provider" class="settings-select" onchange="onEngineProvider(this.value)">${ENGINE.providers.length ? opts(ENGINE.providers, ENGINE.provider) : '<option>—</option>'}</select>
      <label class="settings-label" for="engine-model">Model</label>
      <select id="engine-model" class="settings-select" onchange="onEngineModel(this.value)">${models.length ? opts(models, ENGINE.model) : '<option>—</option>'}</select>
      <div class="settings-status ${ENGINE.status}" role="status" aria-live="polite">${esc(msg)}</div>`;
}
function refreshEngineSettings() {
  const host = document.getElementById('engine-settings');
  const focused = document.activeElement && host && host.contains(document.activeElement) ? document.activeElement.id : '';
  if (host) host.innerHTML = renderEngineSettings();
  if (focused) { const el = document.getElementById(focused); if (el) el.focus(); }
  const b = document.getElementById('settings-btn') || document.getElementById('v11-settings-btn');
  if (b) b.classList.toggle('has-alert', ENGINE.status === 'error');
}
function setTheme(t) {
  t = t === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('novaliners-theme', t); } catch (e) { /* private mode: the choice just is not remembered */ }
  document.querySelectorAll('[data-theme-opt]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.themeOpt === t)));
}
function closeSettings() {
  const m = document.getElementById('settings-menu'), b = document.getElementById('settings-btn');
  if (m) m.hidden = true;
  if (b) b.setAttribute('aria-expanded', 'false');
}
function toggleSettings(e) {
  if (e) e.stopPropagation();
  const m = document.getElementById('settings-menu'), b = document.getElementById('settings-btn');
  if (!m) return;
  m.hidden = !m.hidden;
  if (b) b.setAttribute('aria-expanded', String(!m.hidden));
}
window.addEventListener('click', closeSettings);
window.addEventListener('keydown', e => { if (e.key === 'Escape') closeSettings(); });

/* ==========================================================================
   APP SHELL — v11 is the product shell (record D5).
   The v9 sidebar shell was removed in the legacy cleanup (2026-10-15): no screen renders it anymore.
   ========================================================================== */
function renderAppShell(activeNav, screenTitle, contentHtml) {
  return renderAppShellV11(activeNav, screenTitle, contentHtml);
}
// Step labels come from the engine in live mode: keep markup characters inert (quotes stay as they are)
function stepText(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function stepWaitNote(item, steps) {
  const names = (item.waitingFor || []).map(n => stepText((steps[n - 1] || {}).label)).filter(Boolean);
  if (!names.length) return '';
  return item.report && names.length > 1 ? 'After the steps above' : `After: ${names.join(', ')}`;
}
/* Today: what is open right now, in words. Several steps can be ready at once and several can be finished in a day. */
function todayCounts(steps, day) {
  const real = steps.filter(s => !s.report && !s.hold);
  return {
    ready: real.filter(s => s.ready).length,
    done: real.filter(s => s.status === STEP_STATUS.COMPLETED).length,
    total: real.length,
    doneToday: real.filter(s => s.status === STEP_STATUS.COMPLETED && s.doneDay === day).length
  };
}
function todaySubline(steps, day) {
  const c = todayCounts(steps, day);
  const parts = [];
  /* The order promise lives in the checklist note, which knows whether any step waits on another —
     this line must not claim "any order works" for plans that carry real dependencies. */
  if (c.ready > 1) parts.push(`${c.ready} steps are ready.`);
  if (c.doneToday > 0) parts.push(`${c.doneToday} done today.`);
  return parts.join(' ');
}
/* Today: steps from the routes that fit the user (route nodes on the frontier). A node the user did moves to
   "proof needed": doing it is a fact, but it only counts once evidence for it comes in. */
function renderRouteTasks(items) {
  if (!items || !items.length) return '';
  return `
      <div class="card-clean" style="padding:18px 20px">
        <div class="section-meta-label" style="margin:0 0 4px">Also ready · from your routes</div>
        <p style="font-size:12.5px;color:var(--ink-3);line-height:1.5;margin:0 0 12px">Steps from the routes that fit you. Do them in any order.</p>
        <div class="route-task-list">${items.map(t => `
          <div class="route-task ${t.state === 'proof' ? 'proof' : ''}">
            <div class="route-task-head">
              <span class="route-task-route">${t.route}${t.hyp ? ' <span class="mp-tag mp-rel" title="Hypothesis for your goal: nothing on record yet proves this route moves it. Test it small.">Hypothesis</span>' : ''}</span>
              <span class="status-pill ${t.state === 'proof' ? 'test_first' : 'open'}">${t.state === 'proof' ? 'PROOF NEEDED' : 'READY'}</span>
            </div>
            <div class="route-task-title"${t.lang ? ` lang="${t.lang}"` : ''}>${t.title}</div>
            ${t.state === 'proof' ? `
            <div class="route-task-note">You did this. It counts once evidence that it worked comes in.</div>
            <div class="route-task-actions"><button class="btn-secondary btn-sm" onclick="${t.onUndo}">Undo</button></div>` : `
            <div class="route-task-actions"><button class="btn-primary btn-sm" onclick="${t.onDone}">I did this</button></div>`}
          </div>`).join('')}
        </div>
      </div>`;
}

/* P0-04: canonical Moves — a measured experiment with its own durable lifecycle. Kept visually
   separate from route steps ("from your routes") and from the plan steps, so the four object types
   are never conflated by title. Executing is a FACT; the outcome stays a separate report. */
function renderCanonicalMoves(items) {
  if (!items || !items.length) return '';
  const rows = items.map(m => {
    const life = m.lifecycle;
    /* The action count is never taken on faith: when the card's own count is missing, the move's
       OWN action list answers. A move with actions can never be executed from here. */
    const rawActions = (m.raw && Array.isArray(m.raw.actions)) ? m.raw.actions.length : null;
    const total = Number(m.actionsTotal) || rawActions || 0;
    const done = Number(m.actionsDone) || 0;
    const open = life === 'PLANNED' || life === 'STARTED';
    /* Phase 7: the Move owns its ACTION LIST, so execution is recorded there one action at a time.
       [Mark executed] exists ONLY for a move that has no actions at all: everywhere else it would
       bypass the action list that is the canonical execution record. */
    const acts = (life === 'PLANNED'
      ? '<button class="btn-secondary btn-sm" onclick="liveMoveEvent(\'' + esc(m.moveId) + '\',\'STARTED\')">Start</button>'
      : '')
      + (open ? '<button class="btn-secondary btn-sm" onclick="liveMoveEvent(\'' + esc(m.moveId) + '\',\'ABANDONED\')">Cannot do</button>' : '')
      + (open && total === 0 ? '<button class="btn-primary btn-sm" onclick="liveMoveEvent(\'' + esc(m.moveId) + '\',\'EXECUTED\')">Mark executed</button>' : '')
      + '<button class="btn-secondary btn-sm" onclick="openCanonicalMove(\'' + esc(m.moveId) + '\')">Open move</button>';
    const progress = total
      ? done + ' of ' + total + ' actions completed.'
      : 'No actions are on this move.';
    const execNote = total
      ? 'Execution is recorded through the action list, one action at a time. There is no separate mark-executed.'
      : 'With no action list, this move can be marked executed directly.';
    return '<div class="route-task">'
      + '<div class="route-task-head"><span class="route-task-route">Canonical move</span>'
      + '<span class="status-pill ' + (life === 'EXECUTED' ? 'open' : 'not_yet') + '">' + esc(life) + '</span></div>'
      + '<div class="route-task-title">' + esc(m.title) + '</div>'
      + '<div class="route-task-note">' + esc(progress + ' ' + execNote) + '</div>'
      + '<div class="route-task-note">Executing is a fact, not proof.'
      + (m.hasOutcome ? ' An outcome is on record for this move.' : ' Report the outcome separately.') + '</div>'
      + '<div class="route-task-actions">' + acts + '</div></div>';
  }).join('');
  return '<div class="card-clean" style="padding:18px 20px;margin-top:16px">'
    + '<div class="section-meta-label" style="margin:0 0 4px">Canonical moves · measured experiments</div>'
    + '<p style="font-size:12.5px;color:var(--ink-3);line-height:1.5;margin:0 0 12px">A move has its own durable lifecycle and its own action list. It is not a route step and not a plan step.</p>'
    + '<div class="route-task-list">' + rows + '</div></div>';
}
/* [Open move] hands the Moves screen the exact server-issued move_id. Nothing is matched by title,
   path name or list position; the Moves screen shows the move this selection names. */
function openCanonicalMove(moveId) {
  const id = String(moveId || '');
  if (!id) return;
  STORE.movesSelectedMoveId = id;
  renderScreen('04');
}

/* Today: content boxes shown inside the main action card */
function renderMsgBox(heading, textEn, textId, isId, opts) {
  const text = isId ? textId : textEn;
  const o = opts || {};
  // live: the engine writes one message in the session language, so the EN/ID switch is not shown
  const langSwitch = o.noLang ? '' : `
        <div class="segmented-control">
          <button class="segmented-btn ${isId ? 'active' : ''}" onclick="toggleTodayLang('id')">Bahasa Indonesia</button>
          <button class="segmented-btn ${!isId ? 'active' : ''}" onclick="toggleTodayLang('en')">English</button>
        </div>`;
  return `
    <div class="msg-box">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px">
        <span class="box-heading">${heading}</span>${langSwitch}
      </div>
      <div class="msg-draft" lang="${o.lang || (isId ? 'id' : 'en')}">${o.noLang ? esc(text) : text}</div>
      <div style="display:flex;align-items:center;gap:8px;margin-top:10px">
        <button class="btn-secondary btn-sm" onclick="copyTodayMsg(this)">Copy message</button>
        <button class="btn-secondary btn-sm" onclick="window.open('https://wa.me/', '_blank')">Open WhatsApp</button>
      </div>
    </div>`;
}

function renderListBox(heading, intro, items, numbered) {
  const tag = numbered ? 'ol' : 'ul';
  return `
    <div class="content-box">
      <div class="box-heading" style="margin-bottom:8px">${heading}</div>
      <div style="font-weight:600;margin-bottom:6px">${intro}</div>
      <${tag} style="padding-left:20px;margin:0;color:var(--ink-2);display:flex;flex-direction:column;gap:4px">
        ${items.map(it => `<li>${it}</li>`).join('')}
      </${tag}>
    </div>`;
}

function renderQuoteBox(heading, quote, note) {
  return `
    <div class="content-box">
      <div class="box-heading" style="margin-bottom:8px">${heading}</div>
      <div class="msg-draft">${quote}</div>
      ${note ? `<p style="color:var(--ink-3);font-size:12.5px;margin:8px 0 0">${note}</p>` : ''}
    </div>`;
}

function renderDoneBox(title, text) {
  return `
    <div style="border:1px solid var(--border);border-radius:12px;padding:16px 18px;display:flex;align-items:center;gap:14px">
      <span aria-hidden="true" style="color:var(--open-fg);font-size:18px;font-weight:700;flex-shrink:0">✓</span>
      <div>
        <div style="font-family:var(--font-ui);font-weight:700;font-size:14.5px;color:var(--ink)">${title}</div>
        <div style="font-size:13px;color:var(--ink-2);margin-top:2px">${text}</div>
      </div>
    </div>`;
}

/* Today: thin "what success looks like" helper right under the action buttons */
function renderSuccessTip(label, text) {
  return `
  <div class="success-tip"><strong style="color:var(--ink);font-family:var(--font-ui)">${label}:</strong> ${text}</div>`;
}

/* Activity: the reason for the step in one line, with the way back to the Diagnosis screen */
function renderTodayWhy(headline) {
  return `
  <div class="today-why"><span><strong>Why this step:</strong> ${headline}</span><a href="#/state" onclick="event.preventDefault();goDestination('state')">State →</a></div>`;
}

/* Today: turn a step tag like "DAY 4–5 · UNDER 15 MINUTES" into a minimal time indicator */
function toTimeTag(tag) {
  let m = tag.match(/UNDER (\d+) MINUTES/);
  if (m) return `Under ${m[1]} min`;
  m = tag.match(/(\d+)-MINUTE CALL/);
  if (m) return `${m[1]} min call`;
  if (/SAVED/.test(tag)) return 'Done';
  if (/During the call/.test(tag)) return 'During the call';
  return 'About 5 min';
}

function renderOtherPathRow(status, name, rightHtml) {
  return `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
      <div style="display:flex;align-items:center;gap:8px;min-width:0">
        ${getPathGlyph(status)}
        <span>${name}</span>
      </div>
      ${rightHtml}
    </div>`;
}
const LOCK_NOTE = text => `<span style="font-family:var(--font-ui);font-size:11px;color:var(--notyet-fg);font-weight:600;white-space:nowrap">${text}</span>`;
