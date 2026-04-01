import os
import time
from pathlib import Path
from typing import cast
from dotenv import load_dotenv
from google import genai

# ---------------------------------------------------------------------------
# 1. Setup and Keys (Finding .env in the root)
# ---------------------------------------------------------------------------
script_folder = Path(__file__).parent
env_path = script_folder / ".." / ".env"
load_dotenv(dotenv_path=env_path)

# Initialize the Google GenAI client
# It will automatically look for GOOGLE_API_KEY in your environment
client = genai.Client()

# ---------------------------------------------------------------------------
# 2. Create a NEW File Search Store
# ---------------------------------------------------------------------------
ground_truth_store = client.file_search_stores.create(
    config={'display_name': 'Ground-Truth-Advocacy-Feedback'}
)

# OPTION B: Use 'cast' to tell Pylance: "This name is definitely a string"
# This clears the "None is not assignable to str" error
NEW_STORE_ID = cast(str, ground_truth_store.name)

# ---------------------------------------------------------------------------
# 3. Upload and Index Files
# ---------------------------------------------------------------------------
FIELD_FILES = [
    r"C:\Users\shani\Documents\_ANIMAL-ADVOCACY\GoodGrowth\Country Profiles\Data Sources\Boots-on-the-ground sources\Stray-Dog-Institute_RAP\Regional-Advisory-Panels_January-2026_Full-Report.md"
]

for file_path in FIELD_FILES:
    file_name = os.path.basename(file_path)
    print(f"Uploading field source: {file_name}...")
    
    operation = client.file_search_stores.upload_to_file_search_store(
        file=file_path,
        file_search_store_name=NEW_STORE_ID,
        config={'display_name': file_name}
    )
    
    # Wait for the indexing operation to finish
    while not operation.done:
        print("...still indexing...")
        time.sleep(3)
        operation = client.operations.get(operation)
        
    print(f"✅ Success! {file_name} indexed in Ground Truth vault.")

print(f"\n========================================================")
print(f"🌟 SAVE THIS NEW STORE ID: {NEW_STORE_ID}")
print(f"========================================================\n")

def run_setup():
    # Move all your upload and indexing logic inside here
    # ... (your existing for loop) ...
    print(f"✅ Success! Store ID: {NEW_STORE_ID}")

if __name__ == "__main__":
    run_setup()