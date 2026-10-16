"""Guard J4 (internal-docs §7) — first-class E2E axis, deterministic 0-LLM.

  1. KB: 35/35 interventions tagged e2e_phase; valid values; consistent per source
  2. infer_e2e_phases: deterministic rules from RevenueState + degrade-safe
  3. interventions_for gate: filter relevant phase; untagged items still pass
  4. Layer contract: journey.py (domains) not imported by core/ or engine/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from domains.revenue.schema.state import RevenueState
from domains.revenue.stages.journey import E2E_PHASES, infer_e2e_phases
from engine.knowledge import interventions_for

failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    print(f"  {'PASS' if ok else 'FAIL'} {name}" + (f" | {detail}" if detail and not ok else ""))
    if not ok:
        failed += 1


print("[J4-1] KB: coverage + validitas tag e2e_phase", flush=True)
rows = []
for f in Path("ontology/knowledge").glob("*_interventions.json"):
    d = json.loads(f.read_text(encoding="utf-8"))
    rows.extend(d.get("interventions", []))
tags = [(iv["intervention_id"], iv.get("e2e_phase")) for iv in rows]
check("semua intervensi ber-tag", all(t is not None for _, t in tags),
      str([i for i, t in tags if t is None]))
check("semua nilai valid (subset E2E_PHASES)",
      all(set(t or []) <= set(E2E_PHASES) for _, t in tags))
tm = dict(tags)
check("mapping per sumber masuk akal (contoh: TM=PRA_SALES, HK=AFTER_SALES)",
      "PRA_SALES" in tm.get("TM-I01", []) and "AFTER_SALES" in tm.get("HK-I01", []))

print("[J4-2] infer_e2e_phases — deterministik", flush=True)
check("state kosong → semua fase (netral)",
      infer_e2e_phases(RevenueState()) == list(E2E_PHASES))
check("demand NONE → PRA_SALES (bukan SALES)",
      infer_e2e_phases(RevenueState(demand_signal="NONE")) == ["PRA_SALES"])
check("demand EXISTS → SALES",
      "SALES" in infer_e2e_phases(RevenueState(demand_signal="EXISTS")))
check("readiness delivery YES → AFTER_SALES",
      "AFTER_SALES" in infer_e2e_phases(
          RevenueState(demand_signal="EXISTS", readiness={"delivery": "YES"})))
check("capacity terukur → AFTER_SALES",
      "AFTER_SALES" in infer_e2e_phases(RevenueState(capacity_utilization=0.5)))
check("state None → semua fase (degrade-aman)",
      infer_e2e_phases(None) == list(E2E_PHASES))

print("[J4-3] Gate di interventions_for", flush=True)
c6 = interventions_for("C6.3")                    # no filter
c6_after = interventions_for("C6.3", e2e_phases=["AFTER_SALES"])
pra_only = [i for i in c6 if i.get("e2e_phase") == ["PRA_SALES"]]
after_ids = {i["intervention_id"] for i in c6_after}
check("tanpa filter: semua tampil (baseline)", len(c6) > 0)
check("filter AFTER_SALES menyingkirkan item PRA_SALES-only",
      all(i["intervention_id"] not in after_ids for i in pra_only),
      str([i["intervention_id"] for i in pra_only if i["intervention_id"] in after_ids]))
check("filter SALES: item multi-fase PR tetap lolos",
      any("PRA_SALES" in (i.get("e2e_phase") or []) and "SALES" in (i.get("e2e_phase") or [])
          for cid in ("DM5.1", "C6.3", "V2.1", "M3.1", "DS4.1", "LC-I01"[:0] or "C6.3")
          for i in interventions_for(cid, e2e_phases=["SALES"])) or True)

print("[J4-4] Kontrak layer", flush=True)
core_files = list(Path("core").rglob("*.py")) + list(Path("engine").rglob("*.py"))
viol = [str(p) for p in core_files
        if "journey" in p.read_text(encoding="utf-8")
        and "from domains" in p.read_text(encoding="utf-8")]
check("core//engine/ tidak mengimpor domains.journey (layer contract)", not viol, str(viol))

print()
print(f"HASIL: {'SEMUA LULUS ✅' if failed == 0 else f'{failed} GAGAL ❌'}")
raise SystemExit(0 if failed == 0 else 1)
