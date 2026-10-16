"""MC-02 (18 Oct) — context-directed prose candidates ASKED: deterministic unit (mock LLM).

Incident session e1704203f327 (EN, brand designer): narrowing mapper v1 = single-language
token-overlap (EN claim vs Indonesian registry hay). A user answer that DIRECTLY answers
the need the engine asked about (working hours for delivery.spare_capacity) was never
proposed -> second-pass never called for the right rid -> ledger empty ->
`open_askable` frozen ("6 key questions left"), the engine keeps asking the same need until
ASK_CAP runs out, the checkpoint never levels up.

Contract proven here:
  F1  wiring: EN claim (0 mapper overlap) + focus_requirement_ids -> focus proposal ->
      second-pass -> VERIFIED -> adjudicate -> ledger PRESENT; `focused` summary recorded.
  F2  without focus_requirement_ids the era A+B behavior is intact: EN claim stays
      UNRESOLVED, no focus proposal, no ledger entry.
  F3  a focus rid that ALREADY has a verified state (same goal context) is not
      re-proposed (no longer a key question; budget not burned).
  F4  formal / unregistered rid ignored by the focus path (formal path stays single).
  F5  goal-scoping: another goal's state does not clog this goal's context (Probe A).
  F6  verdict none = honest degradation: UNRESOLVED SECOND_PASS_NO_MATCH, no ledger
      entry, no exception (CP-25).
  F7  budget: focus rid <= MAX_FOCUS_REQUIREMENTS; claim candidates <= FOCUS_CANDIDATE_CAP
      and taken from the NEWEST.
  F8  app.navigation.focus_requirement_ids parses planner_log (presented/decision,
      newest first, dedup).

Run: .venv/bin/python evals/test_focus_adjudication.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

import store.adjudication_ledger as ledger  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="focus_adj_"))
ledger._LEDGER_ROOT = _TMP / "ledger"

from core.schema.evidence import EvidenceItem  # noqa: E402
from engine.requirements import load_registry  # noqa: E402
from ontology.mapper import second_pass  # noqa: E402
from ontology.mapper.contract import narrow_candidates  # noqa: E402
from ontology.mapper.live_adjudication import (  # noqa: E402
    FOCUS_CANDIDATE_CAP,
    MAX_FOCUS_REQUIREMENTS,
    PROPOSED_BY_FOCUS,
    formal_envelope,
    run_live_adjudication,
    support_of,
)
from store.requirement_state import LedgerRequirementReader  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


class FakeVerdictLLM:
    """Deterministic LLM verifier (test_second_pass pattern): a script per requirement_id."""

    name = "fake"
    model = "fake-verifier-1"

    def __init__(self, script: dict[str, list[dict[str, Any]]] | None = None):
        self.script = script or {}
        self.calls: list[str] = []

    def structured_call(self, schema, system, user, retries: int = 0):  # noqa: ANN001
        m = re.search(r"^REQUIREMENT (\S+)", user, re.M)
        rid = m.group(1) if m else ""
        self.calls.append(rid)
        return schema.model_validate(
            {"contract_version": "spv.v1", "requirement_id": rid,
             "claim_checks": self.script.get(rid, [])})


def ev(i: str, text: str, *, role: str = "claim", gap: bool = False, admissible: bool = True,
       superseded: bool = False, claim_id: str = "", event_id: str = "") -> EvidenceItem:
    return EvidenceItem(
        id=i, signal=text, source_quote=text, level="self_reported", topic="CLAIM", is_gap=gap,
        claim_role=role, epistemic="reported", admissible=admissible, superseded=superseded,
        claim_id=claim_id, event_id=event_id)


def ledger_rows(user: str) -> list[dict]:
    f = ledger._LEDGER_ROOT / user / "adjudication_ledger.jsonl"
    return ([json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
            if f.exists() else [])


def reader(user: str, goal_id: str | None = None) -> LedgerRequirementReader:
    return LedgerRequirementReader(user, support_of=support_of(), goal_id=goal_id)


# EN claim from the incident session: answers the delivery.spare_capacity need DIRECTLY,
# without a single token overlapping the Indonesian registry hay (proven by F0).
HOURS_EN = "I spend about 20 hours a week on design and client work and only have 3 to 5 spare hours left"
SPARE = "delivery.spare_capacity"

entries = list(load_registry().values())
formal_ids = set(formal_envelope().get("rules") or {})

# ── F0 · incident premise: the narrowing mapper indeed does not reach (reason for the focus path) ──
print("F0 · premis: narrowing mapper satu-bahasa tidak mengusulkan rid path utk klaim EN")
check("F0a klaim EN TIDAK diusulkan mapper ke delivery.spare_capacity (recall 0 — premis insiden)",
      SPARE not in [r for r, _s in narrow_candidates(HOURS_EN, entries)],
      str(narrow_candidates(HOURS_EN, entries)[:5]))
check("F0b delivery.spare_capacity adalah requirement PROSA (bukan formal/unit)",
      SPARE not in formal_ids)

# ── F1 · wiring: focus -> proposal -> second-pass -> adjudicate -> ledger ─────────────────────
print("F1 · wiring focus_requirement_ids end-to-end")
second_pass.clear_cache()
U1 = "u-focus-f1"
facts1 = [ev("e1", HOURS_EN, claim_id="c1", event_id="ev-1")]
llm1 = FakeVerdictLLM({SPARE: [
    {"evidence_ref": "e1", "quote": "only have 3 to 5 spare hours left", "branch": "sufficient",
     "unit_key": None, "basis": "sisa kapasitas waktu mingguan dinyatakan langsung"},
]})
run1 = run_live_adjudication(
    U1, facts1, now=1_700_000_000, llm=llm1,
    goal={"goal_id": "g-f1"}, focus_requirement_ids=[SPARE])
adj1 = {a["requirement_id"]: a for a in run1["adjudicated"]}
check("F1a jawaban EN naik lewat jalur focus: spare_capacity teradjudikasi",
      adj1.get(SPARE, {}).get("status") in ("PRESENT", "PARTIAL"), str(run1["adjudicated"]))
check("F1b ringkasan mencatat rid yang difokuskan (no invisible supplement)",
      run1.get("focused") == [SPARE], str(run1.get("focused")))
check("F1c SPV DIPANGGIL utk rid yang tak pernah diusulkan mapper (wiring focus bekerja)",
      SPARE in llm1.calls and SPARE not in run1["proposed_rids"],
      f"calls={llm1.calls} proposed_rids={run1['proposed_rids']}")
st1 = reader(U1, "g-f1").read(SPARE)
check("F1d ledger tertulis goal-scoped + reader konteks membaca keadaan non-UNKNOWN",
      st1.satisfaction in ("PRESENT", "PARTIAL") and st1.evidence_refs, str(st1))

# ── F2 · without focus: era A+B behavior intact ─────────────────────────────────────────────
print("F2 · tanpa focus_requirement_ids (default) perilaku lama utuh")
second_pass.clear_cache()
U2 = "u-focus-f2"
run2 = run_live_adjudication(U2, [ev("e1", HOURS_EN)], now=1_700_000_100, llm=FakeVerdictLLM())
check("F2a tidak ada proposal focus (ringkasan focused kosong)", not run2.get("focused"))
check("F2b spare_capacity TIDAK teradjudikasi (jalur mapper saja — recall 0 utk EN)",
      not any(a["requirement_id"] == SPARE for a in run2["adjudicated"]))
check("F2c tidak ada entri ledger utk spare_capacity", not ledger_rows(U2))

# ── F3 · a rid that already has a verified state is not re-proposed ──────────────────────────
print("F3 · kebutuhan resolved tidak dibakar ulang")
second_pass.clear_cache()
llm3 = FakeVerdictLLM({SPARE: [
    {"evidence_ref": "e1", "quote": "only have 3 to 5 spare hours left", "branch": "sufficient",
     "unit_key": None, "basis": "idempoten"},
]})
run3 = run_live_adjudication(
    U1, [ev("e1", HOURS_EN)], now=1_700_000_200, llm=llm3,
    goal={"goal_id": "g-f1"}, focus_requirement_ids=[SPARE])
check("F3a spare_capacity PRESENT di konteks g-f1 -> tidak diajukan focus lagi",
      run3.get("focused") != [SPARE] and SPARE not in llm3.calls,
      f"focused={run3.get('focused')} calls={llm3.calls}")

# ── F4 · formal / unregistered rid ignored ───────────────────────────────────────────────────
print("F4 · jalur focus hanya utk prose terdaftar")
second_pass.clear_cache()
formal_sample = sorted(formal_ids)[0]
unknown_rid = "notregistry.zzz"
run4 = run_live_adjudication(
    "u-focus-f4", [ev("e1", HOURS_EN)], now=1_700_000_300, llm=FakeVerdictLLM(),
    focus_requirement_ids=[formal_sample, unknown_rid, SPARE])
check("F4a rid formal & tak terdaftar tidak masuk ringkasan focused",
      set(run4.get("focused") or []) == {SPARE}, str(run4.get("focused")))

# ── F5 · goal-scoping: another goal's state does not clog this context ───────────────────────
print("F5 · scope konteks bisnis (Probe A) dijalur focus")
second_pass.clear_cache()
U5 = "u-focus-f5"
llm5 = FakeVerdictLLM({SPARE: [
    {"evidence_ref": "e1", "quote": "only have 3 to 5 spare hours left", "branch": "sufficient",
     "unit_key": None, "basis": "goal lain"},
]})
run5a = run_live_adjudication(
    U5, [ev("e1", HOURS_EN)], now=1_700_000_400, llm=llm5,
    goal={"goal_id": "g-A"}, focus_requirement_ids=[SPARE])
check("F5a goal A terverifikasi dulu", run5a.get("focused") == [SPARE])
run5b = run_live_adjudication(
    U5, [ev("e1", HOURS_EN)], now=1_700_000_500, llm=FakeVerdictLLM({SPARE: [
        {"evidence_ref": "e1", "quote": "only have 3 to 5 spare hours left", "branch": "sufficient",
         "unit_key": None, "basis": "goal B"},
    ]}), goal={"goal_id": "g-B"}, focus_requirement_ids=[SPARE])
check("F5b goal B (konteks lain, masih UNKNOWN) TETAP diusulkan — tidak terhalang entri goal A",
      run5b.get("focused") == [SPARE], str(run5b.get("focused")))
stB = reader(U5, "g-B").read(SPARE)
check("F5c reader goal B membaca keadaan konteksnya sendiri",
      stB.satisfaction in ("PRESENT", "PARTIAL"), str(stB))

# ── F6 · verdict none = honest degradation ───────────────────────────────────────────────────
print("F6 · verdict none tidak menjatuhkan apa pun")
second_pass.clear_cache()
U6 = "u-focus-f6"
run6 = run_live_adjudication(
    U6, [ev("e1", HOURS_EN)], now=1_700_000_600,
    llm=FakeVerdictLLM({SPARE: [
        {"evidence_ref": "e1", "quote": "about 20 hours", "branch": "none",
         "unit_key": None, "basis": "tidak menyentuh kondisi"},
    ]}), goal={"goal_id": "g-f6"}, focus_requirement_ids=[SPARE])
check("F6a none tercatat UNRESOLVED SECOND_PASS_NO_MATCH tanpa exception",
      run6["unresolved"].get("SECOND_PASS_NO_MATCH", 0) >= 1, str(run6["unresolved"]))
check("F6b tidak ada entri ledger dari verdict none", not any(
    r["adjudication"]["requirement_id"] == SPARE for r in ledger_rows(U6)))
check("F6c kandidat jalur focus ber-label context_focus_v1 saat unresolved (audit)",
      any(c.get("mapping_rule") == PROPOSED_BY_FOCUS and c["requirement_id"] == SPARE
          for c in run6["candidates"]))

# ── F7 · budget & newest candidates ──────────────────────────────────────────────────────────
print("F7 · anggaran jalur focus")
second_pass.clear_cache()
U7 = "u-focus-f7"
many = [ev(f"e{i}", f"old filler claim number {i} about nothing in particular") for i in range(12)]
many.append(ev("e-new", HOURS_EN))
llm7 = FakeVerdictLLM({rid: [] for rid in [
    "delivery.capacity", "commercial.willingness_to_pay", "commercial.willingness_to_pay_at_new_price",
    "conversion.proof", "offering.outcome", "retention.repeat_purchase", SPARE]})
rids7 = [SPARE, "delivery.capacity", "commercial.willingness_to_pay",
         "commercial.willingness_to_pay_at_new_price", "conversion.proof",
         "offering.outcome", "retention.repeat_purchase"]  # 7 rid -> MC-03 cap = 12, all fit
run7 = run_live_adjudication(
    U7, many, now=1_700_000_700, llm=llm7, goal={"goal_id": "g-f7"},
    focus_requirement_ids=rids7)
check("F7a universe <= MAX_FOCUS_REQUIREMENTS dengan rid pertama tetap prioritas",
      len(run7.get("focused") or []) == min(len(rids7), MAX_FOCUS_REQUIREMENTS) and
      (run7.get("focused") or [])[0] == SPARE and set(rids7) <= set(run7.get("focused") or []),
      str(run7.get("focused")))
# first-rid claim candidates = last 8 (e5..e11 + e-new) — verified via the prompt the llm receives
sent_refs = None
orig_call = llm7.structured_call


def spy_call(schema, system, user, retries=0):  # noqa: ANN001
    global sent_refs
    m = re.findall(r"evidence_ref: (e\S+)", user)
    if sent_refs is None:
        sent_refs = m
    return orig_call(schema, system, user, retries=retries)


llm7.structured_call = spy_call
second_pass.clear_cache()
run_live_adjudication(
    U7, many, now=1_700_000_800, llm=llm7, goal={"goal_id": "g-f7"},
    focus_requirement_ids=rids7)
check("F7b kandidat klaim dibatasi FOCUS_CANDIDATE_CAP dan diambil dari TERBARU (e-new masuk)",
      sent_refs is not None and len(sent_refs) <= FOCUS_CANDIDATE_CAP and "e-new" in sent_refs,
      str(sent_refs))

# ── F8 · focus parser from planner_log ───────────────────────────────────────────────────────
print("F8 · app.navigation.focus_requirement_ids")
from app.navigation import focus_requirement_ids  # noqa: E402

log = [
    {"decision": {"reason": {"need_id": "requirement:delivery.spare_capacity"}}},
    {"presented": {"focus": {"id": "requirement:delivery.spare_capacity"},
                   "reason": {"need_id": "requirement:delivery.spare_capacity"}}},
    {"presented": {"focus": {"id": "su-abc"}, "reason": {"need_id": "semantic:su-abc"}}},
    {"presented": {"focus": {"id": "requirement:commercial.willingness_to_pay"}}},
]
got = focus_requirement_ids(log)
check("F8a rid requirement terkumpul terbaru-dulu, semantic/fokus lain dilewati, dedup",
      got == ["commercial.willingness_to_pay", "delivery.spare_capacity"], str(got))
check("F8b log kosong / tanpa requirement -> [] (jalur tidak aktif)",
      focus_requirement_ids([]) == [] and focus_requirement_ids(None) == []
      and focus_requirement_ids([{"presented": {"focus": {"id": "su-x"}}}]) == [])

# ── F9 · MC-03: universe extended to every live-UNKNOWN context requirement ──────────────────
print("F9 · universe konteks: entri terakhir ber-input menambah rid konteks UNKNOWN")


def _req(sat: str, *, navigable: bool = True, app: str = "APPLIES") -> dict:
    return {"satisfaction": sat,
            "contexts": [{"kind": "path", "id": "p1", "navigable": navigable, "applicability": app}]}


log9 = [
    {"presented": {"focus": {"id": "requirement:delivery.spare_capacity"}}},
    {"presented": {"focus": {"id": "su-abc"}, "reason": {"need_id": "semantic:su-abc"}},
     "input": {"requirements": {
         "delivery.spare_capacity": _req("PRESENT"),
         "commercial.willingness_to_pay": _req("UNKNOWN"),
         "retention.repeat_purchase": _req("UNKNOWN", navigable=False),
         "offering.outcome": _req("UNKNOWN", app="UNKNOWN"),
         "conversion.proof": _req("UNKNOWN"),
     }}},
]
got9 = focus_requirement_ids(log9)
check("F9a rid fokus tanya dulu, lalu rid konteks hidup UNKNOWN (path/route navigable+APPLIES) ikut",
      got9 == ["delivery.spare_capacity", "commercial.willingness_to_pay", "conversion.proof"], str(got9))
check("F9b PRESENT dilewati; navigable=false / applicability bukan APPLIES tidak masuk",
      "retention.repeat_purchase" not in got9 and "offering.outcome" not in got9)
log9b = [{"presented": {"focus": {"id": "su-x"}},
          "input": {"requirements": {"delivery.capacity": _req("UNKNOWN")}}}]
check("F9c giliran ber-fokus semantik MURNI tetap mengumpulkan rid konteks (penyebab chip macet iterasi-1)",
      focus_requirement_ids(log9b) == ["delivery.capacity"])

# ── F10/F11 · MC-03 iteration-2/3: candidate selection & mapper-proposed rid ─────────────────
print("F10/F11 · kandidat quantity-first + rid mapper tetap ditambah kandidat fokus")
from ontology.mapper.live_adjudication import _focus_proposals  # noqa: E402

U10 = "u-focus-f10"
g10 = {"nodes": {"c-qty": {"quantity": {"value": 4, "unit": "clients"}}}}
facts10 = [ev("e-qty", "I currently have four active clients", claim_id="c-qty")]
facts10 += [ev(f"e{i}", f"plain narrative filler number {i} without numbers") for i in range(12)]
props10 = _focus_proposals(
    [SPARE], index={e.id: e for e in facts10}, facts=facts10, graph=g10,
    formal_ids=formal_ids, registry_ids=set(load_registry()),
    mapper_refs_by_rid={}, user_id=U10, goal_id=None, now=1)
refs10 = (props10[0]["evidence_refs"] if props10 else [])
check("F10a klaim ber-quantity di AWAL sesi tetap jadi kandidat (bukan hanya N-terakhir)",
      "e-qty" in refs10, str(refs10))
check("F10b kandidat dibatasi FOCUS_CANDIDATE_CAP", len(refs10) <= 16)
props11 = _focus_proposals(
    [SPARE], index={e.id: e for e in facts10}, facts=facts10, graph=g10,
    formal_ids=formal_ids, registry_ids=set(load_registry()),
    mapper_refs_by_rid={SPARE: {"e-qty"}}, user_id=U10, goal_id=None, now=1)
refs11 = (props11[0]["evidence_refs"] if props11 else [])
check("F11a rid yang sudah diusulkan mapper TETAP dapat kandidat fokus tambahan (bukan di-skip)",
      bool(props11) and "e-qty" not in refs11 and refs10 and set(refs11) <= set(refs10),
      f"{refs11[:4]}...")

# ── results ──────────────────────────────────────────────────────────────────────────────────
fails = [r for r in RESULTS if not r[1]]
print(f"\n{'✅' if not fails else '❌'} {len(RESULTS) - len(fails)}/{len(RESULTS)} check lulus")
sys.exit(1 if fails else 0)
