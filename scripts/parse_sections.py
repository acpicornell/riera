"""Riera-native section parser — administrative + geographic.

Riera's corpus has TWO distinct article shapes, and the right strategy
is different for each:

  • ADMINISTRATIVE entries (V., L., C., Ald., Cas., Cot., Felig.,
    Desp., Villa, Ciudad, Aldea, Lugar, Caserío, Ayuntamiento) follow
    a structured 9-section template. The classification fact lives in
    Org. civ. → 'Corresponde á la prov. de X'.

  • GEOGRAPHIC entries (CABO, CALA, ISLA, PUNTA, BAHÍA, PROMONTORIO,
    ENSENADA, CAYO, BAJO, FONDEADERO, FARO, MORRO, GOLFO, …) are
    free prose with no Org. civ. The classification fact lives in
    explicit references to the Balearic islands or maritime
    provinces in the body itself.

The dispatch is decided by the lemma's first word OR the place-type
abbreviation that appears immediately after the lemma's `.—`
separator. Once routed, each strategy uses a small, focused regex
set rather than the previous cascade of token-counting heuristics.

Section coverage (administrative only):

    LEMMA.—V. con ayunt.
      <head paragraph — agregados, statistics, geography>
      Org. judicial.    audiencia / partido judicial
      Org. civ.         provincia / distrito / circunscripción
      Org. mil.         capitanía general / gobierno militar / depto. marítimo
      Org. econ.        intervención / administración / recaudación
      Org. ecles.       diócesis / arciprestazgo / parroquia
      Servicio público. correo / telégrafo / alumbrado
      Obras públicas.   casa consistorial / fuentes / caminos
      Instrucción públ. escuelas elementales / superior
      Población.        habitantes / edificios
     (Industria | Geografía | Producciones | Historia — optional tails)

The section markers are typographically distinct and (after OCR noise
normalisation) regex-extractable with high confidence. Once the body
is split into sections, the discriminative facts we care about — IS
THIS BALEARIC? — are explicit fields:

    sections['org_civ'].provincia    == 'Baleares'   → Balearic
    sections['org_ecles'].diocesis   ∈ {'Mallorca', 'Menorca', 'Ibiza'}

There is no need to count BALEARIC_TOKENS, no need for cascading
negative-evidence rules. The entry tells us where it belongs in its
own admin section.

This module is the foundation for the next-generation indexer: it
replaces the regex-token classification pipeline with a parse-and-
check pipeline that is deterministic, semantically clear, and
auditable per field.

Run as a script for a smoke test:
    python scripts/parse_sections.py
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Section markers
#
# Each Riera section announces itself with a canonical phrase. OCR
# occasionally garbles the 'Org.' prefix (Or^., Ory., O.g, Org-, Ori.)
# but reliably preserves the trailing section-name token (judicial,
# civ., mil., econ., ecles.). We anchor on that token, with a
# permissive lookbehind for the 'Or' family.
#
# Order matters: the most specific tokens come first so 'Servicio
# público' is captured as a whole rather than matching just
# 'público'.
# ---------------------------------------------------------------------------

_ORG_PREFIX = r"(?:[OoQ][a-z\.\^]{0,3}[\.\,\^]?\s+|\s+)"

SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Compound section names go first
    ("servicio_publico",
     re.compile(r"\bservicio\s+p[uú]bl(?:ico)?\.?", re.I)),
    ("obras_publicas",
     re.compile(r"\bobras\s+p[uú]blicas?\.?", re.I)),
    ("instruccion_publica",
     re.compile(r"\binstrucci[óo]n\s+p[uú]bl(?:ica)?\.?", re.I)),
    # Org. <subfield> family — anchor on the SUBFIELD token because
    # 'Org.' itself is OCR-prone.
    ("org_judicial",
     re.compile(rf"{_ORG_PREFIX}judicial\.?", re.I)),
    ("org_civ",
     re.compile(rf"{_ORG_PREFIX}civ(?:il)?\.", re.I)),
    ("org_mil",
     re.compile(rf"{_ORG_PREFIX}mil(?:itar)?\.", re.I)),
    ("org_econ",
     re.compile(rf"{_ORG_PREFIX}econ(?:[óo]mica)?\.", re.I)),
    ("org_ecles",
     re.compile(rf"{_ORG_PREFIX}ecles(?:i[áa]stica)?\.", re.I)),
    # Stand-alone sections
    ("poblacion",
     re.compile(r"(?:^|[\.\—\n])\s*Poblaci[óo]n\.", re.I)),
    ("industria",
     re.compile(r"(?:^|[\.\—\n])\s*Industria\.", re.I)),
    ("geografia",
     re.compile(r"(?:^|[\.\—\n])\s*Geograf[íi]a\.", re.I)),
    ("producciones",
     re.compile(r"(?:^|[\.\—\n])\s*Producciones\.", re.I)),
    ("historia",
     re.compile(r"(?:^|[\.\—\n])\s*Historia\.", re.I)),
]


# ---------------------------------------------------------------------------
# Per-section field extractors
#
# These are the FIELDS we extract from each section's prose. The list
# is intentionally narrow — only the things we actually need for
# classification, statistics and search. Anything richer goes to the
# LLM extractor downstream (which still serves the rich web UI).
# ---------------------------------------------------------------------------


# The 46 peninsular Spanish provinces + Canarias, in accent-stripped
# lowercase form. Used by ParsedEntry.is_balearic to short-circuit on
# self-declared peninsular entries.
_PROV_NON_BAL_SET = {
    "alava", "albacete", "alicante", "almeria", "asturias", "oviedo",
    "avila", "badajoz", "barcelona", "burgos", "caceres", "cadiz",
    "santander", "castellon", "ciudad real", "cordoba", "cuenca",
    "gerona", "granada", "guadalajara", "guipuzcoa", "huelva", "huesca",
    "jaen", "coruna", "leon", "lerida", "logrono", "lugo", "madrid",
    "malaga", "murcia", "navarra", "orense", "palencia", "pontevedra",
    "salamanca", "segovia", "sevilla", "soria", "tarragona", "teruel",
    "toledo", "valencia", "valladolid", "vizcaya", "zamora", "zaragoza",
    "canarias",
}

# Peninsular dioceses — accent-stripped, lowercased. Used to reject
# entries that self-declare 'Dióc. de X' where X is a non-Balearic
# Spanish diocese. The Balearic dioceses (Mallorca, Menorca, Ibiza)
# are checked separately as positive evidence.
_PEN_DIOCESE_SET = {
    "astorga", "toledo", "tarragona", "barcelona", "valencia",
    "santander", "almeria", "lerida", "leon", "burgos", "valladolid",
    "granada", "sevilla", "cordoba", "malaga", "cadiz", "huesca",
    "jaca", "calahorra", "tortosa", "orihuela", "siguenza", "cuenca",
    "ciudad", "albacete", "salamanca", "segovia", "avila",
    "zamora", "palencia", "logrono", "pamplona", "vitoria", "bilbao",
    "santiago", "lugo", "orense", "mondonedo", "tuy", "oviedo",
    "plasencia", "coria", "badajoz", "caceres", "albarracin",
    "barbastro", "guadix", "jaen", "murcia", "huelva", "alicante",
    "teruel", "soria", "gerona", "navarra", "pontevedra",
}


def _strip_accents_lower(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def _unwrap_hyphens(text: str) -> str:
    """Join words that pdftotext broke across lines with a hyphen.

    19th-century typesetting hyphenates words at line ends. pdftotext
    preserves the hyphen+newline literally, so 'Bale-\nares' arrives
    as a 4-char fragment followed by a separate token. Reassemble
    them before any field-extraction regex runs."""
    return re.sub(r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ])-\s*\n\s*"
                  r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ])", r"\1\2", text)


# Recognise the captured 'province' token, allowing the common OCR
# corruptions Riera shows for 'Baleares' (Balsares, Bsleares, etc.).
# Any captured token whose accent-stripped lowercase form starts with
# one of these prefixes is treated as Baleares. Other captured tokens
# are returned verbatim — the caller decides whether they're peninsular
# from set membership.
_BALEARES_PREFIXES = ("balear", "bsleare", "balsare", "baleare", "baleat")


# Tokens that are NEVER province names — captured when the regex hits
# section-marker words instead of an actual province. 'civil' / 'jud'
# / 'mil' come from 'Org. civ./jud./mil.' bleeding into a malformed
# 'prov.' clause. Filipino islands ('masbate', 'cebú', 'luzon') get
# captured in colonial entries whose lemma escaped the COLONIAL gate.
_PROVINCE_BLACKLIST = {
    "civil", "jud", "mil", "econ", "ecles", "judicial", "civ", "militar",
    "economica", "eclesiastica", "publica", "publico", "social",
    "masbate", "cebu", "luzon", "mindanao", "panay", "samar", "leyte",
    "mindoro", "negros", "bohol", "marinduque", "palawan", "cavite",
    "vecindario", "ayuntamiento", "estado",
}


def _clean_province(raw: str) -> str:
    """Normalise a captured province name to a canonical token.

    Steps:
      1. Trim punctuation and collapse internal whitespace.
      2. Drop articles ('la', 'las', 'el', 'los') and trailing
         connector clauses ('y contribuye al', 'al partido', etc.).
      3. Detect 'Baleares' via prefix match against the list of OCR
         variants — anything starting with 'balear' / 'balsare' /
         'baleare' is canonicalised to 'baleares'.
      4. For two-word provinces ('Ciudad Real'), keep both tokens.
      5. Lowercase, strip accents."""
    s = raw.strip(" .,;:")
    s = re.split(
        r"\s+(?:y\b|al\b|para\b|que\b|contribuye|en\s+lo|del|de\b)",
        s, maxsplit=1, flags=re.I,
    )[0]
    s = re.sub(r"^(?:la\s+|las\s+|el\s+|los\s+)", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .,")
    norm = _strip_accents_lower(s)
    if any(norm.startswith(p) for p in _BALEARES_PREFIXES):
        return "baleares"
    # Blacklist: when the regex anchors on the wrong token (Org. civ.
    # bleeding into a malformed prov. clause, or Filipino islands
    # captured by entries whose colonial-lemma marker was garbled by
    # OCR), the captured 'province' is nonsense. Treat as no match.
    first_word = norm.split(" ")[0] if norm else ""
    if first_word in _PROVINCE_BLACKLIST or norm in _PROVINCE_BLACKLIST:
        return ""
    return norm


_PROV_RE = re.compile(
    r"prov\.?(?:incia)?\s+(?:de\s+)?([A-Za-záéíóúñÑÁÉÍÓÚüÜ\s]{2,40})",
    re.I,
)


def parse_org_civ(text: str) -> dict:
    """Extract `provincia` from Org. civ. section text.

    Riera writes 'Corresponde á la prov. de Baleares, al 3.er
    distrito de su part. jud. …'. We capture the province name
    after 'prov. de'."""
    m = _PROV_RE.search(text)
    if not m:
        return {"provincia": None, "raw": text[:240]}
    return {"provincia": _clean_province(m.group(1)), "raw": text[:240]}


_DIOC_RE = re.compile(
    r"di[óo]c\.?(?:esis)?\s+(?:de\s+)?([A-Za-záéíóúñÑÁÉÍÓÚüÜ]{2,30})",
    re.I,
)
# Spanish stopwords that the diocese regex occasionally captures when
# the article doesn't begin its 'dióc.' clause with the diocese name
# (e.g. 'dióc. que se halla en el archipiélago…').
_DIOCESE_STOPWORDS = {
    "que", "la", "las", "el", "los", "en", "de", "del", "y", "o", "a",
    "se", "ese", "esta", "estos", "una", "lo", "su", "sus", "los",
    "men", "pe",
}
_ARCIPR_RE = re.compile(
    r"arciprestazgo\s+(?:de\s+)?([A-Za-záéíóúñÑÁÉÍÓÚüÜ\s]{2,40}?)"
    r"(?:[,\.\-—]|\s+y\b)",
    re.I,
)


def parse_org_ecles(text: str) -> dict:
    """Extract `diocesis` and `arciprestazgo` from Org. ecles."""
    out: dict = {"diocesis": None, "arciprestazgo": None, "raw": text[:240]}
    m = _DIOC_RE.search(text)
    if m:
        out["diocesis"] = _strip_accents_lower(m.group(1).strip(" .,;:"))
    m = _ARCIPR_RE.search(text)
    if m:
        out["arciprestazgo"] = _strip_accents_lower(m.group(1).strip(" .,;:"))
    return out


_AUDIENCIA_RE = re.compile(
    r"audiencia\s+(?:territorial\s+)?(?:de\s+)?"
    r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]+(?:\s+[A-Za-záéíóúñÑÁÉÍÓÚüÜ]+)?)",
    re.I,
)
_PART_JUD_RE = re.compile(
    r"part(?:ido|\.)\s+jud(?:icial|\.)?\s+(?:de\s+)?"
    r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]+(?:\s+[A-Za-záéíóúñÑÁÉÍÓÚüÜ]+)?)",
    re.I,
)


def parse_org_judicial(text: str) -> dict:
    out: dict = {"audiencia": None, "partido_judicial": None,
                 "raw": text[:240]}
    m = _AUDIENCIA_RE.search(text)
    if m:
        out["audiencia"] = _strip_accents_lower(m.group(1).strip(" .,;:"))
    m = _PART_JUD_RE.search(text)
    if m:
        out["partido_judicial"] = _strip_accents_lower(m.group(1).strip(" .,;:"))
    return out


def _to_int(s: str) -> Optional[int]:
    s = re.sub(r"[\.,\s]", "", s)
    if not s.isdigit():
        return None
    return int(s)


_HAB_RE = re.compile(r"([\d\.,]+)\s*hab(?:itantes)?", re.I)
_EDIF_RE = re.compile(r"([\d\.,]+)\s*edif(?:icios)?", re.I)


def parse_poblacion(text: str) -> dict:
    out: dict = {"habitantes": None, "edificios": None, "raw": text[:240]}
    m = _HAB_RE.search(text)
    if m:
        out["habitantes"] = _to_int(m.group(1))
    m = _EDIF_RE.search(text)
    if m:
        out["edificios"] = _to_int(m.group(1))
    return out




# ---------------------------------------------------------------------------
# Entry kind detection — administrative vs geographic
# ---------------------------------------------------------------------------

# Lemma starts with a geographic-type word: the entry is a natural
# feature (cape, cala, island, etc.) and the body is free prose with
# no Org. civ. section. List ordered by Riera's vocabulary frequency.
GEOGRAPHIC_LEMMA_PREFIX_RE = re.compile(
    r"^\s*(?:CABO|CALA|ISLA|ISLAS|ISLOTE|ISLOTES|ISLETA|ISLETAS|"
    r"PUNTA|PUERTO|SIERRA|MONTE|BAH[ÍI]A|CORDILLERA|R[ÍI]O|"
    r"VALLE|LAGUNA|FUENTE|PROMONTORIO|PEÑ[ÓO]N|ENSENADA|"
    r"ESTERO|CAYO|BAJO|ARRECIFE|FONDEADERO|SURGIDERO|FARO|"
    r"BANCO|MORRO|GOLFO|ESTRECHO|PASO|ARCHIPI[ÉE]LAGO|"
    r"PEN[ÍI]NSULA|EMBALSE|TORRENTE|RAMBLA|COLLADO|PUEYO)\b",
    re.I,
)

# Place-type abbreviation immediately after the lemma's `.—` — used
# when the lemma itself doesn't lead with a geographic word. Riera's
# 19th-century shorthand for ADMINISTRATIVE settlement types.
ADMIN_PLACE_TYPE_RE = re.compile(
    r"\.\s*[—\-~]+\s*(V|L|C|B|Ald|Aid|Cas|Cot|Cor|Felig|Desp|"
    r"Ayunt|Villa|Ciudad|Granja|Aldea|Lugar|Coto|Caser[ií]o|"
    r"Cuart[oó]n|Pueblo|Barrio|Departamento|Anteiglesia)\.?",
    re.I,
)

# Balearic toponym references — used by the geographic and unknown
# branches. The narrower contextual patterns in the previous draft
# missed too many real entries (e.g. 'costa SO. de la prov. de
# Mallorca' for capes, or 'separada de Ibiza' for the islands).
# Geographic entries are short and explicit; any mention of the seven
# Balearic identifiers is meaningful, modulo the 'Cabrera' homonym
# (the León arciprestat). We exclude bare 'Cabrera' from this list
# and only accept 'isla de Cabrera' or 'Cabrera (Baleares)'.
BALEARIC_GEO_RE = re.compile(
    r"\b(?:mallorca|menorca|ibiza|iviza|eivissa|formentera|"
    r"isla\s+de\s+cabrera|"
    r"bale[aà]res?|bale[aà]ric|bale[aà]riques|"
    r"mah[oó]n|ciudadela|ciutadella|cindadela)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Top-level: parse a whole body into sections (administrative) or
# extract geographic-classification facts (geographic)
# ---------------------------------------------------------------------------


@dataclass
class ParsedEntry:
    kind: str = "unknown"            # 'administrative' | 'geographic' | 'unknown'
    head: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    fields: dict[str, dict] = field(default_factory=dict)
    coverage: int = 0                # 9-section coverage (admin only)
    body_balearic_refs: int = 0      # geographic discriminator
    body_excerpt: str = ""           # for debug / display
    lemma_in_body: bool = False      # NGIB-rescue guard signal

    def get_provincia(self) -> Optional[str]:
        """Return the province from whichever source has it. Field-level
        body-wide capture wins over section-level (the body-wide regex
        is more permissive for OCR-broken sections)."""
        return (
            self.fields.get("provincia")
            or (self.fields.get("org_civ") or {}).get("provincia")
        )

    def get_diocesis(self) -> Optional[str]:
        return (
            self.fields.get("diocesis")
            or (self.fields.get("org_ecles") or {}).get("diocesis")
        )

    def is_balearic(self, ngib_balearic: bool = False) -> bool:
        """Determined by Riera's own self-declaration in the body.

        Signal priority (highest first):
          1. provincia == 'baleares'           → accept
          2. provincia ∈ peninsular set        → reject
          3. diocesis  ∈ Balearic set          → accept
          4. diocesis  ∈ peninsular set        → reject
          5. geographic / unknown + ≥1 Balearic toponym in head → accept
          6. ngib_balearic flag                → accept (lemma rescue)
          7. otherwise                         → reject

        Steps 2 and 4 are the negative-evidence guards that prevent
        body-extraction failures from smuggling peninsular content
        in via the lemma-level NGIB rescue."""
        prov = self.get_provincia()
        if prov == "baleares":
            return True
        if prov and prov in _PROV_NON_BAL_SET:
            return False
        dioc = self.get_diocesis()
        if dioc and any(
            dioc.startswith(d)
            for d in ("mallorca", "menorca", "ibiza", "iviza",
                      "malloeca", "menorea")
        ):
            return True
        if dioc and dioc in _PEN_DIOCESE_SET:
            return False
        if self.kind in ("geographic", "unknown"):
            if self.body_balearic_refs >= 1:
                return True
        if ngib_balearic:
            # NGIB lemma rescue — accept when one of the following:
            #   (a) body extraction returned nothing (extraction
            #       failure → trust NGIB).
            #   (b) body is a cross-reference ('Véase X').
            #   (c) body has Riera structural signal (kind != unknown:
            #       admin sections or geographic-type opener).
            #   (d) the lemma reappears inside the body — proof that
            #       the article text is ABOUT the place the lemma
            #       names. Statistical tables like 'ANDRAIX, EN 1883'
            #       qualify; Cuban body bleed about Guanajal / hatos
            #       de Camarai does not (lemma never reappears).
            # Reject otherwise: kind=unknown + non-trivial body + no
            # lemma reappearance is almost always body bleed.
            body = (self.head or "").strip()
            if len(body) < 50:
                return True
            if "véase" in body.lower()[:80] or "veasee" in body.lower()[:80]:
                return True
            if self.kind != "unknown":
                return True
            if self.lemma_in_body:
                return True
            return False
        return False

    def diagnosis(self) -> str:
        prov = self.get_provincia()
        dioc = self.get_diocesis()
        hab = (self.fields.get("poblacion") or {}).get("habitantes")
        return (f"[{self.kind[:3]}] prov={prov or '?':<10} "
                f"dioc={dioc or '?':<10} hab={hab if hab is not None else '?':>6}  "
                f"refs={self.body_balearic_refs}  cov={self.coverage}")


def _find_markers(body: str) -> list[tuple[int, int, str]]:
    """Return [(start, end, section_name)] for every section marker
    found in body, sorted by start. Each marker name is unique — if
    the same section appears twice (rare; usually OCR noise) we keep
    only the first."""
    raw: list[tuple[int, int, str]] = []
    for name, pat in SECTION_PATTERNS:
        for m in pat.finditer(body):
            raw.append((m.start(), m.end(), name))
    raw.sort()
    # Deduplicate by name, keeping the first occurrence.
    seen: set[str] = set()
    out: list[tuple[int, int, str]] = []
    for start, end, name in raw:
        if name in seen:
            continue
        seen.add(name)
        out.append((start, end, name))
    return out


_SECTION_FIELD_PARSERS = {
    "org_civ": parse_org_civ,
    "org_ecles": parse_org_ecles,
    "org_judicial": parse_org_judicial,
    "poblacion": parse_poblacion,
}


def _classify_kind(lemma: str, body: str) -> str:
    """Decide whether to parse the body as administrative (9-section
    template) or geographic (free prose).

    Signal hierarchy:
      1. Lemma starts with a geographic-type word (CABO, ISLA, …) →
         geographic. Reliable, since Riera ALWAYS leads such entries
         with the type word.
      2. Body contains a place-type abbreviation '.—V.', '.—L.',
         '.—C.' etc. within the first 200 chars → administrative.
         This is the canonical opener of a settlement article.
      3. Body contains any Org. section marker → administrative.
      4. Otherwise unknown.
    """
    if lemma and GEOGRAPHIC_LEMMA_PREFIX_RE.match(lemma):
        return "geographic"
    if ADMIN_PLACE_TYPE_RE.search(body[:200]):
        return "administrative"
    # If even one Org. <subfield> marker exists, treat as admin
    for _, pat in SECTION_PATTERNS:
        if pat.search(body):
            return "administrative"
    return "unknown"


def parse_entry(body: str, lemma: str = "") -> ParsedEntry:
    """Parse a Riera entry body into structured fields, taking the
    cleanest path available:

      1. Hyphen-line-wraps are stitched first (OCR artefact).
      2. Body-wide regexes pick up 'prov. de X' and 'dióc. de X'
         regardless of whether the OCR preserved a clean Org. civ. /
         Org. ecles. section marker. This is the single most robust
         classification signal we have — present in admin entries
         (Riera writes 'Corresponde á la prov. de Baleares'), present
         in Tom XII Catalan-additional entries (which often skip the
         Org. structure but keep 'Dióc. de Mallorca'), and absent
         from purely geographic articles (where the kind dispatcher
         catches up via balearic-toponym density).
      3. Administrative entries additionally get full section parsing
         so the LLM-extracted JSON downstream can be cross-validated.

    The classification logic in is_balearic() reads BOTH the body-
    level fields and the section-level fields, so misclassified
    'kind' values don't lose information."""
    body = _unwrap_hyphens(body)
    entry = ParsedEntry()
    entry.kind = _classify_kind(lemma, body)
    entry.body_excerpt = body[:120].replace("\n", " ")
    entry.head = body
    # Does the lemma appear in the body text? Used by NGIB rescue to
    # discriminate genuine extraction (where the article text repeats
    # the lemma, e.g. in statistical-table headings 'PORLA ADUANA DE
    # ANDRAIX, EN 1883') from body-bleed (Cuban entry whose body
    # never mentions the would-be Balearic lemma at all).
    if lemma:
        lk = _strip_accents_lower(re.sub(r"\s+", " ", lemma)).strip()
        # Strip noise: the parenthetical territory marker '(Baleares)'
        # and the prefix ALL-CAPS word that's the same as the
        # opener — what we want is the SECOND occurrence of the
        # lemma's stem in body prose.
        lk_main = re.split(r"\s*\(", lk, maxsplit=1)[0].strip()
        if lk_main and len(lk_main) >= 3:
            body_norm = _strip_accents_lower(body)
            # The opener line is excluded from `body` by the extractor
            # (lines start at i+1), so any occurrence here is the
            # article's prose actually mentioning its own toponym —
            # the discriminating signal vs body bleed from an unrelated
            # article that doesn't repeat the lemma. We also check a
            # no-whitespace variant so Riera's spaced-glyph emphasis
            # ('A N D R A I X' in a stat-table heading) still counts.
            body_no_ws = re.sub(r"\s+", "", body_norm)
            lemma_no_ws = re.sub(r"\s+", "", lk_main)
            if (body_norm.count(lk_main) >= 1
                    or (len(lemma_no_ws) >= 5
                        and body_no_ws.count(lemma_no_ws) >= 1)):
                entry.lemma_in_body = True

    # Body-wide field extraction — works for any entry shape.
    pm = _PROV_RE.search(body)
    if pm:
        entry.fields["provincia"] = _clean_province(pm.group(1))
    dm = _DIOC_RE.search(body)
    if dm:
        dioc_raw = _strip_accents_lower(dm.group(1).strip(" .,;:"))
        # Reject common Spanish stopwords captured as diocese
        # ('dióc. que se halla situado…' → 'que'; 'dióc. de la pro-
        # vincia' → 'la'). Only proper-name captures are kept.
        if dioc_raw not in _DIOCESE_STOPWORDS and len(dioc_raw) >= 3:
            entry.fields["diocesis"] = dioc_raw
    # Balearic-toponym density — relevant for geographic / unknown
    # entries that lack any explicit province assignment.
    entry.body_balearic_refs = len(BALEARIC_GEO_RE.findall(body[:1500]))

    # Administrative branch: section-level parsing on top.
    if entry.kind == "administrative":
        markers = _find_markers(body)
        if markers:
            entry.head = body[: markers[0][0]].strip()
            for i, (start, end, name) in enumerate(markers):
                next_start = (markers[i + 1][0]
                              if i + 1 < len(markers) else len(body))
                section_text = body[end:next_start].strip()
                entry.sections[name] = section_text
                parser = _SECTION_FIELD_PARSERS.get(name)
                if parser:
                    entry.fields[name] = parser(section_text)
            entry.coverage = len(entry.sections)
    return entry


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def _smoke_test() -> None:
    """Re-parse every body in data/index/*.jsonl with the new
    section/geographic parser and report what it sees vs the current
    classifier."""
    PROJECT = Path(__file__).resolve().parent.parent
    INDEX_DIR = PROJECT / "data" / "index"
    import sys as _s; _s.path.insert(0, str(PROJECT / "scripts"))
    from index_volume import extract_body_pdftotext  # type: ignore
    import json as _j
    n = bal = pen = unclass = 0
    by_kind: dict[str, int] = {}
    misc: list[tuple[str, int, str, str, str]] = []
    for f in sorted(INDEX_DIR.glob("tomo*.jsonl")):
        for line in f.read_text().splitlines():
            e = _j.loads(line)
            body = extract_body_pdftotext(
                {"page": int(e["page"]), "lemma": e["lemma"]}, e["vol"]
            )
            parsed = parse_entry(body, lemma=e["lemma"])
            n += 1
            by_kind[parsed.kind] = by_kind.get(parsed.kind, 0) + 1
            if parsed.is_balearic():
                bal += 1
            else:
                prov = (parsed.fields.get("org_civ") or {}).get("provincia")
                if prov and prov != "baleares":
                    pen += 1
                    misc.append((e["vol"], int(e["page"]), e["lemma"],
                                 parsed.kind, prov))
                else:
                    unclass += 1
                    misc.append((e["vol"], int(e["page"]), e["lemma"],
                                 parsed.kind,
                                 f"refs={parsed.body_balearic_refs}"))
    print(f"\nTotal reanalysed:  {n}")
    print(f"  by kind: " + ", ".join(f"{k}={v}" for k, v in by_kind.items()))
    print(f"\nBalearic (new parser):                    {bal}")
    print(f"Self-declared peninsular (parser rejects): {pen}")
    print(f"Unclassified (no signal either way):       {unclass}")
    if misc:
        print(f"\nEntries indexed but parser now rejects "
              f"({len(misc)} total):")
        for v, p, lm, kind, why in misc[:60]:
            print(f"  tom{v} p{p:>4}  [{kind:<14}] "
                  f"{lm[:36]:<36}  {why}")
        if len(misc) > 60:
            print(f"  … and {len(misc) - 60} more")


if __name__ == "__main__":
    _smoke_test()
