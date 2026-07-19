"""Post-ingest attribution check for the Movement Map store, both collections.

Proves the property the pipelines were built for: answers about an organization
are grounded in that organization's own document, with the correct values. For
a random sample of orgs it asks a pointed question and asserts:
  1. the org's own document appears in the grounding citations, and
  2. the answer contains the expected value from the manifest (budget tier for
     ACE docs, role in movement for SDI docs).
File Search retrieves the top-k most similar documents per query, so other
orgs' profiles legitimately appear alongside the target in grounding metadata;
that is normal retrieval, not misattribution — each retrieved profile is a
self-contained single-org document, so details cannot cross between orgs.

Also smoke-tests custom_metadata filters:
  - a string_value filter (--country, ACE manifests only), and
  - the intervention_tags string_list_value filter, including the OR form —
    the exact expressions internal_researcher.py builds via build_tag_filter().
    If this test errors, fix the grammar in ONE place:
    src/country_profiles/intervention_tags.py::build_tag_filter.

Usage:
    python verify_profiles.py \
        --manifest <dir>/sdi_movement_map_manifest.json \
        [--store fileSearchStores/...] [--sample 10] [--seed 42] [--country Spain]
"""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

from colorama import Fore, Style
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src" / "country_profiles"))
from config import get_client, MOVEMENT_MAP_STORE  # noqa: E402
from intervention_tags import INTERVENTION_TAGS, build_tag_filter  # noqa: E402

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


def _normalized(text: str) -> str:
    """Case- and dash-insensitive form for value comparison — the model may
    render "Tier 2: $100k-1M" with an en-dash."""
    return text.replace("–", "-").replace("—", "-").lower()


def probe_for(entry: dict) -> tuple[str, str]:
    """(pointed question, expected answer fragment or '') for one org, using
    whichever checkable field this collection's metadata carries."""
    meta = entry["custom_metadata"]
    org = meta["organization"]
    budget = meta.get("budget_tier", "")
    if budget.lower().startswith("tier"):
        return (f"According to the movement map, what is the estimated annual budget size "
                f"of the organization named \"{org}\"? Answer with just the budget tier value.", budget)
    role = meta.get("role", "")
    if role:
        return (f"According to the movement map, what is the role in the movement "
                f"of the organization named \"{org}\"? Answer briefly.", role)
    return (f"What does the movement map record about the organization named \"{org}\"? "
            f"Answer in one sentence.", "")


def check_org(store_name: str, entry: dict) -> bool:
    org = entry["custom_metadata"]["organization"]
    display_name = entry["display_name"]
    prompt, expected = probe_for(entry)
    response = ask(store_name, prompt)
    titles = list(dict.fromkeys(grounding_titles(response)))  # dedupe, keep order
    answer = (response.text or "").strip()

    neighbors = [t for t in titles if t != display_name]
    problems = []
    if not titles:
        problems.append("no grounding citations returned")
    elif display_name not in titles:
        problems.append(f"org's OWN document was not among the citations; retrieved: {titles}")
    if expected and _normalized(expected) not in _normalized(answer):
        problems.append(f"expected {expected!r} not in answer {answer!r}")

    if problems:
        print(f"{Fore.RED}❌ {org}{Style.RESET_ALL}")
        for p in problems:
            print(f"     {p}")
        return False
    note = f" (+{len(neighbors)} similar org(s) also retrieved — normal)" if neighbors else ""
    print(f"{Fore.GREEN}✅ {org}{Style.RESET_ALL} → {answer!r}, grounded in its own document{note}")
    return True


def check_string_filter(store_name: str, entries: list[dict], country: str) -> bool:
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


def check_tag_filter(store_name: str, entries: list[dict]) -> bool:
    """Run build_tag_filter() expressions — single tag, then two-tag OR — and
    assert every citation carries the filtered tag(s) per the manifest. Note the
    store also holds the OTHER collection's docs matching the tag; those are
    legitimate results, so only THIS manifest's docs are checked for wrongness."""
    tag_counts = Counter(
        code
        for e in entries
        for code in e["custom_metadata"].get("intervention_tags", [])
    )
    if not tag_counts:
        print(f"{Fore.YELLOW}⚠️  No intervention_tags in manifest; skipping tag filter test{Style.RESET_ALL}")
        return True

    ok = True
    top_codes = [code for code, _ in tag_counts.most_common(2)]
    for codes in ([top_codes[0]], top_codes if len(top_codes) > 1 else []):
        if not codes:
            continue
        filter_str = build_tag_filter(codes)
        allowed = {e["display_name"] for e in entries
                   if set(codes) & set(e["custom_metadata"].get("intervention_tags", []))}
        disallowed = {e["display_name"] for e in entries} - allowed
        labels = "; ".join(INTERVENTION_TAGS[c] for c in codes)
        try:
            response = ask(store_name,
                           f"List organizations that work on: {labels}. Name each organization.",
                           metadata_filter=filter_str)
        except Exception as e:
            print(f"{Fore.RED}❌ tag filter {filter_str!r} was rejected by the API: {e}\n"
                  f"   Adjust build_tag_filter() in src/country_profiles/intervention_tags.py "
                  f"(runtime and verifier share it).{Style.RESET_ALL}")
            ok = False
            continue
        titles = set(grounding_titles(response))
        wrong = titles & disallowed
        if wrong:
            print(f"{Fore.RED}❌ tag filter {filter_str!r} cited docs that lack the tag(s): "
                  f"{sorted(wrong)}{Style.RESET_ALL}")
            ok = False
        elif not titles:
            print(f"{Fore.YELLOW}⚠️  tag filter {filter_str!r} returned no citations — filter may be "
                  f"over-restrictive or the grammar silently matched nothing; investigate before "
                  f"relying on it{Style.RESET_ALL}")
            ok = False
        else:
            print(f"{Fore.GREEN}✅ tag filter {filter_str!r}: {len(titles)} citation(s), none "
                  f"contradicting the manifest{Style.RESET_ALL}")
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spot-check attribution integrity of the Movement Map store")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Manifest produced by either collection's convert.py")
    parser.add_argument("--store", default=MOVEMENT_MAP_STORE,
                        help="Store ID (default: MOVEMENT_MAP_STORE from config.py)")
    parser.add_argument("--sample", type=int, default=10, help="Number of orgs to spot-check (default: 10)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for a reproducible sample")
    parser.add_argument("--country", default=None,
                        help="Country for the string metadata_filter smoke test (ACE manifests; e.g. Spain)")
    args = parser.parse_args()

    if not args.store or not args.store.startswith("fileSearchStores/"):
        sys.exit("❌ No valid store ID. Set MOVEMENT_MAP_STORE in scripts/filestore_scripts/config.py "
                 "or pass --store.")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents = manifest["documents"]
    rng = random.Random(args.seed)
    sample = rng.sample(documents, min(args.sample, len(documents)))

    print(f"Store: {args.store}")
    print(f"Spot-checking {len(sample)} of {len(documents)} orgs...\n")
    passed = sum(check_org(args.store, e) for e in sample)

    print()
    filters_ok = check_tag_filter(args.store, documents)
    if args.country:
        filters_ok = check_string_filter(args.store, documents, args.country) and filters_ok

    print(f"\n{'='*60}")
    if passed == len(sample) and filters_ok:
        print(f"{Fore.GREEN}✅ All {passed}/{len(sample)} attribution checks passed; "
              f"metadata filters OK.{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}❌ {len(sample) - passed} attribution failure(s); "
              f"metadata filters {'OK' if filters_ok else 'FAILED'}.{Style.RESET_ALL}")
        sys.exit(1)
