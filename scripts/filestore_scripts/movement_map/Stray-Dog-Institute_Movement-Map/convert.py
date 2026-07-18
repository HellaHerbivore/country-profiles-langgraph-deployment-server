"""Convert Stray Dog Institute's India Partner Directory (Directory-tab CSV
export) into per-organization Markdown documents plus an upload manifest for
the Stray-Dog-Institute_Movement-Map collection.

Same row-integrity design as the ACE pipeline (see ACE_Movement-Map/convert.py):
one self-contained profile per organization so a File Search chunk can never
mix two organizations.

Intervention tags: the "Tags (all)" column holds codes from SDI's State of the
Movement taxonomy (legend in the sheet's Read Me tab, canonically stored in
src/country_profiles/intervention_tags.py). Each profile gets BOTH the expanded
human-readable labels (semantic retrieval signal) and the raw codes
(exact-string search), and the codes are attached as `intervention_tags`
custom metadata for metadata_filter queries. A '?' suffix on a tag means SDI
believes it applies but has not verified it — rendered "(unverified)" in the
profile, stripped in the metadata. The five per-category columns (Government /
Business / Public / Movement / Animals-Other) are the same tags split for
spreadsheet filtering and are ignored here.

This script is stdlib-only on purpose — it needs no API key or google-genai
install, so the CSV (shared with partners, not public) can be converted anywhere.

Usage:
    python convert.py --csv /path/to/sdi_directory.csv \
        --out ../../../../data/Stray-Dog-Institute_Movement-Map
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # movement_map/ shared helpers
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src" / "country_profiles"))
from common import (  # noqa: E402
    clean, dedupe_slug, slugify, truncate_metadata_value,
    warn_if_oversized, write_manifest,
)
from intervention_tags import INTERVENTION_TAGS  # noqa: E402

# Citations render as the display_name, so this prefix is user-facing text.
DISPLAY_PREFIX = "Stray Dog Institute Movement Map - "
SOURCE_LABEL = "Stray Dog Institute India Partner Directory v1.0 (2026-07-06)"
MANIFEST_FILENAME = "sdi_movement_map_manifest.json"

# Source CSV column headers (exact strings from the Directory tab)
COL_REF = "Ref"
COL_NAME = "Name"
COL_ENTITY = "Entity Type"
COL_STATUS = "Status"
COL_POSITION = "Movement Position"
COL_ROLE = "Role in Movement"
COL_CITY = "City"
COL_STATE = "State"
COL_FOUNDED = "Founded"
COL_WEBSITE = "Website"
COL_DESC = "Description"
COL_TAGS = "Tags (all)"
COL_NOTES = "Notes & open questions"

# Meaning of the Status column, from the sheet's Read Me tab.
STATUS_GLOSS = {
    "in hub": "in Stray Dog Institute's live database",
    "recommended": "vetted addition accepted but not yet imported",
    "conditional": "recommended with an open question (see notes)",
    "india program": "India operation of an international organization without a separate Indian entity",
}

POSITION_GLOSS = {
    "smo": "social movement organization",
}


def parse_tags(raw: str, unknown: set[str]) -> list[tuple[str, bool]]:
    """(code, unverified) pairs from the semicolon-separated "Tags (all)" cell,
    order preserved. Codes not in the taxonomy are kept (the profile should
    still show them) but reported at the end of the run."""
    tags = []
    for part in [p.strip() for p in clean(raw).split(";") if p.strip()]:
        unverified = part.endswith("?")
        code = part.rstrip("?").strip()
        if code not in INTERVENTION_TAGS:
            unknown.add(code)
        tags.append((code, unverified))
    return tags


def expand_tags(tags: list[tuple[str, bool]]) -> str:
    parts = []
    for code, unverified in tags:
        label = INTERVENTION_TAGS.get(code, code)
        parts.append(f"{label} (unverified)" if unverified else label)
    return "; ".join(parts)


def _with_gloss(value: str, gloss: dict[str, str]) -> str:
    extra = gloss.get(value.casefold())
    return f"{value} ({extra})" if extra else value


def build_markdown(fields: dict, tags: list[tuple[str, bool]]) -> str:
    """Render one self-contained org profile. The org name appears in the H1 and
    as the first labeled field so any chunk of this document is self-attributing."""
    org = fields[COL_NAME]
    location = ", ".join(v for v in (fields.get(COL_CITY, ""), fields.get(COL_STATE, "")) if v)
    labeled = [
        ("Entity type", fields.get(COL_ENTITY, "")),
        ("Status in Stray Dog Institute hub", _with_gloss(fields.get(COL_STATUS, ""), STATUS_GLOSS)),
        ("Movement position", _with_gloss(fields.get(COL_POSITION, ""), POSITION_GLOSS)),
        ("Role in movement", fields.get(COL_ROLE, "")),
        ("Location", location),
        ("Founded", fields.get(COL_FOUNDED, "")),
        ("Website", fields.get(COL_WEBSITE, "")),
        ("Interventions used", expand_tags(tags)),
        ("Intervention tags", "; ".join(code for code, _ in tags)),
        ("Notes & open questions", fields.get(COL_NOTES, "")),
    ]
    lines = [f"# {org}", "", f"**Organization:** {org}"]
    lines += [f"**{label}:** {value}" for label, value in labeled if value]
    description = fields.get(COL_DESC, "")
    if description:
        lines += ["", "## Summary", description]
    lines.append("")
    return "\n".join(lines)


def build_metadata(fields: dict, tags: list[tuple[str, bool]]) -> dict:
    string_fields = [
        (COL_NAME, "organization"),
        (COL_REF, "ref"),
        (COL_ENTITY, "entity_type"),
        (COL_STATUS, "status"),
        (COL_POSITION, "movement_position"),
        (COL_ROLE, "role"),
        (COL_CITY, "city"),
        (COL_STATE, "state"),
        (COL_FOUNDED, "founded"),
    ]
    meta = {}
    for col, key in string_fields:
        value = fields.get(col, "")
        if value:
            meta[key] = truncate_metadata_value(value)
    expanded = expand_tags(tags)
    if expanded:
        meta["interventions"] = truncate_metadata_value(expanded)
    codes = list(dict.fromkeys(code for code, _ in tags))  # dedupe, keep order
    if codes:
        meta["intervention_tags"] = codes  # list -> string_list_value at upload
    meta["source"] = SOURCE_LABEL
    return meta


def convert(csv_path: Path, out_dir: Path) -> dict:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or COL_NAME not in rows[0]:
        sys.exit(f"❌ CSV at {csv_path} is empty or missing the '{COL_NAME}' column — "
                 f"got headers: {list(rows[0].keys()) if rows else 'none'}. "
                 "This converter expects the Directory tab, not the Read Me tab.")

    out_dir.mkdir(parents=True, exist_ok=True)

    seen_names: set[str] = set()
    seen_slugs: dict[str, int] = {}
    unknown_tags: set[str] = set()
    documents = []
    skipped = 0

    for i, row in enumerate(rows, start=2):  # start=2: row 1 is the header
        fields = {col: clean(row[col]) for col in row if col is not None}
        org = fields.get(COL_NAME, "")
        if not org:
            print(f"⚠️  Skipping CSV row {i}: empty Name cell")
            skipped += 1
            continue
        if org in seen_names:
            sys.exit(f"❌ Duplicate organization name at CSV row {i}: {org!r}. "
                     "Each org must be unique so citations and --replace stay unambiguous; "
                     "dedupe the sheet and re-run.")
        seen_names.add(org)

        tags = parse_tags(row.get(COL_TAGS, ""), unknown_tags)
        slug = dedupe_slug(slugify(org), seen_slugs)
        filename = f"{slug}.md"
        markdown = build_markdown(fields, tags)
        warn_if_oversized(org, markdown)
        (out_dir / filename).write_text(markdown, encoding="utf-8")
        documents.append({
            "file": filename,
            "display_name": f"{DISPLAY_PREFIX}{org}.md",
            "custom_metadata": build_metadata(fields, tags),
        })

    manifest_path = write_manifest(out_dir, MANIFEST_FILENAME, csv_path, documents)

    print(f"✅ Wrote {len(documents)} org profiles to {out_dir}")
    if skipped:
        print(f"⚠️  Skipped {skipped} row(s) with no organization name")
    if unknown_tags:
        print(f"⚠️  Tag code(s) not in the taxonomy (kept in profiles, check for typos or a "
              f"legend update): {sorted(unknown_tags)}")
    print(f"✅ Manifest: {manifest_path}")
    return {"documents": documents, "manifest_path": manifest_path}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert the SDI India Partner Directory CSV into per-org Markdown + upload manifest")
    parser.add_argument("--csv", type=Path, required=True,
                        help="Path to the Directory-tab CSV export")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[4] / "data" / "Stray-Dog-Institute_Movement-Map",
                        help="Output directory (default: <repo>/data/Stray-Dog-Institute_Movement-Map, gitignored)")
    args = parser.parse_args()
    convert(args.csv, args.out)
