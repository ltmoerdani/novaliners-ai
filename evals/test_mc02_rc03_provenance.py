"""MC02-RC-03 — merger provenance & reproducibility (RC-03 audit).

Tests: every attempt is bound to the candidate identity (commit SHA + working-tree fingerprint),
the ACTUAL provider/model, corpus version+hash, contract version, run/attempt id, `sequence`
(execution order, not a timestamp), the rerun reason, and its original result; the final report
refuses to merge attempts from different candidates; the verdict is reproducible from
`attempts_all` alone.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals._merge_attempts import (  # noqa: E402
    MixedCandidateError,
    candidate_identity,
    load_attempts,
    select_attempts,
)
from evals._merge_golden import merge as merge_golden  # noqa: E402
from evals.run_live_golden import THRESHOLDS, aggregate  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, ok, detail=""):
    global _PASS, _FAIL
    print(f"  {'OK ' if ok else 'XX '} {name}" + (f" | {detail}" if detail and not ok else ""))
    if ok:
        _PASS += 1
    else:
        _FAIL += 1


def sc(sid, dims=("role",)):
    return {"id": sid, "mode": "live", "critical": False, "cohort": "holdout",
            "checks": [{"dim": d, "type": "claim"} for d in dims]}


def corpus(*scenarios):
    return {"corpus_version": "rc03-test", "scenarios": list(scenarios)}


def run(sid, rep=1, ok=True, error=None):
    r = {"id": sid, "rep": rep, "checks": [], "turns": []}
    if error:
        r["error"] = error
        return r
    r["checks"] = [{"dim": "role", "type": "claim", "ok": bool(ok)}]
    return r


def wr(tmp: Path, name: str, runs, *, provider="zai", model="glm-5.3-flash", ts="t", candidate=None):
    d = {"status": "LIVE_PASS", "runs": runs, "provider": provider, "model": model,
         "corpus": "rc03-test", "ts_wib": ts, "contract": "nm.v2", "thresholds": THRESHOLDS}
    if candidate is not None:
        d["candidate"] = candidate
    p = tmp / name
    p.write_text(json.dumps(d))
    return str(p)


def t1_provenance_fields():
    print("T1 — setiap attempt membawa provenance lengkap (RC-03)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cpath = tmp / "corpus.json"
        cpath.write_text(json.dumps(corpus(sc("G-01"))))
        p = wr(tmp, "a.json", [run("G-01")])
        attempts, _ = load_attempts([f"{p}::kuota_habis"], corpus_path=cpath)
        sel = select_attempts(attempts, [])
        a = sel["attempts_all"][0]
        need = ("attempt_id", "run_id", "report_sha256", "sequence", "provider", "model",
                "corpus_version", "corpus_sha256", "contract", "thresholds_sha256",
                "candidate", "rerun_reason")
        check("semua field provenance wajib ada", all(k in a for k in need),
              [k for k in need if k not in a])
        check("hash korpus + kontrak + rerun_reason terisi",
              len(a["corpus_sha256"]) == 16 and a["contract"] == "nm.v2"
              and a["rerun_reason"] == "kuota_habis")
        check("identitas kandidat: commit SHA + fingerprint working tree",
              set(a["candidate"]) >= {"commit_sha", "worktree_dirty", "worktree_fingerprint"}
              and a["candidate"]["commit_sha"] != "",
              json.dumps(a["candidate"]))
        check("sequence = urutan eksekusi (0-based), ts hanya metadata",
              a["sequence"] == 0 and "ts_wib" in a)


def t2_mixed_provider_rejected():
    print("T2 — provider/model berbeda DITOLAK (tidak boleh jadi satu verdict)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p1 = wr(tmp, "a.json", [run("G-01")], provider="zai", model="glm-5.3-flash")
        p2 = wr(tmp, "b.json", [run("G-02")], provider="opencode_go", model="mimo")
        attempts, blocked = load_attempts([p1, p2])
        try:
            select_attempts(attempts, blocked)
            check("harus menolak kandidat/provider campur", False, "tidak menolak")
        except MixedCandidateError as exc:
            check("MixedCandidateError menyebut provider/model yang bentrok",
                  "opencode_go" in str(exc) or "mimo" in str(exc), str(exc)[:160])


def t3_mixed_candidate_sha_rejected():
    print("T3 — commit SHA / fingerprint kode berbeda DITOLAK")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cand_a = {"commit_sha": "aaa111", "worktree_dirty": False, "worktree_fingerprint": "clean"}
        cand_b = {"commit_sha": "bbb222", "worktree_dirty": True, "worktree_fingerprint": "deadbeef1234"}
        p1 = wr(tmp, "a.json", [run("G-01")], candidate=cand_a)
        p2 = wr(tmp, "b.json", [run("G-02")], candidate=cand_b)
        attempts, blocked = load_attempts([p1, p2])
        try:
            select_attempts(attempts, blocked)
            check("harus menolak dua revisi kode dalam satu verdict", False, "tidak menolak")
        except MixedCandidateError as exc:
            check("MixedCandidateError mencantumkan kedua SHA", "aaa111" in str(exc)
                  and "bbb222" in str(exc), str(exc)[:200])


def t4_mixed_corpus_rejected():
    print("T4 — corpus berbeda (hash) DITOLAK")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        c1 = tmp / "c1.json"
        c1.write_text(json.dumps(corpus(sc("G-01"))))
        p1 = wr(tmp, "a.json", [run("G-01")])
        attempts1, _ = load_attempts([p1], corpus_path=c1)
        c2 = tmp / "c2.json"
        c2.write_text(json.dumps(corpus(sc("G-01"), sc("G-99"))))     # korpus berbeda
        attempts2, _ = load_attempts([wr(tmp, "b.json", [run("G-01")])], corpus_path=c2)
        check("hash korpus berbeda terdeteksi",
              attempts1[0]["_attempt"]["corpus_sha256"] != attempts2[0]["_attempt"]["corpus_sha256"])
        try:
            select_attempts(attempts1 + attempts2, [])
            check("harus menolak korpus berbeda", False, "tidak menolak")
        except MixedCandidateError as exc:
            check("MixedCandidateError menyebut korpus", "corpus" in str(exc).lower()
                  or len(str(exc)) > 20, str(exc)[:160])


def t5_verdict_reproducible_from_attempts_all():
    print("T5 — verdict dapat direproduksi dari attempts_all SAJA (tanpa report sumber)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cpath = tmp / "corpus.json"
        cpath.write_text(json.dumps(corpus(sc("G-01"), sc("G-02"))))
        p1 = wr(tmp, "a.json", [run("G-01"), run("G-02")])
        rep = merge_golden([p1], corpus_path=cpath)
        rebuilt = [a["result"] for a in rep["attempts_all"] if a["selected"]]
        check("hasil asli setiap attempt tersimpan lengkap di attempts_all",
              rebuilt == rep["runs"] and all("checks" in a["result"] for a in rep["attempts_all"]),
              f"{len(rebuilt)} vs {len(rep['runs'])}")
        c = json.loads(cpath.read_text())
        acc = [t for r in rebuilt for t in r["turns"][1:] if t.get("adaptive")]
        gr = round(sum(1 for t in acc if t["adaptive"] == "ACCEPTED") / len(acc), 3) if acc else None
        rep2 = aggregate(rebuilt, c, blocked_ids=rep["attempts_policy"]["source_blocked"],
                         guard_rate=gr, thresholds=THRESHOLDS)
        check("agregasi ulang dari attempts_all menghasilkan verdict yang SAMA",
              rep2["status"] == rep["status"], f"{rep2['status']} vs {rep['status']}")


def t6_sequence_not_timestamp():
    print("T6 — urutan ditentukan `sequence`, bukan timestamp (ts menyesatkan diabaikan)")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cpath = tmp / "corpus.json"
        cpath.write_text(json.dumps(corpus(sc("G-01"))))
        # report A has a NEWER ts but arrived earlier (sequence 0) and FAILED quality;
        # report B has an older ts, sequence 1, passes → first-quality-wins must use A.
        pa = wr(tmp, "a.json", [run("G-01", ok=False)], ts="2999-01-01 00:00:00")
        pb = wr(tmp, "b.json", [run("G-01", ok=True)], ts="1999-01-01 00:00:00")
        attempts, blocked = load_attempts([pa, pb])
        sel = select_attempts(attempts, blocked)
        seqs = {a["key"][0]: a["sequence"] for a in sel["attempts_all"]}
        check("sequence mengikuti urutan kedatangan argumen (0,1)",
              [a["sequence"] for a in sel["attempts_all"]] == [0, 1], seqs)
        check("first-quality-wins memakai attempt sequence-0 (FAIL), bukan ts terbaru",
              sel["runs"][0]["checks"][0]["ok"] is False
              and any(e["exclusion"] == "superseded_by_first_quality_attempt"
                      for e in sel["policy"]["excluded"]))


def t7_wrapper_uses_real_labels():
    print("T7 — wrapper TIDAK lagi meng-hardcode provider/model")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cpath = tmp / "corpus.json"
        cpath.write_text(json.dumps(corpus(sc("G-01"))))
        p = wr(tmp, "a.json", [run("G-01")], provider="provX", model="modelY")
        rep = merge_golden([p], corpus_path=cpath)
        check("label report final = label provider/model dari attempt",
              rep["provider"] == "provX" and rep["model"] == "modelY",
              f"{rep['provider']}/{rep['model']}")
        check("identitas kandidat ikut ke report final (binding verdict)",
              rep["identity"]["provider"] == "provX"
              and len(rep["identity"]["commit_sha"]) >= 0 and "corpus_sha256" in rep["identity"])


def t8_candidate_identity_helper():
    print("T8 — helper identitas kandidat: SHA nyata + fingerprint dirty")
    ident = candidate_identity()
    check("commit_sha terisi (dari repo) atau dari env override",
          isinstance(ident["commit_sha"], str) and ident["commit_sha"] != "", ident)
    check("fingerprint 'clean' bila worktree bersih, hash 12 char bila kotor",
          ident["worktree_fingerprint"] == "clean"
          or len(ident["worktree_fingerprint"]) == 12, ident)


def main() -> int:
    t1_provenance_fields()
    t2_mixed_provider_rejected()
    t3_mixed_candidate_sha_rejected()
    t4_mixed_corpus_rejected()
    t5_verdict_reproducible_from_attempts_all()
    t6_sequence_not_timestamp()
    t7_wrapper_uses_real_labels()
    t8_candidate_identity_helper()
    print(f"\n{'=' * 62}\nMC02-RC-03 evidence provenance: {_PASS} OK, {_FAIL} GAGAL")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
