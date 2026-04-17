"""Topic cluster registry for Research Hub."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from research_hub.config import get_config
from research_hub.operations import _update_frontmatter_field, move_paper, note_matches_query
from research_hub.security import atomic_write_text, safe_join

logger = logging.getLogger(__name__)


@dataclass
class Cluster:
    """Stable named container for a line of inquiry."""

    slug: str
    name: str
    seed_keywords: list[str] = field(default_factory=list)
    zotero_collection_key: str | None = None
    obsidian_subfolder: str = ""
    notebooklm_notebook: str = ""
    notebooklm_notebook_url: str = ""
    notebooklm_notebook_id: str = ""
    created_at: str = ""
    first_query: str = ""
    description: str = ""


def score_cluster_match(query_tokens: set[str], cluster: "Cluster") -> int:
    """Count how many slugified query tokens overlap with cluster seed keywords."""
    return len(query_tokens & set(cluster.seed_keywords))


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

            atomic_write_text(
                self.path,
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except ImportError:
            atomic_write_text(
                self.path,
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def get(self, slug: str) -> Cluster | None:
        """Get a cluster by slug."""
        return self.clusters.get(slug)

    def raw_dir(self, slug: str, vault_raw: Path | None = None) -> Path:
        """Return a cluster raw directory using safe path joining."""
        return safe_join(vault_raw or get_config().raw, slug)

    def hub_dir(self, slug: str, hub_root: Path | None = None) -> Path:
        """Return a cluster hub directory using safe path joining."""
        root = hub_root or get_config().hub
        return safe_join(root, slug)

    def list(self) -> list[Cluster]:
        """List all clusters."""
        return list(self.clusters.values())

    def _refresh_graph_if_possible(self) -> None:
        try:
            cfg = get_config()
        except Exception:
            return
        if not hasattr(cfg, "root"):
            return
        try:
            from research_hub.vault.graph_config import refresh_graph_from_vault

            refresh_graph_from_vault(cfg)
        except Exception as exc:
            logger.warning("graph refresh failed after cluster change: %s", exc)

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
        self._refresh_graph_if_possible()
        return cluster

    def bind(
        self,
        slug: str,
        *,
        zotero_collection_key: str | None = None,
        obsidian_subfolder: str | None = None,
        notebooklm_notebook: str | None = None,
        notebooklm_notebook_url: str | None = None,
        notebooklm_notebook_id: str | None = None,
    ) -> Cluster:
        """Update the cluster's system bindings. Only non-None params are changed."""
        cluster = self.clusters.get(slug)
        if cluster is None:
            raise ValueError(f"Cluster not found: {slug}")
        if zotero_collection_key is not None:
            cluster.zotero_collection_key = zotero_collection_key
        if obsidian_subfolder is not None:
            cluster.obsidian_subfolder = obsidian_subfolder
        if notebooklm_notebook is not None:
            cluster.notebooklm_notebook = notebooklm_notebook
        if notebooklm_notebook_url is not None:
            cluster.notebooklm_notebook_url = notebooklm_notebook_url
        if notebooklm_notebook_id is not None:
            cluster.notebooklm_notebook_id = notebooklm_notebook_id
        self.save()
        self._refresh_graph_if_possible()
        return cluster

    def rename(self, slug: str, new_name: str) -> Cluster:
        """Rename a cluster display name without changing its slug."""
        cluster = self.clusters.get(slug)
        if cluster is None:
            raise ValueError(f"Cluster not found: {slug}")
        cluster.name = new_name
        self.save()
        self._refresh_graph_if_possible()
        return cluster

    def delete(self, slug: str, dry_run: bool = False) -> dict[str, str | int | bool]:
        """Delete a cluster registry entry and unbind its notes."""
        if slug not in self.clusters:
            raise ValueError(f"Cluster not found: {slug}")
        cfg = get_config()
        note_paths = sorted((cfg.raw / slug).glob("*.md"))
        if not dry_run:
            self.clusters.pop(slug)
            for note_path in note_paths:
                _update_frontmatter_field(note_path, "topic_cluster", "")
            self.save()
            self._refresh_graph_if_possible()
        return {"slug": slug, "notes_unbound": len(note_paths), "dry_run": dry_run}

    def merge(self, source_slug: str, target_slug: str, vault_raw: Path | None = None) -> dict[str, str | int]:
        """Move all notes from one cluster into another and delete the source."""
        source = self.clusters.get(source_slug)
        target = self.clusters.get(target_slug)
        if source is None:
            raise ValueError(f"Cluster not found: {source_slug}")
        if target is None:
            raise ValueError(f"Cluster not found: {target_slug}")
        raw_dir = vault_raw or get_config().raw
        moved = 0
        for note_path in sorted((raw_dir / source_slug).glob("*.md")):
            move_paper(note_path.stem, target_slug)
            moved += 1
        self.clusters.pop(source.slug)
        self.save()
        self._refresh_graph_if_possible()
        return {"source": source_slug, "target": target_slug, "moved": moved}

    def split(
        self,
        source_slug: str,
        query: str,
        new_name: str,
        seed_keywords: list[str] | None = None,
        vault_raw: Path | None = None,
    ) -> dict[str, str | int]:
        """Create a new cluster and move matching notes from the source cluster."""
        source = self.clusters.get(source_slug)
        if source is None:
            raise ValueError(f"Cluster not found: {source_slug}")
        raw_dir = vault_raw or get_config().raw
        new_cluster = self.create(query, name=new_name, seed_keywords=seed_keywords)
        moved = 0
        remaining = 0
        for note_path in sorted((raw_dir / source_slug).glob("*.md")):
            if note_matches_query(note_path, query):
                move_paper(note_path.stem, new_cluster.slug)
                moved += 1
            else:
                remaining += 1
        self._refresh_graph_if_possible()
        return {
            "source": source_slug,
            "new_cluster": new_cluster.slug,
            "moved": moved,
            "remaining": remaining,
        }

    def match_by_query(self, query: str, min_overlap: int = 2) -> Cluster | None:
        """Match the best existing cluster by keyword overlap."""
        query_tokens = set(slugify(query).split("-"))
        best: tuple[int, Cluster | None] = (0, None)
        for cluster in self.clusters.values():
            overlap = score_cluster_match(query_tokens, cluster)
            if overlap > best[0] and overlap >= min_overlap:
                best = (overlap, cluster)
        return best[1]
