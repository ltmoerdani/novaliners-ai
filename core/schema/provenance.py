"""Canonical provenance of a knowledge rule — "which evidence makes this rule TRUE?"

internal-docs §6.1. A matched rule may only contribute to candidate paths when its
basis can be pointed at: evidence ledger entries that really exist (or verbatim transcript quotes),
per predicate branch that is actually satisfied. When the basis cannot be formed, the result is
`UNSUPPORTED` — never fabricated support (PROV-04).

This module is a leaf: types only. Formation logic lives in core/stages (rule_predicates,
knowledge_rules)."""

from __future__ import annotations

from pydantic import BaseModel, Field

SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"

# Reference form for a transcript quote (not an evidence id): transcript:"<quote>"
TRANSCRIPT_PREFIX = "transcript:"


class BranchSupport(BaseModel):
    """One SATISFIED predicate branch with its anchors. `branch` = path in the predicate tree
    (e.g. `all_of[1].text_contains_any`); unsatisfied branches never appear here."""

    branch: str
    operator: str
    operand: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)


# Basis of an absence assumption. A tier-1 negative condition (`none_of`, `text_absent_pattern`,
# `evidence_level_absent`) is "satisfied" when NO matching record exists in the inspected ledger +
# transcript. That is absence of record, NOT proof that it did not happen (absence of evidence != evidence
# of absence).
ABSENCE_BASIS_NO_RECORD = "NO_MATCHING_RECORD"


class AbsenceAssumption(BaseModel):
    """A negative condition satisfied only because no matching record exists.

    It NEVER carries anchors and NEVER counts as positive support: it only marks that a positive
    twin claim (its sibling branch) rests on the assumption "no record denies it yet". True absence
    evidence (non-occurrence) can only be a POSITIVE branch quoting evidence/quotes that STATE that
    absence."""

    branch: str
    operator: str
    operand: list[str] = Field(default_factory=list)
    basis: str = ABSENCE_BASIS_NO_RECORD


class RuleSupport(BaseModel):
    """Why a rule matched, from the evaluation that actually ran.

    status SUPPORTED   : real anchors exist (non-gap evidence ledger entries and/or transcript quotes);
                         `evidence_ids` & `quotes` = union of the anchors of all satisfied branches
    status UNSUPPORTED : the rule is recorded as matched but anchors cannot be formed/verified — must NOT
                         ground candidate paths.
    assumptions        : negative conditions satisfied by absence of records (not absence evidence);
                         bookkeeping only — changes no status and adds no anchor."""

    rule_id: str
    tier: str = "judgment"  # deterministic | judgment
    status: str = UNSUPPORTED
    evidence_ids: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    branches: list[BranchSupport] = Field(default_factory=list)
    assumptions: list[AbsenceAssumption] = Field(default_factory=list)
    reason: str = ""

    @property
    def anchored(self) -> bool:
        return self.status == SUPPORTED and bool(self.evidence_ids or self.quotes)

    def refs(self) -> tuple[str, ...]:
        """Anchors as signal references: evidence ids, then prefixed transcript quotes."""
        return tuple(self.evidence_ids) + tuple(f'{TRANSCRIPT_PREFIX}"{q}"' for q in self.quotes)
