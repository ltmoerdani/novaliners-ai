"""Gemini provider — Google AI (the Gemini family) via an OpenAI-compatible endpoint.

AI Builder Cup 2026 compliance (internal-docs §3.2): models must be from
the Gemini/Gemma family. Interface identical to the other `LLMProvider` adapters →
agents unchanged.

Endpoint: generativelanguage.googleapis.com/v1beta/openai (the Gemini API's official
OpenAI compatibility). Auth: GEMINI_API_KEY (AI Studio; the new format starts with "AQ.").
"""
from __future__ import annotations

import os

from openai import OpenAI

from .base import LLMProvider

# Quick reference for the UI picker; NOT a hard whitelist (new models on Google's side
# remain usable by typing their name directly).
# gemini-2.5-flash REJECTED for new users (404 "no longer available", 16 Oct 2026).
# Availability sweep 16 Oct: 3.5-flash-lite 4.1s ✅ · 3.5-flash 4.8s ✅ · flash-lite-latest
# 12.9s ✅ · flash-latest/3.8-flash/3.1-flash-lite fluctuating 503 · Pro tier 429 (free-key quota).
AVAILABLE_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-pro-latest",
)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: str | None = None) -> None:
        self.client = OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url=os.environ.get(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai",
            ),
            timeout=float(os.environ.get("GEMINI_TIMEOUT", "300")),
            max_retries=1,
        )
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.det_temperature = float(os.environ.get("LLM_TEMPERATURE_DETERMINISTIC", "0.0"))

    def raw_json(self, system: str, user: str) -> str:
        temp = self.det_temperature if self.determinism_mode else self.temperature
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=temp,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""
