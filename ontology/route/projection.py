"""Canonical MAPS Projection (R2) — authoritative snapshot -> single presentation model.

internal-docs
(v0.2) + MAP-01..03 (int 00). THIS projection is NOT a second engine (K13): it is purely a
derivation — it does not judge, does not diagnose, does not pick NextMove, does not
rank. All statuses are READ as is from the `/routes` payload
(`compose_path_routes`) and the path display context from the diagnosis; the only
presentation rule is deriving a WORD from three orthogonal axes
(satisfaction · executability · execution) that are NEVER merged:

    done            <- satisfaction PRESENT
    awaiting_proof  <- execution EXECUTED  AND satisfaction != PRESENT (INV-R8:
                       a finished activity is not evidence — the node moves to VERIFY)
    now             <- frontier EXECUTE
    waiting         <- executability UNKNOWN
    locked          <- executability FALSE
    open            <- the rest (open condition, not yet executable)

Mandatory rules (int 03 §3):
1. A Path without a Route -> NO invented RouteNode (`route: null` + reason).
2. STOP ends at ✕ — it never touches the goal landmark (goal = a SEPARATE landmark
   with its own metric/version; route terminal != Goal achieved, K2).
3. Edges ONLY from `depends_on`. No geometric edge to the Goal. No
   date/day on a node (K16).
4. Frontier: ALL valid opportunities carried as is — without ranking/meaning order.
5. Input integrity FAIL-LOUD (not a second validator, but no blind trust):
   dangling dependency, unknown enum, missing revision, duplicate node_id,
   or cycle -> `ProjectionIntegrityError`, NOT read as vacuous-TRUE
   (compose guard pattern).

Determinism: pure function — same input -> identical model (R2 snapshot test).

Focus (MAP-03): the model carries a `focus` block with EMPTY contents + contract; the
`activeDecisionPathId` value is filled by the consumer from the server presentation decision
(`snapshot.nextmove.path_id`), `selectedPathId`/`expandedRouteId` = UI state.
The projection never derives focus itself (no second authority).
"""

from __future__ import annotations

from typing import Any

PROJECTION_VERSION = 1

# Enums read from the actual backend contract (compose.py / execution_view.py /
# lifecycle.py) — not a new authority (int 03 §2).
_SATISFACTION = {"PRESENT", "PARTIAL", "UNKNOWN", "ABSENT"}
_EXECUTABILITY = {"TRUE", "FALSE", "UNKNOWN"}
_EXECUTION_VIEW = {"NOT_STARTED", "EXECUTED", "ABANDONED"}
_FRONTIER_KIND = {"EXECUTE", "VERIFY", "RESOLVE_APPLICABILITY"}
_LINEAGE_STATUS = {"OPEN", "CLOSED"}
# Actual route-level applicability enum (compose.py + core/navigation/applicability.py:53-57):
# "UNDETERMINED" ≡ UNKNOWN on the applicability axis — counted as valid, not a defective payload.
_APPLICABILITY = {"APPLIES", "NOT_APPLICABLE", "UNKNOWN", "UNDETERMINED"}
_LIFECYCLE_STOP = {"STOPPED", "PAUSED"}

_FOCUS_NOTE = (
    "activeDecisionPathId diisi konsumen dari snapshot.nextmove.path_id "
    "(keputusan presentasi server); selectedPathId/expandedRouteId adalah "
    "state UI terpisah (MAP-03). Projection tidak menurunkan fokus."
)


class ProjectionIntegrityError(ValueError):
    """Defective route payload (dangling dep, foreign enum, missing revision, cycle).

    Fail loud at the projection door — never partially drawn and
    never read as vacuous-TRUE (int 03 §3.1)."""


def _fail(route_id: str, msg: str) -> None:
    raise ProjectionIntegrityError(f"[projection:{route_id or '?'}] {msg}")


def _status_of(value: Any, *, field: str, rid: str, nid: str) -> str:
    """Enum payloads come in two valid shapes from the actual contract: a plain string
    (`executability: "TRUE"`) or `{status}` (`satisfaction: {"status": ...}`).
    Both are read; any other shape = defective payload -> fail loud."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("status"), str):
        return value["status"]
    _fail(rid, f"node {nid}: {field} bukan enum yang sah: {value!r}")


def _presentation(node: dict[str, Any], frontier_kind: str | None) -> dict[str, str]:
    """Presentation word from three orthogonal axes — WITHOUT merging them.

    Priority: done > awaiting_proof > now(EXECUTE) > waiting > locked > open.
    Each word explains ONE side; the raw values of the three axes are still carried
    as is in the model, so the consumer never guesses."""
    sat = (node.get("satisfaction") or {}).get("status")
    exe = (node.get("executability") or {}).get("status")
    view = (node.get("execution") or {}).get("view")
    if sat == "PRESENT":
        return {"kind": "done", "word": "Confirmed"}
    if view == "EXECUTED":
        # EXECUTED without PRESENT = awaiting proof — NOT done (INV-R8).
        return {"kind": "awaiting_proof", "word": "Awaiting proof"}
    if frontier_kind == "EXECUTE":
        return {"kind": "now", "word": "Now"}
    if exe == "UNKNOWN":
        return {"kind": "waiting", "word": "Waiting"}
    if exe == "FALSE":
        return {"kind": "locked", "word": "Locked"}
    return {"kind": "open", "word": "Open"}


def _project_nodes(route: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Node + edge model from the route payload. FAIL-LOUD on a defective payload."""
    rid = str(route.get("route_id") or "")
    rev = route.get("revision_no")
    if not rid:
        _fail(rid, "route tanpa route_id")
    if not isinstance(rev, int):
        _fail(rid, f"revision_no hilang/bukan int: {rev!r}")
    raw_nodes = route.get("nodes")
    if not isinstance(raw_nodes, list):
        _fail(rid, "nodes hilang / bukan array")

    nodes: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    frontier_entries = route.get("frontier") or []
    frontier_by_node: dict[str, str] = {}
    for fe in frontier_entries:
        kind = fe.get("kind")
        if kind not in _FRONTIER_KIND:
            _fail(rid, f"frontier kind tak dikenal: {kind!r}")
        if kind == "RESOLVE_APPLICABILITY":
            continue  # without a node — the route has not determined applicability
        nid = fe.get("node")
        if not nid or nid not in {n.get("node_id") for n in raw_nodes}:
            _fail(rid, f"frontier {kind} menunjuk node yang tidak ada: {nid!r}")
        frontier_by_node[nid] = kind  # noqa: E501 — kind already validated above

    for n in raw_nodes:
        nid = n.get("node_id")
        if not nid or not isinstance(nid, str):
            _fail(rid, f"node tanpa node_id: {n!r}")
        if nid in by_id:
            _fail(rid, f"node_id duplikat dalam satu route: {nid}")
        resolves = n.get("resolves")
        if not resolves or not all(isinstance(r, str) and r for r in resolves):
            _fail(rid, f"node {nid} tanpa resolves yang sah")
        deps = n.get("depends_on") or []
        if not isinstance(deps, list) or not all(isinstance(d, str) and d for d in deps):
            _fail(rid, f"node {nid}: depends_on bukan array id")
        sat = _status_of(n.get("satisfaction"), field="satisfaction.status", rid=rid, nid=str(nid))
        exe = _status_of(n.get("executability"), field="executability.status", rid=rid, nid=str(nid))
        view = _status_of(n.get("execution_view"), field="execution_view", rid=rid, nid=str(nid))
        if sat not in _SATISFACTION:
            _fail(rid, f"node {nid}: satisfaction.status tak dikenal: {sat!r}")
        if exe not in _EXECUTABILITY:
            _fail(rid, f"node {nid}: executability.status tak dikenal: {exe!r}")
        if view not in _EXECUTION_VIEW:
            _fail(rid, f"node {nid}: execution_view tak dikenal: {view!r}")
        fk = frontier_by_node.get(nid)
        label = str(n.get("activity") or resolves[0])
        node: dict[str, Any] = {
            "node_id": nid,
            "label": label,
            "resolves": list(resolves),
            "depends_on": list(deps),
            "ref": {"path_id": route.get("path_id"), "route_id": rid, "route_revision": rev},
            "satisfaction": {"status": sat},
            "executability": {"status": exe},
            "execution": {"view": view},
            "presentation": _presentation(
                {"satisfaction": {"status": sat},
                 "executability": {"status": exe},
                 "execution": {"view": view}},
                fk,
            ),
            "frontier_kind": fk,
        }
        if n.get("guidance"):
            node["guidance"] = n["guidance"]  # curated carrier as is (single readiness door)
        nodes.append(node)
        by_id[nid] = node
        for d in deps:
            edges.append({"from": d, "to": nid})  # dependency edge — ONE edge source (int 03 §2)

    # Dangling dependency = defective payload -> fail loud, not partially drawn.
    for e in edges:
        if e["from"] not in by_id:
            _fail(rid, f"depends_on menggantung: {e['from']} -> {e['to']}")
    _assert_acyclic(rid, nodes, edges)
    return nodes, edges


def _assert_acyclic(rid: str, nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> None:
    """A cycle in the dependencies = defective edge (a valid template is guaranteed a DAG by
    validate_route.py at the entrance — K13; projection only rejects the broken ones)."""
    adj: dict[str, list[str]] = {n["node_id"]: [] for n in nodes}
    for e in edges:
        adj[e["from"]].append(e["to"])
    state: dict[str, int] = {}

    def visit(u: str) -> None:
        state[u] = 1
        for v in adj.get(u, ()):
            if state.get(v, 0) == 1:
                _fail(rid, f"siklus dependency melalui {u} -> {v}")
            if state.get(v, 0) == 0:
                visit(v)
        state[u] = 2

    for n in nodes:
        if state.get(n["node_id"], 0) == 0:
            visit(n["node_id"])


def _terminals(nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> list[str]:
    """Terminal = node with out-degree 0 in the dependency graph (int 03 §2) —
    NOT 'the last node of the array'. Route terminal != Goal achieved (K2): the model
    never links a terminal to the goal landmark."""
    has_out = {e["from"] for e in edges}
    ids = [n["node_id"] for n in nodes]
    return [i for i in ids if i not in has_out]


def _project_route(route: dict[str, Any]) -> dict[str, Any]:
    rid = str(route.get("route_id") or "")
    lineage_status = route.get("lineage_status")
    if lineage_status not in _LINEAGE_STATUS:
        _fail(rid, f"lineage_status tak dikenal: {lineage_status!r}")
    applicability = route.get("applicability") or {}
    app_status = applicability.get("status")
    if app_status not in _APPLICABILITY:
        _fail(rid, f"applicability.status tak dikenal: {app_status!r}")
    nodes, edges = _project_nodes(route)
    frontier_out: list[dict[str, Any]] = []
    for fe in route.get("frontier") or []:
        entry: dict[str, Any] = {"kind": fe["kind"]}
        if fe["kind"] in ("EXECUTE", "VERIFY"):
            entry["node_id"] = fe["node"]
        else:
            entry["route_id"] = rid
        frontier_out.append(entry)
    return {
        "route_id": rid,
        "revision_no": route.get("revision_no"),
        "lineage_status": lineage_status,
        "derived_status": route.get("derived_status"),
        "applicability": {"status": app_status},
        "goal_anchor": route.get("goal_anchor"),
        "nodes": nodes,
        "edges": edges,
        "frontier": frontier_out,
        "terminals": _terminals(nodes, edges),
        "note": "node order & edges = dependency, bukan tanggal; terminal route bukan Goal tercapai (K2/K16)",
    }


def _path_ctx_of(paths_ctx: dict[str, dict[str, Any]], path_id: str) -> dict[str, Any]:
    ctx = paths_ctx.get(path_id) or {}
    lifecycle = ctx.get("lifecycle") or "OPEN"
    status = str(ctx.get("status") or "OPEN")
    stopped = lifecycle in _LIFECYCLE_STOP or status == "STOP"
    if lifecycle in _LIFECYCLE_STOP:
        stop_source: str | None = "you"
    elif stopped:
        stop_source = "evidence"
    else:
        stop_source = None
    return {
        "title": str(ctx.get("title") or path_id),
        "lifecycle": lifecycle,
        "status": status,
        "status_display": "STOP" if stopped else status,
        "stopped": stopped,
        "stop_source": stop_source,
        "goal_relation": ctx.get("goal_relation"),
        "goal_relation_note": ctx.get("goal_relation_note") or "",
    }


def project_maps(
    routes: list[dict[str, Any]],
    paths_ctx: dict[str, dict[str, Any]],
    *,
    goal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`routes` payload `/routes` + path display context -> MAPS presentation model.

    `paths_ctx`: {path_id: {title, lifecycle, status, stop_provenance?, goal_relation,
    goal_relation_note}} — from the diagnosis (`possible_paths.paths`), STOP rule
    same as the VM (lifecycle STOPPED/PAUSED = stopped by the user; status STOP
    with an open lifecycle = by evidence).

    `goal`: a SEPARATE business landmark {text, goal_id, version, metric?, horizon?}
    — evaluated by metric+evidence+Goal version (K2), NOT the route end.

    Pure: same input -> identical output. All EXISTING routes are carried (exists !=
    surfaced, INV-R17) — display decisions (cap, card order) belong to the UI."""
    goal = goal or {}
    routes = routes or []
    path_ids: list[str] = []
    seen: set[str] = set()
    for p in paths_ctx:
        if p not in seen:
            seen.add(p)
            path_ids.append(p)
    for r in routes:
        pid = r.get("path_id")
        if pid and pid not in seen:
            seen.add(pid)
            path_ids.append(pid)

    routes_by_path: dict[str, list[dict[str, Any]]] = {}
    for r in routes:
        routes_by_path.setdefault(str(r.get("path_id")), []).append(r)

    paths_out: list[dict[str, Any]] = []
    for pid in path_ids:
        ctx = _path_ctx_of(paths_ctx, pid)
        entry: dict[str, Any] = {
            "path_id": pid,
            "title": ctx["title"],
            "status": ctx["status"],
            "status_display": ctx["status_display"],
            "lifecycle": ctx["lifecycle"],
            "stopped": ctx["stopped"],
            "stop_source": ctx["stop_source"],
            "goal_relation": ctx["goal_relation"],
            "goal_relation_note": ctx["goal_relation_note"],
            "route": None,
            "route_unavailable": None,
        }
        candidates = routes_by_path.get(pid) or []
        if candidates:
            # One route per path in the current composition; if >1 (unexpected),
            # the first is used and the rest are NOT discarded — recorded as is.
            entry["route"] = _project_route(candidates[0])
            if len(candidates) > 1:
                entry["additional_route_ids"] = [c.get("route_id") for c in candidates[1:]]
        else:
            # G02: without a route context -> NO invented node.
            entry["route_unavailable"] = {"reason": "no_route_context"}
        paths_out.append(entry)

    metric = goal.get("metric")
    return {
        "version": PROJECTION_VERSION,
        "kind": "maps_projection",
        "goal_landmark": {
            "text": str(goal.get("text") or ""),
            "goal_id": goal.get("goal_id"),
            "version": goal.get("version"),
            "horizon": goal.get("horizon") if isinstance(goal.get("horizon"), (str, type(None))) else None,
            "metric": metric if isinstance(metric, (dict, type(None))) else None,
        "note": "Business goal landmark — dinilai dari metric + evidence + versi "
                "Goal, TERPISAH dari route (K2/G14).",
        },
        "focus": {
            "activeDecisionPathId": None,
            "selectedPathId": None,
            "expandedRouteId": None,
            "note": _FOCUS_NOTE,
        },
        "paths": paths_out,
    }
