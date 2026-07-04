"""Stage 1 — render the ICNL India page (expanded) and save its HTML.

ICNL Civic Freedom Monitor pages are server-rendered accordions: the body text
under each collapsible heading is already in the DOM, just visually collapsed.
We still drive Camoufox (the project's scraping browser, which also clears
ICNL's bot protection the same way it clears PIB's Akamai wall) to click the
"expand all subheadings" controls and any remaining accordion toggles, so that
anything *lazily* revealed on expand is captured too. Then we save the full
page HTML for the parser. Best-effort throughout — the parser reads the whole
DOM regardless of collapse state, so a failed click never loses content.
"""
from camoufox.async_api import AsyncCamoufox
import asyncio
import random

from config import ICNL_INDIA_URL, DATA_HTML_DIR, SNAPSHOT_BASENAME


async def _reveal_all_sections(page) -> None:
    """Best-effort expand of every collapsible section so all content is in the DOM."""
    # 1. Click the page-level + per-section "expand all subheadings" controls.
    try:
        controls = page.get_by_text("expand all subheadings", exact=False)
        for i in range(await controls.count()):
            try:
                await controls.nth(i).click(timeout=3000)
                await page.wait_for_timeout(random.uniform(400, 900))
            except Exception:
                continue
    except Exception:
        pass

    # 2. Defensive sweep: click any remaining collapsed accordion toggles.
    #    aria-expanded="false" is the standard marker for a collapsed control.
    try:
        toggles = page.locator('[aria-expanded="false"]')
        for i in range(await toggles.count()):
            try:
                await toggles.nth(i).click(timeout=2000)
                await page.wait_for_timeout(random.uniform(200, 500))
            except Exception:
                continue
    except Exception:
        pass

    # Let any expand animations / lazily-loaded content settle.
    await page.wait_for_timeout(1500)


async def fetch_icnl_page() -> None:
    out_dir = DATA_HTML_DIR
    out_dir.mkdir(exist_ok=True)

    print("1. Starting Camoufox (virtual headless)...")
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()

        print(f"2. Loading {ICNL_INDIA_URL} ...")
        await page.goto(ICNL_INDIA_URL, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle")
        except Exception:
            pass
        await page.wait_for_timeout(random.uniform(3000, 5000))

        print("3. Expanding all collapsible sections...")
        await _reveal_all_sections(page)

        print("4. Capturing full page HTML...")
        try:
            html = await page.content()
        except Exception:
            # ASP-style postback races aside, ICNL is mostly static; one retry.
            await page.wait_for_timeout(2000)
            html = await page.content()

        out_file = out_dir / f"{SNAPSHOT_BASENAME}.html"
        out_file.write_text(html, encoding="utf-8")
        print(f"SUCCESS: saved {len(html):,} bytes to {out_file}")


if __name__ == "__main__":
    asyncio.run(fetch_icnl_page())
