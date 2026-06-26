"""Month-lifecycle logic shared by archive-style scrapers.

Sources that publish immutable *per-month* archives (e.g. PIB press releases)
re-scrape the current and previous month every run because those indexes keep
growing, and only treat strictly-older months as final/immutable. Keeping that
single definition here lets every downstream stage (skip-already-done in the
fetchers, upload-only-settled in the uploader) agree on when a month is "done".

Living-document sources (e.g. ICNL, a single page edited in place) do not use
this — they always replace their one document.
"""
from datetime import date


def is_settled_month(year: int, month: int, today: date | None = None) -> bool:
    """True when (year, month) is older than the *previous* calendar month.

    The current and previous month are never settled (their indexes still grow);
    everything strictly older is final/immutable and safe to publish once.
    """
    today = today or date.today()
    prev_year = today.year if today.month > 1 else today.year - 1
    prev_month = today.month - 1 if today.month > 1 else 12
    return (year, month) < (prev_year, prev_month)
