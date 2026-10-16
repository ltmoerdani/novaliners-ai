"""Semantic mapper: UniversalClaim (dict from the graph) → revenue role / signal.

Deterministic. Only three outputs:
- numeric role (current_revenue / target / client_rate / historical_revenue)
- operational signal (founder_dependency, operational_load) — WITHOUT a diagnosis name
- desire (forwarded as a motivation signal, without interpretation)

Match sources: raw predicate label + subject label. Nodes from the M1 mapper
(predicate `has_<old_role>`) and from universal understanding (predicate
'currently'/'was'/'wants' etc.) are both mapped here — this plugin is
the only place that knows the meaning of both."""
from __future__ import annotations

import re

# subjects commonly meaning revenue in everyday user language
_REVENUE_SUBJECTS = re.compile(
    r"omzet|omz(e|é)t|revenue|pendapatan|penghasilan|income|sales|penjualan|cash ?flow", re.I
)
_TARGET_HINTS = re.compile(r"target|ingin|mau|pengen|want|goal|goal_revenue|aim", re.I)
_CLIENT_SUBJECTS = re.compile(r"klien|client|customer|pelanggan|retainer", re.I)
_FOUNDER_HINTS = re.compile(
    r"passes_through|handle|sendiri|lewat saya|saya sendiri|founder|owner|solo", re.I
)
_LOAD_HINTS = re.compile(r"makin_banyak|increasing|nambah|menumpuk|meningkat", re.I)
_RATE_HINTS = re.compile(r"bayar|bayar|pay|retainer|harga|fee|per bulan|per_bulan|monthly", re.I)


# R4-C: PERSONAL income (salary/take-home) is not BUSINESS turnover/revenue. Only explicit markers are
# used; a bare "penghasilan"/"income" stays ambiguous and is mapped as before (freelancer: personal =
# business). Do not guess beyond the markers.
_PERSONAL_INCOME = re.compile(
    r"\bgaji\b|\bsalary\b|take[- ]?home|penghasilan pribadi|personal income|uang saku|gaji pokok", re.I)

# A quantity that binds only a point may become a numeric field; ranges & bounds may NOT
# (R4-C: a bound/range must not become an exact number).
_POINT_KINDS = ("exact", "approximate")


def is_personal_income(subject: str, verbatim: str = "") -> bool:
    return bool(_PERSONAL_INCOME.search(subject or "") or _PERSONAL_INCOME.search(verbatim or ""))


def _revenue_role_hint(subj: str, ctype: str, tense: str, pred: str) -> str:
    """The revenue role that WILL be mapped for this subject/tense (used to report withheld material)."""
    if _TARGET_HINTS.search(pred) or (ctype in ("goal",) and tense == "future"):
        return "target"
    return "historical_revenue" if tense == "past" else "current_revenue"


def map_claim(node: dict) -> dict | None:
    """Return mapping {kind, role?, signal?, node_id, value?, tense} or None
    when the node is not the revenue domain's business (e.g. a non-business career desire).

    R4-C: only ACTIVE claims are mapped (a replaced/negated claim is not restored);
    mapping `kind="withheld"` reports WHY a number is not projected (range/bound,
    personal income) — a visible loss, not an invented value."""
    if (node.get("status") or "active") != "active":
        return None
    t = node.get("triple") or {}
    subj = (t.get("subject") or {}).get("label") or ""
    pred = (t.get("predicate") or {}).get("label") or ""
    value = t.get("value")
    tense = node.get("tense") or "now"
    ctype = node.get("type") or "claim"
    q = node.get("quantity")
    if isinstance(q, dict) and q.get("value_kind") not in _POINT_KINDS and (
            q.get("value") is not None or q.get("low") is not None or q.get("high") is not None):
        if _REVENUE_SUBJECTS.search(subj) or ctype == "goal":
            return {"kind": "withheld", "reason": f"quantity_{q.get('value_kind')}_not_point",
                    "role": _revenue_role_hint(subj, ctype, tense, pred), "node_id": node.get("id")}
        value = None
    if (value is not None and _REVENUE_SUBJECTS.search(subj)
            and is_personal_income(subj, node.get("verbatim") or "")):
        return {"kind": "withheld", "reason": "personal_income_not_business_revenue",
                "role": _revenue_role_hint(subj, ctype, tense, pred), "node_id": node.get("id")}
    precision = "approximate" if (isinstance(q, dict) and q.get("value_kind") == "approximate") or \
        node.get("hedge") else "exact"
    epistemic = node.get("epistemic") or "reported"

    # ── numeric role ────────────────────────────────────────────────────────
    # 1) node from the M1 mapper: predicate 'has_current_revenue' etc.
    m = re.match(r"has_(current_revenue|target|client_rate|historical_client_rate|"
                 r"rejected_price|ask_price|lead_count)", pred)
    if m:
        role = m.group(1)
        if role == "historical_client_rate":
            role = "historical_revenue_rate"
        return {"kind": "role", "role": role, "value": value, "tense": tense,
                "node_id": node.get("id"), "precision": precision, "epistemic": epistemic}
    # 2) universal understanding node: revenue-nuanced subject + number
    if value is not None and _REVENUE_SUBJECTS.search(subj):
        if _TARGET_HINTS.search(pred) or ctype in ("goal",) and tense == "future":
            role = "target"
        elif tense == "past":
            role = "historical_revenue"
        else:
            role = "current_revenue"
        return {"kind": "role", "role": role, "value": value, "tense": tense,
                "node_id": node.get("id"), "precision": precision, "epistemic": epistemic}
    # 2b) client/customer with a value → client_rate ONLY when the predicate
    # rate-nuanced (bayar/pay/retainer/harga/fee); otherwise = count.
    # (live M3 test: 'klien aktif | punya = 3' was once wrongly mapped to client_rate)
    if value is not None and _CLIENT_SUBJECTS.search(subj) and tense != "future":
        if _RATE_HINTS.search(pred):
            return {"kind": "role", "role": "client_rate", "value": value,
                    "tense": tense, "node_id": node.get("id")}
        return {"kind": "role", "role": "client_count", "value": value,
                "tense": tense, "node_id": node.get("id")}

    # ── operational signals (SEMANTIC, not diagnosis) ──────────────────────
    if _FOUNDER_HINTS.search(pred) or _FOUNDER_HINTS.search(subj):
        signal = "founder_dependency"
        if _LOAD_HINTS.search(pred):
            signal = "operational_load_increase"
        return {"kind": "signal", "signal": signal, "node_id": node.get("id"),
                "verbatim": node.get("verbatim")}
    if _LOAD_HINTS.search(pred):
        return {"kind": "signal", "signal": "operational_load_increase",
                "node_id": node.get("id"), "verbatim": node.get("verbatim")}

    # ── desire (motivasi — diteruskan mentah) ───────────────────────────────
    if ctype in ("desire", "goal"):
        return {"kind": "desire", "subject": subj, "predicate": pred,
                "object": (t.get("object") or {}).get("label"),
                "node_id": node.get("id"), "verbatim": node.get("verbatim")}

    # other clients/non-numeric: not yet mapped in M3 (record the loss in view.loss)
    return None
