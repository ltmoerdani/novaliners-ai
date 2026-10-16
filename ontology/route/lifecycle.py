"""M4 ROUTE LIFECYCLE — terminal transitions & applicability (owner verdict
27 Sep: M4 first, then the bridge install; the DEBT-M4 from T1.17 is paid off).

ENUM DECISION (owner's question, 27 Sep): COMPLETED is NOT a `lineage_status`
value. Terminal lineage is stored CLOSED + `close_reason`; COMPLETED is a
DERIVED status (int 08 §3.2: terminal COMPLETED | CLOSED; INV-R11: COMPLETED
= goal satisfaction valid at the measurement horizon).
Reasons:
  1. Schema/validator FINAL: lineage_status enum ["OPEN","CLOSED"]
     (validate_route.py) — changing it means changing a locked contract.
  2. Goal status authority = the adjudication ledger (INV-R12). Storing
     COMPLETED as an enum would COPY that authority into the lineage — two
     sources of truth for "goal achieved".
  3. Model B (INV-R20): if COMPLETED became an enum, completed lineage would
     VANISH from the `find_closed_by_key` scan (reopened_from) — a silent
     bug class. With close_reason, both terminal flavors pass one gate.
  4. int 08 §7: store-vs-compute for a derived status = an implementation decision.

TRANSITIONS (owner 27 Sep):
  - TERMINAL: goal PRESENT (valid proof at the measurement horizon) → CLOSED
    `close_reason=goal_achieved` (derived COMPLETED). Applicability falling
    with positive proof → CLOSED `close_reason=not_applicable`.
  - NON-TERMINAL: APPLIES ↔ UNDETERMINED → lineage STAYS OPEN, frontier
    recomputed along with it (RESOLVE_APPLICABILITY when UNDETERMINED). This
    is EMERGENT from the `compose_route` re-projection (§3.2: status is
    computed, never sticky) — the lifecycle delegates, it does not imitate.
  - EVERY transition = a NEW row in the store (last-row-wins), with a reason.
  - MODEL B: terminal lineage is NEVER reopened — reconcile only finds rows
    via `find_open_by_key` (CLOSED never matches).

The bridge stays ORCHESTRATION only — the lifecycle caller is the same
runtime path; semantics (applicability, satisfaction) remain owned by the
composer + reader.
"""
from __future__ import annotations

import time
from typing import Any

from ontology.route.compose import (  # noqa: F401  (intern package-same)
    _build_nodes_u,
    _frontier_for,
    _read,
    compose_route,
)
from store import route_lineages as rl
from store.user_scope import validate_user_id

# close_reason enum (the derived_status key; not lineage_status)
CLOSE_GOAL_ACHIEVED = "goal_achieved"      # derived → COMPLETED
CLOSE_NOT_APPLICABLE = "not_applicable"    # derived → CLOSED

DERIVED_COMPLETED = "COMPLETED"            # int 08 §3.2 terminal (derived)
DERIVED_CLOSED = "CLOSED"


def derived_route_status(lineage: dict[str, Any]) -> str | None:
    """The DERIVED terminal status per the enum decision above. None = not
    terminal (OPEN — runtime). COMPLETED comes only from the close_reason
    goal_achieved (INV-R11: completion is a satisfaction matter)."""
    if lineage.get("lineage_status") != "CLOSED":
        return None
    if lineage.get("close_reason") == CLOSE_GOAL_ACHIEVED:
        return DERIVED_COMPLETED
    return DERIVED_CLOSED


def _evaluate_applicability(template: dict[str, Any],
                            evidence: list[Any]) -> tuple[str, list[str]]:
    """MIRROR of compose.py step 2 (the SINGLE SEMANTIC SOURCE lives there):
    filter is_gap before evaluation (corrective 9c5bcb4), for both
    applies and not_applicable. This 10-line duplication is deliberate,
    with cross comments — owner verdict: compose.py must not be refactored
    again; if compose step-2 changes, this mirror MUST change in the same
    stroke (lifecycle tests lock their alignment via the gap & negation cases)."""
    from core.stages.rule_predicates import evaluate_predicate
    app_evidence = [e for e in evidence if not getattr(e, "is_gap", False)]
    aw = template.get("applies_when") or {}
    applies = False
    cites: list[str] = []
    if aw.get("applies"):
        applies, cites, _r = evaluate_predicate(
            {"any_of": aw["applies"]}, app_evidence, "",
            negation_aware=True)
    not_app = False
    na_cites: list[str] = []
    if aw.get("not_applicable"):
        not_app, na_cites, _r2 = evaluate_predicate(
            {"any_of": aw["not_applicable"]}, app_evidence, "",
            negation_aware=True)
    if not applies and not_app:
        return "NOT_APPLICABLE", na_cites
    return ("APPLIES", cites) if (applies and not not_app) else \
        ("UNDETERMINED", [])


def _close(user_id: str, row: dict[str, Any], reason: str,
           basis: dict[str, Any], base_dir,
           applicability: dict[str, Any] | None = None) -> dict[str, Any]:
    """A terminal transition = a NEW row (last-row-wins), with a reason.
    The optional `applicability` is UPDATED in the same record (corrective
    from review 7de3e73: closing not_applicable without updating
    applicability leaves a contradictory record — APPLIES + close_reason
    not_applicable; now the record is consistent and INV-R2 is satisfied
    in the record itself: NOT_APPLICABLE carries positive proof)."""
    lineage = {**row["lineage"], "lineage_status": "CLOSED",
               "close_reason": reason, "closed_at": int(time.time()),
               "close_basis": basis}
    if applicability is not None:
        lineage["applicability"] = applicability
    rl.append_lineage(user_id, {"lineage": lineage, "frontier": []}, base_dir)
    return {"outcome": "LINEAGE_COMPLETED" if reason == CLOSE_GOAL_ACHIEVED
            else "LINEAGE_CLOSED",
            "reason": f"lineage CLOSED close_reason={reason} — "
                      f"{basis.get('detail', '')}",
            "lineage": lineage, "frontier": [],
            "derived_route_status": derived_route_status(lineage)}


def reconcile(user_id: str, template: dict[str, Any], *,
              goal_anchor: str, scope_anchor: list[str],
              evidence: list[Any],
              requirement_status_reader: Any,
              context_id: str | None = None,
              base_dir=None) -> dict[str, Any] | None:
    """One lifecycle pass for OPEN lineage keyed by (goal, strategy, scope,
    context — Probe B remediation 17 Oct: context_id = the session's business context).

    Returns None when there is no OPEN lineage (including: already terminal —
    Model B, terminal is never reopened; NO new row is written).
    Non-terminal transitions are delegated to compose_route (re-projection;
    outcome ROUTE_REUSED) — applicability & frontier recomputed."""
    validate_user_id(user_id)
    key = {"goal_anchor": goal_anchor, "strategy_id": template["strategy_id"],
           "scope_anchor": scope_anchor, "context_id": context_id}
    open_row = rl.find_open_by_key(user_id, key, base_dir)
    if open_row is None:
        return None  # no OPEN: terminal stays terminal (Model B)

    # 1. terminal: goal PRESENT per the CURRENT LEDGER STATUS (INV-R11/
    #    INV-R12 — the lifecycle does NOT check the measurement horizon itself;
    #    horizon validity = the adjudicator's business, §6.4)
    goal_status = _read(requirement_status_reader, goal_anchor)
    if goal_status == "PRESENT":
        return _close(user_id, open_row, CLOSE_GOAL_ACHIEVED,
                      {"goal_anchor": goal_anchor, "goal_status": goal_status,
                       "detail": f"goal {goal_anchor} status ledger terkini "
                                 f"PRESENT — route selesai"},
                      base_dir)

    # 2. terminal: applicability falls with positive proof (INV-R3)
    app_status, app_cites = _evaluate_applicability(template, evidence)
    if app_status == "NOT_APPLICABLE":
        return _close(user_id, open_row, CLOSE_NOT_APPLICABLE,
                      {"applicability": "NOT_APPLICABLE",
                       "evidence": app_cites,
                       "detail": "applicability gugur dgn bukti positif"},
                      base_dir,
                      applicability={"status": "NOT_APPLICABLE",
                                     "evidence": app_cites})

    # 3. non-terminal (APPLIES ↔ UNDETERMINED): delegated to the composer —
    #    the re-projection writes a new OPEN row with applicability +
    #    frontier recomputed (UNDETERMINED → RESOLVE_APPLICABILITY §3.5)
    result = compose_route(template, goal_anchor=goal_anchor,
                           scope_anchor=scope_anchor, evidence=evidence,
                           requirement_status_reader=requirement_status_reader,
                           motion=open_row["lineage"]["motion"],
                           user_id=user_id, context_id=context_id,
                           base_dir=base_dir)
    before = open_row["lineage"]["applicability"]["status"]
    # applicability_after comes from the COMPOSE RESULT (not the mirror) —
    # corrective from review 7de3e73: what gets recorded = the actual state; the
    # mirror is used ONLY to detect NOT_APPLICABLE in step 2.
    result["transition"] = {
        "kind": "APPLICABILITY_RESOLVED"
        if before != result["lineage"]["applicability"]["status"]
        else "REPROJECTION",
        "applicability_before": before,
        "applicability_after": result["lineage"]["applicability"]["status"],
        "terminal": False,
    }
    return result
