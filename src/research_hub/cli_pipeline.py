"""Pipeline CLI handlers for Research Hub."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config, require_config
from research_hub.pipeline import run_pipeline
from research_hub.pipeline_repair import repair_cluster
from research_hub.cli_common import (
    _emit_cli_json,
    _load_zotero_if_configured,
    _stdout_to_stderr,
)


def _cmd_doctor(args, *, emit_json: bool = False) -> int:
    from research_hub.doctor import print_doctor_report, run_doctor
    from research_hub.vault_autofix import run_autofix

    autofix_summary = None
    if getattr(args, "autofix", False):
        autofix_summary = run_autofix(get_config())
        if not emit_json:
            print(
                "[autofix] "
                f"topic_cluster={autofix_summary['topic_cluster']} "
                f"ingested_at={autofix_summary['ingested_at']} "
                f"doi_derived={autofix_summary['doi_derived']} "
                f"skipped_no_cluster={autofix_summary['skipped_no_cluster']}"
            )
    results = run_doctor(strict=getattr(args, "strict", False))
    if emit_json:
        rc = 1 if any(result.status == "FAIL" for result in results) else 0
        _emit_cli_json(
            "doctor",
            rc,
            {
                "strict": bool(getattr(args, "strict", False)),
                "autofix": bool(getattr(args, "autofix", False)),
                "autofix_summary": autofix_summary,
                "checks": results,
            },
        )
        return rc
    return print_doctor_report(results)

def _cmd_ingest(args, *, emit_json: bool = False) -> int:
    run_kwargs = {
        "dry_run": args.dry_run,
        "cluster_slug": args.cluster,
        "query": args.query,
        "verify": args.verify,
        "allow_library_duplicates": args.allow_library_duplicates,
        "fit_check": args.fit_check,
        "fit_check_threshold": args.fit_check_threshold,
        "no_fit_check_auto_labels": args.no_fit_check_auto_labels,
        "batch_label": args.batch_label,
        "allow_archived_cluster": bool(args.cluster),
    }
    if args.with_pdfs:
        run_kwargs["with_pdfs"] = True
    with _stdout_to_stderr(emit_json):
        rc = run_pipeline(**run_kwargs)

    fit_check_labels = None
    if rc == 0 and args.fit_check and not args.no_fit_check_auto_labels:
        from research_hub.paper import apply_fit_check_to_labels

        cfg = get_config()
        fit_check_labels = apply_fit_check_to_labels(cfg, args.cluster)
        if not emit_json:
            print(f"auto-labeled {len(fit_check_labels['tagged'])} paper(s) as deprecated from fit-check sidecar")
    if emit_json:
        cfg = get_config()
        pipeline_output_path = Path(cfg.logs) / "pipeline_output.json"
        pipeline_output = None
        if pipeline_output_path.exists():
            try:
                pipeline_output = json.loads(pipeline_output_path.read_text(encoding="utf-8"))
            except Exception:
                pipeline_output = None
        _emit_cli_json(
            "ingest",
            rc,
            {
                "cluster_slug": args.cluster,
                "query": args.query,
                "dry_run": args.dry_run,
                "verify": args.verify,
                "with_pdfs": bool(args.with_pdfs),
                "fit_check": bool(args.fit_check),
                "fit_check_threshold": args.fit_check_threshold,
                "batch_label": args.batch_label,
                "pipeline_output_path": pipeline_output_path,
                "pipeline_output": pipeline_output,
                "fit_check_auto_labels": fit_check_labels,
            },
        )
    return rc

def _fit_check_emit(
    cluster_slug: str,
    candidates_path: str,
    definition: str | None,
    out: str | None,
    *,
    emit_json: bool = False,
) -> int:
    from research_hub.fit_check import emit_prompt

    cfg = get_config()
    candidates = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    prompt = emit_prompt(cluster_slug, candidates, definition=definition, cfg=cfg)
    if out:
        Path(out).write_text(prompt, encoding="utf-8")
        if emit_json:
            _emit_cli_json(
                "fit-check emit",
                0,
                {
                    "cluster_slug": cluster_slug,
                    "candidates_path": candidates_path,
                    "definition": definition,
                    "out_path": out,
                    "prompt_chars": len(prompt),
                },
            )
            return 0
        print(f"wrote {out}")
    else:
        if emit_json:
            _emit_cli_json(
                "fit-check emit",
                0,
                {
                    "cluster_slug": cluster_slug,
                    "candidates_path": candidates_path,
                    "definition": definition,
                    "out_path": None,
                    "prompt": prompt,
                    "prompt_chars": len(prompt),
                },
            )
            return 0
        print(prompt)
    return 0

def _fit_check_apply(
    cluster_slug: str,
    candidates_path: str,
    scored_path: str,
    threshold: int,
    auto_threshold: bool,
    out: str | None,
    *,
    emit_json: bool = False,
) -> int:
    from research_hub.fit_check import apply_scores

    cfg = get_config()
    candidates = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    scored = json.loads(Path(scored_path).read_text(encoding="utf-8"))
    report = apply_scores(
        cluster_slug,
        candidates,
        scored,
        threshold=threshold,
        auto_threshold=auto_threshold,
        cfg=cfg,
    )
    output = json.dumps([item.to_dict() for item in report.accepted], indent=2, ensure_ascii=False)
    if out:
        Path(out).write_text(output, encoding="utf-8")
    elif not emit_json:
        print(output)
    rc = 0
    if emit_json:
        _emit_cli_json(
            "fit-check apply",
            rc,
            {
                "cluster_slug": report.cluster_slug,
                "threshold": report.threshold,
                "candidates_in": report.candidates_in,
                "accepted": report.accepted,
                "rejected": report.rejected,
                "accepted_output_path": out,
                "auto_threshold": auto_threshold,
            },
        )
        return rc
    print(f"fit-check {report.summary()}", file=sys.stderr)
    return 0

def _fit_check_audit(cluster_slug: str) -> int:
    from research_hub.fit_check import parse_nlm_off_topic
    from research_hub.notebooklm.upload import read_latest_briefing
    from research_hub.topic import hub_cluster_dir

    cfg = get_config()
    try:
        briefing = read_latest_briefing(cluster_slug, cfg)
    except FileNotFoundError:
        print(f"no briefing found for cluster {cluster_slug}", file=sys.stderr)
        return 2
    flagged = parse_nlm_off_topic(briefing)
    out_path = hub_cluster_dir(cfg, cluster_slug) / ".fit_check_nlm_flags.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"cluster_slug": cluster_slug, "flagged": flagged}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if not flagged:
        print("off-topic: none")
        return 0
    print(f"off-topic: {len(flagged)} paper(s)")
    for title in flagged:
        print(f"  - {title}")
    return 1

def _fit_check_drift(cluster_slug: str, threshold: int) -> int:
    from research_hub.fit_check import drift_check

    cfg = get_config()
    result = drift_check(cfg, cluster_slug, threshold=threshold)
    print(result["prompt"])
    return 0

def _import_folder_command(args, emit_json: bool | None = None) -> int:
    from research_hub.importer import import_folder

    emit_json = bool(getattr(args, "json", False) if emit_json is None else emit_json)
    cfg = require_config()
    report = import_folder(
        cfg,
        args.folder,
        cluster_slug=args.cluster,
        extensions=tuple(item.strip() for item in args.extensions.split(",") if item.strip()),
        skip_existing=not args.no_skip_existing,
        use_graphify=args.use_graphify,
        graphify_graph=Path(args.graphify_graph) if args.graphify_graph else None,
        dry_run=args.dry_run,
        with_zotero=args.with_zotero,
        yes=args.yes,
        batch_label=args.batch_label,
    )
    rc = 0 if report.failed_count == 0 else 1
    if emit_json:
        _emit_cli_json("import-folder", rc, report)
        return rc
    print(f"\nImport summary ({'DRY RUN' if args.dry_run else 'WRITTEN'}):")
    print(f"  imported:  {report.imported_count}")
    print(f"  skipped:   {report.skipped_count}")
    print(f"  failed:    {report.failed_count}")
    if report.failed_count > 0:
        print("\nFailures:")
        for entry in report.entries:
            if entry.status == "failed":
                print(f"  {entry.path.name}: {entry.error}")
    return rc

def _import_folder_dep_precheck(args) -> int | None:
    import importlib

    target = Path(args.folder).expanduser().resolve()
    if not target.exists() or not target.is_dir():
        print(f"ERROR: not a directory: {target}", file=sys.stderr)
        return 2

    selected_extensions = {
        item.strip().lower().lstrip(".")
        for item in args.extensions.split(",")
        if item.strip()
    }
    discovered_extensions = {
        path.suffix.lower()
        for path in target.rglob("*")
        if path.is_file() and path.suffix
    }
    if selected_extensions:
        discovered_extensions = {
            suffix for suffix in discovered_extensions if suffix.lstrip(".") in selected_extensions
        }
    if not discovered_extensions:
        return None

    def _has_module(name: str) -> bool:
        try:
            return importlib.import_module(name) is not None
        except ImportError:
            return False

    missing_deps: list[str] = []
    if ".pdf" in discovered_extensions and not _has_module("pdfplumber"):
        missing_deps.append("pdfplumber (for PDF)")
    if ".docx" in discovered_extensions and not _has_module("docx"):
        missing_deps.append("python-docx (for DOCX)")
    if missing_deps:
        print(
            "ERROR: missing extras for file types in this folder:\n"
            f"  {', '.join(missing_deps)}\n"
            "  Install: pip install 'research-hub-pipeline[import]'",
            file=sys.stderr,
        )
        return 2
    return None

def _auto(
    *,
    topic,
    cluster_slug,
    cluster_name,
    max_papers,
    field,
    do_nlm,
    do_crystals,
    do_cluster_overview: bool = True,
    do_fit_check: bool = True,
    # CLI-handler default: mirrors the argparse default (strict 4). The
    # public `auto_pipeline(...)` API keeps `fit_check_threshold=3` so
    # existing programmatic callers / tests stay backward-compatible —
    # the strict default is a CLI-UX choice for end-users, not an API
    # contract change.
    fit_check_threshold: int = 4,
    no_llm_fit_check: bool = False,
    zotero_batch_size: int = 50,
    llm_cli,
    dry_run,
    append: bool = False,
    force: bool = False,
    show: bool = True,
    batch_label: str | None = None,
    # Programmatic callers (tests, library users) stay opt-in here so the
    # PDF-attach network round-trips don't fire silently; the CLI hands in
    # an explicit value from argparse (default-on via BooleanOptionalAction).
    with_pdfs: bool = False,
    with_summary: bool = False,
    peer_reviewed: bool = False,
    include_suspect_urls: bool = False,
    # Year filter — parsed from `--year RANGE` upstream. None = no filter.
    year_from: int | None = None,
    year_to: int | None = None,
    emit_json: bool = False,
) -> int:
    from research_hub.auto import auto_pipeline

    if cluster_slug:
        cfg = get_config()
        cluster_raw = cfg.raw / cluster_slug
        existing_papers = len(list(cluster_raw.glob("*.md"))) if cluster_raw.exists() else 0
        if existing_papers > 0 and not (append or force):
            message = (
                f"cluster '{cluster_slug}' already has {existing_papers} paper(s). "
                "Re-run with --append or --force."
            )
            if emit_json:
                _emit_cli_json(
                    "auto",
                    2,
                    {
                        "topic": topic,
                        "cluster_slug": cluster_slug,
                        "existing_papers": existing_papers,
                        "error": message,
                    },
                )
                return 2
            print(f"ERROR: cluster '{cluster_slug}' already has {existing_papers} paper(s).")
            print("       Re-run with --append (add more) or --force (overwrite).")
            return 2

    previous_batch_label = os.environ.get("RESEARCH_HUB_BATCH_LABEL")
    if batch_label is not None:
        os.environ["RESEARCH_HUB_BATCH_LABEL"] = batch_label
    try:
        auto_kwargs = {
            "topic": topic,
            "cluster_slug": cluster_slug,
            "cluster_name": cluster_name,
            "max_papers": max_papers,
            "field": field,
            "do_nlm": do_nlm,
            "do_crystals": do_crystals,
            "do_cluster_overview": do_cluster_overview,
            "do_fit_check": do_fit_check,
            "fit_check_threshold": fit_check_threshold,
            "no_llm_fit_check": no_llm_fit_check,
            "zotero_batch_size": zotero_batch_size,
            "llm_cli": llm_cli,
            "dry_run": dry_run,
            "append": append,
            "force": force,
            "peer_reviewed": peer_reviewed,
            "include_suspect_urls": include_suspect_urls,
            "print_progress": not emit_json,
        }
        if with_pdfs:
            auto_kwargs["with_pdfs"] = True
        if with_summary:
            auto_kwargs["with_summary"] = True
        if year_from is not None:
            auto_kwargs["year_from"] = year_from
        if year_to is not None:
            auto_kwargs["year_to"] = year_to
        report = auto_pipeline(**auto_kwargs)
    finally:
        if batch_label is not None:
            if previous_batch_label is None:
                os.environ.pop("RESEARCH_HUB_BATCH_LABEL", None)
            else:
                os.environ["RESEARCH_HUB_BATCH_LABEL"] = previous_batch_label
    if not report.ok:
        if emit_json:
            _emit_cli_json("auto", 1, report)
            return 1
        print(f"  [ERR] {report.error}")
        return 1
    if not emit_json and show and sys.stdin.isatty():
        try:
            from research_hub.dashboard import generate_dashboard

            generate_dashboard(open_browser=True)
        except Exception as exc:
            print(f"[auto] Could not open dashboard: {exc}.")
            print("       Run `research-hub serve --dashboard` to view results.")
    if emit_json:
        _emit_cli_json("auto", 0, report)
    return 0

def _sync_status(cluster_slug: str | None = None) -> int:
    from research_hub.vault.sync import compute_sync_status

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    zot = _load_zotero_if_configured()
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    clusters = registry.list()
    if cluster_slug is not None:
        cluster = registry.get(cluster_slug)
        if cluster is None:
            raise ValueError(f"Cluster not found: {cluster_slug}")
        clusters = [cluster]

    print("slug\tzotero\tobsidian\tnlm_cache\tin_both\tzotero_only\tobsidian_only")
    for cluster in clusters:
        status = compute_sync_status(cluster, zot, cfg.raw, nlm_cache_path=cache_path)
        print(
            f"{cluster.slug}\t{status.zotero_count}\t{status.obsidian_count}\t"
            f"{status.nlm_cached_count}\t{status.in_both}\t"
            f"{len(status.zotero_only)}\t{len(status.obsidian_only)}"
        )
    return 0

def _sync_reconcile(cluster_slug: str, execute: bool) -> int:
    from research_hub.vault.sync import reconcile_zotero_to_obsidian

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    zot = _load_zotero_if_configured()
    if zot is None:
        raise RuntimeError("Zotero client not configured")

    report = reconcile_zotero_to_obsidian(cluster, zot, cfg, dry_run=not execute)
    mode = "Planned" if report.dry_run else "Created"
    print(f"{mode} {len(report.created_notes)} notes for {cluster.slug}")
    print(f"Skipped existing: {report.skipped_existing}")
    if report.created_notes:
        for note_path in report.created_notes:
            print(note_path)
    if report.errors:
        print(f"Errors: {len(report.errors)}")
        for error in report.errors:
            print(json.dumps(error, ensure_ascii=False))
    return 0

def _pipeline_repair(cluster_slug: str, execute: bool) -> int:
    cfg = get_config()
    report = repair_cluster(cfg, cluster_slug, dry_run=not execute)
    print(report.summary())
    if report.zotero_orphans:
        print("Zotero orphan items:")
        for item in report.zotero_orphans:
            print(json.dumps(item, ensure_ascii=False))
    if report.obsidian_orphans:
        print("Obsidian orphan notes:")
        for note_path in report.obsidian_orphans:
            print(note_path)
    if report.stale_dedup:
        print("Stale dedup DOIs:")
        for doi in report.stale_dedup:
            print(doi)
    if report.created_notes:
        print("Created notes:")
        for note_path in report.created_notes:
            print(note_path)
    return 0

def _migrate_yaml(
    assign_cluster: str | None = None,
    folder: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    from research_hub.vault.migrate import migrate_vault

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    if assign_cluster is not None and registry.get(assign_cluster) is None:
        raise ValueError(f"Cluster not found: {assign_cluster}")

    folder_path = Path(folder) if folder else None
    report = migrate_vault(
        cfg.raw,
        cluster_override=assign_cluster,
        folder=folder_path,
        force=force,
        dry_run=dry_run,
    )
    mode = "Would patch" if dry_run else "Patched"
    print(
        f"{mode} {report['changed']} notes "
        f"(scanned {report['scanned']}, skipped {report['skipped']})"
    )
    return 0
