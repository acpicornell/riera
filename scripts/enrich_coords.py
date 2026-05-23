"""Resolve geographic coordinates for each indexed Balearic entry.

For each entry in ``data/index/tomo<vol>.jsonl`` that carries an NGIB
match, look up the canonical (lon, lat) from the NGIB gazetteer and
emit a single ``data/coords.json`` keyed by (vol, page, lemma).

Entries without an NGIB match (typically Castilian-form capes and
islets like CABO PINAR, ISLETA DEL AIRE) fall back to the centroid of
their island. The fallback is flagged in the output so the map UI can
distinguish ``matched`` from ``island-centroid`` markers.

Run: ``python scripts/enrich_coords.py``
Output: ``data/coords.json``
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

PROJECT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT / "data" / "index"
GAZETTEER = Path("/Users/acpicornell/nomenclators/minano/data/gazetteer.parquet")
TEXT_DIR = PROJECT / "data" / "text"
OUT = PROJECT / "data" / "coords.json"

# Approximate island centroids (degrees), used as a fallback when
# NGIB has no match for the lemma. Coordinates from minano's enrich
# pipeline.
ISLAND_CENTROID = {
    "Mallorca":   (2.9489, 39.6953),
    "Menorca":    (4.0962, 39.9684),
    "Ibiza":      (1.4326, 38.9758),
    "Eivissa":    (1.4326, 38.9758),
    "Formentera": (1.4368, 38.7100),
    "Cabrera":    (2.9528, 39.1438),
    "Baleares":   (2.9489, 39.6953),  # province-level → Mallorca centroid
}


def load_gazetteer_lookup() -> dict[str, tuple[float, float, str]]:
    """Return {NGIB_normalized_key → (lon, lat, spelling)} from gazetteer."""
    con = duckdb.connect(":memory:")
    rows = con.execute(f"""
        SELECT normalized, spelling, lon, lat
        FROM read_parquet('{GAZETTEER}')
        WHERE island IN ('Mallorca','Menorca','Eivissa','Formentera','Cabrera')
          AND lon IS NOT NULL AND lat IS NOT NULL
    """).fetchall()
    lookup: dict[str, tuple[float, float, str]] = {}
    for norm, spelling, lon, lat in rows:
        # Keep first-seen value (NGIB has duplicate normalized for variants)
        if norm not in lookup:
            lookup[norm] = (lon, lat, spelling)
    return lookup


def main() -> None:
    gaz = load_gazetteer_lookup()
    print(f"Gazetteer rows with coords: {len(gaz)}")

    # Read text JSONs to know which entries actually need a coord
    text_keys: set[tuple[str, int, str]] = set()
    for tf in TEXT_DIR.glob("page_*.json"):
        j = json.loads(tf.read_text())
        for e in j.get("entries", []):
            text_keys.add((j["vol"], int(j["page"]), e["title"]))

    # Read index files for the NGIB match data
    index_by_key: dict[tuple[str, int, str], dict] = {}
    for idx_f in sorted(INDEX_DIR.glob("tomo*.jsonl")):
        for line in idx_f.read_text().splitlines():
            entry = json.loads(line)
            key = (entry["vol"], int(entry["page"]), entry["lemma"])
            index_by_key[key] = entry

    out: list[dict] = []
    n_matched = n_fallback = n_unresolved = 0
    for tf in sorted(TEXT_DIR.glob("page_*.json")):
        j = json.loads(tf.read_text())
        vol = j["vol"]
        page = int(j["page"])
        for entry in j.get("entries", []):
            title = entry["title"]
            island = entry.get("island")
            ng = None
            # Find matching index entry — prefer same lemma, otherwise any
            # entry on this page (multiple entries can be in one index page).
            for (v, p, l), idx in index_by_key.items():
                if v == vol and p == page:
                    if idx.get("ngib"):
                        ng = idx["ngib"]
                        break
            row = {"vol": vol, "page": page, "title": title, "island": island}
            if ng and ng["key"] in gaz:
                lon, lat, sp = gaz[ng["key"]]
                row["lon"] = lon
                row["lat"] = lat
                row["matched"] = sp
                row["match_score"] = ng["score"]
                row["match_type"] = ng.get("type")
                n_matched += 1
            elif island and island in ISLAND_CENTROID:
                lon, lat = ISLAND_CENTROID[island]
                row["lon"] = lon
                row["lat"] = lat
                row["fallback"] = f"island-centroid:{island}"
                n_fallback += 1
            else:
                n_unresolved += 1
                continue
            out.append(row)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nWrote {OUT.relative_to(PROJECT)}:")
    print(f"  NGIB-matched:     {n_matched}")
    print(f"  Island-centroid:  {n_fallback}")
    print(f"  Unresolved:       {n_unresolved}")
    print(f"  Total written:    {len(out)}")


if __name__ == "__main__":
    main()
