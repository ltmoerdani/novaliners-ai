"""TYPED contract for the domain pack manifest (Phase B / P0.4, internal-docs §9).

The manifest SHAPE is GENERIC — the engine does not care about domain content. Only the
*data* is domain-specific (`ontology/domain_pack.json`).

Why typed instead of a loose `dict`: research + our findings showed that manual validation
(grep `if not ...: raise`) leaks on unforeseen things (uncontracted fields, key typos,
foreign enum values). Pydantic moves validation into the CONTRACT: `Literal` for ops, types
for numbers, `model_validate` for structure. This is also the pre-image of the `DomainPack`
Protocol (F1) — the protocol follows in this module.

Note: manifest files use `$`-prefixed keys as documentation (`$comment`,
`$field_legend`, `$known_legacy_gap`). Pydantic ignores them (extra default).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ConstraintDomain(BaseModel):
    """One domain constraint (ID prefix) + its behavioral weights in the generic engine."""

    prefix: str = Field(min_length=1, description="prefix constraint ID, mis. 'DM5'")
    name: str = ""
    upstream_order: int = Field(
        ge=0, description='upstream-ness order; the smaller, the more upstream'
    )
    reversibility: float = Field(
        ge=0.0, le=1.0,
        description='effective-score multiplier — how quickly the user can fix it',
    )
    decision_priority: bool = Field(
        default=False,
        description="true = touches a decision number → full decision_relevance (1.0)",
    )
    experiment_priority: bool = Field(
        default=False,
        description=(
                    'true = the test for this constraint is fast & informative →'
                    'experiment_confidence +0.25'
                    ),
    )


class StateCondition(BaseModel):
    """State condition evaluated against the state object (duck-typed, `getattr`).

    `op` is deliberately narrow and closed: adding an op = adding a Literal value, not
    adding an `if` in the engine. A foreign value = ValidationError at load (fail-fast).
    """

    field: str = Field(min_length=1, description="atribut state, mis. 'deals_needed'")
    op: Literal["is_not_null", "gte"]
    value: float | None = Field(default=None, description='comparator for numeric ops')


class WhenState(BaseModel):
    all_of: list[StateCondition] = Field(default_factory=list)


class EvidenceMarkers(BaseModel):
    """Lexicon phrase table for classifying evidence from user text (Phase E).

    `event`    = phrases marking a failure EVENT (loss/stall/delay/reject) —
                 used by tier-1 to decide OBSERVED, not merely "hard evidence".
    `contrast` = natural-experiment phrases ("6/10 saat rajin vs sekarang") that are
                 also observations about the real world.

    The words are domain-specific (user language, sales context) → they live in the pack.
    """

    event: list[str] = Field(default_factory=list)
    contrast: list[str] = Field(default_factory=list)


class UnmappedDistributionNote(BaseModel):
    """E5 (iter-7) / Phase J: distribution evidence EXISTS but the LLM mapping missed it → honest note.

    Without this, a distribution constraint gets the UNKNOWN label "belum ter-probe" even
    though evidence exists — just because the LLM mapping dropped it. The signal vocabulary
    and its issuing domain belong to the pack (user language); the engine only knows
    how to use it.
    """

    applies_to_constraint_domains: list[str] = Field(min_length=1)
    signals: list[str] = Field(min_length=1)


class Mechanism(BaseModel):
    """One domain mechanism cluster: supported constraints + its detection signals."""

    id: str = Field(min_length=1, description='snake_case; appears in the artifact as `mech:<id>`')
    name: str = Field(min_length=1)
    description: str = ""
    constraints: list[str] = Field(min_length=1)
    signals: list[str] = Field(min_length=1)


class MechanismCatalog(BaseModel):
    """Domain mechanism catalog (`ontology/mechanisms.json`) — Phase F.

    The shape is generic; the content is domain. The engine keeps only the
    detection algorithm.
    """

    version: str = Field(min_length=1)
    mechanisms: list[Mechanism] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "MechanismCatalog":
        ids = [m.id for m in self.mechanisms]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"id mechanism DUPLIKAT: {dupes}")
        return self

    def as_engine_map(self) -> dict[str, dict]:
        """The shape the engine uses: id → {name, description, constraints}."""
        return {
            m.id: {"name": m.name, "description": m.description, "constraints": list(m.constraints)}
            for m in self.mechanisms
        }

    def signal_map(self) -> dict[str, tuple[str, ...]]:
        return {m.id: tuple(m.signals) for m in self.mechanisms}


class SystemicRiskRule(BaseModel):
    """Escalate UNRESOLVED → SYSTEMIC_RISK when state shows capacity is stuck."""

    verdict: str = "SYSTEMIC_RISK"
    applies_to_constraint_domains: list[str] = Field(default_factory=list)
    when_state: WhenState = Field(default_factory=WhenState)


class DomainPackManifest(BaseModel):
    """Manifest + lexicon of one domain pack (`ontology/domain_pack.json`)."""

    pack_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    schema_version: str | None = None
    constraint_domains: list[ConstraintDomain] = Field(min_length=1)
    evidence_markers: EvidenceMarkers = Field(default_factory=EvidenceMarkers)
    # Phase J (internal-docs): the last two domain vocabularies moved out of confidence.py.
    # Required (min_length=1) — a pack without these declarations fails at load, not silently.
    material_gap_keywords: list[str] = Field(
        min_length=1,
        description='P2: a gap touching the decision numbers is a MATERIAL gap → penalty + probe',
    )
    unmapped_distribution_note: UnmappedDistributionNote
    systemic_risk: SystemicRiskRule

    def domain_order(self) -> list[str]:
        return [d.prefix for d in sorted(self.constraint_domains, key=lambda d: d.upstream_order)]

    @model_validator(mode="after")
    def _unique_prefixes(self) -> "DomainPackManifest":
        """Duplicate prefix = contract violated.

        Previously this check lived as `if prefix in seen: raise` in the loader; now it is a
        contract invariant so that every use of the manifest is validated the same way.
        """
        prefixes = [d.prefix for d in self.constraint_domains]
        dupes = sorted({p for p in prefixes if prefixes.count(p) > 1})
        if dupes:
            raise ValueError(f"prefix constraint_domains DUPLIKAT: {dupes}")
        return self
