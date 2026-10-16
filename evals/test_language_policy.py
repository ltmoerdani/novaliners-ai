"""Guard language policy D1/D10 (closure session, 10 Oct 2026): the Revenue system narration is English.

Deterministic, 0 real LLM calls. Run: .venv/bin/python evals/test_language_policy.py

What it guards:
  1. the system prompts of diagnosis, explain and ask each carry an explicit English-output rule
     (D1a for explain and ask, D10 for the diagnosis);
  2. none of them carries the core mirror rule ("... SAME language the user writes in ..."), and no
     Revenue prompt module imports LANGUAGE_RULES any more (the diagnosis prompt was the last one);
  3. mvp/core is untouched: the core module still defines its mirror LANGUAGE_RULES for other domains.
"""
from __future__ import annotations

import inspect
import sys

sys.path.insert(0, ".")

from core.prompts import core_rules  # noqa: E402
from domains.revenue.prompts import ask_system, diagnosis_system, explain_system  # noqa: E402

MIRROR = "SAME language the user writes in"

PROMPTS = [
    ("diagnosis_system", diagnosis_system, "Write ALL user-facing output in ENGLISH"),
    ("explain_system", explain_system, "write in English, whatever language the USER WORDS section is in"),
    ("ask_system", ask_system, "write in English, whatever language the USER QUESTION is in"),
]

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


for name, mod, marker in PROMPTS:
    src = inspect.getsource(mod)
    check(f"{name}: the system prompt carries an explicit English-output rule", marker in mod.SYSTEM, marker)
    check(f"{name}: the core mirror rule is not in the prompt", MIRROR not in mod.SYSTEM)
    check(f"{name}: LANGUAGE_RULES is no longer imported or interpolated", "LANGUAGE_RULES" not in src)

check(
    "core untouched: core_rules.LANGUAGE_RULES still defines the mirror rule for other domains",
    MIRROR in core_rules.LANGUAGE_RULES,
)

# ── 18 Oct 2026 incident: opening path written in Indonesian on an EN session ─
# Root cause: Indonesian example fragments in the explain prompt primed the model to write Indonesian
# ("Anda sudah punya ..." was copied almost verbatim), and the guard did not check language.
from domains.revenue.guards.plain_language import check_language  # noqa: E402

ID_PRIMING = (
    "Anda cerita", "Anda sudah punya", "Anda belum mengukur", "Jangan dulu",
    "yang kami lihat", "sepertinya", "belum kami ketahui", "misal: tulis",
    "mencari klien baru", "coba kecil dulu", "uji kecil dulu",
)
for name, mod, _ in PROMPTS:
    for marker in ID_PRIMING:
        check(f"{name}: no Indonesian example priming ({marker!r})",
              marker not in mod.SYSTEM)

check("check_language: Indonesian sentence in an en session is flagged",
      check_language("Anda sudah punya paket dan jalur ini meminta bukti.", "en") != [])
check("check_language: clean English passes",
      check_language("You already have a package; this path asks for proof.", "en") == [])
check("check_language: one stray word (a quote) is tolerated",
      check_language("You said the word \"jalur\" once.", "en") == [])
check("check_language: an id session is not checked",
      check_language("Anda sudah punya paket dan jalur ini meminta bukti.", "id") == [])
check("check_language: empty text passes",
      check_language("", "en") == [])

failed = [n for n, ok, _ in _results if not ok]
verdict = "FAIL" if failed else "pass"
print(f"LANGUAGE POLICY: {len(_results) - len(failed)}/{len(_results)} checks {verdict}")
sys.exit(1 if failed else 0)
