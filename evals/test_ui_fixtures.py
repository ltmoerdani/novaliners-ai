"""UI fixtures (e2e/fixtures/*.json) must match the engine's CURRENT output — not a stale copy.

Fixtures are built by evals/make_ui_fixtures.py from the real engine; e2e/paths.spec.mjs uses
them for UI states unreachable via the mock provider (zero/one/many paths; requirement
UNKNOWN/PARTIAL/met; new requirement). If the engine shape changes, this test fails until the
fixtures are rebuilt: `python evals/make_ui_fixtures.py`.
Run: .venv/bin/python evals/test_ui_fixtures.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, ".")

from evals.make_ui_fixtures import build  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


built = json.loads(json.dumps(build(), sort_keys=True))
for name, data in built.items():
    f = pathlib.Path("e2e/fixtures") / f"{name}.json"
    check(
        f"fixture {name} sama dengan keluaran engine saat ini",
        f.exists() and json.loads(f.read_text(encoding="utf-8")) == data,
        "bangun ulang: python evals/make_ui_fixtures.py",
    )
on_disk = {p.stem for p in pathlib.Path("e2e/fixtures").glob("*.json")}
check("tidak ada fixture yatim di e2e/fixtures", on_disk == set(built), str(sorted(on_disk ^ set(built))))

z = built["paths_zero"]["possible_paths"]
check(
    "nol path membawa alasan eksplisit berbahasa UI",
    z["paths"] == [] and z["unresolved"][0]["i18n"]["en"]["detail"],
)
check(
    "satu path berasal dari mekanisme, bukan angka pendapatan",
    [p["strategy_id"] for p in built["paths_one"]["possible_paths"]["paths"]] == ["value_repricing"],
)
check(
    "delapan path dari domain sintetis (bukan lima)",
    len(built["paths_eight"]["possible_paths"]["paths"]) == 8,
)
WORDS = ((3, "three"), (5, "five"), (6, "six"), (8, "eight"), (10, "ten"))
counts = {n: len(built[f"paths_{w}"]["possible_paths"]["paths"]) for n, w in WORDS}
check(
    "fixture 0..N untuk kebijakan tampilan: engine mengembalikan 3, 5, 6, 8, 10 path utuh (UI membatasi)",
    counts == {3: 3, 5: 5, 6: 6, 8: 8, 10: 10},
    str(counts),
)
many = built["paths_candidates_many"]["possible_paths"]["paths"]
check(
    "delapan kandidat bercampur status (3 OPEN, 3 TEST_FIRST, 1 NOT_YET, 1 STOP), semua lahir dari kandidat",
    sorted(p["status"] for p in many)
    == ["NOT_YET", "OPEN", "OPEN", "OPEN", "STOP", "TEST_FIRST", "TEST_FIRST", "TEST_FIRST"]
    and all(p["provenance"]["candidate"]["evidence_ids"] for p in many)
    and all(p["motion"] is None and not p["route_substrate"]["available"] for p in many),
)
gold = built["paths_candidate_golden"]
gp = next(p for p in gold["projection"]["paths"] if p["strategy_id"] == "simplify_onboarding")
check(
    "golden Candidate-born (komposer nyata + ledger): path-kandidat ber-route, node dari ledger, NextMove",
    gp["candidate"]["origin"] == "MECHANISM_PATTERN"
    and gp["route"]["template_id"] == "simplify_onboarding_v1"
    and {i["key"]: i["state"] for i in gp["items"]}
    == {
        "delivery.onboarding": "PRESENT",
        "retention.aha_moment_defined": "UNKNOWN",
        "retention.activation": "UNKNOWN",
    }
    and gold["routes"]["next_move"]["output"] == "ACTION"
    and gold["routes"]["routes"][0]["motion"] == "ACTIVATION",
)
new = built["readiness_new_requirement"]["projection"]["paths"][0]["items"]
check(
    "requirement baru: judul dari fallback id, bukan dari pack presentation",
    any(i["key"] == "sample.injected_condition" and i["title"]["source"] == "fallback" for i in new),
)


# ── new fixtures: cases that must come from the real engine ─────────────────────────────────────────
eng, usr = built["paths_engine_stop"], built["paths_user_stop"]


def stops(fx):
    return {
        p["strategy_id"]: [x["source"] for x in p["stop_provenance"]]
        for p in fx["possible_paths"]["paths"]
        if p["status"] == "STOP"
    }


check(
    "engine STOP: asal ENGINE_CONTRADICTION saja, lifecycle tetap OPEN",
    stops(eng)
    and all(v == ["ENGINE_CONTRADICTION"] for v in stops(eng).values())
    and all(p["lifecycle"] == "OPEN" for p in eng["possible_paths"]["paths"]),
)
check(
    "user STOP: asal LIFECYCLE saja, feasibility engine tidak ditimpa",
    stops(usr) == {"value_repricing": ["LIFECYCLE"]}
    and next(p for p in usr["possible_paths"]["paths"] if p["strategy_id"] == "value_repricing")[
        "feasibility"
    ]
    != "CONTRADICTED",
)
leg = built["paths_legacy"]
check(
    "legacy: possible_paths null dan navigation LEGACY dari loader artefak nyata",
    leg["possible_paths"] is None
    and leg["navigation"]["status"] == "LEGACY"
    and leg["navigation"]["needs_rediagnosis"] is True,
)
check(
    "semua fixture path non-legacy bernavigasi CURRENT",
    all(
        v["navigation"]["status"] == "CURRENT"
        for k, v in built.items()
        if k not in ("paths_legacy", "paths_legacy_content")  # both intentionally LEGACY
    ),
)
legc = built["paths_legacy_content"]
check(
    "legacy-content: versi lain TAPI paths terisi — tetap LEGACY, proyeksi paths kosong",
    legc["navigation"]["status"] == "LEGACY"
    and legc["navigation"]["reason_code"] == "SCHEMA_VERSION_MISMATCH"
    and len(legc["possible_paths"]["paths"]) == 5
    and legc["projection"]["paths"] == [],
)
know = built["paths_knowledge"]["possible_paths"]["paths"]
hire = next(p for p in know if p["strategy_id"] == "structured_interviews")
check(
    "knowledge: path lahir dari rule + mekanisme dengan anchor evidence nyata; tanpa motion Revenue",
    hire["provenance"]["knowledge_ids"] == ["HR-R1"]
    and hire["provenance"]["mechanism_ids"] == ["inconsistent_hiring_bar"]
    and {"ev-hr-1", "ev-hr-2"} <= set(hire["provenance"]["evidence_ids"])
    and hire["motion"] is None,
)
five = built["paths_revenue_five"]["possible_paths"]["paths"]
check(
    "Revenue: lima motion primitive lahir sebagai path yang identitasnya strategi",
    sorted(p["motion"] for p in five)
    == sorted(["ACQUISITION", "REPRICING", "EXPANSION", "PARTNERSHIP", "PAID_ACQUISITION"])
    and all(p["path_id"] == f"path.{p['strategy_id']}" for p in five),
)

fails = [x for x in _results if not x[1]]
print(
    f"\n{'=' * 50}\nHASIL: {len(_results) - len(fails)}/{len(_results)} PASS"
    + (" ✅" if not fails else f" — {len(fails)} GAGAL ❌")
)
sys.exit(1 if fails else 0)
