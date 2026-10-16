"""Uncertainty candidates from planner input (int 16 §R5-A) — CANDIDATE SOURCE, not a selector.

The set of "what is still unknown and can be asked" is assembled by USING the m4.v1 planner itself,
without duplicating its logic: the planner is called repeatedly on the same input; each time it picks one need,
that need is marked "already asked ASK_CAP times" and the planner is called again, until it no longer picks
QUESTION/EVIDENCE_REQUEST. The result is ALL askable needs (goal, applicability, state per
requirement/check, contradictions, path-maker facts), in a deterministic information-policy order — that order
is NOT business priority and the model is free to choose another (the guard only checks legality).
"""
from __future__ import annotations

import copy
from typing import Any, Mapping

from core.navigation.planner import ASK_CAP, KIND_EVIDENCE, KIND_QUESTION, plan_next_move
from core.navigation.planner_text import render_move
from core.reasoning.contract import MAX_UNCERTAINTY_CANDIDATES

# One canonical limit (see `contract.MAX_UNCERTAINTY_CANDIDATES`): the list capacity in the `nm.v2` contract must
# always be >= the number of candidates that can be assembled here, otherwise askable candidates can be entirely unrepresented.
_MAX_CANDIDATES = MAX_UNCERTAINTY_CANDIDATES


def candidate_uncertainties(inp: Mapping[str, Any]) -> list[dict[str, Any]]:
    work = copy.deepcopy(dict(inp))
    hist = work.setdefault("history", {})
    asked = dict(hist.get("asked") or {})
    original = dict(asked)
    hist["asked"] = asked
    lang = work.get("lang") or "en"
    out: list[dict[str, Any]] = []
    for _ in range(_MAX_CANDIDATES):
        d = plan_next_move(work)
        if d["kind"] not in (KIND_QUESTION, KIND_EVIDENCE):
            break
        nid = (d.get("reason") or {}).get("need_id")
        if not nid or any(u["id"] == nid for u in out):
            break
        try:
            r = render_move(d, work, lang)
            label = r.get("headline") or r.get("text") or nid
            wording = r.get("text") or ""
        except Exception:  # noqa: BLE001 - label is display only; the candidate remains valid
            label, wording = nid, ""
        out.append({
            "id": nid, "kind": (d.get("reason") or {}).get("stage", "").lower() or "need",
            "focus": d.get("focus"), "label": label, "asked": int(original.get(nid, 0)),
            "askable": True, "needed_by": len(d.get("contexts") or []),
            # step-shape suggestion: a need that was asked before is escalated into an evidence request (planner m4.v1)
            "suggested_kind": d["kind"],
            # wording suggestion from the old renderer: the model MAY ignore it (display compat & degradation)
            "legacy_wording": wording,
            # planner trail for this need (NOT sent to the model; dropped by public_view)
            "_reason": d.get("reason"),
        })
        asked[nid] = ASK_CAP     # mark as exhausted so the planner surfaces the next need
    return out


def public_view(uncertainties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The part of the candidate that may be sent to the model/hashed: keys prefixed with `_` are internal trails."""
    return [{k: v for k, v in u.items() if not k.startswith("_")} for u in uncertainties]
