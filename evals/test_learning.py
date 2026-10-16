"""Full P3 (internal-docs §10.8) — guard for knowledge-confidence recalc + overlay.

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_learning.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from store import nba as nba_store  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


tmp = Path(tempfile.mkdtemp())
src = tmp / "nba_reports.jsonl"
conf = tmp / "knowledge_confidence.json"

# Seed reports: IV-BAGUS 3 moved + 1 not_moved · IV-BURUK 1 moved + 4 regret
# · IV-CONF 2 confounded (excluded).
rows = (
    [("IV-BAGUS", "moved")] * 3 + [("IV-BAGUS", "not_moved")]
    + [("IV-BURUK", "moved")] + [("IV-BURUK", "regret")] * 4
    + [("IV-CONF", "confounded")] * 2
)
with src.open("w", encoding="utf-8") as fh:
    for iid, outcome in rows:
        fh.write(json.dumps({"session_id": "t", "intervention_id": iid,
                             "outcome": outcome, "notes": "", "ts": 0}) + "\n")

data = nba_store.recalc(conf_path=conf, src_path=src)
items = data["items"]

bagus = items["IV-BAGUS"]["confidence"]   # (3+1)/(4+2) = 0.667
buruk = items["IV-BURUK"]["confidence"]   # (1+1)/(5+2) = 0.286
conf_i = items.get("IV-CONF")
check("Laplace: 3✓1✗ → 0.667", bagus == 0.667, str(bagus))
check("Laplace: 1✓4✗ → 0.286", buruk == 0.286, str(buruk))
check("confounded dikecualikan (n=0)", conf_i is None)
check("urutan: IV-BAGUS > IV-BURUK", bagus > buruk)

overlay = nba_store.load_confidence(conf)
check("load_confidence overlay terbaca", overlay.get("IV-BAGUS") == 0.667)

# ------------------------------------------------- engine overlay ordering
from engine.knowledge import interventions_for  # noqa: E402

real_conf = Path(nba_store.CONF_PATH)
real_src = Path(nba_store._PATH)
backup_c = real_conf.read_bytes() if real_conf.exists() else None
backup_s = real_src.read_bytes() if real_src.exists() else None
try:
    # Find a constraint with >=2 interventions to test ordering.
    target = None
    for cid in ("C6.3", "V2.1", "DM5.1", "C6.4", "DS4.2"):
        ivs = interventions_for(cid)
        if len(ivs) >= 2:
            target = (cid, ivs)
            break
    if target:
        cid, ivs = target
        a, b = ivs[0]["intervention_id"], ivs[1]["intervention_id"]
        nba_store.recalc(conf_path=real_conf, src_path=src)  # writes the IV-* overlay
        # Force the overlay to hold high IV-BAGUS & low IV-BURUK? It only contains
        # IV-* — real interventions without data = neutral 0.5, so ordering stays stable.
        after = interventions_for(cid)
        order_ok = [i["intervention_id"] for i in after] == [i["intervention_id"] for i in ivs]
        check("ordering stabil: intervensi tanpa data tetap netral (0.5)", order_ok)
        iv_a = [i for i in after if i["intervention_id"] == a][0]
        check("item membawa field confidence (netral 0.5 bila tanpa outcome)",
              iv_a.get("confidence") == 0.5, str(iv_a.get("confidence")))
    else:
        check("constraint >=2 interventions ditemukan", False)
finally:
    if backup_c is not None:
        real_conf.write_bytes(backup_c)
    else:
        real_conf.unlink(missing_ok=True)
    real_src.write_bytes(backup_s) if backup_s is not None else real_src.write_text("")

fails = [r for r in _results if not r[1]]
_n = len(_results) - len(fails)
print(f"\n{'=' * 50}\nHASIL: {_n}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
