"""New domain without touching core: state + knowledge + mechanism + strategy + requirement + template.

internal-docs §15. Proves the principle: a new domain (here "hiring", fictional) arrives
ONLY as data + a signal reader, and traverses the whole chain

    evidence -> knowledge rule -> (mechanism) -> strategy -> Possible Path -> route plan -> Readiness

— including requirements that exist only in the registry. This module deliberately does NOT import
domains.revenue. The cross-domain matrix checks the same invariants over Revenue, SaaS, B2B, zero path.
Deterministic, 0 LLM. Run: .venv/bin/python evals/test_domain_extensibility.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

import engine.requirements as req_mod  # noqa: E402
from core.navigation.contracts import display_status  # noqa: E402
from core.navigation.evaluator import build_path_set  # noqa: E402
from core.navigation.readiness import build_projection  # noqa: E402
from core.stages.knowledge_rules import evaluate_rule_tier1  # noqa: E402
from evals.navigation_fixtures import (  # noqa: E402
    B2B_SPACE,
    HIRING_REQ,
    HIRING_RULE,
    SAAS_SPACE,
    hiring_evidence,
    hiring_reader,
    hiring_space,
    node,
    reader_of,
)
from ontology.route.plan import plan_compositions  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


NEW_REQ = HIRING_REQ  # requirement that exists ONLY in the registry (not pack presentation, not code)
RULE, EVIDENCE, HIRING = HIRING_RULE, hiring_evidence(), hiring_space(with_requirement=True)

m = evaluate_rule_tier1(RULE, EVIDENCE, "")
check("hiring: rule knowledge domain baru dievaluasi oleh interpreter generik (A AND B)", m.matched, m.reason)
by_op = {tuple(b.operand): b.evidence_ids for b in m.support.branches}
check(
    "hiring: cabang A -> ev-hr-1, cabang B -> ev-hr-2 (evidence yang membuat rule TRUE)",
    by_op == {("tanpa rubrik",): ["ev-hr-1"], ("nilai subjektif",): ["ev-hr-2"]},
    str(by_op),
)
ps = build_path_set(HIRING, hiring_reader(m.support))
ids = [p["path_id"] for p in ps["paths"]]
check(
    "hiring: evidence -> knowledge -> mechanism -> strategy -> Possible Path",
    ids == ["path.structured_interviews"],
    str(ids),
)
prov = ps["paths"][0]["provenance"]
check(
    "hiring: provenance memuat rule, mekanisme, dan anchor evidence keduanya",
    prov["knowledge_ids"] == ["HR-R1"]
    and prov["mechanism_ids"] == ["inconsistent_hiring_bar"]
    and {"ev-hr-1", "ev-hr-2"} <= set(prov["evidence_ids"])
    and "ev-hr-3" not in prov["evidence_ids"],
    str(prov["evidence_ids"]),
)
check("hiring: tanpa kosakata/motion Revenue (motion=None)", ps["paths"][0]["motion"] is None)
nope = build_path_set(HIRING, hiring_reader(None))
check(
    "hiring: tanpa dukungan rule -> NOL path dengan alasan (strategi tak lahir karena dugaan)",
    nope["paths"] == [] and nope["unresolved"],
)
check(
    "hiring: strategi yang keadaannya tidak mendukung (network_large FALSE) tidak lahir",
    "referral_hiring" not in [p["strategy_id"] for p in ps["paths"]],
)


ps_net = build_path_set(HIRING, hiring_reader(m.support, network_large=True))
ref = next(p for p in ps_net["paths"] if p["strategy_id"] == "referral_hiring")
check(
    "hiring: strategi yang MENYATAKAN tanpa prasyarat: SUPPORTED, dasarnya bernama (bukan all([]) hampa)",
    (ref["feasibility"], ref["feasibility_basis"]) == ("SUPPORTED", "DECLARED_UNCONDITIONAL"),
)
check(
    "hiring: dua strategi baru lahir bersamaan (jumlah mengikuti keadaan, bukan daftar)",
    len(ps_net["paths"]) == 2,
)

# route substrate: the new template belongs to the new strategy; the composition plan knows no Revenue
tpl_lib = [{"template_id": "structured_interviews_v1", "strategy_id": "structured_interviews"}]
plan = plan_compositions(ps["paths"], tpl_lib)
check(
    "hiring: rencana komposisi strategi-dulu: template milik strategi path",
    [(p["path_id"], t["template_id"]) for p, t in plan]
    == [("path.structured_interviews", "structured_interviews_v1")],
)

# new requirement only in the registry -> Readiness unchanged
saved, fake = req_mod.load_registry, dict(req_mod.load_registry())
fake[NEW_REQ] = {
    "requirement_id": NEW_REQ,
    "definition": "Wawancara memakai rubrik tertulis yang sama untuk semua kandidat.",
    "observability": ["Rubrik tertulis dapat ditunjukkan"],
    "satisfaction_rule": {"mode": "BINARY", "sufficient": "s", "no_decisive": "n", "contradicting": "c"},
    "provenance": {
        "source_id": "tm",
        "chapters": ["ch01"],
        "knowledge_type": "source_claim",
        "confidence": "normative_only",
    },
}
req_mod.load_registry = lambda: fake
try:
    route = {
        "strategy_id": "structured_interviews",
        "path_id": "path.structured_interviews",
        "route_id": "r-1",
        "template_id": "structured_interviews_v1",
        "applicability": {"status": "APPLIES"},
        "lineage_status": "OPEN",
        "revision_no": 1,
        "nodes": [node(NEW_REQ, "UNKNOWN", "Tulis rubrik satu halaman", nid="n1")],
    }
    proj = build_projection(ps, {"routes": [route]}, lambda rid: req_mod.describe(rid, "en"), lang="en")
    item = proj["paths"][0]["items"]
    by_key = {i["key"]: i for i in item}
    check(
        "hiring: requirement registry-only terproyeksi; UNKNOWN tetap UNKNOWN; judul dari fallback id",
        by_key[NEW_REQ]["state"] == "UNKNOWN"
        and by_key[NEW_REQ]["title"]["text"] == "Interview rubric"
        and by_key[NEW_REQ]["title"]["source"] == "fallback",
        str(by_key[NEW_REQ]["title"]),
    )
    check(
        "hiring: check domain baru dan node route dengan requirement yang sama melebur jadi SATU butir",
        len(item) == 1 and by_key[NEW_REQ]["sources"] == ["route", "check"],
    )
finally:
    req_mod.load_registry = saved

leaked = sorted(n for n in sys.modules if n == "domains.revenue" or n.startswith("domains.revenue."))
check(
    "hiring: rantai penuh (rule, generator, evaluator, rencana route, readiness) tidak memuat Revenue",
    not leaked,
    str(leaked[:3]),
)

# ── Cross-domain matrix: the SAME invariants for every domain ──────────────────────────────────────────
saas = reader_of(
    {"state:revenue_goal_set": True, "state:many_signups": True, "state:weak_activation": True},
    {
        "state:weak_activation": ("ev-7",),
        "state:many_signups": ("ev-3",),
        "state:revenue_goal_set": ("ev-0",),
    },
)
b2b = reader_of(
    {"state:revenue_goal_set": True, "state:many_leads": True, "state:poor_decision_maker_access": True},
    {
        "state:many_leads": ("ev-1",),
        "state:poor_decision_maker_access": ("ev-2",),
        "state:revenue_goal_set": ("ev-0",),
    },
)
matrix = {
    "hiring": ps,
    "saas": build_path_set(SAAS_SPACE, saas),
    "b2b": build_path_set(B2B_SPACE, b2b),
    "none": build_path_set(SAAS_SPACE, reader_of({})),
}
for name, pset in matrix.items():
    paths = pset["paths"]
    ok = all(
        p["path_id"] == f"path.{p['strategy_id']}"
        and p["provenance"]["support"]
        and p["status"] == display_status(p["feasibility"], p["lifecycle"])
        for p in paths
    )
    check(
        f"matriks[{name}]: {len(paths)} path; identitas dari strategi; provenance; status dari satu pemetaan",
        ok,
    )
check(
    "matriks: SaaS activation_first lahir tanpa kosakata Revenue",
    [p["path_id"] for p in matrix["saas"]["paths"]] == ["path.activation_first"],
)
check(
    "matriks: B2B decision_maker_access lahir; lead_qualification sah tanpa template route",
    {p["strategy_id"] for p in matrix["b2b"]["paths"]} == {"decision_maker_access", "lead_qualification"},
)
check("matriks: nol path sah dan beralasan", matrix["none"]["paths"] == [] and matrix["none"]["unresolved"])
check(
    "matriks: jumlah path berbeda-beda (tidak ada 'lima')",
    sorted({len(p["paths"]) for p in matrix.values()}) == [0, 1, 2],
)

failed = [n for n, ok, _ in _results if not ok]
print("=" * 50)
tail = f" — {len(failed)} GAGAL ❌" if failed else " ✅"
print(f"HASIL: {len(_results) - len(failed)}/{len(_results)} PASS{tail}")
sys.exit(1 if failed else 0)
