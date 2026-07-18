"""Shared helpers for the Movement Map converter pipelines.

Two pipelines feed the same Gemini File Search store — ACE_Movement-Map/ and
Stray-Dog-Institute_Movement-Map/ — and both emit the same artifact shape: one
self-contained Markdown profile per organization plus a JSON manifest consumed
by upload_profiles.py.

Stdlib-only on purpose — no API key or google-genai install needed, so the
confidential CSVs can be converted anywhere.
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

# Sheet placeholders that mean "no value"
ABSENT_VALUES = {"", "[no website found]", "n/a", "na", "-", "—"}

# Gemini custom metadata string values are capped at 256 BYTES — the API error
# says "characters" but counts UTF-8 bytes, so em-dashes cost 3. Stay safely under.
METADATA_VALUE_MAX_BYTES = 250


def truncate_metadata_value(value: str, max_bytes: int = METADATA_VALUE_MAX_BYTES) -> str:
    """Truncate to the metadata byte budget without splitting a UTF-8 character."""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()

# upload_profiles.py chunks at 500 tokens. A profile at or above this estimate
# (~4 chars/token) could split into two chunks and lose the one-org-one-chunk
# guarantee, so converters warn about it.
PROFILE_TOKEN_WARN_THRESHOLD = 450


def clean(value: str | None) -> str:
    """Strip and normalize whitespace; return '' for placeholder non-values."""
    if value is None:
        return ""
    text = re.sub(r"[ \t]+", " ", value.replace("\r", "")).strip()
    if text.lower() in ABSENT_VALUES:
        return ""
    return text


def split_list(value: str | None, sep: str = ",") -> list[str]:
    """Cleaned items of a separated menu field, empties dropped."""
    text = clean(value)
    if not text:
        return []
    return [p.strip() for p in text.split(sep) if p.strip()]


def clean_list(value: str | None, sep: str = ",") -> str:
    """Normalize a separated menu field (collapses doubled spaces after separators)."""
    return f"{sep} ".join(split_list(value, sep))


def slugify(name: str, max_len: int = 80) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug[:max_len].strip("-") or "org"


def dedupe_slug(slug: str, seen_slugs: dict[str, int]) -> str:
    """Suffix repeated slugs (-2, -3, ...) so filenames stay unique."""
    if slug in seen_slugs:
        seen_slugs[slug] += 1
        return f"{slug}-{seen_slugs[slug]}"
    seen_slugs[slug] = 1
    return slug


def estimated_tokens(text: str) -> int:
    return len(text) // 4


def warn_if_oversized(org: str, markdown: str) -> bool:
    tokens = estimated_tokens(markdown)
    if tokens >= PROFILE_TOKEN_WARN_THRESHOLD:
        print(f"⚠️  {org}: profile ≈{tokens} tokens — near the 500-token chunk size, may split into two chunks")
        return True
    return False


def write_manifest(out_dir: Path, filename: str, source_csv: Path, documents: list[dict]) -> Path:
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_csv": source_csv.name,
        "expected_count": len(documents),
        "documents": documents,
    }
    path = out_dir / filename
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
