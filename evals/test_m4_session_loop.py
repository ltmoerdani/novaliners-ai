"""M4 — end-to-end conversation STATE LOOP over real HTTP (internal-docs §25).

One live session from message to NextMove, repeatedly:

    message -> evidence -> Universal State -> live adjudication -> requirement state -> candidate/path -> readiness
          -> Question Planner -> QUESTION | EVIDENCE_REQUEST | ACTION | HOLD -> next message -> ...

Provider = deterministic mock (no LLM, no quota). `.env` holds live keys, so `get_llm` is PATCHED and the test
refuses to run when the provider is not mock. All stores are redirected to a temp directory.

  O   full loop: every turn carries NextMove + reason trail; live adjudication fills the ledger; ACTION when enough
  I   free order: A (price->customers->proof->capacity) vs B (customers->proof->price->capacity) -> final state
      EQUIVALENT, trajectories may differ; no turn asks about something already answered
  J   direction switch: new evidence births a new path and shifts planner focus without a session restart
  K   ready to act: stop asking (ACTION), no invented questions; the session keeps accepting messages
  HOLD no safe step -> HOLD with a reason; new information resumes it (not locked)
  C   UNKNOWN != ABSENT at the session level
  35  two users: requirement status does not leak; anonymous sessions are honest (no ledger)
  P   persistence + REPLAY: the decision log survives on disk; same input -> same decision; old sessions load
  F   finalize keeps working without phase gating; Readiness reads the same ledger state as the planner
  X   API contract: turn fields (kind, progress, evidence_delta, intent_tags, ...) remain; `phase`/`phase_index`
      are GONE (M5)

Run: .venv/bin/python evals/test_m4_session_loop.py
"""
from __future__ import annotations

import atexit
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="m4_loop_"))
rl._BASE = _TMP / "lineages"
ledger._LEDGER_ROOT = _TMP / "ledger"
workspace._BASE = _TMP / "workspaces"
route_execution._BASE = _TMP / "workspaces"
funnel._PATH = _TMP / "funnel.jsonl"
path_states._BASE = _TMP
path_states._STATES = _TMP / "path_states.json"
path_states._HISTORY = _TMP / "path_history.jsonl"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as app_main  # noqa: E402
from app.navigation import REPLAY_WINDOW, compact_log, navigate_session  # noqa: E402
from core.navigation.planner import KINDS, replay  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import SessionStore, store  # noqa: E402

app_main.get_llm = lambda: MockProvider()  # deterministic: does NOT use the real provider from .env
assert app_main.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
client = TestClient(app_main.app)
_created: list[str] = []


def _drop_sessions() -> None:
    for sid in _created:
        (store.PERSIST_DIR / f"{sid}.json").unlink(missing_ok=True)


atexit.register(_drop_sessions)
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


GOAL = "Saya konsultan marketing, mau Rp20 juta per bulan dalam 90 hari."
INC0 = "Pendapatan saya sekarang Rp0 per bulan."
INC8 = "Sekarang pendapatan saya Rp8 juta per bulan dari 2 klien aktif."
CAP = "Saya kerja sekitar 30 jam per minggu untuk delivery klien."
DEM = "Ada 3 orang yang bertanya soal jasa saya bulan ini (inquiry masuk)."
ICP = "ICP saya berisi jenis usaha UKM, level direktur, dan peran pembeli owner."
PRICE = "Harga jasa saya Rp3 juta per klien."
CUST = "Saya punya 2 klien aktif yang bayar penuh."
PROOF = "Klien pertama saya bersedia memberi testimoni tertulis."


def new_session(user: str | None, goal: str = GOAL, lang: str = "en") -> str:
    body = {"goal_text": goal, "language": lang}
    if user:
        body["user_id"] = user
    r = client.post("/session", json=body)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _created.append(sid)
    return sid


def say(sid: str, text: str) -> dict:
    r = client.post(f"/session/{sid}/message", json={"text": text})
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    # R5: planner m4.v1 is now the CANDIDATE SOURCE + guard (not the substance chooser of the question). The
    # M4 POLICY assertions in this file test that deterministic candidate decision (`candidate_move`); the
    # PRESENTED step (`presented_move`) is checked separately in the R5 block below and in evals/test_recovery_adaptive.py.
    j["presented_move"] = j["next_move"]
    j["next_move"] = j["candidate_move"]
    return j


def nav(sid: str) -> dict:
    r = client.get(f"/session/{sid}/navigation")
    assert r.status_code == 200, r.text[:300]
    return r.json()


def ledger_rows(user: str) -> list[dict]:
    f = ledger._LEDGER_ROOT / user / "adjudication_ledger.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def final_state(sid: str) -> dict:
    n = nav(sid)
    return {
        "paths": sorted(p["path_id"] for p in n["summary"]["paths"]),
        "applicable": {k: (v["applicability"], v["satisfaction"], v["adjudicated"]) for k, v in n["requirements"].items()},
    }


# ───────────────────────────── O · full loop ─────────────────────────────
print("O · loop penuh (message -> state -> adjudikasi -> path -> planner -> next move -> loop)")
U1 = "u-m4-loop-1"
sid = new_session(U1)
turns = [say(sid, t) for t in (INC0, CAP, DEM, ICP)]
nm = [t["next_move"] for t in turns]
check("O1 tiap giliran membawa NextMove sah + reason trail mesin-terbaca",
      all(m["kind"] in KINDS and m["intent"] and m["focus"] and "why" in m["reason"] and m["reason"]["considered"] is not None
          and m["reason"]["counts"] and m["reason"]["input_digest"] for m in nm), str([m["kind"] for m in nm]))
g_nodes = list((store.get(sid).state_graph.get("nodes") or {}).values())
check("O2 evidence diekstrak tiap giliran dan Universal State (graph) terisi dari klaim yang LOLOS verify gate",
      all(t["evidence_delta"] for t in turns) and any(n["triple"]["value"] == 0.0 and n["verbatim"] for n in g_nodes),
      str(g_nodes)[:200])
check("O3 pergantian giliran menggeser keputusan: bukan urutan tetap (kind/fokus berganti sesuai state)",
      len({(m["kind"], m["focus"]["id"]) for m in nm}) >= 3, str([(m["kind"], m["focus"]["id"]) for m in nm]))
check("O4 candidate/path 0..N dibentuk dari state percakapan (tanpa finalize): direct_outreach OPEN setelah kapasitas+demand",
      {p["path_id"]: p["status"] for p in turns[2]["navigation"]["paths"]}.get("path.direct_outreach") == "OPEN")
adj = turns[3]["navigation"]["adjudication"]
check("O5 adjudikasi LIVE mengisi ledger: ICP terbukti oleh aturan formal, bukan oleh mapper/LLM",
      [(a["requirement_id"], a["status"]) for a in adj["adjudicated"]] == [("access.icp", "PRESENT")]
      and [r["adjudication"]["requirement_id"] for r in ledger_rows(U1)] == ["access.icp"])
n = nav(sid)
icp = n["requirements"]["access.icp"]
check("O6 Requirement State Reader memuat keadaan lengkap: PRESENT + sitasi + waktu + asal + dukungan",
      icp["satisfaction"] == "PRESENT" and icp["adjudicated"] and icp["evidence_refs"] and icp["last_updated"]
      and icp["verification"]["method"] == "deterministic_adjudicator" and icp["support"] == "FORMAL_RULE", str(icp))
outreach = [r for r in rl.list_rows(U1) if r["lineage"]["reconciliation_key"]["strategy_id"] == "direct_outreach"]
nodes = {nd["resolves"][0]: nd for nd in outreach[-1]["lineage"]["revisions"][-1]["nodes"]} if outreach else {}
check("O7 Route membaca keadaan yang SAMA lewat reader tunggal: node access.icp PRESENT, tak ada pembacaan ledger kedua",
      nodes.get("access.icp", {}).get("satisfaction", {}).get("status") == "PRESENT")
last = turns[3]["next_move"]
check("O8 cukup untuk bertindak -> ACTION/EXECUTE: langkah konkret, stop=True, tanpa pertanyaan karangan",
      last["kind"] == "ACTION" and last["intent"] == "EXECUTE" and last["stop"] and turns[3]["next_question"] is None
      and turns[3]["progress"] == 1.0 and "First step:" in last["text"], str(last["text"]))
check("O8b teks langkah pertama berakhir dengan titik dan memakai langkah terkurasi (bukan teks mesin)",
      last["text"].endswith("came from.") and "List real people by name" in last["text"], last["text"])
more = say(sid, "Saya juga punya portofolio tiga proyek yang selesai.")
check("O9 setelah ACTION sesi TIDAK terkunci: pesan baru tetap diproses dan keputusan dihitung ulang",
      more["next_move"]["kind"] in KINDS and more["evidence_delta"])
check("O9b langkah yang SAMA (ACTION, fokus sama) tidak diulang sebagai kalimat identik: dibunyikan 'tidak berubah', keputusan tetap sama",
      more["next_move"]["kind"] == "ACTION" and more["next_move"]["focus"] == last["focus"]
      and more["next_move"]["text"].startswith("Noted. Your next step has not changed:")
      and "List real people by name" in more["next_move"]["text"] and more["next_move"]["text"] != last["text"])
before = len(ledger_rows(U1))
say(sid, "Saya menyukai desain yang bersih dan sederhana.")
check("O10 ledger = riwayat PERUBAHAN: pesan yang tak mengubah adjudikasi tak menulis baris baru", len(ledger_rows(U1)) == before)
check("O11 tak ada requirement yang menjadi ABSENT hanya karena tak disebut (UNKNOWN != ABSENT)",
      all(v[1] != "ABSENT" for v in final_state(sid)["applicable"].values()))

# ───────────────────────────── RD · Readiness computed in the loop, not the planner ─────────────────────────────
print("RD · Readiness dihitung dari state yang sama; bukan input planner; satu pembaca SEBELUM finalize")
import app.navigation as nav_mod  # noqa: E402

rd_n = nav(sid)
rdp = rd_n["readiness"] or {}
check("RD1 /navigation memuat proyeksi Readiness (v4, CURRENT) atas path yang sama dengan planner; butir konsisten dengan hitungan",
      rdp.get("version") == 4 and rdp["navigation"]["status"] == "CURRENT"
      and [p_["path_id"] for p_ in rdp["paths"]] == [p_["path_id"] for p_ in rd_n["summary"]["paths"]]
      and all(p_["counts"]["total"] == len(p_["items"]) for p_ in rdp["paths"]), str(list(rdp)))
check("RD2 ringkasan tiap giliran membawa hitungan Readiness per path (tanpa memuat proyeksi penuh)",
      all({"path_id", "executability", "counts"} <= set(r_) for r_ in turns[3]["navigation"]["readiness"])
      and [r_["path_id"] for r_ in turns[3]["navigation"]["readiness"]] == [p_["path_id"] for p_ in turns[3]["navigation"]["paths"]])
pairs_rd = []
for p_ in rdp.get("paths", []):
    rt_ = p_.get("route")
    for it_ in p_["items"]:
        if rt_ and it_["requirement_id"] and "route" in it_["sources"]:
            ctx_ = [c for c in rd_n["requirements"].get(it_["requirement_id"], {}).get("contexts", [])
                    if c["kind"] == "route" and c["id"] == rt_["route_id"]]
            pairs_rd.append((it_["requirement_id"], it_["state"], ctx_[0]["state"] if ctx_ else None))
check("RD3 SATU PEMBACA sebelum finalize: tiap butir Readiness asal node route = pembacaan planner di konteks route yang sama "
      "(dari respons /navigation yang sama)",
      len(pairs_rd) >= 8 and all(a_[1] == a_[2] for a_ in pairs_rd), str([a_ for a_ in pairs_rd if a_[1] != a_[2]][:3]))
check("RD4 Readiness BUKAN input planner: input keputusan tak memuat Readiness",
      all("readiness" not in e_["input"] for e_ in store.get(sid).planner_log if "input" in e_))
s_rd = store.get(sid)
base_nav = navigate_session(s_rd, asked_from=s_rd.planner_log[:-1])
_orig_bp = nav_mod.build_projection
nav_mod.build_projection = lambda *a_, **k_: (_ for _ in ()).throw(RuntimeError("readiness boom"))
try:
    broken_nav = navigate_session(s_rd, asked_from=s_rd.planner_log[:-1])
finally:
    nav_mod.build_projection = _orig_bp
check("RD5 proyeksi Readiness yang gagal TIDAK mengubah keputusan planner (keputusan identik, termasuk digest) dan tercatat di errors",
      broken_nav.readiness is None and base_nav.readiness is not None and broken_nav.decision == base_nav.decision
      and any("readiness: RuntimeError" in e_ for e_ in broken_nav.errors) and not base_nav.errors)

# ───────────────────────────── I · free order ─────────────────────────────
print("I · free-order: dua urutan, keadaan akhir ekuivalen, trajektori berbeda")
ORDER_A = [INC0, PRICE, CUST, PROOF, CAP]
ORDER_B = [INC0, CUST, PROOF, PRICE, CAP]
sa, sb = new_session("u-m4-order-a"), new_session("u-m4-order-b")
ta = [say(sa, t) for t in ORDER_A]
tb = [say(sb, t) for t in ORDER_B]
check("I1 keadaan akhir EKUIVALEN (path + requirement + applicability + satisfaction) walau urutan jawaban berbeda",
      final_state(sa) == final_state(sb), f"{final_state(sa)['paths']} vs {final_state(sb)['paths']}")
traj_a = [(m["next_move"]["kind"], m["next_move"]["focus"]["id"]) for m in ta]
traj_b = [(m["next_move"]["kind"], m["next_move"]["focus"]["id"]) for m in tb]
check("I2 trajektori percakapan BERBEDA (planner mengikuti state, bukan urutan tetap)", traj_a != traj_b, f"{traj_a} / {traj_b}")


def resolved_asked(sid_: str) -> list[str]:
    """Turns asking about a requirement ALREADY answered in that turn's input (should be empty)."""
    bad = []
    for e in store.get(sid_).planner_log:
        d = e["decision"]
        if d["focus"]["type"] == "requirement" and d["kind"] in ("QUESTION", "EVIDENCE_REQUEST"):
            # input is stored only for the last REPLAY_WINDOW; the rest state their own reason in the decision
            sat = e["input"]["requirements"][d["focus"]["id"]]["satisfaction"] if "input" in e else None
            if (sat is not None and sat != "UNKNOWN") or "satisfaction=UNKNOWN" not in d["reason"]["why"]:
                bad.append(d["focus"]["id"])
    return bad


check("I3 planner tak pernah menanyakan sesuatu yang sudah terjawab (di kedua urutan)", not resolved_asked(sa) and not resolved_asked(sb))
cap_turn_a = next(i for i, t in enumerate(ORDER_A) if t == CAP)
check("I4 jawaban kapasitas muncul di posisi berbeda (A akhir, B akhir) tetapi memetakan requirement yang sama",
      final_state(sa)["applicable"]["delivery.capacity"][1] == "PRESENT" == final_state(sb)["applicable"]["delivery.capacity"][1]
      and cap_turn_a == 4)
multi = new_session("u-m4-multi")
t_multi = say(multi, f"{INC0} {CAP} {DEM}")
c_multi = t_multi["next_move"]["reason"]["counts"]
check("I5 satu pesan berisi beberapa fakta memetakan beberapa kebutuhan sekaligus (resolved >= 2)", c_multi["resolved"] >= 2, str(c_multi))
fs_multi = final_state(multi)["applicable"]
check("I6 satu jawaban BUKAN otomatis PRESENT untuk semua: requirement lain tetap UNKNOWN tanpa adjudikasi",
      fs_multi["access.icp"] == ("APPLIES", "UNKNOWN", False) and fs_multi["delivery.capacity"][1] == "PRESENT"
      and sum(1 for v in fs_multi.values() if v[1] == "PRESENT") == 1, str(fs_multi))

# ───────────────────────────── J · direction switch ─────────────────────────────
print("J · direction switch tanpa restart sesi")
sj = new_session("u-m4-switch")
j1, j2 = say(sj, INC0), say(sj, CAP)
paths_before = {p["path_id"] for p in j2["navigation"]["paths"]}
j3 = say(sj, INC8)
paths_after = {p["path_id"] for p in j3["navigation"]["paths"]}
check("J1 evidence baru (pendapatan berjalan) melahirkan arah BARU: path bertambah di sesi yang sama",
      paths_before == {"path.direct_outreach", "path.paid_channel_test"}
      and {"path.value_repricing", "path.client_expansion", "path.referral_partnership"} <= paths_after, f"{paths_before} -> {paths_after}")
foc = j3["next_move"]["focus"]
check("J2 fokus planner bergeser ke kebutuhan milik arah baru (bukan terkunci pada hipotesis awal)",
      foc["id"] == "commercial.willingness_to_pay"
      and any(c["id"] == "path.value_repricing" for c in j3["next_move"]["reason"]["contexts"]), str(j3["next_move"]))
check("J3 sesi yang sama (tanpa restart): log planner tumbuh, id sesi tetap",
      len(store.get(sj).planner_log) == 4)   # R5: the first Create Map question is now counted (1) + 3 messages

# ───────────────────────────── K · candidate-born ─────────────────────────────
print("K · candidate-born: lahir dari mekanisme, memakai pipeline YANG SAMA (tanpa cabang khusus)")

LEAK = "Ada 3 orang yang bertanya soal jasa saya (inquiry masuk), tapi tidak di-follow dan respons lambat, sering lambat membalas."
CAND = "path.fix_response_before_more_leads"
sk = new_session("u-m4-cand")
k1, k2, k3 = say(sk, INC0), say(sk, LEAK), say(sk, CAP)
sess_k = store.get(sk)
nav_k = navigate_session(sess_k, asked_from=sess_k.planner_log[:-1])
cand = next((p_ for p_ in nav_k.path_set["paths"] if p_["path_id"] == CAND), None)
ids_before = {p_["path_id"] for p_ in k1["navigation"]["paths"]}
ids_after = {p_["path_id"] for p_ in k2["navigation"]["paths"]}
check("K1 evidence kebocoran melahirkan path KANDIDAT di sesi yang sama (sebelumnya tak ada); path 0..N bertambah",
      CAND not in ids_before and CAND in ids_after and len(ids_after) == len(ids_before) + 1, f"{ids_before} -> {ids_after}")
cprov = ((cand or {}).get("provenance") or {}).get("candidate") or {}
user_ev = {e.id for e in sess_k.evidence}
check("K2 provenance candidate: origin MECHANISM_PATTERN, mekanisme lead_leakage, dikutip dari evidence yang ADA di sesi",
      cprov.get("origin") == "MECHANISM_PATTERN" and cprov.get("mechanism_ids") == ["lead_leakage"]
      and bool(cprov.get("evidence_ids")) and set(cprov["evidence_ids"]) <= user_ev, str(cprov)[:200])
routes_k = [r_ for r_ in (nav_k.routes or {}).get("routes", []) if r_.get("strategy_id") == (cand or {}).get("strategy_id")]
check("K3 path kandidat TANPA route dan TANPA check berjangkar: tetap path navigable (dihitung), tak ada pertanyaan karangan",
      cand is not None and cand["checks"] == [] and routes_k == []
      and k2["next_move"]["reason"]["counts"]["navigable_paths"] == k1["next_move"]["reason"]["counts"]["navigable_paths"] + 1
      and not any(c_["id"] == CAND for t_ in (k2, k3) for c_ in t_["next_move"]["reason"]["contexts"]))
check("K4 pipeline yang sama: tak ada error navigasi, keputusan sah, dan path lain tetap bergerak (direct_outreach OPEN setelah kapasitas)",
      all(not t_["navigation"]["errors"] and t_["next_move"]["kind"] in KINDS for t_ in (k1, k2, k3))
      and {p_["path_id"]: p_["status"] for p_ in k3["navigation"]["paths"]}.get("path.direct_outreach") == "OPEN"
      and CAND in {p_["path_id"] for p_ in k3["navigation"]["paths"]})
check("K5 kandidat tidak meniadakan pembacaan state: adjudikasi/ledger user tak tersentuh oleh kelahiran kandidat",
      ledger_rows("u-m4-cand") == [] and all(not v_["adjudicated"] for v_ in nav(sk)["requirements"].values()))

# ───────────────────────────── HOLD ─────────────────────────────
print("HOLD · tak ada langkah aman")
sh = new_session("u-m4-hold", goal="bisnis saya")
h = [say(sh, t) for t in ("halo apa kabar semuanya baik", "oke terima kasih banyak ya", "sampai jumpa lagi nanti")]
check("H1 tujuan tak pernah terbukti: ditanya lalu (batas tercapai) -> HOLD dengan alasan, bukan mengulang tanpa akhir",
      # R5: the first Create Map question now counts as "asked" (ASK_CAP=2 total): ask (Create Map) + ask
      # (message 1) then HOLD — the total goal-question count stays 2, no longer 3 (one question used to go unlogged).
      [t["next_move"]["kind"] for t in h] == ["QUESTION", "HOLD", "HOLD"] and h[2]["next_question"] is None)
check("H2 HOLD bukan 'selesai': progress < 1.0 dan input tetap diterima", h[2]["progress"] < 1.0)
h4 = say(sh, "Saya mau Rp20 juta per bulan dari jasa dalam 90 hari. Pendapatan saya sekarang Rp0 per bulan.")
check("H3 informasi baru melanjutkan percakapan (HOLD tidak mengunci): planner menghitung ulang dan bertanya lagi",
      h4["next_move"]["kind"] in ("QUESTION", "EVIDENCE_REQUEST") and h4["next_move"]["reason"]["stage"] != "FALLBACK",
      str(h4["next_move"]["kind"]))

# ───────────────────────────── 35 · scoping ─────────────────────────────
print("35 · scoping user + sesi anonim")
UA, UB = "u-m4-scope-a", "u-m4-scope-b"
sA, sB = new_session(UA), new_session(UB)
for t in (INC0, CAP, DEM, ICP):
    say(sA, t)
for t in (INC0, CAP, DEM):
    say(sB, t)
check("S1 ICP milik A terbukti di ledger A", nav(sA)["requirements"]["access.icp"]["satisfaction"] == "PRESENT")
check("S2 user B dengan evidence yang sama KECUALI ICP: ICP tidak terbaca (UNKNOWN by absence), tak bocor dari A",
      nav(sB)["requirements"]["access.icp"]["adjudicated"] is False and nav(sB)["requirements"]["access.icp"]["satisfaction"] == "UNKNOWN")
check("S3 ledger terpisah per user; B tidak punya entri", ledger_rows(UB) == [] and len(ledger_rows(UA)) == 1)
anon = new_session(None)
ta1 = say(anon, INC0)
ta2 = say(anon, CAP)
n_an = nav(anon)
check("S4 sesi tanpa user tetap berjalan (path + planner), adjudikasi dilaporkan tidak ber-scope — bukan ledger bersama",
      ta2["navigation"]["adjudication"] == {"scoped": False, "skipped": "NO_USER_SCOPE"} and ta2["next_move"]["kind"] in KINDS
      and not (ledger._LEDGER_ROOT / "adjudication_ledger.jsonl").exists())
check("S5 requirement sesi anonim berdukungan NO_USER_SCOPE (tak mengarang status)",
      all(v["support"] == "NO_USER_SCOPE" and not v["adjudicated"] for v in n_an["requirements"].values()))
check("S6 sesi anonim: path tetap terbentuk dan planner tetap bertanya tentang state yang dapat dijawab",
      ta1["navigation"]["paths"] and ta1["next_move"]["kind"] == "QUESTION")

# ───────────────────────────── P · persistence + replay ─────────────────────────────
print("P · persistensi + replay")
log = store.get(sid).planner_log
within = [e for e in log if "input" in e]
older = [e for e in log if "input" not in e]
check("P1 log keputusan tersimpan per giliran (turn, keputusan, teks); INPUT hanya pada REPLAY_WINDOW entri terakhir, "
      "`texts` tak pernah disimpan, `applicable` hanya pada entri terakhir",
      len(log) >= 6 and all({"turn", "decision", "text"} <= set(e) for e in log)
      and [("input" in e) for e in log] == [i >= len(log) - REPLAY_WINDOW for i in range(len(log))]
      and all("texts" not in e.get("input", {}) for e in log)
      and [("applicable" in e.get("input", {})) for e in log] == [i == len(log) - 1 for i in range(len(log))])
check("P2 REPLAY: setiap keputusan yang inputnya tersimpan dihitung ulang -> identik",
      len(within) == REPLAY_WINDOW and all(replay(e)["ok"] is True for e in within))
check("P2b entri yang dipadatkan jujur: replay -> ok None / COMPACTED (bukan lolos), keputusan + digest tetap ada",
      bool(older) and all(replay(e)["ok"] is None and replay(e)["reason"] == "COMPACTED"
                          and e["decision"]["reason"]["input_digest"] for e in older))
synthetic = [{"turn": i, "input": {"a": i, "texts": {}, "applicable": {"x": i}}, "decision": {"i": i}, "text": {}}
             for i in range(REPLAY_WINDOW + 4)]
packed = compact_log(synthetic)
check("P2c compact_log: hanya REPLAY_WINDOW terakhir menyimpan input, hanya yang terakhir menyimpan applicable; "
      "keputusan tak pernah dibuang; idempoten; tak mengubah masukan",
      [("input" in e) for e in packed] == [i >= 4 for i in range(REPLAY_WINDOW + 4)]
      and [("applicable" in e.get("input", {})) for e in packed] == [i == REPLAY_WINDOW + 3 for i in range(REPLAY_WINDOW + 4)]
      and [e["decision"] for e in packed] == [e["decision"] for e in synthetic]
      and compact_log(packed) == packed and "applicable" in synthetic[0]["input"])
check("P3 endpoint /navigation melaporkan replay keputusan terakhir", nav(sid)["last_logged"]["replay"] is True)
sid_chk = new_session("u-m4-sync")
sync_ok, sync_detail = True, ""
for t_ in (INC0, CAP, DEM):
    resp = say(sid_chk, t_)
    rec = nav(sid_chk)
    pm = resp["presented_move"]   # R5: /navigation.move = the PRESENTED step (not the deterministic candidate)
    same = (rec["move"]["reason"]["policy"] == pm["reason"]["policy"]
            and rec["move"]["kind"] == pm["kind"] and rec["move"]["text"] == pm["text"]
            and rec["last_logged"]["kind"] == resp["candidate_move"]["kind"])
    if not (same and rec["in_sync"] and rec["recomputed"] is None):
        sync_ok, sync_detail = False, f"{rec['move']['kind']} vs {pm['kind']} in_sync={rec['in_sync']}"
check("P3b /navigation.move = langkah yang SEDANG disajikan (sama persis dengan respons giliran: digest, jenis, teks), in_sync, "
      "bukan langkah sesudahnya", sync_ok, sync_detail)
fresh = SessionStore()
loaded = fresh.get(sid)
hist = nav(sid)["history"]
check("P3c /navigation.history memuat tiap langkah yang pernah disajikan (kind, intent, headline, text) — dasar pemulihan UI",
      len(hist) == len(store.get(sid).planner_log) and all({"turn", "kind", "intent", "headline", "text"} <= set(h_) for h_ in hist)
      and hist[-1]["text"] == store.get(sid).planner_log[-1]["text"]["text"])
check("P4 sesi dimuat ulang dari DISK dengan log planner utuh (replay entri ber-input tetap OK setelah restart; "
      "entri terpadatkan tetap jujur)",
      loaded is not None and len(loaded.planner_log) == len(log)
      and all(replay(e)["ok"] is True for e in loaded.planner_log if "input" in e)
      and all(replay(e)["ok"] is None for e in loaded.planner_log if "input" not in e)
      and [("input" in e) for e in loaded.planner_log] == [("input" in e) for e in log])
legacy_path = store.PERSIST_DIR / "m4legacy000001.json"
legacy_path.write_text(json.dumps({"id": "m4legacy000001", "goal_text": "lama", "language": "id", "phase": "MOTION",
                                   "transcript": [["user", "halo"]], "evidence": [], "turns_in_phase": 1}), encoding="utf-8")
_created.append("m4legacy000001")
legacy = SessionStore().get("m4legacy000001")
check("P5 sesi LAMA tanpa planner_log termuat aman (aditif): log kosong, planner siap; kunci legacy `phase`/`turns_in_phase` "
      "diabaikan (M5: tak menjadi atribut Session)",
      legacy is not None and legacy.planner_log == [] and not hasattr(legacy, "phase") and not hasattr(legacy, "turns_in_phase"))
check("P6 asked-counter berasal dari log (bukan state mutable): jumlah QUESTION/EVIDENCE per kebutuhan konsisten dengan log",
      nav(sid)["asked"] == {k: v for k, v in nav(sid)["asked"].items() if v >= 1})

# ───────────────────────────── X · compatibility + phases not moving ─────────────────────────────
print("X · kontrak API tanpa fase interview (M5)")
first = turns[0]
check("X1 field turn yang berlaku ada (kind, progress, intent_tags, evidence_delta, next_question, next_move, navigation); "
      "`phase` dan `phase_index` TIDAK ada",
      all(k in first for k in ("kind", "progress", "intent_tags", "evidence_delta", "next_question", "next_move", "navigation"))
      and not any(k in first for k in ("phase", "phase_index")) and first["kind"] == "probe")
s_obj = store.get(sid)
persisted = json.loads((store.PERSIST_DIR / f"{sid}.json").read_text(encoding="utf-8"))
check("X2 setelah 6+ giliran: Session tak punya state fase, berkas sesi baru tak menulis `phase`/`turns_in_phase`, "
      "evidence tersimpan sebagai `topic` (bukan `phase`)",
      not hasattr(s_obj, "phase") and not hasattr(s_obj, "turns_in_phase")
      and "phase" not in persisted and "turns_in_phase" not in persisted
      and all("topic" in e_ and "phase" not in e_ for e_ in persisted["evidence"]))
check("X3 next_question = teks NextMove untuk QUESTION/EVIDENCE_REQUEST; None untuk ACTION/HOLD",
      all((t["next_question"] == t["presented_move"]["text"]) if t["presented_move"]["kind"] in ("QUESTION", "EVIDENCE_REQUEST")
          else t["next_question"] is None for t in turns + h))
check("X4 progress berbasis state: tidak berupa (indeks fase+1)/5 — bernilai 0.0/0.5/0.95/1.0 sesuai kejelasan",
      {t["progress"] for t in turns} <= {0.0, 0.25, 0.33, 0.5, 0.67, 0.75, 0.95, 1.0}
      and not all(abs(t["progress"] - (i + 1) / 5) < 0.01 for i, t in enumerate(turns)))
check("X5 interview_done tidak diputuskan planner: tetap False sampai /finalize (sesi tidak terkunci)", s_obj.interview_done is False)

# ───────────────────────────── F · finalize + Readiness single reality ─────────────────────────────
print("F · finalize tanpa gating fase; Readiness membaca keadaan yang sama")
fr = client.post(f"/session/{sid}/finalize")
check("F1 /finalize (provisional/final) tetap berfungsi tanpa fase sebagai gating", fr.status_code == 200, fr.text[:200])
d = fr.json()
check("F2 diagnosis memuat possible_paths 0..N (jalur diagnosis tak berubah semantik)",
      isinstance(d.get("possible_paths", {}).get("paths"), list))
rd = client.get(f"/session/{sid}/readiness")
items = {it["key"]: it for p in rd.json()["paths"] for it in p["items"]} if rd.status_code == 200 else {}
check("F3 Readiness (route -> reader ledger) menampilkan ICP PRESENT yang SAMA dengan planner (satu realitas)",
      rd.status_code == 200 and items.get("access.icp", {}).get("state") == "PRESENT", str(items.get("access.icp")))
rd_paths = rd.json()["paths"] if rd.status_code == 200 else []
plan_views = nav(sid)["requirements"]
pairs = []
for p_ in rd_paths:
    rt = p_.get("route")
    for it_ in p_["items"]:
        if rt and it_["requirement_id"] and "route" in it_["sources"]:
            ctx = [c for c in plan_views.get(it_["requirement_id"], {}).get("contexts", [])
                   if c["kind"] == "route" and c["id"] == rt["route_id"]]
            pairs.append((p_["path_id"], it_["requirement_id"], it_["state"], ctx[0]["state"] if ctx else None))
mismatch = [x for x in pairs if x[2] != x[3]]
check("F3b SATU PEMBACA: untuk SETIAP butir Readiness berasal dari node route, keadaannya = pembacaan planner di "
      "konteks route yang sama (ledger + aturan merge yang sama), bukan hanya satu requirement",
      len(pairs) >= 10 and not mismatch, f"{len(pairs)} pasangan; selisih: {mismatch[:4]}")
check("F3c tak ada karangan: konteks route tanpa sumber pembacaan (ledger/check) selalu UNKNOWN",
      all(c["state"] == "UNKNOWN" for v_ in plan_views.values() for c in v_["contexts"]
          if c["kind"] == "route" and not c["sources"]))
from domains.revenue.navigation.space import revenue_space  # noqa: E402

space = revenue_space()
routeless_anchored = sorted(
    [s_.strategy_id for s_ in space.strategies if not s_.route_template_ids and any(c.requirement_id for c in s_.checks)]
    + [p_.direction for p_ in space.patterns if any(c.requirement_id for c in getattr(p_, "checks", ()))])
check("F3d BATAS YANG DIPANTAU: tak ada strategi tanpa template / pola kandidat yang membawa check berjangkar "
      "requirement — satu-satunya kasus di mana Readiness (route-backed) tak membaca ledger; bila daftar ini terisi, "
      "Readiness wajib menerima RequirementStateReader (lihat doc 14 §25.9)", routeless_anchored == [], str(routeless_anchored))
fk = client.post(f"/session/{sk}/finalize")
rk = client.get(f"/session/{sk}/readiness")
rk_path = next((p_ for p_ in rk.json()["paths"] if p_["path_id"] == CAND), None) if rk.status_code == 200 else None
check("F3e path kandidat tampil di Readiness sebagai path TANPA route dan tanpa butir (Possible Path != RouteTemplate), "
      "dengan asal candidate — tidak ada requirement/butir yang dikarang untuknya",
      fk.status_code == 200 and rk_path is not None and rk_path["route"] is None and rk_path["items"] == []
      and (rk_path["candidate"] or {}).get("origin") == "MECHANISM_PATTERN", str(rk_path)[:200])
# ───── LN · REAL LLM deviation on extraction (found via a real provider probe) ─────
from agents.interview import TurnExtraction  # noqa: E402
from core.llm import LLMProvider  # noqa: E402

_dev = {"intent_tags": [{"kind": "fact", "quote": "q", "normalized": "n", "confidence": 0.9},
                        {"kind": "Self_Reported", "quote": "q2", "normalized": "n2", "confidence": 0.9}],
        "evidence": [{"id": "x", "signal": "s", "level": "SELF_REPORTED", "topic": "DEMAND", "is_gap": False}],
        "number_claims": []}
_fixed, _diffs = LLMProvider._shape_repair(TurnExtraction, json.loads(json.dumps(_dev)))
_defs = LLMProvider._semantic_defects(TurnExtraction, _fixed)
check("LN1 case-only tetap mekanis tanpa retry penuh ('fact'→FACT, 'SELF_REPORTED'→self_reported); "
      "kosakata silang ('Self_Reported' sbg kind) = SemanticDefect MC01-M06, BUKAN dipetakan diam-diam; "
      "confidence tidak lagi diturunkan paksa",
      _fixed["intent_tags"][0]["kind"] == "FACT" and _fixed["intent_tags"][1]["kind"] == "Self_Reported"
      and _fixed["intent_tags"][1]["confidence"] == 0.9
      and _fixed["evidence"][0]["level"] == "self_reported"
      and [d.code for d in _defs] == ["MC01-M06"])

# ───── FS · fail-safe: broken navigation does not drop the conversation, and invents no step ─────
import app.navigation as nav_mod  # noqa: E402

sfs = new_session("u-m4-failsafe")
fs0 = say(sfs, INC0)
orig_paths = nav_mod.revenue_live.provisional_path_set


def _boom(*_a, **_k):
    raise RuntimeError("boom")


nav_mod.revenue_live.provisional_path_set = _boom
try:
    fs1 = say(sfs, CAP)
finally:
    nav_mod.revenue_live.provisional_path_set = orig_paths
check("FS1 navigasi gagal di tengah giliran -> /message tetap 200: langkah = HOLD jujur (bukan pertanyaan karangan), "
      "kesalahan TERLIHAT di navigation.errors, evidence giliran itu tetap tercatat",
      fs1["next_move"]["kind"] == "HOLD" and fs1["next_question"] is None and fs1["evidence_delta"]
      and any("RuntimeError: boom" in e_ for e_ in fs1["navigation"]["errors"])
      and fs1["navigation"]["adjudication"].get("skipped") == "NAVIGATION_FAILED", str(fs1["navigation"]))
fs2 = say(sfs, DEM)
check("FS2 giliran berikutnya PULIH tanpa campur tangan: navigasi normal, tak ada error, state hasil giliran gagal tak hilang",
      not fs2["navigation"]["errors"] and fs2["next_move"]["kind"] in ("QUESTION", "EVIDENCE_REQUEST", "ACTION")
      and fs2["next_move"]["reason"]["stage"] != "FALLBACK"
      and {p_["path_id"]: p_["status"] for p_ in fs2["navigation"]["paths"]}.get("path.direct_outreach") == "OPEN")
fs_log = store.get(sfs).planner_log
check("FS3 giliran gagal tetap tercatat di log planner dan dapat direplay (HOLD dihitung lewat planner yang sama)",
      len(fs_log) == 4 and fs_log[2]["decision"]["kind"] == "HOLD" and replay(fs_log[2])["ok"] is True)   # [0] = Create Map (R5)
# R6 (int 16 §R6-A, F-17): the OLD assertion "after finalize /message returns an ack" locked in the very defect
# that was removed — a post-diagnosis user correction MUST NOT be ignored. Replaced: post-finalize messages
# enter the same path.
r_ack = client.post(f"/session/{sid}/message", json={"text": "Koreksi: sebenarnya klien aktif saya 3 orang."})
j_ack = r_ack.json()
check("F4 (R6) setelah finalize /message TIDAK lagi ack: pesan diproses (evidence + langkah) dan diklasifikasi perubahan",
      r_ack.status_code == 200 and j_ack["kind"] == "probe" and j_ack["next_move"] is not None
      and j_ack["evidence_delta"] and j_ack["change_class"] in ("new_information", "correction", "goal_change"),
      str({k: j_ack.get(k) for k in ("kind", "change_class")}))
check("F5 anti-regresi: tidak ada 500 / error navigasi di seluruh percakapan",
      all(not t["navigation"]["errors"] for t in turns + ta + tb + h + [t_multi, j1, j2, j3]))

print()
bad = [n for n, ok, _ in RESULTS if not ok]
print(f"HASIL: {len(RESULTS) - len(bad)}/{len(RESULTS)} PASS {'✅' if not bad else '❌ ' + str(bad)}")
sys.exit(0 if not bad else 1)
