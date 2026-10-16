/* NextMove view-model (live only). The server's Question Planner decides the next conversation move from state
 * (internal-docs §25); this file only turns that decision into words and markup. Nothing here
 * decides anything: kind, focus, text and reason all come from the engine, and the raw reason trail stays
 * inspectable under "Engine trail".
 *
 * Move kinds (engine): QUESTION, EVIDENCE_REQUEST, ACTION, HOLD. Plain words for readers: Question, Needs
 * evidence, Ready, On hold. The raw enum is never shown. */
const MOVE_LABEL = { QUESTION: 'Question', EVIDENCE_REQUEST: 'Needs evidence', ACTION: 'Ready', HOLD: 'On hold' };

function moveLabel(kind) { return MOVE_LABEL[kind] || 'Question'; }

/* Engine reason tokens -> one plain sentence each. A token with no sentence is not shown in the plain list
 * (it is still in the engine trail), so nothing is invented and nothing is hidden. */
const WHY_TEXT = [
  [/^goal=GOAL_ABSENT$/, () => 'The goal you gave us does not say what you want to reach.'],
  [/^goal=/, () => 'We do not know your goal yet.'],
  [/^conflict=true$/, () => 'Parts of what you told us point in different directions.'],
  [/^applicability=APPLIES$/, () => 'It applies to your situation.'],
  [/^applicability=UNKNOWN$/, () => 'We cannot yet tell whether this applies to you.'],
  [/^satisfaction=UNKNOWN$/, () => 'We cannot tell yet where you stand on it.'],
  [/^navigable_contexts=(\d+)$/, m => `It matters for ${m[1]} of your possible ${m[1] === '1' ? 'path' : 'paths'}.`],
  [/^dependency_ready=true$/, () => 'Nothing else has to come first.'],
  [/^strength_rank=0$/, () => 'It could rule a path in or out.'],
  [/^resolvable_by=ASK$/, () => 'You can tell us this directly.'],
  [/^asked_before=([1-9]\d*)$/, m => `We asked about this before (${m[1]} time${m[1] === '1' ? '' : 's'}).`],
  [/^evidence_on_file=true$/, () => 'What you told us so far did not settle it.'],
  [/^blocks_next_decision=true$/, () => 'Without it we cannot choose the next step.'],
  [/^navigable_paths=0$/, () => 'No way forward is clear yet.'],
  [/^blocking_uncertainty=none$/, () => 'Nothing we can still ask would change the next step.'],
  [/^enough_to_map=true$/, () => 'We know enough to map your options.'],
  [/^no_safe_next_question=true$/, () => 'There is no question we can safely ask next.'],
  [/^applicable_route_actionable=true$/, () => 'One of your options is clear enough to start on.']
];

function whyLines(reason) {
  const out = [];
  for (const raw of (reason && reason.why) || []) {
    for (const [rx, fn] of WHY_TEXT) {
      const m = rx.exec(raw);
      if (m) { const s = fn(m); if (s) out.push(s); break; }
    }
  }
  return out;
}

/* One plain line saying why THIS is the thing being asked (by the engine's own stage, then by its first reasons). */
const STAGE_SUB = {
  GOAL: () => 'We need to know what you want to reach before we can map anything.',
  CONTRADICTION: () => 'Parts of what you told us point in different directions.',
  APPLICABILITY: () => 'We cannot yet tell whether this option applies to you.',
  EMERGENCE: () => 'No way forward is clear yet. This is the missing fact that would let one appear.'
};
function focusSub(mv, lines) {
  const stage = (mv.reason || {}).stage;
  if (STAGE_SUB[stage]) return STAGE_SUB[stage]();
  if (mv.intent === 'RESOLVE_APPLICABILITY') return STAGE_SUB.APPLICABILITY();
  return lines.slice(0, 2).join(' ') || 'This is the most useful thing we can still learn right now.';
}

/* How many other needs are waiting behind this one (deferred, or blocked by something that comes first). */
function waitingCount(reason) {
  return ((reason && reason.considered) || []).filter(c => c.verdict === 'DEFERRED' || /^DEPENDENCY_UNRESOLVED/.test(c.why || '')).length;
}

/* Phase 6.2: the CURRENT decision. With `current` in the navigation read, that is current.move; the
 * top-level `move` is only the last PRESENTED turn (history) and is never read as the current decision.
 * Without `current` (older payload, or a snapshot taken right after a send) the presented move is current.
 * A null current.move means "no current decision" and never falls back to the old turn. */
function navCurrentMove(nav) {
  if (!nav) return null;
  if (nav.current) return nav.current.move || null;
  return nav.move || null;
}
/* True when the current decision was recomputed after the last presented turn, so the person has not been
 * asked it yet (move_authority CANDIDATE / AWAITING_PRESENTATION, relation CHANGED_SINCE_PRESENTED, or presented_is_historical). */
function navCurrentNotPresented(nav) {
  const c = nav && nav.current;
  return !!c && (c.move_authority === 'CANDIDATE' || c.status === 'AWAITING_PRESENTATION' || c.relation === 'CHANGED_SINCE_PRESENTED' || c.presented_is_historical === true);
}

/* Header pill: the state of the conversation in words, from checkpoint eligibility
   (int 18 §11.6, phase C 17 Oct): a narrative label replaces the count "N clear, M still to learn".
   Planner counts are often unpopulated on the adaptive path (the "0 clear, 0 still to learn" bug in session
   c913b0b51579) and count proxies are forbidden by contract — eligibility is the official source. */
function clarityText(nav) {
  const mv = navCurrentMove(nav);
  if (!mv) return 'Getting started';
  // MC01-5 (audit P1): DEGRADED = technical failure, NOT a business pause — the pill must distinguish it
  // before reading kind (compat DTO uses kind=HOLD for degraded; dsc.v1: ACTION ≠ eligibility).
  if (mv.degraded) return 'Technical pause';
  const cp = mv.checkpoint || {};
  if (cp.can_offer_checkpoint) return 'First picture available';
  if (cp.level === 'DISCOVERY_NEEDED') {
    const paths = (nav.summary && nav.summary.paths) || [];
    return paths.length ? 'Some possibilities are emerging' : 'Understanding your situation';
  }
  if (cp.level === 'STATE_ONLY') return 'Understanding your situation';
  // compat fallback: legacy DTO without a checkpoint block — use kind, not a fake number
  if (mv.kind === 'HOLD') return 'On hold';
  return 'Getting to know you';
}

/* The small caption on an engine message: what kind of move it was and what it was about. */
function moveTagHtml(move) {
  if (!move) return '';
  // CIR-01 (int 19 §11.6): a technical failure looks DIFFERENT from a business HOLD — a technical pause (amber, recoverable),
  // not "we decided to stop". Source: the degraded flag + stable error_code from the backend.
  if (move.degraded) {
    const why = { PROVIDER_UNAVAILABLE: 'the model service did not answer', SCHEMA_INVALID: 'the answer came back malformed',
                  GUARD_REJECTED: 'the answer failed our safety checks', APPLICATION_ERROR: 'something broke on our side' }[move.error_code] || 'something broke on our side';
    return `<span class="move-tag" data-move-kind="DEGRADED" title="Technical failure (${esc(move.error_code || 'UNKNOWN')}) — your story is saved; press Continue to retry without resending."><span class="move-dot" style="background:var(--test-line)" aria-hidden="true"></span>Technical pause · ${esc(why)}</span>`;
  }
  const ready = move.kind === 'ACTION';
  const dot = ready ? 'var(--open-line)' : 'var(--ink-muted)';
  const about = move.headline ? ` · ${esc(brief(move.headline, 60))}` : '';
  return `<span class="move-tag" data-move-kind="${esc(move.kind)}"><span class="move-dot" style="background:${dot}" aria-hidden="true"></span>${esc(moveLabel(move.kind))}${about}</span>`;
}

/* The "what we are asking about" box above the input: current focus, a one-line reason, and an inspectable why. */
function moveFocusHtml(nav) {
  const mv = navCurrentMove(nav);
  if (!mv) {
    return `<span class="nav-focus-label">What we are asking about · Where you are now</span>
      <span class="nav-focus-text">Start with where you are: what you do, what you earn, and where you want to be.</span>`;
  }
  const reason = mv.reason || {};
  // MC01-5: DEGRADED focus = a technical failure that can be recovered WITHOUT resending the story
  // (MC01-2) — not "we decided to stop". A legitimate HOLD still uses business wording.
  if (mv.degraded) {
    const why = { PROVIDER_UNAVAILABLE: 'the model service did not answer', SCHEMA_INVALID: 'the answer came back malformed',
                  GUARD_REJECTED: 'the answer failed our safety checks', APPLICATION_ERROR: 'something broke on our side' }[mv.error_code] || 'something broke on our side';
    return `
    <span class="nav-focus-label" id="nav-focus-label">Technical pause · ${esc(brief(mv.headline || 'Processing stopped', 70))}</span>
    <span class="nav-focus-text" id="nav-focus-text">Your story is saved on the map. ${esc(why)} — press Continue to retry the processing; you don't need to resend anything.</span>
    <details class="nav-why">
      <summary>What happened</summary>
      <ul class="nav-why-list"><li>Technical failure (${esc(mv.error_code || 'UNKNOWN')}) — not a decision to stop.</li></ul>
    </details>`;
  }
  /* A decision recomputed after the last presented turn was never asked: no "asked before" wording and
     no "we are asking" present tense for it. */
  const notAsked = navCurrentNotPresented(nav);
  const lines = whyLines(reason).filter(l => !(notAsked && /^We asked about this before/.test(l)));
  const waiting = waitingCount(reason);
  const trail = [`stage ${reason.stage}`, reason.need_id ? `need ${reason.need_id}` : '', ...(reason.why || []),
    `input ${reason.input_digest || ''}`].filter(Boolean);
  const label = mv.kind === 'ACTION' ? 'What happens next' : (mv.kind === 'HOLD' ? 'Where this stands' : (notAsked ? 'What we will ask next' : 'What we are asking about'));
  const head = mv.kind === 'ACTION' ? 'Enough to map your options' : (mv.headline || 'Your situation');
  const whyLabel = mv.kind === 'ACTION' ? 'Why we can stop asking' : (mv.kind === 'HOLD' ? 'Why we paused' : 'Why we ask this');
  const sub = mv.kind === 'ACTION' ? 'We can build your diagnosis now. You can still add details first.'
    : (mv.kind === 'HOLD' ? 'We cannot name a safe next question yet. Anything new you tell us will be read again.'
      : focusSub(mv, lines));
  const bullets = lines.filter(l => !sub.includes(l));      // the line above already says it: do not repeat it below
  return `
    <span class="nav-focus-label" id="nav-focus-label">${esc(label)} · ${esc(brief(head, 70))}</span>
    <span class="nav-focus-text" id="nav-focus-text">${esc(sub)}</span>
    <details class="nav-why">
      <summary>${esc(whyLabel)}</summary>
      <ul class="nav-why-list">${(bullets.length ? bullets : (lines.length ? [] : ['This is the next thing the engine can act on.'])).map(l => `<li>${esc(l)}</li>`).join('')}
        ${waiting ? `<li>${waiting === 1 ? '1 other thing is waiting: it depends on this, or can only be settled by doing.' : `${waiting} other things are waiting: they depend on this, or can only be settled by doing.`}</li>` : ''}</ul>
      <details class="nav-trail">
        <summary>Engine trail</summary>
        <ul class="nav-trail-list">${trail.map(t => `<li>${esc(t)}</li>`).join('')}</ul>
      </details>
    </details>`;
}
