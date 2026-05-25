# Riera · Balearic subset

Digital edition of the **Balearic Islands articles** of Pablo Riera y
Sans' *Diccionario geográfico, estadístico, histórico, biográfico,
postal, municipal, marítimo y eclesiástico de España y sus posesiones
de ultramar* (Barcelona, Imprenta y librería religiosa y científica
del heredero de Pablo Riera, 1881–1887, 12 vols.).

Riera records the country at the height of the Restoration:
post-1857 disentailment, after the 1873–1874 First Republic, with
the railway network largely completed, civil registry in place, and
the modern municipal map essentially settled. For the Balearic
Islands the dictionary captures the demographic state of the islands
shortly before the *filoxera* (1891) and the first wave of textile
and tourist transformations.

This repository extracts every article relating to Mallorca, Menorca,
Eivissa, Formentera and Cabrera, structures the data into a relational
schema, and publishes a static website for consultation.

## Coverage

| Indicator | Value |
|---|---|
| Volumes processed | 12 / 12 (1881–1887) |
| PDF pages indexed (dictionary body only) | 12 254 |
| Total articles detected | ~25 520 |
| **Balearic articles extracted** | **123** |
| Balearic ratio | ~0.48 % |
| DB schema | 12 narrative sections + `stats` JSON + `cross_references` |
| Public website | static site under `web/` (HTML + CSS + JS vanilla + one JSON file) |
| License | AGPL-3.0-or-later (code); original text in the public domain (CC0 per BDCyL) |

### Per-volume breakdown

| Tom | Year | PDF pp. | Balearic entries | Lemma range |
|:---:|:---:|:---:|:---:|---|
| I    | 1881 | 1 021 | 7  | A — AZ |
| II   | 1882 | 1 071 | 7  | B — BU |
| III  | 1882 | 1 259 | 23 | C — CUZ |
| IV   | 1883 | 943   | 13 | D — F |
| V    | 1884 | 1 239 | 17 | G — J |
| VI   | 1884 | 1 141 | 11 | L — LL |
| VII  | 1885 | 1 199 | 9  | M — O |
| VIII | 1885 | 1 047 | 7  | P |
| IX   | 1886 | 1 197 | 19 | S (saint-prefixed) |
| X    | 1886 | 1 069 | 4  | S — T |
| XI   | 1887 | 997   | 3  | V — Z |
| XII  | 1887 | 509   | 3  | Supplement |

Tom III is the densest Balearic volume — it absorbs every entry whose
lemma begins with C, including the 13 capes recorded as autonomous
entries (CABO BAJOLÍ, CABO BLANCO of Mallorca, CABO BLANCO of Ibiza,
CABO CABALLERÍA, CABO CALAT FIGUERA, CABO CAMPANICH, CABO DARTUTX,
CABO DE PERA, CABO FORMENTOR, CABO LAMOLA, CABO PINAR, CABO PONTINAT,
CABO SALINAS), plus the inhabited municipalities CALONGE, CALVIÁ,
CAMPANET, CAMPOS, CAPDEPERA, CIUDADELA, CONSELL, COSTITX. Tom IX
contains all the *San* / *Santa* / *Santo* parishes of Spain,
including the Eivissan parish villages (SAN ANTONIO ABAD, SAN JOSE,
SAN JUAN BAUTISTA, SANTA EULALIA…) and Menorcan SAN CRISTÓBAL.

### Distribution by island and place type

| Island | Entries |
|---|:---:|
| Mallorca | 86 |
| Menorca | 21 |
| Ibiza | 11 |
| Cabrera | 2 |
| Formentera | 2 |
| Baleares (supramunicipal) | 1 |
| **Total** | **123** |

All 123 entries carry coordinates resolved in three categories:

- **NGIB translation table** (~83 entries) — Castilian-to-Catalan
  mapping against the *Nomenclàtor Geogràfic de les Illes Balears*
  (Govern de les Illes Balears).
- **Manual cape table** (~27 entries) — hand-curated lat/lon for
  the 13 mallorcan + 7 menorcan + 7 ibizan capes whose NGIB form
  (*Cap de Pinar*, *Cap de Formentor*…) diverges structurally from
  Riera's Castilian (*Cabo Pinar*, *Cabo Formentor*).
- **Island centroids** (~13 entries) — the genuinely-supramunicipal
  articles (BALEARES, ISLA DE MALLORCA / MENORCA / IBIZA, the two
  diocesan articles in tom XII).

By place type: 55 villas, 25 lugares, 14 cabos, 7 islas, 5 agregados,
4 ciudades, 3 isletas, 2 ayuntamientos, 1 aldea, 1 archipiélago,
1 islotes, 1 santuario, 1 obispado.

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
and excludes places that had ceased to exist as standalone
population entities by 1881:

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

For the Balearic Islands, two consequences:

- *La Pobla*, *La Vileta*, *La Bonanova*, *La Alquería Blanca* live
  at L, not P, A or B. *San Antonio Abad*, *San Joan Bautista*,
  *Santa Eulalia*, *Santa María* live at S, not A, J, E or M. The
  corpus is scattered across all twelve volumes, never concentrated
  in any single one.
- The hundreds of Mallorcan *Son X* possessions that earlier
  dictionaries catalogued exhaustively are absent: the only `SON X`
  entries in the entire dictionary are **SON SARDINA** (agregado al
  ayunt. de Palma) and **SON SERVERA** (independent municipality),
  both correctly detected by the indexer.

## Pipeline

The extraction is a five-stage pipeline. The first three stages are
deterministic; stages 4 and 5 use Anthropic's Claude (via the Claude
Max subscription — never the paid API). All outputs are checked into
the repository as JSON / DuckDB so the database and website rebuild
without re-spending tokens.

### Stage 1 — OCR ingestion (`scripts/fetch_volume.py`)

Download per-volume PDFs from BDCyL and run `pdftotext -raw` to
extract plain text. The text artefact under `data/txt/tomoNN.txt`
is kept for grep / inspection; it is *not* the source of truth for
the indexer.

### Stage 2 — Article detection by INDENT (`scripts/index_volume.py`)

Riera's print layout uses a typographic convention that `pdftotext`
discards: every entry's first line is indented ~10–12 pt to the right
of the body-text left margin. The indexer uses PyMuPDF to read each
line's `x0` coordinate, recovers the left-column and right-column
body baselines from the bimodal x0 distribution, and flags as an
article opener every line whose x0 exceeds its column's baseline by
≥ 5 pt **and** whose lemma matches `^[A-Z]{2,}` **and** whose first
70 chars contain a `.—` / `. —` separator.

Internal section headers (*Organización judicial / civil / militar /
económica / eclesiástica*, *Servicio público*, *Obras públicas*,
*Instrucción pública*, *Población*, *Artes*, *Situación*, *Historia*)
share the indent but begin with TitleCase, so they are filtered out
by an exclusion list rather than by re-analysing the indent.

The indent signal recovers ~30 % more articles than a pure text
regex on `pdftotext -raw` output, because the visual indent is a
property of the print rather than of the text and survives OCR
errors that break the textual `.—` pattern. It also lets the
indexer auto-crop front matter (introductions, abbreviation
tables, dedicatory texts) and trailing appendices (plate indexes,
*Cuba*, *Puerto Rico*) by detecting the first and last contiguous
block of pages where ≥ 2 indented all-caps openers carry a
place-type marker.

### Stage 3 — Balearic classification (`scripts/index_volume.py`)

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

A manual exclusion list (`data/manual_exclusions.txt`) overrides
the body-token heuristic for a handful of well-documented body-bleed
false positives — chiefly Cuban / Filipino entries on the same page
as a Balearic neighbour, and page-continuation headers (`SANTA
M A R I A` printed with letter-spaced typography) that PyMuPDF
mistakes for fresh openers.

### Stage 4 — LLM extraction + DB load + web export

The output of Stage 3 is a per-volume JSONL under `data/index/`
listing each Balearic article with its lemma, body opener and
fuzzy NGIB match. From there:

- **`scripts/refresh_text.py`** reconciles `data/index/*.jsonl` ↔
  `data/text/page_*.json`. New articles get a minimal placeholder
  derived from the parser; deleted lemmas are pruned; existing
  rich entries are preserved.
- **Article descomposition.** Each Balearic article is read by
  Anthropic Claude (Max subscription, via subagent dispatch or
  in-session work — never the paid API) and broken down into the
  twelve-section template that Riera himself uses:
    - `org_judicial` · `org_civil` · `org_militar` · `org_economica`
      · `org_eclesiastica`
    - `servicio_publico` · `obras_publicas` · `instruccion_publica`
    - `poblacion` · `industria` · `geografia` · `historia`
    - plus a free-form `description`, a `stats` JSON
      (habitantes, edificios, habitados_temporalmente,
      inhabitados, caserios_y_grupos, presupuesto_municipal_pts…)
      and a `cross_references` list.
- **`scripts/load_text.py`** writes the per-page JSON into a
  DuckDB database (`db/riera.duckdb`, schema `db/schema.sql`).
- **`scripts/enrich_coords.py`** resolves lat/lon via NGIB
  translation table + manual cape coordinates + island centroids
  → `data/coords.json`.
- **`scripts/export_web_data.py`** joins everything and produces
  `web/data.json` (~338 KB, 123 entries), the only artefact the
  static site consumes.

### Stage 5 — OCR cleanup pipeline

The text that PyMuPDF returns is faithful to the OCR but carries
systematic typographic artefacts of the original composition:

- End-of-line **soft hyphens** that were never stitched
  (`resi-\ndencia` instead of `residencia`).
- Italic passages **decompressed letter-by-letter**
  (`T a r r a g o n a`, `A r a g ó n`, `D á m e t e`).
- **Section markers destroyed** by OCR (`vS^. geog`, `Or^. júd`,
  `Eist. y Biog`).
- Archaic conjunctions and prepositions **fused** to the
  neighbouring word (`flotaá conquistar`, `mallorquinesyá los
  reyes`, `Aragóny Mallorca`).
- Roman numerals scattered with spaces (`V I I`, `Cárlos II I`).

Cleanup runs in two successive passes:

1. **Mechanical pass** (deterministic regex): soft-hyphen stitching;
   collapse of runs of 3+ singletons separated by spaces (for the
   italic letter-spacing); normalisation of known broken section
   markers; a curated dictionary of specific corrections verified
   against the PDF (`huques`→`buques`, `iuz`→`luz`,
   `Almudaína`→`Almudaina`…).

2. **Semantic pass** via Claude Max subagents with PDF verification.
   For each suspect word, the subagent opens the original PDF page
   with PyMuPDF, verifies what Riera actually wrote, and only
   corrects when the canonical form is unambiguously present in the
   facsimile. **Absolute rule**: no invention, no translation, no
   paraphrase. If the word is not recoverable from the PDF, it is
   preserved as-is.

The PALMA article (the largest in the corpus — ~40 KB spanning
pp. 1091–1108 of tom VII, with ten intermediate pages of
illegible statistical tables) required 77 semantic corrections by
the subagent on top of 60+ mechanical corrections. The remaining
76 Balearic articles were already clean enough from Stage 4 and
contributed roughly fifty additional fixes between them.

## Website

The static site under `web/` consumes a single `web/data.json` and
offers five tabs:

- **Inici** — project overview, summary statistics and a five-card
  grid (one per island) with entry counts and short descriptions.
- **Explorar** — filterable table (search by title or text; filters
  by island, municipality, place type, volume, confidence). Selecting
  a row expands the full article rendered as the twelve administrative
  sections, the demographic stats and the cross-references.
- **Mapa** — Leaflet map with one circle marker per entry. Radius is
  proportional to √habitants and colour identifies the island. Click
  a marker to open the full article.
- **Estadístiques** — six charts:
    - Top 25 nuclei by population
    - Building composition stacked bars (habitats establement /
      temporally inhabited / uninhabited)
    - Distribution by place type
    - Demography per island as twin donuts (habitants / edificis)
    - Density top 50 (habitants/edifici ratio)
    - Municipality pyramid as tag-cloud groups
- **Notes** — three-part guide: the dictionary itself (history,
  editorial decisions, fitxa structure); the methodology of this
  digital edition (sources, indent detection, OCR cleanup pipeline);
  and Riera's most common abbreviations.

The site is 100 % static (HTML + CSS + JS vanilla + Leaflet for the
map). No backend, no build step, no framework. A clean clone with
`riera.duckdb` and `data.json` already checked in serves the site
without running any script.

## Running locally

```bash
uv venv && uv pip install -e .

# Stage 1 — OCR ingestion (downloads ~5.3 GB of PDFs)
python scripts/fetch_volume.py 01      # one volume
python scripts/fetch_volume.py --all   # all twelve

# Stage 2 + Stage 3 — Article detection + Balearic classification
python scripts/index_volume.py --all

# Stage 4 — Reconcile, load, enrich, export
python scripts/refresh_text.py         # data/index/*.jsonl ↔ data/text/page_*.json
python scripts/load_text.py            # DuckDB
python scripts/enrich_coords.py        # lat/lon resolution
python scripts/export_web_data.py      # web/data.json

# Stage 5 — OCR cleanup is dispatched per article via Claude Max
# subagents; there is no CLI for it.

# Serve locally
python -m http.server 8000 --directory web
```

All stages are idempotent: re-running overwrites in place. Aggregate
status report:

```bash
python scripts/report.py
```

## License

Code: AGPL-3.0-or-later (see `LICENSE`). Running a modified version
as a network service obliges the operator to make the modifications
available to its users.

Original text (1881–1887) and the BDCyL facsimile derived from a
public-domain edition are themselves in the public domain (CC0 per
the BDCyL record).
