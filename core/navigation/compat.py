"""Navigation artifact compatibility — "zero paths because of evidence" != "zero paths because this
artifact is older".

internal-docs §11 (DATA-01..03). Artifacts stored before the current navigation schema do not
carry a trustworthy PathSet (e.g. a fixed route list from an older era, or no projection at all). Reading
them as `paths=[]` would masquerade as an engine decision ("the verified state supports no path"). Contract:

    PathSet of the current version, readable content    -> CURRENT   (0..N paths is an engine finding)
    PathSet missing / different version / BROKEN content -> LEGACY    (needs_rediagnosis = True; NO path is
                                                          invented, NO migration is guessed)

Automatic migration is deliberately not provided: old paths were born from fixed lists/string gates, without
provenance mappable to strategy + evidence anchors. The only honest route is re-diagnosis over the same
evidence (the check-in cycle). Pure functions; no store, no domain."""

from __future__ import annotations

from typing import Any

from core.navigation.contracts import Feasibility
from core.navigation.evaluator import PATHSET_VERSION

NAV_CURRENT = "CURRENT"
NAV_LEGACY = "LEGACY"

_TEXT = {
    "PATHSET_MISSING": {
        "id": "artefak ini dibuat sebelum model navigasi saat ini dan tidak memuat hasil Possible Path",
        "en": "This map was made before the current way of finding paths, so it holds no path result. "
        "That is not the same as having no paths.",
    },
    "SCHEMA_VERSION_MISMATCH": {
        "id": "artefak ini dibuat dengan skema navigasi versi lain; hasilnya tidak dibaca sebagai temuan",
        "en": "This map was made with an older version of the path model, so its result is not read as a "
        "current finding. That is not the same as having no paths.",
    },
    "PATHSET_MALFORMED": {
        "id": "hasil path pada artefak ini tidak dapat dibaca (rusak); ia tidak dibaca sebagai temuan "
        "dan tidak dikarang ulang",
        "en": "The path result in this map is unreadable, so it is not read as a current finding — "
        "and none is invented. That is not the same as having no paths.",
    },
}


def _malformed_reason(path_set: Any) -> str | None:
    """A version-matching PathSet whose content cannot be read -> a reason; healthy content -> None.

    A valid path entry is a dict with non-empty `path_id`/`strategy_id` strings, an enum `feasibility`, and
    a list-of-dict `checks` — exactly the fields downstream readers DO subscript (readiness
    `p0["strategy_id"]`/`p0["checks"]`/`p0["feasibility"]`, evaluator `Feasibility(...)`, POST /routes
    `route_substrate`). Matching version + broken content must neither 500 downstream nor be read as an
    engine finding — both lose to the explicit classification here (one decision gate for "is this result
    trustworthy")."""
    if not isinstance(path_set.get("paths"), list):
        return "PATHSET_MALFORMED"
    feas = {f.value for f in Feasibility}
    for p in path_set["paths"]:
        if not isinstance(p, dict) or not isinstance(p.get("path_id"), str) or not p["path_id"]:
            return "PATHSET_MALFORMED"
        if not isinstance(p.get("strategy_id"), str) or not p["strategy_id"]:
            return "PATHSET_MALFORMED"
        if p.get("feasibility") not in feas:
            return "PATHSET_MALFORMED"
        if not isinstance(p.get("checks"), list) or any(
            not isinstance(c, dict) for c in p["checks"]
        ):
            return "PATHSET_MALFORMED"
        rs = p.get("route_substrate")
        if rs is not None and not isinstance(rs, dict):
            return "PATHSET_MALFORMED"
    return None


def assess_path_set(path_set: Any) -> dict[str, Any]:
    """A PathSet (or None) -> {status, needs_rediagnosis, reason_code, found_version, current_version,
    detail, i18n}. `detail`/`i18n` are engine text; the UI only renders it."""
    if not isinstance(path_set, dict) or "paths" not in path_set:
        code, found = "PATHSET_MISSING", None
    elif path_set.get("version") != PATHSET_VERSION:
        code, found = "SCHEMA_VERSION_MISMATCH", path_set.get("version")
    elif (bad := _malformed_reason(path_set)) is not None:
        code, found = bad, path_set.get("version")
    else:
        return {
            "status": NAV_CURRENT,
            "needs_rediagnosis": False,
            "reason_code": None,
            "found_version": PATHSET_VERSION,
            "current_version": PATHSET_VERSION,
            "detail": "",
            "i18n": {},
        }
    txt = _TEXT[code]
    return {
        "status": NAV_LEGACY,
        "needs_rediagnosis": True,
        "reason_code": code,
        "found_version": found,
        "current_version": PATHSET_VERSION,
        "detail": txt["id"],
        "i18n": {k: {"detail": v} for k, v in txt.items() if k != "id"},
    }


def is_legacy(path_set: Any) -> bool:
    return assess_path_set(path_set)["status"] == NAV_LEGACY
