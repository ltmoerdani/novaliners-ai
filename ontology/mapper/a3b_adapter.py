"""A3b runtime adapter — moves the SPECIFICATION (previously locked in
ontology/adjudication/test_adjudication_path.py::_aggregate_a3b) into a runtime
module. Unit-unknown policy LOCK 27 Sep (int 09 §8.4 A3b):

    all known & satisfied                 -> sufficient
    >=1 satisfied & >=1 known failed      -> partial (proven on both sides;
                                              remaining unknown does not negate)
    all known & all failed                -> contradicting
    otherwise (some unknown, without
    two-sided proof)                      -> no_decisive
    empty set                             -> no_decisive (generic;
                                              per-entry via rule)

The mapper ONLY produces evidence→requirement→unit; the T/F/None outcome per
unit = result of evaluating the rule per unit evidence subset (deterministic by the
caller), and A3b produces the RULE EVALUATION (4-bool) — the adjudicator
remains the ONE AND ONLY status authority (LOCK).
"""
from __future__ import annotations

UnitStatus = bool | None  # True/False known; None = not yet known


def aggregate_a3b(units: list[UnitStatus]) -> dict[str, bool]:
    """Aggregation specification (identical to the locked test — drift is locked by test)."""
    known = [u for u in units if u is not None]
    ok = [u for u in known if u is True]
    fail = [u for u in known if u is False]
    if not known:                       # empty / all unknown
        return {"sufficient": False, "partial": False,
                "no_decisive": True, "contradicting": False}
    if len(ok) == len(units):           # all known & satisfied
        return {"sufficient": True, "partial": False,
                "no_decisive": False, "contradicting": False}
    if ok and fail:                     # PARTIAL proven on both sides
        return {"sufficient": False, "partial": True,
                "no_decisive": False, "contradicting": False}
    if fail and len(fail) == len(units):    # all known, ZERO satisfied
        return {"sufficient": False, "partial": False,
                "no_decisive": False, "contradicting": True}
    return {"sufficient": False, "partial": False,   # some unknown still present
            "no_decisive": True, "contradicting": False}


def unit_outcomes(rule: dict, unit_evidence: dict[str, list]) -> dict[str, str]:
    """Outcome per unit — DETERMINISTIC (evaluate_predicate per subset) with
    the CONFLICT CONTRACT (review 282cd29): SATISFIED (S-match) · FAILED
    (C-match without S) · UNKNOWN (no match) · CONFLICT (S-match AND
    C-match — D-A1a: BOTH sides preserved, NOT prioritized;
    CONFLICT units are FORBIDDEN from entering A3b — fallback to the authoritative
    requirement-level adjudication path)."""
    from core.stages.rule_predicates import evaluate_predicate  # noqa: E402
    out: dict[str, str] = {}
    for unit_key, evs in unit_evidence.items():
        s, _c1, _r1 = evaluate_predicate(rule["sufficient"], evs, negation_aware=True)
        c, _c2, _r2 = evaluate_predicate(rule["contradicting"], evs, negation_aware=True)
        if s and c:
            out[unit_key] = "CONFLICT"
        elif s:
            out[unit_key] = "SATISFIED"
        elif c:
            out[unit_key] = "FAILED"
        else:
            out[unit_key] = "UNKNOWN"
    return out


_OUTCOME_MAP = {"SATISFIED": True, "FAILED": False, "UNKNOWN": None}


def build_precomputed(unit_outcomes: dict) -> tuple[dict[str, bool] | None, list[str]]:
    """unit outcomes -> (precomputed 4-bool, conflict_units). CONFLICT units
    are excluded from A3b and reported — the caller MUST fall back to
    adjudicate() WITHOUT precomputed (requirement-level conflict path,
    D-A1a). Also accepts bool/None (legacy direct-input, fixture T5)."""
    conflicts = sorted(k for k, v in unit_outcomes.items()
                       if v == "CONFLICT")
    if conflicts:
        # GUARD (review a602666 #7): precomputed MUST NOT be used by a careless
        # caller when a conflict unit exists -> None forces fallback to
        # normal adjudicate (D-A1a requirement-level)
        return None, conflicts
    vals = [(_OUTCOME_MAP[v] if isinstance(v, str) else v)
            for k, v in unit_outcomes.items()]
    return aggregate_a3b(vals), conflicts
