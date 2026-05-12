from camoufox.async_api import AsyncCamoufox
import asyncio
import re
import random
from pathlib import Path

async def fetch_full_text():
    # Setup directories
    md_dir = Path("data_markdown")
    output_dir = Path("data_full_text")
    output_dir.mkdir(exist_ok=True)
    
    # Grab all year-based index files
    md_files = list(md_dir.glob("fisheries_releases_*.md"))
    if not md_files:
        print("No index files found in 'data_markdown'. Please run the parser first.")
        return

    print(f"Found {len(md_files)} year files. Starting the deep fetch...")
    
    # Launch browser - Visible mode helps monitor progress
    async with AsyncCamoufox(headless=False) as browser:
        page = await browser.new_page()
        
        # 1. Warm up the browser to get the Akamai clearance badge
        print("Warming up at the front door...")
        await page.goto("https://pib.gov.in/AllRelease.aspx")
        await page.wait_for_timeout(6000)
        
        for md_file in md_files:
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
                        await page.goto(url, referer="https://pib.gov.in/AllRelease.aspx")
                        await page.wait_for_timeout(3000) # Wait for iframe to load content

                        article_text = ""
                        
                        # 2. Dive into the scrolling windows (iframes)
                        for frame in page.frames:
                            try:
                                text = await frame.locator("body").inner_text()
                                # Only grab the text if it looks like the actual release
                                if "Ministry of Fisheries" in text or "Posted On:" in text:
                                    article_text = text.strip()
                                    break 
                            except:
                                continue

                        # 3. Fallback if no iframe content was found
                        if not article_text:
                            article_text = await page.locator("body").inner_text()

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