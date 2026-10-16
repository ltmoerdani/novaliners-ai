"""GraphStore — adjacency list inside the session (int 11 Rev 11.1: graph semantics
≠ graph database; storage evolves only at thousands of nodes / cross-session).

Delta ingestion goes ONLY through this path; updates never delete old nodes (INV-4
— status changes, rows do not disappear).
"""
from __future__ import annotations

from core.state_graph.models import GraphDelta


class GraphStore:
    """In-memory graph per session; serialized as a plain dict into the session JSON."""

    def __init__(self, data: dict | None = None):
        d = data or {}
        self.nodes: dict[str, dict] = d.get("nodes") or {}
        self.edges: dict[str, dict] = d.get("edges") or {}

    # ── read ────────────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {"nodes": self.nodes, "edges": self.edges}

    def claim_ids(self) -> set[str]:
        return set(self.nodes.keys())

    def __len__(self) -> int:
        return len(self.nodes)

    # ── write (the only path) ───────────────────────────────────────────────
    def apply_delta(self, delta: GraphDelta) -> int:
        """Apply a delta that has ALREADY passed verify. Returns the number of new nodes.

        Idempotent: existing ids are skipped (verify already filters them too).
        """
        added = 0
        for c in delta.claims:
            if c.id in self.nodes:
                continue
            self.nodes[c.id] = c.model_dump()
            added += 1
        for e in delta.edges:
            if e.id in self.edges:
                continue
            self.edges[e.id] = e.model_dump()
        return added
