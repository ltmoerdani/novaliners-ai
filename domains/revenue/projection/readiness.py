"""Adjudicated Readiness Projection for Revenue — the domain hook over the universal projection.

All projection logic (item adjudication, executability, counts, narrative fallback, cache basis)
lives in `core/navigation/readiness.py` and is generic. This module only binds three things owned
by the domain/infrastructure:

  - Requirement Registry + Requirement Presentation (engine.requirements.describe) — ONE requirement
    source; there is no requirement dictionary or string-gate mapping here;
  - the diagnosis artifact (`possible_paths`, path identity = strategy);
  - the latest lifecycle per path from user outcomes (store/path_states via `lifecycles_from_states`).

UI and LLM read the SAME projection (internal-docs §10;
internal-docs §Readiness). The projection preserves UNKNOWN != ABSENT and
PRESENT != PARTIAL."""

from __future__ import annotations

from core.navigation.readiness import (  # noqa: F401 (re-export for domain readers)
    build_projection,
    projection_path_keys,
    readiness_basis,
)
from domains.revenue.navigation.paths import lifecycles_from_states
from engine.requirements import describe


def build_readiness_projection(
    diagnosis, route_data: dict | None = None, path_states: dict | None = None, lang: str = "en"
) -> dict:
    """(diagnosis, route komposisi user, outcome state per path) -> proyeksi final."""
    path_set = getattr(diagnosis, "possible_paths", None) if diagnosis else None
    return build_projection(
        path_set,
        route_data,
        lambda rid: describe(rid, lang),
        lifecycles=lifecycles_from_states(path_states),
        lang=lang,
    )
