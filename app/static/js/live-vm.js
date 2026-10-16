/* LIVE view-models: real artifact → the shapes the v9 templates render.
 * Pure functions of LIVE (+ a few UI selections). No DOM, no network. */

/* 1 -> "One", 5 -> "Five"; beyond twelve the numeral reads better than a word. */
const COUNT_WORD_LIST = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve'];
function countWord(n) { return COUNT_WORD_LIST[n] || String(n); }
const STATUS_WORD = { OPEN: 'OPEN', TEST_FIRST: 'TEST FIRST', NOT_YET: 'NOT YET', STOP: 'STOP' };

/* Decision spectrum (engine) → the headline verdict on the reveal screen. */
const VERDICT_UI = {
  STOP:       { pill: 'STOP',        line: "Don't move on this yet.",                    tone: 'stop' },
  NOT_YET:    { pill: 'NOT YET',     line: 'Not yet. Measure first, then move.',         tone: 'notyet' },
  TEST_FIRST: { pill: 'TEST FIRST',  line: 'Move, but test small first.',                tone: 'test' },
  GO_SMALL:   { pill: 'GO SMALL', line: "Move, but don't spend money yet.",           tone: 'ink' },
  PROCEED:    { pill: 'GO',          line: 'The evidence supports moving now.',          tone: 'open' },
  SCALE:      { pill: 'SCALE',       line: 'The model is proven. Make it systematic.',   tone: 'open' }
};

function liveVerdict() {
  const lvl = ((LIVE.artifact || {}).decision_spectrum || {}).level;
  return Object.assign({ level: lvl || null }, VERDICT_UI[lvl] || { pill: 'IN PROGRESS', line: 'Your diagnosis is still forming.', tone: 'ink' });
}
function bandWord(b) { return ({ HIGH: 'High confidence', MEDIUM: 'Medium confidence', LOW: 'Low confidence' })[b] || 'Confidence not set'; }

/* ── Paths ─────────────────────────────────────────────────────────────────── */
/* Per-path plain-language rewrite (LIVE.explain.paths, written from the user's own words and checked by the
 * server, the same layer as the Diagnosis screen). Falls back, path by path, to the engine's own template. */
function liveExplainPaths() {
  if (LIVE.explainState !== 'ready' || !LIVE.explain || !Array.isArray(LIVE.explain.paths)) return [];
  return LIVE.explain.paths.filter(x => x && x.key);
}
function liveExplainChecks() {
  if (LIVE.explainState !== 'ready' || !LIVE.explain || !Array.isArray(LIVE.explain.checks)) return {};
  const m = {};
  LIVE.explain.checks.forEach(c => { if (c && c.key) m[c.key] = c; });
  return m;
}

/* The active goal's metric context (engine's own goal context) — relation copy uses it so a
 * hypothesis line names the goal's own measure, never money. */
function liveGoalMetric() { return (V11_ENGINE.snapshot().goal || {}).metric || null; }
/* F-01: the engine's goal relation, spoken in user language. UNKNOWN_RELATION stays a hypothesis
 * judged by the goal's own measure; DIRECT_CONTRIBUTION stays the domain definition (not a
 * proof of effectiveness — that is what the path's checks say). */
function relationLineOf(relation) {
  if (relation === 'UNKNOWN_RELATION') {
    const m = liveGoalMetric();
    const measure = (m && (m.name || m.id)) || "your goal's measure";
    return 'Hypothesis for your goal: nothing on record yet proves this path moves ' + measure +
      '. Test it small and judge it by ' + measure + ', not by money.';
  }
  if (relation === 'DIRECT_CONTRIBUTION') return "Direct line to your income goal: this map's paths are defined against it.";
  return '';
}

/* Phase 4 (ronde 4): the relation must be visible wherever a path is offered as an option, not only in a detail
 * panel. These helpers are the one reading of `goal_relation` for every Maps surface, Moves and the route list.
 * UNKNOWN_RELATION is shown as a hypothesis: it never becomes a claim that the path works, and it does not change
 * the path's status (TEST FIRST / OPEN / ... come from the evidence, not from the relation). */
function isHypothesisPath(p) { return !!p && p.goal_relation === 'UNKNOWN_RELATION'; }
function relationMeasure() {
  const m = liveGoalMetric();
  return (m && (m.name || m.id)) || "your goal's measure";
}
function relationShortLine(p) {
  return isHypothesisPath(p)
    ? 'Not shown yet: nothing on record says this moves ' + relationMeasure() + '. A hypothesis to test.' : '';
}
function relationChipHtml(p) {
  return isHypothesisPath(p)
    ? `<span class="mp-tag mp-rel" title="${esc(relationLineOf('UNKNOWN_RELATION'))}">Hypothesis</span>` : '';
}
/* The full sentence, as its own element so tests, screen readers and every lens read the same text */
function relationBlockHtml(p, cls) {
  const line = relationLineOf(p && p.goal_relation);
  if (!line) return '';
  return `<p class="${cls || 'mp-sel-line'} mp-rel-line" data-testid="path-relation" data-relation="${esc(p.goal_relation)}">${esc(line)}</p>`;
}

/* Path view-model: a pure reading of `possible_paths` (0..N paths). Names, status, checks, unlock text and the
 * reason sentences all come from the engine; the UI picks its language and phrases the two sentences below
 * (`why`, `next`) around them. No path list, name table or requirement rule lives here. */
function livePathModels() {
  // LEGACY (doc 14 §11): an artifact older than the schema — or with unreadable content — carries NO path
  // finding at all. Its entries are never rendered, with or without content (audit #9): the map shows the
  // legacy card instead (liveNoPaths), never paths read out of an untrusted artifact.
  if (liveLegacyNav()) return [];
  const raw = livePathSet().paths || [];
  const activeKey = liveActivePathKey();
  const rs = useRoadmapStore.getState();
  const cur = rs.steps && rs.steps[rs.currentStep - 1];
  const exPaths = liveExplainPaths();
  return raw.map(p => {
    const status = pathStatusOf(p);
    const pres = (p.presentation || {})[UI_LANG] || {};
    const checks = p.checks || [];
    const passed = checks.filter(c => c.state === 'PRESENT');
    const failed = checks.filter(c => c.state === 'ABSENT');
    const unknown = checks.filter(c => c.state === 'UNKNOWN');
    const unlock = checks.filter(c => c.state !== 'PRESENT' && pickText(c, 'unlock')).map(c => pickText(c, 'unlock'));
    const missing = unknown.map(c => ({ check_id: c.check_id, need: pickText(c, 'unlock') }));
    const isActive = p.path_id === activeKey;
    const reason = c => (c ? pickText(c, 'reason') + '.' : '');
    const lifecycleStop = (p.stop_provenance || []).find(x => x.source === 'LIFECYCLE');
    const stopReason = lifecycleStop ? (lifecycleStop.cause_i18n && lifecycleStop.cause_i18n[UI_LANG]) || lifecycleStop.cause || '' : '';
    let why, next;
    if (status === 'OPEN') {
      // "clears every check" is only true when there are checks: a path that declares no entry conditions says that instead
      why = checks.length ? 'Your evidence clears every check for this path. ' + reason(passed[0]) : 'This path has no entry conditions to check, so nothing holds it back.';
      next = isActive && cur ? `Today: ${String(cur.label).replace(/[.。]+$/, '')}.` : 'Open, but not your current path. Come back to it if the current path stalls.';
    } else if (status === 'TEST_FIRST') {
      why = checks.length ? 'Some checks cannot be judged yet, so this path needs a small test first. ' + reason(unknown[0]) : 'Nothing was set to check this path against, so it needs a small test first.';
      next = (missing[0] && missing[0].need) || unlock[0] || 'Run one small test before you commit.';
    } else if (status === 'NOT_YET') {
      why = 'Not open yet. ' + (failed[0] ? reason(failed[0]) : reason(unknown[0]));
      next = unlock.length ? 'Opens when: ' + unlock.join(' Then: ') : 'Keep going on your current path. This one opens when its checks pass.';
    } else {
      why = stopReason || ('The facts say no for now. ' + reason(failed[0]));
      next = unlock.length ? 'Reopens when: ' + unlock.join(' Then: ') : 'Wait until you have real results to show first.';
    }
    const exp = exPaths.find(x => x.key === p.path_id) || null;
    const expWhy = exp && String(exp.why || '').trim();
    const expNext = exp && String(exp.next || '').trim();
    return {
      key: p.path_id, id: p.path_id, name: p.title, word: pres.word || p.title, short: pres.short || p.title,
      status, raw: p.feasibility, lifecycle: p.lifecycle, basis: pres.basis || p.basis || '',
      why: (expWhy || why).trim(), next: (expNext || next).trim(), explained: !!(expWhy || expNext),
      /* F-01: the engine's goal relation survives the response → view-model flow */
      goalRelation: p.goal_relation || null, goalRelationNote: p.goal_relation_note || '',
      relationLine: relationLineOf(p.goal_relation || null),
      unlock, missing, passedN: passed.length, gateN: checks.length, isActive, stopReason, checks
    };
  });
}

/* Zero Possible Paths is a valid answer, not an error: the engine says WHY it could not form a path (universal reason
 * codes plus what it does not know yet), in the UI language. Nothing is invented to fill the space. */
function liveNoPaths() {
  const set = livePathSet();
  if (!LIVE.artifact) return null;
  // LEGACY wins over any content (doc 14 §11): with or without entries in `paths`, an untrusted artifact
  // carries no path finding — the legacy card is shown, never the entries and never "no paths".
  const legacy = liveLegacyNav();
  if (legacy) return [{ code: legacy.reason_code, text: pickText(legacy, 'detail'), missing: [], legacy: true }];
  if ((set.paths || []).length) return null;
  return (set.unresolved || []).map(u => ({
    code: u.code, text: pickText(u, 'detail'),
    missing: (u.missing_detail || []).map(m => pickText(m, 'reason')).filter(Boolean)
  }));
}
function liveNoPathsHtml() {
  const reasons = liveNoPaths() || [];
  if (liveLegacyNav()) {
    const why = reasons.map(r => `<p style="font-size:14px;color:var(--ink-2);line-height:1.55;margin:10px 0 0">${trText(r.text)}</p>`).join('');
    return `<div class="card-clean" data-testid="legacy-artifact" style="padding:24px"><h2 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin:0">This map needs a fresh look.</h2>${why}<p style="font-size:13px;color:var(--ink-3);margin:14px 0 0">Run a new check-in and the map is rebuilt from your evidence with the current method.</p></div>`;
  }
  const why = reasons.map(r => `<p style="font-size:14px;color:var(--ink-2);line-height:1.55;margin:10px 0 0">${trText(r.text)}</p>`).join('');
  const missing = [].concat(...reasons.map(r => r.missing));
  const list = missing.length
    ? `<p style="font-size:12.5px;font-weight:600;margin:14px 0 4px">What we do not know yet</p><ul style="margin:0;padding-left:18px;font-size:13px;color:var(--ink-2);line-height:1.6">${missing.map(m => `<li>${trText(m)}</li>`).join('')}</ul>`
    : '';
  return `<div class="card-clean" data-testid="no-paths" style="padding:24px"><h2 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin:0">We cannot name a path yet.</h2>${why}${list}<p style="font-size:13px;color:var(--ink-3);margin:14px 0 0">Tell us more in a follow-up check-in and the map is rebuilt from it.</p></div>`;
}

/* Candidate Possibility, as the reader meets it (internal-docs §23). Two things, both read from the
 * engine's projection and never decided here:
 *   - a path that was born from a verified mechanism says WHY it is on the map (liveWhyHereHtml);
 *   - a possibility that is only taking shape is NOT a path: it sits in its own card, with its own words, until the
 *     evidence settles (liveEmergingHtml). One fact missing, parts of the evidence disagree, or a hint with nothing
 *     behind it: three different things, never shown as a way forward. */
const EMERGING_COPY = {
  UNKNOWN: { word: 'One fact missing', line: 'We have a first sign of this, but one fact is still missing.' },
  CONFLICT: { word: 'Not settled', line: 'Parts of what you told us point in different directions, so we are not counting this yet.' },
  UNSUPPORTED: { word: 'Not backed yet', line: 'We noticed a hint of this, but nothing you shared backs it, so we are not counting it.' }
};
function liveEmerging() {
  const pr = LIVE.projection;
  if (!pr || !pr.navigation || pr.navigation.status !== 'CURRENT') return [];
  return (pr.emerging || []).filter(e => EMERGING_COPY[e.state]);
}
function liveEmergingHtml() {
  const items = liveEmerging();
  if (!items.length) return '';
  const row = e => {
    const c = EMERGING_COPY[e.state];
    const need = e.state === 'UNKNOWN' ? (e.need || []).map(rdTxt).filter(Boolean) : [];
    return `<li class="emerging-item" data-state="${esc(e.state)}">
      <div class="emerging-top"><span class="emerging-title">${rdTxt(e.title)}</span><span class="emerging-pill">${c.word}</span></div>
      <p class="emerging-line">${c.line}</p>
      ${need.length ? `<p class="emerging-need"><span>To settle it:</span> ${need.join('; ')}</p>` : ''}
    </li>`;
  };
  return `<section class="card-clean emerging" data-testid="emerging" aria-labelledby="emerging-head">
    <h2 id="emerging-head" class="emerging-head">Taking shape</h2>
    <p class="emerging-sub">Not on your map yet. A possibility becomes a path only when the evidence settles.</p>
    <ul class="emerging-list">${items.map(row).join('')}</ul>
  </section>`;
}
function liveCandidateOf(key) {
  const pr = LIVE.projection;
  if (!pr || !pr.navigation || pr.navigation.status !== 'CURRENT') return null;
  const p = (pr.paths || []).find(x => x.key === key);
  return p && p.candidate && p.candidate.why ? p.candidate : null;
}
function liveWhyHereHtml(key) {
  const c = liveCandidateOf(key);
  if (!c) return '';
  const n = (c.evidence_ids || []).length, k = (c.knowledge_ids || []).length;
  const basis = `${n ? `It rests on ${n} ${n === 1 ? 'thing' : 'things'} you shared` : 'It rests on what you shared'}${k ? `, read against ${k} ${k === 1 ? 'rule' : 'rules'} from our knowledge base` : ''}.`;
  // Two things the engine keeps beside the reason, said plainly: a related reading that is not settled (it is NOT
  // part of the reason), and support that leans on "nothing you shared says otherwise" (not the same as confirmed).
  const names = (c.unsettled || []).map(u => String(u.name || '').trim().toLowerCase()).filter(Boolean);
  const unsettled = names.length ? `<p class="why-here-note" data-testid="why-here-unsettled">Parts of what you told us point in different directions about ${names.map(esc).join(' and ')}, so we are not counting that as part of the reason.</p>` : '';
  const assumes = c.assumes_absence ? `<p class="why-here-note" data-testid="why-here-assumes">It also assumes nothing you told us points the other way. We have not confirmed that.</p>` : '';
  return `<details class="why-here" data-testid="why-here"><summary>Why this is on your map</summary>
    <p class="why-here-text">${rdTxt(c.why)}</p><p class="why-here-basis">${basis}</p>${unsettled}${assumes}</details>`;
}

/* The presentation cap, said out loud (internal-docs §24.7). The engine forms 0..N possibilities and
 * the screens draw at most PATH_VIEW_CAP of them (present-cap.js). What is not drawn is not hidden from the
 * reader: this is the honest counterpart, "+3 other possibilities", with the same names, statuses and reasons
 * behind a disclosure that works with Enter and Space. It never says or implies that the drawn ones are all there
 * is, and it never ranks them.
 *   pres  the result of presentPaths()
 *   opts  { pick: 'jsFunctionName' (called with the path key), pickLabel } */
const PATH_PILL_CLS = { OPEN: 'open', TEST_FIRST: 'test_first', NOT_YET: 'not_yet', STOP: 'stop' };
function pathShownLine(pres) {
  return `Showing ${countWord(pres.visible.length).toLowerCase()} of ${countWord(pres.total).toLowerCase()} possibilities`;
}
function livePathOverflowHtml(pres, opts) {
  if (!pres || !pres.overflow) return '';
  const o = opts || {};
  const n = pres.overflow;
  const held = pres.summary.map(s => `${s.n} ${s.label}`).join(' · ');
  const row = p => `<li class="po-row" data-key="${esc(p.key)}">
      <div class="po-row-top"><span class="po-name">${esc(p.name)}</span><span class="status-pill ${PATH_PILL_CLS[p.status] || 'not_yet'}">${STATUS_WORD[p.status] || ''}</span></div>
      ${p.why ? `<p class="po-why">${esc(brief(p.why, 120))}</p>` : ''}
      ${o.pick ? `<button type="button" class="btn-secondary po-pick" onclick="${o.pick}('${esc(p.key)}')">${esc(o.pickLabel || 'Look at this one')}</button>` : ''}
    </li>`;
  return `<details class="path-overflow" data-testid="path-overflow" data-hidden="${n}" ${STORE.pathOverflowOpen ? 'open' : ''} ontoggle="STORE.pathOverflowOpen = this.open">
    <summary><span class="po-count">+${n} other ${n === 1 ? 'possibility' : 'possibilities'}</span><span class="po-note">${pathShownLine(pres)}. Not drawn: ${held}.</span></summary>
    <p class="po-sub">They are not drawn here, but they are on your map with the same evidence behind them.</p>
    <ul class="po-list">${pres.hidden.map(row).join('')}</ul>
  </details>`;
}

/* The same answer, compact, for the diagnosis screen's side card. */
function liveNoPathsInline() {
  const reasons = liveNoPaths() || [];
  const first = reasons[0];
  if (liveLegacyNav()) return `<p data-testid="legacy-artifact-inline" style="font-size:13.5px;line-height:1.55;color:var(--ink-2);margin:0">This map needs a fresh look. ${first ? trText(first.text) : ''}</p>`;
  return `<p data-testid="no-paths-inline" style="font-size:13.5px;line-height:1.55;color:var(--ink-2);margin:0">We cannot name a path yet. ${first ? trText(first.text) : ''}</p>`;
}

/* ── Today plan (day_by_day → steps) ───────────────────────────────────────── */
const SEND_RE = /\b(send|message|reply|follow[ -]?up|email|dm|whatsapp|contact|call|kirim|balas|pesan|hubungi|telepon)\b/i;

function actionParts(it, i) {
  const text = String((it && it.text) || it || '').trim();
  const m = text.match(/^(?:hari|day|h)\s*(\d+)(?:\s*[-–]\s*\d+)?\s*[:.\-–]?\s*/i);
  const body = m ? text.slice(m[0].length) : text;
  return { day: (it && it.day) || (m ? Number(m[1]) : i + 1), body };
}
function oneWord(body) {
  // first real word (skip numbers, ids and 1-2 letter fillers)
  const words = String(body || '').split(/\s+/).map(w => w.replace(/[^A-Za-z\-]/g, '')).filter(w => w.length >= 3);
  const s = words[0] || '';
  return s ? s.charAt(0).toUpperCase() + s.slice(1, 11).toLowerCase() : 'Step';
}

function liveSteps() {
  const d = LIVE.artifact;
  if (!d) return [];
  /* Phase 7: ONLY the recorded legacy plan is read here, and only as history. The old browser-tracked
     "single fallback step" (built from first_step_today / next_best_action and marked done in
     localStorage, with no server action slot) is REMOVED: an execution record the server never
     accepted must not exist. Executable work is the canonical Move's own action list. */
  const items = d.day_by_day || [];
  const startDay = (LIVE.checkins.length ? LIVE.checkins[LIVE.checkins.length - 1].day : 0) + 1;
  const script = String(d.outreach_script || '').trim();
  const scriptUsable = script && !script.startsWith('[');
  // The ready-to-send message belongs only to a step that IS the sending (starts with the verb) or
  // explicitly mentions it. Phase 3: the old fallback ("else step 1") attached an outreach script to
  // unrelated actions — a review step must not offer Copy message / Open WhatsApp. No match, no script.
  const STARTS_SEND = /^\s*(send|reply|message|follow[ -]?up|email|dm|whatsapp|contact|call|kirim|balas|hubungi|telepon)\b/i;
  let scriptAt = items.findIndex(it => STARTS_SEND.test(actionParts(it, 0).body));
  if (scriptAt < 0) scriptAt = items.findIndex(it => SEND_RE.test(actionParts(it, 0).body));
  // A low-confidence plan ends with a note ("Hari 4-7 DIGANTUNG: ...") saying the later days wait for what the
  // first steps show. It is a hold, not a task: it can never be marked done and never counts as ready.
  const isHold = it => /DIGANTUNG/i.test(String((it && it.text) || it || ''));
  const firstTodo = items.findIndex(it => !isHold(it) && ((it.status || 'TODO') === 'TODO' || it.status === 'BLOCKED'));
  const cycleLen = liveCycleLen();
  // Steps are tasks, not calendar slots: any that is not done can be done now, in any order. The plan's day is
  // only when it suggests doing it; a done step keeps the real day it was finished on.
  const dayOf = ts => (ts && LIVE.startTs ? Math.max(1, Math.floor((ts * 1000 - LIVE.startTs) / 86400000) + 1) : null);
  const today = liveDay();
  const steps = items.map((it, i) => {
    const { day, body } = actionParts(it, i);
    const absDay = startDay + day - 1;
    const st = it.status || 'TODO';
    const hold = isHold(it);
    const isDone = !hold && (st === 'DONE' || st === 'SKIPPED');
    const status = isDone ? STEP_STATUS.COMPLETED
      : (i === firstTodo ? STEP_STATUS.CURRENT : STEP_STATUS.UPCOMING);
    const isScript = scriptUsable && i === scriptAt;
    const doneDay = isDone ? (dayOf(it.done_at) || today) : null;
    return {
      num: i + 1, idx: i, id: `live-step-${i + 1}`, status, done: isDone, hold, ready: !isDone && !hold, needs: hold ? [items.length + 1] : [], waitingFor: hold ? [items.length + 1] : [], doneDay,
      label: brief(body, 68), title: brief(body, 170), full: userFacing(body),
      desc: i === 0 && d.first_step_today && brief(d.first_step_today, 200) !== brief(body, 200) ? brief(userFacing(d.first_step_today), 200) : '',
      /* Phase 7: no planned-day language. `day` stays a numeric ordering key for legacy charts only;
         the day label is empty and the timing line is about readiness, never a calendar slot. */
      day: absDay, dayLabel: '', mapLabel: oneWord(body),
      timeTag: hold ? 'On hold' : isDone ? 'Done' : 'Ready when you are',
      doneDay: doneDay,
      local: !!it.local, sent: SEND_RE.test(body), outcome: it.outcome || '', note: it.note || '', rawStatus: st,
      expected: it.expected_evidence || '',
      box: () => isScript
        ? renderMsgBox('Message, ready to send', script, script, false, { noLang: true, lang: document.documentElement.lang || 'en' })
        : (it.expected_evidence
          ? renderListBox('What to look for', 'You will know this step worked when:', [esc(it.expected_evidence)])
          : '')   // the cycle's success measure is shown once, under the card (no second copy here)
    };
  });
  const reportDay = startDay + cycleLen - 1;
  const allDone = firstTodo < 0;
  const tasks = steps.filter(s => !s.hold);
  const openNums = tasks.filter(s => !s.done).map(s => s.num);
  steps.push({
    num: steps.length + 1, idx: -1, id: 'live-step-report', status: allDone ? STEP_STATUS.CURRENT : STEP_STATUS.UPCOMING,
    done: false, ready: allDone, needs: tasks.map(s => s.num), waitingFor: openNums,
    label: 'Report your results', title: 'Report what happened.',
    desc: 'Tell us who replied, who you spoke to, and whether anyone paid. Your map updates from there.',
    day: reportDay, dayLabel: '', mapLabel: 'Check-in', timeTag: 'Check-in', sent: false, report: true,
    box: () => renderDoneBox(allDone ? 'All steps done' : 'Almost there', 'Time for your check-in: how many people replied, how many calls you had, and whether anyone paid.')
  });
  return steps;
}

/* ── Route steps (Today: "also ready, from your routes") ───────────────────────
 * Nodes on the frontier of a route that applies to this user: EXECUTE = ready to do, VERIFY = done, proof still
 * missing. Only what the engine says is shown: routes that still need a clarifying answer stay out (which routes
 * to surface is an open product decision, internal-docs §8), and at most 3 steps at a time. */
function liveRouteTasks() {
  const r = LIVE.routes;
  if (!r || !Array.isArray(r.routes)) return [];
  const first = r.next_move && r.next_move.frontier_ref;
  const out = [];
  r.routes.forEach(route => {
    if ((route.applicability || {}).status !== 'APPLIES' || route.lineage_status !== 'OPEN') return;
    const name = route.path_title || 'Your route';
    const relPath = ((V11_ENGINE.snapshot().paths) || []).find(x => x.id === route.path_id);
    (route.frontier || []).forEach(e => {
      if (e.kind !== 'EXECUTE' && e.kind !== 'VERIFY') return;
      const node = (route.nodes || []).find(n => n.node_id === e.node);
      if (!node || node.execution_view === 'ABANDONED') return;
      const args = ev => `'${route.route_id}','${node.node_id}','${ev}'`;
      const actEn = ((node.i18n || {}).en || {}).activity;
      out.push({
        key: node.node_id, route: esc(name), title: esc(actEn || node.activity), lang: actEn ? 'en' : 'id', hyp: isHypothesisPath(relPath),
        state: e.kind === 'VERIFY' ? 'proof' : 'ready', firstMove: node.node_id === first,
        onDone: `liveRouteEvent(${args('EXECUTED')})`, onUndo: `liveRouteEvent(${args('RESET')})`
      });
    });
  });
  out.sort((a, b) => (b.firstMove - a.firstMove) || ((a.state === 'proof') - (b.state === 'proof')));
  return out.slice(0, 3);
}

/* ── Phase 7: the canonical Move read model ─────────────────────────────────
   ONE reader for Maps, Moves, Journey and the completion prompt. The rows come from the canonical
   Move ledger (GET /moves, or the same rows on the version-bound /experience payload): every row
   carries its server-issued move_id and its OWN action list. Nothing here is matched by title,
   inferred from array position, or fabricated in the browser. */
function liveMoveRows() {
  const a = (LIVE.moves && Array.isArray(LIVE.moves.moves)) ? LIVE.moves.moves : null;
  const b = (LIVE.experience && Array.isArray(LIVE.experience.moves)) ? LIVE.experience.moves : null;
  const rows = (a && a.length) ? a : (b || a || []);
  return rows.filter(function (x) { return x && x.move_id; });
}
function liveMoveById(moveId) {
  if (!moveId) return null;
  const id = String(moveId);
  return liveMoveRows().find(function (x) { return String(x.move_id) === id; }) || null;
}
/* Moves of ONE path: only through their DECLARED linked_path_id. A Move with no path binding is
   never attributed to a path here (it stays visible as session work, unaffiliated). */
function liveMovesForPath(pathId) {
  const pid = String(pathId || '');
  return liveMoveRows()
    .filter(function (x) { return String(x.linked_path_id || '') === pid; })
    .sort(function (x, y) { return (Number(x.created_ts) || 0) - (Number(y.created_ts) || 0); });
}
/* The Move the person is working on for a path: the newest still-open one; else the newest. */
function liveCurrentMoveForPath(pathId) {
  const rows = liveMovesForPath(pathId);
  if (!rows.length) return null;
  const open = rows.filter(function (x) {
    const l = String(x.lifecycle || '').toUpperCase();
    return l === 'PLANNED' || l === 'STARTED';
  });
  /* The FIRST still-open Move: earlier authorized work is not skipped because a newer Move appeared. */
  return (open.length ? open[0] : rows[rows.length - 1]);
}
/* The session's current Move, as the SERVER names it, with an honest local fallback: the newest open
   Move, else the newest Move awaiting a result, else the newest. */
function liveMovesCurrentId() {
  return (LIVE.moves && LIVE.moves.current_move_id) ? String(LIVE.moves.current_move_id) : '';
}
function liveCurrentMove() {
  const rows = liveMoveRows();
  if (!rows.length) return null;
  const byServer = liveMoveById(liveMovesCurrentId());
  if (byServer) return byServer;
  const open = rows.filter(function (x) {
    const l = String(x.lifecycle || '').toUpperCase();
    return l === 'PLANNED' || l === 'STARTED';
  });
  if (open.length) return open[0];
  const pending = rows.filter(function (x) {
    return String(x.lifecycle || '').toUpperCase() === 'EXECUTED'
      && !(x.outcome_report && (x.outcome_report.outcome || x.outcome_report.note));
  });
  return pending.length ? pending[pending.length - 1] : rows[rows.length - 1];
}
/* The Move a result report would be about: an executed Move, or one whose required actions are all
   done. Null = no canonical result target (the legacy plan flow answers instead). */
function liveMoveOutcomeTarget() {
  const mv = liveCurrentMove();
  if (!mv) return null;
  const l = String(mv.lifecycle || '').toUpperCase();
  if (l === 'EXECUTED' || l === 'OBSERVED') return mv;
  const prog = mv.progress || {};
  return prog.complete ? mv : null;
}
/* Maps: the persistent Move sequence of one path (historical + current), each with its lifecycle and
   its own action progress. The first open Move is the current one; earlier ones stay visible. */
function livePathMoveRows(pathId) {
  const rows = liveMovesForPath(pathId);
  const cur = liveCurrentMoveForPath(pathId);
  const currentId = cur ? String(cur.move_id) : '';
  let seenOpen = false;
  return rows.map(function (x) {
    const life = String(x.lifecycle || 'PLANNED').toUpperCase();
    const prog = x.progress || {};
    const done = ['EXECUTED', 'OBSERVED', 'VALIDATED', 'INCONCLUSIVE', 'UNSUPPORTED'].indexOf(life) >= 0;
    let status = 'next';
    if (life === 'ABANDONED') status = 'abandoned';
    else if (done) status = 'done';
    else if (String(x.move_id) === currentId && !seenOpen) { status = 'current'; seenOpen = true; }
    else if (seenOpen) status = 'locked';
    return {
      id: String(x.move_id), title: brief(userFacing(String(x.objective || 'Move')), 90),
      objective: String(x.objective || ''), status: status, lifecycle: life,
      actionsDone: prog.done || 0, actionsTotal: prog.total || 0,
      actionsRequired: prog.required || 0, complete: !!prog.complete,
      executedTs: x.executed_ts || null, pathId: String(x.linked_path_id || ''), record: x
    };
  });
}
/* P0-04: canonical Move rows for the Moves screen. A DISTINCT object from route nodes
   (liveRouteTasks) and plan steps (liveSteps); never equated with them by title or path name. */
function liveCanonicalMoves() {
  return liveMoveRows().map(function (x) {
    const prog = x.progress || {};
    return {
      moveId: String(x.move_id || ''),
      title: brief(userFacing(String(x.objective || 'Move')), 150),
      objective: String(x.objective || ''),
      lifecycle: String(x.lifecycle || 'PLANNED').toUpperCase(),
      pathId: x.linked_path_id || null,
      actionsDone: prog.done || 0, actionsTotal: prog.total || 0,
      hasOutcome: !!(x.outcome_report && (x.outcome_report.outcome || x.outcome_report.note)),
      raw: x
    };
  }).filter(function (x) { return x.moveId; });
}

/* ── Store hydration ───────────────────────────────────────────────────────── */
function liveTimeline() {
  const h = liveHorizon(), day = liveDay(), cyc = liveCycleLen();
  const cycle = LIVE.checkins.filter(c => c.outcome !== 'missed').length + 1;
  const last = LIVE.checkins.length ? LIVE.checkins[LIVE.checkins.length - 1].day : 0;
  return {
    cycle, cycleDay: Math.max(1, day - last), day, horizon: h, cycleLen: cyc,
    daysLeft: Math.max(h - day, 0), weekday: WEEKDAYS[(day - 1) % 7],
    nextCheckIn: Math.min(last + cyc, h)
  };
}

/* Income on record: the last check-in that carried one, else what the diagnosis found. null = nothing recorded. */
function liveEarnedKnown() {
  const c = LIVE.checkins;
  for (let i = c.length - 1; i >= 0; i--) if (c[i].rp != null) return true;
  return liveGoal().current != null;
}
function liveEarned() {
  const c = LIVE.checkins;
  for (let i = c.length - 1; i >= 0; i--) if (c[i].rp != null) return c[i].rp;
  const g = liveGoal();
  return g.current != null ? g.current : 0;
}

function syncStoreFromLive() {
  if (IS_DEMO || typeof useRoadmapStore === 'undefined') return;
  const steps = liveSteps();
  const cur = steps.findIndex(s => s.status === STEP_STATUS.CURRENT);
  const tl = liveTimeline();
  const g = liveGoal();
  const paths = LIVE.artifact ? livePathModels() : [];
  const ended = LIVE.artifact && liveHorizonKnown() && tl.day >= tl.horizon;   // no deadline on record, no ending
  const earned = liveEarned();
  useRoadmapStore.setState({
    doneNums: steps.filter(s => s.done).map(s => s.num),
    doneDays: steps.reduce((m, s) => (s.done ? Object.assign(m, { [s.num]: s.doneDay }) : m), {}),
    currentCycle: tl.cycle,
    currentStep: cur >= 0 ? cur + 1 : Math.max(steps.length, 1),
    currentDay: tl.day,
    steps,
    activeNodeId: cur >= 0 ? steps[cur].id : '',
    activePathId: liveActivePathKey(),
    activePaths: paths.filter(p => p.status === 'OPEN').map(p => p.key),
    earned,
    moneySaved: null,
    goalRp: g.target != null ? g.target : 0,
    history: LIVE.checkins,
    ending: ended ? (g.target != null && earned >= g.target ? 'success' : 'miss') : null
  });
}


/* ==========================================================================
   V11 SNAPSHOT (record D2, D3). The destinations State, Maps, Moves, Journey and Talk read ONE snapshot shaped like the
   prototype's V11_ENGINE (internal-docs "Engine snapshot layer"):

     goal      { text, now, horizon }                 text/now: "Rp20M a month" / "Rp8M", or 'Not set yet'
     paths[]   { id, title, group?, status_display, lifecycle, stop_source, requirements[], evidence_ids, provenance,
                 trail[], next_move, why_here?, basis?, advisory?, narrative?, conflicts? }
     state     { where_you_are, blocking, why_we_think_so[], what_not_to_do[], next_best_action, know_right_when,
                 when_to_reassess, uncertain[], changed[] } | null
     evidence[] { id, source, quote, day, disputed }
     nextmove  { type: ACTION|QUESTION|EVIDENCE_REQUEST|HOLD|NONE, title, minutes?, path_id, path_affiliation, source, degraded?, move_id? } | null
     zero      { kind, detail, missing[] } | null     why there are no paths (engine's own reason), when there are none

   The adapter ONLY re-shapes what the existing endpoints already say (/state, /diagnosis, /readiness, /navigation,
   /evidence, /journey, plus the workspace and routes the page already loads). It computes no status, no order and no
   count: a field with no engine source is left out, never made up (`group` has none, so it is not set and the UI shows
   no group label). Demo mode uses the prototype's fixtures (demo-data.js) through the same seam.
   ========================================================================== */
const SNAP_WORD = { OPEN: 'OPEN', TEST_FIRST: 'TEST FIRST', NOT_YET: 'NOT YET', STOP: 'STOP' };
const SNAP_SAT = { PRESENT: 'PRESENT', PARTIAL: 'PARTIAL', UNKNOWN: 'UNKNOWN', ABSENT: 'ABSENT' };
const SNAP_ZERO = {
  GOAL_NOT_ESTABLISHED: 'INSUFFICIENT_INFORMATION', INSUFFICIENT_VERIFIED_STATE: 'INSUFFICIENT_INFORMATION',
  NO_SUPPORTED_STRATEGY: 'NO_APPLICABLE_PATH', ALL_CANDIDATES_NOT_APPLICABLE: 'NO_APPLICABLE_PATH', GOAL_ABSENT: 'NO_APPLICABLE_PATH',
  EMPTY_POSSIBILITY_SPACE: 'NO_APPLICABLE_PATH'
};
function snapText(o) { return o && typeof o === 'object' ? String(o.text || '') : String(o || ''); }
function snapEmpty() {
  return { goal: { text: 'Not set yet', now: 'Not set yet', horizon: null }, paths: [], overflow: 0, state: null, evidence: [], nextmove: null, zero: null };
}
/* The first undone, non-hold step of the plan, by the same rule as liveSteps(): the engine's day_by_day order. */
function snapNextAction(diag) {
  const items = (diag && diag.day_by_day) || [];
  const isHold = it => /DIGANTUNG/i.test(String((it && it.text) || it || ''));
  const i = items.findIndex(it => !isHold(it) && ((it.status || 'TODO') === 'TODO' || it.status === 'BLOCKED'));
  if (i >= 0) return userFacing(actionParts(items[i], i).body);
  if (items.length) return '';
  return userFacing((diag && (diag.first_step_today || diag.next_best_action)) || '');
}
/* Goal-Relative formatting (int 09 par 6): one formatter per metric unit — a goal is never
   forced into the "Rp X a month" mould. Values stay what they are; unknown stays 'Not set yet'. */
function fmtGoalValue(gctx, v) {
  if (v == null || isNaN(Number(v))) return 'Not set yet';
  const n = Number(v), unit = gctx.unit || '', mid = gctx.metric_id || '';
  if (mid === 'revenue_monthly' || unit === 'Rp juta/bulan') return fmtM(n);
  if (unit === 'ratio') return (Math.round(n * 1000) / 10) + '%';
  if (unit === 'Rp ribu') return 'Rp' + (+n.toFixed(1)).toLocaleString('en-US') + 'k';
  if (unit === 'hours/week') return (+n.toFixed(1)) + 'h a week';
  if (unit === 'days') return (+n.toFixed(1)) + ' days';
  if (unit === 'criteria') return 'Defined by evidence';
  return String(+parseFloat(n.toFixed(2)));
}
function goalNowLabel(gctx) {
  const mid = (gctx.metric_id || '').toLowerCase();
  if (mid === 'revenue_monthly') return 'Income now';
  return (gctx.metric_name || 'Your metric') + ' now';
}
function goalWord(gctx) { return gctx.metric_name || 'your goal'; }
function fmtGoalText(gctx, sg) {
  const t = sg.target != null ? fmtGoalValue(gctx, sg.target) : null;
  if (!t || t === 'Not set yet') {
    return (gctx.metric_name && gctx.metric_id) ? gctx.metric_name + ': not set yet' : 'Not set yet';
  }
  if ((gctx.unit || '') === 'criteria') return gctx.metric_name + ': ' + t;
  const w = (gctx.measurement_window_days || sg.measurement_window_days)
    ? ' in ' + (gctx.measurement_window_days || sg.measurement_window_days) + ' days' : '';
  const dl = sg.deadline_days ? ' within ' + sg.deadline_days + ' days' : '';
  return t + ' ' + goalWord(gctx).toLowerCase() + (w || dl);
}

/* src = { state, diag, ready, evidence, nav, journey, workspace, routes, explain, checkins } : the payloads of the endpoints. */
function snapshotFromPayloads(src) {
  const diag = src.diag, ready = src.ready;
  if (!diag) return snapEmpty();
  const ex = src.explain || {};
  const has = k => (Array.isArray(ex[k]) ? ex[k].length > 0 : !!String(ex[k] || '').trim());
  const rs = diag.revenue_state || {};
  const sg = ((src.state || {}).goal) || {};
  const gctx = (((diag.possible_paths || {}).context || {}).goal) || {};
  const parsedDeadline = Number(sg.deadline_days);
  const horizon = Number(src.horizonOverride) || (parsedDeadline >= 14 && parsedDeadline <= 120 ? parsedDeadline : 0);
  const target = src.goalOverride || (rs.target_monthly != null ? rs.target_monthly : null);
  const current = rs.current_monthly != null ? rs.current_monthly : null;
  /* Goal display (GR-26/GR-27): metric-aware when the engine's own goal context is in
     (metric_id + unit + readiness); revenue labels remain for revenue goals and legacy
     sessions without a structured goal. */
  let goal;
  if (gctx.metric_id) {
    const dir = gctx.direction || '';
    const decrease = dir === 'DECREASE_TO_THRESHOLD' || dir === 'AT_MOST';
    /* A-02/A-03 (int 09 par 5): a NON-revenue current Goal value is never borrowed from the
       revenue slot (rs.current_monthly) — cross-unit borrowing makes a revenue number
       formatted as leads/rate. Revenue fallback is only valid for a revenue metric. */
    const isRevenueMetric = gctx.metric_id === 'revenue_monthly' || gctx.unit === 'Rp juta/bulan';
    /* Ronde 4: a measurement the workspace holds for THIS goal (comparable, current evaluation) is the goal's value now;
       without one, the goal's own recorded value; unmeasured stays unmeasured (never zero). Revenue keeps its own path. */
    const gm = (src.state || {}).goal_measured;
    const measuredNow = !isRevenueMetric && gm && gm.value != null ? gm.value : null;
    const goalCurrent = measuredNow != null ? measuredNow : (sg.current != null ? sg.current : (isRevenueMetric ? current : null));
    goal = {
      text: fmtGoalText(gctx, sg),
      now: fmtGoalValue(gctx, goalCurrent),
      horizon: horizon ? ('Day ' + horizon) : null,
      metric: {
        id: gctx.metric_id, metric_id: gctx.metric_id,
        name: gctx.metric_name || gctx.metric_id, metric_name: gctx.metric_name || gctx.metric_id,
        unit: gctx.unit || '',
        direction: dir, window: gctx.measurement_window_days || null,
        /* raw metric-unit values for metric-aware renderers (Maps/Journey): never revenue slots */
        target: sg.target != null ? sg.target : null,
        current: goalCurrent,
        ready: !!((gctx.readiness || {}).ready), blocking: ((gctx.readiness || {}).blocking) || [],
        unresolved: ((gctx.readiness || {}).unresolved) || [],
        confirmed: !!gctx.target_confirmed, guardrails: gctx.guardrails || [],
        /* JOURNEY (Goal-relative): the observation series and the assessment come from the server, for THIS goal.
           The UI plots them and words them; it never recomputes attainment or invents a point. */
        series: ((src.state || {}).goal_series) || null,
        assessment: gm && gm.status ? gm.status : null
      }
    };
  } else {
    goal = {
      text: target != null ? (fmtM(target) + ' a month') : 'Not set yet',
      now: current != null ? fmtM(current) : 'Not set yet',
      horizon: horizon ? ('Day ' + horizon) : null
    };
  }

  /* Paths: the adjudicated readiness projection is the one source (a LEGACY artifact carries no path finding). */
  const navOk = ready && ready.navigation && ready.navigation.status === 'CURRENT';
  const legacy = diag.navigation && diag.navigation.status === 'LEGACY' ? diag.navigation : null;
  const overlay = key => { const ps = src.workspace && src.workspace.path_states && src.workspace.path_states[key]; return ps && ps.outcome_state === 'STOPPED'; };
  const exChecks = {}; (ex.checks || []).forEach(c => { if (c && c.key) exChecks[c.key] = c; });
  const exPaths = {}; (ex.paths || []).forEach(p => { if (p && p.key) exPaths[p.key] = p; });
  const routesByPath = {};
  ((src.routes && src.routes.routes) || []).forEach(r => { routesByPath[r.path_id] = r; });
  /* Where the paths come from: the adjudicated projection when it is in; until then (or when it failed) the paths the
     artifact itself carries (`possible_paths`), whose requirements are the path's own checks. Never both, never a list of ours. */
  /* F-01: the engine's goal relation travels with the path into every snapshot consumer
     (the readiness projection rows do not carry it — the artifact's own paths do). */
  const relById = {};
  (((diag.possible_paths || {}).paths) || []).forEach(p => { if (p && p.path_id) relById[p.path_id] = p; });
  const relationOf = key => {
    const src = relById[key];
    return src ? { goal_relation: src.goal_relation || null, goal_relation_note: src.goal_relation_note || '' }
               : { goal_relation: null, goal_relation_note: '' };
  };
  const asProjectionPath = pp => ({
    key: pp.path_id, title: pp.title, status: pp.status, lifecycle: pp.lifecycle, basis: { text: ((pp.presentation || {})[UI_LANG] || {}).basis || '', lang: UI_LANG },
    stop_provenance: pp.stop_provenance || [], provenance: pp.provenance || null, candidate: pp.candidate || null, counts: null, narrative: {},
    items: (pp.checks || []).map(c => { const i = (c.i18n || {})[UI_LANG] || {}; return { key: c.requirement_id || c.check_id, title: { text: i.title || '', lang: i.title ? UI_LANG : 'id' }, state: c.state, guidance: { text: i.unlock || '', lang: UI_LANG }, reason: { text: i.reason || '', lang: UI_LANG } }; })
  });
  const projPaths = navOk ? (ready.paths || []) : [];
  const diagOk = !legacy && (!diag.navigation || diag.navigation.status === 'CURRENT');
  const fromDiag = diagOk && !projPaths.length ? (((diag.possible_paths || {}).paths) || []).map(asProjectionPath) : [];
  const paths = (projPaths.length ? projPaths : fromDiag).map(p => {
    /* Stopped by you: the engine's own lifecycle says STOPPED or PAUSED (an outcome you reported), or a fresh report the server has not re-read yet. A STOP with an OPEN lifecycle is the evidence's. */
    const byYou = !!overlay(p.key) || p.lifecycle === 'STOPPED' || p.lifecycle === 'PAUSED';
    const status = byYou ? 'STOP' : p.status;
    const reqs = (p.items || []).map(it => {
      const contested = it.settled === false;
      const x = exChecks[it.key];
      return {
        id: it.key, label: snapText(it.title) || it.key,
        satisfaction: contested ? 'UNKNOWN' : (SNAP_SAT[it.state] || 'UNKNOWN'),
        conflict: contested || !!it.conflict, conflict_note: it.conflict ? snapText(it.conflict.note) : '',
        guidance: x && x.how ? String(x.how) : snapText(it.guidance),
        reason: snapText(it.reason),
        partial: !!it.partial, executed: !!it.executed
      };
    });
    const ep = exPaths[p.key] || {};
    const cand = p.candidate && p.candidate.why ? p.candidate : null;
    /* The path's own next move: the first node on its route's frontier that can be done now (or needs proof), worded by
       the requirement's curated guidance. A node whose only wording is the engine's untranslated text is left out. */
    const route = routesByPath[p.key];
    let nextMove = null;
    if (route && (route.applicability || {}).status === 'APPLIES' && route.lineage_status === 'OPEN') {
      const fe = (route.frontier || []).find(e => e.kind === 'EXECUTE' || e.kind === 'VERIFY');
      const node = fe && (route.nodes || []).find(n => n.node_id === fe.node);
      const it = node && (p.items || []).find(i => i.key === (node.resolves || [])[0]);
      const g = it && it.guidance;
      if (g && g.text && (g.source === 'curated' || g.lang === UI_LANG)) nextMove = { type: 'ACTION', title: String(g.text), why: '' };
    }
    const unsettled = cand ? (cand.unsettled || []).map(u => String(u.name || '').trim().toLowerCase()).filter(Boolean) : [];
    const ne = cand ? (cand.evidence_ids || []).length : 0, nk = cand ? (cand.knowledge_ids || []).length : 0;
    const whyBasis = cand ? `${ne ? `It rests on ${ne} ${ne === 1 ? 'thing' : 'things'} you shared` : 'It rests on what you shared'}${nk ? `, read against ${nk} ${nk === 1 ? 'rule' : 'rules'} from our knowledge base` : ''}.` : '';
    const whyNotes = [];
    if (unsettled.length) whyNotes.push(`Parts of what you told us point in different directions about ${unsettled.join(' and ')}, so we are not counting that as part of the reason.`);
    if (cand && cand.assumes_absence) whyNotes.push('It also assumes nothing you told us points the other way. We have not confirmed that.');
    const trail = (src.overrides || []).filter(o => o.path === p.key).map(o => `${new Date(o.ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} · You chose to go ahead anyway. Your decision, recorded here`);
    const stoppedByEvidence = status === 'STOP' && !byYou;
    const lifeStop = (p.stop_provenance || []).find(x => x.source === 'LIFECYCLE');
    const rel = relationOf(p.key);
    return {
      id: p.key, title: p.title, status_display: SNAP_WORD[status] || 'NOT YET',
      lifecycle: byYou ? (p.lifecycle === 'PAUSED' ? 'PAUSED' : 'STOPPED') : (p.lifecycle || 'OPEN'),
      stop_source: byYou ? 'you' : (stoppedByEvidence ? 'evidence' : null),
      goal_relation: rel.goal_relation, goal_relation_note: rel.goal_relation_note,
      requirements: reqs,
      route_nodes: route ? (route.nodes || []) : null,
      route_frontier: route ? (route.frontier || []) : null,
      evidence_ids: (p.provenance && p.provenance.evidence_ids) || [],
      provenance: p.provenance && (p.provenance.evidence_ids || []).length ? 'From your Talk' : '',
      trail, next_move: nextMove,
      /* Phase 7: the canonical Moves of this path, in order, each with its own lifecycle and action
         progress. The legacy 'moves' field keeps its branching-illustration meaning, so the live map
         keeps rendering the 2D composition; the canonical sequence travels in canonical_moves. */
      canonical_moves: livePathMoveRows(p.key),
      basis: snapText(p.basis), advisory: snapText(p.advisory),
      why_here: cand ? snapText(cand.why) : '', why_basis: whyBasis, why_notes: whyNotes,
      narrative: { opening: String(ep.opening || ''), supported: String(ep.supported || (p.narrative || {}).supported || ''), holding: String(ep.holding || (p.narrative || {}).holding || ''), unclear: String(ep.unclear || (p.narrative || {}).unclear || '') },
      counts: p.counts || null,
      stop_cause: lifeStop ? ((lifeStop.cause_i18n || {})[UI_LANG] || '') : ''
    };
  });

  /* Evidence: the user's own words, verbatim (the ledger's source_quote). A gap is a question, not a fact. */
  const evAll = (src.evidence && src.evidence.evidence) || [];
  const facts = evAll.filter(e => !e.is_gap);
  const gaps = evAll.filter(e => e.is_gap);
  const topic = e => ((typeof TOPIC_UI !== 'undefined' && TOPIC_UI[e.topic]) || {}).label || '';
  const evidence = facts.map(e => ({ id: e.id, source: 'From your Talk' + (topic(e) ? ' · ' + topic(e) : ''), quote: String(e.source_quote || e.signal || ''), day: null, disputed: false }));

  /* NextMove: ONE living decision the server presents (the CURRENT decision = navCurrentMove(src.nav), which is
     nav.current.move when the read carries it, else the presented nm.v2 + guard). The route
     frontier / plan step are kept as clearly-separate fallbacks (source label), never silently substituted
     for the live decision. */
  const liveMove = navCurrentMove(src.nav);
  const nm = src.routes && src.routes.next_move;
  const step = snapNextAction(diag);
  const MOVE_TYPES = ['ACTION', 'QUESTION', 'EVIDENCE_REQUEST', 'HOLD', 'NONE'];
  let nextmove = null;
  if (liveMove && MOVE_TYPES.includes(liveMove.kind)) {
    // path_id: EXPLICIT affiliation from the server (nullable) is prioritized. The route selector is only a fallback
    // proxy (legacy DTO compat) - not the main way to choose a Path. mapsActive() uses this path_id as the
    // sole determinant of path focus on the snapshot.
    const liveRoute = (src.routes && src.routes.routes || [])
      .find(r => nm && (r.route_id === nm.route_id || r.route_id === nm.frontier_ref));
    // EXPLICIT path_id (nullable) is the server's final answer: null means "no single path" and
    // MUST stay null. Only fields that are genuinely ABSENT (legacy DTO) may use the route proxy.
    // JSON.parse never yields undefined for a key that exists, so undefined = absent field.
    const pathIsExplicit = liveMove.path_id !== undefined;
    const explicitPath = pathIsExplicit ? (liveMove.path_id || null) : null;
    nextmove = {
      type: liveMove.kind,
      title: liveMove.headline || liveMove.text || '',
      path_id: pathIsExplicit ? explicitPath : (liveRoute ? liveRoute.path_id : null),
      path_affiliation: pathIsExplicit ? (explicitPath ? 'explicit' : 'none') : (liveRoute ? 'derived' : 'none'),
      degraded: !!liveMove.degraded,
      move_id: liveMove.move_id || null,
      /* only an authorized (PRESENTED) decision may claim to be presented; a candidate stays a candidate */
      source: navCurrentNotPresented(src.nav) ? 'candidate' : 'presented'
    };
  } else if (nm && nm.output) {
    // A CLEARLY separate fallback: not a live decision (nm.v2) - source is carried to the UI, not swallowed.
    const route = (src.routes.routes || []).find(r => r.route_id === nm.route_id || r.route_id === nm.frontier_ref);
    const type = MOVE_TYPES.includes(nm.output) ? nm.output : 'NONE';
    nextmove = { type, title: type === 'ACTION' || type === 'NONE' ? step : '', path_id: route ? route.path_id : null, path_affiliation: route ? 'derived' : 'none', source: 'routes.next_move' };
  } else if (step) {
    nextmove = { type: 'ACTION', title: step, path_id: null, path_affiliation: 'none', source: 'plan' };
  }

  /* State block: the explanation layer's own words when the server wrote them, else the engine's sentences. */
  /* Presentation boundary only: strip the ALL-CAPS section labels the diagnosis prompt mandates (with or
     without a trailing colon — the engine sometimes drops it mid-sentence) and the "(1)/(2)" structure
     markers at sentence starts. Markers INSIDE a sentence can be the user's own quoted words and are
     never touched. */
  const whereFull = userFacing(diag.where_you_are)
    .replace(/\b[A-ZÀ-Ý]{3,}(?: [A-ZÀ-Ý]{2,})+(?: \([^)]*\))?:\s*/g, '')
    .replace(/\bWHAT WE DON'T(?: KNOW YET)?|\bWHAT WE KNOW\b\s*:?\s*/g, '')
    .replace(/(^|[.!?]\s+)\(\d+\)\s*/g, '$1');
  const headFull = userFacing(diag.primary_constraint);
  const whyFull = userFacing((diag.why || [])[0] || '');
  const first = (whyFull.match(/^[^.!?]+[.!?]/) || [whyFull])[0];
  const dd = diag.do_not_detail || {};
  const dnText = userFacing(dd.text || String(diag.do_not || '').replace(/^.*?—\s*[^—]*?—\s*/, ''));
  const seen = new Set();
  const factLines = facts.filter(e => { const k = brief(userFacing(e.signal), 60); if (seen.has(k)) return false; seen.add(k); return true; })
    .slice(0, 4).map(e => brief(userFacing(e.signal), 110));
  const windowDays = Number(diag.reassess_window_days) || 0;
  const state = {
    where_you_are: has('summary') ? ex.summary.join(' ') : whereFull,
    /* Structured paragraphs kept whole for the State reader: the explanation layer authors 1-3 real
       paragraphs and the list survives to the client; where_you_are stays flat for existing consumers. */
    where_you_are_paras: has('summary')
      ? ex.summary.map(s => String(s || '').trim()).filter(Boolean)
      : (whereFull ? [whereFull] : []),
    blocking: has('blocking_title') ? ex.blocking_title : headFull,
    blocking_body: has('blocking_title') ? String(ex.blocking_body || '') : userFacing(whyFull.slice(first.length).trim()),
    why_we_think_so: has('why') ? ex.why.slice() : factLines,
    what_not_to_do: (has('hold_title') ? ex.hold_title : dnText) ? [has('hold_title') ? ex.hold_title : dnText] : [],
    what_not_to_do_note: has('hold_title') ? String(ex.hold_body || '') : userFacing(dd.reason || ''),
    what_not_to_do_until: userFacing(dd.unlock_condition || dd.until || ''),
    next_best_action: has('do_title') ? ex.do_title : step,
    next_best_why: has('do_title') ? String(ex.do_why || '') : '',
    know_right_when: has('done_when') ? ex.done_when : userFacing(diag.success_metric || diag.well_know_when || ''),
    when_to_reassess: windowDays ? `We look at this again in about ${windowDays} days. Your state is rebuilt from what you report.` : '',
    uncertain: gaps.map(e => brief(userFacing(e.signal), 110)),
    changed: [],
    provisional: diag.status === 'provisional' || diag.confidence_band === 'LOW'
  };

  /* Zero paths: the engine's own reason (generator.UNRESOLVED_TEXT), or the artifact is LEGACY. */
  let zero = null;
  if (!paths.length) {
    if (legacy) zero = { kind: 'LEGACY_ARTIFACT', detail: snapText(((legacy.i18n || {})[UI_LANG] || {}).detail) || String(legacy.detail || ''), missing: [] };
    else if (!navOk && !diagOk) zero = { kind: 'EVALUATION_UNAVAILABLE', detail: '', missing: [] };
    else {
      const un = (diag.possible_paths && diag.possible_paths.unresolved) || (ready && ready.unresolved) || [];
      const conflict = ((ready && ready.emerging) || []).some(e => e.state === 'CONFLICT');
      const u = un[0];
      zero = {
        kind: conflict && !u ? 'EVIDENCE_CONFLICT' : (u ? (SNAP_ZERO[u.code] || 'NO_APPLICABLE_PATH') : 'NO_APPLICABLE_PATH'),
        goal_code: u && u.goal_code ? u.goal_code : null,
        goal_blocking: u && u.goal_blocking ? u.goal_blocking : [],
        detail: u ? snapText(((u.i18n || {})[UI_LANG] || {}).detail) : '',
        missing: u ? (u.missing_detail || []).map(m => snapText(((m.i18n || {})[UI_LANG] || {}).reason)).filter(Boolean) : []
      };
    }
  }
  /* R2: canonical Maps projection (server, dok 03) travels with the snapshot. The
     2D map reads its RouteNodes from here (one source for every renderer); null when
     /routes produced none (anonymous/legacy/no path) — the map then draws the path
     from its own checks, as before. */
  return { goal, paths, overflow: 0, state, evidence, nextmove, zero, emerging: navOk ? ((ready && ready.emerging) || []) : [],
    maps_projection: (src.routes && src.routes.maps_projection) || null,
    /* V4 section 4: the version-bound read model travels with the snapshot so every surface and
       every test can compare the SAME projection_revision and inspect the typed graph sources. */
    experience: src.experience || null };
}
/* The same snapshot from what the page already holds (LIVE keeps the last answer of each endpoint). */
function liveSnapshotSource() {
  return { state: LIVE.state, diag: LIVE.artifact, ready: LIVE.projection, evidence: { evidence: LIVE.evidence }, journey: LIVE.journey,
    workspace: LIVE.workspace, routes: LIVE.routes, experience: LIVE.experience,
    overrides: LIVE.overrides, explain: LIVE.explainState === 'ready' ? LIVE.explain : null, nav: LIVE.nav ? { move: LIVE.nav.move, current: LIVE.nav.current || null } : null,
    goalOverride: LIVE.goalOverride, horizonOverride: LIVE.horizonOverride };
}
function liveSnapshot() { return LIVE.artifact ? snapshotFromPayloads(liveSnapshotSource()) : snapEmpty(); }
/* D2: buildSnapshot(sid) asks the endpoints and composes the snapshot. The page keeps the same payloads in LIVE, so a
   test can ask for both and compare: there is one adapter and one contract. */
async function buildSnapshot(sid) {
  const get = (fn) => fn().catch(() => null);
  const [state, diag] = await Promise.all([get(() => API.state(sid)), get(() => API.diagnosis(sid))]);
  if (!diag) return snapEmpty();
  const [ready, evidence, nav, journey, experience] = await Promise.all([
    get(() => API.readiness(sid)), get(() => API.evidence(sid)), get(() => API.navigation(sid)),
    state && state.journey_ok ? get(() => API.journey(sid)) : Promise.resolve(null),
    get(() => API.experience(sid))]);
  const same = sid === LIVE.sid;
  return snapshotFromPayloads({ state, diag, ready, evidence, nav, journey, experience,
    workspace: same ? LIVE.workspace : null, routes: same ? LIVE.routes : null, overrides: same ? LIVE.overrides : [], explain: same && LIVE.explainState === 'ready' ? LIVE.explain : null,
    goalOverride: same ? LIVE.goalOverride : 0, horizonOverride: same ? LIVE.horizonOverride : 0 });
}

/* The seam every v11 renderer reads (and tests write): live reads the adapter, demo reads the prototype's fixtures. */
const V11_ENGINE = {
  snaps: {},
  snapshot(key) {
    if (!IS_DEMO) return this.injected && this.injected.sid === LIVE.sid ? this.injected.snap : liveSnapshot();
    const k = key || STORE.currentPersona || 'dimas';
    if (!this.snaps[k]) this.snaps[k] = engineSeedSnapshot(k);
    return this.snaps[k];
  },
  /* Tests and demos put a snapshot in place. Live: for the open map only, until the next load. */
  set(key, snap) { if (IS_DEMO) this.snaps[key] = snap; else this.injected = snap ? { sid: LIVE.sid, snap } : null; },
  clear() { this.injected = null; this.snaps = {}; },
  apply(key, update) {
    if (!IS_DEMO) return this.snapshot();
    const k = key || STORE.currentPersona || 'dimas';
    this.snaps[k] = engineApplyUpdate(this.snapshot(k), update);
    return this.snaps[k];
  }
};
/* A path of the snapshot in the shape present-cap.js knows ({ key, status }), and back. One policy, one implementation. */
function presentSnapshotPaths(paths, opts) {
  const list = (paths || []).map(p => ({ key: p.id, status: SNAP_STATUS_KEY[p.status_display] || 'NOT_YET', p }));
  const pres = presentPaths(list, opts);
  return { visible: pres.visible.map(x => x.p), hidden: pres.hidden.map(x => x.p), total: pres.total, cap: pres.cap };
}
const SNAP_STATUS_KEY = { OPEN: 'OPEN', 'TEST FIRST': 'TEST_FIRST', 'NOT YET': 'NOT_YET', STOP: 'STOP' };
