/* LIVE: real-engine session model.
 *
 * One object (`LIVE`) holds what the server knows about the current revenue map plus the few things
 * the browser owns (stable user id, check-in log, "do it anyway" decisions). Screens render from
 * `LIVE` (via the view-models in live-vm.js) and from `useRoadmapStore` (hydrated by syncStoreFromLive).
 * Server stays the source of truth: sessions, evidence, diagnosis and action reports all come from
 * the existing endpoints. Nothing here is fabricated.
 */
const LS_LIVE = 'novaliners-v9';
/* Role labels for the evidence panel. DISPLAY ONLY: the conversation is not organised by topic or step.
 * Evidence is grouped by the semantic role of the claim it came from (goal/desire/event/assumption/claim);
 * what the user explicitly does not know is shown separately as "Still to learn" (E1: "we do not know"
 * must stay visible). The engine picks the next move from what it knows and what is still unclear
 * (internal-docs §25). */
const ROLE_KEYS = ['goal', 'desire', 'event', 'assumption', 'claim'];
const ROLE_UI = {
  goal:       { label: 'Goal',        color: 'var(--open-line)',   desc: 'Where you want to go, and by when.' },
  desire:     { label: 'Wants',       color: 'var(--violet)',      desc: 'Why it matters to you, in your own words.' },
  event:      { label: 'Events',      color: 'var(--notyet-line)', desc: 'Things that happened, including before now.' },
  assumption: { label: 'Assumptions', color: 'var(--test-line)',   desc: 'What you believe without data yet. Kept apart from facts.' },
  claim:      { label: 'Facts',       color: 'var(--ink-muted)',   desc: 'What you told us about how things are now.' }
};
const GAP_UI = { label: 'Still to learn', color: 'var(--ink-muted)', desc: 'What you said you do not know or do not have yet.' };
/* Resolve the role of one evidence item: claim_role first, then the legacy topic label (old sessions
 * grouped facts by interview topic; those topics are not roles, so they fold into Facts). */
function evidenceRole(e) {
  const r = String((e && e.claim_role) || '').toLowerCase();
  if (ROLE_UI[r]) return r;
  const t = String((e && e.topic) || '').toLowerCase();
  if (ROLE_UI[t]) return t;
  return 'claim';
}
/* Legacy label lookup (Journey "From your Talk", reveal "strongest evidence"): old topic keys and the
 * role-named topics written by newer sessions both resolve to a readable label. Not used for grouping. */
const TOPIC_UI = {
  GOAL: ROLE_UI.goal, REVENUE_STATE: { label: 'Income' }, MOTION: { label: 'What you tried' },
  DEMAND: { label: 'Interest' }, CONVERSION: { label: 'Buying' },
  DESIRE: ROLE_UI.desire, EVENT: ROLE_UI.event, ASSUMPTION: ROLE_UI.assumption,
  CLAIM: ROLE_UI.claim, GAP: GAP_UI
};

const LIVE = {
  loaded: false,
  userId: '', sid: '', chain: [], startTs: 0,
  goalText: '', state: null, artifact: null, baseline: null,
  explain: null, explainState: 'idle',   // plain-language rewrite of the diagnosis (server: /explain), idle | loading | ready | failed
  workspace: null, journey: null, maps: [],
  msgs: [], evidence: [], tags: [],
  progress: 0, interviewDone: false,
  nav: null,               // latest planner move from the server: { move: {kind, intent, focus, text, headline, stop, reason}, summary }
  thinking: false, finalizing: false, stage: '', err: '',
  checkins: [], overrides: [], tips: {}, activePath: '', horizonOverride: 0, goalOverride: 0,
  lastDiff: null,          // before/after path statuses from the last check-in (for the "map updated" screens)
  localDone: {},           // sid -> done time (ms) when the single fallback step was done (no server slot for it)
  routes: null,            // POST /session/{sid}/routes: route nodes on the frontier (Today: "from your routes")
  projection: null,        // GET /session/{sid}/readiness: the adjudicated readiness projection (screen 18, one source of truth)
  projectionTried: '',     // sid we already tried to load the projection for (never loop)
  pendingPrior: '',        // set while a follow-up cycle is waiting for the user's first message
  finalizeAbort: null
};

function newUserId() {
  const a = new Uint8Array(8);
  (window.crypto || {}).getRandomValues ? crypto.getRandomValues(a) : a.forEach((_, i) => { a[i] = Math.floor(Math.random() * 256); });
  return 'u_' + Array.from(a).map(b => b.toString(16).padStart(2, '0')).join('');
}

/* Persistence: one LS record per revenue map (keyed by the first session of its chain), plus what is
 * browser-wide (user id, tips, which map is open). Switching maps never loses another map's check-in log. */
function lsData() {
  const d = lsGet(LS_LIVE, {}) || {};
  if (!d.maps && d.sid) {           // pre-multi-map format
    d.maps = { [(d.chain && d.chain[0]) || d.sid]: { chain: d.chain || [d.sid], startTs: d.startTs || 0, checkins: d.checkins || [], overrides: d.overrides || [],
      activePath: d.activePath || '', horizonOverride: d.horizonOverride || 0, goalOverride: d.goalOverride || 0 } };
    d.current = d.current || d.sid;
  }
  d.maps = d.maps || {};
  return d;
}
function saveLive() {
  const d = lsData();
  d.userId = LIVE.userId; d.tips = LIVE.tips; d.localDone = LIVE.localDone; d.current = LIVE.sid;
  const key = LIVE.chain[0] || LIVE.sid;
  if (key) d.maps[key] = { chain: LIVE.chain, startTs: LIVE.startTs, checkins: LIVE.checkins, overrides: LIVE.overrides,
    activePath: LIVE.activePath, horizonOverride: LIVE.horizonOverride, goalOverride: LIVE.goalOverride };
  lsSet(LS_LIVE, d);
}
function applyMapEntry(sid, created) {
  const m = Object.values(lsData().maps).find(x => (x.chain || []).includes(sid));
  if (m) {
    LIVE.chain = m.chain.slice(); LIVE.startTs = m.startTs || created || Date.now();
    LIVE.checkins = m.checkins || []; LIVE.overrides = m.overrides || [];
    LIVE.activePath = m.activePath || ''; LIVE.horizonOverride = m.horizonOverride || 0; LIVE.goalOverride = m.goalOverride || 0;
  } else {                            // a map this browser has never tracked: the timeline starts when the server made it
    LIVE.chain = [sid]; LIVE.startTs = created || Date.now();
    LIVE.checkins = []; LIVE.overrides = []; LIVE.activePath = ''; LIVE.horizonOverride = 0; LIVE.goalOverride = 0;
  }
  LIVE.baseline = null; LIVE.lastDiff = null;
}

/* ── Derived facts ─────────────────────────────────────────────────────────── */
function liveGoal() {
  const rs = (LIVE.artifact && LIVE.artifact.revenue_state) || {};
  const target = LIVE.goalOverride || (rs.target_monthly != null ? rs.target_monthly : null);
  const current = rs.current_monthly != null ? rs.current_monthly : null;
  return { current, target, gap: target != null && current != null ? Math.max(target - current, 0) : (rs.gap_monthly != null ? rs.gap_monthly : null) };
}
function liveHorizon() {
  // The goal model parses the deadline from the goal text ("within 90 days"); 90 is the product default.
  // The user can move it at Welcome back / Day review (LIVE.horizonOverride).
  const g = (LIVE.state && LIVE.state.goal) || {};
  // The goal parser can pick up other durations from the text ("running 8 months"), so only a plausible
  // planning window (2 weeks to 4 months) is trusted; anything else falls back to the 90-day product default.
  const parsed = Number(g.deadline_days);
  const plausible = parsed >= 14 && parsed <= 120 ? parsed : 0;
  return Math.max(7, Math.min(365, Number(LIVE.horizonOverride) || plausible || 90));
}
function liveCycleLen() {
  const d = LIVE.artifact;
  return Math.max(7, Math.min(60, Number(d && d.reassess_window_days) || 14));
}
/* A deadline the person or the goal actually gave (never the 90-day product default). */
function liveHorizonKnown() {
  const parsed = Number(((LIVE.state && LIVE.state.goal) || {}).deadline_days);
  return Number(LIVE.horizonOverride) > 0 || (parsed >= 14 && parsed <= 120);
}
function liveDay() {
  if (!LIVE.startTs) return 1;
  return Math.max(1, Math.min(liveHorizon(), Math.floor((Date.now() - LIVE.startTs) / 86400000) + 1));
}
function liveGoalTitle() {
  const t = String(LIVE.goalText || '').replace(/\s+/g, ' ').trim();
  if (!t) return 'Your revenue goal';
  const g = liveGoal();
  if (g.target != null) return `Reach ${fmtM(g.target)} a month`;
  return brief(t, 38);
}
function liveMapTitle() { return liveGoalTitle(); }

/* ── Server sync ───────────────────────────────────────────────────────────── */
async function liveLoadSession(sid, opts) {
  const st = await API.state(sid);                       // 404 → throws, caller resets
  if (!(LIVE.chain || []).includes(sid)) applyMapEntry(sid, st.created_ts ? st.created_ts * 1000 : 0);
  LIVE.sid = sid;
  STORE.viewStep = 0;
  LIVE.state = st;
  LIVE.goalText = st.goal_text || LIVE.goalText || '';
  LIVE.interviewDone = !!st.interview_done;
  LIVE.nav = null;
  LIVE.thinking = false; LIVE.finalizing = false; LIVE.err = '';
  // Evidence / transcript (server copy is the truth; survives a cleared browser)
  try {
    const ev = await API.evidence(sid);
    LIVE.msgs = (ev.transcript || []).map(m => ({ role: m[0] || m.role, text: String(m[1] != null ? m[1] : m.text || '') }))
      .map(m => ({ role: m.role === 'user' ? 'user' : 'engine', text: m.text }));
    LIVE.evidence = ev.evidence || [];
    LIVE.tags = ev.intent_tags || [];
  } catch (e) { LIVE.msgs = []; LIVE.evidence = []; LIVE.tags = []; }
  // Diagnosis (only when the state says one exists: avoids 409 console noise)
  LIVE.artifact = null; LIVE.explain = null; LIVE.explainState = 'idle';
  LIVE.projection = null; LIVE.projectionTried = '';
  if (st.has_diagnosis) {
    try { LIVE.artifact = await API.diagnosis(sid); } catch (e) { LIVE.artifact = null; }
  }
  // The current move (what we are asking and why) is restored from the server on EVERY load — a checkpoint
  // is not the end of the conversation (R6), and the same presented decision must survive reload.
  {
    try {
      const n = await API.navigation(sid);
      LIVE.nav = { move: n.move, summary: n.summary, current: n.current || null };
      // old engine messages come back tagged with their step type: matched by exact text from the server planner log
      const left = (n.history || []).slice();
      LIVE.msgs.forEach(m => {
        if (m.role !== 'engine') return;
        const i = left.findIndex(h => h.text === m.text);
        if (i >= 0) { const h = left.splice(i, 1)[0]; m.move = { kind: h.kind, intent: h.intent, headline: h.headline }; }
      });
    } catch (e) { LIVE.nav = null; }
  }
  if (LIVE.artifact && !LIVE.baseline) LIVE.baseline = LIVE.artifact;
  // Journey (linked sessions only) + workspace (per-user path states / snapshots)
  LIVE.journey = null;
  if (st.journey_ok) { try { LIVE.journey = await API.journey(sid); } catch (e) { /* optional */ } }
  await liveLoadWorkspace();
  await liveLoadRoutes();
  await liveLoadMoves();        // P0-04: canonical Move ledger (distinct from route nodes/plan steps)
  await liveLoadReadiness();
  await liveLoadExperience();   // V4: the version-bound read all five surfaces compare against
  await liveLoadCheckins();     // D-02: durable check-in history replaces the browser log
  saveLive();
  syncStoreFromLive();
}

/* Route nodes the user can do next. Best effort: routes are extra steps, so the plan never waits on them.
   D-03 / MAP-06: refreshes use the READ-ONLY GET /routes (Rebuild View), which never births a route.
   Only when nothing has been composed for this map yet do we compose ONCE via POST, then read again;
   after that every render/refresh is a pure read, so no GET can mutate lineage as a side effect. */
async function liveLoadRoutes() {
  LIVE.routes = null;
  const sid = LIVE.sid;
  if (!sid || !LIVE.artifact || !(LIVE.state && LIVE.state.user_id)) return;
  try {
    let r = await API.routesRead(sid);
    if (LIVE.sid !== sid) return;
    if (!(r && (r.routes || []).length) && LIVE.routesBirthTried !== sid) {
      LIVE.routesBirthTried = sid;                       // one composition attempt per map, never a loop
      try { await API.routes(sid); } catch (e) { /* keep the honest empty read */ }
      if (LIVE.sid !== sid) return;
      r = await API.routesRead(sid);
    }
    if (LIVE.sid !== sid) return;
    LIVE.routes = r;
  } catch (e) { LIVE.routes = null; }
}
/* The adjudicated readiness projection: what screen 18 shows and what the narrative is grounded in.
   Best effort like routes; a failure leaves the checklist empty rather than inventing states. */
async function liveLoadReadiness() {
  LIVE.projection = null;
  const sid = LIVE.sid;
  if (!sid || !LIVE.artifact) return;
  LIVE.projectionTried = sid;
  try { LIVE.projection = await API.readiness(sid); } catch (e) { LIVE.projection = null; }
}
/* Presentation only: the durable row keeps null (a count that was never reported); the browser
   cache shows an em dash so a missing count never renders as "null" or as a misleading 0. */
function liveCountField(v) { return v == null ? '—' : v; }
/* D-02: check-in history is DURABLE server state, not localStorage. On load the server copy is
   authoritative for a logged-in map; a failed call keeps the local log and claims nothing durable.
   Fields the server stored as null stay null in the store (missing != 0); the cache maps them to a
   display dash only. */
async function liveLoadCheckins() {
  const sid = LIVE.sid;
  const uid = LIVE.state && LIVE.state.user_id;
  if (IS_DEMO || !sid || !uid) return;
  try {
    const r = await API.checkins(sid);
    if (LIVE.sid !== sid) return;   // a late answer for a map the person left is dropped
    LIVE.checkins = (r.checkins || []).map(c => ({
      cycle: c.cycle, day: c.day, outcome: c.outcome,
      contacted: liveCountField(c.contacted), replies: liveCountField(c.replies), calls: liveCountField(c.calls),
      paid: c.paid, rp: c.rp,
      path: c.path, title: c.title, note: c.note,
      ts: (c.created_ts || 0) * 1000, sid: c.session_id, checkinId: c.checkin_id
    }));
    saveLive();
  } catch (e) { /* offline: keep the local log; nothing here is claimed durable */ }
}
/* P0-04: the canonical Move ledger. A Move is a measured experiment with its own lifecycle — it is
   NOT a route node, NOT a plan step, and NOT the adaptive NextMove suggestion. Read-only here. */
async function liveLoadMoves() {
  LIVE.moves = null;
  const sid = LIVE.sid;
  if (!sid || !LIVE.artifact) return;
  try { const m = await API.moves(sid); if (LIVE.sid === sid) LIVE.moves = m; } catch (e) { LIVE.moves = null; }
}
/* P0-04: canonical Move transition, idempotent per (move, event) key. Executing is a FACT; it is never
   rendered as a verified outcome. A 409 (invalid transition or reused key with a different payload) is
   surfaced, never retried blindly. */
async function liveMoveEvent(moveId, event) {
  LIVE.pendingMoveOps = LIVE.pendingMoveOps || {};
  const opk = moveId + ':' + event;
  const opId = LIVE.pendingMoveOps[opk] || (LIVE.pendingMoveOps[opk] = newOperationId('mv'));
  try {
    await API.moveEventOp(LIVE.sid, moveId, event, '', opId);
    delete LIVE.pendingMoveOps[opk];
    const ok = await liveRefreshAfterMutation();
    const msg = event === 'EXECUTED' ? 'Recorded as executed. That is a fact, not proof.'
      : (event === 'ABANDONED' ? 'Recorded as cannot-do. Nothing was claimed.' : 'Move started.');
    showToast(ok ? msg : msg + ' The latest view could not be refreshed.', '', '', ok ? '' : 'error');
  } catch (e) {
    showToast('Could not record that: ' + e.message, '', '', 'error');
  }
}
/* Phase 7: execute ONE action of ONE canonical Move. The action identity (move_id + action_id) is
   the server's; the browser never invents one. DONE, SKIPPED and BLOCKED are three separate events,
   and the accepted event is never resubmitted (one operation key per (move, action, status)). */
async function liveReportMoveAction(moveId, actionId, status, note, btn) {
  LIVE.pendingMoveActionOps = LIVE.pendingMoveActionOps || {};
  const opk = String(moveId) + ':' + String(actionId) + ':' + String(status);
  const opId = LIVE.pendingMoveActionOps[opk] || (LIVE.pendingMoveActionOps[opk] = newOperationId('mx'));
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }
  try {
    const r = await API.moveActionOp(LIVE.sid, moveId, actionId, status, note || '', opId);
    delete LIVE.pendingMoveActionOps[opk];
    await liveRefreshAfterMutation();
    return r;
  } catch (e) {
    if (btn) { btn.disabled = false; btn.style.opacity = ''; }
    throw e;
  }
}
/* Phase 7: the RESULT of the Move as a whole. Execution stays untouched by this call. */
async function liveReportMoveOutcome(moveId, body) {
  const payload = Object.assign({}, body);
  if (payload.outcome && !payload.path) payload.path = liveActivePathKey();
  let r = null;
  try {
    r = await API.moveOutcome(LIVE.sid, moveId, payload);
  } catch (e) {
    if (e && e.code === 'MOVE_OUTCOME_REJECTED') await liveRefreshAfterMutation({ render: false });
    throw e;
  }
  await liveRefreshAfterMutation();
  return r;
}

/* Phase 7 §10 case B: the user asks the engine to decide what comes NEXT. This is an explicit,
   LLM-backed decision at the result boundary - never started silently by a checkbox, never a
   checkpoint. It runs the SAME navigation authority a conversation turn uses, so the answer is either
   an authorized ACTION (which creates the canonical Move with its own action list) or the authorized
   QUESTION / EVIDENCE_REQUEST / HOLD. */
async function liveDecideNextMove(btn) {
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }
  try {
    const r = await API.nextMove(LIVE.sid);
    await liveRefreshAfterMutation();
    const d = (r && r.decision) || {};
    if (r && r.move_id) {
      showToast('A move is authorized - it has its own action list now.', 'Open Moves \u2192', 'moves');
    } else if (d.degraded) {
      showToast('The engine could not finish deciding. Nothing changed - try again.', '', '', 'error');
    } else if (d.kind === 'QUESTION' || d.kind === 'EVIDENCE_REQUEST') {
      showToast('One thing has to be settled first: ' + brief(d.headline || d.text || '', 90), 'Answer in Talk \u2192', 'talk');
    } else {
      showToast('Nothing new is authorized yet. ' + brief(d.headline || '', 90));
    }
    return r;
  } catch (e) {
    if (btn) { btn.disabled = false; btn.style.opacity = ''; }
    const msg = (e && e.code === 'MOVE_ALREADY_ACTIONABLE') ? 'There is already a move to work on.'
      : (e && e.code === 'RESULT_STILL_PENDING') ? 'Report what happened for that move first.'
        : (e && e.message) ? e.message : 'Could not decide right now.';
    showToast(msg, '', '', 'error');
    return null;
  }
}

/* "I did this" / "Undo" on a route step: a fact about what the user did, not proof that it worked. */
async function liveRouteEvent(routeId, nodeId, event) {
  // D-10: one operation key per (route, node, event). A retry after a failed response reuses it, so the
  // server replays the accepted event rather than appending a second one.
  LIVE.pendingRouteOps = LIVE.pendingRouteOps || {};
  const opk = routeId + ':' + nodeId + ':' + event;
  const opId = LIVE.pendingRouteOps[opk] || (LIVE.pendingRouteOps[opk] = newOperationId('rn'));
  try {
    await API.routeNodeOp(LIVE.sid, routeId, nodeId, event, opId);
    delete LIVE.pendingRouteOps[opk];
    const ok = await liveRefreshAfterMutation();   // P0-01/NC-02: one version-checked boundary
    const msg = event === 'EXECUTED' ? 'Saved. It counts once evidence that it worked comes in.' : 'Undone. It is back on your list.';
    showToast(ok ? msg : msg + ' The latest view could not be refreshed.', '', '', ok ? '' : 'error');
    if (STORE.currentScreen === 'moves') renderScreen('moves');
  } catch (e) {
    showToast('Could not save that: ' + e.message, '', '', 'error');
  }
}

async function liveLoadWorkspace() {
  LIVE.workspace = null;
  // Only sessions created with a user id have a workspace (avoids a pointless 404 for legacy sessions)
  const uid = LIVE.state && LIVE.state.user_id;
  if (!uid) return;
  try { LIVE.workspace = await API.workspace(uid); } catch (e) { LIVE.workspace = null; }
}

/* Plain-language rewrite of the diagnosis. The server writes it once per diagnosis (one LLM call, 15 to 50 seconds) and caches it;
   until it arrives the screen shows a skeleton for the summary and the engine's own text everywhere else. Never blocks, never loops:
   a failure leaves the engine's text in place. */
async function liveEnsureExplain() {
  const sid = LIVE.sid;
  if (IS_DEMO || !sid || !LIVE.artifact || LIVE.explainState !== 'idle') return;
  LIVE.explainState = 'loading';
  try {
    const ex = await API.explain(sid);
    if (LIVE.sid !== sid) return;
    LIVE.explain = ex; LIVE.explainState = 'ready';
  } catch (e) {
    if (LIVE.sid !== sid) return;
    LIVE.explainState = 'failed';
  }
  if (['state', 'maps'].includes(STORE.currentScreen)) {
    // An Explain response that arrives late must not close an overlay the user is using:
    // renderScreen replaces the DOM and closes drawers/modals (router). If an overlay is open,
    // defer to the next navigation (summary content renders then too — contract:
    // never blocks, never loops); with no overlay, render as usual.
    if (document.querySelector('#stop-modal.open, #why-drawer.open')) return;
    // Scroll container of the v11 split pane is .ws-main (`.diag-scroll` kept for older shells).
    const sc = document.querySelector('.ws-main') || document.querySelector('.diag-scroll'); const top = sc ? sc.scrollTop : 0;
    renderScreenKeepingUi(STORE.currentScreen);   // the rewrite is not the person's action: keep their focus, open lists and scroll
    const sc2 = document.querySelector('.ws-main') || document.querySelector('.diag-scroll'); if (sc2) sc2.scrollTop = top;
  }
}

async function liveRefreshMaps() {
  try { LIVE.maps = await API.sessions(); } catch (e) { LIVE.maps = []; }
  return LIVE.maps;
}

async function liveBoot() {
  const d = lsData();
  LIVE.userId = d.userId || newUserId();
  LIVE.tips = d.tips || {};
  LIVE.localDone = d.localDone || {};
  LIVE.sid = ''; LIVE.chain = [];
  if (d.current) {
    try { await liveLoadSession(d.current); }
    catch (e) { if (e.status === 404) liveForget(); }
  }
  LIVE.loaded = true;
  saveLive();
  liveRefreshMaps();
}

/* Forget the current map (server keeps the session; the user just starts fresh). */
function liveForget() {
  LIVE.sid = ''; LIVE.chain = []; LIVE.startTs = 0; LIVE.goalText = '';
  LIVE.state = null; LIVE.artifact = null; LIVE.baseline = null; LIVE.workspace = null; LIVE.journey = null;
  LIVE.projection = null; LIVE.projectionTried = '';
  LIVE.msgs = []; LIVE.evidence = []; LIVE.tags = [];
  LIVE.nav = null; LIVE.progress = 0; LIVE.interviewDone = false;
  LIVE.thinking = false; LIVE.finalizing = false; LIVE.err = '';
  LIVE.checkins = []; LIVE.overrides = []; LIVE.activePath = ''; LIVE.lastDiff = null;
  LIVE.horizonOverride = 0; LIVE.goalOverride = 0;
  LIVE.routesBirthTried = '';
  saveLive();
  syncStoreFromLive();
}

/* ── Interview ─────────────────────────────────────────────────────────────── */
async function liveStartSession(goalText, priorSid, keepMsgs) {
  const body = { goal_text: goalText, language: document.documentElement.lang || 'en', user_id: LIVE.userId };
  if (priorSid) body.prior_session_id = priorSid;
  const s = await API.createSession(body);
  LIVE.sid = s.session_id;
  if (!priorSid) { LIVE.chain = []; LIVE.checkins = []; LIVE.startTs = Date.now(); LIVE.baseline = null; LIVE.lastDiff = null; }
  LIVE.chain.push(LIVE.sid);
  LIVE.goalText = goalText;
  LIVE.state = { session_id: LIVE.sid, goal_text: goalText, goal: s.goal || null, user_id: LIVE.userId, has_prior: !!priorSid, interview_done: false,
                 has_diagnosis: false, journey_ok: false };
  LIVE.artifact = null; LIVE.journey = null;
  if (!keepMsgs) LIVE.msgs = [];
  LIVE.evidence = []; LIVE.tags = [];
  LIVE.nav = null; LIVE.progress = 0; LIVE.interviewDone = false; LIVE.err = '';
  saveLive();
  return s;
}

async function liveSendMessage(text) {
  text = String(text || '').trim();
  if (!text || LIVE.thinking) return false;
  LIVE.err = '';
  const firstTurn = !LIVE.sid;
  // Optimistic: the user's words and the thinking indicator show before any network round trip.
  LIVE.msgs.push({ role: 'user', text, ts: Date.now() });
  LIVE.thinking = true;
  renderChatLive();
  try {
    if (firstTurn) {
      // Follow-up cycle: the new session keeps the ORIGINAL goal and links back to the previous session
      // (prior_session_id), so the engine's journey loop (verdict, path states) applies. The user's
      // words become the first interview answer.
      const prior = LIVE.pendingPrior || '';
      LIVE.pendingPrior = '';
      const created = await liveStartSession(prior ? LIVE.goalText : text, prior, true);
      if (!prior && created && created.first_question) {
        // Create Map: the story is ALREADY the first durable event on the server (read once by the semantic observer)
        // and the server chose the first move from what it understood. Do not send the same story again as a second
        // message (that read it twice and discarded the server's first question).
        LIVE.thinking = false;
        try {
          const ev = await API.evidence(LIVE.sid);
          LIVE.tags = ev.intent_tags || [];
          const at = LIVE.msgs.length;
          LIVE.evidence = (ev.evidence || []).map(e => Object.assign({ _msg: at }, e));
        } catch (e) { /* evidence is optional here */ }
        let mv = { kind: 'QUESTION', intent: '', headline: '' };
        try {
          const n = await API.navigation(LIVE.sid);
          LIVE.nav = { move: n.move, summary: n.summary, current: n.current || null };
          mv = { kind: n.move.kind, intent: n.move.intent, headline: n.move.headline,
                 degraded: !!n.move.degraded, error_code: n.move.error_code || '',
                 checkpoint: n.move.checkpoint || null };
        } catch (e) { LIVE.nav = null; }
        LIVE.progress = 0;
        LIVE.msgs.push({ role: 'engine', text: created.first_question, ts: Date.now(), move: mv });
        saveLive();
        return true;
      }
    }
    // Stable idempotency key: the same text resent after a failure uses the same key (no double effect).
    if (!(LIVE.retryKey && LIVE.retryText === text)) { LIVE.retryKey = 'k-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10); LIVE.retryText = text; }
    // Duplicate-send guard (16 Oct incident, session 7989259580af): a message identical to the last
    // successful send is a NEW event on the server (different idempotency key) — confirm
    // first so a re-paste is not processed twice (CP-25 / W-12, presentation layer only).
    if (LIVE.lastSentText && LIVE.lastSentText === text && typeof window !== 'undefined' && !window.confirm('This looks like the exact message you already sent. Send it again anyway?')) { LIVE.thinking = false; return false; }
    const j = await API.message(LIVE.sid, text, LIVE.retryKey);
    LIVE.lastSentText = text;
    LIVE.retryKey = ''; LIVE.retryText = '';
    LIVE.thinking = false;
    if (j.kind === 'ack') {
      // the server closed this conversation (a diagnosis was already built): the message is not read as new evidence
      LIVE.interviewDone = true; LIVE.progress = 1;
      if (!firstTurn) LIVE.msgs.push({ role: 'engine', text: 'This interview is finished. Your last message is saved as a note. Build your diagnosis when you are ready.', ts: Date.now() });
    } else {
      LIVE.progress = j.progress || 0;
      (j.intent_tags || []).forEach(t => LIVE.tags.push(t));
      const at = LIVE.msgs.length;      // engine reply lands at this index; evidence links back to it
      (j.evidence_delta || []).forEach(e => LIVE.evidence.push(Object.assign({ _msg: at }, e)));
      // Gate A: a user correction can mark OLD evidence as superseded — the delta only carries
      // NEW items, so realign with the server's full ledger (superseded flag comes in, _msg preserved).
      try {
        const evx = await API.evidence(LIVE.sid);
        const byId = new Map(LIVE.evidence.map(e => [e.id, e]));
        LIVE.evidence = (evx.evidence || []).map(f => Object.assign({}, f, { _msg: (byId.get(f.id) || {})._msg != null ? byId.get(f.id)._msg : at }));
      } catch (e) { /* full ledger optional — the local delta is already in */ }
      const mv = j.next_move;
      if (mv) {
        // The move is the engine's decision from state (QUESTION, EVIDENCE_REQUEST, ACTION or HOLD).
        // CIR-05: `checkpoint` (early-conclusion offer, int 18 orthogonal to the step) and technical
        // status (`degraded`/`error_code`, CIR-01) also go to the UI — neither is a new step type.
        LIVE.nav = { move: mv, summary: j.navigation || null };
        LIVE.msgs.push({ role: 'engine', text: mv.text, ts: Date.now(),
          move: { kind: mv.kind, intent: mv.intent, headline: mv.headline,
                  degraded: !!mv.degraded, error_code: mv.error_code || '',
                  checkpoint: mv.checkpoint || null } });
      } else if (j.next_question) {
        LIVE.msgs.push({ role: 'engine', text: j.next_question, ts: Date.now() });   // a server without the planner
      }
    }
    // R6: a diagnosis is a checkpoint; post-diagnosis messages are processed. Notify when the checkpoint is now stale.
    if (j.checkpoint && j.checkpoint.status === 'stale' && j.change_class && j.change_class !== 'no_material_change') {
      LIVE.checkpointStale = true;
      LIVE.msgs.push({ role: 'engine', text: 'Noted. This changes what the last diagnosis was based on — reassess when you are ready.', ts: Date.now(), move: { kind: 'NOTE', intent: 'REASSESS', headline: 'Diagnosis checkpoint is out of date' } });
    }
    if (LIVE.state) LIVE.state.interview_done = LIVE.interviewDone;
    saveLive();
    return true;
  } catch (e) {
    LIVE.thinking = false;
    LIVE.err = e.message || 'Something went wrong. Try again.';
    LIVE.failedText = text;   // offered back in the input so nothing the user typed is lost
    return false;
  }
}

// MC01-2 (audit CIR-MC01 P0-B): reasoning-only recovery over a State already accepted —
// the user does NOT resend the story; the server reruns navigation+reasoning only.
async function liveRetryReasoning() {
  if (!LIVE.sid || LIVE.thinking) return false;
  LIVE.err = ''; LIVE.thinking = true; renderChatLive();
  try {
    const j = await API.retryReasoning(LIVE.sid);
    LIVE.thinking = false;
    LIVE.progress = (j && j.progress) || LIVE.progress;
    const mv = j && j.next_move;
    if (mv) {
      LIVE.nav = { move: mv, summary: j.navigation || null };
      LIVE.msgs.push({ role: 'engine', text: mv.text, ts: Date.now(),
        move: { kind: mv.kind, intent: mv.intent, headline: mv.headline,
                degraded: !!mv.degraded, error_code: mv.error_code || '',
                checkpoint: mv.checkpoint || null } });
    }
    saveLive(); renderChatLive();
    return true;
  } catch (e) {
    // A 409 from /retry_reasoning for a turn with UNDERSTANDING_FAILED is the server's HONEST
    // ANSWER (contract R7/MC02-RC-02): its recovery path is RESEND THE MESSAGE via
    // /message, not reasoning-only. Fallback: take the user text from the failed turn
    // and resend through the correct idempotent path — exactly what a manual retry does.
    const failedMsg = [...LIVE.msgs].reverse().find(m => m.role === 'user' && m.text);
    const lastMove = navCurrentMove(LIVE.nav);
    if (e && e.status === 409 && failedMsg && lastMove
        && lastMove.degraded && lastMove.error_code === 'UNDERSTANDING_FAILED') {
      LIVE.thinking = false;
      return await liveSendMessage(failedMsg.text);
    }
    LIVE.thinking = false;
    LIVE.err = (e && e.message) || 'Retry failed.';
    saveLive(); renderChatLive();
    return false;
  }
}

async function liveFinalize() {
  if (!LIVE.sid || LIVE.finalizing) return false;
  LIVE.finalizing = true; LIVE.err = ''; LIVE.stage = '';
  LIVE.finalizeAbort = new AbortController();
  renderChatLive();
  const poll = setInterval(async () => {
    try {
      const p = await API.progress(LIVE.sid);
      if (p && p.active && p.label) { LIVE.stage = p.label; updateFinalizeStage(); }
    } catch (e) { /* progress must never break the main flow */ }
  }, 1500);
  try {
    const d = await API.finalize(LIVE.sid, LIVE.finalizeAbort.signal);
    if (!d || !d.primary_constraint_id) throw new Error((d && d.detail) || 'The diagnosis did not come back. Try again.');
    LIVE.artifact = d; LIVE.explain = null; LIVE.explainState = 'idle';
    LIVE.interviewDone = true;
    if (!LIVE.baseline) LIVE.baseline = d;
    try { LIVE.state = await API.state(LIVE.sid); } catch (e) { /* keep */ }
    if (LIVE.state && LIVE.state.journey_ok) { try { LIVE.journey = await API.journey(LIVE.sid); } catch (e) { /* optional */ } }
    await liveLoadWorkspace();
    await liveLoadRoutes();
    await liveLoadReadiness();
    syncStoreFromLive();
    saveLive();
    liveRefreshMaps();
    return true;
  } catch (e) {
    LIVE.err = e.name === 'AbortError'
      ? 'Cancelled. The server may still finish in the background: reopen this map from the list if it does.'
      : (e.message || 'The diagnosis failed. Try again.');
    return false;
  } finally {
    clearInterval(poll);
    LIVE.finalizing = false; LIVE.finalizeAbort = null; LIVE.stage = '';
  }
}

/* ── Actions (Today) ───────────────────────────────────────────────────────── */
/* status: DONE | SKIPPED | BLOCKED | TODO ; outcome optional (moved | not_moved | regret | confounded) */
/* Phase 6.2: the message a person sees for a refused or failed report. The server's own detail.message wins;
   a historical action (its plan was replaced by a newer checkpoint) has an honest fallback. */
function liveReportErrorText(e) {
  const d = (e && e.detail) || null;
  if (d && d.message) return String(d.message);
  if (e && e.code === 'HISTORICAL_ACTION_READ_ONLY') return 'That action belongs to an earlier plan that a newer checkpoint replaced. Nothing was changed.';
  return (e && e.message) || 'Could not save that.';
}
/* Phase 6.2: the quiet note for an ACCEPTED report. correction = an earlier report was replaced and kept as
   history; effects_pending = durable, while derived effects settle later. Empty when neither applies. */
function liveReportNoteText(r) {
  const effects = !!(r && r.effects_pending === true);
  if (r && r.correction === true) return 'Your earlier report was corrected; the earlier one is kept in history.' + (effects ? ' Its effect on the map settles shortly.' : '');
  return effects ? 'Your report is saved. Its effect on the map settles shortly.' : '';
}
async function liveReportAction(idx, body) {
  const payload = Object.assign({}, body);
  if (payload.outcome && !payload.path) payload.path = liveActivePathKey();
  /* Phase 6.2: the report names the checkpoint whose plan the person is looking at, so the server can refuse an
     action of a replaced plan (HISTORICAL_ACTION_READ_ONLY) instead of filing it against another action.
     Omitted when no plan is known; a caller that already named one keeps it. */
  const planCheckpoint = livePlanCurrentCheckpointId();
  if (planCheckpoint && !payload.checkpoint_id) payload.checkpoint_id = planCheckpoint;
  let r = null;
  try {
    r = await API.actionReport(LIVE.sid, idx, payload);
  } catch (e) {
    /* A refused historical action changed nothing. The plan projection is re-read so the screen shows the CURRENT
       plan; the report itself is never retried. */
    if (e && e.code === 'HISTORICAL_ACTION_READ_ONLY') await liveRefreshAfterMutation({ render: false });
    throw e;
  }
  if (r && r.action && LIVE.artifact && LIVE.artifact.day_by_day) LIVE.artifact.day_by_day[idx] = r.action;
  await liveLoadWorkspace();
  syncStoreFromLive();
  /* NC-02: one version-checked refresh after the accepted execution event, so Maps/Journey read the
     same accepted revision. render:false — the caller owns the redraw (and the completion prompt). */
  await liveRefreshAfterMutation({ render: false });
  return r;
}

/* Move-centric: the ONE outcome for the whole set of actions of the current plan. Same refresh discipline as
   liveReportAction: the accepted report is never resent, and the view is re-read through the shared boundary. */
async function liveReportPlan(body) {
  const payload = Object.assign({}, body);
  if (payload.outcome && !payload.path) payload.path = liveActivePathKey();
  const planCheckpoint = livePlanCurrentCheckpointId();
  if (planCheckpoint && !payload.checkpoint_id) payload.checkpoint_id = planCheckpoint;
  let r = null;
  try {
    r = await API.planReport(LIVE.sid, payload);
  } catch (e) {
    if (e && e.code === 'HISTORICAL_ACTION_READ_ONLY') await liveRefreshAfterMutation({ render: false });
    throw e;
  }
  if (r && r.plan_report && LIVE.artifact) LIVE.artifact.plan_report = Object.assign({}, LIVE.artifact.plan_report || {}, r.plan_report);
  await liveLoadWorkspace();
  syncStoreFromLive();
  await liveRefreshAfterMutation({ render: false });
  return r;
}

/* ── Paths ─────────────────────────────────────────────────────────────────── */
/* The engine decides which Possible Paths exist (0, 1 or N) and their status (feasibility x lifecycle -> OPEN,
 * TEST_FIRST, NOT_YET or STOP). The UI reads `possible_paths` and never assumes a count or a list of names. */
function livePathSet() { return (LIVE.artifact || {}).possible_paths || { paths: [], unresolved: [] }; }
/* An artifact older than the current navigation schema carries no trustworthy path result: the engine marks it
 * (`navigation.status === 'LEGACY'`). Its empty list is NOT "no paths" and must never be shown as that. */
function liveLegacyNav() { const n = (LIVE.artifact || {}).navigation; return n && n.status === 'LEGACY' ? n : null; }
function pathStatusOf(p) {
  // The engine's status already carries lifecycle. Between two diagnoses a fresh "regret" report can stop a path
  // before the server re-reads it: that lifecycle overlay (the user's own decision) is applied here, and only that.
  const ov = LIVE.workspace && LIVE.workspace.path_states && LIVE.workspace.path_states[p.path_id];
  if (ov && ov.outcome_state === 'STOPPED') return 'STOP';
  // One reality for map, readiness and NextMove (doc 14 §10.1): when the adjudicated projection is in, its
  // per-path status wins — a disputed check (settled=false) is UNDETERMINED there even if the raw PathSet
  // snapshot predates the dispute. The raw status stays the fallback until the projection has loaded.
  const proj = LIVE.projection;
  if (proj && proj.navigation && proj.navigation.status === 'CURRENT') {
    const pp = (proj.paths || []).find(x => x.key === p.path_id);
    if (pp && pp.status) return pp.status;
  }
  return p.status;
}
function liveActivePathKey() {
  const paths = livePathSet().paths || [];
  if (LIVE.activePath && paths.some(p => p.path_id === LIVE.activePath)) return LIVE.activePath;
  const rank = { OPEN: 0, TEST_FIRST: 1, NOT_YET: 2, STOP: 3 };
  const sorted = paths.map((p, i) => ({ p, i })).sort((a, b) => (rank[pathStatusOf(a.p)] - rank[pathStatusOf(b.p)]) || (a.i - b.i));
  return sorted.length ? sorted[0].p.path_id : '';
}
function liveSetActivePath(key) {
  LIVE.activePath = key; saveLive(); syncStoreFromLive();
}

/* Follow-up cycle (journey loop): open the chat with the previous session as prior. The session itself
 * is created when the user sends their first update, so nothing is created for a click that goes nowhere. */
function liveStartFollowUp() {
  if (!LIVE.sid) return;
  LIVE.pendingPrior = LIVE.sid;
  LIVE.sid = ''; LIVE.artifact = null; LIVE.state = null; LIVE.journey = null; STORE.viewStep = 0;
  LIVE.msgs = [{ role: 'engine', local: true, ts: Date.now(),
    text: 'Welcome back. Tell us what happened since your last check-in: what you did, who replied, and what changed in your income.' }];
  LIVE.evidence = []; LIVE.tags = []; LIVE.nav = null; LIVE.progress = 0; LIVE.interviewDone = false;
  LIVE.err = ''; LIVE.failedText = '';
  STORE.chatEvidenceOpen = false;
  syncStoreFromLive();
}
