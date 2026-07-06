"""Convert the ACE Movement Map spreadsheet (CSV export) into per-organization
Markdown documents plus an upload manifest.

Why one document per organization: Gemini File Search chunks documents with a
whitespace/token splitter that ignores row boundaries, so uploading the raw CSV
(or one big JSON) can produce chunks that start mid-row and lose the
"Organization" cell that gives the row meaning. Chunks never span document
boundaries, so emitting one small self-contained document per org makes
cross-org misattribution structurally impossible: every row here fits inside a
single chunk (see chunking_config in upload_movement_map.py).

This script is stdlib-only on purpose — it needs no API key or google-genai
install, so the confidential CSV can be converted anywhere.

Usage:
    python convert_movement_map.py --csv /path/to/movement_map.csv \
        --out ../../../data/movement_map
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# Source CSV column headers (exact strings from the sheet)
COL_ORG = "Organization"
COL_WEBSITE = "Website"
COL_SUMMARY = "Summary description"
COL_COUNTRY = "Country of registration/ headquarters"
COL_REGIONS = "Countries/regions of operation (if different from headquarters)"
COL_ANIMALS = "Animals helped (menu)"
COL_INTERVENTIONS = "Interventions used (menu)"
COL_TOC = "Foundational TOC (see this resource for more context)"
COL_BUDGET = "Estimated annual budget size"
COL_GRANTS = "Recent grant(s) from a major (E)AA funder in the past 2 years (2024-2026)"
COL_ACE = "ACE history"
COL_NOTES = "Other notes"

# Field label shown in the Markdown profile, in output order (summary handled separately)
FIELD_LABELS = [
    (COL_WEBSITE, "Website"),
    (COL_COUNTRY, "Country of registration / headquarters"),
    (COL_REGIONS, "Countries/regions of operation"),
    (COL_ANIMALS, "Animals helped"),
    (COL_INTERVENTIONS, "Interventions used"),
    (COL_TOC, "Foundational theory of change"),
    (COL_BUDGET, "Estimated annual budget size"),
    (COL_GRANTS, "Recent grants from major (E)AA funders (2024–2026)"),
    (COL_ACE, "ACE history"),
    (COL_NOTES, "Other notes"),
]

# Fields attached as custom_metadata for metadata_filter queries (max 20 per doc)
METADATA_FIELDS = [
    (COL_ORG, "organization"),
    (COL_COUNTRY, "country"),
    (COL_REGIONS, "regions_of_operation"),
    (COL_BUDGET, "budget_tier"),
    (COL_ANIMALS, "animals_helped"),
    (COL_INTERVENTIONS, "interventions"),
    (COL_ACE, "ace_history"),
]

# Gemini custom metadata string values are capped; stay safely under the limit.
METADATA_VALUE_MAX_CHARS = 250

# Sheet placeholders that mean "no value"
ABSENT_VALUES = {"", "[no website found]", "n/a", "na", "-"}


def clean(value: str | None) -> str:
    """Strip and normalize whitespace; return '' for placeholder non-values."""
    if value is None:
        return ""
    text = re.sub(r"[ \t]+", " ", value.replace("\r", "")).strip()
    if text.lower() in ABSENT_VALUES:
        return ""
    return text


def clean_list(value: str | None) -> str:
    """Normalize a comma-separated menu field (collapses doubled spaces after commas)."""
    text = clean(value)
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r",\s*", text) if p.strip()]
    return ", ".join(parts)


def slugify(name: str, max_len: int = 80) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug[:max_len].strip("-") or "org"


LIST_COLUMNS = {COL_ANIMALS, COL_INTERVENTIONS, COL_REGIONS}


def row_fields(row: dict) -> dict:
    """Cleaned column values for one row, keyed by source column header."""
    out = {}
    for col in row:
        if col is None:
            continue
        out[col] = clean_list(row[col]) if col in LIST_COLUMNS else clean(row[col])
    return out


def build_markdown(fields: dict) -> str:
    """Render one self-contained org profile. The org name appears in the H1 and
    as the first labeled field so any chunk of this document is self-attributing."""
    org = fields[COL_ORG]
    lines = [f"# {org}", "", f"**Organization:** {org}"]
    for col, label in FIELD_LABELS:
        value = fields.get(col, "")
        if value:
            lines.append(f"**{label}:** {value}")
    summary = fields.get(COL_SUMMARY, "")
    if summary:
        lines += ["", "## Summary", summary]
    lines.append("")
    return "\n".join(lines)


def build_metadata(fields: dict) -> dict:
    meta = {}
    for col, key in METADATA_FIELDS:
        value = fields.get(col, "")
        if value:
            meta[key] = value[:METADATA_VALUE_MAX_CHARS]
    return meta


def convert(csv_path: Path, out_dir: Path) -> dict:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or COL_ORG not in rows[0]:
        sys.exit(f"❌ CSV at {csv_path} is empty or missing the '{COL_ORG}' column — "
                 f"got headers: {list(rows[0].keys()) if rows else 'none'}")

    out_dir.mkdir(parents=True, exist_ok=True)

    seen_names: set[str] = set()
    seen_slugs: dict[str, int] = {}
    documents = []
    skipped = 0

    for i, row in enumerate(rows, start=2):  # start=2: row 1 is the header
        fields = row_fields(row)
        org = fields.get(COL_ORG, "")
        if not org:
            print(f"⚠️  Skipping CSV row {i}: empty Organization cell")
            skipped += 1
            continue
        if org in seen_names:
            sys.exit(f"❌ Duplicate organization name at CSV row {i}: {org!r}. "
                     "Each org must be unique so citations and --replace stay unambiguous; "
                     "dedupe the sheet and re-run.")
        seen_names.add(org)

        slug = slugify(org)
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 1

        filename = f"{slug}.md"
        (out_dir / filename).write_text(build_markdown(fields), encoding="utf-8")
        documents.append({
            "file": filename,
            "display_name": f"Movement Map - {org}.md",
            "custom_metadata": build_metadata(fields),
        })

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_csv": csv_path.name,
        "expected_count": len(documents),
        "documents": documents,
    }
    manifest_path = out_dir / "movement_map_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ Wrote {len(documents)} org profiles to {out_dir}")
    if skipped:
        print(f"⚠️  Skipped {skipped} row(s) with no organization name")
    print(f"✅ Manifest: {manifest_path}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert the Movement Map CSV into per-org Markdown + upload manifest")
    parser.add_argument("--csv", type=Path, required=True, help="Path to the Movement Map CSV export")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[3] / "data" / "movement_map",
                        help="Output directory (default: <repo>/data/movement_map, gitignored)")
    args = parser.parse_args()
    convert(args.csv, args.out)
