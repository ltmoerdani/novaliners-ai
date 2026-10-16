/* LIVE home screens: 04 Activity · 17 Diagnosis · 05 Check-in · 06a/06b/12 map change · 14 Welcome back · 16 Day review.
 * Same templates and spacing as prototype v9. Data: the real plan (day_by_day), real reports, real path states. */

function parseRpM(v) {
  // "Rp15.000.000" / "15000000" -> 15 ; "15" / "15jt" / "7,5" -> 15 / 7.5 (millions of rupiah)
  const raw = String(v == null ? '' : v).trim().toLowerCase();
  if (!raw) return null;
  const digits = raw.replace(/[^0-9.,]/g, '');
  if (!digits) return null;
  if (/^\d{1,3}(\.\d{3})+$/.test(digits) || Number(digits.replace(/[.,]/g, '')) >= 100000) return Math.round(Number(digits.replace(/[.,]/g, '')) / 100000) / 10;
  const n = Number(digits.replace(',', '.'));
  return Number.isNaN(n) ? null : n;
}
function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning.' : (h < 18 ? 'Good afternoon.' : 'Good evening.');
}

/* ── 04 · Activity ────────────────────────────────────────────────────────────── */
function otherPathRowsLive(paths, activeKey) {
  return paths.filter(p => p.key !== activeKey).map(p => {
    const right = p.status === 'NOT_YET'
      ? LOCK_NOTE(`${p.passedN} of ${p.gateN} checks passed`)
      : `<span class="status-pill ${p.status === 'OPEN' ? 'open' : (p.status === 'TEST_FIRST' ? 'test_first' : 'stop')}">${STATUS_WORD[p.status]}</span>`;
    return renderOtherPathRow(p.status, esc(p.name), right);
  }).join('');
}

function screen04Live() {
  const rs = useRoadmapStore.getState();
  const tl = getTimeline();
  const paths = livePathModels();
  const active = paths.find(p => p.key === rs.activePathId) || paths[0];
  /* Phase 7: the Moves page IS the canonical Move. mv and mc are read ONCE here from the shared read
     model; the renderer below reports what they say and never computes lifecycle authority itself. */
  const mv = (typeof liveCurrentMove === 'function') ? liveCurrentMove() : null;
  const mc = (typeof liveMoveContextSummary === 'function') ? liveMoveContextSummary(mv) : null;
  /* [Open move] on the ledger card names ONE move to show. Without a selection the page follows the
     server's current move; a selection is honoured only by its server-issued move_id. */
  const selId = STORE.movesSelectedMoveId ? String(STORE.movesSelectedMoveId) : '';
  const selMv = (selId && (!mv || String(mv.move_id) !== selId) && typeof liveMoveById === 'function') ? liveMoveById(selId) : null;
  const pageMc = (selMv && typeof liveMoveContextSummary === 'function') ? liveMoveContextSummary(selMv) : mc;
  /* P0-04/P1-05: the canonical Move ledger is an INDEPENDENT identity. It must render on every path
     through this screen — including the empty plan, the report-only plan and the completed plan — so
     it is computed once here and appended to every return below. */
  const canonicalMovesHtml = renderCanonicalMoves(liveCanonicalMoves());

  if (rs.ending) {
    const short = rs.goalRp ? Math.max(rs.goalRp - rs.earned, 0) : null;
    return renderAppShell('moves', 'Moves', `
    <div class="dest-page mv-page">
      <div class="ws-main"><div class="ws-inner"><div class="mv-main">
        ${pageMc ? mvCanonicalMoveHtml(pageMc) : ''}
        <div class="today-layout" style="grid-template-columns:minmax(0, 640px);justify-content:center;align-content:center">
          <div class="card-clean" style="padding:32px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:12px">
            <h1 class="serif-heading" style="font-size:32px">Your ${tl.horizon} days are done.</h1>
            <p style="font-size:14.5px;color:var(--ink-2);line-height:1.55;margin:0;max-width:460px">You're at ${esc(fmtM(rs.earned) || 'Rp0')} a month${rs.ending === 'success' ? ', past your goal' : (short != null ? `, ${esc(fmtM(short))} short of your goal` : '')}. Before we plan anything new, look back at what happened and choose what comes next.</p>
            <button class="btn-primary" style="margin-top:8px" onclick="renderScreen('16')">See your review →</button>
          </div>
        </div>
        ${canonicalMovesHtml}
      </div></div></div>
    </div>`);
  }

  const last = LIVE.checkins[LIVE.checkins.length - 1];
  const fresh = rs.steps.every(s => s.report || s.status !== STEP_STATUS.COMPLETED);
  /* A saved execution whose follow-up read failed keeps its own banner with the read-only retry:
     the record is saved and is never resubmitted (NC-02). */
  const banner = mvSaveNoticeHtml() + (last && fresh ? `
      <div class="today-banner">
        <span class="today-banner-icon">✓</span>
        <span style="flex:1;min-width:0">Check-in ${last.cycle} done · ${esc(last.title)}.${last.note ? ' ' + esc(last.note) : ''}</span>
      </div>` : '');
  /* The legacy plan and the route work follow the canonical Move; they never lead the page. The plan
     is reachable only as collapsed, read-only history (mvLegacyPlanHistoryHtml). */
  const v = {
    banner,
    steps: rs.steps,
    pathTitle: esc(active ? active.name : 'Your plan'),
    routeTasks: renderRouteTasks(liveRouteTasks())
  };
  const sideClosed = !!STORE.movesSideClosed;
  /* A closed move does not end the destination: the person still needs somewhere to go next.
     The frontier card (with "Ask the engine for the next move") is shown once the current move is
     finished AND its result is on record - never while a result is still pending, which is the
     honest order. */
  const nextCard = (pageMc && mvMoveNeedsNext(pageMc)) ? mvMoveFrontierHtml() : '';
  const content = `
  <div class="dest-page mv-page ws-split${sideClosed ? ' is-collapsed' : ''}">
    <div class="ws-main">
      <div class="ws-inner">
        <div class="mv-main">
          ${sideClosed ? `<div class="mv-head-actions">${wsPanelShowBtn('mv-side-toggle', 'mv-side', 'setMovesSide', 'progress and detail')}</div>` : ''}
          ${banner}
          ${mvCanonicalMoveHtml(pageMc)}
          ${nextCard}
          ${mvLegacyPlanHistoryHtml(v)}
          ${renderMovesQueues(v)}
          ${canonicalMovesHtml}
        </div>
      </div>
    </div>
    ${sideClosed ? '' : mvMovesPanel(v)}
  </div>`;
  return renderAppShell('moves', 'Moves', content);
}

/* ══════════════════════════════════════════════════════════════════════════════
   PHASE 7 — THE CANONICAL MOVE ON THE MOVES SCREEN
   A Move owns its ACTION LIST: free order, the person decides when. Only an explicit
   depends_on_action_ids restricts order, and only DONE satisfies one. Completing the required
   actions advances the SAME move server-side; the RESULT is reported against the move as a whole.
   Lifecycle words, counts and completeness are READ, never computed here.
   ══════════════════════════════════════════════════════════════════════════════ */
const MV_OUTCOME_WORD = {
  moved: 'Something moved', not_moved: 'Nothing changed yet',
  confounded: 'Something else may have caused it', regret: 'It went backwards',
  unknown: 'Too early to tell / not measured'
};
const MV_ACTION_WORD = { DONE: 'Done', SKIPPED: 'Skipped', BLOCKED: 'Blocked', TODO: 'Not started' };
const MV_MOVE_EXECUTED_LIFECYCLES = ['EXECUTED', 'OBSERVED', 'VALIDATED', 'INCONCLUSIVE', 'UNSUPPORTED'];
/* A REAL completion timestamp may be shown as a date. A plan day number is a schedule claim, so it is
   never shown anywhere on this screen. */
function mvStamp(ts) {
  const n = Number(ts);
  if (!ts || !isFinite(n) || n <= 0) return '';
  const d = new Date(n * 1000);
  if (isNaN(d.getTime())) return '';
  try { return d.toLocaleDateString(document.documentElement.lang || undefined, { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch (e) { return d.toISOString().slice(0, 10); }
}
/* The legacy plan's own completion timestamp (done_at on the row). Derived locally so no day label is
   needed; absent when the record carries none - then no date is claimed. */
function mvDoneStamp(s) {
  let ts = null;
  if (s && s.doneAt) ts = s.doneAt;
  if (!ts && s && typeof s.idx === 'number' && s.idx >= 0 && LIVE.artifact && Array.isArray(LIVE.artifact.day_by_day)) {
    const row = LIVE.artifact.day_by_day[s.idx];
    if (row && row.done_at) ts = row.done_at;
  }
  return ts ? mvStamp(ts) : '';
}
function mvOutcomeWord(o) {
  const k = String(o || '').toLowerCase();
  return MV_OUTCOME_WORD[k] || String(o || '');
}
/* The lifecycle word is the pill's whole label: the read model owns it. */
function mvMovePill(life) {
  const l = String(life || 'PLANNED').toUpperCase();
  const cls = l === 'PLANNED' ? 'not_yet' : (l === 'STARTED' ? 'test_first' : (l === 'ABANDONED' ? 'stop' : 'open'));
  return `<span class="status-pill ${cls}">${esc(l)}</span>`;
}
/* ONE action of the Move. The move_id/action_id pair is the server's own identity. Controls are only
   rendered while the list is editable, and a declared, unsatisfied dependency disables them with the
   reason said out loud - the display order itself never implies an order. */
function mvCanonicalActionRow(st, mc) {
  const moveId = String(st.moveId || mc.moveId || '');
  const actionId = String(st.actionId || '');
  if (!moveId || !actionId) return '';                 // no identity, no row: nothing is invented
  const status = String(st.status || 'TODO').toUpperCase();
  const editable = mc.actionsEditable !== false;
  const waits = (Array.isArray(st.dependsOn) ? st.dependsOn : []).map(function (depId) {
    let dep = null;
    try { dep = (typeof liveMoveActionState === 'function') ? liveMoveActionState(moveId, depId) : null; }
    catch (e) { dep = null; }
    return { id: String(depId), title: dep ? String(dep.title || '') : '', done: !!(dep && String(dep.status || '').toUpperCase() === 'DONE') };
  }).filter(function (d) { return !d.done; });
  const closed = status === 'DONE' || status === 'SKIPPED' || status === 'BLOCKED';
  const mark = status === 'DONE' ? '✓' : (status === 'SKIPPED' ? '–' : (status === 'BLOCKED' ? '!' : ''));
  const word = MV_ACTION_WORD[status] || MV_ACTION_WORD.TODO;
  /* Optional actions are named as such: the Move advances on its REQUIRED actions. */
  const wordFull = word + (st.required === false ? ' · optional' : '');
  const stamp = status === 'DONE' ? mvStamp(st.completedAt) : '';
  const waitNames = waits.map(function (d) { return d.title ? esc(d.title) : 'the action ' + esc(d.id); }).join(', ');
  const waitNote = waits.length
    ? `<p class="mv-fine">This action waits for ${waitNames}. Its controls stay disabled until that action is recorded as done - skipping or blocking it does not count.</p>`
    : '';
  const dis = waits.length ? ' disabled aria-disabled="true" style="opacity:0.5;cursor:not-allowed"' : '';
  let controls = '';
  if (editable && closed) {
    controls = `<div class="mv-actions today-actions"><button type="button" class="btn-secondary btn-sm"${dis} onclick="mvMoveAction('${esc(moveId)}','${esc(actionId)}','TODO',this)">Reopen</button></div>`;
  } else if (editable) {
    controls = `<div class="mv-actions today-actions">
      <button type="button" class="btn-primary btn-sm"${dis} onclick="mvMoveAction('${esc(moveId)}','${esc(actionId)}','DONE',this)">Record as done</button>
      <button type="button" class="btn-secondary btn-sm"${dis} onclick="mvMoveAction('${esc(moveId)}','${esc(actionId)}','SKIPPED',this)">Mark as skipped</button>
      <button type="button" class="btn-secondary btn-sm"${dis} onclick="mvMoveAction('${esc(moveId)}','${esc(actionId)}','BLOCKED',this)">Mark as blocked</button>
    </div>`;
  }
  const body = `${st.note ? `<p class="mv-fine">Recorded note: ${esc(st.note)}</p>` : ''}${waitNote}${controls}`;
  return `
  <div class="mv-action ${status === 'DONE' ? 'is-done' : ''} ${status === 'SKIPPED' ? 'is-skipped' : ''} ${status === 'BLOCKED' ? 'is-blocked' : ''}${waits.length ? ' is-waiting' : ''}" data-action-id="${esc(actionId)}">
    <div class="mv-action-head" style="cursor:default">
      <span class="mv-action-num" aria-hidden="true">${mark}</span>
      <span class="mv-action-label">${st.title ? esc(st.title) : '<span style="color:var(--ink-3)">No title is recorded for this action</span>'}<span class="sr-only"> - ${wordFull}</span>${st.instruction ? `<span class="step-note">${esc(st.instruction)}</span>` : ''}</span>
      <span class="mv-action-mark">${stamp ? esc(wordFull + ' · ' + stamp) : wordFull}</span>
    </div>
    ${body.trim() ? `<div class="mv-action-body">${body}</div>` : ''}
  </div>`;
}
/* The result of the WHOLE move. Until a result is on record the move offers the prompt exactly when
   the shared read model says one is due; after that it shows what was recorded. */
function mvMoveResultHtml(mc, life) {
  const raw = (typeof liveMoveById === 'function') ? liveMoveById(mc.moveId) : null;
  const rep = (raw && raw.outcome_report) || null;
  if (mc.hasOutcome) {
    const word = rep && rep.outcome ? mvOutcomeWord(rep.outcome) : '';
    const note = rep && rep.note ? String(rep.note) : '';
    const when = rep && rep.reported_at ? mvStamp(rep.reported_at) : '';
    return `
    <div class="mv-sec mv-report is-ready">
      <div class="section-meta-label">RECORDED RESULT</div>
      <p class="mv-body">${word ? esc(word) : 'A result is on record for this move.'}${note ? ` - ${esc(note)}` : ''}</p>
      <p class="mv-fine">${when ? 'Reported ' + esc(when) + '. ' : ''}A reported result is not a verdict: your map decides what it means.</p>
    </div>`;
  }
  const ctx = (typeof liveMovesReportContext === 'function') ? liveMovesReportContext() : null;
  const mine = (ctx && String(ctx.moveId || '') === String(mc.moveId)) ? ctx : null;
  if (mine) {
    const head = MV_MOVE_EXECUTED_LIFECYCLES.indexOf(life) >= 0 ? 'MOVE EXECUTED' : 'Every required action is done';
    return `
    <div class="mv-sec mv-report is-ready">
      <div class="section-meta-label">${head}</div>
      <h2 class="mv-report-title">What happened as a result?</h2>
      <p class="mv-body">The actions are recorded. The result belongs to this move as a whole - it does not change or undo an action.</p>
      <div class="mv-report-actions">
        <button type="button" class="btn-primary btn-sm" onclick="openMovesOutcomeReport()">Report outcome</button>
        <button type="button" class="btn-secondary btn-sm" onclick="mvDismissMoveOutcome('${esc(mine.reportContextKey || '')}')">I'll report later</button>
      </div>
    </div>`;
  }
  /* A deferred prompt is not a closed door: while this move is the report target the way back stays
     reachable, quietly, without asking again on every render. */
  const target = (typeof liveMoveOutcomeTarget === 'function') ? liveMoveOutcomeTarget() : null;
  const isTarget = !!(target && String(target.move_id) === String(mc.moveId));
  if (isTarget && (mc.complete || MV_MOVE_EXECUTED_LIFECYCLES.indexOf(life) >= 0)) {
    return `
    <div class="mv-sec mv-report">
      <div class="section-meta-label">RESULT</div>
      <p class="mv-body">The actions are recorded. You can report what happened as a result whenever you are ready.</p>
      <button type="button" class="moves-q-link" onclick="openMovesOutcomeReport()">Report outcome →</button>
    </div>`;
  }
  return '';
}
/* The canonical Move checklist. Rendered FIRST on the Moves screen; everything legacy follows it. */
function mvCanonicalMoveHtml(mc) {
  if (!mc) return mvMoveFrontierHtml();
  const life = String(mc.lifecycle || 'PLANNED').toUpperCase();
  const total = Number(mc.total) || 0;
  const done = Number(mc.done) || 0;
  const required = Number(mc.required) || 0;
  const skipped = Number(mc.skipped) || 0;
  const blocked = Number(mc.blocked) || 0;
  const editable = mc.actionsEditable !== false;
  const states = Array.isArray(mc.states) ? mc.states : [];
  const rows = states.map(function (st) { return mvCanonicalActionRow(st, mc); }).join('');
  const cur = (typeof liveCurrentMove === 'function') ? liveCurrentMove() : null;
  const isCurrent = !cur || String(cur.move_id) === String(mc.moveId);
  const facts = [];
  if (skipped) facts.push(skipped + ' skipped');
  if (blocked) facts.push(blocked + ' blocked');
  if (Number(mc.open)) facts.push(Number(mc.open) + ' not started');
  const zeroActions = total === 0
    ? `<p class="mv-body">This move has no action list, so there is nothing to complete one by one.</p>
       ${editable && (life === 'PLANNED' || life === 'STARTED')
        ? `<div class="mv-actions today-actions"><button type="button" class="btn-primary btn-sm" onclick="liveMoveEvent('${esc(mc.moveId)}','EXECUTED')">Mark this move executed</button></div>`
        : ''}`
    : '';
  return `
  <section class="mv-card mv-canonical" id="mv-current-move" data-move-id="${esc(mc.moveId)}" aria-labelledby="mv-canonical-title">
    <div class="mv-list-head" style="align-items:flex-start">
      <div style="display:flex;flex-direction:column;gap:6px;min-width:0">
        <div class="section-meta-label mb-0">YOUR MOVE</div>
        <h1 class="serif-heading" id="mv-canonical-title" style="font-size:26px;margin:0;line-height:1.25">${mc.objective ? esc(mc.objective) : 'Your move'}</h1>
      </div>
      ${mvMovePill(life)}
    </div>
    <p class="mv-fine">${done} of ${total} actions completed${required !== total ? ` · ${required} of them required` : ''}</p>
    ${isCurrent ? '' : `<p class="mv-fine">You opened this move from the list. <button type="button" class="moves-q-link" onclick="mvClearMoveSelection()">Back to your current move →</button></p>`}
    <p class="mv-body">Complete these actions whenever you are ready.</p>
    ${total ? `<p class="mv-fine">The order below is the order they were written in, not a schedule, and it does not make one action wait for another - a row only waits when it says which action it waits for.</p>
    <p class="mv-fine">Recording an action says it was done, skipped or blocked. There is no separate mark-executed: the move advances when its required actions are done.</p>` : ''}
    ${rows ? `<div class="mv-canonical-rows">${rows}</div>` : ''}
    ${facts.length ? `<p class="mv-fine">${facts.join(' · ')}</p>` : ''}
    ${total && !editable ? `<p class="mv-fine">This action list is history now: its recorded statuses can no longer be changed.${mc.hasOutcome ? ' The result on record stands.' : ''}</p>` : ''}
    ${zeroActions}
    ${mvMoveResultHtml(mc, life)}
  </section>`;
}
/* No canonical Move on record: render the frontier the server reports. A move is never invented to
   fill the page - a move awaiting its result is named as such, and everything else says why. */
/* True when the current Move is CLOSED and its result is on record, so the only thing left is the
   next piece of work. EXECUTED without a result stays false: reporting the result comes first. */
function mvMoveNeedsNext(mc) {
  if (!mc) return false;
  const l = String(mc.lifecycle || '').toUpperCase();
  if (l === 'ABANDONED' || l === 'OBSERVED' || l === 'VALIDATED' || l === 'INCONCLUSIVE' || l === 'UNSUPPORTED') return true;
  return l === 'EXECUTED' && !!mc.hasOutcome;
}
function mvMoveFrontierHtml() {
  const frontier = (LIVE.moves && LIVE.moves.frontier) || null;
  const kind = String((frontier && frontier.kind) || '');
  const headline = frontier && frontier.headline ? String(frontier.headline) : '';
  if (kind === 'MOVE_EXECUTED_RESULT_PENDING') {
    return `
    <section class="mv-card mv-canonical" id="mv-current-move" aria-labelledby="mv-canonical-title">
      <div class="section-meta-label mb-0">YOUR MOVE</div>
      <h1 class="serif-heading" id="mv-canonical-title" style="font-size:26px;margin:0;line-height:1.25">Your move is executed.</h1>
      <p class="mv-body">Report what happened.</p>
      <p class="mv-fine">Executing is a fact. The result is a separate report about the move as a whole.</p>
      <div class="mv-report-actions"><button type="button" class="btn-primary btn-sm" onclick="openMovesOutcomeReport()">Report outcome</button></div>
    </section>`;
  }
  const reason = headline
    ? headline
    : (kind === 'NEXT_MOVE_PENDING'
      ? 'The last move is finished and no next move is authorized yet.'
      : 'No path or decision on your map authorizes a move yet.');
  const heading = kind === 'NEXT_MOVE_PENDING'
    ? 'Your move is recorded. What comes next?'
    : 'No move is authorized yet.';
  return `
  <section class="mv-card mv-canonical" id="mv-current-move" aria-labelledby="mv-canonical-title">
    <div class="section-meta-label mb-0">YOUR MOVE</div>
    <h1 class="serif-heading" id="mv-canonical-title" style="font-size:26px;margin:0;line-height:1.25">${heading}</h1>
    <p class="mv-body">${esc(reason)}</p>
    <p class="mv-fine">Nothing is invented here: a move comes from your map's current work or from a decision in Talk.</p>
    <div class="mv-report-actions">
      <button type="button" class="btn-primary btn-sm" onclick="liveDecideNextMove(this)">Ask the engine for the next move</button>
      <button type="button" class="btn-secondary btn-sm" onclick="goDestination('talk')">Talk about what comes next →</button>
    </div>
    <p class="mv-fine">Asking weighs what you have recorded and decides. It can take a moment, and it may answer with a question instead of a move - that answer is not a failure.</p>
  </section>`;
}
/* The plan an EARLIER diagnosis wrote (day_by_day). It has no declared relationship to any canonical
   Move: there is no legitimate identity binding, and none is invented. So it keeps its OWN record -
   its steps stay workable here (done, skipped or blocked, in any order) - and finishing them is never
   credited to the move above. When no move is authorized, this list IS the work the person has. */
function mvLegacyPlanHistoryHtml(v) {
  const steps = (v.steps || []).filter(function (s) { return !s.report; });
  if (!steps.length) return '';
  const mvNow = (typeof liveCurrentMove === 'function') ? liveCurrentMove() : null;
  const mc = (typeof liveMoveContextSummary === 'function') ? liveMoveContextSummary(mvNow) : null;
  const relation = (mc && mc.moveId)
    ? 'Finishing a step here is recorded on THIS plan, not on the move above: the two records are separate and neither is inferred from the other.'
    : 'Finishing a step here is recorded on THIS plan. No move is authorized yet, so this is the work on record.';
  return [
    '<section class="mv-card mv-history" aria-label="Earlier recorded plan (history)">',
    '<div class="st-acc-list mv-acc-list">',
    mvAcc('plan-history', 'clock', 'Earlier recorded plan (history)', steps.length,
      '<p class="mv-fine">The plan an earlier diagnosis wrote, kept as a record. No day schedule applies to it - you decide when to work. ' + relation + '</p>'
      + mvActionList(v, { history: false }), false),
    '</div>',
    '</section>'
  ].join('');
}
/* ONE action of ONE canonical Move. DONE, SKIPPED, BLOCKED and TODO are four separate events; the
   accepted event is never resubmitted, and the screen always redraws from the read model. */
async function mvMoveAction(moveId, actionId, status, el) {
  const mvId = String(moveId || '');
  const actId = String(actionId || '');
  const st = String(status || '').toUpperCase();
  if (!mvId || !actId) return null;                    // never invent a move_id or an action_id
  if (['DONE', 'SKIPPED', 'BLOCKED', 'TODO'].indexOf(st) < 0) return null;
  if (st === 'SKIPPED' && !window.confirm('Mark this action as skipped? It is recorded as not done, and it will not count as completed.')) return null;
  if (st === 'BLOCKED' && !window.confirm('Mark this action as blocked? It is recorded as blocked: not done and not skipped, and it stays open work.')) return null;
  let r = null;
  let failed = null;
  try { r = await liveReportMoveAction(mvId, actId, st, '', el || null); }
  catch (e) { failed = e; }
  const fresh = !LIVE.lastRefreshFailed && !LIVE.experienceError;
  if (failed) {
    /* The server's own message is the toast; the read model is re-rendered below so the page cannot
       keep claiming a state the server refused. */
    showToast(liveReportErrorText(failed), '', '', 'error');
  } else {
    const stale = fresh ? '' : ' Your record is saved, but this view could not be refreshed.';
    if (st !== 'TODO') LIVE.movesSaveNotice = fresh ? null : { status: st, ts: Date.now() };
    if (r && r.move_executed === true) {
      showToast('Every required action is done. This move is executed - not a result yet.' + stale, '', '', fresh ? '' : 'error');
    } else if (st === 'DONE') {
      showToast('Action recorded as completed. Results are a separate report.' + stale, fresh ? 'See your map →' : '', fresh ? 'maps' : '', fresh ? '' : 'error');
    } else if (st === 'SKIPPED') {
      showToast('Action recorded as skipped. Skipped is not done, and results are a separate report.' + stale, '', '', fresh ? '' : 'error');
    } else if (st === 'BLOCKED') {
      showToast('Action recorded as blocked. It stays open work, and results are a separate report.' + stale, '', '', fresh ? '' : 'error');
    } else {
      showToast('Action reopened. The move is back in progress.' + stale, '', '', fresh ? '' : 'error');
    }
  }
  const onMoves = STORE.currentScreen === '04' || STORE.currentScreen === 'moves';
  if (onMoves && typeof renderScreenKeepingUi === 'function') renderScreenKeepingUi('04');
  else renderScreen('04');
  /* The move just became EXECUTED server-side: ask for the result only when the read model says the
     prompt is due (a stale read yields no prompt, never a guessed one). */
  if (!failed && r && r.move_executed === true) {
    const ctx = (typeof liveMovesReportContext === 'function') ? liveMovesReportContext() : null;
    if (ctx && typeof openMovesOutcomeReport === 'function') openMovesOutcomeReport();
  }
  return failed ? null : r;
}
/* "I'll report later" is scoped to this exact move state: another action, another move or a recorded
   result has a different key, so the prompt returns by itself instead of being silenced for good. */
function mvDismissMoveOutcome(key) {
  if (key) STORE.movesReportDismissed = String(key);
  renderScreen('04');
}
function mvClearMoveSelection() {
  STORE.movesSelectedMoveId = '';
  renderScreen('04');
}


/* Phase 2: explicit execution controls. DONE, SKIPPED and BLOCKED are three separate execution
   events; the UI never derives one from another, and an outcome report never changes execution
   (NC-R6). Every event carries a stable operation id held on a LIVE field, so a retry of the SAME
   step and status replays the accepted event instead of appending a second one. */
function liveStepLookup(num) {
  const rs = useRoadmapStore.getState();
  /* The button passes the expanded step's own number; the old implicit STORE.viewStep || currentStep
     chain remains only as a fallback for no-arg callers. */
  const step = rs.steps[(num || STORE.viewStep || rs.currentStep) - 1] || null;
  STORE.viewStep = 0;
  return step;
}
async function liveReportExecution(status, step, btn) {
  LIVE.pendingActionOps = LIVE.pendingActionOps || {};
  const key = String(LIVE.sid || '') + ':' + step.idx + ':' + status;
  const opId = LIVE.pendingActionOps[key] || (LIVE.pendingActionOps[key] = newOperationId('ax'));
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }
  try {
    const r = await liveReportAction(step.idx, { status: status, operation_id: opId });
    delete LIVE.pendingActionOps[key];
    /* Phase 6.2: unchanged = this step already carries that status and nothing was written. A calm neutral
       acknowledgement only: no "recorded as" success line and no completion prompt. */
    if (r && r.unchanged === true) {
      showToast('Nothing changed - this step was already recorded.', '', '', 'neutral');
      return 'unchanged';
    }
    /* replayed:true is the server saying this exact event was already accepted. That is a success,
       not a second event. The accepted event is reported to the caller as saved even when the READ
       that follows it failed; the caller must not resubmit. */
    liveExecutionSaved(status, !!(r && r.replayed));
    return true;
  } catch (e) {
    if (btn) { btn.disabled = false; btn.style.opacity = ''; }
    /* Phase 6.2: a historical action changed nothing and is never retried. Its pending operation id is dropped
       (the same index can name another action after a plan change) and the screen redraws from the re-read plan. */
    if (e && e.code === 'HISTORICAL_ACTION_READ_ONLY') {
      delete LIVE.pendingActionOps[key];
      showToast(liveReportErrorText(e), '', '', 'error');
      if (STORE.currentScreen) renderScreenKeepingUi(STORE.currentScreen);
      return null;
    }
    showToast('Could not save that: ' + liveReportErrorText(e), '', '', 'error');
    return null;
  }
}
/* The execution event is accepted by the server. A failed follow-up READ is reported as what it is -
   a view that is behind - and the only control offered is the read-only retry: the accepted event is
   never resubmitted (NC-02). */
function liveExecutionSaved(status, replayed) {
  const word = status === 'DONE' ? 'completed' : (status === 'SKIPPED' ? 'skipped' : 'blocked');
  const fresh = !LIVE.lastRefreshFailed && !LIVE.experienceError;
  if (!fresh) {
    LIVE.movesSaveNotice = { status: status, ts: Date.now() };
    showToast('Step recorded as ' + word + '. Your record is saved, but this view could not be refreshed.', '', '', 'error');
    return false;
  }
  LIVE.movesSaveNotice = null;
  if (status === 'DONE') {
    showToast(replayed
      ? 'This action was already recorded as completed. Results are still a separate report.'
      : 'Action recorded as completed. Results are a separate report.', 'See your map →', 'maps');
  } else if (status === 'SKIPPED') {
    showToast('Action recorded as skipped. Skipped is not done, and results are a separate report.');
  } else {
    showToast('Action recorded as blocked. It stays open work, and results are a separate report.');
  }
  return true;
}
async function liveSetStepStatus(status, num, el) {
  const step = liveStepLookup(num);
  if (!step || step.report) { renderScreen('05'); return null; }
  if (step.local) {
    // P0-04: a step with NO server action slot is never marked done locally. Its result belongs to
    // the canonical check-in boundary, so the browser cannot claim an accepted execution.
    showToast('This step has no action slot on the server. Report the result in your check-in.',
      'Open check-in →', '05');
    renderScreen('05');
    return null;
  }
  return await liveReportExecution(status, step, el || document.getElementById('advance-btn'));
}
async function liveAdvanceStep(num, el) {
  const r = await liveSetStepStatus('DONE', num, el);
  if (!r) return;
  /* NC-04: when the whole work context is accepted as complete, offer the contextual outcome
     report instead of routing through the legacy check-in screen. Deferring stays possible. A read
     that is behind never opens it: the execution is already saved, so the retry comes first. */
  const rctx = (typeof liveMovesReportContext === 'function') ? liveMovesReportContext() : null;
  const fresh = !LIVE.lastRefreshFailed && !LIVE.experienceError;
  renderScreen('04');
  /* Phase 6.2: an unchanged DONE recorded nothing new, so it opens no completion prompt. */
  if (rctx && fresh && r !== 'unchanged') openMovesOutcomeReport();
}
/* SKIPPED and BLOCKED are explicit operations with their own confirmation: never implied by a DONE
   action, a check-in or an outcome report, and never collapsed into "done" in any count or row. */
async function liveSkipStep(num, el) {
  if (!window.confirm('Mark this step as skipped? It is recorded as not done, and it will not count as completed.')) return;
  if (await liveSetStepStatus('SKIPPED', num, el)) renderScreen('04');
}
async function liveBlockStep(num, el) {
  if (!window.confirm('Mark this step as blocked? It is recorded as blocked: not done and not skipped, and it stays open work.')) return;
  if (await liveSetStepStatus('BLOCKED', num, el)) renderScreen('04');
}
/* Read-only retry of the workspace READ that follows a saved execution. It never resubmits. */
async function mvRetryRefresh() {
  if (typeof liveRetryRefresh !== 'function') return false;
  const ok = await liveRetryRefresh();
  if (ok) {
    LIVE.movesSaveNotice = null;
    if (typeof renderScreenKeepingUi === 'function' && STORE.currentScreen) renderScreenKeepingUi(STORE.currentScreen);
  }
  return ok;
}

/* ── 05 · Weekly check-in ──────────────────────────────────────────────────── */
function screen05Live() {
  const tl = getTimeline();
  const outcome = STORE.checkInOutcome === 'worked' || STORE.checkInOutcome === 'mixed' || STORE.checkInOutcome === 'none' ? STORE.checkInOutcome : '';
  if (!STORE.liveCheckIn) STORE.liveCheckIn = { contacted: '', replies: '', calls: '', paid: '', income: '' };
  const c = STORE.liveCheckIn;
  const card = (k, title, text) => `
        <div class="radio-card ${outcome === k ? 'selected' : ''}" onclick="setCheckInOutcomeLive('${k}')" role="radio" aria-checked="${outcome === k}" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();setCheckInOutcomeLive('${k}')}">
          <div class="radio-dot"></div>
          <div>
            <div style="font-family:var(--font-ui);font-weight:700;font-size:14.5px">${title}</div>
            <div style="font-size:13px;color:var(--ink-2)">${text}</div>
          </div>
        </div>`;
  const inp = (id, label, type, val, ph) => `
          <div>
            <label for="${id}" style="font-size:12px;color:var(--ink-3)">${label}</label>
            <input type="${type}" id="${id}" value="${esc(val)}" placeholder="${esc(ph || '0')}" ${type === 'number' ? 'min="0"' : ''} oninput="updateCheckInLive('${id.replace('checkin-', '')}', this.value)" style="width:100%;border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-top:4px;font-weight:700">
          </div>`;
  const content = `
  <div style="padding:40px 24px;display:flex;flex-direction:column;align-items:center">
    <div style="width:100%;max-width:720px;display:flex;flex-direction:column;gap:24px">
      <a onclick="renderScreen('04')" style="font-family:var(--font-ui);font-size:13px;color:var(--ink-2);text-decoration:none;cursor:pointer">← Back to Moves</a>
      <div>
        <div class="section-meta-label">Day ${tl.day} check-in · review</div>
        <h1 class="serif-heading" style="font-size:36px">What happened this week?</h1>
        <p style="font-size:14px;color:var(--ink-2);margin-top:6px">Pick what happened and add the numbers below. Whatever the result, your map will update.</p>
      </div>

      <div style="display:flex;flex-direction:column;gap:10px" role="radiogroup" aria-label="How did it go?">
        <span class="section-meta-label">How did it go? (pick one)</span>
        ${card('worked', 'It worked', 'Someone agreed to pay or signed a project')}
        ${card('mixed', 'Mixed', 'People replied and met with you, but no one signed yet')}
        ${card('none', 'No replies', 'Messages went out but no one replied. That tells us the message or the reach needs to change.')}
      </div>

      ${LIVE.tips.checkin ? '' : `
      <div class="tip-bubble pointer-left">
        <div style="font-family:var(--font-ui);font-size:12px;font-weight:600;color:var(--on-dark-2);margin-bottom:2px">Good to know · shown once</div>
        <div style="font-family:var(--font-ui);font-size:13.5px;font-weight:700;margin-bottom:4px">Every result teaches us something.</div>
        <div style="font-size:12.5px;color:var(--on-dark-3);line-height:1.5;margin-bottom:10px">There's no failing here. A step that gets no reaction is recorded as evidence, and it never marks a whole path as wrong on its own.</div>
        <button class="btn-secondary btn-sm" style="background:var(--surface);border:none;color:var(--ink)" onclick="dismissTip('checkin')">Got it</button>
      </div>`}

      <div class="card-clean">
        <div class="section-meta-label mb-8">This week's numbers</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(140px, 1fr));gap:12px">
          ${inp('checkin-contacted', 'People contacted', 'number', c.contacted)}
          ${outcome !== 'none' ? inp('checkin-replies', 'Replies', 'number', c.replies) + inp('checkin-calls', 'Calls held', 'number', c.calls) : ''}
          ${outcome === 'worked' ? inp('checkin-paid', 'Paid (in Rp)', 'text', c.paid, 'Rp0') : ''}
          ${inp('checkin-income', 'Monthly income now (Rp)', 'text', c.income, fmtM(liveEarned()) ? fmtM(liveEarned()).replace('Rp', 'Rp ') : 'Rp0')}
        </div>
      </div>

      <div id="checkin-err" role="alert" style="color:var(--stop-fg);font-size:13px;display:none"></div>
      <button class="btn-primary" id="checkin-submit" style="height:48px;font-size:15px;font-weight:600;${outcome ? '' : 'opacity:0.5;cursor:not-allowed'}" onclick="liveSubmitCheckIn()">
        Update my map →
      </button>
    </div>
  </div>`;
  return renderAppShell('activity', 'Weekly check-in', content);
}
function setCheckInOutcomeLive(k) { STORE.checkInOutcome = k; LIVE.pendingCheckinOp = ''; renderScreen('05'); }
function updateCheckInLive(key, val) { if (!STORE.liveCheckIn) STORE.liveCheckIn = {}; STORE.liveCheckIn[key] = val; LIVE.pendingCheckinOp = ''; }

async function liveSubmitCheckIn() {
  const outcome = STORE.checkInOutcome;
  const err = document.getElementById('checkin-err');
  if (!['worked', 'mixed', 'none'].includes(outcome)) {
    if (err) { err.style.display = 'block'; err.textContent = 'Pick what happened first.'; }
    return;
  }
  const btn = document.getElementById('checkin-submit');
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; btn.textContent = 'Updating your map…'; }
  const c = STORE.liveCheckIn || {};
  const rs = useRoadmapStore.getState();
  const before = livePathModels().map(p => ({ key: p.key, name: p.name, status: p.status, why: p.why }));
  /* D-02/N02/N10: a field the person did not fill in is null, never 0; an explicit 0 (for example
     "no replies") stays 0. paid only means something when the outcome is "worked". */
  const num = v => (v === '' || v == null) ? null : (Number.isNaN(Number(v)) ? null : Number(v));
  const paid = outcome === 'worked' ? num(c.paid) : null;
  const income = parseRpM(c.income);
  const rp = income != null ? income : null;   // null = no income was reported at this check-in (never the carried-over figure)
  const contacted = num(c.contacted);
  const replies = outcome === 'none' ? 0 : num(c.replies);
  const calls = outcome === 'none' ? 0 : num(c.calls);
  const titles = {
    worked: paid ? ('Paid result · ' + fmtM(paid)) : 'It worked',
    mixed: 'Interested, but no one paid yet',
    none: 'No replies this week'
  };
  const summary = (contacted != null ? contacted + ' contacted' : 'contacts not reported')
    + ' · ' + (replies != null ? replies + ' replies' : 'replies not reported')
    + ' · ' + (calls != null ? calls + ' calls' : 'calls not reported')
    + (paid ? ' · paid ' + fmtM(paid) : '');
  const rec = {
    cycle: rs.currentCycle, day: Math.min(rs.currentCycle * liveCycleLen(), liveHorizon()), outcome, contacted, replies, calls, paid, rp,
    path: liveActivePathKey(), title: titles[outcome], note: summary, ts: Date.now(), sid: LIVE.sid
  };
  try {
    const items = (LIVE.artifact.day_by_day || []);
    const opId = LIVE.pendingCheckinOp || (LIVE.pendingCheckinOp = newOperationId('ci'));
    /* P0-05: ONE canonical commit boundary. The check-in and the last plan step's report go in a
       SINGLE idempotent operation, so a failure can never half-apply (a report without its check-in,
       or a duplicated report on retry). A 409 on a reused key with a different payload is surfaced. */
    const body = {
      outcome, cycle: rec.cycle, day: rec.day, contacted, replies, calls, paid, rp,
      path: rec.path, title: rec.title, note: rec.note, operation_id: opId
    };
    if (items.length) {
      body.action_index = items.length - 1;
      body.action_status = 'DONE';
      body.action_outcome = outcome === 'none' ? 'not_moved' : 'moved';
    }
    const saved = await API.checkin(LIVE.sid, body);
    LIVE.pendingCheckinOp = '';
    const row = (saved && saved.checkin) || {};
    LIVE.checkins.push(Object.assign({}, rec, {
      checkinId: row.checkin_id, ts: (row.created_ts || Math.floor(Date.now() / 1000)) * 1000,
      contacted: liveCountField(row.contacted != null ? row.contacted : contacted),
      replies: liveCountField(row.replies != null ? row.replies : replies),
      calls: liveCountField(row.calls != null ? row.calls : calls),
      paid: row.paid != null ? row.paid : paid,
      rp: row.rp != null ? row.rp : rp
    }));
    saveLive();
    syncStoreFromLive();
    // P0-05: refresh the Experience projection after acceptance through the shared version-checked
    // boundary (render:false — this flow renders its own confirmation screen next).
    const ok = await liveRefreshAfterMutation({ render: false });
    const after = livePathModels().map(p => ({ key: p.key, name: p.name, status: p.status, why: p.why }));
    LIVE.lastDiff = { outcome, before, after, rec };
    STORE.liveCheckIn = null; STORE.checkInOutcome = '';
    /* NC-05: no separate "Map updated" product. Navigate to the ONE Maps destination and let the
       durable change_set explain what actually changed — or that nothing material did. */
    STORE.pendingChangeSummary = { source: 'checkin', outcome: outcome, refreshFailed: !ok };
    renderScreen('maps');
  } catch (e) {
    if (btn) { btn.disabled = false; btn.style.opacity = ''; btn.textContent = 'Update my map →'; }
    if (err) { err.style.display = 'block'; err.textContent = 'Could not save your check-in: ' + e.message; }
  }
}

/* ── 06a / 12 / 06b · Map updated or adjusted ─────────────────────────────── */
function pillFor(status) {
  const cls = { OPEN: 'open', TEST_FIRST: 'test_first', NOT_YET: 'not_yet', STOP: 'stop' }[status] || 'not_yet';
  return `<span class="status-pill ${cls}">${STATUS_WORD[status] || status}</span>`;
}
function screen06Live(kind) {
  const diff = LIVE.lastDiff;
  if (!diff) return screen04Live();
  const rs = useRoadmapStore.getState();
  const tl = getTimeline();
  const rec = diff.rec;
  const changed = diff.after.filter(a => { const b = diff.before.find(x => x.key === a.key); return b && b.status !== a.status; });
  const paths = livePathModels();
  const activeKey = rs.activePathId;
  const d = LIVE.artifact;
  const g = liveGoal();
  const dn = cleanDoNot(d);
  const kicker = { worked: 'Map updated from your', mixed: 'Map adjusted from your', none: 'Map adjusted from your' }[kind];
  const head = {
    worked: changed.length ? 'A path just changed.' : 'Your evidence just got stronger.',
    mixed: 'People are interested. Nobody has said yes yet.',
    none: "No replies this week. That's evidence too."
  }[kind];
  const sub = {
    worked: changed.length ? 'Your goal stays the same. You just have different options now.' : 'Your goal stays the same. This result is now part of your map, and it counts.',
    mixed: 'Replies and calls tell us the need may be real. The first commitment probably feels too big, so the next move should shrink it, not discount it.',
    none: "Your goal hasn't changed, and neither has what we know about what you offer. What changes is how we test it."
  }[kind];
  const learned = `
        <div class="card-clean">
          <div class="section-meta-label">What we learned</div>
          <div style="display:flex;gap:24px;margin:12px 0 16px;flex-wrap:wrap">
            <div><div style="font-size:24px;font-weight:700">${rec.replies}${rec.contacted ? ` / ${rec.contacted}` : ''}</div><div style="font-size:12px;color:var(--ink-3)">replied</div></div>
            <div><div style="font-size:24px;font-weight:700">${rec.calls}</div><div style="font-size:12px;color:var(--ink-3)">calls held</div></div>
            <div><div style="font-size:24px;font-weight:700;${rec.paid ? '' : 'color:var(--ink-muted)'}">${rec.paid ? esc(fmtM(rec.paid)) : '0'}</div><div style="font-size:12px;color:var(--ink-3)">paid</div></div>
          </div>
          <p style="font-size:14px;color:var(--ink);line-height:1.55">${{
            worked: 'A result that moved something is the strongest kind of evidence. It validates the path you worked on, and it can reopen one you had stopped.',
            mixed: 'Interest without a yes is a real signal. It is worth a change of approach, not a change of goal. The engine does not lower a path because one step fell short.',
            none: 'A step that gets no reaction says something about the message or the reach, not about you. The engine does not mark a whole path as wrong from one quiet week.'
          }[kind]}</p>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:14px">
            <span class="evidence-chip">${esc(rec.note)}</span>
            ${rec.rp != null ? `<span class="evidence-chip">Income ${esc(fmtM(rec.rp))} a month</span>` : ''}
          </div>
        </div>`;
  const changedRows = `
        <div class="card-clean" style="${kind === 'worked' ? 'flex:1;min-width:320px;padding:0;overflow:hidden' : 'width:400px;flex-shrink:0'}">
          ${kind === 'worked' ? `
          <div style="display:grid;grid-template-columns:2.5fr 1fr 24px 1.5fr;background:var(--surface-2);padding:10px 16px;font-family:var(--font-ui);font-size:11px;font-weight:700;color:var(--ink-3)">
            <span>Path</span><span>Before</span><span></span><span>Now</span>
          </div>
          ${diff.after.map((a, i) => {
            const b = diff.before.find(x => x.key === a.key) || a;
            const ch = b.status !== a.status;
            const isActive = a.key === activeKey;
            return `<div style="display:grid;grid-template-columns:2.5fr 1fr 24px 1.5fr;padding:${ch ? 14 : 12}px 16px;${ch ? 'background:var(--open-soft);border-top:1px solid var(--open-border);border-bottom:1px solid var(--open-border);' : (i < diff.after.length - 1 ? 'border-bottom:1px solid var(--border);' : '')}align-items:center">
              <div>${ch ? `<strong>${esc(a.name)}</strong>` : `<span>${esc(a.name)}</span>`}
                <div style="font-size:12px;color:${ch ? 'var(--open-fg)' : 'var(--ink-3)'}">${ch ? 'Changed after your report' : (isActive ? 'Your current path' : 'Unchanged')}</div></div>
              ${pillFor(b.status)}<span style="${ch ? 'color:var(--open-fg);' : ''}font-weight:700">→</span>${pillFor(a.status)}
            </div>`;
          }).join('')}` : `
          <div class="section-meta-label">What changed on your map</div>
          <div style="display:flex;flex-direction:column;gap:14px;margin-top:14px">
            ${diff.after.map(a => {
              const b = diff.before.find(x => x.key === a.key) || a;
              const ch = b.status !== a.status;
              const stop = a.status === 'STOP';
              return `<div style="padding:10px 12px;${stop ? 'background:var(--stop-soft);border:1px solid var(--stop-border);' : (a.key === activeKey ? 'background:var(--open-soft);' : 'background:var(--surface-2);')}border-radius:8px">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><span style="${stop ? 'color:var(--stop-fg);font-weight:600' : (a.key === activeKey ? 'font-weight:700' : '')}">${esc(a.name)}</span>${pillFor(a.status)}</div>
                <div style="font-size:12px;margin-top:4px;color:${stop ? 'var(--stop-fg)' : (a.key === activeKey ? 'var(--open-fg)' : 'var(--ink-3)')}">${esc(ch ? `Changed from ${STATUS_WORD[b.status]}` : (a.key === activeKey ? 'Still your current path. Unchanged.' : 'Unchanged'))}</div>
              </div>`;
            }).join('')}
          </div>`}
        </div>`;
  const why = kind === 'worked' ? `
      <div class="card-clean" style="width:380px;flex-shrink:0">
        <div class="section-meta-label">What we recorded</div>
        <div style="display:flex;flex-direction:column;gap:12px;margin-top:12px;font-size:13.5px;line-height:1.55">
          <div style="display:flex;align-items:flex-start;gap:8px"><span style="color:var(--open-fg);font-weight:700">✓</span><div><strong>Your report:</strong> ${esc(rec.note)}</div></div>
          <div style="display:flex;align-items:flex-start;gap:8px"><span style="color:var(--open-fg);font-weight:700">✓</span><div><strong>Sent to the engine as:</strong> a result that moved something</div></div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin:14px 0">
          <span class="evidence-chip">${esc(rec.note)}</span>${rec.rp != null ? `<span class="evidence-chip">Income ${esc(fmtM(rec.rp))} a month</span>` : ''}
        </div>
        <div style="font-size:12.5px;color:var(--ink-2);background:var(--surface-2);border-radius:8px;padding:10px 12px;line-height:1.5;margin-top:14px">
          A moved result validates the path you worked on and reopens one you stopped. It does not change the other paths by itself. Paths open or close when your evidence changes, and the next cycle re-checks all of them.
        </div>
      </div>` : '';
  const next = {
    worked: ['Start the next week', 'Re-check your map with what you just learned. We look at what changed and plan your next step.', 'Start the next week →'],
    mixed: ['Start the next week', 'Re-check your map with what you just learned, and get a smaller first step.', 'Start the next week →'],
    none: ['Try again with a new angle', 'A follow-up check-in lets the engine look again and pick a different move. Same goal, same paths.', 'Start the next week →']
  }[kind];
  const planCard = `
        <div class="${kind === 'mixed' ? 'card-clean' : 'card-dark'}">
          <div class="section-meta-label" ${kind === 'mixed' ? '' : 'style="color:var(--border-strong)"'}>Next week</div>
          <h3 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin:6px 0 4px">${esc(next[0])}</h3>
          <p style="font-size:13.5px;${kind === 'mixed' ? 'color:var(--ink-2)' : 'color:var(--border)'};line-height:1.5;margin-bottom:${kind === 'worked' ? 0 : 18}px">${esc(next[1])}</p>
          ${d.pivot_rule ? `<div style="font-size:12.5px;${kind === 'mixed' ? 'color:var(--ink-2)' : 'color:var(--border)'};line-height:1.5;border-top:1px solid ${kind === 'mixed' ? 'var(--border)' : 'var(--ink-2b)'};padding-top:12px;margin-top:8px"><strong>Your pivot rule:</strong> ${esc(brief(userFacing(d.pivot_rule), 260))}</div>` : ''}
          ${kind === 'mixed' && dn.text ? `<div class="card-danger" style="margin-top:16px;padding:14px"><div class="section-meta-label" style="color:var(--stop-fg)">What not to do</div><div style="font-size:13px;color:var(--ink);line-height:1.5;margin-top:4px">${esc(brief(dn.text, 240))}</div></div>` : ''}
          <div style="display:flex;gap:12px;margin-top:22px;flex-wrap:wrap">
            <button class="btn-primary" ${kind === 'mixed' ? '' : 'style="background:var(--surface);color:var(--ink)"'} onclick="startFollowUpFlow()">${esc(next[2])}</button>
            <button class="btn-secondary" ${kind === 'mixed' ? '' : 'style="border-color:var(--ink-2b);color:var(--on-ink)"'} onclick="renderScreen('07')">See your map</button>
          </div>
        </div>`;
  const progress = g.target && rec.rp != null ? `
      <div style="text-align:right">
        <div style="display:flex;align-items:center;gap:10px;justify-content:flex-end">
          <span style="font-family:var(--font-ui);font-size:13px;font-weight:700">${esc(fmtM(rec.rp))} of ${esc(fmtM(g.target))}</span>
          <div style="width:120px;height:8px;background:var(--border);border-radius:999px;overflow:hidden"><div style="width:${Math.min(100, Math.round(rec.rp / g.target * 100))}%;height:100%;background:var(--open-line);border-radius:999px"></div></div>
        </div>
        <div style="font-size:12px;color:var(--ink-3);margin-top:4px">Day ${tl.day} of ${tl.horizon}</div>
      </div>` : '';
  const nextSection = `
    <div style="margin-top:10px">
      <div class="section-meta-label mb-8">What do you want to do next?</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div class="card-dark" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span class="status-pill open" style="background:var(--open-fg);color:var(--on-ink);border:none">RECOMMENDED</span></div>
            <h3 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin-bottom:8px">${esc(next[0])}</h3>
            <p style="font-size:13.5px;color:var(--border-strong);line-height:1.55">${esc(next[1])}${d.pivot_rule ? ` Your pivot rule: ${esc(brief(userFacing(d.pivot_rule), 180))}` : ''}</p>
          </div>
          <div style="margin-top:20px"><button class="btn-primary" style="background:var(--surface);color:var(--ink);width:100%" onclick="startFollowUpFlow()">${esc(next[2])}</button></div>
        </div>
        <div class="card-clean" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span class="section-meta-label">Keep going</span></div>
            <h3 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin-bottom:8px">Stay on this plan</h3>
            <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55">Finish what is left of this week first, then re-check. Slower, but builds more evidence before you change anything.</p>
          </div>
          <div style="margin-top:20px"><button class="btn-secondary" style="width:100%" onclick="renderScreen('04')">Stay on this plan</button></div>
        </div>
      </div>
      <div style="font-size:12px;color:var(--ink-3);margin-top:10px;text-align:center">Either way, your history is kept.</div>
    </div>`;
  const content = kind === 'worked' ? `
  <div style="padding:40px 56px;display:flex;flex-direction:column;gap:28px">
    <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:16px">
      <div>
        <div class="section-meta-label" style="color:var(--open-fg)">${kicker} Day ${rec.day} check-in</div>
        <h1 class="serif-heading" style="font-size:36px">${esc(head)}</h1>
        <p style="font-size:14.5px;color:var(--ink-2);margin-top:6px">${esc(sub)}</p>
      </div>${progress}
    </div>
    <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">${changedRows}${why}</div>
    ${nextSection}
  </div>` : `
  <div style="padding:40px 56px;display:flex;flex-direction:column;gap:28px">
    <div>
      <div class="section-meta-label">${kicker} Day ${rec.day} check-in${kind === 'mixed' ? ' · mixed result' : ''}</div>
      <h1 class="serif-heading" style="font-size:36px">${esc(head)}</h1>
      <p style="font-size:14.5px;color:var(--ink-2);margin-top:6px">${esc(sub)}</p>
    </div>
    <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">
      <div style="flex:1;min-width:320px;display:flex;flex-direction:column;gap:20px">${learned}${planCard}</div>
      ${changedRows}
    </div>
  </div>`;
  return renderAppShell('map', kind === 'worked' ? 'Map updated' : 'Map adjusted', content);
}

/* ── 14 · Welcome back ─────────────────────────────────────────────────────── */
function screen14Live() {
  const rs = useRoadmapStore.getState();
  const tl = getTimeline();
  const last = LIVE.checkins[LIVE.checkins.length - 1];
  const reports = (LIVE.artifact.day_by_day || []).map(x => x.reported_at).filter(Boolean);
  const lastTouch = Math.max(LIVE.startTs || 0, last ? last.ts : 0, ...reports.map(t => t * 1000));
  const daysSince = Math.max(1, Math.floor((Date.now() - lastTouch) / 86400000));
  const overdue = tl.day > tl.nextCheckIn;
  const cur = rs.steps[rs.currentStep - 1];
  const opt = STORE.welcomeBackOption || 'busy';
  const timeline = STORE.welcomeBackTimeline || tl.horizon;
  const paths = livePathModels();
  const active = paths.find(p => p.key === rs.activePathId) || paths[0];
  const stepBox = cur && !cur.report ? cur.box() : '';
  const content = `
  <div style="padding:40px 56px;display:flex;flex-direction:column;gap:28px">
    <div>
      <div class="section-meta-label">${daysSince} day${daysSince === 1 ? '' : 's'} since your last visit${overdue ? ` · Day ${tl.nextCheckIn} check-in missed` : ''}</div>
      <h1 class="serif-heading" style="font-size:36px">Welcome back. Let's start from where you are now.</h1>
    </div>
    <div style="display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap">
      <div style="flex:1;min-width:320px;display:flex;flex-direction:column;gap:20px">
        <div class="card-clean">
          <div class="section-meta-label mb-8">Did anything happen since we last spoke?</div>
          <div style="font-size:13.5px;color:var(--ink-2);margin-bottom:14px">${cur ? `Your next step is “${esc(cur.label)}.”` : ''}</div>
          <div style="display:flex;flex-direction:column;gap:10px" role="radiogroup">
            <div class="radio-card ${opt === 'results' ? 'selected' : ''}" onclick="setWelcomeBackOption('results')" role="radio" aria-checked="${opt === 'results'}" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();setWelcomeBackOption('results')}">
              <div class="radio-dot"></div>
              <div>
                <div style="font-family:var(--font-ui);font-weight:700;font-size:14px">Yes, I have results to report</div>
                ${opt === 'results' ? `<div style="font-size:13px;color:var(--open-fg);margin-top:4px">Great. Log them now and your map updates straight away.<div style="margin-top:8px"><button class="btn-primary btn-sm" onclick="renderScreen('05')">Report results →</button></div></div>` : ''}
              </div>
            </div>
            <div class="radio-card ${opt === 'steps' ? 'selected' : ''}" onclick="setWelcomeBackOption('steps')" role="radio" aria-checked="${opt === 'steps'}" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();setWelcomeBackOption('steps')}">
              <div class="radio-dot"></div>
              <div>
                <div style="font-family:var(--font-ui);font-weight:700;font-size:14px">I did some steps, but no results yet</div>
                ${opt === 'steps' ? `<div style="font-size:13px;color:var(--ink-2);margin-top:4px">That still counts. Mark what you did in Activity and we'll pick up from the next step.<div style="margin-top:8px"><button class="btn-secondary btn-sm" onclick="renderScreen('04')">Go to Today →</button></div></div>` : ''}
              </div>
            </div>
            <div class="radio-card ${opt === 'busy' ? 'selected' : ''}" onclick="setWelcomeBackOption('busy')" role="radio" aria-checked="${opt === 'busy'}" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();setWelcomeBackOption('busy')}">
              <div class="radio-dot"></div>
              <div>
                <div style="font-family:var(--font-ui);font-weight:700;font-size:14px">Nothing yet, life got busy</div>
                ${opt === 'busy' ? `<div style="font-size:13px;color:var(--ink-2);margin-top:4px">That's okay, and it happens to most people. Nothing is lost: your path is still open. Just take the one step below.</div>` : ''}
              </div>
            </div>
          </div>
        </div>
        ${opt !== 'results' && cur && !cur.report ? `
        <div class="card-clean" style="border:2px solid var(--ink);padding:24px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span class="section-meta-label" style="color:var(--ink)">This week, smaller · one step</span>
            <span class="status-pill open">ACTIVE</span>
          </div>
          <h3 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin-bottom:6px">${esc(cur.title)}</h3>
          <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55;margin-bottom:14px">No need to do everything. Just this one step to get going again.</p>
          <div style="margin-bottom:14px">${stepBox}</div>
          <div style="display:flex;gap:10px"><button class="btn-primary btn-sm" onclick="liveAdvanceStep()">Mark as done</button><button class="btn-secondary btn-sm" onclick="renderScreen('04')">Open Today</button></div>
        </div>` : ''}
      </div>
      <div style="width:380px;display:flex;flex-direction:column;gap:18px;flex-shrink:0">
        <div class="card-clean">
          <div class="section-meta-label">Your timeline</div>
          <p style="font-size:13.5px;color:var(--ink-2);margin:6px 0 12px">Your goal stays the same. Do you want to keep the deadline, or give yourself more room?</p>
          <div style="display:flex;gap:10px">
            <button class="card-clean" style="flex:1;padding:10px;text-align:center;border:1.5px solid ${timeline === tl.horizon ? 'var(--ink)' : 'var(--border)'}" onclick="setWelcomeBackTimeline(${tl.horizon})">
              <div style="font-weight:700;font-size:13px">Keep Day ${tl.horizon}</div><div style="font-size:11px;color:var(--ink-3)">${tl.daysLeft} days left</div>
            </button>
            <button class="card-clean" style="flex:1;padding:10px;text-align:center;border:1.5px solid ${timeline !== tl.horizon ? 'var(--ink)' : 'var(--border)'}" onclick="setWelcomeBackTimeline(${tl.horizon + 30})">
              <div style="font-weight:700;font-size:13px">Move to Day ${tl.horizon + 30}</div><div style="font-size:11px;color:var(--ink-3)">${tl.daysLeft + 30} days left</div>
            </button>
          </div>
          <div style="font-size:11.5px;color:var(--ink-3);margin-top:8px">Moving the deadline changes the weekly pace, not the paths.</div>
        </div>
        <div class="card-clean">
          <div class="section-meta-label">Stay on track</div>
          <div style="font-size:13px;color:var(--ink-2);margin-top:8px;line-height:1.5">Your next check-in is on Day ${tl.nextCheckIn}. Open Novaliners once a week and report what happened.</div>
        </div>
        <div class="card-soft-green">
          <div class="section-meta-label" style="color:var(--open-fg)">What didn't change</div>
          <div style="font-size:13px;color:var(--ink);line-height:1.5;margin-top:6px">${active ? esc(active.name) + ' is still ' + STATUS_WORD[active.status].toLowerCase() + ', and your' : 'Your'} answers are saved. Nothing you did so far is lost.</div>
        </div>
      </div>
    </div>
  </div>`;
  return renderAppShell('activity', 'Welcome back', content);
}
function setWelcomeBackOption(v) { STORE.welcomeBackOption = v; renderScreen('14'); }
function setWelcomeBackTimeline(days) {
  STORE.welcomeBackTimeline = days;
  if (!IS_DEMO) { LIVE.horizonOverride = days; saveLive(); }
  renderScreen('14');
}

/* ── 16 · Day review ───────────────────────────────────────────────────────── */
function screen16Live() {
  const rs = useRoadmapStore.getState();
  const tl = getTimeline();
  const g = liveGoal();
  const goal = rs.goalRp || g.target || 0;
  const h = LIVE.checkins;
  const miss = rs.ending !== 'success';
  const paid = h.filter(r => r.paid > 0);
  const paidTotal = Math.round(paid.reduce((s, r) => s + r.paid, 0) * 10) / 10;
  const peak = h.length ? Math.max(...h.map(r => r.rp)) : rs.earned;
  const quiet = h.filter(r => r.outcome === 'none' || r.outcome === 'missed').length;
  const paths = livePathModels();
  const openNow = paths.filter(p => p.status === 'OPEN');
  const held = paths.filter(p => p.status === 'STOP' || p.status === 'NOT_YET');
  const other = openNow.find(p => p.key !== rs.activePathId);
  const choice = STORE.endingChoice;
  const short = goal ? Math.max(goal - rs.earned, 0) : 0;
  const base = liveGoal().current || 0;
  const options = miss ? [
    { id: 'extend', title: 'Give it 30 more days', desc: `Keep the ${esc(fmtM(goal))} goal and move the deadline to Day ${tl.horizon + 30}. Same paths, same rhythm.`, tag: 'Keeps the goal' },
    { id: 'lower', title: `Set the goal to ${esc(fmtM(Math.round((rs.earned + goal) / 2)))} for now`, desc: `A goal between where you are and where you aimed. ${esc(fmtM(goal))} stays as the next step after it.`, tag: 'More realistic' },
    { id: 'switch', title: other ? `Lead with ${esc(other.name.toLowerCase())}` : 'Try a different path', desc: other ? 'Another path is open. Put most of your weekly time here for the next cycle.' : 'Pick a different path from your map and put most of your weekly time here.', tag: 'Changes the path' }
  ] : [
    { id: 'hold', title: `Hold ${esc(fmtM(goal))} for 30 days`, desc: 'Prove the income is steady before you aim higher. Fewer new tests, more follow-through.', tag: 'RECOMMENDED' },
    { id: 'raise', title: `Aim for ${esc(fmtM(goal * 2))} next`, desc: 'A new goal. The map redraws from what already works.', tag: 'New goal' },
    ...(paid.length >= 3 ? [{ id: 'register', title: 'Register your company', desc: `You have ${paid.length} paying results, so the rule that held this back is met.`, tag: 'UNLOCKED' }] : [])
  ];
  const worked = [
    paid.length ? `${paid.length} check-in${paid.length === 1 ? '' : 's'} brought a payment, ${esc(fmtM(paidTotal))} in total.` : null,
    h.some(r => r.outcome === 'mixed') ? 'People replied and met with you, so the interest is real.' : null,
    rs.earned > base ? `Monthly income moved from ${esc(fmtM(base))} to ${esc(fmtM(rs.earned))}.` : null,
    `${(LIVE.evidence || []).filter(e => !e.is_gap).length || 'Real'} facts back this map, not templates.`
  ].filter(Boolean);
  const heldBack = [
    quiet ? `${quiet} check-in${quiet === 1 ? '' : 's'} with no result or a missed one.` : null,
    h.length >= 3 && h.slice(-3).every(r => r.rp === h[h.length - 1].rp) ? `Income stayed at ${esc(fmtM(rs.earned))} for the last 3 check-ins.` : null,
    held.length ? `${held.length} path${held.length === 1 ? ' is' : 's are'} still held back until their checks pass.` : null,
    LIVE.artifact.pivot_rule ? `Your pivot rule: ${esc(brief(userFacing(LIVE.artifact.pivot_rule), 150))}` : null
  ].filter(Boolean);
  const stat = (label, val, sub, soft) => `<div class="card-clean" style="padding:16px 18px;"><div class="section-meta-label" ${soft ? 'style="color:var(--open-fg)"' : ''}>${label}</div><div style="font-size:22px;font-weight:700;margin-top:4px;${soft ? 'color:var(--open-fg)' : ''}">${val}</div><div style="font-size:11.5px;color:var(--ink-3);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${sub}</div></div>`;
  return renderAppShell('journey', `Day ${tl.horizon} Review`, `
  <div style="padding:32px 48px 40px;display:flex;flex-direction:column;gap:20px;max-width:1120px;width:100%;margin:0 auto">
    <div>
      <div class="section-meta-label" style="color:${miss ? 'var(--notyet-fg)' : 'var(--open-fg)'}">Day ${tl.horizon} review · ${h.length} check-in${h.length === 1 ? '' : 's'}</div>
      <h1 class="serif-heading" style="font-size:34px;margin-top:4px">${miss ? `You reached ${esc(fmtM(rs.earned))} a month. Not ${esc(fmtM(goal))} yet.` : `You reached ${esc(fmtM(rs.earned))} a month. Goal done.`}</h1>
      <p style="font-size:15px;color:var(--ink-2);margin-top:8px;max-width:760px;line-height:1.55">${miss
        ? `That's ${esc(fmtM(short))} a month short. ${rs.earned > base ? `It's also ${esc(fmtM(rs.earned - base))} more than where you started. ` : ''}Missing the date doesn't undo what you learned. Here's what happened, and honest ways forward.`
        : `From ${esc(fmtM(base))} to ${esc(fmtM(rs.earned))} a month. Here's what got you there, and what to do next.`}</p>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px">
      ${stat('Monthly income', esc(fmtM(rs.earned)), `Goal ${esc(fmtM(goal))} · peak ${esc(fmtM(peak))}`)}
      ${stat('Check-ins with a payment', String(paid.length), `${esc(fmtM(paidTotal))} in new payments`)}
      ${stat('Paths open', String(openNow.length), esc(openNow.map(p => p.name).join(' + ') || 'None'))}
      ${stat('Paths held back', String(held.length), 'Kept on hold until the evidence is there', true)}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="card-clean" style="padding:20px 22px"><div class="section-meta-label" style="margin-bottom:10px">What worked</div>
        <ul style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:6px;font-size:13.5px;color:var(--ink-2);line-height:1.5">${worked.map(w => `<li>${w}</li>`).join('')}</ul></div>
      <div class="card-clean" style="padding:20px 22px"><div class="section-meta-label" style="margin-bottom:10px">${miss ? 'What held it back' : 'What to watch'}</div>
        <ul style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:6px;font-size:13.5px;color:var(--ink-2);line-height:1.5">${(heldBack.length ? heldBack : ['Nothing stands out. Keep the rhythm going.']).map(w => `<li>${w}</li>`).join('')}</ul></div>
    </div>
    <div>
      <div class="section-meta-label" style="margin-bottom:10px">${miss ? 'What do you want to do now?' : 'What next?'}</div>
      <div style="display:grid;grid-template-columns:repeat(${options.length},1fr);gap:14px" role="radiogroup">
        ${options.map(o => `
        <button class="card-clean ending-option ${choice === o.id ? 'selected' : ''}" onclick="chooseEnding('${o.id}')" role="radio" aria-checked="${choice === o.id}">
          <span class="section-meta-label" style="margin:0;color:${choice === o.id ? 'var(--open-on-ink)' : 'var(--ink-3)'}">${o.tag}</span>
          <span style="font-family:var(--font-ui);font-size:15px;font-weight:700;line-height:1.3">${o.title}</span>
          <span style="font-size:13px;line-height:1.5;opacity:0.85">${o.desc}</span>
        </button>`).join('')}
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:16px;flex-wrap:wrap">
        <span style="font-size:12.5px;color:var(--ink-3)">${choice ? 'Your choice is saved. The map will redraw from here.' : 'Pick one. You can change it later.'}</span>
        <div style="display:flex;gap:10px">
          <button class="btn-secondary" onclick="renderScreen('08')">See the full journey</button>
          <button class="btn-primary" ${choice ? '' : 'disabled style="opacity:0.5;cursor:not-allowed"'} onclick="confirmEnding()">Start the next 30 days →</button>
        </div>
      </div>
    </div>
  </div>`);
}

/* Applies the Day-review choice for real: deadline, goal or lead path change, then a follow-up cycle. */
function confirmEnding() {
  if (!STORE.endingChoice) return;
  if (IS_DEMO) { showToast('Plan saved. The next 30 days start from what you already built.', 'View journey →', '08'); return; }
  const id = STORE.endingChoice;
  const rs = useRoadmapStore.getState();
  const goal = rs.goalRp || liveGoal().target || 0;
  if (id === 'extend' || id === 'hold') LIVE.horizonOverride = liveHorizon() + 30;
  if (id === 'lower') LIVE.goalOverride = Math.round((rs.earned + goal) / 2);
  if (id === 'raise') LIVE.goalOverride = goal * 2;
  if (id === 'switch') { const o = livePathModels().find(p => p.status === 'OPEN' && p.key !== rs.activePathId); if (o) LIVE.activePath = o.key; }
  saveLive();
  showToast('Plan saved. The next 30 days start from what you already built.', '', '');
  liveStartFollowUp();
  renderScreen('02');
}


/* ==========================================================================
   V11 STATE and MOVES (record D3, D8). P4 bridge: the v9 Diagnosis and Activity bodies inside the v11 shell.
   Replaced by the v11 renderers in P5a and P5c.
   ========================================================================== */
/* ── State (record D3): where you are, what matters, what to do, why. Fed by the snapshot only. ── */
/* ── ported from Revenue Navigation v11.dc.html lines 11064-11292 ── */
const stateN = (n, one, many) => `${n} ${n === 1 ? one : many}`;
function stateSentences(text) {
  const t = String(text || '').trim();
  if (!t) return [];
  const out = [];
  t.split(/(?<=[.!?])\s+(?=[A-Z“"‘'(\d])/).forEach(p => {
    if (out.length && /\b(e\.g|i\.e|vs|etc)\.$/i.test(out[out.length - 1])) out[out.length - 1] += ' ' + p;
    else out.push(p);
  });
  return out;
}
function stateMoney(s) {
  const m = /Rp\s?([\d.,]+)\s?([MBK])?\b/i.exec(String(s || ''));
  const n = m ? parseFloat(m[1].replace(/,/g, '')) : NaN;
  return isNaN(n) ? null : { n, unit: (m[2] || '').toUpperCase() };
}
/* The gap only exists when both numbers are known and speak the same unit */
function stateGap(now, goal) {
  const a = stateMoney(now), g = stateMoney(goal);
  if (!a || !g || (a.unit !== g.unit && a.n !== 0)) return null;
  const d = Math.max(g.n - a.n, 0);
  return d === 0 ? 'Reached' : `Rp${+d.toFixed(1)}${g.unit}`;
}
/* Situation tier (v11 editorial grammar): a small uppercase label, a serif headline, then the author's
   own paragraphs with their boundaries INTACT. The headline is never invented — it is the first
   sentence of the explanation's authored summary (PlainExplain paragraph 1), or the engine's own
   where-you-are opening when the rewrite has not landed. Long tails fold into destMore; nothing is
   clipped, nothing is regrouped by punctuation math. */
function stateSituation(st, snap) {
  const paras = (Array.isArray(st.where_you_are_paras) && st.where_you_are_paras.length)
    ? st.where_you_are_paras.map(p => String(p || '').trim()).filter(Boolean)
    : (String(st.where_you_are || '').trim() ? [String(st.where_you_are).trim()] : []);
  if (!paras.length) return { headline: '', body: '' };
  const headline = stateSentences(paras[0])[0] || paras[0];
  const rest = paras.map((p, i) => (i === 0 ? p.slice(headline.length).trim() : p)).filter(Boolean);
  const shown = rest.slice(0, 2).map(p => `<p>${stratEsc(p)}</p>`).join('');
  const more = rest.length > 2
    ? destMore('Read the rest of this account', rest.slice(2).map(p => `<p>${stratEsc(p)}</p>`).join('')) : '';
  const goal = snap.goal && snap.goal.text && snap.goal.text !== 'Not set yet' ? snap.goal.text : '';
  const money = stateMoney(goal);
  const flat = paras.join(' ');
  const named = goal && (flat.includes(goal) || (money && flat.includes(`Rp${money.n}${money.unit}`)));
  const aim = goal && !named ? `<p class="dest-aim">Everything here serves one goal: ${stratEsc(goal)}.</p>` : '';
  return { headline, body: shown + more + aim };
}
/* "Why this fits" is bound by EXPLICIT identity only (the snapshot NextMove carries path_id / move_id):
   title similarity can never prove that a path's reason belongs to the decision on screen, so without
   an identity relationship the specific explanation is simply omitted. */
function stateMoveWhy(snap, nmMove) {
  if (!nmMove) return '';
  const host = snap.paths.find(p => p.next_move && (
    (nmMove.move_id && p.next_move.move_id === nmMove.move_id) ||
    (nmMove.path_id && p.id === nmMove.path_id)));
  return host ? String(host.next_move.why || '') : '';
}
/* Progressive disclosure: a quiet one-line summary that opens in place */
function destMore(summary, bodyHtml, open) {
  return `<details class="dest-more"${open ? ' open' : ''}><summary>${summary}</summary><div>${bodyHtml}</div></details>`;
}
function destStep(num, key, hasNext, inner) {
  return `<section class="dest-step dest-${key}${hasNext ? ' has-next' : ''}"><span class="dest-num" aria-hidden="true">${num}</span>${inner}</section>`;
}

/* The paths card when there are none: say the engine's own reason, not a generic "nothing applies" (int 10 §4.3). */
function stateZeroLine(snap, st) {
  if (!st) return 'Nothing applies yet. Paths appear once your Talk gives them something to stand on.';
  const k = (snap.zero && snap.zero.kind) || '';
  const gc = snap.zero && snap.zero.goal_code;
  if (gc === 'GOAL_METRIC_UNSUPPORTED')
    return 'Your goal uses a measure we cannot evaluate yet. That is a limit of the system, not of your goal.';
  if (gc === 'GOAL_UNDERSPECIFIED')
    return 'Your goal is not defined enough to judge paths against yet. Your Talk can pin it down.';
  return {
    INSUFFICIENT_INFORMATION: 'Not enough is known to name a path yet. Your map says why.',
    NO_APPLICABLE_PATH: 'No path applies right now. Your map says why.',
    EVIDENCE_CONFLICT: 'The evidence conflicts, so no path is shown yet. Your map says why.',
    EVALUATION_UNAVAILABLE: 'We could not evaluate your map. This is not a result about your business.',
    LEGACY_ARTIFACT: 'This map needs a fresh look. Your map says more.'
  }[k] || 'No path is shown right now. Your map says why.';
}
/* Goal-Relative rail (int 09 par 6 STATE): labels follow the active metric; a gap is only
   shown when the metric direction makes one meaningful. Unknowns stay visible, never zero. */
function goalGapText(snap) {
  const g = snap.goal || {}, m = g.metric;
  if (!m) {
    const goalSet = g.text && g.text !== 'Not set yet';
    const nowSet = g.now && g.now !== 'Not set yet';
    return goalSet && nowSet ? stateGap(g.now, g.text) : null;
  }
  const sg = ((LIVE.state || {}).goal) || {};
  const cur = sg.current != null ? sg.current : null;
  const tgt = sg.target != null ? sg.target : null;
  if (cur == null || tgt == null) return null;
  if (m.direction === 'INCREASE_TO_THRESHOLD' || m.direction === 'AT_LEAST') {
    const d = Number(tgt) - Number(cur);
    return d <= 0 ? 'Reached' : fmtGoalValue(m, d) + ' to go';
  }
  if (m.direction === 'DECREASE_TO_THRESHOLD' || m.direction === 'AT_MOST') {
    const d = Number(cur) - Number(tgt);
    return d <= 0 ? 'Reached' : fmtGoalValue(m, d) + ' above the limit';
  }
  return null;   /* RATE/COUNT/criteria: a raw "target minus current" would lie (GR-02/GR-09) */
}
const GOAL_GAP_HUMAN = {
  METRIC_UNRESOLVED: 'The business result you mean is not pinned down yet',
  QUALIFICATION_UNDEFINED: 'What counts as qualified is not defined yet',
  WINDOW_MISSING: 'The measuring window is not set yet',
  TARGET_MISSING: 'The success target is not set yet',
  ACTIVITY_NOT_OUTCOME: 'This counts work done, not results - needs clarifying',
  DENOMINATOR_MISSING: 'The rate needs its denominator and cohort',
  DIRECTION_MISSING: 'The direction of success is not set yet'
};
/* One row of the State inspector: the label lives on the summary, the section's content folds under it
   (v11 phase-1: the detail that used to stack on the page now folds inside the panel). */
const ST_ACC_CHEV = '<svg class="st-chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>';
const ST_ACC_ICO = {
  why: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9.1 9.2a3 3 0 0 1 5.8 1c0 2-2.9 2.8-2.9 2.8"/><line x1="12" y1="17" x2="12" y2="17.01"/></svg>',
  hold: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><line x1="10" y1="9" x2="10" y2="15"/><line x1="14" y1="9" x2="14" y2="15"/></svg>',
  numbers: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
  paths: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="5" r="2.2"/><path d="M8 17.5c6-2 4.5-7.5 8-11"/></svg>',
  reassess: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/></svg>',
  changed: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v4l3 2"/></svg>'
};
function stAcc(label, ico, body, open) {
  return `<details class="st-acc"${open ? ' open' : ''}>
      <summary><span class="st-acc-ico">${ST_ACC_ICO[ico] || ''}</span><span>${label}</span>${ST_ACC_CHEV}</summary>
      <div class="st-acc-body">${body}</div>
    </details>`;
}
function stateRail(snap, st) {
  const g = snap.goal || {};
  const m = g.metric || null;
  const goalSet = g.text && g.text !== 'Not set yet';
  const nowSet = g.now && g.now !== 'Not set yet';
  const gap = goalGapText(snap);
  const sp = v11StatusParts();
  const nowLabel = m ? goalNowLabel(m) : 'Income now';
  const fig = (label, value, sub) => `<div class="dest-figure"><span>${label}</span><b>${value}</b>${sub ? `<span class="sub">${sub}</span>` : ''}</div>`;
  const gaps = m && !m.ready ? `
        ${fig('Definition gaps', m.blocking.length ? String(m.blocking.length) : 'some', m.blocking.map(c => GOAL_GAP_HUMAN[c] || c).slice(0, 2).join(' . '))}` : '';
  /* The topics that used to stack on the page: why we think so, what can wait, what changed. */
  const facts = (st && st.why_we_think_so) || [];
  const hold = (st && st.what_not_to_do) || [];
  const changed = ((st && st.changed) || []).filter(t => !/state created/i.test(t));
  const why = st ? stAcc('WHY WE THINK SO', 'why', `
      <p class="v11-prose-sm is-muted">${facts.length ? 'Based on what we’ve seen, we can confirm:' : 'Not much is on record yet.'}</p>
      ${facts.length ? `<ul class="dest-list">${facts.map(t => `<li>${stratEsc(t)}</li>`).join('')}</ul>` : ''}
      <div class="dest-btn-row"><button type="button" class="btn-secondary" onclick="openStateWhyDrawer()">How we got here →</button></div>`, true) : '';
  const holdAcc = hold.length ? stAcc('WHAT NOT TO DO YET', 'hold', `
      <p>Not never. These can wait until the record gives a reason.</p>
      <ul class="dest-list">${hold.map(t => `<li>${stratEsc(t)}</li>`).join('')}</ul>
      ${st.what_not_to_do_note ? `<p class="v11-prose-sm is-muted">${stratEsc(st.what_not_to_do_note)}</p>` : ''}
      ${st.what_not_to_do_until ? `<p class="v11-prose-sm is-muted">It can move when: ${stratEsc(st.what_not_to_do_until)}</p>` : ''}`, false) : '';
  const changedAcc = changed.length ? stAcc('WHAT CHANGED', 'changed', `
      <p class="v11-prose-sm is-muted">Since your last assessment:</p>
      ${changed.map(t => `<div class="v11-trail-item">${stratEsc(t)}</div>`).join('')}`, false) : '';
  const numbers = stAcc('YOUR NUMBERS', 'numbers', `
      <section class="dest-panel-sec dest-numbers" aria-label="Your numbers">
        <div class="dest-figures">
          ${fig(nowLabel, nowSet ? stratEsc(g.now) : 'Not set', nowSet ? '' : 'add it at your next check-in')}
          ${fig('Goal', goalSet ? stratEsc(g.text) : 'Not set', goalSet ? '' : 'a Talk sets it')}
          ${gap ? fig('Still to go', gap) : ''}
          ${gaps}
          ${g.horizon ? fig('Deadline', stratEsc(g.horizon), sp.horizon && sp.horizon > sp.day ? stateN(sp.horizon - sp.day, 'day', 'days') + ' left' : '') : ''}
        </div>
      </section>`, true);
  const pres = presentSnapshotPaths(snap.paths, {});
  const shown = pres.visible;
  const paths = stAcc('PATHS ON YOUR MAP', 'paths', `
      <section class="dest-panel-sec dest-paths" aria-label="Paths on your map">
        ${shown.length ? `
        <p>${stateN(snap.paths.length, 'possible path', 'possible paths')}. In no particular order.</p>
        <div class="dest-routes">${shown.map(p => `<button type="button" class="dest-route" onclick="openMapsAt('${p.id}')"><span>${stratEsc(p.title)}${p.goal_relation === 'UNKNOWN_RELATION' ? ' <span style="color:var(--ink-3);font-weight:400">· hypothesis</span>' : ''}</span><span class="dest-route-state ${(STRAT_STATUS_FROM_DISPLAY[p.status_display] || 'NOT_YET').toLowerCase()}">${p.status_display}</span></button>`).join('')}</div>
        ${pres.hidden.length > 0 ? `<span class="dest-more-routes">+${pres.hidden.length} other possibilit${pres.hidden.length === 1 ? 'y' : 'ies'} on your map</span>` : ''}`
      : `
        <p>${stateZeroLine(snap, st)}</p>`}
      </section>`, true);
  const reassess = st && st.when_to_reassess ? stAcc('REASSESS', 'reassess', `
      <section class="dest-panel-sec dest-reassess" aria-label="When to reassess">
        <p>${stratEsc(st.when_to_reassess)}</p>
      </section>`, true) : '';
  return `${why}${holdAcc}${numbers}${paths}${reassess}${changedAcc}`;
}
/* The inspector itself: the foldable topics and the map sections, with the two ways out in the foot.
   It hides from its own top-right control; a hidden panel leaves the "Show details" pill on the header. */
function statePanel(snap, st) {
  return `
  <aside class="ws-side st-side has-panel-hide" id="st-side" aria-label="Detail and reasons">
    ${wsPanelHideBtn('st-side-toggle', 'st-side', 'setStateSide', 'detail and reasons')}
    <div class="st-side-head">
      <div class="st-eyebrow">Detail and reasons</div>
      <p class="st-fine">Every line traces to the record. Fold any topic you don't need.</p>
    </div>
    <div class="st-acc-list dest-rail" id="dest-rail" role="group" aria-label="Your numbers, your paths, and when to reassess">
      ${stateRail(snap, st)}
    </div>
    <div class="st-side-foot">
      <button type="button" class="st-cta st-cta-quiet" onclick="goDestination('maps')">See your map</button>
      <button type="button" class="st-cta st-cta-quiet" onclick="goDestination('talk')">Talk about this →</button>
    </div>
  </aside>`;
}

function screenState11() {
  liveEnsureExplain();   // no-op unless the plain-language rewrite has not been asked for yet (demo: no-op); the page re-renders when it lands
  const snap = V11_ENGINE.snapshot();
  if (!snap.state) return screenStateZero(snap);
  const st = snap.state;
  const ev = snap.evidence || [];
  const facts = st.why_we_think_so || [];
  const unsure = st.uncertain || [];
  const hold = st.what_not_to_do || [];
  const changed = (st.changed || []).filter(t => !/state created/i.test(t));
  const asks = snap.nextmove && /^(EVIDENCE_REQUEST|QUESTION)$/.test(snap.nextmove.type);
  /* R5/P0-3: the NEXT MOVE card uses ONE live decision (snapshot.nextmove = validated nm.v2).
     Diagnosis/explanation are narrative context only; they do not replace the decision. st.next_best_action
     is kept ONLY as a fallback when the snapshot carries no nextmove (demo/legacy compat) and
     is labeled with its source so the fallback does not masquerade as a live decision. */
  const nmMove = snap.nextmove;
  const moveTitle = (nmMove && nmMove.title) ? nmMove.title : (st.next_best_action || '');
  /* The note describes WHERE THE SHOWN TITLE CAME FROM, not merely nmMove.source: a routes fallback can
     carry an empty title, in which case the title below is the diagnosis plan and must say so. A demo
     fixture (no source) is the prototype's own live move, never labelled a fallback. */
  const moveFromPlan = !(nmMove && nmMove.title);
  const moveSourceKey = moveFromPlan ? 'plan' : ((nmMove && nmMove.source) || 'presented');
  const moveSourceNote = !moveTitle ? '' : ({
    presented: '',
    'routes.next_move': 'From your map’s current step',
    plan: 'From your last plan'
  }[moveSourceKey] || '');
  const why = moveTitle ? stateMoveWhy(snap, nmMove) : '';
  /* A3-02: WHY THIS FITS must explain the decision being SHOWN. The diagnosis's next_best_why
     is only valid when the shown title IS that diagnosis action; otherwise it is a stale reason for another
     step and must not be silently attached to a different live decision. */
  const whyFromDiagnosis = !!(st.next_best_action && st.next_best_action === moveTitle);
  const whyText = (whyFromDiagnosis ? st.next_best_why : '') || why;
  /* EER: the CTA routes by the decision's own kind, never a fixed "open Moves". QUESTION and
     EVIDENCE_REQUEST continue in Talk; ACTION opens Moves; HOLD explains the pending state with no
     executable CTA; NONE invents nothing; degraded carries honest technical-recovery messaging, never
     a business STOP. Legacy fallback (plan step, no kind on the record) keeps the Moves route. */
  /* The CTA and its explanation are split: the button sits on the card's right edge (v11), the honesty
     notes (degraded / hold) stay with the text they explain. */
  const moveCta = (() => {
    if (!nmMove) return moveTitle ? { note: '', btn: `<button class="btn-primary st-cta dest-cta" onclick="goDestination('moves')">Go to your move →</button>` } : { note: '', btn: '' };
    if (nmMove.degraded) return { note: `<p class="v11-prose-sm is-muted" data-move-recovery>We could not finish computing this move — a technical problem on our side. Nothing on your map stopped, and this says nothing about your business. It is rebuilt from Talk.</p>`, btn: `<button class="btn-primary st-cta dest-cta" onclick="goDestination('talk')">Recover in Talk →</button>` };
    if (nmMove.type === 'ACTION') return { note: '', btn: `<button class="btn-primary st-cta dest-cta" onclick="goDestination('moves')">Go to your move →</button>` };
    if (nmMove.type === 'QUESTION' || nmMove.type === 'EVIDENCE_REQUEST') return { note: '', btn: `<button class="btn-primary st-cta dest-cta" onclick="goDestination('talk')">Continue in Talk →</button>` };
    if (nmMove.type === 'HOLD') return { note: `<p class="v11-prose-sm is-muted" data-move-hold>This move is on hold until its checks pass. There is nothing to run yet — your map says what would open it.</p>`, btn: '' };
    return { note: '', btn: '' };   /* NONE: the engine decided nothing is executable, so no CTA is invented */
  })();
  const provisional = !!st.provisional;

  const focus = st.blocking || unsure.length ? `
      <section class="dest-focus st-card st-matters" aria-labelledby="st-matters-label">
        <div class="section-meta-label mb-0" id="st-matters-label">WHAT MATTERS NOW</div>
        ${st.blocking
          ? `<h2 class="st-headline is-secondary">${stratEsc(st.blocking)}</h2>`
          : `<h2 class="st-headline is-secondary">What we don’t know yet</h2>`}
        ${st.blocking && st.blocking_body ? `<p class="dest-focus-note">${stratEsc(st.blocking_body)}</p>` : ''}
        ${st.blocking && unsure.length ? destMore(`What we don’t know yet · ${unsure.length}`,
          `<ul class="dest-list">${unsure.map(t => `<li>${stratEsc(t)}</li>`).join('')}</ul><p>Not known is not no. Finding out is a move.</p>`, asks) : ''}
        ${!st.blocking && unsure.length ? `<ul class="dest-list">${unsure.map(t => `<li>${stratEsc(t)}</li>`).join('')}</ul><p class="dest-focus-note">Not known is not no. Finding out is a move.</p>` : ''}
      </section>` : '';

  /* Tier 3 — YOUR NEXT DECISION (EER §7.4): the framed card is the page's one action. What not to do,
     why we think so and what changed fold into the inspector (v11 phase-1: detail lives in the panel). */
  /* The kind label never defaults a missing NextMove to ACTION: a kindless legacy plan fallback is
     labelled with its own source, and NONE stays NONE — no executable action is implied. */
  const nmType = (nmMove && nmMove.type) || '';
  const decisionKind = nmType
    ? ({ ACTION: 'MOVE', QUESTION: 'QUESTION', EVIDENCE_REQUEST: 'EVIDENCE REQUEST', HOLD: 'HOLD', NONE: 'NONE' }[nmType] || nmType)
    : (moveTitle ? 'MOVE · FROM YOUR LAST PLAN' : 'NONE ON RECORD');
  const moveCard = moveTitle ? `
      <section class="dest-step dest-s1 st-move-card" role="group" aria-labelledby="st-move-label">
        <div class="st-move-text dest-action" data-move-source="${stratEsc(moveSourceKey)}">
          <div class="section-meta-label mb-0" id="st-move-label">YOUR NEXT DECISION · ${decisionKind}${decisionKind === 'MOVE' && nmMove && nmMove.minutes ? ` · ABOUT ${nmMove.minutes} MIN` : ''}</div>
          <h3 class="st-move-h">${stratEsc(moveTitle)}</h3>
          ${moveSourceNote ? `<p class="v11-prose-sm is-muted" data-move-source-note>${stratEsc(moveSourceNote)}</p>` : ''}
          ${whyText ? `<div class="section-meta-label dest-sublabel">WHY THIS FITS</div><p class="st-body st-small">${stratEsc(whyText)}</p>` : ''}
          ${st.know_right_when ? `<p class="st-body st-small"><span class="st-lead">We’ll know we’re right when</span> ${stratEsc(st.know_right_when)}</p>` : ''}
          ${moveCta.note}
        </div>
        ${moveCta.btn}
      </section>` : '';

  /* Situation tier (v11): the opening is contextual — small uppercase label + serif headline drawn from
     the record's own first sentence, never a generic page title. When no authored text exists the label
     alone carries the section and the summary is presented without a fabricated headline. */
  const sit = stateSituation(st, snap);
  const sideClosed = !!STORE.stateSideClosed;
  const content = `
  <div class="dest-page st-page ws-split${sideClosed ? ' is-collapsed' : ''}">
    <div class="ws-main">
      <div class="ws-inner">
        <section class="st-card st-now" aria-labelledby="${sit.headline ? 'state-h1' : 'state-label'}">
          <header class="dest-hero">
            <div class="v11-pagehead">
              <div class="v11-pagehead-text">
                <div class="st-eyebrow" id="state-label">CURRENT SITUATION</div>
                ${sit.headline ? `<h1 class="serif-heading" id="state-h1">${stratEsc(sit.headline)}</h1>` : ''}
              </div>
              ${sideClosed ? `<div class="v11-pagehead-actions st-now-actions">${wsPanelShowBtn('st-side-toggle', 'st-side', 'setStateSide', 'detail and reasons')}</div>` : ''}
            </div>
            <div class="dest-narrative">${sit.body}</div>
            ${provisional ? '<p class="v11-prose-sm is-muted" data-testid="state-provisional">This is a first read. It firms up as you tell us more in Talk.</p>' : ''}
          </header>
        </section>
        ${focus}
        <div class="dest-steps">${moveCard}</div>
      </div>
    </div>
    ${sideClosed ? '' : statePanel(snap, st)}
  </div>`;
  return renderAppShell('state', 'State', content);
}

/* Why-drawer for the State destination, in reading order: summary → evidence (by source) →
   what we made of it → what happened, in order → correct it. Built from the snapshot. */
function openStateWhyDrawer() {
  const snap = V11_ENGINE.snapshot();
  const st = snap.state || {};
  const ev = snap.evidence || [];
  const sec = (label, inner) => `<section style="display:flex;flex-direction:column;gap:10px"><div class="section-meta-label mb-0">${label}</div>${inner}</section>`;
  const bySource = {};
  ev.forEach(e => { (bySource[e.source || 'On record'] = bySource[e.source || 'On record'] || []).push(e); });
  const evidence = ev.length ? Object.keys(bySource).map(src => `
      <div class="dest-src">
        <div class="dest-src-name">${stratEsc(src)}</div>
        ${bySource[src].map(e => `<p class="dest-quote">“${stratEsc(e.quote)}”${e.disputed ? ' <span class="v11-disputed-badge">DISPUTED</span>' : ''}</p>`).join('')}
      </div>`).join('') : '<p class="v11-prose-sm is-muted">Nothing is on record yet.</p>';
  const read = (label, items) => (items || []).length ? `
      <div class="dest-read"><strong>${label}</strong><ul class="dest-list">${items.map(t => `<li>${stratEsc(t)}</li>`).join('')}</ul></div>` : '';
  const lead = stateSentences(st.where_you_are)[0] || '';
  const body = `
    <div class="rv-stack">
      ${sec('IN SHORT', `<p class="rv-p">${stratEsc(lead)}</p>
        <p class="rv-p-sm">This is not an opinion about you. It is what the record supports right now, built from ${stateN(ev.length, 'thing', 'things')} on record. Each one names where it came from.</p>`)}
      ${sec('THE EVIDENCE, BY SOURCE', `<div style="display:flex;flex-direction:column;gap:10px">${evidence}</div>`)}
      ${sec('WHAT WE MADE OF IT', `
        ${read('True on the record', st.why_we_think_so)}
        ${read('Not known yet', st.uncertain)}
        ${st.blocking ? `<div class="dest-read"><strong>Holding movement</strong><p class="rv-body" style="color:var(--ink-2)">${stratEsc(st.blocking)}</p></div>` : ''}
        ${destMore('How to read these words', `
          <p><strong>True on the record</strong>: evidence behind it, on the trail.</p>
          <p><strong>Partly shown</strong>: some evidence, not enough to settle it.</p>
          <p><strong>Not known yet</strong>: is not no. Finding out is a move.</p>
          <p><strong>Missing</strong>: what holds a path closed right now.</p>`)}`)}
      ${(st.changed || []).length ? sec('WHAT HAPPENED, IN ORDER', `<div style="display:flex;flex-direction:column;gap:8px">${st.changed.map(t => `<div class="v11-trail-item">${stratEsc(t)}</div>`).join('')}</div>`) : ''}
      <div class="rv-foot is-split" style="padding-top:16px">
        <span class="rv-fine" style="max-width:34ch">Something wrong here? Correct it in Talk. The trail keeps both versions.</span>
        <button class="btn-secondary btn-sm" onclick="closeDrawer();goDestination('talk')">Open Talk →</button>
      </div>
    </div>`;
  openWhyDrawer('WHY THIS STATE?', 'Why your state reads this way', 'Every line traces to the record.', body);
}

/* A fresh map has nothing on record. Same grammar as the full page: say so, say why,
   point to Talk. It never invents a state to look useful. */
function screenStateZero(snap) {
  const sideClosed = !!STORE.stateSideClosed;
  const content = `
  <div class="dest-page st-page ws-split${sideClosed ? ' is-collapsed' : ''}">
    <div class="ws-main">
      <div class="ws-inner">
        <section class="st-card st-now" aria-labelledby="state-h1">
          <header class="dest-hero">
            <div class="v11-pagehead">
              <div class="v11-pagehead-text">
                <div class="st-eyebrow" id="state-label">CURRENT SITUATION</div>
                <h1 class="serif-heading" id="state-h1">We can’t read that honestly yet.</h1>
              </div>
              ${sideClosed ? `<div class="v11-pagehead-actions st-now-actions">${wsPanelShowBtn('st-side-toggle', 'st-side', 'setStateSide', 'detail and reasons')}</div>` : ''}
            </div>
            <div class="dest-narrative">
              <p>Nothing is on record. Your state is written from what you tell us and what the evidence shows. Until then this page shows nothing rather than guess, and nothing is hidden from you.</p>
            </div>
          </header>
        </section>
        <div class="dest-steps">
          <section class="dest-step dest-s1 st-move-card">
            <div class="st-move-text dest-action">
              <div class="section-meta-label mb-0">FIRST, A CONVERSATION</div>
              <h3 class="st-move-h">A short Talk writes your first state: what is true, what is not known yet, and what to try first.</h3>
            </div>
            <button class="btn-primary st-cta dest-cta" onclick="goDestination('talk')">Start your first Talk →</button>
          </section>
        </div>
      </div>
    </div>
    ${sideClosed ? '' : statePanel(snap, null)}
  </div>`;
  return renderAppShell('state', 'State', content);
}

/* Prototype menu: jump straight to a step that shows one kind of task card (int 13).
   The project opens where that card lives, with the steps before it done. */

function screenMoves11() { return IS_DEMO ? screen04() : screen04Live(); }   // both build their page through renderAppShell and renderTodayLayout, which are v11 unless a LEGACY screen is drawn


/* ── V11 Moves layout (record P5c; int 10 §6.3): one move on screen, and what else is alive around it ─────────────────
   The working set is read from the plan (the steps the diagnosis wrote, with their own prerequisites), from the engine's
   routes ("also ready"), from the snapshot (paths that are open or worth a test, what is on hold) and from the engine's
   NextMove when it is a question. Marking a move done records the action; it never claims the result or that the map moved. */
/* Move-status pill: retired in Phase 2 — the parent work context no longer needs a per-selection pill. */
/* Moves queues: what else is alive besides the move on screen. The card is the prototype's
   (.mv-card.mv-queues); the rows keep the product's own hooks (.moves-q / .section-meta-label /
   .moves-q-row / .moves-q-link), because those rows are asserted by moves.spec and goal-relative.spec. */
function renderMovesQueues(v) {
  const snap = V11_ENGINE.snapshot();
  const also = (snap.paths || []).filter(p => (p.status_display === 'OPEN' || p.status_display === 'TEST FIRST') && esc(p.title) !== v.pathTitle).slice(0, 3);
  const hold = (snap.state && snap.state.what_not_to_do) || [];
  const asks = snap.nextmove && /^(EVIDENCE_REQUEST|QUESTION)$/.test(snap.nextmove.type) && snap.nextmove.title ? snap.nextmove : null;
  const rows = [];
  if (v.routeTasks) rows.push(`<div class="moves-routes">${v.routeTasks}</div>`);
  const asksPath = asks && asks.path_id ? (snap.paths || []).find(x => x.id === asks.path_id) : null;
  if (asks) rows.push(`
    <div class="moves-q">
      <div class="section-meta-label mb-2">NEEDS EVIDENCE · NOT KNOWN YET</div>
      <div class="moves-q-row"><span>${stratEsc(asks.title)}${isHypothesisPath(asksPath) ? ' ' + relationChipHtml(asksPath) : ''}</span><button type="button" class="moves-q-link" onclick="goDestination('talk')">Answer in Talk →</button></div>
    </div>`);
  if (also.length) rows.push(`
    <div class="moves-q">
      <div class="section-meta-label mb-2">ALSO READY ON YOUR MAP</div>
      ${also.map(p => `<div class="moves-q-row"><span>${stratEsc(p.title)}${isHypothesisPath(p) ? ' ' + relationChipHtml(p) : ''}${p.next_move ? `: ${stratEsc(p.next_move.title)}` : ''}</span><button type="button" class="moves-q-link" onclick="openMapsAt('${esc(p.id)}')">Open Maps →</button></div>`).join('')}
    </div>`);
  if (hold.length) rows.push(`
    <div class="moves-q">
      <div class="section-meta-label mb-8">ON HOLD · UNTIL THE RECORD CHANGES</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px">${hold.map(h => `<span class="status-pill hold">${stratEsc(h)}</span>`).join('')}</div>
    </div>`);
  return `
  <section class="mv-card mv-queues moves-queues" aria-labelledby="mv-list-label">
    <div class="mv-list-head"><h2 class="mv-eyebrow" id="mv-list-label">OTHER AVAILABLE WORK</h2>${rows.length ? `<span class="st-count">${rows.length}</span>` : ''}</div>
    ${rows.length ? rows.join('') : '<p class="mv-fine">Nothing else is alive around this move yet. Another move appears once a path on your map names its next step.</p>'}
  </section>`;
}
/* ── Moves grammar (phase-1, ported from Revenue Navigation v11.dc.html: the base grammar 1430-1500,
   tiles 2728-2761, the step section 2867-2889, the context panel 3576-3584, the ws-split overrides
   4907-4950). The icon paths are the prototype's own, so the marks match. ── */
const MV_ICO = {
  bulb: '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
  ban: '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/>'
};
function mvIco(name) {
  return `<svg class="st-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${MV_ICO[name] || ''}</svg>`;
}
const MOVES_REQ_WORD = { PRESENT: 'On record', PARTIAL: 'Partly on record', UNKNOWN: 'Not known yet', ABSENT: 'Missing' };
const MV_NEED_CLS = { PRESENT: 'present', PARTIAL: 'partial', UNKNOWN: 'unknown', ABSENT: 'absent' };
const MV_NEED_MARK = { PRESENT: '✓', PARTIAL: '◐', UNKNOWN: '?', ABSENT: '✕' };
/* The mark and the word both carry the state, so colour never does it alone. */
function mvReqMark(s) {
  return `<span class="mv-need-mark mv-need-${MV_NEED_CLS[s] || 'unknown'}" aria-hidden="true">${MV_NEED_MARK[s] || '?'}</span>`;
}
function mvNeedsList(reqs) {
  return reqs.length ? `<ul class="mv-needs">${reqs.map(r => `<li class="mv-need">${mvReqMark(r.satisfaction)}<span class="mv-need-label">${stratEsc(r.label)}</span><span class="mv-req mv-req-${MV_NEED_CLS[r.satisfaction] || 'unknown'}">${MOVES_REQ_WORD[r.satisfaction] || stratEsc(r.satisfaction)}</span></li>`).join('')}</ul>`
    : '<p>No requirements are on record for this path.</p>';
}
/* mvFact retired in Phase 2: the expanded action carries its own instruction and timing. */
function mvAcc(key, icon, label, count, inner, open) {
  return `<details class="st-acc" id="mv-acc-${key}"${open ? ' open' : ''}>
      <summary><span class="st-acc-ico">${mvIco(icon)}</span><span>${label}</span>${count === null ? '' : `<span class="st-count">${count}</span>`}${ST_ACC_CHEV}</summary>
      <div class="st-acc-body">${inner}</div>
    </details>`;
}
/* Phase 2 interaction model: the parent work context is stable; selecting an action only expands
   its own detail inline. STORE.viewStep is a UI-only selection, never a business event. */
function mvScrollEl() { return document.querySelector('.mv-page .ws-main'); }
function mvToggleStep(num) {
  if (!num || STORE.viewStep === num) return;
  const sc = mvScrollEl();
  const y = sc ? sc.scrollTop : window.scrollY;
  STORE.viewStep = num;
  renderScreen('04');
  const sc2 = mvScrollEl();
  if (sc2) sc2.scrollTop = y; else window.scrollTo(0, y);
  const btn = document.querySelector(`.mv-action-head[aria-controls="mv-act-${num}"]`);
  if (btn) btn.focus({ preventScroll: true });
}
/* Completion controls belong INSIDE the expanded action and carry the step's own identity. */
function mvStepActions(s, rs, advanceFn) {
  if (s.hold) return '<span class="today-note">On hold: later steps wait for what your first results show.</span>';
  if (s.ready === false) {
    const first = rs.steps[s.waitingFor[0] - 1];
    return `<button class="btn-primary" onclick="mvToggleStep(${first ? first.num : s.num})">Start with step ${first ? first.num : ''} →</button>
        <span class="today-note">${stepWaitNote(s, rs.steps)}.</span>`;
  }
  if (IS_DEMO) {
    return `<button class="btn-primary" onclick="${advanceFn}(${s.num})">${s.sent ? 'Record as sent' : 'Record as done'}</button>
        <button class="btn-secondary" onclick="notTodayStep()">Pick a different action</button>`;
  }
  /* Live: this file is the ONLY place a step's execution status is mutated from the UI. DONE keeps
     the existing path; SKIPPED and BLOCKED are their own explicit controls with their own confirm. */
  return `<button class="btn-primary" onclick="liveAdvanceStep(${s.num}, this)">${s.sent ? 'Record as sent' : 'Record as done'}</button>
        <button class="btn-secondary" onclick="liveSkipStep(${s.num}, this)">Mark as skipped</button>
        <button class="btn-secondary" onclick="liveBlockStep(${s.num}, this)">Mark as blocked</button>
        <button class="btn-secondary" onclick="notTodayStep()">Pick a different action</button>`;
}
/* ── Execution facts for the Moves copy (NC-R6) ───────────────────────────────
   One read of the plan record, and one row state per action. Execution status comes from the
   canonical plan action (live) with the browser step only as a fallback, so SKIPPED and BLOCKED can
   never render as Done. Counts come from liveWorkContextSummary() when the projection layer exposes
   them, then from the plan record's own counts, then from the actions themselves. */
function mvPlanRecord() {
  const p = (!IS_DEMO && LIVE.experience) ? LIVE.experience.plan : null;
  if (!p || typeof p !== 'object') return null;
  const cur = (p.current && typeof p.current === 'object') ? p.current : null;
  const superseded = Array.isArray(p.superseded) ? p.superseded : [];
  const n = (typeof p.superseded_total === 'number') ? p.superseded_total : superseded.length;
  return { raw: p, current: cur, supersededCount: n || 0 };
}
function mvPlanCurrent() {
  const rec = mvPlanRecord();
  return rec ? rec.current : null;
}
function mvPlanSupersededCount() {
  const rec = mvPlanRecord();
  return rec ? rec.supersededCount : 0;
}
function mvRowState(s) {
  let status = '';
  let hasOutcome = !!(s && s.outcome);
  if (!IS_DEMO && s && typeof s.idx === 'number' && s.idx >= 0 && typeof livePlanActionState === 'function') {
    const pst = livePlanActionState(s.idx);
    if (pst) {
      if (pst.status) status = String(pst.status).toUpperCase();
      hasOutcome = !!pst.hasOutcome || !!pst.outcome;
    }
  }
  if (!status && s) status = String(s.rawStatus || '').toUpperCase();
  if (!status && s && s.status === STEP_STATUS.COMPLETED) status = 'DONE';
  if (status !== 'DONE' && status !== 'SKIPPED' && status !== 'BLOCKED') status = 'TODO';
  return {
    status: status,
    label: { DONE: 'Done', SKIPPED: 'Skipped', BLOCKED: 'Blocked', TODO: 'Not started' }[status],
    executed: status === 'DONE', skipped: status === 'SKIPPED', blocked: status === 'BLOCKED',
    closed: status !== 'TODO', hasOutcome: hasOutcome
  };
}
/* The stored execution fact, said in the plan action's own words. A skipped step is never "done". */
function mvClosedNote(st, s) {
  /* Only a REAL completion timestamp is shown, as a date: the legacy plan no longer carries a day
     label in this product. */
  const stamp = mvDoneStamp(s);
  if (st.status === 'DONE') {
    return `Recorded as done${stamp ? ` on ${stamp}` : ''}. Done means the action was finished, not that it worked.`;
  }
  if (st.status === 'SKIPPED') {
    return `Recorded as skipped${stamp ? ` on ${stamp}` : ''}. Skipped means the action was not done, so it is not counted as done.`;
  }
  if (st.status === 'BLOCKED') return 'Recorded as blocked. Blocked is not done and not skipped, and it stays open work.';
  return '';
}
/* A closed step that was not executed can still be corrected to done; the operation keeps its own id. */
function mvClosedControls(s, st) {
  if (IS_DEMO || (st.status !== 'SKIPPED' && st.status !== 'BLOCKED')) return '';
  return `<div class="mv-actions today-actions"><button type="button" class="btn-secondary btn-sm" onclick="liveAdvanceStep(${s.num}, this)">Record as done instead</button></div>`;
}
/* NC-04: the outcome dialog is reachable for EVERY action that has no outcome yet, not only the last
   one. This opens the same dialog focused on this action; it never touches execution. */
function mvActionOutcomeLink(s, st) {
  if (IS_DEMO || !st || st.hasOutcome) return '';
  if (typeof s.idx !== 'number' || s.idx < 0) return '';
  if (typeof openMovesOutcomeReport !== 'function') return '';
  return `<div class="mv-actions today-actions"><button type="button" class="moves-q-link" onclick="openMovesOutcomeForAction(${s.idx})">Add an outcome for this action →</button></div>`;
}
function openMovesOutcomeForAction(idx) {
  if (IS_DEMO || !LIVE.artifact) return;
  const i = Number(idx);
  if (!isFinite(i)) return;
  STORE.movesReportIndex = i;
  openMovesOutcomeReport();
}
/* Canonical counts for the CURRENT plan. Missing projection fields are derived, never guessed:
   DONE is counted only from DONE, and SKIPPED and BLOCKED stay their own numbers (NC-R6). */
function mvExecutionCounts() {
  const sum = (!IS_DEMO && typeof liveWorkContextSummary === 'function') ? liveWorkContextSummary() : null;
  const states = (!IS_DEMO && typeof livePlanActionItems === 'function')
    ? livePlanActionItems().filter(a => !a.hold)
      .map(a => (typeof livePlanActionState === 'function') ? livePlanActionState(a.idx) : null).filter(Boolean)
    : [];
  const rc = (() => { const cur = mvPlanCurrent(); return (cur && cur.counts && typeof cur.counts === 'object') ? cur.counts : null; })();
  const num = v => (typeof v === 'number' && isFinite(v)) ? v : null;
  const first = (...vals) => { for (const v of vals) { const n = num(v); if (n != null) return n; } return null; };
  const byStatus = k => states.filter(st => String(st.status || '').toUpperCase() === k).length;
  let total = first(sum && sum.total, rc && rc.total, states.length) || 0;
  let executed = first(sum && sum.executed, rc && rc.executed, rc && rc.done, states.length ? byStatus('DONE') : 0) || 0;
  let skipped = first(sum && sum.skipped, rc && rc.skipped, states.length ? byStatus('SKIPPED') : 0) || 0;
  let blocked = first(sum && sum.blocked, rc && rc.blocked, states.length ? byStatus('BLOCKED') : 0) || 0;
  let closed = first(sum && sum.closed, rc && rc.closed, executed + skipped + blocked) || 0;
  /* A current plan with no recorded steps must never borrow the previous plan's completion. */
  const scopeEmpty = !!(rc && num(rc.total) === 0 && mvPlanSupersededCount() > 0);
  if (scopeEmpty) { total = 0; executed = 0; skipped = 0; blocked = 0; closed = 0; }
  const allExecuted = (sum && typeof sum.allExecuted === 'boolean') ? sum.allExecuted
    : ((rc && typeof rc.executed_all === 'boolean') ? rc.executed_all : (total > 0 && executed === total));
  const allClosed = (sum && typeof sum.allClosed === 'boolean') ? sum.allClosed
    : ((rc && typeof rc.complete === 'boolean') ? rc.complete : (total > 0 && closed === total && blocked === 0));
  return {
    total: total, executed: executed, skipped: skipped, blocked: blocked, closed: closed,
    open: Math.max(total - closed, 0), scopeEmpty: scopeEmpty,
    allExecuted: !!(allExecuted && total > 0), allClosed: !!(allClosed && total > 0),
    hasAnyOutcome: !!(sum && sum.hasAnyOutcome)
  };
}
/* "2 done, 1 skipped" - only the facts that are non-zero, each with its own word. */
function mvExecutionParts(c) {
  const parts = [];
  if (c.executed) parts.push(c.executed + ' done');
  if (c.skipped) parts.push(c.skipped + ' skipped');
  if (c.blocked) parts.push(c.blocked + ' blocked');
  if (c.open) parts.push(c.open + ' not started');
  return parts.join(', ');
}
/* The headline says all done ONLY when every step is DONE. Closed work with a skip or a block is
   named as what it is, so "closed" is never read as "executed" (NC-R6). */
function mvExecutionHeadline(c) {
  if (!c || !c.total) return '';
  const parts = mvExecutionParts(c);
  if (c.allExecuted) return c.total === 1 ? 'The one action step is done.' : `All ${c.total} action steps done.`;
  if (c.allClosed && !c.blocked) return parts ? `All action steps closed - ${parts}.` : 'All action steps closed.';
  if (c.blocked && c.closed === c.total) return `All action steps closed - ${parts}.`;
  if (c.closed) return `${c.closed} of ${c.total} action steps closed${parts ? ' - ' + parts : ''}.`;
  return 'No steps are recorded as closed yet.';
}
/* The list header names the state only while steps remain open; the closed summary belongs to the
   report section, so the same count is not printed twice. */
function mvExecutionProgressNote(c) {
  if (!c || !c.total || c.allExecuted) return '';
  /* When the report section states the same count (context closed, no outcome yet), the header stays
     quiet so one fact is not printed twice. Every other case shows the execution summary here. */
  const sum = (!IS_DEMO && typeof liveWorkContextSummary === 'function') ? liveWorkContextSummary() : null;
  const recorded = !!(sum && sum.hasAnyOutcome);
  const ctx = (!recorded && !IS_DEMO && typeof liveMovesReportContext === 'function') ? liveMovesReportContext() : null;
  if (ctx) return '';
  return mvExecutionHeadline(c);
}
/* The number of steps counts the CURRENT plan only. When it carries no recorded steps while an
   earlier plan did, the previous plan's completion is never shown as this plan's progress; the
   projection layer owns the wording when it offers one (livePlanScopeLabel, called defensively). */
function mvPlanScopeNote(actionN) {
  const rec = mvPlanRecord();
  if (!rec) return '';
  let label = '';
  if (typeof livePlanScopeLabel === 'function') {
    try { const l = livePlanScopeLabel(rec.current || rec.raw); if (typeof l === 'string') label = l.trim(); }
    catch (e) { label = ''; }   // a projection helper mid-change must never break the page
  }
  if (label) return label;
  const rc = (rec.current && rec.current.counts && typeof rec.current.counts === 'object') ? rec.current.counts : null;
  const planEmpty = !!(rc && typeof rc.total === 'number' && rc.total === 0);
  if ((planEmpty || !actionN) && rec.supersededCount) {
    return 'No action steps are recorded on this plan yet. Steps from earlier plans are not counted here.';
  }
  return '';
}
/* The record is saved; the view may be behind. The only control offered is the read-only retry. */
function mvSaveNoticeHtml() {
  const n = LIVE.movesSaveNotice;
  if (!n) return '';
  /* The notice speaks about the read that failed: any later consistent read clears it. */
  if (!LIVE.lastRefreshFailed && !LIVE.experienceError) { LIVE.movesSaveNotice = null; return ''; }
  const word = n.status === 'DONE' ? 'completed' : (n.status === 'SKIPPED' ? 'skipped' : 'blocked');
  return `<div class="today-banner" role="status">
        <span class="today-banner-icon">✓</span>
        <span style="flex:1;min-width:0">Step recorded as ${word}. Your record is saved. This view could not be refreshed, so it may be behind.
          <button type="button" class="moves-q-link" onclick="mvRetryRefresh()">Retry refresh →</button></span>
      </div>`;
}
/* What was REPORTED about a legacy plan action, read from the plan record's own row. A reported result
   is not an execution status and never changes one. */
function mvPlanRowResult(s) {
  const out = { outcome: '', note: '', reportedAt: null };
  if (s && typeof s.idx === 'number' && s.idx >= 0 && typeof livePlanActionState === 'function') {
    const pst = livePlanActionState(s.idx);
    if (pst) { out.outcome = String(pst.outcome || ''); out.note = String(pst.note || ''); out.reportedAt = pst.reportedAt || null; }
  }
  if (!out.outcome && s) out.outcome = String(s.outcome || '');
  if (!out.note && s) out.note = String(s.note || '');
  return out;
}
/* The legacy action list. On the Moves screen it is HISTORY only ({ history: true }): the recorded
   statuses and reported results, with NO Done / Skip / Block controls and no day labels. The
   interactive form below is the prototype's demo path (screen04); it is not the live work surface.
   Report steps stay out of the list — reporting belongs to the Move — but keep their indexing. */
function mvActionList(v, opts) {
  const history = !!(opts && opts.history);
  const all = v.steps || [];
  const steps = all.filter(s => !s.report);
  if (!steps.length) return '';
  if (history) {
    const rows = steps.map(s => {
      const st = mvRowState(s);
      const res = mvPlanRowResult(s);
      const stamp = st.status === 'DONE' ? mvDoneStamp(s) : '';
      const word = st.status === 'DONE' ? 'Done' : (st.status === 'SKIPPED' ? 'Skipped' : (st.status === 'BLOCKED' ? 'Blocked' : 'Not started'));
      const mark = st.status === 'DONE' ? '✓' : (st.status === 'SKIPPED' ? '–' : (st.status === 'BLOCKED' ? '!' : ''));
      const bits = [];
      if (res.outcome) bits.push('Result recorded: ' + esc(mvOutcomeWord(res.outcome)));
      if (res.note) bits.push(esc(res.note));
      if (res.reportedAt) { const d = mvStamp(res.reportedAt); if (d) bits.push('reported ' + esc(d)); }
      return `
    <div class="mv-action ${st.status === 'DONE' ? 'is-done' : ''} ${st.status === 'SKIPPED' ? 'is-skipped' : ''} ${st.status === 'BLOCKED' ? 'is-blocked' : ''}">
      <div class="mv-action-head" style="cursor:default">
        <span class="mv-action-num" aria-hidden="true">${mark}</span>
        <span class="mv-action-label">${stratEsc(s.title || s.label)}${bits.length ? `<span class="step-note">${bits.join(' · ')}</span>` : ''}</span>
        <span class="mv-action-mark">${stamp ? esc(word + ' · ' + stamp) : word}</span>
      </div>
    </div>`;
    }).join('');
    return `<div class="mv-canonical-rows">${rows}</div>`;
  }
  const rs = useRoadmapStore.getState();
  const suggested = steps.find(s => s.num === rs.currentStep) || steps.find(s => s.ready) || null;
  const suggestedNum = suggested ? suggested.num : 0;
  const openNum = (STORE.viewStep && steps.some(s => s.num === STORE.viewStep)) ? STORE.viewStep : suggestedNum;
  const advanceFn = IS_DEMO ? 'advanceTodayStep' : 'liveAdvanceStep';
  const details = v.stepDetails || {};
  /* Only promise "any order" among EXECUTION steps: the reporting step waits on all of them by design,
     and counting it here made the note contradict the rows above. */
  const hasDeps = steps.some(s => s.ready === false && s.waitingFor && s.waitingFor.length);
  /* The note names the three execution facts, because a recorded step is not always a completed
     one: done, skipped and blocked are separate records (NC-R6). */
  const orderNote = (hasDeps
    ? 'Some steps wait for the step before them.'
    : 'Any order works.') + ' Recording a step says what happened to the action: done, skipped or blocked. It does not confirm the outcome.';
  const rows = steps.map(s => {
    const open = s.num === openNum;
    const st = mvRowState(s);
    const done = st.status === 'DONE';
    const closed = st.closed;
    const waiting = !closed && s.ready === false;
    /* The mark states the execution fact, so a skipped step can never read as done. "Available" was
       a plan-level claim (nothing in the plan blocks it), never a canonical-Move readiness claim.
       No day label: only a real completion timestamp is a fact this screen may show. */
    const stamp = (done || st.status === 'SKIPPED') ? mvDoneStamp(s) : '';
    const mark = (done || st.status === 'SKIPPED') ? `${st.label}${stamp ? ' · ' + stamp : ''}`
      : (st.status === 'BLOCKED' ? st.label : (s.num === suggestedNum ? 'Suggested next' : (waiting ? 'Waiting' : st.label)));
    const note = waiting ? stepWaitNote(s, all) : '';
    const det = details[s.num] || {};
    return `
    <div class="mv-action ${open ? 'is-open' : ''} ${done ? 'is-done' : ''} ${st.status === 'SKIPPED' ? 'is-skipped' : ''} ${st.status === 'BLOCKED' ? 'is-blocked' : ''} ${waiting ? 'is-waiting' : ''} ${s.num === suggestedNum ? 'is-suggested' : ''}">
      <button type="button" class="mv-action-head" aria-expanded="${open}" aria-controls="mv-act-${s.num}" onclick="mvToggleStep(${s.num})">
        <span class="mv-action-num" aria-hidden="true">${done ? '✓' : s.num}</span>
        <span class="mv-action-label">${stratEsc(s.title || s.label)}${note ? `<span class="step-note">${note}</span>` : ''}</span>
        <span class="mv-action-mark">${mark}</span>
        <span class="mv-action-chev" aria-hidden="true">${ST_ACC_CHEV}</span>
      </button>
      ${open ? `
      <div class="mv-action-body" id="mv-act-${s.num}">
        <div class="section-meta-label">What to do</div>
        ${det.desc ? `<p class="mv-body">${det.desc}</p>` : `<p class="mv-body">${stratEsc(s.full || s.title || s.label)}</p>`}
        ${det.box ? `<div class="mv-action-box">${det.box}</div>` : ''}
        ${closed ? `<p class="mv-fine">${mvClosedNote(st, s)}</p>${mvClosedControls(s, st)}${mvActionOutcomeLink(s, st)}` : `<div class="mv-actions today-actions">${mvStepActions(s, rs, advanceFn)}</div>${mvActionOutcomeLink(s, st)}`}
      </div>` : ''}
    </div>`;
  }).join('');
  return `
    <section class="mv-card mv-actions-card today-card moves-list" aria-label="Action list">
      <div class="mv-list-head">
        <h2 class="mv-eyebrow">Action steps · ${steps.length}</h2>
        ${suggestedNum && openNum !== suggestedNum ? `<button type="button" class="moves-q-link" onclick="mvToggleStep(${suggestedNum})">Suggested step →</button>` : ''}
      </div>
      ${rows}
      <p class="mv-fine moves-q-note is-wrap">${orderNote}</p>
    </section>`;
}
/* Reporting belongs to the current work context (NC-04). It is the boundary where outcomes are
   recorded; it is not a fourth action and not a separate destination. */
function mvReportSection(v) {
  const ctx = (!IS_DEMO && typeof liveMovesReportContext === 'function') ? liveMovesReportContext() : null;
  const sum = (!IS_DEMO && typeof liveWorkContextSummary === 'function') ? liveWorkContextSummary() : null;
  const recorded = !!(sum && sum.hasAnyOutcome);
  if (recorded) {
    return [
      '<section class="mv-sec mv-report">',
      '<div class="section-meta-label">After the actions</div>',
      '<p class="mv-body">Your result is on record. You can still add or correct an outcome for another action.</p>',
      '<div class="mv-report-actions">',
      '<button type="button" class="btn-secondary btn-sm" onclick="' + (IS_DEMO ? 'renderScreen(\'05\')' : 'openMovesOutcomeReport()') + '">Add or update an outcome</button>',
      '<button type="button" class="moves-q-link" onclick="renderScreen(\'maps\')">See what changed on your map →</button>',
      '</div>',
      '</section>'
    ].join('');
  }
  if (ctx) {
    /* The context is closed, but closed is not the same fact as executed: the title counts what
       actually happened (done / skipped / blocked), and says "all done" only when every step is
       DONE (NC-R6). */
    const headline = mvExecutionHeadline(mvExecutionCounts());
    return [
      '<section class="mv-sec mv-report is-ready">',
      '<div class="section-meta-label">After the actions</div>',
      '<h3 class="mv-report-title">' + esc(headline || 'Your action steps are closed.') + '</h3>',
      '<p class="mv-body">Your work is recorded. What happened as a result?</p>',
      '<div class="mv-report-actions">',
      '<button type="button" class="btn-primary btn-sm" onclick="openMovesOutcomeReport()">Report what happened</button>',
      '<button type="button" class="btn-secondary btn-sm" onclick="dismissMovesReportPrompt()">I\'ll report later</button>',
      '</div>',
      '</section>'
    ].join('');
  }
  return [
    '<section class="mv-sec mv-report">',
    '<div class="section-meta-label">After the actions</div>',
    '<p class="mv-body">Report what actually happened. Completing an action is not proof it worked, and results can be reported once they exist.</p>',
    '<button type="button" class="moves-q-link" onclick="' + (IS_DEMO ? 'renderScreen(\'05\')' : 'openMovesOutcomeReport()') + '">' + esc(v.reportLabel || 'Report outcome →') + '</button>',
    '<button type="button" class="moves-q-link" onclick="renderScreen(\'05\')">Full check-in →</button>',
    '</section>'
  ].join('');
}
/* Goal status: income as of the last evaluation against the goal, from the record. A percentage only when
   both numbers speak the same unit; it is never the share of moves done. */
function mvGoalSection(v) {
  const snap = V11_ENGINE.snapshot();
  const g = snap.goal || {};
  const nowSet = !!g.now && g.now !== 'Not set yet';
  const goalSet = !!g.text && g.text !== 'Not set yet';
  const pct = (() => {
    const a = stateMoney(g.now), b = stateMoney(g.text);
    if (!a || !b || b.n <= 0 || (a.unit !== b.unit && a.n !== 0)) return null;
    return Math.min(100, Math.round((a.n / b.n) * 100));
  })();
  const left = getTimeline().daysLeft;
  /* The bar is a comparison of two recorded values as of the last check-in — never a claim that the
     goal has succeeded. At 100% the honest line is "at goal as of the last measurement", not a
     celebratory full bar, and missing/compatible-unit gaps show no percentage at all. */
  const measured = 'as of your last check-in';
  return `
    <section class="mv-ctx-sec mv-goal" aria-labelledby="mv-progress-label">
      <h2 class="mv-eyebrow" id="mv-progress-label">Goal context</h2>
      ${goalSet && nowSet ? `
        <p class="mv-goal-line"><b>${stratEsc(g.now)}</b> of ${stratEsc(g.text)}${pct === null ? '' : ` <span class="mv-goal-pct">· ${pct}%</span>`}</p>
        ${pct !== null && pct < 100 ? `<div class="mv-bar" role="img" aria-label="Income is ${pct}% of the goal, ${measured}"><span style="width:${pct}%"></span></div>` : ''}
        ${pct !== null && pct >= 100 ? `<p class="mv-goal-line"><b>At goal</b> <span class="mv-goal-pct">· ${measured}</span></p>` : ''}
        <p class="mv-fine">Recorded income compared with your goal${g.horizon ? ` by ${stratEsc(g.horizon)}` : ''}${left ? `, ${stateN(left, 'day', 'days')} left` : ''} — ${measured}. Moves done are counted separately.</p>`
      : '<p class="mv-body">No goal on record yet. A talk can set one.</p>'}
    </section>`;
}
/* About this path: the why, the requirements and the experiment-level observation belong to the PATH,
   not to whichever action happens to be expanded — Phase 3 makes that scope explicit. */
function mvAboutSection(v) {
  const snap = V11_ENGINE.snapshot();
  const st = snap.state || {};
  const fp = (snap.nextmove && snap.nextmove.path_id) ? (snap.paths || []).find(p => p.id === snap.nextmove.path_id) : null;
  const reqs = fp ? (fp.requirements || []).filter(r => r.applicable !== false) : [];
  return `
    <section class="mv-ctx-sec mv-about" aria-labelledby="mv-about-label">
      <h2 class="mv-eyebrow" id="mv-about-label">About this path</h2>
      ${v.whyText ? `<p class="mv-body">${stratEsc(v.whyText)}</p>` : (st.next_best_why ? `<p class="mv-body">${stratEsc(st.next_best_why)}</p>` : '<p class="mv-body">No reason is on record for this work yet.</p>')}
      ${st.know_right_when ? `<div><div class="section-meta-label mb-2">What this path is trying to learn</div><p class="mv-body">${stratEsc(st.know_right_when)}</p><p class="mv-fine">An observation for the whole path, not a completion rule for each action.</p></div>` : ''}
      ${mvNeedsList(reqs)}
      <button type="button" class="moves-q-link" onclick="goDestination('maps')">See this path on your map →</button>
    </section>`;
}
function mvDetailSection(v) {
  const snap = V11_ENGINE.snapshot();
  const st = snap.state || {};
  const ev = snap.evidence || [];
  const hold = st.what_not_to_do || [];
  const fp = (snap.nextmove && snap.nextmove.path_id) ? (snap.paths || []).find(p => p.id === snap.nextmove.path_id) : null;
  const reqs = fp ? (fp.requirements || []).filter(r => r.applicable !== false) : [];
  const bySrc = {};
  ev.forEach(e => { const src = e.source || 'On record'; (bySrc[src] = bySrc[src] || []).push(e); });
  const srcBlocks = Object.keys(bySrc).map(name => `
        <div class="dr-source">
          <div class="dr-source-head">${mvIco('file')}<b>${stratEsc(name)}</b><span class="st-count">${bySrc[name].length}</span></div>
          ${bySrc[name].map(e => `<blockquote class="mv-quote">“${stratEsc(e.quote)}”${e.disputed ? ' <span class="v11-disputed-badge">DISPUTED</span>' : ''}</blockquote>`).join('')}
        </div>`).join('');
  return `
    <section class="mv-ctx-sec" aria-labelledby="mv-detail-label">
      <h2 class="mv-eyebrow" id="mv-detail-label">Evidence and details</h2>
      <div class="st-acc-list mv-acc-list">
        ${mvAcc('hold', 'ban', 'What not to do yet', hold.length, hold.length
          ? `<p class="dr-note">Not never. These can wait until the record gives a reason.</p><ul class="dr-tiles">${hold.map(h => `<li class="dr-tile"><span class="dr-mark" aria-hidden="true">${mvIco('ban')}</span><span class="dr-text">${stratEsc(h)}</span><span class="dr-chip">Can wait</span></li>`).join('')}</ul>`
          : '<p>Nothing is marked as waiting yet.</p>', STORE.movesSideTopic === 'hold')}
        ${mvAcc('evidence', 'file', 'Evidence and sources', ev.length, ev.length ? srcBlocks : '<p>Nothing is on record yet.</p>', STORE.movesSideTopic === 'evidence')}
      </div>
    </section>`;
}
/* The inspector: folds away from the panel's own top-right control (the same control State uses). */
function mvMovesPanel(v) {
  return `
  <aside class="mv-aside ws-side has-panel-hide" id="mv-side" aria-label="Progress and detail">
    ${wsPanelHideBtn('mv-side-toggle', 'mv-side', 'setMovesSide', 'progress and detail')}
    <div class="mv-card mv-side mv-context">
      ${mvAboutSection(v)}
      ${mvGoalSection(v)}
      ${mvDetailSection(v)}
    </div>
  </aside>`;
}
/* Moves is a split-pane destination: a stable work context and its action list in the main pane,
   progress and detail docked right, exactly like State. Selecting an action expands it inline and never
   changes the parent heading, the suggested step, or the engine's decision. */
function renderMovesLayout(v) {
  const steps = v.steps || [];
  const actionN = steps.filter(s => !s.report).length;
  const sideClosed = !!STORE.movesSideClosed;
  /* The count stays the CURRENT plan's own steps. Scope and execution progress are separate lines:
     the scope never borrows an earlier plan's completion, and execution is never implied to be
     outcome (NC-R6). */
  const scopeNote = mvPlanScopeNote(actionN);
  const progressNote = mvExecutionProgressNote(mvExecutionCounts());
  return `
  <div class="dest-page mv-page ws-split${sideClosed ? ' is-collapsed' : ''}">
    <div class="ws-main">
      <div class="ws-inner">
        <h1 class="sr-only">Moves</h1>
        <div class="mv-main">
          ${sideClosed ? `<div class="mv-head-actions">${wsPanelShowBtn('mv-side-toggle', 'mv-side', 'setMovesSide', 'progress and detail')}</div>` : ''}
          ${v.banner || ''}
          <section class="mv-parent mv-featured">
            <div class="section-meta-label">Actions for</div>
            <h2 class="mv-parent-title">${v.pathTitle || 'Your current plan'}</h2>
            <p class="mv-fine">${actionN ? `${actionN} action step${actionN === 1 ? '' : 's'}` : 'No actions are on record for this plan yet.'}</p>
            ${scopeNote ? `<p class="mv-fine">${esc(scopeNote)}</p>` : ''}
            ${progressNote ? `<p class="mv-fine">${esc(progressNote)}</p>` : ''}
          </section>
          ${mvActionList(v)}
          ${mvReportSection(v)}
          ${renderMovesQueues(v)}
        </div>
      </div>
    </div>
    ${sideClosed ? '' : mvMovesPanel(v)}
  </div>`;
}
