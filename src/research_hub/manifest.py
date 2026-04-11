"""Append-only ingestion manifest for Research Hub."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ManifestEntry:
    """Single ingestion log line."""

    timestamp: str
    cluster: str
    query: str
    action: str
    doi: str = ""
    title: str = ""
    zotero_key: str = ""
    obsidian_path: str = ""
    error: str = ""


class Manifest:
    """Append-only JSONL manifest."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, entry: ManifestEntry) -> None:
        """Append an entry to the manifest."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def read_all(self) -> list[ManifestEntry]:
        """Read all valid manifest entries."""
        if not self.path.exists():
            return []
        entries: list[ManifestEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                payload = line.strip()
                if not payload:
                    continue
                try:
                    entries.append(ManifestEntry(**json.loads(payload)))
                except Exception:
                    continue
        return entries

    def get_ingested_keys(self, cluster: str) -> set[str]:
        """Return newly ingested Zotero keys for a cluster."""
        return {
            entry.zotero_key
            for entry in self.read_all()
            if entry.cluster == cluster and entry.zotero_key and entry.action == "new"
        }

    def count_by_action(self, cluster: str | None = None) -> dict[str, int]:
        """Return action counts, optionally scoped to a cluster."""
        counts: dict[str, int] = {}
        for entry in self.read_all():
            if cluster and entry.cluster != cluster:
                continue
            counts[entry.action] = counts.get(entry.action, 0) + 1
        return counts


def new_entry(cluster: str, query: str, action: str, **kwargs) -> ManifestEntry:
    """Create a manifest entry with the current UTC timestamp."""
    return ManifestEntry(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        cluster=cluster,
        query=query,
        action=action,
        **kwargs,
    )
