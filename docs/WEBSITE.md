# Website

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

