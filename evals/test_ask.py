"""Ask screen: follow-up discussion, guarded for human language
(internal-docs §4).

Deterministic, 0 real LLM. Run: .venv/bin/python evals/test_ask.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

from fastapi.testclient import TestClient  # noqa: E402

from agents.ask import ask_session, readiness_lines  # noqa: E402
from app.main import app  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.schema.ask import AskReply  # noqa: E402
from evals.navigation_fixtures import revenue_artifact  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import Session, store  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def make_session(sid: str = "ask1") -> Session:
    goal = (
        "I left my job as a marketing manager. I want Rp20 million a month within 90 days. "
        "I have no clients yet."
    )
    s = Session(id=sid, goal_text=goal, language="en")
    s.transcript = [("user", goal), ("user", "Marketing selama 8 tahun, belum punya client sama sekali.")]
    s.evidence = [
        EvidenceItem(
            id="ev-1",
            signal="no active clients",
            level="self_reported",
            source_quote="no clients",
            topic="GOAL",
        )
    ]
    # capacity slack (met), demand unmeasured (unknown), WtP negative (missing on the repricing path)
    s.diagnosis = revenue_artifact(
        current_monthly=30.0,
        target_monthly=60.0,
        gap_monthly=30.0,
        capacity_utilization=0.5,
        willingness_to_pay="PRICE_SENSITIVE",
        avg_deal_size=10.0,
    )
    return s


s = make_session()

# 1 — what each path needs enters the context, including all three states
rl = readiness_lines(s.diagnosis)
check(
    "konteks path memuat met/missing/unknown",
    # Round 7 (e0553724): spare capacity requirement = delivery.spare_capacity
    # ("Room left in your week"); WTP at current price shown via client_expansion.
    "met: Room left in your week" in rl
    and "missing: Someone willing to pay that price" in rl
    and "unknown: Demand exists" in rl,
    rl,
)
check("konteks path memuat cara mendapatkannya", "Show that clients pay full price today" in rl)
check("konteks path memakai kunci path_id engine, bukan motion", "- path.direct_outreach:" in rl)

# 1b — CONFLICT ≠ ABSENT ≠ PRESENT (ontology invariant): a `settled=False` item must never be read out
# as met or missing — two evidence readings disagree, it is not a measurable gap.
_proj = {
    "navigation": {"status": "CURRENT"},
    "paths": [
        {
            "key": "path.direct_outreach",
            "status": "OPEN",
            "items": [
                {"key": "req.capacity", "state": "PRESENT", "settled": True,
                 "title": {"text": "Hours you can spare"}},
                {"key": "req.wtp", "state": "ABSENT", "settled": True,
                 "title": {"text": "Someone willing to pay"}, "unlock": {"text": "Show a paid deal"}},
                {"key": "req.demand", "state": "ABSENT", "settled": False,
                 "title": {"text": "Demand exists"}},  # evidence readings contradict each other
                {"key": "req.pricing", "state": "PRESENT", "settled": False,
                 "title": {"text": "Written price anchor"}},  # conflict on a PRESENT item
            ],
        }
    ],
}
rlc = readiness_lines(s.diagnosis, projection=_proj)
check(
    "butir konflik tidak pernah di met/missing — selalu unknown dengan wording CONFLICT",
    "unknown: Demand exists (conflict: two readings of the evidence disagree, not settled); "
    "Written price anchor (conflict: two readings of the evidence disagree, not settled)" in rlc
    and "met: Hours you can spare" in rlc
    and "missing: Someone willing to pay (to get it: Show a paid deal)" in rlc
    and "Demand exists" not in rlc.split("missing:")[1].split("unknown:")[0]
    and "Written price anchor" not in rlc.split("met:")[1].split("missing:")[0],
    rlc,
)

# 2 — mock end-to-end: clean, not dropped, follow-up questions present
out = ask_session(MockProvider(), s, "Kenapa ini yang menahan saya?", [], "")
check("mock: jawaban tidak dibuang", out["dropped"] is False, str(out))
check("mock: ada jawaban dan saran pertanyaan", bool(out["answer"]) and 1 <= len(out["follow_ups"]) <= 3)


# 3 — a violating answer gets ONE repair; one that still violates is dropped
# and replaced with an honest sentence
class Stubborn(MockProvider):
    calls = 0

    def structured_call(self, schema, system, user, retries=2):
        Stubborn.calls += 1
        return AskReply(
            answer="Jangan SCALE akuisisi dulu, urutkan 4 fase konversi.", follow_ups=["Apa itu funnel?"]
        )


o2 = ask_session(Stubborn(), s, "Apa langkah saya?", [], "")
check("perbaikan hanya satu kali", Stubborn.calls == 2, f"calls={Stubborn.calls}")
check("jawaban yang tetap melanggar dibuang", o2["dropped"] is True and "scale" not in o2["answer"].lower())
check("saran pertanyaan ikut dibuang", o2["follow_ups"] == [])
check("kalimat pengganti jujur", "Diagnosis" in o2["answer"])


# 4 — invented numbers rejected, numbers from the question or a source accepted;
# jargon-laden follow-ups filtered
class Numbers(MockProvider):
    def structured_call(self, schema, system, user, retries=2):
        return AskReply(answer="Anda butuh 37 klien.", follow_ups=[])


check("angka karangan dibuang", ask_session(Numbers(), s, "Berapa klien?", [], "")["dropped"] is True)


class Cites(MockProvider):
    def structured_call(self, schema, system, user, retries=2):
        return AskReply(
            answer="Ya, 15 hari cukup untuk mencoba.",
            follow_ups=["Apa itu funnel?", "Apa langkah pertama saya?"],
        )


o3 = ask_session(Cites(), s, "Apakah 15 hari cukup?", [], "")
check("angka dari pertanyaan diterima", o3["dropped"] is False, str(o3))
check(
    "saran pertanyaan berjargon disaring",
    o3["follow_ups"] == ["Apa langkah pertama saya?"],
    str(o3["follow_ups"]),
)

# 5 — conversation history enters the prompt, path focus too
seen: dict = {}


class Spy(MockProvider):
    def structured_call(self, schema, system, user, retries=2):
        seen["user"] = user
        return super().structured_call(schema, system, user)


ask_session(
    Spy(),
    s,
    "Lalu apa?",
    [{"role": "user", "text": "Kenapa?"}, {"role": "assistant", "text": "Karena begini."}],
    "Paid ads",
)
check(
    "riwayat percakapan ada di prompt",
    "User: Kenapa?" in seen["user"] and "You: Karena begini." in seen["user"],
)
check("fokus jalur ada di prompt", "THE USER IS LOOKING AT: Paid ads" in seen["user"])
check("kata pengguna ada di prompt", "belum punya client" in seen["user"])

# 6 — endpoint: 404, 409 without diagnosis, 400 empty question, 200 with diagnosis
import app.main as app_main  # noqa: E402

app_main.get_llm = lambda: MockProvider()  # deterministic: never uses the real provider from .env
c = TestClient(app)
check(
    "endpoint: sesi tidak ada = 404", c.post("/session/none/ask", json={"question": "hai"}).status_code == 404
)
sid = c.post("/session", json={"goal_text": "naik ke 20 juta per bulan", "language": "id"}).json()[
    "session_id"
]
check(
    "endpoint: tanpa diagnosis = 409",
    c.post(f"/session/{sid}/ask", json={"question": "hai"}).status_code == 409,
)
real = store.get(sid)
real.diagnosis = make_session("tmp").diagnosis
store.save(real)
check(
    "endpoint: pertanyaan kosong = 400",
    c.post(f"/session/{sid}/ask", json={"question": "  "}).status_code == 400,
)
check(
    "endpoint: pertanyaan terlalu panjang ditolak",
    c.post(f"/session/{sid}/ask", json={"question": "x" * 700}).status_code == 422,
)
r = c.post(f"/session/{sid}/ask", json={"question": "Apa yang menahan saya?", "history": [], "focus": ""})
check("endpoint: 200 dengan diagnosis", r.status_code == 200 and r.json().get("answer"), r.text[:120])
check(
    "endpoint: riwayat dengan peran asing ditolak",
    c.post(
        f"/session/{sid}/ask", json={"question": "hai", "history": [{"role": "system", "text": "x"}]}
    ).status_code
    == 422,
)
try:
    import os

    os.remove(f"store/sessions/{sid}.json")
except OSError:
    pass

n_ok = sum(1 for _, ok, _ in _results if ok)
print(f"\nHASIL: {n_ok}/{len(_results)} PASS {'✅' if n_ok == len(_results) else '❌'}")
sys.exit(0 if n_ok == len(_results) else 1)
