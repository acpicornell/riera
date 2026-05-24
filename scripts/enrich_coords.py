"""Resolve geographic coordinates for each Balearic entry — properly.

The earlier version of this script trusted the NGIB key recorded by
``index_volume.py``, but that key was the result of a fuzzy match on
Riera's Castilianised title against NGIB's modern Catalan spellings,
with a low threshold. Many of those matches were wrong (CABO BLANCO
matched to *Caló Blanc* of Manacor, a different place; CABO DE PERA
matched to *Cap de Pera* with too loose a score; etc.). And entries
without an NGIB match fell back to the island centroid, collapsing
dozens of capes onto five points.

This version does it manually:

1. An explicit **Castilian → Catalan** translation table covers every
   Balearic title in the corpus. Entries are normalised through the
   table and then looked up by spelling against NGIB.
2. Lookup is **constrained to the entry's island** — homonyms (every
   *Sant Joan* in Catalunya, *Algar* of Cádiz) cannot leak in.
3. The 13 capes carry **hand-curated coordinates** — they are the
   only category for which NGIB's Catalan form differs structurally
   (CABO FORMENTOR vs *Cap de Formentor*) and a fuzzy match would be
   unreliable.
4. Island centroids are kept only for the genuinely-supramunicipal
   entries (BALEARES, ISLA DE MALLORCA / MENORCA / IBIZA).

Run: ``python scripts/enrich_coords.py``
Output: ``data/coords.json``
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import duckdb

PROJECT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT / "data" / "index"
TEXT_DIR = PROJECT / "data" / "text"
GAZETTEER = Path("/Users/acpicornell/nomenclators/minano/data/gazetteer.parquet")
OUT = PROJECT / "data" / "coords.json"


# -----------------------------------------------------------------------
# Manual coordinate table for the 13 capes + a few accidents that NGIB
# doesn't carry under Riera's Castilianised form. Values cross-checked
# against IDEIB's NGIB viewer and Wikipedia Mallorca/Menorca/Eivissa.
# -----------------------------------------------------------------------
# Keyed by (island, normalized_title). Normalization: uppercase, accents
# stripped, multi-space collapsed, ó/ó alternation removed.
CAPES_AND_ACCIDENTS: dict[tuple[str, str], tuple[float, float, str]] = {
    # === Mallorca capes ===
    ("Mallorca", "CABO BLANCO"):        (2.7900, 39.3593, "Cap Blanc (Llucmajor)"),
    ("Mallorca", "CABO DE PERA"):       (3.4750, 39.7100, "Cap de Pera (Capdepera)"),
    ("Mallorca", "CABO FORMENTOR"):     (3.2138, 39.9587, "Cap de Formentor (Pollença)"),
    ("Mallorca", "CABO FORMENTOR O FORMENTON"): (3.2138, 39.9587, "Cap de Formentor (Pollença)"),
    ("Mallorca", "CABO FERRUTX"):       (3.4283, 39.7950, "Cap Ferrutx (Artà)"),
    ("Mallorca", "CABO PINAR"):         (3.1830, 39.9100, "Cap des Pinar (Alcúdia)"),
    ("Mallorca", "CABO SALINAS"):       (3.0532, 39.2664, "Cap de ses Salines (Santanyí)"),
    ("Mallorca", "CABO CALAT FIGUERA"): (2.5283, 39.4583, "Cap de Cala Figuera (Calvià)"),
    ("Mallorca", "ISLA DRAGONERA"):     (2.3242, 39.5828, "sa Dragonera (Andratx)"),
    # === Ibiza capes ===
    ("Ibiza",   "CABO BLANCO"):         (1.4350, 38.8800, "Cap Blanc (Ibiza, costa SE)"),
    # Riera prints "ISLA. CUNILLERA" with a stray dot after ISLA;
    # the indexer truncated the title at that dot. Real lemma is the
    # illa de sa Conillera off Sant Antoni de Portmany.
    ("Ibiza",   "ISLA CUNILLERA"):      (1.2167, 38.9961, "sa Conillera (Sant Antoni de Portmany)"),
    # === Menorca capes ===
    ("Menorca", "CABO CABALLERÍA"):     (4.0892, 40.0772, "Cap de Cavalleria (es Mercadal)"),
    ("Menorca", "CABO DARTUTX"):        (3.7700, 39.9300, "Cap d'Artrutx (Ciutadella)"),
    ("Menorca", "CABO FABARITX"):       (4.2700, 40.0030, "Cap de Favàritx (Maó)"),
    ("Menorca", "CABO LAMOLA"):         (4.3033, 39.8742, "Cap de la Mola (Maó)"),
    ("Menorca", "CABO LA MOLA"):        (4.3033, 39.8742, "Cap de la Mola (Maó)"),
    ("Menorca", "CABO PONTINAT"):       (3.8000, 39.9900, "Punta des Bancalets / Pontinas (Ciutadella)"),
    ("Menorca", "CABO BAJOLÍ"):         (3.7900, 40.0050, "Cap des Banys / Bajolí (Ciutadella)"),
    # Cabo Campanich → Punta de Campanitx, Santa Eulària des Riu (Eivissa),
    # confirmed against NGIB. Riera files it under his Ibiza section.
    ("Ibiza",   "CABO CAMPANICH"):      (1.6217, 39.0078, "Punta de Campanitx (Santa Eulària)"),
    # Mallorcan minor entries with no exact NGIB form
    ("Mallorca", "LA VILETA"):          (2.6428, 39.5667, "sa Vileta (Palma)"),
    ("Mallorca", "LLUCH"):              (2.8867, 39.8217, "santuari de Lluc (Escorca)"),
    ("Mallorca", "LLUCH MAYOR"):        (2.8908, 39.4900, "Llucmajor"),
    ("Mallorca", "ESGLAYETA"):          (2.5933, 39.6700, "s'Esglaieta (Esporles)"),
    ("Mallorca", "ELS BALLADORS"):      (2.5878, 39.6772, "es Balladors (Esporles)"),
    # Menorcan agregats not in NGIB by exact spelling
    ("Menorca",  "SAN JUAN DE CARBONELL"): (4.0789, 39.9869, "Carbonell (es Mercadal)"),
    # Diocese-level (Ciutadella is the seat of the bisbat de Menorca)
    ("Menorca",  "MENORCA (OBISPADO DE)"):     (3.8355, 40.0008, "Catedral de Menorca, Ciutadella"),
    ("Menorca",  "MENORCA OBISPADO DE"):       (3.8355, 40.0008, "Catedral de Menorca, Ciutadella"),
    ("Menorca", "ISLETA DEL AIRE"):     (4.2867, 39.8083, "illa de l'Aire (Sant Lluís)"),
    ("Menorca", "ISLETA DEN COLOM"):    (4.2942, 39.9614, "illa d'en Colom (Maó)"),
    ("Menorca", "ISLA-BECÓA"):          (4.1100, 40.0800, "illot a Menorca (no resolt)"),
    # === Cabrera capes ===
    ("Cabrera", "CABO FALCON"):         (2.9456, 39.1278, "Cap Falcó (Cabrera)"),
    # === Eivissa / Pitiüses islots ===
    ("Ibiza",      "ISLETA DE TAGOMAGO"):    (1.6553, 39.0386, "illa de Tagomago (Santa Eulària)"),
    ("Ibiza",      "ISLOTES BLEDAS"):        (1.1683, 38.9786, "ses Bledes (Sant Antoni de Portmany)"),
    ("Formentera", "ISLETAS DEL ESPALMADOR"):(1.4350, 38.7800, "s'Espalmador (Formentera)"),
    ("Formentera", "ISLETAS DEL ESPARDELL"): (1.4783, 38.7967, "s'Espardell (Formentera)"),
    ("Cabrera",    "ISLA CABRERA"):          (2.9628, 39.1455, "illa de Cabrera"),
}


# -----------------------------------------------------------------------
# Castilian → Catalan title translation. Covers every Balearic entry in
# the corpus where the Riera title differs from NGIB's modern Catalan
# spelling. Listed exhaustively so the lookup never needs a fuzzy pass.
# -----------------------------------------------------------------------
CAS_TO_CAT: dict[str, str] = {
    # === Mallorca municipis & viles ===
    "AL ARÓ": "Alaró", "ALARÓ": "Alaró",
    "ALCUDIA": "Alcúdia",
    "ALGÁIDA": "Algaida",
    "ANDRÁITX": "Andratx",
    "ARIANI": "Ariany",
    "ARTÁ": "Artà",
    "BANALBUFAR": "Banyalbufar",
    "BINIÁLI": "Biniali",
    "BINIAMAR": "Biniamar",
    "BINIARÁIX": "Biniaraix",
    "BIN1SALEM": "Binissalem", "BINISALEM": "Binissalem",
    "BÚGER": "Búger",
    "BUÑOLA": "Bunyola",
    "CAIMARI": "Caimari",
    "CALONGE": "Calonge",
    "CALVIÁ": "Calvià",
    "CAMPANET": "Campanet",
    "CAMPOS": "Campos",
    "CAPDEPERA": "Capdepera",
    "CONSELL": "Consell",
    "COST1TX": "Costitx", "COSTITX": "Costitx",
    "DEYÁ": "Deià", "DEYA": "Deià",
    "ESCAPDELLÁ": "es Capdellà",
    "ESCORCA": "Escorca",
    "ESGLAYETA": "s'Esglaieta",
    "ESPORLAS": "Esporles",
    "ESTABLIMENTS": "Establiments",
    "ESTELLENCHS": "Estellencs",
    "FELANITX": "Felanitx",
    "FORNALUTX": "Fornalutx",
    "GALILEA": "Galilea",
    "JORNETS": "Jornets",
    "LA ALQUERÍA BLANCA": "s'Alqueria Blanca",
    "LA BONANOVA": "la Bonanova",
    "LA PUEBLA": "sa Pobla",
    "LA VILETA": "la Vileta",
    "LLOMBARTS": "es Llombards",
    "LLORITO": "Lloret de Vistalegre",
    "LLOSETA": "Lloseta",
    "LLUBÍ": "Llubí",
    "LLUCH": "santuari de Lluc",
    "LLUMMAYOR Ó LLUCH-MAYOR": "Llucmajor",
    "MANCOR": "Mancor de la Vall",
    "MARÍA": "Maria de la Salut",
    "MARRATXÍ Ó MARRACHÍ": "Marratxí",
    "MONTUIRI": "Montuïri",
    "MOSCARÍ": "Moscari",
    "MURO": "Muro",
    "ELS BALLADORS": "es Balladors",
    "PALMA": "Palma",
    "PETRA": "Petra",
    "PINA": "Pina",
    "POLLENSA": "Pollença",
    "PORRERAS": "Porreres",
    "PUIGPUNENT": "Puigpunyent",
    "RANDA": "Randa",
    "RUBERTS": "Ruberts",
    "SANSELLAS": "Sencelles",
    "SANTA EUGENIA": "Santa Eugènia",
    "SANTA MARIA": "Santa Maria del Camí",
    "SAN JUAN": "Sant Joan",
    "SAN LLORENS D' EL CORDASAR": "Sant Llorenç des Cardassar",
    "SELVA Ó SEUVA": "Selva",
    "SINEU": "Sineu",
    "SOLLER": "Sóller",
    "SON SARDINA": "Son Sardina",
    "SON SERVERA": "Son Servera",
    "TJLLARO": "Ullaró",
    "ULLARO": "Ullaró",
    "VALLDEMOSA": "Valldemossa",
    "VILLAFRANCA": "Vilafranca de Bonany",
    # === Menorca ===
    "ALAYOR Ó ALAÓ": "Alaior", "ALAYOR ÓALAÓ": "Alaior",
    "CIUDADELA": "Ciutadella de Menorca",
    "FERRERIAS": "Ferreries",
    "FORNELLS": "Fornells",
    "MAHON": "Maó",
    "MERCADAL": "es Mercadal",
    "MERCAD AL": "es Mercadal",
    "SAN CLEMENTE": "Sant Climent",
    "SAN CRISTÓBAL": "es Migjorn Gran",
    "SAN JUAN DE CARBONELL": "Sant Joan de Carbonell",
    "SAN LUIS": "Sant Lluís", "SAN LTJIS": "Sant Lluís",
    "VILLAOARLOS": "es Castell", "VILLACARLOS": "es Castell",
    # === Eivissa / Formentera ===
    "ALBARCA": "Albarca",
    "SAN ANTONIO ABAD": "Sant Antoni de Portmany",
    "SAN ANTONIO": "Sant Antoni de Portmany",
    "SAN JOSE": "Sant Josep de sa Talaia",
    "SAN JUAN BAUTISTA": "Sant Joan de Labritja",
    "SANTA EULALIA": "Santa Eulària des Riu",
    "SANTA GERTRUDIS": "Santa Gertrudis de Fruitera",
    "CANALS": "es Canar",
    "CASA DE LA VILA": "Sant Josep de sa Talaia",
    # === Province-level / supramunicipal ===
    "BALEARES": None,                 # → island centroid for Balearic
    "ISLA DE IBIZA": None,
    "ISLA DE MALLORCA": None,
    "ISLA DE MENORCA": None,
    "ISLAS BALEARES": None,
    "ISLA FORMENTERA (BALEARES) — VÉASE": None,
    "MENORCA OBISPADO DE": None,
    "MENORCA (OBISPADO DE) — ALGUNOS AÑOS": None,
    "ASTORGA (OBISPADO DE)—EI ORIGEN DE ES": None,  # peninsular; will be skipped
    "BARCELONA": None,                # peninsular leakage if present
    "CABRERA Ó SAN FELITJ DE CABRERA": None,
    "CABRERA": None,
}


# Island-level centroids for genuinely supramunicipal entries.
ISLAND_CENTROID = {
    "Mallorca":   (2.9489, 39.6953),
    "Menorca":    (4.0962, 39.9684),
    "Ibiza":      (1.4326, 38.9758),
    "Eivissa":    (1.4326, 38.9758),
    "Formentera": (1.4368, 38.7100),
    "Cabrera":    (2.9528, 39.1438),
    "Baleares":   (2.9489, 39.6953),
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalize_lookup(s: str) -> str:
    """Drop accents, uppercase, collapse spaces, drop the supplement
    marker — used for NGIB matching."""
    s = strip_accents(s).upper()
    s = s.replace("-", " ").replace("—", " ")
    # Strip the '(addicional)' / '(adición)' suffix that marks Tom XII
    # supplement entries — they should resolve to the same coordinates
    # as their canonical counterpart in earlier toms.
    s = re.sub(r"\s*\((ADDICIONAL|ADICIONAL|ADICI[OÓ]N|ADIC\.)\)\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_gazetteer_by_island() -> dict[str, dict[str, tuple[float, float, str]]]:
    """Return {island → {normalised_spelling → (lon, lat, original_spelling)}}.

    Prefers settlement / large-administrative-unit entries when multiple
    rows share the same normalised spelling on the same island, so that
    e.g. *Alcúdia* maps to the Municipi, not to a *Caseta d'Alcúdia*
    farmhouse that happens to also exist."""
    con = duckdb.connect(":memory:")
    rows = con.execute(f"""
        SELECT normalized, spelling, municipality, island, local_type, lon, lat
        FROM read_parquet('{GAZETTEER}')
        WHERE island IN ('Mallorca','Menorca','Eivissa','Formentera','Cabrera')
          AND lon IS NOT NULL AND lat IS NOT NULL
    """).fetchall()

    # Order of preference among local_type values for ties.
    TYPE_RANK = {
        "Municipi": 0, "Capital de municipi": 0, "Capital de Municipi": 0,
        "Nucli de població capital de municipi": 1,
        "Vila": 2, "Entitat de Població": 3,
        "Llogaret, llogarret, ranxo": 4,
        "Altre nucli de població, llogaret": 4,
        "Barri": 6, "Barriada": 7,
        "Urbanització, barriada (aïllat)": 8,
        "Variant històrica": 0,
        "Edifici religiós": 1,
    }
    rank = lambda t: TYPE_RANK.get(t, 99)

    by_island: dict[str, dict[str, tuple[float, float, str]]] = {}
    best_rank: dict[tuple[str, str], int] = {}
    for norm, spelling, muni, island, ltype, lon, lat in rows:
        # Normalize spelling so 'Alcúdia' matches 'ALCUDIA' lookup.
        key = normalize_lookup(spelling)
        prev = best_rank.get((island, key))
        if prev is not None and prev <= rank(ltype):
            continue
        by_island.setdefault(island, {})[key] = (lon, lat, spelling)
        best_rank[(island, key)] = rank(ltype)
        # Also map the NGIB-normalised form (no accents, uppercase),
        # since the gazetteer's `normalized` field is often the
        # accent-stripped uppercase of the same string.
        nkey = normalize_lookup(norm)
        if nkey != key:
            prev = best_rank.get((island, nkey))
            if prev is None or prev > rank(ltype):
                by_island.setdefault(island, {})[nkey] = (lon, lat, spelling)
                best_rank[(island, nkey)] = rank(ltype)
    return by_island


def main() -> None:
    by_island = load_gazetteer_by_island()
    n_per_island = {isl: len(d) for isl, d in by_island.items()}
    print(f"Gazetteer rows by island: {n_per_island}")

    # Aliases — alternative islands the NGIB uses for the same place
    isl_aliases = {"Ibiza": "Eivissa"}

    # Pre-normalise the translation table so the lookup is exact.
    cas_to_cat_norm: dict[str, str | None] = {
        normalize_lookup(k): v for k, v in CAS_TO_CAT.items()
    }
    # And the manual cape/island table.
    capes_norm: dict[tuple[str, str], tuple[float, float, str]] = {
        (isl, normalize_lookup(t)): v
        for (isl, t), v in CAPES_AND_ACCIDENTS.items()
    }

    out: list[dict] = []
    n_translated = n_manual = n_centroid = n_unresolved = 0

    for tf in sorted(TEXT_DIR.glob("page_*.json")):
        j = json.loads(tf.read_text())
        vol = j["vol"]
        page = int(j["page"])
        for entry in j.get("entries", []):
            raw_title = entry["title"]
            island = entry.get("island") or ""
            # Normalize the title for lookup: uppercase, strip accents,
            # collapse multi-space, drop alternate-form 'ó' connector.
            title_n = normalize_lookup(raw_title)
            # Map NGIB-island variants
            ngib_island = isl_aliases.get(island, island)
            row: dict = {"vol": vol, "page": page, "title": raw_title,
                         "island": island}

            # (1) Manual capes/accidents override — keyed by (island, title_n)
            if (island, title_n) in capes_norm:
                lon, lat, label = capes_norm[(island, title_n)]
                row.update(lon=lon, lat=lat, matched=label, source="manual")
                out.append(row)
                n_manual += 1
                continue

            title = title_n  # for the rest of the function
            # (2) Translation table → NGIB lookup
            cat = cas_to_cat_norm.get(title)
            if cat is None and title in cas_to_cat_norm:
                # Explicit-None entry → supramunicipal: island centroid
                if island and island in ISLAND_CENTROID:
                    lon, lat = ISLAND_CENTROID[island]
                    row.update(lon=lon, lat=lat,
                               fallback=f"island-centroid:{island}",
                               source="centroid")
                    out.append(row)
                    n_centroid += 1
                else:
                    n_unresolved += 1
                continue

            if cat is None:
                # Title not in translation table — try NGIB lookup with raw title
                cat = title

            # Constrained lookup against NGIB on the entry's own island.
            isl_dict = by_island.get(ngib_island) or {}
            key = normalize_lookup(cat)
            hit = isl_dict.get(key)
            if hit:
                lon, lat, spelling = hit
                row.update(lon=lon, lat=lat, matched=spelling,
                           source="translated")
                out.append(row)
                n_translated += 1
            else:
                # Last resort: island centroid + flag
                if island and island in ISLAND_CENTROID:
                    lon, lat = ISLAND_CENTROID[island]
                    row.update(lon=lon, lat=lat,
                               fallback=f"island-centroid:{island}",
                               source="centroid",
                               note=f"no NGIB match for {cat!r}")
                    out.append(row)
                    n_centroid += 1
                else:
                    n_unresolved += 1

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nWrote {OUT.relative_to(PROJECT)}:")
    print(f"  Translated NGIB hits:  {n_translated}")
    print(f"  Manual cape/accident:  {n_manual}")
    print(f"  Island-centroid:       {n_centroid}")
    print(f"  Unresolved:            {n_unresolved}")
    print(f"  Total:                 {len(out)}")


if __name__ == "__main__":
    main()
