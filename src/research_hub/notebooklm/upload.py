"""Upload a cluster's bundle to NotebookLM and cache the resulting state."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from research_hub.notebooklm.auth import default_state_file
from research_hub.notebooklm.client import (
    BriefingArtifact,
    NotebookHandle,
    NotebookLMClient,
    NotebookLMError,
    UploadResult,
    _parse_notebook_id,
)

BETWEEN_UPLOADS_SEC = 1.0

# Legacy test monkeypatch anchors. The RPC implementation no longer uses them.
open_cdp_session = None

BRIEFING_OFF_TOPIC_SECTION = """### Off-topic papers

List any papers in the provided sources that are NOT about the cluster topic.
For each, give the paper's title and a one-sentence explanation of why it
doesn't fit. If every paper is on-topic, write "none" on a single line.
"""


def _check_session_health(_page) -> tuple[bool, str]:
    return True, "ok"


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


@dataclass
class DownloadReport:
    cluster_slug: str
    notebook_name: str
    artifact_path: Path
    char_count: int
    titles: list[str] = field(default_factory=list)


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


def _open_debug_log(research_hub_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = research_hub_dir / f"nlm-debug-{timestamp}.jsonl"
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


def _attempt_upload(
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
        _log_jsonl(log_path, {"kind": "upload_attempt", "attempt": attempt, "action": action, "key": key})
        if action == "pdf":
            result = client.upload_pdf(Path(entry["pdf_path"]))
        elif action == "url":
            result = client.upload_url(entry["url"])
        else:
            _log_jsonl(log_path, {"kind": "upload_skip", "action": action, "key": key})
            return None
        last_result = result
        if result.success:
            _log_jsonl(log_path, {"kind": "upload_ok", "attempt": attempt, "action": action, "key": key})
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
            time.sleep(3 ** (attempt - 1))
    return last_result


_upload_with_retry = _attempt_upload


def upload_cluster(
    cluster,
    cfg,
    *,
    dry_run: bool = False,
    create_if_missing: bool = True,
    headless: bool = False,
    rate_limit_cap: int = 50,
) -> UploadReport:
    """Upload a cluster bundle to NotebookLM, resuming from ``nlm_cache.json``."""
    from research_hub.clusters import ClusterRegistry

    report = UploadReport(cluster_slug=cluster.slug, dry_run=dry_run)
    bundle_dir = _find_latest_bundle(cfg.research_hub_dir / "bundles", cluster.slug)
    if bundle_dir is None:
        raise FileNotFoundError(
            "No bundle found for cluster '{0}'. Run `research-hub notebooklm bundle "
            "--cluster {0}` first.".format(cluster.slug)
        )

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
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
    uploaded_sources: set[str] = {str(item) for item in cluster_cache.get("uploaded_sources", [])}
    notebook_name = cluster.notebooklm_notebook or cluster.name

    if dry_run:
        _plan_dry_run(report, manifest, uploaded_sources, notebook_name, rate_limit_cap)
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

    state_file = default_state_file(cfg.research_hub_dir)
    retry_count = 0
    client = _make_client(state_file, headless=headless)
    try:
        handle = (
            _find_or_create_notebook(client, notebook_name)
            if create_if_missing
            else client.open_notebook_by_name(notebook_name)
        )
        _set_active_notebook(client, handle.notebook_id)
        prior_url = (cluster.notebooklm_notebook_url or "").strip()
        report.notebook_was_reused = bool(prior_url and prior_url == handle.url)
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

            key = str(entry.get("pdf_path") or entry.get("url") or entry.get("doi") or "")
            if key in uploaded_sources:
                report.skipped_already_uploaded += 1
                _log_jsonl(log_path, {"kind": "upload_cached_skip", "key": key})
                continue

            result = _attempt_upload(client, entry, log_path)
            if result is None:
                continue
            report.uploaded.append(result)
            retry_count += max(0, _count_attempts_for_key(log_path, key) - 1)
            if result.success:
                uploaded_sources.add(key)
                uploads += 1
            else:
                report.errors.append({"source": key, "error": result.error})
            time.sleep(BETWEEN_UPLOADS_SEC)
    finally:
        getattr(client, "close", lambda: None)()

    cluster_cache["notebook_url"] = report.notebook_url
    cluster_cache["notebook_id"] = report.notebook_id
    cluster_cache["notebook_name"] = report.notebook_name
    cluster_cache["uploaded_sources"] = sorted(uploaded_sources)
    cluster_cache["uploaded_doi_count"] = len(uploaded_sources)
    cluster_cache["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_nlm_cache(cache_path, cache)

    ClusterRegistry(cfg.clusters_file).bind(
        slug=cluster.slug,
        notebooklm_notebook_url=report.notebook_url,
        notebooklm_notebook_id=report.notebook_id,
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


def _plan_dry_run(
    report: UploadReport,
    manifest: dict,
    uploaded_sources: set[str],
    notebook_name: str,
    rate_limit_cap: int,
) -> None:
    planned = 0
    for entry in manifest.get("entries", []):
        if entry.get("action") == "skip":
            continue
        key = str(entry.get("pdf_path") or entry.get("url") or entry.get("doi") or "")
        if key in uploaded_sources:
            report.skipped_already_uploaded += 1
            continue
        report.uploaded.append(
            UploadResult(
                source_kind=entry.get("action", "?"),
                path_or_url=key,
                success=True,
            )
        )
        planned += 1
        if planned >= rate_limit_cap:
            break
    report.notebook_name = notebook_name


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


def download_briefing_for_cluster(
    cluster,
    cfg,
    *,
    headless: bool = False,
) -> DownloadReport:
    """Download the latest briefing text and save it into the vault."""
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(log_path, {"kind": "download_start", "cluster_slug": cluster.slug, "headless": headless})
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})

    state_file = default_state_file(cfg.research_hub_dir)
    client = _make_client(state_file, headless=headless)
    try:
        handle = _resolve_notebook_handle(client, cluster, cluster_cache, create_if_missing=False)
        _log_jsonl(log_path, {"kind": "download_navigate", "notebook_url": handle.url})
        artifact: BriefingArtifact = client.download_briefing(handle)
    finally:
        getattr(client, "close", lambda: None)()

    if artifact.source_count == 0:
        artifact.source_count = int(cluster_cache.get("uploaded_doi_count", 0))

    safe_slug = Path(cluster.slug).name
    artifacts_dir = cfg.research_hub_dir / "artifacts" / safe_slug
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_path = artifacts_dir / f"brief-{timestamp}.txt"
    header = (
        "# {0}\n\n"
        "Source: {1}\n"
        "Downloaded: {2}\n"
        "Sources: {3}\n"
    ).format(artifact.notebook_name, artifact.notebook_url, timestamp, artifact.source_count)
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
        key=lambda path: path.stat().st_mtime,
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
    artifact_type: str | None = None,
    kind: str | None = None,
    headless: bool = False,
) -> str:
    """Trigger NotebookLM artifact generation and return an artifact id or URL."""
    kind_name = _normalize_artifact_kind(artifact_type or kind or "brief")
    log_path = _open_debug_log(cfg.research_hub_dir)
    _log_jsonl(
        log_path,
        {"kind": "generate_start", "cluster_slug": cluster.slug, "kind_name": kind_name, "headless": headless},
    )

    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    cache = _load_nlm_cache(cache_path)
    cluster_cache = cache.setdefault(cluster.slug, {})
    state_file = default_state_file(cfg.research_hub_dir)
    client = _make_client(state_file, headless=headless)
    try:
        handle = _resolve_notebook_handle(client, cluster, cluster_cache, create_if_missing=True)
        _set_active_notebook(client, handle.notebook_id)
        if kind_name == "brief":
            artifact_ref = _call_trigger(client.trigger_briefing, handle.notebook_id)
            cluster_cache["briefing_url"] = artifact_ref
        elif kind_name == "audio":
            artifact_ref = _call_trigger(client.trigger_audio_overview, handle.notebook_id)
            cluster_cache["audio_url"] = artifact_ref
        elif kind_name == "mind_map":
            artifact_ref = _call_trigger(client.trigger_mind_map, handle.notebook_id)
            cluster_cache["mind_map_url"] = artifact_ref
        elif kind_name == "video":
            artifact_ref = _call_trigger(client.trigger_video_overview, handle.notebook_id)
            cluster_cache["video_url"] = artifact_ref
        else:
            raise ValueError(f"Unknown generation kind: {kind_name}")
        if not artifact_ref:
            raise NotebookLMError("Generation button not found")
    finally:
        getattr(client, "close", lambda: None)()

    cluster_cache["notebook_url"] = handle.url
    cluster_cache["notebook_id"] = handle.notebook_id
    cluster_cache["notebook_name"] = handle.name
    cluster_cache["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_nlm_cache(cache_path, cache)
    _log_jsonl(log_path, {"kind": "generate_ok", "kind_name": kind_name, "artifact_ref": artifact_ref})
    return artifact_ref


def _normalize_artifact_kind(kind: str) -> str:
    if kind == "mind-map":
        return "mind_map"
    return kind


def _resolve_notebook_handle(
    client,
    cluster,
    cluster_cache: dict,
    *,
    create_if_missing: bool,
) -> NotebookHandle:
    notebook_name = cluster.notebooklm_notebook or cluster.name
    notebook_id = (
        getattr(cluster, "notebooklm_notebook_id", "")
        or cluster_cache.get("notebook_id", "")
        or _parse_notebook_id(getattr(cluster, "notebooklm_notebook_url", "") or cluster_cache.get("notebook_url", ""))
    )
    notebook_url = getattr(cluster, "notebooklm_notebook_url", "") or cluster_cache.get("notebook_url", "")
    if notebook_id:
        return NotebookHandle(name=notebook_name, url=notebook_url, notebook_id=notebook_id)
    if create_if_missing:
        return _find_or_create_notebook(client, notebook_name)
    return client.open_notebook_by_name(notebook_name)


def _set_active_notebook(client, notebook_id: str) -> None:
    setter = getattr(client, "set_active_notebook", None)
    if setter is not None:
        setter(notebook_id)
    else:
        setattr(client, "_active_notebook_id", notebook_id)


def _call_trigger(method, notebook_id: str):
    try:
        return method(notebook_id)
    except TypeError:
        return method()


def _make_client(state_file: Path, *, headless: bool):
    try:
        return NotebookLMClient(state_file, headless=headless)
    except TypeError:
        legacy_page = type(
            "_LegacyNotebookLMPage",
            (),
            {"url": "https://notebooklm.google.com/notebook/fixture", "calls": []},
        )()
        return NotebookLMClient(legacy_page)


def _find_or_create_notebook(client, notebook_name: str):
    method = getattr(client, "find_or_create_notebook", None)
    if method is not None:
        return method(notebook_name)
    return client.open_or_create_notebook(notebook_name)
