"""Plain-language explainer for the Diagnosis screen (revenue domain).

One LLM call (+ at most one repair) that rewrites the diagnosis artifact in the user's own words.
Guarded by `domains/revenue/guards/plain_language.py`: violating fields are dropped, never silently
repaired. Cached per session (Session.explain), keyed to the artifact AND the readiness projection
via `basis` so it never goes stale.

The readiness narrative is grounded in the engine-adjudicated projection (core/navigation/readiness.py):
the LLM reads the SAME checklist as the UI, path keys/item keys are reconciled against the engine
keys, and the claim-level grounding contract (core/navigation/claims.py + guards/readiness_grounding.py)
rejects narration that invents state — with no fact-checker LLM. The path count is set by the engine
(0..N).
"""
from __future__ import annotations

import hashlib
import json
import time

from core.llm import schema_hint
from core.navigation.narrative import candidate_line, emerging_lines
from domains.revenue.guards.goal_consistency import (
    GOAL_CODES,
    check_explain_goal,
    codes_of,
    fallback_value,
    goal_facts_of,
)
from domains.revenue.guards.plain_language import check_explain, numbers_in
from domains.revenue.guards.readiness_grounding import (
    check_check_entries,
    check_grounding,
    grounding_note,
)
from domains.revenue.projection.readiness import (
    build_readiness_projection,
    projection_path_keys,
    readiness_basis,
)
from domains.revenue.prompts.diagnosis_user import goal_context_block
from domains.revenue.prompts.explain_system import SYSTEM, build_user_prompt
from domains.revenue.schema.explain import PlainExplain

# 8 (18 Oct 2026): example-fragment prompt replaced with full EN + the `check_language` guard
# (an EN-session narrative containing ID prose = field dropped; opening-path incident on the
# Readiness screen).
VERSION = 8
USER_TURNS = 8
USER_TURN_CHARS = 520
FACTS_CAP = 30
# Prompt budget, NOT an engine limit: the engine forms 0..N paths. Paths above this cap are not read
# out to the LLM, and the LLM is told that some were left unread (`_paths_read`) — it must never state
# a path count.
PATHS_CAP = 10
CHECKS_CAP = 36


def _clip(t: str, n: int) -> str:
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "..."


def basis_of(s, projection: dict | None = None, goal_ctx: dict | None = None) -> str:
    """Cache basis for the explain: diagnosis content + readiness projection state (semantic, not time).

    Readiness changes (route changes, new gates, shifted statuses) invalidate a stale explain;
    execution reports ("already worked on") do not, because they are not a state change."""
    d = s.diagnosis
    if not d:
        return ""
    g = s.goal or {}
    parts = [d.primary_constraint, d.where_you_are, d.do_not, d.next_best_action, d.success_metric,
             readiness_basis(projection if projection is not None else build_readiness_projection(d)),
             # the narrative depends on the Goal (target/version) and its measured value:
             # changed = stale explain
             [g.get("goal_id"), g.get("target"), g.get("version"), (goal_ctx or {}).get("measured_current")]]
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:12]


def _user_words(s) -> str:
    turns = [t for r, t in s.transcript if r == "user"]
    if len(turns) > USER_TURNS:
        turns = turns[:1] + turns[-(USER_TURNS - 1):]
    return "\n".join(f"- {_clip(t, USER_TURN_CHARS)}" for t in turns) or f"- {_clip(s.goal_text, 400)}"


def _facts(s) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for e in s.evidence:
        key = e.signal.strip().lower()
        if getattr(e, "is_gap", False) or key in seen:
            continue
        seen.add(key)
        lines.append(f"- {e.signal}")
        if len(lines) >= FACTS_CAP:
            break
    return "\n".join(lines) or "- (none)"


def _numbers(s) -> tuple[str, list[float]]:
    rs = s.diagnosis.revenue_state if isinstance(s.diagnosis.revenue_state, dict) else {}
    goal = s.goal or {}
    mid = goal.get("metric_id") or ("revenue_monthly" if goal.get("metric") == "revenue_monthly" else "")
    # A-02/TALK grounding: NON-revenue Goal values are never narrated as rupiah —
    # the pack carries the metric's own measure (unit follows the registry), not a revenue slot.
    non_revenue = bool(mid) and mid != "revenue_monthly"
    if non_revenue:
        mname = mid.replace("_", " ")
        cur = goal.get("current")
        tgt = goal.get("target")
        window = goal.get("measurement_window_days")
        days = goal.get("deadline_days")
        rows = []
        pct = (lambda v: f" (that is {v * 100:g} percent)") if goal.get("unit") == "ratio" else (lambda v: "")
        if cur is not None:
            rows.append(f"{mname} now: {cur:g}{pct(cur)} (the goal's own measure, not rupiah)")
        if tgt is not None:
            rows.append(f"goal ({mname}): {tgt:g}{pct(tgt)}" + (f" within {window} days" if window else ""))
        if days:
            rows.append(f"time frame: {days} days")
        derived = [v for v in (cur, tgt, days) if v is not None]
        return "\n".join(f"- {r}" for r in rows) or "- (none)", derived
    cur = rs.get("current_monthly")
    tgt = rs.get("target_monthly") or goal.get("target")
    gap = rs.get("gap_monthly")
    days = goal.get("deadline_days")
    rows = []
    if cur is not None:
        rows.append(f"income now: {cur:g} million rupiah a month")
    if tgt is not None:
        rows.append(f"goal: {tgt:g} million rupiah a month")
    if gap is not None:
        rows.append(f"still to go: {gap:g} million rupiah a month")
    if days:
        rows.append(f"time frame: {days} days")
    derived = [v for v in (cur, tgt, gap, days) if v is not None]
    if cur is not None and tgt is not None:
        derived.append(max(tgt - cur, 0))
    return "\n".join(f"- {r}" for r in rows) or "- (none)", derived


def relations_of(s) -> dict[str, str]:
    """{path_id: goal_relation} from the artifact's path set - the universal readiness
    projection does not carry it."""
    pp = getattr(s.diagnosis, "possible_paths", None) or {}
    rows = pp.get("paths") if isinstance(pp, dict) else None
    return {str(p.get("path_id")): str(p.get("goal_relation") or "")
            for p in (rows or []) if isinstance(p, dict) and p.get("path_id")}


def goal_facts_for(s, goal_ctx: dict | None = None):
    """The authoritative GoalFacts for this session: the session's structured Goal + revenue state +
    path relations. `goal_ctx` (optional, from the workspace)
    = {other_goals, history, measured_current, achieved}."""
    ctx = goal_ctx or {}
    rs = getattr(s.diagnosis, "revenue_state", None)
    rs = rs.model_dump() if hasattr(rs, "model_dump") else (rs if isinstance(rs, dict) else {})
    return goal_facts_of(
        s.goal or {}, revenue_state=rs, relations=relations_of(s).values(),
        other_goals=ctx.get("other_goals") or (), history=ctx.get("history") or (),
        measured_current=ctx.get("measured_current"), achieved=bool(ctx.get("achieved")))


def _goal_block(s, facts) -> str:
    """The structured Goal block (authority) for the pack: the narrative MUST serve this goal; the
    current value is stated as measured or NOT measured (missing != zero); UNKNOWN path relations are
    stated so they are never turned into claims."""
    block = goal_context_block(s.goal)
    if not block:
        return ""
    if facts.current is None:
        cur_txt = "NOT MEASURED (unknown, not zero)"
    elif facts.ratio:   # a share is told as a percent too, so the narrative never shows a raw 0.3
        cur_txt = f"{facts.current:g} (that is {facts.current * 100:g} percent)"
    else:
        cur_txt = f"{facts.current:g}"
    rows = ["current measured value: " + cur_txt]
    if facts.unknown_relation:
        rows.append("link of the map's paths to this goal: NOT SHOWN YET (hypotheses; never say a path or "
                    "move will reach or move this goal)")
    return block + "".join(f"- {r}\n" for r in rows)


def _engine_read(d) -> str:
    dn = d.do_not_detail or {}
    hold = f"{_clip(dn.get('text') or d.do_not, 500)} | reason: {_clip(dn.get('reason', ''), 500)}"
    fine_when = _clip(dn.get("unlock_condition") or dn.get("until", ""), 300)
    return "\n".join([
        f"verdict: {(d.decision_spectrum or {}).get('level', '')}; confidence: {d.confidence_band}",
        f"category label (from a fixed list, may be generic or not fit): {d.primary_constraint}",
        f"where_you_are: {_clip(d.where_you_are, 1400)}",
        f"why: {_clip(' '.join(d.why), 1200)}",
        f"hold off (technical): {hold} | fine again when: {fine_when}",
        f"first step today: {_clip(d.first_step_today, 500)}",
        f"7-day plan: {_clip(d.next_best_action, 900)}",
        f"success measure: {_clip(d.success_metric, 600)}",
        f"how we will know: {_clip(d.well_know_when, 700)}",
        f"re-check window: {d.reassess_window_days} days",
    ])


_STATE_WORD = {
    "PRESENT": "confirmed",
    "ABSENT": "still to get",
    "PARTIAL": "partly there",
    "UNKNOWN": "not checked yet",
}


def _item_line(it: dict, indent: str = "    ") -> str:
    """One projection item for the LLM: the exact key (to be repeated), the title, its final state."""
    reason = (it.get("reason") or {}).get("text")
    unlock = (it.get("unlock") or {}).get("text")
    extra = "".join(
        [
            f"; {_clip(reason, 180)}" if reason else "",
            f"; opens when: {_clip(unlock, 180)}" if unlock else "",
        ]
    )
    title = (it.get("title") or {}).get("text") or it.get("key")
    word = _STATE_WORD.get(it.get("state"), it.get("state"))
    if not it.get("settled", True):
        word = "CONFLICT: two readings of the evidence disagree, not settled"
    return f'{indent}item {it.get("key")} ("{title}"): {word}{extra}'


def _paths_read(projection: dict, relations: dict[str, str] | None = None) -> str:
    """Path read for the LLM, from the adjudicated projection (not the raw route).

    One state, once: duplicate check vs requirement entries are merged in the projection, so the
    Readiness narrative is grounded in the same checklist shown in the UI. Paths can be 0: the engine's
    reason is read out verbatim."""
    paths = (projection or {}).get("paths") or []
    if ((projection or {}).get("navigation") or {}).get("status") == "LEGACY":
        return (
            "- (this map was made before the current path model; NO path result exists for it. Do not say "
            "there are no paths and do not describe any path. Say the map needs a fresh check-in.)"
        )
    possibilities = emerging_lines(projection)
    if not paths:
        why = "; ".join(
            f"{u.get('code')}: {_clip(u.get('detail'), 160)}"
            for u in (projection or {}).get("unresolved") or []
        )
        return "\n".join([f"- (no path was formed. engine reason: {why or 'not stated'})"] + possibilities)
    lines: list[str] = []
    for p in paths[:PATHS_CAP]:
        lines.append(
            f"- path {p.get('key')}: status {p.get('status')}; "
            f"what it is about: {_clip(p.get('title', ''), 60)} — "
            f"{_clip((p.get('basis') or {}).get('text'), 160)}"
        )
        if (relations or {}).get(p.get("key")) == "UNKNOWN_RELATION":
            lines.append("  link to your goal: not shown yet (a hypothesis to test, never a promise)")
        if candidate_line(p):
            lines.append(candidate_line(p))
        for it in (p.get("items") or [])[:CHECKS_CAP]:
            lines.append(_item_line(it))
    if len(paths) > PATHS_CAP:
        lines.append(
            f"- ({len(paths) - PATHS_CAP} more paths exist that are NOT described here. Do not say how many "
            "paths there are, do not say these are all of them, and do not describe or compare the others.)"
        )
    return "\n".join(lines + possibilities)


def _checks_read(projection: dict) -> str:
    """Readiness check read (screen 18): projection items per path, with their final state.

    Keys = exact engine requirement ids or check ids — the UI uses the same keys."""
    rows: list[tuple[str, str]] = []  # (key, one context line)
    seen: set[str] = set()
    for p in (projection or {}).get("paths") or []:
        for it in p.get("items") or []:
            k = str(it.get("key") or "")
            if not k or k in seen:
                continue
            seen.add(k)
            g = it.get("guidance") or {}
            rows.append(
                (
                    k,
                    f"state {_STATE_WORD.get(it.get('state'), it.get('state'))}; to get or check it, "
                    f"the engine suggests: {_clip(g.get('text'), 200)}",
                )
            )
    if not rows:
        return "- (none)"
    return "\n".join(f"- key {k}: {line}" for k, line in rows[:CHECKS_CAP])


def build_pack(s, route_data: dict | None = None,
               projection: dict | None = None, goal_ctx: dict | None = None) -> tuple[str, set[str]]:
    """(context text for the LLM, the set of numbers allowed in the output).

    `projection` = the adjudicated readiness projection; when not given, built from
    diagnosis + route_data. This is the SAME read the UI uses."""
    projection = projection if projection is not None else build_readiness_projection(s.diagnosis, route_data)
    numbers, derived = _numbers(s)
    gblock = _goal_block(s, goal_facts_for(s, goal_ctx))
    pack = (
        f"GOAL AS THE USER WROTE IT: {_clip(s.goal_text, 400)}\n\n"
        f"USER WORDS (their own messages):\n{_user_words(s)}\n\n"
        f"FACTS (from what they said):\n{_facts(s)}\n\n"
        f"NUMBERS:\n{numbers}\n"
        f"{gblock}\n"
        "ENGINE READ (technical; translate the meaning, never copy the wording):\n"
        f"{_engine_read(s.diagnosis)}\n\n"
        "PATHS READ (the paths of the map, as many as the engine formed, possibly none, with the\n"
        "adjudicated checks behind each status; translate the meaning, never copy the wording):\n"
        f"{_paths_read(projection, relations_of(s))}\n\n"
        "CHECKS READ (the readiness checklist for this user; key is the exact key your\n"
        "answer must repeat and the exact key every claim must anchor on; engine text is\n"
        "technical, translate the meaning):\n"
        f"{_checks_read(projection)}\n\n"
        f"{grounding_note()}"
    )
    pool = numbers_in(pack)
    for v in derived:
        pool |= numbers_in(f"{v:g}")
    return pack, pool


def _repair_note(bad: dict[str, list[str]]) -> str:
    lines = "\n".join(f"- {f}: {'; '.join(v)}" for f, v in bad.items())
    return (
        "\nYour previous answer broke these rules. Rewrite ONLY those fields so they follow the rules, "
        f"keep the other fields as they were, and return the full JSON again:\n{lines}\n"
    )


def _violations(
    dump: dict, pool: set[str], projection: dict, facts=None, lang: str = "en"
) -> dict[str, list[str]]:
    """Language guard + grounding contract + unknown keys + GOAL CONSISTENCY, in one map.

    Goal violations carry a code prefix ("FOREIGN_TARGET: ...") so the caller can tell them apart from
    language violations when deciding repair/fallback."""
    bad = dict(check_explain(dump, pool, lang))
    for key, v in check_grounding(dump.get("paths") or [], projection).items():
        bad[key] = (bad.get(key) or []) + v
    for key, v in check_check_entries(dump.get("checks") or [], projection).items():
        bad[key] = (bad.get(key) or []) + v
    engine = set(projection_path_keys(projection))
    for p in dump.get("paths") or []:
        k = str(p.get("key") or "")
        if not k or k not in engine:
            bad[f"paths:{k or '?'}"] = (bad.get(f"paths:{k or '?'}") or []) + [
                "unknown path key: repeat only the path keys given in PATHS READ"]
    if facts is not None:
        for key, v in check_explain_goal(dump, facts).items():
            bad[key] = (bad.get(key) or []) + v
    return bad


def _is_goal_violation(msg: str) -> bool:
    return msg.split(":", 1)[0] in GOAL_CODES


def _reconcile(items: list[dict], engine_keys: list[str], dropped: list[str], prefix: str) -> list[dict]:
    """LLM output keys are reconciled against engine keys: foreign keys are dropped,
    duplicates keep the first, final order = engine order."""
    allowed = [k for k in engine_keys if k]
    first: dict[str, dict] = {}
    order: list[str] = []
    for it in items:
        k = str((it or {}).get("key") or "")
        if k not in allowed:
            dropped.append(f"{prefix}:{k or '?'}:unknown-key")
            continue
        if k in first:
            dropped.append(f"{prefix}:{k}:duplicate")
            continue
        first[k] = it
        order.append(k)
    return [first[k] for k in allowed if k in first]


def explain_session(llm, s, route_data: dict | None = None, projection: dict | None = None,
                    max_repairs: int = 1, goal_ctx: dict | None = None) -> dict:
    """Build the explanation; violating fields are dropped (the UI falls back to artifact text there).

    Violating path/check items are dropped ONE BY ONE ("paths:KEY" / "checks:KEY"); other items and
    other blocks stay in use. Path/check keys are reconciled against engine keys, and grounding drops
    items whose narration invents state beyond the projection. `projection` = the adjudicated readiness
    projection (optional; without it, built from diagnosis + route_data).

    GOAL CONSISTENCY (round 4): the narrative is checked against the session's structured Goal
    (`goal_consistency`). Violations go back to the provider ONCE (retry cap = max_repairs, no loop).
    If still violating, top-level fields are replaced with deterministic sentences from the structured
    Goal + state (not answers known to be wrong) and path/check items are dropped (the UI falls back to
    engine sentences). The `guard` diagnostic records violation CODES + actions - without narrative text."""
    projection = projection if projection is not None else build_readiness_projection(s.diagnosis, route_data)
    facts = goal_facts_for(s, goal_ctx)
    pack, pool = build_pack(s, route_data, projection, goal_ctx)
    hint = schema_hint(PlainExplain)
    lang = str(getattr(s, "language", "en") or "en")
    try:
        dump = llm.structured_call(PlainExplain, SYSTEM, build_user_prompt(pack, hint)).model_dump()
    except ValueError:
        # provider output failed the schema (broken JSON / missing required field) even after the
        # provider's own retries: do not 500 and do not show anything from that output - return the
        # deterministic explanation from the structured Goal + state. Limit/auth errors (not ValueError)
        # still propagate to the endpoint.
        return _deterministic_explain(s, projection, facts, "SCHEMA_INVALID", goal_ctx)
    bad = _violations(dump, pool, projection, facts, lang)
    initial_goal_codes = codes_of({k: [m for m in v if _is_goal_violation(m)] for k, v in bad.items()})
    retried = False
    for _ in range(max_repairs):
        if not bad:
            break
        try:
            note = _repair_note(bad)
            retry = llm.structured_call(
                PlainExplain, SYSTEM, build_user_prompt(pack, hint, note)).model_dump()
        except Exception:
            break
        retried = True
        bad_retry = _violations(retry, pool, projection, facts, lang)
        if len(bad_retry) <= len(bad):
            dump, bad = retry, bad_retry
    out = dump
    dropped: list[str] = []
    goal_fallback: list[str] = []
    for f, msgs in bad.items():
        if f.startswith("paths:") or f.startswith("checks:"):
            dropped.append(f)
        elif any(_is_goal_violation(m) for m in msgs):
            # never show an answer known to contradict the Goal: replace with Goal facts
            out[f] = fallback_value(f, facts) or ([] if isinstance(out.get(f), list) else "")
            goal_fallback.append(f)
        else:
            out[f] = [] if isinstance(out.get(f), list) else ""
            dropped.append(f)
    out["paths"] = [p for p in (out.get("paths") or []) if f"paths:{p.get('key') or '?'}" not in bad]
    out["checks"] = [c for c in (out.get("checks") or []) if f"checks:{c.get('key') or '?'}" not in bad]
    out["paths"] = _reconcile(out["paths"], projection_path_keys(projection), dropped, "paths")
    out["checks"] = _reconcile(out["checks"], projection_check_keys(projection), dropped, "checks")
    final_goal_codes = codes_of({k: [m for m in v if _is_goal_violation(m)] for k, v in bad.items()})
    out.update({
        "version": VERSION, "basis": basis_of(s, projection, goal_ctx), "generated_ts": int(time.time()),
        "model": getattr(llm, "model", "") or getattr(llm, "name", ""), "dropped": sorted(set(dropped)),
        "guard": {"goal": {
            "checked": bool(facts.metric_id), "metric_id": facts.metric_id,
            "violations_first_pass": initial_goal_codes, "retried": retried,
            "violations_after_repair": final_goal_codes,
            "repaired": bool(initial_goal_codes) and not final_goal_codes,
            "fallback_fields": sorted(goal_fallback)}},
    })
    return out


def _deterministic_explain(s, projection: dict, facts, reason: str, goal_ctx: dict | None = None) -> dict:
    """Full explanation from facts (structured Goal + state), no provider. Empty path/check items:
    the UI uses engine sentences for those."""
    out = {f: fallback_value(f, facts) for f in (
        "summary", "blocking_title", "blocking_body", "do_title", "do_why", "done_when", "hold_title",
        "hold_body", "why")}
    if not facts.metric_id:   # legacy session without a structured Goal: only the user's own words
        wrote = f"Your goal as you wrote it: {_clip(s.goal_text, 200)}"
        out.update({"summary": [wrote], "why": [wrote, "Nothing about it is measured yet."],
                    "do_title": "Write down where things stand today."})
    out.update({"paths": [], "checks": [], "version": VERSION, "basis": basis_of(s, projection, goal_ctx),
                "generated_ts": int(time.time()), "model": "deterministic-fallback", "dropped": [],
                "guard": {"goal": {"checked": bool(facts.metric_id), "metric_id": facts.metric_id,
                                   "violations_first_pass": [reason], "retried": False,
                                   "violations_after_repair": [], "repaired": False,
                                   "fallback_fields": ["*"]}}})
    return out


def projection_check_keys(projection: dict) -> list[str]:
    """Engine-version check keys, in order, no duplicates (path order then item order)."""
    keys: list[str] = []
    for p in (projection or {}).get("paths") or []:
        for it in p.get("items") or []:
            k = str(it.get("key") or "")
            if k and k not in keys:
                keys.append(k)
    return keys
