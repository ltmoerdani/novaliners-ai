"""S4 — one decision PRESENTED at GET /navigation (projection) matches POST /message.

Contract (AGENT-N findings; int 20 S4):
  N1 move.kind/focus/reason = presented (nm.v2 + guard), not the deterministic candidate.
  N2 technical policy/tier (degraded/error_code/retry_reasoning/checkpoint) NOT dropped by projection.
  N3 last_logged.kind consistent with move.kind (presented, not decision).
  N4 move.text = the text actually presented.
  N5 NO business-status calculator in the projection (decision-field pass-through only).

Provider = deterministic mock. Run: .venv/bin/python evals/test_navigation_decision_passthrough.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import store  # noqa: E402

app_main.get_llm = lambda: MockProvider()
assert app_main.get_llm().name == "mock"
client = TestClient(app_main.app)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


r0 = client.post("/session", json={"goal_text": "Saya mau Rp20 juta per bulan dalam 90 hari.",
                                   "language": "en", "user_id": "u-nav-pass",
                                   "desire": "Pendapatan Rp8 juta per bulan dari 2 klien."})
assert r0.status_code == 200, r0.text
sid = r0.json()["session_id"]
r1 = client.post(f"/session/{sid}/message", json={"text": "Ada 3 orang bertanya soal jasa saya bulan ini."})
assert r1.status_code == 200, r1.text

s = store.get(sid)
last = s.planner_log[-1]
presented = last.get("presented") or last["decision"]
j = client.get(f"/session/{sid}/navigation").json()
move = j["move"]

check("N1 move.kind == presented.kind", move["kind"] == presented["kind"],
      f"move={move['kind']} presented={presented['kind']}")
check("N1b move.focus == presented.focus", move["focus"] == presented["focus"], str(move["focus"]))
check("N1c move.reason == presented.reason (jejak guard/planner utuh)",
      move["reason"] == presented["reason"], "reason beda")
check("N2 move.policy == presented.policy (tidak dibuang)",
      move.get("policy") == presented.get("policy"), f"move.policy={move.get('policy')}")
for k in ("degraded", "error_code", "retry_reasoning", "checkpoint", "move_id", "source"):
    check(f"N2 {k}: ada di move bila ada di presented",
          (k in move) == (presented.get(k) is not None),
          f"presented={presented.get(k)!r} move={move.get(k)!r}")
check("N3 last_logged.kind == move.kind (presented, bukan decision)",
      j["last_logged"]["kind"] == move["kind"],
      f"last_logged={j['last_logged']['kind']} move={move['kind']}")
check("N4 move.text == teks yang disajikan", move["text"] == last["text"]["text"],
      "teks proyeksi beda")
allowed = {"kind", "intent", "focus", "stop", "text", "headline", "reason",
           "policy", "degraded", "error_code", "retry_reasoning", "checkpoint",
           "move_id", "source", "lang", "path_id"}
check("N5 proyeksi hanya field keputusan (tanpa kalkulasi status bisnis)",
      set(move) <= allowed, str(sorted(set(move) - allowed)))
# R5/P1-1: EXPLICIT Path affiliation (nullable) — client need not borrow from the route selector.
check("N6 move membawa path_id eksplisit (nullable, bukan field hilang)",
      "path_id" in move, str(sorted(move)))
if (move.get("focus") or {}).get("type") == "path":
    check("N6b focus path -> path_id sama dengan focus.id",
          move.get("path_id") == move["focus"]["id"], f"path_id={move.get('path_id')} focus={move['focus']}")

# N2 ADVERSARIAL (A5 F-02): on the happy path the technical fields above are ABSENT, making the
# pass-through check vacuous. Run one turn with the provider DEAD so degraded/error_code/
# retry_reasoning actually form, then assert the GET /navigation projection carries their values.
from core.reasoning.contract import NextMoveProposal  # noqa: E402


class _DeadReasoner(MockProvider):
    def structured_call(self, schema, system, user, retries=2):
        if schema is NextMoveProposal:
            raise RuntimeError("provider_unavailable (injeksi uji)")
        return super().structured_call(schema, system, user, retries)


app_main.get_llm = lambda: _DeadReasoner()
r2 = client.post(f"/session/{sid}/message", json={"text": "Tidak ada kabar baru soal itu."})
check("N2-degraded: giliran provider mati tetap dilayani (bukan 500)", r2.status_code == 200, r2.text[:160])
degraded = r2.json().get("next_move") or {}
check("N2-degraded: presented HOLD + degraded + error_code + retry_reasoning",
      degraded.get("kind") == "HOLD" and degraded.get("degraded") is True
      and bool(degraded.get("error_code")) and degraded.get("retry_reasoning") is True, str(degraded))
m2 = client.get(f"/session/{sid}/navigation").json()["move"]
for k in ("degraded", "error_code", "retry_reasoning"):
    check(f"N2-degraded: GET /navigation membawa {k} = nilai presented",
          m2.get(k) == degraded.get(k), f"move={m2.get(k)!r} presented={degraded.get(k)!r}")
check("N2-degraded: HOLD teknis (degraded) BUKAN STOP bisnis",
      m2.get("stop") is False and m2.get("kind") == "HOLD")

app_main.get_llm = lambda: MockProvider()

print()
failed = [r for r in RESULTS if not r[1]]
print(f"{'❌ FAIL' if failed else '✅ PASS'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
for name, _ok, detail in failed:
    print(f"   ❌ {name}: {detail[:200]}")
sys.exit(1 if failed else 0)
