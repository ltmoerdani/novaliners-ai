/* Engine state + the floating review widget.
 *  - live: the engine (provider/model, switch without restart: README "Ganti model") is a section of the Settings
 *    menu in the sidebar (renderEngineSettings in ui-kit.js). There is no floating panel; the host element is removed.
 *  - demo (?demo=1): the prototype's review widget (screen switcher, 90-day simulation, personas) stays as designed,
 *    and the Engine section shows the same static mock as the prototype (nothing is called). */
const ENGINE = IS_DEMO
  ? { provider: 'vertex', model: 'gemini-3.5-flash-lite', commit: '', status: 'ok', detail: '',
      providers: ['vertex', 'gemini', 'mock'],
      models: { vertex: ['gemini-3.5-flash-lite', 'gemini-3.5-flash', 'gemini-3.8-flash'], gemini: ['gemini-3.5-flash-lite', 'gemini-3.5-flash', 'gemini-pro-latest'], mock: ['mock'] } }
  : { provider: null, model: null, models: {}, providers: [], status: 'loading', detail: '', commit: '' };

function initWidget() {
  if (IS_DEMO) {
    if (localStorage.getItem('novaliners_proto_widget_open') === 'true') {
      const btn = document.getElementById('proto-widget-btn');
      const card = document.getElementById('proto-widget-card');
      if (btn && card) { btn.style.display = 'none'; card.style.display = 'flex'; }
    }
    return;
  }
  const host = document.getElementById('proto-widget');
  if (host) host.remove();
}

async function loadEngine() {
  try { applyEngine(await API.health()); }
  catch (e) { ENGINE.status = 'error'; ENGINE.detail = 'Cannot reach the server: ' + e.message; refreshEngineSettings(); }
}
function applyEngine(h) {
  ENGINE.provider = h.provider; ENGINE.model = h.model || null;
  ENGINE.models = h.models_by_provider || {}; ENGINE.providers = h.providers || [];
  ENGINE.status = h.status === 'ok' ? 'ok' : 'error';
  ENGINE.detail = h.detail || ''; ENGINE.commit = h.commit || '';
  refreshEngineSettings();
}

async function onEngineProvider(p) {
  if (IS_DEMO) { ENGINE.provider = p; ENGINE.model = (ENGINE.models[p] || [])[0] || null; refreshEngineSettings(); return; }
  await switchEngineTo({ provider: p, model: null });
}
async function onEngineModel(m) {
  if (IS_DEMO) { ENGINE.model = m; refreshEngineSettings(); return; }
  await switchEngineTo({ provider: ENGINE.provider, model: m });
}
async function switchEngineTo(want) {
  if (want.provider === ENGINE.provider && want.model === ENGINE.model) return;
  ENGINE.status = 'loading'; ENGINE.detail = 'Switching…'; refreshEngineSettings();
  try {
    applyEngine(await API.switchEngine(want));
    showToast(`Engine active: ${ENGINE.provider} · ${ENGINE.model || '—'}`, '', '');
  } catch (e) {
    await loadEngine();
    ENGINE.status = 'error'; ENGINE.detail = 'Could not switch: ' + e.message; refreshEngineSettings();
    showToast('Could not switch engine: ' + e.message, '', '', 'error');
  }
}

/* ── Prototype review widget (demo mode) ──────────────────────────────────── */
function setPersona(personaKey) {
  STORE.currentPersona = personaKey;
  const pSel = document.getElementById('persona-selector');
  if (pSel) pSel.value = personaKey;

  STORE.activeProject = personaKey;
  STORE.mapsView = 'landscape';
  renderScreen('state');
}

/* The widget's screen switcher: 'maps:readiness' picks a Maps lens ('maps:overview' resolves to Explore). */
function widgetGo(value) {
  if (value.startsWith('maps')) {
    let lens = value.split(':')[1] || 'landscape';
    if (lens === 'overview') lens = 'landscape';   // Overview was merged into Explore
    if (lens !== 'readiness' && STORE.mapsView === 'readiness') STORE.mapsLens = lens;
    STORE.mapsView = lens;
    renderScreen('maps');
    return;
  }
  renderScreen(value);
}

function toggleProtoWidget() {
  const btn = document.getElementById('proto-widget-btn');
  const card = document.getElementById('proto-widget-card');
  if (!btn || !card) return;
  const isCardOpen = card.style.display === 'flex';
  if (isCardOpen) {
    card.style.display = 'none';
    btn.style.display = 'flex';
    localStorage.setItem('novaliners_proto_widget_open', 'false');
  } else {
    card.style.display = 'flex';
    btn.style.display = 'none';
    localStorage.setItem('novaliners_proto_widget_open', 'true');
  }
}

function updateProtoWidgetLabel() {
  const selEl = document.getElementById('screen-selector');
  const lbl = document.getElementById('proto-widget-current-screen');
  if (selEl && lbl && selEl.options && selEl.options[selEl.selectedIndex]) {
    lbl.textContent = selEl.options[selEl.selectedIndex].text;
  }
}
