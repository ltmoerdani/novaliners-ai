"""NumberClaim → UniversalClaim mapper (M1 additive; int 11 §10.14, moved
earlier as a temporary bridge).

IMPORTANT (INV-2 / Rev 11.1 #1): this mapper accepts PLAIN DICTS (the persisted
session state), not agent class imports — core does not import the agent/domain
layer. Legacy `role` (current_revenue, etc.) enters as a RAW LABEL predicate
(vocabulary_source=null, confidence=raw) — core does not know its meaning; the
revenue plugin fills `normalized` later.
"""
from __future__ import annotations

from core.state_graph.models import (
    Concept,
    Edge,
    EdgeKind,
    GraphDelta,
    Modality,
    Tense,
    Triple,
    UniversalClaim,
)

_TENSE = {"now": Tense.now, "past": Tense.past, "future": Tense.future}


def _modality(hedge: bool, tense: Tense) -> Modality:
    if hedge:
        return Modality.hedged
    if tense == Tense.future:
        return Modality.aspirational
    return Modality.factual


def number_claims_to_delta(
    number_claims: list[dict], turn: int, session_id: str
) -> GraphDelta:
    """Build the proposed delta from one turn's number claims. `related_to` edges
    within the same turn are created for claims with an identical subject."""
    claims: list[UniversalClaim] = []
    edges: list[Edge] = []
    by_subject: dict[str, str] = {}

    for i, c in enumerate(number_claims, 1):
        cid = f"cl-t{turn}-{i:03d}"
        tense = _TENSE.get(str(c.get("tense") or "now"), Tense.now)
        subject_label = str(c.get("subject") or "user")
        role_label = str(c.get("role") or "other")
        predicate = Concept(label=f"has_{role_label}")  # raw, neutral from core's viewpoint
        uc = UniversalClaim(
            id=cid,
            type="claim",
            triple=Triple(
                subject=Concept(label=subject_label),
                predicate=predicate,
                value=c.get("value"),
                unit=None,
            ),
            tense=tense,
            temporal_context=f"turn {turn}",
            modality=_modality(bool(c.get("hedge")), tense),
            hedge=bool(c.get("hedge")),
            verbatim=str(c.get("verbatim") or ""),
            provenance={"turn": turn, "session": session_id, "source": "number_claims"},
            confidence="self_reported",
        )
        claims.append(uc)
        prev = by_subject.get(subject_label)
        if prev:
            edges.append(
                Edge(
                    id=f"e-t{turn}-{len(edges) + 1:03d}",
                    src=prev,
                    dst=cid,
                    kind=EdgeKind.related_to,
                    provenance={"turn": turn, "reason": "same subject"},
                )
            )
        else:
            by_subject[subject_label] = cid

    return GraphDelta(claims=claims, edges=edges)
