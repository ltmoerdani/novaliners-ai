"""ActivityReference — one current decision + alternatives labeled by source (R1.6).

Mandate: internal-docs §3.5 + §2.5 ("present a single current
decision reference with explicit alternatives and versions") and the package
internal-docs §3 (K18).

Contract (pure projection — does NOT choose, does not judge, does not create
new semantic rules, does not become a second chooser):
  - `current`: the SINGLE current interaction decision, ONLY from the authoritative
    presented move (server). Without a presented move -> current = None; NEVER
    filled from alternatives (silent promotion forbidden).
  - `alternatives`: source+version-labeled opportunities from FOUR notions that coexist
    side by side (int 20 §3.5): presented decision, route frontier, canonical
    Move ledger, checkpoint day_by_day — each separate and honest
    about its origin.
"""
from __future__ import annotations

from typing import Any

CURRENT_SOURCE = "presented_decision"
ALT_SOURCES = ("route_frontier", "canonical_move_ledger", "checkpoint_day_by_day")
_SOURCES = (CURRENT_SOURCE, *ALT_SOURCES)


def _item(source: str, kind: str, id_: str, version: Any, title: str, **refs: Any) -> dict:
    out = {"source": source, "kind": kind, "id": id_, "version": version, "title": title}
    out.update({k: v for k, v in refs.items() if v is not None})
    return out


def _from_presented(presented: dict | None) -> dict | None:
    if not presented:
        return None  # no authority -> no current; NOT replaced by an alternative
    return _item(
        CURRENT_SOURCE, str(presented.get("kind") or "UNKNOWN"),
        str(presented.get("move_id") or presented.get("id") or "presented"),
        presented.get("version"), str(presented.get("headline") or presented.get("text") or ""),
        path_id=presented.get("path_id"), degraded=bool(presented.get("degraded")) or None,
    )


def _from_route_frontier(frontier: list[dict]) -> list[dict]:
    out = []
    for e in frontier or []:
        out.append(_item(
            "route_frontier", str(e.get("kind") or "EXECUTE"),
            f"route:{e.get('route_id')}/node:{e.get('node')}", e.get("route_revision"),
            str(e.get("activity") or e.get("title") or e.get("node") or ""),
            route_id=e.get("route_id"), node_id=e.get("node"),
        ))
    return out


def _from_move_ledger(moves: list[dict]) -> list[dict]:
    out = []
    for mv in moves or []:
        out.append(_item(
            "canonical_move_ledger", f"move:{mv.get('lifecycle') or 'PLANNED'}",
            str(mv.get("move_id") or ""), None, str(mv.get("objective") or ""),
            route_node_ref=mv.get("route_node_ref"),
        ))
    return out


def _from_checkpoint(plan: dict | None) -> list[dict]:
    if not plan:
        return []
    version = plan.get("version")
    return [_item(
        "checkpoint_day_by_day", "plan_step", str(st.get("id") or f"step:{i}"),
        version, str(st.get("title") or st.get("what") or ""),
        checkpoint_version=version,
    ) for i, st in enumerate(plan.get("steps") or [])]


def activity_references(*, presented_move: dict | None = None,
                        route_frontier: list[dict] | None = None,
                        move_ledger: list[dict] | None = None,
                        checkpoint_plan: dict | None = None) -> dict:
    """Build the activity reference from four sources. Deterministic; same input
    -> same output; without input -> {"current": None, "alternatives": []}."""
    return {
        "current": _from_presented(presented_move),
        "alternatives": (_from_route_frontier(route_frontier)
                         + _from_move_ledger(move_ledger)
                         + _from_checkpoint(checkpoint_plan)),
        "sources": list(_SOURCES),
    }
