"""Deduplication index for Research Hub.

Checks DOI and normalized-title matches across BOTH Zotero and the Obsidian vault.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

from research_hub.security import atomic_write_text
from research_hub.utils.doi import normalize_doi  # re-export

logger = logging.getLogger(__name__)


def _normalized_real_doi(doi: object) -> str:
    ndoi = normalize_doi(str(doi or ""))
    return ndoi if (ndoi.startswith("10.") and "/" in ndoi) else ""


def normalize_title(title: str | None) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    if not title:
        return ""
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def normalize_title_unicode(title: str | None) -> str:
    """Casefold, fold Latin diacritics, preserve non-Latin letters, collapse punctuation/spaces."""
    if not title:
        return ""
    from research_hub.workspace.sync_hooks import _fold_latin_diacritics

    folded = _fold_latin_diacritics(title).casefold()
    chars = [
        ch if unicodedata.category(ch)[0] in ("L", "N", "M") else " "
        for ch in folded
    ]
    return " ".join("".join(chars).split())


@dataclass
class DedupHit:
    """A single deduplication hit from Zotero or Obsidian."""

    source: str
    doi: str = ""
    title: str = ""
    zotero_key: str | None = None
    obsidian_path: str | None = None
    year: int | str | None = None
    authors: list[str] = field(default_factory=list)
    volume: str = ""
    edition: str = ""


_DEDUP_HIT_FIELDS = frozenset({
    "source",
    "doi",
    "title",
    "zotero_key",
    "obsidian_path",
    "year",
    "authors",
    "volume",
    "edition",
})


def _hit_from_dict(raw: dict) -> DedupHit:
    filtered = {k: v for k, v in raw.items() if k in _DEDUP_HIT_FIELDS}
    if "authors" in filtered:
        authors = filtered["authors"]
        if authors is None:
            filtered["authors"] = []
        elif isinstance(authors, str):
            filtered["authors"] = [authors] if authors.strip() else []
        elif isinstance(authors, list):
            filtered["authors"] = [str(a) for a in authors if a is not None]
        else:
            filtered["authors"] = []
    if "volume" in filtered:
        filtered["volume"] = "" if filtered["volume"] is None else str(filtered["volume"])
    if "edition" in filtered:
        filtered["edition"] = "" if filtered["edition"] is None else str(filtered["edition"])
    return DedupHit(**filtered)


def _extract_year_4digit(raw_value: object) -> int | None:
    if raw_value in (None, ""):
        return None
    text = str(raw_value).strip()
    for match in re.finditer(r"(?<!\d)(\d{4})(?!\d)", text):
        year_val = int(match.group(1))
        if 1000 <= year_val <= 2100:
            return year_val
    return None


def _extract_zotero_item_identity(item_or_data: dict) -> dict:
    """Extract normalized bibliographic identity from a Zotero item or data dict."""
    if not isinstance(item_or_data, dict):
        return {
            "doi": "",
            "title": "",
            "zotero_key": None,
            "year": None,
            "authors": [],
            "volume": "",
            "edition": "",
        }
    data = item_or_data.get("data") if isinstance(item_or_data.get("data"), dict) else item_or_data
    raw_zkey = (
        item_or_data.get("key")
        or data.get("key")
        or data.get("zotero_key")
        or data.get("zotero-key")
    )
    zotero_key = str(raw_zkey).strip() if raw_zkey else None
    doi = str(data.get("DOI") or data.get("doi") or "").strip()
    title = str(data.get("title") or "").strip()
    raw_date = data.get("date") if data.get("date") not in (None, "") else data.get("year")
    year = _extract_year_4digit(raw_date)
    if year is None and data.get("year") not in (None, "") and raw_date is not data.get("year"):
        year = _extract_year_4digit(data.get("year"))

    authors: list[str] = []
    creators = data.get("creators")
    if isinstance(creators, list):
        for creator in creators:
            if isinstance(creator, dict):
                last = str(creator.get("lastName") or "").strip()
                first = str(creator.get("firstName") or "").strip()
                if last:
                    authors.append(f"{last}, {first}" if first else last)
                elif creator.get("name"):
                    name = str(creator.get("name") or "").strip()
                    if name:
                        authors.append(name)
            elif isinstance(creator, str) and creator.strip():
                authors.append(creator.strip())
    if not authors:
        raw_authors = data.get("authors")
        if isinstance(raw_authors, list):
            for author in raw_authors:
                if isinstance(author, str) and author.strip():
                    authors.append(author.strip())
                elif isinstance(author, dict):
                    last = str(author.get("lastName") or author.get("family") or "").strip()
                    first = str(author.get("firstName") or author.get("given") or "").strip()
                    if last:
                        authors.append(f"{last}, {first}" if first else last)
                    elif author.get("name"):
                        name = str(author.get("name") or "").strip()
                        if name:
                            authors.append(name)
        elif isinstance(raw_authors, str) and raw_authors.strip():
            authors = [part.strip() for part in raw_authors.split(";") if part.strip()] if ";" in raw_authors else [raw_authors.strip()]

    return {
        "doi": doi,
        "title": title,
        "zotero_key": zotero_key or None,
        "year": year,
        "authors": authors,
        "volume": str(data.get("volume") or "").strip(),
        "edition": str(data.get("edition") or "").strip(),
    }


@dataclass
class DedupCompactReport:
    before_doi_keys: int = 0
    before_title_keys: int = 0
    after_doi_keys: int = 0
    after_title_keys: int = 0
    removed_zotero_keys: list[str] = field(default_factory=list)
    dry_run: bool = True


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
            index.doi_to_hits[doi] = [_hit_from_dict(hit) for hit in hits]
        for title, hits in data.get("title_to_hits", {}).items():
            index.title_to_hits[title] = [_hit_from_dict(hit) for hit in hits]
        return index

    def save(self, path: Path) -> None:
        """Persist the index to disk.

        v0.91.0 W4 (G2 #9): top-level `schema_version: "1.0"` for
        third-party parser stability. Older files without this field
        load as schema 1.0 implicitly (see `load`).
        """
        from research_hub.locks import file_lock
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "doi_to_hits": {
                doi: [hit.__dict__ for hit in hits] for doi, hits in self.doi_to_hits.items()
            },
            "title_to_hits": {
                title: [hit.__dict__ for hit in hits]
                for title, hits in self.title_to_hits.items()
            },
        }
        with file_lock(path):
            atomic_write_text(
                path,
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

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
            incoming_real_doi = _normalized_real_doi(doi)
            normalized_title = normalize_title(title)
            if normalized_title and normalized_title in self.title_to_hits:
                for hit in self.title_to_hits[normalized_title]:
                    hit_real_doi = _normalized_real_doi(hit.doi)
                    if (
                        incoming_real_doi
                        and hit_real_doi
                        and incoming_real_doi != hit_real_doi
                    ):
                        continue
                    matches.append(hit)
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
        """Rescan vault notes and rebuild the Obsidian side of the index.

        v0.49.3: also drop ANY hit whose ``obsidian_path`` no longer exists,
        regardless of ``source``. The original implementation only purged
        ``source='obsidian'`` hits, which left importer-tagged stale paths
        behind forever (doctor would warn about them, ``tidy`` couldn't
        clear them, only manual ``dedup invalidate --path X`` worked).
        """
        def _is_alive(hit: "DedupHit") -> bool:
            # Hits without an obsidian_path (pure-Zotero hits) are always kept.
            if not hit.obsidian_path:
                return True
            return Path(hit.obsidian_path).exists()

        for key in list(self.title_to_hits.keys()):
            self.title_to_hits[key] = [
                hit for hit in self.title_to_hits[key]
                if hit.source != "obsidian" and _is_alive(hit)
            ]
            if not self.title_to_hits[key]:
                del self.title_to_hits[key]
        for key in list(self.doi_to_hits.keys()):
            self.doi_to_hits[key] = [
                hit for hit in self.doi_to_hits[key]
                if hit.source != "obsidian" and _is_alive(hit)
            ]
            if not self.doi_to_hits[key]:
                del self.doi_to_hits[key]
        for hit in build_from_obsidian(raw_root):
            self.add(hit)
        return self

    def compact(self, raw_root: Path, zot=None, *, dry_run: bool = True) -> tuple["DedupIndex", DedupCompactReport]:
        """Rebuild Obsidian hits and drop Zotero hits whose item now 404s."""

        compacted = self.copy()
        report = DedupCompactReport(
            before_doi_keys=len(self.doi_to_hits),
            before_title_keys=len(self.title_to_hits),
            dry_run=dry_run,
        )
        compacted.rebuild_from_obsidian(raw_root)
        stale_keys = _find_stale_zotero_keys(compacted, zot) if zot is not None else []
        if stale_keys:
            _remove_zotero_keys(compacted, set(stale_keys))
        report.removed_zotero_keys = stale_keys
        report.after_doi_keys = len(compacted.doi_to_hits)
        report.after_title_keys = len(compacted.title_to_hits)
        return compacted, report

    def copy(self) -> "DedupIndex":
        copied = DedupIndex.empty()
        copied.doi_to_hits = {
            key: [_hit_from_dict(hit.__dict__) for hit in hits]
            for key, hits in self.doi_to_hits.items()
        }
        copied.title_to_hits = {
            key: [_hit_from_dict(hit.__dict__) for hit in hits]
            for key, hits in self.title_to_hits.items()
        }
        return copied

    @staticmethod
    def _append_unique(hits: list[DedupHit], new_hit: DedupHit) -> None:
        marker = (
            new_hit.source,
            normalize_doi(new_hit.doi),
            normalize_title(new_hit.title),
            new_hit.zotero_key,
            new_hit.obsidian_path,
            str(new_hit.year or "").strip(),
            str(new_hit.volume or "").strip().lower(),
            str(new_hit.edition or "").strip().lower(),
        )
        for existing in hits:
            existing_marker = (
                existing.source,
                normalize_doi(existing.doi),
                normalize_title(existing.title),
                existing.zotero_key,
                existing.obsidian_path,
                str(existing.year or "").strip(),
                str(existing.volume or "").strip().lower(),
                str(existing.edition or "").strip().lower(),
            )
            if existing_marker == marker:
                return
        hits.append(new_hit)


def _find_stale_zotero_keys(index: DedupIndex, zot) -> list[str]:
    keys: set[str] = set()
    for mapping in (index.doi_to_hits, index.title_to_hits):
        for hits in mapping.values():
            for hit in hits:
                if hit.source == "zotero" and hit.zotero_key:
                    keys.add(hit.zotero_key)
    stale: list[str] = []
    for key in sorted(keys):
        try:
            zot.item(key)
        except Exception as exc:
            if _is_404_error(exc):
                stale.append(key)
            else:
                raise
    return stale


def _remove_zotero_keys(index: DedupIndex, stale_keys: set[str]) -> None:
    for mapping in (index.doi_to_hits, index.title_to_hits):
        for key in list(mapping.keys()):
            kept = [
                hit for hit in mapping[key]
                if not (hit.source == "zotero" and hit.zotero_key in stale_keys)
            ]
            if kept:
                mapping[key] = kept
            else:
                del mapping[key]


_ZOTERO_TRANSPORT_ERROR_MARKERS = (
    "gaierror",
    "connecterror",
    "connectionerror",
    "dnserror",
    "timeout",
    "timed out",
    "host not found",
    "name or service not known",
    "nodename nor servname",
    "getaddrinfo",
)


def is_zotero_not_found_error(exc: Exception) -> bool:
    """Return True iff *exc* represents a definitive HTTP 404 Not Found from Zotero."""
    if "pyzotero" in type(exc).__module__.lower():
        if type(exc).__name__ == "ResourceNotFoundError":
            return True
        code_match = re.search(r"(?im)^\s*code:\s*(\d{3})\b", str(exc))
        if code_match:
            return int(code_match.group(1)) == 404

    candidates = [
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
    ]
    if isinstance(exc, urllib.error.HTTPError) or not isinstance(exc, OSError):
        candidates.append(getattr(exc, "code", None))
    for val in candidates:
        if isinstance(val, bool) or val is None:
            continue
        num: int | None = None
        if isinstance(val, int):
            num = val
        elif isinstance(val, str):
            stripped = val.strip()
            if stripped.isascii() and stripped.isdigit():
                num = int(stripped)
        if num is not None and 100 <= num <= 599:
            return num == 404

    if (
        isinstance(exc, OSError)
        or isinstance(getattr(exc, "__cause__", None), OSError)
        or isinstance(getattr(exc, "__context__", None), OSError)
    ):
        return False
    exc_name = type(exc).__name__.lower()
    msg = str(exc)
    msg_lower = msg.lower()
    if any(marker in exc_name or marker in msg_lower for marker in _ZOTERO_TRANSPORT_ERROR_MARKERS):
        return False

    msg_clean = re.sub(r"https?://\S+|/(?:users|groups)/\d+(?:/\S*)?", " ", msg)
    if re.search(
        r"(?i)(?:\bcode\s*[:=]\s*|\bstatus(?:\s+code)?\s*[:=]?\s*|\bhttp(?:/\d(?:\.\d)?)?\s+)(?!404\b)[1-5]\d{2}\b",
        msg_clean,
    ):
        return False
    return bool(
        re.search(
            r"(?i)(?:^\s*404\b|\b(?:http(?:/\d(?:\.\d)?)?|status(?:\s+code)?|code|error)\s*[:=]?\s*404\b|\b404\s+(?:item\s+)?not\s+found\b)",
            msg_clean,
        )
    )


def _is_404_error(exc: Exception) -> bool:
    return is_zotero_not_found_error(exc)


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
            ident = _extract_zotero_item_identity(item)
            hits.append(
                DedupHit(
                    source="zotero",
                    doi=ident["doi"],
                    title=ident["title"],
                    zotero_key=ident["zotero_key"],
                    year=ident["year"],
                    authors=ident["authors"],
                    volume=ident["volume"],
                    edition=ident["edition"],
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
        try:
            import yaml

            parsed = yaml.safe_load(frontmatter) or {}
            if not isinstance(parsed, dict):
                parsed = {}
        except ImportError:
            parsed = {}
        except Exception as exc:
            logger.warning("Skipping malformed frontmatter in %s: %s", md_path, exc)
            continue
        if parsed:
            title = str(parsed.get("title", "") or "")
            doi = str(parsed.get("doi", "") or "")
            zotero_key = parsed.get("zotero-key")
        else:
            title_match = re.search(r'^title:\s*"([^"]+)"', frontmatter, re.MULTILINE)
            doi_match = re.search(r'^doi:\s*"([^"]*)"', frontmatter, re.MULTILINE)
            key_match = re.search(r'^zotero-key:\s*"?([^"\n]+)"?', frontmatter, re.MULTILINE)
            title = title_match.group(1) if title_match else ""
            doi = doi_match.group(1) if doi_match else ""
            zotero_key = key_match.group(1) if key_match else None
        if zotero_key == "null":
            zotero_key = None
        hits.append(
            DedupHit(
                source="obsidian",
                doi=doi,
                title=title,
                zotero_key=zotero_key,
                obsidian_path=str(md_path),
            )
        )
    return hits
