import re
import time
import json
import argparse
from pathlib import Path
from datetime import datetime, date
from colorama import Fore, Style
from config import (
    get_client,
    FOREIGN_ACADEMIC_STORE,
    ON_GROUND_ADVOCATE_STORE,
    LOCAL_ACADEMIC_STORE,
    GOI_PIB_STORE,
    REGULATORY_ENVIRONMENT_STORE,
    MOVEMENT_MAP_STORE,
)

# Store aliases for convenience
STORE_ALIASES = {
    "foreign-academic": FOREIGN_ACADEMIC_STORE,
    "on-ground": ON_GROUND_ADVOCATE_STORE,
    "local-academic": LOCAL_ACADEMIC_STORE,
    "goi-pib": GOI_PIB_STORE,
    "regulatory-environment": REGULATORY_ENVIRONMENT_STORE,
    "movement-map": MOVEMENT_MAP_STORE,
}

client = get_client()

def upload_single_file(store_name: str, file_path: Path, max_retries=3) -> bool:
    """Upload one file to a Gemini File Search Store with retry."""
    # Size check (100MB limit)
    if file_path.stat().st_size > 100 * 1024 * 1024:
        print(f"  {Fore.RED}❌ Skipping (>100MB): {file_path.name}{Style.RESET_ALL}")
        return False

    for attempt in range(max_retries):
        try:
            operation = client.file_search_stores.upload_to_file_search_store(
                file=str(file_path),
                file_search_store_name=store_name,
                config={'display_name': file_path.name},
            )
            while not operation.done:
                print("  ...indexing...")
                time.sleep(3)
                operation = client.operations.get(operation)
            print(f"  {Fore.GREEN}✅ Uploaded: {file_path.name}{Style.RESET_ALL}")
            return True
        except Exception as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f"  {Fore.YELLOW}⚠️  Attempt {attempt + 1} failed: {e}{Style.RESET_ALL}")
            if attempt < max_retries - 1:
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)

    print(f"  {Fore.RED}❌ Failed after {max_retries} attempts: {file_path.name}{Style.RESET_ALL}")
    return False

# Check for if the file exists already
MANIFEST_PATH = Path(__file__).parent / ".upload_manifest.json"

def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}

def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

def is_already_uploaded(manifest: dict, file_path: Path, store_name: str) -> bool:
    key = f"{store_name}::{file_path.name}"
    return key in manifest

def record_upload(manifest: dict, file_path: Path, store_name: str):
    key = f"{store_name}::{file_path.name}"
    manifest[key] = {"uploaded_at": datetime.now().isoformat()}


def _delete_document_config():
    """force=True deletes a document even though it has indexed chunks. Prefer the
    typed config (per Google's cookbook); fall back to a dict on older SDKs."""
    try:
        from google.genai import types
        return types.DeleteDocumentConfig(force=True)
    except (ImportError, AttributeError):
        return {"force": True}


def delete_docs_by_display_name(store_name: str, display_name: str, dry_run: bool = False) -> int:
    """Delete every document in the store whose display name matches; return the count.

    Used by --replace-by-display-name for *living documents* (e.g. the ICNL Civic
    Freedom Monitor page): the store should hold exactly one current copy, so the
    prior one is removed before the fresh snapshot is uploaded."""
    try:
        docs = list(client.file_search_stores.documents.list(parent=store_name))
    except Exception as e:
        print(f"  {Fore.YELLOW}⚠️  Could not list documents to replace: {e}{Style.RESET_ALL}")
        return 0
    deleted = 0
    for doc in docs:
        if (getattr(doc, "display_name", "") or "") != display_name:
            continue
        if dry_run:
            print(f"  Would delete existing: {display_name} ({doc.name})")
            deleted += 1
            continue
        try:
            client.file_search_stores.documents.delete(name=doc.name, config=_delete_document_config())
            print(f"  {Fore.CYAN}🗑️  Deleted existing: {display_name}{Style.RESET_ALL}")
            deleted += 1
        except Exception as e:
            print(f"  {Fore.YELLOW}⚠️  Failed to delete {doc.name}: {e}{Style.RESET_ALL}")
    return deleted


def is_recent_month_file(file_path: Path, skip_recent_months: int, today: date | None = None) -> bool:
    """True if the filename encodes a YYYY_MM within the last `skip_recent_months`
    months (i.e. the current/previous month, still mutable and not yet final).

    Used by the monthly refresh to publish only *settled* months, so that an
    uploaded file never changes afterwards and the manifest dedup stays correct.
    skip_recent_months=2 matches scraper config.is_settled_month. Files whose name
    carries no YYYY_MM (e.g. PDFs) are never considered recent.
    """
    if skip_recent_months <= 0:
        return False
    m = re.search(r"(\d{4})_(\d{2})$", file_path.stem)
    if not m:
        return False
    today = today or date.today()
    months_ago = (today.year - int(m.group(1))) * 12 + (today.month - int(m.group(2)))
    return 0 <= months_ago < skip_recent_months


# CLI Interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload files to a Gemini File Search Store")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", type=Path, help="Directory of files to upload")
    group.add_argument("--file", type=Path, help="Single file to upload")
    parser.add_argument("--store", required=True, help="Store name/ID or alias (foreign-academic, ground-truth, local-academic)")
    parser.add_argument("--mode", choices=["pdf-only", "md-only", "both"], default="both", help="Which file types to upload (default: both)")
    parser.add_argument("--skip-recent-months", type=int, default=0, metavar="N",
                        help="Skip files whose name ends in a YYYY_MM within the last N months "
                             "(still-mutable months). Use 2 for the monthly refresh to upload only settled months.")
    parser.add_argument("--replace-by-display-name", action="store_true",
                        help="Living-document mode: before uploading each file, delete any existing "
                             "document in the store with the same display name (the file's name), and "
                             "bypass the manifest dedup so the latest scrape always replaces the old one.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without uploading")

    args = parser.parse_args()

    # Resolve store alias or use raw ID
    store_name = STORE_ALIASES.get(args.store) or args.store
    print(f"Target store: {store_name}")

    # Collect files to upload
    if args.file:
        files = [args.file]
    else:
        if args.mode == "pdf-only":
            files = list(args.dir.glob("*.pdf"))
        elif args.mode == "md-only":
            files = list(args.dir.glob("*.md"))
        else:  # both
            files = list(args.dir.glob("*.pdf")) + list(args.dir.glob("*.md"))

    # Exclude still-mutable recent months so we only publish final, immutable files.
    if args.skip_recent_months > 0:
        recent = [f for f in files if is_recent_month_file(f, args.skip_recent_months)]
        for f in recent:
            print(f"  Skipping (recent/in-progress month, not yet final): {f.name}")
        files = [f for f in files if f not in recent]

    if args.dry_run:
        print(f"{Fore.YELLOW}DRY RUN — no files will be uploaded{Style.RESET_ALL}")

    manifest = load_manifest()
    uploaded, skipped, failed = 0, 0, 0

    for f in files:
        # Living-document mode: replace the prior copy, ignore the manifest.
        if args.replace_by_display_name:
            delete_docs_by_display_name(store_name, f.name, dry_run=args.dry_run)
            if args.dry_run:
                print(f"  Would upload (replace): {f.name}")
                continue
            if upload_single_file(store_name, f):
                uploaded += 1
            else:
                failed += 1
            continue

        # Default append-only mode: manifest dedups already-published files.
        if is_already_uploaded(manifest, f, store_name):
            print(f"  Skipping (already uploaded): {f.name}")
            skipped += 1
            continue
        if args.dry_run:
            print(f"  Would upload: {f.name}")
            continue
        if upload_single_file(store_name, f):
            record_upload(manifest, f, store_name)
            save_manifest(manifest)
            uploaded += 1
        else:
            failed += 1

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Done! Uploaded: {uploaded}, Skipped: {skipped}, Failed: {failed}")


