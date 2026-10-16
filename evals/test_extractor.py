"""E7 (iter-10) — Regression guard for the Revenue State extractor.

Deterministic, no LLM. Run: .venv/bin/python evals/test_extractor.py

Background: a single unit bug in the extractor can poison the whole report
(run v6: "Rp234 ribu per jam" → declared Rp234 juta → confidence 15%).
"""
import sys

sys.path.insert(0, ".")

from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.stages.extract import (  # noqa: E402
    _extract_rp,
    _extract_rp_range_mid,
    _is_rate_signal,
)
from domains.revenue.stages.state import build_revenue_state  # noqa: E402

FAILS: list[str] = []


def check(label: str, got, want) -> None:
    ok = (
        (abs(got - want) < 0.01)
        if isinstance(want, (int, float)) and isinstance(got, (int, float))
        else (got == want)
    )
    print(f"{'✅' if ok else '❌'} {label}: got={got!r} want={want!r}")
    if not ok:
        FAILS.append(label)


# --- E1: units ---
check("E1 'Rp234 ribu' → 0.234", _extract_rp("sekitar Rp234 ribu per jam kerja"), 0.234)
check("E1 'Rp30 juta' → 30", _extract_rp("Rp30 juta/bulan"), 30.0)
check("E1 'Rp30jt' → 30", _extract_rp("Rp30jt"), 30.0)
check("E1 'Rp30000000' → 30", _extract_rp("Rp30000000"), 30.0)
check("E1 'Rp1,5 juta' → 1.5", _extract_rp("Rp1,5 juta"), 1.5)
check("E1 'Rp1-2 juta' midpoint → 1.5", _extract_rp_range_mid("Rp1-2 juta per proyek"), 1.5)
check("E1 'Rp8-10 juta' midpoint → 9", _extract_rp_range_mid("Rp8-10 juta per klien"), 9.0)

# --- E2: rate context, not revenue ---
check("E2 rate 'per jam'", _is_rate_signal("sekitar Rp234 ribu per jam kerja"), True)
check("E2 rate 'per semester'", _is_rate_signal("Rp48 juta per semester"), True)
check(
    "E2 bukan rate 'Rp8jt/bulan, kontrak per semester'",
    _is_rate_signal("Rp8 juta/bulan kontrak per semester"),
    False,
)
check("E2 bukan rate 'Rp30 juta/bulan'", _is_rate_signal("Rp30 juta/bulan"), False)

# --- v6 run ledger replication (declared 234 / computed 120 / deal 1.5 bug) ---
LEDGER_V6 = [
    EvidenceItem(
        id="a",
        signal="Total yang benar-benar saya terima per bulan Rp30 juta/bulan dari ketiga retainer",
        level="transactional",
        topic="REVENUE_STATE",
    ),
    EvidenceItem(
        id="b",
        signal="Klinik kecantikan Rp12 juta/bulan mulai sekitar 8 bulan lalu",
        level="transactional",
        topic="REVENUE_STATE",
    ),
    EvidenceItem(
        id="c",
        signal="Restoran Rp10 juta/bulan mulai sekitar 6 bulan lalu",
        level="transactional",
        topic="REVENUE_STATE",
    ),
    EvidenceItem(
        id="d",
        signal="Sekolah swasta Rp8 juta/bulan kontrak per semester mulai 5 bulan lalu",
        level="transactional",
        topic="REVENUE_STATE",
    ),
    EvidenceItem(
        id="e",
        signal="sekitar Rp234 ribu per jam kerja, angkanya tidak berubah dua tahun",
        level="self_reported",
        topic="MOTION",
    ),
    EvidenceItem(
        id="f",
        signal="proyek kecil dari kenalan Rp1-2 juta sekali dan tidak tiap bulan",
        level="self_reported",
        topic="REVENUE_STATE",
    ),
    EvidenceItem(
        id="g",
        signal="Klinik pakai 60 jam per bulan, restoran 36 jam per bulan, sekolah 32 jam per bulan",
        level="self_reported",
        topic="MOTION",
    ),
    EvidenceItem(
        id="h",
        signal="klien baru di kisaran Rp8-10 juta per klien",
        level="self_reported",
        topic="CONVERSION",
    ),
]

s = build_revenue_state(LEDGER_V6, "Rp25 juta/bulan dari jasa")
check("V6 current = 30", s.current_monthly, 30.0)
check("V6 target = 25 (goal menang, E4)", s.target_monthly, 25.0)
check("V6 deal size = 9 (midpoint, bukan Rp1.5 ad-hoc)", s.avg_deal_size, 9.0)
check("V6 tanpa MISMATCH palsu", (s.reconciliation.get("current_monthly") or {}).get("status"), "VERIFIED")

# --- Ledger order must not change the result (regression R1) ---
import itertools  # noqa: E402

for perm in itertools.islice(itertools.permutations(LEDGER_V6), 24):
    s2 = build_revenue_state(list(perm), "Rp25 juta/bulan dari jasa")
    if s2.current_monthly != 30.0:
        FAILS.append(f"order-dependence: cur={s2.current_monthly}")
        print(f"❌ order-dependence terdeteksi: cur={s2.current_monthly}")
        break
else:
    print("✅ order-independent (24 permutasi → cur=30)")

# --- Real MISMATCH still detected ---
MISMATCH = [
    EvidenceItem(
        id="a",
        signal="Total revenue saya Rp35 juta per bulan",
        level="transactional",
        topic="REVENUE_STATE",
    ),
    EvidenceItem(id="b", signal="klinik Rp12 juta per klien", level="transactional", topic="REVENUE_STATE"),
    EvidenceItem(id="c", signal="restoran Rp10 juta per klien", level="transactional", topic="REVENUE_STATE"),
    EvidenceItem(id="d", signal="sekolah Rp8 juta per klien", level="transactional", topic="REVENUE_STATE"),
]
sm = build_revenue_state(MISMATCH, "Rp60 juta per bulan")
rec = sm.reconciliation.get("current_monthly") or {}
check("MISMATCH: declared menang (35)", sm.current_monthly, 35.0)
check("MISMATCH: status", rec.get("status"), "MISMATCH")

# --- Annual does not become monthly (regression S1) ---
sa = build_revenue_state(
    [
        EvidenceItem(
            id="a",
            signal="Tahun lalu revenue Rp280 juta dari 4 klien manufaktur",
            level="outcome",
            topic="REVENUE_STATE",
        )
    ],
    "Rp30 juta per bulan",
)
check("Annual Rp280jt/tahun → 23.3", sa.current_monthly, 23.3)

print("\n" + ("=" * 50))
print(f"HASIL: {'SEMUA LULUS ✅' if not FAILS else f'{len(FAILS)} GAGAL ❌ → {FAILS}'}")
sys.exit(1 if FAILS else 0)
