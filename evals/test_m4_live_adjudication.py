"""M4 — LIVE adjudication: evidence -> mapper (proposal) -> verification -> adjudication -> ledger -> reader -> route.

internal-docs §25. Proves that the chain that used to live only in tests is now
really wired end-to-end, and that wiring it does NOT loosen a single semantic contract:

  D   mapper = proposal only; status comes ONLY from adjudication (the ledger is untouched by proposals)
  C   UNKNOWN != ABSENT: unmentioned / no formal rule / unit unidentified => still UNKNOWN by absence
  E   end-to-end chain: evidence -> ledger -> Requirement State Reader -> route StatusReader -> route node
  35  user scoping: A's requirement status is never readable for B (both ways), invalid id rejected
      (fail-closed)
      idempotency: ledger = a history of CHANGES, not a per-turn log
      gap: is_gap evidence (missing data) is never admitted (is_gap != NEGATIVE)
      single write gate: only `adjudicate_and_persist` (AST)

Ledger and lineage are redirected to a temp directory; no LLM, no network.
Run: .venv/bin/python evals/test_m4_live_adjudication.py
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

import store.adjudication_ledger as ledger  # noqa: E402
import store.route_lineages as rl  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="m4_live_adj_"))
ledger._LEDGER_ROOT = _TMP / "ledger"
rl._BASE = _TMP / "lineages"

from core.navigation.requirement_state import (  # noqa: E402
    SUPPORT_FORMAL,
    SUPPORT_SECOND_PASS,
    SUPPORT_UNIT,
)
from core.schema.evidence import EvidenceItem  # noqa: E402
from engine.requirements import load_registry  # noqa: E402
from ontology.mapper import contract  # noqa: E402
from ontology.mapper.live_adjudication import (  # noqa: E402
    adjudication_support,
    formal_envelope,
    reason_code,
    run_live_adjudication,
    support_of,
)
from ontology.route.session_bridge import run_session_route, user_status_reader  # noqa: E402
from store.requirement_state import LedgerRequirementReader, user_requirement_reader  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


def ev(i: str, text: str, *, gap: bool = False, level: str = "self_reported") -> EvidenceItem:
    return EvidenceItem(id=i, signal=text, source_quote=text, level=level, phase="REVENUE_STATE", is_gap=gap)


def ledger_lines(user: str) -> list[dict]:
    f = ledger._LEDGER_ROOT / user / "adjudication_ledger.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def reader(user: str) -> LedgerRequirementReader:
    return LedgerRequirementReader(user, support_of=support_of())


# sentences that satisfy/contradict reviewed formal predicates (repo artifacts;
# locked by test_calibration_fase5a)
ICP_OK = "ICP tertulis berisi jenis usaha, level, dan peran pembeli."
ICP_NO = "Kami hubungi siapa saja."
DIFF_OK = "Pembeda kami di dimensi yang dipedulikan customer: waktu pengiriman 2 hari."
DIFF_NO = "Kualitas kami bagus."
OFFER_OK = "Jasa kami konkret dengan deliverable berupa laporan mingguan."
OFFER_NO = "Penawaran kami masih berupa ide."
PROSPECT_PARTIAL = "Satu entri memuat nama nyata dan asal yang jelas; entri lain tidak memuatnya sama sekali."

# ───────────────────────────── coverage: what CAN be adjudicated ─────────────────────────────
print("cakupan formal (jujur: parsial)")
env = formal_envelope()
registry = set(load_registry())
check("K1 hanya sebagian kecil registry punya predikat formal (5 dari 49) — bukan seluruhnya",
      0 < len(env["rules"]) < len(registry) // 4, f"{len(env['rules'])}/{len(registry)}")
check("K2 dukungan: FORMAL utk formal biasa, UNIT utk unit-berlipak, SECOND_PASS utk prose registry (Gate A conditional)",
      adjudication_support("access.icp", env) == SUPPORT_FORMAL
      and adjudication_support("access.prospect_list", env) == SUPPORT_UNIT
      and adjudication_support("commercial.price", env) == SUPPORT_SECOND_PASS)

# ───────────────────────────── D · mapper = proposal only ─────────────────────────────
print("D · mapper hanya proposal")
U = "u-live-1"
facts = [ev("e1", ICP_OK), ev("e2", OFFER_OK)]
index = {e.id: e for e in facts}
proposals = contract.propose_deterministic(index, list(load_registry().values()))
check("D1 mapper menghasilkan proposal (bentuk 4-field persis), TANPA status/polarity",
      proposals and all(set(p) == {"proposed_by", "requirement_id", "evidence_refs", "proposed_at"} for p in proposals))
check("D2 proposal saja tidak menyentuh ledger (belum ada adjudikasi apa pun)",
      ledger.latest_entry(U, "access.icp") is None and not ledger_lines(U))
run1 = run_live_adjudication(U, facts, now=1_700_000_000)
check("D3 SETELAH verifikasi + adjudikasi barulah ledger terisi (status dari aturan, bukan dari mapper)",
      {a["requirement_id"]: a["status"] for a in run1["adjudicated"]} == {"access.icp": "PRESENT", "offering.exists": "PRESENT"},
      str(run1["adjudicated"]))
check("D4 jumlah proposal > jumlah verified: kebanyakan proposal TIDAK diadmit (verifikasi memutuskan)",
      run1["proposed"] > run1["verified"] > 0, f"{run1['proposed']} vs {run1['verified']}")
check("D5 yang tak lolos verifikasi tercatat dengan KODE alasan stabil, bukan dibuang diam-diam",
      run1["unresolved"].get("NO_FORMAL_RULE", 0) > 0 and run1["malformed"] == 0, str(run1["unresolved"]))
check("D6 reason_code memetakan teks verifikator ke kode stabil; teks asing = OTHER (tidak dikarang)",
      reason_code("rule registry masih PROSA") == "NO_FORMAL_RULE"
      and reason_code("requirement unit-berlipak TANPA unit_context") == "UNIT_CONTEXT_REQUIRED"
      and reason_code("evidence tak memenuhi cabang rule mana pun") == "EVIDENCE_NOT_MEETING_RULE"
      and reason_code("apa pun yang lain") == "OTHER")
st = reader(U).read("access.icp")
check("D7 reader membaca keadaan lengkap: PRESENT + sitasi + waktu + asal + dukungan",
      st.satisfaction == "PRESENT" and st.adjudicated and st.evidence_refs == ("e1",)
      and st.last_updated == 1_700_000_000 and st.verification["method"] == "deterministic_adjudicator"
      and st.verification["rule_evaluation"]["sufficient"] is True and st.support == SUPPORT_FORMAL, str(st))

# single write gate: producer modules must not use private write primitives
src = (Path(__file__).resolve().parents[1] / "ontology/mapper/live_adjudication.py").read_text(encoding="utf-8")
names = {n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute)} | \
        {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
check("D8 produsen live hanya menulis lewat adjudicate_and_persist (nol primitif tulis privat)",
      "adjudicate_and_persist" in names and not ({"_record_adjudication", "_record_anomaly", "_append"} & names))

# ───────────────────────────── C · UNKNOWN != ABSENT ─────────────────────────────
print("C · UNKNOWN != ABSENT")
U2 = "u-live-2"
unrelated = [ev("x1", "Hari ini hujan deras di Bandung."), ev("x2", "Saya suka mendaki gunung akhir pekan.")]
r2 = run_live_adjudication(U2, unrelated, now=1)
check("C1 tak disebut = tak ada entri ledger (BUKAN entri ABSENT, BUKAN entri UNKNOWN)",
      r2["adjudicated"] == [] and not ledger_lines(U2))
rd2 = reader(U2).read("access.icp")
check("C2 reader: UNKNOWN by absence — adjudicated=False, tanpa sitasi/waktu/asal",
      rd2.satisfaction == "UNKNOWN" and not rd2.adjudicated and rd2.evidence_refs == ()
      and rd2.last_updated is None and rd2.verification is None)
only_other = run_live_adjudication("u-live-2b", [ev("o1", ICP_OK)], now=1)
check("C3 menyebut SATU requirement tak menurunkan yang lain: requirement lain tak disebut tetap tanpa entri",
      [a["requirement_id"] for a in only_other["adjudicated"]] == ["access.icp"]
      and reader("u-live-2b").read("offering.exists").adjudicated is False
      and reader("u-live-2b").read("offering.differentiation").adjudicated is False)
price = [ev("p1", "Harga jasa saya Rp3 juta per bulan dan klien setuju membayarnya.")]
r3 = run_live_adjudication("u-live-2c", price, now=1)
check("C4 requirement prose (commercial.price) TANPA llm tak diadjudikasi; jalur SECOND_PASS tercatat, status by-absence",
      r3["adjudicated"] == [] and reader("u-live-2c").read("commercial.price").adjudicated is False
      and reader("u-live-2c").read("commercial.price").support == SUPPORT_SECOND_PASS)
unit = [ev("pl1", PROSPECT_PARTIAL)]
r4 = run_live_adjudication("u-live-2d", unit, now=1)
check("C5 requirement unit-berlipak: identitas unit tak ditebak -> tak diadjudikasi, UNKNOWN by absence",
      r4["adjudicated"] == [] and not reader("u-live-2d").read("access.prospect_list").adjudicated
      and reader("u-live-2d").read("access.prospect_list").support == SUPPORT_UNIT
      and r4["unresolved"].get("UNIT_CONTEXT_REQUIRED", 0) >= 1, str(r4["unresolved"]))
check("C6 sebuah evidence yang MEMBANTAH menghasilkan ABSENT hanya karena cabang contradicting terpenuhi (bukan ketiadaan)",
      {a["requirement_id"]: a["status"] for a in run_live_adjudication("u-live-2e", [ev("n1", ICP_NO)], now=1)["adjudicated"]}
      == {"access.icp": "ABSENT"})
rows = ledger_lines("u-live-2e")
check("C7 entri ABSENT menyitasi evidence yang membantah (auditabel)",
      rows and rows[-1]["adjudication"]["evidence_refs"] == ["n1"])
conf = run_live_adjudication("u-live-2f", [ev("c1", DIFF_OK), ev("c2", DIFF_NO)], now=1)
cst = reader("u-live-2f").read("offering.differentiation")
check("C8 dukungan DAN bantahan = UNKNOWN + konflik dua sisi tercatat (tidak dipilih diam-diam)",
      cst.satisfaction == "UNKNOWN" and cst.adjudicated and cst.conflict
      and cst.verification["conflict"] == {"present_evidence_refs": ["c1"], "contradicting_evidence_refs": ["c2"]},
      str(cst.to_dict()))

# ───────────────────────────── gap ─────────────────────────────
print("gap · data hilang bukan fakta")
g = run_live_adjudication("u-live-gap", [ev("g1", ICP_NO, gap=True), ev("g2", ICP_OK, gap=True)], now=1)
check("G1 evidence is_gap tak pernah diadmit: tak ada ABSENT/PRESENT dari kalimat gap (is_gap != NEGATIVE)",
      g["adjudicated"] == [] and g["gaps_excluded"] == 2 and not ledger_lines("u-live-gap"))
g2 = run_live_adjudication("u-live-gap2", [ev("g1", ICP_NO, gap=True), ev("f1", ICP_OK)], now=1)
check("G2 campuran gap + fakta: hanya fakta yang menentukan (PRESENT, sitasi tanpa g1)",
      [(a["requirement_id"], a["status"], a["evidence_refs"]) for a in g2["adjudicated"]]
      == [("access.icp", "PRESENT", ["f1"])])

# ───────────────────────────── idempotensi ─────────────────────────────
print("idempotensi · ledger = riwayat perubahan")
U3 = "u-live-3"
a = run_live_adjudication(U3, [ev("e1", ICP_OK)], now=100)
n1 = len(ledger_lines(U3))
b = run_live_adjudication(U3, [ev("e1", ICP_OK)], now=200)
check("I1 hasil sama -> tidak menulis ulang (written=False, jumlah baris tetap)",
      a["adjudicated"][0]["written"] is True and b["adjudicated"][0]["written"] is False and len(ledger_lines(U3)) == n1)
check("I2 last_updated TIDAK maju bila keadaan tak berubah (bermakna: kapan terakhir berubah)",
      reader(U3).read("access.icp").last_updated == 100)
c = run_live_adjudication(U3, [ev("e1", ICP_OK), ev("e2", ICP_NO)], now=300)
st3 = reader(U3).read("access.icp")
check("I3 evidence baru yang mengubah hasil -> entri baru (riwayat tumbuh); entri terakhir menang",
      c["adjudicated"][0]["written"] is True and len(ledger_lines(U3)) == n1 + 1
      and st3.satisfaction == "UNKNOWN" and st3.conflict and st3.last_updated == 300)

# ───────────────────────────── 35 · scoping user ─────────────────────────────
print("35 · scoping user")
A, B = "u-scope-A", "u-scope-B"
run_live_adjudication(A, [ev("a1", ICP_OK)], now=1)
check("S1 status milik A tak terbaca untuk B (UNKNOWN by absence)",
      reader(A).read("access.icp").satisfaction == "PRESENT" and reader(B).read("access.icp").adjudicated is False)
run_live_adjudication(B, [ev("b1", ICP_NO)], now=2)
check("S2 B menulis ABSENT; A tetap PRESENT (dua arah terisolasi)",
      reader(B).read("access.icp").satisfaction == "ABSENT" and reader(A).read("access.icp").satisfaction == "PRESENT")
check("S3 ledger terpisah per direktori user", (ledger._LEDGER_ROOT / A).is_dir() and (ledger._LEDGER_ROOT / B).is_dir()
      and ledger_lines(A) != ledger_lines(B))
bad_ok = True
for bad in ("../x", "a/b", "", "u u"):
    try:
        run_live_adjudication(bad, [ev("z1", ICP_OK)], now=1)
        bad_ok = False
    except ValueError:
        pass
check("S4 user_id tak sah ditolak (fail-closed): tidak jatuh ke berkas bersama", bad_ok
      and not (ledger._LEDGER_ROOT / "adjudication_ledger.jsonl").exists())
check("S5 sesi tanpa user: pembaca jujur (UNKNOWN by absence, NO_USER_SCOPE) — bukan ledger bersama",
      user_requirement_reader("").read("access.icp").adjudicated is False
      and user_requirement_reader(None).read("access.icp").support == "NO_USER_SCOPE")

# ───────────────────── E · end-to-end chain to Route ─────────────────────
print("E · ledger -> reader -> Route")
U4 = "u-live-e2e"
evs = [ev("e1", ICP_OK)]
run_live_adjudication(U4, evs, now=1)
status = user_status_reader(U4)
check("E1 StatusReader route membaca ledger lewat Requirement State Reader (PRESENT; tak disebut = None)",
      status("access.icp") == "PRESENT" and status("commercial.price") is None)
tpl = json.loads((Path(__file__).resolve().parents[1] / "ontology/route/templates/direct_outreach_v1.json").read_text())
sess = SimpleNamespace(user_id=U4, evidence=evs)
route = run_session_route(sess, tpl)
nodes = {n["resolves"][0]: n for n in route["lineage"]["revisions"][-1]["nodes"]}
check("E2 node route access.icp = PRESENT dari adjudikasi live; node lain UNKNOWN (tak dikarang)",
      nodes["access.icp"]["satisfaction"]["status"] == "PRESENT"
      and nodes["access.prospect_list"]["satisfaction"]["status"] == "UNKNOWN")
check("E3 dependensi terbuka karena state terbukti: prospek (bergantung ICP) executable TRUE; tanpa ICP = UNKNOWN",
      nodes["access.prospect_list"]["executability"] == "TRUE")
route_b = run_session_route(SimpleNamespace(user_id="u-live-e2e-b", evidence=evs), tpl)
nb = {n["resolves"][0]: n for n in route_b["lineage"]["revisions"][-1]["nodes"]}
check("E4 user lain dengan evidence yang sama TAPI tanpa adjudikasi: node tetap UNKNOWN (tak ada bocoran lintas-user)",
      nb["access.icp"]["satisfaction"]["status"] == "UNKNOWN" and nb["access.prospect_list"]["executability"] == "UNKNOWN")

# ───────────────────────────── gate-2: stale rules honestly rejected ─────────────────────────────
print("gate · formal rules basi")
stale = dict(env)
stale["fingerprint"] = "0" * 64
rs = run_live_adjudication("u-live-stale", [ev("s1", ICP_OK)], now=1, envelope=stale)
check("T1 envelope basi (fingerprint tak cocok registry) -> tak ada adjudikasi; alasan STALE tercatat; tak crash",
      rs["adjudicated"] == [] and rs["unresolved"].get("STALE_FORMAL_RULES", 0) > 0 and not ledger_lines("u-live-stale"),
      str(rs["unresolved"]))
check("T2 ringkasan audit JSON-serializable", bool(json.dumps(run1)))

print()
bad = [n for n, ok, _ in RESULTS if not ok]
print(f"HASIL: {len(RESULTS) - len(bad)}/{len(RESULTS)} PASS {'✅' if not bad else '❌ ' + str(bad)}")
sys.exit(0 if not bad else 1)
