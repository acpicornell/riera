-- Schema for the riera project (Balearic subset of Pablo Riera y
-- Sans' Diccionario geográfico-estadístico-histórico-biográfico-
-- postal-municipal-marítimo-eclesiástico de España y sus posesiones
-- de ultramar, Barcelona 1881-1887, 12 vols.).
--
-- One canonical table: text_entries, the Claude-extracted structured
-- articles. The page-text index (data/index/tomoNN.jsonl) is not
-- loaded into the DB — it is a per-volume build artifact used by
-- extract_text.py; the JSONL stays the source of truth.
--
-- Differences from minano:
--   * `leaf` here is the PDF page index (1-based), not an
--     Internet-Archive scan-leaf number. Riera has no separate
--     printed-leaf vs. printed-page distinction in its source.
--   * `seigneurial_regime` and `mayor_type` are dropped. By 1881 the
--     seigneurial regime had been abolished (Mendizábal 1836-1841 and
--     the 1873 abolition of the foral regime in Mallorca) and Riera
--     reports the post-1845 liberal apparatus only. The relevant
--     administrative attributes are now the "Organización judicial /
--     civil / militar / económica / eclesiástica" cluster Riera
--     templated into every entry; we keep them as structured TEXT
--     columns.

CREATE SEQUENCE IF NOT EXISTS seq_text_id START 1;

CREATE TABLE IF NOT EXISTS text_entries (
    id                  INTEGER PRIMARY KEY DEFAULT nextval('seq_text_id'),
    vol                 TEXT NOT NULL,           -- '01' .. '12'
    leaf                INTEGER NOT NULL,        -- 1-based PDF page index
    page_printed        TEXT,                    -- printed page number recovered from OCR, if any
    title               TEXT NOT NULL,            -- as cleaned by the LLM
    place_type          TEXT,                    -- villa / lugar / aldea / caserío / cortijo / castillo / isla / …
    island              TEXT,                    -- Mallorca / Menorca / Eivissa / Formentera / Cabrera
    municipality        TEXT,                    -- Modern town the entry depends on (post-1845 municipal map)
    -- Riera's nine-section administrative template. Each cell holds
    -- the cleaned transcription of that section's paragraph, or NULL
    -- if the article was short enough to omit it.
    org_judicial        TEXT,                    -- partido judicial / audiencia territorial / distancias
    org_civil           TEXT,                    -- gobierno civil / provincia / distancia
    org_militar         TEXT,                    -- capitanía general / gobierno militar
    org_economica       TEXT,                    -- administración de hacienda / contribuciones
    org_eclesiastica    TEXT,                    -- diócesis / parroquia / advocación / nombramiento
    servicio_publico    TEXT,                    -- correos / estafetas / conducciones
    obras_publicas      TEXT,                    -- caminos / carreteras / ferrocarril
    instruccion_publica TEXT,                    -- escuelas / alumnos
    poblacion           TEXT,                    -- casas / pisos / calles / plazas
    industria           TEXT,                    -- agricultura / molinos / talleres / oficios
    geografia           TEXT,                    -- situación / clima / orografía / hidrografía / límites
    description         TEXT,                    -- residual prose (Riera occasionally adds historical or anecdotal notes)
    ocr_note            TEXT,                    -- editor's note about OCR/transcription issues for this entry, shown collapsed in the UI
    stats               JSON,                    -- {vecinos, habitantes, edificios, viviendas, albergues, …}
    cross_references    TEXT[],                  -- e.g. ["V. la descripción general de Mallorca"]
    confidence          TEXT,                    -- 'high' | 'medium' | 'low'
    -- Multi-page window used at extraction time. 1 = single page;
    -- 2+ = mega-entry sliding window (PALMA, MAHÓN, MALLORCA, …,
    -- which in Riera frequently span several columns).
    window_size         INTEGER,
    -- Provenance.
    model               TEXT,                    -- e.g. 'claude-opus-4-7'
    source_file         TEXT,                    -- 'data/text/page_<vol>_<leaf>.json'
    extracted_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_text_entries_vol_leaf
    ON text_entries(vol, leaf);
CREATE INDEX IF NOT EXISTS idx_text_entries_title
    ON text_entries(title);
CREATE INDEX IF NOT EXISTS idx_text_entries_island
    ON text_entries(island);
CREATE INDEX IF NOT EXISTS idx_text_entries_municipality
    ON text_entries(municipality);
