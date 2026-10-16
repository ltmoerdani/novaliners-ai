"""A Move as a MEASURED EXPERIMENT + lifecycle + outcome linkage (int 16 §R6-D/E).

A Move is not generic advice. It binds: the objective, Goal, Path, hypothesis, contextual instructions,
preconditions, constraints, expected evidence, measurement method, observation window, completion
criteria, and the outcome reference.

Cycle (one vocabulary; `EXECUTED` aligns with `store/route_execution` — execution ≠ credit, INV-R8):

    PLANNED ─► STARTED ─► EXECUTED ─► OBSERVED ─► VALIDATED | INCONCLUSIVE | UNSUPPORTED
        └────────┴───────────┴──► ABANDONED

- EXECUTED is only a user-reported EVENT; not success.
- OBSERVED = a canonical claim exists (from an `outcome_observation` event) bound to this Move.
- Verdicts (VALIDATED/INCONCLUSIVE/UNSUPPORTED) are proposed by reasoning and CHECKED by guard (G11);
  VALIDATED means the observed signal aligns with the expected evidence — NOT causal proof
  (`causal_claim` stays `not_established`; temporal order alone does not establish cause).
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

PLANNED, STARTED, EXECUTED, OBSERVED = "PLANNED", "STARTED", "EXECUTED", "OBSERVED"
VALIDATED, INCONCLUSIVE, UNSUPPORTED, ABANDONED = "VALIDATED", "INCONCLUSIVE", "UNSUPPORTED", "ABANDONED"
LIFECYCLE = (PLANNED, STARTED, EXECUTED, OBSERVED, VALIDATED, INCONCLUSIVE, UNSUPPORTED, ABANDONED)
VERDICTS = (VALIDATED, INCONCLUSIVE, UNSUPPORTED)

ALLOWED: dict[str, set[str]] = {
    PLANNED: {STARTED, EXECUTED, ABANDONED},
    STARTED: {EXECUTED, ABANDONED},
    EXECUTED: {OBSERVED, ABANDONED},
    OBSERVED: {OBSERVED, VALIDATED, INCONCLUSIVE, UNSUPPORTED},
    INCONCLUSIVE: {OBSERVED, ABANDONED},     # more evidence can still be collected
    VALIDATED: set(), UNSUPPORTED: set(), ABANDONED: set(),
}
USER_EVENTS = (STARTED, EXECUTED, ABANDONED)   # the ones a user may report directly

MIN_WINDOW_DAYS, MAX_WINDOW_DAYS = 1, 180
REQUIRED_DESIGN = ("objective", "measurement_method", "expected_evidence", "completion_criteria")

# ── Phase 7: the canonical Move ACTION LIST ─────────────────────────────────────────────────────
# A Move OWNS its executable actions. This list is the ONE live execution record for the work:
# Maps, Moves, Journey and the navigation projection all read the SAME rows through this module.
# `diagnosis.day_by_day` is LEGACY history (see internal-docs); it is never consulted here
# and never written by the action path.
ACTION_TODO, ACTION_DONE, ACTION_SKIPPED, ACTION_BLOCKED = "TODO", "DONE", "SKIPPED", "BLOCKED"
ACTION_STATES = (ACTION_TODO, ACTION_DONE, ACTION_SKIPPED, ACTION_BLOCKED)
# A technical bound on payload/UI size — NOT a product schedule. Fewer actions is normal (1 is a
# perfectly valid Move) and the count is content-driven; only the upper bound is enforced.
MAX_ACTIONS = 12
# The action list is editable while the work is still being done. AFTER execution the rows are
# history — EXCEPT for the narrow correction path below (no observation/verdict has consumed the
# execution yet), so a mis-click cannot strand a person with a wrong record.
ACTION_OPEN_LIFECYCLES = (PLANNED, STARTED)
EXECUTION_BLOCKING = (ACTION_SKIPPED, ACTION_BLOCKED)

# R1.5 (internal-docs §3): a typed
# Move -> RouteNode reference. MUST be distinguished from `binding_id`, which is
# a DECISION-BASIS FINGERPRINT ("bd-<hash>" over State/Goal/KB/prompts —
# app/binding.py:71), NOT a RouteNode identity. Reusing binding_id for this
# relation is forbidden.
ROUTE_REF_KEYS = ("route_id", "node_id", "route_revision")


def _validated_route_ref(ref: Any) -> dict | None:
    """A valid route_node_ref shape: {route_id, node_id: str, route_revision: int>=1}.
    None when absent; MoveError when half-formed/wrong-typed — a typed reference
    must never silently degenerate into a free string."""
    if ref is None:
        return None
    if not isinstance(ref, dict) or set(ref) != set(ROUTE_REF_KEYS):
        raise MoveError(
            f"route_node_ref wajib dict dengan kunci persis {list(ROUTE_REF_KEYS)} "
            f"(bertipe — bukan binding_id/free string): dapat {ref!r}")
    if not isinstance(ref["route_id"], str) or not ref["route_id"]:
        raise MoveError("route_node_ref.route_id wajib string non-empty")
    if not isinstance(ref["node_id"], str) or not ref["node_id"]:
        raise MoveError("route_node_ref.node_id wajib string non-empty")
    if not isinstance(ref["route_revision"], int) or isinstance(ref["route_revision"], bool) \
            or ref["route_revision"] < 1:
        raise MoveError("route_node_ref.route_revision wajib int >= 1")
    return {k: ref[k] for k in ROUTE_REF_KEYS}


class MoveError(ValueError):
    pass


def design_problems(d: dict | None) -> list[str]:
    """Measured-design completeness (used by guard G10). Doesn't judge content quality — only that
    content EXISTS.

    Phase 7: an executable Move owns its ACTION LIST. A design without actions is not an executable
    Move, so it is rejected here (the reasoner repairs once with this feedback). No day/schedule
    field is required or accepted — the person decides when to work."""
    if not d:
        return ["move_design wajib untuk langkah yang dapat dieksekusi"]
    out = [f"move_design.{k} kosong" for k in REQUIRED_DESIGN if not d.get(k)]
    w = d.get("observation_window_days")
    if not isinstance(w, int) or not (MIN_WINDOW_DAYS <= w <= MAX_WINDOW_DAYS):
        out.append(f"move_design.observation_window_days harus {MIN_WINDOW_DAYS}..{MAX_WINDOW_DAYS} hari")
    out.extend(_action_spec_problems(d.get("actions")))
    return out


def _action_spec_problems(specs: Any) -> list[str]:
    """Action-list completeness for G10. A Move needs 1..MAX_ACTIONS executable actions; each has
    ONE concrete title. `depends_on` (optional) may only point at EARLIER positions — an action
    order is never inferred from the array, and no schedule/day is modelled here."""
    rows = specs if isinstance(specs, list) else []
    if not rows:
        return ["move_design.actions kosong: langkah yang dapat dieksekusi wajib memiliki 1..%d "
                "aksi konkret (tanpa jadwal harian)" % MAX_ACTIONS]
    out: list[str] = []
    if len(rows) > MAX_ACTIONS:
        out.append(f"move_design.actions melebihi batas teknis {MAX_ACTIONS} aksi")
    for i, row in enumerate(rows):
        title = row if isinstance(row, str) else (
            (row or {}).get("title") if isinstance(row, dict) else "")
        title = str(title or "").strip()
        if len(title) < 3:
            out.append(f"move_design.actions[{i}] tanpa judul aksi yang konkret")
        deps = (row or {}).get("depends_on") if isinstance(row, dict) else None
        for dep in deps or []:
            if not isinstance(dep, int) or isinstance(dep, bool) or not (1 <= dep < i + 1):
                out.append(f"move_design.actions[{i}].depends_on hanya boleh menunjuk posisi aksi "
                           f"SEBELUMNYA (1..{i}); dapat {dep!r}")
    if rows and not out and not any(
            len(str((r if isinstance(r, str) else (r or {}).get("title", ""))).strip()) >= 3
            for r in rows):
        out.append("move_design.actions tanpa satu pun judul yang dapat dieksekusi")
    return out


# ── action rows ───────────────────────────────────────────────────────────────────────────────

def _action_id(move_id: str, ordinal: int, title: str) -> str:
    """Server-issued, STABLE for a (move, position, title): a replayed creation yields the same ids,
    while a read never derives an action's identity from its display position."""
    return "ma-" + hashlib.sha1(f"{move_id}|{ordinal}|{title.strip()}".encode()).hexdigest()[:10]


def build_actions(move_id: str, specs: Any) -> list[dict]:
    """Materialise `move_design.actions` into canonical MoveAction rows.

    Accepted spec shapes: a plain string (the action title) or an object
    `{title, instruction, required, depends_on:[1-based earlier positions], supporting_refs}`.
    Identity is issued HERE (server side) and never taken from the client or from array order at
    read time. An explicit `depends_on` is the ONLY thing that can restrict order."""
    spec_list = (specs if isinstance(specs, list) else [])[:MAX_ACTIONS]
    rows: list[dict] = []
    row_of: dict[int, int] = {}          # 0-based spec position -> index in `rows`
    for i, spec in enumerate(spec_list, start=1):
        if isinstance(spec, str):
            spec = {"title": spec}
        spec = spec if isinstance(spec, dict) else {}
        title = " ".join(str(spec.get("title") or "").split())
        if not title:
            continue                     # a skipped spec never shifts another's dependency edge
        row_of[i - 1] = len(rows)
        pos = len(rows) + 1               # display position of a KEPT action (1..n, no gaps)
        rows.append({
            "action_id": _action_id(move_id, pos, title),
            "move_id": move_id,
            "ordinal": pos,                   # display order ONLY; carrying no execution authority
            "title": title[:240],
            "instruction": str(spec.get("instruction") or "").strip()[:600],
            "status": ACTION_TODO,
            "required": bool(spec.get("required", True)),
            "depends_on_action_ids": [],      # resolved below (positions -> ids)
            "completed_at": None,
            "execution_event_id": None,
            "supporting_refs": [str(x) for x in (spec.get("supporting_refs") or [])][:6],
            "note": "",
            "history": [],
        })
    for i, spec in enumerate(spec_list):
        if i not in row_of:
            continue
        deps = spec.get("depends_on") if isinstance(spec, dict) else None
        ids: list[str] = []
        for dep in deps or []:
            # A 1-based position of an EARLIER spec, resolved through the kept rows: a dropped spec
            # (empty title) cannot silently re-point the dependency at another action.
            if not isinstance(dep, int) or isinstance(dep, bool) or not (1 <= dep <= i):
                continue
            if (dep - 1) in row_of:
                ids.append(rows[row_of[dep - 1]]["action_id"])
        rows[row_of[i]]["depends_on_action_ids"] = sorted(set(ids))
    return rows


def get_action(mv: dict | None, action_id: str) -> dict | None:
    return next((a for a in ((mv or {}).get("actions") or [])
                 if str(a.get("action_id")) == str(action_id)), None)


def action_progress(mv: dict) -> dict:
    """Honest counts. DONE, SKIPPED and BLOCKED stay three different facts: only DONE is execution.
    `complete` means every REQUIRED action is genuinely done — a skipped or blocked required action
    keeps the Move unresolved instead of faking completion."""
    acts = list(mv.get("actions") or [])
    req = [a for a in acts if a.get("required", True)]
    done = [a for a in acts if a.get("status") == ACTION_DONE]
    req_done = [a for a in req if a.get("status") == ACTION_DONE]
    skipped = [a for a in acts if a.get("status") == ACTION_SKIPPED]
    blocked = [a for a in acts if a.get("status") == ACTION_BLOCKED]
    open_ = [a for a in acts if a.get("status") == ACTION_TODO]
    return {
        "total": len(acts), "required": len(req), "done": len(done), "required_done": len(req_done),
        "skipped": len(skipped), "blocked": len(blocked), "open": len(open_),
        "complete": bool(req) and len(req_done) == len(req),
        "next_action_id": (open_[0]["action_id"] if open_ else None),
        "unresolved_action_ids": [a["action_id"] for a in req
                                 if a.get("status") in (ACTION_TODO,) + EXECUTION_BLOCKING],
    }


def _moves(s: Any) -> list[dict]:
    m = getattr(s, "moves", None)
    if m is None:
        m = []
        s.moves = m
    return m


def get_move(s: Any, move_id: str) -> dict | None:
    return next((m for m in _moves(s) if m["move_id"] == move_id), None)


def _goal_scope_problems(s: Any, mv: dict) -> list[str]:
    """BC-02/BC-03/CP-30: a Move is valid only in the Goal + version where it was created. An explicit
    Goal switch (A-22) or a material revision (GR-20) makes old Moves STALE — their observations and
    verdicts must no longer touch the new Goal's hypotheses/state (Goal A must not contaminate Goal B).

    Moves without Goal linkage (legacy / anonymous sessions) are not enforced: missing linkage is not
    proof that it belongs to another Goal."""
    goal = getattr(s, "goal", None) or {}
    gid = goal.get("goal_id") or ""
    gver = goal.get("version")
    mgid = mv.get("linked_goal_id") or ""
    if mgid and gid and mgid != gid:
        return [f"G11 move milik Goal {mgid} — bukan Goal sesi aktif {gid}"]
    mver = mv.get("linked_goal_version")
    if mver is not None and gver is not None and mver != gver:
        return [f"G11 move dibuat pada Goal v{mver} — kini v{gver}"]
    return []


# ── a Move out of an ALREADY AUTHORIZED route frontier node ──────────────────────────────────
# The route selector (select_next_move) is the existing authority that says which node of a path
# can be executed NOW. When it answers EXECUTE, that node IS the next bounded unit of work, and the
# contract Move<->RouteNode relation exists exactly for this: the Move is created with a typed
# route_node_ref (R1.5), never as a copy of the route and never as a second execution ledger.
# Nothing is invented: the objective and the action are the node own words, and the completion
# criteria are process criteria (the step is done and its result recorded), not business facts.
MIN_ROUTE_TITLE = 8


def design_from_route_node(*, node: dict, route: dict, path_id: str,
                           guidance: str = "", lang: str = "",
                           activity_en: str = "") -> dict | None:
    """Build a guard-valid MoveDesign for an authorized route frontier node, or None.

    Returns None when the node carries no usable name: a Move must say what it IS ("Create
    proposal"), never appear as a generic "next move"."""
    n = node or {}
    _i18n = (n.get("i18n") or {})
    # the composed node drops i18n; the caller looks the template up and passes the English wording
    _en = str(activity_en or ((_i18n.get("en") or {}).get("activity")) or "").strip()
    _base = str(n.get("activity") or "").strip()
    # The person reads the Move in THEIR language: an English session gets the node's English
    # activity when the template carries one, and the template's own wording otherwise (never a
    # machine translation invented here).
    activity = (_en or _base) if str(lang or "")[:2].lower() == "en" and _en else _base
    if not activity:
        activity = _en
    if len(activity) < MIN_ROUTE_TITLE:
        return None
    step = str(guidance or "").strip() or activity
    req_id = str(((n.get("resolves") or []) or [""])[0] or "")
    ref = _validated_route_ref({
        "route_id": str((route or {}).get("route_id") or ""),
        "node_id": str(n.get("node_id") or ""),
        "route_revision": int((route or {}).get("revision_no") or 0),
    }) if (route or {}).get("route_id") and n.get("node_id") else None
    if ref is None:
        return None
    return {
        "objective": activity[:480],
        "actions": [{
            "title": step[:480],
            "instruction": activity[:600],
            "required": True,
        }],
        "preconditions": [],
        "constraints": [],
        "expected_evidence": ["What happened when you did it (your own observation)"],
        "measurement_method": "Record what happened after the step, from your own records",
        "observation_window_days": 1,
        "completion_criteria": ["The step is done and its result is recorded"],
        "linked_path_id": str(path_id or ""),
        "linked_hypothesis_id": "",
        "route_node_ref": ref,
        "_requirement_id": req_id,
    }


def _predecessor_of(s: Any, *, path_id: str, ts: int) -> str | None:
    """The Move on the SAME path that this one legitimately continues, or None.

    A continuation is recorded only when the earlier Move already reached execution (EXECUTED or a
    later lifecycle state) — i.e. there is real finished work on this path to continue FROM. Two
    Moves created for parallel work (the earlier one still PLANNED/STARTED), or Moves with no path,
    get NO predecessor: no chain is inferred from creation order, array index or objective text."""
    if not path_id:
        return None
    earlier = [m for m in _moves(s)
               if str(m.get("linked_path_id") or "") == str(path_id)
               and m.get("lifecycle") in (EXECUTED, OBSERVED, VALIDATED, INCONCLUSIVE, UNSUPPORTED)
               and int((m.get("created_ts") or 0)) <= ts]
    if not earlier:
        return None
    earlier.sort(key=lambda m: (int(m.get("created_ts") or 0), str(m.get("move_id"))))
    return str(earlier[-1]["move_id"])


def create_move(s: Any, *, design: dict, text: str, event_id: str, binding_id: str = "",
                now: int | None = None) -> dict:
    """A new Move from a validated proposal. Deterministic id per (session, event, objective): a replayed
    turn does not duplicate it.

    Phase 7: the Move is created WITH its executable action list (`move_design.actions`), each row
    carrying a server-issued `action_id` bound to THIS `move_id`. The list is the only live
    execution record for this work; no day-by-day plan is written anywhere."""
    mid = "mv-" + hashlib.sha1(f"{s.id}|{event_id}|{design['objective']}".encode()).hexdigest()[:8]
    if (cur := get_move(s, mid)) is not None:
        return cur
    goal = getattr(s, "goal", None) or {}
    ts = int(now if now is not None else time.time())
    path_id = str(design.get("linked_path_id") or "")
    actions = build_actions(mid, design.get("actions"))
    mv = {
        "move_id": mid, "session_id": s.id, "objective": design["objective"],
        "linked_goal_id": goal.get("goal_id", ""), "linked_goal_version": goal.get("version"),
        "linked_path_id": path_id,
        "linked_hypothesis_id": design.get("linked_hypothesis_id", ""),
        "contextual_instructions": text,
        "preconditions": list(design.get("preconditions") or []),
        "constraints": list(design.get("constraints") or []),
        "expected_evidence": list(design["expected_evidence"]),
        "measurement_method": design["measurement_method"],
        "observation_window_days": int(design["observation_window_days"]),
        "completion_criteria": list(design["completion_criteria"]),
        "actions": actions,
        "predecessor_move_id": _predecessor_of(s, path_id=path_id, ts=ts),
        "outcome_reference": None,
        "lifecycle": PLANNED, "created_event_id": event_id, "binding_id": binding_id,
        "created_ts": ts,
        "route_node_ref": _validated_route_ref(design.get("route_node_ref")),
        "history": [{"state": PLANNED, "ts": ts, "event_id": event_id, "note": "proposed"}],
        "observation_claim_refs": [], "executed_ts": None, "assessment": None,
        "causal_claim": "not_established",
    }
    _moves(s).append(mv)
    return mv


def route_ref_problems(mv: dict, lineage_rows: list[dict]) -> list[str]:
    """Guard R1.5: validate a Move's route_node_ref against the user's lineage rows
    (rl.list_rows shape: [{"lineage": {...}}]). Purely argument-based —
    the caller (endpoint/agent) reads the store. Returned problems:
    route missing · node missing from the latest revision · stale route_revision.
    A Move without route_node_ref = valid (a node may live without a Move; MAP-01)."""
    ref = mv.get("route_node_ref")
    if not ref:
        return []
    try:
        _validated_route_ref(ref)
    except MoveError as exc:
        return [str(exc)]
    row = next((r for r in lineage_rows
                if (r.get("lineage") or {}).get("route_id") == ref["route_id"]), None)
    if row is None:
        return [f"route_node_ref menunjuk route {ref['route_id']!r} yang tidak ada di workspace user"]
    lin = row["lineage"]
    latest = lin["revisions"][-1]
    if ref["route_revision"] != latest["revision_no"]:
        return [f"route_node_ref.route_revision basi: {ref['route_revision']} != "
                f"terbaru {latest['revision_no']} (revisi material terjadi)"]
    if not any(n.get("node_id") == ref["node_id"] for n in latest["nodes"]):
        return [f"route_node_ref.node_id {ref['node_id']!r} tidak ada di revisi "
                f"{latest['revision_no']} route {ref['route_id']!r}"]
    return []


def check_transition(s: Any, move_id: str, new_state: str) -> dict:
    """Validate a transition WITHOUT effects (endpoint use: no durable event is written for a 409)."""
    mv = get_move(s, move_id)
    if mv is None:
        raise MoveError(f"move tidak dikenal: {move_id}")
    # A3-F1 (Round 7, AC-G): a Move from an OLD Goal/version is STALE — its execution is rejected HERE,
    # before a durable execution event is written. The same guard as observation/verdict (BC-02/03).
    if scope := _goal_scope_problems(s, mv):
        raise MoveError(scope[0])
    if new_state not in ALLOWED.get(mv["lifecycle"], set()):
        raise MoveError(f"transisi tidak sah: {mv['lifecycle']} → {new_state}")
    return mv


# A3-F2 (Round 7, AC-G): public alias for the POST /message endpoint — the SAME scope guard
# (no new machinery), so a stale/foreign move_id is rejected before the outcome event is
# classified or semantically committed.
goal_scope_problems = _goal_scope_problems


def transition(s: Any, move_id: str, new_state: str, *, event_id: str = "", note: str = "",
               now: int | None = None) -> dict:
    mv = check_transition(s, move_id, new_state)
    ts = int(now if now is not None else time.time())
    mv["lifecycle"] = new_state
    if new_state == EXECUTED:
        mv["executed_ts"] = ts
    mv["history"].append({"state": new_state, "ts": ts, "event_id": event_id, "note": note})
    return mv


def attach_observation(s: Any, move_id: str, event_id: str, claim_ids: list[str], *, now: int | None = None) -> dict:
    """An `outcome_observation` event bound to a Move: its claims become verdict material. Valid only after EXECUTED."""
    mv = get_move(s, move_id)
    if mv is None:
        raise MoveError(f"move tidak dikenal: {move_id}")
    if scope := _goal_scope_problems(s, mv):
        raise MoveError(scope[0])
    if mv["lifecycle"] not in (EXECUTED, OBSERVED, INCONCLUSIVE):
        raise MoveError(f"observasi hanya sah setelah EXECUTED (kini {mv['lifecycle']})")
    if claim_ids:
        mv["observation_claim_refs"] = sorted(set(mv["observation_claim_refs"]) | set(claim_ids))
        if mv["lifecycle"] != OBSERVED:
            transition(s, move_id, OBSERVED, event_id=event_id, note="observasi dicatat", now=now)
        mv["outcome_reference"] = event_id
    return mv


# ── execution of the Move's actions (server-authoritative) ─────────────────────────────────────

def actions_editable(mv: dict) -> bool:
    """The action list is live while the work is being done. After execution it is HISTORY — except
    the narrow correction window (execution recorded, but no observation/verdict has consumed it
    yet), so a mis-click never strands a person with a record that cannot be fixed."""
    if mv.get("lifecycle") in ACTION_OPEN_LIFECYCLES:
        return True
    return (mv.get("lifecycle") == EXECUTED
            and not (mv.get("observation_claim_refs") or [])
            and not mv.get("assessment"))


def action_event_problems(s: Any, mv: dict, action: dict, event: str,
                          *, now: int | None = None) -> list[str]:
    """Validate ONE action execution event WITHOUT mutating (so a rejected event writes nothing).

    Order rules: free unless the action DECLARES dependencies — and then only DONE satisfies one.
    SKIPPED is not DONE and BLOCKED is not DONE: neither can unlock a dependent action."""
    out = _goal_scope_problems(s, mv)
    event = str(event or "").upper()
    if event not in ACTION_STATES:
        out.append(f"status aksi tidak dikenal: {event!r}")
        return out
    if not actions_editable(mv):
        out.append(f"daftar aksi Move ini sudah menjadi riwayat (lifecycle {mv.get('lifecycle')})")
        return out
    if event != ACTION_TODO:
        for dep_id in action.get("depends_on_action_ids") or []:
            dep = get_action(mv, dep_id)
            if dep is None or dep.get("status") != ACTION_DONE:
                out.append(f"aksi ini bergantung pada aksi {dep_id} yang belum selesai "
                           f"(status {((dep or {}).get('status'))!r})")
    return out


def apply_action_event(s: Any, move_id: str, action_id: str, event: str, *, event_id: str,
                       note: str = "", now: int | None = None) -> dict:
    """Apply ONE accepted action event to the canonical Move.

    The Move's lifecycle is advanced HERE (server side) and only when every REQUIRED action is
    genuinely DONE. Nothing is inferred from a browser counter, no outcome is claimed, and the
    Move is never marked successful: EXECUTED is an execution event, not a result."""
    mv = get_move(s, move_id)
    if mv is None:
        raise MoveError(f"move tidak dikenal: {move_id}")
    action = get_action(mv, action_id)
    if action is None:
        raise MoveError(f"aksi tidak dikenal pada move ini: {action_id}")
    event = str(event or "").upper()
    if problems := action_event_problems(s, mv, action, event, now=now):
        raise MoveError(problems[0])
    ts = int(now if now is not None else time.time())
    was = str(action.get("status") or ACTION_TODO)
    action["status"] = event
    action["note"] = (note or "")[:600]
    action["history"] = (list(action.get("history") or []) + [
        {"status": event, "ts": ts, "event_id": event_id, "note": (note or "")[:160]}
    ])[-20:]
    if event == ACTION_DONE:
        action["completed_at"] = ts
        action["execution_event_id"] = event_id
    elif event in EXECUTION_BLOCKING:
        action["completed_at"] = None      # a skip/block is a DECISION, not a completion
        action["execution_event_id"] = event_id
    else:                                   # reopened
        action["completed_at"] = None
        action["execution_event_id"] = None
    move_executed = False
    if (mv.get("lifecycle") == PLANNED and event in (ACTION_DONE,) + EXECUTION_BLOCKING):
        # The first accepted action IS the start of the work: the lifecycle reflects it without the
        # person having to press a separate "start" control.
        transition(s, mv["move_id"], STARTED, event_id=event_id, note="first action recorded", now=ts)
    if event == ACTION_TODO and was != ACTION_TODO and mv.get("lifecycle") == EXECUTED:
        # Narrow correction: the execution had not been consumed by an observation or a verdict,
        # so the Move returns to STARTED (history records the correction). Never a silent reset.
        mv["lifecycle"] = STARTED
        mv["executed_ts"] = None
        mv["execution_completed_by"] = None
        mv["history"].append({"state": STARTED, "ts": ts, "event_id": event_id,
                              "note": f"action reopened: {action.get('title', '')[:80]}"})
    elif mv.get("lifecycle") in ACTION_OPEN_LIFECYCLES and action_progress(mv)["complete"]:
        transition(s, mv["move_id"], EXECUTED, event_id=event_id,
                   note="required actions completed", now=ts)
        mv["execution_completed_by"] = "actions"
        move_executed = True
    return {"move": mv, "action": action, "move_executed": move_executed,
            "progress": action_progress(mv), "previous_status": was}


# ── outcome of the Move (distinct from execution) ─────────────────────────────────────────────

OUTCOME_CHOICES = ("moved", "not_moved", "regret", "confounded")


def outcome_report_problems(s: Any, mv: dict, outcome: str | None, note: str | None) -> list[str]:
    """A result can only be reported on work that was executed. The report never changes the
    execution status and never claims a verdict: VALIDATED/UNSUPPORTED still needs observation
    claims and guard G11."""
    out = _goal_scope_problems(s, mv)
    if mv.get("lifecycle") not in (EXECUTED, OBSERVED, INCONCLUSIVE):
        out.append(f"hasil hanya dapat dilaporkan setelah EXECUTED (kini {mv.get('lifecycle')})")
    if outcome is not None and outcome not in OUTCOME_CHOICES:
        out.append(f"outcome tidak dikenal: {outcome!r}")
    if outcome is None and not (note or "").strip():
        out.append("outcome atau catatan wajib")
    return out


def record_outcome_report(s: Any, move_id: str, *, outcome: str | None, note: str | None, path: str,
                          event_id: str, operation_id: str = "", sig: str = "",
                          now: int | None = None) -> dict:
    """Record what happened as a RESULT of this Move's work (one effective report, corrections kept).

    The report is attached to the Move itself: no arbitrary action has to own the overall result.
    An EXECUTED Move becomes OBSERVED here (a reported result exists); it does NOT become VALIDATED —
    that verdict still needs observation claims and guard G11."""
    mv = get_move(s, move_id)
    if mv is None:
        raise MoveError(f"move tidak dikenal: {move_id}")
    if problems := outcome_report_problems(s, mv, outcome, note):
        raise MoveError(problems[0])
    ts = int(now if now is not None else time.time())
    prev = dict(mv.get("outcome_report") or {})
    row = {
        "outcome": (outcome if outcome is not None else (prev.get("outcome") or "")),
        "note": (prev.get("note") or "") if note is None else note,
        "path": path or (prev.get("path") or ""),
        "reported_at": ts,
        "event_id": event_id,
        "revisions": list(prev.get("revisions") or [])[-20:],
        "ops": list(prev.get("ops") or [])[-9:],
    }
    if prev.get("outcome") or prev.get("note"):
        row["revisions"] = (row["revisions"] + [{
            "outcome": prev.get("outcome"), "note": prev.get("note"), "path": prev.get("path"),
            "reported_at": prev.get("reported_at"), "superseded_at": ts}])[-20:]
    if operation_id:
        row["ops"].append({"op": operation_id, "sig": sig, "ts": ts})
    mv["outcome_report"] = row
    mv["outcome_reference"] = event_id
    if mv.get("lifecycle") == EXECUTED:
        transition(s, move_id, OBSERVED, event_id=event_id, note="hasil dilaporkan", now=ts)
    return {"move": mv, "report": {k: row.get(k) for k in ("outcome", "note", "path", "reported_at")},
            "correction": bool(prev.get("outcome") or prev.get("note"))}


def outcome_report_view(mv: dict) -> dict | None:
    r = mv.get("outcome_report") or {}
    if not (r.get("outcome") or r.get("note")):
        return None
    return {"outcome": r.get("outcome") or None, "note": r.get("note") or None,
            "path": r.get("path") or None, "reported_at": r.get("reported_at"),
            "corrections": len(r.get("revisions") or [])}


def window_open(mv: dict, now: int | None = None) -> bool:
    if not mv.get("executed_ts"):
        return True
    t = int(now if now is not None else time.time())
    return t < mv["executed_ts"] + mv["observation_window_days"] * 86400


def assessment_problems(s: Any, a: dict, *, now: int | None = None) -> list[str]:
    """Deterministic verdict checks (guard G11)."""
    mv = get_move(s, a.get("move_id", ""))
    if mv is None:
        return [f"G11 move tidak dikenal: {a.get('move_id')!r}"]
    out: list[str] = _goal_scope_problems(s, mv)
    if mv["lifecycle"] != OBSERVED:
        out.append(f"G11 move belum OBSERVED (kini {mv['lifecycle']})")
    nodes = (s.state_graph or {}).get("nodes") or {}
    refs = list(a.get("observed_claim_refs") or [])
    seqs = {e["event_id"]: e.get("seq", 0) for e in s.events}
    exec_ev = next((h["event_id"] for h in mv["history"] if h["state"] == EXECUTED), "")
    for c in refs:
        n = nodes.get(c)
        if n is None or (n.get("status") or "active") != "active":
            out.append(f"G11 klaim observasi tak aktif/tak ada: {c}")
            continue
        if c not in mv["observation_claim_refs"]:
            out.append(f"G11 klaim {c} bukan observasi yang terikat Move ini")
        ev = (n.get("provenance") or {}).get("event_id", "")
        if exec_ev and ev in seqs and exec_ev in seqs and seqs[ev] < seqs[exec_ev]:
            out.append(f"G11 klaim {c} lahir SEBELUM eksekusi — bukan hasil Move")
    v = a.get("verdict")
    if v in (VALIDATED, UNSUPPORTED):
        if not refs:
            out.append(f"G11 {v} wajib merujuk klaim observasi")
        if window_open(mv, now):
            out.append(f"G11 {v} tidak sah selagi jendela observasi masih terbuka — gunakan INCONCLUSIVE sementara")
    return out


def apply_assessment(s: Any, a: dict, *, event_id: str, now: int | None = None) -> dict:
    """Apply a guard-passed verdict: lifecycle + related hypotheses (a trail to the observation claims)."""
    mv = get_move(s, a["move_id"])
    if mv is None:
        raise MoveError(f"move tidak dikenal: {a['move_id']}")
    if scope := _goal_scope_problems(s, mv):
        raise MoveError(scope[0])
    transition(s, mv["move_id"], a["verdict"], event_id=event_id, note=a.get("rationale", "")[:160], now=now)
    mv["assessment"] = {"verdict": a["verdict"], "observed_claim_refs": list(a.get("observed_claim_refs") or []),
                        "rationale": a.get("rationale", ""), "remaining_uncertainties":
                        list(a.get("remaining_uncertainties") or []), "event_id": event_id,
                        "causal_claim": "not_established"}
    hid = mv.get("linked_hypothesis_id")
    h = (getattr(s, "hypotheses", None) or {}).get(hid) if hid else None
    if h is not None and a["verdict"] in (VALIDATED, UNSUPPORTED):
        key = "supports" if a["verdict"] == VALIDATED else "contradicts"
        h[key] = sorted(set(h[key]) | set(a.get("observed_claim_refs") or []))
        h["history"].append({"event_id": event_id, "change": f"outcome_{a['verdict'].lower()}",
                             "claims": list(a.get("observed_claim_refs") or []), "move_id": mv["move_id"]})
        from core.reasoning.hypotheses import standing_of
        h["standing"] = standing_of(h, s.state_graph)
    return mv


def summaries(s: Any, now: int | None = None) -> list[dict]:
    """Move summaries for the reasoning snapshot / UI (compact: no per-action rows)."""
    out = []
    for m in _moves(s):
        prog = action_progress(m)
        out.append({k: m.get(k) for k in ("move_id", "objective", "lifecycle", "linked_goal_id", "linked_goal_version",
                                          "linked_hypothesis_id", "linked_path_id",
                                          "expected_evidence", "completion_criteria", "observation_claim_refs",
                                          "observation_window_days")}
                   | {"window_open": window_open(m, now), "assessment": (m.get("assessment") or {}).get("verdict"),
                      "actions_total": prog["total"], "actions_done": prog["done"],
                      "actions_open": prog["open"], "actions_required": prog["required"],
                      "actions_complete": prog["complete"],
                      "pending_actions": [a.get("title") for a in (m.get("actions") or [])
                                          if a.get("status") == ACTION_TODO][:MAX_ACTIONS]})
    return out


def _action_view(a: dict) -> dict:
    return {k: a.get(k) for k in ("action_id", "move_id", "ordinal", "title", "instruction", "status",
                                  "required", "depends_on_action_ids", "completed_at",
                                  "execution_event_id", "supporting_refs", "note")}


def view(m: dict, now: int | None = None) -> dict:
    """ONE Move as the client reads it — the SAME shape for Maps, Moves and Journey.

    `action_id`/`move_id` are the server-issued identities; `actions` is the canonical checklist.
    Nothing here is derived by position at read time and nothing is written by a reader."""
    prog = action_progress(m)
    return {
        "move_id": m.get("move_id"), "objective": m.get("objective"),
        "lifecycle": m.get("lifecycle"), "contextual_instructions": m.get("contextual_instructions"),
        "linked_goal_id": m.get("linked_goal_id"), "linked_goal_version": m.get("linked_goal_version"),
        "linked_path_id": m.get("linked_path_id") or None,
        "linked_hypothesis_id": m.get("linked_hypothesis_id") or None,
        "route_node_ref": m.get("route_node_ref"),
        "predecessor_move_id": m.get("predecessor_move_id") or None,
        "created_ts": m.get("created_ts"), "executed_ts": m.get("executed_ts"),
        "observation_window_days": m.get("observation_window_days"),
        "window_open": window_open(m, now),
        "execution_completed_by": m.get("execution_completed_by"),
        "expected_evidence": list(m.get("expected_evidence") or []),
        "completion_criteria": list(m.get("completion_criteria") or []),
        "measurement_method": m.get("measurement_method"),
        "outcome_reference": m.get("outcome_reference"),
        "outcome_report": outcome_report_view(m),
        "observation_claim_refs": list(m.get("observation_claim_refs") or []),
        "assessment": (m.get("assessment") or {}).get("verdict"),
        "causal_claim": m.get("causal_claim") or "not_established",
        "actions": [_action_view(a) for a in (m.get("actions") or [])],
        "progress": prog,
        "actions_editable": actions_editable(m),
        "history": [h for h in (m.get("history") or [])][-20:],
    }


def moves_view(s: Any, *, path_id: str | None = None, now: int | None = None) -> list[dict]:
    """Every canonical Move of the session (optionally one path), newest last. Historical Moves are
    never dropped: Maps keeps the executed ones visible next to the current one."""
    rows = [m for m in _moves(s)
            if path_id is None or str(m.get("linked_path_id") or "") == str(path_id)]
    rows.sort(key=lambda m: (int(m.get("created_ts") or 0), str(m.get("move_id"))))
    return [view(m, now) for m in rows]
