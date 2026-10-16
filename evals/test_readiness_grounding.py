"""Adjudicated readiness projection + CLAIM-level narrative grounding contract (internal-docs §10;
internal-docs §Narrative Grounding).

Truth matrix: a narrative may INTERPRET state, it may not CREATE state. UNKNOWN never silently
becomes ABSENT; UI and LLM read the same projection. A claim must anchor to a requirement + evidence;
"another PRESENT item exists on this path" is NOT enough to accept a claim. Paths are hand-built (states
precisely controlled) — their count is not assumed to be five. Deterministic, no real LLM.
Run: .venv/bin/python evals/test_readiness_grounding.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

from fastapi.testclient import TestClient  # noqa: E402

from agents.explain import basis_of, build_pack, explain_session  # noqa: E402
from core.navigation.claims import ground_claim  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.guards.plain_language import (  # noqa: E402
    MAX_SENTENCE_WORDS,
    SUMMARY_WORDS,
    check_text,
)
from domains.revenue.guards.readiness_grounding import check_check_entries, check_grounding  # noqa: E402
from domains.revenue.projection.readiness import (  # noqa: E402
    build_readiness_projection,
    projection_path_keys,
    readiness_basis,
)
from domains.revenue.prompts.ask_system import SYSTEM as ASK_SYSTEM  # noqa: E402
from domains.revenue.prompts.explain_system import SYSTEM as EXPLAIN_SYSTEM  # noqa: E402
from domains.revenue.schema.explain import CheckExplain, PathClaim, PathExplain  # noqa: E402
from evals.navigation_fixtures import (  # noqa: E402
    check_row,
    diagnosis_with,
    node,
    pathset,
    pp,
    routes_of,
)
from providers.mock import MockProvider  # noqa: E402
from store.memory import Session, store  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


A, B = "path.direct_outreach", "path.value_repricing"


def _items_of(proj: dict, key: str) -> list[dict]:
    return next(p for p in proj["paths"] if p["key"] == key)["items"]


def _path_of(proj: dict, key: str) -> dict:
    return next(p for p in proj["paths"] if p["key"] == key)


def _proj(pset: dict, routes: dict | None = None, path_states: dict | None = None) -> dict:
    return build_readiness_projection(diagnosis_with(pset), routes, path_states)


# ── 1. UNKNOWN stays UNKNOWN (absence of evidence is not evidence of absence) ──────────
d = pathset(
    pp("direct_outreach", "SUPPORTED"),
    pp(
        "value_repricing",
        "UNDETERMINED",
        [
            check_row(
                "willingness_to_pay",
                "UNKNOWN",
                requirement_id="commercial.willingness_to_pay",
                reason="belum ada data",
            ),
        ],
    ),
)
route = routes_of(direct_outreach=[node("access.icp", "UNKNOWN"), node("access.prospect_list", "PRESENT")])
proj = _proj(d, route)
icp = _items_of(proj, A)[0]
check("route UNKNOWN tetap UNKNOWN (bukan ABSENT/FALSE)", icp["state"] == "UNKNOWN", icp["state"])
check("check tanpa bukti tetap UNKNOWN", _items_of(proj, B)[0]["state"] == "UNKNOWN")
check("PRESENT dibaca sebagai hadir", _items_of(proj, A)[1]["state"] == "PRESENT")
check(
    "status path diturunkan dari feasibility (SUPPORTED->OPEN, UNDETERMINED->TEST_FIRST)",
    _path_of(proj, A)["status"] == "OPEN" and _path_of(proj, B)["status"] == "TEST_FIRST",
)
check(
    "butir UNKNOWN tidak membawa bukti; butir PRESENT membawa jangkar bukti",
    icp["evidence"] == [] and _items_of(proj, A)[1]["evidence"] == ["ledger:access.prospect_list"],
)

# ── 2. Adjudication: a definite state beats an unchecked one; twins = the SAME requirement_id ─────
d2 = pathset(
    pp(
        "direct_outreach",
        "SUPPORTED",
        [
            check_row(
                "capacity_available",
                "PRESENT",
                requirement_id="delivery.capacity",
                reason="minggu ini masih ada sisa 6 jam",
                refs=("ev-3",),
            ),
        ],
    )
)
route2 = routes_of(
    direct_outreach=[
        node("delivery.capacity", "UNKNOWN", nid="n-cap"),
        node("access.icp", "PARTIAL", nid="n-icp"),
        node("access.cadence", "ABSENT", nid="n-cad"),
    ]
)
proj2 = _proj(d2, route2)
cap = [i for i in _items_of(proj2, A) if i["key"] == "delivery.capacity"]
check("check pasti melebur ke requirement yang sama (satu butir)", len(cap) == 1, str(len(cap)))
check("keadaan pasti mengalahkan UNKNOWN", cap[0]["state"] == "PRESENT")
check(
    "alasan + bukti check dibawa ke butir",
    "sisa 6 jam" in cap[0]["reason"]["text"]
    and "ev:ev-3" in cap[0]["evidence"]
    and cap[0]["sources"] == ["route", "check"],
)
check("butir tanpa kembaran tetap masuk", len(_items_of(proj2, A)) == 3)
check(
    "PARTIAL tetap PARTIAL (bukan PRESENT)",
    _items_of(proj2, A)[1]["state"] == "PARTIAL" and _items_of(proj2, A)[1]["partial"] is True,
)
check("ABSENT tetap ABSENT (bukan UNKNOWN)", _items_of(proj2, A)[2]["state"] == "ABSENT")
route2b = routes_of(direct_outreach=[node("delivery.capacity", "ABSENT", nid="n-cap")])
proj2b = _proj(d2, route2b)
cap2 = [i for i in _items_of(proj2b, A) if i["key"] == "delivery.capacity"]
check(
    "dua keadaan pasti bertentangan: node (hasil adjudikasi) menang, tanpa duplikat",
    len(cap2) == 1 and cap2[0]["state"] == "ABSENT",
)
check(
    "perbedaan itu tidak ditelan diam-diam: konflik terstruktur (kedua pembacaan, otoritas, resolusi)",
    cap2[0].get("conflict")
    == {
        "sources": {"route": "ABSENT", "check": "PRESENT"},
        "check_id": cap2[0]["conflict"]["check_id"],
        "authority": "route",
        "resolution": "AUTHORITY",
        "resolved_to": "ABSENT",
        "note": cap2[0]["conflict"]["note"],
    }
    and cap2[0]["settled"] is False,
)
check(
    "counts konsisten dengan butir (total = jumlah butir; tanpa skor skalar)",
    _path_of(proj2, A)["counts"]
    == {"present": 1, "absent": 1, "partial": 1, "unknown": 0, "conflicted": 0, "total": 3},
)

# ── 3. Lifecycle: a user-STOPPED path stays STOP; engine feasibility is not overridden ─────────────
proj3 = _proj(d, route, path_states={A: {"outcome_state": "STOPPED", "moved": 0, "regret": 1}})
p3 = _path_of(proj3, A)
check("outcome STOPPED membaca status STOP", p3["status"] == "STOP")
check(
    "feasibility engine tetap SUPPORTED; lifecycle STOPPED; asal = LIFECYCLE",
    p3["feasibility"] == "SUPPORTED"
    and p3["lifecycle"] == "STOPPED"
    and [x["source"] for x in p3["stop_provenance"]] == ["LIFECYCLE"],
)
d3c = pathset(
    pp(
        "direct_outreach",
        "CONTRADICTED",
        [check_row("wtp", "ABSENT", kind="hard", requirement_id="commercial.willingness_to_pay")],
    )
)
p3c = _path_of(_proj(d3c), A)
check(
    "kontradiksi engine: status STOP, lifecycle tetap OPEN, asal = ENGINE_CONTRADICTION",
    p3c["status"] == "STOP"
    and p3c["lifecycle"] == "OPEN"
    and p3c["stop_provenance"][0]["source"] == "ENGINE_CONTRADICTION",
)

# ── 4. CLAIM-LEVEL narrative matrix: what is ALLOWED and what is NOT for each state ──────────────
proj_m = _proj(
    pathset(pp("direct_outreach", "UNDETERMINED")),
    routes_of(
        direct_outreach=[
            node("access.prospect_list", "PRESENT"),
            node("access.icp", "ABSENT"),
            node("access.cadence", "UNKNOWN"),
            node("access.outreach_asset", "PARTIAL"),
        ]
    ),
)


def cl(field, ctype, req, text="x"):
    return {"field": field, "claim": text, "claim_type": ctype, "requirement": req}


def verdict(entry: dict, projection: dict = proj_m) -> dict:
    return check_grounding([dict({"key": A}, **entry)], projection)


good = verdict(
    {
        "supported": "You already have a list of real prospects.",
        "claims": [cl("supported", "SUPPORTED", "access.prospect_list")],
    }
)
check("PRESENT: 'sudah ada' dengan klaim beranjang boleh", good == {}, str(good))
check(
    "supported TANPA klaim ditolak (teks keadaan tanpa jangkar)",
    "paths:" + A in verdict({"supported": "You already have a list of real prospects."}),
)
check(
    "JEBAKAN supported_count>0: klaim SUPPORTED pada butir UNKNOWN ditolak walau ada butir PRESENT lain",
    "paths:" + A
    in verdict(
        {
            "supported": "You already have a weekly rhythm of contact.",
            "claims": [cl("supported", "SUPPORTED", "access.cadence")],
        }
    ),
)
check(
    "klaim SUPPORTED beranjang pada butir ABSENT ditolak",
    "paths:" + A
    in verdict(
        {
            "supported": "You already have a written ideal client.",
            "claims": [cl("supported", "SUPPORTED", "access.icp")],
        }
    ),
)
check(
    "klaim SUPPORTED beranjang pada butir PARTIAL ditolak (PARTIAL != PRESENT)",
    "paths:" + A
    in verdict(
        {
            "supported": "You already have the first message.",
            "claims": [cl("supported", "SUPPORTED", "access.outreach_asset")],
        }
    ),
)
check(
    "klaim tanpa requirement_anchor ditolak",
    "paths:" + A
    in verdict({"supported": "You already have things.", "claims": [cl("supported", "SUPPORTED", "")]}),
)
check(
    "klaim beranjang pada requirement yang tidak ada di path ditolak",
    "paths:" + A
    in verdict(
        {
            "supported": "You already have a brand.",
            "claims": [cl("supported", "SUPPORTED", "offering.exists")],
        }
    ),
)
check(
    "claim_type asing ditolak",
    "paths:" + A in verdict({"supported": "You have it.", "claims": [cl("supported", "SURE", "access.icp")]}),
)
check(
    "supported yang membantah dirinya ditolak (teks)",
    "paths:" + A
    in verdict(
        {
            "supported": "Nothing is confirmed yet, but keep going.",
            "claims": [cl("supported", "SUPPORTED", "access.prospect_list")],
        }
    ),
)

# UNKNOWN: 'not known yet' allowed with an UNKNOWN claim; NOT allowed as a negative or MISSING claim
for allowed in (
    "We have not seen someone willing to pay at this price yet.",
    "Whether a weekly rhythm of contact is in place is not known yet.",
    "Kita belum melihat jawabannya, dan belum ada yang menutupnya.",
):
    v = verdict({"unclear": allowed, "claims": [cl("unclear", "UNKNOWN", "access.cadence")]})
    check(f'UNKNOWN boleh: "{allowed[:48]}..."', v == {}, str(v))
for forbidden in (
    "Nobody wants to pay this price.",
    "There is no demand for this.",
    "The market rejects this price.",
    "This path has failed.",
    "Nobody has ever paid for work like this.",
):
    v = verdict({"unclear": forbidden, "claims": [cl("unclear", "UNKNOWN", "access.cadence")]})
    check(f'UNKNOWN dilarang dibunyikan negatif: "{forbidden[:44]}..."', "paths:" + A in v)
check(
    "UNKNOWN != ABSENT: klaim MISSING beranjang pada butir UNKNOWN ditolak",
    "paths:" + A
    in verdict(
        {
            "holding": "A weekly rhythm is what it waits on.",
            "claims": [cl("holding", "MISSING", "access.cadence")],
        }
    ),
)
check(
    "unclear beranjang pada butir ABSENT ditolak (tidak boleh melunakkan ABSENT jadi belum tahu)",
    "paths:" + A
    in verdict(
        {
            "unclear": "We do not know if the ideal client exists.",
            "claims": [cl("unclear", "UNKNOWN", "access.icp")],
        }
    ),
)
check(
    "ABSENT: holding dengan klaim MISSING boleh",
    verdict(
        {
            "holding": "A written ideal client is what it waits on.",
            "claims": [cl("holding", "MISSING", "access.icp")],
        }
    )
    == {},
)
check(
    "PARTIAL: holding dengan klaim PARTIAL boleh; klaim MISSING pada butir PARTIAL ditolak",
    verdict(
        {
            "holding": "Part of the first message is in place.",
            "claims": [cl("holding", "PARTIAL", "access.outreach_asset")],
        }
    )
    == {}
    and "paths:" + A
    in verdict(
        {
            "holding": "The first message is missing.",
            "claims": [cl("holding", "MISSING", "access.outreach_asset")],
        }
    ),
)
check(
    "field kosong selalu sah (UI jatuh ke fallback)",
    verdict({"supported": "", "holding": "", "unclear": ""}) == {},
)
check(
    "klaim untuk field yang kosong teksnya diabaikan",
    verdict({"why": "Ok.", "claims": [cl("supported", "SUPPORTED", "access.cadence")]}) == {},
)
proj_none = _proj(
    pathset(pp("direct_outreach", "SUPPORTED")),
    routes_of(direct_outreach=[node("access.prospect_list", "PRESENT")]),
)
check(
    "path tanpa butir UNKNOWN: unclear tanpa dasar ditolak (tanpa klaim)",
    "paths:" + A in check_grounding([{"key": A, "unclear": "Nobody knows the answer yet."}], proj_none),
)

# a SUPPORTED claim without evidence_anchor is rejected (hand-built item without evidence)
bare = {"items": [{"key": "x.y", "state": "PRESENT", "evidence": []}]}
check(
    "ground_claim: SUPPORTED tanpa evidence_anchor ditolak",
    not ground_claim(cl("supported", "SUPPORTED", "x.y"), bare)["grounded"],
)
ok_item = {"items": [{"key": "x.y", "state": "PRESENT", "evidence": ["ledger:x.y"]}]}
gc = ground_claim(cl("supported", "SUPPORTED", "x.y"), ok_item)
check(
    "ground_claim: klaim ter-resolve membawa anchor + evidence + support_state dari PROYEKSI",
    gc["grounded"]
    and gc["requirement_anchor"] == "x.y"
    and gc["evidence_anchor"] == ["ledger:x.y"]
    and gc["support_state"] == "PRESENT",
)

# checklist entries (have/how) are also anchored
chk = check_check_entries(
    [
        {"key": "access.prospect_list", "have": "You have a list."},
        {"key": "access.icp", "have": "You have it."},
        {"key": "access.cadence", "have": "Ok."},
        {"key": "access.icp", "how": "Tulis satu kalimat."},
    ],
    proj_m,
)
check(
    "checks.have hanya sah untuk butir PRESENT yang berbukti",
    "checks:access.prospect_list" not in chk
    and "checks:access.icp" in chk
    and "checks:access.cadence" in chk,
    str(chk),
)

# ── 5. Overclaim lexicon (population/comparison claims, EN + ID) ─────────────────────
for phrase in (
    "That is a warmer start than most.",
    "Better than most freelancers manage.",
    "Stronger than alternatives on price.",
    "Everyone needs this kind of help.",
    "Most clients pay within a week.",
    "The market wants what you make.",
    "This will definitely work.",
    "Your results are guaranteed.",
    "The work is already proven.",
    "Dari 8 tahun kerja, pasti ada yang tahu.",
    "Semua orang butuh jasa seperti ini.",
    "Harga ini dijamin cocok.",
):
    check(f'overclaim ditolak: "{phrase[:40]}..."', "paths:" + A in verdict({"why": phrase}))
check(
    "perbandingan antar path sendiri boleh",
    verdict({"why": "This path asks less up front than the pricing one does."}) == {},
)

# ── 6. Key reconciliation + grounding via explain_session ────────────────────────────
goal = (
    "I left my job as a marketing manager. I want Rp20 million a month within 90 days. I have no clients yet."
)


def _session(sid: str) -> Session:
    s = Session(id=sid, goal_text=goal, language="en")
    s.transcript = [("user", goal), ("user", "Marketing selama 8 tahun, belum punya client sama sekali.")]
    s.evidence = [
        EvidenceItem(
            id="ev-1",
            signal="no active clients",
            level="self_reported",
            source_quote="no clients",
            topic="GOAL",
        )
    ]
    s.diagnosis = diagnosis_with(
        pathset(pp("direct_outreach", "SUPPORTED"), pp("value_repricing", "CONDITIONAL"))
    )
    return s


s = _session("rg1")
NODES = [
    node("access.prospect_list", "PRESENT"),
    node("access.icp", "ABSENT"),
    node("access.cadence", "UNKNOWN"),
]
route_fixture = routes_of(direct_outreach=NODES, value_repricing=NODES)


def _pe(key, **kw):
    return dict(
        {
            "key": key,
            "why": "Ok.",
            "next": "",
            "opening": "",
            "supported": "",
            "holding": "",
            "unclear": "",
            "claims": [],
        },
        **kw,
    )


class Liar(MockProvider):
    """Invented path keys, duplicate keys, missing keys, and foreign check keys."""

    def structured_call(self, schema, system, user, retries=2):
        r = super().structured_call(schema, system, user)
        r.paths = [
            PathExplain(**x)
            for x in [
                _pe(
                    A,
                    next="Ok.",
                    supported="You already have a list of real prospects.",
                    claims=[cl("supported", "SUPPORTED", "access.prospect_list")],
                ),
                _pe("MADE_UP"),
                _pe(B, holding="Ok.", claims=[cl("holding", "MISSING", "access.icp")]),
                _pe(B, why="Duplicate."),
            ]
        ]
        r.checks = [
            CheckExplain(**x)
            for x in [
                {"key": "access.prospect_list", "how": "Ok.", "have": "Ok."},
                {"key": "access.icp", "how": "Ok.", "have": ""},
                {"key": "access.cadence", "how": "Ok.", "have": ""},
                {"key": "not.a.real.key", "how": "Ok.", "have": ""},
            ]
        ]
        return r


out = explain_session(Liar(), s, route_data=route_fixture)
keys = [p["key"] for p in out["paths"]]
check("kunci asing dibuang; keluaran = kunci engine, urutan engine", keys == [A, B], str(keys))
check("kembaran kunci diambil yang pertama", out["paths"][1]["why"] == "Ok.")
check(
    "daftar dropped menyebut kunci asing dan kembaran",
    any(x.startswith("paths:MADE_UP") for x in out["dropped"])
    and f"paths:{B}:duplicate" in out["dropped"]
    and "checks:not.a.real.key:unknown-key" in out["dropped"],
    str(out["dropped"]),
)
check(
    "kunci cek keluaran = kunci engine",
    {c["key"] for c in out["checks"]} <= {"access.prospect_list", "access.icp", "access.cadence"},
    str([c["key"] for c in out["checks"]]),
)


class Shy(MockProvider):
    """Narrative missing entirely: valid — the UI falls back deterministically."""

    def structured_call(self, schema, system, user, retries=2):
        r = super().structured_call(schema, system, user)
        r.paths = []
        r.checks = []
        return r


out_shy = explain_session(Shy(), s, route_data=route_fixture)
check(
    "narasi hilang: tanpa butir path, tanpa crash",
    out_shy["paths"] == [] and out_shy["dropped"] == [],
    str(out_shy["dropped"]),
)


class Overclaimer(MockProvider):
    """Narrative violates grounding: that item is dropped, other items stay intact."""

    def structured_call(self, schema, system, user, retries=2):
        r = super().structured_call(schema, system, user)
        for p in r.paths:
            if p.key == A:
                p.supported = "Nobody wants to pay for work like this, so keep going."
        return r


out_over = explain_session(Overclaimer(), s, route_data=route_fixture)
check(
    "grounding violation: butir path dibuang dari hasil",
    all(p["key"] != A for p in out_over["paths"]),
    str([p["key"] for p in out_over["paths"]]),
)
check("grounding violation: butir bersih dipertahankan", any(p["key"] == B for p in out_over["paths"]))
check(
    "daftar dropped menyebut pelanggaran grounding",
    f"paths:{A}" in out_over["dropped"],
    str(out_over["dropped"]),
)


class UnknownAsSupported(MockProvider):
    """LLM states the UNKNOWN condition as 'already in place' — claim anchors to an UNKNOWN item."""

    def structured_call(self, schema, system, user, retries=2):
        r = super().structured_call(schema, system, user)
        for p in r.paths:
            if p.key == A:
                p.supported = "You already have a weekly rhythm of contact."
                p.claims = [PathClaim(**cl("supported", "SUPPORTED", "access.cadence"))]
        return r


out_unk = explain_session(UnknownAsSupported(), s, route_data=route_fixture)
check(
    "LLM: UNKNOWN diucapkan sebagai PRESENT -> path itu dibuang (walau ada butir PRESENT lain)",
    all(p["key"] != A for p in out_unk["paths"]) and f"paths:{A}" in out_unk["dropped"],
)


class Ungrounded(MockProvider):
    """Condition text with no anchored claim at all."""

    def structured_call(self, schema, system, user, retries=2):
        r = super().structured_call(schema, system, user)
        for p in r.paths:
            if p.key == A:
                p.supported = "You already have a list of real prospects."
                p.claims = []
        return r


out_ung = explain_session(Ungrounded(), s, route_data=route_fixture)
check("LLM: teks keadaan tanpa klaim beranjang dibuang", all(p["key"] != A for p in out_ung["paths"]))

# ── 7. Cache basis: semantic state, not wall-clock time ────────────────────────────────────────
base = _proj(d, route)
b0 = readiness_basis(base)
flipped = _proj(
    pathset(
        pp("direct_outreach", "SUPPORTED"),
        pp(
            "value_repricing",
            "UNDETERMINED",
            [
                check_row(
                    "willingness_to_pay",
                    "ABSENT",
                    requirement_id="commercial.willingness_to_pay",
                    reason="belum ada",
                )
            ],
        ),
    ),
    route,
)
check("check berubah keadaan -> basis berubah", readiness_basis(flipped) != b0)
status_shift = _proj(pathset(pp("direct_outreach", "CONDITIONAL"), d["paths"][1]), route)
check("feasibility/status path bergeser -> basis berubah", readiness_basis(status_shift) != b0)
check(
    "alasan check berubah (keadaan sama) -> basis tetap",
    readiness_basis(
        _proj(
            pathset(
                d["paths"][0],
                pp(
                    "value_repricing",
                    "UNDETERMINED",
                    [
                        check_row(
                            "willingness_to_pay",
                            "UNKNOWN",
                            requirement_id="commercial.willingness_to_pay",
                            reason="alasan lain",
                        )
                    ],
                ),
            ),
            route,
        )
    )
    == b0,
)
executed = _proj(
    d,
    routes_of(
        direct_outreach=[
            node("access.icp", "UNKNOWN", executed=True),
            node("access.prospect_list", "PRESENT"),
        ]
    ),
)
check("laporan 'sudah dikerjakan' bukan perubahan keadaan -> basis tetap", readiness_basis(executed) == b0)
check(
    "lifecycle berubah -> basis berubah",
    readiness_basis(_proj(d, route, path_states={A: {"outcome_state": "STOPPED"}})) != b0,
)
check(
    "basis_of menyertakan readiness (stale terdeteksi)",
    basis_of(_session("rg2"), base) != basis_of(_session("rg2")),
)
s3 = _session("rg3")
check("basis_of deterministik untuk sesi yang sama", basis_of(s3, base) == basis_of(s3, base))

# ── 8. Deterministic narrative fallback: micro-narratives traceable to items (anchored claims) ─────
nar = _path_of(proj, A)["narrative"]
check(
    "fallback supported menyebut yang sudah ada",
    "a list of real prospects" in nar["supported"],
    nar["supported"],
)
check(
    "fallback unclear menyatakan belum diketahui (bukan kegagalan)",
    "not known yet" in nar["unclear"] and "nobody" not in nar["unclear"].lower(),
    nar["unclear"],
)
check("fallback OPEN: holding kosong (path OPEN tidak menunggu apa pun)", nar["holding"] == "")
check(
    "fallback SETIAP klaim ter-ground terhadap proyeksinya sendiri (klaim beranjang menurut konstruksi)",
    nar["claims"] and all(ground_claim(c, _path_of(proj, A))["grounded"] for c in nar["claims"]),
)
check(
    "fallback lolos check_grounding tingkat-klaim",
    check_grounding(
        [dict({"key": A}, **{k: nar[k] for k in ("supported", "holding", "unclear")}, claims=nar["claims"])],
        proj,
    )
    == {},
)
fb_cap = _path_of(_proj(d2, route2), A)["narrative"]
check(
    "fallback supported menyebut keadaan pasti dari check yang melebur ke requirement",
    "hours you can spare" in fb_cap["supported"].lower(),
    fb_cap["supported"],
)
proj_tf = _proj(
    pathset(pp("value_repricing", "UNDETERMINED")),
    routes_of(
        value_repricing=[node("commercial.willingness_to_pay", "UNKNOWN"), node("commercial.price", "ABSENT")]
    ),
)
fb_tf = _path_of(proj_tf, B)["narrative"]
check(
    "fallback TEST_FIRST: unclear menyebut yang belum dicek",
    "willing to pay" in fb_tf["unclear"],
    fb_tf["unclear"],
)
check(
    "fallback TEST_FIRST: holding menunjuk yang belum ada",
    "A specific new price" in fb_tf["holding"],
    fb_tf["holding"],
)
empty_n = _path_of(_proj(pathset(pp("client_expansion", "CONDITIONAL"))), "path.client_expansion")[
    "narrative"
]
check(
    "path tanpa butir: semua fallback kosong (tidak dikarang)",
    (empty_n["supported"], empty_n["holding"], empty_n["unclear"], empty_n["claims"]) == ("", "", "", []),
    str(empty_n),
)
for field, text in (
    ("supported", nar["supported"]),
    ("holding", fb_tf["holding"]),
    ("unclear", nar["unclear"]),
):
    errs = check_text(text, set(), 300)
    check(f"fallback {field} bersih di guard bahasa (tanpa angka karangan)", errs == [], str(errs))
    check(
        f"fallback {field} satu kalimat pendek",
        all(len(x.split()) <= MAX_SENTENCE_WORDS for x in text.split(". ") if x),
    )

# ── 9. One limit constant: prompt = guard = test ─────────────────────────────────────────
check("prompt explain memakai limit guard (kalimat)", f"at most {MAX_SENTENCE_WORDS} words" in EXPLAIN_SYSTEM)
check("prompt explain memakai limit guard (ringkasan)", f"at most {SUMMARY_WORDS} words" in EXPLAIN_SYSTEM)
check("prompt ask memakai limit guard", f"at most {MAX_SENTENCE_WORDS} words" in ASK_SYSTEM)
check(
    "angka lama (18/110) tidak ada lagi di prompt",
    "18 words" not in EXPLAIN_SYSTEM
    and "110 words" not in EXPLAIN_SYSTEM
    and "18 words" not in ASK_SYSTEM
    and "110 words" not in ASK_SYSTEM,
)
pack, _pool = build_pack(s, route_fixture)
check("pack memuat aturan grounding klaim untuk LLM", "Narrative may interpret" in pack and "claim" in pack)
check(
    "prompt explain meminta klaim beranjang", "claims:" in EXPLAIN_SYSTEM and "requirement" in EXPLAIN_SYSTEM
)
check(
    "prompt explain tidak menyebut jumlah path tetap atau motion",
    "five" not in EXPLAIN_SYSTEM.lower() and "ACQUISITION" not in EXPLAIN_SYSTEM,
)

# ── 10. Endpoint readiness: UI reads the same projection ─────────────────────────────
import app.main as app_main  # noqa: E402

app_main.get_llm = lambda: MockProvider()  # deterministic: does not use the real provider from .env
c = TestClient(app_main.app)
check("endpoint: sesi tidak ada = 404", c.get("/session/none/readiness").status_code == 404)
sid = c.post("/session", json={"goal_text": "naik ke 20 juta per bulan", "language": "id"}).json()[
    "session_id"
]
check("endpoint: tanpa diagnosis = 409", c.get(f"/session/{sid}/readiness").status_code == 409)
real = store.get(sid)
real.diagnosis = _session("rg4").diagnosis
real.user_id = "u_rg_test"
store.save(real)
r = c.get(f"/session/{sid}/readiness")
body = r.json()
check("endpoint: 200 dengan diagnosis", r.status_code == 200 and body.get("paths") is not None, r.text[:120])
check(
    "endpoint: proyeksi membawa narrative + counts + items + executability + applicability",
    all(
        (
            "narrative" in p
            and "counts" in p
            and "items" in p
            and "executability" in p
            and "applicability" in p
        )
        for p in body["paths"]
    ),
)
check("endpoint: kunci path = kunci engine", [p["key"] for p in body["paths"]] == projection_path_keys(body))
try:
    import os

    os.remove(f"store/sessions/{sid}.json")
except OSError:
    pass

n_ok = sum(1 for _, ok, _ in _results if ok)
print(f"\nHASIL: {n_ok}/{len(_results)} PASS {'✅' if n_ok == len(_results) else '❌'}")
sys.exit(0 if n_ok == len(_results) else 1)
