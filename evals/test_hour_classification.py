"""Acquisition vs delivery hour-classification regression — era-7 (internal-docs §6.2).

Bug: the keyword-window classifier (14/30 chars) + `"demand"` in `_ACQ_KW` +
`max(_acq_cands)` let a DELIVERY hour leak into the ACQUISITION column:
  "Kapasitas: 34,5 jam per minggu untuk demand generation." ["Capacity: 34.5 hours per
  week for demand generation."] → acq=34.5
Impact: the `acquisition 3-4` DoD smoke invariant failed (sample-1 17/19).

Fix (two layers):
  1. `"demand"` removed from `_ACQ_KW`.
  2. Magnitude sanity check: acq >= del → reject; acq > 20 hours/week → reject
     (fallback None > wrong value — Level A internal-docs).
"""

import sys

sys.path.insert(0, ".")

from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.stages.state import build_revenue_state  # noqa: E402

FAILS: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"{'✅' if ok else '❌'} {label}: got={got!r} want={want!r}")
    if not ok:
        FAILS.append(label)


def rs_for(quote: str, level: str = "outcome"):
    ev = [
        EvidenceItem(
            id="ev-x", topic="REVENUE_STATE", level=level,
            signal="capacity", source_quote=quote,
        )
    ]
    return build_revenue_state(ev)


# ---- T1–T3: reproduce the real bug (delivery number sticks to the ACQ keyword) ----------
s = rs_for("Kapasitas: 34,5 jam per minggu untuk demand generation.")
check("T1 'demand generation' tidak menjadikan 34.5 jam akuisisi",
      s.acquisition_hours_per_week in (None,) or s.acquisition_hours_per_week < 20,
      True)

s = rs_for("Tersedia 34,5 jam per minggu untuk prospek.")
check("T2 absurd cap: 34.5 jam 'untuk prospek' ditolak (>20 jam)",
      s.acquisition_hours_per_week, None)

s = rs_for("Untuk prospek: 34,5 jam per minggu.")
check("T3 absurd cap: 'untuk prospek: 34,5 jam' ditolak (>20 jam)",
      s.acquisition_hours_per_week, None)

# ---- T4: control — a delivery hour is still read correctly ------------------------
s = rs_for("Delivery terpakai 34,5 jam per minggu.")
check("T4 kontrol: delivery 34.5 terbaca di kolom delivery",
      (s.acquisition_hours_per_week, s.delivery_hours_per_week), (None, 34.5))

# ---- T13: number-first EN, keyword AFTER the number (18 Sep 2026 incident) -----
# Form '34.5 hours per week untuk delivery' — previously both columns were None (delivery
# not extracted) → the old fallback captured 34.5 as acquisition.
s = rs_for("34.5 hours per week untuk delivery.")
check("T13 number-first EN: '34.5 hours per week untuk delivery' terbaca kolom delivery",
      (s.acquisition_hours_per_week, s.delivery_hours_per_week), (None, 34.5))

# ---- A/B: real cases from the Rina persona (must stay correct) ----------------
s = rs_for("Sisa waktu untuk prospek 3-4 jam per minggu. "
           "Delivery terpakai 34,5 jam per minggu, tidak ada waktu untuk "
           "demand generation.")
check("A nyata-1: acq 4.0 + del 34.5 tetap benar",
      (s.acquisition_hours_per_week, s.delivery_hours_per_week), (4.0, 34.5))

s = rs_for("Waktu untuk prospek 3-4 jam per minggu. "
           "Delivery terpakai 34,5 jam per minggu. Sisanya untuk operasional.")
check("B nyata-2: acq 4.0 + del 34.5 tetap benar",
      (s.acquisition_hours_per_week, s.delivery_hours_per_week), (4.0, 34.5))

# ---- a reasonable value must not be rejected by the cap ------------------------------
s = rs_for("Waktu prospek 10-12 jam per minggu, sisanya delivery klien.")
check("nilai wajar 12 jam tidak ikut tertolak cap",
      s.acquisition_hours_per_week, 12.0)

# ---- DoD invariant: acq must NEVER be >= del in any state ---------------
QUOTES = [
    "Kapasitas: 34,5 jam per minggu untuk demand generation.",
    "Tersedia 34,5 jam per minggu untuk prospek.",
    "Untuk prospek: 34,5 jam per minggu.",
    "Sisa waktu untuk prospek 3-4 jam per minggu. Delivery terpakai 34,5 jam per minggu.",
    "3-4 jam/minggu prospek, tersedot 30+ jam/minggu delivery.",
]
for i, q in enumerate(QUOTES, 1):
    s = rs_for(q)
    a, d = s.acquisition_hours_per_week, s.delivery_hours_per_week
    ok = a is None or d is None or a < d
    check(f"invariant acq<del (Q{i})", ok, True)

print()
if FAILS:
    print(f"GAGAL: {len(FAILS)} kasus — {FAILS}")
    sys.exit(1)
print("SEMUA KASUS KLASIFIKASI JAM LULUS ✅")
