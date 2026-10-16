"""Semantics that must be explicit: reading conflicts, "no check" != feasible,
vacuous predicates, LEGACY artifacts.

internal-docs §5, §10, §11. Deterministic, 0 LLM. Run:
    .venv/bin/python evals/test_navigation_semantics.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store dialihkan ke tmp — store produksi tak tersentuh

_tmp = Path(tempfile.mkdtemp(prefix="nav_sem_"))
import store.adjudication_ledger as ledger  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_lineages as rl  # noqa: E402

rl._BASE = _tmp / "lineages"
ledger._LEDGER_ROOT = _tmp / "ledger"
path_states._STATES = _tmp / "path_states.json"
path_states._HISTORY = _tmp / "path_history.jsonl"

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import store.memory as memory  # noqa: E402
from agents.ask import readiness_lines  # noqa: E402
from agents.explain import _paths_read  # noqa: E402
from app.main import _require_known_path, app  # noqa: E402
from core.navigation.claims import CLAIM_TYPES, ground_claim  # noqa: E402
from core.navigation.compat import assess_path_set  # noqa: E402
from core.navigation.contracts import (  # noqa: E402
    CheckSpec,
    PossibilitySpace,
    StrategySpec,
    display_status,
    feasibility_from_checks,
)
from core.navigation.evaluator import PATHSET_VERSION, build_path_set  # noqa: E402
from core.navigation.narrative import fallback_narrative  # noqa: E402
from core.navigation.predicate import evaluate  # noqa: E402
from core.navigation.readiness import canonical_feasibility, path_conflicted_requirements  # noqa: E402
from domains.revenue.projection.readiness import build_readiness_projection  # noqa: E402
from domains.revenue.schema.artifact import DiagnosisArtifact  # noqa: E402
from evals.navigation_fixtures import (  # noqa: E402
    check_row,
    diagnosis_with,
    node,
    pathset,
    pp,
    reader_of,
    revenue_artifact,
    routes_of,
)

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def raises(fn, exc=ValueError) -> str | None:
    try:
        fn()
    except exc as e:
        return str(e)
    return None


def proj(route_nodes: list[dict], checks: list[dict]) -> dict:
    return build_readiness_projection(
        diagnosis_with(pathset(pp("s1", "SUPPORTED", checks))), routes_of(s1=route_nodes)
    )


# ══ D. CONFLICT: two definite readings that differ ══════════════════════════════════════════════════
REQ = "commercial.willingness_to_pay"
p = proj([node(REQ, "PRESENT", nid="n1")], [check_row("wtp", "ABSENT", kind="hard", requirement_id=REQ)])
path = p["paths"][0]
it = path["items"][0]
check("D: satu butir untuk requirement yang sama (tanpa duplikat)", len(path["items"]) == 1)
check("D: keadaan yang diproyeksikan = otoritas (node/adjudikasi ledger)", it["state"] == "PRESENT")
check(
    "D: konflik terstruktur: dua pembacaan, otoritas, resolusi, teks dari engine",
    it["conflict"]["sources"] == {"route": "PRESENT", "check": "ABSENT"}
    and it["conflict"]["authority"] == "route"
    and it["conflict"]["resolution"] == "AUTHORITY"
    and it["conflict"]["note"]["text"]
    and it["settled"] is False,
)
check("D: path mencatat butir yang berkonflik", path["conflicts"] == [REQ])
check(
    "D: butir berkonflik TIDAK dihitung terbukti (conflicted terpisah; semua bucket + conflicted = total)",
    path["counts"] == {"present": 0, "absent": 0, "partial": 0, "unknown": 0, "conflicted": 1, "total": 1},
    str(path["counts"]),
)
agree = proj([node(REQ, "PRESENT", nid="n1")], [check_row("wtp", "PRESENT", requirement_id=REQ)])["paths"][0]
check(
    "D: dua pembacaan sepakat -> tanpa konflik, terhitung terbukti",
    "conflict" not in agree["items"][0] and agree["counts"]["present"] == 1 and agree["conflicts"] == [],
)
unk = proj([node(REQ, "UNKNOWN", nid="n1")], [check_row("wtp", "ABSENT", requirement_id=REQ)])["paths"][0]
check(
    "D: UNKNOWN vs pasti -> yang pasti menang, BUKAN konflik (UNKNOWN != pembacaan yang bertentangan)",
    unk["items"][0]["state"] == "ABSENT" and "conflict" not in unk["items"][0],
)

# ══ C2. CONFLICT → DOWNSTREAM: ONE canonical rule everywhere (Task C, doc 14 §10.1) ════════════════
# A DISPUTED condition is proven in neither direction: it contributes UNKNOWN to the same
# feasibility_from_checks — a hard-check dispute is not STOP, disputed support is not SUPPORTED. The raw
# engine reading stays audited in `feasibility_engine`; the NextMove gate uses the SAME canonical
# function (not two evaluators that can diverge).


def proj2(path_spec: dict, route_nodes: list[dict]) -> dict:
    return build_readiness_projection(diagnosis_with(pathset(path_spec)), routes_of(s1=route_nodes))


HARD_ABSENT = [check_row("wtp", "ABSENT", kind="hard", requirement_id=REQ)]
c_stop = proj2(pp("s1", "CONTRADICTED", HARD_ABSENT), [node(REQ, "PRESENT", nid="n1")])["paths"][0]
check(
    "C2: sengketa hard-check → feasibility proyeksi UNDETERMINED (bukan CONTRADICTED)",
    c_stop["feasibility"] == "UNDETERMINED" and c_stop["feasibility_engine"] == "CONTRADICTED",
    f"{c_stop['feasibility']} / {c_stop['feasibility_engine']}",
)
check("C2: status TEST_FIRST — sengketa bukan temuan selesai (bukan STOP)", c_stop["status"] == "TEST_FIRST")
check(
    "C2: temuan yang dipersoalkan bukan alasan berhenti (tanpa ENGINE_CONTRADICTION di stop_provenance)",
    all(sp["source"] != "ENGINE_CONTRADICTION" for sp in c_stop["stop_provenance"]),
    str(c_stop["stop_provenance"]),
)
check("C2: sengketa tetap tercatat di butir", c_stop["conflicts"] == [REQ])
c_rev = proj2(
    pp("s1", "SUPPORTED", [check_row("wtp", "PRESENT", requirement_id=REQ)]),
    [node(REQ, "ABSENT", nid="n1")],
)["paths"][0]
check(
    "C2: dukungan yang bersandar pada check sengketa → UNDETERMINED (bukan SUPPORTED)",
    c_rev["feasibility"] == "UNDETERMINED" and c_rev["feasibility_engine"] == "SUPPORTED",
    f"{c_rev['feasibility']} / {c_rev['feasibility_engine']}",
)
check(
    "C2: status TEST_FIRST, bukan OPEN — dukungan yang dipersoalkan bukan kesiapan",
    c_rev["status"] == "TEST_FIRST",
)
check(
    "C2: keadaan proyeksi = otoritas ledger (ABSENT), sengketa tercatat",
    c_rev["items"][0]["state"] == "ABSENT" and c_rev["items"][0]["settled"] is False,
)
c_unk = proj2(pp("s1", "CONTRADICTED", HARD_ABSENT), [node(REQ, "UNKNOWN", nid="n1")])["paths"][0]
check(
    "C2: UNKNOWN vs pasti → tanpa sengketa: pembacaan engine utuh (CONTRADICTED → STOP tetap)",
    c_unk["feasibility"] == c_unk["feasibility_engine"] == "CONTRADICTED" and c_unk["status"] == "STOP",
)
c_nor = build_readiness_projection(
    diagnosis_with(pathset(pp("s1", "CONTRADICTED", HARD_ABSENT))), routes_of()
)["paths"][0]
check(
    "C2: tanpa route tidak ada sengketa → pembacaan engine identitas",
    c_nor["feasibility"] == "CONTRADICTED",
)
c_multi = proj2(
    pp(
        "s1",
        "CONTRADICTED",
        [
            check_row("wtp-a", "ABSENT", kind="hard", requirement_id=REQ),
            check_row("wtp-b", "ABSENT", kind="hard", requirement_id=REQ),
        ],
    ),
    [node(REQ, "PRESENT", nid="n1")],
)["paths"][0]
mi = c_multi["items"][0]
check(
    "C2: multi-sumber tetap SATU butir (bukan duplikat yang menyembunyikan perselisihan)",
    len(c_multi["items"]) == 1,
)
check(
    "C2: kedua check tercatat sebagai sumber konflik (check + check_2)",
    mi["conflict"]["sources"] == {"route": "PRESENT", "check": "ABSENT", "check_2": "ABSENT"}
    and mi["conflict"].get("additional_check_ids") == ["wtp-b"],
    str(mi.get("conflict")),
)
check(
    "C2: counts conflicted = 1 (semua bucket + conflicted = total)",
    c_multi["counts"]["conflicted"] == 1 and c_multi["counts"]["total"] == 1,
    str(c_multi["counts"]),
)
gate_path = pp("s1", "CONTRADICTED", HARD_ABSENT)
check(
    "C2: gate NextMove atas pembacaan teradjudikasi: sengketa → TEST_FIRST (ikut dipertimbangkan)",
    display_status(canonical_feasibility(gate_path, [node(REQ, "PRESENT", nid="n1")]), "OPEN")
    == "TEST_FIRST",
)
check(
    "C2: gate NextMove: kontradiksi TANPA sengketa tetap STOP",
    display_status(canonical_feasibility(gate_path, [node(REQ, "UNKNOWN", nid="n1")]), "OPEN") == "STOP",
)
check(
    "C2: fungsi kanonik sepakat dengan butir settled proyeksi (satu definisi konflik)",
    path_conflicted_requirements(gate_path, [node(REQ, "PRESENT", nid="n1")]) == {REQ}
    and path_conflicted_requirements(
        pp("s1", "SUPPORTED", [check_row("wtp", "PRESENT", requirement_id=REQ)]),
        [node(REQ, "UNKNOWN", nid="n1")],
    )
    == set(),
)

# narrative over five states: PRESENT, PARTIAL, UNKNOWN, ABSENT, CONFLICT
matrix = proj(
    [
        node("offering.outcome", "PRESENT", nid="a"),
        node("commercial.pricing_basis", "PARTIAL", nid="b"),
        node("commercial.price", "UNKNOWN", nid="c"),
        node("delivery.capacity", "ABSENT", nid="d"),
        node(REQ, "PRESENT", nid="e"),
    ],
    [check_row("wtp", "ABSENT", kind="hard", requirement_id=REQ)],
)["paths"][0]
items = {i["key"]: i for i in matrix["items"]}
check("NARR: CONFLICT adalah jenis klaim yang dikenal", "CONFLICT" in CLAIM_TYPES)


def claim(ctype: str, key: str) -> dict:
    return ground_claim({"field": "unclear", "claim": "x", "claim_type": ctype, "requirement": key}, matrix)


expect_ok = {
    ("SUPPORTED", "offering.outcome"),
    ("PARTIAL", "commercial.pricing_basis"),
    ("UNKNOWN", "commercial.price"),
    ("MISSING", "delivery.capacity"),
    ("CONFLICT", REQ),
}
wrong = []
for ctype in ("SUPPORTED", "PARTIAL", "UNKNOWN", "MISSING", "CONFLICT"):
    for key in items:
        ok = claim(ctype, key)["grounded"]
        if ok != ((ctype, key) in expect_ok):
            wrong.append((ctype, key, ok))
check(
    "NARR: matriks klaim x 5 keadaan (PRESENT/PARTIAL/UNKNOWN/ABSENT/CONFLICT): hanya yang cocok lolos",
    not wrong,
    str(wrong),
)
check(
    "NARR: butir berkonflik tidak boleh dinyatakan SUPPORTED (sengketa bukan fakta selesai)",
    not claim("SUPPORTED", REQ)["grounded"] and "berkonflik" in claim("SUPPORTED", REQ)["violation"],
)
check(
    "NARR: UNKNOWN tidak boleh diucapkan sebagai MISSING",
    not claim("MISSING", "commercial.price")["grounded"],
)
narr = matrix["narrative"]
grounded = [ground_claim(c, matrix) for c in narr["claims"]]
check(
    "NARR: fallback memakai proyeksi yang sama: semua klaimnya ter-ground menurut konstruksi",
    all(c["grounded"] for c in grounded) and narr["claims"],
    str([c["violation"] for c in grounded if not c["grounded"]]),
)
check(
    "NARR: fallback tidak menyatakan butir berkonflik sebagai sudah dimiliki",
    any(c["claim_type"] == "CONFLICT" for c in narr["claims"])
    and "willingness to pay" not in narr["supported"].lower(),
    narr["supported"],
)
check(
    "NARR: klaim butir berkonflik di fallback berada di field unclear (bukan supported)",
    all(c["field"] == "unclear" for c in narr["claims"] if c["claim_type"] == "CONFLICT"),
)
check(
    "NARR: fallback_narrative sendiri bebas dari butir tanpa label_ok",
    fallback_narrative("OPEN", [{"key": "k", "state": "PRESENT", "title": {"text": "X"}, "evidence": ["e"]}])[
        "supported"
    ]
    == "",
)
ask_txt = _paths_read({"paths": [matrix]})
wtp_line = next(ln for ln in ask_txt.splitlines() if "commercial.willingness_to_pay" in ln)
check(
    "NARR: prompt penjelas menandai butir berkonflik CONFLICT, bukan confirmed",
    "CONFLICT" in wtp_line and "confirmed" not in wtp_line,
    wtp_line,
)

# ══ E. "NO CHECK" != FEASIBLE ══════════════════════════════════════════════════════════════════════
check(
    "E: feasibility_from_checks([]) = UNDETERMINED (bukan all([]) yang diam-diam TRUE)",
    feasibility_from_checks([]).value == "UNDETERMINED",
)
check(
    "E: pernyataan eksplisit tanpa prasyarat = SUPPORTED",
    feasibility_from_checks([], unconditional=True).value == "SUPPORTED",
)
R = reader_of({"state:g": True, "state:t": True}, {"state:g": ("e0",), "state:t": ("e1",)})


def one(strategy: StrategySpec) -> dict:
    return build_path_set(PossibilitySpace("e", (strategy,), "state:g"), R)["paths"][0]


none_p = one(StrategySpec("bare", "Bare", emerges_when="state:t"))
check(
    "E: strategi tanpa check: UNDETERMINED + basis NO_CHECKS_DECLARED + status TEST_FIRST",
    (none_p["feasibility"], none_p["feasibility_basis"], none_p["status"])
    == ("UNDETERMINED", "NO_CHECKS_DECLARED", "TEST_FIRST"),
)
free = one(StrategySpec("free", "Free", emerges_when="state:t", no_preconditions=True))
check(
    "E: strategi yang MENYATAKAN tanpa prasyarat: SUPPORTED + basis DECLARED_UNCONDITIONAL",
    (free["feasibility"], free["feasibility_basis"]) == ("SUPPORTED", "DECLARED_UNCONDITIONAL"),
)
chk = one(StrategySpec("chk", "Chk", emerges_when="state:t", checks=(CheckSpec("c", "state:t"),)))
check(
    "E: strategi dengan check yang PRESENT: SUPPORTED + basis CHECKS",
    (chk["feasibility"], chk["feasibility_basis"]) == ("SUPPORTED", "CHECKS"),
)
check(
    "E: no_preconditions bersama checks ditolak (pernyataan saling bertentangan)",
    bool(
        raises(
            lambda: StrategySpec(
                "x", "X", emerges_when="s", checks=(CheckSpec("c", "s"),), no_preconditions=True
            )
        )
    ),
)
check(
    "E: SUPPORTED bukan satisfaction: path SUPPORTED dengan 0 butir terbukti tetap sah (OPEN != READY)",
    proj([node("offering.outcome", "UNKNOWN", nid="a")], [])["paths"][0]["counts"]["present"] == 0,
)
msg = raises(lambda: evaluate({"all_of": []}, R))
check("E: all_of tanpa operan ditolak (TRUE hampa tanpa dukungan dilarang)", bool(msg), msg or "")
check(
    "E: any_of tanpa operan ditolak (FALSE hampa dilarang)", bool(raises(lambda: evaluate({"any_of": []}, R)))
)
check(
    "E: predikat cacat ditolak saat strategi dibentuk, bukan saat dievaluasi",
    bool(raises(lambda: StrategySpec("m", "M", emerges_when={"all_of": []}))),
)
check("E: predikat kosong tetap = tak ada klaim (None), bukan TRUE", evaluate({}, R).value is None)

# ══ C. LEGACY ARTIFACTS: zero paths from an old artifact != zero paths from evidence ══════════════
check(
    "C: tanpa PathSet -> LEGACY + needs_rediagnosis",
    (assess_path_set(None)["status"] == "LEGACY" and assess_path_set(None)["needs_rediagnosis"] is True),
)
old = assess_path_set({"version": 2, "paths": []})
check(
    "C: PathSet versi lain -> LEGACY (bukan 'nol path')",
    old["status"] == "LEGACY"
    and old["reason_code"] == "SCHEMA_VERSION_MISMATCH"
    and old["found_version"] == 2
    and old["current_version"] == PATHSET_VERSION,
)
cur0 = assess_path_set({"version": PATHSET_VERSION, "paths": [], "unresolved": [{"code": "X"}]})
check(
    "C: PathSet versi ini dengan 0 path = CURRENT: nol path adalah temuan engine yang sah",
    cur0["status"] == "CURRENT" and cur0["needs_rediagnosis"] is False,
)
check("C: teks penjelasan datang dari engine (id + en)", old["detail"] and old["i18n"]["en"]["detail"])

# legacy artifact genuinely read from the session disk (key `revenue_paths`, no possible_paths)
real = revenue_artifact(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0).model_dump()
legacy_dump = {k: v for k, v in real.items() if k not in ("possible_paths", "navigation")}
legacy_dump["revenue_paths"] = [{"path": "ACQUISITION", "gate": "ELIGIBLE"}] * 5
legacy_art = DiagnosisArtifact(**legacy_dump)
check(
    "C: DiagnosisArtifact lama dimuat: possible_paths None, navigation LEGACY",
    legacy_art.possible_paths is None and legacy_art.navigation["status"] == "LEGACY",
)
fresh = revenue_artifact(current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0)
check(
    "C: artefak baru dari engine: CURRENT",
    fresh.navigation["status"] == "CURRENT" and fresh.possible_paths["version"] == PATHSET_VERSION,
)
thin = revenue_artifact(target_monthly=20.0)
check(
    "C: state tipis nyata -> nol path tetapi CURRENT (dengan alasan unresolved)",
    thin.possible_paths["paths"] == []
    and thin.possible_paths["unresolved"]
    and thin.navigation["status"] == "CURRENT",
)

# via the real SessionStore (loaded from disk) and HTTP
sdir = _tmp / "sessions"
sdir.mkdir()
sid = "legacy000001"
(sdir / f"{sid}.json").write_text(
    json.dumps(
        {
            "id": sid,
            "goal_text": "naik ke 20 juta",
            "language": "id",
            "interview_done": True,
            "user_id": "u-legacy",
            "diagnosis": legacy_dump,
            "evidence": [],
            "transcript": [],
        },
        default=str,
    )
)
saved_dir = memory.SessionStore.PERSIST_DIR
memory.SessionStore.PERSIST_DIR = sdir
try:
    loaded = memory.SessionStore()
finally:
    memory.SessionStore.PERSIST_DIR = saved_dir
ls = loaded.get(sid)
check(
    "C: SessionStore memuat sesi lama tanpa crash; artefaknya LEGACY",
    ls is not None and ls.diagnosis.navigation["status"] == "LEGACY",
)

c = TestClient(app)
memory.store._sessions[sid] = ls
saved_persist = memory.store.PERSIST_DIR
memory.store.PERSIST_DIR = sdir  # next save() will not touch the repo's store/sessions
try:
    body = c.get(f"/session/{sid}/diagnosis").json()
    check(
        "C: GET /diagnosis membawa navigation LEGACY; possible_paths tidak dikarang (null)",
        body["navigation"]["status"] == "LEGACY" and body["possible_paths"] is None,
    )
    rd = c.get(f"/session/{sid}/readiness").json()
    check(
        "C: GET /readiness: paths=[] TETAPI navigation LEGACY (bukan temuan 'tidak ada path')",
        rd["paths"] == []
        and rd["unresolved"] == []
        and rd["navigation"]["status"] == "LEGACY"
        and rd["navigation"]["needs_rediagnosis"] is True,
    )
    rt = c.post(f"/session/{sid}/routes").json()
    check(
        "C: POST /routes: tanpa route, alasan = artefak lama (bukan 'belum ada path')",
        rt["routes"] == [] and "lebih tua" in rt["reason"] and rt["navigation"]["status"] == "LEGACY",
    )
    code = None
    try:
        _require_known_path(ls, "path.value_repricing")
    except HTTPException as e:
        code = e.status_code
    check(
        "C: outcome pada path artefak lama -> 409 (diagnosis ulang), bukan 422 'path tak dikenal'",
        code == 409,
        str(code),
    )
    check(
        "C: penjelas/ask tidak diberi tahu 'tidak ada path' untuk artefak LEGACY",
        "NO path result exists" in _paths_read(rd) and "predates" in readiness_lines(ls.diagnosis, rd),
    )
    cur = revenue_artifact(target_monthly=20.0)
    ls2 = memory.store.create("naik ke 20 juta", "id", user_id="u-thin")
    ls2.diagnosis = cur
    rd2 = c.get(f"/session/{ls2.id}/readiness").json()
    check(
        "C: artefak CURRENT dengan nol path: alasan engine tetap dibawa, bukan LEGACY",
        rd2["navigation"]["status"] == "CURRENT" and rd2["paths"] == [] and rd2["unresolved"],
    )
    # Task G: a CURRENT-versioned PathSet with BROKEN CONTENT = LEGACY (PATHSET_MALFORMED) — neither a
    # "no paths" finding nor a 500. Regression: before the fix, readiness 500'd on such artifacts.
    ls2.diagnosis = DiagnosisArtifact(
        **{
            **cur.model_dump(),
            "possible_paths": {"version": PATHSET_VERSION, "paths": [{"strategy_id": "s"}]},
        }
    )
    rd3 = c.get(f"/session/{ls2.id}/readiness").json()
    check(
        "C: isi PathSet rusak (entri tanpa path_id) -> LEGACY PATHSET_MALFORMED; paths=[]; bukan 500",
        rd3["navigation"]["status"] == "LEGACY"
        and rd3["navigation"]["reason_code"] == "PATHSET_MALFORMED"
        and rd3["paths"] == []
        and rd3["navigation"]["i18n"]["en"]["detail"]
        and rd3["navigation"]["needs_rediagnosis"] is True,
    )
    for label, ps in (
        ("paths bukan list", {"version": PATHSET_VERSION, "paths": "junk"}),
        ("entri bukan dict", {"version": PATHSET_VERSION, "paths": [42]}),
        ("path_id kosong", {"version": PATHSET_VERSION, "paths": [{"path_id": ""}]}),
        # audit this iteration: the old gate was narrower than what downstream reads — these five shapes
        # passed as CURRENT then 500'd in readiness/POST /routes. All = PATHSET_MALFORMED.
        ("strategy_id hilang", {"version": PATHSET_VERSION, "paths": [{"path_id": "path.s"}]}),
        (
            "strategy_id tak bisa jadi key dict",
            {
                "version": PATHSET_VERSION,
                "paths": [
                    {
                        "path_id": "path.s",
                        "strategy_id": {"x": 1},
                        "feasibility": "UNDETERMINED",
                        "checks": [],
                    }
                ],
            },
        ),
        (
            "checks bukan list",
            {
                "version": PATHSET_VERSION,
                "paths": [
                    {"path_id": "path.s", "strategy_id": "s", "feasibility": "UNDETERMINED", "checks": "junk"}
                ],
            },
        ),
        (
            "feasibility di luar enum",
            {
                "version": PATHSET_VERSION,
                "paths": [{"path_id": "path.s", "strategy_id": "s", "feasibility": 42, "checks": []}],
            },
        ),
        (
            "route_substrate bukan dict",
            {
                "version": PATHSET_VERSION,
                "paths": [
                    {
                        "path_id": "path.s",
                        "strategy_id": "s",
                        "feasibility": "UNDETERMINED",
                        "checks": [],
                        "route_substrate": "junk",
                    }
                ],
            },
        ),
        (
            "sehat: satu path (semua field yang dibaca hilir hadir)",
            {
                "version": PATHSET_VERSION,
                "paths": [
                    {
                        "path_id": "path.s",
                        "strategy_id": "s",
                        "status": "OPEN",
                        "feasibility": "UNDETERMINED",
                        "checks": [],
                    }
                ],
            },
        ),
    ):
        a = assess_path_set(ps)
        want = "CURRENT" if label.startswith("sehat") else "LEGACY"
        check(
            f"C: PathSet {label} -> {want}" + ("" if want == "CURRENT" else " PATHSET_MALFORMED"),
            a["status"] == want and (want == "CURRENT" or a["reason_code"] == "PATHSET_MALFORMED"),
            str(a["reason_code"]),
        )
finally:
    memory.store.PERSIST_DIR = saved_persist
    memory.store._sessions.pop(sid, None)
    try:
        memory.store._sessions.pop(ls2.id, None)
        (saved_persist / f"{ls2.id}.json").unlink(missing_ok=True)
    except Exception:
        pass

failed = [n for n, ok, _ in _results if not ok]
print("=" * 50)
print(
    f"HASIL: {len(_results) - len(failed)}/{len(_results)} PASS"
    + (f" — {len(failed)} GAGAL ❌" if failed else " ✅")
)
sys.exit(1 if failed else 0)
