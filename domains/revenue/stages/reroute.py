"""P-E Path Rerouting (internal-docs §3.5, roadmap P-E — CORE INNOVATION).

Connecting the broken edge: **outcome → path status**.

Before P-E: an outcome report (J2/J6) only raised the epistemic grade of the
INTERVENTION — the path was recomputed from state alone each session; the loop never
touched the map. After P-E: the outcome also updates the path status
via DETERMINISTIC rules (not LLM opinion — per engine doctrine), emits the
`PATH_STATUS_CHANGED` event, and path history is stored (reopen possible).

Principles preserved (internal-docs §7 + cases #7/#8):
- **Action failure ≠ path failure**: `not_moved` does NOT demote the path —
  execution failure ≠ wrong diagnosis ≠ wrong path. Only the
  execution/sample/window check can do that (later P-E phase).
- **Disconfirm → STOP**: `regret` ("should not have been done") is the
  user's strongest counter-evidence → the path is STOPPED (not deleted — path
  history is knowledge, docs §4.5).
- **Argued reopen**: `moved` on a STOPPED path reopens it
  (OPEN) with a recorded reason — an argued transition, not a re-recommendation.
- **confounded** shifts nothing (unmeasurable result — consistent
  with P3 knowledge confidence).

State machine per path (per user, persisted in store/path_states.py):

    OPEN --regret--> STOPPED --moved--> OPEN
    not_moved/confounded: counter only (evidence, not a verdict)

This outcome state is the path LIFECYCLE (process decision/state, universal:
OPEN/PAUSED/STOPPED/CLOSED), not feasibility: "the user decided to stop" is not the same
as "the engine found a contradiction". Its attachment to a path is in
domains/revenue/navigation/paths.py (`lifecycles_from_states`);
the state key = path_id (path identity from the strategy, not the motion).
Docs: internal-docs §Lifecycle."""
from __future__ import annotations

import re
from typing import Any

OPEN, STOPPED = "OPEN", "STOPPED"

# valid path_id: "path.<strategy_id>" (core.navigation.contracts.path_id_for). Syntax only — the list of
# live paths is determined by the generator per user state, not a fixed enum.
PATH_ID_RE = re.compile(r"^path\.[a-z0-9_]+$")

VALID_OUTCOMES = ("moved", "not_moved", "regret", "confounded")


def new_path_state() -> dict[str, Any]:
    return {"outcome_state": OPEN, "moved": 0, "not_moved": 0, "regret": 0, "confounded": 0}


def apply_outcome(state: dict[str, Any] | None, outcome: str) -> tuple[dict[str, Any], dict | None]:
    """One outcome → (new state, event|None). Pure function, 0 LLM.

    event: {"type": "PATH_STATUS_CHANGED", "from": ..., "to": ..., "cause": ...}
    None = no state transition (counter only) — not an error."""
    st = dict(state or new_path_state())
    for k in VALID_OUTCOMES:
        st.setdefault(k, 0)
    st.setdefault("outcome_state", "OPEN")

    if outcome == "regret":
        if st["outcome_state"] != "STOPPED":
            ev = {
                "type": "PATH_STATUS_CHANGED",
                "from": st["outcome_state"], "to": "STOPPED",
                "cause": "outcome=regret — bukti kontra dari user (bukan asumsi engine)",
            }
            st["outcome_state"] = "STOPPED"
        else:
            ev = None  # already stopped — reinforcement, not a new transition
    elif outcome == "moved":
        if st["outcome_state"] == "STOPPED":
            ev = {
                "type": "PATH_STATUS_CHANGED",
                "from": "STOPPED", "to": "OPEN",
                "cause": "outcome=moved — jalur REOPEN: bukti positif mematahkan stop",
            }
            st["outcome_state"] = "OPEN"
        else:
            ev = None
    else:
        ev = None  # not_moved/confounded — counter only (action failure ≠ path failure)

    st[outcome] += 1
    return st, ev
