"""Requirement State — THE single reader of requirement state for Route, Readiness, and the Question Planner.

internal-docs §25 (M4). Requirement Registry = what MUST be true (WHAT, global, context-free).
A requirement's state for a user belongs to neither the registry nor the evidence: it is the result of
ADJUDICATION (registry satisfaction rules over verified evidence) recorded in a user-scoped ledger.

    Evidence -> mapper (proposal) -> verification -> adjudication -> ledger -> RequirementStateReader
                                                                 \\-> Route (status_reader)
                                                                  \\-> Readiness (route nodes; merged)
                                                                   \\-> Question Planner

Three things guarded here (and nowhere else):

  1. `UNKNOWN` because there is NO adjudication (`adjudicated=False`) differs from an adjudication that
     produced `UNKNOWN` (`adjudicated=True`: inconclusive evidence, or two sides in conflict). Neither is ever
     demoted to `ABSENT` (UNKNOWN != ABSENT; absence of evidence != evidence of absence).
  2. Merging two readings of the same requirement (the latest state from ledger/route node vs a path check on
     a state signal) uses ONE function, `merge_readings`: Readiness and the session reader have no separate
     evaluators that could disagree. Conflict = structured metadata, not a fifth `Satisfaction` value.
  3. `support` states whether CONVERSATIONAL evidence can shift this requirement's state at all (a reviewed
     formal rule exists) — not a claim about the state itself. A requirement without a formal rule stays
     UNKNOWN until a valid adjudication exists; the planner must not ask it as if asking would shift it.

This module is GENERIC: it knows no domain, store, ledger, or mapper (core must not import that layer).
The ledger-backed reader implementation lives in `store/requirement_state.py`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from core.navigation.applicability import owner_path_id
from core.navigation.contracts import Satisfaction

# Adjudication support: can conversational evidence shift this requirement's state?
SUPPORT_FORMAL = "FORMAL_RULE"  # a reviewed formal rule exists -> evidence can shift the state
SUPPORT_UNIT = "UNIT_CONTEXT_REQUIRED"  # a formal rule exists, but it needs a unit identity (not derivable)
SUPPORT_SECOND_PASS = "SECOND_PASS"  # the rule is still PROSE but a mapper -> second-pass verifier path
# (D-A2 C) exists: the state POTENTIALLY shifts via conversation. This is a PATH CLAIM, not a guarantee
# of mapper recall or of the verifier's outcome (Gate A Oct 15, owner decision: conditional,
# NO mass promotion; planner priority/ASK_CAP/applicability unchanged).
SUPPORT_NONE = "NO_FORMAL_RULE"  # unknown to the registry / no conversational verification path
SUPPORT_UNSCOPED = "NO_USER_SCOPE"  # session without a user: no ledger, hence no adjudication
SUPPORT_VALUES = (SUPPORT_FORMAL, SUPPORT_UNIT, SUPPORT_SECOND_PASS, SUPPORT_NONE, SUPPORT_UNSCOPED)

_UNKNOWN = str(Satisfaction.UNKNOWN)
_SAT = {s.value for s in Satisfaction}


@dataclass(frozen=True)
class RequirementState:
    """The state of ONE requirement for one user according to the adjudication ledger.

    `satisfaction`  PRESENT | PARTIAL | UNKNOWN | ABSENT. `UNKNOWN` when `adjudicated=False` = UNKNOWN by
                    absence (no valid adjudication yet; INV-9), not a finding.
    `adjudicated`   True only when the ledger holds a valid adjudication for this requirement.
    `evidence_refs` the evidence cited by that adjudication (empty when none).
    `verification`  the state's origin: method, rule mode, ledger entry id, rule_evaluation (audit). None when
                    absent.
    `last_updated`  time of the last adjudication (epoch seconds) when present; never invented.
    `conflict`      the adjudication found support AND counter-evidence (D-A1a): the result is UNKNOWN and
                    both sides are recorded. Conflict is not a fifth Satisfaction value.
    `support`       see the SUPPORT_* constants."""

    requirement_id: str
    satisfaction: str = _UNKNOWN
    adjudicated: bool = False
    evidence_refs: tuple[str, ...] = ()
    verification: Mapping[str, Any] | None = None
    last_updated: int | None = None
    conflict: bool = False
    support: str = SUPPORT_NONE

    def __post_init__(self) -> None:
        if self.satisfaction not in _SAT:
            raise ValueError(
                f"{self.requirement_id}: satisfaction {self.satisfaction!r} di luar {sorted(_SAT)}"
            )
        if self.support not in SUPPORT_VALUES:
            raise ValueError(f"{self.requirement_id}: support {self.support!r} di luar {SUPPORT_VALUES}")
        carries = self.satisfaction != _UNKNOWN or self.evidence_refs or self.verification
        if not self.adjudicated and carries:
            # state, citations, or origin without an adjudication = invention; UNKNOWN by absence carries none
            raise ValueError(f"{self.requirement_id}: keadaan/sitasi/asal tanpa adjudikasi tidak sah")

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "satisfaction": self.satisfaction,
            "adjudicated": self.adjudicated,
            "evidence_refs": list(self.evidence_refs),
            "verification": dict(self.verification) if self.verification else None,
            "last_updated": self.last_updated,
            "conflict": self.conflict,
            "support": self.support,
        }

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "RequirementState":
        return RequirementState(
            requirement_id=d["requirement_id"],
            satisfaction=d.get("satisfaction", _UNKNOWN),
            adjudicated=bool(d.get("adjudicated")),
            evidence_refs=tuple(d.get("evidence_refs") or ()),
            verification=d.get("verification"),
            last_updated=d.get("last_updated"),
            conflict=bool(d.get("conflict")),
            support=d.get("support", SUPPORT_NONE),
        )


def unknown_state(requirement_id: str, support: str = SUPPORT_NONE) -> RequirementState:
    """UNKNOWN by absence: no valid adjudication yet. Carries no citations, origin, or timestamp."""
    return RequirementState(requirement_id, support=support)


class RequirementStateReader(Protocol):
    """The only way to read requirement state. Implementations live outside core (user-scoped ledger)."""

    def read(self, requirement_id: str) -> RequirementState: ...


def status_reader(reader: RequirementStateReader) -> Callable[[str], str | None]:
    """Adapter for the route composer (`StatusReader`): None = UNKNOWN by absence (D-A1d), not UNKNOWN."""

    def read(requirement_id: str) -> str | None:
        st = reader.read(requirement_id)
        return st.satisfaction if st.adjudicated else None

    return read


class MappingReader:
    """In-memory reader (tests, replay, sessions without a ledger). An unlisted id = UNKNOWN by absence."""

    def __init__(
        self,
        states: Mapping[str, RequirementState | str] | None = None,
        *,
        support: str | Mapping[str, str] = SUPPORT_NONE,
    ) -> None:
        self._states = dict(states or {})
        self._support = support

    def _support_of(self, requirement_id: str) -> str:
        if isinstance(self._support, str):
            return self._support
        return self._support.get(requirement_id, SUPPORT_NONE)

    def read(self, requirement_id: str) -> RequirementState:
        raw = self._states.get(requirement_id)
        if raw is None:
            return unknown_state(requirement_id, self._support_of(requirement_id))
        if isinstance(raw, RequirementState):
            return raw
        return RequirementState(
            requirement_id,
            satisfaction=raw,
            adjudicated=True,
            verification={"method": "fixture"},
            support=self._support_of(requirement_id),
        )


def merge_readings(primary: str, readings: Sequence[str]) -> tuple[str, tuple[int, ...]]:
    """(primary state, path-check readings) -> (projected state, indexes of the disagreeing readings).

    ONE rule for Readiness (`readiness._adjudicate`) and the session reader — not two evaluators:
      - a definite state beats UNKNOWN: a primary UNKNOWN adopts the FIRST definite reading;
      - every definite reading that differs from the projected state = DISAGREEMENT (structured metadata);
      - UNKNOWN is never a disputing party, and is never demoted to ABSENT.
    `primary` = the state from ledger adjudication (route node / reader); `readings` = path-check states over
    state signals. States outside the enum are treated as UNKNOWN (never invented into definite)."""
    state = primary if primary in _SAT else _UNKNOWN
    norm = [r if r in _SAT else _UNKNOWN for r in readings]
    if state == _UNKNOWN:
        definite = [r for r in norm if r != _UNKNOWN]
        if definite:
            state = definite[0]
    disagreeing = tuple(i for i, r in enumerate(norm) if r != _UNKNOWN and r != state)
    return state, disagreeing


@dataclass(frozen=True)
class ContextReading:
    """One requirement's reading WITHIN one context (path or route) — that context's effective state."""

    kind: str  # "path" | "route"
    id: str
    applicability: str  # THE CONTEXT's applicability: APPLIES | UNKNOWN | NOT_APPLICABLE
    via: str  # "check" | "node" | "template"
    strength: str | None  # check: hard|prereq; node: hard|soft
    navigable: bool  # False when the context's path is STOP (engine or lifecycle)
    ref: str | None  # check_id | node_id
    state: str = _UNKNOWN  # the effective state in this context after merge
    conflict: bool = False
    sources: tuple[str, ...] = ()  # where the reading came from: "ledger" | "check"
    # The RAW check reading (state_signal) used to detect ledger-vs-check conflicts. Kept on the view so the
    # conflict lineage survives the state merge (R5/P0-A); None for older call sites.
    signal_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "applicability": self.applicability,
            "via": self.via,
            "strength": self.strength,
            "navigable": self.navigable,
            "ref": self.ref,
            "state": self.state,
            "conflict": self.conflict,
            "sources": list(self.sources),
            "signal_state": self.signal_state,
        }


@dataclass(frozen=True)
class RequirementView:
    """ONE requirement's view for the planner: applicability (from contexts) + state (from reader) + origin.

    `satisfaction` = the requirement-level effective state (the ledger is authoritative; definite checks
    fill UNKNOWN — `merge_readings`). `ledger` = the ledger reading as-is (adjudicated / by absence).
    Contexts carry their own states; `conflict` when some context disagrees or the adjudication found
    two sides."""

    requirement_id: str
    applicability: str
    reason: str
    satisfaction: str
    ledger: RequirementState
    contexts: tuple[ContextReading, ...] = field(default_factory=tuple)
    conflict: bool = False

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        return self.ledger.evidence_refs

    @property
    def verification(self) -> Mapping[str, Any] | None:
        return self.ledger.verification

    @property
    def last_updated(self) -> int | None:
        return self.ledger.last_updated

    @property
    def support(self) -> str:
        return self.ledger.support

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "applicability": self.applicability,
            "reason": self.reason,
            "satisfaction": self.satisfaction,
            "evidence_refs": list(self.evidence_refs),
            "verification": dict(self.verification) if self.verification else None,
            "last_updated": self.last_updated,
            "support": self.support,
            "adjudicated": self.ledger.adjudicated,
            "ledger_state": self.ledger.satisfaction,
            "conflict": self.conflict,
            "contexts": [c.to_dict() for c in self.contexts],
        }


def _check_states_for(path: Mapping[str, Any] | None, requirement_id: str) -> list[tuple[str, str]]:
    """[(check_id, reading)] for path checks anchoring this requirement (PRESENT|ABSENT|UNKNOWN).

    The RAW reading (state_signal) is used when the evaluator has already merged checks with the ledger: the
    state is adjudicated, so two definite readings that disagree seem to agree (bug R5/P0-A — a ledger ABSENT
    vs a PRESENT signal no longer shows as conflict, though Readiness does). The state fallback keeps older
    call sites (without a ledger-backed evaluator) identical."""
    out: list[tuple[str, str]] = []
    for c in (path or {}).get("checks") or []:
        if c.get("requirement_id") == requirement_id:
            raw = c.get("state_signal")
            if raw is None:
                raw = c.get("state")
            out.append((str(c.get("check_id")), str(raw or _UNKNOWN).upper()))
    return out


def _node_for(route: Mapping[str, Any], requirement_id: str) -> Mapping[str, Any] | None:
    for n in route.get("nodes") or []:
        resolves = n.get("resolves") or []
        if resolves and resolves[0] == requirement_id:
            return n
    return None


def read_requirement_views(
    applicable: "Any",  # core.navigation.applicability.ApplicableRequirementSet (avoids a cyclic import)
    reader: RequirementStateReader,
    path_set: Mapping[str, Any] | None,
    route_data: Mapping[str, Any] | None,
) -> dict[str, RequirementView]:
    """ApplicableRequirementSet + reader + PathSet + routes -> {requirement_id: RequirementView}.

    Per CONTEXT: the effective state = `merge_readings(primary, path checks)` under the SAME rule as
    Readiness. Route context: primary = the node's satisfaction (ledger via the route composer). A path
    context without a route node (optional routes): primary = the ledger reading from the reader — the
    ledger is authoritative wherever the requirement appears, not only when a route exists. Requirement
    level: ledger then definite checks."""
    paths = {p["path_id"]: p for p in (path_set or {}).get("paths") or []}
    routes = {r["route_id"]: r for r in (route_data or {}).get("routes") or []}
    out: dict[str, RequirementView] = {}
    for item in applicable.items:
        rid = item.requirement_id
        ledger = reader.read(rid)
        ledger_state = ledger.satisfaction if ledger.adjudicated else _UNKNOWN
        ctx_out: list[ContextReading] = []
        for ctx in item.contexts:
            path = paths.get(ctx.id) if ctx.kind == "path" else None
            route = routes.get(ctx.id) if ctx.kind == "route" else None
            owner = paths.get(owner_path_id(route, paths) or "") if route else path
            checks = _check_states_for(owner, rid)
            node = _node_for(route, rid) if route else None
            if node is not None:
                primary = str(((node.get("satisfaction") or {}).get("status")) or _UNKNOWN).upper()
                # node UNKNOWN = UNKNOWN by absence or an inconclusive adjudication: not a ledger claim
                src = ["ledger"] if primary != _UNKNOWN else []
            else:
                primary, src = ledger_state, (["ledger"] if ledger.adjudicated else [])
            state, bad = merge_readings(primary, [s for _, s in checks])
            if checks and any(s != _UNKNOWN for _, s in checks):
                src = src + ["check"]
            ctx_out.append(
                ContextReading(
                    kind=ctx.kind,
                    id=ctx.id,
                    applicability=ctx.applicability,
                    via=ctx.via,
                    strength=ctx.strength,
                    navigable=ctx.navigable,
                    ref=ctx.ref,
                    state=state,
                    conflict=bool(bad),
                    sources=tuple(dict.fromkeys(src)),
                    signal_state=checks[0][1] if checks else None,
                )
            )
        all_checks = [
            s for p in paths.values() for _, s in _check_states_for(p, rid)
        ]
        state, bad = merge_readings(ledger_state, all_checks)
        out[rid] = RequirementView(
            requirement_id=rid,
            applicability=item.applicability,
            reason=item.reason,
            satisfaction=state,
            ledger=ledger,
            contexts=tuple(ctx_out),
            conflict=bool(ledger.conflict or bad or any(c.conflict for c in ctx_out)),
        )
    return out
