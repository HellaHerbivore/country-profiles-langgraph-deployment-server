from camoufox.async_api import AsyncCamoufox
import asyncio
import random
from pathlib import Path

async def fetch_pib_data():
    print("1. Starting Camoufox in VISIBLE mode...")
    async with AsyncCamoufox(headless=False) as browser:
        page = await browser.new_page()
        
        print("2. Loading the PIB 'All Releases' page...")
        await page.goto("https://pib.gov.in/AllRelease.aspx?MenuId=30&RegionId=3&LanguageId=1")
        await page.wait_for_timeout(4000)
        
        try:
            print("3. Forcing English Language...")
            await page.locator('select[name="ctl00$Bar1$ddlLang"]').select_option(label="English")
            await page.wait_for_load_state("networkidle")
            
            print("4. Selecting Ministry...")
            await page.locator('select[name="ctl00$ContentPlaceHolder1$ddlMinistry"]').select_option(label="Ministry of Fisheries, Animal Husbandry & Dairying")
            await page.wait_for_load_state("networkidle")
            
            print("5. Selecting 'All Days'...")
            await page.locator('select[name="ctl00$ContentPlaceHolder1$ddlday"]').select_option("0")
            await page.wait_for_load_state("networkidle")
            
            output_dir = Path("data_temp")
            output_dir.mkdir(exist_ok=True)
            
            years = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017"]
            months = [
                ("1", "Jan"), ("2", "Feb"), ("3", "Mar"), ("4", "Apr"), 
                ("5", "May"), ("6", "Jun"), ("7", "Jul"), ("8", "Aug"), 
                ("9", "Sep"), ("10", "Oct"), ("11", "Nov"), ("12", "Dec")
            ]
            
            print("\n6. Starting the Date Loop with Human Jitter...")
            
            for year in years:
                print(f"\n--- Scraping Year: {year} ---")
                await page.locator('select[name="ctl00$ContentPlaceHolder1$ddlYear"]').select_option(year)
                await page.wait_for_load_state("networkidle")
                
                for month_val, month_name in months:
                    print(f"  -> Fetching {month_name} {year}...")
                    
                    # 1. The Human Jitter: Wait a random amount of time between 2.5 and 5.5 seconds
                    jitter = random.uniform(2.5, 5.5)
                    await page.wait_for_timeout(jitter * 1000)
                    
                    try:
                        # 2. Explicit Wait: Ensure the drop-down is actually drawn on the screen before touching it
                        month_dropdown = page.locator('select[name="ctl00$ContentPlaceHolder1$ddlMonth"]')
                        await month_dropdown.wait_for(state="visible", timeout=15000)
                        
                        await month_dropdown.select_option(month_val)
                        await page.wait_for_load_state("networkidle")
                        await page.wait_for_timeout(1500)
                        
                        # Save the HTML
                        html_content = await page.content()
                        filename = f"pib_fisheries_{year}_{month_val.zfill(2)}.html"
                        out_file = output_dir / filename
                        out_file.write_text(html_content, encoding="utf-8")
                        
                    except Exception as inner_e:
                        # 3. Safety Net: Take a picture if it breaks, but don't crash the whole tool
                        print(f"  [!] Failed on {month_name} {year}. Taking screenshot...")
                        await page.screenshot(path=f"debug_{year}_{month_name}.png")
                        print(f"  [!] The wall hit us: {inner_e}")
                        break 
                        
            print("\nSUCCESS! All months and years have been scraped.")
            
        except Exception as e:
            print(f"\nFAILED: {e}")
            await page.screenshot(path="debug_screen_loop.png")

if __name__ == "__main__":
    asyncio.run(fetch_pib_data())