/* Contextual outcome reporting in Moves (NC-04, Phase 7). Not a destination: a dialog reached from the
   current work context. This dialog is an OBSERVATION surface: it NEVER sends an execution status (the
   Moves checklist and its per-step control own execution), and "too early to tell / not measured"
   submits NOTHING, so unknown is never coerced to a value and a note is never claimed as saved. A real
   outcome travels with one operation id that is kept for a retry of the SAME submission and cleared only
   after an accepted response. Every wait awaits the server acknowledgement before any success claim.

   Phase 7: execution and result are separate. The CANONICAL branch is about the MOVE as a whole. The
   report is bound to the canonical move_id (POST /session/{sid}/moves/{move_id}/outcome), no action
   <select> is offered, and reporting the result never changes an execution status: completing the
   required actions already advanced the Move server-side. The plan-level selector and the per-action
   endpoints remain ONLY as the LEGACY fallback for sessions without a canonical Move. */
const MOVES_OUTCOME_WORDS = {
  moved: 'Something moved',
  not_moved: 'Nothing changed yet',
  confounded: 'Something else may have caused it',
  regret: 'It went backwards',
  unknown: 'Too early to tell / not measured'
};
/* The LEGACY action options: a plan action index. A canonical result is named by its move_id and must
   never be matched by index or title, so this serves only the fallback branch. */
function movesReportActions() {
  return livePlanActionItems().filter(function (a) { return !a.hold; })
    .map(function (a) { return { idx: a.idx, label: a.text }; });
}
/* The accepted checkpoint the dialog's selection belongs to. liveCheckpointId lives in
   experience-state.js and is called defensively: without it the scope falls back to the session only. */
function movesReportCheckpointId() {
  try { return (typeof liveCheckpointId === 'function') ? String(liveCheckpointId() || '') : ''; }
  catch (e) { return ''; }
}
/* A bare action index does not survive a new accepted plan: after a reassessment the same index can
   point at a DIFFERENT action. When the scope (map + accepted checkpoint) moved since the dialog was
   last used, the stored selection, note, choice and pending operation id are dropped, so the next
   report cannot be filed against another action than the one the person picked. Returns true when the
   scope moved. An empty checkpoint id is the defensive fallback ("not known yet"), not proof that no
   checkpoint existed, so only a changed NON-EMPTY id (or a different map) is a proven move. */
function movesReportSyncCheckpoint() {
  const sid = LIVE.sid || '';
  const cid = movesReportCheckpointId();
  const sameSession = STORE.movesReportSessionId === sid;
  const moved = !sameSession || (!!STORE.movesReportCheckpointId && STORE.movesReportCheckpointId !== cid);
  if (sameSession && STORE.movesReportCheckpointId === cid) return false;
  STORE.movesReportSessionId = sid;
  STORE.movesReportCheckpointId = cid;
  if (!moved) return false;
  STORE.movesReportIndex = null;
  STORE.movesReportChoice = '';
  STORE.movesReportNote = '';
  STORE.movesReportOp = '';
  STORE.movesReportOpSig = '';
  return true;
}
/* The LEGACY selector's default, read from the SAME plan record the checklist uses: the person's own
   pick while it is still a valid action; otherwise an action that carries no recorded outcome yet (the
   work context's reportIndex first, so the default stays consistent with the checklist), and only the
   last action when every action was already reported on. The canonical branch needs no index at all;
   this is guarded so an empty action list can never throw. */
function movesReportDefaultIndex(acts) {
  const list = Array.isArray(acts) ? acts : [];
  if (!list.length) return -1;
  const has = function (i) { return list.some(function (a) { return a.idx === i; }); };
  const unrecorded = function (i) {
    const st = (typeof livePlanActionState === 'function') ? livePlanActionState(i) : null;
    return !!st && !st.hasOutcome;
  };
  /* Move-centric: the business result belongs to the work as a whole, so that is the default. A single
     action is still selectable for a detail worth recording on it. */
  if (STORE.movesReportIndex === -1 || STORE.movesReportIndex == null) return -1;
  if (STORE.movesReportIndex != null && has(STORE.movesReportIndex)) return STORE.movesReportIndex;
  const sum = (typeof liveWorkContextSummary === 'function') ? liveWorkContextSummary() : null;
  const pref = sum ? sum.reportIndex : null;
  if (pref != null && has(pref) && unrecorded(pref)) return pref;
  const free = list.filter(function (a) { return unrecorded(a.idx); })[0];
  if (free) return free.idx;
  if (pref != null && has(pref)) return pref;
  return list[list.length - 1].idx;
}
/* The selected action's execution status exactly as recorded (never invented). A quiet line states
   that reporting an observation leaves it as it is; only an open, blocked or skipped action needs it.
   LEGACY selector only. */
function movesReportStatusNote() {
  const st = (typeof livePlanActionState === 'function') ? livePlanActionState(STORE.movesReportIndex) : null;
  if (!st) return '';
  const status = String(st.status || '');
  if (['SKIPPED', 'BLOCKED', 'TODO'].indexOf(status.toUpperCase()) < 0) return '';
  return 'This action is currently ' + esc(status) + '. Recording what you observed leaves its execution status unchanged - it does not mark the action done.';
}
function movesReportRenderStatusNote() {
  const host = document.getElementById('mr-status-note');
  if (!host) return;
  const text = movesReportStatusNote();
  host.innerHTML = text;
  host.style.display = text ? '' : 'none';
}
/* A neutral in-dialog line: an honest statement of what was (not) recorded. It never carries a
   failure; the red error line stays reserved for a real failure. */
function showMovesReportHint(text) {
  const err = document.getElementById('mr-err');
  if (err) err.style.display = 'none';
  const host = document.getElementById('mr-hint');
  if (!host) { if (text) showToast(text, '', '', ''); return; }
  host.textContent = text || '';
  host.style.display = text ? 'block' : 'none';
}
/* ONE option set for both branches: the four outcomes plus the explicit "not known yet" note-only
   path. "Too early to tell / not measured" is never sent as an outcome value. */
function movesReportOutcomeOptions(choice) {
  const opt = function (k) {
    return '<div class="radio-card ' + (choice === k ? 'selected' : '') + '" onclick="setMovesReportChoice(\'' + k + '\')" role="radio" aria-checked="' + (choice === k) + '" tabindex="0" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();setMovesReportChoice(\'' + k + '\')}">'
      + '<div class="radio-dot"></div><div><div class="mr-opt-word">' + MOVES_OUTCOME_WORDS[k] + '</div></div></div>';
  };
  return ['moved', 'not_moved', 'confounded', 'regret', 'unknown'].map(opt).join('');
}
/* ONE mount for both branches: same modal primitive, same focus/overlay discipline. */
function movesReportMount(html) {
  const card = document.getElementById('modal-content');
  card.innerHTML = html;
  card.setAttribute('aria-labelledby', 'mr-title');
  card.removeAttribute('aria-label');
  document.getElementById('stop-modal').classList.add('open');
  overlayOpened('stop-modal');
}
/* The dismissal key for the dialog that just closed: the canonical Move when one was bound (and the
   read model still knows it), otherwise the legacy work-context key. */
function movesReportDismissalKey(moveId) {
  const id = String(moveId || '');
  if (id && typeof liveMoveReportContextKey === 'function'
    && typeof liveMoveById === 'function' && liveMoveById(id)) return liveMoveReportContextKey(id);
  return liveReportContextKey();
}
/* Phase 7: a result is already on record for this Move. The dialog states exactly what is stored, from
   the Move's own record (outcome word + note) and that saving again corrects it while the earlier
   report is kept as history. Nothing is pre-filled and no new write is claimed. */
function movesReportRecordedHtml(mv, mc) {
  const rec = (mv && mv.outcome_report) || {};
  const has = !!(rec.outcome || rec.note) || !!(mc && mc.hasOutcome);
  if (!has) return '';
  const outcome = String(rec.outcome || (mc && mc.outcome) || '');
  const note = String(rec.note || '');
  const lines = [];
  if (outcome) lines.push('Outcome on record: ' + esc(MOVES_OUTCOME_WORDS[outcome] || outcome) + '.');
  if (note) lines.push('Note on record: &ldquo;' + esc(brief(note, 160)) + '&rdquo;.');
  lines.push('Saving again corrects it; the earlier report is kept as history.');
  return '<div class="mr-sec mr-recorded"><span class="section-meta-label">Already on record</span>'
    + '<p class="rv-sheet-lead mr-recorded-line" id="mr-recorded" role="status">' + lines.join(' ') + '</p></div>';
}
/* Phase 7: the canonical result prompt. The target is the Move itself (liveMoveOutcomeTarget), never
   one of its actions, so the dialog has no action selector: its submission is bound to move_id. When
   the session has no canonical Move, the legacy plan flow answers instead (same modal). */
function openMovesOutcomeReport() {
  if (IS_DEMO || !LIVE.artifact) return;
  const mv = (typeof liveMoveOutcomeTarget === 'function') ? liveMoveOutcomeTarget() : null;
  if (mv && mv.move_id) { openMovesOutcomeReportForMove(mv.move_id); return; }
  movesReportOpenLegacy();
}
/* The CANONICAL modal for ONE Move (Maps/Moves links call this directly). The outcome choices, the note
   field, the note-only path and the operation id are the same as the legacy dialog; only the target
   differs - it is the Move, and STORE.movesReportMoveId is the only thing submit reads. */
function openMovesOutcomeReportForMove(moveId) {
  if (IS_DEMO || !LIVE.artifact) return;
  const id = String(moveId || '');
  const mv = (id && typeof liveMoveById === 'function') ? liveMoveById(id) : null;
  if (!mv || !String(mv.move_id || '')) return;
  /* The legacy scope hygiene still runs (session / accepted checkpoint) but its boolean is ignored: a
     checkpoint never reassigns a move_id, so the Move - not a plan index - is this dialog's identity. */
  movesReportSyncCheckpoint();
  /* A different Move is a different report: a choice or note written for another target is never
     carried over, exactly as a changed scope drops the legacy selection. */
  if (STORE.movesReportMoveId && STORE.movesReportMoveId !== id) {
    STORE.movesReportChoice = '';
    STORE.movesReportNote = '';
    STORE.movesReportOp = '';
    STORE.movesReportOpSig = '';
  }
  STORE.movesReportMoveId = id;
  const mc = (typeof liveMoveContextSummary === 'function') ? liveMoveContextSummary(mv) : null;
  const choice = STORE.movesReportChoice || '';
  const opts = movesReportOutcomeOptions(choice);
  /* The Move's declared path binding names the report's path; without one the current work context is
     used, exactly as before (never inferred from a title or position). */
  const pathKey = String(mv.linked_path_id || '') || liveActivePathKey();
  STORE.movesReportPath = pathKey;
  const path = livePathModels().find(function (p) { return p.key === pathKey; });
  const objective = brief(String(mv.objective || ''), 140);
  const recorded = movesReportRecordedHtml(mv, mc);
  const hint = STORE.movesReportHint || '';
  STORE.movesReportHint = '';
  const html = [
    '<div class="rv-modal mr-modal">',
    '<div class="rv-sheet-head"><div>',
    '<div class="section-meta-label">Outcome · ' + (path ? stratEsc(path.name) : 'your current work') + '</div>',
    '<h2 class="serif-heading" id="mr-title">What happened as a result?</h2>',
    '<p class="rv-sheet-lead">You have finished the required actions of this move. Recording a result reports what you observed. It does not change any execution status; whether your map changes is decided by the evidence.</p>',
    '</div><button type="button" class="rv-x" onclick="closeModal()" aria-label="Close">✕</button></div>',
    objective ? '<div class="mr-sec mr-move"><span class="section-meta-label">The move this result is about</span>'
      + '<p class="rv-sheet-lead mr-move-objective" id="mr-move-objective">' + stratEsc(objective) + '</p></div>' : '',
    recorded,
    '<div class="mr-sec"><span class="section-meta-label">Outcome (optional)</span>',
    '<div class="mr-opts" role="radiogroup" aria-label="Outcome">' + opts + '</div></div>',
    '<div class="mr-sec"><label class="section-meta-label" for="mr-note">What did you observe? (optional)</label>',
    '<textarea id="mr-note" class="mr-note" rows="3" placeholder="For example: two replies, no one committed yet." oninput="setMovesReportNote(this.value)">' + esc(STORE.movesReportNote || '') + '</textarea></div>',
    '<p class="rv-sheet-lead" id="mr-hint" role="status" style="display:none"></p>',
    '<div id="mr-err" role="alert" class="mr-err" style="display:none"></div>',
    '<div class="rv-foot"><button type="button" class="btn-secondary btn-sm" onclick="dismissMovesReportPrompt()">I\'ll report later</button>',
    '<button type="button" class="btn-primary btn-sm" id="mr-submit" onclick="submitMovesOutcomeReport()">Save outcome</button></div>',
    '</div>'
  ].join('');
  movesReportMount(html);
  if (hint) showMovesReportHint(hint);
}
/* The LEGACY plan flow (no canonical Move): the action selector, the per-action status line and the
   plan-level / per-action endpoints stay exactly as history expects them. */
function movesReportOpenLegacy() {
  STORE.movesReportMoveId = '';
  movesReportSyncCheckpoint();
  const acts = movesReportActions();
  if (!acts.length) { renderScreen('05'); return; }
  const idx = movesReportDefaultIndex(acts);
  STORE.movesReportIndex = idx;
  const choice = STORE.movesReportChoice || '';
  const opts = movesReportOutcomeOptions(choice);
  const pathKey = liveActivePathKey();
  /* EC-14: bind the report to the work context it was opened in, even if the path selection changes. */
  STORE.movesReportPath = pathKey;
  const path = livePathModels().find(function (p) { return p.key === pathKey; });
  const options = '<option value="-1"' + (idx === -1 ? ' selected' : '') + '>The whole set of actions (what happened overall)</option>' + acts.map(function (a) {
    return '<option value="' + a.idx + '"' + (a.idx === idx ? ' selected' : '') + '>' + stratEsc(brief(a.label, 90)) + '</option>';
  }).join('');
  const statusNote = movesReportStatusNote();
  const hint = STORE.movesReportHint || '';
  STORE.movesReportHint = '';
  const html = [
    '<div class="rv-modal mr-modal">',
    '<div class="rv-sheet-head"><div>',
    '<div class="section-meta-label">Outcome · ' + (path ? stratEsc(path.name) : 'your current work') + '</div>',
    '<h2 class="serif-heading" id="mr-title">What happened as a result?</h2>',
    '<p class="rv-sheet-lead">Recording an outcome reports what you observed. It does not mark the action done and leaves its execution status unchanged; whether your map changes is decided by the evidence.</p>',
    '</div><button type="button" class="rv-x" onclick="closeModal()" aria-label="Close">✕</button></div>',
    '<div class="mr-sec"><label class="section-meta-label" for="mr-action">What is this result about?</label>',
    '<select id="mr-action" class="mr-select" onchange="setMovesReportActionIndex(this.value)">' + options + '</select>',
    '<p class="rv-sheet-lead" id="mr-status-note" role="status"' + (statusNote ? '' : ' style="display:none"') + '>' + statusNote + '</p></div>',
    '<div class="mr-sec"><span class="section-meta-label">Outcome (optional)</span>',
    '<div class="mr-opts" role="radiogroup" aria-label="Outcome">' + opts + '</div></div>',
    '<div class="mr-sec"><label class="section-meta-label" for="mr-note">What did you observe? (optional)</label>',
    '<textarea id="mr-note" class="mr-note" rows="3" placeholder="For example: two replies, no one committed yet." oninput="setMovesReportNote(this.value)">' + esc(STORE.movesReportNote || '') + '</textarea></div>',
    '<p class="rv-sheet-lead" id="mr-hint" role="status" style="display:none"></p>',
    '<div id="mr-err" role="alert" class="mr-err" style="display:none"></div>',
    '<div class="rv-foot"><button type="button" class="btn-secondary btn-sm" onclick="dismissMovesReportPrompt()">I\'ll report later</button>',
    '<button type="button" class="btn-primary btn-sm" id="mr-submit" onclick="submitMovesOutcomeReport()">Save outcome</button></div>',
    '</div>'
  ].join('');
  movesReportMount(html);
  if (hint) showMovesReportHint(hint);
}
/* Re-render the CURRENT target: the canonical Move while one is bound, else the legacy plan flow. */
function movesReportReopen() {
  const id = String(STORE.movesReportMoveId || '');
  if (id && typeof liveMoveById === 'function' && liveMoveById(id)) {
    openMovesOutcomeReportForMove(id);
    return;
  }
  openMovesOutcomeReport();
}
/* A different outcome is a different submission: the pending operation id must never be reused for it.
   The choice is not an action selection, so the same target stays open - canonical or legacy. */
function setMovesReportChoice(k) {
  STORE.movesReportChoice = k;
  STORE.movesReportOp = ''; STORE.movesReportOpSig = '';
  movesReportReopen();
}
function setMovesReportActionIndex(v) {
  const idx = parseInt(v, 10);
  if (idx === STORE.movesReportIndex) return;
  STORE.movesReportIndex = idx;
  STORE.movesReportOp = ''; STORE.movesReportOpSig = '';
  movesReportRenderStatusNote();
  showMovesReportHint('');
}
function setMovesReportNote(v) {
  STORE.movesReportNote = v;
  STORE.movesReportOp = ''; STORE.movesReportOpSig = '';
  showMovesReportHint('');
}
/* Deferring is scoped to the context the dialog was about: the canonical Move when one was bound, so
   "I'll report later" actually suppresses that Move's prompt (it is keyed by move state, not by plan). */
function dismissMovesReportPrompt() {
  STORE.movesReportDismissed = movesReportDismissalKey(STORE.movesReportMoveId);
  closeModal();
  if (STORE.currentScreen === 'moves') renderScreenKeepingUi('moves');
}
/* True only when the server's own signal says the report was already accepted (a POST can fail after
   the commit). API.raw throws only for a non-2xx response, so a status number alone never means
   acceptance: it is read from the machine code, the parsed detail flags, or the server's message. */
function movesReportWasAccepted(e) {
  if (!e) return false;
  const detail = e.detail || null;
  if (detail && (detail.accepted === true || detail.replayed === true)) return true;
  const code = String(e.code || '').toUpperCase();
  if (/ALREADY[_-]?(ACCEPTED|RECORDED|SAVED|REPORTED)/.test(code)) return true;
  if (/IDEMPOTENT/.test(code)) return true;
  if (/REPLAY/.test(code) && !/(CONFLICT|MISMATCH|DIFFERENT)/.test(code)) return true;
  const msg = String(e.message || '');
  if (/already (been )?(accepted|recorded|saved|reported|applied)|(accepted|recorded|saved|reported) already/i.test(msg)) return true;
  /* A replay message is the server saying the accepted report came back; a conflict over a different
     payload is a real failure and stays one. */
  return /replayed/i.test(msg) && !/(conflict|different payload)/i.test(msg);
}
/* One accepted report: clear the form and the operation key, close the dialog, and hand the change
   summary to the ONE Maps destination. A failed follow-up READ keeps the record and says so.
   Phase 7: a canonical result is reported against the MOVE, so the continuation and the Move travel to
   Maps as a move_outcome summary and the dismissal is scoped to that Move's context key. */
function movesReportAccepted(refreshFailed, r) {
  const moveId = String(STORE.movesReportMoveId || '');
  STORE.movesReportOp = '';
  STORE.movesReportOpSig = '';
  STORE.movesReportChoice = '';
  STORE.movesReportNote = '';
  STORE.movesReportIndex = null;
  STORE.movesReportPath = null;
  STORE.movesReportMoveId = '';
  STORE.movesReportDismissed = movesReportDismissalKey(moveId);
  closeModal();
  /* The record stands. A canonical result carries the server's continuation (what comes next, from the
     canonical authorities) for the Move it was reported on; a legacy whole-plan report keeps its own
     continuation, and a per-action report keeps the change_set summary. */
  if (moveId) {
    STORE.pendingChangeSummary = {
      source: 'move_outcome',
      continuation: (r && r.continuation) || null,
      move: (r && r.move) || null
    };
  } else {
    STORE.pendingChangeSummary = (r && r.continuation) ? { source: 'plan_outcome', continuation: r.continuation, outcome: r.plan_report || null } : { source: 'outcome' };
  }
  renderScreen('maps');
  if (refreshFailed) {
    /* Saved, view behind: the Maps banner carries the read-only retry (liveRetryRefresh through
       mapsRetryRefresh). Never a claim that the save failed and never an automatic resubmit. */
    showToast('Your report is saved. The latest view could not be refreshed.', '', '', 'error');
  }
  /* Phase 6.2: a quiet note for a correction (the earlier report is kept as history) or for effects that settle
     later. Never shown over a failed refresh, which already has its own message. */
  const note = refreshFailed ? '' : liveReportNoteText(r);
  if (note) showToast(note, '', '', '');
}
async function submitMovesOutcomeReport() {
  const err = document.getElementById('mr-err');
  const btn = document.getElementById('mr-submit');
  const choice = STORE.movesReportChoice || 'unknown';
  const note = STORE.movesReportNote || '';
  /* Phase 7: a canonical dialog reports against the MOVE as a whole; the legacy dialog keeps the
     plan-level (-1) and per-action (index) branches. */
  const moveId = String(STORE.movesReportMoveId || '');
  const canonical = !!moveId;
  /* The accepted plan can move while the LEGACY dialog is open: a PROVEN move reopens the dialog fresh
     instead of posting against an action the person did not pick. A canonical report is bound to a
     move_id, which a checkpoint never reassigns, so it does not take this branch. */
  if (!canonical && movesReportSyncCheckpoint()) {
    STORE.movesReportHint = 'Your plan was updated, so nothing was sent. Pick the action again and save.';
    openMovesOutcomeReport();
    return;
  }
  let idx = null;
  let wholePlan = false;
  if (!canonical) {
    idx = STORE.movesReportIndex;
    const acts = movesReportActions();
    const has = function (i) { return acts.some(function (a) { return a.idx === i; }); };
    wholePlan = idx === -1;
    if (idx == null || (!wholePlan && !has(idx))) {
      if (err) { err.style.display = 'block'; err.textContent = 'Pick an action first.'; }
      return;
    }
  }
  /* "Too early to tell / not measured" is not an outcome and is never sent as one. A note on its own IS a
     legitimate report (what the person saw, no outcome invented): it is saved as a note. With neither an
     outcome nor a note there is nothing to record, and the dialog says so instead of claiming a save. */
  const noteOnly = choice === 'unknown';
  if (noteOnly && !note.trim()) {
    showMovesReportHint('Nothing to record yet. Choose an outcome, or write what you saw and save it as a note.');
    return;
  }
  /* D-10 / NC-R6: one operation id per submission. A retry with the SAME target, choice and note resends
     the same id (the server replays it instead of appending a second outcome row); any change to the form
     is a new submission and mints a new id. The id is cleared only after acceptance. */
  const sig = (canonical ? 'mv:' + moveId : String(idx)) + '\u0001' + choice + '\u0001' + note;
  if (!STORE.movesReportOp || STORE.movesReportOpSig !== sig) {
    STORE.movesReportOp = newOperationId(canonical ? 'mo' : 'ar');
    STORE.movesReportOpSig = sig;
  }
  const body = noteOnly
    ? { note: note, operation_id: STORE.movesReportOp }
    : { note: note, outcome: choice, path: STORE.movesReportPath || liveActivePathKey(), operation_id: STORE.movesReportOp };
  const send = canonical
    ? function () { return liveReportMoveOutcome(moveId, body); }
    : (wholePlan ? function () { return liveReportPlan(body); } : function () { return liveReportAction(idx, body); });
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; btn.textContent = 'Saving…'; }
  if (err) err.style.display = 'none';
  try {
    const r = await send();
    /* Phase 6.2: unchanged = the identical report is already on record and nothing was written. The dialog says
       so calmly: no new-recording claim, no move to Maps and no progress. The accepted id is cleared. */
    if (r && r.unchanged === true) {
      STORE.movesReportOp = ''; STORE.movesReportOpSig = '';
      if (btn) { btn.disabled = false; btn.style.opacity = ''; btn.textContent = 'Save outcome'; }
      showMovesReportHint('Nothing changed - this report was already recorded.');
      return;
    }
    /* NC-R6: the canonical / legacy report resolves with the accepted record even when the version-checked
       refresh failed. The record stands; the view is behind and is never resubmitted. */
    movesReportAccepted(!!(LIVE.lastRefreshFailed || LIVE.experienceError), r);
  } catch (e) {
    const code = String((e && e.code) || '').toUpperCase();
    /* Phase 7: a refused canonical result (the Move's own rules, or a result already on record) is the
       server's message shown INSIDE this dialog, which stays open on the Move it is about. The code is
       never read as an acceptance just because it contains ALREADY. */
    if (canonical && (code === 'MOVE_OUTCOME_REJECTED' || code.indexOf('MOVE_ALREADY_') === 0)) {
      if (btn) { btn.disabled = false; btn.style.opacity = ''; btn.textContent = 'Save outcome'; }
      if (err) { err.style.display = 'block'; err.textContent = liveReportErrorText(e); }
      return;
    }
    /* Phase 6.2: an action of an earlier, replaced plan changed nothing and is never retried. The refresh already
       ran in liveReportAction, so the dialog reopens on the CURRENT plan with the server's own message. Checked
       before the accepted signal on purpose. */
    if (e && e.code === 'HISTORICAL_ACTION_READ_ONLY') {
      STORE.movesReportIndex = null; STORE.movesReportOp = ''; STORE.movesReportOpSig = '';
      STORE.movesReportHint = liveReportErrorText(e);
      openMovesOutcomeReport();
      return;
    }
    /* The POST can fail after the server accepted the report. Only the server's own signal may say so;
       the accepted record is then read through the shared version-checked READ boundary, never
       resubmitted. */
    if (movesReportWasAccepted(e)) {
      let ok = false;
      try { ok = await liveRefreshAfterMutation({ render: false }); } catch (e2) { ok = false; }
      movesReportAccepted(!ok);
      return;
    }
    if (btn) { btn.disabled = false; btn.style.opacity = ''; btn.textContent = 'Save outcome'; }
    if (err) { err.style.display = 'block'; err.textContent = 'Could not save that: ' + liveReportErrorText(e); }
  }
}
