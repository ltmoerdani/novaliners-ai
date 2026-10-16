"""Stage: semantic evidence dedup (internal-docs §7)."""
from __future__ import annotations

from core.schema.evidence import EvidenceItem
from domains.revenue.stages.extract import (
    _extract_rp_all,
)


def deduplicate_evidence(
    evidence: list[EvidenceItem],
) -> tuple[list[EvidenceItem], list[dict]]:
    """iter-14 (P0 user): SEMANTIC evidence dedup — 'recurring revenue Rp30jt'
    appearing 4x with different sentences = 1 independent observation, not 4.
    Evidence Count ≠ Independent Evidence Count. Return:
    (representative_evidence, clusters) where cluster =
    {representative_id, duplicate_ids, n, levels}.
    Rule: two evidence items form one cluster when their set of Rp numbers is equal
    (not both empty) AND token overlap is high (≥0.6 Jaccard) —
    different numbers REMAIN different facts (rule D1).
    Gap evidence is not deduped (they are representations of emptiness)."""
    def _tok(t: str) -> set:
        stop = {"yang", "dan", "di", "ke", "dari", "untuk", "tidak", "ada", "saya", "itu", "dengan",
                "per", "the", "a", "of", "revenue", "pendapatan"}
        return {w for w in (t or "").lower().split() if w not in stop}

    def _jac(a: set, b: set) -> float:
        return len(a & b) / len(a | b) if (a or b) else 0.0

    clusters: list[dict] = []
    reps: list[EvidenceItem] = []
    rep_tok: list[set] = []
    rep_nums: list[frozenset] = []
    for e in evidence:
        if getattr(e, "is_gap", False):
            reps.append(e)
            rep_tok.append(set())
            rep_nums.append(frozenset())
            continue
        nums = frozenset(_extract_rp_all(e.signal or ""))
        toks = _tok(e.signal or "")
        matched = None
        for i, (rt, rn) in enumerate(zip(rep_tok, rep_nums)):
            if e.is_gap or not reps[i] or getattr(reps[i], "is_gap", False):
                continue
            # iter-14 fix: numbers may differ MANY vs ONE when the small set is a subset
            # of the large set (aggregate sentences carry total+components; the
            # duplicate sentence only states the total) — as long as token overlap is enough.
            nums_compatible = True
            thr = 0.6
            if nums and rn and nums != rn:
                if nums <= rn or rn <= nums:
                    thr = 0.3  # number subset + same key-tokens (value/subject) = restatement of the total
                else:
                    nums_compatible = False  # genuinely different numbers = different facts (D1)
            if not nums_compatible:
                continue
            if not nums and not rn:
                continue  # without numbers: too risky (different content) — do not merge
            if _jac(toks, rt) >= thr:
                matched = i
                break
        if matched is None:
            reps.append(e)
            rep_tok.append(toks)
            rep_nums.append(nums)
        else:
            c = (
                clusters[matched]
                if matched < len(clusters)
                and clusters[matched]["representative_id"] == reps[matched].id
                else None
            )
            # temukan/aman-kan cluster dict
            for cc in clusters:
                if cc["representative_id"] == reps[matched].id:
                    c = cc
                    break
            if c is None:
                c = {
                    "representative_id": reps[matched].id,
                    "duplicate_ids": [],
                    "n": 1,
                    "levels": [reps[matched].level],
                }
                clusters.append(c)
            c["duplicate_ids"].append(e.id)
            c["n"] += 1
            if e.level not in c["levels"]:
                c["levels"].append(e.level)
    return reps, clusters


