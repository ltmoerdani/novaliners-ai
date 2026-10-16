"""MC01-3 (audit CIR-MC01 P0-C) + MC02-RC-03 (provenance): live attempt merger = APPEND-ONLY.

Policy (frozen before use — never silently changed after a run):
- ALL attempts are stored intact in `attempts_all` **including their original results**
  (checks/turns/error) so a verdict is reproducible WITHOUT the source report (RC-03).
- Per-attempt provenance (RC-03): attempt_id, run_id, originating report + SHA-256, `sequence`
  (verified execution order; timestamps are METADATA only, not the ordering source), the report's
  ACTUAL provider+model, corpus version + corpus hash, contract version, candidate-code identity
  (commit SHA + working-tree fingerprint), and the rerun reason (`file::rerun_reason`).
- SELECTION: each (scenario_id, rep) key is represented by the FIRST COMPLETED attempt
  ("first-quality-wins"). Quality reruns MUST NOT replace a completed attempt.
- An `error` attempt NEVER represents a rep when a completed attempt exists; if only error
  attempts exist, that error attempt is selected (the denominator stays honest).
- RC-03: attempts from a DIFFERENT CANDIDATE/PROVIDER/MODEL/CORPUS are REJECTED
  (`MixedCandidateError`) — results of two code revisions must never merge into one PASS.
- `blocked` from the source report propagates EXCEPT where the key now has a completed attempt.
  BLOCKED_EXTERNAL status never disappears silently: every exclusion is recorded with its reason.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


class MixedCandidateError(ValueError):
    """Attempts from different candidates/providers/models/corpora must not merge into one verdict."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def candidate_identity(repo_root: Path | None = None) -> dict:
    """Candidate-code identity: commit SHA + working-tree fingerprint (RC-03).

    `NVL_CANDIDATE_SHA` may override the SHA (e.g. running inside a container without `.git`);
    the dirty fingerprint is still computed from `git status --porcelain` when available."""
    root = repo_root or Path(__file__).resolve().parents[2]

    def _g(*args: str) -> str:
        try:
            return subprocess.run(["git", "--no-pager", *args], cwd=root, capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001 — without git: empty identity, not a crash
            return ""

    sha = os.environ.get("NVL_CANDIDATE_SHA") or _g("rev-parse", "HEAD")
    dirty = _g("status", "--porcelain")
    return {"commit_sha": sha, "worktree_dirty": bool(dirty),
            "worktree_fingerprint": (hashlib.sha256(dirty.encode()).hexdigest()[:12]
                                     if dirty else "clean")}


def load_attempts(file_specs: list[str],
                  corpus_path: Path | None = None) -> tuple[list[dict], list[str]]:
    """Read N reports → provenance-carrying attempts + source `blocked` entries.

    Syntax: `path` or `path::rerun_reason` (the rerun reason is an audit annotation,
    not a selection criterion)."""
    attempts: list[dict] = []
    blocked_src: list[str] = []
    cpath = Path(corpus_path) if corpus_path else None
    corpus_sha = _sha256_file(cpath) if cpath and cpath.exists() else ""
    cand = candidate_identity()
    for spec in file_specs:
        fp_str, _, reason = spec.partition("::")
        fp = Path(fp_str)
        d = json.loads(fp.read_text())
        sha = _sha256_file(fp)
        for i, r in enumerate(d.get("runs") or []):
            a = dict(r)
            a["_attempt"] = {
                "attempt_id": hashlib.sha1(
                    f"{sha}:{i}:{r.get('id')}:{r.get('rep')}".encode()).hexdigest()[:12],
                "run_id": d.get("run_id") or f"{sha}-{i}",
                "source_report": fp.name, "report_sha256": sha,
                "sequence": len(attempts), "ts_wib": d.get("ts_wib", ""),
                "provider": d.get("provider", ""), "model": d.get("model", ""),
                "corpus_version": d.get("corpus", ""), "corpus_sha256": corpus_sha,
                "contract": d.get("contract", ""),
                "thresholds_sha256": hashlib.sha256(
                    json.dumps(d.get("thresholds") or {}, sort_keys=True).encode()).hexdigest()[:12],
                "candidate": d.get("candidate") or cand,
                "rerun_reason": reason or "unspecified",
                "batch_status": d.get("status", ""),
            }
            attempts.append(a)
        blocked_src.extend(d.get("blocked") or [])
    return attempts, blocked_src


def _blocked_key(bid: str) -> tuple[str, int] | None:
    sid, sep, rep = bid.partition("#")
    if not sep or not rep.isdigit():
        return None
    return sid, int(rep)


def select_attempts(attempts: list[dict], blocked_src: list[str]) -> dict:
    """Append-only + first-quality-wins → {runs, attempts_all, blocked_ids, policy, identity}.

    RC-03: rejects (MixedCandidateError) merging attempts from different
    candidate/provider/model/corpus, and keeps each attempt's original result in `attempts_all`
    (verdict reproducible without the source report)."""
    by_key: dict[tuple, list[dict]] = {}
    for a in attempts:
        by_key.setdefault((a.get("id"), a.get("rep")), []).append(a)

    runs: list[dict] = []
    winner_ids: set[str] = set()
    excluded: list[dict] = []
    for key, group in by_key.items():
        completed = [a for a in group if not a.get("error")]
        if completed:
            winner = completed[0]           # FIRST-quality-wins (sequence order)
        else:
            winner = group[0]               # only error attempts → it still represents (honest)
        winner_ids.add(winner["_attempt"]["attempt_id"])
        runs.append({k: v for k, v in winner.items() if k != "_attempt"})
        for a in group:
            if a is winner:
                continue
            excluded.append({
                "attempt_id": a["_attempt"]["attempt_id"], "key": list(key),
                "outcome": "error" if a.get("error") else "completed",
                "exclusion": ("infra_error_excluded" if a.get("error")
                              else "superseded_by_first_quality_attempt"),
                "source_report": a["_attempt"]["source_report"],
                "rerun_reason": a["_attempt"]["rerun_reason"],
                "error": (a.get("error") or "")[:160],
            })

    attempts_all = []
    for a in attempts:
        p = a["_attempt"]
        attempts_all.append({
            "key": [a.get("id"), a.get("rep")],
            "outcome": "error" if a.get("error") else "completed",
            "selected": p["attempt_id"] in winner_ids,
            "exclusion": (None if p["attempt_id"] in winner_ids
                          else next((e["exclusion"] for e in excluded
                                     if e["attempt_id"] == p["attempt_id"]), "not_representative")),
            # RC-03: the attempt's original result (checks/turns/error) → the verdict is
            # reproducible from this final report alone, without the source report file.
            "result": {k: v for k, v in a.items() if k != "_attempt"},
            **p,
        })

    # ── RC-03: a single identity across all SELECTED attempts ──
    ident = {(str(a["_attempt"]["candidate"].get("commit_sha", "")),
              str(a["_attempt"]["candidate"].get("worktree_fingerprint", "")),
              a["_attempt"]["provider"], a["_attempt"]["model"],
              a["_attempt"]["corpus_version"], a["_attempt"]["corpus_sha256"])
             for a in attempts if a["_attempt"]["attempt_id"] in winner_ids}
    if len(ident) > 1:
        raise MixedCandidateError(
            "attempt terpilih berasal dari kandidat/provider/model/korpus BERBEDA — verdict tunggal "
            "ditolak (pisahkan per kandidat): "
            + "; ".join(sorted("|".join(str(x) for x in t) for t in ident)))
    keys = ("commit_sha", "worktree_fingerprint", "provider", "model",
            "corpus_version", "corpus_sha256")
    identity = dict(zip(keys, next(iter(ident)))) if ident else {k: "" for k in keys}

    completed_keys = {(r.get("id"), r.get("rep")) for r in runs if not r.get("error")}
    blocked_ids = sorted({b for b in set(blocked_src)
                          if (k := _blocked_key(b)) is not None and k not in completed_keys})
    policy = {
        "selection": "first-quality-wins",
        "append_only": True,
        "attempts_self_contained": True,
        "identity_binding": "commit_sha+worktree_fingerprint+provider+model+corpus",
        "ordering": "sequence (bukan timestamp)",
        "mixed_candidate": "rejected",
        "error_attempt_represents_only_when_no_completed": True,
        "blocked_propagation": "superseded_by_completed_rerun",
        "source_blocked": sorted(set(blocked_src)),
        "counts": {"attempts_total": len(attempts_all), "selected": len(runs),
                   "excluded": len(excluded)},
        "excluded": excluded,
    }
    return {"runs": runs, "attempts_all": attempts_all, "blocked_ids": blocked_ids,
            "policy": policy, "identity": identity}
