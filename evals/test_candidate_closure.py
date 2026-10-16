"""Closure of the Candidate Possibility layer (internal-docs §23, §24) — architecture
proof, not a Revenue sample.

One file, seven test families, all through PRODUCTION CODE (the real tier-1 rule interpreter,
generator, evaluator, readiness) — no fake candidates/paths, no other logic-bearing helpers:

    A. Generation vs evaluation boundary   candidate = proposal; pattern does not judge; `context_when` != Requirement
    B. Conflicts never vanish            independent support + contested mechanism -> conflict stays visible
    C. Absence (none_of)               absence of record != verified absence; absence evidence must be anchored
    D. Provenance per branch           nested all_of/any_of/none_of; evaluator == trace over ALL shapes
    E. Promotion & identity            candidate_id / strategy_id / path_id / route_id; duplicates; no override
    F. Cardinality 0..N               synthetic domain + Revenue: path count follows evidence, not "five"
    G. Revenue                        five motions = primitive vocabulary, not the Possible Path universe

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_candidate_closure.py
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
    NOT_EMERGENT,
    ORIGIN_BOTH,
    ORIGIN_PATTERN,
    SUPPORTED,
    UNDETERMINED,
    CandidatePossibility,
)
from core.navigation.contracts import (  # noqa: E402
    CheckSpec,
    MechanismSpec,
    PossibilityPattern,
    PossibilitySpace,
    Proposal,
    Signal,
    StrategySpec,
    candidate_id_for,
    path_id_for,
)
from core.navigation.evaluator import build_path_set, evaluate_candidates, validate_path_set  # noqa: E402
from core.navigation.generator import generate_candidates  # noqa: E402
from core.navigation.knowledge import rule_signal  # noqa: E402
from core.navigation.narrative import candidate_line  # noqa: E402
from core.navigation.readiness import build_projection  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.knowledge_rules import evaluate_rule_tier1  # noqa: E402
from core.stages.rule_predicates import (  # noqa: E402
    ABSENCE_OPERATORS,
    evaluate_predicate,
    trace_predicate_audit,
)
from evals.navigation_fixtures import (  # noqa: E402
    growth_evidence,
    growth_reader,
    growth_space,
    growth_supports,
    signals_path_set,
    signals_space,
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


def describe(rid: str):
    return req_mod.describe(rid, "en")


def dirs(ps: dict) -> list[str]:
    return [p["strategy_id"] for p in ps["paths"]]


def path_of(ps: dict, sid: str) -> dict:
    return next(p for p in ps["paths"] if p["strategy_id"] == sid)


def poss(ps: dict, direction: str) -> dict:
    return next(r for r in ps["generation"].get("possibilities", []) if r["direction"] == direction)


def growth(evidence=None, states=None, space=None, **ev_kw):
    evidence = growth_evidence(**ev_kw) if evidence is None else evidence
    reader = growth_reader(growth_supports(evidence), states)
    space = space or growth_space()
    return build_path_set(space, reader), generate_candidates(space, reader)


def E(i: str, text: str, gap: bool = False) -> EvidenceItem:
    return EvidenceItem(id=i, signal=text, level="behavioral", topic="MOTION", is_gap=gap)


def rule_of(predicate: dict, rule_id: str = "R") -> dict:
    return {"rule_id": rule_id, "evaluation": {"tier": "deterministic", "predicate": predicate}}


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── A. Batas generasi vs evaluasi: kandidat = proposal; pola tidak menilai ──")
EVAL_FIELDS = {
    "not_applicable_when",
    "checks",
    "route_template_ids",
    "no_preconditions",
    "knowledge_sources",
    "motion",
    "basis",
}
check(
    "Proposal (satu-satunya yang dilihat generator) tidak memuat satu pun substrat evaluasi",
    not (EVAL_FIELDS & {f.name for f in dataclasses.fields(Proposal)}),
)
RESULT_FIELDS = {
    "applicability",
    "feasibility",
    "checks",
    "route_substrate",
    "executability",
    "lifecycle",
    "path_id",
    "strategy_id",
    "route_id",
    "requirement_id",
    "satisfaction",
    "pattern",
    "readiness",
    "next_move",
}
cand_fields = {f.name for f in dataclasses.fields(CandidatePossibility)}
check(
    "CandidatePossibility tak punya hasil evaluasi, identitas path/route, route, atau substrat pola",
    not (RESULT_FIELDS & cand_fields),
    str(sorted(RESULT_FIELDS & cand_fields)),
)
tree_c = ast.parse(Path("core/navigation/candidate.py").read_text(encoding="utf-8"))
tree_g = ast.parse(Path("core/navigation/generator.py").read_text(encoding="utf-8"))


def attrs_in(tree: ast.AST, fn_name: str) -> set[str]:
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn_name)
    return {a.attr for a in ast.walk(fn) if isinstance(a, ast.Attribute)}


leaks = {
    f"candidate.{fn}": sorted(attrs_in(tree_c, fn) & (EVAL_FIELDS | {"requires"}))
    for fn in ("generate_possibilities", "pattern_predicate", "_mechanism_audit", "_emerging_kind")
}
leaks["generator.generate_candidates"] = sorted(
    attrs_in(tree_g, "generate_candidates") & {"checks", "not_applicable_when", "route_template_ids"}
)
check(
    "AST: fungsi generasi tak membaca satu pun field evaluasi (checks, eksklusi, template) maupun `requires`",
    not any(leaks.values()),
    str({k: v for k, v in leaks.items() if v}),
)
check(
    "`requires` tak ada lagi di pola (bertabrakan dengan Requirement): konteks kemunculan = `context_when`",
    not hasattr(PossibilityPattern, "requires")
    and "context_when" in {f.name for f in dataclasses.fields(PossibilityPattern)},
)


def eval_heavy(space: PossibilitySpace, *, na: bool = True) -> PossibilitySpace:
    """Same patterns, with a completely different EVALUATION substrate: hard checks, exclusions, templates."""
    pats = tuple(
        dataclasses.replace(
            p,
            no_preconditions=False,
            checks=(CheckSpec("gate", "state:gate", "hard", None, "open the gate"),),
            not_applicable_when="state:na" if na else None,
            route_template_ids=(f"tpl_{p.direction}_v1",),
        )
        for p in space.patterns
    )
    return dataclasses.replace(space, patterns=pats)


def gen_sig(cs) -> list:
    return [
        (c.direction, c.status, c.support, c.mechanisms, c.missing, c.missing_detail, c.conflicts, c.refuted, c.emerging)
        for c in cs.possibilities
    ]


ev_a = growth_evidence(onboarding=True)
rd_a = growth_reader(growth_supports(ev_a), {"state:na": True})
cs_base = generate_candidates(growth_space(), rd_a)
cs_heavy = generate_candidates(eval_heavy(growth_space()), rd_a)
check(
    "generasi IDENTIK walau pola membawa checks/eksklusi/template yang sama sekali berbeda (generator buta)",
    gen_sig(cs_base) == gen_sig(cs_heavy) and len(cs_base.possibilities) == 3,
)
ps_base = evaluate_candidates(cs_base, growth_space(), rd_a)
ps_heavy = evaluate_candidates(cs_heavy, eval_heavy(growth_space()), rd_a)
check(
    "evaluator-lah yang menilai: pola dasar -> 3 path; pola ber-eksklusi TRUE -> 0 path (alasan tercatat)",
    len(ps_base["paths"]) == 3
    and ps_heavy["paths"] == []
    and ps_heavy["unresolved"][0]["code"] == "ALL_CANDIDATES_NOT_APPLICABLE"
    and all(poss(ps_heavy, d)["status"] == SUPPORTED for d in ("define_aha_moment", "simplify_onboarding")),
)
rd_a2 = growth_reader(growth_supports(ev_a), {"state:na": False, "state:gate": False})
sp_h2 = eval_heavy(growth_space())
ps_h2 = evaluate_candidates(generate_candidates(sp_h2, rd_a2), sp_h2, rd_a2)
check(
    "feasibility dari check hard ABSENT diputuskan EVALUATOR: path-kandidat STOP (ENGINE_CONTRADICTION), tetap ada",
    len(ps_h2["paths"]) == 3
    and all(p["status"] == "STOP" for p in ps_h2["paths"])
    and all(p["stop_provenance"][0]["source"] == "ENGINE_CONTRADICTION" for p in ps_h2["paths"])
    and all(p["route_substrate"] == {"template_ids": [f"tpl_{p['strategy_id']}_v1"], "available": True} for p in ps_h2["paths"]),
)
check(
    "kandidat tak membawa feasibility/applicability/route walau lahir dari pola ber-substrat evaluasi penuh",
    all(
        not (RESULT_FIELDS & set(c.lineage()) | RESULT_FIELDS & set(c.audit("PROMOTED")))
        for c in cs_heavy.possibilities
    ),
)

space_ctx = PossibilitySpace(
    "ctx",
    (),
    goal_signal="state:goal",
    mechanisms=(MechanismSpec("m1", "Mechanism one", activated_by="rule:R1"),),
    patterns=(
        PossibilityPattern("d1", "Direction one", ("m1",), context_when="state:ctx", no_preconditions=True),
    ),
)
led_ctx = [E("e1", "gejala satu terjadi")]
sup_ctx = evaluate_rule_tier1(rule_of({"text_contains_any": ["gejala satu"]}, "R1"), led_ctx, "").support


def ctx_reader(ctx: bool | None):
    def read(sid: str) -> Signal:
        if sid == "rule:R1":
            return rule_signal("R1", sup_ctx)
        if sid == "state:goal":
            return Signal(True, "goal", ("ev-goal",))
        if sid == "state:ctx":
            return Signal(ctx, "ctx", ("ev-ctx",) if ctx else ())
        return Signal(None)

    return read


c_t, c_f, c_n = (generate_candidates(space_ctx, ctx_reader(v)).possibilities[0] for v in (True, False, None))
check(
    "context_when: TRUE -> SUPPORTED; FALSE -> NOT_EMERGENT; belum diketahui -> UNDETERMINED (PARTIAL, bukan FALSE)",
    (c_t.status, c_f.status, c_n.status) == (SUPPORTED, NOT_EMERGENT, UNDETERMINED) and c_n.emerging == "PARTIAL",
    str((c_t.status, c_f.status, c_n.status)),
)
ps_ctx = build_path_set(space_ctx, ctx_reader(True))
proj_ctx = build_projection(ps_ctx, None, describe, lang="en")
check(
    "context_when BUKAN requirement: tak jadi check, butir readiness, atau requirement_id; readiness tak berubah",
    ps_ctx["paths"][0]["checks"] == []
    and proj_ctx["paths"][0]["items"] == []
    and "requirement_id" not in json.dumps(ps_ctx["paths"][0]["provenance"]["candidate"]),
)
bad_imports = []
for f in ("candidate.py", "generator.py", "evaluator.py", "contracts.py"):
    for node_ in ast.walk(ast.parse(Path("core/navigation", f).read_text(encoding="utf-8"))):
        mods = [a.name for a in node_.names] if isinstance(node_, ast.Import) else (
            [node_.module or ""] if isinstance(node_, ast.ImportFrom) else []
        )
        bad_imports += [f"{f}:{m}" for m in mods if m.split(".")[0] in ("engine", "ontology", "domains")]
check(
    "lapisan kandidat/evaluator tak mengimpor Requirement Registry/engine/ontology/domain (tak ada kamus requirement)",
    not bad_imports,
    str(bad_imports),
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── B. Konflik tidak hilang: dukungan independen + mekanisme bersengketa ──")
ps_cf, cs_cf = growth(onboarding=True, retention=True)
cp_imp = next(c for c in cs_cf.possibilities if c.direction == "improve_activation_before_acquisition")
imp = path_of(ps_cf, "improve_activation_before_acquisition")
cand_b = imp["provenance"]["candidate"]
check(
    "kandidat: tetap SUPPORTED lewat cabang independen (onboarding_friction) DAN membawa sengketa (activation_bottleneck)",
    cp_imp.status == SUPPORTED
    and [c["mechanism_id"] for c in cp_imp.conflicts] == ["activation_bottleneck"]
    and {"supports", "refutes"} <= set(cp_imp.conflicts[0]),
)
check(
    "kedua sisi sengketa beranjang evidence ledger nyata: dukung (ev-g-1, ev-g-2), bantah (ev-g-6)",
    {r for s in cp_imp.conflicts[0]["supports"] for r in s["refs"]} == {"ev-g-1", "ev-g-2"}
    and {r for s in cp_imp.conflicts[0]["refutes"] for r in s["refs"]} == {"ev-g-6"},
)
row_b = poss(ps_cf, "improve_activation_before_acquisition")
check(
    "audit (PROMOTED) dan provenance path membawa sengketa yang sama — tak hilang saat promosi",
    row_b["disposition"] == "PROMOTED"
    and [c["mechanism_id"] for c in row_b["conflicts"]] == ["activation_bottleneck"]
    and [c["mechanism_id"] for c in cand_b["conflicts"]] == ["activation_bottleneck"],
)
mech_status = {m["mechanism_id"]: m["status"] for m in cand_b["mechanisms"]}
check(
    "sengketa BUKAN dukungan: mekanisme bersengketa tak masuk mechanism_ids/evidence path; bantahan tak jadi anchor",
    mech_status == {"activation_bottleneck": MECH_CONFLICT, "onboarding_friction": MECH_ACTIVE}
    and cand_b["mechanism_ids"] == ["onboarding_friction"]
    and imp["provenance"]["mechanism_ids"] == ["onboarding_friction"]
    and "ev-g-6" not in imp["provenance"]["evidence_ids"]
    and "ev-g-1" not in imp["provenance"]["evidence_ids"],
    str(imp["provenance"]["evidence_ids"]),
)
ps_noc, _ = growth(onboarding=True)  # no refuting evidence: activation_bottleneck ACTIVE
ps_und, _ = growth(onboarding=True, signups=False, weak=False)  # activation_bottleneck not yet detected
check(
    "sengketa tidak mengubah feasibility/status path (evaluasi atas check, bukan atas sengketa): sama dengan tanpa-bantahan",
    (imp["feasibility"], imp["status"])
    == (
        path_of(ps_und, "improve_activation_before_acquisition")["feasibility"],
        path_of(ps_und, "improve_activation_before_acquisition")["status"],
    )
    == (
        path_of(ps_noc, "improve_activation_before_acquisition")["feasibility"],
        path_of(ps_noc, "improve_activation_before_acquisition")["status"],
    ),
)
proj_b = build_projection(ps_cf, None, describe, lang="en")
pv_b = next(p for p in proj_b["paths"] if p["strategy_id"] == "improve_activation_before_acquisition")
check(
    "readiness: candidate.unsettled menyebut mekanisme bersengketa; konsisten dengan provenance (satu klasifikasi)",
    [u["mechanism_id"] for u in pv_b["candidate"]["unsettled"]] == ["activation_bottleneck"]
    and pv_b["candidate"]["unsettled"][0]["name"] == "Activation bottleneck"
    and set(pv_b["candidate"]["mechanism_ids"]) == {m for m, s in mech_status.items() if s == MECH_ACTIVE}
    and [u["mechanism_id"] for u in pv_b["candidate"]["unsettled"]]
    == [m for m, s in mech_status.items() if s == MECH_CONFLICT],
)
check(
    "readiness: alasan ('why') hanya menceritakan mekanisme yang AKTIF — kalimat terkurasi per mekanisme",
    pv_b["candidate"]["why"]["source"] == "curated"
    and pv_b["candidate"]["why"]["text"].startswith("Your first session is confusing")
    and "sign up" not in pv_b["candidate"]["why"]["text"],
    pv_b["candidate"]["why"]["text"],
)
check(
    "readiness: sengketa mekanisme bukan butir requirement dan tak menggeser counts",
    all(not i["key"].startswith(("cand.", "mechanism")) for i in pv_b["items"])
    and pv_b["counts"]["conflicted"] == 0,
)
ln = candidate_line(pv_b)
check(
    "narasi/Ask/Explain: baris kandidat menyebut 'NOT settled' + nama mekanisme, dan bukan sebagai bagian alasan",
    "why it is on the map: Your first session is confusing" in ln
    and "NOT settled and NOT part of that reason" in ln
    and "Activation bottleneck" in ln,
    ln,
)
pv_noc = next(
    p
    for p in build_projection(ps_noc, None, describe, lang="en")["paths"]
    if p["strategy_id"] == "improve_activation_before_acquisition"
)
check(
    "tanpa sengketa: tak ada 'unsettled' dan tak ada baris 'NOT settled' (tak ada kebisingan palsu)",
    pv_noc["candidate"]["unsettled"] == [] and "NOT settled" not in candidate_line(pv_noc),
)
check(
    "kandidat yang HANYA bergantung pada mekanisme bersengketa tetap bukan path: possibility CONFLICT (bukan hilang)",
    "define_aha_moment" not in dirs(ps_cf)
    and poss(ps_cf, "define_aha_moment")["disposition"] == "CONFLICTED"
    and [e["state"] for e in proj_b["emerging"]] == ["CONFLICT"],
)
full_b = growth_evidence(onboarding=True, retention=True)
ps_lost, _ = growth(evidence=[e for e in full_b if e.id != "ev-g-3"])  # remove the independent-branch evidence
check(
    "arah terbalik: cabut bukti cabang independen -> path hilang, sengketa TIDAK hilang (jadi possibility CONFLICT)",
    "improve_activation_before_acquisition" not in dirs(ps_lost)
    and poss(ps_lost, "improve_activation_before_acquisition")["emerging"] == "CONFLICT",
)
check(
    "satu realitas: projeksi path/audit/readiness/narasi memakai klasifikasi mekanisme yang sama (ACTIVE vs CONFLICT)",
    {m["mechanism_id"]: m["status"] for m in ps_cf["generation"]["mechanisms"]}
    == {"activation_bottleneck": MECH_CONFLICT, "onboarding_friction": MECH_ACTIVE}
    == mech_status,
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── C. Ketiadaan: absence of record != verified absence; bukti ketiadaan harus beranjang ──")
A_ = {"text_contains_any": ["alpha"]}
B_ = {"text_contains_any": ["beta"]}
X_ = {"text_contains_any": ["refund"]}
lA = [E("e1", "alpha terjadi")]


def tier1(predicate: dict, ledger: list, transcript: str = ""):
    return evaluate_rule_tier1(rule_of(predicate), ledger, transcript)


def asm_of(m) -> list[tuple[str, str]]:
    return [(a.branch, a.operator) for a in (m.support.assumptions if m.support else [])]


for name, pred in (
    ("none_of", {"none_of": [X_]}),
    ("text_absent_pattern", {"text_absent_pattern": "refund"}),
    ("evidence_level_absent", {"evidence_level_absent": ["outcome"]}),
):
    m = tier1(pred, lA)
    check(
        f"ketiadaan SAJA ({name}): tak ada rule matched, tak ada anchor, tak ada dukungan",
        not m.matched and m.support is None,
    )
m_pos = tier1({"all_of": [A_, {"none_of": [X_]}]}, lA)
check(
    "positif beranjang + none_of: SUPPORTED murni dari cabang positif; none_of tak membawa anchor",
    m_pos.matched
    and m_pos.support.status == "SUPPORTED"
    and m_pos.support.evidence_ids == ["e1"]
    and all(b.operator != "none_of" for b in m_pos.support.branches),
)
check(
    "…tetapi ketiadaan yang diandalkan DICATAT sebagai asumsi (NO_MATCHING_RECORD), bukan disajikan terverifikasi",
    asm_of(m_pos) == [(".all_of[1].none_of", "none_of")]
    and m_pos.support.assumptions[0].basis == "NO_MATCHING_RECORD",
    str(asm_of(m_pos)),
)
check(
    "operator ketiadaan lain tercatat sama: text_absent_pattern dan evidence_level_absent",
    asm_of(tier1({"all_of": [A_, {"text_absent_pattern": "refund"}]}, lA))
    == [(".all_of[1].text_absent_pattern", "text_absent_pattern")]
    and asm_of(tier1({"all_of": [A_, {"evidence_level_absent": ["outcome"]}]}, lA))
    == [(".all_of[1].evidence_level_absent", "evidence_level_absent")],
)
check(
    "min_evidence_count adalah ambang jumlah (bukan ketiadaan): tak tercatat sebagai asumsi ketiadaan",
    asm_of(tier1({"all_of": [A_, {"min_evidence_count": 1}]}, lA)) == [],
)
m_expl = tier1(
    {"all_of": [A_, {"text_contains_any": ["belum pernah refund"]}]}, lA + [E("e3", "belum pernah refund sama sekali")]
)
check(
    "BUKTI ketiadaan = cabang positif yang mengutip pernyataan ketiadaan: beranjang (e3), tanpa asumsi ketiadaan",
    m_expl.matched and m_expl.support.evidence_ids == ["e1", "e3"] and asm_of(m_expl) == [],
)
check(
    "ketiadaan dibatalkan oleh catatan yang cocok (X disebut): rule tak matched — constraint tak bisa dipaksa lolos",
    not tier1({"all_of": [A_, {"none_of": [X_]}]}, lA + [E("e2", "ada refund besar")]).matched,
)
check(
    "evidence is_gap yang menyebut X mencegah anggapan ketiadaan (aman): rule tak matched",
    not tier1(
        {"all_of": [A_, {"none_of": [X_]}]}, lA + [E("e9", "tidak tahu soal refund", gap=True)]
    ).matched,
)
m_nest_gap = tier1(
    {"all_of": [A_, {"any_of": [{"none_of": [X_]}, B_]}]}, lA + [E("e2", "beta terjadi", gap=True)]
)
m_nest_ok = tier1({"all_of": [A_, {"any_of": [{"none_of": [X_]}, B_]}]}, lA + [E("e2", "beta terjadi")])
check(
    "bersarang: OR yang hanya tegak berkat none_of (cabang B cuma gap) -> asumsi ketiadaan DIANDALKAN, tercatat",
    m_nest_gap.support.status == "SUPPORTED"
    and m_nest_gap.support.evidence_ids == ["e1"]
    and asm_of(m_nest_gap) == [(".all_of[1].any_of[0].none_of", "none_of")],
    str(asm_of(m_nest_gap)),
)
check(
    "bersarang: OR yang ditopang cabang berjangkar (B anchored) TIDAK bersandar pada ketiadaan -> tak ada asumsi",
    m_nest_ok.support.evidence_ids == ["e1", "e2"] and asm_of(m_nest_ok) == [],
)
check(
    "none_of bersarang (none_of[any_of[X,B]]) tercatat sebagai SATU asumsi dengan operand ringkas",
    asm_of(tier1({"all_of": [A_, {"none_of": [{"any_of": [X_, B_]}]}]}, lA))
    == [(".all_of[1].none_of", "none_of")],
)

# navigation (Kleene): `not` is TRUE only when the negated thing is PROVEN FALSE;
# UNKNOWN/CONFLICT never becomes TRUE
neg_space = PossibilitySpace(
    "neg",
    (),
    goal_signal="state:goal",
    mechanisms=(MechanismSpec("m1", "Mechanism one", activated_by="rule:R1"),),
    patterns=(
        PossibilityPattern(
            "d_neg", "Needs X absent", ("m1",), context_when={"not": "state:x"}, no_preconditions=True
        ),
    ),
)


def neg_reader(x: bool | None, refs: tuple[str, ...] = ()):
    def read(sid: str) -> Signal:
        if sid == "rule:R1":
            return rule_signal("R1", sup_ctx)
        if sid == "state:goal":
            return Signal(True, "goal", ("ev-goal",))
        if sid == "state:x":
            return Signal(x, "x", refs)
        return Signal(None)

    return read


s_unknown, s_false, s_true = (
    generate_candidates(neg_space, neg_reader(v, ("ev-x",) if v is False else ())).possibilities[0]
    for v in (None, False, True)
)
check(
    "ketiadaan TANPA bukti (X belum diketahui): `not X` = UNKNOWN -> kandidat UNDETERMINED, bukan SUPPORTED/NOT_EMERGENT",
    s_unknown.status == UNDETERMINED and s_unknown.refuted == [],
)
check(
    "ketiadaan DENGAN bukti eksplisit (X terbukti FALSE, beranjang): `not X` TRUE; anchor = bukti FALSE itu",
    s_false.status == SUPPORTED and any(r["signal"] == "state:x" and r["refs"] == ["ev-x"] for r in s_false.support),
)
check("X TRUE -> `not X` FALSE -> NOT_EMERGENT", s_true.status == NOT_EMERGENT)
neg_conf = dataclasses.replace(
    growth_space(),
    patterns=growth_space().patterns
    + (
        PossibilityPattern(
            "calm_activation",
            "Calm activation",
            ("onboarding_friction",),
            context_when={"not": "mechanism:activation_bottleneck"},
            no_preconditions=True,
        ),
    ),
)
cs_conf = {c.direction: c for c in generate_candidates(neg_conf, growth_reader(growth_supports(growth_evidence(onboarding=True, retention=True)))).possibilities}
cs_refd = {c.direction: c for c in generate_candidates(neg_conf, growth_reader(growth_supports(growth_evidence(weak=False, signups=False, onboarding=True, retention=True)))).possibilities}
check(
    "konflik != ketiadaan: mekanisme BERSENGKETA bernilai UNKNOWN, jadi `not mekanisme` tak pernah TRUE",
    cs_conf["calm_activation"].status == UNDETERMINED,
    cs_conf["calm_activation"].status,
)
check(
    "bantahan eksplisit (mekanisme REFUTED, beranjang ev-g-6) = bukti ketiadaan yang sah -> `not mekanisme` TRUE",
    cs_refd["calm_activation"].status == SUPPORTED
    and any(r["signal"] == "mechanism:activation_bottleneck" and r["refs"] == ["ev-g-6"] for r in cs_refd["calm_activation"].support),
)
ps_asm, _ = growth(onboarding=True)
pa = path_of(ps_asm, "define_aha_moment")
check(
    "rantai nyata: asumsi ketiadaan GW-R1 (none_of 'aktivasi sudah kuat') sampai ke provenance kandidat DAN path",
    [a["rule_id"] for a in pa["provenance"]["assumed_absences"]] == ["GW-R1"]
    and pa["provenance"]["assumed_absences"] == pa["provenance"]["candidate"]["assumed_absences"]
    and pa["provenance"]["knowledge_support"][0]["assumed_absences"][0]["basis"] == "NO_MATCHING_RECORD"
    and "aktivasi sudah kuat" in pa["provenance"]["assumed_absences"][0]["operand"][0],
)
check(
    "…dan tak pernah jadi anchor: evidence_ids path tak memuat apa pun dari ketiadaan (ev-g-9 tak relevan)",
    "ev-g-9" not in pa["provenance"]["evidence_ids"],
)
pv_asm = next(p for p in build_projection(ps_asm, None, describe, lang="en")["paths"] if p["strategy_id"] == "define_aha_moment")
check(
    "readiness + narasi: path yang bersandar pada ketiadaan catatan ditandai (bukan disajikan sebagai terverifikasi)",
    pv_asm["candidate"]["assumes_absence"] is True and "NOT confirmed" in candidate_line(pv_asm),
)
pv_simple = next(p for p in build_projection(ps_asm, None, describe, lang="en")["paths"] if p["strategy_id"] == "simplify_onboarding")
check(
    "path yang tak bersandar pada ketiadaan (GW-R2 tanpa none_of) tak ditandai",
    pv_simple["candidate"]["assumes_absence"] is False and "NOT confirmed" not in candidate_line(pv_simple),
)
validate_path_set(ps_asm)
check("PathSet dengan asumsi ketiadaan tetap valid (aditif) dan PATHSET_VERSION tak berubah", ps_asm["version"] == 3)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── D. Provenance per cabang: evaluator produksi == trace atas SEMUA bentuk (tanpa helper berlogika lain) ──")
ledger_cases = {
    "kosong": [],
    "A": [E("a", "alpha ada")],
    "B": [E("b", "beta ada")],
    "A+B": [E("a", "alpha ada"), E("b", "beta ada")],
    "A+X": [E("a", "alpha ada"), E("x", "ada refund")],
    "A,B-gap": [E("a", "alpha ada"), E("b", "beta ada", gap=True)],
    "A-gap,B-gap": [E("a", "alpha ada", gap=True), E("b", "beta ada", gap=True)],
    "A+outcome": [E("a", "alpha ada"), EvidenceItem(id="o", signal="hasil", level="outcome", topic="MOTION")],
    "A+B+X": [E("a", "alpha ada"), E("b", "beta ada"), E("x", "ada refund")],
}
LEAVES = [
    {"text_contains_any": ["alpha"]},
    {"text_contains_any": ["beta"]},
    {"none_of": [{"text_contains_any": ["refund"]}]},
    {"text_absent_pattern": "refund"},
    {"evidence_level_absent": ["outcome"]},
    {"min_evidence_count": 1},
]
shapes: list[dict] = []
for op in ("all_of", "any_of"):
    for x, y in itertools.permutations(LEAVES, 2):
        shapes.append({op: [x, y]})
for o1, o2 in itertools.product(("all_of", "any_of"), repeat=2):
    for inner in itertools.permutations(LEAVES[:4], 2):
        for third in LEAVES:
            shapes.append({o1: [{o2: list(inner)}, third]})
            shapes.append({o1: [third, {o2: list(inner)}]})
bad_agree, bad_order, bad_asm, n_eval, n_match = [], [], [], 0, 0
for pred in shapes:
    for lname, ledger in ledger_cases.items():
        ev_ok, cited, _ = evaluate_predicate(pred, ledger, "")
        tr_ok, branches, un_req, assumed = trace_predicate_audit(pred, ledger, "")
        n_eval += 1
        n_match += ev_ok
        if ev_ok != tr_ok:
            bad_agree.append((json.dumps(pred)[:90], lname))
        if assumed and not (ev_ok and all(a.operator in ABSENCE_OPERATORS and a.basis == "NO_MATCHING_RECORD" for a in assumed)):
            bad_asm.append((json.dumps(pred)[:90], lname))
        if tr_ok:
            ids = {i for b in branches for i in b.evidence_ids}
            gap_ids = {e.id for e in ledger if e.is_gap}
            if (ids - gap_ids) != {i for b in branches for i in b.evidence_ids if i not in gap_ids}:
                bad_asm.append(("anchor", lname))
    # child order must not change the outcome (any_of/all_of are commutative)
    key = next(iter(pred))
    flipped = {key: list(reversed(pred[key]))}
    for lname, ledger in ledger_cases.items():
        if evaluate_predicate(pred, ledger, "")[0] != evaluate_predicate(flipped, ledger, "")[0]:
            bad_order.append((json.dumps(pred)[:90], lname))
check(
    f"evaluator == trace untuk setiap bentuk × ledger ({len(shapes)} bentuk × {len(ledger_cases)} ledger = {n_eval} kasus)",
    not bad_agree,
    str(bad_agree[:3]),
)
check(
    "hasil evaluator tidak bergantung urutan anak all_of/any_of (regresi: constraint terpenuhi tak menutupi positif)",
    not bad_order,
    str(bad_order[:3]),
)
check(
    "asumsi ketiadaan hanya ada pada match yang terpenuhi, hanya dari operator ketiadaan, dan tak pernah jadi anchor",
    not bad_asm,
    str(bad_asm[:3]),
)
check(
    "ruang uji tidak vakum: ada bentuk×ledger yang matched DAN yang tidak",
    0 < n_match < n_eval,
    f"{n_match}/{n_eval}",
)
m_or = tier1({"any_of": [{"none_of": [X_]}, A_]}, lA)
check(
    "regresi spesifik: any_of[none_of[X], A] matched (dulu salah-negatif karena constraint di depan menutupi sitasi A)",
    m_or.matched and m_or.support.evidence_ids == ["e1"],
)
m_ab_gap = tier1({"all_of": [A_, B_]}, lA + [E("e2", "beta ada", gap=True)])
check(
    "A beranjang + B hanya gap: rule matched tetapi UNSUPPORTED — satu referensi aggregate tak cukup",
    m_ab_gap.matched and m_ab_gap.support.status == "UNSUPPORTED" and not m_ab_gap.support.anchored,
)
m_ab_tr = tier1({"all_of": [A_, B_]}, lA, "pengguna: beta juga terjadi minggu lalu.")
check(
    "cabang B beranjang kutipan transkrip (bukan ledger): SUPPORTED, anchor B = kutipan (per cabang)",
    m_ab_tr.support.status == "SUPPORTED"
    and m_ab_tr.support.evidence_ids == ["e1"]
    and len(m_ab_tr.support.quotes) == 1
    and [b.quotes for b in m_ab_tr.support.branches] == [[], m_ab_tr.support.quotes],
)
m_nest_un = tier1({"all_of": [{"any_of": [A_, B_]}, {"text_contains_any": ["gamma"]}]}, [
    E("a", "alpha ada", gap=True), E("b", "beta ada", gap=True), E("g", "gamma ada"),
])
check(
    "bersarang: all_of[any_of[A-gap, B-gap], C]: OR tanpa satu pun anak beranjang menggugurkan seluruh rule",
    m_nest_un.matched and m_nest_un.support.status == "UNSUPPORTED",
)
ev_g1_gap = [e if e.id != "ev-g-1" else e.model_copy(update={"is_gap": True}) for e in growth_evidence()]
ps_g1, _ = growth(evidence=ev_g1_gap)
check(
    "rantai: cabang wajib GW-R1 (ev-g-1) hanya gap -> rule UNSUPPORTED -> mekanisme tak aktif -> kandidat tak lahir",
    "define_aha_moment" not in dirs(ps_g1)
    and any(u["signal"] == "rule:GW-R1" for u in ps_g1["generation"]["unsupported_knowledge"]),
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── E. Promosi & identitas: candidate_id / strategy_id / path_id / route_id, duplikat, tak ada timpa ──")
ps_e, cs_e = growth(onboarding=True)
ids_e = []
for p in ps_e["paths"]:
    ids_e += [
        p["provenance"]["candidate"]["candidate_id"],
        p["strategy_id"],
        p["path_id"],
    ]
check(
    "identitas tiga lapis berbeda untuk setiap path-kandidat dan tak saling bertabrakan (cand.* / <arah> / path.*)",
    len(set(ids_e)) == len(ids_e) == 3 * len(ps_e["paths"])
    and all(
        p["provenance"]["candidate"]["candidate_id"] == candidate_id_for(p["strategy_id"])
        and p["path_id"] == path_id_for(p["strategy_id"])
        for p in ps_e["paths"]
    ),
)
check(
    "arah ber-titik/berprefiks (cand./path.) ditolak saat authoring: identitas tak bisa disamarkan sebagai lapis lain",
    all(raises(lambda d=d: PossibilityPattern(d, "x", ("m",))) for d in ("cand.x", "path.x", "a.b", "x y", "")),
)
check(
    "setiap path-kandidat mempertahankan jangkar tujuan, mekanisme, basis knowledge, dan dukungan (tak ada yang jatuh)",
    all(
        any(r["signal"] == "state:revenue_goal" for r in p["provenance"]["support"])
        and p["provenance"]["candidate"]["mechanism_ids"]
        and p["provenance"]["candidate"]["knowledge_ids"]
        and {r["signal"] for r in p["provenance"]["candidate"]["support"]}
        <= {r["signal"] for r in p["provenance"]["support"]}
        and p["provenance"]["candidate"]["origin"] == ORIGIN_PATTERN
        for p in ps_e["paths"]
    ),
)
check(
    "tak ada path ganda: path_id unik (validate_path_set menolak duplikat) dan satu arah = satu path",
    len({p["path_id"] for p in ps_e["paths"]}) == len(ps_e["paths"])
    and bool(raises(lambda: validate_path_set({**ps_e, "paths": ps_e["paths"] + ps_e["paths"][:1]}))),
)
strat_dormant = StrategySpec(
    "define_aha_moment",
    "Define the aha moment (declared)",
    emerges_when="state:aha_undefined",
    not_applicable_when="state:declared_exclusion",
    checks=(CheckSpec("declared_check", "state:declared_check", "prereq", None, "declared unlock"),),
    route_template_ids=("declared_tpl_v1",),
)
sp_dorm = dataclasses.replace(
    growth_space(),
    strategies=(strat_dormant,),
    patterns=tuple(
        dataclasses.replace(p, no_preconditions=False) if p.direction == "define_aha_moment" else p
        for p in growth_space().patterns
    ),
)
ps_dorm, _ = growth(space=sp_dorm, onboarding=True)
pd_ = path_of(ps_dorm, "define_aha_moment")
check(
    "strategi terdeklarasi dorman + pola: SATU path; evaluasi = milik strategi (check/template), asal = pola; tak ditimpa",
    dirs(ps_dorm).count("define_aha_moment") == 1
    and [c["check_id"] for c in pd_["checks"]] == ["declared_check"]
    and pd_["route_substrate"]["template_ids"] == ["declared_tpl_v1"]
    and pd_["provenance"]["candidate"]["origin"] == ORIGIN_PATTERN,
)
ps_dorm_na, _ = growth(space=sp_dorm, onboarding=True, states={"state:declared_exclusion": True})
check(
    "eksklusi strategi terdeklarasi tetap berlaku bagi kandidat dari pola (evaluator memutuskan, pola tak mengganti)",
    "define_aha_moment" not in dirs(ps_dorm_na)
    and poss(ps_dorm_na, "define_aha_moment")["disposition"] == "REJECTED_NOT_APPLICABLE",
)
ps_dorm_both, _ = growth(space=sp_dorm, onboarding=True, states={"state:aha_undefined": True})
pb_ = path_of(ps_dorm_both, "define_aha_moment")
sigs_b = [r["signal"] for r in pb_["provenance"]["support"]]
check(
    "strategi + pola sama-sama lahir: SATU path, origin BOTH, dukungan digabung tanpa baris ganda",
    dirs(ps_dorm_both).count("define_aha_moment") == 1
    and pb_["provenance"]["candidate"]["origin"] == ORIGIN_BOTH
    and len(sigs_b) == len(set(sigs_b))
    and {"state:aha_undefined", "mechanism:activation_bottleneck"} <= set(sigs_b),
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── F. Kardinalitas 0..N: jumlah path mengikuti bukti — domain sintetis 'signals' (tanpa StrategySpec) ──")
counts: dict[int, int] = {}
for n, active in (
    (0, []),
    (1, [0]),
    (2, [0, 1]),
    (3, [0, 1, 2]),
    (3, [0, 2]),
    (4, [0, 1, 2, 3]),
    (5, [0, 1, 2, 3, 4]),
    (6, list(range(6))),
    (8, list(range(8))),
    (10, list(range(10))),
    (13, list(range(13))),
):
    ps_n = signals_path_set(n, active)
    counts.setdefault(len(active), len(ps_n["paths"]))
    assert counts[len(active)] == len(ps_n["paths"])
    if n in (0, 3, 6, 13):
        check(
            f"signals n={n}, bukti untuk {len(active)} gejala -> engine mengembalikan TEPAT {len(active)} path",
            len(ps_n["paths"]) == len(active)
            and (len(ps_n["paths"]) > 0 or bool(ps_n["unresolved"]))
            and all(p["provenance"]["candidate"]["evidence_ids"] for p in ps_n["paths"]),
        )
check(
    "kardinalitas bebas: 0,1,2,3,4,5,6,8,10,13 semuanya diproduksi engine apa adanya (tak ada 5, tak ada 10)",
    counts == {k: k for k in (0, 1, 2, 3, 4, 5, 6, 8, 10, 13)},
    str(counts),
)
ps_mixed = signals_path_set(10, [1, 4, 7])
check(
    "10 arah dikenal, 3 terbukti -> 3 path; 7 sisanya 'belum terdeteksi' (bukan NOT_EMERGENT: UNKNOWN != ABSENT)",
    dirs(ps_mixed) == ["direction_1", "direction_4", "direction_7"]
    and len(ps_mixed["generation"]["undetermined"]) == 7
    and not ps_mixed["generation"]["not_emergent"],
)
ps_nog = signals_path_set(6, [0, 1, 2])
from evals.navigation_fixtures import signals_ledger, signals_reader  # noqa: E402

ps_nogoal = build_path_set(signals_space(6), signals_reader(6, signals_ledger([0, 1, 2]), goal=False))
check(
    "tujuan belum dinyatakan -> NOL path walau semua gejala terbukti (alasan eksplisit, tak ada path karangan)",
    len(ps_nog["paths"]) == 3 and ps_nogoal["paths"] == [] and ps_nogoal["unresolved"][0]["code"] == "GOAL_NOT_ESTABLISHED",
)
ps_rl = signals_path_set(8, list(range(8)), templates={1: "tpl_dir_1", 5: "tpl_dir_5"})
check(
    "route-less vs ber-template bercampur dalam satu PathSet 8 path: hanya yang punya substrat 'available'",
    {p["strategy_id"]: p["route_substrate"]["available"] for p in ps_rl["paths"]}
    == {f"direction_{i}": i in (1, 5) for i in range(8)},
)
proj8 = build_projection(ps_rl, None, describe, lang="en")
check(
    "readiness memproyeksikan SEMUA 8 path (tak ada pemotongan di engine/proyeksi); route-less tetap muncul",
    [p["strategy_id"] for p in proj8["paths"]] == dirs(ps_rl) and len(proj8["paths"]) == 8,
)

from agents.explain import PATHS_CAP, _paths_read  # noqa: E402

proj13 = build_projection(signals_path_set(13, list(range(13))), None, describe, lang="en")
read13 = _paths_read(proj13)
proj_small = build_projection(signals_path_set(4, [0, 1, 2]), None, describe, lang="en")
check(
    "konteks LLM (Explain) adalah anggaran prompt, bukan batas engine: 13 path -> 10 dibacakan + pengungkapan eksplisit",
    sum(1 for ln in read13.splitlines() if ln.startswith("- path ")) == PATHS_CAP == 10
    and "3 more paths exist that are NOT described here" in read13
    and "Do not say how many paths there are" in read13,
)
check(
    "…dan tanpa pemotongan tak ada pengungkapan palsu (3 path -> 3 dibacakan, tanpa kalimat 'more paths')",
    sum(1 for ln in _paths_read(proj_small).splitlines() if ln.startswith("- path ")) == 3
    and "more paths exist" not in _paths_read(proj_small),
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── G. Revenue: lima motion = kosakata primitive domain, BUKAN semesta Possible Path ──")
from domains.revenue.navigation.paths import build_possible_paths  # noqa: E402
from domains.revenue.navigation.space import revenue_space  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from ontology.route.strategies import load_motion_vocabulary  # noqa: E402

MOTIONS = set(load_motion_vocabulary())
FULL = dict(
    current_monthly=30.0,
    target_monthly=60.0,
    gap_monthly=30.0,
    capacity_utilization=0.5,
    willingness_to_pay="PROVEN_AT_CURRENT_PRICE",
    demand_exists=True,
    avg_deal_size=10.0,
)
M1 = {"lead_leakage": ["ev-7"]}
M3 = {"lead_leakage": ["ev-7"], "targeting_gap": ["ev-8"], "offer_disconnect": ["ev-9"]}


def rev(mech, **state):
    return build_possible_paths(RevenueState(**state), {"level": None}, mechanisms=mech)


check(
    "A. lima motion tetap kosakata primitive (ACQUISITION, REPRICING, EXPANSION, PARTNERSHIP, PAID_ACQUISITION)",
    MOTIONS == {"ACQUISITION", "REPRICING", "EXPANSION", "PARTNERSHIP", "PAID_ACQUISITION"},
)
r0 = rev(None, target_monthly=60.0)
r1 = rev(M1, target_monthly=60.0)
r3 = rev(M3, target_monthly=60.0)
r5 = rev(None, **FULL)
r8 = rev(M3, **FULL)
check(
    "B. bukti mendukung SATU kemungkinan -> engine 1 path (lead_leakage), bukan lima",
    dirs(r1) == ["fix_response_before_more_leads"] and r0["paths"] == [] and r0["unresolved"],
    str(dirs(r1)),
)
check(
    "C. bukti mendukung TIGA -> engine 3 path (ketiganya di luar lima strategi lama; tak ada filler)",
    sorted(dirs(r3)) == ["fix_response_before_more_leads", "narrow_target_before_volume", "shape_buyable_offer"]
    and all(p["motion"] is None for p in r3["paths"]),
)
check(
    "D. bukti mendukung DELAPAN -> engine 8 path (5 strategi + 3 kandidat), bukan 5",
    len(r8["paths"]) == 8 and len(r5["paths"]) == 5 and set(dirs(r5)) < set(dirs(r8)),
    str((len(r5["paths"]), len(r8["paths"]))),
)
check(
    "hanya 5 path yang membawa label motion; 3 sisanya motion=None — motion atribut informasi, bukan identitas",
    sorted(p["motion"] for p in r8["paths"] if p["motion"]) == sorted(MOTIONS)
    and sum(1 for p in r8["paths"] if p["motion"] is None) == 3,
)
check(
    "jumlah path Revenue yang teramati {0,1,3,5,8}: tak satu pun jumlah dipaksa; semesta tidak dikunci pada lima",
    sorted({len(r["paths"]) for r in (r0, r1, r3, r5, r8)}) == [0, 1, 3, 5, 8],
)
check(
    "ruang Revenue: 5 strategi terdeklarasi + 3 pola kandidat = substrat; tak ada daftar path (path lahir dari bukti)",
    len(revenue_space().strategies) == 5 and len(revenue_space().patterns) == 3,
)

failed = [n for n, ok, _ in _results if not ok]
print("=" * 50)
tail = f" — {len(failed)} GAGAL ❌" if failed else " ✅"
print(f"HASIL: {len(_results) - len(failed)}/{len(_results)} PASS{tail}")
sys.exit(1 if failed else 0)
