# Revenue Navigation — Novaliners AI

> **The idea: a GPS for commercialization decisions.**

## BUILDING GOT EASY. SELLING DIDN'T.

Building something has never been easier. Turning it into revenue has never been harder.
Founders, freelancers, agencies, consultants, and small-business owners don't lack
information — they lack certainty: *what stands between my offer and paying customers,
what do I do next, and is that next step even right for my situation?*

Courses answer with more material. AI chat answers with confident guesses — it invents
your business state, then advises on top of it. Revenue Navigation answers differently:
it connects **real evidence** to **possible directions**, **practical actions**, and
**better decisions** as new results come in.

**DECISION PROMISE — Understand your situation → choose a useful move → learn and reassess.**

Like a GPS: it asks where you are, where you want to go, checks the road conditions,
then gives you the next instruction — including an honest **"don't go yet."**

## Who it helps

Founders, freelancers, agencies, consultants, and small-business owners chasing revenue —
no TOFU/MOFU/CAC vocabulary required. You talk in your own words; the engine does the
navigation.

## What makes it different

**The LLM proposes. The engine decides.**

The LLM (Gemini) understands your language and drafts interpretations. A deterministic
navigation engine — with full provenance down to your own sentences — verifies every
claim before it becomes state. The LLM **never** creates state, decides satisfaction,
or invents evidence. Swap the model and the decisions stay identical.

That single split is what makes three things possible that chatbots can't do:

1. **Negative guidance that argues.** Verdicts are not limited to "GO". The engine says
   `STOP · TEST FIRST · NOT YET` *with explicit unlock conditions* — "you're not ready
   for paid acquisition until X and Y are proven" — never generic "do more" advice.
2. **Possible Paths 0..N, honest to the evidence.** The number of viable directions
   follows your evidence: zero, one, three, thirteen — all valid. Zero paths comes with
   a reasoned explanation, not an empty screen.
3. **Every answer is replayable.** Each turn leaves a decision trail: which evidence
   produced which state, which rule or verifier produced which verdict. Inspect, replay,
   audit — no "the model felt like it".

Built for **Google Cloud AI Builder Cup 2026** — theme *Future of Work & Enterprise
Productivity*.

## 🔗 Live demo

**https://novaliners-4sphntnsyq-et.a.run.app** — Cloud Run (`asia-southeast2`).

Answer the onboarding in plain language, talk to the engine, then explore the five
destinations: **STATE · MAPS · MOVES · JOURNEY · TALK** — your verified situation, a map
of possible directions with readiness per requirement, concrete moves with a Maps↔Moves
loop (pick a move, do it, report the outcome, watch the map reassess), your trajectory,
and a copilot grounded in the same engine state.

## How a conversation works

Every message runs the same deterministic state loop:

```text
message → semantic observation → evidence + Universal State
  → live adjudication (LLM proposes, deterministic adjudicator decides)
  → Possible Paths 0..N → Route (optional) → Readiness
  → Question Planner (pure function, no LLM) → QUESTION · EVIDENCE_REQUEST · ACTION · HOLD
  → next message ── and after every action: Outcome → new Evidence → reassessment ↺
```

The Question Planner decides *what to ask next from the current state* — never from a
fixed script. Questions you already answered are never repeated; questions the
conversation can't settle are not asked. A monotonic **question budget** keeps the
interview finite and visible.

## Architecture

Every arrow below is real code:

```text
Universal State ─► Evidence ─► Knowledge ─► Mechanism / Pattern ─► Candidate Possibility
   ─► Candidate Evaluation ─► Possible Path (0..N) ─► Route (optional) ─► Requirement
   ─► Readiness ─► NextMove (QUESTION · EVIDENCE_REQUEST · ACTION · HOLD) ─► Action
   ─► Outcome ─► new Evidence ↺
```

Supporting machinery a judge can verify in code: a 49-entry **Requirement Registry**
with per-requirement presentation text, a 13-metric **Goal Registry** (revenue, leads,
close rate, CAC, founder hours, … — a goal is not forced into "Rp X per month"),
multi-layer adjudication (deterministic compiled rules + a grounded second-pass
verifier whose only job is to propose branches with substring-backed quotes),
goal-relative navigation with typed semantics, and per-user workspaces where path
history, goal revisions, and decision trajectories are never rewritten.

Architecture contract: [`docs/14-universal-navigation-architecture.md`](docs/14-universal-navigation-architecture.md).
Tech stack & compliance: [`docs/01-techstack-revenue-navigation.md`](docs/01-techstack-revenue-navigation.md),
[`docs/21-gemini-provider-live.md`](docs/21-gemini-provider-live.md).

## Google Cloud stack

| Layer | Choice |
|---|---|
| Reasoning | **Gemini via Vertex AI** (`gemini-3.5-flash-lite` default) — AI Builder Cup Path A: the Gemini/Gemma family |
| Runtime | **Cloud Run** (`asia-southeast2`), autoscaled 1–3 instances |
| Secrets | **Secret Manager** (API keys never in code or CI) |
| CI/CD | **GitHub Actions + Workload Identity Federation** — keyless: every push to `main` runs the deterministic test gate, then builds, deploys, and smoke-tests |

Provider lineup is pluggable — one `LLMProvider` class per provider, the agents layer
never changes:

| Provider | Endpoint | Default model | Status |
|---|---|---|---|
| `vertex` | aiplatform.googleapis.com (Agent Platform) | `gemini-3.5-flash-lite` | ✅ live |
| `gemini` | Gemini API (OpenAI-compatible) | `gemini-3.5-flash-lite` | ✅ live |
| `mock` | — | — | keyless demo |

Switch engines live — no restart — via **Settings → Engine** in the UI or
`POST /admin/model`.

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # set VERTEX_API_KEY / GEMINI_API_KEY — or LLM_PROVIDER=mock for DEMO MODE
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Reproducibility

```bash
bash gate-fast.sh   # deterministic suite (zero LLM calls) — runs in CI before every deploy
```

Decisions are engine-owned, so the product is testable without burning tokens: the
deterministic gate covers the navigation contract (0..N paths, readiness, negative
guidance, planner determinism, goal-relative semantics, provenance) with **zero LLM
calls**, and UI tests run against the mock provider. LLM smoke tests are a separate,
explicitly-paid command.

## Team

**Novaliners** — *people who find the line forward.* JAPAC regional entry,
Google Cloud AI Builder Cup 2026.
