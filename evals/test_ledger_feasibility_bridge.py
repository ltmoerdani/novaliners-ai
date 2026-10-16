"""S3 — ledger -> feasibility bridge: adjudicated requirement state shifts Path feasibility.

Contract (int 20 S3; AGENT-Q seam #1): checks anchored to a requirement_id consume the ledger
state (authority) via the SAME merge_readings as Readiness — not a second evaluator. Evidence:
  L1 no ledger: old behavior UNCHANGED (backward-compatible).
  L2 ledger PRESENT + UNKNOWN signal -> check PRESENT and feasibility rises (decision changes).
  L3 ledger UNKNOWN -> no change (failure-to-change when evidence is insufficient).
  L4 ledger ABSENT + PRESENT signal -> ABSENT (ledger authority); raw state_signal kept,
     CONFLICT recorded (not a false SUPPORTED).
  L5 check WITHOUT requirement_id untouched by the ledger (no wild promotion).
  L6 no ledger_state_of at all (old call-site) -> identical to baseline.

Deterministic, no LLM. Run: .venv/bin/python evals/test_ledger_feasibility_bridge.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.navigation.evaluator import build_path_set  # noqa: E402
from evals.navigation_fixtures import SAAS_SPACE, reader_of  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


BASE = {
    "state:revenue_goal_set": True,
    "state:many_signups": True,
    "state:weak_activation": True,
    "state:activation_already_strong": None,
    "state:funnel_measured": True,
    "state:aha_moment_defined": None,
}
RID = "retention.aha_moment_defined"


def path_of(ps: dict, sid: str) -> dict:
    return next(p for p in ps["paths"] if p["strategy_id"] == sid)


def row_of(path: dict, cid: str) -> dict:
    return next(c for c in path["checks"] if c["check_id"] == cid)


def ledger(values: dict[str, str]):
    return lambda rid: values.get(rid, "UNKNOWN")


# ── L1/L6 · baseline without ledger ────────────────────────────────────────────────────────────
print("L1/L6 · baseline & backward-compat")
ps_base = build_path_set(SAAS_SPACE, reader_of(BASE))
af_base = path_of(ps_base, "activation_first")
base_row = row_of(af_base, "activation_defined")
check("L1 baseline: check ber-requirement UNKNOWN (sinyal tak dijawab)",
      base_row["state"] == "UNKNOWN", str(base_row))
check("L6 baseline: bentuk default tidak berubah (tanpa field audit ledger)",
      base_row["state"] == "UNKNOWN" and "state_signal" not in base_row
      and "sources" not in base_row, str(sorted(base_row)))
check("L6b tanpa ledger_state_of eksplisit == baseline",
      build_path_set(SAAS_SPACE, reader_of(BASE), ledger_state_of=None) == ps_base)
ps_noarg = build_path_set(SAAS_SPACE, reader_of(BASE))
check("L6c signature lama tetap menerima pemanggilan 2-argumen", ps_noarg == ps_base)

# ── L2 · ledger PRESENT raises feasibility ────────────────────────────────────────────────
print("L2 · ledger PRESENT menggeser keputusan")
ps_present = build_path_set(SAAS_SPACE, reader_of(BASE), ledger_state_of=ledger({RID: "PRESENT"}))
af_p = path_of(ps_present, "activation_first")
row_p = row_of(af_p, "activation_defined")
check("L2a ledger PRESENT + sinyal UNKNOWN -> check PRESENT",
      row_p["state"] == "PRESENT", str(row_p))
check("L2b state_signal tetap UNKNOWN (audit pembacaan mentah)",
      row_p["state_signal"] == "UNKNOWN")
check("L2c sources menandai ledger", "ledger" in row_p["sources"], str(row_p["sources"]))
check("L2d feasibility path NAIK dari baseline (bukan tetap)",
      af_p["feasibility"] != af_base["feasibility"] and af_p["feasibility"] == "SUPPORTED",
      f"base={af_base['feasibility']} ledger={af_p['feasibility']}")
check("L2e status path berubah mengikuti feasibility",
      af_p["status"] != af_base["status"] or af_base["status"] == "OPEN",
      f"base={af_base['status']} ledger={af_p['status']}")

# ── L3 · ledger UNKNOWN changes nothing ───────────────────────────────────────────────
print("L3 · failure-to-change saat bukti tidak cukup")
ps_unknown = build_path_set(SAAS_SPACE, reader_of(BASE), ledger_state_of=ledger({}))
check("L3 ledger UNKNOWN -> PathSet identik dengan baseline", ps_unknown == ps_base)

# ── L4 · ledger ABSENT vs PRESENT signal = conflict, not SUPPORTED ─────────────────────────
print("L4 · otoritas ledger + sengketa terstruktur")
present_signal = dict(BASE, **{"state:aha_moment_defined": True})
ps_conflict = build_path_set(SAAS_SPACE, reader_of(present_signal),
                             ledger_state_of=ledger({RID: "ABSENT"}))
af_c = path_of(ps_conflict, "activation_first")
row_c = row_of(af_c, "activation_defined")
check("L4a ledger ABSENT mengalahkan sinyal PRESENT (state ABSENT)",
      row_c["state"] == "ABSENT", str(row_c))
check("L4b state_signal tetap PRESENT (audit mentah tidak hilang)",
      row_c["state_signal"] == "PRESENT")
check("L4c sengketa tercatat terstruktur (authority ledger)",
      isinstance(row_c.get("conflict"), dict)
      and row_c["conflict"].get("authority") == "ledger", str(row_c.get("conflict")))
check("L4d TIDAK menjadi SUPPORTED palsu saat sengketa hard",
      af_c["feasibility"] != "SUPPORTED", f"feasibility={af_c['feasibility']}")

# ── L5 · check without requirement_id untouched ──────────────────────────────────────────
print("L5 · check non-requirement tidak dipromosikan")
row_funnel = row_of(af_p, "funnel_measured")
check("L5 check tanpa requirement_id tetap dari sinyal saja (tanpa field ledger)",
      row_funnel["state"] == "PRESENT" and "state_signal" not in row_funnel
      and "sources" not in row_funnel, str(row_funnel))

# ── L7/L8 · conflict on HARD check must not become STOP/SUPPORTED ─────────────────────────
print("L7/L8 · sengketa ledger-vs-check pada hard check")
from core.navigation.contracts import CheckSpec, PossibilitySpace, StrategySpec  # noqa: E402
from core.navigation.readiness import _check_item, _ledger_merge, canonical_feasibility  # noqa: E402
from engine.requirements import describe as _describe  # noqa: E402

HARD_SPACE = PossibilitySpace(
    space_id="s3hard", goal_signal="state:g",
    strategies=(StrategySpec(strategy_id="hard_strat", title="Hard", basis="b",
                             emerges_when="state:g",
                             checks=(CheckSpec("hardc", "state:cond", "hard", "adv.req", "unlock"),)),))

led_absent = ledger({"adv.req": "ABSENT"})
ps_c1 = build_path_set(HARD_SPACE, reader_of({"state:g": True, "state:cond": True}),
                       ledger_state_of=led_absent)
p_c1 = path_of(ps_c1, "hard_strat")
check("L7 sinyal PRESENT + ledger ABSENT -> feasibility TIDAK CONTRADICTED (tidak STOP palsu)",
      p_c1["feasibility"] != "CONTRADICTED", f"feas={p_c1['feasibility']}")
check("L7b canonical_feasibility juga TIDAK CONTRADICTED",
      canonical_feasibility(p_c1, None, led_absent) != "CONTRADICTED")
check("L7c check mencatat sengketa + state_signal mentah",
      row_of(p_c1, "hardc").get("state_signal") == "PRESENT"
      and row_of(p_c1, "hardc").get("conflict") is not None, str(row_of(p_c1, "hardc")))
it = _check_item(row_of(p_c1, "hardc"), lambda rid, lang=None: _describe(rid, lang or "en"))
check("L7d readiness._check_item meneruskan state_signal",
      it.get("state_signal") == "PRESENT", str(sorted(it)))
_ledger_merge(it, ledger({"adv.req": "ABSENT"}))
check("L7e readiness merge menandai sengketa (settled False + conflict)",
      it.get("settled") is False and it.get("conflict") is not None, str(it))

led_present = ledger({"adv.req": "PRESENT"})
ps_c2 = build_path_set(HARD_SPACE, reader_of({"state:g": True, "state:cond": False}),
                       ledger_state_of=led_present)
p_c2 = path_of(ps_c2, "hard_strat")
check("L8 sinyal ABSENT + ledger PRESENT -> feasibility TIDAK SUPPORTED (tidak OPEN palsu)",
      p_c2["feasibility"] != "SUPPORTED", f"feas={p_c2['feasibility']}")
check("L8b canonical_feasibility juga TIDAK SUPPORTED",
      canonical_feasibility(p_c2, None, led_present) != "SUPPORTED")

# ── L9 · conflict on ROUTE-BEARING path (twin _adjudicate) ─────────────────────────────────────
print("L9 · _adjudicate route-bearing memakai pembacaan mentah")
from core.navigation.readiness import _adjudicate  # noqa: E402

route_item = {"requirement_id": "adv.req", "state": "ABSENT", "sources": ["route"], "partial": False,
              "evidence": [], "check_id": None, "reason": {}, "unlock": {}}
check_item = {"requirement_id": "adv.req", "check_id": "hardc", "state": "ABSENT",
              "state_signal": "PRESENT", "partial": False, "evidence": ["check:hardc"],
              "reason": {}, "unlock": {}}
adj = _adjudicate([route_item], [check_item])[0]
check("L9a node ADJUDIKASI ledger ABSENT vs sinyal MENTAH PRESENT -> sengketa terdeteksi",
      adj.get("settled") is False and adj.get("conflict", {}).get("sources", {}).get("check") == "PRESENT",
      str(adj.get("conflict")))
check("L9b state terproyeksi tetap otoritas node (ABSENT), bukan state ter-merge",
      adj["state"] == "ABSENT", str(adj["state"]))
# without state_signal (old call-site) -> old behavior (no false conflict).
# NB: _adjudicate mutates its input, so use a FRESH dict (not the already-mutated route_item copy).
route_item_legacy = {"requirement_id": "adv.req", "state": "ABSENT", "sources": ["route"],
                     "partial": False, "evidence": [], "check_id": None, "reason": {}, "unlock": {}}
check_item_legacy = {"requirement_id": "adv.req", "check_id": "hardc", "state": "ABSENT",
                     "partial": False, "evidence": [], "reason": {}, "unlock": {}}
adj2 = _adjudicate([route_item_legacy], [check_item_legacy])[0]
check("L9c tanpa state_signal: tidak ada sengketa (backward-compatible)",
      adj2.get("settled") is not False, str(adj2.get("settled")))

print()
failed = [r for r in RESULTS if not r[1]]
print(f"{'❌ FAIL' if failed else '✅ PASS'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
for name, _ok, detail in failed:
    print(f"   ❌ {name}: {detail[:200]}")
sys.exit(1 if failed else 0)
