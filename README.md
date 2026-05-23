# Riera · Balearic subset

Digital edition of the **Balearic Islands articles** of Pablo Riera y
Sans' *Diccionario geográfico, estadístico, histórico, biográfico,
postal, municipal, marítimo y eclesiástico de España y sus posesiones
de ultramar* (Barcelona, Imprenta y librería religiosa y científica
del heredero de Pablo Riera, 1881–1887, 12 vols.).

Riera is the immediate successor to Pascual Madoz's *Diccionario*
(1845–1850) and the last great pre-twentieth-century geographical
dictionary of Spain. It records the country at the height of the
Restoration: post-1857 disentailment, after the 1873–1874 First
Republic, with the railway network largely completed, civil registry
in place, and the modern municipal map essentially settled. For the
Balearic Islands it captures the demographic shift between the Madoz
census and the late-century filoxera / textile-industry transitions.

This repository extracts every article relating to Mallorca, Menorca,
Eivissa, Formentera and Cabrera, structures the data into a relational
schema, and (eventually) publishes a static website for consultation —
mirroring the editorial choices and pipeline shape of the sibling
projects [`../minano`](../minano) (Miñano, 1826–1829) and
[`../madoz`](../madoz) (Madoz, 1845–1850).

## Coverage

| Indicator | Value |
|---|---|
| Volumes processed | 12 / 12 (1881–1887) |
| PDF pages indexed (dictionary body only) | 12 254 |
| Total articles detected | **25 520** |
| **Balearic articles detected** | **133** |
| Balearic ratio | 0.52 % |
| Public website | not yet built |
| License | AGPL-3.0-or-later (code); original text in the public domain (CC0 per BDCyL) |

### Per-volume breakdown

| Tom | PDF pp. | Body pp. | Articles | Balearic | Coverage (lemma range) |
|:---:|:---:|:---:|:---:|:---:|---|
| I | 1 021 | 24 – 1008 | 1 600 | 7 | A – AZ |
| II | 1 071 | 11 – 1061 | 1 614 | 9 | B – BU |
| III | 1 259 | 12 – 1247 | 2 287 | **27** | C – CUZ |
| IV | 943 | 12 – 931 | 1 622 | 14 | D – F |
| V | 1 239 | 9 – 1230 | 2 088 | 18 | G – J |
| VI | 1 141 | 12 – 1130 | 1 581 | 9 | L – LL |
| VII | 1 199 | 11 – 1191 | 2 503 | 11 | M – O |
| VIII | 1 047 | 11 – 1038 | 2 191 | 9 | P |
| IX | 1 197 | 11 – 1185 | **5 437** | 17 | S (saint-prefixed villages) |
| X | 1 069 | 11 – 1053 | 1 767 | 4 | S – T |
| XI | 997 | 51 – 988 | 1 546 | 4 | V – Z |
| XII | 509 | 15 – 460 | 1 284 | 4 | Suplemento |

Tom III is the densest Balearic volume — it absorbs every entry whose
lemma begins with C (including the 13 capes recorded as autonomous
entries: CABO BAJOLÍ, CABO BLANCO of Mallorca, CABO BLANCO of Ibiza,
CABO CABALLERÍA, CABO CALAT FIGUERA, CABO CAMPANICH, CABO DARTUTX,
CABO DE PERA, CABO FORMENTOR, CABO LAMOLA, CABO PINAR, CABO PONTINAT,
CABO SALINAS), plus the inhabited municipalities CALONGE, CALVIÁ,
CAMPANET, CAMPOS, CAPDEPERA, CIUDADELA, CONSELL, COSTITX. Tom IX is
the largest volume by raw article count (5 437) because it carries all
the *San* / *Santa* / *Santo* parishes of Spain, including the
Eivissan parish villages (SAN ANTONIO ABAD, SAN JOSE, SAN JUAN
BAUTISTA, SAN MIGUEL DE BALANZAT, SANTA EULALIA…) and Menorcan
SAN CRISTÓBAL.

### Distribution by island and place type

Of the 133 Balearic articles, 75 cross-validate against the NGIB
(Nomenclàtor Geogràfic de les Illes Balears) gazetteer:

| Island | Count |
|---|:---:|
| Mallorca | 60 |
| Menorca | 9 |
| Eivissa | 5 |
| Formentera | 1 |
| (no NGIB match — capes/islets/lagoons under Castilian forms) | 58 |

The 58 NGIB-unmatched entries are mostly maritime accidents
(CABO X, ISLA X, ISLETA X, PUERTO X) under Riera's Castilian spelling,
which differs structurally from NGIB's modern Catalan (CABO PINAR vs
*Cap de Pinar*, ISLETA DEL AIRE vs *l'Illa de l'Aire*). A small
override table will resolve them in stage 3.

## Source

The canonical source is the **Biblioteca Digital de Castilla y León**
(BDCyL) record `id=24173`:

<https://bibliotecadigital.jcyl.es/es/consulta/registro.cmd?id=24173>

Twelve per-volume PDFs are available under CC0, each with an embedded
text layer (PDFlib+PDI 8.0.0, ~2017 production).

| Tomo | Viewer path | PDF path |
|------|-------------|----------|
| I    | 10132262    | 10132396 |
| II   | 10132263    | 10132397 |
| III  | 10132264    | 10132398 |
| IV   | 10132265    | 10132399 |
| V    | 10132266    | 10132400 |
| VI   | 10132214    | 10132348 |
| VII  | 10132215    | 10132349 |
| VIII | 10132216    | 10132350 |
| IX   | 10132217    | 10132351 |
| X    | 10132218    | 10132352 |
| XI   | 10132219    | 10132353 |
| XII  | 10132220    | 10132354 |

PDF URLs follow the pattern
`https://bibliotecadigital.jcyl.es/es/catalogo_imagenes/grupo.do?path=<PDF-path>`
and require a browser `User-Agent` header. BDCyL serves the binary
directly at that endpoint despite the misleading `.do` suffix.

### Note on tom VI

On the first download attempt the BDCyL CDN truncated tom VI at
312 MB (correct size 498 MB). The truncated PDF had a corrupt xref
table and `pdftotext` could only emit a partial extraction. Re-running
`scripts/fetch_volume.py 06` after deleting the partial file
re-fetched the full file successfully. `fetch_volume.py` now treats
non-zero `pdftotext` exit codes as a soft warning instead of crashing
the batch.

### Editorial scope (from Riera's own prologue)

Riera explicitly bases his dictionary on the 1877 population census
and excludes places that Madoz had catalogued but no longer existed
as standalone population entities by 1881:

> *"Como base para nuestro DICCIONARIO hemos tomado el censo de
> población de 1877, publicado por el Instituto Geográfico-
> Estadístico; por lo tanto no debe extrañarse si en el nuestro no se
> encuentran muchos lugares que en el de Madoz y en otros aparecen.
> Estos lugares hoy se han agregado á otros para constituir una
> entidad de población, y esto es lo que en nuestro libro
> consignamos."*  (Tom I, *Cuatro palabras del editor*, p. XIV.)

He also re-alphabetises entries by their "true initial", so e.g.
*La Almunia* lives at L (not A) and *San Vicente de la Barquera*
lives at S (not V):

> *"hemos colocado los pueblos en la inicial con que principia su
> verdadera denominación ó las con que generalmente se les conoce."*

These two rules explain the 5–6× gap with Madoz's Balearic coverage:

| Work | Balearic articles | Per-volume |
|---|:---:|---|
| Miñano (1826–1829, 11 vols.) | ~ 182 | ~ 16 |
| Madoz (1845–1850, 16 vols.) | ~ 700 | ~ 44 |
| **Riera (1881–1887, 12 vols.)** | **133** | **~ 11** |

Madoz exhaustively catalogued every *predio*, *alquería*, *cala*,
*cabo*, *atalaya* and *islote*; Riera includes only inhabited places
plus a small set of major coastal features (the 13 *cabos* in tom
III, the islands of Cabrera / Dragonera / Espalmador / Espardell,
the Eivissan parishes and Menorcan villages). The hundreds of
Mallorcan *Son X* possessions Madoz listed are absent from Riera:
the only `SON X` entries in the entire dictionary are **SON SARDINA**
(Mallorca, agreg. al ayunt. de Palma) and **SON SERVERA** (now an
independent municipality), both correctly detected by the indexer.

## Pipeline

The extraction is a four-stage pipeline. All stages are deterministic
except the planned Anthropic-model call in stage 2; the model output
will be checked into the repository as JSON so the database and
website can be rebuilt without re-spending tokens.

1. **OCR ingestion** (`scripts/fetch_volume.py`).
   Download per-volume PDFs from BDCyL and run `pdftotext -raw` to
   extract plain text. The text artefact under `data/txt/tomoNN.txt`
   is kept for grep / inspection; it is *not* the source of truth for
   the indexer.

2. **Article detection by INDENT** (`scripts/index_volume.py`).
   Riera's print layout uses a typographic convention that
   `pdftotext` discards: every entry's first line is indented
   ~10-12 pt to the right of the body-text left margin. The indexer
   uses PyMuPDF to read each line's `x0` coordinate, recovers the
   left-column and right-column body baselines from the bimodal x0
   distribution, and flags as an article opener every line whose x0
   exceeds its column's baseline by ≥ 5 pt **and** whose lemma
   matches `^[A-Z]{2,}` **and** whose first 70 chars contain a
   `.—` / `. —` separator. Internal section headers (Organización
   judicial / civil / militar / económica / eclesiástica, Servicio
   público, Obras públicas, Instrucción pública, Población, Artes,
   Situación, Historia) share the indent but begin with TitleCase, so
   they are filtered out by an exclusion list rather than by
   re-analysing the indent.

   The indent signal recovers ~30 % more articles than a pure text
   regex on `pdftotext -raw` output, because the visual indent is a
   property of the print rather than of the text and survives OCR
   errors that break the textual `.—` pattern. It also lets the
   indexer auto-crop front matter (introductions, abbreviation
   tables, dedicatory texts) and trailing appendices (plate indexes,
   *Cuba*, *Puerto Rico*) by detecting the first and last contiguous
   block of pages where ≥ 2 indented all-caps openers carry a
   place-type marker.

3. **Balearic classification.**
   An article is Balearic iff its body's HEAD (first 40 lines, opener
   line excluded) contains at least one unambiguous Balearic token —
   one of `Mallorca`, `Menorca`, `Ibiza`, `Iviza`, `Eivissa`,
   `Formentera`, `Cabrera`, `Baleares`, `Mahón`, `Ciudadela`,
   `Palma de Mallorca`. Long entries (≥ 25 body lines) need ≥ 2 hits
   to avoid false positives from peninsular cities that mention
   Baleares once in an audiencia-territorial roster (BARCELONA,
   CARTAGENA, VALENCIA…). The detector deliberately rejects place
   names like *Alcudia*, *Andratx*, *Felanitx*, *Manacor* and *Inca*
   from the token list — they all have peninsular homonyms or appear
   in peninsular articles as cross-references (parishes named *anejo
   de la parroquial de Alcudia*).

4. **LLM extraction** *(TODO)*. Each Balearic article will be sent
   to Claude Opus 4.7 along with surrounding context, returning a
   structured JSON per article with title, place_type, island,
   municipality, the nine-section administrative template, stats
   and cross-references. The output will be loaded into a DuckDB
   database (`db/riera.duckdb`, schema in `db/schema.sql`) and
   exported as a single `web/data.json` consumed by a static site.

## Running locally

```bash
uv venv && uv pip install -e .

# Stage 1 — OCR ingestion (downloads ~5.3 GB of PDFs)
python scripts/fetch_volume.py 01      # one volume
python scripts/fetch_volume.py --all   # all twelve

# Stage 2 — Article + Balearic detection (writes data/index/tomoNN.jsonl)
python scripts/index_volume.py --all

# Aggregate report
python scripts/report.py
```

Both stage 1 and stage 2 are idempotent: re-running overwrites in
place, and the per-volume JSONL under `data/index/` is the canonical
list of Balearic articles for downstream LLM extraction.

## Divergences from the Miñano source

Unlike Internet Archive's chOCR (used by `../minano`), BDCyL does
not publish a standalone OCR / METS-ALTO artefact. The text is only
available inside the PDFs, and BDCyL serves no per-word bounding
boxes. Two consequences:

- The website will not be able to highlight matched text on the
  facsimile in the way `minano` does on the IA reader. Article-level
  page links to the BDCyL viewer remain available.
- There is no leaf-vs-printed-page distinction. The PDF page index
  is the only natural addressing scheme; printed page numbers
  recovered from the OCR text would be brittle (Riera's running
  headers are inconsistent across volumes).

## License

Code: AGPL-3.0-or-later (see `LICENSE`). Running a modified version
as a network service obliges the operator to make the modifications
available to its users.

Original text (1881–1887) and the BDCyL facsimile derived from a
public-domain edition are themselves in the public domain (CC0 per
the BDCyL record).
