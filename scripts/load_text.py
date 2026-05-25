"""Load Phase 3 JSON extracts into the project DuckDB.

Reads every ``data/text/page_<vol>_<page>.json`` produced by
``extract_text.py`` and inserts one row per entry into the
``text_entries`` table defined in ``db/schema.sql``.

Each run fully replaces the table — the JSON files are the source of
truth; the DB is a derived index. Re-run after every new batch of
extractions.

Run: ``python scripts/load_text.py``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

PROJECT = Path(__file__).resolve().parent.parent
DB = PROJECT / "db" / "riera.duckdb"
SCHEMA = PROJECT / "db" / "schema.sql"
TEXT_DIR = PROJECT / "data" / "text"


def main() -> None:
    if not SCHEMA.exists():
        sys.exit(f"Schema not found at {SCHEMA}.")
    if not TEXT_DIR.exists():
        sys.exit(f"No text output dir at {TEXT_DIR}.")

    files = sorted(p for p in TEXT_DIR.glob("page_*.json") if p.is_file())
    if not files:
        sys.exit(f"No page_*.json files under {TEXT_DIR}.")
    print(f"Reading {len(files)} page extracts...")

    payload: list[tuple] = []
    for path in files:
        page = json.loads(path.read_text())
        vol = page["vol"]
        leaf = int(page["page"])      # Riera schema column 'leaf' = PDF page index
        page_printed = None             # not extracted yet
        model = page.get("model")
        window = page.get("window_size")  # not used in Riera; PyMuPDF handles columns
        source_file = str(path.relative_to(PROJECT))
        for e in page.get("entries", []):
            stats = e.get("stats")
            xrefs = e.get("cross_references") or []
            payload.append((
                vol, leaf, page_printed,
                e.get("title") or "",
                e.get("place_type"),
                e.get("island"),
                e.get("municipality"),
                e.get("org_judicial"),
                e.get("org_civil"),
                e.get("org_militar"),
                e.get("org_economica"),
                e.get("org_eclesiastica"),
                e.get("servicio_publico"),
                e.get("obras_publicas"),
                e.get("instruccion_publica"),
                e.get("poblacion"),
                e.get("industria"),
                e.get("geografia"),
                e.get("historia"),
                e.get("description"),
                e.get("ocr_note"),
                json.dumps(stats, ensure_ascii=False) if stats else None,
                xrefs,
                e.get("confidence"),
                window,
                model,
                source_file,
            ))

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute(SCHEMA.read_text())
    con.execute("BEGIN")
    con.execute("DELETE FROM text_entries")
    con.executemany(
        """INSERT INTO text_entries
           (vol, leaf, page_printed, title, place_type, island,
            municipality, org_judicial, org_civil, org_militar,
            org_economica, org_eclesiastica, servicio_publico,
            obras_publicas, instruccion_publica, poblacion, industria,
            geografia, historia, description, ocr_note, stats, cross_references,
            confidence, window_size, model, source_file)
           VALUES (?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?)""",
        payload,
    )
    con.execute("COMMIT")

    n_total, n_high, n_med, n_low = con.execute(
        "SELECT COUNT(*), "
        "       SUM(CASE WHEN confidence='high'   THEN 1 ELSE 0 END), "
        "       SUM(CASE WHEN confidence='medium' THEN 1 ELSE 0 END), "
        "       SUM(CASE WHEN confidence='low'    THEN 1 ELSE 0 END) "
        "FROM text_entries"
    ).fetchone()
    print(f"\ntext_entries: {n_total} total  "
          f"(high={n_high or 0}  medium={n_med or 0}  low={n_low or 0})")

    print("\n--- Coverage by tomo ---")
    for r in con.execute(
        "SELECT vol, COUNT(*) n, COUNT(DISTINCT leaf) pages "
        "FROM text_entries GROUP BY 1 ORDER BY 1"
    ).fetchall():
        print(f"  tomo {r[0]}  {r[1]:>4} entries on {r[2]:>3} pages")

    print("\n--- Distribution by island ---")
    for r in con.execute(
        "SELECT COALESCE(island,'(unknown)'), COUNT(*) "
        "FROM text_entries GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall():
        print(f"  {r[0]:15} {r[1]:>5}")

    print("\n--- Top place types ---")
    for r in con.execute(
        "SELECT COALESCE(place_type,'(unknown)'), COUNT(*) "
        "FROM text_entries GROUP BY 1 ORDER BY 2 DESC LIMIT 12"
    ).fetchall():
        print(f"  {r[0]:25} {r[1]:>5}")

    print("\n--- Stats presence ---")
    n_with_hab = con.execute(
        "SELECT COUNT(*) FROM text_entries "
        "WHERE stats IS NOT NULL AND json_extract(stats, '$.habitantes') IS NOT NULL"
    ).fetchone()[0]
    print(f"  with habitantes: {n_with_hab}")


if __name__ == "__main__":
    main()
