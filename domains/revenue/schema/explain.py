"""Human-language explanations for the Diagnosis screen
(internal-docs §6).

The engine produces artifacts that are correct but technical in tone (ontology labels, static
contraindication text, evidence summaries full of jargon). This layer rewrites the SAME MEANING in the
user's own words. It is not a source of truth: the artifact remains the source; this only reads it out.
A field that fails the guard is dropped (the UI falls back to the artifact text), never silently repaired."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PathClaim(BaseModel):
    """One state claim behind a supported/holding/unclear sentence: anchored to ONE projection item.
    The engine takes the state and evidence of that item from the projection; a claim whose anchor does
    not match is dropped."""

    field: str = Field(default="", description="Which text it backs: supported, holding or unclear")
    claim: str = Field(default="", description="The clause you claim, short, in your own words")
    claim_type: str = Field(
        default="",
        description=(
            "SUPPORTED (item is confirmed), MISSING (still to get), PARTIAL (partly there), UNKNOWN "
            "(not checked yet) or CONFLICT (two readings disagree). It must match the item's state in "
            "PATHS READ."
        ),
    )
    requirement: str = Field(
        default="", description="The exact item key from PATHS READ / CHECKS READ this claim anchors on"
    )


class PathExplain(BaseModel):
    """One path on the map (screen 07) and its reading in Readiness (screen 18): why the status is
    so, what it means from their position, and the concrete next step.

    Narrative fields (opening/supported/holding/unclear) may be empty: the UI reassembles that part
    from the same check items it displays (it never invents)."""

    key: str = Field(
        default="", description="The path key, exactly as listed in PATHS READ (e.g. path.some_strategy)"
    )
    why: str = Field(
        default="",
        description=(
            "1-2 sentences: why this path has the status it has, in their situation, starting from "
            "something they said or from a check with its outcome. Empty means the UI falls back."
        ),
    )
    next: str = Field(
        default="",
        description=(
            "1-2 sentences: the one concrete thing to do next on this path, small enough to start, "
            "from the path's own unlock or missing evidence. Empty means the UI falls back."
        ),
    )
    opening: str = Field(
        default="",
        description=(
            "For the readiness screen: 2-3 short sentences on what this path means FROM WHERE THEY ARE: "
            "start from their own facts, say what the path comes down to for them. Not a status repeat, "
            "not advice. Empty means the UI falls back."
        ),
    )
    supported: str = Field(
        default="",
        description=(
            "1-2 sentences: what is ALREADY in place for this path and what it adds up to, from checks "
            "marked confirmed and their own facts. Write it ONLY if at least one item under the path is "
            "confirmed. Empty means the UI falls back."
        ),
    )
    holding: str = Field(
        default="",
        description=(
            "1-2 sentences: the one thing that most holds this path back, from a check that failed or a "
            "condition still missing. For an open path leave empty unless something real is still unproven. "
            "Empty means the UI falls back."
        ),
    )
    unclear: str = Field(
        default="",
        description=(
            "1-2 sentences: what is NOT known yet about this path (checks nobody can answer yet), said as "
            "not known, never as false. Empty means the UI falls back."
        ),
    )


    claims: list[PathClaim] = Field(
        default_factory=list,
        description=(
            "One claim per fact stated in supported, holding and unclear, each anchored on ONE item key "
            "from PATHS READ. A field with text but no matching claim is thrown away."
        ),
    )


class CheckExplain(BaseModel):
    """One readiness checklist item (screen 18): how to check/obtain it, concretely for them."""

    key: str = Field(
        default="",
        description="The check key, exactly as listed in CHECKS READ (a requirement id or a check name)",
    )
    how: str = Field(
        default="",
        description=(
            "For a check still open or not checked: 1-2 sentences, one concrete thing they can do, "
            "with a tiny example built from their own situation when it helps. Empty means the UI falls back."
        ),
    )
    have: str = Field(
        default="",
        description=(
            "For a check already in place: ONE sentence saying what they have, in their terms. "
            "Leave empty for checks that are not in place yet."
        ),
    )


class PlainExplain(BaseModel):
    summary: list[str] = Field(
        default_factory=list,
        description=(
            "1-3 short paragraphs, second person, the user's own facts, at most 110 words in all. "
            "P1: where they are now. P2: what stands out and the main sticking point, with what is "
            "still unknown. P3 only if it changes what they do."
        ),
    )
    blocking_title: str = Field(
        default="", description="ONE sentence: what is holding them back, in their own terms")
    blocking_body: str = Field(
        default="", description="1-2 sentences: how it shows up in THEIR days (a concrete fact they gave)")
    do_title: str = Field(
        default="", description="The next step as one plain instruction they can finish today")
    do_why: str = Field(
        default="", description="ONE sentence: why this step fits THEM (tie to something they said)")
    done_when: str = Field(
        default="",
        description="1-2 sentences: what they will see if it is working; any result still teaches something",
    )
    hold_title: str = Field(
        default="", description="ONE sentence starting with the tempting move to hold off on, in their terms")
    hold_body: str = Field(
        default="", description="1-2 sentences: why not yet in THEIR situation, and when it becomes fine")
    why: list[str] = Field(
        default_factory=list,
        description="2-3 short lines; each starts from something the user said or did",
    )
    paths: list[PathExplain] = Field(
        default_factory=list,
        description=(
            "For the Path map screen: ONE entry per path key listed in PATHS READ, same keys, same "
            "field rules as the blocks above (own facts, no invented numbers, everyday words). "
            "Entries may be left out; the UI then shows the engine's own sentence for that path."
        ),
    )
    checks: list[CheckExplain] = Field(
        default_factory=list,
        description=(
            "For the readiness checklist: ONE entry per key listed in CHECKS READ, same keys. For a "
            "check still open fill how; for a check already in place fill have; never both. Entries "
            "may be left out; the UI then shows the generic instruction for that check."
        ),
    )

    @field_validator("summary", "why", mode="before")
    @classmethod
    def _as_list(cls, v):
        if isinstance(v, str):
            parts = [p.strip(" -•\t") for p in v.split("\n") if p.strip(" -•\t")]
            return parts or ([v.strip()] if v.strip() else [])
        return v
