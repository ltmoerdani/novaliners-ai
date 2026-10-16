"""Stage: mechanism layer (internal-docs §7) — ALGORITHM ONLY.

Phase F (internal-docs §9): the mechanism clusters (6) + their signal lists USED
TO BE hardcoded in this module — domain identity living in the generic layer, same class of
issue as finding S1. They now live in `ontology/mechanisms.json` (owned by the domain pack)
and are read through `engine/domain_pack.py`. This module keeps only the generic part:
Evidence → Mechanism (deterministic keyword index) → Constraint. Evidence is never mapped
straight from the LLM to a constraint — it passes through observable mechanisms
(lead leakage, insufficient pipeline, trust gap, etc.).

`MECHANISMS` & `MECHANISM_SIGNALS` are still exported in the old shape so consumers
(`schemas/models.py`, `confidence.py`, evals) need no change; their contents are built from
the pack at import — the declaration stays one source of truth, and a broken pack = failure
at import (fail-fast), not a silent default.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from engine.domain_pack import mechanism_signals, mechanisms

if TYPE_CHECKING:
    from core.schema.evidence import EvidenceItem

MECHANISMS: dict[str, dict] = mechanisms()
MECHANISM_SIGNALS: dict[str, tuple[str, ...]] = mechanism_signals()


def detect_mechanisms(evidence: list["EvidenceItem"]) -> dict[str, list[str]]:
    """Deterministic Evidence → mechanism mapping (signal keywords).

    Returns: mechanism_id -> [evidence_id]. Gap evidence is excluded.
    """
    out: dict[str, list[str]] = {}
    for ev in evidence:
        if getattr(ev, "is_gap", False):
            continue
        text = (ev.signal or "").lower()
        for mech_id, signals in MECHANISM_SIGNALS.items():
            if any(s in text for s in signals):
                out.setdefault(mech_id, []).append(ev.id)
    return out
