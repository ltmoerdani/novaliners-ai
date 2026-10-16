"""SESSION RUNTIME BRIDGE — session → composition orchestration (T2, owner
verdict 27 Sep: the bridge is ready to be built after f15309c).

BRIDGE INVARIANTS (owner, 27 Sep — strictly guarded):
1. The bridge is a COMPOSITION/ORCHESTRATION LAYER ONLY. It does not diagnose,
   interpret applicability, create new semantic rules, or choose the NextMove —
   all of that belongs to other layers.
2. USER IDENTITY IS EXPLICIT FROM THE SESSION BOUNDARY. The bridge NEVER takes
   user_id from evidence, goal text, other metadata, or inference — only
   `session.user_id`, validated ONCE at the entry point
   (store.user_scope.validate_user_id) BEFORE any store is touched (including
   legacy stores not yet using the shared helper — debt recorded in tests).
3. ALL status lookups are scoped to the user session: the reader built by the
   bridge is always `latest_status(user_id, rid)` — the global StatusReader
   `latest_status(rid)` has been GONE since 71b3c63 and must NOT be recreated
   here.

Flow: Session(user_id, evidence) → validate → user-scoped reader →
compose_route(...). No LLM, deterministic.
"""
from __future__ import annotations

from typing import Any

from core.navigation.requirement_state import status_reader
from store.requirement_state import LedgerRequirementReader
from store.user_scope import validate_user_id

# A1 DECISION (owner 27 Sep): one scope per user for this iteration —
# see the run_session_route docstring (granularity debt recorded).
SCOPE_PER_USER = ["state:user"]


def user_status_reader(user_id: str, goal_id: str | None = None):
    """User-scoped StatusReader (bridge contract #3) — and, since the Probe A
    remediation (17 Oct), scoped to the BUSINESS CONTEXT as well when `goal_id`
    is given: goal-bearing ledger entries of other businesses are not readable
    from here. Returning None = UNKNOWN by absence (D-A1d) — the composer
    validates its own enum.

    M4 (doc 14 §25): not a second read path to the ledger — a thin adapter on top of the single
    Requirement State Reader (`store.requirement_state`), which Readiness and the
    Question Planner also read."""
    validate_user_id(user_id)
    return status_reader(LedgerRequirementReader(user_id, goal_id=goal_id))


def run_session_route(
    session: Any,
    template: dict[str, Any],
    *,
    base_dir=None,
    read_only: bool = False,
) -> dict[str, Any]:
    """Session → composition. `session` must at least have `.user_id` and
    `.evidence` (duck-typed store.memory.Session — no circular import:
    the bridge does not mutate the session, it only READS).

    A1 DECISION (owner 27 Sep; tightened by review 5611993):
    - goal_anchor is ALWAYS `template["goal_anchor"]` — the route's goal is
      the targeted capability state, a GRAMMAR declaration validated by the
      validator (registry + requires + resolver), NOT the caller's choice
      and NOT a derivation of the user's revenue goal. The override
      parameter was REMOVED: the owner test proved an override enables a
      second lineage whose goal was never declared by the template
      (copy_composition) — the door A1 closed would reopen.
    - scope_anchor is ALWAYS ["state:user"] (SCOPE_PER_USER) — ONE scope
      per user; per-call scope = a new lineage per variation =
      INV-R13 broken. GRANULARITY debt recorded (int 08 §8.2/8.3):
      session evidence = EvidenceItem, not UniversalClaim; once claims
      are normalized, the scope is raised — fork via successor_of.

    Returns the compose_route/lifecycle result as-is (outcome/reason/
    lineage/frontier). The bridge adds nothing, modifies nothing, judges
    nothing — invariant #1."""
    # SINGLE identity entry point (bridge contract #2): validated
    # before evidence is read and before any store is called.
    user_id = validate_user_id(getattr(session, "user_id", None))

    goal = template.get("goal_anchor")
    if not goal:
        raise ValueError(
            "goal_anchor tidak ada: template wajib membawa field "
            "'goal_anchor' (A1 owner 27 Sep — deklarasi tujuan route di "
            "template, divalidasi validator; bridge hanya membaca)")
    scope = list(SCOPE_PER_USER)
    # R1-remediation Probe A/B (17 Oct — the mechanism A1 pre-announced: "once
    # claims are normalized, the scope is raised"): the business context = the
    # session's goal_id. A continuing session of the same map inherits the goal
    # via prior_session_id (the create_session gate), so its context is STABLE
    # across sessions; two different businesses owned by the same user carry
    # different goals = different contexts. scope_anchor does NOT change
    # (still ["state:user"], A1 decision intact; context granularity now lives
    # in reconciliation_key.context_id + the ledger filter).
    goal_id = (getattr(session, "goal", None) or {}).get("goal_id") or None
    context_id = goal_id
    # D5: motion FROM the strategy registry (not the template — T1.13 — and
    # not the caller); unregistered strategy -> ValueError, not a default.
    from ontology.route.strategies import motion_for
    motion = motion_for(template["strategy_id"])

    from ontology.route.compose import compose_route  # local: avoid a test import cycle
    from ontology.route.lifecycle import reconcile  # local: avoid a cycle

    # LIFECYCLE FIRST (corrective from review 7de3e73 — owner: DEBT-M4 must be
    # active on the runtime path, not just a side door): the order remains
    # pure orchestration, no new semantic rules (invariant #1).
    #  - terminal transitions (LINEAGE_*) → returned as-is;
    #  - non-terminal → reconcile ALREADY delegates to compose_route
    #    (re-projection) — that compose result is what gets returned; the
    #    bridge never calls compose twice;
    #  - None (no OPEN lineage — including a new session/user) →
    #    compose for birth (the T1 contract).
    # READ-ONLY (P0-02): a GET must never create or reconcile lineage. Skip the lifecycle pass
    # entirely and ask the composer for a pure re-projection: an existing OPEN route is returned
    # without a new lineage row, and a route that was never born stays not-born.
    if read_only:
        return compose_route(
            template,
            goal_anchor=goal,
            scope_anchor=scope,
            evidence=list(getattr(session, "evidence", []) or []),
            requirement_status_reader=user_status_reader(user_id, goal_id),
            motion=motion,
            user_id=user_id,
            context_id=context_id,
            base_dir=base_dir,
            read_only=True,
        )
    r = reconcile(user_id, template, goal_anchor=goal,
                  scope_anchor=scope,
                  evidence=list(getattr(session, "evidence", []) or []),
                  requirement_status_reader=user_status_reader(user_id, goal_id),
                  context_id=context_id,
                  base_dir=base_dir)
    if r is not None:
        return r
    return compose_route(
        template,
        goal_anchor=goal,
        scope_anchor=scope,
        evidence=list(getattr(session, "evidence", []) or []),
        requirement_status_reader=user_status_reader(user_id, goal_id),
        motion=motion,
        user_id=user_id,
        context_id=context_id,
        base_dir=base_dir,
    )
