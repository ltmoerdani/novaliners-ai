"""Narrative-contradiction guard against structured Goal + scenario-aware PlainExplain (round 4, Phase 5).

Two things proven, not assumed:
  A. A WRONG provider is rejected before it shows (the stub deliberately writes target/metric/current/relations
     that contradict the structured Goal): one bounded retry, then a deterministic fallback from the Goal -
     an answer known to be wrong never reaches the output. Applies to PlainExplain, TALK (Ask) answers,
     and DiagnosisDraft.
  B. The mock PlainExplain follows the active scenario: it carries no other scenario's facts (formerly: "8 years of
     marketing" and Rp20 juta for everyone).
Deterministic, 0 real LLM. Run: .venv/bin/python evals/test_goal_narrative_guard.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

from agents.ask import ask_session  # noqa: E402
from agents.diagnosis import DiagnosisDraft, _guard_goal_consistency  # noqa: E402
from agents.explain import build_pack, explain_session  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.guards.goal_consistency import (  # noqa: E402
    check_text_goal,
    goal_facts_of,
    goal_line,
    measurement_line,
)
from domains.revenue.schema.ask import AskReply  # noqa: E402
from domains.revenue.schema.goal import build_goal  # noqa: E402
from evals.navigation_fixtures import revenue_artifact  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import Session  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def session(goal: dict, goal_text: str, relation: str | None = None, sid: str = "g1", **rs_kw) -> Session:
    s = Session(id=sid, goal_text=goal_text, language="en")
    s.transcript = [("user", goal_text)]
    s.evidence = [EvidenceItem(id="ev-1", signal="a consulting service for small clinics",
                               level="self_reported", source_quote="clinics", topic="GOAL")]
    s.goal = goal
    s.diagnosis = revenue_artifact(**rs_kw)
    if relation:
        for p in (s.diagnosis.possible_paths or {}).get("paths", []):
            p["goal_relation"] = relation
    return s


LEADS = build_goal("I need three qualified leads in 14 days", measurement_window_days=14,
                   success_definition="qualified = B2B owner who booked a discovery call").model_dump()
RATE = build_goal("Our close rate is about 15%. I want 25% in 60 days.", metric_id="close_rate",
                  target=0.25, measurement_window_days=60).model_dump()
REV = build_goal("grow revenue to Rp60 juta", metric_id="revenue_monthly", target=60.0,
                 deadline_days=90).model_dump()
for g, gid in ((LEADS, "goalA"), (RATE, "goalB"), (REV, "goalR")):
    g["goal_id"] = gid
STATE = dict(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0, capacity_utilization=0.5,
             willingness_to_pay="PRICE_SENSITIVE", avg_deal_size=10.0)


class Stub(MockProvider):
    """Provider that DELIBERATELY errs on the first `bad_calls` invocations, then obeys; counts calls."""

    def __init__(self, mutate, bad_calls: int = 99):
        self.mutate, self.bad_calls, self.calls = mutate, bad_calls, 0

    def structured_call(self, schema, system, user, retries=2):
        self.calls += 1
        r = super().structured_call(schema, system, user)
        if self.calls <= self.bad_calls:
            self.mutate(r)
        return r


def explain(s, mutate, bad_calls=99, ctx=None):
    llm = Stub(mutate, bad_calls)
    out = explain_session(llm, s, goal_ctx=ctx)
    return out, llm


def top_blob(out: dict) -> str:
    """Top-level narrative fields only (the engine's path-item titles may mention 'close rate' etc.)."""
    flat = []
    for k in ("summary", "blocking_title", "blocking_body", "do_title", "do_why", "done_when", "hold_title",
              "hold_body", "why"):
        v = out.get(k)
        flat += v if isinstance(v, list) else [v or ""]
    return " ".join(flat)


def blob(out: dict) -> str:
    parts = [out.get(k) for k in ("summary", "blocking_title", "blocking_body", "do_title", "do_why", "done_when",
                                  "hold_title", "hold_body", "why")]
    flat = [x for p in parts for x in (p if isinstance(p, list) else [p or ""])]
    flat += [str(p.get(f) or "") for p in out.get("paths", []) for f in ("why", "next", "opening", "supported",
                                                                             "holding", "unclear")]
    return " ".join(flat)


# ═══════════════════════════ A. wrong provider rejected ═══════════════════════════
print("== A. PlainExplain: provider yang bertentangan dengan Goal ditolak → retry terbatas → fallback Goal ==")
sL = session(LEADS, "I need three qualified leads in 14 days", relation="UNKNOWN_RELATION", **STATE)

CASES = (
    ("1. target metric berbeda (close rate pada Goal leads)", "FOREIGN_METRIC",
     lambda r: r.summary.__setitem__(0, "Your goal is to raise your close rate to 25 percent.")),
    ("2. current value yang tidak ada (2 leads, belum pernah diukur)", "CURRENT_NOT_MEASURED",
     lambda r: setattr(r, "blocking_body", "You have 2 qualified leads right now.")),
    ("3. target revenue pada Goal leads", "FOREIGN_TARGET",
     lambda r: r.summary.__setitem__(0, "Your target is Rp20 million a month.")),
    ("4. klaim kausal untuk relasi UNKNOWN", "CAUSAL_ON_UNKNOWN_RELATION",
     lambda r: setattr(r, "do_why", "This path will definitely increase your qualified leads.")),
    ("6. achievement diklaim dari aksi DONE", "ACHIEVED_WITHOUT_EVIDENCE",
     lambda r: setattr(r, "hold_body", "You finished every step, so you reached your goal.")),
    ("7. window salah (30 hari, Goal 14 hari)", "WINDOW_MISMATCH",
     lambda r: r.summary.__setitem__(0, "Your goal is 3 qualified leads in 30 days.")),
    ("11. target parsed diklaim dikonfirmasi pengguna", "TARGET_NOT_CONFIRMED",
     lambda r: r.summary.__setitem__(0, "You confirmed your target of 3 qualified leads.")),
)
for name, code, mut in CASES:
    out, llm = explain(sL, mut)
    g = out["guard"]["goal"]
    shown = top_blob(out).lower()
    check(f"{name}: terdeteksi ({code}), retry 1x saja, fallback dari Goal",
          code in g["violations_first_pass"] and llm.calls == 2 and g["retried"] and not g["repaired"]
          and g["fallback_fields"], f"calls={llm.calls} {g['violations_first_pass']}")
    check(f"{name}: teks yang salah TIDAK sampai ke keluaran; fakta Goal yang tampil",
          "close rate" not in shown and "rp20" not in shown and "30 days" not in shown
          and "confirmed your target" not in shown and "will definitely" not in shown
          and "reached your goal" not in shown and "2 qualified leads" not in shown
          and "qualified leads" in shown, shown[:140])

# 5. facts from another Goal/session
other = {"other_goals": [{"goal_id": "goalB", "metric_id": "close_rate", "target": 0.25}]}
out, llm = explain(sL, lambda r: r.summary.__setitem__(0, "Your goal is a close rate of 25 percent."), ctx=other)
check("5. konteks Goal lain di workspace dinyatakan sebagai goal aktif → OTHER_GOAL_CONTEXT, tidak tampil",
      "OTHER_GOAL_CONTEXT" in out["guard"]["goal"]["violations_first_pass"]
      and "close rate" not in top_blob(out).lower())

# 8. a valid answer (obedient mock) passes with no retry and no fallback
out, llm = explain(sL, lambda r: None, bad_calls=0)
check("8. keluaran valid: tidak ada pelanggaran, 1 panggilan, tanpa fallback",
      out["guard"]["goal"]["violations_first_pass"] == [] and llm.calls == 1
      and out["guard"]["goal"]["fallback_fields"] == [], str(out["guard"]["goal"]))

# a retry that succeeds in fixing things = used
out, llm = explain(sL, lambda r: r.summary.__setitem__(0, "Your target is Rp20 million a month."), bad_calls=1)
check("retry yang memperbaiki dipakai: repaired=True, tanpa fallback, teks dari provider tetap",
      out["guard"]["goal"]["repaired"] and out["guard"]["goal"]["fallback_fields"] == [] and llm.calls == 2
      and "rp20" not in top_blob(out).lower())

# 9. schema-invalid output
class BadSchema(MockProvider):
    def structured_call(self, schema, system, user, retries=2):
        raise ValueError("JSON tidak valid / field wajib hilang")


out = explain_session(BadSchema(), sL)
check("9. keluaran gagal skema → penjelasan deterministik dari Goal (tanpa 500, tanpa teks provider)",
      out["model"] == "deterministic-fallback" and "qualified leads" in blob(out).lower()
      and out["guard"]["goal"]["violations_first_pass"] == ["SCHEMA_INVALID"]
      and 1 <= len(out["summary"]) <= 3, blob(out)[:120])

# old target after a revision
revised = dict(LEADS, version=2, target=5.0)
sRev = session(revised, "I need five qualified leads in 14 days", relation="UNKNOWN_RELATION", **STATE)
ctx_rev = {"history": [{"target": 3.0}, {"target": 5.0}]}
out, _ = explain(sRev, lambda r: r.summary.__setitem__(0, "Your goal is 3 qualified leads in 14 days."), ctx=ctx_rev)
check("target LAMA setelah revisi → STALE_TARGET, tidak tampil; target saat ini (5) yang tampil",
      "STALE_TARGET" in out["guard"]["goal"]["violations_first_pass"]
      and "3 leads" not in top_blob(out) and "5 leads" in top_blob(out), top_blob(out)[:140])

# wrong unit/percent on a rate Goal
sR = session(RATE, "Our close rate is about 15%. I want 25% in 60 days.", **STATE)
out, _ = explain(sR, lambda r: r.summary.__setitem__(0, "Your goal is a close rate of 0.25% within 60 days."))
check("7b. konflik unit/persen (0.25% vs 25 percent) → UNIT_CONFLICT, tampil 25 percent",
      "UNIT_CONFLICT" in out["guard"]["goal"]["violations_first_pass"] and "25 percent" in blob(out))

# negative case: HONEST sentences are not rejected (the guard is not a generic prohibition)
honest = ["Your goal is 3 qualified leads within 14 days.",
          "You have no qualified leads measured yet.",
          "You earn Rp30 million a month today. Your goal is 3 qualified leads in 14 days.",
          'You wrote "I want Rp20 million a month" earlier. Your goal on record is 3 qualified leads.',
          "This path might help your goal, but nothing shows yet that it does.",
          "You told us you have 2 qualified leads right now."]
fL = goal_facts_of(LEADS, relations=["UNKNOWN_RELATION"])
check("kalimat jujur (goal sendiri, belum terukur, fakta pendapatan terpisah, kutipan, hedged, atribusi) lolos",
      all(check_text_goal(t, fL) == [] for t in honest),
      str([t for t in honest if check_text_goal(t, fL)]))

# ═══════════════════════════ B. scenario-aware mock ═══════════════════════════
print("== B. PlainExplain mock mengikuti skenario aktif (tanpa fakta skenario lain) ==")
FOREIGN = ("8 years", "marketing manager", "rp20", "one-page service offer", "people do not know exactly")
scen = {
    "leads (belum terukur, target belum dikonfirmasi, relasi UNKNOWN)":
        session(LEADS, "I need three qualified leads in 14 days", relation="UNKNOWN_RELATION", **STATE),
    "close rate": session(RATE, "Our close rate is about 15%. I want 25% in 60 days.", **STATE),
    "revenue": session(REV, "grow revenue to Rp60 juta", relation="DIRECT_CONTRIBUTION", **STATE),
}
texts, tops = {}, {}
for label, sess in scen.items():
    o = explain_session(MockProvider(), sess)
    texts[label] = blob(o).lower()
    tops[label] = top_blob(o).lower()
    check(f"mock [{label}]: tanpa fakta skenario lain, tidak ada field dibuang, guard Goal bersih",
          not any(f in texts[label] for f in FOREIGN) and o["dropped"] == []
          and o["guard"]["goal"]["violations_first_pass"] == [], f"dropped={o['dropped']}")
tl = texts["leads (belum terukur, target belum dikonfirmasi, relasi UNKNOWN)"]
check("mock leads: menyebut metric+target+window sendiri; belum terukur ≠ nol; parsed ≠ konfirmasi; relasi = tes",
      "qualified leads" in tl and "3" in tl and "14 days" in tl and "no measurement of" in tl
      and "not yet confirmed" in tl and ("things to test" in tl or "treat it as something to test" in tl))
check("mock close rate: 25 percent dan 60 days; tidak menyebut leads sebagai goal",
      "25 percent" in tops["close rate"] and "60 days" in tops["close rate"]
      and "qualified leads" not in tops["close rate"])
check("mock revenue: target 60 juta rupiah per bulan; tidak ada klaim relasi 'hipotesis' untuk path",
      "60 million rupiah a month" in tops["revenue"] and "move your" not in tops["revenue"])
check("setiap skenario menghasilkan teks BERBEDA (tidak canned)", len(set(texts.values())) == 3)
check("mock mengutip KATA PENGGUNA sesi ini (fakta dari pack), bukan fakta tetap: 'small clinics' muncul di tiap skenario",
      all("small clinics" in tops[k] for k in tops), str({k: "small clinics" in v for k, v in tops.items()}))

# measured current value stated as measured; honest zero-path
sM = session(LEADS, "I need three qualified leads in 14 days", **STATE)
oM = explain_session(MockProvider(), sM, goal_ctx={"measured_current": 2})
check("mock: current terukur (2) dinyatakan terukur; guard mengizinkan nilai yang cocok pengukuran",
      "measured so far: 2" in blob(oM).lower() and oM["guard"]["goal"]["violations_first_pass"] == [])
from domains.revenue.navigation.paths import build_possible_paths  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402

sRM = session(RATE, "Our close rate is about 15%. I want 25% in 60 days.", **STATE)
oRM = explain_session(MockProvider(), sRM, goal_ctx={"measured_current": 0.3})
check("mock rate terukur 0.3: dituturkan sebagai 30 percent (bukan pecahan mentah), lolos guard angka & Goal",
      "30 percent" in top_blob(oRM) and "0.3" not in top_blob(oRM) and oRM["dropped"] == []
      and oRM["guard"]["goal"]["violations_first_pass"] == [], top_blob(oRM)[:160])
sZ = session(LEADS, "I need three qualified leads in 14 days")
sZ.diagnosis.possible_paths = build_possible_paths(RevenueState(), None, goal=LEADS)
oZ = explain_session(MockProvider(), sZ)
check("mock nol-path: tidak mengarang path; menyatakan belum terbentuk",
      oZ["paths"] == [] and "no path is formed" in blob(oZ).lower())
pack, _ = build_pack(sL)
check("pack membawa blok Goal otoritatif + current belum terukur + relasi path UNKNOWN",
      "ACTIVE GOAL (structured, authoritative" in pack and "NOT MEASURED" in pack
      and "link to your goal: not shown yet" in pack and "NOT SHOWN YET" in pack)

from providers.mock import _mock_for  # noqa: E402

_gb = ("ACTIVE GOAL (structured, authoritative - x):\n- metric: close_rate\n- unit: ratio\n- direction: RATE_OR_RATIO\n"
       "- target: 0.25\n- measurement window: 60 days\n- target confirmed by user: no (parsed, not confirmation)\n")
dm = _mock_for(DiagnosisDraft, _gb)
check("mock DiagnosisDraft rasio: dituturkan 25 percent (bukan '0.25 ratio')",
      "25 percent" in dm["success_metric"] and "0.25 ratio" not in dm["success_metric"], dm["success_metric"])

# ═══════════════════════════ C. TALK answers ═══════════════════════════
print("== C. TALK (Ask): jawaban yang bertentangan dengan Goal sesi ini diganti fakta Goal ==")
class BadAsk(MockProvider):
    def __init__(self, answer: str, bad_calls: int = 99):
        self.answer, self.bad_calls, self.calls = answer, bad_calls, 0

    def structured_call(self, schema, system, user, retries=2):
        self.calls += 1
        r = super().structured_call(schema, system, user)
        if schema is AskReply and self.calls <= self.bad_calls:
            r.answer = self.answer
        return r


sB = session(RATE, "Our close rate is about 15%. I want 25% in 60 days.", sid="g2", **STATE)
llm = BadAsk("Your goal is 3 qualified leads in 14 days.")
res = ask_session(llm, sB, "What is my goal right now?", goal_ctx={
    "other_goals": [{"goal_id": "goalA", "metric_id": "qualified_leads", "target": 3.0}]})
check("TALK pada sesi Goal B memakai Goal A → ditolak (OTHER_GOAL_CONTEXT/FOREIGN), retry 1x, fallback fakta B",
      llm.calls == 2 and res["dropped"] and res["guard"]["goal"]["fallback"]
      and "qualified leads" not in res["answer"].lower() and "25 percent" in res["answer"]
      and "close rate" in res["answer"].lower(), res["answer"][:120])
check("TALK: hanya kode pelanggaran yang dicatat (tanpa teks jawaban)",
      all(isinstance(c, str) and c.isupper() or "_" in c for c in res["guard"]["goal"]["violations_first_pass"])
      and "qualified" not in str(res["guard"]))
llm = BadAsk("Your close rate right now is 18 percent.")
res = ask_session(llm, sB, "How am I doing?")
check("TALK: nilai current yang tidak pernah diukur ditolak (CURRENT_NOT_MEASURED)",
      "CURRENT_NOT_MEASURED" in res["guard"]["goal"]["violations_first_pass"]
      and "18 percent" not in res["answer"] and "no measurement of" in res["answer"])
llm = BadAsk("Your goal is 3 qualified leads in 14 days.", bad_calls=0)
res = ask_session(MockProvider(), sB, "What is my goal right now?")
check("TALK jawaban valid mock: tanpa pelanggaran, tanpa fallback, menyebut close rate sendiri",
      res["guard"]["goal"]["violations_first_pass"] == [] and not res["guard"]["goal"]["fallback"]
      and "close rate" in res["answer"].lower(), res["answer"][:120])
check("TALK mock pada Goal rasio: target dituturkan 25 percent (pack membawa bentuk persen), bukan hanya 0.25",
      "25 percent" in res["answer"], res["answer"][:140])

# ═══════════════════════════ D. DiagnosisDraft ═══════════════════════════
print("== D. DiagnosisDraft: kontradiksi → retry 1x → fallback deterministik dari Goal ==")


def draft(**kw) -> DiagnosisDraft:
    base = dict(where_you_are="What we read so far serves your goal.", primary_constraint="Not enough evidence.",
                primary_constraint_id="NO_FIT", why=["Nothing is measured yet."], next_best_action="Record it.",
                success_metric="3 qualified leads within 14 days", well_know_when="It is measured.",
                pivot_rule="Change the approach, not the goal.", evidence_map={})
    base.update(kw)
    return DiagnosisDraft(**base)


class DraftLLM(MockProvider):
    def __init__(self, first, second=None):
        self.first, self.second, self.calls = first, second, 0

    def structured_call(self, schema, system, user, retries=2):
        self.calls += 1
        return self.first if self.calls == 1 else (self.second or self.first)


bad_d = draft(where_you_are="Your target is Rp20 million a month.",
              why=["You have 2 qualified leads right now."])
llm = DraftLLM(bad_d)
fixed, info = _guard_goal_consistency(llm, "PROMPT", bad_d, LEADS, [])
check("draft salah terus: retry 1x, field yang melanggar diganti dari Goal (bukan teks salah)",
      llm.calls == 1 and info["retried"] and info["fallback_fields"] == ["where_you_are", "why"]
      and "rp20" not in fixed.where_you_are.lower() and "qualified leads" in fixed.where_you_are.lower()
      and "2 qualified leads" not in " ".join(fixed.why), str(info))
llm = DraftLLM(draft())   # the retry call returns an obedient draft
fixed, info = _guard_goal_consistency(llm, "PROMPT", draft(where_you_are="Your target is Rp20 million a month."),
                                      LEADS, [])
check("draft diperbaiki retry: dipakai (repaired), tanpa fallback",
      info["violations_after_repair"] == [] and info["fallback_fields"] == [] and info["retried"]
      and fixed.where_you_are == "What we read so far serves your goal.")
llm = DraftLLM(draft())
fixed, info = _guard_goal_consistency(llm, "PROMPT", draft(), LEADS, [])
check("draft valid: tanpa retry, tanpa perubahan", llm.calls == 0 and info["violations_first_pass"] == [])
rev_d = draft(where_you_are="Right now you earn Rp30 million a month. Your target is Rp60 million a month.")
fixed, info = _guard_goal_consistency(DraftLLM(rev_d), "PROMPT", rev_d, REV, [])
check("revenue: fakta pendapatan + target sendiri tidak ditolak (kompatibilitas revenue)",
      info["violations_first_pass"] == [] and info["fallback_fields"] == [], str(info))

# ═══════════════════════════ E. kelengkapan fallback ═══════════════════════════
fl = goal_facts_of(LEADS)
check("kalimat fallback deterministik: goal + belum terukur + parsed ≠ dikonfirmasi",
      "3 qualified leads" in goal_line(fl).lower().replace(", 3 leads", ", 3 qualified leads")
      or "3 leads" in goal_line(fl)
      and "not yet confirmed" in goal_line(fl) and "no measurement of" in measurement_line(fl))
check("tanpa Goal terstruktur (legacy): guard no-op", check_text_goal("Your target is Rp20 million.",
                                                                       goal_facts_of(None)) == [])

print()
passed = sum(1 for _, ok, _ in _results if ok)
print(f"HASIL: {passed}/{len(_results)} PASS" + (" ✅" if passed == len(_results) else " — GAGAL ❌"))
sys.exit(0 if passed == len(_results) else 1)
