"""Read-only local cache evidence, never a remote synchronization verdict."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

import yaml
from yaml.nodes import MappingNode, ScalarNode


@dataclass(frozen=True)
class SourceEvidence:
    state: str = "unknown"
    reason: str = "not_observed"
    source_key: str = ""
    payload_kind: str = ""
    payload_sha256: str = ""


def note_source_identities(frontmatter: str) -> dict[str, str]:
    """Read only unambiguous string scalars; never consume the next YAML line.

    Compose nodes rather than construct objects. Nulls, containers, custom tags,
    repeated identity fields, multiline values, and malformed YAML stay unknown.
    """
    identities = {"doi": "", "zotero-key": ""}
    try:
        document = yaml.compose(frontmatter, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return identities
    if not isinstance(document, MappingNode):
        return identities
    seen: set[str] = set()
    for key, value in document.value:
        if not isinstance(key, ScalarNode) or key.value not in identities:
            continue
        if key.value in seen:
            identities[key.value] = ""
            continue
        seen.add(key.value)
        if (isinstance(value, ScalarNode) and value.tag == "tag:yaml.org,2002:str"
                and value.start_mark.line == value.end_mark.line):
            text = value.value.strip()
            if "\n" not in text and "\r" not in text and text.lower() not in {"null", "none", "~"}:
                identities[key.value] = text
    return identities


def read_nlm_cache(path: Path) -> tuple[dict, str]:
    """Keep read/parse failures distinct from an absent identity in a valid cache."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Ambiguous duplicate cache key")
            result[key] = value
        return result

    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except FileNotFoundError:
        return {}, "cache_missing"
    except (OSError, UnicodeError):
        return {}, "cache_unreadable"
    except (ValueError, RecursionError):
        return {}, "cache_invalid"
    if not isinstance(payload, dict):
        return {}, "cache_invalid"
    return payload, ""


def cluster_cache_view(value: object) -> tuple[dict, str]:
    """Reject malformed metadata before legacy consumers can drop a whole cluster.

    Return an empty read view, not a repaired cache; the caller must retain the
    invalid reason. No source/cache bytes are changed.
    """
    if not isinstance(value, dict):
        return {}, "cache_invalid"

    def count_valid(count: object) -> bool:
        if type(count) is int:
            return count >= 0
        if not isinstance(count, str) or re.fullmatch(r"[0-9]+", count) is None:
            return False
        try:
            int(count)
        except (ValueError, OverflowError):
            return False
        return True

    if not count_valid(value.get("uploaded_doi_count", 0)):
        return {}, "cache_invalid"
    artifacts = value.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return {}, "cache_invalid"
    for kind in ("brief", "audio", "mind_map", "video"):
        meta = artifacts.get(kind, {})
        if not isinstance(meta, dict) or not count_valid(meta.get("char_count", 0)):
            return {}, "cache_invalid"
        if kind == "brief":
            titles = meta.get("titles", [])
            if not isinstance(titles, list) or any(not isinstance(title, str) for title in titles):
                return {}, "cache_invalid"
    return value, ""


def source_evidence(cluster_cache: object, doi: str, note_path: str, *, issue: str = "") -> SourceEvidence:
    """Only an exact primary-cache key can bind a saved payload fingerprint.

    Do not guess bundle-PDF or shard membership from a DOI, title or basename.
    No file hashing, URL reads, provider calls, writes, or timestamp inference.
    """
    if issue:
        return SourceEvidence(reason=issue)
    if not isinstance(cluster_cache, dict):
        return SourceEvidence(reason="cache_invalid")
    uploaded = cluster_cache.get("uploaded_sources", [])
    if not isinstance(uploaded, list) or any(not isinstance(key, str) for key in uploaded):
        return SourceEvidence(reason="cache_invalid")
    matches = set(uploaded).intersection(key for key in (doi, note_path) if key)
    if not matches:
        return SourceEvidence(reason="identity_not_linked")
    if len(matches) != 1:
        return SourceEvidence(reason="identity_ambiguous")
    key = next(iter(matches))
    versions = cluster_cache.get("source_versions", {})
    version = versions.get(key) if isinstance(versions, dict) else None
    if (isinstance(version, dict) and version.get("kind") in ("pdf", "text")
            and isinstance(version.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", version["sha256"])):
        return SourceEvidence("recorded", "historical_version", key, version["kind"], version["sha256"])
    return SourceEvidence("recorded", "version_unknown", key)
