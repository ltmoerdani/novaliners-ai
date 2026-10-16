/* Ask (screen 19): talk the diagnosis through. The discussion page of a map: understand a part of the result, try a "what if",
   find out what a path still needs. It never changes the map: when something changed, "Update my diagnosis" starts the next
   cycle from what you report. internal-docs §4.
   Layout: the conversation on the left (starter questions while it is empty, follow-up questions after each answer, one composer),
   a reference column on the right (your diagnosis in short, your next step, "Something changed?").
   v = { thread: [{ role: 'user' | 'bot' | 'error', text }], chips: [text], thinking, focus: { name } | null, draft,
         verdict (pill html), blocker (html-safe text), nextStep (html-safe text), canUpdate,
         h: { send, chip, update } (names of the handlers: demo and live differ, the template does not) }
   All text fields are html-safe. */
function renderAskLayout(v) {
  const msg = m => `
      <div class="ask-msg ${m.role}">
        <span class="ask-who">${m.role === 'user' ? 'You' : 'Novaliners'}</span>
        <div class="ask-bubble">${m.text}</div>
      </div>`;
  const chips = v.chips.length ? `<div class="ask-chips" role="group" aria-label="Suggested questions">${v.chips.map((q, i) => `<button type="button" class="ask-chip" onclick="${v.h.chip}(${i})">${q}</button>`).join('')}</div>` : '';
  const empty = !v.thread.length;
  return `
  <div class="ask-layout">
    <section class="ask-main" aria-label="Conversation">
      <header class="ask-head">
        <h1 class="serif-heading" style="font-size:30px;margin:0">Ask about your map</h1>
        <p>Answers use what you told us, your diagnosis and what each path needs. Nothing you ask here changes your map.</p>
      </header>
      <div class="ask-thread" id="ask-thread" role="log" aria-live="polite" aria-label="Your conversation">
        ${empty ? `<div class="ask-start"><p>What would you like to talk through? Pick a question or write your own.</p>${chips}</div>` : v.thread.map(msg).join('')}
        ${v.thinking ? `<div class="ask-msg bot" role="status"><span class="ask-who">Novaliners</span><div class="ask-bubble"><span class="think-dots"><i></i><i></i><i></i></span> Thinking it through…</div></div>` : ''}
        ${!empty && !v.thinking ? chips : ''}
      </div>
      ${v.focus ? `<div class="ask-focus"><span>Asking about <b>${v.focus.name}</b></span><button type="button" onclick="askClearFocus()">Ask about the whole map</button></div>` : ''}
      <form class="ask-composer" onsubmit="${v.h.send}(event)">
        <textarea id="ask-input" rows="1" aria-label="Your question" maxlength="600" placeholder="Ask about your diagnosis, a path, or a step"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();${v.h.send}(event)}">${v.draft || ''}</textarea>
        <button type="submit" class="btn-primary" ${v.thinking ? 'disabled' : ''}>Ask</button>
      </form>
    </section>

    <aside class="ask-side" aria-label="Your map in short">
      <div class="card-clean" style="padding:18px 20px">
        <div class="section-meta-label">Your diagnosis in short</div>
        <div style="margin:2px 0 8px">${v.verdict}</div>
        <p style="font-size:13.5px;line-height:1.55;color:var(--ink-2);margin:0">${v.blocker}</p>
        <button type="button" class="btn-secondary" style="width:100%;margin-top:14px" onclick="renderScreen('17')">Open Diagnosis →</button>
      </div>
      <div class="card-clean" style="padding:18px 20px">
        <div class="section-meta-label">Your next step</div>
        <p style="font-size:13.5px;line-height:1.55;color:var(--ink-2);margin:0">${v.nextStep}</p>
        <button type="button" class="btn-secondary" style="width:100%;margin-top:14px" onclick="renderScreen('04')">Go to Activity →</button>
      </div>
      <div class="card-clean" style="padding:18px 20px">
        <div class="section-meta-label">Something changed?</div>
        <p style="font-size:13.5px;line-height:1.55;color:var(--ink-2);margin:0">A new client, a new number, a step you finished. Tell us what happened and your diagnosis is rebuilt from it.</p>
        <button type="button" class="btn-secondary" style="width:100%;margin-top:14px" ${v.canUpdate ? `onclick="${v.h.update}()"` : 'disabled'}>Update my diagnosis →</button>
      </div>
    </aside>
  </div>`;
}

/* Open Ask from anywhere: optionally about one path, optionally with a question already written in the box */
function openAsk(focusKey, draft) {
  STORE.askFocus = focusKey || '';
  STORE.askDraft = draft || '';
  renderScreen('19');
}
function askClearFocus() {
  const box = document.getElementById('ask-input');
  STORE.askDraft = box ? box.value : '';
  STORE.askFocus = '';
  renderScreen('19');
}
function askScrollEnd() {
  const el = document.getElementById('ask-thread');
  if (el) el.scrollTop = el.scrollHeight;
}

/* ── Demo (Dimas): three canned answers so the page can be reviewed without a model ─────────────── */
const DEMO_ASK = [
  { q: 'Why is this what is holding me back?',
    a: 'You have the skill and two people who asked to hear from you. What is missing is one page they can say yes to.\n\nThat is why the first step is small: write the offer and send it. We do not know yet whether either of them would buy.',
    next: ['What if I skip the first step?', 'What would open the audit path?'] },
  { q: 'What if I skip the first step?',
    a: 'Nothing breaks. But the two people who asked will keep waiting with nothing to answer.\n\nThe offer also makes every later step easier, because you will have something concrete to send.',
    next: ['Why is this what is holding me back?', 'What would open the audit path?'] },
  { q: 'What would open the audit path?',
    a: 'Two things: one client who paid you for an audit, and a second person asking for the same work.\n\nYou have neither yet. A first paying client from the people you know is what starts it.',
    next: ['Why is this what is holding me back?', 'What if I skip the first step?'] }
];
const DEMO_ASK_STARTERS = DEMO_ASK.map(x => x.q);

/* Questions on offer: the starters, the follow-ups of the last answer, or path-specific ones when a path is in focus */
function demoAskFocus() {
  const k = STORE.askFocus;
  return k ? demoReadiness().paths.find(p => p.key === k) || null : null;
}
function demoAskChips() {
  const th = STORE.askDemoThread || [];
  const last = th.length ? th[th.length - 1] : null;
  if (last && last.role === 'bot') return last.next || [];
  const f = demoAskFocus();
  return f ? [`What do I still have to get for ${f.name}?`, 'Which of these should I do first?'] : DEMO_ASK_STARTERS;
}
function demoAskView() {
  const th = STORE.askDemoThread || [];
  const rs = useRoadmapStore.getState();
  const step = rs.steps[rs.currentStep - 1];
  const D = DEMO_DIAGNOSIS;
  const f = demoAskFocus();
  return {
    thread: th.map(m => ({ role: m.role, text: esc(m.text) })),
    chips: demoAskChips().map(esc), thinking: false, focus: f ? { name: esc(f.name) } : null, draft: STORE.askDraft || '',
    verdict: `<span class="status-pill" style="background:var(--ink);color:var(--on-ink)">${D.verdict}</span> <span style="font-size:13px;color:var(--ink-3)">${D.confidence}</span>`,
    blocker: rs.currentCycle >= 2 ? esc(getCycle2Plan(rs.activePathId).diagnosis.blockHead) : esc(D.blockHead),
    nextStep: esc(step ? step.label : 'Report what happened'),
    canUpdate: true, h: { send: 'askSendDemo', chip: 'askPickChipDemo', update: 'askUpdateDemo' }
  };
}
function demoAskAnswer(q) {
  const hit = DEMO_ASK.find(x => x.q === q);
  if (hit) return { role: 'bot', text: hit.a, next: hit.next };
  const f = demoAskFocus();
  if (f && q.startsWith('What do I still have to get for')) {
    const c = rdCounts(f), names = s => f.items.filter(i => i.state === s).map(i => i.title.toLowerCase());
    const list = a => a.length ? a.join(', ') : 'nothing';
    return { role: 'bot', next: ['Which of these should I do first?'],
      text: `For this path we can confirm ${c.have} of the ${c.total} conditions so far.\n\nStill to get: ${list(names('need'))}.\nNot checked yet: ${list(names('unknown'))}.` };
  }
  return { role: 'bot', text: 'This is a demo, so only the suggested questions have answers. In the real app the answer comes from your own diagnosis.', next: DEMO_ASK_STARTERS };
}

function askSendDemo(e) {
  if (e && e.preventDefault) e.preventDefault();
  const box = document.getElementById('ask-input');
  const q = box ? box.value.trim() : '';
  if (q) askDemoPush(q);
}
function askPickChipDemo(i) {
  const q = demoAskChips()[i];
  if (q) askDemoPush(q);
}
function askDemoPush(q) {
  STORE.askDemoThread = (STORE.askDemoThread || []).concat([{ role: 'user', text: q }, demoAskAnswer(q)]);
  STORE.askDraft = '';
  renderScreen('19');
  askScrollEnd();
}
function askUpdateDemo() {
  renderScreen('05');
}
