> **Status**: 🟡 **PLAN / ADR** — planning-era decision; actual implementation partially differs (see banner)
> **Topic**: Final tech stack of the Revenue Navigation prototype - AI Builder Cup 2026 (full research: local projects + internet, September 2026) + ADR FastAPI vs Elysia + product architecture clarification (not a chat app)
> **Updated**: 2026-10-01 (documentation reconciliation: banner/classification/references; content last updated 2026-09-12)
> **Tags**: techstack, gemini, vertex-ai, adk, cloud-run, firestore, python, fastapi
> **Related**: `internal-docs` (§9.1 architecture), `internal-docs` (§8.4, §11)

>
> **⚠️ PLANNING-ERA PLAN / ADR (12 Sep 2026) — not the state of the code**
>
> This document records the stack decision made during competition planning. **Most of it followed the plan, part of it is not implemented** (verified against `mvp/pyproject.toml` and the code, 1 Oct 2026):
>
> | Decision in this document | State of the code |
> |---|---|
> | Python 3.12+, FastAPI, Pydantic v2, structured output | **implemented** |
> | Swappable LLM provider (`LLMProvider`) | **implemented** (`vertex`, `gemini` — both live since 16 Oct, see [21](21-gemini-provider-live.md) & [22](22-cloud-run-deployment-and-two-repo-workflow.md) — and `mock`; `opencode_go` & `zai` removed 19 Oct) |
> | Google ADK 2.0 as agent framework | **not used** (no ADK dependency; `agents/` uses its own provider) |
> | Gemini 3.x via Vertex AI, Cloud Run | **partial**: Gemini via the Gemini API + Vertex AI (REST, account-bound API key) are both live; **Cloud Run service not live yet** (setup ready, see [22 §5](22-cloud-run-deployment-and-two-repo-workflow.md)) |
> | Firestore for session/trajectory | **not implemented** (store = JSON/JSONL files + memory) |
> | Next.js app shell | **not used** (vanilla JS static UI in `mvp/app/static/`) |
> | LLM only in reasoning nodes; deterministic logic separate | **implemented, with a different module map**: `core/` + `core/navigation/` + `domains/revenue/` (not a single `engine/`) |
>
> Current navigation architecture: [`14-universal-navigation-architecture.md`](14-universal-navigation-architecture.md). Document map: [`15-documentation-canonicalization.md`](15-documentation-canonicalization.md).
---

# Tech Stack - Revenue Navigation Prototype

## 1. Stack Decision (Lock)

| Layer | Technology | Reason |
|---|---|---|
| **Language** | Python 3.12+ | ADK is Python first-class; the `google-genai` SDK is most mature in Python; the team is already familiar from the tooling ecosystem |
| **Reasoning Engine** | **Gemini 3.x via Vertex AI** (competition requirement) | Structured output: 100% valid JSON via `response_schema` + `response_mime_type` |
| **Agent Framework** | **Google ADK 2.0** (`google-adk`) | SequentialAgent matches the blueprint; built-in session/state management; official Cloud Run deploy path |
| **Orchestration / API** | **FastAPI** on **Cloud Run** | Already fixed by the blueprint; Cloud Run = mandatory competition requirement |
| **State / Memory** | **Firestore** (ADK session + trajectory persistence) | Makes the Adaptive Learning Loop (S15) real, not a static chatbot |
| **Knowledge Base** | **Curated grounding table** (30–50 benchmark entries, injected into prompts) | Decision `04` §11 — not full RAG Engine for the MVP |
| **Confidence** | Two-layer: Gemini structured assessment + deterministic Python aggregation (ADK tool) | Reproducible demo, auditable reasoning trace |
| **Data validation** | **Pydantic v2** | Schema contract (IntentObject, EvidenceItem, ReadinessAssessment, Decision) |
| **Frontend** | **Next.js/React app shell** — interview screen + diagnosis dashboard + reasoning trace + reality check panel (not a chat app, see §6) — polish in Week 4 | Scope discipline `04` §11.7; UX components from `02` §7.5 & `04` §10.2, §13.1 |
| **Repo** | Public GitHub from H1 | Submission requirement |

> **Compliance path (locked 12 Sep 2026):** Route A — *prototype integrates a Gemini/Gemma model*. The competition rules (`aibuildercup.com/themes.html`) offer 2 routes: (A) the prototype integrates Gemini/Gemma, OR (B) built via Agent Platform/Antigravity/AI Studio. We take **Route A**: (1) the **product** must call Gemini via Vertex AI + deploy to Cloud Run/Firestore; (2) the **build process is free** — dev tools & personal coding LLMs (Copilot BYOK, etc.) are not governed by the competition; only submission artifacts are evaluated; (3) Antigravity does not support BYOK (fixed model list, official docs 12 Sep 2026) — irrelevant for Route A. The deck narrative still highlights the full Google stack at the **product** layer.

> **FE note:** "chat" in the Week 1 plan = **a diagnostic interview interface** (structured branching tree), not a chat product. The system's main output is **structured artifacts** (Revenue Diagnosis, Reality Check, Reasoning Trace) rendered as UI components — not free-text replies.

## 2. Internet Research Findings (verified 11 Sep 2026)

### 2.1 ADK has reached version 2.0 (breaking intel)

- ADK is now available in **Python, TypeScript, Go, Java, Kotlin**; docs moved to `adk.dev`
- **ADK 2.0 introduces Graph Workflows** — "weave deterministic code with adaptive AI reasoning", explicit execution paths. This is *very* relevant to the S0–S15 Diagnostic State Machine: a graph workflow can represent the state machine natively (deterministic routes + LLM reasoning nodes), not just SequentialAgent
- Immediately usable features: **Sessions & State** (`adk.dev/sessions/state/`), **LoopAgent** (loop S4→S5 until confidence is sufficient), **Callbacks** (per-state guardrails), **Evaluation framework** (usable as a smoke test for the two trajectories), the official **Cloud Run deployment guide** (`adk.dev/deploy/cloud-run/`)
- Installation: `pip install google-adk`

**Implication for blueprint §11.3 (mapping S0–S15 to ADK):** the old Root=SequentialAgent option is still valid, but evaluate **Graph Workflows** for the state machine — deterministic transitions between states + LLM only in reasoning nodes (classify intent, assess evidence, generate probe). This strengthens the "what is LLM work vs rules" answer during judges' Q&A.

### 2.2 Gemini 3.x & structured output

- Current Gemini models (per Sep 2026 docs): **gemini-3.8-flash** (newest on the Gemini API), **gemini-3.5-flash** (example in Vertex AI docs), **gemini-3.1-pro-preview**. Pick the final one close to build time; check Vertex region availability
- Official SDK: `google-genai` (one SDK for the Gemini API + Vertex AI). Vertex: set `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_ENTERPRISE=True`
- Key structured output rules (Vertex AI docs, updated 9 Sep 2026):
  - `response_mime_type="application/json"` **WITHOUT** `response_schema` = only a hint, not 100% valid → **always set both**
  - **Do not duplicate the schema in the prompt** — it degrades output quality. Nuance goes in the schema field `description`
  - Complex schemas (deeply nested, long enums, many optionals) can hit `400 InvalidArgument` → split one large call into several small calls (the 4 core calls in `04` §13.4 are the right direction)
  - `propertyOrdering` controls generation order; if there are few-shot examples in the prompt, **field order must match** the schema
  - Fields default to **optional** → mark `required` explicitly; use `nullable` to reduce hallucination when context is thin
  - Always validate output in the app (Pydantic) + retry — "syntactically correct ≠ semantically correct"
- The Gemini 3 series supports **structured output + tools at once** (function calling, URL context) — an option if probe generation needs tools

### 2.3 Vertex AI rebranded

- Vertex AI docs now live under **"Gemini Enterprise Agent Platform"** (`docs.cloud.google.com/gemini-enterprise-agent-platform`). The `*-aiplatform.googleapis.com` API endpoints are unchanged. Don't get confused when googling — the competition term "Vertex AI" still applies

## 3. Insights from Local Projects (`/Users/ltmoerdani/Startup/`)

No existing project uses the Google Cloud stack yet — the transferable insight is **patterns**, not code:

| Project | Relevant insight |
|---|---|
| **campaign-forge** | (1) **Single-call structured generation**: one LLM call produces all connected assets via a Zod schema → prevents "angle drift". Apply: diagnosis synthesis in ONE call so evidence→constraint→decision stays coherent. (2) **Demo mode toggle** without an API key — useful for video rehearsal & judge preview. (3) Docs discipline: research → risk-assessment → architecture per folder (replicate the `docs/` structure in the competition repo) |
| **zeroclaw** | Multi-agent orchestration with per-agent identity files (IDENTITY/SOUL) → the "agent identity" pattern can be used for per-ADK-agent instructions (Sense/Diagnostic/Decision/Outcome) so each has a clear reasoning persona |
| **booking / blazz** (via memory) | Evidence-based verification & anti-regression discipline: every "it works" claim needs run evidence — matches the requirement "STOP/GO must reproduce consistently; if not, that's a bug before recording" |

## 4. ADR: Why FastAPI (Python), Not Elysia/Bun

**Context:** the team has Elysia experience (Blazz, Skowra). Choosing Python+FastAPI is a **competition-contextual** decision, not a claim that FastAPI > Elysia absolutely.

| Factor | Python | TypeScript/Bun (Elysia) |
|---|---|---|
| **ADK** | ✅ Google's primary reference: most complete & earliest features (sessions, state, callbacks, evals, Cloud Run deploy guide) | ⚠️ adk-js just hit GA 2.0 — younger, fewer examples & community |
| **`google-genai` SDK** | ✅ Most mature; every official Vertex AI docs example is Python first | Exists, but always the second example |
| **Google hackathon examples** | Majority Python | Minority |
| **Firestore** | Built-in ADK session service | Manual wiring |

Deciding arguments:

1. **The best-documented path = the smallest build risk in a 4-week window.** 40% of the criteria sit in Gen AI reasoning — energy must go to prompts/schemas/ontology, not fixing framework integration.
2. **A deterministic `engine/` is natural in Python.** Two-layer confidence = pure computation (weights × strength, aggregation, ranking). Latency is dominated by Gemini (seconds), not the web framework (milliseconds) — Elysia's throughput advantage is unused in a 1-user × 1-session × few-LLM-calls app.
3. **One Pydantic definition = three places used**: Gemini `response_schema`, ADK tool types, and the FastAPI response model.

**When Elysia wins:** the post-competition production product (traffic, SSE/WS streaming, FE/BE type-sharing in the Blazz monorepo pattern). Exit strategy: the Python reasoning layer stays intact, just wrapped by an Elysia gateway — the competition investment is not wasted.

## 5. Recommended Repo Structure

```
revenue-navigation/
├── app/                      # FastAPI entry (Cloud Run)
├── agents/                   # ADK agents (sense, diagnostic, decision, outcome)
│   └── identity/             # per-agent instruction (zeroclaw pattern)
├── ontology/                 # Constraint Dictionary (JSON) + probe library
├── engine/                   # two-layer confidence, ranking (deterministic, pure Python)
├── schemas/                  # Pydantic: IntentObject, EvidenceItem, Readiness, Decision
├── grounding/                # curated benchmark table (30–50 entries)
├── evals/                    # two A/B trajectories as reproducible test fixtures
└── docs/
```

Key point: **`engine/` is purely deterministic (no LLM)** — that is the clean answer for judges on the LLM-vs-rules division of labor, and the demo reproducibility guarantee.

## 6. Product Clarification: Decision System + Dashboard, Not a Chat App

Chat/interview is only the **evidence collection phase**. Once evidence is sufficient, the user sees the **Revenue Diagnosis** — a structured panel, not a chat reply.

### 6.1 Main UI components (none of them chat)

| Component | Function | Source |
|---|---|---|
| **Revenue Diagnosis artifact** | Main output: 7 blocks (WHERE YOU ARE → WHEN TO REASSESS) | `02` §7.5 |
| **Reality Check panel** | YOUR EXPECTATION vs REALITY (two columns) | `04` §10.2 |
| **Intent tagging moment** | 📝 ASSUMED INTERVENTION visually separated from FACT | `04` §13.1 |
| **Reasoning Trace** | EVIDENCE → CONSTRAINT → READINESS → DECISION | demo script |
| **Decision Spectrum indicator** | STOP ⟷ SCALE, current verdict position | `02` §6.2 |
| **Progress timeline** | history of diagnosis cycles (see §6.3) | see below |

### 6.2 FE ↔ BE contract (JSON schema, not conversation text)

```
FE (Next.js/React)
├── Interview screen      → POST /session/:id/message     (adaptive branching)
├── Diagnosis dashboard   → GET  /session/:id/diagnosis    (structured artifact)
├── Reality Check         → GET  /session/:id/expectations
├── Reasoning Trace       → GET  /session/:id/trace        (per-evidence log)
├── Progress / Timeline   → GET  /session/:id/trajectory
└── Outcome input         → POST /session/:id/outcome      (feedback loop entry)
```

The FE never renders an "AI reply" as the final answer — every engine message is classified (probe question / diagnosis update / verdict) and rendered as the matching UI component.

### 6.3 Progress & Feedback Loop (state persisted in Firestore)

```
SESSION N: Interview → Evidence → Diagnosis → NBA (7 days)
        → "We'll know we're right when…"
          ↓ user runs the action
SESSION N+1: POST /outcome (positive/negative/mixed/no evidence)
        → S15 REASSESSMENT:
           CONFIRMED   → continue to the next constraint
           DISCONFIRMED → pivot the diagnosis 🔄
        → new diagnosis → new NBA
          ↓
TIMELINE VIEW (the progress the user sees):
●──●──●──●──●──●──●──●──→  each dot = one diagnosis cycle
                            {constraint, verdict, action, outcome, learning}
```

What shows as progress: (1) resolved vs active constraints, (2) diagnosis cycle history, (3) the evidence ledger (facts vs unknowns), (4) outcome-weighted learning (data moat: intervention effectiveness per context).

### 6.4 Prototype vs vision scope (FE)

| Component | Prototype (4 weeks) | Full vision (deck) |
|---|---|---|
| Interview | Yes — the only conversational part | Fully adaptive + multimodal (CV upload) |
| Diagnosis dashboard | Yes — structured output panel | Living dashboard |
| Reasoning trace | Yes — simple list | Interactive graph |
| Reality Check | Yes — two columns | — |
| Progress timeline | ⚠️ Minimal: one reassess field + session history | Full trajectory + maturity level |
| Feedback loop outcome | ⚠️ Semi-simulated (manual input → reassessment) | Automatic + cross-user learning |

Rationale for the minimal app shell in Week 1: 40% of the criteria sit in Gen AI reasoning, UX is only 10%. But the BE architecture (state machine + Firestore) supports the full dashboard from day one — adding views, not reworking.

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| ADK 2.0 graph workflows still new | Spike in H1–H2: try SequentialAgent vs Graph; fallback = SequentialAgent (stable, in the blueprint) |
| Gemini model renamed/re-versioned close to build | Abstract model IDs in one config; re-test in the H1 spike |
| Schema 400 InvalidArgument (too complex) | Split per call; shrink enums; reduce optionals; Pydantic validation + retry |
| LLM non-determinism breaks the two-trajectory repro | Low temperature + strict schema + ontology scaffold + two-layer confidence (`04` §11.1) |
| Wrapper trap (40% criterion) | Gemini must be the reasoning engine (evidence interpretation, hypotheses, contraindications); the ontology is only a scaffold — not a rule engine |

## 8. Technical Next Steps (H1–H2 per the build plan)

1. `pip install google-adk google-genai fastapi` + set up the GCP project & enable Vertex AI/Firestore/Cloud Run
2. Spike: classify 20 sample statements (FACT/GOAL/ASSUMPTION/PREFERENCE) via structured output — measure consistency
3. Small spike: SequentialAgent vs Graph Workflow for the first 3 states (S0→S2)
4. Define the Pydantic schema contracts (Gap #4) in `schemas/`
