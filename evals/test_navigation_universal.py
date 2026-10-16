"""Universal navigation (core/navigation) — separate generator + evaluator,
0..N paths, provenance, isolation.

Demonstrates the ARCHITECTURE, not an example: synthetic domains (SaaS, B2B)
use the same pipeline without touching core; the candidate count is not fixed;
zero paths is a valid state with a reason; UNKNOWN != ABSENT.
Deterministic, 0 LLM. Run: .venv/bin/python evals/test_navigation_universal.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, ".")

from core.navigation.contracts import (  # noqa: E402
    Feasibility,
    Lifecycle,
    display_status,
    feasibility_from_checks,
    path_id_for,
)
from core.navigation.evaluator import build_path_set, validate_path_set  # noqa: E402
from core.navigation.generator import generate_candidates  # noqa: E402
from core.navigation.predicate import evaluate  # noqa: E402
from evals.navigation_fixtures import (  # noqa: E402
    B2B_SPACE,
    SAAS_SPACE,
    reader_of,
    synthetic_space,
)

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


# ── tri-state predicates ────────────────────────────────────────────────────
r = reader_of({"a": True, "b": False, "c": None})
check("all_of dengan satu FALSE = FALSE", evaluate({"all_of": ["a", "b", "c"]}, r).value is False)
check("all_of TRUE + None = None (bukan TRUE)", evaluate({"all_of": ["a", "c"]}, r).value is None)
check("any_of TRUE + None = TRUE", evaluate({"any_of": ["a", "c"]}, r).value is True)
check("any_of FALSE + None = None (bukan FALSE)", evaluate({"any_of": ["b", "c"]}, r).value is None)
check("not None tetap None", evaluate({"not": "c"}, r).value is None)
check("predikat kosong = None (tanpa dasar tak ada dukungan)", evaluate({}, r).value is None)
check(
    "dukungan any_of hanya dari sinyal yang benar-benar TRUE",
    [s for s, _ in evaluate({"any_of": ["a", "b"]}, r).support] == ["a"],
)

# ── Scenario B — SaaS: many sign-ups, weak activation -> contextual path, NOT a Revenue motion ──
saas = reader_of(
    {
        "state:revenue_goal_set": True,
        "state:many_signups": True,
        "state:weak_activation": True,
        "state:activation_already_strong": False,
    },
    {"state:weak_activation": ("ev-7",), "state:many_signups": ("ev-3",)},
)
ps = build_path_set(SAAS_SPACE, saas)
ids = [p["path_id"] for p in ps["paths"]]
check(
    "SaaS: 'activation first' terwakili sebagai Possible Path",
    ids == [path_id_for("activation_first")],
    str(ids),
)
p = ps["paths"][0]
check("SaaS: path TANPA motion Revenue (motion=None)", p["motion"] is None)
check(
    "SaaS: provenance menyebut sinyal & evidence yang benar-benar mendukung",
    set(p["provenance"]["evidence_ids"]) == {"ev-3", "ev-7"}
    and "state:weak_activation" in p["provenance"]["state_claims"],
)
check("SaaS: identitas path diturunkan dari strategi, bukan motion", p["path_id"] == "path.activation_first")
check(
    "SaaS: 'scale acquisition' TIDAK lahir saat aktivasi lemah (pengetahuan mempengaruhi kemungkinan)",
    path_id_for("scale_acquisition") not in ids
    and any(n["strategy_id"] == "scale_acquisition" for n in ps["generation"]["not_emergent"]),
)
check(
    "SaaS: check tanpa bukti = UNKNOWN -> feasibility UNDETERMINED (bukan CONTRADICTED)",
    p["feasibility"] == "UNDETERMINED"
    and p["status"] == "TEST_FIRST"
    and all(c["state"] == "UNKNOWN" for c in p["checks"]),
)
check(
    "SaaS: applicable tetapi 0 kondisi terbukti = sah (OPEN != READY)",
    p["applicability"] == "APPLIES" and not any(c["state"] == "PRESENT" for c in p["checks"]),
)

# ── Scenario C — B2B: many leads, poor decision-maker access ──────────────────────────────────
b2b = reader_of(
    {
        "state:revenue_goal_set": True,
        "state:many_leads": True,
        "state:poor_decision_maker_access": True,
        "state:decision_maker_named": False,
    }
)
ps2 = build_path_set(B2B_SPACE, b2b)
ids2 = [p["path_id"] for p in ps2["paths"]]
check(
    "B2B: 'improve decision-maker access' terwakili", path_id_for("decision_maker_access") in ids2, str(ids2)
)
dm = next(p for p in ps2["paths"] if p["strategy_id"] == "decision_maker_access")
check(
    "B2B: check requirement-anchored ABSENT -> CONDITIONAL, requirement_id terbawa",
    dm["feasibility"] == "CONDITIONAL" and dm["checks"][0]["requirement_id"] == "access.decision_maker",
)
check("B2B: substrat route tersedia dilaporkan eksplisit", dm["route_substrate"]["available"] is True)
lq = next(p for p in ps2["paths"] if p["strategy_id"] == "lead_qualification")
check(
    "B2B: path tanpa template route tetap sah (Possible Path != RouteTemplate)",
    lq["route_substrate"]["available"] is False and lq["route_substrate"]["template_ids"] == [],
)
check(
    "B2B: strategi TANPA check = UNDETERMINED (tak ada yang dievaluasi), bukan SUPPORTED hampa",
    lq["feasibility"] == "UNDETERMINED"
    and lq["feasibility_basis"] == "NO_CHECKS_DECLARED"
    and lq["status"] == "TEST_FIRST"
    and lq["provenance"]["support"],
)

# ── Scenario D — insufficient evidence: ZERO paths is a valid state, not an error ──────────────
sparse = reader_of({})
ps0 = build_path_set(SAAS_SPACE, sparse)
check("Sparse: 0 path, bukan error", ps0["paths"] == [])
check(
    "Sparse: alasan eksplisit (tujuan belum terbukti)",
    [u["code"] for u in ps0["unresolved"]] == ["GOAL_NOT_ESTABLISHED"],
    str(ps0["unresolved"]),
)
goal_only = reader_of({"state:revenue_goal_set": True})
ps0b = build_path_set(SAAS_SPACE, goal_only)
check(
    "Tujuan jelas tetapi keadaan tipis: 0 path + INSUFFICIENT_VERIFIED_STATE + sinyal yang hilang",
    ps0b["paths"] == []
    and ps0b["unresolved"][0]["code"] == "INSUFFICIENT_VERIFIED_STATE"
    and "state:many_signups" in ps0b["unresolved"][0]["missing"],
)
contradictory = reader_of({"state:revenue_goal_set": True, "state:many_signups": False})
ps0c = build_path_set(SAAS_SPACE, contradictory)
check(
    "Keadaan menyingkirkan semua strategi: 0 path + NO_SUPPORTED_STRATEGY",
    ps0c["paths"] == [] and ps0c["unresolved"][0]["code"] == "NO_SUPPORTED_STRATEGY",
    str(ps0c["unresolved"]),
)
check(
    "Tujuan ABSENT (terbukti tidak ada) dibedakan dari belum diketahui",
    build_path_set(SAAS_SPACE, reader_of({"state:revenue_goal_set": False}))["unresolved"][0]["code"]
    == "GOAL_ABSENT",
)
check(
    "Ruang kosong = 0 path dengan alasan",
    build_path_set(synthetic_space(0), reader_of({}))["unresolved"][0]["code"] == "EMPTY_POSSIBILITY_SPACE",
)

# ── Dynamic candidate count: 0/1/2/5/10 without changing core code ────────────────────────────
for n in (0, 1, 2, 5, 10):
    vals = {"state:goal": True, **{f"state:trigger_{i}": True for i in range(n)}}
    out = build_path_set(synthetic_space(n), reader_of(vals))
    check(f"dinamis: {n} strategi lahir -> {n} Possible Path", len(out["paths"]) == n)
    check(
        f"dinamis n={n}: setiap path punya provenance dukungan",
        all(p["provenance"]["support"] for p in out["paths"]),
    )
partial = build_path_set(
    synthetic_space(10),
    reader_of({"state:goal": True, **{f"state:trigger_{i}": True for i in range(0, 10, 3)}}),
)
check("dinamis: hanya yang didukung keadaan yang lahir (4 dari 10)", len(partial["paths"]) == 4)

# ── Applicability separate from satisfaction/feasibility ────────────────────────────────────────
saas_strong = reader_of(
    {
        "state:revenue_goal_set": True,
        "state:many_signups": True,
        "state:weak_activation": True,
        "state:activation_already_strong": True,
    }
)
ps3 = build_path_set(SAAS_SPACE, saas_strong)
check(
    "NOT_APPLICABLE dibuang oleh EVALUATOR (bukan generator), alasan dicatat",
    ps3["paths"] == []
    and ps3["generation"]["rejected"][0]["reason"] == "NOT_APPLICABLE"
    and "activation_first" in ps3["generation"]["emerged"],
)
check(
    "semua kandidat NOT_APPLICABLE -> alasan eksplisit, bukan path karangan",
    ps3["unresolved"][0]["code"] == "ALL_CANDIDATES_NOT_APPLICABLE",
)
saas_unk = reader_of(
    {"state:revenue_goal_set": True, "state:many_signups": True, "state:weak_activation": True}
)
ps4 = build_path_set(SAAS_SPACE, saas_unk)
check(
    "eksklusi belum diketahui -> applicability UNKNOWN (bertahan, tidak difabrikasi APPLIES)",
    ps4["paths"][0]["applicability"] == "UNKNOWN"
    and any(m["check_id"].startswith("applicability:") for m in ps4["paths"][0]["missing_evidence"]),
)

# ── Feasibility vs Lifecycle: two STOP origins stay separate ────────────────────────────────────
check("CONTRADICTED != lifecycle STOPPED (dua enum)", str(Feasibility.CONTRADICTED) != str(Lifecycle.STOPPED))
hard = [{"state": "ABSENT", "kind": "hard"}, {"state": "UNKNOWN", "kind": "prereq"}]
check("hard ABSENT -> CONTRADICTED", feasibility_from_checks(hard) == Feasibility.CONTRADICTED)
check(
    "prereq ABSENT -> CONDITIONAL",
    feasibility_from_checks([{"state": "ABSENT", "kind": "prereq"}]) == Feasibility.CONDITIONAL,
)
check(
    "hanya UNKNOWN -> UNDETERMINED",
    feasibility_from_checks([{"state": "UNKNOWN", "kind": "hard"}]) == Feasibility.UNDETERMINED,
)
check(
    "status kata: STOP dari kontradiksi engine maupun lifecycle",
    display_status(Feasibility.CONTRADICTED, Lifecycle.OPEN) == "STOP"
    and display_status(Feasibility.SUPPORTED, Lifecycle.STOPPED) == "STOP"
    and display_status(Feasibility.SUPPORTED, Lifecycle.PAUSED) == "OPEN",
)
saas_ok = reader_of(
    {
        "state:revenue_goal_set": True,
        "state:many_signups": True,
        "state:weak_activation": True,
        "state:activation_already_strong": False,
        "state:aha_moment_defined": True,
        "state:funnel_measured": True,
    }
)
stopped = build_path_set(
    SAAS_SPACE,
    saas_ok,
    lifecycles={
        "path.activation_first": {"state": "STOPPED", "cause": "outcome=regret", "origin": "USER_OUTCOME"}
    },
)
sp = stopped["paths"][0]
check(
    "path SUPPORTED lalu di-STOP user: feasibility tetap SUPPORTED, lifecycle STOPPED, status STOP",
    sp["feasibility"] == "SUPPORTED" and sp["lifecycle"] == "STOPPED" and sp["status"] == "STOP",
)
check(
    "asal STOP tercatat: LIFECYCLE, bukan ENGINE_CONTRADICTION",
    [s["source"] for s in sp["stop_provenance"]] == ["LIFECYCLE"],
)
saas_bad = reader_of(
    {
        "state:revenue_goal_set": True,
        "state:many_signups": True,
        "state:weak_activation": False,
        "state:activation_already_strong": False,
    }
)
sb = build_path_set(SAAS_SPACE, saas_bad)["paths"]
check(
    "kontradiksi engine tercatat sebagai ENGINE_CONTRADICTION",
    sb and sb[0]["stop_provenance"][0]["source"] == "ENGINE_CONTRADICTION" and sb[0]["lifecycle"] == "OPEN",
)

# ── PathSet invariants ─────────────────────────────────────────────────────────────────────────
try:
    validate_path_set({"paths": [], "unresolved": []})
    check("nol path tanpa alasan ditolak validator", False)
except ValueError:
    check("nol path tanpa alasan ditolak validator", True)
bad = {"paths": [{**ps["paths"][0], "provenance": {"support": []}}], "unresolved": []}
try:
    validate_path_set(bad)
    check("path tanpa provenance ditolak validator", False)
except ValueError:
    check("path tanpa provenance ditolak validator", True)
gen = generate_candidates(SAAS_SPACE, saas)
check(
    "generator TIDAK menilai feasibility/applicability (hanya kandidat)",
    not hasattr(gen.candidates[0], "feasibility") and gen.candidates[0].support,
)

# ── Domain isolation: core/navigation has no Revenue motion/vocabulary ────────────────────────
root = pathlib.Path("core/navigation")
src = "\n".join(f.read_text(encoding="utf-8") for f in root.glob("*.py"))
leaks = sorted(
    set(re.findall(r"ACQUISITION|REPRICING|EXPANSION|PARTNERSHIP|PAID_ACQUISITION|revenue|Revenue", src))
)
check("core/navigation bebas motion & kosakata Revenue", not leaks, str(leaks))

fails = [x for x in _results if not x[1]]
print(
    f"\n{'=' * 50}\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS"
    + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌")
)
sys.exit(1 if fails else 0)
