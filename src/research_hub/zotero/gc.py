"""Zotero collection garbage collection helpers."""

from __future__ import annotations

import fnmatch
import json
import re
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

# 4–8 leading date digits (YYYY..YYYYMMDD) + optional T/_-separated time
# (HHMMSS, ≤6 digits) + a required separator. Deliberately NOT `\d*`
# (unbounded) — a tight bound keeps non-date numeric prefixes (e.g. a Unix
# timestamp) un-stripped, so such names stay LESS likely to be name-matched
# and thus stay flagged (the safe over-flag→under-flag direction).
_DATE_PREFIX_RE = re.compile(r"^\d{4,8}(?:[T_]\d{0,6})?[-_ ]+")
_NAME_MATCH_MIN_LEN = 12


def _normalize_collection_name(name: str) -> str:
    """Strip a leading (possibly Zotero-truncated) date prefix then slugify.

    e.g. '20260518-machine-learning-flood-forecas'
         -> 'machine-learning-flood-forecas'
    Reuses `research_hub.clusters.slugify` (imported lazily to avoid any
    import cycle between zotero.gc and clusters).
    """
    from research_hub.clusters import slugify  # lazy: avoid import cycle

    stripped = _DATE_PREFIX_RE.sub("", name or "")
    return slugify(stripped)


def _name_recognised(name: str, vault_name_slugs: set[str] | None) -> bool:
    """True if the normalized collection name prefix-matches a known
    cluster name/slug in BOTH directions (handles Zotero's name
    truncation either way). Min length guard avoids coincidental short
    matches.

    Accepted conservative edge case: the bidirectional prefix match can
    suppress a *genuine* orphan whose normalized name shares a long
    (≥12-char) prefix with a real cluster slug. This is intentional —
    over-flagging real data was the bug; an occasional harmless
    under-flag (orphan left in Zotero, never deleted) is the safe
    direction. ``delete_candidates``' non-empty hard-skip (PR-A) is the
    independent second safety net.
    """
    if not vault_name_slugs:
        return False
    norm = _normalize_collection_name(name)
    if len(norm) < _NAME_MATCH_MIN_LEN:
        return False
    for v in vault_name_slugs:
        if (
            len(v) >= _NAME_MATCH_MIN_LEN
            and (norm.startswith(v) or v.startswith(norm))
        ):
            return True
    return False


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
    vault_name_slugs: set[str] | None = None,
) -> list[GCCandidate]:
    """Walk the Zotero web library and return collection delete candidates.

    ``vault_name_slugs`` suppresses orphan flags for name-recognised collections.
    """
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
                elif _name_recognised(name, vault_name_slugs):
                    # Name-recognised: a real cluster collection whose key drifted
                    # (e.g. Zotero-truncated date-prefixed name). Suppress the
                    # orphan flag exactly like an explicit kept_keys entry. The
                    # empty>Nd / test-pattern reasons above are unaffected, so an
                    # empty recognised collection can still be flagged junk.
                    pass
                elif num_items == 0 and num_collections == 0:
                    # Empty orphan — safe junk, eligible for --yes auto-GC
                    # (only together with empty>Nd + test-pattern).
                    reasons.append("orphan-from-vault")
                else:
                    # PR-A: a non-empty orphan holds real items/subcollections
                    # (e.g. a stale date-prefixed duplicate from an earlier
                    # pipeline run). It must NEVER be auto-deleted by --yes and
                    # must require a strong, item-count-aware confirm. Distinct
                    # reason keeps it out of the --yes (orphan-from-vault) set.
                    reasons.append(f"orphan-with-items({num_items})")

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


def lookup_collection_names_and_counts(zot, keys: Iterable[str]) -> dict[str, dict]:
    """v0.88 #10: enrich a set of Zotero collection keys with their human
    name + item count. Walks Zotero web library paginated at 200/page
    (same as scan_zotero_for_gc) and matches against the input key set.

    Returns ``{key: {"name": str, "num_items": int, "num_collections": int}}``
    for every key in `keys` that exists in Zotero; missing keys are
    omitted from the result so callers can detect deletions.
    """
    wanted = {str(k).strip() for k in keys if str(k).strip()}
    if not wanted:
        return {}
    out: dict[str, dict] = {}
    start = 0
    while True:
        chunk = zot.collections(limit=200, start=start)
        if not chunk:
            break
        for collection in chunk:
            data = collection.get("data", {})
            meta = collection.get("meta", {})
            key = collection.get("key") or data.get("key", "")
            if key in wanted:
                out[key] = {
                    "name": data.get("name", ""),
                    "num_items": int(meta.get("numItems", 0) or 0),
                    "num_collections": int(meta.get("numCollections", 0) or 0),
                }
                if len(out) == len(wanted):
                    return out
        if len(chunk) < 200:
            break
        start += 200
    return out


def is_orphan_candidate(candidate: GCCandidate) -> bool:
    """True if the candidate is an orphan (not bound to any cluster),
    whether empty (`orphan-from-vault`) or non-empty
    (`orphan-with-items(N)`). PR-A split the reason in two; any site that
    used to key on ``"orphan-from-vault"`` to mean "is an orphan" (e.g.
    ``mark-kept --all-orphans``) must use this so non-empty orphans —
    exactly the real-data collections users most want to protect — are
    not silently dropped.
    """
    return "orphan-from-vault" in candidate.reasons or any(
        reason.startswith("orphan-with-items(") for reason in candidate.reasons
    )


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
