"""LIVE navigation context for the Revenue plugin — Question Planner input mid-conversation.

internal-docs §25. Before M4 a Possible Path only formed at finalize
(`synthesize`). The planner needs that context EVERY turn, so this module derives a PROVISIONAL
PathSet from the current conversation state with the SAME deterministic path as diagnosis,
without an LLM:

    evidence + goal + Universal State graph -> RevenueState (same derivation as diagnosis)
    evidence -> detected mechanisms (catalog keywords)
    evidence + USER transcript -> tier-1 KB rules (deterministic predicates; tier-2 = LLM, at diagnosis)
    -> `build_possible_paths` (generic generator/evaluator; 0..N paths)

Two honesty invariants:
  - PROVISIONAL: without tier-2 rules (which need an LLM), candidates that rest on such rules only
    appear at diagnosis. The planner does not wait; diagnosis can find more, not less than the facts.
  - The transcript read is USER speech only. The engine's own sentences (its questions) are not
    evidence; letting them trigger rules/mechanisms would mean the question proves its own answer.

Injectors for the planner input assembler (`core/navigation/planner_input.py`) also live here:
check signal ids (PathSet does not store signal ids), whether a signal can be answered through
conversation, and the 'not yet known' sentence per signal. All of it is read from the existing
Revenue plugin — no new lists."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.navigation.planner import ACT, ASK
from core.schema.evidence import EvidenceItem
from core.stages.knowledge_rules import KnowledgeRuleOutcome, match_tier1
from core.stages.mechanisms import detect_mechanisms
from core.stages.rule_support import strip_historical_anchors
from domains.revenue.navigation.paths import build_possible_paths
from domains.revenue.navigation.signals import RevenueSignals, unmeasured_signal_ids
from domains.revenue.navigation.space import revenue_space
from domains.revenue.projection.view import apply_view, build_revenue_view
from domains.revenue.schema.goal import Goal
from domains.revenue.schema.state import RevenueState
from domains.revenue.stages.state import build_revenue_state
from ontology.route.strategies import active_template_library


def user_transcript(transcript: Sequence[tuple[str, str]]) -> str:
    """USER speech only. Engine sentences are not evidence (they must not prove their own answer)."""
    return "\n".join(f"user: {text}" for role, text in transcript if role == "user")


def derive_revenue_state(
    evidence: list[EvidenceItem], goal_text: str, transcript: str, graph: Mapping[str, Any] | None,
    historical_evidence: list[EvidenceItem] | None = None,
) -> RevenueState:
    """RevenueState derivation IDENTICAL to diagnosis (one reality): regex/ledger then the graph view (M3)."""
    rs = build_revenue_state(evidence, goal_text, transcript=transcript,
                             graph=dict(graph) if graph else None,
                             historical_evidence=historical_evidence)
    if graph and (graph.get("nodes") or {}):
        try:
            apply_view(rs, build_revenue_view(dict(graph)))
        except Exception:
            pass  # view failed -> the ledger result is still used (diagnosis behavior)
    return rs


def provisional_path_set(
    evidence: list[EvidenceItem],
    goal_text: str,
    transcript: Sequence[tuple[str, str]],
    graph: Mapping[str, Any] | None,
    path_states: Mapping[str, dict] | None = None,
    goal: Mapping[str, Any] | Goal | None = None,
    historical_evidence: list[EvidenceItem] | None = None,
    ledger_state_of: Any = None,
) -> dict[str, Any]:
    """PathSet (0..N) over the current conversation state. Deterministic, zero LLM.

    Goal-Relative (int 09): the session's structured Goal (session.goal dict) is evaluated too -
    the Goal gate uses its metric semantics, not the presence of a revenue number (GR-12)."""
    utext = user_transcript(transcript)
    rs = derive_revenue_state(evidence, goal_text, utext, graph, historical_evidence=historical_evidence)
    outcome = KnowledgeRuleOutcome()
    _t1 = match_tier1(evidence, utext)
    if historical_evidence:
        # DCP-01/03: align the provisional anchor basis with deep synthesis — quotes from
        # superseded claims must not light up current-state rules (divergence without basis). A
        # MIXED quote carrying active facts is kept (14 Oct 2026 audit).
        for _m in _t1:
            if getattr(_m, "matched", False):
                _m.support = strip_historical_anchors(_m.support, historical_evidence, evidence)
    outcome.matches.extend(_t1)
    return build_possible_paths(
        rs,
        None,
        mechanisms=detect_mechanisms(evidence),
        active_rules=outcome.rule_supports(),
        path_states=dict(path_states) if path_states else None,
        goal=goal,
        ledger_state_of=ledger_state_of,
    )


# ───────────────────────── injectors for the planner input assembler ─────────────────────────
def check_signal_map() -> dict[tuple[str, str], str]:
    """(strategy_id | direction, check_id) -> check signal id, read from the Revenue possibility space."""
    space = revenue_space()
    out: dict[tuple[str, str], str] = {}
    for s in space.strategies:
        for c in s.checks:
            out[(s.strategy_id, c.check_id)] = c.signal
    for p in space.patterns:
        for c in p.checks:
            out[(p.direction, c.check_id)] = c.signal
    return out


def signal_of() -> Any:
    table = check_signal_map()
    return lambda strategy_id, check_id: table.get((strategy_id, check_id))


def resolvable(signal_id: str) -> str:
    """ASK if conversation can shift the signal; ACT if the signal is always unmeasurable from state
    (measurement in the real world first). Apart from the unmeasurable ones, every `state:` signal
    can be read from the user's statements."""
    return ACT if signal_id in unmeasured_signal_ids() else ASK


def signal_text(signal_id: str) -> dict[str, str]:
    """The 'not yet known' sentence for a signal: from the signal reader on an EMPTY state
    (all unmeasured)."""
    sig = RevenueSignals(RevenueState())(signal_id)
    out = dict(sig.i18n)
    out["id"] = sig.reason
    return out


def template_requirements() -> dict[str, list[str]]:
    """{template_id: [requirement_id...]} — requirements from templates that were never
    instantiated (NOT_APPLICABLE)."""
    return {
        t["template_id"]: [nc["resolves"][0] for nc in t["node_candidates"] if nc.get("resolves")]
        for t in active_template_library()
    }
