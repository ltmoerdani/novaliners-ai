"""Canonical same-session Journey timeline — READ-ONLY projection (audit D-08).

GET /session/{sid}/journey answers cross-session verdicts (ADVANCED/STUCK/...) and 409 when the first
session has no prior_session_id. As a result, the REAL events of the first session have no single
unified timeline view. This module fills that gap with a read-only projection from the existing
authorities:

  - Session.events   (durable substratum, the backbone / spine source),
  - Session.moves[].history (Move lifecycle + verdicts),
  - Session.checkpoints     (LIVE checkpoints),
  - Session.evidence        (evidence ledger).

Guarantees:
  - NO second mutable store; pure functions: no writes, no time.time(), no LLM,
    no network.
  - ts is NEVER invented: when a source has no ts, the value is None (sorted last).
  - No duplicate event_id: the spine (Session.events) wins over derived sources; strict dedupe
    per event_id. Checkpoints/evidence use prefixed synthetic ids (ckpt:/evd:) that cannot
    collide with durable event ids (ce-...).
  - base_dir is accepted for caller compatibility; the current projection reads ONLY the given
    object s (does not touch disk), keeping it pure.
"""
from __future__ import annotations

from typing import Any

JOURNEY_VERSION = 1

EVENT_KINDS = (
    "map_created",
    "user_message",
    "engine_reply",
    "move_started",
    "move_executed",
    "move_abandoned",
    "outcome_observed",
    "assessment",
    "checkpoint",
    "evidence",
    # P0-06: the canonical model also carries route-node execution and durable check-ins, so JOURNEY
    # has ONE history instead of a separate chart-only one.
    "route_executed",
    "route_abandoned",
    "route_reset",
    "checkin",
    # NC-08: the legacy plan (diagnosis.day_by_day) is part of the same history. Executed
    # (a completed action) and observed (a reported outcome) stay DISTINCT kinds: never one
    # generic "progress" event.
    "action_completed",
    "action_skipped",
    "action_blocked",
    "action_outcome",
)

# Phase 7: one canonical MoveAction status -> its timeline kind. DONE, SKIPPED and BLOCKED are three
# different facts and are never collapsed into one "progress" event.
_ACTION_STATE_KIND = {
    "DONE": "action_completed",
    "SKIPPED": "action_skipped",
    "BLOCKED": "action_blocked",
}
_ACTION_STATE_TITLE = {
    "DONE": "Action completed",
    "SKIPPED": "Action skipped",
    "BLOCKED": "Action blocked",
}

_NOTE = (
    "Read-only projection from canonical authority (session.events, moves, checkpoints, evidence); "
    "no LLM, no second store, no fabricated timestamps (ts=None when the source carries none)."
)

# Move lifecycle state -> timeline kind. PLANNED is deliberately not mapped: there is no
# equivalent EVENT_KINDS member ("move_planned"), so it must not be invented.
_MOVE_STATE_KIND = {
    "STARTED": "move_started",
    "EXECUTED": "move_executed",
    "ABANDONED": "move_abandoned",
    "OBSERVED": "outcome_observed",
    "VALIDATED": "assessment",
    "INCONCLUSIVE": "assessment",
    "UNSUPPORTED": "assessment",
}

_MOVE_TITLE = {
    "move_started": "Move started",
    "move_executed": "Move executed",
    "move_abandoned": "Move abandoned",
    "outcome_observed": "Outcome observed",
}

_MOVE_EVENT_STATES = ("STARTED", "EXECUTED", "ABANDONED")


def _num(value: Any) -> float | None:
    """A finite number or None — bool is not a number, date strings are not guessed."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _trim(value: Any, limit: int = 160) -> str:
    text = _text(value).strip()
    return text if len(text) <= limit else text[:limit]


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _tokens(text: str) -> list[str]:
    return _text(text).replace(":", " ").split()


def _state_token(text: str) -> str | None:
    """Take STARTED/EXECUTED/ABANDONED from the canonical move_event text.

    Canonical write form: "move <move_id> <STATE>[: note]" — the token after move_id wins.
    Fallback scans tokens for tolerated variants; does not guess when none exists."""
    toks = _tokens(text)
    if len(toks) >= 3 and toks[0] == "move" and toks[2].upper() in _MOVE_EVENT_STATES:
        return toks[2].upper()
    for tok in toks:
        if tok.upper() in _MOVE_EVENT_STATES:
            return tok.upper()
    return None


def _move_id_from_text(text: str) -> str:
    toks = _tokens(text)
    return toks[1] if len(toks) >= 2 and toks[0] == "move" else ""


def _goal_ref(s: Any) -> dict | None:
    goal = getattr(s, "goal", None)
    if goal is None:
        return None
    if isinstance(goal, dict):
        gid, ver = goal.get("goal_id"), goal.get("version")
    else:
        gid, ver = getattr(goal, "goal_id", None), getattr(goal, "version", None)
    if gid is None and ver is None:
        return None
    return {"goal_id": gid, "version": ver}


def build_timeline(s: Any, *, base_dir: Any = None) -> dict:
    """Canonical timeline projection for one session (read-only, deterministic, 0-LLM).

    Returns {'version', 'session_id', 'goal', 'events', 'counts', 'source', 'note'}.
    Order: (ts if present, otherwise +inf) then seq — ts is never invented.
    """
    session_id = _text(getattr(s, "id", None))
    events_in = list(getattr(s, "events", None) or [])
    moves_in = list(getattr(s, "moves", None) or [])
    checkpoints_in = list(getattr(s, "checkpoints", None) or [])
    evidence_in = list(getattr(s, "evidence", None) or [])

    entries: list[dict] = []
    seen_ids: set[str] = set()
    _action_event_ids: set[str] = set()
    _move_event_ids: set[str] = set()

    spine_seqs = [
        e.get("seq") for e in events_in
        if isinstance(e, dict) and isinstance(e.get("seq"), int) and not isinstance(e.get("seq"), bool)
    ]
    next_seq = (max(spine_seqs) + 1) if spine_seqs else 0

    def _next_seq() -> int:
        nonlocal next_seq
        value = next_seq
        next_seq += 1
        return value

    def add(event_id: str, seq: int, ts, kind: str, title: str, detail: str, refs: dict) -> None:
        entries.append({
            "event_id": event_id,
            "seq": seq,
            "ts": ts,
            "kind": kind,
            "title": title,
            "detail": detail,
            "refs": refs,
            "source": "canonical",
        })
        if event_id:
            seen_ids.add(event_id)

    # ---- Spine: Session.events is the authority. All ids (including unmapped rows)
    # are marked first so derived sources never duplicate them.
    for e in events_in:
        if isinstance(e, dict):
            eid = _text(e.get("event_id"))
            if eid:
                seen_ids.add(eid)

    for e in events_in:
        if not isinstance(e, dict):
            continue
        role = _text(e.get("role"))
        kind = _text(e.get("kind"))
        text = _text(e.get("text"))
        eid = _text(e.get("event_id"))
        ts = _num(e.get("ts"))
        seq = e.get("seq")
        if not (isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0):
            seq = _next_seq()
        refs: dict = {}
        if isinstance(e.get("turn"), int) and not isinstance(e.get("turn"), bool):
            refs["turn"] = e["turn"]
        if _text(e.get("status")):
            refs["status"] = _text(e.get("status"))
        if _text(e.get("correlation_id")):
            refs["correlation_id"] = _text(e.get("correlation_id"))

        if kind == "create_map":
            add(eid, seq, ts, "map_created", "Map created", text, refs)
        elif kind == "move_event" and len(_tokens(text)) >= 5 and _tokens(text)[2] == "action":
            # Phase 7 canonical action event: "move <move_id> action <action_id> <STATE>[: note]".
            # It is NOT a Move lifecycle transition, so it never becomes move_started/executed.
            toks = _tokens(text)
            if len(toks) < 5 or toks[0] != "move" or toks[2] != "action":
                continue
            ast = toks[4].upper()
            out_kind = _ACTION_STATE_KIND.get(ast, "action_completed")
            refs["move_id"] = toks[1]
            refs["action_id"] = toks[3]
            refs["state"] = ast
            add(eid, seq, ts, out_kind, _ACTION_STATE_TITLE.get(ast, "Action recorded"), text, refs)
            # The action event that COMPLETED the last required action IS also the Move's execution
            # event. Its id is claimed here, so the lifecycle row below would be dropped: remember it
            # and let the Move lifecycle be reported under a derived id (one accepted event, two
            # facts - the action was done AND the move became executed).
            _action_event_ids.add(eid)
        elif kind == "move_event":
            state = _state_token(text)
            if state is None:
                continue
            out_kind = _MOVE_STATE_KIND[state]
            refs["move_id"] = _text(e.get("correlation_id")) or _move_id_from_text(text)
            refs["state"] = state
            add(eid, seq, ts, out_kind, _MOVE_TITLE.get(out_kind, "Move event"), text, refs)
        elif kind == "outcome_observation":
            if _text(e.get("correlation_id")):
                refs["move_id"] = _text(e.get("correlation_id"))
            add(eid, seq, ts, "outcome_observed", "Outcome observed", text, refs)
        elif role == "engine":
            add(eid, seq, ts, "engine_reply", "Engine reply", text, refs)
        elif role == "user" and kind == "message":
            add(eid, seq, ts, "user_message", "User message", text, refs)
        else:
            # kind outside EVENT_KINDS: do not invent it as a member; the id is already marked so
            # derived sources do not surface it again.
            continue

    # ---- Enrichment: Move lifecycle (only those whose event_id is not yet in the spine).
    for mv in moves_in:
        if not isinstance(mv, dict):
            continue
        mid = _text(mv.get("move_id"))
        for h in list(mv.get("history") or []):
            if not isinstance(h, dict):
                continue
            hid = _text(h.get("event_id"))
            if not hid:
                continue
            if hid in seen_ids and hid not in _action_event_ids:
                continue
            # An event already shown as "Action completed" still has to show the lifecycle change it
            # caused; it gets its own derived id so the two facts never erase each other.
            row_id = hid if hid not in seen_ids else f"mvstate:{mid}:{hid}"
            if row_id in seen_ids:
                continue
            state = _text(h.get("state")).upper()
            out_kind = _MOVE_STATE_KIND.get(state)
            if out_kind is None:
                continue
            refs = {"move_id": mid, "state": state}
            note = _text(h.get("note"))
            if out_kind == "assessment":
                title = f"Assessment: {state}"
                detail = note or state
            else:
                title = _MOVE_TITLE.get(out_kind, "Move event")
                detail = note
            add(row_id, _next_seq(), _num(h.get("ts")), out_kind, title, detail, refs)
            _move_event_ids.add(hid)
        # Phase 7: the Move's ACTION rows carry their own history. Replay the accepted action events
        # that are not already in the spine (id = the durable event id), so the journey keeps them even
        # when the event store is not the source being read.
        for a in list(mv.get("actions") or []):
            if not isinstance(a, dict):
                continue
            aid = _text(a.get("action_id"))
            for h in list(a.get("history") or []):
                if not isinstance(h, dict):
                    continue
                hid = _text(h.get("event_id"))
                if not hid or hid in seen_ids:
                    # Already on the timeline (the durable event row, or the lifecycle row derived
                    # from it): the action fact is never written twice.
                    continue
                ast = _text(h.get("status")).upper()
                out_kind = _ACTION_STATE_KIND.get(ast)
                if out_kind is None:
                    continue
                add(hid, _next_seq(), _num(h.get("ts")), out_kind,
                    _ACTION_STATE_TITLE.get(ast, "Action recorded"),
                    _text(h.get("note")) or _text(a.get("title")),
                    {"move_id": mid, "action_id": aid, "state": ast})
        # Phase 7: the Move's OWN result report (one report per Move, corrections kept as history).
        _rep = mv.get("outcome_report") or {}
        if _text(_rep.get("outcome")) or _text(_rep.get("note")):
            for n, rv in enumerate(_rep.get("revisions") or []):
                if not isinstance(rv, dict):
                    continue
                rts = _num(rv.get("reported_at"))
                if rts is None:
                    continue
                eid = f"moveoutrev:{mid}:{n}"
                if eid not in seen_ids:
                    add(eid, _next_seq(), rts, "action_outcome",
                        "Earlier move result (since corrected): " + _text(rv.get("outcome")),
                        _text(rv.get("note")), {"move_id": mid, "superseded": True})
            rid = _text(_rep.get("event_id")) or f"moveout:{mid}"
            if rid not in seen_ids:
                add(rid, _next_seq(), _num(_rep.get("reported_at")), "action_outcome",
                    "Move result reported: " + (_text(_rep.get("outcome")) or "note only"),
                    _text(_rep.get("note")), {"move_id": mid})

    # ---- Checkpoint (synthetic id ckpt:, cannot collide with ce-...).
    for cp in checkpoints_in:
        if not isinstance(cp, dict):
            continue
        cpid = _text(cp.get("checkpoint_id"))
        version = cp.get("version")
        eid = f"ckpt:{cpid}" if cpid else f"ckpt:{session_id}:{version}"
        if eid in seen_ids:
            continue
        status = _text(cp.get("status"))
        reason = _text(cp.get("reason"))
        ts = _num(cp.get("ts"))
        if ts is None:
            ts = _num((cp.get("binding") or {}).get("ts")) if isinstance(cp.get("binding"), dict) else None
        title = reason or (f"Checkpoint {status}" if status else "Checkpoint")
        detail = " · ".join(p for p in (f"v{version}" if version is not None else "", status) if p)
        add(eid, _next_seq(), ts, "checkpoint", title, detail,
            {"checkpoint_id": cpid, "version": version})

    # ---- Evidence (id sintetis evd:, dedupe per evidence id; quote defensif).
    seen_evidence: set[str] = set()
    for ev in evidence_in:
        ev_id = _text(_get(ev, "id"))
        if not ev_id or ev_id in seen_evidence:
            continue
        seen_evidence.add(ev_id)
        eid = f"evd:{ev_id}"
        if eid in seen_ids:
            continue
        quote = _get(ev, "source_quote")
        if quote is None:
            quote = _get(ev, "quote")
        sig = _text(_get(ev, "signal"))
        if quote is None:
            quote = sig
        title = _trim(quote, 160) or _trim(sig, 160) or "Evidence"
        superseded = bool(_get(ev, "superseded", False))
        detail = ("superseded" + (f" | {sig}" if sig else "")) if superseded else sig
        refs = {"evidence_id": ev_id}
        src = _text(_get(ev, "source"))
        if src:
            refs["source"] = src
        level = _text(_get(ev, "level"))
        if level:
            refs["level"] = level
        add(eid, _next_seq(), _num(_get(ev, "ts")), "evidence", title, detail, refs)

    # ---- Route-node execution (durable per-user ledger; only THIS session's rows).
    user_id = _text(getattr(s, "user_id", None))
    if user_id:
        try:
            from store import route_execution as _rex
            rex_rows = _rex.list_rows(user_id, base_dir)
        except Exception:  # noqa: BLE001
            rex_rows = []
        _route_kind = {"EXECUTED": "route_executed", "ABANDONED": "route_abandoned",
                       "RESET": "route_reset"}
        _route_title = {"route_executed": "Route step executed",
                        "route_abandoned": "Route step set aside",
                        "route_reset": "Route step reset"}
        for i, row in enumerate(rex_rows):
            if not isinstance(row, dict):
                continue
            if _text(row.get("session_id")) != session_id:
                continue
            rid, nid = _text(row.get("route_id")), _text(row.get("node_id"))
            state = _text(row.get("event")).upper()
            out_kind = _route_kind.get(state)
            if not out_kind:
                continue
            ts = _num(row.get("ts"))
            eid = f"rte:{rid}:{nid}:{state}:{ts}:{i}"   # stable identity incl. ledger position
            if eid in seen_ids:
                continue
            add(eid, _next_seq(), ts, out_kind, _route_title[out_kind], "",
                {"route_id": rid, "node_id": nid, "state": state})

    # ---- Check-ins as canonical outcome observations.
    # P1-03 SCOPE: this timeline is SAME-SESSION. The check-in ledger is keyed per user+Goal, so a
    # sibling session that shares the Goal would otherwise be mixed in silently; we filter to rows
    # written by THIS session, exactly like the route-execution rows above. The payload carries
    # scope="session" so a consumer never has to guess which history it is reading.
    if user_id:
        try:
            from store import checkins as _ci
            _goal_id = ((getattr(s, "goal", None) or {}).get("goal_id")) or None
            ci_rows = _ci.latest(user_id, goal_id=_goal_id, base_dir=base_dir)
        except Exception:  # noqa: BLE001
            ci_rows = []
        for row in ci_rows:
            if not isinstance(row, dict):
                continue
            if _text(row.get("session_id")) != session_id:
                continue
            cid = _text(row.get("checkin_id"))
            if not cid:
                continue
            eid = f"ci:{cid}"
            if eid in seen_ids:
                continue
            outcome = _text(row.get("outcome"))
            title = "Check-in" + (f": {outcome}" if outcome else "")
            add(eid, _next_seq(), _num(row.get("created_ts")), "checkin", title,
                _text(row.get("note")),
                {"checkin_id": cid, "outcome": outcome, "day": row.get("day"),
                 "path": _text(row.get("path"))})

    # ---- Legacy plan actions (diagnosis.day_by_day): executed vs observed, kept distinct.
    # A status change with a real done_at is EXECUTED; a reported outcome is OBSERVED. A TODO
    # action with no report contributes nothing (unknown is not an event).
    diag = getattr(s, "diagnosis", None)
    for i, it in enumerate(getattr(diag, "day_by_day", None) or []):
        status = _text(_get(it, "status", ""))
        done_ts = _num(_get(it, "done_at", None))
        reported_ts = _num(_get(it, "reported_at", None))
        text = _trim(_get(it, "text", ""))
        if status in ("DONE", "SKIPPED") and done_ts is not None:
            eid = f"act:{session_id}:{i}:completed"
            if eid not in seen_ids:
                add(eid, _next_seq(), done_ts, "action_completed", "Action completed", text,
                    {"action_index": i, "status": status})
        outcome = _text(_get(it, "outcome", ""))
        if outcome and reported_ts is not None:
            eid = f"act:{session_id}:{i}:outcome"
            if eid not in seen_ids:
                revs = _get(it, "outcome_revisions", None) or []
                add(eid, _next_seq(), reported_ts, "action_outcome",
                    ("Action outcome corrected: " if revs else "Action outcome reported: ") + outcome,
                    _text(_get(it, "note", "")) or text,
                    {"action_index": i, "outcome": outcome, **({"corrected": True} if revs else {})})
        # Phase 6.2: a corrected report keeps the one it replaced as HISTORY. It is shown as superseded
        # and is not a second independent observation of the action.
        for n, rv in enumerate(_get(it, "outcome_revisions", None) or []):
            if not isinstance(rv, dict) or not _text(rv.get("outcome")):
                continue
            rts = _num(rv.get("reported_at"))
            if rts is None:
                continue
            eid = f"act:{session_id}:{i}:outcome:rev{n}"
            if eid not in seen_ids:
                add(eid, _next_seq(), rts, "action_outcome",
                    "Earlier outcome report (since corrected): " + _text(rv.get("outcome")),
                    _text(rv.get("note")) or text,
                    {"action_index": i, "outcome": _text(rv.get("outcome")), "superseded": True})

    # ---- Move-centric: the ONE outcome reported for the current plan's work as a whole. Plan-scoped
    # identity (plan:<session>:<checkpoint>), so it can never collide with a later plan's report.
    _pr = getattr(diag, "plan_report", None) or {}
    _cur_cp = (checkpoints_in[-1] if checkpoints_in else None)
    _cur_cp_id = _text(_get(_cur_cp, "checkpoint_id")) if _cur_cp is not None else ""
    if _text(_pr.get("outcome")) and _num(_pr.get("reported_at")) is not None:
        for n, rv in enumerate(_pr.get("revisions") or []):
            rts = _num(rv.get("reported_at")) if isinstance(rv, dict) else None
            if rts is None or not _text(rv.get("outcome")):
                continue
            eid = f"plan:{session_id}:{_cur_cp_id}:outcome:rev{n}"
            if eid not in seen_ids:
                add(eid, _next_seq(), rts, "action_outcome",
                    "Earlier plan outcome (since corrected): " + _text(rv.get("outcome")),
                    _text(rv.get("note")), {"outcome": _text(rv.get("outcome")), "superseded": True,
                                            "checkpoint_id": _cur_cp_id or None})
        eid = f"plan:{session_id}:{_cur_cp_id}:outcome"
        if eid not in seen_ids:
            add(eid, _next_seq(), _num(_pr.get("reported_at")), "action_outcome",
                "Plan outcome reported: " + _text(_pr.get("outcome")), _text(_pr.get("note")),
                {"outcome": _text(_pr.get("outcome")), "checkpoint_id": _cur_cp_id or None})

    # ---- NC-R5 archived plan actions (checkpoint "carried_plan"): a reassessment archives the plan it
    # REPLACED — with the status/outcome reports accepted against that plan — so swapping s.diagnosis
    # can never erase execution history. Replay those frozen rows as their own events; the current plan
    # above is untouched. Identity is PLAN-scoped (actcp:<session>:<checkpoint_id>:<index>...) so an
    # index can never collide across plan versions. ts is the recorded done_at/reported_at — never
    # invented; an archive row without a ts contributes nothing. Read-only: the archive is never
    # mutated, merged into the live plan, renumbered or re-attributed, and an empty archive is absent.
    last_cp = checkpoints_in[-1] if checkpoints_in else None
    current_cp_id = _text(_get(last_cp, "checkpoint_id")) if last_cp is not None else ""
    for cp in checkpoints_in:                      # oldest -> newest, like the archive grows
        if not isinstance(cp, dict):
            continue
        carried = cp.get("carried_plan")
        if not isinstance(carried, dict):
            continue
        carried_cp_id = _text(carried.get("checkpoint_id"))
        # Guard: an archive naming the CURRENT latest checkpoint would re-attribute the live plan to
        # itself; by construction the archive is the plan this checkpoint REPLACED.
        if carried_cp_id and current_cp_id and carried_cp_id == current_cp_id:
            continue
        carried_version = carried.get("checkpoint_version")
        plan_cp_id = carried_cp_id or _text(cp.get("checkpoint_id"))
        scope = plan_cp_id or (f"v{carried_version}" if carried_version is not None else "")
        if carried_version is not None:
            scope_label = f"plan from checkpoint v{carried_version}"
        elif plan_cp_id:
            scope_label = f"plan from checkpoint {plan_cp_id}"
        else:
            scope_label = "plan from an earlier checkpoint"
        _arp = carried.get("report") or {}
        if _text(_arp.get("outcome")) and _num(_arp.get("reported_at")) is not None:
            eid = f"plancp:{session_id}:{scope}:outcome"
            if eid not in seen_ids:
                add(eid, _next_seq(), _num(_arp.get("reported_at")), "action_outcome",
                    "Plan outcome reported: " + _text(_arp.get("outcome")),
                    " · ".join(p for p in (_text(_arp.get("note")), scope_label) if p),
                    {"outcome": _text(_arp.get("outcome")), "checkpoint_id": plan_cp_id or None,
                     "checkpoint_version": carried_version})
        for i, it in enumerate(carried.get("actions") or []):
            status = _text(_get(it, "status", ""))
            done_ts = _num(_get(it, "done_at", None))
            reported_ts = _num(_get(it, "reported_at", None))
            text = _trim(_get(it, "text", ""))
            if status in ("DONE", "SKIPPED") and done_ts is not None:
                eid = f"actcp:{session_id}:{scope}:{i}:completed"
                if eid not in seen_ids:
                    add(eid, _next_seq(), done_ts, "action_completed", "Action completed",
                        " · ".join(p for p in (text, scope_label) if p),
                        {"action_index": i, "status": status,
                         "checkpoint_id": plan_cp_id or None,
                         "checkpoint_version": carried_version})
            outcome = _text(_get(it, "outcome", ""))
            if outcome and reported_ts is not None:
                eid = f"actcp:{session_id}:{scope}:{i}:outcome"
                if eid not in seen_ids:
                    add(eid, _next_seq(), reported_ts, "action_outcome",
                        "Action outcome reported: " + outcome,
                        " · ".join(p for p in (_text(_get(it, "note", "")) or text, scope_label) if p),
                        {"action_index": i, "outcome": outcome,
                         "checkpoint_id": plan_cp_id or None,
                         "checkpoint_version": carried_version})

    def sort_key(entry: dict):
        ts = _num(entry.get("ts"))
        return (float("inf") if ts is None else ts, entry.get("seq", 0))

    events = sorted(entries, key=sort_key)
    counts = {kind: 0 for kind in EVENT_KINDS}
    for entry in events:
        if entry["kind"] in counts:
            counts[entry["kind"]] += 1

    return {
        "version": JOURNEY_VERSION,
        "session_id": session_id,
        "goal": _goal_ref(s),
        "events": events,
        "counts": counts,
        "source": "canonical",
        "scope": "session",   # P1-03: never a silent mix of same-session and map-wide histories
        "note": _NOTE,
    }


def timeline_summary(timeline: Any, limit: int = 200) -> dict:
    """Size-safe slice for the API payload: events[:limit] + intact counts.

    The real event total is still reported via total/truncated so trimming does not
    masquerade as data loss."""
    if not isinstance(timeline, dict):
        return {
            "version": JOURNEY_VERSION,
            "session_id": "",
            "goal": None,
            "events": [],
            "counts": {kind: 0 for kind in EVENT_KINDS},
            "source": "canonical",
            "note": _NOTE,
            "total": 0,
            "truncated": False,
        }
    events = list(timeline.get("events") or [])
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 200
    if n < 0:
        n = 0
    out = dict(timeline)
    out["events"] = events[:n]
    out["counts"] = dict(timeline.get("counts") or {kind: 0 for kind in EVENT_KINDS})
    out["total"] = len(events)
    out["truncated"] = len(events) > n
    return out
