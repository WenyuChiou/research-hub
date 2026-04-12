"""Command line entry points for Research Hub."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.dedup import DedupIndex, build_from_obsidian, build_from_zotero
from research_hub.operations import mark_paper, move_paper, remove_paper
from research_hub.pipeline import run_pipeline
from research_hub.search import SemanticScholarClient, iter_new_results
from research_hub.suggest import PaperInput, suggest_cluster_for_paper, suggest_related_papers
from research_hub.verify import verify_arxiv, verify_doi, verify_paper
from research_hub.vault_search import search_vault


def _verify(args) -> int:
    if args.doi:
        result = verify_doi(args.doi)
        print(f"ok={result.ok} source={result.source} reason={result.reason}")
        return 0 if result.ok else 1
    if args.arxiv:
        result = verify_arxiv(args.arxiv)
        print(f"ok={result.ok} source={result.source} reason={result.reason}")
        return 0 if result.ok else 1
    if args.paper:
        result = verify_paper(args.paper, authors=args.paper_author, year=args.paper_year)
        print(f"ok={result.ok} source={result.source} reason={result.reason}")
        return 0 if result.ok else 1

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "verify_setup.py"
    if not script_path.exists():
        print("Repo-integrity script not found (this is normal for pip-installed packages).")
        print("Use --doi, --arxiv, or --paper to verify a specific paper.")
        return 0
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


def _clusters_rename(slug: str, name: str) -> int:
    cfg = get_config()
    cluster = ClusterRegistry(cfg.clusters_file).rename(slug, name)
    print(f"{cluster.slug}\t{cluster.name}")
    return 0


def _clusters_delete(slug: str, dry_run: bool) -> int:
    cfg = get_config()
    result = ClusterRegistry(cfg.clusters_file).delete(slug, dry_run=dry_run)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _clusters_merge(source: str, target: str) -> int:
    cfg = get_config()
    result = ClusterRegistry(cfg.clusters_file).merge(source, target, vault_raw=cfg.raw)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _clusters_split(source: str, query: str, new_name: str) -> int:
    cfg = get_config()
    result = ClusterRegistry(cfg.clusters_file).split(source, query, new_name, vault_raw=cfg.raw)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _remove(identifier: str, include_zotero: bool, dry_run: bool) -> int:
    print(json.dumps(remove_paper(identifier, include_zotero=include_zotero, dry_run=dry_run)))
    return 0


def _mark(slug: str | None, status: str, cluster: str | None) -> int:
    print(json.dumps(mark_paper(slug, status, cluster=cluster)))
    return 0


def _move(slug: str, to_cluster: str) -> int:
    print(json.dumps(move_paper(slug, to_cluster)))
    return 0


def _find(
    query: str,
    cluster: str | None,
    status: str | None,
    full_text: bool,
    emit_json: bool,
    limit: int,
) -> int:
    results = search_vault(query, cluster=cluster, status=status, full_text=full_text, limit=limit)
    if emit_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    for item in results:
        print(f"{item['slug']}\t{item['title']}\t{item['cluster']}\t{item['status']}")
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


def _cite(
    identifier: str | None,
    cluster: str | None,
    content_format: str,
    out_path: str | None,
) -> int:
    """Export BibTeX / BibLaTeX / RIS / CSL-JSON for a paper or cluster.

    Resolves the identifier (DOI, slug, or raw title) to one or more
    Zotero item keys via the dedup index and vault frontmatter, then
    calls ZoteroDualClient.get_formatted to fetch each entry. Concatenates
    results and writes to stdout or --out file.
    """
    from research_hub.zotero.client import ZoteroDualClient
    from research_hub.dedup import normalize_doi

    cfg = get_config()
    index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")

    keys: list[str] = []
    if cluster:
        cluster_dir = cfg.raw / cluster
        if not cluster_dir.exists():
            print(f"Cluster folder not found: {cluster_dir}")
            return 1
        for md_path in sorted(cluster_dir.glob("*.md")):
            key = _read_zotero_key_from_frontmatter(md_path)
            if key:
                keys.append(key)
        if not keys:
            print(f"No zotero-key entries found in {cluster_dir}")
            return 1
    elif identifier:
        normalized = normalize_doi(identifier)
        hits = index.doi_to_hits.get(normalized, [])
        for hit in hits:
            if hit.zotero_key and hit.zotero_key not in keys:
                keys.append(hit.zotero_key)
        if not keys:
            # Fall back: treat identifier as a filename stem in raw/
            for md_path in cfg.raw.rglob(f"{identifier}.md"):
                key = _read_zotero_key_from_frontmatter(md_path)
                if key:
                    keys.append(key)
        if not keys:
            print(f"Could not resolve identifier '{identifier}' to a Zotero key")
            return 1
    else:
        print("Either a positional <identifier> or --cluster <slug> is required")
        return 2

    dual = ZoteroDualClient()
    entries: list[str] = []
    for key in keys:
        try:
            entries.append(dual.get_formatted(key, content_format=content_format))
        except Exception as exc:
            print(f"  [warn] {key}: {exc}")
    body = "\n\n".join(e for e in entries if e)
    if out_path:
        Path(out_path).write_text(body + "\n", encoding="utf-8")
        print(f"Wrote {len(entries)} {content_format} entries to {out_path}")
    else:
        print(body)
    return 0 if entries else 1


def _read_zotero_key_from_frontmatter(md_path: Path) -> str | None:
    """Pull the `zotero-key: XXXX` line out of an Obsidian raw note."""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    frontmatter = text[3:end]
    import re as _re
    match = _re.search(r"^zotero-key:\s*([A-Z0-9]+)", frontmatter, _re.MULTILINE)
    return match.group(1) if match else None


def _search(query: str, limit: int, verify: bool = False) -> int:
    cfg = get_config()
    index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    client = SemanticScholarClient()
    results = iter_new_results(client, query, index.doi_to_hits.keys(), limit=limit)
    for result in results:
        line = f"{result.title}\t{result.doi}"
        if verify:
            verified = bool(result.doi) and verify_doi(result.doi).ok
            line += "\tVERIFIED" if verified else "\tUNVERIFIED"
        print(line)
    return 0


def _references(identifier: str, limit: int, emit_json: bool) -> int:
    from research_hub.citation_graph import CitationGraphClient

    client = CitationGraphClient()
    nodes = client.get_references(identifier, limit=limit)
    if emit_json:
        print(json.dumps([asdict(node) for node in nodes], indent=2, ensure_ascii=False))
        return 0
    print(f"References of {identifier} ({len(nodes)} returned):")
    for node in nodes:
        year = node.year if node.year else "????"
        first_author = (node.authors[0] if node.authors else "Unknown").split()[-1]
        print(f"  [{year}] {first_author:15s} {node.title[:70]}")
        if node.doi:
            print(f"             DOI: {node.doi}")
    return 0


def _cited_by(identifier: str, limit: int, emit_json: bool) -> int:
    from research_hub.citation_graph import CitationGraphClient

    client = CitationGraphClient()
    nodes = client.get_citations(identifier, limit=limit)
    if emit_json:
        print(json.dumps([asdict(node) for node in nodes], indent=2, ensure_ascii=False))
        return 0
    print(f"Citations of {identifier} ({len(nodes)} returned):")
    for node in nodes:
        year = node.year if node.year else "????"
        first_author = (node.authors[0] if node.authors else "Unknown").split()[-1]
        print(f"  [{year}] {first_author:15s} {node.title[:70]}")
        if node.doi:
            print(f"             DOI: {node.doi}")
    return 0


def _suggest(identifier: str, top: int, emit_json: bool) -> int:
    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    dedup = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")

    paper = PaperInput(title=identifier)
    if re.search(r"10\.\S+", identifier):
        fetched = SemanticScholarClient().get_paper(identifier)
        if fetched is not None:
            paper = PaperInput(
                title=fetched.title,
                doi=fetched.doi,
                authors=fetched.authors,
                year=fetched.year,
                venue=fetched.venue,
                abstract=fetched.abstract,
            )
    elif re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", identifier):
        fetched = SemanticScholarClient().get_paper(identifier)
        if fetched is not None:
            paper = PaperInput(
                title=fetched.title,
                doi=fetched.doi,
                authors=fetched.authors,
                year=fetched.year,
                venue=fetched.venue,
                abstract=fetched.abstract,
            )

    cluster_suggestions = suggest_cluster_for_paper(paper, registry, dedup, top_n=3)
    related_papers = suggest_related_papers(paper, dedup, registry, top_n=top)

    if emit_json:
        payload = {
            "identifier": identifier,
            "paper": asdict(paper),
            "cluster_suggestions": [asdict(item) for item in cluster_suggestions],
            "related_papers": [asdict(item) for item in related_papers],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("Cluster suggestions (top 3):")
    for item in cluster_suggestions:
        print(f"  [{item.score:.1f}] {item.cluster_slug}")
        print(f"         {', '.join(item.reasons)}")

    print(f"\nRelated papers (top {top}):")
    for item in related_papers:
        print(f"  [{item.score:.1f}] {item.title}  ({item.source})")
        print(f"         {', '.join(item.reasons)}")
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

    init_parser = subparsers.add_parser(
        "init",
        help="Interactive setup wizard for first-time users",
    )
    init_parser.add_argument("--vault", default=None, help="Vault root directory")
    init_parser.add_argument("--zotero-key", default=None, help="Zotero API key")
    init_parser.add_argument(
        "--zotero-library-id",
        default=None,
        help="Zotero library ID",
    )
    init_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip prompts; require all values via flags",
    )

    subparsers.add_parser("doctor", help="Health check for research-hub installation")

    install_parser = subparsers.add_parser(
        "install",
        help="Install research-hub skill for AI coding assistants",
    )
    install_parser.add_argument(
        "--platform",
        choices=["claude-code", "codex", "cursor", "gemini"],
        default=None,
        help="Target platform",
    )
    install_parser.add_argument(
        "--list",
        dest="list_platforms",
        action="store_true",
        help="List supported platforms and install status",
    )

    subparsers.add_parser(
        "serve",
        help="Start MCP stdio server for AI assistant integration",
    )

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

    for parser_with_verify in (run_parser, ingest_parser):
        parser_with_verify.add_argument(
            "--no-verify",
            dest="verify",
            action="store_false",
            default=True,
            help="Skip DOI/arxiv HTTP verification (default: verify on)",
        )

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
    rename_parser = clusters_subparsers.add_parser("rename", help="Rename a cluster")
    rename_parser.add_argument("slug")
    rename_parser.add_argument("--name", required=True)
    delete_parser = clusters_subparsers.add_parser("delete", help="Delete a cluster")
    delete_parser.add_argument("slug")
    delete_parser.add_argument("--dry-run", action="store_true")
    merge_parser = clusters_subparsers.add_parser("merge", help="Merge two clusters")
    merge_parser.add_argument("source", help="Source cluster slug (will be removed)")
    merge_parser.add_argument("--into", required=True, dest="target", help="Target cluster slug")
    split_parser = clusters_subparsers.add_parser("split", help="Split a cluster")
    split_parser.add_argument("source", help="Source cluster slug")
    split_parser.add_argument("--query", required=True, help="Keywords for the new sub-cluster")
    split_parser.add_argument("--new-name", required=True, help="Display name for new cluster")

    remove_parser = subparsers.add_parser("remove", help="Remove a paper from the vault")
    remove_parser.add_argument("identifier", help="DOI or note filename slug")
    remove_parser.add_argument("--zotero", action="store_true", help="Also delete from Zotero")
    remove_parser.add_argument("--dry-run", action="store_true")

    mark_parser = subparsers.add_parser("mark", help="Update reading status of a paper")
    mark_parser.add_argument("slug", nargs="?", default=None, help="Note filename slug")
    mark_parser.add_argument(
        "--status", required=True, choices=["unread", "reading", "deep-read", "cited"]
    )
    mark_parser.add_argument("--cluster", default=None, help="Bulk-mark all notes in cluster")

    move_parser = subparsers.add_parser("move", help="Move a paper to a different cluster")
    move_parser.add_argument("slug", help="Note filename slug")
    move_parser.add_argument("--to", required=True, dest="to_cluster", help="Target cluster slug")

    find_parser = subparsers.add_parser("find", help="Search within vault notes")
    find_parser.add_argument("query", help="Search query")
    find_parser.add_argument("--cluster", default=None)
    find_parser.add_argument(
        "--status", default=None, choices=["unread", "reading", "deep-read", "cited"]
    )
    find_parser.add_argument("--full", action="store_true", help="Full-text search (slower)")
    find_parser.add_argument("--json", action="store_true")
    find_parser.add_argument("--limit", type=int, default=20)

    search_parser = subparsers.add_parser("search", help="Search Semantic Scholar")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify each DOI against doi.org before printing (adds 1-2s per result)",
    )

    references_parser = subparsers.add_parser(
        "references",
        help="List papers cited by the given paper (its bibliography)",
    )
    references_parser.add_argument("identifier", help="DOI, arXiv ID, or S2 paper ID")
    references_parser.add_argument("--limit", type=int, default=20)
    references_parser.add_argument("--json", action="store_true")

    citations_parser = subparsers.add_parser(
        "cited-by",
        help="List papers that cite the given paper",
    )
    citations_parser.add_argument("identifier", help="DOI, arXiv ID, or S2 paper ID")
    citations_parser.add_argument("--limit", type=int, default=20)
    citations_parser.add_argument("--json", action="store_true")

    suggest_parser = subparsers.add_parser(
        "suggest",
        help="Suggest which cluster a new paper belongs to and related existing notes",
    )
    suggest_parser.add_argument(
        "identifier",
        help="DOI, arxiv ID, or quoted paper title",
    )
    suggest_parser.add_argument(
        "--top", type=int, default=5,
        help="Maximum number of related-paper suggestions (default 5)",
    )
    suggest_parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON instead of human output",
    )

    cite_parser = subparsers.add_parser(
        "cite",
        help="Export BibTeX / BibLaTeX / RIS / CSL-JSON for a paper or cluster",
    )
    cite_parser.add_argument(
        "identifier",
        nargs="?",
        default=None,
        help="DOI or raw-note filename stem (omit when using --cluster)",
    )
    cite_parser.add_argument(
        "--cluster",
        default=None,
        help="Export every paper in this cluster folder",
    )
    cite_parser.add_argument(
        "--format",
        dest="content_format",
        choices=["bibtex", "biblatex", "ris", "csljson"],
        default="bibtex",
    )
    cite_parser.add_argument(
        "--out",
        default=None,
        help="Write to this file instead of stdout",
    )

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

    verify_parser = subparsers.add_parser(
        "verify",
        help="Run verification checks (repo integrity or paper identifier)",
    )
    verify_parser.add_argument("--doi", default=None, help="Verify a single DOI")
    verify_parser.add_argument("--arxiv", default=None, help="Verify a single arXiv ID")
    verify_parser.add_argument(
        "--paper",
        default=None,
        help="Verify by fuzzy title match against Semantic Scholar",
    )
    verify_parser.add_argument(
        "--paper-year",
        type=int,
        default=None,
        help="Optional year constraint when --paper is used",
    )
    verify_parser.add_argument(
        "--paper-author",
        action="append",
        default=None,
        help="Optional author surname(s) when --paper is used (can repeat)",
    )

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
        "--cdp",
        action="store_true",
        help="CDP attach mode (RECOMMENDED): launches real Chrome as a subprocess with "
             "--remote-debugging-port and has Playwright connect over CDP. Chrome never knows "
             "it is being automated, so Google's bot check does not fire. Fixes the "
             "'This browser or app may have security concerns' block.",
    )
    nlm_login.add_argument(
        "--chrome-binary",
        default=None,
        help="Path to chrome.exe (CDP mode). Auto-detected if omitted.",
    )
    nlm_login.add_argument(
        "--use-system-chrome",
        action="store_true",
        help="Launch the installed Chrome binary (channel=chrome) instead of bundled Chromium",
    )
    nlm_login.add_argument(
        "--from-chrome-profile",
        action="store_true",
        help="Clone your existing Chrome profile (with Google auth cookies already present) into "
             "the session dir so Google does not trigger bot detection. Chrome MUST be closed first.",
    )
    nlm_login.add_argument(
        "--chrome-profile-path",
        default=None,
        help="Override the auto-detected Chrome user data dir (the folder containing 'Default')",
    )
    nlm_login.add_argument(
        "--chrome-profile-name",
        default="Default",
        help="Which Chrome profile to clone (default: Default; try 'Profile 1' etc.)",
    )
    nlm_login.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max seconds to wait for login (default: 300)",
    )
    nlm_login.add_argument(
        "--keep-open",
        action="store_true",
        help="(CDP mode) Do NOT auto-close on login detection. Keeps Chrome open "
             "so you can inspect the DOM with F12 DevTools. Press Enter in the "
             "terminal when finished.",
    )
    nlm_bundle = nlm_sub.add_parser("bundle", help="Export a drag-drop folder for NotebookLM")
    nlm_bundle.add_argument("--cluster", required=True)
    nlm_upload = nlm_sub.add_parser("upload", help="Auto-upload bundle to NotebookLM")
    nlm_upload.add_argument("--cluster", required=True)
    nlm_upload.add_argument("--dry-run", action="store_true")
    nlm_upload.add_argument("--headless", action="store_true", default=False)
    nlm_upload.add_argument("--visible", dest="headless", action="store_false")
    nlm_upload.add_argument("--create-if-missing", action="store_true", default=True)
    nlm_generate = nlm_sub.add_parser("generate", help="Trigger NotebookLM artifact generation")
    nlm_generate.add_argument("--cluster", required=True)
    nlm_generate.add_argument(
        "--type",
        choices=["brief", "audio", "mind-map", "video", "all"],
        default="brief",
    )
    nlm_generate.add_argument("--headless", action="store_true", default=False)
    nlm_generate.add_argument("--visible", dest="headless", action="store_false")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in (None, "run"):
        return run_pipeline(
            dry_run=getattr(args, "dry_run", False),
            cluster_slug=getattr(args, "cluster", None),
            query=getattr(args, "query", None),
            verify=getattr(args, "verify", True),
        )
    if args.command == "init":
        from research_hub.init_wizard import run_init

        return run_init(
            vault_root=args.vault,
            zotero_key=args.zotero_key,
            zotero_library_id=args.zotero_library_id,
            non_interactive=args.non_interactive,
        )
    if args.command == "doctor":
        from research_hub.doctor import print_doctor_report, run_doctor

        return print_doctor_report(run_doctor())
    if args.command == "install":
        from research_hub.skill_installer import install_skill, list_platforms

        if args.list_platforms:
            for key, name, installed in list_platforms():
                status = "installed" if installed else "not installed"
                print(f"  {key:15s} {name:20s} [{status}]")
            return 0
        if not args.platform:
            print("Specify --platform or use --list to see options.")
            return 1
        path = install_skill(args.platform)
        print(f"Installed SKILL.md to {path}")
        return 0
    if args.command == "serve":
        from research_hub.mcp_server import main as serve_main

        serve_main()
        return 0
    if args.command == "ingest":
        return run_pipeline(
            dry_run=args.dry_run,
            cluster_slug=args.cluster,
            query=args.query,
            verify=args.verify,
        )
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
        if args.clusters_command == "rename":
            return _clusters_rename(args.slug, args.name)
        if args.clusters_command == "delete":
            return _clusters_delete(args.slug, args.dry_run)
        if args.clusters_command == "merge":
            return _clusters_merge(args.source, args.target)
        if args.clusters_command == "split":
            return _clusters_split(args.source, args.query, args.new_name)
    if args.command == "remove":
        return _remove(args.identifier, args.zotero, args.dry_run)
    if args.command == "mark":
        return _mark(args.slug, args.status, args.cluster)
    if args.command == "move":
        return _move(args.slug, args.to_cluster)
    if args.command == "find":
        return _find(args.query, args.cluster, args.status, args.full, args.json, args.limit)
    if args.command == "search":
        return _search(args.query, args.limit, verify=args.verify)
    if args.command == "references":
        return _references(args.identifier, args.limit, args.json)
    if args.command == "cited-by":
        return _cited_by(args.identifier, args.limit, args.json)
    if args.command == "suggest":
        return _suggest(args.identifier, args.top, args.json)
    if args.command == "cite":
        return _cite(args.identifier, args.cluster, args.content_format, args.out)
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
        return _verify(args)
    if args.command == "cleanup":
        return _cleanup_hub(dry_run=args.dry_run)
    if args.command == "synthesize":
        return _synthesize(cluster=args.cluster, graph_colors=args.graph_colors)
    if args.command == "notebooklm":
        if args.notebooklm_command == "login":
            from pathlib import Path as _Path

            from research_hub.notebooklm.session import (
                login_interactive,
                login_interactive_cdp,
            )

            cfg = get_config()
            session_dir = cfg.research_hub_dir / "nlm_sessions" / "default"
            if args.cdp:
                return login_interactive_cdp(
                    session_dir,
                    timeout_sec=args.timeout,
                    chrome_binary=args.chrome_binary,
                    keep_open=args.keep_open,
                )
            chrome_path = _Path(args.chrome_profile_path) if args.chrome_profile_path else None
            return login_interactive(
                session_dir,
                use_system_chrome=args.use_system_chrome,
                timeout_sec=args.timeout,
                from_chrome_profile=args.from_chrome_profile,
                chrome_profile_path=chrome_path,
                chrome_profile_name=args.chrome_profile_name,
            )
        if args.notebooklm_command == "bundle":
            return _notebooklm_bundle(args.cluster)
        if args.notebooklm_command == "upload":
            return _nlm_upload(args.cluster, args.dry_run, args.headless, args.create_if_missing)
        if args.notebooklm_command == "generate":
            return _nlm_generate(args.cluster, args.type, args.headless)

    parser.error(f"Unknown command: {args.command}")
    return 2
