"""Adaptive NextMove reasoning (int 16 §R5-C/D): snapshot -> model -> proposal -> guard -> (limited repair) -> decision.

Responsibilities are separated (BC-03/F-01):
  - MEANING of the user's words = `core/semantic` (so.v1). This module does NOT reinterpret claims, does not change grade,
    does not confirm Goal, does not write requirement status.
  - This module decides "which uncertainty is most meaningful to resolve next and why", gives it
    sentence form, and proposes competing hypotheses. Every reference is checked by the guard.
Failure (provider, schema, guard after 1 repair) -> an honest `degraded` decision: there is NO old deterministic
question picker silently used as a substitute for substance.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from core.prompts.core_rules import ANTI_FABRICATION, JSON_CONTRACT, LANGUAGE_RULES, SYSTEM_IDENTITY
from core.reasoning.contract import NM_CONTRACT_VERSION, NextMoveProposal
from core.reasoning.guard import GuardResult, validate

log = logging.getLogger("novaliners.reasoner")
MAX_REPAIRS = 1

REASONER_SYSTEM = f"""{SYSTEM_IDENTITY}

YOUR ROLE: the NextMove reasoning module (contract {NM_CONTRACT_VERSION}). The user's statements were ALREADY
interpreted into canonical claims; you do NOT re-interpret them, do NOT change claim meaning, evidence grades,
goal confirmation, or any requirement status. You decide: GIVEN what is actually known, which CONSEQUENTIAL
uncertainty should be resolved next, and why.

{LANGUAGE_RULES}

{ANTI_FABRICATION}

HOW TO REASON:
- Pick ONE focus from `uncertainties` (type "uncertainty"), a hypothesis id (type "hypothesis") that discriminates
  between competing explanations, or "goal" only if the goal is listed as unestablished.
- `suggested_kind` per uncertainty: a need already asked once escalates to EVIDENCE_REQUEST (ask for the observable
  evidence, not the same question again).
- Prefer the uncertainty whose different answers would CHANGE a decision (which explanation, which path, whether to
  act). Say what would change in `expected_decision_change`. Do not ask what the claims already answer; do not
  repeat a question already asked (`asked` counts) unless new claims changed the situation.
- Use `knowledge` ONLY as a lens: cite ids in `knowledge_refs` that are listed there; knowledge never states facts
  about the user. Competing hypotheses must cite ACTIVE claim ids as support/contradiction. Do not claim causes
  more strongly than the claims support; list `missing_evidence`.
- HYPOTHESIS DUTY (RC-03): when ACTIVE claims support two or more competing explanations of the user's situation
  — including the user's OWN causal assumption as ONE hypothesis to test, versus an alternative the claims allow
  — you MUST propose them in `competing_hypotheses`, each citing ACTIVE claim ids (supports/contradicts) and
  `missing_evidence` that would discriminate them. Return an empty list ONLY when no grounded competing
  explanation exists yet (not because it is optional or early in the conversation). A user assumption is a
  hypothesis, never a fact and never silently dropped. An alternative must name the CONCRETE mechanism the
  claims allow (e.g. "demand exists but responses are slow", anchored to the claim showing inquiries arrive) —
  a generic "other factors" without a claim-grounded mechanism does not discriminate anything and will be
  treated as absent.
- FIRST-QUESTION DISCIPLINE (CP-01/CP-32): when the user's story expresses NO financial target, do NOT open by
  demanding a numeric revenue/income/omzet target. Ask about what matters in THEIR words: what success looks
  like for them, their current situation, or the constraint/preference they stated. A "goal" focus question must
  restate the user's own words, not fish for a number they never mentioned.
  HARD RULE for the FIRST question of a fresh story with no financial numbers: the question text must NOT contain
  the words "penghasilan", "omzet", "pendapatan", "revenue", or "berapa … juta/rupiah". If the story names a
  CONSTRAINT (hours, caregiving, health, location), the first question should explore how they define success
  WITHIN that constraint (e.g. "what does 'still running' look like for you?"), or ask about the nature of their
  work — never open with their income figure.
- `uncertainties` berisi kebutuhan dari DUA asal: kebutuhan requirement (id planner) dan unknown
  hasil pemahaman user (id `su-...`, origin semantic_observation) — keduanya sama sah sebagai fokus;
  pilih yang jawabannya paling mengubah keputusan. Kebutuhan dengan `asked` >= 1 lebih baik dieskalasi
  ke EVIDENCE_REQUEST (bukti teramati), bukan pertanyaan ulang.
- `knowledge` berisi dua jenis item: `kind:"rule"` (lensa menafsirkan bukti) dan `kind:"probe"`
  (metode pertanyaan diagnostik hasil kurasi — gunakan PRINSIPNYA untuk merancang pertanyaan
  dalam kosakata user sendiri; JANGAN menyalin teks probe verbatim, dan probe tetap BUKAN
  fakta tentang user).
- Honour the user's constraints/preferences visible in claims (aspect constraint/preference/concern).
- If the user said they do not know/track something, do NOT ask for the same number again: propose an
  EVIDENCE_REQUEST/ACTION that would measure it.
- EVIDENCE_REQUEST asks for evidence that ALREADY EXISTS: cite `evidence_source_refs` (ACTIVE claim ids, or the
  knowledge ids offered) and say why the source matters in `information_value_rationale`. A NEW measurement is NOT
  an evidence request — propose it as ACTION carrying `move_design`; the Move is the one place an experiment lives
  (PLANNED -> STARTED -> EXECUTED -> OBSERVED), and an executed Move is never a proven outcome.
- If you must pause (HOLD) while answerable needs remain, explain it PER NEED — a bare `abstain=true` is rejected:
  the need is not material (give its marginal entry an EMPTY `counterfactual`), or it needs EXTERNAL data
  (`answerability=needs_external`), or the user EXPLICITLY asked to pause (cite the ACTIVE claim in
  `basis_claim_refs`; the user's OWN WORDS must ask for a pause/hold/skip — a business constraint alone is NOT a
  pause request). A need that can only be answered by a MEASUREMENT is NOT a HOLD: propose it as ACTION +
  `move_design` so a real PLANNED Move exists — HOLD must never carry `move_design`.
  `conditions_for_abstention` is still required, and HOLD never means the diagnosis is finished.
- `move_text` is ONE message to the user in the user's language (question, evidence request, or action). Natural,
  specific to what they said; never mention internal ids. QUESTION = one question.
- LENGTH DISCIPLINE (the schema hard-rejects overlong strings and the WHOLE turn is lost): `move_text` at most
  ~120 words (~700 characters); `expected_decision_change`, `information_value_rationale`, and every marginal
  field under ~50 words each. When the user's story is rich, CHOOSE what matters — never pad, never restate their
  whole story back to them.
- Decide TWO things in parallel: the next move, AND whether a provisional conclusion is already worth offering
  (`checkpoint_eligibility`). They are independent: you may keep asking one useful question AND say the first
  picture is ready. Level: STATE_ONLY (only the situation, no grounded interpretation yet) · DISCOVERY_NEEDED (a
  MATERIAL need can still be answered in conversation) · PROVISIONAL_READY (all five hold: purpose anchor, state
  anchor, grounded interpretation from cited ACTIVE claims, disclosure of the remaining needs, a useful next step)
  · DECISION_USABLE (PROVISIONAL_READY **and** nothing material must be settled before the recommended action is
  safe to choose).
  CLASSIFY EVERY REMAINING NEED by TWO INDEPENDENT questions (int 18 §11.2) — never by materiality alone:
    (1) MATERIALITY: can you state the counterfactual "if the user answered X, decision Y changes to Z"? An empty
        counterfactual means the need is NOT material.
    (2) ANSWERABILITY NOW: is it answerable in THIS conversation (`answerability=now_conversation`), or does it
        need a NEW measurement / external data?
  Then place it in EXACTLY ONE list, with a `marginal_information_value` entry whose `answerability` matches:
    · material AND answerable now  → `critical_unknown_ids` (the ONLY blocking list; DECISION_USABLE requires it
      to be EMPTY);
    · material AND NOT answerable now (`needs_measurement` / `needs_external`) → `nonblocking_unknown_ids`, and
      the counterfactual STAYS FILLED — it does not block because of ANSWERABILITY, not because it stopped being
      material. Do NOT ask it as a QUESTION: when the decision needs it, the move is ACTION + `move_design`
      (a real measurement);
    · NOT material → `nonblocking_unknown_ids` with an EMPTY `counterfactual`.
  MECHANICAL CHECK — this is computed, not judged (the turn is REJECTED otherwise): for every id you list the
  engine computes `cf` = "non-empty counterfactual" and `now` = "answerability == now_conversation". It rejects
  any run where an id in `critical_unknown_ids` fails `cf AND now`, or where an id in `nonblocking_unknown_ids`
  satisfies `cf AND now`. Therefore: `cf AND now` ⇒ MUST be `critical_unknown_ids`. Everything else ⇒
  `nonblocking_unknown_ids`. There is no third option and no judgement call — "in my opinion this does not block
  the conclusion" is NOT an exemption from the rule.
  If you want to offer a provisional picture while a material, answerable need still exists, that is a LEVEL
  decision, not a list decision: keep the id in `critical_unknown_ids` and set the level to whatever its own
  rules allow (a useful question and a provisional offer may coexist). Do not reclassify the id to express it.
  WORKED EXAMPLE (never copy literally): the user must MEASURE the kitchen's maximum daily capacity, and the
  answer could change whether you advise adding clients or raising price → `nonblocking_unknown_ids` includes
  that need, its marginal entry has `answerability=needs_measurement` and a FILLED counterfactual, and the move is
  ACTION (measurement). Listing it in `critical_unknown_ids`, or making it a QUESTION focus, is a contract
  violation.
  Disclose every remaining need exactly once, with one `marginal_information_value` entry per id.
  `external_evidence_pending` is ORTHOGONAL (true may accompany PROVISIONAL_READY/DECISION_USABLE — say so in
  `rationale`). `can_offer_checkpoint=true` exactly when the level is PROVISIONAL_READY or DECISION_USABLE.
  Never label the conclusion final: you propose, the engine decides.
- ACTION is legal when there is a real basis: `action_allowed` is true, OR the state has a USABLE path (one whose
  `navigable` is true, status is not STOP, and feasibility is SUPPORTED/CONDITIONAL), OR the action IS the
  measurement of a need that cannot be answered in conversation. A path that is STOP or not navigable can NEVER
  justify an action; if you fill `linked_path_id` it MUST be a usable path from `paths` (linking a STOP path
  rejects the proposal); when several usable paths exist, link the one this action belongs to. It MUST cite
  `supporting_claim_refs` and carry `move_design`: objective, measurement_method, expected_evidence,
  completion_criteria, observation_window_days (1..180), plus preconditions/constraints; link `linked_path_id`
  (from `paths`) and `linked_hypothesis_id` when relevant. A Move is a bounded experiment, not generic advice.
  Never invent audience lists, contact details, methods the user did not mention, or success probabilities;
  derive everything from ACTIVE claims.
- THE MOVE'S ACTION LIST (Phase 7, mandatory for ACTION): `move_design.actions` is the checklist the person
  will actually DO. Give 1..12 ONE-STEP actions, each contributing to the objective (`title` one concrete
  sentence in the user's language; optional `instruction`; optional `required`; optional `depends_on`).
  There is NO day/date/week/cadence field and you must NOT write "Hari 1", "Day 2", "today" or a schedule
  into the titles: the person decides when to work. Do NOT pad the list to a number - ONE action is a valid
  Move when that is what the work needs. Default is FREE ORDER: put a 1-based earlier position in `depends_on`
  ONLY when the step genuinely cannot be done before it (then say why in the instruction). Never derive order
  from the list itself. `completion_criteria` says when the Move counts as EXECUTED; `expected_evidence` says
  what result would be looked for later - they are different things.
- `moves` lists existing experiments. If a Move is OBSERVED, you may add `outcome_assessment`: cite
  `observed_claim_refs` (claims attached to that Move). VALIDATED/UNSUPPORTED are not allowed while its observation
  window is open (use INCONCLUSIVE). Never state or imply causation: only whether the observed signal matches the
  expected evidence. An executed Move is NOT a successful outcome.
- `proposed_focus` must be EXACTLY ONE legal id — never a sentence, never two ids joined together: for
  `focus_type=uncertainty` one id from the offered `uncertainties`; for `focus_type=hypothesis` one EXISTING
  hypothesis id (a brand-new hypothesis cannot be a focus); for `focus_type=goal` the literal `goal`. Put your
  reasoning in `move_text`/`information_value_rationale`, NOT in the focus field. `goal_ref` must echo the
  snapshot's `goal_id` EXACTLY, or be empty — never a placeholder such as "goal".
- Echo `snapshot_id` as `state_snapshot_ref`. Cite claim ids in `supporting_claim_refs`.
- `move_design` SHAPE (ACTION only; a HOLD carrying it is rejected): {{"objective":"...",
  "actions":[{{"title":"...","instruction":"","required":true,"depends_on":[]}}],"preconditions":[],
  "constraints":[],"expected_evidence":["..."],"measurement_method":"...","observation_window_days":7,
  "completion_criteria":["..."],"linked_path_id":"","linked_hypothesis_id":""}}. An ACTION whose
  `actions` list is empty is REJECTED (a Move owns its executable actions).

OUTPUT: JSON only, matching nm.v2: {{"contract_version":"nm.v2","state_snapshot_ref":"...","goal_ref":"",
"proposed_move_kind":"QUESTION|EVIDENCE_REQUEST|ACTION|HOLD","focus_type":"uncertainty|hypothesis|goal",
"proposed_focus":"...","move_text":"...","information_value_rationale":"...","expected_decision_change":"...",
"supporting_claim_refs":["cl-..."],"knowledge_refs":[],"competing_hypotheses":[{{"id":"","statement":"...",
"supports":["cl-..."],"contradicts":[],"missing_evidence":[],"knowledge_refs":[]}}],
"evidence_source_refs":[],"candidate_uncertainty_ids":[],"conditions_for_abstention":"","abstain":false,
"user_constraints_considered":[],
"move_design":null,"outcome_assessment":null,
"checkpoint_eligibility":{{"level":"STATE_ONLY|DISCOVERY_NEEDED|PROVISIONAL_READY|DECISION_USABLE",
"basis_claim_refs":["cl-..."],"critical_unknown_ids":["..."],"nonblocking_unknown_ids":["..."],
"marginal_information_value":[{{"uncertainty_id":"...","decision_impact":"...",
"answerability":"now_conversation|needs_measurement|needs_external|unknown","information_gain":"...",
"user_friction":"...","counterfactual":"..."}}],"external_evidence_pending":false,
"can_offer_checkpoint":false,"recommendation":"","rationale":"..."}}}}

{JSON_CONTRACT}"""


def build_user_prompt(snapshot: dict, language: str, action_allowed: bool, feedback: list[str] | None = None) -> str:
    body = {k: snapshot.get(k) for k in ("snapshot_id", "goal", "claims", "claim_ids", "recent_exchange",
                                         "hypotheses", "uncertainties", "knowledge", "requirement_states",
                                         "moves", "paths", "deterministic_hint")}
    fb = ("\n\nYOUR PREVIOUS PROPOSAL WAS REJECTED BY THE VALIDATOR. Fix exactly these problems and re-issue the "
          "full JSON:\n- " + "\n- ".join(feedback)) if feedback else ""
    # BC-07 (incident 16 Oct, c21ccde618be turn 23): Indonesian registry/KB prose rode along in the
    # snapshot and "leaked" into move_text even though USER LANGUAGE=en. The verdict language must not change
    # with language (semantic right), but the RENDERED TEXT must follow the user's language.
    return (f"USER LANGUAGE: {language}\n"
            f"LANGUAGE RULE: every user-facing string you write (move_text, headline, recommendation) MUST be "
            f"in USER LANGUAGE ({language}) only. Registry rules and knowledge in the snapshot may be written "
            f"in Indonesian — that NEVER changes your output language. Do not mix languages.\n"
            f"action_allowed: {str(action_allowed).lower()}\n\n"
            f"STATE SNAPSHOT (selection: {snapshot['selection']}):\n"
            f"{json.dumps(body, ensure_ascii=False, indent=1)}{fb}")


def parse_snapshot_prompt(user: str) -> dict:
    """Retrieve the JSON snapshot back from the user prompt (audit/test; not the decision path)."""
    start = user.index("):\n{", user.index("STATE SNAPSHOT")) + 3
    depth, end = 0, start
    in_str = esc = False
    for i in range(start, len(user)):
        ch = user[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(user[start:end])


def reason_next_move(
    llm: Any, snapshot: dict, *, language: str, graph: dict, hypotheses: dict, knowledge_ids: set[str],
    action_allowed: bool, design_problems=None, assessment_problems=None, path_ids: set[str] | None = None,
    paths: list[dict] | None = None,
) -> dict[str, Any]:
    """Result: {status, proposal, guard, attempts, violations_history, error?}.
    status: ACCEPTED | DEGRADED (provider/schema/guard failed; no step was invented)."""
    attempts: list[dict[str, Any]] = []
    feedback: list[str] | None = None
    # CIR-01 (int 19 §12.5): SCHEMA failure (the model did not produce valid Pydantic) and GUARD failure
    # (the proposal is structurally valid but violates legality) are DIFFERENT categories — both end
    # as an honest DEGRADED, but the final reasons must not be merged into one bucket
    # `guard_rejected_after_repair`.
    last_kind: str | None = None      # "schema" | "guard"
    # SC-09 (int 16): a VALID hypothesis from the last attempt is still carried out even though the Move
    # is ultimately rejected — valid meaning survives beyond the rejected step; `adaptive`
    # decides its application (hypothesis guard = validate_proposals, not Move).
    last_valid_hypotheses: list[dict] = []
    for attempt in range(1 + MAX_REPAIRS):
        try:
            proposal = llm.structured_call(
                NextMoveProposal, REASONER_SYSTEM, build_user_prompt(snapshot, language, action_allowed, feedback))
        except Exception as exc:  # noqa: BLE001 - provider/schema: recorded, not swallowed
            attempts.append({"attempt": attempt, "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                             "error_kind": "schema"})
            if getattr(exc, "status_code", None) in (401, 403, 429) or type(exc).__name__ in (
                    "RateLimitError", "AuthenticationError", "APITimeoutError"):
                return {"status": "DEGRADED", "reason": "provider_unavailable", "attempts": attempts,
                        "proposal": None, "guard": None}
            last_kind = "schema"
            feedback = [f"respons tidak sesuai skema nm.v2: {type(exc).__name__}"]
            continue
        res: GuardResult = validate(proposal, snapshot=snapshot, graph=graph, hypotheses=hypotheses,
                                    knowledge_ids=knowledge_ids, action_allowed=action_allowed,
                                    design_problems=design_problems, assessment_problems=assessment_problems,
                                    path_ids=path_ids, paths=paths)
        attempts.append({"attempt": attempt, "guard": res.to_dict()})
        last_kind = "guard"
        last_valid_hypotheses = res.valid_hypotheses
        if res.ok:
            return {"status": "ACCEPTED", "proposal": proposal.model_dump(), "guard": res.to_dict(),
                    "attempts": attempts, "_valid_hypotheses": res.valid_hypotheses}
        feedback = res.violations
    return {"status": "DEGRADED",
            "reason": "schema_invalid" if last_kind == "schema" else "guard_rejected_after_repair",
            "attempts": attempts,
            "proposal": None, "guard": attempts[-1].get("guard") if attempts else None,
            "_valid_hypotheses": last_valid_hypotheses}
