"""Universal readiness: Requirement Registry = single source, Presentation = language layer,
Readiness = projection.

Proves the architectural invariants (internal-docs §Requirement, §Readiness):
  - every registry requirement that appears on a route can be presented by Readiness, with no second
    dictionary;
  - a NEW requirement (absent from the presentation pack, absent from the code) is still projected,
    readable (deterministic fallback), and usable as a narrative-claim anchor — no readiness code touched;
  - no REQ_EN / GATE_REQ / string-gate mapping in code; identity = requirement_id / check_id;
  - applicability, satisfaction, executability stay three separate axes; UNKNOWN != ABSENT.
Deterministic, 0 LLM. Run: .venv/bin/python evals/test_readiness_universal.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, ".")

import engine.requirements as req_mod  # noqa: E402
from core.navigation.claims import ground_claim  # noqa: E402
from core.navigation.presentation import humanize_id, resolve_presentation  # noqa: E402
from domains.revenue.guards.readiness_grounding import check_grounding  # noqa: E402
from domains.revenue.projection.readiness import build_readiness_projection  # noqa: E402
from evals.navigation_fixtures import (  # noqa: E402
    check_row,
    diagnosis_with,
    node,
    pathset,
    pp,
    routes_of,
)
from ontology.route.strategies import active_template_library  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


def proj_of(pset: dict, routes: dict | None = None, **kw) -> dict:
    return build_readiness_projection(diagnosis_with(pset), routes, **kw)


P = "path.demo_strategy"
registry = req_mod.load_registry()
pack = req_mod.load_presentation_pack()

# ── 1. Requirement universality: EVERY registry requirement projected, in all four states ─────────
all_ids = sorted(registry)
for state in ("PRESENT", "PARTIAL", "UNKNOWN", "ABSENT"):
    nodes = [node(rid, state, nid=f"n{i}") for i, rid in enumerate(all_ids)]
    pr = proj_of(pathset(pp("demo_strategy", "SUPPORTED")), routes_of(demo_strategy=nodes))
    items = pr["paths"][0]["items"]
    ok = (
        len(items) == len(all_ids)
        and {i["key"] for i in items} == set(all_ids)
        and all(i["state"] == state for i in items)
        and all(i["title"]["text"] and i["title"]["lang"] for i in items)
    )
    check(f"universalitas: {len(all_ids)} requirement registry terproyeksi sebagai {state} dengan judul", ok)
tpl_ids = {r for t in active_template_library() for r in t["requires"]}
check(
    "setiap requirement yang dipakai template aktif ada di registry",
    tpl_ids <= set(registry),
    str(sorted(tpl_ids - set(registry))),
)

# ── 2. Presentation: curated when available, deterministic fallback otherwise (no invented copy) ────────
cur = req_mod.describe("commercial.price")
check(
    "terkurasi: title/verification dari pack presentation",
    cur["title"]["source"] == "curated"
    and cur["verification"]["source"] == "curated"
    and cur["title"]["lang"] == "en",
)
# Pack "en" complete (49/49, 10 Oct 2026, decision D1): the fallback stays valid for NEW requirements
# and those removed from the pack — tested on a pack copy with one entry removed, not the original pack.
uncurated = all_ids[0]
thin_pack = {**pack, "entries": {k: v for k, v in pack["entries"].items() if k != uncurated}}
fb = resolve_presentation(uncurated, registry[uncurated], thin_pack, "en")
check(
    "fallback: title dari kata id, description dari definition registry, verification dari observability",
    fb["title"]["text"] == humanize_id(uncurated)
    and fb["title"]["source"] == "fallback"
    and fb["description"]["text"] == registry[uncurated]["definition"]
    and fb["verification"]["text"] == "; ".join(registry[uncurated]["observability"])
    and fb["description"]["lang"] == "id",
    str(fb),
)
check(
    "cakupan pack 'en' lengkap: setiap requirement registry terkurasi, tidak ada lang 'id' untuk UI",
    set(pack["entries"]) == set(registry)
    and all(
        f["source"] == "curated" and f["lang"] == "en"
        for rid in all_ids
        for f in req_mod.describe(rid, "en").values()
    ),
)
check(
    "id tak dikenal registry: title dari id, tanpa mengarang deskripsi",
    resolve_presentation("ghost.thing", None, pack)["description"]["text"] == "",
)
check("humanize_id deterministik", humanize_id("commercial.pricing_basis") == "Pricing basis")

# ── 3. NEW requirement (not in pack, not in code) — Readiness needs no change ──────────────────
NEW = "sample.injected_condition"
saved = req_mod.load_registry
fake = dict(registry)
fake[NEW] = {
    "requirement_id": NEW,
    "definition": "Kondisi baru yang ditambahkan ke registry saja.",
    "observability": ["Kondisi baru dapat diamati"],
    "satisfaction_rule": {"mode": "BINARY", "sufficient": "s", "no_decisive": "n", "contradicting": "c"},
    "provenance": {
        "source_id": "tm",
        "chapters": ["ch01"],
        "knowledge_type": "source_claim",
        "confidence": "normative_only",
    },
}
req_mod.load_registry = lambda: fake
try:
    check("requirement baru tidak ada di pack presentation", NEW not in pack["entries"])
    routes_new = routes_of(
        demo_strategy=[
            node(NEW, "UNKNOWN", "Lakukan sesuatu"),
            node("access.icp", "PRESENT"),
            node("access.cadence", "ABSENT"),
        ]
    )
    pr_new = proj_of(pathset(pp("demo_strategy", "UNDETERMINED")), routes_new)
    it = next(i for i in pr_new["paths"][0]["items"] if i["key"] == NEW)
    check(
        "proyeksi: butir requirement baru ada, UNKNOWN tetap UNKNOWN, judul dari fallback id",
        it["state"] == "UNKNOWN"
        and it["title"]["text"] == "Injected condition"
        and it["title"]["source"] == "fallback",
    )
    check(
        "proyeksi: guidance jatuh ke aktivitas node (teks mesin), bukan dikarang",
        it["guidance"]["text"] == "Lakukan sesuatu",
    )
    nar = pr_new["paths"][0]["narrative"]
    check(
        "narasi fallback: requirement baru disebut sebagai belum diketahui, bukan kegagalan",
        "injected condition" in nar["unclear"].lower() and "not known yet" in nar["unclear"],
        nar["unclear"],
    )
    good = {"key": P, "unclear": nar["unclear"], "claims": nar["claims"]}
    check(
        "grounding: klaim beranjang pada requirement baru diterima",
        check_grounding([good], pr_new) == {}
        and any(c["requirement_anchor"] == NEW and c["support_state"] == "UNKNOWN" for c in nar["claims"]),
    )
    check(
        "grounding: requirement baru UNKNOWN tidak bisa diklaim SUPPORTED",
        not ground_claim(
            {"field": "supported", "claim_type": "SUPPORTED", "requirement": NEW}, pr_new["paths"][0]
        )["grounded"],
    )
    pr_present = proj_of(
        pathset(pp("demo_strategy", "SUPPORTED")), routes_of(demo_strategy=[node(NEW, "PRESENT")])
    )
    check(
        "requirement baru PRESENT berbukti dan bisa dijangkari klaim SUPPORTED",
        ground_claim(
            {"field": "supported", "claim_type": "SUPPORTED", "requirement": NEW}, pr_present["paths"][0]
        )["grounded"],
    )
finally:
    req_mod.load_registry = saved

# ── 4. No requirement dictionary / string-gate mapping in code ─────────────────────────────────────
root = pathlib.Path(".")
code = [
    f
    for pat in (
        "core/**/*.py",
        "domains/**/*.py",
        "agents/**/*.py",
        "app/**/*.py",
        "engine/**/*.py",
        "store/**/*.py",
        "app/static/js/*.js",
    )
    for f in root.glob(pat)
]
blob = {f: f.read_text(encoding="utf-8") for f in code}
check(
    "tidak ada REQ_EN / GATE_REQ di kode produksi",
    not [str(f) for f, t in blob.items() if re.search(r"\bREQ_EN\b|\bGATE_REQ\b", t)],
)
gate_strings = (
    "willingness-to-pay terbukti",
    "kapasitas masih tersedia",
    "baseline konversi terukur",
    "ekonomi viable",
)
check(
    "tidak ada string gate manusia sebagai kunci logika di kode (hanya di data ontology)",
    not [str(f) for f, t in blob.items() if any(g in t for g in gate_strings)],
    str([str(f) for f, t in blob.items() if any(g in t for g in gate_strings)]),
)
check(
    "identitas butir = requirement_id atau check_id stabil (tanpa spasi)",
    all(" " not in i["key"] for p in pr_new["paths"] for i in p["items"]),
)
check(
    "readiness core tidak memuat kamus requirement (tidak ada id requirement literal)",
    not re.search(
        r"\b(?:access|commercial|conversion|delivery|offering|retention|gtm|experiment)\.[a-z_]+",
        (root / "core/navigation/readiness.py").read_text(encoding="utf-8"),
    ),
)

# ── 5. Three separate axes: applicability != satisfaction != executability ───────────────────────────
seven = [
    node(f"access.req{i}" if False else rid, "UNKNOWN", nid=f"z{i}", executability="TRUE")
    for i, rid in enumerate(
        [
            "offering.exists",
            "offering.outcome",
            "access.icp",
            "access.cadence",
            "access.prospect_list",
            "access.outreach_asset",
            "delivery.capacity",
        ]
    )
]
pr5 = proj_of(pathset(pp("demo_strategy", "SUPPORTED")), routes_of(demo_strategy=seven))
p5 = pr5["paths"][0]
check(
    "path APPLIES + 0/7 requirement terbukti = sah (OPEN != READY); hitungan tidak dimanipulasi",
    p5["applicability"] == "APPLIES"
    and p5["status"] == "OPEN"
    and p5["counts"]
    == {"present": 0, "absent": 0, "partial": 0, "unknown": 7, "conflicted": 0, "total": 7},
)
check(
    "executability path: ada node executable -> TRUE (terpisah dari satisfaction)",
    p5["executability"] == "TRUE",
)
blocked = [
    node("access.icp", "ABSENT", nid="b1", executability="FALSE"),
    node("access.cadence", "UNKNOWN", nid="b2", executability="FALSE"),
]
check(
    "executability path: semua tertunda tak bisa dikerjakan -> FALSE",
    proj_of(pathset(pp("demo_strategy")), routes_of(demo_strategy=blocked))["paths"][0]["executability"]
    == "FALSE",
)
unk = [node("access.icp", "UNKNOWN", nid="u1", executability="UNKNOWN")]
check(
    "executability path: tertunda tak diketahui -> UNKNOWN",
    proj_of(pathset(pp("demo_strategy")), routes_of(demo_strategy=unk))["paths"][0]["executability"]
    == "UNKNOWN",
)
done = [node("access.icp", "PRESENT", nid="d1")]
check(
    "route terpenuhi: tak ada yang tersisa dikerjakan -> executability None (bukan FALSE)",
    proj_of(pathset(pp("demo_strategy")), routes_of(demo_strategy=done))["paths"][0]["executability"] is None,
)
check(
    "path tanpa route: executability UNKNOWN + substrat dilaporkan; path tetap ada",
    proj_of(pathset(pp("demo_strategy", checks=[check_row("c1", "PRESENT")])))["paths"][0]["executability"]
    == "UNKNOWN",
)
und = routes_of(demo_strategy=[node("access.icp", "UNKNOWN")])
und["routes"][0]["applicability"] = {"status": "UNDETERMINED"}
pu = proj_of(pathset(pp("demo_strategy")), und)["paths"][0]
check(
    "route applicability UNDETERMINED dipetakan ke UNKNOWN (bukan APPLIES); executability UNKNOWN",
    pu["route"]["applicability"] == "UNKNOWN" and pu["executability"] == "UNKNOWN",
)
check(
    "node membawa executability sendiri per butir",
    all(i["executability"] in ("TRUE", "FALSE", "UNKNOWN") for i in p5["items"]),
)

# ── 6. UNKNOWN != ABSENT along the chain ────────────────────────────────────────────────────────────
from domains.revenue.navigation.signals import RevenueSignals  # noqa: E402
from domains.revenue.schema.state import RevenueState  # noqa: E402

check(
    "engine: angka tak ada = signal None, bukan False",
    RevenueSignals(RevenueState())("state:wtp_proven").value is None,
)
pr6 = proj_of(
    pathset(
        pp(
            "demo_strategy",
            "UNDETERMINED",
            [check_row("wtp", "UNKNOWN", requirement_id="commercial.willingness_to_pay")],
        )
    )
)
check(
    "proyeksi: check UNKNOWN tetap UNKNOWN (bukan ABSENT)",
    pr6["paths"][0]["items"][0]["state"] == "UNKNOWN" and pr6["paths"][0]["counts"]["absent"] == 0,
)
check(
    "LLM: klaim MISSING pada butir UNKNOWN ditolak",
    not ground_claim(
        {"field": "holding", "claim_type": "MISSING", "requirement": "commercial.willingness_to_pay"},
        pr6["paths"][0],
    )["grounded"],
)

# ── 7. Zero paths: valid projection with a reason, not an error ─────────────────────────────────────────────
pr0 = proj_of(pathset(unresolved=[{"code": "INSUFFICIENT_VERIFIED_STATE", "detail": "belum cukup"}]))
check(
    "nol path: proyeksi kosong dengan alasan eksplisit",
    pr0["paths"] == [] and pr0["unresolved"][0]["code"] == "INSUFFICIENT_VERIFIED_STATE",
)
check(
    "diagnosis tanpa possible_paths: proyeksi kosong, bukan crash",
    build_readiness_projection(None)["paths"] == [],
)

fails = [x for x in _results if not x[1]]
print(
    f"\n{'=' * 50}\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS"
    + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌")
)
sys.exit(1 if fails else 0)
