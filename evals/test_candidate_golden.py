"""GOLDEN: one Candidate-born lineage, end to end, through PRODUCTION CODE.

    evidence ─► knowledge (tier-1 rule) ─► mechanism ─► Candidate ─► evaluation ─► Possible Path ─► Route
              ─► Readiness (canonical state: adjudication ledger) ─► NextMove

Not separate unit tests: one scenario, every layer read from the previous layer's output.
No fake candidates/paths/routes — the rule interpreter, generator, evaluator, `plan_compositions`,
route composer (`compose_route` via `run_session_route`), adjudication ledger, `build_projection`,
and `select_next_move` are all production modules. The only simulated step is adding the motion
label + domain strategy to the REGISTRY (data, `strategies.json`) — exactly the documented path
for a new domain (doc 14 §7.2).

    A. Forward lineage (synthetic "growth" domain, REAL route)      12 properties of Task C
    B. Canonical state: adjudication changes readiness and NextMove; route reused
    C. Reverse lineage: remove/invalidate evidence -> no ghost candidate/path/route/NextMove
    D. Downstream is origin-blind: Candidate-born == declared-strategy (route, readiness, NextMove)
    E. Isolation: full chain without a single Revenue module
    F. Revenue (real HTTP): candidate-born == declared-born for a REAL templated strategy
    G. API returns 0..N paths as-is (no cap in the engine)
    H. Conflict: provenance not lost (path stands via the independent branch) and route/NextMove unchanged

Deterministic, 0 LLM. Run: .venv/bin/python evals/test_candidate_golden.py
"""

from __future__ import annotations

import atexit
import copy
import dataclasses
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

_tmp = Path(tempfile.mkdtemp(prefix="cand_golden_"))
import contextlib  # noqa: E402

from core.navigation.candidate import ORIGIN_PATTERN  # noqa: E402
from core.navigation.contracts import (  # noqa: E402
    PossibilityPattern,
    PossibilitySpace,
    StrategySpec,
    candidate_id_for,
    path_id_for,
)
from core.navigation.evaluator import build_path_set, validate_path_set  # noqa: E402
from core.navigation.readiness import build_projection  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from evals.golden_fixtures import (  # noqa: E402
    GOAL,
    SPACE,
    SPACE_ACTIVATION_ROUTE,
    TEMPLATE,
    TEMPLATE_ACTIVATION,
    adjudicate,
    compose_routes,
    describe,
    growth_registry,
    ledger_items,
    projection,
    temp_stores,
    world,
)
from evals.navigation_fixtures import growth_evidence, signals_path_set  # noqa: E402
from ontology.route import validate_route as vr  # noqa: E402
from ontology.route.plan import plan_compositions  # noqa: E402

# Temp store for the WHOLE test (rl/ledger redirected); the "growth" domain registry only for the synthetic
# parts (A–E, then H) and released before the Revenue part (F) — the real Revenue registry returns.
_stack = contextlib.ExitStack()
_stack.enter_context(temp_stores(_tmp))
_growth = contextlib.ExitStack()
_growth.enter_context(growth_registry(_tmp))

import store.route_lineages as rl  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

SRC_IDS = {s["source_id"] for s in json.loads(Path("ontology/knowledge/sources.json").read_text())["sources"]}
vr.errors.clear()
vr.check_template(TEMPLATE, "golden.simplify_onboarding_v1", vr.load_registry(), SRC_IDS)
TEMPLATE_ERRORS = list(vr.errors)
vr.errors.clear()

LEDGER = ledger_items()
LEDGER_IDS = {e.id for e in LEDGER}
USER = "u-golden"
ps_template = SPACE  # no StrategySpec; simplify_onboarding is templated


def routes_of(ps, ledger_items_, user=USER):
    return compose_routes(ps, ledger_items_, user)


def pview(proj, sid="simplify_onboarding"):
    return next((p for p in proj["paths"] if p["strategy_id"] == sid), None)


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── A. Garis keturunan maju: evidence → … → Possible Path → Route → Readiness → NextMove ──")
check(
    "template sintetis lolos validator route PRODUKSI (0 error) — grammar nyata, bukan fixture bebas",
    TEMPLATE_ERRORS == [],
    str(TEMPLATE_ERRORS[:2]),
)
ps = world(LEDGER)
path = next(p for p in ps["paths"] if p["strategy_id"] == "simplify_onboarding")
prov, cand = path["provenance"], path["provenance"]["candidate"]
check(
    "1. evidence nyata menjadi sumber: setiap id evidence di provenance path ADALAH id ledger (tak ada id karangan)",
    set(prov["evidence_ids"]) <= LEDGER_IDS and "ev-g-3" in prov["evidence_ids"] and "ev-g-0" in prov["evidence_ids"],
    str(prov["evidence_ids"]),
)
ks = prov["knowledge_support"][0]
check(
    "2. knowledge ter-grounded: rule GW-R2 -> cabang predikat -> evidence ev-g-3 (hasil interpreter tier-1)",
    [k["rule_id"] for k in prov["knowledge_support"]] == ["GW-R2"]
    and ks["evidence_ids"] == ["ev-g-3"]
    and ks["branches"][0]["operator"] == "text_contains_any",
)
act = next(m for m in cand["mechanisms"] if m["mechanism_id"] == "onboarding_friction")
check(
    "3. mekanisme aktif karena dukungan beranjang: onboarding_friction DERIVED dari GW-R2 -> ev-g-3",
    act["status"] == "ACTIVE" and act["derived"] and not act["direct"] and act["knowledge_ids"] == ["GW-R2"]
    and act["evidence_ids"] == ["ev-g-3"],
)
check(
    "4+5. kandidat lahir dengan provenance: cand.simplify_onboarding, mekanisme + knowledge + evidence + asal",
    cand["candidate_id"] == "cand.simplify_onboarding"
    and cand["mechanism_ids"] == ["onboarding_friction"]
    and cand["knowledge_ids"] == ["GW-R2"]
    and set(cand["evidence_ids"]) <= LEDGER_IDS
    and cand["origin"] == ORIGIN_PATTERN,
)
row = next(r for r in ps["generation"]["possibilities"] if r["direction"] == "simplify_onboarding")
check(
    "6+7. lolos evaluasi dan dipromosikan: disposition PROMOTED -> path; applicability/feasibility dari EVALUATOR",
    row["disposition"] == "PROMOTED"
    and row["path_id"] == path["path_id"]
    and (path["applicability"], path["feasibility"], path["feasibility_basis"], path["status"])
    == ("APPLIES", "SUPPORTED", "DECLARED_UNCONDITIONAL", "OPEN"),
)
check(
    "8. path_id benar dan identitas empat lapis berbeda (candidate_id / strategy_id / path_id; route_id menyusul)",
    path["path_id"] == path_id_for("simplify_onboarding") == "path.simplify_onboarding"
    and cand["candidate_id"] == candidate_id_for(path["strategy_id"])
    and len({cand["candidate_id"], path["strategy_id"], path["path_id"]}) == 3,
)
check(
    "path-kandidat tervalidasi seperti path lain (validate_path_set) dan route_substrate membawa template",
    validate_path_set(ps) is None and path["route_substrate"] == {"template_ids": ["simplify_onboarding_v1"], "available": True},
)
plan = plan_compositions(ps["paths"], [TEMPLATE])
check(
    "9a. rencana komposisi strategi-dulu: hanya path ber-template; template milik strategi path (bukan kandidat)",
    [(p["path_id"], t["template_id"], t["strategy_id"]) for p, t in plan]
    == [("path.simplify_onboarding", "simplify_onboarding_v1", "simplify_onboarding")],
)
rt = routes_of(ps, LEDGER)
route = rt["routes"][0]
check(
    "9b. komposer route NYATA: route lahir (ROUTE_CREATED) membawa strategi/path path itu; motion dari REGISTRY",
    len(rt["routes"]) == 1
    and rt["not_born"] == []
    and route["outcome"] == "ROUTE_CREATED"
    and (route["strategy_id"], route["path_id"], route["template_id"])
    == ("simplify_onboarding", "path.simplify_onboarding", "simplify_onboarding_v1")
    and route["motion"] == "ACTIVATION"
    and route["applicability"]["status"] == "APPLIES"
    and route["applicability"]["evidence"] == ["ev-g-3"],
    str(route["applicability"]),
)
check(
    "route_id = UUID tersendiri; tak ada candidate_id/path_id di kunci rekonsiliasi (identitas route != kandidat)",
    bool(UUID_RE.match(route["route_id"]))
    and route["route_id"] not in {cand["candidate_id"], path["path_id"], path["strategy_id"]}
    and "cand" not in json.dumps(rl.list_rows(USER)[0]["lineage"]["reconciliation_key"]),
)
sat = {n["resolves"][0]: (n["satisfaction"]["status"], n["executability"]) for n in route["nodes"]}
check(
    "10. readiness membaca state canonical: tanpa adjudikasi semua UNKNOWN (UNKNOWN != ABSENT), eksekutabilitas dari dependensi",
    sat
    == {
        "delivery.onboarding": ("UNKNOWN", "TRUE"),
        "retention.aha_moment_defined": ("UNKNOWN", "TRUE"),
        "retention.activation": ("UNKNOWN", "UNKNOWN"),
    },
    str(sat),
)
check(
    "11. NextMove muncul dari route path-kandidat: ACTION di node pertama frontier, route_id milik route itu",
    rt["next_move"]["output"] == "ACTION"
    and rt["next_move"]["route_id"] == route["route_id"]
    and rt["next_move"]["frontier_ref"] in {e["node"] for e in route["frontier"]},
)
proj = projection(ps, rt)
pv = pview(proj)
check(
    "readiness: path ber-route; butir = node route (tanpa check: pola no_preconditions); counts 0/0/0/3 -> unknown",
    pv["route"]["template_id"] == "simplify_onboarding_v1"
    and pv["route"]["route_id"] == route["route_id"]
    and [i["key"] for i in pv["items"]] == ["delivery.onboarding", "retention.aha_moment_defined", "retention.activation"]
    and pv["counts"] == {"present": 0, "absent": 0, "partial": 0, "unknown": 3, "conflicted": 0, "total": 3},
)
check(
    "12. hilir tak membedakan: path-kandidat punya status/executability/narasi seperti path lain; asal hanya di `candidate`",
    (pv["status"], pv["feasibility"], pv["executability"]) == ("OPEN", "SUPPORTED", "TRUE")
    and pv["candidate"]["origin"] == ORIGIN_PATTERN
    and pv["candidate"]["why"]["source"] == "curated"
    and pv["candidate"]["evidence_ids"] == cand["evidence_ids"],
)
check(
    "OPEN != READY: path OPEN (feasible) dengan 0 dari 3 requirement terbukti adalah sah",
    pv["status"] == "OPEN" and pv["counts"]["present"] == 0,
)
check(
    "kandidat belum-path tak pernah jadi butir requirement atau route: tak ada 'cand.*' di items/routes",
    not any("cand." in json.dumps(x) for x in (pv["items"], rt["routes"])),
)
check(
    "path lain dari ruang yang sama (route-less) tetap sah: 3 path, hanya 1 yang punya route; tanpa NextMove sendiri",
    [p["strategy_id"] for p in ps["paths"]]
    == ["improve_activation_before_acquisition", "define_aha_moment", "simplify_onboarding"]
    and [r["path_id"] for r in rt["routes"]] == ["path.simplify_onboarding"]
    and all(p["route"] is None for p in proj["paths"] if p["strategy_id"] != "simplify_onboarding"),
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── B. State kanonik: adjudikasi (ledger) mengubah readiness + NextMove; route di-reuse ──")
r_ad = adjudicate(USER, "delivery.onboarding", "onboarding dipersingkat jadi tiga langkah", "ev-ad-1")
rt2 = routes_of(ps, LEDGER)
route2 = rt2["routes"][0]
sat2 = {n["resolves"][0]: n["satisfaction"]["status"] for n in route2["nodes"]}
check(
    "adjudikasi lewat pintu publik ledger (PRESENT); route DI-REUSE (route_id identik), bukan route baru",
    r_ad["adjudication"]["status"] == "PRESENT"
    and route2["outcome"] == "ROUTE_REUSED"
    and route2["route_id"] == route["route_id"]
    and sat2["delivery.onboarding"] == "PRESENT",
)
pv2 = pview(projection(ps, rt2))
it2 = {i["key"]: i for i in pv2["items"]}
check(
    "readiness membaca ledger: delivery.onboarding PRESENT (anchor ledger:), lainnya tetap UNKNOWN; counts bergeser",
    it2["delivery.onboarding"]["state"] == "PRESENT"
    and it2["delivery.onboarding"]["evidence"] == ["ledger:delivery.onboarding"]
    and it2["retention.aha_moment_defined"]["state"] == "UNKNOWN"
    and pv2["counts"]["present"] == 1
    and pv2["counts"]["unknown"] == 2,
)
aha_node = next(n for n in route2["nodes"] if n["resolves"] == ["retention.aha_moment_defined"])
check(
    "NextMove bergeser mengikuti state kanonik: node onboarding keluar frontier -> ACTION di node 'aha' (executable)",
    rt2["next_move"]["output"] == "ACTION" and rt2["next_move"]["frontier_ref"] == aha_node["node_id"],
)
adjudicate(USER, "retention.aha_moment_defined", "momen aha: pengguna menyelesaikan proyek pertama", "ev-ad-2")
rt3 = routes_of(ps, LEDGER)
act_node = next(n for n in rt3["routes"][0]["nodes"] if n["resolves"] == ["retention.activation"])
check(
    "dependensi terbuka bila prasyarat PRESENT: 'activation' executable -> NextMove ACTION di 'activation'",
    act_node["executability"] == "TRUE" and rt3["next_move"]["frontier_ref"] == act_node["node_id"],
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── C. Garis keturunan TERBALIK: cabut / invalidasi evidence → tak ada kandidat/path/route hantu ──")
without = [e for e in LEDGER if e.id != "ev-g-3"]
ps_c = world(without)
rt_c = routes_of(ps_c, without)
proj_c = projection(ps_c, rt_c)
check(
    "cabut ev-g-3: cabang predikat gugur -> GW-R2 tak matched -> mekanisme tak aktif -> kandidat -> path hilang",
    "simplify_onboarding" not in [p["strategy_id"] for p in ps_c["paths"]]
    and not any(m["status"] == "ACTIVE" for m in ps_c["generation"]["mechanisms"] if m["mechanism_id"] == "onboarding_friction"),
)
check(
    "…route/readiness/NextMove ikut: tak ada route yang disajikan, tak ada NextMove, path tak ada di proyeksi",
    rt_c["routes"] == [] and rt_c["next_move"] is None and pview(proj_c) is None,
)
check(
    "…lineage route TETAP ada di store (exists != surfaced) tetapi tidak muncul sebagai route/NextMove (bukan hantu)",
    any(r["lineage"]["reconciliation_key"]["strategy_id"] == "simplify_onboarding" for r in rl.list_rows(USER))
    and rt_c["next_move"] is None,
)
check(
    "tak ada hantu: tak satu pun id evidence yang dicabut tersisa di PathSet maupun proyeksi",
    "ev-g-3" not in json.dumps(ps_c) and "ev-g-3" not in json.dumps(proj_c),
)
gap_ledger = [e.model_copy(update={"is_gap": True}) if e.id == "ev-g-3" else e for e in LEDGER]
ps_gap = world(gap_ledger)
check(
    "invalidasi (evidence menjadi is_gap = data hilang): efek sama dengan dicabut — gap bukan dukungan",
    "simplify_onboarding" not in [p["strategy_id"] for p in ps_gap["paths"]]
    and any(u["signal"] == "rule:GW-R2" for u in ps_gap["generation"]["unsupported_knowledge"]),
)
ps_back = world(LEDGER)
rt_back = routes_of(ps_back, LEDGER)
check(
    "bukti dikembalikan: path lahir lagi dan route LAMA dipakai ulang (identitas stabil, tak ada route ganda)",
    rt_back["routes"][0]["outcome"] == "ROUTE_REUSED" and rt_back["routes"][0]["route_id"] == route["route_id"],
)
full = [GOAL, *growth_evidence(onboarding=True, churn=True)]
ps_p = world(full)
cand_p = path_p = next(p for p in ps_p["paths"] if p["strategy_id"] == "improve_activation_before_acquisition")
partial = [e for e in full if e.id != "ev-g-3"]
ps_p2 = world(partial)
path_p2 = next(p for p in ps_p2["paths"] if p["strategy_id"] == "improve_activation_before_acquisition")
proj_p = build_projection(ps_p, None, describe, lang="en")
proj_p2 = build_projection(ps_p2, None, describe, lang="en")
check(
    "dukungan parsial turun: path yang punya dua mekanisme tetap ada, tetapi provenance & alasan MENGIKUTI",
    path_p["provenance"]["candidate"]["mechanism_ids"] == ["activation_bottleneck", "onboarding_friction"]
    and path_p2["provenance"]["candidate"]["mechanism_ids"] == ["activation_bottleneck"]
    and "GW-R2" in path_p["provenance"]["knowledge_ids"]
    and "GW-R2" not in path_p2["provenance"]["knowledge_ids"]
    and "ev-g-3" not in path_p2["provenance"]["evidence_ids"]
    and pview(proj_p, "improve_activation_before_acquisition")["candidate"]["why"]["text"]
    != pview(proj_p2, "improve_activation_before_acquisition")["candidate"]["why"]["text"],
)
ps_none = world([GOAL])
check(
    "semua bukti dicabut: NOL path dengan alasan eksplisit; tak ada path yang bertahan karena snapshot lama",
    ps_none["paths"] == [] and ps_none["unresolved"] and projection(ps_none, routes_of(ps_none, [GOAL]))["paths"] == [],
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── D. Hilir tak membedakan asal: Candidate-born == declared-strategy ──")
DECLARED = PossibilitySpace(
    "growth_declared",
    (
        StrategySpec(
            "simplify_onboarding",
            "Simplify onboarding",
            basis="friction in the first session keeps people from reaching value",
            emerges_when="mechanism:onboarding_friction",
            no_preconditions=True,
            route_template_ids=("simplify_onboarding_v1",),
            presentation=SPACE.patterns[2].presentation,
        ),
    ),
    goal_signal="state:revenue_goal",
    mechanisms=(SPACE.mechanisms[1],),
)
ps_d = world(LEDGER, DECLARED)
pd_ = ps_d["paths"][0]
check(
    "ruang deklarasi (StrategySpec) menghasilkan path yang SAMA bentuknya, tanpa blok kandidat (asal murni strategi)",
    pd_["strategy_id"] == "simplify_onboarding" and "candidate" not in pd_["provenance"],
)


def fresh_user(name: str) -> str:
    """New user with an IDENTICAL canonical state (only onboarding PRESENT) — a fair comparison."""
    adjudicate(name, "delivery.onboarding", "onboarding dipersingkat jadi tiga langkah", f"ev-{name}")
    return name


rt_cand = routes_of(ps, LEDGER, fresh_user("u-eq-candidate"))
rt_d = routes_of(ps_d, LEDGER, fresh_user("u-eq-declared"))


def norm_routes(rts: dict) -> dict:
    """Route/NextMove without UUIDs (replaced by position): what remains is SEMANTIC."""
    out = copy.deepcopy(rts)
    for r in out["routes"]:
        idx = {n["node_id"]: i for i, n in enumerate(r["nodes"])}
        for n in r["nodes"]:
            n["node_id"] = idx[n["node_id"]]
            n["depends_on"] = [idx[d] for d in n["depends_on"]]
        r["frontier"] = [{"kind": e["kind"], **({"node": idx[e["node"]]} if "node" in e else {})} for e in r["frontier"]]
        r["route_id"] = "R"
        r["outcome"] = "ROUTE"
        if out["next_move"] and out["next_move"].get("frontier_ref") in idx:
            out["next_move"]["frontier_ref"] = idx[out["next_move"]["frontier_ref"]]
    if out["next_move"]:
        out["next_move"]["route_id"] = "R"
    return out


check(
    "route + NextMove IDENTIK (setelah UUID dinormalisasi): node, satisfaction, executability, frontier, aksi",
    norm_routes(rt_cand) == norm_routes(rt_d),
    "" if norm_routes(rt_cand) == norm_routes(rt_d) else json.dumps([norm_routes(rt_cand)["next_move"], norm_routes(rt_d)["next_move"]]),
)


def semantic(path_view: dict) -> dict:
    out = {k: v for k, v in path_view.items() if k not in ("provenance", "candidate")}
    out["route"] = {k: v for k, v in (out["route"] or {}).items() if k != "route_id"}
    return out


check(
    "readiness IDENTIK kecuali `provenance`/`candidate`: status, feasibility, butir, counts, executability, narasi",
    semantic(pview(projection(ps, rt_cand))) == semantic(pview(projection(ps_d, rt_d))),
)
stripped = copy.deepcopy(ps)
for p in stripped["paths"]:
    p["provenance"].pop("candidate", None)
    p["provenance"].pop("emerges_when", None)
rt_s = routes_of(stripped, LEDGER, fresh_user("u-eq-stripped"))
check(
    "pelucutan: hapus SELURUH blok kandidat dari path -> route/NextMove/readiness tak berubah (hilir tak membacanya)",
    norm_routes(rt_s) == norm_routes(rt_cand)
    and semantic(pview(projection(stripped, rt_s))) == semantic(pview(projection(ps, rt_cand))),
)
import ast  # noqa: E402

downstream = ("path_routes.py", "plan.py", "next_move.py", "session_bridge.py", "compose.py", "lifecycle.py")
leak_names = {"candidate", "origin", "possibility", "candidate_id", "candidate_block"}
hits = []
for f in downstream:
    for node_ in ast.walk(ast.parse(Path("ontology/route", f).read_text(encoding="utf-8"))):
        names = set()
        if isinstance(node_, ast.Attribute):
            names.add(node_.attr)
        elif isinstance(node_, ast.Name):
            names.add(node_.id)
        elif isinstance(node_, ast.Constant) and isinstance(node_.value, str):
            names.add(node_.value)
        hits += [f"{f}:{n}" for n in names & leak_names]
check(
    "AST: modul route (rencana, komposer, bridge, NextMove, lifecycle) tak menyebut candidate/origin/possibility",
    not hits,
    str(hits[:4]),
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── E. Isolasi: rantai penuh (rule → kandidat → path → route NYATA → readiness → NextMove) tanpa Revenue ──")
leaked = sorted(n for n in sys.modules if n == "domains.revenue" or n.startswith("domains.revenue."))
check("tak satu pun modul domains.revenue dimuat oleh rantai penuh domain sintetis", not leaked, str(leaked[:3]))

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── F. Revenue (HTTP nyata): candidate-born == declared-born untuk strategi dengan template NYATA ──")
_growth.close()  # release the "growth" registry: the real Revenue registry returns
import store.path_states as path_states  # noqa: E402

path_states._STATES = _tmp / "path_states.json"
path_states._HISTORY = _tmp / "path_history.jsonl"
import tempfile as _tempfile_guard  # noqa: E402
from pathlib import Path as _PathGuard  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.main as _app_main_guard  # noqa: E402
import store.events as _event_store_guard  # noqa: E402
from app.main import app  # noqa: E402
from providers.mock import MockProvider as _MockGuard  # noqa: E402

# R4: this test USED TO call the real Z.ai (get_llm left unpatched): burning quota on every gate-fast.
# Provider forced to mock; conversation events go to a temp directory.
_app_main_guard.get_llm = lambda: _MockGuard()
assert _app_main_guard.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
_event_store_guard.EVENTS_DIR = _PathGuard(_tempfile_guard.mkdtemp(prefix="nvl-ev-"))
from core.stages.mechanisms import detect_mechanisms  # noqa: E402
from domains.revenue.navigation.signals import RevenueSignals  # noqa: E402
from domains.revenue.navigation.space import revenue_space  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402
from evals.navigation_fixtures import diagnosis_with  # noqa: E402
from store.memory import store  # noqa: E402

client = TestClient(app)
_created: list[str] = []


def _drop_sessions() -> None:
    """Do not leave test sessions in store/sessions — also when the test halts with an error (atexit)."""
    for sid in _created:
        f = store.PERSIST_DIR / f"{sid}.json"
        if f.exists():
            f.unlink()


atexit.register(_drop_sessions)
REV_LEDGER = [
    EvidenceItem(id="ev-r1", signal="jarang outreach dan pipeline tipis bulan ini", level="behavioral", topic="MOTION"),
    EvidenceItem(
        id="ev-r2", signal="Saya konsultan, jual jasa ke klien bisnis.", level="self_reported", topic="REVENUE_STATE"
    ),
]
MECH = detect_mechanisms(REV_LEDGER)
check(
    "mekanisme Revenue terdeteksi dari ledger lewat detektor NYATA: insufficient_pipeline <- ev-r1",
    MECH.get("insufficient_pipeline") == ["ev-r1"],
    str(MECH),
)
BASE = revenue_space()
DORMANT = dataclasses.replace(
    BASE,
    strategies=tuple(
        dataclasses.replace(s, emerges_when={}) if s.strategy_id == "direct_outreach" else s for s in BASE.strategies
    ),
    patterns=BASE.patterns
    + (
        PossibilityPattern(
            direction="direct_outreach",
            title="Direct outreach",
            mechanism_ids=("insufficient_pipeline",),
            thesis="too little outreach to fill the pipeline",
        ),
    ),
)


def revenue_path_set(space, ledger_items):
    rs = RevenueState(target_monthly=60.0)
    return build_path_set(space, RevenueSignals(rs, detect_mechanisms(ledger_items), None))


def revenue_session(user: str, pset: dict, ledger_items) -> str:
    r = client.post("/session", json={"goal_text": "naik ke 60 juta per bulan", "language": "id", "user_id": user})
    assert r.status_code == 200, r.text[:200]
    sid = r.json()["session_id"]
    _created.append(sid)
    s = store.get(sid)
    s.evidence = list(ledger_items)
    s.diagnosis = diagnosis_with(pset)
    store.save(s)
    return sid


ps_decl_rev = revenue_path_set(BASE, REV_LEDGER)
ps_cand_rev = revenue_path_set(DORMANT, REV_LEDGER)
pdr, pcr = ps_decl_rev["paths"][0], ps_cand_rev["paths"][0]
check(
    "Revenue: SAMA bukti -> path.direct_outreach lahir dua cara: declared-strategy (tanpa blok kandidat) vs kandidat",
    [p["strategy_id"] for p in ps_decl_rev["paths"]] == ["direct_outreach"] == [p["strategy_id"] for p in ps_cand_rev["paths"]]
    and "candidate" not in pdr["provenance"]
    and pcr["provenance"]["candidate"]["origin"] == ORIGIN_PATTERN
    and pcr["provenance"]["candidate"]["mechanism_ids"] == ["insufficient_pipeline"]
    and pcr["provenance"]["candidate"]["evidence_ids"] == ["ev-r1"],
)
check(
    "Revenue: path-kandidat memakai check + template milik strategi NYATA (bukan dikarang): feasibility & substrat identik",
    [c["check_id"] for c in pcr["checks"]] == [c["check_id"] for c in pdr["checks"]] == ["capacity_available", "demand_exists"]
    and pcr["route_substrate"] == pdr["route_substrate"] == {"template_ids": ["direct_outreach_v1"], "available": True}
    and (pcr["feasibility"], pcr["status"]) == (pdr["feasibility"], pdr["status"]),
)
sid_d = revenue_session("u-rev-declared", ps_decl_rev, REV_LEDGER)
sid_c = revenue_session("u-rev-candidate", ps_cand_rev, REV_LEDGER)
res_d = client.post(f"/session/{sid_d}/routes")
res_c = client.post(f"/session/{sid_c}/routes")
bd, bc = res_d.json(), res_c.json()
check(
    "Revenue HTTP: POST /routes -> 200 untuk keduanya; route lahir dari template direct_outreach_v1 (komposer NYATA)",
    res_d.status_code == res_c.status_code == 200
    and [r["template_id"] for r in bd["routes"]] == ["direct_outreach_v1"] == [r["template_id"] for r in bc["routes"]]
    and bc["routes"][0]["motion"] == bd["routes"][0]["motion"] == "ACQUISITION",
    str(res_c.text[:200]),
)
check(
    "Revenue HTTP: route + NextMove IDENTIK antara candidate-born dan declared-born (UUID dinormalisasi)",
    norm_routes({"routes": bc["routes"], "next_move": bc["next_move"]})
    == norm_routes({"routes": bd["routes"], "next_move": bd["next_move"]})
    and bc["next_move"] is not None,
    str(bc["next_move"]),
)
rd_d = client.get(f"/session/{sid_d}/readiness").json()
rd_c = client.get(f"/session/{sid_c}/readiness").json()
check(
    "Revenue HTTP: GET /readiness IDENTIK kecuali provenance/candidate (satu realitas untuk UI dan LLM)",
    semantic(pview(rd_c, "direct_outreach")) == semantic(pview(rd_d, "direct_outreach"))
    and pview(rd_c, "direct_outreach")["candidate"]["origin"] == ORIGIN_PATTERN
    and pview(rd_d, "direct_outreach")["candidate"] is None,
)
no_ev = [e for e in REV_LEDGER if e.id != "ev-r1"]
sid_c2 = revenue_session("u-rev-candidate", revenue_path_set(DORMANT, no_ev), no_ev)
b_c2 = client.post(f"/session/{sid_c2}/routes").json()
rd_c2 = client.get(f"/session/{sid_c2}/readiness").json()
check(
    "Revenue arah terbalik: cabut ev-r1 -> mekanisme tak terdeteksi -> path hilang -> tak ada route/NextMove di HTTP",
    b_c2["routes"] == []
    and b_c2["next_move"] is None
    and rd_c2["paths"] == []
    and "ev-r1" not in json.dumps(rd_c2)
    and any(r["lineage"]["reconciliation_key"]["strategy_id"] == "direct_outreach" for r in rl.list_rows("u-rev-candidate")),
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── G. API mengembalikan 0..N path apa adanya: engine tak punya batas (UI-lah yang membatasi) ──")
api_counts = {}
for n in (0, 1, 3, 5, 6, 8, 10, 13):
    pset = signals_path_set(max(n, 1), list(range(n)))
    sid_n = revenue_session(f"u-api-{n}", pset, [])
    dg = client.get(f"/session/{sid_n}/diagnosis").json()
    rdn = client.get(f"/session/{sid_n}/readiness").json()
    api_counts[n] = (
        len(dg["possible_paths"]["paths"]),
        len(rdn["paths"]),
        dg["navigation"]["status"],
    )
check(
    "diagnosis + readiness HTTP mengembalikan SEMUA path: 0,1,3,5,6,8,10,13 -> jumlah yang sama (tanpa batas 5 atau 10)",
    api_counts == {n: (n, n, "CURRENT") for n in (0, 1, 3, 5, 6, 8, 10, 13)},
    str(api_counts),
)
sid_all = revenue_session("u-api-all", signals_path_set(13, list(range(13))), [])
paths_all = client.get(f"/session/{sid_all}/diagnosis").json()["possible_paths"]["paths"]
check(
    "path yang kelak disembunyikan UI tak kehilangan evidence/provenance di API: ke-13 path membawa jejak penuh",
    len(paths_all) == 13
    and all(p["provenance"]["candidate"]["evidence_ids"] and p["provenance"]["knowledge_support"] for p in paths_all),
)

# ═════════════════════════════════════════════════════════════════════════════════════════════════════════
print("── H. Konflik: provenance TIDAK hilang (path tegak lewat cabang independen) dan TIDAK mengubah route/NextMove ──")
IMP = "improve_activation_before_acquisition"
vr.errors.clear()
vr.check_template(TEMPLATE_ACTIVATION, "golden.improve_activation_v1", vr.load_registry(), SRC_IDS)
ACT_ERRORS = list(vr.errors)
vr.errors.clear()
check(
    "template kedua (improve_activation_v1) juga lolos validator route PRODUKSI (0 error)",
    ACT_ERRORS == [],
    str(ACT_ERRORS[:2]),
)
calm_items = ledger_items()  # activation_bottleneck + onboarding_friction active, no refutation
conf_items = ledger_items(retention=True)  # + ev-g-6 "day-7 retention high": GW-R3 refutes activation_bottleneck
ps_calm = world(calm_items, SPACE_ACTIVATION_ROUTE)
ps_conf = world(conf_items, SPACE_ACTIVATION_ROUTE)
p_calm = next(p for p in ps_calm["paths"] if p["strategy_id"] == IMP)
p_conf = next(p for p in ps_conf["paths"] if p["strategy_id"] == IMP)
c_calm, c_conf = p_calm["provenance"]["candidate"], p_conf["provenance"]["candidate"]
check(
    "konflik pada SATU mekanisme: path tetap lahir lewat cabang independen (onboarding_friction), status/feasibility sama",
    c_calm["mechanism_ids"] == ["activation_bottleneck", "onboarding_friction"]
    and c_conf["mechanism_ids"] == ["onboarding_friction"]
    and (p_conf["applicability"], p_conf["feasibility"], p_conf["status"])
    == (p_calm["applicability"], p_calm["feasibility"], p_calm["status"]),
    str(c_conf["mechanism_ids"]),
)
conf = c_conf["conflicts"]
check(
    "konflik TIDAK hilang: tercatat terstruktur di provenance (mekanisme, baris yang mendukung, baris yang membantah)",
    [c["mechanism_id"] for c in conf] == ["activation_bottleneck"]
    and [r["signal"] for r in conf[0]["supports"]] == ["rule:GW-R1"]
    and [r["signal"] for r in conf[0]["refutes"]] == ["rule:GW-R3"]
    and conf[0]["refutes"][0]["refs"] == ["ev-g-6"]
    and c_calm["conflicts"] == [],
    json.dumps(conf)[:240],
)
check(
    "bukti penyangkal bukan dukungan: ev-g-6 tak masuk evidence_ids path/kandidat, hanya di dalam blok konflik",
    "ev-g-6" not in p_conf["provenance"]["evidence_ids"]
    and "ev-g-6" not in c_conf["evidence_ids"]
    and "GW-R3" not in p_conf["provenance"]["knowledge_ids"],
)
with growth_registry(_tmp):
    rt_calm = compose_routes(ps_calm, calm_items, fresh_user("u-conf-calm"), [TEMPLATE_ACTIVATION])
    rt_conf = compose_routes(ps_conf, conf_items, fresh_user("u-conf-conflict"), [TEMPLATE_ACTIVATION])
r_conf = rt_conf["routes"][0]
check(
    "route NYATA lahir dari path yang menyimpan konflik (ROUTE_CREATED, template milik strategi path)",
    len(rt_conf["routes"]) == 1
    and rt_conf["not_born"] == []
    and (r_conf["outcome"], r_conf["strategy_id"], r_conf["path_id"], r_conf["template_id"])
    == ("ROUTE_CREATED", IMP, f"path.{IMP}", "improve_activation_v1")
    and r_conf["applicability"]["evidence"] == ["ev-g-1"],
    str(r_conf["applicability"]),
)
check(
    "route + NextMove IDENTIK dengan dunia tanpa konflik (UUID dinormalisasi): komposer & NextMove buta terhadap konflik",
    norm_routes(rt_conf) == norm_routes(rt_calm) and rt_conf["next_move"] is not None,
)
aha_conf = next(n for n in r_conf["nodes"] if n["resolves"] == ["retention.aha_moment_defined"])
check(
    "NextMove dihitung dari state kanonik: ACTION di node 'aha' (frontier pertama), tak terpengaruh sengketa mekanisme",
    rt_conf["next_move"]["output"] == "ACTION" and rt_conf["next_move"]["frontier_ref"] == aha_conf["node_id"],
)
check(
    "hilir tak memuat konflik: tak ada mekanisme/rule/evidence penyangkal di route maupun NextMove",
    all(tok not in json.dumps(rt_conf) for tok in ("activation_bottleneck", "GW-R3", "ev-g-6")),
)
conf_names = {"conflicts", "unsettled", "assumed_absences", "assumes_absence"}
conf_hits = []
for f in downstream:
    for node_ in ast.walk(ast.parse(Path("ontology/route", f).read_text(encoding="utf-8"))):
        found = set()
        if isinstance(node_, ast.Attribute):
            found.add(node_.attr)
        elif isinstance(node_, ast.Name):
            found.add(node_.id)
        elif isinstance(node_, ast.Constant) and isinstance(node_.value, str):
            found.add(node_.value)
        conf_hits += [f"{f}:{n}" for n in found & conf_names]
check(
    "AST: modul route (rencana, komposer, bridge, NextMove, lifecycle) tak menyebut conflicts/unsettled/assumed_absences",
    not conf_hits,
    str(conf_hits[:4]),
)
pv_calm = pview(projection(ps_calm, rt_calm), IMP)
pv_conf = pview(projection(ps_conf, rt_conf), IMP)
check(
    "readiness: status, feasibility, butir, counts, eksekutabilitas IDENTIK dengan dunia tanpa konflik; hanya `candidate` beda",
    semantic(pv_conf) == semantic(pv_calm) and pv_conf["candidate"] != pv_calm["candidate"],
)
check(
    "readiness membawa sengketa sebagai `unsettled` (nama mekanisme), bukan sebagai state/enum kelima; dunia tenang: kosong",
    pv_conf["candidate"]["unsettled"] == [{"mechanism_id": "activation_bottleneck", "name": "Activation bottleneck"}]
    and pv_calm["candidate"]["unsettled"] == []
    and {i["state"] for i in pv_conf["items"]} <= {"PRESENT", "ABSENT", "PARTIAL", "UNKNOWN"},
    json.dumps(pv_conf["candidate"]["unsettled"]),
)
why_conf = pv_conf["candidate"]["why"]["text"]
check(
    "alasan path hanya menyebut mekanisme yang AKTIF: kalimat activation_bottleneck (bersengketa) tak ikut diceritakan",
    "first session is confusing" in why_conf and "sign up" not in why_conf,
    why_conf[:160],
)
# Reverse direction: without the independent branch, conflict ALONE is not support -> no ghost path/route/NextMove
only_conf = ledger_items(retention=True, onboarding=False)
ps_oc = world(only_conf, SPACE_ACTIVATION_ROUTE)
with growth_registry(_tmp):
    rt_oc = compose_routes(ps_oc, only_conf, fresh_user("u-conf-only"), [TEMPLATE_ACTIVATION])
row_oc = next(r for r in ps_oc["generation"]["possibilities"] if r["direction"] == IMP)
check(
    "tanpa cabang independen: konflik saja BUKAN dukungan -> kandidat CONFLICTED (tak dipromosikan), nol path/route/NextMove",
    row_oc["disposition"] == "CONFLICTED"
    and IMP not in [p["strategy_id"] for p in ps_oc["paths"]]
    and rt_oc["routes"] == []
    and rt_oc["next_move"] is None
    and pview(projection(ps_oc, rt_oc), IMP) is None,
    str(row_oc["disposition"]),
)

_drop_sessions()

failed = [n for n, ok, _ in _results if not ok]
print("=" * 50)
tail = f" — {len(failed)} GAGAL ❌" if failed else " ✅"
print(f"HASIL: {len(_results) - len(failed)}/{len(_results)} PASS{tail}")
sys.exit(1 if failed else 0)
