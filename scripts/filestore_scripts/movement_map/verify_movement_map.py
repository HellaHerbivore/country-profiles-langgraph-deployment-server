"""Post-ingest attribution check for the Movement Map store.

Proves the property the pipeline was built for: answers about an organization
are grounded in that organization's own document, with the correct values. For
a random sample of orgs it asks a pointed question (budget tier) and asserts:
  1. the org's own document appears in the grounding citations, and
  2. the answer contains the org's budget tier from the manifest.
File Search retrieves the top-k most similar documents per query, so other
orgs' profiles legitimately appear alongside the target in grounding metadata;
that is normal retrieval, not misattribution — each retrieved profile is a
self-contained single-org document, so details cannot cross between orgs.
Also smoke-tests a custom_metadata filter (country).

Usage:
    python verify_movement_map.py \
        --manifest ../../../data/movement_map/movement_map_manifest.json \
        [--store fileSearchStores/...] [--sample 10] [--seed 42] [--country Spain]
"""

import argparse
import json
import random
import sys
from pathlib import Path

from colorama import Fore, Style
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import get_client, MOVEMENT_MAP_STORE  # noqa: E402

client = get_client()
MODEL = "gemini-3-flash-preview"  # same model the agent uses


def grounding_titles(response) -> list[str]:
    titles = []
    for candidate in response.candidates or []:
        meta = getattr(candidate, "grounding_metadata", None)
        for chunk in (getattr(meta, "grounding_chunks", None) or []):
            ctx = getattr(chunk, "retrieved_context", None)
            if ctx and ctx.title:
                titles.append(ctx.title)
    return titles


def ask(store_name: str, prompt: str, metadata_filter: str | None = None):
    file_search = types.FileSearch(file_search_store_names=[store_name])
    if metadata_filter:
        file_search.metadata_filter = metadata_filter
    return client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(file_search=file_search)],
            temperature=0.0,
        ),
    )


def check_org(store_name: str, entry: dict) -> bool:
    org = entry["custom_metadata"]["organization"]
    display_name = entry["display_name"]
    budget = entry["custom_metadata"].get("budget_tier", "")
    prompt = (f"According to the Movement Map, what is the estimated annual budget size "
              f"of the organization named \"{org}\"? Answer with just the budget tier value.")
    response = ask(store_name, prompt)
    titles = list(dict.fromkeys(grounding_titles(response)))  # dedupe, keep order
    answer = (response.text or "").strip()

    neighbors = [t for t in titles if t != display_name]
    problems = []
    if not titles:
        problems.append("no grounding citations returned")
    elif display_name not in titles:
        problems.append(f"org's OWN document was not among the citations; retrieved: {titles}")
    if budget and budget.lower() not in answer.lower():
        problems.append(f"expected budget {budget!r} not in answer {answer!r}")

    if problems:
        print(f"{Fore.RED}❌ {org}{Style.RESET_ALL}")
        for p in problems:
            print(f"     {p}")
        return False
    note = f" (+{len(neighbors)} similar org(s) also retrieved — normal)" if neighbors else ""
    print(f"{Fore.GREEN}✅ {org}{Style.RESET_ALL} → {answer!r}, grounded in its own document{note}")
    return True


def check_metadata_filter(store_name: str, entries: list[dict], country: str) -> bool:
    expected = {e["display_name"] for e in entries
                if e["custom_metadata"].get("country") == country}
    if not expected:
        print(f"{Fore.YELLOW}⚠️  No orgs with country={country!r} in manifest; skipping filter test{Style.RESET_ALL}")
        return True
    response = ask(store_name,
                   f"List three organizations headquartered in {country} and what animals they help.",
                   metadata_filter=f'country = "{country}"')
    titles = set(grounding_titles(response))
    outside = titles - expected
    if outside:
        print(f"{Fore.RED}❌ metadata_filter country={country!r} cited documents outside the filter: "
              f"{sorted(outside)}{Style.RESET_ALL}")
        return False
    print(f"{Fore.GREEN}✅ metadata_filter country={country!r}: {len(titles)} citation(s), "
          f"all within the filtered set{Style.RESET_ALL}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spot-check attribution integrity of the Movement Map store")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="movement_map_manifest.json produced by convert_movement_map.py")
    parser.add_argument("--store", default=MOVEMENT_MAP_STORE,
                        help="Store ID (default: MOVEMENT_MAP_STORE from config.py)")
    parser.add_argument("--sample", type=int, default=10, help="Number of orgs to spot-check (default: 10)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for a reproducible sample")
    parser.add_argument("--country", default="Spain", help="Country for the metadata_filter smoke test")
    args = parser.parse_args()

    if not args.store or not args.store.startswith("fileSearchStores/"):
        sys.exit("❌ No valid store ID. Set MOVEMENT_MAP_STORE in scripts/filestore_scripts/config.py "
                 "or pass --store.")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    # Only orgs with a concrete budget tier make a checkable question
    candidates = [e for e in manifest["documents"]
                  if e["custom_metadata"].get("budget_tier", "").lower().startswith("tier")]
    rng = random.Random(args.seed)
    sample = rng.sample(candidates, min(args.sample, len(candidates)))

    print(f"Store: {args.store}")
    print(f"Spot-checking {len(sample)} of {len(candidates)} orgs with a budget tier...\n")
    passed = sum(check_org(args.store, e) for e in sample)

    print()
    filter_ok = check_metadata_filter(args.store, manifest["documents"], args.country)

    print(f"\n{'='*60}")
    if passed == len(sample) and filter_ok:
        print(f"{Fore.GREEN}✅ All {passed}/{len(sample)} attribution checks passed; "
              f"metadata filter OK.{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}❌ {len(sample) - passed} attribution failure(s); "
              f"metadata filter {'OK' if filter_ok else 'FAILED'}.{Style.RESET_ALL}")
        sys.exit(1)
