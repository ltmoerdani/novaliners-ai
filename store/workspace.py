"""P-D Workspace & State Versioning (internal-docs §5 + roadmap P-D).

Novaliners is workspace-centric, not chat-centric: the life journey lives in the
WORKSPACE (per user); sessions are only interactions. This module wraps the parts
that already live (Session store + J3 delta + P-E path states) into a formal
workspace object:

Workspace (per user_id)
├── Goal (P-A — from the last session carrying a goal)
├── Sessions (J3 linkage)
├── Possible Paths + outcome states (P-E — store/path_states)
├── State Snapshots (NEW — on every diagnosis finalize)
├── Business State Diff (NEW — deterministic between snapshots)
└── Event History (NEW — append-only, starting from P-E events)

A snapshot captures the METRICS that changed (not the full artifact — that is already in the
session store): revenue, utilization, WtP, demand sufficiency, primary
constraint, spectrum, status of each Possible Path (0..N). Diff = Business State Diff §5.2:
revenue delta, constraint migration, path status changes, spectrum change.

Deterministic, 0 LLM. File: store/workspaces/<user_id>/snapshots.jsonl + events.jsonl.
Without user_id → silent degrade (consistent with path_states).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from store.user_scope import validate_user_id

_BASE = Path(__file__).resolve().parents[1] / "store" / "workspaces"

# Minimal P-D event vocabulary (docs §7) — only what the runtime actually emits.
EVENTS = (
    "WORKSPACE_CREATED",
    "STATE_SNAPSHOT_CREATED",
    "PATH_STATUS_CHANGED",  # emitted by store/path_states (already live — P-E)
)


def _user_dir(user_id: str) -> Path:
    """D8 (int 08 §8.4): path-safe user_id via the shared helper — traversal
    is rejected BEFORE the path join. Callers still check `if not user_id`
    first (silent degrade for anonymous users is preserved)."""
    return _BASE / validate_user_id(user_id)


def _append_jsonl(path: Path, row: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass  # best-effort


def _read_jsonl(path: Path, limit: int = 0) -> list[dict]:
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out[-limit:] if limit else out


# ---------------------------------------------------------------- workspace --

def workspace_exists(user_id: str) -> bool:
    return bool(user_id) and _user_dir(user_id).exists()


def ensure_workspace(user_id: str) -> dict[str, Any] | None:
    """Get-or-create the workspace for a user. Emit WORKSPACE_CREATED once.
    None if user_id is empty (silent degrade)."""
    if not user_id:
        return None
    d = _user_dir(user_id)
    if not d.exists():
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        _append_jsonl(d / "events.jsonl", {
            "ts": int(time.time()), "type": "WORKSPACE_CREATED", "user_id": user_id,
        })
    return {"user_id": user_id, "dir": str(d)}


# ---------------------------------------------------------------- snapshot ---

def _snapshot_from_diagnosis(session_id: str, artifact) -> dict[str, Any]:
    """Changed state metrics + path status — deterministic from the artifact.

    Goal-Relative (int 09 §4.4): the snapshot carries the active Goal context (goal_id + metric)
    so snapshot history is attributed per Goal; the revenue field stays (legacy projection)."""
    rs = getattr(artifact, "revenue_state", None)
    paths = (getattr(artifact, "possible_paths", None) or {})
    gctx = ((paths.get("context") or {}).get("goal")) or {}
    return {
        "ts": int(time.time()),
        "session_id": session_id,
        "goal_id": gctx.get("goal_id") or None,
        "goal_metric_id": gctx.get("metric_id") or None,
        "current_monthly": getattr(rs, "current_monthly", None),
        "capacity_utilization": getattr(rs, "capacity_utilization", None),
        "willingness_to_pay": getattr(rs, "willingness_to_pay", None),
        "demand_sufficiency": getattr(rs, "demand_sufficiency", None),
        "avg_deal_size": getattr(rs, "avg_deal_size", None),
        "primary_constraint_id": getattr(artifact, "primary_constraint_id", None),
        "spectrum_level": (getattr(artifact, "decision_spectrum", None) or {}).get("level"),
        "path_statuses": {p["path_id"]: p.get("status") for p in paths.get("paths", []) if p.get("path_id")},
    }


def record_snapshot(user_id: str, session_id: str, artifact) -> dict[str, Any] | None:
    """Append a snapshot on diagnosis finalize + emit STATE_SNAPSHOT_CREATED.
    Return the snapshot + diff vs the previous snapshot (if any)."""
    ensure_workspace(user_id)
    snap = _snapshot_from_diagnosis(session_id, artifact)
    d = _user_dir(user_id)
    prior = _read_jsonl(d / "snapshots.jsonl", limit=1)
    _append_jsonl(d / "snapshots.jsonl", snap)
    _append_jsonl(d / "events.jsonl", {
        "ts": snap["ts"], "type": "STATE_SNAPSHOT_CREATED",
        "user_id": user_id, "session_id": session_id,
    })
    diff = state_diff(prior[0], snap) if prior else None
    return {"snapshot": snap, "diff_vs_prior": diff}


# -------------------------------------------------------------------- diff ---

_METRICS = ("current_monthly", "capacity_utilization", "willingness_to_pay",
            "demand_sufficiency", "avg_deal_size")


def state_diff(a: dict | None, b: dict) -> dict[str, Any]:
    """Business State Diff §5.2 — deterministic, one-way (a → b).
    Only changed fields are reported; no opinions/causal claims."""
    a = a or {}
    changed_metrics = {
        m: {"from": a.get(m), "to": b.get(m)}
        for m in _METRICS
        if a.get(m) != b.get(m)
    }
    constraint_migration = None
    if a.get("primary_constraint_id") and a.get("primary_constraint_id") != b.get("primary_constraint_id"):
        constraint_migration = {
            "from": a.get("primary_constraint_id"), "to": b.get("primary_constraint_id"),
        }
    path_changes = {}
    pa, pb = a.get("path_statuses") or {}, b.get("path_statuses") or {}
    for k in set(pa) | set(pb):
        if pa.get(k) != pb.get(k):
            path_changes[k] = {"from": pa.get(k), "to": pb.get(k)}
    spectrum_change = None
    if a.get("spectrum_level") and a.get("spectrum_level") != b.get("spectrum_level"):
        spectrum_change = {"from": a.get("spectrum_level"), "to": b.get("spectrum_level")}
    return {
        "changed_metrics": changed_metrics,
        "constraint_migration": constraint_migration,
        "path_status_changes": path_changes,
        "spectrum_change": spectrum_change,
        "anything_changed": bool(changed_metrics or constraint_migration
                                 or path_changes or spectrum_change),
    }


# ------------------------------------------------------------------- view ----

def workspace_view(user_id: str, path_states: dict | None = None,
                   sessions_summary: list[dict] | None = None) -> dict[str, Any] | None:
    """Workspace projection for API/UI: current goal, snapshots, last diff,
    event history. The internal graph is NEVER shown raw (§3.5 —
    the Map is a view)."""
    if not workspace_exists(user_id):
        return None
    d = _user_dir(user_id)
    snaps = _read_jsonl(d / "snapshots.jsonl")
    last_diff = state_diff(snaps[-2], snaps[-1]) if len(snaps) >= 2 else None
    return {
        "user_id": user_id,
        "goal": None,  # filled by the caller from the latest session that has a goal (P-A)
        "path_states": path_states or {},
        "sessions": sessions_summary or [],
        "snapshots": snaps[-10:],
        "n_snapshots": len(snaps),
        "last_diff": last_diff,
        "events": _read_jsonl(d / "events.jsonl", limit=50),
    }
