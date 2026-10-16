"""Rule provenance construction — canonical for the question "what evidence makes this rule TRUE?"

internal-docs §6.1. Two match sources, two ways to build a basis, one result
(`RuleSupport`):

  TIER 1 (deterministic) : the satisfied predicate branch + each branch's anchors
                           (`trace_predicate`). The basis is built by the evaluator itself —
                           no guessing.
  TIER 2 (judgment/LLM)  : free citation (`applied_to`) VERIFIED against the ledger and
                           transcript: the evidence id must exist in the ledger; the quote must
                           actually appear (verbatim) in the evidence or transcript. A citation
                           that cannot be verified is not a basis -> `UNSUPPORTED`.

What the engine does NOT do for tier 2: check that the cited evidence actually satisfies the
rule condition — that remains the LLM's judgment. The engine only guarantees that the anchors
are real (KNOW-02: knowledge does not invent evidence).

Evidence `is_gap` (missing/rejected data, not a fact) never becomes an anchor for positive support."""

from __future__ import annotations

import re

from core.schema.evidence import EvidenceItem
from core.schema.provenance import SUPPORTED, UNSUPPORTED, AbsenceAssumption, BranchSupport, RuleSupport

_MIN_FRAGMENT = 8  # a quote shorter than this is too generic to be an auditable anchor
_QUOTED = re.compile(r"[“\"‘']([^”\"’']{%d,})[”\"’']" % _MIN_FRAGMENT)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _dedupe(xs: list[str]) -> list[str]:
    return list(dict.fromkeys(xs))


def _unsupported(
    rule_id: str,
    tier: str,
    reason: str,
    branches: list[BranchSupport] | None = None,
    assumptions: list[AbsenceAssumption] | None = None,
) -> RuleSupport:
    return RuleSupport(
        rule_id=rule_id,
        tier=tier,
        status=UNSUPPORTED,
        branches=branches or [],
        assumptions=assumptions or [],
        reason=reason,
    )


def support_from_branches(
    rule_id: str,
    branches: list[BranchSupport],
    evidence: list[EvidenceItem],
    tier: str = "deterministic",
    *,
    unanchored_required: list[str] | None = None,
    assumptions: list[AbsenceAssumption] | None = None,
) -> RuleSupport:
    """Satisfied branch (tier 1) -> RuleSupport. Anchors are confirmed against the ledger: the id must
    exist and not be a gap. A branch without anchors is still recorded (e.g. an evidence-count
    threshold) but adds no support.

    Per-branch provenance (doc 14 §6.1, P1-1): `unanchored_required` = the name of a POSITIVE
    branch (operator `core.stages.rule_predicates.POSITIVE_OPERATORS`) that is satisfied without a
    single verified anchor. One required branch without anchors DISQUALIFIES the overall support —
    the aggregate `evidence_ids` from sibling branches must not hide it. CONSTRAINT branches
    (`*_absent*`, `none_of`, `min_evidence_count`) never enter this list: they carry no anchors and
    need none (absence of evidence ≠ evidence of absence).

    `assumptions` = absence conditions satisfied because no matching record exists and relied upon
    by the match (`rule_predicates.trace_predicate_audit`): only RECORDED in RuleSupport — they add
    no anchors and do not change SUPPORTED/UNSUPPORTED."""
    ledger = {e.id: e for e in evidence}
    kept: list[BranchSupport] = []
    dropped_gap: list[str] = []
    for b in branches:
        ids = []
        for eid in b.evidence_ids:
            ev = ledger.get(eid)
            if ev is None:
                continue  # an id outside the ledger is not an anchor
            if ev.is_gap:
                dropped_gap.append(eid)
                continue
            ids.append(eid)
        kept.append(b.model_copy(update={"evidence_ids": ids}))
    ev_ids = _dedupe([i for b in kept for i in b.evidence_ids])
    quotes = _dedupe([q for b in kept for q in b.quotes])
    if unanchored_required:
        why = "rule matched tetapi cabang positif wajib tanpa anchor terverifikasi: " + ", ".join(
            unanchored_required
        )
        if dropped_gap:
            why += f" (hanya evidence gap: {', '.join(_dedupe(dropped_gap))} — data hilang bukan dukungan)"
        return _unsupported(rule_id, tier, why, kept, assumptions)
    if not ev_ids and not quotes:
        why = "rule matched tetapi tidak ada anchor evidence/kutipan yang dapat diverifikasi"
        if dropped_gap:
            why += f" (hanya evidence gap: {', '.join(_dedupe(dropped_gap))} — data hilang bukan dukungan)"
        return _unsupported(rule_id, tier, why, kept, assumptions)
    return RuleSupport(
        rule_id=rule_id,
        tier=tier,
        status=SUPPORTED,
        evidence_ids=ev_ids,
        quotes=quotes,
        branches=kept,
        assumptions=list(assumptions or []),
        reason="anchor dibentuk dari cabang predikat yang terpenuhi",
    )


def _fragments(text: str) -> list[str]:
    quoted = _QUOTED.findall(text)
    if quoted:
        return [q.strip() for q in quoted]
    parts = re.split(r"[;|\n]", text)
    return [p.strip(" \t.,:-—«»“”\"'()[]") for p in parts if len(_norm(p)) >= _MIN_FRAGMENT]


def support_from_citation(
    rule_id: str, applied_to: str, evidence: list[EvidenceItem], transcript: str = ""
) -> RuleSupport:
    """Free citation tier 2 -> verified RuleSupport (or UNSUPPORTED). Adds no anchors that the
    citation does not name, does not 'repair' a mismatched citation."""
    ledger = {e.id: e for e in evidence}
    text = applied_to or ""
    cited_ids = [eid for eid in ledger if re.search(rf"(?<![\w-]){re.escape(eid)}(?![\w-])", text)]
    gap_ids = [eid for eid in cited_ids if ledger[eid].is_gap]
    ev_ids = [eid for eid in cited_ids if not ledger[eid].is_gap]

    rest = text
    for eid in cited_ids:
        rest = rest.replace(eid, " ")
    corpus = {e.id: _norm(f"{e.signal or ''} {e.source_quote or ''}") for e in evidence if not e.is_gap}
    tnorm = _norm(transcript)
    quotes: list[str] = []
    unresolved: list[str] = []
    for frag in _fragments(rest):
        n = _norm(frag)
        hit = [eid for eid, body in corpus.items() if n in body]
        if hit:
            ev_ids.extend(hit)
        elif n and n in tnorm:
            quotes.append(frag[:90])
        else:
            unresolved.append(frag[:60])

    ev_ids = _dedupe(ev_ids)
    quotes = _dedupe(quotes)
    branch = BranchSupport(
        branch="judgment", operator="llm_match", operand=[text[:120]], evidence_ids=ev_ids, quotes=quotes
    )
    if not ev_ids and not quotes:
        why = "sitasi tier-2 tidak dapat diverifikasi terhadap ledger maupun transkrip"
        if gap_ids:
            why += f" (hanya evidence gap: {', '.join(gap_ids)})"
        elif unresolved:
            why += f" (kutipan tidak ditemukan: {unresolved[0]!r})"
        return _unsupported(rule_id, "judgment", why, [branch])
    note = "anchor sitasi tier-2 terverifikasi (kecocokan kondisi tetap penilaian LLM)"
    if unresolved:
        note += f"; kutipan tak terverifikasi diabaikan: {len(unresolved)}"
    return RuleSupport(
        rule_id=rule_id,
        tier="judgment",
        status=SUPPORTED,
        evidence_ids=ev_ids,
        quotes=quotes,
        branches=[branch],
        reason=note,
    )

def evidence_quote_corpus(evidence) -> list[str]:
    """Signal/quote normalization for a set of evidence — used for both historical AND current.

    Only fragments >= `_MIN_FRAGMENT`: short generic quotes never become a cleaning key."""
    out: list[str] = []
    for e in evidence or []:
        for t in (getattr(e, "signal", "") or "", getattr(e, "source_quote", "") or ""):
            n = _norm(t)
            if len(n) >= _MIN_FRAGMENT and n not in out:
                out.append(n)
    return out


def historical_quote_corpus(historical_evidence) -> list[str]:
    """Normalization of signals/quotes of claims that were ALREADY replaced (DCP-01, int 16 S1)."""
    return evidence_quote_corpus(historical_evidence)


def strip_fragments(text: str, fragments: list[str]) -> str:
    """Remove fragments (the `_norm` normalized form) from raw text SURGICALLY.

    Fragment tokens are combined into a regex with whitespace tolerance + case-insensitivity; after removal,
    extra whitespace/splits are tidied. NOT a parser — only deterministic substring removal for
    already-known fragments (e.g. historical claims). Non-matching fragments are LEFT as is;
    the caller decides the fallback (14 Oct 2026 audit: a substring may only be an explicit fallback)."""
    out = text
    for f in fragments or []:
        toks = [t for t in (f or "").split() if t]
        if not toks:
            continue
        pat = re.compile(r"\s+".join(re.escape(t) for t in toks), re.IGNORECASE)
        out = pat.sub(" ", out)
    return re.sub(r"\s{2,}", " ", out).strip(" \t,;")


def strip_historical_anchors(support, historical_evidence, current_evidence=None):
    """Remove transcript quotes from historical (superseded) claims from the rule basis.

    DCP-01: the full transcript may be used for context/chronology, but content from a claim that
    was already replaced MUST NOT become an anchor for the CURRENT state. Evidence ids are already
    guarded by the evidence ledger (current-only); here the quote path is what is cleaned. No
    ledger mutation.

    Explicit limitation of substring matching (14 Oct 2026 audit):
      - `nq in h`  — the quote is part of the historical text (purely historical) -> dropped;
      - `h in nq`  — the quote is LONGER and contains a historical fragment = a mixed sentence.
        If that quote also overlaps literally with CURRENT evidence (`current_evidence`),
        it is KEPT (deleting it = losing an active-fact anchor) and the reason is recorded;
        with no overlap at all -> treated as historical content -> dropped.
    """
    corpus = historical_quote_corpus(historical_evidence)
    if not corpus or support is None or not getattr(support, "quotes", None):
        return support
    current_corpus = evidence_quote_corpus(current_evidence) if current_evidence else []
    kept, dropped, mixed = [], 0, 0
    for q in support.quotes:
        nq = _norm(q)
        pure_hist = any(nq in h for h in corpus)
        contains_hist = any(h in nq for h in corpus)
        if not pure_hist and not contains_hist:
            kept.append(q)
            continue
        if not pure_hist and current_corpus and any(c in nq for c in current_corpus):
            kept.append(q)  # a mixed sentence carries current facts — active anchors are not dropped
            mixed += 1
            continue
        dropped += 1
    if not dropped and not mixed:
        return support
    note = ""
    if dropped:
        note += f" | {dropped} kutipan historis (klaim digantikan) diabaikan sebagai anchor saat ini"
    if mixed:
        note += (f" | {mixed} kutipan campuran (historis + fakta saat ini) DIPERTAHANKAN karena "
                 "beririsan literal dengan evidence saat ini")
    if not support.evidence_ids and not kept:
        return support.model_copy(
            update={"status": UNSUPPORTED, "quotes": [], "reason": support.reason + note}
        )
    return support.model_copy(update={"quotes": kept, "reason": support.reason + note})
