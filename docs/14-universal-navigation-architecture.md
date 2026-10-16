# 14 — Universal Navigation Architecture: Possible Path, Route, Requirement, Readiness

> **Status**: 🟢 Active — **CANONICAL DOCUMENT** for Possible Path, Route, Requirement, Readiness, Applicability, and Knowledge→Mechanism→Candidate Possibility. Implemented on branch `iteration/universal-navigation-architecture` (30 Sep 2026; provenance/route/legacy/conflict hardening completed in the same iteration; the Knowledge→Candidate Possibility layer was added 1 Oct 2026 on top of the frozen foundation, [§23](#23-knowledge--mechanism--candidate-possibility); **that layer was CLOSED and FROZEN on 1 Oct 2026, [§24](#24-closing-the-candidate-possibility-layer-1-oct-2026--frozen)**: generation/evaluation boundaries, conflicts and absence assumptions never vanish, one path→route pipeline for every path origin, Possible Path 0..N with a UI presentation cap of 5; **M4 — live conversation driven by state, not phases — IMPLEMENTED 2 Oct 2026 on branch `iteration/universal-conversation-navigation-m4`, [§25](#25-m4--conversation-as-state-navigation)**: Applicable Requirement Set, live adjudication, a single Requirement State Reader, a deterministic Question Planner with reason trail and replay). Every implementation claim carries a label: **IMPLEMENTED** · **PARTIALLY IMPLEMENTED** · **NOT YET IMPLEMENTED** · **HISTORICAL** (see §21).
> **Topic**: From "Revenue has five fixed paths and readiness = a Revenue gate system" to a universal pipeline: `Universal State → Knowledge → Mechanism → Candidate Possibility → Applicability/Evaluation → Possible Paths (0..N) → Routes → Readiness → NextMove → Grounded narrative`; the screen draws at most five paths at a time (presentation cap, not a generation limit, §24.7). Revenue becomes the first domain plugin. In the live conversation, the next step is chosen from state by the Question Planner: `message → evidence → adjudication → state → Applicable Requirement Set → Requirement State → Planner → QUESTION | EVIDENCE_REQUEST | ACTION | HOLD → new evidence` (§25).
> **Updated**: 2026-10-02 (M5: the phased interview engine removed, §26)
> **Tags**: architecture, question-planner, conversation-loop, requirement-state, applicable-requirement-set, live-adjudication, possible-path, candidate-possibility, mechanism, candidate-generation, knowledge-taxonomy, presentation-cap, absence-of-record, knowledge-provenance, route-composition, legacy-artifact, readiness, requirement-registry, presentation, narrative-grounding, domain-plugin
> **Related**: `15` (**document map: what is current, what is history, reading order** — this document remains the single canonical source of the architecture) · `10` (constitution of 7 invariants — beneath this) · `11` (Universal State inversion) · `04-knowledge-substrate/08` (route ontology: RouteNode, frontier) · `04-knowledge-substrate/09` (Requirement Registry) · `07-design/ask-and-readiness-design.md` (Readiness & Ask screens) · [`../05-proof-and-gates/07-m4-completion-matrix.md`](../05-proof-and-gates/07-m4-completion-matrix.md) (M4 closure evidence: per-item status, commands, honest limits) · [`../05-proof-and-gates/08-m5-completion-matrix.md`](../05-proof-and-gates/08-m5-completion-matrix.md) (evidence of the phase-engine removal, M5)
> **Supersedes**: the "path = five fixed routes" concept (`02-product-concept/03` §4.5, `06-history-frontier/07`), `REQ_EN` / `GATE_REQ` (old readiness), the string-gate → requirement mapping. See [§20](#20-superseded-documents-and-the-term-map).

---

## 0. One sentence

> **Knowledge defines the supported possibility space. Verified state determines what applies. The generator proposes candidates. The deterministic evaluator decides what survives. Routes compose what survives into workable structure. Readiness projects the state of verified requirements. Narrative interprets that state and never creates it.**

The direction that must never be reversed: `LLM proposes → Knowledge supports → Evidence anchors → Engine decides → Projection explains → UI renders → Outcome becomes new evidence`.

## 1. Data flow

```text
 USER ──► UNIVERSAL STATE ──► VERIFIED EVIDENCE
                                     │
            KNOWLEDGE (rules, state, detected mechanisms) + APPLICABILITY
                                     │   rule ──► RuleSupport (anchored to real evidence, §6.1)
            ┌────────────────────────▼────────────────────────┐
            │  MECHANISM            core/navigation/candidate   │  active only when anchored support (§23)
            └────────────────────────┬────────────────────────┘
                                     │  active / unsettled / contested / rebutted mechanisms
            ┌────────────────────────▼────────────────────────┐
            │  CANDIDATE POSSIBILITY core/navigation/candidate  │  mechanism → direction pattern  ← proposal, NOT a path
            │  CANDIDATE GENERATION  core/navigation/generator  │  + emerges_when of declared strategies
            └────────────────────────┬────────────────────────┘
                                     │  0 / 1 / N candidates (+ provenance)
            ┌────────────────────────▼────────────────────────┐
            │  CANDIDATE EVALUATION   core/navigation/evaluator │  applicability, feasibility  ← decides
            └────────────────────────┬────────────────────────┘
                                     │  POSSIBLE PATHS (0..N)  + unresolved when 0 + "emerging" (not yet paths)
                  ROUTE COMPOSITION (strategy-first: path → template)   ontology/route/plan.py
                                     │
                                   ROUTE ──► nodes: requirement · satisfaction · executability
                                     │
            ┌────────────────────────▼────────────────────────┐
            │  READINESS PROJECTION   core/navigation/readiness │  consumer, not the arbiter of meaning
            └───────────────┬─────────────────────┬───────────┘
                            ▼                     ▼
                           UI              NARRATIVE (LLM) ──► anchored claims ──► deterministic guards
                                     │
                                NEXT MOVE (v1 selector, over non-STOP route paths)
                                     │
                     execution ──► new evidence ──► the map evolves

 PRESENTATION (UI, not engine): the engine returns 0..N paths; the screen draws at most 5 at a time + "+N other possibilities" (§24.7)
```

**Live conversation loop (M4, §25).** The flow above is the navigation architecture; in a live session it runs **every turn** through the state loop (`evidence → live adjudication → provisional Possible Paths → Applicable Requirement Set → Requirement State Reader → Question Planner`). NextMove v1 (the selector over routes) becomes one `DOWNSTREAM` stage of the Question Planner (§25.5): forwarded, not duplicated.

Code: `mvp/core/navigation/` (generic) · `mvp/domains/revenue/navigation/` (Revenue plugin) · `mvp/ontology/possibility/` (Revenue possibility space) · `mvp/ontology/route/` (templates, composition, lifecycle, **`path_routes.py`: one path→route pipeline for every path, whatever its origin**) · `mvp/app/static/js/present-cap.js` (UI presentation cap) · `mvp/engine/requirements.py` + `mvp/ontology/registry/` (Requirement Registry + Presentation) · `mvp/core/stages/{knowledge_rules,rule_predicates,rule_support}.py` (rule interpreter + provenance) · **M4**: `mvp/core/navigation/{applicability,requirement_state,planner,planner_input,planner_text}.py` (generic) · `mvp/app/{turn,navigation}.py` (state loop) · `mvp/ontology/mapper/live_adjudication.py` + `mvp/store/requirement_state.py` (live adjudication + single reader) · `mvp/domains/revenue/navigation/live.py` (provisional paths + planner injection) · `mvp/app/static/js/nav-move.js` (UI).

## 2. Definitions (do not merge)

| Term | Definition | Not |
|---|---|---|
| **Universal State** | The user's verified state: claim + provenance + time (docs 10/11). | Not RevenueState (that is a domain projection of state). |
| **Knowledge** | What a source states about mechanisms, strategies, and requirements (KB, `ontology/knowledge`, `mechanisms.json`, registry). *Available* hypotheses, not facts about the user. Serves as explanatory / applicability / requirement / constraint (§24.2). | Not a decision; **not Evidence** (evidence = what the user stated/was measured; knowledge only applies when evidence anchors it); **does not always become a Mechanism** — only the explanatory kind. |
| **Applicability** | Whether a possibility/route applies to the user's situation: `APPLIES · NOT_APPLICABLE · UNKNOWN`. | Not satisfaction. |
| **Active Knowledge** | The part of knowledge triggered by the user's state: detected mechanisms, active rules, state claims — all **signals** (`state:` · `mechanism:` · `rule:`). | |
| **Mechanism** | The explanation of **why** a state implies a possibility (e.g. `pricing_avoidance_loop`, `activation_bottleneck`). Active only when its support is anchored in evidence: detected directly from evidence, or **derived from verified knowledge** (`rule:`) (§23). A `mechanism:<id>` TRUE signal without evidence = UNSUPPORTED. | Not a strategy, not an action, not a requirement, not a route. |
| **Candidate Possibility** | A **proposal** that a direction might be relevant, born from active mechanisms through the `mechanism → direction` pattern (`PossibilityPattern`). Identity = `cand.<direction>` (canonical). Carries only identity + proposal content + provenance (`Proposal`); not yet evaluated: no applicability, feasibility, route, or readiness (§23, §24.3). | **Not** a Possible Path; not a strategy; not a truth claim. |
| **Motion** | Broad domain primitive (Revenue: `ACQUISITION`, `REPRICING`, `EXPANSION`, `PARTNERSHIP`, `PAID_ACQUISITION`). An opaque label on strategies, declared by the domain (§7.2): vocabulary/substrate. | **Not** the definition of a Possible Path. **Not** path identity. **Not the universe of Possible Paths** (§24.5). |
| **Strategy** | A method of moving toward the goal, declared by domain knowledge (`StrategySpec`). Path and route identity derive from `strategy_id`. | Not a path; not a route. |
| **Possible Path** | **A contextual hypothesis that has PASSED deterministic evaluation**: a plausible direction from the user's verified state toward the goal. Dynamic: 0, 1, 2, … N. Identity = `path.<strategy_id>`. Born from declared strategies, from promoted Candidate Possibilities, or both (provenance merged). | Not a template; not a motion; not a Candidate Possibility; there is no "five" invariant. |
| **Presentation cap** | A display policy: the screen draws at most 5 Possible Paths at a time (`PATH_VIEW_CAP`), the rest honestly announced ("+N other possibilities") and still available with their evidence/provenance (§24.7). | **Not** a generation limit; not a completeness target (5 is not a quota); 3 is not a hard limit; not a ranking. |
| **Route Template** | The requirement composition grammar for ONE strategy (`template.strategy_id`). A path may exist **without** a template (`route_substrate.available=false`). | Not a Possible Path. |
| **Route** | A concrete composition of requirements + evaluable, workable nodes (an instance of a template). Identity = `route_id` (UUID) under the `{goal, strategy, scope}` key. | Not a graph revision. |
| **Requirement** | A world condition that must hold (registry: definition, observability, satisfaction rule, provenance). | Not an activity (that is a node/action). |
| **Applicable Requirement Set** | Requirements from the global registry declared relevant by a **context** (check path, route node, route template) for this user now, with applicability `APPLIES · NOT_APPLICABLE · UNKNOWN` and its origin (§25.2). | Not the registry (registry = global WHAT); not a checklist; not satisfaction. |
| **Requirement State** | The state of one requirement for one user produced by **adjudication**, recorded in a user-scoped ledger, read through ONE reader (§25.3). | Not evidence; not a mapper proposal; not applicability. |
| **Question Planner** | A pure deterministic function that picks the conversational NextMove (`QUESTION · EVIDENCE_REQUEST · ACTION · HOLD`) from state and uncertainty, with reason trail and replay (§25.5). | Not an LLM; not a question list; not a phase engine; not a ranking. |
| **Action** | Something the user actually does. | Not proof that it worked (INV-R8). |
| **Outcome** | What happened after execution. Becomes new evidence. | |

Six axes that must **never** be merged into one score:

| Axis | Values | Question | Owner |
|---|---|---|---|
| Applicability | `APPLIES · NOT_APPLICABLE · UNKNOWN` | Does it apply to this situation? | evaluator (path), composer (route) |
| Satisfaction | `PRESENT · PARTIAL · UNKNOWN · ABSENT` | Is the world condition proven? | adjudication (ledger) / checks |
| Executability | `TRUE · FALSE · UNKNOWN` | Can it be done now (no unmet dependencies)? | route composer (from `depends_on`) |
| Feasibility | `SUPPORTED · CONDITIONAL · CONTRADICTED · UNDETERMINED` | The **engine's** decision on a path | evaluator |
| Lifecycle | `OPEN · PAUSED · STOPPED · CLOSED` | **Process** state/decision | outcome store / route lifecycle |
| Status words | `OPEN · TEST_FIRST · NOT_YET · STOP` | Human-reader language | `display_status()` — one mapping |

### 2.1 Words used on more than one axis (do not merge)

Some words appear on different axes. Using them without naming the axis is the most common source of misreading (especially in historical documents):

| Word | Axis A | Axis B / C | Rule |
|---|---|---|---|
| **STOP** | the **Possible Path** status word (`display_status`), with two origins in `stop_provenance`: `ENGINE_CONTRADICTION` (feasibility `CONTRADICTED`) and `LIFECYCLE` (user decision; §12) | the lowest level of the **decision spectrum** (`STOP · NOT_YET · TEST_FIRST · GO_SMALL · PROCEED · SCALE`, `core/stages/spectrum.py`): a verdict per diagnosis/action, not a path state | three different things; engine STOP ≠ user STOP ≠ spectrum STOP. The spectrum never overrides path feasibility |
| **NOT_YET / TEST_FIRST** | path status words (`CONDITIONAL` → `NOT_YET`, `UNDETERMINED` → `TEST_FIRST`; §5) | decision spectrum levels | same word, different object (path vs action verdict) |
| **GO / GO SMALL / PROCEED / SCALE** | **not** path statuses | decision spectrum levels (`GO_SMALL`, `PROCEED`, `SCALE`); "GO" is also the product tagline | never write that a path is "GO"; the human-readable equivalent of path `OPEN` is language only |
| **Mechanism** | a `MechanismSpec` derived from knowledge (§23) | a mechanism **detected from evidence** via the `ontology/mechanisms.json` catalog (Revenue path) | one concept, two activation sources, read as the same `mechanism:<id>` signal (§23.3) |
| **Hypothesis** | a constraint hypothesis in diagnosis (constraint ranking) | a Possible Path = a contextual hypothesis that passed evaluation (§2) | not the same object; constraint ranking is not path ranking |
| **Readiness** | the Readiness projection (§10) over route/check requirements | `revenue_state.readiness` = four basic business readiness signals (getting clients, converting, delivering, growth) | two different things sharing a name |
| **NextMove** | the selector over non-STOP routes (§7, `ontology/route/next_move.py`), now a `DOWNSTREAM` stage of the Question Planner | the conversational step produced by the Question Planner (§25.5; int 11 §10.11–§10.12) | selector v1 = one stage; the M4 planner (deterministic, uncertainty-driven) owns the full conversational decision; full quantitative VoI stays FUTURE |
| **Route** | a requirement composition (§7) | "route" in historical documents = an Era 9 display path/strategy | in new documents: path ≠ route |
| **Motion** | a domain primitive label on strategies (§7.2, §24.5) | in historical documents often used as a synonym for "path" | motion ≠ path |

## 3. Universal State, Knowledge Substrate, Active Knowledge

Universal State (docs 10/11) remains the source of truth. Domains read state through **signal readers** (`SignalReader`): functions `id → Signal`. The `Signal` shape (`core/navigation/contracts.py`):

| Field | Meaning |
|---|---|
| `value` | `True · False · None`; **`None` = not yet known, not `False`** (INV-9) |
| `reason`, `i18n` | the reason in machine language (`id`) and UI language |
| `refs` | references to real evidence/claims (evidence-ledger ids; transcript quotes in the form `transcript:"<quote>"`) |
| `basis` | audit detail (e.g. the satisfied rule predicate branch + its anchors) |
| `unsupported` | the reader KNOWS a claim exists (e.g. a rule matched) but its basis cannot be formed; `value` then `None` |

The signal id namespace determines the provenance column: `state:<name>` (state claims), `mechanism:<id>` (mechanisms detected from evidence, `ontology/mechanisms.json`), `rule:<id>` (active KB rule). Knowledge *shifts possibilities* through these signals: the `pricing_avoidance_loop` mechanism births a repricing strategy even before revenue numbers exist; `trust_gap` births partnership/referral. Without mechanisms and without numbers → no paths. The Revenue reader: `domains/revenue/navigation/signals.py`. **IMPLEMENTED.**

### 3.1 Evidence semantics

- **Absence of evidence ≠ evidence of absence.** No evidence does not mean the condition is false: signal `None`, satisfaction `UNKNOWN`, feasibility `UNDETERMINED`. No layer (engine, projection, LLM, UI) ever downgrades `UNKNOWN` into `ABSENT`/`FALSE`/"failed".
- `ABSENT`/`False` only comes from evidence that **states otherwise** (registry RR10: contradicting), never from silence.
- Tiered evidence (transactional · behavioral · self_reported · outcome) and `is_gap` evidence (missing data, not a fact) provide no positive support (int 08 corrective T2) — also enforced on rule anchors (§6.1).
- A "already done" report is not proof that it worked (INV-R8): it never changes satisfaction, only the `execution_view`.

## 4. Candidate Generation (`core/navigation/generator.py`)

The generator **proposes**; it does not judge feasibility, does not decide applicability, does not compose routes.

- Input: `PossibilitySpace` (strategies + `goal_signal`) and a `SignalReader`. Every read goes through `grounded(reader)` (§6.1, PROV-02).
- `goal_signal` not `True` → **zero candidates**, reason `GOAL_NOT_ESTABLISHED` (not yet known) or `GOAL_ABSENT` (proven absent).
- Per strategy: `emerges_when` (a Kleene tri-state predicate over signals) → `TRUE` = a candidate is born with **real support**; `FALSE` = `not_emergent`; `None` = `undetermined` + the missing signals. An empty predicate = `None`: a strategy with no emergence basis is never born. Empty `all_of`/`any_of` operands are rejected (vacuous truth is banned; rejected both at `StrategySpec` construction and at evaluation).
- Candidate provenance = the supporting signals actually evaluated (not assembled after the fact).
- Knowledge signals claimed active but without a basis are recorded in `generation.unsupported_knowledge` (audit) and **never** become support.
- The candidate count is free: 0, 1, 2, 5, 10, … (tested in `evals/test_navigation_universal.py`). **IMPLEMENTED.**

## 5. Candidate Evaluation (`core/navigation/evaluator.py`)

Per candidate, deterministic:

1. **Applicability** — `not_applicable_when` `TRUE` → `NOT_APPLICABLE`: the candidate is **discarded**, reason recorded in `generation.rejected`. An exclusion of `None` → applicability `UNKNOWN`, the candidate survives with `missing_evidence`.
2. **Feasibility** from `checks`: all `PRESENT` → `SUPPORTED`; any `hard` check `ABSENT` → `CONTRADICTED`; any `prereq` check `ABSENT` → `CONDITIONAL`; otherwise (some `UNKNOWN`) → `UNDETERMINED`.
3. **Lifecycle** from outside (e.g. the user stops a path) is applied **on top of** feasibility (`apply_lifecycle`) — it never overrides it.
4. `status` (reader word) = `display_status(feasibility, lifecycle)`: `STOPPED/CLOSED` or `CONTRADICTED` → `STOP`; `SUPPORTED` → `OPEN`; `CONDITIONAL` → `NOT_YET`; `UNDETERMINED` → `TEST_FIRST`.

### 5.1 What `SUPPORTED` means, and strategies without checks

`SUPPORTED` means **every declared check is proven `PRESENT`**. It does *not* mean route requirements are satisfied (satisfaction) and does *not* mean it can be executed now (executability): an `OPEN` path with 0 of 7 requirements proven is valid (**OPEN ≠ READY**).

"No declared blocker" is **not** "proven viable". That is why `all([])` must never silently become `SUPPORTED`:

| State | Feasibility | `feasibility_basis` (on the path) |
|---|---|---|
| strategy has checks, results are decisive | per the rules above | `CHECKS` |
| no checks, domain **declares** `no_preconditions=True` | `SUPPORTED` | `DECLARED_UNCONDITIONAL` |
| no checks and no declaration | `UNDETERMINED` (status `TEST_FIRST`) | `NO_CHECKS_DECLARED` |

`no_preconditions` together with `checks` is rejected at `StrategySpec` construction. The UI never states "your evidence passed all checks" for a path with no checks. **IMPLEMENTED** (`test_navigation_semantics.py` §E).

`TRUE` on a node's executability (`any(ABSENT|PARTIAL) → FALSE`, `any(UNKNOWN) → UNKNOWN`, otherwise `TRUE`, int 08 §3.4) means *no unmet dependencies* — a scheduling fact, neither a viability nor a satisfaction claim.

A `CONTRADICTED` candidate **survives** as `STOP` with its reason (do-not is navigation state). The output is a **PathSet** (`version` = `PATHSET_VERSION` = **3**): `{paths[0..N], generation{considered, emerged, not_emergent, undetermined, rejected, unsupported_knowledge}, unresolved[]}`. Zero paths **must** carry `unresolved` (universal codes `EMPTY_POSSIBILITY_SPACE · GOAL_NOT_ESTABLISHED · GOAL_ABSENT · INSUFFICIENT_VERIFIED_STATE · NO_SUPPORTED_STRATEGY · ALL_CANDIDATES_NOT_APPLICABLE`) — `validate_path_set` rejects zero paths without a reason, paths without provenance, and knowledge provenance without an anchor.

## 6. Possible Path, Motion, Strategy

```jsonc
{
  "path_id": "path.value_repricing",      // from the STRATEGY, not the motion
  "strategy_id": "value_repricing",
  "motion": "REPRICING",                  // domain primitive — informational attribute, not identity
  "title": "Repricing your offer",
  "applicability": "APPLIES",
  "feasibility": "SUPPORTED",
  "feasibility_basis": "CHECKS",
  "lifecycle": "OPEN",
  "status": "OPEN",
  "stop_provenance": [],                  // ENGINE_CONTRADICTION and/or LIFECYCLE, origins stay separate
  "checks": [{ "check_id": "willingness_to_pay", "requirement_id": "commercial.willingness_to_pay",
               "state": "PRESENT", "kind": "hard", "reason": "...", "refs": ["ev-3"],
               "i18n": { "en": { "title": "...", "unlock": "...", "reason": "..." } } }],
  "provenance": { "state_claims": ["state:goal_established", "state:existing_revenue"],
                  "mechanism_ids": [], "knowledge_ids": [], "evidence_ids": ["ev-1"],
                  "transcript_anchors": [], "knowledge_support": [],
                  "support": [...], "knowledge_sources": [{"source_id": "vp", "chapters": ["ch02"]}],
                  "strategy_id": "value_repricing", "motion": "REPRICING",
                  "route_template_ids": ["value_repricing_v1"], "emerges_when": {...} },
  "route_substrate": { "template_ids": ["value_repricing_v1"], "available": true }
}
```

### 6.1 Provenance — from knowledge to evidence (PROV-01..04, KNOW-01/02) — IMPLEMENTED

Every Possible Path answers **"why does this path exist?"** from the actual generator/evaluator inputs, never assembled after the fact. For knowledge, the answer must reach the **evidence that made the rule TRUE**:

```text
Knowledge Rule ─► evaluation ─► RuleSupport(evidence/quote anchors, per predicate branch)
   ─► rule_signal ─► Signal(TRUE, refs = anchors) ─► emerges_when ─► Candidate ─► Possible Path
   └─ basis cannot be formed ─► Signal(None, unsupported) ─► does NOT become support (recorded in generation)
```

- **Tier 1 (deterministic rules)** — `rule_predicates.trace_predicate` uses the same leaves as the ordinary evaluator (`_eval_condition`) and records the branches that were **satisfied**: `all_of` = the union of all children's anchors (A→E1, B→E2 stay separate per branch); `any_of` = only the branches actually satisfied (A true, B false → only A anchors; if both are true, both are valid); `none_of` carries no positive anchors. Trace/evaluator `matched` agreement is tested over every tier-1 KB rule (`test_knowledge_provenance.py`, property-based).
- **Tier 2 (judgment/LLM)** — free-form `applied_to` citations are **verified**: the evidence id must exist in the ledger; the quote must appear verbatim in that evidence (mapped to that evidence id) or in the transcript (quote anchor). Paraphrase, invented ids, or too-short citations → `UNSUPPORTED`. *Honest limit*: the engine guarantees the anchor is **real**; whether that evidence truly satisfies the rule's condition remains an LLM judgment.
- `is_gap` evidence is not an anchor. A rule matched only because of gap evidence → `UNSUPPORTED`.
- Shape: `RuleSupport{rule_id, tier, status SUPPORTED|UNSUPPORTED, evidence_ids, quotes, branches[], reason}` (`core/schema/provenance.py`); `KnowledgeRuleOutcome.rule_supports()` hands them to navigation; the generic bridge `core/navigation/knowledge.rule_signal` is usable by any domain reader.
- **PROV-01** every matched rule contributing to a candidate has `knowledge_support` (rule, anchors, branches). **PROV-02** a `rule:`/`mechanism:` TRUE signal without `refs` is downgraded to `None` + `unsupported` by `grounded(reader)` at the core boundary (applies to any domain reader), and `validate_path_set` rejects knowledge provenance without an anchor. **PROV-03** path provenance stores `state_claims`, `mechanism_ids`, `knowledge_ids` (+ `knowledge_support`), `evidence_ids`, `transcript_anchors`, `strategy_id`, `motion`, `route_template_ids`. **PROV-04** when a basis cannot be formed, the system does not invent: the result is `UNSUPPORTED`/`UNKNOWN`, the candidate is not born, and the reason is recorded.
- Transcript quotes go into `transcript_anchors`, never polluting `evidence_ids`.

**Full Evidence → Possible Path lineage (PROV-01, audited end-to-end)**: evidence ledger → `trace_predicate_full` records every predicate branch as `BranchSupport{branch, operator, operand, evidence_ids, quotes}` (anchored branch naming, e.g. `.all_of[0].text_contains_any`) → `support_from_branches` assembles the `RuleSupport` → `rule_signal` carries `refs` = the union of all branch anchors and `basis` = the branch dump → the candidate support row carries that `basis` → `path.provenance.knowledge_support` stores branches **identical** to what the evaluator saw; the reverse audit ensures every ref is a ledger id or a transcript quote (`test_knowledge_provenance.py` §LINEAGE). The reverse direction is tested too: evidence revoked from the ledger + transcript rebuilt → the branch falls → the rule no longer matches → the path is not born.

**Canonical tier-2 epistemic interpretation (KLEENE at the navigation boundary)**: an anchored branch → `TRUE`; `UNSUPPORTED` → `UNKNOWN` (not "did not match"). A `RuleSupport` with status `UNSUPPORTED` **never becomes positive support at any navigation boundary**: `rule_signal` → `None` + `unsupported`; `build_path_set` → the path is not born, the rule is recorded in `undetermined.missing` + the `unsupported_knowledge` audit; readiness/route/nextmove read the honest absence of a path, never an invented `SUPPORTED` (`test_knowledge_provenance.py` §T2).

**No positive causality — legacy consequences are gated too (full Kleene)**: `UNSUPPORTED` = epistemic UNKNOWN, and an unknown state must not switch consequences in **either direction**. Therefore `apply_rule_consequences` only executes consequences (RAISE/LOWER/BLOCK/FLAG/IGNORE) from anchored matches; matches without verified anchors are skipped, recorded in `outcome.unsupported_rule_ids`, and the old confidence score **does not move because of them** — no delta, no re-sort, no flag/block, and the same for the entire downstream chain (ranking → arbitration → verdict → spectrum → advisory text only). The INFER seam (`rule_evidence_map` from `indicates`) only fills evidence that is **verified** from `support.evidence_ids` — invented ids never enter the mechanism map. The audit trail is honest: a `RULE MATCHED WITHOUT VERIFIED ANCHOR — consequence NOT executed` note, `rules_unsupported` vs `rules_consequence_eligible` in coverage. Proven by `evals/test_unsupported_causal.py`: score purity over every consequential KB rule, VALID→UNSUPPORTED flips (ledger ids vs invented), symmetric boost & penalty directions, INFER seam purity, 7-level spectrum navigation inertia, monotonic downgrade (≡ baseline, never exceeding it), and the none_of contract.

**The absence contract — absence of record ≠ evidence of absence (Task F, `rule_predicates.py` header)**: three layers, one rule.

| Layer | Rule |
|---|---|
| Tier-1 absence operators (`ABSENCE_OPERATORS`: `none_of`, `text_absent_pattern`, `evidence_level_absent`) | "Satisfied" = **no matching record** in the examined ledger + transcript: an *absence of record*, not proof the thing never happened in the world. It never carries anchors and never makes a rule match on its own (mandatory citation, T3). |
| Recording | Every satisfied **and relied upon** absence condition is recorded as `AbsenceAssumption{branch, operator, operand, basis=NO_MATCHING_RECORD}` (`RuleSupport.assumptions` → `Signal.assumes` → `provenance.assumed_absences` on paths and `provenance.candidate`; the readiness projection exposes `candidate.assumes_absence`; UI: "It also assumes nothing you told us points the other way. We have not confirmed that."). `all_of` relies on all its children; `any_of` only when no satisfied child is anchored. Recording only — it does not change SUPPORTED/UNSUPPORTED and adds no anchors. `min_evidence_count` is a count threshold, not absence. |
| Actual evidence of absence | Only a **positive branch** quoting evidence/quotes that *state* the absence (e.g. `text_contains_any ["belum pernah refund"]`): anchored like any other positive branch. `is_gap` evidence (missing data) is not evidence of absence, and a gap mention about X prevents assuming the absence of X. |
| Navigation (Kleene) | `{"not": X}` is TRUE only when X is **proven FALSE** (an anchored FALSE signal, e.g. a `REFUTED` mechanism with rebuttal evidence); X unknown → UNKNOWN; a `CONFLICT` mechanism → UNKNOWN (conflict is not absence); a rule is never FALSE (`rule_signal` only TRUE/None). |

**Tier-1 evaluator ≡ trace, order-independent (PROV-05)**: `evaluate_predicate` and `trace_predicate_audit` use the same leaves and must agree on `matched` for EVERY shape of `all_of`/`any_of`/`none_of`/nested leaves. The closure audit found a latent bug: `any_of` returned the FIRST satisfied child, so an unsourced constraint child placed before an anchored positive child made the rule rejected by mandatory citation (`any_of[none_of[X], A]` a false negative; `any_of[A, none_of[X]]` passed). Citations are now taken from the first satisfied child that *carries* one. Guarded by `test_candidate_closure.py` §D: 636 shapes × 9 ledgers, evaluator == trace and identical results when child order is reversed. No KB rule was affected (zero occurrences of `any_of` with a constraint child), so golden characterization did not shift.

The Revenue motions **stay alive** — as the `motion` attribute on `ontology/route/strategies.json` entries and as a valid, tested primitive collection (`test_revenue_navigation.py` §9). They do not define a path list, never appear in `core/`, and are not used by the UI as a key.

## 7. Route Template → Route (Strategy → Template → Route) — IMPLEMENTED

### 7.1 Ontology contract

```text
Strategy 1 ───► N RouteTemplate        one strategy may own many templates
RouteTemplate N ───► 1 Strategy        one template belongs to EXACTLY ONE strategy (`template.strategy_id`)
```

Rationale: route identity = `reconciliation_key {goal_anchor, strategy_id, scope_anchor}` (INV-R13/R14). `template_id` is not identity; a template shared across strategies has no single route meaning. Therefore **many strategies → one template is not allowed** (and therefore ROUTE-03 "a shared template keeps all relations" does not apply: that relation is invalid and fails). The composition direction is **strategy-first**: path → `route_substrate.template_ids` → template, never template → path.

- `PossibilitySpace` rejects templates claimed by two strategies (ROUTE-04, at construction).
- **Duplicate template protection (ROUTE-04b)** — banned at two layers, not "last write wins": `StrategySpec` rejects `route_template_ids` containing duplicate ids at write time (`ValueError`, naming the duplicated id); `plan_compositions` rejects a library/composition with duplicated templates (`RouteCompositionError`). The live audit guards the active library, the strategy registry, and the `template.strategy_id ∈ registry` relation: a template library with duplicate ids, a registry where two strategies claim the same template, or a template claiming an unregistered strategy = test failure (`test_route_composition.py` §live).
- `ontology/route/plan.plan_compositions(paths, library)`: every referenced template must exist in the library; `template.strategy_id == path.strategy_id` (ROUTE-02); one template may not be the substrate of two paths; a library with duplicate `template_id` is rejected. Violations = a deterministic `RouteCompositionError` (ValueError) — never "last write wins" in a dict. Results are ordered by `template_id`.
- `assert_route_keeps_strategy`: a born route must carry its source path's `strategy_id` in the `reconciliation_key` (ROUTE-01). Route payloads use the `strategy_id`/`path_id` from the **path**, not from a template lookup.
- Readiness merges routes into paths via strategy; **more than one route per path is rejected** (no projection semantics yet) — never silently overwritten; a route claiming another path is rejected. `_readiness_projection` never swallows `RouteCompositionError`.
- ROUTE-05: `route_id` (UUID, stable across recompositions), `revision_no` (graph revision), and `reopened_from` (a new route after a CLOSED lineage) are three different things, tested; `successor_of` (fork when the scope is raised) is only a contract in int 08 §8.2 — **NOT YET IMPLEMENTED**.
- Routes are composed only for surviving paths; a path without a template stays valid (`route_substrate.available=false`; path executability `UNKNOWN`, PATH-07). NextMove (selector v1) chooses only over non-`STOP` route paths (engine **or** user); a STOP route path still exists (exists ≠ surfaced).

**PARTIALLY IMPLEMENTED**: one strategy with N templates can be composed (the plan supports it), but readiness projection supports only one route per path (Revenue: one template per strategy).

### 7.2 The motion vocabulary is owned by the domain

The motion enum used to be hardcoded in the route engine (`compose.py`, `validate_route.py`, `route_schema.json`). The motion label vocabulary is now **declared in the strategy registry** (`ontology/route/strategies.json#motion_vocabulary`) and read by the engine (`strategies.load_motion_vocabulary`); the schema only points to it (`domain_vocabularies`). A new domain adds labels in the registry without touching route code/schema. **IMPLEMENTED.**

## 8. Requirement Registry — the single source, and Requirement Presentation

`ontology/registry/requirement_registry.json` (49 entries; contract in int 09) carries: `requirement_id`, `definition`, `observability`, `satisfaction_rule`, `provenance`. Loader: `engine/requirements.py`.

**Presentation** (`ontology/registry/requirement_presentation.json`, guarded by `validate_presentation.py`) = display text per language, keyed by `requirement_id`: `title`, `description` (optional), `verification`. The registry schema is locked (exactly 5 layers) — so presentation is a **separate layer**, not a new column. A requirement without curated text is still readable through the **deterministic fallback from registry semantics** (`core/navigation/presentation.py`): `title` ← the id words (`commercial.pricing_basis` → "Pricing basis"), `description` ← `definition`, `verification` ← `observability`. Every field carries `source` (`curated|fallback`) and `lang`. The fallback never invents domain copy.

**Invariant**: adding a requirement to the registry **requires no Readiness code changes** (`test_readiness_universal.py` §3 and `test_domain_extensibility.py` inject requirements absent from both pack and code). The `REQ_EN` dictionary and the `GATE_REQ` mapping are **deleted**. **IMPLEMENTED.**

## 9. Path checks and requirement anchors

A path judges world conditions through **checks**: a stable `check_id` (an id, not a sentence) + `signal` + `kind` (`prereq|hard`) + optional `requirement_id` (an anchor to the registry when an identical requirement exists). The check ↔ requirement relation is **declared by the machine** (`ontology/possibility/revenue.json`, validated against the registry), never derived from string matching. Human sentences (title, unlock, reason) are per-language **presentation** shipped along (`i18n`), never the logic key.

## 10. Readiness Projection (`core/navigation/readiness.py`, `PROJECTION_VERSION` = 4)

Readiness **consumes**; it never determines what a requirement means. Input: PathSet + the user's routes + `describe` (registry + presentation) + current lifecycle + language. Per path: `status`, `feasibility`, `lifecycle`, `applicability`, `stop_provenance`, `route{…}`, `executability` (TRUE/FALSE/UNKNOWN; `null` = nothing left), `items[]`, `conflicts[]`, `counts`, `narrative`. At the projection level: `navigation` (§11), `paths`, `unresolved`, `generation`.

Per item: `key` (= `requirement_id` or `check_id`), `state`, `sources` (`route|check`), `executability` (node), `title/guidance/reason/unlock` (text + `lang`), `evidence` (anchors `ledger:` / `check:` / `ev:`), `waits_on`, `settled`/`conflict` (below). No scalar score; `counts` are plain item counts.

### 10.1 Adjudication and conflicts — decision: structured metadata, not a fifth state — IMPLEMENTED

Route nodes and path checks pointing at the same `requirement_id` are merged into one item. A definite state beats `UNKNOWN`. When both are definite but **disagree** (e.g. node `PRESENT` from the adjudication ledger vs check `ABSENT` from a state signal):

| Aspect | Decision |
|---|---|
| Source | route node = state from the **adjudication ledger** (registry satisfaction rules over tiered evidence); path check = a signal read over state |
| Authority | the adjudication ledger is more authoritative → the projected node state (`resolved_to`) |
| Recorded | `conflict = {sources{route,check}, check_id, authority:"route", resolution:"AUTHORITY", resolved_to, note{text,lang}}` + `settled=false` |
| Impact | never counted as proven in `counts` (`conflicted` separate; all buckets + `conflicted` = `total`); the UI treats it as "not settled"; narrative may only claim it as `CONFLICT` (§13) |

Why **not** a `CONFLICT` value on `Satisfaction`: conflict is a dispute between **readers**, not a world state; adding it to the enum breaks the locked registry/adjudication contract, and the same pattern is already used by the evidence adjudicator (`core/stages/adjudicate.py` D-A1a/b: conflicts resolved into the 4-state enum with both sides recorded). `UNKNOWN` vs definite is **not** a conflict. No scalar score; OPEN ≠ READY.

**Node state source (M4, 2 Oct 2026).** In a live session, route node `satisfaction` is now fed from **live adjudication** (§25.4) through the same single reader as the Question Planner (§25.3); node↔check merging uses `requirement_state.merge_readings` — one rule for Readiness and the session reader. Routeless paths with requirement-anchored checks now also read the ledger through the same reader (M4.1): `build_projection(…, state_reader=status_reader(reader))`, ledger authority, no second evaluator.

**Feasibility follows the same canonical rule** (`canonical_feasibility`, `readiness.py`): when an adjudicated route node definitively reads a requirement that a path check reads `ABSENT`/`PARTIAL`, every disputed check contributes `UNKNOWN` to the **same** `feasibility_from_checks` the engine used at diagnosis — a disputed hard check is not `CONTRADICTED` (STOP), support via a disputed check is not `SUPPORTED`. The engine's raw reading stays audited in `feasibility_engine` (a projection audit field). One rule for readiness **and** NextMove — not two evaluators that can disagree. (The old debt "feasibility is not recomputed from adjudicated state" is PAID here; `PROJECTION_VERSION` rose to 4 for this semantics.)

### 10.2 Tiered executability and applicability

Node: `any(ABSENT|PARTIAL) → FALSE`, `any(UNKNOWN) → UNKNOWN`, otherwise `TRUE` (int 08 §3.4). Path: `TRUE` when an executable node exists; `UNKNOWN` when routeless or the route is `UNDETERMINED`; `FALSE` when everything remaining is blocked; `null` when the route is satisfied. A route applicability of `UNDETERMINED` maps to `UNKNOWN` (never `APPLIES`).

## 11. LEGACY artifacts and schema versions (DATA-01..03) — IMPLEMENTED

Artifacts stored before the current navigation schema (`revenue_paths` with five fixed routes; or a diagnosis without a PathSet; or a different PathSet version) **do not** carry trustworthy path results. Reading them as `paths=[]` would masquerade as an engine finding ("verified state supports no path"). Real repo data at audit time: of stored sessions with a diagnosis, the majority used `revenue_paths` or had no path projection — these artifacts used to display as "no paths".

```text
PathSet version = PATHSET_VERSION (3)                    ─► navigation.status = CURRENT  (0..N paths is an engine finding)
PathSet missing / other version / CONTENT UNREADABLE     ─► navigation.status = LEGACY   (needs_rediagnosis = true)
```

- `core/navigation/compat.assess_path_set` → `{status, needs_rediagnosis, reason_code (PATHSET_MISSING | SCHEMA_VERSION_MISMATCH | PATHSET_MALFORMED), found_version, current_version, detail, i18n}` (text from the engine). Corrupt content (`paths` not a list; entries not dicts; `path_id` not a non-empty string) → `PATHSET_MALFORMED`. `assess_path_set` is the SINGLE trust decision point: only a PathSet assessed CURRENT has its content read downstream (`build_projection` reads content only when CURRENT), so corrupt content can neither 500 downstream **nor** masquerade as an engine finding of "zero paths".
- `DiagnosisArtifact.navigation` (computed field, derived on every read from `possible_paths`; the copy saved into the session JSON is ignored on load) → `GET /session/{sid}/diagnosis`; the readiness projection carries `navigation`; `POST /routes` returns an "older artifact" reason (not "no paths yet"); reporting an outcome on a LEGACY artifact path → 409.

**The same rule binds the browser readers (one reality all the way to the client)**: the timeline map, readiness pills, and NextMove UI read the **adjudicated projection** (`navigation.status === 'CURRENT'` → per-path status from `projection.paths`); the raw PathSet snapshot is only a fallback when the projection is absent, and the `STOPPED` lifecycle overlay (user decision) sits above both (`pathStatusOf` in `app/static/js/live.js`). Patching one layer alone never moves the UI — that is by design: a state the engine did not assess cannot display as a finding just because it was injected at the raw layer. A session loads in order state → evidence → artifacts → journey → workspace → routes → **readiness last**, so persisted state comes only from an intact session; a readiness screen that arrives before its data fetches on its own (fetch-on-null), never displays emptiness as a finding.
- **No automatic migration** — intentional: old paths were born from fixed lists/string gates without provenance mappable to strategies + evidence anchors; guessing a migration means inventing. The honest path = re-diagnose over the same evidence (the check-in cycle).
- The UI distinguishes: "We cannot name a path yet." (an engine finding, with a reason) vs "This map needs a fresh look." (a LEGACY artifact); a LEGACY baseline is not a comparison baseline. Narrative (`explain`/`ask`) is told there are no path results, not "zero paths".
- Versions: `PATHSET_VERSION` 3 (bumped because rule provenance is now anchored), `PROJECTION_VERSION` 4 (bumped because projection feasibility is now the adjudicated reading — §10.1). Pre-hardening v2 artifacts become LEGACY.

## 12. Lifecycle and the semantics of STOP

`STOP` is a **reader word** with two origins kept separate in `stop_provenance`: `ENGINE_CONTRADICTION` (feasibility `CONTRADICTED`, with the causing `check_id`) and `LIFECYCLE` (user decision/outcome — `regret` → `STOPPED`, `moved` → reopen; `domains/revenue/stages/reroute.py`, state key = `path_id`). A single `STOP` enum for both **does not exist**. Lifecycle never overrides feasibility (ROUTE-03): a user-STOPped path still carries its engine feasibility. `PAUSED` and `CLOSED` are part of the contract; `CLOSED` is used by route lifecycle, `PAUSED` has no producer yet (**NOT YET IMPLEMENTED** as a producer). NextMove is never chosen from a STOP route path, whatever the origin.

## 13. Grounded narrative

The LLM proposes; the engine decides. For state fields (`supported`, `holding`, `unclear`) the LLM must carry **anchored claims**:

```text
Narrative Claim
├── claim               the claimed clause
├── claim_type          SUPPORTED | PARTIAL | MISSING | UNKNOWN | CONFLICT
├── requirement_anchor  the projection item key
├── evidence_anchor     the item's evidence anchor (taken from the PROJECTION, not from the LLM)
└── support_state       the item's state per the projection
```

`core/navigation/claims.py` rejects: claims without an anchor; anchors outside the path; `SUPPORTED` on an item that is not `PRESENT` or has no evidence; `MISSING` on `UNKNOWN` (UNKNOWN ≠ ABSENT); claims that reverse a state; **any claim other than `CONFLICT` on a conflicted item** (a dispute is never stated as settled fact) and `CONFLICT` on an item without conflict. **Merely having another `PRESENT` item on that path is not enough.** Narrative fields without anchored claims are dropped; the deterministic fallback (`core/navigation/narrative.py`) is built from the same items and produces grounded-by-construction claims (conflicted items enter the `unclear` field as `CONFLICT` claims). The text layer (`domains/revenue/guards/readiness_grounding.py`) still rejects population/comparison claims and "not known yet" voiced as a failure. The claim × {PRESENT, PARTIAL, UNKNOWN, ABSENT, CONFLICT} matrix is tested in `test_navigation_semantics.py`. **IMPLEMENTED.**

The LLM **may**: interpret language, propose wording/candidates, explain verified state. The LLM **may not**: create state, decide satisfaction, override route applicability/validity, invent evidence, downgrade `UNKNOWN` into `PRESENT`, or shape routes.

## 14. Domain Plugin Boundary

| Layer | Generic (engine; `core/navigation`, `core/stages`, and for routes `ontology/route`) | Domain plugin |
|---|---|---|
| Contracts | enums, `StrategySpec`, `Signal`, `PathSet`, `RuleSupport` | — |
| Emergence | Kleene predicates, generator, `grounded`, `rule_signal` | `emerges_when` in data; signal readers |
| Evaluation | evaluator, `display_status`, lifecycle | `checks` in data; `requirement_id` to the registry |
| Route | `plan_compositions` (strategy-first), composer | templates; motion labels in the strategy registry |
| Readiness | projection, adjudication, conflicts, executability, narrative fallback | `describe` (registry+presentation), lifecycle hooks |
| Narrative | anchored claims | per-language wording/lexicon guards |

Mechanically guarded: `evals/test_core_scope.py` (no domain identity in `core/`; every `core/` file classified), import-linter (`core` may not import `domains`), `test_navigation_universal.py` (core contains no Revenue motions/vocabulary), and `test_domain_extensibility.py` (a full fictional-domain chain loads no Revenue module). **IMPLEMENTED.**

## 15. Model for extending to a new domain

1. Declare a `PossibilitySpace` (strategies: `emerges_when`, `not_applicable_when`, `checks` or `no_preconditions`) — data, not core code.
2. Write a `SignalReader` mapping domain state to tri-state signals (`None` when unknown) with real `refs` and `i18n`; `rule:` signals go through `rule_signal(rule_id, RuleSupport)`.
3. (Optional) Route templates for those strategies (`template.strategy_id`); without a template a path stays valid. Motion labels (if used) are added to `strategies.json#motion_vocabulary`.
4. New requirements enter the **registry** (+ curated presentation when available); Readiness does not change.
5. Validators (`validate_possibility.py`, same pattern) reject orphan signals, requirements not in the registry, and strategies without an emergence basis.

The synthetic SaaS, B2B, and "hiring" domains in `evals/navigation_fixtures.py` prove steps 1–2 (including evidence → rule → mechanism → strategy → path) without touching `core/`. **IMPLEMENTED.**

## 16. Examples

**Revenue** — `RevenueState(current_monthly=30, target=60, capacity_utilization=0.86, willingness_to_pay=PROVEN)`: `value_repricing` **OPEN** (SUPPORTED), `client_expansion` **OPEN**, `direct_outreach` **NOT_YET** (CONDITIONAL: capacity full), `referral_partnership` **NOT_YET**, `paid_channel_test` **TEST_FIRST** (UNDETERMINED: 3 evidence missing). WtP proven negative → `value_repricing` **STOP** with `stop_provenance=[ENGINE_CONTRADICTION: willingness_to_pay]` and lifecycle still `OPEN`; the user reports `regret` → **STOP** with `[LIFECYCLE]`, engine feasibility unchanged.

**SaaS** — many sign-ups + weak activation + a revenue goal → `path.activation_first`, `motion=null`; `scale_acquisition` does **not** get born. Provenance: `state:weak_activation`, `state:many_signups` + supporting evidence ids.

**B2B** — many leads + poor decision-maker access → `path.decision_maker_access` with check `access.decision_maker` (registry requirement); `lead_qualification` exists without a route template (a path is valid without a route), feasibility `UNDETERMINED` because it has no checks.

**Knowledge-driven (synthetic "hiring")** — evidence `no rubric` (ev-hr-1) and `subjective scoring` (ev-hr-2) satisfy rule `HR-R1` (`all_of`: branch A → ev-hr-1, branch B → ev-hr-2); the `inconsistent_hiring_bar` mechanism is detected from ev-hr-2; strategy `structured_interviews` declares `emerges_when: all_of[rule:HR-R1, mechanism:inconsistent_hiring_bar]` → `path.structured_interviews` with correct `knowledge_support` and evidence anchors, no Revenue vocabulary.

**Zero paths** — a Rp20 million goal with no revenue numbers: `paths=[]`, `unresolved=[INSUFFICIENT_VERIFIED_STATE, missing: state:existing_revenue, state:revenue_gap, …]`, `navigation.status=CURRENT`. UI: "We cannot name a path yet." + what is not yet known. No path is invented to fill the screen.

**Old artifact** — an old session with `revenue_paths`: `possible_paths=null`, `navigation.status=LEGACY`. UI: "This map needs a fresh look." — not "zero paths".

## 17. Failure modes

| Failure mode | Guard |
|---|---|
| A path invented to fill the UI | `validate_path_set`: zero paths must carry `unresolved`; paths must carry support provenance |
| An "active" rule without evidence becoming support | `rule_signal` + `grounded` (PROV-02); `validate_path_set` rejects knowledge without an anchor; `test_knowledge_provenance.py` |
| Invented tier-2 citations | `support_from_citation` verifies against the ledger/transcript |
| A typo'd signal silently becoming UNKNOWN | `validate_possibility.py` (every signal must be declared by a reader) |
| `all([])` / `all_of: []` silently TRUE | `feasibility_basis`; empty operands rejected; `test_navigation_semantics.py` |
| A new requirement breaking readiness | registry fallback (`test_readiness_universal §3`, `test_domain_extensibility`) |
| A narrative claim of "already there" for UNKNOWN or a conflicted item | `ground_claim` + `check_grounding` (§13) |
| Motion leaking into identity/UI | `path_id` from the strategy; the UI reads `possible_paths`; core isolation tests |
| A route built for a nonexistent path / changed strategy / overwritten | `plan_compositions`, `assert_route_keeps_strategy`, `test_route_composition.py` |
| An ambiguous STOP origin | `stop_provenance`, two sources |
| An old artifact read as "zero paths" | `assess_path_set` / `navigation` (§11) |
| An outcome attached to an invented path | `_require_known_path` (422; 409 for LEGACY artifacts) |
| A positive candidate born from UNSUPPORTED knowledge (directly, via a derived mechanism, or via the score) | `rule_signal` → `Signal(None, unsupported)`; `MechanismOverlay` never activates from a basis-less signal; `grounded`; `test_candidate_possibility.py` §F (UNSUPPORTED ≡ absent rule for paths, readiness, routes) |
| Two contradicting knowledge entries silently picked | `MechanismSpec.contradicted_by`: explicit support AND rebuttal = a `CONFLICT` mechanism, its candidates `UNDETERMINED` + `conflicts` in the audit; never a path |
| A candidate presented as a Possible Path (shown as a road) | UI: a separate "Taking shape" card (dashed, neutral pill); projection `emerging` ≠ `paths`; Ask/Explain read out "NOT a path" |
| Candidate provenance lost at promotion | `provenance.candidate` (candidate_id, mechanisms, knowledge, evidence) + `validate_path_set` rejects candidate-paths without mechanisms/anchors |
| Inventing Revenue knowledge | `validate_possibility.py`: mechanisms must exist in the catalog, KB interventions must exist and their `targets` must intersect the mechanism's constraints |
| The generator judging (reading checks/exclusions/template patterns) | `Proposal` is the only thing the generator sees; AST guards + generation invariance tests (`test_candidate_closure.py` §A) |
| `requires` read as a Requirement | replaced by `context_when` (emergence context, not a requirement); the validator rejects the old key with an explanation |
| A sibling-mechanism dispute vanishing while a candidate stays SUPPORTED via an independent branch | the dispute is carried onto the candidate, the audit says PROMOTED, `provenance.candidate.conflicts`, readiness `candidate.unsettled`, the Ask/Explain row "NOT settled and NOT part of that reason" (§B) |
| A reason ("why") narrating a disputed mechanism | `because` is curated per mechanism (only ACTIVE ones) or falls back to active mechanisms (`readiness._because`) |
| Absence of record displayed as verified absence | `AbsenceAssumption` → `assumed_absences` / `assumes_absence`; Kleene `not` only from proven FALSE (§6.1, §C) |
| The tier-1 evaluator depending on child order (evaluator != trace) | §6.1 PROV-05; 636 shapes × 9 ledgers (§D) |
| Candidate-paths treated differently downstream (route/readiness/NextMove) | one `compose_path_routes` pipeline; golden: candidate-born == declared-strategy, detaching a candidate block changes nothing, the route modules' AST never mentions candidate |
| Ghost paths/routes/NextMove after evidence is revoked | everything is recomputed from current evidence; old route lineage stays in the store (exists != surfaced), is never presented, and is reused if the evidence returns (golden §C) |
| The UI silently dropping paths, or implying "only five" | presentation cap + "+N other possibilities" on every screen (the zero-open map used to hide the 5th path without a word); wording guarded by `presentation-cap.spec.mjs` |
| An LLM prompt truncating paths without saying so | `PATHS_CAP` (the prompt budget) is announced to the LLM; the LLM may not state a path count |

## 18. Knowledge → Mechanism → Strategy: deliberate boundaries, and what does NOT exist

The existing contract (**IMPLEMENTED**): knowledge enters as signals (`rule:`, `mechanism:`) with anchored provenance; a **strategy** declares explicitly in its data (`emerges_when`) which knowledge signals make it a candidate (KNOW-03: explicit mapping, no magic). In Revenue, mechanism → strategy exists and is real (`pricing_avoidance_loop → value_repricing`, `trust_gap → referral_partnership`, `insufficient_pipeline → direct_outreach`). Since 1 Oct 2026 there is also a path **without a strategy list**: knowledge → mechanism → Candidate Possibility → path ([§23](#23-knowledge--mechanism--candidate-possibility)).

| | Status |
|---|---|
| `rule:` signals with evidence anchors, generic for any domain | **IMPLEMENTED** |
| Evidence → Knowledge → Mechanism as a **derivation chain** (a rule produces a mechanism, `MechanismSpec.activated_by`), generic | **IMPLEMENTED** (§23) — proven on the synthetic "growth" and "hiring" domains |
| Mechanism → Candidate Possibility → Possible Path without a strategy list (`PossibilityPattern`), generic | **IMPLEMENTED** (§23) — proven on Revenue (3 patterns from real catalog mechanisms) and synthetic domains |
| The `rule → mechanism/strategy` edge for **Revenue** | **NOT IMPLEMENTED BY DESIGN** — Revenue KB rules modulate constraints/confidence; they neither propose methods nor activate mechanisms; no ontology is tight enough to map them honestly. Revenue mechanisms remain **detected directly from evidence** (catalog keywords); Revenue patterns rely on existing mechanisms + KB interventions. |
| Candidates from the LLM | **NOT YET IMPLEMENTED** — the contract is ready (the LLM may propose; proposals must pass the same verification as patterns: anchored mechanisms, the evaluator), not yet wired |

The existing interfaces do **not** make this architecture "complete": the knowledge-driven chain as a full derivation is only proven on synthetic domains (`test_candidate_possibility.py`, `test_domain_extensibility.py`, E2E fixtures `paths_candidates`, `paths_knowledge`); on Revenue it is proven from detected mechanisms to paths.

## 19. Tests (map)

| Test | Proves |
|---|---|
| `evals/test_navigation_universal.py` | generator/evaluator separation; 0/1/2/5/10 paths; SaaS, B2B, zero paths; provenance; Kleene; domain isolation |
| `evals/test_candidate_possibility.py` | CAND-01..08: knowledge → derived mechanism → Candidate Possibility → evaluation → Possible Path. The 0/1/2/N candidate matrix, duplicates (two mechanisms → one candidate), same mechanism different candidate, merging with declared strategies; `all_of`/`any_of`/`none_of`/nested; UNKNOWN ≠ ABSENT; UNSUPPORTED ≡ absent rule for paths/readiness/routes/NextMove; conflicts (explicit support + rebuttal) never silently picked; reverse lineage (revoke evidence → the candidate vanishes); monotonicity over 16 evidence subsets; routeless vs routed + four separate identities; LEGACY stays LEGACY; readiness `emerging`/`why`; Ask/Explain distinguish verified/unknown/conflict/unsupported; synthetic growth & hiring domains without `StrategySpec`; core isolation (AST: no domain imports, no Revenue identity); real Revenue (3 patterns from catalog mechanisms + KB interventions) |
| `evals/test_candidate_closure.py` | Closing the candidate layer, all through production code: **A** generation boundary != evaluation (generation invariance over the evaluation substrate, AST guards, `context_when` is not a requirement); **B** disputes never vanish in candidates/audit/paths/readiness/narrative; **C** absence of record != verified absence (absence alone, explicit evidence of absence, UNKNOWN, conflict, nested none_of, gap evidence); **D** evaluator == trace over 636 shapes × 9 ledgers, order-independent; **E** promotion and identity (`cand.*` / direction / `path.*`, dormant strategies + patterns, no overwrite/duplicates); **F** 0..N cardinality (0,1,2,3,4,5,6,8,10,13) on a third synthetic domain + the LLM prompt budget disclosure; **G** Revenue: five motions = vocabulary, not universe (1, 3, 5, 8 paths) |
| `evals/test_candidate_golden.py` | **Golden Candidate-born** end-to-end: evidence → tier-1 rule → mechanism → candidate → evaluation → path → the REAL route composer → readiness (canonical state: the adjudication ledger) → NextMove; reverse lineage (revoke/invalidate evidence → no ghost path/route/NextMove; evidence returns → the route is reused); downstream never distinguishes origin (candidate-born == declared-strategy, detaching a candidate block, route module AST); Revenue over real HTTP (path.direct_outreach born two ways: identical route + NextMove + readiness); the API returns 0..13 paths intact; **H** conflict + a REAL route (a two-mechanism path stands via an independent branch: the dispute is recorded in provenance/readiness `unsettled`, not support, while route/NextMove are IDENTICAL to the conflict-free world and the route module never mentions `conflicts`/`unsettled`; without the independent branch: a CONFLICTED candidate, zero routes/NextMove) |
| `evals/test_knowledge_provenance.py` | PROV-01..04: scenarios A–D (E1→R1→S1; A AND B; A OR B; basis not formable → rejected), tier-2, gaps, transcripts, the trace ≡ evaluator property over every tier-1 KB rule |
| `evals/test_unsupported_causal.py` | UNSUPPORTED zero positive causality: `apply_rule_consequences` score purity over every consequential KB rule; VALID→UNSUPPORTED flips (ledger ids vs invented citations); symmetric boost & penalty directions; the INFER seam's anti-invention; 7-level spectrum navigation inertia (UNSUPPORTED ≡ absent for paths, ≠ in the audit); monotonic downgrade (score ≡ baseline, never exceeding it); the none_of contract (absence is not support; explicit absence may be) |
| `evals/test_route_composition.py` | Strategy→Template→Route: identity preserved, shared templates rejected, N templates, routes never overwritten, a stable `route_id`, NextMove × STOP (engine/user), HTTP E2E |
| `evals/test_navigation_semantics.py` | reading conflicts, the claim × 5-state matrix, "no checks" ≠ viable, vacuous predicates, LEGACY artifacts (a real store + HTTP) |
| `evals/test_domain_extensibility.py` | a new domain (state+knowledge+mechanism+strategy+requirement+template) without touching core; the Revenue/SaaS/B2B/zero matrix |
| `evals/test_revenue_navigation.py` | the Revenue plugin; mechanisms birthing strategies; ENGINE_CONTRADICTION vs LIFECYCLE; motion as a primitive |
| `evals/test_readiness_universal.py` | all 49 requirements projected; new requirements; no `REQ_EN`/`GATE_REQ` dictionaries (deleted; tested absent); three axes; UNKNOWN≠ABSENT |
| `evals/test_readiness_grounding.py` | the claim matrix; adjudication; conflicts; lifecycle; fallback; endpoints |
| `evals/test_routes_endpoint.py` | routes only for surviving paths; zero paths without routes |
| `evals/test_ui_fixtures.py` + `evals/make_ui_fixtures.py` | UI fixtures = the real current engine output (0/1/8 paths, Revenue five, knowledge, engine/user STOP, LEGACY, UNKNOWN/PARTIAL/satisfied, registry-only requirements) |
| `ontology/registry/validate_presentation.py`, `ontology/possibility/validate_possibility.py`, `ontology/route/validate_route.py` | presentation/possibility/route with no orphans, with negative tests |
| `e2e/paths.spec.mjs` | UI: 0/1/8 paths (eight = the engine forms eight; the map draws five + overflow), UNKNOWN/PARTIAL/satisfied, new requirements, engine vs user STOP, LEGACY, knowledge, the five Revenue paths; light/dark, 390px; a11y; no raw tokens |
| `e2e/candidates.spec.mjs` | Candidate Possibility UI: candidate-paths routeless/routed/among the five Revenue paths carry a reason ("Why this is on your map", openable); sibling disputes and "relying on the absence of a record" display beside the reason, never as the reason; new possibilities (one fact short / disputed / without a basis) appear on the separate "Taking shape" card and never become a lane; LEGACY reads no content; keyboard Enter/Space + focus rings; light/dark/390px; axe WCAG A+AA; 0 console errors, 0 failed requests |
| `e2e/presentation-cap.spec.mjs` | **Presentation cap**: pure policy (`present-cap.js` loaded as-is; 0..13 and 40 paths, pinning, order, determinism, no filler/no loss); the UI for 0/1/3/5/6/8/10 on the map, the readiness list, the diagnosis card, reveal; honest wording (never "only/best/top"); the overflow list, selecting a hidden path, keyboard-only (Enter/Space/Tab) + focus rings; hidden candidate-paths still carry "why"; the zero-open map announces the rest; light/dark/390px; axe WCAG A+AA; 0 console errors, 0 failed requests |
| `e2e/accessibility.spec.mjs` | UI-03: keyboard-only — Tab reachability of lanes/modal, `:focus-visible` rings, Enter/Space activates lanes & radio-cards (query-by-label: activation re-renders), the STOP flow via keyboard, dark+390px, zero console errors |
| `evals/test_m4_applicability.py` | **M4** Applicable Requirement Set + Requirement State Reader: applicability from context (A), registry extensibility (B), UNKNOWN ≠ ABSENT (C), requirements without context are not members (L), candidate-born and optional routes (M, N), one merge rule with Readiness over the full matrix, the ledger is authoritative + conflicts = metadata, applicability ≠ navigable |
| `evals/test_m4_live_adjudication.py` | **M4** live adjudication: the mapper only proposes (D), UNKNOWN ≠ ABSENT (C), ledger → reader → route (E), user scoping (35), idempotency, gap evidence never admitted, one write door (AST), stale formal rules, honest formal coverage |
| `evals/test_m4_planner.py` | **M4** Question Planner: four step kinds (F), goal (S0), applicability uncertainty (G, G4), contradiction (H), ready-to-act (K), no-relevance (L), registry extensibility (B), dependencies A → B → C, uncertainty-driven (no phases/fixed order; input permutations), the loop guard (`ASK_CAP`), ASK/ACT channels, direction changes (J), 0..N paths + optional routes, emergence, language, reason trail + replay + digest (R1–R10), structural invariants (no LLM/ranking/phases) |
| `evals/test_m4_session_loop.py` | **M4** state loop E2E over HTTP (mock provider): the full loop (O), free order (I), direction changes (J), candidate-born (K), HOLD, scoping + anonymous sessions (35), persistence + replay + condensed logs (P), API compatibility + phases never gate (X), finalize + one Readiness↔planner reader (F, F3b, F3d, F3e), fail-safe (FS) |
| `evals/test_m5_phase_removal.py` | **M5** INV-7 guard: AST over ALL production code — zero phase-engine identifiers; old files/symbols absent; API and persistence without `phase`; old data reads without effect; phases/topics/turns never gate (negative property); rule activation + domain E2E intact (§26). Replaces `test_m4_no_phase_authority` (M4: "present but not an authority") |
| `e2e/conversation.spec.mjs` | **M4** state-driven conversation UI: the first step + reason one click away, free order, the "ready" card, sessions never locked, reload restores, light/dark/390px, HOLD, zero console errors; visual baselines `conv-*.png`; axe WCAG A+AA |
| `e2e/live.spec.mjs`, `e2e/tokens.spec.mjs`, `e2e/copy.spec.mjs`, `e2e/parity.spec.mjs` | drawer/modal/escape; theme tokens; copy; prototype parity |

## 20. Superseded documents and the term map

> The full classification of every document (CANONICAL / SUPPORTING / HISTORICAL / RESEARCH / TEST) and the reading order: `15-documentation-canonicalization.md`. The table below only covers terms and artifacts superseded by this architecture.

| Old document / term | Status | What applies now |
|---|---|---|
| "5 canonical routes = Possible Path" (`02-product-concept/03` §4.5, `06-history-frontier/07`, `04-skenario-uji`) | **SUPERSEDED** for definition; HISTORICAL for history | chapters 2, 4–6 of this document |
| `revenue_paths` (artifact) | removed; artifacts carrying it = LEGACY (§11) | `possible_paths` |
| Path key = motion (`ACQUISITION`…) | removed | `path_id = path.<strategy_id>` |
| `REQ_EN`, `GATE_REQ`, string gates as keys | removed | registry + presentation + `check_id` |
| `ELIGIBLE / CONDITIONAL / NOT_YET / BLOCKED` (gate statuses) | replaced | `Feasibility` + `Lifecycle` → `display_status` |
| `stages/paths.py` (`build_revenue_paths`) | removed | `domains/revenue/navigation/` + `ontology/possibility/revenue.json` |
| `CANONICAL_PATHS` / `CANON_PATHS` (path_states) | removed | the `path_id` syntax (`PATH_ID_RE`) |
| The motion enum hardcoded in the route engine | removed | `strategies.json#motion_vocabulary` (§7.2) |
| `ontology/route/strategies.json` (strategy registry) | stays (route contract) | `motion` = domain primitive |
| `disagrees_with_check` (a free flag) | replaced | structured `conflict` + `settled` (§10.1) |
| `all([])` ⇒ `SUPPORTED` | replaced | `feasibility_basis` (§5.1) |
| `PossibilityPattern.requires` | replaced 1 Oct 2026 (collided with Requirement) | `context_when` (§23.2, §24.2); the validator rejects the old key |
| The v9 "five routes" prototype/demo | **DEMO** (an illustrative story, not a contract) | see `07-design/v9-mvp-port-implementation.md` |

## 21. Implementation status per invariant

| Invariant | Status | Evidence |
|---|---|---|
| PATH-01 paths not from a fixed list | IMPLEMENTED | generator + `test_navigation_universal` |
| PATH-02 motion = domain primitive | IMPLEMENTED | core without motions; vocabulary in the registry |
| PATH-03 generation ≠ evaluation | IMPLEMENTED | two separate modules |
| PATH-04 paths carry provenance | IMPLEMENTED | `validate_path_set` |
| PATH-05 zero paths valid | IMPLEMENTED | `unresolved` mandatory |
| PATH-06 applicability ≠ readiness | IMPLEMENTED | separate axes |
| PATH-07 paths need no template | IMPLEMENTED | `route_substrate.available=false` |
| PATH-08 strategy identity survives to the route | IMPLEMENTED | `plan_compositions`, `assert_route_keeps_strategy` |
| KNOW-01 matched knowledge anchored | IMPLEMENTED | `RuleSupport`, `grounded` |
| KNOW-02 knowledge never invents evidence | IMPLEMENTED | anchors verified against the ledger/transcript (tier-2: condition matching remains an LLM judgment) |
| KNOW-03 explicit knowledge→strategy mapping | IMPLEMENTED (mechanisms, generic rules); Revenue rule→strategy NOT IMPLEMENTED BY DESIGN | `emerges_when`; §18 |
| KNOW-04 core without domain knowledge | IMPLEMENTED | `test_core_scope`, import-linter |
| PROV per-branch lineage end-to-end (Evidence → BranchSupport → RuleSupport → Signal → Candidate → Path, + reverse direction) | IMPLEMENTED | `test_knowledge_provenance` §LINEAGE |
| Tier-2 `UNSUPPORTED` never positive support at any navigation boundary (rule_signal/path/readiness/route/nextmove) | IMPLEMENTED | `test_knowledge_provenance` §T2 |
| ROUTE-04b duplicate templates banned in authoring + composition + live audit | IMPLEMENTED | `test_route_composition` §live |
| DATA-03b corrupt content → `PATHSET_MALFORMED`→LEGACY; no 500, never masquerading as "zero paths" | IMPLEMENTED | `test_navigation_semantics` §C |
| UI-03 keyboard: Tab reachable, Enter/Space operable, `:focus-visible` ring, Escape closes overlays (light/dark, 1440/390px) | IMPLEMENTED | `mvp/e2e/accessibility.spec.mjs` (5 tests; the a11y axe suite in live.spec stays green) |
| CAND-01 candidate generation ≠ candidate evaluation | IMPLEMENTED | separate `generate_candidates` / `evaluate_candidates`; `test_candidate_possibility` §B |
| CAND-02 candidates must carry provenance down to evidence | IMPLEMENTED | `provenance.candidate` + `validate_path_set`; §E |
| CAND-03 UNSUPPORTED knowledge produces no positive candidate support | IMPLEMENTED | `MechanismOverlay`, `grounded`; §F |
| CAND-04 Candidate ≠ Possible Path | IMPLEMENTED | candidate status (`SUPPORTED/UNDETERMINED/NOT_EMERGENT`) ≠ path status; the evaluator may discard (`REJECTED_NOT_APPLICABLE`); §B |
| CAND-05 candidates/paths can exist without a Route | IMPLEMENTED | `route_substrate.available=false`; §I |
| CAND-06 promotion preserves provenance + separate identities | IMPLEMENTED | `candidate_id` ≠ `strategy_id` ≠ `path_id` ≠ `route_id`; §E, §I |
| CAND-07 the candidate layer is domain-independent | IMPLEMENTED | generic `candidate.py`; AST + sys.modules; §L, §M |
| CAND-08 the candidate layer never changes the frozen navigation semantics | IMPLEMENTED | `PATHSET_VERSION`=3 and `PROJECTION_VERSION`=4 unchanged (additive fields only); all old tests green |
| CAND-09 a candidate is a proposal only; the generator sees only `Proposal` (never checks/exclusions/pattern templates) | IMPLEMENTED | `Proposal`, `PossibilityPattern.proposal`; `test_candidate_closure` §A (invariance + AST) |
| CAND-10 sibling-mechanism disputes never vanish while a candidate stays SUPPORTED | IMPLEMENTED | `CandidatePossibility.conflicts`, `provenance.candidate.conflicts`, readiness `candidate.unsettled`; §B; `candidates.spec` 03b |
| CAND-11 absence of record != verified absence; absence assumptions recorded, never anchors | IMPLEMENTED | `AbsenceAssumption`, `assumed_absences`; §C; `candidates.spec` 03c |
| CAND-12 one pipeline path -> route -> readiness -> NextMove; downstream never distinguishes path origin | IMPLEMENTED | `ontology/route/path_routes.compose_path_routes`; `test_candidate_golden` §A–D, §F |
| PROV-05 tier-1 evaluator == trace, order-independent | IMPLEMENTED | `rule_predicates._eval_condition` / `trace_predicate_audit`; §D |
| PRES-01 engine 0..N; screen ≤ 5; no filler; nothing discarded | IMPLEMENTED | `present-cap.js`; `presentation-cap.spec`; `test_candidate_golden` §G (API intact) |
| PRES-02 honest overflow, openable and operable from the keyboard | IMPLEMENTED | `livePathOverflowHtml` (native `<details>`); `presentation-cap.spec` |
| PRES-03 hidden paths still carry evidence/provenance | IMPLEMENTED | the same path objects are returned; `presentation-cap.spec` (hidden candidate-paths + "why") |
| REQ-01..04 | IMPLEMENTED | registry + presentation; IDs are engine identifiers |
| READY-01..05 | IMPLEMENTED (READY-03/05 guarded by module structure) | `test_readiness_*` |
| NARR-01..04 | IMPLEMENTED | `claims.py`, fallback from the same projection |
| ROUTE-01..05 | IMPLEMENTED; ROUTE-03 "shared template" = invalid by contract | `test_route_composition` |
| DATA-01..03 | IMPLEMENTED (no automatic migration, by design) | `test_navigation_semantics` §C |
| M4-01..M4-20 (state-driven conversation; Applicable Requirement Set; a single Requirement State Reader; live adjudication; Question Planner; reason trail + replay; scoping; fail-safe; inspectable UI) | IMPLEMENTED | §25.10 — `test_m4_*`, `conversation.spec` |
| INV-7 item 4 (int 10): no new path carries "advanced because the turn ran out" | IMPLEMENTED; since M5 the old engine is DELETED (§26) | `test_m5_phase_removal` (AST over all production code + negative property) |

## 22. Known debts (never claimed done)

Debts PAID in this iteration and removed from the list: ~~feasibility not recomputed from adjudicated state~~ (now `canonical_feasibility`, §10.1, `PROJECTION_VERSION` 4); ~~duplicate templates in library/registry~~ (now ROUTE-04b, §7.1); ~~corrupt PathSet content read as results~~ (now `PATHSET_MALFORMED`, §11); ~~map interactivity without keyboard support~~ (now UI-03, `accessibility.spec.mjs`); ~~Tier-2 knowledge & the old score — an UNSUPPORTED match still modulated the confidence score~~ (now consequences only from anchored matches, §6.1; `evals/test_unsupported_causal.py` proves zero positive causality into navigation); ~~the adjudication ledger producer not wired into the live session flow~~ (now §25.4, M4); ~~the conversational NextMove phase-driven, no question planner~~ (now the Question Planner, §25.5, M4).
- **One route per path** in readiness projection (§7.1).
- **PAUSED** without a producer; **one scope per user** for route lineage (int 08 §8.2); languages other than `id`/`en` have no data yet.
- **Candidates from the LLM** not wired yet (§18, §23.9): the contract is ready, but there is no LLM producer.
- **Mechanism → mechanism chains** (derived mechanisms depending on other derived mechanisms) are rejected at `PossibilitySpace` construction (cycle prevention) — FUTURE, not a need of this iteration.
- **Revenue rule → mechanism** stays NOT IMPLEMENTED BY DESIGN (§18, §23.8); Revenue patterns rely on mechanisms detected directly from evidence.
- ~~**NextMove over candidate-born routes**~~ — **PAID** (closure 1 Oct): `test_candidate_golden.py` runs the REAL route composer + `select_next_move` over templated candidate-paths (a synthetic domain with templates passing the production route validator; Revenue over HTTP with the real `direct_outreach_v1` template). The production Revenue patterns stay routeless (no templates invented).
- **Candidate ranking**: candidates get no score/ranking; order = declaration order of the space (strategies first, then patterns) — intentional, not a contract debt.
- **Ranking re-sort on `any_signal`** (`core/stages/knowledge_rules.py`): once ANY anchored rule executes a consequence, the entire ranking is re-sorted `(effective_score desc, constraint_id)` — hypotheses whose scores did not move may reorder among themselves via the tiebreak. Deterministic and not an UNSUPPORTED leak (the trigger is always an anchored match), but it remains a cross-hypothesis consequence no test yet requires; FUTURE, not changed in this iteration.
- **The map on narrow screens (390px)**: lanes may be cropped inside the map's own horizontal scroll container (the existing design, "Scroll sideways"); no page-level overflow. Keyboard stays operable at 390px (UI-03 tested dark+390px).
- **The store→domain edge** (`mvp/store/path_states.py` imports `domains.revenue.stages.reroute`): the store calls the domain for reroute lifecycle — NON-BLOCKING: one direction (store→domain), it does not pierce the core boundary (`test_core_scope` stays green), and that call is the very reason this store module exists.
- **NON-BLOCKING — a lane picked from the overflow may sit off-screen**: the 4-slot strategy lane can branch into the next cycle column (existing map geometry); a path picked from "+N other possibilities" stays pinned, but its lane may need horizontal scrolling. Its path card detail is always visible.
- **NON-BLOCKING — `PATHS_CAP = 10` in `agents/explain.py`** is an LLM prompt budget, not an engine limit; it is announced to the LLM, and the UI falls back to engine text for unexplained paths.
- **NON-BLOCKING — per-branch provenance for tier-2 (judgment/LLM)** is impossible: free-form citations are verified as one `judgment` branch (condition matching remains an LLM judgment); per-branch applies fully to tier-1.
- **NON-BLOCKING — the mock provider** (`providers/mock.py`) ships ready-made explanations for the five Revenue path keys (DEMO/mock; explicitly referenced); other keys fall back to engine sentences.
- **NON-BLOCKING — ties between routes in `select_next_move`**: when several OPEN routes share priority and node strength, ties are broken by `route_id` (the UUID minted when the route was born; stable afterwards because routes are reused). That is not a ranking and is never claimed "best"; the frozen foundation, unchanged. `test_candidate_golden.py` §H uses a single route so NextMove stays deterministic. FUTURE if a meaningful order is ever needed.
- ~~**NON-BLOCKING — the adjudication ledger producer not wired into the live session flow**~~ — **PAID (M4, 2 Oct 2026)**: `ontology/mapper/live_adjudication.py` is called every turn by `app/navigation.navigate_session` (§25.4); route node `satisfaction` in live sessions now reflects the ledger. What remains is **formal rule coverage** (see the M4 item below), not the producer.
- **NON-BLOCKING — temporary scripts tracked** `mvp/e2e/boot.tmp.mjs` and `mvp/e2e/repro04.tmp.mjs` (commit `0b9856c`, before this iteration): unused by Playwright (`testMatch` only `*.spec.mjs`) and untouched here; clean them up whoever holds their context.
- **FUTURE**: candidates from the LLM, mechanism → mechanism chains, candidate ranking/scoring (intentionally absent), a `PAUSED` producer.
- **Live LLM** (`make gate-smoke`, `evals/run_dod_smoke.py`): **NOT RUN** on the 1 Oct closure iteration (candidates) — requires a paid API key; outside the deterministic gate. **Run once at the M4 closure (2 Oct 2026, on mandate instruction; provider `opencode_go`, model `deepseek-v4.1-flash`)**: attempt 1 → 19/20 invariants (one word-heuristic failed: the NBA text was Indonesian using "calon", without "eligible"/"lead"); attempt 2 (the Makefile's built-in retry) → 20/20, `DOD MET`, exit 0. P0-1 (explicit numbers: current 30, target 60, gap 30, delivery 34.5, acquisition 4) passed on both attempts, i.e. M4 extraction does not damage explicit facts under a real LLM. That word heuristic was not compared against `main`: it did not recur on attempt 2 and depends on the LLM's word choice ("calon" vs "lead").
- **M4 (2 Oct 2026) — known debts** (all NON-BLOCKING; no BLOCKING debts):
  - **Partial, lexical formal rule coverage**: of 49 requirements, 3 `FORMAL_RULE` can be adjudicated from conversation, 2 `UNIT_CONTEXT_REQUIRED`, 44 `NO_FORMAL_RULE` (stay `UNKNOWN`, handed to actions/routes); the formal rules' keywords are Indonesian. Adding rules = data (`formal_rules_compiled.json`) and review, not planner changes (§25.4).
  - **`ASK_CAP` = 2**: one hard-to-satisfy adjudicated requirement can consume up to 2 turns before being skipped (`ASKED_ENOUGH`); intentional (knowing when to stop), but not a solution.
  - **Deterministic wording**: step text from frameworks + Requirement Presentation; LLM rewording (wording only, never decisions) is FUTURE.
  - **Identical `ACTION` decisions may repeat** when state does not change between turns (the planner re-decides from state, with no action memory); the wording voices "unchanged" rather than an identical sentence (§25.6).
  - **Readiness for routeless paths with requirement-anchored checks** — **PAID (M4.1, 2 Oct 2026)**: reads the ledger through the same `RequirementStateReader` (`build_projection(…, state_reader=status_reader(reader))`, `merge_readings`; conflicts = `authority: ledger` metadata). Proven by `evals/test_m4_readiness_routeless.py`.
  - ~~Topic labels `phase` on evidence, `phase`/`phase_index` API fields, the phase engine, `analyze_turn`/`build_turn`, the `phases.json` probes~~ — **PAID in M5** (§26): evidence now carries `topic` (a display label), the API has no `phase`, the engine and `phases.json` are deleted. Remaining M5 debts are in §26.8.
  - **Live extraction** is tested with the deterministic mock provider; with a real LLM it is verified via the 4-turn probe and `make gate-smoke` (2 Oct 2026, see the live LLM item above). The real-LLM probe found and fixed one normalization bug (lowercased `kind`/`level` triggering a full retry), and confirmed the formal rule coverage boundary (paraphrased statements do not pass literal verification; the planner asks twice then stops).
  - **Outside M4, found 2 Oct 2026 (NON-BLOCKING)**: the Diagnosis screen shows 6 interactive controls for artifacts with > 5 paths (the presentation-cap overflow list adds two "Show on the map" buttons), so the Hick UX law (max 4 actions; `e2e/diagnosis-ux.spec.mjs` "real engine artifacts") fails for such real artifacts. Reproduced exactly on `main` (3e4376a) with the same data; that spec reads the local `store/sessions` (not in git), so it only fails on machines holding such artifacts. Not changed in M4 (frozen layer, out of scope).

## 23. Knowledge → Mechanism → Candidate Possibility

> **Status**: **IMPLEMENTED** (1 Oct 2026) on top of the frozen foundation: not one of the `Signal`, `RuleSupport`, `PathSet`, `StrategySpec`, `Requirement`, `Satisfaction`, `Applicability`, `Feasibility`, `Lifecycle`, `Readiness`, `NextMove`, `Route`, `Legacy`, `UNKNOWN`/`UNSUPPORTED`/`CONFLICT` semantics changed. `PATHSET_VERSION` stays 3 and `PROJECTION_VERSION` stays 4: every addition is additive.

### 23.1 What is new, and what is not

Before this layer, a path could only be born from a `StrategySpec` already written by the domain. Now verified knowledge can birth **new directions** without a strategy list:

```text
Evidence ──► Knowledge (rule:/state:) ──► MECHANISM ──► CANDIDATE POSSIBILITY ──► evaluation ──► POSSIBLE PATH ──► Route ──► Readiness ──► NextMove
              (RuleSupport, anchors)      active when      a proposal, not yet    applicability   0..N          (optional)
                                          anchored                                  feasibility
```

| | Answers | Example | Not |
|---|---|---|---|
| **Knowledge** | what a source states | rule `GW-R1`: "many sign-ups" + "not reaching aha" | evidence about the user |
| **Mechanism** | *why* this state implies a direction | `activation_bottleneck` (active because `GW-R1` is anchored to ev-g-1, ev-g-2) | actions, requirements, strategies, routes |
| **Candidate Possibility** | which direction *might* be worth considering | `cand.improve_activation_before_acquisition` | a path; a claim that the direction is right |
| **Possible Path** | a direction that *passed deterministic evaluation* and is worth navigating | `path.improve_activation_before_acquisition` (TEST_FIRST: the `aha_defined` check is unknown) | a route |
| **Requirement / Route / Action / Outcome** | as in §2 | — | — |

**Candidate Possibility ≠ Possible Path ≠ Route; Requirement ≠ Action; Knowledge ≠ Evidence; Mechanism ≠ Strategy.** There is no `knowledge → path` shortcut (INV-03).

### 23.2 The contract (`core/navigation/contracts.py`, `core/navigation/candidate.py`)

- **`MechanismSpec{mechanism_id, title, activated_by, contradicted_by}`** — a mechanism that can become active because of knowledge. `activated_by` is a Kleene predicate over `rule:`/`state:` signals (or a `mechanism:` signal the domain reader reports directly). A mechanism is **active** only when its support is anchored in evidence (real `refs`). `contradicted_by` = an **explicit** counter-evidence predicate. A mechanism without `activated_by` is active only when a domain reader reports it directly and anchored (Revenue).
- **`PossibilityPattern{direction, title, mechanism_ids, thesis, context_when, not_applicable_when, checks, route_template_ids, no_preconditions, presentation, knowledge_sources}`** — domain knowledge of the form "if mechanism M is active (in context C), direction D is worth considering". `direction` is the canonical semantic identity. `mechanism_ids` means *any_of*: two mechanisms pointing at the same direction produce **one** candidate with merged provenance. Patterns are not a path list and not a `StrategySpec`. Two field groups with different responsibilities: **PROPOSAL** (`pattern.proposal` = `Proposal{direction, title, mechanism_ids, thesis, context_when, presentation}` — the only thing the generator reads) and **EVALUATION** (`not_applicable_when`, `checks`, `route_template_ids`, `no_preconditions` — read by the evaluator only after promotion). `context_when` (formerly `requires`) = extra state context (a Kleene predicate over signals, like a strategy's `emerges_when`) that must be TRUE for that mechanism to imply this direction; it is **not a Requirement** (not a Requirement Registry item, has no satisfaction, does not form checks) and does not decide feasibility/readiness: TRUE → the candidate may be born, FALSE → `NOT_EMERGENT`, unknown → `UNDETERMINED` (+ the "One fact missing" possibility). `presentation.<lang>.because` may be pattern text or `{mechanism_id: text}`.
- **`CandidatePossibility`** — the proposal: `candidate_id` (`cand.<direction>`), a base status (`SUPPORTED` · `UNDETERMINED` · `NOT_EMERGENT`), `support` (the support rows actually evaluated, including the rules/state behind the mechanisms), `mechanisms` (lineage audit), `missing`, `conflicts` (disputes among the causing mechanisms — recorded **also** on a SUPPORTED candidate standing via independent sibling branches: it does not cancel that support, but it must not vanish), `refuted`, `emerging` (`CONFLICT` · `PARTIAL` · `UNSUPPORTED` · `None`). The candidate holds a `Proposal` (not a `PossibilityPattern`), so it structurally carries no evaluation substrate. No new enum for states: conflict is **structured metadata** (the same pattern as §10.1), not a fifth value.
- **What is deliberately NOT on `CandidatePossibility`**: `applicability`, evaluated `candidate_requirements`/`checks`, `route_substrate`, `feasibility`, a status word. All of that belongs to **evaluation** and exists only on a Possible Path (path fields are not duplicated; generation does not judge). The candidate carries only what is needed to answer "why is this direction proposed": the goal (via support rows), the thesis, mechanisms, knowledge, evidence, counter-evidence.
- **`PossibilitySpace.mechanisms` / `.patterns`** (optional). A space without either behaves exactly as before. Guarded at construction (`ValueError`, never discovered downstream): duplicate `direction`; a mechanism depending on another derived mechanism or itself (cycle prevention); patterns without mechanisms; patterns sharing identity with a declared strategy while carrying `checks`/templates/exclusions (a pattern may only add provenance); templates claimed by two owners.

### 23.3 Knowledge → Mechanism (`MechanismOverlay`)

The overlay wraps the domain reader (already `grounded`) and adds derived mechanisms:

| Support | Explicit rebuttal | Mechanism result |
|---|---|---|
| `activated_by` TRUE anchored (or reported directly & anchored) | none | `ACTIVE` — `Signal(True, refs = merged anchors, basis = {via: DERIVED/DETECTED, derived_from: [...]})` |
| present | `contradicted_by` TRUE | **`CONFLICT`** — `Signal(None)`; both sides recorded in `conflicts`; **never silently picked** |
| absent | `contradicted_by` TRUE | `REFUTED` — `Signal(False, refs = counter-evidence)` |
| absent / `rule:` UNSUPPORTED | none | `UNDETERMINED` — `Signal(None)` (+ `unsupported` when the read knowledge has no basis). **Never FALSE:** absent support is not evidence of absence |

**One mechanism concept, two activation sources — not two systems.** Detecting mechanisms from evidence (the `ontology/mechanisms.json` catalog keywords, `core/stages/mechanisms.py`) still belongs to the diagnosis pipeline and enters navigation as an anchored `mechanism:<id>` signal (the Revenue path). `MechanismSpec` is the second lane on the **same** signal: mechanisms derived from verified knowledge (`rule:`). Both are read through one interface (`mechanism:<id>`), one provenance rule (real `refs`), and can be active together (`via: DETECTED+DERIVED`). The catalog is not duplicated: Revenue patterns reference existing catalog ids and are validated against it.

An "active" mechanism without a single `refs` is downgraded to `UNSUPPORTED` (PROV-02 applies to derived mechanisms too). A pure `none_of` rule does not even *match* (mandatory citation), so absent evidence is never support; `none_of` as a sibling of `all_of` carries no positive anchors.

### 23.4 Mechanism → Candidate, and generation ≠ evaluation (CAND-01)

- `generate_candidates(space, reader)` — **only proposes**: a SUPPORTED candidate when the pattern predicate (`any_of` mechanisms, `all_of` `context_when`) is TRUE; `NOT_EMERGENT` when FALSE (a mechanism explicitly refuted or a condition proven FALSE); `UNDETERMINED` when it cannot be judged yet. A non-TRUE goal (`goal_signal`) → zero candidates, as before. It never judges applicability, feasibility, route, or readiness.
- `evaluate_candidates(...)` — SUPPORTED candidates enter the **same evaluation pipeline** as candidates from declared strategies (`promote_possibilities` forms a `generator.Candidate`; there is no second pipeline, INV-12). The evaluator still decides: `NOT_APPLICABLE` → discarded (`generation.rejected`, disposition `REJECTED_NOT_APPLICABLE`), feasibility from `checks`, lifecycle on top. A candidate without checks is never silently `SUPPORTED` (§5.1): `UNDETERMINED`/`TEST_FIRST` unless the pattern declares `no_preconditions`.
- `build_path_set` = both steps, still separate inside; re-evaluating never mutates candidates.

### 23.5 Promotion, identity, duplicates, collisions (CAND-06)

| Layer | Identity | Notes |
|---|---|---|
| Candidate Possibility | `candidate_id` = `cand.<direction>` | canonical from the direction; **not** a replacement for `strategy_id` |
| Strategy / Possible Path | `strategy_id` = `direction`; `path_id` = `path.<strategy_id>` | unchanged (PATH-08) |
| Route | `route_id`, `revision_no`, `reopened_from`; key `{goal, strategy_id, scope}` | unchanged (ROUTE-01..05); `candidate_id` never enters the route key |

- **Duplicates**: two mechanisms → the same direction = one candidate; two patterns with the same `direction` are rejected at authoring; the same direction as a declared strategy, also born via `emerges_when` = **one** path, `origin=BOTH`, support merged (deduplicated per signal).
- **Same mechanism, different directions**: valid (`activation_bottleneck` → `improve_activation_before_acquisition` and `define_aha_moment`).
- **Provenance never lost**: `path.provenance.candidate = {candidate_id, origin (MECHANISM_PATTERN|BOTH), direction, thesis, mechanism_ids (only ACTIVE ones), knowledge_ids, evidence_ids, transcript_anchors, mechanisms[…] (every cause with its status), support[…], conflicts[…], assumed_absences[…]}`; per-branch `knowledge_support` stays on the path provenance (same as §6.1). `validate_path_set` rejects candidate-paths without a causing mechanism, without evidence anchors, or with a non-canonical `candidate_id`. Paths born purely from strategies get **no** `candidate` block (no invented origin).

### 23.6 The epistemic contract

```text
verified support   → a candidate may exist (SUPPORTED, then evaluated)
UNSUPPORTED        → no positive support; zero effect on paths, readiness, routes, NextMove (≡ absent rule, except in the audit)
UNKNOWN            → the candidate stays UNDETERMINED; never treated as confirmed; never becomes NOT_EMERGENT
explicit rebuttal  → a REFUTED mechanism → NOT_EMERGENT; support + rebuttal → CONFLICT (the candidate is never silently SUPPORTED)
evidence shrinks   → support never grows (monotonic); reverse lineage: revoke an anchor → the branch falls → the mechanism falls → the candidate falls
```

### 23.7 PathSet audit and projection (additive)

- `generation.mechanisms` — the audit of every derived mechanism (status, via, knowledge_ids, evidence_ids, conflicts); `generation.possibilities` — the fate of candidates that have something to audit (`PROMOTED` + `path_id` · `REJECTED_NOT_APPLICABLE` · `CONFLICTED` · a flagged `UNRESOLVED` · `NOT_EMERGENT`); "never detected" without any flag stays only in `generation.undetermined` (artifacts are not bloated by silent patterns). `generation.considered` now counts strategies + patterns.
- **Readiness projection**: every path carries `candidate` (`candidate_id`, `origin`, mechanisms, knowledge, evidence, `why`, `unsettled` = disputed causing mechanisms, `assumes_absence` = support resting on absent records); the projection level carries `emerging` — newly surfacing possibilities that are **not yet paths**: `CONFLICT` · `UNKNOWN` (an anchored mechanism, other conditions unknown; needing only a **state fact**, not a mechanism name) · `UNSUPPORTED` (an unbacked hint). `emerging` never becomes a requirement item, never changes `counts`, and is empty for LEGACY artifacts. `why` = the domain's curated text (`presentation.<lang>.because`) when it cannot narrate an unanchored mechanism — the text form is used only when the pattern has ONE causing mechanism or ALL of its causes are active; the `{mechanism_id: text}` form combines the sentences of the ACTIVE mechanisms only; otherwise a deterministic fallback from the **active anchored mechanisms only** (a disputed mechanism is never narrated as the reason; it appears separately as `unsettled`).
- **Narrative & Ask/Explain**: the LLM context carries `why it is on the map` per path and the row `possibility (not a path): … UNKNOWN|CONFLICT|UNSUPPORTED … NOT a path` — the four states (verified/unknown/conflicted/unsupported) each read differently and none is voiced as certainty. The LLM never invents a candidate's reason.
- **UI** (`live-vm.js`, `live.css`): candidate-paths show "Why this is on your map" (`<details>`, openable with Enter/Space; its content = the reason + "It rests on N things you shared, read against K rules from our knowledge base"); newly surfacing possibilities live on the separate **"Taking shape"** card — a dashed frame, a neutral pill ("One fact missing" · "Not settled" · "Not backed yet"), never a lane, status, or action button. Two separate notes accompany the reason when present: "Parts of what you told us point in different directions about …, so we are not counting that as part of the reason." (`unsettled`) and "It also assumes nothing you told us points the other way. We have not confirmed that." (`assumes_absence`). No raw ids/enums reach the reader (`candidates.spec.mjs`).

### 23.8 Evidence: Revenue and synthetic domains

**Revenue** (`ontology/possibility/revenue.json#patterns`, validated by `validate_possibility.py`): three patterns from catalog mechanisms **that previously birthed no paths**, each resting on a real KB intervention whose `targets` intersect the mechanism's constraints (the validator rejects invented knowledge):

| Mechanism (detected from evidence) | Direction | Rests on |
|---|---|---|
| `lead_leakage` (C6.4) | `fix_response_before_more_leads` | `PR-I02` Simple Response System (pr/ch03) |
| `targeting_gap` (M3.1) | `narrow_target_before_volume` | `PR-I03` ICP List Filter before adding volume (pr/ch03) |
| `offer_disconnect` (V2.1) | `shape_buyable_offer` | `VP-I02` Ad-lib offer + Value Map (vp/ch02, ch04) |

The five old strategies are unchanged; without mechanisms there are no new candidates (old behavior identical). The resulting paths are routeless (intentional: no templates invented) and carry status `TEST_FIRST` (`NO_CHECKS_DECLARED` — the mechanism is proven, viability untested). Revenue KB rules are not used as mechanism derivation (see §18: not ontologically honest).

**Synthetic** (`evals/navigation_fixtures.py`, without touching `core/`, without `StrategySpec`): "growth" (`GW-R1` nesting `all_of`/`any_of`/`none_of` → `activation_bottleneck` rebutted by `GW-R3`; `GW-R2` → `onboarding_friction`; three directions, one templated) and "hiring" (`HR-R1` → `inconsistent_hiring_bar` → `calibrate_hiring_bar`). Both walk evidence → rule → derived mechanism → candidate → path with the same generic code.

### 23.9 Deliberate boundaries

- The LLM may propose candidates/patterns/wording; **there is no LLM producer yet**. When wired, its proposals must pass the same verification: anchored mechanisms, the deterministic evaluator; the LLM never sets state, satisfaction, applicability, or routes.
- Candidates get no score or ranking; order = space declaration.
- Mechanism → mechanism chains are not supported (rejected at authoring).

## 24. Closing the Candidate Possibility layer (1 Oct 2026) — FROZEN

> **Status**: **IMPLEMENTED, TESTED, FROZEN.** This section summarizes the canonical pipeline, the knowledge taxonomy, definitions, cardinality, the presentation cap, and candidate-born lineage after closure. The foundation semantics did not change: `PATHSET_VERSION` = 3 and `PROJECTION_VERSION` = 4, all additions additive. The next iteration builds **on top of** this layer; redesigning the layer's architecture is not planned.

### 24.1 The current canonical pipeline

```text
Goal ─► Verified State ─► Knowledge ─┬─ explanatory ──► Mechanism ─► Candidate Possibility ─► Candidate Evaluation
                                     ├─ applicability ───────────────────────────────────────────────┐ (not_applicable_when)
                                     ├─ requirement  ──► Requirement Registry / Readiness           │
                                     └─ constraint   ──────────────────────────────────────────────┘ (checks, contradicted_by)
                                                                                                      ▼
   Possible Path 0..N ─► Route (optional) ─► Readiness ─► NextMove ─► Action ─► Outcome ─► new Evidence ↺
        (engine, all of it)                                                              (UI: at most 5 at a time, §24.7)
```

The explanatory branch: `Evidence → Knowledge → Mechanism → Candidate Possibility → Evaluation → Possible Path`. There is no `knowledge → path`, `candidate → route`, or `mechanism → action` shortcut.

### 24.2 The Knowledge taxonomy

Knowledge is not one thing. Its function determines **where** it enters the pipeline; **only explanatory knowledge becomes a Mechanism**.

| Function | Answers | Enters | In code |
|---|---|---|---|
| **Explanatory** | *why* state X implies direction Y | **Mechanism** → Candidate Possibility | `MechanismSpec.activated_by` over `rule:`/`state:` signals; `PossibilityPattern.mechanism_ids` |
| **Applicability** | whether a direction *applies* to this situation | **Evaluation** (`Applicability`) | `not_applicable_when` (strategies/patterns); `applies_when` on route templates |
| **Requirement** | which world condition *must hold* | **Readiness** / requirement items | Requirement Registry + route templates (`node_candidates`) |
| **Constraint** | what *holds back or contradicts* | **Evaluation** (`Feasibility`) | `checks` (`prereq` / `hard`); `MechanismSpec.contradicted_by` (explicit mechanism rebuttal) |

Two things often mistaken for one: `context_when` (a pattern's **emergence** context — read by the generator) is not applicability (read by the evaluator) and not a requirement (it has no satisfaction). And a KB rule that modulates constraints/confidence does **not** automatically become a mechanism (§18: Revenue rule → mechanism NOT IMPLEMENTED BY DESIGN).

### 24.3 Candidate Possibility: definition and boundaries

- **Candidate ≠ Possible Path ≠ Strategy ≠ Route.** Candidate = a *proposal*: `cand.<direction>` + proposal content (`Proposal`) + provenance. Possible Path = a proposal that **passed deterministic evaluation** (`path.<direction>`). Strategy = a domain-declared method. Route = a workable composition of requirements (`route_id`).
- **Generation ≠ evaluation.** The generator answers "which possibilities emerge from active knowledge/mechanisms?" and reads only `pattern.proposal`. The evaluator answers "is it applicable, viable, and open?" and reads the pattern's evaluation substrate. A candidate structurally has no applicability, feasibility, requirement state, executability, route, or readiness.
- **Explicit promotion** (`promote_possibilities`): SUPPORTED candidates enter the same evaluation pipeline as declared strategies; the evaluator may discard them (`NOT_APPLICABLE`) and judge them (feasibility from `checks`).
- **Provenance preserved** down to evidence: mechanisms, knowledge (per predicate branch), evidence/quotes, **disputes** (§23.3) and **absence assumptions** (§6.1). `UNSUPPORTED` ≡ an absent rule; `UNKNOWN` never becomes `NOT_EMERGENT`.
- **Identity**: `candidate_id` (`cand.<direction>`) ≠ `strategy_id` (= the direction) ≠ `path_id` (`path.<direction>`) ≠ `route_id` (UUID). A direction is only `[A-Za-z0-9_]`, so `cand.`/`path.` can never be disguised as another layer.

### 24.4 Revenue = the commercial navigation domain

**Revenue** at Novaliners is the **commercial navigation domain**: the movement of a business toward revenue — getting clients, traffic and lead generation, qualification, closing and conversion, offers and pricing, deal value, expanding existing clients, partnerships and referrals, acquisition, marketing, sales, business development, and related commercial activity. It is **not** a single revenue KPI. The numeric fields on `RevenueState` (running revenue, target, capacity, willingness to pay) are **signals** read by the domain reader (`RevenueSignals`), not the domain's definition; its real outcomes include non-numeric directions like `fix_response_before_more_leads` (lead response), `narrow_target_before_volume` (targeting), and `shape_buyable_offer` (offering).

### 24.5 The five Revenue motions

> **ACQUISITION, REPRICING, EXPANSION, PARTNERSHIP, and PAID_ACQUISITION are Revenue-domain strategic motions/primitives, not the universe of Possible Paths.**

They stay alive as the domain's **vocabulary/substrate**: the `motion` label on strategies (`ontology/route/strategies.json#motion_vocabulary`) and a tested primitive collection. They are not a path list, not path identity (`path_id` comes from the strategy, not the motion), not a UI key, and never appear in `core/`. Proven by `test_candidate_closure.py` §G and `test_candidate_golden.py`: evidence supporting **one** possibility → 1 path; **three** → 3 paths (all outside the five old strategies); **eight** (5 strategies + 3 candidates) → 8 paths, not 5. Only 5 paths carry a motion label; the rest have `motion = null`.

### 24.6 Possible Path cardinality: 0..N

The number of Possible Paths = the number of **evidence-supported** possibilities — 0, 1, 2, 3, …, 8, 10, 13, … — with no target of five and no upper bound from the engine. `unresolved` is mandatory at zero (universal codes). Proven on three synthetic domains (growth, hiring, "signals" with N directions) and Revenue, and over HTTP: diagnosis + readiness return **all** paths (0, 1, 3, 5, 6, 8, 10, 13) without truncation.

### 24.7 The presentation cap

```text
ENGINE    Possible Paths = 0..N          (unbounded; all evaluated, stored, returned by the API)
UI        visible paths  <= 5            (display policy: `PATH_VIEW_CAP` in app/static/js/present-cap.js)
UX        natural density ≈ 3            (when that is all the evidence supports; 2 supported shows 2; no filler)
```

**The presentation cap ≠ the generation cap.** Five is not the universe, not a completeness target, and not a quota; three is not a hard limit; no synthetic paths to round out the screen.

| Engine | UI |
|---|---|
| 0 | 0 (the explicit reason "We cannot name a path yet.") |
| 1 / 2 / 3 / 4 / 5 | 1 / 2 / 3 / 4 / 5 |
| 6 / 8 / 10 / N>5 | 5 + "+N other possibilities" |

The rule (`presentPaths(paths, {cap, pinned})`, a pure function): `visible` + `hidden` = exactly the input (nothing dropped or added, the same objects so evidence/provenance travel along); the **active** path, the one **being viewed/selected**, and those **already taken** always display; the rest are chosen by the engine's own status words (`OPEN → TEST_FIRST → NOT_YET → STOP`, ties follow engine order) — not a ranking, and never called "best/optimal/top". The overflow (`livePathOverflowHtml`): "+3 other possibilities" with "Showing five of eight possibilities. Not drawn: 3 test first.", a native `<details>` (Tab, Enter, Space), the list of hidden paths with name, status, reason, and a button bringing a chosen path onto the screen. Applied on the map, the readiness list, the diagnosis card, reveal, and the zero-open map (which used to drop the 5th path without a word). The map headline still counts **all** paths.

### 24.8 Candidate-born routes: full lineage

```text
Knowledge ─► Mechanism ─► Candidate ─► Possible Path ─► Route ─► Readiness ─► NextMove
tier-1 rule   active when    cand.<dir>    path.<dir>      route_id    canonical    v1 selector
+ anchors     anchored       (proposal)    (passed eval)   (UUID)      state (the   over non-STOP
per branch                                             (ledger))   ledger)      routes
```

One pipeline for every path origin: `plan_compositions` (strategy-first) → `run_session_route` (lifecycle first, then the composer) → `overlay_execution` → `assert_route_keeps_strategy` → the NextMove gate over the adjudicated reading → `select_next_move` — all in `ontology/route/path_routes.compose_path_routes`, called by the `POST /session/{sid}/routes` endpoint **and** the golden test. It never reads `provenance.candidate`, `origin`, or `candidate_id` (an AST guard). Candidates have **no** route composer of their own. A path without a template stays valid (route-less). The route `reconciliation_key` carries `strategy_id`, never `candidate_id`. The golden test proves: candidate-born == declared-strategy (route, readiness, NextMove), detaching the entire candidate block changes nothing, and the reverse direction (revoke/invalidate evidence → no ghost path/route/NextMove; the evidence returns → the old route is reused).

### 24.9 Invariant → implementation → test → E2E map

| Invariant | Implementation | Unit/integration test | E2E |
|---|---|---|---|
| Candidate ≠ Path (CAND-04) | `candidate.py`, `evaluator.py` | `test_candidate_possibility` §B | `candidates.spec` 04–06 (not-yet-paths are not lanes) |
| Generation ≠ evaluation (CAND-01/09) | `Proposal`, `generate_possibilities` | `test_candidate_closure` §A (invariance + AST) | — |
| Per-branch provenance; evaluator == trace (PROV-01/05) | `rule_predicates.py`, `rule_support.py` | `test_candidate_closure` §D; `test_knowledge_provenance` | — |
| Absence of record ≠ verified absence (CAND-11) | `AbsenceAssumption`, `assumed_absences` | `test_candidate_closure` §C | `candidates.spec` 03c |
| Disputes never vanish (CAND-10) | `CandidatePossibility.conflicts`, `readiness._candidate_view` | `test_candidate_closure` §B; `test_candidate_golden` §H (with a REAL route: route/NextMove blind to the dispute) | `candidates.spec` 03b |
| UNSUPPORTED ≡ absent rule (CAND-03) | `grounded`, `rule_signal` | `test_candidate_possibility` §F; `test_unsupported_causal` | `candidates.spec` 06 |
| Possible Path 0..N (PATH-01/05) | generator, evaluator | `test_candidate_closure` §F; `test_navigation_universal`; `test_candidate_golden` §G | `paths.spec` 00–03; `presentation-cap.spec` |
| Optional routes (PATH-07/CAND-05) | `route_substrate` | `test_candidate_possibility` §I; `test_candidate_golden` §A | `candidates.spec` 01 |
| Candidate-born routes first-class (CAND-12) | `path_routes.compose_path_routes` | `test_candidate_golden` §A–D, §F | `candidates.spec` 02 |
| Reverse lineage | grounded + recomputed | `test_candidate_golden` §C; `test_candidate_possibility` §E | — |
| Five motions ≠ universe | `revenue_space`, `strategies.json` | `test_candidate_closure` §G; `test_revenue_navigation` §9 | `paths.spec` 12; `candidates.spec` 03 |
| Core domain-independent | `core_scope.json`, import-linter | `test_candidate_possibility` §M; `test_domain_extensibility`; `test_candidate_golden` §E | — |
| Presentation cap (PRES-01..03) | `present-cap.js`, `live-vm.js` | `test_ui_fixtures`; `test_candidate_golden` §G | `presentation-cap.spec`; `paths.spec` 03 |
| Legacy safe (DATA-01..03) | `compat.py` | `test_navigation_semantics` §C | `paths.spec` 10, 15; `candidates.spec` 07 |
| Accessibility (keyboard, focus, WCAG A+AA) | native `<details>`, `:focus-visible` | — | `presentation-cap.spec`; `candidates.spec` 08; `accessibility.spec` |

### 24.10 Freezing

The Knowledge → Mechanism → Candidate Possibility → Possible Path → Route → Readiness → NextMove layer is considered **closed**: architecture, implementation, tests, E2E, visuals, accessibility, and documentation are consistent. Any later change touching the contracts in this section (beyond adding a domain or data) requires an architecture-level justification against the entire downstream. Known debts are in §22, separated into BLOCKING / NON-BLOCKING / FUTURE; there are no BLOCKING debts. M4 (§25) was built **on top of** this layer without changing its contracts (`PATHSET_VERSION` 3, `PROJECTION_VERSION` 4).

## 25. M4 — Conversation as state navigation

> **Status**: **IMPLEMENTED, TESTED** (2 Oct 2026; branch `iteration/universal-conversation-navigation-m4`) on top of the frozen foundation (§24): `PATHSET_VERSION` stays 3 and `PROJECTION_VERSION` stays 4, all additions additive; the `Signal`, `Satisfaction`, `Applicability`, `Feasibility`, `Lifecycle`, `Readiness`, NextMove v1, `Route`, `LEGACY`, `UNKNOWN`/`UNSUPPORTED`/`CONFLICT` semantics unchanged. This section realizes M4 of int 11 §10.15 ("switch navigation"). **Historical M4 snapshot — when M4 closed (2 Oct 2026), M5 was not yet done**: the phase engine still existed then, marked DEPRECATED, and was proven **not an authority** in the conversation path (§25.9). **Current state: at the M5 closure (2 Oct 2026) the phased interview engine was DELETED — see §26.** Per-mandate-item evidence with its honest limits: [`../05-proof-and-gates/07-m4-completion-matrix.md`](../05-proof-and-gates/07-m4-completion-matrix.md).

### 25.1 Why, and what changed

Before M4, `POST /session/{sid}/message` was driven by **phases** (`PHASES`, `turns_in_phase`, "advance because the turn ran out"). As a result the next question was born from phase progress, not uncertainty; Possible Paths only existed at `finalize`; there was no adjudication-ledger producer in the session flow (route node satisfaction was always `UNKNOWN`); and the question, Route, and Readiness each read a different reality. That violated INV-7 (int 10): Question and Action are one type, NextMove, chosen from state.

After M4 one turn is one round of the **state loop**:

```text
 user message
   │  EXTRACTION (LLM interprets, PROPOSAL)         agents/interview.extract_turn → TurnExtraction (evidence, number claims, intent)
   ▼
 EVIDENCE ledger (dedup, deterministic ids) + UNIVERSAL STATE (graph + verify gate)                   app/turn.py
   │
   ├─ LIVE ADJUDICATION  evidence → mapper (proposal) → verification → adjudication → user-scoped LEDGER   §25.4
   ├─ POSSIBLE PATHS 0..N provisional (deterministic, zero LLM) → optional ROUTE (one pipeline)        §25.4
   ├─ APPLICABLE REQUIREMENT SET  which requirements apply, relative to context                        §25.2
   ├─ REQUIREMENT STATE READER    one ledger reader for Route, Readiness, and the Planner              §25.3
   ├─ READINESS PROJECTION        from the SAME paths/routes/state; read by UI, narrative, inspection      §25.3
   ▼                             (Readiness ≠ planner: the planner does NOT read it)
 QUESTION PLANNER (a pure function, policy m4.v1)                                                     §25.5
   │   → QUESTION | EVIDENCE_REQUEST | ACTION | HOLD   + machine-readable reason trail + replay       §25.6
   └─► user's answer / a real-world action → new evidence ↺
```

Single assembler: `mvp/app/navigation.py::navigate_session` (used by `/message`, `/navigation`, and tests); one turn: `mvp/app/turn.py::run_turn`. New code: `core/navigation/{applicability,requirement_state,planner,planner_input,planner_text}.py` (generic), `store/requirement_state.py`, `ontology/mapper/live_adjudication.py`, `domains/revenue/navigation/live.py` (the Revenue plugin), `app/static/js/nav-move.js` (UI).

Three guarded separations: **(1) WHAT vs WHICH-NOW** — the Requirement Registry = what must hold (global, context-free); the Applicable Requirement Set = which are relevant now (context-relative); Requirement State = what their state is for this user (the ledger). **(2) proposal vs decision** — the LLM and the mapper only propose; deterministic adjudication and the planner decide. **(3) conversation vs state** — phases have no authority; the only thing that determines the next step is state and its uncertainty.

### 25.2 Applicable Requirement Set — which requirements apply

`core/navigation/applicability.py` (generic, pure). The registry gets **no** applicability/route/strategy fields: a requirement's applicability is always **relative to a context**, and that context is what declares relevance:

| Context | Declares a requirement via | Applicability carried |
|---|---|---|
| Possible Path | `check.requirement_id` (the domain declares: this path needs that world condition) | the path's applicability |
| Route | `node.resolves[0]` | the route's applicability (`UNDETERMINED` → `UNKNOWN`) |
| A route template that was not born | `node_candidates[*].resolves` — only when the composer declares `NOT_APPLICABLE` | `NOT_APPLICABLE` |

Aggregation per requirement (three values, not a score): `APPLIES` when ≥ 1 context APPLIES · `UNKNOWN` when nothing APPLIES but some context is not yet decided · `NOT_APPLICABLE` when EVERY declaring context is NOT_APPLICABLE. Output contract: `{version, items:[{requirement_id, applicability, reason, contexts:[{kind, id, applicability, via, strength, navigable, ref}]}]}` with `reason` ∈ `APPLIES_VIA_CONTEXT` · `UNKNOWN_CONTEXT_APPLICABILITY` · `NOT_APPLICABLE_IN_ALL_CONTEXTS`.

- A requirement **declared by no context is not a member** of the set: the registry is not a checklist, and "no context" is not "applies". Adding a requirement to the registry (49 → N) changes nothing in this module; a new requirement joins if — and only if — a context anchors it.
- `navigable` ≠ applicability: a STOP path (engine or lifecycle) still has its own applicability, but its context never drives the conversation (NextMove is never chosen from a STOP path, §12). Two axes, never merged.
- A path check **without** a `requirement_id` is not a requirement (a path-specific condition); it still becomes a planner need (§25.5) through its signal.
- A non-CURRENT PathSet (LEGACY, §11) has its content never read: an empty set, not an invention.

### 25.3 Requirement State Reader — one reader for Route, Readiness, and the Planner

`core/navigation/requirement_state.py` (the contract, generic) and `store/requirement_state.py` (a user-scoped ledger reader). `RequirementState{requirement_id, satisfaction, adjudicated, evidence_refs, verification, last_updated, conflict, support}`:

| Aspect | Rule |
|---|---|
| `UNKNOWN` because nothing was adjudicated (`adjudicated=false`) vs an adjudication that produced `UNKNOWN` (`adjudicated=true`: the evidence was indecisive, or two sides conflict) | distinguished; neither is ever downgraded to `ABSENT`. The constructor rejects states, citations, or origins WITHOUT adjudication (never invented) |
| `support` — can CONVERSATION evidence move this state? | `FORMAL_RULE` (a reviewed formal rule exists) · `UNIT_CONTEXT_REQUIRED` (a rule exists, needs a non-derivable unit identity) · `NO_FORMAL_RULE` (the rule is still prose) · `NO_USER_SCOPE` (a session without a user: no ledger). A statement about COVERAGE, not about the user's state |
| Scope | the reader is bound to one validated `user_id` (fail-closed); A's status is never read for B; anonymous sessions → `NO_USER_SCOPE` (never a shared ledger) |
| Write | the reader is pure; the ledger's only write door = `adjudicate_and_persist` (AST-tested) |

**One reader, one merge rule.** Route reads node states through the thin adapter `ontology/route/session_bridge.user_status_reader` over `LedgerRequirementReader`; the Question Planner reads the same `LedgerRequirementReader` (`read_requirement_views`); Readiness reads those route nodes and merges them with path checks via `merge_readings` — the **same function** the planner uses per context (`readiness._adjudicate` calls it; tested over the full matrix): a definite state beats `UNKNOWN`; two different definite states = a dispute (structured metadata, not a fifth value); `UNKNOWN` is never a disputing party. Proven end-to-end over real sessions: for every Readiness item sourced from a route node, its state equals the planner's reading in the same route context — after finalize (`test_m4_session_loop` F3/F3b) **and before finalize inside the loop** (RD3, from the same `/navigation` response).

**Readiness is computed in the loop, but it is not the planner.** `navigate_session` calls `build_projection` (frozen, v4) every turn over the same provisional paths + routes + state; the result feeds the UI, narrative, and inspection (`/navigation.readiness`, the per-turn `navigation.readiness` summary: executability + item counts per path). The planner **does not read it**: no M4 core module imports Readiness (`test_m4_planner` V6), decision inputs never carry it (RD4), and a failing projection is recorded in `errors` without changing the decision (RD5). Readiness answers "how ready is this path/route"; the planner answers "what needs to be known or done next".

**A watched boundary — CLOSED (M4.1, 2 Oct 2026).** Readiness now reads the ledger through route nodes **and**, for routeless paths carrying requirement-anchored checks, directly through the same `RequirementStateReader` as the planner (`build_projection(…, state_reader=status_reader(reader))`). Merging uses `requirement_state.merge_readings` — one primitive, no second evaluator; a definite state beats UNKNOWN; two different definite states = a dispute with `ledger` authority (structured metadata, never counted settled); UNKNOWN is never downgraded to ABSENT. Evidence: `evals/test_m4_readiness_routeless.py` (A1–A4, the route-backed regression R4 and the candidate-born route-less R5).

### 25.4 Live adjudication and provisional paths

**The adjudication producer** (`ontology/mapper/live_adjudication.py`). Before M4 this chain only lived in tests; the live session flow never filled the ledger. Now:

```text
EvidenceItem (Universal State; raw transcript FORBIDDEN; is_gap evidence NOT admitted)
  → MAPPER (propose_deterministic, one evidence per proposal)        PROPOSAL, not status
  → deterministic VERIFICATION (verify_batch, two-gate)              VERIFIED only when the evidence satisfies ≥ 1 branch of a reviewed FORMAL rule
  → ADJUDICATION (core/stages/adjudicate)                            the SINGLE authority on status
  → user-scoped LEDGER (adjudicate_and_persist)                      idempotent: writes only when the result changes → a history of CHANGES
```

Coverage honesty (measured 2 Oct 2026 over the 49-entry registry): **3** requirements carry `FORMAL_RULE` support adjudicable from conversation (`access.icp`, `offering.exists`, `offering.differentiation`), **2** `UNIT_CONTEXT_REQUIRED` (`access.prospect_list`, `experiment.baseline_comparison`; the unit identity is not guessable), **44** `NO_FORMAL_RULE`. Requirements without a formal rule **never get predicates invented**: they stay `UNKNOWN` by absence, and the planner does not ask about them as if the answer would move them (the ASK vs ACT channels, §25.5). The formal coverage is partial and lexical (Indonesian keywords): that is a known limit (§22), not the user's state. Adding formal rules = data (`formal_rules_compiled.json`), not planner changes.

What is deliberately **not** done: the mapper never becomes the status authority; unverified proposals never touch the ledger; there is no ledger entry for requirements without verified evidence (absent adjudication is never fabricated into a record); proposals are not bundled across evidence (`text_absent_pattern` predicates are global over the admitted set: bundling silently produces false negatives); stale formal rules (a registry fingerprint mismatch) → no adjudication and a recorded `STALE` reason.

**Provisional paths** (`domains/revenue/navigation/live.py`). Every turn a 0..N PathSet is formed through the SAME deterministic path as diagnosis: `build_revenue_state` + the graph view → detected mechanisms (catalog keywords) → **tier-1** KB rules over **the USER'S OWN words only** → `build_possible_paths`, no LLM. *Provisional*: tier-2 rules (LLM-dependent) apply at diagnosis, so diagnosis may find more, never less, than the turn's facts. The engine's own sentences (its questions) are not evidence: letting them trigger rules/mechanisms would let a question prove its own answer. Routes are composed through the one `compose_path_routes` pipeline (§24.8), optional.

### 25.5 The Question Planner (`core/navigation/planner.py`, policy `m4.v1`)

The question the planner answers: *what is the most valuable information or action still needed NOW to reduce uncertainty or open a valid navigation step?* — never "question number N of phase X". It is a **pure function** `plan_next_move(input) → decision`: no LLM, store, network, or clock calls (`test_m4_planner` V1: the import guard). The LLM may only render wording or interpret language; it is never the authority on status, applicability, readiness, satisfaction, contradictions, order, or next-step policy.

**Input** (`planner_input.assemble_planner_input`; JSON-safe): `goal`, `paths` (applicability, status, checks, navigable), `routes` (nodes, dependencies, executability), `facts_missing`, `requirements` (satisfaction, adjudicated, conflict, support, `contexts[]`), `signals` (the ASK/ACT channel per signal), `next_move_v1` (the route selector's output), `history.asked` (how often each need was already asked — computed from logs, not mutable state). `applicable` and `texts` are attached for inspection and display but are **not decision inputs** (excluded from `input_digest`).

**Stages** (in order; the first stage producing a decision wins, and every decision carries its reason):

| Stage | Condition | Decision |
|---|---|---|
| `GOAL` | the goal is not yet proven | `QUESTION` · `RESOLVE_GOAL` |
| `CONTRADICTION` | a disputed requirement in a navigable context | `EVIDENCE_REQUEST` · `RESOLVE_CONTRADICTION` (discriminating evidence; the dispute is never forced closed) |
| `APPLICABILITY` | a navigable path with `UNKNOWN` applicability and an askable fact | `QUESTION` then `EVIDENCE_REQUEST` · `RESOLVE_APPLICABILITY` (the fact that makes applicability decidable) |
| `STATE` | a requirement or check still `UNKNOWN` in an `APPLIES` + navigable context, dependency-ready, and **answerable** through conversation | `QUESTION` then `EVIDENCE_REQUEST` · `RESOLVE_STATE` / `COLLECT_EVIDENCE` |
| `EMERGENCE` | no navigable path | `QUESTION` · `RESOLVE_STATE` over path-forming facts (never guessing paths) |
| `DOWNSTREAM` | NextMove v1 (the route frontier selector) | `ACTION` · `QUESTION` · `EVIDENCE_REQUEST` · `HOLD` — **forwarded, not duplicated**. One adjustment: another route's applicability question never holds back EXECUTE on a route that already applies |
| `FALLBACK` | a navigable path exists → `ACTION` · `PRESENT` (enough is mapped); otherwise `HOLD` | |

The rules that keep it honest:

- **The ASK vs ACT channels.** Only what conversation can move is asked: requirements backed by a `FORMAL_RULE`, or path checks whose signal is readable from state. Everything else (signals that are always unmeasured from state, requirements without a formal rule) = `ACT`: handed to actions on the route and to outcome evidence; asking them repeatedly is an endless loop.
- **Dependencies A → B → C** (HOW = route node `depends_on`; the registry = WHAT): while a node's dependencies are not `PRESENT`, the planner does not dig into that need (`DEPENDENCY_UNRESOLVED:<req>` recorded).
- **Knowing when to stop asking.** One need is asked at most `ASK_CAP` = 2 times (`QUESTION` then `EVIDENCE_REQUEST`); afterwards it is skipped and recorded `ASKED_ENOUGH`. Non-navigable contexts (STOP paths: engine OR user decision) never drive the conversation.
- **No business ranking.** Ordering among equal needs = deterministic information policy: condition strength (`hard` → `prereq` → `soft`), how many contexts need it, dependency depth, then the id. Not "the best".
- **Fail-safe.** A different or incomplete input version never produces invented questions: fall back to `HOLD`. Navigation failing mid-turn → `degraded_navigation`: an honest `HOLD` + the error visible in `navigation.errors`; the conversation never crashes and the next turn recovers (`test_m4_session_loop` FS1–FS3).

**Free order and direction changes.** Extraction does not depend on what was asked last (`extract_turn`: no phases, no question): one message may carry several facts, or facts nobody asked about. Every fact becomes evidence and only moves the requirements its rule satisfies (one answer ≠ `PRESENT` for everything). Because decisions are recomputed from state every turn, answering something else resolves *that* need and the next question follows state, not a script; new evidence can birth new paths (e.g. running revenue birthing the repricing and expansion directions) and shift the planner's focus **without a session restart**. Two different answer orders produce equivalent final states (paths, applicability, satisfaction), with conversation trajectories that may differ (`test_m4_session_loop` I1–I4, J1–J3).

**Candidates, Possible Paths, and optional Routes.** Provisional paths use the same generator and evaluator as diagnosis, so candidates born from mechanisms (e.g. `lead_leakage` → `path.fix_response_before_more_leads`) appear as ordinary Possible Paths: they count as navigable paths, carry no checks or routes (nothing invented), and trigger no invented questions. No candidate-origin special branch exists in the planner, applicability, or the reader (AST in `test_m4_applicability` M; E2E `test_m4_session_loop` K1–K5). Routes are optional: the planner accepts empty `routes` (anonymous sessions, paths without templates); a path without a route is still navigable via its checks and, when no needs remain, yields `ACTION` · `PRESENT`.

### 25.6 The NextMove contract, reason trail, replay

```jsonc
{ "version": 1, "policy": "m4.v1",
  "kind": "QUESTION | EVIDENCE_REQUEST | ACTION | HOLD",
  "intent": "RESOLVE_GOAL | RESOLVE_APPLICABILITY | RESOLVE_CONTRADICTION | RESOLVE_STATE | COLLECT_EVIDENCE | EXECUTE | PRESENT | WAIT",
  "focus": { "type": "goal | requirement | check | path | route | node | signal | navigation", "id": "…" },
  "stop": false,                      // true = stop asking (ACTION / HOLD)
  "payload": { },
  "reason": {
    "stage": "STATE", "need_id": "requirement:access.icp",
    "why": ["applicability=APPLIES", "satisfaction=UNKNOWN", "navigable_contexts=1", "dependency_ready=true",
            "strength_rank=1", "resolvable_by=ASK", "asked_before=0", "blocks_next_decision=true"],
    "contexts": [ ],                  // the contexts (path / route) declaring this need
    "considered": [ { "need": "…", "verdict": "SELECTED | DEFERRED | SKIPPED",
                      "why": "ASKED_ENOUGH | NOT_ASKABLE_ACT | DEPENDENCY_UNRESOLVED:… | LOWER_INFORMATION_PRIORITY" } ],
    "counts": { "applicable": 13, "navigable_paths": 3, "resolved": 2, "open_askable": 1, "open_act_only": 9 },
    "input_digest": "…" } }
```

- **Reason trail** machine-readable (not prose): every decision carries the stage, the need, the reasons, the contexts, what was considered and skipped, plain need counts (no scores), and the decision input's fingerprint.
- **Replay** (`planner.replay`): `{input, decision}` stored → recompute → identical or not (`ok`). `input_digest` covers decision inputs only (no `texts`, no `applicable`).
- **Per-session decision log** (`Session.planner_log`, persisted to disk): `PLANNER_LOG_CAP` = 25 entries; only the last `REPLAY_WINDOW` = 5 entries keep their INPUT (the rest keep decision + text + digest). Replaying a compacted entry reports `ok=None` with reason `COMPACTED` — never "passed". The "already asked" counters are read from the stored log, so turns older than the last 25 are forgotten (old needs may be asked again; the limit is intentional for file size). The session file after 10 turns ≈ 250 KB (before compaction ≈ 645 KB).
- **Text** (`planner_text.render_move`, deterministic, en/id): wording from Requirement Presentation + sentence frames. An `ACTION`/`HOLD` step EXACTLY identical to the one just presented is voiced as "unchanged" ("Noted. Your next step has not changed: …") instead of repeating the identical sentence; that is wording only (the predecessor decision is not a decision input, excluded from `input_digest`), and questions are never treated as repeats. **No LLM rewording yet** (the contract is ready: the LLM may only rewrite already-decided text and never changes the decision; FUTURE, §22).
- `progress` (clarity) = the share of answerable needs already answered (max 0.95); `1.0` only on an `ACTION` decision. Never `(phase index + 1) / 5`.

### 25.7 API and cost

| Endpoint | M4 behavior |
|---|---|
| `POST /session/{sid}/message` | one round of the state loop (§25.1). The `InterviewTurn` response: `next_move` (`kind, intent, focus, stop, text, headline, reason, policy`), `navigation` (summary: `counts, stage, adjudication{…}, paths[{path_id, status, applicability}], readiness[{path_id, executability, counts}], errors`), `next_question` (= the text when `QUESTION`/`EVIDENCE_REQUEST`, otherwise `null`), `progress`, `evidence_delta`, `intent_tags`. Since M5 the response **no longer carries** `phase`/`phase_index` (§26.4); `kind` ∈ `probe` · `ack`. An already-`finalize`d session → `kind="ack"`, `next_move=null` (the old behavior) |
| `GET /session/{sid}/navigation` | inspection: `move` = the step **currently presented** (the last logged decision; not the next one to be decided, since asking something raises the "already asked" counter), `in_sync` / `recomputed` (when state changed since it was presented), `applicable`, `requirements` (full states + origins), `readiness` (the full projection over the same state), `summary`, `asked`, `history`, `last_logged.replay` |

Per turn: 1 extraction call (`extract_turn`) + 1 graph-understanding call (`understand_turn`, predating M4); the navigation stages (adjudication → paths → routes → applicable → reader → planner) = **0 LLM calls**, and never 49 × LLM per turn. Measured 2 Oct 2026 (`mock` provider, dev machine): a mean of 0.08s per turn for the entire deterministic portion including persistence (max 0.27s on the first turn).

### 25.8 UI: the state-driven conversation

`app/static/js/nav-move.js` and `screens-live-chat.js` only render engine decisions; no decision logic lives in the client. Engine messages carry a step-kind caption ("Question", "Needs evidence", "Ready", "On hold"; raw enums never display). The "What we are asking about" box shows the focus, a one-sentence reason, and a `<details>` "Why we ask this" / "Why we can stop asking" / "Why we paused" containing the reason in plain language plus the "Engine trail" (stage, need, reason tokens, `input_digest`): the machine trail is inspectable from the UI. The header pill states the conversation's state in words ("3 clear, 1 still to learn", "Ready to map", "On hold"), never a step bar. No phase, act, or "step n of 5" words. Reloading the conversation restores what is being asked and why from the server (`/navigation`). Guarded by `e2e/conversation.spec.mjs` (8 scenarios, visual baselines `conv-*.png`, axe WCAG A+AA, light/dark/390px, zero console errors).

### 25.9 Invariants, failure modes, and deliberate limits

**Phases are not an authority (INV-7 item 4, int 10).** M4 proved phases "present but not an authority" (positive control: `analyze_turn` still detected). **M5 deleted that engine** (§26): the guard is now `test_m5_phase_removal` — zero phase-engine identifiers across all production code, negative tests per identifier, and negative properties (phases/topics/turn counts never change decisions). Diagnosis is never phase-gated (`synthesize` no longer takes a phase parameter).

| Failure mode | Guard |
|---|---|
| Phases or fixed order still determining questions | a pure planner over state; AST guards + positive controls; free-order tests (two answer orders → equivalent final states, different trajectories) |
| The LLM deciding steps or status | the planner imports no LLM/store/network (V1); the LLM only `extract_turn` (proposal) |
| Planted requirement or question lists | the applicable set from contexts; registry extensibility tests (new requirements without planner code changes); K2 / `core_scope` (a generic planner with no domain lexicon) |
| The mapper or LLM writing status | the single write door `adjudicate_and_persist`; proposals never touch the ledger; PROPOSED ≠ VERIFIED ≠ satisfaction |
| "Not mentioned" becoming "not there" | `adjudicated=false` ≠ adjudicated `UNKNOWN`; no ledger entries without evidence; no requirement becomes `ABSENT` for being unmentioned |
| Gap evidence read as proof | `is_gap` never admitted at the live boundary |
| One answer treated as satisfying everything | per-evidence proposals + formal rules per requirement; a multi-fact message maps several needs, other requirements stay `UNKNOWN` |
| Asking forever, the already-answered, or the unanswerable | `ASK_CAP`, the ASK/ACT channels, dependencies; test I3 (never re-asks the answered) |
| A contradiction swallowed | the `CONTRADICTION` stage → `EVIDENCE_REQUEST`; disputes = metadata |
| Status leaking across users | the reader + ledger per `user_id`; anonymous sessions have no ledger |
| Broken navigation crashing the chat | `degraded_navigation` (an honest HOLD + visible errors); optional routes with recorded errors |
| Decisions not inspectable | reason trail + `input_digest` + replay; `/navigation.in_sync` |

**Deliberate limits and what does NOT exist** (detailed in §22): partial, lexical formal rule coverage (3 of 49 requirements adjudicable from conversation); `ASK_CAP` can spend up to 2 turns per hard-to-satisfy adjudicated requirement; deterministic decision wording (LLM rewording = FUTURE); identical `ACTION` decisions may repeat when state does not change (worded as "unchanged"); evidence topic labels (`topic`) are display only; live extraction depends on a real LLM provider (tested with: the deterministic mock). `make gate-smoke` **was run** at the M4 closure (2 Oct 2026, see §25.9 live LLM): attempt 1 → 19/20 (one lexical NBA heuristic), attempt 2 (the Makefile's built-in retry) → 20/20 `DOD MET`, exit 0 — its word heuristic depends on the LLM's word choice, so it is not proof of determinism; the deterministic gate remains `make gate-fast` (M4.2 added F3d to gate-fast, see §25.9).

### 25.10 Invariant → implementation → test → E2E map

| Invariant | Implementation | Test | E2E |
|---|---|---|---|
| M4-01 conversation driven by state, not phases (INV-7) | `planner.py`, `app/turn.py`, `app/navigation.py` | `test_m5_phase_removal` R1–R5, G1–G4, N1–N6 (formerly `test_m4_no_phase_authority` P1–P7); `test_m4_session_loop` X1–X2 | `conversation.spec` 01–02 |
| M4-02 applicability from context, not registry fields or lists | `applicability.py` | `test_m4_applicability` A, L, axes | — |
| M4-03 registry extensible (49 → N without code changes) | `applicability.py`, `planner.py` | `test_m4_applicability` B; `test_m4_planner` B | — |
| M4-04 one Requirement State Reader (Route, Readiness, Planner); Readiness computed in the loop but not the planner | `requirement_state.py`, `store/requirement_state.py`, `session_bridge.py`, `readiness.py` (`merge_readings`), `app/navigation.py` | `test_m4_applicability` merge / reader; `test_m4_live_adjudication` E; `test_m4_session_loop` O7, F3, F3b, F3d, RD1–RD5; `test_m4_planner` V6 | `conversation.spec` 03 |
| M4-05 UNKNOWN ≠ ABSENT; un-adjudicated ≠ adjudicated-UNKNOWN | `RequirementState`, `live_adjudication.py` | `test_m4_applicability` C; `test_m4_live_adjudication` C; `test_m4_session_loop` O11 | — |
| M4-06 the mapper only proposes; adjudication the single authority; one write door | `live_adjudication.py`, `store/adjudication_ledger.py` | `test_m4_live_adjudication` D + single-door (AST); `test_adjudication_path` | — |
| M4-07 live adjudication wired to `/message` without loosening contracts | `live_adjudication.py`, `app/navigation.py` | `test_m4_live_adjudication`; `test_m4_session_loop` O5, O10 | `conversation.spec` 03 |
| M4-08 a pure, deterministic planner without an LLM | `planner.py` | `test_m4_planner` V1, R6 | — |
| M4-09 four step kinds; uncertainty-driven; dependencies A → B → C | `planner.py` | `test_m4_planner` F, dependencies, uncertainty-driven | `conversation.spec` 01–03, 07 |
| M4-10 knowing when to stop asking; ready-to-act | `ASK_CAP`, the `DOWNSTREAM` / `FALLBACK` stages | `test_m4_planner` K, loop guard; `test_m4_session_loop` O8, H1 | `conversation.spec` 03–04 |
| M4-11 direction changes | planner + provisional paths | `test_m4_planner` J; `test_m4_session_loop` J1–J3 | — |
| M4-12 contradictions and applicability uncertainty | the `CONTRADICTION`, `APPLICABILITY` stages | `test_m4_planner` G, G4, H | — |
| M4-13 no relevance → no invented questions | `planner.py` | `test_m4_planner` L, emergence | `conversation.spec` 07 |
| M4-14 candidate-born and route-less through the same pipeline | `compose_path_routes`, `applicability.py` | `test_m4_applicability` M, N; `test_m4_planner` 0..N paths; `test_m4_session_loop` K1–K5, F3e | — |
| M4-15 free order; multi-requirement evidence | planner + live adjudication | `test_m4_session_loop` I1–I6 | `conversation.spec` 02 |
| M4-16 reason trail + replay + compacted logs | `planner.py`, `app/navigation.py` | `test_m4_planner` R1–R10; `test_m4_session_loop` P1–P6 | `conversation.spec` 01, 05 |
| M4-17 user and session scoping | `store/requirement_state.py` | `test_m4_live_adjudication` 35; `test_m4_session_loop` S1–S6 | — |
| M4-18 bounded cost + fail-safe | `degraded_navigation`; zero LLM in navigation | `test_m4_session_loop` FS1–FS3, F5 | `conversation.spec` 08 |
| M4-19 a state-driven, inspectable, accessible UI | `nav-move.js`, `screens-live-chat.js` | — | `conversation.spec` 01–08; `live.spec` |
| M4-20 API compatibility (old fields, finalize, old sessions) | `app/main.py`, `store/memory.py` | `test_m4_session_loop` X1–X5, F1–F4, P5 | `live.spec` |

Commands: `make test-m4` (the five deterministic suites `evals/test_m4_*.py`, also part of `make gate-fast`); UI: `make test-ui` (or `cd mvp/e2e && npx playwright test conversation.spec.mjs`; the mock server on port 8765).

### 25.11 Relation to M5 and other documents

**A map of this section.** WHY: §25.1 · WHAT: §25.2 (Applicable Requirement Set), §25.3 (Requirement State), §25.6 (the NextMove contract) · WHERE: §25.1 (modules), §25.10 (implementation per invariant) · HOW: §25.4 (live adjudication, provisional paths), §25.5 (planner policy), §25.7 (API and cost), §25.8 (UI) · AUTHORITY: §25.1 (the three separations), §25.3 (one reader), §25.5 (a pure planner), §25.9 (phases are not an authority) · INVARIANTS: §25.9, §25.10 · FAILURE MODES: §25.9 (table) · TEST CONTRACT: §25.10 and §19.

M5 (§26) deleted the phase engine, `analyze_turn`/`build_turn`, the `phases.json` probes, and the `phase` fields; M4 only ever guaranteed that engine had no authority. The Route contract (`04-knowledge-substrate/08`) and the Requirement Registry (`04-knowledge-substrate/09`) are unchanged; the planner reads both through the existing contracts.

---

## 26. M5 — removing the phased interview engine

> **Status**: **IMPLEMENTED, TESTED** (2 Oct 2026; branch `iteration/universal-navigation-m5-phase-removal`). M5 is **not a new authority migration** (authority already moved in M4, §25): it purifies the architecture by deleting the phased interview engine that remained as revivable dead code. Per-item evidence: [`../05-proof-and-gates/08-m5-completion-matrix.md`](../05-proof-and-gates/08-m5-completion-matrix.md).

### 26.1 Three meanings of "phase" — what was removed and what was kept

| Category | Examples | Fate in M5 |
|---|---|---|
| **Interview phases (LEGACY INTERVIEW PHASE)** | `GOAL · REVENUE_STATE · MOTION · DEMAND · CONVERSION` as stages the conversation walks through; `PHASES`, `phase_index`, `turns_in_phase`, `MAX_TURNS_PER_PHASE`, `phase_has_hard_evidence`, `phase_gap_count`, `analyze_turn`, `build_turn`, `format_probe_hints`, `probes_for_phase`, `phases.json` | **DELETED** from production code |
| **Persistence / API compatibility fields** | `Session.phase`, `turns_in_phase`, `phase_index`, `InterviewTurn.phase`, the `phase` key on stored evidence | **Read-only when needed on old data, never written, no effect** (§26.3) |
| **Domain phases that are NOT interview phases** | `E2E_PHASES` = `PRA_SALES · SALES · AFTER_SALES` (`domains/revenue/stages/journey.py`, the `e2e_phase` tag on KB interventions) | **KEPT**: that is the user's position in the commercial journey (an intervention applicability filter), not a conversation stage |

The word `phase` was not removed by string. What was removed is the interview phase's **authority and runtime dependencies**; every remaining occurrence has an explicit reason (§26.9).

### 26.2 What was deleted

- **The phased interviewer**: `agents/interview.py::analyze_turn`, `build_turn`, `InterviewAnalysis`; the interviewer's `SYSTEM` prompt (`domains/revenue/prompts/interview_system.py`) and `domains/revenue/prompts/phase_openers.py` (per-phase opener/goal). What remains in that module is state-free extraction: `extract_turn`, `TurnExtraction`, `NumberClaim`, `EXTRACTION_SYSTEM`. The LLM still only **interprets** (evidence, number claims, intent tags); status, applicability, readiness, routes, and NextMove remain the deterministic engine's. *(Follow-up note 15 Oct 2026 — legacy cleanup: `extract_turn` + `EXTRACTION_SYSTEM` were removed; the module now only holds the `TurnExtraction`/`NumberClaim` type contracts for the semantic-derivation path `core/semantic/`; evidence `../05-proof-and-gates/state-discovery-recovery/15-legacy-cleanup-consolidation.md`.)*
- **The Session model**: `Session.phase`, `turns_in_phase`, `phase_index`, `phase_has_hard_evidence()`, `phase_gap_count()`, `MAX_TURNS_PER_PHASE`, `HARD_TURN_CAP`.
- **Schemas**: `Phase`/`PHASES`, `InterviewTurn.phase`/`phase_index`, `kind="phase_transition"`, `core/schema/phases.py` (`PhaseModel`, `PhaseDeclaration`).
- **The knowledge engine**: `probes_for_phase`, `format_probe_hints`, `phase_config`, `probe_hint_budget`, `ontology/knowledge/phases.json`, the `phase` parameter on `active_rule_sources`, `candidate_rules`, `candidate_anti_patterns`, `match_tier1`, `run_knowledge_rules`, `knowledge_activation_log`, `synthesize`.
- **Funnel logs**: the `phase` column (never read).

### 26.3 Old data

- Old session files carrying `phase` / `turns_in_phase` **still load**: the loader only takes the fields `Session` knows, so those keys are ignored and never influence the planner, paths, requirements, readiness, routes, or NextMove. Re-saving an old session never writes those keys back.
- Old evidence storing its label as `phase` still reads: `EvidenceItem.topic` accepts the `phase` key as a **read alias** (`validation_alias`), and new serialization always writes `topic`. This alias is not a compatibility layer preserving the phase engine: there is no logic behind it, and tests verify the label never changes decisions.
- New sessions never write `phase`, `turns_in_phase`, or `phase_index`, never record phase transitions, and never store phase progress.

`EvidenceItem.topic` is a **display grouping label** (the evidence panel in the UI; a free value; the `GOAL/REVENUE_STATE/MOTION/DEMAND/CONVERSION` vocabulary is only panel grouping). It is never read by navigation, the planner, requirements, readiness, routes, or paths (`test_m5_phase_removal` N1–N2).

### 26.4 The API contract

| Endpoint | After M5 |
|---|---|
| `POST /session` | no `phase`; still `session_id`, `goal`, `first_question` |
| `GET /session/{sid}/state` | no `phase`/`phase_index` |
| `POST /session/{sid}/message` | `InterviewTurn` without `phase`/`phase_index`; `kind` ∈ `probe` · `ack` (no `phase_transition`); `evidence_delta[*]` carries `topic` |

Migrated consumers: `screens-live-chat.js` and `screens-live-reveal.js` group evidence by `topic`; the manual/live evaluation scripts no longer read `phase`. The `InterviewTurn` class name is kept as the turn-response DTO name (a historical name; no phase meaning).

### 26.5 The knowledge engine boundary: `active_rule_sources` and `phases.json`

Dependency analysis: `active_rule_sources(phase)` is called by diagnosis, but its only live caller (`_diagnose`) has passed `phase=None` since M4, so what always ran was the **default list** (the nine sources `TM VP CS HK PR HG SP LC EM`), identical to the `CONVERSION` phase's list. Per-phase rule-source gating only ever existed for diagnosis in the middle of a phased interview. That is case **A** (part of the old interview engine), not a knowledge activation mechanism that happened to be named phase.

Decision: diagnosis was migrated to the canonical mechanism without phases, with **identical semantics**:

- `ontology/knowledge/rule_activation.json` (a typed contract in `core/schema/rule_activation.py`) declares one active rule-source list for the whole ledger; `engine.knowledge.active_rule_sources()` takes no arguments.
- `validate_knowledge.py` rejects prefixes not registered in `sources.json` and the absence of that file (`test_m5_phase_removal` K6–K8).
- `phases.json` is deleted. The Mom Test probes stay alive as **knowledge content** (`probes` in `ontology/knowledge/*.json`, validated and synced with markdown) but have no runtime consumer: there is no more per-phase prompt injection. Probes do not automatically become planner questions (§26.8).
- Proof the semantics did not change: the golden `evals/golden/deterministic_stages.json` (ranking, status, tier, confidence across all scenarios) shows no difference; the only delta is the `phase_model` block replaced by `rule_activation` (the same nine-source list as the old `__final__`). The diagnosis trace's `active_reason` text no longer mentions phases.

### 26.6 Invariants guarded

- No phase-engine identifier in any production code (an AST over the whole tree except the `evals/` harness), no phase-engine files, and the old symbols cannot be imported.
- **Negative properties** (not just "symbols are gone"): evidence topic labels, old phase keys, huge `turns_in_phase`, and turn counts never change NextMove; no "hard evidence per phase" gate produces a `HOLD`; free answer order and returning to an old topic never trigger a phase rollback.
- M4 and prior semantics unchanged: `PROPOSED ≠ VERIFIED`, `UNKNOWN ≠ ABSENT`, adjudication and the ledger, Possible Paths `0..N`, routes born because of applicability and readiness because of evidence, the `RESOLVE_APPLICABILITY`/`EXECUTE`/`VERIFY` frontiers, the `m4.v1` Question Planner (QUESTION / EVIDENCE_REQUEST / ACTION / HOLD).

### 26.7 The test map

| Test | Proves |
|---|---|
| `test_m5_phase_removal` (`make test-m5`) | R: the removal; G: guards are not vacuous; A: the API contract; P: persistence; C: old data (including every session file on disk); N: negative properties; K: rule activation; E: the domain E2E intact |
| `test_m4_session_loop` X1–X2, P5, F1 | the new API contract, old sessions loading without phase attributes, finalize without gating |
| `test_characterization` (golden) | diagnosis semantics unchanged |
| `test_e2e_phase` | the domain E2E (PRA_SALES/SALES/AFTER_SALES) alive |
| `test_knowledge_rules`, `test_unsupported_causal`, `test_knowledge_provenance` | the knowledge stage without a phase parameter |
| `e2e/conversation.spec.mjs`, `e2e/live.spec.mjs` | UI: no interview-phase display; the state-driven conversation flow intact |

### 26.8 What is NOT part of M5 (known debts)

M5 is not the closure of every Novaliners debt. Still open and unchanged here: formal adjudication coverage (3 of 49 requirements from conversation), the LLM candidate producer, quantitative VoI, a `PAUSED` producer, one route per path in readiness projection, deterministic decision wording, the diagnosis-control overflow in the 390px viewport, `GeminiProvider`, Cloud Run, Firestore, the Next.js shell, and the pilot. KB probes without a runtime consumer (§26.5) are knowledge content awaiting a product decision (e.g. as `EVIDENCE_REQUEST` material), not a hidden engine.

### 26.9 The inventory of remaining "phase" words (all explained)

| Occurrence | Class | Reason |
|---|---|---|
| `E2E_PHASES`, `infer_e2e_phases`, `e2e_phase` (KB), `test_e2e_phase.py`, `interventions_for(..., e2e_phases=)` | **a domain concept** | commercial-journey stages, not interview phases (§26.1) |
| `EvidenceItem.topic` `validation_alias=("topic","phase")` in `core/schema/evidence.py` | **read compatibility** | old stored evidence; never written |
| loader comments in `store/memory.py` | **read compatibility** | explaining why old keys are ignored |
| `evals/test_m5_phase_removal.py` (the forbidden-identifier list, test sessions tainted with `phase`) | **a test** | proving the removal and compatibility |
| historical text in `internal-docs`, `internal-docs,4,7]`, `internal-docs`, `internal-docs` | **historical documentation** | HISTORICAL/RESEARCH bannered (int 15) |
| `domains/revenue/prompts/explain_system.py` ("No phases") | **unrelated** | an explain-copy style ban for the user |
| `screen02()` in `screens-onboarding.js` (demo mode: "Step n/5 · Goal / Income / What you tried / Interest / Buying", a `Phase:` comment) | **a scripted demo, disconnected from the engine** | a v9 prototype screen over static data (`STORE.chatStep`), locked by pixel parity (`make test-ui-parity`); not the live flow (`screens-live-chat.js`, which shows no phases) and not a product contract (int 15: demo mode ≠ contract) |
| the CSS classes `.phase-tabs-row`/`.phase-tab-item` | **deleted** | dead code with no users; a leftover of the phased interview UI |

