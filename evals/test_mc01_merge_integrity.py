"""MC01-3 — live-qualification merge integrity: APPEND-ONLY (CIR-MC01 audit P0-C).

Adversarial: a quality-FAIL MUST NOT vanish because a rerun of the same (scenario, rep) key
passes; an infra-error attempt may be replaced by a completed rerun; BLOCKED_EXTERNAL does not
vanish silently; the whole attempt history + provenance (SHA, provider/model, corpus, rerun
reason) is kept and the verdict is reproducible from it.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals._merge_attempts import load_attempts, select_attempts  # noqa: E402
from evals._merge_golden import merge as merge_golden  # noqa: E402
from evals.run_live_golden import aggregate  # noqa: E402

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


def sc(sid, *, critical=False, dims=("role",)):
    return {"id": sid, "mode": "live", "critical": critical, "cohort": "holdout",
            "checks": [{"dim": d, "type": "claim"} for d in dims]}


def corpus(*scenarios):
    return {"corpus_version": "mc01-merge-test", "scenarios": list(scenarios)}


def run(sid, rep, checks, error=None):
    r = {"id": sid, "rep": rep, "checks": [], "turns": []}
    if error:
        r["error"] = error
        return r
    if isinstance(checks, dict):
        checks = [{"dim": d, "type": "claim", "ok": bool(v)} for d, v in checks.items()]
    r["checks"] = checks
    return r


def _write_reports(tmp: Path, reports: list[dict]) -> list[str]:
    paths = []
    for i, rep in enumerate(reports):
        fp = tmp / f"batch{i}.json"
        fp.write_text(json.dumps(rep, ensure_ascii=False))
        paths.append(str(fp))
    return paths


def t1_quality_fail_cannot_be_replaced_by_pass():
    print("T1 — ADVERSARIAL: rerun PASS (kunci sama) TIDAK menggantikan FAIL pertama")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        paths = _write_reports(tmp, [
            {"status": "LIVE_FAIL", "runs": [run("G-01", 1, {"role": False})],
             "provider": "zai", "model": "glm-5.3-flash", "corpus": "c1", "ts_wib": "t1"},
            {"status": "LIVE_PASS", "runs": [run("G-01", 1, {"role": True})],
             "provider": "zai", "model": "glm-5.3-flash", "corpus": "c1", "ts_wib": "t2"},
        ])
        attempts, blocked = load_attempts([paths[0], f"{paths[1]}::ingin_lulus"])
        sel = select_attempts(attempts, blocked)
        c = corpus(sc("G-01"))
        rep = aggregate(sel["runs"], c, guard_rate=1.0)
        check("attempt terpilih = FAIL pertama → verdict tetap bukan PASS",
              sel["runs"][0]["checks"][0]["ok"] is False and rep["status"] != "LIVE_PASS",
              rep["status"])
        check("attempt PASS rerun TIDAK hilang: tersimpan + eksklusi ber-alasan",
              len(sel["attempts_all"]) == 2
              and sum(1 for a in sel["attempts_all"] if not a["selected"]) == 1
              and sel["attempts_all"][1]["exclusion"] == "superseded_by_first_quality_attempt"
              and sel["attempts_all"][1]["rerun_reason"] == "ingin_lulus",
              sel["attempts_all"])
        check("provenance SHA + provider/model/corpus + sequence tercatat",
              all(len(a["report_sha256"]) == 16 and a["provider"] == "zai"
                  and a["corpus_version"] == "c1" and isinstance(a["sequence"], int)
                  for a in sel["attempts_all"]))


def t2_infra_error_can_be_superseded_by_completed():
    print("T2 — attempt infra-error BOLEH digantikan rerun selesai (dan tetap tersimpan)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        paths = _write_reports(tmp, [
            {"status": "LIVE_FAIL", "runs": [run("G-01", 1, None, error="RateLimitError: kuota")],
             "provider": "zai", "corpus": "c1"},
            {"status": "LIVE_PASS", "runs": [run("G-01", 1, {"role": True})],
             "provider": "zai", "corpus": "c1"},
        ])
        attempts, blocked = load_attempts([f"{paths[0]}::kuota_habis", paths[1]])
        sel = select_attempts(attempts, blocked)
        c = corpus(sc("G-01"))
        rep = aggregate(sel["runs"], c, guard_rate=1.0)
        check("rerun selesai mewakili rep → verdict PASS",
              rep["status"] == "LIVE_PASS" and sel["runs"][0]["checks"][0]["ok"] is True,
              rep["status"])
        check("attempt error tetap tersimpan + eksklusi infra_error_excluded",
              sel["attempts_all"][0]["outcome"] == "error"
              and sel["attempts_all"][0]["exclusion"] == "infra_error_excluded"
              and sel["attempts_all"][0]["rerun_reason"] == "kuota_habis")


def t3_error_only_attempt_represents_honestly():
    print("T3 — bila hanya ada attempt error, dia yang mewakili (denominator tidak menyusut)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        paths = _write_reports(tmp, [
            {"status": "LIVE_FAIL", "runs": [run("G-01", 1, None, error="ValueError: boom")]}])
        attempts, blocked = load_attempts(paths)
        sel = select_attempts(attempts, blocked)
        c = corpus(sc("G-01"))
        rep = aggregate(sel["runs"], c, guard_rate=1.0)
        check("attempt error terpilih → completed < expected → bukan PASS",
              sel["runs"][0].get("error") and rep["status"] != "LIVE_PASS"
              and rep["completed_attempts"] < rep["expected_attempts"], rep)


def t4_blocked_propagation_and_recovery():
    print("T4 — BLOCKED_EXTERNAL ter-propagasi; pulih hanya bila ada rerun selesai")
    c2 = corpus(sc("G-01"), sc("G-02"))
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # batch A: G-01 finished, G-02 blocked by infra (has no run)
        paths_a = _write_reports(tmp, [
            {"status": "BLOCKED_EXTERNAL_PARTIAL", "blocked": ["G-02#1"],
             "runs": [run("G-01", 1, {"role": True})]}])
        attempts, blocked = load_attempts(paths_a)
        sel = select_attempts(attempts, blocked)
        rep = aggregate(sel["runs"], c2, blocked_ids=sel["blocked_ids"], guard_rate=1.0)
        check("tanpa rerun: blocked ter-propagasi → BLOCKED_EXTERNAL_PARTIAL",
              sel["blocked_ids"] == ["G-02#1"]
              and rep["status"] == "BLOCKED_EXTERNAL_PARTIAL", rep["status"])
        # batch B: finished rerun for G-02
        paths_b = _write_reports(tmp, [
            {"status": "BLOCKED_EXTERNAL_PARTIAL", "blocked": ["G-02#1"],
             "runs": [run("G-01", 1, {"role": True})]},
            {"status": "LIVE_PASS", "runs": [run("G-02", 1, {"role": True})]}])
        attempts, blocked = load_attempts(paths_b)
        sel = select_attempts(attempts, blocked)
        rep = aggregate(sel["runs"], c2, blocked_ids=sel["blocked_ids"], guard_rate=1.0)
        check("dengan rerun selesai: blocked tidak dihitung dua kali → PASS",
              sel["blocked_ids"] == [] and rep["status"] == "LIVE_PASS", rep["status"])
        check("blocked sumber tetap tercatat di policy (riwayat tidak hilang)",
              sel["policy"]["source_blocked"] == ["G-02#1"])


def t5_merge_golden_end_to_end(tmpdir=None):
    print("T5 — merge() golden end-to-end: report final membawa seluruh riwayat attempt")
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        tmp = Path(td)
        cpath = tmp / "corpus.json"
        cpath.write_text(json.dumps(corpus(sc("G-01"))))
        a = tmp / "a.json"
        b = tmp / "b.json"
        a.write_text(json.dumps({"status": "LIVE_FAIL",
                                 "runs": [run("G-01", 1, {"role": False})],
                                 "provider": "zai", "model": "glm-5.3-flash", "corpus": "c1"}))
        b.write_text(json.dumps({"status": "LIVE_PASS",
                                 "runs": [run("G-01", 1, {"role": True})],
                                 "provider": "zai", "model": "glm-5.3-flash", "corpus": "c1"}))
        rep = merge_golden([f"{a}::salah_config", str(b)], corpus_path=cpath)
        check("status final memakai attempt pertama (FAIL) — bukan cherry-pick PASS",
              rep["status"] != "LIVE_PASS", rep["status"])
        check("report final memuat attempts_all + policy + runs terpilih",
              len(rep["attempts_all"]) == 2 and rep["attempts_policy"]["selection"]
              == "first-quality-wins" and len(rep["runs"]) == 1)
        check("verdict dapat direproduksi dari attempts_all (selected == runs)",
              [a["key"] for a in rep["attempts_all"] if a["selected"]] == [[r["id"], r["rep"]]
                                                                            for r in rep["runs"]])


def main() -> int:
    t1_quality_fail_cannot_be_replaced_by_pass()
    t2_infra_error_can_be_superseded_by_completed()
    t3_error_only_attempt_represents_honestly()
    t4_blocked_propagation_and_recovery()
    t5_merge_golden_end_to_end()
    print(f"\n{'=' * 62}\nMC01-3 merge integrity: {_PASS} OK, {_FAIL} GAGAL")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
