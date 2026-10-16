"""Knowledge -> Mechanism -> Candidate Possibility -> Possible Path (internal-docs §23, CAND-01..08).

Proves the candidate layer is a NEW LAYER on top of the frozen foundation, not a new name for Possible Path:

    Evidence -> Knowledge (rule) -> MECHANISM -> CANDIDATE POSSIBILITY -> evaluation -> Possible Path

Two synthetic domains WITHOUT a strategy list ("growth", "hiring") and one real domain (Revenue) walk the
same chain through generic code. Matrix: 0/1/N candidates, duplicates, conflicts, UNSUPPORTED, UNKNOWN,
all_of/any_of/none_of/nested, reverse lineage, monotonicity, route-less vs with-route, LEGACY, core isolation.
Deterministic, 0 LLM. Run: .venv/bin/python evals/test_candidate_possibility.py
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

import engine.requirements as req_mod  # noqa: E402
from core.navigation.candidate import (  # noqa: E402
    MECH_ACTIVE,
    MECH_CONFLICT,
    MECH_REFUTED,
    NOT_EMERGENT,
    ORIGIN_BOTH,
    ORIGIN_PATTERN,
    SUPPORTED,
    UNDETERMINED,
    promote_possibilities,
)
from core.navigation.compat import assess_path_set  # noqa: E402
from core.navigation.contracts import (  # noqa: E402
    CheckSpec,
    MechanismSpec,
    PossibilityPattern,
    PossibilitySpace,
    Signal,
    StrategySpec,
    candidate_id_for,
    path_id_for,
)
from core.navigation.evaluator import (  # noqa: E402
    PATHSET_VERSION,
    build_path_set,
    evaluate_candidates,
    validate_path_set,
)
from core.navigation.generator import generate_candidates  # noqa: E402
from core.navigation.readiness import build_projection  # noqa: E402
from core.schema.provenance import RuleSupport  # noqa: E402
from evals.navigation_fixtures import (  # noqa: E402
    HIRING_RULE,
    growth_evidence,
    growth_reader,
    growth_space,
    growth_supports,
    hiring_candidate_space,
    hiring_evidence,
    hiring_reader,
    node,
)
from ontology.route.next_move import select_next_move  # noqa: E402
from ontology.route.plan import (  # noqa: E402
    RouteCompositionError,
    assert_route_keeps_strategy,
    plan_compositions,
)

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def raises(fn, exc=ValueError) -> str | None:
    try:
        fn()
    except exc as e:
        return str(e)
    return None


def growth(evidence=None, states=None, space=None, **ev_kw):
    """(PathSet, CandidateSet) for the growth domain from a synthetic evidence ledger (REAL rules)."""
    evidence = growth_evidence(**ev_kw) if evidence is None else evidence
    reader = growth_reader(growth_supports(evidence), states)
    space = space or growth_space()
    return build_path_set(space, reader), generate_candidates(space, reader)


def _mutated(pset: dict, how: str) -> dict:
    bad = json.loads(json.dumps(pset))
    cand_ = bad["paths"][0]["provenance"]["candidate"]
    if how == "no_mechanism":
        cand_["mechanism_ids"] = []
    elif how == "no_evidence":
        cand_["evidence_ids"], cand_["transcript_anchors"] = [], []
    else:
        cand_["candidate_id"] = "cand.lain"
    return bad


def dirs(ps: dict) -> list[str]:
    return [p["strategy_id"] for p in ps["paths"]]


def poss(ps: dict, direction: str) -> dict:
    return next(r for r in ps["generation"].get("possibilities", []) if r["direction"] == direction)


def path_of(ps: dict, strategy_id: str) -> dict:
    return next(p for p in ps["paths"] if p["strategy_id"] == strategy_id)


print("── A. Generasi: 0 / 1 / N / duplikat / mekanisme sama-kandidat beda ──")
ps0, cs0 = growth(signups=False, weak=False)
check(
    "0 kandidat: tanpa evidence, tanpa path — alasan eksplisit, bukan path karangan",
    ps0["paths"] == [] and ps0["unresolved"] and all(c.status != SUPPORTED for c in cs0.possibilities),
    str([r["code"] for r in ps0["unresolved"]]),
)
ps1, _ = growth(onboarding=True, signups=False, weak=False, states={"state:acquisition_exists": None})
check(
    "1 kandidat: onboarding_friction aktif, syarat akuisisi belum diketahui -> hanya simplify_onboarding",
    dirs(ps1) == ["simplify_onboarding"],
    str(dirs(ps1)),
)
ps2, _ = growth(onboarding=True, signups=False, weak=False)
check(
    "2 kandidat: onboarding_friction aktif + akuisisi diketahui -> dua arah (mekanisme sama punya dua turunan)",
    dirs(ps2) == ["improve_activation_before_acquisition", "simplify_onboarding"],
    str(dirs(ps2)),
)
psn, csn = growth(onboarding=True)
check(
    "N kandidat: dua mekanisme aktif -> tiga arah, jumlah mengikuti keadaan",
    dirs(psn) == ["improve_activation_before_acquisition", "define_aha_moment", "simplify_onboarding"],
    str(dirs(psn)),
)
check(
    "ruang tanpa SATU PUN StrategySpec tetap menghasilkan path (kandidat muncul tanpa daftar path)",
    growth_space().strategies == () and len(psn["paths"]) == 3,
)
imp = path_of(psn, "improve_activation_before_acquisition")
check(
    "duplikat: dua mekanisme menunjuk arah yang sama -> SATU kandidat, SATU path, provenance gabungan",
    dirs(psn).count("improve_activation_before_acquisition") == 1
    and set(imp["provenance"]["candidate"]["mechanism_ids"])
    == {"activation_bottleneck", "onboarding_friction"}
    and set(imp["provenance"]["candidate"]["knowledge_ids"]) == {"GW-R1", "GW-R2"},
)
check(
    "mekanisme sama, kandidat berbeda: activation_bottleneck -> improve_activation DAN define_aha_moment",
    {"improve_activation_before_acquisition", "define_aha_moment"} <= set(dirs(psn))
    and "activation_bottleneck"
    in path_of(psn, "define_aha_moment")["provenance"]["candidate"]["mechanism_ids"],
)
check(
    "jumlah path berbeda-beda untuk keadaan berbeda (0, 1, 2, 3) — bukan 'lima'",
    sorted({len(ps0["paths"]), len(ps1["paths"]), len(ps2["paths"]), len(psn["paths"])}) == [0, 1, 2, 3],
)
empty = PossibilitySpace("kosong", ())
cs_empty = generate_candidates(empty, lambda sid: Signal(None))
check(
    "ruang tanpa strategi DAN tanpa pola = EMPTY_POSSIBILITY_SPACE",
    [b["code"] for b in cs_empty.blockers] == ["EMPTY_POSSIBILITY_SPACE"],
)

print("── B. Pemisahan generasi vs evaluasi; Candidate != Possible Path (CAND-01, CAND-04) ──")
cs = csn
check(
    "generate_candidates hanya MENGUSULKAN: kandidat ada, belum ada path/feasibility/route",
    len(cs.possibilities) == 3
    and all(c.status == SUPPORTED for c in cs.possibilities)
    and not hasattr(cs, "paths")
    and all("feasibility" not in c.lineage() for c in cs.possibilities),
)
promoted = promote_possibilities(cs, growth_space())
check(
    "promosi menghasilkan Candidate pipeline path yang sama (generator.Candidate) — bukan pipeline kedua",
    [type(c).__name__ for c in promoted] == ["Candidate"] * 3
    and all(c.origin == ORIGIN_PATTERN for c in promoted),
)
ps_a = evaluate_candidates(
    cs, growth_space(), growth_reader(growth_supports(growth_evidence(onboarding=True)))
)
ps_b = build_path_set(growth_space(), growth_reader(growth_supports(growth_evidence(onboarding=True))))
check("generate + evaluate terpisah == build_path_set (satu pipeline)", ps_a == ps_b)
check(
    "evaluasi dapat dipanggil ulang tanpa memutasi kandidat (idempoten)",
    evaluate_candidates(cs, growth_space(), growth_reader(growth_supports(growth_evidence(onboarding=True))))
    == ps_a,
)
na_pat = dataclasses.replace(growth_space().patterns[2], not_applicable_when="state:already_simple")
sp_na = dataclasses.replace(growth_space(), patterns=growth_space().patterns[:2] + (na_pat,))
ps_na, _ = growth(onboarding=True, states={"state:already_simple": True}, space=sp_na)
check(
    "kandidat SUPPORTED belum tentu path: evaluator membuang NOT_APPLICABLE (alasan tercatat)",
    "simplify_onboarding" not in dirs(ps_na)
    and poss(ps_na, "simplify_onboarding")["disposition"] == "REJECTED_NOT_APPLICABLE"
    and poss(ps_na, "simplify_onboarding")["status"] == SUPPORTED,
)
check(
    "path hasil promosi membawa feasibility dari EVALUASI: check aha_defined belum diketahui -> TEST_FIRST",
    (imp["feasibility"], imp["status"], imp["feasibility_basis"]) == ("UNDETERMINED", "TEST_FIRST", "CHECKS"),
    str((imp["feasibility"], imp["status"])),
)
check(
    "kandidat tanpa check yang menyatakan no_preconditions -> SUPPORTED dengan dasar DECLARED_UNCONDITIONAL",
    path_of(psn, "define_aha_moment")["feasibility_basis"] == "DECLARED_UNCONDITIONAL",
)

print("── C. Epistemik: verified / UNKNOWN / UNSUPPORTED / konflik / bantahan ──")
ps_unk, _ = growth(signups=True, weak=False)
und_unk = next(
    u for u in ps_unk["generation"]["undetermined"] if u["candidate_id"] == "cand.define_aha_moment"
)
cs_unk = generate_candidates(growth_space(), growth_reader(growth_supports(growth_evidence(weak=False))))
st_unk = next(c for c in cs_unk.possibilities if c.direction == "define_aha_moment")
check(
    "UNKNOWN: rule tidak matched -> kandidat UNDETERMINED (bukan path, bukan NOT_EMERGENT: UNKNOWN != ABSENT)",
    "define_aha_moment" not in dirs(ps_unk)
    and st_unk.status == UNDETERMINED
    and st_unk.refuted == []
    and und_unk["missing"] == ["mechanism:activation_bottleneck"],
    str(und_unk["missing"]),
)
check(
    "UNKNOWN: tanpa tanda apa pun tidak jadi 'emerging' dan tak membengkakkan audit (hanya generation.undetermined)",
    st_unk.emerging is None
    and all(r["direction"] != "define_aha_moment" for r in ps_unk["generation"].get("possibilities", [])),
)
ev_none = growth_evidence(signups=False, weak=False)
check(
    "none_of murni: ketiadaan bukti TIDAK pernah menjadi dukungan — rule bahkan tidak matched (citation required)",
    growth_supports(ev_none)["GW-R4"] is None,
)
ev_u = growth_evidence()
sup_u = growth_supports(ev_u)
sup_u["GW-R1"] = RuleSupport(rule_id="GW-R1", tier="deterministic", reason="basis tak dapat dibentuk")
ps_un = build_path_set(growth_space(), growth_reader(sup_u))
check(
    "UNSUPPORTED: rule matched tanpa basis -> TIDAK ada kandidat positif, tercatat di unsupported_knowledge",
    "define_aha_moment" not in dirs(ps_un)
    and any(u["signal"] == "rule:GW-R1" for u in ps_un["generation"]["unsupported_knowledge"]),
    str(ps_un["generation"]["unsupported_knowledge"]),
)
check(
    "UNSUPPORTED: kandidatnya tampil sebagai petunjuk tanpa basis (emerging=UNSUPPORTED), tidak menjadi path",
    poss(ps_un, "define_aha_moment")["emerging"] == "UNSUPPORTED"
    and poss(ps_un, "define_aha_moment")["disposition"] == "UNRESOLVED"
    and poss(ps_un, "define_aha_moment")["status"] == UNDETERMINED,
)
lie = growth_reader({}, None)


def lying_reader(sid):  # a reader that CLAIMS a rule is active without any evidence at all
    if sid == "rule:GW-R1":
        return Signal(True, "klaim aktif tanpa evidence", ())
    return lie(sid)


ps_lie = build_path_set(growth_space(), lying_reader)
check(
    "pembaca mengaku rule aktif tanpa refs -> diturunkan UNSUPPORTED di batas core; tak ada kandidat",
    all(
        p["provenance"].get("candidate") is None
        or "activation_bottleneck" not in p["provenance"]["candidate"]["mechanism_ids"]
        for p in ps_lie["paths"]
    )
    and "define_aha_moment" not in dirs(ps_lie),
)
ps_cf, cs_cf = growth(onboarding=True, retention=True)
act = {a["mechanism_id"]: a for a in ps_cf["generation"]["mechanisms"]}
check(
    "konflik: dukungan (GW-R1) DAN bantahan eksplisit (GW-R3) -> CONFLICT, tidak dipilih diam-diam",
    act["activation_bottleneck"]["status"] == MECH_CONFLICT and act["activation_bottleneck"]["conflicts"],
    str(act["activation_bottleneck"]["status"]),
)
check(
    "konflik terlihat di audit: kandidat CONFLICTED + sengketa menyebut dua sisi",
    poss(ps_cf, "define_aha_moment")["disposition"] == "CONFLICTED"
    and poss(ps_cf, "define_aha_moment")["emerging"] == "CONFLICT"
    and {"supports", "refutes"} <= set(poss(ps_cf, "define_aha_moment")["conflicts"][0]),
)
check(
    "konflik: kandidat yang HANYA bergantung pada mekanisme bersengketa tidak menjadi path",
    "define_aha_moment" not in dirs(ps_cf),
)
check(
    "konflik: mekanisme lain yang berdiri sendiri tetap sah (any_of: onboarding_friction beranjang)",
    "improve_activation_before_acquisition" in dirs(ps_cf)
    and "activation_bottleneck"
    not in path_of(ps_cf, "improve_activation_before_acquisition")["provenance"]["candidate"][
        "mechanism_ids"
    ],
)
ps_rf, _ = growth(weak=False, signups=False, retention=True)
check(
    "bantahan eksplisit tanpa dukungan -> mekanisme REFUTED (False) dan kandidat NOT_EMERGENT, bukan path",
    {a["mechanism_id"]: a["status"] for a in ps_rf["generation"]["mechanisms"]}["activation_bottleneck"]
    == MECH_REFUTED
    and poss(ps_rf, "define_aha_moment")["status"] == NOT_EMERGENT
    and "define_aha_moment" not in dirs(ps_rf),
)
ps_abs, _ = growth(weak=False)
check(
    "absence != evidence of absence: evidence tak ada TIDAK menghasilkan mekanisme/kandidat negatif",
    {a["mechanism_id"]: a["status"] for a in ps_abs["generation"]["mechanisms"]}["activation_bottleneck"]
    == "UNDETERMINED"
    and all(r["status"] != NOT_EMERGENT for r in ps_abs["generation"].get("possibilities", [])),
)

print("── D. Struktur rule: all_of / any_of / none_of / bersarang ──")
ps_all, _ = growth(weak=False, churn=False)
check(
    "all_of: salah satu cabang tak terbukti -> rule tak matched -> tak ada kandidat",
    "define_aha_moment" not in dirs(ps_all),
)
ps_any, _ = growth(weak=False, churn=True)
prov_any = path_of(ps_any, "define_aha_moment")["provenance"]
branches = prov_any["knowledge_support"][0]["branches"]
check(
    "any_of (bersarang di all_of): cabang alternatif cukup; anchor HANYA cabang yang terpenuhi (ev-g-5)",
    "ev-g-5" in prov_any["evidence_ids"]
    and "ev-g-2" not in prov_any["evidence_ids"]
    and any("any_of[1]" in b["branch"] for b in branches),
    str(prov_any["evidence_ids"]),
)
ps_none, _ = growth(strong=True)
check(
    "none_of dalam rule: bukti keberatan eksplisit ('aktivasi sudah kuat') mematikan rule; tak ada kandidat",
    "define_aha_moment" not in dirs(ps_none),
)
check(
    "none_of: tidak membawa anchor positif (ev-g-9 yang tak relevan tidak pernah jadi anchor)",
    "ev-g-9" not in path_of(psn, "define_aha_moment")["provenance"]["evidence_ids"],
)
check(
    "bersarang: all_of > any_of > none_of menghasilkan cabang bernama beranjang per lapis",
    any(
        b["branch"].startswith(".all_of[1].any_of[")
        for b in path_of(psn, "define_aha_moment")["provenance"]["knowledge_support"][0]["branches"]
    ),
)
space_not = dataclasses.replace(
    growth_space(),
    mechanisms=(
        MechanismSpec(
            "activation_bottleneck",
            "An activation bottleneck",
            activated_by={"all_of": ["rule:GW-R1", {"not": "state:aha_defined"}]},
        ),
    )
    + growth_space().mechanisms[1:],
)
ps_n1, _ = growth(space=space_not, states={"state:aha_defined": False})
ps_n2, _ = growth(space=space_not, states={"state:aha_defined": None})
check(
    "predikat mekanisme dengan `not`: aha_defined FALSE terbukti -> aktif; belum diketahui -> tak aktif",
    "define_aha_moment" in dirs(ps_n1) and "define_aha_moment" not in dirs(ps_n2),
)

print("── E. Provenance: Evidence -> Knowledge -> Mechanism -> Candidate -> Path (CAND-02, CAND-06) ──")
ledger_ids = {e.id for e in growth_evidence(onboarding=True)}
cand = imp["provenance"]["candidate"]
check(
    "path membawa provenance.candidate: candidate_id, mechanism_ids, knowledge_ids, evidence_ids, strategy_id",
    cand["candidate_id"] == "cand.improve_activation_before_acquisition"
    and cand["mechanism_ids"]
    and cand["knowledge_ids"]
    and cand["evidence_ids"]
    and imp["provenance"]["strategy_id"] == "improve_activation_before_acquisition"
    and cand["origin"] == ORIGIN_PATTERN,
)
lineage_ev = {r for m in cand["mechanisms"] for r in m["evidence_ids"]}
check(
    "lineage: setiap evidence mekanisme adalah id ledger NYATA (bukan karangan)",
    lineage_ev and lineage_ev <= ledger_ids,
    str(lineage_ev),
)
check(
    "lineage: knowledge_support (rule -> cabang -> evidence) identik dengan yang dilihat evaluator",
    {k["rule_id"] for k in imp["provenance"]["knowledge_support"]} == {"GW-R1", "GW-R2"}
    and all(
        k["evidence_ids"] and set(k["evidence_ids"]) <= ledger_ids
        for k in imp["provenance"]["knowledge_support"]
    ),
)
mech_row = next(r for r in imp["provenance"]["support"] if r["signal"] == "mechanism:activation_bottleneck")
check(
    "mekanisme turunan menyebut dari rule mana ia diturunkan (basis DERIVED -> rule:GW-R1)",
    mech_row["basis"][0]["via"] == ["DERIVED"] and mech_row["basis"][0]["derived_from"] == ["rule:GW-R1"],
)
# reverse direction: remove evidence -> support gone -> mechanism gone -> candidate gone
full = growth_evidence(onboarding=True)
for drop, gone_mech, gone_dir in (
    ("ev-g-2", "activation_bottleneck", "define_aha_moment"),
    ("ev-g-1", "activation_bottleneck", "define_aha_moment"),
    ("ev-g-3", "onboarding_friction", "simplify_onboarding"),
):
    ps_r, _ = growth(evidence=[e for e in full if e.id != drop])
    mech = {a["mechanism_id"]: a["status"] for a in ps_r["generation"]["mechanisms"]}[gone_mech]
    check(
        f"lineage terbalik: cabut {drop} -> mekanisme {gone_mech} tak aktif -> kandidat {gone_dir} hilang",
        mech != MECH_ACTIVE and gone_dir not in dirs(ps_r),
        mech,
    )
ps_alt, _ = growth(evidence=[e for e in growth_evidence(onboarding=True, churn=True) if e.id != "ev-g-2"])
check(
    "cabut evidence yang punya jalur alternatif: dukungan bergeser ke anchor lain (ev-g-5), tak diwariskan ev-g-2",
    "define_aha_moment" in dirs(ps_alt)
    and "ev-g-2" not in path_of(ps_alt, "define_aha_moment")["provenance"]["evidence_ids"],
)
check(
    "validate_path_set menolak path-kandidat tanpa mekanisme / tanpa anchor evidence",
    all(
        raises(lambda m=mut: validate_path_set(_mutated(psn, m)))
        for mut in ("no_mechanism", "no_evidence", "bad_candidate_id")
    ),
)

print("── F. UNSUPPORTED: nol kausalitas positif (CAND-03) ──")
ev_v = growth_evidence(onboarding=True)
valid = growth_supports(ev_v)
flipped = dict(valid)
flipped["GW-R1"] = RuleSupport(rule_id="GW-R1", tier="deterministic", reason="basis tak dapat dibentuk")
ps_valid = build_path_set(growth_space(), growth_reader(valid))
ps_flip = build_path_set(growth_space(), growth_reader(flipped))
ps_absent = build_path_set(growth_space(), growth_reader({k: v for k, v in valid.items() if k != "GW-R1"}))
check(
    "VALID -> UNSUPPORTED: kandidat bergantung GW-R1 kehilangan dukungan positif (path hilang)",
    "define_aha_moment" in dirs(ps_valid) and "define_aha_moment" not in dirs(ps_flip),
)
check(
    "UNSUPPORTED ≡ rule absen untuk PATH (urutan, status, feasibility, provenance identik) — beda hanya di audit",
    [json.dumps(p, sort_keys=True) for p in ps_flip["paths"]]
    == [json.dumps(p, sort_keys=True) for p in ps_absent["paths"]]
    and any(u["signal"] == "rule:GW-R1" for u in ps_flip["generation"]["unsupported_knowledge"])
    and not ps_absent["generation"]["unsupported_knowledge"],
)
check(
    "UNSUPPORTED: tak ada kebocoran tidak langsung — mekanisme tak aktif, kandidat bersandar GW-R1 tak SUPPORTED",
    {a["mechanism_id"]: a["status"] for a in ps_flip["generation"]["mechanisms"]}["activation_bottleneck"]
    != MECH_ACTIVE
    and poss(ps_flip, "define_aha_moment")["status"] != SUPPORTED,
)
proj_flip = build_projection(ps_flip, None, lambda rid: req_mod.describe(rid, "en"), lang="en")
proj_absent = build_projection(ps_absent, None, lambda rid: req_mod.describe(rid, "en"), lang="en")
strip = lambda pr: [  # noqa: E731
    {k: v for k, v in p.items() if k not in ("narrative",)} for p in pr["paths"]
]
check(
    "UNSUPPORTED: readiness (status, counts, butir) identik dengan rule absen — tak ada kenaikan readiness",
    strip(proj_flip) == strip(proj_absent),
)
check(
    "UNSUPPORTED: tidak ada route/NextMove: tanpa route -> select_next_move([]) None",
    all(p["route"] is None for p in proj_flip["paths"]) and select_next_move([]) is None,
)

print("── G. Monotonisitas dan UNKNOWN ──")
pos_items = [
    e
    for e in growth_evidence(onboarding=True, churn=True)
    if e.id in ("ev-g-1", "ev-g-2", "ev-g-3", "ev-g-5")
]
keep = [e for e in growth_evidence(onboarding=True, churn=True) if e.id == "ev-g-9"]
viol = []
subsets = [c for r in range(len(pos_items) + 1) for c in itertools.combinations(pos_items, r)]
res = {}
for sub in subsets:
    ps_s, _ = growth(evidence=list(sub) + keep)
    res[frozenset(e.id for e in sub)] = {
        r["direction"] for r in ps_s["generation"].get("possibilities", []) if r["disposition"] == "PROMOTED"
    }
for a, b in itertools.permutations(res, 2):
    if a < b and not res[a] <= res[b]:
        viol.append((sorted(a), sorted(b)))
check(
    f"monotonisitas: evidence N -> N-1 tak pernah menambah kandidat (semua {len(res)} subset evidence positif)",
    not viol,
    str(viol[:2]),
)
ps_ctr, _ = growth(onboarding=True, strong=True)
check(
    "bukti penyangkal eksplisit tak pernah MENAMBAH dukungan (kandidat ⊆ tanpa penyangkal)",
    {r["direction"] for r in ps_ctr["generation"].get("possibilities", []) if r["disposition"] == "PROMOTED"}
    <= res[frozenset({"ev-g-1", "ev-g-2", "ev-g-3", "ev-g-5"})] | {"simplify_onboarding"},
)
ps_u0, _ = growth(onboarding=True)
ps_u1, _ = growth(onboarding=True, states={"state:acquisition_exists": None})
r_u = poss(ps_u1, "improve_activation_before_acquisition")
check(
    "PRESENT -> UNKNOWN (syarat state): kandidat tidak tetap 'supported' — UNDETERMINED + PARTIAL, bukan path",
    "improve_activation_before_acquisition" in dirs(ps_u0)
    and "improve_activation_before_acquisition" not in dirs(ps_u1)
    and r_u["status"] == UNDETERMINED
    and r_u["emerging"] == "PARTIAL"
    and "state:acquisition_exists" in r_u["missing"],
    str(r_u["missing"]),
)
check(
    "PRESENT -> UNKNOWN: mekanisme tetap beranjang tetapi tidak dijadikan NOT_EMERGENT (UNKNOWN != ABSENT)",
    r_u["refuted"] == [] and r_u["status"] != NOT_EMERGENT,
)
ps_nogoal = build_path_set(growth_space(), growth_reader(growth_supports(ev_v), {"state:revenue_goal": None}))
check(
    "tujuan belum jelas -> NOL path, GOAL_NOT_ESTABLISHED; kandidat tak lahir",
    ps_nogoal["paths"] == [] and ps_nogoal["unresolved"][0]["code"] == "GOAL_NOT_ESTABLISHED",
)

print("── H. Strategi terdeklarasi + pola: gabung provenance, tak ada path ganda ──")
sp_decl = growth_space(with_declared_strategy=True)
ps_both, _ = growth(space=sp_decl, states={"state:aha_undefined": True})
pb = path_of(ps_both, "define_aha_moment")
check(
    "strategi terdeklarasi yang JUGA ditunjuk pola: SATU path, origin BOTH, provenance digabung",
    dirs(ps_both).count("define_aha_moment") == 1
    and pb["provenance"]["candidate"]["origin"] == ORIGIN_BOTH
    and "state:aha_undefined" in pb["provenance"]["state_claims"]
    and "activation_bottleneck" in pb["provenance"]["mechanism_ids"],
)
ps_decl_only, _ = growth(space=sp_decl)
check(
    "strategi terdeklarasi yang tak lahir lewat emerges_when tetap bisa lahir dari pola (origin MECHANISM_PATTERN)",
    path_of(ps_decl_only, "define_aha_moment")["provenance"]["candidate"]["origin"] == ORIGIN_PATTERN,
)
ps_strat_only, _ = growth(space=sp_decl, states={"state:aha_undefined": True}, signups=False, weak=False)
check(
    "strategi terdeklarasi tanpa pola aktif: path murni STRATEGY_DECLARED TANPA blok kandidat (perilaku lama utuh)",
    "candidate" not in path_of(ps_strat_only, "define_aha_moment")["provenance"],
)
check(
    "guard authoring: pola berbagi identitas dengan strategi tak boleh membawa checks/template/eksklusi",
    raises(
        lambda: PossibilitySpace(
            "x",
            (StrategySpec("s1", "S", emerges_when="state:a", no_preconditions=True),),
            patterns=(
                PossibilityPattern(
                    "s1", "S", ("m1",), checks=(CheckSpec("c", "state:c", "prereq", None, "u"),)
                ),
            ),
        )
    ),
)
check(
    "guard authoring: direction ganda, mekanisme bergantung pada mekanisme turunan, sirkular, tanpa mekanisme, template ganda",
    all(
        raises(f)
        for f in (
            lambda: PossibilitySpace(
                "x",
                (),
                patterns=(PossibilityPattern("d", "D", ("m",)), PossibilityPattern("d", "D2", ("n",))),
            ),
            lambda: PossibilitySpace(
                "x",
                (),
                mechanisms=(
                    MechanismSpec("a", activated_by="rule:r"),
                    MechanismSpec("b", activated_by="mechanism:a"),
                ),
            ),
            lambda: MechanismSpec("a", activated_by="mechanism:a"),
            lambda: PossibilityPattern("d", "D", ()),
            lambda: PossibilitySpace(
                "x",
                (),
                patterns=(
                    PossibilityPattern("d1", "D1", ("m",), route_template_ids=("t",)),
                    PossibilityPattern("d2", "D2", ("m",), route_template_ids=("t",)),
                ),
            ),
        )
    ),
)

print("── I. Possible Path 0..N, route-less, dengan route, identitas (CAND-05) ──")
describe = lambda rid: req_mod.describe(rid, "en")  # noqa: E731
proj = build_projection(psn, None, describe, lang="en")
check(
    "route-less: path-kandidat tetap muncul di readiness walau tanpa route/template (PATH-07)",
    [p["strategy_id"] for p in proj["paths"]] == dirs(psn)
    and all(p["route"] is None and p["route_substrate"]["available"] is False for p in proj["paths"]),
)
check(
    "route-less: executability path UNKNOWN (tidak ada route), bukan hilang dan bukan FALSE",
    all(p["executability"] == "UNKNOWN" for p in proj["paths"]),
)
ev_t = growth_evidence(onboarding=True)
sp_t = growth_space(with_template=True)
ps_t = build_path_set(sp_t, growth_reader(growth_supports(ev_t)))
pt = path_of(ps_t, "simplify_onboarding")
lib = [{"template_id": "simplify_onboarding_v1", "strategy_id": "simplify_onboarding"}]
plan = plan_compositions(ps_t["paths"], lib)
check(
    "dengan route: path kandidat -> strategi -> template (strategi-dulu); hanya path ber-template yang dikomposisikan",
    pt["route_substrate"] == {"template_ids": ["simplify_onboarding_v1"], "available": True}
    and [(p["path_id"], t["template_id"]) for p, t in plan]
    == [("path.simplify_onboarding", "simplify_onboarding_v1")],
)
check(
    "template milik strategi lain ditolak deterministik untuk path-kandidat (ROUTE-02)",
    raises(
        lambda: plan_compositions(
            ps_t["paths"], [{"template_id": "simplify_onboarding_v1", "strategy_id": "lain"}]
        ),
        RouteCompositionError,
    ),
)
route = {
    "strategy_id": pt["strategy_id"],
    "path_id": pt["path_id"],
    "route_id": "route-uuid-1",
    "template_id": "simplify_onboarding_v1",
    "applicability": {"status": "APPLIES"},
    "lineage_status": "OPEN",
    "revision_no": 1,
    "nodes": [node("access.icp", "UNKNOWN", "Tulis siapa yang Anda tuju", nid="n1")],
}
proj_r = build_projection(ps_t, {"routes": [route]}, describe, lang="en")
pr_ = next(p for p in proj_r["paths"] if p["strategy_id"] == "simplify_onboarding")
ids = {
    "candidate_id": pr_["candidate"]["candidate_id"],
    "strategy_id": pr_["strategy_id"],
    "path_id": pr_["path_id"],
    "route_id": pr_["route"]["route_id"],
}
check(
    "identitas terpisah per lapis: candidate_id / strategy_id / path_id / route_id — empat nilai berbeda",
    len(set(ids.values())) == 4
    and ids["candidate_id"] == candidate_id_for(ids["strategy_id"])
    and ids["path_id"] == path_id_for(ids["strategy_id"]),
    str(ids),
)
assert_route_keeps_strategy(
    pt,
    {
        "reconciliation_key": {
            "goal_anchor": "g",
            "strategy_id": "simplify_onboarding",
            "scope_anchor": ["state:user"],
        }
    },
)
check(
    "route yang lahir tetap membawa strategy_id (bukan candidate_id) di reconciliation_key (ROUTE-01)",
    raises(
        lambda: assert_route_keeps_strategy(pt, {"reconciliation_key": {"strategy_id": ids["candidate_id"]}}),
        RouteCompositionError,
    ),
)
check(
    "path-kandidat yang routeless tidak menghasilkan NextMove; route (bila ada) satu per path di readiness",
    pr_["route"]["template_id"] == "simplify_onboarding_v1"
    and raises(
        lambda: build_projection(ps_t, {"routes": [route, dict(route, route_id="r2")]}, describe, lang="en")
    )
    is not None,
)
check(
    "readiness membaca PROYEKSI kanonik: kandidat belum-settle tidak pernah menjadi butir requirement",
    all(not any(i["key"].startswith("cand.") for i in p["items"]) for p in proj_r["paths"])
    and all(
        i["state"] in ("PRESENT", "PARTIAL", "UNKNOWN", "ABSENT") for p in proj_r["paths"] for i in p["items"]
    ),
)

print("── J. Readiness: 'why' + possibility yang baru muncul (bukan path) ──")
why = pr_["candidate"]["why"]
check(
    "setiap path lahir-dari-kandidat punya alasan; terkurasi domain bila ada (presentation.because)",
    why["source"] == "curated" and why["text"].startswith("Your first session is confusing"),
    why["text"],
)


def bare(space):  # no curated text: the reason must be derived deterministically from anchored mechanisms
    return dataclasses.replace(
        space, patterns=tuple(dataclasses.replace(p, presentation={}) for p in space.patterns)
    )


ps_bare = build_path_set(bare(sp_t), growth_reader(growth_supports(ev_t)))
why_b = next(
    p
    for p in build_projection(ps_bare, None, describe, lang="en")["paths"]
    if p["strategy_id"] == "simplify_onboarding"
)["candidate"]["why"]
check(
    "tanpa teks terkurasi: fallback deterministik dari mekanisme beranjang (tanpa karangan)",
    why_b["source"] == "fallback" and "onboarding friction" in why_b["text"].lower(),
    why_b["text"],
)
check(
    "path murni strategi: candidate=None (tidak ada klaim asal yang dikarang)",
    next(p for p in build_projection(ps_strat_only, None, describe)["paths"])["candidate"] is None,
)
emerging = build_projection(ps_u1, None, describe, lang="en")["emerging"]
check(
    "possibility baru muncul (mekanisme beranjang, syarat belum diketahui) terproyeksi sebagai UNKNOWN — bukan path",
    [e["direction"] for e in emerging] == ["improve_activation_before_acquisition"]
    and emerging[0]["state"] == "UNKNOWN"
    and "improve_activation_before_acquisition"
    not in [p["strategy_id"] for p in build_projection(ps_u1, None, describe)["paths"]],
    str(emerging),
)
em_cf = build_projection(ps_cf, None, describe, lang="en")["emerging"]
check(
    "possibility bersengketa terproyeksi CONFLICT (dibedakan dari UNKNOWN dan dari path)",
    [e["state"] for e in em_cf] == ["CONFLICT"] and em_cf[0]["conflicts"] == ["activation_bottleneck"],
    str(em_cf),
)
em_un = build_projection(ps_un, None, describe, lang="en")["emerging"]
check(
    "possibility UNSUPPORTED terproyeksi UNSUPPORTED (tak pernah tampil sebagai kemungkinan terverifikasi)",
    em_un
    and all(e["state"] == "UNSUPPORTED" for e in em_un)
    and {e["direction"] for e in em_un} == {"define_aha_moment", "improve_activation_before_acquisition"},
)
check(
    "kebutuhan possibility hanya FAKTA keadaan (state), bukan nama mekanisme/rule",
    [n["text"] for n in emerging[0]["need"]] == ["Acquisition exists is not measured yet"],
    str(emerging[0]["need"]),
)
check(
    "UNKNOWN murni (belum terdeteksi) tidak muncul sama sekali — tidak ada kebisingan",
    build_projection(ps_unk, None, describe)["emerging"] == [],
)
check(
    "tidak ada token mentah (cand./mechanism:/rule:/state:) di teks projeksi yang dilihat pengguna",
    not any(
        tok in json.dumps({k: v for k, v in e.items() if k in ("title", "need")})
        for e in emerging + em_cf + em_un
        for tok in ("cand.", "mechanism:", "rule:", "state:")
    ),
)

print("── K. LEGACY aman: kandidat tak mengubah LEGACY menjadi CURRENT ──")
legacy = {"version": PATHSET_VERSION - 1, "paths": [], "generation": ps_valid["generation"], "unresolved": []}
check(
    "PathSet versi lama + blok kandidat tetap LEGACY (tidak ada migrasi otomatis)",
    assess_path_set(legacy)["status"] == "LEGACY" and assess_path_set(None)["status"] == "LEGACY",
)
proj_l = build_projection(legacy, None, describe)
check(
    "proyeksi LEGACY: paths=[] DAN emerging=[] (isi lama tidak dibaca)",
    proj_l["navigation"]["status"] == "LEGACY" and proj_l["paths"] == [] and proj_l["emerging"] == [],
)
check(
    "PathSet CURRENT dengan blok kandidat tetap CURRENT (aditif — PATHSET_VERSION tak berubah)",
    assess_path_set(ps_valid)["status"] == "CURRENT" and PATHSET_VERSION == 3,
)

print("── L. Domain sintetis kedua: hiring (rule -> mekanisme -> kandidat -> path) tanpa strategi ──")
hs = hiring_candidate_space()
m_hr = growth_supports([])  # not used; hiring uses rule HR-R1 from the fixture
from core.stages.knowledge_rules import evaluate_rule_tier1  # noqa: E402

m = evaluate_rule_tier1(HIRING_RULE, hiring_evidence(), "")
ps_h = build_path_set(hs, hiring_reader(m.support, detect_mechanisms=False))
ph = path_of(ps_h, "calibrate_hiring_bar")
check(
    "hiring: tanpa StrategySpec, tanpa deteksi mekanisme langsung — mekanisme TURUNAN dari rule HR-R1",
    hs.strategies == () and dirs(ps_h) == ["calibrate_hiring_bar"],
    str(dirs(ps_h)),
)
check(
    "hiring: provenance sampai evidence — kandidat -> inconsistent_hiring_bar -> HR-R1 -> ev-hr-1 + ev-hr-2",
    ph["provenance"]["candidate"]["mechanism_ids"] == ["inconsistent_hiring_bar"]
    and ph["provenance"]["candidate"]["knowledge_ids"] == ["HR-R1"]
    and {"ev-hr-1", "ev-hr-2"} <= set(ph["provenance"]["candidate"]["evidence_ids"])
    and "ev-hr-3" not in ph["provenance"]["candidate"]["evidence_ids"],
    str(ph["provenance"]["candidate"]["evidence_ids"]),
)
check(
    "hiring: routeless dan feasibility dari evaluasi (check rubric belum diketahui -> TEST_FIRST)",
    ph["route_substrate"]["available"] is False and ph["status"] == "TEST_FIRST",
)
ps_h0 = build_path_set(hs, hiring_reader(None, detect_mechanisms=False))
check(
    "hiring: tanpa dukungan rule -> NOL path dengan alasan; tanpa kosakata/motion Revenue",
    ps_h0["paths"] == [] and ps_h0["unresolved"] and ph["motion"] is None,
)
leaked = sorted(n for n in sys.modules if n == "domains.revenue" or n.startswith("domains.revenue."))
check(
    "isolasi: rantai growth + hiring penuh (rule, mekanisme, kandidat, evaluasi, readiness) tak memuat Revenue",
    not leaked,
    str(leaked[:3]),
)

print("── M. Isolasi core: tanpa import domain & tanpa identitas strategi domain ──")
core_dir = Path("core/navigation")
bad_imports, bad_ids = [], []
rev_doc = json.loads(Path("ontology/possibility/revenue.json").read_text(encoding="utf-8"))
rev_ids = {s["strategy_id"] for s in rev_doc["strategies"]} | {p["direction"] for p in rev_doc["patterns"]}
rev_ids |= {m for p in rev_doc["patterns"] for m in p["mechanism_ids"]}
rev_ids |= {"REPRICING", "PAID_ACQUISITION", "ACQUISITION", "EXPANSION", "PARTNERSHIP"}
for f in sorted(core_dir.glob("*.py")):
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for node_ in ast.walk(tree):
        mods = []
        if isinstance(node_, ast.Import):
            mods = [a.name for a in node_.names]
        elif isinstance(node_, ast.ImportFrom):
            mods = [node_.module or ""]
        for mod in mods:
            if mod.split(".")[0] in ("domains", "ontology", "engine", "store", "app", "agents"):
                bad_imports.append(f"{f.name}:{mod}")
        if isinstance(node_, ast.Constant) and isinstance(node_.value, str) and node_.value in rev_ids:
            bad_ids.append(f"{f.name}:{node_.value}")
check(
    "core/navigation tidak mengimpor domains/ontology/engine/store/app/agents",
    not bad_imports,
    str(bad_imports),
)
check("core/navigation tidak memuat identitas strategi/mekanisme/motion Revenue", not bad_ids, str(bad_ids))
check(
    "candidate.py ada di core_scope.json (setiap file core/ terkategori)",
    "core/navigation/candidate.py" in Path("ontology/core_scope.json").read_text(encoding="utf-8"),
)

print("── N. Revenue: bukti dunia nyata — kandidat dari mekanisme NYATA, di luar lima strategi lama ──")
from domains.revenue.navigation.paths import build_possible_paths  # noqa: E402
from domains.revenue.navigation.space import revenue_space  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from engine.knowledge import get_kb  # noqa: E402

rs = RevenueState(target_monthly=60, current_monthly=30, willingness_to_pay="PROVEN_AT_CURRENT_PRICE")
rv_base = build_possible_paths(rs, {"level": "TEST_FIRST"})
rv = build_possible_paths(rs, {"level": "TEST_FIRST"}, mechanisms={"lead_leakage": ["ev-7"]})
OLD5 = {"direct_outreach", "value_repricing", "client_expansion", "referral_partnership", "paid_channel_test"}
rv_new = [p for p in rv["paths"] if p["strategy_id"] not in OLD5]
check(
    "Revenue: lima strategi lama tetap utuh; pola tidak mengubah ruang strategi",
    {s.strategy_id for s in revenue_space().strategies} == OLD5 and len(revenue_space().patterns) == 3,
)
check(
    "Revenue: tanpa mekanisme tidak ada kandidat baru; hasil identik dengan sebelum lapisan ini (perilaku lama utuh)",
    all(p["provenance"].get("candidate") is None for p in rv_base["paths"])
    and {p["strategy_id"] for p in rv_base["paths"]} <= OLD5,
)
check(
    "Revenue: lead_leakage terdeteksi (ev-7) -> path BARU di luar lima strategi lama",
    [p["strategy_id"] for p in rv_new] == ["fix_response_before_more_leads"],
    str([p["strategy_id"] for p in rv_new]),
)
rp = rv_new[0]
rc = rp["provenance"]["candidate"]
check(
    "Revenue: provenance mekanisme -> evidence (lead_leakage -> ev-7); sumber knowledge dari KB (pr/ch03)",
    rc["mechanism_ids"] == ["lead_leakage"]
    and "ev-7" in rc["evidence_ids"]
    and {"source_id": "pr", "chapters": ["ch03"]} in rp["provenance"]["knowledge_sources"],
    str(rp["provenance"]["knowledge_sources"]),
)
check(
    "Revenue: routeless (tanpa template) tetap Possible Path sah; belum diuji = TEST_FIRST (bukan OPEN karangan)",
    rp["route_substrate"]["available"] is False
    and rp["status"] == "TEST_FIRST"
    and rp["feasibility_basis"] == "NO_CHECKS_DECLARED",
)
check(
    "Revenue: lima path lama yang lahir tidak ikut terpengaruh oleh mekanisme baru (status identik)",
    {p["strategy_id"]: p["status"] for p in rv["paths"] if p["strategy_id"] in OLD5}
    == {p["strategy_id"]: p["status"] for p in rv_base["paths"]},
)
rv3 = build_possible_paths(
    rs,
    {"level": None},
    mechanisms={"lead_leakage": ["e1"], "targeting_gap": ["e2"], "offer_disconnect": ["e3"]},
)
check(
    "Revenue: tiga mekanisme -> tiga kandidat berbeda (N path, bukan lima tetap)",
    {p["strategy_id"] for p in rv3["paths"]} - OLD5
    == {"fix_response_before_more_leads", "narrow_target_before_volume", "shape_buyable_offer"},
)
kb = get_kb()["interventions"]
from engine.domain_pack import mechanisms as mech_catalog  # noqa: E402

ground_ok = True
for pat in revenue_space().patterns:
    for src in pat.knowledge_sources:
        ground_ok = ground_ok and any(
            i["provenance"]["source_id"] == src["source_id"]
            and i["provenance"]["chapters"] == src["chapters"]
            for i in kb.values()
        )
    for m in pat.mechanism_ids:
        ground_ok = ground_ok and m in mech_catalog()
check(
    "Revenue: setiap pola bersandar pada mekanisme katalog dan sumber KB yang nyata (tak mengarang knowledge)",
    ground_ok,
)
rv_nogoal = build_possible_paths(RevenueState(), {"level": None}, mechanisms={"lead_leakage": ["ev-7"]})
check(
    "Revenue: tujuan belum dinyatakan -> NOL path walau mekanisme terdeteksi (kandidat tak lahir tanpa tujuan)",
    rv_nogoal["paths"] == [] and rv_nogoal["unresolved"],
)
rv_active_rules = build_possible_paths(rs, {"level": None}, mechanisms={"lead_leakage": []})
check(
    "Revenue: mekanisme dilaporkan TANPA evidence -> tak dipakai (UNSUPPORTED), tak ada kandidat",
    all(p["strategy_id"] in OLD5 for p in rv_active_rules["paths"]),
)
rproj = build_projection(rv, None, lambda rid: req_mod.describe(rid, "en"), lang="en")
rpp = next(p for p in rproj["paths"] if p["strategy_id"] == "fix_response_before_more_leads")
check(
    "Revenue: readiness memproyeksikan alasan terkurasi ('kenapa possibility ini ada') + asal kandidat",
    rpp["candidate"]["why"]["source"] == "curated"
    and rpp["candidate"]["origin"] == ORIGIN_PATTERN
    and rpp["candidate"]["evidence_ids"] == ["ev-7"],
    str(rpp["candidate"]),
)

from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.mechanisms import detect_mechanisms  # noqa: E402

led = [
    EvidenceItem(
        id="ev-21",
        signal="lead masuk tapi tidak di-follow selama seminggu",
        level="behavioral",
        topic="MOTION",
    ),
    EvidenceItem(id="ev-22", signal="segmen belum jelas, belum ada icp", level="behavioral", topic="MOTION"),
    EvidenceItem(id="ev-23", signal="kantor di lantai dua", level="behavioral", topic="MOTION"),
]
mech_real = detect_mechanisms(led)
rv_real = build_possible_paths(rs, {"level": None}, mechanisms=mech_real)
new_real = {p["strategy_id"]: p for p in rv_real["paths"] if p["strategy_id"] not in OLD5}
check(
    "Revenue ujung-ke-ujung: evidence ledger -> detect_mechanisms NYATA -> kandidat -> path",
    set(new_real) == {"fix_response_before_more_leads", "narrow_target_before_volume"},
    str(sorted(new_real)),
)
check(
    "Revenue ujung-ke-ujung: provenance kandidat menunjuk id ledger yang membuat mekanisme terdeteksi (bukan ev-23)",
    new_real["fix_response_before_more_leads"]["provenance"]["candidate"]["evidence_ids"] == ["ev-21"]
    and new_real["narrow_target_before_volume"]["provenance"]["candidate"]["evidence_ids"] == ["ev-22"]
    and all("ev-23" not in p["provenance"]["evidence_ids"] for p in new_real.values()),
)
rv_gap = detect_mechanisms([led[0].model_copy(update={"is_gap": True})])
check(
    "Revenue: evidence is_gap bukan dasar mekanisme, sehingga tak melahirkan kandidat",
    "lead_leakage" not in rv_gap,
)

print("── J2. Narasi & Ask/Explain: verified / unknown / conflicted / unsupported tetap terpisah ──")
from agents.ask import readiness_lines  # noqa: E402
from agents.explain import _paths_read  # noqa: E402
from core.navigation.narrative import emerging_lines  # noqa: E402

p_verified = build_projection(psn, None, describe, lang="en")
lines_v = readiness_lines(None, p_verified)
check(
    "Ask: path terverifikasi dibacakan dengan alasan keberadaannya (dari proyeksi, bukan karangan LLM)",
    "why it is on the map: Many people sign up" in lines_v and "possibility (not a path)" not in lines_v,
    lines_v.splitlines()[0][:90],
)
read_by_state = {}
for state, pset in (("UNKNOWN", ps_u1), ("CONFLICT", ps_cf), ("UNSUPPORTED", ps_un)):
    pj = build_projection(pset, None, describe, lang="en")
    txt = readiness_lines(None, pj)
    read_by_state[state] = txt
    check(
        f"Ask/Explain: possibility {state} dibacakan sebagai {state} dan 'NOT a path' — tak pernah kepastian",
        "possibility (not a path)" in txt
        and f"{state}:" in txt
        and "NOT a path" in txt
        and f"{state}:" in _paths_read(pj),
    )
check(
    "Ask/Explain: keempat keadaan (verified/unknown/conflict/unsupported) berbunyi berbeda",
    len({lines_v, *read_by_state.values()}) == 4
    and all(
        read_by_state[a].split("—")[-1] != read_by_state[b].split("—")[-1]
        for a, b in (("UNKNOWN", "CONFLICT"), ("CONFLICT", "UNSUPPORTED"))
    ),
)
check(
    "Ask/Explain: tanpa tanda apa pun tidak ada baris possibility; artefak LEGACY tidak membacanya",
    emerging_lines(build_projection(ps_unk, None, describe)) == []
    and emerging_lines(
        proj_l := build_projection(
            legacy_ps := {"version": 1, "paths": [], "generation": ps_u1["generation"]}, None, describe
        )
    )
    == [],
)
cf_path = next(
    p
    for p in build_projection(
        build_path_set(
            bare(growth_space()),
            growth_reader(growth_supports(growth_evidence(onboarding=True, retention=True))),
        ),
        None,
        describe,
        lang="en",
    )["paths"]
    if p["strategy_id"] == "improve_activation_before_acquisition"
)
check(
    "narasi grounded: alasan path tidak menyebut mekanisme yang BERSENGKETA (hanya yang beranjang aktif)",
    "activation bottleneck" not in cf_path["candidate"]["why"]["text"].lower()
    and "onboarding friction" in cf_path["candidate"]["why"]["text"].lower(),
    cf_path["candidate"]["why"]["text"],
)
check(
    "narasi path-kandidat berasal dari butir proyeksi yang sama: tidak memuat alasan kandidat sebagai klaim keadaan",
    all(p["candidate"]["why"]["text"] not in json.dumps(p["narrative"]) for p in p_verified["paths"]),
)

print("── O. Identitas path baru lolos sintaks identitas yang dipakai store/route ──")
from store.path_states import PATH_ID_RE  # noqa: E402

check(
    "path_id kandidat sah menurut PATH_ID_RE (outcome/lifecycle dapat dilekatkan ke path kandidat)",
    all(PATH_ID_RE.match(p["path_id"]) for p in rv3["paths"] + psn["paths"]),
)


failed = [n for n, ok, _ in _results if not ok]
print("=" * 50)
tail = f" — {len(failed)} GAGAL ❌" if failed else " ✅"
print(f"HASIL: {len(_results) - len(failed)}/{len(_results)} PASS{tail}")
sys.exit(1 if failed else 0)
