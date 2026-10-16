"""Structured drift report (M2, user review: 'not just a string diff').

Compares OLD (number_claims + the legacy evidence path) vs NEW (the accepted graph
delta) per turn — the data-driven basis for the M3 decision ("can the graph view
replace RevenueState?"), not a feeling.
"""
from __future__ import annotations

from core.state_graph.models import GraphDelta


def _claim_field(c, key, default=None):
    """Works with both dicts (persisted state) and live pydantic NumberClaim objects."""
    if isinstance(c, dict):
        return c.get(key, default)
    return getattr(c, key, default)


def _key_number(value, tense) -> tuple:
    return (round(float(value), 2) if value is not None else None, tense)


def build_drift_report(
    turn: int,
    old_number_claims: list,
    accepted: GraphDelta,
    rejected_notes: list[str],
    error: str | None = None,
) -> dict:
    """Deterministic. Matching heuristic: an old number claim counts as 'matched'
    when the graph holds the same value+tense; otherwise 'old_only' (a signal the
    graph catches less). 'new_information' = non-numeric graph nodes (the point of
    M2: this richness is exactly what number_claims lack)."""
    graph_nums = {
        _key_number(c.triple.value, c.tense.value)
        for c in accepted.claims
        if c.triple.value is not None
    }
    matched, old_only = [], []
    for c in old_number_claims:
        k = _key_number(_claim_field(c, "value"), _claim_field(c, "tense"))
        entry = {
            "value": _claim_field(c, "value"),
            "tense": _claim_field(c, "tense"),
            "role": _claim_field(c, "role"),
        }
        (matched if k in graph_nums else old_only).append(entry)
    new_information = [
        {"id": c.id, "type": c.type, "subject": c.triple.subject.label,
         "predicate": c.triple.predicate.label}
        for c in accepted.claims
        if c.triple.value is None
    ]
    report = {
        "turn": turn,
        "old": {
            "number_claim_count": len(old_number_claims),
        },
        "new": {
            "claim_count": len(accepted.claims),
            "edge_count": len(accepted.edges),
            "by_type": _count_by_type(accepted),
        },
        "matched": matched,
        "new_information": new_information,
        "old_only": old_only,
        "verification": {
            "accepted": len(accepted.claims),
            "rejected": len(rejected_notes),
            "rejected_notes": rejected_notes[:10],
        },
        "risk": {
            "ungrounded": sum(1 for n in rejected_notes if "tidak ditemukan" in n or "kosong" in n),
            "unsupported_relation": sum(1 for n in rejected_notes if "edge ditolak" in n),
        },
    }
    if error:
        report["error"] = error
    return report


def _count_by_type(accepted: GraphDelta) -> dict:
    out: dict[str, int] = {}
    for c in accepted.claims:
        out[c.type] = out.get(c.type, 0) + 1
    return out
