import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from colorama import Fore, Style
from config import get_client, FOREIGN_ACADEMIC_STORE, GROUND_TRUTH_STORE, LOCAL_ACADEMIC_STORE

# Store aliases for convenience
STORE_ALIASES = {
    "foreign-academic": FOREIGN_ACADEMIC_STORE,
    "ground-truth": GROUND_TRUTH_STORE,
    "local-academic": LOCAL_ACADEMIC_STORE,
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


# CLI Interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload files to a Gemini File Search Store")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir", type=Path, help="Directory of files to upload")
    group.add_argument("--file", type=Path, help="Single file to upload")
    parser.add_argument("--store", required=True, help="Store name/ID or alias (foreign-academic, ground-truth, local-academic)")
    parser.add_argument("--mode", choices=["pdf-only", "md-only", "both"], default="both", help="Which file types to upload (default: both)")

    args = parser.parse_args()

    # Resolve store alias or use raw ID
    store_name = STORE_ALIASES.get(args.store, args.store)
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

    manifest = load_manifest()
    uploaded, skipped, failed = 0, 0, 0

    for f in files:
        if is_already_uploaded(manifest, f, store_name):
            print(f"  Skipping (already uploaded): {f.name}")
            skipped += 1
            continue
        if upload_single_file(store_name, f):
            record_upload(manifest, f, store_name)
            save_manifest(manifest)
            uploaded += 1
        else:
            failed += 1

    print(f"\nDone! Uploaded: {uploaded}, Skipped: {skipped}, Failed: {failed}")


