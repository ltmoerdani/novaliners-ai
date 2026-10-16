"""S1 — answer routing integrity for AQ (adaptive Q&A) in the catering runner.

Background: runner evals/run_catering_conversational.py sends 4 SCRIPTED (PD) opening story
messages, then answers the model's ACTUAL questions from the fact map (AQ). The old keyword
routing used FIRST match -> short generic keywords ('tanya', 'catatan', 'wa', '25') could
STEAL a question that is really about another fact. This guard locks the rule: the LONGEST
(most specific) match wins.

What is proven:
  AQ1 generic keywords do not steal (tanya -> revenue_composition; catatan -> conversion).
  AQ2 every fact is reachable through its own distinctive keyword.
  AQ3 unmapped question -> SIMULATOR_LIMIT sentinel + default answer (NOT a fact).
  AQ4 the sentinel cannot be mistaken for a fact (not one of the fact keys).
  AQ5 >=2 answers come from model questions (routing level) with provenance source=fact_map.
  AQ6 deterministic: same input -> same output.

HONESTY NOTE: this tests the harness ROUTING deterministically (no LLM). AQ parity with the
REAL model remains NOT_RUN (needs a paid provider). This guard does NOT claim model quality.

Run: .venv/bin/python evals/test_aq_answer_routing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals.run_catering_conversational import CORPUS, _route  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


FACTS = CORPUS["facts"]
FACT_KEYS = {f["key"] for f in FACTS}


def route(q: str) -> tuple[str, str]:
    return _route(q, FACTS)


print("AQ1 · kata kunci generik tidak mencuri jawaban")
key1, _ = route("Boleh saya tanya soal komposisi pendapatan per kantor?")
check("AQ1a 'tanya ... komposisi pendapatan' -> revenue_composition (bukan inquiries_ref)",
      key1 == "revenue_composition", f"dapat {key1}")
key2, _ = route("Apakah ada catatan soal konversi yang jadi klien?")
check("AQ1b 'catatan ... konversi jadi klien' -> conversion (bukan records)",
      key2 == "conversion", f"dapat {key2}")
key3, _ = route("berapa lama waktu balasannya ke prospek?")
check("AQ1c 'waktu balas' -> follow_up_slow (bukan records lewat substring 'wa')",
      key3 == "follow_up_slow", f"dapat {key3}")

print("AQ2 · setiap fakta reachable lewat kata kunci khasnya")
for f in FACTS:
    kw = max(f["match"], key=len)
    got, _ = route(f"Tolong jelaskan soal {kw} ya")
    check(f"AQ2 {f['key']} reachable via '{kw}'", got == f["key"], f"dapat {got}")

print("AQ3/AQ4 · sentinel SIMULATOR_LIMIT bukan fakta")
key_u, ans_u = route("Apakah Anda suka warna biru dan musik jazz?")
check("AQ3 pertanyaan tak terpetakan -> SIMULATOR_LIMIT", key_u == "SIMULATOR_LIMIT", f"dapat {key_u}")
check("AQ4 sentinel bukan salah satu key fakta", key_u not in FACT_KEYS)
check("AQ4b jawaban default dipakai apa adanya (tanpa mengarang angka)",
      ans_u == CORPUS["answer_default"], ans_u[:80])

print("AQ5 · >=2 jawaban dari pertanyaan model (routing-level) dengan provenance")
model_questions = [
    "Berapa kapasitas produksi harian Anda sekarang?",
    "Berapa persen yang jadi pelanggan dari tiap inquiry?",
]
routed = [(q, *route(q)) for q in model_questions]
fact_map = [(q, k) for q, k, _a in routed if k != "SIMULATOR_LIMIT"]
check("AQ5a tepat 2 pertanyaan model dipetakan ke fakta (source=fact_map)",
      len(fact_map) == 2, str(fact_map))
check("AQ5b dua fakta BERBEDA (bukan satu fakta diulang)",
      len({k for _q, k in fact_map}) == 2, str(fact_map))
check("AQ5c key yang dipetakan ada di peta fakta (provenance sah)",
      all(k in FACT_KEYS for _q, k in fact_map), str(fact_map))

print("AQ6 · determinisme")
r_a = route(model_questions[0])
r_b = route(model_questions[0])
check("AQ6 input sama -> output sama", r_a == r_b, f"{r_a} vs {r_b}")

print()
failed = [r for r in RESULTS if not r[1]]
print(f"{'❌ FAIL' if failed else '✅ PASS'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
for name, _ok, detail in failed:
    print(f"   ❌ {name}: {detail[:200]}")
sys.exit(1 if failed else 0)
