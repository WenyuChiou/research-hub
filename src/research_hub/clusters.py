"""Topic cluster registry for Research Hub."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Cluster:
    """Stable named container for a line of inquiry."""

    slug: str
    name: str
    seed_keywords: list[str] = field(default_factory=list)
    zotero_collection_key: str | None = None
    obsidian_subfolder: str = ""
    notebooklm_notebook: str = ""
    created_at: str = ""
    first_query: str = ""
    description: str = ""


def slugify(text: str) -> str:
    """Turn free text into a cluster slug."""
    normalized = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    stopwords = {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "and",
        "or",
        "by",
        "from",
        "as",
        "this",
        "that",
        "is",
        "are",
        "between",
        "their",
        "these",
        "those",
    }
    parts = [part for part in normalized.split("-") if part and part not in stopwords]
    slug = "-".join(parts[:6])
    return slug or "unnamed-cluster"


class ClusterRegistry:
    """Load and save cluster definitions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.clusters: dict[str, Cluster] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            import yaml

            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except ImportError:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        for slug, cluster_dict in (data.get("clusters") or {}).items():
            clean = {key: value for key, value in cluster_dict.items() if key != "slug"}
            self.clusters[slug] = Cluster(slug=slug, **clean)

    def save(self) -> None:
        """Persist cluster definitions."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "clusters": {
                cluster.slug: {
                    key: value for key, value in asdict(cluster).items() if key != "slug"
                }
                for cluster in self.clusters.values()
            }
        }
        try:
            import yaml

            self.path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except ImportError:
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, slug: str) -> Cluster | None:
        """Get a cluster by slug."""
        return self.clusters.get(slug)

    def list(self) -> list[Cluster]:
        """List all clusters."""
        return list(self.clusters.values())

    def create(
        self,
        query: str,
        name: str | None = None,
        slug: str | None = None,
        seed_keywords: list[str] | None = None,
        **kwargs,
    ) -> Cluster:
        """Create a cluster from a query or return the existing one."""
        final_slug = slug or slugify(query)
        if final_slug in self.clusters:
            return self.clusters[final_slug]
        from datetime import datetime, timezone

        cluster = Cluster(
            slug=final_slug,
            name=name or query[:80],
            seed_keywords=seed_keywords or [part for part in slugify(query).split("-") if len(part) > 2],
            first_query=query,
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            obsidian_subfolder=final_slug,
            **kwargs,
        )
        self.clusters[final_slug] = cluster
        self.save()
        return cluster

    def match_by_query(self, query: str, min_overlap: int = 2) -> Cluster | None:
        """Match the best existing cluster by keyword overlap."""
        query_words = set(slugify(query).split("-"))
        best_overlap = 0
        best_cluster: Cluster | None = None
        for cluster in self.clusters.values():
            overlap = len(query_words & set(cluster.seed_keywords))
            if overlap > best_overlap and overlap >= min_overlap:
                best_overlap = overlap
                best_cluster = cluster
        return best_cluster
