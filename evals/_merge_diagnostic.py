"""Merge N diagnostic runner reports (parallel runs/reruns) into ONE final report.

MC01-3: APPEND-ONLY — all attempts + provenance are kept (`attempts_all`); selection
= first-quality-wins (a quality rerun does NOT replace a completed attempt); an error
attempt never represents a rep when a completed attempt exists; source `blocked`
entries propagate except when already superseded by a completed rerun.

Usage: .venv/bin/python evals/_merge_diagnostic.py diagA.json [diagB.json::rerun_reason ...]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals._merge_attempts import MixedCandidateError, load_attempts, select_attempts  # noqa: E402
from evals.run_live_diagnostic import aggregate  # noqa: E402

CORPUS_PATH = Path("evals/diagnostic/corpus_v2.json")


def merge(file_specs: list[str], corpus_path: Path | None = None) -> dict:
    """Merge reports → the final report dict (WITHOUT writing files; the caller writes)."""
    attempts, blocked_src = load_attempts(file_specs, corpus_path or CORPUS_PATH)
    sel = select_attempts(attempts, blocked_src)
    runs = sel["runs"]
    corpus = json.loads((corpus_path or CORPUS_PATH).read_text())
    report = aggregate(runs, corpus, only=None, blocked_ids=sel["blocked_ids"])
    return {"status": report["status"], "ts_wib": time.strftime("%Y-%m-%d %H:%M:%S"),
            # RC-03: the real identity of the selected attempts (no hardcoded labels)
            "provider": sel["identity"]["provider"], "model": sel["identity"]["model"],
            "identity": sel["identity"], "corpus": corpus.get("corpus_version"),
            "acceptance": report.get("acceptance"),
            "aggregate": report, "runs": runs,
            "attempts_all": sel["attempts_all"], "attempts_policy": sel["policy"]}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("pemakaian: _merge_diagnostic.py diagA.json [diagB.json::alasan_rerun ...]")
        return 2
    try:
        rep = merge(argv[1:])
    except MixedCandidateError as exc:
        print("DITOLAK — attempt dari kandidat berbeda tidak boleh disatukan:\n ", exc)
        return 3
    out = Path("traces/live") / f"diagnostic-merged-{int(time.time())}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    pol = rep["attempts_policy"]["counts"]
    print(f"attempt total={pol['attempts_total']} terpilih={pol['selected']} "
          f"dikecualikan={pol['excluded']} blocked={len(rep['aggregate'].get('blocked') or [])}")
    print("status:", rep["aggregate"].get("status"), "| reasons:",
          str(rep["aggregate"].get("reasons"))[:300])
    print("merged ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
