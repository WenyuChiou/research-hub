"""Topic cluster registry for Research Hub."""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

from research_hub.config import get_config
from research_hub.operations import _update_frontmatter_field, move_paper, note_matches_query
from research_hub.security import atomic_write_text, safe_join

# Imported at module level so tests can patch research_hub.clusters._resolve_parent_collection_key_readonly
# without patching the source module (avoids local-import binding issues).
def _resolve_parent_collection_key_readonly(cfg) -> str:
    """Thin module-level shim — delegates to the canonical implementation in zotero.client.

    Defined here so the delete guard can be monkeypatched in tests without
    fighting Python's local-import binding semantics.
    """
    from research_hub.zotero.client import (
        _resolve_parent_collection_key_readonly as _impl,
    )
    return _impl(cfg)

logger = logging.getLogger(__name__)


class CollisionError(ValueError):
    """Raised when two clusters attempt to bind the same Zotero collection key."""


def _try_sync_zotero_collection_name(key: str, vault_name: str) -> None:
    """Best-effort: PATCH Zotero collection name to match the vault name.

    On failure, logs AND prints to stderr so CLI users actually see the
    drift warning (logger.warning by itself is silent in default CLI use).
    """
    import sys as _sys
    try:
        from research_hub.zotero.client import ZoteroDualClient, get_client

        try:
            zot = ZoteroDualClient().web
        except Exception:
            zot = get_client()
        coll = zot.collection(key)
        current_version = coll.get("version") or coll.get("data", {}).get("version")
        if not current_version:
            msg = f"WARN: could not read version for Zotero coll {key}; skip name sync"
            logger.warning(msg)
            print(msg, file=_sys.stderr)
            return
        if coll.get("data", {}).get("name") == vault_name:
            logger.info("Zotero coll %s already matches vault name %r", key, vault_name)
            return
        zot.update_collection({"key": key, "version": current_version, "name": vault_name})
        logger.info("synced Zotero coll %s name to %r", key, vault_name)
    except Exception as exc:
        msg = (
            f"WARN: failed to sync Zotero coll {key} name to {vault_name!r}: {exc}\n"
            f"  Vault left at OLD name. Re-run: python -m research_hub clusters sync-names --apply"
        )
        logger.warning(msg)
        print(msg, file=_sys.stderr)


def _try_restore_zotero_collection(key: str) -> tuple[bool, str]:
    """Best-effort: clear Zotero's deleted flag for a collection."""
    try:
        from research_hub.zotero.client import ZoteroDualClient

        zot = ZoteroDualClient().web
        coll = zot.collection(key)
        version = coll.get("version") or coll.get("data", {}).get("version")
        data = dict(coll.get("data", {}))
        if not data.get("deleted"):
            return (True, f"{key}: already active (no restore needed)")
        data["deleted"] = 0
        data.setdefault("key", key)
        if version:
            data["version"] = version
        zot.update_collection(data)
        return (True, f"{key}: restored from Zotero trash")
    except Exception as exc:
        return (False, f"{key}: restore failed: {exc}")


@dataclass
class CascadeReport:
    slug: str
    obsidian_papers: int = 0
    zotero_items_in_collection: int = 0
    dedup_entries: int = 0
    memory_entries: int = 0
    crystal_files: int = 0
    obsidian_folder_size_bytes: int = 0

    def has_data(self) -> bool:
        return any(
            [
                self.obsidian_papers,
                self.zotero_items_in_collection,
                self.dedup_entries,
                self.memory_entries,
                self.crystal_files,
            ]
        )

    def summary(self) -> str:
        lines = [
            f"Cascade delete preview for '{self.slug}':",
            f"  Obsidian papers:            {self.obsidian_papers}",
            f"  Zotero collection items:    {self.zotero_items_in_collection}",
            f"  Dedup entries:              {self.dedup_entries}",
            f"  Memory entries:             {self.memory_entries}",
            f"  Crystal files:              {self.crystal_files}",
            f"  Obsidian folder bytes:      {self.obsidian_folder_size_bytes}",
        ]
        return "\n".join(lines)


@dataclass
class NotebookShard:
    notebook_id: str
    notebook_url: str
    notebook_name: str
    source_count: int
    source_doi_list: list[str]
    created_at: str


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
    notebooklm_shards: list[NotebookShard] = field(default_factory=list)
    moc_links: list[str] = field(default_factory=list)
    created_at: str = ""
    first_query: str = ""
    description: str = ""
    status: str = "active"
    archived_at: str = ""
    group: str = ""  # optional free-text group tag (e.g. "water-resources", "llm-methods")


@dataclass
class ClusterCoverage:
    """Coverage metrics for a single cluster."""

    slug: str
    name: str
    paper_count: int = 0
    pending_summary: int = 0
    coverage_score: int = 0
    latest_mtime: float = 0.0  # max mtime (seconds since epoch) of paper files


def _load_notebooklm_shards(value: object) -> list[NotebookShard]:
    if not isinstance(value, list):
        return []
    shards: list[NotebookShard] = []
    for item in value:
        if isinstance(item, NotebookShard):
            shards.append(item)
            continue
        if not isinstance(item, dict):
            continue
        shards.append(
            NotebookShard(
                notebook_id=str(item.get("notebook_id", "") or ""),
                notebook_url=str(item.get("notebook_url", "") or ""),
                notebook_name=str(item.get("notebook_name", "") or ""),
                source_count=int(item.get("source_count", 0) or 0),
                source_doi_list=[str(doi) for doi in (item.get("source_doi_list") or [])],
                created_at=str(item.get("created_at", "") or ""),
            )
        )
    return shards


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


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        raw_clusters = data.get("clusters") or {}
        if isinstance(raw_clusters, list):
            cluster_items = []
            for item in raw_clusters:
                if not isinstance(item, dict):
                    continue
                slug = str(item.get("slug", "") or "").strip().lower()
                if slug:
                    cluster_items.append((slug, item))
        elif isinstance(raw_clusters, dict):
            cluster_items = raw_clusters.items()
        else:
            cluster_items = []
        for slug, cluster_dict in cluster_items:
            if not isinstance(cluster_dict, dict):
                continue
            clean = {key: value for key, value in cluster_dict.items() if key != "slug"}
            clean["notebooklm_shards"] = _load_notebooklm_shards(clean.get("notebooklm_shards"))
            self.clusters[slug] = Cluster(slug=slug, **clean)

    def save(self) -> None:
        """Persist cluster definitions.

        v0.91.0 W4 (G2 #9): payload now includes `schema_version: "1.0"`
        as the documented contract for third-party parsers. Older files
        without this field are still readable (see `_load`); they're
        treated as schema 1.0 implicitly.
        """
        from research_hub.locks import file_lock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "clusters": {
                cluster.slug: {
                    key: value for key, value in asdict(cluster).items() if key != "slug"
                }
                for cluster in self.clusters.values()
            },
        }
        with file_lock(self.path):
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
        """Get a cluster by slug. Case-insensitive."""
        if not isinstance(slug, str):
            return None
        return self.clusters.get(slug.strip().lower())

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
        try:
            if Path(cfg.clusters_file).resolve() != self.path.resolve():
                return
        except Exception:
            return
        if not hasattr(cfg, "root"):
            return
        try:
            from research_hub.vault.graph_config import refresh_graph_from_vault

            refresh_graph_from_vault(cfg)
        except Exception as exc:
            logger.warning("graph refresh failed after cluster change: %s", exc)

    def _auto_create_zotero_collection(self, cluster: Cluster, progress=None) -> None:
        try:
            cfg = get_config()
        except Exception as exc:
            if progress:
                progress(f"WARN: Zotero collection auto-create failed: {exc}")
            return
        if getattr(cfg, "no_zotero", False) or cluster.zotero_collection_key:
            return
        if not getattr(cfg, "zotero_api_key", None) or not getattr(cfg, "zotero_library_id", None):
            return
        try:
            if Path(cfg.clusters_file).resolve() != self.path.resolve():
                return
        except Exception:
            return
        try:
            from research_hub.zotero.client import ZoteroDualClient, ensure_parent_collection

            dual = ZoteroDualClient()
            web = dual.web
            parent_name = getattr(cfg, "zotero_parent_collection", "research-hub")
            parent_key: str | bool = ensure_parent_collection(dual, parent_name) if parent_name else False
            resp = web.create_collections(
                [{"name": cluster.name, "parentCollection": parent_key if parent_key else False}]
            )
            if resp and isinstance(resp, dict) and resp.get("successful"):
                new_key = list(resp["successful"].values())[0]["key"]
                cluster.zotero_collection_key = new_key
                self.save()
                if progress:
                    progress(f"Created Zotero collection: {new_key}")
        except Exception as exc:
            if progress:
                progress(f"WARN: Zotero collection auto-create failed: {exc}")

    def create(
        self,
        query: str,
        name: str | None = None,
        slug: str | None = None,
        seed_keywords: list[str] | None = None,
        progress=None,
        **kwargs,
    ) -> Cluster:
        """Create a cluster from a query or return the existing one.

        Also scaffolds hub/<slug>/ on first creation.
        """
        final_slug = (slug or slugify(query)).strip().lower()
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
        self._auto_create_zotero_collection(cluster, progress=progress)
        self._refresh_graph_if_possible()
        try:
            from research_hub.topic import scaffold_cluster_hub

            cfg = get_config()
            if Path(cfg.clusters_file).resolve() != self.path.resolve():
                root = self.path.parent.parent
                cfg = SimpleNamespace(
                    root=root,
                    raw=root / "raw",
                    hub=root / "hub",
                    research_hub_dir=self.path.parent,
                    clusters_file=self.path,
                )
            scaffold_cluster_hub(cfg, final_slug)
        except Exception as exc:
            logger.warning("hub scaffold failed for cluster %s: %s", final_slug, exc)
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
        notebooklm_shards: list[NotebookShard] | None = None,
        sync_zotero: bool = True,
        force_shared: bool = False,
    ) -> Cluster:
        """Update the cluster's system bindings. Only non-None params are changed."""
        cluster = self.clusters.get(slug)
        if cluster is None:
            raise ValueError(f"Cluster not found: {slug}")
        normalized_key = zotero_collection_key
        if isinstance(normalized_key, str):
            normalized_key = normalized_key.strip() or None
        if normalized_key and not force_shared:
            for other_slug, other in self.clusters.items():
                if other_slug == slug:
                    continue
                if (other.zotero_collection_key or "").strip() == normalized_key:
                    raise CollisionError(
                        f"zotero_collection_key '{normalized_key}' is already "
                        f"bound by cluster '{other_slug}'. Pass force_shared=True if intentional."
                    )
        if zotero_collection_key is not None:
            cluster.zotero_collection_key = normalized_key
        if obsidian_subfolder is not None:
            cluster.obsidian_subfolder = obsidian_subfolder
        if notebooklm_notebook is not None:
            cluster.notebooklm_notebook = notebooklm_notebook
        if notebooklm_notebook_url is not None:
            cluster.notebooklm_notebook_url = notebooklm_notebook_url
        if notebooklm_notebook_id is not None:
            cluster.notebooklm_notebook_id = notebooklm_notebook_id
        if notebooklm_shards is not None:
            cluster.notebooklm_shards = notebooklm_shards
        self.save()
        if sync_zotero and cluster.zotero_collection_key and cluster.name:
            _try_sync_zotero_collection_name(cluster.zotero_collection_key, cluster.name)
        self._refresh_graph_if_possible()
        return cluster

    def rename(self, slug: str, new_name: str, *, sync_zotero: bool = True) -> Cluster:
        """Rename a cluster display name without changing its slug.

        Order: Zotero PATCH first (best-effort, prints stderr warning on
        failure), THEN vault save. If both succeed, no drift; if Zotero
        fails, vault stays at the OLD name and the warning tells the user.
        """
        cluster = self.clusters.get(slug)
        if cluster is None:
            raise ValueError(f"Cluster not found: {slug}")
        if sync_zotero and cluster.zotero_collection_key:
            _try_sync_zotero_collection_name(cluster.zotero_collection_key, new_name)
        cluster.name = new_name
        self.save()
        self._refresh_graph_if_possible()
        return cluster

    def archive(self, slug: str) -> Cluster:
        """Mark a cluster inactive and move its hub folder to hub/_archived/<slug>.

        Moves ``hub/<slug>/`` → ``hub/_archived/<slug>/`` so Obsidian's graph
        view can exclude the archived folder. Idempotent: if the cluster is
        already archived (folder already under ``_archived/``) prints a notice
        and returns without error. The cluster's Zotero binding and raw notes
        are NOT touched.
        """
        cluster = self.clusters.get(slug)
        if cluster is None:
            raise ValueError(f"Cluster not found: {slug}")

        cfg = get_config()
        hub_root = cfg.hub
        hub_dir = safe_join(hub_root, slug)
        archived_parent = hub_root / "_archived"
        archived_dir = archived_parent / slug

        if cluster.status == "archived":
            print(f"notice: cluster '{slug}' is already archived (no-op).")
            return cluster

        if hub_dir.exists():
            archived_parent.mkdir(parents=True, exist_ok=True)
            if archived_dir.exists():
                shutil.rmtree(archived_dir)
            shutil.move(str(hub_dir), str(archived_dir))

        cluster.status = "archived"
        cluster.archived_at = _utc_now()
        self.save()
        self._refresh_graph_if_possible()
        return cluster

    def unarchive(self, slug: str) -> Cluster:
        """Restore an archived cluster to active ingest/search workflows.

        Moves ``hub/_archived/<slug>/`` back to ``hub/<slug>/``. Idempotent:
        if the cluster is not currently archived, prints a notice and returns
        without error. The cluster's Zotero binding and raw notes are NOT
        touched.
        """
        cluster = self.clusters.get(slug)
        if cluster is None:
            raise ValueError(f"Cluster not found: {slug}")

        cfg = get_config()
        hub_root = cfg.hub
        hub_dir = safe_join(hub_root, slug)
        archived_dir = hub_root / "_archived" / slug

        if cluster.status != "archived":
            print(f"notice: cluster '{slug}' is not archived (no-op).")
            return cluster

        if archived_dir.exists():
            hub_dir.parent.mkdir(parents=True, exist_ok=True)
            if hub_dir.exists():
                shutil.rmtree(hub_dir)
            shutil.move(str(archived_dir), str(hub_dir))

        cluster.status = "active"
        cluster.archived_at = ""
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


def compute_cluster_cascade_report(cfg, slug: str) -> CascadeReport:
    from research_hub.dedup import DedupIndex
    from research_hub.pipeline_repair import _iter_collection_items
    from research_hub.zotero.client import ZoteroDualClient

    report = CascadeReport(slug=slug)
    raw_dir = safe_join(cfg.raw, slug)
    note_paths = sorted(raw_dir.glob("*.md")) if raw_dir.exists() else []
    report.obsidian_papers = len(note_paths)
    report.obsidian_folder_size_bytes = sum(
        path.stat().st_size for path in note_paths if path.exists()
    )

    hub_dir = safe_join(cfg.hub, slug)
    crystals_dir = hub_dir / "crystals"
    report.crystal_files = len(list(crystals_dir.glob("*.md"))) if crystals_dir.exists() else 0
    memory_json = hub_dir / "memory.json"
    if memory_json.exists():
        try:
            payload = json.loads(memory_json.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            report.memory_entries = sum(
                len(value) for value in payload.values() if isinstance(value, list)
            )

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(slug)
    zotero_keys: set[str] = set()
    if cluster and cluster.zotero_collection_key:
        try:
            zot = ZoteroDualClient().web
            items = _iter_collection_items(zot, cluster.zotero_collection_key)
            report.zotero_items_in_collection = len(items)
            zotero_keys = {
                str(item.get("key") or item.get("data", {}).get("key") or "")
                for item in items
                if (item.get("key") or item.get("data", {}).get("key"))
            }
        except Exception:
            report.zotero_items_in_collection = 0

    dedup = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    obsidian_root = raw_dir.resolve() if raw_dir.exists() else None
    dedup_count = 0
    seen: set[tuple[str | None, str | None]] = set()
    for groups in (dedup.doi_to_hits.values(), dedup.title_to_hits.values()):
        for hits in groups:
            for hit in hits:
                obsidian_match = False
                if obsidian_root and hit.obsidian_path:
                    try:
                        Path(hit.obsidian_path).resolve().relative_to(obsidian_root)
                        obsidian_match = True
                    except Exception:
                        obsidian_match = False
                zotero_match = bool(hit.zotero_key and hit.zotero_key in zotero_keys)
                if obsidian_match or zotero_match:
                    marker = (hit.obsidian_path, hit.zotero_key)
                    if marker not in seen:
                        seen.add(marker)
                        dedup_count += 1
    report.dedup_entries = dedup_count
    return report


def cascade_delete_cluster(
    cfg,
    slug: str,
    *,
    apply: bool,
    delete_zotero_collection: bool = False,
    purge_zotero_items: bool = False,
) -> CascadeReport:
    """Delete a cluster and ALL of its associated data.

    Behaviour:
    - ``apply=False`` (dry-run): returns a :class:`CascadeReport` immediately
      with ZERO Zotero I/O — no network calls, no reads, no writes.
    - ``apply=True``: performs the full cascade delete:
        * Moves ``raw/<slug>/`` → ``raw/_deleted_<slug>/`` (soft delete).
        * Removes ``hub/<slug>/`` (overview, crystals, memory.json, .base,
          briefs) using ``shutil.rmtree`` — never the shell ``rm`` command.
        * Removes ``.research_hub/bundles/<slug>-*`` directories.
        * Removes ``.research_hub/artifacts/<slug>/`` directory.
        * Prunes all lines for this cluster from ``.research_hub/manifest.jsonl``.
        * Prunes ``dedup_index.json`` entries belonging to this cluster.
        * Removes the cluster from ``clusters.yaml``.
        * Zotero: by default, *unbinds* items from the collection (removes the
          collection key from each item's ``collections`` list) and optionally
          deletes the now-empty child collection (``delete_zotero_collection``).
        * If ``purge_zotero_items=True``: deletes each parent item via
          ``ZoteroDualClient.delete_items`` (items go to Zotero trash,
          recoverable until trash emptied). Zotero cascade-deletes child
          attachments (including PDFs) automatically when the parent is trashed,
          so only parent item keys are submitted — submitting child keys
          explicitly would cause 404 failures on an already-removed attachment.
          The operation is strictly scoped to the cluster's own
          ``zotero_collection_key``; parent and sibling collections are never
          enumerated or touched.

    Structural safety invariants (always enforced):
    - All Zotero operations (item enumeration, item deletion, collection
      deletion) operate strictly on the cluster's own ``zotero_collection_key``.
    - An empty ``zotero_collection_key`` is a no-op: the ``if coll_key:``
      block is skipped entirely — no library-wide enumeration ever occurs.
    - Parent and sibling collections are never enumerated or passed to any
      delete operation.
    - Defense-in-depth: if the cluster's own collection key matches the
      configured research-hub parent collection key, the operation is refused
      before any Zotero delete call is made.  The parent key is resolved via
      ``_resolve_parent_collection_key_readonly`` — a read-only lookup that
      NEVER creates a collection — and is checked only on the apply path so
      that dry-run performs zero Zotero I/O.
    - ``purge_zotero_items`` without ``apply`` is a no-op (dry-run only).
    """
    from research_hub.dedup import DedupIndex
    from research_hub.manifest import Manifest
    from research_hub.pipeline_repair import _iter_collection_items
    from research_hub.zotero.client import ZoteroDualClient

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {slug}")

    # Structural safety: all operations below are gated on this cluster's own
    # coll_key — an empty key means the block is skipped entirely (no-op).
    coll_key = (cluster.zotero_collection_key or "").strip()

    # Compute the cascade report (local filesystem + dedup index reads only;
    # also calls Zotero to count items in the collection, but that is a read).
    report = compute_cluster_cascade_report(cfg, slug)

    # Dry-run: return immediately with ZERO Zotero I/O — no network calls,
    # no parent-key resolution, no create side-effects whatsoever.
    if not apply:
        return report

    # Apply path only: defense-in-depth parent-equality guard.
    # Uses _resolve_parent_collection_key_readonly — a read-only lookup that
    # lists existing collections and NEVER creates one.  Falls back to "" on
    # any error; scoping via the coll_key gate above is the primary safety.
    if coll_key:
        parent_key = _resolve_parent_collection_key_readonly(cfg)
        if parent_key and coll_key == parent_key:
            raise ValueError(
                f"Refusing to cascade-delete cluster '{slug}': its "
                f"zotero_collection_key is the research-hub parent collection."
            )

    raw_dir = safe_join(cfg.raw, slug)
    deleted_dir = safe_join(cfg.raw, f"_deleted_{slug}")
    if raw_dir.exists():
        deleted_dir.parent.mkdir(parents=True, exist_ok=True)
        if deleted_dir.exists():
            shutil.rmtree(deleted_dir)
        shutil.move(str(raw_dir), str(deleted_dir))

    if coll_key:
        zot_client = ZoteroDualClient()
        zot = zot_client.web
        items = _iter_collection_items(zot, coll_key)

        if purge_zotero_items:
            # Collect PARENT item keys only — Zotero cascade-deletes child
            # attachments (incl. PDFs) when the parent is trashed, so submitting
            # child keys explicitly would 404 on already-removed items and inflate
            # the failure count with false failures.
            # Strictly scoped: only keys returned from THIS cluster's collection.
            all_keys_to_delete: list[str] = []
            for item in items:
                item_key = item.get("key") or item.get("data", {}).get("key")
                if not item_key:
                    continue
                all_keys_to_delete.append(item_key)
            summary = zot_client.delete_items(all_keys_to_delete)
            if summary["failed"]:
                print(
                    f"warning: {summary['failed']} item(s) failed to delete from "
                    f"Zotero coll {coll_key}: "
                    + ", ".join(e.get("error", "?") for e in summary["errors"]),
                    file=sys.stderr,
                )
            # After parent items are trashed, delete the now-empty child collection.
            try:
                zot_client.delete_collection(coll_key)
            except Exception as exc:
                print(
                    f"warning: failed to delete Zotero coll {coll_key}: {exc}",
                    file=sys.stderr,
                )
        else:
            # Default behavior: unbind items from this collection (remove the
            # collection key from each item's collections list).
            for item in items:
                item_key = item.get("key") or item.get("data", {}).get("key")
                if not item_key:
                    continue
                current = zot.item(item_key)
                data = current.get("data", {})
                collections = [k for k in data.get("collections", []) if k != coll_key]
                data["collections"] = collections
                zot.update_item(data)
            if delete_zotero_collection:
                other_holders = [
                    other.slug
                    for other in ClusterRegistry(cfg.clusters_file).list()
                    if other.slug != slug
                    and (other.zotero_collection_key or "").strip() == coll_key
                ]
                if other_holders:
                    print(
                        f"WARN: refusing to delete Zotero coll {coll_key} "
                        f"because it is still bound by: {', '.join(other_holders)}",
                        file=sys.stderr,
                    )
                else:
                    try:
                        zot_client.delete_collection(coll_key)
                    except Exception as exc:
                        print(
                            f"warning: failed to delete Zotero coll {coll_key}: {exc}"
                        )

    dedup_path = cfg.research_hub_dir / "dedup_index.json"
    dedup = DedupIndex.load(dedup_path)
    for groups in (dedup.doi_to_hits, dedup.title_to_hits):
        for key in list(groups.keys()):
            kept = []
            for hit in groups[key]:
                remove = False
                if hit.obsidian_path:
                    try:
                        Path(hit.obsidian_path).resolve().relative_to(raw_dir.resolve())
                        remove = True
                    except Exception:
                        remove = False
                if remove:
                    continue
                kept.append(hit)
            if kept:
                groups[key] = kept
            else:
                del groups[key]
    dedup.save(dedup_path)

    # hub/<slug>/ — overview, crystals, memory.json, .base, briefs
    hub_dir = safe_join(cfg.hub, slug)
    if hub_dir.exists():
        shutil.rmtree(hub_dir)

    # .research_hub/bundles/<slug>-*/
    bundles_root = cfg.research_hub_dir / "bundles"
    if bundles_root.exists():
        for bundle_dir in bundles_root.glob(f"{slug}-*"):
            if bundle_dir.is_dir():
                shutil.rmtree(bundle_dir)

    # .research_hub/artifacts/<slug>/
    artifacts_dir = cfg.research_hub_dir / "artifacts" / slug
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)

    # Prune manifest.jsonl lines for this cluster
    manifest_path = cfg.research_hub_dir / "manifest.jsonl"
    if manifest_path.exists():
        manifest = Manifest(manifest_path)
        all_entries = manifest.read_all()
        kept_entries = [e for e in all_entries if e.cluster != slug]
        # Rewrite atomically: write to tmp then replace
        import tempfile
        tmp = manifest_path.with_suffix(".jsonl.tmp")
        import json as _json
        import dataclasses
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                for entry in kept_entries:
                    fh.write(_json.dumps(dataclasses.asdict(entry), ensure_ascii=False) + "\n")
            tmp.replace(manifest_path)
        except Exception as exc:
            print(f"warning: failed to prune manifest.jsonl: {exc}", file=sys.stderr)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    registry.clusters.pop(slug, None)
    registry.save()
    registry._refresh_graph_if_possible()
    return report


def enumerate_collection_items_for_purge(
    cfg,
    slug: str,
) -> list[dict]:
    """Return a list of item-info dicts for the cluster's Zotero collection.

    Used by the CLI dry-run to print the purge plan without making any
    writes. Each dict has keys: ``title``, ``doi``, ``key``, ``pdf_count``.

    Returns an empty list if the cluster has no ``zotero_collection_key``
    or if the Zotero client is unavailable.
    """
    from research_hub.pipeline_repair import _iter_collection_items
    from research_hub.zotero.client import ZoteroDualClient

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {slug}")
    coll_key = (cluster.zotero_collection_key or "").strip()
    if not coll_key:
        return []
    try:
        zot = ZoteroDualClient().web
        items = _iter_collection_items(zot, coll_key)
        result: list[dict] = []
        for item in items:
            item_key = item.get("key") or item.get("data", {}).get("key", "")
            data = item.get("data", {})
            title = str(data.get("title", "") or item.get("title", "") or "(no title)")
            doi = str(data.get("DOI", "") or data.get("doi", "") or "")
            pdf_count = 0
            if item_key:
                try:
                    children = zot.children(item_key)
                    pdf_count = sum(
                        1 for c in children
                        if str(c.get("data", {}).get("contentType", "")).startswith("application/pdf")
                    )
                except Exception:
                    pass
            result.append({"key": item_key, "title": title, "doi": doi, "pdf_count": pdf_count})
        return result
    except Exception:
        return []


def compute_coverage(cfg) -> list[ClusterCoverage]:
    """Compute coverage metrics for all active clusters.

    Coverage score formula:
        score = min(100, int(
            min(paper_count / 10.0, 1.0) * 40   # capped at 40 pts
            + (1 - pending_fraction) * 40
            + (1 if paper_count > 0 else 0) * 20
        ))

    ``latest_mtime`` is the max ``st_mtime`` of paper files (seconds since
    epoch), used for ``--sort=recency`` in the coverage CLI command.
    """
    import yaml

    registry = ClusterRegistry(cfg.clusters_file)
    clusters = [
        cluster
        for cluster in registry.list()
        if getattr(cluster, "status", "active") != "archived"
    ]

    frontmatter_re = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
    results: list[ClusterCoverage] = []
    raw_root = Path(cfg.raw)

    for cluster in clusters:
        cluster_dir = raw_root / cluster.slug
        if not cluster_dir.exists():
            results.append(
                ClusterCoverage(
                    slug=cluster.slug,
                    name=cluster.name,
                    paper_count=0,
                    pending_summary=0,
                    coverage_score=0,
                    latest_mtime=0.0,
                )
            )
            continue

        papers = [
            path
            for path in cluster_dir.glob("*.md")
            if not path.name.startswith("00_") and not path.name.startswith("_")
        ]
        paper_count = len(papers)
        pending = 0
        latest_mtime = 0.0
        for paper_path in papers:
            try:
                mtime = paper_path.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
                text = paper_path.read_text(encoding="utf-8", errors="replace")
                match = frontmatter_re.match(text)
                if not match:
                    continue
                try:
                    frontmatter = yaml.safe_load(match.group(1)) or {}
                except Exception:
                    frontmatter = {}
                if str(frontmatter.get("summarize_status", "") or "").strip() == "pending":
                    pending += 1
            except Exception:
                continue

        pending_fraction = pending / paper_count if paper_count > 0 else 0.0
        score = min(
            100,
            int(
                min(paper_count / 10.0, 1.0) * 40
                + (1.0 - pending_fraction) * 40
                + (20 if paper_count > 0 else 0)
            ),
        )
        results.append(
            ClusterCoverage(
                slug=cluster.slug,
                name=cluster.name,
                paper_count=paper_count,
                pending_summary=pending,
                coverage_score=score,
                latest_mtime=latest_mtime,
            )
        )

    return sorted(results, key=lambda row: row.coverage_score)
