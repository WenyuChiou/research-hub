from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.dedup import DedupIndex
from research_hub.doctor import run_doctor
from research_hub.vault.sync import list_cluster_notes
from research_hub.utils.doi import normalize_doi

from research_hub.dashboard.briefing import load_briefing_preview
from research_hub.dashboard.citation import build_bibtex_for_cluster, build_bibtex_for_paper
from research_hub.dashboard.drift import detect_drift
from research_hub.dashboard.types import (
    ClusterCard,
    DashboardData,
    HealthBadge,
    PaperRow,
    Quote,
)
from research_hub.paper import archive_dir, list_papers_by_label
from research_hub.topic import list_subtopics, overview_path

logger = logging.getLogger(__name__)


def _detect_persona(cfg, zot) -> str:
    """Persona is set at init; zot=None alone does not imply analyst.

    The render path can call us without a live Zotero client (the
    bibtex column gracefully degrades to the frontmatter fallback).
    Only an explicit env var or config flag flips us to analyst.
    """
    env_no_zotero = os.environ.get("RESEARCH_HUB_NO_ZOTERO", "").lower() in {"1", "true", "yes"}
    if env_no_zotero or getattr(cfg, "no_zotero", False):
        return "analyst"
    return "researcher"


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


def _field(frontmatter: str, key: str, default: str = "") -> str:
    match = re.search(rf'^{re.escape(key)}:\s*[\'"]?([^\'"\n]*)[\'"]?', frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else default


def _list_field(frontmatter: str, key: str) -> list[str]:
    match = re.search(rf"^{re.escape(key)}:\s*\[(.*?)\]", frontmatter, re.MULTILINE | re.DOTALL)
    if match:
        return [part.strip().strip("\"'") for part in match.group(1).split(",") if part.strip()]
    value = _field(frontmatter, key)
    return [part.strip() for part in value.split(";") if part.strip()] if value else []


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _in_nlm(cluster_cache: dict, doi: str, obsidian_path: str) -> bool:
    uploaded_sources = cluster_cache.get("uploaded_sources", [])
    if not isinstance(uploaded_sources, list):
        return False
    uploaded = {str(item) for item in uploaded_sources}
    normalized_uploaded = {normalize_doi(str(item)) for item in uploaded_sources if item}
    note_path = Path(obsidian_path)
    resolved = ""
    try:
        resolved = str(note_path.resolve())
    except OSError:
        resolved = obsidian_path
    return bool(
        normalize_doi(doi) and normalize_doi(doi) in normalized_uploaded
        or obsidian_path in uploaded
        or resolved in uploaded
    )


def _worst_status(statuses: list[str]) -> str:
    order = {"OK": 0, "WARN": 1, "FAIL": 2}
    return max(statuses or ["OK"], key=lambda item: order.get(item, 0))


def _doctor_subsystem(name: str) -> str:
    if name.startswith("zotero"):
        return "zotero"
    if name.startswith("chrome") or name.startswith("nlm_"):
        return "notebooklm"
    return "obsidian"


def collect_dashboard_data(cfg, zot=None) -> DashboardData:
    """Walk the vault and build the full DashboardData snapshot."""
    persona = _detect_persona(cfg, zot)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    registry = ClusterRegistry(cfg.clusters_file)
    dedup = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    nlm_cache = _load_json(cfg.research_hub_dir / "nlm_cache.json")
    clusters: list[ClusterCard] = []
    briefings = []
    quotes: list[Quote] = []

    for cluster in registry.list():
        try:
            cluster_cache = nlm_cache.get(cluster.slug, {})
            if not isinstance(cluster_cache, dict):
                cluster_cache = {}
            papers: list[PaperRow] = []
            for note_path in list_cluster_notes(cluster.slug, cfg.raw):
                try:
                    frontmatter = _read_frontmatter(note_path)
                    status = _field(frontmatter, "status", "unread") or "unread"
                    zotero_key = _field(frontmatter, "zotero-key")
                    paper = PaperRow(
                        slug=note_path.stem,
                        title=_field(frontmatter, "title", note_path.stem),
                        authors=_field(frontmatter, "authors"),
                        year=_field(frontmatter, "year"),
                        abstract=_field(frontmatter, "abstract"),
                        doi=_field(frontmatter, "doi"),
                        tags=_list_field(frontmatter, "tags"),
                        status=status if status in {"unread", "reading", "deep-read", "cited"} else "unread",
                        ingested_at=_field(frontmatter, "ingested_at"),
                        obsidian_path=str(note_path),
                        zotero_key=zotero_key,
                        in_zotero=bool(zotero_key) and persona == "researcher",
                        in_obsidian=True,
                        in_nlm=_in_nlm(cluster_cache, _field(frontmatter, "doi"), str(note_path)),
                    )
                    paper.bibtex = (
                        ""
                        if persona == "analyst"
                        else build_bibtex_for_paper(paper, zot=zot if persona == "researcher" else None)
                    )
                    papers.append(paper)
                except Exception:
                    logger.exception("Failed to build dashboard paper row for %s", note_path)
            papers.sort(key=lambda paper: (paper.ingested_at or "", paper.title.lower()), reverse=True)
            briefing = load_briefing_preview(
                cluster.slug,
                cluster.name,
                cluster_cache,
                cfg.research_hub_dir / "artifacts" / cluster.slug,
            )
            label_counts: dict[str, int] = {}
            for state in list_papers_by_label(cfg, cluster.slug):
                for label in state.labels:
                    label_counts[label] = label_counts.get(label, 0) + 1
            arch_dir = archive_dir(cfg, cluster.slug)
            archived_count = len(list(arch_dir.glob("*.md"))) if arch_dir.exists() else 0
            card = ClusterCard(
                slug=cluster.slug,
                name=cluster.name,
                papers=papers,
                zotero_count=sum(1 for paper in papers if paper.zotero_key and persona == "researcher"),
                obsidian_count=len(papers),
                nlm_count=int(cluster_cache.get("uploaded_doi_count", 0) or 0),
                last_activity=max((paper.ingested_at for paper in papers), default=""),
                notebooklm_notebook=cluster.notebooklm_notebook or str(cluster_cache.get("notebook_name", "")),
                notebooklm_notebook_url=cluster.notebooklm_notebook_url
                or str(cluster_cache.get("notebook_url", "")),
                zotero_collection_key=cluster.zotero_collection_key or "",
                has_overview=overview_path(cfg, cluster.slug).exists(),
                subtopic_count=len(list_subtopics(cfg, cluster.slug)),
                briefing=briefing,
                label_counts=label_counts,
                archived_count=archived_count,
            )
            card.cluster_bibtex = "" if persona == "analyst" else build_bibtex_for_cluster(card)
            clusters.append(card)
            if briefing is not None:
                briefings.append(briefing)
        except Exception:
            logger.exception("Failed to build dashboard cluster card for %s", cluster.slug)

    health_badges: list[HealthBadge] = []
    try:
        grouped: dict[str, list[dict]] = {"zotero": [], "obsidian": [], "notebooklm": []}
        for result in run_doctor():
            grouped[_doctor_subsystem(result.name)].append(asdict(result))
        for subsystem in ("zotero", "obsidian", "notebooklm"):
            items = grouped[subsystem]
            summaries = [item["message"] for item in items[:2] if item.get("message")]
            health_badges.append(
                HealthBadge(
                    subsystem=subsystem,
                    status=_worst_status([item.get("status", "OK") for item in items]),
                    summary="; ".join(summaries),
                    items=items,
                )
            )
    except Exception:
        logger.exception("Failed to build dashboard health badges")

    try:
        from research_hub.writing import load_all_quotes

        quotes = [Quote(**quote.__dict__) for quote in load_all_quotes(cfg)]
    except Exception:
        logger.exception("Failed to load quotes")
        quotes = []

    drift_alerts = detect_drift(cfg, dedup)
    total_papers = sum(len(cluster.papers) for cluster in clusters)
    papers_this_week = sum(cluster.new_this_week for cluster in clusters)
    clusters.sort(key=lambda cluster: (-len(cluster.papers), cluster.name.lower()))

    return DashboardData(
        vault_root=str(cfg.root),
        generated_at=generated_at,
        persona=persona,
        total_papers=total_papers,
        total_clusters=len(clusters),
        papers_this_week=papers_this_week,
        clusters=clusters,
        briefings=briefings,
        quotes=quotes,
        health_badges=health_badges,
        drift_alerts=drift_alerts,
    )
