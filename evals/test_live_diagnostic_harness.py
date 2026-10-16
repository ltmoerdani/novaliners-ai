"""S1/S3 — diagnostic harness runner unit tests (run_live_diagnostic) + shared aggregation (live_qualify).

Locks the Oct 14 2026 audit:

  - P0-A: corpus v2 adapter semantics — Create Map consumes turns[0], each `message` step
    consumes the NEXT turn, and the user-event count is verified (no duplication/extra events);
  - P0-B: diagnostic aggregation uses the SHARED contract — denominator is SCHEDULED attempts,
    a missing attempt -> not PASS, critical cases require majority, a --only subset -> PARTIAL,
    and zero-tolerance concepts map EXPLICITLY to detecting check types (unmapped concepts are
    reported);
  - P0-C: `fabricated_revenue_fields` reads canonical `RevenueState` fields + provenance —
    the phantom `monthly_revenue` field can never pass again without checking anything.

Run: .venv/bin/python evals/test_live_diagnostic_harness.py  (deterministic, no network)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals import run_live_diagnostic as R  # noqa: E402
from evals.live_qualify import (  # noqa: E402
    DIAGNOSTIC_ZERO_TOLERANCE_TYPES,  # noqa: E402
    fabricated_revenue_fields,
    scheduled_attempts,
)
from evals.live_qualify import aggregate as shared_aggregate  # noqa: E402

_PASS = 0
_FAIL = 0


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print("  OK  " + name)
    else:
        _FAIL += 1
        print("  GAGAL  " + name + (" - " + str(detail) if detail else ""))


# ── synthetic scenario/run helpers for aggregation ────────────────────────────────────────────────


def sc(sid, *, critical=False, dims=(("canonical_fidelity", "superseded_absent_from_current"),)):
    return {"id": sid, "critical": critical, "cohort": "holdout",
            "checks": [{"dim": d, "type": t} for d, t in dims]}


def fake_corpus(scenarios, acceptance=None):
    acc = {"zero_tolerance": ["no_fabricated_metric"],
           "min_rates": {"canonical_fidelity": 0.9, "honest_low_evidence": 0.8},
           "critical_repeats": 2, "critical_pass_majority": 0.5,
           "provider_blocked_class": "BLOCKED_EXTERNAL"}
    if acceptance:
        acc.update(acceptance)
    return {"corpus_version": "test", "acceptance": acc, "scenarios": scenarios}


def mk_from(scen, rep, ok=True):
    return {"id": scen["id"], "rep": rep,
            "checks": [{"dim": ck["dim"], "type": ck["type"], "ok": bool(ok)} for ck in scen["checks"]]}


# ── P0-A: corpus v2 adapter semantics ───────────────────────────────────────────────────────────


def test_corpus_v2_adapter_semantics():
    print("A - adapter v2: Create Map mengonsumsi turns[0]; message = turn berikutnya")
    corpus = R.load_corpus()
    check("versi korpus = dcp-corpus-v2", corpus["corpus_version"] == "dcp-corpus-v2",
          corpus["corpus_version"])
    d01 = next(s for s in corpus["scenarios"] if s["id"] == "D-01")
    texts = R.message_texts(d01)
    check("D-01: daftar message = turns[1:] (tanpa duplikasi turns[0])",
          texts == d01["turns"][1:], texts)
    check("D-01: teks Create Map TIDAK dikirim ulang sebagai message",
          d01["turns"][0] not in texts, texts)
    n_msg = {s["id"]: sum(1 for st in s["sequence"] if st == "message") for s in corpus["scenarios"]}
    check("semua skenario: jumlah message = len(turns)-1",
          all(n_msg[s["id"]] == len(s["turns"]) - 1 for s in corpus["scenarios"]), n_msg)
    v1 = R.HERE / "diagnostic" / "corpus_v1.json"
    check("korpus v1 tetap ada sebagai rekaman", v1.exists(), str(v1))


def test_message_texts_rejects_inconsistent():
    print("B - sequence tidak konsisten DITOLAK (bukan diam-diam mengarang event user)")
    bad = {"id": "X", "turns": ["a"], "sequence": ["session", "message"]}
    try:
        R.message_texts(bad)
        ok = False
    except ValueError:
        ok = True
    check("1 message untuk 1 turn -> ValueError", ok)
    bad2 = {"id": "Y", "turns": ["a", "b", "c"], "sequence": ["session", "message"]}
    try:
        R.message_texts(bad2)
        ok2 = False
    except ValueError:
        ok2 = True
    check("3 turns tapi hanya 1 message -> ValueError", ok2)


def test_scheduled_attempts_diagnostic():
    print("C - attempt terjadwal korpus diagnostik (kritis = 2 repeat)")
    corpus = R.load_corpus()
    sched = scheduled_attempts(corpus["scenarios"],
                               critical_repeats=corpus["acceptance"]["critical_repeats"])
    counts: dict[str, int] = {}
    for sid, _k in sched:
        counts[sid] = counts.get(sid, 0) + 1
    check("D-01/D-02/D-05 = 2 attempt", all(counts[i] == 2 for i in ("D-01", "D-02", "D-05")), counts)
    check("D-03/D-04/D-06/D-07 = 1 attempt",
          all(counts[i] == 1 for i in ("D-03", "D-04", "D-06", "D-07")), counts)


# ── P0-B: diagnostic aggregation uses the shared contract ─────────────────────────────────────────


def test_aggregate_full_pass_and_missing():
    print("D - agregasi diagnostik: cakupan lengkap -> PASS; attempt hilang -> bukan PASS")
    s1 = sc("D-01", critical=True)
    s2 = sc("D-05", dims=(("honest_low_evidence", "no_fabricated_revenue_metric"),))
    corpus = fake_corpus([s1, s2])
    full = [mk_from(s1, 1), mk_from(s1, 2), mk_from(s2, 1)]
    rep = R.aggregate(full, corpus)
    check("cakupan lengkap + lulus -> LIVE_PASS", rep["status"] == "LIVE_PASS",
          (rep["status"], rep["reasons"]))
    partial_runs = [mk_from(s1, 1), mk_from(s2, 1)]  # D-01#2 missing without any blocked/error trace
    rep2 = R.aggregate(partial_runs, corpus)
    check("attempt terjadwal hilang -> bukan PASS", rep2["status"] != "LIVE_PASS", rep2["status"])
    check("attempt hilang terdaftar", rep2["missing_attempts"] == ["D-01#2"], rep2["missing_attempts"])


def test_aggregate_only_subset():
    print("E - subset --only -> PARTIAL, tidak pernah LIVE_PASS")
    s1 = sc("D-01", critical=True)
    s2 = sc("D-05", dims=(("honest_low_evidence", "no_fabricated_revenue_metric"),))
    corpus = fake_corpus([s1, s2])
    runs = [mk_from(s1, 1), mk_from(s1, 2)]  # subset = D-01 only; both critical reps are run
    rep = R.aggregate(runs, corpus, only={"D-01"})
    check("status PARTIAL", rep["status"] == "PARTIAL", (rep["status"], rep["reasons"]))


def test_aggregate_blocked():
    print("F - provider terblokir -> BLOCKED_EXTERNAL_PARTIAL (bukan PASS)")
    s1 = sc("D-01", critical=True)
    s2 = sc("D-05", dims=(("honest_low_evidence", "no_fabricated_revenue_metric"),))
    corpus = fake_corpus([s1, s2])
    runs = [mk_from(s1, 1, ok=True)]
    rep = R.aggregate(runs, corpus, blocked_ids=["D-01#2", "D-05#1"])
    check("status BLOCKED_EXTERNAL_PARTIAL", rep["status"] == "BLOCKED_EXTERNAL_PARTIAL", rep["status"])


def test_critical_majority_closure():
    print("G - kasus kritis < majority -> LIVE_FAIL (ambang dimensi netral)")
    s1 = sc("C-01", critical=True)
    acc = {"zero_tolerance_dims": [], "dim_min_rate": {"canonical_fidelity": 0.0},
           "critical_repeats": 3, "critical_pass_majority": 0.667}
    runs = [mk_from(s1, 1, ok=True), mk_from(s1, 2, ok=False), mk_from(s1, 3, ok=False)]
    rep = shared_aggregate(runs, [s1], acc)
    check("1/3 lulus -> LIVE_FAIL", rep["status"] == "LIVE_FAIL", (rep["status"], rep["reasons"]))
    runs2 = [mk_from(s1, 1, ok=True), mk_from(s1, 2, ok=True), mk_from(s1, 3, ok=False)]
    rep2 = shared_aggregate(runs2, [s1], acc)
    check("2/3 lulus >= majority -> LIVE_PASS", rep2["status"] == "LIVE_PASS",
          (rep2["status"], rep2["reasons"]))


def test_zero_tolerance_type_enforcement():
    print("H - konsep zero-tolerance dipetakan ke tipe check: pelanggaran = FAIL paksa")
    s1 = sc("D-05", dims=(("honest_low_evidence", "no_fabricated_revenue_metric"),))
    corpus = fake_corpus([s1], acceptance={"zero_tolerance": ["no_fabricated_metric"],
                                           "min_rates": {"honest_low_evidence": 0.0}})
    rep = R.aggregate([mk_from(s1, 1, ok=False)], corpus)
    check("pelanggaran terdeteksi via detektor tipe check",
          rep["zero_tolerance_type_violations"], rep["zero_tolerance_type_violations"])
    check("status dipaksa LIVE_FAIL walau ambang dimensi netral",
          rep["status"] == "LIVE_FAIL", rep["status"])
    check("konsep terpetakan (bukan unmapped)",
          "no_fabricated_metric" not in rep["zero_tolerance_unmapped"],
          rep["zero_tolerance_unmapped"])


def test_zero_tolerance_unmapped_reported():
    print("I - konsep zero-tolerance tanpa detektor DILAPORKAN, bukan hilang diam-diam")
    s1 = sc("D-05", dims=(("honest_low_evidence", "no_fabricated_revenue_metric"),))
    corpus = fake_corpus([s1], acceptance={"zero_tolerance": ["no_false_promotion",
                                                              "no_fabricated_metric"],
                                           "min_rates": {"honest_low_evidence": 0.0}})
    rep = R.aggregate([mk_from(s1, 1, ok=True)], corpus)
    check("konsep tanpa detektor -> zero_tolerance_unmapped",
          rep["zero_tolerance_unmapped"] == ["no_false_promotion"], rep["zero_tolerance_unmapped"])
    check("alasan memuat catatan eksplisit",
          any("tanpa detektor" in x for x in rep["reasons"]), rep["reasons"])
    # Gate A (Oct 15): a coverage gap MUST NOT pass as LIVE_PASS — it is vetoed with an
    # explicit classification (coverage gap), distinct from a semantic violation (type violation).
    check("unmapped mem-veto LIVE_PASS (coverage gap)",
          rep["status"] == "LIVE_FAIL"
          and any("coverage gap" in x for x in rep["reasons"]),
          (rep["status"], rep["reasons"]))


def test_diagnostic_corpus_zero_tolerance_mapping():
    # OPEN-L5 (Oct 15 2026): no_false_promotion is now MAPPED to the detector
    # standing_not_supported (D-05 enforces evidence_standing INSUFFICIENT/WEAK) —
    # the concept is no longer a coverage gap; its violation vetoes LIVE_PASS.
    print("J - korpus nyata: 4 konsep zero-tolerance TERPETAKAN "
          "(no_false_promotion via standing_not_supported)")
    corpus = R.load_corpus()
    runs = []  # no runs: exercises the mapping report only, not the verdict
    rep = R.aggregate(runs, corpus)
    check("seluruh konsep zero-tolerance berdetektor (zero unmapped)",
          rep["zero_tolerance_unmapped"] == [], rep["zero_tolerance_unmapped"])
    check("no_false_promotion dijaga standing_not_supported",
          "standing_not_supported" in DIAGNOSTIC_ZERO_TOLERANCE_TYPES["no_false_promotion"])
    # detector violations now veto as VIOLATION (not coverage gap)
    s1 = sc("D-05", dims=(("honest_low_evidence", "standing_not_supported"),))
    fake = fake_corpus([s1], acceptance={"zero_tolerance": ["no_false_promotion"],
                                         "min_rates": {"honest_low_evidence": 0.0}})
    rep2 = R.aggregate([mk_from(s1, 1, ok=False)], fake)
    check("standing gagal -> veto no_false_promotion (bukan unmapped)",
          any(x.startswith("no_false_promotion:") for x in rep2["zero_tolerance_type_violations"])
          and rep2["zero_tolerance_unmapped"] == [],
          (rep2["zero_tolerance_type_violations"], rep2["zero_tolerance_unmapped"]))


# ── P0-C: canonical fields + provenance (not phantom fields) ──────────────────────────────────────


def test_fabricated_revenue_fields():
    print("K - fabricated_revenue_fields: field kanonik + provenance; field hantu tidak bisa lulus")
    empty = {"current_monthly": None, "target_monthly": None, "sources": {}}
    check("semua None -> tidak ada temuan", fabricated_revenue_fields(empty) == [])
    unsourced = {"current_monthly": 12.0, "sources": {}}
    check("nilai tanpa sources -> dilaporkan", fabricated_revenue_fields(unsourced) == ["current_monthly"],
          fabricated_revenue_fields(unsourced))
    sourced = {"current_monthly": 12.0, "sources": {"current_monthly": {"evidence_id": "ev-1"}}}
    check("nilai dengan provenance evidence_id -> sah", fabricated_revenue_fields(sourced) == [])
    deriv = {"current_monthly": None, "target_monthly": 50.0,
             "sources": {"target_monthly": {"derivation": "goal context (registry revenue_monthly)"}}}
    check("nilai dengan provenance derivation -> sah", fabricated_revenue_fields(deriv) == [],
          fabricated_revenue_fields(deriv))
    phantom = {"monthly_revenue": 12.0, "sources": {}}
    check("field hantu 'monthly_revenue' -> schema-hilang terdeteksi (regresi P0-C)",
          fabricated_revenue_fields(phantom) == ["<schema:current_monthly-hilang>"],
          fabricated_revenue_fields(phantom))
    check("dict kosong -> schema-hilang",
          fabricated_revenue_fields({}) == ["<schema:current_monthly-hilang>"])


# ── D-05 continued: three prescription-depth bands (audit: check 0.30–0.59, not a new system) ──


def test_prescription_throttle_bands():
    print("L - prescription throttle tiga band terkunci tes (helper murni)")
    from types import SimpleNamespace

    from agents.diagnosis import prescription_throttle
    d1 = SimpleNamespace(day_by_day=[SimpleNamespace(text=f"A{i}") for i in range(7)])
    note1 = prescription_throttle(d1, 0.22)
    check("band <0.30 -> maksimal 3 item executable", len(d1.day_by_day) == 3, len(d1.day_by_day))
    # 18 Okt (9603d6b): wording diganti DIGANTUNG -> DEFERRED (English-first, konvensi int 07 §7)
    check("band <0.30 -> penundaan DEFERRED di note (bukan ActionItem)",
          "DEFERRED" in note1 and "THROTTLE" in note1, note1[:140])
    d2 = SimpleNamespace(day_by_day=list(range(7)))
    note2 = prescription_throttle(d2, 0.45)
    check("band 0.30–0.59 -> maksimal 5 item (perilaku lama DIKUNCI)",
          len(d2.day_by_day) == 5, len(d2.day_by_day))
    check("band 0.30–0.59 -> tanpa note penundaan", note2 == "", note2)
    d3 = SimpleNamespace(day_by_day=list(range(7)))
    note3 = prescription_throttle(d3, 0.8)
    check("band >=0.60 -> rencana tidak dipangkas", len(d3.day_by_day) == 7 and note3 == "",
          (len(d3.day_by_day), note3))
    d4 = SimpleNamespace(day_by_day=[SimpleNamespace(text="X")])
    note4 = prescription_throttle(d4, 0.1)
    check("band <0.30 rencana pendek -> note throttle tanpa DIGANTUNG",
          "THROTTLE" in note4 and "DIGANTUNG" not in note4, note4[:140])


TESTS = [
    test_corpus_v2_adapter_semantics,
    test_message_texts_rejects_inconsistent,
    test_scheduled_attempts_diagnostic,
    test_aggregate_full_pass_and_missing,
    test_aggregate_only_subset,
    test_aggregate_blocked,
    test_critical_majority_closure,
    test_zero_tolerance_type_enforcement,
    test_zero_tolerance_unmapped_reported,
    test_diagnostic_corpus_zero_tolerance_mapping,
    test_fabricated_revenue_fields,
    test_prescription_throttle_bands,
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
    print("DIAGNOSTIC HARNESS RESULT: " + str(_PASS) + " passed, " + str(_FAIL) + " failed")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
