/* Home screens 04 (Activity/Moves) 05 — v9 screen 17 (Diagnosis) was removed (legacy cleanup 15 Oct 2026); live diagnosis = State destination */
/* Activity: one-viewport, two-column layout (action on the left, roadmap on the right) */
function renderTodayLayout(v) {
  return renderMovesLayout(v);   // v11 (record D5); the v9 layout was removed in the legacy cleanup
}

/* Diagnosis: the map's diagnosis, following the seven-block artifact (docs 02-product-concept/01 §7.5): where you are, what is
   blocking you, next best action, we'll know we're right when, what not to do, why we think so, when to reassess.
   It opens like a person explaining the map: "Where you are" is a short summary in the user's own words (1 to 3 paragraphs),
   then what is blocking them, then three numbered steps joined by a rail (do this, hold off on this, why we think so).
   The right column is reference, not the story: the numbers, the paths on the map (where they go next) and when to check again.
   Long text shows its first sentence and keeps the rest behind "Read more". On a narrow screen the column folds into the same
   reading order: summary, numbers, blocking, steps, paths, reassess.
   v = { confidence, pill, line, summary, where (from diagWhere), blockTitle, blockBody, blockMore, nextTitle, nextWhy, nextMore,
         successText, successMore, stopHead, stopRest, stopMore, stopPill, why, paths, reassess, reassessAction }
   (all html-ready; nextWhy, the *More fields and reassessAction are optional) */
function diagMore(html) {
  return html ? `<details class="diag-more"><summary><span>Read more</span><span>Show less</span></summary><div>${html}</div></details>` : '';
}
function renderDiagnosisLayout(v) {
  const w = v.where;
  const fig = (label, value, sub) => `<div><span class="section-meta-label" style="margin:0">${label}</span><b>${value}</b>${sub ? `<span>${sub}</span>` : ''}</div>`;
  return `
  <div class="diag-scroll"><div class="diag-layout">
    <div class="diag-main">
      <header class="diag-head">
        <div class="diag-eyebrow">${v.pill}<span class="diag-verdict-line">${v.line}</span><span class="diag-confidence">${v.confidence}</span></div>
        <h1 class="serif-heading" style="font-size:30px;margin:16px 0 10px">Where you are</h1>
        <div class="diag-summary">${v.summary}</div>
      </header>

      <section class="diag-block">
        <div class="section-meta-label">What's blocking you</div>
        <h2 class="serif-heading" style="font-size:22px;line-height:1.3;margin:0 0 6px">${v.blockTitle}</h2>
        ${v.blockBody ? `<p style="font-size:14.5px;color:var(--ink-2);line-height:1.6;margin:0">${v.blockBody}</p>` : ''}
        ${diagMore(v.blockMore)}
      </section>

      <section class="diag-step diag-s1">
        <span class="diag-num" aria-hidden="true">1</span>
        <div class="card-dark diag-action" style="padding:18px 20px">
          <div class="section-meta-label" style="color:var(--border-strong)">Next best action · under 30 min</div>
          <h2 style="font-family:var(--font-ui);font-size:17px;font-weight:700;line-height:1.4;margin:0">${v.nextTitle}</h2>
          ${v.nextWhy ? `<p style="font-size:13.5px;line-height:1.55;margin:6px 0 0">${v.nextWhy}</p>` : ''}
          ${diagMore(v.nextMore)}
          <div class="diag-proof">
            <div class="section-meta-label" style="color:var(--border-strong)">We'll know we're right when</div>
            <p style="font-size:13.5px;line-height:1.55;margin:0">${v.successText}</p>
            ${diagMore(v.successMore)}
          </div>
          <button class="btn-primary" style="background:var(--surface);color:var(--ink);width:100%;margin-top:14px" onclick="renderScreen('04')">Go to Activity →</button>
        </div>
      </section>

      <section class="diag-step diag-s2">
        <span class="diag-num" aria-hidden="true">2</span>
        <div class="card-danger diag-stop">
          <div class="section-meta-label" style="color:var(--stop-fg)">What not to do yet</div>
          <h2 style="font-family:var(--font-ui);font-size:17px;font-weight:700;line-height:1.4;color:var(--stop-fg);margin-bottom:6px">${v.stopHead}</h2>
          <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55;margin:0">${v.stopRest}</p>
          ${diagMore(v.stopMore)}
          ${v.stopPill ? `<span style="display:inline-flex;margin-top:12px">${v.stopPill}</span>` : ''}
        </div>
      </section>

      <section class="diag-step diag-s3">
        <span class="diag-num" aria-hidden="true">3</span>
        <div class="card-clean diag-why" style="padding:18px 20px">
          <div class="section-meta-label" style="margin-bottom:8px">Why we think so</div>
          <div style="display:flex;flex-direction:column;gap:10px">${v.why}</div>
          <button type="button" class="btn-secondary" style="width:100%;margin-top:14px" onclick="openDrawer()">How we got here →</button>
        </div>
      </section>
    </div>

    <aside class="diag-side" aria-label="Your numbers and next stops">
      <div class="card-clean diag-where" style="padding:18px 20px">
        <div class="diag-where-head"><span class="section-meta-label" style="margin:0">Your numbers</span><span class="diag-time">${w.time}</span></div>
        <div class="diag-figures">${fig('Income now', w.now, w.nowSub)}${fig('Goal', w.goal, w.goalSub)}${fig('Still to go', w.gap, w.gapSub)}</div>
        ${w.pct == null ? '' : `<div class="diag-bar" role="progressbar" aria-label="Income now against your goal" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${w.pct}"><i style="width:${w.pct}%"></i></div>`}
      </div>
      <div class="card-clean diag-paths" style="padding:18px 20px">
        <div class="section-meta-label" style="margin-bottom:8px">Paths on your map</div>
        <div class="diag-path-list">${v.paths}</div>
        <button type="button" class="btn-secondary" style="width:100%;margin-top:14px" onclick="renderScreen('07')">See your path map →</button>
      </div>
      <div class="card-clean diag-reassess" style="padding:18px 20px">
        <div class="section-meta-label">When to reassess</div>
        <p style="font-size:13.5px;line-height:1.55;color:var(--ink-2);margin:0">${v.reassess}</p>
        ${v.reassessAction || ''}
      </div>
    </aside>
  </div></div>`;
}
/* One line of "why we think so": a bullet, then an optional bold source and the text */
function diagLine(lead, text) { return `<div class="diag-line"><span>${lead ? `<b>${lead}</b> ` : ''}${text}</span></div>`; }
/* One path on the map: name and its status word */
function diagPath(name, cls, word, meta) { return `<div class="diag-path"><span>${name}${meta ? `<i class="diag-path-meta">${meta}</i>` : ''}</span><span class="status-pill ${cls}">${word}</span></div>`; }
/* Where you are, as numbers: monthly income now and goal as numbers (null when unknown), fmt() makes html-safe text ("Rp5M").
   The gap and the progress bar need both; the days left sit beside the goal they belong to. */
function diagWhere(now, goal, fmt, left, day, horizon) {
  const known = now != null && goal != null && goal > 0;
  const gap = known ? Math.max(goal - now, 0) : null;
  return {
    now: now != null ? fmt(now) : 'Not set', nowSub: now != null ? '' : 'add it at your next check-in',
    goal: goal != null ? fmt(goal) : 'Not set', goalSub: goal != null ? '' : 'needs a goal',
    gap: gap != null ? fmt(gap) : '—', gapSub: gap != null ? '' : 'needs both numbers',
    pct: known ? Math.min(100, Math.round(now / goal * 100)) : null,
    time: `${left} day${left === 1 ? '' : 's'} left · Day ${day} of ${horizon}`
  };
}

function screen04() {
  const isId = STORE.todayMsgLang === 'id';
  const rs = useRoadmapStore.getState();
  const earned = rs.earned || 0;
  // What the card shows: the suggested next step, or the one the user picked in the checklist
  const viewNum = STORE.viewStep && STORE.viewStep !== rs.currentStep && rs.steps[STORE.viewStep - 1] ? STORE.viewStep : 0;
  const cur = rs.steps[(viewNum || rs.currentStep) - 1];
  const readyCount = rs.steps.filter(s => s.ready && !s.report).length;
  const oneThing = readyCount > 1 ? 'Several moves are ready.' : 'One move to work on now.';

  // ──────── After Day 90 ────────
  if (rs.ending) {
    const content = `
    <div class="today-layout" style="grid-template-columns:minmax(0, 640px);justify-content:center;align-content:center">
      <div class="card-clean" style="padding:32px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:12px">
        <div class="section-meta-label" style="margin:0">Day 90</div>
        <h1 class="serif-heading" style="font-size:32px">Your 90 days are done.</h1>
        <p style="font-size:14.5px;color:var(--ink-2);line-height:1.55;margin:0;max-width:460px">You're at Rp${rs.earned}M a month${rs.ending === 'success' ? ', past your goal' : `, Rp${Math.max(rs.goalRp - rs.earned, 0)}M short of your goal`}. Before we plan anything new, look back at what happened and choose what comes next.</p>
        <button class="btn-primary" style="margin-top:8px" onclick="renderScreen('16')">See your Day 90 review →</button>
      </div>
    </div>`;
    return renderAppShell('activity', 'Activity', content);
  }

  // ──────── Cycle 2 onward ────────
  if (rs.currentCycle >= 2) {
    const plan = getCycle2Plan(rs.activePathId);
    const isAudit = rs.activePathId === 'audit';

    const lastCheckIn = rs.history[rs.history.length - 1];
    const bannerText = lastCheckIn
      ? `Check-in ${lastCheckIn.cycle} done · ${lastCheckIn.title}. ${lastCheckIn.note || ''}`
      : `Check-in ${rs.currentCycle - 1} done.`;
    const banner = rs.doneNums.length === 0 ? `
      <div class="today-banner">
        <span class="today-banner-icon">✓</span>
        <span style="flex:1;min-width:0">${bannerText}</span>
        ${rs.currentCycle === 2 ? '<button class="btn-secondary btn-sm" onclick="resetToCycle1()" style="white-space:nowrap;font-size:11.5px;height:28px">↺ Redo check-in 1</button>' : ''}
      </div>` : '';

    const content = renderTodayLayout({
      banner,
      stepDetails: { [cur.num]: { desc: cur.desc || '', box: typeof cur.box === 'function' ? cur.box(isId) : (cur.box || '') } },
      timeTag: todayStepTimeTag(cur, cur.tag, rs.currentDay),
      title: cur.title,
      desc: cur.desc,
      box: cur.box(isId),
      actions: todayStepActions(cur, rs, 'advanceTodayStep()'),
      successLabel: 'Success this week',
      successText: plan.success,
      why: renderTodayWhy(plan.diagnosis.headline),
      whyText: plan.diagnosis.headline,
      pathTitle: plan.title,
      pathPill: plan.pill,
      steps: rs.steps,
      reportLabel: cur.report ? `Open Day ${cur.day} check-in →` : 'Report results early',
      routeTasks: renderRouteTasks(demoRouteTasks())
    });
    return renderAppShell('activity', 'Activity', content);
  }

  // ──────── Cycle 1 ────────
  const CYCLE1_CONTENT = {
    1: {
      tag: 'DAY 1–2 · SAVED',
      title: 'Write a one-page offer for your brand advice service.',
      desc: "Keep it under one page: who it's for, what problem it solves, and how 90 days look.",
      box: renderListBox('One-page summary draft', 'Brand Growth Advice for Consumer Brands (90 days):', [
        "<strong>Who it's for:</strong> Local consumer brands making Rp5M to Rp20M",
        '<strong>What you get:</strong> A review of where you sell, a sharper product message, and a 90-day growth plan',
        '<strong>Time needed:</strong> 2 working sessions plus a weekly check-in call',
        '<strong>Price:</strong> Rp15M flat'
      ]),
    },
    2: {
      tag: 'TODAY · UNDER 30 MINUTES',
      title: 'Send your one-page offer to the 2 contacts who asked.',
      desc: 'They told you “let me know when you start.” This is simply you letting them know, not a sales pitch.',
      box: renderMsgBox('WhatsApp message, ready to send',
        "Hi Sari, you once asked me to let you know if I started my own business. It's up and running now. I help consumer brands plan their next 90 days.\n\nI've attached a one-page summary. If it's useful, could we talk for 20 minutes this week?",
        'Halo Mbak Sari, dulu Mbak pernah bilang kabari kalau saya buka jasa sendiri. Sekarang sudah jalan. Saya bantu brand produk sehari-hari menyusun strategi 90 hari.\n\nSaya lampirkan ringkasan 1 halaman. Kalau relevan, boleh kita ngobrol 20 menit minggu ini?', isId),
    },
    3: {
      tag: 'DAY 4–5 · UNDER 15 MINUTES',
      title: 'Follow up with Sari and the 2nd contact to book a 20-min call.',
      desc: 'Ask if they had a chance to read your one-page offer, and suggest a short call about what they need right now.',
      box: renderMsgBox('Follow-up WhatsApp message',
        "Hi Sari, following up on my note yesterday. Did you have a chance to look over the one-page summary? If you have 20 minutes this Thursday or Friday, I'd love to jump on a quick call.",
        'Halo Mbak Sari, sekadar follow up santai dari pesan kemarin. Apakah sempat melihat ringkasannya? Kalau senggang Kamis atau Jumat ini, saya ada waktu 20 menit untuk ngobrol santai.', isId),
    },
    4: {
      tag: 'DAY 6 · UNDER 30 MINUTES',
      title: 'Send your one-page offer to 5 more people you know.',
      desc: 'Reach out to former colleagues or other people you know before the weekly review. Real conversations show you what people will pay for.',
      box: renderMsgBox('Message to people you know',
        "Hi [Name], hope you're doing well! I'm now helping consumer brands make clear 90-day growth plans. I put together a one-page overview of how it works. Happy to share it if it's useful to you.",
        'Halo Mas/Mbak [Nama], semoga kabarnya baik! Saat ini saya sedang fokus membantu brand produk sehari-hari menyusun strategi pertumbuhan 90 hari. Saya ada ringkasan 1 halaman tentang pendekatan ini, boleh saya kirimkan barangkali relevan untuk timmu?', isId),
    },
    5: {
      tag: 'Day 7 · weekly review',
      title: 'Report what happened this week & update your map.',
      desc: 'All 5 steps of your first week are done. Tell us what happened so Novaliners can update your map and open new paths.',
      box: renderDoneBox('7 days of reaching out: done', 'Time for your weekly check-in: how many people replied, how many calls you had, and whether anyone paid.')
    }
  };
  const view = CYCLE1_CONTENT[cur.num] || CYCLE1_CONTENT[2];

  const content = renderTodayLayout(Object.assign({}, view, {
    stepDetails: Object.fromEntries(Object.entries(CYCLE1_CONTENT).map(([k, c]) => [k, { desc: c.desc || '', box: c.box || '' }])),
    timeTag: todayStepTimeTag(cur, view.tag, rs.currentDay),
    actions: todayStepActions(cur, rs, 'advanceTodayStep()'),
    successLabel: 'Success this week',
    successText: 'At least 1 of the 2 replies with a question or a time to talk. Even a “no” helps update your map.',
    why: renderTodayWhy(DEMO_DIAGNOSIS.headline),
    whyText: DEMO_DIAGNOSIS.headline,
    pathTitle: 'Advising people you know',
    pathPill: renderStatusPill('OPEN'),
    steps: rs.steps,
    reportLabel: cur.report ? 'Open Day 7 check-in →' : 'Report results early',
    routeTasks: renderRouteTasks(demoRouteTasks())
  }));
  return renderAppShell('activity', 'Activity', content);
}

/* Time tag of the step card: the effort, plus where the step stands (done, waiting, or ready now).
   Phase 7: no planned-day wording - a step is ready whenever the person chooses to do it. */
function todayStepTimeTag(step, baseTag, day) {
  if (step.status === STEP_STATUS.COMPLETED) return 'Done';
  if (step.hold) return 'On hold';
  if (step.ready === false) return `Waits for ${step.waitingFor.map(n => `step ${n}`).join(' and ')}`;
  const effort = toTimeTag(baseTag || '');
  return !step.report && step.day > day ? `${effort} · Ready now` : effort;
}

/* Buttons of the step card. `advance` is the handler that finishes the step (demo and live differ only there). */
function todayStepActions(cur, rs, advance) {
  if (cur.status === STEP_STATUS.COMPLETED) {
    return `<button class="btn-primary" onclick="setTodayStep(0)">Back to your next step →</button>
        <span class="today-note">You did this on Day ${cur.doneDay || rs.currentDay}.</span>`;
  }
  if (cur.hold) return `<span class="today-note">On hold: the later days wait for what your first steps show. Report your results and the plan updates.</span>`;
  if (cur.ready === false) {
    const first = rs.steps[cur.waitingFor[0] - 1];
    return `<button class="btn-primary" onclick="setTodayStep(${first.num})">Start with step ${first.num} →</button>
        ${cur.report ? `<button class="btn-secondary" onclick="renderScreen('05')">Report early anyway</button>` : ''}
        <span class="today-note">${stepWaitNote(cur, rs.steps)}.</span>`;
  }
  if (cur.report) return `<button class="btn-primary" onclick="renderScreen('05')">Open Day ${cur.day} check-in →</button>`;
  return `<button class="btn-primary" id="advance-btn" onclick="${advance}">${cur.sent ? 'Record as sent' : 'Record step as done'}</button>
        <button class="btn-secondary" onclick="notTodayStep()">Can't do this yet</button>`;
}

// Look at a step from the checklist. Any step can be opened; only ready ones can be finished.
function setTodayStep(step) {
  const rs = useRoadmapStore.getState();
  const s = step && rs.steps[step - 1];
  if (s && s.report && s.ready) { renderScreen('05'); return; }
  STORE.viewStep = s && step !== rs.currentStep ? step : 0;
  renderScreen('04');
}

// "Not today": this step waits, so show another one that can be done now (nothing to switch to = Welcome back)
function notTodayStep() {
  const rs = useRoadmapStore.getState();
  const curNum = STORE.viewStep || rs.currentStep;
  const other = rs.steps.find(s => s.ready && !s.report && s.num !== curNum);
  if (!other) { renderScreen('14'); return; }
  STORE.viewStep = other.num === rs.currentStep ? 0 : other.num;
  showToast('This one can wait. Here is another step you can do now.', '', '');
  renderScreen('04');
}

// "Record as sent / Record as done": finish this step (explicit identity from the Moves action list; the
// old viewStep/currentStep chain remains as a fallback for no-arg callers).
function advanceTodayStep(num) {
  const rs = useRoadmapStore.getState();
  if (!rs.completeStep(num || STORE.viewStep || rs.currentStep)) return;
  showToast('Saved. Your map is updated.', 'View map →', 'maps');
  const after = useRoadmapStore.getState();
  const next = after.steps[after.currentStep - 1];
  if (next && next.report && next.ready) renderScreen('05');
}

function resetToCycle1() {
  const rs = useRoadmapStore.getState();
  rs.startCycle({ cycle: 1, pathId: 'warm', earned: 0, activePaths: ['warm'] });
  rs.advanceDay(1);
  rs.completeStep(1);
  rs.advanceDay(1);
  renderScreen('04');
}

/* Phase 2 sample for design review: steps that come from routes (a capability the user still needs). Demo state only. */
STORE.demoRoute = { icp: 'READY' };
function demoRouteTasks() {
  const v = STORE.demoRoute.icp;
  return [{
    key: 'icp', route: 'Direct outreach', state: v === 'EXECUTED' ? 'proof' : 'ready',
    title: 'Write down who you sell to: type of business, level, and buyer role',
    onDone: "setDemoRoute('EXECUTED')", onUndo: "setDemoRoute('READY')"
  }];
}
function setDemoRoute(v) { STORE.demoRoute.icp = v; renderScreen('04'); }

function toggleTodayLang(lang) {
  STORE.todayMsgLang = lang;
  renderScreen('04');
}

/* ── Screen 05 · Weekly check-in ───────────────────────────────────────── */
function screen05() {
  const outcome = STORE.checkInOutcome || 'worked';
  const cData = STORE.checkInData || {
    contacted: 7,
    replies: 4,
    calls: 2,
    paid: 'Rp15.000.000',
    paidRaw: 15
  };

  const content = `
  <div style="padding:40px 24px;display:flex;flex-direction:column;align-items:center">
    <div style="width:100%;max-width:720px;display:flex;flex-direction:column;gap:24px">
      <a onclick="renderScreen('04')" style="font-family:var(--font-ui);font-size:13px;color:var(--ink-2);text-decoration:none;cursor:pointer">← Back to Moves</a>
      <div>
        <div class="section-meta-label">Day ${getTimeline().nextCheckIn} check-in · review</div>
        <h1 class="serif-heading" style="font-size:36px">What happened this week?</h1>
        <p style="font-size:14px;color:var(--ink-2);margin-top:6px">Pick what happened and adjust the numbers below. Whatever the result, your map will update.</p>
      </div>

      <div style="display:flex;flex-direction:column;gap:10px">
        <label class="section-meta-label">How did it go? (pick one)</label>
        <div class="radio-card ${outcome === 'worked' ? 'selected' : ''}" onclick="setCheckInOutcome('worked')">
          <div class="radio-dot"></div>
          <div>
            <div style="font-family:var(--font-ui);font-weight:700;font-size:14.5px">It worked</div>
            <div style="font-size:13px;color:var(--ink-2)">Someone agreed to pay or signed a project (for example, Sari signed for Rp15M)</div>
          </div>
        </div>
        <div class="radio-card ${outcome === 'mixed' ? 'selected' : ''}" onclick="setCheckInOutcome('mixed')">
          <div class="radio-dot"></div>
          <div>
            <div style="font-family:var(--font-ui);font-weight:700;font-size:14.5px">Mixed</div>
            <div style="font-size:13px;color:var(--ink-2)">People replied and met with you, but no one signed yet because it felt like too big a commitment</div>
          </div>
        </div>
        <div class="radio-card ${outcome === 'none' ? 'selected' : ''}" onclick="setCheckInOutcome('none')">
          <div class="radio-dot"></div>
          <div>
            <div style="font-family:var(--font-ui);font-weight:700;font-size:14.5px">No replies</div>
            <div style="font-size:13px;color:var(--ink-2)">Messages went out but no one replied. That tells us the message needs to be simpler.</div>
          </div>
        </div>
      </div>

      <div class="tip-bubble pointer-left">
        <div style="font-family:var(--font-ui);font-size:12px;font-weight:600;color:var(--on-dark-2);margin-bottom:2px">Good to know</div>
        <div style="font-family:var(--font-ui);font-size:13.5px;font-weight:700;margin-bottom:4px">Every result teaches us something.</div>
        <div style="font-size:12.5px;color:var(--on-dark-3);line-height:1.5">There's no failing here. We use these numbers to decide whether to open a new path or adjust your offer.</div>
      </div>

      <div class="card-clean">
        <div class="section-meta-label mb-8">This week's numbers (you can edit them)</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(140px, 1fr));gap:12px">
          <div>
            <label style="font-size:12px;color:var(--ink-3)">People contacted</label>
            <input type="number" id="checkin-contacted" value="${cData.contacted}" oninput="updateCheckInData('contacted', this.value)" style="width:100%;border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-top:4px;font-weight:700">
          </div>
          ${outcome !== 'none' ? `
          <div>
            <label style="font-size:12px;color:var(--ink-3)">Replies</label>
            <input type="number" id="checkin-replies" value="${cData.replies}" oninput="updateCheckInData('replies', this.value)" style="width:100%;border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-top:4px;font-weight:700">
          </div>
          <div>
            <label style="font-size:12px;color:var(--ink-3)">Calls held</label>
            <input type="number" id="checkin-calls" value="${cData.calls}" oninput="updateCheckInData('calls', this.value)" style="width:100%;border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-top:4px;font-weight:700">
          </div>` : ''}
          ${outcome === 'worked' ? `
          <div>
            <label style="font-size:12px;color:var(--ink-3)">Paid (in Rp)</label>
            <input type="text" id="checkin-paid" value="${cData.paid}" oninput="updateCheckInData('paid', this.value)" style="width:100%;border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-top:4px;font-weight:700">
          </div>` : ''}
        </div>
      </div>

      <button class="btn-primary" style="height:48px;font-size:15px;font-weight:600" onclick="submitCheckIn()">
        Update my map →
      </button>
    </div>
  </div>`;
  return renderAppShell('activity', 'Weekly check-in', content);
}

function setCheckInOutcome(val) {
  STORE.checkInOutcome = val;
  if (!STORE.checkInData) STORE.checkInData = {};
  if (val === 'worked') {
    STORE.checkInData.contacted = 7;
    STORE.checkInData.replies = 4;
    STORE.checkInData.calls = 2;
    STORE.checkInData.paid = 'Rp15.000.000';
    STORE.checkInData.paidRaw = 15;
  } else if (val === 'mixed') {
    STORE.checkInData.contacted = 7;
    STORE.checkInData.replies = 4;
    STORE.checkInData.calls = 2;
    STORE.checkInData.paid = 'Rp0';
    STORE.checkInData.paidRaw = 0;
  } else {
    STORE.checkInData.contacted = 7;
    STORE.checkInData.replies = 0;
    STORE.checkInData.calls = 0;
    STORE.checkInData.paid = 'Rp0';
    STORE.checkInData.paidRaw = 0;
  }
  renderScreen('05');
}

function updateCheckInData(key, val) {
  if (!STORE.checkInData) STORE.checkInData = {};
  STORE.checkInData[key] = val;
  if (key === 'paid') {
    const num = parseInt(String(val).replace(/[^0-9]/g, ''), 10);
    STORE.checkInData.paidRaw = isNaN(num) ? 0 : Math.round(num / 1000000);
  }
}

function submitCheckIn() {
  const rs = useRoadmapStore.getState();
  // From Cycle 2 on, a manual check-in saves straight to history and starts the next cycle
  if (rs.currentCycle >= 2) {
    const pInputLater = document.getElementById('checkin-paid');
    if (pInputLater) updateCheckInData('paid', pInputLater.value);
    const outcome = STORE.checkInOutcome || 'worked';
    const paidNow = (STORE.checkInData && STORE.checkInData.paidRaw) || 0;
    const rp = outcome === 'worked' ? Math.round((rs.earned + paidNow / 2) * 10) / 10 : rs.earned;
    const nextPath = { worked: 'audit', mixed: 'warm_starter', none: 'warm_retest' }[outcome] || rs.activePathId;
    const rec = checkInRecordFromForm(rp, rs.activePaths);
    const isFinal = rs.currentCycle * 7 >= GOAL_DAY;
    if (isFinal) Object.assign(rec, { outcome: 'final', title: `Day 90 · Rp${rp}M a month`, ending: rp >= rs.goalRp ? 'success' : 'miss' });
    rs.recordCheckIn(rec, nextPath);
    showToast(`Check-in ${rs.currentCycle} saved. Your map and journey are updated.`, 'View journey →', '08');
    renderScreen(isFinal ? '16' : '04');
    return;
  }
  const pInput = document.getElementById('checkin-paid');
  if (pInput && STORE.checkInOutcome === 'worked') {
    updateCheckInData('paid', pInput.value);
    useRoadmapStore.getState().setMetrics({ earned: STORE.checkInData.paidRaw || 15 });
  } else if (STORE.checkInOutcome !== 'worked') {
    useRoadmapStore.getState().setMetrics({ earned: 0 });
  }
  
  if (STORE.checkInOutcome === 'worked') {
    renderScreen('06a');
  } else if (STORE.checkInOutcome === 'mixed') {
    renderScreen('12');
  } else {
    renderScreen('06b');
  }
}
