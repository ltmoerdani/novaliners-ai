"""R1.3 gate — route_node_execution session applicability guard (Probe C remediated).

Contract: internal-docs §2.
No LLM. Temporary store; mock provider; test sessions cleaned up.
  1. Cross-context execution (a consultant route via a garage session) -> 409 guard
  2. Same-strategy context (an agency executing a route born in another consultant
     session, same user) -> 200: the guard does NOT block a legitimate continuation
     of one strategy across sessions (note: full cross-MAP separation = Probe B
     remediation, not this guard)
  3. The session that owns the route itself stays 200 (no regression of the normal flow)
  4. RESET via another context session is blocked too (the guard precedes the event)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.route_execution as rex  # noqa: E402
import store.route_lineages as rl  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="r1_guard_"))
rl._BASE = _tmp / "lineages"
rex._BASE = _tmp / "exec"
ledger._LEDGER_ROOT = _tmp / "ledger"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as _app_main  # noqa: E402
import store.events as _event_store  # noqa: E402
from app.main import app  # noqa: E402
from providers.mock import MockProvider  # noqa: E402

_app_main.get_llm = lambda: MockProvider()
assert _app_main.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
_event_store.EVENTS_DIR = Path(tempfile.mkdtemp(prefix="nvl-r1g-ev-"))

from core.schema.evidence import EvidenceItem  # noqa: E402
from evals.navigation_fixtures import revenue_artifact  # noqa: E402
from store.memory import store  # noqa: E402

c = TestClient(app)
USER = "u-r1-guard"
_created: list[str] = []


def _session(user_id: str, text: str, cur: float, tgt: float) -> str:
    r = c.post("/session", json={"goal_text": "naik omzet", "language": "id", "user_id": user_id})
    sid = r.json()["session_id"]
    _created.append(sid)
    s = store.get(sid)
    s.evidence = [EvidenceItem(id="e0", signal=text, source_quote=text,
                               level="self_reported", topic="REVENUE_STATE")]
    s.diagnosis = revenue_artifact(current_monthly=cur, target_monthly=tgt,
                                   gap_monthly=max(tgt - cur, 1.0), capacity_utilization=0.5,
                                   demand_exists=True, avg_deal_size=10.0)
    store.save(s)
    return sid


def _direct_route(sid: str) -> dict:
    b = c.post(f"/session/{sid}/routes").json()
    d = next(x for x in b["routes"] if x["template_id"] == "direct_outreach_v1")
    assert d["applicability"]["status"] == "APPLIES", d["applicability"]
    return d


def _exec(sid: str, rid: str, node: str, event: str = "EXECUTED"):
    return c.post(f"/session/{sid}/routes/{rid}/nodes/{node}/execution", json={"event": event})


def t_cross_context_blocked() -> None:
    sid_kons = _session(USER, "Saya konsultan IT, jual jasa ke klien bisnis B2B.", 30.0, 60.0)
    d = _direct_route(sid_kons)
    node = next(e["node"] for e in d["frontier"] if e["kind"] == "EXECUTE")
    sid_bengkel = _session(USER, "Saya punya bengkel mobil, pelanggan orang umum walk-in.", 15.0, 25.0)
    r = _exec(sid_bengkel, d["route_id"], node)
    assert r.status_code == 409, (r.status_code, r.text)
    # 17 Oct: the context MEMBERSHIP guard (Probe B remediation) outranks the
    # applicability guard — the 409 message may now belong to either guard; both
    # reject cross-context/Goal execution.
    assert "konteks" in r.json()["detail"], r.json()
    r2 = _exec(sid_bengkel, d["route_id"], node, event="RESET")
    assert r2.status_code == 409, "guard harus mendahului semua event (RESET juga)"


def t_same_strategy_context_allowed() -> None:
    """REVISED 17 Oct (Probe B remediation — a deliberate revision, not a regression):
    the old contract 'same-strategy, another session → 200' was EXACTLY the hole
    probe B proved (two different businesses, same strategy, sharing a route). Now:
    - another business context (different goal) → 409 EVEN IF strategy/applies match;
    - a follow-up session of the SAME map (prior_session_id → goal inherited) → 200
      (legitimate continuity — evidence & routes belong to the same context)."""
    sid1 = _session(USER, "Saya konsultan IT, jual jasa ke klien bisnis B2B.", 30.0, 60.0)
    d = _direct_route(sid1)
    node = next(e["node"] for e in d["frontier"] if e["kind"] == "EXECUTE")
    sid2 = _session(USER, "Saya punya agensi desain, kerja proyek klien tiap bulan.", 18.0, 40.0)
    r = _exec(sid2, d["route_id"], node)
    assert r.status_code == 409, "konteks bisnis lain harus ditolak (Probe B)"
    assert "konteks bisnis lain" in r.json()["detail"]
    # follow-up of the same map: prior_session_id → goal (goal_id) is inherited
    s3 = c.post("/session", json={
        "goal_text": "Saya konsultan IT, jual jasa ke klien bisnis B2B, lanjut kejar 60 juta.",
        "language": "id", "user_id": USER, "prior_session_id": sid1}).json()
    sid3 = s3["session_id"]
    g1 = store.get(sid1)
    assert (s3.get("goal") or {}).get("goal_id") == (g1.goal or {}).get("goal_id"), \
        "sesi lanjutan wajib mewarisi goal_id peta yang sama (kontinuitas konteks)"
    r2 = _exec(sid3, d["route_id"], node)
    assert r2.status_code == 200, (r2.status_code, r2.text)
    # the route's own owner may still proceed (that same node is already EXECUTED ->
    # VERIFY frontier; use another executable node when available)
    b = c.post(f"/session/{sid1}/routes").json()
    d1 = next(x for x in b["routes"] if x["route_id"] == d["route_id"])
    more = [e["node"] for e in d1["frontier"] if e["kind"] == "EXECUTE" and e["node"] != node]
    if more:
        assert _exec(sid1, d["route_id"], more[0]).status_code == 200


def main() -> int:
    fails = 0
    for name, fn in [("cross-context blocked", t_cross_context_blocked),
                     ("same-strategy context allowed", t_same_strategy_context_allowed)]:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            fails += 1
            print(f"FAIL {name}: {exc}")
    print("HASIL:", "SEMUA LULUS" if not fails else f"{fails} GAGAL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
