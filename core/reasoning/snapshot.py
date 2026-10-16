"""Snapshot state for reasoning: SELECTIVE context selection, sourced, with explicit budget limits
(int 16 §R5-E). Not "last N turns": old claims that are still material are still included.

Deterministic and replayable: `snapshot_id` = fingerprint of the content sent to the model.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

DEFAULT_BUDGET_CHARS = 9000     # ~2-3k tokens of claims+exchange; not a turn-count limit
_ALWAYS_ROLES = ("goal", "gap")             # always carried while active
_ALWAYS_ASPECTS = ("constraint", "concern", "conflict", "preference")


def _line(n: dict) -> str:
    t = n.get("triple") or {}
    subj = (t.get("subject") or {}).get("label") or "?"
    pred = (t.get("predicate") or {}).get("label") or "?"
    obj = (t.get("object") or {}).get("label")
    q = n.get("quantity")
    qty = ""
    if isinstance(q, dict):
        if q.get("value_kind") == "range":
            qty = f" [range {q.get('low')}..{q.get('high')} {q.get('unit', '')}]"
        elif q.get("value") is not None:
            qty = f" [{q.get('value_kind')} {q.get('value')} {q.get('unit', '')}]"
    asp = f"/{n['aspect']}" if n.get("aspect") else ""
    return (f"{n.get('id')} [{n.get('type')}{asp}|{n.get('tense')}|{n.get('epistemic')}] "
            f"{subj} {pred}{(' ' + obj) if obj else ''}{qty} — \"{(n.get('verbatim') or '')[:140]}\"")


def select_claims(graph: dict, hypotheses: dict, budget_chars: int = DEFAULT_BUDGET_CHARS) -> tuple[list[dict], dict]:
    """ACTIVE claims carried to the model + selection report (skipped ones are counted, never silently lost)."""
    nodes = [n for n in (graph.get("nodes") or {}).values() if (n.get("status") or "active") == "active"]
    nodes.sort(key=lambda n: str(n.get("id")))
    in_hyp = {c for h in (hypotheses or {}).values() if h.get("status") != "retired"
              for c in (h.get("supports") or []) + (h.get("contradicts") or [])}
    edges = (graph.get("edges") or {}).values()
    in_conflict = {x for e in edges if e.get("kind") == "contradicts" for x in (e.get("src"), e.get("dst"))}

    def priority(n: dict) -> int:
        if n.get("id") in in_conflict:
            return 0
        if n.get("type") in _ALWAYS_ROLES or n.get("aspect") in _ALWAYS_ASPECTS:
            return 1
        if n.get("id") in in_hyp:
            return 2
        return 3

    # within one priority: the NEWEST first (lexicographically ordered ids = event order)
    ranked = sorted(nodes, key=lambda n: str(n.get("id")), reverse=True)
    ranked.sort(key=priority)   # stable: newest-first order is preserved within each priority
    chosen: list[dict] = []
    used = 0
    for n in ranked:
        ln = len(_line(n)) + 1
        if used + ln > budget_chars:
            continue
        chosen.append(n)
        used += ln
    chosen.sort(key=lambda n: str(n.get("id")))
    report = {"active_total": len(nodes), "included": len(chosen), "omitted": len(nodes) - len(chosen),
              "budget_chars": budget_chars, "used_chars": used}
    return chosen, report


def build_snapshot(
    *,
    graph: dict,
    goal: dict | None,
    transcript: list,
    hypotheses: dict,
    uncertainties: list[dict],
    knowledge: list[dict],
    requirement_states: dict,
    moves: list | None = None,
    paths: list | None = None,
    hint: dict | None = None,
    recent_pairs: int = 4,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
) -> dict[str, Any]:
    claims, sel = select_claims(graph, hypotheses, budget_chars)
    tail = [(r, t) for r, t in transcript][-(recent_pairs * 2):]
    body = {
        # generic serialization: any scalar Goal field, without domain vocabulary (guard K2)
        "goal": {k: v for k, v in sorted((goal or {}).items())
                 if isinstance(v, (str, int, float, bool)) and v not in ("", None)
                 and k not in ("workspace_id", "notes", "status", "effective_ts")},
        "claims": [_line(n) for n in claims],
        "claim_ids": [n["id"] for n in claims],
        "selection": sel,
        "recent_exchange": [{"role": r, "text": (t or "")[:300]} for r, t in tail],
        "hypotheses": [
            {k: h.get(k) for k in ("id", "statement", "status", "standing", "supports", "contradicts",
                                   "missing_evidence", "knowledge_refs")}
            for h in (hypotheses or {}).values() if h.get("status") != "retired"],
        "uncertainties": uncertainties,
        "knowledge": knowledge,
        "requirement_states": requirement_states,
        "moves": list(moves or []),
        "paths": list(paths or []),
        # deterministic candidate-decision hint (kind + old wording): a HINT only, the model is free to differ
        "deterministic_hint": dict(hint or {}),
    }
    blob = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    body["snapshot_id"] = "ss-" + hashlib.sha1(blob.encode()).hexdigest()[:12]
    return body
