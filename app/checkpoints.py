"""LIVE checkpoint (int 16 §R6-A): a diagnosis is a checkpoint, not the end of the conversation.

New information after finalization: enters a durable event → canonical state → Goal/hypothesis/requirement evaluation
(automatically via the turn path). This module only (1) classifies CHANGE, (2) marks the last checkpoint
`stale` with a reason, and (3) creates a new checkpoint version on reassess — old checkpoints are NOT changed/deleted.

Change classes (not interchangeable):
  no_material_change | new_information | correction | goal_change | outcome_observation | knowledge_version_change
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.binding import build_binding, knowledge_changed

NO_CHANGE, NEW_INFO, CORRECTION, GOAL_CHANGE, OUTCOME, KNOWLEDGE = (
    "no_material_change", "new_information", "correction", "goal_change", "outcome_observation",
    "knowledge_version_change")
MATERIAL = {NEW_INFO, CORRECTION, GOAL_CHANGE, OUTCOME, KNOWLEDGE}


def classify_change(*, commit: Any, goal_before: dict | None, goal_after: dict | None,
                    event_kind: str, move_ref: str = "") -> str:
    """Priority order: outcome > goal_change > correction > new_information > no_material_change."""
    if event_kind == "outcome_observation" or move_ref:
        return OUTCOME if commit.accepted_claims else NO_CHANGE
    gb, ga = goal_before or {}, goal_after or {}
    if (gb.get("version"), gb.get("target"), gb.get("target_min"), gb.get("target_max")) != (
            ga.get("version"), ga.get("target"), ga.get("target_min"), ga.get("target_max")):
        return GOAL_CHANGE
    if getattr(commit, "revisions", None):
        return CORRECTION
    if commit.accepted_claims:
        return NEW_INFO
    return NO_CHANGE


def latest(s: Any) -> dict | None:
    cps = getattr(s, "checkpoints", None) or []
    return cps[-1] if cps else None


def mark_stale(s: Any, *, event_id: str, change: str) -> bool:
    """Mark the last checkpoint stale if the change is material. Returns True if marked."""
    cp = latest(s)
    if cp is None or change not in MATERIAL:
        return False
    cp["status"] = "stale"
    cp.setdefault("stale_reasons", []).append({"event_id": event_id, "change": change})
    return True


def make_checkpoint(s: Any, llm: Any, *, reason: str, artifact: Any = None, now: int | None = None,
                    carried_plan: dict | None = None, operation_id: str = "") -> dict:
    """New checkpoint (version n+1); the old one is marked `superseded` but kept intact.

    NC-R5 (Phase 6.1): `carried_plan` archives the plan REPLACED by this checkpoint — including
    status/outcome already reported against it — so reassessment never erases
    the execution history of the previous plan.
    NC-R4 (Phase 6.1): `operation_id` (pattern D-10) makes resending the same reassessment
    replay the checkpoint already accepted, instead of creating a second version."""
    cps = getattr(s, "checkpoints", None)
    if cps is None:
        cps = []
        s.checkpoints = cps
    prev = cps[-1] if cps else None
    n = (prev["version"] + 1) if prev else 1
    dump = artifact.model_dump() if hasattr(artifact, "model_dump") else artifact
    binding = build_binding(s, llm, now=now)
    cp = {
        "checkpoint_id": f"ck-{s.id}-{n:03d}", "version": n, "status": "current", "reason": reason,
        "binding": binding,
        "knowledge_changed_since_prev": knowledge_changed(prev.get("binding") if prev else None, binding),
        "supersedes": prev["checkpoint_id"] if prev else None,
        "source_event_ids": [e["event_id"] for e in s.events if e.get("role") == "user"],
        "diagnosis_ref": hashlib.sha1(json.dumps(dump, sort_keys=True, default=str).encode()).hexdigest()[:12]
        if dump else None,
        "diagnosis": dump,       # the COMPLETE artifact of this checkpoint — unchanged by subsequent checkpoints
        "stale_reasons": [],
    }
    if carried_plan:
        cp["carried_plan"] = carried_plan          # NC-R5: the replaced plan, together with its report
    if operation_id:
        cp["operation_id"] = str(operation_id)     # NC-R4: identity of the operation that gave birth to this version
    if prev:
        prev["status"] = "superseded"
    cps.append(cp)
    return cp


def summary(cp: dict | None) -> dict | None:
    if not cp:
        return None
    return {k: cp.get(k) for k in ("checkpoint_id", "version", "status", "reason", "supersedes",
                                   "knowledge_changed_since_prev", "stale_reasons", "diagnosis_ref")} | {
        # H6 (hotfix): the operation that produced this version, so a timeout recovery can prove that the
        # newest checkpoint is OUR commit instead of merely assuming it. null for older checkpoints.
        "operation_id": cp.get("operation_id") or None,
        "binding_id": (cp.get("binding") or {}).get("binding_id"), "ts": (cp.get("binding") or {}).get("ts")}


def find_by_operation(s: Any, operation_id: str) -> dict | None:
    """Checkpoints born from this operation (reverse scan). Same pattern as store.checkins:
    resending a reassessment with the SAME key replays the already-accepted result."""
    op = (operation_id or "").strip()
    if not op:
        return None
    for cp in reversed(getattr(s, "checkpoints", None) or []):
        if cp.get("operation_id") == op:
            return cp
    return None


def previous_to(s: Any, cp: dict | None) -> dict | None:
    """Checkpoint immediately BEFORE cp (to show the version transition). Read-only, without guessing."""
    cps = getattr(s, "checkpoints", None) or []
    if cp is None or not cps:
        return None
    for i, c in enumerate(cps):
        if c is cp:
            return cps[i - 1] if i > 0 else None
    return cps[-2] if len(cps) > 1 else None


def plan_actions(items: Any) -> list[dict]:
    """One plan (ActionItem, or a string in older artifacts) as a displayable row.

    Duck-typed like day_texts: this module does not force an import of the artifact schema. A row's identity
    is its identity WITHIN that plan (index + intervention_id). There is no title matching,
    and no status moving between plans (INV: DONE != SKIPPED, new plan != old plan)."""
    out: list[dict] = []
    for i, it in enumerate(items or []):
        out.append({
            "index": i,
            "text": str(getattr(it, "text", it) or ""),
            "status": str(getattr(it, "status", "TODO") or "TODO").upper(),
            "outcome": str(getattr(it, "outcome", "") or ""),
            "note": str(getattr(it, "note", "") or ""),
            "reported_at": getattr(it, "reported_at", None),
            "done_at": getattr(it, "done_at", None),
            "intervention_id": str(getattr(it, "intervention_id", "") or ""),
            # Phase 6.2: the corrections made to this action's report travel with the archived plan
            "outcome_revisions": list(getattr(it, "outcome_revisions", None) or []),
        })
    return out


def plan_counts(actions: list[dict]) -> dict:
    """Honest counts: DONE (executed) and SKIPPED (skipped) are NOT equated. complete means
    every step has been closed; executed_all means every step was actually worked on."""
    rows = actions or []
    n = len(rows)
    done = sum(1 for a in rows if a.get("status") == "DONE")
    skipped = sum(1 for a in rows if a.get("status") == "SKIPPED")
    blocked = sum(1 for a in rows if a.get("status") == "BLOCKED")
    open_ = n - done - skipped - blocked
    reported = sum(1 for a in rows if a.get("outcome") or a.get("reported_at"))
    return {"total": n, "done": done, "executed": done, "skipped": skipped, "blocked": blocked,
            "open": open_, "reported": reported,
            "complete": n > 0 and open_ == 0 and blocked == 0,
            "executed_all": n > 0 and done == n}


def _plan_report_view(report: Any) -> dict | None:
    """The plan-level outcome, without internals (operation keys, pending effect payloads)."""
    if not isinstance(report, dict) or not (report.get("outcome") or report.get("note")):
        return None
    return {k: report.get(k) for k in ("outcome", "note", "path", "reported_at")} | {
        "corrections": len(report.get("revisions") or [])}


def _plan_record_of(actions: list[dict], *, checkpoint: dict | None, source: str,
                    report: Any = None) -> dict:
    return {"report": _plan_report_view(report), "source": source,
            "checkpoint_id": (checkpoint or {}).get("checkpoint_id"),
            "checkpoint_version": (checkpoint or {}).get("version"),
            "actions": actions, "counts": plan_counts(actions)}


def plan_snapshot(s: Any) -> dict | None:
    """The plan CARRIED by the last checkpoint, recorded immediately BEFORE the artifact is replaced.

    Called at the reassessment mutation boundary: reports already accepted against this plan
    (status/outcome/reported_at) are archived too, so the next checkpoint does not erase them."""
    items = getattr(getattr(s, "diagnosis", None), "day_by_day", None) or []
    if not items:
        return None
    return _plan_record_of(plan_actions(items), checkpoint=latest(s), source="live",
                           report=getattr(getattr(s, "diagnosis", None), "plan_report", None))


def plan_record(s: Any, *, limit: int = 3) -> dict | None:
    """Read-only projection: the plan carried by the CURRENT checkpoint + the plan of the previous version that
    has already been replaced (newest first, at most limit). There is no title/position matching and no
    status moved between plans (NC-R5)."""
    cps = getattr(s, "checkpoints", None) or []
    items = getattr(getattr(s, "diagnosis", None), "day_by_day", None) or []
    current = (_plan_record_of(plan_actions(items), checkpoint=(cps[-1] if cps else None), source="live",
                               report=getattr(getattr(s, "diagnosis", None), "plan_report", None))
               if items else None)
    superseded: list[dict] = []
    seen: set[str] = set()
    for cp in reversed(cps):
        carried = cp.get("carried_plan")
        if not carried:
            continue
        cid = str(carried.get("checkpoint_id") or cp.get("checkpoint_id") or "")
        if cid in seen:
            continue
        seen.add(cid)
        row = dict(carried)
        row["replaced_by"] = cp.get("checkpoint_id")
        row["replaced_by_version"] = cp.get("version")
        superseded.append(row)
        if len(superseded) >= max(1, int(limit)):
            break
    total = sum(1 for cp in cps if cp.get("carried_plan"))
    if current is None and not superseded:
        return None
    return {"current": current, "superseded": superseded, "superseded_total": total}

