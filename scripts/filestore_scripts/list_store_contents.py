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

# The movement-map store holds one document per organisation (~1,000 total —
# see scripts/filestore_scripts/movement_map/README.md), so it is reported as
# a single collapsed item (counts per collection) rather than every org name.
MOVEMENT_MAP_COLLECTION_PREFIXES = {
    "ACE Movement Map - ": "ACE Movement Map 2026",
    "Stray Dog Institute Movement Map - ": "Stray Dog Institute India Partner Directory",
}


def _summarise_movement_map(names: list[str]) -> dict:
    counts = {label: 0 for label in MOVEMENT_MAP_COLLECTION_PREFIXES.values()}
    other = 0
    for name in names:
        for prefix, label in MOVEMENT_MAP_COLLECTION_PREFIXES.items():
            if name.startswith(prefix):
                counts[label] += 1
                break
        else:
            other += 1
    if other:
        counts["Other"] = other
    return {"total_documents": len(names), "by_collection": counts}


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

        if key == "movement_map":
            summary = _summarise_movement_map(names)
            results[key] = summary
            print(f"\n=== {key}  ({store_id}) — {summary['total_documents']} documents (one org profile each) ===")
            for label, count in summary["by_collection"].items():
                print(f"  - {label}: {count} organisations")
            continue

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
