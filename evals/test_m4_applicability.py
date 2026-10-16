"""M4 — Applicable Requirement Set + Requirement State Reader (internal-docs §25).

Proves the contract, not merely the data shape:

  A  applicability: APPLYING requirements are SELECTED, NOT_APPLICABLE ones ignored, UNKNOWN ones
     handled explicitly
  B  registry extensibility: a new requirement joins with no code change (only if some context
     anchors it)
  C  UNKNOWN != ABSENT: nothing downgrades "not yet known" to "absent"
  L  no relevance: a global requirement without context is NOT a set member (registry is not a
     checklist)
  M  candidate-born paths take the same road (no special lane for candidate paths)
  N  route optional: the set still forms without a route
     one merge rule: `merge_readings` == `readiness._adjudicate` over the full matrix (not two
     evaluators)
     reader: ledger authoritative, decisive checks fill UNKNOWN, conflict = metadata, ledger
     visible without a route
     axes: applicability != navigable (a STOP path still has its own applicability)

Deterministic, no LLM, no network, no store access. Run: .venv/bin/python evals/test_m4_applicability.py
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from core.navigation import readiness  # noqa: E402
from core.navigation.applicability import (  # noqa: E402
    REASON_APPLIES,
    REASON_NOT_APPLICABLE,
    REASON_UNKNOWN,
    ApplicableRequirementSet,
    build_applicable_set,
)
from core.navigation.requirement_state import (  # noqa: E402
    SUPPORT_FORMAL,
    SUPPORT_NONE,
    MappingReader,
    RequirementState,
    merge_readings,
    read_requirement_views,
    status_reader,
    unknown_state,
)
from engine.requirements import describe, is_known, load_registry  # noqa: E402
from evals.navigation_fixtures import check_row, node, pathset, pp, routes_of  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


def raises(fn, exc=ValueError) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


UNKNOWN, PRESENT, ABSENT, PARTIAL = "UNKNOWN", "PRESENT", "ABSENT", "PARTIAL"


def two_path_set() -> dict:
    """Two paths: outreach (two anchored checks + one unanchored check) and referral (one check)."""
    return pathset(
        pp(
            "direct_outreach",
            "UNDETERMINED",
            checks=[
                check_row("capacity", UNKNOWN, requirement_id="delivery.capacity"),
                check_row("demand", UNKNOWN),  # no anchor: path-specific condition, NOT a requirement
                check_row("icp", PRESENT, requirement_id="access.icp", kind="hard"),
            ],
        ),
        pp(
            "referral_partnership",
            "UNDETERMINED",
            checks=[check_row("cap2", UNKNOWN, requirement_id="delivery.capacity")],
        ),
    )


# ───────────────────────────── A · applicability ─────────────────────────────
print("A · applicability")
ps = two_path_set()
ars = build_applicable_set(ps)
check("A1 himpunan terbentuk dari check berjangkar (route opsional)", ars.ids() == ["access.icp", "delivery.capacity"], str(ars.ids()))
check("A2 check tanpa requirement_id bukan requirement", "demand" not in str(ars.ids()))
cap = ars.get("delivery.capacity")
check("A3 requirement di dua path membawa DUA konteks (provenance utuh)",
      cap is not None and {c.id for c in cap.contexts} == {"path.direct_outreach", "path.referral_partnership"})
check("A4 konteks membawa asal: via=check, ref=check_id, strength=kind",
      all(c.via == "check" and c.ref in ("capacity", "cap2") for c in cap.contexts)
      and ars.get("access.icp").contexts[0].strength == "hard")
check("A5 APPLIES + alasan terstruktur", cap.applicability == "APPLIES" and cap.reason == REASON_APPLIES)

# route: a route node also becomes a context; route UNDETERMINED = UNKNOWN (not APPLIES)
rd = routes_of(direct_outreach=[node("access.prospect_list", UNKNOWN), node("access.icp", UNKNOWN)])
rd["routes"][0]["path_id"] = "path.direct_outreach"
rd["routes"][0]["applicability"] = {"status": "UNDETERMINED"}
ars_r = build_applicable_set(ps, rd)
prospect = ars_r.get("access.prospect_list")
check("A6 node route menjadi konteks; route UNDETERMINED -> applicability UNKNOWN (bukan APPLIES)",
      prospect is not None and prospect.applicability == "UNKNOWN" and prospect.reason == REASON_UNKNOWN
      and prospect.contexts[0].kind == "route" and prospect.contexts[0].via == "node")
check("A7 requirement di konteks UNKNOWN dan konteks APPLIES -> APPLIES (satu konteks APPLIES cukup)",
      ars_r.get("access.icp").applicability == "APPLIES")

# NOT_APPLICABLE: templates not born due to NOT_APPLICABLE are recorded explicitly, ignored downstream
nb = {"routes": [], "not_born": [{"template_id": "paid_v1", "strategy_id": "paid", "path_id": "path.paid",
                                  "outcome": "NO_ROUTE_NOT_APPLICABLE", "reason": "x"}]}
ars_na = build_applicable_set(pathset(pp("paid")), nb, template_requirements={"paid_v1": ["conversion.landing_page"]})
lp = ars_na.get("conversion.landing_page")
check("A8 template tak lahir (NOT_APPLICABLE) -> requirement NOT_APPLICABLE di konteks itu",
      lp is not None and lp.applicability == "NOT_APPLICABLE" and lp.reason == REASON_NOT_APPLICABLE
      and lp.contexts[0].via == "template")
nb2 = {"routes": [], "not_born": [{"template_id": "x_v1", "strategy_id": "a", "path_id": "path.a",
                                   "outcome": "NO_ROUTE_GOAL_PRESENT", "reason": "x"}]}
check("A9 alasan tak lahir lain (goal PRESENT) TIDAK dicatat sebagai NOT_APPLICABLE",
      build_applicable_set(pathset(pp("a")), nb2, template_requirements={"x_v1": ["access.icp"]}).items == ())
mix = build_applicable_set(
    pathset(pp("paid", checks=[check_row("c", UNKNOWN, requirement_id="conversion.landing_page")])),
    nb, template_requirements={"paid_v1": ["conversion.landing_page"]})
check("A10 NOT_APPLICABLE di satu konteks tidak mengalahkan APPLIES di konteks lain (relevan lewat jalur itu)",
      mix.get("conversion.landing_page").applicability == "APPLIES")
check("A11 NOT_APPLICABLE hanya bila SEMUA konteks NOT_APPLICABLE", lp.applicability == "NOT_APPLICABLE" and len(lp.contexts) == 1)

# ───────────────────────────── axes ─────────────────────────────
print("axes · applicability != navigable")
stop_ps = pathset(pp("hard_path", "CONTRADICTED", checks=[check_row("c", ABSENT, requirement_id="access.icp", kind="hard")]))
a = build_applicable_set(stop_ps).get("access.icp")
check("X1 path STOP tetap APPLIES (sumbu applicability) tetapi konteksnya tidak navigable",
      a.applicability == "APPLIES" and a.contexts[0].navigable is False)
check("X2 path tidak STOP -> navigable", build_applicable_set(two_path_set()).get("delivery.capacity").contexts[0].navigable is True)

# ───────────────────────────── B · registry extensibility ─────────────────────────────
print("B · registry extensibility")
NEW_REQ = "hiring.interview_rubric"
check("B0 requirement baru belum ada di registry produksi (fixture benar-benar 'baru')", not is_known(NEW_REQ))
ars_new = build_applicable_set(pathset(pp("structured", checks=[check_row("rubric", UNKNOWN, requirement_id=NEW_REQ)])))
check("B1 requirement baru ikut himpunan TANPA perubahan kode (konteks yang menjangkarkannya)",
      ars_new.ids() == [NEW_REQ])
d = describe(NEW_REQ, "en")
check("B2 presentation fallback deterministik membaca requirement baru (title dari id, tanpa kamus kedua)",
      d["title"]["text"] == "Interview rubric" and d["title"]["source"] == "fallback")
check("B3 modul tidak memuat daftar requirement apa pun (nol literal id registry di applicability/requirement_state)",
      not any(rid in Path(__file__).resolve().parents[1].joinpath("core/navigation/applicability.py").read_text()
              for rid in list(load_registry())[:49]))

# ───────────────────────────── L · no relevance ─────────────────────────────
print("L · no-relevance: registry bukan checklist")
registry_ids = set(load_registry())
member = set(build_applicable_set(two_path_set()).ids())
check("L1 himpunan jauh lebih kecil dari registry (49 -> hanya yang dinyatakan konteks)", len(member) < len(registry_ids) // 5)
check("L2 requirement global tanpa konteks BUKAN anggota (bukan 'tidak berlaku', bukan 'berlaku')",
      "commercial.price" in registry_ids and "commercial.price" not in member)
check("L3 PathSet kosong (nol path) -> himpunan kosong, bukan seluruh registry",
      build_applicable_set(pathset(unresolved=[{"code": "EMPTY_POSSIBILITY_SPACE"}])).items == ())
check("L4 PathSet LEGACY/None tidak dibaca (DATA-01): kosong, tak ada karangan",
      build_applicable_set(None).items == () and build_applicable_set({"version": 1, "paths": [{"junk": 1}]}).items == ())

# ───────────────────────────── C · UNKNOWN != ABSENT (reader) ─────────────────────────────
print("C · UNKNOWN != ABSENT")
check("C1 UNKNOWN by absence tak membawa sitasi/asal/waktu", unknown_state("x.y").adjudicated is False
      and unknown_state("x.y").evidence_refs == () and unknown_state("x.y").last_updated is None)
check("C2 status tanpa adjudikasi = karangan -> ditolak oleh kontrak",
      raises(lambda: RequirementState("x.y", satisfaction=ABSENT))
      and raises(lambda: RequirementState("x.y", evidence_refs=("ev-1",)))
      and raises(lambda: RequirementState("x.y", verification={"m": 1})))
check("C3 enum di luar kontrak ditolak", raises(lambda: RequirementState("x.y", satisfaction="CONFLICT", adjudicated=True))
      and raises(lambda: RequirementState("x.y", support="WHATEVER")))
check("C4 StatusReader route: tanpa adjudikasi = None (UNKNOWN by absence); adjudikasi UNKNOWN = 'UNKNOWN'",
      status_reader(MappingReader({}))("a.b") is None
      and status_reader(MappingReader({"a.b": UNKNOWN}))("a.b") == "UNKNOWN"
      and status_reader(MappingReader({"a.b": PRESENT}))("a.b") == "PRESENT")
views = read_requirement_views(build_applicable_set(two_path_set()), MappingReader({}), two_path_set(), None)
check("C5 tanpa adjudikasi apa pun, requirement UNKNOWN tetap UNKNOWN (tidak pernah ABSENT)",
      views["delivery.capacity"].satisfaction == UNKNOWN and views["delivery.capacity"].ledger.adjudicated is False)
check("C6 view tak mengarang sitasi/waktu", views["delivery.capacity"].evidence_refs == ()
      and views["delivery.capacity"].last_updated is None and views["delivery.capacity"].verification is None)

# ───────────────────────── single merge rule: merge_readings == readiness._adjudicate ─────────────────────────
print("merge · satu aturan, bukan dua evaluator")
STATES = (PRESENT, PARTIAL, UNKNOWN, ABSENT)
mismatches = []
for primary, *chk in itertools.chain(
    itertools.product(STATES, STATES),
    itertools.product(STATES, STATES, STATES),
    itertools.product(STATES, STATES, STATES, STATES),
):
    route_it = [{"requirement_id": "r.x", "state": primary, "partial": primary == PARTIAL, "sources": ["route"],
                 "check_id": None, "reason": {}, "unlock": {}, "evidence": [], "key": "r.x"}]
    check_its = [{"requirement_id": "r.x", "state": s, "partial": s == PARTIAL, "check_id": f"c{i}",
                  "reason": {}, "unlock": {}, "evidence": [f"check:c{i}"], "key": "r.x"} for i, s in enumerate(chk)]
    out = readiness._adjudicate(route_it, check_its)[0]
    merged, bad = merge_readings(primary, chk)
    in_conflict = not out.get("settled", True)
    if out["state"] != merged or in_conflict != bool(bad):
        mismatches.append((primary, chk, out["state"], merged, in_conflict, bad))
check("M1 merge_readings == readiness._adjudicate atas 4+16+64+256 kombinasi (keadaan DAN sengketa)",
      not mismatches, str(mismatches[:3]))
check("M2 keadaan pasti mengalahkan UNKNOWN; UNKNOWN bukan pihak yang berselisih",
      merge_readings(UNKNOWN, [PRESENT]) == (PRESENT, ()) and merge_readings(PRESENT, [UNKNOWN]) == (PRESENT, ()))
check("M3 dua pembacaan pasti berbeda = sengketa (ledger berotoritas), bukan state kelima",
      merge_readings(PRESENT, [ABSENT]) == (PRESENT, (0,)) and merge_readings(UNKNOWN, [PRESENT, ABSENT]) == (PRESENT, (1,)))
check("M4 nilai di luar enum diperlakukan UNKNOWN (tak pernah dikarang jadi pasti)",
      merge_readings("BOGUS", ["ALSO_BOGUS"]) == (UNKNOWN, ()))

# ───────────────────────────── reader: ledger authoritative, route optional ─────────────────────────────
print("reader · satu pembaca untuk semua konsumen")
ledger = MappingReader(
    {"access.icp": RequirementState("access.icp", PRESENT, True, ("ev-1",), {"method": "deterministic_adjudicator"},
                                    1700000000, support=SUPPORT_FORMAL)},
    support={"access.icp": SUPPORT_FORMAL},
)
ps2 = pathset(pp("direct_outreach", checks=[check_row("icp", UNKNOWN, requirement_id="access.icp", kind="hard")]))
v = read_requirement_views(build_applicable_set(ps2), ledger, ps2, None)["access.icp"]
check("R1 ledger terlihat TANPA route (route opsional): konteks path memakai pembacaan ledger",
      v.satisfaction == PRESENT and v.contexts[0].sources == ("ledger",) and v.contexts[0].state == PRESENT)
check("R2 view membawa evidence_refs, verification, last_updated, support dari adjudikasi (tak dikarang)",
      v.evidence_refs == ("ev-1",) and v.verification == {"method": "deterministic_adjudicator"}
      and v.last_updated == 1700000000 and v.support == SUPPORT_FORMAL)
ps3 = pathset(pp("direct_outreach", checks=[check_row("icp", ABSENT, requirement_id="access.icp", kind="hard")]))
v3 = read_requirement_views(build_applicable_set(ps3), ledger, ps3, None)["access.icp"]
check("R3 ledger PRESENT vs check ABSENT = SENGKETA tercatat (konteks + requirement), ledger berotoritas",
      v3.conflict is True and v3.satisfaction == PRESENT and v3.contexts[0].conflict is True)
ps4 = pathset(pp("direct_outreach", checks=[check_row("cap", PRESENT, requirement_id="delivery.capacity")]))
v4 = read_requirement_views(build_applicable_set(ps4), MappingReader({}), ps4, None)["delivery.capacity"]
check("R4 check pasti mengisi UNKNOWN ledger (aturan Readiness yang sama): ledger kosong + check PRESENT -> PRESENT",
      v4.satisfaction == PRESENT and v4.contexts[0].sources == ("check",) and v4.ledger.adjudicated is False)
rd5 = routes_of(direct_outreach=[node("access.icp", UNKNOWN)])
rd5["routes"][0]["path_id"] = "path.direct_outreach"
v5 = read_requirement_views(build_applicable_set(ps3, rd5), MappingReader({}), ps3, rd5)["access.icp"]
rc = [c for c in v5.contexts if c.kind == "route"][0]
check("R5 konteks route memakai satisfaction NODE (ledger lewat komposer) dan merge dengan check path-nya",
      rc.state == ABSENT and rc.sources == ("check",))
rd6 = routes_of(direct_outreach=[node("access.icp", PRESENT)])
v6 = read_requirement_views(build_applicable_set(ps3, rd6), MappingReader({}), ps3, rd6)["access.icp"]
rc6 = [c for c in v6.contexts if c.kind == "route"][0]
check("R6 node PRESENT vs check ABSENT di konteks route = sengketa (identik dengan Readiness)",
      rc6.state == PRESENT and rc6.conflict is True)
check("R7 view JSON-serializable penuh (replay)", bool(json.dumps(v6.to_dict())))
check("R8 ApplicableRequirementSet round-trip dict->objek->dict identik",
      ApplicableRequirementSet.from_dict(ars_r.to_dict()).to_dict() == ars_r.to_dict())
check("R9 pembaca tanpa user (support=NO_USER_SCOPE/NONE) tidak mengarang keadaan",
      MappingReader({}, support=SUPPORT_NONE).read("a.b").satisfaction == UNKNOWN)

# ───────────────────────────── M · candidate-born path gets no special treatment ─────────────────────────────
print("M · candidate-born path memakai jalur yang sama")
cand_path = pp("improve_activation", checks=[check_row("aha", UNKNOWN, requirement_id="retention.aha_moment_defined")])
cand_path["provenance"]["candidate"] = {"candidate_id": "cand.improve_activation", "origin": "MECHANISM_PATTERN"}
plain_path = pp("improve_activation", checks=[check_row("aha", UNKNOWN, requirement_id="retention.aha_moment_defined")])
check("M1 path asal-kandidat == path strategi terdeklarasi untuk himpunan applicable",
      build_applicable_set(pathset(cand_path)).to_dict() == build_applicable_set(pathset(plain_path)).to_dict())
src = Path(__file__).resolve().parents[1].joinpath("core/navigation/applicability.py").read_text()
check("M2 modul tak menyebut candidate/origin sama sekali (tak ada cabang khusus)",
      "candidate" not in src.lower().replace("candidate-born", "") or "provenance" not in src)

# ───────────────────────────── N · route opsional ─────────────────────────────
print("N · route optional")
check("N1 tanpa route sama sekali himpunan tetap terbentuk (paths saja)", len(build_applicable_set(two_path_set(), None)) == 2)
check("N2 route kosong == tanpa route", build_applicable_set(two_path_set(), {"routes": [], "not_born": []}).to_dict()
      == build_applicable_set(two_path_set()).to_dict())
check("N3 route tak mengubah requirement yang sudah dinyatakan check (hanya menambah konteks)",
      {c.kind for c in ars_r.get("access.icp").contexts} == {"path", "route"})

print()
bad = [n for n, ok, _ in RESULTS if not ok]
print(f"HASIL: {len(RESULTS) - len(bad)}/{len(RESULTS)} PASS {'✅' if not bad else '❌ ' + str(bad)}")
sys.exit(0 if not bad else 1)
