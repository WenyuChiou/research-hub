"""Upload a cluster's bundle to NotebookLM and cache the resulting state."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.notebooklm.browser import (
    default_session_dir,
    default_state_file,
    launch_nlm_context,
)
from research_hub.notebooklm.client import (
    BriefingArtifact,
    NotebookLMClient,
    NotebookLMError,
    UploadResult,
)
from research_hub.notebooklm.selectors import BETWEEN_UPLOADS_MS, NOTEBOOKLM_HOME
from research_hub.notebooklm.session import open_cdp_session as open_cdp_session

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
        return False, "Could not reach NotebookLM home: {0}".format(exc)

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
        "{0}). Run `research-hub notebooklm login --cdp` to re-auth."
    ).format(url)


@dataclass
class UploadReport:
    cluster_slug: str
    notebook_url: str = ""
    notebook_id: str = ""
    notebook_name: str = ""
    notebook_was_reused: bool = False
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
        bundles_root.glob("{0}-*".format(cluster_slug)),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _open_debug_log(research_hub_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = research_hub_dir / ("nlm-debug-{0}.jsonl".format(timestamp))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _log_jsonl(path: Path, event: dict) -> None:
    payload = dict(event)
    payload["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _upload_with_retry(
    client,
    entry: dict,
    log_path: Path,
    *,
    max_attempts: int = 3,
):
    """Try an upload up to ``max_attempts`` times with exponential backoff."""
    action = entry.get("action", "?")
    key = entry.get("pdf_path") or entry.get("url") or entry.get("doi") or ""
    last_result = None
    for attempt in range(1, max_attempts + 1):
        _log_jsonl(
            log_path,
            {"kind": "upload_attempt", "attempt": attempt, "action": action, "key": key},
        )
        if action == "pdf":
            result = client.upload_pdf(Path(entry["pdf_path"]))
        elif action == "url":
            result = client.upload_url(entry["url"])
        else:
            _log_jsonl(log_path, {"kind": "upload_skip", "action": action, "key": key})
            return None
        last_result = result
        if result.success:
            _log_jsonl(
                log_path,
                {"kind": "upload_ok", "attempt": attempt, "action": action, "key": key},
            )
            return result
        _log_jsonl(
            log_path,
            {
                "kind": "upload_fail",
                "attempt": attempt,
                "action": action,
                "key": key,
                "error": result.error,
            },
        )
        if attempt < max_attempts:
            backoff_sec = 3 ** (attempt - 1)
            time.sleep(backoff_sec)
    return last_result


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
            "No bundle found for cluster '{0}'. Run `research-hub notebooklm bundle "
            "--cluster {0}` first.".format(cluster.slug)
        )

    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        log_path,
        {
            "kind": "upload_run_start",
            "cluster_slug": cluster.slug,
            "manifest_entries": len(manifest.get("entries", [])),
            "headless": headless,
            "dry_run": dry_run,
        },
    )

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
        _log_jsonl(
            log_path,
            {
                "kind": "upload_run_complete",
                "success_count": report.success_count,
                "fail_count": report.fail_count,
                "retry_count": 0,
                "dry_run": True,
            },
        )
        return report

    retry_count = 0
    session_dir = default_session_dir(cfg.research_hub_dir)
    with open_cdp_session(session_dir, headless=headless) as (_, page):
        client = NotebookLMClient(page)
        ok, detail = _check_session_health(page)
        if not ok:
            raise NotebookLMError(detail, selector="session-health", page_url=page.url)
        handle = (
            client.open_or_create_notebook(notebook_name)
            if create_if_missing
            else client.open_notebook_by_name(notebook_name)
        )
        prior_url = (cluster.notebooklm_notebook_url or "").strip()
        if prior_url and prior_url == handle.url:
            report.notebook_was_reused = True

        report.notebook_url = handle.url
        report.notebook_id = handle.notebook_id
        report.notebook_name = handle.name
        _log_jsonl(
            log_path,
            {
                "kind": "upload_notebook_opened",
                "notebook_url": handle.url,
                "notebook_id": handle.notebook_id,
                "notebook_name": handle.name,
            },
        )

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
                _log_jsonl(log_path, {"kind": "upload_cached_skip", "key": key})
                continue

            result = _upload_with_retry(client, entry, log_path)
            if result is None:
                continue
            report.uploaded.append(result)
            retry_count += max(0, _count_attempts_for_key(log_path, str(key)) - 1)
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

    _log_jsonl(
        log_path,
        {
            "kind": "upload_run_complete",
            "success_count": report.success_count,
            "fail_count": report.fail_count,
            "retry_count": retry_count,
        },
    )
    return report


def _count_attempts_for_key(log_path: Path, key: str) -> int:
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 1
    count = 0
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if payload.get("kind") == "upload_attempt" and str(payload.get("key")) == str(key):
            count += 1
    return max(count, 1)


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
    """Open a cluster's notebook, extract the latest briefing text, save it."""
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        log_path,
        {"kind": "download_start", "cluster_slug": cluster.slug, "headless": headless},
    )
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    notebook_name = cluster.notebooklm_notebook or cluster.name
    safe_slug = Path(cluster.slug).name

    session_dir = default_session_dir(cfg.research_hub_dir)
    with open_cdp_session(session_dir, headless=headless) as (_, page):
        client = NotebookLMClient(page)
        ok, detail = _check_session_health(page)
        if not ok:
            raise NotebookLMError(detail, selector="session-health", page_url=page.url)
        handle = client.open_notebook_by_name(notebook_name)
        _log_jsonl(log_path, {"kind": "download_navigate", "notebook_url": handle.url})
        artifact: BriefingArtifact = client.download_briefing(handle)
    if artifact.source_count == 0:
        artifact.source_count = int(cluster_cache.get("uploaded_doi_count", 0))

    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_path = artifacts_dir / ("brief-{0}.txt".format(timestamp))
    header = (
        "# {0}\n\n"
        "Source: {1}\n"
        "Downloaded: {2}\n"
        "Sources: {3}\n"
    ).format(
        artifact.notebook_name,
        artifact.notebook_url,
        timestamp,
        artifact.source_count,
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
    _log_jsonl(log_path, {"kind": "download_ok", "artifact_path": str(out_path)})

    return DownloadReport(
        cluster_slug=cluster.slug,
        notebook_name=artifact.notebook_name,
        artifact_path=out_path,
        char_count=len(artifact.text),
        titles=artifact.titles,
    )


def read_latest_briefing(cluster, cfg) -> str:
    """Return the most recently downloaded briefing text for a cluster."""
    cluster_slug = cluster if isinstance(cluster, str) else cluster.slug
    safe_slug = Path(cluster_slug).name
    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    if not artifacts_dir.exists():
        raise FileNotFoundError(
            "No artifacts directory for cluster '{0}'. Run `research-hub notebooklm "
            "download --cluster {0}` first.".format(cluster_slug)
        )
    candidates = sorted(
        artifacts_dir.glob("brief-*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            "No brief-*.txt files in {0}. Run `research-hub notebooklm download "
            "--cluster {1}` first.".format(artifacts_dir, cluster_slug)
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
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        log_path,
        {"kind": "generate_start", "cluster_slug": cluster.slug, "kind_name": kind, "headless": headless},
    )
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    notebook_name = cluster.notebooklm_notebook or cluster.name

    session_dir = default_session_dir(cfg.research_hub_dir)
    with open_cdp_session(session_dir, headless=headless) as (_, page):
        client = NotebookLMClient(page)
        ok, detail = _check_session_health(page)
        if not ok:
            raise NotebookLMError(detail, selector="session-health", page_url=page.url)
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
            raise ValueError("Unknown generation kind: {0}".format(kind))

        cluster_cache["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _save_nlm_cache(cache_path, cache)
        _log_jsonl(log_path, {"kind": "generate_ok", "kind_name": kind, "url": url})
        return url
