"""Question Planner — picks the next conversation step from STATE and uncertainty, not from phases.

internal-docs §25 (M4); INV-7 (int 10): Question and Action are one type, NextMove.

    Goal · Universal State · Possible Path (0..N) · Route (optional) · Applicable Requirement Set
    · Requirement State (reader) · dependencies (HOW) · question history
                                   |
                         plan_next_move(input)          <- PURE FUNCTION, deterministic
                                   |
        QUESTION | EVIDENCE_REQUEST | ACTION | HOLD   + machine-readable reason trail

The planner is a DECISION ENGINE, not LLM improvisation. An LLM may render the words or interpret language;
it is never the authority on status, applicability, readiness, satisfaction, contradiction, ordering, or
next-step policy. This module calls no LLM, store, network, or clock.

The question it answers: "which highest-value information or action is still needed NOW to reduce
uncertainty or open a legitimate navigation step?" — not "the Nth question of phase X".

POLICY `m4.v1` (stage order; the first stage producing a decision wins; every decision carries its reasons):

  S0 GOAL            goal not yet established          -> QUESTION  RESOLVE_GOAL
  S1 CONTRADICTION   requirement in conflict           -> EVIDENCE_REQUEST RESOLVE_CONTRADICTION
  S2 APPLICABILITY   navigable path, applicability     -> QUESTION  RESOLVE_APPLICABILITY (the missing fact)
                     UNKNOWN
  S3 STATE           requirement/check still UNKNOWN   -> QUESTION | EVIDENCE_REQUEST  RESOLVE_STATE
                     in navigable contexts, ready         (dependency-aware; only what CAN be answered
                     dependency-wise                      through conversation; no unbounded repeats)
  S4 EMERGENCE       no navigable path                 -> QUESTION  RESOLVE_STATE (path-creating fact)
  S5 DOWNSTREAM      NextMove v1 on routes (existing   -> ACTION | QUESTION | EVIDENCE_REQUEST | HOLD
                     frontier selector)                    (passed through, not duplicated)
  S6 FALLBACK        navigable paths exist             -> ACTION PRESENT (enough mapped); otherwise HOLD

Rules that keep it honest:
  - Only what CAN be answered through conversation is asked (`resolvable_by=ASK`). A requirement without a
    formal rule cannot have its state shifted by an answer; asking it repeatedly is a circle with no end.
    It is handed to action (route) and to proof of the action's result.
  - Dependencies: A -> B -> C. While A (a dependency of B) is not PRESENT, the planner does not dig into C.
    Registry = WHAT; the dependency graph = HOW (route node `depends_on`).
  - A non-navigable context (path STOP: engine finding OR user decision) does not drive the conversation.
  - One need is asked at most `ASK_CAP` times (QUESTION then EVIDENCE_REQUEST); after that it is skipped and
    logged `ASKED_ENOUGH` — the planner knows when to stop asking.
  - There is NO business ranking. Ordering among equal needs is a deterministic information policy
    (condition strength, how many contexts need it, dependency depth, id) — not "the best one".

This module is GENERIC: it knows no domain, registry, store, or display language (text: `planner_text.py`)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

PLANNER_VERSION = 1
POLICY = "m4.v1"
ASK_CAP = 2  # one need: QUESTION, then EVIDENCE_REQUEST; skipped after that
CONSIDERED_CAP = 24  # the reason trail is capped: an audit trail, not a dump

KIND_QUESTION = "QUESTION"
KIND_EVIDENCE = "EVIDENCE_REQUEST"
KIND_ACTION = "ACTION"
KIND_HOLD = "HOLD"
KINDS = (KIND_QUESTION, KIND_EVIDENCE, KIND_ACTION, KIND_HOLD)

INTENT_GOAL = "RESOLVE_GOAL"
INTENT_APPLICABILITY = "RESOLVE_APPLICABILITY"
INTENT_CONTRADICTION = "RESOLVE_CONTRADICTION"
INTENT_STATE = "RESOLVE_STATE"
INTENT_EVIDENCE = "COLLECT_EVIDENCE"
INTENT_EXECUTE = "EXECUTE"
INTENT_PRESENT = "PRESENT"
INTENT_WAIT = "WAIT"
INTENTS = (
    INTENT_GOAL,
    INTENT_APPLICABILITY,
    INTENT_CONTRADICTION,
    INTENT_STATE,
    INTENT_EVIDENCE,
    INTENT_EXECUTE,
    INTENT_PRESENT,
    INTENT_WAIT,
)

ASK = "ASK"  # answerable through conversation
ACT = "ACT"  # shifts only through real-world action/measurement

_STRENGTH_RANK = {"hard": 0, "prereq": 1, "soft": 2}
_UNKNOWN = "UNKNOWN"
_APPLIES = "APPLIES"


# ───────────────────────────── helpers ─────────────────────────────
def _asked(inp: Mapping[str, Any], need_id: str) -> int:
    return int(((inp.get("history") or {}).get("asked") or {}).get(need_id, 0))


def _rank(strength: str | None) -> int:
    return _STRENGTH_RANK.get(strength or "", 3)


def _ctx_ok(c: Mapping[str, Any]) -> bool:
    """A context that drives the conversation: navigable AND applicability certainly APPLIES."""
    return bool(c.get("navigable")) and c.get("applicability") == _APPLIES


# Input parts that are NOT a basis for decisions: `texts` (display words, derived from registry/presentation)
# and `applicable` (an inspection copy of the applicable set; its content already lives in
# `requirements[*].contexts`). Neither is read by `plan_next_move`, so neither joins the fingerprint — that is
# what makes logs compactable without breaking replay.
NON_DECISION_KEYS = frozenset({"texts", "applicable"})


def digest(inp: Mapping[str, Any]) -> str:
    """Decision-input fingerprint (sorted keys, minus NON_DECISION_KEYS): same input => same decision."""
    core = {k: v for k, v in inp.items() if k not in NON_DECISION_KEYS}
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def _considered_row(need_id: str, verdict: str, why: str = "") -> dict[str, str]:
    row = {"need": need_id, "verdict": verdict}
    if why:
        row["why"] = why
    return row


def _counts(inp: Mapping[str, Any]) -> dict[str, int]:
    """RAW NEED counts (no scores): anchored requirements AND path conditions without a requirement, in
    contexts that drive the conversation (APPLIES + navigable). `open_askable` = still UNKNOWN (or in
    conflict) and shiftable by conversation; `open_act_only` = shifts only through action/measurement."""
    reqs = inp.get("requirements") or {}
    nav_paths = [p for p in inp.get("paths") or [] if p.get("navigable")]
    open_ask = open_act = resolved = 0
    for r in reqs.values():
        if not [c for c in r.get("contexts") or [] if _ctx_ok(c)]:
            continue
        if r.get("satisfaction") != _UNKNOWN and not r.get("conflict"):
            resolved += 1
        elif _channel(r, inp) == ASK:
            open_ask += 1
        else:
            open_act += 1
    for p in nav_paths:
        if p.get("applicability") != _APPLIES:
            continue
        for c in p.get("checks") or []:
            if c.get("requirement_id"):
                continue  # already counted via its requirement
            if c.get("state") != _UNKNOWN:
                resolved += 1
            elif _signal_resolvable(inp, c.get("signal")) == ASK:
                open_ask += 1
            else:
                open_act += 1
    return {
        "applicable": len(reqs),
        "navigable_paths": len(nav_paths),
        "resolved": resolved,
        "open_askable": open_ask,
        "open_act_only": open_act,
    }


def _decision(
    kind: str,
    intent: str,
    focus: dict[str, Any],
    stage: str,
    why: list[str],
    inp: Mapping[str, Any],
    *,
    need_id: str | None = None,
    contexts: list[dict[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
    considered: list[dict[str, str]] | None = None,
    stop: bool = False,
) -> dict[str, Any]:
    return {
        "version": PLANNER_VERSION,
        "policy": POLICY,
        "kind": kind,
        "intent": intent,
        "focus": focus,
        "stop": stop,
        "payload": payload or {},
        "reason": {
            "stage": stage,
            "need_id": need_id,
            "why": why,
            "contexts": contexts or [],
            "considered": (considered or [])[:CONSIDERED_CAP],
            "counts": _counts(inp),
            "input_digest": digest(inp),
        },
    }


# ───────────────── channel: can the conversation answer it? ─────────────────
def _signal_resolvable(inp: Mapping[str, Any], signal: str | None) -> str:
    """Defaults to ASK: what the planner does not know counts as askable; ASK_CAP guards the loop."""
    return ((inp.get("signals") or {}).get(signal or "")) or ASK


def _check_of(inp: Mapping[str, Any], path_id: str, check_id: str | None) -> Mapping[str, Any] | None:
    for p in inp.get("paths") or []:
        if p["path_id"] == path_id:
            return next((c for c in p.get("checks") or [] if str(c.get("check_id")) == str(check_id)), None)
    return None


def _channel(req: Mapping[str, Any], inp: Mapping[str, Any]) -> str:
    """ASK when the requirement's state can be shifted by conversational evidence: a ledger-backed formal
    rule, OR a path-check anchor whose signal is readable from state. Otherwise ACT.

    Gate A (Oct 15, owner contract): SUPPORT_SECOND_PASS on a prose requirement is a PATH LABEL (a mapper ->
    second-pass verifier is available), NOT askability — prose does not automatically enter the question
    pool (anti blanket-promotion; the ask priority & universe are preserved). Prose remains askable through
    the same route as before: a path-check anchor with a resolvable signal below."""
    if req.get("support") == "FORMAL_RULE":
        return ASK
    for c in req.get("contexts") or []:
        if c.get("via") == "check":
            chk = _check_of(inp, c["id"], c.get("ref"))
            if chk is not None and _signal_resolvable(inp, chk.get("signal")) == ASK:
                return ASK
    return ACT


# ─────────────────────────── dependencies (HOW) ───────────────────────────
def _node_of(route: Mapping[str, Any] | None, node_id: Any) -> Mapping[str, Any] | None:
    return next((n for n in (route or {}).get("nodes") or [] if str(n.get("node_id")) == str(node_id)), None)


def _sources(ctxs: list[dict[str, Any]]) -> list[str]:
    return sorted({s for c in ctxs for s in c.get("sources") or []})


def _routes_by_id(inp: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {r["route_id"]: r for r in inp.get("routes") or []}


def _node_blockers(route: Mapping[str, Any], node: Mapping[str, Any]) -> list[str]:
    """Node dependency requirements not yet PRESENT (empty = ready)."""
    by_id = {n["node_id"]: n for n in route.get("nodes") or []}
    out = []
    for d in node.get("depends_on") or []:
        dep = by_id.get(d)
        if dep is None or dep.get("state") != "PRESENT":
            out.append((dep or {}).get("requirement_id") or str(d))
    return sorted(out)


def _depth(route: Mapping[str, Any], node: Mapping[str, Any], seen: frozenset[str] = frozenset()) -> int:
    by_id = {n["node_id"]: n for n in route.get("nodes") or []}
    deps = [by_id[d] for d in node.get("depends_on") or [] if d in by_id and d not in seen]
    if not deps:
        return 0
    return 1 + max(_depth(route, d, seen | {node["node_id"]}) for d in deps)


def _ready(req: Mapping[str, Any], inp: Mapping[str, Any]) -> tuple[bool, list[str], int]:
    """(ready?, blockers, depth) — ready when ANY context is ready (check: always; node: deps PRESENT)."""
    routes = _routes_by_id(inp)
    blockers: list[str] = []
    best_depth: int | None = None
    ready = False
    for c in req.get("contexts") or []:
        if not _ctx_ok(c):
            continue
        if c.get("via") != "node":
            ready, best_depth = True, min(best_depth if best_depth is not None else 0, 0)
            continue
        route = routes.get(c["id"])
        node = _node_of(route, c.get("ref"))
        if route is None or node is None:
            ready, best_depth = True, min(best_depth if best_depth is not None else 0, 0)
            continue
        bl = _node_blockers(route, node)
        if not bl:
            ready = True
            d = _depth(route, node)
            best_depth = d if best_depth is None else min(best_depth, d)
        else:
            blockers.extend(bl)
    return ready, sorted(set(blockers)), best_depth or 0


# ───────────────────────────── stages ─────────────────────────────
def _stage_goal(inp: Mapping[str, Any], trace: list[dict[str, str]]) -> dict[str, Any] | None:
    g = inp.get("goal") or {}
    if g.get("established", True):
        return None
    nid = "goal"
    n = _asked(inp, nid)
    if n >= ASK_CAP:
        trace.append(_considered_row(nid, "SKIPPED", "ASKED_ENOUGH"))
        return None
    return _decision(
        KIND_QUESTION,
        INTENT_GOAL,
        {"type": "goal", "id": g.get("signal") or "goal"},
        "GOAL",
        [f"goal={g.get('code') or 'GOAL_NOT_ESTABLISHED'}", f"asked_before={n}"],
        inp,
        need_id=nid,
        payload={"signal": g.get("signal"), "code": g.get("code")},
        considered=[_considered_row(nid, "SELECTED")],
    )


def _stage_contradiction(inp: Mapping[str, Any], trace: list[dict[str, str]]) -> dict[str, Any] | None:
    considered: list[dict[str, str]] = []
    for rid in sorted((inp.get("requirements") or {})):
        r = inp["requirements"][rid]
        if not r.get("conflict"):
            continue
        ctxs = [c for c in r.get("contexts") or [] if c.get("navigable")]
        nid = f"contradiction:{rid}"
        if not ctxs:
            considered.append(_considered_row(nid, "SKIPPED", "NOT_NAVIGABLE"))
            continue
        n = _asked(inp, nid)
        if n >= ASK_CAP:
            considered.append(_considered_row(nid, "SKIPPED", "ASKED_ENOUGH"))
            continue
        considered.append(_considered_row(nid, "SELECTED"))
        return _decision(
            KIND_EVIDENCE,
            INTENT_CONTRADICTION,
            {"type": "requirement", "id": rid},
            "CONTRADICTION",
            ["conflict=true", f"satisfaction={r.get('satisfaction')}", f"navigable_contexts={len(ctxs)}",
             f"asked_before={n}"],
            inp,
            need_id=nid,
            contexts=ctxs,
            payload={"requirement_id": rid, "sources": _sources(ctxs)},
            considered=considered,
        )
    trace.extend(considered)
    return None


def _stage_applicability(inp: Mapping[str, Any], trace: list[dict[str, str]]) -> dict[str, Any] | None:
    """Navigable path with UNKNOWN applicability: ask the fact that makes applicability decidable."""
    considered: list[dict[str, str]] = []
    for p in sorted(inp.get("paths") or [], key=lambda x: x["path_id"]):
        if p.get("applicability") != _UNKNOWN:
            continue
        nid = f"applicability:{p['path_id']}"
        if not p.get("navigable"):
            considered.append(_considered_row(nid, "SKIPPED", "NOT_NAVIGABLE"))
            continue
        facts = [
            m for m in p.get("missing_applicability") or [] if _signal_resolvable(inp, m.get("signal")) == ASK
        ]
        if not facts:
            considered.append(_considered_row(nid, "SKIPPED", "NOT_ASKABLE_ACT"))
            continue
        n = _asked(inp, nid)
        if n >= ASK_CAP:
            considered.append(_considered_row(nid, "SKIPPED", "ASKED_ENOUGH"))
            continue
        considered.append(_considered_row(nid, "SELECTED"))
        sig = sorted(m["signal"] for m in facts)[0]
        return _decision(
            KIND_QUESTION if n == 0 else KIND_EVIDENCE,
            INTENT_APPLICABILITY,
            {"type": "path", "id": p["path_id"]},
            "APPLICABILITY",
            ["applicability=UNKNOWN", "navigable=true", f"missing_signals={len(facts)}", f"asked_before={n}"],
            inp,
            need_id=nid,
            contexts=[{"kind": "path", "id": p["path_id"], "applicability": _UNKNOWN, "navigable": True}],
            payload={"path_id": p["path_id"], "signal": sig},
            considered=considered,
        )
    trace.extend(considered)
    return None


def _state_candidates(inp: Mapping[str, Any]) -> list[dict[str, Any]]:
    """STATE needs: anchored requirements (UNKNOWN in APPLIES+navigable contexts) and free-standing checks."""
    out: list[dict[str, Any]] = []
    for rid in sorted((inp.get("requirements") or {})):
        r = inp["requirements"][rid]
        ctxs = [c for c in r.get("contexts") or [] if _ctx_ok(c)]
        if not ctxs or r.get("satisfaction") != _UNKNOWN or r.get("conflict"):
            continue
        ready, blockers, depth = _ready(r, inp)
        out.append(
            {
                "id": f"requirement:{rid}",
                "type": "requirement",
                "target_id": rid,
                "contexts": ctxs,
                "channel": _channel(r, inp),
                "ready": ready,
                "blockers": blockers,
                "depth": depth,
                "strength": min((_rank(c.get("strength")) for c in ctxs), default=3),
                "evidence_on_file": bool(r.get("adjudicated")),
                "signal": None,
            }
        )
    for p in sorted(inp.get("paths") or [], key=lambda x: x["path_id"]):
        if not (p.get("navigable") and p.get("applicability") == _APPLIES):
            continue
        for c in p.get("checks") or []:
            if c.get("requirement_id") or c.get("state") != _UNKNOWN:
                continue
            ctx = {"kind": "path", "id": p["path_id"], "applicability": _APPLIES, "via": "check",
                   "strength": c.get("kind"), "navigable": True, "ref": c.get("check_id")}
            out.append(
                {
                    "id": f"check:{p['path_id']}:{c.get('check_id')}",
                    "type": "check",
                    "target_id": f"{p['path_id']}:{c.get('check_id')}",
                    "contexts": [ctx],
                    "channel": _signal_resolvable(inp, c.get("signal")),
                    "ready": True,
                    "blockers": [],
                    "depth": 0,
                    "strength": _rank(c.get("kind")),
                    "evidence_on_file": False,
                    "signal": c.get("signal"),
                }
            )
    return out


def _stage_state(inp: Mapping[str, Any], trace: list[dict[str, str]]) -> dict[str, Any] | None:
    cands = _state_candidates(inp)
    considered: list[dict[str, str]] = []
    eligible: list[dict[str, Any]] = []
    for c in cands:
        n = _asked(inp, c["id"])
        if c["channel"] != ASK:
            considered.append(_considered_row(c["id"], "SKIPPED", "NOT_ASKABLE_ACT"))
        elif not c["ready"]:
            why = "DEPENDENCY_UNRESOLVED:" + ",".join(c["blockers"])
            considered.append(_considered_row(c["id"], "SKIPPED", why))
        elif n >= ASK_CAP:
            considered.append(_considered_row(c["id"], "SKIPPED", "ASKED_ENOUGH"))
        else:
            c["asked"] = n
            eligible.append(c)
    if not eligible:
        trace.extend(considered)
        return None
    # deterministic information policy (NOT a business ranking): the most decisive condition first, then the
    # one needed by the most contexts, then the earlier prerequisite in the dependency graph, then id.
    eligible.sort(key=lambda c: (c["strength"], -len(c["contexts"]), c["depth"], c["id"]))
    pick = eligible[0]
    considered = [_considered_row(pick["id"], "SELECTED")] + [
        _considered_row(c["id"], "DEFERRED", "LOWER_INFORMATION_PRIORITY") for c in eligible[1:]
    ] + considered
    escalate = pick["asked"] >= 1 or pick["evidence_on_file"]
    why = [
        "applicability=APPLIES",
        "satisfaction=UNKNOWN",
        f"navigable_contexts={len(pick['contexts'])}",
        "dependency_ready=true",
        f"strength_rank={pick['strength']}",
        "resolvable_by=ASK",
        f"asked_before={pick['asked']}",
        "blocks_next_decision=true",
    ]
    if pick["evidence_on_file"]:
        why.append("evidence_on_file=true")
    payload: dict[str, Any] = {"need_type": pick["type"]}
    if pick["type"] == "requirement":
        payload["requirement_id"] = pick["target_id"]
    else:
        payload["check_ref"] = pick["target_id"]
        payload["signal"] = pick["signal"]
    return _decision(
        KIND_EVIDENCE if escalate else KIND_QUESTION,
        INTENT_EVIDENCE if escalate else INTENT_STATE,
        {"type": pick["type"], "id": pick["target_id"]},
        "STATE",
        why,
        inp,
        need_id=pick["id"],
        contexts=pick["contexts"],
        payload=payload,
        considered=considered,
    )


def _stage_emergence(inp: Mapping[str, Any], trace: list[dict[str, str]]) -> dict[str, Any] | None:
    """No navigable path: ask the fact that would let a path be born (not guess a path)."""
    if any(p.get("navigable") for p in inp.get("paths") or []):
        return None
    facts = list(inp.get("facts_missing") or [])
    considered: list[dict[str, str]] = []
    eligible = []
    for f in facts:
        nid = f"signal:{f['signal']}"
        n = _asked(inp, nid)
        if _signal_resolvable(inp, f["signal"]) != ASK:
            considered.append(_considered_row(nid, "SKIPPED", "NOT_ASKABLE_ACT"))
        elif n >= ASK_CAP:
            considered.append(_considered_row(nid, "SKIPPED", "ASKED_ENOUGH"))
        else:
            eligible.append((f, n))
    if not eligible:
        trace.extend(considered)
        return None
    src_rank = {"emerging": 0, "undetermined": 1, "unresolved": 2}
    eligible.sort(key=lambda fn: (src_rank.get(fn[0].get("source"), 3), -len(fn[0].get("needed_by") or []),
                                  fn[0]["signal"]))
    f, n = eligible[0]
    nid = f"signal:{f['signal']}"
    considered = [_considered_row(nid, "SELECTED")] + [
        _considered_row(f"signal:{x['signal']}", "DEFERRED", "LOWER_INFORMATION_PRIORITY")
        for x, _ in eligible[1:]
    ] + considered
    return _decision(
        KIND_QUESTION if n == 0 else KIND_EVIDENCE,
        INTENT_STATE if n == 0 else INTENT_EVIDENCE,
        {"type": "signal", "id": f["signal"]},
        "EMERGENCE",
        ["navigable_paths=0", f"source={f.get('source')}", f"needed_by={len(f.get('needed_by') or [])}",
         "resolvable_by=ASK", f"asked_before={n}", "blocks_next_decision=true"],
        inp,
        need_id=nid,
        payload={
            "signal": f["signal"],
            "source": f.get("source"),
            "needed_by": list(f.get("needed_by") or []),
        },
        considered=considered,
    )


def _applicable_execute(inp: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    """The best EXECUTE (route, node) on an APPLICABLE, navigable route, or None.

    NextMove v1 is a GLOBAL selector: an applicability question on any route beats EXECUTE on every route.
    That holds back action on a clearly applicable route to ask about another route (one we may never work
    on). The planner does not change that selector; it only refuses to let a question about a DIFFERENT route
    block when the applicable route has a real step. Order = the same key as the selector (hard first,
    route_id, node order) — not a ranking."""
    best: tuple[tuple[int, str, int], Mapping[str, Any], Mapping[str, Any]] | None = None
    for r in inp.get("routes") or []:
        if not (r.get("navigable") and r.get("applicability") == _APPLIES):
            continue
        for pos, n in enumerate(r.get("nodes") or []):
            done = n.get("state") == "PRESENT" or n.get("execution_view") == "EXECUTED"
            if done or n.get("executability") != "TRUE":
                continue
            key = (0 if n.get("strength") == "hard" else 1, str(r.get("route_id")), pos)
            if best is None or key < best[0]:
                best = (key, r, n)
    return (best[1], best[2]) if best else None


def _execute_decision(
    inp: Mapping[str, Any], route: Mapping[str, Any], node: Mapping[str, Any], why: list[str]
) -> dict[str, Any]:
    return _decision(
        KIND_ACTION,
        INTENT_EXECUTE,
        {"type": "node", "id": str(node.get("node_id"))},
        "DOWNSTREAM",
        why,
        inp,
        need_id=f"node:{node.get('node_id')}",
        payload={
            "route_id": route.get("route_id"),
            "node_id": node.get("node_id"),
            "requirement_id": node.get("requirement_id"),
            "activity": node.get("activity"),
        },
        stop=True,
    )


def _stage_downstream(inp: Mapping[str, Any], trace: list[dict[str, str]]) -> dict[str, Any] | None:
    """NextMove v1 (the route frontier selector) is passed through as a downstream capability — not a
    second engine."""
    nm = inp.get("next_move_v1")
    if not nm:
        return None
    out = nm.get("output")
    routes = _routes_by_id(inp)
    route = routes.get(nm.get("route_id") or "")
    if out == "ACTION":
        node = dict(_node_of(route, nm.get("frontier_ref")) or {})
        node.setdefault("node_id", nm.get("frontier_ref"))
        return _execute_decision(
            inp, route or {"route_id": nm.get("route_id")}, node,
            ["source=next_move_v1", "frontier=EXECUTE", "blocking_uncertainty=none"],
        )
    if out == "EVIDENCE_REQUEST":
        node = _node_of(route, nm.get("frontier_ref")) or {}
        nid = f"node:{nm.get('frontier_ref')}"
        n = _asked(inp, nid)
        if n >= ASK_CAP:
            trace.append(_considered_row(nid, "SKIPPED", "ASKED_ENOUGH"))
            return None
        return _decision(
            KIND_EVIDENCE,
            INTENT_EVIDENCE,
            {"type": "node", "id": str(nm.get("frontier_ref"))},
            "DOWNSTREAM",
            ["source=next_move_v1", "frontier=VERIFY", f"asked_before={n}"],
            inp,
            need_id=nid,
            payload={"route_id": nm.get("route_id"), "node_id": nm.get("frontier_ref"),
                     "requirement_id": node.get("requirement_id"), "activity": node.get("activity")},
        )
    if out == "QUESTION":
        nid = f"applicability:{nm.get('route_id')}"
        n = _asked(inp, nid)
        alt = _applicable_execute(inp)
        if alt is not None and (route or {}).get("applicability") != _APPLIES:
            trace.append(_considered_row(nid, "SKIPPED", "APPLICABLE_ROUTE_IS_ACTIONABLE"))
            why = ["source=next_move_v1", "frontier=RESOLVE_APPLICABILITY(other_route)"]
            return _execute_decision(inp, alt[0], alt[1], why + ["applicable_route_actionable=true"])
        if n >= ASK_CAP:
            trace.append(_considered_row(nid, "SKIPPED", "ASKED_ENOUGH"))
            return None
        return _decision(
            KIND_QUESTION if n == 0 else KIND_EVIDENCE,
            INTENT_APPLICABILITY,
            {"type": "route", "id": str(nm.get("route_id"))},
            "DOWNSTREAM",
            ["source=next_move_v1", "frontier=RESOLVE_APPLICABILITY", f"asked_before={n}"],
            inp,
            need_id=nid,
            payload={"route_id": nm.get("route_id"), "path_id": (route or {}).get("path_id")},
        )
    if out == "HOLD":
        return _decision(
            KIND_HOLD,
            INTENT_WAIT,
            {"type": "route", "id": str(nm.get("route_id") or "")},
            "DOWNSTREAM",
            ["source=next_move_v1", "frontier=none", "open_route_waits_for_measured_result"],
            inp,
            payload={"detail": nm.get("reason")},
            stop=True,
        )
    return None


def _stage_fallback(inp: Mapping[str, Any]) -> dict[str, Any]:
    nav = sorted(p["path_id"] for p in inp.get("paths") or [] if p.get("navigable"))
    if nav:
        return _decision(
            KIND_ACTION,
            INTENT_PRESENT,
            {"type": "navigation", "id": "paths"},
            "FALLBACK",
            ["blocking_uncertainty=none", f"navigable_paths={len(nav)}", "enough_to_map=true"],
            inp,
            payload={"path_ids": nav},
            stop=True,
        )
    return _decision(
        KIND_HOLD,
        INTENT_WAIT,
        {"type": "navigation", "id": "none"},
        "FALLBACK",
        ["navigable_paths=0", "no_safe_next_question=true"],
        inp,
        payload={"unresolved": [u.get("code") for u in inp.get("unresolved") or []]},
        stop=True,
    )


def _with_trace(decision: dict[str, Any], trace: list[dict[str, str]]) -> dict[str, Any]:
    """Decision trail = the deciding stage's rows + rows skipped by earlier stages (deduped, capped)."""
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    for r in list(decision["reason"]["considered"]) + trace:
        key = (r["need"], r["verdict"])
        if key not in seen:
            seen.add(key)
            rows.append(r)
    decision["reason"]["considered"] = rows[:CONSIDERED_CAP]
    return decision


_STAGES = (
    _stage_goal,
    _stage_contradiction,
    _stage_applicability,
    _stage_state,
    _stage_emergence,
    _stage_downstream,
)


def plan_next_move(inp: Mapping[str, Any]) -> dict[str, Any]:
    """PlannerInput -> decision. PURE: the same input always yields the same decision.

    Fail-safe: an incomplete input never produces an invented question — it falls back to HOLD."""
    if int(inp.get("version", 0)) != PLANNER_VERSION:
        return _decision(KIND_HOLD, INTENT_WAIT, {"type": "navigation", "id": "none"}, "INPUT",
                         [f"input_version_mismatch={inp.get('version')}"], inp, stop=True)
    trace: list[dict[str, str]] = []  # rows skipped by earlier stages join the final decision trail
    for stage in _STAGES:
        d = stage(inp, trace)
        if d is not None:
            return _with_trace(d, trace)
    return _with_trace(_stage_fallback(inp), trace)


def replay(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Stored {input, decision} -> recompute and compare. `ok` only when the decision is identical.

    Compacted entries (input discarded to save space; decision + digest kept) cannot replay: `ok` = None
    with reason `COMPACTED` — honest, not "passing"."""
    if "input" not in entry:
        return {"ok": None, "reason": "COMPACTED", "expected": entry.get("decision"), "actual": None}
    actual = plan_next_move(entry["input"])
    return {"ok": actual == entry["decision"], "expected": entry["decision"], "actual": actual}
