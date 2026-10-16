"""Readiness narrative grounding contract (internal-docs §10;
internal-docs §Narrative Grounding).

After the LLM writes a narrative, the narrative is checked DETERMINISTICALLY against the
readiness projection verified by the engine — not by an LLM fact checker. A narrative may
INTERPRET a state; it must not INVENT a state.

Two layers:

  1. CLAIM level (core/navigation/claims.py) — replaces the "there is >=1 PRESENT item" count:
     a field stating a state ("supported", "holding", "unclear") must carry an anchored claim
     (claim -> requirement_anchor -> evidence_anchor -> support_state). A SUPPORTED claim is
     valid only if the item it anchors to is PRESENT and has evidence; a claim whose anchor is
     UNKNOWN is rejected; a claim without an anchor is rejected; a claim must not flip the
     item's state. Merely "there is another PRESENT item on this path" is NOT enough.
  2. TEXT level — population/comparison claims ("nobody", "everyone", "most customers",
     "the market wants/rejects", "warmer/better/stronger than ...", "guaranteed",
     "already proven") are rejected unless there is explicit population/comparison evidence in
     the projection; "supported" must not contradict itself; "unclear" must not turn
     "not yet known" into a negative claim (UNKNOWN != ABSENT, UNKNOWN != FALSE): "we have not
     yet seen anyone willing to pay" is allowed, "nobody is willing to pay" is not.

Violations are returned keyed "paths:<KEY>" / "checks:<KEY>" — the same per-item drop mechanism
as the language guard; a violating item is dropped, a deterministic fallback takes over. No
silent repair.
"""
from __future__ import annotations

import re

from core.navigation.claims import check_claims

# population/comparison claim without population/comparison evidence in the projection
# (English + Indonesian — the narrative is written in the user's word language)
_OVERCLAIM = re.compile(
    r"\b(?:nobody|no one|everyone|everybody|most (?:customers|clients|people|buyers|prospects)"
    r"|the market (?:wants|rejects|does not want|doesn't want)|definitely|obviously|clearly|guaranteed"
    r"|already proven|proven to (?:work|sell)"
    r"|than (?:most|others|alternatives|the alternatives|average|the average|anyone(?: else)?)"
    r"|tidak ada yang (?:mau|butuh|ingin|pernah)|semua orang"
    r"|kebanyakan (?:klien|orang|pelanggan|customer)|pasar (?:menolak|mau|ingin)"
    r"|dijamin|sudah terbukti|pasti|tentu saja)\b",
    re.IGNORECASE,
)
# "supported" must not contradict itself (PRESENT must not be read as ABSENT)
_SUPPORTED_SELF_NEGATE = re.compile(
    r"\b(?:nothing (?:yet|confirmed|is (?:confirmed|in place)|has been confirmed|can be confirmed)"
    r"|no proof\b|not proven\b"
    r"|none (?:are|is) confirmed|belum ada yang (?:bisa )?kami pastikan"
    r"|tidak ada yang bisa dipastikan|belum ada bukti)\b",
    re.IGNORECASE,
)
# "unclear" must not sublimate UNKNOWN into failure/rejection
_UNCLEAR_NEGATIVE = re.compile(
    r"\b(?:no demand|the market rejects|has failed|has been rejected|rejected\b"
    r"|does not work|doesn't work|will not pay|won't pay|refuses to pay"
    r"|pasar menolak|tidak laku|gagal|ditolak)\b",
    re.IGNORECASE,
)

# per-path narrative fields subject to the contract (order free; empty is always valid)
_NARRATIVE_FIELDS = ("why", "next", "opening", "supported", "holding", "unclear")


def _text_violations(field: str, text: str) -> list[str]:
    v: list[str] = []
    m = _OVERCLAIM.search(text)
    if m:
        v.append(f"overclaim: \"{m.group(0).lower()}\" is a population or comparison claim "
                 f"the projection does not carry")
    if field == "supported" and _SUPPORTED_SELF_NEGATE.search(text):
        v.append("supported denies itself: confirmed conditions are not described as absent")
    if field == "unclear" and _UNCLEAR_NEGATIVE.search(text):
        v.append("unclear turns \"not known\" into a negative claim; an unknown condition "
                 "is not a failed or rejected one")
    if field not in _NARRATIVE_FIELDS:
        v.append("unknown field")
    return v


def check_grounding(paths: list[dict] | None, projection: dict | None) -> dict[str, list[str]]:
    """(LLM path narrative, adjudicated projection) -> {"paths:KEY": [violations]}.

    A path without a key in the projection is not checked here — key reconciliation drops it (see
    agents.explain). An empty field is always valid: the UI falls back."""
    by_key = {str(p.get("key") or ""): p for p in (projection or {}).get("paths") or []}
    out: dict[str, list[str]] = {}
    for entry in paths or []:
        key = str((entry or {}).get("key") or "")
        p = by_key.get(key)
        if not p:
            continue
        claim_problems = check_claims(entry or {}, p)
        found: list[str] = []
        for field in _NARRATIVE_FIELDS:
            text = str((entry or {}).get(field) or "").strip()
            if not text:
                continue
            found.extend(_text_violations(field, text))
            found.extend(f"{field}: {x}" for x in claim_problems.get(field, []))
        if found:
            out[f"paths:{key}"] = found
    return out


def check_check_entries(checks: list[dict] | None, projection: dict | None) -> dict[str, list[str]]:
    """Checklist entry from the LLM -> {"checks:KEY": [violations]}. `have` states "already exists": its
    anchor is the item itself, so the item must be PRESENT and evidenced; `how` must not state an
    item that is already PRESENT as not existing. Entries without a key in the projection are
    reconciled in agents.explain."""
    items: dict[str, dict] = {}
    for p in (projection or {}).get("paths") or []:
        for it in p.get("items") or []:
            k = str(it.get("key") or "")
            cur = items.get(k)
            if k and (cur is None or (cur["state"] != "PRESENT" and it["state"] == "PRESENT")):
                items[k] = it
    out: dict[str, list[str]] = {}
    for entry in checks or []:
        key = str((entry or {}).get("key") or "")
        it = items.get(key)
        if it is None:
            continue
        found = []
        if str((entry or {}).get("have") or "").strip():
            if it["state"] != "PRESENT":
                found.append(f"have says this is in place but the projection has it as {it['state']}")
            elif not it.get("evidence"):
                found.append("have says this is in place but nothing in the projection evidences it")
            m = _OVERCLAIM.search(str(entry["have"]))
            if m:
                found.append(f"overclaim: \"{m.group(0).lower()}\" is a population or comparison claim")
        if found:
            out[f"checks:{key}"] = found
    return out


def grounding_note() -> str:
    """One sentence to include in the pack/prompt: what the narrative must not do."""
    return ("Narrative may interpret the readiness projection above; it may not create state. "
            "Every sentence in supported, holding and unclear must be backed by a claim that anchors on "
            "ONE item key from the projection (claim_type SUPPORTED only for a confirmed item, MISSING "
            "only for a still-to-get item, PARTIAL only for a partly-there item, UNKNOWN only for a "
            "not-checked-yet item, CONFLICT only for an item marked as conflicting). Unknown never "
            "becomes absent, failed or rejected; absence of "
            "evidence is not evidence of absence.")
