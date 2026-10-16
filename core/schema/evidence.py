"""Layer 0 — schema: evidence, interview, trace (internal-docs §7)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

IntentKind = Literal["FACT", "GOAL", "ASSUMPTION", "PREFERENCE"]

class IntentTag(BaseModel):
    kind: IntentKind
    quote: str = Field(description="Kutipan asli user (verbatim)")
    normalized: str = Field(description="Canonical form, one sentence")
    confidence: float = Field(ge=0, le=1)

EvidenceLevel = Literal["transactional", "behavioral", "self_reported", "outcome"]

class EvidenceItem(BaseModel):
    """One evidence item in the ledger.

    `topic` is only a VIEW grouping label (evidence panel). Not read by navigation, planner, requirement,
    readiness, route, or path. Old ledgers store it as `phase` (a leftover of the phased interview, removed
    in M5): that key is still ACCEPTED on read (`validation_alias`) but never written again."""
    model_config = ConfigDict(populate_by_name=True)

    id: str
    signal: str = Field(description='Observed behavior/transaction')
    level: EvidenceLevel
    source_quote: Optional[str] = None
    topic: str = Field(validation_alias=AliasChoices("topic", "phase"), description="display label only")
    is_gap: bool = Field(
        default=False,
        description=(
                    'True = data MISSING/refused (not a fact). Does not participate in hypothesis'
                    'scoring.'
                    ),
    )
    claim_id: str = Field(
        default="",
        description="R3.2: id of the canonical claim the evidence came from "
        "(provenance); empty = legacy path.",
    )
    event_id: str = Field(default="", description="R4: source event of the claim (provenance)")
    claim_role: str = Field(
        default="", description="R4: semantic role of the source claim (claim|goal|desire|...)")
    epistemic: str = Field(default="", description="R4: epistemic degree of the source claim")
    admissible: bool = Field(
        default=True,
        description=(
                    'R4: may it enter requirement adjudication? False = semantically recognized but'
                    'NOT state evidence (e.g. assumption, desire). Recognized != admissible !='
                    'satisfies the requirement.'
                    ))
    inadmissible_reason: str = ""
    superseded: bool = Field(
        default=False,
        description=(
                    'R3.2: the source claim was superseded/negated. History is preserved, but it'
                    'does NOT count as current evidence (see current_evidence).'
                    ))


def current_evidence(items):
    """Evidence still in force (its source claim not superseded). History stays in the ledger."""
    return [e for e in items if not getattr(e, "superseded", False)]

# ---------------------------------------------------------------------------
# Hypothesis & Confidence (engine, deterministic)
# ---------------------------------------------------------------------------


class KnowledgeActivation(BaseModel):
    item_id: str = Field(description='Rule/intervention ID from the KB, e.g. TM-R01')
    source: str = Field(description="Knowledge source, e.g. tm / vp / cs / hk / internal")
    principle: str = Field(description='The concise principle applied (rule rationale)')
    confidence_impact: str = Field(description="RAISE_CONFIDENCE | LOWER_CONFIDENCE | IGNORE_SIGNAL | ...")
    applied_to: str = Field(
        default="",
        description='iter-16: the specific evidence/event in this case that this rule interprets',
    )
    decision_effect: str = Field(
        default="",
        description=(
                    "iter-16: concrete effect on the decision (e.g. 'lower demand confidence',"
                    "'measure substantive response, not just replies')"
                    ),
    )

class EvidenceActivation(BaseModel):
    evidence_id: str
    level: EvidenceLevel
    is_gap: bool = False
    supports: list[str] = Field(default_factory=list, description=(
                                                                  'constraint_id supported by this'
                                                                  'evidence'
                                                                  ))
    activated_rules: list[str] = Field(
        default_factory=list, description='KB rule triggered by this evidence'
    )

class HypothesisResolution(BaseModel):
    winner: dict = Field(description="{constraint_id, reason}")
    runner_up: list[dict] = Field(default_factory=list, description="[{constraint_id, why_lower}]")

class ReasoningTrace(BaseModel):
    trace_id: str
    evidence_activations: list[EvidenceActivation] = []
    knowledge_activated: list[KnowledgeActivation] = []
    hypothesis_resolution: Optional[HypothesisResolution] = Field(
        default=None,
        description="None when the ranking is empty (the LLM returned an empty mapping / degraded) "
        "— never crash",
    )
    contraindication_triggered: Optional[dict] = Field(
        default=None, description="{verdict, text, reason, until}"
    )
    applicability_conditions: list[dict] = Field(
        default_factory=list, description="[{condition_id, active_reason}]"
    )
    mechanisms: list[dict] = Field(
        default_factory=list,
        description="Evidence→Mechanism→Constraint clusters (internal-docs §2): "
        "[{mechanism_id, name, evidence_ids, constraints}]",
    )
    nba_grounding: Optional[dict] = Field(
        default=None,
        description=(
                    'Phase 3 (internal-docs §10.4): NBA↔KB intervention linkage —'
                    '{status, claimed_id, matched_via, intervention_ids, alternative_id,'
                    'alternative_name, expected_evidence, for_constraint}. None when the guard has'
                    'not run (legacy artifact compatibility).'
                    ),
    )

# ---------------------------------------------------------------------------
# Interview turn
# ---------------------------------------------------------------------------

class InterviewTurn(BaseModel):
    """Response for one conversation turn.

    `next_move` (QUESTION | EVIDENCE_REQUEST | ACTION | HOLD + reason trail) is the decision in force
    (M4). M5: no more `phase`, `phase_index`, or `kind="phase_transition"`; `progress` is state-based
    clarity (1.0 only when the planner stops asking)."""
    kind: Literal["probe", "ack"] = "probe"
    next_question: Optional[str] = None
    progress: float = Field(ge=0, le=1, description="0–1 state-based clarity; 1.0 = stop asking")
    intent_tags: list[IntentTag] = []
    evidence_delta: list[EvidenceItem] = []
    next_move: Optional[dict] = Field(
        default=None, description="planner decision: {kind, intent, focus, text, headline, stop, reason}"
    )
    navigation: Optional[dict] = Field(
        default=None, description=(
                                  'navigation context summary for this turn: counts, adjudication,'
                                  'path'
                                  )
    )
    candidate_move: Optional[dict] = Field(
        default=None,
        description=(
                    'R5: deterministic CANDIDATE decision of the m4.v1 planner'
                    '(candidate/guard/replay), NOT the presented one; the presented one = next_move'
                    '(guard-validated reasoning / degraded)'
                    ),
    )
    change_class: Optional[str] = Field(
        default=None,
        description="R6: no_material_change|new_information|correction|goal_change|outcome_observation",
    )
    checkpoint: Optional[dict] = Field(
        default=None, description=(
                                  'R6: latest checkpoint summary (version, status, staleness'
                                  'reason)'
                                  ))

# ---------------------------------------------------------------------------
# Diagnosis artifact — 7 blocks (internal-docs §L2)
# ---------------------------------------------------------------------------

# cross-module forward-ref rebuild (internal-docs §7 refactor)
for _m in list(globals().values()):
    if isinstance(_m, type) and hasattr(_m, 'model_rebuild'):
        try:
            _m.model_rebuild(_types_namespace=dict(globals()))
        except Exception:
            pass
