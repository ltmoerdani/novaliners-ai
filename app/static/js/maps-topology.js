/* NOVALINERS · Maps 2D — TOPOLOGY + GEOMETRY layer (pure, deterministic, DOM-free).
 *
 * ONE business map: one HERE anchor, one shared GOAL landmark, one horizontal backbone, and the
 * Paths as corridors that branch off the backbone and rejoin it (or stop). The shape is Git-like:
 * long horizontal runs, one turn out, one turn back, corners rounded by a small fixed radius —
 * never Bézier waves, never a fixed five-lane template.
 *
 * TWO TIERS OF CONNECTION, never conflated (int 03 §3, int 07 master §3):
 *   • STRATEGIC corridor — the visual continuity of a Path (HERE → its own lane → GOAL/STOP).
 *     It says "this is a direction the evidence puts in front of you". It proves NOTHING about
 *     dependency, readiness, execution or eventual goal achievement.
 *   • CANONICAL dependency — a RouteNode's real `depends_on`, inside ONE route. Authoritative.
 *     Route-local by construction (Release A ontology, int 08 §8.2): the server projection only
 *     ever emits dependencies that exist in the route's own revision.
 *
 * A relationship between two DIFFERENT routes is NOT invented here. When two routes happen to
 * settle the same requirement id, that is reported as `gaps` (strategic-only, non-authoritative)
 * and may be *marked* on a node — never merged into one checkpoint. Fabricating a cross-route
 * merge to make the picture prettier is exactly what this layer refuses to do.
 *
 * Nothing here re-derives a status: kinds come from the server projection, and a corridor the
 * server composed no route for keeps the honest fallback (count only, no nodes invented).
 *
 * Layout is order-based, not date-based: horizontal position along a corridor is the DEPENDENCY
 * layer of a step. No timeline is implied (INV-11).
 *
 * SEMANTIC ZOOM (int 04 §1, 2026-10 correction): `plan` takes a level — Z0 WORLD, Z1 PATH, Z2 ROUTE
 * (Z3 DETAIL is the inspector, not the canvas). Every RouteNode keeps ONE position at every level
 * (positions are computed for all nodes, then filtered), so zooming reveals and hides, never moves:
 *   Z0 — corridors only, plus the one focal step the server presents (exact route+node reference).
 *   Z1 — the selected corridor's landmarks: its whole frontier, its terminals and the focal step; the
 *        rest of its nodes fold into presentation clusters ("+N steps", never a canonical node).
 *   Z2 — the selected corridor's every RouteNode and its real depends_on edges (one route at a time).
 * A corridor ENDS at its own route terminal. It never rejoins the backbone into the GOAL: reaching
 * the end of a route is not the goal achieved (int 04 §2, K2/G14), and no corridor is drawn into the
 * goal just because its status is not STOP (the `endKind` anti-regression, doc 01 §2).
 *
 * Loaded before screens-live-map.js; exposes window.TOPO. No DOM access: unit-testable in node.
 */
(function (global) {
  'use strict';

  const VERSION = 'topo-1';
  const CORNER = 12;          // px — one value for every corner (int 04 §4: small rounded corners)
  const GAP = 12;             // px — vertical gap between corridor bands
  const BASE_MIN = 44;        // px — band of a corridor with no route: its line + one label line
  const NODE_BAND = 66;       // px — band of a corridor carrying RouteNodes (marker on the line + chip under it)
  const ROOMY = 168;          // px — band of the corridor opened for detail: parallel steps stack in rows
  const PAD_L = 64, PAD_R = 86;   // HERE label room on the left, GOAL label room on the right

  /* ── 1 · TOPOLOGY ─ the relationships, before any coordinate ───────────────────────────────── */
  /* The status of a corridor, from whichever name the presenter used for it. The map shape built by
     screens-live-map.js carries `status`; the raw snapshot path carries `status_display`. Reading
     only one of the two is what made every lane label read "undefined". */
  const statusOf = p => String((p && (p.status_display != null ? p.status_display : p.status)) || '');

  function build(shape) {
    const focusId = (shape && shape.focusId) || null;
    const corridors = ((shape && shape.paths) || []).map((p, i) => {
      const canon = p.canon || null;
      const cols = canon ? canon.cols : null;          // [[node…], …] by dependency depth
      const flat = cols ? cols.reduce((a, c) => a.concat(c), []) : [];
      const ids = {};
      flat.forEach(n => { ids[n.id] = 1; });
      const deps = [];
      if (cols) cols.forEach(col => col.forEach(n => (n.deps || []).forEach(d => {
        if (ids[d] && d !== n.id) deps.push({ from: d, to: n.id });     // route-local only
      })));
      const reqs = [];
      if (cols) cols.forEach(col => col.forEach(n => (n.reqs || []).forEach(r => reqs.push({ reqId: r, nodeId: n.id }))));
      const status = statusOf(p);
      return {
        idx: i,
        pathId: p.id,
        title: p.title,
        status,
        stop: status === 'STOP',
        stopSource: p.stop_source || null,
        relation: p.relation || p.goal_relation || null,
        inFocus: !!focusId && focusId === p.id,
        hasRoute: !!canon,
        routeId: canon ? canon.routeId : null,
        revision: canon ? canon.revisionNo : null,
        lineage: canon ? canon.lineage : null,
        applicability: canon ? canon.applicability : null,
        frontierKinds: canon ? (canon.frontier || []).map(f => f.kind) : [],
        frontierNodes: canon ? (canon.frontier || []).map(f => f.node_id || f.node).filter(Boolean) : [],   // projection emits node_id
        terminals: canon ? (canon.terminals || []).slice() : [],
        cols: cols ? cols.map(col => col.map(n => n.id)) : null,
        nodes: flat.map(n => ({
          id: n.id, label: n.label, title: n.title, kind: n.kind, fk: n.fk,
          sat: n.sat, exe: n.exe, view: n.view, deps: (n.deps || []).slice(),
          reqs: (n.reqs || []).slice(), terminal: !!n.terminal
        })),
        deps, reqs,
        total: cols ? flat.length : ((p.nodes || []).length)
      };
    });

    /* Which requirement ids are settled by more than one corridor? Two treatments, decided by the
       int 22 §38 guard: when the requirement's id, its wording and its state agree on EVERY holding
       path, it is drawn ONCE as a shared node (a group — the MVP reads the wording from the node's own
       label, the wording the map actually shows). Any disagreement falls back to the strategic
       marking: marked, never merged (Release A has no authoritative cross-route node identity). */
    const byReq = {};
    corridors.forEach(c => c.reqs.forEach(r => {
      if (!byReq[r.reqId]) byReq[r.reqId] = {};
      if (!byReq[r.reqId][c.pathId]) byReq[r.reqId][c.pathId] = r.nodeId;
    }));
    const shared = {};        // `${pathId}::${nodeId}` -> [pathId…] (other corridors)
    const ties = [], groups = [];
    Object.keys(byReq).sort().forEach(reqId => {
      const per = byReq[reqId];
      const pids = Object.keys(per);
      if (pids.length < 2) return;
      const holders = pids.map(pid => {
        const c = corridors.find(x => x.pathId === pid);
        const n = c && c.nodes.find(x => x.id === per[pid]);
        return { pathId: pid, nodeId: per[pid], sat: n ? n.sat : null, label: n ? n.label : null };
      });
      const agree = holders.every(h => h.sat === holders[0].sat && h.label === holders[0].label);
      ties.push({ reqId, links: holders.map(h => ({ pathId: h.pathId, nodeId: h.nodeId })), agree, authoritative: false });
      if (agree) groups.push({ reqId, label: holders[0].label, sat: holders[0].sat, links: holders.map(h => ({ pathId: h.pathId, nodeId: h.nodeId })) });
      pids.forEach(pid => {
        const others = pids.filter(x => x !== pid);
        shared[pid + '::' + per[pid]] = others;
      });
    });

    const gaps = [];
    if (ties.length) gaps.push({
      code: 'CROSS_ROUTE_SHARED_REQUIREMENT_STRATEGIC_ONLY',
      count: ties.length,
      detail: 'These requirement ids appear in more than one route. The Release A ontology has no ' +
        'authoritative cross-route node identity, so they are marked as a strategic coincidence ' +
        '(never drawn or merged as one shared checkpoint). Resolving this needs the Release B ' +
        'cross-route DAG identity.'
    });
    const uncomposed = corridors.filter(c => !c.hasRoute).map(c => c.pathId);
    if (uncomposed.length) gaps.push({
      code: 'PATHS_WITHOUT_ROUTE',
      count: uncomposed.length,
      detail: 'The server composed no route for these paths, so the map draws the corridor and its ' +
        'count only — no nodes are invented for them.'
    });

    return { version: VERSION, corridors, ties, groups, shared, gaps, focusId, goal: (shape && shape.goal) || '' };
  }

  /* ── 2 · LAYOUT ─ topology → coordinates ───────────────────────────────────────────────────── */
  function plan(topo, opts) {
    const o = opts || {};
    const w = Math.max(280, Math.round(o.w || 900));
    const h = Math.max(240, Math.round(o.h || 520));
    const selId = o.selId || null;
    const level = o.level === 'Z2' || o.level === 'Z1' ? o.level : 'Z0';
    const focal = o.focal && o.focal.pathId && o.focal.nodeId ? o.focal : null;
    const cs = topo.corridors;
    const n = cs.length;
    const hx = PAD_L, gx = w - PAD_R;
    const span = gx - hx;
    const radius = CORNER;
    const PAD_TOP = 24;      // room for the goal label sitting above the trunk
    const padTopX = PAD_TOP + Math.max(0, Math.min(140, o.padTop || 0));   // extra reserved band (narrow: the goal card lives there)
    const PAD_BOT = 30;      // room for the honest footnote under the lowest corridor

    cs.forEach(c => { c.expanded = (level === 'Z2' && !c.stop && c.hasRoute && c.pathId === selId); });

    /* The backbone is the corridor drawn straight across the canvas: the path the server holds in
       focus when it declares one, else the middle corridor in the engine's own order — a neutral,
       deterministic geometric choice (int 04 §4) that does NOT move when the person selects another
       path, and that keeps corridors balanced above and below the trunk. */
    let back = cs.findIndex(c => c.inFocus);
    if (back < 0) back = Math.floor((n - 1) / 2);

    /* Lanes: everything above the backbone takes a negative offset, everything below a positive one,
       keeping the engine's order on each side (so two corridors never swap places and no two on the
       same side cross). */
    const offsets = cs.map(() => 0);
    let up = 0, down = 0;
    for (let i = back - 1; i >= 0; i--) { up += 1; offsets[i] = -up; }
    for (let i = back + 1; i < n; i++) { down += 1; offsets[i] = down; }

    /* Band heights. A corridor that carries RouteNodes needs room for a marker ON its line and the
       step's state word just under it; the opened one needs a little more for its dependency hops.
       A corridor the server composed no route for stays a thin line. The bands share the height that
       is really there, so the map fills its canvas and nothing is pushed off the bottom. */
    const avail = Math.max(140, h - padTopX - PAD_BOT);
    const gaps = GAP * Math.max(0, n - 1);
    const want = cs.map(c => (c.expanded ? ROOMY : (c.hasRoute ? NODE_BAND : BASE_MIN)));
    let total = want.reduce((a, b) => a + b, 0) + gaps;
    const k = total > avail ? avail / total : 1;           // squeeze proportionally, never overflow
    const bandH = want.map((w, i) => Math.max(cs[i].hasRoute || cs[i].expanded ? 58 : 30, w * k));
    total = bandH.reduce((a, b) => a + b, 0) + gaps;
    if (total < avail && n) {                              // spread the leftover: no dead band
      const extra = (avail - total) / n;
      for (let i = 0; i < n; i++) bandH[i] += extra;
    }

    /* Stack top-to-bottom in offset order and CENTRE THE WHOLE STACK in the canvas — never the trunk
       alone, which is what pushed the lower corridors off the bottom of the map. HERE and the GOAL
       sit on the trunk (the backbone's own row), so the busiest line is the one drawn across. */
    const order = cs.map((c, i) => i).sort((a, b) => (offsets[a] - offsets[b]) || (a - b));
    const stackH = bandH.reduce((a, b) => a + b, 0) + gaps;
    const centers = {};
    let cursor = padTopX + Math.max(0, (avail - stackH) / 2);
    order.forEach(i => { centers[i] = cursor + bandH[i] / 2; cursor += bandH[i] + GAP; });
    const by = centers[back];
    const laneY = cs.map((c, i) => centers[i]);

    /* Where a corridor leaves the backbone. The OUTER lanes leave first and the inner ones later, so an
       outer corridor's turn is always left of every inner corridor's run: no turn crosses another
       corridor's line, and nothing reads as a join that is not there. */
    const maxOff = Math.max(1, ...offsets.map(Math.abs));
    const fan = Math.max(26, Math.min(120, span * 0.13));
    const branchX = i => hx + 26 + (1 - Math.abs(offsets[i]) / maxOff) * fan;
    const joinX = i => gx - 26 - (Math.abs(offsets[i]) / maxOff) * fan;
    const straight = i => Math.abs(offsets[i]) < 0.5;

    /* Corridor polylines: out of HERE on the backbone, one turn into the lane, a long horizontal
       run, one turn back, into GOAL — or, stopped, a run that simply ends where it would have
       rejoined. Straight corridors skip the turns entirely. */
    const endX = gx - 46;                  // every corridor stops short of the goal landmark
    const lanes = cs.map((c, i) => {
      const ly = laneY[i], bx = branchX(i), jx = joinX(i);
      let points, stopEnd = null, terminal = null;
      if (c.stop) {
        if (straight(i)) { points = [[hx, by], [jx, by]]; stopEnd = { x: jx, y: by }; }
        else { points = [[hx, by], [bx, by], [bx, ly], [jx, ly]]; stopEnd = { x: jx, y: ly }; }
      } else if (straight(i)) {
        points = [[hx, by], [endX, by]]; terminal = { x: endX, y: by };
      } else {
        points = [[hx, by], [bx, by], [bx, ly], [endX, ly]]; terminal = { x: endX, y: ly };
      }
      const runStart = straight(i) ? hx + 60 : bx + 28;   // a straight trunk clears the HERE caption
      const runEnd = c.stop ? jx - 28 : endX - 22;
      return {
        pathId: c.pathId, idx: i, offset: offsets[i], y: ly,
        band: { top: ly - bandH[i] / 2, bot: ly + bandH[i] / 2 }, bandH: bandH[i],
        points, stopEnd, terminal, expanded: c.expanded,
        runStart, runEnd: Math.max(runStart + 40, runEnd),
        titleX: runStart
      };
    });

    /* RouteNodes for EVERY corridor the server composed a route for, placed ON that corridor's own
       line at its dependency layer: the checkpoints the person can actually act on, drawn where they
       are instead of leaving a bare line. A corridor the server composed no route for gets no marker
       at all — nothing is invented for it (G02). Only the opened corridor also carries its real
       dependency edges (progressive detail, int 04 §2-3). */
    const nodes = [], edges = [], clusters = [];
    const shows = (c, id) => {
      if (focal && focal.pathId === c.pathId && focal.nodeId === id) return true;
      /* Z0 WORLD shows the moves on EVERY corridor (owner, 17 Oct: "movesnya muncul node2nya di
         titik2nya bukan cuman garis ajah") — a corridor's frontier is exactly where the person can act
         or verify now. Z1/Z2 stay selection-scoped: one path at a time, progressive detail. */
      if (level === 'Z0') return c.frontierNodes.includes(id);
      if (c.pathId !== selId) return false;
      if (level === 'Z2') return c.expanded || c.frontierNodes.includes(id);
      return c.frontierNodes.includes(id);          // Z1: where the person can act or verify now
    };
    cs.forEach((c, i) => {
      if (!c.cols || !c.cols.length) return;
      const L = lanes[i];
      const colN = c.cols.length;
      const colW = (L.runEnd - L.runStart) / colN;
      const maxLen = Math.max(1, ...c.cols.map(col => col.length));
      const room = Math.max(18, L.bandH / 2 - 26);
      const rowsMax = Math.max(1, Math.floor(room / 26));
      const sub = Math.ceil(maxLen / rowsMax);
      const rad = Math.max(8, Math.min(13, colW / (sub * 2.6)));
      const at = {};
      c.cols.forEach((col, ci) => {
        const subW = colW / sub;
        col.forEach((id, k) => {
          const band = Math.floor(k / rowsMax), rowK = k % rowsMax;
          const inBand = Math.min(rowsMax, col.length - band * rowsMax);
          const x = L.runStart + ci * colW + band * subW + subW / 2;
          const y = L.y + (rowK - (inBand - 1) / 2) * Math.min(30, room / Math.max(1, inBand));
          at[id] = { x, y, rad, w: Math.max(34, subW - 10) };
        });
      });
      /* Z1 folds what it does not show into presentation clusters, one per run of hidden columns on
         the selected corridor (a count, never a canonical node). */
      if (level === 'Z1' && c.pathId === selId) {
        let run = [];
        const flush = () => {
          if (!run.length) return;
          const xs = run.map(id => at[id].x);
          clusters.push({ pathId: c.pathId, ids: run.slice(), count: run.length,
            x: (Math.min(...xs) + Math.max(...xs)) / 2, y: L.y, r: Math.max(9, rad) });
          run = [];
        };
        c.cols.forEach(col => {
          const hidden = col.filter(id => !shows(c, id));
          if (hidden.length === col.length) run = run.concat(hidden);
          else { flush(); if (hidden.length) { run = hidden.slice(); flush(); } }
        });
        flush();
      }
      c.cols.forEach(col => col.forEach(id => {
        const nd = c.nodes.find(x => x.id === id);
        if (!nd || !shows(c, id)) return;
        const q = at[id];
        nodes.push({
          pathId: c.pathId, id, x: q.x, y: q.y, r: q.rad, w: q.w, detail: !!c.expanded,
          kind: nd.kind, fk: nd.fk, label: nd.label, title: nd.title,
          sat: nd.sat, exe: nd.exe, view: nd.view, terminal: nd.terminal,
          sharedWith: (topo.shared[c.pathId + '::' + id] || []).slice(),
          focal: !!(focal && focal.pathId === c.pathId && focal.nodeId === id)
        });
        if (!c.expanded) return;                 // dependency edges belong to the opened corridor only
        (nd.deps || []).forEach(d => {
          const a = at[d];
          if (!a) return;
          /* Orthogonal short hop: out of the dependency, along its own row, into this node. Local
             by construction — it can never reach another corridor's lane. */
          const s0 = a.y === q.y
            ? [[a.x + a.rad, a.y], [q.x - q.rad, q.y]]
            : [[a.x + a.rad, a.y], [a.x + a.rad + 12, a.y], [a.x + a.rad + 12, q.y], [q.x - q.rad, q.y]];
          edges.push({ pathId: c.pathId, from: d, to: id, points: s0 });
        });
      }));
    });

    /* Shared requirement groups (int 22 §38, owner amendment): the requirement is drawn ONCE — on the
       member lane nearest the trunk — and the other shown members fold into a dotted rail into it. The
       presented move is never folded: its exact route_node_ref must stay clickable where the server
       put it. A member that is not shown at this level draws nothing anyway, so no rail is laid for it. */
    const glinks = [];
    const out = {
      version: VERSION, w, h, radius, here: { x: hx, y: by }, goal: { x: gx, y: by },
      backbonePathId: cs[back] ? cs[back].pathId : null,
      level, lanes, nodes, edges, clusters, glinks, ties: topo.ties, groups: topo.groups || [], gaps: topo.gaps, bandH
    };
    (topo.groups || []).forEach(g => {
      const shown = g.links
        .map(l => {
          const c = cs.find(x => x.pathId === l.pathId);
          return c ? { pathId: l.pathId, nodeId: l.nodeId, c, n: out.nodes.find(nd => nd.pathId === l.pathId && nd.id === l.nodeId) } : null;
        })
        .filter(Boolean).filter(x => x.n);
      if (shown.length < 2) return;
      const focalMember = shown.find(x => x.n.focal);
      const rep = focalMember || shown.reduce((a, b) => (Math.abs(offsets[a.c.idx]) <= Math.abs(offsets[b.c.idx]) ? a : b));
      shown.forEach(x => { x.n.sharedGroup = { reqId: g.reqId, count: shown.length, label: g.label, sat: g.sat, representative: x === rep }; });
      shown.forEach(x => {
        if (x === rep || x.n.focal) return;      // the representative and the presented move stay
        glinks.push({ pathId: x.pathId, from: { x: x.n.x, y: x.n.y }, to: { x: rep.n.x, y: rep.n.y } });
        x.n.foldedInto = rep;
      });
      out.nodes = out.nodes.filter(nd => !nd.foldedInto);
    });
    return out;
  }

  /* ── 3 · TYPED EXPERIENCE GRAPH DECORATION (P0-07) ──────────────────────────────────────────
     The renderer must be able to tell apart WHAT the backend actually admitted. This is a pure,
     DOM-free adapter over ExperienceReadModel.graph: it normalizes graph.edges by kind and NEVER
     infers an edge from a shared requirement, an identical label, layout proximity or action order.
       • PRESENTATION_CORRIDOR         — the corridor geometry TOPO already draws. Layout/visual only:
                                         it proves nothing about dependency, readiness or causation.
       • INTRA_ROUTE_DEPENDENCY        — canonical `depends_on` inside ONE route (route tier).
       • MEMBER_OF_PATH                — a route node belongs to its path container (association).
       • SHARED_REQUIREMENT_MEMBERSHIP — two routes name the same requirement id (association).
       • MOVE_OF_NODE                  — a Move's typed `route_node_ref` names its route node.
       • BRANCH_FROM / MERGES_INTO     — the ONLY causal kinds. Drawn only when the backend put an
                                         admitted edge (validity ACCEPTED + a non-empty
                                         declaration_ref) in graph.edges. Otherwise nothing is drawn.
     unsupported_edges are read as {id, reason} and surfaced by the caller, never turned into an
     edge. A missing/partial graph yields {present:false, edges:[], causal:[], unsupported:[]} and
     the renderer then behaves exactly as it did before this layer existed. */
  const PRESENTATION_EDGE = 'PRESENTATION_CORRIDOR';
  const GRAPH_EDGE_SPEC = {
    INTRA_ROUTE_DEPENDENCY: { cls: 'intra', causal: false, tier: 'route' },
    MEMBER_OF_PATH: { cls: 'member', causal: false, tier: 'path' },
    SHARED_REQUIREMENT_MEMBERSHIP: { cls: 'shared', causal: false, tier: 'requirement' },
    MOVE_OF_NODE: { cls: 'move', causal: false, tier: 'move' },
    BRANCH_FROM: { cls: 'causal', causal: true, tier: 'cross-route' },
    MERGES_INTO: { cls: 'causal', causal: true, tier: 'cross-route' }
  };
  const CAUSAL_EDGE_KINDS = ['BRANCH_FROM', 'MERGES_INTO'];

  /* The graph-level identity a node names, without assuming any one refs key is present. */
  function graphRefOf(node) {
    const r = (node && node.refs) || {};
    const s = v => (v == null || v === '') ? null : String(v);
    return {
      pathId: s(r.path_id), routeId: s(r.route_id), nodeId: s(r.route_node_id),
      moveId: s(r.move_id), requirementId: s(r.requirement_id), goalId: s(r.goal_id)
    };
  }

  /* graph → typed decoration. Every endpoint is kept as a graph-level reference; the renderer maps
     it to a canvas point (and skips the edge when no point exists — never a phantom). */
  function graphDecorations(graph) {
    const g = (graph && typeof graph === 'object') ? graph : null;
    const rawNodes = g && Array.isArray(g.nodes) ? g.nodes : [];
    const rawEdges = g && Array.isArray(g.edges) ? g.edges : [];
    const rawUnsupported = g && Array.isArray(g.unsupported_edges) ? g.unsupported_edges : [];
    const nodesById = {};
    rawNodes.forEach(n => { if (n && n.graph_id != null) nodesById[String(n.graph_id)] = n; });

    const endpoints = {};
    function endpointFor(gid) {
      const id = String(gid == null ? '' : gid);
      if (endpoints[id]) return endpoints[id];
      const node = nodesById[id];
      const r = graphRefOf(node);
      const ep = {
        graphId: id, kind: node ? node.kind : null,
        pathId: r.pathId, routeId: r.routeId, nodeId: r.nodeId,
        moveId: r.moveId, requirementId: r.requirementId, goalId: r.goalId, hop: null
      };
      ep.onCanvas = !!(ep.pathId && (ep.nodeId || (node && node.kind === 'PATH')));
      endpoints[id] = ep;
      return ep;
    }

    const byKind = {}, edges = [];
    rawEdges.forEach(e => {
      if (!e || e.kind == null) return;
      const kind = String(e.kind);
      const spec = GRAPH_EDGE_SPEC[kind];
      if (!spec) return;                     /* an unknown kind is never guessed into an edge */
      const fromId = String(e.from_id != null ? e.from_id : (e.from != null ? e.from : ''));
      const toId = String(e.to_id != null ? e.to_id : (e.to != null ? e.to : ''));
      const declarationRef = e.declaration_ref != null ? String(e.declaration_ref) : '';
      const validity = e.validity != null ? String(e.validity) : 'ACCEPTED';
      /* A causal edge is ADMITTED only when the backend says so: ACCEPTED and explicitly declared.
         Membership kinds carry no declaration and are never promoted into a causal relation. */
      const admitted = validity === 'ACCEPTED' && (!spec.causal || declarationRef.length > 0);
      const edge = {
        id: String(e.edge_id != null ? e.edge_id : fromId + '->' + toId + ':' + kind),
        fromId, toId, kind, klass: spec.cls, causal: spec.causal, tier: spec.tier,
        declared: !!declarationRef, declarationRef, validity, admitted,
        sourceEventRefs: Array.isArray(e.source_event_refs) ? e.source_event_refs.slice() : [],
        evidenceRefs: Array.isArray(e.evidence_refs) ? e.evidence_refs.slice() : [],
        scope: e.scope != null ? String(e.scope) : null,
        from: endpointFor(fromId), to: endpointFor(toId)
      };
      (byKind[kind] = byKind[kind] || []).push(edge);
      edges.push(edge);
    });

    /* A MOVE endpoint resolves to the route node its MOVE_OF_NODE edge names — the same admission,
       so a causal link that mentions a Move can be positioned without inventing a target. */
    const moveOf = {};
    (byKind.MOVE_OF_NODE || []).forEach(e => { if (e.admitted && !moveOf[e.fromId]) moveOf[e.fromId] = e.to; });
    Object.keys(endpoints).forEach(gid => {
      const ep = endpoints[gid];
      if (ep.kind === 'MOVE' && !ep.onCanvas && moveOf[gid]) {
        const t = moveOf[gid];
        ep.pathId = t.pathId; ep.routeId = t.routeId; ep.nodeId = t.nodeId;
        ep.onCanvas = !!(t.pathId && t.nodeId); ep.hop = 'MOVE_OF_NODE';
      }
    });

    const counts = {};
    Object.keys(GRAPH_EDGE_SPEC).forEach(k => { counts[k] = (byKind[k] || []).length; });
    const unsupported = rawUnsupported.map(u => ({
      id: (u && u.id != null) ? String(u.id) : '?',
      reason: (u && u.reason != null) ? String(u.reason) : 'UNKNOWN'
    }));
    const causal = edges.filter(e => e.causal);
    const admittedCausal = causal.filter(e => e.admitted);
    return {
      version: VERSION, present: !!g, presentationKind: PRESENTATION_EDGE,
      specs: GRAPH_EDGE_SPEC, causalKinds: CAUSAL_EDGE_KINDS.slice(),
      nodesById, endpoints, byKind, edges, causal, admittedCausal,
      counts, unsupported, unsupportedCount: unsupported.length,
      causalCount: causal.length, admittedCausalCount: admittedCausal.length
    };
  }

  /* ── 4 · ROUTER ─ corner points → SVG path with small rounded corners (no Bézier waves) ────── */
  function round(points, r) {
    const pts = (points || []).filter(p => p && p.length === 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]));
    if (pts.length < 2) return '';
    const R = Number.isFinite(r) ? r : CORNER;
    const f = v => Math.round(v * 100) / 100;
    if (pts.length === 2) return 'M ' + f(pts[0][0]) + ' ' + f(pts[0][1]) + ' L ' + f(pts[1][0]) + ' ' + f(pts[1][1]);
    let d = 'M ' + f(pts[0][0]) + ' ' + f(pts[0][1]);
    for (let i = 1; i < pts.length - 1; i++) {
      const p = pts[i - 1], c = pts[i], nx = pts[i + 1];
      const v1x = c[0] - p[0], v1y = c[1] - p[1], v2x = nx[0] - c[0], v2y = nx[1] - c[1];
      const l1 = Math.hypot(v1x, v1y) || 1, l2 = Math.hypot(v2x, v2y) || 1;
      const rr = Math.min(R, l1 / 2, l2 / 2);
      const ax = c[0] - (v1x / l1) * rr, ay = c[1] - (v1y / l1) * rr;
      const bx = c[0] + (v2x / l2) * rr, byy = c[1] + (v2y / l2) * rr;
      d += ' L ' + f(ax) + ' ' + f(ay) + ' Q ' + f(c[0]) + ' ' + f(c[1]) + ' ' + f(bx) + ' ' + f(byy);
    }
    const last = pts[pts.length - 1];
    return d + ' L ' + f(last[0]) + ' ' + f(last[1]);
  }

  /* Shortest distance between two axis-aligned/segmented corridors — used by the geometry checks
     (two corridors must never be drawn on top of each other). */
  function segDist(a, b, c, d) {
    const vx = b[0] - a[0], vy = b[1] - a[1], wx = d[0] - c[0], wy = d[1] - c[1];
    const den = vx * wy - vy * wx;
    if (Math.abs(den) < 1e-9) {
      const t = ((c[0] - a[0]) * vx + (c[1] - a[1]) * vy) / ((vx * vx + vy * vy) || 1);
      const tt = Math.max(0, Math.min(1, t));
      return Math.hypot(a[0] + tt * vx - c[0], a[1] + tt * vy - c[1]);
    }
    const s = ((c[0] - a[0]) * wy - (c[1] - a[1]) * wx) / den;
    const u = ((c[0] - a[0]) * vy - (c[1] - a[1]) * vx) / den;
    if (s >= 0 && s <= 1 && u >= 0 && u <= 1) return 0;
    const pt = [a[0] + s * vx, a[1] + s * vy];
    const dist = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]);
    return Math.min(dist(a, c), dist(a, d), dist(b, c), dist(b, d), dist(pt, c), dist(pt, d));
  }
  function polyDist(P, Q) {
    let m = Infinity;
    for (let i = 1; i < P.length; i++) for (let j = 1; j < Q.length; j++) {
      m = Math.min(m, segDist(P[i - 1], P[i], Q[j - 1], Q[j]));
    }
    return m;
  }

  /* P1-04: the ONLY valid canvas location for a causal endpoint is the endpoint ITSELF. If a specific
     RouteNode is hidden at the current semantic zoom there is NO point for it — the path terminal is
     NOT a substitute, because that would draw a declared cross-route relation to the wrong node.
     Returns null when the exact canonical endpoint is not visible; the caller must then hide the edge
     or use an explicitly disclosed collapsed representation. */
  function causalVisiblePoint(ep, lookup) {
    if (!ep) return null;
    const L = lookup || {};
    if (ep.pathId && ep.nodeId) {
      const n = (L.nodes || []).find(x => x && x.pathId === ep.pathId && x.id === ep.nodeId);
      return n ? { x: n.x, y: n.y, r: (n.r == null ? 0 : n.r) } : null;
    }
    if (ep.kind === 'HERE') return L.here || null;
    if (ep.kind === 'GOAL') return L.goal || null;
    return null;
  }

  global.TOPO = {
    VERSION, CORNER, build, plan, round, polyDist,
    graphDecorations, graphRefOf, GRAPH_EDGE_SPEC, CAUSAL_EDGE_KINDS, PRESENTATION_EDGE,
    causalVisiblePoint,
    /* counts the direction changes of a routed corridor: the graph is meant to read as long runs
       with few turns, so this stays small and the geometry test can pin it */
    turns: points => Math.max(0, (points || []).length - 2)
  };
})(typeof window !== 'undefined' ? window : globalThis);
