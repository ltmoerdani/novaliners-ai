"""Typed goal evaluation — evaluator per registry semantics (int 09 §3.2).

`goal_gap = target − current` is ONLY an INCREASE_TO_THRESHOLD projection; here evaluation
follows the metric's direction/aggregation:

    INCREASE_TO_THRESHOLD  success: current ≥ target
    DECREASE_TO_THRESHOLD  success: current ≤ target (the generic gap would INVERT the meaning — GR-03)
    MAINTAIN_RANGE         success: target_min ≤ current ≤ target_max
    AT_LEAST / AT_MOST     compare per the metric's direction
    COUNT_IN_WINDOW        count ONLY events inside the window that meet qualification;
                           missing timestamp/qualification = UNKNOWN, not 0 (GR-09)
    RATE_OR_RATIO          needs a comparable-cohort numerator/denominator AND a cohort/period
                           proven to match the Goal (measurement_contract); a percentage without
                           context or scope = NOT_COMPUTABLE (GR-02)
    EVIDENCE_CRITERIA      success from explicit evidence criteria; no numeric score invented (GR-11)

Truths: missing ≠ zero; unknown ≠ absent; NOT_COMPUTABLE is neither failure nor success —
the system picks a clarification/measurement step or explains the gap (int 09 §3.2, last line).
"""
from __future__ import annotations

import time
from typing import Any, Optional

from domains.revenue.schema.goal import (
    UNRESOLVED_ACTIVITY,
    UNRESOLVED_DENOMINATOR,
    UNRESOLVED_METRIC,
    UNRESOLVED_QUALIFICATION,
    UNRESOLVED_TARGET,
    UNRESOLVED_WINDOW,
    Goal,
    _unresolved,
)
from domains.revenue.schema.measurement_contract import (
    count_events_in_window,
    rate_measurement_validity,
)
from ontology.registry.metrics import registry_version as _registry_version

ACHIEVED = "ACHIEVED"
NOT_ACHIEVED = "NOT_ACHIEVED"
NOT_COMPUTABLE = "NOT_COMPUTABLE"

_EPS = 1e-9


def evaluate_goal(
    goal: Goal,
    *,
    current: Optional[float] = None,
    events: Optional[list[dict]] = None,
    numerator: Optional[float] = None,
    denominator: Optional[float] = None,
    criteria_results: Optional[list[dict]] = None,
    as_of_ts: Optional[int] = None,
    rate_scope: Optional[dict] = None,
) -> dict[str, Any]:
    """Evaluate a typed Goal → {status, semantics, reasons[], values}.

    An explicit `current` wins over `goal.current` (the latest measured value). `events` =
    [{ts: epoch|None, qualified: bool|None, value?}] for COUNT_IN_WINDOW; events without
    `ts`/qualification are NOT counted and NOT treated as 0 — recorded as unknown (GR-09).

    `as_of_ts` = explicit evaluation time (epoch seconds) for COUNT_IN_WINDOW — A-09:
    the window is measured from the EVALUATION TIME, not the latest event timestamp (baseline bug:
    three events 30 days ago looked "within the 14-day window" because they anchored to the newest
    event). None → wall clock; deterministic fixtures must inject a fixed value. Boundary: an event
    exactly at the cutoff (as_of − window) IS inside the window (inclusive); events timestamped
    after as_of (future) do not raise the observed count.

    `rate_scope` = {cohort, period, period_start_ts?, period_end_ts?} for a RATE_OR_RATIO
    measurement. Without a scope proven to match the Goal (measurement_contract),
    numerator/denominator are NOT evaluated against the target - a number that happens to exceed
    the target is not attainment."""
    mdef = goal.metric_definition()
    sem = goal.direction or (mdef or {}).get("semantics", "")
    out: dict[str, Any] = {"semantics": sem, "metric_id": goal.resolved_metric_id(),
                         "reasons": [], "values": {}}
    if not goal.resolved_metric_id() or not sem:
        return {**out, "status": NOT_COMPUTABLE,
                "reasons": ["metric Goal belum teridentifikasi registry — evaluasi tidak mungkin"]}

    val = current if current is not None else goal.current

    def _need(what: str) -> dict[str, Any]:
        return {**out, "status": NOT_COMPUTABLE,
                "reasons": [f"{what} belum diketahui — bukan nol, bukan gagal"]}

    if sem == "INCREASE_TO_THRESHOLD" or sem == "AT_LEAST":
        if goal.target is None:
            return {**out, "status": NOT_COMPUTABLE, "reasons": ["target belum ditetapkan"]}
        if val is None:
            return _need("nilai current")
        out["values"] = {"current": val, "target": goal.target}
        return {**out, "status": ACHIEVED if val >= goal.target - _EPS else NOT_ACHIEVED}

    if sem == "DECREASE_TO_THRESHOLD" or sem == "AT_MOST":
        threshold = goal.target if goal.target is not None else goal.target_max
        if threshold is None:
            return {**out, "status": NOT_COMPUTABLE, "reasons": ["threshold atas belum ditetapkan"]}
        if val is None:
            return _need("nilai current")
        out["values"] = {"current": val, "threshold": threshold}
        # GR-03: success = current ≤ threshold — NOT the generic target−current
        return {**out, "status": ACHIEVED if val <= threshold + _EPS else NOT_ACHIEVED}

    if sem == "MAINTAIN_RANGE":
        if goal.target_min is None or goal.target_max is None:
            return {**out, "status": NOT_COMPUTABLE,
                "reasons": ["batas range (target_min/target_max) belum lengkap"]}
        if val is None:
            return _need("nilai current")
        out["values"] = {"current": val, "range": [goal.target_min, goal.target_max]}
        ok = goal.target_min - _EPS <= val <= goal.target_max + _EPS
        return {**out, "status": ACHIEVED if ok else NOT_ACHIEVED}

    if sem == "COUNT_IN_WINDOW":
        return _count_in_window(goal, mdef or {}, events or [], as_of_ts=as_of_ts)

    if sem == "RATE_OR_RATIO":
        return _rate_or_ratio(goal, numerator, denominator, rate_scope, as_of_ts)

    if sem == "EVIDENCE_CRITERIA":
        return _evidence_criteria(goal, criteria_results)

    return {**out, "status": NOT_COMPUTABLE, "reasons": [f"semantics {sem!r} tidak dikenal evaluator"]}


def _count_in_window(goal: Goal, mdef: dict, events: list[dict],
                     *, as_of_ts: Optional[int] = None) -> dict[str, Any]:
    base = {"semantics": "COUNT_IN_WINDOW", "metric_id": goal.resolved_metric_id(),
            "reasons": [], "values": {}}
    window = goal.measurement_window_days
    if window is None:
        return {**base, "status": NOT_COMPUTABLE,
                "reasons": ["window pengukuran belum ditetapkan — event tidak bisa difilter (GR-09)"]}
    if goal.target is None:
        return {**base, "status": NOT_COMPUTABLE, "reasons": ["target jumlah event belum ditetapkan"]}
    if not events:
        return {**base, "status": NOT_COMPUTABLE,
                "reasons": ["belum ada event teramati — kosong ≠ nol terverifikasi"]}
    # A-09: the evaluation clock = explicit as_of (or wall clock), NOT the latest event timestamp.
    # The count shares one implementation with trajectory (measurement_contract.count_events_in_window).
    as_of = int(as_of_ts) if as_of_ts is not None else int(time.time())
    c = count_events_in_window(events, window, as_of)
    counted, unknown_ts, unknown_qual = c["counted"], c["unknown_timestamp"], c["unknown_qualification"]
    future, outside, cutoff = c["future_events"], c["outside_window"], c["window_start_ts"]
    reasons = []
    if unknown_ts:
        reasons.append(f"{unknown_ts} event tanpa timestamp — statusnya unknown, tidak dihitung sebagai 0")
    if unknown_qual:
        reasons.append(
            f"{unknown_qual} event belum bisa dinilai kualifikasinya — unknown, bukan auto-qualified")
    if future:
        reasons.append(f"{future} event bertimestamp setelah waktu evaluasi — tidak dihitung")
    base["values"] = {"counted": counted, "target": goal.target, "window_days": window,
                      "as_of_ts": as_of, "window_start_ts": cutoff,
                      "outside_window": outside, "future_events": future,
                      "unknown_timestamp": unknown_ts, "unknown_qualification": unknown_qual}
    status = ACHIEVED if counted >= goal.target else NOT_ACHIEVED
    return {**base, "status": status, "reasons": reasons}


def _rate_or_ratio(goal: Goal, numerator: float | None, denominator: float | None,
                   rate_scope: dict | None = None, as_of_ts: int | None = None) -> dict[str, Any]:
    base = {"semantics": "RATE_OR_RATIO", "metric_id": goal.resolved_metric_id(),
            "reasons": [], "values": {}}
    if numerator is None or denominator is None:
        return {**base, "status": NOT_COMPUTABLE,
                "reasons": ["numerator/denominator (kohort) belum terukur - persentase tanpa kontext "
                            "tidak dievaluasi (GR-02)"]}
    # Validity + cohort/period fit with the Goal: the SAME contract trajectory uses.
    v = rate_measurement_validity(
        goal.model_dump(),
        {"numerator": numerator, "denominator": denominator, **(rate_scope or {})},
        as_of_ts=as_of_ts)
    if not v["valid"]:
        return {**base, "status": NOT_COMPUTABLE,
                "reasons": v["reasons"], "rejection_codes": v["codes"]}
    rate = v["rate"]
    base["values"] = {"rate": rate, "numerator": numerator, "denominator": denominator,
                      "target": goal.target, "cohort": v["cohort"], "period": v["period"]}
    if goal.target is None:
        return {**base, "status": NOT_COMPUTABLE, "reasons": ["target rate belum ditetapkan"]}
    return {**base, "status": ACHIEVED if rate >= goal.target - _EPS else NOT_ACHIEVED}


def _evidence_criteria(goal: Goal, criteria_results: list[dict] | None) -> dict[str, Any]:
    base = {"semantics": "EVIDENCE_CRITERIA", "metric_id": goal.resolved_metric_id(),
            "reasons": [], "values": {}}
    if not goal.success_definition:
        return {**base, "status": NOT_COMPUTABLE,
                "reasons": ["kriteria sukses berbasis bukti belum didefinisikan (GR-11) "
                            "— skor numerik tidak dikarang"]}
    rows = criteria_results or []
    if not rows:
        return {**base, "status": NOT_COMPUTABLE,
                "reasons": ["belum ada hasil kriteria bukti yang teramati"]}
    met = [r for r in rows if r.get("met") is True]
    unmet = [r for r in rows if r.get("met") is False]
    unknown = [r for r in rows if r.get("met") is None]
    base["values"] = {"criteria_met": len(met), "criteria_unmet": len(unmet),
                      "criteria_unknown": len(unknown), "criteria_total": len(rows)}
    if unknown or (not met and not unmet):
        return {**base, "status": NOT_COMPUTABLE,
                "reasons": ["masih ada kriteria berstatus unknown — tidak disimpulkan dua arah"]}
    return {**base, "status": ACHIEVED if (met and not unmet) else NOT_ACHIEVED}


# ───────────────────────────── guardrails (int 09 §4.5, GR-24) ─────────────────────────────

def guardrail_conflicts(goal: Goal, measured: dict[str, float] | None = None) -> list[dict]:
    """MEASURED and violated guardrails → explicit conflicts (not silent weights).

    `measured` = {metric_id: latest measured value} (from state/measurements). Guardrails without
    a measured value are reported as UNMEASURED — neither violated nor safe (GR-25: the evidence
    hierarchy stays visible). AT_LEAST: violated when the value < min; AT_MOST: value > max;
    MAINTAIN_RANGE: outside the range."""
    out: list[dict] = []
    for g in goal.guardrails or []:
        mid = g.get("metric_id", "")
        row = {"metric_id": mid, "relation": g.get("relation", "GUARDS"),
               "semantics": g.get("semantics", ""),
               "threshold": g.get("min", g.get("max")), "status": "UNMEASURED"}
        v = (measured or {}).get(mid)
        if v is not None:
            row["measured"] = v
            sem = g.get("semantics", "")
            violated = False
            if sem == "AT_LEAST" and g.get("min") is not None:
                violated = v < float(g["min"]) - _EPS
            elif sem == "AT_MOST" and g.get("max") is not None:
                violated = v > float(g["max"]) + _EPS
            elif sem == "MAINTAIN_RANGE" and g.get("min") is not None and g.get("max") is not None:
                violated = not (float(g["min"]) - _EPS <= v <= float(g["max"]) + _EPS)
            row["status"] = "VIOLATED" if violated else "HELD"
        out.append(row)
    return out


def goal_readiness(goal: Goal) -> dict[str, Any]:
    """Adjudicate Goal readiness for navigation — with reasons, NOT merely "a number exists".

    The five minimum conditions of int 09 §2.2. Conditions are RECOMPUTED from the Goal's current
    state (not copied from the unresolved entries the parser recorded at parse time — build_goal
    may complete success_definition/window afterwards; stale base entries must not lock readiness).
    The result feeds the Phase 2 Goal gate; non-blocking unknowns are returned as unresolved so the
    planner (M4) picks QUESTION/EVIDENCE_REQUEST/ACTION."""
    mdef = goal.metric_definition()
    mid = goal.resolved_metric_id()
    unresolved: list[dict] = []

    # 1. the main intent is recognized (the desire sits in the user's original text; the metric
    # may be clarified later)
    if not mid:
        unresolved.append(_unresolved(
            UNRESOLVED_METRIC, "hasil bisnis yang dimaksud belum teridentifikasi — Desire saja (GR-05)"))
    else:
        sem = goal.direction or (mdef or {}).get("semantics", "")
        # 2. outcome vs activity
        if mdef and mdef.get("role") == "activity":
            unresolved.append(_unresolved(
                UNRESOLVED_ACTIVITY,
                "metric berperan ACTIVITY — klarifikasi kuota kerja vs proxy outcome (GR-06)"))
        # 3. metric/success criteria + direction clear
        if not sem:
            unresolved.append(_unresolved(
                "DIRECTION_MISSING", f"arah sukses metric {mid} belum jelas"))
        if sem == "COUNT_IN_WINDOW":
            # 4. unit/scope/window clear, or UNKNOWN with a reason
            if goal.measurement_window_days is None:
                unresolved.append(_unresolved(
                    UNRESOLVED_WINDOW, "window pengukuran belum ditetapkan"))
            if mdef and mdef.get("requires_qualification") and not goal.success_definition:
                unresolved.append(_unresolved(
                    UNRESOLVED_QUALIFICATION, "kriteria kualifikasi belum didefinisikan (GR-04/GR-09)"))
        if sem == "RATE_OR_RATIO":
            # denominator/cohort = a measurement need → QUESTION for the planner, non-blocking
            unresolved.append(_unresolved(
                UNRESOLVED_DENOMINATOR, "denominator/kohort rate belum terukur (GR-02)"))
        if sem == "EVIDENCE_CRITERIA":
            if not goal.success_definition:
                unresolved.append(_unresolved(
                    UNRESOLVED_QUALIFICATION, "kriteria bukti belum didefinisikan (GR-11)"))
        elif goal.target is None and goal.target_min is None and goal.target_max is None:
            unresolved.append(_unresolved(
                UNRESOLVED_TARGET, "kriteria/target sukses belum ditetapkan"))

    codes = [u["code"] for u in unresolved]
    blocking = sorted(set(codes) & {
        UNRESOLVED_METRIC, UNRESOLVED_ACTIVITY, UNRESOLVED_WINDOW,
        UNRESOLVED_QUALIFICATION, UNRESOLVED_TARGET,
    })
    return {
        "ready": len(blocking) == 0,
        "reasons": sorted(set(codes)),
        "blocking": blocking,
        "unresolved": unresolved,
        "target_confirmed": goal.confirmed_target(),
        "metric_id": mid,
        "registry_version": _registry_version(),
    }
