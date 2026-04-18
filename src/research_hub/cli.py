"""Command line entry points for Research Hub."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config, require_config
from research_hub.dedup import DedupIndex, build_from_obsidian, build_from_zotero
from research_hub.operations import add_paper, mark_paper, move_paper, remove_paper
from research_hub.pipeline import run_pipeline
from research_hub.pipeline_repair import repair_cluster
from research_hub.security import safe_join
from research_hub.search import SemanticScholarClient, iter_new_results
from research_hub.search.fallback import (
    DEFAULT_BACKENDS,
    FIELD_PRESETS,
    REGION_PRESETS,
    resolve_backends_for_field,
    resolve_backends_for_region,
)
from research_hub.suggest import PaperInput, suggest_cluster_for_paper, suggest_related_papers
from research_hub.verify import verify_arxiv, verify_doi, verify_paper
from research_hub.vault_search import search_vault
from research_hub.writing import (
    Quote,
    build_inline_citation,
    build_markdown_citation,
    format_paper_meta_from_frontmatter,
    load_all_quotes,
    resolve_paper_meta,
    save_quote,
)


def _config_encrypt_secrets() -> int:
    from research_hub.config import _resolve_config_path
    from research_hub.security.secret_box import encrypt, is_encrypted

    config_path = _resolve_config_path()
    if config_path is None or not config_path.exists():
        print("No config file found")
        return 1
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read config: {exc}", file=sys.stderr)
        return 1
    zotero = data.get("zotero")
    if not isinstance(zotero, dict):
        print("No secrets found to encrypt")
        return 0
    changed = False
    api_key = zotero.get("api_key")
    if isinstance(api_key, str) and api_key and not is_encrypted(api_key):
        encrypted = encrypt(api_key, config_path.parent)
        if encrypted != api_key:
            zotero["api_key"] = encrypted
            changed = True
    if not changed:
        print("No plaintext secrets found")
        return 0
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Encrypted secrets in {config_path}")
    return 0


def _package_dxt(out_path: Path) -> int:
    from research_hub import __version__
    from research_hub.dxt import build_dxt

    path = build_dxt(out_path, __version__)
    print(f"Wrote {path}")
    return 0


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


def _dedup(args) -> int:
    cfg = get_config()
    path = cfg.research_hub_dir / "dedup_index.json"
    index = DedupIndex.load(path)

    if args.dedup_command == "invalidate":
        if not args.doi and not args.path:
            print("Provide --doi or --path")
            return 1
        removed = 0
        if args.doi:
            removed += index.invalidate_doi(args.doi)
        if args.path:
            removed += index.invalidate_obsidian_path(args.path)
        index.save(path)
        print(f"Removed {removed} entries")
        return 0

    if args.dedup_command == "rebuild":
        if args.obsidian_only:
            index.rebuild_from_obsidian(cfg.raw)
        else:
            from research_hub.zotero.client import get_client

            new = DedupIndex.empty()
            for hit in build_from_obsidian(cfg.raw):
                new.add(hit)
            try:
                zot = get_client()
                for hit in build_from_zotero(zot, cfg.zotero_library_id):
                    new.add(hit)
            except Exception as exc:
                print(f"  [warn] Zotero rebuild failed: {exc}")
                print("  Use --obsidian-only to skip Zotero")
            index = new
        index.save(path)
        print(f"Index rebuilt: {len(index.doi_to_hits)} DOIs, {len(index.title_to_hits)} titles")
        return 0

    return 1


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
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.rename(slug, name)
    print(f"{cluster.slug}\t{cluster.name}")
    cache_path = cfg.research_hub_dir / "nlm_cache.json"
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            cache = {}
        if isinstance(cache, dict) and isinstance(cache.get(cluster.slug), dict):
            cache[cluster.slug]["notebook_name"] = name
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    if not cluster.zotero_collection_key:
        return 0
    try:
        from research_hub.zotero.client import get_client

        zotero = get_client()
        collection = zotero.collection(cluster.zotero_collection_key)
        current_name = str(collection.get("data", {}).get("name", "") or "")
        if current_name == name:
            print(f"Zotero collection already named {name!r}")
            return 0
        collection["data"]["name"] = name
        zotero.update_collection(collection)
        print(f"renamed Zotero collection {cluster.zotero_collection_key} to {name!r}")
    except Exception as exc:
        print(f"WARNING: Zotero rename failed: {exc}", file=sys.stderr)
    return 0


def _clusters_delete(slug: str, dry_run: bool, purge_folder: bool = False) -> int:
    cfg = get_config()
    result = ClusterRegistry(cfg.clusters_file).delete(slug, dry_run=dry_run)
    purged: list[str] = []
    if purge_folder and not dry_run:
        for root in (cfg.raw, cfg.hub):
            try:
                target = safe_join(root, slug)
                if target.exists():
                    shutil.rmtree(target)
                    purged.append(str(target))
            except Exception as exc:
                print(f"WARN: could not purge {root}/{slug}: {exc}", file=sys.stderr)
    result["purged_folders"] = purged
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


def _cmd_clusters_analyze(args, cfg) -> int:
    from research_hub.analyze import render_split_suggestion_markdown, suggest_split

    if not args.split_suggestion:
        print("(no analysis type specified; pass --split-suggestion)")
        return 0

    suggestion = suggest_split(
        cfg,
        args.cluster,
        min_community_size=args.min_community_size,
        max_communities=args.max_communities,
    )
    markdown = render_split_suggestion_markdown(suggestion)
    out_path = Path(args.out) if args.out else Path("docs") / f"cluster_autosplit_{args.cluster}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(
        "Analyzed "
        f"{suggestion.paper_count} papers -> {suggestion.community_count} communities "
        f"(modularity={suggestion.modularity_score:.3f}, coverage={suggestion.coverage_fraction:.0%})"
    )
    print(f"Report written to {out_path}")
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


def _add(identifier: str, cluster: str | None, no_zotero: bool, skip_verify: bool) -> int:
    result = add_paper(
        identifier,
        cluster=cluster,
        no_zotero=no_zotero,
        skip_verify=skip_verify,
    )
    if result["status"] == "ok":
        print(f"Added: {result['title'][:70]}")
        print(f"  DOI:  {result['doi']}")
        print(f"  Slug: {result['slug']}")
        return 0
    print(f"Failed: {result.get('reason', 'unknown error')}")
    return 1


def _find(
    query: str,
    cluster: str | None,
    status: str | None,
    full_text: bool,
    emit_json: bool,
    limit: int,
    label: str | None = None,
    label_not: str | None = None,
) -> int:
    if cluster and (label or label_not):
        from research_hub.paper import list_papers_by_label

        cfg = get_config()
        states = list_papers_by_label(cfg, cluster, label=label, label_not=label_not)
        if query:
            lowered = query.lower()
            states = [state for state in states if lowered in state.slug.lower()]
        if emit_json:
            payload = [
                {
                    "slug": state.slug,
                    "cluster": state.cluster_slug,
                    "labels": state.labels,
                    "fit_score": state.fit_score,
                    "fit_reason": state.fit_reason,
                    "labeled_at": state.labeled_at,
                    "status": "",
                }
                for state in states[:limit]
            ]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        for state in states[:limit]:
            print(f"{state.slug}\t{state.cluster_slug}\t{state.labels}\t{state.fit_score or ''}")
        return 0
    results = search_vault(query, cluster=cluster, status=status, full_text=full_text, limit=limit)
    if emit_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    for item in results:
        print(f"{item['slug']}\t{item['title']}\t{item['cluster']}\t{item['status']}")
    return 0


def _label(args) -> int:
    from research_hub.paper import read_labels, set_labels

    cfg = get_config()
    set_list = [label.strip() for label in args.set.split(",") if label.strip()] if args.set else None
    add_list = [label.strip() for label in args.add.split(",") if label.strip()] if args.add else None
    remove_list = [label.strip() for label in args.remove.split(",") if label.strip()] if args.remove else None

    if not any([set_list, add_list, remove_list, args.fit_score is not None, args.fit_reason]):
        state = read_labels(cfg, args.slug)
        if state is None:
            print(f"paper not found: {args.slug}", file=sys.stderr)
            return 2
        print(f"slug: {state.slug}")
        print(f"cluster: {state.cluster_slug}")
        print(f"labels: {state.labels}")
        if state.fit_score is not None:
            print(f"fit_score: {state.fit_score}")
            print(f"fit_reason: {state.fit_reason}")
        print(f"labeled_at: {state.labeled_at}")
        return 0

    try:
        state = set_labels(
            cfg,
            args.slug,
            labels=set_list,
            add=add_list,
            remove=remove_list,
            fit_score=args.fit_score,
            fit_reason=args.fit_reason,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"labels: {state.labels}")
    return 0


def _label_bulk(json_path: str) -> int:
    from research_hub.paper import set_labels

    cfg = get_config()
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assignments = payload.get("assignments", {})
    updated = 0
    for slug, labels in assignments.items():
        set_labels(cfg, slug, labels=list(labels))
        updated += 1
    print(f"updated {updated} paper(s)")
    return 0


def _fit_check_apply_labels(cluster_slug: str) -> int:
    from research_hub.fit_check import rejected_as_label_updates

    cfg = get_config()
    result = rejected_as_label_updates(cfg, cluster_slug)
    print(f"tagged: {len(result['tagged'])}")
    for slug in result["tagged"]:
        print(f"  - {slug}")
    if result["already"]:
        print(f"already deprecated: {len(result['already'])}")
    if result["missing"]:
        print(f"missing from vault: {len(result['missing'])}")
    return 0


def _autofill_emit(cluster_slug: str, out: str | None) -> int:
    from research_hub.autofill import emit_autofill_prompt, find_todo_papers

    cfg = get_config()
    prompt = emit_autofill_prompt(cfg, cluster_slug)
    if out:
        Path(out).write_text(prompt, encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(prompt)
    print(f"autofill candidates: {len(find_todo_papers(cfg, cluster_slug))}", file=sys.stderr)
    return 0


def _autofill_apply(cluster_slug: str, scored_path: str) -> int:
    from research_hub.autofill import apply_autofill

    cfg = get_config()
    scored = json.loads(Path(scored_path).read_text(encoding="utf-8"))
    result = apply_autofill(cfg, cluster_slug, scored)
    print(f"filled: {len(result.filled)}")
    if result.skipped:
        print(f"skipped: {len(result.skipped)}")
    if result.missing:
        print(f"missing: {len(result.missing)}")
    return 0


def _cmd_crystal(args, cfg) -> int:
    from research_hub import crystal

    if args.crystal_command == "emit":
        question_slugs = [item.strip() for item in args.questions.split(",") if item.strip()] if args.questions else None
        prompt = crystal.emit_crystal_prompt(cfg, args.cluster, question_slugs=question_slugs)
        if args.out:
            Path(args.out).write_text(prompt, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(prompt)
        return 0
    if args.crystal_command == "apply":
        scored = json.loads(Path(args.scored).read_text(encoding="utf-8"))
        result = crystal.apply_crystals(cfg, args.cluster, scored)
        print(f"written: {len(result.written)}, replaced: {len(result.replaced)}, skipped: {len(result.skipped)}")
        if result.errors:
            for error in result.errors:
                print(f"  ERROR: {error}", file=sys.stderr)
            return 1
        return 0
    if args.crystal_command == "list":
        crystals = crystal.list_crystals(cfg, args.cluster)
        if not crystals:
            print("(no crystals yet; generate via `research-hub crystal emit`)")
            return 0
        for item in crystals:
            print(f"{item.question_slug:25s}  {item.tldr[:80]}")
        return 0
    if args.crystal_command == "read":
        item = crystal.read_crystal(cfg, args.cluster, args.slug)
        if item is None:
            print(f"crystal not found: {args.slug}", file=sys.stderr)
            return 1
        print(item.tldr if args.level == "tldr" else item.full if args.level == "full" else item.gist)
        return 0
    if args.crystal_command == "check":
        staleness = crystal.check_staleness(cfg, args.cluster)
        if not staleness:
            print("(no crystals to check)")
            return 0
        for slug, item in staleness.items():
            marker = "STALE" if item.stale else "fresh"
            print(f"{slug:25s}  {marker}  delta={item.delta_ratio:.0%}  +{len(item.added_papers)}/-{len(item.removed_papers)}")
        return 0
    raise ValueError(f"unknown crystal command: {args.crystal_command}")


def _cmd_memory(args, cfg) -> int:
    from research_hub.memory import (
        apply_memory,
        emit_memory_prompt,
        list_claims,
        list_entities,
        list_methods,
        read_memory,
    )

    if args.memory_command == "emit":
        print(emit_memory_prompt(cfg, args.cluster))
        return 0
    if args.memory_command == "apply":
        scored = json.loads(Path(args.scored).read_text(encoding="utf-8"))
        result = apply_memory(cfg, args.cluster, scored)
        print(f"entities={result.entity_count} claims={result.claim_count} methods={result.method_count}")
        print(f"written: {result.written_path}")
        for error in result.errors:
            print(f"  ! {error}", file=sys.stderr)
        return 0
    if args.memory_command == "list":
        entities = list_entities(cfg, args.cluster)
        claims = list_claims(cfg, args.cluster)
        methods = list_methods(cfg, args.cluster)
        if args.kind == "entities":
            for item in entities:
                print(f"{item.slug}\t{item.type}\t{item.name}")
            return 0
        if args.kind == "claims":
            for item in claims:
                print(f"[{item.confidence}] {item.slug}: {item.text[:80]}")
            return 0
        if args.kind == "methods":
            for item in methods:
                print(f"{item.slug}\t{item.family}\t{item.name}")
            return 0
        print("[entities]")
        for item in entities:
            print(f"{item.slug}\t{item.type}\t{item.name}")
        print()
        print("[claims]")
        for item in claims:
            print(f"[{item.confidence}] {item.slug}: {item.text[:80]}")
        print()
        print("[methods]")
        for item in methods:
            print(f"{item.slug}\t{item.family}\t{item.name}")
        return 0
    if args.memory_command == "read":
        memory = read_memory(cfg, args.cluster)
        if memory is None:
            print(f"No memory found for cluster: {args.cluster}", file=sys.stderr)
            return 1
        print(json.dumps(memory.to_dict(), indent=2, ensure_ascii=False))
        return 0
    raise ValueError(f"unknown memory command: {args.memory_command}")


def _paper_command(args) -> int:
    if args.paper_command == "prune":
        from research_hub.paper import prune_cluster

        cfg = get_config()
        result = prune_cluster(
            cfg,
            args.cluster,
            label=args.label,
            archive=not args.delete,
            delete=args.delete,
            dry_run=args.dry_run,
            include_zotero=args.zotero,
        )
        if args.dry_run:
            print(f"dry run - would affect {len(result['would_affect'])} paper(s):")
            for slug in result["would_affect"]:
                print(f"  - {slug}")
        else:
            mode = result["mode"]
            count = len(result["moved"] if mode == "archive" else result["deleted"])
            print(f"{mode}d {count} paper(s) with label {args.label!r}")
        return 0
    if args.paper_command == "unarchive":
        from research_hub.paper import unarchive

        cfg = get_config()
        try:
            result = unarchive(cfg, args.cluster, args.slug)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"restored: {result['restored']}")
        print(f"path: {result['path']}")
        return 0
    return 2


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


def _import_folder_command(args) -> int:
    from research_hub.importer import import_folder

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
    )
    print(f"\nImport summary ({'DRY RUN' if args.dry_run else 'WRITTEN'}):")
    print(f"  imported:  {report.imported_count}")
    print(f"  skipped:   {report.skipped_count}")
    print(f"  failed:    {report.failed_count}")
    if report.failed_count > 0:
        print("\nFailures:")
        for entry in report.entries:
            if entry.status == "failed":
                print(f"  {entry.path.name}: {entry.error}")
    return 0 if report.failed_count == 0 else 1


def _synthesize(cluster: str | None, graph_colors: bool) -> int:
    from research_hub.vault.graph_config import refresh_graph_from_vault
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
        print(f"Updated graph.json with {refresh_graph_from_vault(cfg)} color groups")

    return 0


def _collect_paper_meta_for_cluster(cfg, cluster: str) -> list[dict]:
    cluster_dir = cfg.raw / cluster
    if not cluster_dir.exists():
        raise FileNotFoundError(f"Cluster folder not found: {cluster_dir}")
    return [format_paper_meta_from_frontmatter(path) for path in sorted(cluster_dir.glob("*.md"))]


def _cite(
    identifier: str | None,
    cluster: str | None,
    content_format: str,
    out_path: str | None,
    *,
    inline: bool = False,
    markdown: bool = False,
    style: str = "apa",
) -> int:
    """Export BibTeX / BibLaTeX / RIS / CSL-JSON for a paper or cluster.

    Resolves the identifier (DOI, slug, or raw title) to one or more
    Zotero item keys via the dedup index and vault frontmatter, then
    calls ZoteroDualClient.get_formatted to fetch each entry. Concatenates
    results and writes to stdout or --out file.
    """
    from research_hub.dedup import normalize_doi
    from research_hub.zotero.client import ZoteroDualClient

    cfg = get_config()

    if inline or markdown:
        if cluster:
            try:
                metas = _collect_paper_meta_for_cluster(cfg, cluster)
            except FileNotFoundError as exc:
                print(str(exc))
                return 1
            rendered = []
            for meta in metas:
                if markdown:
                    rendered.append(build_markdown_citation(meta))
                else:
                    rendered.append(build_inline_citation(meta, style=style))
            body = "\n".join(item for item in rendered if item)
            if not body:
                print(f"No notes found in cluster '{cluster}'")
                return 1
            if out_path:
                Path(out_path).write_text(body + "\n", encoding="utf-8")
                print(f"Wrote {len(rendered)} citations to {out_path}")
            else:
                print(body)
            return 0

        if not identifier:
            print("Either a positional <identifier> or --cluster <slug> is required")
            return 2
        meta = resolve_paper_meta(cfg, identifier)
        if not meta:
            print(f"Could not resolve identifier '{identifier}'")
            return 1
        body = build_markdown_citation(meta) if markdown else build_inline_citation(meta, style=style)
        if out_path:
            Path(out_path).write_text(body + "\n", encoding="utf-8")
            print(f"Wrote citation to {out_path}")
        else:
            print(body)
        return 0

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


def _quote_add(slug: str, page: str, text: str, context: str) -> int:
    cfg = get_config()
    meta = resolve_paper_meta(cfg, slug)
    quote = Quote(
        slug=str(meta.get("slug", slug) or slug),
        doi=str(meta.get("doi", "") or ""),
        title=str(meta.get("title", slug) or slug),
        authors=str(meta.get("authors", "") or ""),
        year=str(meta.get("year", "") or ""),
        cluster_slug=str(meta.get("topic_cluster", "") or ""),
        page=page,
        text=text,
        context_note=context,
    )
    path = save_quote(cfg, quote)
    print(path)
    return 0


def _quote_list(cluster: str | None) -> int:
    cfg = get_config()
    quotes = load_all_quotes(cfg)
    if cluster:
        quotes = [quote for quote in quotes if quote.cluster_slug == cluster]
    for quote in quotes:
        text = re.sub(r"\s+", " ", quote.text).strip()
        preview = text[:80] + ("..." if len(text) > 80 else "")
        print(f"{quote.slug}\t{quote.captured_at}\t{quote.page}\t{preview}")
    return 0


def _quote_remove(slug: str, at: str) -> int:
    cfg = get_config()
    path = cfg.research_hub_dir / "quotes" / f"{slug}.md"
    if not path.exists():
        print(f"Quote file not found: {path}")
        return 1
    original = path.read_text(encoding="utf-8")
    blocks = list(re.finditer(r"^---\n.*?\n---\n.*?(?:\n(?=---\n)|\Z)", original, re.DOTALL | re.MULTILINE))
    kept: list[str] = []
    removed = 0
    for match in blocks:
        block = match.group(0).strip()
        if f"captured_at: {at}" in block and removed == 0:
            removed += 1
            continue
        kept.append(block)
    if removed == 0:
        print(f"No quote block found for {slug} at {at}")
        return 1
    if kept:
        path.write_text("\n\n".join(kept) + "\n", encoding="utf-8")
    else:
        path.unlink()
    print(f"Removed quote {slug} at {at}")
    return 0


def _compose_draft(
    cluster_slug: str,
    outline: str | None,
    quotes: str | None,
    style: str,
    include_bibliography: bool,
    out: str | None,
) -> int:
    from research_hub.drafting import DraftingError, compose_draft_from_cli

    cfg = get_config()
    try:
        result = compose_draft_from_cli(
            cfg,
            cluster_slug,
            outline=outline,
            quote_slugs=quotes,
            style=style,
            include_bibliography=include_bibliography,
            out=out,
        )
    except DraftingError as exc:
        print(f"Draft composition failed: {exc}")
        return 1
    print(f"Draft written to {result.path}")
    print(
        f"  {result.quote_count} quotes, {result.cited_paper_count} cited papers, "
        f"{result.section_count} sections"
    )
    return 0


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


def _search(
    query: str,
    limit: int,
    verify: bool = False,
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    min_citations: int = 0,
    backends: tuple[str, ...] = ("openalex", "arxiv", "semantic-scholar", "crossref", "dblp"),
    exclude_types: tuple[str, ...] = (),
    exclude_terms: tuple[str, ...] = (),
    min_confidence: float = 0.0,
    rank_by: str = "smart",
    backend_trace: bool = False,
    emit_json: bool = False,
    to_papers_input: bool = False,
    cluster_slug: str | None = None,
) -> int:
    cfg = get_config()
    index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    from research_hub.search import search_papers as _search_papers

    results = _search_papers(
        query,
        limit=limit,
        year_from=year_from,
        year_to=year_to,
        min_citations=min_citations,
        backends=backends,
        exclude_types=exclude_types,
        exclude_terms=exclude_terms,
        min_confidence=min_confidence,
        rank_by=rank_by,
        backend_trace=backend_trace,
    )
    from research_hub.dedup import normalize_doi

    ingested = {normalize_doi(doi) for doi in index.doi_to_hits.keys() if doi}
    results = [r for r in results if normalize_doi(r.doi) not in ingested]

    if to_papers_input:
        _emit_papers_input_json(results, cluster_slug)
        return 0
    if emit_json:
        print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
        return 0
    for result in results:
        line = (
            f"{result.title}\t{result.doi or result.arxiv_id}\t"
            f"{result.year or '????'}\t{result.citation_count}\t{result.source}"
        )
        if verify:
            verified = bool(result.doi) and verify_doi(result.doi).ok
            line += "\tVERIFIED" if verified else "\tUNVERIFIED"
        print(line)
    return 0


def _emit_papers_input_json(results: list, cluster_slug: str | None) -> None:
    """Print a flat papers_input.json list to stdout."""
    from research_hub.discover import _to_papers_input

    papers = _to_papers_input([asdict(result) for result in results], cluster_slug)
    print(json.dumps(papers, indent=2, ensure_ascii=False))


def _parse_year_range(spec: str | None) -> tuple[int | None, int | None]:
    if spec is None:
        return (None, None)
    text = spec.strip()
    if not text:
        raise SystemExit(f"invalid --year spec: {spec}")
    if re.fullmatch(r"\d{4}", text):
        year = int(text)
        return (year, year)
    if re.fullmatch(r"\d{4}-", text):
        return (int(text[:4]), None)
    if re.fullmatch(r"-\d{4}", text):
        return (None, int(text[1:]))
    if re.fullmatch(r"\d{4}-\d{4}", text):
        start, end = text.split("-", 1)
        return (int(start), int(end))
    raise SystemExit(f"invalid --year spec: {spec}")


def _parse_csv_terms(spec: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in spec.split(",") if item.strip())


def _parse_negative_terms(spec: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in re.split(r"[\s,]+", spec) if item.strip())


def _parse_seed_dois(seed_dois: str, seed_dois_file: str | None) -> tuple[str, ...]:
    values: list[str] = []
    if seed_dois:
        values.extend(item.strip() for item in seed_dois.split(",") if item.strip())
    if seed_dois_file:
        for line in Path(seed_dois_file).read_text(encoding="utf-8").splitlines():
            doi = line.strip()
            if doi and not doi.startswith("#"):
                values.append(doi)
    return tuple(values)


def _enrich(
    candidates: list[str],
    *,
    backends: tuple[str, ...],
    to_papers_input: bool = False,
    cluster_slug: str | None = None,
) -> int:
    items = list(candidates)
    if not items or items == ["-"]:
        items = [line.strip() for line in sys.stdin if line.strip()]
    if not items:
        print("No candidates provided.", file=sys.stderr)
        return 2

    from research_hub.search import enrich_candidates

    resolved = enrich_candidates(items, backends=backends)
    hits = [r for r in resolved if r is not None]

    if to_papers_input:
        _emit_papers_input_json(hits, cluster_slug)
        return 0

    print(json.dumps([asdict(r) for r in hits], indent=2, ensure_ascii=False))
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


def _dashboard(
    open_browser: bool,
    watch: bool = False,
    refresh: int = 10,
    rich_bibtex: bool = False,
    screenshot: str | None = None,
    out: str | None = None,
    out_dir: str | None = None,
    scale: float = 2.0,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    full_page: bool = False,
) -> int:
    if screenshot:
        from research_hub.dashboard.screenshot import (
            PlaywrightNotInstalled,
            screenshot_all,
            screenshot_dashboard,
        )

        try:
            cfg = require_config()
            if screenshot == "all":
                if not out_dir:
                    print("ERROR: --out-dir required with --screenshot all", file=sys.stderr)
                    return 2
                paths = screenshot_all(
                    cfg,
                    out_dir=Path(out_dir),
                    scale=scale,
                    viewport_width=viewport_width,
                    viewport_height=viewport_height,
                    full_page=full_page,
                )
                for path in paths:
                    print(f"wrote {path}")
                return 0
            if not out:
                print("ERROR: --out required with single-tab --screenshot", file=sys.stderr)
                return 2
            path = screenshot_dashboard(
                cfg,
                tab=screenshot,
                out=Path(out),
                scale=scale,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                full_page=full_page,
            )
            print(f"wrote {path}")
            return 0
        except PlaywrightNotInstalled as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    if watch:
        from research_hub.dashboard import watch_dashboard

        watch_dashboard(
            open_browser=open_browser,
            refresh_seconds=refresh,
            rich_bibtex=rich_bibtex,
        )
        return 0

    from research_hub.dashboard import generate_dashboard
    from research_hub.vault.graph_config import refresh_graph_from_vault

    cfg = get_config()
    out_path = generate_dashboard(open_browser=open_browser, rich_bibtex=rich_bibtex)
    try:
        group_count = refresh_graph_from_vault(cfg)
        print(f"Graph colors refreshed ({group_count} groups)")
    except Exception as exc:
        print(f"WARNING: graph color refresh failed: {exc}", file=sys.stderr)
    print(f"Dashboard written to {out_path}")
    if open_browser:
        print("Opening in browser...")
    return 0


def _cmd_serve(args, cfg) -> int:
    if args.dashboard and args.allow_external:
        print("+" + "-" * 62 + "+")
        print("| DASHBOARD BOUND TO 0.0.0.0" + " " * 34 + "|")
        print("|" + " " * 62 + "|")
        print("| Anyone on your network can:" + " " * 32 + "|")
        print("| - View your research data" + " " * 34 + "|")
        print("| - Execute whitelisted CLI commands" + " " * 24 + "|")
        print("|" + " " * 62 + "|")
        print("| Use only on trusted networks (home LAN, VPN)." + " " * 15 + "|")
        print("|" + " " * 62 + "|")
        if args.yes:
            print("| Continuing immediately because --yes was passed." + " " * 15 + "|")
        else:
            print("| Continuing in 5 seconds - Ctrl+C to abort." + " " * 17 + "|")
        print("+" + "-" * 62 + "+")
        if not args.yes:
            time.sleep(5)
    if args.dashboard:
        from research_hub.dashboard.http_server import serve_dashboard

        serve_dashboard(
            cfg,
            host=args.host,
            port=args.port,
            allow_external=args.allow_external,
            open_browser=not args.no_browser,
        )
        return 0

    from research_hub.mcp_server import main as mcp_main

    mcp_main()
    return 0


def _get_claude_desktop_config_path() -> Path:
    import platform

    if platform.system() == "Windows":
        config_dir = Path.home() / "AppData" / "Roaming" / "Claude"
    elif platform.system() == "Darwin":
        config_dir = Path.home() / "Library" / "Application Support" / "Claude"
    else:
        config_dir = Path.home() / ".config" / "claude"
    return config_dir / "claude_desktop_config.json"


def _install_mcp(config_path: Path | None = None) -> int:
    """Auto-write research-hub MCP server entry to Claude Desktop config."""
    config_path = config_path or _get_claude_desktop_config_path()

    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            config = {}

    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        config["mcpServers"] = servers

    if "research-hub" in servers:
        print(f"research-hub already configured in {config_path}")
        print("  No changes made.")
        return 0

    servers["research-hub"] = {
        "command": "research-hub",
        "args": ["serve"],
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"MCP server added to {config_path}")
    print("  Restart Claude Desktop to activate.")
    print("  Then ask Claude: 'list my research clusters'")
    return 0


def _cmd_install(args, cfg=None) -> int:
    if getattr(args, "mcp", False):
        return _install_mcp()

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


def _cmd_where(args) -> int:
    """Print config/vault/data locations without external API calls."""
    from research_hub.config import _resolve_config_path, get_config

    config_path = _resolve_config_path()
    print()

    if not config_path:
        print("  Config:   (not found)")
        print("  Vault:    (not configured)")
        print()
        print("  Run: research-hub init")
        return 1

    print(f"  Config:   {config_path}")

    try:
        cfg = get_config()
    except Exception as exc:
        print(f"  Vault:    (error: {exc})")
        return 1

    vault = Path(cfg.root)
    print(f"  Vault:    {vault}")

    raw = Path(cfg.raw)
    note_count = len(list(raw.rglob("*.md"))) if raw.exists() else 0

    clusters_file = Path(cfg.research_hub_dir) / "clusters.yaml"
    cluster_count = 0
    if clusters_file.exists():
        try:
            cluster_count = len(ClusterRegistry(clusters_file).list())
        except Exception:
            pass

    print(f"  Notes:    {note_count} papers across {cluster_count} cluster(s)")

    hub = Path(cfg.hub)
    crystal_count = len(list(hub.rglob("crystals/*.md"))) if hub.exists() else 0
    if crystal_count:
        print(f"  Crystals: {crystal_count} pre-computed answers")

    mcp_config = _get_claude_desktop_config_path()
    if mcp_config.exists():
        try:
            mcp_data = json.loads(mcp_config.read_text(encoding="utf-8"))
            if "research-hub" in mcp_data.get("mcpServers", {}):
                print(f"  MCP:      {mcp_config} (configured)")
            else:
                print(f"  MCP:      {mcp_config} (not configured - run: research-hub install --mcp)")
        except Exception:
            print(f"  MCP:      {mcp_config} (error reading)")
    else:
        print("  MCP:      (not found - run: research-hub install --mcp)")

    dashboard = Path(cfg.research_hub_dir) / "dashboard.html"
    if dashboard.exists():
        print(f"  Dashboard: {dashboard}")

    if raw.exists():
        print()
        print("  Vault folders:")
        for cluster_dir in sorted(raw.iterdir()):
            if cluster_dir.is_dir():
                paper_count = len(list(cluster_dir.glob("*.md")))
                topics_dir = cluster_dir / "topics"
                topic_count = len(list(topics_dir.glob("*.md"))) if topics_dir.exists() else 0
                extra = f" + {topic_count} sub-topics" if topic_count else ""
                print(f"    raw/{cluster_dir.name}/  ({paper_count} papers{extra})")

    print()
    return 0


def _vault_graph_colors(refresh: bool) -> int:
    from research_hub.vault.graph_config import refresh_graph_from_vault

    if not refresh:
        print("Nothing to do. Pass --refresh.", file=sys.stderr)
        return 2
    cfg = get_config()
    count = refresh_graph_from_vault(cfg)
    print(f"Refreshed graph colors: {count} groups")
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


def _nlm_download(cluster_slug: str, artifact_type: str, headless: bool) -> int:
    from research_hub.notebooklm.upload import download_briefing_for_cluster

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        raise ValueError(f"Cluster not found: {cluster_slug}")

    report = download_briefing_for_cluster(cluster, cfg, headless=headless)
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


def _fit_check_emit(cluster_slug: str, candidates_path: str, definition: str | None, out: str | None) -> int:
    from research_hub.fit_check import emit_prompt

    cfg = get_config()
    candidates = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    prompt = emit_prompt(cluster_slug, candidates, definition=definition, cfg=cfg)
    if out:
        Path(out).write_text(prompt, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(prompt)
    return 0


def _fit_check_apply(
    cluster_slug: str,
    candidates_path: str,
    scored_path: str,
    threshold: int,
    auto_threshold: bool,
    out: str | None,
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
    print(f"fit-check {report.summary()}", file=sys.stderr)
    output = json.dumps([item.to_dict() for item in report.accepted], indent=2, ensure_ascii=False)
    if out:
        Path(out).write_text(output, encoding="utf-8")
    else:
        print(output)
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


def _discover_new(args) -> int:
    from research_hub.discover import discover_new

    cfg = get_config()
    year_from, year_to = _parse_year_range(args.year) if args.year else (None, None)
    backends = tuple(item.strip() for item in args.backend.split(",") if item.strip()) if args.backend else None
    exclude_types = _parse_csv_terms(args.exclude_type)
    exclude_terms = _parse_negative_terms(args.exclude)
    seed_dois = _parse_seed_dois(args.seed_dois, args.seed_dois_file)
    expand_from = tuple(item.strip() for item in args.expand_from.split(",") if item.strip())
    state, prompt = discover_new(
        cfg,
        args.cluster,
        args.query,
        year_from=year_from,
        year_to=year_to,
        min_citations=args.min_citations,
        backends=backends,
        field=args.field,
        region=args.region,
        limit=args.limit,
        definition=args.definition,
        exclude_types=exclude_types,
        exclude_terms=exclude_terms,
        min_confidence=args.min_confidence,
        rank_by=args.rank_by,
        from_variants=args.from_variants,
        expand_auto=args.expand_auto,
        expand_from=expand_from,
        expand_hops=args.expand_hops,
        seed_dois=seed_dois,
        include_existing=args.include_existing,
    )
    if args.prompt_out:
        Path(args.prompt_out).write_text(prompt, encoding="utf-8")
        print(f"wrote {args.prompt_out}", file=sys.stderr)
    else:
        print(prompt)
    print(
        f"[discover] stashed {state.candidate_count} candidates for {args.cluster}. "
        f"Score the prompt, save to scored.json, then run `discover continue`.",
        file=sys.stderr,
    )
    return 0


def _discover_continue(args) -> int:
    from research_hub.discover import discover_continue

    cfg = get_config()
    scored = json.loads(Path(args.scored).read_text(encoding="utf-8"))
    out_path = Path(args.out) if args.out else None
    state, papers_input_path = discover_continue(
        cfg,
        args.cluster,
        scored,
        threshold=args.threshold,
        auto_threshold=args.auto_threshold,
        out_path=out_path,
    )
    print(
        f"[discover] accepted {state.accepted_count} / {state.candidate_count} "
        f"(rejected {state.rejected_count}, threshold {state.threshold})",
        file=sys.stderr,
    )
    print(f"papers_input.json: {papers_input_path}")
    return 0


def _discover_status(args) -> int:
    from research_hub.discover import discover_status

    cfg = get_config()
    state = discover_status(cfg, args.cluster)
    if state is None:
        print(f"no discover state for cluster {args.cluster}")
        return 1
    print(f"cluster: {state.cluster_slug}")
    print(f"stage:   {state.stage}")
    print(f"query:   {state.query}")
    print(f"candidates: {state.candidate_count}")
    print(f"variations_used: {state.variations_used}")
    print(f"expanded_from: {state.expanded_from}")
    print(f"seed_dois: {state.seed_dois}")
    print(f"deduped_against_cluster: {state.deduped_against_cluster}")
    if state.stage == "done":
        print(f"accepted: {state.accepted_count} / {state.candidate_count}")
        print(f"rejected: {state.rejected_count}")
        suffix = " (auto)" if state.auto_threshold else ""
        print(f"threshold: {state.threshold}{suffix}")
    return 0


def _discover_variants(args) -> int:
    from research_hub.discover import emit_variation_prompt

    cfg = get_config()
    prompt = emit_variation_prompt(cfg, args.cluster, args.query, target_count=args.count)
    if args.out:
        Path(args.out).write_text(prompt, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(prompt)
    return 0


def _discover_clean(args) -> int:
    from research_hub.discover import discover_clean

    cfg = get_config()
    removed = discover_clean(cfg, args.cluster)
    if removed:
        print(f"removed discover state for {args.cluster}")
    else:
        print(f"no discover state for {args.cluster}")
    return 0


def _fit_check_drift(cluster_slug: str, threshold: int) -> int:
    from research_hub.fit_check import drift_check

    cfg = get_config()
    result = drift_check(cfg, cluster_slug, threshold=threshold)
    print(result["prompt"])
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
    parser = argparse.ArgumentParser(
        prog="research-hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Start here ->\n\n"
            "  $ research-hub init           # interactive setup wizard\n"
            "  $ research-hub doctor         # verify everything is wired\n"
            "  $ research-hub where          # show vault + config paths\n"
            "  $ research-hub serve --dashboard  # open live dashboard\n"
            "  $ research-hub install --mcp  # wire into Claude Desktop\n\n"
            "Docs: https://github.com/WenyuChiou/research-hub\n"
        ),
    )
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
    init_parser.add_argument(
        "--persona",
        choices=["researcher", "analyst", "humanities", "internal"],
        default=None,
        help="researcher|humanities use Zotero; analyst|internal skip Zotero",
    )
    init_parser.add_argument(
        "--field",
        choices=sorted(FIELD_PRESETS.keys()),
        help="Field-aware onboarding wizard mode",
    )
    init_parser.add_argument("--cluster", help="Pre-fill cluster slug")
    init_parser.add_argument("--name", help="Pre-fill cluster display name")
    init_parser.add_argument("--query", help="Pre-fill search query")
    init_parser.add_argument("--definition", help="Pre-fill cluster definition")

    subparsers.add_parser("doctor", help="Health check for research-hub installation")

    config_parser = subparsers.add_parser("config", help="Config maintenance commands")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser(
        "encrypt-secrets",
        help="Encrypt plaintext sensitive values in config.json",
    )

    examples_parser = subparsers.add_parser(
        "examples",
        help="Browse and copy bundled cluster examples",
    )
    examples_sub = examples_parser.add_subparsers(dest="examples_command")
    examples_sub.add_parser("list", help="List bundled example clusters")
    examples_show = examples_sub.add_parser("show", help="Show one example's full definition")
    examples_show.add_argument("name")
    examples_copy = examples_sub.add_parser("copy", help="Copy an example into your clusters")
    examples_copy.add_argument("name")
    examples_copy.add_argument("--cluster", help="Override the cluster slug")

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
    install_parser.add_argument(
        "--mcp",
        action="store_true",
        help="Auto-configure Claude Desktop MCP server connection",
    )

    subparsers.add_parser(
        "where",
        help="Show where research-hub stores config, vault, and data",
    )

    dxt_parser = subparsers.add_parser(
        "package-dxt",
        help="Build a .dxt MCP extension archive for Claude Desktop",
    )
    dxt_parser.add_argument("--out", type=Path, default=Path("research-hub.dxt"))

    ask_parser = subparsers.add_parser(
        "ask",
        help="Ask a natural-language question about a cluster (task-level, v0.33+)",
    )
    ask_parser.add_argument("cluster", help="Cluster slug")
    ask_parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="Natural-language question (optional; omitting returns digest)",
    )
    ask_parser.add_argument(
        "--detail",
        choices=["tldr", "gist", "full"],
        default="gist",
        help="Answer detail level (default: gist)",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start MCP stdio server or live dashboard HTTP server",
    )
    serve_parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Run the live dashboard HTTP server instead of MCP stdio",
    )
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Allow binding non-loopback host (power-user only)",
    )
    serve_parser.add_argument("--no-browser", action="store_true")
    serve_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the external-bind warning delay when used with --allow-external",
    )

    run_parser = subparsers.add_parser("run", help="Run the research pipeline")
    run_parser.add_argument("--topic", default=None, help="Pipeline topic context")
    run_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to process")
    run_parser.add_argument("--dry-run", action="store_true", help="Validate config and inputs only")
    run_parser.add_argument("--cluster", default=None, help="Cluster slug for ingestion")
    run_parser.add_argument("--query", default=None, help="Query text")
    run_parser.add_argument(
        "--no-fit-check-auto-labels",
        action="store_true",
        help="Skip auto-labeling papers from fit-check score after ingest",
    )
    run_parser.add_argument(
        "--allow-library-duplicates",
        action="store_true",
        help="Bypass Zotero library duplicate blocking and allow re-ingest",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Run ingestion")
    ingest_parser.add_argument("--cluster", default=None, help="Cluster slug for ingestion")
    ingest_parser.add_argument("--query", default=None, help="Query text")
    ingest_parser.add_argument("--dry-run", action="store_true", help="Validate config and inputs only")
    ingest_parser.add_argument(
        "--no-fit-check-auto-labels",
        action="store_true",
        help="Skip auto-labeling papers from fit-check score after ingest",
    )
    ingest_parser.add_argument(
        "--allow-library-duplicates",
        action="store_true",
        help="Bypass Zotero library duplicate blocking and allow re-ingest",
    )
    ingest_parser.add_argument(
        "--fit-check",
        action="store_true",
        help=(
            "Require a valid .fit_check_rejected.json sidecar from a prior `fit-check apply` run, "
            "and enforce the threshold during ingest"
        ),
    )
    ingest_parser.add_argument(
        "--fit-check-threshold",
        type=int,
        default=3,
        help="Minimum score (0-5) to keep a paper when --fit-check is on",
    )

    import_folder_parser = subparsers.add_parser(
        "import-folder",
        help="Walk a folder and ingest local files as document notes",
    )
    import_folder_parser.add_argument("folder", help="Path to source folder (recursive)")
    import_folder_parser.add_argument("--cluster", required=True, help="Target cluster slug")
    import_folder_parser.add_argument(
        "--extensions",
        default="pdf,md,txt,docx,url",
        help="Comma-separated file extensions to ingest",
    )
    import_folder_parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-import even if content hash matches an existing imported note",
    )
    import_folder_parser.add_argument(
        "--use-graphify",
        action="store_true",
        help="Run graphify post-processing if graphify_bridge is available",
    )
    import_folder_parser.add_argument(
        "--graphify-graph",
        metavar="PATH",
        default=None,
        help=(
            "Path to pre-built graphify-out/graph.json. Adds subtopics frontmatter "
            "to imported notes based on Leiden community detection from the graph. "
            "Run `/graphify <folder>` in Claude Code first to produce graph.json."
        ),
    )
    import_folder_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without writing notes",
    )

    for parser_with_verify in (run_parser, ingest_parser):
        parser_with_verify.add_argument(
            "--no-verify",
            dest="verify",
            action="store_false",
            default=True,
            help="Skip DOI/arxiv HTTP verification (default: verify on)",
        )

    subparsers.add_parser("index", help="Rebuild dedup_index.json from Zotero and Obsidian")

    dedup_parser = subparsers.add_parser(
        "dedup",
        help="Manage the dedup index (invalidate stale entries, rebuild)",
    )
    dedup_subparsers = dedup_parser.add_subparsers(dest="dedup_command", required=True)
    invalidate_parser = dedup_subparsers.add_parser(
        "invalidate",
        help="Remove a DOI or path from the dedup index",
    )
    invalidate_parser.add_argument("--doi", default=None)
    invalidate_parser.add_argument("--path", default=None, help="Obsidian path to invalidate")
    rebuild_parser = dedup_subparsers.add_parser(
        "rebuild",
        help="Rebuild the dedup index",
    )
    rebuild_parser.add_argument(
        "--obsidian-only",
        action="store_true",
        help="Only rescan Obsidian (skip Zotero - useful when API is down)",
    )

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
    delete_parser.add_argument(
        "--purge-folder",
        action="store_true",
        help="Also delete <vault>/raw/<slug>/ and <vault>/hub/<slug>/ folders (destructive)",
    )
    merge_parser = clusters_subparsers.add_parser("merge", help="Merge two clusters")
    merge_parser.add_argument("source", help="Source cluster slug (will be removed)")
    merge_parser.add_argument("--into", required=True, dest="target", help="Target cluster slug")
    split_parser = clusters_subparsers.add_parser("split", help="Split a cluster")
    split_parser.add_argument("source", help="Source cluster slug")
    split_parser.add_argument("--query", required=True, help="Keywords for the new sub-cluster")
    split_parser.add_argument("--new-name", required=True, help="Display name for new cluster")
    analyze_parser = clusters_subparsers.add_parser(
        "analyze",
        help="Analyze a cluster and produce split suggestions",
    )
    analyze_parser.add_argument("--cluster", required=True)
    analyze_parser.add_argument("--split-suggestion", action="store_true")
    analyze_parser.add_argument("--min-community-size", type=int, default=8)
    analyze_parser.add_argument("--max-communities", type=int, default=8)
    analyze_parser.add_argument(
        "--out",
        default=None,
        help="Output markdown path (default: docs/cluster_autosplit_<slug>.md)",
    )
    rebind_parser = clusters_subparsers.add_parser(
        "rebind", help="Detect orphan papers and propose cluster bindings"
    )
    rebind_parser.add_argument("--emit", action="store_true", help="Emit a rebind proposal report to stdout")
    rebind_parser.add_argument("--apply", type=Path, help="Apply moves from a previously emitted report file")
    rebind_parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually move files (default is dry-run)",
    )

    topic_parser = subparsers.add_parser(
        "topic",
        help="Manage cluster topic overview + sub-topic notes",
    )
    topic_subparsers = topic_parser.add_subparsers(dest="topic_command")
    topic_scaffold = topic_subparsers.add_parser("scaffold", help="Create the overview template file")
    topic_scaffold.add_argument("--cluster", required=True)
    topic_scaffold.add_argument("--force", action="store_true", help="Overwrite if exists")
    topic_digest = topic_subparsers.add_parser("digest", help="Emit the cluster digest for an AI to read")
    topic_digest.add_argument("--cluster", required=True)
    topic_digest.add_argument("--out", help="Write digest to this file instead of stdout")
    topic_show = topic_subparsers.add_parser("show", help="Print the current overview markdown")
    topic_show.add_argument("--cluster", required=True)
    topic_propose = topic_subparsers.add_parser(
        "propose",
        help="Emit the sub-topic proposal prompt for an AI",
    )
    topic_propose.add_argument("--cluster", required=True)
    topic_propose.add_argument("--target-count", type=int, default=5)
    topic_propose.add_argument("--out")
    topic_assign = topic_subparsers.add_parser("assign", help="Assign papers to sub-topics")
    topic_assign_sub = topic_assign.add_subparsers(dest="assign_command")
    topic_assign_emit = topic_assign_sub.add_parser("emit", help="Emit the assignment prompt")
    topic_assign_emit.add_argument("--cluster", required=True)
    topic_assign_emit.add_argument("--subtopics", required=True, help="Path to proposed JSON")
    topic_assign_emit.add_argument("--out")
    topic_assign_apply = topic_assign_sub.add_parser(
        "apply",
        help="Apply AI assignments to paper frontmatter",
    )
    topic_assign_apply.add_argument("--cluster", required=True)
    topic_assign_apply.add_argument("--assignments", required=True, help="Path to assignments JSON")
    topic_build = topic_subparsers.add_parser(
        "build",
        help="Generate topics/NN_<slug>.md files from frontmatter",
    )
    topic_build.add_argument("--cluster", required=True)
    topic_list = topic_subparsers.add_parser(
        "list",
        help="List existing sub-topic notes with paper counts",
    )
    topic_list.add_argument("--cluster", required=True)

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

    add_parser = subparsers.add_parser(
        "add",
        help="Fetch a paper by DOI/arXiv ID and ingest it (one-shot)",
    )
    add_parser.add_argument("identifier", help="DOI or arXiv ID")
    add_parser.add_argument("--cluster", default=None, help="Target cluster slug")
    add_parser.add_argument(
        "--no-zotero",
        action="store_true",
        help="Data analyst mode: skip Zotero, Obsidian only",
    )
    add_parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip DOI verification",
    )

    find_parser = subparsers.add_parser("find", help="Search within vault notes")
    find_parser.add_argument("query", nargs="?", default="", help="Search query")
    find_parser.add_argument("--cluster", default=None)
    find_parser.add_argument(
        "--status", default=None, choices=["unread", "reading", "deep-read", "cited"]
    )
    find_parser.add_argument("--full", action="store_true", help="Full-text search (slower)")
    find_parser.add_argument("--json", action="store_true")
    find_parser.add_argument("--limit", type=int, default=20)
    find_parser.add_argument("--label", help="Only return papers with this label")
    find_parser.add_argument("--label-not", help="Only return papers WITHOUT this label")

    label_parser = subparsers.add_parser("label", help="Manage a paper's labels")
    label_parser.add_argument("slug", help="Paper slug (filename stem)")
    label_parser.add_argument("--set", default="", help="Comma-separated labels to set (replaces existing)")
    label_parser.add_argument("--add", default="", help="Comma-separated labels to add")
    label_parser.add_argument("--remove", default="", help="Comma-separated labels to remove")
    label_parser.add_argument("--fit-score", type=int, help="Set fit_score")
    label_parser.add_argument("--fit-reason", help="Set fit_reason")

    bulk_parser = subparsers.add_parser("label-bulk", help="Apply labels from a JSON file")
    bulk_parser.add_argument("--from-json", required=True, help="Path to labels.json")

    search_parser = subparsers.add_parser("search", help="Search for academic papers")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)
    search_parser.add_argument("--year", help="Year range, e.g. 2024-2025 or 2024- or -2024")
    search_parser.add_argument("--min-citations", type=int, default=0)
    search_backend_group = search_parser.add_mutually_exclusive_group()
    search_backend_group.add_argument(
        "--backend",
        default=None,
        help="Comma-separated list of backends",
    )
    search_backend_group.add_argument(
        "--field",
        choices=sorted(FIELD_PRESETS.keys()),
        default=None,
        help="Backend preset for a research field",
    )
    search_backend_group.add_argument(
        "--region",
        choices=sorted(REGION_PRESETS.keys()),
        default=None,
        help="Backend preset by language/region (en, jp, kr, cjk)",
    )
    search_parser.add_argument(
        "--exclude-type",
        default="",
        help="Comma-separated list of doc types to exclude (e.g. 'book-chapter,report,paratext')",
    )
    search_parser.add_argument(
        "--exclude",
        default="",
        help="Comma-or-space-separated negative keywords. Drop papers whose title or abstract contains any.",
    )
    search_parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum confidence (0.0..1.0). 0.5=found by 1 backend, 0.75=2 backends, 1.0=3+",
    )
    search_parser.add_argument(
        "--backend-trace",
        action="store_true",
        help="Print per-backend hit counts before merge",
    )
    search_parser.add_argument(
        "--rank-by",
        choices=["smart", "citation", "year"],
        default="smart",
        help="Ranking strategy. smart = 2*confidence + recency + relevance (default). citation = legacy v0.15 behavior. year = recency only.",
    )
    search_parser.add_argument("--json", action="store_true", help="Emit JSON array")
    search_parser.add_argument(
        "--to-papers-input",
        action="store_true",
        help="Emit a papers_input.json document (stdout) for piping into ingest",
    )
    search_parser.add_argument(
        "--cluster",
        help="Populate sub_category with this cluster slug (used with --to-papers-input)",
    )
    search_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify each DOI against doi.org before printing (adds 1-2s per result)",
    )
    search_parser.add_argument(
        "--enrich",
        action="store_true",
        help="Treat positional `query` as a newline-or-comma-separated candidate list "
        "(DOIs / arxiv IDs / titles) and resolve each via backend.get_paper. "
        "Use '-' to read candidates from stdin.",
    )

    enrich_parser = subparsers.add_parser(
        "enrich",
        help="Resolve candidate identifiers (DOI / arxiv ID / title) to full paper records",
    )
    enrich_parser.add_argument(
        "candidates",
        nargs="*",
        help="Identifiers to resolve. Use '-' to read from stdin (one per line).",
    )
    enrich_parser.add_argument("--backend", default="openalex,arxiv,semantic-scholar")
    enrich_parser.add_argument("--json", action="store_true", default=True)
    enrich_parser.add_argument("--to-papers-input", action="store_true")
    enrich_parser.add_argument("--cluster", help="Populate sub_category when --to-papers-input")

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
    cite_parser.add_argument(
        "--inline",
        action="store_true",
        help="Print an inline citation like (Lamparth et al., 2024)",
    )
    cite_parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print a markdown citation with DOI link",
    )
    cite_parser.add_argument(
        "--style",
        choices=("apa", "chicago", "mla", "latex"),
        default="apa",
        help="Citation style for --inline (default apa)",
    )

    quote_parser = subparsers.add_parser("quote", help="Capture and manage saved paper quotes")
    quote_parser.add_argument("quote_target", nargs="*", help="Slug, or commands: list | remove <slug>")
    quote_parser.add_argument("--page", default=None, help="Page number for the captured quote")
    quote_parser.add_argument("--text", default=None, help="Quoted passage text")
    quote_parser.add_argument("--context", default="", help="Optional context note")
    quote_parser.add_argument("--cluster", default=None, help="Filter list output to one cluster slug")
    quote_parser.add_argument("--at", default=None, help="Quote captured_at timestamp to remove")

    compose_parser = subparsers.add_parser(
        "compose-draft",
        help="Assemble captured quotes into a markdown draft",
    )
    compose_parser.add_argument("--cluster", required=True, help="Cluster slug")
    compose_parser.add_argument(
        "--outline",
        default=None,
        help='Semicolon-separated section headings, e.g. "Intro;Methods;Results"',
    )
    compose_parser.add_argument(
        "--quotes",
        default=None,
        help="Comma-separated paper slugs to restrict which quotes are included",
    )
    compose_parser.add_argument(
        "--style",
        choices=("apa", "chicago", "mla", "latex"),
        default="apa",
        help="Citation style (default: apa)",
    )
    compose_parser.add_argument(
        "--no-bibliography",
        dest="include_bibliography",
        action="store_false",
        default=True,
        help="Omit the References section at the end",
    )
    compose_parser.add_argument(
        "--out",
        default=None,
        help="Output path (default: <vault>/drafts/...)",
    )

    status_parser = subparsers.add_parser("status", help="Show per-cluster reading progress")
    status_parser.add_argument("--cluster", default=None, help="Show only this cluster")

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Generate a personal HTML dashboard for the vault",
    )
    dashboard_parser.add_argument(
        "--open",
        dest="open_browser",
        action="store_true",
        help="Open the dashboard in your default browser after generation",
    )
    dashboard_parser.add_argument(
        "--watch",
        action="store_true",
        help="Re-render the dashboard whenever vault state files change",
    )
    dashboard_parser.add_argument(
        "--refresh",
        type=int,
        default=10,
        help="Browser auto-refresh interval in seconds when --watch is set (default 10)",
    )
    dashboard_parser.add_argument(
        "--rich-bibtex",
        action="store_true",
        help=(
            "Fetch rich BibTeX entries from Zotero for every paper (slow: "
            "~1s/paper). Default uses an instant frontmatter fallback that "
            "is sufficient for most citations."
        ),
    )
    dashboard_parser.add_argument(
        "--screenshot",
        metavar="TAB",
        default=None,
        help=(
            "Capture TAB as PNG via Playwright headless. Tabs: overview, library, "
            "briefings, writing, diagnostics, manage, all. Legacy alias: crystal -> overview."
        ),
    )
    dashboard_parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="Output PNG path for single-tab --screenshot",
    )
    dashboard_parser.add_argument(
        "--out-dir",
        metavar="DIR",
        default=None,
        help="Output directory for --screenshot all",
    )
    dashboard_parser.add_argument(
        "--scale",
        type=float,
        default=2.0,
        help="Device pixel ratio (default: 2.0 for Retina-grade)",
    )
    dashboard_parser.add_argument(
        "--viewport-width",
        type=int,
        default=1440,
        help="Viewport width before scaling (default: 1440)",
    )
    dashboard_parser.add_argument(
        "--viewport-height",
        type=int,
        default=900,
        help="Viewport height before scaling (default: 900)",
    )
    dashboard_parser.add_argument(
        "--full-page",
        action="store_true",
        help="Capture the entire scrolled page instead of the visible viewport",
    )

    vault_parser = subparsers.add_parser("vault", help="Vault maintenance commands")
    vault_subparsers = vault_parser.add_subparsers(dest="vault_command", required=True)
    vault_graph_colors = vault_subparsers.add_parser(
        "graph-colors",
        help="Refresh managed Obsidian graph color groups",
    )
    vault_graph_colors.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild research-hub-managed graph color groups",
    )

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

    pipeline_parser = subparsers.add_parser("pipeline", help="Pipeline maintenance commands")
    pipeline_sub = pipeline_parser.add_subparsers(dest="pipeline_command", required=True)
    pipeline_repair = pipeline_sub.add_parser("repair", help="Repair pipeline orphans for a cluster")
    pipeline_repair.add_argument("--cluster", required=True)
    pipeline_repair.add_argument("--dry-run", action="store_true", default=True)
    pipeline_repair.add_argument("--execute", action="store_true")

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
    nlm_bundle.add_argument(
        "--download-pdfs",
        action="store_true",
        help="Fetch missing PDFs from arxiv/Unpaywall before falling back to URL",
    )
    nlm_upload = nlm_sub.add_parser("upload", help="Auto-upload bundle to NotebookLM")
    nlm_upload.add_argument("--cluster", required=True)
    nlm_upload.add_argument("--dry-run", action="store_true")
    nlm_upload.add_argument("--headless", action="store_true", default=False)
    nlm_upload.add_argument("--visible", dest="headless", action="store_false")
    nlm_upload.add_argument("--create-if-missing", action="store_true", default=True)
    nlm_download = nlm_sub.add_parser(
        "download",
        help="Download a generated NotebookLM artifact (briefing) back to the vault",
    )
    nlm_download.add_argument("--cluster", required=True)
    nlm_download.add_argument(
        "--type",
        choices=["brief"],
        default="brief",
        help="Artifact type to download (v0.9.0: brief only; audio/mind-map/video land in v0.9.1)",
    )
    nlm_download.add_argument("--headless", action="store_true", default=False)
    nlm_download.add_argument("--visible", dest="headless", action="store_false")
    nlm_read_brief = nlm_sub.add_parser(
        "read-briefing",
        help="Print the most recently downloaded briefing for a cluster",
    )
    nlm_read_brief.add_argument("--cluster", required=True)
    nlm_generate = nlm_sub.add_parser("generate", help="Trigger NotebookLM artifact generation")
    nlm_generate.add_argument("--cluster", required=True)
    nlm_generate.add_argument(
        "--type",
        choices=["brief", "audio", "mind-map", "video", "all"],
        default="brief",
    )
    nlm_generate.add_argument("--headless", action="store_true", default=False)
    nlm_generate.add_argument("--visible", dest="headless", action="store_false")

    fit_parser = subparsers.add_parser("fit-check", help="Multi-gate fit-check for clusters")
    fit_sub = fit_parser.add_subparsers(dest="fit_check_command")

    fit_emit = fit_sub.add_parser("emit", help="Emit the Gate 1 scoring prompt for an AI")
    fit_emit.add_argument("--cluster", required=True)
    fit_emit.add_argument("--candidates", required=True)
    fit_emit.add_argument("--definition")
    fit_emit.add_argument("--out")

    fit_apply = fit_sub.add_parser("apply", help="Apply AI scores and emit accepted papers")
    fit_apply.add_argument("--cluster", required=True)
    fit_apply.add_argument("--candidates", required=True)
    fit_apply.add_argument("--scored", required=True)
    fit_apply.add_argument("--threshold", type=int, default=3)
    fit_apply.add_argument(
        "--auto-threshold",
        action="store_true",
        help="Compute threshold as median(scores) - 1 (clamped [2, 5])",
    )
    fit_apply.add_argument("--out")

    fit_audit = fit_sub.add_parser("audit", help="Parse the latest briefing for off-topic flags")
    fit_audit.add_argument("--cluster", required=True)

    fit_drift = fit_sub.add_parser("drift", help="Emit a drift-check prompt")
    fit_drift.add_argument("--cluster", required=True)
    fit_drift.add_argument("--threshold", type=int, default=3)
    fit_apply_labels = fit_sub.add_parser(
        "apply-labels",
        help="Tag rejected papers as deprecated from the sidecar",
    )
    fit_apply_labels.add_argument("--cluster", required=True)

    autofill_parser = subparsers.add_parser(
        "autofill",
        help="Auto-fill paper note body content via AI emit/apply",
    )
    autofill_sub = autofill_parser.add_subparsers(dest="autofill_command")
    autofill_emit = autofill_sub.add_parser("emit", help="Emit autofill prompt for an AI")
    autofill_emit.add_argument("--cluster", required=True)
    autofill_emit.add_argument("--out")
    autofill_apply = autofill_sub.add_parser("apply", help="Apply AI-supplied content to paper notes")
    autofill_apply.add_argument("--cluster", required=True)
    autofill_apply.add_argument("--scored", required=True, help="Path to AI-produced JSON")

    crystal_parser = subparsers.add_parser("crystal", help="Manage pre-computed canonical crystals")
    crystal_sub = crystal_parser.add_subparsers(dest="crystal_command")
    crystal_emit = crystal_sub.add_parser("emit", help="Emit a crystal-generation prompt for an AI")
    crystal_emit.add_argument("--cluster", required=True)
    crystal_emit.add_argument("--questions", help="Comma-separated question slugs to emit")
    crystal_emit.add_argument("--out")
    crystal_apply = crystal_sub.add_parser("apply", help="Apply AI-generated crystals")
    crystal_apply.add_argument("--cluster", required=True)
    crystal_apply.add_argument("--scored", required=True, help="Path to JSON produced by AI")
    crystal_list = crystal_sub.add_parser("list", help="List crystals for a cluster")
    crystal_list.add_argument("--cluster", required=True)
    crystal_read = crystal_sub.add_parser("read", help="Read a specific crystal")
    crystal_read.add_argument("--cluster", required=True)
    crystal_read.add_argument("--slug", required=True)
    crystal_read.add_argument("--level", choices=["tldr", "gist", "full"], default="gist")
    crystal_check = crystal_sub.add_parser("check", help="Check crystal staleness")
    crystal_check.add_argument("--cluster", required=True)

    memory_parser = subparsers.add_parser("memory", help="Manage structured cluster memory registries")
    memory_sub = memory_parser.add_subparsers(dest="memory_command")
    memory_emit = memory_sub.add_parser("emit", help="Emit a memory-extraction prompt for an AI")
    memory_emit.add_argument("--cluster", required=True)
    memory_apply = memory_sub.add_parser("apply", help="Apply AI-generated cluster memory")
    memory_apply.add_argument("--cluster", required=True)
    memory_apply.add_argument("--scored", required=True, help="Path to JSON produced by AI")
    memory_list = memory_sub.add_parser("list", help="List memory records for a cluster")
    memory_list.add_argument("--cluster", required=True)
    memory_list.add_argument("--kind", choices=["entities", "claims", "methods"])
    memory_read = memory_sub.add_parser("read", help="Read the full cluster memory registry")
    memory_read.add_argument("--cluster", required=True)

    paper_parser = subparsers.add_parser("paper", help="Paper curation operations")
    paper_sub = paper_parser.add_subparsers(dest="paper_command")
    prune_p = paper_sub.add_parser("prune", help="Move or delete labeled papers")
    prune_p.add_argument("--cluster", required=True)
    prune_p.add_argument("--label", default="deprecated")
    prune_p.add_argument("--archive", action="store_true", default=True, help="Move to raw/_archive/<cluster>/ (default)")
    prune_p.add_argument("--delete", action="store_true", help="Hard-delete instead of archive")
    prune_p.add_argument("--zotero", action="store_true", help="Also delete Zotero items (only with --delete)")
    prune_p.add_argument("--dry-run", action="store_true")
    unarch_p = paper_sub.add_parser("unarchive", help="Restore an archived paper back to active cluster")
    unarch_p.add_argument("--cluster", required=True)
    unarch_p.add_argument("--slug", required=True)

    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover papers for a cluster (search + fit-check wrapper)",
    )
    discover_sub = discover_parser.add_subparsers(dest="discover_command")

    new_p = discover_sub.add_parser("new", help="Run search + emit fit-check prompt, stash for continue")
    new_p.add_argument("--cluster", required=True)
    new_p.add_argument("--query", required=True)
    new_p.add_argument("--year", help="Year range e.g. 2024-2025")
    new_p.add_argument("--min-citations", type=int, default=0)
    discover_backend_group = new_p.add_mutually_exclusive_group()
    discover_backend_group.add_argument("--backend", default=None)
    discover_backend_group.add_argument(
        "--field",
        choices=sorted(FIELD_PRESETS.keys()),
        default=None,
    )
    discover_backend_group.add_argument(
        "--region",
        choices=sorted(REGION_PRESETS.keys()),
        default=None,
    )
    new_p.add_argument("--exclude-type", default="")
    new_p.add_argument("--exclude", default="")
    new_p.add_argument("--min-confidence", type=float, default=0.0)
    new_p.add_argument("--rank-by", choices=["smart", "citation", "year"], default="smart")
    new_p.add_argument("--limit", type=int, default=50)
    new_p.add_argument("--definition", help="Cluster definition")
    new_p.add_argument("--from-variants", help="Path to a JSON file with query variations from `discover variants`")
    new_p.add_argument(
        "--expand-auto",
        action="store_true",
        help="Auto-pick top 3 keyword results as seeds for citation expansion",
    )
    new_p.add_argument("--expand-from", default="", help="Comma-separated DOIs to use as citation expansion seeds")
    new_p.add_argument("--expand-hops", type=int, default=1, help="Citation expansion hops (default 1, bounded)")
    new_p.add_argument("--seed-dois", default="", help="Comma-separated DOIs to inject as seeds")
    new_p.add_argument("--seed-dois-file", help="File with one DOI per line")
    new_p.add_argument("--include-existing", action="store_true", help="Do NOT dedup against existing cluster papers")
    new_p.add_argument("--prompt-out", help="Write fit-check prompt to file (default: stdout)")

    continue_p = discover_sub.add_parser("continue", help="Apply AI scores, emit papers_input.json")
    continue_p.add_argument("--cluster", required=True)
    continue_p.add_argument("--scored", required=True, help="Path to AI-produced scored JSON")
    continue_p.add_argument("--threshold", type=int)
    continue_p.add_argument("--auto-threshold", action="store_true")
    continue_p.add_argument("--out", help="Write papers_input.json here (default: stash dir)")

    status_p = discover_sub.add_parser("status", help="Show discover stage for a cluster")
    status_p.add_argument("--cluster", required=True)

    clean_p = discover_sub.add_parser("clean", help="Remove stashed discover state")
    clean_p.add_argument("--cluster", required=True)

    variants_p = discover_sub.add_parser("variants", help="Emit a query-variation prompt for an AI to consume")
    variants_p.add_argument("--cluster", required=True)
    variants_p.add_argument("--query", required=True)
    variants_p.add_argument("--count", type=int, default=4)
    variants_p.add_argument("--out", help="Write to file instead of stdout")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    exempt_commands = {"init", "doctor", "install", "examples", "where", "config", "package-dxt"}

    if args.command not in exempt_commands and get_config is require_config.__globals__["get_config"]:
        require_config()

    if args.command in (None, "run"):
        rc = run_pipeline(
            dry_run=getattr(args, "dry_run", False),
            cluster_slug=getattr(args, "cluster", None),
            query=getattr(args, "query", None),
            verify=getattr(args, "verify", True),
            allow_library_duplicates=getattr(args, "allow_library_duplicates", False),
            fit_check=getattr(args, "fit_check", False),
            fit_check_threshold=getattr(args, "fit_check_threshold", 3),
            no_fit_check_auto_labels=getattr(args, "no_fit_check_auto_labels", False),
        )
        if rc == 0 and getattr(args, "fit_check", False) and not getattr(args, "no_fit_check_auto_labels", False):
            from research_hub.paper import apply_fit_check_to_labels

            cfg = get_config()
            result = apply_fit_check_to_labels(cfg, args.cluster)
            print(f"auto-labeled {len(result['tagged'])} paper(s) as deprecated from fit-check sidecar")
        return rc
    if args.command == "init":
        if args.field:
            from research_hub.onboarding import run_field_wizard

            cfg = get_config()
            result = run_field_wizard(
                cfg,
                field=args.field,
                cluster_slug=args.cluster,
                cluster_name=args.name,
                query=args.query,
                definition=args.definition,
                non_interactive=args.non_interactive,
            )
            print(f"Created cluster {result.cluster_slug} with {result.candidate_count} candidates")
            print()
            print("Next steps:")
            for step in result.next_steps:
                print(f"  {step}")
            return 0
        from research_hub.init_wizard import run_init

        return run_init(
            vault_root=args.vault,
            zotero_key=args.zotero_key,
            zotero_library_id=args.zotero_library_id,
            non_interactive=args.non_interactive,
            persona=args.persona,
        )
    if args.command == "doctor":
        from research_hub.doctor import print_doctor_report, run_doctor

        return print_doctor_report(run_doctor())
    if args.command == "config":
        if args.config_command == "encrypt-secrets":
            return _config_encrypt_secrets()
        parser.error("config requires a subcommand")
        return 2
    if args.command == "examples":
        from research_hub.examples import copy_example_as_cluster, list_examples, load_example

        if args.examples_command == "list":
            for ex in list_examples():
                print(f"  {ex['slug']:35s} ({ex['field']:7s}) - {ex['name']}")
            return 0
        if args.examples_command == "show":
            try:
                ex = load_example(args.name)
            except FileNotFoundError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(json.dumps(ex, indent=2, ensure_ascii=False))
            return 0
        if args.examples_command == "copy":
            cfg = get_config()
            try:
                slug = copy_example_as_cluster(cfg, args.name, cluster_slug=args.cluster)
                ex = load_example(args.name)
            except (FileNotFoundError, ValueError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(f"copied {args.name} as cluster {slug}")
            print(
                f"next: research-hub discover new --cluster {slug} --query '{ex['query']}' --field {ex['field']}"
            )
            return 0
        parser.error("examples requires a subcommand")
        return 2
    if args.command == "install":
        return _cmd_install(args)
    if args.command == "where":
        return _cmd_where(args)
    if args.command == "package-dxt":
        return _package_dxt(args.out)
    if args.command == "ask":
        cfg = require_config()
        from research_hub.workflows import ask_cluster as _ask
        result = _ask(cfg, args.cluster, question=args.question, detail=args.detail)
        import json as _json
        print(_json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.command == "serve":
        cfg = get_config()
        return _cmd_serve(args, cfg)
    if args.command == "ingest":
        rc = run_pipeline(
            dry_run=args.dry_run,
            cluster_slug=args.cluster,
            query=args.query,
            verify=args.verify,
            allow_library_duplicates=args.allow_library_duplicates,
            fit_check=args.fit_check,
            fit_check_threshold=args.fit_check_threshold,
            no_fit_check_auto_labels=args.no_fit_check_auto_labels,
        )
        if rc == 0 and args.fit_check and not args.no_fit_check_auto_labels:
            from research_hub.paper import apply_fit_check_to_labels

            cfg = get_config()
            result = apply_fit_check_to_labels(cfg, args.cluster)
            print(f"auto-labeled {len(result['tagged'])} paper(s) as deprecated from fit-check sidecar")
        return rc
    if args.command == "import-folder":
        return _import_folder_command(args)
    if args.command == "fit-check":
        if args.fit_check_command == "emit":
            return _fit_check_emit(args.cluster, args.candidates, args.definition, args.out)
        if args.fit_check_command == "apply":
            return _fit_check_apply(
                args.cluster,
                args.candidates,
                args.scored,
                args.threshold,
                args.auto_threshold,
                args.out,
            )
        if args.fit_check_command == "audit":
            return _fit_check_audit(args.cluster)
        if args.fit_check_command == "drift":
            return _fit_check_drift(args.cluster, args.threshold)
        if args.fit_check_command == "apply-labels":
            return _fit_check_apply_labels(args.cluster)
        parser.error("fit-check requires a subcommand")
        return 2
    if args.command == "autofill":
        if args.autofill_command == "emit":
            return _autofill_emit(args.cluster, args.out)
        if args.autofill_command == "apply":
            return _autofill_apply(args.cluster, args.scored)
        parser.error("autofill requires a subcommand")
        return 2
    if args.command == "crystal":
        if not args.crystal_command:
            parser.error("crystal requires a subcommand")
            return 2
        return _cmd_crystal(args, get_config())
    if args.command == "memory":
        if not args.memory_command:
            parser.error("memory requires a subcommand")
            return 2
        return _cmd_memory(args, get_config())
    if args.command == "discover":
        if args.discover_command == "new":
            return _discover_new(args)
        if args.discover_command == "continue":
            return _discover_continue(args)
        if args.discover_command == "status":
            return _discover_status(args)
        if args.discover_command == "clean":
            return _discover_clean(args)
        if args.discover_command == "variants":
            return _discover_variants(args)
        parser.error("discover requires a subcommand")
        return 2
    if args.command == "index":
        return _rebuild_index()
    if args.command == "dedup":
        return _dedup(args)
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
            return _clusters_delete(args.slug, args.dry_run, args.purge_folder)
        if args.clusters_command == "merge":
            return _clusters_merge(args.source, args.target)
        if args.clusters_command == "split":
            return _clusters_split(args.source, args.query, args.new_name)
        if args.clusters_command == "analyze":
            return _cmd_clusters_analyze(args, get_config())
        if args.clusters_command == "rebind":
            from research_hub.cluster_rebind import apply_rebind, emit_rebind_prompt

            cfg = require_config()
            if args.emit:
                print(emit_rebind_prompt(cfg))
                return 0
            if args.apply:
                result = apply_rebind(cfg, args.apply, dry_run=not args.no_dry_run)
                mode = "DRY-RUN" if not args.no_dry_run else "APPLIED"
                print(
                    f"[{mode}] moved={len(result.moved)} skipped={len(result.skipped)} errors={len(result.errors)}"
                )
                if result.log_path:
                    print(f"Log: {result.log_path}")
                return 0 if not result.errors else 1
            print("Specify --emit or --apply <path>", file=sys.stderr)
            return 2
    if args.command == "topic":
        from research_hub.topic import (
            SubtopicProposal,
            apply_assignments,
            build_subtopic_notes,
            emit_assign_prompt,
            emit_propose_prompt,
            get_topic_digest,
            list_subtopics,
            read_overview,
            scaffold_overview,
        )

        cfg = get_config()
        if args.topic_command == "scaffold":
            try:
                path = scaffold_overview(cfg, args.cluster, force=args.force)
            except FileExistsError as exc:
                print(str(exc), file=sys.stderr)
                print("hint: use --force to overwrite", file=sys.stderr)
                return 1
            print(f"wrote {path}")
            return 0
        if args.topic_command == "digest":
            digest = get_topic_digest(cfg, args.cluster)
            markdown = digest.to_markdown()
            if args.out:
                Path(args.out).write_text(markdown, encoding="utf-8")
                print(f"wrote {args.out} ({digest.paper_count} papers)")
            else:
                print(markdown)
            return 0
        if args.topic_command == "show":
            content = read_overview(cfg, args.cluster)
            if content is None:
                print("no overview (run: research-hub topic scaffold --cluster ...)", file=sys.stderr)
                return 1
            print(content)
            return 0
        if args.topic_command == "propose":
            prompt = emit_propose_prompt(cfg, args.cluster, target_count=args.target_count)
            if args.out:
                Path(args.out).write_text(prompt, encoding="utf-8")
                print(f"wrote {args.out}")
            else:
                print(prompt)
            return 0
        if args.topic_command == "assign":
            if args.assign_command == "emit":
                data = json.loads(Path(args.subtopics).read_text(encoding="utf-8"))
                subtopics = [SubtopicProposal(**item) for item in data.get("subtopics", data)]
                prompt = emit_assign_prompt(cfg, args.cluster, subtopics)
                if args.out:
                    Path(args.out).write_text(prompt, encoding="utf-8")
                    print(f"wrote {args.out}")
                else:
                    print(prompt)
                return 0
            if args.assign_command == "apply":
                data = json.loads(Path(args.assignments).read_text(encoding="utf-8"))
                assignments = data.get("assignments", data)
                report = apply_assignments(cfg, args.cluster, assignments)
                for slug, count in sorted(report.items()):
                    print(f"  {slug}: {count} subtopic(s)")
                return 0
            topic_command_parser = next(
                action
                for action in parser._subparsers._group_actions[0].choices.values()
                if action.prog.endswith(" topic")
            )
            topic_assign = next(
                action
                for action in topic_command_parser._subparsers._group_actions[0].choices.values()
                if action.prog.endswith(" topic assign")
            )
            topic_assign.print_help()
            return 2
        if args.topic_command == "build":
            written = build_subtopic_notes(cfg, args.cluster)
            for path in written:
                print(f"wrote {path}")
            return 0
        if args.topic_command == "list":
            descriptors = list_subtopics(cfg, args.cluster)
            if not descriptors:
                print(f"no sub-topics for cluster {args.cluster}")
                return 0
            print(f"{'slug':<25} {'title':<35} papers")
            for descriptor in descriptors:
                print(f"{descriptor.slug:<25} {descriptor.title:<35} {descriptor.paper_count}")
            return 0
        topic_parser = next(
            action
            for action in parser._subparsers._group_actions[0].choices.values()
            if action.prog.endswith(" topic")
        )
        topic_parser.print_help()
        return 2
    if args.command == "remove":
        return _remove(args.identifier, args.zotero, args.dry_run)
    if args.command == "mark":
        return _mark(args.slug, args.status, args.cluster)
    if args.command == "move":
        return _move(args.slug, args.to_cluster)
    if args.command == "add":
        return _add(args.identifier, args.cluster, args.no_zotero, args.no_verify)
    if args.command == "label":
        return _label(args)
    if args.command == "label-bulk":
        return _label_bulk(args.from_json)
    if args.command == "paper":
        return _paper_command(args)
    if args.command == "quote":
        target = list(args.quote_target or [])
        if target == ["list"]:
            return _quote_list(args.cluster)
        if len(target) == 2 and target[0] == "remove":
            if not args.at:
                print("Usage: research-hub quote remove <slug> --at <iso-timestamp>")
                return 2
            return _quote_remove(target[1], args.at)
        if len(target) != 1 or not args.page or not args.text:
            print("Usage: research-hub quote <slug> --page 12 --text \"...\" [--context \"...\"]")
            return 2
        return _quote_add(target[0], args.page, args.text, args.context)
    if args.command == "compose-draft":
        return _compose_draft(
            args.cluster,
            args.outline,
            args.quotes,
            args.style,
            args.include_bibliography,
            args.out,
        )
    if args.command == "find":
        return _find(
            args.query,
            args.cluster,
            args.status,
            args.full,
            args.json,
            args.limit,
            args.label,
            args.label_not,
        )
    if args.command == "search":
        if args.region:
            backends = resolve_backends_for_region(args.region)
        elif args.field:
            backends = resolve_backends_for_field(args.field)
        elif args.backend:
            backends = tuple(b.strip() for b in args.backend.split(",") if b.strip())
        else:
            backends = DEFAULT_BACKENDS
        exclude_types = _parse_csv_terms(args.exclude_type)
        exclude_terms = _parse_negative_terms(args.exclude)
        if args.enrich:
            candidates = ["-"] if args.query == "-" else [item.strip() for item in re.split(r"[\n,]+", args.query) if item.strip()]
            return _enrich(
                candidates=candidates,
                backends=backends,
                to_papers_input=args.to_papers_input,
                cluster_slug=args.cluster,
            )
        year_from, year_to = _parse_year_range(args.year)
        return _search(
            args.query,
            args.limit,
            verify=args.verify,
            year_from=year_from,
            year_to=year_to,
            min_citations=args.min_citations,
            backends=backends,
            exclude_types=exclude_types,
            exclude_terms=exclude_terms,
            min_confidence=args.min_confidence,
            rank_by=args.rank_by,
            backend_trace=args.backend_trace,
            emit_json=args.json,
            to_papers_input=args.to_papers_input,
            cluster_slug=args.cluster,
        )
    if args.command == "enrich":
        return _enrich(
            candidates=args.candidates,
            backends=tuple(b.strip() for b in args.backend.split(",") if b.strip()),
            to_papers_input=args.to_papers_input,
            cluster_slug=args.cluster,
        )
    if args.command == "references":
        return _references(args.identifier, args.limit, args.json)
    if args.command == "cited-by":
        return _cited_by(args.identifier, args.limit, args.json)
    if args.command == "suggest":
        return _suggest(args.identifier, args.top, args.json)
    if args.command == "cite":
        return _cite(
            args.identifier,
            args.cluster,
            args.content_format,
            args.out,
            inline=args.inline,
            markdown=args.markdown,
            style=args.style,
        )
    if args.command == "status":
        return _status(cluster=args.cluster)
    if args.command == "dashboard":
        return _dashboard(
            args.open_browser,
            watch=args.watch,
            refresh=args.refresh,
            rich_bibtex=args.rich_bibtex,
            screenshot=args.screenshot,
            out=args.out,
            out_dir=args.out_dir,
            scale=args.scale,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height,
            full_page=args.full_page,
        )
    if args.command == "vault":
        if args.vault_command == "graph-colors":
            return _vault_graph_colors(refresh=args.refresh)
    if args.command == "sync":
        if args.sync_command == "status":
            return _sync_status(cluster_slug=args.cluster)
        if args.sync_command == "reconcile":
            return _sync_reconcile(cluster_slug=args.cluster, execute=args.execute)
    if args.command == "pipeline":
        if args.pipeline_command == "repair":
            return _pipeline_repair(cluster_slug=args.cluster, execute=args.execute)
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
            return _notebooklm_bundle(args.cluster, download_pdfs=args.download_pdfs)
        if args.notebooklm_command == "upload":
            return _nlm_upload(args.cluster, args.dry_run, args.headless, args.create_if_missing)
        if args.notebooklm_command == "download":
            return _nlm_download(args.cluster, args.type, args.headless)
        if args.notebooklm_command == "read-briefing":
            return _nlm_read_briefing(args.cluster)
        if args.notebooklm_command == "generate":
            return _nlm_generate(args.cluster, args.type, args.headless)

    parser.error(f"Unknown command: {args.command}")
    return 2
