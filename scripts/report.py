"""Aggregate report: per-volume Balearic counts + island/type breakdown.

Reads data/index/tomoNN.jsonl produced by scripts/index_volume.py and
prints a compact summary suitable for inclusion in the README's
*Coverage* section.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT / "data" / "index"


def load_index(vol: str) -> list[dict]:
    p = INDEX_DIR / f"tomo{vol}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l]


def main() -> None:
    grand = []
    print(f"{'Tom':>3}  {'Balear':>6}  Sample titles")
    print(f"{'---':>3}  {'------':>6}  {'-'*55}")
    for n in range(1, 13):
        vol = f"{n:02d}"
        entries = load_index(vol)
        grand.extend(entries)
        sample = ", ".join(e["lemma"][:18] for e in entries[:5])
        print(f"  {n:>2}  {len(entries):>6}  {sample}")

    print()
    print(f"Total Balearic entries across all volumes: {len(grand)}")

    # By island (where NGIB cross-check resolved)
    by_isl = Counter(e["ngib"]["island"] for e in grand if e["ngib"])
    no_ngib = sum(1 for e in grand if not e["ngib"])
    print(f"\nBy island (NGIB-resolved, n={sum(by_isl.values())}):")
    for isl, n in by_isl.most_common():
        print(f"  {isl:<12}  {n:>3}")
    print(f"  (no NGIB match)  {no_ngib:>3}")

    # By NGIB type (rough place-type distribution)
    by_type = Counter(e["ngib"]["type"] for e in grand if e["ngib"] and e["ngib"].get("type"))
    print(f"\nBy NGIB type (top 8):")
    for t, n in by_type.most_common(8):
        print(f"  {t[:32]:<32}  {n:>3}")

    # Body-length distribution: short geographic-only entries (capes,
    # short cross-references) vs long template-form entries
    short = sum(1 for e in grand if e.get("body_lines", 0) < 20)
    print(f"\nBody-length distribution:")
    print(f"  short (<20 lines)  {short:>3}")
    print(f"  long  (≥20 lines)  {len(grand)-short:>3}")


if __name__ == "__main__":
    main()
