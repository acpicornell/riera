"""Index a Riera volume by INDENT signal (PyMuPDF) and classify Balearic ones.

How Riera's print layout encodes article boundaries:

  Each entry begins with an INDENTED line (~10-12 pt to the right of the
  body-text left margin). The lemma is set in ALL CAPS, followed by
  `.—` and the place-type abbreviation (V., L., C., Cas., …). Section
  headers INSIDE an entry (Organización judicial, Servicio público …)
  share the same indent but begin with TitleCase, not ALL CAPS — so an
  uppercase-test plus a small exclusion list separates the two cleanly.

  This is a fundamentally more reliable signal than text-pattern regex
  because (a) `pdftotext -raw` collapses the indent and we lose it, but
  PyMuPDF preserves the per-line X coordinate; (b) the indent is a
  typographic CONVENTION of the print, not a property of the text — it
  catches damaged-OCR titles, short cross-references, and entries
  whose body diverges from the standard "Org. jud." template.

  Per-page two-column handling: each column has its own baseline X,
  recovered as the mode of x0 values within that column's half of the
  page width.

Balearic classification is unchanged from the previous detector:
unambiguous Balearic tokens (`Mallorca`, `Menorca`, `Ibiza`, `Eivissa`,
`Formentera`, `Cabrera`, `Baleares`, `Mahón`, `Ciudadela`, `Palma de
Mallorca`) in the entry's HEAD (first 40 lines of body). Short entries
need 1 hit; long entries need ≥2 to filter peninsular cities that
mention Baleares once in an administrative-roster line.

Run:
  python scripts/index_volume.py <vol|--all>
Output: data/index/tomoNN.jsonl
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Optional

import pymupdf

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"
PDF_DIR = DATA / "pdf"
INDEX_DIR = DATA / "index"
GAZETTEER = Path("/Users/acpicornell/nomenclators/minano/data/gazetteer.parquet")

# Section headers inside an entry — indented like an opener, but they
# begin with TitleCase, not ALL CAPS. The exclusion is built positive
# (we list the known opener words) to avoid catching real entries
# whose lemma happens to share a prefix.
SECTION_RE = re.compile(
    r"^(Organizaci[oó]n|Servicio\s+p[uú]blic|Obras\s+p[uú]blic|"
    r"Instrucci[oó]n|Poblaci[oó]n|Artes|Situaci[oó]n|Geograf[ií]a|"
    r"Hist[oó]|Org\.|Ins\.|Pob\.|Art\.|S\.\s+p[uú]b|Ob\.\s+p[uú]b|"
    r"Servicio\s+y|Fer\.\s+y|Riqueza|Producciones?|Estad[ií]stic|"
    r"Ferr?[io]carril)"
)
# Article opener: lemma is ≥2 consecutive caps at the start of the line.
# The opener line itself may continue with lowercase (Riera writes the
# place-type abbr V./L./C. after the dash, which is uppercase + dot).
ENTRY_LEMMA_RE = re.compile(r"^[A-ZÁÉÍÓÚÑÜ]{2,}")
# Real dictionary entries ALWAYS carry a dot-em-dash (or dot-hyphen)
# separator between the lemma and the body within the first 70 chars.
# Statistical-table headings inside long entries (BALEARES, CIUDADELA,
# BARCELONA province articles) are indented and all-caps but never
# carry this separator. This single filter removes ~95% of the false
# positives (EUROPA, EXPORTACION, ENTRADA Y SALIDA DE BUQUES…).
ENTRY_SEPARATOR_RE = re.compile(r"\.[\s'\"]*[—\-]|\s—\s")

# Centred page-titles / running heads / volume markers — never an entry.
NOISE_TITLES_RE = re.compile(
    r"^(DICCIONARIO|GEOGR[ÁA]FICO|GEOÓGR|ESTAD[ÍI]STICO|HIST[ÓO]RICO|"
    r"BIOGR[ÁA]FICO|TOMO|FIN\s+DEL|PLANTILLA|CONTINUACION|CUATRO|"
    r"PUBLICADO|INTRODUCCION|EXPLICACION|CUBA|PUERTO\s+RICO|"
    r"PROVINCIA\s+DE|MAPA\s+DE|PROVINCIAS?\s+|GOBIERNO\s+DE\s+|"
    r"PROVINCI|TIENE|TOTAL)"
)

# Unambiguously-Balearic body tokens. NOT a regex of place-name lists —
# just the seven Balearic identifiers, the two capitals (in any of the
# orthographic forms Riera uses), and `Palma de Mallorca` (since bare
# `Palma` can be Palma del Río in Córdoba).
BALEARIC_TOKENS = re.compile(
    r"\b(baleares|bale[aà]ric|bale[aà]riques"
    r"|mallorca|menorca|ibiza|iviza|eivissa|formentera|cabrera"
    r"|mah[oó]n|cindadela|ciutadella|ciudadela"
    r"|palma\s+de\s+mallorca)\b",
    re.I,
)

INDENT_MIN = 5      # points — observed delta is ~10-12pt
Y_MIN, Y_MAX = 60, 780  # crop running headers + page footers

# Place-type abbreviations that confirm an opener is a real dictionary
# entry (vs. a centred TitleCase header that survived the noise filter).
PLACE_TYPE_RE = re.compile(
    r"\b(V\.|L\.|C\.|B\.|Ald\.|Aid\.|Cas\.|Cot\.|Cor\.|Felig\.|Desp\.|"
    r"Castillo|Cabo|Cala|Puerto|Sierra|Monte|Punta|Isla|Islote|Villa|"
    r"Ciudad|Granja|Aldea|Cuart[oó]n|Lugar|Coto|Pueblo|Barrio|Caser[ií]o|"
    r"Ayuntamiento|Anteiglesia|Departamento)"
)


def find_body_page_range(openers_all: list[dict],
                          min_per_page: int = 2) -> tuple[int, int]:
    """Return (first_page, last_page) where the dictionary body lives.

    Front matter (prologue, TOC, explanation of abbreviations) is
    detected by absence of indented opener LINES that match the
    place-type pattern. Same logic for appendices (Cuba/Puerto Rico
    listings, plates, errata) at the tail.

    The body is the contiguous run of pages where at least
    `min_per_page` indented openers carry a place-type marker."""
    per_page: dict[int, int] = {}
    for op in openers_all:
        if PLACE_TYPE_RE.search(op["raw"]):
            per_page[op["page"]] = per_page.get(op["page"], 0) + 1
    if not per_page:
        return (1, 1)
    pages_with = sorted(p for p, n in per_page.items() if n >= min_per_page)
    if not pages_with:
        pages_with = sorted(per_page.keys())
    return (pages_with[0], pages_with[-1])


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalize_title(s: str) -> str:
    s = strip_accents(s).upper().replace("-", " ").replace("—", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+O\s+.*$", "", s)
    return s


def clean_title(t: str) -> str:
    """Strip junk, fix 1/l→I inside caps run, collapse spaces."""
    # The lemma is the leading caps run, stop at the first '.' or '—'
    m = re.match(r"^([A-ZÁÉÍÓÚÑÜ0-9'óòo \-,\(\)]{2,40})[\.\—]", t)
    if m:
        t = m.group(1)
    t = t.strip(" '\"’.,;:•·-")
    t = re.sub(r"(?<=[A-ZÁÉÍÓÚÑÜ])[1l](?=[A-ZÁÉÍÓÚÑÜ]|$|\b)", "I", t)
    t = re.sub(r"\.+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _find_column_baselines(xs: list[float]) -> tuple[float, float]:
    """Two-column body-text baselines, recovered from the bimodal x0
    distribution. The naive page-midpoint split fails on Riera because
    the right column's left edge (x ≈ 267-270) often sits LEFT of the
    page midpoint (x = 273), so right-column text contaminates the
    left bucket and skews the mode.

    Algorithm: bin x0 by 1pt and take the two most populous bins that
    are at least 80pt apart. Those are the two body baselines (left
    and right column start). If there's only one cluster (single-col
    intro or full-page table) return (mode, mode)."""
    if not xs:
        return (0.0, 0.0)
    counter = Counter(round(x) for x in xs)
    sorted_bins = counter.most_common()
    primary = sorted_bins[0][0]
    secondary = None
    for v, _ in sorted_bins[1:]:
        if abs(v - primary) >= 80:
            secondary = v
            break
    if secondary is None:
        return (float(primary), float(primary))
    left, right = sorted((primary, secondary))
    return (float(left), float(right))


def extract_indent_openers(pdf_path: Path) -> list[dict]:
    """Return [{page, x0, y0, raw_text, lemma}] for every detected opener,
    in reading order. The list is sorted by (page, y0_within_column).
    Front matter and trailing appendices are cropped automatically."""
    doc = pymupdf.open(str(pdf_path))
    out = []
    for pn in range(doc.page_count):
        page = doc[pn]
        d = page.get_text("dict")
        lines = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                if not ln["spans"]:
                    continue
                x0 = ln["spans"][0]["bbox"][0]
                y0 = ln["spans"][0]["bbox"][1]
                if y0 < Y_MIN or y0 > Y_MAX:
                    continue
                text = "".join(s["text"] for s in ln["spans"]).rstrip()
                if text:
                    lines.append((x0, y0, text))
        if not lines:
            continue
        # Two-column baselines, recovered from the bimodal x0 dist.
        bl, br = _find_column_baselines([x for x, _, _ in lines])
        # The column boundary is the midpoint between the two baselines
        # (works even when the right column starts to the left of the
        # page geometric centre).
        col_split = (bl + br) / 2 if br > bl else page.rect.width / 2
        for x0, y0, text in lines:
            if x0 < col_split:
                base, col = bl, "L"
            else:
                base, col = br, "R"
            if base is None:
                continue
            if x0 < base + INDENT_MIN:
                continue
            if SECTION_RE.match(text):
                continue
            if NOISE_TITLES_RE.match(text):
                continue
            if not ENTRY_LEMMA_RE.match(text):
                continue
            if len(text) < 5:
                continue
            if not ENTRY_SEPARATOR_RE.search(text[:70]):
                continue
            out.append({
                "page": pn + 1,
                "column": col,
                "x0": x0, "y0": y0,
                "raw": text,
                "lemma": clean_title(text),
            })
    # Sort by page, then within page by (column, y0) — left column flows
    # top to bottom first, then right column.
    out.sort(key=lambda o: (o["page"], o["column"], o["y0"]))
    # Auto-crop front matter and trailing appendices.
    first_page, last_page = find_body_page_range(out)
    return [op for op in out if first_page <= op["page"] <= last_page]


def extract_body(pdf_path: Path,
                 opener_idx: int,
                 openers: list[dict],
                 max_lines: int = 60) -> str:
    """Pull text lines from the page(s) starting RIGHT AFTER opener i,
    up to the next opener or `max_lines`, whichever comes first. The
    opener line itself is excluded — otherwise a peninsular entry
    whose lemma contains a Balearic toponym (CASTRILLO DE CABRERA,
    PUEBLA DE MENORCA) would trigger the Balearic body filter on its
    own title."""
    doc = pymupdf.open(str(pdf_path))
    cur = openers[opener_idx]
    nxt = openers[opener_idx + 1] if opener_idx + 1 < len(openers) else None
    out: list[str] = []
    pn = cur["page"] - 1
    after_cur = True
    while pn < doc.page_count and len(out) < max_lines:
        page = doc[pn]
        d = page.get_text("dict")
        page_lines = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                if not ln["spans"]:
                    continue
                x0 = ln["spans"][0]["bbox"][0]
                y0 = ln["spans"][0]["bbox"][1]
                if y0 < Y_MIN or y0 > Y_MAX:
                    continue
                text = "".join(s["text"] for s in ln["spans"]).rstrip()
                if text:
                    page_lines.append((x0, y0, text))
        mid = page.rect.width / 2
        # Reading order: left column first, then right column, each top→bottom
        page_lines.sort(key=lambda l: ("L" if l[0] < mid else "R", l[1]))
        for x0, y0, text in page_lines:
            col = "L" if x0 < mid else "R"
            # Skip lines BEFORE (and including) the current opener
            if pn + 1 == cur["page"] and (col, y0) <= (cur["column"], cur["y0"]):
                continue
            # Stop at the next opener
            if nxt and pn + 1 == nxt["page"] and (col, y0) >= (nxt["column"], nxt["y0"]):
                return "\n".join(out)
            out.append(text)
            if len(out) >= max_lines:
                return "\n".join(out)
        pn += 1
        if nxt and pn + 1 > nxt["page"]:
            break
    return "\n".join(out)


def is_balearic(body: str) -> tuple[bool, int, int]:
    head = "\n".join(body.split("\n")[:40])
    total = len(BALEARIC_TOKENS.findall(body))
    head_hits = len(BALEARIC_TOKENS.findall(head))
    body_lines = body.count("\n") + 1
    if body_lines < 25:
        return head_hits >= 1, total, head_hits
    return head_hits >= 2, total, head_hits


def load_gazetteer():
    import duckdb
    con = duckdb.connect(":memory:")
    rows = con.execute(f"""
        SELECT normalized, spelling, municipality, island, local_type
        FROM read_parquet('{GAZETTEER}')
        WHERE island IN ('Mallorca','Menorca','Eivissa','Formentera','Cabrera')
    """).fetchall()
    choices: dict[str, list[tuple]] = {}
    for r in rows:
        choices.setdefault(r[0], []).append(r[1:])
    return choices


def fuzzy_match(title: str, choices, norm_list):
    from rapidfuzz import process, fuzz
    norm = normalize_title(title)
    if len(norm) < 3:
        return None
    r = process.extractOne(norm, norm_list, scorer=fuzz.ratio, score_cutoff=85)
    if r is None:
        return None
    match, score, _ = r
    if len(match) < 0.7 * len(norm) or len(norm) < 0.7 * len(match):
        return None
    return match, int(score)


def index_volume(vol: str) -> dict:
    pdf_path = PDF_DIR / f"tomo{vol}.pdf"
    if not pdf_path.exists():
        raise SystemExit(f"{pdf_path} not found")
    openers = extract_indent_openers(pdf_path)
    choices = load_gazetteer()
    norm_list = list(choices.keys())
    balearic = []
    for i, op in enumerate(openers):
        body = extract_body(pdf_path, i, openers)
        ok, total, head = is_balearic(body)
        if not ok:
            continue
        fm = fuzzy_match(op["lemma"], choices, norm_list)
        ngib = None
        if fm:
            sp, muni, island, ltype = choices[fm[0]][0]
            ngib = {"key": fm[0], "score": fm[1], "spelling": sp,
                    "municipality": muni, "island": island, "type": ltype}
        balearic.append({
            "vol": vol, "page": op["page"], "lemma": op["lemma"],
            "raw": op["raw"][:80],
            "body_lines": body.count("\n") + 1,
            "anchors_total": total, "anchors_head": head,
            "ngib": ngib,
        })
    doc = pymupdf.open(str(pdf_path))
    body_start = openers[0]["page"] if openers else 1
    body_end = openers[-1]["page"] if openers else doc.page_count
    return {"vol": vol, "pdf_pages": doc.page_count,
            "body_pages": f"{body_start}-{body_end}",
            "articles": len(openers), "balearic": balearic}


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python scripts/index_volume.py <vol|--all>")
    arg = sys.argv[1]
    vols = [f"{n:02d}" for n in range(1, 13)] if arg == "--all" else [arg.zfill(2)]
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    grand_t = grand_b = 0
    for vol in vols:
        try:
            r = index_volume(vol)
        except SystemExit as e:
            print(f"[skip] tomo {vol}: {e}")
            continue
        out = INDEX_DIR / f"tomo{vol}.jsonl"
        with out.open("w") as fh:
            for art in r["balearic"]:
                fh.write(json.dumps(art, ensure_ascii=False) + "\n")
        grand_t += r["articles"]
        grand_b += len(r["balearic"])
        print(f"  tomo {vol}: pages={r['pdf_pages']:>4}  "
              f"body={r['body_pages']:>9}  "
              f"articles={r['articles']:>5}  "
              f"balearic={len(r['balearic']):>3}  → {out.relative_to(PROJECT)}")
    if len(vols) > 1:
        print(f"\nTotal across {len(vols)} volumes: "
              f"articles={grand_t}, balearic={grand_b}")


if __name__ == "__main__":
    main()
