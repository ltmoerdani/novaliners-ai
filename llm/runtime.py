"""LLM provider runtime — registry, factory, active-provider state (internal-docs §7: A4).
Cut-paste from app/main.py. Note: build_llm still raises HTTPException
(fastapi coupling) — to be cleaned into ValueError in the upcoming api/ refactor."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException

from providers.gemini import AVAILABLE_MODELS as GEMINI_MODELS
from providers.gemini import GeminiProvider
from providers.mock import MockProvider
from providers.vertex import AVAILABLE_MODELS as VERTEX_MODELS
from providers.vertex import VertexProvider

# Absolute path: .env MUST come from mvp/, not the server cwd
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


# ── Provider registry ─────────────────────────────────────────────────────────
# LLM = a swappable engine. Adding a provider = adding one branch here;
# agents/ never knows which provider is active.
# Model priority: the `model` argument > LLM_MODEL (shell override) > provider env var > default.
PROVIDER_SPECS: dict[str, dict[str, str]] = {
    "mock": {"key_env": "", "model_env": "", "default_model": "mock"},
    "gemini": {
        "key_env": "GEMINI_API_KEY", "model_env": "GEMINI_MODEL",
        "default_model": "gemini-3.5-flash-lite",
    },
    "vertex": {
        "key_env": "VERTEX_API_KEY", "model_env": "VERTEX_MODEL",
        "default_model": "gemini-3.5-flash-lite",
    },
}

# Selectable from the UI. `gemini` is now live (OpenAI-compatible endpoint) —
# AI Builder Cup compliance: the Gemini family must be an active option.
SWITCHABLE_PROVIDERS: tuple[str, ...] = ("gemini", "vertex", "mock")

_PROVIDER_MODELS: dict[str, tuple[str, ...]] = {
    "gemini": GEMINI_MODELS,
    "vertex": VERTEX_MODELS,
    "mock": (),
}

_ACTIVE: dict = {"provider": None, "llm": None}


def _resolve_model(provider: str) -> str:
    spec = PROVIDER_SPECS[provider]
    return os.environ.get("LLM_MODEL") or os.environ.get(spec["model_env"], spec["default_model"])


def _reload_env() -> None:
    """Re-read .env every time an engine is built.

    dotenv is read once at import. Without this, a user who just pasted a key
    into .env keeps getting rejected until the server restarts — and the message
    ("key not set") is misleading, because the key is already in the file.
    """
    load_dotenv(ENV_PATH, override=True)


def build_llm(provider: str, model: str | None = None):
    _reload_env()
    if provider not in PROVIDER_SPECS:
        raise HTTPException(
            400, f"LLM_PROVIDER tidak dikenal: {provider!r} (pilih: {', '.join(PROVIDER_SPECS)})"
        )
    if provider == "mock":
        return MockProvider()
    # Fail fast with a clear message before touching the network.
    if provider == "gemini" and not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(
            500,
            "GEMINI_API_KEY belum diset di .env — buat key di AI Studio (aistudio.google.com), "
            "tempel ke mvp/.env, lalu pilih provider ini lagi (tanpa restart)",
        )
    if provider == "vertex" and not os.environ.get("VERTEX_API_KEY"):
        raise HTTPException(
            500,
            "VERTEX_API_KEY belum diset di .env — buat API key di Google Cloud console "
            "(APIs & Services → Credentials, Vertex AI API enabled), tempel ke mvp/.env, "
            "lalu pilih provider ini lagi (tanpa restart)",
        )
    chosen = model or _resolve_model(provider)
    if provider == "gemini":
        return GeminiProvider(model=chosen)
    return VertexProvider(model=chosen)


def get_llm():
    """Active provider (cached per process; swapped without restart via POST /admin/model)."""
    if _ACTIVE["llm"] is None:
        provider = os.environ.get("LLM_PROVIDER", "mock")
        _ACTIVE["provider"] = provider
        _ACTIVE["llm"] = build_llm(provider)
        # era-7 (internal-docs §10): determinism_mode defaults ON — reduces run-to-run
        # variance in evidence extraction (root cause of DoD 17/19↔19/19). Turn it off with
        # LLM_DETERMINISM=0 if you need the old behavior.
        if os.environ.get("LLM_DETERMINISM", "1") == "1":
            _ACTIVE["llm"].set_determinism(True)
    return _ACTIVE["llm"]


def provider_info() -> dict:
    llm = get_llm()
    provider = _ACTIVE["provider"] or os.environ.get("LLM_PROVIDER", "mock")
    return {
        "status": "ok",
        "provider": provider,
        "model": getattr(llm, "model", None),
        "json_mode": getattr(llm, "json_mode", None),
        "providers": list(SWITCHABLE_PROVIDERS),
        "available_models": list(_PROVIDER_MODELS.get(provider, ())),
        # Full map: the UI needs OTHER providers' model lists before those providers are active,
        # otherwise the model dropdown would be filled with the wrong provider's models.
        "models_by_provider": {p: list(m) for p, m in _PROVIDER_MODELS.items()},
    }


