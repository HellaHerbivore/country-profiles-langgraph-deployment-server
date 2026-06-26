"""Configuration for the PIB scraper pipeline.

Month-lifecycle logic now lives in the shared ``common.month_logic`` module so it
can be reused by other archive-style scrapers; it is re-exported here so the
existing ``from config import is_settled_month`` in the PIB stages keeps working.
"""
from pathlib import Path

from common.month_logic import is_settled_month  # noqa: F401 (re-exported)

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