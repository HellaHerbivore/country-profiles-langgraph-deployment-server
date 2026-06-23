"""Shared configuration for the PIB scraper pipeline."""
from pathlib import Path
from datetime import date

# --- Target site ---
PIB_BASE_URL = "https://pib.gov.in"
# Warm-up + referer target (used by the deep fetcher)
PIB_ALL_RELEASES_URL = f"{PIB_BASE_URL}/AllRelease.aspx"
# Pre-filtered entry point (used by the index fetcher)
PIB_FISHERIES_RELEASES_URL = f"{PIB_ALL_RELEASES_URL}?MenuId=30&RegionId=3&LanguageId=1"

# --- Pipeline directories (relative to the working directory) ---
DATA_TEMP_DIR = Path("data_temp")            # raw monthly index HTML  (fetcher  → parser)
DATA_MARKDOWN_DIR = Path("data_markdown")    # parsed link index       (parser   → deep fetcher)
DATA_FULL_TEXT_DIR = Path("data_full_text")  # full article text       (deep fetcher → upload)


# --- Month lifecycle ---
def is_settled_month(year: int, month: int, today: date | None = None) -> bool:
    """True when (year, month) is older than the *previous* calendar month.

    The fetcher always re-scrapes the current and previous month because those
    indexes keep growing; only months strictly older than the previous month are
    final/immutable. Everything downstream (skip-already-done in the deep fetcher,
    upload-only-settled in the uploader) keys off this single definition so a
    file is never published while it can still change.
    """
    today = today or date.today()
    prev_year = today.year if today.month > 1 else today.year - 1
    prev_month = today.month - 1 if today.month > 1 else 12
    return (year, month) < (prev_year, prev_month)