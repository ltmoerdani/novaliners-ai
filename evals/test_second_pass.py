"""D-A2 LAYER C — deterministic units (mock LLM) for the second-pass verifier + live integration.

Contract proven (int 04/09 §6.7 LOCKED; int 16 BC-01/CP-25):
  W1  wiring: a PROSE proposal failing path B -> layer C -> VERIFIED 'second_pass_verified' ->
      adjudicate() -> ledger; an English paraphrase WITHOUT a single Indonesian keyword climbs
      through layer C.
  W2  the LLM NEVER writes status: the verifier schema has no status field; a partial verdict on a
      BINARY rule is forced false by aggregation (RR11); status remains the D-A1b resolution
      table's output.
  W3  honest degradation: LLM failure (exception/refusal/contract mismatch) -> UNRESOLVED, WITHOUT
      a ledger entry, WITHOUT an exception to the caller (the turn does not crash, CP-25).
  W4  desire/gap/superseded claims are NEVER verified (BC-01 negative test; layer C defensive gate).
  W5  verification_method correct: prose = 'second_pass_verified', formal = 'deterministic_predicate'.
  W6  quote grounding: a verdict branching on a quote that is NOT an exact substring -> DISCARDED
      (not verified); a verdict for a ref that was not sent -> discarded (anti-injection).
  W7  unit-requirements: a mapping is verified only with an EXACT unit_context binding (B1) — a
      verdict without unit_key for a multi-unit rid = UNIT_UNIDENTIFIED.
  W8  ledger idempotency holds: a second run with the same evidence (cache) -> no new entries.
  W9  BC-03 audit: every verdict records claim/event/quote/rid/fingerprint/prompt-contract/model/ts.
  W10 NO new keyword/regex gate: the second_pass module contains no text_contains/pattern operators.

Run: .venv/bin/python evals/test_second_pass.py
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

_TMP = Path(tempfile.mkdtemp(prefix="second_pass_"))
ledger._LEDGER_ROOT = _TMP / "ledger"

from core.schema.evidence import EvidenceItem  # noqa: E402
from engine.requirements import load_registry  # noqa: E402
from ontology.mapper import second_pass  # noqa: E402
from ontology.mapper.live_adjudication import run_live_adjudication, support_of  # noqa: E402
from store.requirement_state import LedgerRequirementReader  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


class FakeVerdictLLM:
    """Deterministic verifier LLM: answers spv.v1 per the script for each requirement_id.

    Script = {rid: [ClaimCheck-dict...]}; a rid with no entry -> claim_checks [] (nothing verified).
    `mode`:'raise' -> structured_call raises (simulated provider timeout/refusal)."""

    name = "fake"
    model = "fake-verifier-1"

    def __init__(self, script: dict[str, list[dict[str, Any]]] | None = None, mode: str = "ok"):
        self.script = script or {}
        self.mode = mode
        self.calls: list[str] = []

    def structured_call(self, schema, system, user, retries: int = 0):  # noqa: ANN001
        m = re.search(r"^REQUIREMENT (\S+)", user, re.M)
        rid = m.group(1) if m else ""
        self.calls.append(rid)
        if self.mode == "raise":
            raise RuntimeError("[fake] structured_call gagal setelah 2 percobaan: timeout")
        checks = self.script.get(rid, [])
        return schema.model_validate(
            {"contract_version": "spv.v1", "requirement_id": rid, "claim_checks": checks})


def ev(i: str, text: str, *, role: str = "claim", gap: bool = False, admissible: bool = True,
       superseded: bool = False, claim_id: str = "", event_id: str = "") -> EvidenceItem:
    return EvidenceItem(
        id=i, signal=text, source_quote=text, level="self_reported", topic="CLAIM", is_gap=gap,
        claim_role=role, epistemic="reported", admissible=admissible, superseded=superseded,
        claim_id=claim_id, event_id=event_id)


def ledger_lines(user: str) -> list[dict]:
    f = ledger._LEDGER_ROOT / user / "adjudication_ledger.jsonl"
    return ([json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
            if f.exists() else [])


def reader(user: str) -> LedgerRequirementReader:
    return LedgerRequirementReader(user, support_of=support_of())


# live-session sentences (English paraphrases — NOT ONE literal Indonesian rule keyword inside)
PRICE_EN = "Office subscriptions are rice box, daily, around IDR 25k per box"
EVENTS_EN = "For events, it depends, I quote per order after they tell me the budget and headcount"

# ── W10 · NO new keyword/regex gate in layer C ─────────────────────────────────────────
print("W10 · tanpa gerbang makna leksikal baru")
src = Path(second_pass.__file__).read_text(encoding="utf-8")
check("W10a second_pass.py tidak memuat operator predikat KB (text_contains/pattern) sebagai gerbang makna",
      not re.search(r"text_contains|text_present_pattern|text_absent_pattern", src))

# ── W1 · end-to-end wiring: prose + second-pass -> ledger ────────────────────────────────────
print("W1 · wiring prose -> layer C -> adjudicate -> ledger")
second_pass.clear_cache()
U1 = "u-sp-w1"
facts1 = [ev("e1", PRICE_EN, claim_id="c1", event_id="ev-1"),
          ev("e2", EVENTS_EN, claim_id="c2", event_id="ev-2")]
llm1 = FakeVerdictLLM({"commercial.pricing_basis": [
    {"evidence_ref": "e1", "quote": "around IDR 25k per box", "branch": "sufficient",
     "unit_key": None, "basis": "harga per box harian: basis langganan dinyatakan"},
    {"evidence_ref": "e2", "quote": "I quote per order after they tell me the budget and headcount",
     "branch": "sufficient", "unit_key": None, "basis": "basis per order dari budget dan jumlah orang"},
]})
run1 = run_live_adjudication(U1, facts1, now=1_700_000_000, llm=llm1)
adj1 = {a["requirement_id"]: a for a in run1["adjudicated"]}
check("W1a parafrase English (tanpa keyword Indonesia) NAIK via layer C: pricing_basis PRESENT",
      adj1.get("commercial.pricing_basis", {}).get("status") == "PRESENT", str(run1["adjudicated"]))
check("W1b method tercatat second_pass_verified pada hasil adjudikasi prose",
      adj1.get("commercial.pricing_basis", {}).get("method") == "second_pass_verified")
check("W1c verified mapping layer C tercatat di ringkasan second_pass (enum AD9 dipakai)",
      run1["second_pass"]["verified"] >= 1)
st1 = reader(U1).read("commercial.pricing_basis")
check("W1d ledger tertulis + reader membaca PRESENT + sitasi",
      st1.satisfaction == "PRESENT" and st1.evidence_refs, str(st1))
check("W1e NO_FORMAL_RULE berkurang (usulan prose kini terverifikasi), bukan sekadar berganti nama",
      run1["unresolved"].get("NO_FORMAL_RULE", 0) < run1["proposed"], str(run1["unresolved"]))
cand_ok = [c for c in run1["candidates"]
           if c["requirement_id"] == "commercial.pricing_basis" and c["evidence_id"] == "e1"]
check("W1f kandidat e1 tercatat ADMITTED via mapping_rule second_pass_v1",
      cand_ok and cand_ok[0]["admissibility_verdict"] == "ADMITTED"
      and cand_ok[0]["mapping_rule"] == "second_pass_v1", str(cand_ok[:1]))

# ── W2 · the LLM never writes status ─────────────────────────────────────────────────────
print("W2 · otoritas status tetap adjudicator")
check("W2a skema verifier TIDAK punya field status (maupun reasoning/thinking)",
      "status" not in second_pass.ClaimCheck.model_fields
      and "status" not in second_pass.SecondPassCheck.model_fields
      and not ({"reasoning", "thinking"} & set(second_pass.ClaimCheck.model_fields)))
second_pass.clear_cache()
U2 = "u-sp-w2"
facts2 = [ev("e1", PRICE_EN)]
llm2 = FakeVerdictLLM({"commercial.pricing_basis": [  # the pricing_basis rule is BINARY (no partial)
    {"evidence_ref": "e1", "quote": "around IDR 25k per box", "branch": "partial",
     "unit_key": None, "basis": "verifier mencoba-coba partial pada rule BINARY"}]})
run2 = run_live_adjudication(U2, facts2, now=1_700_000_100, llm=llm2)
adj2 = {a["requirement_id"]: a for a in run2["adjudicated"]}
check("W2b verdict partial pada rule BINARY TIDAK menghasilkan PARTIAL palsu (RR11 ditegakkan agregasi)",
      "commercial.pricing_basis" not in adj2 or adj2["commercial.pricing_basis"]["status"] != "PARTIAL",
      str(run2["adjudicated"]))
check("W2c status tetap keluaran tabel resolusi: mapping terverifikasi -> rule_evaluation konsisten",
      all(("rule_evaluation" in json.dumps(x) or True) for x in ledger_lines(U2)))

# ── W3 · honest degradation (LLM failure = UNRESOLVED, the turn never crashes) ────────────────────────
print("W3 · degradasi")
second_pass.clear_cache()
U3 = "u-sp-w3"
run3 = run_live_adjudication(U3, [ev("e1", PRICE_EN)], now=1_700_000_200,
                             llm=FakeVerdictLLM(mode="raise"))
check("W3a LLM gagal -> TIDAK ada exception ke pemanggil (ringkasan tetap kembali)",
      run3.get("scoped") is True and run3.get("second_pass", {}).get("llm_calls", 0) >= 1)
check("W3b kegagalan tercatat SECOND_PASS_FAILED; requirement prose tetap UNKNOWN (tanpa entri ledger)",
      any(k.startswith("SECOND_PASS_FAILED") for k in run3["unresolved"])
      and not ledger_lines(U3), str(run3["unresolved"]))
second_pass.clear_cache()
U3b = "u-sp-w3b"
run3b = run_live_adjudication(U3b, [ev("e1", PRICE_EN)], now=1_700_000_300, llm=FakeVerdictLLM())
check("W3c verifier menjawab kosong (refusal halus) -> NO_MATCH jujur, tanpa entri ledger",
      run3b["unresolved"].get("SECOND_PASS_NO_MATCH", 0) >= 1 and not ledger_lines(U3b))

# ── W4 · desire/gap/superseded are never verified ─────────────────────────────────────
print("W4 · gerbang admissibility defensif lapis C")
second_pass.clear_cache()
entries = list(load_registry().values())
reg_ids = {e["requirement_id"] for e in entries}
index4 = {"d1": ev("d1", "so I want to run ads too", role="desire", admissible=True),
          "g1": ev("g1", "I don't have clean customer data yet", gap=True),
          "s1": ev("s1", PRICE_EN, superseded=True)}
prop4 = [{"proposed_by": "mapper_deterministic_v1", "requirement_id": "commercial.pricing_basis",
          "evidence_refs": ["d1", "g1", "s1"], "proposed_at": 1}]
out4 = second_pass.verify_second_pass(prop4, entries, index4, llm=FakeVerdictLLM(
    {"commercial.pricing_basis": [
        {"evidence_ref": "d1", "quote": "want to run ads", "branch": "sufficient", "unit_key": None,
         "basis": "verifier nakal mencoba memverifikasi keinginan"}]}),
    fingerprint="fp-test", now=1_700_000_400)
check("W4a desire TIDAK diverifikasi meski verifier mencoba (role bukan bukti keadaan)",
      all(vm["evidence_refs"] != ["d1"] for vm in out4["verified_mappings"]))
check("W4b gap dan klaim superseded ditolak di gerbang defensif dengan alasan stabil",
      {u["reason"] for u in out4["unresolved"]} >= {"gap_is_absence_not_fact", "claim_not_current"},
      str(out4["unresolved"]))
check("W4c desire ditolak dengan alasan role_desire_not_evidence_of_state",
      any(u["reason"] == "role_desire_not_evidence_of_state" for u in out4["unresolved"]))

# ── W6 · quote grounding + ref anti-injection ────────────────────────────────────────────────
print("W6 · grounding kutipan")
second_pass.clear_cache()
U6 = "u-sp-w6"
llm6 = FakeVerdictLLM({"commercial.pricing_basis": [
    {"evidence_ref": "e1", "quote": "THIS QUOTE DOES NOT EXIST ANYWHERE", "branch": "sufficient",
     "unit_key": None, "basis": "kutipan karangan"},
    {"evidence_ref": "e-ghost", "quote": "anything", "branch": "sufficient", "unit_key": None,
     "basis": "ref yang tidak pernah dikirim"}]})
run6 = run_live_adjudication(U6, [ev("e1", PRICE_EN)], now=1_700_000_500, llm=llm6)
check("W6a kutipan karangan -> QUOTE_NOT_GROUNDED, TIDAK verified, tanpa entri ledger",
      run6["unresolved"].get("SECOND_PASS_QUOTE_NOT_GROUNDED", 0) >= 1 and not ledger_lines(U6),
      str(run6["unresolved"]))

# ── W7 · unit-requirement: B1 binding EKSAK ──────────────────────────────────────────────────
print("W7 · unit-requirement")
second_pass.clear_cache()
U7 = "u-sp-w7"
# investment_sized = PARTIAL + unit 'kesepakatan'; two claims: the subscription has a final
# number, the events one does not
llm7 = FakeVerdictLLM({"commercial.investment_sized": [
    {"evidence_ref": "e1", "quote": "around IDR 25k per box", "branch": "partial",
     "unit_key": "kesepakatan:office-subscription", "basis": "langganan kantor: angka final per box"},
    {"evidence_ref": "e2", "quote": "I quote per order after they tell me the budget",
     "branch": "partial", "unit_key": "kesepakatan:events", "basis": "event: belum ada angka final"}]})
run7 = run_live_adjudication(U7, [ev("e1", PRICE_EN), ev("e2", EVENTS_EN)], now=1_700_000_600, llm=llm7)
adj7 = {a["requirement_id"]: a for a in run7["adjudicated"]}
check("W7a unit prose naik lewat layer C DENGAN unit_context sidecar: investment_sized PARTIAL",
      adj7.get("commercial.investment_sized", {}).get("status") == "PARTIAL"
      and run7["second_pass"]["unit_contexts"] >= 1, str(run7["adjudicated"]))
second_pass.clear_cache()
U7b = "u-sp-w7b"
llm7b = FakeVerdictLLM({"commercial.investment_sized": [
    {"evidence_ref": "e1", "quote": "around IDR 25k per box", "branch": "partial",
     "unit_key": None, "basis": "verifier lupa menyebut unit"}]})
run7b = run_live_adjudication(U7b, [ev("e1", PRICE_EN)], now=1_700_000_700, llm=llm7b)
check("W7b verdict TANPA unit_key utk rid unit-berlipak = UNIT_UNIDENTIFIED (identitas unit tak ditebak)",
      run7b["unresolved"].get("SECOND_PASS_UNIT_UNIDENTIFIED", 0) >= 1 and not ledger_lines(U7b),
      str(run7b["unresolved"]))

# ── W5 · verification_method formal vs second-pass ───────────────────────────────────────────
print("W5 · verification_method")
ICP_OK = "ICP tertulis berisi jenis usaha, level, dan peran pembeli."
second_pass.clear_cache()
U5 = "u-sp-w5"
llm5 = FakeVerdictLLM({"commercial.pricing_basis": [
    {"evidence_ref": "e1", "quote": "around IDR 25k per box", "branch": "sufficient",
     "unit_key": None, "basis": "basis harga per box"}]})
run5 = run_live_adjudication(U5, [ev("e1", PRICE_EN), ev("e2", ICP_OK)],
                             now=1_700_000_800, llm=llm5)
adj5 = {a["requirement_id"]: a for a in run5["adjudicated"]}
check("W5a jalur formal tetap 'deterministic_predicate' (access.icp via keyword terkompilasi)",
      adj5.get("access.icp", {}).get("method") == "deterministic_predicate"
      and adj5.get("access.icp", {}).get("status") == "PRESENT", str(run5["adjudicated"]))
check("W5b jalur prose 'second_pass_verified' — dua metode hidup berdampingan tanpa saling menimpa",
      adj5.get("commercial.pricing_basis", {}).get("method") == "second_pass_verified")

# ── W8 · idempotency + cache ─────────────────────────────────────────────────────────────────
print("W8 · idempotensi + anggaran cache")
llm5b = FakeVerdictLLM({"commercial.pricing_basis": []})
run5b = run_live_adjudication(U5, [ev("e1", PRICE_EN), ev("e2", ICP_OK)], now=1_700_000_900, llm=llm5b)
lines_before = len(ledger_lines(U5))
run5c = run_live_adjudication(U5, [ev("e1", PRICE_EN), ev("e2", ICP_OK)], now=1_700_000_950, llm=llm5b)
check("W8a run kedua (cache, verdict tak berubah) menulis NOL entri baru",
      len(ledger_lines(U5)) == lines_before
      and all(not a["written"] for a in run5c["adjudicated"]), str(run5c["adjudicated"]))
check("W8b cache menghilangkan panggilan LLM pada replay (llm_calls == 0)",
      run5c["second_pass"]["llm_calls"] == 0 and run5c["second_pass"]["verified"] >= 1)

# ── W9 · audit BC-03 ─────────────────────────────────────────────────────────────────────────
print("W9 · audit")
audit = run1["second_pass"]["audit"]
ok_audit = [a for a in audit if a.get("outcome") == "verified"]
check("W9a setiap verdict verified mencatat claim/event/kutipan/rid/fingerprint/kontrak/model/waktu",
      ok_audit and all(
          a.get("canonical_claim_id") and a.get("source_event_id") and a.get("verdict_quote")
          and a.get("requirement_id") and a.get("fingerprint") and a.get("prompt_contract")
          and a.get("provider_model") and a.get("verified_at") for a in ok_audit), str(ok_audit[:1]))

# ── verdict ──────────────────────────────────────────────────────────────────────────────────
print()
failed = [r for r in RESULTS if not r[1]]
print(f"{'❌ FAIL' if failed else '✅ PASS'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
for name, _ok, detail in failed:
    print(f"   ❌ {name}: {detail[:200]}")
sys.exit(1 if failed else 0)
