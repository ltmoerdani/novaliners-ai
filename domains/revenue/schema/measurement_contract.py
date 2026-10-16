"""Goal measurement contract — ONE source of validity for both the attainment evaluator and trajectory.

Five different things that must not be collapsed into one boolean (mandate round 4 §2.2):

  1. the measured value        — e.g. rate = numerator / denominator
  2. measurement validity      — whether the evidence is well-defined (denominator > 0, same cohort, ...)
  3. fit with the Goal         — the cohort/period measured = the one the Goal states
  4. target attainment         — a valid value vs the target (goal_evaluation)
  5. trajectory direction      — two comparable observations (trajectory)

This module answers (2) and (3) for RATE_OR_RATIO; (4) stays in `goal_evaluation`, (5) in
`stages/trajectory`. Both call `rate_measurement_validity`, so a measurement rejected for
attainment is also rejected for trajectory — they cannot contradict each other through
different data definitions.

Pure functions, 0 LLM, no I/O.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

from ontology.registry import metrics as metric_registry

# ── reason codes (stable; used by API, UI, and tests) ──────────────────────────────────
RATE_INCOMPLETE = "RATE_INCOMPLETE"                  # numerator/denominator missing
RATE_DENOMINATOR_ZERO = "RATE_DENOMINATOR_ZERO"      # denominator 0 → rate undefined
RATE_NEGATIVE = "RATE_NEGATIVE"                      # negative numerator/denominator
RATE_NUMERATOR_EXCEEDS = "RATE_NUMERATOR_EXCEEDS_DENOMINATOR"  # part-of-whole: n > d = not the same cohort
RATE_COHORT_MISSING = "RATE_COHORT_MISSING"          # cohort not stated → fit unproven
RATE_PERIOD_MISSING = "RATE_PERIOD_MISSING"          # period not stated → fit unproven
RATE_COHORT_MISMATCH = "RATE_COHORT_MISMATCH"        # cohort ≠ the Goal's stated scope
RATE_PERIOD_INVALID = "RATE_PERIOD_INVALID"          # reversed bounds / future / label mismatch
RATE_PERIOD_UNVERIFIABLE = "RATE_PERIOD_UNVERIFIABLE"  # label present, exact interval not establishable
RATE_PERIOD_MISMATCH = "RATE_PERIOD_MISMATCH"        # period length ≠ the Goal's window

KIND_MISMATCH = "MEASUREMENT_KIND_MISMATCH"
KIND_SEMANTICS_UNKNOWN = "GOAL_SEMANTICS_UNKNOWN"

DAY = 86400
# Period-length tolerance vs the Goal's window: cohorts are cut per calendar day.
_PERIOD_TOLERANCE_DAYS = 1.0

# Goal semantics → valid measurement kinds (registry-driven, not metric names)
_KINDS_BY_SEMANTICS: dict[str, tuple[str, ...]] = {
    metric_registry.SEMANTICS_COUNT_IN_WINDOW: ("event",),
    metric_registry.SEMANTICS_RATE_OR_RATIO: ("rate",),
    metric_registry.SEMANTICS_EVIDENCE_CRITERIA: ("criteria",),
    metric_registry.SEMANTICS_INCREASE_TO_THRESHOLD: ("value",),
    metric_registry.SEMANTICS_DECREASE_TO_THRESHOLD: ("value",),
    metric_registry.SEMANTICS_MAINTAIN_RANGE: ("value",),
    metric_registry.SEMANTICS_AT_LEAST: ("value",),
    metric_registry.SEMANTICS_AT_MOST: ("value",),
}


# ── semantics & kind ────────────────────────────────────────────────────────────────

def goal_metric_id(goal: dict | None) -> str:
    g = goal or {}
    return g.get("metric_id") or ("revenue_monthly" if g.get("metric") == "revenue_monthly" else "")


def goal_semantics(goal: dict | None) -> str:
    """Goal semantics: an explicit `direction`, or the registry semantics for its metric.
    Legacy `metric=revenue_monthly` without metric_id/direction = registry revenue_monthly (GR-07)."""
    g = goal or {}
    if g.get("direction"):
        return str(g["direction"])
    mdef = metric_registry.metric_by_id(goal_metric_id(g))
    return str((mdef or {}).get("semantics") or "")


def allowed_kinds(goal: dict | None) -> tuple[str, ...]:
    return _KINDS_BY_SEMANTICS.get(goal_semantics(goal), ())


def kind_check(goal: dict | None, kind: str) -> dict[str, Any]:
    """Does the measurement `kind` fit the Goal's semantics? {ok, code, reason, expected, semantics}.

    A Goal with unknown semantics accepts NO kind: there is no basis for declaring a valid
    evidence shape (unknown ≠ anything goes)."""
    sem = goal_semantics(goal)
    expected = _KINDS_BY_SEMANTICS.get(sem, ())
    if not expected:
        return {"ok": False, "code": KIND_SEMANTICS_UNKNOWN, "semantics": sem, "expected": [],
                "reason": ("semantics Goal belum teridentifikasi registry - bentuk measurement "
                           "yang sah tidak dapat ditentukan")}
    if kind in expected:
        return {"ok": True, "code": "", "semantics": sem, "expected": list(expected), "reason": ""}
    return {"ok": False, "code": KIND_MISMATCH, "semantics": sem, "expected": list(expected),
            "reason": (f"measurement kind={kind!r} tidak cocok dengan semantics Goal {sem} "
                       f"(kind yang sah: {', '.join(expected)})")}


# ── RATE_OR_RATIO ──────────────────────────────────────────────────────────────────

# Canonical period labels that may be normalized into an exact interval. Only these two shapes
# have a single definition; other labels ("last quarter", "Q3", "2026-H2", ...) are NOT guessed -
# they need explicit period_start_ts + period_end_ts. All in UTC, interval [start, end) (end EXCLUSIVE).
_QUARTER_RE = re.compile(r"^(\d{4})-Q([1-4])$", re.IGNORECASE)
_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _utc_ts(year: int, month: int) -> int:
    if month > 12:
        year, month = year + 1, month - 12
    return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())


def normalize_period_label(label: Any) -> tuple[int, int] | None:
    """Canonical labels (`YYYY-Qn`, `YYYY-MM`) -> (start_ts, exclusive end_ts) in UTC; otherwise None."""
    text = str(label or "").strip()
    q = _QUARTER_RE.match(text)
    if q:
        y, n = int(q.group(1)), int(q.group(2))
        return _utc_ts(y, 3 * (n - 1) + 1), _utc_ts(y, 3 * n + 1)
    m = _MONTH_RE.match(text)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return _utc_ts(y, mo), _utc_ts(y, mo + 1)
    return None


def _norm(s: Any) -> str:
    return " ".join(str(s or "").split()).casefold()


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _is_part_of_whole(goal: dict | None) -> bool:
    """A 'ratio' metric (won/opportunities, etc.) is a share of the cohort: numerator ⊆ denominator."""
    mdef = metric_registry.metric_by_id(goal_metric_id(goal))
    unit = (mdef or {}).get("unit") or (goal or {}).get("unit")
    return unit == "ratio"


def rate_measurement_validity(
    goal: dict | None, m: dict, *, as_of_ts: int | None = None,
) -> dict[str, Any]:
    """Validity of one `kind=rate` measurement against the Goal.

    Returns: {valid, rate, codes[], reasons[], cohort, period}. `valid=True` means the rate is
    defined AND proven to come from the stated cohort/period — only that may ground
    `ACHIEVED/NOT_ACHIEVED` or a trajectory series point. A missing cohort/period is NOT
    silently treated as a match (unknown ≠ fit). The period MUST be an exact interval:
    explicit `period_start_ts` + `period_end_ts`, or a normalized canonical label
    (`YYYY-Qn`, `YYYY-MM`, UTC, exclusive end). Any other label without bounds =
    RATE_PERIOD_UNVERIFIABLE (unproven, not guessed). The interval is then compared against the
    Goal's `measurement_window_days` (1-day tolerance: cohorts are cut per calendar day) and must
    not end after the evaluation time."""
    g = goal or {}
    codes: list[str] = []
    reasons: list[str] = []

    def bad(code: str, why: str) -> None:
        codes.append(code)
        reasons.append(why)

    n, d = _num(m.get("numerator")), _num(m.get("denominator"))
    rate: float | None = None
    if n is None or d is None:
        bad(RATE_INCOMPLETE, "numerator/denominator belum lengkap - rate tidak terdefinisi")
    elif d == 0:
        bad(RATE_DENOMINATOR_ZERO, "denominator = 0 - rate tidak terdefinisi (NOT_COMPUTABLE, bukan 0%)")
    elif n < 0 or d < 0:
        bad(RATE_NEGATIVE, "numerator/denominator negatif - bukan hitungan kohort yang sah")
    else:
        rate = round(n / d, 4)
        if _is_part_of_whole(g) and n > d:
            bad(RATE_NUMERATOR_EXCEEDS,
                "numerator melebihi denominator pada metric rasio-bagian - tidak berasal dari "
                "kohort yang sama")
            rate = None

    cohort = str(m.get("cohort") or "").strip()
    period = str(m.get("period") or "").strip()
    if not cohort:
        bad(RATE_COHORT_MISSING, "kohort pengukuran tidak dinyatakan - kesesuaian dengan Goal tidak terbukti")
    elif g.get("scope") and _norm(cohort) != _norm(g["scope"]):
        bad(RATE_COHORT_MISMATCH,
            f"kohort {cohort!r} berbeda dari scope Goal {g['scope']!r}")
    if not period:
        bad(RATE_PERIOD_MISSING,
            "periode pengukuran tidak dinyatakan - kesesuaian dengan Goal tidak terbukti")

    # The period must be VERIFIED into an exact interval: explicit bounds, or a normalized
    # canonical label. A label alone (a non-empty string) is not proof of the period length.
    p0, p1 = _num(m.get("period_start_ts")), _num(m.get("period_end_ts"))
    from_label = normalize_period_label(period) if period else None
    interval: tuple[float, float] | None = None
    source = ""
    if (p0 is None) != (p1 is None):
        bad(RATE_PERIOD_INVALID, "batas periode tidak lengkap (butuh period_start_ts DAN period_end_ts)")
    elif p0 is not None and p1 is not None:
        interval, source = (p0, p1), "explicit"
        if from_label and (abs(p0 - from_label[0]) > DAY * _PERIOD_TOLERANCE_DAYS
                           or abs(p1 - from_label[1]) > DAY * _PERIOD_TOLERANCE_DAYS):
            bad(RATE_PERIOD_INVALID, f"batas periode tidak sesuai label {period!r}")
    elif from_label:
        interval, source = (float(from_label[0]), float(from_label[1])), "label"
    elif period:
        bad(RATE_PERIOD_UNVERIFIABLE,
            f"periode {period!r} tidak dapat ditetapkan menjadi interval eksak - sertakan "
            "period_start_ts dan period_end_ts, atau label YYYY-Qn / YYYY-MM")

    window_checked = False
    if interval is not None:
        b0, b1 = interval
        if b1 <= b0:
            bad(RATE_PERIOD_INVALID, "akhir periode tidak setelah awal periode (interval kosong)")
            interval = None
        else:
            now = int(as_of_ts) if as_of_ts is not None else int(time.time())
            if b1 > now:
                bad(RATE_PERIOD_INVALID, "periode berakhir setelah waktu evaluasi - belum bisa menjadi bukti")
            window = g.get("measurement_window_days")
            if window:
                window_checked = True
                if abs((b1 - b0) / DAY - float(window)) > _PERIOD_TOLERANCE_DAYS:
                    bad(RATE_PERIOD_MISMATCH,
                        f"panjang periode {(b1 - b0) / DAY:g} hari berbeda dari window Goal {window} hari")

    iv = ({"start_ts": int(interval[0]), "end_ts": int(interval[1]), "source": source,
           "window_checked": window_checked} if interval is not None else None)
    return {"valid": not codes, "rate": rate if not codes else None, "codes": codes,
            "reasons": reasons, "cohort": cohort, "period": period, "interval": iv}


def partition_rate_measurements(
    goal: dict | None, ms: list[dict], *, as_of_ts: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """(valid, rejected) for kind=rate measurements, original order preserved.

    valid   : [{**measurement, "rate", "cohort", "period"}]
    rejected: [{"ts", "codes", "reasons"}] — still stored in the store; just not used
              as attainment/trajectory input."""
    valid: list[dict] = []
    rejected: list[dict] = []
    for m in ms:
        if m.get("kind") != "rate":
            continue
        v = rate_measurement_validity(goal, m, as_of_ts=as_of_ts)
        if v["valid"]:
            valid.append({**m, "rate": v["rate"], "cohort": v["cohort"], "period": v["period"],
                          "interval": v["interval"]})
        else:
            rejected.append({"ts": m.get("ts"), "codes": v["codes"], "reasons": v["reasons"]})
    return valid, rejected


# ── COUNT_IN_WINDOW: event time ≠ record time ≠ observation time ≠ as_of ───────────
#
# Four clocks that must not be mixed (mandate round 4 §3.2):
#   event_ts   - when the business event happened (the `event_ts` field; NO fallback to `ts`)
#   recorded   - when the system received the evidence (the `ts` field on a GOAL_MEASURED row = record time)
#   observation- the recorded time of an event measurement used as a historical measurement point
#   as_of      - the evaluation time of current
# A count at time t only uses evidence ALREADY RECORDED at t (recorded <= t): evidence reported
# after t does not rewrite what the system knew at t.

def events_known_at(ms: list[dict], t: int, *, historical: bool = False) -> list[dict]:
    """Event measurements already recorded at `t`, shaped {ts, qualified, recorded_ts, event_id}.

    ts = EVENT time. Rows sharing the same `event_id` are versions of the same event: at time t the
    applicable one is the LATEST recorded version with recorded <= t (qualification corrections
    apply forward only, never retroactively). Rows without an event_id stand alone.
    A missing recording time = not proven known at t: excluded from historical counts
    (`historical=True`), included for current counts."""
    latest: dict[str, dict] = {}
    anon: list[dict] = []
    ordered = sorted(
        (m for m in ms if isinstance(m, dict) and m.get("kind") == "event"),
        key=lambda m: (m.get("ts") is None, m.get("ts") or 0))
    for m in ordered:
        rts = m.get("ts")
        if rts is None:
            if historical:
                continue
        elif int(rts) > int(t):
            continue
        row = {"ts": m.get("event_ts"), "qualified": m.get("qualified"),
               "recorded_ts": int(rts) if rts is not None else None,
               "event_id": str(m.get("event_id") or "").strip()}
        if row["event_id"]:
            latest[row["event_id"]] = row
        else:
            anon.append(row)
    return anon + list(latest.values())


def observation_points(ms: list[dict], as_of_ts: int) -> list[int]:
    """Observation points = the RECORDING time of kind=event measurements (no other kind, not event
    time), never past as_of. The system only 'observes' the Goal's count when it receives count
    evidence."""
    return sorted({int(m["ts"]) for m in ms
                   if isinstance(m, dict) and m.get("kind") == "event"
                   and m.get("ts") is not None and int(m["ts"]) <= int(as_of_ts)})


def count_events_in_window(events: list[dict], window_days: int | float, as_of_ts: int) -> dict[str, Any]:
    """Count qualified events within the window at `as_of_ts` - one implementation shared by attainment
    (goal_evaluation) and trajectory. The lower bound (as_of - window) is INCLUSIVE; events after
    as_of are not counted; unknown ts/qualification = unknown, not 0 and not auto-qualified."""
    cutoff = int(as_of_ts) - int(window_days * DAY)
    counted = unknown_ts = unknown_qual = future = outside = 0
    for e in events:
        ts = e.get("ts")
        if ts is None:
            unknown_ts += 1
            continue
        ts = int(ts)
        if ts > int(as_of_ts):
            future += 1
            continue
        if ts < cutoff:
            outside += 1
            continue
        q = e.get("qualified")
        if q is None:
            unknown_qual += 1
        elif q:
            counted += 1
    return {"counted": counted, "unknown_timestamp": unknown_ts, "unknown_qualification": unknown_qual,
            "future_events": future, "outside_window": outside,
            "window_start_ts": cutoff, "as_of_ts": int(as_of_ts)}


# ── comparability: the meaning of evidence, not just IDs ──────────────────────────────
#
# Dimensions that CHANGE THE MEANING of raw evidence (a difference = the old evidence no longer
# measures the same thing):
#   metric_id, metric_version, direction (semantics), unit, scope (population), success_definition
#   (the qualification / criteria / numerator-denominator definition).
# Dimensions that are only EVALUATION parameters (a difference = the evidence stays valid, just
# re-evaluated):
#   target, target_min/max, deadline, baseline, measurement_window_days.
#   The count window is recomputed from raw events; the rate period is checked against the Goal's
#   window at evaluation time (rate_measurement_validity), so window is not a comparability key.
#
# Metric versions: records without metric_version (pre-versioning) read as version 1 - the registry
# started at v1 before the field existed. Once the registry passes v1, legacy records are not proven
# to follow the new definition and are excluded from current evaluation (kept intact for historical
# evaluation).
MATERIAL_DIMENSIONS = ("metric_id", "metric_version", "direction", "unit", "scope", "success_definition")


def effective_metric_version(goal: dict | None) -> int:
    v = (goal or {}).get("metric_version")
    try:
        return int(v) if v else 1
    except (TypeError, ValueError):
        return 1


def semantic_signature(goal: dict | None) -> dict[str, Any]:
    """The Goal's semantic identity determining its measurement meaning (values normalized)."""
    g = goal or {}
    return {
        "metric_id": goal_metric_id(g),
        "metric_version": effective_metric_version(g),
        "direction": goal_semantics(g),
        "unit": _norm(g.get("unit")),
        "scope": _norm(g.get("scope")),
        "success_definition": _norm(g.get("success_definition")),
    }


def comparability(recorded: dict | None, now: dict | None) -> dict[str, Any]:
    """Does a measurement recorded under the `recorded` Goal still measure the same thing as the
    `now` Goal? {comparable, differences:[{dimension, then, now}], basis}.

    `recorded=None` (no Goal snapshot at recording time - legacy data) is considered comparable with
    basis 'no_snapshot': there is no basis to claim otherwise, and that is reported."""
    if not recorded:
        return {"comparable": True, "differences": [], "basis": "no_snapshot"}
    a, b = semantic_signature(recorded), semantic_signature(now)
    # dimensions missing from the old snapshot = unknown, not "different"
    skip = {k for k in ("unit", "scope", "success_definition") if k not in recorded}
    diffs = [{"dimension": k, "then": a[k], "now": b[k]}
             for k in MATERIAL_DIMENSIONS if k not in skip and a[k] != b[k]]
    return {"comparable": not diffs, "differences": diffs, "basis": "snapshot"}


def material_change(before: dict | None, after: dict | None) -> list[str]:
    """Material dimensions that changed between two Goal states (the GOAL_REVISED basis for
    definitions)."""
    a, b = semantic_signature(before), semantic_signature(after)
    return [k for k in MATERIAL_DIMENSIONS if a[k] != b[k]]
