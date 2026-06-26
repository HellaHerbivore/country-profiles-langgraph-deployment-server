"""Stage 2 — turn the rendered ICNL HTML into one clean Markdown snapshot.

Reads the HTML saved by ``fetch.py``, strips site chrome (nav / header / footer /
forms / buttons), converts the main report container to Markdown, and writes a
single stable file (``icnl_civic_freedom_monitor_india.md``). The whole page is
captured — Recent Developments, Introduction, Legal Analysis and all of its
subsections, and Additional Resources — because collapsed accordion text is in
the DOM and ``get_text``/markdownify read it regardless of visibility.
"""
import re
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from config import DATA_HTML_DIR, DATA_MARKDOWN_DIR, SNAPSHOT_BASENAME, ICNL_INDIA_URL

# Page chrome we never want in the snapshot.
_STRIP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "form", "select", "button", "svg"]

# Boilerplate control text to drop when it appears as its own Markdown line.
_BOILERPLATE_LINES = {
    "back to top",
    "download as pdf",
    "expand all subheadings",
    "click here to expand all subheadings",
    "donate to icnl",
    "sign up",
    "sign up for our newsletters",
}


def _select_main(soup: BeautifulSoup):
    """Return the main report container, falling back progressively."""
    for finder in (
        lambda: soup.find("main"),
        lambda: soup.find(attrs={"role": "main"}),
        lambda: soup.find("article"),
        lambda: soup.body,
    ):
        node = finder()
        if node is not None:
            return node
    return soup


def _is_boilerplate_line(line: str) -> bool:
    """True for a line that is only a boilerplate control, including when
    markdownify wrapped it as a single link, e.g. ``[Back To Top](#top)``."""
    s = line.strip()
    m = re.fullmatch(r"\[(.+?)\]\([^)]*\)\.?", s)  # unwrap a lone [text](url) line
    if m:
        s = m.group(1)
    return s.lower() in _BOILERPLATE_LINES


def _extract_last_updated(text: str) -> str | None:
    """Pull e.g. 'June 25, 2026' out of 'Last updated: June 25, 2026'."""
    m = re.search(r"Last updated:\s*([A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})", text)
    return m.group(1).strip() if m else None


def parse_icnl_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    last_updated = _extract_last_updated(soup.get_text(" ", strip=True))

    main = _select_main(soup)
    for tag in main.find_all(_STRIP_TAGS):
        tag.decompose()

    body_md = md(str(main), heading_style="ATX")

    # Drop boilerplate-only lines and collapse runs of blank lines.
    kept = [line.rstrip() for line in body_md.splitlines() if not _is_boilerplate_line(line)]
    body_md = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()

    header = ["# ICNL Civic Freedom Monitor — India"]
    if last_updated:
        header.append(f"**Last updated:** {last_updated}")
    header.append(f"**Source:** {ICNL_INDIA_URL}")
    return "\n\n".join(header) + "\n\n" + body_md + "\n"


def main() -> None:
    DATA_MARKDOWN_DIR.mkdir(exist_ok=True)
    html_file = DATA_HTML_DIR / f"{SNAPSHOT_BASENAME}.html"
    if not html_file.exists():
        raise SystemExit(f"No HTML found at {html_file}. Run fetch.py first.")

    markdown = parse_icnl_html(html_file.read_text(encoding="utf-8"))
    out_file = DATA_MARKDOWN_DIR / f"{SNAPSHOT_BASENAME}.md"
    out_file.write_text(markdown, encoding="utf-8")
    print(f"SUCCESS: wrote {len(markdown):,} chars to {out_file}")


if __name__ == "__main__":
    main()
