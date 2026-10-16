"""Requirement Presentation — human language for requirements, on top of the Requirement Registry.

The registry is the single source of requirement IDENTITY and SEMANTICS (definition, observability,
satisfaction rules, provenance). Presentation is display text only, per language, keyed by `requirement_id`:

    title         a short name for the condition
    description   what it means (optional)
    verification  how to obtain / check that condition

A requirement without curated text is STILL readable through a deterministic fallback from registry
semantics: title from the id's words, description from `definition`, verification from `observability`. The
fallback invents no domain copy; `source` per field ("curated" | "fallback") and `lang` per field always
travel along so readers (UI, narrative) know what they are reading. Adding a requirement to the registry
does not touch this code."""

from __future__ import annotations

from typing import Any

FIELDS = ("title", "description", "verification")
REGISTRY_LANG = "id"  # the language definitions/observability are written in, in the registry
ID_LANG = "en"  # the words in a requirement id (dotted <domain>.<name>) are English


def humanize_id(requirement_id: str) -> str:
    """'commercial.pricing_basis' -> 'Pricing basis' (last segment, underscore -> space)."""
    tail = requirement_id.rsplit(".", 1)[-1].replace("_", " ").strip()
    return tail[:1].upper() + tail[1:] if tail else requirement_id


def _field(text: str, lang: str, source: str) -> dict[str, str]:
    return {"text": text, "lang": lang, "source": source}


def resolve_presentation(
    requirement_id: str, entry: dict[str, Any] | None, pack: dict[str, Any] | None, lang: str = "en"
) -> dict[str, dict[str, str]]:
    """(id, registry entry|None, presentation pack, language) -> {title, description, verification}.

    `entry` None (an id unknown to the registry) still yields a title from the id; description/verification
    come out empty — no text is invented."""
    curated = (((pack or {}).get("entries") or {}).get(requirement_id) or {}).get(lang) or {}
    out: dict[str, dict[str, str]] = {}
    if curated.get("title"):
        out["title"] = _field(curated["title"], lang, "curated")
    else:
        out["title"] = _field(humanize_id(requirement_id), ID_LANG, "fallback")
    if curated.get("description"):
        out["description"] = _field(curated["description"], lang, "curated")
    else:
        out["description"] = _field((entry or {}).get("definition", ""), REGISTRY_LANG, "fallback")
    if curated.get("verification"):
        out["verification"] = _field(curated["verification"], lang, "curated")
    else:
        obs = "; ".join((entry or {}).get("observability") or [])
        out["verification"] = _field(obs, REGISTRY_LANG, "fallback")
    return out
