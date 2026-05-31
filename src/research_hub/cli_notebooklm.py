"""NotebookLM CLI handlers for Research Hub."""

from __future__ import annotations

import sys

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.errors import ResearchHubError
from research_hub.cli_common import _emit_cli_json, _json_safe


def _preflight_nlm_session(cfg, *, op_name: str) -> int | None:
    """v0.70.1: surface "session expired / not logged in" BEFORE the
    browser launches a 30-second deep-stack failure. Returns None when
    OK to proceed, or an exit code (1) with a one-line actionable hint
    printed to stderr when not."""
    from research_hub._invocation import recommended_cli_invocation
    from research_hub.notebooklm.auth import default_state_file, require_session_health

    inv = recommended_cli_invocation()
    state_file = default_state_file(cfg.research_hub_dir)
    try:
        require_session_health(state_file)
    except ResearchHubError as exc:
        reason = str(exc).split(": ", 1)[1] if ": " in str(exc) else str(exc)
        print(
            f"[notebooklm {op_name}] session check failed: {reason}. "
            f"Run `{inv} notebooklm login --auto-detect` to sign in.",
            file=sys.stderr,
        )
        return 1
    else:
        return None

def _notebooklm_bundle(cluster_slug: str, download_pdfs: bool = False) -> int:
    from research_hub.notebooklm.bundle import bundle_cluster

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    report = bundle_cluster(cluster, cfg, download_pdfs=download_pdfs)
    print(f"Bundle written to {report.bundle_dir}")
    print(
        f"Papers: {len(report.entries)} total "
        f"({report.pdf_count} PDFs, {report.url_count} URLs, "
        f"{report.text_count} abstracts, {report.skip_count} skipped)"
    )
    return 0

def _nlm_upload(
    cluster_slug: str,
    dry_run: bool,
    headless: bool,
    create_if_missing: bool,
    over_cap_strategy: str = "fail",
    shard_size: int = 50,
    include_suspect_urls: bool = False,
) -> int:
    from research_hub.notebooklm.upload import (
        NotebookLMCapacityError,
        check_cluster_capacity,
        upload_cluster,
    )

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    try:
        if over_cap_strategy == "fail":
            check_cluster_capacity(cluster, cfg)
        if not dry_run:
            rc = _preflight_nlm_session(cfg, op_name="upload")
            if rc is not None:
                return rc
        report = upload_cluster(
            cluster,
            cfg,
            dry_run=dry_run,
            headless=headless,
            create_if_missing=create_if_missing,
            over_cap_strategy=over_cap_strategy,
            shard_size=shard_size,
            include_suspect_urls=include_suspect_urls,
        )
    except NotebookLMCapacityError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Notebook: {report.notebook_name or '(planned)'}")
    if report.notebook_url:
        print(f"Notebook URL: {report.notebook_url}")
    print(
        f"Uploads: {report.success_count} succeeded, "
        f"{report.fail_count} failed, "
        f"{report.skipped_already_uploaded} skipped from cache"
    )
    if report.over_cap_skipped:
        print(f"Over-cap pruned ({report.over_cap_strategy}): {len(report.over_cap_skipped)} source(s)")
        for entry in report.over_cap_skipped:
            print(f"  [SKIP] {_display_entry(entry)}")
    for result in report.uploaded:
        status = "OK" if result.success else "FAIL"
        print(f"  [{status}] {result.source_kind}: {result.path_or_url}")
        if result.error:
            print(f"       {result.error}")
    # F8: a non-dry-run upload that transferred, cached, and pruned
    # *nothing* is not a success. Most common real cause (diagnosed
    # 2026-05-19): every URL source was skipped by the URL-quality
    # pre-check (`failed_no_abstract` on publisher/anti-bot pages) — see
    # `upload_skip_error_page` events. Less common: empty bundle, or an
    # actual upstream `notebooklm-py` API drift. List causes honestly.
    if (
        not report.dry_run
        and report.fail_count == 0
        and report.success_count == 0
        and report.skipped_already_uploaded == 0
        and not report.over_cap_skipped
    ):
        print(
            "ERROR: 0 sources uploaded, cached, or pruned. Likely causes "
            "(check the upload log above): (1) all URL sources skipped by "
            "the URL-quality pre-check -- re-run with --include-suspect-urls; "
            "(2) the cluster bundle was empty; (3) an upstream notebooklm-py "
            "API drift ('Sources data ... is not a list'). The notebook may "
            "exist but holds no sources -- not a clean upload.",
            file=sys.stderr,
        )
        return 1
    return 0 if report.fail_count == 0 else 1

def _display_entry(entry: dict) -> str:
    doi = str(entry.get("doi", "") or "").strip() or "(no DOI)"
    title = str(entry.get("title", "") or "").strip() or "(untitled)"
    return f"{doi}  {title}"

def _nlm_shard(
    cluster_slug: str,
    strategy: str,
    shard_size: int,
    dry_run: bool,
    headless: bool,
) -> int:
    from research_hub.notebooklm.upload import upload_cluster

    cfg = get_config()
    if not dry_run:
        rc = _preflight_nlm_session(cfg, op_name="shard")
        if rc is not None:
            return rc
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    report = upload_cluster(
        cluster,
        cfg,
        dry_run=dry_run,
        headless=headless,
        over_cap_strategy="shard",
        shard_size=shard_size,
        shard_strategy=strategy,
    )
    refreshed = ClusterRegistry(cfg.clusters_file).get(cluster_slug)
    shards = list(getattr(refreshed, "notebooklm_shards", []) or []) if refreshed is not None else []
    print(f"Shards: {len(shards)} notebook(s)")
    for shard in shards:
        print(f"  - {shard.notebook_name}: {shard.source_count} sources {shard.notebook_url}")
    if dry_run:
        print(f"Planned uploads: {report.success_count}")
    return 0 if report.fail_count == 0 else 1

def _nlm_download(
    cluster_slug: str,
    artifact_type: str,
    headless: bool,
    slide_format: str = "pdf",
    emit_json: bool = False,
) -> int:
    cfg = get_config()
    rc = _preflight_nlm_session(cfg, op_name="download")
    if rc is not None:
        if emit_json:
            _emit_cli_json(
                "notebooklm download",
                rc,
                {
                    "cluster_slug": cluster_slug,
                    "artifact_type": artifact_type,
                    "slide_format": slide_format,
                    "error": "session check failed",
                },
            )
            return rc
        return rc
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    if artifact_type == "slide-deck":
        from research_hub.notebooklm.upload import download_slide_deck_for_cluster

        report = download_slide_deck_for_cluster(
            cluster, cfg, headless=headless, output_format=slide_format,
        )
        if emit_json:
            payload = _json_safe(report)
            payload["artifact_type"] = artifact_type
            payload["slide_format"] = slide_format
            _emit_cli_json("notebooklm download", 0, payload)
            return 0
        print(f"Saved: {report.artifact_path}")
        print(f"  format: {slide_format}")
        print(f"  size: {report.char_count} bytes")
        return 0

    # default: brief
    from research_hub.notebooklm.upload import download_briefing_for_cluster

    report = download_briefing_for_cluster(cluster, cfg, headless=headless)
    if emit_json:
        payload = _json_safe(report)
        payload["artifact_type"] = artifact_type
        _emit_cli_json("notebooklm download", 0, payload)
        return 0
    print(f"Saved: {report.artifact_path}")
    print(f"  notebook: {report.notebook_name}")
    print(f"  characters: {report.char_count}")
    if report.titles:
        print(f"  saved briefings: {len(report.titles)}")
        for title in report.titles[:5]:
            print(f"    - {title}")
    return 0

def _nlm_read_briefing(cluster_slug: str) -> int:
    from research_hub.notebooklm.upload import read_latest_briefing

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")
    try:
        text = read_latest_briefing(cluster, cfg)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    print(text)
    return 0

def _nlm_generate(cluster_slug: str, artifact_type: str, headless: bool) -> int:
    from research_hub.notebooklm.upload import generate_artifact

    cfg = get_config()
    rc = _preflight_nlm_session(cfg, op_name="generate")
    if rc is not None:
        return rc
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    if artifact_type == "all":
        kinds = ["brief", "audio", "mind_map", "video", "slide_deck"]
    elif artifact_type == "mind-map":
        kinds = ["mind_map"]
    elif artifact_type == "slide-deck":
        kinds = ["slide_deck"]
    else:
        kinds = [artifact_type]

    for kind in kinds:
        url = generate_artifact(cluster, cfg, kind=kind, headless=headless)
        print(f"{kind}: {url}")
    return 0

def _nlm_ask(cluster_slug: str, *, question: str, headless: bool, timeout_sec: int) -> int:
    from research_hub.notebooklm.ask import ask_cluster_notebook

    cfg_for_check = get_config()
    rc = _preflight_nlm_session(cfg_for_check, op_name="ask")
    if rc is not None:
        return rc

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        print(f"  [ERR] Cluster not found: {cluster_slug}")
        return 1
    result = ask_cluster_notebook(
        cluster,
        cfg,
        question=question,
        headless=headless,
        timeout_sec=timeout_sec,
    )
    if not result.ok:
        print(f"  [ERR] {result.error}")
        return 1
    print(result.answer)
    print()
    print(f"  Saved: {result.artifact_path}  ({result.latency_seconds:.1f}s)")
    return 0
