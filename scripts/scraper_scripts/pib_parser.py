import os
from bs4 import BeautifulSoup
from pathlib import Path

def parse_pib_html(html_filepath):
    """Reads a single HTML file and returns a list of press releases."""
    with open(html_filepath, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
    
    releases = []
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
                url = "https://pib.gov.in" + link_tag.get('href')
                date_str = date_tag.get_text(strip=True).replace("Posted on: ", "")
                
                releases.append({
                    "title": title,
                    "date": date_str,
                    "url": url
                })
    return releases

def process_all_files():
    input_dir = Path("data_temp")
    output_dir = Path("data_markdown")
    output_dir.mkdir(exist_ok=True)
    
    print("1. Scanning for downloaded HTML files...")
    html_files = list(input_dir.glob("pib_fisheries_*.html"))
    
    if not html_files:
        print("No HTML files found in 'data_temp'.")
        return
        
    print(f"Found {len(html_files)} files. Starting extraction...")
    
    # We will process them year by year
    years_data = {}
    
    for filepath in html_files:
        filename = filepath.stem
        # filename format is pib_fisheries_YYYY_MM
        parts = filename.split('_')
        if len(parts) == 4:
            year = parts[2]
            
            releases = parse_pib_html(filepath)
            
            if year not in years_data:
                years_data[year] = []
            
            years_data[year].extend(releases)
    
    print("\n2. Writing clean data to Markdown files...")
    
    for year, releases in sorted(years_data.items(), reverse=True):
        out_file = output_dir / f"fisheries_releases_{year}.md"
        
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(f"# Ministry of Fisheries, Animal Husbandry & Dairying - Press Releases ({year})\n\n")
            
            if not releases:
                f.write("*No press releases found for this year.*\n")
            else:
                for r in releases:
                    f.write(f"* **{r['date']}**: [{r['title']}]({r['url']})\n")
        
        print(f"  -> Saved {len(releases)} releases to {out_file.name}")
        
    print("\nSUCCESS! All data parsed and saved to the 'data_markdown' folder.")

if __name__ == "__main__":
    process_all_files()