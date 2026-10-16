"""Stage: E2 data integrity validation (internal-docs §7)."""
from __future__ import annotations

from core.schema.evidence import EvidenceItem
from domains.revenue.schema.state import RevenueState
from domains.revenue.stages.extract import (
    _extract_rp,
    _is_clean_state_number,
    _is_measured,
)


def validate_state(
    state: RevenueState,
    evidence: list[EvidenceItem],
) -> tuple[float, list[dict]]:
    """Return (confidence penalty, issues). Checks:
    A. Contradiction — explicit user monthly revenue number ≠ current_monthly
    B. Unit/semantic confusion — a weird deal size vs current (clamp triggered)
    C. Unsupported derivation — SUFFICIENT without a measured funnel → downgrade
    D. Confidence leakage — derived/self_reported read as measured
    E. Semantic drift — the current source has upsell/estimation/loss context
    """
    issues: list[dict] = []
    penalty = 0.0
    ev_by_id = {e.id: e for e in evidence}

    # A. Contradiction
    user_numbers = []
    for e in evidence:
        if getattr(e, "is_gap", False) or e.level not in ("transactional", "outcome"):
            continue
        t = f"{(e.signal or '')} {(e.source_quote or '')}".lower()
        if (
            ("bulan" in t or "month" in t) and "per klien" not in t
            and "tahun" not in t and _is_clean_state_number(t)
        ):
            v = _extract_rp(t)
            if v:
                user_numbers.append((v, e.id))
    # D2 (iter-9): an A-contradiction is valid only when there is NO user number candidate
    # matching the state. Bug v5: state 30 was declared contradictory only
    # because the first candidate found was 12 (although 30 was also a user number).
    recon_a = (state.reconciliation or {}).get("current_monthly") or {}
    if state.current_monthly is not None and user_numbers and recon_a.get("status") != "VERIFIED":
        any_match = any(abs(v - state.current_monthly) <= 1.0 for v, _ in user_numbers)
        if not any_match:
            closest = min(user_numbers, key=lambda x: abs(x[0] - state.current_monthly))
            issues.append({"check": "A-contradiction", "severity": "BLOCK",
                           "msg": (
                               f"Angka revenue bulanan user ({closest[0]:.0f} jt, ev {closest[1]}) "
                               f"≠ current_monthly state ({state.current_monthly:.0f} jt) — "
                               f"tidak ada kandidat angka user yang cocok")})
            penalty += 0.10

    # B. Unit confusion (clamp triggered → already noted; verified here)
    if state.avg_deal_size and state.current_monthly and state.avg_deal_size > 0.5 * state.current_monthly:
        issues.append({"check": "B-unit-confusion", "severity": "BLOCK",
                       "msg": (
                           f"avg_deal_size Rp{state.avg_deal_size:.0f} jt > 50% current "
                           f"— unit/semantic suspect")})
        penalty += 0.10

    # C. Unsupported derivation
    if state.demand_sufficiency == "SUFFICIENT":
        measured = any(
            ("konversi" in t or "inquiry" in t) and _is_measured(t) and any(c.isdigit() for c in t)
            for e in evidence if not getattr(e, "is_gap", False) and e.level in ("transactional", "outcome")
            for t in [f"{(e.signal or '')}".lower()]
        )
        if not measured:
            state.demand_sufficiency = "UNKNOWN"
            issues.append({"check": "C-unsupported-derivation", "severity": "FLAG",
                           "msg": "Demand SUFFICIENT tanpa funnel number terukur — diturunkan ke UNKNOWN"})
            penalty += 0.05

    # D. Confidence leakage — a derived field used without a marker
    for field, meta in (state.sources or {}).items():
        if meta.get("confidence") == "derived" and meta.get("used_as_measured"):
            issues.append({"check": "D-confidence-leakage", "severity": "FLAG",
                           "msg": f"{field} derived tapi dibaca sebagai measured"})
            penalty += 0.05

    # E. Semantic drift — the current source turns out to have non-state context
    cm = (state.sources or {}).get("current_monthly") or {}
    src_ev = ev_by_id.get(cm.get("evidence_id") or "")
    if src_ev is not None:
        t = f"{(src_ev.signal or '')}".lower()
        if not _is_clean_state_number(t):
            issues.append({"check": "E-semantic-drift", "severity": "BLOCK",
                           "msg": (
                               f"Sumber current_monthly (ev {src_ev.id}) berkonteks perencanaan/estimasi "
                               f"— angka suspect")})
            penalty += 0.10

    # G1 (iter-9): Reconciliation MISMATCH on current revenue → FLAG/BLOCK
    # (declared is still used — never silently reconciled; materiality
    # = whether the target gap is computed from this number).
    recon = (state.reconciliation or {}).get("current_monthly") or {}
    if recon.get("status") == "MISMATCH":
        material = state.gap_monthly is not None
        issues.append({"check": "G1-reconciliation", "severity": "BLOCK" if material else "FLAG",
                       "msg": (f"Revenue MISMATCH: declared Rp{recon.get('declared', 0):.0f} jt vs computed "
                               f"Rp{recon.get('computed', 0):.0f} jt "
                               f"(selisih Rp{recon.get('discrepancy', 0):.0f} jt) — "
                               f"klarifikasi wajib sebelum angka dipakai untuk kalkulasi target")})
        penalty += 0.10 if material else 0.05

    # D3 (iter-9): dedup penalties per ROOT-CAUSE — A-contradiction and
    # G1-reconciliation are the same root manifestation (reconciliation),
    # do not count them twice (bug v5: confidence 0% from 1 root, 2 BLOCK).
    if (
        any(i["check"] == "A-contradiction" for i in issues)
        and any(i["check"] == "G1-reconciliation" for i in issues)
    ):
        penalty = max(0.0, penalty - 0.10)
        for i in issues:
            if i["check"] == "A-contradiction":
                i["severity"] = "FLAG"
                i["msg"] += " (akar sama dengan G1-reconciliation — satu penalti)"
        issues = [i for i in issues if i["check"] != "A-contradiction"] + [
            i for i in issues if i["check"] == "A-contradiction"
        ]

    return round(min(0.30, penalty), 2), issues



