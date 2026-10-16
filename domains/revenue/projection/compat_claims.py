"""NumberClaim role mapping from canonical claims — the DOMAIN layer (guard K2: revenue
role vocabulary must not be in core). Used by app/turn.py as the number_role_mapper
for compatibility with legacy RevenueState consumers; the full semantic→requirement bridge
follows in R4 (BC-01)."""
from __future__ import annotations


def revenue_number_role(claim: dict) -> str:
    """NumberClaim role from a canonical claim (tense + semantic role; without guessing)."""
    if claim.get("type") == "goal" or claim.get("tense") == "future":
        return "target"
    if claim.get("tense") == "past":
        return "historical_client_rate"
    subj = (((claim.get("triple") or {}).get("subject") or {}).get("label") or "").lower()
    if any(w in subj for w in ("omzet", "revenue", "income", "pendapatan", "penghasilan", "sales")):
        return "current_revenue"
    return "other"
