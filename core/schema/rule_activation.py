"""TYPED contract for knowledge rule-source activation (`ontology/knowledge/rule_activation.json`).

Which rule sources (prefixes `TM`, `VP`, ...) may be evaluated for diagnosis. This is a KNOWLEDGE
ACTIVATION mechanism, not an interview phase: one list for the whole ledger, with no per-phase
conversation gating (M5, doc 14 §26). Reference validation (prefixes registered in sources.json)
runs in `validate_knowledge.py`.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RuleActivation(BaseModel):
    """Active rule sources for diagnosis."""

    active_rule_sources: list[str] = Field(min_length=1, description=(
                                                                     'active rule source prefix'
                                                                     '(AC-01)'
                                                                     ))
    rationale: str = ""
