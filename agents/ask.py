"""Follow-up discussion over the analysis result (Ask screen; revenue domain).

One LLM call (+ at most one repair). Grounded in the Diagnosis explain context pack (the user's words,
facts, numbers, the engine read) plus what each path requires (gate feasibility). Guarded by
`guards/plain_language.py`: an answer that still violates after one repair is DROPPED and replaced with
an honest sentence, never silently repaired. Does not change the diagnosis: updates go through a
follow-up cycle (POST /session with prior_session_id).
"""

from __future__ import annotations

import time

from agents.explain import GOAL_CODES, _clip, build_pack, goal_facts_for
from core.llm import schema_hint
from core.navigation.narrative import candidate_line, emerging_lines
from domains.revenue.guards.goal_consistency import (
    check_answer_goal,
    codes_of,
    goal_line,
    measurement_line,
)
from domains.revenue.guards.plain_language import (
    ANSWER_LIMIT,
    BANNED,
    check_language,
    check_text,
    numbers_in,
)
from domains.revenue.projection.readiness import build_readiness_projection
from domains.revenue.prompts.ask_system import SYSTEM, build_user_prompt
from domains.revenue.schema.ask import AskReply

QUESTION_CHARS = 600
HISTORY_TURNS = 6
HISTORY_CHARS = 420
FOLLOW_UP_LIMIT = 90
FALLBACK = {
    "en": (
        "I could not put that plainly enough. Try asking it another way, "
        "or open Diagnosis for the short version."
    ),
    "id": (
        "Saya belum bisa menjawabnya dengan bahasa yang cukup sederhana. "
        "Coba tanyakan dengan cara lain, atau buka Diagnosis untuk versi singkatnya."
    ),
}


def readiness_lines(d, projection: dict | None = None) -> str:
    """What each path requires, from the adjudicated projection (deterministic, same as the UI).

    One state, once: duplicate route requirements and checks are merged in the projection. Paths can be
    zero."""
    proj = projection if projection is not None else build_readiness_projection(d)
    rows = []
    for p in proj.get("paths") or []:
        met: list[str] = []
        miss: list[str] = []
        unk: list[str] = []
        for it in p.get("items") or []:
            name = str((it.get("title") or {}).get("text") or it.get("key") or "")
            unlock = (it.get("unlock") or {}).get("text")
            hint = f" (to get it: {unlock})" if unlock else ""
            if it.get("settled") is False:
                # CONFLICT ≠ ABSENT ≠ PRESENT (ontology invariant): two readings of the evidence disagree —
                # the item counts as neither met nor missing (absence of evidence is not evidence of
                # absence). One state, once: wording mirrors the LLM read in explain.py.
                unk.append(name + " (conflict: two readings of the evidence disagree, not settled)")
            elif it.get("state") == "PRESENT":
                met.append(name)
            elif it.get("state") == "ABSENT":
                miss.append(name + hint)
            else:
                unk.append(name)
        rows.append(
            f"- {p.get('key')}: status {p.get('status')}. met: {'; '.join(met) or 'none'}. "
            f"missing: {'; '.join(miss) or 'none'}. unknown: {'; '.join(unk) or 'none'}."
            + (("\n" + candidate_line(p)) if candidate_line(p) else "")
        )
    if (proj.get("navigation") or {}).get("status") == "LEGACY":
        return "- (this map predates the current path model: no path result exists; ask for a fresh check-in)"
    if not rows:
        why = "; ".join(str(u.get("code")) for u in proj.get("unresolved") or [])
        rows = [f"- (no paths were formed{': ' + why if why else ''})"]
    return "\n".join(rows + emerging_lines(proj))


def _history(history: list[dict]) -> tuple[str, str]:
    turns = [
        h
        for h in (history or [])
        if h.get("role") in ("user", "assistant") and str(h.get("text", "")).strip()
    ]
    turns = turns[-HISTORY_TURNS:]
    return "\n".join(
        f"{'User' if t['role'] == 'user' else 'You'}: {_clip(t['text'], HISTORY_CHARS)}" for t in turns
    ), " ".join(str(t["text"]) for t in turns)


def _repair_note(bad: list[str]) -> str:
    return (
        "\nYour previous answer broke these rules. Rewrite the answer so it follows the rules, "
        "keep the meaning, and return the full JSON again:\n" + "\n".join(f"- {v}" for v in bad) + "\n"
    )


def _clean_follow_ups(items: list[str], pool: set[str]) -> list[str]:
    out = []
    for q in items or []:
        q = " ".join(str(q).split())
        if q and not check_text(q, pool, FOLLOW_UP_LIMIT) and len(out) < 3:
            out.append(q)
    return out


def ask_session(
    llm, s, question: str, history: list[dict] | None = None, focus: str = "", max_repairs: int = 1,
    projection: dict | None = None, goal_ctx: dict | None = None,
) -> dict:
    """{answer, follow_ups, dropped, grounded_on, generated_ts, model}. `dropped` = dropped by the guard.

    `projection` = the adjudicated readiness projection; when given, the answer is grounded in the SAME
    checklist as the Readiness screen (grounded_on records that).

    GOAL CONSISTENCY (round 4): the answer is checked against THIS session's structured Goal (not another
    Goal in the workspace). A contradiction goes back to the provider once; if it still violates, the answer
    is replaced with a deterministic sentence from the structured Goal + state (never showing an answer
    known to be wrong) and `guard.goal` records only the violation codes."""
    question = _clip(question, QUESTION_CHARS)
    projection = projection if projection is not None else build_readiness_projection(s.diagnosis)
    facts = goal_facts_for(s, goal_ctx)
    pack, pool = build_pack(s, projection=projection, goal_ctx=goal_ctx)
    hist_text, hist_raw = _history(history or [])
    pool = pool | numbers_in(question) | numbers_in(hist_raw)
    readiness = readiness_lines(s.diagnosis, projection)
    pool |= numbers_in(readiness)
    hint = schema_hint(AskReply)
    args = (pack, readiness, focus, hist_text, question, hint)
    reply = llm.structured_call(AskReply, SYSTEM, build_user_prompt(*args))
    def violations(text: str) -> list[str]:
        return (
            check_text(text, pool, ANSWER_LIMIT)
            + check_language(text, getattr(s, "language", "en"))
            + check_answer_goal(text, facts)
        )

    def goal_part(msgs: list[str]) -> list[str]:
        return [m for m in msgs if m.split(":", 1)[0] in GOAL_CODES]

    bad = violations(reply.answer)
    first_goal = codes_of(goal_part(bad))
    retried = False
    for _ in range(max_repairs):
        if not bad:
            break
        try:
            retry = llm.structured_call(AskReply, SYSTEM, build_user_prompt(*args, repair=_repair_note(bad)))
        except Exception:
            break
        retried = True
        bad_retry = violations(retry.answer)
        if len(bad_retry) <= len(bad):
            reply, bad = retry, bad_retry
    lang = "id" if getattr(s, "language", "en") == "id" else "en"
    dropped = bool(bad)
    final_goal = codes_of(goal_part(bad))
    if final_goal:   # never show an answer that contradicts the Goal: the Goal's own facts instead
        answer = f"{goal_line(facts)} {measurement_line(facts)}"
    else:
        answer = FALLBACK[lang] if dropped else reply.answer.strip()
    return {
        "answer": answer,
        "follow_ups": [] if dropped else _clean_follow_ups(reply.follow_ups, pool),
        "dropped": dropped,
        "guard": {"goal": {"checked": bool(facts.metric_id), "violations_first_pass": first_goal,
                           "retried": retried, "violations_after_repair": final_goal,
                           "repaired": bool(first_goal) and not final_goal,
                           "fallback": bool(final_goal)}},
        "grounded_on": "diagnosis+readiness" if (projection.get("paths") or []) else "diagnosis",
        "generated_ts": int(time.time()),
        "model": getattr(llm, "model", "") or getattr(llm, "name", ""),
    }


__all__ = ["ask_session", "readiness_lines", "BANNED"]
