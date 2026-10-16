"""Question Planner input assembler — PathSet + route + Applicable Set + Requirement State -> JSON dict.

internal-docs §25. `plan_next_move` is a pure function over the dict assembled here;
everything the planner (and the text renderer) reads lives in that dict, so decisions can be REPLAYED
from the same input:

    input state -> applicable set -> requirement state -> open needs -> reasons -> next move

This module only ASSEMBLES. It does not judge, choose, or invent facts: every value comes from an
artifact already decided by another layer (PathSet = evaluator, route = composer, ARS = applicability,
view = reader). Domain-dependent things arrive via injectors, never encoded here:

  `describe`         requirement_id -> presentation (registry + presentation, not a second dictionary)
  `signal_of`        (strategy_id, check_id) -> check signal id (the PathSet does not store check signal ids)
  `resolvable`       signal id -> "ASK" | "ACT" (can the conversation move that signal?)
  `signal_text`      signal id -> {language: "not yet known" reason sentence}

This module is GENERIC: no I/O, no store, no LLM."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from core.navigation.applicability import ApplicableRequirementSet, owner_path_id
from core.navigation.compat import NAV_CURRENT, assess_path_set
from core.navigation.contracts import SIGNAL_STATE, signal_namespace
from core.navigation.planner import ACT, ASK, PLANNER_VERSION, POLICY
from core.navigation.requirement_state import RequirementView

Describe = Callable[[str], Mapping[str, Mapping[str, str]]]

_ROUTE_APPLICABILITY = {"APPLIES": "APPLIES", "NOT_APPLICABLE": "NOT_APPLICABLE", "UNDETERMINED": "UNKNOWN"}
_GOAL_CODES = ("GOAL_NOT_ESTABLISHED", "GOAL_ABSENT")


def _i18n_text(i18n: Mapping[str, Any] | None, field: str, machine: str, lang: str) -> dict[str, str]:
    """Per-language text FROM DATA: the requested language when present; otherwise machine text (`id`)
    with a marker."""
    v = ((i18n or {}).get(lang) or {}).get(field)
    return {"text": v, "lang": lang} if v else {"text": machine or "", "lang": "id"}


def _goal(path_set: Mapping[str, Any], lang: str) -> dict[str, Any]:
    for u in path_set.get("unresolved") or []:
        if u.get("code") in _GOAL_CODES:
            return {
                "established": False,
                "code": u["code"],
                "signal": u.get("signal"),
                "text": _i18n_text(u.get("i18n"), "detail", u.get("detail", ""), lang),
            }
    return {"established": True, "code": None, "signal": None, "text": {"text": "", "lang": lang}}


def _facts_missing(path_set: Mapping[str, Any], lang: str) -> list[dict[str, Any]]:
    """Missing STATE facts (`state:`) that would let a path/candidate be born. Only `state:` signals:
    mechanisms and rules are knowledge conclusions, not something the user can answer."""
    rank = {"emerging": 0, "undetermined": 1, "unresolved": 2}
    acc: dict[str, dict[str, Any]] = {}

    def add(detail: Mapping[str, Any], needed_by: str, source: str) -> None:
        sid = detail.get("signal")
        if not sid or signal_namespace(sid) != SIGNAL_STATE:
            return
        row = acc.setdefault(
            sid,
            {"signal": sid, "text": _i18n_text(detail.get("i18n"), "reason", detail.get("reason", ""), lang),
             "needed_by": [], "source": source},
        )
        if needed_by and needed_by not in row["needed_by"]:
            row["needed_by"].append(needed_by)
        if rank[source] < rank[row["source"]]:
            row["source"] = source

    gen = path_set.get("generation") or {}
    for u in path_set.get("unresolved") or []:
        for d in u.get("missing_detail") or []:
            add(d, "", "unresolved")
    for u in gen.get("undetermined") or []:
        for d in u.get("missing_detail") or []:
            add(d, str(u.get("candidate_id") or u.get("strategy_id")), "undetermined")
    for row in gen.get("possibilities") or []:
        if row.get("emerging") and row.get("disposition") in ("UNRESOLVED", "CONFLICTED"):
            for d in row.get("missing_detail") or []:
                add(d, str(row["candidate_id"]), "emerging")
    for r in acc.values():
        r["needed_by"] = sorted(r["needed_by"])
    return [acc[k] for k in sorted(acc)]


def assemble_planner_input(
    *,
    lang: str,
    turn: int,
    path_set: Mapping[str, Any] | None,
    route_data: Mapping[str, Any] | None,
    applicable: ApplicableRequirementSet,
    views: Mapping[str, RequirementView],
    describe: Describe,
    signal_of: Callable[[str, str], str | None] | None = None,
    resolvable: Callable[[str], str] | None = None,
    signal_text: Callable[[str], Mapping[str, str]] | None = None,
    asked: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Assemble the PlannerInput (a JSON-safe dict). All display text comes from data/injection; nothing
    is invented."""
    usable = assess_path_set(path_set)["status"] == NAV_CURRENT
    ps: Mapping[str, Any] = path_set if (usable and path_set) else {}
    paths_raw: Sequence[Mapping[str, Any]] = ps.get("paths") or []
    by_pid = {p["path_id"]: p for p in paths_raw}
    resolve = resolvable or (lambda _sid: ASK)
    sig_text = signal_text or (lambda _sid: {})
    texts: dict[str, dict[str, Any]] = {}
    signals: dict[str, str] = {}

    def note_signal(sid: str | None) -> None:
        if sid:
            signals[sid] = resolve(sid)

    goal = _goal(ps, lang)
    if not goal["established"]:
        texts["goal"] = {"reason": goal["text"]}
    facts = _facts_missing(ps, lang)
    for f in facts:
        note_signal(f["signal"])
        texts[f"signal:{f['signal']}"] = {"reason": f["text"]}

    paths: list[dict[str, Any]] = []
    for p in paths_raw:
        pid = p["path_id"]
        pres = (p.get("presentation") or {}).get(lang) or {}
        short = pres.get("short")
        title = {"text": short or p.get("title") or pid, "lang": lang if short else "id"}
        texts[f"path:{pid}"] = {"title": title}
        checks = []
        for c in p.get("checks") or []:
            sid = signal_of(p["strategy_id"], c["check_id"]) if signal_of else None
            note_signal(sid)
            checks.append(
                {
                    "check_id": c["check_id"],
                    "signal": sid,
                    "kind": c.get("kind"),
                    "requirement_id": c.get("requirement_id"),
                    "state": c.get("state"),
                }
            )
            if not c.get("requirement_id"):
                i18n = c.get("i18n")
                texts[f"check:{pid}:{c['check_id']}"] = {
                    "title": _i18n_text(i18n, "title", c.get("title", ""), lang),
                    "reason": _i18n_text(i18n, "reason", c.get("reason", ""), lang),
                    "how": _i18n_text(i18n, "unlock", c.get("unlock", ""), lang),
                }
        missing_app = []
        for m in p.get("missing_evidence") or []:
            cid = str(m.get("check_id") or "")
            if cid.startswith("applicability:"):
                sid = cid.partition(":")[2]
                note_signal(sid)
                st = sig_text(sid)
                missing_app.append({"signal": sid})
                if st.get(lang):
                    reason = {"text": st[lang], "lang": lang}
                else:
                    reason = {"text": st.get("id", ""), "lang": "id"}
                texts.setdefault(f"applicability:{pid}", {})["reason"] = reason
        paths.append(
            {
                "path_id": pid,
                "strategy_id": p["strategy_id"],
                "status": p.get("status"),
                "applicability": p.get("applicability"),
                "navigable": p.get("status") != "STOP",
                "route_available": bool((p.get("route_substrate") or {}).get("available")),
                "checks": checks,
                "missing_applicability": missing_app,
            }
        )

    routes: list[dict[str, Any]] = []
    for r in (route_data or {}).get("routes") or []:
        owner = owner_path_id(r, by_pid)
        nodes = []
        for n in r.get("nodes") or []:
            resolves = n.get("resolves") or []
            nodes.append(
                {
                    "node_id": n.get("node_id"),
                    "requirement_id": resolves[0] if resolves else None,
                    "strength": n.get("strength"),
                    "depends_on": list(n.get("depends_on") or []),
                    "state": str(((n.get("satisfaction") or {}).get("status")) or "UNKNOWN").upper(),
                    "executability": n.get("executability"),
                    "execution_view": n.get("execution_view"),
                    "activity": str(n.get("activity") or ""),
                }
            )
        path_ok = bool(owner and by_pid[owner].get("status") != "STOP")
        navigable = path_ok and r.get("lineage_status") == "OPEN"
        route_app = (r.get("applicability") or {}).get("status")
        routes.append(
            {
                "route_id": r.get("route_id"),
                "path_id": owner,
                "applicability": _ROUTE_APPLICABILITY.get(route_app, "UNKNOWN"),
                "navigable": navigable,
                "nodes": nodes,
            }
        )
        path_title = (texts.get(f"path:{owner}") or {}).get("title") if owner else None
        texts[f"route:{r.get('route_id')}"] = {
            "title": path_title or {"text": str(r.get("strategy") or r.get("path_title") or ""), "lang": "id"}
        }
        for n in r.get("nodes") or []:
            resolves = n.get("resolves") or []
            if resolves:
                # first step: curated verification when available (in the user's language); otherwise the
                # node activity (user's language when the template provides it, docs/03 §7)
                d = describe(resolves[0])["verification"]
                en_act = ((n.get("i18n") or {}).get(lang) or {}).get("activity")
                machine = {
                    "text": str(en_act or n.get("activity") or ""),
                    "lang": lang if en_act else "id",
                }
                curated = d.get("source") == "curated"
                texts[f"node:{n.get('node_id')}"] = {"how": dict(d) if curated else machine}

    requirements: dict[str, dict[str, Any]] = {}
    for rid, v in views.items():
        requirements[rid] = v.to_dict()
        d = describe(rid)
        texts[f"requirement:{rid}"] = {"title": dict(d["title"]), "how": dict(d["verification"])}
        texts[f"contradiction:{rid}"] = {"title": dict(d["title"])}

    return {
        "version": PLANNER_VERSION,
        "policy": POLICY,
        "lang": lang,
        "goal": goal,
        "paths": paths,
        "routes": routes,
        "unresolved": [{"code": u.get("code")} for u in ps.get("unresolved") or []],
        "facts_missing": facts,
        "applicable": applicable.to_dict(),
        "requirements": requirements,
        "signals": dict(sorted(signals.items())),
        "next_move_v1": (dict(route_data["next_move"]) if (route_data or {}).get("next_move") else None),
        "texts": texts,
        "history": {"asked": dict(sorted((asked or {}).items())), "turn": turn},
    }


__all__ = ["assemble_planner_input", "ACT", "ASK"]
