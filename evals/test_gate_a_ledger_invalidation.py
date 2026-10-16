"""Gate A (A1) — deterministic regression: PROSE requirement ledger invalidation after supersession.

Root cause (external audit 15 Oct, P0): the old invalidation only swept
`formal_ids | sp_evaluations(this run)` — prose requirements that had EVER been
adjudicated (e.g. PRESENT via second-pass) then lost ALL proposals because their evidence
was superseded but never revisited -> old status persisted (stale PRESENT).

Contract under test (Gate A owner decision):
  S1  evidence replaced, NO replacement  -> new UNKNOWN entry (not stale PRESENT); history append-only.
  S2  evidence replaced, active evidence REMAINS -> normal re-adjudication: PRESENT with refs to active
      evidence (does NOT automatically drop to UNKNOWN).
  S3  cross-user isolation: user B's ledger untouched by user A's invalidation.
  S4  invalidation needs NO LLM (ledger enumeration, not the verifier path).
  S5  partial correction + provider UNAVAILABLE -> evidence verified on the previous run is NOT
      lost: the last entry stands, no new entry (verification temporarily unavailable
      != evidence no longer valid). Provider returns -> normal re-adjudication of active refs only.
  S6  partial correction + provider FAILS (timeout) -> honest degradation (SECOND_PASS_FAILED recorded),
      active evidence still stands; a provider failure is not a verdict.
  S7  fix bound: active evidence DEFINITIVELY rejected by the verifier (branch=none -> NO_MATCH) still
      recomputes to UNKNOWN — the fix does not over-preserve, does not revive superseded claims.

Scripted second-pass provider (principled, exact grounded quotes) — fully deterministic, 0 quota.
Fixture pattern: override `ledger._LEDGER_ROOT` to tmp (test_second_pass pattern, non-destructive).
"""
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

import store.adjudication_ledger as ledger  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="gate_a_inval_"))
ledger._LEDGER_ROOT = _TMP / "ledger"

from core.schema.evidence import EvidenceItem  # noqa: E402
from engine.requirements import load_registry  # noqa: E402
from ontology.mapper import second_pass  # noqa: E402
from ontology.mapper.live_adjudication import run_live_adjudication  # noqa: E402
from ontology.mapper.second_pass import ClaimCheck  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), str(detail)[:160]))
    print(("  ✅ " if ok else "  ❌ ") + name + (f" :: {detail}" if detail and not ok else ""))


def _ev(eid: str, cid: str, quote: str) -> EvidenceItem:
    return EvidenceItem(
        id=eid, signal=quote, level="self_reported", source_quote=quote, topic="CLAIM",
        claim_id=cid, event_id=f"ce-{cid}", claim_role="claim", epistemic="reported", admissible=True)


class ScriptedSP:
    """Scripted second-pass verifier: every candidate -> sufficient with an exact substring quote."""

    name = "scripted"
    model = "sp-gate-a"

    def structured_call(self, schema, system, prompt, **kw):  # noqa: ANN001
        rid = re.search(r"^REQUIREMENT (\S+)", prompt, re.M).group(1)
        checks = []
        for block in prompt.split("- evidence_ref: ")[1:]:
            ref = block.split()[0]
            m = re.search(r'quote: "([^"]+)"', block)
            checks.append(ClaimCheck(
                evidence_ref=ref, quote=(m.group(1) if m else "")[:25],
                branch="sufficient", unit_key=None, basis="scripted"))
        return NS(contract_version="spv.v1", requirement_id=rid, claim_checks=checks)


class FailingSP:
    """Second-pass provider that fails (timeout) — honest degradation, not a verdict."""

    name = "failing"
    model = "sp-fail"

    def structured_call(self, schema, system, prompt, **kw):  # noqa: ANN001
        raise TimeoutError("provider down")


class NoMatchSP:
    """Healthy second-pass provider that rejects every claim (branch=none) — DEFINITIVE verdict."""

    name = "nomatch"
    model = "sp-nomatch"

    def structured_call(self, schema, system, prompt, **kw):  # noqa: ANN001
        rid = re.search(r"^REQUIREMENT (\S+)", prompt, re.M).group(1)
        checks = []
        for block in prompt.split("- evidence_ref: ")[1:]:
            ref = block.split()[0]
            checks.append(ClaimCheck(
                evidence_ref=ref, quote="", branch="none", unit_key=None, basis="no"))
        return NS(contract_version="spv.v1", requirement_id=rid, claim_checks=checks)


Q1 = "Office subscriptions are rice box, daily, around IDR 25k per box"
Q2 = "about IDR 2.5 million per person per month"
RID = "commercial.pricing_basis"


def _graph(*claims: tuple[str, str]) -> dict:
    return {"nodes": {cid: {"type": "claim", "status": "active", "quantity": None,
                            "aspect": "", "tense": "now"} for cid, _q in claims}}


def _run(user: str, evidence, graph, llm):
    second_pass.clear_cache()
    return run_live_adjudication(user, list(evidence), session_id="gate-a", graph=graph, llm=llm)


def _rid_lines(user: str) -> list[str]:
    """Ledger lines carrying the target rid (per-rid entry identification, append-only)."""
    f = ledger._LEDGER_ROOT / user / "adjudication_ledger.jsonl"
    return [ln for ln in f.read_text().splitlines() if f'"{RID}"' in ln]


def main() -> int:
    user_a, user_b = "u-gatea-a", "u-gatea-b"

    print("S1 · P0: koreksi tanpa pengganti -> INVALID (repro audit)")
    ev1 = _ev("ev-a1", "cl-a1", Q1)
    graph = _graph(("cl-a1", Q1))
    r1 = _run(user_a, [ev1], graph, ScriptedSP())
    e1 = ledger.latest_entry(user_a, RID)
    check("S1a giliran awal: terverifikasi PRESENT via second-pass",
          r1["verified"] > 0 and e1["adjudication"]["status"] == "PRESENT",
          (r1["verified"], e1 and e1["adjudication"]["status"]))
    ev1.superseded = True  # user corrects; claim replaced; NO replacement
    r2 = _run(user_a, [ev1], graph, None)  # NO LLM (S4 merged: invalidation must not need a provider)
    e2 = ledger.latest_entry(user_a, RID)
    inv_hit = any(i["requirement_id"] == RID for i in r2["invalidated"])
    check("S1b pasca-koreksi: invalidated tercatat", inv_hit, r2["invalidated"])
    check("S1c ledger turun ke UNKNOWN (bukan stale PRESENT)",
          e2["adjudication"]["status"] == "UNKNOWN", e2["adjudication"]["status"])
    lines = (ledger._LEDGER_ROOT / user_a / "adjudication_ledger.jsonl").read_text().splitlines()
    rid_lines = [ln for ln in lines if f'"{RID}"' in ln]
    check("S1d sejarah append-only utuh (entri lama tidak ditimpa)",
          len(rid_lines) >= 2 and '"PRESENT"' in rid_lines[0] and '"UNKNOWN"' in rid_lines[-1],
          len(rid_lines))

    print("S2 · koreksi sebagian: masih ada bukti aktif -> TIDAK otomatis turun")
    evB = _ev("ev-b2", "cl-b2", Q2)
    graph2 = _graph(("cl-b1", Q1), ("cl-b2", Q2))
    evA = _ev("ev-b1", "cl-b1", Q1)
    _run(user_a, [evA, evB], graph2, ScriptedSP())
    e3 = ledger.latest_entry(user_a, RID)
    check("S2a dua bukti aktif -> PRESENT (refs keduanya)",
          e3["adjudication"]["status"] == "PRESENT"
          and sorted(e3["adjudication"]["evidence_refs"]) == ["ev-b1", "ev-b2"],
          e3["adjudication"])
    evA.superseded = True  # partial correction: ev-b2 STILL stands
    r4 = _run(user_a, [evA, evB], graph2, ScriptedSP())
    e4 = ledger.latest_entry(user_a, RID)
    check("S2b re-adjudikasi normal: tetap PRESENT dengan refs bukti aktif saja",
          e4["adjudication"]["status"] == "PRESENT"
          and e4["adjudication"]["evidence_refs"] == ["ev-b2"]
          and not any(i["requirement_id"] == RID for i in r4["invalidated"]),
          (e4["adjudication"]["status"], e4["adjudication"]["evidence_refs"], r4["invalidated"]))

    print("S3 · isolasi lintas-user")
    check("S3a user B tak punya entry (ledger B tak tersentuh)",
          ledger.latest_entry(user_b, RID) is None and ledger.requirement_ids_with_entries(user_b) == [])
    check("S3b enumerasi user A memuat rid target & user-scoped (⊆ registry)",
          RID in ledger.requirement_ids_with_entries(user_a)
          and set(ledger.requirement_ids_with_entries(user_a))
          <= {e["requirement_id"] for e in load_registry().values()},
          ledger.requirement_ids_with_entries(user_a))

    print("S4 · invalidasi bebas LLM (tercakup S1b: rerun dengan llm=None tetap menulis UNKNOWN)")

    print("S5 · koreksi parsial + provider TIDAK tersedia -> bukti aktif terverifikasi tidak hilang")
    user_c = "u-gatea-c"
    ev_c1 = _ev("ev-c1", "cl-c1", Q1)
    ev_c2 = _ev("ev-c2", "cl-c2", Q2)
    graph_c = _graph(("cl-c1", Q1), ("cl-c2", Q2))
    _run(user_c, [ev_c1, ev_c2], graph_c, ScriptedSP())
    pre = ledger.latest_entry(user_c, RID)
    check("S5a dua bukti aktif -> PRESENT refs keduanya",
          pre["adjudication"]["status"] == "PRESENT"
          and sorted(pre["adjudication"]["evidence_refs"]) == ["ev-c1", "ev-c2"],
          pre["adjudication"])
    lines_pre = len(_rid_lines(user_c))
    ev_c1.superseded = True  # partial correction: ev-c2 STILL active
    r5 = _run(user_c, [ev_c1, ev_c2], graph_c, None)  # provider absent (run without LLM)
    e5 = ledger.latest_entry(user_c, RID)
    check("S5b absen provider ≠ bukti tak valid: entri terakhir TIDAK turun ke UNKNOWN",
          e5["adjudication"]["status"] == "PRESENT", e5["adjudication"]["status"])
    check("S5c tak ada entri baru utk rid (verification unavailable, bukan bukti digantikan)",
          len(_rid_lines(user_c)) == lines_pre
          and not any(i["requirement_id"] == RID for i in r5["invalidated"]),
          (lines_pre, len(_rid_lines(user_c)), r5["invalidated"]))
    _run(user_c, [ev_c1, ev_c2], graph_c, ScriptedSP())  # provider is back
    e5b = ledger.latest_entry(user_c, RID)
    check("S5d provider kembali -> re-adjudikasi normal: PRESENT refs bukti aktif saja",
          e5b["adjudication"]["status"] == "PRESENT"
          and e5b["adjudication"]["evidence_refs"] == ["ev-c2"],
          e5b["adjudication"])

    print("S6 · koreksi parsial + provider GAGAL (timeout) -> degradasi jujur, bukti tetap berdiri")
    user_d = "u-gatea-d"
    ev_d1 = _ev("ev-d1", "cl-d1", Q1)
    ev_d2 = _ev("ev-d2", "cl-d2", Q2)
    graph_d = _graph(("cl-d1", Q1), ("cl-d2", Q2))
    _run(user_d, [ev_d1, ev_d2], graph_d, ScriptedSP())
    ev_d1.superseded = True
    r6 = _run(user_d, [ev_d1, ev_d2], graph_d, FailingSP())
    e6 = ledger.latest_entry(user_d, RID)
    check("S6a kegagalan provider tidak menurunkan status (bukan verdict)",
          e6["adjudication"]["status"] == "PRESENT", e6["adjudication"]["status"])
    check("S6b kegagalan tercatat jujur (SECOND_PASS_FAILED, bukan exception)",
          any(k.startswith("SECOND_PASS_FAILED") for k in r6["unresolved"]), r6["unresolved"])

    print("S7 · batas fix: penolakan DEFINITIF verifier tetap menurunkan (anti over-preserve)")
    user_e = "u-gatea-e"
    ev_e1 = _ev("ev-e1", "cl-e1", Q1)
    ev_e2 = _ev("ev-e2", "cl-e2", Q2)
    graph_e = _graph(("cl-e1", Q1), ("cl-e2", Q2))
    _run(user_e, [ev_e1, ev_e2], graph_e, ScriptedSP())
    ev_e1.superseded = True
    r7 = _run(user_e, [ev_e1, ev_e2], graph_e, NoMatchSP())
    e7 = ledger.latest_entry(user_e, RID)
    check("S7a bukti aktif ditolak definitif (NO_MATCH) -> recompute UNKNOWN + tercatat",
          e7["adjudication"]["status"] == "UNKNOWN"
          and any(i["requirement_id"] == RID and i["now"] == "UNKNOWN" for i in r7["invalidated"]),
          (e7["adjudication"]["status"], r7["invalidated"]))
    check("S7b klaim superseded tetap tidak dihidupkan (S1 tetap berlaku utk user ini)",
          "ev-e1" not in (e7["adjudication"]["evidence_refs"] or []), e7["adjudication"])

    failed = [r for r in RESULTS if not r[1]]
    print()
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"FAIL :: {name} :: {detail}")
    print(f"\n{'✅ PASS' if not failed else '❌ FAIL'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
