"""
Epoch AI notable models ingester.

Fetches Epoch AI's notable AI models dataset, normalizes to AI Telemetry's
canonical schema (per METHODOLOGY.md v1.0), applies PIT revision semantics,
and writes to data/.

Idempotent: re-running with unchanged upstream data is a no-op (no spurious
revisions, no observed_at churn).

Not in this ingester (deferred):
  - disputes.csv (needs source #2 to disagree with).
  - aliases.csv / overrides.yaml lookups.
  - open_weights, context_window, system_card_url (not in Epoch's schema;
    populated by future lab-blog and Hugging Face ingesters).
  - Org type classification (not in Epoch's schema; manual override later).
  - Frontier-via-benchmark tier upgrades (handled by future eval ingester).

Run from repo root:
    python ingesters/epoch.py

Override Epoch CSV URL if it has moved:
    EPOCH_CSV_URL=https://... python ingesters/epoch.py
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

EPOCH_CSV_URL = os.environ.get(
    "EPOCH_CSV_URL",
    "https://epoch.ai/data/epochdb/notable_ai_models.csv",
)
SOURCE_ID = "epoch_ai"
SOURCE_HOMEPAGE = "https://epoch.ai/data/notable-ai-models"

DEFINITION_VERSION = "v1.0"
NOTABLE_FLOP_THRESHOLD = 1e24
FRONTIER_FLOP_THRESHOLD = 1e25

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MODELS_CSV = DATA_DIR / "models.csv"
ORGS_CSV = DATA_DIR / "orgs.csv"

MODEL_COLUMNS = [
    "entity_id", "name", "org_id", "release_date",
    "training_compute_flop", "compute_confidence",
    "capability_tier", "open_weights", "context_window", "modalities",
    "system_card_url", "paper_url",
    "source", "source_url",
    "observed_at", "source_at", "valid_from", "valid_to",
    "definition_version",
]

ORG_COLUMNS = [
    "org_id", "name", "country", "type", "parent_org_id",
    "source", "source_url",
    "observed_at", "source_at", "valid_from", "valid_to",
    "definition_version",
]

# Fields whose change triggers a revision (closes prior row, appends new).
TRACKED_MODEL_FIELDS = [
    "name", "org_id", "release_date", "training_compute_flop",
    "compute_confidence", "capability_tier", "open_weights",
    "context_window", "modalities", "system_card_url", "paper_url",
]
TRACKED_ORG_FIELDS = ["name", "country", "type", "parent_org_id"]

MODALITY_MAP: dict[str, tuple[str, ...]] = {
    "language": ("text",),
    "text": ("text",),
    "vision": ("image",),
    "image": ("image",),
    "speech": ("audio",),
    "audio": ("audio",),
    "video": ("video",),
    "robotics": ("action",),
    "multimodal": ("text", "image"),
}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def first_present(row: dict, *keys: str) -> str:
    """Return the first non-empty value among keys. Epoch column names drift."""
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def parse_float(s) -> float | None:
    if s in (None, ""):
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def parse_date(s) -> str | None:
    """Return ISO date YYYY-MM-DD or None. Tolerant of Epoch's varying formats."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def derive_modalities(raw: dict) -> str:
    domain = first_present(raw, "Domain", "Modality").lower()
    if not domain:
        return ""
    out: list[str] = []
    for part in re.split(r"[,/|;]", domain):
        for m in MODALITY_MAP.get(part.strip(), ()):
            if m not in out:
                out.append(m)
    return "|".join(out)


def fetch_epoch_csv(url: str = EPOCH_CSV_URL) -> list[dict]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ai-telemetry-ingester/0.1 (+https://aitelemetry.org)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    if "<html" in body[:200].lower():
        raise RuntimeError(
            f"Epoch URL returned HTML, not CSV. Check EPOCH_CSV_URL. URL={url}"
        )
    return list(csv.DictReader(io.StringIO(body)))


def normalize_model(raw: dict) -> dict | None:
    name = first_present(raw, "System", "Model", "Name")
    org = first_present(raw, "Organization", "Organisation", "Author Organization")
    if not name or not org:
        return None

    flop = parse_float(
        first_present(raw, "Training compute (FLOP)", "Training compute", "Compute")
    )
    if flop is None or flop < NOTABLE_FLOP_THRESHOLD:
        return None

    release_date = parse_date(
        first_present(raw, "Publication date", "Release date", "Date")
    )
    if not release_date:
        return None

    confidence = first_present(
        raw, "Training compute confidence", "Confidence"
    ).lower() or "estimated"

    ref = first_present(raw, "Reference", "Reference link", "Paper URL", "URL")
    tier = "frontier" if flop >= FRONTIER_FLOP_THRESHOLD else "notable"

    return {
        "entity_id": f"{slugify(org)}/{slugify(name)}-{release_date[:4]}",
        "name": name.strip(),
        "org_id": slugify(org),
        "release_date": release_date,
        "training_compute_flop": f"{flop:.6e}",
        "compute_confidence": confidence,
        "capability_tier": tier,
        "open_weights": "",
        "context_window": "",
        "modalities": derive_modalities(raw),
        "system_card_url": "",
        "paper_url": ref,
        "source": SOURCE_ID,
        "source_url": ref or SOURCE_HOMEPAGE,
        "source_at": release_date,
        "definition_version": DEFINITION_VERSION,
    }


def normalize_org(raw: dict) -> dict | None:
    org = first_present(raw, "Organization", "Organisation", "Author Organization")
    if not org:
        return None
    country = first_present(raw, "Country", "Organization country")
    return {
        "org_id": slugify(org),
        "name": org.strip(),
        "country": country.strip(),
        "type": "",
        "parent_org_id": "",
        "source": SOURCE_ID,
        "source_url": SOURCE_HOMEPAGE,
        "source_at": "",
        "definition_version": DEFINITION_VERSION,
    }


def read_canonical(path: Path, columns: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c in columns:
            r.setdefault(c, "")
    return rows


def atomic_write_csv(path: Path, columns: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)


def apply_pit(
    existing: list[dict],
    incoming: list[dict],
    key_field: str,
    tracked_fields: list[str],
    now: str,
) -> tuple[list[dict], int, int]:
    """Apply PIT revision semantics. Returns (rows, n_inserted, n_revised)."""
    out = list(existing)
    current_by_key = {r[key_field]: r for r in out if not r.get("valid_to")}
    n_ins = n_rev = 0

    for rec in incoming:
        key = rec[key_field]
        current = current_by_key.get(key)

        if current is None:
            new_row = dict(rec, observed_at=now, valid_from=now, valid_to="")
            out.append(new_row)
            current_by_key[key] = new_row
            n_ins += 1
            continue

        unchanged = all(
            (current.get(f, "") or "") == (rec.get(f, "") or "")
            for f in tracked_fields
        )
        if unchanged:
            continue

        # revision: close current, append new
        current["valid_to"] = now
        new_row = dict(rec, observed_at=now, valid_from=now, valid_to="")
        out.append(new_row)
        current_by_key[key] = new_row
        n_rev += 1

    return out, n_ins, n_rev


def main() -> int:
    print(f"[epoch] fetching {EPOCH_CSV_URL}", file=sys.stderr)
    try:
        raw_rows = fetch_epoch_csv()
    except (urllib.error.URLError, RuntimeError) as e:
        print(f"[epoch] fetch failed: {e}", file=sys.stderr)
        return 2
    print(f"[epoch] fetched {len(raw_rows)} raw rows", file=sys.stderr)

    incoming_models: list[dict] = []
    incoming_orgs: dict[str, dict] = {}
    skipped = 0
    for raw in raw_rows:
        m = normalize_model(raw)
        if m is None:
            skipped += 1
            continue
        incoming_models.append(m)
        o = normalize_org(raw)
        if o and o["org_id"] not in incoming_orgs:
            incoming_orgs[o["org_id"]] = o

    print(
        f"[epoch] normalized: {len(incoming_models)} notable models, "
        f"{len(incoming_orgs)} orgs; skipped {skipped}",
        file=sys.stderr,
    )

    now = now_utc_iso()
    existing_models = read_canonical(MODELS_CSV, MODEL_COLUMNS)
    existing_orgs = read_canonical(ORGS_CSV, ORG_COLUMNS)

    out_models, ins_m, rev_m = apply_pit(
        existing_models, incoming_models, "entity_id", TRACKED_MODEL_FIELDS, now
    )
    out_orgs, ins_o, rev_o = apply_pit(
        existing_orgs, list(incoming_orgs.values()),
        "org_id", TRACKED_ORG_FIELDS, now,
    )

    atomic_write_csv(MODELS_CSV, MODEL_COLUMNS, out_models)
    atomic_write_csv(ORGS_CSV, ORG_COLUMNS, out_orgs)

    print(
        f"[epoch] models: {ins_m} inserted, {rev_m} revised, "
        f"{len(out_models)} total rows",
        file=sys.stderr,
    )
    print(
        f"[epoch] orgs:   {ins_o} inserted, {rev_o} revised, "
        f"{len(out_orgs)} total rows",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
