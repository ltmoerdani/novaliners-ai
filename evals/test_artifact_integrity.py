"""Eval artifact integrity — freshness gate + KB fingerprint (era-7, internal-docs §9).

Background: the claim "DoD 19/19 post-i18n" once stood on an artifact with mtime
10:54 while the i18n commit was made at 12:12. Its detector: `rules_enabled` 34 (KB
iter-21) vs 46 (KB iter-22) — falsifiable coverage turned out to work as a
KB VERSION FINGERPRINT.

This util provides:
  - kb_fingerprint()      → dict {rules_enabled, item_count, sources, sha256}
  - stamp_artifact()      → embed fingerprint + timestamp into the artifact
  - verify_artifact_fresh() → True when the artifact still matches the current KB
  - require_fresh()       → raise SystemExit when stale (used by verification scripts)

Deterministic, no LLM. Run: .venv/bin/python evals/test_artifact_integrity.py
"""

import glob
import hashlib
import json
import sys
import time

sys.path.insert(0, ".")

KB_DIR = "ontology/knowledge"
RULES_ENABLED_BY_ERA = {
    34: "iter-21 (6 sumber, 134 item)",
    46: "iter-22 (10 sumber, 181 item)",
    52: "f2 kb-depth (10 sumber, 199 item) — internal-docs Fase 2",
    61: "f2b kb-depth (10 sumber, 209 item, known_thin=0) — internal-docs Fase 2 iter-2",
}

FAILS: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"{'✅' if ok else '❌'} {label}: got={got!r}")
    if not ok:
        FAILS.append(label)


def kb_fingerprint() -> dict:
    """KB fingerprint: rule/probe counts + deterministic hash of all JSON files."""
    h = hashlib.sha256()
    n_rules = n_items = 0
    sources: set[str] = set()
    for path in sorted(glob.glob(f"{KB_DIR}/*.json")):
        raw = open(path, "rb").read()
        h.update(path.encode())
        h.update(raw)
        d = json.loads(raw)
        for cat in ("probes", "evidence_rules", "anti_patterns", "interventions"):
            n = len(d.get(cat, []))
            n_items += n
            if cat == "evidence_rules":
                n_rules += n
        for s in d.get("sources", []):
            sources.add(s["source_id"])
    return {
        "rules_enabled": n_rules,
        "item_count": n_items,
        "sources": sorted(sources),
        "sha256": h.hexdigest()[:16],
    }


def stamp_artifact(artifact: dict) -> dict:
    """Embed kb_fingerprint + created_at into the artifact (called before dump)."""
    artifact["kb_fingerprint"] = kb_fingerprint()
    artifact["created_at_epoch"] = round(time.time(), 3)
    return artifact


def verify_artifact_fresh(artifact: dict) -> tuple[bool, str]:
    """An artifact is stale when its KB fingerprint ≠ the current KB."""
    fp = artifact.get("kb_fingerprint")
    if not fp:
        return False, "artefak tanpa kb_fingerprint (dibuat sebelum era-7)"
    now = kb_fingerprint()
    if fp.get("sha256") != now["sha256"]:
        era = RULES_ENABLED_BY_ERA.get(fp.get("rules_enabled"), f"rules={fp.get('rules_enabled')}")
        return False, (
            f"artefak basi — dibuat dengan KB lain ({era}); "
            f"KB saat ini rules={now['rules_enabled']}, sha={now['sha256']}"
        )
    return True, f"fresh (rules={now['rules_enabled']}, sha={now['sha256']})"


def require_fresh(path: str) -> dict:
    """Load the artifact and hard-reject when stale. Used by verification scripts."""
    d = json.load(open(path, encoding="utf-8"))
    ok, reason = verify_artifact_fresh(d)
    if not ok:
        print(f"❌ ARTEFAK BASI ({path}): {reason}")
        print("   → jalankan ulang eval terkait sebelum mempercayai artefak ini.")
        raise SystemExit(1)
    print(f"✅ artefak fresh ({path}): {reason}")
    return d


# ================= SELF-TEST =================
fp = kb_fingerprint()
print(f"KB fingerprint: rules={fp['rules_enabled']} items={fp['item_count']} "
      f"sources={len(fp['sources'])} sha={fp['sha256']}")

check("rules_enabled = 61 (pasca F2b kb-depth, internal-docs)", fp["rules_enabled"], 61)
check("item_count = 209", fp["item_count"], 209)
check("sources = 11 (10 L1-L3 + chasm L2-only, 0 item L3 — verdict owner 27 Sep, int 09 §9.5)",
      len(fp["sources"]), 11)
check("fingerprint deterministik", kb_fingerprint() == fp, True)

# stamped artifact → fresh
art = {"status": "final"}
stamp_artifact(art)
ok, reason = verify_artifact_fresh(art)
check("stamped artefak → fresh", ok, True)

# artifact without a stamp → stale
ok, _ = verify_artifact_fresh({"status": "final"})
check("artefak tanpa fingerprint → ditolak", ok, False)

# simulate a stale artifact: fingerprint from an 'old KB' (fingerprint altered)
stale = {"kb_fingerprint": {**fp, "sha256": "0" * 16, "rules_enabled": 34}}
ok, reason = verify_artifact_fresh(stale)
check("artefak KB lama → ditolak", ok, False)
print(f"   alasan: {reason}")

# real artifact in the repo (when present): must be fresh OR explicitly flagged stale
try:
    d = json.load(open("eval_dod_smoke_result.json", encoding="utf-8"))
    ok, reason = verify_artifact_fresh(d)
    print(f"{'✅' if ok else '⚠️ '} eval_dod_smoke_result.json: {reason}")
except FileNotFoundError:
    print("ℹ️  eval_dod_smoke_result.json belum ada — skip")

print()
if FAILS:
    print(f"GAGAL: {len(FAILS)} kasus — {FAILS}")
    sys.exit(1)
print("SEMUA KASUS INTEGRITAS ARTEFAK LULUS ✅")
