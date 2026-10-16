"""P-E Path Rerouting guard (internal-docs §3.5 — edge outcome→path).

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_reroute.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from domains.revenue.navigation.paths import build_possible_paths, lifecycles_from_states  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from domains.revenue.stages.reroute import (  # noqa: E402
    apply_outcome,
    new_path_state,
)
from store import path_states  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


# ---- 1 — State machine murni ------------------------------------------------
st, ev = apply_outcome(new_path_state(), "regret")
check("regret → OPEN→STOPPED + event PATH_STATUS_CHANGED",
      st["outcome_state"] == "STOPPED" and ev and ev["type"] == "PATH_STATUS_CHANGED"
      and ev["from"] == "OPEN" and ev["to"] == "STOPPED")

st2, ev2 = apply_outcome(st, "regret")
check("regret kedua → reinforcement, tanpa event dobel",
      st2["outcome_state"] == "STOPPED" and ev2 is None and st2["regret"] == 2)

st3, ev3 = apply_outcome(st2, "moved")
check("moved di jalur STOPPED → REOPEN (OPEN) + event",
      st3["outcome_state"] == "OPEN" and ev3 and ev3["from"] == "STOPPED" and ev3["to"] == "OPEN")

st4, ev4 = apply_outcome(new_path_state(), "not_moved")
check("not_moved → counter saja, TIDAK demote (action failure ≠ path failure)",
      st4["outcome_state"] == "OPEN" and ev4 is None and st4["not_moved"] == 1)

st5, ev5 = apply_outcome(new_path_state(), "confounded")
check("confounded → counter saja (tak terukur tak menggeser apa pun)",
      st5["outcome_state"] == "OPEN" and ev5 is None and st5["confounded"] == 1)

st6, ev6 = apply_outcome(new_path_state(), "moved")
check("moved di jalur OPEN → counter saja, tanpa event",
      st6["outcome_state"] == "OPEN" and ev6 is None and st6["moved"] == 1)

# ---- 2 — Outcome state = LIFECYCLE on top of feasibility (not overriding status) --------------
rs = RevenueState(capacity_utilization=0.5, willingness_to_pay="PROVEN_AT_CURRENT_PRICE",
                  demand_exists=True, demand_signal="EXISTS", demand_sufficiency="SUFFICIENT",
                  avg_deal_size=10.0, current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0)
base = build_possible_paths(rs, {"level": "PROCEED"})
by = {p["path_id"]: p for p in base["paths"]}
check("baseline: direct_outreach OPEN tanpa lifecycle keputusan",
      by["path.direct_outreach"]["status"] == "OPEN" and by["path.direct_outreach"]["lifecycle"] == "OPEN")

stopped_state = {"path.direct_outreach": {**new_path_state(), "outcome_state": "STOPPED", "regret": 1}}
check("lifecycles_from_states: STOPPED -> lifecycle universal dengan asal USER_OUTCOME",
      lifecycles_from_states(stopped_state)["path.direct_outreach"]["state"] == "STOPPED"
      and lifecycles_from_states(stopped_state)["path.direct_outreach"]["origin"] == "USER_OUTCOME")
check("state OPEN tidak menghasilkan lifecycle keputusan",
      lifecycles_from_states({"path.direct_outreach": new_path_state()}) == {})
ov = build_possible_paths(rs, {"level": "PROCEED"}, path_states=stopped_state)
acq = next(p for p in ov["paths"] if p["path_id"] == "path.direct_outreach")
check("STOP user: status STOP, feasibility asli SUPPORTED tetap terlihat, asal tercatat",
      acq["status"] == "STOP" and acq["feasibility"] == "SUPPORTED" and acq["lifecycle"] == "STOPPED"
      and acq["stop_provenance"][0]["source"] == "LIFECYCLE" and acq["stop_provenance"][0]["cause"])
rep = next(p for p in ov["paths"] if p["path_id"] == "path.value_repricing")
# Status may be OPEN/TEST_FIRST/NOT_YET (from the constraint verdict) — what is forbidden =
# a user STOP leaking onto a path with no outcome history.
check("path tanpa riwayat outcome: lifecycle OPEN, status bukan STOP user",
      rep["lifecycle"] == "OPEN" and rep["status"] in ("OPEN", "TEST_FIRST", "NOT_YET"))

# ---- 3 — Store: apply_and_log + history (unique user_id, cleaned up) ---------
_U = "test-reroute-user"
res = path_states.apply_and_log(_U, "test-sess", "path.paid_channel_test", "regret")
check("apply_and_log: path_id dipakai apa adanya + event tercatat",
      res["event"]["path"] == "path.paid_channel_test" and res["state"]["outcome_state"] == "STOPPED")
res2 = path_states.apply_and_log(_U, "test-sess", "path.paid_channel_test", "moved")
check("reopen via store: STOPPED→OPEN + event",
      res2["state"]["outcome_state"] == "OPEN" and res2["event"]["to"] == "OPEN")
hist = path_states.history(user_id=_U)
check("history per-user: 2 event PATH_STATUS_CHANGED terurut (run ini)",
      len(hist) >= 2 and hist[-2]["to"] == "STOPPED" and hist[-1]["to"] == "OPEN")
states_now = path_states.get_states(_U)
check("get_states: counter kumulatif (regret=1, moved=1)",
      states_now["path.paid_channel_test"]["regret"] == 1
      and states_now["path.paid_channel_test"]["moved"] == 1)

for bad in ("BUKAN_JALUR", "ACQUISITION", "path.", "path.A B"):
    try:
        path_states.apply_and_log(_U, "test-sess", bad, "moved")
        check(f"path_id tak sah {bad!r} → ValueError (anti-fabrikasi)", False)
    except ValueError:
        check(f"path_id tak sah {bad!r} → ValueError (anti-fabrikasi)", True)
check("path_id sah untuk strategi baru diterima (tanpa enum path tetap)",
      path_states.apply_and_log(_U, "test-sess", "path.activation_first", "moved")["state"]["moved"] == 1)

res3 = path_states.apply_and_log("", "test-sess", "path.direct_outreach", "regret")
check("tanpa user_id → degrade senyap (state tidak dipersist)",
      res3["state"] is None and res3["event"] is None)

# cleanup: drop the test user from the store so the guard stays idempotent
_data = path_states._read_states()
_data.pop(_U, None)
path_states._write_states(_data)
# history too — the guard must not leave residue in the committed file
_h = path_states._BASE / "path_history.jsonl"
if _h.exists():
    _keep = [ln for ln in _h.read_text(encoding="utf-8").splitlines()
             if ln.strip() and '"test-reroute-user"' not in ln]
    _h.write_text("\n".join(_keep) + ("\n" if _keep else ""), encoding="utf-8")

fails = [r for r in _results if not r[1]]
_n_ok = len(_results) - len(fails)
print(f"\n{'=' * 50}\nHASIL: {_n_ok}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
