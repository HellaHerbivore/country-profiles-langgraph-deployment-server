import os
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Load your key
# 1. Find the folder where THIS script lives
script_folder = Path(__file__).parent

# 2. Find the .env file one level up
env_path = script_folder / ".." / ".env"

# 3. Load it
load_dotenv(dotenv_path=env_path)
client = genai.Client()

# 2. Your specific store name
STORE_NAME = "fileSearchStores/research-assistant-vault-7ya8m561y6pn"

# 3. List of your files
FILES_TO_UPLOAD = [
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\Bryant AI Research Reports with GG Human Comments\Reviewing_India\Reviewing_India_v2.pdf",
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\Faunalytics\External_Faunalytics\karamchedu-2025_corporate-control-broiler-production-global-south.pdf",
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\Faunalytics\External_Faunalytics\Sentient-2025_Uncovering-Cruelty_-The-Investigative-Landscape-in-India.pdf",
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\Faunalytics\External_Faunalytics\arora-2020_india-readiness-alternative-meat.pdf",
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\Faunalytics\External_Faunalytics\khire-ryba_sustainable-poultry-india.pdf",
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\Faunalytics\External_Faunalytics\krishna-2022_history-animal-rights-india.pdf",
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\Faunalytics\External_Faunalytics\Mason-2022_Mapping-industrial-pig-and-poultry-facilities.pdf",
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\Faunalytics\External_Faunalytics\ryba-2024-evaluating-the-economic-impacts-of-a-cage-free-animal-welfare-policy-in-southeast-asian-and-indian-egg.pdf",
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Reports\GoodGrowth Reports\Full Report, Food Systems Advocacy In The Global South - A Framework And Pilot In India.pdf"

]

for file_path in FILES_TO_UPLOAD:
    print(f"Uploading: {os.path.basename(file_path)}...")
    try:
        # We use the specific 'upload_to_file_search_store' method here
        operation = client.file_search_stores.upload_to_file_search_store(
            file=file_path,
            file_search_store_name=STORE_NAME,
            config={'display_name': os.path.basename(file_path)}
        )
        
        # This is an "Operation," meaning Google is working on it in the background.
        # We wait a few seconds for it to finish.
        while not operation.done:
            print("  ...still indexing...")
            time.sleep(3)
            operation = client.operations.get(operation)
            
        print(f"✅ Success! {os.path.basename(file_path)} is now indexed.")
        
    except Exception as e:
        print(f"❌ Failed to upload {file_path}: {e}")

print("\nAll done. Your research vault is now fully loaded and persistent.")