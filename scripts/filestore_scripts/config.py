import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# .env is two levels up from this script
script_folder = Path(__file__).parent
env_path = script_folder / ".." / ".." / ".env"
load_dotenv(dotenv_path=env_path)

# Store constants (same as internal_researcher.py:35-36)
FOREIGN_ACADEMIC_STORE = "fileSearchStores/research-assistant-vault-7ya8m561y6pn"
GROUND_TRUTH_STORE = "fileSearchStores/groundtruthadvocacyfeedback-2ojwsxpiytnc"
LOCAL_ACADEMIC_STORE = "fileSearchStores/local-academic-sources-75awfk5pza8p"

def get_client():
    """Return a configured genai Client."""
    return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
