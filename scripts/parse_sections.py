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


# Recognise the captured 'province' token. We accept it as 'Baleares'
# when either:
#   • the accent-stripped lowercased prefix matches one of the common
#     OCR variants below — fast path, no library call.
#   • a fuzzy-match against the literal 'baleares' returns ≥85
#     similarity (rapidfuzz fuzz.ratio) — catches arbitrary OCR
#     garbles like 'Bnleares', 'Háleares', 'B aleares', 'Balares',
#     'Baleare' (truncation).
_BALEARES_PREFIXES = ("balear", "bsleare", "balsare", "baleare", "baleat")
_BALEARES_FUZZY_THRESHOLD = 82


def _is_baleares_token(token: str) -> bool:
    """True if `token` (already lowercased + accent-stripped) refers to
    Baleares despite OCR corruption."""
    if not token:
        return False
    if any(token.startswith(p) for p in _BALEARES_PREFIXES):
        return True
    # Fuzzy fallback for one-off OCR garbles. Skip very short captures
    # — a 3-char token has too few characters for fuzz.ratio to be
    # informative and risks false positives.
    if len(token) < 5:
        return False
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return False
    return fuzz.ratio(token, "baleares") >= _BALEARES_FUZZY_THRESHOLD


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
    if _is_baleares_token(norm):
        return "baleares"
    # Blacklist: when the regex anchors on the wrong token (Org. civ.
    # bleeding into a malformed prov. clause, or Filipino islands
    # captured by entries whose colonial-lemma marker was garbled by
    # OCR), the captured 'province' is nonsense. Treat as no match.
    first_word = norm.split(" ")[0] if norm else ""
    if first_word in _PROVINCE_BLACKLIST or norm in _PROVINCE_BLACKLIST:
        return ""
    return norm


# Two-stage province detection.
#
# PRIMARY: anchored on Riera's canonical 'Corresponde á la prov. de X'
# — this is the article's OWN admin self-declaration in the Org. civ.
# section. Settlements always carry it; supramunicipal / maritime
# department articles (like CARTAGENA) don't — so the regex
# correctly returns no match for them, even though their bodies may
# mention 'prov. de Mallorca' as part of describing what's under
# their jurisdiction.
_PROV_RE = re.compile(
    r"corresponde\s+[áa]?\s+(?:la\s+|al\s+)?"
    r"prov\.?(?:incia)?\s*\.?\s*\n?\s*"
    r"de\s+(?:la\s+|las\s+)?"
    r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ\s]{2,40})",
    re.I,
)
# FALLBACK: bare 'prov. de X' anywhere in the body. Used only when
# the primary anchor finds nothing — typical of agregats whose body
# skips the canonical 'Corresponde á' opener, or geographic entries
# that name a province in passing. Less reliable: catches whatever
# province appears first in the body.
_PROV_FALLBACK_RE = re.compile(
    r"\bprov\.?(?:incia)?\s*\.?\s*\n?\s*"
    r"de\s+(?:la\s+|las\s+)?"
    r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ\s]{2,40})",
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
    r"di[óo]c\.?(?:esis)?\s+(?:de\s+)?"
    # Capture up to two words so 'Ciudad Real' is kept as one token,
    # not truncated to 'Ciudad' (which would fuzzy-match 'Ciudadela').
    # Second word must be ≥3 chars to skip 1-char connectors ('y',
    # 'á') that follow a 1-word province name.
    r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]+(?:\s+[A-Za-záéíóúñÑÁÉÍÓÚüÜ]{3,})?)",
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

# Canonical Balearic toponyms / institutional locations. Each
# C-phrase below names one of these after its institution-anchor;
# fuzzy match against this set tolerates OCR corruption (Mallorea
# for Mallorca, Háleares for Baleares, Mahón → Mahon → Maion, etc.).
_BAL_LOCATIONS = (
    "baleares", "mallorca", "menorca", "ibiza", "iviza", "eivissa",
    "formentera", "cabrera", "palma", "mahon", "ciudadela",
    "ciutadella", "cindadela",
)
_BAL_FUZZY_THRESHOLD = 80


# Common OCR mangles of Balearic toponyms — explicit map so we don't
# rely on fuzzy match for known variants (and don't accidentally
# accept their peninsular near-twins like 'Ciudad Real' or 'Las
# Palmas' through over-generous fuzzy thresholds).
_BAL_OCR_VARIANTS = {
    "baleare", "balear", "baleat", "balsare", "bsleare",
    "mallorea", "malloeca", "mailorca",
    "menorea", "mahún", "mahán",
    "iviza",  # already in main set but kept for clarity
}


def _is_bal_location(token: str) -> bool:
    """True if `token` refers to a Balearic place despite OCR
    corruption.

    Three acceptance paths, in increasing permissiveness:
      1. Exact match against the canonical _BAL_LOCATIONS set.
      2. Exact match against a known OCR variant
         (_BAL_OCR_VARIANTS).
      3. Fuzzy match (rapidfuzz fuzz.ratio ≥ 85) — but ONLY for
         tokens ≥ 7 chars, to keep peninsular near-twins out:
         'ciudad' (6) vs 'ciudadela' (9) → 80, would be a false
         positive at the previous threshold of 80. Same for
         'palmas' (6) vs 'palma' (5). Forcing length ≥7 + threshold
         85 ensures the captured token is long enough that a true
         OCR variant of a Balearic toponym (length ≥7) clears it
         while peninsular shorter-name dioceses ('Ciudad', 'Palmas',
         'Pamplona', 'Vitoria') don't."""
    if not token:
        return False
    norm = _strip_accents_lower(token).strip()
    # Strip a leading Spanish article ('la', 'las', 'el', 'los') so
    # 'Dióc. de las Baleares' captured as 'las baleares' still matches.
    norm = re.sub(r"^(?:la|las|el|los)\s+", "", norm).strip()
    if not norm or len(norm) < 4:
        return False
    if norm in _BAL_LOCATIONS:
        return True
    if norm in _BAL_OCR_VARIANTS:
        return True
    if len(norm) < 7:
        return False
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        return False
    r = process.extractOne(norm, list(_BAL_LOCATIONS), scorer=fuzz.ratio)
    return bool(r and r[1] >= 85)


# C-phrases: each is a (label, regex) where the regex captures the
# LOCATION token immediately after the institution-anchor. The
# location is then fuzzy-matched against _BAL_LOCATIONS, so OCR
# garbles of either the location ('Mallorea', 'Pnlma', 'Haleares')
# or partial captures still register.
#
# The anchor itself is hard-regex because the institution name
# (capitanía general, audiencia, gobierno militar, etc.) is rarely
# OCR-corrupted — it's a frequent multi-word string with high
# redundancy. The fragile part is the toponym after it, which is
# where fuzzy match earns its keep.
_C_PHRASES = [
    ("C3a_C.G.",
     re.compile(r"\bC\.\s*G\.\s+de\s+(?:las\s+)?"
                r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]{4,20})", re.I)),
    ("C3b_capitania_general",
     re.compile(r"\bcapitan[ií]a\s+general\s+de\s+(?:las\s+)?"
                r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]{4,20})", re.I)),
    ("C4_audiencia",
     re.compile(r"\baudiencia\s+(?:territorial\s+)?de\s+"
                r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]{4,20})", re.I)),
    ("C5a_G.M.",
     re.compile(r"\bG\.\s*M\.\s+de\s+"
                r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]{4,20})", re.I)),
    ("C5b_gobierno_militar",
     re.compile(r"\bgobierno\s+militar\s+de\s+"
                r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]{4,20})", re.I)),
    ("C6_circunscripcion",
     re.compile(r"\bcircunscripci[óo]n\s+de\s+"
                r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]{4,20})", re.I)),
    ("C7_prov_maritima",
     re.compile(r"\bprov(?:incia)?\.?\s+mar(?:[ií]tima|\.)?\s+de\s+"
                r"([A-Za-záéíóúñÑÁÉÍÓÚüÜ]{4,20})", re.I)),
]


def _match_c_phrase(body: str) -> Optional[str]:
    """Scan body for any canonical Balearic admin-section phrase
    (C3-C7) and return the matching phrase's label, or None."""
    for label, pat in _C_PHRASES:
        for m in pat.finditer(body):
            if _is_bal_location(m.group(1)):
                return label
    return None


# Geographic-type prefix in the lemma. Restricted to the types that
# the exhaustive corpus scan confirmed do carry Balearic entries:
# CABO (16/54 balear), ISLA (6/32), ISLETA (3/5), ISLOTES (1/2). The
# other geographic types we considered (VALLE, FUENTE, ARROYO, PUERTO,
# MONTE, SIERRA, BAHÍA, CALA, PUNTA …) returned ZERO Balearic hits
# across all 12 tomes — so we don't include them, to avoid the risk
# of false positives from peninsular bodies that incidentally mention
# a Balearic toponym.
GEO_LEMMA_PREFIX_RE = re.compile(
    r"^\s*(CABO|CALA|ISLA|ISLAS|ISLOTE|ISLOTES|ISLETA|ISLETAS|"
    r"PUNTA|BAH[ÍI]A|PROMONTORIO)\b",
    re.I,
)

# Tokens that signal a Balearic toponym mention in the lemma or body
# of a geographic-accident article. Used by the geographic rule (G).
#
# RESTRICTIVE whitelist: only the seven Balearic identifiers that
# have NO peninsular or Canarian homonyms. Specifically EXCLUDED:
#
#   • 'Palma'      — Palma del Río (Córdoba), Palma de Gandía
#                    (Valencia), La Palma (Canàries) all share the
#                    name. ISLA DE PALMA (Canàries) would be a
#                    false positive.
#   • 'Cabrera'    — Sierra de Cabrera (León / Almería).
#   • 'Mahón'      — bare form is rare outside Balears but the
#                    anchor 'isla de Mahón' would be needed for
#                    safety; not worth the complexity for ~0 entries.
#   • 'Ciudadela'  — Cuban Ciudadela (Pinar del Río) exists.
#
# The seats Palma/Mahón/Ciudadela are still recognised inside the
# C-group anchors (Audiencia territorial de Palma, G. M. de Mahón,
# etc.) where the institution name carries the disambiguating
# context. For free-prose geographic bodies that lack such an
# anchor we need the unambiguous island names.
_BAL_BODY_REF_RE = re.compile(
    r"\b(mallorca|menorca|ibiza|iviza|eivissa|formentera|"
    r"bale[aà]res?|bale[aà]ric|bale[aà]riques|"
    r"malloeca|menorea|mailorca)\b",
    re.I,
)


def _has_geo_balearic_signal(lemma: str, body: str) -> bool:
    """Geographic entry (CABO, ISLA, ISLETA, …) — accepts when an
    unambiguous Balearic toponym appears in lemma or body[:600]."""
    if not GEO_LEMMA_PREFIX_RE.match(lemma or ""):
        return False
    haystack = (lemma or "") + " " + (body or "")[:600]
    return bool(_BAL_BODY_REF_RE.search(haystack))

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
    lemma: str = ""                  # original lemma — used by rule G

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
        """Decide if the article is Balearic.

        Single rule: ONE of the canonical Balearic admin-section
        phrases must appear in the body. No negative-evidence filters,
        no lemma-based gates, no body-bleed rescues. The C-group
        signals are by construction unambiguous — every Balearic
        settlement article carries at least one, no peninsular
        article carries any.

        Canonical phrases (any one suffices):
          1. 'Corresponde á la prov. de Baleares' (OCR-tolerant)
          2. 'Corresponde á la dióc. de [Mallorca|Menorca|Ibiza|
             Palma|Ciudadela]' (or OCR variants thereof)
          3. 'C. G. de [las] Baleares' / 'Capitanía General de
             [las] Baleares'
          4. 'Audiencia [territorial] de [Palma|Mallorca|Baleares]'
          5. 'G. M. de [Palma|Mahón|Ciudadela]' / 'Gobierno militar
             de [...]'
          6. 'circunscripción de Palma' (Cortes electoral district)
          7. 'prov. mar. de [Mallorca|Menorca|Ibiza|...]' (maritime
             province)

        `ngib_balearic` is accepted as a parameter but does NOT
        participate in the decision — it's consumed downstream as
        a confirmation audit alongside the boolean result."""
        # C1: prov. de Baleares (already fuzzy via _is_baleares_token
        # inside _clean_province → 'baleares' canonical)
        prov = self.get_provincia()
        if prov == "baleares":
            return True
        # C2: dióc. de [Balearic diocese / seat] — fuzzy match the
        # captured diocese name against _BAL_LOCATIONS.
        dioc = self.get_diocesis()
        if dioc and _is_bal_location(dioc):
            return True
        # C3-C7: any of the parallel admin-section phrases. The
        # _match_c_phrase scan runs each anchor regex + fuzzy location
        # check; first hit wins.
        if _match_c_phrase(self.head or ""):
            return True
        # G: geographic accident (CABO, CALA, ISLA, ISLOTE, ISLETA,
        # PUNTA, BAHÍA, PROMONTORIO) — lemma prefix anchors the type,
        # and an unambiguous Balearic island name must appear in
        # lemma or body[:600]. Restrictive whitelist (no Palma /
        # Cabrera / Mahón / Ciudadela) to avoid Canarian / peninsular
        # homonyms.
        if _has_geo_balearic_signal(self.lemma, self.head or ""):
            return True
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
    entry.lemma = lemma
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
