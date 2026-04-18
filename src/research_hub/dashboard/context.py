"""Vault state collector for the dashboard.

`DashboardContext` is the single object every section receives. It is
populated once per `generate_dashboard()` call by walking the vault,
the dedup index, the manifest, and the NotebookLM cache. Sections
read from it and never touch the filesystem themselves — that keeps
section rendering pure and unit-testable with hand-crafted contexts.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupIndex
from research_hub.manifest import Manifest, ManifestEntry


@dataclass
class PaperRow:
    """One paper row for the Reading Queue section."""

    slug: str
    title: str
    cluster_slug: str
    cluster_name: str
    year: str
    status: str
    doi: str
    ingested_at: str
    obsidian_path: str


@dataclass
class ClusterRow:
    """One cluster row for the Clusters section."""

    slug: str
    name: str
    paper_count: int
    unread_count: int
    deep_read_count: int
    cited_count: int
    reading_count: int
    zotero_collection_key: str
    notebooklm_notebook: str
    notebooklm_notebook_url: str
    notebooklm_brief_path: str
    latest_ingested_at: str


@dataclass
class NLMArtifact:
    """One NotebookLM artifact card."""

    cluster_slug: str
    cluster_name: str
    notebook_url: str
    brief_path: str
    downloaded_at: str
    char_count: int
    titles: list[str] = field(default_factory=list)


@dataclass
class ActivityEvent:
    """One row in the Recent Activity feed."""

    timestamp: str
    cluster: str
    action: str
    title: str
    doi: str
    error: str = ""


@dataclass
class DashboardContext:
    """Snapshot of vault state, ready for section rendering."""

    vault_root: str
    generated_at: str
    persona: str  # "researcher" | "analyst"
    total_papers: int
    total_clusters: int
    total_unread: int
    papers_this_week: int
    dedup_doi_count: int
    dedup_title_count: int
    nlm_cached_clusters: int
    clusters: list[ClusterRow] = field(default_factory=list)
    papers: list[PaperRow] = field(default_factory=list)
    activity: list[ActivityEvent] = field(default_factory=list)
    nlm_artifacts: list[NLMArtifact] = field(default_factory=list)

    @property
    def show_nlm_section(self) -> bool:
        """Hide NotebookLM section in analyst persona or when there are no artifacts."""
        return self.persona != "analyst" and bool(self.nlm_artifacts)


def _read_frontmatter(md_path: Path) -> str:
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    return text[3:end]


def _yaml_field(frontmatter: str, key: str, default: str = "") -> str:
    pattern = rf'^{re.escape(key)}:\s*"?([^"\n]*)"?'
    match = re.search(pattern, frontmatter, re.MULTILINE)
    if not match:
        return default
    return match.group(1).strip()


def _detect_persona(cfg) -> str:
    valid = {"researcher", "analyst", "humanities", "internal"}
    explicit = str(getattr(cfg, "persona", "") or "").strip().lower()
    if explicit in valid:
        return explicit
    env_p = os.environ.get("RESEARCH_HUB_PERSONA", "").strip().lower()
    if env_p in valid:
        return env_p
    env_no_zotero = os.environ.get("RESEARCH_HUB_NO_ZOTERO", "").lower() in {"1", "true", "yes"}
    if env_no_zotero or getattr(cfg, "no_zotero", False):
        return "analyst"
    return "researcher"


def _load_nlm_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def collect_dashboard_context(cfg) -> DashboardContext:
    """Walk the vault and produce a fully populated DashboardContext."""
    registry = ClusterRegistry(cfg.clusters_file)
    dedup = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    nlm_cache = _load_nlm_cache(cfg.research_hub_dir / "nlm_cache.json")
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    cluster_rows: dict[str, ClusterRow] = {}
    for slug, cluster in registry.clusters.items():
        cached = nlm_cache.get(slug, {}) if isinstance(nlm_cache.get(slug, {}), dict) else {}
        artifacts = cached.get("artifacts", {}) if isinstance(cached.get("artifacts", {}), dict) else {}
        brief_meta = artifacts.get("brief", {}) if isinstance(artifacts.get("brief", {}), dict) else {}
        cluster_rows[slug] = ClusterRow(
            slug=slug,
            name=cluster.name,
            paper_count=0,
            unread_count=0,
            deep_read_count=0,
            cited_count=0,
            reading_count=0,
            zotero_collection_key=cluster.zotero_collection_key or "",
            notebooklm_notebook=cluster.notebooklm_notebook or "",
            notebooklm_notebook_url=cluster.notebooklm_notebook_url
            or cached.get("notebook_url", ""),
            notebooklm_brief_path=brief_meta.get("path", ""),
            latest_ingested_at="",
        )

    papers: list[PaperRow] = []
    papers_this_week = 0
    if cfg.raw.exists():
        for subdir in cfg.raw.iterdir():
            if not subdir.is_dir():
                continue
            row = cluster_rows.get(subdir.name)
            if row is None:
                continue
            for md_path in subdir.glob("*.md"):
                frontmatter = _read_frontmatter(md_path)
                if not frontmatter:
                    continue
                row.paper_count += 1
                status = _yaml_field(frontmatter, "status", "unread") or "unread"
                if status == "unread":
                    row.unread_count += 1
                elif status == "deep-read":
                    row.deep_read_count += 1
                elif status == "cited":
                    row.cited_count += 1
                elif status == "reading":
                    row.reading_count += 1
                ingested_at = _yaml_field(frontmatter, "ingested_at")
                if ingested_at and ingested_at > row.latest_ingested_at:
                    row.latest_ingested_at = ingested_at
                if ingested_at:
                    try:
                        ts = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if ts >= week_ago:
                            papers_this_week += 1
                    except ValueError:
                        pass
                papers.append(
                    PaperRow(
                        slug=md_path.stem,
                        title=_yaml_field(frontmatter, "title", md_path.stem),
                        cluster_slug=row.slug,
                        cluster_name=row.name,
                        year=_yaml_field(frontmatter, "year"),
                        status=status,
                        doi=_yaml_field(frontmatter, "doi"),
                        ingested_at=ingested_at,
                        obsidian_path=str(md_path),
                    )
                )

    activity: list[ActivityEvent] = []
    try:
        entries = manifest.read_all()
    except Exception:
        entries = []
    for entry in entries[-20:][::-1]:
        activity.append(
            ActivityEvent(
                timestamp=getattr(entry, "timestamp", ""),
                cluster=getattr(entry, "cluster", ""),
                action=getattr(entry, "action", ""),
                title=getattr(entry, "title", "") or getattr(entry, "doi", ""),
                doi=getattr(entry, "doi", ""),
                error=getattr(entry, "error", ""),
            )
        )

    nlm_artifacts: list[NLMArtifact] = []
    nlm_cached_clusters = 0
    for slug, row in cluster_rows.items():
        cached = nlm_cache.get(slug, {}) if isinstance(nlm_cache.get(slug, {}), dict) else {}
        if cached.get("notebook_url"):
            nlm_cached_clusters += 1
        artifacts = cached.get("artifacts", {}) if isinstance(cached.get("artifacts", {}), dict) else {}
        brief = artifacts.get("brief", {}) if isinstance(artifacts.get("brief", {}), dict) else {}
        if brief.get("path"):
            nlm_artifacts.append(
                NLMArtifact(
                    cluster_slug=slug,
                    cluster_name=row.name,
                    notebook_url=row.notebooklm_notebook_url,
                    brief_path=brief.get("path", ""),
                    downloaded_at=brief.get("downloaded_at", ""),
                    char_count=int(brief.get("char_count", 0) or 0),
                    titles=list(brief.get("titles", []) or []),
                )
            )

    total_papers = sum(c.paper_count for c in cluster_rows.values())
    total_unread = sum(c.unread_count for c in cluster_rows.values())

    return DashboardContext(
        vault_root=str(cfg.root),
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        persona=_detect_persona(cfg),
        total_papers=total_papers,
        total_clusters=len(cluster_rows),
        total_unread=total_unread,
        papers_this_week=papers_this_week,
        dedup_doi_count=len(dedup.doi_to_hits),
        dedup_title_count=len(dedup.title_to_hits),
        nlm_cached_clusters=nlm_cached_clusters,
        clusters=sorted(
            cluster_rows.values(),
            key=lambda c: (-c.paper_count, c.name.lower()),
        ),
        papers=sorted(
            papers,
            key=lambda p: (p.ingested_at or "", p.title.lower()),
            reverse=True,
        ),
        activity=activity,
        nlm_artifacts=nlm_artifacts,
    )
