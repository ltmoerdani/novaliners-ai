"""OpenCode Go provider — gateway OpenAI-compatible untuk 13 open model.

Kenapa ada: MVP-1 terkunci ke Z.AI (GLM). Supaya engine bisa diuji lintas model
(kualitas reasoning + konsumsi kuota) tanpa menyentuh agents/, tambahkan satu
provider kedua dengan antarmuka `LLMProvider` yang identik.

Endpoint : https://opencode.ai/zen/go/v1/chat/completions
           (endpoint /go/ menghitung kuota langganan Go, bukan billing Zen per-token)
API key  : key yang sama dengan Zen (opencode.ai/auth) → env OPENCODE_API_KEY
Model    : OPENCODE_GO_MODEL (default deepseek-v4-flash)

Ganti model = ubah satu baris .env (atau POST /admin/model) — agents tidak berubah.
"""
from __future__ import annotations

import logging
import os
import time
from uuid import uuid4

from openai import BadRequestError, OpenAI

from .base import LLMProvider, strip_code_fences

log = logging.getLogger("providers.opencode_go")

DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash"

# Gateway Go MENOLAK klien yang menyamar sebagai SDK generik: minta user agent
# yang mengidentifikasi diri sendiri, plus id sesi percakapan (docs go/#where-can-i-use-it).
DEFAULT_USER_AGENT = "revenue-navigation-mvp/0.1"

# Transport per model TIDAK seragam (docs go/#endpoints). Provider ini bicara lewat
# /chat/completions, jadi hanya model di CHAT_MODELS yang benar-benar bisa dipakai.
#   /chat/completions → dipakai di sini
#   /v1/messages      → MiniMax & Qwen  → butuh klien Anthropic
#   /v1/responses     → Grok, GPT Luna, Muse Spark → butuh Responses API
# Model dua grup terakhir sengaja TIDAK diumbar di picker: kalau dipilih, yang
# muncul bukan jawaban model melainkan error gateway.
CHAT_MODELS: tuple[str, ...] = (
    "deepseek-v4.1-flash",   # limit 4x s/d 20 Sep 2026
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "glm-5.3-flash",
    "glm-5.3",
    "glm-5.2",
    "glm-5.1",
    "kimi-k3",
    "kimi-k2.7-code",
    "kimi-k2.6",
    "longcat-2.0",
    "mimo-v2.5",
    "mimo-v2.5-pro",
    "hy4-preview",
    "hy3",
)

# Referensi saja — supaya tidak ada yang menebak kenapa model ini tidak muncul di UI.
OTHER_TRANSPORT_MODELS: dict[str, tuple[str, ...]] = {
    "messages (anthropic)": (
        "minimax-m3", "minimax-m2.7", "minimax-m2.5",
        "qwen3.8-max", "qwen3.8-flash", "qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus",
    ),
    "responses (openai)": (
        "grok-4.6", "gpt-5.6-luna",
        "muse-spark-1.3-contributor", "muse-spark-1.2-contributor",
    ),
}


def api_key_from_env() -> str | None:
    """OPENCODE_API_KEY (nama utama) atau OPENCODE_GO_API_KEY (alias campaign-forge)."""
    return os.environ.get("OPENCODE_API_KEY") or os.environ.get("OPENCODE_GO_API_KEY") or None


class OpenCodeGoProvider(LLMProvider):
    name = "opencode_go"

    def __init__(self, model: str | None = None) -> None:
        api_key = api_key_from_env()
        if not api_key:
            raise RuntimeError(
                "OPENCODE_API_KEY belum diset di .env. Ambil key di opencode.ai/auth "
                "(key Zen sekaligus berlaku untuk Go)."
            )
        self.client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("OPENCODE_GO_BASE_URL", DEFAULT_BASE_URL),
            timeout=float(os.environ.get("OPENCODE_GO_TIMEOUT", "300")),
            max_retries=1,
            # Aman: _custom_headers di-spread SETELAH "User-Agent" bawaan SDK.
            default_headers={"User-Agent": os.environ.get("OPENCODE_GO_USER_AGENT", DEFAULT_USER_AGENT)},
        )
        self.model = model or os.environ.get("OPENCODE_GO_MODEL", DEFAULT_MODEL)
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.det_temperature = float(os.environ.get("LLM_TEMPERATURE_DETERMINISTIC", "0.0"))
        # Gateway Go tidak menerima `response_format` di seluruh model (mis. sebagian
        # model reasoning). "auto" = coba json_object dulu, turun otomatis bila ditolak.
        self.json_mode = os.environ.get("OPENCODE_GO_JSON_MODE", "auto").strip().lower()
        # WAJIB: tanpa header ini gateway balas 400 MissingSessionID dan tidak bisa
        # merutekan request. Default acak per instance supaya provider tidak mati
        # saat dipanggil di luar alur HTTP (mis. skrip eval); main.py menimpanya
        # dengan id sesi percakapan sebenarnya.
        self.session_id = f"revnav-{uuid4().hex[:16]}"

    def use_session(self, session_id: str | None) -> None:
        if session_id:
            # Nilai instance = fallback (dipanggil di luar alur HTTP, mis. skrip eval).
            # Nilai thread-local = yang dipakai saat request — aman untuk paralel (E2).
            self.session_id = f"revnav-{session_id}"
            super().use_session(self.session_id)

    def _sid(self) -> str:
        """Id sesi untuk panggilan INI: thread-local menang atas default proses."""
        return self.current_session_id() or self.session_id

    @property
    def json_mode_enabled(self) -> bool:
        return self.json_mode != "off"

    def raw_json(self, system: str, user: str) -> str:
        use_json = self.json_mode_enabled
        try:
            return self._call(system, user, json_mode=use_json)
        except BadRequestError as e:
            msg = str(e).lower()
            # Turunkan json_mode HANYA kalau gateway benar-benar mengeluh soal
            # response_format. BadRequestError lain (MissingSessionID, model tidak
            # dikenal) harus naik ke atas — kalau ikut ditelan, penyebab aslinya
            # tertutup oleh pesan kegagalan kedua yang berbeda.
            if not use_json or self.json_mode == "on" or not any(
                k in msg for k in ("response_format", "json_object", "json mode", "structured output")
            ):
                raise
            log.warning(
                "[opencode_go] response_format ditolak gateway untuk model %s (%s) — "
                "lanjut mode prompt-only JSON",
                self.model, str(e)[:160],
            )
            self.json_mode = "off"
            return self._call(system, user, json_mode=False)

    def _call(self, system: str, user: str, *, json_mode: bool) -> str:
        extra: dict = {"response_format": {"type": "json_object"}} if json_mode else {}
        temp = self.det_temperature if self.determinism_mode else self.temperature
        t0 = time.monotonic()
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=temp,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_headers={"x-opencode-session": self._sid()},
            **extra,
        )
        # Instrumentasi A (23 Sep 2026): finish_reason = bukti potong output.
        # "length" berarti JSON terpotong → structured_call kemungkinan retry penuh
        # (satu panggilan 20–50s terbuang — dugaan asal panggilan ke-3 32,8s).
        try:
            fr = str(resp.choices[0].finish_reason or "")
        except Exception:
            fr = ""
        if fr == "length":
            log.warning(
                "[opencode_go] finish_reason=length (OUTPUT TERPOTONG) — JSON tidak utuh, "
                "structured_call kemungkinan retry penuh"
            )
        elapsed = time.monotonic() - t0
        # Kuota Go dihitung dari token, bukan jumlah request. Tanpa baris ini,
        # "berapa kuota terpakai" hanya bisa dilihat dengan membuka console.
        u = getattr(resp, "usage", None)
        fr_s = f" | finish={fr}" if fr else ""
        if u is not None:
            log.info(
                "[opencode_go] %s | in=%s out=%s total=%s | %.1fs%s%s",
                self.model, u.prompt_tokens, u.completion_tokens, u.total_tokens,
                elapsed, "" if json_mode else " | prompt-only JSON", fr_s,
            )
        else:
            log.info("[opencode_go] %s | tanpa usage | %.1fs%s", self.model, elapsed, fr_s)
        msg = resp.choices[0].message
        content = (msg.content or "").strip()
        if not content:
            # Model reasoning bisa menghabiskan budget token di CoT sehingga content
            # kosong. reasoning_content BUKAN output final — pakai hanya sebagai
            # upaya terakhir, dan catat supaya hasil eval tidak diklaim "bersih".
            fallback = (getattr(msg, "reasoning_content", None) or "").strip()
            if fallback:
                log.warning(
                    "[opencode_go] content kosong (kemungkinan token habis di reasoning) — "
                    "memakai reasoning_content sebagai upaya terakhir; kualitas TIDAK dijamin"
                )
            content = fallback
        return strip_code_fences(content)
