"""Universal State Graph models (int 11 Rev 11.1 §10.3–10.5).

Extraction ≠ interpretation (Rev 11.1 #1): triples store RAW labels; semantic
normalization (`normalized` + `vocabulary_source`) may only be filled by the
domain layer, and never replaces the raw label.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field


class Concept(BaseModel):
    """Raw subject/predicate/object — not a controlled vocabulary (anti-ontology INV)."""

    label: str = Field(description="raw extraction label, verbatim-ish, any language")
    normalized: Optional[str] = Field(
        default=None,
        description="normalization by a domain layer; NEVER replaces the raw label",
    )
    vocabulary_source: Optional[str] = Field(
        default=None, description="who normalized, e.g. 'domains/revenue/ontology'"
    )
    confidence: str = Field(default="raw", description="raw | mapped")


ValueType = Union[float, int, None]


class Triple(BaseModel):
    subject: Concept
    predicate: Concept
    object: Optional[Concept] = None
    value: ValueType = Field(default=None, description="numeric value if the claim is quantified")
    unit: Optional[str] = None


class Tense(str, Enum):
    now = "now"
    past = "past"
    future = "future"


class Modality(str, Enum):
    factual = "factual"
    hedged = "hedged"
    aspirational = "aspirational"
    hypothetical = "hypothetical"


class ClaimStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    contradicted = "contradicted"


class UniversalClaim(BaseModel):
    """Graph node (int 11 §10.3). Requires verbatim + provenance (INV-3)."""

    id: str
    type: str = Field(default="claim", description="claim|goal|desire|event|assumption|gap")
    triple: Triple
    tense: Tense = Tense.now
    temporal_context: Optional[str] = None
    modality: Modality = Modality.factual
    hedge: bool = False
    verbatim: str = Field(min_length=1)
    provenance: dict = Field(default_factory=dict, description="{'turn': n, 'session': id}")
    confidence: str = "self_reported"
    status: ClaimStatus = ClaimStatus.active


class EdgeKind(str, Enum):
    """Two classes that must never be confused (Rev 11.1 #2).

    Evidence-class lives in the State Graph; `may_indicate` is possibility-class
    (KB-derived) — `activates` is NOT here (it lives in the Applicability
    Result, §10.10).
    """

    supports = "supports"
    contradicts = "contradicts"
    derived_from = "derived_from"
    related_to = "related_to"
    confirms = "confirms"
    weakens = "weakens"
    supersede = "supersede"
    may_indicate = "may_indicate"


EVIDENCE_EDGES = {
    EdgeKind.supports,
    EdgeKind.contradicts,
    EdgeKind.derived_from,
    EdgeKind.related_to,
    EdgeKind.confirms,
    EdgeKind.weakens,
    EdgeKind.supersede,
}


class Edge(BaseModel):
    id: str
    src: str = Field(description="claim id")
    dst: str = Field(description="claim id | hypothesis id (may_indicate)")
    kind: EdgeKind
    provenance: dict = Field(default_factory=dict)


class GraphDelta(BaseModel):
    """Proposed delta from the understanding layer — becomes state ONLY after verify (§10.3b)."""

    claims: list[UniversalClaim] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
