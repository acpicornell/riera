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
ENTRY_SEPARATOR_RE = re.compile(r"\.[\s'\"]*[—\-~]|\s—\s")

# When the PDF typesetter uses letter-spacing for emphasised lemmas
# (a 19th-century convention in dictionaries), PyMuPDF's text layer
# encodes that as literal spaces between each glyph. pdftotext quietly
# collapses these, PyMuPDF does not. The result on Riera is lines like
# 'D E Y Á . ~ V . con ayunt.' that fail the lemma regex. This
# normaliser detects ≥4 consecutive single-char+space tokens at the
# start of a line and collapses them — stops as soon as the regular
# narrative text begins (lowercase letter or multi-char token).
_SPACED_LEMMA_RE = re.compile(
    r"^((?:[A-ZÁÉÍÓÚÑÜ0-9\.\~\(\)']\s){3,}[A-ZÁÉÍÓÚÑÜ0-9\.\~\(\)'])(?=\s[a-z])"
)


def _collapse_spaced_lemma(text: str) -> str:
    m = _SPACED_LEMMA_RE.match(text)
    if not m:
        return text
    return m.group(1).replace(" ", "") + text[len(m.group(1)):]

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

INDENT_MIN = 0      # observed delta is usually 10-12pt; but some
                    # openers are typeset with no indent at all (e.g.
                    # the Mallorcan ALCUDIA at tom I p353 x=283.9 vs
                    # right baseline ~284). Setting the threshold to 0
                    # lets those through; the lemma + separator regex
                    # and NOISE/SECTION filters carry the load.
# Page Y crop: 60pt was too aggressive — SANTANY (Mallorca) at
# tom IX p713 sits at y=59.3, just under the cutoff. The 60pt floor
# was rejecting legitimate openers near the top of a column. Lowered
# to 30; the running-headers (DICCIONARIO / GEOGRÁFICO-ESTADÍSTICO /
# page numbers) are caught instead by the NOISE_TITLES_RE filter, so
# they don't reach the opener list anyway.
Y_MIN, Y_MAX = 30, 800

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
    distribution.

    Step 1: bin x0 values by 1pt and find the two most-populous bins
    that are ≥80pt apart. Those identify the two columns.

    Step 2 (refinement): within each column, the baseline is the
    SMALLEST x0 value with ≥3 occurrences — not the mode. The mode
    is unreliable on pages where indented openers / section headers
    outnumber the body lines (e.g. tom VI p586 where 14 indented
    SANTA-X openers cluster at x=308 but the actual right-column
    body baseline is at x=287, with only 10 lines). Indent magnitude
    is then computed against this true left edge."""
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
    left_anchor, right_anchor = sorted((primary, secondary))
    # Refine each baseline: smallest x0 in that column with ≥3 hits
    # and within 40pt of the anchor.
    def refine(anchor: int) -> float:
        candidates = sorted(
            (v, c) for v, c in counter.items()
            if c >= 3 and abs(v - anchor) <= 40
        )
        return float(candidates[0][0]) if candidates else float(anchor)
    return refine(left_anchor), refine(right_anchor)


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
                    text = _collapse_spaced_lemma(text)
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


def extract_body_pdftotext(opener: dict, vol: str, max_lines: int = 80) -> str:
    """Body extraction using pdftotext output instead of PyMuPDF.

    PyMuPDF's column-aware text reading (left col top-to-bottom, then
    right col top-to-bottom) silently gives WRONG content when an
    article's body straddles both columns interrupted by a statistical
    table (SOLLER, MANACOR, SAN JUAN BAUTISTA at tom IX p187 etc.).
    pdftotext -raw — already saved to data/txt/tomoNN.txt — handles
    this correctly: text flows in natural reading order across the
    columns. We just locate the opener line and take the next
    max_lines.

    Locating the opener is done by exact lemma + page-range proximity:
    we know from PyMuPDF which PDF page the opener is on; we scan the
    matching pdftotext form-feed segment for a line starting with the
    lemma. This is robust to OCR variations because we match on the
    lemma's NORMALISED prefix (1/I, l/I collapsed, spaces tolerated).
    """
    txt_path = PROJECT / "data" / "txt" / f"tomo{vol}.txt"
    if not txt_path.exists():
        return ""
    txt = txt_path.read_text()
    pages = txt.split("\f")
    target_page = opener["page"]
    if target_page > len(pages):
        return ""
    page_text = pages[target_page - 1]
    # Some openers fall in the last few lines of one page and continue
    # on the next; include the following page as fallback context.
    if target_page < len(pages):
        page_text += "\n" + pages[target_page]
    lines = page_text.split("\n")
    # Normalise lemma for matching: strip accents, OCR-confusion fix,
    # collapse multi-space to single space. We KEEP single spaces so that
    # 'CASA DE LA VILA' (Sant Josep, Eivissa) and 'CASA DE LA VILLA'
    # (Arrés, Lleida) are not conflated — the previous "drop all spaces"
    # rule turned both into the same 10-char prefix and caused
    # cross-article body bleed.
    import unicodedata as _ud
    def _norm(s: str) -> str:
        s = "".join(c for c in _ud.normalize("NFD", s)
                    if _ud.category(c) != "Mn").upper()
        s = re.sub(r"[1l](?=[A-Z])", "I", s)
        # Strip em-dashes / hyphens / tildes / periods — these vary
        # between PyMuPDF's captured lemma and pdftotext's rendering
        # of the same line ('CABRERA (Cuba)—Punta…' vs the index's
        # raw lemma 'CABRERA (Cuba)' truncated by the indexer's TITLE
        # regex). Removing them makes the prefix match robust.
        s = re.sub(r"[\.\-\—\~]+", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s
    lemma_n = _norm(opener["lemma"])
    # Recognises *another* opener in pdftotext. Three patterns:
    #   (a) administrative entries with the canonical separator —
    #       LEMMA.—V./L./C./… (place-type abbr) — most common form
    #   (b) administrative entries WITHOUT the period before the
    #       em-dash — OCR sometimes drops it (CAIMARL —L. agreg.)
    #   (c) geographic entries — CABO X / CALA X / ISLA X / PUERTO X / …
    #       (the lemma already names the type, body starts with prose)
    next_opener_re = re.compile(
        r"^(?:"
        r"[A-ZÁÉÍÓÚÑÜ]{2,}[A-ZÁÉÍÓÚÑÜ0-9'\.\(\) \-]{0,50}"
        r"[\.\,]?\s*[—\-~]+\s*"
        r"(?:V\.|L\.|C\.|B\.|Ald\.|Aid\.|Cas\.|Cot\.|Cor\.|Felig\.|Desp\.|"
        r"Ayunt|Villa|Ciudad|Granja|Aldea|Lugar|Coto)"
        r"|"
        r"(?:CABO|CALA|ISLA|ISLAS|ISLOTE|ISLOTES|ISLETA|ISLETAS|"
        r"PUNTA|PUERTO|SIERRA|MONTE|CASTILLO|BAHÍA|BAHIA|CORDILLERA|"
        r"R[ÍI]O|VALLE|LAGUNA|FUENTE|PROMONTORIO|PEÑ[ÓO]N)\s+[A-ZÁÉÍÓÚÑÜ]"
        r")"
    )
    # pdftotext sometimes wraps an opener across two lines:
    #   line N:   'CABRERA ó SAN FELITJ DE CABRERA.'
    #   line N+1: '—L. con ayunt., al que se hallan…'
    # The orphan continuation '—L. con ayunt.' on its own line signals
    # the wrapped opener — stop the body extraction BEFORE the
    # previous line, which holds the lemma.
    wrapped_cont_re = re.compile(
        r"^[—\-~]+\s*(V\.|L\.|C\.|B\.|Ald\.|Aid\.|Cas\.|Cot\.|Cor\.|"
        r"Felig\.|Desp\.|Castillo|Cabo|Cala|Isla|Punta|"
        r"Villa|Ciudad|Lugar|Aldea|Coto)"
    )
    # A line that is just an ALL CAPS phrase ending in '.' may be a
    # wrapped lemma. We accept it as opener-start if the NEXT line is
    # the continuation pattern above.
    bare_lemma_re = re.compile(r"^[A-ZÁÉÍÓÚÑÜ]{2,}[A-ZÁÉÍÓÚÑÜ0-9'óòo\.\(\) \-]{0,50}\.\s*$")

    # Collect ALL candidate body extracts for the lemma — a page can
    # legitimately host several homonyms (ALCUDIA appears 3× on tom I
    # p353: Alicante, Almería, Mallorca — only the third has Balearic
    # content). Then return the body with the most BALEARIC_TOKENS.
    candidates: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _norm(line)[: len(lemma_n)] != lemma_n:
            continue
        body_lines = []
        for j in range(i + 1, min(i + 1 + max_lines, len(lines))):
            l_stripped = lines[j].lstrip()
            if next_opener_re.match(l_stripped):
                break
            if wrapped_cont_re.match(l_stripped) and body_lines \
                    and bare_lemma_re.match(body_lines[-1].lstrip()):
                body_lines.pop()
                break
            body_lines.append(lines[j])
        body = "\n".join(body_lines)
        candidates.append((len(BALEARIC_TOKENS.findall(body)), body))
    if not candidates:
        return ""
    # Return the body with the highest Balearic-anchor count. If none
    # has any anchors, return the first candidate (preserves backward
    # behaviour for entries with no Balearic context at all).
    candidates.sort(key=lambda c: -c[0])
    return candidates[0][1]


def extract_body(pdf_path: Path,
                 opener_idx: int,
                 openers: list[dict],
                 max_lines: int = 60) -> str:
    """PyMuPDF column-aware body extraction (legacy fallback).

    Used only if pdftotext extraction returns an empty body. Originally
    the primary body extractor but suffered column-bleed on articles
    that span both columns interrupted by tables — see
    extract_body_pdftotext for the replacement."""
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


def is_balearic(body: str, ngib_balearic: bool = False,
                 lemma: str = "") -> tuple[bool, int, int]:
    """Decide if an article is Balearic.

    Body-anchor signal: count unambiguous Balearic tokens in the first
    40 lines of the body. Short entries need ≥1, long entries need ≥2
    to filter out peninsular cities that mention Baleares once in an
    audiencia-territorial roster.

    `ngib_balearic` is an OUT-OF-BAND signal: True when the entry's
    title fuzzy-matches a Balearic NGIB toponym at ≥95. That match is
    enough on its own to qualify the article as Balearic, irrespective
    of body anchors. This rescues entries like SOLLER where the body
    is interrupted by a statistical table that pushes most Balearic
    tokens out of the head window."""
    head = "\n".join(body.split("\n")[:40])
    total = len(BALEARIC_TOKENS.findall(body))
    head_hits = len(BALEARIC_TOKENS.findall(head))
    body_lines = body.count("\n") + 1
    # SECOND fallback — the lemma itself names one of the four major
    # islands or capital cities. 'ISLA DE MALLORCA' describes
    # geography ('lies east of Ibiza, with capes Pinar and Formentor…')
    # without repeating 'Mallorca' often, so the head-anchor count is
    # low (often only 1). 'cabrera' is INTENTIONALLY excluded — too
    # many peninsular entries (CASTRILLO DE CABRERA, Sierra de
    # Cabrera in León) carry it in their lemma and would smuggle in.
    LEMMA_TOKENS = re.compile(
        r"\b(baleares|bale[aà]ric|bale[aà]riques"
        r"|mallorca|menorca|ibiza|iviza|eivissa|formentera"
        r"|mah[oó]n|cindadela|ciutadella|ciudadela)\b",
        re.I,
    )
    lemma_has_token = bool(lemma and LEMMA_TOKENS.search(lemma))
    if lemma_has_token and head_hits >= 1:
        return True, total, head_hits
    # NGIB-as-fallback: title fuzzy-matches a Balearic settlement at
    # ≥95. This rescues entries with low body-anchor counts due to
    # statistical-table interruption (SOLLER, MANACOR). But we must
    # still require at least 1 HEAD anchor — without that guard, three
    # peninsular SANTA EULALIA entries at tom IX p548 (Lleida, Huesca,
    # Lugo) all match NGIB's "Santa Eulalia" and would smuggle in.
    if ngib_balearic and head_hits >= 1:
        return True, total, head_hits
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
        # Prefer pdftotext body (linear reading order, no column-bleed).
        body = extract_body_pdftotext(op, vol)
        if not body:
            # Fallback to PyMuPDF column-aware extraction.
            body = extract_body(pdf_path, i, openers)
        # NGIB title check runs FIRST so we can pass its result into
        # is_balearic as an alternative signal.
        fm = fuzzy_match(op["lemma"], choices, norm_list)
        ngib = None
        ngib_settlement_match = False
        if fm:
            sp, muni, island, ltype = choices[fm[0]][0]
            ngib = {"key": fm[0], "score": fm[1], "spelling": sp,
                    "municipality": muni, "island": island, "type": ltype}
            # Strong match: ≥95 score against a settlement (Municipi,
            # Capital de municipi, Vila, Variant històrica) — the kind
            # of NGIB row Riera would unambiguously be referring to.
            if fm[1] >= 95 and ltype in (
                "Municipi", "Capital de municipi", "Capital de Municipi",
                "Nucli de població capital de municipi", "Vila",
                "Variant històrica", "Entitat de Població",
                "Altre nucli de població, llogaret",
            ):
                ngib_settlement_match = True
        ok, total, head = is_balearic(body,
                                       ngib_balearic=ngib_settlement_match,
                                       lemma=op["lemma"])
        if not ok:
            continue
        balearic.append({
            "vol": vol, "page": op["page"], "lemma": op["lemma"],
            "raw": op["raw"][:80],
            "body_lines": body.count("\n") + 1,
            "anchors_total": total, "anchors_head": head,
            "ngib": ngib,
        })
    # Deduplicate by (page, normalised lemma) — keep the entry with
    # the highest anchors_head (most Balearic context).
    import unicodedata as _ud
    def _key(e):
        s = "".join(c for c in _ud.normalize("NFD", e["lemma"])
                    if _ud.category(c) != "Mn").upper()
        s = re.sub(r"\s+", " ", s).strip()
        return (e["page"], s)
    seen: dict = {}
    for e in balearic:
        k = _key(e)
        if k not in seen or e["anchors_head"] > seen[k]["anchors_head"]:
            seen[k] = e
    balearic = list(seen.values())
    balearic.sort(key=lambda e: (e["page"], e["lemma"]))
    doc = pymupdf.open(str(pdf_path))
    body_start = openers[0]["page"] if openers else 1
    body_end = openers[-1]["page"] if openers else doc.page_count
    return {"vol": vol, "pdf_pages": doc.page_count,
            "body_pages": f"{body_start}-{body_end}",
            "articles": len(openers), "balearic": balearic}


# ---------------------------------------------------------------------------
# Optional second-pass audit using local sentence embeddings.
#
# After the regex+fuzzy+NGIB pipeline builds the index, this pass embeds
# each entry's body + each pdftotext-only rejected candidate's body
# against two archetypal reference queries (Balearic vs León). Entries
# whose Léon-similarity exceeds Balearic-similarity by ≥ 0.02 are
# confirmed peninsular; entries with the opposite margin are confirmed
# Balearic; entries inside the ±0.02 band are flagged for human review.
#
# It only runs when --audit-with-embeddings is passed. Requires
# sentence-transformers (~1 GB model download on first use). All-local,
# no API calls.
# ---------------------------------------------------------------------------

# Archetypal Balearic and peninsular reference descriptions. Three
# archetypes per side cover the structural variety of Riera's
# entries: administrative villas, maritime capes, and island-level
# supramunicipal articles. We take MAX similarity over each side and
# the margin = max_BAL - max_PENINSULAR.
_Q_BAL = [
    # Administrative villa
    ("villa_BAL",
     "Villa con ayuntamiento en la provincia de las Baleares, isla de "
     "Mallorca, diócesis de Palma. Audiencia territorial de Mallorca. "
     "Capitanía general de las Baleares, gobierno militar de Palma. "
     "Departamento marítimo de Cartagena, provincia marítima de Mallorca."),
    # Maritime cape
    ("cape_BAL",
     "Cabo situado en la costa de la isla de Mallorca, provincia y "
     "distrito marítimo de Mallorca, departamento de Cartagena. Al pie "
     "se alza un faro. Cala de buen fondeadero."),
    # Island-level supramunicipal
    ("island_BAL",
     "Isla del archipiélago de las Baleares en el Mediterráneo. Mayor "
     "extensión por sus cabos y puntas. Bahías y calas, puerto y "
     "fondeaderos. División administrativa: partidos judiciales, "
     "ayuntamientos, diócesis y arciprestazgos."),
]
_Q_PENINSULAR = [
    # León village (Cabrera Baja arciprestat)
    ("villa_LEON",
     "Lugar agregado al ayuntamiento en la provincia de León, diócesis "
     "de Astorga, arciprestazgo de Cabrera Baja. Audiencia territorial "
     "de Valladolid. Capitanía general de Castilla la Vieja, gobierno "
     "militar de León."),
    # Peninsular cape (Galicia / Cataluña / Cádiz)
    ("cape_PENINSULAR",
     "Cabo en la costa de la provincia de Coruña, dist. marítimo de "
     "Corcubión, departamento del Ferrol. Punta saliente al mar "
     "Cantábrico. Faro con luz giratoria."),
    # Cuba / Filipinas colonial entry
    ("colonial",
     "Caserío agregado al ayuntamiento, en la provincia marítima de "
     "Santiago de Cuba (ó en las islas Filipinas). Pueblo con gobernador "
     "y casa parroquial bajo la advocación de su patrón."),
]
_AUDIT_MODEL = (
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
)
_AUDIT_MARGIN = 0.02


def run_embeddings_audit(indexed_entries: list[dict]) -> None:
    """Print a per-entry semantic-similarity audit of the index plus the
    pdftotext-only rejected candidates."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("\n[audit] sentence-transformers not installed. "
              "Run `pip install sentence-transformers` first.")
        return
    import numpy as np
    print(f"\n[audit] Loading {_AUDIT_MODEL} (first run downloads ~1 GB)…")
    try:
        model = SentenceTransformer(_AUDIT_MODEL, device="mps")
    except Exception:
        model = SentenceTransformer(_AUDIT_MODEL)
    bal_labels = [lbl for lbl, _ in _Q_BAL]
    pen_labels = [lbl for lbl, _ in _Q_PENINSULAR]
    bal_texts = [t for _, t in _Q_BAL]
    pen_texts = [t for _, t in _Q_PENINSULAR]
    q_emb = model.encode(bal_texts + pen_texts, normalize_embeddings=True)
    q_bal_embs = q_emb[: len(bal_texts)]
    q_pen_embs = q_emb[len(bal_texts):]

    # Gather indexed entries with their bodies.
    rows: list[dict] = []
    for e in indexed_entries:
        body = extract_body_pdftotext(
            {"page": int(e["page"]), "lemma": e["lemma"]},
            e["vol"],
            max_lines=30,
        )
        rows.append({**e, "_body": body, "_kind": "indexed"})

    # Also gather pdftotext-only rejected openers (the same candidates
    # the audit_pdftotext.py script reports) — to look for false
    # negatives.
    rejected = _audit_pdftotext_candidates(indexed_entries)
    for r in rejected:
        rows.append({**r, "_kind": "rejected"})

    if not rows:
        print("[audit] no candidates to evaluate.")
        return

    bodies = [r["_body"] for r in rows]
    embs = model.encode(bodies, normalize_embeddings=True,
                        batch_size=32, show_progress_bar=False)
    # MAX over each side's archetypes — each entry's best Balearic
    # template-match is compared against its best peninsular match.
    sim_bal_each = embs @ q_bal_embs.T  # (N, |bal_q|)
    sim_pen_each = embs @ q_pen_embs.T  # (N, |pen_q|)
    sim_bal = sim_bal_each.max(axis=1)
    sim_leon = sim_pen_each.max(axis=1)  # keep var name for back-compat
    margin = sim_bal - sim_leon
    # Per-entry best matching archetype, for diagnostic display
    best_bal = sim_bal_each.argmax(axis=1)
    best_pen = sim_pen_each.argmax(axis=1)

    ambig_indexed = []
    ambig_rejected = []
    n_indexed = n_rejected = 0
    for row, m, sb, sl, bb, bp in zip(rows, margin, sim_bal, sim_leon,
                                       best_bal, best_pen):
        row["_best_bal"] = bal_labels[bb]
        row["_best_pen"] = pen_labels[bp]
        if row["_kind"] == "indexed":
            n_indexed += 1
            if m < _AUDIT_MARGIN:
                ambig_indexed.append((row, sb, sl, m))
        else:
            n_rejected += 1
            if m > -_AUDIT_MARGIN:
                ambig_rejected.append((row, sb, sl, m))

    print(f"\n[audit] Embeddings audit over {n_indexed} indexed "
          f"+ {n_rejected} rejected candidates.")

    if ambig_indexed:
        print(f"\n[audit] {len(ambig_indexed)} INDEXED entries with "
              f"low or negative margin (potential false positives):")
        for row, sb, sl, m in sorted(ambig_indexed, key=lambda r: r[3]):
            print(f"  tom{row['vol']} p{row['page']:>4}  "
                  f"{row['lemma'][:30]:<30}  "
                  f"BAL/{row['_best_bal']:<10}={sb:.3f}  "
                  f"PEN/{row['_best_pen']:<15}={sl:.3f}  Δ={m:+.3f}")
    else:
        print("[audit] All indexed entries have clear Balearic margin "
              "(≥ +0.02). No false positives suspected.")

    if ambig_rejected:
        print(f"\n[audit] {len(ambig_rejected)} REJECTED candidates with "
              f"high Balearic margin (potential false negatives):")
        for row, sb, sl, m in sorted(ambig_rejected, key=lambda r: -r[3]):
            print(f"  tom{row['vol']} p{row['page']:>4}  "
                  f"{row['lemma'][:30]:<30}  "
                  f"BAL/{row['_best_bal']:<10}={sb:.3f}  "
                  f"PEN/{row['_best_pen']:<15}={sl:.3f}  Δ={m:+.3f}")
    else:
        print("[audit] All rejected candidates have clear peninsular "
              "margin (≤ -0.02). No false negatives suspected.")


def _audit_pdftotext_candidates(indexed_entries: list[dict]) -> list[dict]:
    """Scan pdftotext output of every tom for openers that the regex+
    NGIB pipeline rejected (or never noticed). Returns candidates with
    their body context, for the embeddings audit to evaluate."""
    indexed_keys = {(e["vol"], int(e["page"])) for e in indexed_entries}
    OPENER_RE = re.compile(
        r"^([A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ0-9'óòo\.\(\) \-]{2,40})"
        r"\.\s*[—\-~]+\s*"
        r"(V\.|L\.|C\.|B\.|Ald\.|Aid\.|Cas\.|Cot\.|Felig\.|Desp\.|"
        r"Cabo|Cala|Isla|Islote|Punta|Sierra|Monte|Puerto|Castillo|"
        r"Ayunt|Villa|Ciudad|Granja|Aldea|Lugar|Coto)"
    )
    rejected: list[dict] = []
    txt_dir = PROJECT / "data" / "txt"
    for tf in sorted(txt_dir.glob("tomo*.txt")):
        vol = tf.stem.replace("tomo", "")
        txt = tf.read_text()
        lines = txt.split("\n")
        page = 1
        for i, line in enumerate(lines):
            if "\f" in line:
                # form-feed at end of line — page increments AFTER recording
                page += line.count("\f")
                continue
            m = OPENER_RE.match(line.lstrip())
            if not m:
                continue
            # Body for anchor check: next 25 lines
            body = "\n".join(lines[i + 1 : i + 26])
            if not BALEARIC_TOKENS.search(body[:1500]):
                continue
            # Only flag if not already indexed (allow ±1 page tolerance)
            if any((vol, page + d) in indexed_keys for d in (-1, 0, 1)):
                continue
            rejected.append({
                "vol": vol, "page": page, "lemma": m.group(1).strip(),
                "_body": body,
            })
    return rejected


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("vol", nargs="?",
                    help="single volume number (e.g. 01). Omit when "
                         "passing --all.")
    ap.add_argument("--all", action="store_true",
                    help="process every available volume (01-12).")
    ap.add_argument("--audit-with-embeddings", action="store_true",
                    help="Run a sentence-embedding sanity check over the "
                         "index after building it. Confirms each entry's "
                         "Balearic margin vs an archetypal peninsular "
                         "reference, and flags rejected candidates that "
                         "look semantically Balearic. Requires "
                         "sentence-transformers (~1 GB model on first use).")
    args = ap.parse_args()

    if not args.all and not args.vol:
        ap.error("either VOL or --all is required")
    vols = [f"{n:02d}" for n in range(1, 13)] if args.all else [args.vol.zfill(2)]
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    grand_t = grand_b = 0
    all_indexed: list[dict] = []
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
        all_indexed.extend(r["balearic"])
        grand_t += r["articles"]
        grand_b += len(r["balearic"])
        print(f"  tomo {vol}: pages={r['pdf_pages']:>4}  "
              f"body={r['body_pages']:>9}  "
              f"articles={r['articles']:>5}  "
              f"balearic={len(r['balearic']):>3}  → {out.relative_to(PROJECT)}")
    if len(vols) > 1:
        print(f"\nTotal across {len(vols)} volumes: "
              f"articles={grand_t}, balearic={grand_b}")

    if args.audit_with_embeddings:
        run_embeddings_audit(all_indexed)


if __name__ == "__main__":
    main()
