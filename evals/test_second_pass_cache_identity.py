"""S1 — second-pass cache identity: a verdict must NOT cross model/provider/prompt boundaries.

Contract proven (audit int 20 §S1; int 19 model-switch):
  C1  cold: the first call = 1 LLM call.
  C2  warm same identity: replay (another instance, same name/model) = 0 calls; identical verdict.
  C3  MODEL SWITCH: model A's verdict is NOT served to model B (miss + B's verdict actually used).
  C4  PROVIDER SWITCH (different name, same model): miss — the key carries the full identity.
  C5  the PROMPT CONTRACT version is part of the key (version change = miss).
  C6  evidence CORRECTION/SUPERSESSION: a now-superseded candidate is NEVER admitted from a warm
      cache (no stale PRESENT).
  C7  telemetry: elapsed_s/llm_elapsed_s exist and are consistent (llm_elapsed_s <= elapsed_s when a
      call happens).

Run: .venv/bin/python evals/test_second_pass_cache_identity.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from core.schema.evidence import EvidenceItem  # noqa: E402
from engine.requirements import load_registry  # noqa: E402
from ontology.mapper import second_pass  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail and not ok else ""), flush=True)


class ScriptedVerifier:
    """Deterministic verifier with a mutable (name, model) identity; verdict per rid."""

    def __init__(self, name: str, model: str, checks: dict[str, list[dict[str, Any]]] | None = None):
        self.name = name
        self.model = model
        self.checks = checks or {}
        self.calls = 0

    def structured_call(self, schema, system, user, retries: int = 0):  # noqa: ANN001
        self.calls += 1
        m = re.search(r"^REQUIREMENT (\S+)", user, re.M)
        rid = m.group(1) if m else ""
        return schema.model_validate(
            {"contract_version": "spv.v1", "requirement_id": rid, "claim_checks": self.checks.get(rid, [])})


def ev(i: str, text: str, *, superseded: bool = False) -> EvidenceItem:
    return EvidenceItem(id=i, signal=text, source_quote=text, level="self_reported", topic="CLAIM",
                        claim_role="claim", epistemic="reported", admissible=True, superseded=superseded)


PRICE_EN = "Office subscriptions are rice box, daily, around IDR 25k per box"
RID = "commercial.pricing_basis"
ENTRIES = list(load_registry().values())
PROPOSALS = [{"proposed_by": "mapper_deterministic_v1", "requirement_id": RID,
              "evidence_refs": ["e1"], "proposed_at": 1}]
SUFFICIENT = [{"evidence_ref": "e1", "quote": "around IDR 25k per box", "branch": "sufficient",
               "unit_key": None, "basis": "harga per box diakui"}]
CONTRADICTING = [{"evidence_ref": "e1", "quote": "around IDR 25k per box", "branch": "contradicting",
                  "unit_key": None, "basis": "menyangkal anggapan harga"}]


def run(llm: ScriptedVerifier, index: dict[str, Any]) -> dict[str, Any]:
    return second_pass.verify_second_pass(PROPOSALS[:], ENTRIES, index, llm=llm, fingerprint="fp-cache-id",
                                          now=1_700_000_000)


print("C1/C2 · cold lalu warm identitas sama")
second_pass.clear_cache()
index = {"e1": ev("e1", PRICE_EN)}
llm_a = ScriptedVerifier("prov-a", "model-a", {RID: SUFFICIENT})
r1 = run(llm_a, index)
check("C1 cold = tepat 1 panggilan LLM + verdict terbentuk",
      llm_a.calls == 1 and len(r1["verified_mappings"]) == 1, f"calls={llm_a.calls}")
check("C7 elapsed_s/llm_elapsed_s tersedia dan konsisten (llm <= total)",
      isinstance(r1.get("elapsed_s"), (int, float)) and isinstance(r1.get("llm_elapsed_s"), (int, float))
      and r1["llm_elapsed_s"] <= r1["elapsed_s"] + 0.01,
      f"elapsed={r1.get('elapsed_s')} llm={r1.get('llm_elapsed_s')}")

llm_a2 = ScriptedVerifier("prov-a", "model-a", {RID: CONTRADICTING})  # DIFFERENT verdict, SAME identity
r2 = run(llm_a2, index)
check("C2 warm identitas sama = 0 panggilan (verdict model A dipakai, bukan script baru)",
      llm_a2.calls == 0 and bool(r2["rule_evaluations"][RID]["sufficient"])
      and not r2["rule_evaluations"][RID]["contradicting"], f"calls={llm_a2.calls}")

print("C3 · ganti model WAJIB miss + verdict model baru")
llm_b = ScriptedVerifier("prov-a", "model-b", {RID: CONTRADICTING})
r3 = run(llm_b, index)
check("C3 model berbeda -> 1 panggilan (TIDAK memakai cache model A)",
      llm_b.calls == 1, f"calls={llm_b.calls}")
check("C3b verdict model B benar-benar dipakai (contradicting, bukan sufficient model A)",
      bool(r3["rule_evaluations"][RID]["contradicting"])
      and not r3["rule_evaluations"][RID]["sufficient"], str(r3["rule_evaluations"].get(RID)))

print("C4 · ganti provider (name beda, model sama) WAJIB miss")
llm_c = ScriptedVerifier("prov-other", "model-b", {RID: SUFFICIENT})
r4 = run(llm_c, index)
check("C4 provider berbeda -> 1 panggilan (identitas provider ikut kunci)", llm_c.calls == 1,
      f"calls={llm_c.calls}")

print("C5 · versi kontrak prompt ikut kunci (via _claim_cache_key + digest)")
cands = [(eid, ev_, second_pass._node_of(None, ev_)) for eid, ev_ in index.items()]
K = second_pass._claim_cache_key
PD = second_pass._prompt_digest
k_v1 = K("fp-cache-id", RID, "e1", "prov-a:model-a", PD())
k_v2 = K("fp-cache-id", RID, "e1", "prov-a:model-a", PD() + "v2")  # prompt contract lain
k_model = K("fp-cache-id", RID, "e1", "prov-a:model-b", PD())
check("C5a prompt_contract berbeda -> kunci berbeda", k_v1 != k_v2)
check("C5b model_identity berbeda -> kunci berbeda", k_v1 != k_model)
check("C5c kunci = tuple deterministik (fingerprint, rid, evidence, model, digest)",
      k_v1 == K("fp-cache-id", RID, "e1", "prov-a:model-a", PD()))

print("C6 · koreksi/supersesi tidak membaca cache basi")
second_pass.clear_cache()
llm_d = ScriptedVerifier("prov-a", "model-a", {RID: SUFFICIENT})
r_ok = run(llm_d, {"e1": ev("e1", PRICE_EN)})
check("C6a baseline admissible -> verified", len(r_ok["verified_mappings"]) == 1)
llm_e = ScriptedVerifier("prov-a", "model-a", {RID: SUFFICIENT})
r_sup = run(llm_e, {"e1": ev("e1", PRICE_EN, superseded=True)})
check("C6b evidence kini superseded -> TIDAK verified, TIDAK membaca cache basi (0 panggilan)",
      not r_sup["verified_mappings"] and llm_e.calls == 0
      and any(u["reason"] == "claim_not_current" for u in r_sup["unresolved"]),
      f"verified={len(r_sup['verified_mappings'])} calls={llm_e.calls}")

print()
failed = [r for r in RESULTS if not r[1]]
print(f"{'❌ FAIL' if failed else '✅ PASS'} · {len(RESULTS) - len(failed)}/{len(RESULTS)}")
for name, _ok, detail in failed:
    print(f"   ❌ {name}: {detail[:200]}")
sys.exit(1 if failed else 0)
