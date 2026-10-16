"""UNSUPPORTED causal invariant — zero positive navigation causality, including through the score layer.

doc 14 §6.1/§22: a match whose citation cannot be verified has status UNSUPPORTED — epistemically
UNKNOWN (the claim is known to exist, its basis cannot be shown), not TRUE. Consequences must not
fire from a still-unknown state (Kleene). The tests here prove it from the opposite direction —
trying to make UNSUPPORTED matter, and FAILING at every gate:

  1. SCORE         : an UNSUPPORTED match moves no effective_score / ranking order / flags /
                     blocked at all (a property over ALL consequence-bearing KB rules); revoking an
                     evidence anchor kills consequences already in effect (causal defensibility).
  2. EVIDENCE MAP  : an unverifiable citation — let alone an invented evidence id — injects nothing
                     into `rule_evidence_map` (the side door into scoring is closed).
  3. NAVIGATION    : the score layer cannot change the PathSet — the spectrum level (the only input
                     seam the score can shift via arbitration) changes only advisory text and
                     context, never path/feasibility/status/applicability.
  4. NONE_OF       : epistemic contract — `none_of` is not positive support derived from the
                     absence of evidence; support comes only from explicitly citable evidence.
  5. MONOTONIC     : downgrading SUPPORTED → UNSUPPORTED never raises anything (score, support,
                     evidence map, flags).

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_unsupported_causal.py
"""

from __future__ import annotations

import copy
import sys

sys.path.insert(0, ".")

import core.stages.knowledge_rules as kr  # noqa: E402
from core.navigation.contracts import (  # noqa: E402
    CheckSpec,
    PossibilitySpace,
    Signal,
    StrategySpec,
)
from core.navigation.evaluator import build_path_set  # noqa: E402
from core.navigation.knowledge import rule_signal  # noqa: E402
from core.schema.constraints import HypothesisState  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from core.schema.provenance import SUPPORTED, UNSUPPORTED, RuleSupport  # noqa: E402
from core.stages.knowledge_rules import (  # noqa: E402
    KnowledgeRuleOutcome,
    RuleMatch,
    RuleMatchSet,
    apply_rule_consequences,
    run_knowledge_rules,
)
from core.stages.rule_predicates import evaluate_predicate, trace_predicate_full  # noqa: E402
from core.stages.rule_support import support_from_branches  # noqa: E402
from domains.revenue.navigation.paths import build_possible_paths  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from engine.knowledge import get_kb  # noqa: E402
from providers.base import LLMProvider  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


class FakeMatcher(LLMProvider):
    """structured_call returns a RuleMatchSet from a controlled JSON payload (0 LLM)."""

    name = "fake-matcher-causal"

    def __init__(self, payload: str = '{"matches": [], "anti_patterns": []}'):
        self.payload = payload

    def raw_json(self, system: str, user: str) -> str:  # pragma: no cover
        return "{}"

    def structured_call(self, schema, system, user, retries=0):
        import json

        return schema.model_validate(json.loads(self.payload))


def _ranking():
    return [
        HypothesisState(constraint_id="R7.2", score=0.70, effective_score=0.70),
        HypothesisState(constraint_id="C6.3", score=0.55, effective_score=0.55),
        HypothesisState(constraint_id="C6.1", score=0.40, effective_score=0.40),
    ]


def _snapshot(ranking: list[HypothesisState]) -> list[tuple[str, float, float]]:
    """(id, score, effective_score) IN ORDER — ordering is part of the result."""
    return [(h.constraint_id, h.score, h.effective_score) for h in ranking]


def _ev(signals):
    return [
        EvidenceItem(id=f"ev-{i}", signal=s, level="self_reported", topic="CONVERSION")
        for i, s in enumerate(signals, 1)
    ]


def _match(rule_id: str, status: str, tier: str = "judgment", applied_to: str = "ev-1") -> RuleMatch:
    """A matched RuleMatch with a controlled support status (unit: consequence contract)."""
    sup = RuleSupport(
        rule_id=rule_id,
        tier=tier,
        status=status,
        evidence_ids=(["ev-1"] if status == SUPPORTED else []),
        reason="unit test" if status == SUPPORTED else "basis tidak dapat diverifikasi",
    )
    return RuleMatch(rule_id=rule_id, matched=True, applied_to=applied_to, tier=tier, support=sup)


_SITASI_KARANGAN = (
    "saya curiga ini penyebab utamanya berdasarkan pengamatan pribadi selama bertahun-tahun"
)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. SCORE — consequences do not fire from UNSUPPORTED
# ═══════════════════════════════════════════════════════════════════════════════

print("\n── §1 Skor: apply_rule_consequences tidak menggerakkan apa pun dari UNSUPPORTED ──")

_kb_rules = get_kb()["rules"]
_RANKING_IDS = {"R7.2", "C6.3", "C6.1"}
_targeting = sorted(
    rid
    for rid, r in _kb_rules.items()
    if any(t in _RANKING_IDS for t in (r.get("consequence") or {}).get("targets", []))
)
check(
    "KB punya rule berekonsekuensi atas ranking uji (properti tidak vakum)",
    bool(_targeting),
    f"{len(_targeting)} rule: {', '.join(_targeting[:6])}…",
)

_inert = True
_inert_detail = ""
for rid in _targeting:
    base = _ranking()
    snap = _snapshot(base)
    out = KnowledgeRuleOutcome()
    out.matches.append(_match(rid, UNSUPPORTED))
    apply_rule_consequences(base, out)
    if _snapshot(base) != snap:
        _inert = False
        _inert_detail = f"{rid} menggerakkan skor"
        break
    if out.unsupported_rule_ids != [rid] or out.extra_rule_ids or out.flags or out.blocked:
        _inert = False
        _inert_detail = f"{rid} bocor ke extra/flags/blocked"
        break
    if "TIDAK dieksekusi" not in out.note:
        _inert = False
        _inert_detail = f"{rid} tidak tercatat jujur di note"
        break
check(
    "PROP: SEMUA rule KB berekonsekuensi — match UNSUPPORTED → skor, urutan, flags, blocked NOL delta",
    _inert,
    _inert_detail,
)

# Sanity: the mechanism is alive — a SUPPORTED match really executes consequences.
base = _ranking()
out_lo = KnowledgeRuleOutcome()
out_lo.matches.append(_match("TM-R04", SUPPORTED))  # LOWER_CONFIDENCE → C6.3
apply_rule_consequences(base, out_lo)
c63 = next(h for h in base if h.constraint_id == "C6.3")
check(
    "Sanity: match SUPPORTED mengeksekusi konsekuensi (skor C6.3 didiskon oleh TM-R04)",
    c63.effective_score is not None and c63.effective_score < 0.55 and "TM-R04" in out_lo.extra_rule_ids,
    f"effective={c63.effective_score}",
)

base = _ranking()
out_bl = KnowledgeRuleOutcome()
out_bl.matches.append(_match("HK-R02", SUPPORTED))  # BLOCK_VERDICT → R7.2
apply_rule_consequences(base, out_bl)
check(
    "Sanity: match SUPPORTED BLOCK_VERDICT tercatat di blocked",
    bool(out_bl.blocked) and not KnowledgeRuleOutcome().blocked,
    f"blocked={out_bl.blocked}",
)

# ── End-to-end flip through run_knowledge_rules (FakeMatcher, real KB rules) ──
# HK-R02: a pure TIER-2 (judgment) rule — BLOCK_VERDICT on R7.2. It has no tier-1 twin,
# so a match in out.matches must come from the verified LLM citation path.
_T2_RULE = "HK-R02"


def _tier2_outcome(applied_to: str, signals: list[str] | None = None, rule_id: str | None = None):
    payload = RuleMatchSet(
        matches=[RuleMatch(rule_id=rule_id or _T2_RULE, matched=True, applied_to=applied_to)]
    ).model_dump_json()
    ev = _ev(signals if signals is not None else ["kondisi netral untuk uji sitasi"])
    return run_knowledge_rules(FakeMatcher(payload), ev, "")


out_ok = _tier2_outcome("ev-1")
m_ok = next(m for m in out_ok.matches if m.rule_id == _T2_RULE and m.tier == "judgment")
check(
    "Flip: sitasi id ledger ('ev-1') → RuleSupport SUPPORTED",
    m_ok.support is not None and m_ok.support.anchored,
)

out_bad = _tier2_outcome(_SITASI_KARANGAN)
m_bad = next(m for m in out_bad.matches if m.rule_id == _T2_RULE and m.tier == "judgment")
check(
    "Flip: sitasi tak terverifikasi → RuleSupport UNSUPPORTED (tetap matched, audit tetap ada)",
    m_bad.matched and m_bad.support is not None and m_bad.support.status == UNSUPPORTED,
)

r_ok, r_bad, r_base = _ranking(), _ranking(), _ranking()
apply_rule_consequences(r_ok, out_ok)
apply_rule_consequences(r_bad, out_bad)
_t2_line_bad = next((ln for ln in out_bad.note.splitlines() if ln.startswith("TIER-2 RULES")), "")
check(
    "Flip: UNSUPPORTED → ranking identik baseline; SUPPORTED (BLOCK) → R7.2 diblokir",
    _snapshot(r_bad) == _snapshot(r_base)
    and _snapshot(r_ok) != _snapshot(r_base)
    and out_bad.blocked == []
    and out_ok.blocked,
)
check(
    "Flip: UNSUPPORTED → note membawa audit 'konsekuensi TIDAK dieksekusi', bukan klaim sitasi terverifikasi",
    "TIDAK dieksekusi" in out_bad.note and _T2_RULE not in _t2_line_bad,
)
check(
    "Flip: coverage memisahkan matched vs layak-eksekusi (falsifiable)",
    out_bad.coverage["rules_unsupported"] == [_T2_RULE]
    and _T2_RULE not in out_bad.coverage["rules_consequence_eligible"]
    and _T2_RULE in out_ok.coverage["rules_consequence_eligible"],
)

# ── POSITIVE direction: RAISE_CONFIDENCE is also locked behind an anchor ──
_raise_ok = _tier2_outcome("ev-1", ["banyak inquiry masuk tapi tidak follow up terukur"], rule_id="SP-R01")
m_raise = next(m for m in _raise_ok.matches if m.rule_id == "SP-R01" and m.tier == "judgment")
r_raise = _ranking()
apply_rule_consequences(r_raise, _raise_ok)
c63_raise = next(h for h in r_raise if h.constraint_id == "C6.3")
check(
    "Sanity arah positif: SP-R01 RAISE_CONFIDENCE SUPPORTED menaikkan skor C6.3 (mekanisme hidup)",
    m_raise.matched and m_raise.support.anchored and (c63_raise.effective_score or 0) > 0.55,
    f"effective={c63_raise.effective_score}",
)

_raise_bad = _tier2_outcome(
    _SITASI_KARANGAN, ["banyak inquiry masuk tapi tidak follow up terukur"], rule_id="SP-R01"
)
r_raise_bad = _ranking()
apply_rule_consequences(r_raise_bad, _raise_bad)
check(
    "Arah positif: SP-R01 dengan sitasi tak terverifikasi → skor C6.3 NOL delta dari baseline",
    _snapshot(r_raise_bad) == _snapshot(_ranking()),
)

# ── Causal defensibility: revoking an anchor kills consequences already in effect ──
ev_with = _ev(["kondisi netral untuk uji sitasi"])
out_with = _tier2_outcome("ev-1")
out_removed = _tier2_outcome("ev-1", signals=[])  # ledger emptied: the anchor is gone
m_rem = next(m for m in out_removed.matches if m.rule_id == _T2_RULE and m.tier == "judgment")
r_with, r_removed = _ranking(), _ranking()
apply_rule_consequences(r_with, out_with)
apply_rule_consequences(r_removed, out_removed)
check(
    "Evidence removal: anchor dicabut dari ledger → UNSUPPORTED → skor kembali ke baseline",
    m_rem.support is not None
    and m_rem.support.status == UNSUPPORTED
    and _snapshot(r_removed) == _snapshot(_ranking())
    and out_removed.blocked == []
    and out_with.blocked,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 2. EVIDENCE MAP — the side door into scoring is closed (seam `evaluation.indicates`)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n── §2 rule_evidence_map: hanya anchor terverifikasi yang boleh memetakan bukti ──")

_SYN_RULE = {
    "rule_id": "SYN-R01",
    "evaluation": {"tier": "judgment", "indicates": ["V2.4"], "predicate": {}},
    "consequence": {},
}
_orig_candidate_rules = kr.candidate_rules
_orig_match_group = kr._match_group


def _patch_infer(citation: str):
    """Run run_knowledge_rules with one synthetic `indicates`-bearing rule and one tier-2 match.

    `_match_group` is patched so only the first group returns a match (deterministic under
    ThreadPoolExecutor); `candidate_rules` is patched so SYN-R01 is known in every group."""

    def fake_candidate_rules(group=None):
        return [dict(_SYN_RULE)]

    def fake_match_group(llm, evidence, tail, group):
        if group == kr.SOURCE_GROUPS[0]:
            rms = RuleMatchSet(
                matches=[RuleMatch(rule_id="SYN-R01", matched=True, applied_to=citation)]
            )
            return rms, True
        return None, False

    kr.candidate_rules = fake_candidate_rules
    kr._match_group = fake_match_group
    try:
        return run_knowledge_rules(FakeMatcher(), _ev(["kondisi apa pun"]), "")
    finally:
        kr.candidate_rules = _orig_candidate_rules
        kr._match_group = _orig_match_group


out_inf_bad = _patch_infer(_SITASI_KARANGAN)
check(
    "INFER: sitasi tak terverifikasi menyuntikkan NOL bukti ke rule_evidence_map",
    out_inf_bad.rule_evidence_map == {},
    str(out_inf_bad.rule_evidence_map),
)

out_inf_fake = _patch_infer("ev-999 serta kata-kata panjang yang tidak ada di ledger mana pun")
check(
    "INFER: id evidence KARANGAN (ev-999, tidak di ledger) tidak pernah masuk evidence_map",
    out_inf_fake.rule_evidence_map == {},
    str(out_inf_fake.rule_evidence_map),
)

out_inf_mix = _patch_infer("ev-1 dan juga ev-999")
check(
    "INFER: sitasi campuran (nyata + karangan) → hanya anchor terverifikasi yang masuk",
    out_inf_mix.rule_evidence_map == {"V2.4": ["ev-1"]},
    str(out_inf_mix.rule_evidence_map),
)

# ═══════════════════════════════════════════════════════════════════════════════
# 3. NAVIGATION — the score layer cannot change the PathSet
# ═══════════════════════════════════════════════════════════════════════════════

print("\n── §3 Navigasi: spectrum level (input seam yang bisa digeser skor) hanya menyentuh advisory ──")


def _strip_advisory(r: dict) -> dict:
    """Strip advisory/context fields — the only things the spectrum/score may legitimately affect."""
    out = copy.deepcopy(r)
    for p in out.get("paths", []):
        p.pop("advisory", None)
        p.pop("advisory_i18n", None)
    out.pop("context", None)
    out.pop("note", None)
    return out


def _advice(level: str | None):
    text = {
        None: None,
        "STOP": {
            "id": "Tahan dulu: ukur dan uji kecil sebelum komit.",
            "en": "Hold: measure and test small first.",
        },
        "TEST_FIRST": {
            "id": "Lewat percobaan kecil dulu, bukan langsung skala.",
            "en": "Small test first, not straight to scale.",
        },
        "SCALE": {"id": "Siap skala.", "en": "Ready to scale."},
    }.get(level)
    return None if text is None else (lambda _path: dict(text))


# (a) Core level: `advise` — the exact seam the domain uses — only attaches text.
_rina = RevenueState(
    current_monthly=30.0,
    target_monthly=60.0,
    gap_monthly=30.0,
    capacity_utilization=0.863,
    willingness_to_pay="PROVEN_AT_CURRENT_PRICE",
    demand_exists=True,
    demand_signal="EXISTS",
    avg_deal_size=10.0,
    demand_sufficiency="AT_RISK",
)

levels = [None, "STOP", "NOT_YET", "TEST_FIRST", "GO_SMALL", "PROCEED", "SCALE"]
rev_sets = {lv: build_possible_paths(_rina, {"level": lv}) for lv in levels}
stripped = {lv: _strip_advisory(r) for lv, r in rev_sets.items()}
all_same = all(stripped[lv] == stripped["TEST_FIRST"] for lv in levels)
check(
    "PROP Revenue: 7 spectrum level → path_id, feasibility, status, applicability, counts IDENTIK",
    all_same,
)

advisory_differs = (
    rev_sets["STOP"]["paths"][0].get("advisory") != rev_sets["SCALE"]["paths"][0].get("advisory")
)
context_consumed = all(rev_sets[lv]["context"]["spectrum_level"] == lv for lv in levels)
check(
    "PROP Revenue: input benar-benar dikonsumsi (advisory+context berubah per level) — properti tidak vakum",
    advisory_differs and context_consumed,
)

# (b) Core level, domain-neutral: any advisor at the same seam only attaches text.
_space = PossibilitySpace(
    space_id="synthetic_advise",
    goal_signal="state:goal",
    strategies=(
        StrategySpec(
            strategy_id="S1",
            title="Strategy S1",
            emerges_when="state:goal",
            checks=(CheckSpec("c1", "state:ready", "prereq", None, "siapkan"),),
        ),
    ),
)


def _reader(_: str) -> Signal:
    return Signal(True, "goal", ("ev-goal",)) if _ else Signal(None)


core_sets = [build_path_set(_space, _reader, advise=_advice(lv)) for lv in (None, "STOP", "SCALE")]
check(
    "PROP core: advisor di seam `build_path_set` tidak mengubah apa pun selain advisory",
    all(_strip_advisory(s) == _strip_advisory(core_sets[0]) for s in core_sets[1:]),
)

# (c) UNSUPPORTED ≡ absent at the full-pipeline level: same rule, support flipped →
# an UNSUPPORTED rule in active_rules yields a PathSet IDENTICAL to the rule being absent.
def _reader_with(rules: dict[str, RuleSupport]):
    """Synthetic domain signal reader — the `test_knowledge_provenance.reader_with` pattern:
    state:goal TRUE, `rule:` signals via the generic `rule_signal` bridge."""

    def read(sid: str) -> Signal:
        kind, _, name = sid.partition(":")
        if kind == "rule":
            return rule_signal(name, rules.get(name))
        if sid == "state:goal":
            return Signal(True, "goal", ("ev-goal",))
        return Signal(None)

    return read


def _space_rule(rule_id: str) -> PossibilitySpace:
    return PossibilitySpace(
        space_id="synthetic_flip",
        goal_signal="state:goal",
        strategies=(
            StrategySpec(
                strategy_id="S1",
                title="Strategy S1",
                emerges_when=f"rule:{rule_id}",
                checks=(CheckSpec("c1", "state:ready", "prereq", None, "siapkan"),),
            ),
        ),
    )


_sup_ok = RuleSupport(rule_id="HRX-R1", tier="judgment", status=SUPPORTED, evidence_ids=["ev-hr-1"])
_sup_bad = RuleSupport(
    rule_id="HRX-R1", tier="judgment", status=UNSUPPORTED, reason="basis tidak terverifikasi"
)
ps_supported = build_path_set(_space_rule("HRX-R1"), _reader_with({"HRX-R1": _sup_ok}))
ps_unsupported = build_path_set(_space_rule("HRX-R1"), _reader_with({"HRX-R1": _sup_bad}))
ps_absent = build_path_set(_space_rule("HRX-R1"), _reader_with({}))
check(
    "PROP: rule UNSUPPORTED di active_rules melahirkan NOL path — sama seperti rule tidak ada",
    ps_unsupported["paths"] == [] and ps_absent["paths"] == [] and ps_supported != ps_absent,
)
check(
    "PROP: tapi engine TIDAK melebur keadaannya — UNSUPPORTED tercatat sebagai unsupported_knowledge, "
    "absent sebagai undetermined (UNKNOWN ≠ ABSENT sampai ke audit)",
    ps_unsupported != ps_absent
    and any("HRX-R1" in str(u) for u in ps_unsupported["generation"].get("unsupported_knowledge", []))
    and ps_unsupported["generation"].get("unsupported_knowledge")
    != ps_absent["generation"].get("unsupported_knowledge"),
)
gen_bad = ps_unsupported["generation"]
check(
    "PROP: rule UNSUPPORTED tercatat jujur di generation (undetermined/unsupported), bukan diam-diam hilang",
    "HRX-R1" in str(gen_bad.get("undetermined", {})) + str(gen_bad.get("unsupported_knowledge", [])),
    str(gen_bad.get("unsupported_knowledge")),
)

# ═══════════════════════════════════════════════════════════════════════════════
# 4. NONE_OF — epistemic contract (absence of evidence ≠ evidence of absence)
# ═══════════════════════════════════════════════════════════════════════════════

print("\n── §4 none_of: tidak ada dukungan positif dari ketiadaan bukti ──")

_evs = _ev(["keluhan pelanggan meningkat", "penjualan turun dua bulan berturut"])

ok_none, cited_none, reason_none = evaluate_predicate(
    {"none_of": [{"text_contains_any": ["iklan berbayar"]}]}, _evs, ""
)
check(
    "none_of terpenuhi dari KETIADAAN bukti → matched=False (sitasi wajib menolaknya)",
    ok_none is False and cited_none == [] and "sitasi" in reason_none,
    reason_none,
)

traced, branches, un_required = trace_predicate_full(
    {"all_of": [
        {"text_contains_any": ["keluhan"]},
        {"none_of": [{"text_contains_any": ["iklan berbayar"]}]},
    ]}, _evs, ""
)
check(
    "none_of sebagai saudara all_of: hanya cabang POSITIF yang membawa anchor",
    traced
    and all(b.operator != "none_of" for b in branches)
    and any("keluhan" in str(b.operand) for b in branches),
    str([(b.branch, b.operator, b.evidence_ids) for b in branches]),
)
sup = support_from_branches("R-TEST", branches, _evs, unanchored_required=un_required)
check(
    "Dukungan all_of+none_of berstatus SUPPORTED — anchor-nya murni dari cabang positif",
    sup.anchored and sup.evidence_ids == ["ev-1"],
    str(sup.evidence_ids),
)

# The contract's positive side: EXPLICIT evidence about absence is a citable fact → it may
# support (not "absence of evidence", but "evidence of absence").
_ev_absence = _ev(["kami belum pernah menjalankan iklan berbayar sama sekali"])
ok_abs, cited_abs, _ = evaluate_predicate(
    {"text_contains_any": ["belum pernah menjalankan iklan berbayar"]}, _ev_absence, ""
)
check(
    "Pernyataan absensi EKSPLISIT adalah fakta yang dapat disitasi → boleh menjadi dukungan",
    ok_abs and cited_abs == ["ev-1"],
)

tr_abs, br_abs, un_abs = trace_predicate_full(
    {"all_of": [
        {"text_contains_any": ["belum pernah menjalankan iklan"]},
        {"evidence_level_absent": ["transactional"]},
    ]}, _ev_absence, ""
)
sup_abs = support_from_branches("R-ABS", br_abs, _ev_absence, unanchored_required=un_abs)
check(
    "all_of[positif-absen-eksplisit, level_absent] → SUPPORTED; cabang absent tidak menggugurkan",
    sup_abs.anchored and sup_abs.evidence_ids == ["ev-1"],
    str(sup_abs.evidence_ids),
)

# ═══════════════════════════════════════════════════════════════════════════════
# 5. MONOTONIC — downgrading SUPPORTED → UNSUPPORTED never raises anything
# ═══════════════════════════════════════════════════════════════════════════════

print("\n── §5 Monotonik: downgrade tidak pernah menaikkan skor/dukungan/peta ──")

r_supported, r_downgraded = _ranking(), _ranking()
out_sup = KnowledgeRuleOutcome()
out_sup.matches.append(_match("TM-R04", SUPPORTED))
out_sup.matches.append(_match("HK-R02", SUPPORTED))
out_down = KnowledgeRuleOutcome()
out_down.matches.append(_match("TM-R04", UNSUPPORTED))
out_down.matches.append(_match("HK-R02", UNSUPPORTED))
apply_rule_consequences(r_supported, out_sup)
apply_rule_consequences(r_downgraded, out_down)

def _by_id(ranking: list[HypothesisState]) -> dict[str, float]:
    return {
        h.constraint_id: (h.effective_score if h.effective_score is not None else h.score)
        for h in ranking
    }


_baseline = _by_id(_ranking())
_eff_sup, _eff_down = _by_id(r_supported), _by_id(r_downgraded)
check(
    "Downgrade dua rule (LOWER + BLOCK) → keadaan skor ≡ baseline tanpa rule (nol delta dua arah); "
    "SUPPORTED benar-benar menggeser; audit bersih vs terisi",
    _eff_down == _baseline
    and _snapshot(r_downgraded) == _snapshot(_ranking())
    and _eff_sup != _baseline
    and _snapshot(r_supported) != _snapshot(_ranking())
    and not (out_down.extra_rule_ids or out_down.flags or out_down.blocked)
    and (out_sup.extra_rule_ids or out_sup.flags or out_sup.blocked),
)
# Boost direction: a downgrade never exceeds the baseline (no fictitious bonus from lost evidence).
boost_ok = _tier2_outcome("ev-1", ["banyak inquiry masuk tapi tidak follow up terukur"], rule_id="SP-R01")
boost_bad = _tier2_outcome(
    _SITASI_KARANGAN, ["banyak inquiry masuk tapi tidak follow up terukur"], rule_id="SP-R01"
)
r_b_ok, r_b_bad = _ranking(), _ranking()
apply_rule_consequences(r_b_ok, boost_ok)
apply_rule_consequences(r_b_bad, boost_bad)
_eff_b_ok, _eff_b_bad = _by_id(r_b_ok), _by_id(r_b_bad)
check(
    "Arah boost: RAISE SUPPORTED > baseline, downgrade TIDAK PERNAH > baseline (bonus fiktif dilarang)",
    _eff_b_ok["C6.3"] > _baseline["C6.3"] and _eff_b_bad["C6.3"] <= _baseline["C6.3"],
    f"supported={_eff_b_ok['C6.3']} downgraded={_eff_b_bad['C6.3']} baseline={_baseline['C6.3']}",
)

# Monotonicity at the evidence-map seam: a downgrade shrinks the map or keeps it equal, never grows.
map_sup = _patch_infer("ev-1").rule_evidence_map
map_down = _patch_infer(_SITASI_KARANGAN).rule_evidence_map
check(
    "Downgrade di seam INFER → rule_evidence_map menyusut ke kosong, bukan bergeser ke bukti lain",
    map_down == {} and map_sup == {"V2.4": ["ev-1"]},
)

# Monotonicity at the navigation signal: a downgraded support never produces a TRUE Signal.
sig_sup = rule_signal("HRX-R1", _sup_ok)
sig_down = rule_signal("HRX-R1", _sup_bad)
check(
    "Downgrade support → sinyal rule tidak pernah TRUE; UNKNOWN (None) dengan penanda unsupported",
    sig_sup.value is True and sig_down.value is None and sig_down.unsupported,
)

# ── RESULTS ─────────────────────────────────────────────────────────────────────
failed = [r for r in _results if not r[1]]
print("\n" + "=" * 50)
for name, ok, detail in failed:
    print(f"  ❌ GAGAL: {name} | {detail}")
print(f"HASIL: {len(_results) - len(failed)}/{len(_results)} PASS")
if failed:
    raise SystemExit(1)
