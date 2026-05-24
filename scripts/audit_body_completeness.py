"""Body-completeness audit for the Balearic index.

For each entry in data/index/*.jsonl we re-extract its body from
pdftotext output and check for two pathologies:

  (1) **Truncation** — the body ends before the first sentence-final
      punctuation, suggesting the stopper fired too early or the
      lemma matched the wrong pdftotext line. A body whose first 200
      characters contain no '.', '?' or '!' is flagged as truncated.

  (2) **Bleed** — the body contains a line that is itself a Riera
      opener (CAPS prefix + .— + place-type abbreviation) at any
      position after the first 3 lines. This means the stopper failed
      to detect the next entry's opener and our body absorbed its
      content. Such bleed produces spurious anchor counts (the bled
      content's tokens get attributed to the wrong entry).

  (3) **Empty body** — body extraction returned the empty string
      entirely (lemma never matched a pdftotext line).

The output is a triage report grouped by pathology. No automated
fixes — the human reviewer decides which entries need re-extraction
or lemma normalisation.

Run:  python scripts/audit_body_completeness.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT / "data" / "index"

sys.path.insert(0, str(PROJECT / "scripts"))
from index_volume import extract_body_pdftotext, BALEARIC_TOKENS  # noqa: E402

# Same opener pattern as the body-extraction stopper. If we see this
# pattern inside our body, the stopper missed a real boundary.
_BLEED_OPENER_RE = re.compile(
    r"^(?:"
    r"[A-ZÁÉÍÓÚÑÜ]{2,}[A-ZÁÉÍÓÚÑÜ0-9'óòoáéíúñ\.\(\) \-]{0,50}"
    r"[\.\,]?\s*[—\-~]+\s*"
    r"(?:V\.|L\.|C\.|B\.|Ald\.|Aid\.|Cas\.|Cot\.|Cor\.|Felig\.|Desp\.)"
    r"|"
    r"(?:CABO|CALA|ISLA|ISLOTE|ISLETA|PUNTA|PUERTO|SIERRA|MONTE|"
    r"CASTILLO|BAH[ÍI]A|PROMONTORIO|ENSENADA|ESTERO|CAYO|BAJO|"
    r"FARO|BANCO|GOLFO|ESTRECHO|RIO|R[ÍI]O)\s+[A-ZÁÉÍÓÚÑÜ]"
    r")"
)

# Sentence-final punctuation marker — body must contain one in the
# first 200 chars or we suspect truncation.
_SENTENCE_END_RE = re.compile(r"[\.\?\!]")


def audit_entry(e: dict) -> dict:
    """Return findings for one indexed entry."""
    body = extract_body_pdftotext(
        {"page": int(e["page"]), "lemma": e["lemma"]},
        e["vol"],
        max_lines=80,
    )
    findings: list[str] = []
    if not body or not body.strip():
        findings.append("empty")
        return {"entry": e, "body": body, "findings": findings}
    # Pathology 1: truncation
    head_200 = body[:200]
    if not _SENTENCE_END_RE.search(head_200):
        findings.append("truncated")
    # Pathology 2: bleed — scan past the first 3 lines (the lemma
    # opener itself may legitimately appear at the top).
    body_lines = body.split("\n")
    for i, ln in enumerate(body_lines):
        if i < 3:
            continue
        if _BLEED_OPENER_RE.match(ln.lstrip()):
            findings.append(f"bleed@L{i}: {ln.strip()[:60]}")
            break
    # Anchor sanity: a body with only 1 anchor in a 40-line head and
    # high peninsular content is also suspicious — but this is the
    # peninsular audit's job, not ours.
    return {"entry": e, "body": body, "findings": findings}


def main() -> None:
    all_entries: list[dict] = []
    for f in sorted(INDEX_DIR.glob("tomo*.jsonl")):
        for line in f.read_text().splitlines():
            all_entries.append(json.loads(line))
    print(f"Auditing {len(all_entries)} indexed entries…\n")
    truncated: list[dict] = []
    bleed: list[dict] = []
    empty: list[dict] = []
    for e in all_entries:
        a = audit_entry(e)
        if "empty" in a["findings"]:
            empty.append(a)
        if "truncated" in a["findings"]:
            truncated.append(a)
        if any(f.startswith("bleed") for f in a["findings"]):
            bleed.append(a)

    def _print_section(title: str, items: list[dict]) -> None:
        print(f"\n=== {title}  ({len(items)} entries) ===")
        if not items:
            print("  (none)")
            return
        for a in items:
            e = a["entry"]
            print(f"  tom{e['vol']} p{e['page']:>4}  {e['lemma'][:36]:<36}  "
                  f"{', '.join(a['findings'])[:80]}")

    _print_section("EMPTY bodies", empty)
    _print_section("TRUNCATED (no sentence-end in first 200 chars)", truncated)
    _print_section("BLEED (body contains another opener mid-text)", bleed)

    print(f"\nSummary: {len(empty)} empty, {len(truncated)} truncated, "
          f"{len(bleed)} bleed")


if __name__ == "__main__":
    main()
