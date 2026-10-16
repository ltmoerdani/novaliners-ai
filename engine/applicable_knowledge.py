"""APPLIED knowledge retrieval for reasoning (int 16 §R5-A) — bounded, sourced, traceable menu.

Knowledge (KB rules) is a LENS for interpreting user state, not a claim about the user. This
retrieval:
  - tier-1 (deterministic, anchored): rules whose predicate evaluator matches the evidence/statements
  - lexical: judgment-tier rules whose `matcher_hint` overlaps the WORDS of active claims
    (anchor = claim id)
  - probe (CIR-02, int 19 §8): KB diagnostic probes selected STATE-RELATIVE (word overlap with
    active claims), WITHOUT an interview phase — carrying on the pre-M4 `format_probe_hints`
    capability through the same substrate.
Rule: a rule/probe WITHOUT an anchor to an active claim does not enter the menu (untraceable =
unusable); knowledge does not create evidence (KNOW-02). The menu is bounded (`MENU_CAP`) and
carries the KB version (`kb_version`) so decisions can be explained against the knowledge
snapshot used.

Probe vs rule (int 19 §8.2): a rule interprets WHETHER evidence satisfies a condition; a probe
suggests a valuable QUESTION/discrimination method. Menu slots are set aside (`PROBE_CAP`) so
diagnostic guidance actually reaches the reasoner prompt (CIR-G02) — a conscious trade-off:
2 of 8 menu slots.
"""
from __future__ import annotations

import re
from typing import Any

# 8 → 12 (16 Oct 2026, session 7989259580af): the model cited HG-R04/LC-P01/SP-P03 which ARE in the
# KB but never entered the 8-slot menu → G9 (correctly) dropped an evidenced hypothesis
# because the refs were not sent to the prompt (int 19 §8.5: referenced ⊆ delivered). Widened the
MENU_CAP = 12
PROBE_CAP = 2          # dedicated menu slot for diagnostic probes (CIR-02; the total menu stays MENU_CAP)
_STOP = frozenset(
    "yang dan di ke dari untuk dengan atau ini itu ada tidak saya anda user the a an of to in is are as be by on "
    "for with that this it its at from not no if when then they their which who has have had will would can could "
    "about into over than also more most other some such only own same so too very just".split())
_TOK = re.compile(r"[a-zA-Z]{4,}")


def _tokens(text: str) -> set[str]:
    return {w for w in (m.group(0).lower() for m in _TOK.finditer(text or "")) if w not in _STOP}


def _probe_menu(nodes: list[dict], cap: int) -> list[dict]:
    """STATE-RELATIVE diagnostic probe: word overlap probe ↔ active claims (anchor = claim id).

    Selector = user state (verbatim active claims), NOT the interview phase (int 19 §8.3 — M5 removed
    phase consumers; this is the replacement of its delivery path). A probe without an active-claim
    anchor does not enter."""
    from engine.knowledge import get_kb

    claim_tokens = {n["id"]: _tokens(n.get("verbatim") or "") for n in nodes}
    items: dict[str, dict[str, Any]] = {}
    for pid, p in (get_kb().get("probes") or {}).items():
        sig = _tokens(p.get("text") or "") | _tokens(
            str(((p.get("signal_interpretation") or {}).get("positive")) or ""))
        if not sig:
            continue
        hit = {cid: len(sig & toks) for cid, toks in claim_tokens.items() if len(sig & toks) >= 2}
        if hit:
            items[pid] = {"id": pid, "anchors": sorted(hit), "score": sum(hit.values())}
    ranked = sorted(items.values(), key=lambda x: (-x["score"], x["id"]))[:cap]
    menu = []
    for x in ranked:
        p = (get_kb().get("probes") or {})[x["id"]]
        interp = p.get("signal_interpretation") or {}
        menu.append({
            "id": x["id"],
            "kind": "probe",
            "source": (p.get("provenance") or {}).get("source_id") or x["id"].split("-")[0],
            "principle": (interp.get("positive") or "")[:220],
            "applies_when": (p.get("text") or "")[:220],
            "basis": "probe_state_overlap",
            "anchors": x["anchors"][:6],
        })
    return menu


def retrieve(evidence: list, graph: dict, transcript_user_text: str, *, cap: int = MENU_CAP) -> dict[str, Any]:
    from core.stages.knowledge_rules import candidate_rules, match_tier1
    from engine.knowledge import kb_sha256

    nodes = [n for n in (graph.get("nodes") or {}).values() if (n.get("status") or "active") == "active"]
    claim_tokens = {n["id"]: _tokens(n.get("verbatim") or "") for n in nodes}
    items: dict[str, dict[str, Any]] = {}

    rules = {r["rule_id"]: r for r in candidate_rules()}
    ev_to_claim = {e.id: e.claim_id for e in evidence if getattr(e, "claim_id", "")}
    for m in match_tier1(evidence, transcript_user_text):
        if not m.matched or m.rule_id not in rules:
            continue
        anchors = sorted({ev_to_claim[c] for c in (m.applied_to or "").split(", ") if c in ev_to_claim})
        if not anchors:
            continue
        r = rules[m.rule_id]
        items[m.rule_id] = {"id": m.rule_id, "basis": "tier1_anchored", "anchors": anchors,
                            "score": 100 + len(anchors)}

    for rid, r in rules.items():
        if rid in items:
            continue
        hint = _tokens(r.get("matcher_hint") or r.get("condition") or "")
        if not hint:
            continue
        hit = {cid: len(hint & toks) for cid, toks in claim_tokens.items() if len(hint & toks) >= 2}
        if hit:
            items[rid] = {"id": rid, "basis": "lexical_overlap", "anchors": sorted(hit),
                          "score": sum(hit.values())}

    # CIR-02: set aside probe slots (total menu stays MENU_CAP) — diagnostic guidance is guaranteed.
    probes = _probe_menu(nodes, PROBE_CAP)
    rule_cap = cap - len(probes)
    ranked = sorted(items.values(), key=lambda x: (-x["score"], x["id"]))[:rule_cap]
    menu = []
    for x in ranked:
        r = rules[x["id"]]
        menu.append({
            "id": x["id"],
            "kind": "rule",
            "source": (r.get("provenance") or {}).get("source_id") or x["id"].split("-")[0],
            "principle": ((r.get("consequence") or {}).get("rationale") or "")[:220],
            "applies_when": (r.get("matcher_hint") or r.get("condition") or "")[:220],
            "basis": x["basis"],
            "anchors": x["anchors"][:6],
        })
    return {"kb_version": kb_sha256(), "menu": menu + probes, "considered": len(items)}
