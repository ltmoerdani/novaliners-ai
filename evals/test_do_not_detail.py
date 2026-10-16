"""P-C guard (internal-docs §11): do_not = structured navigation state.

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_do_not_detail.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from agents.diagnosis import (  # noqa: E402
    contraindication_detail_for,
    contraindication_for,
)
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402

ONTOLOGY = json.loads(
    (Path(__file__).resolve().parents[1] / "ontology" / "constraints.json").read_text()
)  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


# 1 — Registry has contraindications with verdicts — detail derived for every pattern.
_patterns = [p for p, c in ONTOLOGY["contraindications"].items() if isinstance(c, dict)]
check("registry kontraindikasi non-kosong", len(_patterns) > 0)

sample_cid = None
for p in _patterns:
    # real constraint_id from ontology with this pattern's prefix
    for cid in ONTOLOGY["constraints"]:
        if cid.startswith(p.rstrip("*")):
            sample_cid = cid
            break
    if sample_cid:
        break
det = contraindication_detail_for(sample_cid)
check("constraint nyata → detail terisi (verdict + unlock_condition)",
      det is not None and det["verdict"] in ("NOT_YET", "STOP", "TEST_FIRST")
      and bool(det["unlock_condition"]))
check("until registry == unlock_condition (satu sumber kebenaran)",
      det["unlock_condition"] == (ONTOLOGY["contraindications"][det["matched_pattern"]].get("until")))

# 2 — Render vs detail consistency: verdict NOT_YET appears in the do_not text.
text = contraindication_for(sample_cid)
if det["verdict"] == "NOT_YET":
    check("render teks memuat 'NOT YET' saat verdict NOT_YET", "NOT YET" in text)
else:
    check(f"render teks memuat verdict {det['verdict']}", det["verdict"].replace("_", " ") in text.upper())

# 3 — Constraint without contraindication → None (honest, no fabrication).
det_none = contraindication_detail_for("XX-UNKNOWN-99")
check("constraint tak dikenal → None", det_none is None)

# 4 — Artifact schema: do_not_detail optional (backward compat) + serialized.
_a = DiagnosisArtifact(
    status="final", where_you_are="w", primary_constraint="p", primary_constraint_id=sample_cid,
    do_not="d", next_best_action="n",
    success_metric="s", well_know_when="wk", pivot_rule="pr",
    do_not_detail={"verdict": "NOT_YET", "unlock_condition": "u"},
)
check("artifact menerima do_not_detail", _a.do_not_detail["verdict"] == "NOT_YET")
_b = _a.model_dump()
check("model_dump membawa do_not_detail", "do_not_detail" in _b)
_c = DiagnosisArtifact(
    status="final", where_you_are="w", primary_constraint="p", primary_constraint_id="X",
    do_not="d", next_best_action="n",
    success_metric="s", well_know_when="wk", pivot_rule="pr",
)
check("tanpa do_not_detail → None (sesi lama tetap valid)", _c.do_not_detail is None)

fails = [r for r in _results if not r[1]]
_n_ok = len(_results) - len(fails)
print(f"\n{'=' * 50}\nHASIL: {_n_ok}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
