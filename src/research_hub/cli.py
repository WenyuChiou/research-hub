"""Command line entry points for Research Hub."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.dedup import DedupIndex, build_from_obsidian, build_from_zotero
from research_hub.pipeline import run_pipeline
from research_hub.search import SemanticScholarClient, iter_new_results


def _verify() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "verify_setup.py"
    completed = subprocess.run([sys.executable, str(script_path)], cwd=str(repo_root))
    return completed.returncode


def _rebuild_index() -> int:
    cfg = get_config()
    index = DedupIndex()
    for hit in build_from_obsidian(cfg.raw):
        index.add(hit)
    if cfg.zotero_library_id:
        from research_hub.zotero.client import get_client

        zot = get_client()
        for hit in build_from_zotero(zot, cfg.zotero_library_id):
            index.add(hit)
    index.save(cfg.research_hub_dir / "dedup_index.json")
    return 0


def _clusters_list() -> int:
    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    for cluster in registry.list():
        print(f"{cluster.slug}\t{cluster.name}")
    return 0


def _clusters_show(slug: str) -> int:
    from research_hub.vault.sync import compute_sync_status

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {slug}")
    status = compute_sync_status(
        cluster,
        _load_zotero_if_configured(),
        cfg.raw,
        nlm_cache_path=cfg.research_hub_dir / "nlm_cache.json",
    )
    print(f"Cluster: {cluster.name} ({cluster.slug})")
    print(f"  Zotero collection:   {cluster.zotero_collection_key or '(unset)'}")
    print(f"  Obsidian folder:     {cluster.obsidian_subfolder or '(unset)'}")
    print(f"  NotebookLM notebook: {cluster.notebooklm_notebook or '(unset)'}")
    print(f"  NotebookLM URL:      {status.notebook_url or '(unset)'}")
    print(
        "  Sync counts: "
        f"Zotero={status.zotero_count}, "
        f"Obsidian={status.obsidian_count}, "
        f"NotebookLM-cache={status.nlm_cached_count}, "
        f"in-both={status.in_both}"
    )
    if status.zotero_only:
        print(f"  Zotero-only keys:    {', '.join(status.zotero_only)}")
    if status.obsidian_only:
        print("  Obsidian-only notes:")
        for note_path in status.obsidian_only:
            print(f"    {note_path}")
    return 0


def _clusters_new(query: str, name: str | None, slug: str | None) -> int:
    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.create(query=query, name=name, slug=slug)
    print(cluster.slug)
    return 0


def _clusters_bind(slug: str, zotero_key, obsidian_folder, notebooklm_notebook) -> int:
    cfg = get_config()
    reg = ClusterRegistry(cfg.clusters_file)
    cluster = reg.bind(
        slug=slug,
        zotero_collection_key=zotero_key,
        obsidian_subfolder=obsidian_folder,
        notebooklm_notebook=notebooklm_notebook,
    )
    print(f"Bound {cluster.slug}:")
    print(f"  Zotero collection:   {cluster.zotero_collection_key or '(unset)'}")
    print(f"  Obsidian folder:     {cluster.obsidian_subfolder or '(unset)'}")
    print(f"  NotebookLM notebook: {cluster.notebooklm_notebook or '(unset)'}")
    return 0


def _cleanup_hub(dry_run: bool = False) -> int:
    from research_hub.vault.cleanup import dedup_hub_pages

    cfg = get_config()
    report = dedup_hub_pages(cfg.hub, dry_run=dry_run)
    prefix = "Would remove" if dry_run else "Removed"
    print(f"{prefix} {report.wikilinks_removed} duplicate wikilinks in {report.files_modified} files")
    print(f"(scanned {report.files_scanned} files under {cfg.hub})")
    if report.per_file:
        for rel, count in sorted(report.per_file.items(), key=lambda kv: -kv[1])[:15]:
            print(f"  {count:4d}  {rel}")
    return 0


def _synthesize(cluster: str | None, graph_colors: bool) -> int:
    from research_hub.vault.graph_config import update_from_clusters_file
    from research_hub.vault.synthesis import synthesize_all_clusters, synthesize_cluster

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)

    if cluster:
        cluster_obj = registry.get(cluster)
        if cluster_obj is None:
            raise ValueError(f"Cluster not found: {cluster}")
        try:
            out = synthesize_cluster(
                cluster_obj.slug,
                cluster_obj.name,
                cluster_obj.first_query,
                cfg.raw,
                cfg.hub,
            )
            print(f"Wrote {out}")
        except FileNotFoundError as exc:
            print(f"Skipped: {exc}")
    else:
        outs = synthesize_all_clusters(cfg.raw, cfg.hub, cfg.clusters_file)
        print(f"Wrote {len(outs)} synthesis pages")

    if graph_colors:
        report = update_from_clusters_file(cfg.root, cfg.clusters_file)
        if report.updated:
            print(f"Updated graph.json with {report.color_groups_written} color groups")
        else:
            print(f"graph.json skipped: {report.skipped_reason}")

    return 0


def _search(query: str, limit: int) -> int:
    cfg = get_config()
    index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    client = SemanticScholarClient()
    results = iter_new_results(client, query, index.doi_to_hits.keys(), limit=limit)
    for result in results:
        print(f"{result.title}\t{result.doi}")
    return 0


def _status(cluster: str | None = None) -> int:
    from research_hub.vault.progress import print_status_table

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    print_status_table(cfg.raw, registry, one_cluster=cluster)
    return 0


def _load_zotero_if_configured():
    try:
        from research_hub.zotero.client import get_client

        return get_client()
    except Exception:
        return None


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


def _notebooklm_bundle(cluster_slug: str) -> int:
    from research_hub.notebooklm.bundle import bundle_cluster

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    report = bundle_cluster(cluster, cfg)
    print(f"Bundle written to {report.bundle_dir}")
    print(
        f"Papers: {len(report.entries)} total "
        f"({report.pdf_count} PDFs, {report.url_count} URLs, {report.skip_count} skipped)"
    )
    return 0


def _nlm_upload(
    cluster_slug: str,
    dry_run: bool,
    headless: bool,
    create_if_missing: bool,
) -> int:
    from research_hub.notebooklm.upload import upload_cluster

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    report = upload_cluster(
        cluster,
        cfg,
        dry_run=dry_run,
        headless=headless,
        create_if_missing=create_if_missing,
    )
    print(f"Notebook: {report.notebook_name or '(planned)'}")
    if report.notebook_url:
        print(f"Notebook URL: {report.notebook_url}")
    print(
        f"Uploads: {report.success_count} succeeded, "
        f"{report.fail_count} failed, "
        f"{report.skipped_already_uploaded} skipped from cache"
    )
    for result in report.uploaded:
        status = "OK" if result.success else "FAIL"
        print(f"  [{status}] {result.source_kind}: {result.path_or_url}")
        if result.error:
            print(f"       {result.error}")
    return 0 if report.fail_count == 0 else 1


def _nlm_generate(cluster_slug: str, artifact_type: str, headless: bool) -> int:
    from research_hub.notebooklm.upload import generate_artifact

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    if artifact_type == "all":
        kinds = ["brief", "audio", "mind_map", "video"]
    elif artifact_type == "mind-map":
        kinds = ["mind_map"]
    else:
        kinds = [artifact_type]

    for kind in kinds:
        url = generate_artifact(cluster, cfg, kind=kind, headless=headless)
        print(f"{kind}: {url}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-hub")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the research pipeline")
    run_parser.add_argument("--topic", default=None, help="Pipeline topic context")
    run_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to process")
    run_parser.add_argument("--dry-run", action="store_true", help="Validate config and inputs only")
    run_parser.add_argument("--cluster", default=None, help="Cluster slug for ingestion")
    run_parser.add_argument("--query", default=None, help="Query text")

    ingest_parser = subparsers.add_parser("ingest", help="Run ingestion")
    ingest_parser.add_argument("--cluster", default=None, help="Cluster slug for ingestion")
    ingest_parser.add_argument("--query", default=None, help="Query text")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Validate config and inputs only")

    subparsers.add_parser("index", help="Rebuild dedup_index.json from Zotero and Obsidian")

    clusters_parser = subparsers.add_parser("clusters", help="Manage topic clusters")
    clusters_subparsers = clusters_parser.add_subparsers(dest="clusters_command", required=True)
    clusters_subparsers.add_parser("list", help="List clusters")
    show_parser = clusters_subparsers.add_parser("show", help="Show cluster details")
    show_parser.add_argument("slug")
    new_parser = clusters_subparsers.add_parser("new", help="Create a new cluster")
    new_parser.add_argument("--query", required=True)
    new_parser.add_argument("--name", default=None)
    new_parser.add_argument("--slug", default=None)
    bind_parser = clusters_subparsers.add_parser(
        "bind", help="Link a cluster to Zotero/Obsidian/NotebookLM"
    )
    bind_parser.add_argument("slug")
    bind_parser.add_argument(
        "--zotero", dest="zotero_key", default=None, help="Zotero collection key"
    )
    bind_parser.add_argument(
        "--obsidian", dest="obsidian_folder", default=None, help="Obsidian sub-folder"
    )
    bind_parser.add_argument(
        "--notebooklm",
        dest="notebooklm_notebook",
        default=None,
        help="NotebookLM notebook name",
    )

    search_parser = subparsers.add_parser("search", help="Search Semantic Scholar")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)

    status_parser = subparsers.add_parser("status", help="Show per-cluster reading progress")
    status_parser.add_argument("--cluster", default=None, help="Show only this cluster")

    migrate_parser = subparsers.add_parser(
        "migrate-yaml", help="Patch legacy notes to v0.3.x YAML spec"
    )
    migrate_parser.add_argument(
        "--assign-cluster",
        default=None,
        help="Bulk-assign all matched notes to this cluster slug",
    )
    migrate_parser.add_argument(
        "--folder",
        default=None,
        help="Restrict to this subfolder under raw/",
    )
    migrate_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing topic_cluster values",
    )
    migrate_parser.add_argument(
        "--dry-run", action="store_true", help="Report without writing"
    )

    subparsers.add_parser("verify", help="Run repository verification checks")

    cleanup_parser = subparsers.add_parser(
        "cleanup", help="Deduplicate wikilinks across hub pages"
    )
    cleanup_parser.add_argument(
        "--dry-run", action="store_true", help="Report without writing"
    )

    synth_parser = subparsers.add_parser(
        "synthesize", help="Generate cluster synthesis pages"
    )
    synth_parser.add_argument(
        "--cluster", default=None, help="Only synthesize this cluster slug"
    )
    synth_parser.add_argument(
        "--graph-colors",
        action="store_true",
        help="Also update .obsidian/graph.json cluster colors",
    )

    sync_parser = subparsers.add_parser("sync", help="Cross-system sync status and reconcile")
    sync_sub = sync_parser.add_subparsers(dest="sync_command", required=True)
    sync_status = sync_sub.add_parser("status", help="Show drift across Zotero/Obsidian/NotebookLM")
    sync_status.add_argument("--cluster", default=None)
    sync_reconcile = sync_sub.add_parser("reconcile", help="Fix Zotero-to-Obsidian drift")
    sync_reconcile.add_argument("--cluster", required=True)
    sync_reconcile.add_argument("--dry-run", action="store_true")
    sync_reconcile.add_argument("--execute", action="store_true")

    nlm_parser = subparsers.add_parser("notebooklm", help="NotebookLM operations")
    nlm_sub = nlm_parser.add_subparsers(dest="notebooklm_command", required=True)
    nlm_login = nlm_sub.add_parser("login", help="Interactive one-time Google sign-in")
    nlm_login.add_argument(
        "--use-system-chrome",
        action="store_true",
        help="Launch the installed Chrome binary (channel=chrome) instead of bundled Chromium",
    )
    nlm_login.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max seconds to wait for login (default: 300)",
    )
    nlm_bundle = nlm_sub.add_parser("bundle", help="Export a drag-drop folder for NotebookLM")
    nlm_bundle.add_argument("--cluster", required=True)
    nlm_upload = nlm_sub.add_parser("upload", help="Auto-upload bundle to NotebookLM")
    nlm_upload.add_argument("--cluster", required=True)
    nlm_upload.add_argument("--dry-run", action="store_true")
    nlm_upload.add_argument("--headless", action="store_true", default=True)
    nlm_upload.add_argument("--visible", dest="headless", action="store_false")
    nlm_upload.add_argument("--create-if-missing", action="store_true", default=True)
    nlm_generate = nlm_sub.add_parser("generate", help="Trigger NotebookLM artifact generation")
    nlm_generate.add_argument("--cluster", required=True)
    nlm_generate.add_argument(
        "--type",
        choices=["brief", "audio", "mind-map", "video", "all"],
        default="brief",
    )
    nlm_generate.add_argument("--visible", dest="headless", action="store_false", default=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "run"):
        return run_pipeline(
            dry_run=getattr(args, "dry_run", False),
            cluster_slug=getattr(args, "cluster", None),
            query=getattr(args, "query", None),
        )
    if args.command == "ingest":
        return run_pipeline(dry_run=args.dry_run, cluster_slug=args.cluster, query=args.query)
    if args.command == "index":
        return _rebuild_index()
    if args.command == "clusters":
        if args.clusters_command == "list":
            return _clusters_list()
        if args.clusters_command == "show":
            return _clusters_show(args.slug)
        if args.clusters_command == "new":
            return _clusters_new(args.query, args.name, args.slug)
        if args.clusters_command == "bind":
            return _clusters_bind(
                args.slug,
                args.zotero_key,
                args.obsidian_folder,
                args.notebooklm_notebook,
            )
    if args.command == "search":
        return _search(args.query, args.limit)
    if args.command == "status":
        return _status(cluster=args.cluster)
    if args.command == "sync":
        if args.sync_command == "status":
            return _sync_status(cluster_slug=args.cluster)
        if args.sync_command == "reconcile":
            return _sync_reconcile(cluster_slug=args.cluster, execute=args.execute)
    if args.command == "migrate-yaml":
        return _migrate_yaml(
            assign_cluster=args.assign_cluster,
            folder=args.folder,
            force=args.force,
            dry_run=args.dry_run,
        )
    if args.command == "verify":
        return _verify()
    if args.command == "cleanup":
        return _cleanup_hub(dry_run=args.dry_run)
    if args.command == "synthesize":
        return _synthesize(cluster=args.cluster, graph_colors=args.graph_colors)
    if args.command == "notebooklm":
        if args.notebooklm_command == "login":
            from research_hub.notebooklm.session import login_interactive

            cfg = get_config()
            return login_interactive(
                cfg.research_hub_dir / "nlm_sessions" / "default",
                use_system_chrome=args.use_system_chrome,
                timeout_sec=args.timeout,
            )
        if args.notebooklm_command == "bundle":
            return _notebooklm_bundle(args.cluster)
        if args.notebooklm_command == "upload":
            return _nlm_upload(args.cluster, args.dry_run, args.headless, args.create_if_missing)
        if args.notebooklm_command == "generate":
            return _nlm_generate(args.cluster, args.type, args.headless)

    parser.error(f"Unknown command: {args.command}")
    return 2
