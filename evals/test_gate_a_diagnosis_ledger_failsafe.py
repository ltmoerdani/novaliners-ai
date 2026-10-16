"""Gate A / A1-F1 — the final diagnosis does NOT read a STALE ledger when adjudication fails.

Deterministic, 0 real LLM (mock provider). R4-E + PC-34/BC-06 + DCP-01/03.
Run: cd mvp && .venv/bin/python evals/test_gate_a_diagnosis_ledger_failsafe.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_TMP = Path(tempfile.mkdtemp(prefix="a1f1-"))
import store.adjudication_ledger as ledger  # noqa: E402

ledger._LEDGER_ROOT = _TMP / "ledger"
import store.funnel as funnel  # noqa: E402

funnel._PATH = _TMP / "funnel.jsonl"
import store.memory as mem  # noqa: E402

mem.PERSIST_DIR = _TMP / "sessions"
import store.path_states as ps  # noqa: E402

ps._BASE = _TMP
ps._STATES = _TMP / "path_states.json"
ps._HISTORY = _TMP / "path_history.jsonl"
import store.workspace as ws  # noqa: E402

ws._BASE = _TMP / "workspaces"

import agents.diagnosis as diag  # noqa: E402
import app.main as app_main  # noqa: E402
import ontology.mapper.live_adjudication as la  # noqa: E402
from core.navigation.requirement_state import MappingReader, RequirementState, unknown_state  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import Session  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'OK ' if ok else 'GAGAL'}  {name}" + (f" | {detail}" if detail else ""))


# ── A. pure guard (read boundary) ────────────────────────────────────────────
sup = {"e1"}


def _base_none(_rid: str):
    return None


g_all = app_main._ledger_state_guard(
    MappingReader({"rid.a": RequirementState("rid.a", satisfaction="PRESENT", adjudicated=True,
                                             evidence_refs=("e1",))}),
    _base_none, sup)
check("A1 guard: seluruh sitasi superseded → UNKNOWN by absence", g_all("rid.a") is None)

_mix_reader = MappingReader({"rid.b": RequirementState("rid.b", satisfaction="PRESENT", adjudicated=True,
                                                    evidence_refs=("e1", "e2"))})
g_mix = app_main._ledger_state_guard(_mix_reader, lambda rid: "PRESENT", sup)
check("A1 guard: sitasi campur (satu masih kini) → PRESENT dipertahankan (anti over-fix)",
      g_mix("rid.b") == "PRESENT")

g_noref = app_main._ledger_state_guard(
    MappingReader({"rid.c": RequirementState("rid.c", satisfaction="UNKNOWN", adjudicated=True,
                                             evidence_refs=())}),
    lambda rid: "UNKNOWN", sup)
check("A1 guard: entri tanpa sitasi → pembacaan dasar apa adanya", g_noref("rid.c") == "UNKNOWN")

g_absent = app_main._ledger_state_guard(MappingReader({}), _base_none, sup)
check("A1 guard: tanpa entri adjudikasi → UNKNOWN by absence", g_absent("rid.x") is None)
check("A1 guard: entri UNKNOWN by absence bukan adjudikasi", unknown_state("rid.x").adjudicated is False)


# ── B. real _diagnose seam: failed adjudication vs control ────────────────────
RID = "access.icp"
TXT = "ICP tertulis berisi jenis usaha, level, dan peran pembeli."
_orig_llm = app_main.get_llm
app_main.get_llm = lambda: MockProvider()


def run_case(user: str, fail: bool) -> tuple[object, object]:
    e1 = EvidenceItem(id="e1", signal=TXT, source_quote=TXT, level="self_reported", topic="REVENUE_STATE")
    la.run_live_adjudication(user, [e1], now=1, session_id="s-" + user)
    e1.superseded = True  # correction replaces the only claim for the RID
    prev = la.run_live_adjudication
    if fail:
        def _boom(*_a, **_k):
            raise RuntimeError("adjudication failed")
        la.run_live_adjudication = _boom
    s = Session(id="s-" + user, goal_text="naikkan omzet", language="en", user_id=user, evidence=[e1])
    s.transcript = [("user", TXT)]
    cap: dict = {}
    orig = diag.build_possible_paths

    def spy(*a, **k):
        cap["ls"] = k.get("ledger_state_of")
        return orig(*a, **k)

    diag.build_possible_paths = spy
    try:
        app_main._diagnose(s)
    finally:
        diag.build_possible_paths = orig
        la.run_live_adjudication = prev
        app_main.get_llm = _orig_llm
    ls = cap.get("ls")
    return (ledger.latest_status(user, RID), ls(RID) if ls else None)


try:
    led_ok, fwd_ok = run_case("u-a1fs-control", fail=False)
    check("kontrol (adjudikasi sukses): status final BUKAN PRESENT basi",
          led_ok == "UNKNOWN" and fwd_ok != "PRESENT", f"ledger={led_ok} fwd={fwd_ok}")

    led_fail, fwd_fail = run_case("u-a1fs-failure", fail=True)
    check("adjudikasi GAGAL: forwarded ke diagnosis final = UNKNOWN (bukan PRESENT basi)",
          fwd_fail is None, f"fwd={fwd_fail}")
    check("adjudikasi GAGAL: berkas ledger append-only tetap memuat PRESENT (sejarah tak dihapus)",
          led_fail == "PRESENT", f"ledger={led_fail}")
finally:
    app_main.get_llm = _orig_llm

fails = [r for r in _results if not r[1]]
print(f"\n{'=' * 50}\nHASIL A1-F1 ledger fail-safe: {len(_results) - len(fails)}/{len(_results)} PASS"
      + (" OK" if not fails else f" — {len(fails)} GAGAL"))
sys.exit(1 if fails else 0)
