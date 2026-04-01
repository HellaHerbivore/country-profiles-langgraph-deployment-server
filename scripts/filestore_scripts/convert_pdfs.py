import argparse
from pathlib import Path
from colorama import Fore, Style
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

# Initialize converter ONCE (loads ~1GB of models into memory)
print("Loading Marker models... (this may take a minute the first time)")
converter = PdfConverter(artifact_dict=create_model_dict())
print(f"{Fore.GREEN}Models loaded.{Style.RESET_ALL}")

def convert_single_pdf(input_path: Path, output_dir: Path) -> Path | None:
    """Convert one PDF to Markdown. Returns output path or None on failure."""
    output_file = output_dir / f"{input_path.stem}_extracted.md"

    # Idempotency: skip if markdown already exists and is newer than PDF
    if output_file.exists() and output_file.stat().st_mtime > input_path.stat().st_mtime:
        print(f"  Skipping (already converted): {input_path.name}")
        return output_file

    try:
        rendered = converter(str(input_path))
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file.write_text(rendered.markdown, encoding="utf-8")
        print(f"  {Fore.GREEN}✅ Converted: {input_path.name}{Style.RESET_ALL}")
        return output_file
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  Failed: {input_path.name} — {e}")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert academic PDFs to Markdown using Marker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-dir", type=Path, help="Directory of PDFs to convert")
    group.add_argument("--input-file", type=Path, help="Single PDF file to convert")
    parser.add_argument("--output-dir", type=Path, required=True, help="Where to save Markdown files")

    args = parser.parse_args()

    if args.input_file:
        convert_single_pdf(args.input_file, args.output_dir)
    else:
        pdfs = list(args.input_dir.glob("*.pdf"))
        print(f"Found {len(pdfs)} PDFs")
        succeeded, failed = 0, 0
        for pdf in pdfs:
            result = convert_single_pdf(pdf, args.output_dir)
            if result:
                succeeded += 1
            else:
                failed += 1
        print(f"\nDone! Converted: {succeeded}, Failed: {failed}")

