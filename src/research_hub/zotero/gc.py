"""Zotero collection garbage collection helpers."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

# Single source of truth — doctor.check_cluster_test_pattern imports this list.
# Keep test/scratch patterns conservative: exact match for ambiguous names like
# 'Beta', wildcards only for clearly-test naming conventions.
TEST_PATTERNS = [
    "*-test",
    "*-scratch",
    "*-sandbox",
    "*-tmp",
    "*-smoke",
    "persona-*",
    "test-*",
    "fresh-user-*",
    "Beta",
]
DEFAULT_AGE_DAYS = 30


@dataclass
class GCCandidate:
    key: str
    name: str
    num_items: int
    num_collections: int
    date_added: str
    reasons: list[str] = field(default_factory=list)


KEPT_FILE_NAME = "zotero_kept_collections.json"


def kept_file_path(research_hub_dir: Path) -> Path:
    """Canonical path to the kept-collections registry inside the vault."""
    return research_hub_dir / KEPT_FILE_NAME


def load_kept_keys(research_hub_dir: Path) -> set[str]:
    """Load the user-curated set of Zotero collection keys to skip in gc.

    The file is created by `research-hub zotero mark-kept` and read by
    `research-hub zotero gc --respect-kept`. Missing or malformed file
    returns an empty set rather than raising.
    """
    path = kept_file_path(research_hub_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except json.JSONDecodeError:
        return set()
    kept = data.get("kept") if isinstance(data, dict) else None
    if not isinstance(kept, list):
        return set()
    return {str(key).strip() for key in kept if str(key).strip()}


def save_kept_keys(
    research_hub_dir: Path,
    keys: Iterable[str],
    *,
    note: str | None = None,
) -> Path:
    """Persist a set of kept Zotero collection keys atomically.

    Writes `{"kept": [...], "marked_at": ISO8601, "note": ...}` into
    `<research_hub_dir>/zotero_kept_collections.json`. Sorted for stable
    diffs. Returns the written path.
    """
    path = kept_file_path(research_hub_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kept": sorted({str(key).strip() for key in keys if str(key).strip()}),
        "marked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if note:
        payload["note"] = note
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def scan_zotero_for_gc(
    zot,
    vault_keys: set[str],
    *,
    include_test_pattern: bool = True,
    age_days: int = DEFAULT_AGE_DAYS,
    kept_keys: set[str] | None = None,
) -> list[GCCandidate]:
    """Walk the Zotero web library and return collection delete candidates."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=age_days)
    out: list[GCCandidate] = []
    start = 0
    while True:
        chunk = zot.collections(limit=200, start=start)
        if not chunk:
            break
        for collection in chunk:
            data = collection.get("data", {})
            meta = collection.get("meta", {})
            num_items = int(meta.get("numItems", 0) or 0)
            num_collections = int(meta.get("numCollections", 0) or 0)
            key = collection.get("key") or data.get("key", "")
            name = data.get("name", "")
            date_added = data.get("dateAdded", "")
            reasons: list[str] = []

            if num_items == 0 and num_collections == 0:
                try:
                    if datetime.fromisoformat(date_added.replace("Z", "+00:00")) < cutoff:
                        reasons.append(f"empty>{age_days}d")
                except Exception:
                    pass

            if include_test_pattern:
                for pattern in TEST_PATTERNS:
                    if fnmatch.fnmatch(name, pattern):
                        reasons.append(f"test-pattern({pattern})")
                        break

            if key and key not in vault_keys:
                if kept_keys and key in kept_keys:
                    # User explicitly marked this collection as kept; skip the
                    # orphan flag so it never appears as a gc candidate.
                    pass
                else:
                    reasons.append("orphan-from-vault")

            if reasons:
                out.append(
                    GCCandidate(
                        key=key,
                        name=name,
                        num_items=num_items,
                        num_collections=num_collections,
                        date_added=date_added,
                        reasons=reasons,
                    )
                )
        if len(chunk) < 200:
            break
        start += 200
    return out


def delete_candidates(zot, candidates: Iterable[GCCandidate]) -> dict[str, str]:
    """Delete each candidate via the Zotero web API.

    Hard safety: refuse to delete a collection that holds items or
    sub-collections, even if the candidate matched a test-pattern.
    Pattern-only matches are advisory; emptiness is required for delete.
    """
    results: dict[str, str] = {}
    for candidate in candidates:
        if candidate.num_items > 0 or candidate.num_collections > 0:
            results[candidate.key] = (
                f"skip:non-empty({candidate.num_items} items, "
                f"{candidate.num_collections} sub-collections)"
            )
            continue
        try:
            coll = zot.collection(candidate.key)
            zot.delete_collection(coll)
            results[candidate.key] = "ok"
        except Exception as exc:
            results[candidate.key] = str(exc)[:80]
    return results
