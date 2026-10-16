"""OPAQUE & PATH-SAFE user identity contract — shared invariant of the per-user store.

Review 71b3c63 (conditionally green, 27 Sep): after the per-user split, `user_id`
became a storage directory component, and when the bridge arrives its value is
EXTERNAL INPUT (session runtime). Two conditions before the bridge:
  1. cross-user isolation is locked by test (see test_adjudication_path);
  2. user_id must not escape the root via path traversal ('../x', 'a/b').

Contract = reviewer option A (user_id canonical opaque ID) AS AN ARCHITECTURAL
CONTRACT + defensive validation at storage (B). This helper is used SHARED by
`adjudication_ledger._channel` and `route_lineages._path` so both storage
layers have an identical user identity invariant — a fix in one place
applies to both.
"""
from __future__ import annotations

import re

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


def validate_user_id(user_id: str) -> str:
    """Hard-reject a user_id that is not path-safe — ValueError (fail-closed,
    not a fallback to a shared file/directory). Return the valid user_id."""
    if not isinstance(user_id, str) or not _USER_ID_RE.fullmatch(user_id):
        raise ValueError(
            f"user_id is not path-safe: {user_id!r} — must match "
            r"^[A-Za-z0-9_-]{1,128}$ (opaque ID contract of the per-user store; "
            "traversal = cross-user leak / escape from root)"
        )
    return user_id
