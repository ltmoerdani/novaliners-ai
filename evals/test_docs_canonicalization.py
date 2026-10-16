"""Documentation guard: canonical map (int 15) ↔ real files ↔ stale terms ↔ links.

Background: after the Universal Navigation architecture closed, old-era documents are
intentionally kept. The risk guarded here: historical documents being read as the current
contract (e.g. "lima jalur tetap" [five fixed paths], `REQ_EN`, `revenue_paths`). This guard
does NOT judge architecture content (that is the navigation tests' job); it checks
documentation discipline:

  D1  the `internal-docs` inventory is complete: every .md under docs/
      (outside design/knowledge assets) is listed, and every listed path exists.
  D2  HISTORICAL / RESEARCH / TEST classes must carry a banner within their first 60 lines
      (the banner names the classification, not just "old").
  D3  stale terms (REQ_EN, GATE_REQ, CANONICAL_PATHS, CANON_PATHS, PATH_COPY,
      revenue_paths, build_revenue_paths, stages/paths.py, "lima/5 jalur tetap"
      [five/5 fixed paths]...) may only appear on lines that carry historical/rejection
      context (±2-line window), or in documents classified HISTORICAL/RESEARCH/TEST.
      CANONICAL/SUPPORTING documents + READMEs must not use them as current claims.
  D4  relative links in docs/ and README resolve to files (and to headings, when an
      anchor is present).
  D5  the root README / mvp/README states the current architecture (Possible Path 0..N,
      Candidate Possibility, references to doc 14 and int 15) and no longer describes
      the repo as a research workspace.
  D6  doc 14 / int 15 contain the key concepts (single canonical source).

Inline negative tests: every rule must be able to reject (not vacuous).
Deterministic, no LLM, no network. Run: .venv/bin/python evals/test_docs_canonicalization.py
"""
from __future__ import annotations

import pathlib
import re
import sys
from urllib.parse import unquote

REPO = pathlib.Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"
FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'✅' if ok else '❌'} {label}" + (f" | {detail}" if detail else ""))
    if not ok:
        FAILS.append(label)


# --------------------------------------------------------------------------- scope
EXCLUDE_PARTS = (
    "internal-docs",  # book summaries: source material, not architecture
    "/uploads/",
    "/node_modules/",
    "internal-docs per brief/",  # tooling files + build spec (spec has its own notes)
    "internal-docs Novaliners",
    "internal-docs Navigation chat diagnostik/",
)


def in_scope(p: pathlib.Path) -> bool:
    rel = p.relative_to(REPO).as_posix()
    return not any(x in rel for x in EXCLUDE_PARTS)


def doc_files() -> list[pathlib.Path]:
    return sorted(p for p in DOCS.rglob("*.md") if in_scope(p))


DOC15 = DOCS / "03-architecture-tech/15-documentation-canonicalization.md"
DOC14 = DOCS / "03-architecture-tech/14-universal-navigation-architecture.md"


# --------------------------------------------------------------------------- D1/D2: inventory
ROW = re.compile(r"^\|\s*`(docs/[^`]+\.md)`\s*\|\s*([A-Z]+)\s*\|")
CLASSES = {"CANONICAL", "SUPPORTING", "HISTORICAL", "RESEARCH", "TEST"}


def parse_inventory(text: str) -> dict[str, str]:
    inv: dict[str, str] = {}
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            inv[m.group(1)] = m.group(2)
    return inv


BANNER_RE = {
    "HISTORICAL": re.compile(r"HISTORICAL|HISTORIS|SUPERSEDED|\bPLAN\b", re.I),
    "RESEARCH": re.compile(r"RESEARCH|RAW ARCHIVE|Arsip|Deprecated", re.I),
    "TEST": re.compile(r"HISTORICAL|SUPERSEDED|Catatan pembacaan|TEST", re.I),
}


def head(p: pathlib.Path, n: int = 60) -> str:
    return "\n".join(p.read_text(encoding="utf-8").splitlines()[:n])


# --------------------------------------------------------------------------- D3: stale terms
STRICT_TERMS = re.compile(
    r"REQ_EN|GATE_REQ|CANONICAL_PATHS|CANON_PATHS|PATH_COPY|revenue_paths|"
    r"build_revenue_paths|stages/paths\.py|\bpaths\.py\b"
)
PHRASE_TERMS = re.compile(
    r"(?:five|\b5\b|lima)[ -]+(?:fixed |canonical |kanonik |possible )?(?:paths?|jalur|jalan|routes?|rute)\b"
    r"|fixed five|\b5 fixed\b|five canonical|canonical five"
    r"|lima (?:jalur )?(?:kanonik|tetap)|jalur (?:kanonik|tetap)"
    r"|ELIGIBLE\s*/\s*CONDITIONAL|GO\s*/\s*CONDITIONAL",
    re.I,
)
# context that makes a term occurrence "not misleading": rejection / history / demo / vocabulary
CONTEXT = re.compile(
    r"dihapus|removed|historis|historical|SUPERSEDED|digantikan|diganti|menggantikan|Era 9|dulu|sebelum|"
    r"snapshot|bukan|\bNOT\b|jangan|usang|demo|ilustrasi|ilustratif|cerita|skenario|prototype|prototipe|"
    r"kosakata|vocabulary|dinamis|0\.\.N|LEGACY|sejarah|Deprecated|arsip|rekonsiliasi|"
    r"bukan semesta|tidak (?:lagi|ada|berjumlah|memakai)|tak (?:lagi|ada)|kini|sekarang|tanggalnya",
    re.I,
)
STRICT_CONTEXT = re.compile(
    r"dihapus|hapus|removed|historis|historical|HISTORICAL|SUPERSEDED|superseded|digantikan|diganti|"
    r"menggantikan|Era 9|dulu|sebelum|lama\b|snapshot|usang|dikeluarkan|tak ada lagi|tidak ada lagi|"
    r"bukan|NOT|jangan|sejarah|riwayat|Deprecated|arsip|rekonsiliasi|rencana 2[0-9] Sep|"
    r"dulu|kini|sekarang|pada 2[0-9] Sep|27 Sep|18 Sep|21 Sep|30 Sep|25 Sep|19 Sep|sejak|"
    r"di[- ]?supersede|diganti|tidak lagi|masa lalu|era lama|legacy|LEGACY|beberapa dokumen",
    re.I,
)


def stale_findings(text: str, strict_only: bool = False) -> list[tuple[int, str]]:
    lines = text.splitlines()
    out: list[tuple[int, str]] = []
    in_code = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_code = not in_code
        strict = STRICT_TERMS.search(line)
        phrase = None if strict_only else PHRASE_TERMS.search(line)
        if not (strict or phrase):
            continue
        span = 2 if strict else 1
        window = " ".join(lines[max(0, i - span): i + span + 1])
        ctx = STRICT_CONTEXT if strict else CONTEXT
        if not ctx.search(window):
            out.append((i + 1, line.strip()[:140]))
    return out


# --------------------------------------------------------------------------- D4: links
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def slugify(h: str) -> str:
    h = re.sub(r"[`*_]", "", h.strip().lower())
    h = re.sub(r"[^\w\- ]", "", h, flags=re.UNICODE)
    return h.replace(" ", "-")


def headings(p: pathlib.Path) -> set[str]:
    out: set[str] = set()
    in_code = False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m:
            out.add(slugify(m.group(1)))
    return out


def broken_links(p: pathlib.Path) -> list[str]:
    bad: list[str] = []
    text = p.read_text(encoding="utf-8")
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        for m in LINK.finditer(line):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")) or "{" in target:
                if target.startswith("#"):
                    own = headings(p)
                    if target[1:] not in own and slugify(unquote(target[1:])) not in own:
                        bad.append(f"{target} (anchor tak ada)")
                continue
            path_part, _, anchor = target.partition("#")
            ref = (p.parent / unquote(path_part)).resolve()
            if not ref.exists():
                bad.append(f"{target} (berkas tak ada)")
            elif anchor and ref.suffix == ".md" and slugify(unquote(anchor)) not in headings(ref):
                bad.append(f"{target} (anchor tak ada)")
    return bad


# =========================================================================== run
def main() -> int:
    docs = doc_files()
    d15 = DOC15.read_text(encoding="utf-8")
    inv = parse_inventory(d15)

    # ---- D1 inventory
    check("D1.0 inventaris int 15 terbaca (>= 80 baris)", len(inv) >= 80, f"{len(inv)} baris")
    check("D1.1 semua kelas valid", all(c in CLASSES for c in inv.values()),
          ", ".join(sorted({c for c in inv.values() if c not in CLASSES})))
    rels = {p.relative_to(REPO).as_posix() for p in docs}
    missing = sorted(rels - set(inv))
    ghost = sorted(x for x in inv if not (REPO / x).exists())
    check("D1.2 setiap .md di docs/ tercantum di inventaris", not missing, "; ".join(missing[:5]))
    check("D1.3 setiap jalur di inventaris ada", not ghost, "; ".join(ghost[:5]))

    # ---- D2 banner per class
    for klass, rx in BANNER_RE.items():
        bad = [x for x, c in inv.items()
               if c == klass and (REPO / x).exists() and not rx.search(head(REPO / x))]
        check(f"D2 kelas {klass}: berbanner dalam 60 baris pertama", not bad, "; ".join(bad[:5]))

    # ---- D3 stale terms
    flagged: list[str] = []
    for x, c in inv.items():
        if c in ("HISTORICAL", "RESEARCH", "TEST") or not (REPO / x).exists():
            continue
        f = stale_findings((REPO / x).read_text(encoding="utf-8"))
        flagged += [f"{x}:{ln}: {t}" for ln, t in f]
    for extra in ("README.md", "mvp/README.private.md"):
        f = stale_findings((REPO / extra).read_text(encoding="utf-8"))
        flagged += [f"{extra}:{ln}: {t}" for ln, t in f]
    check("D3 tidak ada istilah usang tanpa konteks historis (CANONICAL/SUPPORTING/README)", not flagged,
          f"{len(flagged)} temuan; contoh: " + " || ".join(flagged[:4]))

    # D3 negative tests: the detector actually rejects
    check("D3-neg1 klaim saat ini 'Possible Path: lima jalur tetap' terdeteksi",
          bool(stale_findings("Possible Path di engine adalah lima jalur tetap.\n")))
    check("D3-neg2 `REQ_EN` tanpa konteks terdeteksi",
          bool(stale_findings("Gunakan kamus REQ_EN untuk teks readiness.\n")))
    check("D3-neg3 konteks historis meloloskan", not stale_findings("`REQ_EN` dihapus; kini registry.\n"))
    check("D3-neg4 konteks 'bukan semesta' meloloskan",
          not stale_findings("Lima motion adalah kosakata, bukan semesta path (lima jalur demo).\n"))

    # ---- D4 links
    link_files = docs + [REPO / "README.md", REPO / "mvp/README.private.md"]
    broken = []
    for p in link_files:
        broken += [f"{p.relative_to(REPO).as_posix()} -> {b}" for b in broken_links(p)]
    check("D4 tautan relatif (dan anchor) di docs/ + README resolve", not broken,
          f"{len(broken)} rusak; contoh: " + " || ".join(broken[:4]))
    probe = REPO / ".docs_probe_tmp.md"
    try:
        probe.write_text("[x](docs/tidak-ada-berkas.md)\n", encoding="utf-8")
        check("D4-neg1 tautan ke berkas yang tidak ada terdeteksi", bool(broken_links(probe)))
    finally:
        probe.unlink(missing_ok=True)

    # ---- D5 README
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    mvp = (REPO / "mvp/README.private.md").read_text(encoding="utf-8")
    for label, txt in (("README.md", readme), ("mvp/README.private.md", mvp)):
        check(f"D5 {label}: menyebut Possible Path 0..N", "0..N" in txt and "Possible Path" in txt)
        check(f"D5 {label}: merujuk doc 14 dan int 15", "14-universal-navigation-architecture.md" in txt
              and "15-documentation-canonicalization.md" in txt)
    check("D5 README.md: Candidate Possibility + UNKNOWN ≠ ABSENT disebut",
          "Candidate Possibility" in readme and "UNKNOWN ≠ ABSENT" in readme)
    check("D5 README.md: tidak lagi 'workspace riset'", "workspace riset" not in readme.lower()
          and "kode prototype akan menyusul" not in readme.lower())
    check("D5 mvp/README.private.md: memisahkan implementasi saat ini dari milestone historis",
          "Implementasi saat ini" in mvp and "Jejak milestone historis" in mvp)

    # ---- D6 key concepts in doc 14 / 15
    d14 = DOC14.read_text(encoding="utf-8")
    for tok in ("Candidate Possibility", "Possible Path", "0..N", "Requirement Registry", "UNKNOWN",
                "stop_provenance", "Presentation cap", "ENGINE_CONTRADICTION", "LIFECYCLE",
                "compose_path_routes"):
        check(f"D6 doc 14 memuat '{tok}'", tok in d14)
    title_rx = re.compile(r"^#\s*\d*\s*[—-]?\s*Universal Navigation Architecture", re.M)
    check("D6 hanya satu dokumen arsitektur navigasi kanonik (tak ada judul kedua)",
          sum(1 for p in docs if title_rx.search(p.read_text(encoding="utf-8"))) == 1)
    check("D6 int 15 mendeklarasikan dirinya peta, bukan arsitektur baru", "bukan arsitektur baru" in d15)

    print()
    if FAILS:
        print(f"HASIL: {len(FAILS)} GAGAL ❌")
        for f in FAILS:
            print(" -", f)
        return 1
    print("HASIL: SEMUA LULUS ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
