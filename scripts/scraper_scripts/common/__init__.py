"""Shared helpers used across scraper-source pipelines.

Each scraper source lives in its own package under ``scripts/scraper_scripts/``
(the flat ``pib_*.py`` files are the original "source 0"; newer sources such as
``icnl/`` are self-contained subpackages). Anything genuinely shared between
sources — e.g. the month-lifecycle logic — lives here so a source folder only
holds what is specific to it.
"""
