"""Route execution ledger PER-USER — source of the node `execution_view` (int 08 §3.4).

`execution_view` = "did the user take this activity?" — an EVENT, not a
world fact. It is derived from this ledger (append-only, pattern of
store/route_lineages.py), NOT stored in the node revision. A user report
("I already did it") never changes `satisfaction`: satisfaction
changes only through evidence adjudication (INV-R8: execution ≠ credit).

Events the user may record:
  EXECUTED   activity done  -> node moves EXECUTE -> VERIFY (evidence not yet in)
  ABANDONED  user declines/stops -> stays in the EXECUTE frontier (may be retried)
  RESET      cancel the previous report -> NOT_STARTED
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from store.user_scope import validate_user_id

_BASE = Path(__file__).parent / "workspaces"

EVENTS = ("EXECUTED", "ABANDONED", "RESET")
_VIEW_OF = {"EXECUTED": "EXECUTED", "ABANDONED": "ABANDONED", "RESET": "NOT_STARTED"}


def _path(user_id: str, base_dir: Path | str | None = None) -> Path:
    validate_user_id(user_id)  # fail-closed, shared identity invariant
    root = Path(base_dir) if base_dir else _BASE
    return root / user_id / "route_execution.jsonl"


def record(user_id: str, route_id: str, node_id: str, event: str,
           session_id: str = "", base_dir: Path | str | None = None,
           ts: int | None = None, op_id: str = "") -> dict[str, Any]:
    """Append one event. `event` outside EVENTS -> ValueError.

    D-10 (18 Oct 2026): optional `op_id` = client operation key; resending a failed
    request after a timeout does not duplicate the ledger row (see find_by_operation)."""
    if event not in EVENTS:
        raise ValueError(f"event {event!r} outside {EVENTS}")
    p = _path(user_id, base_dir)
    row = {"route_id": route_id, "node_id": node_id, "event": event,
           "session_id": session_id, "ts": int(ts if ts is not None else time.time()),
           "op_id": op_id or ""}
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def find_by_operation(user_id: str, op_id: str,
                      base_dir: Path | str | None = None) -> dict[str, Any] | None:
    """FIRST row with this operation key (or None). Idempotent replay: the caller
    verifies its route/node/event match before returning the same result."""
    if not op_id:
        return None
    for r in list_rows(user_id, base_dir):
        if r.get("op_id") == op_id:
            return r
    return None


def list_rows(user_id: str, base_dir: Path | str | None = None) -> list[dict[str, Any]]:
    p = _path(user_id, base_dir)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue  # a broken line must not break the user flow
    return rows


def latest_views(user_id: str, base_dir: Path | str | None = None,
                 route_ids: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """{node_id: {"view": NOT_STARTED|EXECUTED|ABANDONED, "ts": int}} — the LAST
    event per node wins.

    R1-remediation Probe B (17 Oct): optional `route_ids` restricts events to the
    routes of the context being read — node_id is inherited from the
    template, so two contexts can carry a node with the same id; without the filter
    execution markers could leak across contexts. None = old behavior (all
    user routes) — compatibility for old consumers."""
    out: dict[str, dict[str, Any]] = {}
    for r in list_rows(user_id, base_dir):
        if route_ids is not None and r.get("route_id") not in route_ids:
            continue
        view = _VIEW_OF.get(r.get("event"))
        if view and r.get("node_id"):
            out[r["node_id"]] = {"view": view, "ts": r.get("ts")}
    return out


def latest_views_by_route(user_id: str,
                          base_dir: Path | str | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """{route_id: {node_id: view}} — per-route index for the compose overlay
    (Probe B remediation 17 Oct): node_id is inherited from the template, so a full-
    user overlay could attach another context's execution marker to this context's route.
    Compose picks only its own route's index."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for r in list_rows(user_id, base_dir):
        view = _VIEW_OF.get(r.get("event"))
        rid, nid = r.get("route_id"), r.get("node_id")
        if view and nid and rid:
            out.setdefault(rid, {})[nid] = {"view": view, "ts": r.get("ts")}
    return out
