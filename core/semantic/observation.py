"""Contextual semantic observation — ONE LLM call per user event (int 16 §R3-B, F-01, F-04).

Replaces two independent paths (extract_turn + understand_turn) with one meaning authority.
The model receives enough context: the current message, the latest Q&A pair, the active Goal,
current canonical claims (with ids — so it can revise), open uncertainties, and
contradictions. Compaction MUST NOT drop negation/contradiction/source identity (SC-06).
"""
from __future__ import annotations

from core.prompts.core_rules import (
    ANTI_FABRICATION,
    JSON_CONTRACT,
    LANGUAGE_RULES,
    SYSTEM_IDENTITY,
)
from core.semantic.contract import SemanticObservation

# ── context: compact but source-preserving ──────────────────────────────────

_MAX_TAIL = 10           # the last entry (engine question + user answer) is carried verbatim
_MAX_CLAIMS_CTX = 40     # current canonical claims, summarized
_MAX_GOAL_WORDS = 60


def _clip(text: str, words: int) -> str:
    w = (text or "").split()
    return text if len(w) <= words else " ".join(w[:words]) + " …"


def current_view(graph: dict) -> list[dict]:
    """Canonical claims that are STILL valid (active status) — the current version, not history."""
    nodes = (graph or {}).get("nodes") or {}
    out = [n for n in nodes.values() if (n.get("status") or "active") == "active"]
    return sorted(out, key=lambda n: str(n.get("id")))


def _claim_line(n: dict) -> str:
    t = n.get("triple") or {}
    subj = (t.get("subject") or {}).get("label") or "?"
    pred = (t.get("predicate") or {}).get("label") or "?"
    obj = (t.get("object") or {}).get("label")
    qty = n.get("quantity")
    qty_txt = ""
    if isinstance(qty, dict):
        if qty.get("value_kind") == "range":
            qty_txt = f" [{qty.get('low')}..{qty.get('high')} {qty.get('unit', '')}]".rstrip()
        elif qty.get("value") is not None:
            qty_txt = f" [{qty.get('value_kind')}: {qty.get('value')} {qty.get('unit', '')}]".rstrip()
    parts = [subj, pred] + ([obj] if obj else [])
    aspect = f" ({n['aspect']})" if n.get("aspect") else ""
    epi = f", {n.get('epistemic')}" if n.get("epistemic") else ""
    hedge = ", hedge" if n.get("hedge") else ""
    return (f"- {n.get('id')} [{n.get('type') or 'claim'}{aspect}] " +
            " ".join(p for p in parts if p) + f" | tense={n.get('tense')}" + hedge + epi + qty_txt)


def build_context_digest(session, event: dict) -> str:
    """Assemble the observation context from session state (deterministic, replayable)."""
    lines: list[str] = []

    goal = getattr(session, "goal", None) or {}
    goal_text = (getattr(session, "goal_text", "") or "").strip()
    if goal or goal_text:
        lines.append("ACTIVE GOAL (context, not a claim):")
        if goal_text:
            lines.append(f"- user stated: {_clip(goal_text, _MAX_GOAL_WORDS)}")
        # generic serialization: any scalar field of the active Goal, without domain vocabulary
        for k in sorted(goal):
            v = goal.get(k)
            if k in ("goal_id", "notes", "workspace_id") or not isinstance(v, (str, int, float, bool)):
                continue
            if v == "" or v is None:
                continue
            lines.append(f"- {k}: {_clip(str(v), 24)}")
        lines.append("")

    transcript = getattr(session, "transcript", None) or []
    tail = list(transcript)[-_MAX_TAIL:]
    # engine questions are carried TOGETHER with user answers: elliptical answers ("yes",
    # "the second one") are only meaningful against the question they answer
    # (F-04, SC-06). The current message is marked.
    if tail:
        lines.append("RECENT EXCHANGE (oldest first; ENGINE = question the user may be answering):")
        for role, text in tail:
            who = "USER" if role == "user" else "ENGINE"
            lines.append(f"- {who}: {_clip(text, 80)}")
        lines.append("")

    view = current_view(getattr(session, "state_graph", None) or {})
    if view:
        lines.append(
            "CURRENT CANONICAL CLAIMS (id [role] meaning — "
            "cite an id in 'supersedes' to revise it):")
        for n in view[:_MAX_CLAIMS_CTX]:
            lines.append(_claim_line(n))
        lines.append("")

    edges = ((getattr(session, "state_graph", None) or {}).get("edges") or {})
    contradictions = [e for e in edges.values() if e.get("kind") == "contradicts"]
    if contradictions:
        lines.append("OPEN CONTRADICTIONS:")
        for e in contradictions[:6]:
            lines.append(f"- {e.get('src')} contradicts {e.get('dst')}")
        lines.append("")

    return "\n".join(lines)


# ── prompt ────────────────────────────────────────────────────────────────────

OBSERVATION_SYSTEM = f"""{SYSTEM_IDENTITY}

YOUR ROLE: the ONE semantic observation module of the State Discovery Engine
(contract so.v1). You interpret ONE user message in context. You do NOT interview,
do NOT diagnose, do NOT propose the next move. Meaning only.

{LANGUAGE_RULES}

{ANTI_FABRICATION}

EXTRACTION RULES:
- Extract EVERY meaningful statement as a claim with a RAW triple:
  subject / predicate / object. Predicates are the user's own words or a minimal
  neutral paraphrase (wants, dropped_to, passes_through, avoids, fears).
  NEVER use business/framework taxonomy (no funnel, no conversion, no ICP) unless
  the user literally said it.
- role (REQUIRED, one of): goal | desire | event | assumption | gap | claim
    goal = an outcome the user wants to reach
    desire = why it matters / what they ultimately want
    event = something that happened (past occurrence)
    assumption = what the user believes WITHOUT data
    gap = what the user explicitly does not know / does not have / refused to answer
    claim = other present-state facts
- aspect (optional, orthogonal): preference | concern | constraint | intention | plan
  | behavior | conflict. Use it to keep meaning that the six roles alone would lose
  (e.g. "I don't want to add work hours" = claim + aspect constraint; "I feel bad
  disturbing people" = claim + aspect concern).
- QUANTITY SHAPE RULES (hard contract — violations are rejected):
  * value_kind 'range' → ONLY low+high, NO 'value' field ("Rp4-5 juta" = low 4, high 5).
  * value_kind exact|approximate|less_than|at_most → ONLY one 'value', NO low/high.
  * role 'gap' → quantity MUST be null. A gap is the ABSENCE of data ("I don't know /
    I never measured"). If the user actually STATES a number, that claim's role is 'claim'
    (or goal/event/etc), never 'gap'.
- Numbers MUST be typed: value_kind exact|approximate|range|less_than|at_most|
  greater_than|at_least; keep the user's unit ("juta", "k USD", "orang", "jam");
  period monthly|annual|weekly|daily|per_deal|per_project|one_off|unspecified.
  "up to 8 juta" = at_most 8, NOT exact 8. "sekitar/kira-kira/around" = approximate.
  COMPLETENESS: every number, range ("10 sampai 15" = range), or bound ("paling
  banyak 3" = at_most) the user states MUST become a claim with quantity — never
  skip one because it is brief or embedded mid-sentence.
- CODE-SWITCH: an English term inside an Indonesian sentence (e.g. "series A",
  "lead", "closing") is CONTENT, not noise — extract it like any other statement.
- tense: now | past | future. "dulu/used to" = past.
- epistemic: reported (user says so) | estimated (user guesses a number) | measured
  (user cites a real measured figure). Default reported.
- quote: EXACT substring of the CURRENT message, long enough to anchor the claim
  (a clause, not one word). A claim whose quote is not found verbatim will be
  REJECTED by the deterministic verifier.
- REVISIONS: if this message corrects/refines/confirms/negates an earlier canonical
  claim, set supersedes=<that claim id> + revision_kind=correction|refinement|
  confirmation|negation + revision_reason. Never revise silently.
- relations: evidence relations between claims. src/dst = local ref ("c3") or an
  EXISTING canonical claim id from context (cross-turn). kind: related_to | supports
  | contradicts | derived_from | confirms | weakens. Contradictions between this
  message and an earlier claim are exactly what cross-turn relations are for.
- uncertainties: up to 8 short open unknowns that materially matter (free text).
- A message with no meaningful content -> empty lists. NEVER fabricate.

OUTPUT CONTRACT: JSON only, matching the so.v1 schema:
{{"contract_version":"so.v1","language":"...","claims":[{{"ref":"c1","role":"...",
"aspect":"","subject":"...","predicate":"...","object":null,
"quantity":{{"value_kind":"exact","value":18,"unit":"juta","period":"monthly"}} or null,
"tense":"now","hedge":false,"epistemic":"reported","quote":"...",
"supersedes":null,"revision_kind":null,"revision_reason":""}}],
"relations":[{{"src":"c1","dst":"cl-e0002-003","kind":"contradicts","reason":"..."}}],
"uncertainties":["..."]}}

{JSON_CONTRACT}"""


def build_user_prompt(event: dict, context_digest: str, language: str) -> str:
    return f"""USER LANGUAGE: {language}

{context_digest}

CURRENT USER MESSAGE (turn {event.get('turn', '?')}):
<<<
{event.get('text', '')}
>>>

Observe the semantics of THIS message now. Quotes must be exact substrings of THIS message."""


def observe_semantics(llm, event: dict, context_digest: str, language: str) -> SemanticObservation:
    """ONE semantic-understanding call for one event. Provider-agnostic."""
    obs = llm.structured_call(
        SemanticObservation,
        OBSERVATION_SYSTEM,
        build_user_prompt(event, context_digest, language),
    )
    if obs.contract_version != "so.v1":
        raise ValueError(f"kontrak observasi tak dikenal: {obs.contract_version}")
    return obs
