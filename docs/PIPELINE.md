# Pipeline

How the Balearic subset of Riera's *Diccionario* is detected, extracted,
cleaned and published. See [CORPUS.md](CORPUS.md) for the source volumes
and [WEBSITE.md](WEBSITE.md) for the site.

The extraction is a five-stage pipeline. The first three stages are
deterministic; stages 4 and 5 use Anthropic's Claude (via the Claude
Max subscription — never the paid API). All outputs are checked into
the repository as JSON / DuckDB so the database and website rebuild
without re-spending tokens.

## Stage 1 — OCR ingestion (`scripts/fetch_volume.py`)

Download per-volume PDFs from BDCyL and run `pdftotext -raw` to
extract plain text. The text artefact under `data/txt/tomoNN.txt`
is kept for grep / inspection; it is *not* the source of truth for
the indexer.

## Stage 2 — Article detection by INDENT (`scripts/index_volume.py`)

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

## Stage 3 — Balearic classification (`scripts/index_volume.py`)

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

## Stage 4 — LLM extraction + DB load + web export

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
  `web/data.json` (~394 KB, 123 entries), the only artefact the
  static site consumes.

## Stage 5 — OCR cleanup pipeline

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

The PALMA article (the largest in the corpus — ~42 KB spanning
pp. 1091–1108 of tom VII, with ten intermediate pages of
illegible statistical tables) required 77 semantic corrections by
the subagent on top of 60+ mechanical corrections. The remaining
122 Balearic articles went through a corpus-wide anti-hallucination
audit by six parallel Claude Max subagents that produced roughly a
hundred additional corrections, each verified one-by-one against
the facsimile.

## Reproducing the pipeline

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

