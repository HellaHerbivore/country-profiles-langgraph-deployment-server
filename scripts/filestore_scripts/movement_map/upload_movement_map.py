"""Upload the converted Movement Map org profiles to the "Movement Map"
Gemini File Search store, manifest-driven and in parallel.

Row-integrity design (see convert_movement_map.py): one document per org, plus
an explicit chunking_config sized so every profile (max ~400 tokens) lands in a
single chunk. Each upload also attaches custom_metadata (organization, country,
budget_tier, ...) so queries can use metadata_filter later.

Usage:
    python upload_movement_map.py \
        --manifest ../../../data/movement_map/movement_map_manifest.json \
        [--store fileSearchStores/...] [--replace] [--dry-run] [--workers 8] [--limit N]
"""

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from colorama import Fore, Style

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import get_client, MOVEMENT_MAP_STORE  # noqa: E402

client = get_client()

# Every org profile fits in one chunk (largest row ≈ 400 tokens with labels), so a
# chunk can never mix two organizations. The overlap is belt-and-suspenders: if a
# future, longer profile ever splits, the overlap carries the H1 org name forward.
CHUNKING_CONFIG = {
    "white_space_config": {
        "max_tokens_per_chunk": 500,
        "max_overlap_tokens": 60,
    }
}

# Tracks what has already been uploaded so interrupted runs resume where they left off.
UPLOAD_LOG_PATH = Path(__file__).parent / ".movement_map_upload_manifest.json"
_log_lock = threading.Lock()


def load_upload_log() -> dict:
    if UPLOAD_LOG_PATH.exists():
        return json.loads(UPLOAD_LOG_PATH.read_text())
    return {}


def record_upload(log: dict, store_name: str, display_name: str):
    with _log_lock:
        log[f"{store_name}::{display_name}"] = {"uploaded_at": datetime.now().isoformat()}
        UPLOAD_LOG_PATH.write_text(json.dumps(log, indent=2))


def upload_one(store_name: str, doc_dir: Path, entry: dict, max_retries: int = 3) -> bool:
    file_path = doc_dir / entry["file"]
    display_name = entry["display_name"]
    config = {
        "display_name": display_name,
        "chunking_config": CHUNKING_CONFIG,
        "custom_metadata": [
            {"key": k, "string_value": v} for k, v in entry.get("custom_metadata", {}).items()
        ],
    }
    for attempt in range(max_retries):
        try:
            operation = client.file_search_stores.upload_to_file_search_store(
                file=str(file_path),
                file_search_store_name=store_name,
                config=config,
            )
            while not operation.done:
                time.sleep(2)
                operation = client.operations.get(operation)
            return True
        except Exception as e:
            # Rate limits need a longer pause than transient errors
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            wait = (10 if is_rate_limit else 2) * (2 ** attempt)
            print(f"  {Fore.YELLOW}⚠️  {display_name}: attempt {attempt + 1} failed: {e}{Style.RESET_ALL}")
            if attempt < max_retries - 1:
                time.sleep(wait)
    return False


def delete_all_by_display_names(store_name: str, display_names: set[str], dry_run: bool) -> int:
    """One documents.list pass, then delete every doc whose display name is in the set."""
    from google.genai import types
    try:
        docs = list(client.file_search_stores.documents.list(parent=store_name))
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️  Could not list documents to replace: {e}{Style.RESET_ALL}")
        return 0
    deleted = 0
    for doc in docs:
        display = getattr(doc, "display_name", "") or ""
        if display not in display_names:
            continue
        if dry_run:
            print(f"  Would delete existing: {display}")
            deleted += 1
            continue
        try:
            client.file_search_stores.documents.delete(
                name=doc.name, config=types.DeleteDocumentConfig(force=True))
            deleted += 1
        except Exception as e:
            print(f"  {Fore.YELLOW}⚠️  Failed to delete {doc.name}: {e}{Style.RESET_ALL}")
    return deleted


def count_documents(store_name: str) -> int | None:
    try:
        return sum(1 for _ in client.file_search_stores.documents.list(parent=store_name))
    except Exception as e:
        print(f"{Fore.YELLOW}⚠️  Could not count documents: {e}{Style.RESET_ALL}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload Movement Map org profiles to a File Search store")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="movement_map_manifest.json produced by convert_movement_map.py")
    parser.add_argument("--store", default=MOVEMENT_MAP_STORE,
                        help="Store ID (default: MOVEMENT_MAP_STORE from config.py)")
    parser.add_argument("--replace", action="store_true",
                        help="Delete existing docs with matching display names before uploading "
                             "(sheet-refresh mode; also bypasses the local resume log)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without uploading")
    parser.add_argument("--workers", type=int, default=8, help="Parallel uploads (default: 8)")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N entries (smoke test)")
    args = parser.parse_args()

    if not args.store or not args.store.startswith("fileSearchStores/"):
        sys.exit("❌ No valid store ID. Run `python ../setup_store.py --name \"Movement Map\"` once, "
                 "paste the printed fileSearchStores/... ID into MOVEMENT_MAP_STORE in "
                 "scripts/filestore_scripts/config.py, or pass --store.")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    doc_dir = args.manifest.parent
    entries = manifest["documents"]
    if args.limit:
        entries = entries[: args.limit]
    print(f"Target store: {args.store}")
    print(f"Manifest: {len(entries)} documents ({manifest.get('generated_at', 'unknown date')})")

    missing = [e["file"] for e in entries if not (doc_dir / e["file"]).exists()]
    if missing:
        sys.exit(f"❌ {len(missing)} file(s) in the manifest are missing from {doc_dir} "
                 f"(e.g. {missing[:3]}). Re-run convert_movement_map.py.")

    upload_log = load_upload_log()

    if args.replace:
        names = {e["display_name"] for e in entries}
        deleted = delete_all_by_display_names(args.store, names, args.dry_run)
        print(f"{'Would delete' if args.dry_run else 'Deleted'} {deleted} existing document(s)")
        to_upload = entries
    else:
        to_upload, skipped_entries = [], 0
        for e in entries:
            if f"{args.store}::{e['display_name']}" in upload_log:
                skipped_entries += 1
            else:
                to_upload.append(e)
        if skipped_entries:
            print(f"Skipping {skipped_entries} already-uploaded document(s) (resume log)")

    if args.dry_run:
        for e in to_upload[:10]:
            print(f"  Would upload: {e['display_name']}")
        if len(to_upload) > 10:
            print(f"  ... and {len(to_upload) - 10} more")
        print(f"\nDRY RUN — would upload {len(to_upload)} document(s)")
        sys.exit(0)

    uploaded, failed = 0, []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(upload_one, args.store, doc_dir, e): e for e in to_upload}
        for future in as_completed(futures):
            entry = futures[future]
            if future.result():
                record_upload(upload_log, args.store, entry["display_name"])
                uploaded += 1
                if uploaded % 25 == 0:
                    print(f"  ...{uploaded}/{len(to_upload)} uploaded")
            else:
                failed.append(entry["display_name"])
                print(f"  {Fore.RED}❌ Failed: {entry['display_name']}{Style.RESET_ALL}")

    print(f"\nDone! Uploaded: {uploaded}, Failed: {len(failed)}")
    if failed:
        print(f"{Fore.RED}Failed documents (re-run to retry — resume log skips successes):{Style.RESET_ALL}")
        for name in failed:
            print(f"  - {name}")

    total = count_documents(args.store)
    if total is not None:
        expected = manifest["expected_count"]
        marker = "✅" if total == expected else "⚠️ "
        print(f"{marker} Store now holds {total} documents (manifest expects {expected})")
