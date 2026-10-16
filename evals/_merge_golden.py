"""Merge N golden runner reports (per-batch parallel runs/reruns) into ONE final report.

MC01-3: APPEND-ONLY — all attempts + provenance are kept (`attempts_all`); aggregation
selection = first-quality-wins (a quality rerun does NOT replace a completed attempt);
an error attempt never represents a rep when a completed attempt exists; source
`blocked` entries propagate except when already superseded by a completed rerun. The
verdict is reproducible from the FULL attempt history, not just the selected last result.

Usage: .venv/bin/python evals/_merge_golden.py reportA.json [reportB.json::rerun_reason ...]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals._merge_attempts import MixedCandidateError, load_attempts, select_attempts  # noqa: E402
from evals.run_live_golden import THRESHOLDS, aggregate  # noqa: E402

CORPUS_PATH = Path("evals/golden/corpus_v1.json")


def merge(file_specs: list[str], corpus_path: Path | None = None) -> dict:
    """Merge reports → the final report dict (WITHOUT writing files; the caller writes)."""
    attempts, blocked_src = load_attempts(file_specs, corpus_path or CORPUS_PATH)
    sel = select_attempts(attempts, blocked_src)
    runs = sel["runs"]
    corpus = json.loads((corpus_path or CORPUS_PATH).read_text())
    turns_all = [t for r in runs for t in r["turns"][1:]]
    acc = [t for t in turns_all if t.get("adaptive")]
    guard_rate = round(sum(1 for t in acc if t["adaptive"] == "ACCEPTED") / len(acc), 3) if acc else None
    report = aggregate(runs, corpus, blocked_ids=sel["blocked_ids"], guard_rate=guard_rate,
                       thresholds=THRESHOLDS)
    return {"status": report["status"], "ts_wib": time.strftime("%Y-%m-%d %H:%M:%S"),
            # RC-03: provider/model/candidate taken from the selected attempts — NOT hardcoded
            "provider": sel["identity"]["provider"], "model": sel["identity"]["model"],
            "identity": sel["identity"], "corpus": corpus["corpus_version"],
            "thresholds": THRESHOLDS, "rates": report["rates"], "verdicts": report["verdicts"],
            "guard_acceptance": report["guard_acceptance"],
            "scenario_pass_rate": report["critical_pass_fraction"],
            "blocked": report["blocked"], "runs": runs,
            "attempts_all": sel["attempts_all"], "attempts_policy": sel["policy"],
            "aggregate": {k: v for k, v in report.items()
                          if k not in ("rates", "verdicts", "guard_acceptance", "blocked")}}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("pemakaian: _merge_golden.py reportA.json [reportB.json::alasan_rerun ...]")
        return 2
    try:
        rep = merge(argv[1:])
    except MixedCandidateError as exc:
        print("DITOLAK — attempt dari kandidat berbeda tidak boleh disatukan:\n ", exc)
        return 3
    out = Path("traces/live") / f"golden-merged-{int(time.time())}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    pol = rep["attempts_policy"]["counts"]
    print(f"attempt total={pol['attempts_total']} terpilih={pol['selected']} "
          f"dikecualikan={pol['excluded']} blocked={len(rep['blocked'])}")
    print(json.dumps({"status": rep["status"], "reasons": rep["aggregate"].get("reasons"),
                      "rates": rep["rates"], "verdicts": rep["verdicts"],
                      "guard_acceptance": rep["guard_acceptance"],
                      "scenario": rep["scenario_pass_rate"]}, ensure_ascii=False, indent=1))
    print("merged ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
