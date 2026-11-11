# Corpus and sources

## The source

Digital edition of the **Balearic Islands articles** of Pablo Riera y
Sans' *Diccionario geográfico, estadístico, histórico, biográfico,
postal, municipal, marítimo y eclesiástico de España y sus posesiones
de ultramar* (Barcelona, Imprenta y librería religiosa y científica
del heredero de Pablo Riera, 1881–1887, 12 vols.).

Riera was published during the early decades of the Bourbon
Restoration (1874–1931) and is organised around the **1877 national
census** (the first complete census produced by the
Instituto Geográfico-Estadístico under Carlos Ibáñez de Ibero) and
the post-1845 liberal administrative map: partido judicial,
audiencia territorial, gobierno civil, gobierno militar, diócesis.
For the Balearic Islands the dictionary captures the demographic
state of the archipelago shortly before the *filoxera* outbreak
of 1891.

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
| IX   | 1886 | 1 197 | 19 | S (SA — SL) |
| X    | 1886 | 1 069 | 4  | S (SO) — T |
| XI   | 1887 | 997   | 3  | V — Z |
| XII  | 1887 | 509   | 3  | Supplement |

Tom III is the densest Balearic volume — it absorbs every entry whose
lemma begins with C, including the 14 capes recorded as autonomous
entries (CABO BAJOLÍ, CABO BLANCO, CABO CABALLERÍA, CABO CALAT
FIGUERA, CABO CAMPANICH, CABO DARTUTX, CABO DE PERA, CABO FABARITX,
CABO FALCON, CABO FERRUTX, CABO FORMENTOR, CABO PINAR, CABO PONTINAT,
CABO SALINAS), plus the inhabited municipalities CALONGE, CALVIÁ,
CAMPANET, CAMPOS, CAPDEPERA, CIUDADELA, CONSELL, COSTITX. Tom IX
covers all S-prefixed lemmas through SL (SANABASTRE → SILL…),
including the Eivissan parish villages (SAN ANTONIO ABAD, SAN JOSE,
SAN JUAN BAUTISTA, SANTA EULALIA, SANTA GERTRUDIS) and Menorcan
SAN CRISTÓBAL; SO- entries like SOLLER, SON SARDINA and SON SERVERA
fall in Tom X.

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

- **NGIB translation table** (84 entries) — Castilian-to-Catalan
  mapping against the *Nomenclàtor Geogràfic de les Illes Balears*
  (Govern de les Illes Balears).
- **Manual cape table** (27 entries) — hand-curated lat/lon for the
  Mallorcan + Menorcan + Eivissan + Cabrera capes whose NGIB form
  (*Cap de Pinar*, *Cap de Formentor*…) diverges structurally from
  Riera's Castilian (*Cabo Pinar*, *Cabo Formentor*).
- **Island centroids** (12 entries) — the genuinely-supramunicipal
  articles (BALEARES, ISLA DE MALLORCA / MENORCA / IBIZA, the two
  diocesan articles in tom XII).

By place type: 53 villas, 24 lugares, 14 cabos, 8 islas, 5 ciudades,
5 agregados, 3 isletas, 2 aldeas, 2 ayuntamientos, 2 caseríos,
2 obispados, 1 archipiélago, 1 islotes, 1 cross-reference (MENORCA →
ISLA DE MENORCA).

## Sources

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

- *La Puebla*, *La Vileta*, *La Bonanova*, *La Alquería Blanca* live
  at L, not P, A or B. *San Antonio Abad*, *San Juan Bautista*,
  *Santa Eulalia*, *Santa María* live at S, not A, J, E or M. The
  corpus is scattered across all twelve volumes, never concentrated
  in any single one.
- The hundreds of Mallorcan *Son X* possessions that earlier
  dictionaries catalogued exhaustively are absent: the only `SON X`
  entries our indexer found in the Balearic corpus are
  **SON SARDINA** (agregado al ayunt. de Palma) and **SON SERVERA**
  (independent municipality).

