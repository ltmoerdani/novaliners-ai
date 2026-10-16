"""Layer 0 — schema: DiagnosisArtifact (internal-docs §7)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field, field_validator

from core.navigation.compat import assess_path_set
from core.schema.constraints import ConstraintMapEntry, HypothesisState
from core.schema.evidence import (
    ReasoningTrace,
)
from domains.revenue.schema.state import CausalHypothesis, RevenueState


class ActionItem(BaseModel):
    """J1 (internal-docs §7): structured action items for day_by_day.

    Replaces plain strings so implementation results can be reported
    per action (status + outcome + KB intervention linkage + expected evidence
    at plan time). Backward compatible: old strings are coerced
    into ``text`` by the ``mode="before"`` validator.
    """

    day: Optional[int] = Field(default=None, ge=1, le=7)
    text: str
    intervention_id: str = Field(
        default="",
        description='KB intervention ID that grounds this action (e.g. TM-I03)',
    )
    expected_evidence: str = Field(
        default="",
        description="Expected result prediction (PDCA 'Study'): the comparator for the real outcome",
    )
    status: Literal["TODO", "DONE", "SKIPPED", "BLOCKED"] = "TODO"
    outcome: str = Field(default="", description='Implementation result reported by the user (enum)')
    note: str = Field(default="", description=(
                                              'Free-form note from the user when reporting the'
                                              'result'
                                              ))
    reported_at: Optional[int] = Field(
        default=None, description='Unix timestamp when the outcome was reported'
    )
    done_at: Optional[int] = Field(
        default=None,
        description=(
                    'Unix timestamp when the status became DONE/SKIPPED (order free, multiple per'
                    'day allowed)'
                    ),
    )
    report_operation_id: str = Field(
        default="",
        description=(
            (
            'D-10 (Phase 6.1): operation key of the LAST report applied to this action. Re-sending'
            'with the same key replays the already-accepted report instead of writing a second'
            'outcome event. Empty on old artifacts (no migration).'
            )
        ),
    )
    report_operations: list[dict] = Field(
        default_factory=list,
        description=(
            "D-10/H5 (Phase 6.1 hotfix): BOUNDED history of reports already accepted for this "
            "action ([{op, sig, ts}], at most the latest 10). The last key alone is not enough: "
            "once a newer report overwrites the key, re-sending an OLD report is no longer "
            "recognized and its effect can repeat. Empty on old artifacts (no migration)."
        ),
    )
    outcome_revisions: list[dict] = Field(
        default_factory=list,
        description=(
            "Phase 6.2: history of outcome reports REPLACED by a correction ([{outcome, note, "
            "path, reported_at, superseded_at, op}], at most 20). The effective report remains "
            "`outcome`/`note`; this row preserves history without counting it as a second "
            "independent observation."
        ),
    )
    outcome_path: str = Field(
        default="",
        description=(
            "Phase 6.2: path whose effective outcome effect is currently recorded (for "
            "correction reconciliation)."
        ),
    )
    outcome_log_ref: str = Field(
        default="",
        description=(
            "Phase 6.2: row_id of the effective outcome-log row (referenced by correction via "
            "`corrects`)."
        ),
    )


def day_texts(items: list) -> list[str]:
    """Convert day_by_day (list[ActionItem] or legacy list[str]) → list[str].

    Duck-typed: accepts any object with a ``text`` attribute — guard consumers
    need not import the schema (keeps the contract layer, the nba_grounding pattern).
    """
    return [str(getattr(i, "text", i)) for i in (items or [])]


class DiagnosisArtifact(BaseModel):
    status: Literal["provisional", "final"]
    # 1 WHERE YOU ARE
    where_you_are: str
    # 2 WHAT'S REALLY BLOCKING YOU (human language, NO code)
    primary_constraint: str
    primary_constraint_id: str
    secondary_constraints: list[str] = []
    # 3 WHY WE THINK SO (evidence convergence)
    why: list[str] = []
    # 4 WHAT NOT TO DO (contraindication)
    do_not: str
    do_not_detail: Optional[dict] = Field(
        default=None,
        description=(
                    "P-C (internal-docs §11): 'DON'T' as a navigation state, not a"
                    'static prohibition — {verdict: NOT_YET|STOP|TEST_FIRST, text, reason, until,'
                    'unlock_condition}. Deterministic from the contraindication registry; until ='
                    'the condition that unlocks it. One vocabulary with path status (NOT_YET ='
                    'precondition not met, can unlock).'
                    ),
    )
    # 5 NEXT BEST ACTION (7 days) — anti-generic: anchored to the user's evidence
    next_best_action: str
    first_step_today: str = Field(
        default="", description=(
            "LEGACY (Phase 7): no longer authored. Kept so artifacts written before the Move "
            "reconciliation still load; empty on every new diagnosis."
        )
    )
    day_by_day: list[ActionItem] = Field(
        default_factory=list,
        description=(
            "LEGACY (Phase 7): the old day-1..7 plan. It is NO LONGER AUTHORED and is never a live "
            "execution source - the canonical Move owns its executable action list. Kept so existing "
            "sessions keep their recorded plan, statuses and outcomes as history."
        ),
    )
    plan_report: dict = Field(
        default_factory=dict,
        description=(
            "Move-centric (first slice): the ONE outcome the person reports for the whole set of actions "
            "of this plan ({outcome, note, path, reported_at, revisions[], ops[], effects}). The plan owns "
            "it, so a reassessment that replaces the artifact archives it with the plan it belongs to."
        ),
    )

    @field_validator("day_by_day", mode="before")
    @classmethod
    def _coerce_day_items(cls, v):
        """Plain strings (old LLM output / provider robustness) → ActionItem(text=…)."""
        if isinstance(v, list):
            return [
                {"text": str(x)} if isinstance(x, str) else x
                for x in v
            ]
        return v
    outreach_script: str = Field(
        default="",
        description="First ready-to-copy-paste message/script template, using the user's context",
    )
    success_metric: str
    # 6 WE'LL KNOW WE'RE RIGHT WHEN
    well_know_when: str
    # 7 WHEN TO REASSESS
    reassess_window_days: int = Field(default=14, ge=7, le=60)
    pivot_rule: str
    pipeline_trace: Optional[dict] = Field(
        default=None,
        description="internal-docs §7: TraceReport.to_dict() — stage-by-stage trace alur E2E",
    )
    # Engine output (not LLM)
    confidence: float = 0.0
    constraint_confidence: float = Field(
        default=0.0,
        description=(
                    'iter-14: how certain we are that the primary constraint REALLY EXISTS (hard'
                    'event evidence) — not confidence in the revenue impact'
                    ),
    )
    revenue_impact_confidence: float = Field(
        default=0.0,
        description=(
                    'iter-14: how certain we are that FIXING this constraint moves revenue toward'
                    'the target — discounted by material unknowns (demand/capacity/pricing)'
                    ),
    )
    decision_confidence: float = Field(
        default=0.0,
        description=(
                    'iter-16 (VoI): how certain we are that the recommended NEXT STEP is the right'
                    'decision — may be high even when the diagnosis is uncertain'
                    ),
    )
    experiment_confidence: float = Field(
        default=0.0,
        description=(
                    'iter-16 (VoI): how certain we are that the probe can be executed and yields'
                    'information whatever the result'
                    ),
    )
    hypothesis_ranking: list[HypothesisState] = []
    confidence_band: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        default="LOW",
        description=(
                    'F3+ (18 Sep): epistemic band of `confidence` (LOW <0.35 · MEDIUM 0.35–0.65 ·'
                    'HIGH ≥0.65). A product surface that is STABLE across runs — raw numbers vary'
                    'naturally (LLM extraction variance, G7 internal-docs §10.3), the'
                    'band does not. The number stays for audit.'
                    ),
    )
    evidence_standing: Literal["INSUFFICIENT", "WEAK", "SUPPORTED"] = Field(
        default="WEAK",
        description=(
                    'DCP-05 (int 16 S1): EPISTEMIC standing of this artifact, separate from'
                    'workflow status (provisional|final). INSUFFICIENT = not enough evidence to'
                    'conclude; WEAK = there is a direction but it is not yet fit to treat as'
                    'certainty; SUPPORTED = engine confidence >=0.60 with hard evidence. "Synthesis'
                    'done" != "epistemically final diagnosis".'
                    ),
    )
    requires_new_evidence: bool = Field(
        default=True,
        description=(
                    'DCP-05: True when standing is not SUPPORTED - consumers (UI/checkpoint) must'
                    'show the need for measurement/new evidence, not certainty.'
                    ),
    )
    certification_reasons: list[str] = Field(
        default_factory=list,
        description=(
                    'int 18 §12.5 (dsc.v1): certification REASONS — empty + standing SUPPORTED ='
                    '`final`. Codes: ELIGIBILITY_ABSENT/STALE (+ dimensions:'
                    'STATE/GOAL/KNOWLEDGE/CONTRACT_CHANGED), ELIGIBILITY_LEVEL_NOT_READY,'
                    'ELIGIBILITY_CARRIED_OVER (a previous assessment reused),'
                    'CRITICAL_UNKNOWN_OPEN, EVIDENCE_WEAK/INSUFFICIENT — so `provisional` is always'
                    'explainable (and phase D metrics can be audited from the code, not'
                    'interpreted).'
                    ),
    )
    knowledge_rules_applied: list[str] = Field(
        default_factory=list,
        description='Active KB Rule ID at diagnosis (provenance, internal-docs §2)',
    )
    knowledge_activation: dict = Field(
        default_factory=dict,
        description="WP1/WP3: aktivasi KB — rules (deterministik vs LLM-matched), flags, "
        "blocked verdicts, anti-patterns, interventions (grounding NBA + expected evidence)",
    )
    reasoning_trace: Optional["ReasoningTrace"] = Field(
        default=None,
        description="Structured reasoning path evidence → mechanism → knowledge → decision "
        "(P1, internal-docs §2.10)",
    )
    constraint_map: list["ConstraintMapEntry"] = Field(
        default_factory=list,
        description="Revenue Constraint Map: PRIMARY/CONTRIBUTING/SECONDARY/UNPROVEN/UNKNOWN "
        "(internal-docs §2, iter-6 single-PRIMARY) — not an absolute one-diagnosis",
    )
    engine_disagreement: Optional[str] = Field(
        default=None,
        description="Transparent note when the LLM's choice ≠ the engine ranking (iter-3 #3)",
    )
    opportunities: list[dict] = Field(
        default_factory=list,
        description=(
                    'Tier-2 #8 (iter-11): typed commercial objects — expansion (active client) /'
                    'recovery (warm stall) / reactivation (stalled) — each with a different'
                    'intervention'
                    ),
    )
    decision_spectrum: Optional[dict] = Field(
        default=None,
        description=(
                    'Tier-3 #12 (iter-11): {level, rationale, evidence_required, next_level} —'
                    'STOP→NOT_YET→TEST_FIRST→GO_SMALL→PROCEED→SCALE with the conditions for moving'
                    'up a level'
                    ),
    )
    funnel_stages: list[str] = Field(
        default_factory=list,
        description=(
                    'Tier-3 #11 (iter-11): canonical funnel for measuring the cross-session'
                    'transition rate'
                    ),
    )
    metrics: dict = Field(
        default_factory=dict,
        description=(
                    'Tier-3 #14 (iter-11): run metrics — n_evidence_total, n_evidence_mapped,'
                    'mapping_coverage (for a fair comparison across runs)'
                    ),
    )
    revenue_state: Optional["RevenueState"] = Field(
        default=None,
        description=(
                    'Current Revenue State (internal-docs §4.4): numeric'
                    'representation of the revenue state from deterministic extraction of evidence'
                    '— the layer between evidence and diagnosis'
                    ),
    )
    possible_paths: Optional[dict] = Field(
        default=None,
        description=(
                    'Possible Paths (internal-docs): contextual path hypotheses from'
                    'the verified state — 0..N, identity from the strategy (not the motion); each'
                    'path carries applicability, feasibility'
                    '(SUPPORTED/CONDITIONAL/CONTRADICTED/UNDETERMINED), lifecycle, checks anchored'
                    'to requirements, provenance, and an `unresolved` reason when there are none —'
                    'deterministic, 0 LLM'
                    ),
    )
    provenance: dict = Field(
        default_factory=dict,
        description=(
                    '18 Sep 2026 incident: identity of the code that produced the artifact —'
                    '{code_commit, kb_sha256}. Self-describing artifact: retrospective evaluation'
                    'can no longer wrongly blame the code when the server process is stale.'
                    ),
    )
    layered_diagnosis: Optional[dict] = Field(
        default=None,
        description=(
                    'Layered structure (iter-8, internal-docs §5.2):'
                    'observed_constraint → likely_mechanism → underlying_hypothesis →'
                    'unresolved_cause — deterministic projection of Constraint Status'
                    ),
    )
    causal_hypothesis: Optional["CausalHypothesis"] = Field(
        default=None,
        description=(
                    'Causal hypothesis + Evidence Boundary (internal-docs §4.4):'
                    "causal claims tiered PROVEN→UNKNOWN — distinguishing the 'observed leak point'"
                    "from the 'proven cause'"
                    ),
    )

    @computed_field(  # type: ignore[prop-decorator]
        description="Status skema navigasi artefak (internal-docs §11): CURRENT atau LEGACY. "
        "LEGACY = artefak dibuat sebelum skema navigasi saat ini -> `needs_rediagnosis`; nol path pada "
        "artefak LEGACY BUKAN temuan bahwa tidak ada path. Diturunkan tiap baca dari `possible_paths`."
    )
    @property
    def navigation(self) -> dict:
        return assess_path_set(self.possible_paths)


# ---------------------------------------------------------------------------
# Phase 2 (iter-6, internal-docs §4.4): Revenue State + Evidence Boundary.
# DETERMINISTIC extraction from evidence — the LLM does not co-determine reality.
# ---------------------------------------------------------------------------



DiagnosisArtifact.model_rebuild()
