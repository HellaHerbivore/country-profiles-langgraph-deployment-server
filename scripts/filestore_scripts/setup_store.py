import argparse
from config import get_client

def run_setup(display_name: str):
    """Create a new Gemini File Search Store."""
    client = get_client()
    try:
        my_store = client.file_search_stores.create(
            config={'display_name': display_name}
        )
        print(f"✅ Success! Your storage spot is ready.")
        print(f"Store Name: {my_store.name}")
        print(f"\n--- SAVE THIS STORE NAME IN YOUR config.py ---")
    except Exception as e:
        print(f"❌ Setup failed. Check your API key: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new Gemini File Search Store")
    parser.add_argument("--name", required=True, help="Display name for the store")
    args = parser.parse_args()
    run_setup(args.name)
