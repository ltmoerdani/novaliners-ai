"""Grounded narrative claims: a narrative may INTERPRET the verified state, it must never CREATE it.

A claim is represented as

    Narrative Claim
    ├── claim               the sentence/clause being claimed
    ├── claim_type          SUPPORTED | PARTIAL | MISSING | UNKNOWN | CONFLICT  (what is claimed)
    ├── requirement_anchor  the projection item's key (requirement_id, or check_id when requirementless)
    ├── evidence_anchor     that item's evidence references (ledger:/check:/ev:); empty = no evidence
    └── support_state       the item's state per the projection (PRESENT | PARTIAL | UNKNOWN | ABSENT)

Rules (deterministic, no LLM fact-checker):
  - a claim WITHOUT a requirement anchor is rejected; an anchor absent from that path is rejected;
  - SUPPORTED needs support_state PRESENT AND a non-empty evidence_anchor (not merely "some other PRESENT
  item" existing);
  - MISSING needs ABSENT; PARTIAL needs PARTIAL;
  - UNKNOWN needs UNKNOWN — an UNKNOWN claim must not be spoken as a failure (UNKNOWN != ABSENT), and a
    claim whose anchor is UNKNOWN must not be spoken as SUPPORTED/MISSING;
  - a CONTESTED item (two definite readings in conflict; `settled=False`) may only be claimed CONFLICT —
    the narrative must not state a dispute as settled fact; a CONFLICT claim on an uncontested item is
    rejected.
Violating claims are rejected per claim; narrative fields depending on them are dropped, and the
 deterministic fallback (built from the same items) takes over."""

from __future__ import annotations

from core.navigation.contracts import Satisfaction

CLAIM_TYPES = ("SUPPORTED", "PARTIAL", "MISSING", "UNKNOWN", "CONFLICT")
_REQUIRED_STATE = {
    "SUPPORTED": Satisfaction.PRESENT,
    "PARTIAL": Satisfaction.PARTIAL,
    "MISSING": Satisfaction.ABSENT,
    "UNKNOWN": Satisfaction.UNKNOWN,
}

# Narrative fields that CLAIM a state (their claims must be anchored) — other fields only get the text guard.
STATE_FIELDS = ("supported", "holding", "unclear")


def make_claim(field: str, claim: str, claim_type: str, item: dict) -> dict:
    """An already-resolved claim from an item (used by the deterministic fallback: correct by
    construction)."""
    return {
        "field": field,
        "claim": claim,
        "claim_type": claim_type,
        "requirement_anchor": item["key"],
        "evidence_anchor": list(item.get("evidence") or []),
        "support_state": item["state"],
    }


def ground_claim(raw: dict, path: dict) -> dict:
    """A raw claim (e.g. from the LLM: field, claim, claim_type, requirement) + the path projection -> a
    resolved
    claim with `grounded` and `violation`. Anchors and evidence are ALWAYS taken from the projection,
    never from the raw claim."""
    items = {str(it["key"]): it for it in path.get("items") or []}
    anchor = str(raw.get("requirement") or raw.get("requirement_anchor") or "").strip()
    ctype = str(raw.get("claim_type") or "").strip().upper()
    out = {
        "field": str(raw.get("field") or ""),
        "claim": str(raw.get("claim") or "").strip(),
        "claim_type": ctype,
        "requirement_anchor": anchor,
        "evidence_anchor": [],
        "support_state": "",
        "grounded": False,
        "violation": "",
    }
    if ctype not in CLAIM_TYPES:
        out["violation"] = f"claim_type {ctype!r} tidak dikenal"
        return out
    if not anchor:
        out["violation"] = "klaim tanpa requirement_anchor"
        return out
    item = items.get(anchor)
    if item is None:
        out["violation"] = f"requirement_anchor {anchor!r} tidak ada di path ini"
        return out
    out["evidence_anchor"] = list(item.get("evidence") or [])
    out["support_state"] = item["state"]
    contested = not item.get("settled", True)
    if contested != (ctype == "CONFLICT"):
        out["violation"] = (
            f"klaim {ctype} pada requirement {anchor!r} yang berkonflik — hanya klaim CONFLICT sah"
            if contested
            else f"klaim CONFLICT pada requirement {anchor!r} yang tidak berkonflik"
        )
        return out
    if ctype == "CONFLICT":
        out["grounded"] = True
        return out
    if item["state"] != _REQUIRED_STATE[ctype]:
        out["violation"] = (
            f"klaim {ctype} berjangkar pada requirement {anchor!r} yang keadaannya "
            f"{item['state']} — klaim tidak boleh menciptakan atau membalik keadaan"
        )
        return out
    if ctype == "SUPPORTED" and not out["evidence_anchor"]:
        out["violation"] = f"klaim SUPPORTED pada {anchor!r} tanpa evidence_anchor"
        return out
    out["grounded"] = True
    return out


def check_claims(entry: dict, path: dict) -> dict[str, list[str]]:
    """One path's narrative (text fields + `claims`) -> {field: [violations]}. An empty field is always
    valid.

    A state field (supported/holding/unclear) holding text MUST have at least one grounded claim and must
    not carry any claim that failed to ground. Claims for textually empty fields are ignored."""
    claims = [ground_claim(c, path) for c in (entry.get("claims") or []) if isinstance(c, dict)]
    found: dict[str, list[str]] = {}
    for field in STATE_FIELDS:
        text = str(entry.get(field) or "").strip()
        if not text:
            continue
        mine = [c for c in claims if c["field"] == field]
        problems = [f"{c['violation']}" for c in mine if not c["grounded"]]
        if not mine:
            problems.append(
                f"{field} menyatakan keadaan tetapi tanpa klaim beranjang (requirement + evidence)"
            )
        elif not any(c["grounded"] for c in mine):
            problems.append(f"{field} tidak punya satu pun klaim yang ter-ground")
        if problems:
            found[field] = problems
    return found
