import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# .env is two levels up from this script
script_folder = Path(__file__).parent
env_path = script_folder / ".." / ".." / ".env"
load_dotenv(dotenv_path=env_path)

# Store constants (keep in sync with internal_researcher.py)
FOREIGN_ACADEMIC_STORE = "fileSearchStores/foreign-academic-sources-bqaqi98at2b3"
ON_GROUND_ADVOCATE_STORE = "fileSearchStores/onground-advocate-sources-y9falvyy92h3"
LOCAL_ACADEMIC_STORE = "fileSearchStores/local-academic-sources-cxae72dsk44n"
GOI_PIB_STORE = "fileSearchStores/governmentofindiapressinfor-7wwkcyy8ijd9"
REGULATORY_ENVIRONMENT_STORE = "fileSearchStores/regulatory-environment-o2q9s4tpmr2g"
# ACE Movement Map 2026 (per-organization profiles)
MOVEMENT_MAP_STORE = "fileSearchStores/movement-map-jzf154g2op6j"

def get_client():
    """Return a configured genai Client."""
    return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
