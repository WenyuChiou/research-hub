"""Upload a cluster's bundle to NotebookLM and cache the resulting state."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.notebooklm.client import (
    BriefingArtifact,
    NotebookLMClient,
    NotebookLMError,
    UploadResult,
)
from research_hub.notebooklm.selectors import BETWEEN_UPLOADS_MS, NOTEBOOKLM_HOME
from research_hub.notebooklm.session import (
    PlaywrightSession,
    SessionConfig,
    open_cdp_session,
)

BRIEFING_OFF_TOPIC_SECTION = """### Off-topic papers

List any papers in the provided sources that are NOT about the cluster topic.
For each, give the paper's title and a one-sentence explanation of why it
doesn't fit. If every paper is on-topic, write "none" on a single line.
"""


def _check_session_health(page) -> tuple[bool, str]:
    """Return (ok, message). Probe NotebookLM home; detect expired sessions."""
    try:
        page.goto(NOTEBOOKLM_HOME)
        page.wait_for_load_state("networkidle")
    except Exception as exc:
        return False, f"Could not reach NotebookLM home: {exc}"

    url = page.url or ""
    lowered = url.lower()
    if (
        "notebooklm.google.com" in lowered
        and "accounts.google.com" not in lowered
        and "signin" not in lowered
        and "oauth" not in lowered
    ):
        return True, url
    return False, (
        "Saved Google session appears to be expired (landed on "
        f"{url}). Run `research-hub notebooklm login --cdp` to re-auth."
    )


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
    headless: bool = False,
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
    with open_cdp_session(session_dir, headless=headless) as (_, page):
        client = NotebookLMClient(page)
        ok, detail = _check_session_health(page)
        if not ok:
            raise NotebookLMError(
                detail,
                selector="session-health",
                page_url=page.url,
            )
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


@dataclass
class DownloadReport:
    cluster_slug: str
    notebook_name: str
    artifact_path: Path
    char_count: int
    titles: list[str] = field(default_factory=list)


def download_briefing_for_cluster(
    cluster,
    cfg,
    *,
    headless: bool = False,
) -> DownloadReport:
    """Open a cluster's notebook, extract the latest briefing text, save it.

    Writes to ``<vault>/.research_hub/artifacts/<cluster_slug>/brief-<UTC>.txt``
    and updates the cluster's ``nlm_cache.json`` entry with the latest
    artifact path so future calls (and the dashboard) can find it.
    """
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    notebook_name = cluster.notebooklm_notebook or cluster.name
    safe_slug = Path(cluster.slug).name

    session_dir = cfg.research_hub_dir / "nlm_sessions" / "default"
    with open_cdp_session(session_dir, headless=headless) as (_, page):
        client = NotebookLMClient(page)
        ok, detail = _check_session_health(page)
        if not ok:
            raise NotebookLMError(
                detail,
                selector="session-health",
                page_url=page.url,
            )
        handle = client.open_notebook_by_name(notebook_name)
        artifact: BriefingArtifact = client.download_briefing(handle)

    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_path = artifacts_dir / f"brief-{timestamp}.txt"
    header = (
        f"# {artifact.notebook_name}\n\n"
        f"Source: {artifact.notebook_url}\n"
        f"Downloaded: {timestamp}\n"
        f"Sources: {artifact.source_count}\n"
    )
    if artifact.titles:
        header += "Saved briefings: " + "; ".join(artifact.titles) + "\n"
    out_path.write_text(header + "\n" + artifact.text + "\n", encoding="utf-8")

    cluster_cache.setdefault("artifacts", {})
    cluster_cache["artifacts"]["brief"] = {
        "path": str(out_path),
        "downloaded_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "char_count": len(artifact.text),
        "titles": artifact.titles,
    }
    _save_nlm_cache(cache_path, cache)

    return DownloadReport(
        cluster_slug=cluster.slug,
        notebook_name=artifact.notebook_name,
        artifact_path=out_path,
        char_count=len(artifact.text),
        titles=artifact.titles,
    )


def read_latest_briefing(cluster, cfg) -> str:
    """Return the most recently downloaded briefing text for a cluster.

    Reads from ``<vault>/.research_hub/artifacts/<cluster_slug>/`` and
    picks the newest ``brief-*.txt``. Raises FileNotFoundError if no
    briefing has been downloaded yet.
    """
    cluster_slug = cluster if isinstance(cluster, str) else cluster.slug
    safe_slug = Path(cluster_slug).name
    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    if not artifacts_dir.exists():
        raise FileNotFoundError(
            f"No artifacts directory for cluster '{cluster_slug}'. "
            f"Run `research-hub notebooklm download --cluster {cluster_slug}` first."
        )
    candidates = sorted(
        artifacts_dir.glob("brief-*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No brief-*.txt files in {artifacts_dir}. "
            f"Run `research-hub notebooklm download --cluster {cluster_slug}` first."
        )
    return candidates[0].read_text(encoding="utf-8")


def generate_artifact(
    cluster,
    cfg,
    *,
    kind: str,
    headless: bool = False,
) -> str:
    """Trigger a NotebookLM generation and return the artifact URL."""
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    notebook_name = cluster.notebooklm_notebook or cluster.name

    session_dir = cfg.research_hub_dir / "nlm_sessions" / "default"
    with open_cdp_session(session_dir, headless=headless) as (_, page):
        client = NotebookLMClient(page)
        ok, detail = _check_session_health(page)
        if not ok:
            raise NotebookLMError(
                detail,
                selector="session-health",
                page_url=page.url,
            )
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
