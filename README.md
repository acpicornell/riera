# Riera · Balearic subset

[![Deploy](https://github.com/acpicornell/riera/actions/workflows/deploy.yml/badge.svg)](https://github.com/acpicornell/riera/actions/workflows/deploy.yml)

Digital edition of the **Balearic Islands articles** of Pablo Riera y
Sans' *Diccionario geográfico, estadístico, histórico, biográfico,
postal, municipal, marítimo y eclesiástico de España y sus posesiones
de ultramar* (Barcelona, 1881–1887, 12 vols.), organised around the 1877
census. This repository extracts every article relating to Mallorca,
Menorca, Eivissa, Formentera and Cabrera, structures it into a
relational schema and publishes a static website.

Live at <https://riera.corpusbalear.org>. Part of
[Corpus Balear](https://corpusbalear.org).

## What's in it

- 12 of 12 volumes processed (1881–1887): 12 254 PDF pages of dictionary
  body, ~25 520 articles detected.
- **123 Balearic articles** (~0.48 %): 86 Mallorca, 21 Menorca, 11 Ibiza,
  2 Cabrera, 2 Formentera, 1 supramunicipal — all with coordinates.
- Each article broken into Riera's own twelve administrative sections,
  plus a `stats` JSON and cross-references.
- A static site in Catalan (`web/`): explorable table, map, statistics
  and notes.

## How it was made

The CC0 PDFs of the Biblioteca Digital de Castilla y León are read with
PyMuPDF; article openers are found by their printed indent and
classified as Balearic by deterministic token rules. Claude (via the
Claude Max subscription) decomposes each article into sections and runs
an OCR cleanup verified against the facsimile, with no invention
allowed. The result is loaded into DuckDB, geocoded against the NGIB and
exported as `web/data.json`.

## Run locally

```bash
uv venv && uv pip install -e .
python -m http.server 8000 --directory web
```

`db/riera.duckdb` and `web/data.json` are committed, so a clean clone
serves the site without running any script. The full pipeline is in
[docs/PIPELINE.md](docs/PIPELINE.md).

## Documentation

- [docs/CORPUS.md](docs/CORPUS.md) — the source work, coverage tables
  (per volume, island and place type), the BDCyL volumes and Riera's
  editorial scope.
- [docs/PIPELINE.md](docs/PIPELINE.md) — the five stages (OCR ingestion,
  indent-based detection, Balearic classification, LLM extraction and
  export, OCR cleanup) and the commands to reproduce them.
- [docs/WEBSITE.md](docs/WEBSITE.md) — the five tabs of the static site.

## License

Code: AGPL-3.0-or-later (see `LICENSE`). Running a modified version
as a network service obliges the operator to make the modifications
available to its users.

Original text (1881–1887) and the BDCyL facsimile derived from a
public-domain edition are themselves in the public domain (CC0 per
the BDCyL record).

Coordinates in `data/coords.json` derive from the *Nomenclàtor
Geogràfic de les Illes Balears* (NGIB), published by the Govern de
les Illes Balears (IDEIB) under a Creative Commons Attribution
licence (CC BY). Source dataset:
<https://intranet.caib.es/opendatacataleg/es/dataset/lloc_anomenat>.

## How to cite

As given in the site footer:

> Picornell Company, A. C. *Diccionari de Riera* (1881), edició digital.
> Corpus Balear · riera.corpusbalear.org
