"""S2-B - Goal Creation & Confirmation Authority (int 16 S1/S2-B; RC-06, CP-01/02/05).

Negative regression: the text parser is NOT a second authority. A target is only valid from explicit
structured input or an active canonical goal claim; current revenue figures, personal income, desires,
and historical targets must NOT become the active Goal target.

Run: .venv/bin/python evals/test_recovery_goal_authority.py  (deterministic, no network)
"""
from __future__ import annotations

import atexit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store dialihkan ke tmp — store produksi tak tersentuh

import store.adjudication_ledger as ledger  # noqa: E402
import store.events as event_store  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="nvl-goal-auth-"))
rl._BASE = _TMP / "lineages"
ledger._LEDGER_ROOT = _TMP / "ledger"
workspace._BASE = _TMP / "workspaces"
route_execution._BASE = _TMP / "workspaces"
funnel._PATH = _TMP / "funnel.jsonl"
path_states._BASE = _TMP
path_states._STATES = _TMP / "path_states.json"
path_states._HISTORY = _TMP / "path_history.jsonl"
event_store.EVENTS_DIR = _TMP / "events"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from core.semantic.contract import SemanticObservation  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

_PASS = 0
_FAIL = 0
_created = []


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print("  OK  " + name)
    else:
        _FAIL += 1
        print("  GAGAL  " + name + (" - " + str(detail) if detail else ""))


class Hybrid(MockProvider):
    name = "mock"

    def __init__(self):
        super().__init__()
        self.sem = []

    def structured_call(self, schema, system, user, retries=2):
        if schema is SemanticObservation and self.sem:
            return self.sem.pop(0)
        return super().structured_call(schema, system, user, retries)


LLM = Hybrid()
app_main.get_llm = lambda: LLM
client = TestClient(app_main.app)
atexit.register(lambda: [(store.PERSIST_DIR / (sid + ".json")).unlink(missing_ok=True) for sid in _created])


def obs(*claims, relations=()):
    return SemanticObservation(contract_version="so.v1", language="id", claims=list(claims),
                               relations=list(relations), uncertainties=[])


def cl(*a, **kw):
    import test_recovery_semantic as R
    return R.cl(*a, **kw)


def qty(**kw):
    import test_recovery_semantic as R
    return R.qty(**kw)


def new_session(user, goal, **extra):
    body = {"goal_text": goal, "language": "id"}
    body.update(extra)
    body["user_id"] = user
    r = client.post("/session", json=body)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _created.append(sid)
    return sid


def say(sid, text):
    return client.post("/session/" + sid + "/message", json={"text": text})


def target_of(sid):
    g = store.get(sid).goal or {}
    return g.get("target"), g.get("target_origin")


def test_current_revenue_not_target():
    print("S2-B-1 - angka pendapatan SAAT INI tidak menjadi target Goal")
    LLM.sem = [obs(cl("c0", "claim", "omzet", "is", "Omzet saya sekarang Rp18 juta per bulan",
                      quantity=qty(value_kind="exact", value=18, unit="juta", period="monthly")))]
    sid = new_session("u-ga1", "Omzet saya sekarang Rp18 juta per bulan")
    t, origin = target_of(sid)
    check("target tidak diisi dari pendapatan saat ini", t is None, (t, origin))
    check("target_origin bukan klaim eksplisit palsu", origin in ("none", ""), origin)


def test_personal_income_not_business_target():
    print("S2-B-2 - penghasilan pribadi tidak menjadi target revenue usaha")
    LLM.sem = [obs(cl("c0", "claim", "gaji", "is", "Gaji pribadi saya Rp15 juta per bulan",
                      quantity=qty(value_kind="exact", value=15, unit="juta", period="monthly")))]
    sid = new_session("u-ga2", "Gaji pribadi saya Rp15 juta per bulan")
    t, origin = target_of(sid)
    check("target usaha tidak diisi dari gaji pribadi", t is None, (t, origin))


def test_desire_not_numeric_goal():
    print("S2-B-3 - keinginan tidak menjadi Goal bernomor")
    LLM.sem = [obs(cl("c0", "desire", "saya", "wants", "Saya ingin bisnis lebih tenang"))]
    sid = new_session("u-ga3", "Saya ingin bisnis lebih tenang")
    t, origin = target_of(sid)
    check("desire tidak menghasilkan target", t is None, (t, origin))


def test_historical_target_not_current():
    print("S2-B-4 - target HISTORIS tidak aktif sebagai target kini")
    LLM.sem = [obs(cl("c0", "claim", "omzet", "was", "Dulu target saya Rp50 juta per bulan", tense="past",
                      quantity=qty(value_kind="exact", value=50, unit="juta", period="monthly")))]
    sid = new_session("u-ga4", "Dulu target saya Rp50 juta per bulan")
    t, origin = target_of(sid)
    check("target historis tidak diwariskan sebagai target aktif", t is None, (t, origin))


def test_goal_correction_clears_obsolete_target():
    print("S2-B-5 - koreksi Goal tidak meninggalkan target usang")
    LLM.sem = [obs(cl("c0", "goal", "omzet", "target", "Target omzet saya Rp40 juta per bulan",
                      tense="future", quantity=qty(value_kind="exact", value=40, unit="juta",
                                                   period="monthly")))]
    sid = new_session("u-ga5", "Target omzet saya Rp40 juta per bulan")
    t0, _ = target_of(sid)
    check("target awal terbaca dari klaim goal kanonik", t0 == 40.0, t0)
    nodes = store.get(sid).state_graph["nodes"]
    goal_node = [nid for nid, n in nodes.items() if (n.get("type") == "goal")]
    assert goal_node, "klaim goal tidak ter-commit"
    LLM.sem = [obs(cl("c1", "goal", "omzet", "target", "Target omzet saya sekarang Rp25 juta per bulan",
                      tense="future", quantity=qty(value_kind="exact", value=25, unit="juta",
                                                   period="monthly"),
                      supersedes=goal_node[0], revision_kind="correction", revision_reason="revisi"))]
    say(sid, "Target omzet saya sekarang Rp25 juta per bulan")
    t1, _ = target_of(sid)
    check("target digantikan nilai baru, bukan akumulasi/duplikasi", t1 == 25.0, t1)


def test_parser_target_released_when_canonical_says_no_goal():
    print("S2-B-6 - target parser dilepas saat kanonik tidak punya klaim goal aktif")
    # the text triggers the target parser (goal_fallback) but the canonical observation = an ordinary
    # claim (not a goal)
    LLM.sem = [obs(cl("c0", "claim", "omzet", "is", "Omzet saya Rp18 juta per bulan sekarang",
                      quantity=qty(value_kind="exact", value=18, unit="juta", period="monthly")))]
    sid = new_session("u-ga6", "Omzet saya Rp18 juta per bulan sekarang")
    t, origin = target_of(sid)
    check("parser tidak mempertahankan target yang tak dikonfirmasi kanonik", t is None, (t, origin))
    check("tidak ada klaim goal aktif di graph",
          not [n for n in store.get(sid).state_graph["nodes"].values() if n.get("type") == "goal"])


def test_explicit_api_target_preserved():
    print("S2-B-7 - input eksplisit terstruktur (API) tetap otoritatif")
    LLM.sem = [obs(cl("c0", "claim", "omzet", "is", "Omzet saya Rp18 juta per bulan",
                      quantity=qty(value_kind="exact", value=18, unit="juta", period="monthly")))]
    sid = new_session("u-ga7", "Omzet saya Rp18 juta per bulan", target=60,
                      metric_id="revenue_monthly", direction="INCREASE_TO_THRESHOLD", unit="Rp juta/bulan")
    t, origin = target_of(sid)
    check("target eksplisit API tidak ditimpa/dilepas parser", t == 60.0, (t, origin))
    check("origin tercatat explicit_input", origin == "explicit_input", origin)


TESTS = [
    test_current_revenue_not_target,
    test_personal_income_not_business_target,
    test_desire_not_numeric_goal,
    test_historical_target_not_current,
    test_goal_correction_clears_obsolete_target,
    test_parser_target_released_when_canonical_says_no_goal,
    test_explicit_api_target_preserved,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception:
            import traceback
            traceback.print_exc()
            globals()["_FAIL"] += 1
    print("")
    print("S2-B GOAL AUTHORITY: " + str(_PASS) + " passed, " + str(_FAIL) + " failed")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
