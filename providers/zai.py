"""Z.AI (GLM) provider — OpenAI-compatible API.

Saatnya swap ke Gemini (fase kompetisi): implement `providers/gemini.py`
dengan class yang sama mengikuti `LLMProvider` — agents tidak berubah sama sekali.
"""
from __future__ import annotations

import os

from openai import OpenAI

from .base import LLMProvider

# Referensi cepat untuk picker UI; BUKAN whitelist keras (model baru di sisi Z.AI
# tetap bisa dipakai dengan menulis namanya langsung).
AVAILABLE_MODELS: tuple[str, ...] = (
    "glm-5.3-flash",
    "glm-5.2",
    "glm-4.7",
    "glm-4.6",
    "glm-4.5-air",
)


class ZAIProvider(LLMProvider):
    name = "zai"

    def __init__(self, model: str | None = None) -> None:
        self.client = OpenAI(
            api_key=os.environ["ZAI_API_KEY"],
            base_url=os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4"),
            timeout=float(os.environ.get("ZAI_TIMEOUT", "300")),  # coding plan bisa lambat untuk prompt besar
            max_retries=1,
        )
        self.model = model or os.environ.get("ZAI_MODEL", "glm-4.6")
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.det_temperature = float(os.environ.get("LLM_TEMPERATURE_DETERMINISTIC", "0.0"))

    def _extra_body(self) -> dict:
        """Param thinking per KEMAMPUAN MODEL (docs.z.ai/guides/llm/glm-5.3, diverifikasi 15 Okt 2026):
        GLM-5.3/5.3-flash SELALU reasoning-enabled — `thinking: disabled` tidak didukung lagi
        (migration notice resmi: ganti ke `enabled` + `reasoning_effort`, kalau tidak request gagal).
        Untuk tugas tagging/JSON kita pakai effort terendah `low` (setara niat lama "disable").
        Model lama (glm-4.x dsb.) tetap memakai `disabled` — jangan mengubah perilaku model lain."""
        body: dict = {"response_format": {"type": "json_object"}}
        if self.model.startswith("glm-5.3"):
            body["thinking"] = {"type": "enabled"}
            body["reasoning_effort"] = os.environ.get("ZAI_REASONING_EFFORT", "low")
        else:
            # Thinking default ENABLED di GLM-4.x -> latency besar utk klasifikasi; disable sah di sana.
            body["thinking"] = {"type": "disabled"}
        return body

    def raw_json(self, system: str, user: str) -> str:
        temp = self.det_temperature if self.determinism_mode else self.temperature
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=temp,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_body=self._extra_body(),
        )
        return resp.choices[0].message.content or ""
