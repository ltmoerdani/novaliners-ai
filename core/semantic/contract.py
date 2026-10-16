"""SemanticObservation contract "so.v1" — the ONE semantic-meaning authority (int 16 §R3-C, SC-01..SC-03).

The design follows the int 16 §6 constitution (minimal, extensible, source-preserving semantic model):

- The six pre-M4 claim roles MUST be preserved: claim | goal | desire | event | assumption | gap.
  Orthogonal aspects (preference/concern/constraint/intention/plan/behavior/conflict) do NOT
  replace the role — they enrich without closing meaning (SC-03).
- Raw triple stays open: subject/predicate/object are free of domain vocabulary (SC-02);
  domain normalization may only happen in the projection layer, never overwrite the raw label.
- Typed quantities: exact/approximate/range/bound — "almost 8 million" is not the same as
  "exactly 8 million" (CP-06; the form is adopted from the Adaptive branch study, rebuilt
  here without a closed predicate catalog).
- EXACT source anchor per event: the quote must be a substring of the cited EVENT text,
  not a global transcript substring (SC-05).
- Cross-turn relations: src/dst may reference old CANONICAL claims (id), not only
  this turn's claims (SC-06).
- Revision proposal: supersedes + revision_kind + reason — the status transition is performed by a
  deterministic commit, not by the model (SC-07).

This module is only SHAPE. Validation against state lives in core/semantic/commit.py.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

CONTRACT_VERSION = "so.v1"

MAX_CLAIMS = 32
MAX_RELATIONS = 24
QUOTE_MAX = 400

ValueKind = Literal["exact", "approximate", "range", "less_than", "at_most", "greater_than", "at_least"]
ClaimRole = Literal["claim", "goal", "desire", "event", "assumption", "gap"]
ClaimAspect = Literal[
    "", "preference", "concern", "constraint", "intention", "plan", "behavior", "conflict",
]
Tense = Literal["now", "past", "future"]
Epistemic = Literal["reported", "estimated", "measured"]
RelationKind = Literal[
    "related_to", "supports", "contradicts", "derived_from", "confirms", "weakens",
]
RevisionKind = Literal["correction", "refinement", "confirmation", "negation"]

MAX_VALUE = 1e15


class Quantity(BaseModel):
    """Typed quantity. "value" for exact/approximate/bound; "low"/"high" for range.

    Light normalization the model MAY perform: the user's natural value + unit
    (18 juta -> value=18.0 unit="juta"; 3.5k USD -> 3.5 "k USD"). Conversion to the
    domain's base unit is the projection's business (R4), not observation's.
    """

    value_kind: ValueKind
    value: Optional[float] = Field(default=None, ge=0, le=MAX_VALUE)
    low: Optional[float] = Field(default=None, ge=0, le=MAX_VALUE)
    high: Optional[float] = Field(default=None, ge=0, le=MAX_VALUE)
    unit: str = Field(default="", max_length=24)
    period: str = Field(
        default="unspecified", max_length=24,
        description="monthly | annual | weekly | daily | per_deal | per_project | one_off | unspecified")

    @model_validator(mode="after")
    def _shape(self) -> "Quantity":
        if self.value_kind == "range":
            if self.low is None or self.high is None or self.value is not None:
                raise ValueError("range wajib low+high tanpa value")
            if self.low > self.high:
                raise ValueError("range: low > high")
        elif self.value is None or self.low is not None or self.high is not None:
            raise ValueError(str(self.value_kind) + " wajib value tanpa low/high")
        return self


class ObservedClaim(BaseModel):
    """One claim resulting from semantic understanding — a proposal, not yet canonical."""

    ref: str = Field(pattern=r"^c[0-9]{1,3}$", description="rujukan lokal (c1, c2, ...)")
    role: ClaimRole
    aspect: ClaimAspect = ""
    subject: str = Field(min_length=1, max_length=120)
    predicate: str = Field(min_length=1, max_length=120)
    object: Optional[str] = Field(default=None, max_length=240)
    quantity: Optional[Quantity] = None
    tense: Tense = "now"
    hedge: bool = False
    epistemic: Epistemic = "reported"
    quote: str = Field(
        min_length=2, max_length=QUOTE_MAX,
        description="EXACT substring of this turn's user message")
    supersedes: Optional[str] = Field(default=None, max_length=96,
                                      description='id of the old CANONICAL claim being revised')
    revision_kind: Optional[RevisionKind] = None
    revision_reason: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def _coherent(self) -> "ObservedClaim":
        if self.role == "gap" and self.quantity is not None:
            raise ValueError("gap tidak membawa kuantitas")
        if (self.supersedes is None) != (self.revision_kind is None):
            raise ValueError("supersedes dan revision_kind harus bersama-sama ada/tidak")
        if self.supersedes and not self.revision_reason:
            raise ValueError("revisi wajib revision_reason")
        return self


class ObservedRelation(BaseModel):
    """Evidence relation between claims — intra-turn (local ref) OR cross-turn (old canonical id)."""

    src: str = Field(min_length=2, max_length=96, description=(
                                                              'local ref (c1) or canonical claim id'
                                                              '(cl-...)'
                                                              ))
    dst: str = Field(min_length=2, max_length=96)
    kind: RelationKind = "related_to"
    reason: str = Field(default="", max_length=240)


class SemanticObservation(BaseModel):
    """Result of ONE universal semantic-understanding call for one user event."""

    contract_version: Literal["so.v1"]
    language: str = Field(default="", max_length=8)
    claims: list[ObservedClaim] = Field(default_factory=list, max_length=MAX_CLAIMS)
    relations: list[ObservedRelation] = Field(default_factory=list, max_length=MAX_RELATIONS)
    uncertainties: list[str] = Field(
        default_factory=list, max_length=8,
        description='important things still unknown (free-form, short text)')
