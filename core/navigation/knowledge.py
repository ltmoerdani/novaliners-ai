"""Knowledge -> Signal: the only generic bridge from a matched rule to a navigation signal.

internal-docs §6.1 — any domain signal reader uses `rule_signal` so that
provenance rules are identical everywhere:

    matched rule + RuleSupport ANCHORED   -> Signal(TRUE, refs = real anchors, basis = satisfied branch,
                                                    assumes = absence conditions relied upon)
    matched rule + RuleSupport UNSUPPORTED -> Signal(None, unsupported=True)    (PROV-04: not fabricated)
    unknown / unmatched rule              -> Signal(None)                      (unknown, not FALSE)

Knowledge does NOT create evidence (KNOW-02): anchors always come from the rule evaluator over the ledger."""

from __future__ import annotations

from collections.abc import Mapping

from core.navigation.contracts import Signal
from core.schema.provenance import RuleSupport


def rule_signal(rule_id: str, support: RuleSupport | list[str] | tuple[str, ...] | None) -> Signal:
    """Signal for `rule:<rule_id>`. `support` may be a list of raw references (old contract); an empty
    list = no basis = unsupported — the reader never fabricates anchors."""
    if support is None:
        return Signal(None)
    if isinstance(support, RuleSupport):
        if support.anchored:
            return Signal(
                True,
                f"rule knowledge {rule_id} aktif, didukung evidence {', '.join(support.refs())}",
                support.refs(),
                {"en": f"Knowledge rule {rule_id} is active and backed by {len(support.refs())} anchor(s)"},
                basis=tuple(b.model_dump() for b in support.branches),
                # absence of record, not proof of absence: recorded so it never shows up as verified
                assumes=tuple(a.model_dump() for a in support.assumptions),
            )
        return Signal(
            None,
            f"rule knowledge {rule_id} matched tetapi basisnya tidak dapat dibentuk: {support.reason}",
            (),
            {"en": f"Knowledge rule {rule_id} matched, but its evidence cannot be shown, so it is not used"},
            unsupported=True,
        )
    refs = tuple(str(r) for r in support)
    if not refs:
        return Signal(
            None,
            f"rule knowledge {rule_id} dilaporkan aktif tanpa evidence",
            (),
            {"en": f"Knowledge rule {rule_id} is reported active without evidence, so it is not used"},
            unsupported=True,
        )
    en = {"en": f"Knowledge rule {rule_id} is active"}
    return Signal(True, f"rule knowledge {rule_id} aktif", refs, en)


def rule_reader_table(rules: Mapping[str, RuleSupport | list[str]] | None) -> dict[str, Signal]:
    """rule_id -> Signal, computed once (readers of the signal just look it up)."""
    return {rid: rule_signal(rid, sup) for rid, sup in (rules or {}).items()}
