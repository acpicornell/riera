"""Coordinate quality audit.

Reads ``data/coords.json`` (output of enrich_coords.py) and reports:

  (1) **Out-of-envelope** — coordinates fall outside the Balearic
      bounding box. Riera's Balearic articles describe locations
      within:
          lon: 1.10 … 4.45
          lat: 38.50 … 40.10
      Anything outside is either a bug (lon/lat swap, sign error) or
      a coord assigned to a wrong place.

  (2) **NULL / zero** — entries with (0,0) or missing lon/lat. These
      slipped through enrich_coords.py and need attention.

  (3) **Island-centroid fallbacks** — entries that resolved to an
      island centroid because no NGIB match was found. These render
      at the island's geometric centre on the map, which is not
      useful for cape / minor-village entries. Listed for triage.

  (4) **Cluster-of-one** — entries whose coordinates land exactly on
      the same point as another entry (within 1 km). Usually the
      sign of falling back to the same centroid; might also reveal
      duplicate NGIB matches.

Run: ``python scripts/audit_coords.py``
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
COORDS = PROJECT / "data" / "coords.json"

# Balearic bounding box (slightly padded).
LON_MIN, LON_MAX = 1.05, 4.45
LAT_MIN, LAT_MAX = 38.45, 40.15

CLUSTER_TOL = 0.005  # ~500 m


def in_envelope(lon: float, lat: float) -> bool:
    return LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX


def main() -> None:
    if not COORDS.exists():
        raise SystemExit(f"{COORDS} not found — run enrich_coords.py first")
    data = json.loads(COORDS.read_text())
    print(f"Auditing {len(data)} coord rows…\n")

    out_of_env: list[dict] = []
    null_or_zero: list[dict] = []
    centroid: list[dict] = []
    point_groups: dict[tuple, list[dict]] = defaultdict(list)

    for r in data:
        lon = r.get("lon")
        lat = r.get("lat")
        if lon is None or lat is None or (lon == 0 and lat == 0):
            null_or_zero.append(r)
            continue
        if not in_envelope(float(lon), float(lat)):
            out_of_env.append(r)
        if r.get("source") == "centroid":
            centroid.append(r)
        # Cluster bucket — rounded to CLUSTER_TOL
        key = (round(float(lon) / CLUSTER_TOL), round(float(lat) / CLUSTER_TOL))
        point_groups[key].append(r)

    cluster_groups = {k: v for k, v in point_groups.items() if len(v) >= 2}

    def _print_section(title: str, items: list[dict]) -> None:
        print(f"\n=== {title}  ({len(items)} rows) ===")
        if not items:
            print("  (none)")
            return
        for r in items:
            lon = r.get("lon")
            lat = r.get("lat")
            extra = r.get("matched") or r.get("fallback") or r.get("note") or ""
            print(f"  tom{r.get('vol')} p{r.get('page'):>4}  "
                  f"{r.get('title', '')[:36]:<36}  "
                  f"({lon!s:>8}, {lat!s:>8})  {r.get('source', ''):<10}  "
                  f"{extra[:40]}")

    _print_section("NULL or zero coords", null_or_zero)
    _print_section("OUTSIDE Balearic envelope", out_of_env)
    _print_section("Island-centroid fallbacks (low precision)", centroid)

    print(f"\n=== CLUSTERS at same point  ({len(cluster_groups)} groups) ===")
    if not cluster_groups:
        print("  (none — every coord is unique within 500 m)")
    else:
        for key, group in sorted(cluster_groups.items(),
                                  key=lambda kv: -len(kv[1])):
            print(f"\n  Cluster at (~{group[0]['lon']}, ~{group[0]['lat']}): "
                  f"{len(group)} entries")
            for r in group[:10]:
                print(f"    tom{r['vol']} p{r['page']:>4}  "
                      f"{r.get('title', '')[:36]:<36}  "
                      f"{r.get('source', ''):<10}")
            if len(group) > 10:
                print(f"    … and {len(group) - 10} more")

    print(f"\nSummary:")
    print(f"  Null/zero coords:        {len(null_or_zero)}")
    print(f"  Out of envelope:         {len(out_of_env)}")
    print(f"  Island-centroid (loose): {len(centroid)}")
    print(f"  Multi-point clusters:    {len(cluster_groups)}")


if __name__ == "__main__":
    main()
