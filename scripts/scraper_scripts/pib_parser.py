import os
import re
from bs4 import BeautifulSoup
from config import PIB_BASE_URL, DATA_TEMP_DIR, DATA_MARKDOWN_DIR

def parse_pib_html(html_filepath):
    """Reads a single HTML file and returns a list of press releases."""
    with open(html_filepath, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    releases = []
    seen_prids = set()  # dedupe: same release can appear with decorated URLs
    # The PIB site keeps the releases inside a <ul> with class 'num'
    list_container = soup.find('ul', class_='num')
    
    if list_container:
        # Each release is an <li> tag
        list_items = list_container.find_all('li')
        for item in list_items:
            link_tag = item.find('a')
            date_tag = item.find('span', class_='publishdatesmall')
            
            if link_tag and date_tag:
                title = link_tag.get_text(strip=True)
                url = PIB_BASE_URL + link_tag.get('href')
                date_str = date_tag.get_text(strip=True).replace("Posted on: ", "")
                
                # A release's identity is its PRID; the same PRID can appear
                # with extra query params (&reg=48&lang=1). Keep one per PRID.
                prid_match = re.search(r"PRID=(\d+)", url)
                prid = prid_match.group(1) if prid_match else url
                if prid in seen_prids:
                    continue
                seen_prids.add(prid)
                
                releases.append({
                    "title": title,
                    "date": date_str,
                    "url": url
                })
    return releases

def process_all_files():
    input_dir = DATA_TEMP_DIR
    output_dir = DATA_MARKDOWN_DIR
    output_dir.mkdir(exist_ok=True)
    
    print("1. Scanning for downloaded HTML files...")
    html_files = list(input_dir.glob("pib_fisheries_*.html"))
    
    if not html_files:
        print("No HTML files found in 'data_temp'.")
        return
        
    print(f"Found {len(html_files)} files. Starting extraction...")

    # One output file per month. The HTML index is already per-month
    # (pib_fisheries_YYYY_MM.html), so each input maps to one monthly markdown
    # file. Per-month files are immutable once settled, which keeps uploads to
    # the File Search store append-only (see config.is_settled_month).
    months_data = {}          # "YYYY_MM" -> list of releases
    seen_prids_by_month = {}  # "YYYY_MM" -> set of PRIDs already kept

    for filepath in html_files:
        filename = filepath.stem
        # filename format is pib_fisheries_YYYY_MM
        parts = filename.split('_')
        if len(parts) == 4:
            year, month = parts[2], parts[3]
            key = f"{year}_{month}"

            releases = parse_pib_html(filepath)

            months_data.setdefault(key, [])
            seen_prids_by_month.setdefault(key, set())

            for release in releases:
                prid_match = re.search(r"PRID=(\d+)", release["url"])
                prid = prid_match.group(1) if prid_match else release["url"]
                if prid in seen_prids_by_month[key]:
                    continue
                seen_prids_by_month[key].add(prid)
                months_data[key].append(release)

    print("\n2. Writing clean data to Markdown files...")

    written = 0
    for key, releases in sorted(months_data.items(), reverse=True):
        # Skip empty months entirely — no point creating/uploading a file with
        # no releases (avoids polluting the store with placeholder documents).
        if not releases:
            continue

        year, month = key.split('_')
        out_file = output_dir / f"fisheries_releases_{key}.md"

        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(f"# Ministry of Fisheries, Animal Husbandry & Dairying - Press Releases ({year}-{month})\n\n")
            for r in releases:
                f.write(f"* **{r['date']}**: [{r['title']}]({r['url']})\n")

        written += 1
        print(f"  -> Saved {len(releases)} releases to {out_file.name}")

    print(f"\nSUCCESS! Wrote {written} monthly file(s) to the 'data_markdown' folder.")

if __name__ == "__main__":
    process_all_files()