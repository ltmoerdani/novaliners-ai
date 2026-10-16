"""GATE LIVE #5 — D-A2 layer C end-to-end with a REAL provider from .env (Z.ai).

A short catering session (English, one dense turn) through the PRODUCTION path: run_turn → semantic
observation → evidence → run_live_adjudication(llm=vertex) → layer C (REAL second-pass verifier) →
ledger.

NOT part of make gate-fast (it burns quota). Run manually:
    cd mvp && .venv/bin/python evals/run_live_second_pass.py [--provider vertex]

All stores are redirected to a temporary directory; API keys are never printed. Output: a JSON report
`traces/live/second-pass-<ts>.json`.

Status: LIVE_VERIFIED (live chain: real calls > 0, BC-03 audit complete, no exception; the verified
count is recorded AS-IS — the verifier may honestly answer none) | BLOCKED_EXTERNAL (429/401) |
LIVE_FAILED. No mock result is ever presented as live.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TMP = Path(tempfile.mkdtemp(prefix="nvl-live-sp-"))

import store.adjudication_ledger as ledger  # noqa: E402
import store.events as event_store  # noqa: E402

event_store.EVENTS_DIR = TMP / "events"
ledger._LEDGER_ROOT = TMP / "ledger"

import app.turn as turn_mod  # noqa: E402
from llm.runtime import build_llm  # noqa: E402
from store.memory import Session, SessionStore, store  # noqa: E402

store.PERSIST_DIR = TMP / "sessions"
SessionStore.PERSIST_DIR = TMP / "sessions"

USER = "u-live-secondpass"

# Short catering session — quantity-dense + pricing basis + a quote event
# (a natural prose-requirement trigger).
STORY = (
    "I run a daily catering business. Revenue is about IDR 12 million a month from office subscriptions, "
    "around 3 offices. I want to grow to IDR 25 million within 2 months. Office subscriptions are rice box, "
    "daily, around IDR 25k per box, minimum 20 boxes per office. For events, it depends, I quote per order "
    "after they tell me the budget and headcount."
)

results: list[dict] = []
usage: list[dict] = []


def rec(layer: str, name: str, ok: bool, detail: str = "") -> None:
    results.append({"layer": layer, "check": name, "ok": bool(ok), "detail": detail[:400]})
    print(f"  {'OK ' if ok else 'GAGAL'} [{layer}] {name}{(' — ' + detail[:180]) if (detail and not ok) else ''}")


def instrument(llm) -> None:  # noqa: ANN001 — record latency/token without changing behavior
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
    rep = {"status": status, "ts_wib": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results,
           "usage_totals": {"calls": len(usage),
                            "latency_s": round(sum(u["latency_s"] for u in usage), 1)},
           **(extra or {})}
    traces = Path(__file__).resolve().parents[1] / "traces" / "live"
    traces.mkdir(parents=True, exist_ok=True)
    out = traces / f"second-pass-{int(time.time())}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"\nSTATUS: {status}  | panggilan={rep['usage_totals']['calls']} laporan={out}")
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
        llm.raw_json("Return JSON only.", 'echo {"answer":"OK"}')
        rec("provider", "konektivitas", True)
    except Exception as exc:  # noqa: BLE001
        rec("provider", "konektivitas", False, f"{type(exc).__name__}: {str(exc)[:160]}")
        return finish("BLOCKED_EXTERNAL" if blocked(exc) else "LIVE_FAILED")

    s = Session(id="livesp01", goal_text="grow my catering business", language="en", user_id=USER)
    from domains.revenue.schema.goal import build_goal
    s.goal = build_goal(s.goal_text, desire="").model_dump()
    llm.use_session(s.id)

    try:
        resp = turn_mod.run_turn(s, llm, STORY, idempotency_key="live-sp-1")
    except Exception as exc:  # noqa: BLE001
        rec("provider" if blocked(exc) else "pipeline", "giliran selesai tanpa exception", False,
            f"{type(exc).__name__}: {str(exc)[:240]}")
        return finish("BLOCKED_EXTERNAL" if blocked(exc) else "LIVE_FAILED")

    rec("pipeline", "giliran selesai tanpa exception (layer C tidak menjatuhkan giliran)", True)
    rec("pipeline", "respons engine tersaji", bool(resp and resp.next_move), "")

    adj = s.last_adjudication or {}
    sp = adj.get("second_pass") or {}
    rec("layer_c", "ringkasan second_pass hadir di last_adjudication", bool(sp),
        json.dumps({k: v for k, v in adj.items() if k in ("proposed", "verified", "unresolved")}, ensure_ascii=False)[:200])
    rec("layer_c", "panggilan LLM verifier NYATA > 0", int(sp.get("llm_calls", 0)) > 0,
        f"llm_calls={sp.get('llm_calls')}")
    audit = sp.get("audit") or []
    rec("audit", "audit BC-03 terisi (claim/event/quote/fingerprint/model/waktu)",
        bool(audit) and all(a.get("provider_model") and a.get("prompt_contract") and a.get("verified_at")
                            for a in audit), f"{len(audit)} verdict")
    models = sorted({a.get("provider_model", "") for a in audit})
    verified_audit = [a for a in audit if a.get("outcome") == "verified"]
    rec("audit", "provider/model tercatat (bukan mock)", all(m and "mock" not in m.lower() for m in models if m),
        str(models))
    rec("layer_c", "verdict verified>0 (dicatat apa adanya; none juga sah)",
        len(verified_audit) > 0, f"verified={len(verified_audit)} dari {len(audit)} verdict")

    # ledger: only prose requirements that pass REAL verification may be written
    for a in (adj.get("adjudicated") or []):
        print(f"      adjudicated: {a['requirement_id']} -> {a['status']} ({a.get('method')}) written={a['written']}")
    negative_ok = True
    for rid in ("access.icp", "offering.differentiation"):
        entry = ledger.latest_entry(USER, rid)
        if entry is not None and entry["adjudication"]["status"] != "UNKNOWN":
            negative_ok = False
    rec("negative", "access.icp & offering.differentiation TIDAK dikarang (BC-01 negative tetap berlaku live)",
        negative_ok)

    ok_all = all(r["ok"] for r in results)
    return finish("LIVE_VERIFIED" if ok_all else "LIVE_FAILED",
                  {"second_pass": {k: sp.get(k) for k in ("llm_calls", "verified", "unit_contexts")},
                   "adjudicated": adj.get("adjudicated"), "unresolved": adj.get("unresolved")})


if __name__ == "__main__":
    sys.exit(main())
