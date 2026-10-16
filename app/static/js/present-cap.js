/* Presentation policy for Possible Paths (internal-docs §24.7).
 *
 *   ENGINE         Possible Paths = 0..N, as many as the evidence supports. Nothing here limits it.
 *   PRESENTATION   at most PATH_VIEW_CAP possibilities are drawn or listed at a time.
 *
 * The cap is about the reader's attention, not about what is true. It is NOT a completeness requirement
 * (five is never a target), NOT a hard limit on three, and it never invents a path to fill a slot. The paths it
 * does not draw stay in the data with their evidence and provenance, and the UI says so: "+3 other possibilities".
 *
 * Pure functions of their arguments: no DOM, no network, no globals besides these constants, so the policy can be
 * loaded on its own and tested exhaustively (e2e/presentation-cap.spec.mjs). */

const PATH_VIEW_CAP = 5;

/* The only ordering the policy knows: the engine's own status word (feasibility x lifecycle -> display_status),
 * so that what the reader can act on now is not pushed behind what is held. Ties keep the engine's order. It is a
 * way to choose what fits on screen, not a ranking of which path is better. */
const PATH_STATUS_RANK = { OPEN: 0, TEST_FIRST: 1, NOT_YET: 2, STOP: 3 };
const PATH_STATUS_LABEL = { OPEN: 'open', TEST_FIRST: 'test first', NOT_YET: 'not yet', STOP: 'stop' };

/* paths  [{ key, status, ... }] in the engine's order.
 * opts.cap     how many may be shown (default PATH_VIEW_CAP)
 * opts.pinned  keys that must stay visible when they exist (the current path, the one being looked at); a pinned
 *              path takes a slot before anything else, so looking at a path from the overflow list brings it
 *              into view instead of leaving the screen pointing at something that is not drawn.
 * Returns { visible, hidden, total, cap, overflow, summary }; `visible` and `hidden` keep the engine's order, and
 * together they are exactly the input: nothing dropped, nothing added. */
function presentPaths(paths, opts) {
  const list = Array.isArray(paths) ? paths.filter(Boolean) : [];
  const cap = Math.max(1, Math.floor((opts && opts.cap) || PATH_VIEW_CAP));
  const total = list.length;
  if (total <= cap) return { visible: list.slice(), hidden: [], total, cap, overflow: 0, summary: [] };
  const index = new Map(list.map((p, i) => [p.key, i]));
  const pins = [];
  ((opts && opts.pinned) || []).forEach(k => { if (index.has(k) && !pins.includes(k) && pins.length < cap) pins.push(k); });
  const rank = p => (p.status in PATH_STATUS_RANK ? PATH_STATUS_RANK[p.status] : 9);
  const rest = list.filter(p => !pins.includes(p.key))
    .sort((a, b) => (rank(a) - rank(b)) || (index.get(a.key) - index.get(b.key)));
  const chosen = new Set(pins.concat(rest.slice(0, cap - pins.length).map(p => p.key)));
  const visible = list.filter(p => chosen.has(p.key));
  const hidden = list.filter(p => !chosen.has(p.key));
  return { visible, hidden, total, cap, overflow: hidden.length, summary: pathStatusSummary(hidden) };
}

/* [{ status, n, label }] in status order, only the statuses that occur: what the reader cannot see, in numbers. */
function pathStatusSummary(paths) {
  return Object.keys(PATH_STATUS_RANK)
    .map(status => ({ status, n: paths.filter(p => p.status === status).length, label: PATH_STATUS_LABEL[status] }))
    .filter(x => x.n > 0);
}
