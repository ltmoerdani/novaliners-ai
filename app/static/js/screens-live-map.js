/* LIVE screens 07 (Path map) and 08 (Journey). Same SVG language and layout as prototype v9; lanes, status,
 * checkpoints and the income curve come from the real artifact, the user's reports and path states. */

/* Goal-Relative (int 09 par 6 MAPS, A-28): the goal label speaks the ACTIVE metric's unit.
 * Non-revenue values come from the engine's own goal context (snapshot.goal.metric) — never
 * from the revenue slots; revenue wording stays only for revenue goals. */
function mapGoalView() {
  const g = liveGoal();
  const gmet = (V11_ENGINE.snapshot().goal || {}).metric || null;
  const nonRevenue = !!(gmet && gmet.id !== 'revenue_monthly');
  const tgt = nonRevenue ? (gmet.target != null ? gmet.target : null) : (g.target != null ? g.target : null);
  const now = nonRevenue ? (gmet.current != null ? gmet.current : null) : (g.current != null ? g.current : null);
  const tgtLabel = tgt == null
    ? (nonRevenue ? (gmet.name || 'your goal').toLowerCase() : 'growth')
    : (nonRevenue ? fmtGoalValue(gmet, tgt) + ' ' + (gmet.name || '').toLowerCase() : fmtM(tgt) + ' a month');
  const nowLabel = now == null ? null : (nonRevenue ? fmtGoalValue(gmet, now) : fmtM(now));
  const decrease = !!(gmet && (gmet.direction === 'DECREASE_TO_THRESHOLD' || gmet.direction === 'AT_MOST'));
  const reached = tgt != null && now != null && (decrease ? now <= tgt : now >= tgt);
  return { g, gmet, nonRevenue, tgt, now, tgtLabel, nowLabel, reached, decrease };
}

/* Slot geometry, git-graph style: the recommended path (slot 1) runs straight from Start to Goal; the other
 * paths branch off the main line with smooth S-curves — the earlier a path branches, the further its lane
 * sits from the main line (two lanes up, two down), so branches never cross. */
function slotGeom(slot, GX, cmoBx, full) {
  // Full lanes curve back into the goal point at the end of the main line, like a git merge
  const endD = (y, end) => end === GX
    ? `L ${GX - 72} ${y} C ${GX - 36} ${y} ${GX - 36} 220 ${GX} 220`
    : `L ${end} ${y}`;
  const branch = (bx, y, end) => ({ d: `M ${bx} 220 C ${bx + 36} 220 ${bx + 36} ${y} ${bx + 72} ${y} ${endD(y, end)}`, y, end });
  switch (slot) {
    case 1: return { d: `M 82 220 L ${GX} 220`, y: 220, end: GX, sticky: [250, 202], mid: [400, 220], lock: [232, 213] };
    case 2: return { ...branch(214, 158, full ? GX : 560), sticky: [312, 146], mid: [430, 158], lock: [294, 151] };
    case 3: return { ...branch(150, 104, GX), sticky: [248, 123], mid: [470, 104], lock: [230, 97] };
    case 4: return { d: `M ${cmoBx} 220 C ${cmoBx + 36} 220 ${cmoBx + 36} 282 ${cmoBx + 72} 282 ${endD(282, GX)}`, y: 282, end: GX, sticky: [cmoBx + 98, 266], mid: [cmoBx + 130, 282], lock: [cmoBx + 80, 275] };
    case 5: return { ...branch(150, 338, full ? GX : 330), sticky: [230, 322], mid: [275, 338], lock: [212, 331] };
    default: {
      // Any further path (the engine forms 0..N): lanes alternate above and below the first five, 54px apart,
      // branching a little earlier each time so branches still never cross.
      const k = slot - 5, ring = Math.ceil(k / 2), up = k % 2 === 1;
      const y = up ? 104 - 54 * ring : 338 + 54 * ring;
      const bx = Math.max(96, 150 - 12 * ring);
      return { ...branch(bx, y, GX), sticky: [bx + 80, y - 16], mid: [bx + 320, y], lock: [bx + 62, y - 7] };
    }
  }
}

/* Vertical extent of the map: the classic 62..384 window for up to five lanes. The map draws at most PATH_VIEW_CAP (five)
 * lanes (present-cap.js), so the wider window is only for a caller that draws more; it is not how the screen behaves today. */
function mapExtent(slots) {
  const ys = Object.values(slots).map(sl => slotGeom(sl, 900, 900, true).y);
  return { top: Math.min(62, Math.min(...ys, 220) - 42), bottom: Math.max(384, Math.max(...ys, 220) + 46) };
}

/* Path → slot: the active path takes the main lane; the rest fan out by status. */
function assignSlots(paths, activeKey) {
  const slots = {};
  const used = new Set([1]);
  const pref = { OPEN: [2, 3, 4, 5], TEST_FIRST: [2, 5, 3, 4], NOT_YET: [3, 4, 2, 5], STOP: [5, 4, 3, 2] };
  // the first five slots are placed by status preference; any further path takes the next free slot (6, 7, ...)
  const nextFree = () => { let n = 2; while (used.has(n)) n++; return n; };
  const act = paths.find(p => p.key === activeKey) || paths[0];
  if (act) slots[act.key] = 1;
  ['OPEN', 'TEST_FIRST', 'NOT_YET', 'STOP'].forEach(st => {
    paths.filter(p => p.key !== (act && act.key) && p.status === st).forEach(p => {
      const s = pref[st].find(x => !used.has(x)) || nextFree();
      used.add(s); slots[p.key] = s;
    });
  });
  return slots;
}

const MAP_TXT = 'font-family="Plus Jakarta Sans"';
function laneSvg(p, g, sel, geomKey) {
  const id = p.key, isSel = sel === id;
  const halo = c => isSel ? `<path d="${g.d}" fill="none" stroke="${c}" stroke-width="12" stroke-linecap="round" opacity="0.14"/>` : '';
  const hit = `<path d="${g.d}" fill="none" stroke="transparent" stroke-width="18" pointer-events="stroke"/>`;
  const sticky = (x, y, color, text) => `<text data-sticky-x="${x}" x="${x}" y="${y}" ${MAP_TXT} font-size="10.5" font-weight="700" fill="${color}" stroke="var(--on-ink)" stroke-width="4" paint-order="stroke">${esc(text)}</text>`;
  let inner;
  if (p.status === 'OPEN') {
    inner = `${halo('var(--open-line)')}${hit}
      <path d="${g.d}" fill="none" stroke="var(--open-line)" stroke-width="3" stroke-linecap="round" opacity="0.35"/>
      <circle cx="${g.end}" cy="${g.y}" r="5" fill="var(--open-line)" opacity="0.85"/>
      ${sticky(g.sticky[0], g.sticky[1], 'var(--open-fg)', `${p.name} · OPEN`)}`;
  } else if (p.status === 'TEST_FIRST') {
    inner = `${halo('var(--test-line)')}${hit}
      <path d="${g.d}" fill="none" stroke="var(--test-line)" stroke-width="2.5" stroke-dasharray="2 6" stroke-linecap="round"/>
      <circle cx="${g.mid[0]}" cy="${g.mid[1]}" r="8" fill="var(--surface)" stroke="var(--test-line)" stroke-width="2" stroke-dasharray="2 4"/>
      <text x="${g.mid[0]}" y="${g.mid[1] + 4}" ${MAP_TXT} font-size="9.5" text-anchor="middle" fill="var(--test-line)">?</text>
      ${sticky(g.sticky[0], g.sticky[1], 'var(--test-line)', `${p.name} · TEST FIRST`)}`;
  } else if (p.status === 'NOT_YET') {
    inner = `${halo('var(--notyet-line)')}${hit}
      <path d="${g.d}" fill="none" stroke="var(--notyet-line)" stroke-width="2" stroke-dasharray="7 5"/>
      <g transform="translate(${g.lock[0]}, ${g.lock[1]})"><rect x="1" y="5" width="10" height="7" rx="1.5" fill="none" stroke="var(--notyet-line)" stroke-width="1.3"/><path d="M3 5V3.5a3 3 0 0 1 6 0V5" fill="none" stroke="var(--notyet-line)" stroke-width="1.3"/></g>
      ${sticky(g.sticky[0], g.sticky[1], 'var(--notyet-fg)', `${p.name} · NOT YET`)}`;
  } else {
    const ex = g.end - 8;
    inner = `${halo('var(--stop-line)')}${hit}
      <path d="${g.d}" fill="none" stroke="var(--stop-line)" stroke-width="2.5"/>
      <line x1="${ex - 8}" y1="${g.y - 8}" x2="${ex + 8}" y2="${g.y + 8}" stroke="var(--stop-fg)" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="${ex + 8}" y1="${g.y - 8}" x2="${ex - 8}" y2="${g.y + 8}" stroke="var(--stop-fg)" stroke-width="2.5" stroke-linecap="round"/>
      <text x="${g.sticky[0]}" y="${g.sticky[1]}" ${MAP_TXT} font-size="10" font-weight="700" fill="var(--stop-fg)">${esc(p.name)} · STOP</text>`;
  }
  return `<g class="map-lane ${isSel ? 'selected' : 'dim'}" onclick="selectMapPath('${id}')" role="button" tabindex="0" aria-label="${esc(p.name)}: ${STATUS_WORD[p.status]}" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();selectMapPath('${id}')}">${inner}</g>`;
}

/* [DEAD 2026-10-15] v9-only live map screen: reachable only via 'v9:07', which has been removed;
   the Maps destination now uses screenMaps11 in this file. Its exclusive functions & helpers (screen07ZeroLive, etc.)
   are safe to delete physically in a mechanical follow-up (node --check + make test-ui). */
function screen07Live() {
  const rs = useRoadmapStore.getState();
  const tl = getTimeline();
  liveEnsureExplain();   // no-op unless the plain-language rewrite has not been asked for yet
  const allPaths = livePathModels();   // the engine forms 0..N possibilities; this is all of them
  const g = liveGoal();
  if (!allPaths.length && liveNoPaths()) return renderAppShell('map', 'Path map', `<div class="today-layout" style="grid-template-columns:minmax(0,620px);justify-content:center;align-content:center"><div class="no-paths-stack">${liveNoPathsHtml()}${liveEmergingHtml()}</div></div>`);
  if (!allPaths.length) return renderAppShell('map', 'Path map', `<div class="today-layout" style="grid-template-columns:minmax(0,560px);justify-content:center;align-content:center"><div class="card-clean" style="padding:28px;text-align:center"><h1 class="serif-heading" style="font-size:28px">No map yet.</h1><p style="font-size:14px;color:var(--ink-2);margin:10px 0 16px">Your paths appear once the diagnosis is done.</p><button class="btn-primary" onclick="renderScreen('${LIVE.sid ? '02' : '01'}')">Continue →</button></div></div>`);
  const openCount = allPaths.filter(p => p.status === 'OPEN').length;
  const activeKey = rs.activePathId;
  const sel = allPaths.find(p => p.key === STORE.selectedMapPath) ? STORE.selectedMapPath : activeKey;
  // Presentation cap (present-cap.js): the map draws at most five lanes. The current path, the one being looked at
  // and the paths already travelled always stay on it; the rest is said out loud in the overflow card below.
  const travelled = LIVE.checkins.slice().reverse().map(r => r.path);
  const pres = presentPaths(allPaths, { pinned: [activeKey, sel].concat(travelled) });
  const paths = pres.visible;
  const slots = assignSlots(paths, activeKey);
  const active = allPaths.find(p => p.key === activeKey);
  const ext = mapExtent(slots), VB_H = ext.bottom - ext.top;

  /* Timeline (cycle columns) */
  const cl = tl.cycleLen, H = tl.horizon;
  const LAST_CYCLE = Math.max(2, Math.ceil(H / cl));
  const COL = 130;
  const colX = c => 880 + (c - 2) * COL;
  const GX = colX(LAST_CYCLE) + 110;
  const VB_W = GX + 80 - 50;
  const cmoBx = colX(Math.min(rs.currentCycle + 1, LAST_CYCLE - 1)) + 10;

  /* Milestones on the main lane: this cycle's steps, then what a result does */
  const steps = rs.steps.filter(s => !s.report && !s.hold).concat(rs.steps.filter(s => s.report));
  const nSteps = Math.max(steps.length, 1);
  const stepX = i => nSteps === 1 ? 250 : Math.round(250 + i * (280 / (nSteps - 1)));
  const gotResult = LIVE.checkins.length >= 1;
  const allStepsDone = steps.every(s => s.status === STEP_STATUS.COMPLETED || s.report);
  const milestones = steps.map((st, i) => ({ id: st.id, x: stepX(i), word: st.mapLabel, title: st.label, when: st.dayLabel, status: st.status,
    ready: st.ready, doneDay: st.doneDay, wait: st.ready === false ? stepWaitNote(st, rs.steps) : '' }));
  milestones.push({
    id: 'result', x: 650, word: 'Result', title: 'A result that moved something', when: 'Can open more paths',
    status: gotResult ? STEP_STATUS.COMPLETED : (allStepsDone && rs.currentCycle === 1 ? STEP_STATUS.CURRENT : STEP_STATUS.UPCOMING)
  });
  milestones.push({
    id: 'recheck', x: 770, word: 'Re-check', title: 'The next check-in re-checks every path', when: 'Follow-up check-in',
    status: LIVE.chain.length >= 2 ? STEP_STATUS.COMPLETED : (gotResult ? STEP_STATUS.CURRENT : STEP_STATUS.UPCOMING)
  });
  const currentMs = milestones.find(m => m.status === STEP_STATUS.CURRENT);
  const lastDone = milestones.filter(m => m.status === STEP_STATUS.COMPLETED).pop();
  // Steps can be finished in any order: the route travelled runs up to the furthest milestone reached
  const progressX = Math.max(250, currentMs ? currentMs.x : 0, ...milestones.filter(m => m.status === STEP_STATUS.COMPLETED).map(m => m.x));

  const doneIds = milestones.filter(m => m.status === STEP_STATUS.COMPLETED).map(m => m.id);
  const newlyDone = MAP_MEMORY.doneIds ? doneIds.filter(id => !MAP_MEMORY.doneIds.includes(id)) : [];
  const newlyCurrent = currentMs && MAP_MEMORY.currentId !== null && MAP_MEMORY.currentId !== currentMs.id ? currentMs.id : null;
  MAP_MEMORY.doneIds = doneIds;
  MAP_MEMORY.currentId = currentMs ? currentMs.id : '';

  const tipSub = m => m.status === STEP_STATUS.COMPLETED ? (m.when ? `Done · ${m.when}` : 'Done')
    : (m.status === STEP_STATUS.CURRENT ? `Start here · ${m.when}`
      : (m.ready === true ? `Ready now · ${m.when}` : (m.ready === false ? `${m.wait} · ${m.when}` : `Coming up · ${m.when}`)));
  const attr = v => String(v).replace(/"/g, '&quot;');
  const tipAttrs = m => `tabindex="0" data-tip-title="${attr(m.title)}" data-tip-sub="${attr(tipSub(m))}"
            onmouseenter="showMapTip(this)" onmouseleave="hideMapTip()" onfocus="showMapTip(this)" onblur="hideMapTip()"`;
  const nodeWord = (x, y, word, status) => {
    const style = status === STEP_STATUS.CURRENT ? 'font-weight="700" fill="var(--ink)"'
      : (status === STEP_STATUS.COMPLETED ? 'font-weight="600" fill="var(--open-fg)"' : 'fill="var(--ink-muted)"');
    return `<text x="${x}" y="${y}" ${MAP_TXT} font-size="9.5" text-anchor="middle" ${style} pointer-events="none">${esc(word)}</text>`;
  };
  function milestoneNode(m) {
    if (m.status === STEP_STATUS.COMPLETED) return `
          <g class="map-node ${newlyDone.includes(m.id) ? 'map-node-done-anim' : ''}" ${tipAttrs(m)}>
            <circle cx="${m.x}" cy="220" r="14" fill="transparent"/>
            <circle cx="${m.x}" cy="220" r="10" fill="var(--surface)"/>
            <circle cx="${m.x}" cy="220" r="7" fill="var(--open-line)" stroke="var(--open-line)" stroke-width="2"/>
            <text x="${m.x}" y="223.5" ${MAP_TXT} font-size="8" font-weight="700" text-anchor="middle" fill="var(--surface)">✓</text>
          </g>`;
    if (m.status === STEP_STATUS.CURRENT) return `
          <g class="map-node ${m.id === newlyCurrent ? 'map-node-unlock-anim' : ''}" ${tipAttrs(m)}>
            <circle cx="${m.x}" cy="220" r="14" fill="var(--surface)"/>
            <circle cx="${m.x}" cy="220" r="17" fill="var(--open-line)" opacity="0.12"/>
            <circle class="map-pulse" cx="${m.x}" cy="220" r="10" fill="none" stroke="var(--open-line)" stroke-width="2"/>
            <circle cx="${m.x}" cy="220" r="9" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.5"/>
            <circle cx="${m.x}" cy="220" r="3.5" fill="var(--ink)"/>
          </g>`;
    if (m.ready === false) return `
          <g class="map-node" ${tipAttrs(m)}>
            <circle cx="${m.x}" cy="220" r="14" fill="transparent"/>
            <circle cx="${m.x}" cy="220" r="10" fill="var(--surface)"/>
            <circle cx="${m.x}" cy="220" r="6" fill="var(--surface)" stroke="var(--border-strong)" stroke-width="2" stroke-dasharray="3 2"/>
          </g>`;
    return `
          <g class="map-node" ${tipAttrs(m)}>
            <circle cx="${m.x}" cy="220" r="14" fill="transparent"/>
            <circle cx="${m.x}" cy="220" r="10" fill="var(--surface)"/>
            <circle cx="${m.x}" cy="220" r="6" fill="var(--surface)" stroke="var(--open-line)" stroke-width="2" opacity="0.7"/>
          </g>`;
  }
  const milestoneSvg = milestones.map(m => nodeWord(m.x, 245, m.word, m.status) + milestoneNode(m)).join('');

  /* Travelled route: this map's steps, then one checkpoint per finished cycle on the lane that was used */
  const laneY = key => slotGeom(slots[key] || 1, GX, cmoBx, true).y;
  const hist = LIVE.checkins.filter(r => r.cycle >= 2);
  const routePts = hist.map(r => ({ x: colX(r.cycle), y: laneY(r.path) }));
  const nowPt = !rs.ending && rs.currentCycle >= 2 ? { x: colX(rs.currentCycle), y: laneY(activeKey) } : null;
  if (nowPt) routePts.push(nowPt);
  const c1End = rs.currentCycle === 1 ? progressX : (lastDone ? lastDone.x : 250);
  let routeD = `M 82 220 L ${c1End} 220`;
  let routeEnd = { x: c1End, y: 220 };
  routePts.forEach(p => {
    const dx = Math.min(36, Math.max(12, (p.x - routeEnd.x) / 2));
    routeD += p.y === routeEnd.y ? ` L ${p.x} ${p.y}`
      : ` C ${routeEnd.x + dx} ${routeEnd.y} ${routeEnd.x + dx} ${p.y} ${routeEnd.x + dx * 2} ${p.y} L ${p.x} ${p.y}`;
    routeEnd = p;
  });
  const gv = mapGoalView();
  const gmet = gv.gmet;
  const gTgt = gv.tgt;
  const decreaseDir = gv.decrease;
  /* Reached: revenue goals keep the recorded earning basis; non-revenue goals compare the
     metric's own measured value (never income vs leads). */
  const reachedVal = gv.nonRevenue ? gv.now : rs.earned;
  const goalReached = gTgt != null && reachedVal != null && (decreaseDir ? reachedVal <= gTgt : reachedVal >= gTgt);
  if (rs.ending && goalReached) routeD += ` L ${GX} ${routeEnd.y}`;
  const nowX = rs.ending ? GX : (nowPt ? nowPt.x : progressX);

  const prevHist = MAP_MEMORY.histLen;
  MAP_MEMORY.histLen = LIVE.checkins.length;
  const OUTCOME_WORD = { mixed: 'Mixed', none: 'Quiet', missed: 'Missed', final: 'Day ' + H };
  const WORD_COLOR = { worked: 'var(--open-fg)', mixed: 'var(--notyet-fg)', final: 'var(--ink)' };
  const checkpointSvg = hist.map(r => {
    const x = colX(r.cycle), y = laneY(r.path);
    const isNew = prevHist !== null && LIVE.checkins.indexOf(r) >= prevHist;
    const word = r.outcome === 'worked' ? (r.paid ? `+${fmtM(r.paid)}` : 'Paid') : (OUTCOME_WORD[r.outcome] || '');
    const dot = r.outcome === 'worked'
      ? `<circle cx="${x}" cy="${y}" r="10" fill="var(--surface)"/><circle cx="${x}" cy="${y}" r="8" fill="var(--open-line)"/><text x="${x}" y="${y + 3.5}" ${MAP_TXT} font-size="8.5" font-weight="700" text-anchor="middle" fill="var(--surface)">✓</text>`
      : r.outcome === 'mixed'
        ? `<circle cx="${x}" cy="${y}" r="10" fill="var(--surface)"/><circle cx="${x}" cy="${y}" r="7" fill="var(--surface)" stroke="var(--notyet-line)" stroke-width="2.5"/><circle cx="${x}" cy="${y}" r="2.5" fill="var(--notyet-line)"/>`
        : `<circle cx="${x}" cy="${y}" r="10" fill="var(--surface)"/><circle cx="${x}" cy="${y}" r="7" fill="var(--surface)" stroke="var(--ink-muted)" stroke-width="2"${r.outcome === 'missed' ? ' stroke-dasharray="2.5 2.5"' : ''}/>`;
    const pn = (allPaths.find(p => p.key === r.path) || {}).name || '';
    return `
          <g class="map-node ${isNew ? 'map-node-done-anim' : ''}" tabindex="0"
             data-tip-title="${attr(`Cycle ${r.cycle}: ${r.title}`)}" data-tip-sub="${attr(`Day ${r.day} · ${pn} · ${fmtM(r.rp)} a month`)}"
             onmouseenter="showMapTip(this)" onmouseleave="hideMapTip()" onfocus="showMapTip(this)" onblur="hideMapTip()">
            <circle cx="${x}" cy="${y}" r="15" fill="transparent"/>${dot}
          </g>
          <text x="${x}" y="${y + 25}" ${MAP_TXT} font-size="9.5" font-weight="${WORD_COLOR[r.outcome] ? 700 : 500}" text-anchor="middle" fill="${WORD_COLOR[r.outcome] || 'var(--ink-muted)'}" pointer-events="none">${esc(word)}</text>`;
  }).join('');
  const activeNode = (x, y) => rs.ending ? '' : `
            <g class="map-node" tabindex="0" data-tip-title="${attr((rs.steps[rs.currentStep - 1] || {}).label || 'Today')}" data-tip-sub="${attr(`Today · Day ${tl.day} · Step ${rs.currentStep} of ${rs.steps.length}`)}"
               onmouseenter="showMapTip(this)" onmouseleave="hideMapTip()" onfocus="showMapTip(this)" onblur="hideMapTip()">
              <circle cx="${x}" cy="${y}" r="14" fill="var(--surface)"/>
              <circle cx="${x}" cy="${y}" r="17" fill="var(--open-line)" opacity="0.12"/>
              <circle class="map-pulse" cx="${x}" cy="${y}" r="10" fill="none" stroke="var(--open-line)" stroke-width="2"/>
              <circle cx="${x}" cy="${y}" r="9" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.5"/>
              <circle cx="${x}" cy="${y}" r="3.5" fill="var(--ink)"/>
            </g>
            ${nodeWord(x, y + 25, (rs.steps[rs.currentStep - 1] || {}).mapLabel || 'Today', STEP_STATUS.CURRENT)}`;

  /* Cycle columns across the top */
  const colState = c => c < rs.currentCycle || rs.ending ? 'past' : (c === rs.currentCycle ? 'now' : 'ahead');
  const headFill = { past: 'var(--ink-3)', now: 'var(--ink)', ahead: 'var(--ink-muted-2)' };
  let columnsSvg = '';
  for (let c = 2; c <= LAST_CYCLE; c++) {
    const x = colX(c), st = colState(c);
    columnsSvg += `
          <line x1="${x - COL / 2}" y1="${ext.top + 8}" x2="${x - COL / 2}" y2="${ext.bottom - 4}" stroke="var(--surface-hover)" stroke-width="1"/>
          ${st === 'now' ? `<rect x="${x - COL / 2 + 4}" y="${ext.top + 4}" width="${COL - 8}" height="${VB_H - 6}" rx="10" fill="var(--open-line)" opacity="0.05"/>` : ''}
          <text x="${x}" y="${ext.top + 14}" ${MAP_TXT} font-size="10" font-weight="700" text-anchor="middle" fill="${headFill[st]}">C${c}</text>
          <text x="${x}" y="${ext.top + 26}" ${MAP_TXT} font-size="8.5" text-anchor="middle" fill="${st === 'ahead' ? 'var(--border-strong)' : 'var(--ink-muted)'}">Day ${Math.min(c * cl, H)}</text>`;
  }
  const c1State = colState(1);
  columnsSvg += `
          ${c1State === 'now' ? `<rect x="205" y="${ext.top + 4}" width="606" height="${VB_H - 6}" rx="10" fill="var(--open-line)" opacity="0.04"/>` : ''}
          <text x="510" y="${ext.top + 14}" ${MAP_TXT} font-size="10" font-weight="700" text-anchor="middle" fill="${headFill[c1State]}">C1</text>
          <text x="510" y="${ext.top + 26}" ${MAP_TXT} font-size="8.5" text-anchor="middle" fill="var(--ink-muted)">Days 1 to ${cl}</text>`;
  const progressKey = `${rs.currentCycle}-${LIVE.checkins.length}-${rs.ending || ''}-${rs.doneNums.join('.')}`;

  /* Lanes: back to front so the active route always sits on top */
  const order = paths.slice().sort((a, b) => (slots[b.key] || 9) - (slots[a.key] || 9));
  const lanesSvg = order.map(p => {
    const slot = slots[p.key] || 5;
    const short = (p.status === 'STOP' || p.status === 'TEST_FIRST') && slot >= 2 && slot !== 3 && slot !== 4;
    const geom = slotGeom(slot, GX, cmoBx, !short);
    return laneSvg(p, geom, sel, slot);
  }).join('');

  const tgtTxt = gv.nonRevenue ? gv.tgtLabel : (g.target != null ? `${fmtM(g.target)} a month` : 'growth');
  const openWords = openCount === 0 ? 'No paths are' : `${countWord(openCount)} ${openCount === 1 ? 'is' : 'are'}`;
  const headline = rs.ending
    ? `Day ${H}: ${fmtM(rs.earned)} a month. ${openWords} open.`
    : (goalReached ? `Goal reached: ${fmtM(rs.earned)} a month. ${openWords} open.` : `${countWord(allPaths.length)} ${allPaths.length === 1 ? 'way' : 'ways'} to ${tgtTxt}. ${openWords} open today.`);
  const startSub = gv.nonRevenue ? (gv.now != null ? gv.nowLabel : 'Not measured yet') : (g.current != null ? `${fmtM(g.current)}/mo` : 'Now');

  /* Selected path detail */
  const pd = allPaths.find(p => p.key === sel) || active;
  const isActive = pd.key === activeKey;
  let action;
  if (rs.ending && isActive) action = `<button class="btn-primary" onclick="renderScreen('16')">See your Day ${H} review →</button>`;
  else if (isActive) action = `<button class="btn-primary" onclick="renderScreen('04')">Go to your next step →</button>`;
  else if (pd.status === 'OPEN') action = `<button class="btn-primary" onclick="makeActivePath('${pd.key}')">Make this my current path</button>`;
  else if (pd.status === 'STOP') action = `<button class="btn-secondary" onclick="openModal('${pd.key}')">I want to do this anyway</button>`;
  else if (pd.status === 'TEST_FIRST') action = `<button class="btn-secondary" onclick="makeActivePath('${pd.key}')">Test this path first</button>`;
  else action = `<button class="btn-secondary" disabled style="opacity:0.5;cursor:default">Locked: ${pd.passedN} of ${pd.gateN} checks passed</button>`;

  if (openCount === 0 && STORE.mapZeroOff !== true) return screen07ZeroLive(allPaths, rs, tl, g);

  const content = `
  <div class="map-layout">
    <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-shrink:0">
      <h1 class="serif-heading" style="font-size:30px">${esc(headline)}</h1>
      <div style="font-size:12px;color:var(--ink-3);max-width:300px;text-align:right;line-height:1.45">
        Each column is one cycle (${cl} days). Scroll sideways to see all ${LAST_CYCLE}. Click a path for details, point at a dot for what happened.${pres.overflow ? ` ${pathShownLine(pres)}.` : ''}
      </div>
    </div>

    <div class="map-body">
    <div class="card-clean map-canvas-card" id="map-canvas-card">
      <div class="map-tip" id="map-tip" hidden></div>
      <div class="map-canvas">
        <svg viewBox="50 ${ext.top} ${VB_W} ${VB_H}" preserveAspectRatio="xMinYMid meet" xmlns="http://www.w3.org/2000/svg" role="group" aria-label="Path map: ${pres.overflow ? `${countWord(paths.length).toLowerCase()} of ${countWord(allPaths.length).toLowerCase()}` : countWord(paths.length).toLowerCase()} ${allPaths.length === 1 ? 'way' : 'ways'} to your goal"
             style="aspect-ratio:${VB_W} / ${VB_H}" data-vbw="${VB_W}" data-nowx="${nowX}" data-progress-key="${progressKey}">
          ${columnsSvg}
          <line x1="${GX}" y1="${ext.top + 8}" x2="${GX}" y2="${ext.bottom - 4}" stroke="${goalReached ? 'var(--open-line)' : 'var(--border-strong)'}" stroke-width="${goalReached ? 1.5 : 1}" stroke-dasharray="3 4"/>

          <circle cx="72" cy="220" r="10" fill="var(--ink)"/>
          <circle cx="72" cy="220" r="3.5" fill="var(--surface)"/>
          <text x="72" y="240" ${MAP_TXT} font-size="9.5" font-weight="700" text-anchor="middle" fill="var(--ink)">Start</text>
          <text x="72" y="252" ${MAP_TXT} font-size="9" text-anchor="middle" fill="var(--ink-3)">${esc(startSub)}</text>

          ${lanesSvg}

          ${!rs.ending ? `<path class="route-ahead" d="M ${routeEnd.x} ${routeEnd.y} ${routeEnd.y === 220 ? `L ${GX} 220` : `L ${GX - 72} ${routeEnd.y} C ${GX - 36} ${routeEnd.y} ${GX - 36} 220 ${GX} 220`}" fill="none" stroke="var(--open-line)" stroke-width="2.5" stroke-linecap="round" opacity="0.45" pointer-events="none"/>` : ''}
          <path id="map-progress" d="${routeD}" fill="none" stroke="var(--open-line)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" pointer-events="none"/>
          <circle cx="${GX}" cy="220" r="10" fill="var(--surface)"/>
          ${goalReached
            ? `<circle cx="${GX}" cy="220" r="15" fill="var(--open-line)" opacity="0.18"/><circle cx="${GX}" cy="220" r="8" fill="var(--open-line)"/>`
            : `<circle cx="${GX}" cy="220" r="4.5" fill="var(--surface)" stroke="var(--ink-muted)" stroke-width="2"/>`}
          <text x="${GX - 14}" y="200" ${MAP_TXT} font-size="10.5" font-weight="700" text-anchor="end" fill="${goalReached ? 'var(--open-fg)' : 'var(--ink-3)'}" stroke="var(--surface)" stroke-width="4" paint-order="stroke">${goalReached ? '✓ Goal reached' : `Goal${gTgt != null ? ` · ${gmet ? fmtGoalValue(gmet, gTgt) : fmtM(gTgt)}${gmet && gmet.id !== 'revenue_monthly' ? ' ' + gmet.name.toLowerCase() : ' / month'}` : ''}`}</text>
          <text x="${GX - 14}" y="212" ${MAP_TXT} font-size="8.5" text-anchor="end" fill="var(--ink-muted)" stroke="var(--surface)" stroke-width="4" paint-order="stroke">Day ${H}</text>
          ${milestoneSvg}
          ${checkpointSvg}
          ${nowPt ? activeNode(nowPt.x, nowPt.y) : ''}
        </svg>
      </div>

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

    <aside class="map-bottom" aria-label="Selected path">
      <div class="card-clean map-detail">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;flex-shrink:0">
          <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
            <h2 style="font-family:var(--font-ui);font-size:17px;font-weight:700">${esc(pd.name)}</h2>
            ${isActive ? `<span style="font-family:var(--font-ui);font-size:11.5px;font-weight:600;color:var(--open-fg)">● Your current path · Day ${tl.day}</span>` : ''}
          </div>
          <span class="status-pill ${pd.status.toLowerCase()}">${STATUS_WORD[pd.status]}</span>
        </div>
        <div class="map-detail-body">
          <div>
            <div class="section-meta-label" style="margin-bottom:2px">Why this status</div>
            <p style="font-size:13px;color:var(--ink-2);line-height:1.5;margin:0">${pd.explained ? esc(pd.why) : esc(pd.basis) + ' ' + esc(pd.why)}</p>
          </div>
          <div>
            <div class="section-meta-label" style="margin-bottom:2px">Next step</div>
            <p style="font-size:13px;color:var(--ink-2);line-height:1.5;margin:0">${esc(pd.next)}</p>
          </div>
        </div>
        ${liveWhyHereHtml(pd.key)}
        ${pd.relationLine ? `<div class="path-relation-note" style="margin-top:10px;padding:10px 12px;border:1px solid var(--border);border-radius:8px;font-size:12.5px;color:var(--ink-2);line-height:1.5;background:var(--surface-2)">${esc(pd.relationLine)}</div>` : ''}
        ${renderMapNeed((liveReadiness() || { paths: [] }).paths.find(p => p.key === pd.key))}
        <div class="map-actions">
          ${action}
          <button class="btn-secondary" onclick="openReadiness('${pd.key}')">What it needs →</button>
          <button class="btn-secondary" onclick="renderScreen('08')">See your progress →</button>
        </div>
      </div>
      ${livePathOverflowHtml(pres, { pick: 'selectMapPath', pickLabel: 'Show on the map' })}
      ${liveEmergingHtml()}
    </aside>
    </div>
  </div>`;
  return renderAppShell('map', 'Path map', content);
}

function makeActivePath(key) { liveSetActivePath(key); STORE.selectedMapPath = key; renderScreen('07'); }

/* ── 07b · No path is open yet (zero-open state) ─────────────────────────── */
function screen07ZeroLive(paths, rs, tl, g) {
  const gvz = mapGoalView();
  const d = LIVE.artifact;
  const test = paths.find(p => p.status === 'TEST_FIRST') || paths.find(p => p.status === 'NOT_YET') || paths[0];
  const others = paths.filter(p => p !== test);
  const dn = cleanDoNot(d);
  const steps = rs.steps.filter(s => !s.report && !s.hold).slice(0, 3);
  const lane = (p, y, dim) => {
    const c = { TEST_FIRST: ['var(--test-line)', '2 6', 3.5], NOT_YET: ['var(--notyet-line)', '6 4', 2], STOP: ['var(--stop-line)', '', 2], OPEN: ['var(--open-line)', '', 2.5] }[p.status];
    return `<path d="M 112 220 C 180 220, 180 ${y}, 260 ${y} L ${p === test ? 598 : 520} ${y}" fill="none" stroke="${c[0]}" stroke-width="${dim ? 2 : c[2]}" ${c[1] ? `stroke-dasharray="${c[1]}"` : ''} ${dim ? 'opacity="0.4"' : ''}/>
      <text x="260" y="${y + 18}" ${MAP_TXT} font-size="10.5" fill="${c[0]}" ${dim ? 'opacity="0.6"' : ''}>${esc(p.name)} · ${STATUS_WORD[p.status]}</text>`;
  };
  const ys = [130, 210, 300, 370];
  const unlock = test.unlock[0] || 'the checks for this path pass';
  return renderAppShell('map', 'Path map', `
  <div style="padding:40px 56px;display:flex;flex-direction:column;gap:28px">
    <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:16px">
      <div>
        <div class="section-meta-label">Your map · Day ${tl.day} of ${tl.horizon}</div>
        <h1 class="serif-heading" style="font-size:36px">No path is open yet. Here's the test that opens one.</h1>
      </div>
      <div style="font-size:12px;color:var(--ink-3);max-width:320px;text-align:right">Each path's status is based on what has actually happened. Not enough has happened yet, so your first step is to make something happen.</div>
    </div>
    <div class="dot-grid-canvas" style="padding:22px">
      <svg viewBox="0 0 1072 440" style="width:100%;height:auto;display:block" role="img" aria-label="Path map with no open path">
        <line x1="480" y1="30" x2="480" y2="400" stroke="var(--border-strong)" stroke-dasharray="3 3"/>
        <text x="485" y="45" ${MAP_TXT} font-size="11" font-weight="700" fill="var(--ink-3)">Today · Day ${tl.day}</text>
        <line x1="1010" y1="30" x2="1010" y2="400" stroke="var(--border-strong)" stroke-dasharray="3 3"/>
        <text x="930" y="45" ${MAP_TXT} font-size="11" font-weight="700" fill="var(--ink-3)">Goal${gvz.tgt != null ? ` · ${esc(gvz.tgtLabel)}` : ''}</text>
        <circle cx="100" cy="220" r="12" fill="var(--ink)"/><circle cx="100" cy="220" r="3" fill="var(--surface)"/>
        <text x="100" y="248" ${MAP_TXT} font-size="11" font-weight="700" text-anchor="middle" fill="var(--ink)">Start${gvz.now != null ? ` (${esc(gvz.nowLabel)})` : (gvz.nonRevenue ? ' (not measured yet)' : '')}</text>
        ${lane(test, ys[0], false)}
        <circle cx="300" cy="${ys[0]}" r="5" fill="var(--test-fg)"/>
        <circle cx="480" cy="${ys[0]}" r="8" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.5"/>
        <text x="480" y="${ys[0] + 22}" ${MAP_TXT} font-size="11" font-weight="700" text-anchor="middle" fill="var(--ink)">Your test · this week</text>
        <polygon points="598,${ys[0] - 12} 610,${ys[0]} 598,${ys[0] + 12} 586,${ys[0]}" fill="var(--surface)" stroke="var(--ink)" stroke-width="2.5"/>
        <text x="598" y="${ys[0] + 40}" ${MAP_TXT} font-size="11" font-weight="700" text-anchor="middle" fill="var(--ink)">Unlocks when the checks pass</text>
        <path d="M 610 ${ys[0]} L 1010 ${ys[0]}" fill="none" stroke="var(--ink-muted)" stroke-width="2" stroke-dasharray="4 4"/>
        <text x="780" y="${ys[0] - 10}" ${MAP_TXT} font-size="10" fill="var(--ink-3)">Opens if the test works</text>
        ${others.slice(0, 3).map((p, i) => lane(p, ys[i + 1], true)).join('')}
      </svg>
      <div style="display:flex;gap:16px;font-family:var(--font-ui);font-size:11.5px;color:var(--ink-3);margin-top:14px;border-top:1px solid var(--border);padding-top:10px;flex-wrap:wrap">
        <span>◇ Unlock point: what has to happen to open a path</span><span>┄ Test first (dotted)</span><span>┄ Not yet (dashed)</span><span>■ Stop (✕)</span>
        ${others.length > 3 ? `<span data-testid="zero-overflow">+${others.length - 3} other ${others.length - 3 === 1 ? 'possibility not drawn here. It is' : 'possibilities not drawn here. They are'} on the full map.</span>` : ''}
      </div>
    </div>
    <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">
      <div class="card-clean" style="flex:1;min-width:320px">
        <div class="section-meta-label">This isn't a dead end</div>
        <p style="font-size:14px;color:var(--ink);line-height:1.55;margin:8px 0 16px">${esc(brief(test.why, 240))} That's normal early on. So your next step isn't to pick a path. It's to run the smallest test that could open one.</p>
        <div style="display:flex;flex-direction:column;gap:12px;border-top:1px solid var(--border);padding-top:14px">
          <div><div class="section-meta-label" style="color:var(--stop-fg)">Still on hold, and why</div>
            <div style="font-size:13px;color:var(--ink-2);line-height:1.5;margin-top:2px">${esc(brief(dn.text || 'Spending money or scaling anything waits until something has worked.', 220))}</div></div>
          <div><div class="section-meta-label">If the test stays quiet</div>
            <div style="font-size:13px;color:var(--ink-2);line-height:1.5;margin-top:2px">${esc(brief(userFacing(d.pivot_rule || 'We look at it again at your next check-in and keep your goal as it is.'), 220))}</div></div>
        </div>
      </div>
      <div class="card-dark" style="width:420px;flex-shrink:0">
        <div class="section-meta-label" style="color:var(--border-strong)">Your test · this week</div>
        <h3 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin:6px 0 8px">${esc(brief(userFacing(d.first_step_today || d.next_best_action), 120))}</h3>
        <div style="display:flex;flex-direction:column;gap:10px;font-size:13.5px;color:var(--border);margin:16px 0">
          ${steps.map((s, i) => `<div style="display:flex;gap:8px"><span style="color:var(--ink-muted)">${i + 1}.</span><span>${esc(s.label)}</span></div>`).join('')}
        </div>
        <div style="background:var(--ink-hover);border-radius:8px;padding:10px 12px;font-size:12.5px;color:var(--ink-muted);line-height:1.45;margin-bottom:18px">
          <strong style="color:var(--on-ink)">Opens “${esc(test.name)}” when:</strong> ${esc(brief(unlock, 200))}
        </div>
        <div style="display:flex;gap:10px">
          <button class="btn-primary" style="background:var(--surface);color:var(--ink);flex:1" onclick="renderScreen('04')">Start the test →</button>
          <button class="btn-secondary" style="border-color:var(--ink-2b);color:var(--on-ink)" onclick="STORE.mapZeroOff=true;renderScreen('07')">See full map</button>
        </div>
      </div>
    </div>
  </div>`);
}

/* ── 08 · Journey ───────────────────────────────────────────────────────── */
/* [DEAD 2026-10-15] v9-only live journey screen: reachable only via 'v9:08', which has been removed;
   the Journey destination now = screenJourney11 (below). Safe to delete physically in a mechanical follow-up. */
function screen08Live() {
  const rs = useRoadmapStore.getState();
  const tl = getTimeline();
  const d = LIVE.artifact;
  const g = liveGoal();
  const H = tl.horizon, cl = tl.cycleLen;
  const LAST = Math.max(2, Math.ceil(H / cl));
  const history = LIVE.checkins;
  const ending = rs.ending;
  const earned = rs.earned || 0;
  const goal = g.target || Math.max(earned * 1.25, 1);
  const fmtRp = rp => rp ? fmtM(rp) : 'Rp0';
  const paths = livePathModels();
  const activeP = paths.find(p => p.key === rs.activePathId) || paths[0];
  const curStep = rs.steps[rs.currentStep - 1] || { label: '' };
  const reachedAt = g.target != null ? history.find(r => r.rp >= g.target) : null;
  const base = g.current != null ? g.current : 0;

  const X0 = 55, X1 = 860;
  const xOf = day => X0 + Math.min(day, H) * ((X1 - X0) / H);
  const yOf = rp => 192 - Math.min(rp / goal, 1.08) * 154;
  const held = paths.filter(p => p.status === 'STOP' || p.status === 'NOT_YET');

  const nodes = [{
    day: 0, rp: base, kind: 'start', label: 'START · Day 0', title: 'Diagnosis done',
    rows: [g.target != null ? `Goal set: ${fmtM(g.target)} a month within ${H} days` : `Horizon: ${H} days`, `Main problem: ${brief(userFacing(d.primary_constraint), 90)}`],
    saved: held.length ? `${held.length} path${held.length === 1 ? '' : 's'} held back until the evidence is there` : 'No paths held back'
  }];
  history.forEach(r => nodes.push({
    day: r.day, rp: r.rp, kind: r.outcome, event: null,
    label: `Check-in ${r.cycle} · Day ${r.day}`, title: r.title,
    rows: [r.outcome === 'missed' ? 'No check-in this week' : `${r.contacted} contacted · ${r.replies} replies · ${r.calls} calls`,
      r.paid ? `New payment: ${fmtM(r.paid)}` : null, `Monthly income after: ${fmtRp(r.rp)}`].filter(Boolean),
    saved: `Paths held back: ${held.length}`
  }));
  const stepCounts = todayCounts(rs.steps, tl.day);
  const showNow = !ending && (history.length === 0 || rs.doneNums.length > 0);
  if (showNow) nodes.push({
    day: tl.day, rp: earned, kind: 'now', label: `Now · Day ${tl.day}`, title: `Cycle ${tl.cycle} · ${stepCounts.done} of ${stepCounts.total} steps done`,
    rows: [activeP ? activeP.name : '', curStep.label, `Check-in on Day ${tl.nextCheckIn}`].filter(Boolean), saved: `Paths held back: ${held.length}`
  });
  else if (!ending && history.length) nodes[nodes.length - 1].now = true;
  window.__journeyNodes = nodes;

  const pts = nodes.map(n => ({ x: xOf(n.day), y: yOf(n.rp) }));
  let realized = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const mx = (pts[i - 1].x + pts[i].x) / 2;
    realized += ` C ${mx} ${pts[i - 1].y} ${mx} ${pts[i].y} ${pts[i].x} ${pts[i].y}`;
  }
  const last = pts[pts.length - 1], lastNode = nodes[nodes.length - 1];
  let estimateSvg = '';
  if (!ending) {
    let est = g.target != null ? g.target : earned;
    if (history.length >= 2) {
      const recent = [{ day: 0, rp: base }].concat(history).slice(-4);
      const slope = (recent[recent.length - 1].rp - recent[0].rp) / Math.max(recent[recent.length - 1].day - recent[0].day, 1);
      est = Math.max(0, Math.round((lastNode.rp + slope * (H - lastNode.day)) * 10) / 10);
    }
    const ex = xOf(H), ey = yOf(est);
    estimateSvg = `
        <path d="M ${last.x} ${last.y} C ${(last.x + ex) / 2} ${last.y} ${(last.x + ex) / 2} ${ey} ${ex} ${ey}" fill="none" stroke="var(--ink-muted)" stroke-width="1.5" stroke-dasharray="5 4"/>
        <circle cx="${ex}" cy="${ey}" r="3.5" fill="var(--surface)" stroke="var(--ink-muted)" stroke-width="1.5"/>
        <text x="${ex - 6}" y="${ey + (ey < 60 ? 16 : -8)}" ${MAP_TXT} font-size="9" font-weight="600" text-anchor="end" fill="var(--ink-3)">${history.length >= 2 ? `Estimate at Day ${H}: ${esc(fmtRp(est))}` : 'Target path'}</text>`;
  }
  const OUT = { worked: { color: 'var(--open-line)' }, mixed: { color: 'var(--notyet-line)' }, none: { color: 'var(--ink-muted)' }, missed: { color: 'var(--ink-muted)' }, final: { color: 'var(--ink)' } };
  const nodesSvg = nodes.map((n, i) => {
    const p = pts[i], st = OUT[n.kind] || { color: 'var(--open-line)' };
    const isNow = n.kind === 'now' || n.now;
    return `
        <g class="j-node" role="img" tabindex="0" aria-label="${esc(n.label + ': ' + n.title)}"
           onmouseenter="showJourneyTip(this, ${i})" onmouseleave="hideJourneyTip()" onfocus="showJourneyTip(this, ${i})" onblur="hideJourneyTip()">
          <circle cx="${p.x}" cy="${p.y}" r="14" fill="transparent"/>
          ${isNow ? `<circle class="map-pulse" cx="${p.x}" cy="${p.y}" r="7" fill="none" stroke="var(--open-line)" stroke-width="2"/>` : ''}
          <circle class="j-ring" cx="${p.x}" cy="${p.y}" r="5" fill="${isNow ? 'var(--open-line)' : 'var(--surface)'}" stroke="${n.kind === 'start' ? 'var(--ink)' : st.color}" stroke-width="2.5"/>
        </g>`;
  }).join('');
  const cycleMarks = Array.from({ length: LAST }, (_, i) => i + 1).map(k => {
    const isCur = !ending && k === tl.cycle;
    return `
        ${k < LAST ? `<line x1="${xOf(k * cl)}" y1="38" x2="${xOf(k * cl)}" y2="192" stroke="var(--border-subtle)" stroke-width="1"/>` : ''}
        <text x="${xOf(Math.min(k * cl - cl / 2, H - cl / 2))}" y="208" ${MAP_TXT} font-size="9" text-anchor="middle" font-weight="${isCur ? '700' : '400'}" fill="${isCur ? 'var(--ink)' : 'var(--ink-muted)'}">C${k}</text>`;
  }).join('');

  let headline = 'Your goal stayed the same. Your path changed.';
  if (!history.length) headline = 'Your goal is set. Your first check-in is coming up.';
  else if (ending === 'miss') headline = `Day ${H}: ${fmtRp(earned)} a month. Not ${g.target != null ? fmtM(g.target) : 'your goal'} yet.`;
  else if (ending === 'success') headline = `Day ${H}: you reached your goal.`;
  else if (reachedAt) headline = 'You reached your goal. Now keep it steady.';

  // a legacy baseline has no trustworthy path result: it is no baseline (nothing to compare), never "0 paths before"
  const baseLegacy = LIVE.baseline && LIVE.baseline.navigation && LIVE.baseline.navigation.status === 'LEGACY';
  const baseOpen = (((((baseLegacy ? null : LIVE.baseline) || d).possible_paths || {}).paths)) || [];
  const baseOpenKeys = baseOpen.filter(p => p.status === 'OPEN').map(p => p.path_id);
  const opened = paths.filter(p => p.status === 'OPEN' && !baseOpenKeys.includes(p.key));
  const j = LIVE.journey;
  const verdictPill = j && j.verdict ? `<span class="status-pill ${j.verdict === 'ADVANCED' ? 'open' : (j.verdict === 'REGRESSED' ? 'stop' : (j.verdict === 'STUCK' ? 'not_yet' : 'test_first'))}" title="Compared with your previous cycle">${esc(j.verdict)}</span>` : '';

  const historyRows = history.slice().reverse().map(r => {
    const st = { worked: ['open', 'Paid'], mixed: ['not_yet', 'Mixed'], none: ['', 'No replies'], missed: ['', 'Missed'] }[r.outcome] || ['', r.outcome];
    const pn = (paths.find(p => p.key === r.path) || {}).name || '';
    return `
          <div class="j-hist-row">
            <div style="font-family:var(--font-ui);font-size:11px;font-weight:700;color:var(--ink-3);white-space:nowrap">C${r.cycle} · Day ${r.day}</div>
            <div style="min-width:0">
              <div style="font-family:var(--font-ui);font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.title)}</div>
              <div style="font-size:11.5px;color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(pn)}</div>
            </div>
            <span class="status-pill ${st[0]}" style="${st[0] ? '' : 'background:var(--surface-2);color:var(--ink-3);border-color:var(--border)'}">${st[1]}</span>
            <div style="font-family:var(--font-ui);font-size:12.5px;font-weight:700;text-align:right;white-space:nowrap">${esc(fmtRp(r.rp))}</div>
          </div>`;
  }).join('');

  const dn = cleanDoNot(d);
  const decisions = [];
  if (dn.text) decisions.push({ t: brief(dn.text, 70), s: brief(dn.reason, 90), pill: dn.verdict ? dn.verdict.replace('_', ' ') : 'On hold', cls: dn.verdict === 'STOP' ? 'stop' : 'not_yet' });
  LIVE.overrides.slice(-2).forEach(o => {
    const pn = (paths.find(p => p.key === o.path) || {}).name || 'A stopped path';
    decisions.push({ t: o.choice === 'capped' ? `Chose a small test on ${pn}` : `Went ahead on ${pn}`, s: `Your call in cycle ${o.cycle}, logged`, pill: o.choice === 'capped' ? 'Capped' : 'Your call', cls: 'test_first' });
  });
  paths.filter(p => p.status === 'STOP' || p.status === 'NOT_YET').slice(0, 2).forEach(p => decisions.push({ t: `${p.name} stays ${STATUS_WORD[p.status].toLowerCase()}`, s: brief(p.why, 90), pill: STATUS_WORD[p.status], cls: p.status === 'STOP' ? 'stop' : 'not_yet' }));

  const content = `
  <div id="j-root" style="position:relative;padding:32px 48px 40px;display:flex;flex-direction:column;gap:20px">
    <div class="j-tip" id="j-tip" hidden></div>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
      <h1 class="serif-heading" style="font-size:30px">${esc(headline)}</h1>${verdictPill}
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px">
      <div class="card-clean" style="padding:16px 18px"><div class="section-meta-label">Monthly income</div><div style="font-size:22px;font-weight:700;margin-top:4px">${esc(fmtRp(earned))}</div><div style="font-size:11.5px;color:var(--ink-3);margin-top:2px">${g.target != null ? `${Math.round(earned / g.target * 100)}% of the ${esc(fmtM(g.target))} goal` : 'No target set yet'}</div></div>
      <div class="card-clean" style="padding:16px 18px"><div class="section-meta-label">Days left</div><div style="font-size:22px;font-weight:700;margin-top:4px">${ending ? 0 : tl.daysLeft}</div><div style="font-size:11.5px;color:var(--ink-3);margin-top:2px">${ending ? `Day ${H} reached` : `Day ${tl.day} of ${H}`}</div></div>
      <div class="card-clean" style="padding:16px 18px"><div class="section-meta-label">New paths opened</div><div style="font-size:22px;font-weight:700;margin-top:4px">${opened.length}</div><div style="font-size:11.5px;color:var(--ink-3);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${opened.length ? esc(opened.map(p => p.name).join(' + ')) : 'None yet'}</div></div>
      <div class="card-clean" style="padding:16px 18px"><div class="section-meta-label">Check-ins done</div><div style="font-size:22px;font-weight:700;margin-top:4px">${history.length} of ${Math.max(LAST, history.length)}</div><div style="font-size:11.5px;color:var(--ink-3);margin-top:2px">${ending ? 'All done' : `Next on Day ${tl.nextCheckIn}`}</div></div>
    </div>

    <div class="card-clean" style="padding:20px 24px 14px;overflow-x:auto;scrollbar-width:thin;scrollbar-color:var(--border-strong) transparent">
      <div style="min-width:860px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div style="display:flex;align-items:baseline;gap:10px">
          <div class="section-meta-label" style="margin:0">Monthly income over ${H} days</div>
          <span style="font-size:11.5px;color:var(--ink-3)">Point at a dot to see that check-in</span>
        </div>
        <div style="display:flex;align-items:center;gap:14px;font-family:var(--font-ui);font-size:10.5px;color:var(--ink-3)">
          <span style="display:flex;align-items:center;gap:5px"><svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="var(--open-line)" stroke-width="2.5"/></svg>Actual</span>
          <span style="display:flex;align-items:center;gap:5px"><svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="var(--ink-muted)" stroke-width="1.5" stroke-dasharray="4 3"/></svg>Estimate</span>
          <span style="display:flex;align-items:center;gap:4px"><svg width="10" height="10"><circle cx="5" cy="5" r="3.5" fill="var(--surface)" stroke="var(--open-line)" stroke-width="2"/></svg>Paid</span>
          <span style="display:flex;align-items:center;gap:4px"><svg width="10" height="10"><circle cx="5" cy="5" r="3.5" fill="var(--surface)" stroke="var(--notyet-line)" stroke-width="2"/></svg>Mixed</span>
          <span style="display:flex;align-items:center;gap:4px"><svg width="10" height="10"><circle cx="5" cy="5" r="3.5" fill="var(--surface)" stroke="var(--ink-muted)" stroke-width="2"/></svg>No result</span>
        </div>
      </div>
      <svg viewBox="0 0 880 218" style="width:100%;height:auto;display:block;overflow:visible" xmlns="http://www.w3.org/2000/svg" role="group" aria-label="Monthly income over ${H} days">
        <line x1="${X0}" y1="115" x2="${X1}" y2="115" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 3"/>
        <text x="10" y="119" ${MAP_TXT} font-size="9.5" fill="var(--ink-3)">${esc(fmtM(goal / 2))}</text>
        <line x1="${X0}" y1="192" x2="${X1}" y2="192" stroke="var(--border)" stroke-width="1"/>
        <text x="22" y="196" ${MAP_TXT} font-size="9.5" fill="var(--ink-3)">Rp0</text>
        <line x1="${X0}" y1="38" x2="${X1}" y2="38" stroke="${reachedAt ? 'var(--open-line)' : 'var(--border-strong)'}" stroke-width="${reachedAt ? 1.5 : 1}" stroke-dasharray="3 4"/>
        <text x="10" y="42" ${MAP_TXT} font-size="9.5" fill="var(--ink-3)">${esc(fmtM(goal))}</text>
        <text x="${X0 + 4}" y="30" ${MAP_TXT} font-size="9" font-weight="700" text-anchor="start" fill="${reachedAt ? 'var(--open-fg)' : 'var(--ink-3)'}">${reachedAt ? `Goal reached on Day ${reachedAt.day} · ${esc(fmtM(goal))} / month` : `Goal${g.target != null ? ` · ${esc(fmtM(goal))} / month` : ''}`}</text>
        ${cycleMarks}
        ${estimateSvg}
        <path d="${realized}" fill="none" stroke="var(--open-line)" stroke-width="3" stroke-linecap="round"/>
        ${nodesSvg}
      </svg>
      </div>
    </div>

    ${sinceLastDiagnosisHtml(paths)}
    <div style="display:grid;grid-template-columns:3fr 2fr;gap:20px;align-items:start">
      <div class="card-clean" style="padding:20px 22px">
        <div class="section-meta-label" style="margin-bottom:12px">Check-in history</div>
        ${!ending ? `
        <div class="dark-surface" style="border:1px solid var(--ink);border-radius:10px;padding:12px 14px;background:var(--ink);margin-bottom:8px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
            <div style="min-width:0">
              <div style="font-family:var(--font-ui);font-size:13px;font-weight:700;color:var(--on-ink)">Cycle ${tl.cycle} · ${activeP ? esc(activeP.name) : 'Your plan'}</div>
              <div style="font-size:12px;color:var(--ink-muted);margin-top:2px">${stepCounts.done} of ${stepCounts.total} steps done · next: ${esc(curStep.label)} · check-in on Day ${tl.nextCheckIn}</div>
            </div>
            <span style="font-family:var(--font-ui);font-size:10px;font-weight:700;padding:3px 8px;border-radius:999px;background:var(--surface);color:var(--ink);white-space:nowrap">IN PROGRESS</span>
          </div>
        </div>` : ''}
        ${history.length ? `<div class="j-hist">${historyRows}</div>` : `<div style="font-size:12.5px;color:var(--ink-3);padding:6px 0">Your first check-in is on Day ${tl.nextCheckIn}.</div>`}
        <div style="padding-top:14px">
          ${ending
            ? `<button class="btn-primary" style="width:100%" onclick="renderScreen('16')">See your Day ${H} review →</button>`
            : `<button class="btn-primary" style="width:100%" onclick="renderScreen('05')">Report Cycle ${tl.cycle} result →</button>`}
        </div>
      </div>

      <div class="card-clean" style="padding:20px 22px">
        <div class="section-meta-label" style="margin-bottom:12px">Decisions that protected you</div>
        <div style="border:1px solid var(--border);border-radius:12px;padding:14px 16px;margin-bottom:16px">
          <div class="section-meta-label" style="margin:0">On hold</div>
          <div style="font-family:var(--font-ui);font-size:30px;font-weight:800;color:var(--ink);line-height:1.15;margin-top:2px">${held.length} path${held.length === 1 ? '' : 's'}</div>
          <div style="font-size:12px;color:var(--ink-2);margin-top:2px">Kept off your plate until the evidence is there, instead of spent on things that couldn't work yet</div>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px">
          ${decisions.map((x, i) => `${i ? '<div style="height:1px;background:var(--border)"></div>' : ''}
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
            <div style="min-width:0"><div style="font-family:var(--font-ui);font-size:13px;font-weight:700">${esc(x.t)}</div><div style="font-size:12px;color:var(--ink-3);margin-top:2px">${esc(x.s)}</div></div>
            <span class="status-pill ${x.cls}" style="white-space:nowrap">${esc(x.pill)}</span>
          </div>`).join('') || '<div style="font-size:12.5px;color:var(--ink-3)">Nothing has been held back yet.</div>'}
        </div>
      </div>
    </div>
  </div>`;
  return renderAppShell('journey', 'Journey', content);
}


/* "Since your last diagnosis": the workspace's Business State Diff (deterministic, from the server). */
const DRIFT_WORD = { GOAL_DRIFT: 'Goal changed', STRATEGY_DRIFT: 'Strategy shifted', CONSTRAINT_SHIFT: 'Main problem changed', EXECUTION_DRIFT: 'Acted, nothing moved yet', MARKET_DRIFT: 'Market signals moved' };
const METRIC_WORD = { current_monthly: 'Monthly income', capacity_utilization: 'Time used', willingness_to_pay: 'Willingness to pay', demand_sufficiency: 'Demand', avg_deal_size: 'Average deal' };
function sinceLastDiagnosisHtml(paths) {
  const w = LIVE.workspace, diff = w && w.last_diff;
  if (!diff || !diff.anything_changed) return '';
  const fmtV = (k, v) => v == null ? 'not measured' : (k === 'current_monthly' || k === 'avg_deal_size' ? fmtM(v) : (k === 'capacity_utilization' ? Math.round(v * 100) + '%' : String(v).replace(/_/g, ' ').toLowerCase()));
  const rows = [];
  Object.entries(diff.changed_metrics || {}).forEach(([k, v]) => rows.push([METRIC_WORD[k] || k, `${fmtV(k, v.from)} → ${fmtV(k, v.to)}`]));
  Object.entries(diff.path_status_changes || {}).forEach(([k, v]) => {
    const p = paths.find(x => x.key === k);
    const word = st => ({ ELIGIBLE: 'OPEN', CONDITIONAL: 'TEST FIRST', NOT_YET: 'NOT YET', BLOCKED: 'STOP', STOP: 'STOP' })[st] || st || 'none';
    rows.push([p ? p.name : k, `${word(v.from)} → ${word(v.to)}`]);
  });
  if (diff.spectrum_change) rows.push(['Verdict', `${diff.spectrum_change.from.replace('_', ' ')} → ${diff.spectrum_change.to.replace('_', ' ')}`]);
  if (diff.constraint_migration) rows.push(['Main problem', 'Changed since last time']);
  const drift = (w.drift || []).map(t => `<span class="status-pill test_first">${esc(DRIFT_WORD[t] || t)}</span>`).join(' ');
  return `
    <div class="card-clean" style="padding:20px 22px">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px">
        <div class="section-meta-label" style="margin:0">Since your last diagnosis</div><div style="display:flex;gap:6px;flex-wrap:wrap">${drift}</div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px">
        ${rows.map(r => `<div style="border:1px solid var(--border);border-radius:10px;padding:10px 12px"><div style="font-size:11.5px;color:var(--ink-3)">${esc(r[0])}</div><div style="font-family:var(--font-ui);font-size:13px;font-weight:700;margin-top:2px">${esc(r[1])}</div></div>`).join('')}
      </div>
    </div>`;
}


/* ==========================================================================
   V11 MAPS (record D3, D8). One workspace, two lenses (Explore, Readiness) over one set of paths and one
   selection (internal-docs, int 08 §6.2). Lens controller ported from the prototype.
   ========================================================================== */
/* ==========================================================================
   V11 JOURNEY (record P5d; int 10 §6.4; prototype screen08 with the R2 rules of int 06 §12.2).
   What has been recorded, in the order it happened, and what each check-in changed. Four things stay apart:
   ACTUAL (what you reported), TARGET (the goal on record, drawn dashed), TREND (a straight line through recorded
   check-ins, labelled, only with enough of them, never anchored to the goal) and nothing else. No goal on record means
   no goal line; no deadline on record means no timeline and no day counter; no income on record says "not recorded".
   Demo and live read one view-model (journeyVm); only its source differs.
   ========================================================================== */
const PROJECTION_MIN_CHECKINS = 3;   // fewest recorded check-ins a straight-line trend may be drawn from
/* Shared SVG text measuring (Journey goal chart label placement): canvas-measured, never guessed */
const V12_MEASURE = (() => {
  let ctx = null;
  return (t, size, weight) => {
    t = String(t || '');
    try {
      ctx = ctx || document.createElement('canvas').getContext('2d');
      ctx.font = `${weight || 500} ${size}px "Plus Jakarta Sans", sans-serif`;
      return ctx.measureText(t).width * 1.03;      // a little air: SVG text is not pixel-snapped
    } catch (e) { return t.length * size * 0.6; }
  };
})();
/* Smallest round axis value at or above x (1, 2, 2.5 or 5 times a power of ten): short, honest axis labels */
function niceCeil(x) {
  const p = Math.pow(10, Math.floor(Math.log10(x)));
  return [1, 2, 2.5, 5, 10].map(m => m * p).find(v => v >= x);
}
/* The day a check-in happened, counted from the day the map began (the real date when the record has one). */
function journeyDayOf(rec) {
  return rec.ts && LIVE.startTs ? Math.max(1, Math.floor((rec.ts - LIVE.startTs) / 86400000) + 1) : rec.day;
}
function journeyVm() {
  const snap = V11_ENGINE.snapshot();
  const nameOf = key => (snap.paths.find(p => p.id === key) || {}).title || JOURNEY_PATH_NAMES[key] || '';
  if (IS_DEMO) {
    const rs = useRoadmapStore.getState(), tl = getTimeline();
    const goal = Number(rs.goalRp) > 0 ? Number(rs.goalRp) : null;
    return { goal, horizon: Number(rs.horizonDays) > 0 ? Number(rs.horizonDays) : GOAL_DAY, ending: rs.ending, earned: Number.isFinite(rs.earned) ? rs.earned : null,
      day: tl.day, daysLeft: tl.daysLeft, nextCheckIn: tl.nextCheckIn, cycle: tl.cycle,
      history: rs.history.map(r => ({ cycle: r.cycle, day: r.day, rp: r.rp, outcome: r.outcome, title: r.title, path: r.path, pathName: nameOf(r.path), event: r.event,
        rows: [r.outcome === 'missed' ? 'No check-in this week' : `${r.contacted} contacted · ${r.replies} replies · ${r.calls} calls`, r.paid ? `New payment: ${fmtM(r.paid)}` : null, r.note || null].filter(Boolean) })),
      now: { step: rs.currentStep, label: (rs.steps[rs.currentStep - 1] || {}).label || '', pathName: nameOf(rs.activePathId) || JOURNEY_PATH_NAMES[rs.activePathId] || '' },
      sample: JOURNEY_START[STORE.currentPersona] || null, startRp: 0, snap };
  }
  const rs = useRoadmapStore.getState(), g = liveGoal();
  const horizon = liveHorizonKnown() ? liveHorizon() : null;
  const day = liveDay();
  const last = LIVE.checkins.length ? journeyDayOf(LIVE.checkins[LIVE.checkins.length - 1]) : 0;
  const cyc = liveCycleLen();
  const history = LIVE.checkins.map((r, i) => ({ cycle: i + 1, day: journeyDayOf(r), rp: r.rp != null ? r.rp : null, outcome: r.outcome, title: r.title, path: r.path, pathName: nameOf(r.path), event: null,
    rows: [r.outcome === 'missed' ? 'No check-in this week' : `${r.contacted} contacted · ${r.replies} replies · ${r.calls} calls`, r.paid ? `New payment: ${fmtM(r.paid)}` : null].filter(Boolean) }));
  const cur = rs.steps[rs.currentStep - 1];
  /* A-27/A-28: a non-revenue goal is NOT forced onto the income axis — the goal is carried separately
     (metric + metric-unit value) so Journey displays it with its own semantics. */
  const jg = (V11_ENGINE.snapshot().goal || {}).metric || null;
  const jNonRevenue = !!(jg && jg.id !== 'revenue_monthly');
  return { goal: jNonRevenue ? null : (g.target != null && g.target > 0 ? g.target : null), horizon, ending: rs.ending, earned: liveEarnedKnown() ? liveEarned() : null,
    day, daysLeft: horizon ? Math.max(horizon - day, 0) : null, nextCheckIn: last + cyc, cycle: history.length + 1, history,
    now: { step: rs.currentStep, label: cur ? cur.label : '', pathName: nameOf(liveActivePathKey()) }, sample: null,
    startRp: ((LIVE.baseline || {}).revenue_state || {}).current_monthly != null ? LIVE.baseline.revenue_state.current_monthly : null, snap,
    metric: jNonRevenue ? jg : null, metricNow: jNonRevenue && jg.current != null ? jg.current : null };
}
/* ── Goal-relative trajectory (JOURNEY, non-revenue goals) ───────────────────────────────────────────────
   The active goal's own metric, in its own unit. Source: the server's `goal_series` for THIS goal (observations that
   passed the measurement contract). The UI plots those points and words the server's assessment; it never computes
   attainment, never joins dots across different populations, never draws a point or a trend that was not observed,
   and never puts income on this axis. Without a valid observation it says what is known and what is missing. */
const J_REJECT_WORD = {
  RATE_PERIOD_UNVERIFIABLE: 'the period could not be pinned to exact dates',
  RATE_PERIOD_MISMATCH: 'the period is not as long as the goal’s window',
  RATE_PERIOD_INVALID: 'the period dates are impossible or not finished yet',
  RATE_PERIOD_MISSING: 'no period was given',
  RATE_COHORT_MISSING: 'no group was named',
  RATE_COHORT_MISMATCH: 'the group is not the one the goal names',
  RATE_INCOMPLETE: 'the counts were incomplete',
  RATE_DENOMINATOR_ZERO: 'nothing was in the denominator',
  RATE_NEGATIVE: 'a count was negative',
  RATE_NUMERATOR_EXCEEDS_DENOMINATOR: 'more won than were counted'
};
const J_ASSESS_WORD = { ACHIEVED: 'Target reached', NOT_ACHIEVED: 'Target not reached yet', NOT_COMPUTABLE: 'Cannot be assessed from the evidence yet' };
function journeyGoalLine(jm) {
  const dir = jm.direction || '', t = jm.target != null ? fmtGoalValue(jm, jm.target) : null;
  if (t == null) return 'No target set yet';
  if (dir === 'DECREASE_TO_THRESHOLD' || dir === 'AT_MOST') return `Goal: ${t} or lower`;
  if (dir === 'MAINTAIN_RANGE') return 'Goal: stay inside the range on record';
  return `Goal: ${t} or more${jm.window ? ` in ${jm.window}-day windows` : ''}`;
}
function journeyGoalLimits(se) {
  const out = [];
  const rej = (se.rejected && se.rejected.count) || 0;
  if (rej) {
    const why = [...new Set(((se.rejected.codes) || []).map(c => J_REJECT_WORD[c]).filter(Boolean))];
    out.push(`${rej} measurement${rej === 1 ? '' : 's'} recorded but not plotted${why.length ? ': ' + why.join('; ') : ''}.`);
  }
  if (se.excluded_incomparable) out.push(`${se.excluded_incomparable} measurement${se.excluded_incomparable === 1 ? '' : 's'} recorded under an earlier definition of this goal ${se.excluded_incomparable === 1 ? 'is' : 'are'} not plotted.`);
  return out;
}
function journeyGoalChart(vm) {
  const jm = vm.metric, se = jm.series;
  const stale = se && (LIVE.state && LIVE.state.goal && LIVE.state.goal.goal_id) && se.goal_id && se.goal_id !== LIVE.state.goal.goal_id;
  const head = `<div class="j-chart-tools"><div class="j-chart-tools-l"><div class="section-meta-label mb-0">${esc(jm.name.toUpperCase())}, TOWARD YOUR GOAL</div></div></div>`;
  const limits = !se || stale ? [] : journeyGoalLimits(se);
  const limitHtml = limits.length ? `<p class="j-chart-note j-proj-note" data-j-limits>${limits.map(esc).join(' ')}</p>` : '';
  const assess = jm.assessment ? `<p class="j-chart-note j-assess" data-j-assessment="${esc(jm.assessment)}"><b>${esc(J_ASSESS_WORD[jm.assessment] || jm.assessment)}.</b> This is the server’s reading of the recorded evidence.</p>` : '';
  const shell = (inner, kind) => `<div class="card-clean j-chartcard j-gcard" data-j-goal-chart="${kind}" data-j-metric="${esc(jm.id || '')}" data-j-unit="${esc(jm.unit || '')}">${head}${inner}</div>`;
  const known = [
    `<li><span>Goal</span><b data-j-goal-line>${esc(journeyGoalLine(jm).replace(/^Goal: /, ''))}</b></li>`,
    se && se.baseline != null ? `<li><span>Baseline</span><b>${esc(fmtGoalValue(jm, se.baseline))}</b></li>` : '',
    `<li><span>Measured now</span><b>${jm.current != null ? esc(fmtGoalValue(jm, jm.current)) : 'Not measured yet'}</b></li>`
  ].join('');
  if (!se || stale) {
    return shell(`<div class="j-gempty" data-j-empty="unavailable"><p class="j-gempty-t">No trajectory is available for this goal yet.</p><ul class="j-gknown">${known}</ul><p class="j-chart-note">Nothing is drawn until the record holds a valid observation of ${esc(jm.name.toLowerCase())}.</p></div>`, 'empty');
  }
  if (se.status === 'UNSUPPORTED') {
    const crit = (se.criteria || []).map(c => `<li data-j-criterion><span>${esc(c.criterion)}</span><b>${c.met === true ? 'Met' : c.met === false ? 'Not met' : 'Not known'}</b></li>`).join('');
    return shell(`<div class="j-gempty" data-j-empty="unsupported"><p class="j-gempty-t">${crit ? 'This goal is judged by evidence, not by a number.' : 'This goal has no number to plot.'}</p><ul class="j-gknown">${crit || known}</ul><p class="j-chart-note">There is no axis for it, so none is drawn.</p>${assess}${limitHtml}</div>`, 'unsupported');
  }
  if (se.status !== 'OBSERVED' || !se.points.length) {
    return shell(`<div class="j-gempty" data-j-empty="no-observations"><p class="j-gempty-t">No valid observation of ${esc(jm.name.toLowerCase())} yet.</p><ul class="j-gknown">${known}</ul><p class="j-chart-note">A trajectory needs recorded observations. Nothing is drawn, and a missing value is not zero.</p>${assess}${limitHtml}</div>`, 'no-observations');
  }
  /* geometry: a phone gets its own narrower canvas instead of a shrunken desktop one */
  const narrow = window.matchMedia && window.matchMedia('(max-width: 640px)').matches;
  const W = narrow ? 340 : 880, H = 232, X0 = narrow ? 46 : 62, X1 = W - (narrow ? 16 : 26), YT = 28, YB = 176;
  /* Day 0 = the day the map began. Evidence recorded earlier (backfilled) sits LEFT of it, at its real date. */
  const origin = LIVE.startTs || se.points[0].ts * 1000;
  const dayOfTs = ts => (ts * 1000 - origin) / 86400000;
  const pts = se.points.map(p => Object.assign({}, p, { day: dayOfTs(p.ts) }));
  const horizon = vm.horizon || null;
  const dMin = Math.min(0, ...pts.map(p => p.day)), dMax = Math.max(horizon || 0, ...pts.map(p => p.day), vm.day || 0, 1);
  const xOf = d => X0 + (Math.min(Math.max(d, dMin), dMax) - dMin) * ((X1 - X0) / (dMax - dMin));
  const vals = pts.map(p => p.value).concat([se.target, se.baseline, se.target_min, se.target_max].filter(v => v != null));
  const yTop = niceCeil(Math.max(...vals, 1e-9) * 1.15), yOf = v => YB - Math.min(Math.max(v, 0) / yTop, 1) * (YB - YT);
  const ft = v => esc(fmtGoalValue(jm, v));
  const txt = (x, y, t, o) => { o = o || {}; return `<text x="${x}" y="${y}"${o.a ? ` text-anchor="${o.a}"` : ''} font-family="Plus Jakarta Sans" font-size="${o.s || 9.5}" font-weight="${o.w || 500}" fill="${o.f || 'var(--ink-3)'}">${t}</text>`; };
  const whole = se.kind === 'count' || ['leads', 'inquiries', 'partners', 'messages'].includes(jm.unit);   // a count has no half-units
  const grid = [0, ...(whole && yTop % 2 ? [] : [yTop / 2]), yTop].map(v => `<line x1="${X0}" y1="${yOf(v)}" x2="${X1}" y2="${yOf(v)}" stroke="var(--border)" stroke-width="1"${v ? ' stroke-dasharray="3 3"' : ''}/>${txt(X0 - 6, yOf(v) + 3.5, ft(v), { a: 'end' })}`).join('');
  const band = se.target_min != null && se.target_max != null ? `<rect x="${X0}" y="${yOf(se.target_max)}" width="${X1 - X0}" height="${Math.max(2, yOf(se.target_min) - yOf(se.target_max))}" fill="var(--open-soft)" opacity="0.7" data-j-range/>` : '';
  const tgt = se.target != null ? `<line data-j-target data-value="${se.target}" x1="${X0}" y1="${yOf(se.target)}" x2="${X1}" y2="${yOf(se.target)}" stroke="var(--ink-3)" stroke-width="1.3" stroke-dasharray="3 4"/>` : '';
  const base = se.baseline != null ? `<line data-j-baseline data-value="${se.baseline}" x1="${X0}" y1="${yOf(se.baseline)}" x2="${X1}" y2="${yOf(se.baseline)}" stroke="var(--border-strong)" stroke-width="1" stroke-dasharray="1 4"/>` : '';
  /* a line only joins two observations of the same population; a lone observation is a dot, never a trend */
  const segs = {}; pts.forEach(p => { (segs[p.segment || 0] = segs[p.segment || 0] || []).push(p); });
  const lines = Object.values(segs).filter(a => a.length > 1).map(a => `<polyline data-j-line points="${a.map(p => `${xOf(p.day).toFixed(1)},${yOf(p.value).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--open-line)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`).join('');
  const dateOf = ts => new Date(ts * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' });
  const dots = pts.map((p, i) => {
    const tip = `${fmtGoalValue(jm, p.value)} · recorded ${dateOf(p.ts)}` + (p.cohort ? ` · ${p.cohort}` : '') + (p.period_start_ts ? ` · period ${dateOf(p.period_start_ts)} to ${dateOf(p.period_end_ts)}` : '') + (p.numerator != null ? ` · ${p.numerator} of ${p.denominator}` : '');
    const last = i === pts.length - 1;
    return `<g class="j-gpoint" data-j-point data-value="${p.value}" data-ts="${p.ts}" data-segment="${p.segment || 0}" tabindex="0" role="img" aria-label="${esc(tip)}"><title>${esc(tip)}</title><circle cx="${xOf(p.day).toFixed(1)}" cy="${yOf(p.value).toFixed(1)}" r="${last ? 6 : 4.5}" fill="${last ? 'var(--open-line)' : 'var(--surface)'}" stroke="var(--open-line)" stroke-width="2"/></g>`;
  }).join('');
  /* Words on the chart go where they meet nothing: the dots are claimed first, then the last value, the deadline and the axis words,
     then the target and baseline words; each tries its places in order and is left out (the legend and the table still say it) when
     none is free. Widths are measured, never guessed. */
  const occ = [];
  const claim = (x0, y0, x1, y1) => occ.push({ x0, y0, x1, y1 });
  const roomFor = r => r.x0 >= 2 && r.x1 <= W - 2 && !occ.some(b => r.x0 < b.x1 + 3 && r.x1 > b.x0 - 3 && r.y0 < b.y1 + 2 && r.y1 > b.y0 - 2);
  const put = (label, size, weight, cands, o) => {
    const w = V12_MEASURE(label, size, weight);
    for (const [x, y, a] of cands) {
      const x0 = a === 'end' ? x - w : a === 'middle' ? x - w / 2 : x, r = { x0, y0: y - size, x1: x0 + w, y1: y + 3 };
      if (roomFor(r)) { claim(r.x0, r.y0, r.x1, r.y1); return txt(x, y, esc(label), Object.assign({ a, s: size, w: weight }, o)); }
    }
    return '';
  };
  const fr = v => fmtGoalValue(jm, v);
  claim(0, YT - 12, X0 - 2, YB + 6);                                  // the value labels of the vertical axis
  pts.forEach(p => claim(xOf(p.day) - 8, yOf(p.value) - 8, xOf(p.day) + 8, yOf(p.value) + 8));
  const lastP = pts[pts.length - 1], lx = xOf(lastP.day), ly = yOf(lastP.value);
  const lastLab = put(fr(lastP.value), 10.5, 700, [[lx, ly - 15, 'middle'], [lx, ly + 24, 'middle'], [lx + 12, ly + 4, 'start'], [lx - 12, ly + 4, 'end']], { f: 'var(--ink)' });
  const today = vm.day ? `<line x1="${xOf(vm.day)}" y1="${YT - 6}" x2="${xOf(vm.day)}" y2="${YB}" stroke="var(--border-strong)" stroke-width="1"/>${put('Today', 9.5, 500, [[xOf(vm.day), YT - 10, 'middle']])}` : '';
  const dl = horizon ? `<line x1="${X1}" y1="${YT - 6}" x2="${X1}" y2="${YB}" stroke="var(--ink-3)" stroke-width="1.2" stroke-dasharray="2 3"/>${put('Deadline · Day ' + horizon, 9.5, 600, [[X1, YB + 14, 'end']], { f: 'var(--ink-2)' })}` : '';
  const axisY = [YB + 14, YB + 26];
  const ticks = put(dMin < -0.5 ? 'Map began' : 'Day 0', 9.5, 500, axisY.map(y => [xOf(0), y, 'middle']))
    + (dMin < -0.5 ? put(Math.abs(Math.floor(dMin)) + ' days before', 9.5, 500, axisY.map(y => [xOf(dMin), y, 'start'])) : '')
    + (horizon ? '' : put('Day ' + Math.round(dMax), 9.5, 500, axisY.map(y => [X1, y, 'end'])));   // the deadline carries its own label
  const tgtTxt = se.target != null ? put('Target ' + fr(se.target), 9.5, 700, [[X0 + 4, yOf(se.target) - 5, 'start'], [X1 - 8, yOf(se.target) - 5, 'end'], [X0 + 4, yOf(se.target) + 13, 'start'], [X1 - 8, yOf(se.target) + 13, 'end']], { f: 'var(--ink-2)' }) : '';
  const baseTxt = se.baseline != null ? put('Baseline ' + fr(se.baseline), 9.5, 500, [[X1 - 8, yOf(se.baseline) + 12, 'end'], [X0 + 4, yOf(se.baseline) + 12, 'start'], [X1 - 8, yOf(se.baseline) - 5, 'end'], [X0 + 4, yOf(se.baseline) - 5, 'start']]) : '';
  const began = dMin < -0.5 ? `<line x1="${xOf(0)}" y1="${YT - 6}" x2="${xOf(0)}" y2="${YB}" stroke="var(--border-strong)" stroke-width="1" stroke-dasharray="1 3"/>` : '';
  const one = pts.length === 1 ? '<p class="j-chart-note j-proj-note" data-j-one>One valid observation: a direction needs at least two comparable ones, so no trend is drawn.</p>' : '';
  const cohortBreak = Object.keys(segs).length > 1 ? '<p class="j-chart-note j-proj-note">The group measured changed along the way, so those dots are not joined.</p>' : '';
  const rows = pts.map(p => `<tr><td>${esc(dateOf(p.ts))}</td><td data-j-cell-value>${esc(fmtGoalValue(jm, p.value))}</td><td>${esc(p.cohort || '')}</td><td>${p.period_start_ts ? esc(dateOf(p.period_start_ts) + ' to ' + dateOf(p.period_end_ts)) : ''}</td></tr>`).join('');
  const legend = `<div class="j-legend"><span>${`<svg width="22" height="6" aria-hidden="true"><line x1="0" y1="3" x2="22" y2="3" stroke="var(--open-line)" stroke-width="2.5"/></svg>`}Valid observation</span><span><svg width="22" height="6" aria-hidden="true"><line x1="0" y1="3" x2="22" y2="3" stroke="var(--ink-3)" stroke-width="1.3" stroke-dasharray="3 4"/></svg>Target</span>${se.baseline != null ? '<span><svg width="22" height="6" aria-hidden="true"><line x1="0" y1="3" x2="22" y2="3" stroke="var(--border-strong)" stroke-width="1" stroke-dasharray="1 4"/></svg>Baseline</span>' : ''}</div>`;
  const aria = `${jm.name} at each valid observation, in ${jm.unit === 'ratio' ? 'percent' : jm.unit || 'its own unit'}${se.target != null ? ', against the target of ' + fmtGoalValue(jm, se.target) : ''}. ${pts.length} observation${pts.length === 1 ? '' : 's'}.`;
  return shell(`<div class="j-gtop"><span class="j-chart-note" data-j-goal-line>${esc(journeyGoalLine(jm))}</span>${legend}</div>
      <svg data-j-chart="goal" viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;overflow:visible" xmlns="http://www.w3.org/2000/svg" role="group" aria-label="${esc(aria)}">${grid}${band}${base}${tgt}${began}${today}${dl}${lines}${dots}${lastLab}${ticks}${tgtTxt}${baseTxt}</svg>
      ${one}${cohortBreak}${assess}${limitHtml}
      <table class="sr-only" data-j-table><caption>${esc(jm.name)}: valid observations</caption><thead><tr><th>Recorded</th><th>${esc(jm.name)}</th><th>Group</th><th>Period</th></tr></thead><tbody>${rows}</tbody></table>`, 'series');
}

/* The Journey inspector: what the state block itself holds back, and nothing else. It is the page's only
   right column (doc 21 §3 "Journey: 'On hold' lives in a hideable side panel"), so the grid, the timeline and
   the chart keep the main pane. */
function journeyHoldPanel(holdItems) {
  return `
  <aside class="ws-side j-side has-panel-hide" id="j-side" aria-label="What is on hold">
    ${wsPanelHideBtn('j-side-toggle', 'j-side', 'setJourneySide', 'what is on hold')}
    <section class="ws-sec j-hold-side">
      <div class="section-meta-label mb-12">ON HOLD</div>
      ${holdItems.length ? `
      <p class="j-lead">These are on hold until the record gives a reason to move on them. Putting something on hold is not a recorded decision or a result.</p>
      <div class="j-dec-list">
        ${holdItems.map((h, i) => `${i ? '<div class="j-sep"></div>' : ''}<div class="j-dec-row"><div><div class="j-dec-title">${stratEsc(h)}</div></div><span class="status-pill hold">On hold</span></div>`).join('')}
      </div>` : '<div class="j-hist-empty">Nothing is on hold for this map.</div>'}
    </section>
  </aside>`;
}

function screenJourney11() {
  const vm = journeyVm();
  const { goal, horizon, history, ending, earned, snap } = vm;
  const noHorizon = horizon === null;           // no deadline on record: no timeline is drawn and none is invented
  const span = horizon || 1;
  const incomeRecorded = earned !== null && earned !== undefined;
  const fmtRp = rp => rp ? fmtM(rp) : 'Rp0';
  const endLabel = noHorizon ? 'Final check-in' : `Day ${horizon}`;
  /* Non-revenue goal (A-27/A-28): used with its own semantics — NOT pulled
     onto the income axis (the "RpX / month" line for leads targets = mixed units). */
  const jm = vm.metric || null;
  const reachedAt = goal && !jm ? history.find(r => r.rp != null && r.rp >= goal) : null;

  // Chart scale: the map's own deadline across the chart; the income scale comes from the larger of the goal and what was recorded
  const X0 = 55, X1 = 860;
  const xOf = day => X0 + Math.min(day, span) * ((X1 - X0) / span);
  const inSpan = n => noHorizon || n.day <= horizon;           // a check-in dated past the deadline is listed, never plotted
  const maxRp = Math.max(goal || 0, incomeRecorded ? earned : 0, ...history.filter(inSpan).map(r => r.rp || 0), 1);
  const yTop = niceCeil(maxRp * 1.2);
  const yOf = rp => 192 - Math.min(Math.max(rp, 0) / yTop, 1) * 154;

  // Goal-Relative labels (int 09 par 6 JOURNEY): the tracked measure names itself; revenue
  // wording only for revenue goals. Check-ins without a recorded value stay honest, never zero.
  // The plotted series IS monthly income — rows say "Income after" in every case, so the label
  // never renames an income value into a leads/rate value (A-02 cross-unit rule).
  const jmet = jm;
  const jMeasure = 'Income';
  const jGoalLine = jm
    ? (jm.target != null
        ? `Goal set: ${fmtGoalValue(jm, jm.target)} ${jm.name.toLowerCase()}${jm.window ? ` in ${jm.window}-day windows` : (horizon ? ` within ${horizon} days` : '')}`
        : `Goal on record: ${jm.name.toLowerCase()} — target not set yet`)
    : (goal
        ? `Goal set: ${fmtM(goal)} a month${horizon ? ` within ${horizon} days` : ''}`
        : 'No goal on record yet');
  // Nodes: the start (only when the starting income is known), every check-in, and "now" while a round is in progress
  const nodes = [{
    day: 0, rp: vm.startRp, kind: 'start', label: 'START · DAY 0', title: 'Your state is mapped',
    rows: [jGoalLine, vm.sample ? vm.sample[0] : null].filter(Boolean),
    saved: vm.sample ? vm.sample[1] : null
  }];
  history.forEach(r => nodes.push({ day: r.day, rp: r.rp, kind: r.outcome, event: r.event, label: `CHECK-IN ${r.cycle} · DAY ${r.day}`, title: r.title,
    rows: jm ? r.rows : [...r.rows, r.rp != null ? `${jMeasure} after: ${fmtRp(r.rp)}` : `${jMeasure} not recorded at this check-in`], saved: null }));
  const showNow = !ending && (history.length === 0 || vm.now.step > 1 || vm.now.label);
  if (showNow) nodes.push({ day: vm.day, rp: null, kind: 'now',   // a marker on the day axis: it claims no income, and it never anchors the trend
     label: `NOW · DAY ${vm.day}`, title: `Check-in ${vm.cycle} is next`,
    rows: [vm.now.pathName, vm.now.label, noHorizon ? '' : `Check-in on Day ${vm.nextCheckIn}`].filter(Boolean), saved: null });
  else if (!ending && history.length) nodes[nodes.length - 1].now = true;
  window.__journeyNodes = nodes;

  const plotted = nodes.map((n, i) => i).filter(i => inSpan(nodes[i]) && nodes[i].rp != null);   // the line uses dated points inside the deadline that carry an income
  const pts = nodes.map(n => ({ x: xOf(n.day), y: yOf(n.rp == null ? 0 : n.rp) }));
  let realized = '';
  if (plotted.length) {
    realized = `M ${pts[plotted[0]].x} ${pts[plotted[0]].y}`;
    for (let j = 1; j < plotted.length; j++) { const a = pts[plotted[j - 1]], b = pts[plotted[j]], mx = (a.x + b.x) / 2; realized += ` C ${mx} ${a.y} ${mx} ${b.y} ${b.x} ${b.y}`; }
  }
  const lastIdx = plotted.length ? plotted[plotted.length - 1] : -1;

  /* Trend. A straight line through the income recorded at the last (up to four) check-ins that happened, continued to the
     map's own deadline: "if the recent pace holds". It needs PROJECTION_MIN_CHECKINS real check-ins that carry an income;
     with fewer there is nothing to project from, so nothing is drawn. Never anchored to the goal. Labelled a trend. */
  const recorded = history.filter(r => r.outcome !== 'missed' && r.rp != null && inSpan(r));
  const hasProjection = horizon !== null && !ending && recorded.length >= PROJECTION_MIN_CHECKINS && lastIdx >= 0;
  let estimateSvg = '', projectionNote = '';
  if (hasProjection) {
    const recent = recorded.slice(-4), a = recent[0], b = recent[recent.length - 1];
    const slope = (b.rp - a.rp) / Math.max(b.day - a.day, 1);
    const lastNode = nodes[lastIdx];
    const est = Math.max(0, Math.round((lastNode.rp + slope * (horizon - lastNode.day)) * 10) / 10);
    const ex = xOf(horizon), ey = yOf(est), last = pts[lastIdx];
    estimateSvg = `
        <path d="M ${last.x} ${last.y} L ${ex} ${ey}" fill="none" stroke="var(--ink-muted)" stroke-width="1.5" stroke-dasharray="5 4"/>
        <circle cx="${ex}" cy="${ey}" r="3.5" fill="var(--surface)" stroke="var(--ink-muted)" stroke-width="1.5"/>
        <text x="${ex - 6}" y="${ey + (ey < 60 ? 16 : -8)}" font-family="Plus Jakarta Sans" font-size="9" font-weight="600" text-anchor="end" fill="var(--ink-2)">If the recent pace holds: about ${fmtRp(est)} by Day ${horizon}</text>`;
    projectionNote = `The dashed grey line is a straight-line trend from your last ${recent.length} recorded check-ins. It is not a forecast.`;
  } else if (!ending) {
    projectionNote = `No projection yet. A trend needs at least ${PROJECTION_MIN_CHECKINS} recorded check-ins with an income, and ${recorded.length} ${recorded.length === 1 ? 'is' : 'are'} on record.`;
  }

  const nodesSvg = nodes.map((n, i) => {
    if (!inSpan(n)) return '';
    const p = pts[i], onAxis = n.rp == null;
    const st = OUTCOME_STYLE[n.kind] || { color: 'var(--open-line)' };
    const isNow = n.kind === 'now' || n.now;
    const flag = n.event && EVENT_FLAGS[n.event] ? `<text x="${p.x}" y="${i % 2 ? p.y - 13 : p.y + 20}" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="600" text-anchor="middle" fill="var(--ink-2)" pointer-events="none">${EVENT_FLAGS[n.event]}</text>` : '';
    return `
        <g class="j-node" tabindex="0" role="button" aria-label="${esc(n.label)}: ${esc(n.title)}"
           onmouseenter="showJourneyTip(this, ${i})" onmouseleave="hideJourneyTip()" onfocus="showJourneyTip(this, ${i})" onblur="hideJourneyTip()">
          <circle cx="${p.x}" cy="${p.y}" r="14" fill="transparent"/>
          ${isNow ? `<circle class="map-pulse" cx="${p.x}" cy="${p.y}" r="7" fill="none" stroke="var(--open-line)" stroke-width="2"/>` : ''}
          <circle class="j-ring" cx="${p.x}" cy="${p.y}" r="${n.kind === 'final' ? 7 : 5}" fill="${isNow || n.kind === 'final' ? 'var(--open-line)' : 'var(--surface)'}" stroke="${n.kind === 'start' ? 'var(--ink)' : st.color}" stroke-width="2"${onAxis ? ' stroke-dasharray="2 2"' : ''}/>
        </g>${flag}`;
  }).join('');

  // Path each week: one lane per path worked, one bar per check-in, on the same day axis as the income line
  const ROUTE_TOP = 230, LANE_H = 30, FIRST_LANE = ROUTE_TOP + 28;
  const worked = history.filter(r => r.path && inSpan(r));
  const laneKeys = [];
  worked.forEach(r => { if (!laneKeys.includes(r.path)) laneKeys.push(r.path); });
  const laneY = key => FIRST_LANE + laneKeys.indexOf(key) * LANE_H;
  const routeBottom = laneKeys.length ? FIRST_LANE + (laneKeys.length - 1) * LANE_H + 18 : ROUTE_TOP - 6;
  const routeSvg = laneKeys.length ? `
        <text x="10" y="${ROUTE_TOP}" font-family="Plus Jakarta Sans" font-size="9" font-weight="700" letter-spacing="0.06em" fill="var(--ink-3)">PATH WORKED, CHECK-IN BY CHECK-IN</text>
        ${laneKeys.map(key => `
        <text x="${X0}" y="${laneY(key) - 8}" font-family="Plus Jakarta Sans" font-size="9.5" font-weight="600" fill="var(--ink-2)">${esc((worked.find(r => r.path === key) || {}).pathName || '')}</text>
        <line x1="${X0}" y1="${laneY(key)}" x2="${X1}" y2="${laneY(key)}" stroke="var(--surface-tint)" stroke-width="8" stroke-linecap="round"/>`).join('')}
        ${worked.map((r, i) => {
          const prevDay = i ? worked[i - 1].day : 0;
          const x1 = xOf(prevDay) + 2, x2 = Math.max(xOf(r.day) - 2, x1 + 6), y = laneY(r.path);
          const color = (OUTCOME_STYLE[r.outcome] || {}).color || 'var(--ink-muted)';
          const idx = nodes.findIndex(n => n.kind === r.outcome && n.day === r.day && n.title === r.title);
          return `<g ${idx >= 0 ? `class="j-node" tabindex="0" role="button" aria-label="Check-in ${r.cycle}: ${esc(r.pathName)}" onmouseenter="showJourneyTip(this, ${idx})" onmouseleave="hideJourneyTip()" onfocus="showJourneyTip(this, ${idx})" onblur="hideJourneyTip()"` : ''}>
          <rect x="${x1}" y="${y - 10}" width="${x2 - x1}" height="20" fill="transparent"/>
          <rect class="j-ring" x="${x1}" y="${y - 4}" width="${x2 - x1}" height="8" rx="4" fill="${color}"${['none', 'missed'].includes(r.outcome) ? ' fill-opacity="0.55"' : ''}/></g>`;
        }).join('')}` : '';
  const weekMarks = noHorizon ? '' : Array.from({ length: Math.ceil(horizon / 7) }, (_, i) => i + 1).map(k => {
    const isCur = !ending && vm.day > (k - 1) * 7 && vm.day <= k * 7;
    return `${k * 7 < span ? `<line x1="${xOf(k * 7)}" y1="38" x2="${xOf(k * 7)}" y2="${routeBottom}" stroke="var(--surface-tint)" stroke-width="1"/>` : ''}
        <text x="${xOf(Math.min(k * 7 - 3.5, span - 2.5))}" y="208" font-family="Plus Jakarta Sans" font-size="9" text-anchor="middle" font-weight="${isCur ? '700' : '400'}" fill="${isCur ? 'var(--ink)' : 'var(--ink-3)'}">W${k}</text>`;
  }).join('');

  let headline = 'What is recorded on this journey, check-in by check-in.';
  if (!history.length) headline = 'No check-ins are recorded yet.';
  else if (jm && ending) headline = `${endLabel} reached. ${J_ASSESS_WORD[jm.assessment] || 'No verified measurement of ' + jm.name.toLowerCase() + ' on record'}.`;
  else if (ending === 'miss') headline = (goal && !jm) ? `${endLabel}: ${fmtRp(earned)} a month. Not ${fmtM(goal)} yet.` : `${endLabel}: ${fmtRp(earned)} a month.`;
  else if (ending === 'success' && goal && !jm) headline = `${endLabel}: you reached your goal.`;
  else if (reachedAt) headline = 'You reached your goal. Now keep it steady.';

  const open = (snap.paths || []).filter(p => p.status_display === 'OPEN');
  const holdItems = (snap.state && snap.state.what_not_to_do) || [];
  const historyRows = history.slice().reverse().map(r => {
    const st = OUTCOME_STYLE[r.outcome] || OUTCOME_STYLE.mixed;
    return `
          <div class="j-hist-row">
            <div class="j-hist-k">Check-in ${r.cycle} · Day ${r.day}</div>
            <div style="min-width:0">
              <div class="j-hist-title">${esc(r.title)}</div>
              <div class="j-hist-sub">${esc(r.pathName)}</div>
            </div>
            <span class="status-pill ${st.pill}" style="${st.pill ? '' : 'background:var(--surface-2);color:var(--ink-3);border-color:var(--border)'}">${st.label}</span>
            <div class="j-hist-val">${jm ? '' : r.rp != null ? fmtRp(r.rp) : 'Not recorded'}</div>
          </div>`;
  }).join('');
  const sw = (c, dash) => `<svg width="22" height="6" aria-hidden="true"><line x1="0" y1="3" x2="22" y2="3" stroke="${c}" stroke-width="${dash ? 1.5 : 2.5}"${dash ? ` stroke-dasharray="${dash}"` : ''}/></svg>`;
  const dot = c => `<svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="3.5" fill="var(--surface)" stroke="${c}" stroke-width="2"/></svg>`;

  /* Non-revenue goal: the path lanes keep their own card (which path each check-in worked), on the same day axis,
     and carry no income and no goal value: they are not a measure of the goal. */
  const lanesCardHtml = !jm || noHorizon || !laneKeys.length ? '' : `<div class="card-clean j-chartcard" data-j-lanes>
      <div style="min-width:860px">
      <div class="j-chart-tools"><div class="j-chart-tools-l"><span class="j-chart-note">Which path each check-in worked. This is effort, not a measure of your goal. Point at a bar to see that check-in.</span></div></div>
      <svg viewBox="0 198 880 ${routeBottom + 14 - 198}" style="width:100%;height:auto;display:block;overflow:hidden" xmlns="http://www.w3.org/2000/svg" role="group" aria-label="The path worked at each check-in, against the days of the journey">
        ${weekMarks}
        ${routeSvg}
      </svg>
      </div>
    </div>`;

  /* Timeline first (int 18): what happened, in the order it happened; the chart below supports it. Built once
     here so it can sit above the chart without duplicating the markup. */
  const historyColHtml = `
    <div class="v11-journey-cols">
      <div class="card-clean j-col-hist" style="padding:20px 22px">
        <div class="section-meta-label mb-12">CHECK-IN HISTORY</div>
        ${!ending ? `
        <div class="j-now">
          <div class="j-now-row">
            <div style="min-width:0">
              <div class="j-now-title">Check-in ${vm.cycle}${noHorizon ? '' : ` · by Day ${vm.nextCheckIn}`}${vm.now.pathName ? ` · ${esc(vm.now.pathName)}` : ''}</div>
              <div class="j-now-sub">${vm.now.label ? `Move ${vm.now.step}: ${esc(vm.now.label)}` : 'No move in progress'}</div>
            </div>
            <span class="j-now-chip">IN PROGRESS</span>
          </div>
        </div>` : ''}
        ${history.length ? `<div class="j-hist" tabindex="0" role="region" aria-label="Check-in history">${historyRows}</div>` : '<div class="j-hist-empty">Nothing has been reported yet.</div>'}
        <div style="padding-top:14px">
          ${ending
            ? `<button class="btn-primary" style="width:100%" onclick="renderScreen('16')">See your ${endLabel} review →</button>`
            : `<button class="btn-primary" style="width:100%" onclick="renderScreen('05')">Open check-in ${vm.cycle} →</button>`}
        </div>
      </div>
    </div>`;
  const sideClosed = !!STORE.journeySideClosed;
  const content = `
  <div id="j-root" class="dest-page j-page ws-split${sideClosed ? ' is-collapsed' : ''}" style="position:relative">
    <div class="j-tip" id="j-tip" hidden></div>
    <div class="ws-main"><div class="ws-inner">
    ${v11PageHead({ dest: 'Journey', title: headline, actions: sideClosed ? wsPanelShowBtn('j-side-toggle', 'j-side', 'setJourneySide', 'what is on hold') : '' })}

    <div class="v11-statgrid">
      <div class="card-clean j-statcard">
        <div class="section-meta-label">${jm ? jm.name.toUpperCase() : 'MONTHLY INCOME'}</div>
        ${jm ? `<div class="j-stat">${vm.metricNow != null ? fmtGoalValue(jm, vm.metricNow) : 'Not measured yet'}</div>
        <div class="j-stat-sub">${jm.target != null ? 'Goal: ' + fmtGoalValue(jm, jm.target) + ' ' + jm.name.toLowerCase() : 'Goal target not set yet'}</div>`
        : `<div class="j-stat">${incomeRecorded ? fmtRp(earned) : 'Not recorded'}</div>
        <div class="j-stat-sub">${!incomeRecorded ? 'No income recorded yet' : goal ? `${Math.round(earned / goal * 100)}% of the ${fmtM(goal)} goal` : 'No goal on record yet'}</div>`}
      </div>
      <div class="card-clean j-statcard">
        <div class="section-meta-label">${noHorizon ? 'DEADLINE' : 'DAYS LEFT'}</div>
        <div class="j-stat">${noHorizon ? 'None' : ending ? 0 : vm.daysLeft}</div>
        <div class="j-stat-sub">${noHorizon ? 'No deadline is set' : ending ? `Day ${horizon} reached` : `Day ${vm.day} of ${horizon}`}</div>
      </div>
      <div class="card-clean j-statcard">
        <div class="section-meta-label">PATHS OPEN NOW</div>
        <div class="j-stat">${open.length}</div>
        <div class="j-stat-sub is-clip">${open.length ? open.map(p => esc(p.title)).join(' + ') : 'None are open yet'}</div>
      </div>
      <div class="card-clean j-statcard">
        <div class="section-meta-label">CHECK-INS RECORDED</div>
        <div class="j-stat">${history.length}</div>
        <div class="j-stat-sub">${ending ? 'All done' : noHorizon ? 'Report one when something happens' : `Next check-in: Day ${vm.nextCheckIn}`}</div>
      </div>
    </div>
    ${historyColHtml}

    ${jm ? journeyGoalChart(vm) : ''}
    ${jm ? (noHorizon || !laneKeys.length ? '' : lanesCardHtml) : (noHorizon ? '<p class="j-chart-note j-proj-note">No deadline is set, so there is no timeline to draw. Your recorded check-ins are listed below.</p>' : `<div class="card-clean j-chartcard">
      <div style="min-width:860px">
      <div class="j-chart-tools">
        <div class="j-chart-tools-l">
          <div class="section-meta-label mb-0">MONTHLY INCOME, AND THE PATH BEHIND IT</div>
          <span class="j-chart-note">Point at a dot or a bar to see that check-in</span>
        </div>
        <div class="j-legend">
          <span class="j-legend-item">${sw('var(--open-line)')}Actual</span>
          ${goal ? `<span class="j-legend-item">${sw('var(--border-strong)', '3 4')}Goal (target)</span>` : ''}
          ${hasProjection ? `<span class="j-legend-item">${sw('var(--ink-muted)', '5 4')}Trend if the pace holds</span>` : ''}
          <span class="j-legend-item">${dot('var(--open-line)')}Paid</span>
          <span class="j-legend-item">${dot('var(--notyet-line)')}Mixed</span>
          <span class="j-legend-item">${dot('var(--ink-muted)')}No result</span>
        </div>
      </div>
      <svg viewBox="0 0 880 ${routeBottom + 14}" style="width:100%;height:auto;display:block;overflow:visible" xmlns="http://www.w3.org/2000/svg" role="group" aria-label="Monthly income at each recorded check-in, against the deadline${goal ? ' and the goal' : ''}">
        <line x1="${X0}" y1="${yOf(yTop / 2)}" x2="${X1}" y2="${yOf(yTop / 2)}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 3"/>
        <text x="10" y="${yOf(yTop / 2) + 4}" font-family="Plus Jakarta Sans" font-size="9.5" fill="var(--ink-3)">Rp${yTop / 2}M</text>
        <line x1="${X0}" y1="192" x2="${X1}" y2="192" stroke="var(--border)" stroke-width="1"/>
        <text x="22" y="196" font-family="Plus Jakarta Sans" font-size="9.5" fill="var(--ink-3)">Rp0</text>
        <line x1="${X0}" y1="${yOf(yTop)}" x2="${X1}" y2="${yOf(yTop)}" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 3"/>
        <text x="10" y="${yOf(yTop) + 4}" font-family="Plus Jakarta Sans" font-size="9.5" fill="var(--ink-3)">Rp${yTop}M</text>
        ${goal ? `<line x1="${X0}" y1="${yOf(goal)}" x2="${X1}" y2="${yOf(goal)}" stroke="${reachedAt ? 'var(--open-line)' : 'var(--ink-3)'}" stroke-width="${reachedAt ? 1.5 : 1.2}" stroke-dasharray="3 4"/>
        <text x="${X0 + 4}" y="${yOf(goal) - 6}" font-family="Plus Jakarta Sans" font-size="9" font-weight="700" text-anchor="start" fill="${reachedAt ? 'var(--open-fg)' : 'var(--ink-3)'}">${reachedAt ? `Goal reached on Day ${reachedAt.day} · ${fmtM(goal)} / month` : `Goal · ${fmtM(goal)} / month`}</text>` : ''}
        ${weekMarks}
        ${estimateSvg}
        ${realized ? `<path d="${realized}" fill="none" stroke="var(--open-line)" stroke-width="3" stroke-linecap="round"/>` : ''}
        ${nodesSvg}
        ${routeSvg}
      </svg>
      ${projectionNote ? `<p class="j-chart-note j-proj-note">${projectionNote}</p>` : ''}
      </div>
    </div>`)}
    </div></div>
    ${sideClosed ? '' : journeyHoldPanel(holdItems)}
  </div>`;
  return renderAppShell('journey', 'Journey', content);
}


/* ═══════════════════════════════════════════════════════════════════════════
   MAPS DESTINATION — ported verbatim from Revenue Navigation v11.dc.html @HEAD
   (18 Okt 2026: path-card map with semantic zoom, shared-requirement nodes,
   move detail in the panel, focus state, engine-worded zero screens).
   MVP seams, applied on purpose:
   · selection & move-step keys use v11MapKey() (persona in demo, live session id in live)
   · renderScreen('maps') / renderAppShell('maps', …) instead of the prototype's scene ids
   · presentSnapshotPaths() adapts the shared presentPaths policy to snapshot paths
   · MVP overlay plumbing (overlayOpened) instead of the prototype's overlayEnter
   · no recorded-goal fixtures, no unevaluated custom maps, no emerging card
     (the prototype QA states those screens serve do not exist in the MVP)
   ═══════════════════════════════════════════════════════════════════════════ */

/* Sample-record wording (demo personas only): provenance lines read like a record, not like "your Talk" */
const SAMPLE_RECORD_MAPS = ['dimas', 'rina', 'arif', 'bayu'];

function provText(text, key) {
  const k = key || v11MapKey();
  if (!text || !SAMPLE_RECORD_MAPS.includes(k)) return text;
  return String(text)
    .replace(/\bFrom your Talk\b/g, 'From the sample record')
    .replace(/\bYour Talk\b/g, 'Sample record')
    .replace(/\byour Talk\b/g, 'the sample record');
}

const MOVE_KIND_WORD = { ACTION: 'Ready', EVIDENCE_REQUEST: 'Needs evidence', QUESTION: 'Question', HOLD: 'On hold' }

function movesCollect(snap) {
  const featuredId = snap.nextmove && snap.nextmove.path_id ? snap.nextmove.path_id : null;
  const featured = featuredId ? snap.paths.find(p => p.id === featuredId) || null : null;
  const ready = [];
  const waiting = [];
  snap.paths.forEach(p => {
    if (p.status_display === 'STOP' || p.id === featuredId) return;
    if (p.next_move && p.next_move.type !== 'HOLD') {
      ready.push({ path: p, title: p.next_move.title, why: p.next_move.why, kind: p.next_move.type || 'ACTION' });
    } else if (p.status_display === 'NOT YET') {
      const open = (p.requirements || []).filter(r => r.applicable !== false && r.satisfaction !== 'PRESENT');
      const first = open.find(r => r.satisfaction === 'ABSENT') || open[0] || null;
      waiting.push({ path: p, need: first });
    }
  });
  return { featured, ready, waiting };
}

const MOVE_STEPS_CATALOG = {
  // 3-step complex move: Dimas advise-network (Research -> Draft -> Send)
  'dimas:advise-network': [
    { id: 's1', label: 'Research contacts', instruction: 'Review the 2 past contacts who previously asked for brand or strategy advice.' },
    { id: 's2', label: 'Draft 1-page offer', instruction: 'Prepare a 1-page advisory summary outlining the 2-week scope and Rp7.5M price point.' },
    { id: 's3', label: 'Send to contacts', instruction: 'Reach out directly via message with the 1-page offer and invite their candid feedback.' }
  ],
  // 6-step complex move: Arif fixed-audit (Review -> Scope -> Price -> Rubric -> Proposal -> Kickoff)
  'arif:fixed-audit': [
    { id: 's1', label: 'Review past inquiries', instruction: 'Extract the specific audit questions asked by the 2 returning clients.' },
    { id: 's2', label: 'Define 4-hr scope', instruction: 'Boundary the deliverables to fit within a strict 4-hour evaluation session.' },
    { id: 's3', label: 'Set fixed rate', instruction: 'Establish fixed pricing that exceeds current hourly billing rate.' },
    { id: 's4', label: 'Prepare audit rubric', instruction: 'Structure the findings template and benchmark scoring sheet.' },
    { id: 's5', label: 'Send proposal', instruction: 'Deliver the scoped audit proposal to the 2 returning clients.' },
    { id: 's6', label: 'Schedule kickoff', instruction: 'Confirm the booking date and reserve the 4-hour calendar block.' }
  ],
  // 1-step move: Rina small-test (Concise action item)
  'rina:small-test': [
    { id: 's1', label: 'Interview 3 past buyers', instruction: 'Contact 3 buyers from last month to learn their primary trigger for purchasing.' }
  ],
  // 0-step simple move: Bayu quick-cash (Clean objective and facts without checklist)
  'bayu:quick-cash': [],
  'recorded:plan-0': [
    { id: 's1', label: 'Draft service offer', instruction: 'Write a one-page service offer from your 8 years of experience.' }
  ],
  'recorded:plan-1': [
    { id: 's1', label: 'Send offer', instruction: 'Send that offer to the 2 people who once asked.' }
  ],
  'recorded:plan-2': [
    { id: 's1', label: 'Ask acquaintances', instruction: 'Ask 3 acquaintances what they pay for marketing today.' }
  ]
}

function getMoveSteps(pathId, moveId) {
  /* Phase 7: a canonical MOVE owns its ACTION LIST. In LIVE the steps are that Move's own action rows,
     addressed by move_id + action_id (liveMoveStepsForPath); there is no day schedule and no plan step
     borrowed for an attribution. A Move with no id and no attributable row shows none — never a
     fabricated one. Prototype/demo keeps its catalog, keyed by path as before. */
  if (!IS_DEMO) return (typeof liveMoveStepsForPath === 'function') ? (liveMoveStepsForPath(pathId, moveId || null) || []) : [];
  if (STORE.qaMoveSteps !== undefined && STORE.qaMoveSteps !== null) {
    if (STORE.qaMoveSteps === 0) return [];
    if (STORE.qaMoveSteps === 1) {
      return [{ id: 's1', label: 'Action item', instruction: 'Review the 1-page offer draft and verify pricing consistency.' }];
    }
    if (STORE.qaMoveSteps === 3) {
      return [
        { id: 's1', label: 'Research contacts', instruction: 'Review the 2 past contacts who previously asked for brand or strategy advice.' },
        { id: 's2', label: 'Draft 1-page offer', instruction: 'Prepare a 1-page advisory summary outlining the 2-week scope and Rp7.5M price point.' },
        { id: 's3', label: 'Send to contacts', instruction: 'Reach out directly via message with the 1-page offer and invite their candid feedback.' }
      ];
    }
    if (STORE.qaMoveSteps === 6) {
      return [
        { id: 's1', label: 'Review past inquiries', instruction: 'Extract the specific audit questions asked by the 2 returning clients.' },
        { id: 's2', label: 'Define 4-hr scope', instruction: 'Boundary the deliverables to fit within a strict 4-hour evaluation session.' },
        { id: 's3', label: 'Set fixed rate', instruction: 'Establish fixed pricing that exceeds current hourly billing rate.' },
        { id: 's4', label: 'Prepare audit rubric', instruction: 'Structure the findings template and benchmark scoring sheet.' },
        { id: 's5', label: 'Send proposal', instruction: 'Deliver the scoped audit proposal to the 2 returning clients.' },
        { id: 's6', label: 'Schedule kickoff', instruction: 'Confirm the booking date and reserve the 4-hour calendar block.' }
      ];
    }
  }

  const p = persona || v11MapKey();
  const key = `${p}:${pathId}`;
  if (MOVE_STEPS_CATALOG[key]) return MOVE_STEPS_CATALOG[key];

  const snap = V11_ENGINE.snapshot(p);
  const pathObj = snap.paths.find(x => x.id === pathId);
  if (pathObj && pathObj.next_move && Array.isArray(pathObj.next_move.steps)) {
    return pathObj.next_move.steps;
  }
  return [];
}

function isStepDone(pathId, moveId, stepIndex, step) {
  /* Phase 7: LIVE execution truth comes from the typed projection (MOVE_ACTION), never from
     prototype-local STORE.moveStepsDone. `step.__exec` is the MOVE_ACTION source ref resolved when
     the steps were built (move_id + action_id); without one the answer is honestly "not done". */
  if (!IS_DEMO) {
    const ref = (step && step.__exec) || null;
    return !!(ref && typeof liveExecutionDone === 'function' && liveExecutionDone(ref));
  }
  const p = v11MapKey();
  const key = `${p}:${pathId}`;
  return !!(STORE.moveStepsDone && STORE.moveStepsDone[key] && STORE.moveStepsDone[key][stepIndex]);
}
/* The canonical Move a path is on now, for panels that name its actions. It reads the rows the read
   model already attached to the path (canonical_moves); never a title, index or array position. Null
   when the snapshot carries no canonical rows (the demo catalog path). */
function v12PathMoveNow(p) {
  const rows = (p && Array.isArray(p.canonical_moves)) ? p.canonical_moves : [];
  return rows.length ? (rows.find(m => m.status === 'current') || rows[rows.length - 1] || null) : null;
}
/* The one station a chosen path opens: the Move named by STORE.mapsMoveDetail when it belongs to this
   path's own sequence, else the current Move. Selection is identity, never a position. */
function v12SeqSelectedMove(pathId, seq) {
  const rows = Array.isArray(seq) ? seq : [];
  const detail = (STORE.mapsMoveDetail && String(STORE.mapsMoveDetail).startsWith(pathId + ':'))
    ? String(STORE.mapsMoveDetail).slice(pathId.length + 1) : null;
  return (detail && rows.find(m => String(m.id) === detail)) || rows.find(m => m.status === 'current') || null;
}

const STATE_ICON = {
  check: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.3 2.4c-.6.3-.9.8-.9 1.4v.6"/><path d="M12 16.8h.01"/>',
  trend: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
  target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  bulb: '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
  rocket: '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  paths: '<circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v4"/><path d="M12 11l-5 6"/><path d="M12 11l5 6"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  ban: '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/>',
  book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  chart: '<path d="M3 3v18h18"/><path d="M8 17V9"/><path d="M13 17V5"/><path d="M18 17v-4"/>'
};
/* One requirement mark for the whole system: a small round badge with an outline glyph in the stIcon style.
   Shape and glyph carry the state together with colour: confirmed (check), partly shown (half disc), not known yet
   (question mark, dashed ring; never styled like absent), not in place (cross), does not apply (dash). */
const REQ_MARK = {
  PRESENT: ['met', '<path d="m6.4 10.4 2.4 2.4 4.8-5"/>'],
  PARTIAL: ['partial', '<circle cx="10" cy="10" r="4.2"/><path d="M10 5.8a4.2 4.2 0 0 1 0 8.4z" fill="currentColor" stroke="none"/>'],
  UNKNOWN: ['unknown', '<path d="M8.1 8.2a2 2 0 1 1 2.7 1.9c-.5.2-.8.6-.8 1.1v.4"/><path d="M10 13.9h.01"/>'],
  ABSENT: ['absent', '<path d="m7.2 7.2 5.6 5.6"/><path d="m12.8 7.2-5.6 5.6"/>'],
  NA: ['na', '<path d="M7 10h6"/>']
};
function reqMark(sat, size) {
  const m = REQ_MARK[sat] || REQ_MARK.UNKNOWN;
  return `<span class="rq-mark rq-${m[0]}${size === 'sm' ? ' rq-sm' : ''}" aria-hidden="true"><svg viewBox="3.5 3.5 13 13" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round" focusable="false">${m[1]}</svg></span>`;
}
function stIcon(name, cls) {
  return `<svg class="st-ico${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${STATE_ICON[name]}</svg>`;
}
function stateBadge(icon, solid) { return `<span class="st-badge${solid ? ' st-badge-solid' : ''}">${stIcon(icon)}</span>`; }
/* ═══ Maps destination (screen 17) ═══════════════════════════════════════════ */
const MAPS_STATUS_MEANING = {
  OPEN: { short: 'Supported enough to move.', long: 'The evidence supports moving on this path now.' },
  'TEST FIRST': { short: 'Worth testing before committing.', long: 'A real possibility, but test it in a small way before you commit to it.' },
  'NOT YET': { short: 'Needs more evidence.', long: 'This may make sense later. For now the evidence is not there yet.' },
  STOP: { short: 'Current evidence says don’t continue.', long: 'What you have learned so far does not support continuing this path.' }
};
const MAPS_WORDS = ['OPEN', 'TEST FIRST', 'NOT YET', 'STOP'];
const mapsKey = w => (STRAT_STATUS_FROM_DISPLAY[w] || 'NOT_YET').toLowerCase();
const mapsStateWord = p => p.status_display + (p.stop_source ? STOP_BY_WORD[p.stop_source === 'you' ? 'you' : 'numbers'] : '');
const mapsReduced = () => !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

/* The selected thing: a path id, 'start' (HERE), 'goal', or null. A map with exactly one path opens on that path. */
function mapsEffectiveSel(snap) {
  const id = (STORE.mapsSelBy || {})[v11MapKey()];
  if (id === 'start' || id === 'goal') return id;
  if (id && snap.paths.some(p => p.id === id)) return id;
  if (id && String(id).startsWith('req:') && v12SharedById(id, snap)) return id;
  return snap.paths.length === 1 ? snap.paths[0].id : null;
}
/* The path in focus: ONLY the path the current move is recorded against (snapshot.nextmove.path_id). When the
   move carries no path, or that path is stopped, nothing is in focus. Never "the first OPEN path": engine order
   and status words are not a relationship. Not a recommendation — any path can be opened. */
function mapsActive(snap) {
  const id = snap && snap.nextmove && snap.nextmove.path_id;
  const p = id ? (snap.paths || []).find(x => x.id === id) : null;
  return p && p.status_display !== 'STOP' ? p : null;
}

/* Requirement tally. The engine's four words stay four: PRESENT (confirmed) · PARTIAL (partly shown) · UNKNOWN (not
   known yet) · ABSENT (the record shows it is not in place). A requirement flagged applicable:false does not count
   toward any of them: not applicable is not unmet. With nothing applicable there is no denominator, so no ratio. */
const REQ_WORDS = { PRESENT: 'confirmed', PARTIAL: 'partly shown', UNKNOWN: 'not known yet', ABSENT: 'not in place' };
function reqTally(p) {
  const c = { PRESENT: 0, PARTIAL: 0, UNKNOWN: 0, ABSENT: 0, total: 0, na: 0 };
  (p.requirements || []).forEach(r => {
    if (r.applicable === false) { c.na++; return; }
    if (c[r.satisfaction] !== undefined) { c[r.satisfaction]++; c.total++; }
  });
  return c;
}
function reqSummary(p) {
  const c = reqTally(p);
  if (!c.total) return c.na ? 'No requirements apply to this path right now.' : 'No requirements are recorded for this path.';
  const parts = [`${c.PRESENT} of ${c.total} confirmed`];
  ['PARTIAL', 'UNKNOWN', 'ABSENT'].forEach(k => { if (c[k]) parts.push(`${c[k]} ${REQ_WORDS[k]}`); });
  return parts.join(' · ');
}

/* Why a path is on the map, in the person's own words when the record has them; otherwise what is known about it */
function mapsWhy(p, snap) {
  const ev = (snap.evidence || []).find(e => (p.evidence_ids || []).includes(e.id));
  if (ev) return { quote: ev.quote, source: ev.source, disputed: !!ev.disputed };
  const first = p.requirements.find(r => r.satisfaction === 'PRESENT');
  return { note: first ? `${first.label}.` : 'Noted from what you told us. Nothing is confirmed yet.', source: p.provenance };
}
/* What would open / move a path: a key and one line, taken from the engine's own requirements and next move */
function mapsOpens(p) {
  const absent = p.requirements.filter(r => r.satisfaction === 'ABSENT').map(r => r.label);
  const unsure = p.requirements.filter(r => r.satisfaction === 'UNKNOWN' || r.satisfaction === 'PARTIAL').map(r => r.label);
  const pick = (k, l, fallback) => ({ k, t: l.length ? l[0] : fallback, more: Math.max(l.length - 1, 0) });
  if (p.stop_source === 'you') return { k: 'IF YOU CHANGE YOUR MIND', t: 'You can go ahead anyway. It is recorded as your decision.', more: 0 };
  if (p.status_display === 'OPEN') return p.next_move ? { k: 'NEXT MOVE', t: p.next_move.title, more: 0 } : { k: 'STATUS', t: 'Ready to move on.', more: 0 };
  if (p.status_display === 'TEST FIRST') return pick('WHAT TO TEST', unsure.length ? unsure : absent, 'A small version first.');
  if (p.status_display === 'STOP') return pick('WOULD REOPEN IF', absent.length ? absent : unsure, 'The evidence changes.');
  return pick('WOULD OPEN WHEN', absent.length ? absent : unsure, 'The evidence is there.');
}

/* Plain counts of the snapshot, in the engine's words — never a score */
/* ── Maps: one workspace, three lenses (internal-docs) ──────────────────────────────
   LANDSCAPE   "Where can I go?"                                  the map, map-dominant — possibility space
   OVERVIEW    "Where can I go, and what does each path need?"    the same map + a concise readiness read
   READINESS   "What does each path need?"                        deep inspection of the same Path
   Not three destinations and not three models: every lens reads the same snapshot Path objects and the same
   selection (STORE.mapsSelBy[map] — read through selectedPathId()), so changing lens never loses the selection. */
const MAPS_VIEWS = ['landscape', 'readiness'];
const MAPS_VIEW_LABEL = { landscape: 'Explore', readiness: 'Readiness' };
function mapsViewNow() { return MAPS_VIEWS.includes(STORE.mapsView) ? STORE.mapsView : 'landscape'; }
/* The selected Path id, or null. HERE and GOAL can be selected on the map, but they are not Paths. */
function selectedPathId(snap) {
  const sn = snap || V11_ENGINE.snapshot();
  const id = mapsEffectiveSel(sn);
  return id && sn.paths.some(p => p.id === id) ? id : null;
}
/* The one write path for the shared selection. `isDefault` marks a presentation default that the person did not
   choose: it is stored (every lens then shows the same subject, IA int 08 / Maps composition int 07 §selection) and it
   stays disclosed until the person picks a path. */
function mapsSetSel(id, isDefault) {
  const key = v11MapKey();
  STORE.mapsSelBy[key] = id || null;
  STORE.mapsSelDefaultBy = STORE.mapsSelDefaultBy || {};
  STORE.mapsSelDefaultBy[key] = isDefault && id ? id : null;
}
/* True only while the stored selection is still the presentation default: the default id is compared with the
   stored id, so a later explicit choice (or a cleared selection) can never leave the disclosure behind. */
function mapsSelIsDefault(snap) {
  const key = v11MapKey();
  const id = (STORE.mapsSelBy || {})[key];
  return !!id && (STORE.mapsSelDefaultBy || {})[key] === id && selectedPathId(snap) === id;
}
/* Readiness on a map with no selection at all: the first path in engine order is stored as the default subject.
   HERE and goal are choices the person made on the map, so Readiness shows the first path WITHOUT overwriting them. */
function mapsSeedReadinessDefault(snap) {
  const key = v11MapKey();
  if (!snap.paths.length || (STORE.mapsSelBy || {})[key] != null) return;
  mapsSetSel(snap.paths[0].id, true);
}
/* Readiness always needs a subject when there is at least one path. With no Path selected (HERE, goal or nothing) it
   shows the first path in the snapshot's order as a disclosed presentation default, not a recommendation. */
function mapsReadinessSubject(snap) {
  if (!snap.paths.length) return { id: null, isDefault: false };
  const id = selectedPathId(snap);
  const shared = !id && v12SharedById((STORE.mapsSelBy || {})[v11MapKey()], snap);
  if (shared) return { id: shared.members[0], isDefault: true, fromShared: shared };
  return id ? { id, isDefault: mapsSelIsDefault(snap) } : { id: snap.paths[0].id, isDefault: true };
}
/* Disclosure for a presentation default wherever a stored default is the subject. Never shown for a choice. */
function mapsDefaultLine(snap) {
  if (!mapsSelIsDefault(snap) || snap.paths.length < 2) return '';
  const id = selectedPathId(snap);
  if (snap.paths[0].id !== id && (mapsActive(snap) || {}).id === id)
    return '<p class="mp-fine mp-default-note">Shown because it is in focus: your current move is recorded against it. Not a recommendation. Pick another path to choose one.</p>';
  return '<p class="mp-fine mp-default-note">Shown first by default: the first path in the list, not a recommendation and not your choice. Pick a path to choose one.</p>';
}

function renderMapsViewSwitch() {
  const cur = mapsViewNow();
  const Q = { landscape: 'Where can I go, and what should I know about each path?', readiness: 'What does each path need?' };
  const btn = v => `<button type="button" class="${cur === v ? 'active' : ''}" aria-pressed="${cur === v}" onclick="setMapsView('${v}')">${cur === v ? '<span class="v11-lens-pill" aria-hidden="true"></span>' : ''}<span class="v11-lens-name" data-label="${MAPS_VIEW_LABEL[v]}">${MAPS_VIEW_LABEL[v]}</span><span class="v11-lens-q">${Q[v]}</span></button>`;
  return `<div class="v11-view-switch" role="group" aria-label="Maps views: three lenses on the same paths">${MAPS_VIEWS.map(btn).join('')}</div><p class="v11-lens-caption"><strong>${MAPS_VIEW_LABEL[cur]}:</strong> ${Q[cur]}</p>`;
}
/* Maps' local control row: the lens switch first, then a quiet plain-language count */
function renderMapsLocalBar(caption, extra) {
  return `<div class="v11-localbar">${renderMapsViewSwitch()}${caption ? `<span class="mp-summary">${caption}</span>` : ''}${extra || ''}</div>`;
}
/* Lens change: same workspace, different depth. The language is the destination transition's (the white pill glides,
   the page eases in) at lower intensity — the map keeps its identity and nothing slides in from the side. Reduced
   motion and browsers without View Transitions get the plain swap. The selection is untouched. */
function setMapsView(view) {
  if (view === 'overview') view = 'landscape';   // Overview was merged into Explore; old links still land there
  if (!MAPS_VIEWS.includes(view) || view === mapsViewNow()) return;
  const from = mapsViewNow();
  if (from !== 'readiness') STORE.mapsLens = from;
  const a = document.activeElement;
  if (a && a.closest && a.closest('.v11-view-switch')) STORE.restoreFocus = '.v11-view-switch .active';
  const old = document.querySelector('.v11-lens-pill');
  const oldBox = old ? old.getBoundingClientRect() : null;
  STORE.mapsView = view;
  renderScreen('maps');
  const now = document.querySelector('.v11-lens-pill');
  if (oldBox && now && now.animate) {
    const box = now.getBoundingClientRect();
    if (Math.abs(oldBox.left - box.left) >= 1) now.animate([{ transform: `translateX(${oldBox.left - box.left}px)`, width: oldBox.width + 'px' }, { transform: 'translateX(0)', width: box.width + 'px' }],
      { duration: 260, easing: 'cubic-bezier(0.22, 0.8, 0.3, 1)' });
  }
  const stage = document.getElementById('mpw-stage');
  if (stage && stage.animate && !mapsReduced()) stage.animate([{ opacity: 0, transform: 'translateY(4px)' }, { opacity: 1, transform: 'none' }], { duration: 150, easing: 'ease-out' });
}

/* ── Path card: orientation, not detail. Landscape: what is it, why is it here, how does it stand. Overview adds what
   would open it and a plain count of what is confirmed. The whole card is the button. ── */
function mapsCard(p, snap, sel, act) {
  const lens = mapsViewNow();
  const w = mapsWhy(p, snap), o = mapsOpens(p);
  const foot = p.group ? stratEsc(p.group) : '';
  return `<li><button type="button" class="mp-card" data-path="${p.id}" aria-pressed="${sel === p.id}" onclick="mapsSelect('${p.id}',{scroll:true})">
    <span class="mp-card-top"><span class="mp-state ${mapsKey(p.status_display)}">${stratEsc(mapsStateWord(p))}</span>${act && act.id === p.id ? '<span class="mp-tag">In focus</span>' : ''}</span>
    <span class="mp-card-title">${stratEsc(p.title)}</span>
    ${o ? `<span class="mp-card-line"><span class="mp-k">WHAT COMES NEXT</span>${stratEsc(o.t)}${o.more ? ` <span class="mp-plus">+${o.more} more</span>` : ''}</span>` : ''}
    ${foot ? `<span class="mp-card-group">${foot}</span>` : ''}
  </button></li>`;
}
/* Overview's list: only the paths the map does not draw. Selecting one brings it onto the map. */
function mapsMoreHtml(snap, pres, sel, moreOpen) {
  const act = mapsActive(snap);
  const hidden = pres.hidden;
  const hiddenParts = MAPS_WORDS.map(w => [w, hidden.filter(p => p.status_display === w).length]).filter(x => x[1]).map(([w, c]) => `${c} ${w.toLowerCase()}`).join(' · ');
  return `
  <details class="mp-more" id="mp-more"${moreOpen ? ' open' : ''}>
    <summary><span class="mp-more-n">+${hidden.length} more possibilit${hidden.length === 1 ? 'y' : 'ies'}</span><span class="mp-more-sub">${hiddenParts}</span></summary>
    <div>
      <p class="mp-note">The map draws up to ${pres.cap} paths at a time. That is a limit of this screen, not of how many possibilities exist. Select one to bring it onto the map.</p>
      <ul class="mp-cards">${hidden.map(p => mapsCard(p, snap, sel, act)).join('')}</ul>
    </div>
  </details>`;
}

/* ── Panel: the selected path (or HERE / goal), or a short orientation when nothing is selected ── */
const mapsLegendHtml = () => MAPS_WORDS.map(k => `<li><span class="mp-state ${mapsKey(k)}">${k}</span><span>${MAPS_STATUS_MEANING[k].short}</span></li>`).join('');
/* Landscape's orientation: fixed. It reads the same whatever is selected — selecting a path never swaps it for path detail. */
/* Overview's rail with nothing selected: what the panel is for, never a pick made for you */
function mapsOverviewEmpty(snap) {
  return `
    <div class="section-meta-label">EXPLORE YOUR PATHS</div>
    <p class="mp-p">Select a path to understand why it is here, what supports it, and what remains uncertain.</p>`;
}
/* Landscape's selection: one quiet bar under the map — identity and a way forward, no requirements, no evidence */
/* A shared requirement in the inspector. Everything here is read from the paths that hold it; nothing is explained,
   credited or authorised by the frontend. A move is offered only when the engine's own next step names this
   requirement (recorded goals: question.focus); otherwise the panel says the record ties no move to it. */
function mapsSharedReqPanel(s, snap) {
  if (s.reqs && s.reqs.length > 1) return mapsSharedGroupPanel(s, snap);
  const st = V12_REQ_NODE[s.satisfaction] || 'unknown';
  const STATE_LINE = { met: 'Confirmed by the evidence on record.', partial: 'Partly shown so far.', unknown: 'Nothing on record settles this yet.', absent: 'The record shows it is not in place.' };
  const members = s.members.map(id => snap.paths.find(p => p.id === id)).filter(Boolean);
  const guidance = (s.refs.map(r => r.req.guidance).find(Boolean)) || '';
  const reasons = s.refs.filter(r => r.req.reason).map(r => ({ p: snap.paths.find(x => x.id === r.pathId), reason: r.req.reason })).filter(x => x.p);
  const conflict = s.refs.some(r => r.req.conflict);
  const rec = null;   /* MVP has no recorded-goal fixtures (prototype QA personas) */
  const focus = rec && rec.question && rec.question.focus;
  const tied = !!(focus && focus.type === 'requirement' && (s.reqs || [s]).some(r => r.id === focus.id) && snap.nextmove);
  const nmPath = snap.nextmove && snap.nextmove.path_id && s.members.includes(snap.nextmove.path_id) ? snap.paths.find(p => p.id === snap.nextmove.path_id) : null;
  const action = tied
    ? `<p class="mp-p">The engine’s next step is about this requirement: <b>${stratEsc(snap.nextmove.title)}</b></p>
       <div class="mp-actions"><button type="button" class="btn-primary btn-sm" onclick="goDestination('moves')">Open in Moves →</button></div>`
    : `<p class="mp-fine">No move is tied to this requirement in the record, so there is nothing here to start.${nmPath ? ` Your current move is recorded on <b>${stratEsc(nmPath.title)}</b>, which lists it; the record does not link that move to this requirement, so finishing it is not counted here.` : ''}</p>`;
  /* Requirement ≠ RouteNode ≠ Move. The prototype records membership only (no route_id, node_id or depends_on), so the
     panel says what the record supports: listed by these paths, not a gate in front of them. */
  const openHolders = st !== 'met' ? members.filter(p => p.status_display === 'OPEN') : [];
  return `
    <div class="mp-top"><span class="section-meta-label">SHARED REQUIREMENT</span></div>
    <h2 class="serif-heading mp-title" id="mp-title" tabindex="-1">${stratEsc(s.label)}</h2>
    <p class="mp-lede">${reqMark(s.satisfaction)} <span>${stratEsc(V12_STATE_WORD[st])}. ${stratEsc(STATE_LINE[st])}</span></p>
    ${conflict ? '<p class="mp-fine">The evidence on record conflicts on this requirement.</p>' : ''}
    ${st !== 'met' && guidance ? `<p class="mp-p"><span class="mp-fine">To check it:</span> ${stratEsc(guidance)}</p>` : ''}
    <section class="mp-members" aria-label="What it is">
      <div class="section-meta-label">CONDITION, NOT A GATE</div>
      <p class="mp-p">Each path below lists it as one of the things it needs. The record does not say it must be met before any step can start, or before a path can be chosen, so the map draws it where their lines run together, not as a step to pass first.</p>
      ${openHolders.length ? `<p class="mp-fine">${openHolders.map(p => `<b>${stratEsc(p.title)}</b>`).join(', ')} ${openHolders.length === 1 ? 'is' : 'are'} OPEN while this is ${stratEsc(V12_STATE_WORD[st].toLowerCase())}: OPEN says the evidence supports moving on the path, not that every condition is met yet.</p>` : ''}
    </section>
    <section class="mp-members" aria-label="Paths that list it">
      <div class="section-meta-label">LISTED BY ${members.length} PATHS</div>
      <ul>${members.map(p => `<li><button type="button" class="mp-member" onclick="mapsSelect('${p.id}')"><span class="mp-member-title">${stratEsc(p.title)}</span><span class="mp-state ${mapsKey(p.status_display)}">${p.status_display}</span></button></li>`).join('')}</ul>
      <p class="mp-fine">Each path keeps its own status. Shown once because every path lists it in the same words and the same state.</p>
    </section>
    <section class="mp-members" aria-label="Still uncertain">
      <div class="section-meta-label">STILL UNCERTAIN</div>
      <p class="mp-fine">Whether one thing would meet it for all ${members.length} paths. They use the same words; the record does not say it is one piece of work.</p>
    </section>
    ${reasons.length ? `<section class="mp-members" aria-label="Why it matters"><div class="section-meta-label">WHY IT MATTERS</div><ul class="mp-reasons">${reasons.map(x => `<li><b>${stratEsc(x.p.title)}:</b> ${stratEsc(x.reason)}</li>`).join('')}</ul></section>` : ''}
    <section class="mp-next-sec" aria-label="Action">${action}
      <p class="mp-fine">Marking a move done records that you did it. Whether this requirement is met is decided from evidence, for every path that holds it.</p>
    </section>`;
}
/* Several requirements held by the same paths: one node on the map, each requirement listed with its own state */
function mapsSharedGroupPanel(s, snap) {
  const members = s.members.map(id => snap.paths.find(p => p.id === id)).filter(Boolean);
  const rec = null;   /* MVP has no recorded-goal fixtures (prototype QA personas) */
  const focus = rec && rec.question && rec.question.focus;
  const tiedReq = focus && focus.type === 'requirement' && snap.nextmove ? s.reqs.find(r => r.id === focus.id) : null;
  return `
    <div class="mp-top"><span class="section-meta-label">SHARED REQUIREMENTS · ${s.reqs.length}</span></div>
    <h2 class="serif-heading mp-title" id="mp-title" tabindex="-1">What these ${members.length} paths both need</h2>
    <ul class="mp-req-list">${s.reqs.map(r => {
      const st = V12_REQ_NODE[r.satisfaction] || 'unknown';
      const guidance = r.refs.map(x => x.req.guidance).find(Boolean);
      return `<li>${reqMark(r.satisfaction)}<div><b>${stratEsc(r.label)}</b> <span class="mp-mark-word">${V12_STATE_WORD[st]}</span>${st !== 'met' && guidance ? `<p class="mp-fine">To check it: ${stratEsc(guidance)}</p>` : ''}</div></li>`;
    }).join('')}</ul>
    <section class="mp-members" aria-label="Paths that hold them">
      <div class="section-meta-label">HELD BY ${members.length} PATHS</div>
      <ul>${members.map(p => `<li><button type="button" class="mp-member" onclick="mapsSelect('${p.id}')"><span class="mp-member-title">${stratEsc(p.title)}</span><span class="mp-state ${mapsKey(p.status_display)}">${p.status_display}</span></button></li>`).join('')}</ul>
      <p class="mp-fine">Conditions these paths list, not a gate in front of them: the record does not say any must be met first. Drawn as one node because the same paths hold each of them. They stay separate requirements, each with its own state.</p>
    </section>
    <section class="mp-next-sec" aria-label="Action">${tiedReq
      ? `<p class="mp-p">The engine’s next step is about <b>${stratEsc(tiedReq.label)}</b>: ${stratEsc(snap.nextmove.title)}</p><div class="mp-actions"><button type="button" class="btn-primary btn-sm" onclick="goDestination('moves')">Open in Moves →</button></div>`
      : '<p class="mp-fine">No move is tied to these requirements in the record.</p>'}
      <p class="mp-fine">Marking a move done records that you did it. Whether a requirement is met is decided from evidence, for every path that holds it.</p>
    </section>`;
}
function mapsHerePanel(snap) {
  const now = snap.goal.now && snap.goal.now !== 'Not set yet' ? `${snap.goal.now} a month today.` : 'Nothing is measured yet.';
  return `
    <div class="mp-top"><span class="section-meta-label">YOUR CURRENT STATE</span></div>
    <h2 class="serif-heading mp-title">Where you are right now</h2>
    <p class="mp-p">${stratEsc(now)} ${stratEsc(provText('Every path on this map starts from what your Talk and your check-ins actually showed.'))}</p>
    <div class="mp-actions"><button type="button" class="btn-secondary btn-sm" onclick="goDestination('state')">See where you are →</button></div>`;
}
function mapsGoalPanel(snap) {
  return `
    <div class="mp-top"><span class="section-meta-label">YOUR GOAL</span></div>
    <h2 class="serif-heading mp-title">${stratEsc(snap.goal.text)}</h2>
    <p class="mp-p">Paths earn their place on the map by what the evidence supports, never by a score. How ready each one is lives in Readiness.</p>
    <div class="mp-actions"><button type="button" class="btn-secondary btn-sm" onclick="goDestination('moves')">See what moves you toward it →</button></div>`;
}
function mapsPathPanel(p, snap) {
  const meaning = MAPS_STATUS_MEANING[p.status_display] || MAPS_STATUS_MEANING['NOT YET'];
  const act = mapsActive(snap);
  const isRec = false;   /* MVP has no recorded-goal fixtures */
  const isAct = !isRec && !!act && act.id === p.id;
  const stopYou = p.stop_source === 'you';
  const live = p.requirements.filter(r => r.applicable !== false);
  const supports = live.filter(r => r.satisfaction === 'PRESENT');
  const open = live.filter(r => r.satisfaction === 'ABSENT').concat(live.filter(r => r.satisfaction === 'UNKNOWN' || r.satisfaction === 'PARTIAL'));
  const lede = stopYou ? 'You paused this path. It stays on your map with everything you learned on it.' : meaning.long;
  /* What matters now: at most one condition that holds and one that does not yet. Each keeps its own state word
     (Confirmed, Partly shown, Not known yet, Not in place), so unknown never reads as absent. Nothing is added to fill. */
  const MARK = { PRESENT: ['✓', 'Confirmed', 'met'], PARTIAL: ['◐', 'Partly shown', 'partial'], UNKNOWN: ['?', 'Not known yet', 'unknown'], ABSENT: ['✕', 'Not in place', 'absent'] };
  const shortlist = [supports[0], open[0]].filter(Boolean);
  const matter = shortlist.length ? `<section class="mp-matters" aria-label="What matters now"><div class="mp-matters-h">What matters now</div><ul>${shortlist.map(r => { const m = MARK[r.satisfaction] || MARK.UNKNOWN; return `<li>${reqMark(r.satisfaction)}<span>${stratEsc(r.label)} <span class="mp-mark-word">${m[1]}</span></span></li>`; }).join('')}</ul>${live.length > shortlist.length ? `<p class="mp-fine">${live.length - shortlist.length} more in Readiness</p>` : ''}</section>` : '';
  /* The move is offered first only when the record ties one to this path: it is the path in focus (nextmove.path_id,
     never STOP) and it has a next move. Otherwise Readiness leads, and no move is invented. */
  const hasMove = !stopYou && isAct && !!p.next_move;
  /* Phase 7: the actions are the CURRENT canonical Move's own list. The move id comes from the read
     model's rows, never from the legacy next_move object or a position. */
  const nowMove = v12PathMoveNow(p);
  const nowMoveId = nowMove ? nowMove.id : null;
  const steps = hasMove ? getMoveSteps(p.id, nowMoveId) : [];
  let stepsPreview = '';
  if (steps && steps.length > 1) {
    stepsPreview = `
      <section class="mp-steps-preview" aria-label="Step sequence for supported move">
        <div class="section-meta-label mp-seq-h">ACTIONS IN THIS MOVE · ${steps.length}</div>
        <p class="mp-fine">Move: ${stratEsc(nowMove ? (nowMove.objective || nowMove.title) : p.next_move.title)}</p>
        ${nowMove ? `<p class="mp-fine">${stratEsc(nowMove.lifecycle)} · ${nowMove.actionsDone} of ${nowMove.actionsTotal} actions completed</p>` : ''}
        ${mapsMoveSeq(p.id, nowMoveId, steps)}
      </section>`;
  } else if (steps && steps.length === 1) {
    stepsPreview = `
      <section class="mp-steps-preview" aria-label="Action item for supported move">
        <div class="section-meta-label mp-seq-h">ACTION ITEM</div>
        <p class="mp-single-step-text"><b>${stratEsc(steps[0].label)}:</b> ${stratEsc(steps[0].instruction)}</p>
      </section>`;
  }
  /* Where its line starts on the map, from the projection only (shared membership), never from its status */
  const chain = (v12ProjectionNow(snap).chains || {})[p.id];
  const proj = chain ? v12ProjectionNow(snap) : null;
  const firstShared = chain && chain.length ? proj.byKey.get(chain[0]) : null;
  const onMap = !chain ? ''
    : firstShared ? `It shares a condition with ${firstShared.members.length - 1} other path${firstShared.members.length === 2 ? '' : 's'}: “${stratEsc(firstShared.reqs.length > 1 ? `${firstShared.reqs.length} shared requirements` : firstShared.label)}”. Shared is not a step they pass together, and meeting it is decided by evidence.`
    : 'It shares no condition with the other paths on the map.';
  const notYet = live.length - supports.length;
  const openNote = p.status_display === 'OPEN' && notYet ? ` OPEN is about the path as a whole; ${notYet} of its ${live.length} conditions ${notYet === 1 ? 'is' : 'are'} not confirmed yet.` : '';
  const mapNote = onMap || openNote ? `<p class="mp-fine mp-onmap">${onMap}${openNote}</p>` : '';
  /* Route relations, only when the data carries them (the illustration map): where it branches, where it merges, its moves */
  const moveOf = (pid, mid) => { const q = snap.paths.find(x => x.id === pid); const m = q && (q.moves || []).find(x => x.id === mid); return q && m ? { q, m } : null; };
  const bf = p.branches_from && p.branches_from !== 'start' ? moveOf(p.branches_from.path_id, p.branches_from.move_id) : null;
  const mi = p.merges_into ? moveOf(p.merges_into.path_id, p.merges_into.move_id) : null;
  const routeRel = Array.isArray(p.moves) || p.branches_from ? `
    <section class="mp-members mp-route-rel" aria-label="On this route">
      <div class="section-meta-label">ON THIS ROUTE · EXAMPLE DATA</div>
      <p class="mp-fine">${bf ? `Branches from <b>${stratEsc(bf.q.title)}</b>, after “${stratEsc(bf.m.title)}”.${p.branches_from.when ? ` Opens: ${stratEsc(p.branches_from.when)}.` : ''}` : 'Starts from your current state.'}${mi ? ` Feeds into “${stratEsc(mi.m.title)}” on <b>${stratEsc(mi.q.title)}</b>.` : ''}</p>
      ${(p.moves || []).length ? (() => { const fo = p.moves.findIndex(q => q.status !== 'done'); return `<ol class="mp-route-moves">${p.moves.map((m, i) => `<li class="${m.status === 'done' ? 'is-done' : m.status === 'current' && isAct ? 'is-current' : i > fo ? 'is-locked' : ''}"><span class="mp-rm-n">${m.status === 'done' ? '✓' : i + 1}</span><span>${stratEsc(m.title)}${m.status === 'current' && isAct ? ' · current move' : m.status === 'done' ? ' · done' : i > fo ? ' · locked until the move before it is done' : ''}</span></li>`).join('')}</ol>`; })() : ''}
      <p class="mp-fine">Written in this example’s data. A branch or merge is never inferred from names or order.</p>
    </section>` : '';
  const links = [
    stopYou ? `<button type="button" class="mp-link" onclick="resumeStoppedPath('${p.id}')">Go ahead anyway</button>` : '',
    p.status_display === 'STOP' && !stopYou ? `<button type="button" class="mp-link" onclick="openStopModal('${p.id}')" aria-haspopup="dialog">Why is this stopped? →</button>` : '',
    `<button type="button" class="mp-link" onclick="openTalkAbout('${p.id}')">Talk about this →</button>`
  ].filter(Boolean).join('');
  return `
    <div class="mp-top"><span class="section-meta-label">PATH${p.group ? ` · ${stratEsc(p.group)}` : ''}</span></div>
    <h2 class="serif-heading mp-title" id="mp-title" tabindex="-1">${stratEsc(p.title)}</h2>
    <p class="mp-lede">${stratEsc(lede)}</p>
    ${matter}
    ${mapNote}
    ${routeRel}
    ${stepsPreview}
    <div class="mp-actions">${hasMove
      ? `<button type="button" class="btn-primary btn-sm" onclick="goDestination('moves')">See your move →</button><button type="button" class="btn-secondary btn-sm" onclick="openReadiness('${p.id}')">Explore readiness →</button>`
      : `<button type="button" class="btn-primary btn-sm" onclick="openReadiness('${p.id}')">Explore readiness →</button>`}</div>
    <div class="mp-links">${links}</div>`;
}
function mapsPanelHtml(snap, sel, preview) {
  if (sel === 'start') return mapsHerePanel(snap);
  if (sel === 'goal') return mapsGoalPanel(snap);
  const shared = v12SharedById(sel, snap);
  if (shared) return mapsSharedReqPanel(shared, snap);
  const p = sel && snap.paths.find(x => x.id === sel);
  if (!p) return mapsOverviewEmpty(snap);
  const detailId = (STORE.mapsMoveDetail && mapsViewNow() !== 'readiness' && String(STORE.mapsMoveDetail).startsWith(p.id + ':'))
    ? String(STORE.mapsMoveDetail).slice(p.id.length + 1) : null;
  if (detailId) {
    /* LIVE: a Move's detail is read from the canonical rows by move_id. Never from a stale title or an
       index: when the id is not on record, the panel says so instead of drawing something in its place. */
    const canonical = (!IS_DEMO && typeof liveMoveById === 'function') ? liveMoveById(detailId) : null;
    if (canonical) return mapsMoveDetailPanel(p, canonical, snap);
    const legacy = (p.moves || []).find(m => String(m.id) === detailId);
    if (legacy) return mapsMoveDetailPanel(p, legacy, snap);
    if (!IS_DEMO) return mapsMoveMissingPanel(p);
  }
  return mapsViewNow() === 'readiness' ? mapsReadinessPanel(p, snap) : mapsPathPanel(p, snap);
}
/* The selected Move is not among the canonical rows any more (a reload, or a stale selection): say so. */
function mapsMoveMissingPanel(p) {
  return `
    <div class="mp-top"><span class="section-meta-label">MOVE · ${stratEsc(p.title.toUpperCase())}</span></div>
    <h2 class="serif-heading mp-title" id="mp-title" tabindex="-1">That move is not on record</h2>
    <p class="mp-lede">The move this panel was opened for is not among the moves the record holds for this path now. Nothing is shown in its place.</p>
    <div class="mp-links"><button type="button" class="mp-link" onclick="mapsSelect('${p.id}')">← Back to the path</button></div>`;
}
/* Phase 7: a canonical Move's detail. Everything is read from the Move's own row: its objective, its
   lifecycle, the counts the server keeps, and its OWN action list with each action's status. A Move has
   no day schedule, so no day is shown; its result is the MOVE's, never an arbitrary action's. */
function mapsCanonicalMoveDetail(p, mv, mc, snap) {
  const row = (Array.isArray(p.canonical_moves) ? p.canonical_moves : []).find(x => String(x.id) === String(mc.moveId)) || null;
  const life = mc.lifecycle;
  const counts = mc.total ? `${mc.done} of ${mc.total} actions completed` : 'No actions are recorded for this move yet';
  const req = (mc.required && mc.required !== mc.total) ? ` · ${mc.requiredOpen} of ${mc.required} required still open` : '';
  const note = (mv.outcome_report && mv.outcome_report.note) ? String(mv.outcome_report.note) : '';
  const STATUS_WORD = { TODO: 'open', DONE: 'done', SKIPPED: 'skipped', BLOCKED: 'blocked' };
  const rows = mc.states.map((s, i) => `<li class="${s.done ? 'is-done' : ''}" data-v12-move="${stratEsc(mc.moveId)}" data-v12-action="${stratEsc(s.actionId)}" data-status="${stratEsc(s.status)}">
      <span class="mp-rm-n">${s.done ? '✓' : i + 1}</span><span><b>${stratEsc(s.title)}</b> <span class="mp-mark-word">${STATUS_WORD[s.status] || stratEsc(s.status)}${s.required ? '' : ' · optional'}</span>${s.note ? ` — ${stratEsc(s.note)}` : ''}</span></li>`).join('');
  return `
    <div class="mp-top"><span class="section-meta-label">MOVE · ${stratEsc(p.title.toUpperCase())}</span></div>
    <h2 class="serif-heading mp-title" id="mp-title" tabindex="-1">${stratEsc(mc.objective || (row && row.title) || 'Move')}</h2>
    <p class="mp-lede mp-move-state is-${row && row.status === 'done' ? 'done' : 'current'}">${stratEsc(life)}${row && row.status === 'current' ? ' · current move' : row && row.status === 'abandoned' ? ' · abandoned' : ''} · ${stratEsc(counts)}${req}</p>
    ${mc.states.length ? `<section class="mp-members" aria-label="Actions in this move"><div class="section-meta-label">ACTIONS IN THIS MOVE · ${mc.done} OF ${mc.total} COMPLETED</div>
      <ol class="mp-route-moves">${rows}</ol></section>`
      : '<p class="mp-fine">No actions are recorded for this move yet.</p>'}
    ${mc.hasOutcome ? `<section class="mp-members" aria-label="What happened"><div class="section-meta-label">WHAT HAPPENED</div>
      <p class="mp-p">${mc.outcome ? `<span class="mp-state ${mc.outcome === 'moved' ? 'open' : 'not_yet'}">${stratEsc(mapsOutcomeWord(mc.outcome))}</span> ` : ''}${note ? `“${stratEsc(note)}” ` : ''}Reported against this move, not against one action.</p></section>`
      : '<p class="mp-fine">No result is on record for this move yet. A result is reported against the move as a whole.</p>'}
    <p class="mp-fine">Its actions carry no day schedule: the order is the one the record declares, and only an explicit dependency restricts it.</p>
    <div class="mp-links"><button type="button" class="mp-link" onclick="mapsSelect('${p.id}')">← Back to the path</button></div>`;
}
/* Move detail (from the map). Only what is on record for the move: its actions, when it was marked done, the outcome
   and evidence logged with it, and what that evidence changed. Done is not "it worked": with no outcome it says so. */
function mapsMoveDetailPanel(p, m, snap) {
  const raw = (m && (m.move_id ? m : (m.record && m.record.move_id ? m.record : null))) || null;
  const mc = (raw && typeof liveMoveContextSummary === 'function') ? liveMoveContextSummary(raw) : null;
  if (mc && mc.moveId) return mapsCanonicalMoveDetail(p, raw, mc, snap);
  const ms = p.moves || [], i = ms.indexOf(m), fo = ms.findIndex(q => q.status !== 'done');
  const inFocus = snap.nextmove && snap.nextmove.path_id === p.id;
  const state = m.status === 'done' ? 'done' : i > fo ? 'locked' : m.status === 'current' && inFocus ? 'current' : 'open';
  const rec = m.record || null;
  const moveId = m && m.id != null ? String(m.id) : null;
  const acts = state === 'current' ? (getMoveSteps(p.id, moveId) || []).map((st, k) => ({ label: st.label, done: isStepDone(p.id, moveId, k, st) })) : (rec && rec.actions) || [];
  const W = { PRESENT: 'Confirmed', PARTIAL: 'Partly shown', UNKNOWN: 'Not known yet', ABSENT: 'Not in place' };
  const head = { done: 'Done', current: 'Current move · not done yet', locked: `Locked until “${stratEsc(ms[fo] ? ms[fo].title : '')}” is done`, open: 'Not started' }[state];
  const OUT = { worked: 'Worked', mixed: 'Mixed', none: 'No result' };
  return `
    <div class="mp-top"><span class="section-meta-label">MOVE ${i + 1} OF ${ms.length} · ${stratEsc(p.title.toUpperCase())}</span></div>
    <h2 class="serif-heading mp-title" id="mp-title" tabindex="-1">${stratEsc(m.title)}</h2>
    <p class="mp-lede mp-move-state is-${state}">${head}</p>
    ${acts.length ? `<section class="mp-members" aria-label="Actions in this move"><div class="section-meta-label">ACTIONS IN THIS MOVE · ${acts.filter(a => a.done).length} OF ${acts.length} CHECKED</div>
      <ol class="mp-route-moves">${acts.map((a, k) => `<li class="${a.done ? 'is-done' : ''}"><span class="mp-rm-n">${a.done ? '✓' : k + 1}</span><span>${stratEsc(a.label)}${a.done ? '' : ' · not checked'}</span></li>`).join('')}</ol></section>`
      : state === 'locked' ? '<p class="mp-fine">Its actions are named when it opens.</p>' : ''}
    ${state === 'done' ? `<section class="mp-members" aria-label="What happened"><div class="section-meta-label">WHAT HAPPENED</div>
      ${rec && rec.outcome ? `<p class="mp-p"><span class="mp-state ${rec.outcome.kind === 'worked' ? 'open' : 'not_yet'}">${OUT[rec.outcome.kind] || 'Recorded'}</span> ${stratEsc(rec.outcome.text)}</p>` : '<p class="mp-fine">No outcome recorded. Done means it was done, not that it worked.</p>'}
      ${rec && (rec.evidence || []).length ? rec.evidence.map(e => `<blockquote class="mp-quote">“${stratEsc(e.quote)}”<cite>${stratEsc(e.source)}</cite></blockquote>`).join('') : ''}
    </section>
    <section class="mp-members" aria-label="What it changed"><div class="section-meta-label">WHAT IT CHANGED</div>
      ${rec && (rec.changed || []).length ? `<ul class="mp-req-list">${rec.changed.map(c => `<li>${reqMark(c.to)}<div><b>${stratEsc(c.label)}</b> <span class="mp-mark-word">${W[c.from] || c.from} → ${W[c.to] || c.to}</span></div></li>`).join('')}</ul><p class="mp-fine">Changed by the evidence logged with it, not by marking it done.</p>` : '<p class="mp-fine">Nothing on record changed because of this move.</p>'}
    </section>` : ''}
    <p class="mp-fine">${snap.illustration ? 'Example data.' : ''}</p>
    <div class="mp-links"><button type="button" class="mp-link" onclick="mapsSelect('${p.id}')">← Back to the path</button></div>`;
}
/* Maps keeps a move's detail in its own panel, never a drawer. Each step folds open to its instruction; the move's
   supporting detail folds below it in the State/Moves accordion grammar. What it needs and the evidence stay in the
   Readiness centre, so they are not repeated here. */
function mapsMoveSeq(pathId, moveId, steps) {
  return `<ol class="mp-seq">${steps.map((st, i) => {
    const done = isStepDone(pathId, moveId, i, st);
    return `<li class="${done ? 'is-done' : ''}"><details class="mp-seq-item">
      <summary><span class="mp-seq-n">${done ? '✓' : i + 1}</span><span class="mp-seq-label">${stratEsc(st.label)}</span>${stIcon('chevron', 'st-chev')}</summary>
      ${st.instruction ? `<p class="mp-seq-text">${stratEsc(st.instruction)}</p>` : ''}
    </details></li>`;
  }).join('')}</ol>`;
}
function mapsMoveFolds(p, snap) {
  const featured = snap.nextmove && snap.nextmove.path_id === p.id;
  const title = featured && snap.nextmove.title ? snap.nextmove.title : p.next_move ? p.next_move.title : p.title;
  const why = p.next_move && p.next_move.why ? p.next_move.why : stateMoveWhy(snap, title);
  const st = snap.state || {};
  const acc = (key, icon, label, inner) => `
    <details class="st-acc" id="mp-acc-${key}">
      <summary>${stIcon(icon, 'st-acc-ico')}<span>${label}</span>${stIcon('chevron', 'st-chev')}</summary>
      <div class="st-acc-body">${inner}</div>
    </details>`;
  const folds = [
    why ? acc('why', 'bulb', 'Why this matters', `<p>${stratEsc(why)}</p>`) : '',
    acc('from', 'paths', 'Where it comes from', `<p>This move comes from the path <b>${stratEsc(p.title)}</b>. What it needs is in the Readiness list on the left.</p>`),
    featured && st.know_right_when ? acc('right', 'check', 'We’ll know we’re right when', `<p>${stratEsc(st.know_right_when)}</p>`) : ''
  ].filter(Boolean).join('');
  return `<div class="mv-acc-list mp-folds">${folds}</div>`;
}
/* Readiness lens: the centre already carries the path, its state and what it needs, so the panel carries only the move
   on this path and the ways onward. A move is shown only when the record ties one to this path; nothing is invented. */
function mapsReadinessPanel(p, snap) {
  const act = mapsActive(snap);
  const isRec = false;   /* MVP has no recorded-goal fixtures */
  const isAct = !isRec && !!act && act.id === p.id;
  const stopYou = p.stop_source === 'you';
  const hasMove = !stopYou && isAct && !!p.next_move;
  const nowMove = v12PathMoveNow(p);   /* Phase 7: the actions are the current canonical Move's own list */
  const nowMoveId = nowMove ? nowMove.id : null;
  const steps = hasMove ? (getMoveSteps(p.id, nowMoveId) || []) : [];
  const nm = snap.nextmove || {};
  const kind = nm.path_id === p.id ? (nm.type || 'ACTION') : ((p.next_move && p.next_move.type) || null);
  const meta = [kind ? MOVE_KIND_WORD[kind] || 'Ready' : '', nm.path_id === p.id && nm.minutes ? `About ${nm.minutes} min` : ''].filter(Boolean).join(' · ');
  const body = hasMove
    ? `${nm.title ? `<p class="mp-next-title">${stratEsc(nm.title)}</p>` : ''}
       ${meta ? `<p class="mp-next-meta">${stratEsc(meta)}</p>` : ''}
       ${steps.length ? `<div class="section-meta-label mp-seq-h">MOVE SEQUENCE · ${steps.length} ${steps.length === 1 ? 'STEP' : 'STEPS'}</div>
       ${mapsMoveSeq(p.id, nowMoveId, steps)}` : ''}
       ${mapsMoveFolds(p, snap)}`
    : p.status_display === 'STOP' || stopYou
      ? '<p class="mp-fine">No move: this path is stopped. Its readiness stays on record.</p>'
      : p.next_move
        ? `<p class="mp-fine">The record names this step for the path: “${stratEsc(p.next_move.title)}”. It is not your current move.</p>`
        : '<p class="mp-fine">No move is named for this path yet. What it needs comes first.</p>';
  const links = [
    `<button type="button" class="mp-link" onclick="openTalkAbout('${p.id}')">Talk about this →</button>`,
    (p.trail || []).length ? `<button type="button" class="mp-link" onclick="openPathTrailDrawer('${p.id}')">Everything on record →</button>` : '',
    p.status_display === 'STOP' && !stopYou ? `<button type="button" class="mp-link" onclick="openStopModal('${p.id}')" aria-haspopup="dialog">Why is this stopped? →</button>` : ''
  ].filter(Boolean).join('');
  return `
    <section class="mp-next-sec" aria-label="Next move on this path">
      <div class="mp-steps-head">
        <span class="section-meta-label">NEXT MOVE ON THIS PATH</span>
      </div>
      ${body}
    </section>
    <div class="mp-actions">
      ${hasMove ? `<button type="button" class="btn-primary btn-sm" onclick="goDestination('moves')">See your move →</button>` : ''}
      ${stopYou ? `<button type="button" class="btn-secondary btn-sm" onclick="resumeStoppedPath('${p.id}')">Go ahead anyway</button>` : ''}
    </div>
    <div class="mp-links">${links}</div>`;
}

/* ═══ v12 map adoption (Revenue Navigation v12): the Maps canvas draws the paths as
   routes over a timeline (2D). It reads the same
   engine snapshot and the same selection as the cards, list and panel. The shapes on
   it (lanes, branch days, step markers) are presentation-only, derived deterministically
   from each path's status and requirements — never new facts, never a ranking. ═══ */
const V12_ST = {
  'OPEN':       { line: '#059669', fg: '#047857' },
  'TEST FIRST': { line: '#2563eb', fg: '#1d4ed8' },
  'NOT YET':    { line: '#d97706', fg: '#b45309' },
  'STOP':       { line: '#dc2626', fg: '#dc2626' }
};
/* Node styles. A node is one thing the record says about a path: a requirement (in the engine's four words), the
   path's own next move, or a stop. Colour never carries it alone: each has its own icon and its own word. */
const V12_NS = {
  met:      { word: 'Confirmed', fill: '#ffffff', stroke: '#059669', icon: '#047857', dash: null, sw: 1.8 },
  partial:  { word: 'Partly shown', fill: '#ffffff', stroke: '#52525b', icon: '#3f3f46', dash: '4 2.5', sw: 1.6 },
  unknown:  { word: 'Not known yet', fill: '#ffffff', stroke: '#a1a1aa', icon: '#52525b', dash: '1.5 2.5', sw: 1.6 },
  absent:   { word: 'Not in place', fill: '#fafafa', stroke: '#71717a', icon: '#52525b', dash: null, sw: 1.6 },
  move:     { word: 'Next move', fill: '#18181b', stroke: '#18181b', icon: '#ffffff', dash: null, sw: 1.5 },
  stopped:  { word: 'Stopped', fill: '#fef2f2', stroke: '#dc2626', icon: '#dc2626', dash: null, sw: 1.5 }
};
/* Inline stroke icons (24×24): the node kinds carry their meaning by shape as well as colour, and nothing here
   depends on a remote icon font. */
const V12_ICONS = {
  met:     '<path d="m5 12.5 4.5 4.5L19 7"/>',
  partial: '<path d="M6 12h12"/>',
  unknown: '<path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.6-3 4.2"/><path d="M12 18h.01"/>',
  absent:  '<path d="m7 7 10 10M17 7 7 17"/>',
  move:    '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  stopped: '<path d="m7 7 10 10M17 7 7 17"/>'
};
const V12_REQ_NODE = { PRESENT: 'met', PARTIAL: 'partial', UNKNOWN: 'unknown', ABSENT: 'absent' };
/* Layout coordinate along a lane (0 = Here, 90 = goal). It spaces nodes in ORDER; it is not a date and no label
   on the map ever reads it as one. */
const V12_DAYU = d => (d <= 7 ? (0.36 * d) / 7 : d <= 14 ? 0.36 + (0.14 * (d - 7)) / 7 : 0.5 + 0.5 * Math.min(1, (d - 14) / 76));
const v12Short = (t, n) => { t = String(t || ''); return t.length > n ? t.slice(0, n - 1).trimEnd() + '…' : t; };

/* Snapshot → map shape. Every path leaves HERE on its own lane and reaches the goal (or ends crossed, when stopped).
   Lanes are spread evenly around the centre in the snapshot's own order: no status owns the middle, and nothing about
   position, length or size says "better". Nodes are the path's requirements, then its own next move; their spacing
   is order only. */
function v12Shape(snap) {
  const list = snap.paths.slice();
  const n = list.length;
  /* the same rule the Moves destination uses: a path whose move waits on what it still needs (movesCollect) */
  const waitBy = new Map(movesCollect(snap).waiting.map(w => [w.path.id, w.need]));
  const paths = list.map((p, i) => {
    const lane = i - (n - 1) / 2;
    const stopped = p.status_display === 'STOP';
    const items = stopped
      ? [{ state: 'stopped', type: 'stopped', label: p.stop_source === 'you' ? 'Stopped by you' : 'Stopped by evidence', title: p.stop_source === 'you' ? 'You chose to stop this path' : 'The evidence says not to continue this path' }]
      : p.requirements.map(r => ({ state: V12_REQ_NODE[r.satisfaction] || 'unknown', type: V12_REQ_NODE[r.satisfaction] || 'unknown', label: v12Short(r.label, 28), title: r.label }))
          .concat(p.next_move ? [{ state: 'move', type: 'move', label: 'Next move', title: p.next_move.title }] : []);
    const lo = 3, hi = stopped ? 4.4 : 74;
    const nodes = items.map((it, k) => Object.assign({ id: 'n' + (k + 1), day: stopped ? 2.6 : lo + ((k + 1) / (items.length + 1)) * (hi - lo) }, it));
    return { id: p.id, title: p.title, group: p.group, status: p.status_display, stop_source: p.stop_source,
      lane, branch: 0.4, end: stopped ? 4.4 : 90, endKind: stopped ? 'stop' : 'goal',
      ev: p.evidence_ids || [], reqs: p.requirements.filter(r => r.applicable !== false).map(r => [r.label, r.satisfaction, r.note || '']), nodes,
      hasMove: !!p.next_move, moveTitle: p.next_move ? p.next_move.title : '',
      waiting: waitBy.has(p.id), waitNeed: waitBy.get(p.id) || null,
      moves: Array.isArray(p.moves) ? p.moves : null, branches_from: p.branches_from || null, merges_into: p.merges_into || null,
      /* Phase 7: the path's canonical Moves, in the order the read model gives them. `moves` keeps its
         branching-illustration meaning untouched, so the live 2D composition is unchanged. */
      moveSeq: Array.isArray(p.canonical_moves) ? p.canonical_moves : null,
      requirements: (p.requirements || []).filter(r => r.applicable !== false) };
  });
  const horizon = snap.goal && snap.goal.horizon ? snap.goal.horizon : null;
  return { goal: snap.goal.text, now: snap.goal.now, horizon, paths,
    evidence: (snap.evidence || []).map(e => ({ id: e.id, source: e.source, quote: e.quote })) };
}

/* Map Zoom & Pan State */
const V12_ZOOM = {
  k: 1.0,
  panX: 0,
  panY: 0,
  minK: 0.6,
  maxK: 2.2,
  step: 1.25
};

/* The host is a named group, not a focus stop: keyboard users reach the map through its real controls (path lane labels, "+N more"), so the container itself takes no tab stop. */
function v12MapCanvasHtml() {
  return `<div class="v12-map" id="v12-map" role="group" aria-label="Map of your possible paths. The same paths are listed below."><div class="v12-stage"></div></div>
  <div class="v12-zoom-bar" id="v12-zoom-bar" role="group" aria-label="Map detail"></div>`;
}

function v12ApplyZoom() {
  const host = document.getElementById('v12-map');
  if (!host) return;
  const svg = host.querySelector('svg');
  if (!svg) return;
  const cw = host.clientWidth || 800;
  const ch = host.clientHeight || 460;
  const k = V12_ZOOM.k;
  /* a drawing that declares its own size (the branching view) is fitted to the canvas first; + and − scale from there */
  const fw = +svg.getAttribute('data-fit-w') || 0, fh = +svg.getAttribute('data-fit-h') || 0;
  if (fw && fh) {
    const s = Math.min(1.1, cw / fw, ch / fh);
    const vw = cw / (k * s), vh = ch / (k * s);
    svg.setAttribute('viewBox', `${((fw - vw) / 2 + V12_ZOOM.panX).toFixed(1)} ${((fh - vh) / 2 + V12_ZOOM.panY).toFixed(1)} ${vw.toFixed(1)} ${vh.toFixed(1)}`);
    const fitB = document.querySelector('[data-v12-zoom="fit"]');
    if (fitB) fitB.disabled = v12LevelNow() === 'Z0' && k === 1.0 && Math.abs(V12_ZOOM.panX) < 1 && Math.abs(V12_ZOOM.panY) < 1;
    return;
  }
  const vbW = cw / k;
  const vbH = ch / k;
  const vbX = ((cw - vbW) / 2) + V12_ZOOM.panX;
  const vbY = ((ch - vbH) / 2) + V12_ZOOM.panY;
  svg.setAttribute('viewBox', `${vbX.toFixed(1)} ${vbY.toFixed(1)} ${vbW.toFixed(1)} ${vbH.toFixed(1)}`);

  const fit = document.querySelector('[data-v12-zoom="fit"]');
  if (fit) fit.disabled = v12LevelNow() === 'Z0' && k === 1.0 && Math.abs(V12_ZOOM.panX) < 1 && Math.abs(V12_ZOOM.panY) < 1;
}

function v12InitPanZoom(host) {
  if (host._panZoomInited) return;
  host._panZoomInited = true;

  let isDragging = false;
  let startX = 0, startY = 0;
  let initPanX = 0, initPanY = 0;

  host.addEventListener('pointerdown', e => {
    if (e.target.closest('.v12-lane-label, .v12-step-node, .v12-station, .v12-stop-end, [data-v12-hit], button, a')) return;
    const svg0 = host.querySelector('svg');
    const wide = svg0 && +svg0.getAttribute('width') && (svg0.viewBox.baseVal.width < host.clientWidth - 1 || host.clientWidth < 560);
    if (V12_ZOOM.k <= 1 && !wide) return;          // nothing to pan: a click stays a click
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    initPanX = V12_ZOOM.panX;
    initPanY = V12_ZOOM.panY;
    host.style.cursor = 'grabbing';
    try { host.setPointerCapture(e.pointerId); } catch (_) {}
  });

  host.addEventListener('pointermove', e => {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    V12_ZOOM.panX = initPanX - (dx / V12_ZOOM.k);
    V12_ZOOM.panY = initPanY - (dy / V12_ZOOM.k);
    v12ApplyZoom();
  });

  const endDrag = e => {
    if (!isDragging) return;
    isDragging = false;
    host.style.cursor = '';
    try { host.releasePointerCapture(e.pointerId); } catch (_) {}
  };

  host.addEventListener('pointerup', endDrag);
  host.addEventListener('pointercancel', endDrag);

  /* ctrl/⌘ + wheel or a trackpad pinch scales the drawing; past a threshold (with hysteresis) the level changes.
     A plain wheel is never captured: the page keeps scrolling. */
  host.addEventListener('wheel', e => {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    V12_ZOOM.k = Math.max(V12_ZOOM.minK, Math.min(V12_ZOOM.maxK, +(V12_ZOOM.k * Math.exp(-e.deltaY * 0.01)).toFixed(3)));
    const lvl = v12LevelNow();
    if (V12_ZOOM.k >= 1.45 && lvl !== 'Z2') { v12ZoomIn(); return; }
    if (V12_ZOOM.k <= 0.72 && lvl !== 'Z0') { v12ZoomOut(); return; }
    v12ApplyZoom();
  }, { passive: false });
}

function v12Mount() {
  const host = document.getElementById('v12-map');
  if (!host) return;
  const cw = host.clientWidth, ch = host.clientHeight;
  if (!cw || !ch) { requestAnimationFrame(v12Mount); return; }
  const currentP = v11MapKey();
  if (host.dataset.persona !== currentP) {
    host.dataset.persona = currentP;
    V12_ZOOM.k = 1.0;
    V12_ZOOM.panX = 0;
    V12_ZOOM.panY = 0;
  }
  const snap = V11_ENGINE.snapshot();
  if (!snap.paths.length) return;
  v12RenderInto(host, snap);
  v12InitPanZoom(host);
}

function v12RenderInto(host, snap) {
  const cw = host.clientWidth, ch = host.clientHeight;
  const st = mapsFocusState(snap);
  /* The canvas draws at most PATH_VIEW_CAP paths (a presentation limit, never an engine limit). The shown path and the path
     in focus always take a slot; the rest wait in the list, and a visible control says how many. */
  const pres = presentSnapshotPaths(snap.paths, { pinned: [st.shown, st.active] });
  const shape = v12Shape(Object.assign({}, snap, { paths: pres.visible }));
  shape.proj = v12Project(pres.visible);
  shape.level = v12LevelNow(snap);
  /* A choice is drawn as selected. Nothing chosen: in Landscape the shown path steps forward and the rest step back, with no
     selection styling (no dark overlay, no pressed state). */
  /* A metro map needs room: below 720px it is laid out at 720 and the canvas shows its left part (Here and the route
     tags); drag or zoom out to see the rest. The list below the canvas carries every path at any width. */
  /* route relations on record (moves[], branches_from, merges_into) → the branching view; otherwise the path cards */
  const out = (shape.paths.some(p => p.moves) ? v12BuildFlow : v12Build2D)(shape, Math.max(cw, 720), ch, st.choice, st.active, cw);
  host.dataset.mode = '2d';
  const more = pres.hidden.length
    ? `<button type="button" class="v12-more" onclick="mapsOpenMore()">+${pres.hidden.length} more possibilit${pres.hidden.length === 1 ? 'y' : 'ies'} not drawn here. Open the list</button>` : '';
  host.innerHTML = `<div class="v12-stage">${out.svg}</div>${more}`;
  host.dataset.level = shape.level;
  const zb = document.getElementById('v12-zoom-bar');
  if (zb) zb.innerHTML = v12ZoomBarHtml(snap);
  v12LayoutLabels(host);
  v12ApplyZoom();
}

/* Places each lane's pills after its title, sized to their words. Measures the rendered text; falls back to an
   estimate when the canvas is not laid out yet. */
function v12LayoutLabels(host) {
  host.querySelectorAll('.v12-lane-label').forEach(g => {
    const title = g.querySelector('.v12-lt'), lp = g.querySelector('.v12-lp');
    if (!title || !lp) return;
    let x = 0;
    lp.querySelectorAll(':scope > .v12-pill, :scope > .v12-origin').forEach(el => {
      if (el.classList.contains('v12-pill')) {
        const tx = el.querySelector('text'), rect = el.querySelector('rect');
        let tw = 0; try { tw = tx.getComputedTextLength(); } catch (e) { tw = 0; }
        if (!tw) tw = tx.textContent.length * 6.2;
        rect.setAttribute('width', (tw + 14).toFixed(1));
        el.setAttribute('transform', `translate(${x.toFixed(1)} 0)`);
        x += tw + 14 + 5;
      } else {
        el.setAttribute('x', (x + 2).toFixed(1));
      }
    });
    const lx = +lp.dataset.x;
    lp.setAttribute('transform', `translate(${lx.toFixed(1)} ${(+lp.dataset.y).toFixed(1)})`);
  });
}

function v12Tap(id) { if (id) mapsSelect(id); }
/* choosing a move on the map: its path is chosen and the panel shows the move (what is on record for it) */
function v12OpenMove(pathId, moveId) { mapsSelect(pathId, { move: moveId }); }
function v12Key(ev, id) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); v12Tap(id); } }
const v12NowText = shape => (!shape.now || shape.now === 'Not set yet') ? 'Nothing measured yet' : shape.now + (/month/i.test(shape.now) ? '' : ' a month');
const v12GoalText = shape => (!shape.goal || shape.goal === 'Not set yet') ? 'Goal not set yet' : `Goal · ${shape.goal}`;
const v12StatusWord = p => p.status + (p.stop_source ? (p.stop_source === 'you' ? ' · by you' : ' · by the evidence') : '');

/* ── 2D: interconnected path map (2026-10). One navigational world drawn from the snapshot, never a second graph engine.
   v12Project is a thin, read-only, deterministic projection:
   · A requirement two or more paths hold is drawn ONCE as a shared node — only when its id, its wording and its state
     agree on every path (the engine's requirement satisfaction is global, so a different state means a different scope:
     those stay separate and are reported as a gap). Each path keeps its own reference (path id + its own requirement).
   · A path passes through the shared nodes it holds, the widest-shared first. That order is GROUPING, not a sequence or
     a dependency: no edge is read from array order, labels or proximity. The snapshot carries no depends_on, no route
     ids and no node ids, so no execution dependency, AND/OR gate or convergence milestone is drawn.
   · A path holding no shared requirement leaves HERE directly. A path without requirements or a move shows only itself.
   · A STOP path ends at its own terminus; others run on to the goal (solid when OPEN, dashed otherwise: reaching the goal
     is never implied). Path-specific requirements and move steps appear only for the chosen path (progressive
     disclosure). Spacing is order, never a date; position, length and colour never rank. ── */
const V12_METRO_ICON = {
  met: '<path d="m6.5 12.5 3.5 3.5 7.5-8"/>', partial: '<path d="M7 12h10"/>',
  unknown: '<path d="M9.6 9.4a2.6 2.6 0 0 1 5 .9c0 1.7-2.6 2.2-2.6 3.6"/><path d="M12 17.2h.01"/>',
  absent: '<path d="m8 8 8 8M16 8l-8 8"/>'
};
const V12_STATE_WORD = { met: 'Confirmed', partial: 'Partly shown', unknown: 'Not known yet', absent: 'Not in place' };
/* Stable key for a shared requirement: its id and its wording (fixture ids are not canonical on their own) */
function v12ReqKey(id, label) {
  const s = `${id}|${label}`;
  let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return 'req:' + String(id || 'r').replace(/[^A-Za-z0-9_.-]/g, '') + '-' + h.toString(36);
}
function v12Project(paths) {
  const groups = new Map();     // id|label → { refs: [{ pathId, req }] }
  (paths || []).forEach(p => (p.requirements || []).forEach(r => {
    if (!r || r.applicable === false) return;
    const k = `${r.id}|${r.label}`;
    if (!groups.has(k)) groups.set(k, { id: r.id, label: r.label, refs: [] });
    groups.get(k).refs.push({ pathId: p.id, req: r });
  }));
  const shared = [], gaps = [];
  groups.forEach(g => {
    const pathIds = [...new Set(g.refs.map(x => x.pathId))];
    if (pathIds.length < 2) return;
    const states = [...new Set(g.refs.map(x => x.req.satisfaction))];
    if (states.length > 1) { gaps.push({ kind: 'state-differs', id: g.id, label: g.label, paths: pathIds, states }); return; }
    shared.push({ key: v12ReqKey(g.id, g.label), id: g.id, label: g.label, satisfaction: states[0], members: pathIds, refs: g.refs });
  });
  /* Requirements held by exactly the same paths become one visual node (a group of references, not a merged entity) */
  const byMembers = new Map();
  shared.forEach(r => { const sig = r.members.slice().sort().join(','); if (!byMembers.has(sig)) byMembers.set(sig, []); byMembers.get(sig).push(r); });
  const hubs = [...byMembers.values()].map(reqs => {
    reqs.sort((a, b) => String(a.id).localeCompare(String(b.id)) || String(a.label).localeCompare(String(b.label)));
    const states = [...new Set(reqs.map(r => r.satisfaction))];
    return { key: reqs.length === 1 ? reqs[0].key : v12ReqKey(reqs.map(r => r.key).join(','), 'group'), reqs, id: reqs[0].id, label: reqs[0].label,
      satisfaction: states.length === 1 ? states[0] : null, members: reqs[0].members, refs: [].concat(...reqs.map(r => r.refs)) };
  });
  /* One global order (widest first, then id/label) makes every path's chain consistent, so the drawing is acyclic */
  hubs.sort((a, b) => b.members.length - a.members.length || String(a.id).localeCompare(String(b.id)) || String(a.label).localeCompare(String(b.label)));
  shared.length = 0; hubs.forEach(h => shared.push(h));
  const byKey = new Map(shared.map(s => [s.key, s]));
  const chains = {};
  (paths || []).forEach(p => { chains[p.id] = shared.filter(s => s.members.includes(p.id)).map(s => s.key); });
  /* Depth: the longest run of shared nodes before it on any chain that holds it */
  const depth = new Map(shared.map(s => [s.key, 1]));
  let changed = true, guard = 0;
  while (changed && guard++ < 64) {
    changed = false;
    Object.values(chains).forEach(c => c.forEach((k, i) => { if (i && depth.get(k) <= depth.get(c[i - 1])) { depth.set(k, depth.get(c[i - 1]) + 1); changed = true; } }));
  }
  shared.forEach(s => { s.depth = depth.get(s.key); });
  return { shared, requirements: hubs.reduce((a, h) => a.concat(h.reqs), []), byKey, chains, gaps, maxDepth: shared.length ? Math.max(...shared.map(s => s.depth)) : 0 };
}
/* Orthogonal route with small rounded corners (Git-like): runs are horizontal, a turn is one short vertical. */
function v12Ortho(pts, r) {
  const P = pts.filter((p, i) => i === 0 || Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 0.5);
  if (P.length < 2) return '';
  const f = v => (Math.round(v * 10) / 10).toFixed(1);
  let d = `M ${f(P[0][0])} ${f(P[0][1])}`;
  for (let i = 1; i < P.length - 1; i++) {
    const [ax, ay] = P[i - 1], [bx, by] = P[i], [cx, cy] = P[i + 1];
    const l1 = Math.hypot(bx - ax, by - ay), l2 = Math.hypot(cx - bx, cy - by), rr = Math.min(r, l1 / 2, l2 / 2);
    d += ` L ${f(bx - (bx - ax) / l1 * rr)} ${f(by - (by - ay) / l1 * rr)} Q ${f(bx)} ${f(by)} ${f(bx + (cx - bx) / l2 * rr)} ${f(by + (cy - by) / l2 * rr)}`;
  }
  const z = P[P.length - 1];
  return d + ` L ${f(z[0])} ${f(z[1])}`;
}
/* Soft Git branching (2026-10-17): the same orthogonal route (same points, same branch and end points), but every
   turn (horizontal run → vertical → horizontal run) is ONE cubic Bézier with horizontal tangents at both ends. Its
   width follows the rise (2×clamp(rise·0.8, 16, 84)) and never eats more than 85% of the runs on either
   side, so long runs stay straight and x never runs backwards. Returns the d string and the turn boxes (obstacles). */
function v12Soft(pts) {
  const P = pts.filter((p, i) => i === 0 || Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 0.5);
  const f = v => (Math.round(v * 10) / 10).toFixed(1);
  const boxes = [];
  if (P.length < 2) return { d: '', boxes };
  /* a run is flat within a bundle offset or two: a shared stretch changes its side-by-side offset at a node */
  const flat = (u, v) => u && v && Math.abs(u[1] - v[1]) < 9 && v[0] > u[0];
  const upright = (u, v) => u && v && Math.abs(u[0] - v[0]) < 0.5 && Math.abs(u[1] - v[1]) >= 0.5;
  let d = `M ${f(P[0][0])} ${f(P[0][1])}`, usedX = P[0][0], i = 1;
  while (i < P.length) {
    const b = P[i], n = P[i + 1], nn = P[i + 2];
    if (flat(P[i - 1], b) && upright(b, n) && flat(n, nn)) {
      /* a turn at x = b.x, from b.y to n.y. The run after it is shared with the next turn when there is one. */
      const rise = Math.abs(n[1] - b[1]);
      const inMax = Math.max(0, (b[0] - usedX) * 0.85);
      const outMax = Math.max(0, (nn[0] - n[0]) * (upright(nn, P[i + 3]) ? 0.45 : 0.85));
      const w = Math.min(2 * Math.max(16, Math.min(84, rise * 0.8)), inMax + outMax);
      let hin = Math.min(inMax, w / 2), hout = w - hin;
      if (hout > outMax) { hout = outMax; hin = Math.min(inMax, w - hout); }
      const sx = b[0] - hin, ex = b[0] + hout, mx = (sx + ex) / 2;
      d += ` L ${f(sx)} ${f(b[1])} C ${f(mx)} ${f(b[1])} ${f(mx)} ${f(n[1])} ${f(ex)} ${f(n[1])}`;
      /* the turn's footprint, sampled along the curve (8 small boxes), so a label beside it is not refused */
      const B = (t, a0, a1, a2, a3) => { const u = 1 - t; return u * u * u * a0 + 3 * u * u * t * a1 + 3 * u * t * t * a2 + t * t * t * a3; };
      for (let k = 0; k < 8; k++) {
        const t0 = k / 8, t1 = (k + 1) / 8;
        const xa = B(t0, sx, mx, mx, ex), xb = B(t1, sx, mx, mx, ex), ya = B(t0, b[1], b[1], n[1], n[1]), yb = B(t1, b[1], b[1], n[1], n[1]);
        boxes.push({ x0: Math.min(xa, xb) - 2, x1: Math.max(xa, xb) + 2, y0: Math.min(ya, yb) - 2, y1: Math.max(ya, yb) + 2 });
      }
      usedX = ex; i += 2; continue;
    }
    d += ` L ${f(b[0])} ${f(b[1])}`;
    usedX = b[0]; i++;
  }
  return { d, boxes };
}
/* ── Semantic zoom (int 04 §1, ported from the MVP renderer, 2026-10): Z0 WORLD · Z1 PATH · Z2 ROUTE on the
   canvas, Z3 DETAIL in the panel. The level is UI state only; zooming out keeps the chosen path chosen. ── */
const V12_LEVELS = ['Z0', 'Z1', 'Z2'];
const V12_LEVEL_WORD = { Z0: 'Overview', Z1: 'Path', Z2: 'Route' };
function v12LevelNow(snap) {
  const s = snap || V11_ENGINE.snapshot();
  const ch = mapsFocusState(s).choice;
  const l = V12_LEVELS.includes(STORE.mapsLevel) ? STORE.mapsLevel : 'Z0';
  return ch && s.paths.some(p => p.id === ch) ? l : 'Z0';
}
function v12SetLevel(l) {
  STORE.mapsLevel = V12_LEVELS.includes(l) ? l : 'Z0';
  V12_ZOOM.k = 1; V12_ZOOM.panX = 0; V12_ZOOM.panY = 0;
  const host = document.getElementById('v12-map'), snap = V11_ENGINE.snapshot();
  if (host) v12RenderInto(host, snap);
  const lvl = v12LevelNow(snap), p = snap.paths.find(x => x.id === mapsFocusState(snap).choice);
  const say = document.getElementById('mp-status');
  if (say) say.textContent = lvl === 'Z0' ? 'Overview: every path, without its steps.' : lvl === 'Z1' ? `Path: the steps and what ${p ? p.title : 'this path'} needs, in summary.` : `Route: everything ${p ? p.title : 'this path'} needs, one by one.`;
}
function v12ZoomIn() {
  const snap = V11_ENGINE.snapshot(), lvl = v12LevelNow(snap);
  if (lvl === 'Z0') {
    const ch = mapsFocusState(snap).choice;
    const pick = ch && snap.paths.some(p => p.id === ch) ? ch : (mapsActive(snap) || {}).id;
    if (!pick) { const say = document.getElementById('mp-status'); if (say) say.textContent = 'Choose a path on the map to see more of it.'; return; }
    STORE.mapsLevel = 'Z1';
    if (pick !== ch) { mapsSelect(pick); return; }
    return v12SetLevel('Z1');
  }
  if (lvl === 'Z1') v12SetLevel('Z2');
}
function v12ZoomOut() {
  const lvl = v12LevelNow();
  if (lvl === 'Z2') v12SetLevel('Z1'); else if (lvl === 'Z1') v12SetLevel('Z0');
}
function v12ToggleRoute() { v12LevelNow() === 'Z2' ? v12SetLevel('Z1') : (v12LevelNow() === 'Z1' ? v12SetLevel('Z2') : v12ZoomIn()); }
function v12ExpandRoute(id) { if (mapsFocusState(V11_ENGINE.snapshot()).choice !== id) mapsSelect(id); v12SetLevel('Z2'); }
function v12FitAll() { if (v12LevelNow() !== 'Z0') v12SetLevel('Z0'); else v12ZoomReset(); }
function v12ZoomReset() { V12_ZOOM.k = 1.0; V12_ZOOM.panX = 0; V12_ZOOM.panY = 0; v12ApplyZoom(); }
function v12ZoomBarHtml(snap) {
  const lvl = v12LevelNow(snap), ch = mapsFocusState(snap).choice;
  const canIn = lvl !== 'Z2' && !!(ch && snap.paths.some(p => p.id === ch) || mapsActive(snap));
  const b = (k, label, title, on, js) => `<button type="button" class="v12-zoom-btn" data-v12-zoom="${k}" title="${title}" aria-label="${title}" ${on ? '' : 'disabled'} onclick="${js}">${label}</button>`;
  /* minus, plus, fit: the level (Overview/Path/Route) is internal; the canvas does not name it */
  return b('out', '−', 'Show less', lvl !== 'Z0', 'v12ZoomOut()')
    + b('in', '+', 'Show more', canIn, 'v12ZoomIn()')
    + b('fit', '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>', 'Fit the map', true, 'v12FitAll()');
}

/* ── 2D: navigation canvas in the v10 composition, with v11 objects (2026-10-17). Four objects, never merged:
   · PATH  = a strategic direction: a card on its own corridor (name, status). A path never leads into another path.
   · MOVE  = the one executable move the record names for a path (path.next_move). One small marker at the FRONT of
             its corridor. Its actions (MOVE_STEPS_CATALOG: Research, Draft, Send…) are inside the move, so they are
             listed in the panel, never drawn as map nodes.
   · CONDITION = what the path needs (its requirements). One dashed checkpoint with evidence-backed progress
             ("N of M confirmed"); Z2 opens it into each requirement. A requirement several paths list is marked
             "shared" there and in the panel; it is never drawn as a junction the paths pass through.
   · GOAL  = a separate landmark. No corridor reaches it; a corridor fades out after its checkpoint.
   Z0 overview: start, cards, move marker on the path in focus, a lock + "N of M" per path. Z1: the chosen path's move
   named, and its checkpoint named. Z2: each condition. Z3: the panel. Order of lanes = engine order (never status). */
/* A node opened in place (semantic zoom): a MOVE opens into its actions, a CONDITION checkpoint into its conditions.
   The capsule replaces the node; its items are what the node holds, in their own order. Actions read their done state
   from the same record as the Moves checklist (isStepDone); the first not done is the current action. */
function v12Capsule(kind, o) {
  const { cx, y, items, spacing, color, wrapAt } = o;
  const n = items.length, w = (n - 1) * spacing + 30, x0 = cx - (n - 1) * spacing / 2;
  const T = (x, yy, s, st) => `<text x="${x}" y="${yy}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="${st.s}" font-weight="${st.w}" fill="${st.f}" paint-order="stroke" stroke="#ffffff" stroke-width="3.5" stroke-linejoin="round" pointer-events="none">${stratEsc(s)}</text>`;
  const wrap = (t, c) => { const out = ['']; String(t).split(/\s+/).forEach(w => { const cur = out[out.length - 1]; if (!cur) out[out.length - 1] = w; else if ((cur + ' ' + w).length <= c) out[out.length - 1] = cur + ' ' + w; else out.push(w); }); if (out.length > 2) { out.length = 2; out[1] = v12Short(out[1], c - 1) + '…'; } return out; };
  let g = `<rect x="${cx - w / 2}" y="${y - 15}" width="${w}" height="30" rx="15" fill="#ffffff" stroke="${kind === 'move' ? '#18181b' : '#a1a1aa'}" stroke-width="${kind === 'move' ? 2 : 1.5}"${kind === 'move' ? '' : ' stroke-dasharray="3 3"'}/>`;
  if (n > 1) g += `<path d="M ${x0} ${y} L ${x0 + (n - 1) * spacing} ${y}" stroke="${kind === 'move' ? color : '#d4d4d8'}" stroke-width="2" ${kind === 'move' ? '' : 'stroke-dasharray="2 3"'}/>`;
  items.forEach((it, i) => {
    const x = x0 + i * spacing;
    let dot;
    if (kind === 'move') {
      dot = it.state === 'done' ? `<circle cx="${x}" cy="${y}" r="7" fill="${color}"/><path d="M ${x - 2.8} ${y + 0.2} l 1.9 1.9 l 3.7 -4" stroke="#ffffff" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`
        : it.state === 'current' ? `<circle cx="${x}" cy="${y}" r="7" fill="#ffffff" stroke="#18181b" stroke-width="2.6"/><circle cx="${x}" cy="${y}" r="2.2" fill="#18181b"/>`
        : `<circle cx="${x}" cy="${y}" r="6.5" fill="#ffffff" stroke="#a1a1aa" stroke-width="2"/>`;
    } else {
      const ring = { met: '#059669', partial: '#d97706', unknown: '#a1a1aa', absent: '#dc2626' }[it.state] || '#a1a1aa';
      dot = `<circle cx="${x}" cy="${y}" r="8" fill="#ffffff" stroke="${ring}" stroke-width="1.8" stroke-dasharray="3 2.5"/><svg x="${x - 4.5}" y="${y - 4.5}" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#3f3f46" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" style="pointer-events:none">${V12_METRO_ICON[it.state] || V12_METRO_ICON.unknown}</svg>`;
    }
    const ls = wrap(it.label, wrapAt || 11);
    /* DATA IDENTITY: an action element carries the server-issued action_id (and its move_id) when the
       record has one; it never invents one from an index. Conditions keep their own group. */
    g += `<g class="${kind === 'move' ? 'v12-action' : 'v12-station v12-own'}"${it.key || it.actionId ? ` data-v12-action="${it.actionId || it.key}"` : ''}${it.moveId ? ` data-v12-move="${it.moveId}"` : ''}${it.onclick ? ` role="button" tabindex="0" onclick="${it.onclick}" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();${it.onclick}}` : ''} data-state="${it.state}"><title>${stratEsc(it.title)}</title>${dot}`
      + ls.map((l, k) => T(x, y + 29 + k * 10.5, l, { s: 8.5, w: it.state === 'current' ? 700 : 600, f: it.state === 'current' ? '#18181b' : '#3f3f46' })).join('')
      + (it.sub ? T(x, y + 29 + ls.length * 10.5, it.sub, { s: 8, w: 500, f: '#71717a' }) : '') + '</g>';
  });
  return { svg: g, w };
}
/* The actions of ONE canonical Move, as capsule items. A step's key carries the action identity
   (path · move_id · action_id), never only a path index; the item also carries the raw action_id and
   move_id so the rendered element states exactly whose action it is. */
function v12ActionItems(pathId, moveId) {
  const steps = getMoveSteps(pathId, moveId) || [];
  const doneFlags = steps.map((st, i) => isStepDone(pathId, moveId, i, st));
  const cur = doneFlags.findIndex(d => !d);
  const mv = (moveId && typeof liveMoveById === 'function') ? liveMoveById(moveId) : null;
  const mvName = mv ? v12Short(String(mv.objective || mv.title || ''), 60) : '';
  const on = `event.stopPropagation();v12OpenMove('${pathId}','${moveId}')`;
  return steps.map((st, i) => {
    const state = doneFlags[i] ? 'done' : i === cur ? 'current' : 'next';
    const aid = st.actionId || st.id || '';
    return { key: `${pathId}:${moveId || ''}:${aid || i}`, state, label: st.label,
      actionId: st.actionId || '', moveId: String(moveId || ''), onclick: moveId ? on : '',
      title: `Action ${i + 1} of ${steps.length}${mvName ? ` in “${mvName}”` : ' in this move'}: ${st.label} (${state === 'done' ? 'done' : state === 'current' ? 'current action' : 'not done'})` };
  });
}
function v12ConditionItems(reqs) {
  return reqs.map(r => { const st = V12_REQ_NODE[r.satisfaction] || 'unknown'; return { state: st, label: r.label, sub: V12_STATE_WORD[st], title: `${V12_STATE_WORD[st]}: ${r.label}` }; });
}
function v12Build2D(shape, cw, ch, selId, focusId, viewW) {
  const paths = shape.paths;
  const n = paths.length;
  const vw = viewW || cw;
  const level = shape.level || 'Z0';
  const narrow = vw < 560;
  const x0 = narrow ? 34 : 50;
  const goalW = narrow ? 112 : 150, goalH = 54;
  const goalLeftX = cw - goalW - (narrow ? 12 : 22);
  const STATUS = { 'OPEN': '#059669', 'TEST FIRST': '#2563eb', 'NOT YET': '#d97706', 'STOP': '#dc2626' };
  const PILLC = { 'OPEN': '#047857', 'TEST FIRST': '#1d4ed8', 'NOT YET': '#b45309', 'STOP': '#b91c1c' };
  const NEUTRAL = '#a1a1aa';
  const T = (x, y, s, o) => {
    o = o || {};
    return `<text x="${x}" y="${y}"${o.a ? ` text-anchor="${o.a}"` : ''} font-family="Plus Jakarta Sans" font-size="${o.s || 10.5}" font-weight="${o.w || 500}" fill="${o.f || '#71717a'}"${o.ls ? ` letter-spacing="${o.ls}"` : ''}${o.po ? ` paint-order="stroke" stroke="#ffffff" stroke-width="${o.po}" stroke-linejoin="round"` : ''} pointer-events="none">${stratEsc(s)}</text>`;
  };
  const wrap = (t, c) => {
    const out = [''];
    String(t).split(/\s+/).forEach(w => { const cur = out[out.length - 1]; if (!cur) out[out.length - 1] = w; else if ((cur + ' ' + w).length <= c) out[out.length - 1] = cur + ' ' + w; else out.push(w); });
    if (out.length > 2) { out.length = 2; out[1] = v12Short(out[1], c - 1) + (out[1].endsWith('…') ? '' : '…'); }
    return out.map(l => v12Short(l, c));
  };

  const proj = shape.proj;
  const selReq = selId && proj.byKey.has(selId) ? proj.byKey.get(selId) : null;
  const selPath = selId && paths.some(p => p.id === selId) ? selId : null;
  const lit = id => !selId || (selPath ? selPath === id : (selReq ? selReq.members.includes(id) : true));
  const detailOn = selPath && level !== 'Z0';
  const selTitle = selPath ? (paths.find(p => p.id === selPath) || {}).title : '';
  const noteText = detailOn && level === 'Z2' ? `What ${selTitle} needs, one by one. Conditions are checked by evidence, not by doing a move.`
    : detailOn ? `${selTitle}: its move, and what it needs. Press + to see each condition.`
    : selReq ? 'Highlighted: the paths that list this condition. Listed by several paths is not an order.'
    : 'Each card is a possible path. Lines show where each one starts, not steps, dates or a sure way to your goal.';
  const bg = T(16, 20, v12Short(noteText, Math.max(20, Math.floor((vw - 24) / 5.6))), { s: 10.5, f: '#71717a' });

  /* Columns: start · cards · move slot · checkpoint · (Z2 conditions) · fade · goal */
  const cardX = x0 + (narrow ? 70 : 110);
  const cardW = Math.round(Math.max(176, Math.min(232, cw * 0.2))), cardH = 50;
  const moveX = cardX + cardW + (narrow ? 60 : 80);
  const ckX = moveX + (narrow ? 104 : 140);
  const fadeEnd = Math.min(goalLeftX - 48, ckX + 120);
  const top = 78, bottom = ch - 40;
  const laneGap = n > 1 ? Math.min(118, (bottom - top) / (n - 1)) : 0;
  const block = laneGap * (n - 1);
  const firstY = Math.round((top + bottom) / 2 - block / 2);
  const laneY = paths.map((p, i) => Math.round(firstY + i * laneGap));
  const midY = n ? Math.round((laneY[0] + laneY[n - 1]) / 2) : Math.round(ch / 2);
  const sx = x0 + 14;

  const focusPath = paths.find(p => p.id === focusId && p.status !== 'STOP');
  const sharedOf = r => { const k = v12ReqKey(r.id, r.label); return proj.shared.find(s => s.reqs.some(q => q.key === k)) || null; };
  const RING = { met: '#059669', partial: '#d97706', unknown: '#a1a1aa', absent: '#dc2626' };

  let lines = '', hits = '', nodes = '', tags = '', ends = '', badge = '', detail = '';
  paths.forEach((p, pi) => {
    const ly = laneY[pi];
    const stop = p.status === 'STOP';
    const isFocus = focusPath && focusPath.id === p.id;
    const on = !!selId && lit(p.id), quiet = !lit(p.id);
    const hot = isFocus || (selPath === p.id) || (selReq && on);
    const color = hot ? (STATUS[p.status] || NEUTRAL) : NEUTRAL;
    const op = quiet ? 0.35 : (hot ? 1 : 0.7);
    /* the branch: one soft curve from the start to the card (horizontal tangents at both ends) */
    const bx = (cardX - sx) * 0.55;
    const branch = Math.abs(ly - midY) < 0.5 ? `M ${sx} ${midY} L ${cardX} ${ly}` : `M ${sx} ${midY} C ${sx + bx} ${midY} ${cardX - bx} ${ly} ${cardX} ${ly}`;
    const live = (p.requirements || []).filter(r => r.applicable !== false);
    /* Phase 7: the path's canonical Moves as the persistent sequence the read model declared. The order
       on the lane is presentation only. No edge is drawn between two Moves and no dependency is
       inferred from their order: only an explicit depends_on in the record restricts it. */
    const seq = Array.isArray(p.moveSeq) ? p.moveSeq : null;
    const chosen = detailOn && selPath === p.id;
    const seqCur = (seq && seq.length) ? seq.findIndex(m => m.status === 'current') : -1;
    const seqSelIdx = (chosen && seq && seq.length) ? seq.findIndex(m => m.id === (v12SeqSelectedMove(p.id, seq) || {}).id) : -1;
    let seqStart = 0, seqShown = [];
    if (seq && seq.length) {
      const CAP = 4;                                      /* at most four stations inline */
      seqStart = Math.max(0, seq.length - CAP);
      if (seqCur >= 0 && seqCur < seqStart) seqStart = seqCur;             /* the current Move is never collapsed */
      if (seqSelIdx >= 0 && seqSelIdx < seqStart) {
        const anchor = seqCur >= 0 ? Math.max(seqCur, seqSelIdx) : seqStart;
        seqStart = (anchor - seqSelIdx) <= CAP - 1 ? Math.max(0, anchor - (CAP - 1)) : seqStart;
      }
      seqShown = seq.slice(seqStart, seqStart + CAP);
    }
    const seqSelected = (chosen && seq && seq.length) ? v12SeqSelectedMove(p.id, seq) : null;
    const seqSelShown = !!(seqSelected && seqShown.some(m => String(m.id) === String(seqSelected.id)));
    /* the selected station opens into its actions (Z1+); the checkpoint moves right to make room */
    const openActs = (seq && seq.length)
      ? (seqSelShown ? v12ActionItems(p.id, seqSelected.id) : [])
      : (chosen && p.hasMove && !stop ? v12ActionItems(p.id, null) : []);
    const capW = openActs.length > 1 ? (openActs.length - 1) * 58 + 30 : 0;
    /* A station now carries the Move's NAME under it, so the gap must fit the name, not just the
       dot: with 2-3 named Moves the lane widens (the condition cluster and the corridor shift with
       it through seqW/ck below). Beyond three stations the names are tooltip-only and the compact
       gap returns, so a long history never squeezes the lane. */
    const _nameGap = (seq && seq.length && seq.length <= 3) ? (narrow ? 92 : 128) : 52;
    const MOVE_GAP = _nameGap, seqXs = [];
    let seqW = 0;
    if (seq && seq.length) {
      const chipW = seqStart > 0 ? 96 : 0;                 /* the "+N earlier moves" chip takes the first slot (+ a gap) */
      let shift = 0;
      seqShown.forEach((m, i) => {
        seqXs[i] = moveX + chipW + i * MOVE_GAP + shift;
        if (seqSelShown && openActs.length && String(m.id) === String(seqSelected.id)) shift += Math.max(capW, 30) + 18;
      });
      const lastX = seqXs.length ? seqXs[seqXs.length - 1] : moveX + chipW;
      let right = lastX + 14;
      if (seqSelShown && openActs.length) {
        const oi = seqShown.findIndex(m => String(m.id) === String(seqSelected.id));
        if (oi >= 0) right = Math.max(right, seqXs[oi] + 22 + (capW || 30) + 14);
      }
      seqW = Math.max(0, right - moveX);
    }
    const capX = (seqSelShown && openActs.length)
      ? (() => { const oi = seqShown.findIndex(m => String(m.id) === String(seqSelected.id)); return seqXs[oi >= 0 ? oi : 0] + 22 + (capW ? capW / 2 : 15); })()
      : moveX - 15 + capW / 2;
    const ck = (seq && seq.length) ? Math.max(ckX, moveX + seqW + 44) : (capW ? Math.max(ckX, moveX - 15 + capW + 44) : ckX);
    const met = live.filter(r => r.satisfaction === 'PRESENT').length;
    const corridorEnd = stop ? cardX + cardW + 34 : (detailOn && selPath === p.id && level === 'Z2' && live.length ? Math.min(goalLeftX - 48, ck + 26 + live.length * 92) : fadeEnd);
    const solidTo = stop ? corridorEnd : (live.length ? ck - 13 : corridorEnd - 40);
    const d = `${branch} M ${cardX + cardW} ${ly} L ${solidTo} ${ly}`;
    const dash = stop ? ' stroke-dasharray="5 5"' : '';
    lines += `<g class="v12-route${on ? ' is-sel' : ''}${quiet ? ' is-quiet' : ''}" data-v12-route="${p.id}" opacity="${op}"><path class="v12-line v12-corridor" data-v12-path="${p.id}" d="${d}" stroke="${color}" stroke-width="${selPath === p.id ? 3.5 : 2.5}" fill="none" stroke-linecap="round"${dash}/>`
      + (stop ? '' : `<path d="M ${live.length ? ck + 13 : corridorEnd - 40} ${ly} L ${corridorEnd} ${ly}" stroke="${color}" stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round" fill="none" opacity="0.7"/>`)
      /* an OPEN path points toward the goal with a dotted line: a direction the evidence supports, never a sure way */
      + (p.status === 'OPEN' ? (() => { const gx = goalLeftX - 4, dx = Math.max(20, (gx - corridorEnd) * 0.55); return `<path class="v12-goal-link" data-v12-goal-link="${p.id}" d="M ${corridorEnd} ${ly} C ${corridorEnd + dx} ${ly} ${gx - dx} ${midY} ${gx} ${midY}" stroke="${STATUS['OPEN']}" stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round" fill="none" opacity="${quiet ? 0.35 : 0.8}"><title>May lead toward your goal: the evidence supports this path (OPEN). A possible direction, not a sure way.</title></path>`; })() : '') + '</g>';
    hits += `<path d="${d}" stroke="transparent" stroke-width="16" fill="none" style="cursor:pointer" data-v12-hit="${p.id}" onclick="v12Tap('${p.id}')" onmouseenter="v12RouteHover('${p.id}',true)" onmouseleave="v12RouteHover('${p.id}',false)"/>`;

    /* the card */
    const full = `${p.title} · ${v12StatusWord(p)}${isFocus ? ' · in focus' : ''}`;
    const origin = p.stop_source ? (p.stop_source === 'you' ? 'by you' : 'by the evidence') : '';
    const statusLine = [p.status, isFocus ? 'IN FOCUS' : '', origin && !narrow ? origin : ''].filter(Boolean).join(' · ');
    const pressed = selPath === p.id;
    tags += `<g class="v12-lane-label v12-card${quiet ? ' is-quiet' : ''}${isFocus ? ' is-focus' : ''}" data-v12-path="${p.id}" role="button" tabindex="0" aria-pressed="${pressed}" aria-label="${stratEsc(full)}" onkeydown="v12Key(event,'${p.id}')" onclick="v12Tap('${p.id}')" onmouseenter="v12RouteHover('${p.id}',true)" onmouseleave="v12RouteHover('${p.id}',false)" style="cursor:pointer" opacity="${quiet ? 0.5 : 1}"><title>${stratEsc(full)}</title>`
      + (isFocus ? `<rect x="${cardX - 5}" y="${ly - cardH / 2 - 5}" width="${cardW + 10}" height="${cardH + 10}" rx="16" fill="none" stroke="#a7f3d0" stroke-width="4"/>` : '')
      + `<rect class="v12-tag-hit" x="${cardX}" y="${ly - cardH / 2}" width="${cardW}" height="${cardH}" rx="12" fill="#ffffff" stroke="${pressed ? '#18181b' : '#e4e4e7'}" stroke-width="${pressed ? 2 : 1.2}" pointer-events="all"/>`
      + `<circle cx="${cardX + 18}" cy="${ly - 6}" r="5" fill="${STATUS[p.status] || NEUTRAL}"/>`
      + `<text class="v12-lt" x="${cardX + 31}" y="${ly - 2}" font-family="Plus Jakarta Sans" font-size="12" font-weight="${pressed || isFocus ? 700 : 600}" fill="#18181b" pointer-events="none">${stratEsc(v12Short(p.title, Math.floor((cardW - 42) / 6.3)))}</text>`
      + `<text x="${cardX + 31}" y="${ly + 14}" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" letter-spacing="0.05em" fill="${PILLC[p.status] || '#52525b'}" pointer-events="none">${stratEsc(statusLine.toUpperCase())}</text></g>`;

    if (stop) {
      const tx = corridorEnd;
      ends += `<g class="v12-stop-end${quiet ? ' is-quiet' : ''}" data-v12-route="${p.id}" onclick="v12Tap('${p.id}')" style="cursor:pointer" opacity="${quiet ? 0.4 : 0.85}"><title>${stratEsc(p.title)} · Stopped ${p.stop_source === 'you' ? 'by you' : 'by the evidence'}</title><circle cx="${tx}" cy="${ly}" r="9" fill="#ffffff" stroke="#dc2626" stroke-width="2"/><path d="M ${tx - 3} ${ly - 3} L ${tx + 3} ${ly + 3} M ${tx + 3} ${ly - 3} L ${tx - 3} ${ly + 3}" stroke="#dc2626" stroke-width="1.8" stroke-linecap="round"/>`
        + T(tx + 15, ly + 3.5, 'Stopped', { s: 9.5, w: 700, f: '#b91c1c', po: 3 }) + '</g>';
      return;
    }

    /* MOVE: the path's persistent journey, one station per canonical Move. When the read model carries no
       sequence (demo, or an older payload) the single-marker behaviour below is kept exactly. */
    if (seq && seq.length) {
      if (seqStart > 0) {
        const chipW = 88, chipTxt = `+${seqStart} earlier move${seqStart === 1 ? '' : 's'}`;
        nodes += `<g class="v12-seq-more" data-v12-move-count="${seqStart}" role="button" tabindex="0" aria-label="${stratEsc(chipTxt + '. Open Moves to see every move')}" onclick="event.stopPropagation();goDestination('moves')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();goDestination('moves')}" style="cursor:pointer" opacity="${quiet ? 0.45 : 0.9}"><title>${stratEsc(`${chipTxt} not drawn here. Open Moves to see every move`)}</title>`
          + `<rect x="${moveX}" y="${ly - 10}" width="${chipW}" height="20" rx="10" fill="#ffffff" stroke="#a1a1aa" stroke-width="1.2" stroke-dasharray="3 2.5"/>`
          + T(moveX + chipW / 2, ly + 3.2, chipTxt, { a: 'middle', s: 8.5, w: 700, f: '#52525b' }) + '</g>';
      }
      seqShown.forEach((m, i) => {
        const x = seqXs[i] !== undefined ? seqXs[i] : moveX, num = seqStart + i + 1, st = m.status || 'next';
        const counts = m.actionsTotal ? `${m.actionsDone} of ${m.actionsTotal} actions completed` : 'No actions recorded yet';
        const tip = `${m.objective || m.title || 'Move'} · ${counts}${st === 'done' ? ` · ${m.lifecycle || 'EXECUTED'}` : st === 'current' ? ' · current' : st === 'abandoned' ? ' · abandoned' : ''}`;
        const mark = st === 'done' ? `<circle cx="${x}" cy="${ly}" r="10" fill="${color}"/><path d="M ${x - 3.6} ${ly + 0.2} l 2.4 2.4 l 4.6 -4.8" stroke="#ffffff" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`
          : st === 'current' ? `<circle cx="${x}" cy="${ly}" r="11" fill="#ffffff" stroke="#18181b" stroke-width="3"/><circle cx="${x}" cy="${ly}" r="2.6" fill="#18181b"/>`
          : st === 'locked' ? `<circle cx="${x}" cy="${ly}" r="8" fill="#ffffff" stroke="#a1a1aa" stroke-width="1.8" stroke-dasharray="3 2.5"/>`
          : st === 'abandoned' ? `<circle cx="${x}" cy="${ly}" r="8" fill="#ffffff" stroke="#a1a1aa" stroke-width="1.6" stroke-dasharray="2.5 2"/><path d="M ${x - 3} ${ly - 3} L ${x + 3} ${ly + 3} M ${x + 3} ${ly - 3} L ${x - 3} ${ly + 3}" stroke="#a1a1aa" stroke-width="1.6" stroke-linecap="round"/>`
          : `<circle cx="${x}" cy="${ly}" r="9" fill="#ffffff" stroke="${color}" stroke-width="2.4"/><circle cx="${x}" cy="${ly}" r="2" fill="${color}"/>`;
        const word = st === 'done' ? String(m.lifecycle || 'EXECUTED') : st === 'current' ? 'current' : '';
        /* the objective, shortened to what fits under one station (never a fabricated name) */
        const _nm = String(m.title || m.objective || '').trim();
        const _lim = narrow ? 16 : 24;
        const moveName = _nm.length <= _lim ? _nm
          : (_nm.slice(0, _lim - 1).replace(/\s+\S*$/, '') || _nm.slice(0, _lim - 1)) + '…';
        const dim = quiet ? 0.4 : (st === 'locked' || st === 'abandoned' ? 0.7 : 1);
        nodes += `<g class="v12-station v12-seq-station is-${st}" data-v12-move="${m.id}" data-state="${st}" role="button" tabindex="0" aria-label="${stratEsc(`Move ${num}: ${m.title}${word ? ', ' + word : ''}. ${counts}. Open its detail`)}" onclick="event.stopPropagation();v12OpenMove('${p.id}','${m.id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();v12OpenMove('${p.id}','${m.id}')}" style="cursor:pointer" opacity="${dim}"><title>${stratEsc(tip)}</title>${mark}`
          + T(x, ly + 22, `Move ${num}`, { a: 'middle', s: 9, w: st === 'current' ? 700 : 600, f: st === 'locked' || st === 'abandoned' ? '#a1a1aa' : st === 'current' ? '#18181b' : '#52525b', po: 3.5 })
          + (word ? T(x, ly + 32, word, { a: 'middle', s: 7.6, w: 700, f: st === 'done' ? '#047857' : '#18181b', po: 3, ls: '0.04em' }) : '')
          /* THE MOVE'S NAME, under its station: a move is work with an objective ('Create the
             proposal'), never a generic 'next move'. Shown while the lane has room for it. */
          + ((seqShown.length <= 3 && moveName) ? T(x, ly + (word ? 42 : 34), moveName, { a: 'middle', s: 8, w: 600, f: st === 'locked' || st === 'abandoned' ? '#a1a1aa' : '#52525b', po: 3 }) : '')
          /* where the selected station stands, right under it (only for the chosen path) */
          + (chosen && seqSelected && String(m.id) === String(seqSelected.id) ? T(x, ly + (openActs.length ? 64 : 54), st === 'done' ? 'Move executed' : counts, { a: 'middle', s: 8, w: 600, f: '#71717a', po: 3 }) : '')
          + '</g>';
        if (st === 'current' && (isFocus || chosen)) badge = `<g class="v12-here-badge" data-v12-marker="move" aria-hidden="true"><path d="M ${x} ${ly - 26} L ${x} ${ly - 13}" stroke="#047857" stroke-width="1.5" stroke-linecap="round"/><rect x="${x - 42}" y="${ly - 44}" width="84" height="18" rx="9" fill="#047857"/><text x="${x}" y="${ly - 32}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" fill="#ffffff">Current move</text></g>`;
      });
      if (seqSelShown && openActs.length) {
        const cap = v12Capsule('move', { cx: capX, y: ly, items: openActs, spacing: 58, color: STATUS[p.status] || NEUTRAL, wrapAt: 10 });
        nodes += `<g class="v12-station v12-move v12-move-open" data-v12-move="${seqSelected.id}" data-actions="${openActs.length}"><title>${stratEsc(`${seqSelected.title} · ${openActs.length} action${openActs.length === 1 ? '' : 's'} inside`)}</title>${cap.svg}</g>`;
      }
    } else if (p.hasMove && capW) {
      /* the move, opened: its actions inside it (the same record as the Moves checklist) */
      const cap = v12Capsule('move', { cx: capX, y: ly, items: openActs, spacing: 58, color: STATUS[p.status] || NEUTRAL, wrapAt: 10 });
      nodes += `<g class="v12-station v12-move v12-move-open${isFocus ? ' v12-focal' : ''}" data-v12-move="${p.id}" data-actions="${openActs.length}"><title>${stratEsc(`Move: ${p.moveTitle} · ${openActs.length} actions inside`)}</title>${cap.svg}</g>`;
      if (isFocus) { const bt = `Current move · ${v12Short(p.moveTitle, 30)}`, bw = Math.round(bt.length * 4.9 + 22); badge = `<g class="v12-here-badge" data-v12-marker="move" aria-hidden="true"><path d="M ${capX} ${ly - 28} L ${capX} ${ly - 16}" stroke="#047857" stroke-width="1.5"/><rect x="${capX - bw / 2}" y="${ly - 46}" width="${bw}" height="18" rx="9" fill="#047857"/><text x="${capX}" y="${ly - 34}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" fill="#ffffff">${stratEsc(bt)}</text></g>`; }
    } else if (p.hasMove) {
      const steps = getMoveSteps(p.id, null) || [];
      const done = steps.filter((st, i) => isStepDone(p.id, null, i, st)).length;
      const name = `Move: ${p.moveTitle}${steps.length ? ` · ${steps.length} action${steps.length === 1 ? '' : 's'} inside, ${done} done` : ''}`;
      nodes += `<g class="v12-station v12-move${isFocus ? ' v12-focal' : ''}${quiet ? ' is-quiet' : ''}" data-v12-move="${p.id}" onclick="event.stopPropagation();v12Tap('${p.id}')" style="cursor:pointer" opacity="${quiet ? 0.4 : 1}"><title>${stratEsc(name)}</title>`
        + `<circle cx="${moveX}" cy="${ly}" r="10" fill="#ffffff"/><circle cx="${moveX}" cy="${ly}" r="7" fill="#ffffff" stroke="${isFocus || chosen ? '#18181b' : color}" stroke-width="3"/><circle cx="${moveX}" cy="${ly}" r="2.2" fill="${isFocus || chosen ? '#18181b' : color}"/>`
        + (chosen ? wrap(p.moveTitle, narrow ? 18 : 24).map((l, i) => T(moveX, ly + 24 + i * 11, l, { a: 'middle', s: 9.5, w: i ? 500 : 600, f: '#27272a', po: 3.5 })).join('')
          + (steps.length ? T(moveX, ly + 24 + Math.min(2, wrap(p.moveTitle, narrow ? 18 : 24).length) * 11, `${steps.length} action${steps.length === 1 ? '' : 's'} inside · ${done} done`, { a: 'middle', s: 8.5, f: '#71717a', po: 3 }) : '')
          : T(moveX, ly + 24, 'Move', { a: 'middle', s: 8.5, w: 600, f: '#71717a', po: 3 }))
        + '</g>';
      if (isFocus) badge = `<g class="v12-here-badge" data-v12-marker="move" aria-hidden="true"><path d="M ${moveX} ${ly - 24} L ${moveX} ${ly - 11}" stroke="#047857" stroke-width="1.5" stroke-linecap="round"/><rect x="${moveX - 42}" y="${ly - 42}" width="84" height="18" rx="9" fill="#047857"/><text x="${moveX}" y="${ly - 30}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" fill="#ffffff">Current move</text></g>`;
    } else if (p.waiting) {
      /* a WAITING move (as in Moves): locked behind what the path still needs; no step is named, so none is drawn */
      const need = p.waitNeed ? `${p.waitNeed.label} (${(REQ_WORDS[p.waitNeed.satisfaction] || 'not known yet')})` : '';
      const name = `Move waiting · no step named yet${need ? ` · first it needs: ${need}` : ''}`;
      nodes += `<g class="v12-station v12-move is-waiting${quiet ? ' is-quiet' : ''}" data-v12-move-waiting="${p.id}" onclick="event.stopPropagation();v12Tap('${p.id}')" style="cursor:pointer" opacity="${quiet ? 0.4 : 0.85}"><title>${stratEsc(name)}</title>`
        + `<circle cx="${moveX}" cy="${ly}" r="10" fill="#ffffff"/><circle cx="${moveX}" cy="${ly}" r="7" fill="#fafafa" stroke="#a1a1aa" stroke-width="1.6" stroke-dasharray="2.5 2"/>`
        + `<path d="M ${moveX - 2.2} ${ly - 0.6} v -1.3 a 2.2 2.2 0 0 1 4.4 0 v 1.3 M ${moveX - 3} ${ly - 0.6} h 6 v 4 h -6 z" stroke="#71717a" stroke-width="1.1" fill="none" stroke-linejoin="round"/>`
        + (chosen ? wrap(`Waiting on: ${p.waitNeed ? p.waitNeed.label : 'what it needs'}`, narrow ? 18 : 24).map((l, i) => T(moveX, ly + 24 + i * 11, l, { a: 'middle', s: 9, w: i ? 500 : 600, f: '#52525b', po: 3.5 })).join('')
          : T(moveX, ly + 24, 'Waiting', { a: 'middle', s: 8.5, w: 600, f: '#a1a1aa', po: 3 }))
        + '</g>';
    } else if (chosen) {
      nodes += T(moveX, ly + 4, 'No move named yet', { a: 'middle', s: 9, f: '#a1a1aa', po: 3 });
    }

    /* CONDITION: one dashed checkpoint with evidence-backed progress; Z2 opens it */
    if (!live.length) return;
    if (chosen && level === 'Z2') {
      live.forEach((r, i) => {
        const rx = ck + i * 92, st = V12_REQ_NODE[r.satisfaction] || 'unknown';
        const sh = sharedOf(r);
        /* INV-R8: an executed route node is VERIFY — the requirement stays unresolved until evidence. */
        const nm = `${V12_STATE_WORD[st]}: ${r.label}${r.executed && st !== 'met' ? ' · executed, proof still needed' : ''}${sh ? ` · shared by ${sh.members.length} paths` : ''}`;
        const ls = wrap(r.label, 16).concat([V12_STATE_WORD[st]]).concat(sh ? [`Shared by ${sh.members.length} paths`] : []);
        detail += `<g class="v12-station v12-own${sh ? ' v12-shared-cond' : ''}"${sh ? ` role="button" tabindex="0" aria-label="${stratEsc('Shared condition: ' + nm)}" onclick="event.stopPropagation();mapsSelect('${sh.key}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();mapsSelect('${sh.key}')}" style="cursor:pointer"` : ''}><title>${stratEsc(nm)}</title>`
          + `<circle cx="${rx}" cy="${ly}" r="10" fill="#ffffff" stroke="${RING[st]}" stroke-width="1.8" stroke-dasharray="3 2.5"/><svg x="${rx - 4.5}" y="${ly - 4.5}" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#3f3f46" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" style="pointer-events:none">${V12_METRO_ICON[st] || V12_METRO_ICON.unknown}</svg>`
          + ls.map((l, k) => T(rx, ly + 24 + k * 10.5, l, Object.assign({ a: 'middle', s: 9, w: 600, f: '#27272a', po: 3.5 }, k >= ls.length - (sh ? 2 : 1) ? { s: 8.5, w: k === ls.length - 1 && sh ? 700 : 500, f: k === ls.length - 1 && sh ? '#475569' : '#71717a' } : {}))).join('') + '</g>';
      });
      return;
    }
    const name = `What it needs · ${met} of ${live.length} confirmed — show each one`;
    nodes += `<g class="v12-station v12-cluster${quiet ? ' is-quiet' : ''}" data-v12-cluster="${live.length}"${chosen ? ' role="button" tabindex="0"' : ''} aria-label="${stratEsc(name)}" onclick="event.stopPropagation();v12ExpandRoute('${p.id}')"${chosen ? ` onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();v12ExpandRoute('${p.id}')}"` : ''} style="cursor:pointer" opacity="${quiet ? 0.4 : (hot ? 1 : 0.75)}"><title>${stratEsc(name)}</title>`
      + `<circle cx="${ck}" cy="${ly}" r="12" fill="#ffffff" stroke="#a1a1aa" stroke-width="1.5" stroke-dasharray="3 3"/><path d="M ${ck - 3.5} ${ly - 1} v -2 a 3.5 3.5 0 0 1 7 0 v 2 M ${ck - 4.5} ${ly - 1} h 9 v 6 h -9 z" stroke="#71717a" stroke-width="1.4" fill="none" stroke-linejoin="round"/>`
      + (chosen ? T(ck, ly + 27, 'What it needs', { a: 'middle', s: 9.5, w: 600, f: '#27272a', po: 3.5 }) + T(ck, ly + 38, `${met} of ${live.length} confirmed`, { a: 'middle', s: 8.5, f: '#71717a', po: 3 })
        : T(ck, ly + 27, `${met} of ${live.length}`, { a: 'middle', s: 8.5, f: '#a1a1aa', po: 3 }))
      + '</g>';
  });

  /* Start and goal. The goal stands alone: no corridor reaches it. */
  ends += `<circle cx="${x0}" cy="${midY}" r="15" fill="#ffffff"/><circle cx="${x0}" cy="${midY}" r="13" fill="#18181b"/><circle cx="${x0}" cy="${midY}" r="4.5" fill="#ffffff"/>`
    + T(narrow ? x0 - 15 : x0, midY + 30, 'YOUR STATE', { a: narrow ? 'start' : 'middle', w: 700, s: 10.5, f: '#18181b', ls: '0.04em', po: 3 })
    + T(narrow ? x0 - 15 : x0, midY + 42, v12Short(v12NowText(shape), 16), { a: narrow ? 'start' : 'middle', s: 9, f: '#71717a', po: 3 });
  const goalText = v12GoalText(shape).replace('Goal · ', '');
  const gy = midY - Math.round(goalH / 2);
  ends += `<g class="v12-goal-node" aria-label="Goal: ${stratEsc(goalText)}. A separate landmark, judged by its own metric; only open paths point toward it, with a dotted line (possible, not certain).">
      <rect class="v12-goal-bg" x="${goalLeftX}" y="${gy}" width="${goalW}" height="${goalH}" rx="14" fill="#18181b"/>
      <text x="${goalLeftX + 18}" y="${midY - 8}" font-family="Plus Jakarta Sans" font-size="8" font-weight="700" letter-spacing="0.06em" fill="#6ee7b7">YOUR GOAL</text>
      <text x="${goalLeftX + 18}" y="${midY + 7}" font-family="Plus Jakarta Sans" font-size="12.5" font-weight="700" fill="#ffffff">${stratEsc(v12Short(goalText, 16))}</text>
      <text x="${goalLeftX + 18}" y="${midY + 19}" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="500" fill="#a1a1aa">${shape.horizon ? stratEsc('by ' + shape.horizon) : 'no horizon recorded'}</text>
    </g>`;
  const svg = `<svg width="${vw}" height="${ch}" viewBox="0 0 ${vw} ${ch}" role="img" aria-label="Map of your ${n} possible path${n === 1 ? '' : 's'} from your current state. Each path is a card on its own line; a path's move sits at the front of its line, and what it needs is a checkpoint after it. Your goal is a separate landmark no line reaches. The same paths are listed below."><g>${bg}</g><g class="v12-lines">${lines}</g><g>${hits}</g><g>${detail}</g><g>${nodes}</g><g>${ends}</g><g>${tags}</g><g>${badge}</g></svg>`;
  return { svg };
}

/* ── Branching view in the card composition (2026-10-17). Used ONLY when the data carries route relations: path.moves[],
   path.branches_from and path.merges_into (today: the illustration map). Same objects as the card view: a PATH card on
   its own corridor, its MOVES after the card, one CONDITION checkpoint ("N of M") after its moves. What is new is where
   a corridor starts and ends: a path starts at the move it is recorded to branch from (or at your state), and a path
   that merges leaves its checkpoint and joins the move it is recorded to feed. Nothing is drawn that is not in those
   fields. Positions come from the relations alone; a merge always lands to the right of the branch it closes. ── */
function v12BuildFlow(shape, cw, ch, selId, focusId, viewW) {
  const paths = shape.paths, n = paths.length;
  const level = shape.level || 'Z0';
  const STATUS = { 'OPEN': '#059669', 'TEST FIRST': '#2563eb', 'NOT YET': '#d97706', 'STOP': '#dc2626' };
  const PILLC = { 'OPEN': '#047857', 'TEST FIRST': '#1d4ed8', 'NOT YET': '#b45309', 'STOP': '#b91c1c' };
  const NEUTRAL = '#a1a1aa', RING = { met: '#059669', partial: '#d97706', unknown: '#a1a1aa', absent: '#dc2626' };
  const T = (x, y, s, o) => { o = o || {}; return `<text x="${x}" y="${y}"${o.a ? ` text-anchor="${o.a}"` : ''} font-family="Plus Jakarta Sans" font-size="${o.s || 10.5}" font-weight="${o.w || 500}" fill="${o.f || '#71717a'}"${o.ls ? ` letter-spacing="${o.ls}"` : ''}${o.po ? ` paint-order="stroke" stroke="#ffffff" stroke-width="${o.po}" stroke-linejoin="round"` : ''} pointer-events="none">${stratEsc(s)}</text>`; };
  const wrap = (t, c) => { const out = ['']; String(t).split(/\s+/).forEach(w => { const cur = out[out.length - 1]; if (!cur) out[out.length - 1] = w; else if ((cur + ' ' + w).length <= c) out[out.length - 1] = cur + ' ' + w; else out.push(w); }); if (out.length > 2) { out.length = 2; out[1] = v12Short(out[1], c - 1) + '…'; } return out; };
  const selPath = selId && paths.some(p => p.id === selId) ? selId : null;
  const selReq = selId && shape.proj.byKey.has(selId) ? shape.proj.byKey.get(selId) : null;
  const lit = id => !selId || (selPath ? selPath === id : (selReq ? selReq.members.includes(id) : true));
  const pIdx = new Map(paths.map((p, i) => [p.id, i]));
  const key = (pid, mid) => `${pid}:${mid}`;
  const focusPath0 = paths.find(p => p.id === focusId && p.status !== 'STOP');

  /* 1. Geometry constants */
  const startX = 40, cardW = 160, cardH = 52, gapIn = 36, moveGap = 66, lockGap = 22, mergeGap = 56;
  const fromStartGap = 76, fromMoveGap = 50;
  const top = 80, laneGap = 82;
  /* at Z2 the chosen path's conditions open under its card, so the lanes below it move down to make room */
  const selIdx = selPath ? pIdx.get(selPath) : -1;
  const condOpen = level === 'Z2' && selIdx >= 0 && paths[selIdx].status !== 'STOP' && (paths[selIdx].requirements || []).some(r => r.applicable !== false);
  const laneY = paths.map((p, i) => top + i * laneGap + (condOpen && i > selIdx ? 84 : 0));
  const midY = Math.round((laneY[0] + laneY[n - 1]) / 2);

  /* 2. Positions from the relations: card after its origin, moves after the card, checkpoint after the moves; a merge
     target is pushed right of the branch's checkpoint, and everything after it (and branching from it) follows. */
  const originOf = p => {
    const b = p.branches_from;
    if (!b || b === 'start') return null;
    const q = pIdx.has(b.path_id) ? paths[pIdx.get(b.path_id)] : null;
    return q && (q.moves || []).some(m => m.id === b.move_id) ? key(b.path_id, b.move_id) : null;
  };
  /* nodes opened in place take room: a move opens into its actions when its path is chosen (Z1+), the checkpoint
     opens into its conditions at Z2. half(k) is half the extra width a node takes. */
  const IS = 64;
  const openMove = (p, m) => {
    if (selPath !== p.id) return null;
    /* the move whose detail is open shows its actions (a done move: the ones logged with it) */
    if (STORE.mapsMoveDetail === key(p.id, m.id) && m.status === 'done' && m.record && (m.record.actions || []).length)
      return m.record.actions.map((a, i) => ({ key: `${p.id}:${m.id}:${i}`, state: a.done ? 'done' : 'next', label: a.label, title: `Action ${i + 1} in “${m.title}”: ${a.label} (${a.done ? 'checked' : 'not checked'})` }));
    if (STORE.mapsMoveDetail && STORE.mapsMoveDetail !== key(p.id, m.id)) return null;
    return level !== 'Z0' && m.status === 'current' && focusPath0 && focusPath0.id === p.id ? v12ActionItems(p.id, m.id) : null;
  };
  const liveOf = p => (p.requirements || []).filter(r => r.applicable !== false);
  const openLock = () => false;   // conditions no longer sit on the lane (they open under the card)
  const half = new Map(), lockHalf = new Map();
  paths.forEach(p => {
    (p.moves || []).forEach(m => { const a = openMove(p, m); half.set(key(p.id, m.id), a && a.length > 1 ? (a.length - 1) * IS / 2 + 8 : 0); });
    lockHalf.set(p.id, openLock(p) ? (liveOf(p).length - 1) * IS / 2 + 8 : 0);
  });
  const minX = new Map();
  let X = new Map(), card = new Map(), lockX = new Map(), guard = 0, changed = true;
  while (changed && guard++ < 40) {
    changed = false; X = new Map(); card = new Map(); lockX = new Map();
    /* parents before children: repeat until every origin is placed */
    let left = paths.slice(), pass = 0;
    while (left.length && pass++ < n + 2) {
      left = left.filter(p => {
        const o = originOf(p);
        if (o && !X.has(o)) return true;
        const ox = o ? X.get(o) + half.get(o) : startX;
        const cx0 = ox + (o ? fromMoveGap : fromStartGap);
        card.set(p.id, cx0);
        let x = cx0 + cardW + gapIn - moveGap, prevH = 0;
        (p.moves || []).forEach(m => { const h = half.get(key(p.id, m.id)); x = Math.max(x + moveGap + prevH + h, minX.get(key(p.id, m.id)) || 0); X.set(key(p.id, m.id), x); prevH = h; });
        lockX.set(p.id, (p.moves || []).length ? x + lockGap + prevH + lockHalf.get(p.id) : cx0 + cardW + gapIn + 6 + lockHalf.get(p.id));
        return false;
      });
    }
    paths.forEach(p => {
      const mi = p.merges_into; if (!mi) return;
      const k = key(mi.path_id, mi.move_id); if (!X.has(k)) return;
      const need = lockX.get(p.id) + lockHalf.get(p.id) + mergeGap + half.get(k);
      if (X.get(k) < need - 0.5) { minX.set(k, need); changed = true; }
    });
  }
  const maxX = Math.max(startX, ...[...X.entries()].map(([k, v]) => v + half.get(k)), ...[...lockX.entries()].map(([k, v]) => v + lockHalf.get(k)));
  /* the goal sits right of everything on the lanes it spans (the two last lanes), so it adds no width when there is room */
  const goalW = 150, goalH = 54;
  const lowEnd = Math.max(startX, ...paths.slice(-2).map(p => (lockX.get(p.id) || 0) + (lockHalf.get(p.id) || 0) + 100));
  const goalX = Math.max(lowEnd, maxX - goalW + 20);
  /* a dotted goal link runs on a rail right of every lane end, so it never crosses a card or a lane */
  const laneEnd = Math.max(...paths.map(p => (lockX.get(p.id) || 0) + 70), goalX + goalW);
  const railX = laneEnd + 26;
  const hasGoalLink = paths.some(p => p.status === 'OPEN' && !p.merges_into);
  const fitW = Math.max(maxX + 110, goalX + goalW + 20, hasGoalLink ? railX + 16 : 0), fitH = laneY[n - 1] + 64;

  const focusPath = paths.find(p => p.id === focusId && p.status !== 'STOP');
  const goalY = Math.round((laneY[n - 2] + laneY[n - 1]) / 2) - goalH / 2;
  const posOf = (k, side) => k ? [X.get(k) + (side || 0) * (half.get(k) || 0), laneY[pIdx.get(k.split(':')[0])]] : [startX, laneY[0]];
  /* connectors: from your state, one soft S (as in the card view); from a move, a straight drop with round corners */
  const sCurve = (a, b) => { const dx = (b[0] - a[0]) * 0.55; return `M ${a[0]} ${a[1]} C ${a[0] + dx} ${a[1]} ${b[0] - dx} ${b[1]} ${b[0]} ${b[1]}`; };
  const drop = (a, xv, y1, xEnd) => { const r = Math.min(22, Math.abs(y1 - a[1]) / 2, (xEnd - xv) * 0.8, (xv - a[0]) * 0.9), sg = y1 > a[1] ? 1 : -1; return ` L ${xv - r} ${a[1]} Q ${xv} ${a[1]} ${xv} ${a[1] + sg * r} L ${xv} ${y1 - sg * r} Q ${xv} ${y1} ${xv + r} ${y1} L ${xEnd} ${y1}`; };

  const noteText = selPath && level === 'Z2' ? 'What this path needs, one by one. Conditions are checked by evidence, not by doing a move.'
    : 'Example data · each branch and merge is written in this example’s data, not steps, dates or a sure way to your goal.';
  let lines = '', hits = '', nodes = '', tags = '', ends = '', badge = '', detail = '';
  paths.forEach((p, pi) => {
    const ly = laneY[pi], ms = p.moves || [], stop = p.status === 'STOP';
    const isFocus = focusPath && focusPath.id === p.id, quiet = !lit(p.id), pressed = selPath === p.id;
    const hot = isFocus || pressed || (selReq && lit(p.id));
    const color = hot ? (STATUS[p.status] || NEUTRAL) : NEUTRAL;
    const op = quiet ? 0.35 : hot ? 1 : 0.75;
    const o = originOf(p), O = posOf(o, 1), cx0 = card.get(p.id), lx = lockX.get(p.id), lh = lockHalf.get(p.id);
    const live = (p.requirements || []).filter(r => r.applicable !== false);
    const met = live.filter(r => r.satisfaction === 'PRESENT').length;
    /* corridor: origin → card → moves → checkpoint (→ merge) */
    /* from your state: ONE trunk (every first-level path drops along the same line) that peels off with a round corner */
    let d = !o ? (Math.abs(O[1] - ly) < 0.5 ? `M ${O[0]} ${O[1]} L ${cx0} ${ly}` : `M ${O[0]} ${O[1]}${drop(O, O[0] + 40, ly, cx0)}`)
      : (Math.abs(O[1] - ly) < 0.5 ? `M ${O[0]} ${O[1]} L ${cx0} ${ly}` : `M ${O[0]} ${O[1]}${drop(O, O[0] + 32, ly, cx0)}`);
    const endX = stop ? cx0 + cardW + 40 : lx;
    d += ` L ${endX} ${ly}`;
    const mi = p.merges_into && X.has(key(p.merges_into.path_id, p.merges_into.move_id)) ? posOf(key(p.merges_into.path_id, p.merges_into.move_id), -1) : null;
    let tail = '';
    if (mi) d += `${drop([lx, ly], mi[0] - 26, mi[1], mi[0])}`;
    else if (!stop) tail = `<path d="M ${lx} ${ly} L ${Math.max(lx, Math.min(goalX - 40, lx + 70))} ${ly}" stroke="${color}" stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round" fill="none" opacity="0.7"/>`;
    /* an OPEN path points toward the goal with a dotted line (it enters the goal card from above) */
    if (!mi && p.status === 'OPEN') {
      const sx0 = Math.max(lx, Math.min(goalX - 40, lx + 70));
      const gm = goalY + goalH / 2, r = Math.min(18, Math.abs(gm - ly) / 2), sg = gm > ly ? 1 : -1;
      tail += `<path class="v12-goal-link" data-v12-goal-link="${p.id}" d="M ${sx0} ${ly} L ${railX - r} ${ly} Q ${railX} ${ly} ${railX} ${ly + sg * r} L ${railX} ${gm - sg * r} Q ${railX} ${gm} ${railX - r} ${gm} L ${goalX + goalW + 3} ${gm}" stroke="${STATUS['OPEN']}" stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round" fill="none" opacity="${quiet ? 0.35 : 0.8}"><title>May lead toward your goal: the evidence supports this path (OPEN). A possible direction, not a sure way.</title></path>`;
    }
    /* travelled vs not yet: past the first move not done, the line is dashed (locked moves are not a road yet) */
    const fo = ms.findIndex(q => q.status !== 'done');
    let ahead = '';
    if (!stop && fo >= 0 && fo < ms.length - 1) {
      const ax = X.get(key(p.id, ms[fo].id)) + half.get(key(p.id, ms[fo].id)) + 12, bx = endX;
      if (bx > ax) ahead = `<path class="v12-ahead" d="M ${ax} ${ly} L ${bx} ${ly}" stroke="#ffffff" stroke-width="${pressed ? 5 : 4}" fill="none"/><path class="v12-ahead" d="M ${ax} ${ly} L ${bx} ${ly}" stroke="${NEUTRAL}" stroke-width="2" stroke-dasharray="4 4" fill="none" opacity="0.8"/>`;
    }
    lines += `<g class="v12-route${pressed ? ' is-sel' : ''}${quiet ? ' is-quiet' : ''}" data-v12-route="${p.id}" opacity="${op}"><path class="v12-line v12-corridor" data-v12-path="${p.id}" d="${d}" stroke="${color}" stroke-width="${pressed ? 3.5 : 2.5}" fill="none" stroke-linecap="round" stroke-linejoin="round"${stop ? ' stroke-dasharray="5 5"' : ''}/>${ahead}${tail}</g>`;
    hits += `<path d="${d}" stroke="transparent" stroke-width="16" fill="none" style="cursor:pointer" data-v12-hit="${p.id}" onclick="v12Tap('${p.id}')" onmouseenter="v12RouteHover('${p.id}',true)" onmouseleave="v12RouteHover('${p.id}',false)">${o && p.branches_from.when ? `<title>${stratEsc(p.title + ' · ' + p.branches_from.when)}</title>` : ''}</path>`;
    /* the branch's note (what opens it) shows when the path is chosen; at the overview it is in the line's title */
    if (o && pressed && p.branches_from.when && Math.abs(O[1] - ly) > 0.5) {
      const wl = wrap(p.branches_from.when, 14), my = (O[1] + ly) / 2 - (wl.length - 1) * 5;
      detail += wl.map((l, k) => T(O[0] + 39, my + 3 + k * 10, l, { s: 8.5, w: 500, f: quiet ? '#d4d4d8' : '#71717a', po: 3.5 })).join('');
    }

    /* the card */
    const full = `${p.title} · ${v12StatusWord(p)}${isFocus ? ' · in focus' : ''}`;
    const statusLine = [p.status, isFocus ? 'IN FOCUS' : '', p.stop_source ? (p.stop_source === 'you' ? 'by you' : 'by the evidence') : ''].filter(Boolean).join(' · ');
    tags += `<g class="v12-lane-label v12-card${quiet ? ' is-quiet' : ''}${isFocus ? ' is-focus' : ''}" data-v12-path="${p.id}" role="button" tabindex="0" aria-pressed="${pressed}" aria-label="${stratEsc(full)}" onkeydown="v12Key(event,'${p.id}')" onclick="v12Tap('${p.id}')" onmouseenter="v12RouteHover('${p.id}',true)" onmouseleave="v12RouteHover('${p.id}',false)" style="cursor:pointer" opacity="${quiet ? 0.5 : 1}"><title>${stratEsc(full)}</title>`
      + (isFocus ? `<rect x="${cx0 - 5}" y="${ly - cardH / 2 - 5}" width="${cardW + 10}" height="${cardH + 10}" rx="16" fill="none" stroke="#a7f3d0" stroke-width="4"/>` : '')
      + `<rect class="v12-tag-hit" x="${cx0}" y="${ly - cardH / 2}" width="${cardW}" height="${cardH}" rx="12" fill="#ffffff" stroke="${pressed ? '#18181b' : '#e4e4e7'}" stroke-width="${pressed ? 2 : 1.2}" pointer-events="all"/>`
      + `<circle cx="${cx0 + 15}" cy="${ly - 13}" r="4.5" fill="${STATUS[p.status] || NEUTRAL}"/>`
      + wrap(p.title, 19).map((l, k) => `<text${k ? '' : ' class="v12-lt"'} x="${cx0 + 26}" y="${ly - 9 + k * 13}" font-family="Plus Jakarta Sans" font-size="11" font-weight="${pressed || isFocus ? 700 : 600}" fill="#18181b" pointer-events="none">${stratEsc(l)}</text>`).join('')
      + `<text x="${cx0 + 26}" y="${ly + 20}" font-family="Plus Jakarta Sans" font-size="8" font-weight="700" letter-spacing="0.05em" fill="${PILLC[p.status] || '#52525b'}" pointer-events="none">${stratEsc(v12Short(statusLine.toUpperCase(), 22))}</text>`
      /* what the path needs: a chip on the card, the only lock on the map (a condition is about the whole path) */
      + (live.length && !stop ? `<g class="v12-station v12-cluster${condOpen && pressed ? ' v12-cluster-open' : ''}" data-v12-cluster="${live.length}"${pressed ? ' role="button" tabindex="0"' : ''} aria-label="${stratEsc(`What it needs · ${met} of ${live.length} confirmed`)}" onclick="event.stopPropagation();${condOpen && pressed ? "v12SetLevel('Z1')" : `v12ExpandRoute('${p.id}')`}" style="cursor:pointer"><title>${stratEsc(`What this path needs · ${met} of ${live.length} confirmed — ${condOpen && pressed ? 'hide' : 'show each one'}`)}</title><rect x="${cx0 + cardW - 46}" y="${ly + 10}" width="40" height="15" rx="7.5" fill="#fafafa" stroke="#a1a1aa" stroke-dasharray="2.5 2"/><path d="M ${cx0 + cardW - 40} ${ly + 17} v -1 a 2 2 0 0 1 4 0 v 1 M ${cx0 + cardW - 40.8} ${ly + 17} h 5.6 v 4 h -5.6 z" stroke="#71717a" stroke-width="1" fill="none"/>${T(cx0 + cardW - 20, ly + 21, `${met}/${live.length}`, { a: 'middle', s: 8, w: 700, f: '#52525b' })}</g>` : '')
      + '</g>';

    if (stop) {
      const tx = endX;
      ends += `<g class="v12-stop-end" data-v12-route="${p.id}" onclick="v12Tap('${p.id}')" style="cursor:pointer" opacity="${quiet ? 0.4 : 0.85}"><title>${stratEsc(p.title)} · Stopped ${p.stop_source === 'you' ? 'by you' : 'by the evidence'}</title><circle cx="${tx}" cy="${ly}" r="9" fill="#ffffff" stroke="#dc2626" stroke-width="2"/><path d="M ${tx - 3} ${ly - 3} L ${tx + 3} ${ly + 3} M ${tx + 3} ${ly - 3} L ${tx - 3} ${ly + 3}" stroke="#dc2626" stroke-width="1.8" stroke-linecap="round"/>${T(tx + 15, ly + 3.5, 'Stopped', { s: 9.5, w: 700, f: '#b91c1c', po: 3 })}</g>`;
      return;
    }
    /* moves: done ✓ · current (dark ring, "Current move") · not started · waiting (dashed, locked: as in Moves) */
    const showLabels = selPath ? pressed : isFocus;
    ms.forEach((m, i) => {
      const x = X.get(key(p.id, m.id));
      const acts = openMove(p, m);
      if (acts && acts.length) {
        /* the move, opened: its actions inside it */
        const cap = v12Capsule('move', { cx: x, y: ly, items: acts, spacing: IS, color, wrapAt: 11 });
        const isDone = m.status === 'done';
        nodes += `<g class="v12-station v12-flow-move v12-move-open" data-v12-flow-move="${p.id}:${m.id}" data-state="${isDone ? 'done' : 'current'}" data-actions="${acts.length}" role="button" tabindex="0" aria-label="${stratEsc(`Move ${i + 1}: ${m.title}`)}" onclick="event.stopPropagation();v12OpenMove('${p.id}','${m.id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();v12OpenMove('${p.id}','${m.id}')}" style="cursor:pointer"><title>${stratEsc(`Move ${i + 1} on ${p.title}: ${m.title} · ${acts.length} action${acts.length === 1 ? '' : 's'} inside`)}</title>${cap.svg}</g>`;
        if (isDone) { const bt = 'Done', bw = Math.round(bt.length * 4.9 + 22); detail += `<g aria-hidden="true"><rect x="${x - bw / 2}" y="${ly - 46}" width="${bw}" height="18" rx="9" fill="#ecfdf5" stroke="#a7f3d0"/><text x="${x}" y="${ly - 34}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" fill="#047857">${stratEsc(bt)}</text></g>`; return; }
        const bt = `Current move · ${v12Short(m.title, 30)}`, bw = Math.round(bt.length * 4.9 + 22);
        badge = `<g class="v12-here-badge" data-v12-marker="move" aria-hidden="true"><path d="M ${x} ${ly - 28} L ${x} ${ly - 16}" stroke="#047857" stroke-width="1.5"/><rect x="${x - bw / 2}" y="${ly - 46}" width="${bw}" height="18" rx="9" fill="#047857"/><text x="${x}" y="${ly - 34}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" fill="#ffffff">${stratEsc(bt)}</text></g>`;
        return;
      }
      /* order is a move's own rule: only the first move not done can be worked on; every move after it is locked */
      const firstOpen = ms.findIndex(q => q.status !== 'done');
      const st = m.status === 'done' ? 'done' : p.waiting ? 'waiting' : i > firstOpen ? 'locked' : m.status === 'current' && isFocus ? 'current' : 'next';
      const word = { done: 'done', current: 'current move', waiting: 'waiting on what this path needs', locked: 'locked until the move before it is done', next: 'not started' }[st];
      let g = `<circle cx="${x}" cy="${ly}" r="11" fill="#ffffff"/>`;
      const logged = m.record && (m.record.outcome || (m.record.evidence || []).length);
      if (st === 'done') g += `<circle cx="${x}" cy="${ly}" r="8" fill="${color}"/><path d="M ${x - 3.2} ${ly + 0.2} l 2.2 2.2 l 4.2 -4.6" stroke="#ffffff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`
        + (logged ? `<circle class="v12-logged" cx="${x + 7}" cy="${ly - 7}" r="3.4" fill="#1d4ed8" stroke="#ffffff" stroke-width="1.5"/>` : '');
      else if (st === 'current') g += `<circle cx="${x}" cy="${ly}" r="8" fill="#ffffff" stroke="#18181b" stroke-width="3"/><circle cx="${x}" cy="${ly}" r="2.4" fill="#18181b"/>`;
      else if (st === 'locked') g += `<circle cx="${x}" cy="${ly}" r="7" fill="#ffffff" stroke="#d4d4d8" stroke-width="2.2"/>`;
      else if (st === 'waiting') g += `<circle cx="${x}" cy="${ly}" r="7" fill="#ffffff" stroke="#a1a1aa" stroke-width="1.8" stroke-dasharray="2.5 2"/>`;
      else g += `<circle cx="${x}" cy="${ly}" r="7.5" fill="#ffffff" stroke="${color}" stroke-width="2.5"/>`;
      nodes += `<g class="v12-station v12-flow-move${STORE.mapsMoveDetail === key(p.id, m.id) ? ' is-sel' : ''}" data-v12-flow-move="${p.id}:${m.id}" data-state="${st}" role="button" tabindex="0" aria-label="${stratEsc(`Move ${i + 1}: ${m.title}, ${word}`)}" onclick="event.stopPropagation();v12OpenMove('${p.id}','${m.id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();v12OpenMove('${p.id}','${m.id}')}" style="cursor:pointer" opacity="${quiet ? 0.4 : 1}"><title>${stratEsc(`Move ${i + 1} on ${p.title}: ${m.title} (${word}${logged ? ', outcome or evidence on record' : ''}). Open its detail`)}</title>${STORE.mapsMoveDetail === key(p.id, m.id) ? `<circle cx="${x}" cy="${ly}" r="13" fill="none" stroke="#18181b" stroke-width="1.5"/>` : ''}${g}`
        + (showLabels ? wrap(m.title, 11).map((l, k) => T(x, ly + 24 + k * 10.5, l, { a: 'middle', s: 8.5, w: st === 'current' ? 700 : 500, f: st === 'current' ? '#18181b' : st === 'locked' || st === 'waiting' ? '#a1a1aa' : '#52525b', po: 3.5 })).join('') : '')
        + '</g>';
      if (st === 'current') badge = `<g class="v12-here-badge" data-v12-marker="move" aria-hidden="true"><path d="M ${x} ${ly - 24} L ${x} ${ly - 12}" stroke="#047857" stroke-width="1.5"/><rect x="${x - 42}" y="${ly - 42}" width="84" height="18" rx="9" fill="#047857"/><text x="${x}" y="${ly - 30}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" fill="#ffffff">Current move</text></g>`;
    });
    /* Z2: what the path needs, opened under its card (about the whole path, not a step at the end of it) */
    if (pressed && condOpen) {
      const cxm = cx0 + cardW / 2, cy = ly + cardH / 2 + 44;
      const cap = v12Capsule('condition', { cx: cxm, y: cy, items: v12ConditionItems(live), spacing: IS, wrapAt: 11 });
      detail += `<g class="v12-conditions-open" data-v12-conditions="${p.id}"><path d="M ${cxm} ${ly + cardH / 2} L ${cxm} ${cy - 30}" stroke="#d4d4d8" stroke-width="1.5" stroke-dasharray="2 3"/>${T(cxm, cy - 20, `What it needs · ${met} of ${live.length} confirmed`, { a: 'middle', s: 8.5, w: 700, f: '#52525b', po: 3.5 })}${cap.svg}</g>`;
    }
  });

  /* start and goal: the goal stands alone */
  ends += `<circle cx="${startX}" cy="${laneY[0]}" r="15" fill="#ffffff"/><circle cx="${startX}" cy="${laneY[0]}" r="13" fill="#18181b"/><circle cx="${startX}" cy="${laneY[0]}" r="4.5" fill="#ffffff"/>`
    + T(startX, laneY[0] + 30, 'YOUR STATE', { a: 'middle', w: 700, s: 10, f: '#18181b', po: 3 }) + T(startX, laneY[0] + 42, v12Short(v12NowText(shape), 16), { a: 'middle', s: 9, f: '#71717a', po: 3 });
  const goalText = v12GoalText(shape).replace('Goal · ', ''), gy = goalY;
  ends += `<g class="v12-goal-node" aria-label="Goal: ${stratEsc(goalText)}. A separate landmark; only open paths point toward it, with a dotted line (possible, not certain)."><rect class="v12-goal-bg" x="${goalX}" y="${gy}" width="${goalW}" height="${goalH}" rx="14" fill="#18181b"/><text x="${goalX + 18}" y="${gy + 19}" font-family="Plus Jakarta Sans" font-size="8" font-weight="700" letter-spacing="0.06em" fill="#6ee7b7">YOUR GOAL</text><text x="${goalX + 18}" y="${gy + 34}" font-family="Plus Jakarta Sans" font-size="12.5" font-weight="700" fill="#ffffff">${stratEsc(v12Short(goalText, 16))}</text><text x="${goalX + 18}" y="${gy + 46}" font-family="Plus Jakarta Sans" font-size="8.5" fill="#a1a1aa">${shape.horizon ? stratEsc('by ' + shape.horizon) : ''}</text></g>`;
  const bg = T(16, 22, noteText, { s: 10.5, f: '#71717a' });
  const svg = `<svg width="${viewW || cw}" height="${ch}" viewBox="0 0 ${fitW} ${fitH}" data-fit-w="${fitW}" data-fit-h="${fitH}" role="img" aria-label="Example map with ${n} paths. Each path is a card on its own line; branches start at the move on record and merges join the move on record. Your goal is a separate landmark no line reaches."><g>${bg}</g><g class="v12-lines">${lines}</g><g>${hits}</g><g>${detail}</g><g>${nodes}</g><g>${ends}</g><g>${tags}</g><g>${badge}</g></svg>`;
  return { svg };
}
/* Hover: the whole line thickens with its name */
function v12RouteHover(id, on) {
  document.querySelectorAll(`.v12-route[data-v12-route="${id}"]`).forEach(g => g.classList.toggle('is-hover', on));
}
/* The projection for what the canvas shows (the same capped set the canvas draws) */
function v12ProjectionNow(snap) {
  const s = snap || V11_ENGINE.snapshot();
  const stored = (STORE.mapsSelBy || {})[v11MapKey()];
  return v12Project(presentPaths(s.paths, { pinned: [stored, (mapsActive(s) || {}).id] }).visible);
}
function v12SharedById(id, snap) { return id && String(id).startsWith('req:') ? v12ProjectionNow(snap).byKey.get(id) || null : null; }

/* A requirement or next-move marker on the map. It is DECORATIVE: it shows a state, it is not a control. Clicking a
   path is done through its callout (a native button with a name, aria-pressed and keyboard activation), so no marker
   pretends to be a button without a keyboard route. The state it shows is also in the callout and in Readiness. */
function v12NodeMarker(pathId, cx, cy, r, n) {
  const ns = V12_NS[n.state] || V12_NS.unknown;
  const dash = ns.dash ? ` stroke-dasharray="${ns.dash}"` : '';
  const icon = V12_ICONS[n.type] || V12_ICONS.unknown;
  let g = `<title>${stratEsc(ns.word)}: ${stratEsc(n.title || n.label)}</title>`;
  g += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${ns.fill}" stroke="${ns.stroke}" stroke-width="${ns.sw}"${dash}/>`;
  g += `<svg x="${cx - r * 0.575}" y="${cy - r * 0.575}" width="${r * 1.15}" height="${r * 1.15}" viewBox="0 0 24 24" fill="none" stroke="${ns.icon}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="pointer-events:none">${icon}</svg>`;
  return `<g class="v12-node" data-v12-node="${pathId}" aria-hidden="true" pointer-events="none">${g}</g>`;
}

function mapsSelect(id, opts) {
  const o = opts || {};
  const snap = V11_ENGINE.snapshot();
  /* a move's detail is opened only by choosing that move; any other pick closes it */
  STORE.mapsMoveDetail = o.move && id ? `${id}:${o.move}` : null;
  const ok = id && (id === 'start' || id === 'goal' || snap.paths.some(p => p.id === id) || !!v12SharedById(id, snap));
  const prevChoice = mapsFocusState(snap).choice;
  mapsSetSel(ok ? id : null, false);
  if (!ok || !snap.paths.some(p => p.id === id)) STORE.mapsLevel = ok ? STORE.mapsLevel : 'Z0';
  /* a newly chosen path always opens at Path level; choosing the same path again keeps its level */
  else if (!V12_LEVELS.includes(STORE.mapsLevel) || STORE.mapsLevel === 'Z0' || prevChoice !== id) STORE.mapsLevel = 'Z1';
  /* A pick is a request to see the path: if the inspector was closed in Explore, it opens on that path */
  if (ok && STORE.mapsInspectorClosed && mapsViewNow() === 'landscape') { STORE.mapsInspectorClosed = false; STORE.restoreFocus = '#mp-title'; renderScreen('maps'); return; }
  /* Repaint in place when the lens is on screen (the v12 canvas, or the legacy strategy canvas if one is mounted).
     Only a missing panel, or no canvas at all, falls back to a full render. The old guard looked only for the legacy
     canvas, which the v12 Maps screen never mounts, so every pick re-rendered the page and dropped keyboard focus. */
  const el = document.querySelector('.strat[data-key="full"]');
  const panel = document.getElementById('mp-panel');
  const v12Host = document.getElementById('v12-map');
  if (!panel || (!v12Host && !el)) { renderScreen('maps'); return; }
  const a = document.activeElement;
  const hadCard = a && a.classList && a.classList.contains('mp-card');
  const hadNode = a && a.closest && a.closest('[data-node]');
  const st = mapsFocusState(snap);
  const sel = st.shown;   // the path the panel shows: focus, announcements and scrolling follow it
  const pres = presentSnapshotPaths(snap.paths, { pinned: [st.shown, st.active] });
  const more = document.getElementById('mp-more');
  panel.innerHTML = mapsPanelHtml(snap, st.shown, st.preview);
  const list = document.getElementById('mp-list');
  if (list) list.innerHTML = mapsMoreHtml(snap, pres, st.choice, !!(more && more.open));
  /* v12 map: the canvas redraws from the same selection; the strat pan/zoom canvas stays
     for the other scenes (diagnosis, split views) that still embed it. */
  const v12 = document.getElementById('v12-map');
  if (v12) {
    const hadMap = !!(a && a.closest && a.closest('.v12-map'));
    v12RenderInto(v12, snap);
    if (sel && hadMap) { const c = v12.querySelector(`.v12-lane-label[data-v12-path="${sel}"], .v12-shared[data-v12-shared="${sel}"]`); if (c) c.focus({ preventScroll: true }); }
  }
  else if (el && typeof stratReveal === 'function') stratReveal(el, sel);   /* the legacy strategy canvas is not mounted on the v11 Maps screen */
  if (hadCard && sel) { const c = document.querySelector(`.mp-card[data-path="${sel}"]`); if (c) c.focus({ preventScroll: true }); }
  else if (hadNode && sel && el) { const n = el.querySelector(`[data-node="${sel}"]`); if (n) n.focus({ preventScroll: true }); }
  const p = snap.paths.find(x => x.id === sel);
  const say = document.getElementById('mp-status');
  if (say) say.textContent = p ? `${p.title}, ${p.status_display}. Details are in the panel.` : (sel === 'start' ? 'Here. Details are in the panel.' : sel === 'goal' ? 'Your goal. Details are in the panel.' : 'Selection cleared.');
  // Below 1101px the panel sits under the map: bring it into view when something was chosen
  if (o.scroll && sel && !window.matchMedia('(min-width: 1101px)').matches) panel.scrollIntoView({ block: 'nearest', behavior: mapsReduced() ? 'auto' : 'smooth' });
}
/* Escape clears a chosen path in Overview, and the default comes back. An open drawer keeps its own Escape. */
(function initMapsEscape() {
  if (window.__mapsEscape) return;
  window.__mapsEscape = true;
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || e.defaultPrevented) return;
    if (!document.getElementById('mp-panel') || mapsViewNow() !== 'landscape') return;
    const drawer = document.getElementById('why-drawer');
    if (drawer && drawer.classList.contains('open')) return;
    if (!(STORE.mapsSelBy || {})[v11MapKey()]) return;
    mapsSelect(null);
  });
})();
/* Keep a selected node inside the visible part of a zoomed or panned map */
function stratReveal(el, id) {
  const s = el._strat;
  const n = s && s.g.nodes.find(x => x.id === id);
  if (!n) return;
  const k = s.fitK * s.st.rel, hw = s.W / 2 / k, hh = s.H / 2 / k;
  if (n.x < s.st.cx - hw + 110 || n.x > s.st.cx + hw - 110 || n.y < s.st.cy - hh + 40 || n.y > s.st.cy + hh - 40) {
    s.st.cx = n.x; s.st.cy = n.y; stratClampView(s); el._stratApply();
  }
}
/* "+N more possibilities" on the map opens the list that holds them */
function mapsOpenMore() {
  const d = document.getElementById('mp-more');
  if (!d) return;
  d.open = true;
  d.scrollIntoView({ block: 'center', behavior: mapsReduced() ? 'auto' : 'smooth' });
  const sm = d.querySelector('summary');
  if (sm) sm.focus({ preventScroll: true });
}
/* Cross-destination hand-offs that carry the path with them */
function openMapsAt(id) {
  if (id) mapsSetSel(id, false);
  goDestination('maps');
}
function openReadiness(id) {
  if (id) mapsSetSel(id, false);
  if (activeDestination(STORE.currentScreen) === 'maps') { setMapsView('readiness'); return; }
  STORE.mapsView = 'readiness';
  STORE.restoreFocus = '.rd-path-item.active';
  renderScreen('maps');
}
function openTalkAbout(id) {
  const p = V11_ENGINE.snapshot().paths.find(x => x.id === id);
  STORE.talkAboutNext = p ? { id: p.id, title: p.title } : null;
  goDestination('talk');
}

/* Zero paths: not an empty canvas. A calm, honest answer from the engine's own state, at the depth of each lens:
   Landscape — the empty stretch and what prevents a path · Overview — plus what would need to change ·
   Readiness — what we know, what prevents a path, what would need to change. */
/* A zero-path result is a valid answer, not an error. What we may say about WHY is limited to what the snapshot
   actually carries: an explicit snap.zero_reason (INSUFFICIENT_INFORMATION · NO_APPLICABLE_PATH · EVIDENCE_CONFLICT ·
   EVALUATION_UNAVAILABLE), else the state's own blocking sentence, else "nothing has been described yet" when there is
   no state at all. With none of those, we say no reason is on record. We never guess one. */
function mapsZeroReason(snap) {
  const st = snap.state;
  const z = snap.zero || null;   /* MVP adapter seam: the engine's zero arrives as { kind, detail } (live-vm snapshotFromPayloads) */
  const kind = (z && z.kind) || snap.zero_reason || null;
  const own = (z && z.detail) || (st && st.blocking ? st.blocking : null);
  const T = {
    INSUFFICIENT_INFORMATION: { title: 'There is not enough information to assess a path yet.', body: own || 'What is on record is not enough to tell whether any direction applies.' },
    NO_APPLICABLE_PATH: { title: 'No path applies to what is on record.', body: own || 'The directions that were evaluated do not apply to your current situation.' },
    EVIDENCE_CONFLICT: { title: 'The evidence conflicts, so no path can be shown yet.', body: own || 'Some of what is on record contradicts the rest. It has to be resolved before a path can be assessed.' },
    EVALUATION_UNAVAILABLE: { title: 'We could not evaluate your map.', body: own || 'The evaluation did not complete, so this is not a result about your business. Try again, or go back to your State.' },
    LEGACY_ARTIFACT: { title: 'This map needs a fresh look.', body: own || 'This map was made before the current method, so it carries no path result. Run a new check-in and the map is rebuilt from your evidence.' }
  };
  if (kind && T[kind]) return Object.assign({ kind, source: 'engine' }, T[kind]);
  /* (The prototype's unevaluated custom maps have no MVP equivalent: every MVP map is engine-evaluated.) */
  if (!st) return { kind: 'INSUFFICIENT_INFORMATION', source: 'derived', title: 'There is not enough information to assess a path yet.', body: 'Nothing has been described yet, so there is nothing for a path to stand on. Nothing is made up to fill the map.' };
  if (own) return { kind: 'UNSPECIFIED', source: 'engine', title: 'No path is shown right now.', body: own };
  return { kind: 'UNSPECIFIED', source: 'none', title: 'No path is shown right now.', body: 'No reason for this is on record, so we do not want to guess one. Your State and Talk show what is known.' };
}
/* Zero paths: not an empty canvas. A calm, honest answer at the depth of each lens:
   Landscape — the empty stretch and the reason · Overview — plus what would need to change ·
   Readiness — what we know, the reason, and what would need to change. */
/* A custom map the prototype has not evaluated: one compact card (status, headline, one line, the next action), with what
   the person shared folded underneath. No HERE→GOAL strip, no lenses, no path or route: nothing was evaluated. */
function screenMapsZero(snap, view) {
  view = view || mapsViewNow();
  const st = snap.state;
  const why = mapsZeroReason(snap);
  const facts = st && st.why_we_think_so && st.why_we_think_so.length ? `<ul class="dest-list">${st.why_we_think_so.map(t => `<li>${stratEsc(t)}</li>`).join('')}</ul>` : `<p class="mp-p">${st ? 'Not much is on record yet.' : 'Nothing is on record yet.'}</p>`;
  const change = st && st.uncertain && st.uncertain.length
    ? `<ul class="dest-list">${st.uncertain.map(t => `<li>${stratEsc(t)}</li>`).join('')}</ul><p class="mp-fine">Not known is not no. Finding out is a move.</p>`
    : why.kind === 'EVALUATION_UNAVAILABLE' ? '<p class="mp-p">Nothing about your situation has changed. Try again, or open State to see what is on record.</p>'
    : `<p class="mp-p">${st ? 'A new answer, a check-in, or a correction in Talk may change this. What it changes is decided when the map is evaluated again.' : 'Telling Talk where you are and where you want to be gives the map something to stand on.'}</p>`;
  const move = snap.nextmove;
  const nowSet = snap.goal.now && snap.goal.now !== 'Not set yet';
  const goalSet = snap.goal.text && snap.goal.text !== 'Not set yet';
  const strip = `
      <svg class="mp-zero-strip" viewBox="0 0 680 92" role="img" aria-label="From here, across an empty stretch, to your goal. No path is shown in between.">
        <circle cx="40" cy="46" r="14" fill="#18181b"/><circle cx="40" cy="46" r="4.5" fill="#fff"/>
        <text x="64" y="42" font-family="Plus Jakarta Sans" font-size="11" font-weight="700" fill="#18181b">HERE</text>
        <text x="64" y="58" font-family="Source Sans 3" font-size="12" fill="#52525b">${nowSet ? stratEsc(snap.goal.now) + ' a month' : 'Nothing measured yet'}</text>
        <line x1="190" y1="46" x2="480" y2="46" stroke="#a1a1aa" stroke-width="2" stroke-dasharray="2 7" stroke-linecap="round"/>
        <text x="335" y="36" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="10.5" font-weight="700" letter-spacing="0.08em" fill="#71717a">NO PATH SHOWN</text>
        <rect x="520" y="22" width="140" height="48" rx="12" fill="#18181b"/>
        <text x="536" y="41" font-family="Plus Jakarta Sans" font-size="8.5" font-weight="700" letter-spacing="0.06em" fill="#6ee7b7">YOUR GOAL</text>
        <text x="536" y="58" font-family="Plus Jakarta Sans" font-size="12" font-weight="700" fill="#fff">${stratEsc(goalSet ? snap.goal.text.replace(' a month', '') : 'Not set yet')}</text>
      </svg>`;
  const sec = (label, body) => `<section class="dest-focus"><div class="section-meta-label mb-0">${label}</div>${body}</section>`;
  const knowSec = sec('WHAT WE KNOW', facts);
  const reasonSec = sec('WHY NO PATH IS SHOWN', `<h2 class="serif-heading mp-zero-h">${stratEsc(why.title)}</h2><p class="mp-p">${stratEsc(why.body)}</p>`);
  const changeSec = sec('WHAT MAY CHANGE THIS', change);
  const lead = {
    landscape: 'No path is shown right now. That is a valid answer, not an error.',
    overview: 'No path is shown right now, so there is nothing to compare. Here is what we can say about why.',
    readiness: 'No path is shown right now, so there are no requirements to inspect. Here is what we can say about why.'
  }[view];
  const parts = view === 'landscape' ? [strip, reasonSec, changeSec] : [knowSec, reasonSec, changeSec];
  const failed = why.kind === 'EVALUATION_UNAVAILABLE';
  const content = `
  <div class="mp-page">
    <div class="mp-head">
      ${v11PageHead({ dest: 'Maps', title: failed ? 'We could not evaluate your map.' : 'No path is shown yet.', lead })}
      ${renderMapsLocalBar('')}
    </div>
    <div class="mp-zero">
      ${parts.join('')}
      <div class="card-dark dest-action">
        <div class="section-meta-label on-dark mb-0">${failed ? 'WHAT YOU CAN DO' : move ? 'TALK FIRST, OR TAKE THE NEXT MOVE' : 'THE WAY IN'}</div>
        <h2>${failed ? 'Go back to your State, or try again from Talk.' : move ? stratEsc(move.title) : 'Start with a Talk about where you are and where you want to be.'}</h2>
        <div class="mp-zero-actions">
          <button type="button" class="btn-primary dest-cta" onclick="goDestination('${failed ? 'state' : 'talk'}')">${failed ? 'Open State →' : 'Talk about this →'}</button>
      ${move && !failed ? `<button type="button" class="mp-link-dark" onclick="goDestination('moves')">Go to your move →</button>` : ''}
        </div>
      </div>
    </div>
  </div>`;
  return renderAppShell('maps', MAPS_VIEW_LABEL[view], content);
}
/* Readiness: the deepest lens. Same snapshot, read as words and counts — never bars, never %.
   Landscape/Overview say which paths exist and how each stands; Readiness says everything one path needs. */
/* The one sentence a reader needs first: what holds this path back, or why it stands. From the record only. */
function rdKeyFinding(p) {
  const live = p.requirements.filter(r => r.applicable !== false);
  const absent = live.find(r => r.satisfaction === 'ABSENT');
  const unknown = live.find(r => r.satisfaction === 'UNKNOWN');
  const partial = live.find(r => r.satisfaction === 'PARTIAL');
  if (p.stop_source === 'you') return 'You paused this path. Nothing on it was lost.';
  if (absent) return `Not in place yet: ${absent.label}.`;
  if (unknown) return `Not known yet: ${unknown.label}. Not known is not the same as no.`;
  if (partial) return `Partly shown: ${partial.label}.`;
  return (MAPS_STATUS_MEANING[p.status_display] || MAPS_STATUS_MEANING['NOT YET']).long;
}
/* Readiness detail for one path. Reading order: what it is → can it be pursued (status) → why → what needs attention →
   a valid action, if any. Everything is read from the snapshot: status, requirement states, the engine's narrative,
   guidance and conflict notes when the record carries them. Nothing is ranked, scored or invented; a field the record
   does not carry is left out. OPEN, IN FOCUS and the current move stay three different things. */
const RD_ATTENTION = ['ABSENT', 'UNKNOWN', 'PARTIAL'];
const rdQ = s => stratEsc(String(s || '').replace(/[.\s]+$/, ''));   /* a quoted title without its own full stop */
function rdStatusWhy(p) {
  if (p.stop_source === 'you') return 'You paused this path. Nothing on it was lost.';
  if (p.status_display === 'STOP') return MAPS_STATUS_MEANING.STOP.long;
  return (p.narrative && p.narrative.opening) || (MAPS_STATUS_MEANING[p.status_display] || MAPS_STATUS_MEANING['NOT YET']).long;
}
function rdFocusLine(snap, p, act) {
  if (act && act.id === p.id) return '<p class="rd-focus-line"><span class="mp-tag">In focus</span> Your current move is recorded against this path. In focus is not a ranking.</p>';
  if (p.status_display === 'OPEN' && act) return `<p class="rd-focus-line">Open, but not in focus: your current move is recorded against ${stratEsc(act.title)}. You can still read everything here; looking is not choosing.</p>`;
  if (p.status_display === 'OPEN') return '<p class="rd-focus-line">Open, and no move is recorded against it right now.</p>';
  return '';
}
/* The state-specific section: its label follows the path's actual state; its content comes from the record only */
function rdStateSection(snap, p, act) {
  const live = (p.requirements || []).filter(r => r.applicable !== false);
  const by = k => live.filter(r => r.satisfaction === k);
  const how = r => r.guidance ? `<span class="rd-how">${r.satisfaction === 'UNKNOWN' ? 'To check it' : 'To get it'}: ${stratEsc(r.guidance)}</span>` : '';
  /* At most three conditions here; the full list is one click away (progressive disclosure) */
  let shown = 0, hidden = 0;
  const list = (rows, word) => {
    const take = rows.slice(0, Math.max(0, 3 - shown)); shown += take.length; hidden += rows.length - take.length;
    return take.length ? `<ul class="rd-need-list">${take.map(r => `<li>${reqMark(r.satisfaction, 'sm')}<span><b>${stratEsc(r.label)}</b> <span class="rd-need-word">${word}</span>${how(r)}</span></li>`).join('')}</ul>` : '';
  };
  const more = () => hidden ? `<button type="button" class="st-entry rd-more" onclick="rdOpenAll()"><span>${hidden} more in the full list</span>${stIcon('arrow')}</button>` : '';
  const sec = (label, inner, tone) => `<section class="rd-state${tone ? ' is-' + tone : ''}" aria-labelledby="rd-state-h"><div class="rd-state-h" id="rd-state-h">${label}</div>${inner}${more()}</section>`;
  const isFocus = act && act.id === p.id;
  if (p.stop_source === 'you') {
    return sec('You paused this path', `<p>${STOP_BY_NOTE.you}</p><p class="mp-fine">Going ahead again is your decision; it is recorded on the trail next to the pause.</p>`, 'paused');
  }
  if (p.status_display === 'STOP') {
    const absent = by('ABSENT');
    return sec('Why this path is stopped', `<p>${stratEsc(p.stop_cause || STOP_BY_NOTE.numbers)}</p>${absent.length ? `<p class="rd-state-sub">What would need to change, from the record:</p>${list(absent, 'not in place')}` : '<p class="mp-fine">The record names no single condition that would reopen it.</p>'}`, 'stop');
  }
  const named = p.next_move && !isFocus ? `<p class="rd-state-sub">The record names this step for the path: “${rdQ(p.next_move.title)}”. It is not your current move.</p>` : '';
  if (p.status_display === 'OPEN') {
    const open = [...by('ABSENT'), ...by('UNKNOWN'), ...by('PARTIAL')];
    const moveLine = isFocus && snap.nextmove && snap.nextmove.title ? `<p class="rd-state-sub">Your current move on this path: “${rdQ(snap.nextmove.title)}”.</p>` : '';
    return sec(open.length ? 'What still needs attention' : 'Nothing is recorded as missing',
      (open.length ? list(by('ABSENT'), 'not in place') + list(by('UNKNOWN'), 'not known yet') + list(by('PARTIAL'), 'partly shown') : '<p>Every requirement on record is confirmed.</p>') + moveLine + named);
  }
  if (p.status_display === 'TEST FIRST') {
    const v = [...by('UNKNOWN'), ...by('PARTIAL')];
    return sec('What needs to be verified',
      (v.length ? list(by('UNKNOWN'), 'not known yet') + list(by('PARTIAL'), 'partly shown') : '<p>The record does not name a single condition to verify.</p>') + (by('ABSENT').length && shown < 3 ? '<p class="rd-state-sub">Also not in place today:</p>' : '') + list(by('ABSENT'), 'not in place') + named);
  }
  const a = by('ABSENT'), u = by('UNKNOWN'), pa = by('PARTIAL');
  return sec('What would need to change',
    (a.length || u.length || pa.length
      ? `${a.length ? `<p class="rd-state-sub">Not in place today:</p>${list(a, 'not in place')}` : ''}${u.length ? `<p class="rd-state-sub">Not established yet (not known is not no):</p>${list(u, 'not known yet')}` : ''}${pa.length ? `<p class="rd-state-sub">Partly shown:</p>${list(pa, 'partly shown')}` : ''}`
      : '<p>The record does not name what is missing. The status comes from the engine’s overall reading.</p>') + named);
}
function readinessDetailHtml(snap, p) {
  const live = p.requirements.filter(r => r.applicable !== false);
  const nar = p.narrative || {};
  /* Groups in the engine's own states; what needs attention first, then what holds, then what does not count */
  const groups = [
    { label: 'Not in place', note: nar.holding || 'The record shows this is missing today.', rows: live.filter(r => r.satisfaction === 'ABSENT'), sat: 'ABSENT' },
    { label: 'Not known yet', note: nar.unclear || 'There is no evidence either way. Not known is not the same as no.', rows: live.filter(r => r.satisfaction === 'UNKNOWN'), sat: 'UNKNOWN' },
    { label: 'Partly shown', note: 'Some evidence supports this, but not enough to count it as confirmed.', rows: live.filter(r => r.satisfaction === 'PARTIAL'), sat: 'PARTIAL' },
    { label: 'Confirmed', note: nar.supported || '', rows: live.filter(r => r.satisfaction === 'PRESENT'), sat: 'PRESENT' },
    { label: 'Does not apply right now', note: 'Not counted for or against this path.', rows: p.requirements.filter(r => r.applicable === false), sat: 'NA' }
  ].filter(g => g.rows.length);
  const c = reqTally(p);
  const ev = snap.evidence.filter(e => (p.evidence_ids || []).includes(e.id));
  const act = mapsActive(snap);
  const isFocus = act && act.id === p.id;
  const disputed = ev.some(e => e.disputed) || live.some(r => r.conflict);
  const counts = !c.total
    ? `<p class="rd-counts">${stratEsc(reqSummary(p))}</p>`
    : `<p class="rd-counts"><strong>${c.PRESENT} of ${c.total}</strong> requirement${c.total === 1 ? '' : 's'} confirmed${RD_ATTENTION.some(k => c[k]) ? ' · ' + RD_ATTENTION.filter(k => c[k]).map(k => `${c[k]} ${REQ_WORDS[k]}`).join(' · ') : ''}${c.na ? ` · ${c.na} not counted` : ''}</p>`;
  return `
        <section class="rd-header-card" aria-label="Path summary">
          <div class="rd-status-line">
            <h2 class="serif-heading mp-title">${stratEsc(p.title)}</h2>
            ${stratPill(p.status_display, p.stop_source)}
            ${p.group ? `<span class="v11-req-word">${stratEsc(p.group)}</span>` : ''}
          </div>
          <p class="rd-finding">${stratEsc(rdStatusWhy(p))}</p>
          ${rdFocusLine(snap, p, act)}
          ${counts}
          ${p.goal_relation === 'UNKNOWN_RELATION' ? '<p class="mp-fine">Not shown yet: nothing on record says this path moves your goal. A hypothesis to test.</p>' : ''}
          ${p.advisory ? `<p class="mp-fine">${stratEsc(p.advisory)}</p>` : ''}
          ${disputed ? '<p class="rd-line"><span class="v11-disputed-badge">DISPUTED</span> Part of the record for this path is disputed. It is shown in full, never counted as confirmed.</p>' : ''}
        </section>
        ${p.stop_source === 'you' || p.status_display === 'STOP' ? rdStateSection(snap, p, act) : ''}
        ${groups.length ? `<section class="rd-reqs-open" id="rd-reqs" aria-labelledby="rd-reqs-h">
          <div class="rd-reqs-h" id="rd-reqs-h">Requirements by state · ${(p.requirements || []).length}</div>
          ${groups.map(g => `<div class="rd-group">
            <div class="rd-group-title">${reqMark(g.sat, 'sm')}${g.label} · ${g.rows.length}</div>
            ${g.note ? `<div class="rd-item-note">${stratEsc(g.note)}</div>` : ''}
            ${g.rows.map(r => `<div class="rd-item">
                <div class="rd-item-name">${reqMark(g.sat)}<span>${stratEsc(r.label)}${r.conflict ? ' <span class="v11-req-word">not settled</span>' : ''}</span></div>
                ${r.guidance && (g.sat === 'ABSENT' || g.sat === 'UNKNOWN' || g.sat === 'PARTIAL') ? `<div class="rd-item-note">${g.sat === 'UNKNOWN' ? 'To check it' : 'To get it'}: ${stratEsc(r.guidance)}</div>` : ''}
                ${r.conflict_note ? `<div class="rd-item-note">${stratEsc(r.conflict_note)}</div>` : ''}
              </div>`).join('')}
          </div>`).join('')}
        </section>` : ''}
        ${ev.length || p.provenance ? `<details class="mp-legend rd-evidence">
          <summary>Evidence and where this came from${ev.length ? ` · ${ev.length}` : ''}</summary>
          ${ev.map(e => `<div class="rd-basic-row is-top"><span class="rd-line">“${stratEsc(e.quote)}”${e.disputed ? ' <span class="v11-disputed-badge">DISPUTED</span>' : ''}</span><span class="rd-basic-val">${stratEsc(provText(e.source))}</span></div>`).join('')}
          ${p.provenance ? `<p class="mp-fine">On your map since: ${stratEsc(provText(p.provenance))}</p>` : ''}
        </details>` : '<p class="mp-fine">No evidence is on record for this path yet.</p>'}
`;
}
function rdOpenAll() { const d = document.getElementById('rd-reqs'); if (!d) return; if (d.tagName === 'DETAILS') d.open = true; const s = d.querySelector('summary'); if (s) { s.focus(); d.scrollIntoView({ block: 'nearest', behavior: mapsReduced() ? 'auto' : 'smooth' }); } }
/* Picking a path in Readiness writes the one shared selection and repaints in place (no page reset) */
function readinessSelect(id) {
  const snap = V11_ENGINE.snapshot();
  const p = snap.paths.find(x => x.id === id);
  if (!p) return;
  mapsSetSel(id, false);
  document.querySelectorAll('.rd-path-item').forEach(b => {
    const on = b.dataset.path === id;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
  });
  const host = document.getElementById('rd-detail');
  if (host) host.innerHTML = readinessDetailHtml(snap, p);
  const panel = document.getElementById('mp-panel');
  if (panel) panel.innerHTML = mapsPanelHtml(snap, id, false);
  const dn = document.getElementById('rd-default-note'); if (dn) dn.remove();
  const say = document.getElementById('rd-status'); if (say) say.textContent = `Showing what ${p.title} needs.`;
  // Stacked (≤760px) the detail sits under the list: bring it into view
  if (host && window.innerWidth <= 760) host.scrollIntoView({ block: 'start', behavior: mapsReduced() ? 'auto' : 'smooth' });
}
function screenReadiness(snap) {
  const subj = mapsReadinessSubject(snap);
  const p = snap.paths.find(x => x.id === subj.id);
  const stage = `
          <div class="rd-layout">
            <div class="rd-path-list" role="group" aria-label="Paths">
              ${snap.paths.map(x => `
                <button type="button" class="rd-path-item ${x.id === p.id ? 'active' : ''}" data-path="${x.id}" ${x.id === p.id ? 'aria-current="true"' : ''} onclick="readinessSelect('${x.id}')" aria-label="${stratEsc(x.title)}">
                  <span class="rd-path-item-title">${stratEsc(x.title)}</span>
                </button>`).join('')}
            </div>
            <div class="rd-detail" id="rd-detail">${readinessDetailHtml(snap, p)}</div>
            <div class="sr-only" role="status" id="rd-status"></div>
          </div>`;
  const content = mapsWorkspaceHtml(snap, subj.fromShared ? stage.replace('<div class="rd-detail" id="rd-detail">', `<div class="rd-detail" id="rd-detail"><p class="mp-fine mp-default-note" id="rd-default-note">Shown because it holds the shared requirement you picked on the map: ${stratEsc(subj.fromShared.label)}.</p>`) : stage, p.id, false);
  return renderAppShell('maps', 'Readiness', content);
}
/* Landscape (v13, reference layout): the map, with the status legend under it and the selected route on the right. The map
   itself is the existing canvas (2D lanes). Everything in the panel is read from the snapshot, and nothing is
   ranked, scored, or called recommended. */
/* The key under the map: each status as a chip with its count, and what it means, in an aligned two-column grid */
function mprKeyHtml(snap) {
  const n = w => snap.paths.filter(p => p.status_display === w).length;
  return `<dl class="mpr-key" aria-label="What the status words mean">${MAPS_WORDS.map(k => `<div class="mpr-key-row"><dt><span class="mpr-key-dot" style="background:${(V12_ST[k] || {}).line || '#a1a1aa'}" aria-hidden="true"></span><span class="mpr-key-word">${k}</span><span class="mpr-key-n" aria-label="${n(k)} on your map">${n(k)}</span></dt><dd>${stratEsc(MAPS_STATUS_MEANING[k].short)}</dd></div>`).join('')}</dl>`;
}
function mprLegendHtml(snap) {
  const n = w => snap.paths.filter(p => p.status_display === w).length;
  const item = (label, color, word) => `<span class="mpr-legend-item"><i style="background:${color}" aria-hidden="true"></i>${label} <b>${n(word)}</b></span>`;
  return `<div class="mpr-legend" aria-label="Legend: how many paths have each status">${item('Open', 'var(--open-line)', 'OPEN')}${item('Test first', 'var(--test-line)', 'TEST FIRST')}${item('Not yet', 'var(--notyet-line)', 'NOT YET')}${item('Stop', 'var(--stop-fg)', 'STOP')}</div>`;
}
/* What the map and the panel show. A choice is a path the person picked: it is drawn as selected. A stored
   presentation default (Readiness seeds the first path) is shown as in focus, never as a choice. With nothing stored,
   the path in focus is previewed and disclosed. `active` is the path the current move is recorded against. */
function mapsFocusState(snap) {
  const key = v11MapKey();
  const stored = mapsEffectiveSel(snap);
  const explicit = (STORE.mapsSelBy || {})[key];
  const active = (mapsActive(snap) || {}).id || null;
  const isDefault = !!stored && mapsSelIsDefault(snap);
  const choice = stored && explicit === stored && !isDefault ? stored : null;
  return { choice, shown: stored || active, preview: !stored && !!active, active };
}
function screenLandscape(snap) {
  const n = snap.paths.length;
  const st = mapsFocusState(snap);
  const pres = presentSnapshotPaths(snap.paths, { pinned: [st.shown, st.active] });
  const stage = `
          <div class="mp-canvas${n <= 2 ? ' is-sparse' : ''}">${v12MapCanvasHtml()}</div>
          ${mprKeyHtml(snap)}
          ${pres.hidden.length ? `<div id="mp-list">${mapsMoreHtml(snap, pres, st.choice, false)}</div>` : ''}`;
  const content = mapsWorkspaceHtml(snap, stage, st.shown, st.preview);
  return renderAppShell('maps', 'Explore', content);
}
/* NC-05: the durable change summary inside the ONE Maps destination. It is rendered from
   LIVE.experience.graph.change_set (never from a checkbox, an outcome label or a re-render) plus the
   contextual flag an accepted mutation sets. A bare deep link to a retired result page claims no
   specific change: there is nothing to diff against, so it resolves to Maps with no banner. */
function mapsChangeSummaryHtml(model) {
  const changed = (model.changed || []).map(function (c) {
    const delta = (c.from || c.to) ? (' <span class="mcs-move">' + stratEsc(String(c.from || '—')) + ' → ' + stratEsc(String(c.to || '—')) + '</span>') : '';
    return '<li><b>' + stratEsc(c.label) + '</b>' + delta + '</li>';
  }).join('');
  const actions = model.retry
    ? '<button type="button" class="btn-secondary btn-sm" onclick="mapsRetryRefresh()">Refresh the view</button>'
    : '<button type="button" class="btn-secondary btn-sm" onclick="goDestination(\'moves\')">Back to Moves</button>'
      + '<button type="button" class="btn-secondary btn-sm" onclick="goDestination(\'journey\')">See the journey</button>'
      + '<button type="button" class="btn-secondary btn-sm" onclick="mapsOpenReassessment()">Check for a new assessment</button>';
  return [
    '<section class="maps-change-summary" role="status" aria-label="What changed" data-kind="' + stratEsc(model.kind) + '">',
    '<div class="mcs-body">',
    '<div class="section-meta-label">AFTER YOUR REPORT</div>',
    '<h2 class="mcs-title">' + stratEsc(model.title) + '</h2>',
    model.body ? '<p class="mcs-line">' + stratEsc(model.body) + '</p>' : '',
    changed ? '<ul class="mcs-list">' + changed + '</ul>' : '',
    '<p class="mcs-fine">A recorded result is an observation. Whether a path changes is decided by the evidence, not by marking an action done.</p>',
    '</div>',
    '<div class="mcs-actions">' + actions + '<button type="button" class="rv-x" onclick="mapsDismissChangeSummary()" aria-label="Dismiss">✕</button></div>',
    '</section>'
  ].join('');
}
/* Move-centric first slice: ONE receipt after a result is reported - for the whole plan (plan_outcome) or
   for one canonical Move (move_outcome). It states where the work stands and what the canonical
   authorities say comes next: never a checkpoint, never an invented Move. NEXT_MOVE_AVAILABLE with an
   actionable canonical Move names it; RESULT_PENDING keeps reporting open; NEEDS_INFORMATION names the
   one thing to settle (a candidate, not an instruction); NOTHING_AUTHORIZED gives the real reason and
   offers the assessment as the OPTIONAL read it is. */
function mapsPlanOutcomeHtml(pending) {
  const c = (pending && pending.continuation) || {};
  const plan = c.plan || {};
  const out = (pending && pending.outcome) || c.outcome || {};
  const next = c.next || {};
  const row = (pending && pending.move) || null;          /* the canonical Move row, when the server sent one */
  const worked = plan.total ? ('You worked through ' + (plan.done || 0) + ' of ' + plan.total + ' actions' + (plan.skipped ? ' (' + plan.skipped + ' skipped)' : '') + '. ') : '';
  const said = out.outcome ? ('Your result: ' + mapsOutcomeWord(out.outcome) + '. ') : (out.note ? 'Your note is recorded. ' : '');
  /* The Move's own line, from its row only: objective + the counts it carries. A null move says nothing. */
  const prog = row && row.progress ? row.progress : null;
  const moveStat = (prog && prog.total != null) ? ((prog.done || 0) + ' of ' + prog.total + ' actions completed') : '';
  const moveBits = row ? [row.objective ? 'Move: ' + String(row.objective) : '', moveStat].filter(Boolean).join(' · ') : '';
  const journey = '<button type="button" class="btn-secondary btn-sm" onclick="goDestination(\'journey\')">See the journey</button>';
  const check = '<button type="button" class="btn-secondary btn-sm" onclick="mapsOpenReassessment()">Check for a new assessment</button>';
  /* Phase 7 §10 case B: asking the engine to decide is EXPLICIT and LLM-backed - never started by a
     checkbox. It is offered exactly where a decision is what is missing, and never where a result or
     an existing move comes first. */
  const ask = '<button type="button" class="btn-primary btn-sm" onclick="liveDecideNextMove(this)">Ask for the next move</button>';
  let title = 'Your result is recorded';
  let line = 'No continuation read came with this report, so nothing is claimed about what comes next.';
  let actions = journey + check;
  if (!c.state) {
    /* the report is on record but no continuation read arrived: claim nothing about what comes next */
  } else if (c.state === 'NEXT_MOVE_AVAILABLE' && next.kind === 'MOVE_ACTIONABLE') {
    title = 'Your next move is ready';
    line = 'The move you just executed is recorded. This is the next one.';
    actions = '<button type="button" class="btn-primary btn-sm" onclick="goDestination(\'moves\')">Open Moves</button>' + journey;
  } else if (c.state === 'NEXT_MOVE_AVAILABLE') {
    title = 'Your next piece of work is ready';
    line = 'The route already points at what comes next.';
    actions = '<button type="button" class="btn-primary btn-sm" onclick="goDestination(\'moves\')">Open Moves</button>' + journey;
  } else if (c.state === 'RESULT_PENDING') {
    title = 'Your move is executed';
    line = 'What happened as a result is still open. Reporting it is separate from finishing the work.';
    const call = next.move_id ? (`openMovesOutcomeReportForMove('${next.move_id}')`) : 'openMovesOutcomeReport()';
    actions = '<button type="button" class="btn-primary btn-sm" onclick="' + call + '">Report what happened</button>' + journey;
  } else if (c.state === 'NEEDS_INFORMATION') {
    title = 'One thing to settle before the next move';
    line = (next.headline || next.text) ? String(next.headline || next.text) : 'More information is needed before the next move.';
    actions = ask + '<button type="button" class="btn-secondary btn-sm" onclick="goDestination(\'talk\')">Answer in Talk</button>' + journey + check;
  } else {
    /* NOTHING_AUTHORIZED (or a state we do not know): the real reason, and the assessment offered as optional.
       The copy never implies a checkpoint is what stands between the person and continuing. */
    const reason = next.text || next.headline || '';
    const cand = next.kind ? String(next.kind).toLowerCase().replace(/_/g, ' ') : '';
    const base = reason ? String(reason)
      : (cand ? ('The canonical authorities authorize no next move yet' + (next.authority === 'CANDIDATE' ? (', and a candidate read (' + cand + ') is information, not an instruction') : '') + '.')
        : 'The canonical authorities authorize no next move yet.');
    title = 'Nothing new is authorized yet';
    line = base + ' Nothing here waits on a checkpoint, and a new assessment is optional.';
    actions = ask + journey + check;   /* the decision is the missing piece: ask for it, explicitly */
  }
  return [
    '<section class="maps-change-summary" role="status" aria-label="After your result" data-kind="' + ((pending && pending.source === 'move_outcome') ? 'MOVE_OUTCOME' : 'PLAN_OUTCOME') + '">',
    '<div class="mcs-body">',
    '<div class="section-meta-label">AFTER YOUR RESULT</div>',
    '<h2 class="mcs-title">' + stratEsc(title) + '</h2>',
    ((worked + said) ? '<p class="mcs-line">' + stratEsc(worked + said) + '</p>' : ''),
    (moveBits ? '<p class="mcs-line">' + stratEsc(moveBits) + '</p>' : ''),
    '<p class="mcs-line">' + stratEsc(line) + '</p>',
    '<p class="mcs-fine">A reported result is your own observation. Whether a path changes is decided by the evidence.</p>',
    '</div>',
    '<div class="mcs-actions">' + actions + '<button type="button" class="rv-x" onclick="mapsDismissChangeSummary()" aria-label="Dismiss">✕</button></div>',
    '</section>'
  ].join('');
}
function mapsOutcomeWord(o) {
  return ({ moved: 'moved', not_moved: 'no change yet', confounded: 'possibly confounded', regret: 'went backwards' }[o] || o);
}
/* ── NC-R7: recorded progress is a COMPACT row above the graph ──────────────────────────────────
   It reads the plan record the server projects (GET /experience .plan): the latest checkpoint
   carries ONE plan, with its own counts, and a superseded plan keeps ITS OWN counts under ITS OWN
   checkpoint label. DONE and SKIPPED are different words, and an old 3/3 is never presented as
   completion of a plan generated later. The per-action rows live behind a native disclosure, so the
   collapsed banner costs one line and the map stays dominant. */
function mapsTxt(v) { return stratEsc(String(v == null ? '' : v)); }
function mapsPlanCountsText(c) {
  const n = c || {};
  const total = n.total || 0;
  const bits = ['<strong>' + (n.executed_all ? 'All ' + total : ((n.done || 0) + ' of ' + total)) + '</strong> action step' + (total === 1 ? '' : 's') + ' done'];
  if (n.skipped) bits.push(n.skipped + ' skipped');
  if (n.blocked) bits.push(n.blocked + ' blocked');
  if (n.open) bits.push(n.open + ' still open');
  if (n.reported) bits.push('outcome on record');
  return bits.join(' · ');
}
const MAPS_PLAN_STATUS_WORD = { DONE: 'done', SKIPPED: 'skipped', BLOCKED: 'blocked', TODO: 'open' };
function mapsPlanActionRow(a) {
  const status = String((a && a.status) || 'TODO').toUpperCase();
  const mark = status === 'DONE' ? '✓' : status === 'SKIPPED' ? '–' : status === 'BLOCKED' ? '!' : '○';
  const cls = status === 'DONE' ? ' is-done' : status === 'SKIPPED' ? ' is-skipped' : status === 'BLOCKED' ? ' is-blocked' : '';
  const word = MAPS_PLAN_STATUS_WORD[status] || status.toLowerCase();
  const outcome = a && a.outcome ? ' <span class="mcs-move">· ' + mapsTxt(mapsOutcomeWord(a.outcome)) + '</span>' : '';
  const note = a && a.note ? '<div class="mcs-note">' + mapsTxt(brief(String(a.note), 160)) + '</div>' : '';
  return '<li class="mcs-prog' + cls + '">' + mark + ' ' + mapsTxt(brief(String((a && a.text) || ''), 96))
    + ' <span class="mcs-status">· ' + mapsTxt(word) + '</span>' + outcome + note + '</li>';
}
function mapsLegacyProgressRow(a) {
  const row = a || {};
  return '<li class="mcs-prog' + (row.done ? ' is-done' : '') + '">' + (row.done ? '✓' : '○') + ' '
    + mapsTxt(brief(row.label || '', 80)) + (row.outcome ? ' <span class="mcs-move">· ' + mapsTxt(mapsOutcomeWord(row.outcome)) + '</span>' : '') + '</li>';
}
function mapsPlanTopologyChanged() {
  const cs = (typeof liveExperienceChangeSet === 'function') ? liveExperienceChangeSet() : null;
  return !!(cs && (cs.topology_changed || (cs.changed || []).length));
}
/* A superseded plan is shown with ITS OWN checkpoint label, and only when it carries recorded steps:
   an old count can never read as the state of the plan the latest checkpoint created. */
function mapsSupersededPlanHtml(plan) {
  const rows = (plan && plan.superseded) || [];
  const rec = rows.find(function (p) {
    const c = (p && p.counts) || {};
    return (c.done || 0) > 0 || (c.skipped || 0) > 0 || (c.reported || 0) > 0;
  });
  if (!rec) return '';
  const v = rec.checkpoint_version != null ? rec.checkpoint_version : '?';
  const by = rec.replaced_by_version != null ? rec.replaced_by_version : '?';
  return '<p class="mcs-superseded"><span class="mcs-scope">plan from checkpoint v' + mapsTxt(v) + '</span> '
    + mapsPlanCountsText(rec.counts) + ' <span class="mcs-fine-inline">replaced by checkpoint v' + mapsTxt(by) + '</span></p>';
}
/* Records what is on the execution record. It never claims that a path changed: execution is not
   proof, and an executed route node stays labelled as proof still needed. Falls back to the previous
   per-action projection when the plan record is not available, worded "on the current plan". */
function mapsRecordedProgressHtml(model) {
  const plan = (LIVE.experience && LIVE.experience.plan) || null;
  const cur = (plan && plan.current) || null;
  const cc = (cur && cur.counts) || null;
  const usePlan = !!(cc && (cc.total || 0) > 0);
  const leg = (!usePlan && model && ((model.total || 0) > 0 || (model.verify || []).length)) ? model : null;
  if (!usePlan && !leg) return '';
  const verify = (model && (model.verify || []).length)
    ? '<p class="mcs-line">' + model.verify.length + ' route step' + (model.verify.length === 1 ? '' : 's') + ' executed, proof still needed.</p>'
    : '';
  /* A recorded outcome is visible without expanding anything: the plan counts carry it, and a legacy
     action with an outcome says it too. */
  const legOutcome = ((leg && leg.actions) || []).some(function (a) { return !!(a && a.outcome); });
  const compact = usePlan
    ? '<p class="mcs-compact-row"><span>' + mapsPlanCountsText(cc) + '</span><span class="mcs-scope">this plan</span></p>'
    : '<p class="mcs-compact-row"><span><strong>' + (leg.done || 0) + ' of ' + (leg.total || 0) + '</strong> action steps recorded'
      + (legOutcome ? ' · outcome on record' : '') + '</span><span class="mcs-scope">on the current plan</span></p>';
  const rows = usePlan
    ? (cur.actions || []).map(mapsPlanActionRow).join('')
    : (leg.actions || []).map(mapsLegacyProgressRow).join('');
  const changed = mapsPlanTopologyChanged();
  return [
    '<section class="maps-change-summary is-compact" role="status" aria-label="Recorded progress" data-kind="PROGRESS">',
    '<div class="mcs-body">',
    compact,
    /* Line 2 keeps the reassessment action visible: the server's own availability wording, the native
       progress disclosure, and the ONE entry point. The per-action rows stay inside the disclosure. */
    '<div class="mcs-line2">',
    '<span class="mcs-avail" id="maps-reassess-slot"></span>',
    '<details class="mcs-details">',
    '<summary class="mcs-details-toggle">Review progress</summary>',
    '<div class="mcs-details-body">',
    rows ? '<ul class="mcs-list">' + rows + '</ul>' : '',
    verify,
    usePlan ? mapsSupersededPlanHtml(plan) : '',
    '<p class="mcs-line">' + (changed ? 'Your map has changed.' : 'No path status has changed yet.') + ' Marking an action done records that you did it, not that it worked.</p>',
    '<div class="mcs-details-actions">',
    '<button type="button" class="btn-secondary btn-sm" onclick="goDestination(\'moves\')">Back to Moves</button>',
    '<button type="button" class="btn-secondary btn-sm" onclick="goDestination(\'journey\')">See the journey</button>',
    '</div>',
    '</div></details>',
    '<button type="button" class="btn-secondary btn-sm mcs-reassess-btn" onclick="mapsOpenReassessment()">Reassess</button>',
    '</div>',
    '</div>',
    '<div class="mcs-actions"><button type="button" class="rv-x" onclick="mapsDismissRecordedProgress()" aria-label="Dismiss">✕</button></div>',
    '</section>'
  ].join('');
}
/* Availability is stated ONLY from an actual server preview read: eligible, or the server's own
   blocked wording, rendered verbatim. Not fetched (or a failed read) says nothing at all - the CTA
   stays visible and performs its own fresh check. Eligibility is never claimed early. */
function mapsReassessAvailabilityHtml(p) {
  if (!p) return '';
  const elig = p.eligibility;
  if (!elig || typeof elig !== 'object') {
    /* COMPATIBILITY (hotfix): a payload without an eligibility block is a server build that cannot
       report it. That is a TECHNICAL fact, not an eligibility claim, so it is stated plainly instead
       of leaving the CTA a silent dead end. When the record shows no change, nothing is said. */
    return p.material_change === true
      ? 'This server build cannot confirm reassessment eligibility.'
      : '';
  }
  if (elig.eligible === true) return 'Reassessment available.';
  const blocked = (elig.blocked_details || []).filter(Boolean).map(String);
  return blocked.length ? blocked.join(' ') : '';
}
function mapsPaintReassessAvailability(p, hostKey) {
  const host = document.getElementById('maps-page-banners');
  if (!host || host.dataset.filledKey !== hostKey) return;      /* a later render owns this host */
  const slot = document.getElementById('maps-reassess-slot');
  if (slot) slot.textContent = mapsReassessAvailabilityHtml(p);
}
/* The preview entry is a cache of the last READ for this session/revision, never a lock: the flow
   itself always fetches a fresh one. */
function mapsCacheReassessPreview(sid, preview) {
  const rev = (LIVE.experience && LIVE.experience.revision && LIVE.experience.revision.projection_revision) || '';
  LIVE.reassessPreview[sid] = { rev: rev, data: preview };
}
function mapsLoadReassessAvailability(sid, hostKey) {
  if (IS_DEMO || !sid) return;
  const rev = (LIVE.experience && LIVE.experience.revision && LIVE.experience.revision.projection_revision) || '';
  const cached = LIVE.reassessPreview[sid];
  if (cached && cached.rev === rev && cached.data) { mapsPaintReassessAvailability(cached.data, hostKey); return; }
  API.reevaluatePreview(sid).then(function (p) {
    if (LIVE.sid !== sid) return;
    mapsCacheReassessPreview(sid, p);
    mapsPaintReassessAvailability(p, hostKey);
  }).catch(function () { /* availability unknown: the banner claims nothing */ });
}
/* Dismissal is VERSIONED, never a permanent boolean: session + checkpoint + projection revision +
   the newest recorded event. A newer accepted revision (or a new report) surfaces the summary
   again; re-rendering the SAME revision stays dismissed. */
function mapsProgressContextKey() {
  const exp = LIVE.experience || {};
  const cur = (exp.plan && exp.plan.current) || null;
  const lastEvent = ((cur && cur.actions) || []).reduce(function (mx, a) {
    const t = Number((a && (a.reported_at || a.done_at)) || 0);
    return t > mx ? t : mx;
  }, 0);
  return [LIVE.sid || '', mapsCurrentCheckpointId(), (exp.revision && exp.revision.projection_revision) || '', lastEvent].join(':');
}
function mapsProgressDismissed() {
  return !!STORE.mapsProgressDismissed && STORE.mapsProgressDismissed === mapsProgressContextKey();
}
function mapsDismissRecordedProgress() {
  STORE.mapsProgressDismissed = mapsProgressContextKey();
  const host = document.getElementById('maps-page-banners');
  if (host) { host.innerHTML = ''; host.dataset.filledKey = ''; }
}
/* ── Seen accepted checkpoint: the reload-surviving acknowledgement (NC-R8, §16 "returns later") ──
   STORE.pendingChangeSummary lives in memory only, so a checkpoint committed in an earlier page
   load would never be acknowledged. Maps remembers the last checkpoint id it has actually SHOWN for
   this session, client-side only. A checkpoint accepted later is therefore a result the person has
   not seen: the result notice is rendered from the serving model, and the id is written ONLY after
   that notice rendered and only when the read model is fresh - a failed refresh must never consume
   the acknowledgement. The same key scopes the dismissal. */
function mapsSeenKey(sid) { return 'nova.maps.seenCheckpoint.' + String(sid || ''); }
function mapsSeenGet(sid) {
  try { return localStorage.getItem(mapsSeenKey(sid)) || ''; } catch (e) {
    const mem = LIVE.mapsSeenCheckpoint;
    return (mem && mem.sid === sid) ? (mem.checkpointId || '') : '';
  }
}
function mapsSeenSet(sid, checkpointId) {
  LIVE.mapsSeenCheckpoint = { sid: sid, checkpointId: checkpointId || '' };
  try { localStorage.setItem(mapsSeenKey(sid), checkpointId || ''); } catch (e) { /* private mode: the in-memory marker still covers this page */ }
}
function mapsCurrentCheckpointId() {
  const exp = LIVE.experience || {};
  const cp = exp.checkpoint || {};
  const rev = exp.revision || {};
  return String(cp.checkpoint_id || rev.checkpoint_id || '');
}
function mapsCurrentCheckpointReason() {
  return String(((LIVE.experience || {}).checkpoint || {}).reason || '');
}
/* The current accepted checkpoint, when Maps has not shown it yet. A first sight of the initial
   checkpoint is not a reassessment result; a checkpoint whose server reason IS a reassessment is.
   A stale read claims nothing and consumes nothing. */
function mapsUnseenAcceptedCheckpoint() {
  if (LIVE.experienceError) return '';
  const id = mapsCurrentCheckpointId();
  if (!id) return '';
  const seen = mapsSeenGet(LIVE.sid);
  if (!seen) return mapsCurrentCheckpointReason() === 'reassessment' ? id : '';
  return id !== seen ? id : '';
}
function mapsMarkCheckpointSeen() {
  if (LIVE.experienceError) return;
  const id = mapsCurrentCheckpointId();
  if (id) mapsSeenSet(LIVE.sid, id);
}
/* ── NC-R8: the committed result notice ─────────────────────────────────────────────────────────
   Built from liveReassessmentResultModel() when it exists (execution-projection.js owns the meaning),
   otherwise from the durable change summary. This file renders the model's own title, body, reason
   and changed rows and never authors a business reason of its own; a next-destination control is
   offered only from the model's own nextLabel/nextAction. */
function mapsReassessmentResultModel() {
  if (typeof liveReassessmentResultModel === 'function') {
    try {
      const m = liveReassessmentResultModel();
      if (m) return m;
    } catch (e) { /* fall through to the durable change summary */ }
  }
  return (typeof liveChangeSummaryModel === 'function') ? liveChangeSummaryModel() : null;
}
function mapsResultField(o, keys) {
  for (let i = 0; i < keys.length; i++) {
    const v = o ? o[keys[i]] : null;
    if (v !== undefined && v !== null && v !== '') return v;
  }
  return '';
}
/* The next destination is ONLY what the model offers (nextLabel + nextAction): no label, or an
   action this build cannot resolve, means no button at all. Maps never invents a Move, a DONE
   action, or a destination of its own. */
const MAPS_RESULT_DESTS = ['moves', 'journey', 'maps', 'state', 'talk'];
function mapsResultNextCta(model) {
  const m = model || {};
  const label = String(m.nextLabel || '').trim();
  const action = m.nextAction;
  if (!label || action == null || action === '') return '';
  let onclick = '';
  if (typeof action === 'object') {
    const dest = String(action.dest || action.destination || action.screen || '');
    if (MAPS_RESULT_DESTS.indexOf(dest) >= 0) onclick = "goDestination('" + dest + "')";
  } else if (typeof action === 'string') {
    if (MAPS_RESULT_DESTS.indexOf(action) >= 0) onclick = "goDestination('" + action + "')";
    else if (/^[A-Za-z_$][\w$]*$/.test(action) && typeof window[action] === 'function') onclick = action + '()';
  }
  if (!onclick) return '';
  return '<button type="button" class="btn-secondary btn-sm" onclick="' + onclick + '">' + mapsTxt(label) + '</button>';
}
function mapsResultChangedRows(model) {
  const m = model || {};
  const rows = Array.isArray(m.changed) ? m.changed : (Array.isArray(m.changed_entities) ? m.changed_entities : []);
  return rows.map(function (c) {
    const label = mapsResultField(c, ['label', 'name', 'title']);
    const from = mapsResultField(c, ['from', 'from_label']);
    const to = mapsResultField(c, ['to', 'to_label']);
    const delta = (from || to)
      ? ' <span class="mcs-move">' + mapsTxt(from || '—') + ' → ' + mapsTxt(to || '—') + '</span>'
      : '';
    return '<li><b>' + mapsTxt(label) + '</b>' + delta + '</li>';
  }).join('');
}
/* title, body and reason are rendered VERBATIM from the model: Maps adds no second sentence and
   never replaces the server-grounded reason with an explanation of its own. An empty model renders
   nothing at all (the caller then keeps the checkpoint unseen rather than claiming anything). */
function mapsReassessmentResultHtml(model) {
  const m = model || {};
  const kind = String(m.kind || 'REASSESSED').toUpperCase();
  const rows = mapsResultChangedRows(m);
  const title = String(m.title || '');
  const body = String(m.body || '');
  const reason = String(m.reason || '');
  if (!title && !body && !reason && !rows) return '';
  return [
    '<section class="maps-change-summary is-compact" role="status" aria-label="Reassessment result" data-kind="' + mapsTxt(kind) + '">',
    '<div class="mcs-body">',
    '<div class="section-meta-label">REASSESSMENT</div>',
    title ? '<h2 class="mcs-title">' + mapsTxt(title) + '</h2>' : '',
    body ? '<p class="mcs-line">' + mapsTxt(body) + '</p>' : '',
    reason ? '<p class="mcs-line mcs-reason">' + mapsTxt(reason) + '</p>' : '',
    rows ? '<ul class="mcs-list">' + rows + '</ul>' : '',
    '</div>',
    '<div class="mcs-actions">',
    mapsResultNextCta(m),
    '<button type="button" class="rv-x" onclick="mapsDismissChangeSummary()" aria-label="Dismiss">✕</button>',
    '</div>',
    '</section>'
  ].join('');
}
/* The committed checkpoint is on record but the read model could not be refreshed: the commit still
   stands, so the banner keeps the receipt and offers the READ-ONLY retry. It never resubmits. */
function mapsReassessStaleHtml(message) {
  if (typeof liveReassessmentStaleHtml === 'function') {
    try {
      const h = liveReassessmentStaleHtml();
      if (h) return h;
    } catch (e) { /* the local receipt below is the honest fallback */ }
  }
  return [
    '<section class="maps-change-summary is-compact" role="status" aria-label="Reassessment committed" data-kind="REASSESSED">',
    '<div class="mcs-body">',
    '<p class="mcs-compact-row"><strong>Your reassessment is committed.</strong></p>',
    '<p class="mcs-line">' + mapsTxt(message || 'The new assessment is on record, but this view could not be refreshed, so it may still show the previous one.') + '</p>',
    '</div>',
    '<div class="mcs-actions">',
    '<button type="button" class="btn-secondary btn-sm" onclick="mapsReassessRetryRead()">Check now</button>',
    '<button type="button" class="rv-x" onclick="mapsDismissChangeSummary()" aria-label="Dismiss">✕</button>',
    '</div>',
    '</section>'
  ].join('');
}
function mapsBannerContextKey() {
  const p = STORE.pendingChangeSummary || null;
  const exp = LIVE.experience || {};
  return [
    LIVE.sid || '',
    (exp.revision && exp.revision.projection_revision) || '',
    mapsCurrentCheckpointId(),
    p ? (p.source + (p.refreshFailed ? ':stale' : ':ok') + ':' + (p.expectCheckpointId || '')) : '',
    LIVE.reassessReceipt ? 'receipt' : ''
  ].join('|');
}
/* Never steals a focus the person chose: only a CHANGED graph may bring a new reference forward,
   and only while no explicit choice is stored. */
function mapsMaybeSelectChanged(model, snap) {
  const changed = (model && model.changed) || [];
  if (!changed.length || String(model.kind || '').toUpperCase().indexOf('CHANGED') !== 0) return;
  const refs = changed[0].pathId || changed[0].path_id || null;
  if (!refs || typeof mapsSelect !== 'function' || !snap) return;
  const st = mapsFocusState(snap);
  if (st.choice) return;                                   // an explicit choice is never overwritten
  if (refs !== st.shown) mapsSelect(refs);
}
/* NC-05/NC-R8: ONE banner host above the graph. The already-drawn marker is keyed on the revision
   and checkpoint, so a NEW accepted result always renders while a re-render of the same revision
   does not. Reassessment wording is owned by the server facts: this never claims eligibility. */
function mapsEnsureChangeSummary() {
  if (IS_DEMO) return;
  const host = document.getElementById('maps-page-banners');
  if (!host) return;
  const key = mapsBannerContextKey();
  if (host.dataset.filledKey === key) return;
  const snap = V11_ENGINE.snapshot();
  if (STORE.pendingChangeSummary) {
    const pending = STORE.pendingChangeSummary;
    if (pending.source === 'reassess') {
      if (pending.refreshFailed) {
        host.innerHTML = mapsReassessStaleHtml(pending.message);
        host.dataset.filledKey = key;
        return;                                            // the read-only retry stays reachable
      }
      const model = mapsReassessmentResultModel();
      if (!model) return;                                  // nothing is claimed before its model exists
      const html = mapsReassessmentResultHtml(model);
      if (!html) return;                                   // an empty model claims nothing and consumes nothing
      host.innerHTML = html;
      host.dataset.filledKey = key;
      mapsMarkCheckpointSeen();                            // the result has now actually been shown
      mapsMaybeSelectChanged(model, snap);
      return;                                              // kept until dismissed: this is a receipt
    }
    /* ONE receipt for a reported result, whether it was reported for the plan or for a canonical Move
       (plan_outcome / move_outcome). Never a second banner; kept until the person dismisses it. */
    if (pending.source === 'plan_outcome' || pending.source === 'move_outcome') {
      host.innerHTML = mapsPlanOutcomeHtml(pending);       // a receipt: kept until the person dismisses it
      host.dataset.filledKey = key;
      mapsMarkCheckpointSeen();
      return;
    }
    const model = (typeof liveChangeSummaryModel === 'function') ? liveChangeSummaryModel() : null;
    if (!model) return;
    host.innerHTML = mapsChangeSummaryHtml(model);
    host.dataset.filledKey = key;
    mapsMaybeSelectChanged(model, snap);
    mapsMarkCheckpointSeen();
    /* A one-time acknowledgement; an unavailable projection keeps the banner so the retry stays reachable. */
    if (model.kind !== 'UNAVAILABLE') STORE.pendingChangeSummary = null;
    return;
  }
  /* An already-shown result notice stays until it is dismissed: a background re-render (the
     plain-language rewrite landing late) must not silently replace the receipt with the progress
     summary. A newer accepted revision changes the key and surfaces the NEW result instead. */
  if (LIVE.mapsReassessNoticeKey && LIVE.mapsReassessNoticeKey === key) {
    const model = mapsReassessmentResultModel();
    const html = model ? mapsReassessmentResultHtml(model) : '';
    if (html) { host.innerHTML = html; host.dataset.filledKey = key; return; }
  }
  const unseen = mapsUnseenAcceptedCheckpoint();
  if (unseen) {
    const model = mapsReassessmentResultModel();
    if (!model) return;                                    // stays unseen until it can be shown honestly
    const html = mapsReassessmentResultHtml(model);
    if (!html) return;                                     // still unseen: nothing was actually shown
    host.innerHTML = html;
    host.dataset.filledKey = key;
    LIVE.mapsReassessNoticeKey = key;
    mapsSeenSet(LIVE.sid, unseen);
    mapsMaybeSelectChanged(model, snap);
    return;
  }
  if (mapsProgressDismissed()) { mapsMarkCheckpointSeen(); return; }
  const prog = (typeof liveRecordedProgressModel === 'function') ? liveRecordedProgressModel() : null;
  const html = mapsRecordedProgressHtml(prog);
  mapsMarkCheckpointSeen();                                // Maps has rendered this checkpoint
  if (!html) return;
  host.innerHTML = html;
  host.dataset.filledKey = key;
  mapsLoadReassessAvailability(LIVE.sid, key);             // availability from the server's own read, or silence
}
function mapsDismissChangeSummary() {
  STORE.pendingChangeSummary = null;
  LIVE.mapsReassessNoticeKey = null;                       // the receipt was seen and dismissed
  mapsMarkCheckpointSeen();
  const host = document.getElementById('maps-page-banners');
  if (host) { host.innerHTML = ''; host.dataset.filledKey = ''; }
}
async function mapsRetryRefresh() {
  if (typeof liveRetryRefresh === 'function') await liveRetryRefresh();
}
/* ── The ONE reassessment entry point on Maps ───────────────────────────────────────────────────
   A reassessment is expensive and committing, so Maps decides it IN PLACE: always a FRESH preview
   (never the cached one), a confirmation built only from the server's own facts, one operation id
   per approved submission, and a pending state that reports the server's own stage. Nothing
   navigates away to mutate, and an ambiguous failure is reconciled by a READ, never a second POST. */
LIVE.reassessPreview = LIVE.reassessPreview || {};
LIVE.reassessBusy = false;                                 /* a committing POST is in flight */
LIVE.reassessApproved = LIVE.reassessApproved || null;     /* {sid, token, preview, checkpointId, revision, op} */
LIVE.reassessReceipt = LIVE.reassessReceipt || null;       /* the committed checkpoint = the receipt */
LIVE.reassessAmbiguous = LIVE.reassessAmbiguous || null;   /* a timed-out POST: never resubmitted */
LIVE.reassessToken = 0;                                    /* the sheet generation on screen */
LIVE.reassessTimer = null;
LIVE.reassessProgress = null;
LIVE.reassessKeepWatching = false;
LIVE.mapsSeenCheckpoint = LIVE.mapsSeenCheckpoint || null; /* in-memory fallback for the seen marker */
LIVE.mapsReassessNoticeKey = LIVE.mapsReassessNoticeKey || null; /* the result notice currently kept on Maps */

function mapsReassessSheetVisible(token) {
  const root = document.getElementById('rs-root');
  const back = document.getElementById('stop-modal');
  if (!root || !back || !back.classList.contains('open')) return false;
  return token == null || root.dataset.rsToken === String(token);
}
function mapsReassessOpenSheet(token, html) {
  const card = document.getElementById('modal-content');
  const back = document.getElementById('stop-modal');
  if (!card || !back) return false;
  card.innerHTML = '<div class="rv-modal mr-modal rs-sheet" id="rs-root" data-rs-token="'
    + mapsTxt(token == null ? LIVE.reassessToken : token) + '">' + html + '</div>';
  card.setAttribute('aria-labelledby', 'rs-title');
  card.removeAttribute('aria-label');
  back.classList.add('open');
  overlayOpened('stop-modal');
  return true;
}
function mapsReassessHead(meta, title, lead) {
  return '<div class="rv-sheet-head"><div>'
    + '<div class="section-meta-label">' + mapsTxt(meta) + '</div>'
    + '<h2 class="serif-heading" id="rs-title">' + mapsTxt(title) + '</h2>'
    + (lead ? '<p class="rv-sheet-lead">' + mapsTxt(lead) + '</p>' : '')
    + '</div><button type="button" class="rv-x" onclick="closeModal()" aria-label="Close">✕</button></div>';
}
function mapsReassessFoot(buttons) { return '<div class="rv-foot">' + buttons + '</div>'; }
/* Render an outcome into the sheet only while it is still the sheet the person is looking at; a
   sheet they closed or navigated away from is reported by toast instead. */
function mapsReassessShowOutcome(token, html, toast) {
  if (mapsReassessSheetVisible(token)) { mapsReassessOpenSheet(token, html); return true; }
  if (toast) showToast(toast, '', '', 'error');
  return false;
}

/* a. The check is ALWAYS a fresh read; the cached preview entry is never trusted. On failure an
   honest "could not check" state with a retry is shown - eligibility is never claimed. */
async function mapsOpenReassessment() {
  if (IS_DEMO || !LIVE.sid) return;
  if (LIVE.reassessBusy) { mapsReassessRenderPending(); return; }   /* never a second POST */
  const sid = LIVE.sid;
  const token = ++LIVE.reassessToken;
  mapsReassessStopPolling();
  LIVE.reassessApproved = null;
  mapsReassessOpenSheet(token, mapsReassessPreviewPendingHtml());
  let preview = null;
  try {
    preview = await API.reevaluatePreview(sid);
  } catch (e) {
    if (LIVE.sid === sid && mapsReassessSheetVisible(token)) {
      mapsReassessOpenSheet(token, mapsReassessPreviewErrorHtml((e && e.message) || 'the request failed'));
    }
    return;
  }
  if (LIVE.sid !== sid || !mapsReassessSheetVisible(token)) return;  /* the person left or closed the sheet */
  mapsCacheReassessPreview(sid, preview);
  LIVE.reassessApproved = mapsReassessApprovedFrom(preview, sid, token);
  mapsReassessOpenSheet(token, mapsReassessConfirmSheet(preview, ''));
}
function mapsReassessPreviewPendingHtml() {
  return mapsReassessHead('REASSESSMENT', 'Checking your record…', 'Reading what changed since your last checkpoint. This check saves nothing.')
    + '<p class="rs-status" role="status"><span class="think-dots"><i></i><i></i><i></i></span> Reading the current record…</p>';
}
function mapsReassessPreviewErrorHtml(message) {
  return mapsReassessHead('REASSESSMENT', 'Could not check your record.', 'The check did not come back' + (message ? ' (' + message + ')' : '') + '. Nothing was assessed and nothing was saved.')
    + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
      + '<button type="button" class="btn-primary btn-sm" onclick="mapsOpenReassessment()">Try again</button>');
}
/* b. The confirmation shows ONLY server facts: the eligibility reason details, the basis counts when
   the server reports them, and the checkpoint a re-evaluation would supersede. NOT eligible shows the
   server's blocked details and NO commit button (close / check again only). */
function mapsReassessConfirmSheet(preview, notice) {
  const p = preview || {};
  const elig = p.eligibility || {};
  const basis = p.basis || {};
  const cp = p.checkpoint || null;
  const eligible = elig.eligible === true;
  const version = cp && cp.version != null ? cp.version : elig.current_checkpoint_version;
  const nextV = p.next_checkpoint_version != null ? p.next_checkpoint_version : elig.next_checkpoint_version;
  const facts = (elig.reason_details || []).filter(Boolean).map(String);
  if (!facts.length) {
    const added = (basis.evidence_added_since_checkpoint || []).length;
    const corrected = (basis.evidence_superseded || []).length;
    if (added) facts.push(added + ' new fact' + (added === 1 ? '' : 's') + ' since your last checkpoint');
    if (corrected) facts.push(corrected + ' earlier claim' + (corrected === 1 ? ' was' : 's were') + ' corrected');
  }
  const blocked = (elig.blocked_details || []).filter(Boolean).map(String);
  const list = function (rows) {
    return '<ul class="rs-facts">' + rows.map(function (t) { return '<li>' + mapsTxt(t) + '</li>'; }).join('') + '</ul>';
  };
  /* COMPATIBILITY (hotfix): the preview is the server's own statement. A payload WITHOUT an eligibility
     block is not "not eligible" - it means this server build cannot report eligibility at all (an older
     process, a partial deployment). Calling that "a reassessment is not available" is a false negative
     that dead-ends the person; silently committing instead would bypass the operation key, the revision
     precondition, the durable commit and the plan archive. So the sheet states the real situation,
     keeps the observed facts, and offers only a read-only retry. */
  if (!p.eligibility || typeof p.eligibility !== 'object') {
    const observed = (basis.evidence_added_since_checkpoint || []).length;
    const corrected = (basis.evidence_superseded || []).length;
    const seen = [];
    if (observed) seen.push(observed + ' new fact' + (observed === 1 ? '' : 's') + ' since your last checkpoint');
    if (corrected) seen.push(corrected + ' earlier claim' + (corrected === 1 ? ' was' : 's were') + ' corrected');
    if (p.material_change === true) seen.push('The record reports material change, but this build cannot confirm whether a re-evaluation may run.');
    return mapsReassessHead('REASSESSMENT', 'This server build does not report reassessment eligibility.',
      'The check came back without its eligibility block, so Novaliners cannot verify that a re-evaluation is safe to run from here. Nothing was changed.')
      + (notice ? '<p class="rs-notice" role="alert">' + mapsTxt(notice) + '</p>' : '')
      + (seen.length ? list(seen) : '')
      + '<p class="mcs-fine">Restart the app server so the current contract is loaded, then check again. Reassessing against a build that cannot report eligibility would skip the operation key, the revision precondition and the archive of the plan it replaces.</p>'
      + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
        + '<button type="button" class="btn-primary btn-sm" onclick="mapsOpenReassessment()">Check again</button>');
  }
  const head = eligible
    ? mapsReassessHead('REASSESSMENT', 'Reassess your navigation', 'Your record has changed since the previous assessment.')
    : mapsReassessHead('REASSESSMENT', 'A reassessment is not available right now.', 'The server decides whether a re-evaluation can run. This is what it reported.');
  const body = eligible
    ? '<p class="mcs-line">Novaliners can re-evaluate your current situation and determine whether any Path, condition, or next Move should change. Your existing history will remain available.</p>'
    : '';
  const versionHtml = (eligible && nextV != null)
    ? '<p class="rs-version">This would build checkpoint v' + mapsTxt(nextV)
      + (version != null ? ' and replace checkpoint v' + mapsTxt(version) + ', which stays readable as history' : '') + '.</p>'
    : '';
  const foot = eligible
    ? mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Not now</button>'
      + '<button type="button" class="btn-primary btn-sm" id="rs-confirm" onclick="mapsConfirmReassessment()">Reassess now</button>')
    : mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
      + '<button type="button" class="btn-secondary btn-sm" onclick="mapsOpenReassessment()">Check again</button>');
  return head
    + (notice ? '<p class="rs-notice" role="alert">' + mapsTxt(notice) + '</p>' : '')
    + body
    + (facts.length ? list(facts) : '')
    + (blocked.length ? '<div class="rs-blocked">' + list(blocked) + '</div>' : '')
    + versionHtml + foot;
}
function mapsReassessApprovedFrom(preview, sid, token) {
  const elig = (preview && preview.eligibility) || {};
  return {
    sid: sid, token: token, preview: preview || null,
    checkpointId: (preview && preview.checkpoint && preview.checkpoint.checkpoint_id) || elig.current_checkpoint_id || '',
    revision: (preview && preview.current_projection_revision) || elig.current_projection_revision || '',
    op: null                                            /* a NEW confirmation needs a NEW operation id */
  };
}

/* c+d. One operation id per approved submission, kept for a retry of the SAME submission. The
   pending state is honest: the server's own stage label plus an elapsed counter, no percentages,
   and no cancel that would imply the synthesis stopped. */
async function mapsConfirmReassessment() {
  if (IS_DEMO || !LIVE.sid) return;
  const approved = LIVE.reassessApproved;
  if (!approved || approved.sid !== LIVE.sid) { mapsOpenReassessment(); return; }
  if (LIVE.reassessBusy) return;                        /* double-click, re-render, navigation: never a second POST */
  if (!approved.op) approved.op = newOperationId('rs');
  const token = ++LIVE.reassessToken;
  approved.token = token;
  LIVE.reassessBusy = true;
  LIVE.reassessKeepWatching = false;
  LIVE.reassessAmbiguous = null;
  mapsReassessOpenSheet(token, mapsReassessPendingHtml());
  mapsReassessStartPolling(token, approved.sid);
  try {
    const r = await API.reassessConfirm(approved.sid, {
      operation_id: approved.op,
      expected_checkpoint_id: approved.checkpointId || '',
      expected_projection_revision: approved.revision || ''
    });
    try {
      await mapsReassessAccepted(r, approved, token);
    } catch (e2) {
      /* The 200 is the commit: a failure past it is a report/read problem and is never re-posted. */
      const cpId = (r && r.checkpoint && r.checkpoint.checkpoint_id) || '';
      LIVE.reassessReceipt = LIVE.reassessReceipt || { checkpoint: (r && r.checkpoint) || null, previous_checkpoint: null, replayed: false, plan: null };
      STORE.pendingChangeSummary = { source: 'reassess', expectCheckpointId: cpId, refreshFailed: true, message: 'The new assessment is on record, but this view could not be updated.' };
      if (STORE.currentScreen === 'maps') { closeModal(); renderScreenKeepingUi('maps'); }
    }
  } catch (e) {
    mapsReassessRejected(e, approved, token);
  } finally {
    LIVE.reassessBusy = false;
    if (LIVE.reassessKeepWatching) LIVE.reassessKeepWatching = false;  /* an in-progress sheet keeps its watcher */
    else mapsReassessStopPolling();
  }
}
function mapsReassessPendingHtml() {
  const p = (LIVE.reassessApproved && LIVE.reassessApproved.preview) || {};
  const nextV = p.next_checkpoint_version != null ? p.next_checkpoint_version : ((p.eligibility || {}).next_checkpoint_version);
  return mapsReassessHead('REASSESSMENT', 'Re-evaluating your navigation…', 'Novaliners is re-reading your record and determining whether any Path, condition, or next Move should change. This can take a while.')
    + '<p class="rs-status" role="status" aria-live="polite"><span class="think-dots"><i></i><i></i><i></i></span> <span id="rs-stage">Working…</span> <span class="rs-when" id="rs-elapsed"></span></p>'
    + (nextV != null ? '<p class="rs-version">Building checkpoint v' + mapsTxt(nextV) + '.</p>' : '')
    + '<p class="mcs-fine">Do not submit this again while it runs. Closing this sheet does not stop it: the re-evaluation keeps running and the result is reported on your map.</p>'
    + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Hide</button>');
}
function mapsReassessRenderPending() {
  const token = LIVE.reassessToken;                     /* the SAME generation: the outcome still lands here */
  mapsReassessOpenSheet(token, mapsReassessPendingHtml());
  mapsReassessTouchStatus();
}
function mapsReassessStartPolling(token, sid) {
  mapsReassessStopPolling();
  LIVE.reassessProgress = { token: token, sid: sid, started: Date.now(), label: '' };
  LIVE.reassessTimer = setInterval(async function () {
    const p = LIVE.reassessProgress;
    if (!p || p.token !== token) return;
    try {
      const pr = await API.progress(sid);
      if (LIVE.sid === sid && pr && pr.active && pr.label) p.label = String(pr.label);
    } catch (e) { /* progress must never break the main flow */ }
    if (!mapsReassessSheetVisible(token)) { mapsReassessStopPolling(); return; }  /* the sheet is gone: stop watching */
    mapsReassessTouchStatus();
  }, 1500);
  mapsReassessTouchStatus();
}
function mapsReassessStopPolling() {
  if (LIVE.reassessTimer) clearInterval(LIVE.reassessTimer);
  LIVE.reassessTimer = null;
  LIVE.reassessProgress = null;
}
function mapsReassessElapsedText() {
  const p = LIVE.reassessProgress;
  if (!p) return '';
  const s = Math.max(0, Math.round((Date.now() - p.started) / 1000));
  return s < 60 ? s + 's' : (Math.floor(s / 60) + 'm ' + (s % 60) + 's');
}
function mapsReassessTouchStatus() {
  const stage = document.getElementById('rs-stage');
  if (stage) stage.textContent = (LIVE.reassessProgress && LIVE.reassessProgress.label) || 'Working…';
  const when = document.getElementById('rs-elapsed');
  if (when) when.textContent = mapsReassessElapsedText();
}

/* e. On 200 the returned checkpoint IS the receipt. The read models are then refreshed: a failed read
   is a stale VIEW over a committed checkpoint, never a failed commit, and it is never resubmitted. */
async function mapsReassessAccepted(r, approved, token) {
  const sid = approved.sid;
  if (LIVE.sid !== sid) return;
  const cp = r && r.checkpoint;
  /* COMPATIBILITY (hotfix): a server build older than this contract answers /reassess with
     {session_id, checkpoint} and no ok/committed markers. A checkpoint in the response is the server
     saying the synthesis committed, so it must not be reported as "not confirmed" - but the older
     build also could not enforce the operation key or the revision precondition, and that caveat is
     carried into the receipt instead of being hidden. */
  const olderContract = !!r && r.ok === undefined && r.committed === undefined;
  const accepted = !!cp && !!cp.checkpoint_id
    && (olderContract ? true : (r.ok === true && r.committed === true));
  if (!accepted) {
    mapsReassessShowOutcome(token, mapsReassessHead('REASSESSMENT', 'The reassessment was not confirmed.', 'The server did not report a committed checkpoint, so nothing is being claimed here.')
      + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
        + '<button type="button" class="btn-secondary btn-sm" onclick="mapsOpenReassessment()">Check again</button>'),
      'The reassessment was not confirmed. Open Maps to review.');
    return;
  }
  LIVE.reassessReceipt = { checkpoint: cp, previous_checkpoint: (r && r.previous_checkpoint) || null,
    replayed: !!(r && r.replayed), plan: (r && r.plan) || null, contractUnverified: olderContract };
  LIVE.reassessAmbiguous = null;
  LIVE.reassessApproved = null;
  delete LIVE.reassessPreview[sid];
  const expectId = cp.checkpoint_id;
  const ok = await mapsReassessRefresh(expectId);
  LIVE.lastRefreshFailed = !ok;
  STORE.pendingChangeSummary = { source: 'reassess', expectCheckpointId: expectId, refreshFailed: !ok };
  if (STORE.currentScreen === 'maps') { closeModal(); renderScreenKeepingUi('maps'); }
  else {
    showToast(ok ? 'Your reassessment is on record.' : 'Your reassessment is committed. Open Maps to read it.', '', '', ok ? '' : 'error');
    renderScreenKeepingUi(STORE.currentScreen);
  }
}
/* The read both callers share. liveRefreshAfterReassessment resolves {ok, exp}; the legacy helpers in
   the same module resolve a boolean, so the two shapes stay distinct. */
async function mapsReassessRefresh(expectCheckpointId) {
  try {
    if (typeof liveRefreshAfterReassessment === 'function') {
      const res = await liveRefreshAfterReassessment({ expectCheckpointId: expectCheckpointId || '', render: false });
      return !!(res && res.ok === true);
    }
    if (typeof liveRefreshAfterMutation === 'function') {
      return (await liveRefreshAfterMutation({ render: false })) === true;
    }
  } catch (e) { return false; }
  return !LIVE.experienceError && !LIVE.experiencePending;
}
/* The committed receipt stands; the view could not be read. Retry the READ only. */
async function mapsReassessRetryRead() {
  if (IS_DEMO || !LIVE.sid) return false;
  const pending = STORE.pendingChangeSummary || {};
  const expectId = pending.expectCheckpointId || '';
  const ok = await mapsReassessRefresh(expectId);
  LIVE.lastRefreshFailed = !ok;
  if (!ok) { showToast('Still could not read the new assessment. It is on record - try again shortly.', '', '', 'error'); return false; }
  STORE.pendingChangeSummary = { source: 'reassess', expectCheckpointId: expectId };
  renderScreenKeepingUi('maps');
  return true;
}

/* f. Guarded refusals render the server's own code and details. A technical failure is never a
   business STOP or NOT YET, and an ambiguous transport failure is reconciled by a READ. */
function mapsReassessRejected(err, approved, token) {
  if (LIVE.sid !== approved.sid) return;
  const status = err && err.status;
  const code = (err && err.code) || '';
  const detail = (err && err.detail) || null;
  const message = (detail && detail.message) || (err && err.message) || 'The reassessment did not go through.';
  if (!status) {                                       /* no HTTP answer at all: the outcome is UNKNOWN */
    LIVE.reassessAmbiguous = { approved: approved };
    LIVE.reassessApproved = approved;
    mapsReassessShowOutcome(token, mapsReassessHead('REASSESSMENT', 'We could not confirm whether that finished.', 'The connection dropped before the server answered. The re-evaluation may still be running on the server.')
      + '<p class="mcs-fine">Nothing will be submitted again. The next step is a read-only check.</p>'
      + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
        + '<button type="button" class="btn-primary btn-sm" onclick="mapsReassessCheckNow()">Check now</button>'),
      'Could not confirm the reassessment. Open Maps to check.');
    return;
  }
  if (status === 409 && code === 'REASSESSMENT_IN_PROGRESS') {
    LIVE.reassessApproved = approved;
    const html = mapsReassessHead('REASSESSMENT', 'A re-evaluation is already running for this map.', 'Only one re-evaluation runs at a time. Nothing is submitted from here while it runs.')
      + '<p class="rs-status" role="status" aria-live="polite"><span class="think-dots"><i></i><i></i><i></i></span> <span id="rs-stage">Working…</span> <span class="rs-when" id="rs-elapsed"></span></p>'
      + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Hide</button>'
        + '<button type="button" class="btn-primary btn-sm" onclick="mapsReassessCheckNow()">Check now</button>');
    if (mapsReassessShowOutcome(token, html, 'A re-evaluation is already running.')) {
      LIVE.reassessKeepWatching = true;
      mapsReassessStartPolling(token, approved.sid);
      mapsReassessTouchStatus();
    }
    return;
  }
  /* BASIS_CHANGED_DURING_REASSESSMENT (Phase 6.2): the record moved WHILE the re-evaluation ran, so nothing was
     committed. It takes the same honest path as the other conflicts: the fresh preview is shown and the person
     confirms again. The expensive synthesis is never resent from here. */
  if (status === 409 && (code === 'CHECKPOINT_CHANGED' || code === 'REVISION_CHANGED' || code === 'BASIS_CHANGED_DURING_REASSESSMENT')) {
    const fresh = detail && detail.preview;
    const duringRun = code === 'BASIS_CHANGED_DURING_REASSESSMENT';
    const title = duringRun ? 'Your record changed during the re-evaluation.' : 'Your record changed while you were confirming.';
    const shown = duringRun ? ((detail && detail.message) || 'Your record changed during the re-evaluation, so nothing was committed. This is the current check.') : message;
    if (fresh) {
      mapsCacheReassessPreview(approved.sid, fresh);
      LIVE.reassessApproved = mapsReassessApprovedFrom(fresh, approved.sid, token);
      mapsReassessShowOutcome(token, mapsReassessConfirmSheet(fresh, shown || 'Your record changed while you were confirming. This is the current check.'),
        title + ' Open Maps to review it.');
    } else {
      mapsReassessShowOutcome(token, mapsReassessHead('REASSESSMENT', title, shown)
        + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
          + '<button type="button" class="btn-secondary btn-sm" onclick="mapsOpenReassessment()">Check again</button>'),
        title + ' Open Maps to check again.');
    }
    return;
  }
  if (status === 409 && code === 'NOT_ELIGIBLE') {
    const elig = (detail && detail.eligibility) || (detail && detail.preview && detail.preview.eligibility) || {};
    const fresh = (detail && detail.preview) || { eligibility: elig, checkpoint: null, basis: {}, next_checkpoint_version: elig.next_checkpoint_version };
    LIVE.reassessApproved = mapsReassessApprovedFrom(fresh, approved.sid, token);
    mapsReassessShowOutcome(token, mapsReassessConfirmSheet(fresh, message), 'A reassessment is not available right now. Open Maps to see why.');
    return;
  }
  /* Any 5xx is a TECHNICAL failure, never a verdict about the plan, and the server's own code names
     which one it was (502 REASSESSMENT_TECHNICAL_FAILURE included). Try again reuses the SAME
     operation id, so a retry is idempotent: if the server did commit, it replays that checkpoint. */
  if (status >= 500) {
    const durable = code === 'CHECKPOINT_NOT_DURABLE';
    const tech = code === 'REASSESSMENT_TECHNICAL_FAILURE';
    mapsReassessShowOutcome(token, mapsReassessHead('REASSESSMENT',
      durable ? 'The new assessment could not be saved.'
        : (tech ? 'A technical error stopped the re-evaluation.' : 'The reasoning provider is unavailable.'),
      message)
      + '<p class="mcs-fine">This is a technical failure, not a decision about your plan.</p>'
      + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
        + '<button type="button" class="btn-primary btn-sm" onclick="mapsConfirmReassessment()">Try again</button>'),
      'The reassessment hit a technical failure. Open Maps to retry.');
    return;
  }
  mapsReassessShowOutcome(token, mapsReassessHead('REASSESSMENT', 'That did not go through.', message)
    + '<p class="mcs-fine">No commit is claimed for this request.</p>'
    + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
      + '<button type="button" class="btn-secondary btn-sm" onclick="mapsOpenReassessment()">Check again</button>'),
    'The reassessment did not go through. Open Maps to try again.');
}

/* The read-only reconciliation used after an ambiguous failure. liveReconcileReassessment owns the
   GET /checkpoints read and never POSTs. The approved operation id is the ONLY proof of attribution:
   the checkpoint id only says which version the person approved from, so a newer checkpoint is
   adopted only when the server reports mine === true. */
async function mapsReconcileNewer(expectedCheckpointId, operationId) {
  const expectedId = String(expectedCheckpointId || '');
  const op = String(operationId || '');
  if (typeof liveReconcileReassessment !== 'function') {
    return mapsReconcileOutcome({ status: 'unknown', mine: false, checkpoint: null, latest: null,
      error: 'the reconciliation read is not available' }, expectedId);
  }
  try {
    return mapsReconcileOutcome(await liveReconcileReassessment(expectedId, op), expectedId);
  } catch (e) {
    return mapsReconcileOutcome({ status: 'unknown', mine: false, checkpoint: null, latest: null,
      error: (e && e.message) ? e.message : String(e) }, expectedId);
  }
}
/* Classify one reconciliation read into the ONE answer the recovery may state:
     mine     - this operation's checkpoint is the newest one (adopt it);
     expected - the approved checkpoint is still the latest, i.e. the pre-submit state;
     other    - a different newer checkpoint we cannot attribute to this request;
     none     - no checkpoint exists at all;
     unknown  - the read failed or could not be matched, so the commit status stays unknown.
   Nothing is upgraded by the id comparison alone: only mine === true adopts a checkpoint. */
function mapsReconcileOutcome(rec, expectedId) {
  const r = rec || {};
  const status = String(r.status || '');
  const latest = (r.latest && r.latest.checkpoint_id) ? r.latest
    : ((r.checkpoint && r.checkpoint.checkpoint_id) ? r.checkpoint : null);
  if (status === 'none') return { outcome: 'none', checkpoint: null, latest: null, error: '' };
  if (status !== 'committed' && status !== 'moved') {
    return { outcome: 'unknown', checkpoint: null, latest: latest,
      error: String(r.error || 'the read did not complete') };
  }
  if (!latest) {
    return { outcome: 'unknown', checkpoint: null, latest: null,
      error: String(r.error || 'the read returned no checkpoint') };
  }
  if (expectedId && String(latest.checkpoint_id || '') === String(expectedId)) {
    return { outcome: 'expected', checkpoint: null, latest: latest, error: '' };
  }
  if (r.mine === true) return { outcome: 'mine', checkpoint: latest, latest: latest, error: '' };
  return { outcome: 'other', checkpoint: null, latest: latest, error: '' };
}
async function mapsReassessCheckNow() {
  if (IS_DEMO || !LIVE.sid) return;
  const sid = LIVE.sid;
  const token = ++LIVE.reassessToken;
  const ambiguousApproved = (LIVE.reassessAmbiguous && LIVE.reassessAmbiguous.approved) || null;
  const approved = LIVE.reassessApproved || ambiguousApproved || null;
  const approvedId = (approved && approved.checkpointId) || (STORE.pendingChangeSummary && STORE.pendingChangeSummary.expectCheckpointId) || '';
  const approvedOp = (approved && approved.op) || (ambiguousApproved && ambiguousApproved.op) || '';
  mapsReassessStopPolling();
  mapsReassessOpenSheet(token, mapsReassessHead('REASSESSMENT', 'Checking what is on record…', 'A read-only check: nothing is submitted and nothing is changed by it.'));
  const rec = (await mapsReconcileNewer(approvedId, approvedOp)) || { outcome: 'unknown' };
  if (LIVE.sid !== sid || !mapsReassessSheetVisible(token)) return;
  const outcome = String(rec.outcome || 'unknown');
  if (outcome === 'mine' && rec.checkpoint && rec.checkpoint.checkpoint_id) {
    await mapsReassessAcceptedFromRead(rec.checkpoint, sid);
    return;
  }
  if (outcome === 'unknown' || outcome === 'mine') {
    const detail = rec.error ? ' (' + rec.error + ')' : '';
    const readFailed = !rec.latest;
    mapsReassessOpenSheet(token, mapsReassessHead('REASSESSMENT',
      readFailed ? 'The record could not be read.' : 'The commit status is still unknown.',
      (readFailed ? 'The read-only check did not come back' : 'The newest checkpoint on record could not be matched to this request')
        + detail + ', so the commit status of this reassessment is still unknown.')
      + '<p class="mcs-fine">Nothing was submitted again. Checking again only reads your record.</p>'
      + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
        + '<button type="button" class="btn-primary btn-sm" onclick="mapsReassessCheckNow()">Check again</button>'));
    return;
  }
  if (outcome === 'other') {
    const latest = rec.latest || {};
    const version = latest.version != null ? ' (checkpoint v' + latest.version + ')' : '';
    mapsReassessOpenSheet(token, mapsReassessHead('REASSESSMENT', 'A newer checkpoint is already on record.',
      'A different, newer checkpoint is now on record for this map' + version + ', and this request cannot be attributed to it. Nothing here claims that your reassessment produced it.')
      + '<p class="mcs-fine">Checking again only reads your record. Review and reassess starts a fresh check and confirmation.</p>'
      + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
        + '<button type="button" class="btn-secondary btn-sm" onclick="mapsReassessCheckNow()">Check again</button>'
        + '<button type="button" class="btn-primary btn-sm" onclick="mapsOpenReassessment()">Review and reassess</button>'));
    return;
  }
  const preSubmit = outcome === 'expected' && !!(approved && approved.checkpointId);
  mapsReassessOpenSheet(token, mapsReassessHead('REASSESSMENT', 'No new checkpoint is on record yet.',
    preSubmit
      ? 'The checkpoint you approved is still the latest on record, so no newer one has been committed yet. The re-evaluation is still running, or it stopped before committing. Nothing was submitted again.'
      : 'The re-evaluation is still running, or it stopped before committing. Nothing was submitted again.')
    + mapsReassessFoot('<button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>'
      + '<button type="button" class="btn-secondary btn-sm" onclick="mapsReassessCheckNow()">Check now</button>'
      + '<button type="button" class="btn-primary btn-sm" onclick="mapsOpenReassessment()">Review and reassess</button>'));
}
/* A checkpoint found by a READ (never by a POST) and PROVED to belong to the approved operation. It is
   shown as the committed result and the read models are refreshed like any other commit. The receipt
   keeps the 200 shape; replayed is true because the recovery proved this operation already committed. */
async function mapsReassessAcceptedFromRead(cp, sid) {
  LIVE.reassessReceipt = { checkpoint: cp, previous_checkpoint: null, replayed: true, plan: null };
  LIVE.reassessAmbiguous = null;
  LIVE.reassessApproved = null;
  const expectId = cp.checkpoint_id;
  const ok = await mapsReassessRefresh(expectId);
  LIVE.lastRefreshFailed = !ok;
  STORE.pendingChangeSummary = { source: 'reassess', expectCheckpointId: expectId, refreshFailed: !ok };
  if (STORE.currentScreen === 'maps') { closeModal(); renderScreenKeepingUi('maps'); }
  else {
    showToast(ok ? 'A new assessment is on record.' : 'A new assessment is on record. Open Maps to read it.', '', '', ok ? '' : 'error');
    renderScreenKeepingUi(STORE.currentScreen);
  }
}
/* Maps workspace (wireframe 2026-10), shared by Explore and Readiness: one head, one toolbar (count left, lens switch
   right), one path panel on the right. Switching lenses only swaps the stage under the toolbar, so nothing above it or
   beside it moves. */
function mapsWorkspaceHtml(snap, stage, panelSel, preview) {
  const closed = !!STORE.mapsInspectorClosed;
  return `
  <div class="mp-page is-landscape mpr-page mpw is-lens-${mapsViewNow()}${closed ? ' is-collapsed' : ''}">
    <div class="mpw-main">
      <div class="mpw-inner">
        <h1 class="sr-only">Maps</h1>
        <div class="mpw-banners" id="maps-page-banners"></div>
        <section class="mpr-main" aria-labelledby="mpr-map-h">
          <div class="mpw-bar">${stateBadge('paths')}<h2 id="mpr-map-h">Possible paths <span class="st-count">${snap.paths.length}</span></h2>${renderMapsViewSwitch()}${closed ? wsPanelShowBtn('mp-panel-toggle', 'mp-panel', 'setMapsInspector', 'path details') : ''}</div>
          <div class="mpw-stage" id="mpw-stage">${stage}</div>
        </section>
      </div>
    </div>
    ${closed ? '' : `<aside class="mpr-panel mpw-panel has-panel-hide" aria-label="Path details">
      ${wsPanelHideBtn('mp-panel-toggle', 'mp-panel', 'setMapsInspector', 'path details')}
      <div class="mp-panel" id="mp-panel">${mapsPanelHtml(snap, panelSel, preview)}</div>
    </aside>`}
    <div class="sr-only" role="status" id="mp-status"></div>
  </div>`;
}
/* The path panel's toggle (top bar): » hides it, « brings it back; it says which it will do */
function mapsPanelToggle(closed) {
  const label = closed ? 'Show path details' : 'Hide path details';
  return `<button type="button" class="cw-ctx-toggle mpr-toggle${closed ? '' : ' is-on'}" aria-expanded="${!closed}" aria-controls="mp-panel" onclick="setMapsInspector(${closed})" title="${label}">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${closed ? '<path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/>' : '<path d="m6 17 5-5-5-5"/><path d="m13 17 5-5-5-5"/>'}</svg>
        <span class="cw-ctx-label">${label}</span>
      </button>`;
}
/* Closing the inspector gives the map the width; the selection stays, and reopening shows the same path */
function setMapsInspector(open) {
  STORE.mapsInspectorClosed = !open;
  STORE.restoreFocus = '.mp-panel-toggle';
  renderScreen('maps');
}

function openPathTrailDrawer(pathId) {
  const snap = V11_ENGINE.snapshot();
  const p = snap.paths.find(x => x.id === pathId);
  if (!p) return;
  const ev = snap.evidence.filter(e => (p.evidence_ids || []).includes(e.id));
  const sec = (label, inner) => `<div class="rv-sec"><div class="section-meta-label">${label}</div>${inner}</div>`;
  const reqList = (label, rows, icon) => rows.length ? sec(label,
    rows.map(r => `<div class="rd-item"><div class="rd-item-name">${reqMark(icon)}${stratEsc(r.label)}</div></div>`).join('')) : '';
  const secs = [
    sec('WHY IT IS ON YOUR MAP', `<p class="v11-prose-sm" style="margin:0">${stratEsc(provText(p.provenance))}. This path is on your map because it applies to your goal and situation as they are on record. Nobody ranked it against the others.</p>`),
    reqList('WHAT THE EVIDENCE SUPPORTS', p.requirements.filter(r => r.satisfaction === 'PRESENT'), 'PRESENT'),
    reqList('PARTLY SHOWN', p.requirements.filter(r => r.satisfaction === 'PARTIAL'), 'PARTIAL'),
    reqList('NOT KNOWN YET', p.requirements.filter(r => r.satisfaction === 'UNKNOWN'), 'UNKNOWN'),
    reqList('WHAT HOLDS IT BACK', p.requirements.filter(r => r.satisfaction === 'ABSENT'), 'ABSENT'),
    ev.length ? sec('THE EVIDENCE BEHIND THIS', ev.map(e => `<div class="rd-item"><div class="rd-item-name is-light">“${stratEsc(e.quote)}”${e.disputed ? ' <span class="v11-disputed-badge">DISPUTED</span>' : ''}</div><div class="rd-item-note">${stratEsc(provText(e.source))}</div></div>`).join('')) : '',
    p.stop_source ? sec('WHY IT IS STOPPED', `<p class="v11-prose-sm" style="margin:0"><strong>${p.stop_source === 'you' ? 'Stopped by you.' : 'Stopped by the evidence.'}</strong> ${STOP_BY_NOTE[p.stop_source === 'you' ? 'you' : 'numbers']}</p>`) : '',
    (p.trail || []).length ? sec('THE TRAIL: WHAT HAPPENED, IN ORDER', p.trail.map(t => `<div class="v11-trail-item"><span>${stratEsc(provText(t))}</span></div>`).join('')) : ''
  ].filter(Boolean);
  openWhyDrawer('PATH DETAIL', stratEsc(p.title), 'Everything on record about this path.', `<div class="rv-sec" style="gap:22px">${secs.join('')}</div>`);
}
function resumeStoppedPath(pathId) {
  if (!IS_DEMO) {
    /* HOTFIX: in LIVE mode V11_ENGINE.apply() is a no-op — the map is read from the server, not
       mutated locally — so claiming "Recorded" would be a false persisted change. Route the user to
       TALK, where reporting a change goes through the canonical semantic path. */
    showToast('Nothing is recorded from here. Tell us what has changed and the map re-checks it.');
    openTalkAbout(pathId);
    return;
  }
  V11_ENGINE.apply(null, { type: 'path-resumed-by-you', path_id: pathId });
  showToast('Recorded: you chose to go ahead anyway. The trail keeps both facts.');
  renderScreen('maps');
}
function stoppedPathFor(id) {
  const snap = V11_ENGINE.snapshot();
  const paths = (snap.paths || []).filter(p => p.status_display === 'STOP');
  return { snap, p: paths.find(p => p.id === id) || paths[0] || null };
}
function openStopModal(pathId) {
  const { snap, p } = stoppedPathFor(pathId);
  if (!p) { showToast('No stopped path is on record for this map.'); return; }
  STORE.stopModalPath = p.id;
  const byYou = p.stop_source === 'you';
  const live = (p.requirements || []).filter(r => r.applicable !== false);
  const absent = live.filter(r => r.satisfaction === 'ABSENT');
  const unknown = live.filter(r => r.satisfaction === 'UNKNOWN' || r.satisfaction === 'PARTIAL');
  const ev = (snap.evidence || []).filter(e => (p.evidence_ids || []).includes(e.id));
  const reqRows = (rows, word) => rows.map(r => `<li>${reqMark(r.satisfaction, 'sm')}<span><b>${stratEsc(r.label)}</b> <span class="rd-need-word">${word(r)}</span></span></li>`).join('');
  const title = byYou ? 'You paused this path.' : absent.length ? 'The evidence on record goes against this path.' : 'This path is stopped until something is known.';
  const lead = byYou ? STOP_BY_NOTE.you
    : absent.length ? 'Something this path needs is recorded as not in place. Effort alone does not change that; new evidence can.'
    : 'What this path depends on has not been established yet. It is stopped, not ruled out.';
  document.getElementById('modal-content').innerHTML = `
    <div class="rv-modal sp-modal">
      <div class="rv-sheet-head">
        <div>
          <div class="rv-labrow">
            <span class="section-meta-label">${stratEsc(p.title)}</span>
            <span class="mp-state stop">${byYou ? 'STOP · BY YOU' : 'STOP · BY THE EVIDENCE'}</span>
          </div>
          <h2 class="serif-heading" id="sp-title">${title}</h2>
          <p class="rv-sheet-lead">${lead}</p>
        </div>
        <button type="button" class="rv-x" onclick="closeModal()" aria-label="Close">✕</button>
      </div>
      ${absent.length ? `<section class="sp-sec" aria-labelledby="sp-against"><h3 class="sp-h" id="sp-against">What goes against it</h3><ul class="rd-need-list">${reqRows(absent, () => 'not in place')}</ul></section>` : ''}
      ${unknown.length ? `<section class="sp-sec" aria-labelledby="sp-unknown"><h3 class="sp-h" id="sp-unknown">Not known yet</h3><ul class="rd-need-list">${reqRows(unknown, r => r.satisfaction === 'PARTIAL' ? 'partly shown' : 'not known yet')}</ul><p class="sp-fine">Not known is not no.</p></section>` : ''}
      ${ev.length ? `<section class="sp-sec" aria-labelledby="sp-ev"><h3 class="sp-h" id="sp-ev">On record</h3>${ev.map(e => `<blockquote class="mv-quote">“${stratEsc(e.quote)}”${e.disputed ? ' <span class="v11-disputed-badge">DISPUTED</span>' : ''}<cite>${stratEsc(provText(e.source))}</cite></blockquote>`).join('')}</section>` : ''}
      ${(p.trail || []).length ? `<p class="sp-fine">${p.trail.map(t => stratEsc(provText(t))).join(' · ')}</p>` : ''}
      ${byYou ? '' : `<p class="sp-note">There is no “go ahead anyway” here. If something has changed, for example new savings, a first buyer or a different plan, tell us. The path is re-checked from the new record.</p>`}
      <div class="rv-foot">
        <button type="button" class="btn-secondary btn-sm" onclick="closeModal()">Close</button>
        ${byYou
          ? `<button type="button" class="btn-primary btn-sm" onclick="closeModal();resumeStoppedPath('${p.id}')">Resume this path</button>`
          : `<button type="button" class="btn-secondary btn-sm" onclick="closeModal();openReadiness('${p.id}')">See what it needs</button>
             <button type="button" class="btn-primary btn-sm" onclick="closeModal();openTalkAbout('${p.id}')">Tell us what has changed →</button>`}
      </div>
    </div>`;
  const card = document.getElementById('modal-content');
  card.setAttribute('aria-labelledby', 'sp-title');
  card.removeAttribute('aria-label');
  document.getElementById('stop-modal').classList.add('open');
  overlayOpened('stop-modal');
}

/* The Maps destination: zero paths, or one of the two lenses (Explore, Readiness).
   Live seam: the projection arrives from its own request; ask for it once and say so
   meanwhile (never a failure before it has failed). */
function screenMaps11() {
  const snap = V11_ENGINE.snapshot();
  const view = mapsViewNow();
  if (!IS_DEMO && LIVE.projection === null && LIVE.projectionTried !== LIVE.sid && LIVE.sid && !V11_ENGINE.injected) {
    liveLoadReadiness().then(() => { if (STORE.currentScreen === 'maps') renderScreen('maps'); });
    if (!snap.paths.length && !(snap.zero && snap.zero.kind === 'LEGACY_ARTIFACT')) {
      return renderAppShell('maps', MAPS_VIEW_LABEL[view], `<div class="mp-page"><div class="mp-head">${v11PageHead({ dest: 'Maps', title: 'Reading your map…' })}</div><p class="v11-lead" role="status">One moment while we read what each path needs.</p></div>`);
    }
  }
  if (!snap.paths.length) return screenMapsZero(snap, view);
  if (view === 'readiness') { mapsSeedReadinessDefault(snap); return screenReadiness(snap); }
  return screenLandscape(snap);
}
