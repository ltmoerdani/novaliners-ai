"""P-E Path States Store — per-path per-user outcome state persistence + event log.

internal-docs §3.5 (forensic audit): the outcome→path synapse is now
connected; state + history live here (a full P-D workspace prerequisite).

Goal-Relative (int 09 §4.4, Phase 3): outcome state is now GOAL-SCOPED —
- store/path_states.json        — LEGACY user-wide (GLOBAL scope; old data stays readable)
- store/path_states_goals.json  — {user_id: {goal_id: {path_id: state}}} (GOAL scope)
- store/path_history.jsonl      — append-only PATH_STATUS_CHANGED event log (audit)

A STOP/outcome reported on Goal A does NOT propagate to Goal B (GR-19): a read of
get_states(user_id, goal_id) = global merge (inherited, tagged) + goal-scoped
(goal-scoped wins on conflict). Cross-goal writes only happen through explicit
writes without a goal_id (legacy behavior) — never automatically.

Deterministic, no LLM. Best-effort (silent write failures — consistent with nba.py).
Keyed per USER (not session) — same as outcomes_by_intervention J7-c.
A user without a user_id → state is not persisted (degrades to no overlay).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from domains.revenue.stages.reroute import (
    PATH_ID_RE,
    VALID_OUTCOMES,
    apply_outcome,
)

_BASE = Path(__file__).resolve().parents[1] / "store"
_STATES = _BASE / "path_states.json"
_STATES_GOALS = _BASE / "path_states_goals.json"
_HISTORY = _BASE / "path_history.jsonl"


def _read_states() -> dict[str, dict[str, dict]]:
    try:
        return json.loads(_STATES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(path: Path, data: dict) -> None:
    """Durable write: temp file + fsync + atomic replace. RAISES OSError on failure - a path-state effect
    that cannot be stored must be a visible failure, never a silent no-op (Phase 6.2.1)."""
    _BASE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _write_states(data: dict) -> None:
    _atomic_write(_STATES, data)


def _read_goal_states() -> dict[str, dict[str, dict[str, dict]]]:
    try:
        return json.loads(_STATES_GOALS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_goal_states(data: dict) -> None:
    _atomic_write(_STATES_GOALS, data)


def _event_exists(op_key: str) -> bool:
    if not op_key or not _HISTORY.exists():
        return False
    needle = json.dumps(op_key, ensure_ascii=False)
    try:
        return any(needle in line and f'"op_key": {needle}' in line
                   for line in _HISTORY.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def _append_event(ev: dict) -> None:
    """Append one history event. Raises OSError on failure (see _atomic_write). An event carrying an
    op_key is written at most once, so re-applying an effect after an ambiguous
    failure cannot duplicate it."""
    if ev.get("op_key") and _event_exists(ev["op_key"]):
        return
    _BASE.mkdir(parents=True, exist_ok=True)
    with _HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def get_states(user_id: str, goal_id: str | None = None) -> dict[str, dict]:
    """The user's path states — empty without a user_id / with no history yet.

    goal_id None → LEGACY behavior (GLOBAL user-wide scope only, for old callers).
    goal_id given → GLOBAL merge (inherited, tagged _scope=GLOBAL) + GOAL-scoped
    (goal-scoped wins conflicts) — GR-19: other Goals' outcomes do not leak."""
    if not user_id:
        return {}
    states = dict(_read_states().get(user_id, {}))
    if goal_id is None:
        return states
    scoped = _read_goal_states().get(user_id, {}).get(goal_id, {})
    out: dict[str, dict] = {}
    for pid, st in states.items():  # inherited: still applies across goals (legacy behavior)
        out[pid] = {**(st or {}), "_scope": "GLOBAL"}
    for pid, st in scoped.items():  # goal-scoped wins
        out[pid] = {**(st or {}), "_scope": "GOAL"}
    return out


def _transition(state: dict | None, outcome: str, reverse: dict | None):
    """apply_outcome, optionally preceded by the REVERSAL of an earlier effect of the same action.

    Phase 6.2 correction semantics: a corrected report must not leave the first outcome counted as
    an independent observation. The reversal takes the old outcome's counter back by one; if the old
    outcome was the `regret` that STOPPED the path and no regret remains, the stop is lifted with a
    recorded reason (the path history in the event log keeps the original STOP)."""
    if not reverse:
        return apply_outcome(state, outcome)
    st = dict(state or {})
    old = str(reverse.get("outcome") or "")
    if old in VALID_OUTCOMES and int(st.get(old) or 0) > 0:
        st[old] = int(st[old]) - 1
    reopened = (old == "regret" and int(st.get("regret") or 0) == 0
                and st.get("outcome_state") == "STOPPED")
    if reopened:
        st["outcome_state"] = "OPEN"
    if outcome is None:                      # reversal only (the corrected report moved to another path)
        new_state, ev = st, None
    else:
        new_state, ev = apply_outcome(st, outcome)
    if reopened and ev is None:
        ev = {"type": "PATH_STATUS_CHANGED", "from": "STOPPED", "to": "OPEN",
              "cause": "outcome corrected - the regret that stopped this path was withdrawn"}
    return new_state, ev


_OPS_KEPT = 30   # bounded per-path memory of applied effect keys


def _remember_op(state: dict, op_key: str) -> None:
    if op_key:
        ops = [o for o in (state.get("applied_ops") or []) if o != op_key]
        ops.append(op_key)
        state["applied_ops"] = ops[-_OPS_KEPT:]


def apply_and_log(
    user_id: str, session_id: str, path: str, outcome: str, goal_id: str = "",
    *, op_key: str = "", reverse: dict | None = None,
) -> dict[str, Any]:
    """One outcome report for one path → update state + log an event.
    Returns {"state": ..., "event": ev|None}. "path" = a path_id ("path.<strategy_id>"); an
    invalid shape → ValueError (enforced in this layer, not the route). The list of live paths is
    decided by the generator per user state, not a fixed enum here.

    Empty goal_id → GLOBAL scope (user-wide inheritance). A goal_id → GOAL scope:
    the outcome only affects that Goal's evaluation (int 09 §4.4; GR-19)."""
    p = (path or "").strip()
    if not PATH_ID_RE.match(p):
        raise ValueError(f"path '{path}' bukan path_id yang sah (bentuk: path.<strategy_id>)")
    if not user_id:
        return {"state": None, "event": None,
                "note": "tanpa user_id — state jalur tidak dipersist (degrade)"}
    gid = (goal_id or "").strip()
    if gid:
        data = _read_goal_states()
        scope = data.setdefault(user_id, {}).setdefault(gid, {})
        writer = _write_goal_states
    else:
        data = _read_states()
        scope = data.setdefault(user_id, {})
        writer = _write_states
    if op_key and op_key in ((scope.get(p) or {}).get("applied_ops") or []):
        return {"state": scope.get(p), "event": None, "applied": False}
    new_state, ev = _transition(scope.get(p), outcome, reverse)
    _remember_op(new_state, op_key)
    scope[p] = new_state
    if ev:
        ev = {
            **ev, "ts": int(time.time()), "user_id": user_id,
            "session_id": session_id, "path": p, "outcome": outcome,
            **({"goal_id": gid} if gid else {}),
            **({"correction_of": reverse["outcome"]} if reverse else {}),
            **({"op_key": op_key} if op_key else {}),
        }
        # Event BEFORE state, both durable (raise on failure): if the state write fails after the event
        # is down, the retry finds the event by op_key and only writes the state. The op is remembered
        # in the state itself, so the state write is what makes the effect "applied".
        _append_event(ev)
    writer(data)
    return {"state": new_state, "event": ev, "applied": True}


def history(user_id: str | None = None, limit: int = 50, goal_id: str | None = None) -> list[dict]:
    """PATH_STATUS_CHANGED event log — filtered per user (and per goal when requested)."""
    out: list[dict] = []
    try:
        for line in _HISTORY.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if user_id and row.get("user_id") != user_id:
                continue
            if goal_id and row.get("goal_id") != goal_id:
                continue
            out.append(row)
    except OSError:
        pass
    return out[-limit:]
