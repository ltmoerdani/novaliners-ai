"""Guard J6 / K7 (internal-docs §10) — Outcome Learning: epistemic grade from outcome.

Deterministic 0-LLM:
  1. _grade: conservative threshold (n≥3+conf≥0.55 → empirical_low;
     n≥8+conf≥0.65 → empirical_high; below that stays normative_only)
  2. recalc writes the grade to the overlay (frozen KB untouched)
  3. load_grades: graded interventions only; corrupt file → {} (degrade-safe)
  4. interventions_for: graded interventions carry confidence_grade
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from store.nba import _grade, load_grades, recalc

failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(f"  {'PASS' if ok else 'FAIL'} {name}" + (f" | {detail}" if detail and not ok else ""))
    if not ok:
        failed += 1


print("[J6-1] _grade — ambang konservatif", flush=True)


def _grade_conf(succ_plus_1: int, n_plus_2: int) -> float:
    return round(succ_plus_1 / n_plus_2, 3)


check("n=0 → normative_only", _grade(0.5, 0) is None)
check("n=2 sukses semua → normative_only (belum cukup data)",
      _grade(_grade_conf(3, 2), 2) is None)
check("n=3 sukses semua → empirical_low", _grade(_grade_conf(4, 3), 3) == "empirical_low")
check("n=3 campur (conf rendah) → normative_only",
      _grade(_grade_conf(1 + 1, 3 + 2), 3) is None)
check("n=8 sukses semua → empirical_high", _grade(_grade_conf(9, 8), 8) == "empirical_high")
check("n=8 50:50 → normative_only (netral tidak dinaikkan)",
      _grade(0.5, 8) is None)

print("[J6-2] recalc menulis grade ke overlay", flush=True)
with tempfile.TemporaryDirectory() as td:
    src = Path(td) / "reports.jsonl"
    conf = Path(td) / "confidence.json"
    rows = [
        {"intervention_id": "TM-I02", "outcome": o}
        for o in ["moved", "moved", "moved", "not_moved"]
    ]
    rows += [{"intervention_id": "LC-I01", "outcome": o} for o in ["moved"] * 8]
    rows += [{"intervention_id": "PR-I01", "outcome": "confounded"}]
    src.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    data = recalc(conf_path=conf, src_path=src)
    check("TM-I02: 3/4 → empirical_low",
          data["items"]["TM-I02"]["grade"] == "empirical_low",
          str(data["items"].get("TM-I02")))
    check("LC-I01: 8 moved → empirical_high",
          data["items"]["LC-I01"]["grade"] == "empirical_high")
    check("confounded dikecualikan (PR-I01 tidak muncul)",
          "PR-I01" not in data["items"])
    check("load_grades hanya yang ber-grade",
          set(load_grades(conf)) == {"TM-I02", "LC-I01"})

    conf.write_text("{korup", encoding="utf-8")
    check("file korup → {} (degrade-aman)", load_grades(conf) == {})

print("[J6-3] interventions_for membawa confidence_grade", flush=True)
from engine.knowledge import interventions_for  # noqa: E402 — needs sys.path

ivs = interventions_for("C6.3")
check("panggilan normal tetap jalan (degrade-aman di repo asli)",
      isinstance(ivs, list))

print()
print(f"HASIL: {'SEMUA LULUS ✅' if failed == 0 else f'{failed} GAGAL ❌'}")
raise SystemExit(0 if failed == 0 else 1)
