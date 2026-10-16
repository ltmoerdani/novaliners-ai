"""RUNTIME ROUTE COMPOSITION — T1 (spec v0 owner 27 Sep, review draft A).

Not a final API but a BOUNDARY: compose_route(template, *,
goal_anchor, scope_anchor, evidence, requirement_status_reader, motion,
user_id, ...) — all context is EXPLICIT (the composer does NOT diagnose/
guess: goal_anchor, scope_anchor, motion come from the composition
context — T1.11/T1.13).

Flow (owner, 13 steps):
1. goal status PRESENT -> NOT BORN (outcome NO_ROUTE_GOAL_PRESENT,
   read through status_reader — INV-R12 via ledger authority)
2. applicability: evaluate_predicate over EvidenceItem (transcript
   does NOT enter — T1.4/T1.5; the ban is enforced by the call, not
   by agreement)
3. NOT_APPLICABLE -> no active route (outcome NO_ROUTE_NOT_
   APPLICABLE — DISTINGUISHED from the goal-PRESENT reason for audit — INV-R3;
   lineage CLOSED with NOT_APPLICABLE is NOT created at birth)
4. reconciliation key = {goal_anchor, strategy_id, scope_anchor}
5. OPEN lineage with the same key -> REUSE route_id (T1.9 — route identity
   is NOT template content)
6. CLOSED with the same key -> new route + reopened_from (T1.10; Model B:
   CLOSED is excluded from match candidates)
7. instantiate: candidate_key -> NEW node_id; depends_on candidate ->
   node_id from the mapping (primarily via candidate_key; fallback is its
   unique primary)
8. satisfaction = status_reader (None = UNKNOWN by absence, D-A1d) —
   through the reader, NOT self-assessed (T1.8)
9. executability from depends_on: any (ABSENT|PARTIAL)->FALSE · any
   UNKNOWN->UNKNOWN · else TRUE (vacuous for []) — §3.4
10. execution_view = NOT_STARTED (T1)
11. frontier: UNDETERMINED -> [{RESOLVE_APPLICABILITY, route_id, WITHOUT
    node}] · APPLIES -> EXECUTE for nodes with exec TRUE & sat != PRESENT;
    exec FALSE/UNKNOWN wait; sat PRESENT leaves the frontier
12. persist via store/route_lineages (per-user, workspace pattern)
13. STOP AT THE FRONTIER — without NextMove/ranking/selection/LLM.

goal_anchor MUST appear in resolves[] of one of the nodes (INV-R4,
T1.11). motion MUST come from context — the template does NOT carry motion
(T1.13).

storage-scope debt (owner): the adjudication ledger is still global —
the composer does not make it worse: all reads go through the injected
status_reader.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

import store.route_lineages as rl
from ontology.route.strategies import load_motion_vocabulary

# Motion vocabulary = domain labels declared by the strategy registry (not a route machine enum).
MOTIONS = set(load_motion_vocabulary())

StatusReader = Callable[[str], "str | None"]  # None = UNKNOWN (absence)

SATISFACTION_ENUM = {"PRESENT", "PARTIAL", "UNKNOWN", "ABSENT"}


def _read(reader: StatusReader, rid: str) -> str:
    """The reader value is VALIDATED against the satisfaction enum (review 6585c32):
    an arbitrary value MUST NOT enter the instance. None = UNKNOWN by
    absence (D-A1d)."""
    s = reader(rid)
    if s is None:
        return "UNKNOWN"
    if s not in SATISFACTION_ENUM:
        raise ValueError(
            f"status_reader {rid!r} -> {s!r} di luar enum satisfaction "
            f"{sorted(SATISFACTION_ENUM)}")
    return s


def _apply_executability(nodes: list[dict[str, Any]]) -> None:
    """§3.4: any (ABSENT|PARTIAL)->FALSE · any UNKNOWN->UNKNOWN · else
    TRUE (vacuous for an empty depends_on)."""
    by_id = {n["node_id"]: n for n in nodes}
    for n in nodes:
        for d in n["depends_on"]:
            if d not in by_id:
                raise ValueError(
                    f"depends_on {d!r} is dangling — must not read as "
                    f"vacuous TRUE silently (review 568beb9)")
        dep_statuses = [by_id[d]["satisfaction"]["status"]
                        for d in n["depends_on"]]
        if any(s in ("ABSENT", "PARTIAL") for s in dep_statuses):
            n["executability"] = "FALSE"
        elif any(s == "UNKNOWN" for s in dep_statuses):
            n["executability"] = "UNKNOWN"
        else:
            n["executability"] = "TRUE"


def _frontier_for(route_id: str, applicability: str,
                  nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """§3.5: UNDETERMINED -> [{RESOLVE_APPLICABILITY, without node}];
    APPLIES -> EXECUTE for exec TRUE & sat != PRESENT (FALSE/UNKNOWN
    wait; PRESENT leaves the frontier)."""
    if applicability == "UNDETERMINED":
        return [{"kind": "RESOLVE_APPLICABILITY", "route_id": route_id}]
    out: list[dict[str, Any]] = []
    for n in nodes:
        if n["satisfaction"]["status"] == "PRESENT":
            continue
        if n["executability"] == "TRUE":
            # EXECUTE: not yet/abandoned · VERIFY: already done, evidence not yet
            # in (§3.5). The composer always goes NOT_STARTED -> EXECUTE; VERIFY only
            # appears via the ledger overlay (ontology/route/execution_view.py).
            kind = "VERIFY" if n.get("execution_view") == "EXECUTED" else "EXECUTE"
            out.append({"kind": kind, "route_id": route_id,
                        "node": n["node_id"]})
    return out


def frontier_for(route_id: str, applicability: str,
                 nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Public alias for the overlay (execution_view.py)."""
    return _frontier_for(route_id, applicability, nodes)



def compose_route(
    template: dict[str, Any],
    *,
    goal_anchor: str,
    scope_anchor: list[str],
    evidence: list[Any],
    requirement_status_reader: StatusReader,
    motion: str,
    user_id: str,
    context_id: str | None = None,
    revision_label: str = "",
    base_dir=None,
    read_only: bool = False,
) -> dict[str, Any]:
    """Result = {outcome, reason, lineage?, frontier?}. outcome:
    NO_ROUTE_GOAL_PRESENT | NO_ROUTE_NOT_APPLICABLE |
    ROUTE_CREATED | ROUTE_REUSED. The two 'not born' reasons are DISTINGUISHED
    (auditability, INV-R3).

    R1-remediation Probe B (17 Oct): `context_id` = business context identity
    (the session's goal_id; inherited by follow-up sessions of the same map) — it enters the
    reconciliation_key so two different businesses of the same user no longer
    share a route identity. None (legacy session without a goal) = key
    normalized to None — old lineages still match (historical compatibility,
    matching in store.route_lineages._norm_key).

    DEBT-M4 (review 6585c32, owner: do not widen it in T1): when the goal is
    PRESENT / applicability fails while an OPEN lineage already exists — the composer
    ONLY refuses birth; lineage closure (COMPLETED/CLOSED) =
    route lifecycle M4. Flagged in the output reason."""
    if not user_id:
        raise ValueError("user_id wajib non-empty — path kosong = file "
                         "bersama lintas-user (review 6585c32)")
    if motion not in MOTIONS:
        raise ValueError(f"motion {motion!r} is not a contract enum")
    if not scope_anchor or not all(
            isinstance(s, str) and s.startswith("state:") for s in scope_anchor):
        raise ValueError("scope_anchor must be an array of grounded "
                         "state:claim_* references (T: the composer does not guess scope)")

    # 1. goal status via reader (INV-R12 — ledger authority; None =
    #    UNKNOWN by absence D-A1d, not PRESENT)
    goal_status = _read(requirement_status_reader, goal_anchor)
    if goal_status == "PRESENT":
        return {"outcome": "NO_ROUTE_GOAL_PRESENT",
                "reason": "goal requirement sudah PRESENT terbukti — "
                          "route tak lahir (INV-R12). DEBT-M4: lineage "
                          "OPEN yang ada TIDAK ditutup composer (lifecycle "
                          "M4 — jangan diperlebar di T1)"}

    # 2. applicability over EvidenceItem (transcript NEVER enters
    #    — T1.4/T1.5: the evaluator's arguments are evidence + "" only)
    aw = template.get("applies_when") or {}
    from core.stages.rule_predicates import evaluate_predicate
    # T2 CORRECTIVE (review 4a1a4e8, owner: bug proven via a real Session):
    # GAP evidence = "information not yet available", NOT a world fact — a
    # shortfall sentence ("no website yet") MUST NOT become positive applicability
    # evidence (is_gap ≠ NEGATIVE; mapper contract; spirit of INV-R2).
    # Filter BEFORE evaluation — applies AND not_applicable — so the
    # gap-citation fallback in _cite is never touched by this path.
    # This semantic decision belongs to the COMPOSER, not the bridge (invariant #1).
    app_evidence = [e for e in evidence if not getattr(e, "is_gap", False)]
    applies = False
    if aw.get("applies"):
        applies, cites_app, _r = evaluate_predicate(
            {"any_of": aw["applies"]}, app_evidence, "",
            negation_aware=True)
    not_app = False
    if aw.get("not_applicable"):
        not_app, _c2, _r2 = evaluate_predicate(
            {"any_of": aw["not_applicable"]}, app_evidence, "",
            negation_aware=True)
    if not applies and not_app:
        return {"outcome": "NO_ROUTE_NOT_APPLICABLE",
                "reason": "applicability NOT_APPLICABLE — no active route "
                          "(INV-R3/§3.5; birth tak menciptakan lineage "
                          "CLOSED). DEBT-M4: lineage OPEN yang ada TIDAK "
                          "ditutup composer (lifecycle M4)"}
    applicability = "APPLIES" if applies and not not_app else "UNDETERMINED"
    # citations (review 6585c32): evidence field = WHAT IS CITED (APPLIES),
    # [] for UNDETERMINED — not the whole evidence set
    app_cites = list(cites_app) if applicability == "APPLIES" else []

    # 4-6. reconciliation (Model B: CLOSED excluded from the OPEN match)
    # R1-remediation Probe B: context_id = business context (session goal_id) —
    # part of the identity; normalized matching in route_lineages._norm_key.
    key = {"goal_anchor": goal_anchor,
           "strategy_id": template["strategy_id"],
           "scope_anchor": scope_anchor,
           "context_id": context_id}
    open_row = rl.find_open_by_key(user_id, key, base_dir)
    if open_row is not None:
        return _reuse_open(open_row, template, applicability, app_cites,
                           requirement_status_reader, user_id,
                           revision_label, base_dir, read_only=read_only)
    closed_row = rl.find_closed_by_key(user_id, key, base_dir)

    # 7-11. SINGLE DERIVATION SOURCE (review: divergence between the birth/reuse paths
    # = bug source; birth now uses the same helper — without
    # silent primary fallback; unresolved dep = ValueError)
    nodes = _build_nodes_u(template, requirement_status_reader, [])
    route_id = str(uuid.uuid4())
    frontier = _frontier_for(route_id, applicability, nodes)

    # 11b. INV-R4: goal_anchor must be bound in >=1 node
    if goal_anchor not in {r for n in nodes for r in n["resolves"]}:
        raise ValueError(f"goal_anchor {goal_anchor!r} is NOT present in "
                         f"the template's resolves[] — INV-R4")

    lineage = {
        "route_id": route_id,
        "reconciliation_key": key,
        "applicability": {"status": applicability,
                          "evidence": app_cites},
        "motion": motion,
        "lineage_status": "OPEN",
        "revisions": [{
            "revision_no": 1,
            "label": revision_label or f"compose T1 {template['template_id']}",
            "based_on": scope_anchor,
            "nodes": nodes,
        }],
    }
    if closed_row:
        lineage["reopened_from"] = closed_row["lineage"]["route_id"]  # INV-R20

    # 12. persist (HELD in read-only mode: GET must not give birth to a route)
    if read_only:
        return {"outcome": "NO_ROUTE_READ_ONLY",
                "reason": "read-only: kelahiran route ditahan (GET tidak menulis lineage)",
                "lineage": None, "frontier": None}
    rl.append_lineage(user_id, {"lineage": lineage, "frontier": frontier},
                      base_dir)
    return {"outcome": "ROUTE_CREATED",
            "reason": "lineage baru" + (" (reopened)" if closed_row
                                        else ""),
            "lineage": lineage, "frontier": frontier}


def _sig(nodes: list[dict[str, Any]]) -> tuple:
    """GRAPH CONTENT signature (for material-change detection): structure
    at candidate level — resolved-id (UUID) does NOT count (a
    new id per instantiation may differ without being considered material)."""
    by_id = {n["node_id"]: n for n in nodes}

    def _dep(n):
        out = []
        for d in n.get("depends_on", []):
            t = by_id.get(d)
            out.append((tuple(t["resolves"]), t.get("execution_context"))
                       if t else ("?", d))
        return tuple(sorted(out))

    # activity/order IGNORED (render wording ≠ material change —
    # review 568beb9): signature = resolves + strength + depends_on
    # structure + execution_context
    return tuple(sorted(
        (tuple(n["resolves"]), n.get("strength"),
         _dep(n), n.get("execution_context")) for n in nodes))


def _reuse_open(row: dict[str, Any], template: dict[str, Any],
                applicability: str, app_cites: list[str],
                reader: StatusReader, user_id: str,
                revision_label: str, base_dir,
                read_only: bool = False) -> dict[str, Any]:
    """PATCH review 6585c32 (RED: stale projection): route_id
    is RETAINED, but satisfaction/executability/frontier are COMPUTED
    ANEW from the current reader+evidence (§3.2 status-computed-not-
    stored; §6.4 recompute-without-sticky). Material graph change ->
    revision_no+1; node identity match (resolves+activity+strength+
    deps-candidate+execution_context) is INHERITED, a new node = new
    identity. Write a NEW row (last-row-wins) so reload is consistent."""
    lin = row["lineage"]
    route_id = lin["route_id"]
    old_rev = lin["revisions"][-1]
    old_nodes = old_rev["nodes"]
    new_nodes = _build_nodes_u(template, reader, old_nodes)
    same_graph = _sig(new_nodes) == _sig(old_nodes)
    if same_graph:
        new_rev = {**old_rev, "nodes": new_nodes}
        reason = "graph identik — projection RE-COMPUTED dari reader/" \
                 "evidence terkini (stale projection tak dikembalikan)"
    else:
        new_rev = {**old_rev, "revision_no": old_rev["revision_no"] + 1,
                   "nodes": new_nodes,
                   "label": revision_label or old_rev["label"]}
        reason = (f"material graph berubah — revision "
                  f"{old_rev['revision_no']} -> {new_rev['revision_no']}; "
                  f"node identity match diwarisi, node baru = identity baru")
    # revision history INTACT for material change (§3.3 versioned
    # content — review P0-1); replace-last only for re-projection of an
    # identical graph (same rev_no, not a new historical event)
    hist = (lin["revisions"] + [new_rev] if not same_graph
            else lin["revisions"][:-1] + [new_rev])
    lineage = {**lin, "revisions": hist,
               "applicability": {"status": applicability,
                                 "evidence": app_cites}}
    frontier = _frontier_for(route_id, applicability, new_nodes)
    # read-only re-projection: compute the SAME payload, WITHOUT writing a lineage row
    if not read_only:
        rl.append_lineage(user_id, {"lineage": lineage, "frontier": frontier},
                          base_dir)
    return {"outcome": "ROUTE_REUSED", "reason": reason,
            "lineage": lineage, "frontier": frontier}


def _build_nodes_u(template: dict[str, Any], reader: StatusReader,
                   old_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-instantiation with INHERITED IDENTITY: template node key
    matching an old node -> node_id REUSED; the rest get a new UUID."""
    old_by_key: dict[tuple, str] = {}
    for n in old_nodes:
        # INV-R5: node identity = (primary_requirement_id,
        # execution_context for INV-R18 twins) — activity/position/
        # order = CONTENT (review 568beb9): wording changes are NOT a
        # new identity/revision
        k = (tuple(n["resolves"]), n.get("execution_context"))
        old_by_key[k] = n["node_id"]

    key_by_candidate: dict[str, str] = {}
    for nc in template["node_candidates"]:
        if len(nc["resolves"]) > 1:
            raise ValueError(
                f"candidate {nc['candidate_key']}: multi-resolves = T2+ "
                f"(review 6585c32)")
        k = (tuple(nc["resolves"]), nc.get("execution_context"))
        key_by_candidate[nc["candidate_key"]] = (
            old_by_key.get(k) or str(uuid.uuid4()))

    def _resolve_dep(dep: str) -> str:
        if dep in key_by_candidate:
            return key_by_candidate[dep]
        raise ValueError(f"depends_on {dep!r} does not resolve to a candidate_key")

    nodes: list[dict[str, Any]] = []
    for nc in template["node_candidates"]:
        rid = nc["resolves"][0]
        node = {
            "node_id": key_by_candidate[nc["candidate_key"]],
            "resolves": nc["resolves"],
            "strength": nc["strength"],
            "depends_on": [_resolve_dep(d) for d in nc["depends_on"]],
            "activity": nc["activity"],
            "satisfaction": {"status": _read(reader, rid)},
            "execution_view": "NOT_STARTED",
        }
        if nc.get("execution_context"):
            node["execution_context"] = nc["execution_context"]
        if nc.get("i18n"):
            # UI language version (docs/03 §7): UI/inspector picks en; the `activity` text stays
            # machine-canonical
            node["i18n"] = nc["i18n"]
        nodes.append(node)
    _apply_executability(nodes)
    return nodes
