"""P-F Trajectory & Drift (internal-docs §5.3–5.4 + roadmap P-F).

Two trajectories, NOT one — the critical §5.3 insight: revenue can be flat while
understanding improves strongly; without these two axes a legitimate learning
phase looks like failure.

1. GOAL trajectory  — is the business moving toward its target? (metric vs time)
   ON TRACK | IMPROVING | DRIFTING | OFF TRACK | INSUFFICIENT_DATA
   Deterministic: achieved pace vs required pace (linear to the deadline,
   from the P-A goal: baseline/current/target/deadline_days).

2. DECISION trajectory — is UNDERSTANDING improving? (not revenue)
   IMPROVING | STABLE | NEEDS_DATA
   Deterministic signals from the snapshot series: the count of undecided paths
   (TEST_FIRST/NOT_YET) decreasing (unknown → definitive = learning), constraint
   migration happening (old constraint tested & replaced), or a
   PATH_STATUS_CHANGED event (outcome evidence arriving). All without causal claims.

Drift taxonomy §5.4 — rerouting is NORMAL, not failure (GPS behavior):
classify the latest change from the Business State Diff:
  GOAL_DRIFT | STRATEGY_DRIFT | CONSTRAINT_SHIFT | EXECUTION_DRIFT | MARKET_DRIFT

Pure functions, 0 LLM. Honest degradation: missing data → INSUFFICIENT_DATA /
NEEDS_DATA — never fabricate a direction.
"""
from __future__ import annotations

import time
from typing import Any

from domains.revenue.schema.measurement_contract import (
    DAY,
    count_events_in_window,
    events_known_at,
    observation_points,
    partition_rate_measurements,
)

# ---------------------------------------------------------------- goal traj --

_EPS = 1e-9


def goal_trajectory(
    goal: dict | None, snapshots: list[dict], values: list[float] | None = None,
) -> dict[str, Any]:
    """Goal (P-A/Goal-Relative dict) + snapshots/measurements → business trajectory status.

    Goal-Relative (int 09 §4.4, Phase 3): a non-revenue metric is evaluated with its own
    directional semantics (DECREASE: approaching/crossing the threshold from above = improving —
    NOT the generic target−current). The value source = observed measurements (`values`, from the
    GOAL_MEASURED workspace); without measurements → INSUFFICIENT_DATA (no fabricated direction,
    GR-22: a checked-off action is not an outcome). Revenue goals (legacy & registry) still use
    the current_monthly snapshot as before."""
    mid = (goal or {}).get("metric_id") or (
        "revenue_monthly" if (goal or {}).get("metric") == "revenue_monthly" else "")
    if mid and mid != "revenue_monthly":
        return _typed_trajectory(goal or {}, [v for v in (values or []) if v is not None])
    if not goal or goal.get("target") is None or not snapshots:
        return {"status": "INSUFFICIENT_DATA",
                "reason": "goal belum punya target terukur / belum ada snapshot"}
    target = float(goal["target"])
    baseline = goal.get("baseline")
    deadline = goal.get("deadline_days")
    current = None
    for s in reversed(snapshots):  # latest MEASURED revenue value
        if s.get("current_monthly") is not None:
            current = float(s["current_monthly"])
            break
    if current is None:
        return {"status": "INSUFFICIENT_DATA", "reason": "revenue belum terukur"}

    if current >= target - _EPS:
        return {"status": "ON_TRACK", "current": current, "target": target,
                "reason": "target tercapai (current ≥ target)"}

    # Required rate vs achieved rate — only when baseline & deadline exist.
    if baseline is None or not deadline:
        return {"status": "INSUFFICIENT_DATA", "current": current, "target": target,
                "reason": "baseline/deadline belum terdefinisi — laju tak bisa dihitung"}
    span = max(target - baseline, _EPS)
    frac_needed = 1.0  # (deadline running; no goal start-ts, full-span assumption)
    frac_achieved = (current - baseline) / span
    if frac_achieved >= frac_needed:
        return {"status": "ON_TRACK", "current": current, "target": target,
                "frac_achieved": round(frac_achieved, 3)}
    if frac_achieved < 0:  # below baseline
        return {"status": "OFF_TRACK", "current": current, "baseline": baseline,
                "frac_achieved": round(frac_achieved, 3)}
    # Between baseline and target but pace not yet 100%: rising = improving, flat =
    # drifting (honest: without a start-ts we cannot distinguish any finer).
    prev = next((float(s["current_monthly"]) for s in reversed(snapshots[:-1])
                 if s.get("current_monthly") is not None), None)
    if prev is not None and current > prev:
        return {"status": "IMPROVING", "current": current, "prev": prev,
                "frac_achieved": round(frac_achieved, 3)}
    if prev is not None and current < prev:
        return {"status": "DRIFTING", "current": current, "prev": prev,
                "frac_achieved": round(frac_achieved, 3)}
    return {"status": "INSUFFICIENT_DATA", "current": current,
            "reason": "revenue datar & laju < yang dibutuhkan — butuh ts start goal"}


def typed_goal_trajectory(
    goal: dict, measurements: list[dict], *, as_of_ts: int | None = None,
) -> dict[str, Any]:
    """Goal trajectory from MEASUREMENT records per metric semantics (A-16, int 09 §3.2).

    Baseline bug (reproduced at e6c04a5): the trajectory endpoint only fed
    measurement kind="value" in as a scalar list - event, rate, and criteria
    measurements never entered the trajectory even though the Goal evaluator supports them.

    Each kind is evaluated with its own semantics:
      kind=event    -> COUNT_IN_WINDOW: count of qualified events in the sliding window at
                       observation points (A-09: explicit as_of, not the event as the clock);
      kind=rate     -> RATE_OR_RATIO: comparable numerator/denominator; an empty or zero
                       denominator = NOT_COMPUTABLE - excluded from the series but counted;
      kind=criteria -> EVIDENCE_CRITERIA: met/unmet/unknown status per criterion - NO
                       numeric score; more evidence is not an outcome trend (GR-22);
      kind=value    -> the existing scalar path (_typed_trajectory, direction per semantics).
    The decision/learning axis stays SEPARATE (decision_trajectory) - this function only
    covers Goal outcomes. Missing data -> INSUFFICIENT_DATA with a reason, not a made-up trend."""
    g = goal or {}
    direction = g.get("direction") or ""
    ms = sorted((m for m in measurements or [] if isinstance(m, dict)),
                key=lambda m: m.get("ts") or m.get("event_ts") or 0)
    base_mid = g.get("metric_id") or ("revenue_monthly" if g.get("metric") == "revenue_monthly" else "")
    if direction == "COUNT_IN_WINDOW":
        return _count_window_trajectory(g, ms, as_of_ts)
    if direction == "RATE_OR_RATIO":
        return _rate_trajectory(g, ms, as_of_ts)
    if direction == "EVIDENCE_CRITERIA":
        return _criteria_trajectory(g, ms)
    values = [float(m["value"]) for m in ms
              if m.get("kind") == "value" and m.get("value") is not None]
    if base_mid == "revenue_monthly":
        return {"status": "INSUFFICIENT_DATA",
                "reason": "trajectory revenue memakai snapshot workspace (jalur legacy)"}
    return _typed_trajectory(g, values)


def _count_window_trajectory(goal: dict, ms: list[dict], as_of_ts: int | None) -> dict[str, Any]:
    """COUNT_IN_WINDOW: four clocks kept apart (mandate round 4 §3) - event, record, observation,
    as_of.

    - event_ts  : when the business event happened (no fallback to the recording time).
    - recorded  : the measurement row's `ts` = when the system RECEIVED the evidence.
    - observasi : the recording time of a kind=event measurement (other kinds create no observation
                  point).
    - as_of     : the evaluation time of current.

    A count at time t only uses evidence ALREADY recorded at t (events_known_at). Current
    = the count at as_of (valid backfilled evidence is included). Past observations do NOT change
    because evidence was reported later (no temporal leakage). A count increase that comes entirely
    from late evidence (events before the previous observation, reported afterward) is not a
    business-improving signal: no direction is inferred. A trend (IMPROVING/DRIFTING) needs >= 2
    real observation points - raw events accumulating is not automatically improving (F-09)."""
    window = goal.get("measurement_window_days")
    target = goal.get("target")
    if window is None or target is None:
        return {"status": "INSUFFICIENT_DATA",
                "reason": "window/target count belum lengkap - trajectory tidak dikarang"}
    as_of = int(as_of_ts) if as_of_ts is not None else int(time.time())
    known_now = events_known_at(ms, as_of)
    if not known_now:
        return {"status": "INSUFFICIENT_DATA", "metric_id": goal.get("metric_id"),
                "reason": "belum ada event teramati (aksi selesai bukan hasil - GR-22)"}
    cnow = count_events_in_window(known_now, window, as_of)
    now_count = cnow["counted"]
    obs = observation_points(ms, as_of)
    earlier = [t for t in obs if t < as_of]
    prev_t = earlier[-1] if earlier else None
    prev = late = None
    if prev_t is not None:
        known_then = events_known_at(ms, prev_t, historical=True)
        prev = count_events_in_window(known_then, window, prev_t)["counted"]
        # late evidence: qualified, happened BEFORE/at the previous observation, recorded after it,
        # and still inside the current window
        lo = as_of - int(window) * DAY
        late = sum(1 for e in known_now
                   if e.get("qualified") is True and e.get("ts") is not None
                   and lo <= int(e["ts"]) <= prev_t
                   and (e.get("recorded_ts") is None or e["recorded_ts"] > prev_t))
    qualified_ts = [int(e["ts"]) for e in known_now
                    if e.get("qualified") is True and e.get("ts") is not None and int(e["ts"]) <= as_of]
    base = {"metric_id": goal.get("metric_id"), "direction": "COUNT_IN_WINDOW",
            "counted": now_count, "target": target, "window_days": window,
            "as_of_ts": as_of, "window_start_ts": cnow["window_start_ts"],
            "n_observations": len(obs), "last_event_ts": max(qualified_ts) if qualified_ts else None,
            "unknown_qualification": cnow["unknown_qualification"],
            "unknown_timestamp": cnow["unknown_timestamp"]}
    if prev_t is not None:
        base["prev_observation_ts"] = prev_t
        base["late_reported"] = late
    if now_count >= target:
        return {"status": "ON_TRACK", **base,
                "reason": "target count terpenuhi pada window berjalan (waktu evaluasi)"}
    if prev is None:
        return {"status": "OFF_TRACK", **base,
                "reason": (f"{now_count} qualified dalam window berjalan, target {target:g} - "
                           "satu titik observasi, arah belum bisa dinilai")}
    like_for_like = now_count - (late or 0)
    if now_count > prev:
        if like_for_like > prev:
            return {"status": "IMPROVING", **base, "prev": prev}
        return {"status": "INSUFFICIENT_DATA", **base, "prev": prev,
                "reason": (f"count naik {prev} -> {now_count} hanya karena {late} bukti yang baru dilaporkan "
                           "(kejadian sebelum observasi sebelumnya) - bukan kejadian baru, "
                           "arah tidak disimpulkan")}
    if now_count < prev:
        return {"status": "DRIFTING", **base, "prev": prev,
                "reason": "window bergeser: count teramati menurun sejak observasi terakhir"}
    return {"status": "INSUFFICIENT_DATA", **base, "prev": prev,
            "reason": "count datar di bawah target - arah belum terlihat"}


def _rate_trajectory(goal: dict, ms: list[dict], as_of_ts: int | None = None) -> dict[str, Any]:
    """RATE_OR_RATIO: rate series from measurements that PASS the validity contract (A-11/F-10).

    The validity contract = `measurement_contract.rate_measurement_validity` - the SAME one the
    attainment evaluator uses, so the trajectory cannot claim "not proven comparable" while
    attainment uses the same number (or vice versa). Rejected measurements (zero denominator,
    missing/mismatched cohort or period, numerator > denominator) stay out of the series; the
    count + reasons are reported (`skipped`, `rejected`).

    A trend (IMPROVING/DRIFTING) is only stated when the LAST PAIR carries an identical
    cohort+period; otherwise the current status stays factual and no direction is claimed."""
    target = goal.get("target")
    rows, rejected = partition_rate_measurements(goal, ms, as_of_ts=as_of_ts)
    skipped = len(rejected)
    rej = [{"codes": r["codes"], "reasons": r["reasons"]} for r in rejected[-5:]]
    if target is None:
        return {"status": "INSUFFICIENT_DATA", "metric_id": goal.get("metric_id"),
                "reason": "target rate belum ditetapkan"}
    if not rows:
        return {"status": "INSUFFICIENT_DATA", "metric_id": goal.get("metric_id"),
                "skipped": skipped, "rejected": rej,
                "reason": ("rate tak terukur untuk Goal ini - denominator nol, kohort/periode tidak "
                           "terbukti sesuai Goal, atau belum ada pengukuran"
                           + (f" ({skipped} pengukuran ditolak, lihat rejected)" if skipped else ""))}
    rates = [r["rate"] for r in rows]
    current = rates[-1]
    prev = rates[-2] if len(rates) >= 2 else None
    pair = {(rows[-2]["cohort"], rows[-2]["period"]),
            (rows[-1]["cohort"], rows[-1]["period"])} if len(rows) >= 2 else set()
    comparable = len(rows) >= 2 and len(pair) == 1
    base = {"metric_id": goal.get("metric_id"), "direction": "RATE_OR_RATIO",
            "current": current, "target": target, "rates": rates,
            "cohort": rows[-1]["cohort"], "period": rows[-1]["period"],
            "n_measurements": len(rates), "skipped": skipped, "rejected": rej,
            "comparable": comparable}
    if current >= target - _EPS:
        return {"status": "ON_TRACK", **base, "reason": "rate terkini mencapai target"}
    if prev is None or not comparable:
        return {"status": "INSUFFICIENT_DATA", **base,
                "reason": ("arah tidak dinyatakan: rate yang dibandingkan tidak sebanding "
                           "(kohort/periode berbeda)" if len(rates) >= 2
                           else "satu pengukuran - arah belum bisa dinilai")}
    if current > prev:
        return {"status": "IMPROVING", **base, "prev": prev}
    if current < prev:
        return {"status": "DRIFTING", **base, "prev": prev,
                "reason": "rate bergerak menjauh dari target"}
    return {"status": "INSUFFICIENT_DATA", **base, "prev": prev,
            "reason": "rate datar di bawah target"}


def _criteria_trajectory(goal: dict, ms: list[dict]) -> dict[str, Any]:
    """EVIDENCE_CRITERIA: met/unmet/unknown criterion status - NO numeric score (A-15)."""
    latest: dict[str, bool | None] = {}
    for m in ms:
        if m.get("kind") == "criteria":
            latest[m.get("criterion") or "criterion"] = m.get("met")
    if not latest:
        return {"status": "INSUFFICIENT_DATA", "metric_id": goal.get("metric_id"),
                "reason": "belum ada hasil kriteria bukti teramati"}
    met = sum(1 for v in latest.values() if v is True)
    unmet = sum(1 for v in latest.values() if v is False)
    unknown = sum(1 for v in latest.values() if v is None)
    base = {"metric_id": goal.get("metric_id"), "direction": "EVIDENCE_CRITERIA",
            "criteria": dict(latest), "criteria_met": met, "criteria_unmet": unmet,
            "criteria_unknown": unknown, "criteria_total": len(latest)}
    if unknown:
        return {"status": "INSUFFICIENT_DATA", **base,
                "reason": "kriteria berstatus unknown - tidak disimpulkan dua arah"}
    if unmet:
        return {"status": "INSUFFICIENT_DATA", **base,
                "reason": (f"kriteria bukti belum terpenuhi ({unmet} dari {len(latest)})"
                           " - bukan tren angka, bukan kegagalan bisnis")}
    return {"status": "ON_TRACK", **base, "reason": "semua kriteria bukti terpenuhi"}


def _typed_trajectory(goal: dict, values: list[float]) -> dict[str, Any]:
    """Non-revenue metric trajectory: direction per semantics (int 09 §3.2)."""
    target = goal.get("target")
    if target is None:
        return {"status": "INSUFFICIENT_DATA", "reason": "target metric belum terukur"}
    if not values:
        return {"status": "INSUFFICIENT_DATA",
                "reason": "metric belum punya pengukuran teramati (aksi selesai bukan hasil — GR-22)"}
    current = float(values[-1])
    prev = float(values[-2]) if len(values) >= 2 else None
    direction = goal.get("direction") or ""
    target = float(target)
    if direction in ("DECREASE_TO_THRESHOLD", "AT_MOST"):
        achieved = current <= target + _EPS
        improving = prev is not None and current < prev
        worsening = prev is not None and current > prev
    elif direction == "MAINTAIN_RANGE":
        lo = goal.get("target_min")
        hi = goal.get("target_max")
        if lo is None or hi is None:
            return {"status": "INSUFFICIENT_DATA", "reason": "batas range belum lengkap"}
        achieved = float(lo) - _EPS <= current <= float(hi) + _EPS
        improving = prev is not None and abs(current - (float(lo) + float(hi)) / 2) < abs(
            prev - (float(lo) + float(hi)) / 2)
        worsening = prev is not None and not improving and not achieved
    else:  # INCREASE_TO_THRESHOLD / AT_LEAST / default
        achieved = current >= target - _EPS
        improving = prev is not None and current > prev
        worsening = prev is not None and current < prev
    base = {"metric_id": goal.get("metric_id"), "direction": direction,
            "current": current, "target": target, "n_measurements": len(values)}
    if achieved:
        return {"status": "ON_TRACK", **base, "reason": "target tercapai (semantik arah terpenuhi)"}
    if improving:
        return {"status": "IMPROVING", **base, "prev": prev}
    if worsening:
        return {"status": "DRIFTING", **base, "prev": prev,
                "reason": "nilai bergerak menjauh dari threshold"}
    if prev is None:
        return {"status": "INSUFFICIENT_DATA", **base,
                "reason": "arah belum bisa dinilai dari satu pengukuran"}
    return {"status": "INSUFFICIENT_DATA", **base, "reason": "nilai datar — arah belum terlihat"}


# ----------------------------------------------------------- goal series ----
#
# Observation series for the JOURNEY: the Goal's trajectory in its own metric + unit. Only
# OBSERVATIONS that pass the contract (rate: rate_measurement_validity; count: evidence already
# recorded at that point; value: observed value) become points. No interpolation, no invented
# historical points, missing != 0. Assessment (ACHIEVED/...) is NOT recomputed here or in the
# UI - that is `goal_evaluation`.

SERIES_OBSERVED = "OBSERVED"              # >= 1 valid observation
SERIES_NO_OBSERVATIONS = "NO_OBSERVATIONS"  # supported metric kind, no valid observation yet
SERIES_UNSUPPORTED = "UNSUPPORTED"        # no meaningful numeric series (criteria / unknown metric)

_SERIES_KIND = {"RATE_OR_RATIO": "rate", "COUNT_IN_WINDOW": "count", "EVIDENCE_CRITERIA": "criteria"}


def _is_revenue_goal(goal: dict) -> bool:
    return (goal.get("metric_id") or ("revenue_monthly" if goal.get("metric") == "revenue_monthly" else "")
            ) == "revenue_monthly"


def goal_series(
    goal: dict | None, measurements: list[dict], *, as_of_ts: int | None = None,
) -> dict[str, Any] | None:
    """Goal observation series for visualization, or None for a revenue Goal (the income check-in
    path remains).

    `measurements` = evidence COMPARABLE to the current Goal (the split lives in the store). Returns:
      {metric_id, unit, direction, kind, target, baseline, target_min, target_max, window_days,
       status: OBSERVED|NO_OBSERVATIONS|UNSUPPORTED, reason, points:[{ts, value, segment, ...}],
       rejected:{count, codes[]}, criteria?:[{criterion, met}]}
    `ts` = the observation's RECORDING time (epoch seconds). `segment` increments when the population
    (cohort) changes: a line connector is only valid within one segment."""
    g = goal or {}
    if _is_revenue_goal(g):
        return None
    direction = g.get("direction") or ""
    base: dict[str, Any] = {
        "goal_id": g.get("goal_id") or "", "goal_version": g.get("version"),
        "metric_id": g.get("metric_id") or "", "unit": g.get("unit") or "", "direction": direction,
        "kind": _SERIES_KIND.get(direction) or ("value" if direction else ""),
        "target": g.get("target"), "baseline": g.get("baseline"),
        "target_min": g.get("target_min"), "target_max": g.get("target_max"),
        "window_days": g.get("measurement_window_days"),
        "points": [], "rejected": {"count": 0, "codes": []}}
    ms = sorted((m for m in measurements or [] if isinstance(m, dict)),
                key=lambda m: m.get("ts") or m.get("event_ts") or 0)
    as_of = int(as_of_ts) if as_of_ts is not None else int(time.time())

    if not direction:
        return {**base, "status": SERIES_UNSUPPORTED,
                "reason": "semantics Goal belum teridentifikasi - tidak ada seri yang sah untuk digambar"}

    if direction == "EVIDENCE_CRITERIA":
        latest: dict[str, bool | None] = {}
        for m in ms:
            if m.get("kind") == "criteria":
                latest[m.get("criterion") or "criterion"] = m.get("met")
        return {**base, "status": SERIES_UNSUPPORTED,
                "reason": "Goal diukur dengan kriteria bukti (met/unmet), bukan angka - tanpa sumbu numerik",
                "criteria": [{"criterion": k, "met": v} for k, v in latest.items()]}

    pts: list[dict[str, Any]] = []
    if direction == "RATE_OR_RATIO":
        rows, rejected = partition_rate_measurements(g, ms, as_of_ts=as_of)
        seg, prev_cohort = 0, None
        for r in rows:
            cohort = str(r.get("cohort") or "")
            if prev_cohort is not None and cohort != prev_cohort:
                seg += 1
            prev_cohort = cohort
            iv = r.get("interval") or {}
            pts.append({"ts": r.get("ts"), "value": r["rate"], "segment": seg, "cohort": cohort,
                        "period": r.get("period") or "", "period_start_ts": iv.get("start_ts"),
                        "period_end_ts": iv.get("end_ts"), "numerator": r.get("numerator"),
                        "denominator": r.get("denominator")})
        codes = sorted({c for x in rejected for c in x["codes"]})
        base["rejected"] = {"count": len(rejected), "codes": codes}
    elif direction == "COUNT_IN_WINDOW":
        window = g.get("measurement_window_days")
        if window:
            for t in observation_points(ms, as_of):
                known = events_known_at(ms, t, historical=True)
                pts.append({"ts": t, "value": count_events_in_window(known, window, t)["counted"],
                            "segment": 0})
    else:  # INCREASE/DECREASE_TO_THRESHOLD, AT_LEAST, AT_MOST, MAINTAIN_RANGE: observed values
        for m in ms:
            if m.get("kind") == "value" and m.get("value") is not None and m.get("ts") is not None:
                pts.append({"ts": int(m["ts"]), "value": float(m["value"]), "segment": 0})
    pts = [p for p in pts if p.get("ts") is not None and int(p["ts"]) <= as_of]
    pts.sort(key=lambda p: int(p["ts"]))
    if pts:
        return {**base, "status": SERIES_OBSERVED, "points": pts, "reason": ""}
    n_rej = base["rejected"]["count"]
    why = "belum ada observasi sah untuk metric ini"
    if n_rej:
        why += f" ({n_rej} pengukuran ditolak kontrak)"
    if direction == "COUNT_IN_WINDOW" and not g.get("measurement_window_days"):
        why = "window hitung belum ditetapkan - observasi count tidak dapat dihitung"
    return {**base, "status": SERIES_NO_OBSERVATIONS, "reason": why}


# ------------------------------------------------------------ decision traj --

# Status of "not yet settled" paths — the display-status vocabulary the engine ACTUALLY uses
# (contracts.py STATUS_WORDS: OPEN|TEST_FIRST|NOT_YET|STOP; feasibility mapping §contracts:
# UNDETERMINED→TEST_FIRST, CONDITIONAL→NOT_YET). This iteration's audit: the old signal counted
# "CONDITIONAL" statuses that never appeared in snapshots → a DEAD signal (never fired).
_UNSETTLED = ("TEST_FIRST", "NOT_YET")


def _n_unsettled(snap: dict) -> int:
    return sum(1 for v in (snap.get("path_statuses") or {}).values()
               if v in _UNSETTLED)


def decision_trajectory(snapshots: list[dict], events: list[dict] | None = None) -> dict[str, Any]:
    """Is UNDERSTANDING improving? Deterministic signals, no causal claims:
    - undecided paths (TEST_FIRST/NOT_YET) decreasing (unknown → definitive = evidence arrived)
    - primary constraint migrated (old constraint tested & replaced)
    - a PATH_STATUS_CHANGED event exists (a real outcome entered the system)"""
    if len(snapshots) < 2:
        return {"status": "NEEDS_DATA", "reason": "butuh ≥2 snapshot"}
    prev, cur = snapshots[-2], snapshots[-1]
    signals: list[str] = []
    nc_prev, nc_cur = _n_unsettled(prev), _n_unsettled(cur)
    if nc_cur < nc_prev:
        signals.append(f"jalur belum-tertentu (TEST_FIRST/NOT_YET) {nc_prev}→{nc_cur} (bukti masuk)")
    if (prev.get("primary_constraint_id") != cur.get("primary_constraint_id")
            and prev.get("primary_constraint_id")):
        signals.append(
            f"constraint migration {prev['primary_constraint_id']}→"
            f"{cur['primary_constraint_id']} (pemahaman berubah dari tes)")
    if any(e.get("type") == "PATH_STATUS_CHANGED" for e in (events or [])):
        signals.append("ada PATH_STATUS_CHANGED (outcome nyata menggeser jalur)")
    if signals:
        return {"status": "IMPROVING", "signals": signals}
    if prev == cur:
        return {"status": "STABLE", "reason": "tidak ada sinyal pemahaman berubah"}
    return {"status": "STABLE", "signals": ["perubahan metric tanpa sinyal epistemik"]}


# ------------------------------------------------------------- drift types ---

def drift_taxonomy(diff: dict | None, goal_changed: bool = False,
                    path_events: list[dict] | None = None) -> list[str]:
    """Classify the latest change — rerouting is normal (§5.4).
    May return >1 type at once; empty = no drift."""
    out: list[str] = []
    d = diff or {}
    if goal_changed:
        out.append("GOAL_DRIFT")
    if d.get("path_status_changes"):
        # path changes WITHOUT any changed metric = strategy, not conditions
        if not d.get("changed_metrics"):
            out.append("STRATEGY_DRIFT")
        else:
            out.append("STRATEGY_DRIFT")  # paths shifted (may coincide with conditions)
    if d.get("constraint_migration"):
        out.append("CONSTRAINT_SHIFT")
    if d.get("changed_metrics"):
        changed = set(d["changed_metrics"])
        market = changed & {"demand_sufficiency", "willingness_to_pay"}
        internal = changed - market
        if market and not internal:
            out.append("MARKET_DRIFT")  # demand/WtP changed, internals stable
    pe = path_events or []
    if (not d.get("changed_metrics") and not d.get("constraint_migration")
            and any(e.get("outcome") == "not_moved" for e in pe)):
        out.append("EXECUTION_DRIFT")  # actions ran without results, state unchanged
    # canonical order for determinism
    order = ["GOAL_DRIFT", "STRATEGY_DRIFT", "CONSTRAINT_SHIFT",
             "EXECUTION_DRIFT", "MARKET_DRIFT"]
    return [t for t in order if t in out]
