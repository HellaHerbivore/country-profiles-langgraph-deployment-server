from camoufox.async_api import AsyncCamoufox
import asyncio
import re
import random
from config import PIB_ALL_RELEASES_URL, DATA_MARKDOWN_DIR, DATA_FULL_TEXT_DIR

async def _extract_article_text(page, retries=3, delay_ms=2000):
    """Pull article text from the release iframes, retrying when the page hasn't
    settled yet. Returns the best text found; falls back to the page body.
    Always returns whatever it has — never raises on thin content."""
    for attempt in range(retries):
        for frame in page.frames:
            try:
                text = await frame.locator("body").inner_text()
                if "Ministry of Fisheries" in text or "Posted On:" in text:
                    return text.strip()
            except Exception:
                continue
        # No matching frame yet — if we have tries left, re-wait and retry.
        if attempt < retries - 1:
            print(f"     article not ready (attempt {attempt + 1}/{retries}), re-waiting...")
            await page.wait_for_timeout(delay_ms)

    # Fallback after retries: whatever the main page body holds.
    try:
        return (await page.locator("body").inner_text()).strip()
    except Exception:
        return ""


async def fetch_full_text():
    # Setup directories
    md_dir = DATA_MARKDOWN_DIR
    output_dir = DATA_FULL_TEXT_DIR
    output_dir.mkdir(exist_ok=True)
    
    # Grab all year-based index files
    md_files = list(md_dir.glob("fisheries_releases_*.md"))
    if not md_files:
        print("No index files found in 'data_markdown'. Please run the parser first.")
        return

    print(f"Found {len(md_files)} year files. Starting the deep fetch...")
    
    # Launch browser - Visible mode helps monitor progress
    async with AsyncCamoufox(headless="virtual") as browser:
        page = await browser.new_page()
        
        # 1. Warm up the browser to get the Akamai clearance badge
        print("Warming up at the front door...")
        await page.goto(PIB_ALL_RELEASES_URL)
        await page.wait_for_timeout(6000)
        
        from datetime import date
        current_year = str(date.today().year)

        for md_file in md_files:
            # Skip a past year only if we already have its full-text output.
            # Always redo the current year (its recent months keep growing).
            year_match = re.search(r"fisheries_releases_(\d{4})", md_file.name)
            file_year = year_match.group(1) if year_match else None
            out_check = output_dir / md_file.name
            if file_year and file_year != current_year and out_check.exists():
                print(f"\n--- Skipping Year: {md_file.name} (already have full text) ---")
                continue

            print(f"\n--- Processing Year: {md_file.name} ---")
            content = md_file.read_text(encoding="utf-8")
            
            # Regex to find: * **Date**: [Title](URL)
            links = re.findall(r'\* \*\*([^*]+)\*\*: \[(.*?)\]\((https://pib\.gov\.in/.*?)\)', content)
            
            out_filepath = output_dir / md_file.name
            with open(out_filepath, "w", encoding="utf-8") as f:
                f.write(f"# FULL TEXT LOG: {md_file.name}\n\n")
                
                for date, title, url in links:
                    print(f"  -> Fetching: {title[:50]}...")
                    
                    try:
                        # Human-like delay between pages
                        await page.wait_for_timeout(random.uniform(2000, 4500))
                        
                        # Navigate with a referer header to look organic
                        await page.goto(url, referer=PIB_ALL_RELEASES_URL)
                        await page.wait_for_timeout(3000) # Wait for iframe to load content

                        # Dive into the iframes (with retry), falling back to page body.
                        article_text = await _extract_article_text(page)

                        # 4. Save to the file
                        f.write(f"## {title}\n")
                        f.write(f"**Date:** {date}\n")
                        f.write(f"**Link:** {url}\n\n")
                        f.write(f"{article_text}\n\n")
                        f.write("---\n\n")
                        f.flush() # Save progress immediately
                        
                    except Exception as e:
                        print(f"     [!] Error on link: {e}")
                        f.write(f"## {title}\n**Date:** {date}\n*[Error: Could not reach page]*\n\n---\n\n")
                        
            print(f"COMPLETED: {md_file.name} saved to {output_dir}")

    print("\nMISSION SUCCESS: All releases have been downloaded and cleaned.")

if __name__ == "__main__":
    asyncio.run(fetch_full_text())