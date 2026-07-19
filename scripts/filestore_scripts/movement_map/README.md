# Movement Map ingestion

Ingests two org-directory collections into the single shared Gemini File Search
store `MOVEMENT_MAP_STORE` (created as **"Movement Map"**):

| Collection | Source | Docs | Citation display name |
|---|---|---|---|
| `ACE_Movement-Map/` | ACE's Movement Map 2026 spreadsheet (confidential CSV export, ~957 orgs, worldwide) | one per org | `ACE Movement Map - {Organization}` |
| `Stray-Dog-Institute_Movement-Map/` | Stray Dog Institute's India Partner Directory v1.0, 2026-07-06 (Directory-tab CSV, ~68 orgs; shared with partners, not public) | one per org | `Stray Dog Institute Movement Map - {Name}` |

Neither CSV is committed; converted output lands in `data/` (gitignored).

## Why per-organization documents

File Search chunks uploads with a whitespace/token splitter that ignores row
boundaries, so a raw CSV (or one big JSON) can yield chunks that start mid-row
and lose the org name — details from one nonprofit can then surface attributed
to another. Chunks never cross document boundaries, so both pipelines emit **one
self-contained Markdown profile per organization** (H1 + labeled fields) and
upload each with `chunking_config` of 500 tokens/chunk. Every profile is well
under 500 tokens (the converters warn otherwise), so each org is exactly one
chunk: cross-org misattribution is structurally impossible.

## Intervention tags

Both collections carry the intervention taxonomy from SDI's State of the
Movement survey, canonically stored in
`src/country_profiles/intervention_tags.py` (codes like `PUB-Investigations`,
`MVT-Training`). Tags are stored twice, deliberately:

- **In the profile body** as expanded human-readable labels (plus the raw codes
  for the SDI collection) — this is what semantic File Search retrieval
  actually matches on.
- **As `intervention_tags` custom metadata** (`string_list_value`) — used by
  `internal_researcher.py`, which runs a supplementary metadata-filtered
  movement-map retrieval for the "existing players doing similar work"
  dimension (`build_tag_filter()` builds the filter; `verify_profiles.py`
  validates the grammar against the live store).

SDI tags with a `?` suffix (analyst-unverified) render as "(unverified)" in the
body and are stripped to the bare code in metadata. The SDI sheet's five
per-category tag columns are a redundant split of "Tags (all)" and are ignored.
The ACE sheet has no tag codes — its free-text interventions menu is mapped to
codes by label matching in `ACE_Movement-Map/convert.py` (`MENU_TAG_ALIASES`
holds any values that don't match automatically; unmatched cells are reported
at the end of a convert run).

Other metadata: ACE docs keep organization / country / regions_of_operation /
budget_tier / animals_helped / interventions / ace_history; SDI docs carry
organization / ref / entity_type / status / movement_position / role / city /
state / founded / interventions. Both add `source` identifying the collection.

## Prerequisites

- `GOOGLE_API_KEY` in the repo-root `.env` (same as the other filestore
  scripts) — needed for upload/verify only; the converters are stdlib-only.
- The source CSV saved somewhere **outside the repo**.

## Runbook

All commands from `scripts/filestore_scripts/movement_map/`.

```bash
# 0. The store already exists (MOVEMENT_MAP_STORE in ../config.py). To recreate
#    from scratch: python ../setup_store.py --name "Movement Map" and paste the
#    printed fileSearchStores/... ID into config.py + internal_researcher.py.

# 1. Convert CSV → per-org Markdown + manifest (stdlib-only, no API key needed)
python ACE_Movement-Map/convert.py --csv /path/to/ace_movement_map.csv
python Stray-Dog-Institute_Movement-Map/convert.py --csv /path/to/sdi_directory.csv

# 2. Upload (parallel; resumes automatically if interrupted)
python upload_profiles.py --manifest ../../../data/ACE_Movement-Map/ace_movement_map_manifest.json
python upload_profiles.py --manifest ../../../data/Stray-Dog-Institute_Movement-Map/sdi_movement_map_manifest.json

# 3. Verify attribution integrity + metadata filters (attribution spot-checks,
#    the intervention_tags list filter incl. the OR form the agent uses, and
#    optionally a string filter via --country for the ACE manifest)
python verify_profiles.py --manifest ../../../data/ACE_Movement-Map/ace_movement_map_manifest.json --seed 42 --country Spain
python verify_profiles.py --manifest ../../../data/Stray-Dog-Institute_Movement-Map/sdi_movement_map_manifest.json --seed 42
```

Useful flags: `--dry-run` and `--limit N` on the uploader for a smoke test;
`--sample N` on the verifier.

## One-time migration from the old single-collection naming

Docs uploaded before the split carry display names `Movement Map - {org}`.
`--replace` only deletes docs matching the NEW manifest's names, so a plain
re-upload would leave 957 orphans. Purge the old prefix while uploading the
renamed ACE collection (exact prefix match — it cannot touch either new
collection's names):

```bash
python upload_profiles.py \
    --manifest ../../../data/ACE_Movement-Map/ace_movement_map_manifest.json \
    --purge-prefix "Movement Map - "
```

## Refreshing after a sheet update

Re-export the CSV, re-run that collection's `convert.py`, then upload with
`--replace`:

```bash
python upload_profiles.py --manifest <that collection's manifest> --replace
```

`--replace` deletes each existing document by display name before re-uploading,
so the store always holds exactly one current profile per org. Orgs removed
from the sheet are NOT auto-deleted; remove them manually or recreate the store.
The other collection is untouched.

## Agent wiring (done)

The store is registered end to end:

1. `scripts/filestore_scripts/config.py` — `MOVEMENT_MAP_STORE` holds the store
   ID (kept in sync with `internal_researcher.py`).
2. `src/country_profiles/internal_researcher.py` — constant + `STORE_REGISTRY`
   entry (`movement_map`) + `DATA_SOURCE_DESCRIPTIONS` entry; the
   `team_players` dimension additionally runs the tag-filtered supplementary
   retrieval (`_tag_filtered_movement_scan`).
3. `EVAL_DIMENSIONS`: `movement_map` feeds `team_players` (Existing Players
   Doing Similar Work — overlap surfaced as alliance/coalition potential),
   `challenges_landscape` (How the Movement Is Performing — aggregate texture
   only; the map is a directory, not a scorecard), and `windows_unspotted`
   (coalition/partner opportunities); it is also searched by the On-the-Ground
   Experts writer.
4. `scripts/filestore_scripts/upload_to_store.py` — `"movement-map"` alias.
5. `frontend/web/src/lib/sources.ts` — "Movement Map (ACE + Stray Dog
   Institute)" source checkbox (checked by default).

Citations show as `ACE Movement Map - {Organization}` or
`Stray Dog Institute Movement Map - {Name}`; no citation-rule exception is
needed since each document is a single logical record.
