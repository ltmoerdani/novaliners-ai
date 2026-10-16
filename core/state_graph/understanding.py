"""Universal Understanding layer (M2, int 11 Rev 11.1 §10.3 + strict user review).

The LLM produces a ProposedGraphDelta DIRECTLY (claims + evidence relations +
goals/desires/events/assumptions/gaps) — no longer only via number_claims.

Boundary rules (non-negotiable, from the M2 review):
- The LLM does NOT produce may_indicate (that belongs to KB-match; verify rejects it).
- No next_question here — that is NextMove (M4).
- IDs coming from the LLM are not trusted: the engine assigns ids; the LLM refers to
  claims via indexes into its own list.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from core.prompts.core_rules import (
    ANTI_FABRICATION,
    JSON_CONTRACT,
    LANGUAGE_RULES,
    SYSTEM_IDENTITY,
)
from core.state_graph.models import (
    Concept,
    Edge,
    EdgeKind,
    GraphDelta,
    Modality,
    Tense,
    Triple,
    UniversalClaim,
)

# ── LLM-facing schema (compact; ids & provenance filled by the engine) ────────


class UClaim(BaseModel):
    """One claim produced by understanding — raw triple + context (extraction != interpretation)."""

    type: str = Field(default="claim", description="claim|goal|desire|event|assumption|gap")
    subject: str
    predicate: str
    object: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    tense: str = Field(default="now", description="now|past|future")
    hedge: bool = False
    verbatim: str = Field(description="EXACT quote from the user's message")


class UEdge(BaseModel):
    """Evidence relation between claims — refer to claims by (0-based) index in the claims list."""

    src_index: int
    dst_index: int
    kind: str = Field(
        default="related_to",
        description="related_to|supports|contradicts|derived_from|confirms|weakens",
    )
    reason: str = ""


class UniversalUnderstanding(BaseModel):
    claims: list[UClaim] = Field(default_factory=list)
    edges: list[UEdge] = Field(default_factory=list)


# ── Prompt (universal — NO phase context, NO domain ontology) ────────────────

UNDERSTANDING_SYSTEM = f"""{SYSTEM_IDENTITY}

YOUR ROLE: the universal understanding module of the State Discovery Engine.
You receive ONE user message. Extract the user's current state as a graph of
raw claims and evidence relations. You are NOT interviewing — do not ask
anything. You are NOT diagnosing — do not interpret mechanisms.

{LANGUAGE_RULES}

{ANTI_FABRICATION}

EXTRACTION RULES:
- Extract EVERY meaningful statement as a claim with a raw triple:
  subject / predicate / object (or numeric value + unit).
- Predicates are RAW labels from the user's own words or a minimal neutral
  paraphrase (e.g. 'passes_through', 'wants', 'dropped_to'). Do NOT use any
  business/domain taxonomy — no 'conversion', no 'funnel', no framework names,
  unless the user literally said them.
- Claim types: goal (what they want), desire (why they want it), event (what
  happened), assumption (what they believe without data), gap (what they
  explicitly don't know/have), claim (everything else factual).
- Numbers: normalize value to the natural unit the user used (8jt -> 8.0 with
  unit 'juta'; $3k -> 3.0 with unit 'k USD'). Informal formats must be read.
- tense: now (currently true) | past (was true, stopped: 'dulu', 'pernah',
  'used to') | future (plan/target).
- hedge: true when approximate ('around', 'kira-kira', 'sekitar', 'maybe').
- verbatim: EXACT substring of the user's message. A claim without a valid
  verbatim will be REJECTED by the system.
- Edges: only evidence relations between claims you just extracted
  (related_to, supports, contradicts, derived_from, confirms, weakens).
  NEVER invent interpretive relations like 'indicates a bottleneck' —
  interpretation is not your job and will be rejected.
- A message with no meaningful claims -> empty lists. Never fabricate.
- Goals/desires/events/assumptions/gaps are as important as numbers: 'saya
  capek semua pekerjaan lewat saya' is a first-class claim.

EXAMPLES (few-shot):
User: 'Dulu omzet saya 30 juta, sekarang sekitar 18 juta. Saya juga merasa
makin banyak pekerjaan yang harus saya handle sendiri.'
claims:
- {{type:'claim', subject:'omzet', predicate:'was', value:30.0, unit:'juta',
   tense:'past', hedge:false, verbatim:'Dulu omzet saya 30 juta'}}
- {{type:'claim', subject:'omzet', predicate:'currently', value:18.0, unit:'juta',
   tense:'now', hedge:true, verbatim:'sekarang sekitar 18 juta'}}
- {{type:'claim', subject:'semua pekerjaan', predicate:'passes_through',
   object:'saya', tense:'now', hedge:false,
   verbatim:'semua pekerjaan yang harus saya handle sendiri'}}
edges:
- {{src_index:0, dst_index:1, kind:'related_to', reason:'same subject omzet'}}
- {{src_index:1, dst_index:2, kind:'related_to', reason:'same turn context'}}

User: 'Saya pengen banget bisa libur sebulan tanpa bisnis mati.'
claims:
- {{type:'desire', subject:'saya', predicate:'wants', object:'libur sebulan tanpa bisnis mati',
   tense:'future', hedge:false,
   verbatim:'pengen banget bisa libur sebulan tanpa bisnis mati'}}

{JSON_CONTRACT}"""


def build_user_prompt(user_text: str, language: str) -> str:
    return f"""USER LANGUAGE: {language}

USER MESSAGE:
\"\"\"{user_text}\"\"\"

Extract the graph delta now."""


# ── Engine-side: UClaim -> UniversalClaim (ids & provenance engine-made) ─────

_TENSE = {"now": Tense.now, "past": Tense.past, "future": Tense.future}
_KINDS = {
    "related_to": EdgeKind.related_to,
    "supports": EdgeKind.supports,
    "contradicts": EdgeKind.contradicts,
    "derived_from": EdgeKind.derived_from,
    "confirms": EdgeKind.confirms,
    "weakens": EdgeKind.weakens,
    # passed through AS-IS so the verify gate is the one that rejects + records the reason —
    # not silently dropped here (M2 review: the LLM must not produce
    # may_indicate; the rejection must be visible in the drift report)
    "may_indicate": EdgeKind.may_indicate,
}


def _modality(hedge: bool, tense: Tense, ctype: str) -> Modality:
    if ctype == "assumption":
        return Modality.hypothetical
    if hedge:
        return Modality.hedged
    if tense == Tense.future or ctype in ("goal", "desire"):
        return Modality.aspirational
    return Modality.factual


def delta_from_understanding(
    u: UniversalUnderstanding, turn: int, session_id: str
) -> GraphDelta:
    claims: list[UniversalClaim] = []
    ids: list[str] = []
    for i, c in enumerate(u.claims, 1):
        cid = f"cl-t{turn}-{i:03d}"
        ids.append(cid)
        ctype = c.type if c.type in ("claim", "goal", "desire", "event", "assumption", "gap") else "claim"
        tense = _TENSE.get(c.tense, Tense.now)
        claims.append(
            UniversalClaim(
                id=cid,
                type=ctype,
                triple=Triple(
                    subject=Concept(label=c.subject),
                    predicate=Concept(label=c.predicate),
                    object=Concept(label=c.object) if c.object else None,
                    value=c.value,
                    unit=c.unit,
                ),
                tense=tense,
                temporal_context=f"turn {turn}",
                modality=_modality(c.hedge, tense, ctype),
                hedge=c.hedge,
                verbatim=c.verbatim,
                provenance={"turn": turn, "session": session_id, "source": "universal_understanding"},
                confidence="self_reported",
            )
        )
    edges: list[Edge] = []
    for j, e in enumerate(u.edges, 1):
        kind = _KINDS.get(e.kind, EdgeKind.related_to)
        if not (0 <= e.src_index < len(ids) and 0 <= e.dst_index < len(ids)):
            continue  # wild index reference dropped silently before verify
        edges.append(
            Edge(
                id=f"e-t{turn}-{j:03d}",
                src=ids[e.src_index],
                dst=ids[e.dst_index],
                kind=kind,
                provenance={"turn": turn, "reason": e.reason or "llm relation"},
            )
        )
    return GraphDelta(claims=claims, edges=edges)


def understand_turn(llm, user_text: str, language: str) -> UniversalUnderstanding:
    """Call the LLM with the universal prompt. Provider-agnostic via structured_call."""
    return llm.structured_call(
        UniversalUnderstanding,
        UNDERSTANDING_SYSTEM,
        build_user_prompt(user_text, language),
    )
