"""Configuration for the ICNL Civic Freedom Monitor (India) scraper.

The ICNL page is a single living document (one "Last updated" date, edited in
place), so this source has no per-month / settled-month logic: every run yields
one snapshot that REPLACES the previous one in the file store.
"""
from pathlib import Path

# --- Target page ---
ICNL_INDIA_URL = "https://www.icnl.org/resources/civic-freedom-monitor/india"

# --- Pipeline directories (relative to the working directory) ---
DATA_HTML_DIR = Path("data_html")          # rendered page HTML       (fetch → parse)
DATA_MARKDOWN_DIR = Path("data_markdown")  # clean markdown snapshot  (parse → upload)

# --- File store ---
# Alias resolved by filestore_scripts/upload_to_store.py -> REGULATORY_ENVIRONMENT_STORE.
STORE_ALIAS = "regulatory-environment"
# Stable display name for the single living document. Kept clean (no date) so the
# agent cites it sensibly and the "always replace" upload can find and delete the
# prior copy by this exact name before re-uploading.
SNAPSHOT_BASENAME = "icnl_civic_freedom_monitor_india"
