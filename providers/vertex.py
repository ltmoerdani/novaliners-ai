"""Vertex AI provider — the Gemini family via Agent Platform / Vertex AI (account-bound API key).

AI Builder Cup 2026 compliance: the full Google option (Agent Platform, ex-Vertex AI)
alongside `gemini` (the Gemini API). Auth: VERTEX_API_KEY — a NEW key type from
the Google Cloud console that is BOUND to a service account (account-bound, starting
with "AQ."). This key is REJECTED on generativelanguage (the Gemini API) — it requires
the aiplatform.googleapis.com endpoint with the `x-goog-api-key` header.

Transport: direct REST via httpx (`generateContent` + `responseMimeType`
application/json = a hint, doc 01-techstack §2.2 — Pydantic validation in the
pipeline stays the gate of truth).
"""
from __future__ import annotations

import os

import httpx

from .base import LLMProvider

# Models served by Vertex/Agent Platform — live sweep 16 Oct 2026 (all OK):
# 3.5-flash-lite 1.2s · 3.5-flash 2.3s · 3.8-flash 3.7s · 2.5-pro 13.7s.
# Note: the `gemini-pro-latest` alias (Gemini API) 404s on Vertex — use the specific name.
AVAILABLE_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-2.5-pro",
)

_ENDPOINT = (
    "https://aiplatform.googleapis.com/v1beta1/publishers/google/models/{model}:generateContent"
)


class VertexProvider(LLMProvider):
    name = "vertex"

    def __init__(self, model: str | None = None) -> None:
        self.api_key = os.environ["VERTEX_API_KEY"]
        self.endpoint = os.environ.get("VERTEX_ENDPOINT_TEMPLATE", _ENDPOINT)
        self.model = model or os.environ.get("VERTEX_MODEL", "gemini-3.5-flash-lite")
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.det_temperature = float(os.environ.get("LLM_TEMPERATURE_DETERMINISTIC", "0.0"))

    def raw_json(self, system: str, user: str) -> str:
        temp = self.det_temperature if self.determinism_mode else self.temperature
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "systemInstruction": {"role": "system", "parts": [{"text": system}]},
            "generationConfig": {
                "temperature": temp,
                "responseMimeType": "application/json",
            },
        }
        with httpx.Client(timeout=float(os.environ.get("VERTEX_TIMEOUT", "300"))) as client:
            resp = client.post(
                self.endpoint.format(model=self.model),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                json=payload,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Vertex AI {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"] or ""
