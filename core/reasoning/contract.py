"""NextMove adaptive proposal contract "nm.v2" (int 16 §R5-C; int 18 `dsc.v1`).

TWO decisions side by side, not one: (1) the next step (nm.v1: kind/focus/text, UNCHANGED) and
(2) the sufficiency decision `checkpoint_eligibility` — whether the initial conclusion is already eligible to be
OFFERED even though useful questions remain. The second decision is parallel because "good enough" is orthogonal to
"what is the next step": the model may say "there is still one useful question, BUT the first picture is already eligible".

`MoveKind` stays at 4 (QUESTION|EVIDENCE_REQUEST|ACTION|HOLD) — there is NO PROVISIONAL as a step kind
(int 18 §4: that decision is parallel, not a step).

The model PROPOSES the next step from state + knowledge + hypotheses; deterministic rules (`guard.py`)
check every reference before the proposal becomes a NextMove. This contract deliberately does NOT include
requirement status fields, Goal confirmation, evidence grade, or diagnosis closure: the model has no
path to write them (extra="forbid").
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

NM_CONTRACT_VERSION = "nm.v2"
# One active version (owner decision #1): NO dual-validation nm.v1/nm.v2 — only the `checkpoint_eligibility`
# block is read OPTIONALLY (absence = previous behavior), so rollback = changing one line above.
CONTRACT_VERSIONS = (NM_CONTRACT_VERSION,)

# Canonical capacity for the number of uncertainty candidates per snapshot — ONE source for the candidate builder
# (`core/reasoning/uncertainties.py`) AND for the list capacity in this contract.
# Final deep check 15 Oct 2026 (finding P1): the candidate builder used to cap at 16 while `critical_unknown_ids`,
# `nonblocking_unknown_ids`, `marginal_information_value`, and `candidate_uncertainty_ids` capped at 12. As a result
# a snapshot with 13–16 askable candidates had NO valid representation for a ready level: S2 requires every
# askable candidate to be disclosed + every classified candidate to have a marginal entry, while the contract could
# not hold them. What is aligned is the CONTRACT CAPACITY — the candidate limit is NOT lowered (lowering it
# risks hiding material uncertainty).
MAX_UNCERTAINTY_CANDIDATES = 16

# The PROSE length limits in this contract are an anti-abuse safeguard (DoS), NOT semantics. Live finding
# 15 Oct 2026 (catering session, `store/sessions/3b69aac9157d`): the real model answered a rich story with
# `move_text` >600 and `expected_decision_change` >400 characters → pydantic rejected it → the whole turn fell to
# degraded HOLD ("On hold" that the user sees). Normal-length prose must NOT kill the turn; what is still
# rejected is genuinely exceeding this loose limit. Brevity discipline is still requested via the reasoner prompt.
PROSE_CAP_MOVE_TEXT = 1200          # move_text: one message to the user
PROSE_CAP_RATIONALE = 1200          # information_value_rationale
PROSE_CAP_DECISION_CHANGE = 800     # expected_decision_change · decision_impact · counterfactual · rationale
PROSE_CAP_DETAIL = 600              # information_gain · user_friction · measurement_method · conditions · rekomendasi
PROSE_CAP_STATEMENT = 480           # statement · hypothesis/action objective

MoveKind = Literal["QUESTION", "EVIDENCE_REQUEST", "ACTION", "HOLD"]
FocusType = Literal["uncertainty", "hypothesis", "goal"]
CheckpointLevel = Literal["STATE_ONLY", "DISCOVERY_NEEDED", "PROVISIONAL_READY", "DECISION_USABLE"]
Answerability = Literal["now_conversation", "needs_measurement", "needs_external", "unknown"]
LEVELS_READY = ("PROVISIONAL_READY", "DECISION_USABLE")


class MarginalDecisionValue(BaseModel):
    """Marginal decision value for ONE uncertainty candidate — qualitative and human-auditable;
    no numerical optimizer (scope firewall int 16 §16). `counterfactual` is its mandatory question:
    "if the user answered differently, which decision would change?". Empty = that question is NON-MATERIAL and
    therefore MUST NOT block the conclusion (int 18 §11.4)."""

    model_config = ConfigDict(extra="forbid")

    uncertainty_id: str = Field(min_length=1, max_length=120)
    decision_impact: str = Field(default="", max_length=PROSE_CAP_DECISION_CHANGE,
                                 description='which decision changes if this is answered')
    answerability: Answerability = Field(default="unknown",
                                         description=(
                                                     'can be answered now through conversation, or'
                                                     'needs measurement/external data'
                                                     ))
    information_gain: str = Field(default="", max_length=PROSE_CAP_DETAIL)
    user_friction: str = Field(default="", max_length=PROSE_CAP_DETAIL)
    counterfactual: str = Field(default="", max_length=PROSE_CAP_DECISION_CHANGE,
                                description=(
                                            "'if the user answers X, the decision changes to Y';"
                                            'empty = non-material'
                                            ))


class CheckpointEligibility(BaseModel):
    """PARALLEL decision on sufficiency: whether the initial conclusion is eligible to be offered. Four levels; EVIDENCE_PENDING
    is not a fifth level but an orthogonal condition `external_evidence_pending` (int 18 §11.2).

    The model cannot fake status: there is no requirement/Goal/grade status field here, and the highest
    level only means "the next useful decision is safe to pick" — not a final diagnosis.
    """

    model_config = ConfigDict(extra="forbid")

    level: CheckpointLevel
    basis_claim_refs: list[str] = Field(default_factory=list, max_length=16,
                                        description='id of the ACTIVE claims supporting this level')
    critical_unknown_ids: list[str] = Field(default_factory=list, max_length=MAX_UNCERTAINTY_CANDIDATES,
                                           description=(
                                                       'material uncertainties blocking'
                                                       'DECISION_USABLE'
                                                       ))
    nonblocking_unknown_ids: list[str] = Field(default_factory=list, max_length=MAX_UNCERTAINTY_CANDIDATES,
                                               description=(
                                                           'uncertainties that do NOT block the'
                                                           'conclusion'
                                                           ))
    marginal_information_value: list[MarginalDecisionValue] = Field(
        default_factory=list, max_length=MAX_UNCERTAINTY_CANDIDATES)
    external_evidence_pending: bool = False
    can_offer_checkpoint: bool = False
    recommendation: str = Field(default="", max_length=PROSE_CAP_DETAIL)
    rationale: str = Field(default="", max_length=PROSE_CAP_DECISION_CHANGE)


class HypothesisProposal(BaseModel):
    """Competing explanations proposed/revised by the model. `standing` is NOT here: it is computed by the guard
    from active support/contradiction (without false precision)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="", max_length=64, description=(
                                                           'id of an existing hypothesis, or empty'
                                                           '= new hypothesis'
                                                           ))
    statement: str = Field(min_length=3, max_length=PROSE_CAP_STATEMENT)
    supports: list[str] = Field(default_factory=list, max_length=12, description="id of the ACTIVE canonical claim")
    contradicts: list[str] = Field(default_factory=list, max_length=12)
    missing_evidence: list[str] = Field(default_factory=list, max_length=6)
    knowledge_refs: list[str] = Field(default_factory=list, max_length=6)


# Phase 7: one Move owns 1..MAX_MOVE_ACTIONS executable actions. This is a TECHNICAL bound on
# payload/UI size — NOT a product schedule: the count is content-driven (1 is a valid Move) and there
# is deliberately NO day/date field anywhere in the design.
MAX_MOVE_ACTIONS = 12


class MoveActionDesign(BaseModel):
    """ONE executable action inside a Move. It carries no day, date or cadence: the person decides
    when to do it, and only an EXPLICIT `depends_on` can restrict the order."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=PROSE_CAP_STATEMENT)
    instruction: str = Field(default="", max_length=PROSE_CAP_DETAIL)
    required: bool = True
    # 1-based positions of EARLIER actions in this same list. Empty = free order. Never inferred from
    # the array order — an unreferenced action has no dependency at all.
    depends_on: list[int] = Field(default_factory=list, max_length=6)


class MoveDesign(BaseModel):
    """Measurable experiment design for an executable step (int 16 §R6-D). The model MUST NOT invent an
    audience/contact/probability list: fill only with derivatives of active claims; unknown = leave empty, do not invent.

    Phase 7: the design also carries the Move's EXECUTABLE ACTION LIST (`actions`). It replaces the
    old day-by-day plan: no day indices, no seven-day cadence, no forced order."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(default="", max_length=PROSE_CAP_STATEMENT)
    actions: list[MoveActionDesign] = Field(default_factory=list, max_length=MAX_MOVE_ACTIONS)
    preconditions: list[str] = Field(default_factory=list, max_length=6)
    constraints: list[str] = Field(default_factory=list, max_length=6)
    expected_evidence: list[str] = Field(default_factory=list, max_length=6)
    measurement_method: str = Field(default="", max_length=PROSE_CAP_DETAIL)
    observation_window_days: int = Field(default=0, ge=0, le=365)
    completion_criteria: list[str] = Field(default_factory=list, max_length=6)
    linked_path_id: str = Field(default="", max_length=120)
    linked_hypothesis_id: str = Field(default="", max_length=64)

    @field_validator("actions", mode="before")
    @classmethod
    def _coerce_action_specs(cls, v):
        """Provider robustness (the same rule as the legacy ActionItem coercion): a plain string is
        the action's title, so a well-meaning list of sentences is not a schema failure. A day/schedule
        key is NOT accepted — `extra="forbid"` rejects it explicitly rather than silently ignoring it."""
        if isinstance(v, list):
            out = []
            for row in v:
                if isinstance(row, str):
                    out.append({"title": row})
                elif isinstance(row, dict) and isinstance(row.get("text"), str)                         and "title" not in row:
                    out.append({**{k: x for k, x in row.items() if k != "text"}, "title": row["text"]})
                else:
                    out.append(row)
            return out
        return v


class OutcomeAssessment(BaseModel):
    """Verdict on a Move that has already been OBSERVED (G11). VALIDATED = signal aligned with the expected evidence; NOT causality."""

    model_config = ConfigDict(extra="forbid")

    move_id: str = Field(max_length=64)
    verdict: Literal["VALIDATED", "INCONCLUSIVE", "UNSUPPORTED"]
    observed_claim_refs: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = Field(default="", max_length=PROSE_CAP_DECISION_CHANGE)
    remaining_uncertainties: list[str] = Field(default_factory=list, max_length=6)


class NextMoveProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = NM_CONTRACT_VERSION
    state_snapshot_ref: str = Field(description=(
                                                'echo of the provided snapshot_id; proposals over'
                                                'stale state are rejected'
                                                ))
    goal_ref: str = ""
    proposed_move_kind: MoveKind
    focus_type: FocusType = "uncertainty"
    proposed_focus: str = Field(default="", max_length=120,
                                description="id ketidakpastian kandidat | id hipotesis | 'goal'")
    move_text: str = Field(default="", max_length=PROSE_CAP_MOVE_TEXT,
                           description=(
                                       "step sentence in the user's language (question/evidence"
                                       'request/action)'
                                       ))
    information_value_rationale: str = Field(default="", max_length=PROSE_CAP_RATIONALE)
    expected_decision_change: str = Field(default="", max_length=PROSE_CAP_DECISION_CHANGE)
    supporting_claim_refs: list[str] = Field(default_factory=list, max_length=16)
    evidence_source_refs: list[str] = Field(default_factory=list, max_length=8,
                                            description=(
                                                        'EVIDENCE_REQUEST for already-existing'
                                                        'evidence: id of an active claim OR'
                                                        'retrieved knowledge that is the SOURCE;'
                                                        'new measurement is not this (F1:'
                                                        'measurement = ACTION + move_design)'
                                                        ))
    knowledge_refs: list[str] = Field(default_factory=list, max_length=6)
    competing_hypotheses: list[HypothesisProposal] = Field(default_factory=list, max_length=4)
    candidate_uncertainty_ids: list[str] = Field(default_factory=list, max_length=MAX_UNCERTAINTY_CANDIDATES,
                                                 description='uncertainties considered')
    conditions_for_abstention: str = Field(default="", max_length=PROSE_CAP_DETAIL,
                                           description=(
                                                       'when to stop asking and switch to'
                                                       'measuring/acting'
                                                       ))
    abstain: bool = False
    user_constraints_considered: list[str] = Field(default_factory=list, max_length=8)
    move_design: Optional[MoveDesign] = None                 # required for ACTION (G10)
    outcome_assessment: Optional[OutcomeAssessment] = None   # only for a Move OBSERVED (G11)
    # dsc.v1: PARALLEL (sufficiency) decision — optional; absence = behavior before nm.v2 (fail-closed guard in G7)
    checkpoint_eligibility: Optional[CheckpointEligibility] = None
    notes: Optional[str] = Field(default=None, max_length=400)
