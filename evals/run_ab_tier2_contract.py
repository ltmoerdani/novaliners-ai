"""A/B test of the tier-2 output contract (verbose vs sparse) — USES the LLM, NOT part of the gate.

Answers two questions with evidence, not guesses (option A, 23 Sep 2026):

1. Does the SPARSE contract cut output & duration without sacrificing the
   matched set (recall proxy) on the SAME session evidence?
   → run the VERBOSE mode first (baseline), then SPARSE.
2. Is the hypothesis "retry = output truncated (finish_reason=length)" true?
   → see the WARNING logs `finish_reason=length` and
   `structured_call parse/validate GAGAL` ("FAILED", the literal log text) below
   (instrumentation installed in
   core/llm.py).

Data: evidence + transcript of a real session (store/sessions/01b9ad47cb85.json),
per group (SOURCE_GROUPS), same model & temperature (determinism mode).

Run from mvp/:
    .venv/bin/python evals/run_ab_tier2_contract.py

Revert the default contract: set KB_TIER2_SPARSE=0 (env / .env).
Integrity note: 1 run per contract = INDICATIVE (LLM variance), not a statistical
recall study. Treat diff results as signals to investigate, not definitive proof
of equivalence.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import time

# Bootstrap identical to evals/test_*.py — the script is run directly (not via -m),
# so sys.path[0] = the evals/ folder, not mvp/.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

# `load_dotenv` MUST run after logging setup (intent), not before it.
from dotenv import load_dotenv  # noqa: E402 — after logging setup (intent)

from core.schema.evidence import EvidenceItem  # noqa: E402
from core.stages.knowledge_rules import (  # noqa: E402
    SOURCE_GROUPS,
    _match_group,
    _tier2_sparse,
)
from engine.knowledge import get_kb  # noqa: E402
from llm.runtime import ENV_PATH, get_llm  # noqa: E402

load_dotenv(ENV_PATH, override=True)   # same as the app/main.py bootstrap

SESSION = pathlib.Path(__file__).resolve().parent.parent / "store" / "sessions" / "01b9ad47cb85.json"


def main() -> int:
    if not SESSION.exists():
        print(f"FAIL: sesi uji tidak ada: {SESSION}")
        return 1
    data = json.loads(SESSION.read_text(encoding="utf-8"))
    evidence = [EvidenceItem(**e) for e in (data.get("evidence") or [])]
    transcript = "\n".join(f"{r}: {t}" for r, t in (data.get("transcript") or [])[-12:])
    get_kb()   # pre-warm: the KB load cost must not be recorded as contract duration
    print(f"sesi={SESSION.stem} evidence={len(evidence)}", flush=True)

    llm = get_llm()
    llm.set_determinism(True)

    # ── 3 paired rounds (default; override: argv[1] or env AB_ROUNDS) ────────
    # Experiment design (A, 23 Sep 2026): each round runs BOTH contracts
    # on the SAME evidence, so two distinguishable signals exist:
    #   (a) diff verbose↔sparse  = CONTRACT EFFECT,
    #   (b) diff verbose↔verbose = NOISE FLOOR (control; LLM sampling is not
    #       deterministic even at temperature 0).
    # If (a) ≈ (b), the difference is noise — not a recall loss caused by the contract.
    # The contract order is swapped every round (controls time/gateway-load bias).
    rounds = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AB_ROUNDS", "3"))
    results: dict[tuple[str, int, int], dict] = {}   # (contract, round, group)
    for rnd in range(rounds):
        order = ("verbose", "sparse") if rnd % 2 == 0 else ("sparse", "verbose")
        for contract in order:
            os.environ["KB_TIER2_SPARSE"] = "0" if contract == "verbose" else "1"
            if _tier2_sparse() != (contract == "sparse"):
                print("FAIL: flag KB_TIER2_SPARSE tidak terbaca")
                return 1
            for gi, group in enumerate(SOURCE_GROUPS):
                t0 = time.monotonic()
                res, had = _match_group(llm, evidence, transcript, group)
                dt = time.monotonic() - t0
                matched = sorted(m.rule_id for m in (res.matches if res else []) if m.matched)
                results[(contract, rnd, gi)] = {
                    "dt": dt, "matched": set(matched), "had": had, "ok": res is not None,
                    "entries": len(res.matches) if res else 0,
                    "anti": len(res.anti_patterns) if res else 0,
                    "evaluated": len(getattr(res, "evaluated", None) or []) if res else 0,
                }
                r = results[(contract, rnd, gi)]
                print(
                    f"r{rnd + 1} [{contract:7}] grup{gi} ({'+'.join(group)}): {dt:5.1f}s "
                    f"entries={r['entries']:3d} anti={r['anti']:2d} "
                    f"matched={len(matched):2d} evaluated={r['evaluated']:3d} had={had}",
                    flush=True,
                )
    os.environ.pop("KB_TIER2_SPARSE", None)   # restore the sparse default

    def _runs(contract: str, gi: int) -> list[set[str]]:
        return [
            results[(contract, r, gi)]["matched"]
            for r in range(rounds) if (contract, r, gi) in results
        ]

    def _mean_sym(runs: list[set[str]]) -> float:
        ds = [len(a ^ b) for i, a in enumerate(runs) for b in runs[i + 1:]]
        return sum(ds) / len(ds) if ds else 0.0

    def _mean_cross(vs: list[set[str]], ss: list[set[str]]) -> float:
        ds = [len(v ^ s) for v in vs for s in ss]
        return sum(ds) / len(ds) if ds else 0.0

    print(f"\n=== {rounds}× A/B berpasangan — proxy recall (evidence identik) ===")
    stable_ok, noise_all, effect_all = True, [], []
    for gi, group in enumerate(SOURCE_GROUPS):
        V, S = _runs("verbose", gi), _runs("sparse", gi)
        if not V or not S:
            print(f"grup{gi}: data tidak lengkap (V={len(V)} S={len(S)})")
            continue
        v_core = set.intersection(*V)
        v_union = set.union(*V)
        s_core = set.intersection(*S)
        s_union = set.union(*S)
        nv, ns, cross = _mean_sym(V), _mean_sym(S), _mean_cross(V, S)
        noise_all += [nv, ns]
        effect_all.append(cross)
        recall_core = (len(v_core & s_union) / len(v_core)) if v_core else 1.0
        lost_stable = sorted(v_core - s_union)
        gained = sorted(s_union - v_union)
        lost_any = sorted(v_union - s_union)
        if lost_stable:
            stable_ok = False
        print(f"\ngrup{gi} ({'+'.join(group)})  [matched per run: "
              f"v={[len(x) for x in V]} s={[len(x) for x in S]}]")
        print(f"  stable-core verbose = {sorted(v_core)}")
        print(f"  stable-core sparse  = {sorted(s_core)}")
        print(f"  NOISE (rata-rata |Δ| sekontrak): v↔v={nv:.1f}  s↔s={ns:.1f}"
              f"   | EFEK (v↔s)={cross:.1f}")
        print(f"  recall stable-core verbose TERTANGKAP di sparse-union: {recall_core:.0%}"
              + (f"  ⚠ HILANG: {lost_stable}" if lost_stable else "  ✔ lengkap"))
        print(f"  pernah match HANYA di sparse  (gain) : {gained}")
        print(f"  pernah match HANYA di verbose (hilang): {lost_any}")

    tv = sum(results[("verbose", r, gi)]["dt"] for (c, r, gi) in results if c == "verbose")
    ts = sum(results[("sparse", r, gi)]["dt"] for (c, r, gi) in results if c == "sparse")
    n_avg = sum(noise_all) / len(noise_all) if noise_all else 0.0
    e_avg = sum(effect_all) / len(effect_all) if effect_all else 0.0
    print(f"\nTOTAL wall {rounds}×: verbose {tv:.1f}s vs sparse {ts:.1f}s "
          f"({(1 - ts / tv) * 100:.0f}% lebih cepat)" if tv > 0 else "")
    print(f"Rata-rata NOISE={n_avg:.2f} vs EFEK={e_avg:.2f} (ukuran: rata-rata |Δmatched|)")
    if not stable_ok:
        print("⚠ VERDICT: stable-core verbose TIDAK tertangkap sparse → "
              "JANGAN kunci kontrak sparse; selidiki dulu.")
        return 2
    if e_avg <= n_avg * 1.25:
        print("✔ VERDICT: stable-core terjaga & EFEK ≤ 1,25× NOISE → "
              "beda antar-kontrak tidak signifikan thd sampling. "
              "Kontrak sparse layak dikunci.")
        return 0
    print("⚠ VERDICT: stable-core terjaga TAPI EFEK > 1,25× NOISE → "
          "ada beda sistematis; selidiki sebelum kunci kontrak.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
