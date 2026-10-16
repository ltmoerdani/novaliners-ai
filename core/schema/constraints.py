"""Layer 0 — schema: hypothesis & constraint map (internal-docs §7)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HypothesisState(BaseModel):
    constraint_id: str
    score: float = Field(ge=0, le=1, description='RAW score (evidence level-weighted)')
    effective_score: float | None = Field(
        default=None,
        description=(
                    'iter-12: effective score after epistemic status + reversibility + diagnostic'
                    'value weighting — THIS is what determines the ranking'
                    ),
    )
    evidence_strength: float | None = Field(
        default=None,
        description=(
                    'iter-16: how strongly the evidence supports this constraint (level-weighted,'
                    'before penalties)'
                    ),
    )
    diagnostic_fit: float | None = Field(
        default=None,
        description=(
                    'iter-16 (ACH diagnosticity): fraction of supporting evidence NOT shared with'
                    'other constraints — non-diagnostic evidence must not inflate the ranking'
                    ),
    )
    decision_relevance: float | None = Field(
        default=None,
        description=(
                    'iter-16: how important it is to resolve now (reversibility × closeness to'
                    'conversion)'
                    ),
    )
    supporting_evidence_ids: list[str] = []
    contradicting_evidence_ids: list[str] = []


# ---------------------------------------------------------------------------
# Constraint Map (internal-docs §2): not ONE absolute diagnosis — the ranking
# is grouped per tier. "Which constraint is most worth resolving
# now" > "what is my problem".
# ---------------------------------------------------------------------------

ConstraintTier = Literal["PRIMARY", "CONTRIBUTING", "SECONDARY", "UNPROVEN", "UNKNOWN"]

# A1 (iter-8, internal-docs §5.2): epistemic dimension of a constraint — separates
# OBSERVED events from inference over the user's state. Orthogonal to the score tier.
ConstraintStatus = Literal[
    "OBSERVED",           # >=1 transactional/outcome evidence about an EVENT (loss/stall/deal)
    "INFERRED",           # dominant evidence about the user's own state/behavior (admission, habit)
    "CAUSAL_HYPOTHESIS",  # emerges from a mechanism cluster, no direct evidence
    "SYSTEMIC_RISK",      # computed from the Revenue State (capacity vs gap), not a probe
    "UNRESOLVED",         # not yet probed / two competing explanations
]

class ConstraintMapEntry(BaseModel):
    constraint_id: str
    name: str
    tier: ConstraintTier
    status: ConstraintStatus = Field(
        default="UNRESOLVED",
        description='Epistemic dimension (iter-8): OBSERVED > INFERRED > CAUSAL_HYPOTHESIS',
    )
    score: float = Field(ge=0, le=1)
    effective_score: float | None = Field(
        default=None,
        description=(
                    'iter-12: effective score (status × reversibility × diagnostic) — what'
                    'determines the ranking'
                    ),
    )
    supporting_evidence_ids: list[str] = []
    evidence_strength: float | None = None
    diagnostic_fit: float | None = None
    decision_relevance: float | None = None
    note: str = Field(default="", description='Includes a disqualifier note if triggered')

# iter-6: EXACTLY ONE PRIMARY (ranking[0]) — answers "which constraint drives the
# next action", not "which ones are also true". Runner-up >=0.6 = CONTRIBUTING
# (real but not the first-action driver), >=0.4 SECONDARY, the rest UNPROVEN.
# UNKNOWN = constraint not yet probed (has no evidence at all) —
# filled by the engine from the full ontology minus what is already ranked.
TIER_THRESHOLDS = {"PRIMARY": 0.6, "CONTRIBUTING": 0.6, "SECONDARY": 0.4, "UNPROVEN": 0.0}



# cross-module forward-ref rebuild (internal-docs §7 refactor)
for _m in list(globals().values()):
    if isinstance(_m, type) and hasattr(_m, 'model_rebuild'):
        try:
            _m.model_rebuild(_types_namespace=dict(globals()))
        except Exception:
            pass
