#!/usr/bin/env python3
"""End-to-end monthly refresh for the GoI / Ministry of Fisheries press-release
RAG source.

Scrapes the PIB index, parses it into per-month markdown, fetches the full
article text, and uploads only the *settled* (final, immutable) monthly files
into the Gemini File Search store ``goi-pib``. Uploads are append-only: each
settled month is published exactly once and never changes, so no deletes are
needed (see ``scraper_scripts/config.is_settled_month``).

Deployment-agnostic — run it by hand, from a systemd timer / cron, or in a
container. Each stage runs as a subprocess in its own directory because the
stage scripts import ``config`` relative to the working directory and write to
relative ``data_*`` folders. Fails fast and exits non-zero on the first stage
failure so a scheduler can alert.

Usage:
    python scripts/run_monthly_refresh.py
"""
import sys
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SCRAPER_DIR = SCRIPTS_DIR / "scraper_scripts"
FILESTORE_DIR = SCRIPTS_DIR / "filestore_scripts"
FULL_TEXT_DIR = SCRAPER_DIR / "data_full_text"
LOCKFILE = SCRIPTS_DIR / ".monthly_refresh.lock"

# Don't publish the current or previous month (their indexes still grow). Must
# match scraper config.is_settled_month, i.e. upload only months >= 2 old.
SKIP_RECENT_MONTHS = "2"
STORE = "goi-pib"


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def run_stage(name: str, argv: list[str], cwd: Path) -> None:
    log(f"START {name}: {' '.join(argv)} (cwd={cwd})")
    result = subprocess.run(argv, cwd=str(cwd))
    if result.returncode != 0:
        log(f"FAIL  {name}: exit {result.returncode}")
        raise SystemExit(result.returncode)
    log(f"OK    {name}")


def main() -> None:
    if LOCKFILE.exists():
        log(f"Another run appears to be in progress ({LOCKFILE}); exiting.")
        raise SystemExit(1)
    LOCKFILE.write_text(datetime.now().isoformat())
    try:
        py = sys.executable
        # 1-3: scrape (each stage uses CWD-relative config + data_* dirs)
        run_stage("fetch index", [py, "pib_fetcher.py"], SCRAPER_DIR)
        run_stage("parse index", [py, "pib_parser.py"], SCRAPER_DIR)
        run_stage("fetch full text", [py, "pib_deep_fetcher.py"], SCRAPER_DIR)
        # 4: upload only settled monthly files (append-only; manifest dedup)
        run_stage(
            "upload",
            [
                py, "upload_to_store.py",
                "--dir", str(FULL_TEXT_DIR),
                "--store", STORE,
                "--mode", "md-only",
                "--skip-recent-months", SKIP_RECENT_MONTHS,
            ],
            FILESTORE_DIR,
        )
        log("DONE: monthly refresh complete.")
    finally:
        LOCKFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
