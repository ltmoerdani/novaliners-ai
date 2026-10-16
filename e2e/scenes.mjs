// Shared scene lists. The MVP in demo mode (?demo=1) and the v11 prototype expose the same design-review API (goDestination,
// setMapsView, renderScreen), so one act runs in both pages.
//   PARITY_SCENES   the seven canonical frames at the eight responsive viewports (parity.spec.mjs, visual.spec.mjs)
//   scenes          [name, JS] for the copy guard in demo mode: the destinations (light and dark) and the entry,
//                   check-in, map-change and ending screens that are still in the product (copy.spec.mjs)
export const VIEWPORTS = [
  { w: 1440, h: 900 }, { w: 1280, h: 800 }, { w: 1180, h: 800 }, { w: 1024, h: 768 },
  { w: 900, h: 800 }, { w: 768, h: 1024 }, { w: 390, h: 844 }, { w: 320, h: 800 },
];
const TOP = [{ sel: '#v11-main h1', min: 1 }, { sel: '.v11-topnav-item', min: 5 }];
const LENS = [
  { sel: '.mpw', min: 1 },                                   // the one workspace
  { sel: '.mpw-bar', min: 1 },                               // the section bar: icon, count, switch — above the stage, never inside it
  { sel: '#mpw-stage', min: 1 },                             // the only part a lens change may swap
  { sel: '.mpw-bar .v11-view-switch button', min: 2 },
  { sel: '.mpw-bar .v11-lens-name[data-label]', min: 2 },    // the reserved semibold width needs data-label
  { sel: '.v11-view-switch button', min: 2 },
  { sel: '#v12-map', min: 1 },
  { sel: '#mp-panel', min: 1 },
];
/* the parts only Explore carries: the key under the map (inside the frame, never back in a card) */
const LENS_EXPLORE = [{ sel: '.mpw .mpr-key', min: 1 }, { sel: '.mpw-panel .mp-actions, .mpw.is-collapsed .mpw .v11-pagehead-actions', min: 0 }];
/* the parts only Readiness carries: "Requirements by state" is always open, and the evidence is a fold */
const LENS_READINESS = [{ sel: '.rd-reqs-open', min: 1 }, { sel: '.rd-reqs-open .rd-group', min: 1 }, { sel: '.rd-evidence', min: 1 }];
export const PARITY_SCENES = [
  { name: 'state', act: 'goDestination("state")', anchors: [...TOP, { sel: '.btn-primary', min: 1 }] },
  { name: 'maps-landscape', act: 'goDestination("maps"); setMapsView("landscape")', anchors: [...TOP, ...LENS, ...LENS_EXPLORE] },
  // 'overview' is the OLD Overview address/route: since UX v11 it must resolve to Explore (doc 16 G-34), in both pages
  { name: 'maps-overview', act: 'goDestination("maps"); setMapsView("overview")', anchors: [...TOP, ...LENS, ...LENS_EXPLORE] },
  // Readiness on BOTH pages at this prototype commit does not render the map canvas (#v12-map: 0 visible
  // in proto and MVP — verified). The canvas anchor returns with the Maps phase (deferred: newer Maps work
  // is landing on main); the other readiness anchors still hold in both pages.
  { name: 'maps-readiness', act: 'goDestination("maps"); setMapsView("readiness")', anchors: [...TOP, { sel: '.v11-view-switch button', min: 2 }, { sel: '.rd-path-item', min: 5 }, { sel: '#rd-detail', min: 1 }, ...LENS_READINESS] },
  // Moves is a split-pane destination now: the frame anchors are shared again (featured card + docked panel).
  // .moves-queues stays OUT of the shared set: the prototype renders it only when other moves exist, while the
  // MVP keeps its own queues card unconditional (asserted on the MVP side by visual.spec).
  { name: 'moves', act: 'goDestination("moves")', anchors: [...TOP, { sel: '.today-actions .btn-primary', min: 1 }, { sel: '.mv-featured', min: 1 }, { sel: '#mv-side', min: 1 }] },
  { name: 'journey', act: 'goDestination("journey")', anchors: [...TOP, { sel: '.j-statcard', min: 4 }, { sel: '.j-chartcard', min: 1 }] },
  { name: 'talk', act: 'goDestination("talk")', anchors: [...TOP, { sel: '#talk-ongoing-input', min: 1 }, { sel: '.talk-send', min: 1 }, { sel: '#chat-messages-container', min: 1 }] },
];

const reset = 'resetSimulation(true);';
export const scenes = [];
const dest = (js) => `${reset} ${js}`;
for (const s of PARITY_SCENES) scenes.push([`dest-${s.name}`, dest(s.act)]);
for (const s of ['01', '02', '03', '05', '06a', '06b', '12', '13', '14', '15', '16'])
  scenes.push([`entry-${s}`, dest(`renderScreen('${s}')`)]);
scenes.push(['stop-modal', dest(`goDestination('maps'); setMapsView('overview'); renderScreen('11')`)]);
scenes.push(['why-drawer', dest(`renderScreen('09')`)]);
// Dark theme (v5 palette), last; 'theme-reset' puts the page back to light
for (const s of PARITY_SCENES) scenes.push([`dark-${s.name}`, `setTheme('dark'); ${dest(s.act)}`]);
for (const s of ['01', '05', '14', '16']) scenes.push([`dark-entry-${s}`, `setTheme('dark'); ${dest(`renderScreen('${s}')`)}`]);
scenes.push(['theme-reset', `setTheme('light'); ${dest('goDestination("state")')}`]);
