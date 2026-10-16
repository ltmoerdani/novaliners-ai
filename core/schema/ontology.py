"""TYPED contract for `ontology/constraints.json` (Phase E — ontology schema v0.3).

Why this module exists. `disqualifiers` used to be PROSE:

    "disqualifiers": ["Tidak ada bukti rejection/loss yang disebabkan trust/proof",
                      "Ada transaksi nyata baru-baru ini (trust terbukti cukup)"]

Prose cannot be executed, so the implementation lived as
`if constraint_id == "DM5.5"` in the generic layer — domain identity inside `core` (the same
bug class as S1), AND the first prose item was never executed at all. That is
"confidence theater", knowledge edition: the declaration looks present but binds nothing.

Now every disqualifier MUST be one of:

  (a) EXECUTABLE — has a `predicate` (the generic predicate language, the SAME as the KB rule;
      see `core/stages/rule_predicates.py`, including the mandatory citation rule) + a `note`
      shown when it fires; or
  (b) NON-EXECUTABLE — `executable: false` + an explicit `reason`.

Bare prose = ValidationError. No declaration may sit silently inert.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class Disqualifier(BaseModel):
    """One signal that VETOES a constraint (internal-docs §4)."""

    id: str = Field(min_length=1, description="unique ID, e.g. 'DM5.5-DQ1-transaksi-nyata'")
    source_prose: str = Field(
        min_length=1,
        description='the original prose (document/roadmap) translated — authoring trail',
    )
    predicate: dict[str, Any] | None = Field(
        default=None,
        description="predikat generik; dievaluasi core.stages.rule_predicates.evaluate_predicate",
    )
    note: str = Field(default="", description='text shown when the disqualifier fires')
    executable: bool = True
    reason: str | None = Field(
        default=None, description='why it is NOT yet executable (required when executable=false)'
    )

    @model_validator(mode="after")
    def _executability_must_be_declared(self) -> "Disqualifier":
        if self.executable:
            if not self.predicate:
                raise ValueError(f"{self.id}: executable=True wajib punya `predicate`")
            if not self.note:
                raise ValueError(f"{self.id}: executable=True wajib punya `note` (ditampilkan saat terpicu)")
        elif not self.reason:
            raise ValueError(
                f"{self.id}: executable=False wajib punya `reason` — deklarasi tanpa alasan "
                "adalah deklarasi yang diam-diam inert"
            )
        return self


def validate_disqualifiers(constraints: dict[str, dict]) -> list[str]:
    """Validate the `disqualifiers` block contract across all constraints.

    Returns a list of error messages (empty = pass). Deliberately returns a list instead of
    raising, so the ontology validator can collect ALL problems at once.
    """
    errors: list[str] = []
    for cid, body in constraints.items():
        for raw in body.get("disqualifiers") or []:
            try:
                Disqualifier.model_validate(raw)
            except Exception as exc:  # ValidationError → concise message
                first = getattr(exc, "errors", lambda: [])()
                detail = first[0].get("msg", str(exc)) if first else str(exc)
                errors.append(f"{cid}: disqualifier tidak memenuhi kontrak v0.3 — {detail}")
    return errors


def disqualifier_entries(body: dict) -> list[Disqualifier]:
    """Disqualifier entries of one constraint, already validated & normalized."""
    return [Disqualifier.model_validate(raw) for raw in body.get("disqualifiers") or []]
