"""Phase 3 — LLM extraction of structured Balearic articles from Riera.

Adapted from ``../minano/scripts/extract_text.py``. The source of
truth is ``data/index/tomo<vol>.jsonl`` (the indent-detected Balearic
entries) plus PyMuPDF for body text retrieval.

Key differences from the minano extractor:

- Source format: PDF + indent, not Internet Archive chOCR. We use
  PyMuPDF to grab the text BETWEEN two consecutive openers (the
  current entry's opener and the next opener anywhere in the volume).
- No leaf-vs-printed-page distinction: addressing is (vol, page) where
  `page` is the 1-based PDF page index of the opener line.
- Schema reflects Riera's 1881 administrative template rather than
  Miñano's 1826 vocabulary: drops `seigneurial_regime` and
  `mayor_type` (abolished by 1837), adds the nine-section structure
  (org_judicial, org_civil, org_militar, org_economica,
  org_eclesiastica, servicio_publico, obras_publicas,
  instruccion_publica, poblacion, industria, geografia).

Output: ``data/text/page_<vol>_<page>.json`` — one file per (vol,
page) combination. Multiple entries on the same page produce a single
file with a list of entries.

Requires ``ANTHROPIC_API_KEY`` in env (loaded from .env).

Modes:
  --page VOL PAGE       extract a single page (testing)
  --sample VOL          run on a 3-entry curated sample
  --vol VOL             process every Balearic entry in one volume
  --all                 process all 133 Balearic entries

Output: ``data/text/page_<vol>_<page>.json`` — one file per (vol, page).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import unicodedata

import anthropic
import pymupdf
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


PROJECT = Path(__file__).resolve().parent.parent
PDF_DIR = PROJECT / "data" / "pdf"
INDEX_DIR = PROJECT / "data" / "index"
OUT_DIR = PROJECT / "data" / "text"

DEFAULT_MODEL = "claude-opus-4-7"
MODEL_PRICING = {
    "claude-opus-4-7":           {"in": 15.00, "out": 75.00},
    "claude-sonnet-4-6":         {"in": 3.00,  "out": 15.00},
    "claude-haiku-4-5-20251001": {"in": 1.00,  "out": 5.00},
}

# ---------- Body extraction via PyMuPDF (re-uses index_volume logic) -------

from collections import Counter

Y_MIN, Y_MAX = 60, 780


def _find_column_baselines(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return (0.0, 0.0)
    counter = Counter(round(x) for x in xs)
    sorted_bins = counter.most_common()
    primary = sorted_bins[0][0]
    secondary = None
    for v, _ in sorted_bins[1:]:
        if abs(v - primary) >= 80:
            secondary = v
            break
    if secondary is None:
        return (float(primary), float(primary))
    left, right = sorted((primary, secondary))
    return (float(left), float(right))


def _page_lines(page) -> list[tuple[float, float, str]]:
    d = page.get_text("dict")
    out: list[tuple[float, float, str]] = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            if not ln["spans"]:
                continue
            x0 = ln["spans"][0]["bbox"][0]
            y0 = ln["spans"][0]["bbox"][1]
            if y0 < Y_MIN or y0 > Y_MAX:
                continue
            text = "".join(s["text"] for s in ln["spans"]).rstrip()
            if text:
                out.append((x0, y0, text))
    return out


def _column_of(x0: float, page_width: float, lines: list[tuple[float, float, str]]) -> str:
    bl, br = _find_column_baselines([x for x, _, _ in lines])
    split = (bl + br) / 2 if br > bl else page_width / 2
    return "L" if x0 < split else "R"


def extract_body_text(pdf_path: Path,
                       opener_page: int,
                       opener_lemma: str,
                       next_opener_page: int | None,
                       next_opener_lemma: str | None,
                       max_lines: int = 200) -> str:
    """Return the body text of one entry, from the opener (exclusive)
    to the next opener (exclusive) or `max_lines` whichever comes first.

    Opener identification uses fuzzy matching: the raw OCR line often
    differs from the cleaned lemma in OCR-confusion characters (1↔I,
    l↔I, 0↔O), so a strict-prefix compare misses entries like
    FERRER1AS vs FERRERIAS. We compare normalised forms (caps,
    1→I, accent-stripped) and accept any ratio ≥ 85."""
    from rapidfuzz import fuzz
    doc = pymupdf.open(str(pdf_path))
    out: list[str] = []
    started = False

    def _normalize_lemma(s: str) -> str:
        s = strip_accents(s).upper()
        s = re.sub(r"[1l](?=[A-Z]|$|\b)", "I", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def is_opener(text: str, lemma: str) -> bool:
        # Strip the body that follows '.—' / '. —' so we compare lemmas only.
        head_text = re.split(r"\.\s*[—\-]", text, maxsplit=1)[0]
        head_text_n = _normalize_lemma(head_text)
        head_lemma_n = _normalize_lemma(lemma)
        if not head_text_n or not head_lemma_n:
            return False
        # First test: prefix match on normalised forms (cheap, ≥99% of cases).
        if head_text_n.startswith(head_lemma_n[:8]):
            return True
        # Fallback: fuzzy ratio over the whole lemma (handles OCR
        # confusions deeper than the first 8 chars, e.g. mid-word
        # 1→I that prefix-startswith might also tolerate — kept as a
        # safety net for spelling variants).
        return fuzz.ratio(head_text_n[:len(head_lemma_n) + 2],
                          head_lemma_n) >= 85

    end_page = next_opener_page or doc.page_count
    for pn in range(opener_page - 1, min(doc.page_count, end_page + 1)):
        page = doc[pn]
        page_lines = _page_lines(page)
        if not page_lines:
            continue
        bl, br = _find_column_baselines([x for x, _, _ in page_lines])
        split = (bl + br) / 2 if br > bl else page.rect.width / 2
        # Sort by column then y0
        page_lines.sort(key=lambda l: ("L" if l[0] < split else "R", l[1]))
        for x0, y0, text in page_lines:
            col = "L" if x0 < split else "R"
            # Have we started collecting yet?
            if not started:
                if pn + 1 == opener_page and is_opener(text, opener_lemma):
                    started = True
                continue
            # Are we at the next opener?
            if next_opener_lemma and pn + 1 == end_page and is_opener(
                    text, next_opener_lemma):
                return "\n".join(out)
            out.append(text)
            if len(out) >= max_lines:
                return "\n".join(out)
        if pn + 1 >= (end_page or doc.page_count):
            break
    return "\n".join(out)


# ---------- Index loading -------------------------------------------------


def load_index(vol: str) -> list[dict]:
    p = INDEX_DIR / f"tomo{vol}.jsonl"
    if not p.exists():
        raise FileNotFoundError(
            f"Missing {p}. Run scripts/index_volume.py {vol} first."
        )
    return [json.loads(l) for l in p.open()]


def all_balearic_entries() -> list[dict]:
    """Return every Balearic entry across all 12 vols, sorted by (vol, page)."""
    out: list[dict] = []
    for n in range(1, 13):
        vol = f"{n:02d}"
        p = INDEX_DIR / f"tomo{vol}.jsonl"
        if p.exists():
            out.extend(json.loads(l) for l in p.open())
    out.sort(key=lambda e: (e["vol"], e["page"]))
    return out


# ---------- Tool schema (Riera-specific) ----------------------------------

ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": (
                "Cleaned canonical title as printed by Riera, in ALL "
                "CAPS, with any parenthetical specifier preserved "
                "(e.g. 'BINISALEM', 'CABO FORMENTOR', 'ISLA DE "
                "MENORCA'). Repair obvious OCR damage (1→I, l→I) but "
                "keep Riera's 1881 Castilianised orthography "
                "('BANALBUFAR', 'BUÑOLA', 'CIUDADELA') — do NOT "
                "modernise to current Catalan toponyms."
            ),
        },
        "place_type": {
            "type": "string",
            "description": (
                "Spanish lemma for the entry type, lowercase. Riera "
                "abbreviations: V.=villa, L.=lugar, C.=ciudad, "
                "B.=barrio, Ald.=aldea, Cas.=caserío, Cot.=coto, "
                "Cor.=corregimiento, Felig.=feligresía, "
                "Desp.=despoblado. For natural features use the noun "
                "directly ('cabo', 'isla', 'cala', 'punta', 'sierra', "
                "'puerto', 'bahía', 'monte', 'río', 'arroyo')."
            ),
        },
        "island": {
            "type": "string",
            "enum": ["Mallorca", "Menorca", "Ibiza", "Formentera",
                     "Cabrera", "Baleares"],
            "description": (
                "Balearic island the entry belongs to. Use 'Baleares' "
                "for province-wide entries (the BALEARES article in "
                "tom II). Use 'Ibiza' for Riera's spelling (he writes "
                "'Ibiza' not 'Iviza'). The four major islands plus "
                "Cabrera; islets fall under their major island."
            ),
        },
        "municipality": {
            "type": "string",
            "description": (
                "The modern municipality this entry depends on for "
                "civil administration. For VILLES/CIUTATS that are "
                "themselves municipalities (Alaró, Algaida, Calvià, "
                "Manacor, Ciudadela…) put the modern Catalan form "
                "here. For agregados (lugares, aldeas, barrios) put "
                "the parent ayuntamiento (Llombarts → Santanyí, "
                "Ariany → Petra, Llorito → Sineu). For supramunicipal "
                "entities (the whole province article, an island "
                "summary, capes outside any municipi) leave null."
            ),
        },
        "org_judicial": {
            "type": "string",
            "description": (
                "Verbatim or paraphrased content of the 'Organización "
                "judicial' section: partido judicial, audiencia "
                "territorial and the distances Riera reports."
            ),
        },
        "org_civil": {
            "type": "string",
            "description": (
                "'Organización civil' section: gobierno civil, "
                "provincia and the distances. Also any guardia civil "
                "post mentioned."
            ),
        },
        "org_militar": {
            "type": "string",
            "description": (
                "'Organización militar' section: capitanía general "
                "(C. G. de las Baleares) and gobierno militar."
            ),
        },
        "org_economica": {
            "type": "string",
            "description": (
                "'Organización económica' section: administración "
                "económica, contribuciones, presupuesto municipal "
                "(when stated)."
            ),
        },
        "org_eclesiastica": {
            "type": "string",
            "description": (
                "'Organización eclesiástica' section: diócesis, "
                "parroquia, advocación, número y nombramiento de "
                "curas, ermitas, conventos."
            ),
        },
        "servicio_publico": {
            "type": "string",
            "description": (
                "'Servicio público' section: estafetas, conducciones "
                "de correo, carterías, estaciones de ferrocarril o "
                "telégrafo."
            ),
        },
        "obras_publicas": {
            "type": "string",
            "description": (
                "'Obras públicas y medios de comunicación' section: "
                "carreteras, caminos vecinales, ferrocarril, puerto."
            ),
        },
        "instruccion_publica": {
            "type": "string",
            "description": (
                "'Instrucción pública' section: número y tipo de "
                "escuelas, alumnos. Often very short."
            ),
        },
        "poblacion": {
            "type": "string",
            "description": (
                "'Población' section: casas, pisos, calles, plazas, "
                "edificios notables."
            ),
        },
        "industria": {
            "type": "string",
            "description": (
                "'Artes, oficios, industria' section: agricultura, "
                "molinos, fábricas, talleres, oficios mecánicos."
            ),
        },
        "geografia": {
            "type": "string",
            "description": (
                "'Situación geográfica y topográfica' section: "
                "ubicación, clima, orografía, hidrografía, límites, "
                "producciones agrícolas, latitud/longitud cuando se "
                "indican."
            ),
        },
        "description": {
            "type": "string",
            "description": (
                "Residual prose Riera occasionally adds: historical "
                "notes, anecdotes, biographies of distinguished sons. "
                "For SHORT geographic entries (capes, islets, "
                "harbours) where there's NO administrative template, "
                "put the complete body here and leave the section "
                "fields null."
            ),
        },
        "stats": {
            "type": "object",
            "description": (
                "Population & infrastructure figures Riera inlines in "
                "the body. Keys: 'habitantes' (souls; Riera uses 1877 "
                "census), 'edificios' (total buildings), 'viviendas' "
                "(habitable), 'albergues' (uninhabitable shelters), "
                "'caserios_y_grupos' (hamlets aggregated), 'contr_"
                "territorial' (territorial tax, in pts.), 'contr_"
                "subsidio' (subsidio industrial), 'presupuesto_"
                "municipal'. For ambiguous OCR digits set the field "
                "but mark confidence 'low'."
            ),
            "additionalProperties": True,
        },
        "cross_references": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Other Riera entries this one points to via 'Véase X' "
                "or 'V. X' or '(V. su artículo)'. Empty array if none."
            ),
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": (
                "Your confidence in the structured fields given the "
                "input is OCR text. 'low' when OCR garbled key fields; "
                "'medium' for moderate ambiguity especially numerics; "
                "'high' for clean extraction."
            ),
        },
    },
    "required": ["title", "island", "confidence"],
    "additionalProperties": False,
}

TOOL = {
    "name": "record_page_entries",
    "description": (
        "Record every Balearic Riera dictionary entry whose TITLE "
        "appears on the target page. One call with the full list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "items": ENTRY_SCHEMA,
                "description": "All Balearic entries titled on the target page.",
            },
        },
        "required": ["entries"],
    },
}

SYSTEM_PROMPT = """\
You extract structured records from OCR'd text of Pablo Riera y Sans'
"Diccionario geográfico, estadístico, histórico, biográfico, postal,
municipal, marítimo y eclesiástico de España y sus posesiones de
ultramar" (Barcelona, 1881-1887, 12 vols.). The OCR is from a
PDF-embedded text layer (PDFlib+PDI 8.0.0, ~2017) over a 19th-century
two-column letterpress facsimile served by the Biblioteca Digital de
Castilla y León. The text layer is reasonably clean for a 19th-century
source but expect: mangled digits (1↔i↔l), broken accents, glued or
split words ('lapob.' → 'la pob.', 'admon.econ.' → 'admon. econ.'),
stray glyphs, and column-edge OCR confusions.

We care ONLY about Balearic entries — those whose geographic context
names Mallorca, Menorca, Ibiza, Eivissa, Formentera or Cabrera (the
islet south of Mallorca, NOT the peninsular Sierra de Cabrera in
León/Almería). Reject non-Balearic entries that share the page.

Each Riera entry begins with a TITLE in ALL CAPS followed by '.—' and
the place-type abbreviation (V.=villa, L.=lugar, C.=ciudad,
B.=barrio, Ald.=aldea, Cas.=caserío). Riera then uses a nine-section
administrative template:

  Organización judicial    — partido judicial, audiencia territorial
  Organización civil       — gobierno civil, provincia
  Organización militar     — capitanía general, gobierno militar
  Organización económica   — administración de hacienda
  Organización eclesiástica — diócesis, parroquia, advocación
  Servicio público         — correos, estaciones, telégrafo
  Obras públicas y medios… — caminos, carreteras, ferrocarril
  Instrucción pública      — escuelas, alumnos
  Población                — casas, calles, edificios notables
  Artes, oficios, industria — agricultura, molinos, fábricas, talleres
  Situación geográfica y topográfica — situación, clima, orografía,
                                       hidrografía, límites, producciones

A COMPACT form using abbreviations (Org. civ., Org. mil., Org. ecle.,
Org. jud., Org. econ., S. púb., Ob. púb. y med. de com., Ins. púb.,
Pob., Art., of. ind., Sit. geog. y top.) is common for shorter entries
(agregados, barrios). Both forms map to the same fields.

SHORT GEOGRAPHIC ENTRIES (the 13 cabos in tom III, the islotes, some
small calas) have NO administrative template — they are a single
paragraph describing position, coordinates, lighthouse, fondeadero.
For those, leave the section fields null and put the full body in
`description`.

Riera bases his demographic figures on the 1877 census (Instituto
Geográfico-Estadístico under General Ibáñez). The 'habitantes' figure
is what he reports. He often drops 'vecinos' (Madoz still used that).

Call the `record_page_entries` tool exactly once with the full list
of Balearic entries titled on this page.\
"""


# ---------- Extraction ----------------------------------------------------


def build_user_message(
    vol: str,
    page: int,
    page_entries: list[dict],
    body_text: str,
) -> str:
    titles_hint = "\n".join(f"  - {e['lemma']}" for e in page_entries)
    return (
        f"Volume tom {vol}, PDF page {page}.\n\n"
        f"Our indexer flagged these {len(page_entries)} Balearic "
        f"openers on this page (the lemma may carry OCR noise):\n"
        f"{titles_hint}\n\n"
        f"=== ARTICLE BODY (extracted from the indented opener through "
        f"the next opener) ===\n{body_text}\n\n"
        f"Extract every Balearic entry on this page. Include the full "
        f"body even if it spilled into the next page."
    )


def extract_page(
    client: anthropic.Anthropic,
    vol: str,
    page: int,
    page_entries: list[dict],
    all_entries_sorted: list[dict],
    model: str = DEFAULT_MODEL,
) -> dict:
    pdf_path = PDF_DIR / f"tomo{vol}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF missing: {pdf_path}")

    # Concatenate bodies of all entries on this page in document order.
    bodies = []
    for entry in page_entries:
        idx = all_entries_sorted.index(entry)
        nxt = all_entries_sorted[idx + 1] if idx + 1 < len(all_entries_sorted) else None
        nxt_page = nxt["page"] if nxt and nxt["vol"] == vol else None
        nxt_lemma = nxt["lemma"] if nxt and nxt["vol"] == vol else None
        bodies.append(
            f"--- Opener: {entry['lemma']} ---\n" +
            extract_body_text(pdf_path, entry["page"], entry["lemma"],
                              nxt_page, nxt_lemma)
        )
    body_text = "\n\n".join(bodies)

    user_text = build_user_message(vol, page, page_entries, body_text)
    msg = client.messages.create(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_page_entries"},
        messages=[{"role": "user", "content": user_text}],
    )

    payload = None
    for block in msg.content:
        if block.type == "tool_use" and block.name == "record_page_entries":
            payload = block.input
            break
    if payload is None:
        raise RuntimeError(
            f"Model did not call the expected tool. blocks: "
            f"{[b.type for b in msg.content]}"
        )

    return {
        "vol": vol, "page": page, "model": model,
        "usage": {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        },
        "entries": payload["entries"],
        "source_text": body_text,
    }


# ---------- CLI -----------------------------------------------------------


def pick_sample(vol: str, entries_in_vol: list[dict]) -> list[int]:
    """Pick 3 diverse pages: multi-entry, short-body, long-body."""
    by_page: dict[int, list[dict]] = defaultdict(list)
    for e in entries_in_vol:
        by_page[e["page"]].append(e)
    if not by_page:
        return []
    pages = sorted(by_page)
    chosen = []
    # Multi-entry page
    multi = [p for p in pages if len(by_page[p]) >= 2]
    if multi:
        chosen.append(multi[0])
    # Short-body page (≤ 20 body lines)
    for p in pages:
        if p in chosen:
            continue
        if any(e["body_lines"] < 20 for e in by_page[p]):
            chosen.append(p)
            break
    # Backfill from the head
    for p in pages:
        if p in chosen:
            continue
        chosen.append(p)
        if len(chosen) >= 3:
            break
    return chosen[:3]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_mutually_exclusive_group(required=True)
    sub.add_argument("--page", nargs=2, metavar=("VOL", "PAGE"),
                     help="extract one page (e.g. --page 03 4811)")
    sub.add_argument("--sample", metavar="VOL",
                     help="run on a 3-page curated sample of one tomo")
    sub.add_argument("--vol", metavar="VOL",
                     help="process every Balearic entry in one volume")
    sub.add_argument("--all", action="store_true",
                     help="process all 133 Balearic entries across the 12 vols")
    ap.add_argument("--overwrite", action="store_true",
                    help="re-extract pages even if their JSON already exists")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    choices=list(MODEL_PRICING),
                    help=f"model to use (default {DEFAULT_MODEL})")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set (or .env missing).")
    client = anthropic.Anthropic()

    all_entries = all_balearic_entries()
    if not all_entries:
        sys.exit("No indexed entries found. Run scripts/index_volume.py --all first.")

    if args.page:
        vol = args.page[0].zfill(2)
        page = int(args.page[1])
        page_entries = [e for e in all_entries if e["vol"] == vol and e["page"] == page]
        if not page_entries:
            sys.exit(f"No entries at vol={vol}, page={page}")
        groups = [(vol, page, page_entries)]
    elif args.sample:
        vol = args.sample.zfill(2)
        in_vol = [e for e in all_entries if e["vol"] == vol]
        if not in_vol:
            sys.exit(f"No Balearic entries in tom {vol}")
        sample_pages = pick_sample(vol, in_vol)
        print(f"Sample for tom {vol}: pages {sample_pages}")
        groups = []
        for p in sample_pages:
            pe = [e for e in in_vol if e["page"] == p]
            groups.append((vol, p, pe))
    elif args.vol:
        vol = args.vol.zfill(2)
        in_vol = [e for e in all_entries if e["vol"] == vol]
        by_page: dict[int, list[dict]] = defaultdict(list)
        for e in in_vol:
            by_page[e["page"]].append(e)
        groups = [(vol, p, by_page[p]) for p in sorted(by_page)]
    else:
        by_page: dict[tuple[str, int], list[dict]] = defaultdict(list)
        for e in all_entries:
            by_page[(e["vol"], e["page"])].append(e)
        groups = [(vol, p, by_page[(vol, p)]) for (vol, p) in sorted(by_page)]

    suffix = "" if args.model == DEFAULT_MODEL else f"_{args.model.split('-')[1]}"
    total_in = total_out = 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for vol, page, page_entries in groups:
        out_path = OUT_DIR / f"page_{vol}_{page}{suffix}.json"
        if out_path.exists() and not args.overwrite:
            print(f"  [skip] {out_path.name} already exists")
            continue
        try:
            titles = ", ".join(e["lemma"] for e in page_entries)
            print(f"  [GET]  tom{vol} p{page} ({titles[:60]}) [{args.model}]…", flush=True)
            result = extract_page(client, vol, page, page_entries,
                                   all_entries, model=args.model)
        except Exception as e:
            print(f"  [fail] tom{vol} p{page}: {e}", file=sys.stderr)
            continue
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        ti = result["usage"]["input_tokens"]
        to = result["usage"]["output_tokens"]
        total_in += ti
        total_out += to
        print(f"  [ok]   {out_path.name}: {len(result['entries'])} entries "
              f"(in={ti} out={to})")
        time.sleep(0.2)

    if total_in or total_out:
        rate = MODEL_PRICING[args.model]
        cost = total_in / 1_000_000 * rate["in"] + total_out / 1_000_000 * rate["out"]
        print()
        print(f"Tokens: in={total_in:,}  out={total_out:,}  ({args.model})")
        print(f"Estimated cost (non-batch): ${cost:.4f}")


if __name__ == "__main__":
    main()
