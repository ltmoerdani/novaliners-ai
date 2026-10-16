"""Phase 6.2 — accepted same-session OBSERVATION context for reassessment synthesis.

Why this exists: reassessment eligibility fires on accepted observations (action outcomes, check-ins,
Move observations), but the journey context was compiled only from a PRIOR session. In a single
session `prior_session_id` is empty, so the synthesis was silently starved of the very observations
that made the reassessment eligible. This module derives a typed, bounded, deterministic context from
the durable records that already exist - it adds no store and calls no LLM.

Epistemic rules (never relaxed here):
  * a reported outcome is SELF_REPORTED, never verified evidence;
  * a completed action with no outcome is EXECUTED_UNMEASURED (completion != outcome);
  * missing data is "not reported", never zero and never a negative;
  * a corrected report contributes ONE effective observation; the superseded one is history;
  * nothing here is added to the evidence ledger, so it cannot be counted twice as independent support.
"""
from __future__ import annotations

from typing import Any

CONTEXT_VERSION = "ao.v1"
_MAX_ACTIONS, _MAX_CHECKINS, _MAX_MOVES, _MAX_HISTORY = 12, 8, 8, 6
_NOTE_LIMIT = 240
_TEXT_LIMIT = 160

SELF_REPORTED = "SELF_REPORTED"
EXECUTED_UNMEASURED = "EXECUTED_UNMEASURED"
NOT_EXECUTED = "NOT_EXECUTED"
HISTORICAL = "HISTORICAL"


def _trim(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _action_row(i: int, it: Any, *, plan: str) -> dict | None:
    status = str(getattr(it, "status", None)
                 or (it.get("status") if isinstance(it, dict) else "TODO") or "TODO").upper()
    def g(k, d=""):
        return getattr(it, k, None) if not isinstance(it, dict) else it.get(k, d)
    outcome = str(g("outcome") or "")
    note = _trim(g("note"), _NOTE_LIMIT)
    if status == "TODO" and not outcome and not note:
        return None          # nothing was done or observed: absence of a record is not an observation
    if outcome:
        epistemic = SELF_REPORTED
    elif status == "DONE":
        epistemic = EXECUTED_UNMEASURED
    else:
        epistemic = NOT_EXECUTED
    row = {
        "ref": f"{plan}:action:{i}",
        "action": _trim(g("text"), _TEXT_LIMIT),
        "execution": status,
        "outcome": outcome or None,          # None = not reported (unknown), never "no effect"
        "note": note or None,
        "epistemic": epistemic,
        "verified": False,
    }
    revs = g("outcome_revisions") or []
    if revs:
        row["corrected_from"] = [
            {"outcome": r.get("outcome") or None, "note": _trim(r.get("note"), 80) or None}
            for r in revs[-2:] if isinstance(r, dict)]
    return row


def accepted_observation_context(s: Any, *, base_dir: Any = None) -> dict | None:
    """The accepted observations of this session (check-ins of earlier sessions
    carry their own scope), ready for the synthesis prompt. None when empty."""
    diag = getattr(s, "diagnosis", None)
    actions = []
    for i, it in enumerate(getattr(diag, "day_by_day", None) or []):
        row = _action_row(i, it, plan="current")
        if row:
            actions.append(row)
    # Plans archived by earlier reassessments stay visible, flagged HISTORICAL: an old plan's
    # results are context the new synthesis must acknowledge, not current-plan progress.
    history = []
    for cp in reversed(getattr(s, "checkpoints", None) or []):
        carried = cp.get("carried_plan") or {}
        for a in carried.get("actions") or []:
            row = _action_row(int(a.get("index") or 0), a, plan=str(carried.get("checkpoint_id") or "prior"))
            if row:
                row["epistemic_scope"] = HISTORICAL
                history.append(row)
        if len(history) >= _MAX_HISTORY:
            break
    plan_obs = None
    pr = getattr(diag, "plan_report", None) or {}
    if pr.get("outcome") or pr.get("note"):
        plan_obs = {"ref": "current:plan", "outcome": pr.get("outcome") or None,
                    "note": _trim(pr.get("note"), _NOTE_LIMIT) or None,
                    "epistemic": SELF_REPORTED if pr.get("outcome") else EXECUTED_UNMEASURED,
                    "verified": False, "corrections": len(pr.get("revisions") or [])}
    checkins = []
    user_id = getattr(s, "user_id", "") or ""
    if user_id:
        try:
            from store import checkins as _ck
            goal_id = ((getattr(s, "goal", None) or {}).get("goal_id")) or None
            for r in _ck.latest(user_id, goal_id=goal_id, base_dir=base_dir, limit=_MAX_CHECKINS):
                # Provenance: a check-in belongs to THIS session only when it was recorded in it.
                # Rows of other sessions (same business/Goal) are real history, kept but labelled so.
                scope = "THIS_SESSION" if str(r.get("session_id") or "") == str(getattr(s, "id", "")) \
                    else "PRIOR_SESSION_SAME_GOAL"
                checkins.append({
                    "scope": scope, "ts": r.get("created_ts"),
                    "ref": f"checkin:{r.get('checkin_id')}",
                    "outcome": r.get("outcome") or r.get("action_outcome") or None,
                    "note": _trim(r.get("note"), _NOTE_LIMIT) or None,
                    "epistemic": SELF_REPORTED, "verified": False})
        except Exception:  # noqa: BLE001 - a broken check-in file must not block a diagnosis
            pass
    moves = []
    for mv in (getattr(s, "moves", None) or [])[:_MAX_MOVES]:
        verdict = (mv.get("assessment") or {}).get("verdict")
        rep = mv.get("outcome_report") or {}
        if not (mv.get("executed_ts") or verdict or mv.get("observation_claim_refs")
                or rep.get("outcome") or rep.get("note")):
            continue
        prog = mv.get("progress") or {}
        done = sum(1 for a in (mv.get("actions") or []) if a.get("status") == "DONE")
        moves.append({
            "ref": f"move:{mv.get('move_id')}", "executed": bool(mv.get("executed_ts")),
            "verdict": verdict or None,
            "claim_refs": sorted(mv.get("observation_claim_refs") or [])[:6],
            # Phase 7: the Move's OWN action progress and the result reported for the Move as a whole.
            # A self-reported result is not evidence of the Goal; it is what the person observed.
            "actions_done": done, "actions_total": len(mv.get("actions") or []),
            "actions_required_open": int(prog.get("open") or 0),
            "result": rep.get("outcome") or None, "result_note": _trim(rep.get("note"), _NOTE_LIMIT) or None})
    if not (actions or history or checkins or moves or plan_obs):
        return None
    unknown = []
    if any(a["epistemic"] == EXECUTED_UNMEASURED for a in actions):
        unknown.append("Some completed actions have no reported result yet.")
    return {
        "version": CONTEXT_VERSION,
        "plan_observation": plan_obs,
        "action_observations": actions[:_MAX_ACTIONS],
        "prior_plan_observations": history[:_MAX_HISTORY],
        "checkin_observations": checkins,
        "canonical_move_observations": moves,
        "uncertainty": unknown,
        # Overlap rule: these records are NOT in the evidence ledger, so they are not independent
        # support for any claim. They inform what was done and seen; they do not verify anything.
        "counted_as_independent_evidence": False,
    }


def prompt_lines(ctx: dict | None) -> list[str]:
    """Short, label-only rendering for the synthesis prompt (values stay data)."""
    if not ctx:
        return []
    lines = ["SESSION OBSERVATIONS (accepted from the user, this session unless\n"
             "             marked as earlier history; SELF-REPORTED, NOT verified evidence -\n"
             "             never read a reply as payment, never treat 'not reported' as zero):"]
    po = ctx.get("plan_observation")
    if po:
        res = po["outcome"] if po["outcome"] else "result not reported"
        extra = f' | user note: "{po["note"]}"' if po.get("note") else ""
        lines.append(f"- Result the user reported for the plan's work as a whole: {res}{extra}.")
    for mv in ctx.get("canonical_move_observations") or []:
        if not (mv.get("result") or mv.get("result_note") or mv.get("verdict")
                or mv.get("actions_total")):
            continue
        res = mv.get("result") or "result not reported"
        extra = f' | user note: "{mv["result_note"]}"' if mv.get("result_note") else ""
        prog = f' ({mv.get("actions_done", 0)} of {mv.get("actions_total", 0)} actions done)'
        verd = f' | engine verdict: {mv["verdict"]}' if mv.get("verdict") else ""
        lines.append(f'- Move {mv.get("ref")}{prog}: {res}{extra}{verd}.')
    for a in ctx.get("action_observations") or []:
        res = a["outcome"] if a["outcome"] else "result not reported"
        extra = f' | user note: "{a["note"]}"' if a.get("note") else ""
        lines.append(f'- Action "{a["action"]}": {a["execution"]}, {res}{extra}.')
    for a in ctx.get("prior_plan_observations") or []:
        res = a["outcome"] if a["outcome"] else "result not reported"
        extra = f' | user note: "{a["note"]}"' if a.get("note") else ""
        lines.append(f'- Earlier plan action "{a["action"]}": {a["execution"]}, {res}{extra} (historical).')
    for c in ctx.get("checkin_observations") or []:
        tag = "" if c.get("scope") == "THIS_SESSION" else " (earlier session, same goal - history)"
        lines.append(f'- Check-in{tag}: {c["outcome"] or "no outcome"}'
                     + (f' | "{c["note"]}"' if c.get("note") else "") + ".")
    for m in ctx.get("canonical_move_observations") or []:
        lines.append(f'- Move {m["ref"]}: executed={m["executed"]}, verdict={m["verdict"] or "none"}.')
    for u in ctx.get("uncertainty") or []:
        lines.append(f"- Unknown: {u}")
    lines.append("Revise the assessment where these observations bear on it, keep the evidence hierarchy, "
                 "and do not repeat a recipe the user already ran without a result.")
    return lines
