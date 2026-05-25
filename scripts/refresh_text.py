"""Sync data/text/page_*.json with the current data/index/*.jsonl.

Three sync operations:

  1. DELETE files for (vol, page) pairs no longer in the index.
  2. UPDATE files where the page is still in the index: keep entries
     whose title still matches an index lemma (preserve LLM-extracted
     rich content); drop entries whose lemma was rejected; ADD minimal
     entries for index lemmas not yet covered.
  3. CREATE files for (vol, page) pairs in the index but with no
     corresponding page_*.json.

The minimal entry for a NEW or unmatched lemma carries only the
fields the section parser can extract deterministically: title,
place_type (from body opener), island (from NGIB match), provincia,
diocesis, habitantes, edificios, plus a body excerpt as `description`.
The richer LLM-extracted fields stay empty for these entries until
they're re-extracted via subagent dispatch.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "scripts"))

from index_volume import extract_body_pdftotext, fuzzy_match, load_gazetteer  # type: ignore
from parse_sections import parse_entry, _strip_accents_lower  # type: ignore


INDEX_DIR = PROJECT / "data" / "index"
TEXT_DIR = PROJECT / "data" / "text"


PLACE_TYPE_MAP = {
    "V.": "villa", "L.": "lugar", "C.": "ciudad", "B.": "barrio",
    "Ald.": "aldea", "Aid.": "aldea", "Cas.": "caserío",
    "Cot.": "coto", "Cor.": "corral", "Felig.": "feligresía",
    "Desp.": "despoblado",
}
_PLACE_TYPE_RE = re.compile(
    r"[—~\-]\s*(V|L|C|B|Ald|Aid|Cas|Cot|Cor|Felig|Desp)\.", re.I
)
_GEO_TYPE_RE = re.compile(
    r"^\s*(CABO|CALA|ISLA|ISLOTE|ISLETA|PUNTA|PUERTO|SIERRA|MONTE|"
    r"BAH[ÍI]A|PROMONTORIO|ENSENADA|ESTERO|CAYO|BAJO|"
    r"FARO|BANCO|MORRO|GOLFO|ESTRECHO|PASO|ARCHIPI[ÉE]LAGO|"
    r"PEN[ÍI]NSULA|FUENTE)\b",
    re.I,
)


def _norm(s: str) -> str:
    """Title-comparable normalisation: strip accents, uppercase,
    drop parenthetical qualifiers, collapse internal whitespace."""
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn").upper()
    s = re.sub(r"\s*\([^)]*\).*$", "", s).strip()
    s = re.sub(r"[\.\-—~]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _detect_place_type(lemma: str, body: str) -> str | None:
    m = _GEO_TYPE_RE.match(lemma)
    if m:
        return m.group(1).lower()
    head = body[:200] if body else ""
    m = _PLACE_TYPE_RE.search(head)
    if m:
        abbr = m.group(1).rstrip(".") + "."
        return PLACE_TYPE_MAP.get(abbr) or PLACE_TYPE_MAP.get(abbr.lower())
    return None


def _minimal_entry(ix_entry: dict, body: str, choices, norm_list) -> dict:
    """Build a page-entry record from parser fields when no prior
    LLM extraction exists."""
    parsed = parse_entry(body, lemma=ix_entry["lemma"])
    poblacion = parsed.fields.get("poblacion") or {}
    island = None
    municipality = None
    if ix_entry.get("ngib"):
        island = ix_entry["ngib"].get("island")
        municipality = ix_entry["ngib"].get("municipality")
    # Body excerpt — first paragraph up to ~600 chars, for the web UI
    excerpt = (body or "").strip()
    excerpt = re.sub(r"\s+", " ", excerpt)[:600] if excerpt else None
    return {
        "title": ix_entry["lemma"],
        "place_type": _detect_place_type(ix_entry["lemma"], body),
        "island": island,
        "municipality": municipality,
        "org_judicial": None,
        "org_civil": (parsed.fields.get("org_civ") or {}).get("raw"),
        "org_militar": None,
        "org_economica": None,
        "org_eclesiastica": (parsed.fields.get("org_ecles") or {}).get("raw"),
        "servicio_publico": None,
        "obras_publicas": None,
        "instruccion_publica": None,
        "poblacion": (parsed.fields.get("poblacion") or {}).get("raw"),
        "industria": None,
        "geografia": None,
        "description": excerpt,
        "ocr_note": ("auto-generated from parser fields; "
                     "rich extraction pending LLM dispatch"),
        "stats": {
            "habitantes": poblacion.get("habitantes"),
            "edificios": poblacion.get("edificios"),
        } if (poblacion.get("habitantes") or poblacion.get("edificios")) else None,
        "cross_references": [],
        "confidence": "low",
    }


def main() -> None:
    # Index pages
    idx_by_page: dict[tuple[str, int], list[dict]] = {}
    for f in sorted(INDEX_DIR.glob("tomo*.jsonl")):
        for line in f.read_text().splitlines():
            e = json.loads(line)
            idx_by_page.setdefault((e["vol"], int(e["page"])), []).append(e)
    idx_pages = set(idx_by_page.keys())

    # Existing page_*.json files
    txt_files: dict[tuple[str, int], Path] = {}
    for f in sorted(TEXT_DIR.glob("page_*.json")):
        try:
            j = json.loads(f.read_text())
        except Exception:
            continue
        txt_files[(j["vol"], int(j["page"]))] = f
    txt_pages = set(txt_files.keys())

    print(f"Index pages: {len(idx_pages)} ({sum(len(v) for v in idx_by_page.values())} entries)")
    print(f"Text pages:  {len(txt_pages)}")

    # Delete pages not in index
    stale = txt_pages - idx_pages
    print(f"\nDeleting {len(stale)} stale page_*.json files…")
    for vp in stale:
        f = txt_files[vp]
        f.unlink()

    # NGIB choices for minimal-entry generation
    choices = load_gazetteer()
    norm_list = list(choices.keys())

    # Update or create each indexed page
    n_updated = n_created = n_added_entries = 0
    for vp, ix_entries in sorted(idx_by_page.items()):
        vol, page = vp
        out_path = TEXT_DIR / f"page_{vol}_{page}.json"
        existing = {}
        if vp in txt_files:
            existing = json.loads(txt_files[vp].read_text())
        existing_entries = existing.get("entries", [])
        # Map existing entries by normalised title for fast lookup
        existing_by_norm = {}
        for ee in existing_entries:
            existing_by_norm[_norm(ee.get("title") or "")] = ee
        new_entries = []
        used_ids: set[int] = set()
        for ix_e in ix_entries:
            norm_lemma = _norm(ix_e["lemma"])
            matched = None
            # Try exact normalised match
            if (norm_lemma in existing_by_norm
                    and id(existing_by_norm[norm_lemma]) not in used_ids):
                matched = existing_by_norm[norm_lemma]
            else:
                # Try prefix match (lemma truncated by OCR). Skip
                # candidates that were already assigned to a previous
                # ix_entry on this page — otherwise two index entries
                # like 'MENORCA' and 'MENORCA (Obispado de)' would
                # both grab the same existing page entry and the page
                # file ends up with two copies of the same content.
                for ek, ev in existing_by_norm.items():
                    if id(ev) in used_ids:
                        continue
                    if (norm_lemma and ek
                            and (norm_lemma.startswith(ek)
                                 or ek.startswith(norm_lemma))):
                        matched = ev
                        break
            if matched:
                used_ids.add(id(matched))
                # Deep-copy so that subsequent in-place edits to the
                # entry don't leak into other references (no shared
                # mutable state between different page-file slots).
                import copy
                matched_copy = copy.deepcopy(matched)
                matched_copy["title"] = ix_e["lemma"]
                new_entries.append(matched_copy)
            else:
                body = extract_body_pdftotext(
                    {"page": int(ix_e["page"]), "lemma": ix_e["lemma"]},
                    ix_e["vol"],
                )
                new_entries.append(_minimal_entry(ix_e, body, choices, norm_list))
                n_added_entries += 1
        payload = {
            "vol": vol,
            "page": page,
            "model": existing.get("model") or "section-parser+claude-max",
            "entries": new_entries,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        if vp in txt_files:
            n_updated += 1
        else:
            n_created += 1
    print(f"\nUpdated: {n_updated}  Created: {n_created}  "
          f"New minimal entries added: {n_added_entries}")


if __name__ == "__main__":
    main()
