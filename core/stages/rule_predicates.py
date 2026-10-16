"""Tier-1 predicate evaluator — T1 (internal-docs §8.4).

Promulgation principle (arXiv 2608.15147): *duties that can be established → rule
engine; judgment that cannot be reduced → LLM*. Rules whose conditions can be
stated as structured predicates over the evidence ledger are evaluated here
— 0 LLM, deterministic, mandatory citation.

Declarations live in the KB (`evaluation.tier == "deterministic"` + `evaluation.predicate`),
not in Python code. Adding/changing a rule = editing JSON, not the engine.

Supported operators:
  all_of / any_of / none_of                → list[condition] (Boolean)
  text_contains_any / text_contains_all    → list[str] (substring, case-insensitive)
  text_present_pattern / text_absent_pattern → regex
  evidence_level_present / evidence_level_absent → list[level]
  min_evidence_count                       → int (non-gap)

Haystack = evidence.signal + evidence.source_quote + transcript tail.
The transcript is read too, because many book conditions talk about what the
user SAID, which is not always extracted into an evidence item.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from core.schema.evidence import EvidenceItem
from core.schema.provenance import TRANSCRIPT_PREFIX, AbsenceAssumption, BranchSupport

TRANSCRIPT_ID = "__transcript__"


# Operators known to `_eval_condition`. ALSO used by the validator (authoring time,
# validate_knowledge.py) so an operator typo does not end up as a caught ValueError
# → "predicate error" → silently never matching.
OPERATORS: frozenset[str] = frozenset({
    "all_of", "any_of", "none_of",
    "text_contains_any", "text_contains_all",
    "text_present_pattern", "text_absent_pattern",
    "evidence_level_present", "evidence_level_absent",
    "min_evidence_count",
})

# Two semantic classes of operator (doc 14 §6.1, per-branch provenance):
#   POSITIVE  — answers "WHAT exists" → a satisfied branch MUST carry a verified
#               anchor (non-gap evidence in the ledger, or a transcript quote).
#   CONSTRAINT — answers "WHAT must NOT exist" / a count threshold → valid as
#               an all_of/any_of clause, but by nature it does NOT carry and does NOT need
#               a positive anchor (absence of evidence ≠ evidence of absence; a
#               negative claim without a reference cannot be audited — T3).
# Distinguishing them prevents aggregate provenance from hiding unanchored required
# branches: a satisfied `text_absent_pattern` indeed cannot be cited, but a `text_contains_any`
# without an anchor must also not pass just because its sibling branch is anchored.
#
# ABSENCE CONTRACT (Task F, doc 14 §6.1) — one rule, three layers:
#   1. Absence operators (`ABSENCE_OPERATORS`: none_of, text_absent_pattern, evidence_level_absent)
#      "satisfied" = NO matching record on the inspected ledger + transcript. That is absence of
#      RECORD, not proof that it did not happen. It never carries an anchor and never
#      makes a rule matched on its own (mandatory citation, T3).
#   2. Every satisfied absence condition RELIED UPON by a match is recorded as an
#      `AbsenceAssumption` (RuleSupport.assumptions) — an anchored positive claim must not silently
#      appear as if that absence were verified.
#   3. Actual PROOF of absence can only be a POSITIVE branch quoting evidence/a quote that
#      STATES the absence (e.g. text_contains_any ["belum pernah refund"]) — anchored like any
#      other positive branch; is_gap evidence (missing data) never proves absence.
POSITIVE_OPERATORS: frozenset[str] = frozenset({
    "text_contains_any", "text_contains_all",
    "text_present_pattern", "evidence_level_present",
})
ABSENCE_OPERATORS: frozenset[str] = frozenset({
    "none_of", "text_absent_pattern", "evidence_level_absent",
})

# Leaf dispatch order in `_eval_condition` (the source if-chain order). `_trace` uses the
# same order when labeling branches: on a broken multi-operator node (the authoring validator
# rejects it, but the trace also runs at runtime), the operator label must be the operator
# ACTUALLY evaluated — not merely the dict's first key (this iteration's audit).
_LEAF_PRIORITY: tuple[str, ...] = (
    "text_contains_any", "text_contains_all", "text_present_pattern",
    "text_absent_pattern", "evidence_level_present", "evidence_level_absent",
    "min_evidence_count",
)


def _build_items(
    evidence: list[EvidenceItem], transcript_tail: str
) -> list[tuple[str, str, Optional[EvidenceItem]]]:
    items: list[tuple[str, str, Optional[EvidenceItem]]] = []
    for e in evidence:
        text = f"{e.signal or ''} {e.source_quote or ''}".strip()
        items.append((e.id, text, e))
    if transcript_tail:
        items.append((TRANSCRIPT_ID, transcript_tail, None))
    return items


def _cite(items: list[tuple[str, str, Optional[EvidenceItem]]], predicate) -> list[str]:
    """Citations satisfying the predicate.

    Priority: non-gap evidence → gap evidence → **transcript quote**.
    The transcript is cited too, because a fact may live in what the user said
    without being extracted into an evidence item. Without this, a tier-1 rule
    whose condition is only satisfied in the transcript would be rejected as
    "uncited" — a misleading false negative (proven on VP-R06).

    Transcript citations use the form `transcript:"<quote>"` so they remain
    auditable, and are NOT used for INFER (which needs evidence ids).
    """
    primary: list[str] = []
    fallback: list[str] = []
    transcript_hits: list[str] = []
    for eid, text, ev in items:
        if eid == TRANSCRIPT_ID:
            for seg in re.split(r"(?<=[.!?])\s+|\n", text):
                seg = seg.strip()
                if not seg:
                    continue
                try:
                    hit = bool(predicate(seg))
                except Exception:
                    hit = False
                if hit:
                    transcript_hits.append(seg[:90])
            continue
        try:
            hit = bool(predicate(text))
        except Exception:
            hit = False
        if not hit:
            continue
        if ev is not None and getattr(ev, "is_gap", False):
            fallback.append(eid)
        else:
            primary.append(eid)
    if primary or fallback:
        return primary or fallback
    return [f'transcript:"{h}"' for h in transcript_hits[:2]]


# --- B1 NEGATION (D3 int 08 §8.4, 27 Sep) --------------------------------
# A needle preceded by a negation marker in the same clause does NOT count
# as a match: "saya tidak pakai website" is not evidence of "website". Opt-in via
# `negation_aware=True` — the route/mapper/adjudicator paths enable it;
# the old diagnosis engine (knowledge_rules/confidence) keeps the old default
# so the golden characterization does not silently shift.
# A needle that CONTAINS its own negator ("belum konkret", "tanpa baseline")
# stays literal. Regex patterns (`text_*_pattern`) are untouched — explicit
# authoring belongs to the predicate writer.
_NEGATORS = frozenset({
    "tidak", "tak", "belum", "tanpa", "bukan", "gak", "ga", "nggak",
    "enggak", "ndak", "not", "no", "never", "without", "dont", "don't",
    "doesnt", "doesn't", "isnt", "isn't",
})
_CLAUSE_BREAK = re.compile(r"[.,;:!?\n]|\b(tapi|tetapi|namun|but|however)\b",
                           re.I)
_NEG_WINDOW = 3  # number of words before the needle that are checked


def _needle_affirmed(text: str, needle: str) -> bool:
    """True when there EXISTS a needle occurrence outside negation scope
    (a negator <= _NEG_WINDOW words before it, same clause)."""
    low = text.lower()
    n = needle.lower()
    if not n:
        return False
    first = n.split()[0] if n.split() else ""
    if first in _NEGATORS:
        return n in low  # the needle contains its own negator: literal
    start = 0
    while True:
        i = low.find(n, start)
        if i < 0:
            return False
        before = low[:i]
        brk = None
        for m in _CLAUSE_BREAK.finditer(before):
            brk = m
        clause = before[brk.end():] if brk else before
        words = re.findall(r"[a-z']+", clause)[-_NEG_WINDOW:]
        if not any(w in _NEGATORS for w in words):
            return True
        start = i + 1


def _contains(text: str, needle: str, negation_aware: bool) -> bool:
    if negation_aware:
        return _needle_affirmed(text, needle)
    return needle.lower() in text.lower()


def _eval_condition(
    cond: dict[str, Any],
    items: list[tuple[str, str, Optional[EvidenceItem]]],
    evidence: list[EvidenceItem],
    negation_aware: bool = False,
) -> tuple[bool, list[str]]:
    """Return (matched, cited_evidence_ids)."""
    if "all_of" in cond:
        cited: list[str] = []
        for sub in cond["all_of"]:
            ok, c = _eval_condition(sub, items, evidence, negation_aware)
            if not ok:
                return False, []
            cited.extend(x for x in c if x not in cited)
        return True, cited

    if "any_of" in cond:
        satisfied = False
        for sub in cond["any_of"]:
            ok, c = _eval_condition(sub, items, evidence, negation_aware)
            if ok:
                satisfied = True
                if c:
                    # the citation is taken from the FIRST satisfied child that carries citations: the result
                    # must not depend on child order. A constraint child satisfied earlier (none_of,
                    # *_absent, min_evidence_count — no citations by nature) must not mask a positive
                    # child anchored behind it (the trace records ALL satisfied children; the evaluator
                    # must agree).
                    return True, c
        return satisfied, []

    if "none_of" in cond:
        for sub in cond["none_of"]:
            ok, _ = _eval_condition(sub, items, evidence, negation_aware)
            if ok:
                return False, []
        return True, []

    if "text_contains_any" in cond:
        needles = [str(n).lower() for n in cond["text_contains_any"]]
        cited = _cite(items, lambda t: any(
            _contains(t, n, negation_aware) for n in needles))
        return bool(cited), cited

    if "text_contains_all" in cond:
        needles = [str(n).lower() for n in cond["text_contains_all"]]

        def _all_in(t: str) -> bool:
            return all(_contains(t, n, negation_aware) for n in needles)

        cited = _cite(items, _all_in)
        return bool(cited), cited

    if "text_present_pattern" in cond:
        rx = re.compile(cond["text_present_pattern"], re.I)
        cited = _cite(items, lambda t: bool(rx.search(t)))
        return bool(cited), cited

    if "text_absent_pattern" in cond:
        rx = re.compile(cond["text_absent_pattern"], re.I)
        found = any(rx.search(t) for _, t, _ in items)
        return (not found), []

    if "evidence_level_present" in cond:
        levels = set(cond["evidence_level_present"])
        hit = [e for e in evidence if e.level in levels and not e.is_gap]
        return bool(hit), [e.id for e in hit]

    if "evidence_level_absent" in cond:
        levels = set(cond["evidence_level_absent"])
        hit = [e for e in evidence if e.level in levels and not e.is_gap]
        return (not hit), []

    if "min_evidence_count" in cond:
        n = sum(1 for e in evidence if not e.is_gap)
        return n >= int(cond["min_evidence_count"]), []

    raise ValueError(
        f"operator predicate tidak dikenal: {sorted(set(cond) - OPERATORS) or sorted(cond)}"
    )


def evaluate_predicate(
    predicate: dict[str, Any],
    evidence: list[EvidenceItem],
    transcript_tail: str = "",
    *,
    negation_aware: bool = False,
) -> tuple[bool, list[str], str]:
    """Evaluate a tier-1 predicate. Return (matched, cited_ids, reason).

    `negation_aware=True` (B1): a `text_contains_*` needle inside negation scope
    in the same clause does not count as a match (see `_needle_affirmed`).

    **Mandatory citation**: a satisfied predicate with not a single referenceable
    evidence item is REJECTED. The consequence: predicates that are entirely
    negative (only `*_absent` / `none_of` / `evidence_level_absent`) cannot
    pass — and that is deliberate: a negative claim without a reference is not
    auditable. The KB validator rejects such predicates at authoring time
    (see `validate_knowledge.py`) so the failure surfaces early.
    """
    items = _build_items(evidence, transcript_tail)
    try:
        matched, cited = _eval_condition(predicate, items, evidence,
                                         negation_aware)
    except Exception as exc:  # broken predicate → NEVER silently false
        return False, [], f"predicate error: {type(exc).__name__}: {exc}"
    if matched and not cited:
        # mandatory citation (T3): a match without evidence cannot be audited → treat as no match
        return False, [], "matched tanpa sitasi evidence — ditolak (citation required)"
    reason = "predicate terpenuhi" if matched else "predicate tidak terpenuhi"
    return matched, cited, reason


def _split_cites(cited: list[str]) -> tuple[list[str], list[str]]:
    """(evidence ids, transcript quotes) from `_cite` output — quotes look like `transcript:"<text>"`."""
    ids: list[str] = []
    quotes: list[str] = []
    for c in cited:
        if c.startswith(TRANSCRIPT_PREFIX):
            q = c[len(TRANSCRIPT_PREFIX):].strip()
            quotes.append(q[1:-1] if len(q) >= 2 and q[0] == q[-1] == '"' else q)
        else:
            ids.append(c)
    return ids, quotes


def _operand_summary(op: str, operand: Any) -> list[str]:
    if isinstance(operand, list):
        return [str(x) for x in operand]
    return [str(operand)]


def _cond_summary(cond: Any) -> str:
    """One condition -> a compact audit string, e.g. `text_contains_any(refund)`. Read-only —
    never used for logic."""
    if not isinstance(cond, dict) or not cond:
        return str(cond)
    op = next((k for k in _LEAF_PRIORITY if k in cond), next(iter(cond)))
    arg = cond[op]
    if isinstance(arg, list) and arg and all(isinstance(a, dict) for a in arg):
        inner = ", ".join(_cond_summary(a) for a in arg)
    else:
        inner = ", ".join(_operand_summary(op, arg))
    return f"{op}({inner})"


def _carries_anchor(branches: list[BranchSupport]) -> bool:
    return any(b.evidence_ids or b.quotes for b in branches)


def _trace(
    cond: dict[str, Any],
    items: list[tuple[str, str, Optional[EvidenceItem]]],
    evidence: list[EvidenceItem],
    negation_aware: bool,
    path: str,
    ledger: dict[str, EvidenceItem],
) -> tuple[bool, list[BranchSupport], list[str], list[AbsenceAssumption]]:
    """(satisfied?, leaf branches that SUPPORT that result, required positive branches WITHOUT a verified
    anchor, absence assumptions RELIED UPON by that result).

    Leaves are evaluated by the same `_eval_condition` as the plain evaluator — there is no second semantics;
    what is new is only the recording of contributing branches and their anchor completeness (doc 14 §6.1).

      all_of  : satisfied when all children are satisfied; support = the union of all children's support;
                ANCHORED when ALL children are anchored (one unanchored positive branch defeats it)
      any_of  : satisfied when some child is satisfied; support = ONLY the children actually satisfied;
                anchored when >=1 satisfied child is anchored
      none_of : satisfied when no child is satisfied; the negation carries and needs no positive anchor
      leaf    : support = the anchors the leaf itself cites; a POSITIVE leaf must carry >=1 verified
                anchor (non-gap evidence in the ledger or a transcript quote) — a leaf satisfied only
                through gap evidence lands on the "required without anchor" list

    Return element 3 = the branch name (e.g. `all_of[1].text_contains_any`) that is POSITIVE and satisfied
    but unanchored — the input to the SUPPORTED vs UNSUPPORTED decision in `support_from_branches`.

    Return element 4 = absence conditions (`ABSENCE_OPERATORS`) satisfied because no matching record
    exists AND relied upon by the result (the absence contract above): all_of relies on all children;
    any_of only when no satisfied child carries an anchor (an OR already backed by an anchored branch
    does not rest on the absence of records). Recording only — it does not change satisfied/anchor."""
    if "all_of" in cond:
        out: list[BranchSupport] = []
        un_required: list[str] = []
        assumed: list[AbsenceAssumption] = []
        for i, sub in enumerate(cond["all_of"]):
            ok, br, un, asm = _trace(sub, items, evidence, negation_aware, f"{path}.all_of[{i}]", ledger)
            if not ok:
                return False, [], [], []
            out.extend(br)
            un_required.extend(un)
            assumed.extend(asm)
        return True, out, un_required, assumed
    if "any_of" in cond:
        satisfied = False
        out = []
        un_merged: list[str] = []
        assumed = []
        grounded_child = False
        anchored_child = False
        for i, sub in enumerate(cond["any_of"]):
            ok, br, un, asm = _trace(sub, items, evidence, negation_aware, f"{path}.any_of[{i}]", ledger)
            if ok:
                satisfied = True
                out.extend(br)
                assumed.extend(asm)
                if un:
                    un_merged.extend(un)
                else:
                    grounded_child = True
                    anchored_child = anchored_child or _carries_anchor(br)
        if not satisfied:
            return False, [], [], []
        # The OR is anchored when ANY ONE satisfied child is anchored; other unanchored children remain
        # recorded as branches (audit), but do not defeat the combined support.
        return True, out, [] if grounded_child else un_merged, [] if anchored_child else assumed
    if "none_of" in cond:
        for i, sub in enumerate(cond["none_of"]):
            ok, _, _, _ = _trace(sub, items, evidence, negation_aware, f"{path}.none_of[{i}]", ledger)
            if ok:
                return False, [], [], []
        node = f"{path}.none_of" if path else "none_of"
        absence = AbsenceAssumption(
            branch=node, operator="none_of", operand=[_cond_summary(s) for s in cond["none_of"]]
        )
        return True, [], [], [absence]
    ok, cited = _eval_condition(cond, items, evidence, negation_aware)
    if not ok:
        return False, [], [], []
    op = next((k for k in _LEAF_PRIORITY if k in cond), next(iter(cond)))
    ids, quotes = _split_cites(cited)
    support = BranchSupport(
        branch=f"{path}.{op}" if path else op,
        operator=op,
        operand=_operand_summary(op, cond[op]),
        evidence_ids=ids,
        quotes=quotes,
    )
    if op in POSITIVE_OPERATORS:
        verified = any((ev := ledger.get(i)) is not None and not ev.is_gap for i in ids)
        if not verified and not quotes:
            # a positive leaf "satisfied" only through gap evidence: recorded, but required to count
            # as unanchored — gap evidence is missing data, not a fact about the world (mapper contract).
            return True, [support], [support.branch], []
    absence = (
        [AbsenceAssumption(branch=support.branch, operator=op, operand=support.operand)]
        if op in ABSENCE_OPERATORS
        else []
    )
    return True, [support], [], absence


def trace_predicate_audit(
    predicate: dict[str, Any],
    evidence: list[EvidenceItem],
    transcript_tail: str = "",
    *,
    negation_aware: bool = False,
) -> tuple[bool, list[BranchSupport], list[str], list[AbsenceAssumption]]:
    """`trace_predicate_full` + absence assumptions: (matched, branches, unanchored_required, assumptions).

    `unanchored_required` = the name of a POSITIVE branch satisfied without any verified anchor.
    Empty + >=1 anchored branch -> eligible SUPPORTED; non-empty -> that required branch defeats
    the support (`support_from_branches(..., unanchored_required=...)`).

    `assumptions` = absence conditions satisfied because no matching record exists and relied upon by
    the match (absence contract, module header): recorded so an anchored positive claim does not appear
    as if that absence were verified. Changes neither `matched` nor anchors.

    `matched` is ALWAYS identical to the plain evaluator, INCLUDING the mandatory-citation rejection
    (T3): a state satisfied only by constraint operators (without a single anchored branch) is returned
    as not-satisfied — a satisfied `none_of` never becomes positive support (Task E)."""
    items = _build_items(evidence, transcript_tail)
    try:
        matched, branches, un_required, assumed = _trace(
            predicate, items, evidence, negation_aware, "", {e.id: e for e in evidence}
        )
    except Exception:
        return False, [], [], []
    if matched and not any(b.evidence_ids or b.quotes for b in branches):
        # mirrors `evaluate_predicate` (T3): satisfied without anything citable = rejected. The shell is
        # anchor-aware: a predicate satisfied ONLY through negative/counting operators (`*_absent`,
        # `min_evidence_count` — legitimately valid without per-leaf citations) yields branches with no
        # anchor at all; the plain evaluator rejects it (cited=[]), so the trace must not present it as
        # a matched-with-branches result. The UNSUPPORTED path is unaffected: a positive leaf always
        # carries an evidence id (including gap ids) or a quote, so its branch always passes this check.
        return False, [], [], []
    return matched, branches, un_required, assumed


def trace_predicate_full(
    predicate: dict[str, Any],
    evidence: list[EvidenceItem],
    transcript_tail: str = "",
    *,
    negation_aware: bool = False,
) -> tuple[bool, list[BranchSupport], list[str]]:
    """`trace_predicate` + per-branch provenance completeness: (matched, branches, unanchored_required).
    The 3-tuple shape is kept for old callers; absence assumptions live in `trace_predicate_audit`."""
    matched, branches, un_required, _ = trace_predicate_audit(
        predicate, evidence, transcript_tail, negation_aware=negation_aware
    )
    return matched, branches, un_required


def trace_predicate(
    predicate: dict[str, Any],
    evidence: list[EvidenceItem],
    transcript_tail: str = "",
    *,
    negation_aware: bool = False,
) -> tuple[bool, list[BranchSupport]]:
    """Like `evaluate_predicate`, but returns the satisfied branches with their anchors.

    `matched` is ALWAYS identical to the plain evaluator (property-tested in
    evals/test_knowledge_provenance.py); a broken predicate -> (False, []) — breakage never masquerades
    as support. For per-branch completeness (required branches without anchors) use `trace_predicate_full`."""
    matched, branches, _ = trace_predicate_full(
        predicate, evidence, transcript_tail, negation_aware=negation_aware
    )
    return matched, branches


# ---------------------------------------------------------------------------
# Structural predicate validator (review 640680d BLOCKER-2): lives in the
# PREDICATE ENGINE LAYER — one source; the KB validator (authoring) and the
# mapper gate-2 both use it. Malformed operand/tree = caught BEFORE the evaluator
# (the evaluator swallows ValueError -> False — breakage must NOT masquerade
# as 'not enough evidence').
# ---------------------------------------------------------------------------
_OPERAND_SPEC: dict[str, str] = {
    "all_of": "predicate_list",
    "any_of": "predicate_list",
    "none_of": "predicate_list",
    "text_contains_any": "str_list",
    "text_contains_all": "str_list",
    "text_present_pattern": "regex",
    "text_absent_pattern": "regex",
    "evidence_level_present": "str_list",
    "evidence_level_absent": "str_list",
    "min_evidence_count": "int",
}
_EVIDENCE_LEVELS = frozenset(
    {"transactional", "behavioral", "self_reported", "outcome"})


def validate_predicate_tree(cond: object, where: str = "predicate") -> list[str]:
    """Return a list of structural errors ([] = valid). Checks: known operators,
    operand type per operator (list[str] / regex-str / int / list-of-dict),
    recursively valid combinator children, single-operator node."""
    if not isinstance(cond, dict):
        return [f"{where}: node wajib objek, dapat {type(cond).__name__}"]
    errs: list[str] = []
    unknown = set(cond) - OPERATORS  # review 9ed8d13 point-2: a foreign key
    # at node level = MALFORMED — not ignored just because a valid sibling exists
    if unknown:
        errs.append(f"{where}: key tak dikenal {sorted(unknown)} — node "
                    f"WAJIB hanya operator (single-operator)")
    ops = [k for k in cond if k in OPERATORS]
    if not ops:
        return errs or [f"{where}: operator tak dikenal {sorted(cond)}"]
    if len(ops) > 1:
        errs.append(f"{where}: multi-operator node {sorted(ops)} — satu node "
                    f"WAJIB tepat satu operator")
    for op in ops:
        spec = _OPERAND_SPEC[op]
        v = cond[op]
        if spec == "predicate_list":
            if not isinstance(v, list) or not v:
                errs.append(f"{where}.{op}: operand wajib list non-kosong "
                            f"dari predikat anak")
                continue
            for i, sub in enumerate(v):
                errs.extend(validate_predicate_tree(sub, f"{where}.{op}[{i}]"))
        elif spec == "str_list":
            if not isinstance(v, list) or not v \
                    or not all(isinstance(x, str) and x for x in v):
                errs.append(f"{where}.{op}: operand wajib list non-kosong "
                            f"dari string non-empty")
        elif spec == "regex":
            if not isinstance(v, str) or not v:
                errs.append(f"{where}.{op}: operand wajib string regex "
                            f"non-empty")
            else:
                try:
                    re.compile(v, re.I)
                except re.error as exc:
                    errs.append(f"{where}.{op}: regex invalid ({exc})")
        elif spec == "int":
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                errs.append(f"{where}.{op}: operand wajib integer >= 0")
        if op.startswith("evidence_level_"):
            bad = [x for x in v if x not in _EVIDENCE_LEVELS] \
                if isinstance(v, list) else []
            if bad:
                errs.append(f"{where}.{op}: level tak dikenal {bad} "
                            f"(valid: {sorted(_EVIDENCE_LEVELS)})")
    return errs
