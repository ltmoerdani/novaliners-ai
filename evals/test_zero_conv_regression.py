"""Zero-conversion & entity-opportunity regression — corpus from REAL cases.

Every bug found in replay/user-testing enters here as a permanent case
(property/regression testing principle — internal-docs §7 rule 5).
Run from the mvp/ folder: .venv/bin/python evals/test_zero_conv_regression.py
"""
import sys

sys.path.insert(0, ".")

from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.stages.opportunities import build_opportunities  # noqa: E402
from domains.revenue.stages.state import build_revenue_state  # noqa: E402

FAILS: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"{'✅' if ok else '❌'} {label}: got={got!r} want={want!r}")
    if not ok:
        FAILS.append(label)


def E(sig: str, level="self_reported", topic="DEMAND"):
    return EvidenceItem(id="x", signal=sig, source_quote=sig, level=level, topic=topic)


def sufficiency_of(evids):
    return build_revenue_state(evids).demand_sufficiency


# ---- Corpus: zero-conversion sentence variants (from the REAL ledger) ----
ZERO_CONVERSION = [
    "Konversi nol: 0 dari 7-8 inquiry dalam 90 hari menjadi klien berbayar",
    "Konversi inquiry ke klien berbayar nol dari 7-8 inquiry dalam 90 hari",
    "Yang bayar dari 7-8 itu: nol",
    "konversi 90 hari terakhir 0%",                       # iter-17 pattern (old regression)
    "Yang bayar: nol. inquiry tanya harga lalu diam",     # iter-17 pattern (old regression)
]
for t in ZERO_CONVERSION:
    s = build_revenue_state(
        [
            E(t),
            E("rata-rata deal retainer baru Rp9 juta", level="transactional", topic="REVENUE_STATE"),
        ]
    )
    check(f"zero-conv AT_RISK: {t[:44]!r}", s.demand_sufficiency, "AT_RISK")

# ---- Negative: a positive claim must NOT be flagged ----
POSITIVE = "7-8 inquiry masuk dan 2 menjadi klien berbayar dalam 90 hari"
s = build_revenue_state(
    [
        E(POSITIVE),
        E("rata-rata deal retainer baru Rp9 juta", level="transactional", topic="REVENUE_STATE"),
    ]
)
check("klaim positif tidak salah-flag", s.demand_sufficiency != "AT_RISK", True)

# ---- Entity opportunity: corpus from user replay ----
BAD_ENTITIES = [
    "Revenue berjalan Rp30 juta/bulan dari 3 klien retainer aktif",       # entity 'revenue' (replay bug)
    "Volume inquiry nyata rendah: 7-8 percakapan dalam 90 hari",          # entity 'volume' (long-run bug)
    "Satu klien retainer aktif diperoleh via referral",                   # entity 'satu' (long-run bug)
]
evs = [E(t, topic="REVENUE_STATE") for t in BAD_ENTITIES]
evs[0].level = "transactional"
ops = build_opportunities(evs)
bad = [o["entity"] for o in ops if o["entity"] in ("revenue", "volume", "satu", "")]
check("entity generik dibuang (revenue/volume/satu)", bad, [])

print()
if FAILS:
    print(f"GAGAL: {len(FAILS)} kasus — {FAILS}")
    sys.exit(1)
print("SEMUA KASUS REGRESI LULUS ✅")
