"""Durable ConversationEvent — conversation substratum that PERSISTS (int 16 §R3-A, EC-01, BC-04).

Principles:
- User messages are FACTS that happened, not processing output: they are persisted FIRST
  before the LLM/understanding touches them. A processing failure does not lose the message.
- Immutable: the original text is never modified; status changes are processed via status markers.
- Idempotent: the client idempotency key prevents double semantic effects on resubmissions.
- Persistence failures are RAISED (not swallowed) — the caller honestly rejects the turn
  before paying for LLM calls.

Storage: append-only JSONL per session (`store/events/<sid>.jsonl`) + a mirror in the session
(`Session.events`) so that a session reload restores the event list without reading the JSONL.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from pydantic import BaseModel, Field

EVENTS_DIR = Path(__file__).resolve().parent / "events"

STATUS_RECEIVED = "received"
STATUS_ACCEPTED = "accepted"              # observation passed the in-memory commit, snapshot NOT yet durable
STATUS_COMMITTED = "committed"            # canonical observation + session snapshot are durable
STATUS_PERSIST_FAILED = "persist_failed"  # in-memory commit exists, snapshot failed (retry allowed)
STATUS_UNDERSTANDING_FAILED = "understanding_failed"
STATUS_DUPLICATE = "duplicate"

# Status progression order: a lagging/stale JSONL amendment must not LOWER the snapshot status.
STATUS_RANK = {STATUS_RECEIVED: 0, STATUS_UNDERSTANDING_FAILED: 1, STATUS_PERSIST_FAILED: 2,
               STATUS_ACCEPTED: 3, STATUS_COMMITTED: 4, STATUS_DUPLICATE: 0}


def _rank(status) -> int:
    return STATUS_RANK.get(status, 0)


KIND_CREATE_MAP = "create_map"            # initial Start/Create Map input (BC-04)
KIND_MESSAGE = "message"
KIND_ENGINE = "engine"                    # engine reply (correlation to the user event)
KIND_OUTCOME = "outcome_observation"      # Move result reported by the user (R6); same pipeline
KIND_MOVE_EVENT = "move_event"            # STARTED/EXECUTED/ABANDONED — durable attribution (S2-E)


class EventPersistenceError(RuntimeError):
    """Failure to write a durable event — must be visible, not swallowed."""


class SessionPersistenceError(EventPersistenceError):
    """The canonical session snapshot failed to persist — the turn MUST NOT be ACKed as successful."""


class ConversationEvent(BaseModel):
    """One conversation event that the pipeline cannot fabricate again."""

    event_id: str = Field(description="ce-<sid>-<seq:04d>; assigned by the store, not the client")
    seq: int = Field(ge=0, description="event order within the session (basis for deterministic claim id)")
    session_id: str
    role: str = Field(description="user | engine")
    kind: str = Field(description="create_map | message | engine")
    text: str = Field(description="original text, NOT modified")
    turn: int = Field(ge=0, description="user turn order (0 = initial Create Map input)")
    ts: float = Field(default_factory=lambda: time.time())
    status: str = STATUS_RECEIVED
    idempotency_key: str = ""
    correlation_id: str = Field(default="", description="user event that triggered it (for engine)")
    processing_note: str = ""
    result: dict | None = Field(
        default=None, description="R3.2: full response returned to the client (engine event) — "
                                  "basis for result recovery on retry, not recomputation")


def _event_file(session_id: str) -> Path:
    safe = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
    if not safe:
        raise EventPersistenceError("session id is not valid for event storage")
    return EVENTS_DIR / f"{safe}.jsonl"


def find_by_idempotency_key(session, key: str):
    """First event with this idempotency key (or None)."""
    if not key:
        return None
    for e in getattr(session, "events", None) or []:
        if e.get("idempotency_key") == key:
            return e
    return None


def find_engine_event(session, user_event_id: str, latest: bool = False):
    """Engine reply already recorded for this user event (exactly-once reply).

    `latest=True` takes the LATEST reply (MC01-2: after a reasoning retry there is >1 reply
    correlated to the same event — idempotent recovery must use the newest result, not the old
    degraded reply)."""
    found = None
    for e in getattr(session, "events", None) or []:
        if e.get("role") == "engine" and e.get("correlation_id") == user_event_id:
            found = e
            if not latest:
                return e
    return found


def _durable_append(path: Path, text: str) -> None:
    """Append one or more JSONL lines durably: flush + fsync the file.

    Claim made: after this function returns without error, the line has been handed to the
    storage device (fsync). NOT claimed to be immune to devices that lie about flush or to
    media failure; that is outside the MVP scope. If the file ends without a newline
    (an earlier torn write), a newline is added first so the new line does not stick to the
    damaged trailing line."""
    prefix = ""
    try:
        if path.exists() and path.stat().st_size > 0:
            with path.open("rb") as rf:
                rf.seek(-1, os.SEEK_END)
                if rf.read(1) != b"\n":
                    prefix = "\n"
    except OSError:
        pass
    with path.open("a", encoding="utf-8") as f:
        f.write(prefix + text)
        f.flush()
        os.fsync(f.fileno())


def append_event(
    session,
    *,
    role: str,
    kind: str,
    text: str,
    idempotency_key: str = "",
    correlation_id: str = "",
    result: dict | None = None,
) -> dict:
    """Write the event durably and mirror it into the session. Raise EventPersistenceError on failure.

    Determines `turn`: the next user turn for the user role; an engine reply uses the
    turn of the correlated user event.
    """
    events = getattr(session, "events", None)
    if events is None:
        events = []
        setattr(session, "events", events)
    seq = len(events)
    if role == "user":
        turn = 1 + sum(1 for e in events if e.get("role") == "user")
    else:
        turn = next((e.get("turn", 0) for e in reversed(events) if e.get("role") == "user"), 0)
    ev = ConversationEvent(
        event_id=f"ce-{session.id}-{seq:04d}",
        seq=seq,
        session_id=session.id,
        role=role,
        kind=kind,
        text=text,
        turn=turn,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        result=result,
    )
    payload = ev.model_dump()
    try:
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        _durable_append(_event_file(session.id), json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise EventPersistenceError(
            f"failed to write event {ev.event_id}: {type(exc).__name__}: {exc}"
        ) from exc
    events.append(payload)
    return payload


def mark_event_status(session, event_id: str, status: str, note: str = "") -> None:
    """Update the event's processing status (session mirror + new JSONL line as audit).

    JSONL is append-only: the new status is written as an amending line `{"event_id": ..., "status": ...}`.
    The original event line is never rewritten.
    """
    for e in getattr(session, "events", None) or []:
        if e.get("event_id") == event_id:
            if _rank(e.get("status")) > _rank(status) and e.get("status") == STATUS_COMMITTED \
                    and status != STATUS_COMMITTED:
                # committed event reprocessed (e.g. reprocess) — do not lower the durable status
                return
            e["status"] = status
            if note:
                e["processing_note"] = (e.get("processing_note", "") + " | " + note).strip(" |")
            break
    else:
        return
    try:
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        _durable_append(_event_file(session.id), json.dumps(
            {"event_id": event_id, "status": status, "note": note}, ensure_ascii=False) + "\n")
    except OSError:
        # status is audit, not primary data: an amendment failure does not cancel the turn,
        # but remains visible through the session mirror (saved by store.save).
        pass


def load_events_checked(session_id: str) -> tuple[list[dict], list[dict]]:
    """Load durable events + integrity report.

    Fail-closed policy: lines that cannot be parsed are NOT silently discarded.
    - last line without newline & unparsable = `torn_tail` (crash mid-write; expected)
    - broken line in the middle = `malformed_row` (corruption; the rest is still read)
    - amendment for an unknown event = `orphan_amendment`
    The caller decides how to react (recovery_issues in SessionStore); data is never invented."""
    f = _event_file(session_id)
    issues: list[dict] = []
    if not f.exists():
        return [], issues
    out: list[dict] = []
    try:
        raw = f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [], [{"kind": "unreadable", "detail": f"{type(exc).__name__}: {exc}"}]
    lines = raw.split("\n")
    ends_clean = raw.endswith("\n")
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        is_last_unterminated = (idx == len(lines) - 1) and not ends_clean
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            issues.append({"kind": "torn_tail" if is_last_unterminated else "malformed_row",
                           "detail": f"baris {idx + 1}"})
            continue
        if not isinstance(row, dict):
            issues.append({"kind": "malformed_row", "detail": f"baris {idx + 1}: bukan objek"})
            continue
        if "role" in row:  # full event row
            out.append(row)
        elif "event_id" in row:  # row amends status
            for e in out:
                if e["event_id"] == row["event_id"]:
                    if _rank(row.get("status")) >= _rank(e.get("status")):
                        e["status"] = row.get("status", e.get("status"))
                    break
            else:
                issues.append({"kind": "orphan_amendment", "detail": row.get("event_id", "?")})
    return out, issues


def load_events(session_id: str) -> list[dict]:
    """Reload durable events from JSONL (replay/audit). See load_events_checked."""
    return load_events_checked(session_id)[0]


def reconcile_session_events(session) -> int:
    """Restore the `session.events` mirror from the durable JSONL (post-restart recovery).

    JSONL is the source of truth for events: events present in the JSONL but missing from the
    session snapshot (snapshot failed to persist) are re-inserted, and status is aligned with the
    amending lines. Returns the number of restored events. Does not call the LLM; semantic
    reprocessing happens through retry (idempotency key / same event).
    """
    durable = load_events(session.id)
    mirror = getattr(session, "events", None)
    if mirror is None:
        mirror = []
        setattr(session, "events", mirror)
    by_id = {e.get("event_id"): e for e in mirror}
    restored = 0
    for e in durable:
        cur = by_id.get(e["event_id"])
        if cur is None:
            mirror.append(dict(e))
            restored += 1
        else:
            # forward only: a lagging JSONL amendment does not lower the snapshot status
            if _rank(e.get("status")) > _rank(cur.get("status")):
                cur["status"] = e["status"]
    mirror.sort(key=lambda e: e.get("seq", 0))
    return restored


def user_event_of_turn(session, turn: int):
    """User event for a given turn (anchoring of quote verification)."""
    for e in getattr(session, "events", None) or []:
        if e.get("role") == "user" and e.get("turn") == turn:
            return e
    return None
