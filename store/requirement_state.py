"""Ledger-backed Requirement State Reader — the ONLY way to read requirement state.

internal-docs §25. The contracts (`RequirementState`, `RequirementStateReader`) live in
`core/navigation/requirement_state.py` (generic); this module only binds them to the user-scoped ledger
(`store/adjudication_ledger.py`):

    Route (StatusReader)   ─┐
    Readiness (node route)  ├─►  LedgerRequirementReader(user_id) ─► ledger[user_id] (last entry wins)
    Question Planner        ─┘

Three invariants are guarded:
  - USER SCOPE: a reader is always bound to one validated `user_id` (`store.user_scope`); there is no
    global reader. User A's requirement status is never readable for user B.
  - UNKNOWN != ABSENT: with no ledger entry the result is `adjudicated=False` (UNKNOWN by absence), with
    no citations, origin, or time — never invented. An entry with status UNKNOWN (the adjudication was
    inconclusive) stays `adjudicated=True`.
  - no status is written here: a pure reader. Writing happens only via `adjudicate_and_persist`.
"""
from __future__ import annotations

from typing import Any, Callable

from core.navigation.requirement_state import (
    SUPPORT_NONE,
    SUPPORT_UNSCOPED,
    MappingReader,
    RequirementState,
    RequirementStateReader,
    unknown_state,
)
from store import adjudication_ledger as ledger
from store.user_scope import validate_user_id

# Gate A (15 Oct): the label names the ADJUDICATOR IDENTITY (deterministic) — NOT the evidence
# verification method. The per-mapping method (`deterministic_predicate` | `second_pass_verified`) is not
# persisted in the ledger entry (exact-key schema, not extended without contract justification); its
# trace lives in `session.last_adjudication` (candidates + second_pass summary, BC-03).
VERIFICATION_METHOD = "deterministic_adjudicator"


def state_from_entry(
    requirement_id: str, entry: dict[str, Any] | None, support: str = SUPPORT_NONE
) -> RequirementState:
    """Ledger entry (`{entry_id, adjudication}`) -> RequirementState. None -> UNKNOWN by absence."""
    if entry is None:
        return unknown_state(requirement_id, support)
    adj = entry["adjudication"]
    conflict = adj.get("conflict") or {}
    both = bool(conflict.get("present_evidence_refs")) and bool(conflict.get("contradicting_evidence_refs"))
    verification: dict[str, Any] = {
        "method": VERIFICATION_METHOD,
        "entry_id": entry.get("entry_id"),
        "rule_evaluation": dict(adj.get("rule_evaluation") or {}),
        "evaluation_time": adj.get("evaluation_time"),
    }
    if both:
        verification["conflict"] = {
            "present_evidence_refs": list(conflict.get("present_evidence_refs") or []),
            "contradicting_evidence_refs": list(conflict.get("contradicting_evidence_refs") or []),
        }
    return RequirementState(
        requirement_id=requirement_id,
        satisfaction=adj["status"],
        adjudicated=True,
        evidence_refs=tuple(adj.get("evidence_refs") or ()),
        verification=verification,
        last_updated=adj.get("adjudicated_at"),
        conflict=both,
        support=support,
    )


class LedgerRequirementReader:
    """User-scoped ledger reader. One instance = one ledger snapshot (read once).

    R1 Probe A remediation (17 Oct): optional `goal_id` narrows the snapshot to
    one business context — goal-scoped entries of other contexts are unread
    (legacy without a goal stays readable; policy in ledger._latest_entries)."""

    def __init__(self, user_id: str, *, goal_id: str | None = None,
                 support_of: Callable[[str], str] | None = None) -> None:
        self.user_id = validate_user_id(user_id)  # fail-closed: no fallback to a shared file
        self.goal_id = goal_id
        self._support_of = support_of or (lambda _rid: SUPPORT_NONE)
        self._entries: dict[str, dict[str, Any]] | None = None

    def _snapshot(self) -> dict[str, dict[str, Any]]:
        if self._entries is None:
            self._entries = ledger._latest_entries(self.user_id, self.goal_id)
        return self._entries

    def read(self, requirement_id: str) -> RequirementState:
        entry = self._snapshot().get(requirement_id)
        return state_from_entry(requirement_id, entry, self._support_of(requirement_id))

    def adjudicated_ids(self) -> list[str]:
        """Requirements with a valid adjudication for this user (audit; not a list of what holds)."""
        return sorted(self._snapshot())


def user_requirement_reader(
    user_id: str | None, *, goal_id: str | None = None,
    support_of: Callable[[str], str] | None = None
) -> RequirementStateReader:
    """Reader for a session. Without a user (`None`/empty) there is no ledger: an honest reader reports
    UNKNOWN by absence with `NO_USER_SCOPE` support — it does not fall back to a shared ledger.

    R1 Probe A remediation: `goal_id` = the session's business context (the session's goal_id;
    inherited by continuation sessions of the same map via prior_session_id) — two different
    businesses of the same user no longer share requirement state."""
    if not user_id:
        return MappingReader({}, support=SUPPORT_UNSCOPED)
    return LedgerRequirementReader(user_id, goal_id=goal_id, support_of=support_of)
