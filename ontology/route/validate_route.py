#!/usr/bin/env python
"""Load-time validator for the NOVALINERS ROUTE SCHEMA v0.1.

Enforces the Route Ontology contract (internal-docs — FINAL CONTRACT
26 Sep 2026: decisions #1–#5 + review §3–§4 + Model B + tri-state):

1. Schema self-check  : schema enums == CONTRACT_ENUMS (contract mirror — anti drift)
                        + no banned value in the schema enums
2. RouteLineage       : route_id uuid (INV-R15) · reconciliation_key EXACTLY
                        {goal_anchor, strategy_id, scope_anchor} (INV-R13/R14)
                        · motion ∈ enum & NOT in the key · lineage_status enum
                        · reopened_from/successor_of = separate link (INV-R20)
3. Applicability      : 3 values · NOT_APPLICABLE requires evidence (INV-R2)
4. RouteNode          : resolves at least 1 (CORRECT-1: [] = composition gap, NOT
                        a node state) · strength enum · satisfaction = enum
                        registry + quality_flag only when PRESENT (INV-R7)
                        · executability tri-state · execution_view enum (INV-R8)
5. INV-R4             : goal_anchor ∈ union resolves[] ≥1 node
6. INV-R18            : twin primaries per revision → node_id must be unique;
                        forbidden to rely on UNIQUE(route_id, primary)
7. depends_on         : each ref resolves to EXACTLY ONE node (node_id, or
                        unique primary) — ambiguous = error (node_id required)
8. Frontier           : ONLY the current revision (max revision_no) — review P0-1;
                        kind = closed set {RESOLVE_APPLICABILITY, EXECUTE,
                        VERIFY} (INV-R19) · RESOLVE_APPLICABILITY fully verified:
                        route exists + applicability=UNDETERMINED +
                        not CLOSED + without a node (review P0-2) · node frontier
                        only when APPLIES (UNDETERMINED → route frontier only)
                        · route_id MANDATORY for all kinds, without fallback (review A)
9. Executability      : projection consistency — TRUE is only valid when all
                        depends_on satisfaction=PRESENT (review hole-3).
                        NOT epistemic adjudication: mapping the FALSE vs
                        UNKNOWN value from the dependency = runtime function (§7 item 9)
10. Lineage links     : Model B workspace-level — reopened_from → target EXISTS
                        + CLOSED + SAME key; successor_of → EXISTS + DIFFERENT key
                        (review hole-4; target outside the workspace = honest warning,
                        the check is NOT claimed verified)
11. Workspace         : route_id unique (review C) · next_move.frontier_ref
                        referential integrity to an existing frontier entry (review B)
12. Registry cross-check (INV-R6): if requirement_registry.json EXISTS → every
                        requirement_ref must be registered; if NOT YET →
                        warning "substrate pending" (not an error — the registry
                        is indeed rebuilt on this branch).

Boundary (second review): validator = structural existence + provenance + dependency
consistency + projection consistency + frontier validity. It MUST NOT become a
diagnosis engine.

Usage: python validate_route.py  (run from mvp/ or repo root)
Exit 0 = all instances valid; exit 1 = a violation exists.
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).parent                # mvp/ontology/route/
sys.path.insert(0, str(HERE.parent.parent))  # mvp/ — once, module-level
from core.stages.rule_predicates import OPERATORS  # noqa: E402

# REUSE directly (review 4f3e9ac: a duplicate = drift in two places;
# validate_knowledge is safe to import — main is guarded by __name__):
from ontology.knowledge.validate_knowledge import _has_citable_operator as _has_citable  # noqa: E402
from ontology.knowledge.validate_knowledge import _predicate_ops as _pred_ops  # noqa: E402
from ontology.registry.validate_registry import CONTRACT_ENUMS as _REG_ENUMS  # noqa: E402

ONTO = HERE.parent                          # mvp/ontology/
SCHEMA_PATH = ONTO / "route_schema.json"
# INV-R6 (Phase 6 wave-22 — fix for review finding 0ed2452): CANONICAL path
# = the registry validator location. Previously: HERE/"requirement_registry.json" (wrong —
# a DIFFERENT path from ontology/registry/) + key r["id"] (wrong — contract §5.1 =
# requirement_id) → blind cross-check while the registry did not exist. Path equality
# is guarded MECHANICALLY by ontology/route/test_inv_r6.py (not good intentions).
REGISTRY_PATH = ONTO / "registry" / "requirement_registry.json"
INSTANCES = HERE / "instances"

# --- Contract mirror (internal-docs) — the only source   ---
# The validator compares schema enums vs this list; drift = error.         ---
CONTRACT_ENUMS = {
    "satisfaction": ["PRESENT", "PARTIAL", "UNKNOWN", "ABSENT"],
    "applicability": ["APPLIES", "UNDETERMINED", "NOT_APPLICABLE"],
    "executability": ["TRUE", "FALSE", "UNKNOWN"],
    "execution_view": ["NOT_STARTED", "IN_PROGRESS", "EXECUTED", "ABANDONED"],
    "lineage_status": ["OPEN", "CLOSED"],
    "close_reason": ["goal_achieved", "not_applicable"],
    "frontier_kind": ["RESOLVE_APPLICABILITY", "EXECUTE", "VERIFY"],
    "next_move": ["QUESTION", "EVIDENCE_REQUEST", "ACTION", "HOLD"],
    "strength": ["hard", "soft"],
    "quality_flag": ["completed_with_gaps"],
    "strategy_status": ["active", "proof_only"],
}
BANNED = {
    "PROPOSED", "REOPEN", "WAIT", "WAIT_FOR_DEPENDENCY", "WAIT_FOR_EXECUTABILITY",
    "BLOCKED", "RESOLVE_DEPENDENCY", "RESOLVE_EXECUTABILITY",
    "DONE_CREDITED", "DONE_EXECUTED", "NODE_PENDING_REQUIREMENT",
    "TEMPLATE_PENDING_ROUTE", "READY", "NOT_YET",
}
REQ_REF = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
LINEAGE_REQUIRED = {"route_id", "reconciliation_key", "applicability", "motion",
                    "lineage_status", "revisions"}
KEY_FIELDS = {"goal_anchor", "strategy_id", "scope_anchor"}
# R1-remediation Probe B (17 Oct): business context (session goal_id); legacy = absent/None.
KEY_OPTIONAL = {"context_id"}
NODE_REQUIRED = {"resolves", "strength", "depends_on", "activity"}

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _uuid(value, where: str) -> None:
    if not isinstance(value, str):
        err(f"{where}: harus string uuid, dapat {type(value).__name__}")
        return
    try:
        uuid.UUID(value)
    except ValueError:
        err(f"{where}: bukan uuid valid ({value!r})")


def _domain_vocab() -> dict[str, list[str]]:
    """Domain-OWNED vocabulary (not a contract enum): read from the strategy registry. The validator
    plants no domain label of its own."""
    from ontology.route.strategies import load_motion_vocabulary

    return {"motion": list(load_motion_vocabulary())}


def _enum(value, name: str, where: str) -> None:
    allowed = CONTRACT_ENUMS.get(name) or _domain_vocab()[name]
    if value not in allowed:
        hint = " [TER-BANNED]" if value in BANNED else ""
        err(f"{where}: {value!r} bukan enum {name} {allowed}{hint}")


def _req_ref(value, where: str) -> None:
    if not isinstance(value, str) or not REQ_REF.match(value):
        err(f"{where}: requirement_ref tidak valid ({value!r}) — pola "
            f"'<domain>.<name>' (mis. commercial.price)")


def load_registry() -> set[str] | None:
    """INV-R6 cross-check. Registry not yet built = warning, not an error."""
    if not REGISTRY_PATH.exists():
        warn("Requirement Registry belum ada (entries = tahap 6) "
             "— cross-check INV-R6 requirement_ref DITUNDA")
        return None
    data = load(REGISTRY_PATH)
    entries = data.get("requirements") or data.get("entries") or []
    # CANONICAL key = requirement_id (contract §5.1). The old key "id" is NOT read
    # and NO alias is created — an alias blurs the contract (review
    # 0ed2452 prohibition: do not "fix" legacy req.* errors by softening the validator).
    return {r["requirement_id"] for r in entries if "requirement_id" in r}


def check_applicability(obj, where: str, registry: set[str] | None) -> None:
    if not isinstance(obj, dict) or "status" not in obj:
        err(f"{where}: applicability wajib objek dengan 'status'")
        return
    _enum(obj["status"], "applicability", f"{where}.status")
    # INV-R2: NOT_APPLICABLE must have positive evidence
    if obj["status"] == "NOT_APPLICABLE" and not obj.get("evidence"):
        err(f"{where}: NOT_APPLICABLE wajib ber-evidence positif (INV-R2 — "
            f"kekosongan bukti = UNDETERMINED, bukan NOT_APPLICABLE)")
    if obj["status"] == "APPLIES" and obj.get("evidence") is None:
        warn(f"{where}: APPLIES tanpa evidence (diperbolehkan, tapi evidence "
             f"disarankan untuk audit)")


def check_satisfaction(obj, where: str) -> None:
    if not isinstance(obj, dict) or "status" not in obj:
        err(f"{where}: satisfaction wajib objek dengan 'status'")
        return
    _enum(obj["status"], "satisfaction", f"{where}.status")
    if "quality_flag" in obj:
        _enum(obj["quality_flag"], "quality_flag", f"{where}.quality_flag")
        # INV-R7: soft-gap flag is only valid when all hard deps are PRESENT
        if obj["status"] != "PRESENT":
            err(f"{where}: quality_flag hanya sah saat satisfaction=PRESENT "
                f"(soft tidak pernah menahan/menurunkan status — INV-R7), "
                f"dapat status={obj['status']}")


def check_node(node, where: str, registry: set[str] | None) -> None:
    if not isinstance(node, dict):
        err(f"{where}: node harus objek")
        return
    missing = NODE_REQUIRED - node.keys()
    if missing:
        err(f"{where}: field wajib hilang: {sorted(missing)}")
        return
    # CORRECT-1: resolves=[] is NOT a RouteNode
    resolves = node["resolves"]
    if not isinstance(resolves, list) or not resolves:
        err(f"{where}: resolves[] minimal 1 — [] BUKAN RouteNode, itu composition/"
            f"substrate gap SEBELUM node terbentuk (CORRECT-1)")
        resolves = []
    for i, r in enumerate(resolves):
        _req_ref(r, f"{where}.resolves[{i}]")
        if registry is not None and r not in registry:
            err(f"{where}: requirement {r!r} tidak ada di Requirement Registry (INV-R6)")
    _enum(node["strength"], "strength", f"{where}.strength")
    if not isinstance(node.get("activity"), str) or not node["activity"].strip():
        err(f"{where}.activity: wajib non-empty")
    if not isinstance(node.get("depends_on"), list):
        err(f"{where}.depends_on: wajib array")
    if "node_id" in node:
        _uuid(node["node_id"], f"{where}.node_id")
    if "executability" in node:
        _enum(node["executability"], "executability", f"{where}.executability")
    if "execution_view" in node:
        _enum(node["execution_view"], "execution_view", f"{where}.execution_view")
    if "satisfaction" in node:
        check_satisfaction(node["satisfaction"], f"{where}.satisfaction")


def check_revision(rev, where: str, registry: set[str] | None) -> None:
    if not isinstance(rev, dict):
        err(f"{where}: revision harus objek")
        return
    if not isinstance(rev.get("revision_no"), int) or rev.get("revision_no", 0) < 1:
        err(f"{where}.revision_no: wajib integer >= 1")
    nodes = rev.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        err(f"{where}.nodes: wajib array non-empty")
        return
    for i, node in enumerate(nodes):
        check_node(node, f"{where}.nodes[{i}]", registry)

    # INV-R18: primary (resolves[0]) twins → node_id must be unique
    primaries: dict[str, list[int]] = {}
    for i, node in enumerate(nodes):
        if isinstance(node, dict) and isinstance(node.get("resolves"), list) and node["resolves"]:
            primaries.setdefault(node["resolves"][0], []).append(i)
    for primary, idxs in primaries.items():
        if len(idxs) < 2:
            continue
        ids = [nodes[i].get("node_id") for i in idxs]
        if not all(ids):
            err(f"{where}: primary {primary!r} dipakai {len(idxs)} node "
                f"(indeks {idxs}) tapi tidak semua punya node_id (INV-R18: primary "
                f"kembar wajib terbedakan secara struktural; UNIQUE(route_id,primary) dilarang)")
        elif len(set(ids)) != len(ids):
            err(f"{where}: node_id duplikat pada primary kembar {primary!r} (INV-R18)")
        for i in idxs:
            if not nodes[i].get("execution_context"):
                warn(f"{where}.nodes[{i}]: primary kembar {primary!r} tanpa "
                     f"execution_context — bagian SEMANTIK INV-R18 (audit manual)")

    # depends_on: resolve to EXACTLY ONE node
    by_id = {n.get("node_id"): i for i, n in enumerate(nodes)
             if isinstance(n, dict) and n.get("node_id")}
    by_primary: dict[str, list[int]] = {}
    for i, n in enumerate(nodes):
        if isinstance(n, dict) and isinstance(n.get("resolves"), list) and n["resolves"]:
            by_primary.setdefault(n["resolves"][0], []).append(i)
    for i, n in enumerate(nodes):
        if not isinstance(n, dict) or not isinstance(n.get("depends_on"), list):
            continue
        targets: list[int] = []
        for dep in n["depends_on"]:
            if dep in by_id:
                targets.append(by_id[dep])  # node_id reference — unique by construction
                continue
            hits = by_primary.get(dep, [])
            if len(hits) == 0:
                err(f"{where}.nodes[{i}].depends_on: {dep!r} tidak resolve ke node mana pun")
            elif len(hits) > 1:
                err(f"{where}.nodes[{i}].depends_on: {dep!r} AMBIGU ({len(hits)} node "
                    f"dengan primary sama) — pakai node_id sebagai referensi (INV-R18)")
            else:
                targets.append(hits[0])
        # Review hole-3: projection consistency (NOT epistemic adjudication —
        # the FALSE/UNKNOWN mapping vs dependency value = runtime function, §7 item 9)
        if n.get("executability") == "TRUE":
            for t in targets:
                dep_n = nodes[t]
                dep_sat = (dep_n.get("satisfaction") or {}).get("status") \
                    if isinstance(dep_n, dict) else None
                if dep_sat != "PRESENT":
                    err(f"{where}.nodes[{i}]: executability=TRUE padahal dependency "
                        f"->{dep_n.get('node_id') or dep_n.get('resolves')} "
                        f"satisfaction={dep_sat!r} — TRUE hanya sah bila seluruh "
                        f"dependency PRESENT (projection consistency, review hole-3)")


def check_lineage(lin, where: str, registry: set[str] | None) -> None:
    if not isinstance(lin, dict):
        err(f"{where}: lineage harus objek")
        return
    missing = LINEAGE_REQUIRED - lin.keys()
    if missing:
        err(f"{where}: field wajib hilang: {sorted(missing)}")
        return
    _uuid(lin["route_id"], f"{where}.route_id")  # INV-R15

    # INV-R13/R14: key EXACTLY three fields (+ optional `context_id`, remediation
    # Probe B 17 Oct) — motion/template_id/label forbidden
    key = lin["reconciliation_key"]
    if not isinstance(key, dict):
        err(f"{where}.reconciliation_key: wajib objek")
    else:
        extra = set(key) - KEY_FIELDS - KEY_OPTIONAL
        absent = KEY_FIELDS - set(key)
        if extra:
            err(f"{where}.reconciliation_key: field asing {sorted(extra)} — key "
                f"persis {{goal_anchor, strategy_id, scope_anchor[, context_id]}} (INV-R13/R14; "
                f"motion & template_id BUKAN identity)")
        if absent:
            err(f"{where}.reconciliation_key: field wajib hilang {sorted(absent)}")
        cid = key.get("context_id")
        if cid is not None and (not isinstance(cid, str) or not cid):
            err(f"{where}.reconciliation_key.context_id: wajib string non-kosong "
                f"atau None (legacy)")
        if "goal_anchor" in key:
            _req_ref(key["goal_anchor"], f"{where}.reconciliation_key.goal_anchor")
            if registry is not None and key["goal_anchor"] not in registry:
                err(f"{where}: goal_anchor {key['goal_anchor']!r} tidak ada di Registry (INV-R6)")
        if "scope_anchor" in key:
            sa = key["scope_anchor"]
            if not isinstance(sa, list) or not sa:
                err(f"{where}.reconciliation_key.scope_anchor: wajib non-empty "
                    f"(referensi state ter-grounding, bukan label bebas)")
            else:
                for i, s in enumerate(sa):
                    if not isinstance(s, str) or not s.startswith("state:"):
                        warn(f"{where}.scope_anchor[{i}]: {s!r} bukan rujukan "
                             f"state:claim_* — kekhawatiran grounding (INV: scope "
                             f"harus ter-grounding)")

    _enum(lin["motion"], "motion", f"{where}.motion")
    _enum(lin["lineage_status"], "lineage_status", f"{where}.lineage_status")
    check_applicability(lin["applicability"], f"{where}.applicability", registry)

    # Review hole-5: INV-R3 at the LINEAGE LEVEL — enforcement must not ride
    # on check_frontier (a NOT_APPLICABLE lineage sitting silently without a frontier =
    # passed). §3.5: "NOT_APPLICABLE → no RouteInstance / route closed".
    if (isinstance(lin.get("applicability"), dict)
            and lin["applicability"].get("status") == "NOT_APPLICABLE"
            and lin.get("lineage_status") != "CLOSED"):
        err(f"{where}: applicability=NOT_APPLICABLE tapi lineage_status="
            f"{lin.get('lineage_status')!r} — wajib CLOSED (INV-R3/§3.5: "
            f"NOT_APPLICABLE = no active route; review hole-5)")

    # M4 corrective (review 7de3e73): lineage closing fields are LOCKED —
    # derived_route_status depends on close_reason, so its shape
    # must be contractual (not a free field).
    reason = lin.get("close_reason")
    if lin.get("lineage_status") == "CLOSED":
        if reason is None:
            err(f"{where}: lineage_status=CLOSED wajib close_reason "
                f"(goal_achieved | not_applicable — int 08 §8.2 keputusan "
                f"enum: COMPLETED = derivasi, bukan enum)")
        elif reason not in CONTRACT_ENUMS["close_reason"]:
            err(f"{where}.close_reason={reason!r} di luar enum "
                f"{CONTRACT_ENUMS['close_reason']}")
        elif reason == "not_applicable":
            app = lin.get("applicability")
            if not (isinstance(app, dict)
                    and app.get("status") == "NOT_APPLICABLE"):
                err(f"{where}: close_reason=not_applicable tapi "
                    f"applicability={app!r} — record konsisten wajib "
                    f"(arah kebalikan hole-5; INV-R2: bukti positif di "
                    f"record itu sendiri)")
    elif reason is not None:
        err(f"{where}: lineage OPEN membawa close_reason={reason!r} — "
            f"dilarang (penutup hanya di transisi terminal; baris OPEN "
            f"baru harus bersih)")

    # INV-R20: two lineage links have different meanings — both are uuid if present
    for link in ("successor_of", "reopened_from"):
        if link in lin:
            _uuid(lin[link], f"{where}.{link}")
    if "reopened_from" in lin and "successor_of" in lin:
        warn(f"{where}: punya successor_of DAN reopened_from — pastikan keduanya "
             f"memang berbeda peristiwa (fork dari hasil reopen); bukan alias (INV-R20)")

    revisions = lin.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        err(f"{where}.revisions: wajib array non-empty")
        return
    revnos = [r.get("revision_no") for r in revisions if isinstance(r, dict)]
    if len(revnos) != len(set(revnos)):
        err(f"{where}.revisions: revision_no duplikat")
    for i, rev in enumerate(revisions):
        if isinstance(rev, dict) and not rev.get("based_on"):
            err(f"{where}.revisions[{i}].based_on: wajib non-empty (grounding Universal State)")
        check_revision(rev, f"{where}.revisions[{i}]", registry)

    # INV-R4: goal_anchor ∈ union resolves[] of at least one node
    if isinstance(key, dict) and isinstance(key.get("goal_anchor"), str):
        union = set()
        for rev in revisions:
            if isinstance(rev, dict):
                for n in rev.get("nodes") or []:
                    if isinstance(n, dict) and isinstance(n.get("resolves"), list):
                        union |= set(n["resolves"])
        if key["goal_anchor"] not in union:
            err(f"{where}: goal_anchor {key['goal_anchor']!r} TIDAK terikat di node "
                f"mana pun (INV-R4: goal_anchor ∈ union resolves[] — composition defect)")


def current_revision_nodes(lin: dict) -> list[dict]:
    """Nodes from the CURRENT revision (max revision_no) ONLY.

    Review P0-1: frontier = a projection of the route's CURRENT state; merging
    all revisions mixes historical snapshots with current state. Old revisions
    are still structurally validated (check_lineage) — they do not enter the projection.
    """
    revs = [r for r in (lin.get("revisions") or []) if isinstance(r, dict)]
    if not revs:
        return []

    def _no(r):
        v = r.get("revision_no")
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    cur = max(revs, key=_no)
    return [n for n in (cur.get("nodes") or []) if isinstance(n, dict)]


def check_frontier(entries, lineages, where: str) -> None:
    if not isinstance(entries, list):
        err(f"{where}: frontier harus array")
        return
    # Per route_id index: CURRENT revision nodes + route meta (review P0-1/P0-2)
    nodes_by_route: dict[str, list[dict]] = {}
    meta_by_route: dict[str, dict] = {}
    for lin in lineages:
        if not isinstance(lin, dict):
            continue
        rid = lin.get("route_id")
        nodes_by_route[rid] = current_revision_nodes(lin)
        meta_by_route[rid] = {
            "applicability": (lin.get("applicability") or {}).get("status"),
            "lineage_status": lin.get("lineage_status"),
        }

    for i, e in enumerate(entries):
        w = f"{where}[{i}]"
        if not isinstance(e, dict) or "kind" not in e:
            err(f"{w}: frontier entry wajib punya 'kind'")
            continue
        _enum(e["kind"], "frontier_kind", f"{w}.kind")  # INV-R19: closed set

        # Review A: route_id is MANDATORY — every opportunity comes from a specific route
        rid = e.get("route_id")
        if not rid:
            err(f"{w}: route_id wajib untuk semua frontier entry (setiap "
                f"opportunity berasal dari route tertentu — tanpa fallback global)")
            continue
        meta = meta_by_route.get(rid)
        if meta is None:
            err(f"{w}: route_id {rid!r} tidak ada di workspace")
            continue

        # Route CLOSED = all kinds leave the frontier (exit cause: route CLOSED)
        if meta["lineage_status"] == "CLOSED":
            err(f"{w}: frontier pada route CLOSED (route sudah terminal — "
                f"semua kind keluar frontier)")
            continue

        if e["kind"] == "RESOLVE_APPLICABILITY":
            # Review P0-2: fully verified, not a blind continue
            if e.get("node"):
                err(f"{w}: RESOLVE_APPLICABILITY tidak boleh menunjuk node "
                    f"(route-level gate, bukan node frontier)")
            if meta["applicability"] != "UNDETERMINED":
                err(f"{w}: RESOLVE_APPLICABILITY hanya sah saat applicability="
                    f"UNDETERMINED — route ini {meta['applicability']!r} "
                    f"(APPLIES → node frontier; NOT_APPLICABLE → no active route)")
            continue

        # EXECUTE/VERIFY only when APPLIES (#5: UNDETERMINED → node frontier CLOSED)
        if meta["applicability"] != "APPLIES":
            extra = ("selama UNDETERMINED hanya RESOLVE_APPLICABILITY yang sah (#5)"
                     if meta["applicability"] == "UNDETERMINED"
                     else "NOT_APPLICABLE = no active route")
            err(f"{w}: node frontier ({e['kind']}) hanya sah saat applicability="
                f"APPLIES — route ini {meta['applicability']!r} ({extra})")
            continue

        ref = e.get("node")
        if not ref:
            err(f"{w}: kind {e['kind']} butuh 'node' (node_id atau primary)")
            continue
        cands = nodes_by_route.get(rid, [])
        matched = [n for n in cands
                   if n.get("node_id") == ref
                   or (isinstance(n.get("resolves"), list) and n["resolves"]
                       and n["resolves"][0] == ref)]
        if len(matched) != 1:
            err(f"{w}: node {ref!r} resolve ke {len(matched)} node di CURRENT "
                f"revision (wajib tepat 1 — node revision lama tidak ikut "
                f"projection, P0-1)")
            continue
        n = matched[0]
        sat = (n.get("satisfaction") or {}).get("status")
        exe = n.get("executability")
        view = n.get("execution_view")
        if e["kind"] == "EXECUTE":
            if sat == "PRESENT":
                err(f"{w}: EXECUTE tapi satisfaction=PRESENT (sudah terbayar — "
                    f"harus keluar frontier)")
            if exe != "TRUE":
                err(f"{w}: EXECUTE tapi executability={exe!r} — hanya TRUE "
                    f"yang eligible (FALSE/UNKNOWN bukan frontier — INV-R19)")
            if view not in ("NOT_STARTED", "ABANDONED"):
                err(f"{w}: EXECUTE tapi execution_view={view!r} (harus "
                    f"NOT_STARTED/ABANDONED; EXECUTED → kind VERIFY)")
        else:  # VERIFY
            if sat == "PRESENT":
                err(f"{w}: VERIFY tapi satisfaction=PRESENT (keluar frontier)")
            if exe != "TRUE":
                err(f"{w}: VERIFY tapi executability={exe!r} — hanya TRUE "
                    f"yang eligible (INV-R19, berlaku untuk EXECUTE & VERIFY)")
            if view != "EXECUTED":
                err(f"{w}: VERIFY tapi execution_view={view!r} — VERIFY hanya "
                    f"untuk aktivitas yang SUDAH dilakukan, bukti belum masuk")


def check_next_move(nm, where: str) -> None:
    if not isinstance(nm, dict) or "output" not in nm:
        err(f"{where}: next_move wajib objek dengan 'output'")
        return
    _enum(nm["output"], "next_move", f"{where}.output")


TEMPLATE_DIR = HERE / "templates"
PROV_FIELDS = {"source_id", "chapters", "knowledge_type", "confidence"}
# Contract enums = ONE source: the registry validator (anti parallel drift)
# CITABLE/pred_ops = REUSE validate_knowledge directly (review 4f3e9ac:
# a local duplicate = drift in two places; validate_knowledge is safe to import —
# main is guarded by __name__)

PROV_ENUMS = {"knowledge_type": set(_REG_ENUMS["knowledge_type"]),
              "confidence": set(_REG_ENUMS["confidence"])}
STRENGTH_ENUM = {"hard", "soft"}


def check_template(tpl: dict, where: str, registry: set[str] | None,
                   sources: set[str] | None) -> None:
    """Phase 7 (review f3a8d88): route_template entity validator —
    structural + provenance (enum!) + recursive predicate + citation +
    cycle + resolves⊆requires + twin execution_context. Prose
    is FORBIDDEN (INV-R16)."""
    for f in ("template_id", "strategy_id"):
        v = tpl.get(f)
        if not isinstance(v, str) or not re.fullmatch(r"[a-z0-9_\-]+", v):
            err(f"{where}.{f}: wajib string pola [a-z0-9_-]+ (INV-R14: "
                f"template = grammar berprovenance, strategy = identitas)")
    # applicability — NOT satisfaction (review f3a8d88 #1: the predicate
    # 'X already exists' belongs to the registry/adjudicator, INV-R1+RR7; goal
    # PRESENT => INV-R12 route not born, not NOT_APPLICABLE)
    aw = tpl.get("applies_when")
    if not isinstance(aw, dict) or set(aw) - {"applies", "not_applicable"} \
            or not isinstance(aw.get("applies"), list) or not aw["applies"] \
            or not isinstance(aw.get("not_applicable"), list):
        err(f"{where}.applies_when: wajib objek {{applies: [pred...], "
            f"not_applicable: [pred...]}} — applicability_rule 3-nilai "
            f"(prosa DILARANG, INV-R16)")
        aw = None
    if aw is not None:
        for branch in ("applies", "not_applicable"):
            for i, pred in enumerate(aw[branch]):
                bad = _pred_ops(pred) - OPERATORS
                if not isinstance(pred, dict) or not pred or bad:
                    err(f"{where}.applies_when.{branch}[{i}]: operator tak "
                        f"dikenal {sorted(bad) or '(bukan objek predikat)'} — "
                        f"wajib ⊆ {sorted(OPERATORS)} (ValueError ditelan -> "
                        f"tak pernah match)")
                elif not _has_citable(pred):
                    err(f"{where}.applies_when.{branch}[{i}]: predikat murni "
                        f"negatif TANPA operator bisa-sitasi — tak akan pernah "
                        f"match; INV-R2 bolong by construction")
    req = tpl.get("requires")
    if not isinstance(req, list) or not req:
        err(f"{where}.requires: wajib array non-empty requirement_ref")
        req = []
    reqset = set(req)
    if registry is not None:
        for r in req:
            if r not in registry:
                err(f"{where}.requires: {r!r} tidak terdaftar di registry "
                    f"(INV-R6)")
    nodes = tpl.get("node_candidates")
    if not isinstance(nodes, list) or not nodes:
        err(f"{where}.node_candidates: wajib array non-empty")
        nodes = []
    # local key: candidate_key (NOT the node_id UUID — review f3a8d88 #2:
    # a UUID = physical instance; a template = knowledge-layer grammar; copied
    # at instantiation => duplicate node_id across lineages, INV-R15)
    keys: dict[str, int] = {}
    primaries: dict[str, list[int]] = {}
    for i, nc in enumerate(nodes):
        if not isinstance(nc, dict):
            continue
        ck = nc.get("candidate_key")
        if not isinstance(ck, str) or not re.fullmatch(r"[a-z0-9_]+", ck):
            err(f"{where}.node_candidates[{i}].candidate_key: wajib string "
                f"[a-z0-9_]+ — kunci LOKAL template (UUID diterbitkan saat "
                f"instansiasi, INV-R15)")
        elif ck in keys:
            err(f"{where}.node_candidates[{i}].candidate_key {ck!r} DUPLIKAT")
        else:
            keys[ck] = i
        if nc.get("node_id") is not None:
            err(f"{where}.node_candidates[{i}].node_id DILARANG di template "
                f"(kunci fisik instance — pakai candidate_key)")
        if nc.get("strength") not in STRENGTH_ENUM:
            err(f"{where}.node_candidates[{i}].strength: wajib "
                f"{sorted(STRENGTH_ENUM)}")
        if not isinstance(nc.get("activity"), str) or not nc["activity"]:
            err(f"{where}.node_candidates[{i}].activity: wajib string "
                f"non-empty")
        elif not ((nc.get("i18n") or {}).get("en") or {}).get("activity"):
            warn(f"{where}.node_candidates[{i}].i18n.en.activity: kosong — "
                 f"aktivitas node akan lolos berbahasa mesin ke UI sesi EN "
                 f"(kebijakan bahasa UI, internal-docs)")
        rs = nc.get("resolves")
        if isinstance(rs, list) and rs:
            primaries.setdefault(rs[0], []).append(i)
            for r in rs:
                if registry is not None and r not in registry:
                    err(f"{where}.node_candidates[{i}].resolves: {r!r} tidak "
                        f"terdaftar di registry (INV-R6)")
                if r not in reqset:
                    err(f"{where}.node_candidates[{i}].resolves: {r!r} DI LUAR "
                        f"requires[] template (kandidat menyelesaikan syarat "
                        f"yang tak dinyatakan)")
    # execution_context for twin primaries (mirror of the instance check — warning)
    for prim, idxs in primaries.items():
        if len(idxs) > 1:
            for i in idxs:
                if not nodes[i].get("execution_context"):
                    warn(f"{where}.node_candidates[{i}]: primary kembar "
                         f"{prim!r} tanpa execution_context (INV-R18 semantik)")
    # THE OPPOSITE DIRECTION (review 4f3e9ac #1): requires ⊆ ⋃ resolves —
    # a requirement that no candidate resolves will never
    # be completable by the route; caught AT AUTHORING TIME (not at
    # instantiation when INV-R4 explodes)
    resolved = {r for nc in nodes if isinstance(nc, dict)
                for r in (nc.get("resolves") or [])}
    for r in reqset - resolved:
        err(f"{where}.requires: {r!r} TIDAK di-resolve kandidat mana pun — "
            f"syarat tak terpenuhkan oleh grammar ini (goal_anchor-nya akan "
            f"gagal INV-R4 saat instansiasi)")
    # A1 (owner decision 27 Sep): goal_anchor = a template DECLARATION —
    # the route's destination (the capability state aimed at), NOT a derivation of the user's
    # revenue goal (a revenue-metric goal = Universal State context;
    # route relevance to revenue = surfacing/NextMove concern, INV-R17).
    # Checked AT AUTHORING TIME (INV-R4 + INV-R6) so it does not explode at
    # instantiation — the bridge only READS this field (orchestration).
    ga = tpl.get("goal_anchor")
    if not isinstance(ga, str) or not ga:
        err(f"{where}.goal_anchor: wajib requirement_ref — deklarasi "
            f"tujuan route (keputusan A1 owner 27 Sep; bukan turunan "
            f"goal revenue user)")
    else:
        if registry is not None and ga not in registry:
            err(f"{where}.goal_anchor: {ga!r} tidak terdaftar di registry "
                f"(INV-R6)")
        if ga not in reqset:
            err(f"{where}.goal_anchor: {ga!r} tidak ada di requires[] "
                f"template (tujuan route wajib syarat yang dinyatakan)")
        if ga not in resolved:
            err(f"{where}.goal_anchor: {ga!r} tidak di-resolve kandidat "
                f"mana pun — INV-R4 pasti gagal saat instansiasi")
    # depends_on: resolve by candidate_key OR unique primary + anti-cycle
    graph: dict[int, list[int]] = {}
    for i, nc in enumerate(nodes):
        if not isinstance(nc, dict):
            continue
        deps = nc.get("depends_on")
        if not isinstance(deps, list):
            err(f"{where}.node_candidates[{i}].depends_on: wajib array")
            continue
        graph[i] = []
        for dep in deps:
            if dep in keys:
                graph[i].append(keys[dep])
                continue
            hits = primaries.get(dep, [])
            if len(hits) == 0:
                err(f"{where}.node_candidates[{i}].depends_on: {dep!r} tidak "
                    f"resolve ke kandidat mana pun (candidate_key/primary)")
            elif len(hits) > 1:
                err(f"{where}.node_candidates[{i}].depends_on: {dep!r} AMBIGU "
                    f"({len(hits)} kandidat primary sama — pakai candidate_key)")
            else:
                graph[i].append(hits[0])
    # cycle detection (color DFS)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {i: WHITE for i in graph}

    def dfs(u: int) -> None:
        color[u] = GRAY
        for v in graph.get(u, []):
            if color.get(v) == GRAY:
                err(f"{where}.node_candidates: SIKLUS depends_on melibatkan "
                    f"kandidat[{v}] — grammar eksekusi tak boleh melingkar")
            elif color.get(v) == WHITE:
                dfs(v)
        color[u] = BLACK
    for u in list(graph):
        if color[u] == WHITE:
            dfs(u)
    # provenance: KB object + contract ENUM (review: enum was not checked)
    prov = tpl.get("provenance")
    if not isinstance(prov, list) or not prov:
        err(f"{where}.provenance: wajib array non-empty objek skema KB (D5)")
        prov = []
    for i, pr in enumerate(prov):
        if not isinstance(pr, dict) or set(pr) != PROV_FIELDS:
            err(f"{where}.provenance[{i}]: wajib PERSIS {sorted(PROV_FIELDS)} "
                f"— string 'source:chapter' DITOLAK (format T6)")
            continue
        if sources is not None and pr["source_id"] not in sources:
            err(f"{where}.provenance[{i}].source_id {pr['source_id']!r} tidak "
                f"terdaftar di sources.json")
        ch = pr.get("chapters")
        if not isinstance(ch, list) or not ch or not all(
                isinstance(c, str) and c for c in ch):
            err(f"{where}.provenance[{i}].chapters: wajib array non-empty "
                f"string")
        for f_enum in ("knowledge_type", "confidence"):
            if pr.get(f_enum) not in PROV_ENUMS[f_enum]:
                err(f"{where}.provenance[{i}].{f_enum}: {pr.get(f_enum)!r} "
                    f"bukan enum kontrak {sorted(PROV_ENUMS[f_enum])}")


STRATEGY_PATH = HERE / "strategies.json"
STRATEGY_FIELDS = {"strategy_id", "motion", "status", "description"}


def check_strategies() -> dict[str, dict] | None:
    """D5: strategy registry — closed structure, unique ids, motion & status
    contract enums. Return {strategy_id: entry} (None if the file is missing)."""
    if not STRATEGY_PATH.exists():
        err("strategies.json tidak ada (D5 — motion wajib dari strategy registry)")
        return None
    out: dict[str, dict] = {}
    for i, s in enumerate(load(STRATEGY_PATH).get("strategies") or []):
        w = f"strategies[{i}]"
        if not isinstance(s, dict) or set(s) != STRATEGY_FIELDS:
            err(f"{w}: wajib PERSIS {sorted(STRATEGY_FIELDS)}")
            continue
        sid = s["strategy_id"]
        if not isinstance(sid, str) or not re.fullmatch(r"[a-z0-9_\-]+", sid):
            err(f"{w}.strategy_id: pola [a-z0-9_-]+")
        elif sid in out:
            err(f"{w}: strategy_id {sid!r} DUPLIKAT")
        _enum(s["motion"], "motion", f"{w}.motion")
        _enum(s["status"], "strategy_status", f"{w}.status")
        if not isinstance(s["description"], str) or not s["description"].strip():
            err(f"{w}.description: wajib non-empty")
        out[sid] = s
    return out


def check_templates(registry: set[str] | None,
                    sources: set[str] | None) -> None:
    if not TEMPLATE_DIR.exists():
        warn("folder templates tidak ada (Tahap 7: validator self-check saja)")
        return
    strategies = check_strategies()
    seen_ids: set[str] = set()
    for f in sorted(TEMPLATE_DIR.glob("*.json")):
        tpl = load(f)
        check_template(tpl, f"templates/{f.name}", registry, sources)
        if "motion" in tpl:
            err(f"templates/{f.name}: field 'motion' DILARANG di template "
                f"(T1.13 — motion milik strategy registry, D5)")
        if strategies is not None and tpl.get("strategy_id") not in strategies:
            err(f"templates/{f.name}: strategy_id {tpl.get('strategy_id')!r} "
                f"tidak terdaftar di strategies.json (D5)")
        tid = tpl.get("template_id")
        if tid in seen_ids:
            err(f"templates/{f.name}: template_id {tid!r} DUPLIKAT")
        seen_ids.add(tid)


def _template_self_expect(registry: set[str] | None,
                          sources: set[str] | None) -> None:
    """SELF-EXPECTING fixture for the template validator (review f3a8d88:
    WITHOUT assert — dies under python -O; failure = explicit error)."""
    base = {"template_id": "t-x", "strategy_id": "s",
            "requires": ["conversion.landing_page"],
            "goal_anchor": "conversion.landing_page",
            "node_candidates": [
                {"candidate_key": "copy_main",
                 "resolves": ["conversion.landing_page"], "strength": "hard",
                 "depends_on": [], "activity": "a"}],
            "provenance": [{"source_id": "tm", "chapters": ["ch01"],
                            "knowledge_type": "source_claim",
                            "confidence": "normative_only"}],
            "applies_when": {"applies": [{"text_contains_any": ["x"]}],
                             "not_applicable": []}}

    def run(mut) -> list[str]:
        tpl = json.loads(json.dumps(base))
        mut(tpl)
        saved, wsaved = errors[:], warnings[:]
        errors.clear()
        warnings.clear()
        check_template(tpl, "fixture", registry, sources)
        got = errors[:]
        errors.clear()
        warnings.clear()
        errors.extend(saved)
        warnings.extend(wsaved)
        return got

    def set_pred_bad(t):
        t["applies_when"]["applies"] = [{"text_contains_anyx": ["x"]}]
    def set_pred_nested_bad(t):
        t["applies_when"]["applies"] = [
            {"any_of": [{"text_contains_any": ["x"]},
                        {"operator_hantu": 1}]}]
    def set_pred_pure_negative(t):
        # predicate SHAPE-VALID but purely negative (no citable at
        # any level — review 4f3e9ac #2: the old case {'none_of':['x']}
        # errored for the wrong reason: string, not predicate)
        t["applies_when"]["applies"] = [
            {"none_of": [{"min_evidence_count": 1}]}]
    def set_requires_unresolved(t):
        t["requires"].append("conversion.proposal")
    def set_goal_anchor_hilang(t):
        del t["goal_anchor"]
    def set_goal_anchor_di_luar_requires(t):
        # conversion.proposal is in the registry, is NOT resolved — and is not
        # in requires[]: two errors (requires + resolver)
        t["goal_anchor"] = "conversion.proposal"
    def set_prov_string(t):
        t["provenance"] = ["tm:ch01"]
    def set_prov_bad_enum(t):
        t["provenance"][0]["confidence"] = "super_confident"
    def set_unknown_req(t):
        t["requires"] = ["tidak.ada"]
    def set_cycle(t):
        t["node_candidates"].append(
            {"candidate_key": "n2", "resolves": ["conversion.landing_page"],
             "strength": "soft", "depends_on": ["n3"], "activity": "b",
             "execution_context": "ctx-b"})
        t["node_candidates"].append(
            {"candidate_key": "n3", "resolves": ["conversion.landing_page"],
             "strength": "soft", "depends_on": ["copy_main"], "activity": "c",
             "execution_context": "ctx-c"})
        t["node_candidates"][0]["depends_on"] = ["n2"]
    def set_resolves_outside(t):
        t["node_candidates"][0]["resolves"] = ["offering.exists"]

    cases = [
        (lambda t: None, 0, [], "valid"),
        (set_pred_bad, 1, ["operator tak dikenal"],
         "operator tak dikenal"),
        (set_pred_nested_bad, 1, ["operator tak dikenal"],
         "operator bersarang salah"),
        (set_pred_pure_negative, 1, ["murni negatif"],
         "predikat murni negatif (INV-R2)"),
        (set_prov_string, 1, ["string 'source:chapter' DITOLAK"],
         "provenance string T6"),
        (set_prov_bad_enum, 1, ["bukan enum kontrak"],
         "enum confidence salah"),
        (set_unknown_req, 4, ["tidak terdaftar di registry",
                              "DI LUAR requires[]",
                              "TIDAK di-resolve kandidat mana pun",
                              "goal_anchor: 'conversion.landing_page' tidak ada di requires"],
         "requires tak terdaftar (INV-R6 + resolves-outside + unresolved + A1)"),
        (set_cycle, 1, ["SIKLUS"], "siklus depends_on"),
        (set_resolves_outside, 3, ["DI LUAR requires[]",
                                  "TIDAK di-resolve kandidat mana pun",
                                  "goal_anchor: 'conversion.landing_page' tidak di-resolve"],
         "resolves di luar requires (+ requires tanpa resolver + A1)"),
        (set_requires_unresolved, 1, ["TIDAK di-resolve kandidat mana pun"],
         "requires tanpa resolver (review 4f3e9ac #1)"),
        (set_goal_anchor_hilang, 1, ["goal_anchor: wajib requirement_ref"],
         "goal_anchor wajib (A1 owner 27 Sep)"),
        (set_goal_anchor_di_luar_requires, 2,
         ["tidak ada di requires[]", "tidak di-resolve kandidat"],
         "goal_anchor di luar requires/resolver (A1)"),
    ]
    # BOTH DIRECTIONS (review #2 — the _expect_ok registry pattern): every pattern MUST
    # appear AND no error outside the expectation (count == len(patterns))
    fails = []
    for mut, want, pats, ket in cases:
        got = run(mut)
        for p in pats:
            if not any(p in g for g in got):
                fails.append(f"{ket}: pola {p!r} TIDAK muncul: {got}")
        if len(got) != want:
            fails.append(f"{ket}: jumlah {len(got)} != {want}: {got}")
    if fails:
        err("SELF-EXPECT template GAGAL: " + " | ".join(fails))
    else:
        print("fixture template: 10/10 sesuai ekspektasi (pola dua arah)")


def main() -> int:
    schema = load(SCHEMA_PATH)

    # 1. Schema self-check: enums == contract mirror (anti drift)
    if schema.get("enums") != CONTRACT_ENUMS:
        for k, v in CONTRACT_ENUMS.items():
            got = (schema.get("enums") or {}).get(k)
            if got != v:
                err(f"SCHEMA DRIFT: enums.{k} = {got}, kontrak = {v}")
    schema_values = {val for vals in (schema.get("enums") or {}).values() for val in vals}
    banned_in_schema = BANNED & schema_values
    if banned_in_schema:
        err(f"SCHEMA: nilai ter-banned ada di enums: {sorted(banned_in_schema)}")
    banned_list = set((schema.get("banned_values") or {}).get("values", []))
    if banned_list != BANNED:
        warn(f"schema.banned_values berbeda dari mirror validator: "
             f"+{sorted(banned_list - BANNED)} -{sorted(BANNED - banned_list)}")

    registry = load_registry()

    # Phase 7: templates + self-expect fixture (owner verdict 27 Sep)
    sources: set[str] | None = None
    src_path = ONTO / "knowledge" / "sources.json"
    if src_path.exists():
        try:
            sources = {s["source_id"] for s in
                      load(src_path).get("sources", [])}
        except (KeyError, TypeError):
            sources = None
    check_templates(registry, sources)
    _template_self_expect(registry, sources)

    # 2. Instances — collect the workspace first (uniqueness + lineage link across files)
    all_lineages: list[dict] = []
    frontier_blocks: list[tuple[str, list]] = []
    next_move_blocks: list[tuple[str, dict]] = []
    if not INSTANCES.exists():
        err(f"folder instances tidak ada: {INSTANCES}")
    else:
        files = sorted(INSTANCES.glob("*.json"))
        if not files:
            warn("tidak ada instance di instances/ (validator hanya self-check schema)")
        for f in files:
            data = load(f)
            lineages = data.get("lineages")
            if not isinstance(lineages, list) or not lineages:
                err(f"{f.name}: wajib punya 'lineages' array non-empty")
                continue
            for i, lin in enumerate(lineages):
                check_lineage(lin, f"{f.name}.lineages[{i}]", registry)
            all_lineages.extend(lin for lin in lineages if isinstance(lin, dict))
            if "frontier" in data:
                frontier_blocks.append((f"{f.name}.frontier", data["frontier"]))
            if isinstance(data.get("next_move"), dict):
                next_move_blocks.append((f"{f.name}.next_move", data["next_move"]))

    # Review C: route_id = persistent identity → unique per workspace
    seen: dict[str, dict] = {}
    for lin in all_lineages:
        rid = lin.get("route_id")
        if not isinstance(rid, str):
            continue
        if rid in seen:
            err(f"route_id DUPLIKAT {rid!r} — persistent identity wajib unik "
                f"per workspace (INV-R15, review C)")
        else:
            seen[rid] = lin

    # Review hole-4: verify the lineage link (Model B) — not just uuid syntax
    for lin in all_lineages:
        rid = lin.get("route_id")
        for link in ("successor_of", "reopened_from"):
            val = lin.get(link)
            if not val:
                continue
            try:
                uuid.UUID(str(val))
            except (ValueError, TypeError, AttributeError):
                continue  # invalid syntax already errors in check_lineage
            target = seen.get(str(val))
            if target is None:
                warn(f"{rid!r}.{link} → {val!r} tidak ada di instance workspace ini "
                     f"— target di persistence LAIN: check Model B TIDAK diverifikasi "
                     f"di sini (akan diverifikasi runtime/store)")
                continue
            t_status = target.get("lineage_status")
            t_key = target.get("reconciliation_key")
            c_key = lin.get("reconciliation_key")
            if link == "reopened_from":
                if t_status != "CLOSED":
                    err(f"{rid!r}.reopened_from → {val!r}: target harus CLOSED "
                        f"(Model B — episode terminal; dapat {t_status!r}, review hole-4)")
                if t_key != c_key:
                    err(f"{rid!r}.reopened_from → {val!r}: reconciliation_key "
                        f"BERBEDA — reopened_from = key SAMA muncul lagi (episode baru); "
                        f"key beda = pakai successor_of (INV-R20)")
            else:  # successor_of
                if t_key == c_key:
                    err(f"{rid!r}.successor_of → {val!r}: reconciliation_key SAMA — "
                        f"itu bukan fork; pakai reopened_from (INV-R20)")

    # Frontier: projection over ALL workspace lineages (current revision only)
    for where, entries in frontier_blocks:
        check_frontier(entries, all_lineages, where)

    # NextMove: enum + referential integrity (review B) + kind match (hole-6)
    # int 06 §5 mapping: ACTION→EXECUTE, EVIDENCE_REQUEST→VERIFY,
    # QUESTION→RESOLVE_APPLICABILITY; HOLD deliberately WITHOUT frontier_ref.
    OUTPUT_KIND = {"ACTION": "EXECUTE", "EVIDENCE_REQUEST": "VERIFY",
                   "QUESTION": "RESOLVE_APPLICABILITY"}
    for where, nm in next_move_blocks:
        check_next_move(nm, where)
        ref = nm.get("frontier_ref")
        if not ref:
            continue
        all_entries = [e for _, ents in frontier_blocks
                       if isinstance(ents, list) for e in ents
                       if isinstance(e, dict)]
        matched = [e for e in all_entries
                   if ref == e.get("node") or ref == e.get("route_id")]
        if not matched:
            err(f"{where}.frontier_ref: {ref!r} tidak menunjuk opportunity frontier "
                f"mana pun (referential integrity — NextMove = selector over valid "
                f"frontier, review B)")
            continue
        # hole-6: referential passes, but the MEANING match output ↔ kind is not yet checked
        want = OUTPUT_KIND.get(nm.get("output"))
        if want is None:
            # Only HOLD has a special message; OTHER invalid enums are already
            # reported by check_next_move — do not duplicate with a misleading
            # message (cosmetic polish after owner review 8d20107).
            if nm.get("output") == "HOLD":
                err(f"{where}: output='HOLD' TIDAK BOLEH punya frontier_ref — "
                    f"HOLD tidak menunjuk opportunity (int 06 §5, review hole-6)")
            continue
        if not any(e.get("kind") == want for e in matched):
            got = ", ".join(sorted({str(e.get("kind")) for e in matched}))
            err(f"{where}.frontier_ref: output={nm.get('output')!r} butuh kind "
                f"{want}, tapi entry yang ditunjuk kind [{got}] (kecocokan makna "
                f"— review hole-6: ACTION→EXECUTE, EVIDENCE_REQUEST→VERIFY, "
                f"QUESTION→RESOLVE_APPLICABILITY)")

    # Report
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    ok = not errors
    print(f"\nroute schema v0.1 — {len(errors)} error, {len(warnings)} warning "
          f"→ {'VALID ✓' if ok else 'INVALID ✗'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
