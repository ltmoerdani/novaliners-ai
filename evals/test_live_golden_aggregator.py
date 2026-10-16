"""S3-C - unit tests for the LIVE qualification aggregator (run_live_golden.aggregate).

The verdict must be mechanical from the evidence record: scheduled coverage (not only completed),
mandatory dims, zero-tolerance, critical cases, the acceptance guard, --only subsets, and
provider blocks.

Run: .venv/bin/python evals/test_live_golden_aggregator.py  (deterministic, no network)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.run_live_golden import THRESHOLDS, aggregate  # noqa: E402

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


def sc(sid, *, mode="live", critical=False, dims=("role",), cohort="holdout"):
    return {"id": sid, "mode": mode, "critical": critical, "cohort": cohort,
            "checks": [{"dim": d, "type": "claim"} for d in dims]}


def corpus(*scenarios):
    return {"corpus_version": "test", "scenarios": list(scenarios)}


def run(sid, rep, checks, error=None):
    r = {"id": sid, "rep": rep, "checks": [], "turns": []}
    if error:
        r["error"] = error
        return r
    if isinstance(checks, dict):
        checks = [{"dim": d, "type": "claim", "ok": bool(v)} for d, v in checks.items()]
    r["checks"] = checks
    return r


def all_true(dims):
    return {d: True for d in dims}


def test_full_pass():
    print("A - semua skenario selesai, ambang lulus -> LIVE_PASS")
    c = corpus(sc("G-01", dims=("role", "goal")), sc("G-02", dims=("role", "goal")))
    runs = [run("G-01", 1, all_true(("role", "goal"))), run("G-02", 1, all_true(("role", "goal")))]
    rep = aggregate(runs, c, guard_rate=1.0)
    check("status LIVE_PASS", rep["status"] == "LIVE_PASS", rep)
    check("cakupan lengkap", rep["expected_attempts"] == 2 and rep["completed_attempts"] == 2)


def test_non_provider_error():
    print("B - satu skenario error non-provider -> LIVE_FAIL")
    c = corpus(sc("G-01"), sc("G-02"))
    runs = [run("G-01", 1, all_true(("role",))), run("G-02", 1, {}, error="ValueError: boom")]
    rep = aggregate(runs, c, guard_rate=1.0)
    check("status LIVE_FAIL", rep["status"] == "LIVE_FAIL", rep["status"])


def test_missing_mandatory_check():
    print("C - satu check wajib hilang -> bukan PASS")
    c = corpus(sc("G-01", dims=("role", "goal")))
    runs = [run("G-01", 1, all_true(("role",)))]  # goal not reported
    rep = aggregate(runs, c, guard_rate=1.0)
    check("status bukan LIVE_PASS", rep["status"] != "LIVE_PASS", rep["status"])
    check("dimensi wajib absen terdeteksi", "goal" in rep["missing_dims"], rep["missing_dims"])


def test_required_dim_absent():
    print("D - dimensi wajib absen dari cakupan selesai -> bukan PASS")
    c = corpus(sc("G-01", dims=("role",)), sc("G-02", dims=("goal",)))
    runs = [run("G-01", 1, all_true(("role",))), run("G-02", 1, [])]  # G-02 finishes with no checks
    rep = aggregate(runs, c, guard_rate=1.0)
    check("status bukan LIVE_PASS", rep["status"] != "LIVE_PASS", rep["status"])
    check("goal tercatat absen", "goal" in rep["missing_dims"], rep["missing_dims"])


def test_only_subset_partial():
    print("E - subset --only -> PARTIAL, tidak pernah LIVE_PASS")
    c = corpus(sc("G-01"), sc("G-02"))
    runs = [run("G-01", 1, all_true(("role",)))]
    rep = aggregate(runs, c, only={"G-01"}, guard_rate=1.0)
    check("status PARTIAL", rep["status"] == "PARTIAL", rep["status"])
    check("cakupan terjadwal = subset", rep["expected_attempts"] == 1)


def test_blocked_halfway():
    print("F - provider terblokir separuh -> BLOCKED_EXTERNAL_PARTIAL")
    c = corpus(sc("G-01"), sc("G-02"))
    runs = [run("G-01", 1, all_true(("role",)))]
    rep = aggregate(runs, c, blocked_ids=["G-02#1"], guard_rate=1.0)
    check("status BLOCKED_EXTERNAL_PARTIAL", rep["status"] == "BLOCKED_EXTERNAL_PARTIAL", rep["status"])


def test_critical_one_of_three():
    print("G - kasus kritis lulus 1/3 -> FAIL")
    c = corpus(sc("G-04", critical=True, dims=("role",)))
    runs = [run("G-04", 1, all_true(("role",))),
            run("G-04", 2, {"role": False}),
            run("G-04", 3, {"role": False})]
    rep = aggregate(runs, c, guard_rate=1.0)
    check("fraksi kritis 1/3", rep["critical_pass_fraction"]["G-04"] == round(1 / 3, 3),
          rep["critical_pass_fraction"])
    check("status LIVE_FAIL", rep["status"] == "LIVE_FAIL", rep["status"])


def test_critical_two_of_three_eligible():
    print("H - kasus kritis lulus 2/3 tanpa zero-tolerance -> eligible bila ambang lain lulus")
    c = corpus(sc("G-04", critical=True, dims=("role",)),
               *[sc("G-%02d" % i, dims=("role",)) for i in range(5, 12)])
    runs = [run("G-04", 1, all_true(("role",))),
            run("G-04", 2, all_true(("role",))),
            run("G-04", 3, {"role": False})]
    runs += [run("G-%02d" % i, 1, all_true(("role",))) for i in range(5, 12)]
    rep = aggregate(runs, c, guard_rate=1.0)
    check("fraksi kritis 2/3", rep["critical_pass_fraction"]["G-04"] == round(2 / 3, 3),
          rep["critical_pass_fraction"])
    check("rate role tetap di atas ambang", rep["rates"]["role"] >= THRESHOLDS["dim_min_rate"]["role"],
          rep["rates"])
    check("status LIVE_PASS (eligible)", rep["status"] == "LIVE_PASS", (rep["status"], rep["reasons"]))


def test_zero_tolerance_violation():
    print("I - pelanggaran zero-tolerance -> FAIL")
    c = corpus(sc("G-01", dims=("role", "no_false_goal")))
    runs = [run("G-01", 1, {"role": True, "no_false_goal": False})]
    rep = aggregate(runs, c, guard_rate=1.0)
    check("status LIVE_FAIL", rep["status"] == "LIVE_FAIL", rep["status"])
    check("zero-tolerance tercatat", "no_false_goal" in rep["zero_tolerance_failures"],
          rep["zero_tolerance_failures"])


def test_guard_below_threshold():
    print("J - guard acceptance di bawah ambang -> FAIL")
    c = corpus(sc("G-01", dims=("role",)))
    runs = [run("G-01", 1, all_true(("role",)))]
    rep = aggregate(runs, c, guard_rate=0.5)
    check("status LIVE_FAIL", rep["status"] == "LIVE_FAIL", rep["status"])


def test_zero_completed():
    print("K - nol skenario LIVE selesai -> bukan PASS")
    c = corpus(sc("G-01", dims=("role",)))
    rep = aggregate([], c, guard_rate=None)
    check("status bukan LIVE_PASS", rep["status"] != "LIVE_PASS", rep["status"])
    rep2 = aggregate([], c, blocked_ids=["G-01#1"], guard_rate=None)
    check("blokir total -> BLOCKED_EXTERNAL", rep2["status"] == "BLOCKED_EXTERNAL", rep2["status"])


def test_unrated_dimension():
    print("L - dimensi tak terklasifikasi -> hasil eksplisit, bukan PASS diam-diam")
    c = corpus(sc("G-01", dims=("custom_dim",)))
    runs = [run("G-01", 1, {"custom_dim": True})]
    rep = aggregate(runs, c, guard_rate=1.0)
    check("status bukan LIVE_PASS", rep["status"] != "LIVE_PASS", rep["status"])
    check("dimensi tak terklasifikasi dilaporkan", "custom_dim" in rep["unrated_dims"], rep["unrated_dims"])


def test_rates_use_scheduled_denominator():
    print("M - rate memakai denominator attempt TERJADWAL (bukan hanya selesai)")
    c = corpus(sc("G-04", critical=True, dims=("role",)))
    runs = [run("G-04", 1, all_true(("role",)))]  # 2 scheduled attempts missing
    rep = aggregate(runs, c, guard_rate=1.0)
    check("rate role = 1/3, bukan 1.0", rep["rates"]["role"] == round(1 / 3, 3), rep["rates"])
    check("attempt hilang terdeteksi", len(rep["missing_attempts"]) == 2, rep["missing_attempts"])
    check("status bukan LIVE_PASS", rep["status"] != "LIVE_PASS", rep["status"])


TESTS = [
    test_full_pass, test_non_provider_error, test_missing_mandatory_check, test_required_dim_absent,
    test_only_subset_partial, test_blocked_halfway, test_critical_one_of_three,
    test_critical_two_of_three_eligible, test_zero_tolerance_violation, test_guard_below_threshold,
    test_zero_completed, test_unrated_dimension, test_rates_use_scheduled_denominator,
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
    print("AGGREGATOR RESULT: " + str(_PASS) + " passed, " + str(_FAIL) + " failed")
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
