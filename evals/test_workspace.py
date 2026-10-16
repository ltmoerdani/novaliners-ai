"""P-D Workspace guard (internal-docs §5 + roadmap P-D).

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_workspace.py
Uses a test user + the directory is cleaned up at the end (idempotent).
"""
from __future__ import annotations

import shutil
import sys

sys.path.insert(0, ".")

from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from store import workspace  # noqa: E402
from store.workspace import state_diff  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


_U = "test-ws-user"
_DIR = workspace._BASE / _U


def _artifact(**rs_kw) -> DiagnosisArtifact:
    rs = RevenueState(**rs_kw) if rs_kw else None
    paths = {
        "paths": [
            {"path_id": "path.direct_outreach", "status": "OPEN"},
            {"path_id": "path.value_repricing", "status": "TEST_FIRST"},
        ]
    }
    return DiagnosisArtifact(
        status="final", where_you_are="w", primary_constraint="p",
        primary_constraint_id="C6.3", do_not="d", next_best_action="n",
        success_metric="s", well_know_when="wk", pivot_rule="pr",
        revenue_state=rs, possible_paths=paths,
    )


# ---- 1 — ensure + event -----------------------------------------------------
workspace._BASE.mkdir(parents=True, exist_ok=True)
if _DIR.exists():
    shutil.rmtree(_DIR)
w = workspace.ensure_workspace(_U)
check("ensure_workspace → created + event WORKSPACE_CREATED",
      w is not None and workspace.workspace_exists(_U))
check("ensure idempotent — kedua kalau tanpa event baru",
      workspace.ensure_workspace(_U) is not None
      and len([e for e in workspace._read_jsonl(_DIR / "events.jsonl")
               if e["type"] == "WORKSPACE_CREATED"]) == 1)

# ---- 2 — snapshot + diff ----------------------------------------------------
a1 = _artifact(current_monthly=30.0, capacity_utilization=0.5, avg_deal_size=10.0)
r1 = workspace.record_snapshot(_U, "sess-1", a1)
check("snapshot pertama: tanpa diff, event STATE_SNAPSHOT_CREATED",
      r1["diff_vs_prior"] is None
      and r1["snapshot"]["current_monthly"] == 30.0
      and r1["snapshot"]["path_statuses"]["path.direct_outreach"] == "OPEN")

a2 = _artifact(current_monthly=45.0, capacity_utilization=0.9, avg_deal_size=10.0)
r2 = workspace.record_snapshot(_U, "sess-2", a2)
d = r2["diff_vs_prior"]
check("diff revenue + utilization terdeteksi",
      d["changed_metrics"]["current_monthly"] == {"from": 30.0, "to": 45.0}
      and d["changed_metrics"]["capacity_utilization"] == {"from": 0.5, "to": 0.9})
check("metric tak berubah tidak dilaporkan (avg_deal_size absen)",
      "avg_deal_size" not in d["changed_metrics"])
check("constraint migration None bila primary tak berubah", d["constraint_migration"] is None)
check("anything_changed True", d["anything_changed"] is True)

# ---- 3 — constraint migration + path status change --------------------------
a3 = _artifact(current_monthly=45.0, capacity_utilization=0.9, avg_deal_size=12.0)
a3 = a3.model_copy(update={
    "primary_constraint_id": "LC2.1",
    "possible_paths": {"paths": [
        {"path_id": "path.direct_outreach", "status": "STOP"},      # P-E lifecycle
        {"path_id": "path.value_repricing", "status": "OPEN"},       # upgrade
    ]},
})
r3 = workspace.record_snapshot(_U, "sess-3", a3)
d3 = r3["diff_vs_prior"]
check("constraint migration C6.3 → LC2.1",
      d3["constraint_migration"] == {"from": "C6.3", "to": "LC2.1"})
check("path status changes: direct_outreach OPEN→STOP, value_repricing TEST_FIRST→OPEN (kunci = path_id)",
      d3["path_status_changes"] == {
          "path.direct_outreach": {"from": "OPEN", "to": "STOP"},
          "path.value_repricing": {"from": "TEST_FIRST", "to": "OPEN"},
      })

# ---- 4 — diff murni (pure function) -----------------------------------------
empty = state_diff(None, {"current_monthly": 10.0})
check("diff vs None: semua metric 'baru', bukan error",
      empty["changed_metrics"]["current_monthly"]["from"] is None
      and empty["anything_changed"] is True)
same = state_diff({"current_monthly": 1.0}, {"current_monthly": 1.0})
check("state identik → anything_changed False", same["anything_changed"] is False)

# ---- 5 — workspace_view ------------------------------------------------------
view = workspace.workspace_view(_U, path_states={"path.direct_outreach": {"outcome_state": "STOPPED"}})
check("view: 3 snapshot + last_diff + events",
      view["n_snapshots"] == 3 and view["last_diff"]["constraint_migration"]
      and len(view["events"]) >= 4)
check("view: path_states dibawa", view["path_states"]["path.direct_outreach"]["outcome_state"] == "STOPPED")
check("view: user tak dikenal → None", workspace.workspace_view("no-such-user") is None)

# cleanup
shutil.rmtree(_DIR, ignore_errors=True)

fails = [r for r in _results if not r[1]]
_n_ok = len(_results) - len(fails)
print(f"\n{'=' * 50}\nHASIL: {_n_ok}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
