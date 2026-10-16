"""Goal records workspace — first-class per-user Goal collection (int 09 §4.4, Phase 3).

The workspace stores 0..N Goals with stable identity + version + effective time;
EVERY navigation evaluation references one active goal. Target/definition changes = an EVENT
(GOAL_REVISED, version +1) — history is never rewritten (GR-20). Outcomes/achievements
are per-Goal: reaching Goal A does not close Goal B (GR-21).

File: store/workspaces/<user_id>/goals.jsonl — one line per event:
  {type: GOAL_CREATED|GOAL_REVISED|GOAL_ACTIVATED|GOAL_ACHIEVED|GOAL_STOPPED|GOAL_RESUMED|GOAL_MEASURED,
   ts, goal_id, version, goal: {...the Goal state at the event...}, payload: {...}}
The latest Goal record = the last state row per goal_id. Active goal = the latest GOAL_ACTIVATED
event (or the last GOAL_CREATED if it was never explicitly activated).

Deterministic, 0 LLM. Best-effort (consistent with workspace.py): no user_id → None.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from store.user_scope import validate_user_id

_BASE = Path(__file__).resolve().parents[1] / "store" / "workspaces"

EVENTS = (
    "GOAL_CREATED", "GOAL_REVISED", "GOAL_ACTIVATED", "GOAL_ACHIEVED",
    "GOAL_STOPPED", "GOAL_RESUMED", "GOAL_MEASURED",
)
_STATUS_BY_EVENT = {"GOAL_ACHIEVED": "ACHIEVED", "GOAL_STOPPED": "STOPPED", "GOAL_RESUMED": "ACTIVE"}


def _user_dir(user_id: str) -> Path:
    return _BASE / validate_user_id(user_id)


def _append(user_id: str, row: dict) -> None:
    d = _user_dir(user_id)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "goals.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _rows(user_id: str) -> list[dict]:
    out: list[dict] = []
    try:
        for line in (_user_dir(user_id) / "goals.jsonl").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def _now() -> int:
    return int(time.time())


def upsert_goal(user_id: str, goal: dict, *, activate: bool = True) -> dict:
    """Register a Goal (from create_session) — GOAL_CREATED for a new goal_id,
    GOAL_REVISED when material content changes (target/window/definition/metric).
    Returns the last event row (or None when nothing changed)."""
    if not user_id or not goal:
        return {}
    gid = goal.get("goal_id") or ""
    if not gid:
        return {}
    cur = current_goal(user_id, gid)
    ts = _now()
    if cur is None:
        row = {"type": "GOAL_CREATED", "ts": ts, "goal_id": gid, "version": 1,
               "goal": dict(goal), "payload": {}}
        if activate:
            _append(user_id, {"type": "GOAL_ACTIVATED", "ts": ts, "goal_id": gid,
                              "version": 1, "goal": dict(goal), "payload": {}})
        _append(user_id, row)
        return row
    from domains.revenue.schema.measurement_contract import material_change

    # evaluation parameters (target/window/deadline) OR dimensions that change evidence meaning
    # (metric/version/semantics/unit/scope/qualification) = a revision. The metric version is
    # compared in effective form (None legacy = v1) so re-upserting an old record does not
    # fabricate a revision.
    changed = any(cur.get(k) != goal.get(k) for k in (
        "target", "target_min", "target_max", "measurement_window_days", "deadline_days")) \
        or bool(material_change(cur, goal))
    if not changed:
        return {}
    version = int(cur.get("version", 1)) + 1
    g2 = {**goal, "version": version, "effective_ts": ts}
    row = {"type": "GOAL_REVISED", "ts": ts, "goal_id": gid, "version": version,
           "goal": g2, "payload": {"changed_from_version": cur.get("version", 1)}}
    _append(user_id, row)
    return row


def current_goal(user_id: str, goal_id: str) -> dict | None:
    """The current Goal state (the last state row for the goal_id)."""
    best: dict | None = None
    for r in _rows(user_id):
        if r.get("goal_id") == goal_id and r.get("goal"):
            best = r
    if best is None:
        return None
    g = dict(best["goal"])
    g["goal_id"] = goal_id
    # status = from the latest lifecycle event (ACHIEVED/STOPPED/ACTIVE)
    for r in _rows(user_id):
        if r.get("goal_id") != goal_id or r["type"] not in _STATUS_BY_EVENT:
            continue
        g["status"] = _STATUS_BY_EVENT[r["type"]]
    return g


def goals(user_id: str) -> list[dict]:
    """All of the user's current Goals (ordered by latest event)."""
    out: dict[str, dict] = {}
    for r in _rows(user_id):
        gid = r.get("goal_id")
        if not gid:
            continue
        if r.get("goal"):
            out.setdefault(gid, None)
            out[gid] = None  # state row — resolved via current_goal
    return [current_goal(user_id, gid) for gid in out if current_goal(user_id, gid)]


def active_goal_id(user_id: str) -> str | None:
    """Primary Goal for the next evaluation: the latest GOAL_ACTIVATED; without that,
    the last GOAL_CREATED (a new goal is automatically active — the single create_session gate)."""
    act = next((r["goal_id"] for r in reversed(_rows(user_id))
                if r.get("type") == "GOAL_ACTIVATED"), None)
    if act:
        return act
    return next((r["goal_id"] for r in reversed(_rows(user_id))
                 if r.get("type") == "GOAL_CREATED"), None)


def activate_goal(user_id: str, goal_id: str) -> dict | None:
    """Swap the Primary Goal (the next evaluation references this goal). The goal must exist."""
    cur = current_goal(user_id, goal_id)
    if cur is None:
        return None
    row = {"type": "GOAL_ACTIVATED", "ts": _now(), "goal_id": goal_id,
           "version": cur.get("version", 1), "goal": cur, "payload": {}}
    _append(user_id, row)
    return row


def lifecycle(user_id: str, goal_id: str, event: str, payload: dict | None = None) -> dict | None:
    """GOAL_ACHIEVED | GOAL_STOPPED | GOAL_RESUMED — per Goal, never propagates (GR-21)."""
    if event not in ("GOAL_ACHIEVED", "GOAL_STOPPED", "GOAL_RESUMED"):
        raise ValueError(f"event lifecycle Goal tidak sah: {event}")
    cur = current_goal(user_id, goal_id)
    if cur is None:
        return None
    row = {"type": event, "ts": _now(), "goal_id": goal_id,
           "version": cur.get("version", 1), "goal": cur, "payload": payload or {}}
    _append(user_id, row)
    return row


def record_measurement(user_id: str, goal_id: str, measurement: dict) -> dict:
    """Goal metric measurement (an observed event/value) — GR-09/GR-22: only measured evidence
    drives evaluation/trajectory, not action checkboxes. Returns the current evaluation."""
    cur = current_goal(user_id, goal_id)
    if cur is None:
        return {"error": "goal tidak ditemukan"}
    from domains.revenue.schema.measurement_contract import kind_check

    kc = kind_check(cur, str((measurement or {}).get("kind") or ""))
    if not kc["ok"]:
        # Rejected at the boundary: not logged, does not drive evaluation, old data untouched.
        return {"error": kc["reason"], "rejected": True, "code": kc["code"],
                "expected_kinds": kc["expected"], "semantics": kc["semantics"]}
    row = {"type": "GOAL_MEASURED", "ts": _now(), "goal_id": goal_id,
           "version": cur.get("version", 1), "goal": cur,
           "payload": dict(measurement)}
    _append(user_id, row)
    return evaluate_from_measurements(user_id, goal_id)


def measurements(user_id: str, goal_id: str) -> list[dict]:
    """All GOAL_MEASURED payloads for a goal (time-ordered) — input for the typed trajectory.

    Every row carries `ts` (= RECORD time, when the system accepted the evidence), `goal_version`
    and `recorded_goal` (the Goal's semantic identity at record time: metric/version/semantics/
    unit/scope/qualification): target/definition revisions do not rewrite history — an old
    evidence item's meaning is always readable with the Goal of its time (A-17)."""
    from domains.revenue.schema.measurement_contract import MATERIAL_DIMENSIONS

    out = []
    for r in _rows(user_id):
        if r.get("goal_id") != goal_id or r.get("type") != "GOAL_MEASURED":
            continue
        snap = r.get("goal") or {}
        rg = {k: snap.get(k) for k in (*MATERIAL_DIMENSIONS, "metric") if k in snap}
        out.append(dict(r["payload"], ts=r["ts"], goal_version=r.get("version"), recorded_goal=rg))
    return out


def _evaluate(cur: dict, ms: list[dict], as_of: int) -> dict:
    """Evaluate the typed Goal `cur` over measurements `ms` at time `as_of` — a pure function of
    its inputs; used identically by CURRENT and HISTORICAL evaluation (only the Goal, the evidence
    set, and as_of differ)."""
    from domains.revenue.schema.goal import Goal
    from domains.revenue.schema.goal_evaluation import evaluate_goal
    from domains.revenue.schema.measurement_contract import (
        events_known_at,
        partition_rate_measurements,
    )

    g = Goal(**{k: v for k, v in cur.items() if k in Goal.model_fields})
    if g.direction == "COUNT_IN_WINDOW":
        # The count = evidence already recorded as of as_of (valid backfill included); ts here =
        # EVENT time, with no fallback to the recording time (that is not when it happened).
        events = [{"ts": e["ts"], "qualified": e["qualified"]} for e in events_known_at(ms, as_of)]
        return evaluate_goal(g, events=events, as_of_ts=as_of)
    if g.direction == "RATE_OR_RATIO":
        # Only rates PASSING the contract (cohort/period matching the Goal, denominator > 0) become
        # the attainment basis — the same contract as the trajectory (measurement_contract).
        valid, rejected = partition_rate_measurements(cur, ms, as_of_ts=as_of)
        if valid:
            last = valid[-1]
            out = evaluate_goal(g, numerator=last.get("numerator"),
                                denominator=last.get("denominator"), as_of_ts=as_of,
                                rate_scope={k: last.get(k) for k in (
                                    "cohort", "period", "period_start_ts", "period_end_ts")})
        else:
            out = evaluate_goal(g)
            if rejected:
                out = {**out, "reasons": list(rejected[-1]["reasons"]),
                       "rejection_codes": list(rejected[-1]["codes"])}
        if rejected:
            out["rejected_rate_measurements"] = {
                "count": len(rejected),
                "reason": "rate tidak lolos kontrak kohort/periode - tersimpan, tidak dipakai attainment",
                "items": rejected[-5:]}
        return out
    if g.direction == "EVIDENCE_CRITERIA":
        crits = [m for m in ms if m.get("kind") == "criteria"]
        return evaluate_goal(g, criteria_results=[
            {"criterion": m.get("criterion", ""), "met": m.get("met")} for m in crits])
    vals = [m.get("value") for m in ms if m.get("kind") == "value" and m.get("value") is not None]
    return evaluate_goal(g, current=vals[-1] if vals else None)


def version_end_ts(user_id: str, goal_id: str, version: int) -> int | None:
    """When `version` stopped being valid = the ts of the first revision to a higher version.
    None when that version is still the current one."""
    for r in _rows(user_id):
        if r.get("goal_id") == goal_id and r.get("type") == "GOAL_REVISED" \
                and int(r.get("version", 1)) > int(version):
            return int(r["ts"])
    return None


def evaluate_from_measurements(
    user_id: str, goal_id: str, *, as_of_ts: int | None = None, version: int | None = None,
) -> dict:
    """Evaluate the typed Goal from the collected measurements. TWO modes, never mixed:

    CURRENT (version=None): the active Goal version's definition over measurements COMPARABLE with it
      (same evidence meaning: metric/version/semantics/unit/scope/qualification). Items whose
      meaning changed are reported as `excluded_incomparable` with per-dimension reasons — still
      stored, not discarded. Target/window revisions do not void evidence: raw events are
      re-evaluated under the new definition.
    HISTORICAL (version=N): Goal version N's definition (reconstructed from the event log) over the
      measurements recorded at version N, evaluated at the end of that version's validity — not at
      the current clock, so old results do not shift just because a window moved.
    `evaluation_basis` states the mode, version, and as_of used."""
    if version is not None:
        gh = goal_at_version(user_id, goal_id, version)
        if gh is None:
            return {"error": f"versi {version} tidak ditemukan untuk goal ini", "not_found": True}
        from domains.revenue.schema.measurement_contract import kind_check

        ms_v = [m for m in measurements(user_id, goal_id)
                if m.get("goal_version") == int(version) and kind_check(gh, m.get("kind", ""))["ok"]]
        end = version_end_ts(user_id, goal_id, int(version))
        as_of = int(as_of_ts) if as_of_ts is not None else (end if end is not None else _now())
        return {**_evaluate(gh, ms_v, as_of),
                "evaluation_basis": {"mode": "historical", "goal_version": int(version), "as_of_ts": as_of,
                                     "n_measurements": len(ms_v), "version_ended_ts": end}}
    cur = current_goal(user_id, goal_id)
    if cur is None:
        return {"error": "goal tidak ditemukan"}
    ms, excluded = split_comparable_measurements(user_id, goal_id)
    as_of = int(as_of_ts) if as_of_ts is not None else _now()
    out = _evaluate(cur, ms, as_of)
    out["evaluation_basis"] = {"mode": "current", "goal_version": cur.get("version", 1),
                               "as_of_ts": as_of, "n_measurements": len(ms)}
    if excluded:
        out["excluded_incomparable"] = excluded_summary(excluded)
    return out


def excluded_summary(excluded: list[dict]) -> dict:
    """Summary of measurements excluded from the current evaluation + auditable reasons."""
    by_dim: dict[str, int] = {}
    for m in excluded:
        ex = m.get("exclusion") or {}
        for d in ex.get("differences", []):
            by_dim[d["dimension"]] = by_dim.get(d["dimension"], 0) + 1
        if ex.get("kind_code"):
            by_dim["kind"] = by_dim.get("kind", 0) + 1
    return {
        "count": len(excluded),
        "by_dimension": by_dim,
        "reason": ("makna bukti berubah sejak pengukuran direkam (metric/versi/semantics/unit/scope/"
                   "kualifikasi) atau bentuk bukti tidak cocok dengan semantics Goal - bukan bahan "
                   "evaluasi current; tetap tersimpan dan dapat dievaluasi historis per versi"),
        "items": [{"ts": m.get("ts"), "goal_version": m.get("goal_version"), "kind": m.get("kind"),
                   **(m.get("exclusion") or {})} for m in excluded[-5:]],
    }


def history(user_id: str, goal_id: str | None = None, limit: int = 200) -> list[dict]:
    """Goal event log (GR-20 audit) — filtered per goal when requested."""
    rows = [r for r in _rows(user_id) if goal_id is None or r.get("goal_id") == goal_id]
    return rows[-limit:]


def goal_at_version(user_id: str, goal_id: str, version: int) -> dict | None:
    """The Goal state at a given VERSION — reconstructed from the event log (source of truth,
    §5.3 mandate). GOAL_CREATED/GOAL_REVISED/GOAL_ACTIVATED rows store the full Goal state at
    their version; the last row with the requested version wins. None when the version never
    existed — the API caller maps this to 404. History is NEVER overwritten."""
    version = int(version)
    found: dict | None = None
    for r in _rows(user_id):
        if r.get("goal_id") != goal_id or not r.get("goal"):
            continue
        if r.get("type") in ("GOAL_CREATED", "GOAL_REVISED", "GOAL_ACTIVATED") \
                and int(r.get("version", 1)) == version:
            found = r
    if found is None:
        return None
    g = dict(found["goal"])
    g["goal_id"] = goal_id
    return g


def measurement_comparable(goal_now: dict, goal_at_v: dict | None) -> bool:
    """Compat: comparable when the evidence meaning at `goal_at_v` equals `goal_now`
    (see measurement_contract.comparability; no snapshot = comparable, the basis is reported)."""
    from domains.revenue.schema.measurement_contract import comparability

    return comparability(goal_at_v, goal_now)["comparable"]


def split_comparable_measurements(user_id: str, goal_id: str) -> tuple[list[dict], list[dict]]:
    """(comparable, excluded) against the CURRENT Goal. Excluded when (a) the evidence meaning
    changed since recording (material dimensions, incl. the metric version) or (b) its kind does
    not match the Goal's semantics (pre-validation data). Excluded items carry `exclusion`
    (dimensions + old/new values) so the reason is auditable. Nothing is deleted; different
    target/window does not exclude evidence."""
    from domains.revenue.schema.measurement_contract import comparability, kind_check

    cur = current_goal(user_id, goal_id)
    if cur is None:
        return [], []
    comp: list[dict] = []
    excluded: list[dict] = []
    for m in measurements(user_id, goal_id):
        cmp_ = comparability(m.get("recorded_goal"), cur)
        kc = kind_check(cur, m.get("kind", ""))
        if cmp_["comparable"] and kc["ok"]:
            comp.append(m)
        else:
            excluded.append({**m, "exclusion": {
                "differences": cmp_["differences"],
                **({"kind_code": kc["code"], "kind_reason": kc["reason"]} if not kc["ok"] else {})}})
    return comp, excluded
