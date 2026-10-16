"""Per-turn extraction DATA contract (no longer an LLM producer).

R3 (int 16 §R3, cleanup 15 Oct 2026): the meaning producer is the canonical semantic observation
(`core/semantic/observation.py`); evidence/number claims/intent tags are DERIVED from the canonical
claims produced by commit (`core/semantic/derive.extraction_payload`). The old producer function
(`extract_turn`, the LLM caller with the `EXTRACTION_SYSTEM` prompt) was removed in the 15 Oct 2026
legacy cleanup because it had no runtime consumer anymore; this module still holds the TYPE CONTRACT
used by the derivation path (`app/turn.apply_commit_effects`), the mock provider, and the
normalization test (LN1).

M5 (doc 14 §26): the phase-based interviewer (`analyze_turn`, `build_turn`, `InterviewAnalysis`)
was removed — enforced mechanically by evals/test_m5_phase_removal.py.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from core.schema.evidence import (  # exhaust the shim
    EvidenceItem,
    IntentTag,  # noqa: F401
)


class NumberClaim(BaseModel):
    """One number claim from a user answer — the product of LLM context understanding (int 08 §3).

    The old regex was dropped because it could not grasp tense (past vs now), semantic
    role (target vs rejected rate), and formats without "Rp" ("8jt/bln").
    The LLM decides all of that here; correctness is guarded by the verify gate (Phase B).
    """
    value: float = Field(description=(
                                     "number in MILLIONS (unit normalization in the LLM; '8jt/bln'"
                                     '→ 8.0)'
                                     ))
    period: str = Field(description="monthly | one_off | annual | per_project | hourly | count")
    tense: str = Field(description="now | past | future")
    role: str = Field(
        description="current_revenue | target | client_rate | historical_client_rate "
        "| rejected_price | ask_price | lead_count | horizon | other"
    )
    subject: Optional[str] = Field(
        default=None, description="who/what the number is about"
    )
    verbatim: str = Field(description=(
                                      'exact quote of the user sentence this number comes from'
                                      '(grounding)'
                                      ))
    hedge: bool = Field(
        default=False,
        description="true when the figure is an estimate ('about', 'around', 'usually')",
    )


class TurnExtraction(BaseModel):
    """Extraction result of ONE user message — no questions, no navigation decisions."""
    intent_tags: list[IntentTag] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    number_claims: list[NumberClaim] = Field(default_factory=list)
