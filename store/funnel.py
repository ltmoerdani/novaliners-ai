"""Iteration 12 — cross-session persistence funnel.

Goal (backlog internal-docs §5.5 #3): measure the TRANSITION RATE across sessions, not just
one diagnosis. Every `finalize` writes one summary row to JSONL; the
`summary()` function computes the spectrum level distribution + primary constraint + mapping
coverage across sessions (used during reassess).

Deterministic, no LLM. Does not store conversation content (metadata only).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parents[1] / "eval_funnel.jsonl"


def record(
    session_id: str,
    primary: str,
    spectrum_level: str | None,
    funnel_stages: list[str] | None,
    metrics: dict[str, Any] | None,
    confidence: float | None = None,
    user_id: str = "",
) -> None:
    """Append one session summary. Silent failure if the FS cannot be written.

    J3 (internal-docs §7): optional user_id — when set, the state evolution of the same
    person can be reconstructed (delta across runs), not just the global
    transition rate keyed by a random session."""
    rec = {
        "ts": int(time.time()),
        "session_id": session_id,
        "user_id": user_id,
        "primary": primary,
        "spectrum": spectrum_level,
        "confidence": confidence,
        "funnel_stages": funnel_stages or [],
        "metrics": metrics or {},
    }
    try:
        with _PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _rows() -> list[dict]:
    if not _PATH.exists():
        return []
    out: list[dict] = []
    try:
        for line in _PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def summary() -> dict:
    """Cross-session summary: spectrum distribution, primary constraint, coverage,
    and median confidence. This is the basis of 'transition rate' during reassess."""
    rows = _rows()
    by_spectrum: dict[str, int] = {}
    by_primary: dict[str, int] = {}
    cov: list[float] = []
    conf: list[float] = []
    for r in rows:
        if r.get("spectrum"):
            by_spectrum[r["spectrum"]] = by_spectrum.get(r["spectrum"], 0) + 1
        if r.get("primary"):
            by_primary[r["primary"]] = by_primary.get(r["primary"], 0) + 1
        m = r.get("metrics") or {}
        if isinstance(m.get("mapping_coverage"), (int, float)):
            cov.append(float(m["mapping_coverage"]))
        if isinstance(r.get("confidence"), (int, float)):
            conf.append(float(r["confidence"]))

    def _median(xs: list[float]) -> float | None:
        if not xs:
            return None
        xs = sorted(xs)
        mid = len(xs) // 2
        return round(xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2, 3)

    return {
        "sessions": len(rows),
        "spectrum_distribution": by_spectrum,
        "primary_distribution": by_primary,
        "median_mapping_coverage": _median(cov),
        "median_confidence": _median(conf),
        "funnel_stages": (rows[-1].get("funnel_stages") if rows else []) or [],
        "note": "Transition rate dihitung dari perubahan level spektrum antar sesi dengan primary yang sama.",
    }
