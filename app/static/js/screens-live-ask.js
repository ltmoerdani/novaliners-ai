/* LIVE screen 19 (Ask). Same template as the demo (renderAskLayout); the answers come from POST /session/{sid}/ask, which is
 * grounded in this map's diagnosis and paths and checked by the plain-language guard. The conversation is kept in this browser,
 * one thread per session (a new cycle starts a new thread). Nothing here changes the diagnosis: "Update my diagnosis" opens the
 * follow-up cycle, where what happened is reported. internal-docs §4. */
const LS_ASK = 'novaliners-ask';
const ASK_KEEP = 40;   // messages kept per thread

function askStore() { return lsGet(LS_ASK, {}) || {}; }
function liveAskThread() {
  if (LIVE.askSid !== LIVE.sid) { LIVE.askSid = LIVE.sid; LIVE.askThread = (askStore()[LIVE.sid] || []).slice(); LIVE.askThinking = false; }
  return LIVE.askThread;
}
/* NC-R9: at most one REASSESS_PREVIEW row is kept — the newest. A preview is a read, not a record
   change, so repeated explicit previews must not pile up permanent copies in the thread. Rows written
   by older builds carry no kind and are left alone; a user-authored row is never dropped. */
function askKeepNewestPreview(list) {
  let newest = -1;
  for (let i = list.length - 1; i >= 0; i--) {
    if (list[i] && list[i].kind === 'REASSESS_PREVIEW') { newest = i; break; }
  }
  if (newest < 0) return list;
  return list.filter((m, i) => !(m && m.kind === 'REASSESS_PREVIEW') || i === newest);
}
function askSaveThread() {
  const all = askStore();
  all[LIVE.sid] = askKeepNewestPreview(LIVE.askThread.filter(m => m.role !== 'error')).slice(-ASK_KEEP);
  const sids = Object.keys(all);
  if (sids.length > 12) sids.slice(0, sids.length - 12).forEach(k => { delete all[k]; });   // keep the last 12 maps' threads
  lsSet(LS_ASK, all);
}

function liveAskFocus() {
  const key = STORE.askFocus;
  const p = key && livePathModels().find(x => x.key === key);
  return p || null;
}

/* Questions offered when the thread is empty, or after an answer that brought no follow-ups of its own */
function liveAskStarters() {
  const focus = liveAskFocus();
  if (focus) return [`What do I still have to get for ${focus.name}?`, 'Which of these should I do first?', `Is ${focus.name} worth it for me right now?`];
  const other = livePathModels().find(p => p.status !== 'OPEN');
  return ['Why is this what is holding me back?', 'What if I skip the first step?',
    other ? `What would open ${other.name}?` : 'Which path should I take?', 'What do you still not know about me?'];
}

function liveAskView() {
  const d = LIVE.artifact;
  const rs = useRoadmapStore.getState();
  const th = liveAskThread();
  const last = th.length ? th[th.length - 1] : null;
  const chips = LIVE.askThinking ? [] : (last && last.role === 'bot' ? (last.next || []) : (th.length ? [] : liveAskStarters()));
  LIVE.askChips = chips;
  const ex = LIVE.explain || {};
  const v = liveVerdict();
  const blocker = String(ex.blocking_title || '').trim() || gist(userFacing(d.primary_constraint) || v.line, 150).short;
  const step = rs.steps[rs.currentStep - 1];
  const focus = liveAskFocus();
  return {
    thread: th.map(m => ({ role: m.role, text: esc(m.text) })),
    chips: chips.map(esc), thinking: !!LIVE.askThinking,
    focus: focus ? { name: esc(focus.name) } : null, draft: esc(STORE.askDraft || ''),
    verdict: `<span class="status-pill" style="background:var(--ink);color:var(--on-ink)">${esc(v.pill)}</span> <span style="font-size:13px;color:var(--ink-3)">${esc(bandWord(d.confidence_band))}</span>`,
    blocker: esc(blocker),
    nextStep: esc(step ? (step.label || step.title) : 'Report what happened'),
    canUpdate: true, h: { send: 'askSendLive', chip: 'askPickChipLive', update: 'askUpdateLive' }
  };
}

function askPickChipLive(i) {
  const q = (LIVE.askChips || [])[i];
  if (q) askSubmitLive(q);
}
function askSendLive(e) {
  if (e && e.preventDefault) e.preventDefault();
  const box = document.getElementById('ask-input');
  const q = box ? box.value.trim() : '';
  if (q && !LIVE.askThinking) askSubmitLive(q);
}

async function askSubmitLive(q) {
  if (!LIVE.sid || LIVE.askThinking) return;
  const th = liveAskThread();
  const sid = LIVE.sid;
  const focus = liveAskFocus();
  const history = th.filter(m => m.role !== 'error').slice(-6).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', text: m.text }));
  th.push({ role: 'user', text: q });
  STORE.askDraft = '';
  LIVE.askThinking = true;
  askRedraw();
  try {
    const r = await API.ask(sid, { question: q, history, focus: focus ? focus.name : '' });
    if (LIVE.sid !== sid) return;
    th.push({ role: 'bot', text: String(r.answer || '').trim(), next: (r.follow_ups || []).slice(0, 3) });
    askSaveThread();
  } catch (err) {
    if (LIVE.sid !== sid) return;
    th.pop();                                  // the question goes back into the box: nothing is lost
    STORE.askDraft = q;
    th.push({ role: 'error', text: 'That did not go through: ' + err.message + ' Your question is back in the box.' });
  } finally {
    if (LIVE.sid === sid) LIVE.askThinking = false;
  }
  if (LIVE.sid === sid) askRedraw();
}

/* Redraw the page, keep the reader at the newest message and the cursor in the box */
function askRedraw() {
  if (STORE.currentScreen !== 'talk') return;
  renderScreen('19');
}

function askUpdateLive() { startFollowUpFlow(); }


/* ==========================================================================
   V11 TALK (record P5e; int 10 §6.5). Ask a question about your map, or say what changed. The answers come from the real
   conversation endpoint (POST /session/{sid}/ask, grounded in this map's diagnosis and paths, checked by the plain-language
   guard); nothing is echoed or invented here. A question never changes the record: when something changed, "Update my
   diagnosis" opens the follow-up where it is reported. What you type is shown exactly as you typed it, in your own
   language; the replies are English (record D1). Before a diagnosis exists, Talk is the interview (screen 02).
   ========================================================================== */
const TALK_MAX = 2000;
const TALK_DEMO_FIRST = 'Received. This demo has no engine behind it. Your message is shown here only. It was not analyzed, not saved to your record, and not used to change any path, so nothing on your State, Maps, Moves or Journey has changed.';
const TALK_DEMO_NEXT = 'Received. Shown here only. Nothing on your record has changed.';
function talkKey() { return IS_DEMO ? (STORE.currentPersona || 'dimas') : LIVE.sid; }
/* The conversation of the open map: live, the thread kept per session; demo, a page-only log per sample workspace. */
function talkThread() {
  if (!IS_DEMO) return liveAskThread();
  STORE.talkLogs = STORE.talkLogs || {};
  return (STORE.talkLogs[talkKey()] = STORE.talkLogs[talkKey()] || []);
}
function talkDraft() { return STORE.askDraft || ''; }
function talkAbout() { return STORE.talkAbout || null; }
function talkMsgHtml(m) {
  if (m.role === 'user') return `
            <div class="talk-msg is-mine">
              <div class="talk-meta"><span class="talk-who">You</span></div>
              <div class="talk-bubble">${stratEsc(m.text)}</div>
            </div>`;
  if (m.role === 'error') return `
            <div class="talk-msg is-error" role="alert">
              <div class="talk-meta"><span>Novaliners</span></div>
              <div class="talk-body">${stratEsc(m.text)}</div>
            </div>`;
  return `
            <div class="talk-msg"${m.kind ? ` data-kind="${stratEsc(String(m.kind))}"` : ''}>
              <div class="talk-meta"><span>Novaliners</span></div>
              <div class="talk-body">${stratEsc(m.text)}</div>
            </div>`;
}
function talkOpeningHtml() {
  const snap = V11_ENGINE.snapshot();
  const move = snap.nextmove && snap.nextmove.title ? snap.nextmove.title : null;
  const about = talkAbout();
  return `
            <div class="talk-msg">
              <div class="talk-meta"><span>Novaliners</span></div>
              <div class="talk-body">Ask about your State, your map or your next move.${about ? ` You opened this from “${stratEsc(about.title)}”, so that is the context for what you write.` : ''}${move ? ` The move on your State is “${stratEsc(String(move).replace(/[.。]+$/, ''))}”.` : ''}
                <br><br>A question never changes your record. If something changed, say so here, then use “Update my diagnosis” to record it.</div>
            </div>`;
}
function talkChipsHtml() {
  if (LIVE.askThinking) return '';
  const th = talkThread();
  const last = th.length ? th[th.length - 1] : null;
  const chips = last && last.role === 'bot' ? (last.next || []) : (th.length ? [] : liveAskStarters());
  LIVE.askChips = chips;
  return chips.length ? `<div class="ask-chips talk-chips" role="group" aria-label="Suggested questions">${chips.map((q, i) => `<button type="button" class="ask-chip" onclick="talkPickChip(${i})"><svg class="cw-rel-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4v7a4 4 0 0 0 4 4h11"/><path d="m15 10 5 5-5 5"/></svg><span>${stratEsc(q)}</span></button>`).join('')}</div>` : '';
}
function talkPathsHtml(snap) {
  const act = mapsActive(snap);
  const pres = presentSnapshotPaths(snap.paths, { pinned: [act && act.id] });
  if (!snap.paths.length) return '<p class="mp-p">No path is shown for this map yet.</p>';
  return `<div class="talk-paths-wrap">
          <div class="dest-routes talk-paths">${pres.visible.map(p => `<button type="button" class="dest-route" onclick="openMapsAt('${esc(p.id)}')"><span>${stratEsc(p.title)}${act && act.id === p.id ? ' <span class="mp-tag">In focus</span>' : ''}</span><span class="dest-route-state ${mapsKey(p.status_display)}">${stratEsc(mapsStateWord(p))}</span></button>`).join('')}</div>
          ${pres.hidden.length ? `<p class="mp-fine">+${pres.hidden.length} more possibilit${pres.hidden.length === 1 ? 'y' : 'ies'} on your map. <button type="button" class="v11-textlink" onclick="goDestination('maps')">Open Maps</button></p>` : ''}
          <p class="mp-fine">In no particular order. Open a path to see it in Maps.</p></div>`;
}
function talkFactsHtml(snap) {
  const ev = snap.evidence || [];
  return `
        <div class="chat-side-body">
        <p class="evp-intro">What is on record for this map. Questions asked here are not added to it.</p>
        ${ev.length ? ev.map(e => `<div class="card-clean evp-card is-plain">
              <div class="evp-fact">“${stratEsc(e.quote)}”${e.disputed ? ' <span class="v11-disputed-badge">DISPUTED</span>' : ''}</div>
              <div class="evp-meta"><span class="evp-src"><span class="evp-src-dot"></span> ${stratEsc(e.source)}</span></div>
            </div>`).join('') : '<p class="mp-p">Nothing is on record yet.</p>'}
        </div>`;
}
/* The context rail: the same fold as the other inspectors (the ws-panel helpers). It docks on the split
   frame (>=1001px) and stays folded below it; an explicit close (the specs, live flows) wins over the fold. */
function talkSideOpen() {
  if (STORE.chatEvidenceOpen === false) return false;   // an explicit close is honoured
  if (STORE.talkSideClosed !== undefined) return !STORE.talkSideClosed;
  return window.innerWidth >= 1001;                     // the docked rail is open on the split frame
}
function setTalkSide(open) {
  STORE.talkSideClosed = !open;
  STORE.chatEvidenceOpen = open;                        // one truth for the older readers of this key
  STORE.restoreFocus = '.talk-side-toggle';
  renderScreen('talk');
  requestAnimationFrame(wsPanelMarkEnter);
}
function screenTalk11() {
  const snap = V11_ENGINE.snapshot();
  const th = talkThread();
  const panelOpen = talkSideOpen();
  const tab = STORE.chatPanelTab === 'facts' ? 'facts' : 'map';
  const about = talkAbout();
  if (about && !IS_DEMO) STORE.askFocus = about.id;
  const thinking = !!LIVE.askThinking;
  const messages = th.map(talkMsgHtml).join('') + (thinking ? `<div class="talk-msg" role="status"><div class="talk-meta"><span>Novaliners</span></div><div class="talk-body"><span class="think-dots"><i></i><i></i><i></i></span> Thinking it through…</div></div>` : '');
  const content = `
  <div class="tk-page">
    ${panelOpen ? '' : wsPanelShowBtn('talk-side-toggle', 'tk-side', 'setTalkSide', 'context')}
    <div class="tk-grid${panelOpen ? '' : ' is-collapsed'}">
      <section class="tk-chat" aria-label="Conversation">
        <div id="chat-messages-container" class="talk-log" tabindex="0" role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation">
          <header class="tk-head cw-intro">
            <h1 class="sr-only">Talk</h1>
            <div class="talk-head-meta">
              <div class="talk-head-chip" title="${IS_DEMO ? 'Demo: no engine is connected, and messages stay on this page' : 'Answers come from your State and your map. A question never changes your record.'}">
                <span class="talk-chip-dot"></span>
                <span class="talk-head-chip-text">${IS_DEMO ? 'Demo · messages stay on this page' : 'Grounded in your state'}</span>
              </div>
              ${about ? `<div class="talk-about-chip" title="Talking about this path, from your map"><span class="talk-about-k">ABOUT</span><span class="talk-about-t">${stratEsc(about.title)}</span></div>` : ''}
            </div>
          </header>
          <div class="talk-stream">
            ${talkOpeningHtml()}
            ${messages}
            ${talkChipsHtml()}
          </div>
        </div>
        <div class="talk-composer">
          <div class="talk-composer-inner">
            <div class="talk-inputbox">
              <textarea id="talk-ongoing-input" class="talk-input" rows="1" aria-label="Your message" aria-describedby="talk-hint talk-error" placeholder="${about ? 'Ask about “' + stratEsc(about.title) + '”, or say what changed' : 'Ask a question, or say what changed'}…" oninput="talkDraftInput(this)" onkeydown="if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();sendTalkMessage();}">${stratEsc(talkDraft())}</textarea>
              <div class="talk-composer-foot">
                <span class="talk-composer-note" id="talk-hint">Enter to send · Shift+Enter for a new line${IS_DEMO ? ' · Demo: messages stay on this page' : ` · <button type="button" class="chat-gap-btn" onclick="askUpdateLive()">Update my diagnosis</button>`}</span>
                <button type="button" class="btn-primary talk-send" onclick="sendTalkMessage()" aria-label="Send message" title="Send message"${thinking ? ' disabled' : ''}>↑</button>
              </div>
            </div>
            <p class="talk-error" id="talk-error" role="alert" hidden></p>
          </div>
        </div>
      </section>
      ${panelOpen ? `
      <aside class="tk-side has-panel-hide" id="tk-side" aria-label="Context for this conversation">
        ${wsPanelHideBtn('talk-side-toggle', 'tk-side', 'setTalkSide', 'context')}
        <div class="tk-rail-head">
          <span class="tk-k">Context on demand</span>
          <div class="chat-tabs" role="tablist">
            <button type="button" role="tab" class="${tab === 'map' ? 'active' : ''}" onclick="setChatPanelTab('map')">Your map</button>
            <button type="button" role="tab" class="${tab === 'facts' ? 'active' : ''}" onclick="setChatPanelTab('facts')">What we know · ${(snap.evidence || []).length}</button>
          </div>
        </div>
        <div class="tk-rail">
          ${tab === 'map' ? `<div class="chat-side-body is-map"><p class="chat-map-caption">Your paths as they stand now. Questions do not change them.</p>${talkPathsHtml(snap)}</div>` : talkFactsHtml(snap)}
        </div>
      </aside>` : ''}
    </div>
  </div>`;
  return renderAppShell('talk', 'Talk', content);
}
function talkSetError(msg) {
  const ta = document.getElementById('talk-ongoing-input'), er = document.getElementById('talk-error');
  if (er) { er.textContent = msg || ''; er.hidden = !msg; }
  if (ta) { if (msg) ta.setAttribute('aria-invalid', 'true'); else ta.removeAttribute('aria-invalid'); }
}
/* The composer grows with what is typed, up to its cap, then the box scrolls; if the conversation was at
   its newest message it stays there while the composer takes the room (ported from the prototype's autogrow). */
function talkAutoGrow(ta) {
  if (!ta || !ta.classList.contains('talk-input')) return;
  const log = document.getElementById('chat-messages-container');
  const pinned = log && (log.scrollHeight - log.scrollTop - log.clientHeight) < 40;
  ta.style.height = 'auto';
  const max = parseFloat(getComputedStyle(ta).maxHeight) || 220;
  ta.style.height = Math.min(ta.scrollHeight + 2, max) + 'px';
  ta.style.overflowY = ta.scrollHeight + 2 > max ? 'auto' : 'hidden';
  if (pinned && log) log.scrollTop = log.scrollHeight;
}
function talkDraftInput(ta) {
  STORE.askDraft = ta.value;
  if (LIVE.pendingTalkOp) LIVE.pendingTalkOp = '';   // edited text is a NEW operation: never reuse a key
  talkAutoGrow(ta);
  if (ta.getAttribute('aria-invalid')) talkSetError('');
}
/* Append only what is new, so a live-region reader announces the new messages and not the whole transcript again. */
function talkAppend(html) {
  const stream = document.querySelector('#chat-messages-container .talk-stream');
  if (!stream) return;
  stream.insertAdjacentHTML('beforeend', html);
  const el = document.getElementById('chat-messages-container');
  if (el) el.scrollTop = el.scrollHeight;
}
function sendTalkMessage() {
  const ta = document.getElementById('talk-ongoing-input');
  if (!ta || LIVE.askThinking) return;
  const text = ta.value.trim();
  if (!text) { talkSetError('Write a message first. An empty message is not sent.'); ta.focus(); return; }
  if (text.length > TALK_MAX) {
    talkSetError(`This message is ${text.length.toLocaleString('en-US')} characters long and the limit is ${TALK_MAX.toLocaleString('en-US')}. It was not sent. Your text is still in the box: shorten it and send again.`);
    ta.focus(); return;
  }
  talkSetError('');
  talkSubmit(text);
}
async function talkSubmit(q) {
  const sid = IS_DEMO ? 'demo' : LIVE.sid;
  if (!sid || LIVE.askThinking) return;
  const th = talkThread();
  const focus = IS_DEMO ? null : liveAskFocus();
  const history = th.filter(m => m.role !== 'error').slice(-6).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', text: m.text }));
  th.push({ role: 'user', text: q });
  STORE.askDraft = '';
  const ta = document.getElementById('talk-ongoing-input');
  if (ta) { ta.value = ''; ta.style.height = 'auto'; ta.style.overflowY = 'hidden'; }
  LIVE.askThinking = true;
  document.querySelectorAll('.talk-chips').forEach(c => c.remove());
  talkAppend(talkMsgHtml({ role: 'user', text: q }) + '<div class="talk-msg" id="talk-thinking" role="status"><div class="talk-meta"><span>Novaliners</span></div><div class="talk-body"><span class="think-dots"><i></i><i></i><i></i></span> Thinking it through…</div></div>');
  const send = document.querySelector('.talk-send'); if (send) send.disabled = true;
  let reply = null;
  const here = () => IS_DEMO || LIVE.sid === sid;
  try {
    if (IS_DEMO) {
      /* no engine behind the demo: say so, and keep the message on this page only */
      reply = { role: 'bot', text: th.filter(m => m.role === 'user').length > 1 ? TALK_DEMO_NEXT : TALK_DEMO_FIRST, next: [] };
      th.push(reply);
    } else if (talkMode() === 'update') {
      /* Report a change / outcome: the ONLY branch that writes (POST /message, semantic path). The
         operation key is kept across a failed attempt so a retry replays the accepted event instead
         of recording it twice; a hypothetical question can never reach this branch. */
      const opId = LIVE.pendingTalkOp || (LIVE.pendingTalkOp = newOperationId('talk'));
      /* C52: when the person opened "Report outcome" for the presented canonical Move, the message is
         tied to that stable move_ref, so the outcome lands on the Move (and MAPS/JOURNEY), not as a
         free-floating fact. A foreign/stale move is rejected server-side (409). */
      const moveRef = LIVE.talkMoveId || '';
      const r = await API.message(sid, q, opId, moveRef || undefined);
      LIVE.pendingTalkOp = '';
      LIVE.talkMoveId = '';
      reply = { role: 'bot', text: talkUpdateAck(r), next: [] };
      if (here()) {
        th.push(reply); askSaveThread();
        // P0-01/NC-02: an acknowledged change must not leave stale Facts or MAPS visible. Refresh
        // every destination through ONE version-checked boundary; the flag records a failed READ
        // without ever re-sending the accepted mutation.
        await liveRefreshAfterMutation();
      }
    } else {
      const r = await API.ask(sid, { question: q, history, focus: focus ? focus.name : '' });
      reply = { role: 'bot', text: String(r.answer || '').trim(), next: (r.follow_ups || []).slice(0, 3) };
      if (here()) { th.push(reply); askSaveThread(); }
    }
  } catch (err) {
    if (here()) {
      th.pop();                                  // the question goes back into the box: nothing is lost
      STORE.askDraft = q;
      reply = { role: 'error', text: 'That did not go through: ' + err.message + ' Your message is back in the box.' };
      th.push(reply);
    }
  } finally {
    if (here()) LIVE.askThinking = false;
  }
  if (!here()) return;
  const think = document.getElementById('talk-thinking'); if (think) think.remove();
  if (reply) talkAppend(talkMsgHtml(reply));
  const box = document.getElementById('talk-ongoing-input');
  if (box) { if (reply && reply.role === 'error') box.value = q; box.focus(); }
  if (send) send.disabled = false;
  if (reply && reply.role === 'bot' && reply.next.length) { LIVE.askChips = reply.next; talkAppend(talkChipsHtml()); }
  // An accepted factual update changed the record: redraw TALK from the same revision so the facts
  // panel is not a stale snapshot (the reply is in the thread, so nothing is duplicated).
  if (reply && reply.role === 'bot' && talkMode() === 'update') renderScreenKeepingUi('talk');
}
/* A suggested question is sent as a message of the person's own choosing, through the same path */
function talkPickChip(i) {
  const q = (LIVE.askChips || [])[i];
  if (q) talkSubmit(q);
}
function talkAfterRender() {
  const el = document.getElementById('chat-messages-container');
  if (el) el.scrollTop = el.scrollHeight;
  const box = document.getElementById('talk-ongoing-input');
  if (box) { talkAutoGrow(box); if (!LIVE.askThinking && talkThread().length) box.focus({ preventScroll: true }); }
  talkEnsureIntent();
}

/* ── Ask vs Report a change (V4 §4 / C50–C53; audit D-01) ─────────────────────────────────────────
   One composer, two explicit intents. "Ask" is read-only: it answers from the current record and
   commits nothing. "Report a change" is the only branch that writes, through POST /message, so a
   speculative question can never leak into a semantic claim. */
function talkMode() { return STORE.talkMode === 'update' ? 'update' : 'ask'; }
function talkSetMode(m) {
  STORE.talkMode = (m === 'update') ? 'update' : 'ask';
  LIVE.pendingTalkOp = '';
  if (talkMode() !== 'update') LIVE.talkMoveId = '';
  STORE.restoreFocus = talkMode() === 'update' ? '.talk-intent-update' : '.talk-intent-ask';
  renderScreen('talk');
}
/* The canonical Move the server is presenting right now (stable id from the presented decision).
   A plan step or a route frontier alone is NOT a canonical Move, so no move_ref is invented. */
function talkCurrentMove() {
  const nm = (typeof V11_ENGINE !== 'undefined' && V11_ENGINE.snapshot) ? (V11_ENGINE.snapshot().nextmove || {}) : {};
  return (nm && nm.move_id) ? { moveId: nm.move_id, title: nm.title || '' } : null;
}
/* C43: mark the canonical Move EXECUTED (durable, idempotent, execution != proof). */
async function talkMarkMoveDone() {
  const mv = talkCurrentMove();
  if (!mv || LIVE.askThinking) return;
  const sid = LIVE.sid;
  const th = talkThread();
  LIVE.askThinking = true;
  LIVE.pendingMoveOps = LIVE.pendingMoveOps || {};
  const key = LIVE.pendingMoveOps[mv.moveId] || (LIVE.pendingMoveOps[mv.moveId] = newOperationId('mv'));
  talkAppend('<div class="talk-msg" id="talk-thinking" role="status"><div class="talk-meta"><span>Novaliners</span></div><div class="talk-body"><span class="think-dots"><i></i><i></i><i></i></span> Recording the move...</div></div>');
  let reply = null;
  try {
    await API.moveEventOp(sid, mv.moveId, 'EXECUTED', '', key);
    delete LIVE.pendingMoveOps[mv.moveId];
    reply = { role: 'bot', text: 'Recorded: this move is marked done. That is execution, not proof. Report what happened and the outcome stays a separate, evidence-checked step.', next: [] };
    th.push(reply); askSaveThread();
    if (LIVE.sid === sid) await liveRefreshAfterMutation();   // P0-01/NC-02: one boundary, honest on failure
  } catch (e) {
    if (LIVE.sid !== sid) return;
    reply = { role: 'error', text: 'Could not record that: ' + e.message };
    th.push(reply);
  } finally {
    if (LIVE.sid === sid) LIVE.askThinking = false;
  }
  if (LIVE.sid !== sid) return;
  const think = document.getElementById('talk-thinking'); if (think) think.remove();
  if (reply) talkAppend(talkMsgHtml(reply));
}
/* C52: the next message is the outcome of the presented Move. */
function talkMoveOutcome() {
  const mv = talkCurrentMove();
  if (!mv) return;
  LIVE.talkMoveId = mv.moveId;
  STORE.talkMode = 'update';
  STORE.restoreFocus = '#talk-ongoing-input';
  renderScreen('talk');
}
function talkIntentHtml() {
  const m = talkMode();
  function btn(mode, cls, label) {
    const on = (m === mode);
    return '<button type="button" class="' + cls + (on ? ' is-on' : '') + '" aria-pressed="' + (on ? 'true' : 'false') + '" '
      + 'style="font:inherit;font-size:12px;font-weight:600;padding:5px 11px;border-radius:999px;border:1px solid var(--line,#d8d8d8);'
      + 'background:' + (on ? 'var(--ink,#111)' : 'transparent') + ';color:' + (on ? 'var(--on-ink,#fff)' : 'inherit') + ';cursor:pointer" '
      + 'onclick="talkSetMode(\'' + mode + '\')">' + label + '</button>';
  }
  const mv = talkCurrentMove();
  const mvHtml = mv ? '<div class="talk-move" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0 0;font-size:12px">'
    + '<span style="color:var(--ink-3,#666)">Current move:</span><b>' + esc(mv.title || mv.moveId) + '</b>'
    + '<button type="button" style="font:inherit;font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid var(--line,#d8d8d8);background:transparent;color:inherit;cursor:pointer" onclick="talkMarkMoveDone()">Mark done</button>'
    + '<button type="button" style="font:inherit;font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid var(--line,#d8d8d8);background:transparent;color:inherit;cursor:pointer" onclick="talkMoveOutcome()">Report outcome</button>'
    + (LIVE.talkMoveId === mv.moveId ? '<span style="color:var(--ink-2,#444)">The next message reports this move\'s outcome.</span>' : '')
    + '</div>' : '';
  return '<div class="talk-intent" role="group" aria-label="What this message does" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0 2px">'
    + btn('ask', 'talk-intent-ask', 'Ask')
    + btn('update', 'talk-intent-update', 'Report a change')
    + '<button type="button" class="talk-preview-btn" style="font:inherit;font-size:12px;padding:5px 11px;border-radius:999px;border:1px dashed var(--line,#d8d8d8);background:transparent;color:inherit;cursor:pointer" '
    + 'onclick="talkPreviewChanges()" title="Read-only: what changed since your last checkpoint. Nothing is saved.">What changed?</button>'
    + '<button type="button" class="talk-sources-btn" style="font:inherit;font-size:12px;padding:5px 11px;border-radius:999px;border:1px dashed var(--line,#d8d8d8);background:transparent;color:inherit;cursor:pointer" '
    + 'onclick="talkGraphSources()" title="Read-only: the node/edge sources behind your map, including what was rejected.">Map sources</button>'
    + '<span style="font-size:12px;color:var(--ink-3,#666)">'
    + (m === 'update' ? 'Writes to your record' : 'Read-only answer') + '</span></div>' + mvHtml;
}
function talkEnsureIntent() {
  const host = document.querySelector('.talk-composer-inner');
  if (!host || document.getElementById('talk-intent')) return;
  const wrap = document.createElement('div');
  wrap.id = 'talk-intent';
  wrap.innerHTML = talkIntentHtml();
  host.insertBefore(wrap, host.firstChild);
}
/* Graph sources in TALK (C07 "graph sources inspectable"): a READ-ONLY listing of the typed nodes,
   edges, DECLARED causal links and every relation the engine REFUSED to draw, with its reason. It
   never ranks, never invents an edge and never promotes an example into a live claim. */
function talkGraphSourcesText(exp) {
  const g = (exp && exp.graph) || null;
  if (!g) return 'No graph is available for this map yet.';
  const count = (arr, key) => { const m = {}; (arr || []).forEach(x => { m[x[key]] = (m[x[key]] || 0) + 1; }); return m; };
  const nk = count(g.nodes, 'kind'), ek = count(g.edges, 'kind');
  const bits = [];
  bits.push('Nodes: ' + (Object.keys(nk).length ? Object.keys(nk).sort().map(k => nk[k] + ' ' + k).join(', ') : 'none') + '.');
  bits.push('Edges: ' + (Object.keys(ek).length ? Object.keys(ek).sort().map(k => ek[k] + ' ' + k).join(', ') : 'none') + '.');
  const causal = (g.edges || []).filter(e => e.kind === 'BRANCH_FROM' || e.kind === 'MERGES_INTO');
  bits.push(causal.length
    ? 'Declared causal links: ' + causal.map(e => e.kind + ' ' + e.from_id + ' -> ' + e.to_id + (e.declaration_ref ? ' (' + e.declaration_ref + ')' : '')).join('; ') + '.'
    : 'No cross-route causal link is declared, so none is drawn.');
  const uns = g.unsupported_edges || [];
  bits.push(uns.length
    ? 'Not drawn, with reason: ' + uns.map(u => u.id + ' - ' + u.reason).join('; ') + '.'
    : 'Nothing was rejected as an invalid relation.');
  const cs = g.change_set || {};
  if (cs.no_material_change) {
    bits.push('Topology did not change in this revision.');
  } else {
    const bits2 = [];
    if ((cs.added || []).length) bits2.push('added ' + cs.added.slice(0, 6).join(', '));
    if ((cs.changed || []).length) bits2.push('changed ' + cs.changed.slice(0, 6).map(c => c.id + ' (' + (c.from || 'none') + ' -> ' + (c.to || 'none') + ')').join(', '));
    if ((cs.unlocked || []).length) bits2.push('unlocked ' + cs.unlocked.slice(0, 6).join(', '));
    if ((cs.closed || []).length) bits2.push('closed ' + cs.closed.slice(0, 6).join(', '));
    if ((cs.links_added || []).length) bits2.push('links added ' + cs.links_added.slice(0, 6).join(', '));
    if ((cs.links_retracted || []).length) bits2.push('links retracted ' + cs.links_retracted.slice(0, 6).join(', '));
    bits.push('Topology changed: ' + (bits2.length ? bits2.join('; ') : 'ids only') + '.');
  }
  const rev = (exp.revision || {}).projection_revision;
  if (rev) bits.push('Revision ' + rev + '.');
  bits.push('Sources only: no ranking, and no causal claim beyond a declared link.');
  return bits.join(' ');
}
async function talkGraphSources() {
  if (IS_DEMO || !LIVE.sid || LIVE.askThinking) return;
  const sid = LIVE.sid;
  const th = talkThread();
  LIVE.askThinking = true;
  talkAppend('<div class="talk-msg" id="talk-thinking" role="status"><div class="talk-meta"><span>Novaliners</span></div><div class="talk-body"><span class="think-dots"><i></i><i></i><i></i></span> Reading the graph sources...</div></div>');
  let reply = null;
  try {
    const exp = (LIVE.experience && LIVE.experience.session_id === sid) ? LIVE.experience : await API.experience(sid);
    if (LIVE.sid !== sid) return;
    reply = { role: 'bot', text: talkGraphSourcesText(exp), next: [] };
    th.push(reply); askSaveThread();
  } catch (e) {
    if (LIVE.sid !== sid) return;
    reply = { role: 'error', text: 'Could not read the graph sources: ' + e.message };
    th.push(reply);
  } finally {
    if (LIVE.sid === sid) LIVE.askThinking = false;
  }
  if (LIVE.sid !== sid) return;
  const think = document.getElementById('talk-thinking'); if (think) think.remove();
  if (reply) talkAppend(talkMsgHtml(reply));
}

/* MAP-06 Re-evaluate Preview in TALK (C08/D-11): a READ-ONLY deterministic read of what changed
   since the last checkpoint. No LLM, no write, no new checkpoint - committing is a separate action. */
function talkPreviewText(p) {
  const b = (p && p.basis) || {};
  const bits = [];
  if (!p || !p.checkpoint) {
    bits.push('There is no checkpoint yet, so there is nothing to compare against. You can keep talking.');
  } else {
    const n = (b.evidence_added_since_checkpoint || []).length;
    bits.push(n ? (n + ' new fact' + (n === 1 ? '' : 's') + ' since your last checkpoint.') : 'No new facts since your last checkpoint.');
    const s = (b.evidence_superseded || []).length;
    if (s) bits.push(s + ' earlier claim' + (s === 1 ? ' was' : 's were') + ' corrected.');
    if (b.goal_changed) bits.push('Your Goal has a new version.');
    if (b.knowledge_changed) bits.push('The knowledge base changed since then.');
    if (b.observation_changed) bits.push('New outcomes or check-ins are on record since your last checkpoint.');
    const ex = (b.executed_moves || []).length;
    if (ex) bits.push(ex + ' move' + (ex === 1 ? ' was' : 's were') + ' marked done (execution, not proof).');
    /* NC-R2: whether a re-evaluation may run is the server's decision; render its own codes and
       wording instead of inferring permission from material_change. A provider outage is a technical
       condition, never a business verdict. */
    const elig = (p && p.eligibility) || null;
    if (elig && (elig.blocked_details || []).length) {
      bits.push(elig.blocked_details.join(' '));
    } else if (elig && (elig.blocked_reasons || []).length) {
      bits.push('A re-evaluation is not available right now: ' + elig.blocked_reasons.join(', ') + '.');
    } else if (elig && elig.eligible) {
      bits.push('A re-evaluation is available and would build checkpoint v' + p.next_checkpoint_version + '. The reassessment itself is started from Maps.');
    } else {
      bits.push(p.material_change
        ? ('A re-evaluation would build checkpoint v' + p.next_checkpoint_version + '.')
        : 'Nothing material changed, so a re-evaluation is not needed yet.');
    }
  }
  bits.push('This is a preview only: nothing was saved and no synthesis ran.');
  return bits.join(' ');
}
async function talkPreviewChanges() {
  if (IS_DEMO || !LIVE.sid || LIVE.askThinking) return;
  const sid = LIVE.sid;
  const th = talkThread();
  LIVE.askThinking = true;
  talkAppend('<div class="talk-msg" id="talk-thinking" role="status"><div class="talk-meta"><span>Novaliners</span></div><div class="talk-body"><span class="think-dots"><i></i><i></i><i></i></span> Checking your record...</div></div>');
  let reply = null;
  try {
    const p = await API.reevaluatePreview(sid);
    if (LIVE.sid !== sid) return;
    reply = { role: 'bot', kind: 'REASSESS_PREVIEW',
      checkpointId: (p && p.checkpoint && p.checkpoint.checkpoint_id) || '',
      text: talkPreviewText(p), next: [] };
    for (let i = th.length - 1; i >= 0; i--) {
      if (th[i] && th[i].kind === 'REASSESS_PREVIEW') th.splice(i, 1);   // keep only the newest preview
    }
    th.push(reply); askSaveThread();
  } catch (e) {
    if (LIVE.sid !== sid) return;
    reply = { role: 'error', text: 'Could not read that: ' + e.message };
    th.push(reply);
  } finally {
    if (LIVE.sid === sid) LIVE.askThinking = false;
  }
  if (LIVE.sid !== sid) return;
  const think = document.getElementById('talk-thinking'); if (think) think.remove();
  if (reply) {
    /* A newer preview replaces the previous one on screen too (older builds' untagged rows stay). */
    if (reply.kind === 'REASSESS_PREVIEW') document.querySelectorAll('#chat-messages-container [data-kind="REASSESS_PREVIEW"]').forEach(el => el.remove());
    talkAppend(talkMsgHtml(reply));
  }
}

/* Honest acknowledgement of an accepted semantic update, built only from what the server returned. */
function talkUpdateAck(r) {
  const cls = (r && r.change_class) ? String(r.change_class) : '';
  const bits = [];
  if (cls === 'no_material_change') bits.push('Recorded. Nothing material changed on your map.');
  else if (cls === 'correction') bits.push('Recorded as a correction. The earlier claim is superseded, not erased.');
  else if (cls === 'goal_change') bits.push('Recorded. Your Goal has a new version; older checkpoints stay as history.');
  else if (cls === 'outcome_observation') bits.push('Recorded as an observed outcome, not proof that it worked.');
  else if (cls === 'new_information') bits.push('Recorded as new information on your map.');
  else bits.push('Recorded on your map.');
  const cp = r && r.checkpoint;
  if (cp && cp.status === 'stale') bits.push('Your last checkpoint is now stale: it stays readable as history and can be rebuilt later.');
  const nm = r && r.next_move;
  if (nm && nm.headline) bits.push('Next: ' + String(nm.headline).slice(0, 200));
  return bits.join(' ');
}
