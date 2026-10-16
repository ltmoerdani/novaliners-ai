"""Applicable Requirement Set — WHICH requirements from the global registry are relevant to this user now.

internal-docs §25 (M4).

    Global Requirement Registry (WHAT, context-free)
              |
    Contexts: Goal · Verified State · Possible Path (checks) · Route (node) · template route
              |
    Applicable Requirement Set  <- this module
              |
    Requirement State (reader) -> uncertainty -> Question Planner

The registry gets NO applicability/route/strategy/frontier fields: a requirement's applicability is always
RELATIVE to a context, and it is the context that declares relevance:

  - a path CHECK that anchors the `requirement_id` (the domain declares: this path needs that world
    condition);
  - a route NODE that `resolves` that requirement (template composition);
  - a route TEMPLATE that did not come into being because its applicability is NOT_APPLICABLE (an explicit
    statement that "this requirement does not apply through that context").

Three values (not scores, not a ranking; `Applicability` in contracts.py):

  APPLIES         at least one APPLIES context declares this requirement
  UNKNOWN         no APPLIES context, but some context's applicability cannot be established yet
  NOT_APPLICABLE  ALL contexts declaring it say NOT_APPLICABLE

A requirement declared by no context is NOT a member of this set: the registry is not a checklist, and
"no context" is not "applies". Adding a requirement to the registry does not change this module; a new
requirement joins when (and only when) a context anchors it.

`navigable` is not applicability: a path in STOP status (an engine contradiction OR a user decision) still
has its own applicability, but its contexts do not drive the conversation (NextMove is never picked from a
STOP path — doc 14 §12). Two axes, kept separate, never merged.

This module is GENERIC and pure (no I/O, no store, no LLM)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from core.navigation.compat import NAV_CURRENT, assess_path_set
from core.navigation.contracts import Applicability

APPLICABLE_SET_VERSION = 1

# Requirement-level reason codes (machine-readable; not display text).
REASON_APPLIES = "APPLIES_VIA_CONTEXT"
REASON_UNKNOWN = "UNKNOWN_CONTEXT_APPLICABILITY"
REASON_NOT_APPLICABLE = "NOT_APPLICABLE_IN_ALL_CONTEXTS"

# `UNDETERMINED` belongs to route applicability (compose.py); on the applicability axis it means UNKNOWN.
_ROUTE_APPLICABILITY = {
    "APPLIES": str(Applicability.APPLIES),
    "NOT_APPLICABLE": str(Applicability.NOT_APPLICABLE),
    "UNDETERMINED": str(Applicability.UNKNOWN),
    "UNKNOWN": str(Applicability.UNKNOWN),
}


@dataclass(frozen=True)
class ApplicabilityContext:
    """One context declaring a requirement's relevance, together with its provenance."""

    kind: str  # "path" | "route"
    id: str  # path_id | route_id | "template:<template_id>"
    applicability: str
    via: str  # "check" | "node" | "template"
    strength: str | None = None  # check: hard|prereq; node: hard|soft
    navigable: bool = True
    ref: str | None = None  # check_id | node_id | template_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "applicability": self.applicability,
            "via": self.via,
            "strength": self.strength,
            "navigable": self.navigable,
            "ref": self.ref,
        }


@dataclass(frozen=True)
class ApplicableRequirement:
    requirement_id: str
    applicability: str
    reason: str
    contexts: tuple[ApplicabilityContext, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "applicability": self.applicability,
            "reason": self.reason,
            "contexts": [c.to_dict() for c in self.contexts],
        }


@dataclass(frozen=True)
class ApplicableRequirementSet:
    items: tuple[ApplicableRequirement, ...]
    version: int = APPLICABLE_SET_VERSION

    def get(self, requirement_id: str) -> ApplicableRequirement | None:
        return next((i for i in self.items if i.requirement_id == requirement_id), None)

    def ids(self, applicability: str | None = None) -> list[str]:
        return [
            i.requirement_id for i in self.items if applicability is None or i.applicability == applicability
        ]

    def __len__(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "items": [i.to_dict() for i in self.items]}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "ApplicableRequirementSet":
        return ApplicableRequirementSet(
            version=int(d.get("version", APPLICABLE_SET_VERSION)),
            items=tuple(
                ApplicableRequirement(
                    requirement_id=i["requirement_id"],
                    applicability=i["applicability"],
                    reason=i["reason"],
                    contexts=tuple(ApplicabilityContext(**c) for c in i["contexts"]),
                )
                for i in d.get("items") or []
            ),
        )


def owner_path_id(route: Mapping[str, Any], paths: Mapping[str, Mapping[str, Any]]) -> str | None:
    """The path owning a route: `path_id` when present, otherwise via `strategy_id` (like Readiness)."""
    pid = route.get("path_id")
    if pid in paths:
        return pid
    return next((i for i, p in paths.items() if p.get("strategy_id") == route.get("strategy_id")), None)


def _aggregate(contexts: Sequence[ApplicabilityContext]) -> tuple[str, str]:
    """Contexts -> (applicability, reason code). A single APPLIES context is enough."""
    values = {c.applicability for c in contexts}
    if str(Applicability.APPLIES) in values:
        return str(Applicability.APPLIES), REASON_APPLIES
    if str(Applicability.UNKNOWN) in values:
        return str(Applicability.UNKNOWN), REASON_UNKNOWN
    return str(Applicability.NOT_APPLICABLE), REASON_NOT_APPLICABLE


def build_applicable_set(
    path_set: Mapping[str, Any] | None,
    route_data: Mapping[str, Any] | None = None,
    *,
    template_requirements: Mapping[str, Sequence[str]] | None = None,
) -> ApplicableRequirementSet:
    """(PathSet, optional route composition result, optional requirements per template) -> applicable set.

    `route_data` = the output of `compose_path_routes` (`routes`, `not_born`); None/empty = no routes (valid:
    routes are optional) — the set still forms from path checks. A PathSet that is not CURRENT (missing /
    other version / corrupt content) is not read (DATA-01): an empty set, never invented content.
    `template_requirements` = {template_id: [requirement_id...]} used ONLY to record requirements from
    templates that did not come into being due to NOT_APPLICABLE (a failure the composer found, not one
    guessed here)."""
    by_req: dict[str, list[ApplicabilityContext]] = {}
    if assess_path_set(path_set)["status"] != NAV_CURRENT:
        return ApplicableRequirementSet(items=())
    paths = {p["path_id"]: p for p in (path_set or {}).get("paths") or []}
    navigable = {pid: p.get("status") != "STOP" for pid, p in paths.items()}
    for pid, p in paths.items():
        for c in p.get("checks") or []:
            rid = c.get("requirement_id")
            if not rid:
                continue  # a check without a requirement anchor is not a requirement (path-only condition)
            by_req.setdefault(rid, []).append(
                ApplicabilityContext(
                    kind="path",
                    id=pid,
                    applicability=str(p.get("applicability") or Applicability.UNKNOWN),
                    via="check",
                    strength=c.get("kind"),
                    navigable=navigable[pid],
                    ref=str(c.get("check_id")),
                )
            )
    for r in (route_data or {}).get("routes") or []:
        pid = owner_path_id(r, paths)
        status = (r.get("applicability") or {}).get("status")
        app = _ROUTE_APPLICABILITY.get(status, str(Applicability.UNKNOWN))
        nav = navigable.get(pid, True) and r.get("lineage_status", "OPEN") == "OPEN"
        for n in r.get("nodes") or []:
            resolves = n.get("resolves") or []
            if not resolves:
                continue
            by_req.setdefault(resolves[0], []).append(
                ApplicabilityContext(
                    kind="route",
                    id=str(r.get("route_id")),
                    applicability=app,
                    via="node",
                    strength=n.get("strength"),
                    navigable=nav,
                    ref=str(n.get("node_id")),
                )
            )
    for nb in (route_data or {}).get("not_born") or []:
        if nb.get("outcome") != "NO_ROUTE_NOT_APPLICABLE":
            continue
        tid = str(nb.get("template_id"))
        for rid in (template_requirements or {}).get(tid, ()):
            by_req.setdefault(rid, []).append(
                ApplicabilityContext(
                    kind="route",
                    id=f"template:{tid}",
                    applicability=str(Applicability.NOT_APPLICABLE),
                    via="template",
                    navigable=navigable.get(nb.get("path_id"), True),
                    ref=tid,
                )
            )
    items = []
    for rid in sorted(by_req):
        ctxs = tuple(by_req[rid])
        app, reason = _aggregate(ctxs)
        items.append(ApplicableRequirement(rid, app, reason, ctxs))
    return ApplicableRequirementSet(items=tuple(items))
