"""P-A Goal Model guard (internal-docs §2.1 + §11 roadmap).

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_goal_model.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from domains.revenue.schema.goal import build_goal, goal_gap, parse_goal_text  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


# 1 — Parser: explicit 'target ... Rp X' marker = strongest origin.
g1 = parse_goal_text("Saya ingin capai target Rp60 juta per bulan dalam 90 hari dari baseline Rp30 juta")
check("target marker → 60", g1.target == 60.0)
check("origin = goal_marker (bukan fallback)", g1.target_origin == "goal_marker")
check("baseline terbaca → 30", g1.baseline == 30.0)
check("deadline 90 hari", g1.deadline_days == 90)

# 2 — Parser: no marker → first-Rp fallback, WEAK origin + guard note.
g2 = parse_goal_text("Saya pengin resign, sekarang dapet Rp18 juta dari 3 klien")
check("fallback Rp pertama → 18", g2.target == 18.0)
check("origin = goal_fallback + note guard aktif",
      g2.target_origin == "goal_fallback" and any("fallback" in n for n in g2.notes))

# 3 — The 19 Sep incident must not recur: 'target 1 klien baru' WITHOUT Rp → target None,
# not a number produced by a sneaky regex.
g3 = parse_goal_text("target saya cuma dapat 1 klien baru bulan ini")
check("tanpa angka Rp → target None (tidak fabrikasi)", g3.target is None and g3.target_origin == "none")

# 4 — Explicit input is NEVER overwritten by the parser (origin = explicit_input).
g4 = build_goal("mau Rp18 juta", target=25.0, baseline=10.0, deadline_days=60,
                desire="pengin resign dari kerjaan",
                success_definition="target tercapai tanpa jam kerja > 40h/minggu")
check("input eksplisit menang: target 25 (bukan 18 dari teks)", g4.target == 25.0)
check("origin = explicit_input", g4.target_origin == "explicit_input")
check("desire & success_definition tersimpan (constraint-encoded)",
      g4.desire == "pengin resign dari kerjaan" and "40h" in g4.success_definition)
check("deadline_days = 60", g4.deadline_days == 60)

# 5 — One week/month converted to days.
g5 = parse_goal_text("dalam 2 minggu naik ke Rp50 juta")
check("2 minggu → 14 hari", g5.deadline_days == 14)
g5b = parse_goal_text("dalam 3 bulan")
check("3 bulan → 90 hari", g5b.deadline_days == 90)

# 6 — Gap computation belongs to the goal object, not scattered regexes.
gg = goal_gap(g4.model_copy(update={"current": 12.0}))
check("gap = 25 − 12 = 13", gg == {"target": 25.0, "current": 12.0, "gap": 13.0, "computable": True})
gg2 = goal_gap(g2)
check("tanpa current → gap None (jujur, tidak fabrikasi)", gg2["gap"] is None and not gg2["computable"])

# 7 — Numbers formatted 1.5 juta / 500 ribu.
g7 = parse_goal_text("target Rp1,5 juta per bulan")
check("koma desimal → 1.5", g7.target == 1.5)
g7b = parse_goal_text("cukup Rp500 ribu dulu")
check("ribu → 0.5 juta", g7b.target == 0.5)

# 8 — E2E BUG 21 Sep: the format "8jt/bln ... ingin 25jt/bln" WITHOUT "Rp" must be read.
g8 = parse_goal_text(
    "Saya copywriter lepas, penghasilan 8jt/bln tidak stabil — "
    "ingin 25jt/bln dari 3 klien retainer dalam 60 hari"
)
check("kasus E2E: baseline 8 (penghasilan ... jt, tanpa Rp)", g8.baseline == 8.0)
check("kasus E2E: target 25 (ingin ... jt/bln, tanpa Rp)", g8.target == 25.0)
check("kasus E2E: origin intent_phrase (frasa niat, bukan fallback)",
      g8.target_origin == "intent_phrase")
check("kasus E2E: deadline 60 hari tetap terbaca", g8.deadline_days == 60)

fails = [r for r in _results if not r[1]]
_n_ok = len(_results) - len(fails)
print(f"\n{'=' * 50}\nHASIL: {_n_ok}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
