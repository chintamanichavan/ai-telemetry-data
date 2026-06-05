"""
Eyeball the current canonical data.

Reads data/models.csv and data/orgs.csv using a real CSV parser (awk and cut
break on quoted fields containing commas) and prints a summary plus the
top frontier models by training compute.

Run from repo root:
    python3 scripts/show.py
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_CSV = REPO_ROOT / "data" / "models.csv"
ORGS_CSV = REPO_ROOT / "data" / "orgs.csv"


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_flop(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def main() -> int:
    models = load(MODELS_CSV)
    orgs = load(ORGS_CSV)

    if not models:
        print("data/models.csv is empty or missing. Run: python3 ingesters/epoch.py")
        return 1

    current = [r for r in models if not r["valid_to"]]
    superseded = [r for r in models if r["valid_to"]]

    print(f"models.csv: {len(current)} current, {len(superseded)} superseded "
          f"({len(models)} total rows)")
    print(f"orgs.csv:   {len(orgs)} orgs")
    print()

    tiers = Counter(r["capability_tier"] for r in current)
    confidences = Counter(r["compute_confidence"] for r in current)
    sources = Counter(r["source"] for r in current)

    print(f"tier:         {dict(tiers)}")
    print(f"confidence:   {dict(confidences)}")
    print(f"source:       {dict(sources)}")
    print()

    frontier = sorted(
        (r for r in current if r["capability_tier"] == "frontier"),
        key=lambda r: parse_flop(r["training_compute_flop"]),
        reverse=True,
    )
    print(f"frontier models ({len(frontier)}), by compute:")
    print(f"  {'compute (FLOP)':>16}  {'release':<11}  {'name':<32}  org")
    for r in frontier:
        print(
            f"  {r['training_compute_flop']:>16}  "
            f"{r['release_date']:<11}  "
            f"{r['name'][:32]:<32}  "
            f"{r['org_id']}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
