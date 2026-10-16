"""M4 — Question Planner: deterministic decisions driven by STATE and uncertainty (internal-docs §25).

All tests run production code (`assemble_planner_input` -> `plan_next_move` -> `render_move`) over fixture-built
PathSets/routes; no requirement list is baked into the planner. What is proven:

  F   the four outputs: QUESTION · EVIDENCE_REQUEST · ACTION · HOLD
  G   applicability uncertainty -> RESOLVE_APPLICABILITY (canonical), not mixed with the route frontier
  H   contradictions are not forced closed: the planner asks for discriminating evidence
  K   enough to act -> stop asking (ACTION), no invented questions
  L   a non-applicable global requirement is never asked about
  B   registry extensibility: a new requirement joins with no planner code change
  dependency A -> B -> C: C is not mined before A
  uncertainty-driven: not a phase index/fixed order; input order does not shift decisions
  loop guard: a need is not asked about forever (QUESTION -> EVIDENCE_REQUEST -> skipped)
  ASK vs ACT: what cannot be resolved in conversation is not asked (handed to action)
  J   direction switch: new evidence shifts focus without a restart
  replay: same input -> identical decision; the stored decision can be re-checked
  reason trail: machine-readable, complete, JSON-safe
  no ranking / no LLM / no phases (AST)

Deterministic, no LLM, no network. Run: .venv/bin/python evals/test_m4_planner.py
"""
from __future__ import annotations

import ast
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from core.navigation.applicability import build_applicable_set  # noqa: E402
from core.navigation.planner import (  # noqa: E402
    ACT,
    ASK,
    ASK_CAP,
    KIND_ACTION,
    KIND_EVIDENCE,
    KIND_HOLD,
    KIND_QUESTION,
    KINDS,
    NON_DECISION_KEYS,
    digest,
    plan_next_move,
    replay,
)
from core.navigation.planner_input import assemble_planner_input  # noqa: E402
from core.navigation.planner_text import render_move  # noqa: E402
from core.navigation.requirement_state import (  # noqa: E402
    SUPPORT_FORMAL,
    SUPPORT_NONE,
    MappingReader,
    RequirementState,
    read_requirement_views,
)
from engine.requirements import describe  # noqa: E402
from evals.navigation_fixtures import check_row, node, pathset, pp, routes_of  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


UNKNOWN, PRESENT, ABSENT = "UNKNOWN", "PRESENT", "ABSENT"
ICP = RequirementState("access.icp", PRESENT, True, ("ev-1",), {"method": "deterministic_adjudicator"}, 1,
                       support=SUPPORT_FORMAL)


def build(path_set, route_data=None, *, ledger=None, asked=None, signals=None, lang="en", signal_of=None,
          support=None, turn=1):
    """PathSet (+ route) + ledger -> (input, decision, text) through the production path."""
    ars = build_applicable_set(path_set, route_data)
    reader = ledger if ledger is not None else MappingReader({}, support=support or SUPPORT_NONE)
    views = read_requirement_views(ars, reader, path_set, route_data)
    inp = assemble_planner_input(
        lang=lang, turn=turn, path_set=path_set, route_data=route_data, applicable=ars, views=views,
        describe=lambda rid: describe(rid, lang),
        signal_of=signal_of or (lambda sid, cid: f"state:{cid}"),
        resolvable=lambda s: (signals or {}).get(s, ASK),
        signal_text=lambda s: {"en": f"{s} is not known yet", "id": f"{s} belum diketahui"},
        asked=asked,
    )
    dec = plan_next_move(inp)
    return inp, dec, render_move(dec, inp, lang)


def route_for(strategy, nodes, *, applies=True, next_move=None):
    rd = routes_of(**{strategy: nodes})
    rd["routes"][0]["path_id"] = f"path.{strategy}"
    if not applies:
        rd["routes"][0]["applicability"] = {"status": "UNDETERMINED"}
    rd["next_move"] = next_move
    return rd


FORMAL = {"access.icp": SUPPORT_FORMAL}

# ───────────────────────────── F · four outputs ─────────────────────────────
print("F · QUESTION / EVIDENCE_REQUEST / ACTION / HOLD")
ps_q = pathset(pp("outreach", "UNDETERMINED", checks=[check_row("capacity", UNKNOWN, requirement_id="delivery.capacity")]))
inp, d, txt = build(ps_q)
check("F1 QUESTION: requirement UNKNOWN yang dapat dijawab lewat state -> QUESTION RESOLVE_STATE",
      d["kind"] == KIND_QUESTION and d["intent"] == "RESOLVE_STATE" and d["focus"] == {"type": "requirement", "id": "delivery.capacity"}, str(d["focus"]))
check("F1b teks dirender dari presentation registry (bukan kamus planner) dan menyebut judul requirement",
      "Hours you can spare" in txt["text"] and txt["headline"] == "Hours you can spare", txt["text"])

# EVIDENCE_REQUEST: asked once already -> escalate to a concrete evidence request
inp, d, txt = build(ps_q, asked={"requirement:delivery.capacity": 1})
check("F2 EVIDENCE_REQUEST: setelah QUESTION tak menggeser state -> minta bukti konkret",
      d["kind"] == KIND_EVIDENCE and d["intent"] == "COLLECT_EVIDENCE", str(d["kind"]))

# ACTION: all askable needs are resolved -> pass through NextMove v1 / PRESENT
ps_ok = pathset(pp("outreach", "SUPPORTED", checks=[check_row("capacity", PRESENT, requirement_id="delivery.capacity")]))
inp, d, txt = build(ps_ok)
check("F3 ACTION (PRESENT): tak ada ketidakpastian yang menahan keputusan navigasi -> berhenti bertanya",
      d["kind"] == KIND_ACTION and d["intent"] == "PRESENT" and d["stop"] is True and d["focus"]["type"] == "navigation")
rd_act = route_for("outreach", [node("access.icp", UNKNOWN, "Tulis ICP satu kalimat")],
                   next_move={"output": "ACTION", "frontier_ref": "n-access.icp", "route_id": "r-outreach", "reason": "x"})
inp, d, txt = build(ps_ok, rd_act, support={"access.icp": SUPPORT_NONE})
check("F3b ACTION (EXECUTE) diteruskan dari NextMove v1 (selector route tidak digandakan)",
      d["kind"] == KIND_ACTION and d["intent"] == "EXECUTE" and d["payload"]["node_id"] == "n-access.icp"
      and d["payload"]["activity"] == "Tulis ICP satu kalimat", str(d))
check("F3c teks ACTION memakai langkah terkurasi bahasa pengguna (presentation registry), bukan teks mesin",
      "Write down who you sell to" in txt["text"] and "Tulis ICP satu kalimat" not in txt["text"], txt["text"])
inp_id, d_id, txt_id = build(ps_ok, rd_act, support={"access.icp": SUPPORT_NONE}, lang="id")
check("F3d bahasa tanpa teks terkurasi (id) jatuh ke aktivitas node apa adanya, tidak dikarang",
      "Tulis ICP satu kalimat" in txt_id["text"] and "Langkah pertama" in txt_id["text"], txt_id["text"])
inp, d, txt = build(pathset(unresolved=[{"code": "NO_SUPPORTED_STRATEGY"}]))
check("F4 HOLD: tak ada path navigable dan tak ada yang bisa ditanyakan -> HOLD + alasan (bukan pertanyaan karangan)",
      d["kind"] == KIND_HOLD and d["reason"]["why"] and d["payload"]["unresolved"] == ["NO_SUPPORTED_STRATEGY"])
check("F5 hanya empat jenis keluaran yang sah", {KIND_QUESTION, KIND_EVIDENCE, KIND_ACTION, KIND_HOLD} == set(KINDS))
check("F5b input versi asing -> HOLD aman, bukan crash/karangan",
      plan_next_move({**inp, "version": 999})["kind"] == KIND_HOLD)

# ───────────────────────────── goal ─────────────────────────────
print("S0 · goal")
goal_ps = pathset(unresolved=[{"code": "GOAL_NOT_ESTABLISHED", "signal": "state:goal_established",
                               "detail": "tujuan belum ada", "i18n": {"en": {"detail": "No goal yet"}}}])
inp, d, txt = build(goal_ps)
check("G0 tujuan belum terbukti -> QUESTION RESOLVE_GOAL (sebelum apa pun)",
      d["kind"] == KIND_QUESTION and d["intent"] == "RESOLVE_GOAL" and "goal" in txt["text"].lower())
inp, d, txt = build(goal_ps, asked={"goal": ASK_CAP})
check("G0b sudah ditanya sampai batas -> berhenti (HOLD), bukan mengulang tanpa akhir",
      d["kind"] == KIND_HOLD)

# ───────────────────────────── G · applicability ─────────────────────────────
print("G · applicability uncertainty")
ps_app = pathset(pp("repricing", "SUPPORTED", checks=[]))
ps_app["paths"][0]["applicability"] = "UNKNOWN"
ps_app["paths"][0]["missing_evidence"] = [{"check_id": "applicability:state:has_clients", "need": ""}]
inp, d, txt = build(ps_app)
check("G1 applicability path UNKNOWN + fakta hilang -> QUESTION RESOLVE_APPLICABILITY (kanonik)",
      d["kind"] == KIND_QUESTION and d["intent"] == "RESOLVE_APPLICABILITY" and d["focus"] == {"type": "path", "id": "path.repricing"}
      and d["payload"]["signal"] == "state:has_clients", str(d))
check("G1b teks menyebut path dan alasan sinyal, bukan id mentah di kalimat", "Repricing" in txt["text"])
inp, d, _ = build(ps_app, signals={"state:has_clients": ACT})
check("G2 fakta applicability yang tak dapat ditanyakan (ACT) tidak ditanyakan", d["intent"] != "RESOLVE_APPLICABILITY")
rd_q = route_for("repricing", [node("commercial.price", UNKNOWN)], applies=False,
                 next_move={"output": "QUESTION", "frontier_ref": "r-repricing", "route_id": "r-repricing", "reason": "x"})
ps_r = pathset(pp("repricing", "SUPPORTED", checks=[]))
inp, d, txt = build(ps_r, rd_q)
check("G3 applicability ROUTE UNDETERMINED diteruskan dari NextMove v1 sebagai RESOLVE_APPLICABILITY (route)",
      d["kind"] == KIND_QUESTION and d["intent"] == "RESOLVE_APPLICABILITY" and d["focus"]["type"] == "route", str(d))
inp, d, _ = build(ps_r, rd_q, asked={"applicability:r-repricing": ASK_CAP})
check("G3b ditanya sampai batas -> lanjut ke PRESENT (cukup untuk memetakan), tidak mengulang",
      d["kind"] == KIND_ACTION and d["intent"] == "PRESENT")

print("G4 · route berlaku yang dapat dieksekusi tidak ditahan pertanyaan applicability route LAIN")
ps_two = pathset(pp("outreach", "SUPPORTED", checks=[]), pp("paid", "SUPPORTED", checks=[]))
rd_two = routes_of(outreach=[node("access.icp", PRESENT, nid="a1"), node("access.prospect_list", UNKNOWN, depends=["a1"], nid="a2")],
                   paid=[node("offering.exists", UNKNOWN, nid="p1")])
rd_two["routes"][0]["path_id"], rd_two["routes"][1]["path_id"] = "path.outreach", "path.paid"
rd_two["routes"][1]["applicability"] = {"status": "UNDETERMINED"}
rd_two["next_move"] = {"output": "QUESTION", "frontier_ref": "r-paid", "route_id": "r-paid", "reason": "x"}
inp, d, txt = build(ps_two, rd_two, support={"access.prospect_list": SUPPORT_NONE, "offering.exists": SUPPORT_NONE})
check("G4a NextMove v1 memilih pertanyaan applicability route 'paid' -> planner tetap ACTION di route yang BERLAKU",
      d["kind"] == KIND_ACTION and d["intent"] == "EXECUTE" and d["payload"]["route_id"] == "r-outreach"
      and d["payload"]["node_id"] == "a2", str(d))
check("G4b jejak mencatat kenapa pertanyaan itu dilewati", any(c["why"] == "APPLICABLE_ROUTE_IS_ACTIONABLE" for c in d["reason"]["considered"]))
rd_only = routes_of(paid=[node("offering.exists", UNKNOWN, nid="p1")])
rd_only["routes"][0]["path_id"] = "path.paid"
rd_only["routes"][0]["applicability"] = {"status": "UNDETERMINED"}
rd_only["next_move"] = {"output": "QUESTION", "frontier_ref": "r-paid", "route_id": "r-paid", "reason": "x"}
inp, d, _ = build(pathset(pp("paid", "SUPPORTED", checks=[])), rd_only, support={"offering.exists": SUPPORT_NONE})
check("G4c tanpa route berlaku yang dapat dieksekusi, pertanyaan applicability TETAP diteruskan",
      d["kind"] == KIND_QUESTION and d["intent"] == "RESOLVE_APPLICABILITY" and d["focus"]["type"] == "route")

# ───────────────────────────── H · contradiction ─────────────────────────────
print("H · contradiction / verification")
ps_c = pathset(pp("outreach", "UNDETERMINED", checks=[check_row("icp", ABSENT, requirement_id="access.icp", kind="hard")]))
inp, d, txt = build(ps_c, ledger=MappingReader({"access.icp": ICP}, support=FORMAL))
check("H1 ledger PRESENT vs check ABSENT = kontradiksi -> EVIDENCE_REQUEST RESOLVE_CONTRADICTION (tidak dipaksa selesai)",
      d["kind"] == KIND_EVIDENCE and d["intent"] == "RESOLVE_CONTRADICTION" and d["focus"]["id"] == "access.icp", str(d))
check("H1b kontradiksi menang atas pertanyaan state lain (S1 sebelum S3)", d["reason"]["stage"] == "CONTRADICTION")
inp, d, _ = build(ps_c, ledger=MappingReader({"access.icp": ICP}, support=FORMAL), asked={"contradiction:access.icp": ASK_CAP})
check("H2 kontradiksi yang sudah diminta buktinya sampai batas dilewati (tercatat), tidak menjebak percakapan",
      d["reason"]["stage"] != "CONTRADICTION")
ps_stop = pathset(pp("hard_path", "CONTRADICTED", checks=[check_row("c", ABSENT, requirement_id="access.icp", kind="hard")]))
inp, d, _ = build(ps_stop, ledger=MappingReader({"access.icp": ICP}, support=FORMAL))
check("H3 kontradiksi di konteks yang tak navigable (path STOP) tak menggerakkan percakapan",
      d["reason"]["stage"] != "CONTRADICTION" and d["kind"] == KIND_HOLD, str(d["reason"]["stage"]))

# ───────────────────────────── K · enough to act ─────────────────────────────
print("K · ready-to-act")
inp, d, txt = build(ps_ok)
check("K1 semua kondisi terjawab -> tidak mengarang pertanyaan (kind ACTION, stop=True)",
      d["kind"] == KIND_ACTION and d["stop"] and not any(c["verdict"] == "SELECTED" for c in d["reason"]["considered"]))
act_only = pathset(pp("outreach", "UNDETERMINED", checks=[check_row("cap", UNKNOWN, requirement_id="commercial.price")]))
inp, d, txt = build(act_only)  # commercial.price without a formal rule & without a readable signal
inp2, d2, _ = build(act_only, signals={"state:cap": ACT})
check("K2 kebutuhan yang tak dapat digeser percakapan (ACT) tidak ditanyakan -> ACTION (diserahkan ke aksi)",
      d2["kind"] == KIND_ACTION and any(c["why"] == "NOT_ASKABLE_ACT" for c in d2["reason"]["considered"]), str(d2["reason"]["considered"]))
check("K2b jejak mencatat yang dilewati beserta alasannya (explainability)",
      d2["reason"]["counts"]["open_act_only"] == 1 and d2["reason"]["counts"]["open_askable"] == 0)

print("counts · kebutuhan = requirement berjangkar + kondisi path tanpa requirement")
ps_cnt = pathset(pp("outreach", "UNDETERMINED", checks=[
    check_row("demand", UNKNOWN),                                   # free condition, askable
    check_row("cap", PRESENT, requirement_id="delivery.capacity"),  # requirement answered
    check_row("cac", UNKNOWN),                                      # free condition, only via measurement
]))
_, d_cnt, _ = build(ps_cnt, signals={"state:cac": ACT})
c_cnt = d_cnt["reason"]["counts"]
check("CN1 hitungan mencakup kondisi path TANPA requirement: resolved=1, open_askable=1, open_act_only=1 (bukan 0/0/0)",
      (c_cnt["resolved"], c_cnt["open_askable"], c_cnt["open_act_only"]) == (1, 1, 1), str(c_cnt))
check("CN2 selama masih ada yang dapat ditanyakan, keputusan bukan ACTION dan hitungan menunjukkannya (anti 'progress' palsu)",
      d_cnt["kind"] == KIND_QUESTION and c_cnt["open_askable"] >= 1)

# ───────────────────────────── L · no relevance ─────────────────────────────
print("L · no-relevance")
ps_l = pathset(pp("a", "UNDETERMINED", checks=[check_row("c1", UNKNOWN, requirement_id="delivery.capacity")]))
inp, d, _ = build(ps_l)
asked_targets = {c["need"] for c in d["reason"]["considered"]}
check("L1 hanya requirement yang dinyatakan konteks yang dipertimbangkan (bukan 49 registry)",
      asked_targets == {"requirement:delivery.capacity"}, str(asked_targets))
ps_na = pathset(pp("paid"))
nb = {"routes": [], "not_born": [{"template_id": "paid_v1", "strategy_id": "paid", "path_id": "path.paid",
                                  "outcome": "NO_ROUTE_NOT_APPLICABLE", "reason": "x"}], "next_move": None}
ars = build_applicable_set(ps_na, nb, template_requirements={"paid_v1": ["conversion.landing_page"]})
inp = assemble_planner_input(lang="en", turn=1, path_set=ps_na, route_data=nb, applicable=ars,
                             views=read_requirement_views(ars, MappingReader({}), ps_na, nb), describe=lambda r: describe(r, "en"))
d = plan_next_move(inp)
check("L2 requirement NOT_APPLICABLE (template tak lahir) tidak pernah ditanyakan",
      all("conversion.landing_page" not in c["need"] for c in d["reason"]["considered"]) and d["kind"] in (KIND_ACTION, KIND_HOLD))

# ───────────────────────────── B · registry extensibility ─────────────────────────────
print("B · registry extensibility")
NEW = "hiring.interview_rubric"
ps_new = pathset(pp("structured", "UNDETERMINED", checks=[check_row("rubric", UNKNOWN, requirement_id=NEW)]))
inp, d, txt = build(ps_new)
check("B1 requirement BARU (tak ada di registry produksi) dipilih planner tanpa perubahan kode",
      d["kind"] == KIND_QUESTION and d["focus"] == {"type": "requirement", "id": NEW}, str(d))
check("B2 teks memakai fallback deterministik registry-style (judul dari id), tak ada kamus requirement di planner",
      "Interview rubric" in txt["text"])
src = Path(__file__).resolve().parents[1].joinpath("core/navigation/planner.py").read_text()
check("B3 kode planner tidak memuat satu pun id requirement (nol literal 'x.y' dotted-id)",
      not [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and "." in n.value and n.value.replace(".", "").replace("_", "").isalpha() and n.value.count(".") == 1
           and n.value.split(".")[0] in {"access", "commercial", "offering", "delivery", "conversion", "retention", "gtm", "experiment"}])

# ───────────────────────────── dependencies (HOW) ─────────────────────────────
print("dependensi · A -> B -> C")
chain = [node("access.icp", UNKNOWN, nid="A"), node("access.prospect_list", UNKNOWN, depends=["A"], nid="B"),
         node("conversion.commitment_obtained", UNKNOWN, depends=["B"], nid="C")]
ps_dep = pathset(pp("outreach", "SUPPORTED", checks=[]))
rd_dep = route_for("outreach", chain)
inp, d, _ = build(ps_dep, rd_dep, support={r: SUPPORT_FORMAL for r in ("access.icp", "access.prospect_list", "conversion.commitment_obtained")})
check("D1 A belum terselesaikan -> planner menanyakan A, bukan B atau C",
      d["focus"]["id"] == "access.icp", str(d["focus"]))
rows = {c["need"]: c for c in d["reason"]["considered"]}
check("D2 B dan C dilewati dengan alasan dependensi yang menyebut pemblokirnya",
      rows["requirement:access.prospect_list"]["why"].startswith("DEPENDENCY_UNRESOLVED:access.icp")
      and rows["requirement:conversion.commitment_obtained"]["why"].startswith("DEPENDENCY_UNRESOLVED:"), str(rows))
chain2 = [node("access.icp", PRESENT, nid="A"), node("access.prospect_list", UNKNOWN, depends=["A"], nid="B"),
          node("conversion.commitment_obtained", UNKNOWN, depends=["B"], nid="C")]
inp, d, _ = build(ps_dep, route_for("outreach", chain2),
                  support={r: SUPPORT_FORMAL for r in ("access.prospect_list", "conversion.commitment_obtained")})
check("D3 A terbukti -> B terbuka dan dipilih; C masih menunggu B", d["focus"]["id"] == "access.prospect_list", str(d["focus"]))
check("D4 Registry = WHAT, dependensi = HOW: dependensi dibaca dari node route, bukan dari registry",
      "depends_on" in json.dumps(inp["routes"]) and "depends_on" not in json.dumps(inp["requirements"]))

# ───────────────────────────── uncertainty-driven, not a fixed order ─────────────────────────────
print("uncertainty-driven · tanpa fase/urutan tetap")
two = pathset(
    pp("p1", "UNDETERMINED", checks=[check_row("soft_c", UNKNOWN, requirement_id="delivery.capacity", kind="prereq")]),
    pp("p2", "UNDETERMINED", checks=[check_row("hard_c", UNKNOWN, requirement_id="commercial.willingness_to_pay", kind="hard"),
                                      check_row("cap2", UNKNOWN, requirement_id="delivery.capacity", kind="prereq")]),
)
inp, d, _ = build(two)
check("U1 kondisi 'hard' (yang dapat membunuh path) ditanya lebih dulu daripada yang 'prereq'",
      d["focus"]["id"] == "commercial.willingness_to_pay", str(d["focus"]))
shuffled = []
rng = random.Random(7)
for _ in range(25):
    ps2 = json.loads(json.dumps(two))
    rng.shuffle(ps2["paths"])
    for p in ps2["paths"]:
        rng.shuffle(p["checks"])
    shuffled.append(build(ps2)[1]["focus"]["id"])
check("U2 urutan path/check di input TIDAK menggeser keputusan (bukan urutan tetap/indeks)", set(shuffled) == {"commercial.willingness_to_pay"}, str(set(shuffled)))
only_cap = pathset(
    pp("p1", "UNDETERMINED", checks=[check_row("a", UNKNOWN, requirement_id="delivery.capacity")]),
    pp("p2", "UNDETERMINED", checks=[check_row("b", UNKNOWN, requirement_id="delivery.capacity"),
                                      check_row("c", UNKNOWN, requirement_id="commercial.price")]),
)
inp, d, _ = build(only_cap)
check("U3 setara kekuatan: yang dibutuhkan konteks TERBANYAK dulu (mengurangi ketidakpastian terbanyak)",
      d["focus"]["id"] == "delivery.capacity" and d["reason"]["contexts"] and len(d["reason"]["contexts"]) == 2, str(d["focus"]))

# ───────────────────────────── loop guard ─────────────────────────────
print("loop guard · tahu kapan berhenti bertanya")
need = "requirement:delivery.capacity"
seq = []
asked: dict[str, int] = {}
for _ in range(5):
    _, dd, _ = build(ps_q, asked=dict(asked))
    seq.append((dd["kind"], dd["intent"]))
    if dd["reason"]["need_id"]:
        asked[dd["reason"]["need_id"]] = asked.get(dd["reason"]["need_id"], 0) + 1
check("LG1 satu kebutuhan: QUESTION -> EVIDENCE_REQUEST -> berhenti (ACTION), maksimal ASK_CAP kali",
      seq[0][0] == KIND_QUESTION and seq[1][0] == KIND_EVIDENCE and seq[2][0] == KIND_ACTION and seq[3][0] == KIND_ACTION
      and asked.get(need) == ASK_CAP, str(seq))

# ───────────────────────────── J · direction switch ─────────────────────────────
print("J · direction switch")
before = pathset(pp("outreach", "UNDETERMINED", checks=[check_row("cap", UNKNOWN, requirement_id="delivery.capacity")]))
after = pathset(
    pp("outreach", "UNDETERMINED", checks=[check_row("cap", UNKNOWN, requirement_id="delivery.capacity")]),
    pp("offer_shaping", "UNDETERMINED", checks=[check_row("fit", UNKNOWN, requirement_id="offering.differentiation", kind="hard")]),
)
_, d1, _ = build(before)
_, d2, _ = build(after, support={"offering.differentiation": SUPPORT_FORMAL})
check("J1 evidence baru melahirkan arah baru -> fokus planner bergeser (tanpa restart sesi)",
      d1["focus"]["id"] == "delivery.capacity" and d2["focus"]["id"] == "offering.differentiation", f"{d1['focus']} -> {d2['focus']}")
gone = pathset(pp("outreach", "CONTRADICTED", checks=[check_row("cap", ABSENT, requirement_id="delivery.capacity", kind="hard")]))
_, d3, _ = build(gone)
check("J2 arah awal tergugurkan (STOP) -> planner tidak lagi menggalinya", d3["kind"] in (KIND_HOLD, KIND_ACTION) and d3["focus"]["id"] != "delivery.capacity")

# ───────────────────────────── 0..N paths, route optional ─────────────────────────────
print("0..N path · route opsional")
for n in (0, 1, 3, 8, 13):
    paths = [pp(f"s{i}", "SUPPORTED", checks=[check_row(f"c{i}", PRESENT, requirement_id=f"access.req{i}")]) for i in range(n)]
    ps = pathset(*paths, unresolved=[] if n else [{"code": "NO_SUPPORTED_STRATEGY"}])
    _, dn, _ = build(ps)
    ok = dn["kind"] == (KIND_ACTION if n else KIND_HOLD) and dn["reason"]["counts"]["navigable_paths"] == n
    if not ok:
        check(f"N0 kardinalitas {n}", False, str(dn))
        break
else:
    check("N1 kardinalitas path 0/1/3/8/13 ditangani (tak ada angka tetap; nol path -> HOLD beralasan)", True)
_, dn, _ = build(ps_q, None)
check("N2 path TANPA route tetap dapat dinavigasi (QUESTION atas check path)", dn["kind"] == KIND_QUESTION and not dn["reason"]["contexts"][0].get("kind") == "route")
cand = pp("improve_activation", "UNDETERMINED", checks=[check_row("aha", UNKNOWN, requirement_id="retention.aha_moment_defined")])
cand["provenance"]["candidate"] = {"candidate_id": "cand.improve_activation", "origin": "MECHANISM_PATTERN"}
plain = json.loads(json.dumps(cand))
plain["provenance"].pop("candidate")
a_inp, a_dec, _ = build(pathset(cand))
b_inp, b_dec, _ = build(pathset(plain))
check("N3 path asal-kandidat dinavigasi PERSIS sama dengan path strategi terdeklarasi (tak ada jalan khusus)",
      a_dec == b_dec and a_inp == b_inp)

# ───────────────────────────── emergence ─────────────────────────────
print("emergence · tak ada path navigable")
em_ps = pathset(unresolved=[{
    "code": "INSUFFICIENT_VERIFIED_STATE", "missing": ["state:existing_revenue", "mechanism:x"],
    "missing_detail": [
        {"signal": "state:existing_revenue", "reason": "pendapatan belum terukur", "i18n": {"en": {"reason": "Your current income is not measured yet"}}},
        {"signal": "mechanism:x", "reason": "x", "i18n": {}},
    ]}])
inp, d, txt = build(em_ps)
check("E1 nol path + fakta keadaan hilang -> tanyakan FAKTA itu (bukan menebak path); mekanisme/rule tak ditanyakan",
      d["kind"] == KIND_QUESTION and d["focus"] == {"type": "signal", "id": "state:existing_revenue"}
      and "Your current income is not measured yet" in txt["text"], str(d["focus"]) + txt["text"])
inp, d, _ = build(em_ps, signals={"state:existing_revenue": ACT})
check("E2 fakta yang hanya dapat diukur lewat aksi (ACT) tidak ditanyakan -> HOLD", d["kind"] == KIND_HOLD)
inp, d, _ = build(pathset(pp("ok", "SUPPORTED", checks=[]), unresolved=[]))
check("E3 emergence tidak mengganggu bila sudah ada path navigable", d["reason"]["stage"] != "EMERGENCE")

# ───────────────────────────── language ─────────────────────────────
print("bahasa")
_, d_en, t_en = build(ps_q, lang="en")
_, d_id, t_id = build(ps_q, lang="id")
check("T1 bahasa hanya mengubah KATA-KATA, tidak keputusan (en == id untuk keputusan inti)",
      d_en["kind"] == d_id["kind"] and d_en["focus"] == d_id["focus"] and d_en["intent"] == d_id["intent"]
      and t_en["text"] != t_id["text"] and "Saya belum bisa menilai" in t_id["text"])

_dec_state = {"intent": "RESOLVE_STATE", "focus": {"type": "requirement", "id": "x.y"}, "payload": {}}
_dec_evid = {"intent": "COLLECT_EVIDENCE", "focus": {"type": "requirement", "id": "x.y"}, "payload": {}}
_nopunct = {"requirement:x.y": {"title": {"text": "Thing"}, "how": {"text": "Show a signed invoice"}}}
_punct = {"requirement:x.y": {"title": {"text": "Thing"}, "how": {"text": "Show a signed invoice."}}}
_t_np = render_move(_dec_state, {"lang": "en", "texts": _nopunct}, "en")["text"]
_t_p = render_move(_dec_state, {"lang": "en", "texts": _punct}, "en")["text"]
_t_id = render_move(_dec_state, {"lang": "id", "texts": _nopunct}, "id")["text"]
_t_ev = render_move(_dec_evid, {"lang": "en", "texts": _nopunct}, "en")["text"]
check("T1 cara memverifikasi dari teks fallback (tanpa tanda baca) dirender sebagai kalimat sendiri, tidak menempel pada "
      "kalimat berikutnya; teks yang sudah berakhiran titik tidak digandakan",
      "invoice. Real examples" in _t_np and "invoice. Real examples" in _t_p and ".." not in _t_p
      and "invoice. Contoh nyata" in _t_id and _t_ev.endswith("invoice."))

_act = {"kind": "ACTION", "intent": "EXECUTE", "focus": {"type": "node", "id": "n1"},
        "payload": {"activity": "List real people by name"}}
_pres = {"kind": "ACTION", "intent": "PRESENT", "focus": {"type": "navigation", "id": "paths"}, "payload": {}}
_hold = {"kind": "HOLD", "intent": "WAIT", "focus": {"type": "navigation", "id": "none"}, "payload": {}}
_ques = {"kind": "QUESTION", "intent": "RESOLVE_STATE", "focus": {"type": "requirement", "id": "x.y"}, "payload": {}}
_i_en, _i_id = {"lang": "en", "texts": {}}, {"lang": "id", "texts": {}}
_first = render_move(_act, _i_en, "en")["text"]
_again = render_move(_act, _i_en, "en", previous=_act)["text"]
_other = render_move(_act, _i_en, "en", previous={**_act, "focus": {"type": "node", "id": "n2"}})["text"]
_after_q = render_move(_act, _i_en, "en", previous=_ques)["text"]
check("T2 langkah ACTION yang SAMA persis dengan yang baru disajikan dibunyikan 'tidak berubah' (bukan kalimat identik); "
      "yang berbeda (fokus lain / sebelumnya pertanyaan / tanpa pendahulu) tetap kalimat biasa; keputusan tak berubah",
      _first.startswith("You have enough to act on.") and _again.startswith("Noted. Your next step has not changed:")
      and "List real people by name" in _again and _other == _first == _after_q
      and render_move(_act, _i_id, "id", previous=_act)["text"].startswith("Dicatat. Langkah berikutnya tidak berubah:"))
check("T2b PRESENT dan HOLD yang berulang juga dibunyikan 'tidak berubah' (en + id); QUESTION/EVIDENCE_REQUEST TIDAK PERNAH "
      "dianggap pengulangan (menanyakan lagi = keputusan planner, `ASK_CAP`)",
      render_move(_pres, _i_en, "en", previous=_pres)["text"].startswith("Noted. I can already map")
      and render_move(_hold, _i_en, "en", previous=_hold)["text"].startswith("Still nothing I can point to")
      and render_move(_hold, _i_id, "id", previous=_hold)["text"].startswith("Masih belum ada langkah")
      and render_move(_ques, _i_en, "en", previous=_ques)["text"] == render_move(_ques, _i_en, "en")["text"])

# ───────────────────────────── reason trail + replay ─────────────────────────────
print("reason trail + replay")
inp, d, _ = build(ps_dep, route_for("outreach", chain), support={r: SUPPORT_FORMAL for r in ("access.icp", "access.prospect_list", "conversion.commitment_obtained")})
r = d["reason"]
check("R1 reason trail lengkap: stage, need_id, why[], contexts[], considered[], counts, input_digest",
      all(k in r for k in ("stage", "need_id", "why", "contexts", "considered", "counts", "input_digest"))
      and "applicability=APPLIES" in r["why"] and "satisfaction=UNKNOWN" in r["why"] and "dependency_ready=true" in r["why"]
      and "blocks_next_decision=true" in r["why"])
check("R2 keputusan dan input JSON-serializable penuh (replay dari penyimpanan)", bool(json.dumps(d)) and bool(json.dumps(inp)))
loaded = json.loads(json.dumps({"input": inp, "decision": d}))
check("R3 REPLAY: input tersimpan -> keputusan identik (ok=True)", replay(loaded)["ok"] is True)
tampered = json.loads(json.dumps(loaded))
tampered["decision"]["kind"] = KIND_HOLD
check("R4 replay MENDETEKSI keputusan yang tidak sesuai input (ok=False)", replay(tampered)["ok"] is False)
check("R5 digest input stabil dan peka: input berbeda -> sidik jari berbeda",
      digest(inp) == digest(json.loads(json.dumps(inp))) and digest(inp) != digest({**inp, "turn": 99}))
check("R6 determinisme: 20 kali hitung ulang -> keputusan identik", len({json.dumps(plan_next_move(inp), sort_keys=True) for _ in range(20)}) == 1)
core_inp = {k: v for k, v in inp.items() if k not in NON_DECISION_KEYS}
check("R7 kata-kata tampilan dan salinan inspeksi BUKAN dasar keputusan: tanpa `texts`/`applicable` keputusan identik "
      "(termasuk digest) — dasar yang membuat log aman dipadatkan",
      set(NON_DECISION_KEYS) == {"texts", "applicable"} and plan_next_move(core_inp) == d and digest(core_inp) == digest(inp)
      and digest({**inp, "texts": {}}) == digest(inp))
check("R8 REPLAY tetap benar dari input yang tak memuat texts/applicable (bentuk yang disimpan log)",
      replay({"input": core_inp, "decision": d})["ok"] is True)
check("R9 digest tetap PEKA pada input keputusan (requirements/paths/history), bukan hanya `turn`",
      digest(inp) != digest({**inp, "requirements": {}}) and digest(inp) != digest({**inp, "paths": []})
      and digest(inp) != digest({**inp, "history": {"asked": {"x": 1}, "turn": inp["history"]["turn"]}}))
check("R10 entri yang inputnya sudah dipadatkan TIDAK dilaporkan lolos: ok=None, reason=COMPACTED, keputusan terbawa",
      replay({"decision": d}) == {"ok": None, "reason": "COMPACTED", "expected": d, "actual": None})

# ───────────────────────────── no ranking / no LLM / no phases ─────────────────────────────
print("invarian struktural")
mods = ["planner.py", "planner_input.py", "planner_text.py"]
src_all = {m: Path(__file__).resolve().parents[1].joinpath("core/navigation", m).read_text() for m in mods}
imports = {n.module for m in mods for n in ast.walk(ast.parse(src_all[m])) if isinstance(n, ast.ImportFrom) and n.module}
imports |= {a.name for m in mods for n in ast.walk(ast.parse(src_all[m])) if isinstance(n, ast.Import) for a in n.names}
check("V1 planner tak mengimpor LLM/provider/store/jaringan/agents (murni, deterministik)",
      not any(x.split(".")[0] in {"providers", "store", "agents", "app", "openai", "httpx", "requests", "llm", "random", "time", "datetime"} for x in imports), str(sorted(imports)))
code_words = " ".join(src_all.values()).lower()
check("V2 tak ada kosakata peringkat bisnis sebagai kesimpulan (best/top/winner/rank-path)",
      not any(w in code_words.replace("information priority", "") for w in (" winner", "best path", "best requirement", "top path", "best strategy")))
check("V3 tak ada indeks fase / urutan tetap sebagai otoritas di modul planner",
      not any(w in code_words for w in ("phase_index", "phases[", "advance_to_next", "turns_in_phase", "max_turns_per_phase")))


# ── V6: Readiness != planner — no M4 core module imports Readiness (both read the same state)
def _imports_of(src: str) -> set[str]:
    out: set[str] = set()
    for n_ in ast.walk(ast.parse(src)):
        if isinstance(n_, ast.ImportFrom):
            out |= {n_.module or ""} | {f"{n_.module}.{a.name}" for a in n_.names}
        elif isinstance(n_, ast.Import):
            out |= {a.name for a in n_.names}
    return out


def _imports_readiness(src: str) -> bool:
    return any(x.startswith("core.navigation.readiness") for x in _imports_of(src))


_core_dir = Path(__file__).resolve().parents[1] / "core/navigation"
_core_m4 = ["planner.py", "planner_input.py", "planner_text.py", "applicability.py", "requirement_state.py"]
_offenders = [m for m in _core_m4 if _imports_readiness((_core_dir / m).read_text(encoding="utf-8"))]
check("V6 Readiness != planner: modul inti M4 (planner, perakit input, teks, applicability, reader) tak mengimpor Readiness",
      not _offenders, str(_offenders))
check("V6b kontrol positif: impor Readiness terdeteksi bila ada (dua bentuk impor)",
      _imports_readiness("from core.navigation.readiness import build_projection")
      and _imports_readiness("import core.navigation.readiness as r") and not _imports_readiness("import json"))

# ── V4: no hidden requirement list: registry ids are never written as literals in M4 modules
from engine.requirements import load_registry  # noqa: E402

_REG_IDS = set(load_registry())
_M4_MODULES = [
    "core/navigation/applicability.py", "core/navigation/requirement_state.py", "core/navigation/planner.py",
    "core/navigation/planner_input.py", "core/navigation/planner_text.py", "app/turn.py", "app/navigation.py",
    "store/requirement_state.py", "domains/revenue/navigation/live.py", "ontology/mapper/live_adjudication.py",
]


def _registry_literals(src: str) -> list[str]:
    return sorted({n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant)
                   and isinstance(n.value, str) and n.value in _REG_IDS})


_ROOT = Path(__file__).resolve().parents[1]
_found = {m: _registry_literals((_ROOT / m).read_text(encoding="utf-8")) for m in _M4_MODULES}
check("V4 tak ada daftar requirement tersembunyi: tak satu pun id registry (49) ditulis sebagai literal di modul M4 "
      "(planner, applicability, reader, perakit, live, adjudikasi live)",
      len(_REG_IDS) >= 40 and not any(_found.values()), str({m: v for m, v in _found.items() if v}))
check("V4b kontrol positif: potongan yang MENULIS id registry sebagai literal terdeteksi (guard tak vacuous)",
      _registry_literals(f"OUTREACH_REQUIREMENTS = [{sorted(_REG_IDS)[0]!r}]\n") == [sorted(_REG_IDS)[0]])

print()
bad = [n for n, ok, _ in RESULTS if not ok]
print(f"HASIL: {len(RESULTS) - len(bad)}/{len(RESULTS)} PASS {'✅' if not bad else '❌ ' + str(bad)}")
sys.exit(0 if not bad else 1)
