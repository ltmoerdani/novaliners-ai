"""Stage: causal hypothesis + evidence boundary (internal-docs §7)."""
from __future__ import annotations

import re as _re

from core.schema.constraints import HypothesisState
from core.schema.evidence import EvidenceItem
from core.stages.mechanisms import MECHANISMS
from domains.revenue.schema.state import CausalHypothesis


def build_causal_hypothesis(
    evidence: list[EvidenceItem],
    ranking: list[HypothesisState],
    mechanisms: dict[str, list[str]],
    next_best_action: str,
    primary_id: str,
) -> CausalHypothesis:
    """Evidence Boundary (iter-6 #4/#8): causal claims are tiered deterministically.
    It separates the 'observed leak point' (proven) from the 'proven cause' (not yet).
    A3 (iter-8, fix N1): the dominant mechanism MUST come from the cluster containing
    PRIMARY — the winner and its winning reason must be ontologically connected
    (bug v3: C6.3 won with mechanism Insufficient Pipeline → DS42)."""
    primary_clusters = [mid for mid, spec in MECHANISMS.items() if primary_id in spec["constraints"]]
    # iter-18 (P0 user #2): ATTRIBUTION language = the user claims a cause, not an isolated
    # event. 'lead hilang karena saya telat balas 5 hari' → the event (lead
    # lost) was observed, the cause (late reply) is attribution — Plausible, not isolated.
    _ATTRIBUTION_RE = _re.compile(
        r"\b(karena|menyebabkan|disebabkan|akibat|lantaran|gara-?gara|sehingga|"
        r"caused|because|due to|led to|blamed)\b",
        _re.I,
    )
    # A3: pick the largest mechanism THAT contains primary; fallback: the largest
    # whole (with a mismatch marker in the claim)
    mech_in_cluster = [m for m in mechanisms if m in primary_clusters]
    mismatch = False
    if mech_in_cluster:
        top_mech = max(mech_in_cluster, key=lambda k: len(mechanisms[k]))
    else:
        top_mech = max(mechanisms, key=lambda k: len(mechanisms[k]), default=None)
        mismatch = top_mech is not None
    mech_name = MECHANISMS[top_mech]["name"] if top_mech else "—"
    primary_name = primary_id

    proven, supported, plausible, attributed = [], [], [], []
    for e in evidence:
        if getattr(e, "is_gap", False):
            continue
        if e.level in ("transactional", "outcome"):
            if _ATTRIBUTION_RE.search(e.signal or ""):
                attributed.append(e.signal)
            else:
                proven.append(e.signal)
        elif e.level == "behavioral":
            supported.append(e.signal)
        elif e.level == "self_reported":
            plausible.append(e.signal)
    # iter-18 (P0 user #2): causal status — outcome evidence with attribution language
    # is NOT a 'proven cause', only a 'user-attributed cause'. One lead does not
    # prove a causal mechanism.
    causal_status = "USER_ATTRIBUTED (plausible, not isolated)" if attributed else "OBSERVED_ONLY"

    n_behav = len(supported)
    claim = (
        f"{primary_name} adalah titik kebocoran teramati terkuat saat ini "
        f"(mekanisme dominan: {mech_name}; {n_behav} bukti behavioral konvergen, "
        f"{len(proven)} bukti transaksional/outcome murni)"
    )
    if attributed:
        claim += (
            f"; {len(attributed)} kejadian lain PENYEBABNYA berasal dari atribusi user "
            f"— plausible, not isolated"
        )
    claim += "."
    if mismatch:
        claim += (
            f" ⚠ Catatan: mechanism dengan bukti terbanyak "
            f"({MECHANISMS[top_mech]['name'] if top_mech else '—'}) "
            f"TIDAK ter-cluster dengan {primary_name} — kandidat constraint alternatif yang perlu dipantau."
        )
    unproven = [
        f"Bahwa memperbaiki {mech_name.lower()} AKAN meningkatkan konversi — "
        f"ini hipotesis, hanya bisa dibuktikan lewat eksperimen",
        "Bahwa penyebab akarnya (mis. arsitektur harga vs nilai vs kualifikasi) "
        "— perlu eksperimen disambiguasi",
        # B3: quantified pain ≠ value proof — the hypothesis chain between the pain
        # number and price fit must be tested step by step, not skipped
        "Bahwa pain terkuantifikasi otomatis menjadikan harga layak — "
        "antara angka pain dan price-fit masih ada: attribution, urgency, "
        "otoritas keputusan, alternatif solusi, willingness-to-pay, dan expected outcome",
    ]
    return CausalHypothesis(
        claim=claim,
        observed_mechanism=mech_name,
        proven=proven[:4],
        user_attributed=attributed[:4],
        causal_status=causal_status,
        strongly_supported=supported[:4],
        plausible=plausible[:4],
        still_unproven=unproven,
        diagnostic_test=(next_best_action[:220] + "…") if len(next_best_action) > 220 else next_best_action,
    )


# ---------------------------------------------------------------------------
# Tier-2 #8 (iter-11): Opportunity typing — an active client ≠ a lead.
# expansion (existing client) | recovery (warm, stalled) | reactivation (stalled long)
# ---------------------------------------------------------------------------


