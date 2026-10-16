"""R5 — Semantic closure: one requirement state across Path/View/Readiness/Planner + ledger parity.

The Round 4 audit (HEAD ee0123f) found two P0 gaps still readable from source:
  P0-A  RequirementView reads the already-merged check.state so the ledger-vs-check dispute
        disappears; Readiness still sees it (state_signal) → the planner may pick ACTION/HOLD
        amid a dispute.
  P0-B  agents/diagnosis.synthesize calls build_possible_paths WITHOUT the ledger, while
        app/navigation uses it → the final diagnosis's feasible set can differ from the
        provisional conversation.

Deterministic proof (no LLM/credentials) on ONE input:
  C1 the evaluator stores the raw reading + dispute;  C2 RequirementView carries it;
  C3 PlannerInput + plan_next_move pick CONTRADICTION;  C4 Readiness agrees (UNDETERMINED, not STOP);
  C5 the control with a merged reading does NOT detect it (proving the raw path is load-bearing);
  C6/C7 both directions + agreement;  C8/C9 synthesize forwards the ledger to the same engine.

Run: .venv/bin/python evals/test_round5_semantic_closure.py
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.navigation.applicability import build_applicable_set  # noqa: E402
from core.navigation.evaluator import build_path_set  # noqa: E402
from core.navigation.planner import KIND_EVIDENCE, plan_next_move  # noqa: E402
from core.navigation.planner_input import assemble_planner_input  # noqa: E402
from core.navigation.readiness import canonical_feasibility, path_conflicted_requirements  # noqa: E402
from core.navigation.requirement_state import (  # noqa: E402
    SUPPORT_FORMAL,
    MappingReader,
    RequirementState,
    read_requirement_views,
)
from engine.requirements import describe  # noqa: E402
from evals.navigation_fixtures import SAAS_SPACE, reader_of  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


BASE = {
    "state:revenue_goal_set": True,
    "state:many_signups": True,
    "state:weak_activation": True,
    "state:activation_already_strong": None,
    "state:funnel_measured": True,
    "state:aha_moment_defined": None,
}
RID = "retention.aha_moment_defined"
SID = "activation_first"
CHECK = "activation_defined"


def ledger(value: str):
    return lambda rid: value


def path_of(ps: dict, sid: str) -> dict:
    return next(p for p in ps["paths"] if p["strategy_id"] == sid)


def row_of(path: dict, cid: str) -> dict:
    return next(c for c in path["checks"] if c["check_id"] == cid)


def planner_decision(ps: dict, reader, ledger_of):
    """The same PRODUCTION path as app/navigation.py: ARS -> views -> input -> plan_next_move."""
    ars = build_applicable_set(ps, None, template_requirements=[])
    views = read_requirement_views(ars, reader, ps, None)
    inp = assemble_planner_input(
        lang="en", turn=1, path_set=ps, route_data=None, applicable=ars, views=views,
        describe=lambda r: describe(r, "en"),
        signal_of=lambda s, c: "state:" + c,
        resolvable=lambda s: "ASK",
        signal_text=lambda s: {"en": s + "?", "id": s},
        asked={},
    )
    return views, inp, plan_next_move(inp)


def build(ledger_value: str, signal_present: bool):
    values = dict(BASE)
    values["state:aha_moment_defined"] = True if signal_present else False
    return build_path_set(SAAS_SPACE, reader_of(values), ledger_state_of=ledger(ledger_value))


reader_absent = MappingReader(
    {RID: RequirementState(RID, "ABSENT", True, (), {"method": "fixture"})}, support=SUPPORT_FORMAL
)

# ── C1–C4 · ledger ABSENT vs raw signal PRESENT = the dispute that drives the planner ──────────────
print("C1–C4 · sengketa ledger ABSENT vs sinyal PRESENT")
ps_c = build("ABSENT", True)
p_c = path_of(ps_c, SID)
row_c = row_of(p_c, CHECK)
check("C1 evaluator: state=ABSENT (otoritas ledger), state_signal=PRESENT mentah, konflik tercatat",
      row_c["state"] == "ABSENT" and row_c.get("state_signal") == "PRESENT"
      and isinstance(row_c.get("conflict"), dict)
      and row_c["conflict"].get("authority") == "ledger", str(row_c))
views_c, inp_c, dec_c = planner_decision(ps_c, reader_absent, ledger("ABSENT"))
v_c = views_c[RID]
check("C2 RequirementView membawa sengketa + lineage mentah",
      v_c.conflict is True and v_c.satisfaction == "ABSENT"
      and v_c.contexts[0].conflict is True and v_c.contexts[0].signal_state == "PRESENT", str(v_c.to_dict()))
check("C3 PlannerInput menandai requirement bersengketa", inp_c["requirements"][RID].get("conflict") is True)
check("C4 plan_next_move memilih EVIDENCE_REQUEST/RESOLVE_CONTRADICTION (bukan ACTION buta)",
      dec_c["kind"] == KIND_EVIDENCE and dec_c["intent"] == "RESOLVE_CONTRADICTION"
      and dec_c["reason"]["stage"] == "CONTRADICTION", str(dec_c.get("reason", {}).get("stage")))
check("C4b Readiness sepakat: canonical_feasibility sengketa = UNDETERMINED (bukan STOP/CONTRADICTED)",
      path_conflicted_requirements(p_c, None, ledger("ABSENT")) == {RID}
      and canonical_feasibility(p_c, None, ledger("ABSENT")) == "UNDETERMINED",
      f"canon={canonical_feasibility(p_c, None, ledger('ABSENT'))} engine={p_c['feasibility']}")

# ── C5 · control: the merged state reading alone (without state_signal) loses the dispute ──────────
print("C5 · kontrol regresi (membuktikan jalur mentah load-bearing)")
import copy  # noqa: E402

ps_merged = copy.deepcopy(ps_c)
p_m = path_of(ps_merged, SID)
row_m = row_of(p_m, CHECK)
row_m.pop("state_signal", None)
row_m.pop("conflict", None)  # simulating the OLD reading: merged state only
views_m, inp_m, dec_m = planner_decision(ps_merged, reader_absent, ledger("ABSENT"))
check("C5 tanpa state_signal: RequirementView TIDAK melihat sengketa (bug pra-fix)",
      views_m[RID].conflict is False, str(views_m[RID].to_dict()))
check("C5b tanpa state_signal: planner tidak memilih CONTRADICTION",
      dec_m["reason"]["stage"] != "CONTRADICTION", str(dec_m.get("reason", {}).get("stage")))

# ── C6/C7 · both directions + agreement ─────────────────────────────────────────────────────────────
print("C6/C7 · dua arah dan kesepakatan")
reader_present = MappingReader(
    {RID: RequirementState(RID, "PRESENT", True, ("ev-1",), {"method": "fixture"})}, support=SUPPORT_FORMAL
)
ps_r = build("PRESENT", False)
views_r, _inp_r, dec_r = planner_decision(ps_r, reader_present, ledger("PRESENT"))
check("C6 ledger PRESENT vs sinyal ABSENT juga sengketa (tidak OPEN palsu)",
      views_r[RID].conflict is True and views_r[RID].satisfaction == "PRESENT"
      and dec_r["reason"]["stage"] == "CONTRADICTION", str(dec_r.get("reason", {}).get("stage")))
ps_a = build("ABSENT", False)
views_a, _inp_a, dec_a = planner_decision(ps_a, reader_absent, ledger("ABSENT"))
check("C7 ledger ABSENT vs sinyal ABSENT = sepakat, bukan sengketa",
      views_a[RID].conflict is False and dec_a["reason"]["stage"] != "CONTRADICTION",
      str(views_a[RID].to_dict()))

# ── C8/C9 · provisional -> final parity: synthesize uses the same engine + ledger ──────────
print("C8/C9 · paritas ledger provisional -> final diagnosis")
import agents.diagnosis as diagnosis  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from providers.mock import MockProvider  # noqa: E402

check("C9 synthesize mengekspos seam ledger_state_of (bukan default tersembunyi)",
      "ledger_state_of" in inspect.signature(diagnosis.synthesize).parameters)
_captured: dict = {}
_orig = diagnosis.build_possible_paths


def _spy(*a, **k):
    _captured["passed"] = "ledger_state_of" in k
    _captured["ledger"] = k.get("ledger_state_of")
    return _orig(*a, **k)


_sentinel = ledger("PRESENT")
diagnosis.build_possible_paths = _spy
try:
    diagnosis.synthesize(
        MockProvider(), "omzet 20 juta per bulan", [
            EvidenceItem(id="e1", signal="Saya punya 8 tahun pengalaman marketing",
                         source_quote="Saya punya 8 tahun pengalaman marketing",
                         level="self_reported", topic="CLAIM"),
        ],
        "user: omzet 20 juta per bulan", "en", "provisional", ledger_state_of=_sentinel,
    )
finally:
    diagnosis.build_possible_paths = _orig
check("C8 synthesize meneruskan ledger_state_of APA ADANYA ke build_possible_paths",
      _captured.get("passed") is True and _captured.get("ledger") is _sentinel,
      str({k: type(v).__name__ for k, v in _captured.items()}))

print()
failed = [r for r in RESULTS if not r[1]]
print(f"{'❌ FAIL' if failed else '✅ PASS'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
for name, _ok, detail in failed:
    print(f"   ❌ {name}: {detail[:240]}")
sys.exit(1 if failed else 0)
