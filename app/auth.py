"""API actor authentication (BC-02/CP-30, int 16 DR-17) — bearer token OPTIONAL.

Two modes:
- **TOKEN mode**: env `NOVALINERS_ACTOR_TOKENS` contains JSON `{token: user_id}`.
  Every endpoint (except public exempt ones) must carry `Authorization: Bearer <token>`;
  the actor identity is DERIVED from the token — a `user_id` from the body/client NEVER becomes
  the authority (DR-17: client-provided ID is not proof of access rights). Session ownership is enforced
  by middleware: a session owned by another actor → 403; someone else's workspace → 403.
- **LOCAL mode (default, env not set)**: the old MVP behavior stays intact (no auth) so that
  all deterministic/live local suites still run without headers. Deployment boundary is
  EXPLICIT: LOCAL mode is NOT for public multi-user (int 16 BC-02).

Tokens are NEVER printed to logs. Env is re-read per request (no cache) so it can be
reconfigured without a restart and is easy to test.
"""
from __future__ import annotations

import json
import os

TOKENS_ENV = "NOVALINERS_ACTOR_TOKENS"

# Public paths that do not require a bearer (health/banner/docs).
EXEMPT_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}


def configured_tokens() -> dict[str, str]:
    """token→user_id map from env; empty = LOCAL mode. Invalid JSON → ignored
    (fail-closed to LOCAL is forbidden: safer to treat broken JSON = TOKEN mode with an empty map
    = every request 401)."""
    raw = os.environ.get(TOKENS_ENV, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}  # handled by mode(): env present but broken is still treated as TOKEN mode
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


def auth_mode() -> str:
    """'token' if env is set (even if the JSON is broken/empty → fail-closed), 'local' if not."""
    return "token" if os.environ.get(TOKENS_ENV, "").strip() else "local"


def authenticate(authorization_header: str | None) -> str | None:
    """Validate the `Authorization: Bearer <token>` header in TOKEN mode.
    Return the actor's user_id, or None if invalid (the caller must reject with 401)."""
    tokens = configured_tokens()
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return None
    token = authorization_header[len("Bearer "):].strip()
    return tokens.get(token)


def actor_from_path_session(sid: str, actor: str | None) -> bool:
    """True if access to session `sid` by `actor` is allowed. Anonymous sessions (without a user_id)
    remain readable via sid in TOKEN mode (MVP; boundary documented in the module docstring)."""
    if actor is None:
        return True
    from store.memory import store  # local import: avoid a cycle when importing app
    s = store.get(sid)
    if s is None:
        return True  # 404 is handled by the endpoint, not 403 here
    return not s.user_id or s.user_id == actor
