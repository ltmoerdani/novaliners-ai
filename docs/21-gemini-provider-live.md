# 21 — Gemini Provider Live: AI Builder Cup 2026 Compliance

> **Status**: 🟢 Active
> **Topic**: Implementation of `GeminiProvider` (previously a stub) via the OpenAI-compatible Gemini API endpoint — the Gemini model family becomes an active engine option, key configuration, model availability sweep results (16 Oct 2026), and Cloud Run deployment notes
> **Updated**: 2026-10-16
> **Tags**: gemini, provider, ai-builder-cup, compliance, model-sweep, cloud-run, llm-provider
> **Supersedes**: the `gemini | stub` row in [06-provider-agnostic-engine-and-model-switching.md](06-provider-agnostic-engine-and-model-switching.md) §2 (other rows remain valid)
> **Depends on**: [06-provider-agnostic-engine-and-model-switching.md](06-provider-agnostic-engine-and-model-switching.md), [01-techstack-revenue-navigation.md](01-techstack-revenue-navigation.md) (compliance path Route A)

---

## 1. Context

The AI Builder Cup 2026 technical requirement (`internal-docs` §3.2): the model must be from the **Gemini/Gemma** family or a Google agentic platform; deployment must be on **Cloud Run/Firebase/GCP**. The 40% judging criterion (Gen AI integral) demands Gemini as the reasoning engine, not a bolt-on. Until 16 Oct 2026, `providers/gemini.py` was still a `NotImplementedError` stub and was not listed in the UI picker.

## 2. Implementation

**Files changed** (baseline commit `e0553724`, branch `feat/e2e-capability-latency-recovery`):

| File | Change |
|---|---|
| `mvp/providers/gemini.py` | Stub → full `GeminiProvider` implementation, identical pattern to `ZAIProvider`: OpenAI SDK pointed at the official Gemini **OpenAI-compatible endpoint** (`https://generativelanguage.googleapis.com/v1beta/openai`), `response_format={"type": "json_object"}`, temperature via `LLM_TEMPERATURE`/`LLM_TEMPERATURE_DETERMINISTIC` |
| `mvp/llm/runtime.py` | `PROVIDER_SPECS["gemini"]` populated (`GEMINI_API_KEY`/`GEMINI_MODEL`), `gemini` added to `SWITCHABLE_PROVIDERS`, `_PROVIDER_MODELS["gemini"] = AVAILABLE_MODELS` |
| `mvp/.env` | `GEMINI_API_KEY` (new AI Studio format, prefixed `AQ.`), `GEMINI_MODEL=gemini-3.5-flash-lite`, `GEMINI_TIMEOUT=300` |

The interface remains `LLMProvider.raw_json(system, user)` + `determinism_mode` → **`agents/` is unchanged entirely** (the provider-agnostic principle of int 06 still holds). The registry lives in `llm/runtime.py` (no longer `app/main.py` — `main.py` only imports `SWITCHABLE_PROVIDERS` for `/health`).

**Design decision:** the OpenAI-compatible endpoint, not the `google-genai` SDK. Reasons: (1) the existing provider pattern already uses the OpenAI SDK, zero new dependencies; (2) interface and retry path are identical to ZAI. Consequence: structured output uses `json_object` (a hint), **not** the `response_schema` promised by `google-genai` — consistent with the `01-techstack` §2.2 note that `json_object` without a schema is only a hint. Pydantic validation in the pipeline remains the gate of truth. Migration to the official SDK + `response_schema` stays open if JSON quality degrades.

## 3. Model sweep results (16 Oct 2026, 1 JSON turn per model)

| Model | Result | Notes |
|---|---|---|
| `gemini-3.5-flash-lite` | ✅ 4.1s | **Chosen default** — fastest, cheapest tier |
| `gemini-3.5-flash` | ✅ 4.8s | Slightly stronger reasoning |
| `gemini-flash-lite-latest` | ✅ 12.9s | Safe but slow (alias resolving across generations) |
| `gemini-flash-latest`, `gemini-3.8-flash`, `gemini-3.1-flash-lite` | 503 | High demand — **fluctuates by the hour**, retry |
| `gemini-pro-latest`, `gemini-4-argon`, `gemini-3.1-pro-preview` | 429 | Free-tier API key quota exhausted (not high demand); needs billing |
| `gemini-2.5-flash`, `gemini-2.5-flash-lite` | 404 | **"No longer available to new users"** — do not use |

`AVAILABLE_MODELS` in the picker is ordered by this sweep; 503/429 statuses change at any time. Smoke verification through the full path: `build_llm('gemini')` → OK (7.3s, valid JSON).

## 4. Configuration & operations

```bash
# .env (mvp/)
LLM_PROVIDER=gemini            # or switch at runtime without a restart:
GEMINI_API_KEY=[API_KEY]       # AI Studio, new "AQ." format
GEMINI_MODEL=gemini-3.5-flash-lite
```

- **Runtime switch:** `POST /admin/model` `{"provider": "gemini", "model": "..."}` or the Engine dropdown in the UI (populated from `GET /health` → `providers` + `models_by_provider`). A running server must be restarted after the registry changes — the dropdown will not show `gemini` in a process still on the old code (16 Oct incident).
- **Do not put `LLM_MODEL` in `.env`** (one-shot override; `load_dotenv(override=True)` makes it win, see int 06).
- e2e `make test-ui` moves the server to `mock` and rejects other providers — unaffected.

## 5. Limits & what is not done yet

- **Vertex AI is now LIVE as a separate provider** — `providers/vertex.py` (live 16 Oct, commit `bc8fdcd2`): GCP console account-bound keys are **rejected** on generativelanguage; endpoint `aiplatform.googleapis.com` + header `x-goog-api-key`. See [22-cloud-run-deployment-and-two-repo-workflow.md](22-cloud-run-deployment-and-two-repo-workflow.md) for Vertex auth findings & model sweep.
- **Cloud Run service not live yet** — setup & tooling ready (Procfile, .gcloudignore, deploy command), the first deploy did not complete; status & checklist: [int 22 §5](22-cloud-run-deployment-and-two-repo-workflow.md).
- **Cross-model calibration** (Gemini tagging/adjudication quality vs DeepSeek/GLM) **has not been run** — smoke only proves connectivity + valid JSON, not reasoning quality. Required before claiming "Gemini integral" in the submission.
- The 503/429 statuses on the sweep date are a snapshot, not a permanent property of the models.
