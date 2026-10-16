"""A deterministic narrative fallback from projection items (a micro-narrative, not a cosmetic checklist).

Every sentence is built from the SAME items as those displayed, and every item mentioned becomes an anchored
claim (claim -> requirement_anchor -> evidence_anchor -> support_state). So every fallback sentence is
traceable to the requirement state and the evidence behind it; no word is invented.

Only items with English titles are named (curated, or derived from the requirement id); other items still
count in `counts` but their names are not invented."""

from __future__ import annotations

from core.navigation.claims import make_claim
from core.navigation.contracts import Satisfaction


def _low(label: str) -> str:
    return label[:1].lower() + label[1:] if label else label


def _join(labels: list[str]) -> str:
    parts = [p for p in labels if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _unknown_clause(label: str) -> str:
    """A requirement label -> the 'what is not yet known' clause. A question-shaped label is used as-is; a
    noun-shaped one is framed as 'whether ... in place'."""
    if label[:1].lower() in ("w", "h") and label[:4].lower() in ("what", "whet", "how "):
        return label
    return f"Whether {_low(label)} is in place"


def fallback_narrative(status: str, items: list[dict]) -> dict:
    def named(state: str) -> list[dict]:
        return [it for it in items if it["state"] == state and it.get("label_ok") and it.get("settled", True)]

    def label(it: dict) -> str:
        return it["title"]["text"]

    present, absent = named(Satisfaction.PRESENT), named(Satisfaction.ABSENT)
    partial, unknown = named(Satisfaction.PARTIAL), named(Satisfaction.UNKNOWN)
    claims: list[dict] = []

    supported = ""
    if present:
        shown = present[:3]
        supported = f"You already have {_join([_low(label(x)) for x in shown])}."
        claims += [
            make_claim("supported", f"You already have {_low(label(x))}.", "SUPPORTED", x) for x in shown
        ]
        if absent:
            supported += f" What is not in place yet is {_low(label(absent[0]))}."
            claims.append(
                make_claim("supported", f"{label(absent[0])} is not in place yet.", "MISSING", absent[0])
            )
        elif unknown:
            supported += f" What we cannot say yet: whether {_low(label(unknown[0]))} is in place."
            claims.append(
                make_claim(
                    "supported",
                    f"Whether {_low(label(unknown[0]))} is in place is not known yet.",
                    "UNKNOWN",
                    unknown[0],
                )
            )
        else:
            supported += " That is what this path stands on right now."

    holding = ""
    if status not in ("OPEN", "STOP"):
        if absent:
            first = absent[0]
            claims.append(
                make_claim("holding", f"{label(first)} is what this path waits on.", "MISSING", first)
            )
            if len(absent) == 1:
                holding = f"{label(first)} is what this path still waits on."
            else:
                holding = (
                    f"{label(first)} is what this path waits on first; "
                    f"{_low(label(absent[1]))} comes after that."
                )
                claims.append(
                    make_claim("holding", f"{label(absent[1])} comes after that.", "MISSING", absent[1])
                )
        elif partial:
            holding = f"Part of {_low(label(partial[0]))} is in place; the rest is what this path waits on."
            claims.append(
                make_claim(
                    "holding", f"Part of {_low(label(partial[0]))} is in place.", "PARTIAL", partial[0]
                )
            )

    unclear = ""
    contested = [it for it in items if not it.get("settled", True) and it.get("label_ok")]
    if contested:
        c = contested[0]
        unclear = f"{label(c)}: two readings of your evidence disagree, so we do not treat it as settled."
        text = f"{label(c)} is not settled: the readings disagree."
        claims.append(make_claim("unclear", text, "CONFLICT", c))
    if unknown:
        shown = unknown[:2]
        clauses = [_unknown_clause(label(u)) for u in shown]
        if len(clauses) == 1:
            more = f"{clauses[0]} is not known yet."
        else:
            more = f"Still open: {_low(clauses[0])}, and {_low(clauses[1])}."
        unclear = f"{unclear} {more}".strip()
        claims += [
            make_claim("unclear", f"{_unknown_clause(label(u))} is not known yet.", "UNKNOWN", u)
            for u in shown
        ]

    return {"supported": supported, "holding": holding, "unclear": unclear, "claims": claims}


# Readings of NEWLY EMERGING possibilities for machine readers (Ask/Explain): the hard words come from the
# projection, not from the LLM. An unsettled possibility is NOT a path and is never read out as a certainty.
_EMERGING_READ = {
    "UNKNOWN": "UNKNOWN: a first sign exists but one fact is missing. It is NOT a path and NOT confirmed",
    "CONFLICT": "CONFLICT: the evidence disagrees, so it is not settled. It is NOT a path and NOT confirmed",
    "UNSUPPORTED": "UNSUPPORTED: a hint with nothing backing it, so it is not counted. It is NOT a path",
}


def emerging_lines(projection: dict | None) -> list[str]:
    """Newly emerging possibilities -> deterministic context lines (verified/unknown/conflict/unsupported
    stay separate). Empty for a LEGACY artifact or when there is no sign."""
    proj = projection or {}
    if (proj.get("navigation") or {}).get("status") == "LEGACY":
        return []
    out = []
    for e in proj.get("emerging") or []:
        word = _EMERGING_READ.get(e.get("state"))
        title = str((e.get("title") or {}).get("text") or "").strip()
        if word and title:
            out.append(f"- possibility (not a path): {title} — {word}.")
    return out


def candidate_line(path: dict) -> str:
    """'Why this path exists' for paths born from a Candidate Possibility; '' otherwise.

    Two notes join when present (both from the projection, nothing invented): a disputed mechanism is NOT
    part of the reason (contradicting evidence; not read out as a certainty), and support that leans on the
    absence of a record (not yet verified)."""
    cand = path.get("candidate") or {}
    text = str((cand.get("why") or {}).get("text") or "").strip()
    if not text:
        return ""
    lines = [f"  why it is on the map: {text}"]
    names = [str(u.get("name") or "") for u in cand.get("unsettled") or [] if u.get("name")]
    if names:
        lines.append(
            f"  NOT settled and NOT part of that reason: the evidence disagrees about {', '.join(names)}"
        )
    if cand.get("assumes_absence"):
        lines.append(
            "  note: this also assumes nothing you shared points the other way; that is NOT confirmed"
        )
    return "\n".join(lines)
