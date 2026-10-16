"""R7 — LIVE smoke of so.v1 (3 turns) + nm.v2 reasoning with a REAL provider from .env (Z.ai).

NOT part of make gate-fast (it burns quota). Run manually / after the quota recovers:
    cd mvp && .venv/bin/python evals/run_live_so_smoke.py [--provider vertex]

All stores are redirected to a temporary directory; API keys are never printed. Output: a JSON report
(`traces/live/so-smoke-<ts>.json`) with the proper failure layers — connectivity alone is NOT a
semantic pass.

Layers: provider | schema | source_verification | semantic | revision | persistence | decision.
Final status: LIVE_VERIFIED (all layers pass) | LIVE_FAILED (a semantic/contract failure) |
BLOCKED_EXTERNAL (429/1308/401).
No mock result is ever presented as live.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TMP = Path(tempfile.mkdtemp(prefix="nvl-live-so-"))

import store.adjudication_ledger as ledger  # noqa: E402
import store.events as event_store  # noqa: E402

event_store.EVENTS_DIR = TMP / "events"
ledger._LEDGER_ROOT = TMP / "ledger"

import app.turn as turn_mod  # noqa: E402
from llm.runtime import build_llm  # noqa: E402
from store.memory import Session, SessionStore, store  # noqa: E402

store.PERSIST_DIR = TMP / "sessions"
SessionStore.PERSIST_DIR = TMP / "sessions"

TURNS = [
    # T1: a desire with no target number; working-hours facts; family context
    "Saya ingin punya lebih banyak waktu untuk keluarga, tapi bisnis desain saya makin sepi. "
    "Sekarang saya kerja sekitar 60 jam seminggu.",
    # T2: assumption + behavior + feelings + historical/current quantities
    "Sepertinya masalahnya di marketing. Tapi sebenarnya saya jarang follow-up orang yang sudah tanya, karena saya "
    "merasa tidak enak mengganggu. Bulan lalu omzet sekitar 12 juta, dulu pernah 30 juta.",
    # T3: correction + upper bound + target range
    "Ralat, bulan lalu bukan 12 juta, paling banyak 9 juta. Target saya sekitar 20 sampai 25 juta per bulan.",
]

results: list[dict] = []
usage: list[dict] = []


def rec(layer: str, name: str, ok: bool, detail: str = "") -> None:
    results.append({"layer": layer, "check": name, "ok": bool(ok), "detail": detail[:300]})
    print(f"  {'OK ' if ok else 'GAGAL'} [{layer}] {name}{(' — ' + detail[:160]) if (detail and not ok) else ''}")


def instrument(llm):
    """Record latency + tokens per call (without changing behavior)."""
    client = getattr(llm, "client", None)
    if client is None:
        return
    orig = client.chat.completions.create

    def wrapped(*a, **k):
        t0 = time.time()
        r = orig(*a, **k)
        u = getattr(r, "usage", None)
        usage.append({"latency_s": round(time.time() - t0, 2),
                      "prompt_tokens": getattr(u, "prompt_tokens", None),
                      "completion_tokens": getattr(u, "completion_tokens", None)})
        return r
    client.chat.completions.create = wrapped


def blocked(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}"
    return any(x in s for x in ("429", "1308", "RateLimit", "AuthenticationError", "401"))


def finish(status: str, extra: dict | None = None) -> int:
    out = TMP.parent / f"nvl-live-so-report-{int(time.time())}.json"
    rep = {"status": status, "ts_wib": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results, "usage": usage,
           "totals": {"calls": len(usage), "latency_s": round(sum(u["latency_s"] for u in usage), 1),
                      "prompt_tokens": sum(u["prompt_tokens"] or 0 for u in usage),
                      "completion_tokens": sum(u["completion_tokens"] or 0 for u in usage)}, **(extra or {})}
    traces = Path(__file__).resolve().parents[1] / "traces" / "live"
    traces.mkdir(parents=True, exist_ok=True)
    (traces / out.name).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"\nSTATUS: {status}  | panggilan={rep['totals']['calls']} laporan={traces / out.name}")
    return {"LIVE_VERIFIED": 0, "LIVE_FAILED": 1, "BLOCKED_EXTERNAL": 3}[status]


def main() -> int:
    provider = "vertex"
    if "--provider" in sys.argv:
        provider = sys.argv[sys.argv.index("--provider") + 1]
    llm = build_llm(provider)
    if getattr(llm, "name", "") == "mock":
        print("Menolak: provider mock bukan bukti LIVE.")
        return 2
    llm.set_determinism(True)
    instrument(llm)
    print(f"provider={llm.name} model={getattr(llm, 'model', '?')}")
    try:
        llm.raw_json("Return JSON only.", '{"ping":"ok"} -> echo {"answer":"OK"}')
        rec("provider", "konektivitas", True)
    except Exception as exc:  # noqa: BLE001
        rec("provider", "konektivitas", False, f"{type(exc).__name__}: {str(exc)[:160]}")
        return finish("BLOCKED_EXTERNAL" if blocked(exc) else "LIVE_FAILED", {"error": f"{type(exc).__name__}"})

    s = Session(id="livesmoke01", goal_text="bisnis desain saya makin sepi", language="id", user_id="")
    from domains.revenue.schema.goal import build_goal
    s.goal = build_goal(s.goal_text, desire="").model_dump()
    llm.use_session(s.id)
    snapshots: list[dict] = []
    for i, text in enumerate(TURNS, 1):
        try:
            resp = turn_mod.run_turn(s, llm, text, idempotency_key=f"live-smoke-{i}")
        except Exception as exc:  # noqa: BLE001
            rec("provider" if blocked(exc) else "schema", f"T{i} giliran selesai", False,
                f"{type(exc).__name__}: {str(exc)[:200]}")
            return finish("BLOCKED_EXTERNAL" if blocked(exc) else "LIVE_FAILED", {"failed_turn": i})
        ev = [e for e in s.events if e["role"] == "user"][-1]
        rec("schema", f"T{i} observasi lolos skema so.v1 (status event {ev['status']})",
            ev["status"] == "committed", ev.get("processing_note", ""))
        note = ev.get("processing_note", "")
        rec("verifikasi_sumber", f"T{i} tidak ada kutipan ditolak verifier", "verifier_rejected" not in note, note)
        snapshots.append({"graph": json.loads(json.dumps(s.state_graph)), "resp": resp.model_dump(),
                          "goal": json.loads(json.dumps(s.goal))})
        ad = s.planner_log[-1].get("adaptive", {})
        pr = s.planner_log[-1].get("presented", {})
        rec("keputusan", f"T{i} penalaran nm.v2 DITERIMA guard (bukan degraded)", ad.get("status") == "ACCEPTED",
            f"{ad.get('status')} {ad.get('reason', '')} {json.dumps(ad.get('attempts', [])[-1:], ensure_ascii=False)[:200]}")
        print(f"      langkah: {pr.get('kind')} | {str(pr.get('text'))[:120]}")

    nodes = lambda g: list((g["nodes"]).values())  # noqa: E731
    g1, g2 = snapshots[0]["graph"], snapshots[1]["graph"]
    n1, n2 = nodes(g1), nodes(g2)
    # ── T1 ──
    rec("semantik", "T1 keinginan (desire) tertangkap", any(n["type"] == "desire" for n in n1))
    rec("semantik", "T1 TIDAK ada Goal bernilai karangan (tak ada klaim goal berangka rupiah)",
        not any(n["type"] == "goal" and (n.get("quantity") or {}).get("unit", "").lower() in ("juta", "jt", "rp")
                for n in n1))
    rec("semantik", "T1 jam kerja 60/minggu terekam sebagai kuantitas",
        any(((n.get("quantity") or {}).get("value") == 60) for n in n1))
    from domains.revenue.schema.goal import Goal as _Goal
    g1_goal = _Goal(**snapshots[0]["goal"])
    rec("semantik", "T1 Goal sesi tanpa target & tanpa metric karangan setelah giliran 1",
        g1_goal.target is None and g1_goal.target_origin == "none", f"target={g1_goal.target} origin={g1_goal.target_origin}")
    # ── T2 ──
    rec("semantik", "T2 asumsi 'marketing' bertipe assumption", any(n["type"] == "assumption" for n in n2))
    rec("semantik", "T2 perilaku jarang follow-up terekam (aspek behavior/concern)",
        any(n.get("aspect") in ("behavior", "concern") for n in n2 if n["id"] not in {x["id"] for x in n1}))
    twelve = [n for n in n2 if (n.get("quantity") or {}).get("value") == 12]
    thirty = [n for n in n2 if (n.get("quantity") or {}).get("value") == 30]
    # Erratum 15 Oct 2026 (owner decision): the old assertion demanded a `different tense`, but
    # "bulan lalu" (last month) and "dulu" (in the past) are BOTH past (enum Tense: now/past/future
    # — no tense can contrast here). The material meaning = TWO separate claims (12M last
    # month vs 30M historical), not a tense contrast. The 14 Oct run result STAYS LIVE_FAILED
    # (not applied retroactively); the check change is recorded in 08-real-provider-evaluation.md.
    rec("semantik", "T2 12 juta (bulan lalu) dan 30 juta (dulu) terekam sebagai DUA klaim terpisah",
        bool(twelve) and bool(thirty) and twelve[0]["id"] != thirty[0]["id"],
        f"tense={[(n.get('tense')) for n in twelve + thirty]} (keduanya sah past — erratum 15 Okt 2026)")
    # ── T3 ──
    final = s.state_graph["nodes"]
    old12 = next((n for n in final.values() if (n.get("quantity") or {}).get("value") == 12), None)
    rec("revisi", "T3 klaim 12 juta DIGANTIKAN (superseded), sejarah utuh",
        old12 is not None and old12.get("status") in ("superseded", "negated"), str(old12 and old12.get("status")))
    nine = [n for n in final.values() if (n.get("quantity") or {}).get("value") == 9]
    rec("semantik", "T3 'paling banyak 9 juta' bertipe batas (at_most/less_than), BUKAN eksak",
        bool(nine) and nine[0]["quantity"]["value_kind"] in ("at_most", "less_than"),
        str([n["quantity"] for n in nine]))
    rng = [n for n in final.values() if (n.get("quantity") or {}).get("value_kind") == "range"]
    rec("semantik", "T3 target 20–25 terekam sebagai RENTANG", bool(rng) and (rng[0]["quantity"].get("low"), rng[0]["quantity"].get("high")) == (20, 25),
        str([n["quantity"] for n in rng]))
    edges = s.state_graph["edges"].values()
    rec("revisi", "T3 edge supersede/koreksi tercatat", any(e["kind"] == "supersede" for e in edges))
    from domains.revenue.schema.goal import Goal
    g = Goal(**s.goal)
    rec("semantik", "Goal akhir: tidak ada angka eksak karangan; rentang → min/max, tentatif (bukan terkonfirmasi)",
        g.target is None and not g.confirmed_target(), f"target={g.target} min={g.target_min} max={g.target_max} origin={g.target_origin}")
    from app.turn import _sync_evidence_currency  # noqa: F401
    from core.schema.evidence import current_evidence
    from domains.revenue.navigation.live import derive_revenue_state
    utext = "\n".join(f"user: {t}" for r, t in s.transcript if r == "user")
    rs = derive_revenue_state(current_evidence(s.evidence), s.goal_text, utext, s.state_graph)
    rec("semantik", "RevenueState: batas 'paling banyak 9' tidak menjadi omzet saat ini eksak", rs.current_monthly in (None,) or rs.current_monthly != 12.0,
        str(rs.current_monthly))
    # ── persistence ──
    store.save_strict(s)
    re = SessionStore().get(s.id)
    rec("persistensi", "reload dari disk: graph + hipotesis + log keputusan identik",
        re is not None and re.state_graph == s.state_graph and re.hypotheses == s.hypotheses
        and len(re.planner_log) == len(s.planner_log))
    bad = [r for r in results if not r["ok"]]
    return finish("LIVE_VERIFIED" if not bad else "LIVE_FAILED",
                  {"failed_layers": sorted({r["layer"] for r in bad}), "model": getattr(llm, "model", "")})


if __name__ == "__main__":
    raise SystemExit(main())
