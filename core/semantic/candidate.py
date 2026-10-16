"""EvidenceCandidate — bridge from canonical claim -> requirement (int 16 §R4-D). NOT a status authority.

Three states that are NOT equivalent and are recorded separately:
  1. RECOGNIZED  — the claim is semantically understood (present in the graph, or has no
                   requirement proposal at all).
  2. ADMISSIBLE  — the evidence may enter adjudication for a specific requirement
                   (admissibility gate + verification).
  3. SATISFYING  — the requirement is truly satisfied: ONLY the result of the formal
                   adjudicator (ledger), never determined here.

This module only records deterministic provenance per (evidence, requirement); it does not
call an LLM and does not write the ledger. Domain vocabulary is absent here (guard K2).
"""
from __future__ import annotations

from typing import Any

CANDIDATE_VERSION = "ec.v1"

V_ADMITTED = "ADMITTED"                  # passes two-gate verification; may be counted by the adjudicator
V_NOT_ADMISSIBLE = "NOT_ADMISSIBLE"      # rejected by the admissibility gate (not state evidence, gap)
V_UNRESOLVED = "UNRESOLVED"              # proposed but verification did not pass (reason = reason_code)
V_RECOGNIZED_ONLY = "RECOGNIZED_ONLY"    # understood; no requirement can be proposed


def candidate_record(
    ev: Any,
    *,
    requirement_id: str,
    verdict: str,
    reason: str,
    mapping_rule: str,
    goal: dict | None = None,
    session_id: str = "",
    user_id: str = "",
    graph: dict | None = None,
) -> dict[str, Any]:
    node = ((graph or {}).get("nodes") or {}).get(getattr(ev, "claim_id", "") or "") or {}
    return {
        "candidate_version": CANDIDATE_VERSION,
        "canonical_claim_id": getattr(ev, "claim_id", "") or "",
        "source_event_id": getattr(ev, "event_id", "") or "",
        "source_quote": getattr(ev, "source_quote", None) or "",
        "scope": {"session_id": session_id, "user_id": user_id},
        "goal_id": (goal or {}).get("goal_id", ""),
        "goal_version": (goal or {}).get("version"),
        "semantic_role": getattr(ev, "claim_role", "") or node.get("type", ""),
        "aspect": node.get("aspect", ""),
        "epistemic_grade": getattr(ev, "epistemic", "") or node.get("epistemic", ""),
        "evidence_level": getattr(ev, "level", ""),
        "quantity": node.get("quantity"),
        "claim_status": node.get("status", "active"),
        "evidence_id": getattr(ev, "id", ""),
        "requirement_id": requirement_id,
        "mapping_rule": mapping_rule,
        "admissibility_verdict": verdict,
        "reason": reason,
    }
