"""Download a Riera volume PDF and derive its plain text.

Pablo Riera y Sans' *Diccionario geográfico, estadístico, histórico,
biográfico, postal, municipal, marítimo y eclesiástico de España y sus
posesiones de ultramar* (Barcelona, 1881-1887) ships as 12 per-volume
PDFs on the Biblioteca Digital de Castilla y León (BDCyL). Each PDF
already carries a searchable text layer (PDFlib+PDI 8.0.0); BDCyL does
not publish a standalone OCR / METS-ALTO file, so the PDF text layer is
our only OCR source.

For each volume we need:

- ``data/pdf/tomoNN.pdf`` — the source PDF as served by BDCyL. The
  endpoint returns 403 unless the request carries a browser User-Agent.
- ``data/txt/tomoNN.txt`` — column-aware plain text extracted with
  ``pdftotext -raw``. Pages are separated by form-feed (``\\f``), which
  is poppler's native page delimiter and what downstream indexers split
  on. ``-raw`` (rather than ``-layout``) is critical: ``-layout`` tries
  to preserve the original two-column visual layout side-by-side, which
  produces lines where the left and right columns are interleaved
  character by character.

Run:
  python scripts/fetch_volume.py <vol>     # e.g. 01
  python scripts/fetch_volume.py --all     # all 12 volumes
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"
PDF_DIR = DATA / "pdf"
TXT_DIR = DATA / "txt"

UA = "Mozilla/5.0 (research; nomenclators/riera)"

# Map Riera tomo ('01'-'12') → BDCyL path of the *PDF* artifact. These
# IDs come from the registry page at
# https://bibliotecadigital.jcyl.es/es/consulta/registro.cmd?id=24173 .
# The viewer paths (Tomo I = 10132262, etc.) are intentionally NOT used:
# they lead to the page-by-page facsimile viewer, not to a downloadable
# file.
VOL_TO_PDF_PATH: dict[str, str] = {
    "01": "10132396",   # Tomo I    (A — …)
    "02": "10132397",   # Tomo II
    "03": "10132398",   # Tomo III
    "04": "10132399",   # Tomo IV
    "05": "10132400",   # Tomo V
    "06": "10132348",   # Tomo VI
    "07": "10132349",   # Tomo VII
    "08": "10132350",   # Tomo VIII
    "09": "10132351",   # Tomo IX
    "10": "10132352",   # Tomo X
    "11": "10132353",   # Tomo XI
    "12": "10132354",   # Tomo XII
}

PDF_URL_TEMPLATE = (
    "https://bibliotecadigital.jcyl.es/es/catalogo_imagenes/grupo.do?path={path}"
)


def _download_pdf(vol: str) -> Path:
    path_id = VOL_TO_PDF_PATH[vol]
    url = PDF_URL_TEMPLATE.format(path=path_id)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    out = PDF_DIR / f"tomo{vol}.pdf"
    if out.exists() and out.stat().st_size > 0:
        print(f"  [skip] {out.relative_to(PROJECT)} already exists "
              f"({out.stat().st_size / 1024 / 1024:.1f} MB)")
        return out
    print(f"  [GET]  {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            ctype = r.headers.get("Content-Type", "")
            if "pdf" not in ctype.lower():
                raise SystemExit(
                    f"Expected a PDF response from BDCyL but got "
                    f"Content-Type={ctype!r}. The server may have changed "
                    f"the URL pattern; re-check the registry page."
                )
            tmp = out.with_suffix(".pdf.partial")
            with tmp.open("wb") as fh:
                shutil.copyfileobj(r, fh, length=1 << 20)
            tmp.rename(out)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} from BDCyL for tomo {vol}: {e.reason}")
    print(f"  [OK]   {out.relative_to(PROJECT)} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return out


def _extract_text(vol: str, pdf: Path) -> Path:
    TXT_DIR.mkdir(parents=True, exist_ok=True)
    out = TXT_DIR / f"tomo{vol}.txt"
    if out.exists() and out.stat().st_size > 0:
        print(f"  [skip] {out.relative_to(PROJECT)} already exists "
              f"({out.stat().st_size / 1024 / 1024:.2f} MB)")
        return out
    if not shutil.which("pdftotext"):
        raise SystemExit(
            "pdftotext not found in PATH. Install poppler "
            "(`brew install poppler` on macOS, `apt install poppler-utils` "
            "on Debian/Ubuntu)."
        )
    print(f"  [TXT]  pdftotext -raw {pdf.name} → {out.relative_to(PROJECT)}")
    # Don't `check=True`: BDCyL occasionally serves PDFs with corrupt
    # xref tables (observed on tomo06 path=10132348). pdftotext exits
    # non-zero but may still salvage partial text — and even when it
    # can't, we want the loop to move on to the next volume instead
    # of crashing the whole batch.
    result = subprocess.run(
        ["pdftotext", "-raw", "-enc", "UTF-8", str(pdf), str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        size = out.stat().st_size if out.exists() else 0
        print(f"  [WARN] pdftotext returncode={result.returncode}; "
              f"text size {size/1024/1024:.2f} MB (PDF may be corrupt — "
              f"try re-downloading: rm data/pdf/tomo{vol}.pdf and rerun)")
        if size == 0:
            return out
    print(f"  [OK]   {out.relative_to(PROJECT)} ({out.stat().st_size / 1024 / 1024:.2f} MB)")
    return out


def fetch(vol: str) -> None:
    print(f"=== Tomo {vol} (path={VOL_TO_PDF_PATH[vol]}) ===")
    pdf = _download_pdf(vol)
    _extract_text(vol, pdf)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(
            "Usage: python scripts/fetch_volume.py <vol>\n"
            "       python scripts/fetch_volume.py --all\n"
            "where <vol> is one of: " + ", ".join(sorted(VOL_TO_PDF_PATH))
        )
    arg = sys.argv[1]
    if arg == "--all":
        for vol in sorted(VOL_TO_PDF_PATH):
            fetch(vol)
        return
    vol = arg.zfill(2)
    if vol not in VOL_TO_PDF_PATH:
        known = ", ".join(sorted(VOL_TO_PDF_PATH))
        sys.exit(f"Volume {vol} unknown. Known volumes: {known}")
    fetch(vol)


if __name__ == "__main__":
    main()
