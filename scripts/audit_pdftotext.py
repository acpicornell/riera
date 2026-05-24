"""Cross-validate the PyMuPDF index against pdftotext output.

PyMuPDF + indent is our primary detector (preserves x0 coordinates,
which encode dictionary-style entry indents). But its text layer
extraction occasionally fragments emphasised lemmas into spaced
glyphs ('D E Y Á . ~ V .'), and the indent baseline algorithm fails
on layout-irregular pages.

This audit uses ``data/txt/tomoNN.txt`` (pdftotext -raw output, which
PyMuPDF doesn't read but pdftotext does, and which already collapses
the spaced-lemma artefact) as an independent witness. For each
lemma.— opener pdftotext sees with Balearic body markers, we check
whether our PyMuPDF index has the same (vol, page) entry. Discrepancies
are reported for either fixing the indexer or a fallback recovery
pass.

This is a 100% local script — no API, no Tesseract. Tesseract would
only be needed as a tertiary witness if BOTH PyMuPDF and pdftotext
silently dropped the same content (extremely rare for digitalised
PDFs with embedded text).

Run: ``python scripts/audit_pdftotext.py``
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT / "data" / "index"
TXT_DIR = PROJECT / "data" / "txt"

# Same separator class as index_volume.py — accept em-dash, hyphen and
# tilde (PDFlib occasionally encodes em-dash as ~ on Riera).
OPENER_RE = re.compile(
    r"^([A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ0-9'óòo\.\(\) \-]{2,40})"
    r"\.\s*[—\-~]+\s*"
    r"(V\.|L\.|C\.|B\.|Ald\.|Aid\.|Cas\.|Cot\.|Felig\.|Desp\.|"
    r"Cabo|Cala|Isla|Islote|Punta|Sierra|Monte|Puerto|Castillo|"
    r"Ayunt|Villa|Ciudad|Granja|Aldea|Lugar|Coto)"
)
BALEARIC = re.compile(
    r"\b(baleares|mallorca|menorca|ibiza|iviza|eivissa|formentera|cabrera"
    r"|mah[oó]n|cindadela|ciutadella|ciudadela"
    r"|palma\s+de\s+mallorca)\b",
    re.I,
)


def page_for_line(txt: str, line_no: int) -> int:
    """Form-feed-based PDF page number for a 1-based pdftotext line."""
    return txt[: sum(len(l) + 1 for l in txt.split("\n")[: line_no - 1])].count("\f") + 1


def main() -> None:
    # Index our existing PyMuPDF detections
    pymupdf_pages: dict[str, set[int]] = defaultdict(set)
    for f in sorted(INDEX_DIR.glob("tomo*.jsonl")):
        vol = f.stem.replace("tomo", "")
        for line in f.read_text().splitlines():
            e = json.loads(line)
            pymupdf_pages[vol].add(int(e["page"]))
    n_pymupdf = sum(len(v) for v in pymupdf_pages.values())
    print(f"PyMuPDF index: {n_pymupdf} (vol, page) tuples\n")

    # Scan pdftotext for openers with Balearic context
    candidates: list[dict] = []
    for tf in sorted(TXT_DIR.glob("tomo*.txt")):
        vol = tf.stem.replace("tomo", "")
        txt = tf.read_text()
        lines = txt.split("\n")
        # Precompute cumulative form-feeds per line
        page = 1
        line_pages = []
        for l in lines:
            line_pages.append(page)
            page += l.count("\f")
        for i, l in enumerate(lines, 1):
            m = OPENER_RE.match(l.lstrip())
            if not m:
                continue
            # Body: next 25 lines
            body = "\n".join(lines[i : i + 25])
            head_anchors = len(BALEARIC.findall(body[:1500]))
            if head_anchors < 1:
                continue
            pn = line_pages[i - 1]
            candidates.append({
                "vol": vol, "page": pn, "line": i,
                "lemma": m.group(1).strip(),
                "type": m.group(2),
                "head_anchors": head_anchors,
                "raw": l[:80],
            })

    print(f"pdftotext openers with ≥1 Balearic head anchor: {len(candidates)}\n")

    # Cross-check
    missing_in_pymupdf = []
    for c in candidates:
        if c["page"] not in pymupdf_pages[c["vol"]]:
            # Also accept ±1 page in case of small mismatch
            if (c["page"] - 1) not in pymupdf_pages[c["vol"]] \
                    and (c["page"] + 1) not in pymupdf_pages[c["vol"]]:
                missing_in_pymupdf.append(c)

    print(f"In pdftotext but NOT in PyMuPDF index: {len(missing_in_pymupdf)}\n")
    for c in missing_in_pymupdf:
        print(f"  tom{c['vol']} p{c['page']:>4} L{c['line']:>6}  "
              f"{c['lemma']:<30} {c['type']:<6}  anch={c['head_anchors']}")
        print(f"      raw: {c['raw']!r}")


if __name__ == "__main__":
    main()
