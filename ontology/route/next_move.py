"""NextMove selector v1 (D6 int 08 §8.4) — choosing over cross-route frontiers.

Contract (int 08 §3.6, INV-R10): a frontier = a SET with no ranking; ordering
lives ONLY here. The selector does not judge nodes/routes (projection already
did the judging) — it picks one opportunity and maps it to an output:

    VERIFY                -> EVIDENCE_REQUEST  (frontier_ref = node)
    RESOLVE_APPLICABILITY -> QUESTION          (frontier_ref = route_id)
    EXECUTE               -> ACTION            (frontier_ref = node)
    no opportunity, but an OPEN route exists -> HOLD (no frontier_ref)
    no OPEN route                          -> None (no NextMove)

Policy v1 = DETERMINISTIC PRIORITY (not information-gain — that is X3):
  1. EVIDENCE_REQUEST — the activity was already done, the proof is not in yet:
     the cheapest information, closing a node without new work.
  2. ACTION — hard nodes before soft (hard decides the node's satisfaction,
     soft is only a quality_flag — decision #4).
  3. QUESTION — applicability not yet certain: "Know Before You Move".

Ordering 2 before 3 is a correction (19 Oct 2026): applicability is a PER-ROUTE
property, while the old order compared it ACROSS routes. An APPLIES route can only
have an EXECUTE frontier when its own nodes are ready, so executing it never acts on
a route that may not apply — the invariant that matters is preserved. What the old
order did instead was let an UNRESOLVED SIBLING route freeze every executable one:
with five routes where one had unknown applicability, no ACTION was ever selected,
so no work could be authorised even though a route already applied. A route whose
applicability is unknown still has no EXECUTE frontier, so it can never be executed
on a guess.
Stable tie-break: (priority, strength, route_id, node order in the revision).
No LLM.
"""
from __future__ import annotations

from typing import Any

_PRIORITY = {"VERIFY": 0, "EXECUTE": 1, "RESOLVE_APPLICABILITY": 2}
_OUTPUT = {"VERIFY": "EVIDENCE_REQUEST", "RESOLVE_APPLICABILITY": "QUESTION",
           "EXECUTE": "ACTION"}


def select_next_move(routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """`routes` = the compose/bridge result: [{"lineage": ..., "frontier": [...]}].
    Only OPEN lineage is considered (CLOSED = out of the frontier)."""
    open_routes = [r for r in routes
                   if (r.get("lineage") or {}).get("lineage_status") == "OPEN"]
    if not open_routes:
        return None
    candidates: list[tuple] = []
    for r in open_routes:
        lin = r["lineage"]
        nodes = lin["revisions"][-1]["nodes"]
        pos = {n["node_id"]: i for i, n in enumerate(nodes)}
        strength = {n["node_id"]: n.get("strength") for n in nodes}
        for e in r.get("frontier") or []:
            kind = e.get("kind")
            if kind not in _PRIORITY or e.get("route_id") != lin["route_id"]:
                continue
            node = e.get("node")
            key = (_PRIORITY[kind],
                   0 if strength.get(node, "hard") == "hard" else 1,
                   lin["route_id"], pos.get(node, -1))
            candidates.append((key, kind, e, lin))
    if not candidates:
        return {"output": "HOLD",
                "reason": "tidak ada opportunity terbuka; route OPEN menunggu "
                          "hasil terukur atau dependency"}
    _key, kind, entry, lin = min(candidates, key=lambda c: c[0])
    ref = entry["route_id"] if kind == "RESOLVE_APPLICABILITY" else entry["node"]
    return {"output": _OUTPUT[kind], "frontier_ref": ref,
            "route_id": lin["route_id"],
            "reason": f"{kind} dipilih oleh policy prioritas v1"}
