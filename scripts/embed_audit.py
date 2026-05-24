"""Sanity-check the 25 pdftotext-only audit candidates with local embeddings.

Each candidate is a Riera opener that pdftotext sees with ≥1 Balearic-token
mention in the head but that PyMuPDF's indent detector hasn't picked up.
The audit suggests these are peninsular false positives whose body mentions
'Cabrera' incidentally (arciprestat de Cabrera Baja in the León diocese).

This script confirms that hypothesis semantically: it embeds each body with
a multilingual sentence-transformer (bge-m3 for highest quality on Spanish,
or paraphrase-multilingual-mpnet-base-v2 for a faster smaller model), then
measures cosine similarity against two reference queries:

  • Q_BAL  — what a real Balearic village description looks like
  • Q_LEON — what a León village description looks like

A clean separation (Q_LEON > Q_BAL by a wide margin) confirms the candidate
is peninsular and our regex+anchor detector was right to skip it.

Run: ``python scripts/embed_audit.py``
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

PROJECT = Path(__file__).resolve().parent.parent
TXT_DIR = PROJECT / "data" / "txt"

# Quality vs size:
#   BAAI/bge-m3                                    2.2 GB, best multilingual
#   sentence-transformers/paraphrase-multilingual-mpnet-base-v2  1.1 GB, faster
MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


# Reference queries: archetypal descriptions of a Balearic vs León entry.
# We deliberately use Riera's own administrative vocabulary so the
# embeddings sit in the same neighbourhood of vector space.
Q_BAL = (
    "Villa con ayuntamiento en la provincia de las Baleares, "
    "isla de Mallorca, diócesis de Palma. Audiencia territorial "
    "de Mallorca. Capitanía general de las Baleares, gobierno "
    "militar de Palma. Departamento marítimo de Cartagena, "
    "provincia marítima de Mallorca."
)
Q_LEON = (
    "Lugar agregado al ayuntamiento en la provincia de León, "
    "diócesis de Astorga, arciprestazgo de Cabrera Baja. "
    "Audiencia territorial de Valladolid. Capitanía general de "
    "Castilla la Vieja, gobierno militar de León."
)


# Body extraction copied from audit_pdftotext.py but per (vol, line)
def get_body(vol: str, line_no: int, max_lines: int = 30) -> str:
    txt = (TXT_DIR / f"tomo{vol}.txt").read_text()
    lines = txt.split("\n")
    return "\n".join(lines[line_no - 1 : line_no - 1 + max_lines])


# The 25 audit candidates (vol, page-from-audit, line, lemma) — generated
# manually from the last `audit_pdftotext.py` run.
CANDIDATES = [
    ("01", 238, 25464, "ALBER1TE"),
    ("02", 76, 9001, "BAILLO"),
    ("02", 656, 91092, "BENUZA"),
    ("03", 1064, 139275, "CORPORALES"),
    ("03", 1238, 162277, "CUNAS"),
    ("04", 203, 25175, "EL BERRUECO"),
    ("04", 347, 43683, "ENCINEDO"),
    ("05", 645, 88988, "IGUALADA"),
    ("05", 700, 96523, "IRUELA"),
    ("06", 175, 20468, "LA VEGA DE ALMANZA"),
    ("06", 402, 54949, "LOMBA"),
    ("06", 423, 57575, "LOSADILLA"),
    ("06", 492, 66845, "LUCILLO"),
    ("06", 554, 76936, "LLAMAS"),
    ("07", 122, 14508, "MATARO"),
    ("07", 480, 60758, "MORLA"),
    ("07", 1034, 135444, "PÁJARA"),
    ("08", 76, 8774, "PELEGRINA"),
    ("08", 274, 34207, "POMBRIEGO"),
    ("08", 366, 46510, "POZOS"),
    ("08", 583, 74559, "QUINTANILLA DE YUSO"),
    ("08", 804, 102244, "ROBLEDO DE LOSADA"),
    ("09", 1173, 157185, "SILVAN"),
    ("10", 16, 596, "SOBRADO"),
    ("10", 111, 14685, "SOTILLO"),
    ("10", 636, 87507, "TRABAZOS"),
    ("10", 679, 93095, "TRUCHAS"),
    ("10", 679, 93164, "TRUCHILLAS"),
    ("11", 552, 72940, "VILLAR DEL MONTE"),
    ("11", 582, 76657, "VILLARINO"),
    ("11", 683, 89374, "VILLORUEBO"),
    ("11", 783, 103852, "YEBRA"),
]


def main():
    print(f"Loading model: {MODEL} (first run downloads ~1 GB)...")
    t0 = time.time()
    model = SentenceTransformer(MODEL, device="mps")
    print(f"  loaded in {time.time()-t0:.1f}s")

    # Embed reference queries
    q_emb = model.encode([Q_BAL, Q_LEON], normalize_embeddings=True)
    q_bal, q_leon = q_emb

    # Read each candidate body
    rows = []
    for vol, page, line, lemma in CANDIDATES:
        body = get_body(vol, line, max_lines=30)
        rows.append((vol, page, lemma, body))

    print(f"\nEmbedding {len(rows)} candidate bodies...")
    bodies = [r[3] for r in rows]
    t0 = time.time()
    body_emb = model.encode(bodies, normalize_embeddings=True,
                             batch_size=32, show_progress_bar=False)
    print(f"  embedded in {time.time()-t0:.1f}s")

    # Cosine similarities (vectors are already normalised so dot product = cos)
    sim_bal = body_emb @ q_bal
    sim_leon = body_emb @ q_leon
    margin = sim_leon - sim_bal

    print()
    print(f"  {'tom/page':<10} {'lemma':<22} {'sim_BAL':>9} {'sim_LEON':>9} {'Δ(LEON-BAL)':>11}  classification")
    for (vol, page, lemma, _), sb, sl, m in zip(rows, sim_bal, sim_leon, margin):
        # Margin > 0.02 → clear León; margin < -0.02 → clear Balearic;
        # else ambiguous.
        if m > 0.02:
            tag = "→ peninsular (confirmed)"
        elif m < -0.02:
            tag = "→ POSSIBLE BALEARIC ⚠"
        else:
            tag = "ambiguous"
        print(f"  tom{vol} p{page:>4}  {lemma[:22]:<22} {sb:>9.3f} {sl:>9.3f} {m:>+11.3f}  {tag}")


if __name__ == "__main__":
    main()
