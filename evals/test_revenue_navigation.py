"""Revenue plugin for universal navigation (internal-docs §Domain Plugin Boundary).

Tests the Revenue possibility space: candidates born from verified state + mechanisms (not a fixed list),
feasibility evaluated from requirement-anchored checks, lifecycle separate from feasibility, and the five
Revenue motions as strategy PRIMITIVES (not Possible Path definitions). Deterministic, 0 LLM.
Run: .venv/bin/python evals/test_revenue_navigation.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from core.navigation.contracts import path_id_for  # noqa: E402
from domains.revenue.navigation.paths import build_possible_paths  # noqa: E402
from domains.revenue.navigation.signals import RevenueSignals, declared_signal_ids  # noqa: E402
from domains.revenue.navigation.space import revenue_space  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from engine.requirements import is_known  # noqa: E402
from ontology.route.strategies import load_strategies  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def st(**kw) -> RevenueState:
    return RevenueState(**kw)


def by_strategy(r: dict) -> dict[str, dict]:
    return {p["strategy_id"]: p for p in r["paths"]}


def ids(r: dict) -> list[str]:
    return [p["strategy_id"] for p in r["paths"]]


# 1 — Rina case: full capacity (0.863) + proven WtP + measured clients.
s = st(
    current_monthly=30.0,
    target_monthly=60.0,
    gap_monthly=30.0,
    capacity_utilization=0.863,
    willingness_to_pay="PROVEN_AT_CURRENT_PRICE",
    willingness_to_pay_new_price="PROVEN_AT_NEW_PRICE",
    demand_exists=True,
    demand_signal="EXISTS",
    avg_deal_size=10.0,
    demand_sufficiency="AT_RISK",
)
r = build_possible_paths(s, {"level": "TEST_FIRST"})
by = by_strategy(r)
check(
    "kapasitas penuh + WtP proven: value_repricing OPEN (SUPPORTED)",
    by["value_repricing"]["status"] == "OPEN" and by["value_repricing"]["feasibility"] == "SUPPORTED",
)
check(
    "kapasitas penuh: direct_outreach NOT_YET (prasyarat kapasitas diketahui belum terpenuhi)",
    by["direct_outreach"]["status"] == "NOT_YET" and by["direct_outreach"]["feasibility"] == "CONDITIONAL",
)
check("NOT_YET berargumen: unlock_conditions non-kosong", len(by["direct_outreach"]["unlock_conditions"]) > 0)
check("spectrum TEST_FIRST -> advisory terpasang di semua path", all(p["advisory"] for p in r["paths"]))
check(
    "path OPEN: value_repricing + client_expansion",
    [p["strategy_id"] for p in r["paths"] if p["status"] == "OPEN"]
    == ["value_repricing", "client_expansion"],
)

# 2 — Slack capacity + demand exists, WtP unknown.
s2 = st(
    current_monthly=20.0,
    target_monthly=40.0,
    gap_monthly=20.0,
    capacity_utilization=0.3,
    willingness_to_pay="PROVEN_AT_CURRENT_PRICE",
    demand_exists=True,
    demand_signal="EXISTS",
    demand_sufficiency="AT_RISK",
)
by2 = by_strategy(build_possible_paths(s2, {"level": "TEST_FIRST"}))
check(
    "longgar + demand ada: direct_outreach OPEN (WtP tak relevan untuk path ini)",
    by2["direct_outreach"]["status"] == "OPEN",
)
check(
    "value_repricing tanpa bukti over-demand & WtP harga baru: UNDETERMINED (TEST_FIRST), bukan gagal",
    by2["value_repricing"]["feasibility"] == "UNDETERMINED"
    and by2["value_repricing"]["status"] == "TEST_FIRST",
)

# 3 — SUFFICIENT + proven + slack: three paths OPEN at once; advisory empty at PROCEED.
s3 = st(
    current_monthly=30.0,
    target_monthly=60.0,
    gap_monthly=30.0,
    capacity_utilization=0.5,
    willingness_to_pay="PROVEN_AT_CURRENT_PRICE",
    willingness_to_pay_new_price="PROVEN_AT_NEW_PRICE",
    demand_exists=True,
    demand_signal="EXISTS",
    demand_sufficiency="SUFFICIENT",
    avg_deal_size=10.0,
)
r3 = build_possible_paths(s3, {"level": "PROCEED"})
check(
    "SUFFICIENT + proven: direct_outreach, value_repricing, client_expansion OPEN",
    [p["strategy_id"] for p in r3["paths"] if p["status"] == "OPEN"]
    == ["direct_outreach", "value_repricing", "client_expansion"],
)
check(
    "advisory PROCEED = kosong (fungsi level, bukan selalu ada)", all(not p["advisory"] for p in r3["paths"])
)
r3b = build_possible_paths(s3, {"level": "STOP"})
check(
    "advisory STOP berbeda dari TEST_FIRST (level-appropriate)",
    r3b["paths"][0]["advisory"] and r3b["paths"][0]["advisory"] != r["paths"][0]["advisory"],
)

# 4 — Thin state: ZERO paths with a reason, not five fabricated CONDITIONAL paths.
r4 = build_possible_paths(st(), None)
check("state kosong: 0 path (bukan error)", r4["paths"] == [])
check(
    "state kosong: alasan eksplisit (tujuan belum dinyatakan)",
    [u["code"] for u in r4["unresolved"]] == ["GOAL_NOT_ESTABLISHED"],
    str(r4["unresolved"]),
)
r4b = build_possible_paths(st(target_monthly=60.0), None)
check(
    "tujuan ada, angka lain belum: 0 path + INSUFFICIENT_VERIFIED_STATE + sinyal yang hilang",
    r4b["paths"] == []
    and r4b["unresolved"][0]["code"] == "INSUFFICIENT_VERIFIED_STATE"
    and "state:existing_revenue" in r4b["unresolved"][0]["missing"],
    str(r4b["unresolved"]),
)

# 5 — Path count follows the state (not a fixed five).
r5a = build_possible_paths(st(target_monthly=60.0, current_monthly=0.0, gap_monthly=60.0), None)
check(
    "belum ada pendapatan + ada gap: hanya path yang didukung (outreach + paid), bukan lima",
    ids(r5a) == ["direct_outreach", "paid_channel_test"],
    str(ids(r5a)),
)
r5b = build_possible_paths(st(target_monthly=30.0, current_monthly=30.0, gap_monthly=0.0), None)
check(
    "target tercapai (gap 0): path akuisisi tidak lahir, path basis klien lahir",
    "direct_outreach" not in ids(r5b) and "value_repricing" in ids(r5b),
    str(ids(r5b)),
)
check("jumlah path bervariasi menurut keadaan", len({len(ids(x)) for x in (r, r4, r5a, r5b)}) >= 3)

# 6 — Knowledge shapes possibility: detected mechanisms birth strategies without revenue numbers.
base = st(target_monthly=60.0)
no_mech = build_possible_paths(base, None)
with_mech = build_possible_paths(
    base, None, mechanisms={"pricing_avoidance_loop": ["ev-9"], "trust_gap": ["ev-4"]}
)
check("tanpa mekanisme: 0 path", no_mech["paths"] == [])
check(
    "mekanisme pricing_avoidance_loop + trust_gap melahirkan value_repricing & referral_partnership",
    ids(with_mech) == ["value_repricing", "referral_partnership"],
    str(ids(with_mech)),
)
prov = by_strategy(with_mech)["value_repricing"]["provenance"]
check(
    "provenance menyebut mekanisme + evidence yang benar-benar mendukung",
    prov["mechanism_ids"] == ["pricing_avoidance_loop"] and "ev-9" in prov["evidence_ids"],
)
check("provenance memuat sinyal tujuan sebagai dukungan", "state:goal_established" in prov["state_claims"])
check(
    "provenance membawa sumber pengetahuan dari template (bukan karangan)",
    all(k["source_id"] for k in prov["knowledge_sources"]) and prov["knowledge_sources"],
)

# 7 — Engine contradiction (hard) vs lifecycle (user decision): two separate STOP origins.
s7 = st(
    current_monthly=30.0,
    target_monthly=60.0,
    gap_monthly=30.0,
    capacity_utilization=0.5,
    willingness_to_pay="PRICE_SENSITIVE",
    willingness_to_pay_new_price="REJECTED_AT_NEW_PRICE",
    demand_exists=True,
    demand_signal="EXISTS",
    avg_deal_size=10.0,
)
by7 = by_strategy(build_possible_paths(s7, {"level": "PROCEED"}))
check(
    "WtP negatif (hard): value_repricing CONTRADICTED -> STOP, lifecycle tetap OPEN",
    by7["value_repricing"]["feasibility"] == "CONTRADICTED"
    and by7["value_repricing"]["status"] == "STOP"
    and by7["value_repricing"]["lifecycle"] == "OPEN",
)
check(
    "asal STOP = ENGINE_CONTRADICTION dengan check yang menyebabkannya",
    by7["value_repricing"]["stop_provenance"]
    == [{"source": "ENGINE_CONTRADICTION", "checks": ["willingness_to_pay"]}],
)
check(
    "client_expansion juga CONTRADICTED (check hard yang sama)",
    by7["client_expansion"]["feasibility"] == "CONTRADICTED",
)
stopped = build_possible_paths(
    s3,
    {"level": "PROCEED"},
    path_states={"path.value_repricing": {"outcome_state": "STOPPED", "moved": 0, "regret": 1}},
)
sp = by_strategy(stopped)["value_repricing"]
check(
    "user STOP (outcome regret): feasibility tetap SUPPORTED, lifecycle STOPPED, status STOP",
    sp["feasibility"] == "SUPPORTED" and sp["lifecycle"] == "STOPPED" and sp["status"] == "STOP",
)
check(
    "asal STOP = LIFECYCLE (keputusan user), bukan kontradiksi engine",
    [x["source"] for x in sp["stop_provenance"]] == ["LIFECYCLE"]
    and sp["stop_provenance"][0]["origin"] == "USER_OUTCOME",
)

# 8 — A path without evidence yet: PAID with nothing = UNDETERMINED + three missing_evidence (unlock filled).
paid = by_strategy(build_possible_paths(s, None))["paid_channel_test"]
check(
    "paid_channel_test tanpa bukti: UNDETERMINED + 3 missing_evidence",
    paid["status"] == "TEST_FIRST" and len(paid["missing_evidence"]) == 3,
)
check(
    "missing evidence = peta bukti yang harus dikumpulkan (need terisi)",
    all(m["need"] for m in paid["missing_evidence"]),
)
part = by_strategy(build_possible_paths(s3, {"level": "PROCEED"}))["referral_partnership"]
check(
    "referral_partnership: klien terukur + kapasitas longgar tanpa bukti referral -> UNDETERMINED",
    part["feasibility"] == "UNDETERMINED" and len(part["missing_evidence"]) >= 1,
)
check(
    "kapasitas penuh -> referral_partnership CONDITIONAL (prereq, ada unlock)",
    by["referral_partnership"]["feasibility"] == "CONDITIONAL",
)

# 9 — Path & motion identity: motion = a domain primitive on strategies, NOT part of path identity.
reg = load_strategies()
motions = {reg[sp_.strategy_id]["motion"] for sp_ in revenue_space().strategies}
check(
    "lima motion Revenue hidup sebagai primitive pada strategi aktif (koleksi motion, bukan koleksi path)",
    motions == {"ACQUISITION", "REPRICING", "EXPANSION", "PARTNERSHIP", "PAID_ACQUISITION"},
)
check(
    "path_id diturunkan dari strategi saja (motion = atribut, bukan bagian identitas)",
    all(
        p["path_id"] == path_id_for(p["strategy_id"]) == f"path.{p['strategy_id']}" and p["motion"]
        for p in r["paths"]
    ),
)
check(
    "spesimen proof_only tidak ikut ruang kemungkinan",
    "template_led" not in {sp_.strategy_id for sp_ in revenue_space().strategies},
)

# 10 — Requirement-anchored checks: anchors valid in the Requirement Registry; no gate strings as keys.
anchored = [c.requirement_id for sp_ in revenue_space().strategies for c in sp_.checks if c.requirement_id]
check(
    "setiap requirement_id pada check ada di Requirement Registry",
    anchored and all(is_known(x) for x in anchored),
    str([x for x in anchored if not is_known(x)]),
)
check(
    "check_id stabil (id, bukan kalimat)",
    all(" " not in c.check_id for sp_ in revenue_space().strategies for c in sp_.checks),
)

# 11 — Every signal the possibility space references is declared by the reader (no orphan ids / silent typos).
from core.navigation.predicate import signal_ids  # noqa: E402

space = revenue_space()
used = {space.goal_signal}
for sp_ in space.strategies:
    used |= set(signal_ids(sp_.emerges_when)) | set(signal_ids(sp_.not_applicable_when))
    used |= {c.signal for c in sp_.checks}
check(
    "semua sinyal yang dirujuk ruang dideklarasikan",
    used <= declared_signal_ids(),
    str(sorted(used - declared_signal_ids())),
)
check(
    "sinyal tak dikenal = belum diketahui (None), tidak pernah FALSE",
    RevenueSignals(st())("state:tidak_ada").value is None,
)
check(
    "angka tak ada = None, bukan False (UNKNOWN != ABSENT)",
    RevenueSignals(st())("state:capacity_available").value is None
    and RevenueSignals(st())("state:existing_revenue").value is None,
)

fails = [x for x in _results if not x[1]]
print(
    f"\n{'=' * 50}\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS"
    + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌")
)
sys.exit(1 if fails else 0)
