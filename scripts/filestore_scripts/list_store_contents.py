import argparse
import json
from pathlib import Path
from config import (
    get_client,
    FOREIGN_ACADEMIC_STORE,
    ON_GROUND_ADVOCATE_STORE,
    LOCAL_ACADEMIC_STORE,
    GOI_PIB_STORE,
    REGULATORY_ENVIRONMENT_STORE,
    MOVEMENT_MAP_STORE,
)

STORES = {
    "foreign_academic": FOREIGN_ACADEMIC_STORE,
    "onground_advocate": ON_GROUND_ADVOCATE_STORE,
    "local_academic": LOCAL_ACADEMIC_STORE,
    "goi_pib": GOI_PIB_STORE,
    "regulatory_environment": REGULATORY_ENVIRONMENT_STORE,
    "movement_map": MOVEMENT_MAP_STORE,
}


def main():
    ap = argparse.ArgumentParser(description="List every document's display name in each Gemini File Search store")
    ap.add_argument("--out", help="Optional path to also save the results as JSON")
    args = ap.parse_args()

    client = get_client()
    results = {}

    for key, store_id in STORES.items():
        names = []
        for doc in client.file_search_stores.documents.list(parent=store_id):
            names.append(getattr(doc, "display_name", "") or doc.name)
        names.sort()
        results[key] = names

        print(f"\n=== {key}  ({store_id}) — {len(names)} documents ===")
        for n in names:
            print(f"  - {n}")

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(results, indent=2))
        print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
