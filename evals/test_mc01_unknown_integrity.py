"""MC01-4 — semantic unknown integrity (CIR-MC01 audit P1; su-* architecture & M4 planner preserved).

What is tested: claim_refs provenance + Goal binding at record time; answered-detection that
does not conflate word similarity with a real answer (echo/paraphrase/don't-know ≠ answered);
deterministic pruning; official candidates need a verifiable basis (accepted event + ≥1 active
ref); exclusion transparency (including when the candidate slots are full from the planner).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.reasoning.contract import MAX_UNCERTAINTY_CANDIDATES  # noqa: E402
from core.reasoning.semantic_unknowns import (  # noqa: E402
    merge_semantic_candidates,
    record_unknowns,
    unknown_id,
)

_PASS = 0
_FAIL = 0


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print("  OK  " + name)
    else:
        _FAIL += 1
        print("  GAGAL  " + name + (" - " + str(detail) if detail else ""))


class FakeSession:
    def __init__(self, goal_id="g-1", version=1):
        self.id = "s-mc01-u"
        self.semantic_unknowns = []
        self.state_graph = {"nodes": {}}
        self.events = []
        self.goal = {"goal_id": goal_id, "version": version}
        self.planner_log = []
        self.transcript = []


def add_event(s, eid, status="committed", turn=1):
    ev = {"event_id": eid, "seq": len(s.events), "role": "user", "status": status,
          "kind": "message", "turn": turn}
    s.events.append(ev)
    return ev


def add_claim(s, eid, cid, text, status="active"):
    s.state_graph["nodes"][cid] = {
        "id": cid, "verbatim": text, "status": status, "provenance": {"event_id": eid},
        "triple": {"subject": {"label": "x"}, "predicate": {"label": "y"}, "object": None}}


UNKNOWN = "berapa inquiry yang tidak ditindaklanjuti karena balasan lambat"
UNKNOWN_EN = "market demand for the smaller productized logo and guidelines package"


def u1_provenance_and_goal_binding():
    print("U1 — unknown membawa claim_refs + basis + pengikatan Goal saat direkam")
    s = FakeSession()
    ev = add_event(s, "ce-1")
    add_claim(s, "ce-1", "cl-0001-001", "dapat tiga sampai empat inquiry lewat referensi")
    record_unknowns(s, ev, [UNKNOWN])
    u = s.semantic_unknowns[0]
    check("basis=claims dengan claim_refs klaim aktif event itu",
          u["basis"] == "claims" and u["claim_refs"] == ["cl-0001-001"], u)
    check("pengikatan Goal tercatat (goal_id + version)",
          u["goal_id"] == "g-1" and u["goal_version"] == "1", u)

    s2 = FakeSession()
    ev2 = add_event(s2, "ce-2")          # event accepted WITHOUT any claim passing verification
    record_unknowns(s2, ev2, [UNKNOWN])
    u2 = s2.semantic_unknowns[0]
    check("unknown tanpa klaim diterima TETAP TERSIMPAN (basis event_only, tidak dibuang)",
          u2["basis"] == "event_only" and u2["claim_refs"] == [] and u2["status"] == "open")


def u2_answered_adversarial():
    print("U2 — ADVERSARIAL answered: gema pertanyaan & pernyataan tidak-tahu BUKAN jawaban")
    base = FakeSession()
    ev0 = add_event(base, "ce-0", turn=1)
    add_claim(base, "ce-0", "cl-0000-001", "konteks awal inquiry kantor")
    record_unknowns(base, ev0, [UNKNOWN])
    uid = unknown_id(UNKNOWN)

    # (a) echo of the question without new information → NOT answered
    s = FakeSession()
    s.semantic_unknowns = [dict(u) for u in base.semantic_unknowns]
    ev = add_event(s, "ce-a", turn=2)
    add_claim(s, "ce-a", "cl-a-001", "soal inquiry yang lambat ditindaklanjuti itu...")
    record_unknowns(s, ev, [])
    check("gema/parafrase pertanyaan TIDAK menandai terjawab",
          s.semantic_unknowns[0]["status"] == "open", s.semantic_unknowns[0])

    # (b) don't-know statement (similar vocabulary + the new word 'tahu'/'know') → NOT answered
    s = FakeSession()
    s.semantic_unknowns = [dict(u) for u in base.semantic_unknowns]
    ev = add_event(s, "ce-b", turn=2)
    add_claim(s, "ce-b", "cl-b-001", "saya belum tahu soal inquiry yang lambat ditindaklanjuti")
    record_unknowns(s, ev, [])
    check("'belum tahu …' = gap, BUKAN terjawab", s.semantic_unknowns[0]["status"] == "open")

    # (c) a real answer (new data: two/four/missed/yesterday) → answered + basis recorded
    s = FakeSession()
    s.semantic_unknowns = [dict(u) for u in base.semantic_unknowns]
    ev = add_event(s, "ce-c", turn=2)
    add_claim(s, "ce-c", "cl-c-001",
              "dua dari empat inquiry terlewat karena balasan lambat sekali kemarin")
    changes = record_unknowns(s, ev, [])
    u = s.semantic_unknowns[0]
    check("jawaban dengan info baru → terjawab (basis lexical_overlap_info_gain)",
          u["status"] == "answered" and u["answered_basis"] == "lexical_overlap_info_gain"
          and any(c["id"] == uid and c["change"] == "answered" for c in changes))


def u3_candidate_gating():
    print("U3 — kandidat resmi butuh dasar verifiable; eksklusi ber-alasan; planner tetap depan")
    def mk():
        s = FakeSession()
        ev = add_event(s, "ce-ok")
        add_claim(s, "ce-ok", "cl-ok-001", "klaim aktif penopang")
        record_unknowns(s, ev, [UNKNOWN])
        return s

    s = mk()
    merged, rep = merge_semantic_candidates(s, [])
    check("unknown ber-grounding ditawarkan sebagai kandidat",
          [x["id"] for x in merged if x.get("origin") == "semantic_observation"] == [unknown_id(UNKNOWN)]
          and rep["offered"] == [unknown_id(UNKNOWN)])

    s = mk()
    s.semantic_unknowns[0]["claim_refs"] = ["cl-ok-001"]
    s.state_graph["nodes"]["cl-ok-001"]["status"] = "superseded"   # correction nullifies the basis
    _, rep = merge_semantic_candidates(s, [])
    check("seluruh ref superseded → eksklusi basis_superseded",
          rep["excluded"] == [{"id": unknown_id(UNKNOWN), "why": "basis_superseded"}], rep)

    s = mk()
    s.semantic_unknowns[0]["claim_refs"] = []      # event-only: kept, not an official candidate
    _, rep = merge_semantic_candidates(s, [])
    check("event-only → eksklusi no_accepted_claim_basis (tetap tersimpan di sesi)",
          rep["excluded"][0]["why"] == "no_accepted_claim_basis" and len(s.semantic_unknowns) == 1)

    s = mk()
    s.events[0]["status"] = "understanding_failed"
    _, rep = merge_semantic_candidates(s, [])
    check("event sumber gagal dipahami → eksklusi source_event_not_accepted",
          rep["excluded"][0]["why"] == "source_event_not_accepted")

    s = mk()
    s.semantic_unknowns[0]["event_id"] = "ce-tak-ada"
    _, rep = merge_semantic_candidates(s, [])
    check("event sumber hilang → eksklusi source_event_missing",
          rep["excluded"][0]["why"] == "source_event_missing")

    s = mk()
    s.semantic_unknowns[0]["goal_id"] = "g-lama"
    _, rep = merge_semantic_candidates(s, [])
    check("Goal berganti → eksklusi goal_changed (freshness)",
          rep["excluded"][0]["why"] == "goal_changed")


def u4_capacity_transparency():
    print("U4 — slot kandidat penuh oleh planner → eksklusi candidate_capacity tercatat")
    s = FakeSession()
    ev = add_event(s, "ce-ok")
    add_claim(s, "ce-ok", "cl-ok-001", "klaim aktif penopang")
    record_unknowns(s, ev, [UNKNOWN])
    planner = [{"id": f"need-{i}", "kind": "need", "focus": {"type": "uncertainty", "id": f"need-{i}"},
                "label": f"kebutuhan planner {i}", "asked": 0, "askable": True, "needed_by": 1,
                "suggested_kind": "QUESTION", "legacy_wording": ""}
               for i in range(MAX_UNCERTAINTY_CANDIDATES)]
    merged, rep = merge_semantic_candidates(s, planner)
    n = MAX_UNCERTAINTY_CANDIDATES
    check(f"planner {n} slot tetap UTUH di depan; unknown tidak dimasukkan diam-diam",
          [x["id"] for x in merged] == [f"need-{i}" for i in range(n)])
    check("eksklusi capacity tercatat (no invisible drop) + unknown tetap terhitung open",
          rep["excluded"] == [{"id": unknown_id(UNKNOWN), "why": "candidate_capacity"}]
          and rep["open"] == 1)


def u5_deterministic_prune():
    print("U5 — pruning deterministik: hasil identik untuk urutan penyisipan berbeda")

    def build(insert_order):
        s = FakeSession()
        ev = add_event(s, "ce-p", turn=99)
        # the so.v1 contract caps 8 uncertainties per call → record in batches of 8 (24 open total)
        for chunk_start in range(0, 24, 8):
            record_unknowns(s, ev, [f"pertanyaan terbuka nomor {i} tentang produksi harian"
                                    for i in range(chunk_start, chunk_start + 8)])
        answered = [{"id": f"su-ans{i:04d}", "text": f"sudah dijawab nomor {i}",
                     "status": "answered", "event_id": "ce-p", "turn": (i % 3) + 1,
                     "claim_refs": [], "basis": "claims", "goal_id": "g-1", "goal_version": "1"}
                    for i in insert_order]
        s.semantic_unknowns.extend(answered)
        record_unknowns(s, ev, ["satu lagi yang terbuka"])     # trigger prune (24+12+1=37 > 32)
        return {u["id"] for u in s.semantic_unknowns}

    a = build(range(12))
    b = build(list(reversed(range(12))))
    check("survivor set identik untuk dua urutan penyisipan berbeda (deterministik)", a == b)
    # overflow=5 → the OLDEST answered (turn, id) is dropped first: turn1={0,3,6,9} then su-ans0001
    check("answered tertua (turn,id) terbuang lebih dulu; termuda bertahan; open selamat",
          "su-ans0011" in a and "su-ans0005" in a
          and not ({"su-ans0000", "su-ans0003", "su-ans0006", "su-ans0009", "su-ans0001"} & a),
          sorted(x for x in a if x.startswith("su-ans")))


def u6_presented_then_answered():
    """MC-04 (Oct 18, session e1704203f327): an unknown that is ASKED and then answered by the
    next turn's claims MUST become answered — the lexical heuristic can never match a
    cross-language answer, and an open-evergreen unknown feeds the critical eligibility pool
    (stuck chip)."""
    print("U6 — MC-04 presented-then-answered: tanya→jawab menutup unknown")
    uid = unknown_id(UNKNOWN_EN)
    s = FakeSession()
    ev0 = add_event(s, "ce-1", turn=1)
    add_claim(s, "ce-1", "cl-0001-001", "brand designer running two years")
    record_unknowns(s, ev0, [UNKNOWN_EN])
    check("unknown EN tercatam open", s.semantic_unknowns[0]["id"] == uid
          and s.semantic_unknowns[0]["status"] == "open", s.semantic_unknowns)

    ev1 = add_event(s, "ce-2", turn=2)
    add_claim(s, "ce-2", "cl-0002-001",
              "every month two three instagram direct messages ask how much for just a logo")
    changes = record_unknowns(s, ev1, [], presented_need_id=uid)
    u = next(x for x in s.semantic_unknowns if x["id"] == uid)
    check("unknown yang baru ditanyakan dijawab klaim giliran ini -> answered",
          u["status"] == "answered" and u.get("answered_basis") == "presented_then_user_claims", u)
    check("perubahan tercatat di audit changes",
          any(c["id"] == uid and c["change"] == "answered" for c in changes), changes)

    s2 = FakeSession()
    record_unknowns(s2, add_event(s2, "ce-a", turn=1), [UNKNOWN_EN])
    ev_gap = add_event(s2, "ce-b", turn=2)
    record_unknowns(s2, ev_gap, [], presented_need_id=uid)
    u2 = next(x for x in s2.semantic_unknowns if x["id"] == uid)
    check("event tanpa klaim tidak menutup unknown (ASK_CAP yang menjaga tanya-ulang)",
          u2["status"] == "open", u2)

    s3 = FakeSession()
    add_claim(s3, "ce-1", "cl-0001-001", "brand designer running two years")
    record_unknowns(s3, add_event(s3, "ce-1", turn=1), [UNKNOWN_EN])
    ev3 = add_event(s3, "ce-2", turn=2)
    add_claim(s3, "ce-2", "cl-0002-001", "some unrelated new claim")
    record_unknowns(s3, ev3, [], presented_need_id="requirement:delivery.spare_capacity")
    u3 = next(x for x in s3.semantic_unknowns if x["id"] == uid)
    check("need_id bukan su-* tidak menutup unknown semantik", u3["status"] == "open", u3)
    record_unknowns(s3, add_event(s3, "ce-3", turn=3), [UNKNOWN_EN])
    u3 = next(x for x in s3.semantic_unknowns if x["id"] == uid)
    check("unknown yang masih open direkam ulang = idempoten (tanpa jejak reopen palsu)",
          u3["status"] == "open" and u3.get("event_id") == "ce-1" and "reopened_event" not in u3, u3)

    # answered is no longer a candidate (clean critical pool) — before the reopen case
    planner_cands = [{"id": "requirement:delivery.spare_capacity", "kind": "requirement"}]
    merged, _report = merge_semantic_candidates(s, planner_cands)
    ids = [c["id"] for c in merged]
    check("unknown answered dikeluarkan dari kandidat uncertainty", uid not in ids, ids)

    # reopen LEGITIMATE from answered: understanding re-affirms that the same thing is still open
    ev4 = add_event(s, "ce-3", turn=3)
    add_claim(s, "ce-3", "cl-0003-001", "demand for the small package still untested this quarter")
    record_unknowns(s, ev4, [UNKNOWN_EN])
    u4 = next(x for x in s.semantic_unknowns if x["id"] == uid)
    check("pemahaman berikutnya boleh reopen unknown answered (sinyal termutakhir menang)",
          u4["status"] == "open" and u4.get("reopened_event") == "ce-3", u4)
    merged2, _r2 = merge_semantic_candidates(s, planner_cands)
    check("unknown hasil reopen kembali menjadi kandidat (open = kandidat)",
          uid in [c["id"] for c in merged2])


def u7_variant_of_answered():
    """MC-05 (Oct 18, session 7f2e13b1fcbe): understanding re-recording a paraphrase of an
    unknown that is already answered as a NEW unknown (different text-hash id) → evergreen
    critical pool. The variant must be born answered, and MUST NOT revive via the reopen path."""
    print("U7 — MC-05 varian parafrase dari unknown answered tidak lahir open")
    orig = "exact pricing for the proposed smaller starter brand package"
    variant = "exact price point to set for the starter package"
    other = "whether rp1.5 million will attract endless revision requests"
    uid_v = unknown_id(variant)
    s = FakeSession()
    add_claim(s, "ce-1", "cl-0001-001", "brand designer running two years")
    record_unknowns(s, add_event(s, "ce-1", turn=1), [orig])
    uid_o = s.semantic_unknowns[0]["id"]
    ev2 = add_event(s, "ce-2", turn=2)
    add_claim(s, "ce-2", "cl-0002-001", "thinking around rp1.2 to 1.5 million for starter package")
    record_unknowns(s, ev2, [], presented_need_id=uid_o)
    check("unknown asal answered (tanya→jawab)", next(
        x for x in s.semantic_unknowns if x["id"] == uid_o)["status"] == "answered")

    ev3 = add_event(s, "ce-3", turn=3)
    add_claim(s, "ce-3", "cl-0003-001", "some unrelated new claim this turn")
    changes = record_unknowns(s, ev3, [variant, other])
    uv = next((x for x in s.semantic_unknowns if x["id"] == uid_v), None)
    check("varian parafrase lahir answered (variant_of_answered), bukan open",
          uv is not None and uv["status"] == "answered"
          and uv.get("answered_basis") == "variant_of_answered", uv)
    check("audit mencatat recorded_answered_variant dengan asalnya",
          any(c.get("change") == "recorded_answered_variant" and c.get("variant_of") == uid_o
              for c in changes), changes)
    uo = next(x for x in s.semantic_unknowns if x["text"] == other)
    check("topik benar-benar berbeda tetap open (bukan kena dedup berlebih)",
          uo["status"] == "open", uo)

    # observation repeats the variant wording → NO reopen
    record_unknowns(s, add_event(s, "ce-4", turn=4), [variant])
    uv = next(x for x in s.semantic_unknowns if x["id"] == uid_v)
    check("varian tidak bangkit lewat reopen (anti evergreen)", uv["status"] == "answered", uv)


def main() -> int:
    u1_provenance_and_goal_binding()
    u2_answered_adversarial()
    u3_candidate_gating()
    u4_capacity_transparency()
    u5_deterministic_prune()
    u6_presented_then_answered()
    u7_variant_of_answered()
    print(f"\n{'=' * 62}\nMC01-4 unknown integrity: {_PASS} OK, {_FAIL} GAGAL")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
