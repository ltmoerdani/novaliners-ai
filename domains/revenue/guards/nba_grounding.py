"""Guard: NBA grounding to the knowledge base (internal-docs §6.2, layer guards).

RDKL contract (internal-docs §1): intervention selection belongs to the KB
(deterministic), contextualization belongs to the LLM. This guard verifies that the Next Best
Action proposed by the draft is LINKED to an active KB intervention — the same pattern
as guards/population.py (registry check) + _resolve_evidence_map (validate → fallback →
explicit flag; never fabrication).

0 LLM. Does not touch confidence — grounding is not epistemic proof (F7).
"""
from __future__ import annotations

import re

# Type note: `draft` is DiagnosisDraft-like (duck-typed) from the
# agents.diagnosis module — only the grounded_intervention_id/next_best_action/
# first_step_today/day_by_day fields are read. `menu` and `kb_interventions_final`
# are list[dict] from engine.knowledge.interventions_for() (+ the
# for_constraint key) — duck-typed, no schema import (keeps the layer contract).


def _iv_id(iv: dict) -> str:
    return str(iv.get("intervention_id", "") or "")


def _action_text(draft) -> str:
    # J1 (internal-docs): day_by_day is now list[ActionItem] (attr .text) or legacy str.
    day_by_day = [str(getattr(x, "text", x)) for x in (getattr(draft, "day_by_day", []) or [])]
    parts = [
        getattr(draft, "next_best_action", "") or "",
        getattr(draft, "first_step_today", "") or "",
        day_by_day[0] if day_by_day else "",
    ]
    return " ".join(p for p in parts if p)


def _name_tokens(name: str) -> list[str]:
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "your", "into",
        "session", "practice", "review", "plan",
    }
    return [
        t for t in re.findall(r"[a-zA-Z]{5,}", name.lower())
        if t not in stop
    ]


def guard_nba_grounding(draft, menu: list[dict], kb_interventions_final: list[dict]) -> dict:
    """Verifikasi deterministik linkage NBA ↔ intervention KB.

    Return dict {status, claimed_id, matched_via, intervention_ids,
    alternative_id, alternative_name, expected_evidence, for_constraint}.
    Status: GROUNDED / PARTIAL / UNGROUNDED / NO_FIT / NO_KB_SCOPE.
    """
    primary = (getattr(draft, "primary_constraint_id", "") or "").strip().upper()

    # Exit pass-with-reason: the ontology rejects it → do not force the KB
    # (internal-docs §8.4).
    if primary == "NO_FIT":
        return {"status": "NO_FIT", "claimed_id": "", "matched_via": "exit",
                "intervention_ids": [], "alternative_id": "", "alternative_name": "",
                "expected_evidence": "", "for_constraint": ""}

    scope: list[dict] = []
    seen: set[str] = set()
    for iv in list(kb_interventions_final) + list(menu):
        iid = _iv_id(iv)
        if iid and iid not in seen:
            seen.add(iid)
            scope.append(iv)

    # Exit pass-with-reason: no intervention for any candidate —
    # do not fabricate linkage (P0-2: never manufacture evidence).
    if not scope:
        return {"status": "NO_KB_SCOPE", "claimed_id": "", "matched_via": "exit",
                "intervention_ids": [], "alternative_id": "", "alternative_name": "",
                "expected_evidence": "", "for_constraint": ""}

    scope_ids = {_iv_id(iv) for iv in scope}
    text = _action_text(draft)
    claimed = (getattr(draft, "grounded_intervention_id", "") or "").strip()

    # (1) Explicit valid claim?
    if claimed and claimed in scope_ids:
        return {"status": "GROUNDED", "claimed_id": claimed, "matched_via": "field",
                "intervention_ids": [claimed], "alternative_id": "", "alternative_name": "",
                "expected_evidence": "", "for_constraint": ""}

    # (2) Fallback: the intervention ID is written in the action text ('[TM-I03] ...')
    m = re.search(r"\b([A-Z]{2,3}-I\d{2})\b", text)
    if m and m.group(1) in scope_ids:
        return {"status": "GROUNDED", "claimed_id": m.group(1), "matched_via": "text",
                "intervention_ids": [m.group(1)], "alternative_id": "", "alternative_name": "",
                "expected_evidence": "", "for_constraint": ""}

    # (3) Fallback PARTIAL: the intervention name (significant token) appears in the text
    # action — contextual adaptation without naming the ID.
    text_l = text.lower()
    for iv in scope:
        tokens = _name_tokens(str(iv.get("name", "")))
        if tokens and all(t in text_l for t in tokens[:2]):
            iid = _iv_id(iv)
            return {"status": "PARTIAL", "claimed_id": iid, "matched_via": "name",
                    "intervention_ids": [iid], "alternative_id": "", "alternative_name": "",
                    "expected_evidence": "", "for_constraint": iv.get("for_constraint", "")}

    # (4) UNGROUNDED — explicit flag + grounded alternative for PRIMARY
    # (the first intervention of the final scope; the user still gets a KB-based option).
    alt: dict = {}
    for iv in kb_interventions_final:
        if iv.get("for_constraint") == primary or primary == "":
            alt = iv
            break
    if not alt and kb_interventions_final:
        alt = kb_interventions_final[0]
    return {
        "status": "UNGROUNDED",
        "claimed_id": claimed,
        "matched_via": "none",
        "intervention_ids": [],
        "alternative_id": _iv_id(alt),
        "alternative_name": str(alt.get("name", "")),
        "expected_evidence": str(alt.get("expected_evidence", "")),
        "for_constraint": str(alt.get("for_constraint", "")),
    }
