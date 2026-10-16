"""Phase 4 (internal-docs §10.6) — Outcome Learning Store: NBA outcome reports.

Closes the Gate 5(b) criterion of internal-docs §2.1: the CAPTURE mechanism for
Decision Regret — the user reports the post-action outcome; the report goes into JSONL
(analogous to funnel.record) for reassessment + the prerequisite of P3 Outcome Learning
(internal-docs §13.2: actual vs expected_evidence → update knowledge confidence).

Deterministic, no LLM. Silent write failure (best-effort, consistent with funnel).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parents[1] / "store" / "nba_reports.jsonl"
CONF_PATH = Path(__file__).resolve().parents[1] / "store" / "knowledge_confidence.json"

# Outcome enum — explicitly bounded (internal-docs Gate 5b): moved / not_moved /
# regret / confounded (unmeasurable result due to external factors).
VALID_OUTCOMES = ("moved", "not_moved", "regret", "confounded")
# J6/K7 (internal-docs §10): grade-upgrade threshold from normative_only —
# conservative (user reports = empirical signal, not transactional proof).
GRADE_N_LOW, GRADE_CONF_LOW = 3, 0.55    # empirical_low
GRADE_N_HIGH, GRADE_CONF_HIGH = 8, 0.65  # empirical_high


def _grade(conf: float, n: int) -> str | None:
    """Epistemic grade from real outcomes — None means it stays normative_only.
    conf here is already Laplace-smoothed: a 0.5 prior holds the grade until n is sufficient."""
    if n >= GRADE_N_HIGH and conf >= GRADE_CONF_HIGH:
        return "empirical_high"
    if n >= GRADE_N_LOW and conf >= GRADE_CONF_LOW:
        return "empirical_low"
    return None
# P3 (internal-docs §13.2): outcomes counted as SUCCESS vs FAILURE (confounded
# excluded — unmeasurable results must not shift knowledge confidence).
_SUCCESS = ("moved",)
_FAILURE = ("not_moved", "regret")


def _iter_rows(path: Path | None = None, *, effective: bool = False):
    """Yield parsed rows. effective=True drops rows REPLACED by a later correction (`corrects`),
    so a corrected report is one observation, not two. The file stays append-only."""
    src = path or _PATH
    if not src.exists():
        return
    rows = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    replaced = {r.get("corrects") for r in rows if r.get("corrects")} if effective else set()
    for r in rows:
        if effective and r.get("row_id") in replaced:
            continue
        yield r


def record(
    session_id: str,
    intervention_id: str,
    outcome: str,
    notes: str = "",
    primary_constraint: str | None = None,
    op_key: str = "",
    corrects: str = "",
) -> dict[str, Any]:
    """Validate + append one report. Raise ValueError if the outcome is unknown
    or intervention_id is empty (anti-fabrication in the route layer; this layer
    enforces the enum). Return the written row (for test/route)."""
    outcome_l = (outcome or "").strip().lower()
    if outcome_l not in VALID_OUTCOMES:
        raise ValueError(
            f"outcome '{outcome}' is unknown — must be one of {VALID_OUTCOMES}"
        )
    iid = (intervention_id or "").strip().upper()
    if not iid:
        raise ValueError("intervention_id is empty — a report without linkage is meaningless")

    # Phase 6.2: effect identity. `op_key` makes a re-applied effect (recovery after an ambiguous
    # failure) return the row already written instead of appending a duplicate; `corrects` names the
    # row_id this report REPLACES, so readers count the pair as ONE effective observation.
    if op_key:
        for prior in _iter_rows():
            if prior.get("op_key") == op_key:
                return prior
    row: dict[str, Any] = {
        "row_id": uuid.uuid4().hex[:16],
        **({"op_key": op_key} if op_key else {}),
        **({"corrects": corrects} if corrects else {}),
        "ts": int(time.time()),
        "session_id": session_id,
        "intervention_id": iid,
        "outcome": outcome_l,
        "notes": notes,
        "primary_constraint": primary_constraint,
    }
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if op_key:
                fh.flush()
                os.fsync(fh.fileno())
    except OSError:
        if op_key:
            raise        # an effect with an identity must fail visibly so it stays pending and retryable
        # legacy callers without an effect key keep the best-effort behaviour
    return row


def summary() -> dict[str, Any]:
    """Report summary: global outcome distribution + per intervention.
    Used by reassessment (actual vs expected_evidence) & Gate 5b monitoring."""
    by_outcome: dict[str, int] = {}
    by_intervention: dict[str, dict[str, int]] = {}
    n = 0
    if _PATH.exists():
        for row in _iter_rows(effective=True):
            n += 1
            o = row.get("outcome", "?")
            by_outcome[o] = by_outcome.get(o, 0) + 1
            iid = row.get("intervention_id", "?")
            by_intervention.setdefault(iid, {})
            by_intervention[iid][o] = by_intervention[iid].get(o, 0) + 1
    regret_rate = round(by_outcome.get("regret", 0) / n, 3) if n else None
    return {
        "total": n,
        "by_outcome": by_outcome,
        "by_intervention": by_intervention,
        "regret_rate": regret_rate,
    }


def outcomes_by_intervention(session_ids: set[str]) -> dict[str, dict[str, int]]:
    """J7-c (internal-docs §7): outcome aggregation per intervention_id for ONE user
    (their session set). confounded is excluded (consistent with P3 recalc).
    Pure-read — used by compile_journey_context for the demote list."""
    out: dict[str, dict[str, int]] = {}
    if not session_ids or not _PATH.exists():
        return out
    for row in _iter_rows(effective=True):
        if row.get("session_id") not in session_ids:
            continue
        iid = (row.get("intervention_id") or "").strip().upper()
        outcome = row.get("outcome")
        if not iid or outcome in ("confounded", None):
            continue
        out.setdefault(iid, {})
        out[iid][outcome] = out[iid].get(outcome, 0) + 1
    return out


def recalc(conf_path: Path = CONF_PATH, src_path: Path = _PATH) -> dict:
    """P3 (internal-docs §13.2) — recalc knowledge confidence from real outcomes.

    Formula: Laplace-smoothed success rate per intervention —
        conf = (successes + 1) / (n + 2)
    (prior 0.5; an intervention without data stays 0.5 = neutral). `confounded`
    is excluded from n. The overlay is written to `knowledge_confidence.json`
    — the original KB JSON (frozen, guarded by test_knowledge_sync) is NOT touched.
    """
    stats: dict[str, dict[str, int]] = {}
    if src_path.exists():
        for row in _iter_rows(src_path, effective=True):
            iid = (row.get("intervention_id") or "").strip().upper()
            outcome = row.get("outcome")
            if not iid or outcome in ("confounded", None):
                continue
            st_ = stats.setdefault(iid, {"successes": 0, "failures": 0})
            if outcome in _SUCCESS:
                st_["successes"] += 1
            elif outcome in _FAILURE:
                st_["failures"] += 1
    items: dict[str, dict[str, Any]] = {}
    for iid, st_ in stats.items():
        s_, f_ = st_["successes"], st_["failures"]
        conf = round((s_ + 1) / (s_ + f_ + 2), 3)
        items[iid] = {
            "confidence": conf,
            "grade": _grade(conf, s_ + f_),  # J6/K7 (internal-docs §10): epistemic grade
            "successes": s_,
            "failures": f_,
            "n": s_ + f_,
        }
    data = {"updated_at": int(time.time()), "items": items}
    try:
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    except OSError:
        pass
    return data


def load_confidence(conf_path: Path = CONF_PATH) -> dict[str, float]:
    """Overlay {intervention_id: confidence} for the engine (best-effort)."""
    try:
        items = json.loads(conf_path.read_text(encoding="utf-8")).get("items", {})
        return {iid: float(v["confidence"]) for iid, v in items.items()}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {}


def load_grades(conf_path: Path = CONF_PATH) -> dict[str, str]:
    """J6/K7 (internal-docs §10): overlay {intervention_id: grade} — only interventions
    that have ALREADY risen above normative_only. Safe degrade: broken/empty file =
    {} (everything stays normative_only)."""
    try:
        items = json.loads(conf_path.read_text(encoding="utf-8")).get("items", {})
        return {
            iid: str(v["grade"])
            for iid, v in items.items()
            if v.get("grade")
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {}
