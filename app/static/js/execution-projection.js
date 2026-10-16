/* Execution presentation projection (NC-01). READ-ONLY, typed, source-referenced.

   Why this file exists: Maps used to read `STORE.moveStepsDone` — prototype-local client state that
   no live mutation ever wrote — as if it were execution truth. This module replaces that with ONE
   honest projection over the canonical sources:
     PLAN_ACTION    -> diagnosis.day_by_day[idx]      (the Moves checklist record)
     ROUTE_NODE     -> LIVE.routes route node          (execution ledger view)
     CANONICAL_MOVE -> LIVE.moves / experience.moves   (Move lifecycle)
   Objects are NEVER correlated by title, text similarity, display position or path name. A source
   that carries no valid relation returns the honest absence instead of a fabricated one. Nothing here
   writes, mutates, ranks paths, or infers satisfaction. */

const EXEC_KIND = Object.freeze({
  PLAN_ACTION: 'PLAN_ACTION',
  ROUTE_NODE: 'ROUTE_NODE',
  CANONICAL_MOVE: 'CANONICAL_MOVE',
  /* Phase 7: the canonical Move's OWN action. This is the live execution source for Move work; a
     PLAN_ACTION row is legacy history and never stands in for it. */
  MOVE_ACTION: 'MOVE_ACTION'
});

function execRefPlanAction(actionIndex) {
  return { kind: EXEC_KIND.PLAN_ACTION, sessionId: LIVE.sid || '', actionIndex: actionIndex };
}
function execRefRouteNode(routeId, nodeId) {
  return { kind: EXEC_KIND.ROUTE_NODE, routeId: String(routeId), nodeId: String(nodeId) };
}
function execRefMove(moveId) {
  return { kind: EXEC_KIND.CANONICAL_MOVE, moveId: String(moveId) };
}
function execRefMoveAction(moveId, actionId) {
  return { kind: EXEC_KIND.MOVE_ACTION, moveId: String(moveId), actionId: String(actionId) };
}
function execRefKey(ref) {
  if (!ref) return '';
  if (ref.kind === EXEC_KIND.PLAN_ACTION) return 'pa:' + (ref.sessionId || '') + ':' + ref.actionIndex;
  if (ref.kind === EXEC_KIND.ROUTE_NODE) return 'rn:' + ref.routeId + ':' + ref.nodeId;
  if (ref.kind === EXEC_KIND.CANONICAL_MOVE) return 'mv:' + ref.moveId;
  if (ref.kind === EXEC_KIND.MOVE_ACTION) return 'ma:' + ref.moveId + ':' + ref.actionId;
  return '';
}
function execIsHold(it) { return /DIGANTUNG/i.test(String((it && it.text) || it || '')); }

/* ── PLAN_ACTION ─────────────────────────────────────────────────────────── */
function livePlanActionItems() {
  const items = (LIVE.artifact && LIVE.artifact.day_by_day) || [];
  return items.map((it, i) => ({ idx: i, item: it, hold: execIsHold(it), text: String((it && it.text) || '') }));
}
function livePlanActionState(actionIndex) {
  const it = (LIVE.artifact && LIVE.artifact.day_by_day && LIVE.artifact.day_by_day[actionIndex]) || null;
  if (!it) return null;
  const status = String(it.status || 'TODO');
  /* DONE != SKIPPED: `done` stays the CLOSED predicate existing consumers depend on, while
     `executed` (DONE only) and `closed` make the distinction explicit for new callers. */
  const executed = status === 'DONE';
  const skipped = status === 'SKIPPED';
  return {
    ref: execRefPlanAction(actionIndex), source: EXEC_KIND.PLAN_ACTION,
    status: status, done: executed || skipped, closed: executed || skipped,
    executed: executed, skipped: skipped,
    blocked: status === 'BLOCKED', outcome: String(it.outcome || ''), hasOutcome: !!it.outcome,
    reportedAt: it.reported_at || null, doneAt: it.done_at || null, note: String(it.note || '')
  };
}

/* ── PLAN RECORD (versioned; NC-R5/NC-R7) ─────────────────────────────────
   The server carries the recorded plan TOGETHER with the checkpoint that bears it: `current` plus
   up to 3 replaced versions, each archived with its own status/outcome (`LIVE.experience.plan`).
   A version is read as a whole: two versions are never merged, re-keyed or correlated by title,
   text similarity or position. */
function livePlanScopeLabel(record) {
  if (!record) return '';
  const v = (record.checkpoint_version != null) ? record.checkpoint_version : record.version;
  if (v == null || v === '') return '';
  return 'on the plan from checkpoint v' + String(v);
}
/* The accepted checkpoint id, taken from the canonical read model. `liveCheckpointId` is owned by the
   experience client; while it is absent the checkpoint/revision/plan records answer instead. */
function liveCurrentCheckpointId() {
  if (typeof liveCheckpointId === 'function') {
    try { const v = liveCheckpointId(); if (v) return String(v); } catch (e) { /* fall through */ }
  }
  const cp = (LIVE.experience && LIVE.experience.checkpoint) || null;
  if (cp && cp.checkpoint_id) return String(cp.checkpoint_id);
  const rev = (LIVE.experience && LIVE.experience.revision) || null;
  if (rev && rev.checkpoint_id) return String(rev.checkpoint_id);
  const plan = (LIVE.experience && LIVE.experience.plan) || null;
  if (plan && plan.current && plan.current.checkpoint_id) return String(plan.current.checkpoint_id);
  return '';
}
function liveExperiencePlanRecord() {
  return (LIVE.experience && LIVE.experience.plan) || null;
}
/* Phase 6.2: the checkpoint whose plan the person is looking at (plan.current, the recorded plan of the
   latest checkpoint). Empty when no plan is known, so a report then omits checkpoint_id. */
function livePlanCurrentCheckpointId() {
  const cur = (LIVE.experience && LIVE.experience.plan && LIVE.experience.plan.current) || null;
  return (cur && cur.checkpoint_id) ? String(cur.checkpoint_id) : '';
}
/* One recorded plan action, exactly as recorded: DONE, SKIPPED and a reported outcome stay separate. */
function livePlanRecordActions(record) {
  return ((record && record.actions) || []).map(function (a) {
    const status = String((a && a.status) || 'TODO').toUpperCase();
    const executed = status === 'DONE';
    const skipped = status === 'SKIPPED';
    return {
      label: String((a && a.text) || ''), status: status,
      executed: executed, skipped: skipped, done: executed || skipped,
      outcome: String((a && a.outcome) || ''), reportedAt: (a && a.reported_at) || null
    };
  });
}
/* Honest counts with the same meaning as the server's plan_counts; the server's own numbers win. */
function livePlanRecordCounts(record, actions) {
  const rows = actions || livePlanRecordActions(record);
  const n = rows.length;
  const executed = rows.filter(a => a.executed).length;
  const skipped = rows.filter(a => a.skipped).length;
  const blocked = rows.filter(a => a.status === 'BLOCKED').length;
  const open = n - executed - skipped - blocked;
  const reported = rows.filter(a => a.outcome || a.reportedAt).length;
  const computed = { total: n, done: executed, executed: executed, skipped: skipped, blocked: blocked,
    open: open, reported: reported,
    complete: n > 0 && open === 0 && blocked === 0, executed_all: n > 0 && executed === n };
  const c = (record && record.counts) || null;
  return (c && typeof c === 'object') ? Object.assign({}, computed, c) : computed;
}
function livePlanRecordModel(record, fallbackLabel) {
  const actions = livePlanRecordActions(record);
  return {
    label: livePlanScopeLabel(record) || (fallbackLabel || ''),
    checkpointId: (record && record.checkpoint_id) || null,
    checkpointVersion: (record && record.checkpoint_version != null) ? record.checkpoint_version : null,
    actions: actions, counts: livePlanRecordCounts(record, actions)
  };
}
/* The newest REPLACED plan that actually carries recorded steps. An archived version with nothing on
   it is not shown as a plan (no invented "0 of N"); when none carries steps the answer is null. */
function liveHistoricalPlanModel(plan) {
  const rows = (plan && plan.superseded) || [];
  for (let i = 0; i < rows.length; i++) {
    const rec = rows[i] || {};
    const actions = livePlanRecordActions(rec);
    const counts = livePlanRecordCounts(rec, actions);
    if (!((counts.executed || 0) + (counts.skipped || 0) + (counts.reported || 0))) continue;
    const cv = (rec.checkpoint_version != null && rec.checkpoint_version !== '') ? rec.checkpoint_version : null;
    const rbv = (rec.replaced_by_version != null && rec.replaced_by_version !== '') ? rec.replaced_by_version : null;
    const parts = [];
    if (cv != null) parts.push('plan from checkpoint v' + String(cv));
    if (rbv != null) parts.push('replaced in v' + String(rbv));
    return { label: parts.length ? parts.join(', ') : 'replaced plan',
      checkpointId: rec.checkpoint_id || null, checkpointVersion: cv, replacedByVersion: rbv,
      actions: actions, counts: counts };
  }
  return null;
}

/* ── ROUTE_NODE ──────────────────────────────────────────────────────────── */
function liveRouteNodeState(routeId, nodeId) {
  const routes = (LIVE.routes && LIVE.routes.routes) || [];
  const r = routes.find(x => String(x.route_id) === String(routeId));
  if (!r) return null;
  const node = (r.nodes || []).find(n => String(n.node_id) === String(nodeId)) || null;
  const fr = (r.frontier || []).find(e => String(e.node) === String(nodeId)) || null;
  const executionView = (node && node.execution_view) || '';
  const frontierKind = fr ? fr.kind : null;
  const view = executionView || (frontierKind === 'VERIFY' ? 'EXECUTED' : 'NOT_STARTED');
  return {
    ref: execRefRouteNode(routeId, nodeId), source: EXEC_KIND.ROUTE_NODE,
    executionView: executionView, frontierKind: frontierKind, view: view,
    done: view === 'EXECUTED', onFrontier: !!fr,
    /* execution != evidence: a reported node is VERIFY while its requirement stays unresolved. */
    verifyPending: view === 'EXECUTED' && frontierKind === 'VERIFY', satisfied: false,
    lineageStatus: r.lineage_status || '', applicability: ((r.applicability || {}).status) || ''
  };
}

/* ── CANONICAL_MOVE ──────────────────────────────────────────────────────── */
function liveCanonicalMoveState(moveId) {
  const fromMoves = (LIVE.moves && LIVE.moves.moves) || [];
  const fromExp = (LIVE.experience && LIVE.experience.moves) || [];
  const m = fromMoves.find(x => String(x.move_id) === String(moveId)) || fromExp.find(x => String(x.move_id) === String(moveId));
  if (!m) return null;
  const hist = Array.isArray(m.history) ? m.history : [];
  const prog = (m.progress && typeof m.progress === 'object') ? m.progress : null;
  return {
    ref: execRefMove(moveId), source: EXEC_KIND.CANONICAL_MOVE,
    lifecycle: String(m.lifecycle || 'PLANNED').toUpperCase(),
    executed: !!m.executed_ts || hist.some(h => h && h.state === 'EXECUTED'),
    hasOutcome: !!(m.outcome_report && m.outcome_report.outcome) || !!m.outcome
      || hist.some(h => h && h.state === 'OBSERVED'),
    /* The Move view carries the verdict as a plain string; a legacy summary shape carried an
       object. Both are read honestly, and an absent verdict stays null. */
    assessment: (typeof m.assessment === 'string' ? m.assessment
      : ((m.assessment && m.assessment.verdict) || null)),
    /* Phase 7: the Move carries its own action list and honest counts. */
    actions: liveMoveActionItems(m),
    progress: prog || { total: 0, done: 0, open: 0, complete: false },
    pathId: m.linked_path_id || null,
    predecessorMoveId: m.predecessor_move_id || null
  };
}

/* ── MOVE_ACTION: one action of one canonical Move ──────────────────────────
   The row is read from the Move's OWN action list (same move_id/action_id the server issues), so the
   checklist the person executes, the map node and the journey event all name the SAME identity. No
   title matching, no array-order association, no frontend-issued id. */
function liveMoveActionItems(mv) {
  const acts = (mv && Array.isArray(mv.actions)) ? mv.actions : [];
  return acts.map(function (a, i) {
    return { idx: i, action: a, key: String(a.action_id || ''),
      moveId: String((mv && mv.move_id) || a.move_id || ''),
      actionId: String(a.action_id || ''), text: String(a.title || '') };
  }).filter(function (a) { return a.actionId; });
}
function liveMoveActionState(moveId, actionId) {
  const mv = liveMoveById(moveId);
  const a = (mv && (mv.actions || []).find(function (x) {
    return String(x.action_id) === String(actionId);
  })) || null;
  if (!a) return null;
  const status = String(a.status || 'TODO').toUpperCase();
  const executed = status === 'DONE';
  const skipped = status === 'SKIPPED';
  return {
    ref: execRefMoveAction(moveId, actionId), source: EXEC_KIND.MOVE_ACTION,
    status: status, done: executed, closed: executed || skipped, executed: executed, skipped: skipped,
    blocked: status === 'BLOCKED', required: a.required !== false,
    title: String(a.title || ''), instruction: String(a.instruction || ''), note: String(a.note || ''),
    dependsOn: Array.isArray(a.depends_on_action_ids) ? a.depends_on_action_ids : [],
    completedAt: (a.completed_at != null) ? a.completed_at : null,
    /* The Move this action belongs to is the ONLY owner of the overall result. */
    moveId: String(moveId), actionId: String(actionId)
  };
}
/* One canonical Move as the checklist context: counts, the row to act on next, and whether every
   REQUIRED action is genuinely done (the condition the server uses to advance the Move). */
function liveMoveContextSummary(mv) {
  if (!mv) return null;
  const items = liveMoveActionItems(mv);
  const states = items.map(function (a) { return liveMoveActionState(mv.move_id, a.actionId); }).filter(Boolean);
  const open = states.filter(function (s) { return s.status === 'TODO'; });
  const done = states.filter(function (s) { return s.executed; });
  const skipped = states.filter(function (s) { return s.skipped; });
  const blocked = states.filter(function (s) { return s.blocked; });
  const required = states.filter(function (s) { return s.required; });
  const requiredOpen = required.filter(function (s) { return s.status !== 'DONE'; });
  const lifecycle = String(mv.lifecycle || 'PLANNED').toUpperCase();
  return {
    moveId: String(mv.move_id || ''), objective: String(mv.objective || ''),
    lifecycle: lifecycle, actionsEditable: mv.actions_editable !== false,
    total: states.length, required: required.length, done: done.length, skipped: skipped.length,
    blocked: blocked.length, open: open.length, states: states,
    requiredOpen: requiredOpen.length,
    complete: required.length > 0 && requiredOpen.length === 0,
    firstOpen: open[0] || null,
    lastDone: done.length ? done[done.length - 1] : null,
    outcome: (mv.outcome_report && mv.outcome_report.outcome) || null,
    hasOutcome: !!(mv.outcome_report && (mv.outcome_report.outcome || mv.outcome_report.note))
  };
}

function liveExecutionState(ref) {
  if (!ref) return null;
  if (ref.kind === EXEC_KIND.PLAN_ACTION) return livePlanActionState(ref.actionIndex);
  if (ref.kind === EXEC_KIND.ROUTE_NODE) return liveRouteNodeState(ref.routeId, ref.nodeId);
  if (ref.kind === EXEC_KIND.CANONICAL_MOVE) return liveCanonicalMoveState(ref.moveId);
  if (ref.kind === EXEC_KIND.MOVE_ACTION) return liveMoveActionState(ref.moveId, ref.actionId);
  return null;
}
function liveExecutionDone(ref) {
  const st = liveExecutionState(ref);
  return !!(st && st.done);
}

/* ── The current work context (the Moves checklist) ──────────────────────── */
function liveWorkContextSummary() {
  const states = livePlanActionItems().filter(a => !a.hold)
    .map(a => livePlanActionState(a.idx)).filter(Boolean);
  const open = states.filter(s => !s.done);
  const closed = states.filter(s => s.closed);
  const executed = states.filter(s => s.executed);
  const lastDone = [...states].reverse().find(s => s.done) || null;
  /* The report target prefers a step with NO recorded outcome, so adding or correcting an outcome
     stays reachable once every step is closed. */
  const withoutOutcome = states.filter(s => !s.hasOutcome);
  const reportTarget = withoutOutcome.filter(s => !s.closed)[0] || withoutOutcome[0] || null;
  const plan = liveExperiencePlanRecord();
  return {
    /* `done` keeps the CLOSED meaning existing consumers depend on; executed and skipped are
       reported separately and never folded back into it. allDone == every step CLOSED,
       allExecuted == every step actually executed. */
    total: states.length, done: closed.length, open: open.length,
    executed: executed.length, skipped: states.filter(s => s.skipped).length,
    blocked: states.filter(s => s.blocked).length, closed: closed.length,
    allDone: states.length > 0 && open.length === 0,
    allExecuted: states.length > 0 && executed.length === states.length,
    allClosed: states.length > 0 && closed.length === states.length,
    hasAnyOutcome: states.some(s => s.hasOutcome),
    lastDone: lastDone, firstOpen: open[0] || null,
    reportIndex: reportTarget ? reportTarget.ref.actionIndex
      : (open.length ? open[0].ref.actionIndex : (lastDone ? lastDone.ref.actionIndex : null)),
    /* A version label exists only where the PLAN record carries one; a checkpoint version is never
       borrowed to label artefact-derived counts. */
    planScope: livePlanScopeLabel((plan && plan.current) || null)
  };
}
/* A stable key for "the report prompt was already dismissed in this work context". The accepted
   checkpoint id belongs in the key: a dismissal or submission recorded against the OLD plan must not
   suppress the prompt for the plan a reassessment just committed. */
function liveReportContextKey() {
  const sum = liveWorkContextSummary();
  return [LIVE.sid || '', liveActivePathKey(), liveCurrentCheckpointId(),
    sum.total, sum.executed, sum.skipped].join(':');
}
/* The contextual reporting invitation is offered only when every applicable action in the current
   context is accepted as complete, no outcome is on record yet, and the prompt was not dismissed. */
/* Phase 7: the completion prompt belongs to the CANONICAL MOVE. It opens when the Move's required
   actions are genuinely done (or the server already recorded EXECUTED) and no result is on record
   yet; deferring stays possible, and the dismissal is scoped to that exact move state. */
function liveMoveReportContextKey(moveId) {
  const mc = liveMoveContextSummary(liveMoveById(moveId));
  return [LIVE.sid || '', String(moveId || ''), mc ? mc.lifecycle : '',
    mc ? mc.done : '', mc ? mc.skipped : '', mc ? mc.blocked : ''].join(':');
}
function liveMovesReportContext() {
  const mv = (typeof liveMoveOutcomeTarget === 'function') ? liveMoveOutcomeTarget() : null;
  const mc = liveMoveContextSummary(mv);
  if (mc && mc.moveId) {
    const key = liveMoveReportContextKey(mc.moveId);
    if (!mc.complete && mc.lifecycle !== 'EXECUTED') return null;
    if (STORE.movesReportDismissed && STORE.movesReportDismissed === key) return null;
    return Object.assign({}, mc, { reportContextKey: key, canonical: true, outcome: mc.outcome });
  }
  const sum = liveWorkContextSummary();
  /* An already-recorded outcome does NOT close the context: the person must still be able to add or
     correct an outcome for the other actions. The prompt hides only after it was dismissed/submitted. */
  if (!sum.total || !sum.allDone || sum.reportIndex == null) return null;
  if (STORE.movesReportDismissed && STORE.movesReportDismissed === liveReportContextKey()) return null;
  return sum;
}

/* ── Action steps of ONE canonical Move, for Maps ───────────────────────────
   Phase 7: the steps drawn on the map are the Move's OWN action rows, addressed by move_id +
   action_id. A Move is attributed to a path only through its declared linked_path_id; a Move with no
   path binding is never attributed to a path by position or title.

   The legacy day_by_day plan is NOT a step source here any more - it carries no path_id and no
   canonical Move identity, so drawing it as the path's current work would fabricate an attribution.
   It stays visible as history on the Moves screen and in Journey. */
function liveMoveStepsForPath(pathId, moveId) {
  if (!LIVE.artifact) return [];
  const mv = moveId ? liveMoveById(moveId) : liveCurrentMoveForPath(pathId);
  if (!mv) return [];
  const bound = mv.linked_path_id ? String(mv.linked_path_id) : '';
  if (bound && pathId && String(pathId) !== bound) return [];
  return liveMoveActionItems(mv).map(function (a) {
    const st = liveMoveActionState(mv.move_id, a.actionId) || {};
    return {
      id: 'ma-' + a.actionId, idx: a.idx, plan: false, moveId: String(mv.move_id),
      actionId: a.actionId, required: st.required !== false,
      label: (typeof brief === 'function') ? brief(a.text, 68) : a.text,
      instruction: String((a.action && a.action.instruction) || a.text),
      __exec: execRefMoveAction(mv.move_id, a.actionId)
    };
  });
}

/* Recorded plan/route progress for the Maps workspace. This is NOT a change claim: it reports what is
   on the execution record (no fabrication, no node invention). NC-R5/NC-R7: it reads the VERSIONED
   plan record, so a reassessment that replaced a plan leaves the previous version visible instead of
   silently turning a recorded "3 of 3" into "0 of N". Versions are never merged or re-mapped. */
function liveRecordedProgressModel() {
  const plan = liveExperiencePlanRecord();
  const planCurrent = (plan && plan.current) || null;
  let current;
  if (planCurrent) {
    current = livePlanRecordModel(planCurrent, 'on the current plan');
  } else {
    /* No plan record (an older payload, or no plan yet): today's artefact read, honestly labelled. */
    const cp = (LIVE.experience && LIVE.experience.checkpoint) || null;
    const actions = livePlanActionItems().filter(function (a) { return !a.hold; }).map(function (a) {
      const st = livePlanActionState(a.idx) || {};
      return { label: a.text, status: st.status || 'TODO', executed: !!st.executed, skipped: !!st.skipped,
        done: !!st.done, outcome: st.outcome || '', reportedAt: st.reportedAt || null };
    });
    current = {
      /* No plan record to label with: the honest label is the scope, not a borrowed version. */
      label: 'on the current plan',
      checkpointId: liveCurrentCheckpointId() || null,
      checkpointVersion: (cp && cp.version != null) ? cp.version : null,
      actions: actions, counts: livePlanRecordCounts(null, actions)
    };
  }
  const historical = liveHistoricalPlanModel(plan);

  const routes = (LIVE.routes && LIVE.routes.routes) || [];
  const verify = [];
  routes.forEach(function (r) {
    if (((r.applicability || {}).status) !== 'APPLIES' || r.lineage_status !== 'OPEN') return;
    (r.nodes || []).forEach(function (n) {
      if (n && n.execution_view === 'EXECUTED') {
        verify.push({ routeId: r.route_id, nodeId: n.node_id,
          label: (((n.i18n || {}).en || {}).activity) || n.activity || n.node_id });
      }
    });
  });
  if (!current.actions.length && !historical && !verify.length) return null;
  const counts = current.counts;
  const closed = (counts.executed || 0) + (counts.skipped || 0);
  /* `done`/`allDone` keep their historical "closed" meaning for the existing banner; executed,
     skipped, allExecuted and allClosed carry the exact split, from the CURRENT plan only. */
  return {
    current: current, historical: historical, verify: verify,
    total: counts.total, done: closed, open: counts.open, allDone: !!counts.complete,
    executed: counts.executed, skipped: counts.skipped, blocked: counts.blocked, closed: closed,
    allExecuted: !!counts.executed_all, allClosed: !!counts.complete,
    planScope: current.label, actions: current.actions
  };
}

/* ── Change summary model (NC-05/NC-13), from the durable Experience read model ──
   Never inferred from a checkbox, an outcome label, a new check-in or a re-render. */
function liveChangeEntryLabel(entry) {
  const refs = (entry && entry.refs) || {};
  const paths = (typeof livePathModels === 'function') ? livePathModels() : [];
  const p = refs.path_id ? paths.find(x => x.key === refs.path_id) : null;
  if (refs.move_id) return 'Move' + (p ? ' on ' + p.name : ' ' + refs.move_id);
  if (refs.route_node_id) return (p ? p.name : (refs.path_id || 'Path')) + ' · requirement ' + refs.route_node_id;
  if (refs.path_id) return p ? p.name : refs.path_id;
  return String((entry && entry.id) || '');
}
function liveChangeSummaryModel() {
  if (LIVE.experienceError) {
    return { kind: 'UNAVAILABLE', title: 'Your result is on record.',
      body: "The latest map couldn't be refreshed. Your record was saved; refresh the view to see it.",
      retry: true, changeSet: null };
  }
  const cs = (typeof liveExperienceChangeSet === 'function') ? liveExperienceChangeSet() : null;
  if (!cs) return null;
  if (cs.baseline || cs.no_material_change) {
    return { kind: 'NONE', title: 'Your result is on record.', body: 'No path status has changed yet.', changeSet: cs };
  }
  const changed = (cs.changed || []).map(e => ({ label: liveChangeEntryLabel(e), from: e.from, to: e.to,
    pathId: (e.refs && e.refs.path_id) || null }));
  if (cs.topology_changed || changed.length) {
    return { kind: 'CHANGED', title: 'Your map has changed.', body: '', changed: changed, changeSet: cs };
  }
  return { kind: 'RECORDED', title: 'Your result is on record.', body: 'No path status has changed yet.', changeSet: cs };
}

/* ── The reassessment RESULT (NC-R7) ───────────────────────────────────────
   Read-only interpretation of a COMMITTED re-synthesis, built only from canonical read-model data:
   the change set, the checkpoint, the versioned plan, the canonical Moves and the presented decision.
   The classification below is the ONLY inference allowed. It never invents a Move, a path, a node or
   an event, and it never retells a technical failure as a business outcome (or the reverse). */
function livePresentedDecision() {
  const mv = navCurrentMove(LIVE.nav);
  if (!mv) return { move: null, kind: '', moveId: '' };
  return { move: mv, kind: String(mv.kind || '').toUpperCase(),
    moveId: mv.move_id ? String(mv.move_id) : '' };
}
/* A canonical Move record: LIVE.moves carries the full ledger, experience.moves the summaries. */
function liveCanonicalMoveRecord(moveId) {
  const id = String(moveId || '');
  if (!id) return null;
  const full = (LIVE.moves && LIVE.moves.moves) || [];
  const m = full.find(x => String(x.move_id) === id);
  if (m) return m;
  const sums = (LIVE.experience && LIVE.experience.moves) || [];
  return sums.find(x => String(x.move_id) === id) || null;
}
/* A Path's display name from the canonical path records; the raw id when no name exists. */
function livePathLabelById(pathId) {
  if (!pathId) return '';
  const paths = (typeof livePathModels === 'function') ? livePathModels() : [];
  const p = paths.find(x => x.key === pathId || x.id === pathId);
  if (p && p.name) return String(p.name);
  const expPaths = (LIVE.experience && LIVE.experience.paths) || [];
  const ep = expPaths.find(x => String(x.path_id) === String(pathId));
  if (ep && (ep.title || ep.name)) return String(ep.title || ep.name);
  return String(pathId);
}
/* The degraded-source names the read model reports. A degraded presented decision is a technical
   failure, never a business HOLD (CIR-INV-11). */
function liveProjectionDegradedSources() {
  const out = [];
  const push = function (s) { const t = String(s == null ? '' : s).trim(); if (t && out.indexOf(t) < 0) out.push(t); };
  const exp = LIVE.experience || null;
  const integ = (exp && exp.integrity) || null;
  if (integ) {
    if (integ.compatible === false) push('projection');
    ((integ.degraded_sources) || []).forEach(push);
  }
  (((exp && exp.degraded_sources) || [])).forEach(push);
  const mv = navCurrentMove(LIVE.nav);
  if (mv && mv.degraded) push(mv.error_code || 'technical failure');
  return out;
}
/* The plan version this checkpoint replaced, from the archive rows themselves (never computed). */
function livePreviousPlanVersion(plan, cp) {
  const rows = (plan && plan.superseded) || [];
  if (!rows.length) return null;
  const match = (cp && cp.checkpoint_id)
    ? rows.find(r => String((r && r.replaced_by) || '') === String(cp.checkpoint_id)) : null;
  const rec = match || rows[0] || null;
  const v = rec && rec.checkpoint_version;
  return (v == null || v === '') ? null : v;
}
/* The explanation behind a result, as a sentence a person can act on. It is a PROJECTION of canonical
   records: the path status words, the requirement the current decision is about (resolved by its
   canonical id inside the path the decision names - never by text similarity) and that requirement's
   own satisfaction word, so "unknown" never reads as "absent". Raw engine identifiers (cause classes,
   stage names, requirement ids, reason trails) are deliberately NOT shown: "causes: execution_revision ·
   need: requirement:commercial.willingness_to_pay_at_new_price" is not an explanation, it is a log line. */
function liveReassessmentReasonText(cs, cp, mv) {
  const parts = [];
  const paths = (typeof livePathModels === 'function') ? (livePathModels() || []) : [];
  if (paths.length) {
    const n = function (w) { return paths.filter(function (p) { return p.status_display === w; }).length; };
    const open = n('OPEN'), test = n('TEST FIRST'), notyet = n('NOT YET'), stop = n('STOP');
    /* Only stated when NOTHING changed: the changed rows are rendered separately by the notice, so
       repeating the counts after a change would be redundant and reads like a claim about the change
       the rows already explain. The words are the map's own status words, so they match the legend. */
    const moved = !!(cs && (cs.topology_changed || (cs.changed || []).length));
    const words = [];
    if (open) words.push(open + ' open');
    if (test) words.push(test + ' test first');
    if (notyet) words.push(notyet + ' not yet');
    if (stop) words.push(stop + ' stopped');
    if (words.length && !moved) parts.push('No path status has changed: ' + words.join(', ') + '.');
  }
  const kind = String((mv && mv.kind) || '');
  const needRaw = (mv && mv.reason && mv.reason.need_id) ? String(mv.reason.need_id) : '';
  const needId = needRaw.indexOf('requirement:') === 0 ? needRaw.slice('requirement:'.length) : needRaw;
  const asksForInformation = (kind === 'EVIDENCE_REQUEST' || kind === 'QUESTION');
  const named = (mv && mv.path_id) ? paths.filter(function (p) { return p.id === mv.path_id; }) : [];
  const pools = named.length ? named : (asksForInformation ? paths : []);
  let req = null, pathTitle = '';
  for (let i = 0; i < pools.length && !req; i++) {
    const rs = pools[i].requirements || [];
    if (needId) req = rs.filter(function (r) { return r.id === needId; })[0] || null;
    if (req) pathTitle = pools[i].title || '';
  }
  if (!req && asksForInformation) {
    for (let i = 0; i < pools.length && !req; i++) {
      const rs = pools[i].requirements || [];
      req = rs.filter(function (r) { return r.satisfaction !== 'PRESENT'; })[0] || null;
      if (req) pathTitle = pools[i].title || '';
    }
  }
  if (req) {
    const W = { PRESENT: 'Confirmed', PARTIAL: 'Partly shown', UNKNOWN: 'Not known yet', ABSENT: 'Not in place' };
    const word = W[String(req.satisfaction || '').toUpperCase()] || 'Not known yet';
    parts.push('Still unresolved' + (pathTitle ? ' on ' + pathTitle : '') + ': ' + String(req.label || '') + ' - ' + word.toLowerCase() + '.');
  }
  return parts.join(' ');
}
function liveReassessmentResultModel() {
  const exp = LIVE.experience || null;
  const cs = (typeof liveExperienceChangeSet === 'function') ? liveExperienceChangeSet() : null;
  const cp = (exp && exp.checkpoint) || null;
  const plan = (exp && exp.plan) || null;
  const decision = livePresentedDecision();
  const mv = decision.move;
  const checkpointVersion = (cp && cp.version != null) ? cp.version : null;
  const previousVersion = livePreviousPlanVersion(plan, cp);

  /* A read/refresh failure is reported BEFORE anything is interpreted: nothing is read out of a
     stale view, and the retry belongs to the READ only. */
  if (LIVE.experienceError || LIVE.lastRefreshFailed) {
    return { kind: 'UNAVAILABLE', title: 'Your result is on record.',
      body: (cp && cp.checkpoint_id)
        ? 'The checkpoint is recorded, but the current view could not be loaded. Refresh the view to see it.'
        : 'The current view could not be loaded. Refresh the view to try again.',
      changed: [], reason: String(LIVE.experienceError || 'The workspace could not be refreshed.'),
      nextLabel: null, nextAction: null, retry: true,
      isNewMove: false, moveId: '',
      checkpointVersion: checkpointVersion, previousVersion: previousVersion, changeSet: cs };
  }
  if (!exp || !cp || !cp.checkpoint_id) return {};
  /* A result exists only where a checkpoint superseded an earlier one; a first checkpoint is not a
     reassessment. The archived plan versions are the second canonical record of that transition. */
  if (!cp.supersedes && !((plan && plan.superseded) || []).length) return {};

  const changed = ((cs && cs.changed) || []).map(function (e) {
    return { label: liveChangeEntryLabel(e), from: (e && e.from != null) ? e.from : null,
      to: (e && e.to != null) ? e.to : null };
  });
  const addedMoves = ((cs && cs.added) || []).map(String)
    .filter(id => id.indexOf('move:') === 0).map(id => id.slice(5));
  const actionMoveId = (decision.kind === 'ACTION' && decision.moveId) ? decision.moveId : '';
  const degradedSources = liveProjectionDegradedSources();
  const navDegraded = !!(mv && mv.degraded);

  let kind = '';
  if (addedMoves.length || actionMoveId) kind = 'NEW_MOVE';
  else if (decision.kind === 'EVIDENCE_REQUEST' && !navDegraded) kind = 'EVIDENCE';
  else if (navDegraded) kind = 'DEGRADED';
  else if (decision.kind === 'HOLD' || decision.kind === 'NONE') kind = decision.kind;
  else if (cs && (cs.topology_changed || changed.length)) kind = 'CHANGED';
  else if (degradedSources.length) kind = 'DEGRADED';
  else if (cs) kind = 'UNCHANGED';
  else return {};

  const moveId = addedMoves.length ? addedMoves[0] : (actionMoveId || '');
  const moveRec = liveCanonicalMoveRecord(moveId);
  const moveLabel = (moveRec && (moveRec.objective || moveRec.title))
    ? String(moveRec.objective || moveRec.title) : String(moveId || '');
  const movePath = livePathLabelById(moveRec && moveRec.linked_path_id);
  const decisionText = mv
    ? ((typeof brief === 'function') ? brief(String(mv.headline || mv.text || ''), 110)
      : String(mv.headline || mv.text || '').slice(0, 110))
    : '';

  let title = 'Your latest assessment is ready.';
  let body = '';
  if (kind === 'NEW_MOVE') {
    const lead = addedMoves.length
      ? 'The latest assessment added a Move' : 'The current decision is an actionable Move';
    body = lead + ': ' + moveLabel + (movePath ? ', on the Path ' + movePath : '') + '.';
  } else if (kind === 'EVIDENCE') {
    body = 'The current decision asks for evidence' + (decisionText ? ': ' + decisionText : '') + '.';
  } else if (kind === 'HOLD') {
    title = 'Your latest assessment is on record.';
    body = 'The current decision is on hold' + (decisionText ? ': ' + decisionText : '') + '.';
  } else if (kind === 'NONE') {
    title = 'Your latest assessment is on record.';
    body = 'The current decision names no next step' + (decisionText ? ': ' + decisionText : '') + '.';
  } else if (kind === 'CHANGED') {
    body = 'The current view differs from the previous checkpoint.';
  } else if (kind === 'DEGRADED') {
    title = 'Your latest assessment is on record.';
    body = 'The checkpoint is recorded, but parts of the current view could not be loaded ('
      + degradedSources.join(', ') + ').';
  } else {
    title = 'Your latest assessment is on record.';
    body = (cs && cs.baseline)
      ? 'No earlier projection was recorded, so no change is claimed.'
      : 'No material change since the previous checkpoint.';
  }

  /* A next interaction only where one legitimately exists; otherwise no destination is suggested. */
  let nextLabel = null, nextAction = null;
  if (kind === 'NEW_MOVE' || (decision.kind === 'ACTION' && decision.moveId)) {
    nextLabel = 'Open Moves'; nextAction = 'moves';
  } else if (decision.kind === 'QUESTION' || decision.kind === 'EVIDENCE_REQUEST') {
    nextLabel = 'Continue in Talk'; nextAction = 'talk';
  }

  return { kind: kind, title: title, body: body, changed: changed,
    reason: liveReassessmentReasonText(cs, cp, mv),
    nextLabel: nextLabel, nextAction: nextAction,
    /* `isNewMove` is the STRONG claim: the change set ADDED this canonical move node. kind NEW_MOVE
       with isNewMove false means the presented decision is an actionable Move that already existed;
       the two body texts above say which of the two happened. */
    isNewMove: addedMoves.length > 0, moveId: String(moveId || ''),
    checkpointVersion: checkpointVersion, previousVersion: previousVersion, changeSet: cs };
}
