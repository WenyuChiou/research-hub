"""Upload a cluster's bundle to NotebookLM and cache the resulting state."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.notebooklm.client import NotebookLMClient, UploadResult
from research_hub.notebooklm.selectors import BETWEEN_UPLOADS_MS
from research_hub.notebooklm.session import PlaywrightSession, SessionConfig


@dataclass
class UploadReport:
    cluster_slug: str
    notebook_url: str = ""
    notebook_id: str = ""
    notebook_name: str = ""
    uploaded: list[UploadResult] = field(default_factory=list)
    skipped_already_uploaded: int = 0
    errors: list[dict] = field(default_factory=list)
    dry_run: bool = False

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.uploaded if result.success)

    @property
    def fail_count(self) -> int:
        return sum(1 for result in self.uploaded if not result.success)


def _load_nlm_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_nlm_cache(cache_path: Path, cache: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_latest_bundle(bundles_root: Path, cluster_slug: str) -> Path | None:
    """Pick the most recent bundle folder for a cluster."""
    if not bundles_root.exists():
        return None
    candidates = sorted(
        bundles_root.glob(f"{cluster_slug}-*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def upload_cluster(
    cluster,
    cfg,
    *,
    dry_run: bool = False,
    create_if_missing: bool = True,
    headless: bool = True,
    rate_limit_cap: int = 50,
) -> UploadReport:
    """Upload a cluster bundle to NotebookLM, resuming from `nlm_cache.json`."""
    from research_hub.clusters import ClusterRegistry

    report = UploadReport(cluster_slug=cluster.slug, dry_run=dry_run)
    bundle_dir = _find_latest_bundle(cfg.research_hub_dir / "bundles", cluster.slug)
    if bundle_dir is None:
        raise FileNotFoundError(
            f"No bundle found for cluster '{cluster.slug}'. "
            f"Run `research-hub notebooklm bundle --cluster {cluster.slug}` first."
        )

    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    uploaded_sources: set[str] = set(cluster_cache.get("uploaded_sources", []))
    notebook_name = cluster.notebooklm_notebook or cluster.name

    if dry_run:
        planned = 0
        for entry in manifest.get("entries", []):
            if entry.get("action") == "skip":
                continue
            key = entry.get("pdf_path") or entry.get("url") or entry.get("doi")
            if key in uploaded_sources:
                report.skipped_already_uploaded += 1
                continue
            report.uploaded.append(
                UploadResult(
                    source_kind=entry.get("action", "?"),
                    path_or_url=str(key),
                    success=True,
                )
            )
            planned += 1
            if planned >= rate_limit_cap:
                break
        report.notebook_name = notebook_name
        return report

    session_dir = cfg.research_hub_dir / "nlm_sessions" / "default"
    session = PlaywrightSession(SessionConfig(user_data_dir=session_dir, headless=headless))
    with session.open() as (_, page):
        client = NotebookLMClient(page)
        handle = (
            client.open_or_create_notebook(notebook_name)
            if create_if_missing
            else client.open_notebook_by_name(notebook_name)
        )

        report.notebook_url = handle.url
        report.notebook_id = handle.notebook_id
        report.notebook_name = handle.name

        uploads = 0
        for entry in manifest.get("entries", []):
            action = entry.get("action", "skip")
            if action == "skip":
                continue
            if uploads >= rate_limit_cap:
                break

            key = entry.get("pdf_path") or entry.get("url") or entry.get("doi")
            if key in uploaded_sources:
                report.skipped_already_uploaded += 1
                continue

            if action == "pdf":
                result = client.upload_pdf(Path(entry["pdf_path"]))
            elif action == "url":
                result = client.upload_url(entry["url"])
            else:
                continue

            report.uploaded.append(result)
            if result.success:
                uploaded_sources.add(key)
                uploads += 1
            else:
                report.errors.append({"source": key, "error": result.error})
            time.sleep(BETWEEN_UPLOADS_MS / 1000)

        cluster_cache["notebook_url"] = handle.url
        cluster_cache["notebook_id"] = handle.notebook_id
        cluster_cache["notebook_name"] = handle.name
        cluster_cache["uploaded_sources"] = sorted(uploaded_sources)
        cluster_cache["uploaded_doi_count"] = len(uploaded_sources)
        cluster_cache["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _save_nlm_cache(cache_path, cache)

        registry = ClusterRegistry(cfg.clusters_file)
        registry.bind(
            slug=cluster.slug,
            notebooklm_notebook_url=handle.url,
            notebooklm_notebook_id=handle.notebook_id,
        )

    return report


def generate_artifact(
    cluster,
    cfg,
    *,
    kind: str,
    headless: bool = True,
) -> str:
    """Trigger a NotebookLM generation and return the artifact URL."""
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    notebook_name = cluster.notebooklm_notebook or cluster.name

    session_dir = cfg.research_hub_dir / "nlm_sessions" / "default"
    session = PlaywrightSession(SessionConfig(user_data_dir=session_dir, headless=headless))
    with session.open() as (_, page):
        client = NotebookLMClient(page)
        client.open_or_create_notebook(notebook_name)

        if kind == "brief":
            url = client.trigger_briefing()
            cluster_cache["briefing_url"] = url
        elif kind == "audio":
            url = client.trigger_audio_overview()
            cluster_cache["audio_url"] = url
        elif kind == "mind_map":
            url = client.trigger_mind_map()
            cluster_cache["mind_map_url"] = url
        elif kind == "video":
            url = client.trigger_video_overview()
            cluster_cache["video_url"] = url
        else:
            raise ValueError(f"Unknown generation kind: {kind}")

        cluster_cache["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _save_nlm_cache(cache_path, cache)
        return url
