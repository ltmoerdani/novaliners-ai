/* Map + Journey */
/* ── Screen 07 · Path map ────────────────────── */
// What the map looked like the last time it was shown: used to animate only what changed since then
const MAP_MEMORY = { doneIds: null, currentId: null, auditOpen: null, cmoOpen: null, progressLen: null, histLen: null, scrollKey: null, scrollLeft: null, gliding: false };

function screen07() {
  const sel = STORE.selectedMapPath || 'warm';
  const tl = getTimeline();
  const rs = useRoadmapStore.getState();
  const activeMapPath = toMapPath(rs.activePathId);
  const auditOpen = rs.activePaths.includes('audit');
  const firstPaid = rs.earned > 0;

  // Milestones on the "Advising people you know" lane: the 5 Cycle 1 steps, then 2 outcomes
  const cycle1Steps = rs.currentCycle === 1 ? rs.steps : buildSteps(1, 6);
  const allStepsDone = cycle1Steps.every(st => st.status === STEP_STATUS.COMPLETED);
  const stepX = [250, 320, 390, 460, 530];
  const milestones = cycle1Steps.map((st, i) => ({ id: st.id, x: stepX[i], word: st.mapLabel, title: st.label, when: st.dayLabel, status: st.status,
    ready: st.ready, doneDay: st.doneDay, wait: st.ready === false ? stepWaitNote(st, cycle1Steps) : '' }));
  milestones.push({
    id: 'first-paid', x: 650, word: 'Paid', title: 'First paid client', when: 'Opens the audit path',
    status: firstPaid ? STEP_STATUS.COMPLETED : (allStepsDone && rs.currentCycle === 1 ? STEP_STATUS.CURRENT : STEP_STATUS.UPCOMING)
  });
  milestones.push({
    id: 'repeat-request', x: 770, word: 'Repeat', title: 'A second person asks for the same work', when: 'Second condition for the audit path',
    status: auditOpen ? STEP_STATUS.COMPLETED : (firstPaid && rs.currentCycle === 1 ? STEP_STATUS.CURRENT : STEP_STATUS.UPCOMING)
  });
  const currentMs = milestones.find(m => m.status === STEP_STATUS.CURRENT);
  const lastDone = milestones.filter(m => m.status === STEP_STATUS.COMPLETED).pop();
  // Steps can be finished in any order: the route travelled runs up to the furthest milestone reached
  const progressX = Math.max(250, currentMs ? currentMs.x : 0, ...milestones.filter(m => m.status === STEP_STATUS.COMPLETED).map(m => m.x));

  // Diff against the last visit
  const doneIds = milestones.filter(m => m.status === STEP_STATUS.COMPLETED).map(m => m.id);
  const newlyDone = MAP_MEMORY.doneIds ? doneIds.filter(id => !MAP_MEMORY.doneIds.includes(id)) : [];
  const newlyCurrent = currentMs && MAP_MEMORY.currentId !== null && MAP_MEMORY.currentId !== currentMs.id ? currentMs.id : null;
  const auditJustOpened = auditOpen && MAP_MEMORY.auditOpen === false;
  const cmoOpen = rs.activePaths.includes('cmo');
  const cmoJustOpened = cmoOpen && MAP_MEMORY.cmoOpen === false;
  MAP_MEMORY.cmoOpen = cmoOpen;
  const goalReached = rs.earned >= rs.goalRp;
  const twoPathsCompete = auditOpen && cmoOpen;
  MAP_MEMORY.doneIds = doneIds;
  MAP_MEMORY.currentId = currentMs ? currentMs.id : '';
  MAP_MEMORY.auditOpen = auditOpen;

  const tipSub = m => m.status === STEP_STATUS.COMPLETED ? (m.doneDay ? `Done · Day ${m.doneDay}` : `Done · ${m.when}`)
    : (m.status === STEP_STATUS.CURRENT ? `Start here · ${m.when}`
      : (m.ready === true ? `Ready now · ${m.when}` : (m.ready === false ? `${m.wait} · ${m.when}` : `Coming up · ${m.when}`)));
  const tipAttrs = m => `tabindex="0" data-tip-title="${m.title}" data-tip-sub="${tipSub(m)}"
            onmouseenter="showMapTip(this)" onmouseleave="hideMapTip()" onfocus="showMapTip(this)" onblur="hideMapTip()"`;
  const nodeWord = (x, y, word, status) => {
    const style = status === STEP_STATUS.CURRENT ? 'font-weight="700" fill="var(--ink)"'
      : (status === STEP_STATUS.COMPLETED ? 'font-weight="600" fill="var(--open-fg)"' : 'fill="var(--ink-muted)"');
    return `<text x="${x}" y="${y}" font-family="Plus Jakarta Sans" font-size="9.5" text-anchor="middle" ${style} pointer-events="none">${word}</text>`;
  };
  const milestoneSvg = milestones.map(m => nodeWord(m.x, 245, m.word, m.status) + milestoneNode(m)).join('');
  function milestoneNode(m) {
    if (m.status === STEP_STATUS.COMPLETED) {
      return `
          <g class="map-node ${newlyDone.includes(m.id) ? 'map-node-done-anim' : ''}" ${tipAttrs(m)}>
            <circle cx="${m.x}" cy="220" r="14" fill="transparent"/>
            <circle cx="${m.x}" cy="220" r="10" fill="var(--surface)"/>
            <circle cx="${m.x}" cy="220" r="7" fill="var(--open-line)" stroke="var(--open-line)" stroke-width="2"/>
            <text x="${m.x}" y="223.5" font-family="Plus Jakarta Sans" font-size="8" font-weight="700" text-anchor="middle" fill="var(--surface)">✓</text>
          </g>`;
    }
    if (m.status === STEP_STATUS.CURRENT) {
      return `
          <g class="map-node ${m.id === newlyCurrent ? 'map-node-unlock-anim' : ''}" ${tipAttrs(m)}>
            <circle cx="${m.x}" cy="220" r="14" fill="var(--surface)"/>
            <circle cx="${m.x}" cy="220" r="17" fill="var(--open-line)" opacity="0.12"/>
            <circle class="map-pulse" cx="${m.x}" cy="220" r="10" fill="none" stroke="var(--open-line)" stroke-width="2"/>
            <circle cx="${m.x}" cy="220" r="9" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.5"/>
            <circle cx="${m.x}" cy="220" r="3.5" fill="var(--ink)"/>
          </g>`;
    }
    if (m.ready === false) {
      return `
          <g class="map-node" ${tipAttrs(m)}>
            <circle cx="${m.x}" cy="220" r="14" fill="transparent"/>
            <circle cx="${m.x}" cy="220" r="10" fill="var(--surface)"/>
            <circle cx="${m.x}" cy="220" r="6" fill="var(--surface)" stroke="var(--border-strong)" stroke-width="2" stroke-dasharray="3 2"/>
          </g>`;
    }
    return `
          <g class="map-node" ${tipAttrs(m)}>
            <circle cx="${m.x}" cy="220" r="14" fill="transparent"/>
            <circle cx="${m.x}" cy="220" r="10" fill="var(--surface)"/>
            <circle cx="${m.x}" cy="220" r="6" fill="var(--surface)" stroke="var(--open-line)" stroke-width="2" opacity="0.7"/>
          </g>`;
  }

  const statuses = { warm: 'OPEN', agency: 'TEST_FIRST', audit: auditOpen ? 'OPEN' : 'NOT_YET', cmo: cmoOpen ? 'OPEN' : 'NOT_YET', ads: 'STOP' };
  const todayStep = rs.steps[rs.currentStep - 1];
  // Active checkpoint on whichever lane is the current path (the warm lane uses its own milestones)
  const activeNode = (x, y) => rs.ending ? '' : `
            <g class="map-node" tabindex="0" data-tip-title="${todayStep.label}" data-tip-sub="Today · Day ${tl.day} · Step ${rs.currentStep} of 5"
               onmouseenter="showMapTip(this)" onmouseleave="hideMapTip()" onfocus="showMapTip(this)" onblur="hideMapTip()">
              <circle cx="${x}" cy="${y}" r="14" fill="var(--surface)"/>
              <circle cx="${x}" cy="${y}" r="17" fill="var(--open-line)" opacity="0.12"/>
              <circle class="map-pulse" cx="${x}" cy="${y}" r="10" fill="none" stroke="var(--open-line)" stroke-width="2"/>
              <circle cx="${x}" cy="${y}" r="9" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.5"/>
              <circle cx="${x}" cy="${y}" r="3.5" fill="var(--ink)"/>
            </g>
            ${nodeWord(x, y + 25, todayStep.mapLabel, STEP_STATUS.CURRENT)}`;
  const openCount = Object.values(statuses).filter(st => st === 'OPEN').length;
  const COUNT_WORDS = ['No paths are', 'One is', 'Two are', 'Three are', 'Four are', 'Five are'];
  const laneClass = id => `map-lane ${sel === id ? 'selected' : 'dim'}`;
  const laneClick = id => `onclick="selectMapPath('${id}')"`;
  const halo = (id, d, color) => sel === id ? `<path d="${d}" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round" opacity="0.14"/>` : '';
  const hit = d => `<path d="${d}" fill="none" stroke="transparent" stroke-width="18" pointer-events="stroke"/>`;
  // Timeline: Cycle 1 keeps its 5 steps, then one column per cycle up to Day 90 (the map scrolls sideways)
  const LAST_CYCLE = Math.ceil(GOAL_DAY / 7);
  const COL = 130;
  const colX = c => 880 + (c - 2) * COL;
  const GX = colX(LAST_CYCLE) + 110;
  const VB_W = GX + 80 - 50;
  // Git-graph geometry: the recommended path runs straight from Start to Goal; the others branch off
  // the main line with smooth S-curves — the earlier a path branches, the further its lane sits from the main line.
  const LANE_Y = { warm: 220, agency: 158, audit: 338, cmo: 282, ads: 104 };
  const laneY = p => LANE_Y[toMapPath(p)] || 220;
  const cmoRec = rs.history.find(r => r.paths && r.paths.includes('cmo'));
  const cmoBx = (cmoRec ? colX(Math.max(cmoRec.cycle, 2)) : colX(Math.min(rs.currentCycle + 1, LAST_CYCLE - 1))) + 10;
  // Full lanes curve back into the goal point at the end of the main line, like a git merge
  const branchD = (bx, y, end) => `M ${bx} 220 C ${bx + 36} 220 ${bx + 36} ${y} ${bx + 72} ${y} ${end === GX
    ? `L ${GX - 72} ${y} C ${GX - 36} ${y} ${GX - 36} 220 ${GX} 220`
    : `L ${end} ${y}`}`;
  const WARM_D = `M 82 220 L ${GX} 220`;
  const AGENCY_D = branchD(214, 158, 560);
  const AUDIT_D = branchD(650, 338, GX);
  const CMO_D = branchD(cmoBx, 282, GX);
  const ADS_D = branchD(150, 104, 330);

  // The route actually travelled: Cycle 1 steps, then one checkpoint per check-in on the lane used that cycle
  const hist = rs.history.filter(r => r.cycle >= 2);
  const c1End = rs.currentCycle === 1 ? progressX : (lastDone ? lastDone.x : 250);
  const routePts = hist.map(r => ({ x: colX(r.cycle), y: laneY(r.path) }));
  const nowPt = !rs.ending && rs.currentCycle >= 2 ? { x: colX(rs.currentCycle), y: laneY(rs.activePathId) } : null;
  if (nowPt) routePts.push(nowPt);
  let routeD = `M 82 220 L ${c1End} 220`;
  let routeEnd = { x: c1End, y: 220 };
  routePts.forEach(p => {
    const dx = Math.min(36, Math.max(12, (p.x - routeEnd.x) / 2));
    routeD += p.y === routeEnd.y ? ` L ${p.x} ${p.y}`
      : ` C ${routeEnd.x + dx} ${routeEnd.y} ${routeEnd.x + dx} ${p.y} ${routeEnd.x + dx * 2} ${p.y} L ${p.x} ${p.y}`;
    routeEnd = p;
  });
  if (rs.ending && goalReached) routeD += ` L ${GX} ${routeEnd.y}`;
  const nowX = rs.ending ? GX : (nowPt ? nowPt.x : progressX);

  // Checkpoints: one dot per check-in, coloured by what happened
  const prevHist = MAP_MEMORY.histLen;
  MAP_MEMORY.histLen = rs.history.length;
  const attr = v => String(v).replace(/"/g, '&quot;');
  const OUTCOME_WORD = { mixed: 'Mixed', none: 'Quiet', missed: 'Missed', final: 'Day 90' };
  const WORD_COLOR = { worked: 'var(--open-fg)', mixed: 'var(--notyet-fg)', final: 'var(--ink)' };
  const EVENT_FLAG = { ads: ['Ads test · Rp2M', 'var(--stop-fg)'], capacity: ['Not enough hours', 'var(--notyet-fg)'], 'cmo-open': ['Marketing lead opened', 'var(--open-fg)'] };
  const checkpointSvg = hist.map(r => {
    const x = colX(r.cycle), y = laneY(r.path);
    const isNew = prevHist !== null && rs.history.indexOf(r) >= prevHist;
    const word = r.outcome === 'worked' ? `+Rp${r.paid}M` : (OUTCOME_WORD[r.outcome] || '');
    const flag = EVENT_FLAG[r.event];
    const dot = r.outcome === 'worked'
      ? `<circle cx="${x}" cy="${y}" r="10" fill="var(--surface)"/><circle cx="${x}" cy="${y}" r="8" fill="var(--open-line)"/><text x="${x}" y="${y + 3.5}" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" text-anchor="middle" fill="var(--surface)">✓</text>`
      : r.outcome === 'final'
        ? `<circle cx="${x}" cy="${y}" r="10" fill="var(--surface)"/><circle cx="${x}" cy="${y}" r="9" fill="var(--ink)"/><circle cx="${x}" cy="${y}" r="3.5" fill="var(--surface)"/>`
        : r.outcome === 'mixed'
          ? `<circle cx="${x}" cy="${y}" r="10" fill="var(--surface)"/><circle cx="${x}" cy="${y}" r="7" fill="var(--surface)" stroke="var(--notyet-line)" stroke-width="2.5"/><circle cx="${x}" cy="${y}" r="2.5" fill="var(--notyet-line)"/>`
          : `<circle cx="${x}" cy="${y}" r="10" fill="var(--surface)"/><circle cx="${x}" cy="${y}" r="7" fill="var(--surface)" stroke="var(--ink-muted)" stroke-width="2"${r.outcome === 'missed' ? ' stroke-dasharray="2.5 2.5"' : ''}/>`;
    return `
          <g class="map-node ${isNew ? 'map-node-done-anim' : ''}" tabindex="0"
             data-tip-title="${attr(`Cycle ${r.cycle}: ${r.title}`)}" data-tip-sub="${attr(`Day ${r.day} · ${JOURNEY_PATH_NAMES[r.path] || 'Advising people you know'} · Rp${r.rp}M a month`)}"
             onmouseenter="showMapTip(this)" onmouseleave="hideMapTip()" onfocus="showMapTip(this)" onblur="hideMapTip()">
            <circle cx="${x}" cy="${y}" r="15" fill="transparent"/>
            ${dot}
          </g>
          <text x="${x}" y="${y + 25}" font-family="Plus Jakarta Sans" font-size="9.5" font-weight="${WORD_COLOR[r.outcome] ? 700 : 500}" text-anchor="middle" fill="${WORD_COLOR[r.outcome] || 'var(--ink-muted)'}" pointer-events="none">${word}</text>
          ${flag ? `<text x="${x}" y="${y + 37}" font-family="Plus Jakarta Sans" font-size="9" font-weight="700" text-anchor="middle" fill="${flag[1]}" stroke="var(--on-ink)" stroke-width="4" paint-order="stroke" pointer-events="none">${flag[0]}</text>` : ''}`;
  }).join('');

  // Cycle columns across the top
  const colState = c => c < rs.currentCycle || rs.ending ? 'past' : (c === rs.currentCycle ? 'now' : 'ahead');
  const headFill = { past: 'var(--ink-3)', now: 'var(--ink)', ahead: 'var(--ink-muted-2)' };
  let columnsSvg = '';
  for (let c = 2; c <= LAST_CYCLE; c++) {
    const x = colX(c), st = colState(c);
    columnsSvg += `
          <line x1="${x - COL / 2}" y1="70" x2="${x - COL / 2}" y2="380" stroke="var(--surface-hover)" stroke-width="1"/>
          ${st === 'now' ? `<rect x="${x - COL / 2 + 4}" y="66" width="${COL - 8}" height="316" rx="10" fill="var(--open-line)" opacity="0.05"/>` : ''}
          <text x="${x}" y="76" font-family="Plus Jakarta Sans" font-size="10" font-weight="700" text-anchor="middle" fill="${headFill[st]}">C${c}</text>
          <text x="${x}" y="88" font-family="Plus Jakarta Sans" font-size="8.5" text-anchor="middle" fill="${st === 'ahead' ? 'var(--border-strong)' : 'var(--ink-muted)'}">Day ${Math.min(c * 7, GOAL_DAY)}</text>`;
  }
  const c1State = colState(1);
  columnsSvg += `
          ${c1State === 'now' ? '<rect x="205" y="66" width="606" height="316" rx="10" fill="var(--open-line)" opacity="0.04"/>' : ''}
          <text x="510" y="76" font-family="Plus Jakarta Sans" font-size="10" font-weight="700" text-anchor="middle" fill="${headFill[c1State]}">C1</text>
          <text x="510" y="88" font-family="Plus Jakarta Sans" font-size="8.5" text-anchor="middle" fill="var(--ink-muted)">Days 1 to 7</text>`;
  const progressKey = `${rs.currentCycle}-${rs.history.length}-${rs.ending || ''}`;
  const stickyLabel = (x, y, color, text) =>
    `<text data-sticky-x="${x}" x="${x}" y="${y}" font-family="Plus Jakarta Sans" font-size="10.5" font-weight="700" fill="${color}" stroke="var(--on-ink)" stroke-width="4" paint-order="stroke">${text}</text>`;

  const pathDetails = {
    warm: {
      label: 'Advising people you know',
      why: 'Two contacts already asked to hear from you when you start. It is the cheapest and fastest way to find out if people will pay.',
      next: (rs.currentCycle === 1 || activeMapPath === 'warm')
        ? `Today (Day ${tl.day}): ${rs.steps[rs.currentStep - 1].label.toLowerCase()}. A first paying client here is what opens the audit path.`
        : 'Your first week on this path is done. Keep it going alongside your current path.',
      action: `<button class="btn-primary" onclick="renderScreen('04')">Go to your next step →</button>`
    },
    agency: {
      label: 'Freelancing for agencies',
      why: "One agency contact is interested but hasn't said how much work they have. A short call this week would tell you.",
      next: "Have a 30-minute call with the agency contact. Ask: what's the work, when is it due, and what does it pay?",
      action: `<button class="btn-secondary" onclick="renderScreen('04')">Go to your next step →</button>`
    },
    audit: auditOpen ? {
      label: 'Fixed-price brand audit',
      why: 'Opened: Sari paid you, and a second contact asked for the same kind of work.',
      next: activeMapPath === 'audit'
        ? `This is your current path. Today (Day ${tl.day}): ${todayStep.label.toLowerCase()}.`
        : 'Open, but not your current path this week. It is proven, so come back to it if the current path stalls.',
      action: `<button class="btn-primary" onclick="renderScreen('04')">Go to your next step →</button>`
    } : {
      label: 'Fixed-price brand audit',
      why: "Opens when: (1) you have at least 1 paying client, and (2) a second contact requests the same type of work.",
      next: "Keep going on Advising people you know. Once Sari signs, this path unlocks automatically.",
      action: `<button class="btn-secondary" disabled style="opacity:0.5;cursor:default">Locked: conditions not met yet</button>`
    },
    cmo: cmoOpen ? {
      label: 'Part-time marketing lead',
      why: "Opened: you've done 2 full-price audits, so you can deliver the same result more than once.",
      next: (twoPathsCompete ? 'Heads up: audits take about 4 h a week and this role needs 5. You have 6 h free, so lead with one of them. ' : '')
        + (activeMapPath === 'cmo' ? `Today (Day ${tl.day}): ${todayStep.label.toLowerCase()}.` : 'Not your current path this week.'),
      action: `<button class="btn-primary" onclick="renderScreen('04')">Go to your next step →</button>`
    } : {
      label: 'Part-time marketing lead',
      why: "Opens after you've done 2 brand audits. That proves you can deliver the same result more than once.",
      next: "Finish the audit path first. This comes later, from the third check-in onward.",
      action: `<button class="btn-secondary" disabled style="opacity:0.5;cursor:default">Locked: 0 of 2 audits done</button>`
    },
    ads: {
      label: 'Paid LinkedIn ads',
      why: "Why not: you don't have a proven offer to advertise yet, and both past clients came from people you know. Getting seen by more people isn't the problem.",
      next: "Wait until at least 1 client has paid for your offer and you have results you can show.",
      action: `<button class="btn-secondary" onclick="openModal()">I want to do this anyway</button>`
    }
  };
  const pdKey = pathDetails[sel] ? sel : 'warm';
  const pd = pathDetails[pdKey];
  if (rs.ending && activeMapPath === pdKey) pd.next = 'Your 90 days are done. The review shows what worked and what to do next.';
  const pdStatus = statuses[pdKey];


  const content = `
  <div class="map-layout">
    <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-shrink:0">
      <h1 class="serif-heading" style="font-size:30px">${rs.ending ? `Day 90: Rp${rs.earned}M a month. ${COUNT_WORDS[openCount]} open.` : goalReached ? `Goal reached: Rp${rs.earned}M a month. ${COUNT_WORDS[openCount]} open.` : `Five ways to Rp${rs.goalRp}M a month. ${COUNT_WORDS[openCount]} open today.`}</h1>
      <div style="font-size:12px;color:var(--ink-3);max-width:300px;text-align:right;line-height:1.45">
        Each column is one week. Scroll sideways to see all 13. Click a path for details, point at a dot for what happened.
      </div>
    </div>

    <!-- SVG path map: takes all the height that's left -->
    <div class="map-body">
    <div class="card-clean map-canvas-card" id="map-canvas-card">
      <div class="map-tip" id="map-tip" hidden></div>
      <div class="map-canvas">
        <svg viewBox="50 62 ${VB_W} 322" preserveAspectRatio="xMinYMid meet" xmlns="http://www.w3.org/2000/svg"
             style="aspect-ratio:${VB_W} / 322" data-vbw="${VB_W}" data-nowx="${nowX}" data-progress-key="${progressKey}">
          ${columnsSvg}

          <!-- Goal: Day 90 -->
          <line x1="${GX}" y1="70" x2="${GX}" y2="380" stroke="${goalReached ? 'var(--open-line)' : 'var(--border-strong)'}" stroke-width="${goalReached ? 1.5 : 1}" stroke-dasharray="3 4"/>

          <!-- START node -->
          <circle cx="72" cy="220" r="10" fill="var(--ink)"/>
          <circle cx="72" cy="220" r="3.5" fill="var(--surface)"/>
          <text x="72" y="240" font-family="Plus Jakarta Sans" font-size="9.5" font-weight="700" text-anchor="middle" fill="var(--ink)">Start</text>
          <text x="72" y="252" font-family="Plus Jakarta Sans" font-size="9" text-anchor="middle" fill="var(--ink-3)">Rp0 / mo</text>

          <!-- LANE 2: Freelancing for agencies - TEST FIRST (blue dotted, branches up off the main line) -->
          <g class="${laneClass('agency')}" ${laneClick('agency')}>
            ${halo('agency', AGENCY_D, 'var(--test-line)')}
            ${hit(AGENCY_D)}
            <path d="${AGENCY_D}" fill="none" stroke="var(--test-line)" stroke-width="2.5" stroke-dasharray="2 6" stroke-linecap="round"/>
            <circle cx="430" cy="158" r="8" fill="var(--surface)" stroke="var(--test-line)" stroke-width="2" stroke-dasharray="2 4"/>
            <text x="430" y="162" font-family="Plus Jakarta Sans" font-size="9.5" text-anchor="middle" fill="var(--test-line)">?</text>
            ${stickyLabel(312, 146, 'var(--test-line)', 'Freelancing for agencies · TEST FIRST')}
          </g>

          <!-- LANE 5: Paid LinkedIn Ads - STOP (red, branches up and dead-ends early) -->
          <g class="${laneClass('ads')}" ${laneClick('ads')}>
            ${halo('ads', ADS_D, 'var(--stop-line)')}
            ${hit(ADS_D)}
            <path d="${ADS_D}" fill="none" stroke="var(--stop-line)" stroke-width="2.5"/>
            <line x1="314" y1="96" x2="330" y2="112" stroke="var(--stop-fg)" stroke-width="2.5" stroke-linecap="round"/>
            <line x1="330" y1="96" x2="314" y2="112" stroke="var(--stop-fg)" stroke-width="2.5" stroke-linecap="round"/>
            <text x="230" y="123" font-family="Plus Jakarta Sans" font-size="10" font-weight="700" fill="var(--stop-fg)">Paid LinkedIn ads · STOP</text>
          </g>

          <!-- LANE 4: Part-time marketing lead (branches down off the main line when the cycle opens it) -->
          <g class="${laneClass('cmo')} ${cmoJustOpened ? 'map-lane-unlock-anim' : ''}" ${laneClick('cmo')}>
            ${halo('cmo', CMO_D, cmoOpen ? 'var(--open-line)' : 'var(--notyet-line)')}
            ${hit(CMO_D)}
            ${cmoOpen ? `
            <path d="${CMO_D}" fill="none" stroke="var(--open-line)" stroke-width="3" stroke-linecap="round" opacity="0.35"/>
            ${stickyLabel(cmoBx + 98, 266, 'var(--open-fg)', 'Part-time marketing lead · OPEN')}` : `
            <path d="${CMO_D}" fill="none" stroke="var(--notyet-line)" stroke-width="1.8" stroke-dasharray="6 5"/>
            <g transform="translate(${cmoBx + 80}, 275)">
              <rect x="1" y="5" width="10" height="7" rx="1.5" fill="none" stroke="var(--notyet-line)" stroke-width="1.3"/>
              <path d="M3 5V3.5a3 3 0 0 1 6 0V5" fill="none" stroke="var(--notyet-line)" stroke-width="1.3"/>
            </g>
            ${stickyLabel(cmoBx + 98, 266, 'var(--notyet-fg)', 'Part-time marketing lead · NOT YET')}`}
          </g>

          <!-- LANE 3: Fixed-price audit (branches down from "First paid client"; opens when both conditions are met) -->
          <g class="${laneClass('audit')} ${auditJustOpened ? 'map-lane-unlock-anim' : ''}" ${laneClick('audit')}>
            ${halo('audit', AUDIT_D, auditOpen ? 'var(--open-line)' : 'var(--notyet-line)')}
            ${hit(AUDIT_D)}
            ${auditOpen ? `
            <path d="${AUDIT_D}" fill="none" stroke="var(--open-line)" stroke-width="3" stroke-linecap="round" opacity="0.35"/>
            ${stickyLabel(742, 322, 'var(--open-fg)', 'Fixed-price audit · OPEN')}` : `
            <path d="${AUDIT_D}" fill="none" stroke="var(--notyet-line)" stroke-width="2" stroke-dasharray="7 5"/>
            <g transform="translate(728, 331)">
              <rect x="1" y="5" width="10" height="7" rx="1.5" fill="none" stroke="var(--notyet-line)" stroke-width="1.3"/>
              <path d="M3 5V3.5a3 3 0 0 1 6 0V5" fill="none" stroke="var(--notyet-line)" stroke-width="1.3"/>
            </g>
            ${stickyLabel(746, 322, 'var(--notyet-fg)', 'Fixed-price audit · NOT YET')}`}
          </g>

          <!-- LANE 1: Advising people you know - OPEN (the main line, straight from Start to Goal) -->
          <g class="${laneClass('warm')}">
            <g ${laneClick('warm')} style="cursor:pointer">
              ${halo('warm', WARM_D, 'var(--open-line)')}
              ${hit(WARM_D)}
              <path d="${WARM_D}" fill="none" stroke="var(--open-line)" stroke-width="3" stroke-linecap="round" opacity="0.35"/>
              ${stickyLabel(250, 202, 'var(--open-fg)', 'Advising people you know · OPEN')}
            </g>
          </g>

          <!-- The route travelled so far (always on top, never dimmed) -->
          ${!rs.ending ? `<path class="route-ahead" d="M ${routeEnd.x} ${routeEnd.y} ${routeEnd.y === 220 ? `L ${GX} 220` : `L ${GX - 72} ${routeEnd.y} C ${GX - 36} ${routeEnd.y} ${GX - 36} 220 ${GX} 220`}" fill="none" stroke="var(--open-line)" stroke-width="2.5" stroke-linecap="round" opacity="0.45" pointer-events="none"/>` : ''}
          <path id="map-progress" d="${routeD}" fill="none" stroke="var(--open-line)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" pointer-events="none"/>
          <circle cx="${GX}" cy="220" r="10" fill="var(--surface)"/>
          ${goalReached
            ? `<circle cx="${GX}" cy="220" r="15" fill="var(--open-line)" opacity="0.18"/><circle cx="${GX}" cy="220" r="8" fill="var(--open-line)"/>`
            : `<circle cx="${GX}" cy="220" r="4.5" fill="var(--surface)" stroke="var(--ink-muted)" stroke-width="2"/>`}
          <text x="${GX - 14}" y="200" font-family="Plus Jakarta Sans" font-size="10.5" font-weight="700" text-anchor="end" fill="${goalReached ? 'var(--open-fg)' : 'var(--ink-3)'}" stroke="var(--surface)" stroke-width="4" paint-order="stroke">${goalReached ? '✓ Goal reached' : `Goal · Rp${rs.goalRp}M / month`}</text>
          <text x="${GX - 14}" y="212" font-family="Plus Jakarta Sans" font-size="8.5" text-anchor="end" fill="var(--ink-muted)" stroke="var(--surface)" stroke-width="4" paint-order="stroke">Day 90</text>
          ${milestoneSvg}
          ${checkpointSvg}
          ${nowPt ? activeNode(nowPt.x, nowPt.y) : ''}
        </svg>
      </div>

      <!-- Legend -->
      <div class="map-legend">
        <span style="display:flex;align-items:center;gap:6px"><svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="var(--open-line)" stroke-width="3"/></svg> Open</span>
        <span style="display:flex;align-items:center;gap:6px"><svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="var(--test-line)" stroke-width="2.5" stroke-dasharray="2 6" stroke-linecap="round"/></svg> Test first</span>
        <span style="display:flex;align-items:center;gap:6px"><svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="var(--notyet-line)" stroke-width="2" stroke-dasharray="7 4"/></svg> Not yet: locked until conditions are met</span>
        <span style="display:flex;align-items:center;gap:6px"><svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="var(--stop-line)" stroke-width="2.5"/></svg>✕ Stop: the facts say no</span>
        <span style="display:flex;align-items:center;gap:6px;margin-left:auto"><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="var(--open-line)"/></svg> Paid</span>
        <span style="display:flex;align-items:center;gap:6px"><svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="var(--surface)" stroke="var(--notyet-line)" stroke-width="2"/></svg> Mixed</span>
        <span style="display:flex;align-items:center;gap:6px"><svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="var(--surface)" stroke="var(--ink-muted)" stroke-width="1.5"/></svg> Quiet or missed</span>
        <span style="display:flex;align-items:center;gap:6px"><svg width="16" height="16"><circle cx="8" cy="8" r="7" fill="var(--open-line)" opacity="0.15"/><circle cx="8" cy="8" r="4.5" fill="var(--surface)" stroke="var(--ink)" stroke-width="2"/></svg> Today</span>
      </div>
    </div>

    <!-- Path selector + detail (fixed, compact height) -->
    <aside class="map-bottom" aria-label="Selected path">
      <div class="card-clean map-detail">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;flex-shrink:0">
          <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
            <h2 style="font-family:var(--font-ui);font-size:17px;font-weight:700">${pd.label}</h2>
            ${activeMapPath === pdKey ? `<span style="font-family:var(--font-ui);font-size:11.5px;font-weight:600;color:var(--open-fg)">● Your current path · Day ${tl.day}</span>` : ''}
          </div>
          <span class="status-pill ${pdStatus.toLowerCase()}">${pdStatus.replace('_', ' ')}</span>
        </div>
        <div class="map-detail-body">
          <div>
            <div class="section-meta-label" style="margin-bottom:2px">Why this status</div>
            <p style="font-size:13px;color:var(--ink-2);line-height:1.5;margin:0">${pd.why}</p>
          </div>
          <div>
            <div class="section-meta-label" style="margin-bottom:2px">Next step</div>
            <p style="font-size:13px;color:var(--ink-2);line-height:1.5;margin:0">${pd.next}</p>
          </div>
        </div>
        ${renderMapNeed(demoReadiness().paths.find(p => p.key === pdKey))}
        <div class="map-actions">
          ${rs.ending && !pd.action.includes('openModal') && !pd.action.includes('disabled') ? `<button class="btn-primary" onclick="renderScreen('16')">See your Day 90 review →</button>` : pd.action}
          <button class="btn-secondary" onclick="openReadiness('${pdKey}')">What it needs →</button>
          <button class="btn-secondary" onclick="renderScreen('08')">See your progress →</button>
        </div>
      </div>
    </aside>
    </div>
  </div>`;
  return renderAppShell('map', 'Path map', content);
}

// Map node tooltip (labels are hidden on the curve to keep it clean)
function showMapTip(el) {
  const tip = document.getElementById('map-tip');
  const card = document.getElementById('map-canvas-card');
  if (!tip || !card) return;
  const dot = el.getBoundingClientRect();
  const box = card.getBoundingClientRect();
  tip.innerHTML = `<div class="map-tip-title">${esc(el.dataset.tipTitle)}</div><div class="map-tip-sub">${esc(el.dataset.tipSub)}</div>`;   // dataset is decoded text: escape again before innerHTML
  tip.hidden = false;
  const half = tip.offsetWidth / 2;
  const x = dot.left + dot.width / 2 - box.left;
  tip.style.left = Math.max(half + 8, Math.min(x, box.width - half - 8)) + 'px';
  tip.style.top = (dot.top - box.top) + 'px';
}
function hideMapTip() {
  const tip = document.getElementById('map-tip');
  if (tip) tip.hidden = true;
}

// Draw the solid route forward from where it was on the previous visit to the new checkpoint
function animateMapProgress() {
  setupMapScroll();
  const path = document.getElementById('map-progress');
  if (!path) return;
  const len = path.getTotalLength();
  const prev = MAP_MEMORY.progressLen === null ? 0 : Math.min(MAP_MEMORY.progressLen, len);
  MAP_MEMORY.progressLen = len;
  if (prev === len || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  path.style.transition = 'none';
  path.style.strokeDasharray = `${len}`;
  path.style.strokeDashoffset = `${len - prev}`;
  path.getBoundingClientRect();
  path.style.transition = 'stroke-dashoffset 0.9s cubic-bezier(0.4, 0, 0.2, 1)';
  path.style.strokeDashoffset = '0';
}

// Sideways scroll: keep the reader's place on a plain re-render, glide to "now" when progress changed.
// Lane names slide along the left edge so you always know which lane you're looking at.
function setupMapScroll() {
  const box = document.querySelector('.map-canvas');
  const svg = box && box.querySelector('svg');
  if (!svg) return;
  const VB_X = 50;
  const scale = () => { const w = svg.getBoundingClientRect().width; return w ? w / Number(svg.dataset.vbw) : 1; };   // detached/hidden svg: width 0 must not become NaN
  const targetLeft = () => Math.max(0, (Number(svg.dataset.nowx) - VB_X) * scale() - box.clientWidth * 0.6);
  const placeLabels = () => {
    const left = VB_X + box.scrollLeft / scale() + 14;
    svg.querySelectorAll('[data-sticky-x]').forEach(t => t.setAttribute('x', Math.max(Number(t.dataset.stickyX), left)));
  };
  let userScrolled = false;
  ['wheel', 'pointerdown', 'keydown', 'touchstart'].forEach(ev => box.addEventListener(ev, () => { userScrolled = true; MAP_MEMORY.gliding = false; }, { passive: true }));
  box.addEventListener('scroll', () => {
    if (!document.body.contains(box)) return;      // a smooth glide can still fire after the map was re-rendered
    MAP_MEMORY.scrollLeft = box.scrollLeft;
    if (Math.abs(box.scrollLeft - targetLeft()) < 2) MAP_MEMORY.gliding = false;
    placeLabels(); hideMapTip();
  }, { passive: true });
  const key = svg.dataset.progressKey;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (MAP_MEMORY.scrollKey === key && MAP_MEMORY.scrollLeft !== null) {
    box.scrollLeft = MAP_MEMORY.scrollLeft;
    // A re-render in the middle of the glide to "now" keeps gliding instead of freezing halfway
    if (MAP_MEMORY.gliding) box.scrollTo({ left: targetLeft(), behavior: reduced ? 'auto' : 'smooth' });
    else userScrolled = true;
  } else if (MAP_MEMORY.scrollLeft === null || reduced) {
    box.scrollLeft = targetLeft();
  } else {
    box.scrollLeft = MAP_MEMORY.scrollLeft;
    MAP_MEMORY.gliding = true;
    box.scrollTo({ left: targetLeft(), behavior: 'smooth' });
  }
  MAP_MEMORY.scrollKey = key;
  MAP_MEMORY.scrollLeft = box.scrollLeft;
  placeLabels();
  // The canvas can change size after render (fonts, window resize): keep "now" in view and labels on the edge
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      if (!document.body.contains(box)) return;
      if (!userScrolled) box.scrollLeft = targetLeft();
      placeLabels();
    }).observe(svg);
  }
}

function selectMapPath(id) {
  STORE.selectedMapPath = id;
  renderScreen('07');
}

/* ── Screen 08 · Journey (AppShell + Sidebar 256px) ─────────────────────── */
const JOURNEY_PATH_NAMES = {
  audit: 'Fixed-price brand audit',
  warm_starter: 'Advising people you know · Smaller offer',
  warm_retest: 'Advising people you know · Trying again',
  warm: 'Advising people you know',
  cmo: 'Part-time marketing lead'
};
/* Sample workspaces only (demo mode): what the Journey says about the day the map began. A user's own map gets none. */
const JOURNEY_START = {
  dimas: ['Main problem: no written offer yet', 'Office rent and paid ads put on hold · Rp20M kept in the bank'],
  rina: ['No settled explanation yet: three are still close', 'Office, ads and registering a company put on hold'],
  bayu: ['Safety first: savings cover about 5 weeks', 'Ads, courses and an office put on hold'],
  arif: ['Main limit: about 6 free hours a week', 'Jobs that would go past your hours put on hold']
};
const OUTCOME_STYLE = {
  worked: { label: 'Paid', color: 'var(--open-line)', pill: 'open' },
  mixed: { label: 'Mixed', color: 'var(--notyet-line)', pill: 'not_yet' },
  none: { label: 'No replies', color: 'var(--ink-muted)', pill: '' },
  missed: { label: 'Missed', color: 'var(--ink-muted)', pill: '' },
  final: { label: 'Day 90', color: 'var(--ink)', pill: '' }
};
const EVENT_FLAGS = { 'audit-open': 'Audit opened', 'welcome-back': 'Missed check-in', ads: 'Ads test', 'cmo-open': 'Marketing lead opened', capacity: 'Not enough hours' };
/* screen08 (v9 Journey) was removed in the 2026-10-15 legacy cleanup — only reachable via 'v9:08';
   Journey is now the 'journey' destination (screenJourney11, screens-live-map.js). The journey constants
   above stay: used by screenJourney11 + screen16 + screens-other. */

function showJourneyTip(el, i) {
  const n = (window.__journeyNodes || [])[i];
  const tip = document.getElementById('j-tip');
  const wrap = document.getElementById('j-root');
  if (!n || !tip || !wrap) return;
  const ring = el.querySelector('.j-ring').getBoundingClientRect();
  const box = wrap.getBoundingClientRect();
  const x = ring.left + ring.width / 2 - box.left;
  const y = ring.top + ring.height / 2 - box.top;
  tip.innerHTML = `
    <div class="j-tip-label">${esc(n.label)}</div>
    <div class="j-tip-title">${esc(n.title)}</div>
    ${n.rows.map(r => `<div class="j-tip-row">${esc(r)}</div>`).join('')}
    <div class="j-tip-saved">${esc(n.saved)}</div>`;
  tip.hidden = false;
  const half = tip.offsetWidth / 2;
  tip.style.left = Math.max(half, Math.min(x, box.width - half)) + 'px';
  const below = y < tip.offsetHeight + 24;
  tip.style.top = y + 'px';
  tip.style.transform = below ? 'translate(-50%, 18px)' : 'translate(-50%, calc(-100% - 18px))';
}

function hideJourneyTip() {
  const tip = document.getElementById('j-tip');
  if (tip) tip.hidden = true;
}
