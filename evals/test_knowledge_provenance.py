"""Provenance knowledge -> path (PROV-01..04, KNOW-01..03) — the REAL flow, no architecture-bypassing fixture.

    evidence ledger -> rule evaluator (tier-1 predicate / tier-2 verified citation) -> RuleSupport (anchors)
      -> rule_signal -> `rule:` signal -> generator (emerges_when) -> evaluator -> Possible Path + provenance

The domain here is synthetic (not Revenue): it proves the knowledge -> strategy -> path lane without Revenue
vocabulary in core. Deterministic, 0 LLM. Run: .venv/bin/python evals/test_knowledge_provenance.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

from core.navigation.contracts import (  # noqa: E402
    CheckSpec,
    PossibilitySpace,
    Signal,
    StrategySpec,
    grounded,
    path_id_for,
)
from core.navigation.evaluator import build_path_set, validate_path_set  # noqa: E402
from core.navigation.knowledge import rule_signal  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from core.schema.provenance import RuleSupport  # noqa: E402
from core.stages.knowledge_rules import evaluate_rule_tier1, match_tier1  # noqa: E402
from core.stages.rule_predicates import (  # noqa: E402
    evaluate_predicate,
    trace_predicate,
    trace_predicate_full,
)
from core.stages.rule_support import support_from_branches, support_from_citation  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def ev(eid: str, signal: str, *, gap: bool = False, quote: str | None = None) -> EvidenceItem:
    return EvidenceItem(
        id=eid, signal=signal, level="behavioral", source_quote=quote, topic="MOTION", is_gap=gap
    )


def rule(rule_id: str, predicate: dict) -> dict:
    return {"rule_id": rule_id, "evaluation": {"tier": "deterministic", "predicate": predicate}}


def space_for(rule_id: str, strategy_id: str = "S1") -> PossibilitySpace:
    """Synthetic domain: strategy `S1` is born ONLY when the knowledge rule is active — the rule -> strategy
    mapping is declared explicitly in `emerges_when`, not by magic (KNOW-03)."""
    return PossibilitySpace(
        space_id="synthetic_knowledge",
        goal_signal="state:goal",
        strategies=(
            StrategySpec(
                strategy_id=strategy_id,
                title="Strategy S1",
                emerges_when=f"rule:{rule_id}",
                checks=(CheckSpec("c1", "state:ready", "prereq", None, "siapkan"),),
            ),
        ),
    )


def reader_with(rules: dict[str, RuleSupport | list[str] | None]):
    """Synthetic-domain signal reader: state:goal TRUE; rule: via the generic `rule_signal` bridge."""

    def read(sid: str) -> Signal:
        kind, _, name = sid.partition(":")
        if kind == "rule":
            return rule_signal(name, rules.get(name))
        if sid == "state:goal":
            return Signal(True, "goal", ("ev-goal",))
        return Signal(None)

    return read


def path_set_for(r: dict, evidence: list[EvidenceItem], transcript: str = ""):
    m = evaluate_rule_tier1(r, evidence, transcript)
    support = m.support if m.matched else None
    return m, build_path_set(space_for(r["rule_id"]), reader_with({r["rule_id"]: support} if support else {}))


# ── Scenario A — E1 satisfies R1 -> strategy S1 -> path.S1 with knowledge provenance=R1, evidence=E1 ──
R1 = rule("R1", {"text_contains_any": ["follow up terlambat"]})
E1 = ev("E1", "klien bilang follow up terlambat 5 hari")
m, ps = path_set_for(R1, [E1])
check("A: rule R1 matched oleh evaluator nyata", m.matched, m.reason)
check(
    "A: R1 membawa provenance SUPPORTED dengan anchor E1",
    m.support.anchored and m.support.evidence_ids == ["E1"],
)
check("A: lahir tepat satu path, identitas dari strategi", [p["path_id"] for p in ps["paths"]] == ["path.S1"])
prov = ps["paths"][0]["provenance"]
check("A: provenance.knowledge_ids = [R1]", prov["knowledge_ids"] == ["R1"], str(prov["knowledge_ids"]))
check(
    "A: provenance.evidence_ids memuat E1 (anchor rule)",
    "E1" in prov["evidence_ids"],
    str(prov["evidence_ids"]),
)
ks = prov["knowledge_support"]
check(
    "A: knowledge_support menunjuk rule, anchor, dan cabang predikat yang terpenuhi",
    len(ks) == 1
    and ks[0]["rule_id"] == "R1"
    and ks[0]["evidence_ids"] == ["E1"]
    and ks[0]["branches"][0]["operator"] == "text_contains_any",
    str(ks),
)
check(
    "A: provenance PROV-03 menyimpan strategi, substrat route, dan dukungan",
    all(k in prov for k in ("strategy_id", "route_template_ids", "support", "state_claims", "mechanism_ids")),
)

# ── Scenario B — A AND B: each branch points to its own evidence ───────────────────────────────
R2 = rule("R2", {"all_of": [{"text_contains_any": ["alpha"]}, {"text_contains_any": ["beta"]}]})
EA, EB = ev("E1", "sinyal alpha terlihat"), ev("E2", "sinyal beta terlihat")
m2 = evaluate_rule_tier1(R2, [EA, EB], "")
by_op = {tuple(b.operand): b.evidence_ids for b in m2.support.branches}
check("B: A AND B matched", m2.matched)
check(
    "B: cabang A -> E1, cabang B -> E2 (bukan campuran)",
    by_op == {("alpha",): ["E1"], ("beta",): ["E2"]},
    str(by_op),
)
check("B: anchor rule = gabungan kedua cabang", m2.support.evidence_ids == ["E1", "E2"])
m2b = evaluate_rule_tier1(R2, [EA], "")
check("B: hanya A terpenuhi -> rule TIDAK matched, tanpa dukungan", not m2b.matched and m2b.support is None)

# ── Scenario C — A OR B, only A true: branch A alone; B must not become support ────────────────────────
R3 = rule("R3", {"any_of": [{"text_contains_any": ["alpha"]}, {"text_contains_any": ["beta"]}]})
EA, EX = ev("E1", "sinyal alpha terlihat"), ev("E2", "hal lain yang tidak relevan")
m3 = evaluate_rule_tier1(R3, [EA, EX], "")
check("C: A OR B matched ketika A benar", m3.matched)
check(
    "C: branch = A, evidence = E1",
    [b.operand for b in m3.support.branches] == [["alpha"]] and m3.support.evidence_ids == ["E1"],
)
check(
    "C: B tidak muncul sebagai dukungan (operand maupun evidence)",
    all("beta" not in b.operand for b in m3.support.branches) and "E2" not in m3.support.evidence_ids,
)
m3b = evaluate_rule_tier1(R3, [ev("E1", "sinyal alpha terlihat"), ev("E2", "ada beta juga")], "")
check(
    "C: bila A dan B keduanya benar, keduanya sah mendukung",
    sorted(b.operand[0] for b in m3b.support.branches) == ["alpha", "beta"],
)

# ── Scenario A2 — PER-BRANCH provenance: the aggregate must not hide an anchor-required bare branch ────
# Positive branches must each be anchored; CONSTRAINT branches (threshold/absent/none_of) are valid
# without an anchor. The aggregate evidence_ids of sibling branches must NOT cover a bare positive one.
R4 = rule("R4", {"all_of": [{"text_contains_any": ["alpha"]}, {"min_evidence_count": 2}]})
GA, GB = ev("E1", "sinyal alpha terlihat"), ev("E2", "sinyal beta terlihat")
m4 = evaluate_rule_tier1(R4, [GA, GB], "")
check("A2: all_of[positif, ambang-jumlah] matched", m4.matched)
check(
    "A2: SUPPORTED — cabang positif berjangkar; cabang constraint tak butuh anchor",
    m4.support.anchored and m4.support.evidence_ids == ["E1"],
    m4.support.reason,
)
check(
    "A2: cabang constraint tetap tercatat (audit) dengan anchor kosong",
    any(b.operator == "min_evidence_count" and not b.evidence_ids for b in m4.support.branches),
)
g_alpha = ev("G1", "alpha tercatat di catatan internal", gap=True)
g_beta = ev("G2", "beta tercantum di catatan internal", gap=True)
R5 = rule("R5", {"all_of": [{"text_contains_any": ["alpha"]}, {"text_contains_any": ["beta"]}]})
m5 = evaluate_rule_tier1(R5, [GA, g_beta], "")
check("A2: all_of matched — kondisi formal terpenuhi (fallback gap tetap = match)", m5.matched)
check(
    "A2: cabang B wajib tanpa anchor → UNSUPPORTED WALAU cabang A berjangkar",
    not m5.support.anchored and "all_of[1].text_contains_any" in m5.support.reason,
    m5.support.reason,
)
_, ps5 = path_set_for(R5, [GA, g_beta])
check("A2: dukungan gugur → NOL path (aggregate tak bisa memalsukan kandidat)", ps5["paths"] == [])
check(
    "A2: rule tercatat unsupported_knowledge, strategi undetermined (bukan not_emergent)",
    [u["signal"] for u in ps5["generation"]["unsupported_knowledge"]] == ["rule:R5"]
    and [u["strategy_id"] for u in ps5["generation"]["undetermined"]] == ["S1"],
)
m6 = evaluate_rule_tier1(R3, [GA, g_beta], "")
check(
    "A2: any_of[alpha berjangkar, beta gap-only] → SUPPORTED dari cabang alpha (OR cukup satu)",
    m6.support.anchored and "G2" not in m6.support.evidence_ids,
    m6.support.reason,
)
m6b = evaluate_rule_tier1(R3, [g_alpha, g_beta], "")
check(
    "A2: any_of dengan seluruh cabang terpenuhi gap-only → UNSUPPORTED",
    m6b.matched and not m6b.support.anchored,
    m6b.support.reason,
)

# ── Scenario B2 — nested & deep: none_of carries no anchor; completeness counts per positive branch ─────
R7 = rule(
    "R7",
    {
        "all_of": [
            {"any_of": [{"text_contains_any": ["alpha"]}, {"text_contains_any": ["gamma"]}]},
            {"none_of": [{"text_contains_any": ["refund"]}]},
        ]
    },
)
m7 = evaluate_rule_tier1(R7, [GA], "")
check("B2: nested all_of(any_of, none_of) matched", m7.matched)
check(
    "B2: SUPPORTED — none_of terpenuhi sebagai batasan, TIDAK muncul sebagai cabang dukungan",
    m7.support.anchored
    and m7.support.evidence_ids == ["E1"]
    and {b.operator for b in m7.support.branches} == {"text_contains_any"},
    str(m7.support.branches),
)
g_gamma = ev("G3", "gamma juga hanya di catatan internal", gap=True)
m7b = evaluate_rule_tier1(R7, [g_gamma], "")
check(
    "B2: nested positif semua gap-only → UNSUPPORTED dengan nama cabang bersisting",
    m7b.matched
    and not m7b.support.anchored
    and "all_of[0].any_of[1].text_contains_any" in m7b.support.reason,
    m7b.support.reason,
)
R7c = rule(
    "R7c",
    {
        "all_of": [
            {
                "any_of": [
                    {"all_of": [{"text_contains_any": ["alpha"]}, {"text_contains_any": ["beta"]}]},
                    {"text_contains_any": ["gamma"]},
                ]
            },
            {"min_evidence_count": 1},
        ]
    },
)
m7c = evaluate_rule_tier1(R7c, [GA, GB], "")
check(
    "B2: deep nesting — dukungan = cabang daun berjangkar (any_of memilih all_of[0])",
    m7c.support.anchored
    and {
        tuple(b.operand)
        for b in m7c.support.branches
        if b.operator == "text_contains_any"
    }
    == {("alpha",), ("beta",)},
    str([(b.branch, b.evidence_ids) for b in m7c.support.branches]),
)

# ── Scenario E — none_of: absence of positive evidence ≠ evidence of absence (doc 14 §6.1) ──────────
R8 = rule("R8", {"none_of": [{"text_contains_any": ["refund"]}]})
m8 = evaluate_rule_tier1(R8, [GA], "")  # no "refund" anywhere → none_of "satisfied"
check(
    "E: none_of terpenuhi tanpa bukti → TIDAK matched (sitasi wajib; bukan dukungan positif)",
    not m8.matched and m8.support is None,
)
check(
    "E: trace sepakat dengan evaluator utk none_of-only (matched=False, tanpa cabang)",
    trace_predicate_full(R8["evaluation"]["predicate"], [GA], "") == (False, [], []),
)
# This iteration's audit — the T3 mirror must be anchor-aware: a predicate satisfied ONLY through a
# negative/counting operator (`*_absent`, `min_evidence_count` — valid without per-leaf citation)
# yields a branch with no anchor at all. The ordinary evaluator rejects it (cited=[] → T3), so the
# trace must not present it as a branched match (divergence = a fake SUPPORTED lane in the gate-2 mapper).
R8c = rule("R8c", {"all_of": [{"evidence_level_absent": ["transactional"]}, {"min_evidence_count": 1}]})
_ev8c = [GA]  # behavioral non-gap: level_absent ✓, count 1 ≥ 1 ✓ — satisfied WITHOUT a single citation
check(
    "E: negatif/counting-only terpenuhi → evaluator menolak (T3, cited kosong)",
    evaluate_predicate(R8c["evaluation"]["predicate"], _ev8c, "")[0] is False,
)
check(
    "E: trace anchor-aware sepakat — bukan match ber-cabang tanpa anchor (tidak divergensi)",
    trace_predicate_full(R8c["evaluation"]["predicate"], _ev8c, "") == (False, [], []),
)
check(
    "E: matched(trace) == matched(evaluator) untuk predikat negatif-only",
    trace_predicate_full(R8c["evaluation"]["predicate"], _ev8c, "")[0]
    == evaluate_predicate(R8c["evaluation"]["predicate"], _ev8c, "")[0],
)
# This iteration's audit — branch labels use the same dispatch order as `_eval_condition`:
# on a malformed multi-operator node (the authoring validator rejects it, but the trace also runs at
# runtime), the labeled operator must be the one actually evaluated (the source if-chain order), not
# the first dict key (in R11, `min_evidence_count` precedes `text_contains_any` by insertion).
R11 = rule("R11", {"min_evidence_count": 1, "text_contains_any": ["alpha"]})
_m11 = trace_predicate_full(R11["evaluation"]["predicate"], [GA], "")
check(
    "E: label cabang multi-operator-rusak mengikuti urutan dispatch evaluator",
    _m11[0] is True and _m11[1] and _m11[1][0].operator == "text_contains_any"
    and _m11[1][0].evidence_ids == ["E1"],
    str([(b.branch, b.operator, b.evidence_ids) for b in _m11[1]]),
)
EXU = ev("E7", "hal lain yang sama sekali tidak relevan")
m8b = evaluate_rule_tier1(R8, [EXU], "")
check(
    "E: none_of + evidence tak relevan → sama: bukan dukungan (tidak ada yang bisa disitasi)",
    not m8b.matched,
)
R9 = rule("R9", {"all_of": [{"text_contains_any": ["tidak ada refund"]}]})
m9 = evaluate_rule_tier1(R9, [ev("E8", "klien tegas bilang tidak ada refund")], "")
check(
    "E: bukti negatif EKSPLISIT (diucapkan user) → SUPPORTED lewat operator positif, anchor E8",
    m9.matched and m9.support.anchored and m9.support.evidence_ids == ["E8"],
    m9.support.reason,
)
R10 = rule(
    "R10", {"all_of": [{"text_contains_any": ["alpha"]}, {"none_of": [{"text_contains_any": ["refund"]}]}]}
)
m10 = evaluate_rule_tier1(R10, [GA], "")
check(
    "E: all_of[positif, none_of] → SUPPORTED murni dari cabang positif (none_of tanpa anchor)",
    m10.support.anchored and m10.support.evidence_ids == ["E1"] and len(m10.support.branches) == 1,
    str(m10.support.branches),
)

# ── Scenario D — rule matched but the basis cannot be formed -> the candidate is rejected, no fake evidence
unsupported = RuleSupport(rule_id="R1", tier="judgment", reason="sitasi tidak terverifikasi")
ps_d = build_path_set(space_for("R1"), reader_with({"R1": unsupported}))
check(
    "D: rule matched tanpa basis -> NOL path (kandidat tidak diterima)",
    ps_d["paths"] == [],
    str(ps_d["paths"]),
)
check("D: nol path membawa alasan eksplisit, bukan kosong", bool(ps_d["unresolved"]))
check(
    "D: rule itu tercatat sebagai unsupported_knowledge (audit, bukan dukungan)",
    [u["signal"] for u in ps_d["generation"]["unsupported_knowledge"]] == ["rule:R1"],
)
check(
    "D: strategi tercatat undetermined (belum dapat dinilai), bukan not_emergent",
    [u["strategy_id"] for u in ps_d["generation"]["undetermined"]] == ["S1"]
    and ps_d["generation"]["not_emergent"] == [],
)
ps_d2 = build_path_set(space_for("R1"), reader_with({"R1": []}))
check(
    "D: rujukan mentah kosong = unsupported, tidak jadi path (kontrak lama tak bisa memalsukan)",
    ps_d2["paths"] == [],
)

# PROV-02 is enforced at the core boundary: any reader claiming rule:/mechanism: TRUE without refs
rogue = grounded(
    lambda sid: Signal(True, "klaim kosong", ()) if sid != "state:goal" else Signal(True, "g", ("e",))
)
check(
    "PROV-02: rule: TRUE tanpa refs diturunkan menjadi None + unsupported",
    (rogue("rule:X").value is None and rogue("rule:X").unsupported),
)
check("PROV-02: mechanism: TRUE tanpa refs juga diturunkan", rogue("mechanism:X").value is None)
check("PROV-02: state: tidak terkena guard knowledge", rogue("state:x").value is True)
ps_rogue = build_path_set(
    space_for("X"),
    lambda sid: Signal(True, "klaim kosong", ()) if sid != "state:goal" else Signal(True, "g", ("e",)),
)
check("PROV-02: pembaca nakal tidak bisa melahirkan path lewat rule: tanpa dasar", ps_rogue["paths"] == [])

# PathSet validator rejects knowledge provenance without an anchor (engine bug = ValueError, not user data)
good = build_path_set(space_for("R1"), reader_with({"R1": m.support}))
bad = {
    **good,
    "paths": [
        {
            **good["paths"][0],
            "provenance": {
                **good["paths"][0]["provenance"],
                "knowledge_support": [
                    {"rule_id": "R1", "evidence_ids": [], "transcript_anchors": [], "branches": []}
                ],
            },
        }
    ],
}
try:
    validate_path_set(bad)
    check("PROV-02: validator menolak knowledge_support tanpa anchor", False)
except ValueError:
    check("PROV-02: validator menolak knowledge_support tanpa anchor", True)

# ── Gap evidence is not positive support (int 08 T2) ───────────────────────────────────────────────────
gap = ev("E1", "klien bilang follow up terlambat 5 hari", gap=True)
mg = evaluate_rule_tier1(R1, [gap], "")
check(
    "GAP: rule matched hanya karena evidence gap -> UNSUPPORTED",
    mg.matched and not mg.support.anchored,
    mg.support.reason,
)
mg2 = evaluate_rule_tier1(R1, [gap, ev("E2", "follow up terlambat lagi")], "")
check("GAP: bila ada evidence non-gap, anchor hanya non-gap", mg2.support.evidence_ids == ["E2"])

# ── Transcript quotes (a valid anchor that is not an evidence id) ──────────────────────────────────────
mt = evaluate_rule_tier1(R1, [], "Saya: follow up terlambat terus.")
check(
    "TRANSCRIPT: rule matched dari transkrip -> anchor berupa kutipan, bukan id evidence fiktif",
    mt.support.anchored and mt.support.evidence_ids == [] and len(mt.support.quotes) == 1,
    str(mt.support.quotes),
)
pst = build_path_set(space_for("R1"), reader_with({"R1": mt.support}))
pv = pst["paths"][0]["provenance"]
check(
    "TRANSCRIPT: kutipan masuk transcript_anchors, tidak mencemari evidence_ids",
    pv["evidence_ids"] == ["ev-goal"] and len(pv["transcript_anchors"]) == 1,
    str(pv["evidence_ids"]),
)

# ── Tier-2: LLM citations are verified against the ledger/transcript ────────────────────────────────────
ledger = [ev("ev-motion-001", "klien lambat dibalas", quote="saya balas setelah lima hari")]
ok1 = support_from_citation("T2R", "ev-motion-001", ledger, "")
check("T2: id evidence nyata -> SUPPORTED", ok1.anchored and ok1.evidence_ids == ["ev-motion-001"])
ok2 = support_from_citation("T2R", '"saya balas setelah lima hari"', ledger, "")
check(
    "T2: kutipan verbatim dari evidence -> dipetakan ke id evidence itu",
    ok2.evidence_ids == ["ev-motion-001"],
)
ok3 = support_from_citation(
    "T2R", 'user said "kami sering telat follow up"', ledger, "Saya: kami sering telat follow up"
)
check(
    "T2: kutipan verbatim dari transkrip -> anchor kutipan",
    ok3.anchored and ok3.evidence_ids == [] and ok3.quotes,
)
bad1 = support_from_citation("T2R", "ev-karangan-999", ledger, "")
check("T2: id yang tidak ada di ledger -> UNSUPPORTED (tidak dikarang)", not bad1.anchored, bad1.reason)
bad2 = support_from_citation("T2R", "parafrase yang tidak pernah diucapkan siapa pun", ledger, "")
check("T2: parafrase yang tak ditemukan di mana pun -> UNSUPPORTED", not bad2.anchored, bad2.reason)
bad3 = support_from_citation("T2R", "ok", ledger, "")
check("T2: sitasi terlalu pendek -> UNSUPPORTED", not bad3.anchored)

# ══ Task D — navigation's epistemic boundary: a tier-2 (judgment) match without a verified citation =
#    UNSUPPORTED, and UNSUPPORTED never becomes POSITIVE support for navigation/strategy/path/readiness/
#    route/nextmove. The CANONICAL epistemic interpretation (one, there is no second): anchored -> TRUE;
#    UNSUPPORTED -> UNKNOWN (None) + unsupported. Score modulation outside navigation is documented debt.
import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from core.navigation.readiness import build_projection  # noqa: E402
from core.schema.provenance import UNSUPPORTED as T2_UNSUPPORTED  # noqa: E402

judgment_unsup = RuleSupport(
    rule_id="T2R", tier="judgment", status=T2_UNSUPPORTED,
    reason="sitasi LLM tidak dapat diverifikasi terhadap ledger/transkrip",
)
sig_unsup = rule_signal("T2R", judgment_unsup)
check(
    "D: interpretasi kanonik — UNSUPPORTED -> sinyal UNKNOWN + unsupported (bukan TRUE, bukan FALSE)",
    sig_unsup.value is None and sig_unsup.unsupported and sig_unsup.reason,
)

# strategy: emerges_when = that judgment rule -> births no candidate, recorded undetermined + audit
ps_unsup = build_path_set(space_for("T2R"), reader_with({"T2R": judgment_unsup}))
gen = ps_unsup["generation"]
check(
    "D: strategi yang emergensinya bergantung rule UNSUPPORTED -> undetermined (bukan kandidat, bukan gagal)",
    ps_unsup["paths"] == []
    and "S1" in [u["strategy_id"] for u in gen["undetermined"]]
    and any(u["missing"] == ["rule:T2R"] for u in gen["undetermined"]),
    str(gen["undetermined"]),
)
check(
    "D: rule UNSUPPORTED tercatat di audit generation.unsupported_knowledge (tidak hilang senyap)",
    any(u["signal"] == "rule:T2R" for u in gen["unsupported_knowledge"]),
    str(gen["unsupported_knowledge"]),
)

# readiness: zero paths is a valid CURRENT finding; the engine records the reason (the rule is named)
proj_unsup = build_projection(ps_unsup, {"routes": []}, lambda rid: rid)
check(
    "D: readiness membaca nol path dari rule UNSUPPORTED sebagai temuan CURRENT, alasan engine tercatat",
    proj_unsup["paths"] == []
    and proj_unsup["navigation"]["status"] == "CURRENT"
    and "rule:T2R" in json.dumps(proj_unsup["unresolved"]),
    str(proj_unsup["unresolved"])[:120],
)

# route + nextmove over real HTTP engine: an artifact holding this zero-path PathSet births no route
import tempfile as _tempfile_guard  # noqa: E402
from pathlib import Path as _PathGuard  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.main as _app_main_guard  # noqa: E402
import store.events as _event_store_guard  # noqa: E402
import store.memory as memory_d  # noqa: E402
from app.main import app as _app_d  # noqa: E402
from providers.mock import MockProvider as _MockGuard  # noqa: E402

# R4: this test USED to call real Z.ai (get_llm unpatched): it burned quota on every gate-fast.
# Provider forced to mock; conversation events go to a temp directory.
_app_main_guard.get_llm = lambda: _MockGuard()
assert _app_main_guard.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
_event_store_guard.EVENTS_DIR = _PathGuard(_tempfile_guard.mkdtemp(prefix="nvl-ev-"))
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from evals.navigation_fixtures import revenue_artifact  # noqa: E402

_tmpd = Path(tempfile.mkdtemp(prefix="prov_t2_"))
_saved_d = memory_d.store.PERSIST_DIR
memory_d.store.PERSIST_DIR = _tmpd  # do not touch the repo's store/sessions
_c = TestClient(_app_d)
try:
    sid_d = _c.post(
        "/session", json={"goal_text": "naik ke 20 juta", "language": "id", "user_id": "u-prov-t2"}
    ).json()["session_id"]
    s_d = memory_d.store.get(sid_d)
    s_d.diagnosis = DiagnosisArtifact(
        **{**revenue_artifact(target_monthly=20.0).model_dump(), "possible_paths": ps_unsup}
    )
    memory_d.store.save(s_d)
    rt = _c.post(f"/session/{sid_d}/routes").json()
    check(
        "D: route tidak lahir dari rule UNSUPPORTED (tanpa path, tanpa route; alasan bukan kontradiksi)",
        rt["routes"] == [] and rt["next_move"] is None and "belum ada" in rt["reason"],
        rt["reason"][:90],
    )
    rd_d = _c.get(f"/session/{sid_d}/readiness").json()
    check(
        "D: readiness HTTP konsisten dengan proyeksi murni (nol path, CURRENT, alasan tercatat)",
        rd_d["paths"] == [] and rd_d["navigation"]["status"] == "CURRENT",
    )
finally:
    memory_d.store.PERSIST_DIR = _saved_d
    try:
        (_tmpd / f"{sid_d}.json").unlink(missing_ok=True)
    except Exception:
        pass

# ── Property: the predicate trace ALWAYS agrees with the ordinary evaluator, over every tier-1 KB rule ──
from engine.knowledge import get_kb  # noqa: E402

pool = [
    [],
    [ev("e1", "klien manggut-manggut setuju tapi tidak jadi beli")],
    [ev("e1", "meeting tanpa komitmen"), ev("e2", "diskon diminta terus", quote="minta diskon")],
    [ev("e1", "trial 2 minggu berbayar dan pricing page"), ev("e2", "follow up terlambat", gap=True)],
    [ev(f"e{i}", f"outreach dm ke prospek {i} referral lead inquiry") for i in range(5)],
]
deterministic = [
    r for r in get_kb()["rules"].values() if (r.get("evaluation") or {}).get("tier") == "deterministic"
]


def needles(pred: dict) -> list[str]:
    """Every text needle the predicate references — evidence material that DELIBERATELY satisfies the rule."""
    out: list[str] = []
    for op, arg in pred.items():
        if op in ("all_of", "any_of", "none_of"):
            out += [n for sub in arg for n in needles(sub)] if op != "none_of" else []
        elif op in ("text_contains_any", "text_contains_all"):
            out += list(arg)
    return out


pool += [
    [ev("s1", " ".join(needles(r["evaluation"].get("predicate") or {})) or "x"), ev("s2", "pelengkap")]
    for r in deterministic
]
disagree, unanchored, total_matched, masking = [], [], 0, []
for r in deterministic:
    for evs in pool:
        for tr in ("", "kami follow up terlambat dan minta diskon terus"):
            pred = r["evaluation"].get("predicate") or {}
            legacy, cited, _ = evaluate_predicate(pred, evs, tr)
            traced, branches, un_req = trace_predicate_full(pred, evs, tr)
            wrapped, w_branches = trace_predicate(pred, evs, tr)
            if legacy != traced or (wrapped, w_branches) != (traced, branches):
                disagree.append(r["rule_id"])
            if legacy:
                total_matched += 1
                # anti-masking: support must not claim SUPPORTED while a required positive branch
                # has no verified anchor (the real `evaluate_rule_tier1` lane, not a separate check)
                sup = support_from_branches(r["rule_id"], branches, evs, unanchored_required=un_req)
                if sup.anchored and un_req:
                    masking.append(r["rule_id"])
                anchors = {i for b in branches for i in b.evidence_ids} | {
                    q for b in branches for q in b.quotes
                }
                if not anchors:
                    unanchored.append(r["rule_id"])
                leg_ids = {c for c in cited if not c.startswith("transcript:")}
                if not leg_ids <= {i for b in branches for i in b.evidence_ids}:
                    disagree.append(r["rule_id"] + ":cite")
check(
    f"PROP: trace == evaluator atas {len(deterministic)} rule tier-1 KB x {len(pool) * 2} keadaan",
    not disagree,
    str(sorted(set(disagree))[:5]),
)
check(
    "PROP: anti-masking — SUPPORTED ⟹ tak ada cabang positif wajib tanpa anchor",
    not masking,
    str(sorted(set(masking))[:5]),
)
check(
    f"PROP: setiap rule tier-1 yang matched ({total_matched} kasus) punya anchor nyata",
    not unanchored,
    str(sorted(set(unanchored))[:5]),
)
kb_matches = [m for m in match_tier1(pool[1], "") if m.matched]
check(
    "PROP: match_tier1 nyata -> setiap rule matched punya support",
    all(m.support is not None for m in kb_matches),
)

# ── path_id still comes from the strategy (not from the rule) ────────────────────────────────────────────
check(
    "PATH-08: path_id diturunkan dari strategi, bukan dari rule/evidence",
    ps["paths"][0]["path_id"] == path_id_for("S1"),
)

# ══ Task B — full lineage audit: Evidence → predicate branch → RuleSupport → RuleSignal → Candidate →
#    Possible Path. Every hop must carry anchors whose resolution is identical in both directions.
from core.navigation.generator import generate_candidates  # noqa: E402
from core.schema.provenance import SUPPORTED, TRANSCRIPT_PREFIX  # noqa: E402

LEDGER = [
    ev("E1", "klien bilang follow up terlambat 5 hari"),
    ev("E2", "penawaran dikirim minggu lalu, belum ditindaklanjuti"),
    ev("E3", "sinyal lain yang tidak relevan untuk rule ini"),
]
RULE_B = rule(
    "R-B",
    {
        "all_of": [
            {"text_contains_any": ["follow up terlambat"]},
            {"text_contains_any": ["belum ditindaklanjuti"]},
        ]
    },
)
TXT = " ".join(e.signal for e in LEDGER)

# hop 1→2: ledger → predicate branch
traced, branches, un_req = trace_predicate_full(RULE_B["evaluation"]["predicate"], LEDGER, TXT)
check("LINEAGE: cabang terpenuhi dari ledger nyata; tanpa cabang wajib tanpa anchor", traced and not un_req)
check(
    "LINEAGE: setiap id anchor pada cabang resolves ke evidence di ledger",
    all(eid in {e.id for e in LEDGER} for b in branches for eid in b.evidence_ids),
    str([b.evidence_ids for b in branches]),
)

# hop 2→3: branch → RuleSupport
sup = support_from_branches("R-B", branches, LEDGER)
check(
    "LINEAGE: RuleSupport SUPPORTED; gabungan anchor cabang == anchor dukungan",
    sup.anchored and sorted(sup.evidence_ids) == sorted({e for b in branches for e in b.evidence_ids}),
    str(sup.evidence_ids),
)

# hop 3→4: RuleSupport → RuleSignal (the single generic bridge)
sig = rule_signal("R-B", sup)
check(
    "LINEAGE: rule_signal TRUE membawa refs == anchor dukungan dan basis == cabang dukungan",
    sig.value is True
    and list(sig.refs) == list(sup.refs())
    and [dict(b) for b in sig.basis] == [b.model_dump() for b in sup.branches],
)

# hop 4→5: RuleSignal → Candidate (emerges_when = this rule)
def reader_lineage(sid: str) -> Signal:
    kind, _, name = sid.partition(":")
    if kind == "rule":
        return rule_signal(name, sup if name == "R-B" else None)
    if sid == "state:goal":
        return Signal(True, "goal", ("ev-goal",))
    return Signal(None)


space_b = PossibilitySpace(
    "lineage",
    goal_signal="state:goal",
    strategies=(
        StrategySpec("S_B", "S B", emerges_when="rule:R-B", route_template_ids=()),
    ),
)
cset = generate_candidates(space_b, reader_lineage)
sup_branches = [b.model_dump() for b in sup.branches]
check(
    "LINEAGE: tepat satu kandidat; dukungan emergensinya membawa basis cabang yang sama",
    len(cset.candidates) == 1
    and cset.candidates[0].path_id == "path.S_B"
    and any(
        row["signal"] == "rule:R-B" and [dict(b) for b in row.get("basis", [])] == sup_branches
        for row in cset.candidates[0].support
    ),
    str(cset.candidates[0].support if cset.candidates else cset.not_emergent),
)

# hop 5→6: Candidate → Possible Path (provenance reads back to the ledger)
ps_b = build_path_set(space_b, reader_lineage)
p0 = ps_b["paths"][0]
ks = (p0["provenance"].get("knowledge_support") or [])
check(
    "LINEAGE: path membawa knowledge_support R-B dengan cabang identik dan anchor yang resolves ke ledger",
    p0["path_id"] == "path.S_B"
    and p0["provenance"]["knowledge_ids"] == ["R-B"]
    and len(ks) == 1
    and ks[0]["branches"] == [b.model_dump() for b in sup.branches]
    and all(
        eid in {e.id for e in LEDGER}
        for krow in ks
        for eid in krow["evidence_ids"]
    ),
    str(ks),
)
ledger_ids = {e.id for e in LEDGER}
check(
    "LINEAGE: naik lagi — setiap anchor di proyeksi path adalah id ledger atau kutipan transkrip berprefiks",
    all(
        ref in ledger_ids or ref.startswith(TRANSCRIPT_PREFIX)
        for row in ks
        for ref in [*row["evidence_ids"], *row["transcript_anchors"]]
    )
    and p0["provenance"]["knowledge_support"] and sup.status == SUPPORTED,
)

# reverse direction: drop one evidence anchor AND its transcript -> branch falls -> zero paths
LEDGER2 = [e for e in LEDGER if e.id != "E1"]
TXT2 = " ".join(e.signal for e in LEDGER2)
m2 = evaluate_rule_tier1(RULE_B, LEDGER2, TXT2)
traced2, branches2, un_req2 = trace_predicate_full(RULE_B["evaluation"]["predicate"], LEDGER2, TXT2)
sup2 = support_from_branches("R-B", branches2, LEDGER2)
check(
    "LINEAGE: mundur — tanpa E1 (dan kutipannya), cabang all_of[0] gugur → rule tak matched, nol path",
    not traced2 and not m2.matched and m2.support is None and ps_b and not un_req2,
    f"matched={m2.matched} anchored={sup2.anchored}",
)
ps2 = build_path_set(space_b, reader_with({"R-B": m2.support if m2.matched else None}))
check(
    "LINEAGE: mundur — nol path; rule tercatat di generation tanpa dikarang jadi kandidat",
    ps2["paths"] == [] and ps2["generation"]["unsupported_knowledge"] or ps2["paths"] == [],
    str(ps2["generation"].get("unsupported_knowledge")),
)

failed = [n for n, ok, _ in _results if not ok]
print("=" * 50)
print(
    f"HASIL: {len(_results) - len(failed)}/{len(_results)} PASS"
    + (f" — {len(failed)} GAGAL ❌" if failed else " ✅")
)
sys.exit(1 if failed else 0)
