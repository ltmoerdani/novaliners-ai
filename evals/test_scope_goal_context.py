"""R1-remediation gate — business-context scoping (goal_id) after Probes A/B/C.

Adversarial variations (17 Oct package, D3):
  1. Contamination via the PRODUCTION PATH: run_live_adjudication writes rows carrying
     a goal_id; readers of other contexts do not see them (Probe A, the original path).
  2. LEGACY entries (without goal_id) remain readable by both contexts — historical
     compatibility, without false promotion and without losing old data.
  3. Same goal_id across two sessions = SAME context: legitimate route reuse
     (ROUTE_REUSED, same route_id) — the same map's continuity is not broken.
  4. Goal revised (version up, same goal_id) → context stays the same.
  5. Legacy lineage (key without context_id) still matches context-None queries.
Pure unit + TestClient (mock provider), isolated store.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()

import store.events as ev  # noqa: E402
from store import adjudication_ledger as ledger  # noqa: E402
from store import goals as workspace_goals  # noqa: E402
from store import route_execution as rex  # noqa: E402
from store import route_lineages as rl  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="scope_ctx_"))
rl._BASE = _tmp / "lineages"
rex._BASE = _tmp / "exec"
ev.EVENTS_DIR = Path(tempfile.mkdtemp(prefix="scope_ctx_ev_"))
# 17 Oct (found during the gate): `isolate_store()` only redirects snapshot+events —
# the WORKSPACE stores (ledger, lineage, execution, goals) still point at production, so
# this suite wrote real adjudication rows to `store/workspaces/u-scope-*` and stale cross-run
# rows won last-wins on filtered reads. All workspace channels are redirected to the same tmp
# here (the same pattern as run_maps_r1_probes).
ledger._LEDGER_ROOT = _tmp / "ledger"
workspace_goals._BASE = _tmp / "goals"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.adjudicate import adjudicate  # noqa: E402
from evals.navigation_fixtures import revenue_artifact  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

app_main.get_llm = lambda: MockProvider()

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


_RULE = {
    "mode": "PARTIAL",
    "sufficient": {"any_of": [{"text_contains_any": ["icp sudah ditulis"]}]},
    "partial": {"any_of": [{"text_contains_any": ["draft icp"]}]},
    "no_decisive": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "contradicting": {"any_of": [{"text_contains_any": ["belum tahu target klien"]}]},
}


def _ev(text: str) -> list[EvidenceItem]:
    return [EvidenceItem(id="e0", signal=text, source_quote=text,
                         level="self_reported", topic="REVENUE_STATE")]


def t_production_write_is_goal_scoped() -> None:
    """The production write gate (`adjudicate_and_persist` — the ONE atomic gate used by
    run_live_adjudication with a goal_id ctx): rows carry goal_id, and readers of other
    contexts do NOT see their status. End-to-end via the original path is proven by
    probe A (run_maps_r1_probes)."""
    row = ledger.adjudicate_and_persist(
        "u-scope-a", "access.icp", _RULE, _ev("icp sudah ditulis: klien konsultan IT"),
        [{"requirement_id": "access.icp", "evidence_refs": ["e0"],
          "verification_method": "deterministic_predicate", "verified": True,
          "verified_at": 1}], evaluation_time=100, goal_id="goal-A")
    assert row.get("goal_id") == "goal-A", row
    assert ledger.latest_status("u-scope-a", "access.icp", goal_id="goal-A") == "PRESENT"
    other = ledger.latest_status("u-scope-a", "access.icp", goal_id="goal-B")
    assert other is None, f"konteks lain membaca PRESENT milik goal-A: {other}"


def t_legacy_entry_not_credited_to_context() -> None:
    """REVISED 17 Oct (D3 closure, INTENTIONAL policy revision — see the docstring of
    `_latest_entries`): the old contract 'legacy entries readable by every context' was a
    hole — unknown ownership was misread as shared ownership, so a PRESENT status from
    before goal_id could be credited to any business context. The policy is now:
      - reads with goal_id    → ONLY entries with the same goal_id (legacy is not
        credited — old data is not promoted into a context's ownership);
      - unfiltered reads (goal_id=None) → all entries (inspection/audit, Gate A
        sweep, recovery) — old data is not lost;
      - self-healing: the production path re-writes goal_id-bearing rows idempotently
        from the same evidence while a session runs."""
    out = adjudicate("legacy.req", _RULE, _ev("icp sudah ditulis"),
                     [{"requirement_id": "legacy.req", "evidence_refs": ["e0"],
                       "verification_method": "deterministic_predicate",
                       "verified": True, "verified_at": 1}], evaluation_time=1)
    row = ledger._record_adjudication("u-scope-b", out, rule_mode="PARTIAL")
    assert row is not None and "goal_id" not in row, row
    # context-scoped read: legacy is NOT credited (ownership unknown)
    assert ledger.latest_status("u-scope-b", "legacy.req", goal_id="goal-X") is None, \
        "entri legacy tidak boleh dikreditkan ke konteks tanpa bukti kepemilikan"
    assert ledger.latest_status("u-scope-b", "legacy.req", goal_id="goal-Y") is None
    # unfiltered read: all entries remain readable (audit/inspection — nothing lost)
    assert ledger.latest_status("u-scope-b", "legacy.req") == "PRESENT"
    assert ledger.latest_entry("u-scope-b", "legacy.req") is not None


def _mk_session(user: str, goal_id: str, *, prior: str | None = None) -> str:
    c = TestClient(app_main.app)
    body: dict = {"goal_text": "Saya konsultan IT jasa B2B, dari 30 ke 60 juta per bulan.",
                  "language": "id", "user_id": user, "goal_id": goal_id}
    if prior:
        body["prior_session_id"] = prior
    r = c.post("/session", json=body)
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _direct_route(sid: str) -> dict:
    c = TestClient(app_main.app)
    s = store.get(sid)
    s.evidence = _ev("Saya konsultan IT, jual jasa ke klien bisnis B2B via website.")
    s.diagnosis = revenue_artifact(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0,
                                   capacity_utilization=0.5, demand_exists=True, avg_deal_size=10.0)
    store.save(s)
    b = c.post(f"/session/{sid}/routes").json()
    d = next(x for x in b["routes"] if x["template_id"] == "direct_outreach_v1")
    return d


def t_same_goal_reuses_route() -> None:
    """Same goal_id (two sessions, same context) → ROUTE_REUSED, SAME route_id —
    legitimate continuity is not broken by the remediation."""
    s1 = _mk_session("u-scope-c", "goal-C")
    d1 = _direct_route(s1)
    s2 = _mk_session("u-scope-c", "goal-C")
    d2 = _direct_route(s2)
    assert d2["route_id"] == d1["route_id"], (d1["route_id"], d2["route_id"])
    assert d2["outcome"] == "ROUTE_REUSED", d2["outcome"]


def t_goal_revision_keeps_context() -> None:
    """Goal revised (version +1, SAME goal_id) → context unchanged: legitimate reuse."""
    s1 = _mk_session("u-scope-d", "goal-D")
    d1 = _direct_route(s1)
    _mk_session("u-scope-d", "goal-D")  # second session, same context
    # goal revision: the goals.jsonl row gets version+1 — goal_id does not change
    from store import goals as workspace_goals
    g = {"goal_id": "goal-D", "version": 2, "metric_id": "revenue_monthly",
         "text": "dari 30 ke 60 juta (revisi)", "target_min": 60.0}
    workspace_goals.upsert_goal("u-scope-d", {"type": "GOAL_REVISED", "ts": 1,
                                              "goal_id": "goal-D", "version": 2, "goal": g})
    d2 = _direct_route(_mk_session("u-scope-d", "goal-D"))
    assert d2["route_id"] == d1["route_id"], "revisi goal (goal_id sama) tidak boleh memecah konteks"


def t_legacy_lineage_matches_none_context() -> None:
    """Legacy lineage (key without context_id) still matches context-None queries —
    historical matching compatibility (old routes are not orphaned)."""
    key3 = {"goal_anchor": "A1", "strategy_id": "direct_outreach",
            "scope_anchor": ["state:user"]}
    lin = {"route_id": "11111111-1111-4111-8111-111111111111",
           "reconciliation_key": dict(key3),
           "applicability": {"status": "APPLIES", "evidence": []},
           "motion": "MOTION_A", "lineage_status": "OPEN",
           "revisions": [{"revision_no": 1, "label": "l", "based_on": {}, "nodes": []}]}
    rl.append_lineage("u-scope-e", {"lineage": lin, "frontier": []})
    assert rl.find_open_by_key("u-scope-e", dict(key3)) is not None
    assert rl.find_open_by_key("u-scope-e", {**key3, "context_id": None}) is not None
    assert rl.find_open_by_key("u-scope-e", {**key3, "context_id": "goal-Z"}) is None


def t_followup_inherits_goal_via_api() -> None:
    """A follow-up session (prior_session_id) inherits the same map's goal — proof of
    context continuity at the create_session gate."""
    c = TestClient(app_main.app)
    s1 = _mk_session("u-scope-f", "goal-F")
    r = c.post("/session", json={"goal_text": "lanjutan peta yang sama", "language": "id",
                                 "user_id": "u-scope-f", "prior_session_id": s1})
    assert r.status_code == 200, r.text
    g2 = (r.json().get("goal") or {}).get("goal_id")
    assert g2 == "goal-F", f"sesi lanjutan tidak mewarisi goal: {g2}"


ALL = [
    ("tulisan produksi ber-goal & terisolasi", t_production_write_is_goal_scoped),
    ("entri legacy tidak dikreditkan ke konteks (D3-penutupan)", t_legacy_entry_not_credited_to_context),
    ("same goal → reuse route sah", t_same_goal_reuses_route),
    ("revisi goal (goal_id sama) tetap satu konteks", t_goal_revision_keeps_context),
    ("lineage legacy cocok konteks-None", t_legacy_lineage_matches_none_context),
    ("sesi lanjutan mewarisi goal via API", t_followup_inherits_goal_via_api),
]


def main() -> int:
    for name, fn in ALL:
        check(name, fn)
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, msg in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS — R1 remediasi scope konteks")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
