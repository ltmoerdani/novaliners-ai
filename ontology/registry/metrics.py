"""METRIC REGISTRY loader (internal-docs §3.1).

Registry = catalog of versioned metric definitions — NOT a strategy recommendation and NOT a path list.
One lookup door: by metric_id, by user-language alias, or by free text (`match_metric_text`).
Outside the registry = invalid as a Goal metric in the first release (ADR-GR1) → the caller must abstain
with reason `GOAL_METRIC_UNSUPPORTED`, not map it to the nearest revenue slot.

Structural validator: `ontology/registry/validate_metrics.py` (included in `make gate-fast`).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).parent / "metric_registry.json"

SEMANTICS_INCREASE_TO_THRESHOLD = "INCREASE_TO_THRESHOLD"
SEMANTICS_DECREASE_TO_THRESHOLD = "DECREASE_TO_THRESHOLD"
SEMANTICS_MAINTAIN_RANGE = "MAINTAIN_RANGE"
SEMANTICS_AT_LEAST = "AT_LEAST"
SEMANTICS_AT_MOST = "AT_MOST"
SEMANTICS_COUNT_IN_WINDOW = "COUNT_IN_WINDOW"
SEMANTICS_RATE_OR_RATIO = "RATE_OR_RATIO"
SEMANTICS_EVIDENCE_CRITERIA = "EVIDENCE_CRITERIA"

ALL_SEMANTICS = (
    SEMANTICS_INCREASE_TO_THRESHOLD, SEMANTICS_DECREASE_TO_THRESHOLD, SEMANTICS_MAINTAIN_RANGE,
    SEMANTICS_AT_LEAST, SEMANTICS_AT_MOST, SEMANTICS_COUNT_IN_WINDOW, SEMANTICS_RATE_OR_RATIO,
    SEMANTICS_EVIDENCE_CRITERIA,
)

ROLE_ACTIVITY = "activity"
ROLE_OUTCOME = "outcome"


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _cached_registry() -> dict[str, Any]:
    return load_registry()


def registry_version() -> str:
    return _cached_registry().get("registry_version", "unknown")


def metrics() -> list[dict[str, Any]]:
    return list(_cached_registry().get("metrics", []))


def metric_by_id(metric_id: str) -> dict[str, Any] | None:
    for m in metrics():
        if m["metric_id"] == metric_id:
            return m
    return None


def metric_by_alias(alias: str) -> dict[str, Any] | None:
    """User-language alias → definition (case-insensitive, trim)."""
    key = (alias or "").strip().lower()
    if not key:
        return None
    for m in metrics():
        if key == m["metric_id"] or key in {a.lower() for a in m.get("aliases", [])}:
            return m
    return None


def _alias_words(alias: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9%]+", alias.lower()) if len(w) > 2}


def match_metric_text(
    text: str, exclude: frozenset[str] | set[str] = frozenset(),
) -> dict[str, Any] | None:
    """Free text → metric definition with LONGEST alias-match weight (deterministic).

    `exclude` = metric_id that must not win (used by the parser: a guardrail-role metric
    must not become primary when another outcome metric also matches — UC-05).
    Not a semantic claim: this is the candidate PROPOSED by the parser (origin is still tracked by the
    caller); text without a matching alias → None (not a revenue default).
    """
    t = (text or "").lower()
    if not t.strip():
        return None
    best: tuple[int, dict[str, Any]] | None = None
    for m in metrics():
        if m["metric_id"] in exclude:
            continue
        for alias in [m["metric_id"], *m.get("aliases", [])]:
            a = alias.lower().strip()
            if not a:
                continue
            if a in t:
                cand = (len(a), m)
                if best is None or cand[0] > best[0]:
                    best = cand
    if best is None:
        return None
    # a longer multi-word alias wins; between two aliases of equal length,
    # the first candidate wins (registry order) — deterministic.
    return best[1]


def known_metric(metric_id: str) -> bool:
    return metric_by_id(metric_id) is not None
