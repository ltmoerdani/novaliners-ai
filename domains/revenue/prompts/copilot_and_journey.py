"""Prompt copilot & journey block — moved from app/main.py & stages/journey.py
(25 Sep 2026 prompt audit): all SYSTEM prompts live in prompts/, the universal
instruction language is English, output mirrors the user's language.
"""
from __future__ import annotations

from domains.revenue.prompts.core_rules import (
    ANTI_FABRICATION,
    LANGUAGE_RULES,
    SYSTEM_IDENTITY,
)

COPILOT_SYSTEM = f"""{SYSTEM_IDENTITY}

YOUR ROLE: the Business Assistant. You answer free-form questions about the
user's session, grounded ONLY in the provided context (goal, evidence ledger,
diagnosis, transcript).

{LANGUAGE_RULES}

{ANTI_FABRICATION}

- If the context is not enough to answer, say plainly what is missing and what
  question the user should answer first.
- Style: straight to the substance, max 180 words, short bullets allowed.
- Return ONLY valid JSON of the form {{"answer": "<your answer>"}}."""


def journey_prompt_block(ctx: dict | None) -> str:
    """J7-b: render a SHORT prompt block (≤6 lines — lesson from internal-docs Phase 3).

    Label language is English (instructions for the LLM); values stay as-is data.
    """
    if not ctx:
        return ""
    # Phase 6.2: accepted observations of THIS session (no prior session needed).
    from app.observations import prompt_lines as _obs_lines
    obs = _obs_lines(ctx.get("session_observations"))
    lines = ["USER JOURNEY (summary of previous session, compiled, not transcript):"]
    p = ctx.get("prior") or {}
    if p.get("primary_constraint_id"):
        lines.append(
            f"- Previous session: PRIMARY {p['primary_constraint_id']}, spectrum "
            f"{p.get('spectrum_level') or '?'}, verdict vs prior: {p.get('verdict') or 'n/a'}."
        )
    pa = ctx.get("prior_actions") or {}
    if pa.get("by_status") or pa.get("by_outcome"):
        lines.append(
            f"- Reported actions: status {pa.get('by_status') or '{}'}, "
            f"outcome {pa.get('by_outcome') or '{}'} — the new plan must "
            f"acknowledge these results, not repeat the same recipe."
        )
    ra = ctx.get("reassess") or {}
    if ra.get("status") not in (None, "NO_PRIOR_DIAGNOSIS"):
        lines.append(
            f"- Reassess: window {ra.get('window_days') or '?'} days, previous "
            f"session age {ra.get('age_days') if ra.get('age_days') is not None else '?'} days "
            f"({ra['status']})."
        )
    dem = ctx.get("demoted_interventions") or {}
    if dem:
        lines.append(
            "- Interventions the user ALREADY ran WITHOUT results "
            f"({'; '.join(f'{k}: {v}' for k, v in sorted(dem.items()))}) — do NOT "
            "recommend them again as NBA; pick an alternative from the menu."
        )
    if len(lines) == 1 and not obs:
        return ""
    if len(lines) == 1:
        lines = []
    return "\n".join(lines + obs) + "\n\n"
