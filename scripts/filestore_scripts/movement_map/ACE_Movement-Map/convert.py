"""Convert the ACE Movement Map spreadsheet (CSV export) into per-organization
Markdown documents plus an upload manifest for the ACE_Movement-Map collection.

Why one document per organization: Gemini File Search chunks documents with a
whitespace/token splitter that ignores row boundaries, so uploading the raw CSV
(or one big JSON) can produce chunks that start mid-row and lose the
"Organization" cell that gives the row meaning. Chunks never span document
boundaries, so emitting one small self-contained document per org makes
cross-org misattribution structurally impossible: every row here fits inside a
single chunk (see chunking_config in upload_profiles.py).

This script is stdlib-only on purpose — it needs no API key or google-genai
install, so the confidential CSV can be converted anywhere.

Usage:
    python convert.py --csv /path/to/movement_map.csv \
        --out ../../../../data/ACE_Movement-Map
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # movement_map/ shared helpers
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src" / "country_profiles"))
from common import (  # noqa: E402
    METADATA_VALUE_MAX_CHARS, clean, clean_list, dedupe_slug, slugify,
    warn_if_oversized, write_manifest,
)
from intervention_tags import INTERVENTION_TAGS  # noqa: E402

# Citations render as the display_name, so this prefix is user-facing text.
DISPLAY_PREFIX = "ACE Movement Map - "
SOURCE_LABEL = "ACE Movement Map 2026"
MANIFEST_FILENAME = "ace_movement_map_manifest.json"

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

# ACE's interventions menu and the tag legend both derive from the State of the
# Movement survey, so most menu values equal a tag's label (with or without the
# "Category — " prefix); those map automatically below. Menu values that don't
# line up textually get an explicit alias here (menu value -> tag code).
# Values that still match nothing are reported at the end of the run.
MENU_TAG_ALIASES: dict[str, str] = {}


def _tag_alias_table() -> dict[str, tuple[str, ...]]:
    """tag code -> lowercase text fragments whose presence in the interventions
    cell means the org carries that tag."""
    table: dict[str, list[str]] = {}
    for code, label in INTERVENTION_TAGS.items():
        aliases = [label.casefold()]
        if " — " in label:
            aliases.append(label.split(" — ", 1)[1].casefold())
        table[code] = aliases
    for menu_value, code in MENU_TAG_ALIASES.items():
        table[code].append(menu_value.casefold())
    return {code: tuple(aliases) for code, aliases in table.items()}


TAG_ALIASES = _tag_alias_table()


def interventions_to_tags(interventions_text: str, unmatched: set[str]) -> list[str]:
    """Tag codes whose label (or alias) appears in the free-text interventions
    cell. Substring scan rather than a split — the menu labels themselves
    contain commas, so the cell cannot be split reliably."""
    text = interventions_text.casefold()
    if not text:
        return []
    codes = [code for code, aliases in TAG_ALIASES.items() if any(a in text for a in aliases)]
    if not codes:
        unmatched.add(interventions_text)
    return codes


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


def build_metadata(fields: dict, unmatched_interventions: set[str]) -> dict:
    meta = {}
    for col, key in METADATA_FIELDS:
        value = fields.get(col, "")
        if value:
            meta[key] = value[:METADATA_VALUE_MAX_CHARS]
    tags = interventions_to_tags(fields.get(COL_INTERVENTIONS, ""), unmatched_interventions)
    if tags:
        meta["intervention_tags"] = tags  # list -> string_list_value at upload
    meta["source"] = SOURCE_LABEL
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
    unmatched_interventions: set[str] = set()
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

        slug = dedupe_slug(slugify(org), seen_slugs)
        filename = f"{slug}.md"
        markdown = build_markdown(fields)
        warn_if_oversized(org, markdown)
        (out_dir / filename).write_text(markdown, encoding="utf-8")
        documents.append({
            "file": filename,
            "display_name": f"{DISPLAY_PREFIX}{org}.md",
            "custom_metadata": build_metadata(fields, unmatched_interventions),
        })

    manifest_path = write_manifest(out_dir, MANIFEST_FILENAME, csv_path, documents)

    print(f"✅ Wrote {len(documents)} org profiles to {out_dir}")
    if skipped:
        print(f"⚠️  Skipped {skipped} row(s) with no organization name")
    if unmatched_interventions:
        print(f"⚠️  {len(unmatched_interventions)} interventions cell(s) matched no tag code — "
              "add entries to MENU_TAG_ALIASES and re-run. Distinct values:")
        for value in sorted(unmatched_interventions):
            print(f"     {value!r}")
    print(f"✅ Manifest: {manifest_path}")
    return {"documents": documents, "manifest_path": manifest_path}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert the ACE Movement Map CSV into per-org Markdown + upload manifest")
    parser.add_argument("--csv", type=Path, required=True, help="Path to the ACE Movement Map CSV export")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[4] / "data" / "ACE_Movement-Map",
                        help="Output directory (default: <repo>/data/ACE_Movement-Map, gitignored)")
    args = parser.parse_args()
    convert(args.csv, args.out)
