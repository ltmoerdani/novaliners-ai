"""Gate T-NavigationLinks — cross-route navigation link store (navigation doc).

Key properties under test: admission (shape/provenance/route-node/CLOSED/scope),
cycles & self-loops rejected, append idempotency (LAST row wins), and
latest_links (last-row-wins + context filter). Pure unit tests + temp JSONL;
no real route store / LLM.

Run: cd mvp && .venv/bin/python evals/test_navigation_links.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from itertools import count
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # mvp/

from store.navigation_links import (  # noqa: E402
    LINK_KINDS,
    NavigationLinkError,
    _path,
    admission_problems,
    append_link,
    latest_links,
    link_id_of,
    list_rows,
)

RESULTS: list[tuple[str, bool, str]] = []
BASE = tempfile.mkdtemp(prefix="navigation-links-")
_SEQ = count()


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as exc:
        RESULTS.append((name, False, str(exc)))
    except Exception as exc:  # pragma: no cover — unexpected failures must stay visible
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def _uid() -> str:
    return f"user{next(_SEQ)}"


def _routes(*, route_id="r-1", revision_no=1, lineage_status="OPEN",
            nodes=("n1", "n2")):
    return [{
        "route_id": route_id,
        "revision_no": revision_no,
        "lineage_status": lineage_status,
        "nodes": [{"node_id": n} for n in nodes],
    }]


def _rn(route_id="r-1", node_id="n1", route_revision=1):
    return {"route_id": route_id, "node_id": node_id,
            "route_revision": route_revision}


def _mv(move_id="m-1"):
    return {"move_id": move_id}


def _link(frm, to, *, kind="BRANCH_FROM", declaration_ref="decl-1",
          source_event_refs=("evt-1",), evidence_refs=(), context_id=None):
    link = {
        "kind": kind,
        "from": frm,
        "to": to,
        "declaration_ref": declaration_ref,
        "source_event_refs": list(source_event_refs),
        "evidence_refs": list(evidence_refs),
    }
    if context_id is not None:
        link["context_id"] = context_id
    return link


def _raises(fn) -> None:
    try:
        fn()
    except NavigationLinkError:
        return
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"error salah tipe: {type(exc).__name__}: {exc}")
    raise AssertionError("harusnya NavigationLinkError")


# --------------------------------------------------------------- admission OK
def t_valid_branch_admitted() -> None:
    u = _uid()
    link = _link(_rn(node_id="n1"), _rn(node_id="n2"))
    assert admission_problems(link, routes=_routes(), existing=[],
                              context_id=None) == [], "link sah harus admissible"
    row = append_link(u, link, base_dir=BASE)
    assert row["kind"] == "BRANCH_FROM" and row["status"] == "ACCEPTED"
    assert row["link_id"].startswith("nl-") and len(row["link_id"]) == 11, row["link_id"]
    assert isinstance(row["created_ts"], int)
    assert row["from"] == {"route_id": "r-1", "node_id": "n1", "route_revision": 1}
    rows = list_rows(u, base_dir=BASE)
    assert len(rows) == 1 and rows[0] == row


def t_move_endpoint_admitted() -> None:
    u = _uid()
    link = _link(_mv("m-1"), _rn(node_id="n2"))
    assert admission_problems(link, routes=_routes(), existing=[],
                              context_id=None) == [], "endpoint move harus sah"
    row = append_link(u, link, base_dir=BASE)
    assert row["from"] == {"move_id": "m-1"}


# --------------------------------------------------------------- provenance
def t_missing_declaration_ref_rejected() -> None:
    u = _uid()
    link = _link(_rn(), _rn(node_id="n2"))
    del link["declaration_ref"]
    probs = admission_problems(link, routes=_routes(), existing=[], context_id=None)
    assert any("declaration_ref" in p for p in probs), probs
    _raises(lambda: append_link(u, link, base_dir=BASE))


def t_empty_provenance_rejected() -> None:
    u = _uid()
    link = _link(_rn(), _rn(node_id="n2"), source_event_refs=(), evidence_refs=())
    probs = admission_problems(link, routes=_routes(), existing=[], context_id=None)
    assert any("provenance" in p for p in probs), probs
    _raises(lambda: append_link(u, link, base_dir=BASE))


def t_evidence_only_provenance_ok() -> None:
    u = _uid()
    link = _link(_rn(), _rn(node_id="n2"), source_event_refs=(),
                 evidence_refs=("ev-1",))
    assert admission_problems(link, routes=_routes(), existing=[],
                              context_id=None) == []
    append_link(u, link, base_dir=BASE)


# ------------------------------------------------------------------- shape
def t_malformed_endpoint_rejected() -> None:
    u = _uid()
    bad = {"route_id": "r-1", "node_id": "n1"}  # route_revision missing
    link = _link(bad, _rn(node_id="n2"))
    assert admission_problems(link, routes=_routes(), existing=[], context_id=None)
    _raises(lambda: append_link(u, link, base_dir=BASE))
    bad_rev = {"route_id": "r-1", "node_id": "n1", "route_revision": 0}
    probs = admission_problems(_link(bad_rev, _rn(node_id="n2")),
                               routes=_routes(), existing=[], context_id=None)
    assert probs, "route_revision 0 harus ditolak"
    extra = {"route_id": "r-1", "node_id": "n1", "route_revision": 1, "x": 1}
    probs2 = admission_problems(_link(extra, _rn(node_id="n2")),
                                routes=_routes(), existing=[], context_id=None)
    assert probs2, "field asing pada endpoint harus ditolak"


# --------------------------------------------------------------- route checks
def t_orphan_node_rejected() -> None:
    link = _link(_rn(node_id="ghost"), _rn(node_id="n2"))
    probs = admission_problems(link, routes=_routes(nodes=("n1", "n2")),
                               existing=[], context_id=None)
    assert any("yatim" in p for p in probs), probs


def t_stale_revision_rejected() -> None:
    link = _link(_rn(node_id="n1", route_revision=1), _rn(node_id="n2"))
    probs = admission_problems(link, routes=_routes(revision_no=2, nodes=("n1", "n2")),
                               existing=[], context_id=None)
    assert any("STALE" in p for p in probs), probs


def t_closed_route_rejected() -> None:
    link = _link(_rn(node_id="n1"), _rn(node_id="n2"))
    probs = admission_problems(link, routes=_routes(lineage_status="CLOSED"),
                               existing=[], context_id=None)
    assert any("CLOSED" in p for p in probs), probs


def t_unknown_route_rejected() -> None:
    link = _link(_rn(route_id="r-hantu"), _rn(node_id="n2"))
    probs = admission_problems(link, routes=_routes(), existing=[], context_id=None)
    assert probs, "route tak ada harus ditolak"


# ------------------------------------------------------------------- scope
def t_scope_mismatch_rejected_legacy_none_matches() -> None:
    link = _link(_rn(), _rn(node_id="n2"), context_id="c-1")
    probs = admission_problems(link, routes=_routes(), existing=[], context_id="c-2")
    assert any("c-1" in p for p in probs), probs
    legacy = _link(_rn(), _rn(node_id="n2"))  # context_id absent = legacy wildcard
    assert admission_problems(legacy, routes=_routes(), existing=[],
                              context_id="c-2") == [], "legacy None cocok konteks apa pun"


# -------------------------------------------------------------- loop / cycle
def t_self_loop_rejected() -> None:
    u = _uid()
    link = _link(_rn(node_id="n1"), _rn(node_id="n1"))
    probs = admission_problems(link, routes=_routes(), existing=[], context_id=None)
    assert any("self-loop" in p for p in probs), probs
    _raises(lambda: append_link(u, link, base_dir=BASE))


def t_cycle_rejected() -> None:
    u = _uid()
    r = _routes()
    a = _link(_rn(node_id="n1"), _rn(node_id="n2"), declaration_ref="d-a")
    append_link(u, a, base_dir=BASE)
    b = _link(_rn(node_id="n2"), _rn(node_id="n1"), declaration_ref="d-b")
    probs = admission_problems(b, routes=r, existing=list_rows(u, base_dir=BASE),
                               context_id=None)
    assert any("siklus" in p for p in probs), probs
    _raises(lambda: append_link(u, b, base_dir=BASE))


# ------------------------------------------------------- idempotency & conflicts
def t_double_append_idempotent() -> None:
    u = _uid()
    link = _link(_rn(node_id="n1"), _rn(node_id="n2"))
    r1 = append_link(u, link, base_dir=BASE)
    r2 = append_link(u, link, base_dir=BASE)
    assert r1["link_id"] == r2["link_id"], "link_id harus stabil"
    assert r1 == r2, "append kedua harus mengembalikan baris lama"
    assert len(list_rows(u, base_dir=BASE)) == 1, "tidak boleh ada baris duplikat"


def t_conflict_diff_declaration_rejected() -> None:
    u = _uid()
    a = _link(_rn(node_id="n1"), _rn(node_id="n2"), declaration_ref="d-1")
    append_link(u, a, base_dir=BASE)
    b = _link(_rn(node_id="n1"), _rn(node_id="n2"), declaration_ref="d-2")
    probs = admission_problems(b, routes=_routes(),
                               existing=list_rows(u, base_dir=BASE), context_id=None)
    assert any("konflik" in p for p in probs), probs
    _raises(lambda: append_link(u, b, base_dir=BASE))


# ------------------------------------------------------------- latest_links
def t_latest_last_row_wins() -> None:
    u = _uid()
    p = _path(u, BASE)
    p.parent.mkdir(parents=True, exist_ok=True)
    row1 = {
        "link_id": "nl-manual1", "kind": "BRANCH_FROM",
        "from": _rn(node_id="n1"), "to": _rn(node_id="n2"),
        "declaration_ref": "d", "source_event_refs": ["ev"], "evidence_refs": [],
        "context_id": "c-1", "status": "ACCEPTED", "created_ts": 1,
    }
    row2 = dict(row1)
    row2["created_ts"] = 2
    row2["declaration_ref"] = "d2"
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(row1) + "\n" + json.dumps(row2) + "\n")
    out = latest_links(u, base_dir=BASE)
    assert len(out) == 1, out
    assert out[0]["created_ts"] == 2 and out[0]["declaration_ref"] == "d2", out


def t_latest_context_filter() -> None:
    u = _uid()
    c1 = _link(_rn(node_id="n1"), _rn(node_id="n2"), context_id="c-1")
    c2 = _link(_rn(node_id="n1"), _rn(node_id="n2"), declaration_ref="d-2",
               context_id="c-2")
    append_link(u, c1, base_dir=BASE)
    append_link(u, c2, base_dir=BASE)
    assert len(latest_links(u, base_dir=BASE)) == 2
    only1 = latest_links(u, base_dir=BASE, context_id="c-1")
    assert len(only1) == 1 and only1[0]["context_id"] == "c-1", only1
    assert latest_links(u, base_dir=BASE, context_id="nope") == []


def t_link_id_stable_and_sensitive() -> None:
    a = link_id_of("BRANCH_FROM", _rn(node_id="n1"), _mv("m-1"), "d-1", "c-1")
    b = link_id_of("BRANCH_FROM", {"node_id": "n1", "route_revision": 1,
                                   "route_id": "r-1"}, _mv("m-1"), "d-1", "c-1")
    assert a == b, "urutan kunci dict tidak boleh mengubah link_id"
    assert a.startswith("nl-") and len(a) == 11
    c = link_id_of("BRANCH_FROM", _rn(node_id="n1"), _mv("m-1"), "d-2", "c-1")
    assert a != c, "declaration_ref beda harus beda link_id"
    assert "BRANCH_FROM" in LINK_KINDS and "MERGES_INTO" in LINK_KINDS


ALL = [
    ("branch valid admitted", t_valid_branch_admitted),
    ("endpoint move admitted", t_move_endpoint_admitted),
    ("declaration_ref hilang ditolak", t_missing_declaration_ref_rejected),
    ("provenance kosong ditolak", t_empty_provenance_rejected),
    ("provenance evidence-only sah", t_evidence_only_provenance_ok),
    ("endpoint malformed ditolak", t_malformed_endpoint_rejected),
    ("node yatim ditolak", t_orphan_node_rejected),
    ("revisi STALE ditolak", t_stale_revision_rejected),
    ("route CLOSED ditolak", t_closed_route_rejected),
    ("route tak ada ditolak", t_unknown_route_rejected),
    ("scope mismatch ditolak / legacy None cocok", t_scope_mismatch_rejected_legacy_none_matches),
    ("self-loop ditolak", t_self_loop_rejected),
    ("siklus ditolak", t_cycle_rejected),
    ("append ganda idempotent", t_double_append_idempotent),
    ("konflik declaration_ref ditolak", t_conflict_diff_declaration_rejected),
    ("latest last-row-wins", t_latest_last_row_wins),
    ("latest filter konteks", t_latest_context_filter),
    ("link_id stabil & sensitif", t_link_id_stable_and_sensitive),
]


def main() -> int:
    for name, fn in ALL:
        check(name, fn)
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, msg in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {msg}" if msg else ""))
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS - navigation links")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
