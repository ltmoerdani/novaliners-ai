"""Tri-state predicate (Kleene logic) over verified state signals.

Grammar: "<signal id>" | {"all_of": [p, ...]} | {"any_of": [p, ...]} | {"not": p}

  TRUE   = proven; FALSE = proven otherwise; None = not yet known.
  all_of : any FALSE -> FALSE; all TRUE -> TRUE; otherwise None
  any_of : any TRUE -> TRUE; all FALSE -> FALSE; otherwise None
  not    : flips TRUE/FALSE; None stays None

None never becomes FALSE. `support` = list of (signal id, Signal) that SUPPORT a TRUE result — provenance
material: only signals actually evaluated and actually contributing."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.navigation.contracts import Predicate, Signal, SignalReader


@dataclass
class Evaluation:
    value: bool | None
    support: list[tuple[str, Signal]] = field(default_factory=list)  # supporting evidence for a TRUE result
    seen: list[str] = field(default_factory=list)  # all signals read


def signal_ids(pred: Predicate | None) -> list[str]:
    """All signal ids referenced by the predicate (for possibility-space validation)."""
    if pred is None or pred == {}:
        return []
    if isinstance(pred, str):
        return [pred]
    if not isinstance(pred, dict) or len(pred) != 1:
        raise ValueError(f"predikat tidak valid: {pred!r}")
    ((op, arg),) = pred.items()
    if op in ("all_of", "any_of"):
        if not isinstance(arg, list) or not arg:
            raise ValueError(f"{op} butuh list non-kosong: {pred!r}")
        return [sid for p in arg for sid in signal_ids(p)]
    if op == "not":
        return signal_ids(arg)
    raise ValueError(f"operator predikat tidak dikenal: {op!r}")


def evaluate(pred: Predicate | None, reader: SignalReader) -> Evaluation:
    """Empty/None predicate = None (no claim), NOT TRUE: there is no support without basis."""
    if pred is None or pred == {}:
        return Evaluation(None)
    if isinstance(pred, str):
        sig = reader(pred)
        return Evaluation(sig.value, [(pred, sig)] if sig.value is True else [], [pred])
    ((op, arg),) = pred.items()
    if op in ("all_of", "any_of") and not arg:
        # all([]) == True is vacuous truth: with no operands nothing is proven
        raise ValueError(f"{op} tanpa operan bukan predikat yang sah: {pred!r}")
    if op == "not":
        inner = evaluate(arg, reader)
        if inner.value is None:
            return Evaluation(None, [], inner.seen)
        # a TRUE negation is supported by a signal proven FALSE (not by a TRUE signal)
        sup = [(sid, sig) for sid, sig in _falsy_leaves(arg, reader)] if inner.value is False else []
        return Evaluation(not inner.value, sup, inner.seen)
    parts = [evaluate(p, reader) for p in arg]
    seen = [s for e in parts for s in e.seen]
    vals = [e.value for e in parts]
    if op == "all_of":
        if any(v is False for v in vals):
            return Evaluation(False, [], seen)
        if all(v is True for v in vals):
            return Evaluation(True, [s for e in parts for s in e.support], seen)
        return Evaluation(None, [], seen)
    # any_of
    if any(v is True for v in vals):
        return Evaluation(True, [s for e in parts if e.value is True for s in e.support], seen)
    if all(v is False for v in vals):
        return Evaluation(False, [], seen)
    return Evaluation(None, [], seen)


def _falsy_leaves(pred: Predicate, reader: SignalReader) -> list[tuple[str, Signal]]:
    """Leaves proven FALSE inside the predicate (support for `not`)."""
    if isinstance(pred, str):
        sig = reader(pred)
        return [(pred, sig)] if sig.value is False else []
    ((op, arg),) = pred.items()
    if op == "not":
        return []
    return [x for p in arg for x in _falsy_leaves(p, reader)]
