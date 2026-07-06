# Movement Map ingestion

Ingests ACE's Movement Map 2026 spreadsheet (confidential CSV export, ~957
organizations) into a dedicated Gemini File Search store named **"Movement Map"**.

## Why per-organization documents

File Search chunks uploads with a whitespace/token splitter that ignores row
boundaries, so a raw CSV (or one big JSON) can yield chunks that start mid-row
and lose the org name — details from one nonprofit can then surface attributed
to another. Chunks never cross document boundaries, so this pipeline emits **one
self-contained Markdown profile per organization** (H1 + labeled fields) and
uploads each with `chunking_config` of 500 tokens/chunk. Every profile is well
under 500 tokens, so each org is exactly one chunk: cross-org misattribution is
structurally impossible. Structured fields (organization, country, budget_tier,
animals_helped, interventions, ace_history, regions_of_operation) are also
attached as `custom_metadata` for `metadata_filter` queries.

The document `display_name` is `Movement Map - {Organization}.md`, so agent
citations render as "Movement Map - {Organization}".

## Prerequisites

- `GOOGLE_API_KEY` in the repo-root `.env` (same as the other filestore scripts)
- The CSV export saved somewhere **outside the repo** (it is confidential; the
  generated docs land in `data/movement_map/`, which is gitignored)

## Runbook

All commands from `scripts/filestore_scripts/movement_map/`.

```bash
# 1. Create the store (once). Paste the printed fileSearchStores/... ID into
#    MOVEMENT_MAP_STORE in scripts/filestore_scripts/config.py.
python ../setup_store.py --name "Movement Map"

# 2. Convert CSV → per-org Markdown + manifest (stdlib-only, no API key needed)
python convert_movement_map.py --csv /path/to/movement_map.csv

# 3. Upload (parallel; resumes automatically if interrupted)
python upload_movement_map.py --manifest ../../../data/movement_map/movement_map_manifest.json

# 4. Verify attribution integrity (spot-checks that answers about an org cite
#    ONLY that org's document, plus a metadata_filter smoke test)
python verify_movement_map.py --manifest ../../../data/movement_map/movement_map_manifest.json --seed 42
```

Useful flags: `--dry-run` and `--limit N` on the uploader for a smoke test;
`--sample N` on the verifier.

## Refreshing after a sheet update

Re-export the CSV, then:

```bash
python convert_movement_map.py --csv /path/to/new_export.csv
python upload_movement_map.py --manifest ../../../data/movement_map/movement_map_manifest.json --replace
```

`--replace` deletes each existing document by display name before re-uploading,
so the store always holds exactly one current profile per org. Orgs removed
from the sheet are NOT auto-deleted; remove them manually or recreate the store.

## Follow-up: wiring the store into the agent (not done yet)

Once the store is populated and verified:

1. `scripts/filestore_scripts/config.py` — `MOVEMENT_MAP_STORE` already holds the ID.
2. `src/country_profiles/internal_researcher.py` — add the same constant next to
   the other store IDs (~line 36-40), a `STORE_REGISTRY` entry (~line 43-49), and
   a `DATA_SOURCE_DESCRIPTIONS` entry (~line 57-63).
3. Add the `movement_map` key to the relevant `EVAL_DIMENSIONS` entries
   (~line 473-546) so retrieval fans out to this store where it matters.
4. Optional: add a `"movement-map"` alias in `scripts/filestore_scripts/upload_to_store.py`.

Citations will show as `Movement Map - {Organization}`; no citation-rule
exception is needed since each document is a single logical record.
