"""Candidate Path Generator — from the domain's possibility space + verified state to path CANDIDATES.

This stage only PROPOSES. It judges no feasibility, decides no applicability, and composes no route: that
is the evaluator's job (`core/navigation/evaluator.py`) and the route composer's. The separation is
deliberate — "the generator proposes, the evaluator decides" (analogous to the LLM proposing, the engine
deciding).

Emergence rules (no fixed count):
  - a candidate is born ONLY when the strategy's `emerges_when` is TRUE with real support (signals that are
    genuinely TRUE — a detected mechanism, a state claim, an active knowledge rule);
  - `emerges_when` FALSE  -> no basis (recorded as `not_emergent`), not a candidate;
  - `emerges_when` None   -> not yet decidable (recorded as `undetermined` with the missing signals);
  - the space's `goal_signal` not TRUE -> ZERO candidates + an explicit reason.
0, 1, 2, ..., N candidates are all valid; there is no invariant "five".

Candidate provenance = the supporting signals actually evaluated (not assembled afterwards)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.navigation.candidate import (
    NOT_EMERGENT,
    ORIGIN_STRATEGY,
    UNDETERMINED,
    CandidatePossibility,
    assumed_absences,
    generate_possibilities,
    overlay_of,
    with_mechanisms,
)
from core.navigation.contracts import (
    SIGNAL_MECHANISM,
    SIGNAL_RULE,
    SIGNAL_STATE,
    PossibilitySpace,
    Signal,
    SignalReader,
    StrategySpec,
    grounded,
    path_id_for,
)
from core.navigation.predicate import evaluate, signal_ids
from core.schema.provenance import TRANSCRIPT_PREFIX


@dataclass
class Candidate:
    """A contextual hypothesis before evaluation. `support` = [{signal, reason, refs}] backing emergence."""

    strategy: StrategySpec
    support: list[dict] = field(default_factory=list)
    # Candidate origin: declared strategy / mechanism pattern / both (`core/navigation/candidate.py`).
    origin: str = ORIGIN_STRATEGY
    possibility: CandidatePossibility | None = None

    @property
    def path_id(self) -> str:
        return path_id_for(self.strategy.strategy_id)


@dataclass
class CandidateSet:
    space_id: str
    candidates: list[Candidate] = field(default_factory=list)
    not_emergent: list[dict] = field(default_factory=list)  # {strategy_id}: all trigger signals FALSE
    undetermined: list[dict] = field(default_factory=list)  # {strategy_id, missing[]}: not yet decidable
    blockers: list[dict] = field(default_factory=list)  # {code, detail}: global reason for no candidates
    # PROV-04: knowledge signals claimed active whose basis cannot be formed. Recorded for audit; they never
    # become candidate support.
    unsupported: list[dict] = field(default_factory=list)  # {signal, reason}
    considered: int = 0
    # The Knowledge -> Mechanism -> Candidate Possibility layer: proposals (not yet paths) + mechanism audit.
    possibilities: list[CandidatePossibility] = field(default_factory=list)
    mechanisms: list[dict] = field(default_factory=list)  # derived mechanism activation audit


def _support_row(sid: str, sig: Signal) -> dict:
    row = {"signal": sid, "reason": sig.reason, "refs": list(sig.refs)}
    if sig.basis:
        row["basis"] = [dict(b) for b in sig.basis]
    if sig.assumes:
        row["assumes"] = [dict(a) for a in sig.assumes]
    return row


def _dedupe(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for r in rows:
        if r["signal"] not in seen:
            seen.add(r["signal"])
            out.append(r)
    return out


# Sentences for the UNIVERSAL reason codes for zero paths (machine language + UI language). Codes carry no
# domain identity; domain-specific reasons come from the signal reader (`Signal.reason` / `Signal.i18n`).
UNRESOLVED_TEXT: dict[str, dict[str, str]] = {
    "EMPTY_POSSIBILITY_SPACE": {
        "id": "domain ini belum mendeklarasikan strategi apa pun",
        "en": "This domain has no supported ways forward declared yet.",
    },
    "INSUFFICIENT_VERIFIED_STATE": {
        "id": "keadaan terverifikasi belum cukup untuk membentuk hipotesis path",
        "en": "We do not yet know enough about your situation to name a way forward with confidence.",
    },
    "NO_SUPPORTED_STRATEGY": {
        "id": "tidak ada strategi yang didukung keadaan terverifikasi saat ini",
        "en": "Nothing we know about your situation points to a way forward we can support right now.",
    },
    "ALL_CANDIDATES_NOT_APPLICABLE": {
        "id": "kandidat muncul tetapi semuanya tidak berlaku untuk situasi ini",
        "en": "Some ways forward came up, but none of them fits your situation.",
    },
}


def _reason_row(code: str, **extra: Any) -> dict:
    txt = UNRESOLVED_TEXT[code]
    i18n = {k: {"detail": v} for k, v in txt.items() if k != "id"}
    return {"code": code, "detail": txt["id"], "i18n": i18n, **extra}


def _signal_detail(sid: str, sig: Signal) -> dict:
    return {"signal": sid, "reason": sig.reason, "i18n": {k: {"reason": v} for k, v in sig.i18n.items()}}


def generate_candidates(space: PossibilitySpace, reader: SignalReader) -> CandidateSet:
    reader = grounded(reader)  # PROV-02: TRUE knowledge signals without a basis never become support
    reader = with_mechanisms(space, reader)  # knowledge -> derived mechanisms (no-op without MechanismSpec)
    out = CandidateSet(space_id=space.space_id, considered=len(space.strategies) + len(space.patterns))
    if not space.strategies and not space.patterns:
        out.blockers.append(_reason_row("EMPTY_POSSIBILITY_SPACE"))
        return out

    goal_support: list[dict] = []
    if space.goal_signal:
        goal = reader(space.goal_signal)
        if goal.value is not True:
            out.blockers.append(
                {
                    "code": "GOAL_NOT_ESTABLISHED" if goal.value is None else "GOAL_ABSENT",
                    "detail": goal.reason or f"sinyal tujuan {space.goal_signal!r} belum terbukti",
                    "i18n": {k: {"detail": v} for k, v in goal.i18n.items()},
                    "signal": space.goal_signal,
                }
            )
            return out
        goal_support = [_support_row(space.goal_signal, goal)]

    noted: set[str] = set()
    overlay = overlay_of(reader)
    if overlay is not None:
        for row in overlay.unsupported():
            noted.add(row["signal"])
            out.unsupported.append(row)
        out.mechanisms = [a.audit() for a in overlay.activations()]
    out.possibilities = generate_possibilities(space, reader, goal_support)
    for cp in out.possibilities:
        for sid in cp.missing:
            sig = reader(sid)
            if sig.unsupported and sid not in noted:
                noted.add(sid)
                out.unsupported.append({"signal": sid, "reason": sig.reason})
        if cp.status == UNDETERMINED:
            out.undetermined.append(
                {
                    "strategy_id": cp.direction,
                    "candidate_id": cp.candidate_id,
                    "missing": list(cp.missing),
                    "missing_detail": list(cp.missing_detail),
                }
            )
        elif cp.status == NOT_EMERGENT:
            out.not_emergent.append({"strategy_id": cp.direction, "candidate_id": cp.candidate_id})
    for strat in space.strategies:
        ev = evaluate(strat.emerges_when, reader)
        for sid in dict.fromkeys(ev.seen):
            sig = reader(sid)
            if sig.unsupported and sid not in noted:
                noted.add(sid)
                out.unsupported.append({"signal": sid, "reason": sig.reason})
        if ev.value is True:
            support = _dedupe(goal_support + [_support_row(sid, sig) for sid, sig in ev.support])
            out.candidates.append(Candidate(strat, support))
        elif ev.value is False:
            out.not_emergent.append({"strategy_id": strat.strategy_id})
        else:
            missing = [sid for sid in dict.fromkeys(ev.seen) if reader(sid).value is None]
            missing = missing or signal_ids(strat.emerges_when)
            out.undetermined.append(
                {
                    "strategy_id": strat.strategy_id,
                    "missing": missing,
                    "missing_detail": [_signal_detail(sid, reader(sid)) for sid in missing],
                }
            )
    return out


def unresolved_reasons(cset: CandidateSet) -> list[dict]:
    """Why zero candidates — only when there really are none. Codes derive from the generator's records,
    never invented."""
    if cset.candidates:
        return []
    if cset.blockers:
        return list(cset.blockers)
    reasons = []
    if cset.undetermined:
        detail: dict[str, dict] = {}
        for u in cset.undetermined:
            for d in u["missing_detail"]:
                detail.setdefault(d["signal"], d)
        reasons.append(
            _reason_row(
                "INSUFFICIENT_VERIFIED_STATE",
                missing=sorted(detail),
                missing_detail=[detail[k] for k in sorted(detail)],
            )
        )
    if cset.not_emergent:
        reasons.append(_reason_row("NO_SUPPORTED_STRATEGY"))
    return reasons


def split_support(support: list[dict]) -> dict[str, Any]:
    """Support -> provenance columns by signal namespace (state / mechanism / rule) + evidence references.

    Transcript quote references (`transcript:"..."`) are not evidence ids: they land in
    `transcript_anchors`. A `rule:` signal also yields `knowledge_support` — which rule, which evidence or
    quotes, which predicate branch, and which absence conditions are relied on (`assumed_absences`:
    absence of record, not an anchor)."""
    cols: dict[str, Any] = {
        "state_claims": [],
        "mechanism_ids": [],
        "knowledge_ids": [],
        "evidence_ids": [],
        "transcript_anchors": [],
    }
    knowledge_support: list[dict] = []
    for row in support:
        kind, _, name = row["signal"].partition(":")
        if kind == SIGNAL_STATE:
            cols["state_claims"].append(row["signal"])
        elif kind == SIGNAL_MECHANISM:
            cols["mechanism_ids"].append(name)
        elif kind == SIGNAL_RULE:
            cols["knowledge_ids"].append(name)
        ev = [r for r in row["refs"] if not r.startswith(TRANSCRIPT_PREFIX)]
        tr = [r for r in row["refs"] if r.startswith(TRANSCRIPT_PREFIX)]
        cols["evidence_ids"].extend(ev)
        cols["transcript_anchors"].extend(tr)
        if kind == SIGNAL_RULE:
            knowledge_support.append(
                {
                    "rule_id": name,
                    "evidence_ids": list(dict.fromkeys(ev)),
                    "transcript_anchors": list(dict.fromkeys(tr)),
                    "branches": [dict(b) for b in row.get("basis", [])],
                    "assumed_absences": [dict(a) for a in row.get("assumes", [])],
                }
            )
    out: dict[str, Any] = {k: list(dict.fromkeys(v)) for k, v in cols.items()}
    out["knowledge_support"] = knowledge_support
    out["assumed_absences"] = assumed_absences(support)
    return out
