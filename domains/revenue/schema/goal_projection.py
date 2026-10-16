"""Goal projection from CANONICAL CLAIMS (int 16 §R4-B, RC-06) — replaces the semantic authority of
raw-text parsing.

Flow:  active claims in the state graph (the so.v1 output + verifier + commit)  ->  session Goal.

Contracts preserved (no new heuristics):
- DESIRE != TARGET != MOTIVATION. A `desire`-role claim only fills `Goal.desire`; it never
  produces a number, metric, or motivation.
- Target numbers come ONLY from typed `Quantity` values on ACTIVE `goal`-role claims; raw text/
  transcript is never scanned for numbers. Range -> target_min/max; an upper/lower bound -> only
  the stated side; an approximation -> `target_precision="approximate"`. Nothing is fused into an
  exact number.
- METRIC identity (registry/alias lexicon, validation, window, qualification, guardrails) still
  uses the existing registry logic, but only over the verifier-passed QUOTE of the goal claim —
  not the transcript.
- TENTATIVE vs CONFIRMED Goal: a claim-derived target = `intent_phrase` (unconfirmed, GR-05). It
  becomes `explicit_input` only when the user confirms that claim (the commit's `confirms` edge).
  Correcting/replacing a goal claim makes the new target TENTATIVE again (old confirmations are
  not inherited).
- Explicit API input (a target without `target_claim_id`) is never overwritten by claims.
- Personal income (a salary) is never the business's revenue target.
- Idempotent and a pure function of the graph: recomputed from the currently active claims, so a
  replaced claim is never resurrected. The Goal version rises only on material content changes.
"""
from __future__ import annotations

import time
from typing import Any

from core.semantic.derive import _UNIT_TO_JUTA
from domains.revenue.projection.mapper import is_personal_income
from domains.revenue.schema.goal import Goal, parse_goal_text

_ACTIVE = "active"


def _active(nodes: dict, role: str) -> list[dict]:
    return sorted(
        (n for n in nodes.values() if n.get("type") == role and (n.get("status") or _ACTIVE) == _ACTIVE),
        key=lambda n: n.get("id") or "",
    )


def _unit_mult(unit: str | None) -> float | None:
    """Factor-to-juta for known MONEY units. Whole-word matching (not a letter prefix): 'klien' is
    NOT a money unit. Unknown unit → None (no guessing)."""
    u = (unit or "").lower().strip()
    head = u.split("/")[0].split()[0] if u else ""
    return _UNIT_TO_JUTA.get(head) if head in _UNIT_TO_JUTA else None


def _typed_target(q: dict | None, currency: bool) -> dict[str, Any]:
    """Typed Quantity -> {target,target_min,target_max,target_precision}. No meaning inflation."""
    out: dict[str, Any] = {"target": None, "target_min": None, "target_max": None,
                           "target_precision": "exact"}
    if not isinstance(q, dict):
        return out
    mult = _unit_mult(q.get("unit")) if currency else 1.0
    if mult is None:
        return out

    def conv(v):
        return None if v is None else round(float(v) * mult, 3)

    kind = q.get("value_kind")
    if kind in ("exact", "approximate"):
        out["target"] = conv(q.get("value"))
        out["target_precision"] = "approximate" if kind == "approximate" else "exact"
    elif kind == "range":
        out["target_min"], out["target_max"] = conv(q.get("low")), conv(q.get("high"))
        out["target_precision"] = "range"
    elif kind in ("at_most", "less_than"):
        out["target_max"] = conv(q.get("value"))
        out["target_precision"] = "upper_bound"
    elif kind in ("at_least", "greater_than"):
        out["target_min"] = conv(q.get("value"))
        out["target_precision"] = "lower_bound"
    return out


def project_goal(goal: dict | None, graph: dict | None) -> tuple[dict | None, list[str]]:
    """(session goal, canonical graph) -> (new goal, list of changes). Does not mutate its arguments."""
    if not goal or not graph:
        return goal, []
    try:
        g = Goal(**{k: v for k, v in goal.items() if k in Goal.model_fields})
    except Exception:  # noqa: BLE001 - invalid goal: leave it as-is (no fabrication)
        return goal, []
    nodes = graph.get("nodes") or {}
    changes: list[str] = []

    # ── desire: the raw wish. No number/metric/motivation is derived from it. ──
    desires = _active(nodes, "desire")
    if desires and not g.desire:
        g.desire = (desires[-1].get("verbatim") or "").strip()
        changes.append("desire dari klaim kanonik")

    # qualification definitions (count goals) often arrive as a separate claim ("A qualified lead is ...").
    # Read from the verifier-passed QUOTE of the active claim (not the transcript); still tentative.
    # Also when the Goal was typed at creation (no separate goal claim).
    if g.direction == "COUNT_IN_WINDOW" and not g.success_definition:
        from domains.revenue.schema.goal import extract_qualification_definition
        for n in sorted(nodes.values(), key=lambda x: x.get("id") or ""):
            if (n.get("status") or _ACTIVE) != _ACTIVE:
                continue
            qdef = extract_qualification_definition(n.get("verbatim") or "")
            if qdef:
                g.success_definition = qdef
                g.version += 1
                g.notes = list(g.notes) + ["kriteria kualifikasi dari klaim kanonik (tentatif)"]
                changes.append("success_definition dari klaim kanonik")
                break

    # a claim that only CONFIRMS another claim (the `confirms` edge) is not a new goal statement
    confirmers = {e.get("src") for e in (graph.get("edges") or {}).values() if e.get("kind") == "confirms"}
    goal_claims = [n for n in _active(nodes, "goal") if n.get("id") not in confirmers]
    owned = bool(g.target_claim_id)
    if not goal_claims:
        # R4-B/S2-B (int 16): the parser must NOT become a second authority. When the canonical graph
        # holds no active goal claim, a parser-derived target (goal_fallback/goal_marker/intent_phrase)
        # is released.
        # Exception: understanding failed totally (no active claim at all) — the user's input must not
        # vanish; the parser target stays tentative until understanding is available. An explicit_input
        # (API) target is untouched.
        _has_active_any = any((n.get("status") or _ACTIVE) == _ACTIVE for n in nodes.values())
        _parser_target = (
            g.target_origin not in ("explicit_input", "none")
            and any(getattr(g, k) is not None for k in ("target", "target_min", "target_max"))
        )
        # Only a REAL contradiction releases the parser target (not merely "no goal claim"):
        # (a) a weak fallback origin (the first number in the text, not a goal statement), or
        # (b) an active non-goal claim with the SAME number in PAST tense (a historical target).
        # Typed non-revenue Goals from Create Map text (e.g. "3 qualified leads in 14 days") stay intact.
        _contradicted = False
        if _parser_target and not owned and _has_active_any:
            _pnums = {getattr(g, k) for k in ("target", "target_min", "target_max")} - {None}
            if g.target_origin == "goal_fallback":
                _contradicted = True
            else:
                for _n in nodes.values():
                    if (_n.get("status") or _ACTIVE) != _ACTIVE or _n.get("type") == "goal":
                        continue
                    _q = _n.get("quantity") or {}
                    _nnums = {_q.get("value"), _q.get("low"), _q.get("high")} - {None}
                    if _pnums and (_nnums & _pnums) and _n.get("tense") == "past":
                        _contradicted = True
                        break
        if owned or _contradicted:
            g.target = g.target_min = g.target_max = None
            g.target_origin, g.target_claim_id, g.target_precision = "none", "", "exact"
            g.version += 1
            changes.append("tidak ada klaim goal kanonik aktif — target tentatif (parser) dilepas")
        return (g.model_dump() if changes else goal), changes

    claim = goal_claims[-1]  # the latest active goal claim
    verbatim = claim.get("verbatim") or ""
    subj = ((claim.get("triple") or {}).get("subject") or {}).get("label") or ""
    if is_personal_income(subj, verbatim):
        if "penghasilan pribadi bukan target revenue usaha" not in " ".join(g.notes):
            g.notes.append("penghasilan pribadi bukan target revenue usaha — tidak dijadikan target")
            changes.append("target pribadi ditahan")
        return (g.model_dump() if changes else goal), changes

    if g.target is not None and not owned and g.target_origin == "explicit_input":
        return (g.model_dump() if changes else goal), changes  # explicit API input is not overwritten

    q = claim.get("quantity")
    unit = ((q or {}).get("unit") or "") if isinstance(q, dict) else ""
    currency = _unit_mult(unit) is not None

    # metric identity: registry lexicon over the VERIFIED goal claim QUOTE (not the transcript)
    cand = parse_goal_text(verbatim)
    before = g.model_dump()
    if g.metric_id in ("", "revenue_monthly"):
        _default_unit = "Rp juta/bulan"   # legacy model default — not the active Goal semantics
        for f in ("metric", "metric_id", "metric_version", "direction", "category", "unit", "scope",
                  "measurement_window_days", "deadline_days"):
            cur, new = getattr(g, f), getattr(cand, f)
            fillable = cur in (None, "", "revenue_monthly") or (
                f == "unit" and cur == _default_unit and cand.resolved_metric_id() != "revenue_monthly")
            if new and fillable and cur != new:
                setattr(g, f, new)
    if currency and not g.metric_id:
        g.metric_id, g.metric_version, g.category = "revenue_monthly", 1, "revenue"
        g.direction = cand.direction or "INCREASE_TO_THRESHOLD"
    if cand.success_definition and not g.success_definition:
        g.success_definition = cand.success_definition
    if not g.guardrails and cand.guardrails:
        g.guardrails = cand.guardrails
    metric_known = bool(g.resolved_metric_id())

    typed = _typed_target(q, currency=currency or not metric_known)
    if not currency and metric_known and isinstance(q, dict) and g.resolved_metric_id() == "revenue_monthly":
        typed = {"target": None, "target_min": None, "target_max": None, "target_precision": "exact"}
    has_value = any(typed[k] is not None for k in ("target", "target_min", "target_max"))
    if has_value:
        confirmed = bool(claim.get("confirmed_by"))
        new_origin = "explicit_input" if confirmed else "intent_phrase"
        for k in ("target", "target_min", "target_max", "target_precision"):
            setattr(g, k, typed[k])
        g.target_origin = new_origin
        g.target_claim_id = claim.get("id") or ""
    elif owned and g.target_claim_id != (claim.get("id") or ""):
        # a new goal claim without numbers replaces the old target-source claim: do not inherit
        # the old numbers
        g.target = g.target_min = g.target_max = None
        g.target_origin, g.target_claim_id, g.target_precision = "none", "", "exact"

    after = g.model_dump()
    material = {k for k in after if after[k] != before[k]}
    if material - {"notes", "version", "effective_ts"}:
        g.version = int(before.get("version") or 1) + 1
        g.effective_ts = int(time.time())
        g.notes = list(g.notes) + [
            f"goal diproyeksikan dari klaim kanonik {claim.get('id')} "
            f"({'terkonfirmasi' if g.confirmed_target() else 'tentatif'})"]
        meta = {"notes", "version", "effective_ts"}
        changes.append("goal diproyeksikan: " + ",".join(sorted(material - meta)))
    return (g.model_dump() if changes else goal), changes
