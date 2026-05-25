"""Apply the manual-exclusion list to data/index/ and data/text/.

Reads data/manual_exclusions.txt — a simple list of `vol page lemma`
triples — and removes matching entries from both the index JSONL
files and the page_*.json files. Designed to be cheap to audit: the
exclusion list is plain text, one entry per line, with mandatory
justification comments.

Run after every reindex (the indexer rewrites data/index/ from the
PDFs and would otherwise re-introduce removed entries):

    python scripts/index_volume.py --all
    python scripts/apply_exclusions.py
    python scripts/load_text.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
EXCL = PROJECT / "data" / "manual_exclusions.txt"
INDEX_DIR = PROJECT / "data" / "index"
TEXT_DIR = PROJECT / "data" / "text"


def load_exclusions() -> set[tuple[str, int, str]]:
    out: set[tuple[str, int, str]] = set()
    for line in EXCL.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # First two tokens are vol+page; rest of the line is the lemma.
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        vol, page, lemma = parts
        out.add((vol, int(page), lemma))
    return out


def main() -> None:
    exclusions = load_exclusions()
    print(f"Loaded {len(exclusions)} exclusion entries from {EXCL.name}")

    # Filter index JSONL
    n_idx = 0
    for f in sorted(INDEX_DIR.glob("tomo*.jsonl")):
        entries = [json.loads(l) for l in f.read_text().splitlines()]
        kept = [e for e in entries
                if (e["vol"], int(e["page"]), e["lemma"]) not in exclusions]
        removed = len(entries) - len(kept)
        if removed:
            with f.open("w") as fh:
                for e in kept:
                    fh.write(json.dumps(e, ensure_ascii=False) + "\n")
            n_idx += removed
            print(f"  {f.name}: {removed} excluded")

    # Filter page_*.json (and delete page files that become empty)
    n_txt = 0
    for f in sorted(TEXT_DIR.glob("page_*.json")):
        page = json.loads(f.read_text())
        vol, pg = page["vol"], int(page["page"])
        before = page.get("entries", [])
        kept = [e for e in before
                if (vol, pg, e.get("title")) not in exclusions]
        if len(kept) == len(before):
            continue
        n_txt += len(before) - len(kept)
        if not kept:
            f.unlink()
            print(f"  Deleted {f.name} (empty after exclusion)")
        else:
            page["entries"] = kept
            f.write_text(json.dumps(page, ensure_ascii=False, indent=2))

    print(f"\nRemoved {n_idx} from index, {n_txt} from text.")


if __name__ == "__main__":
    main()
