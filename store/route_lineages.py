"""Store RouteLineage PER-USER (T4, pattern of store/workspace.py without
importing domains.revenue — the ontology layer does not depend on the
revenue domain; T1 owner review).

storage-scope DEBT PAID (71b3c63, 27 Sep): the adjudication ledger is now
per-user too — both status channels share the same user boundary.
Identity invariant: user_id is validated by store.user_scope (SHARED helper
of both stores) — canonical pattern ^[A-Za-z0-9_-]{1,128}$, rejects
traversal; review conditionally green 27 Sep. The composer uses an injected
status_reader — the caller is responsible for the read scope.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from store.user_scope import validate_user_id

_BASE = Path(__file__).parent / "workspaces"


def _path(user_id: str, base_dir: Path | str | None = None) -> Path:
    validate_user_id(user_id)  # fail-closed, same as adjudication_ledger
    root = Path(base_dir) if base_dir else _BASE
    return root / user_id / "route_lineages.jsonl"


def append_lineage(user_id: str, row: dict[str, Any],
                   base_dir: Path | None = None) -> None:
    """row = {"lineage": dict, "frontier": [...]}. Append JSONL (pattern of
    workspace._append_jsonl)."""
    p = _path(user_id, base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def list_rows(user_id: str,
              base_dir: Path | None = None) -> list[dict[str, Any]]:
    p = _path(user_id, base_dir)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _last_row_per_route(rows: list[dict[str, Any]]) -> dict[str, dict]:
    """Last-row-wins per route_id (review 6585c32: append-only +
    update via a new row — the LAST row = winning state; prevents
    DUPLICATE route_id in build_instance_document)."""
    by_rid: dict[str, dict] = {}
    for row in rows:
        by_rid[row["lineage"].get("route_id")] = row
    return by_rid


def _norm_key(key: dict[str, Any]) -> dict[str, Any]:
    """R1-remediation Probe B (17 Oct): `context_id` enters the reconciliation key.
    Legacy rows/queries without this field are normalized to None so that:
    (1) old (3-field) lineages still match a None-context query — historical
    compatibility, old routes are not orphaned; (2) new goal-scoped lineages only match
    the same context — two different businesses of the same user no longer
    share a route identity."""
    out = dict(key or {})
    out["context_id"] = out.get("context_id")
    return out


def find_open_by_key(user_id: str, key: dict[str, Any],
                     base_dir: Path | None = None) -> dict[str, Any] | None:
    """Model B (matching rule): CLOSED lineages are EXCLUDED from
    match candidates — only OPEN ones may evolve with the same key.
    Uses the LAST row per route_id (state wins).

    R1-remediation Probe B: matching uses `_norm_key` on BOTH sides —
    a different context_id = a different key = a different route (separate
    business context); same/None context_id = valid reuse as before."""
    want = _norm_key(key)
    for row in _last_row_per_route(list_rows(user_id, base_dir)).values():
        lin = row["lineage"]
        if lin.get("lineage_status") == "OPEN" \
                and _norm_key(lin.get("reconciliation_key")) == want:
            return row
    return None


def find_closed_by_key(user_id: str, key: dict[str, Any],
                       base_dir: Path | None = None) -> dict[str, Any] | None:
    """CLOSED with the same key = source of reopened_from (Model B), NOT a
    reuse candidate. Normalized matching (`_norm_key`, Probe B remediation)."""
    want = _norm_key(key)
    hit = None
    for row in _last_row_per_route(list_rows(user_id, base_dir)).values():
        lin = row["lineage"]
        if lin.get("lineage_status") == "CLOSED" \
                and _norm_key(lin.get("reconciliation_key")) == want:
            hit = row  # the last one wins (chronological order)
    return hit


def build_instance_document(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconstruct the instance document (validate_route format): {lineages,
    frontier} — for T1.12 persist->reload->validator."""
    last = _last_row_per_route(rows)  # last-row-wins for identity dedup
    keep = list(last.values())
    return {
        "lineages": [r["lineage"] for r in keep],
        "frontier": [e for r in keep for e in r.get("frontier", [])],
    }
