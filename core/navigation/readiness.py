"""Readiness Projection — a PROJECTION of verified requirement state over a route, not the decider of
its meaning.

    Possible Path (feasibility, lifecycle, applicability)
  + Route (node: requirement, satisfaction, executability)          -> Readiness Projection
  + Check path (verified world conditions, anchored by requirement_id)

Readiness is a CONSUMER: the meaning of a requirement (definition, observability, satisfaction rules)
belongs to the Requirement Registry, and its display text belongs to Requirement Presentation. Adding a
requirement does NOT require changing this module: every requirement_id appearing in a route/check is
read through `describe` (curated or deterministic fallback). There is no requirement dictionary here and
no string-gate -> requirement mapping: checks carry `requirement_id` from the machine that produced them.

Three axes stay separate in the output: applicability (path & route), satisfaction (per item),
executability (per node and per path). No scalar score hides them.

Invariants guarded here (not in the readers): PRESENT != ABSENT, UNKNOWN != ABSENT, PARTIAL != PRESENT.
Absence of evidence is not evidence of absence: UNKNOWN items stay UNKNOWN, never downgraded."""

from __future__ import annotations

import hashlib
import json
from typing import Callable

from core.navigation.compat import NAV_CURRENT, assess_path_set
from core.navigation.contracts import (
    FEASIBILITY_BASIS_UNCONDITIONAL,
    Applicability,
    Executability,
    Satisfaction,
    feasibility_from_checks,
)
from core.navigation.evaluator import apply_lifecycle
from core.navigation.narrative import fallback_narrative
from core.navigation.presentation import humanize_id
from core.navigation.requirement_state import merge_readings

PROJECTION_VERSION = 4  # v4: projected feasibility = the ADJUDICATED reading (conflict -> UNDETERMINED)

Describe = Callable[[str], dict[str, dict[str, str]]]

_SAT = {s.value for s in Satisfaction}
_ROUTE_APPLICABILITY = {
    "APPLIES": Applicability.APPLIES,
    "NOT_APPLICABLE": Applicability.NOT_APPLICABLE,
    "UNDETERMINED": Applicability.UNKNOWN,
}


# Conflict note text comes from the engine (UI language `en`, basis `id`) — the UI only renders it.
_CONFLICT_NOTE = {
    "text": "Two readings of your evidence disagree here, so we do not count it as settled.",
    "lang": "en",
}


def _low(label: str) -> str:
    return label[:1].lower() + label[1:] if label else label


def _node_state(n: dict) -> str:
    st = str(((n.get("satisfaction") or {}).get("status")) or Satisfaction.UNKNOWN).upper()
    return st if st in _SAT else str(Satisfaction.UNKNOWN)


def _check_state(c: dict) -> str:
    st = str(c.get("state") or Satisfaction.UNKNOWN).upper()
    return st if st in _SAT else str(Satisfaction.UNKNOWN)


def _pick(i18n: dict | None, lang: str, field: str, default: str) -> dict[str, str]:
    """Per-language text FROM DATA (no dictionary here): the requested language when available; otherwise
    the machine text (language `id`) with an honest language marker."""
    v = ((i18n or {}).get(lang) or {}).get(field)
    return {"text": v, "lang": lang} if v else {"text": default, "lang": "id"}


def _title_of(
    requirement_id: str | None, check: dict | None, describe: Describe, lang: str = "en"
) -> dict[str, str]:
    """Item title: the requirement presentation when an anchor exists; otherwise the check text;
    otherwise derived from the id."""
    if requirement_id:
        return dict(describe(requirement_id)["title"])
    if check and (check.get("title") or ((check.get("i18n") or {}).get(lang) or {}).get("title")):
        return {**_pick(check.get("i18n"), lang, "title", check.get("title") or ""), "source": "engine"}
    ident = (check or {}).get("check_id") or ""
    return {"text": humanize_id(ident) if ident else "", "lang": "en", "source": "fallback"}


def _guidance(
    requirement_id: str | None, node: dict | None, check: dict | None, describe: Describe, lang: str = "en"
) -> dict[str, str]:
    """How to obtain/verify: curated verification > route node activity (machine text) > check unlock >
    registry fallback. The order is fixed here so the UI never chooses on its own."""
    pres = describe(requirement_id)["verification"] if requirement_id else None
    if pres and pres["source"] == "curated":
        return dict(pres)
    if node and node.get("activity"):
        en_act = ((node.get("i18n") or {}).get(lang) or {}).get("activity")
        if en_act:
            return {"text": str(en_act), "lang": lang, "source": "engine"}
        return {"text": str(node["activity"]), "lang": "id", "source": "engine"}
    if check and check.get("unlock"):
        return {**_pick(check.get("i18n"), lang, "unlock", str(check["unlock"])), "source": "engine"}
    return dict(pres) if pres else {"text": "", "lang": "id", "source": "fallback"}


def node_guidance(
    requirement_id: str | None, node: dict | None, describe: Describe, lang: str = "en"
) -> dict[str, str]:
    """The ONE-DOOR guidance rule for route nodes in the composition payload (same rule as `_guidance`
    in the readiness projection): curated verification > node activity > fallback. Consumers (the
    per-path "Next move" UI) never choose on their own; the check path is irrelevant here (None)."""
    return _guidance(requirement_id, node, None, describe, lang)


def _route_item(n: dict, by_id: dict[str, dict], describe: Describe, lang: str = "en") -> dict:
    req = ((n.get("resolves") or []) or [""])[0]
    state = _node_state(n)
    waits = []
    for d in n.get("depends_on") or []:
        dep = by_id.get(d)
        if dep and _node_state(dep) != Satisfaction.PRESENT:
            dreq = ((dep.get("resolves") or []) or [""])[0]
            if dreq:
                waits.append({"key": dreq, "title": describe(dreq)["title"]["text"]})
    return {
        "key": req or str(n.get("node_id") or ""),
        "requirement_id": req or None,
        "check_id": None,
        "sources": ["route"],
        "state": state,
        "partial": state == Satisfaction.PARTIAL,
        "soft": n.get("strength") == "soft",
        "executed": n.get("execution_view") == "EXECUTED",
        "executability": str(n.get("executability") or Executability.UNKNOWN),
        "title": _title_of(req or None, None, describe, lang),
        "guidance": _guidance(req or None, n, None, describe, lang),
        "activity": str(n.get("activity") or ""),
        "reason": {"text": "", "lang": lang},
        "unlock": {"text": "", "lang": lang},
        "waits_on": waits,
        # evidence anchor: a definite node state = the adjudication (ledger) result; UNKNOWN = none yet
        "evidence": ([f"ledger:{req}"] if req and state != Satisfaction.UNKNOWN else []),
    }


def _check_item(c: dict, describe: Describe, lang: str = "en") -> dict:
    req = c.get("requirement_id")
    state = _check_state(c)
    ev = [f"check:{c['check_id']}"] if state != Satisfaction.UNKNOWN else []
    ev += [f"ev:{r}" for r in c.get("refs") or []] if state != Satisfaction.UNKNOWN else []
    item = {
        "key": req or c["check_id"],
        "requirement_id": req,
        "check_id": c["check_id"],
        "sources": ["check"],
        "state": state,
        "partial": state == Satisfaction.PARTIAL,
        "soft": False,
        "executed": False,
        "executability": None,
        "title": _title_of(req, c, describe, lang),
        "guidance": _guidance(req, None, c, describe, lang),
        "activity": "",
        "reason": _pick(c.get("i18n"), lang, "reason", str(c.get("reason") or "")),
        "unlock": _pick(c.get("i18n"), lang, "unlock", str(c.get("unlock") or "")),
        "waits_on": [],
        "evidence": ev,
    }
    # The RAW signal reading (when the evaluator merged with the ledger) is passed through to the readiness
    # projection so _ledger_merge/canonical_feasibility see the dispute, not the already-merged state.
    if "state_signal" in c:
        item["state_signal"] = c["state_signal"]
    return item


def _ledger_merge(
    c: dict, ledger_state_of: Callable[[str], str | None], _CONFLICT_AUTHORITY: str = "ledger"
) -> None:
    """Route-less path: the check has no route-node twin, but when the check is anchored on a
    `requirement_id`, the ledger state (adjudication) REMAINS authoritative — the Requirement State
    Reader is the same source for the Planner and Readiness (docs/14 §25, F3d). ONE merge rule
    (`merge_readings`), not a second evaluator: a definite state beats UNKNOWN; differing definite
    states = a dispute with ledger authority; UNKNOWN is never downgraded."""
    rid = c["requirement_id"]
    primary = str(ledger_state_of(rid) or Satisfaction.UNKNOWN)
    # state_signal = the raw signal reading (when the evaluator already merged) so the ledger-vs-check
    # conflict stays visible here; falls back to the old state for callers not yet using the new evaluator.
    raw = c.get("state_signal", c["state"])
    merged, bad = merge_readings(primary, [raw])
    if merged != raw:
        c["sources"] = ["ledger", "check"]
        c["state"] = merged
        c["partial"] = merged == Satisfaction.PARTIAL
        c["evidence"] = [f"ledger:{rid}"] if merged != Satisfaction.UNKNOWN else c["evidence"]
    if bad:
        c["sources"] = sorted(set(c["sources"]) | {"ledger"})
        c["settled"] = False
        c["conflict"] = {
            "sources": {"ledger": primary, "check": raw},
            "check_id": c["check_id"],
            "authority": _CONFLICT_AUTHORITY,
            "resolution": "AUTHORITY",
            "resolved_to": c["state"],
            "note": dict(_CONFLICT_NOTE),
        }


def _adjudicate(
    route_items: list[dict],
    check_items: list[dict],
    ledger_state_of: Callable[[str], str | None] | None = None,
) -> list[dict]:
    """Two readings of the same state (route node vs check path) become one item.

    Twin = the SAME requirement_id (an anchor from the machine, not a string match). A DEFINITE state
    beats UNKNOWN.

    CONFLICT (two differing definite states): a SEMANTIC CONTRACT — not a fifth state.
      source & authority: route node = the state from LEDGER ADJUDICATION (the registry's satisfaction
                          rules over tiered evidence); check path = a signal reading of that state. Ledger
                          adjudication has higher authority, so the node state is the one projected.
      recorded           : a structured `conflict` on the item (both readings, authority, resolution) —
                          the conflict is never silently swallowed.
      impact             : the item is marked `settled=False`; it is NOT counted as proven in `counts`
                          (`conflicted`), and the narrative may only call it a conflict (CONFLICT claim).
    This mirrors the evidence adjudicator (core/stages/adjudicate.py D-A1a/b): a conflict is decided into a
    4-state enum and both of its sides are recorded; CONFLICT is not a Satisfaction value because it is a
    dispute between READERS, not a world state (adding it would break the locked registry/adjudication
    contract).
    UNKNOWN is never downgraded to ABSENT.

    MULTI-SOURCE: ALL checks sharing the same requirement_id adjudicate against the node — not just the
    first one. An UNKNOWN item adopts the first DEFINITE twin; every DEFINITE twin that differs from the
    projected state becomes a conflict source (`check`, `check_2`, ... — a multi-check dispute stays one
    item, not duplicate items that hide the disagreement)."""
    out: list[dict] = []
    used: set[int] = set()
    for it in route_items:
        twins = [
            i
            for i, c in enumerate(check_items)
            if c["requirement_id"] and c["requirement_id"] == it["requirement_id"] and i not in used
        ]
        if twins:
            used.update(twins)
            first = check_items[twins[0]]
            it["sources"] = ["route", "check"]
            it["check_id"] = first["check_id"]
            it["reason"], it["unlock"] = first["reason"], first["unlock"]
            # ONE merge rule with the session reader (`requirement_state.merge_readings`): a definite state
            # beats UNKNOWN (the FIRST definite reading is adopted); differing definite readings = a dispute.
            # Compare the RAW signal readings (state_signal) against the route node — an evaluator-merged
            # state must not mask the dispute on a ROUTED path (R-1).
            raw_readings = [check_items[j].get("state_signal", check_items[j]["state"]) for j in twins]
            route_state = it["state"]
            merged, bad = merge_readings(route_state, raw_readings)
            if merged != route_state:
                ad = next(check_items[j] for k, j in enumerate(twins)
                          if raw_readings[k] != Satisfaction.UNKNOWN)
                it["state"] = merged
                it["partial"] = merged == Satisfaction.PARTIAL
                it["evidence"] = list(ad["evidence"])
            disagreeing = [(check_items[twins[k]], raw_readings[k]) for k in bad]
            if disagreeing:
                sources: dict[str, str] = {"route": route_state}
                ids: list[str] = []
                for k, (c, raw) in enumerate(disagreeing):
                    sources["check" if k == 0 else f"check_{k + 1}"] = raw
                    ids.append(c["check_id"])
                it["settled"] = False
                it["conflict"] = {
                    "sources": sources,
                    "check_id": ids[0],
                    "authority": "route",
                    "resolution": "AUTHORITY",
                    "resolved_to": it["state"],
                    "note": dict(_CONFLICT_NOTE),
                }
                if len(ids) > 1:
                    it["conflict"]["additional_check_ids"] = ids[1:]
        out.append(it)
    for i, c in enumerate(check_items):
        if i in used:
            continue
        # F3d: a route-less path still reads the ledger through the Requirement State Reader —
        # the SAME semantics as the Planner, not a raw-check reader alone.
        if ledger_state_of is not None and c["requirement_id"]:
            _ledger_merge(c, ledger_state_of)
        out.append(c)
    return out


def path_conflicted_requirements(
    path: dict, route_nodes: list[dict] | None, ledger_state_of: Callable[[str], str | None] | None = None
) -> set[str]:
    """Requirements whose readings are DISPUTED: the ledger node (route) and the check path are both
    definite and differ; or — on a route-less path — the ledger (Requirement State Reader) and the check
    path are both definite and differ.

    The canonical Task C function (doc 14 §10.1) — ONE conflict definition shared by the readiness
    projection AND the NextMove gate; there is no second conflict evaluator. Agrees with `_adjudicate`:
    twins = the same requirement_id; a definite state beats UNKNOWN; UNKNOWN is never a disputing party."""
    if not route_nodes and ledger_state_of is None:
        return set()
    by_req: dict[str, str] = {}
    for n in (route_nodes or []):
        rid = ((n.get("resolves") or []) or [""])[0]
        if rid:
            by_req[rid] = _node_state(n)
    out: set[str] = set()
    for c in path.get("checks") or []:
        req = c.get("requirement_id")
        if not req:
            continue
        # Compare the RAW signal reading (state_signal) against the ledger — an evaluator-merged state
        # must not mask the dispute.
        raw_c = dict(c, state=c["state_signal"]) if c.get("state_signal") is not None else c
        st, ns = _check_state(raw_c), by_req.get(req)
        if ledger_state_of is not None and ns is None:
            # route-less: the comparison reading comes from the Requirement State Reader
            ls = str(ledger_state_of(req) or Satisfaction.UNKNOWN)
            ns = ls if ls != Satisfaction.UNKNOWN else None
        if st != Satisfaction.UNKNOWN and ns not in (None, Satisfaction.UNKNOWN) and ns != st:
            out.add(req)
    return out


def canonical_feasibility(
    path: dict, route_nodes: list[dict] | None, ledger_state_of: Callable[[str], str | None] | None = None
) -> str:
    """Feasibility over the ADJUDICATED reading (Task C, doc 14 §10.1): a DISPUTED condition proves
    nothing in either direction — it contributes UNKNOWN (not its raw state) to the same
    `feasibility_from_checks` the engine uses at diagnosis. A disputed hard-check is therefore not
    CONTRADICTED (STOP), and support backed by a disputed check is not SUPPORTED. With no dispute, the
    engine reading passes through unchanged.
    F3d: on a route-less path, `ledger_state_of` is forwarded to `path_conflicted_requirements` so the
    ledger-vs-check dispute is visible to feasibility with the SAME semantics as satisfaction and the
    Planner — not a raw-check reader alone.
    The raw reading is still audited in the projection's `feasibility_engine`. ONE rule for readiness AND
    NextMove — not two evaluators that could disagree."""
    conflicted = path_conflicted_requirements(path, route_nodes, ledger_state_of)
    if not conflicted:
        return str(path.get("feasibility") or "")
    checks = [
        dict(c, state="UNKNOWN") if c.get("requirement_id") in conflicted else c
        for c in path.get("checks") or []
    ]
    return str(
        feasibility_from_checks(
            checks, unconditional=path.get("feasibility_basis") == FEASIBILITY_BASIS_UNCONDITIONAL
        )
    )


def _counts(items: list[dict]) -> dict:
    """Item counts as-is (no score). Conflicted items are counted under `conflicted`, not in their state
    bucket: they must not add to "proven" (all buckets + conflicted = total)."""
    live = [it for it in items if it.get("settled", True)]
    n = lambda s: sum(1 for it in live if it["state"] == s)  # noqa: E731
    return {
        "present": n(Satisfaction.PRESENT),
        "absent": n(Satisfaction.ABSENT),
        "partial": n(Satisfaction.PARTIAL),
        "unknown": n(Satisfaction.UNKNOWN),
        "conflicted": len(items) - len(live),
        "total": len(items),
    }


def _path_executability(route: dict | None, nodes: list[dict]) -> str | None:
    """Path-level executability, derived from the nodes — not a score. None = nothing left to do."""
    if not route:
        return str(Executability.UNKNOWN)
    if _ROUTE_APPLICABILITY.get((route.get("applicability") or {}).get("status")) != Applicability.APPLIES:
        return str(Executability.UNKNOWN)
    pending = [n for n in nodes if _node_state(n) != Satisfaction.PRESENT]
    if not pending:
        return None
    ex = {str(n.get("executability")) for n in pending}
    if Executability.TRUE in ex:
        return str(Executability.TRUE)
    if Executability.UNKNOWN in ex:
        return str(Executability.UNKNOWN)
    return str(Executability.FALSE)


def build_projection(
    path_set: dict | None,
    route_data: dict | None,
    describe: Describe,
    *,
    lifecycles: dict[str, dict] | None = None,
    lang: str = "en",
    state_reader: Callable[[str], str | None] | None = None,
) -> dict:
    """(PathSet, the user's composition route, requirement describe, current lifecycles, language, state
reader) -> the final projection.

    A Path = the authoritative identity from the PathSet (0..N); routes are joined via `strategy_id`, not
    via motion. A path without a route still appears (items from its checks alone):
    Possible Path != RouteTemplate.
    `state_reader` (StatusReader: requirement_id -> ledger state or None) enforces F3d: checks anchored on
    a requirement_id in a route-less path are read through the SAME Requirement State Reader semantics as
    the Planner (`merge_readings`), not the raw check state alone."""
    # Routes are joined to paths via strategy. No "last one wins": more than one route for one path has no
    # projection semantics yet, so it fails deterministically (ROUTE-04) instead of overwriting silently.
    routes_by_strategy: dict[str, list[dict]] = {}
    for r in (route_data or {}).get("routes") or []:
        routes_by_strategy.setdefault(str(r.get("strategy_id") or ""), []).append(r)
    paths: list[dict] = []
    # Task G (DATA-01/03): only a PathSet judged CURRENT has its contents read. LEGACY (missing, another
    # version, or CORRUPT CONTENT) -> paths=[] + a LEGACY navigation below: corrupt content must not
    # 500 downstream, and must not masquerade as the engine finding "no path".
    usable = assess_path_set(path_set)["status"] == NAV_CURRENT
    for p0 in ((path_set or {}).get("paths") or []) if usable else []:
        candidates = routes_by_strategy.get(p0["strategy_id"], [])
        if len(candidates) > 1:
            raise ValueError(
                f"path {p0['path_id']!r}: {len(candidates)} route untuk satu strategi — proyeksi readiness "
                "mendukung tepat satu route per path"
            )
        route = candidates[0] if candidates else None
        if route is not None and route.get("path_id") not in (None, p0["path_id"]):
            raise ValueError(
                f"route {route.get('route_id')!r} milik path {route.get('path_id')!r}, "
                f"bukan {p0['path_id']!r}"
            )
        nodes = (route or {}).get("nodes") or []
        by_id = {n.get("node_id"): n for n in nodes}
        items = _adjudicate(
            [_route_item(n, by_id, describe, lang) for n in nodes],
            [_check_item(c, describe, lang) for c in p0["checks"]],
            ledger_state_of=state_reader,
        )
        # Projected feasibility = the ADJUDICATED reading (Task C, doc 14 §10.1): a disputed condition
        # (ledger node vs check path) proves nothing in either direction -> contributes UNKNOWN, so a
        # dispute on a hard check no longer shows as STOP and disputed support no longer shows as
        # SUPPORTED. The engine's raw reading is still audited in `feasibility_engine`.
        feasibility_engine = p0["feasibility"]
        canon = canonical_feasibility(p0, nodes, state_reader)
        p = apply_lifecycle({**p0, "feasibility": canon}, (lifecycles or {}).get(p0["path_id"]))
        for it in items:
            it["label_ok"] = it["title"]["lang"] == "en" and bool(it["title"]["text"])
        paths.append(
            {
                "key": p["path_id"],
                "path_id": p["path_id"],
                "strategy_id": p["strategy_id"],
                "motion": p.get("motion"),
                "title": p["title"],
                "presentation": p.get("presentation") or {},
                "basis": _pick(p.get("presentation"), lang, "basis", p.get("basis") or ""),
                "status": p["status"],
                "feasibility": p["feasibility"],
                "feasibility_engine": feasibility_engine,
                "lifecycle": p["lifecycle"],
                "applicability": p["applicability"],
                "stop_provenance": p["stop_provenance"],
                "advisory": (
                    {"text": (p.get("advisory_i18n") or {})[lang], "lang": lang}
                    if (p.get("advisory_i18n") or {}).get(lang)
                    else {"text": p.get("advisory") or "", "lang": "id"}
                ),
                "provenance": p.get("provenance") or {},
                # the path's origin + reason for existing when born from a Candidate Possibility (CAND-06)
                "candidate": _candidate_view(p, lang),
                "route": (
                    {
                        "route_id": route.get("route_id"),
                        "template_id": route.get("template_id"),
                        "applicability": str(
                            _ROUTE_APPLICABILITY.get(
                                (route.get("applicability") or {}).get("status"), Applicability.UNKNOWN
                            )
                        ),
                        "lineage_status": route.get("lineage_status"),
                        "revision_no": route.get("revision_no"),
                    }
                    if route
                    else None
                ),
                "route_substrate": p.get("route_substrate") or {},
                "executability": _path_executability(route, nodes),
                "items": items,
                "conflicts": [it["key"] for it in items if not it.get("settled", True)],
                "counts": _counts(items),
                "narrative": fallback_narrative(p["status"], items),
            }
        )
    return {
        "version": PROJECTION_VERSION,
        # LEGACY = an artifact older than the navigation schema: `paths=[]` below is NOT an
        # engine finding (DATA-01)
        "navigation": assess_path_set(path_set),
        "paths": paths,
        "unresolved": list((path_set or {}).get("unresolved") or []),
        "generation": (path_set or {}).get("generation") or {},
        # newly emerging possibilities (not paths yet): from CURRENT PathSets only, no effect on counts
        "emerging": _emerging(path_set, lang) if usable else [],
    }


def _candidate_view(path: dict, lang: str) -> dict | None:
    """The path's origin + reason for existing (CAND-06), read from the SAME provenance the evaluator
    sees. Two things that must not vanish even though the path stands via the independently anchored
    branch:

      `unsettled`       disputed causal mechanisms (evidence FOR and AGAINST). Not the reason this path
                        exists (`why` only names the anchored-active ones), but never hidden either.
      `assumes_absence` the rule support leans on an absence condition (no record denying it) —
                        absence of record, not verified absence."""
    cand = (path.get("provenance") or {}).get("candidate")
    if not cand:
        return None
    names = {m["mechanism_id"]: m.get("title") for m in cand.get("mechanisms") or []}
    unsettled, seen = [], set()
    for c in cand.get("conflicts") or []:
        mid = c.get("mechanism_id")
        if mid and mid not in seen:
            seen.add(mid)
            unsettled.append({"mechanism_id": mid, "name": names.get(mid) or _name_of(mid)})
    return {
        "candidate_id": cand["candidate_id"],
        "origin": cand.get("origin"),
        "mechanism_ids": list(cand.get("mechanism_ids") or []),
        "knowledge_ids": list(cand.get("knowledge_ids") or []),
        "evidence_ids": list(cand.get("evidence_ids") or []),
        "why": _because(cand, path.get("presentation"), lang),
        "unsettled": unsettled,
        "assumes_absence": bool(cand.get("assumed_absences")),
    }


def _name_of(identifier: str) -> str:
    """'mechanism:lead_leakage' -> 'Lead leakage' (words from the id, nothing invented)."""
    return humanize_id(identifier.partition(":")[2] or identifier)


def _because(cand: dict, presentation: dict | None, lang: str) -> dict[str, str]:
    """ "Why does this possibility exist?" — curated domain text when available
    (`presentation[lang].because`); otherwise a deterministic fallback from the genuinely anchored
    mechanisms. No text is invented.

    Curated text is a CLAIM about the user's situation, so it is used only when it cannot misdescribe an
    unanchored mechanism (disputed, not yet detected, contradicted):
      - `because` as text = a claim about the pattern thesis: used when the pattern has only ONE causal
        mechanism, or ALL of its causal mechanisms are active;
      - `because` as {mechanism_id: text}: sentences owned by ACTIVE mechanisms only, joined.
    Otherwise: a fallback from the active mechanisms (deterministic)."""
    curated = ((presentation or {}).get(lang) or {}).get("because")
    mechs = cand.get("mechanisms") or []
    active = [m for m in mechs if m.get("status") == "ACTIVE"]
    if isinstance(curated, dict):
        texts = [curated.get(m["mechanism_id"]) for m in active]
        if active and all(texts):
            return {"text": " ".join(texts), "lang": lang, "source": "curated"}
    elif curated and (len(mechs) <= 1 or len(active) == len(mechs)):
        return {"text": curated, "lang": lang, "source": "curated"}
    names = [m.get("title") or _name_of(m["mechanism_id"]) for m in active]
    names = [n for n in names if n] or [_name_of(m) for m in cand.get("mechanism_ids") or []]
    text = "What you shared points to: " + ", ".join(n[:1].lower() + n[1:] for n in names) + "."
    return {"text": text, "lang": "en", "source": "fallback"}


_EMERGING_STATE = {"CONFLICT": "CONFLICT", "PARTIAL": "UNKNOWN", "UNSUPPORTED": "UNSUPPORTED"}


def _emerging(path_set: dict | None, lang: str) -> list[dict]:
    """NEWLY EMERGING possibilities: a real signal exists but it has not settled (not a Possible Path).
    Read from the same PathSet generation audit (not raw LLM output); not requirement items."""
    out: list[dict] = []
    for row in ((path_set or {}).get("generation") or {}).get("possibilities") or []:
        if not row.get("emerging") or row.get("disposition") not in ("UNRESOLVED", "CONFLICTED"):
            continue
        pres = (row.get("presentation") or {}).get(lang) or {}
        title = pres.get("short") or pres.get("word")
        need = []
        for d in row.get("missing_detail") or []:
            # only STATE facts the user can fulfil; mechanisms/rules are knowledge conclusions, not
            # something that can be "completed" — never offered as a need
            if not str(d.get("signal", "")).startswith("state:"):
                continue
            txt = ((d.get("i18n") or {}).get(lang) or {}).get("reason")
            need.append(
                {"text": txt, "lang": lang}
                if txt
                else {"text": _name_of(d["signal"]), "lang": "en", "source": "fallback"}
            )
        out.append(
            {
                "key": row["candidate_id"],
                "candidate_id": row["candidate_id"],
                "direction": row["direction"],
                "title": {"text": title, "lang": lang} if title else {"text": row["title"], "lang": "id"},
                "state": _EMERGING_STATE[row["emerging"]],
                "mechanism_ids": list(row.get("mechanism_ids") or []),
                "need": need,
                "conflicts": [c.get("mechanism_id") for c in row.get("conflicts") or []],
            }
        )
    return out


def projection_path_keys(projection: dict) -> list[str]:
    """Engine-versioned path keys, in order — identities the LLM/UI must never replace."""
    return [str(p.get("key") or "") for p in (projection or {}).get("paths") or []]


def readiness_basis(projection: dict) -> str:
    """Hash of the projection's semantic state (not a timestamp): keys, status, each item's state.

    Readiness changes (route changed, new check, status shifted) invalidate the explanation cache; the
    execution report ("already done") is deliberately excluded — that is not a state change (INV-R8)."""
    rows = []
    for p in (projection or {}).get("paths") or []:
        rows.append(
            [
                p.get("key"),
                p.get("status"),
                p.get("lifecycle"),
                p.get("feasibility"),
                [
                    [it.get("key"), it.get("state"), it.get("soft"), it.get("settled", True)]
                    for it in p.get("items") or []
                ],
            ]
        )
    return hashlib.sha1(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()[:12]
