/* Demo simulation controls */
// Where to land after a check-in that triggers something worth seeing
const SIM_EVENT_SCREEN = { 'audit-open': 'maps', 'welcome-back': '14', ads: '11', 'cmo-open': 'maps', capacity: 'maps', ending: '16' };

function simulateNextCycle(scenario, opts) {
  const list = scenario || (STORE.simEnding === 'success' ? SCENARIO_SUCCESS : SCENARIO_MISS);
  if (STORE.currentPersona !== 'dimas') { STORE.currentPersona = 'dimas'; const ps = document.getElementById('persona-selector'); if (ps) ps.value = 'dimas'; }
  const rs = useRoadmapStore.getState();
  if (rs.ending) return;
  const rec = list[rs.currentCycle - 1];
  if (!rec) return;
  if (['worked', 'mixed', 'none'].includes(rec.outcome)) STORE.checkInOutcome = rec.outcome;
  rs.recordCheckIn(rec, rec.next);
  if (opts && opts.quiet) return;
  const screen = SIM_EVENT_SCREEN[rec.event] || (['moves', 'maps', 'journey'].includes(STORE.currentScreen) ? STORE.currentScreen : 'journey');
  renderScreen(screen);
  if (rec.outcome !== 'final') showToast(`Cycle ${rs.currentCycle} check-in: ${rec.title}`, screen === 'journey' ? '' : 'View journey →', 'journey');
  updateSimStatus();
}

function simulateToDay90(ending) {
  if (useRoadmapStore.getState().ending || ending !== STORE.simEnding) resetSimulation(true);
  STORE.simEnding = ending || 'miss';
  const list = STORE.simEnding === 'success' ? SCENARIO_SUCCESS : SCENARIO_MISS;
  while (!useRoadmapStore.getState().ending) simulateNextCycle(list, { quiet: true });
  renderScreen('16');
  updateSimStatus();
}

function resetSimulation(quiet) {
  STORE.simEnding = 'miss';
  STORE.checkInOutcome = 'worked';
  STORE.endingChoice = null;
  STORE.currentPersona = 'dimas';
  const ps = document.getElementById('persona-selector');
  if (ps) ps.value = 'dimas';
  MAP_MEMORY.doneIds = null; MAP_MEMORY.currentId = null; MAP_MEMORY.auditOpen = null; MAP_MEMORY.cmoOpen = null; MAP_MEMORY.progressLen = null;
  MAP_MEMORY.histLen = null; MAP_MEMORY.scrollKey = null; MAP_MEMORY.scrollLeft = null; MAP_MEMORY.gliding = false;
  useRoadmapStore.getState().reset();
  STORE.demoRoute = { icp: 'READY' };
  STORE.askDemoThread = null; STORE.askDraft = ''; STORE.askFocus = ''; STORE.readinessPath = '';
  if (!quiet) { renderScreen('04'); updateSimStatus(); }
}

// Let a day go by inside the current cycle (steps finished earlier keep the day they were finished on)
function advanceDemoDay() {
  useRoadmapStore.getState().advanceDay(1);
  updateSimStatus();
}

function updateSimStatus() {
  const el = document.getElementById('sim-status');
  if (!el) return;
  const rs = useRoadmapStore.getState();
  el.textContent = rs.ending ? `Day 90 · Rp${rs.earned}M a month` : `Cycle ${rs.currentCycle} · Day ${rs.currentDay} · Rp${rs.earned}M`;
}
useRoadmapStore.subscribe(() => updateSimStatus());
