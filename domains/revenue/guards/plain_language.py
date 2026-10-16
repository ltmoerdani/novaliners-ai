"""Human-language guard (internal-docs §6). Deterministic, 0 LLM.

Machine-checkable rules from plain-language research (NN/g: middle/high-school level,
15-20 word sentences, no jargon; AHRQ/health literacy: 2-3 points, not a verdict) and repo
conventions (no em dash, no internal codes):
  1. no internal technical terms (BANNED list)
  2. no machine symbols/notation (→ ≠ ± — (1)…)
  3. no all-caps words
  4. sentences are not long (max 28 words, average <= 22); the whole summary <= 115 words
  5. numbers only from a source (user or engine computation), never invented
  6. per-field length is limited
  7. required fields are filled
The result is per field: a violating field is dropped by the caller, the UI falls back to the artifact text.
"""
from __future__ import annotations

import re

_TERMS = (
    "probe|funnel|icp|cac|ltv|kpi|roi|pipeline|feasibility|price[- ]?response|value[- ]?framing|"
    "constraint|hipotesis|hypothesis|akuisisi|konversi|conversion|inquiry|eksperimen|intervensi|"
    "validasi|sampel|isolasi|baseline|benchmark|scaling|scale|metrik|metric|utilization|confound|"
    "demand|traksi|traction|diagnostik|diagnostic|kontraindikasi|prasyarat|threshold|ambang"
)
BANNED = re.compile(rf"\b({_TERMS})\b", re.I)
SYMBOLS = re.compile(r"[→≠±—]|\(\d\)|\bev-[a-z_]+-\d+|\b[A-Z]\d\.\d\b")
SHOUT = re.compile(r"\b[A-Z]{4,}\b")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

# EN narrative containing Indonesian function/content words = the narrative fell into another language (18 Oct
# incident: the path opening followed the ID examples in the prompt). Only function words are counted (not
# names/brands); a 1-2 word user quote is still tolerated, an ID sentence pattern is not.
_ID_WORDS = re.compile(
    r"\b(yang|dan|dengan|untuk|dari|sudah|belum|juga|akan|bisa|karena|tapi|jika|kalau|anda|kami|kita|"
    r"jangan|adalah|bahwa|saja|agar|supaya|kepada|pada|dalam|tidak|bukan|atau|jalur|klien|pembeli|"
    r"harga|juta|ribu|bulan|minggu|cerita|tunjukkan|meminta|terukur)\b",
    re.I,
)

SUMMARY_WORDS = 115   # the whole summary: 1-3 paragraphs, readable at a glance
MAX_SENTENCE_WORDS = 28
MAX_AVG_WORDS = 22
ANSWER_LIMIT = 900    # the whole Ask answer (characters) — one constant for prompt + guard
LIMITS = {  # karakter per item
    "summary": 460, "blocking_title": 150, "blocking_body": 320, "do_title": 220, "do_why": 260,
    "done_when": 380, "hold_title": 160, "hold_body": 340, "why": 200,
}
COUNTS = {"summary": (1, 3), "why": (2, 3)}
REQUIRED = ("summary", "blocking_title", "do_title", "done_when", "hold_title", "why")
OPTIONAL = ("do_why", "blocking_body", "hold_body")   # empty is allowed; if present it must be clean

# Nested (screen 07/18): per-path and per-readiness-check items. All empty text is allowed —
# the UI falls back to the engine sentence for that item.
PATH_LIMITS = {"why": 300, "next": 320, "opening": 480, "supported": 300, "holding": 300, "unclear": 260}
CHECK_LIMITS = {"how": 360, "have": 240}


def sentences(text: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]


def numbers_in(text: str) -> set[str]:
    out: set[str] = set()
    for n in NUMBER.findall(text or ""):
        n = n.replace(",", ".")
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def check_language(text: str, lang: str) -> list[str]:
    """Narrative language vs session language (D1/D10): an `en` session written in Indonesian
    prose = a violation.

    Deterministic, 0 LLM: ID function/content words are counted; 2 different words OR 3
    occurrences are already a sentence pattern, not a coincidental quote. An `id` session is free
    (the narrative really is ID)."""
    if (lang or "en").lower()[:2] != "en" or not str(text or "").strip():
        return []
    hits = _ID_WORDS.findall(text)
    distinct = {w.lower().strip() for w in hits}
    if len(distinct) >= 2 or len(hits) >= 3:
        return [f"not in English (Indonesian words: {', '.join(sorted(distinct)[:4])})"]
    return []


def check_text(text: str, pool: set[str], limit: int) -> list[str]:
    if not text.strip():
        return ["empty"]
    out: list[str] = []
    if len(text) > limit:
        out.append(f"too long ({len(text)} > {limit} chars)")
    for term in sorted({m.group(0).lower() for m in BANNED.finditer(text)}):
        out.append(f"technical term: {term}")
    if SYMBOLS.search(text):
        out.append(f"machine notation: {SYMBOLS.search(text).group(0)}")
    for word in sorted({m.group(0) for m in SHOUT.finditer(text)}):
        out.append(f"shouting: {word}")
    counts = [len(s.split()) for s in sentences(text)]
    if counts and max(counts) > MAX_SENTENCE_WORDS:
        out.append(f"sentence of {max(counts)} words (max {MAX_SENTENCE_WORDS})")
    if counts and sum(counts) / len(counts) > MAX_AVG_WORDS:
        out.append(f"average sentence {sum(counts) / len(counts):.0f} words (max {MAX_AVG_WORDS})")
    for n in sorted(numbers_in(text) - pool):
        out.append(f"number not from the user or the engine: {n}")
    return out


def check_explain(ex: dict, pool: set[str], lang: str = "en") -> dict[str, list[str]]:
    """{field: [violations]} for violating fields (empty = clean).

    Top-level keys for ordinary fields ("summary"), nested "paths:KEY" / "checks:KEY" keys for
    violating path/check items — the caller drops that item, not the whole block.
    `lang` = session language; an EN-session narrative is also language-checked (check_language)."""
    bad: dict[str, list[str]] = {}
    for f, limit in LIMITS.items():
        v = ex.get(f)
        items = v if isinstance(v, list) else [v or ""]
        errs: list[str] = []
        lo, hi = COUNTS.get(f, (1, 1))
        if isinstance(v, list) and not (lo <= len(v) <= hi):
            errs.append(f"{len(v)} items (need {lo}-{hi})")
        for it in items:
            errs += check_text(str(it), pool, limit)
            errs += check_language(str(it), lang)
        if errs:
            bad[f] = sorted(set(errs))
    total = sum(len(str(p).split()) for p in ex.get("summary") or [])
    if total > SUMMARY_WORDS:
        bad.setdefault("summary", []).append(f"summary is {total} words (max {SUMMARY_WORDS})")
    for f in OPTIONAL:
        if bad.get(f) == ["empty"]:
            del bad[f]

    def nested(prefix: str, rows, limits: dict[str, int]) -> None:
        for row in rows or []:
            if not isinstance(row, dict):
                bad.setdefault(f"{prefix}:?", []).append("not an object")
                continue
            key = str(row.get("key") or "").strip()
            name = f"{prefix}:{key or '?'}"
            if not key:
                bad[name].append("missing key")
            for f, limit in limits.items():
                errs = check_text(str(row.get(f) or ""), pool, limit)
                errs += check_language(str(row.get(f) or ""), lang)
                if errs != ["empty"]:   # empty text is valid: the UI falls back to the engine sentence
                    if errs:
                        bad.setdefault(name, []).extend(errs)

    nested("paths", ex.get("paths"), PATH_LIMITS)
    nested("checks", ex.get("checks"), CHECK_LIMITS)
    return bad
