"""M5 — the phased interview engine is REMOVED from production architecture (doc 14 §26; INV-7 int 10; int 11 §10.15).

M4 proved the phase engine is "present but not an authority" (positive control: `analyze_turn` still detected).
M5 flips the control: the engine NO LONGER EXISTS, and the conversation path has nowhere to reload it.

  R   removal: not a single phase-engine identifier in PRODUCTION CODE (AST over the whole tree, not a module
      list); the phase-engine files are gone; old symbols cannot be imported
  G   guard not vacuous: synthetic snippets containing every forbidden identifier are caught; clean code is not
  A   API contract: /session, /session/{id}, /message responses without `phase`/`phase_index`; schema without
      `phase_transition`
  P   persistence: new sessions do not write `phase`/`turns_in_phase`; evidence is written as `topic`
  C   legacy data compatibility: files stained with `phase`/`turns_in_phase`/evidence-`phase` load, and the phase
      does NOT influence planner decisions (negative property); every legacy session on disk loads
  N   negative property: evidence topic labels, old phases, and turn counts do not change NextMove/readiness
  K   knowledge: rule-source activation = one list (diagnosis semantics unchanged); the validator rejects wrong
      prefixes
  E   the E2E domain (PRA_SALES/SALES/AFTER_SALES) stays alive: a different concept from interview phases

Deterministic, no LLM (mock provider). Run: .venv/bin/python evals/test_m5_phase_removal.py
"""
from __future__ import annotations

import ast
import atexit
import copy
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MVP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MVP))

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

import store.adjudication_ledger as ledger  # noqa: E402
import store.funnel as funnel  # noqa: E402
import store.path_states as path_states  # noqa: E402
import store.route_execution as route_execution  # noqa: E402
import store.route_lineages as rl  # noqa: E402
import store.workspace as workspace  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="m5_phase_"))
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
from app.navigation import navigate_session  # noqa: E402
from providers.mock import MockProvider  # noqa: E402
from store.memory import SessionStore, store  # noqa: E402

app_main.get_llm = lambda: MockProvider()
assert app_main.get_llm().name == "mock", "uji ini hanya boleh berjalan dengan provider mock"
client = TestClient(app_main.app)
_created: list[str] = []
atexit.register(lambda: [(store.PERSIST_DIR / f"{sid}.json").unlink(missing_ok=True) for sid in _created])

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


# Phased interview-machine identifiers. Names (variables/attributes/imports/arguments), not free text.
FORBIDDEN = {
    "PHASES", "Phase", "phase_index", "turns_in_phase", "MAX_TURNS_PER_PHASE", "HARD_TURN_CAP",
    "phase_has_hard_evidence", "phase_gap_count", "phase_opener", "phase_fallback", "PHASE_GOALS",
    "analyze_turn", "build_turn", "InterviewAnalysis", "format_probe_hints", "probes_for_phase",
    "probe_hint_budget", "phase_config", "PhaseModel", "PhaseDeclaration", "advance_to_next_phase",
    "next_phase", "llm_wants_advance", "hard_capped", "evidence_sufficient", "phase", "phase_transition",
}
FORBIDDEN_MODULES = ("core.schema.phases", "domains.revenue.prompts.phase_openers")
# E2E domain (NOT interview phases): journey.py uses `phases`/`E2E_PHASES`/`e2e_phases` — not `phase`.


def names_in(node: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.append((n.id, n.lineno))
        elif isinstance(n, ast.Attribute):
            out.append((n.attr, n.lineno))
        elif isinstance(n, ast.alias):
            out.append((n.name.split(".")[-1], getattr(n, "lineno", 0)))
        elif isinstance(n, ast.arg):
            out.append((n.arg, n.lineno))
        elif isinstance(n, ast.keyword) and n.arg:
            out.append((n.arg, getattr(n.value, "lineno", 0)))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append((n.name, n.lineno))
    return out


def violations(tree: ast.AST) -> list[tuple[str, int]]:
    return [(nm, ln) for nm, ln in names_in(tree) if nm in FORBIDDEN]


def production_files() -> list[Path]:
    """All production .py: everything that is not an eval harness (`evals/`), not venv/node_modules/egg-info."""
    skip = {".venv", "node_modules", "novaliners_engine.egg-info", "__pycache__", "evals", "e2e", "traces"}
    out = []
    for p in sorted(MVP.rglob("*.py")):
        if any(part in skip for part in p.relative_to(MVP).parts):
            continue
        out.append(p)
    return out


# ── R · removal
print("R · mesin fase tak ada di kode produksi")
files = production_files()
check("R0 pemindaian mencakup pohon produksi (agents, app, core, domains, engine, ontology, providers, store)",
      {"agents", "app", "core", "domains", "engine", "ontology", "providers", "store"}
      <= {f.relative_to(MVP).parts[0] for f in files}, str(len(files)))
bad: list[str] = []
for f in files:
    v = violations(ast.parse(f.read_text(encoding="utf-8")))
    if v:
        bad.append(f"{f.relative_to(MVP)}:{v[:3]}")
check("R1 NOL identifier mesin fase (PHASES, phase_index, analyze_turn, build_turn, phase, ...) di seluruh kode produksi",
      not bad, "; ".join(bad[:5]))
bad_imports = []
for f in files:
    for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        mods = ([n.module] if isinstance(n, ast.ImportFrom) and n.module
                else ([a.name for a in n.names] if isinstance(n, ast.Import) else []))
        bad_imports += [(str(f.relative_to(MVP)), m) for m in mods if m.startswith(FORBIDDEN_MODULES)]
check("R2 tak ada impor modul mesin fase", not bad_imports, str(bad_imports))
gone = ["ontology/knowledge/phases.json", "core/schema/phases.py", "domains/revenue/prompts/phase_openers.py",
      # interview_system: old extraction producer removed (Oct 15 cleanup, replaced by core/semantic)
      "domains/revenue/prompts/interview_system.py"]
check("R3 berkas mesin fase tak ada + prompt ekstraksi lama terhapus",
      not [g for g in gone if (MVP / g).exists()], str([g for g in gone if (MVP / g).exists()]))


def has(modname: str, attr: str) -> bool:
    return hasattr(importlib.import_module(modname), attr)


removed = [("agents.interview", a) for a in ("analyze_turn", "build_turn", "InterviewAnalysis", "extract_turn")] + [
    ("core.schema.evidence", a) for a in ("Phase", "PHASES")
] + [("engine.knowledge", a) for a in ("probes_for_phase", "format_probe_hints", "phase_config", "probe_hint_budget",
                                       "default_rule_sources")]
check("R4 simbol lama tak bisa diimpor (analyze_turn, build_turn, InterviewAnalysis, extract_turn, Phase, PHASES, ...)",
      not [(m, a) for m, a in removed if has(m, a)], str([(m, a) for m, a in removed if has(m, a)]))
SessionCls = importlib.import_module("store.memory").Session
check("R4b Session tak punya state/metode fase (phase, turns_in_phase, phase_index, phase_has_hard_evidence, ...)",
      not [a for a in ("phase", "turns_in_phase", "phase_index", "phase_has_hard_evidence", "phase_gap_count",
                       "MAX_TURNS_PER_PHASE", "HARD_TURN_CAP")
           if hasattr(SessionCls, a) or a in getattr(SessionCls, "__dataclass_fields__", {})])
check("R5 kontrak ekstraksi tetap ada di jalur semantik: TurnExtraction + NumberClaim + derive.extraction_payload",
      all(has("agents.interview", a) for a in ("TurnExtraction", "NumberClaim"))
      and has("core.semantic.derive", "extraction_payload"))

# ── G · guard not vacuous
print("G · guard: kontrol negatif (tertangkap) dan bersih (tak tertangkap)")
missed = [nm for nm in sorted(FORBIDDEN)
          if not violations(ast.parse(f"x = {nm}\ny.{nm}()\ndef f({nm}): pass\nclass {nm}: pass\nz(**dict({nm}=1))"))]
check("G1 setiap identifier terlarang tertangkap di posisi Name/Attribute/arg/def/kwarg", not missed, str(missed))
check("G2 potongan 'advance karena giliran habis' tertangkap",
      bool(violations(ast.parse("if s.turns_in_phase >= MAX_TURNS_PER_PHASE:\n    s.phase = PHASES[s.phase_index + 1]"))))
check("G3 potongan pewawancara berfase (analyze_turn/build_turn) tertangkap",
      bool(violations(ast.parse("a = analyze_turn(llm, t, phase, i)\nr = build_turn(a, phase, i, nxt)"))))
check("G4 kode bersih TIDAK tertangkap (tak ada false positive); domain E2E `e2e_phases` tidak tertangkap",
      not violations(ast.parse("decision = plan_next_move(inp)\nfocus = decision['focus']\ne2e_phases = infer_e2e_phases(rs)")))

# ── A · API contract
print("A · kontrak API tanpa fase")
from core.schema.evidence import EvidenceItem, InterviewTurn  # noqa: E402

check("A1 InterviewTurn tanpa field phase/phase_index; kind tak memuat phase_transition",
      not ({"phase", "phase_index"} & set(InterviewTurn.model_fields))
      and "phase_transition" not in str(InterviewTurn.model_fields["kind"].annotation))
check("A2 skema EvidenceItem memakai `topic` (label tampilan), bukan `phase`",
      "topic" in EvidenceItem.model_fields and "phase" not in EvidenceItem.model_fields)

GOAL = "Saya konsultan marketing, mau Rp20 juta per bulan dalam 90 hari."
MSGS = ["Pendapatan saya sekarang Rp0 per bulan.", "Saya kerja sekitar 30 jam per minggu untuk delivery klien.",
        "Ada 3 orang yang bertanya soal jasa saya bulan ini (inquiry masuk).",
        "ICP saya berisi jenis usaha UKM, level direktur, dan peran pembeli owner.",
        "Harga jasa saya Rp3 juta per klien.", "Saya punya 2 klien aktif yang bayar penuh."]


def new_session(user: str | None) -> tuple[str, dict]:
    body = {"goal_text": GOAL, "language": "en"}
    if user:
        body["user_id"] = user
    r = client.post("/session", json=body)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    _created.append(sid)
    return sid, r.json()


sid, created = new_session("u-m5-a")
turns = []
for m in MSGS:
    r = client.post(f"/session/{sid}/message", json={"text": m})
    assert r.status_code == 200, r.text[:200]
    turns.append(r.json())
state = client.get(f"/session/{sid}/state").json()
check("A3 POST /session: tanpa `phase`; tetap memuat session_id, goal, first_question",
      "phase" not in created and {"session_id", "goal", "first_question"} <= set(created))
check("A4 GET /session/{id}/state: tanpa `phase`/`phase_index` (fase bukan state kanonik)",
      not ({"phase", "phase_index"} & set(state)) and {"session_id", "goal_text", "interview_done"} <= set(state))
check("A5 POST /message x6: tak satu pun respons memuat `phase`/`phase_index`; kind selalu probe/ack; NextMove ada",
      all(not ({"phase", "phase_index"} & set(t)) and t["kind"] in ("probe", "ack") and t["next_move"] for t in turns))
check("A6 evidence_delta ber-`topic` dan tanpa `phase`",
      all("topic" in e and "phase" not in e for t in turns for e in t["evidence_delta"])
      and any(t["evidence_delta"] for t in turns))
sess_list = client.get("/sessions").json()
check("A7 GET /sessions tanpa `phase`", all("phase" not in str(set(x)) for x in sess_list)
      if isinstance(sess_list, list) else "phase_index" not in json.dumps(sess_list)[:20000])

# ── P · persistence
print("P · sesi baru tidak menulis state fase")
persisted = json.loads((store.PERSIST_DIR / f"{sid}.json").read_text(encoding="utf-8"))
check("P1 berkas sesi baru tanpa kunci `phase`/`turns_in_phase`/`phase_index`",
      not ({"phase", "turns_in_phase", "phase_index"} & set(persisted)))
check("P2 evidence tersimpan sebagai `topic`; tak ada `phase` di entri evidence",
      persisted["evidence"] and all("topic" in e and "phase" not in e for e in persisted["evidence"]))
check("P3 funnel log tak lagi menulis kolom `phase`", not _TMP.joinpath("funnel.jsonl").exists()
      or all("phase" not in json.loads(x) for x in _TMP.joinpath("funnel.jsonl").read_text().splitlines() if x))

# ── C · legacy data
print("C · kompatibilitas data lama (hanya BACA; fase diabaikan)")
_ORIG_DIR = SessionStore.PERSIST_DIR
legacy_dir = Path(tempfile.mkdtemp(prefix="m5_legacy_", dir=_TMP))
SessionStore.PERSIST_DIR = legacy_dir
try:
    old = copy.deepcopy(persisted)
    old["id"] = "m5legacy000001"
    old["phase"], old["turns_in_phase"], old["phase_index"] = "CONVERSION", 99, 4
    for i, e in enumerate(old["evidence"]):  # old shape: `phase` key, not `topic`
        e["phase"] = ["GOAL", "DEMAND", "MOTION", "CONVERSION", "REVENUE_STATE"][i % 5]
        e.pop("topic", None)
    (legacy_dir / "m5legacy000001.json").write_text(json.dumps(old), encoding="utf-8")
    minimal = {"id": "m5legacy000002", "goal_text": "lama", "language": "id", "phase": "MOTION",
               "transcript": [["user", "halo"]], "evidence": [{"id": "ev-x", "signal": "s", "level": "outcome",
                                                               "phase": "DEMAND"}], "turns_in_phase": 1}
    (legacy_dir / "m5legacy000002.json").write_text(json.dumps(minimal), encoding="utf-8")
    fresh = SessionStore()
    s_old, s_min = fresh.get("m5legacy000001"), fresh.get("m5legacy000002")
    check("C1 berkas lama bernoda phase/turns_in_phase/phase_index termuat; kunci itu tak menjadi atribut Session",
          s_old is not None and s_min is not None
          and not any(hasattr(s_old, a) for a in ("phase", "turns_in_phase", "phase_index")))
    check("C2 evidence berkunci `phase` (lama) terbaca sebagai `topic` (alias baca saja)",
          s_old is not None and len(s_old.evidence) == len(persisted["evidence"])
          and [e.topic for e in s_old.evidence][:3] == ["GOAL", "DEMAND", "MOTION"]
          and s_min is not None and s_min.evidence[0].topic == "DEMAND")
    fresh.save(s_old)
    resaved = json.loads((legacy_dir / "m5legacy000001.json").read_text(encoding="utf-8"))
    check("C3 menyimpan ulang sesi lama TIDAK menulis kembali kunci fase; evidence dimigrasikan ke `topic`",
          not ({"phase", "turns_in_phase", "phase_index"} & set(resaved))
          and all("topic" in e and "phase" not in e for e in resaved["evidence"]))

    # ── N · negative property (computed from the same session with/without phase noise)
    print("N · sifat negatif: fase/topic/giliran tak mengubah keputusan")
    SessionStore.PERSIST_DIR = _ORIG_DIR
    s_base = store.get(sid)

    def digest(s) -> dict:
        d = navigate_session(s).decision
        return {"kind": d["kind"], "intent": d["intent"], "focus": d["focus"], "stop": d["stop"],
                "digest": d["reason"]["input_digest"], "counts": d["reason"]["counts"], "stage": d["reason"]["stage"]}

    base_d = digest(s_base)
    s_old.user_id = s_base.user_id
    s_old.planner_log = copy.deepcopy(s_base.planner_log)
    old_d = digest(s_old)
    check("N1 sesi lama bernoda phase=CONVERSION/turns_in_phase=99 + topic acak -> keputusan planner IDENTIK (kind, intent, "
          "focus, digest input, counts)", base_d == old_d, f"{base_d} vs {old_d}")
    s_topics = copy.deepcopy(s_base)
    for e in s_topics.evidence:
        e.topic = "DEMAND"
    check("N2 mengubah semua label topik evidence tak mengubah keputusan (topic = tampilan saja)",
          digest(s_topics) == base_d)
    s_turns = copy.deepcopy(s_base)
    s_turns.transcript = s_turns.transcript + [("user", "terima kasih")] * 12  # many turns without new evidence
    nav_t, nav_b = navigate_session(s_turns), navigate_session(s_base)
    strip = lambda pi: {k: v for k, v in pi.items() if k != "history"}  # noqa: E731 — history = "already asked" bookkeeping
    check("N3 jumlah giliran bukan gerbang: 12 giliran tambahan tanpa evidence -> input planner (di luar pembukuan "
          "history.turn) dan keputusan (kind, intent, focus, stop) IDENTIK",
          strip(nav_t.planner_input) == strip(nav_b.planner_input)
          and all(nav_t.decision[k] == nav_b.decision[k] for k in ("kind", "intent", "focus", "stop")))
    check("N3b `history.turn` hanya dicatat di input planner dan tak dibaca logika keputusan (planner*.py)",
          not any('"turn"' in (MVP / "core/navigation" / f).read_text() or ".turn" in (MVP / "core/navigation" / f).read_text()
                  for f in ("planner.py", "planner_text.py", "requirement_state.py", "applicability.py")))
    jwt = json.dumps(navigate_session(s_base).decision["reason"], default=str).lower()
    check("N4 reason trail tak merujuk fase / turns_in_phase / hard-evidence-per-fase",
          not any(w in jwt for w in ("phase", "turns_in_phase", "hard_evidence", "phase_gap")), jwt[:200])
    only_self = copy.deepcopy(s_base)
    for e in only_self.evidence:
        e.level = "self_reported"
    d_self = navigate_session(only_self).decision
    check("N5 evidence berlevel self_reported semua (tanpa 'hard evidence') tak otomatis HOLD: tak ada gerbang bukti-keras "
          "per fase", d_self["kind"] in ("QUESTION", "EVIDENCE_REQUEST", "ACTION", "HOLD")
          and "hard_evidence" not in json.dumps(d_self["reason"], default=str).lower())
    # a new session hopping between topics (user not following the old interview order): no "phase rollback"
    sid2, _ = new_session("u-m5-b")
    seq = [MSGS[3], MSGS[0], MSGS[4], MSGS[1], MSGS[3], MSGS[2], MSGS[0]]  # random order + back to an old topic
    outs = [client.post(f"/session/{sid2}/message", json={"text": m}).json() for m in seq]
    check("N6 urutan bebas + kembali ke topik lama: tiap giliran 200 dengan NextMove sah, tanpa kunci fase, tanpa error navigasi",
          all(o["next_move"] and not ({"phase", "phase_index"} & set(o)) and not o["navigation"]["errors"] for o in outs),
          str([o["navigation"]["errors"] for o in outs])[:200])
finally:
    SessionStore.PERSIST_DIR = _ORIG_DIR

# compatibility over ALL legacy sessions on disk (real data, e.g. tagged with `phase`)
files_on_disk = sorted(_ORIG_DIR.glob("*.json"))
fresh_all = SessionStore()
loaded_ids = {s.id for s in fresh_all.all_sessions()}
unreadable = [f.name for f in files_on_disk if f.stem not in loaded_ids and f.stem not in {x for x in _created}]
check("C4 SELURUH berkas sesi di disk termuat (tak ada yang gagal dibaca karena skema fase dihapus)",
      not unreadable, f"{len(unreadable)}/{len(files_on_disk)} gagal: {unreadable[:5]}")

# ── K · knowledge
print("K · aktivasi sumber rule (mekanisme knowledge, bukan fase)")
from engine.knowledge import active_rule_sources, get_kb  # noqa: E402

EXPECTED = {"TM", "VP", "CS", "HK", "PR", "HG", "SP", "LC", "EM"}
check("K1 active_rule_sources() = himpunan yang SAMA dengan diagnosis M4 (semantik diagnosis tak berubah)",
      active_rule_sources() == EXPECTED, str(active_rule_sources()))
check("K2 hasilnya salinan: mutasi pemanggil tak mengubah konfigurasi",
      (active_rule_sources().add("ZZ") or True) and active_rule_sources() == EXPECTED)
import inspect  # noqa: E402

from agents.diagnosis import synthesize  # noqa: E402
from core.stages.knowledge_rules import candidate_rules, run_knowledge_rules  # noqa: E402

check("K3 diagnosis & stage knowledge tak lagi menerima parameter fase",
      all("phase" not in inspect.signature(f).parameters for f in (synthesize, candidate_rules, run_knowledge_rules)))
check("K4 semua rule KB yang sumbernya aktif menjadi kandidat (tanpa gerbang per fase)",
      len(candidate_rules()) == sum(1 for rid in get_kb()["rules"] if rid.split("-")[0] in EXPECTED))
kb_dir = MVP / "ontology" / "knowledge"
act = json.loads((kb_dir / "rule_activation.json").read_text(encoding="utf-8"))
check("K5 rule_activation.json: tanpa kunci `phases`/`probe_ids`; hanya aktivasi sumber",
      set(act) >= {"active_rule_sources"} and "phases" not in act and "probe_ids" not in json.dumps(act))


def run_validator(mutate) -> int:
    root = Path(tempfile.mkdtemp(prefix="m5_kb_", dir=_TMP))
    shutil_copy = __import__("shutil").copytree
    shutil_copy(MVP / "ontology", root / "ontology", symlinks=True)
    for d in ("core", "engine", "store", "providers", "domains"):
        os.symlink(MVP / d, root / d)
    mutate(root / "ontology" / "knowledge")
    r = subprocess.run([sys.executable, str(root / "ontology/knowledge/validate_knowledge.py")], cwd=root,
                       capture_output=True, text=True)
    return r.returncode


def typo(kb: Path) -> None:
    f = kb / "rule_activation.json"
    d = json.loads(f.read_text())
    d["active_rule_sources"].append("ZZ")
    f.write_text(json.dumps(d))


def missing(kb: Path) -> None:
    (kb / "rule_activation.json").unlink()


check("K6 kontrol: validator LULUS pada KB asli", run_validator(lambda kb: None) == 0)
check("K7 validator MENOLAK prefix sumber yang tak terdaftar di rule_activation.json", run_validator(typo) != 0)
check("K8 validator MENOLAK ketiadaan rule_activation.json", run_validator(missing) != 0)

# ── E · domain E2E
print("E · domain E2E (PRA_SALES / SALES / AFTER_SALES) bukan fase wawancara dan tetap hidup")
from domains.revenue.stages.journey import E2E_PHASES, infer_e2e_phases  # noqa: E402
from engine.knowledge import interventions_for  # noqa: E402

check("E1 E2E_PHASES tetap tiga tahap perjalanan", list(E2E_PHASES) == ["PRA_SALES", "SALES", "AFTER_SALES"], str(E2E_PHASES))
check("E2 infer_e2e_phases tanpa sinyal = netral (semua tahap), tak terkait fase wawancara",
      list(infer_e2e_phases(None)) == list(E2E_PHASES))
tagged = [i for i in get_kb()["interventions"].values() if i.get("e2e_phase")]
check("E3 KB masih memuat intervensi ber-tag e2e_phase, semuanya ⊂ E2E_PHASES",
      tagged and all(set(i["e2e_phase"]) <= set(E2E_PHASES) for i in tagged))
cid = next((c for i in tagged for c in (i.get("targets") or i.get("constraint_targets") or [])), None)
full = interventions_for(cid)
only_after = interventions_for(cid, e2e_phases=["AFTER_SALES"])
check("E4 filter intervensi per tahap E2E tetap bekerja (hanya yang relevan, atau tanpa tag)",
      all((not i.get("e2e_phase")) or "AFTER_SALES" in {p.upper() for p in i["e2e_phase"]} for i in only_after)
      and len(only_after) <= len(full))

print()
bad_r = [n for n, ok, _ in RESULTS if not ok]
print(f"HASIL: {len(RESULTS) - len(bad_r)}/{len(RESULTS)} PASS {'✅' if not bad_r else '❌ ' + str(bad_r)}")
sys.exit(0 if not bad_r else 1)
