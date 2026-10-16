"""Competing-hypothesis management (int 16 §R5-B) — deterministic, sourced, revisable.

A hypothesis = a candidate explanation of the user's situation. NOT a user claim, NOT a fact, NOT a requirement status.
It lives in `session.hypotheses` and always carries:
  - support / contradiction: canonical (active) claim ids — an audit trail to the user's words
  - evidence that is still missing (missing_evidence)
  - knowledge references (knowledge_refs) — only ids present in the KB and included in the retrieved menu
  - revision history: when, because of which claim/event, what changed

`standing` is computed DETERMINISTICALLY from ACTIVE support/contradiction, with no numeric score:
  unsupported  : no active support
  tentative    : 1 active support (or support from a single event only)
  supported    : >= 2 active supports from >= 2 different events, with no active contradiction
  contested    : there is an active contradicting claim
No standing states proven CAUSALITY; "supported" means supported by the user's words, not
proven cause.
"""
from __future__ import annotations

import hashlib
from typing import Any

ST_UNSUPPORTED, ST_TENTATIVE, ST_SUPPORTED, ST_CONTESTED = "unsupported", "tentative", "supported", "contested"
STATUS_ACTIVE, STATUS_WEAKENED, STATUS_RETIRED = "active", "weakened", "retired"

_MAX_HYPOTHESES = 12


def _active_claims(graph: dict) -> dict[str, dict]:
    return {cid: n for cid, n in (graph.get("nodes") or {}).items()
            if (n.get("status") or "active") == "active"}


def _event_of(graph: dict, cid: str) -> str:
    return ((graph.get("nodes") or {}).get(cid) or {}).get("provenance", {}).get("event_id", "")


def standing_of(h: dict, graph: dict) -> str:
    active = _active_claims(graph)
    sup = [c for c in h.get("supports") or [] if c in active]
    con = [c for c in h.get("contradicts") or [] if c in active]
    if con:
        return ST_CONTESTED
    if not sup:
        return ST_UNSUPPORTED
    if len(sup) >= 2 and len({_event_of(graph, c) for c in sup}) >= 2:
        return ST_SUPPORTED
    return ST_TENTATIVE


def hypothesis_id(statement: str) -> str:
    return "hyp-" + hashlib.sha1(" ".join(statement.lower().split()).encode()).hexdigest()[:8]


def validate_proposals(
    proposals: list, graph: dict, knowledge_ids: set[str], existing: dict
) -> tuple[list[dict], list[str]]:
    """Model proposal -> valid hypotheses + violations. References must be real; those without active support are rejected
    (a hypothesis with no trace to the user's words is fabrication)."""
    active = _active_claims(graph)
    ok: list[dict] = []
    bad: list[str] = []
    for p in proposals or []:
        sup = [c for c in p.supports if c in active]
        con = [c for c in p.contradicts if c in active]
        miss = [c for c in p.supports + p.contradicts if c not in active]
        if miss:
            bad.append(f"hipotesis '{p.statement[:40]}': rujukan klaim tak aktif/tak ada: {miss}")
            continue
        if not sup:
            bad.append(f"hipotesis '{p.statement[:40]}': tanpa dukungan klaim aktif")
            continue
        unk = [k for k in p.knowledge_refs if k not in knowledge_ids]
        if unk:
            bad.append(f"hipotesis '{p.statement[:40]}': knowledge_refs tak terambil/tak ada: {unk}")
            continue
        hid = p.id if p.id and p.id in existing else hypothesis_id(p.statement)
        ok.append({"id": hid, "statement": p.statement.strip(), "supports": sup, "contradicts": con,
                   "missing_evidence": list(p.missing_evidence), "knowledge_refs": list(p.knowledge_refs)})
    return ok, bad


def apply_proposals(s: Any, valid: list[dict], event_id: str) -> list[dict]:
    """Apply valid hypotheses to `s.hypotheses` (upsert + history). Returns the changes for audit."""
    store: dict = getattr(s, "hypotheses", None)
    if store is None:
        store = {}
        s.hypotheses = store
    changes: list[dict] = []
    for h in valid:
        cur = store.get(h["id"])
        if cur is None:
            if len(store) >= _MAX_HYPOTHESES:
                continue
            rec = {**h, "status": STATUS_ACTIVE, "created_event": event_id, "history": [
                {"event_id": event_id, "change": "created", "claims": h["supports"] + h["contradicts"]}]}
            rec["standing"] = standing_of(rec, s.state_graph)
            store[h["id"]] = rec
            changes.append({"id": h["id"], "change": "created"})
            continue
        before = (tuple(cur["supports"]), tuple(cur["contradicts"]), tuple(cur["missing_evidence"]))
        cur["supports"] = sorted(set(cur["supports"]) | set(h["supports"]))
        cur["contradicts"] = sorted(set(cur["contradicts"]) | set(h["contradicts"]))
        cur["missing_evidence"] = h["missing_evidence"] or cur["missing_evidence"]
        cur["knowledge_refs"] = sorted(set(cur["knowledge_refs"]) | set(h["knowledge_refs"]))
        after = (tuple(cur["supports"]), tuple(cur["contradicts"]), tuple(cur["missing_evidence"]))
        if before != after:
            cur["history"].append({"event_id": event_id, "change": "updated",
                                   "claims": sorted(set(h["supports"]) | set(h["contradicts"]))})
            changes.append({"id": h["id"], "change": "updated"})
        cur["standing"] = standing_of(cur, s.state_graph)
    return changes


def reconcile(s: Any, event_id: str = "") -> list[dict]:
    """After state changes (correction/negation/new claim): refresh standing and trail. Supporting claims that
    are now inactive are RELEASED from `supports` (history records the cause); a hypothesis without active support
    becomes `weakened`, and retired if it was already weak before and remains unsupported."""
    store: dict = getattr(s, "hypotheses", None) or {}
    graph = s.state_graph or {}
    nodes = graph.get("nodes") or {}
    changes: list[dict] = []
    for hid, h in store.items():
        if h.get("status") == STATUS_RETIRED:
            continue
        lost = [c for c in h["supports"] if (nodes.get(c) or {}).get("status", "active") != "active"]
        gone_con = [c for c in h["contradicts"] if (nodes.get(c) or {}).get("status", "active") != "active"]
        if lost:
            h["supports"] = [c for c in h["supports"] if c not in lost]
            h["history"].append({"event_id": event_id, "change": "support_lost", "claims": lost,
                                 "caused_by": [nodes[c].get("superseded_by") for c in lost if c in nodes]})
            changes.append({"id": hid, "change": "support_lost", "claims": lost})
        if gone_con:
            h["contradicts"] = [c for c in h["contradicts"] if c not in gone_con]
            h["history"].append({"event_id": event_id, "change": "contradiction_resolved", "claims": gone_con})
            changes.append({"id": hid, "change": "contradiction_resolved", "claims": gone_con})
        h["standing"] = standing_of(h, graph)
        if h["standing"] == ST_UNSUPPORTED:
            new = STATUS_RETIRED if h.get("status") == STATUS_WEAKENED else STATUS_WEAKENED
            if h.get("status") != new:
                h["status"] = new
                h["history"].append({"event_id": event_id, "change": f"status_{new}"})
                changes.append({"id": hid, "change": f"status_{new}"})
        elif h.get("status") == STATUS_WEAKENED:
            h["status"] = STATUS_ACTIVE
    return changes
