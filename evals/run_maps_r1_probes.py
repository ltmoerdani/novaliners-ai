"""R1 PROBE RUNNER — Maps Route Experience Reconciliation (int 02 §2, package v0.2).

Three RUNTIME collision probes (TestClient + temporary store + mock provider —
the pattern of evals/test_route_execution.py). The probes use REAL components: the
adjudicate -> ledger -> reader -> composer -> endpoint pipeline. NO mock on the
logic under test.

  Probe A — requirement contamination: one user, two business contexts (two
    "Maps"); a PRESENT adjudication for context A's requirement must never be
    read as SATISFIED by context B, which never proved it.
  Probe B — route identity collision: two business contexts with the same
    strategy (identical goal_anchor + strategy_id) must not share one RouteLineage.
  Probe C — cross-Goal execution: a node owned by context A's route must not
    be executable through context C's session, which does not load that route.

Verdict per probe: PASS (behavior matches the contract) / FAIL (violation
proven). FAIL => R1 status BLOCKED + REMEDIATION_REQUIRED (int 02 §2).
Artifact: eval_maps_r1_probes.json. NOT part of gate-fast until all PASS.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — the production store stays untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.route_execution as rex  # noqa: E402
import store.route_lineages as rl  # noqa: E402

_tmp = Path(tempfile.mkdtemp(prefix="r1_probe_"))
rl._BASE = _tmp / "lineages"
rex._BASE = _tmp / "exec"
ledger._LEDGER_ROOT = _tmp / "ledger"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as _app_main  # noqa: E402
import store.events as _event_store  # noqa: E402
from app.main import app  # noqa: E402
from providers.mock import MockProvider  # noqa: E402

_app_main.get_llm = lambda: MockProvider()
assert _app_main.get_llm().name == "mock", "probe hanya boleh jalan dengan provider mock"
_event_store.EVENTS_DIR = Path(tempfile.mkdtemp(prefix="nvl-r1-ev-"))

from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.adjudicate import adjudicate  # noqa: E402
from evals.navigation_fixtures import revenue_artifact  # noqa: E402
from store.memory import store  # noqa: E402

c = TestClient(app)
_created: list[str] = []

# Business context: direct_outreach applicability keywords = b2b/services/consulting/
# agency/client projects (template applies_when). Context C is deliberately WITHOUT keywords.
CTX_KONSULTAN = ("naik ke 30 juta per bulan",
                 "Saya konsultan IT, jual jasa ke klien bisnis B2B.", 30.0, 60.0)
CTX_AGENSI = ("desain agensi capai 40 juta",
              "Saya punya agensi desain, kerja proyek klien tiap bulan.", 18.0, 40.0)
CTX_BENGKEL = ("bengkel naik dari 15 ke 25 juta",
               "Saya punya bengkel mobil, pelanggan orang umum walk-in.", 15.0, 25.0)

# Synthetic PARTIAL rule (pattern of ontology/adjudication/test_adjudication_path.py)
_RULE_ICP = {
    "mode": "PARTIAL",
    "sufficient": {"any_of": [{"text_contains_any": ["icp sudah ditulis", "profil klien ideal jelas"]}]},
    "partial": {"any_of": [{"text_contains_any": ["draft icp"]}]},
    "no_decisive": {"any_of": [{"text_contains_any": ["__never__"]}]},
    "contradicting": {"any_of": [{"text_contains_any": ["belum tahu target klien"]}]},
}


def _session(user_id: str, ctx: tuple) -> str:
    goal, text, cur, tgt = ctx
    r = c.post("/session", json={"goal_text": goal, "language": "id", "user_id": user_id})
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


def _routes(sid: str) -> dict:
    return c.post(f"/session/{sid}/routes").json()


def _direct(body: dict) -> dict | None:
    return next((x for x in body.get("routes", []) if x.get("template_id") == "direct_outreach_v1"), None)


def _node_sat(route: dict, requirement_id: str) -> str | None:
    for n in route.get("nodes", []):
        if (n.get("resolves") or [""])[0] == requirement_id:
            return (n.get("satisfaction") or {}).get("status")
    return None


def probe_a() -> dict:
    """PRESENT for access.icp proven in the CONSULTANT context; the AGENCY context
    (same user, never proven anything about their ICP) must not read it as
    SATISFIED."""
    user = "u-r1-a"
    sid_a = _session(user, CTX_KONSULTAN)
    d_a = _direct(_routes(sid_a))
    assert d_a, "fixture: direct_outreach harus lahir di konteks konsultan"

    ev = EvidenceItem(id="ev.icp", signal="icp sudah ditulis: klien konsultan IT",
                      source_quote="icp sudah ditulis: klien konsultan IT",
                      level="self_reported", topic="REVENUE_STATE")
    out = adjudicate("access.icp", _RULE_ICP, [ev],
                     [{"requirement_id": "access.icp", "evidence_refs": ["ev.icp"],
                       "verification_method": "deterministic_predicate",
                       "verified": True, "verified_at": 1}], evaluation_time=100)
    # Probe A remediation (17 Oct): the adjudication write uses the PRODUCTION FORM —
    # with goal_id (session A's business context), exactly like the
    # run_live_adjudication path. A row without goal_id is legacy (read by all
    # contexts) and no longer represents a production write.
    _goal_a = (store.get(sid_a).goal or {}).get("goal_id")
    row = ledger._record_adjudication(user, out, rule_mode="PARTIAL", goal_id=_goal_a)
    assert row is not None and row["adjudication"]["status"] == "PRESENT", out
    ledger_a = ledger.latest_status(user, "access.icp")
    assert ledger_a == "PRESENT"

    sid_b = _session(user, CTX_AGENSI)
    d_b = _direct(_routes(sid_b))
    assert d_b, "fixture: direct_outreach juga lahir di konteks agensi"
    sat_b = _node_sat(d_b, "access.icp")
    desired, actual = "UNKNOWN", sat_b
    return {"desired": desired, "actual": actual, "verdict": "PASS" if actual == desired else "FAIL",
            "evidence": {"ledger_status_user_scope": ledger_a, "satisfaction_di_ctx_b": sat_b,
                         "note": "reader per-user context-blind; konteks B tak pernah membuktikan icp"}}


def probe_b() -> dict:
    """Two different business contexts (same strategy) must NOT share a route_id."""
    user = "u-r1-b"
    d1 = _direct(_routes(_session(user, CTX_KONSULTAN)))
    d2 = _direct(_routes(_session(user, CTX_AGENSI)))
    assert d1 and d2
    same = d1["route_id"] == d2["route_id"]
    desired = "berbeda (lineage per konteks)"
    actual = "sama (ROUTE_REUSED lintas konteks)" if same else "berbeda"
    return {"desired": desired, "actual": actual, "verdict": "FAIL" if same else "PASS",
            "evidence": {"route_id_ctx1": d1["route_id"], "route_id_ctx2": d2["route_id"],
                         "note": "reconciliation key = goal_anchor+strategy+scope(state:user) "
                         "tanpa dimensi konteks"}}


def probe_c() -> dict:
    """Executing a node of context A's route through the GARAGE context session must be
    REJECTED (409). ORDER MATTERS: execution runs WITHOUT composing context C first —
    composing another context OVERWRITES the shared applicability lineage (the
    side effect of collision B: last-caller-wins), which would make the 409 happen
    for the wrong reason."""
    user = "u-r1-c"
    sid_a = _session(user, CTX_KONSULTAN)
    d_a = _direct(_routes(sid_a))
    assert d_a
    node = next((e["node"] for e in d_a["frontier"] if e["kind"] == "EXECUTE"), None)
    assert node, d_a["frontier"]
    sid_c = _session(user, CTX_BENGKEL)
    # execute directly — do not compose ctx C first (see the docstring note)
    code = c.post(f"/session/{sid_c}/routes/{d_a['route_id']}/nodes/{node}/execution",
                  json={"event": "EXECUTED"}).status_code
    body_c = _routes(sid_c)
    has_route_c = any(r.get("route_id") == d_a["route_id"] for r in body_c.get("routes", []))
    d_a2 = _direct(_routes(sid_a))  # context A recomposes: who reports applicability?
    app_a_after = (d_a2 or {}).get("applicability", {}).get("status")
    desired = 409
    verdict = "PASS" if code == desired else "FAIL"
    return {"desired": f"HTTP {desired}", "actual": f"HTTP {code}", "verdict": verdict,
            "evidence": {"route_in_ctx_c_navigation": has_route_c, "http": code,
                         "applicability_ctx_a_setelah_ctx_c_compose": app_a_after,
                         "note": "guard: route harus termuat di hasil composition sesi pemanggil; "
                                 "kolisi B membuat lineage bersama bisa termutasi sesi lain"}}


def _sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def main() -> int:
    probes = {"A_requirement_contamination": probe_a,
              "B_route_identity_collision": probe_b,
              "C_cross_goal_execution": probe_c}
    results = {}
    for name, fn in probes.items():
        r = fn()
        results[name] = r
        print(f"[probe {name[-1]}] {name}: verdict={r['verdict']} "
              f"(desired={r['desired']!r}, actual={r['actual']!r})")
    art = {"timestamp": datetime.now(timezone.utc).isoformat(), "sha": _sha(),
           "policy": "FAIL => R1 BLOCKED + REMEDIATION_REQUIRED (dok 02 §2 v0.2)",
           "probes": results,
           "summary": {k: v["verdict"] for k, v in results.items()}}
    out = Path(__file__).resolve().parents[1] / "eval_maps_r1_probes.json"
    out.write_text(json.dumps(art, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"artefak: {out}")
    n_fail = sum(1 for v in results.values() if v["verdict"] == "FAIL")
    print(f"HASIL: {len(results) - n_fail} PASS, {n_fail} FAIL")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
