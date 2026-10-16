"""Layer 0 — schema: RevenueState & CausalHypothesis (internal-docs §7)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from core.schema.constraints import ConstraintMapEntry, HypothesisState  # noqa: F401
from core.schema.evidence import EvidenceItem  # noqa: F401 (type refs)

DemandSufficiency = Literal["UNKNOWN", "AT_RISK", "INSUFFICIENT", "SUFFICIENT"]
PricingArch = Literal["PRESENT", "INFORMAL", "ABSENT", "UNKNOWN"]
ReadinessLevel = Literal["YES", "PARTIAL", "CONSTRAINED", "UNKNOWN", "NO"]

# G1 (iter-9, internal-docs §5.3): Evidence Reconciliation — never silently match
# conflicting evidence, and never overwrite
# the reality stated by the user with the reality computed by the model.
ReconciliationStatus = Literal["VERIFIED", "MISMATCH", "PARTIAL", "UNKNOWN"]


class RevenueState(BaseModel):
    """Representation of the user's revenue situation — computed from numbers in the evidence.

    E1 (iter-7, internal-docs §4.4): semantic typing — every number carries
    provenance in `sources` (field -> {level, evidence_id, derivation,
    confidence: measured|derived|unknown}). The LLM must not change state
    numbers; the extractor may only use numbers whose context is CLEAN."""
    current_monthly: Optional[float] = Field(default=None, description="IDR million per month")
    target_monthly: Optional[float] = None
    # F (23 Sep 2026): target origin — goal_marker|goal_fallback|transcript_marker.
    # goal_fallback is WEAK (target-fallback incident 19 Sep: the first Rp in goal_text)
    # but it was previously recorded "measured" without a marker → the UI now labels it "assumption".
    target_origin: Optional[str] = None
    gap_monthly: Optional[float] = None
    avg_deal_size: Optional[float] = None
    deals_needed: Optional[int] = Field(default=None, description="≈ gap / avg deal size")
    inquiry_rate_per_month: Optional[float] = None
    response_latency_days: Optional[float] = None
    acquisition_hours_per_week: Optional[float] = None
    acquisition_cycle_weeks: Optional[float] = None
    demand_exists: Optional[bool] = Field(default=None, description="Ada inquiry/lead masuk = demand exists")
    demand_signal: str = Field(
        default="UNKNOWN",
        description="Tier-2 #7: EXISTS | NONE | UNKNOWN — a demand signal only, not sufficiency",
    )
    demand_states: dict = Field(
        default_factory=dict,
        description=(
                    'iter-14: tri-state demand — {historical, current_flow,'
                    "sufficiency_for_target}. Proven 'demand exists' is HISTORICAL; sufficiency for"
                    'a future target is not automatic.'
                    ),
    )
    demand_volume: str = Field(
        default="UNKNOWN", description='LOW | MODERATE | HIGH | UNKNOWN (from inquiry rate)'
    )
    demand_quality: str = Field(default="UNKNOWN", description="PARTIALLY KNOWN | KNOWN | UNKNOWN")
    demand_sufficiency: DemandSufficiency = "UNKNOWN"
    demand_scalability: str = Field(default="UNKNOWN")
    willingness_to_pay: str = Field(
        default="UNKNOWN",
        description=(
                    'separate from demand: presence/absence of evidence that buyers pay at this'
                    'price'
                    ),
    )
    # D2 (Round 7): mirror willingness_to_pay for a new price — separate from current-price evidence
    # currently valid (current-price evidence is NOT new-price evidence; registry
    # commercial.willingness_to_pay_at_new_price).
    willingness_to_pay_new_price: str = Field(
        default="UNKNOWN",
        description=(
                    'PROVEN_AT_NEW_PRICE | REJECTED_AT_NEW_PRICE | UNKNOWN — real money commitment'
                    'at the proposed new price'
                    ),
    )
    # F1 (Round 7, D3): referral & CAC measurement — previously the signals state:referral_evidence /
    # state:cac_baseline were ALWAYS UNKNOWN (there is no source field). The field may only be filled
    # from measured evidence (provenance `measured` in `sources`); referral_evidence ≠ channel existence.
    referral_leads_recorded: Optional[int] = Field(
        default=None,
        description=(
                    'Number of recorded leads coming from referrals/network — evidence that'
                    'referrals produce leads, NOT the existence of a referral channel'
                    ),
    )
    cac_measured: Optional[float] = Field(
        default=None,
        description="Customer Acquisition Cost terukur per klien (Rp/juta) — baseline CAC",
    )
    delivery_hours_per_week: Optional[float] = Field(
        default=None,
        description='Tier-3 #13: actual delivery hours per week (for Readiness v1)',
    )
    capacity_utilization: Optional[float] = Field(
        default=None,
        description=(
                    'iter-15: delivery / healthy capacity (~40 hours). >0.8 = CONSTRAINED — a'
                    'boundary condition for revenue decisions, not just a constraint in the'
                    'ranking.'
                    ),
    )
    unit_rate_per_hour: Optional[float] = Field(
        default=None, description="IDR million per working hour (blended) — leverage signal"
    )
    pricing_architecture: PricingArch = "UNKNOWN"
    readiness: dict[str, ReadinessLevel] = Field(
        default_factory=dict,
        description="Readiness Matrix: {acquisition, conversion, delivery, scale} → YES/PARTIAL/UNKNOWN/NO",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Visible arithmetic, e.g. 'needs ±3 new clients to close the gap'",
    )
    sources: dict[str, dict] = Field(
        default_factory=dict,
        description="Provenance per field: {field: {evidence_id, level, derivation, "
        "confidence: measured|derived|unknown}}",
    )
    integrity_issues: list[dict] = Field(
        default_factory=list,
        description='validate_state() result: {check, severity: BLOCK|FLAG, msg}',
    )
    reconciliation: dict[str, dict] = Field(
        default_factory=dict,
        description=(
                    'G1 Evidence Reconciliation (iter-9): {field: {declared, computed, verified,'
                    'status: VERIFIED|MISMATCH|PARTIAL|UNKNOWN, discrepancy}} — never silently'
                    'reconciles conflicting evidence'
                    ),
    )


class CausalHypothesis(BaseModel):
    """Causal hypothesis with an Evidence Boundary — not an absolute verdict."""
    claim: str = Field(description="Strongest observed leak point (not a causal claim)")
    observed_mechanism: str = Field(description='Mechanism cluster with the most evidence')
    proven: list[str] = Field(
        default_factory=list,
        description=(
                    'Transactional/outcome facts WITHOUT attribution language — purely observed'
                    'events'
                    ),
    )
    user_attributed: list[str] = Field(
        default_factory=list,
        description=(
                    (
                    'iter-18 (P0 user #2): observed event whose CAUSE comes from user attribution'
                    "('because I replied late') — not causal isolation"
                    )                   ),
    )
    causal_status: str = Field(
        default="OBSERVED_ONLY",
        description=(
                    'iter-18 (P0 user #2): OBSERVED_ONLY or USER_ATTRIBUTED (plausible, not'
                    "isolated) — distinguishing the 'real event' from the 'cause claimed by the"
                    "user'"
                    ),
    )
    strongly_supported: list[str] = Field(default_factory=list, description="Konvergensi behavioral berulang")
    plausible: list[str] = Field(default_factory=list, description=(
                                                                   'Mechanism link with weaker'
                                                                   'evidence'
                                                                   ))
    still_unproven: list[str] = Field(
        default_factory=list, description='Causal claim NOT yet proven — needs an experiment'   )
    diagnostic_test: str = ""






# forward-ref rebuild across modules (internal-docs §7 refactor)
for _m in list(globals().values()):
    if isinstance(_m, type) and hasattr(_m, 'model_rebuild'):
        try:
            _m.model_rebuild(_types_namespace=dict(globals()))
        except Exception:
            pass
