"""Store NavigationLink ADMITTED PER-USER — cross-route navigation links
(append-only JSONL, pattern of store/route_lineages.py + store/route_execution.py).

A link is a DIRECTED RELATION between node refs: leaving one route
(BRANCH_FROM) or entering another route (MERGES_INTO). Only ADMITTED links
are written; admission rejects orphan endpoints, STALE revisions,
CLOSED routes, cross-context, empty provenance, self-loops, and cycles.
This store deliberately does NOT know route definitions (it does not import the composer):
admission_problems receives the route list from the caller, while
append_link can only validate shape/provenance/cycles.

Idempotency: link identity = link_id (canonical hash kind+from+to+
declaration_ref+context). Rewriting the same link_id when it is already
the LAST row = no-op (the old row is returned, without append).

The user identity invariant is validated by store.user_scope (SHARED helper) —
canonical pattern ^[A-Za-z0-9_-]{1,128}$, rejects traversal. stdlib +
store.user_scope only.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from store.user_scope import validate_user_id

_BASE = Path(__file__).parent / "workspaces"

LINK_KINDS = ("BRANCH_FROM", "MERGES_INTO")

_ROUTE_KEYS = frozenset({"route_id", "node_id", "route_revision"})
_MOVE_KEYS = frozenset({"move_id"})


class NavigationLinkError(ValueError):
    """Link does not satisfy the admission rules (shape/provenance/cycle)."""


def _path(user_id: str, base_dir: Path | str | None = None) -> Path:
    """Per-user JSONL path; user_id fail-closed via store.user_scope."""
    validate_user_id(user_id)
    root = Path(base_dir) if base_dir else _BASE
    return root / user_id / "navigation_links.jsonl"


# --------------------------------------------------------------- shape helpers
def _endpoint_kind(ref: Any) -> str | None:
    """route if exactly {route_id,node_id,route_revision}; move if
    exactly {move_id}; otherwise None (foreign shape)."""
    if not isinstance(ref, dict):
        return None
    keys = set(ref)
    if keys == _MOVE_KEYS:
        return "move"
    if keys == _ROUTE_KEYS:
        return "route"
    return None


def _valid_route_node(ref: dict[str, Any]) -> bool:
    rev = ref.get("route_revision")
    return (
        isinstance(ref.get("route_id"), str) and ref["route_id"] != ""
        and isinstance(ref.get("node_id"), str) and ref["node_id"] != ""
        and isinstance(rev, int) and not isinstance(rev, bool) and rev >= 1
    )


def _valid_move(ref: dict[str, Any]) -> bool:
    return isinstance(ref.get("move_id"), str) and ref["move_id"] != ""


def _endpoint_problem(ref: Any, role: str) -> str | None:
    kind = _endpoint_kind(ref)
    if kind is None:
        return (f"{role}: endpoint wajib tepat {{route_id, node_id, route_revision}} "
                f"atau {{move_id}}")
    if kind == "move":
        return None if _valid_move(ref) else f"{role}: move_id wajib string non-kosong"
    return None if _valid_route_node(ref) else (
        f"{role}: route_id/node_id wajib string non-kosong dan route_revision int >= 1")


def _norm_ref(ref: dict[str, Any]) -> dict[str, Any]:
    """Canonical endpoint copy (drop key order / foreign fields)."""
    if _endpoint_kind(ref) == "move":
        return {"move_id": ref["move_id"]}
    return {
        "route_id": ref.get("route_id"),
        "node_id": ref.get("node_id"),
        "route_revision": ref.get("route_revision"),
    }


def _node_key(ref: dict[str, Any]) -> str | None:
    """Graph ref: route-node -> 'route_id:node_id'; move -> 'move:move_id'."""
    kind = _endpoint_kind(ref)
    if kind == "move":
        return f"move:{ref.get('move_id')}"
    if kind == "route":
        return f"{ref.get('route_id')}:{ref.get('node_id')}"
    return None


def _canon_ref(ref: Any) -> Any:
    if _endpoint_kind(ref) is not None:
        return _norm_ref(ref)
    if isinstance(ref, dict):
        return {key: ref[key] for key in sorted(ref, key=str)}
    return ref


def _ctx_canon(context_id: Any) -> Any:
    """None and '' are equivalent for identity/conflict (legacy None)."""
    return "" if context_id is None else context_id


def link_id_of(kind: str, from_ref: dict[str, Any], to_ref: dict[str, Any],
               declaration_ref: str, context_id: str | None = "") -> str:
    """'nl-' + sha1 hex[:8] of a stable canonical serialization. Endpoint keys
    are sorted & fields normalized so the dict key order does not
    change the identity."""
    payload = {
        "kind": kind,
        "from": _canon_ref(from_ref),
        "to": _canon_ref(to_ref),
        "declaration_ref": declaration_ref,
        "context_id": _ctx_canon(context_id),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return "nl-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:8]


def _link_id_for(link: dict[str, Any]) -> str | None:
    kind = link.get("kind")
    decl = link.get("declaration_ref")
    if kind not in LINK_KINDS or not isinstance(decl, str) or decl == "":
        return None
    frm, to = link.get("from"), link.get("to")
    if _endpoint_problem(frm, "from") or _endpoint_problem(to, "to"):
        return None
    return link_id_of(kind, _norm_ref(frm), _norm_ref(to), decl,
                      link.get("context_id"))


# ------------------------------------------------------------- graph cycle
def _accepted_edges(existing: list[dict[str, Any]] | None) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for row in existing or []:
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        if status is not None and status != "ACCEPTED":
            continue
        frm, to = row.get("from"), row.get("to")
        a = _node_key(frm) if _endpoint_kind(frm) else None
        b = _node_key(to) if _endpoint_kind(to) else None
        if a is not None and b is not None:
            edges.append((a, b))
    return edges


def _reaches(edges: list[tuple[str, str]], start: str | None,
             goal: str | None) -> bool:
    if start is None or goal is None:
        return False
    adj: dict[str, list[str]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    stack = [start]
    seen: set[str] = set()
    while stack:
        cur = stack.pop()
        if cur == goal:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(adj.get(cur, ()))
    return False


# ------------------------------------------------------------------ admission
def admission_problems(link: dict[str, Any], *, routes: list[dict[str, Any]] | None,
                       existing: list[dict[str, Any]],
                       context_id: str | None) -> list[str]:
    """Admission rules — PURE, no I/O. [] = admissible.

    routes=None skips validation of route/revision/node existence (used by
    append_link, which has no route definitions); routes=[] means "no
    route", so route-node endpoints are reported as orphans.
    """
    problems: list[str] = []
    if not isinstance(link, dict):
        return ["link wajib dict"]

    # 1. kind
    kind = link.get("kind")
    if kind not in LINK_KINDS:
        problems.append(f"kind {kind!r} tidak termasuk {LINK_KINDS}")

    # 2. shape endpoint
    frm, to = link.get("from"), link.get("to")
    f_prob = _endpoint_problem(frm, "from")
    t_prob = _endpoint_problem(to, "to")
    if f_prob:
        problems.append(f_prob)
    if t_prob:
        problems.append(t_prob)
    from_ok, to_ok = f_prob is None, t_prob is None
    norm_from = _norm_ref(frm) if from_ok else None
    norm_to = _norm_ref(to) if to_ok else None

    # 3. route exists / revision / node / CLOSED
    if routes is not None:
        index: dict[str, dict[str, Any]] = {}
        for r in routes:
            if isinstance(r, dict) and isinstance(r.get("route_id"), str):
                index[r["route_id"]] = r
        for role, ref, ok in (("from", frm, from_ok), ("to", to, to_ok)):
            if not ok or _endpoint_kind(ref) != "route":
                continue
            route = index.get(ref["route_id"])
            if route is None:
                problems.append(f"{role}: route {ref['route_id']!r} tidak ada di routes")
                continue
            status = route.get("lineage_status")
            if status is None and isinstance(route.get("lineage"), dict):
                status = route["lineage"].get("lineage_status")
            if status == "CLOSED":
                problems.append(
                    f"{role}: route {ref['route_id']!r} CLOSED — tidak boleh menerima link baru")
            current = route.get("revision_no")
            if current is None:
                problems.append(f"{role}: route {ref['route_id']!r} tanpa revision_no")
            elif ref["route_revision"] != current:
                problems.append(
                    f"{role}: revisi {ref['route_revision']} STALE — route "
                    f"{ref['route_id']!r} kini revisi {current}")
            node_ids = {n.get("node_id") for n in (route.get("nodes") or [])
                        if isinstance(n, dict)}
            if ref["node_id"] not in node_ids:
                problems.append(
                    f"{role}: node {ref['node_id']!r} yatim/tidak ada di route "
                    f"{ref['route_id']!r}")

    # 4. context scope (legacy None matches any context)
    link_ctx = link.get("context_id")
    if context_id is not None and link_ctx is not None and link_ctx != context_id:
        problems.append(
            f"context_id {link_ctx!r} tidak cocok dengan konteks {context_id!r}")

    # 5. provenance
    decl = link.get("declaration_ref")
    decl_ok = isinstance(decl, str) and decl != ""
    if not decl_ok:
        problems.append("declaration_ref wajib string non-kosong")

    ser = link.get("source_event_refs")
    ser_ok = True
    if ser is None:
        ser = []
    elif not isinstance(ser, list):
        problems.append("source_event_refs wajib list string non-kosong")
        ser_ok = False
        ser = []
    elif any(not (isinstance(x, str) and x != "") for x in ser):
        problems.append("source_event_refs wajib berisi string non-kosong")
        ser_ok = False

    ev = link.get("evidence_refs")
    ev_ok = True
    if ev is None:
        ev = []
    elif not isinstance(ev, list):
        problems.append("evidence_refs wajib list string non-kosong")
        ev_ok = False
        ev = []
    elif any(not (isinstance(x, str) and x != "") for x in ev):
        problems.append("evidence_refs wajib berisi string non-kosong")
        ev_ok = False
    if ser_ok and ev_ok and not ser and not ev:
        problems.append("provenance kosong: minimal satu source_event_refs atau evidence_refs")

    # 6. siklus
    if from_ok and to_ok and norm_from is not None and norm_to is not None:
        cand_id = (link_id_of(kind, norm_from, norm_to, decl, link_ctx)
                   if kind in LINK_KINDS and decl_ok else None)
        existing_ids = {
            row.get("link_id") for row in (existing or [])
            if isinstance(row, dict) and (row.get("status") in (None, "ACCEPTED"))
        }
        key_from, key_to = _node_key(norm_from), _node_key(norm_to)
        if key_from == key_to:
            problems.append(f"self-loop {key_from!r} — from dan to menunjuk node yang sama")
        elif cand_id is None or cand_id not in existing_ids:
            if _reaches(_accepted_edges(existing), key_to, key_from):
                problems.append(f"siklus: {key_from} -> {key_to} menutup siklus")

    # 7. duplicate/conflict (same link_id = no-op, not a problem)
    if from_ok and to_ok and norm_from is not None and norm_to is not None and decl_ok:
        cand_ctx = _ctx_canon(link_ctx)
        for row in existing or []:
            if not isinstance(row, dict) or row.get("kind") != kind:
                continue
            rf, rt = row.get("from"), row.get("to")
            if _endpoint_kind(rf) is None or _endpoint_kind(rt) is None:
                continue
            if _norm_ref(rf) != norm_from or _norm_ref(rt) != norm_to:
                continue
            if _ctx_canon(row.get("context_id")) != cand_ctx:
                continue
            if row.get("declaration_ref") != decl:
                problems.append(
                    f"konflik: link (kind, from, to, context) sudah ada dengan "
                    f"declaration_ref {row.get('declaration_ref')!r}")
                break

    return problems


# --------------------------------------------------------------------- I/O
def list_rows(user_id: str,
              base_dir: Path | str | None = None) -> list[dict[str, Any]]:
    p = _path(user_id, base_dir)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue  # a broken line must not break the user flow
        if isinstance(data, dict):
            rows.append(data)
    return rows


def append_link(user_id: str, link: dict[str, Any],
                base_dir: Path | str | None = None) -> dict[str, Any]:
    """Append one ADMITTED link. Idempotent: if link_id is already the
    LAST row, return that row without append. Raise NavigationLinkError
    on shape/provenance/cycle/conflict."""
    p = _path(user_id, base_dir)
    existing = list_rows(user_id, base_dir)

    if not isinstance(link, dict):
        raise NavigationLinkError("link harus dict")
    cand = dict(link)
    if cand.get("source_event_refs") is None:
        cand["source_event_refs"] = []
    if cand.get("evidence_refs") is None:
        cand["evidence_refs"] = []
    cand["context_id"] = cand.get("context_id")

    link_id = _link_id_for(cand)
    if link_id is not None and existing and existing[-1].get("link_id") == link_id:
        return existing[-1]

    problems = admission_problems(cand, routes=None, existing=existing,
                                  context_id=None)
    if problems:
        raise NavigationLinkError("; ".join(problems))

    row = {
        "link_id": link_id,
        "kind": cand["kind"],
        "from": _norm_ref(cand["from"]),
        "to": _norm_ref(cand["to"]),
        "declaration_ref": cand["declaration_ref"],
        "source_event_refs": list(cand["source_event_refs"]),
        "evidence_refs": list(cand["evidence_refs"]),
        "context_id": cand.get("context_id"),
        "status": "ACCEPTED",
        "created_ts": int(time.time()),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def latest_links(user_id: str, base_dir: Path | str | None = None,
                 context_id: str | None = None) -> list[dict[str, Any]]:
    """The LAST link per link_id wins (a new row overrides the old state).
    context_id != None filters rows with the exact same context_id."""
    out: dict[str, dict[str, Any]] = {}
    for row in list_rows(user_id, base_dir):
        if context_id is not None and row.get("context_id") != context_id:
            continue
        lid = row.get("link_id")
        if isinstance(lid, str) and lid != "":
            out[lid] = row
    return list(out.values())
