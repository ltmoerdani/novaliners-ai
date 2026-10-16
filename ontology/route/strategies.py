"""Strategy registry (D5 int 08 §8.4) — strategy_id → motion + status.

One source for: (1) a route's motion (the bridge reads it here, not from the
template — T1.13 — and not from the caller); (2) the runtime template library
(only `active` strategies; `proof_only` is never composed). No LLM, deterministic.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
STRATEGY_PATH = HERE / "strategies.json"
TEMPLATE_DIR = HERE / "templates"


def load_strategies(path: Path = STRATEGY_PATH) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {s["strategy_id"]: s for s in data.get("strategies", [])}


def load_motion_vocabulary(path: Path = STRATEGY_PATH) -> tuple[str, ...]:
    """The motion label vocabulary declared by the registry (owned by the domain). The route engine
    (compose, validator) reads this list — no motion enum is hard-coded in route code/schema."""
    vocab = json.loads(path.read_text(encoding="utf-8")).get("motion_vocabulary")
    if not isinstance(vocab, list) or not vocab or len(set(vocab)) != len(vocab):
        raise ValueError("strategies.json: motion_vocabulary wajib list non-kosong tanpa duplikat")
    bad = [m for m in vocab if not isinstance(m, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", m)]
    if bad:
        raise ValueError(f"strategies.json: label motion tidak sah {bad} (pola [A-Z][A-Z0-9_]*)")
    return tuple(vocab)


def motion_for(strategy_id: str) -> str:
    """The strategy's motion — ValueError when the strategy is unregistered (no
    guessing/falling back to a default)."""
    s = load_strategies().get(strategy_id)
    if s is None:
        raise ValueError(f"strategy_id {strategy_id!r} tidak terdaftar di "
                         f"strategies.json (D5)")
    return s["motion"]


def active_template_library(template_dir: Path = TEMPLATE_DIR
                            ) -> list[dict[str, Any]]:
    """Templates whose strategy is `active`, sorted by template_id (deterministic).
    The `proof_only` specimen (landing_first_v1) is excluded. A template whose strategy is NOT
    registered = an orphan artifact -> ValueError (this iteration's audit): passing it over silently
    would hide a template that could actually be composed as an invalid composition path
    (`plan_compositions` relies on valid strategy↔template pairings)."""
    strategies = load_strategies()
    out = []
    for f in sorted(template_dir.glob("*.json")):
        tpl = json.loads(f.read_text(encoding="utf-8"))
        s = strategies.get(tpl.get("strategy_id"))
        if s is None:
            raise ValueError(
                f"{f.name}: strategy_id '{tpl.get('strategy_id')}' tidak terdaftar di "
                f"strategies.json — template yatim (daftarkan strateginya atau hapus template)"
            )
        if s.get("status") == "active":
            out.append(tpl)
    return sorted(out, key=lambda t: t["template_id"])
