"""Zotero collection garbage collection helpers."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

TEST_PATTERNS = ["*-test", "*-scratch", "persona-*", "test-*", "*-tmp", "*-sandbox", "Beta"]
DEFAULT_AGE_DAYS = 30


@dataclass
class GCCandidate:
    key: str
    name: str
    num_items: int
    num_collections: int
    date_added: str
    reasons: list[str] = field(default_factory=list)


def scan_zotero_for_gc(
    zot,
    vault_keys: set[str],
    *,
    include_test_pattern: bool = True,
    age_days: int = DEFAULT_AGE_DAYS,
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
    """Delete each candidate via the Zotero web API."""
    results: dict[str, str] = {}
    for candidate in candidates:
        try:
            coll = zot.collection(candidate.key)
            zot.delete_collection(coll)
            results[candidate.key] = "ok"
        except Exception as exc:
            results[candidate.key] = str(exc)[:80]
    return results
