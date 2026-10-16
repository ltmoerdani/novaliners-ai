"""Phase 4 (internal-docs §10.6) — guard for Outcome Learning Store / nba_report endpoint.

Deterministic, 0 LLM: the session artifact is seeded via `model_construct` (skipping pydantic
validation — only the fields the route reads are needed). Follows the repo's standalone-runner
convention (test_knowledge_sync).

Gate: internal-docs §2.1 Gate 5(b) — the Decision Regret capture mechanism.
Run: .venv/bin/python evals/test_nba_report.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


# ---------------------------------------------------------------- store layer
from store import nba as nba_store  # noqa: E402

row = nba_store.record("test-sess", "lc-i01", "moved", "lead balas & minta proposal")
check("record valid: outcome dinormalisasi upper-ID",
      row["intervention_id"] == "LC-I01" and row["outcome"] == "moved")

try:
    nba_store.record("test-sess", "LC-I01", "semoga-berhasil")
    check("enum outcome ditolak", False)
except ValueError:
    check("enum outcome ditolak", True)

try:
    nba_store.record("test-sess", "", "moved")
    check("intervention_id kosong ditolak", False)
except ValueError:
    check("intervention_id kosong ditolak", True)

# ---------------------------------------------------------------- route layer
import tempfile as _tempfile_guard  # noqa: E402
from pathlib import Path as _PathGuard  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.main as _app_main_guard  # noqa: E402
import store.events as _event_store_guard  # noqa: E402
from app.main import app  # noqa: E402
from providers.mock import MockProvider as _MockGuard  # noqa: E402

# R4: this test USED TO call the real Z.ai (get_llm unpatched): burned quota on every gate-fast.
# Provider is forced to mock; conversation events go to a temp directory.
_app_main_guard.get_llm = lambda: _MockGuard()
assert _app_main_guard.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
_event_store_guard.EVENTS_DIR = _PathGuard(_tempfile_guard.mkdtemp(prefix="nvl-ev-"))
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from store.memory import store  # noqa: E402

c = TestClient(app)

sess = store.create(goal_text="test", language="id")
KA = {
    "tier1_matched": [], "tier2_matched": [], "flags": [],
    "interventions": [
        {"id": "LC-I01", "name": "Commitment Ladder", "for_constraint": "C6.3",
         "expected_evidence": "lead maju 1 tangga komitmen"},
    ],
    "nba_grounding": {"status": "GROUNDED", "claimed_id": "LC-I01", "matched_via": "field",
                      "intervention_ids": ["LC-I01"], "alternative_id": "", "alternative_name": "",
                      "expected_evidence": "", "for_constraint": "C6.3"},
}
# model_construct: skip validation — the route only reads knowledge_activation &
# primary_constraint_id.
sess.diagnosis = DiagnosisArtifact.model_construct(
    knowledge_activation=KA, primary_constraint_id="C6.3",
)

r = c.post(f"/session/{sess.id}/nba_report", json={
    "intervention_id": "LC-I01", "outcome": "not_moved", "notes": "diam setelah follow-up",
})
check("route: laporan valid → 200 + row",
      r.status_code == 200 and r.json()["report"]["outcome"] == "not_moved")

r = c.post(f"/session/{sess.id}/nba_report", json={"intervention_id": "XX-I99", "outcome": "moved"})
check("route: anti-fabrikasi ID asing → 422", r.status_code == 422,
      (r.json().get("detail") or "")[:60])

r = c.post(f"/session/{sess.id}/nba_report", json={"intervention_id": "LC-I01", "outcome": "hmm"})
check("route: outcome di luar enum → 422", r.status_code == 422)

r = c.post("/session/tidak-ada/nba_report", json={"intervention_id": "LC-I01", "outcome": "moved"})
check("route: session tak dikenal → 404", r.status_code == 404)

r = c.post(f"/session/{sess.id}/nba_report", json={
    "intervention_id": "lc-i01", "outcome": "regret", "notes": "seharusnya tidak dilakukan",
})
check("route: lowercase dinormalisasi + REGRET tercatat",
      r.status_code == 200 and r.json()["report"]["outcome"] == "regret")

summ = nba_store.summary()
check("summary: regret_rate terhitung",
      summ["total"] >= 3 and isinstance(summ["regret_rate"], float),
      json.dumps(summ["by_outcome"]))

# ---------------------------------------------------------------- verdict
fails = [r for r in _results if not r[1]]
_n_ok = len(_results) - len(fails)
print(f"\n{'=' * 50}\nHASIL: {_n_ok}/{len(_results)} PASS"
      + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌"))
sys.exit(1 if fails else 0)
