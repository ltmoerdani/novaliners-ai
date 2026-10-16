"""Check-in ledger PER-USER - durable history, NOT localStorage (audit V4 D-02).

Problem closed: LIVE.checkins lived in the browser (localStorage) and time/counters
were created on the client; clearing the browser = progress history lost, and "saved" was never
durable. This store keeps every check-in as an append-only row per user with
business-context scope (goal_id - the SAME boundary as route lineage and requirement
ledger), so a reload / the next session on the same map reads the same history.

Value rules (D-02, N02/N10): a number that is NOT reported is None, never
forced to 0; a 0 reported by the user STAYS 0 (0 != unknown). Unknown fields
are not stored; invalid outcome enums are rejected.

Idempotency (D-10/N27): optional op_id = client operation key; resending with the same
key returns the existing row, not a second row.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from store.user_scope import validate_user_id

_BASE = Path(__file__).parent / "workspaces"
OUTCOMES = ("worked", "mixed", "none")
_NUM_FIELDS = ("cycle", "day", "contacted", "replies", "calls", "paid", "rp", "action_index")
# P0-05: the canonical command includes the optional action report, so a replay of the same op_id
# with different action fields is a CONFLICT (not a silent no-op). Kept as plain strings.
_STR_FIELDS = ("path", "title", "note", "action_status", "action_outcome")


class CheckinError(ValueError):
    """Invalid check-in (outcome/enum/number type)."""


class CheckinConflict(CheckinError):
    """operation_id reused with a different payload (P1-02)."""


def _path(user_id: str, base_dir: Path | str | None = None) -> Path:
    validate_user_id(user_id)
    root = Path(base_dir) if base_dir else _BASE
    return root / user_id / "checkins.jsonl"


def _num_or_none(value: Any, field: str) -> Any:
    """A number or None. Empty string/None = not reported. bool is NOT a number."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise CheckinError(f"{field} must be a number, not a boolean")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value) if "." in value else int(value)
        except ValueError as exc:
            raise CheckinError(f"{field} is not a number: {value!r}") from exc
    raise CheckinError(f"{field} must be a number, got {type(value).__name__}")


def _normalize(row: dict, goal_id: str | None) -> dict:
    if not isinstance(row, dict):
        raise CheckinError("check-in must be a dict")
    outcome = row.get("outcome")
    if outcome not in OUTCOMES:
        raise CheckinError(f"outcome {outcome!r} outside {OUTCOMES}")
    out: dict[str, Any] = {"outcome": outcome, "goal_id": goal_id}
    for f in _NUM_FIELDS:
        out[f] = _num_or_none(row.get(f), f)
    for f in _STR_FIELDS:
        out[f] = str(row.get(f) or "")
    return out


def normalize(row: dict, goal_id: str | None) -> dict:
    """Validate + normalize a check-in command WITHOUT writing (P0-05). Raises CheckinError on an
    invalid field, so a caller can reject the whole request before any mutation."""
    return _normalize(row, goal_id)


def list_rows(user_id: str, base_dir: Path | str | None = None) -> list[dict[str, Any]]:
    p = _path(user_id, base_dir)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue  # a broken line must not break the user flow
        if isinstance(data, dict):
            rows.append(data)
    return rows


def find_by_operation(user_id: str, op_id: str, base_dir: Path | str | None = None) -> dict[str, Any] | None:
    if not op_id:
        return None
    for r in list_rows(user_id, base_dir):
        if r.get("op_id") == op_id:
            return r
    return None


def record(user_id: str, row: dict, *, goal_id: str | None = None, op_id: str = "",
           base_dir: Path | str | None = None, now: int | None = None) -> dict[str, Any]:
    """Append one durable check-in. Idempotent per op_id. Raise CheckinError when invalid."""
    payload = _normalize(row, goal_id)
    if op_id:
        prior = find_by_operation(user_id, op_id, base_dir)
        if prior is not None:
            # P1-02: a replayed key must carry the SAME payload. A different payload under the same
            # key is a conflict, never a silent no-op that would hide contradictory history.
            if any(prior.get(k) != payload.get(k) for k in payload):
                raise CheckinConflict(
                    f"operation_id {op_id!r} reused with a different payload")
            return prior
    ts = int(now if now is not None else time.time())
    seed = f"{user_id}|{op_id or ts}|{goal_id or ''}|{payload['outcome']}|{payload.get('day')}"
    out = {"checkin_id": "ci-" + hashlib.sha1(seed.encode()).hexdigest()[:10],
           "session_id": str(row.get("sid") or row.get("session_id") or ""),
           "op_id": op_id or "", "created_ts": ts, **payload}
    p = _path(user_id, base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out


def latest(user_id: str, *, goal_id: str | None = None, base_dir: Path | str | None = None,
           limit: int = 0) -> list[dict[str, Any]]:
    """Check-in history, chronological. Goal-context filter when given: rows
    with ANOTHER goal do not leak; legacy rows without a goal remain readable (compatibility)."""
    rows = [r for r in list_rows(user_id, base_dir)
            if goal_id is None or r.get("goal_id") in (goal_id, None, "")]
    rows.sort(key=lambda r: (r.get("created_ts") or 0, r.get("checkin_id") or ""))
    return rows[-limit:] if limit else rows
