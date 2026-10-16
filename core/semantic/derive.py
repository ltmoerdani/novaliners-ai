"""Non-authoritative derivations from semantic observation for legacy consumers (R3, compatibility).

The evidence ledger, number_claims, and intent_tags are NOW derived from the canonical claims produced by the
observation commit — not from a second LLM extraction path. This module does NOT reinterpret;
it only projects the data shape for existing consumers (live adjudication,
RevenueState, UI panel). Domain consumers will switch directly to the graph in R4.
"""
from __future__ import annotations

from typing import Any

_UNIT_TO_JUTA = {
    "juta": 1.0, "jt": 1.0, "juta/bulan": 1.0, "million": 1.0, "m": 1.0,
    "ribu": 0.001, "rb": 0.001, "k": 0.001, "ribu/bulan": 0.001,
}

# Claim roles that are NOT state evidence: assumption = the user's hypothesis; desire = aspiration.
# Both are still recognized & stored (graph), but must not satisfy a requirement lexically.
NON_STATE_ROLES = frozenset({"assumption", "desire"})

_PERIOD_OK = {"monthly", "one_off", "annual", "per_project", "hourly", "count", "weekly", "daily"}


def _statement_text(claim: dict) -> str:
    """A short sentence that is easy for adjudication to match: subject + predicate + object/value."""
    t = claim.get("triple") or {}
    subj = (t.get("subject") or {}).get("label") or ""
    pred = (t.get("predicate") or {}).get("label") or ""
    obj = (t.get("object") or {}).get("label")
    qty = claim.get("quantity")
    if isinstance(qty, dict) and qty.get("value_kind") == "range":
        val = f"{qty.get('low')} sampai {qty.get('high')} {qty.get('unit', '')}".strip()
    elif isinstance(qty, dict) and qty.get("value") is not None:
        val = f"{qty.get('value')} {qty.get('unit', '')}".strip()
    elif t.get("value") is not None:
        val = f"{t.get('value')} {t.get('unit') or ''}".strip()
    else:
        val = ""
    parts = [p for p in (subj, pred, obj, val) if p]
    return " ".join(parts) if parts else (claim.get("verbatim") or "")[:160]


def _gap_markers(text: str) -> bool:
    return any(m in text.lower() for m in (
        "tidak dijawab", "belum dijawab", "tidak diketahui", "tidak ada datanya",
        "belum ada data", "tidak pernah dicatat", "belum diukur", "tidak diukur",
        "tidak ada angka", "belum ada angka",
    ))


def evidence_from_commit(commit_result) -> list[dict]:
    """Canonical claim -> EvidenceItem proposal (dict shape; the caller instantiates).

    signal = short statement; source_quote = verbatim event (anchor); level from
    epistemic; is_gap for the gap role; topic = role (display label).
    """
    out: list[dict] = []
    for c in commit_result.accepted_claims:
        if (c.get("status") or "active") != "active":
            continue
        # signal uses the USER'S WORDS (verbatim) — not an engine paraphrase: adjudication
        # and mechanism detection read the user's language; statement is only a fallback.
        quote = (c.get("verbatim") or "").strip()
        text = quote or _statement_text(c)
        out.append({
            "id": "",
            "claim_id": c.get("id") or "",
            "event_id": (c.get("provenance") or {}).get("event_id") or "",
            "claim_role": c.get("type") or "",
            "epistemic": c.get("epistemic") or "",
            "admissible": c.get("type") not in NON_STATE_ROLES,
            "inadmissible_reason": (f"role_not_state_evidence:{c.get('type')}"
                                    if c.get("type") in NON_STATE_ROLES else ""),
            "signal": text,
            # user testimony (including "measured") is NOT equivalent to independent transactional evidence
            # (int 16 §F-06): level promotion only through real adjudication/evidence paths.
            "level": "self_reported",
            "source_quote": quote,
            "topic": (c.get("type") or "claim").upper(),
            "is_gap": c.get("type") == "gap" or _gap_markers(quote),
        })
    return out


_ROLE_TO_TAG = {
    "goal": "GOAL", "desire": "GOAL", "assumption": "ASSUMPTION",
    "event": "FACT", "claim": "FACT", "gap": "FACT",
}


def intent_tags_from_commit(commit_result) -> list[dict]:
    out = []
    for c in commit_result.accepted_claims:
        if (c.get("status") or "active") != "active":
            continue
        kind = "PREFERENCE" if c.get("aspect") == "preference" else _ROLE_TO_TAG.get(c.get("type"), "FACT")
        out.append({
            "kind": kind,
            "quote": c.get("verbatim") or "",
            "normalized": _statement_text(c),
            "confidence": (0.6 if c.get("hedge") or c.get("epistemic") == "estimated" else 0.85),
        })
    return out


def number_claims_from_commit(commit_result, role_mapper=None) -> list[dict]:
    """Quantified claim -> NumberClaim (compat). Values are normalized to MILLIONS when the unit is known.

    Mapping the semantic ROLE (target/current/historical) is the DOMAIN's business — core
    does not contain that vocabulary (guard K2). The caller injects a role_mapper
    (domain); without a mapper, the neutral role "other" (the final consumer still uses the graph
    view; the full bridge is in R4). Unknown unit -> skipped (not a guess).
    """
    out: list[dict] = []
    for c in commit_result.accepted_claims:
        if (c.get("status") or "active") != "active":
            continue
        q = c.get("quantity")
        if not isinstance(q, dict):
            continue
        unit = (q.get("unit") or "").lower().strip()
        mult = None
        head = unit.split("/")[0].split()[0] if unit else ""   # per word: 'klien' is not a currency unit
        if head in _UNIT_TO_JUTA:
            mult = _UNIT_TO_JUTA[head]
        if mult is None:
            continue
        # The legacy NumberClaim holds only ONE value. Ranges and bounds (<, <=, >, >=) cannot
        # be stated honestly as a single number -> not projected (not a midpoint
        # / ordinary value). The full meaning stays in the canonical graph; domain consumers read it in R4.
        if q.get("value_kind") not in ("exact", "approximate"):
            continue
        val = q.get("value")
        if val is None:
            continue
        tense = ("future" if c.get("tense") == "future"
                 else "past" if c.get("tense") == "past" else "now")
        role = (role_mapper(claim=c) if role_mapper is not None else "other")
        period = q.get("period") if q.get("period") in _PERIOD_OK else "one_off"
        out.append({
            "value": round(float(val) * mult, 2),
            "period": period,
            "tense": tense,
            "role": role,
            "subject": ((c.get("triple") or {}).get("subject") or {}).get("label"),
            "verbatim": c.get("verbatim") or "",
            "hedge": bool(c.get("hedge") or q.get("value_kind") == "approximate"),
        })
    return out


def extraction_payload(commit_result, number_role_mapper=None) -> dict[str, Any]:
    """Equivalent shape of TurnExtraction.model_dump() for the legacy consumer path."""
    return {
        "intent_tags": intent_tags_from_commit(commit_result),
        "evidence": evidence_from_commit(commit_result),
        "number_claims": number_claims_from_commit(commit_result, role_mapper=number_role_mapper),
    }
