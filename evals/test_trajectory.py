"""P-F Trajectory & Drift guard (internal-docs §5.3–5.4).

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_trajectory.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from domains.revenue.stages.trajectory import (  # noqa: E402
    decision_trajectory,
    drift_taxonomy,
    goal_trajectory,
)

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


GOAL = {"target": 60.0, "baseline": 30.0, "deadline_days": 90, "metric": "revenue_monthly"}

# ---- 1 — Goal trajectory ----------------------------------------------------
check("tanpa goal/snapshot → INSUFFICIENT_DATA (jujur)",
      goal_trajectory(None, [])["status"] == "INSUFFICIENT_DATA")
check("goal tanpa target → INSUFFICIENT_DATA",
      goal_trajectory({"baseline": 1}, [{"current_monthly": 2}])["status"] == "INSUFFICIENT_DATA")

g = goal_trajectory(GOAL, [{"current_monthly": 60.0}])
check("current ≥ target → ON_TRACK (tercapai)", g["status"] == "ON_TRACK")

g = goal_trajectory(GOAL, [{"current_monthly": 20.0}])
check("current < baseline → OFF_TRACK", g["status"] == "OFF_TRACK")

g = goal_trajectory(GOAL, [{"current_monthly": 35.0}, {"current_monthly": 42.0}])
check("naik menuju target → IMPROVING", g["status"] == "IMPROVING" and g["frac_achieved"] == 0.4)

g = goal_trajectory(GOAL, [{"current_monthly": 42.0}, {"current_monthly": 38.0}])
check("turun dari 42 → DRIFTING", g["status"] == "DRIFTING")

g = goal_trajectory({"target": 60.0}, [{"current_monthly": 40.0}])
check("tanpa baseline/deadline → INSUFFICIENT_DATA (laju tak bisa dihitung)",
      g["status"] == "INSUFFICIENT_DATA")

# ---- 2 — Decision trajectory -------------------------------------------------
check("<2 snapshot → NEEDS_DATA", decision_trajectory([{"x": 1}])["status"] == "NEEDS_DATA")

sigs = decision_trajectory(
    # the real display-status vocabulary (contracts STATUS_WORDS): OPEN|TEST_FIRST|NOT_YET|STOP.
    # This iteration's audit: the old fixture used "CONDITIONAL" — a status that never existed in
    # the snapshot → the uncertain-path decline signal was DEAD (never fired).
    [{"path_statuses": {"A": "TEST_FIRST", "B": "NOT_YET"}, "primary_constraint_id": "C1"},
     {"path_statuses": {"A": "OPEN", "B": "NOT_YET"}, "primary_constraint_id": "C2"}],
    [],
)
check("jalur belum-tertentu turun (TEST_FIRST 2→1) + migration → IMPROVING dgn 2 sinyal",
      sigs["status"] == "IMPROVING" and len(sigs["signals"]) == 2
      and any("belum-tertentu (TEST_FIRST/NOT_YET) 2→1" in s for s in sigs["signals"]),
      str(sigs["signals"]))

sigs2 = decision_trajectory(
    [{"path_statuses": {"A": "OPEN"}, "primary_constraint_id": "C1"},
     {"path_statuses": {"A": "OPEN"}, "primary_constraint_id": "C1"}],
    [{"type": "PATH_STATUS_CHANGED", "path": "A", "to": "OPEN"}],
)
check("event PATH_STATUS_CHANGED → IMPROVING (bukti outcome masuk)",
      sigs2["status"] == "IMPROVING")

sigs3 = decision_trajectory(
    [{"path_statuses": {"A": "OPEN"}, "primary_constraint_id": "C1"},
     {"path_statuses": {"A": "OPEN"}, "primary_constraint_id": "C1"}],
    [],
)
check("snapshot identik → STABLE (bukan failure)", sigs3["status"] == "STABLE")

# ---- 3 — Core insight: flat revenue + improving understanding ---------------
# goal_trajectory DRIFTING/flat + decision IMPROVING = two independent axes, both valid.
flat = goal_trajectory(GOAL, [{"current_monthly": 35.0}])  # flat: only 1 measured snap
learning = decision_trajectory(
    [{"path_statuses": {"A": "TEST_FIRST"}, "primary_constraint_id": "C1"},
     {"path_statuses": {"A": "OPEN"}, "primary_constraint_id": "C2"}], [],
)
check("dua sumbu independen: goal INSUFFICIENT/flat + decision IMPROVING",
      flat["status"] in ("INSUFFICIENT_DATA", "DRIFTING") and learning["status"] == "IMPROVING")

# ---- 4 — Drift taxonomy -------------------------------------------------------
d = {"path_status_changes": {"A": {"from": "ELIGIBLE", "to": "STOP"}}}
check("path change tanpa metric → STRATEGY_DRIFT",
      drift_taxonomy(d) == ["STRATEGY_DRIFT"])
d2 = {"constraint_migration": {"from": "C1", "to": "C2"}}
check("constraint migration → CONSTRAINT_SHIFT",
      drift_taxonomy(d2) == ["CONSTRAINT_SHIFT"])
d3 = {"changed_metrics": {"demand_sufficiency": {"from": "AT_RISK", "to": "SUFFICIENT"}}}
check("hanya demand/WtP berubah → MARKET_DRIFT",
      drift_taxonomy(d3) == ["MARKET_DRIFT"])
d4 = {"changed_metrics": {"current_monthly": {"from": 30.0, "to": 35.0}}}
check("hanya revenue berubah → bukan market/strategy", drift_taxonomy(d4) == [])
check("goal berubah → GOAL_DRIFT", "GOAL_DRIFT" in drift_taxonomy({}, goal_changed=True))
check("eksekusi jalan tanpa hasil & state tak berubah → EXECUTION_DRIFT",
      drift_taxonomy({}, path_events=[{"outcome": "not_moved"}]) == ["EXECUTION_DRIFT"])
check("tanpa diff → kosong (tidak fabrikasi drift)", drift_taxonomy(None) == [])
check("kombinasi: urutan kanonik deterministik",
      drift_taxonomy({"path_status_changes": {"A": 1}, "constraint_migration": {"from": 1}},
                     goal_changed=True) == ["GOAL_DRIFT", "STRATEGY_DRIFT", "CONSTRAINT_SHIFT"])

fails = [r for r in _results if not r[1]]
_n_ok = len(_results) - len(fails)
print(f"\n{'=' * 50}\nHASIL: {_n_ok}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
