"""F1 (Round 7, D3): referral evidence & CAC baseline reachability.

Previously `state:referral_evidence` / `state:cac_baseline` sat in `_UNMEASURED` -
ALWAYS None (permanent UNKNOWN) even though RevenueState already carried real measurements.
This test guarantees:

1. Reproducer: no measurement -> UNKNOWN (not ABSENT).
2. Real evidence (field + provenance `measured`) -> PRESENT with refs.
3. Absent/unmeasurable NEVER becomes PRESENT; UNKNOWN != ABSENT preserved.
4. Referral: evidence recording 0 measured leads -> ABSENT (measured evidence of absence),
   empty field without measured provenance -> UNKNOWN.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domains.revenue.navigation.signals import RevenueSignals  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402


def _measured_sources(*fields):
    return {
        f: {
            "evidence_id": f"ev-{f}",
            "level": "semantic",
            "derivation": "user_statement",
            "confidence": "measured",
        }
        for f in fields
    }


def test_without_measurement_signals_stay_unknown():
    rs = RevenueState()
    read = RevenueSignals(rs)
    for sid in ("state:referral_evidence", "state:cac_baseline"):
        sig = read(sid)
        assert sig.value is None, f"{sid} harus UNKNOWN tanpa pengukuran, dapat {sig.value}"
        assert sig.reason, f"{sid} harus membawa reason belum-terukur"


def test_referral_evidence_reaches_present_with_provenance():
    rs = RevenueState(referral_leads_recorded=2, sources=_measured_sources("referral_leads_recorded"))
    sig = RevenueSignals(rs)("state:referral_evidence")
    assert sig.value is True
    assert sig.refs == ("ev-referral_leads_recorded",), f"provenance nyata dibutuhkan, dapat {sig.refs}"


def test_referral_zero_measured_is_absent_not_unknown():
    rs = RevenueState(referral_leads_recorded=0, sources=_measured_sources("referral_leads_recorded"))
    sig = RevenueSignals(rs)("state:referral_evidence")
    assert sig.value is False, "0 lead terukur = bukti ketiadaan (ABSENT), bukan UNKNOWN"


def test_referral_number_without_measured_provenance_never_present():
    rs = RevenueState(referral_leads_recorded=3)  # number without measured provenance
    sig = RevenueSignals(rs)("state:referral_evidence")
    assert sig.value is None, "angka tanpa provenance measured tidak boleh PRESENT"


def test_cac_baseline_reaches_present_with_provenance():
    rs = RevenueState(cac_measured=1.5, sources=_measured_sources("cac_measured"))
    sig = RevenueSignals(rs)("state:cac_baseline")
    assert sig.value is True
    assert sig.refs == ("ev-cac_measured",)


def test_cac_without_measurement_never_present():
    for rs in (RevenueState(), RevenueState(cac_measured=1.5)):
        sig = RevenueSignals(rs)("state:cac_baseline")
        assert sig.value is None, "CAC tanpa pengukuran terverifikasi tidak boleh PRESENT"
