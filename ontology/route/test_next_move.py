"""D6 (int 08 §8.4) — NextMove selector v1.

Every selector output is written as an instance document and then checked by the
REAL `validate_route.main()` (not a copy): output↔kind match
(ACTION↔EXECUTE, EVIDENCE_REQUEST↔VERIFY, QUESTION↔RESOLVE_APPLICABILITY,
HOLD without ref) + frontier_ref integrity + frontier validity.
"""
from __future__ import annotations

import copy
import io
import json
import random
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # mvp/

import store.adjudication_ledger as ledger  # noqa: E402

_tmp = Path(tempfile.mkdtemp())
ledger._LEDGER_ROOT = _tmp / "ledger"

from core.schema.evidence import EvidenceItem  # noqa: E402
from ontology.route import validate_route as vr  # noqa: E402
from ontology.route.next_move import select_next_move  # noqa: E402
from ontology.route.session_bridge import run_session_route  # noqa: E402
from ontology.route.strategies import active_template_library  # noqa: E402
from store.memory import Session  # noqa: E402

LIB = {t["template_id"]: t for t in active_template_library()}


def _session(uid: str, texts: list[str]) -> Session:
    s = Session.__new__(Session)
    s.user_id = uid
    s.evidence = [EvidenceItem(id=f"e{i}", signal=t, source_quote=t,
                               level="self_reported", topic="REVENUE_STATE")
                  for i, t in enumerate(texts)]
    return s


def _routes(uid: str, texts: list[str], tids: list[str]) -> list[dict]:
    return [run_session_route(_session(uid, texts), LIB[t], base_dir=_tmp)
            for t in tids]


def _validator_ok(routes: list[dict], nm: dict | None) -> list[str]:
    """Write {lineages, frontier, next_move} to a temporary instances dir, then
    run the real validate_route.main()."""
    d = Path(tempfile.mkdtemp())
    doc = {"lineages": [r["lineage"] for r in routes],
           "frontier": [e for r in routes for e in r["frontier"]]}
    if nm is not None:
        doc["next_move"] = {k: v for k, v in nm.items()
                            if k in ("output", "frontier_ref")}
    (d / "doc.json").write_text(json.dumps(doc), encoding="utf-8")
    old = vr.INSTANCES
    vr.INSTANCES = d
    vr.errors.clear()
    vr.warnings.clear()
    try:
        with redirect_stdout(io.StringIO()):
            rc = vr.main()
    finally:
        vr.INSTANCES = old
    return [] if rc == 0 else list(vr.errors)


def t_tanpa_route_none() -> None:
    assert select_next_move([]) is None
    r = _routes("nm-closed", ["Saya konsultan jasa."], ["direct_outreach_v1"])[0]
    closed = copy.deepcopy(r)
    closed["lineage"]["lineage_status"] = "CLOSED"
    assert select_next_move([closed]) is None


def t_action_hard_dulu() -> None:
    routes = _routes("nm-act", ["Saya konsultan, jual jasa ke klien bisnis."],
                     ["direct_outreach_v1"])
    nm = select_next_move(routes)
    assert nm["output"] == "ACTION", nm
    node = next(n for n in routes[0]["lineage"]["revisions"][-1]["nodes"]
                if n["node_id"] == nm["frontier_ref"])
    assert node["strength"] == "hard", node
    assert node["resolves"] == ["access.icp"], node  # akar dependency
    assert not _validator_ok(routes, nm)


def t_question_sebelum_action() -> None:
    # Koreksi policy 19 Okt 2026 (docstring next_move.py): EXECUTE (2) di atas
    # QUESTION (3) — applicability adalah properti PER-ROUTE; sibling yang
    # UNDETERMINED tidak boleh membekukan route yang sudah APPLIES.
    routes = _routes("nm-q", ["Saya konsultan, jual jasa ke klien bisnis."],
                     ["direct_outreach_v1", "paid_channel_test_v1"])
    kinds = {r["lineage"]["applicability"]["status"] for r in routes}
    assert kinds == {"APPLIES", "UNDETERMINED"}, kinds
    nm = select_next_move(routes)
    applies = next(r for r in routes
                   if r["lineage"]["applicability"]["status"] == "APPLIES")
    und = next(r for r in routes
               if r["lineage"]["applicability"]["status"] == "UNDETERMINED")
    # ACTION pada route yang APPLIES — bukan QUESTION yang membekukan, dan
    # TIDAK pernah mengeksekusi route yang belum pasti berlaku.
    assert nm["output"] == "ACTION", nm
    assert nm["route_id"] == applies["lineage"]["route_id"], nm
    assert nm["route_id"] != und["lineage"]["route_id"], nm
    # Route UNDETERMINED sendirian tetap menghasilkan QUESTION (Know-Before-You-Move).
    solo = select_next_move([copy.deepcopy(und)])
    assert solo["output"] == "QUESTION", solo
    assert solo["frontier_ref"] == und["lineage"]["route_id"], solo
    assert not _validator_ok(routes, nm)


def t_evidence_request_paling_depan() -> None:
    routes = _routes("nm-v", ["Saya konsultan, jual jasa ke klien bisnis."],
                     ["direct_outreach_v1", "paid_channel_test_v1"])
    r = copy.deepcopy(next(x for x in routes
                           if x["lineage"]["applicability"]["status"] == "APPLIES"))
    tgt = r["frontier"][0]["node"]
    for n in r["lineage"]["revisions"][-1]["nodes"]:
        if n["node_id"] == tgt:
            n["execution_view"] = "EXECUTED"
    r["frontier"][0]["kind"] = "VERIFY"
    others = [x for x in routes if x["lineage"]["route_id"] != r["lineage"]["route_id"]]
    nm = select_next_move(others + [r])
    assert nm["output"] == "EVIDENCE_REQUEST" and nm["frontier_ref"] == tgt, nm
    assert not _validator_ok(others + [r], nm)


def t_hold_tanpa_ref() -> None:
    r = copy.deepcopy(_routes("nm-h", ["Saya konsultan jasa."],
                              ["direct_outreach_v1"])[0])
    r["frontier"] = []
    nm = select_next_move([r])
    assert nm["output"] == "HOLD" and "frontier_ref" not in nm, nm
    assert not _validator_ok([r], nm)


def t_deterministik_urutan_input() -> None:
    routes = _routes("nm-d", ["Klien aktif kami minta rekomendasi harga; "
                              "saya konsultan jasa."], list(LIB))
    base = select_next_move(routes)
    for seed in range(5):
        shuf = routes[:]
        random.Random(seed).shuffle(shuf)
        assert select_next_move(shuf) == base, seed
    assert not _validator_ok(routes, base)


TESTS = [t_tanpa_route_none, t_action_hard_dulu, t_question_sebelum_action,
         t_evidence_request_paling_depan, t_hold_tanpa_ref,
         t_deterministik_urutan_input]


def main() -> int:
    fails = 0
    for fn in TESTS:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            fails += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(TESTS) - fails}/{len(TESTS)} next-move tests passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
