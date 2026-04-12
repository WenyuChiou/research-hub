"""Deduplication index for Research Hub.

Checks DOI and normalized-title matches across BOTH Zotero and the Obsidian vault.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


def normalize_doi(doi: str | None) -> str:
    """Lowercase, strip whitespace, remove common DOI prefixes."""
    if not doi:
        return ""
    normalized = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized.strip()


def normalize_title(title: str | None) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    if not title:
        return ""
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return re.sub(r"\s+", " ", normalized)


@dataclass
class DedupHit:
    """A single deduplication hit from Zotero or Obsidian."""

    source: str
    doi: str = ""
    title: str = ""
    zotero_key: str | None = None
    obsidian_path: str | None = None


@dataclass
class DedupIndex:
    """Index of already-ingested papers across Zotero and Obsidian."""

    doi_to_hits: dict[str, list[DedupHit]] = field(default_factory=dict)
    title_to_hits: dict[str, list[DedupHit]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "DedupIndex":
        """Load a persisted index from disk, or return an empty one."""
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        index = cls()
        for doi, hits in data.get("doi_to_hits", {}).items():
            index.doi_to_hits[doi] = [DedupHit(**hit) for hit in hits]
        for title, hits in data.get("title_to_hits", {}).items():
            index.title_to_hits[title] = [DedupHit(**hit) for hit in hits]
        return index

    def save(self, path: Path) -> None:
        """Persist the index to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "doi_to_hits": {
                doi: [hit.__dict__ for hit in hits] for doi, hits in self.doi_to_hits.items()
            },
            "title_to_hits": {
                title: [hit.__dict__ for hit in hits]
                for title, hits in self.title_to_hits.items()
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, hit: DedupHit) -> None:
        """Add a hit to DOI and title lookups if not already present."""
        normalized_doi = normalize_doi(hit.doi)
        normalized_title = normalize_title(hit.title)
        if normalized_doi:
            self._append_unique(self.doi_to_hits.setdefault(normalized_doi, []), hit)
        if normalized_title and len(normalized_title) > 15:
            self._append_unique(self.title_to_hits.setdefault(normalized_title, []), hit)

    def lookup(self, doi: str = "", title: str = "") -> list[DedupHit]:
        """Return matching hits by DOI first, then title."""
        matches: list[DedupHit] = []
        normalized_doi = normalize_doi(doi)
        if normalized_doi and normalized_doi in self.doi_to_hits:
            matches.extend(self.doi_to_hits[normalized_doi])
        if not matches:
            normalized_title = normalize_title(title)
            if normalized_title and normalized_title in self.title_to_hits:
                matches.extend(self.title_to_hits[normalized_title])
        return matches

    def check(self, paper: dict) -> tuple[bool, list[DedupHit]]:
        """Check whether a paper dict has already been ingested."""
        hits = self.lookup(doi=paper.get("doi", ""), title=paper.get("title", ""))
        return bool(hits), hits

    @classmethod
    def empty(cls) -> "DedupIndex":
        """Create an empty index."""
        return cls()

    def invalidate_doi(self, doi: str) -> int:
        """Remove all hits for a normalized DOI. Returns count removed."""
        normalized = normalize_doi(doi)
        if normalized not in self.doi_to_hits:
            return 0
        removed = len(self.doi_to_hits[normalized])
        del self.doi_to_hits[normalized]
        return removed

    def invalidate_obsidian_path(self, path: str) -> int:
        """Remove dedup entries pointing at a specific obsidian_path."""
        removed = 0
        for key in list(self.title_to_hits.keys()):
            new_hits = [hit for hit in self.title_to_hits[key] if hit.obsidian_path != path]
            if len(new_hits) != len(self.title_to_hits[key]):
                removed += len(self.title_to_hits[key]) - len(new_hits)
                if new_hits:
                    self.title_to_hits[key] = new_hits
                else:
                    del self.title_to_hits[key]
        for key in list(self.doi_to_hits.keys()):
            new_hits = [hit for hit in self.doi_to_hits[key] if hit.obsidian_path != path]
            if len(new_hits) != len(self.doi_to_hits[key]):
                removed += len(self.doi_to_hits[key]) - len(new_hits)
                if new_hits:
                    self.doi_to_hits[key] = new_hits
                else:
                    del self.doi_to_hits[key]
        return removed

    def rebuild_from_obsidian(self, raw_root: Path) -> "DedupIndex":
        """Rescan vault notes and rebuild only the Obsidian side of the index."""
        for key in list(self.title_to_hits.keys()):
            self.title_to_hits[key] = [
                hit for hit in self.title_to_hits[key] if hit.source != "obsidian"
            ]
            if not self.title_to_hits[key]:
                del self.title_to_hits[key]
        for key in list(self.doi_to_hits.keys()):
            self.doi_to_hits[key] = [hit for hit in self.doi_to_hits[key] if hit.source != "obsidian"]
            if not self.doi_to_hits[key]:
                del self.doi_to_hits[key]
        for hit in build_from_obsidian(raw_root):
            self.add(hit)
        return self

    @staticmethod
    def _append_unique(hits: list[DedupHit], new_hit: DedupHit) -> None:
        marker = (
            new_hit.source,
            normalize_doi(new_hit.doi),
            normalize_title(new_hit.title),
            new_hit.zotero_key,
            new_hit.obsidian_path,
        )
        for existing in hits:
            existing_marker = (
                existing.source,
                normalize_doi(existing.doi),
                normalize_title(existing.title),
                existing.zotero_key,
                existing.obsidian_path,
            )
            if existing_marker == marker:
                return
        hits.append(new_hit)


def build_from_zotero(zot, library_id: str) -> list[DedupHit]:
    """Scan the Zotero library and return dedup hits."""
    del library_id
    hits: list[DedupHit] = []
    start = 0
    while True:
        batch = zot.items(start=start, limit=100, itemType="-attachment || note")
        if not batch:
            break
        for item in batch:
            data = item.get("data", {})
            if data.get("itemType") in ("attachment", "note"):
                continue
            hits.append(
                DedupHit(
                    source="zotero",
                    doi=data.get("DOI", ""),
                    title=data.get("title", ""),
                    zotero_key=item.get("key"),
                )
            )
        if len(batch) < 100:
            break
        start += 100
    return hits


def build_from_obsidian(vault_raw_dir: Path) -> list[DedupHit]:
    """Scan Obsidian raw notes and return dedup hits."""
    hits: list[DedupHit] = []
    if not vault_raw_dir.exists():
        return hits
    for md_path in vault_raw_dir.rglob("*.md"):
        try:
            text = md_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        if end < 0:
            continue
        frontmatter = text[3:end]
        title_match = re.search(r'^title:\s*"([^"]+)"', frontmatter, re.MULTILINE)
        doi_match = re.search(r'^doi:\s*"([^"]*)"', frontmatter, re.MULTILINE)
        key_match = re.search(r'^zotero-key:\s*"?([^"\n]+)"?', frontmatter, re.MULTILINE)
        zotero_key = key_match.group(1) if key_match else None
        if zotero_key == "null":
            zotero_key = None
        hits.append(
            DedupHit(
                source="obsidian",
                doi=doi_match.group(1) if doi_match else "",
                title=title_match.group(1) if title_match else "",
                zotero_key=zotero_key,
                obsidian_path=str(md_path),
            )
        )
    return hits
