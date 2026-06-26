#!/usr/bin/env python3
"""Monthly refresh for the project's RAG scraper sources (registry-driven).

Each scraper source defines an ordered list of stages (scrape → parse →
[deep-fetch] → upload). Choose one with ``--source``; the cron wrapper passes the
source name so different sources can run on different days of the month. Each
source has its own lockfile, so independent schedules never collide.

Adding a new scraper is small and local: drop its scripts under
``scripts/scraper_scripts/<source>/`` and add one entry to ``build_pipelines``.

Deployment-agnostic — run by hand, from cron, or in a container. Each stage runs
as a subprocess in its own directory because the stage scripts import ``config``
relative to the working directory and read/write relative ``data_*`` folders.
Fails fast and exits non-zero on the first stage failure so a scheduler can alert.

Usage:
    python scripts/run_monthly_refresh.py --source pib
    python scripts/run_monthly_refresh.py --source icnl
"""
import sys
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SCRAPER_DIR = SCRIPTS_DIR / "scraper_scripts"
ICNL_DIR = SCRAPER_DIR / "icnl"
FILESTORE_DIR = SCRIPTS_DIR / "filestore_scripts"

# PIB publishes immutable per-month archives; don't publish the current or
# previous month (their indexes still grow). Must match
# scraper_scripts/common/month_logic.is_settled_month (upload months >= 2 old).
PIB_SKIP_RECENT_MONTHS = "2"

# Stable display name of the single ICNL living document (see icnl/config.py).
ICNL_SNAPSHOT = "icnl_civic_freedom_monitor_india.md"


class Stage:
    """One pipeline step: a subprocess argv run in a specific directory."""

    def __init__(self, name: str, argv: list[str], cwd: Path):
        self.name = name
        self.argv = argv
        self.cwd = cwd


def build_pipelines(py: str) -> dict[str, list[Stage]]:
    """Map source name -> ordered stages. ``py`` is the current interpreter."""
    pib_full_text = SCRAPER_DIR / "data_full_text"
    icnl_snapshot = ICNL_DIR / "data_markdown" / ICNL_SNAPSHOT
    return {
        # GoI / Ministry of Fisheries PIB press releases — append-only per-month
        # archives; upload only settled months (manifest dedups duplicates).
        "pib": [
            Stage("fetch index", [py, "pib_fetcher.py"], SCRAPER_DIR),
            Stage("parse index", [py, "pib_parser.py"], SCRAPER_DIR),
            Stage("fetch full text", [py, "pib_deep_fetcher.py"], SCRAPER_DIR),
            Stage("upload", [
                py, "upload_to_store.py",
                "--dir", str(pib_full_text),
                "--store", "goi-pib",
                "--mode", "md-only",
                "--skip-recent-months", PIB_SKIP_RECENT_MONTHS,
            ], FILESTORE_DIR),
        ],
        # ICNL Civic Freedom Monitor (India) — a single living document; always
        # replace the one snapshot in the store (delete old by display name + upload).
        "icnl": [
            Stage("fetch page", [py, "fetch.py"], ICNL_DIR),
            Stage("parse page", [py, "parse.py"], ICNL_DIR),
            Stage("upload", [
                py, "upload_to_store.py",
                "--file", str(icnl_snapshot),
                "--store", "regulatory-environment",
                "--replace-by-display-name",
            ], FILESTORE_DIR),
        ],
    }


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def run_stage(stage: Stage) -> None:
    log(f"START {stage.name}: {' '.join(stage.argv)} (cwd={stage.cwd})")
    result = subprocess.run(stage.argv, cwd=str(stage.cwd))
    if result.returncode != 0:
        log(f"FAIL  {stage.name}: exit {result.returncode}")
        raise SystemExit(result.returncode)
    log(f"OK    {stage.name}")


def main() -> None:
    pipelines = build_pipelines(sys.executable)
    parser = argparse.ArgumentParser(description="Run a monthly RAG refresh for one scraper source.")
    parser.add_argument("--source", required=True, choices=sorted(pipelines),
                        help="Which scraper source to refresh.")
    args = parser.parse_args()

    stages = pipelines[args.source]
    lockfile = SCRIPTS_DIR / f".monthly_refresh_{args.source}.lock"
    if lockfile.exists():
        log(f"Another '{args.source}' run appears to be in progress ({lockfile}); exiting.")
        raise SystemExit(1)
    lockfile.write_text(datetime.now().isoformat())
    try:
        log(f"START refresh: source={args.source} ({len(stages)} stages)")
        for stage in stages:
            run_stage(stage)
        log(f"DONE: '{args.source}' refresh complete.")
    finally:
        lockfile.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
