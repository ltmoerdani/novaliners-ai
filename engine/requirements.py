"""Requirement Registry + Requirement Presentation loader (single source of truth for requirements).

The registry (`ontology/registry/requirement_registry.json`) holds identity, definitions, observability,
satisfaction rules, and provenance. The presentation pack (`requirement_presentation.json`) is display
text per language only. Readiness, UI, and narrative all read through this module — there is no second
requirement dictionary anywhere else.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.navigation.presentation import resolve_presentation

REGISTRY_DIR = Path(__file__).resolve().parent.parent / "ontology" / "registry"
REGISTRY_PATH = REGISTRY_DIR / "requirement_registry.json"
PRESENTATION_PATH = REGISTRY_DIR / "requirement_presentation.json"


@lru_cache(maxsize=1)
def load_registry() -> dict[str, dict[str, Any]]:
    """requirement_id -> registry entry (5 semantic layers)."""
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {e["requirement_id"]: e for e in data["requirements"]}


@lru_cache(maxsize=1)
def load_presentation_pack() -> dict[str, Any]:
    return json.loads(PRESENTATION_PATH.read_text(encoding="utf-8"))


def is_known(requirement_id: str) -> bool:
    return requirement_id in load_registry()


def describe(requirement_id: str, lang: str = "en") -> dict[str, dict[str, str]]:
    """Resolved presentation for one requirement (curated or deterministic fallback)."""
    return resolve_presentation(
        requirement_id, load_registry().get(requirement_id), load_presentation_pack(), lang
    )
