"""Human-language explanation quality with a REAL LLM (manual, consumes provider quota; not in any gate).

  LLM_PROVIDER=vertex .venv/bin/python evals/eval_explain_quality.py 88137f696776 5a999bfde4cc ...

Prints output + readability metrics per session from store/sessions. Does not write to sessions.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")

from agents.explain import build_pack, explain_session  # noqa: E402
from domains.revenue.guards.plain_language import check_explain, sentences  # noqa: E402
from llm.runtime import get_llm  # noqa: E402
from store.memory import store  # noqa: E402

FIELDS = ("blocking_title", "blocking_body", "do_title", "do_why", "done_when", "hold_title", "hold_body")


def show(sid: str) -> dict:
    s = store.get(sid)
    if not s or not s.diagnosis:
        print(f"{sid}: no diagnosis")
        return {}
    llm = get_llm()
    llm.use_session(s.id)
    started = time.time()
    ex = explain_session(llm, s)
    print(f"\n===== {sid} | {s.goal_text[:70]} | {time.time() - started:.0f}s | "
          f"model {ex['model']} | dropped {ex['dropped']}")
    for para in ex["summary"]:
        print("\nSUMMARY:", para)
    for k in FIELDS:
        print(f"\n{k}: {ex.get(k)}")
    for w in ex["why"]:
        print("why:", w)
    texts = [ex.get(k) or "" for k in FIELDS] + ex["summary"] + ex["why"]
    counts = [len(x.split()) for t in texts for x in sentences(t)]
    avg = sum(counts) / max(len(counts), 1)
    words = sum(len(p.split()) for p in ex["summary"])
    guard = check_explain(ex, build_pack(s)[1]) or "clean"
    print(f"\nreadability: {len(counts)} sentences, avg {avg:.1f} words, max {max(counts or [0])}; "
          f"summary {words} words; guard now: {guard}")
    return ex


if __name__ == "__main__":
    for session_id in sys.argv[1:]:
        show(session_id)
