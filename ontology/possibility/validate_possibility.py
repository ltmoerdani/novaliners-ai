#!/usr/bin/env python
"""Domain possibility-space validator (internal-docs §Candidate Generation).

`ontology/possibility/<domain>.json` declares the STRATEGIES supported by domain knowledge, when a
strategy becomes a candidate, and the checks that determine feasibility. The validator keeps:

  1. every strategy_id registered and `active` in the strategy registry (ontology/route/strategies.json),
     and every active strategy holding a declaration (no orphan templates that could never become a path);
  2. `emerges_when` present and well-formed (without an emergence basis, a strategy can never be born);
  3. every referenced signal declared by the domain reader (no orphan ids/typos that silently = UNKNOWN);
  4. every check: id unique per strategy, valid `kind`, `requirement_id` (when present) PRESENT in the
     Requirement Registry, `unlock` filled, and display text only for checks without a requirement;
  5. the file carries no `motion`/path identity: motion is read from the strategy registry (domain label).
  6. `patterns` (Knowledge -> Mechanism -> Candidate Possibility): every pattern names mechanisms that
     EXIST in the catalog, rests on KB interventions that EXIST and whose `targets` intersect the
     mechanism's constraints (a pattern must not invent knowledge), `direction` unique and not a
     registered strategy.

Inline negative tests: every mutation must be rejected (the validator must not be vacuous).
Usage: python ontology/possibility/validate_possibility.py (from mvp/). Exit 0 = valid.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.navigation.contracts import CHECK_KINDS  # noqa: E402
from core.navigation.predicate import signal_ids  # noqa: E402
from domains.revenue.navigation.signals import declared_signal_ids  # noqa: E402
from engine.domain_pack import mechanisms as mechanism_catalog  # noqa: E402
from engine.knowledge import get_kb  # noqa: E402
from engine.requirements import load_registry  # noqa: E402
from ontology.route.strategies import load_strategies  # noqa: E402

HERE = Path(__file__).parent
DOC_PATH = HERE / "revenue.json"
FORBIDDEN_STRATEGY_KEYS = {"motion", "path_id", "status"}
ALLOWED_STRATEGY_KEYS = {
    "strategy_id",
    "title",
    "basis",
    "presentation",
    "emerges_when",
    "not_applicable_when",
    "checks",
}
CHECK_KEYS = {"check_id", "signal", "kind", "requirement_id", "title", "unlock", "i18n"}
I18N_FIELDS = {"title", "unlock"}


def validate(doc: dict, registry_ids: set[str], strategies: dict, signals: set[str]) -> list[str]:
    errs: list[str] = []
    if not doc.get("space_id"):
        errs.append("space_id wajib")
    goal = doc.get("goal_signal")
    if goal and goal not in signals:
        errs.append(f"goal_signal {goal!r} tidak dideklarasikan pembaca domain")
    seen: set[str] = set()
    for i, s in enumerate(doc.get("strategies") or []):
        sid = s.get("strategy_id")
        w = f"strategies[{i}]({sid})"
        if sid in seen:
            errs.append(f"{w}: strategy_id duplikat")
        seen.add(sid)
        reg = strategies.get(sid)
        if reg is None:
            errs.append(f"{w}: tidak terdaftar di strategy registry")
        elif reg.get("status") != "active":
            errs.append(f"{w}: strategi berstatus {reg.get('status')!r} tidak boleh ada di ruang kemungkinan")
        for k in set(s) & FORBIDDEN_STRATEGY_KEYS:
            errs.append(
                f"{w}: field `{k}` dilarang (motion/status milik strategy registry, path_id diturunkan)"
            )
        for k in set(s) - ALLOWED_STRATEGY_KEYS - FORBIDDEN_STRATEGY_KEYS:
            errs.append(f"{w}: field tidak dikenal `{k}`")
        if not str(s.get("title") or "").strip():
            errs.append(f"{w}: title wajib")
        em = s.get("emerges_when")
        if not em:
            errs.append(f"{w}: emerges_when wajib — strategi tanpa dasar kemunculan tak pernah bisa lahir")
        try:
            refs = signal_ids(em) + signal_ids(s.get("not_applicable_when"))
        except ValueError as e:
            errs.append(f"{w}: predikat tidak valid: {e}")
            refs = []
        for r in refs:
            if r not in signals:
                errs.append(f"{w}: sinyal {r!r} tidak dideklarasikan pembaca domain")
        cids: set[str] = set()
        for j, c in enumerate(s.get("checks") or []):
            cw = f"{w}.checks[{j}]"
            for k in set(c) - CHECK_KEYS:
                errs.append(f"{cw}: field tidak dikenal `{k}`")
            cid = c.get("check_id")
            if not cid or " " in str(cid):
                errs.append(f"{cw}: check_id wajib berupa id stabil (tanpa spasi), bukan kalimat")
            if cid in cids:
                errs.append(f"{cw}: check_id {cid!r} duplikat dalam strategi")
            cids.add(cid)
            if c.get("kind") not in CHECK_KINDS:
                errs.append(f"{cw}: kind {c.get('kind')!r} di luar {CHECK_KINDS}")
            if c.get("signal") not in signals:
                errs.append(f"{cw}: sinyal {c.get('signal')!r} tidak dideklarasikan pembaca domain")
            rid = c.get("requirement_id")
            if rid is not None and rid not in registry_ids:
                errs.append(f"{cw}: requirement_id {rid!r} TIDAK ada di Requirement Registry")
            if not rid and not str(c.get("title") or "").strip():
                errs.append(f"{cw}: check tanpa requirement wajib punya title (teks tampilan)")
            if not str(c.get("unlock") or "").strip():
                errs.append(f"{cw}: unlock wajib (peta bukti yang harus dikumpulkan)")
            for lang, tx in (c.get("i18n") or {}).items():
                for k, v in (tx or {}).items():
                    if k not in I18N_FIELDS or not isinstance(v, str) or not v.strip():
                        errs.append(f"{cw}.i18n[{lang}]: `{k}` tidak sah (hanya title/unlock, non-kosong)")
        pres = (s.get("presentation") or {}).get("en") or {}
        if not (pres.get("word") and pres.get("short") and pres.get("basis")):
            errs.append(f"{w}: presentation.en wajib punya word, short, dan basis")
    for sid, reg in strategies.items():
        if reg.get("status") == "active" and sid not in seen:
            errs.append(f"strategi aktif {sid!r} tidak punya deklarasi di ruang kemungkinan")
    return errs


PATTERN_KEYS = {
    "direction",
    "title",
    "thesis",
    "basis",
    "mechanism_ids",
    "context_when",
    "not_applicable_when",
    "grounded_in",
    "presentation",
}


def validate_patterns(
    doc: dict, strategies: dict, signals: set[str], catalog: dict, interventions: dict
) -> list[str]:
    """Mechanism -> possibility patterns: their knowledge basis must be REAL in the repository."""
    errs: list[str] = []
    seen: set[str] = set()
    for i, p in enumerate(doc.get("patterns") or []):
        d = p.get("direction")
        w = f"patterns[{i}]({d})"
        if not d or not str(d).replace("_", "").isalnum():
            errs.append(f"{w}: direction wajib alfanumerik/underscore")
        if d in seen:
            errs.append(f"{w}: direction duplikat")
        seen.add(d)
        if d in strategies:
            errs.append(f"{w}: direction sama dengan strategi terdaftar — deklarasikan di `strategies`")
        for k in set(p) - PATTERN_KEYS:
            if k == "requires":
                errs.append(
                    f"{w}: `requires` sudah tidak ada — namanya bertabrakan dengan Requirement (Registry); "
                    "konteks kemunculan pola ditulis `context_when`"
                )
                continue
            errs.append(
                f"{w}: field tidak dikenal/dilarang `{k}` (strategy_id/motion/path_id bukan milik pola)"
            )
        if not str(p.get("title") or "").strip():
            errs.append(f"{w}: title wajib")
        mids = p.get("mechanism_ids") or []
        if not mids:
            errs.append(f"{w}: mechanism_ids wajib — pola tanpa mekanisme tak punya dasar")
        constraints: set[str] = set()
        for m in mids:
            if m not in catalog:
                errs.append(f"{w}: mekanisme {m!r} tidak ada di katalog mekanisme")
            else:
                constraints |= set(catalog[m].get("constraints") or [])
            if f"mechanism:{m}" not in signals:
                errs.append(f"{w}: sinyal mechanism:{m} tidak dideklarasikan pembaca domain")
        grounded = p.get("grounded_in") or []
        if not grounded:
            errs.append(f"{w}: grounded_in wajib — pola harus bersandar pada intervensi KB yang ada")
        for g in grounded:
            iv = interventions.get(g.get("intervention_id"))
            if iv is None:
                errs.append(
                    f"{w}: intervensi {g.get('intervention_id')!r} TIDAK ada di KB (knowledge dikarang)"
                )
            elif not (set(iv.get("targets") or []) & constraints):
                errs.append(
                    f"{w}: intervensi {g['intervention_id']} menarget {sorted(iv.get('targets') or [])}, "
                    f"tidak beririsan dengan constraint mekanisme {sorted(constraints)}"
                )
        try:
            refs = signal_ids(p.get("context_when")) + signal_ids(p.get("not_applicable_when"))
        except ValueError as e:
            errs.append(f"{w}: predikat tidak valid: {e}")
            refs = []
        for r in refs:
            if r not in signals:
                errs.append(f"{w}: sinyal {r!r} tidak dideklarasikan pembaca domain")
        pres = (p.get("presentation") or {}).get("en") or {}
        if not (pres.get("word") and pres.get("short") and pres.get("basis") and pres.get("because")):
            errs.append(f"{w}: presentation.en wajib punya word, short, basis, dan because")
        because = pres.get("because")
        if isinstance(because, dict) and (
            set(because) != set(mids) or not all(isinstance(v, str) and v.strip() for v in because.values())
        ):
            errs.append(
                f"{w}: presentation.en.because per mekanisme wajib memuat TEPAT mekanisme penyebab pola "
                f"{sorted(mids)} dengan teks non-kosong"
            )
    return errs


def _negative_pattern_cases(
    doc: dict, strategies: dict, signals: set[str], catalog: dict, kb: dict
) -> list[str]:
    def mut(fn) -> dict:
        d = copy.deepcopy(doc)
        fn(d)
        return d

    cases = {
        "pola: mekanisme hantu": mut(lambda d: d["patterns"][0].update(mechanism_ids=["ghost_mechanism"])),
        "pola: intervensi hantu": mut(
            lambda d: d["patterns"][0].update(grounded_in=[{"intervention_id": "XX-I99"}])
        ),
        "pola: intervensi tak beririsan": mut(
            lambda d: d["patterns"][1].update(grounded_in=[{"intervention_id": "SP-I02"}])
        ),
        "pola: tanpa grounded_in": mut(lambda d: d["patterns"][0].pop("grounded_in")),
        "pola: tanpa mekanisme": mut(lambda d: d["patterns"][0].update(mechanism_ids=[])),
        "pola: arah = strategi terdaftar": mut(
            lambda d: d["patterns"][0].update(direction=next(iter(strategies)))
        ),
        "pola: arah duplikat": mut(lambda d: d["patterns"].append(copy.deepcopy(d["patterns"][0]))),
        "pola: membawa motion": mut(lambda d: d["patterns"][0].update(motion="ACQUISITION")),
        "pola: key lama `requires` (bertabrakan dengan Requirement)": mut(
            lambda d: d["patterns"][0].update(requires="state:revenue_gap")
        ),
        "pola: context_when merujuk sinyal yatim": mut(
            lambda d: d["patterns"][0].update(context_when="state:tidak_ada")
        ),
    }
    return [
        f"validator vacuous: mutasi '{n}' lolos"
        for n, d in cases.items()
        if not validate_patterns(d, strategies, signals, catalog, kb)
    ]


def _negative_cases(doc: dict, ids: set[str], strategies: dict, signals: set[str]) -> list[str]:
    def mut(fn) -> dict:
        d = copy.deepcopy(doc)
        fn(d)
        return d

    cases = {
        "strategi tak terdaftar": mut(lambda d: d["strategies"][0].update(strategy_id="ghost_strategy")),
        "motion di berkas": mut(lambda d: d["strategies"][0].update(motion="ACQUISITION")),
        "emerges_when hilang": mut(lambda d: d["strategies"][0].pop("emerges_when")),
        "sinyal yatim": mut(
            lambda d: d["strategies"][0].update(emerges_when={"any_of": ["state:tidak_ada"]})
        ),
        "requirement bukan registry": mut(
            lambda d: d["strategies"][0]["checks"][0].update(requirement_id="ghost.requirement")
        ),
        "check_id kalimat": mut(
            lambda d: d["strategies"][0]["checks"][0].update(check_id="kapasitas masih ada")
        ),
        "kind asing": mut(lambda d: d["strategies"][0]["checks"][0].update(kind="soft")),
        "unlock kosong": mut(lambda d: d["strategies"][0]["checks"][0].update(unlock="")),
        "strategi aktif tak dideklarasikan": mut(lambda d: d["strategies"].pop()),
        "goal_signal yatim": mut(lambda d: d.update(goal_signal="state:tidak_ada")),
    }
    out = [
        f"validator vacuous: mutasi '{n}' lolos"
        for n, d in cases.items()
        if not validate(d, ids, strategies, signals)
    ]
    return out + ([] if not validate(doc, ids, strategies, signals) else [])


def main() -> int:
    doc = json.loads(DOC_PATH.read_text(encoding="utf-8"))
    ids = set(load_registry())
    strategies = load_strategies()
    signals = declared_signal_ids()
    catalog, kb = mechanism_catalog(), get_kb()["interventions"]
    errs = validate(doc, ids, strategies, signals) + _negative_cases(doc, ids, strategies, signals)
    errs += validate_patterns(doc, strategies, signals, catalog, kb)
    errs += _negative_pattern_cases(doc, strategies, signals, catalog, kb)
    for e in errs:
        print(f"ERROR {e}")
    n = len(doc.get("strategies") or [])
    npat = len(doc.get("patterns") or [])
    print(
        f"POSSIBILITY {DOC_PATH.name}: {n} strategi, {npat} pola, {len(signals)} sinyal dideklarasikan → "
        f"{'VALID ✓' if not errs else 'INVALID ✗'}"
    )
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
