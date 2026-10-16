"""Session navigation — the ONE door wiring the conversation state loop
(internal-docs §25, M4).

    Universal State (evidence ledger + graph)
      -> live adjudication          ontology/mapper/live_adjudication   (mapper = proposal; ledger = status)
      -> Possible Path 0..N         domains/revenue/navigation/live     (provisional; deterministic, zero LLM)
      -> Route (optional)           ontology/route/path_routes          (one pipeline for every path origin)
      -> Applicable Requirement Set core/navigation/applicability
      -> Requirement State Reader   store/requirement_state             (one user-scoped ledger reader)
      -> Readiness projection       core/navigation/readiness     (from the SAME path/route/state; read by UI,
                                    narrative, inspection — the planner does NOT read it)
      -> Question Planner           core/navigation/planner   (QUESTION | EVIDENCE_REQUEST | ACTION | HOLD)

Used by `POST /session/{sid}/message` (every turn), `GET /session/{sid}/navigation` (inspection + replay),
and anyone who needs the same decision from the same state. No decisions here: this module only wires
layers that each already own their contract. It never calls the LLM.

Two fail-safe levels, both VISIBLE (never masked):
  - route composition fails (a contract bug): recorded in `errors` (response + log), the planner runs
    route-less — routes are optional by design;
  - navigation fails elsewhere: `degraded_navigation` — the step is an honest HOLD ("no safe next step can
    be named"), not an invented question, and the conversation doesn't crash; the next turn recomputes
    from state (no half-built state is saved)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.navigation.applicability import ApplicableRequirementSet, build_applicable_set
from core.navigation.planner import (
    KIND_EVIDENCE,
    KIND_QUESTION,
    PLANNER_VERSION,
    POLICY,
    plan_next_move,
    replay,
)
from core.navigation.planner_input import assemble_planner_input
from core.navigation.planner_text import render_move
from core.navigation.readiness import build_projection
from core.navigation.requirement_state import RequirementView, read_requirement_views, status_reader
from core.schema.evidence import current_evidence
from domains.revenue.navigation import live as revenue_live
from domains.revenue.navigation.paths import lifecycles_from_states
from engine.requirements import describe
from ontology.mapper.live_adjudication import run_live_adjudication, support_of
from ontology.route.strategies import active_template_library, load_strategies
from store import path_states, route_execution
from store.requirement_state import user_requirement_reader

log = logging.getLogger("novaliners.navigation")

PLANNER_LOG_CAP = 25  # the last decisions kept (the "already asked" counter + history)
REPLAY_WINDOW = 5  # the last entries keeping their INPUT (replay); older ones keep decision + digest only


@dataclass
class TurnNavigation:
    path_set: dict[str, Any]
    routes: dict[str, Any] | None
    applicable: ApplicableRequirementSet
    views: dict[str, RequirementView]
    planner_input: dict[str, Any]
    decision: dict[str, Any]
    rendered: dict[str, str]
    adjudication: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    readiness: dict[str, Any] | None = None  # the Readiness projection; NOT a planner input
    # R5: the step PRESENTED (a guard-validated reasoning proposal, or a degraded HOLD) and its trail.
    # `decision` stays the deterministic decision (candidate/guard/replay), not a substance chooser.
    presented: dict[str, Any] | None = None
    adaptive: dict[str, Any] | None = None
    candidate_rendered: dict[str, str] | None = None   # the deterministic candidate's wording (audit)

    def summary(self) -> dict[str, Any]:
        """Compact summary for the turn response / UI: without the full input."""
        return {
            "counts": self.decision["reason"]["counts"],
            "stage": self.decision["reason"]["stage"],
            "adjudication": {
                k: self.adjudication.get(k)
                for k in (
                    "scoped", "skipped", "proposed", "focused", "verified", "unresolved", "adjudicated",
                    "gaps_excluded"
                )
                if k in self.adjudication
            },
            "paths": [
                {"path_id": p["path_id"], "status": p.get("status"), "applicability": p.get("applicability")}
                for p in self.path_set.get("paths") or []
            ],
            "readiness": [
                {"path_id": p["path_id"], "executability": p.get("executability"), "counts": p["counts"]}
                for p in (self.readiness or {}).get("paths") or []
            ],
            "errors": list(self.errors),
        }


def focus_requirement_ids(planner_log: list[Mapping[str, Any]] | None) -> list[str]:
    """Prose-requirement RIDs that become adjudication focus-path candidates (MC-02/MC-03).

    Two sources, stable order (dedup):
    1. rids that were ever the ASK FOCUS (newest first) — from the PRESENTED decision
       (presented/decision, focus.id / reason.need_id, the 'requirement:' prefix);
    2. all LIVE-context requirements (navigable + APPLIES) still UNKNOWN, from the
       `input.requirements` of the LAST planner_log entry. MC-03 (18 Oct, follow-up session
       e1704203f327): once reasoning moved to semantic unknowns (su-*), context requirements
       never became the ask focus again — even though user answers still answered them — and the
       "key questions left" chip jammed (6→5 then stopped). The last entry is the only one still
       holding the full input (compact_log), and that is the current context state.

    Focus id shape: 'requirement:<rid>'."""
    rids: list[str] = []
    seen: set[str] = set()

    def _add(rid: str) -> None:
        if rid and rid not in seen:
            seen.add(rid)
            rids.append(rid)

    for e in reversed(planner_log or []):
        d = e.get("presented") or e.get("decision") or {}
        for raw in (str((d.get("focus") or {}).get("id") or ""),
                    str(((d.get("reason") or {}).get("need_id")) or "")):
            if raw.startswith("requirement:"):
                _add(raw.split(":", 1)[1].strip())
    for e in reversed(planner_log or []):
        reqs = (e.get("input") or {}).get("requirements") or {}
        if not reqs:
            continue  # entry without input (compacted) — look for the last one that has it
        for rid in sorted(reqs):
            r = reqs[rid] or {}
            if r.get("satisfaction") != "UNKNOWN":
                continue
            alive = any(c.get("navigable") and c.get("applicability") == "APPLIES"
                        for c in (r.get("contexts") or []))
            if alive:
                _add(rid)
        break  # only the last entry with input: the current context state
    return rids


QB_MAX_INITIAL = 10   # MC-07: first batch budget — large enough for rich sessions, small to stay clear
QB_MAX_NEXT = 8     # MC-07: follow-up batches are shorter (toward the next offer)
QB_FLOOR = 1


def _budget_estimate(nav: Any, open_ask: int) -> int:
    """MC-08: the LLM's estimate — how many material unknowns the REASONER sees this turn
    (`checkpoint.critical_count + nonblocking_count`, nm.v2 model output), not a constant.
    Layered fallback: checkpoint absent/None -> open_askable (path set) -> 3. The caller
    clamps to [QB_FLOOR..cap]."""
    cp = (nav.presented or {}).get("checkpoint") or {}
    crit, nonb = cp.get("critical_count"), cp.get("nonblocking_count")
    if isinstance(crit, int) and isinstance(nonb, int):
        est = crit + nonb
        if est > 0:
            return est
    return open_ask or 3


def update_question_budget(s: Any, nav: Any) -> dict:
    """MC-07 (18 Oct, owner decision): a MONOTONIC per-batch QUESTION BUDGET.

    The adjudication pipeline stays honest (planner counts unchanged); this layer is what is
    PROMISED to the user via the chip: the initial number is set when the batch opens, then it
    ONLY GOES DOWN — one by one per PRESENTED question — never up/steady from engine oscillation.

    - Batch 1 opens on the first turn; later batches open AUTOMATICALLY once the budget runs out
      and the user sends another message (= choosing "continue"; the Build button = finalize).
    - initial (MC-08) = clamp(LLM estimate, 1..cap) — the REASONER's view of how many material
      unknowns remain this turn (`checkpoint.critical_count + nonblocking_count`, nm.v2 output),
      FROZEN for that batch; falls back to open_askable (path set) then 3. Rationale (18 Oct,
      owner report "stuck at 3"): open_askable on turn 1 is often 0 (path set not built yet),
      so the old source collapsed to the constant default.
    - answered grows only from QUESTION/EVIDENCE_REQUEST steps; HOLD/ACTION don't count.
    Called ONCE per turn on the primary run_turn path (not the reasoning-retry path)."""
    open_ask = int(((nav.decision.get("reason") or {}).get("counts") or {}).get("open_askable") or 0)
    kind = (nav.presented or {}).get("kind")
    qb = dict(getattr(s, "question_budget", None) or {})
    if not qb or int(qb.get("remaining") or 0) <= 0:
        cap = QB_MAX_INITIAL if not qb else QB_MAX_NEXT
        initial = max(QB_FLOOR, min(_budget_estimate(nav, open_ask), cap))
        qb = {"batch": int(qb.get("batch") or 0) + 1, "initial": initial, "answered": 0,
              "remaining": initial, "open_at_start": open_ask}
    if kind in (KIND_QUESTION, KIND_EVIDENCE):
        qb["answered"] = int(qb.get("answered") or 0) + 1
        qb["remaining"] = max(0, int(qb["initial"]) - int(qb["answered"]))
    s.question_budget = qb
    return qb


def attach_question_budget(summary: dict[str, Any], s: Any) -> dict[str, Any]:
    """Insert the question budget into the response summary (GET /navigation, /message)."""
    summary["question_budget"] = dict(getattr(s, "question_budget", None) or {})
    return summary


def asked_counts(planner_log: list[Mapping[str, Any]]) -> dict[str, int]:
    """How many times EACH need was already asked (QUESTION/EVIDENCE_REQUEST) — from the log, not state."""
    out: dict[str, int] = {}
    for e in planner_log:
        d = e.get("presented") or e.get("decision") or {}  # R5: PRESENTED, not the candidate decision
        if d.get("kind") in (KIND_QUESTION, KIND_EVIDENCE):
            nid = (d.get("reason") or {}).get("need_id")
            if nid:
                out[nid] = out.get(nid, 0) + 1
    return out


def path_affiliation(d: dict[str, Any], routes: dict[str, Any] | None) -> str | None:
    """EXPLICIT (nullable) Path affiliation from ONE guarded decision — used by `GET /navigation` AND the
    turn response (`POST /message`) so the same decision DTO doesn't differ between endpoints (one
    contract, one affiliation). Read from focus/reason/payload; ambiguous (0 or >1 paths) = None,
    not a silent choice."""
    route_path = {
        r.get("route_id"): r.get("path_id")
        for r in ((routes or {}).get("routes") or [])
        if r.get("route_id") and r.get("path_id")
    }
    paths: set[str] = set()
    focus = d.get("focus") or {}
    if focus.get("type") == "path" and focus.get("id"):
        paths.add(str(focus["id"]))
    elif focus.get("type") == "route" and focus.get("id") and route_path.get(focus["id"]):
        paths.add(str(route_path[focus["id"]]))
    for c in ((d.get("reason") or {}).get("contexts") or []):
        if c.get("kind") == "path" and c.get("id"):
            paths.add(str(c["id"]))
        elif c.get("kind") == "route" and c.get("id") and route_path.get(c["id"]):
            paths.add(str(route_path[c["id"]]))
    payload = d.get("payload") or {}
    if payload.get("path_id"):
        paths.add(str(payload["path_id"]))
    if payload.get("route_id") and route_path.get(payload["route_id"]):
        paths.add(str(route_path[payload["route_id"]]))
    return next(iter(paths)) if len(paths) == 1 else None


def compose_routes_for_paths(s: Any, paths: list[dict[str, Any]],
                             read_only: bool = False) -> dict[str, Any]:
    """Possible Paths (0..N) -> `{routes, not_born, next_move}` through the ONE `compose_path_routes`
    pipeline (same as `POST /routes`, readiness, and golden). Latest lifecycles + the user's execution
    views are carried along."""
    from core.navigation.readiness import node_guidance as _guidance_rule
    from ontology.route.path_routes import compose_path_routes

    strategies = load_strategies()
    lang = ((getattr(s, "language", None) or "en")[:2]).lower()

    def _node_guidance(n: dict[str, Any]) -> dict[str, str]:
        """ONE rule with readiness (`_guidance`): curated requirement verification > node activity >
        deterministic fallback. This is the source of the route-node `guidance` that reads as "Next move"
        per path in the Maps UI (17 Oct 2026 gap: compose never threaded guidance through)."""
        req = ((n.get("resolves") or []) or [""])[0] or None
        return _guidance_rule(req, n, lambda rid: describe(rid, lang), lang)

    return compose_path_routes(
        s,
        paths,
        active_template_library(),
        describe_strategy=lambda sid: strategies[sid]["description"],
        lifecycles=lifecycles_from_states(
            path_states.get_states(
                s.user_id, goal_id=((getattr(s, "goal", None) or {}).get("goal_id") or None)
            ) if s.user_id else None
        ),
        views=route_execution.latest_views(s.user_id) if s.user_id else None,
        views_by_route=route_execution.latest_views_by_route(s.user_id) if s.user_id else None,
        node_guidance=_node_guidance,
        read_only=read_only,
    )


def navigate_session(
    s: Any,
    *,
    lang: str | None = None,
    adjudicate: bool = True,
    asked_from: list[Mapping[str, Any]] | None = None,
    llm: Any = None,
) -> TurnNavigation:
    """The session's CURRENT state -> the planner decision. Idempotent: adjudication writes only when the
    result changes.

    `asked_from` = the log used to count "how many times already asked" (default: the whole session log).
    Inspection passes the log WITHOUT the last entry to recompute the presented decision.

    `llm` (optional, EXPLICIT): enables D-A2 layer C (a second-pass verifier for prose requirements).
    Default None = the purely deterministic path (A+B) — test/inspection callers get NO network calls.
    The live paths (run_turn / _first_move) pass the provider they ALREADY hold so a test's
    `app.main.get_llm` patch keeps working (one seam, no silent acquisition)."""
    lang = ((lang or s.language or "en")[:2]).lower()
    errors: list[str] = []

    if adjudicate and s.user_id:
        adjudication = run_live_adjudication(
            s.user_id, s.evidence, goal=getattr(s, "goal", None), session_id=s.id, graph=s.state_graph,
            llm=llm,
            # MC-02: needs that were ever asked (still UNKNOWN) get the latest admissible claims as
            # second-pass candidates — patching the cross-language recall of the narrowing mapper.
            focus_requirement_ids=focus_requirement_ids(s.planner_log))
    else:
        adjudication = {"scoped": False, "skipped": "NO_USER_SCOPE" if not s.user_id else "NOT_REQUESTED"}

    pstates = path_states.get_states(
        s.user_id,
        goal_id=((getattr(s, "goal", None) or {}).get("goal_id") or None),
    ) if s.user_id else None
    # F3d/S3: ONE reader (the Requirement State Reader) is built BEFORE path_set so path feasibility
    # already reads the same adjudicated requirement states as readiness and the planner — the ledger
    # is authoritative over requirement_id-anchored checks (merge_readings, not a second evaluator).
    # R1-remediation Probe A: the reader is scoped to the BUSINESS CONTEXT (the session goal_id) —
    # other businesses owned by the same user are no longer readable from here.
    reader = user_requirement_reader(
        s.user_id,
        goal_id=((getattr(s, "goal", None) or {}).get("goal_id") or None),
        support_of=support_of())
    # Goal-Relative (int 09 §5): the session's structured Goal joins as an evaluation context —
    # the Goal gate uses metric semantics (GR-12), not just goal_text.
    path_set = revenue_live.provisional_path_set(
        current_evidence(s.evidence), s.goal_text, s.transcript, s.state_graph or None, pstates,
        goal=getattr(s, "goal", None),
        historical_evidence=[e for e in s.evidence if getattr(e, "superseded", False)],
        ledger_state_of=status_reader(reader),
    )

    routes: dict[str, Any] | None = None
    paths = path_set.get("paths") or []
    if s.user_id and paths:
        try:
            routes = compose_routes_for_paths(s, paths)
        except Exception as exc:  # route contract bug: visible, never crashes chat (routes optional)
            log.exception("komposisi route gagal; planner berjalan tanpa route")
            errors.append(f"route_composition: {type(exc).__name__}: {exc}"[:240])

    # F3d: the SAME reader (built above) is used by readiness and the planner — route-less readiness
    # reads the ledger through the same Requirement State Reader semantics (merge_readings).

    readiness = None
    if paths:
        # Readiness = a projection over the SAME path/route/state. The planner doesn't read it (Readiness
        # != planner), so its failure never blocks a step: recorded in `errors`, the planner runs as usual.
        try:
            readiness = build_projection(
                path_set, routes, lambda rid: describe(rid, lang),
                lifecycles=lifecycles_from_states(pstates), lang=lang,
                state_reader=status_reader(reader),
            )
        except Exception as exc:
            log.exception("proyeksi readiness gagal; planner tidak membacanya, giliran dilanjutkan")
            errors.append(f"readiness: {type(exc).__name__}: {exc}"[:240])

    ars = build_applicable_set(path_set, routes, template_requirements=revenue_live.template_requirements())
    views = read_requirement_views(ars, reader, path_set, routes)
    inp = assemble_planner_input(
        lang=lang,
        turn=sum(1 for role, _ in s.transcript if role == "user"),
        path_set=path_set,
        route_data=routes,
        applicable=ars,
        views=views,
        describe=lambda rid: describe(rid, lang),
        signal_of=revenue_live.signal_of(),
        resolvable=revenue_live.resolvable,
        signal_text=revenue_live.signal_text,
        asked=asked_counts(s.planner_log if asked_from is None else asked_from),
    )
    decision = plan_next_move(inp)
    history = s.planner_log if asked_from is None else asked_from
    previous = (history[-1].get("decision") if history else None)  # only for wording ("no change")
    return TurnNavigation(
        path_set=path_set,
        routes=routes,
        applicable=ars,
        views=views,
        planner_input=inp,
        decision=decision,
        rendered=render_move(decision, inp, lang, previous=previous),
        adjudication=adjudication,
        errors=errors,
        readiness=readiness,
    )


def degraded_navigation(s: Any, exc: BaseException, *, lang: str | None = None) -> TurnNavigation:
    """Navigation failed mid-turn -> an honest HOLD decision + a visible error (`errors` + log).

    No paths/requirements/questions are invented to fill the gap: the minimal path-less input makes the
    planner fall to HOLD (`no_safe_next_question`). Computed through the same `plan_next_move`, so the
    log entry stays replayable."""
    lang = ((lang or getattr(s, "language", None) or "en")[:2]).lower()
    turn = sum(1 for role, _ in getattr(s, "transcript", []) if role == "user")
    inp: dict[str, Any] = {
        "version": PLANNER_VERSION, "policy": POLICY, "lang": lang, "history": {"asked": {}, "turn": turn},
    }
    decision = plan_next_move(inp)
    return TurnNavigation(
        path_set={},
        routes=None,
        applicable=ApplicableRequirementSet(items=()),
        views={},
        planner_input=inp,
        decision=decision,
        rendered=render_move(decision, inp, lang),
        adjudication={"scoped": bool(getattr(s, "user_id", None)), "skipped": "NAVIGATION_FAILED"},
        errors=[f"navigation: {type(exc).__name__}: {exc}"[:240]],
    )


def log_entry(nav: TurnNavigation, turn: int) -> dict[str, Any]:
    """A decision log entry: input + decision + text — enough to replay without any other state. `texts`
    (display wording) is not saved: not a decision basis and derivable from registry/presentation."""
    inp = {k: v for k, v in nav.planner_input.items() if k != "texts"}
    entry = {"turn": turn, "input": inp, "decision": nav.decision, "text": nav.rendered}
    if nav.presented is not None:
        entry["presented"] = nav.presented
        entry["adaptive"] = nav.adaptive
    return entry


def compact_log(log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact the log so the session file (rewritten every turn) doesn't bloat: only the last
    `REPLAY_WINDOW` entries keep their full input, and only the very last keeps `applicable`. Older
    entries keep decision + text + digest (enough for history and the "already asked" counter)."""
    out: list[dict[str, Any]] = []
    for i, e in enumerate(log):
        from_end = len(log) - 1 - i
        if from_end >= REPLAY_WINDOW:
            e = {k: v for k, v in e.items() if k != "input"}
        elif from_end >= 1 and "applicable" in (e.get("input") or {}):
            e = {**e, "input": {k: v for k, v in e["input"].items() if k != "applicable"}}
        out.append(e)
    return out


def clarity(decision: Mapping[str, Any]) -> float:
    """STATE-based clarity 0..1 (not a phase index): the share of answerable needs already answered.
    1.0 only when the planner decides ACTION (enough to map). Can drop when new needs appear — that's
    honest."""
    if decision.get("stop") and decision.get("kind") == "ACTION":
        return 1.0  # only ACTION means "enough to map"; HOLD is not full clarity
    c = decision["reason"]["counts"]
    total = c["resolved"] + c["open_askable"]
    return round(min(0.95, c["resolved"] / total), 2) if total else 0.0


def replay_logged(entry: Mapping[str, Any]) -> dict[str, Any]:
    return replay(entry)
