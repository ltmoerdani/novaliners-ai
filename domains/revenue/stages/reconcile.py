"""Stage: G1 reconciliation (internal-docs §7)."""
from __future__ import annotations

from domains.revenue.stages.extract import _extract_rp, _extract_rp_all, _monthly_rp_values  # noqa: F401

_RECON_TOLERANCE = 1.0  # million IDR — a difference ≤ tolerance counts as rounding, not a mismatch


def reconcile(
    declared: float | None,
    computed: float | None,
    components_exhaustive: bool = True,
) -> tuple[float | None, str, float | None]:
    """Generic Evidence Reconciliation (G1).
    Return: (value_used, status, discrepancy).
    Golden rule: declared = source of truth; computed = independent verification signal.
    - VERIFIED : declared ≈ computed → value used without a note
    - MISMATCH : both present, difference > tolerance → declared used + FLAG
    - PARTIAL  : components only (and the components are known NOT exhaustive) → the sum
                 is used as a lower-bound computed, NOT as the total
    - UNKNOWN  : not enough data"""
    if declared is not None and computed is not None:
        diff = round(abs(declared - computed), 1)
        if diff <= _RECON_TOLERANCE:
            return declared, "VERIFIED", None
        return declared, "MISMATCH", diff
    if declared is not None:
        return declared, ("VERIFIED" if components_exhaustive else "PARTIAL"), None
    if computed is not None:
        # Level A guard (bug G7 21:30): a SUM of components WITHOUT declared must not be
        # VERIFIED — a component may contain a restated total (ev-goal-001
        # 'Rp30jt/bulan ... per klien' was summed too → current=60, gap lost).
        # PARTIAL = lower-bound computed, NOT total (per the docstring above).
        return computed, "PARTIAL", None
    return None, "UNKNOWN", None



