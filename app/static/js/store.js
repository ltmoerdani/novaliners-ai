/* Store + timeline */
/* Reactive State */
const STORE = {
  currentScreen: '04',
  currentPersona: 'dimas',
  selectedMapPath: 'warm',
  selectedModalChip: 'rather-not',
  selectedModalAction: 'capped',
  checkInOutcome: 'worked',
  checkInData: {
    contacted: 7,
    replies: 4,
    calls: 2,
    paid: 'Rp15.000.000',
    paidRaw: 15
  },
  todayMsgLang: 'en',
  chatEvidenceOpen: window.innerWidth >= 1100,   // as in the prototype: open beside the chat on wide windows
  guide5PhaseOpen: true,
  sidebarCollapsed: false,
  projectDropdownOpen: false,
  intakePrompt: '',
  chatStep: 0,
  chatAnswerSubmitted: false,
  chatUserAnswer1: '',
  chatUserAnswer2: '',
  chatUserAnswer3: '',
  chatUserAnswer4: '',
  chatUserAnswer5: '',
  chatUserAnswer: '',
  /* v11 workspace state (shell, Maps lenses, Talk). Same fields as the prototype's STORE. */
  // Rail is the default at every width. Expanded is a user choice, remembered only where it pushes the layout (>1180).
  sidebarExpanded: (() => { try { return window.innerWidth > 1180 && localStorage.getItem('nova.v11.sidebar') === 'expanded'; } catch (e) { return false; } })(),
  restoreFocus: null,        // selector to refocus after the shell re-renders (keyboard continuity)
  mapsView: 'landscape',     // Maps lens: 'landscape' (Explore) | 'readiness' (one workspace, two lenses)
  mapsLens: 'landscape',     // the map-bearing lens you were last on: where Readiness's back link returns
  mapsInspectorClosed: false, // Maps: the docked path panel is hidden (the map takes the full width). Same as the prototype.
  mapsSelBy: {},             // Maps: selected path (or 'start' / 'goal') per map: one source for canvas, cards and panel
  mapsSelDefaultBy: {},      // Maps: the path id stored in mapsSelBy as a presentation default the person did not choose
  talkAbout: null,           // Talk: the path the conversation was opened from, carried as context
  talkAboutNext: null,
  settingsMenuOpen: false,
  newMapFlow: false,
  ctxMenuOpen: false,       // route switcher popover in the top bar (phase-1 shell)
  ctxFilter: 'all',          // route switcher filter pill: all | active | sample | saved
  stateSideClosed: false,    // State inspector (the split pane's right column) is folded away
  journeySideClosed: false,  // Journey inspector (what is on hold) is folded away
  movesSideClosed: false,    // Moves inspector (progress and detail) is folded away
  talkSideClosed: false,     // Talk context rail (the split pane's right column) is folded away
  movesSideTopic: null,      // the Moves panel topic that was asked for (null = every row folded, as in the prototype)
  wsPanelEnter: false        // the panel was just brought back: play the slide-in once
};
/* Project Info Helper */
function getActiveProjectInfo() {
  if (!IS_DEMO) {
    const g = liveGoal();
    return { name: liveGoalTitle(), cycle: `Cycle ${liveTimeline().cycle}`, current: g.current != null ? fmtM(g.current) : 'Rp0', target: g.target != null ? fmtM(g.target) : '' };
  }
  const p = STORE.currentPersona || 'dimas';
  const c = STORE.cycle || 1;
  if (p === 'dimas') {
    return { 
      name: 'Brand Strategy Studio', 
      cycle: `Cycle ${c}`, 
      current: STORE.earnedThisMonth ? `Rp${STORE.earnedThisMonth}M` : 'Rp0',
      target: c >= 3 ? 'Rp60M' : 'Rp30M'
    };
  } else if (p === 'rina') {
    return { name: "Rina's Craft Studio", cycle: 'Cycle 1', current: 'Rp12M', target: 'Rp35M' };
  } else if (p === 'arif') {
    return { name: "Arif's IT Consulting", cycle: 'Cycle 3', current: 'Rp45M', target: 'Rp80M' };
  } else {
    return { name: "Bayu's Software Studio", cycle: 'Cycle 1', current: 'Rp0M', target: 'Rp25M' };
  }
}
/* ==========================================================================
   ROADMAP STORE: one reactive source of truth for progress, shared by
   Today, Path map and Journey. Same shape as a Zustand store
   (getState / setState / subscribe), written in plain JS for this prototype.
   ========================================================================== */
function createStore(initializer) {
  let state;
  const listeners = new Set();
  const getState = () => state;
  const setState = (partial) => {
    const prev = state;
    const next = typeof partial === 'function' ? partial(state) : partial;
    state = Object.assign({}, state, next);
    listeners.forEach(fn => fn(state, prev));
  };
  const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
  state = initializer(setState, getState);
  return { getState, setState, subscribe };
}
/* Steps are tasks with prerequisites, not calendar slots. Per step:
     done       finished (in any order, several per day)
     ready      not done and every step it needs is done: can be started now
     waitingFor the unmet prerequisites (numbers)
     status     COMPLETED | CURRENT (the suggested next: first ready step) | UPCOMING (ready or waiting)
   `doneNums`/`doneDays` say what is finished and on which day; without them (legacy callers) every step before
   `currentStep` counts as done. */
function stepNeedsOf(d, defs) {
  if (d.report) return defs.filter(x => !x.report).map(x => x.num);
  return d.needs || (d.num > 1 ? [d.num - 1] : []);
}
function buildSteps(cycle, currentStep, pathId, doneNums, doneDays) {
  const defs = cycle === 1
    ? CYCLE1_STEPS
    : getCycle2Plan(pathId).steps.map((st, i) => Object.assign({ num: i + 1 }, st, cycleDays(cycle)[i]));
  const done = doneNums || defs.filter(d => d.num < currentStep).map(d => d.num);
  const days = doneDays || {};
  const rows = defs.map(d => {
    const needs = stepNeedsOf(d, defs);
    const waitingFor = needs.filter(n => !done.includes(n));
    const isDone = done.includes(d.num);
    return Object.assign({}, d, {
      id: `c${cycle}-step-${d.num}`, needs, waitingFor, done: isDone,
      ready: !isDone && !waitingFor.length, doneDay: days[d.num] || null
    });
  });
  const next = rows.find(r => r.ready);
  return rows.map(r => Object.assign(r, {
    status: r.done ? STEP_STATUS.COMPLETED : (next && r.num === next.num ? STEP_STATUS.CURRENT : STEP_STATUS.UPCOMING)
  }));
}
function suggestedStep(steps) {
  return steps.find(s => s.status === STEP_STATUS.CURRENT) || steps[steps.length - 1];
}

const useRoadmapStore = createStore((set, get) => Object.assign(IS_DEMO ? {
  currentCycle: 1,
  currentStep: 2,
  currentDay: 3,
  doneNums: [1],        // steps finished this cycle, and the day each was finished on
  doneDays: { 1: 2 },
  steps: buildSteps(1, 0, 'warm', [1], { 1: 2 }),
  activeNodeId: 'c1-step-2',
  activePathId: 'warm',
  activePaths: ['warm'],
  earned: 0,
  moneySaved: 20,
  goalRp: 30,
  history: [],          // one record per check-in: what happened, income after it, money saved
  ending: null,         // 'miss' | 'success' once Day 90 is reviewed
  lastEvent: null
} : {
  // Live: blank until liveBoot() / liveLoadSession() hydrate it from the engine (syncStoreFromLive)
  currentCycle: 1, currentStep: 1, currentDay: 1, doneNums: [], doneDays: {}, steps: [], activeNodeId: '',
  activePathId: '', activePaths: [], earned: 0, moneySaved: null, goalRp: 0,
  history: [], ending: null, lastEvent: null
}, {

  // Save a check-in result and start the next cycle on the chosen path
  recordCheckIn(rec, nextPathId) {
    const state = get();
    const record = Object.assign({ cycle: state.currentCycle, day: Math.min(state.currentCycle * 7, GOAL_DAY), path: state.activePathId }, rec);
    set({ history: state.history.concat([record]) });
    if (rec.outcome === 'final') {
      set({ earned: rec.rp, moneySaved: rec.saved !== undefined ? rec.saved : state.moneySaved, ending: rec.ending || 'miss', currentDay: GOAL_DAY, lastEvent: { type: 'goal-day-reached' } });
      return;
    }
    get().startCycle({
      cycle: state.currentCycle + 1,
      pathId: nextPathId,
      earned: rec.rp,
      moneySaved: rec.saved,
      activePaths: rec.paths
    });
  },

  reset() {
    STORE.selectedMapPath = 'warm';
    set({
      currentCycle: 1, currentStep: 2, currentDay: 3, doneNums: [1], doneDays: { 1: 2 },
      steps: buildSteps(1, 0, 'warm', [1], { 1: 2 }), activeNodeId: 'c1-step-2',
      activePathId: 'warm', activePaths: ['warm'], earned: 0, moneySaved: 20, goalRp: 30,
      history: [], ending: null, lastEvent: { type: 'reset' }
    });
    STORE.viewStep = 0;
  },

  // Look at a step (e.g. clicking a row in the checklist). Only what Today shows changes: the suggested next step
  // and everything that is done stay as they are.
  goToStep(num) {
    const { currentStep, steps } = get();
    STORE.viewStep = num === currentStep ? 0 : num;
    set({ lastEvent: { type: 'step-selected', stepId: (steps[num - 1] || {}).id } });
  },

  // Finish any step that is ready, in any order and as many per day as you like. Steps that were waiting on it
  // become ready; the day does not move (it only moves with time: see advanceDay).
  completeStep(num) {
    const st = get();
    const step = st.steps[num - 1];
    if (!step || !step.ready || step.report) return false;
    const doneNums = st.doneNums.concat([num]);
    const doneDays = Object.assign({}, st.doneDays, { [num]: st.currentDay });
    const steps = buildSteps(st.currentCycle, 0, st.activePathId, doneNums, doneDays);
    const next = suggestedStep(steps);
    const unlocked = steps.filter(s => s.ready && !st.steps[s.num - 1].ready).map(s => s.id);
    STORE.selectedMapPath = toMapPath(st.activePathId);
    STORE.viewStep = 0;
    set({ doneNums, doneDays, steps, currentStep: next.num, activeNodeId: next.id, lastEvent: { type: 'step-completed', stepId: step.id, unlockedIds: unlocked } });
    return true;
  },
  completeCurrentStep() { return get().completeStep(get().currentStep); },

  // Time passes on its own (a day per day); the review widget can nudge it to see the plan across days
  advanceDay(n) {
    const st = get();
    if (st.ending) return;
    set({ currentDay: Math.min(st.currentDay + (n || 1), Math.min(st.currentCycle * 7, GOAL_DAY)), lastEvent: { type: 'day-advanced' } });
  },

  // Start a new cycle after a check-in
  startCycle({ cycle, pathId, earned, moneySaved, activePaths }) {
    const steps = buildSteps(cycle, 1, pathId || get().activePathId, [], {});
    if (pathId) STORE.selectedMapPath = toMapPath(pathId);
    STORE.viewStep = 0;
    set(state => ({
      currentCycle: cycle,
      currentStep: suggestedStep(steps).num,
      currentDay: steps[0].day,
      doneNums: [],
      doneDays: {},
      steps,
      activeNodeId: suggestedStep(steps).id,
      activePathId: pathId || state.activePathId,
      activePaths: activePaths || state.activePaths,
      earned: earned !== undefined ? earned : state.earned,
      moneySaved: moneySaved !== undefined ? moneySaved : state.moneySaved,
      lastEvent: { type: 'cycle-started', cycle }
    }));
  },

  setMetrics(metrics) {
    set(metrics);
  }
}));

// Read-only aliases so existing screens keep reading STORE.cycle / STORE.todayStep etc.
[['cycle', 'currentCycle'], ['todayStep', 'currentStep'], ['earnedThisMonth', 'earned'], ['capitalProtected', 'moneySaved']].forEach(([alias, key]) => {
  Object.defineProperty(STORE, alias, {
    get: () => useRoadmapStore.getState()[key],
    set: () => { throw new Error(`STORE.${alias} is read-only. Use a useRoadmapStore action.`); }
  });
});

// Reactivity: any screen that shows progress re-renders when the store changes, without a page reload
const PROGRESS_SCREENS = ['moves', 'maps', 'journey', 'state'];
useRoadmapStore.subscribe(() => {
  if (PROGRESS_SCREENS.includes(STORE.currentScreen)) renderScreen(STORE.currentScreen);
});

/* Timeline Helper: Cycle & Day shown anywhere in the app come from the roadmap store.
   A cycle is 7 days; `day` counts from the start of the 90-day goal. */
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
function getTimeline() {
  if (!IS_DEMO) return liveTimeline();
  const p = STORE.currentPersona || 'dimas';
  let cycle, day;
  if (p === 'arif') {
    cycle = 3; day = 15;
  } else if (p !== 'dimas') {
    cycle = 1; day = 1;
  } else {
    const rs = useRoadmapStore.getState();
    cycle = rs.currentCycle;
    day = rs.currentDay;
  }
  return {
    cycle,
    cycleDay: day - (cycle - 1) * 7,
    day,
    daysLeft: Math.max(GOAL_DAY - day, 0),
    weekday: WEEKDAYS[(day - 1) % 7],
    nextCheckIn: Math.min(cycle * 7, GOAL_DAY)
  };
}
