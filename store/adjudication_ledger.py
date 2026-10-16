"""Adjudication ledger + evaluation anomaly channel — Stage 3 step 5 (§6.4/D-A1d).

Contract FINAL: internal-docs §6.

Two SEPARATE stores (RR8 — neither is Universal State):
  1. adjudication ledger (JSONL append-only)  — ONLY VALID adjudications.
     Pattern precedents: store/nba.py (append-only record()) + drift.py (reports
     kept separate from state).
  2. evaluation anomaly channel (a separate JSONL) — rule construction failures
     (e.g. invalid S∧P, D-A1d). Not a RequirementStatus, not an adjudication
     result, not a conflict. Does NOT block the pipeline.

UNKNOWN-by-absence (INV-9): a consumer seeing no ledger entry = no valid adjudication
yet — DIFFERENT from an entry with status UNKNOWN. Absence is never
fabricated into a record.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ontology.adjudication.validate_adjudication import (
    check_evaluation_anomaly,
    check_ledger_entry,
)
from store.user_scope import validate_user_id

# PER-USER SPLIT (27 Sep decision — the session-runtime bridge needs
# per-user status; a global ledger = cross-user leakage [example: goal
# PRESENT owned by A rejecting B's route]). Fail-closed: no user_id OR
# a non-path-safe user_id -> ValueError (never falls back to a shared file).
# Tests override _LEDGER_ROOT (permanently non-destructive pattern).
# Hardening review 71b3c63 (conditionally green 27 Sep): user_id is validated by
# the SHARED store.user_scope helper — identical identity invariant with
# route_lineages ('../x', 'a/b' traversal rejected before the path join).
_LEDGER_ROOT = Path(__file__).resolve().parent / "workspaces"


def _channel(user_id: str, name: str) -> Path:
    validate_user_id(user_id)  # fail-closed: canonical pattern, not just non-empty
    return _LEDGER_ROOT / user_id / name

# Module public surface (wave-14 review): ONE write pipeline (atomic gate)
# + two readers. Write primitives are NOT the pipeline API — see the notes on
# _record_adjudication / _record_anomaly.
__all__ = ["adjudicate_and_persist", "latest_entry", "latest_status", "read_anomalies",
           "requirement_ids_with_entries"]

_seq = 0


def _append(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass  # best-effort, consistent with store/nba.py — never break the user flow
    return row


def _record_adjudication(user_id: str, adjudication: dict[str, Any],
                         rule_mode: str,
                         goal_id: str | None = None) -> dict[str, Any] | None:
    """Append ONE VALID adjudication to the ledger — WRITE PRIMITIVE, not the pipeline API.

    Wave-14 review: this primitive can only prove the record is
    STRUCTURALLY valid, not that it is a valid deterministic adjudication result —
    that provenance belongs to `adjudicate_and_persist()` (the single atomic gate).
    `rule_mode` is REQUIRED (no None default) — the RR11 context for ledger
    revalidation; without it a BINARY record with partial=true passes unchecked
    (review evidence gap). Structural validation first — records failing AD1-AD10
    NEVER enter the ledger. Returns the written row; None when rejected.

    R1 Probe A remediation (17 Oct): `goal_id` = business-context scope at row
    level (AD6 allows it to be optional). None = a legacy-shaped row — readable by all
    contexts (historical compatibility; visibility policy in _latest_entries).
    """
    global _seq
    entry: dict[str, Any] = {"entry_id": "placeholder", "adjudication": adjudication}
    if goal_id is not None:
        entry["goal_id"] = goal_id
    try:
        check_ledger_entry(entry, rule_mode=rule_mode)
    except ValueError:
        return None  # the pipeline caller is expected to record an evaluation anomaly, not an entry
    _seq += 1
    row: dict[str, Any] = {
        "entry_id": f"adj.{adjudication['requirement_id']}.{adjudication['adjudicated_at']}.{_seq}",
        "adjudication": adjudication,
    }
    if goal_id is not None:
        row["goal_id"] = goal_id
    return _append(_channel(user_id, "adjudication_ledger.jsonl"), row)


def _record_anomaly(user_id: str, anomaly: dict[str, Any]) -> dict[str, Any]:
    """Append ONE evaluation anomaly to the SEPARATE channel — WRITE PRIMITIVE
    (not the pipeline API; the official entry point = adjudicate_and_persist).
    Never touches the ledger; never blocks the pipeline (best-effort write)."""
    row = dict(anomaly)
    row.setdefault("anomaly_id", f"anom.{row.get('requirement_id', '?')}.{int(time.time())}")
    check_evaluation_anomaly(row)
    return _append(_channel(user_id, "evaluation_anomalies.jsonl"), row)


def adjudicate_and_persist(
    user_id: str,
    requirement_id: str,
    rule: dict[str, Any],
    evidence: Any,
    verified_mappings: list[dict[str, Any]],
    evaluation_time: int,
    adjudicated_at: int | None = None,
    precomputed_rule_evaluation: dict[str, bool] | None = None,
    precomputed_citations: dict[str, list[str]] | None = None,
    goal_id: str | None = None,
) -> dict[str, Any]:
    """D-A1d ATOMIC (wave-13 review) + the ONLY public write API
    (wave-14 review — the `_record_*` primitives are private; provenance =
    this function): it FORCES the routing, so a caller cannot choose to skip
    the anomaly gate:

        adjudicate → invalid result? ── yes → evaluation anomaly channel
                                             (NO output, NO ledger entry)
                            │ no
                            └──────→ ledger append (only valid adjudications)
                                     (revalidated with the registry's rule_mode — RR11)

    R1 Probe A remediation (17 Oct): optional `goal_id` = business-context scope
    attached to the ledger row (row level). The production caller
    (`ontology/mapper/live_adjudication`) forwards the session's `goal["goal_id"]` —
    two different businesses of the same user no longer share state.

    Returns: a ledger row (has "entry_id") OR an anomaly row (has "anomaly_id")
    — exactly ONE of the two, never both.
    """
    from core.stages.adjudicate import adjudicate  # local import: avoids a module cycle

    rule_mode = (rule or {}).get("mode")
    if rule_mode not in ("BINARY", "PARTIAL"):
        # malformed rule (the registry schema mandates mode) — bad input, not a rule_evaluation anomaly
        raise ValueError(f"satisfaction_rule.mode '{rule_mode}' tidak valid — RR11 butuh konteks mode")

    result = adjudicate(
        requirement_id, rule, evidence, verified_mappings, evaluation_time,
        adjudicated_at=adjudicated_at,
        precomputed_rule_evaluation=precomputed_rule_evaluation,
        precomputed_citations=precomputed_citations,
    )
    if "anomaly_id" in result:
        return _record_anomaly(user_id, result)     # D-A1d: no output, no ledger
    row = _record_adjudication(user_id, result, rule_mode=rule_mode,
                               goal_id=goal_id)  # RR11 context + scope forwarded
    if row is None:  # defense-in-depth: the evaluator passed but ledger revalidation failed
        raise ValueError(
            "adjudication ditolak ledger setelah lolos evaluator — inkonsistensi validator, "
            "jangan pernah menyimpannya"
        )
    return row


def _latest_entries(user_id: str,
                    goal_id: str | None = None) -> dict[str, dict[str, Any]]:
    """The LATEST ledger entry per requirement for ONE user (single read pass;
    the last entry wins).

    R1 Probe A remediation (17 Oct): `goal_id` = business-context filter. Entries
    with a goal are SENSITIVE: only readable by the same context (PRESENT owned by
    business A no longer leaks into business B of the same user).

    D3 closure (17 Oct, DELIBERATE policy revision): LEGACY entries (no goal_id)
    NO LONGER credit satisfaction in context-scoped reads —
    "unknown ownership is not shared ownership". Policy:
      - goal-scoped reads  → only entries with the same goal_id;
      - unfiltered reads (goal_id=None) → ALL entries (inspection/audit,
        Gate A sweep, recovery) — old data is not lost, it just stops
        being auto-credited to contexts it was never proven for;
      - self-healing: the production path (`run_live_adjudication`) rewrites
        goal-scoped rows idempotently while the session runs, so the context's
        status is refilled from the same evidence;
      - explicit rebinding = the goal-scoped write gate (`adjudicate_and_persist`)
        — no silent rewrite."""
    try:
        lines = _channel(user_id, "adjudication_ledger.jsonl").read_text(
            encoding="utf-8").splitlines()
    except OSError:
        return {}
    latest: dict[str, dict[str, Any]] = {}
    for line in lines:
        if not line.strip():
            continue
        entry = json.loads(line)
        if goal_id is not None:
            if entry.get("goal_id") != goal_id:
                continue  # another context, OR legacy without proven ownership (D3)
        latest[entry["adjudication"]["requirement_id"]] = entry
    return latest


def latest_entry(user_id: str, requirement_id: str, *,
                 goal_id: str | None = None) -> dict[str, Any] | None:
    """The LATEST ledger entry (`{entry_id, adjudication}`) for this requirement;
    None = NO valid adjudication exists (UNKNOWN by absence, INV-9). READ
    access only: reading the full state (citations, time, conflict) for the Requirement
    State Reader; it opens no write gate whatsoever.

    R1 Probe A remediation: optional `goal_id` narrows this to a single business
    context (goal-scoped entries of other contexts are unread; legacy stays
    readable — see `_latest_entries`)."""
    return _latest_entries(user_id, goal_id).get(requirement_id)


def requirement_ids_with_entries(user_id: str) -> list[str]:
    """RIDs ever adjudicated for this user (from the ledger, single read pass).

    Gate A (15 Oct, external audit): post-supersession invalidation must be able to find
    PROSE requirements that were adjudicated even when this turn has no new proposal —
    without this, an old status (e.g. PRESENT) survives a user correction. User-scoped by
    construction (one channel per user); it never touches another user."""
    return sorted(_latest_entries(user_id))


def latest_status(user_id: str, requirement_id: str, *,
                  goal_id: str | None = None) -> str | None:
    """Current status of a requirement — PER-USER (27 Sep split) and, since the
    Probe A remediation (17 Oct), PER-BUSINESS-CONTEXT when `goal_id` is given
    (the LATEST ledger entry readable by that context; §6.4: status is a pure
    function). None = NO valid adjudication exists — the consumer falls back to
    UNKNOWN by absence (INV-9); this is NOT 'UNKNOWN'."""
    entry = latest_entry(user_id, requirement_id, goal_id=goal_id)
    # the last entry wins — recompute, no stickiness
    return entry["adjudication"]["status"] if entry else None


def read_anomalies(user_id: str,
                   requirement_id: str | None = None) -> list[dict[str, Any]]:
    """Read the PER-USER anomaly channel (a separate diagnostic path — not
    status history)."""
    try:
        lines = _channel(user_id, "evaluation_anomalies.jsonl").read_text(
            encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if requirement_id is None or row.get("requirement_id") == requirement_id:
            out.append(row)
    return out
