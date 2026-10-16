"""REPLAY GATE (BC-01 layer C) — live session 81e431c5e952 via the ORIGINAL adjudication path.

Not a manual state edit: loads the session evidence from the store, runs run_live_adjudication with a
scripted verifier (deterministic; verdict principle = what a careful verifier says about the QUOTES,
not what we wish had been achieved), then checks the ledger + negative tests.

Per-requirement verdict (quote-based, bilingual):
  commercial.pricing_basis (BINARY):
    e011 "Office subscriptions are rice box, daily, around IDR 25k per box" -> sufficient
         (price + basis: a daily per-box subscription — the official WS2 assignment example)
    e018 "daily rice box subscription, IDR 25k per box, Monday to Friday" -> sufficient
    e014 "I quote per order after they tell me the budget and headcount"  -> sufficient
         (a per-order basis stated together with its reasoning: budget + headcount)
    e016 "per customer, I figure it out per customer"                     -> none  (hesitant -> none)
    e020 "about IDR 2.5 million per person per month"                     -> none  (a number without a
         clearly stated pricing rationale; rule 5: hesitant -> none)
    e022 "Minimum is usually 20 boxes per office"                         -> none  (a minimum order,
         not a pricing basis)
    => PRESENT
  commercial.unit_economics (BINARY): ALL none — no quote at all mentions acquisition/service costs;
    a sufficient conjunction is impossible, and contradicting would be groundless too.
    => stays UNKNOWN (HONEST; see the notes below)
  commercial.willingness_to_pay: e014 none (a prospective client's budget, not real money committed)
  conversion.teaching_insight: e016 none ("I figure it out" is not a customer-burden insight)
  delivery.response_system: e015 none (a delivery schedule, not a log/template/follow-up schedule)
  delivery.strategic_objective_defined: e002 none (CURRENT revenue, not a measurable direction/target)
  commercial.investment_sized (PARTIAL, unit 'deal'):
    e011 -> partial, kesepakatan:office-subscription (final per-box number ready to propose)
    e018 -> partial, kesepakatan:office-subscription
    e014 -> partial, kesepakatan:events (proven NOT to have a final number yet: quote awaits budget)
    => PARTIAL
  conversion.commitment_obtained / experiment.test_card_defined: [] (no commitment quote /
    defined hypothesis) => UNKNOWN

HONEST NOTES (reported, not hidden):
  - unit_economics & strategic_objective_defined do NOT rise in this replay even though they were
    named as the task's minimal expectations. Root cause: (a) unit_economics — the session evidence
    genuinely contains no acquisition/service costs; forcing PRESENT = fabrication (forbidden by
    instruction 3 & example 4). (b) strategic_objective_defined — the goal claim "I want to grow to
    IDR 25 million within 2 months" (ev-goal-004) IS in State and would satisfy the partial branch,
    but the deterministic proposer NEVER proposes it (Indonesian vs English-quote token overlap = a
    known recall limit, root cause #3 of the diagnosis; fixing it with keywords/synonyms = RC-06
    FORBIDDEN).
  - access.icp & offering.differentiation STAY UNKNOWN — mandatory negative tests (the user genuinely
    does not have them; neither the formal gate nor layer C may invent them).

Run: .venv/bin/python evals/replay_second_pass_session.py
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

_TMP = Path(tempfile.mkdtemp(prefix="replay_sp_"))
ledger._LEDGER_ROOT = _TMP / "ledger"

from core.schema.evidence import EvidenceItem  # noqa: E402
from ontology.mapper.live_adjudication import run_live_adjudication, support_of  # noqa: E402
from store.requirement_state import LedgerRequirementReader  # noqa: E402

SESSION = Path(__file__).resolve().parents[1] / "store" / "sessions" / "81e431c5e952.json"
USER = "u-replay-81e431c5e952"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


class ScriptedVerifier:
    """Deterministic spv.v1 verifier — quote-by-quote careful verdicts (see the module docstring)."""

    name = "scripted"
    model = "replay-verifier-1"

    SCRIPT: dict[str, list[dict[str, Any]]] = {
        "commercial.pricing_basis": [
            {"evidence_ref": "ev-claim-011", "quote": "around IDR 25k per box", "branch": "sufficient",
             "unit_key": None, "basis": "harga per box harian: basis langganan + rasionalnya dinyatakan"},
            {"evidence_ref": "ev-claim-018", "quote": "IDR 25k per box, Monday to Friday",
             "branch": "sufficient", "unit_key": None, "basis": "langganan harian dengan harga per box"},
            {"evidence_ref": "ev-claim-014",
             "quote": "I quote per order after they tell me the budget and headcount",
             "branch": "sufficient", "unit_key": None,
             "basis": "basis per order: budget dan jumlah orang, alasannya dinyatakan"},
            {"evidence_ref": "ev-claim-016", "quote": "per customer, I figure it out per customer",
             "branch": "none", "unit_key": None, "basis": "belum menyatakan basis; ragu -> none"},
            {"evidence_ref": "ev-claim-020", "quote": "about IDR 2.5 million per person per month",
             "branch": "none", "unit_key": None, "basis": "angka saja; rasional penetapan tidak cukup"},
            {"evidence_ref": "ev-claim-022", "quote": "Minimum is usually 20 boxes per office",
             "branch": "none", "unit_key": None, "basis": "minimum order, bukan basis harga"},
        ],
        "commercial.unit_economics": [],   # honest: no cost data in this session
        "commercial.willingness_to_pay": [
            {"evidence_ref": "ev-claim-014",
             "quote": "I quote per order after they tell me the budget and headcount",
             "branch": "none", "unit_key": None, "basis": "budget calon klien bukan komitmen uang nyata"},
        ],
        "conversion.teaching_insight": [
            {"evidence_ref": "ev-claim-016", "quote": "per customer, I figure it out per customer",
             "branch": "none", "unit_key": None, "basis": "bukan insight beban customer"},
        ],
        "delivery.response_system": [
            {"evidence_ref": "ev-claim-015", "quote": "Delivery days follow the office schedule",
             "branch": "none", "unit_key": None, "basis": "jadwal pengiriman, bukan sistem follow-up"},
        ],
        "delivery.strategic_objective_defined": [
            {"evidence_ref": "ev-claim-002", "quote": "revenue is about IDR 12 million/month",
             "branch": "none", "unit_key": None, "basis": "pendapatan saat ini, bukan arah terukur"},
        ],
        "commercial.investment_sized": [
            {"evidence_ref": "ev-claim-011", "quote": "around IDR 25k per box", "branch": "partial",
             "unit_key": "kesepakatan:office-subscription",
             "basis": "langganan kantor: angka final per box siap diajukan"},
            {"evidence_ref": "ev-claim-018", "quote": "IDR 25k per box", "branch": "partial",
             "unit_key": "kesepakatan:office-subscription", "basis": "harga final langganan"},
            {"evidence_ref": "ev-claim-014",
             "quote": "I quote per order after they tell me the budget and headcount",
             "branch": "partial", "unit_key": "kesepakatan:events",
             "basis": "event: terbukti belum ada angka final (menunggu budget)"},
        ],
        "conversion.commitment_obtained": [],
        "experiment.test_card_defined": [],
    }

    def __init__(self) -> None:
        self.calls: list[str] = []

    def structured_call(self, schema, system, user, retries: int = 0):  # noqa: ANN001
        m = re.search(r"^REQUIREMENT (\S+)", user, re.M)
        rid = m.group(1) if m else ""
        self.calls.append(rid)
        return schema.model_validate(
            {"contract_version": "spv.v1", "requirement_id": rid,
             "claim_checks": self.SCRIPT.get(rid, [])})


def main() -> int:
    data = json.loads(SESSION.read_text(encoding="utf-8"))
    evidence = [EvidenceItem(**e) for e in data["evidence"]]
    before = {}
    print(f"replay sesi {SESSION.name}: {len(evidence)} evidence, user {USER}")

    verifier = ScriptedVerifier()
    summary = run_live_adjudication(USER, evidence, goal=data.get("goal"), session_id=SESSION.stem,
                                    graph=data.get("state_graph"), llm=verifier, now=1_700_100_000)

    print("\nhasil gate:")
    check("G1 verified > 0 (layer C hidup pada sesi nyata)",
          summary["verified"] > 0, f"verified={summary['verified']}")
    check("G2 ledger TERTULIS untuk requirement prose (via adjudicate_and_persist)",
          bool(ledger.latest_entry(USER, "commercial.pricing_basis"))
          and bool(ledger.latest_entry(USER, "commercial.investment_sized")))
    reader = LedgerRequirementReader(USER, support_of=support_of())

    def status_of(rid: str) -> str:
        st = reader.read(rid)
        return st.satisfaction or "UNKNOWN"

    adj = {a["requirement_id"]: a for a in summary["adjudicated"]}
    check("G3 commercial.pricing_basis naik UNKNOWN -> PRESENT (parafrase English, 0 keyword ID)",
          status_of("commercial.pricing_basis") == "PRESENT"
          and adj.get("commercial.pricing_basis", {}).get("method") == "second_pass_verified",
          status_of("commercial.pricing_basis"))
    check("G4 commercial.investment_sized naik UNKNOWN -> PARTIAL (unit_context sidecar B1 via layer C)",
          status_of("commercial.investment_sized") == "PARTIAL"
          and summary["second_pass"]["unit_contexts"] >= 1, status_of("commercial.investment_sized"))
    check("G5 NEGATIVE access.icp tetap UNKNOWN (tanpa entri ledger — user memang tidak memilikinya)",
          ledger.latest_entry(USER, "access.icp") is None)
    check("G6 NEGATIVE offering.differentiation tetap UNKNOWN (tanpa entri ledger)",
          ledger.latest_entry(USER, "offering.differentiation") is None)
    check("G7 NEGATIVE desire 'so I want to run ads too' tidak pernah diverifikasi (BC-01)",
          not any(c["canonical_claim_id"] and c["requirement_id"] for c in summary["candidates"]
                  if c["admissibility_verdict"] == "ADMITTED" and c["semantic_role"] == "desire"))
    check("G8 NEGATIVE gap (4 buah) tetap di 'Still to learn', tak memenuhi requirement apa pun",
          all(c["admissibility_verdict"] != "ADMITTED" for c in summary["candidates"]
              if c["semantic_role"] == "gap" or c["reason"] == "gap_is_absence_not_fact"))

    # idempotency: the second (cached) replay writes no new entries
    lines_before = len(list((_TMP / "ledger" / USER / "adjudication_ledger.jsonl").read_text().splitlines()))
    verifier2 = ScriptedVerifier()
    summary2 = run_live_adjudication(USER, evidence, goal=data.get("goal"), session_id=SESSION.stem,
                                     graph=data.get("state_graph"), llm=verifier2, now=1_700_200_000)
    lines_after = len(list((_TMP / "ledger" / USER / "adjudication_ledger.jsonl").read_text().splitlines()))
    check("G9 idempotensi: replay kedua 0 entri baru + 0 panggilan LLM (cache)",
          lines_before == lines_after and summary2["second_pass"]["llm_calls"] == 0)

    # before/after report table
    print("\ntabel requirement (sebelum -> sesudah replay):")
    watch = ["commercial.pricing_basis", "commercial.investment_sized", "commercial.unit_economics",
             "delivery.strategic_objective_defined", "access.icp", "offering.differentiation"]
    for rid in watch:
        was = before.get(rid, "UNKNOWN")
        note = "   (honest: bukti tak cukup / tak pernah diusulkan)" if status_of(rid) == "UNKNOWN" else ""
        print(f"  {rid:42} {was} -> {status_of(rid)}{note}")

    print(f"\nunresolved akhir: {summary['unresolved']}")
    print(f"adjudicated: {[(a['requirement_id'], a['status'], a['method']) for a in summary['adjudicated']]}")

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{'❌ FAIL' if failed else '✅ PASS'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
    for name, _ok, detail in failed:
        print(f"   ❌ {name}: {detail[:200]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
