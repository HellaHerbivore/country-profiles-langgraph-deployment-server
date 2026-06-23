#!/usr/bin/env python3
"""One-time migration: drop legacy per-YEAR PIB documents from the goi-pib store.

Earlier runs uploaded one document per year (``fisheries_releases_YYYY.md``).
The pipeline now produces one document per month (``fisheries_releases_YYYY_MM.md``);
leaving the per-year documents in place would duplicate the same press releases
in retrieval. This script deletes ONLY the legacy per-year documents and prunes
their manifest entries, so the monthly refresh can backfill per-month files
cleanly. Per-month documents and every other store are left untouched.

This is a one-off cleanup (not part of the recurring refresh). Always preview
first with --dry-run.

Usage:
    python migrate_pib_to_monthly.py --dry-run   # preview
    python migrate_pib_to_monthly.py             # apply
"""
import re
import argparse

from config import get_client, GOI_PIB_STORE
from upload_to_store import load_manifest, save_manifest

# Per-YEAR display names only: "fisheries_releases_2026.md"
# (NOT the per-month "fisheries_releases_2026_06.md").
PER_YEAR_RE = re.compile(r"^fisheries_releases_\d{4}\.md$")


def _delete_config():
    """force=True deletes the document even though it has chunks. Prefer the
    typed config (per Google's cookbook); fall back to a dict on older SDKs."""
    try:
        from google.genai import types
        return types.DeleteDocumentConfig(force=True)
    except (ImportError, AttributeError):
        return {"force": True}


def main() -> None:
    ap = argparse.ArgumentParser(description="Delete legacy per-year PIB docs from the goi-pib store")
    ap.add_argument("--dry-run", action="store_true", help="List what would change without deleting")
    args = ap.parse_args()

    client = get_client()
    store = GOI_PIB_STORE
    print(f"Store: {store}")
    if args.dry_run:
        print("DRY RUN — nothing will be deleted\n")

    # 1. Find legacy per-year documents in the store.
    to_delete = []
    for doc in client.file_search_stores.documents.list(parent=store):
        name = getattr(doc, "display_name", "") or ""
        if PER_YEAR_RE.match(name):
            to_delete.append(doc)

    if not to_delete:
        print("No legacy per-year documents found in the store.")
    for doc in to_delete:
        if args.dry_run:
            print(f"  Would delete: {doc.display_name} ({doc.name})")
        else:
            client.file_search_stores.documents.delete(name=doc.name, config=_delete_config())
            print(f"  Deleted: {doc.display_name} ({doc.name})")

    # 2. Prune matching manifest entries: keys look like "<store>::fisheries_releases_YYYY.md".
    manifest = load_manifest()
    pruned = []
    for key in list(manifest.keys()):
        store_part, _, fname = key.partition("::")
        if store_part == store and PER_YEAR_RE.match(fname):
            pruned.append(key)
            if not args.dry_run:
                del manifest[key]
    if pruned:
        print(f"\nManifest: {'would prune' if args.dry_run else 'pruned'} {len(pruned)} per-year key(s):")
        for k in pruned:
            print(f"  {k}")
        if not args.dry_run:
            save_manifest(manifest)
    else:
        print("\nManifest: no per-year keys to prune.")

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Done. "
          f"{'Would delete' if args.dry_run else 'Deleted'} {len(to_delete)} document(s).")


if __name__ == "__main__":
    main()
