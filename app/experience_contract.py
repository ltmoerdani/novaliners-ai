"""Experience Read Model + composite projection revision (V4 master prompt section 4;
audit D-04/D-05/D-06/D-09).

WHY THIS FILE EXISTS
--------------------
binding.state_version() fingerprints ONLY the active claims of Universal State. Route
execution, Move lifecycle, reported outcomes and route lineages do NOT change it, so a
checked Move could leave every destination (STATE/MAPS/MOVES/JOURNEY/TALK) showing the
same stale revision. This module adds explicit execution/outcome/lineage digests and a
composite projection_revision that changes on ANY accepted mutation, plus a typed graph
DTO whose edges are declared (never inferred from geometry, order or shared labels).

It is a pure READ projection over canonical stores. It is NOT a second authority, does
not re-diagnose, does not call an LLM, does not write route lineage. Nothing here ranks
paths or decides readiness.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

EXPERIENCE_VERSION = 1

# Edge vocabulary. Causal kinds require an explicit declaration_ref with provenance;
# presentation kinds are membership/association and never count as a causal edge.
CAUSAL_EDGE_KINDS = ("BRANCH_FROM", "MERGES_INTO")
PRESENTATION_EDGE_KINDS = ("INTRA_ROUTE_DEPENDENCY", "MEMBER_OF_PATH",
                           "SHARED_REQUIREMENT_MEMBERSHIP", "MOVE_OF_NODE",
                           # Phase 7: a Move belongs to the Path it DECLARED at creation
                           # (move.linked_path_id). Association only - never a causal claim, and never
                           # inferred from creation order, index or a similar title.
                           "MOVE_OF_PATH", "MOVE_CONTINUATION")
EDGE_KINDS = CAUSAL_EDGE_KINDS + PRESENTATION_EDGE_KINDS


def _digest(value: Any) -> str:
    """Stable short digest over a canonical JSON serialization (sorted keys)."""
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _latest_lineage_rows(s: Any, *, base_dir: Any = None) -> list[dict]:
    """Last-row-wins per route_id, scoped to the session business context when the
    session carries a structured Goal (context_id == goal_id; legacy rows have no
    context and stay readable for historical compatibility)."""
    user_id = getattr(s, "user_id", "") or ""
    if not user_id:
        return []
    try:
        from store import route_lineages
        rows = route_lineages.list_rows(user_id, base_dir)
    except Exception:  # noqa: BLE001 - a broken lineage file must not crash a read
        return []
    goal_id = ((getattr(s, "goal", None) or {}).get("goal_id")) or None
    last: dict[str, dict] = {}
    for row in rows:
        lin = (row or {}).get("lineage") or {}
        rid = lin.get("route_id")
        if not rid:
            continue
        if goal_id is not None:
            ctx = (lin.get("reconciliation_key") or {}).get("context_id")
            if ctx is not None and ctx != goal_id:
                continue
        last[rid] = row
    return list(last.values())


def _route_ids_of(routes: list[dict] | None) -> set[str] | None:
    if routes is None:
        return None
    return {str(r.get("route_id")) for r in routes if r.get("route_id")}


def route_lineage_revision(s: Any, *, routes: list[dict] | None = None, base_dir: Any = None) -> str:
    """Digest of the CURRENT route lineage identities (status + revision + node ids)."""
    scope = _route_ids_of(routes)
    entries: list[tuple] = []
    for row in _latest_lineage_rows(s, base_dir=base_dir):
        lin = row.get("lineage") or {}
        rid = str(lin.get("route_id") or "")
        if scope is not None and rid not in scope:
            continue
        revisions = lin.get("revisions") or []
        latest = revisions[-1] if revisions else {}
        node_ids = sorted(str(n.get("node_id")) for n in (latest.get("nodes") or []) if n.get("node_id"))
        entries.append((rid, lin.get("lineage_status"), latest.get("revision_no"), tuple(node_ids)))
    return "rl-" + _digest(sorted(entries))


def execution_revision(s: Any, *, routes: list[dict] | None = None, base_dir: Any = None) -> str:
    """Digest of the execution ledger (route node views) AND every Move lifecycle entry.
    A checkbox therefore changes this even when claim state_version does not (N24)."""
    user_id = getattr(s, "user_id", "") or ""
    scope = _route_ids_of(routes)
    entries: list[tuple] = []
    if user_id:
        try:
            from store import route_execution
            latest: dict[tuple, dict] = {}
            for row in route_execution.list_rows(user_id, base_dir):
                rid, nid = row.get("route_id"), row.get("node_id")
                if not rid or not nid:
                    continue
                if scope is not None and rid not in scope:
                    continue
                latest[(rid, nid)] = row
            for (rid, nid), row in latest.items():
                entries.append(("route", rid, nid, row.get("event"), row.get("ts")))
        except Exception:  # noqa: BLE001
            pass
    for mv in getattr(s, "moves", None) or []:
        hist = tuple((h.get("state"), h.get("event_id")) for h in (mv.get("history") or []))
        # Phase 7: the Move's OWN action list is execution. Every accepted action event must move
        # this digest, so Maps/Moves/Journey re-read the projection without a checkpoint.
        acts = tuple((a.get("action_id"), a.get("status"), a.get("completed_at"),
                      a.get("execution_event_id")) for a in (mv.get("actions") or []))
        entries.append(("move", mv.get("move_id"), mv.get("lifecycle"), mv.get("executed_ts"), hist, acts))
    # Legacy per-action reports (diagnosis.day_by_day) are execution/outcome facts too: a report must
    # invalidate the composite revision even though it changes no claim (D-05).
    diag = getattr(s, "diagnosis", None)
    for it in (getattr(diag, "day_by_day", None) or []):
        entries.append(("action", getattr(it, "status", None), getattr(it, "outcome", None),
                        getattr(it, "done_at", None), getattr(it, "reported_at", None)))
    return "ex-" + _digest(sorted(entries, key=repr))


def outcome_revision(s: Any, *, base_dir: Any = None) -> str:
    """Digest of durable outcome observations: Move observation refs/assessments and the
    canonical evidence ledger (id + superseded + claim provenance). Unknown stays
    distinct from absent: a superseded item is kept, flagged, never silently dropped."""
    entries: list[tuple] = []
    for mv in getattr(s, "moves", None) or []:
        _or = mv.get("outcome_report") or {}
        entries.append((
            mv.get("move_id"),
            tuple(sorted(mv.get("observation_claim_refs") or [])),
            (mv.get("assessment") or {}).get("verdict"),
            (mv.get("assessment") or {}).get("event_id"),
            _or.get("outcome"), _or.get("note"), _or.get("reported_at"),
            len(_or.get("revisions") or []),
        ))
    for e in getattr(s, "evidence", None) or []:
        entries.append((
            getattr(e, "id", None),
            bool(getattr(e, "superseded", False)),
            getattr(e, "claim_id", ""),
            getattr(e, "event_id", ""),
            getattr(e, "admissible", True),
        ))
    # D-02: a durable check-in is an accepted outcome observation, so it must move the
    # composite revision even though it changes no claim (state_version stays put).
    user_id = getattr(s, "user_id", "") or ""
    if user_id:
        try:
            from store import checkins
            goal_id = ((getattr(s, "goal", None) or {}).get("goal_id")) or None
            for r in checkins.latest(user_id, goal_id=goal_id):
                entries.append(("checkin", r.get("checkin_id"), r.get("outcome"),
                                r.get("day"), r.get("created_ts")))
        except Exception:  # noqa: BLE001 - a broken check-in file must not crash a read
            pass
    return "ou-" + _digest(sorted(entries, key=repr))


def observation_revision(s: Any, *, base_dir: Any = None) -> str:
    """Digest of ACCEPTED user OBSERVATIONS that may be material to navigation: durable
    check-ins, per-action reported outcomes, and Move observations/verdicts.

    It deliberately EXCLUDES mere execution/status (a checked box): completing an action is
    execution, not an observation, and §6.1 forbids triggering reassessment just because an
    action was checked. "Unknown" stays distinct from "absent": an action with no reported
    outcome simply contributes nothing (never a zero)."""
    entries: list[tuple] = []
    diag = getattr(s, "diagnosis", None)
    for i, it in enumerate(getattr(diag, "day_by_day", None) or []):
        outcome = getattr(it, "outcome", "") or ""
        reported = getattr(it, "reported_at", None)
        if outcome or reported:
            entries.append(("action_outcome", i, outcome, reported,
                            getattr(it, "intervention_id", "")))
    _pr = getattr(diag, "plan_report", None) or {}
    if _pr.get("outcome"):
        # appended ONLY when a plan-level outcome exists, so every digest computed before it stays valid
        entries.append(("plan_outcome", _pr.get("outcome"), _pr.get("reported_at")))
    for mv in getattr(s, "moves", None) or []:
        entries.append((
            "move", mv.get("move_id"),
            tuple(sorted(mv.get("observation_claim_refs") or [])),
            (mv.get("assessment") or {}).get("verdict"),
            mv.get("outcome_reference"),
        ))
    user_id = getattr(s, "user_id", "") or ""
    if user_id:
        try:
            from store import checkins
            goal_id = ((getattr(s, "goal", None) or {}).get("goal_id")) or None
            for r in checkins.latest(user_id, goal_id=goal_id, base_dir=base_dir):
                entries.append(("checkin", r.get("checkin_id"), r.get("outcome"),
                                r.get("day"), r.get("created_ts")))
        except Exception:  # noqa: BLE001 - a broken check-in file must not crash a read
            pass
    return "ob-" + _digest(sorted(entries, key=repr))


def observation_fingerprint(s: Any, *, base_dir: Any = None) -> str:
    """Phase 6.2.1: like observation_revision but over the whole EFFECTIVE content of each report
    (outcome, note, path, and how many corrections preceded it), so a correction within the same second,
    or one that only changes the note or the path, still changes the digest. Execution status stays out
    (completion is not an observation). Kept SEPARATE from observation_revision: checkpoints cut before
    this existed carry only the old digest and are compared with it, so no old checkpoint turns
    'changed' merely because the formula grew."""
    entries: list[tuple] = []
    diag = getattr(s, "diagnosis", None)
    for i, it in enumerate(getattr(diag, "day_by_day", None) or []):
        outcome = getattr(it, "outcome", "") or ""
        reported = getattr(it, "reported_at", None)
        note = getattr(it, "note", "") or ""
        if outcome or reported or note:
            entries.append(("action_outcome", i, outcome, note, getattr(it, "outcome_path", "") or "",
                            len(getattr(it, "outcome_revisions", None) or []), reported,
                            getattr(it, "intervention_id", "")))
    pr = getattr(diag, "plan_report", None) or {}
    if pr.get("outcome") or pr.get("note"):
        entries.append(("plan_report", pr.get("outcome"), pr.get("note"), pr.get("path"),
                        len(pr.get("revisions") or []), pr.get("reported_at")))
    for mv in getattr(s, "moves", None) or []:
        entries.append(("move", mv.get("move_id"), tuple(sorted(mv.get("observation_claim_refs") or [])),
                        (mv.get("assessment") or {}).get("verdict"), mv.get("outcome_reference")))
    user_id = getattr(s, "user_id", "") or ""
    if user_id:
        try:
            from store import checkins
            goal_id = ((getattr(s, "goal", None) or {}).get("goal_id")) or None
            for r in checkins.latest(user_id, goal_id=goal_id, base_dir=base_dir):
                entries.append(("checkin", r.get("checkin_id"), r.get("outcome"), r.get("note"),
                                r.get("day"), r.get("created_ts")))
        except Exception:  # noqa: BLE001
            pass
    return "of2-" + _digest(sorted(entries, key=repr))


def link_revision(s: Any, *, base_dir: Any = None) -> str:
    """Digest of ADMITTED cross-route link identities for this business context. CHEAP: it reads the
    link store only, so every read surface can compute the same value without composing routes."""
    user_id = getattr(s, "user_id", "") or ""
    if not user_id:
        return "ln-" + _digest([])
    try:
        from store import navigation_links
        goal_id = ((getattr(s, "goal", None) or {}).get("goal_id")) or None
        rows = navigation_links.latest_links(user_id, base_dir=base_dir, context_id=goal_id)
    except Exception:  # noqa: BLE001
        rows = []
    entries = sorted((str(r.get("link_id")), str(r.get("kind")), str(r.get("declaration_ref")),
                      str(r.get("status"))) for r in (rows or []))
    return "ln-" + _digest(entries)


def graph_revision(graph: dict | None) -> str:
    """Semantic fingerprint of admitted topology + relevant node states. Coordinates,
    pixel positions, sort order, timestamps and renderer ids are deliberately excluded."""
    g = graph or {}
    nodes = sorted((str(n.get("graph_id")), str(n.get("kind")), str(n.get("status")))
                   for n in (g.get("nodes") or []))
    edges = sorted((str(e.get("edge_id")), str(e.get("kind")), str(e.get("from_id")), str(e.get("to_id")))
                   for e in (g.get("edges") or []))
    return "gr-" + _digest({"nodes": nodes, "edges": edges})


def reality_revision(s: Any, *, routes: list[dict] | None = None, graph: dict | None = None,
                     project_revision: bool = True, base_dir: Any = None) -> dict:
    """Composite RealityRevision. projection_revision is stable for identical current reality and
    changes on any accepted semantic/execution/outcome/lineage/link change.

    IMPORTANT: graph_revision is a SEPARATE field and is deliberately NOT hashed into
    projection_revision. Including it would force every read surface (STATE/MAPS/MOVES/JOURNEY/TALK)
    to build the whole graph - and re-compose routes - merely to agree on a revision, which is both
    slow and a write side effect on a read. Every business-relevant topology change is already
    captured by state_version (requirement states), route_lineage_revision, execution_revision,
    outcome_revision and link_revision (admitted cross-route links), all of which are cheap reads.
    The routes argument is accepted for compatibility but is NOT used for scoping: scoping is the
    session business context (goal_id), so every surface computes the same composite.
    """
    from app import checkpoints as _cp
    from app.binding import state_version

    cp = _cp.latest(s)
    goal = getattr(s, "goal", None) or {}
    sv = state_version(s)
    rl = route_lineage_revision(s, base_dir=base_dir)
    ex = execution_revision(s, base_dir=base_dir)
    ou = outcome_revision(s, base_dir=base_dir)
    ln = link_revision(s, base_dir=base_dir)
    gr = graph_revision(graph) if graph is not None else None
    knowledge_binding_id = (cp.get("binding") or {}).get("binding_id") if cp else None
    rev = {
        "session_id": getattr(s, "id", ""),
        "actor_workspace_id": getattr(s, "user_id", "") or "",
        "goal_id": goal.get("goal_id"),
        "goal_version": goal.get("version"),
        "state_version": sv,
        "checkpoint_id": (cp or {}).get("checkpoint_id"),
        "checkpoint_version": (cp or {}).get("version"),
        "route_lineage_revision": rl,
        "execution_revision": ex,
        "outcome_revision": ou,
        "link_revision": ln,
        "knowledge_binding_id": knowledge_binding_id,
        "graph_revision": gr,
    }
    if project_revision:
        composite = {k: v for k, v in rev.items() if k != "graph_revision"}
        rev["projection_revision"] = "pr-" + _digest(composite)
    return rev


def _node(graph_id: str, kind: str, *, status: str | None = None, refs: dict | None = None,
          evidence_refs: list | None = None, provenance_refs: list | None = None,
          history_refs: list | None = None, state_scope: str | None = None) -> dict:
    return {
        "graph_id": graph_id, "kind": kind, "status": status, "refs": refs or {},
        "evidence_refs": list(evidence_refs or []), "provenance_refs": list(provenance_refs or []),
        "history_refs": list(history_refs or []), "state_scope": state_scope,
    }


def _edge(edge_id: str, from_id: str, to_id: str, kind: str, *, declaration_ref: str = "",
          source_event_refs: list | None = None, evidence_refs: list | None = None,
          scope: str | None = None) -> dict:
    return {
        "edge_id": edge_id, "from_id": from_id, "to_id": to_id, "kind": kind,
        "declaration_ref": declaration_ref, "source_event_refs": list(source_event_refs or []),
        "evidence_refs": list(evidence_refs or []), "validity": "ACCEPTED", "scope": scope,
    }


def _link_endpoint_id(ref: Any) -> str | None:
    if not isinstance(ref, dict):
        return None
    if ref.get("move_id"):
        return "move:" + str(ref["move_id"])
    if ref.get("route_id") and ref.get("node_id"):
        return "req:" + str(ref["route_id"]) + ":" + str(ref["node_id"])
    return None


def build_graph(s: Any, maps_projection: dict | None, *, links: list[dict] | None = None) -> dict:
    """Typed graph from the canonical maps projection + canonical Move ledger + ADMITTED
    navigation links. Nothing is inferred from geometry, order, shared names or proximity:
    cross-route causal edges exist only where a validated link row declares them.

    Returns {nodes, edges, unsupported_edges}. The 7-path illustration is NOT a source.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    unsupported: list[dict] = []
    seen_nodes: dict[str, dict] = {}
    _continuations: list[tuple[str, str]] = []

    def add_node(n: dict) -> dict:
        if n["graph_id"] not in seen_nodes:
            seen_nodes[n["graph_id"]] = n
            nodes.append(n)
        return seen_nodes[n["graph_id"]]

    sid_scope = getattr(s, "id", "") or ""
    add_node(_node("here", "HERE", status="current", refs={"session_id": sid_scope}, state_scope=sid_scope))

    proj = maps_projection or {}
    landmark = proj.get("goal_landmark") or {}
    goal = getattr(s, "goal", None) or {}
    goal_id = goal.get("goal_id") or landmark.get("goal_id")
    goal_ver = goal.get("version") if goal.get("version") is not None else landmark.get("version")
    if goal_id:
        add_node(_node("goal:" + str(goal_id) + ":" + str(goal_ver), "GOAL", status="landmark",
                       refs={"goal_id": goal_id, "goal_version": goal_ver},
                       provenance_refs=["goal:" + str(goal_id) + "@" + str(goal_ver)],
                       state_scope=str(goal_id)))

    req_by_key: dict[str, dict] = {}
    req_by_reqid: dict[str, list[dict]] = {}
    for p in proj.get("paths") or []:
        pid = str(p.get("path_id") or "")
        if not pid:
            continue
        path_node_id = "path:" + pid
        add_node(_node(path_node_id, "PATH", status=p.get("status_display") or p.get("status"),
                       refs={"path_id": pid}, provenance_refs=["path:" + pid],
                       state_scope=str(goal_id or "")))
        route = p.get("route")
        if not route:
            continue
        rid = str(route.get("route_id") or "")
        for rn in route.get("nodes") or []:
            nid = str(rn.get("node_id") or "")
            if not nid:
                continue
            resolves = rn.get("resolves") or []
            req_id = str(resolves[0]) if resolves else None
            gid = "req:" + rid + ":" + nid
            gnode = add_node(_node(
                gid, "REQUIREMENT", status=(rn.get("presentation") or {}).get("word"),
                refs={"path_id": pid, "route_id": rid, "route_node_id": nid, "requirement_id": req_id},
                provenance_refs=["route:" + rid + "@" + str(route.get("revision_no"))],
                state_scope=str(goal_id or "")))
            req_by_key[gid] = gnode
            if req_id:
                req_by_reqid.setdefault(req_id, []).append(gnode)
            edges.append(_edge("e:member:" + pid + ":" + gid, path_node_id, gid, "MEMBER_OF_PATH"))
            for dep in rn.get("depends_on") or []:
                from_id = "req:" + rid + ":" + str(dep)
                if from_id in req_by_key:
                    edges.append(_edge("e:intra:" + rid + ":" + str(dep) + "->" + nid, from_id, gid,
                                       "INTRA_ROUTE_DEPENDENCY",
                                       declaration_ref="depends_on:" + rid + ":" + nid))
                else:
                    unsupported.append({"id": "e:intra:" + rid + ":" + str(dep) + "->" + nid,
                                        "reason": "DEPENDENCY_ENDPOINT_MISSING"})

    # Shared requirement membership: same canonical requirement id holding on 2+ DISTINCT
    # routes. Compatible state -> a shared hub node; disagreement -> explicit split (N23).
    for req_id, holders in sorted(req_by_reqid.items()):
        route_ids = {h["refs"].get("route_id") for h in holders}
        if len(route_ids) < 2:
            continue
        labels = {h["status"] for h in holders}
        hub_id = "reqshared:" + req_id
        if len(labels) == 1:
            add_node(_node(hub_id, "REQUIREMENT", status=holders[0]["status"],
                           refs={"requirement_id": req_id}, state_scope=str(goal_id or "")))
            for h in holders:
                edges.append(_edge("e:shared:" + h["graph_id"] + ":" + hub_id, h["graph_id"], hub_id,
                                   "SHARED_REQUIREMENT_MEMBERSHIP",
                                   declaration_ref="shared_requirement:" + req_id))
        else:
            unsupported.append({"id": hub_id,
                                "reason": "INCOMPATIBLE_SCOPE: requirement " + req_id +
                                          " carries disagreeing states " + str(sorted(labels)) +
                                          "; split, never merged"})

    # Canonical Moves. A Move is bound to a route node only through its typed
    # route_node_ref; a mismatch is surfaced, never guessed from a title (N19/N28).
    rev_by_route: dict[str, int] = {}
    for p in proj.get("paths") or []:
        r = p.get("route") or {}
        if r.get("route_id"):
            rev_by_route[str(r["route_id"])] = r.get("revision_no")
    for mv in getattr(s, "moves", None) or []:
        mid = str(mv.get("move_id") or "")
        if not mid:
            continue
        mv_gid = "move:" + mid
        acts = list(mv.get("actions") or [])
        add_node(_node(mv_gid, "MOVE", status=mv.get("lifecycle"),
                       refs={"move_id": mid, "path_id": mv.get("linked_path_id") or None,
                             "objective": mv.get("objective") or "",
                             # The canonical checklist rides on the node: same move_id/action_id the
                             # Moves screen mutates, so progress is never re-derived by title or index.
                             "actions": [{"action_id": a.get("action_id"), "title": a.get("title"),
                                          "status": a.get("status"), "required": a.get("required", True),
                                          "completed_at": a.get("completed_at")} for a in acts],
                             "actions_done": sum(1 for a in acts if a.get("status") == "DONE"),
                             "actions_total": len(acts),
                             "actions_required": sum(1 for a in acts if a.get("required", True)),
                             "executed_ts": mv.get("executed_ts"),
                             "predecessor_move_id": mv.get("predecessor_move_id") or None},
                       provenance_refs=["move:" + mid],
                       history_refs=[h.get("event_id") for h in (mv.get("history") or [])
                                      if h.get("event_id")],
                       state_scope=str(mv.get("linked_goal_id") or goal_id or "")))
        # Path membership: only through the Move's OWN declared linked_path_id, and only when that
        # path is on this map. Otherwise the relation is surfaced as unsupported, never guessed.
        pid = str(mv.get("linked_path_id") or "")
        if pid:
            if ("path:" + pid) in seen_nodes:
                edges.append(_edge("e:movepath:" + mid + ":" + pid, "path:" + pid, mv_gid,
                                   "MOVE_OF_PATH", declaration_ref="linked_path_id:" + mid))
            else:
                unsupported.append({"id": "e:movepath:" + mid + ":" + pid,
                                    "reason": "MOVE_PATH_NOT_ON_CURRENT_MAP"})
        pred = str(mv.get("predecessor_move_id") or "")
        if pred and pred != mid:
            # Recorded at creation from the canonical ledger (the earlier Move was already executed);
            # never inferred from creation time, index or similar objective text. Resolved after the
            # loop so the edge does not depend on the order the ledger happens to be stored in.
            _continuations.append((pred, mid))
        ref = mv.get("route_node_ref") or None
        if ref:
            target = "req:" + str(ref.get("route_id")) + ":" + str(ref.get("node_id"))
            if target in req_by_key:
                cur_rev = rev_by_route.get(str(ref.get("route_id")))
                if cur_rev is not None and ref.get("route_revision") != cur_rev:
                    unsupported.append({"id": "e:move:" + mid, "reason": "STALE_ROUTE_NODE_REF"})
                else:
                    edges.append(_edge("e:move:" + mid + ":" + target, mv_gid, target, "MOVE_OF_NODE",
                                       declaration_ref="route_node_ref:" + mid))
            else:
                unsupported.append({"id": "e:move:" + mid, "reason": "ROUTE_NODE_REF_NOT_ON_CURRENT_MAP"})

    for _pred, _succ in _continuations:
        if ("move:" + _pred) in seen_nodes and ("move:" + _succ) in seen_nodes:
            edges.append(_edge("e:movecont:" + _pred + "->" + _succ, "move:" + _pred, "move:" + _succ,
                               "MOVE_CONTINUATION", declaration_ref="predecessor_move_id:" + _succ))
        else:
            unsupported.append({"id": "e:movecont:" + _pred + "->" + _succ,
                                "reason": "MOVE_PREDECESSOR_NOT_IN_GRAPH"})

    # ADMITTED cross-route links (A03 store). Only rows with valid provenance.
    for link in links or []:
        if (link or {}).get("status") not in (None, "ACCEPTED"):
            continue
        kind = link.get("kind")
        if kind not in CAUSAL_EDGE_KINDS:
            unsupported.append({"id": link.get("link_id") or "?", "reason": "UNKNOWN_LINK_KIND:" + str(kind)})
            continue
        f_id, t_id = _link_endpoint_id(link.get("from")), _link_endpoint_id(link.get("to"))
        if not f_id or not t_id:
            unsupported.append({"id": link.get("link_id") or "?", "reason": "LINK_ENDPOINT_UNRESOLVED"})
            continue
        # N20: a link row can be shape-valid yet point at a node that is not on THIS map (a Move that
        # does not exist here, a node from another context). Drawing it would be a phantom edge, so it
        # is surfaced with a reason instead of being rendered.
        if f_id not in seen_nodes or t_id not in seen_nodes:
            unsupported.append({"id": str(link.get("link_id") or "?"),
                                "reason": "LINK_ENDPOINT_NOT_IN_GRAPH: " + str(f_id) + " -> " + str(t_id)})
            continue
        edges.append(_edge(str(link.get("link_id")), f_id, t_id, kind,
                           declaration_ref=str(link.get("declaration_ref") or ""),
                           source_event_refs=link.get("source_event_refs"),
                           evidence_refs=link.get("evidence_refs"),
                           scope=link.get("context_id")))

    edges = list({e["edge_id"]: e for e in edges}.values())
    nodes = list({n["graph_id"]: n for n in nodes}.values())
    return {"nodes": nodes, "edges": edges, "unsupported_edges": unsupported}


def change_set(prev: dict | None, cur: dict, *, graph: dict | None = None) -> dict:
    """Diff of admitted graph topology + relevant node states. Distinguishes ADDED,
    REMOVED_FROM_CURRENT_VIEW, CHANGED, UNLOCKED, CLOSED, REOPENED, LINK_ADDED/RETRACTED.
    History is never deleted; removal only means not in the current view.

    P1-05: each change is EXPLAINED from canonical identities - the changed node carries its own
    refs/history_refs/provenance_refs, and the causes list names which composite component moved
    (state/lineage/execution/outcome/link), so a material execution/frontier/outcome change is
    traceable to the event class that produced it rather than being an unexplained id."""
    prev = prev or {}
    if not prev:
        # P0-03: with no prior ACCEPTED projection there is nothing to diff against. This is the
        # BASELINE view, not a change, so a first/repeated read stays stable and no material change
        # is claimed merely because the snapshot store is empty.
        return {"from_revision": None, "to_revision": cur.get("projection_revision"),
                "added": [], "removed_from_current_view": [], "changed": [], "unlocked": [],
                "closed": [], "reopened": [], "links_added": [], "links_retracted": [],
                "causes": [], "baseline": True, "no_material_change": True}
    node_by_id = {n["graph_id"]: n for n in (graph or {}).get("nodes") or []}
    causes = []
    pc, cc = (prev.get("components") or {}), (cur.get("components") or {})
    for name in ("state_version", "route_lineage_revision", "execution_revision",
                 "outcome_revision", "link_revision"):
        if pc.get(name) != cc.get(name):
            causes.append(name)
    _CAUSE_CLASS = {"state_version": "state", "route_lineage_revision": "topology",
                    "execution_revision": "execution", "outcome_revision": "outcome",
                    "link_revision": "topology"}
    cause_classes: dict[str, list[str]] = {}
    for _name in causes:
        cause_classes.setdefault(_CAUSE_CLASS[_name], []).append(_name)
    p_nodes = {str(n): (prev.get("statuses") or {}).get(str(n)) for n in (prev.get("node_ids") or [])}
    c_nodes = {str(n): (cur.get("statuses") or {}).get(str(n)) for n in (cur.get("node_ids") or [])}
    p_edges = set(prev.get("edge_ids") or [])
    c_edges = set(cur.get("edge_ids") or [])
    added = sorted(set(c_nodes) - set(p_nodes))
    removed = sorted(set(p_nodes) - set(c_nodes))
    topology_changed = bool(
        "route_lineage_revision" in causes or "link_revision" in causes
        or added or removed or (c_edges - p_edges) or (p_edges - c_edges))
    changed, unlocked, closed, reopened = [], [], [], []
    for nid in sorted(set(p_nodes) & set(c_nodes)):
        before, after = p_nodes[nid], c_nodes[nid]
        if before != after:
            entry = {"id": nid, "from": before, "to": after}
            node = node_by_id.get(nid)
            if node:
                entry["refs"] = node.get("refs")
                entry["history_refs"] = node.get("history_refs")
                entry["provenance_refs"] = node.get("provenance_refs")
            changed.append(entry)
            word = str(after or "").lower()
            if word in ("now", "open"):
                unlocked.append(nid)
            if word in ("locked", "waiting"):
                closed.append(nid)
            if str(before or "").lower() in ("locked", "waiting") and word in ("now", "open"):
                reopened.append(nid)
    return {
        "from_revision": prev.get("projection_revision"),
        "to_revision": cur.get("projection_revision"),
        "added": added,
        "removed_from_current_view": removed,
        "changed": changed,
        "unlocked": unlocked,
        "closed": closed,
        "reopened": reopened,
        "links_added": sorted(c_edges - p_edges),
        "links_retracted": sorted(p_edges - c_edges),
        "causes": causes,
        # P1-06: name WHAT KIND of change moved the revision. Execution/outcome are NOT topology:
        # a Move or a check-in must never read as a new node/edge, and a topology change must not be
        # blamed on an outcome. topology_changed is true only for real node/edge set movement.
        "cause_classes": cause_classes,
        "topology_changed": topology_changed,
        "execution_changed": "execution_revision" in causes,
        "outcome_changed": "outcome_revision" in causes,
        "no_material_change": not (added or removed or changed or (c_edges - p_edges) or (p_edges - c_edges)),
    }


def snapshot_of(revision: dict, graph: dict) -> dict:
    """Compact persisted snapshot of a projection (history, bounded) used to diff revisions."""
    return {
        "projection_revision": revision.get("projection_revision"),
        "graph_revision": revision.get("graph_revision"),
        "node_ids": sorted(n["graph_id"] for n in graph.get("nodes") or []),
        "edge_ids": sorted(e["edge_id"] for e in graph.get("edges") or []),
        "statuses": {n["graph_id"]: n.get("status") for n in graph.get("nodes") or []},
        # P1-05: keep the composite components so a later change_set can name the CAUSE.
        "components": {k: revision.get(k) for k in (
            "state_version", "route_lineage_revision", "execution_revision",
            "outcome_revision", "link_revision")},
    }


def build_experience(s: Any, *, routes: list[dict] | None = None, maps_projection: dict | None = None,
                     links: list[dict] | None = None, timeline: dict | None = None,
                     state: dict | None = None, base_dir: Any = None,
                     degraded_sources: list[str] | None = None) -> dict:
    """Compose the version-bound ExperienceReadModel. The state block may be supplied by
    the caller (the endpoint owns the expensive navigation recompute); omitting it keeps
    the payload honest rather than inventing a second interpretation."""
    from app import checkpoints as _cp
    from app import moves as _moves

    graph = build_graph(s, maps_projection, links=links)
    revision = reality_revision(s, graph=graph, base_dir=base_dir)
    cp = _cp.latest(s)
    route_instances: list[dict] = []
    for p in (maps_projection or {}).get("paths") or []:
        r = p.get("route")
        if not r:
            continue
        route_instances.append({
            "path_id": p.get("path_id"), "route_id": r.get("route_id"),
            "revision_no": r.get("revision_no"), "lineage_status": r.get("lineage_status"),
            "applicability": (r.get("applicability") or {}).get("status"),
            "frontier": r.get("frontier") or [], "nodes": r.get("nodes") or [],
            "edges": r.get("edges") or [], "terminals": r.get("terminals") or [],
        })

    prev = None
    snapshots = getattr(s, "experience_snapshots", None) or []
    if snapshots:
        prev = snapshots[-1]
    cur_snap = snapshot_of(revision, graph)

    stale_reasons: list[str] = []
    if (cp or {}).get("status") == "stale":
        for r in (cp or {}).get("stale_reasons") or []:
            stale_reasons.append("checkpoint_stale:" + str(r.get("change")))
    integrity = {
        "compatible": not (degraded_sources or []),
        "stale_reasons": stale_reasons,
        "degraded_sources": list(degraded_sources or []),
    }
    return {
        "version": EXPERIENCE_VERSION,
        "source": "LIVE",
        "session_id": getattr(s, "id", ""),
        "revision": revision,
        "state": state,
        "checkpoint": _cp.summary(cp),
        "paths": (maps_projection or {}).get("paths") or [],
        "goal_landmark": (maps_projection or {}).get("goal_landmark"),
        "route_instances": route_instances,
        # Phase 7: the canonical Move WITH its action list (the same rows the Moves screen mutates).
        "moves": _moves.moves_view(s),
        "graph": {**graph, "change_set": change_set(prev, cur_snap, graph=graph)},
        "journey_events": (timeline or {}).get("events") if timeline else [],
        "integrity": integrity,
    }


def record_experience_snapshot(s: Any, experience: dict, *, keep: int = 20) -> None:
    """Append the compact snapshot for the NEXT diff. Additive session field; bounded."""
    graph = experience.get("graph") or {}
    revision = experience.get("revision") or {}
    snap = snapshot_of(revision, graph)
    snaps = getattr(s, "experience_snapshots", None)
    if snaps is None:
        snaps = []
        s.experience_snapshots = snaps
    if snaps and snaps[-1].get("projection_revision") == snap.get("projection_revision"):
        return
    snaps.append(snap)
    del snaps[:-keep]
