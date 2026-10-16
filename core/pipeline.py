"""Layer 2 — Diagnosis orchestration pipeline (internal-docs §7).

EXPLICIT stage order — this is the only place that defines the deterministic
E2E flow:

    evidence → extract_state → mechanisms → llm_draft → confidence
             → arbitration → causal → opportunities → spectrum → artifact

Note: `llm_draft` stays in agents/diagnosis.py (large prompt) — the pipeline
records it as a stage through TraceReport, it does not move the prompt.
The `paths` stage (Revenue Path Feasibility) is the next slot (P1-4).
"""
from __future__ import annotations

PIPELINE_STAGES = [
    "extract_state",      # evidence → RevenueState (deterministik)
    "validate_state",     # E2 data integrity (BLOCK/FLAG)
    "mechanisms",         # evidence → mechanism clusters
    "llm_draft",          # LLM: DiagnosisDraft (the only nondeterministic stage)
    "confidence.ranking", # evidence_map → hypothesis ranking (deterministik)
    "confidence.overall", # split confidence 3-arah
    "arbitration",        # LLM-vs-engine evidence gate
    "guard.nba_grounding", # internal-docs NBA↔KB linkage (selection belongs to the KB)
    "causal",             # causal hypothesis + attribution split
    "opportunities",      # typed opportunities (+ eligibility invariant)
    "spectrum",           # decision spectrum verdict
    "paths",              # P1-4: Revenue Path Feasibility (internal-docs §10.7)
]
