"""Stage: decision spectrum (internal-docs §7)."""
from __future__ import annotations

SPECTRUM_ORDER = ["STOP", "NOT_YET", "TEST_FIRST", "GO_SMALL", "PROCEED", "SCALE"]


def decide_spectrum(
    verdict: str | None,
    readiness: dict | None,
    demand_sufficiency: str | None,
    evidence_status: str | None = None,
    capacity_utilization: float | None = None,
) -> dict:
    """Return {level, rationale, evidence_required, next_level}.
    iter-15: CAPACITY BOUNDARY — utilization >80% mengunci level maksimal
    TEST_FIRST. 'A good revenue decision doesn't only ask can this create more
    revenue; it asks can this business absorb the revenue it is trying to
    create.'"""
    r = readiness or {}
    lvl = (verdict or "TEST_FIRST").upper()
    if lvl not in SPECTRUM_ORDER:
        lvl = "TEST_FIRST"
    delivery = r.get("delivery", "UNKNOWN")
    conversion = r.get("conversion", "UNKNOWN")
    # Hard rule: evidence not yet OBSERVED → must not jump to GO_SMALL/PROCEED
    if (
        evidence_status
        and evidence_status != "OBSERVED"
        and SPECTRUM_ORDER.index(lvl) > SPECTRUM_ORDER.index("TEST_FIRST")
    ):
        lvl = "TEST_FIRST"
    if delivery == "NO":
        lvl = min(lvl, "TEST_FIRST", key=lambda x: SPECTRUM_ORDER.index(x))
    capacity_capped = False
    if capacity_utilization is not None and capacity_utilization > 0.8:
        if SPECTRUM_ORDER.index(lvl) > SPECTRUM_ORDER.index("TEST_FIRST"):
            lvl = "TEST_FIRST"
            capacity_capped = True
    req = {
        "STOP": "Satu jalur (channel + ICP + offer) ditulis satu kalimat",
        "NOT_YET": "Syarat area terkait terpenuhi (lihat kontraindikasi)",
        "TEST_FIRST": "Fase 1-2 lulus: price-response diperbaiki, konversi inquiry→deal terukur",
        "GO_SMALL": "≥1 deal closing dari uji volume kecil + bukti berstatus OBSERVED",
        "PROCEED": "Conversion rate stabil ≥2 siklus + delivery capacity terbukti cukup",
        "SCALE": "Semua readiness YES dan funnel tervalidasi pada volume lebih tinggi",
    }.get(lvl, "")
    idx = SPECTRUM_ORDER.index(lvl)
    rationale = (
        f"verdict={verdict or 'TEST_FIRST'} · readiness conversion={conversion}, delivery={delivery} · "
        f"demand sufficiency={demand_sufficiency or 'UNKNOWN'}"
    )
    if delivery == "NO":
        rationale += " · delivery di kapasitas maksimum → level dibatasi TEST_FIRST"
    if capacity_capped:
        rationale += (
            f" · CAPACITY BOUNDARY: delivery {capacity_utilization*100:.0f}% terpakai — "
            f"bisnis belum bisa menyerap volume yang mau diciptakan; "
            f"naik level hanya setelah kapasitas/konversi terjawab"
        )
    return {
        "level": lvl,
        "rationale": rationale,
        "evidence_required": req,
        "next_level": SPECTRUM_ORDER[idx + 1] if idx + 1 < len(SPECTRUM_ORDER) else None,
    }


# Tier-3 #11 (iter-11): canonical funnel (used by NBA/reassess for transition rate).

