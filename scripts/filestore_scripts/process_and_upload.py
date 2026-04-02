import argparse
from pathlib import Path
from colorama import Fore, Style
from convert_pdfs import convert_single_pdf
from upload_to_store import upload_single_file, load_manifest, save_manifest, is_already_uploaded, record_upload, STORE_ALIASES
from config import get_client

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert PDFs and upload to a Gemini File Search Store")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-dir", type=Path, help="Directory of PDFs to process")
    group.add_argument("--input-file", type=Path, help="Single PDF to process")
    parser.add_argument("--output-dir", type=Path, required=True, help="Where to save Markdown files")
    parser.add_argument("--store", required=True, help="Store alias (foreign-academic, on-ground, local-academic) or full ID")
    parser.add_argument("--mode", choices=["pdf-only", "md-only", "both"], default="both", help="Which files to upload (default: both)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without doing it")
    parser.add_argument("--skip-convert", action="store_true", help="Skip Marker conversion, just upload existing files")

    args = parser.parse_args()
    store_name = STORE_ALIASES.get(args.store) or args.store

    # Gather PDFs
    if args.input_file:
        pdfs = [args.input_file]
    else:
        pdfs = list(args.input_dir.glob("*.pdf"))

    print(f"Found {len(pdfs)} PDF(s)")
    print(f"Target store: {store_name}")
    if args.dry_run:
        print(f"{Fore.YELLOW}DRY RUN — no files will be converted or uploaded{Style.RESET_ALL}\n")

    client = get_client()
    manifest = load_manifest()
    converted, uploaded, skipped, failed = 0, 0, 0, 0

    for pdf in pdfs:
        print(f"\n--- {pdf.name} ---")

        # Step 1: Convert
        md_path = None
        if not args.skip_convert:
            if args.dry_run:
                print(f"  Would convert: {pdf.name}")
            else:
                md_path = convert_single_pdf(pdf, args.output_dir)
                if md_path:
                    converted += 1
        else:
            # Look for existing markdown
            md_path = args.output_dir / f"{pdf.stem}_extracted.md"
            if not md_path.exists():
                md_path = None

        # Step 2: Upload
        files_to_upload = []
        if args.mode in ("pdf-only", "both"):
            files_to_upload.append(pdf)
        if args.mode in ("md-only", "both") and md_path:
            files_to_upload.append(md_path)

        for f in files_to_upload:
            if is_already_uploaded(manifest, f, store_name):
                print(f"  Skipping (already uploaded): {f.name}")
                skipped += 1
                continue
            if args.dry_run:
                print(f"  Would upload: {f.name}")
            else:
                if upload_single_file(store_name, f):
                    record_upload(manifest, f, store_name)
                    save_manifest(manifest)
                    uploaded += 1
                else:
                    failed += 1

    print(f"\n{'DRY RUN ' if args.dry_run else ''}Summary:")
    if not args.skip_convert:
        print(f"  Converted: {converted}")
    print(f"  Uploaded: {uploaded}, Skipped: {skipped}, Failed: {failed}")
