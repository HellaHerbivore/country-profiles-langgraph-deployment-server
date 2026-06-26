"""ICNL Civic Freedom Monitor (India) scraper.

A self-contained scraper source: ``fetch.py`` renders the page (expanding its
collapsible sections) and saves the HTML, ``parse.py`` turns that into a single
clean Markdown snapshot. Unlike the PIB source this is a *living document* — one
page edited in place — so there is no per-month archive logic: each run produces
one snapshot that replaces the previous one in the file store.
"""
