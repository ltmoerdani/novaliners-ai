"""Human-language explanation guard (internal-docs §6).

Deterministic, no real LLM. Run: .venv/bin/python evals/test_plain_explain.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from evals._store_isolation import isolate_store  # noqa: E402

isolate_store()  # eval: store redirected to tmp — production store untouched

from agents.explain import build_pack, explain_session  # noqa: E402
from core.schema.evidence import EvidenceItem  # noqa: E402
from domains.revenue.guards.plain_language import check_explain, check_text  # noqa: E402
from domains.revenue.schema.explain import PlainExplain  # noqa: E402
from evals.navigation_fixtures import revenue_artifact, route_for, strategy_ids  # noqa: E402
from providers.mock import MockProvider, _mock_for  # noqa: E402
from store.memory import Session  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    print(f"  {'✅' if ok else '❌'} {name}" + (f" | {detail}" if detail else ""))


POOL = {"8", "25", "60", "12", "18", "20", "6", "5"}

# 1 — the text the product owner complained about is rejected, with the right reasons
raw = (
    "Jangan SCALE akuisisi dulu — dan jangan uji volume akuisisi BERSAMAAN dengan perbaikan konversi. "
    "Urutkan 4 fase: (1) perbaiki price-response pada lead yang ada, (2) ukur konversi inquiry→deal"
)
errs = " ".join(check_text(raw, POOL, 400))
for needle in ("akuisisi", "konversi", "price-response", "scale", "shouting", "machine notation",
               "number not from"):
    check(f"teks teknis ditolak: {needle}", needle in errs)

# 2 — human language grounded in the user's own words passes
good = (
    "Anda punya 18-20 nomor WhatsApp yang bisa dihubungi hari ini. "
    "Dalam 20 hari terakhir tidak ada satu pun pesan keluar."
)
good_errs = check_text(good, POOL, 300)
check("kalimat pendek dari kata pengguna lolos", good_errs == [], str(good_errs))

# 3 — invented numbers rejected; numbers from a source accepted
invented = check_text("Anda butuh 37 klien.", POOL, 100)
check("angka karangan ditolak", any("number not from" in e for e in invented))
check("angka dari sumber diterima", check_text("Target Anda 25 juta.", POOL, 100) == [])

# 4 — long sentences rejected, whole summary capped
long_sentence = " ".join(["kata"] * 30) + "."
long_errs = check_text(long_sentence, POOL, 400)
check("kalimat 30 kata ditolak", any("sentence of 30 words" in e for e in long_errs))
big = PlainExplain(
    summary=[" ".join(["kata."] * 50)] * 3, blocking_title="Ok.", do_title="Tulis.", done_when="Ok.",
    hold_title="Jangan.", why=["a.", "b."],
).model_dump()
big_errs = check_explain(big, POOL).get("summary", [])
check("ringkasan lebih dari 115 kata ditolak", any("summary is" in e for e in big_errs))

# 5 — required fields, item counts, and optional fields
ex = PlainExplain(
    summary=["Satu."], blocking_title="", do_title="Tulis.", done_when="Ok.",
    hold_title="Jangan dulu.", why=["a"],
).model_dump()
bad = check_explain(ex, POOL)
check("field kosong ditandai", bad.get("blocking_title") == ["empty"])
check("jumlah item why (2-3) ditegakkan", any("items" in e for e in bad.get("why", [])))
check("field opsional kosong boleh", not ({"do_why", "blocking_body", "hold_body"} & set(bad)))

# 6 — end-to-end with the mock provider: clean, linked to the artifact, no dropped fields.
# The fixture uses the REAL Revenue engine over synthetic state (paths emerge from the state, not a
# fixed list) and a route with three states, so the mock narrative is grounded in a validatable
# projection.
goal = ("I left my job as a marketing manager. I want Rp20 million a month within 90 days. "
        "I have no clients yet.")
s = Session(id="t1", goal_text=goal, language="en")
s.transcript = [("user", goal), ("user", "Marketing selama 8 tahun, belum punya client sama sekali.")]
s.evidence = [EvidenceItem(id="ev-1", signal="no active clients", level="self_reported",
                           source_quote="no clients", topic="GOAL")]
s.diagnosis = revenue_artifact(
    current_monthly=30.0, target_monthly=60.0, gap_monthly=30.0, capacity_utilization=0.5,
    willingness_to_pay="PROVEN_AT_CURRENT_PRICE", demand_exists=True, demand_signal="EXISTS",
    avg_deal_size=10.0)
ENGINE_KEYS = [f"path.{sid}" for sid in strategy_ids(s.diagnosis)]
route_fixture = {"routes": [route_for(sid) for sid in strategy_ids(s.diagnosis)]}
out = explain_session(MockProvider(), s, route_data=route_fixture)
check("mock: tidak ada field dibuang", out["dropped"] == [], str(out["dropped"]))
check("mock: bersih di guard", check_explain(out, build_pack(s)[1]) == {})
check("mock: tertaut ke artefak + readiness (basis)", len(out["basis"]) == 12)
check("mock: ringkasan 1-3 paragraf", 1 <= len(out["summary"]) <= 3)
check("mock: path direkonsiliasi ke kunci engine (jumlah = yang dibentuk engine, bukan lima tetap)",
      [p["key"] for p in out["paths"]] == ENGINE_KEYS and len(ENGINE_KEYS) >= 3,
      str([p["key"] for p in out["paths"]]))
check("mock: klaim beranjang ikut keluaran dan lolos grounding",
      all(p["claims"] for p in out["paths"] if p.get("supported") or p.get("holding") or p.get("unclear")))


# 7 — a violating LLM gets ONE fix; fields that still violate are dropped, the rest kept
class Stubborn(MockProvider):
    calls = 0

    def structured_call(self, schema, system, user, retries=2):
        Stubborn.calls += 1
        r = super().structured_call(schema, system, user)
        r.hold_title = "Jangan SCALE akuisisi dulu."   # always violates
        return r


out2 = explain_session(Stubborn(), s, route_data=route_fixture)
check("perbaikan hanya satu kali", Stubborn.calls == 2, f"calls={Stubborn.calls}")
check("field yang tetap melanggar dibuang", out2["hold_title"] == "" and out2["dropped"] == ["hold_title"],
      str(out2["dropped"]))
check("field bersih dipertahankan", out2["do_title"] != "" and out2["summary"])

# 8 — the prompt carries the user's words, not only engine labels
pack, _ = build_pack(s)
check("pack memuat kata pengguna", "USER WORDS" in pack and "belum punya client" in pack)
check("pack menandai label ontologi sebagai kemungkinan tidak cocok", "may be generic or not fit" in pack)

# 9 — violating path/check items are flagged per item; clean items and other blocks pass (screen 07/18)
exn = PlainExplain(
    summary=["Ok."], blocking_title="Ok.", do_title="Tulis.", done_when="Ok.", hold_title="Jangan.",
    why=["a.", "b."],
    paths=[
        {"key": "path.direct_outreach", "why": "Jangan SCALE akuisisi dulu.",
         "next": "Send the first message."},
        {"key": "path.value_repricing", "why": "The current price has not been paid yet.", "next": ""},
    ],
    checks=[
        {"key": "access.icp", "how": "Anda butuh 37 klien baru.", "have": ""},
        {"key": "access.cadence", "how": "Record how many people you contact each week.", "have": ""},
    ],
).model_dump()
badn = check_explain(exn, POOL)
bad_keys = sorted(badn)
check("butir jalur pelanggar ditandai per butir",
      any(k.startswith("paths:path.direct_outreach") for k in bad_keys), str(bad_keys))
check("butir jalur bersih tidak ikut ditandai",
      not any(k.startswith("paths:path.value_repricing") for k in bad_keys))
check("cek dengan angka karangan ditandai", any(k.startswith("checks:access.icp") for k in bad_keys))
check("cek bersih tidak ikut ditandai", not any(k.startswith("checks:access.cadence") for k in bad_keys))
check("teks butir kosong sah (fallback engine)",
      not any("empty" in " ".join(v) for k, v in badn.items() if ":" in k))

# 10 — the user route enters the checks-read pack (screen 18); paths enter the paths read (screen 07)
pack_r, _ = build_pack(s, route_data={"routes": [
    route_for("direct_outreach", nodes=[
        ("access.icp", "UNKNOWN", "Tulis siapa yang Anda jual kepada"),
        ("access.prospect_list", "PRESENT", "Tulis daftar orang yang bisa dihubungi"),
    ]),
]})
check("pack memuat bacaan path", "PATHS READ" in pack_r)
check("pack memuat bacaan cek dari route user", "CHECKS READ" in pack_r and "access.icp" in pack_r)
check("kunci cek ditandai persis untuk LLM", "key access.icp" in pack_r)
check("pack tidak menyebut jumlah path tetap", "five" not in pack_r.lower())

# 10b — readiness narrative (screen 18): requirement state enters the paths read per path key
check("state requirement masuk bacaan path",
      "path path.direct_outreach" in pack_r
      and 'item access.icp ("A written ideal client"): not checked yet' in pack_r)
check("state PRESENT dibaca sebagai confirmed",
      'item access.prospect_list ("A list of real prospects"): confirmed' in pack_r)

# 10c — narrative fields guarded per item; empty is valid (UI composition fallback)
exr = PlainExplain(
    summary=["Ok."], blocking_title="Ok.", do_title="Tulis.", done_when="Ok.", hold_title="Jangan.",
    why=["a.", "b."],
    paths=[
        {"key": "path.direct_outreach", "why": "Ok.", "next": "Ok.",
         "opening": " ".join(["kata"] * 60) + ".",
         "supported": "Yang sudah ada: pengalaman Anda.", "holding": "", "unclear": ""},
    ],
).model_dump()
badr = check_explain(exr, POOL)
check("opening yang terlalu panjang ditandai per butir",
      any(k.startswith("paths:path.direct_outreach") for k in badr), str(sorted(badr)))
check("supported bersih dan unclear kosong tidak ditandai",
      not any("too long" in e for v in badr.values() for e in v if "supported" in " ".join(v)))
pack_full, _ = build_pack(s, route_data=route_fixture)
mock_ex = _mock_for(PlainExplain, pack_full)
check("mock: setiap path yang dibentuk engine punya opening",
      len(mock_ex["paths"]) == len(ENGINE_KEYS) and all(p["opening"] for p in mock_ex["paths"]))
check("mock tanpa pack tidak mengarang path", _mock_for(PlainExplain)["paths"] == [])
# Round 4: the mock no longer has fixed text per path key (which used to make some paths "fallback"
# by accident). The contract now: a narrative field exists EXACTLY when the pack carries a path item
# with a matching state - supported <- confirmed, holding <- still to get/partly there, unclear <-
# not checked yet.
from providers.mock import _parse_pack  # noqa: E402

parsed = _parse_pack(pack_full)
by_key = {p["key"]: p for p in mock_ex["paths"]}


def _has(path_key: str, *words: str) -> bool:
    return any(w in words for _, _, w in parsed[path_key]["items"])


check("mock: supported/holding/unclear muncul tepat bila ada butir dengan keadaan yang cocok",
      all(bool(by_key[k].get("supported")) == _has(k, "confirmed")
          and bool(by_key[k].get("unclear")) == _has(k, "not checked yet")
          for k in parsed))
# paths without a matching item still fall back to the engine sentence: the mock fills no
# ungrounded field
pack_noconf = pack_full.replace("): confirmed", "): not checked yet")
mock_noconf = {p["key"]: p for p in _mock_for(PlainExplain, pack_noconf)["paths"]}
check("mock: tanpa butir confirmed di pack, tidak ada supported (fallback engine)",
      all(not p.get("supported") for p in mock_noconf.values())
      and all(p.get("unclear") for p in mock_noconf.values()))
mock_bad = check_explain(mock_ex, POOL)
check("mock: field narasi bersih di guard",
      not any(k.startswith("paths:") for k in mock_bad), str(sorted(mock_bad)))


# 11 — LLM sabotages ONE path item: only that item is dropped; the rest and other fields stay
class PathSaboteur(MockProvider):
    def structured_call(self, schema, system, user, retries=2):
        r = super().structured_call(schema, system, user)
        for p in r.paths:
            if p.key == "path.direct_outreach":
                p.why = "Jangan SCALE akuisisi dulu — ukur dulu (1) fase."
        return r


out3 = explain_session(PathSaboteur(), s, route_data=route_fixture)
check("butir jalur pelanggar dibuang dari hasil",
      all(p["key"] != "path.direct_outreach" for p in out3["paths"]),
      str([p["key"] for p in out3["paths"]]))
check("butir jalur bersih dipertahankan", any(p["key"] == "path.value_repricing" for p in out3["paths"]))
check("daftar dropped menyebut butir itu", "paths:path.direct_outreach" in out3["dropped"],
      str(out3["dropped"]))
check("field blok lain utuh", out3["do_title"] != "" and out3["summary"])

n_ok = sum(1 for _, ok, _ in _results if ok)
print(f"\nHASIL: {n_ok}/{len(_results)} PASS {'✅' if n_ok == len(_results) else '❌'}")
sys.exit(0 if n_ok == len(_results) else 1)
