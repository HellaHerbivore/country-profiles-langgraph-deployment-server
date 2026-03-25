
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Load API Key from .env file
# 1. Find the folder where THIS script lives
script_folder = Path(__file__).parent

# 2. Find the .env file one level up
env_path = script_folder / ".." / ".env"

# 3. Load it
load_dotenv(dotenv_path=env_path)

# 2. Initialize the client
# It will automatically find GOOGLE_API_KEY from your .env
client = genai.Client()

# 3. Create the storage spot
try:
    my_store = client.file_search_stores.create(
        config={'display_name': 'Research Assistant Vault'}
    )
    print(f"Success! Your storage spot is ready.")
    print(f"Store Name: {my_store.name}")
except Exception as e:
    print(f"Setup failed. Check if your API key is correct in .env: {e}")


# 3. Save the store name
# You will need this name (e.g., 'fileSearchStores/123') for your assistant.
print(f"Success! Your storage spot is ready.")
print(f"Store Name: {my_store.name}")