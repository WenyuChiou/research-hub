"""Cluster CLI handlers for Research Hub."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config, require_config
from research_hub.cli_common import _emit_cli_json, _load_zotero_if_configured


def _read_doi_from_frontmatter(md_path: Path) -> str | None:
    """Pull the `doi:` line out of an Obsidian raw note frontmatter."""
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

    match = _re.search(r'^doi:\s*[\'"]?([^\'"\n]+)', frontmatter, _re.MULTILINE)
    return match.group(1).strip() if match else None


def _clusters_list() -> int:
    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    clusters = registry.list()

    # F3b: if any cluster has a group, show grouped output; otherwise flat list
    active = [c for c in clusters if (c.slug or "").strip()]
    has_groups = any(getattr(c, "group", "") for c in active)

    if has_groups:
        grouped: dict[str, list] = {}
        for cluster in active:
            g = (getattr(cluster, "group", "") or "").strip()
            grouped.setdefault(g, []).append(cluster)
        # Named groups alphabetically, ungrouped last
        sorted_groups = sorted(g for g in grouped if g)
        if "" in grouped:
            sorted_groups.append("")
        for g in sorted_groups:
            label = g if g else "(ungrouped)"
            print(f"\n[{label}]")
            for cluster in grouped[g]:
                print(f"  {cluster.slug}\t{cluster.name}")
    else:
        for cluster in active:
            print(f"{cluster.slug}\t{cluster.name}")
    return 0


_INVALID_GROUP_CHARS = frozenset('|[]#\n\r\t')


def _clusters_set_group(slug: str, group: str) -> int:
    """Assign or clear the group tag for a cluster (F3b)."""
    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(slug)
    if cluster is None:
        print(f"Cluster not found: {slug!r}", file=sys.stderr)
        return 1
    clean_group = group.strip()
    if clean_group and any(ch in clean_group for ch in _INVALID_GROUP_CHARS):
        print(
            f"[set-group] Invalid characters in group name: {clean_group!r}. "
            "Avoid: | [ ] # and whitespace other than spaces.",
            file=sys.stderr,
        )
        return 1
    cluster.group = clean_group
    registry.save()
    action = f"set to {group.strip()!r}" if group.strip() else "cleared"
    print(f"[set-group] {slug}: group {action}")
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


def _clusters_audit(cluster_slug: str | None = None, *, emit_json: bool = False) -> int:
    from research_hub.doctor import (
        check_cluster_collection_collision,
        check_cluster_test_pattern,
        check_cluster_zotero_drift,
        check_manifest_orphan_cluster,
    )
    from research_hub.vault.sync import compute_sync_status

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    clusters = registry.list()
    if cluster_slug is not None:
        cluster = registry.get(cluster_slug)
        if cluster is None:
            raise ValueError(f"Cluster not found: {cluster_slug}")
        clusters = [cluster]

    drift_results = check_cluster_zotero_drift(cfg)
    test_result = check_cluster_test_pattern(cfg)
    collision_result = check_cluster_collection_collision(cfg)
    orphan_result = check_manifest_orphan_cluster(cfg)

    drifted = {
        line.strip().split(":", 1)[0]
        for result in drift_results
        for line in result.details.splitlines()
        if line.strip()
    }
    test_slugs = {line.strip() for line in test_result.details.splitlines() if line.strip()}
    collision_slugs: set[str] = set()
    for line in collision_result.details.splitlines():
        if "[" not in line or "]" not in line:
            continue
        inside = line.split("[", 1)[1].rsplit("]", 1)[0]
        collision_slugs.update(slug.strip() for slug in inside.split(",") if slug.strip())

    drift_available = not any(result.status == "INFO" for result in drift_results)
    zot = _load_zotero_if_configured() if drift_available else None
    bad = False
    rows: list[dict[str, object]] = []
    if not emit_json:
        print(f"{'cluster':40} {'obsidian':>8} {'zotero':>8} {'in_both':>8} {'drift':>8} {'test?':>6} {'collision?':>11}")
    for cluster in clusters:
        if drift_available and zot is not None:
            status = compute_sync_status(cluster, zot, cfg.raw)
            drift = status.obsidian_count - status.in_both
            obsidian_cell = str(status.obsidian_count)
            zotero_cell = str(status.zotero_count)
            in_both_cell = str(status.in_both)
            drift_cell = f"!{drift}" if cluster.slug in drifted else str(drift)
        else:
            obsidian_cell = "n/a"
            zotero_cell = "n/a"
            in_both_cell = "n/a"
            drift_cell = "n/a"
        test_mark = "!" if cluster.slug in test_slugs else "-"
        collision_mark = "!" if cluster.slug in collision_slugs else "-"
        rows.append(
            {
                "cluster_slug": cluster.slug,
                "obsidian": obsidian_cell,
                "zotero": zotero_cell,
                "in_both": in_both_cell,
                "drift": drift_cell,
                "test_pattern": test_mark == "!",
                "collision": collision_mark == "!",
            }
        )
        if not emit_json:
            print(f"{cluster.slug:40} {obsidian_cell:>8} {zotero_cell:>8} {in_both_cell:>8} {drift_cell:>8} {test_mark:>6} {collision_mark:>11}")
        bad = bad or cluster.slug in drifted or test_mark == "!" or collision_mark == "!"

    if emit_json:
        rc = 1 if bad else 0
        _emit_cli_json(
            "clusters audit",
            rc,
            {
                "cluster_filter": cluster_slug,
                "drift_available": drift_available,
                "checks": {
                    "drift": drift_results,
                    "test_pattern": test_result,
                    "collection_collision": collision_result,
                    "manifest_orphan_cluster": orphan_result,
                },
                "clusters": rows,
            },
        )
        return rc

    if orphan_result.status != "OK":
        print()
        print(f"[{orphan_result.status}] {orphan_result.name}: {orphan_result.message}")
        if orphan_result.details:
            print(orphan_result.details)

    return 1 if bad else 0


def _clusters_new(query: str, name: str | None, slug: str | None) -> int:
    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.create(query=query, name=name, slug=slug)
    print(cluster.slug)
    return 0


def _clusters_bind(
    slug: str,
    zotero_key,
    obsidian_folder,
    notebooklm_notebook,
    *,
    sync_zotero: bool = True,
    force_shared: bool = False,
) -> int:
    cfg = get_config()
    from research_hub.clusters import CollisionError

    reg = ClusterRegistry(cfg.clusters_file)
    try:
        cluster = reg.bind(
            slug=slug,
            zotero_collection_key=zotero_key,
            obsidian_subfolder=obsidian_folder,
            notebooklm_notebook=notebooklm_notebook,
            sync_zotero=sync_zotero,
            force_shared=force_shared,
        )
    except CollisionError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "Remedy: re-run with --force-shared if the shared binding is intentional, "
            "or use `research-hub clusters resolve-collision <slug> --new --apply`.",
            file=sys.stderr,
        )
        return 2
    print(f"Bound {cluster.slug}:")
    print(f"  Zotero collection:   {cluster.zotero_collection_key or '(unset)'}")
    print(f"  Obsidian folder:     {cluster.obsidian_subfolder or '(unset)'}")
    print(f"  NotebookLM notebook: {cluster.notebooklm_notebook or '(unset)'}")
    return 0


def _clusters_rename(slug: str, name: str, *, sync_zotero: bool = True) -> int:
    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.rename(slug, name, sync_zotero=False)
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
    if not sync_zotero or not cluster.zotero_collection_key:
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


def _clusters_archive(slug: str) -> int:
    registry = ClusterRegistry(get_config().clusters_file)
    cluster = registry.archive(slug)
    print(f"archived: {cluster.slug}")
    return 0


def _clusters_unarchive(slug: str) -> int:
    registry = ClusterRegistry(get_config().clusters_file)
    cluster = registry.unarchive(slug)
    print(f"unarchived: {cluster.slug}")
    return 0


def _clusters_delete(
    slug: str,
    dry_run: bool,
    purge_folder: bool = False,
    *,
    delete_zotero_collection: bool = False,
) -> int:
    del purge_folder
    cfg = get_config()
    from research_hub.clusters import cascade_delete_cluster

    report = cascade_delete_cluster(
        cfg,
        slug,
        apply=not dry_run,
        delete_zotero_collection=delete_zotero_collection,
    )
    print(report.summary())
    if dry_run:
        print("")
        print("Run with --apply to execute the delete.")
        return 0
    return 0


def _clusters_sync_names(
    slug_filter: str | None,
    apply: bool,
    direction: str,
) -> int:
    cfg = get_config()
    from research_hub.zotero.client import get_client

    registry = ClusterRegistry(cfg.clusters_file)
    zot = get_client()
    clusters = registry.list()
    if slug_filter:
        cluster = registry.get(slug_filter)
        if cluster is None:
            print(f"Cluster not found: {slug_filter}", file=sys.stderr)
            return 2
        clusters = [cluster]

    drifts: list[tuple[object, str]] = []
    print("slug\tvault_name\tzotero_name")
    for cluster in clusters:
        if not cluster.zotero_collection_key:
            continue
        try:
            coll = zot.collection(cluster.zotero_collection_key)
            zotero_name = str(coll.get("data", {}).get("name", "") or "")
        except Exception as exc:
            zotero_name = f"<error: {exc}>"
        if cluster.name == zotero_name:
            continue
        drifts.append((cluster, zotero_name))
        print(f"{cluster.slug}\t{cluster.name}\t{zotero_name}")

    if not drifts:
        print("All cluster names already match.")
        return 0
    if not apply:
        print("")
        print("Preview only. Re-run with --apply to sync names.")
        return 0

    for cluster, zotero_name in drifts:
        if direction == "vault-to-zotero":
            _clusters_rename(cluster.slug, cluster.name, sync_zotero=True)
            continue
        registry.rename(cluster.slug, zotero_name, sync_zotero=False)
        print(f"updated vault name for {cluster.slug} -> {zotero_name!r}")
    return 0


def _clusters_restore_zotero_coll(slug_filter: str | None, apply: bool) -> int:
    cfg = get_config()
    from research_hub.clusters import _try_restore_zotero_collection
    from research_hub.zotero.client import ZoteroDualClient

    registry = ClusterRegistry(cfg.clusters_file)
    clusters = registry.list()
    if slug_filter:
        cluster = registry.get(slug_filter)
        if cluster is None:
            print(f"Cluster not found: {slug_filter}", file=sys.stderr)
            return 2
        clusters = [cluster]

    zot = ZoteroDualClient().web
    targets: list[tuple[str, str, str]] = []
    for cluster in clusters:
        key = (cluster.zotero_collection_key or "").strip()
        if not key:
            continue
        try:
            coll = zot.collection(key)
        except Exception:
            continue
        if coll.get("data", {}).get("deleted"):
            targets.append((cluster.slug, key, coll.get("data", {}).get("name", "")))

    if not targets:
        print("No trashed cluster Zotero collections found.")
        return 0

    print(f"{'Slug':<55} {'Key':<10} {'Name':<40}")
    for slug, key, name in targets:
        print(f"{slug:<55} {key:<10} {name:<40}")
    if not apply:
        print("")
        print("Preview only. Re-run with --apply to restore.")
        return 0

    failures = 0
    for _slug, key, _name in targets:
        ok, msg = _try_restore_zotero_collection(key)
        print(f"  {msg}")
        if not ok:
            failures += 1
    return 0 if failures == 0 else 1


def _clusters_resolve_collision(
    slug: str,
    *,
    new: bool,
    target_slug: str | None,
    apply: bool,
    force_shared: bool,
) -> int:
    cfg = get_config()
    from research_hub.vault.sync import list_cluster_notes, list_zotero_collection_items
    from research_hub.zotero.client import get_client

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(slug)
    if cluster is None:
        print(f"Cluster not found: {slug}", file=sys.stderr)
        return 2
    key = (cluster.zotero_collection_key or "").strip()
    if not key:
        print(f"{slug}: no Zotero collection is bound")
        return 0

    colliding = [
        other
        for other in registry.list()
        if other.slug != slug and (other.zotero_collection_key or "").strip() == key
    ]
    if not colliding:
        print(f"{slug}: no collision detected")
        return 0

    print(f"{slug}: {key} is also bound by {', '.join(other.slug for other in colliding)}")
    if not new and not target_slug:
        print("Specify exactly one of --new or --into <target>", file=sys.stderr)
        return 2
    if new and target_slug:
        print("Use either --new or --into, not both", file=sys.stderr)
        return 2

    zot = get_client()
    if not apply:
        if new:
            print("Preview: would create a fresh Zotero collection and re-tag this cluster's items.")
        else:
            print(f"Preview: would drop the Zotero binding from {slug} and keep it on {target_slug}.")
        return 0

    if new:
        from research_hub.zotero.client import ensure_parent_collection as _ensure_parent_cli
        _parent_name_cli = getattr(cfg, "zotero_parent_collection", "research-hub")
        # zot here is a raw pyzotero client from get_client(); wrap for ensure_parent_collection
        from types import SimpleNamespace as _SN_cli
        _dual_cli = _SN_cli(web=zot)
        _parent_key_cli = _ensure_parent_cli(_dual_cli, _parent_name_cli) if _parent_name_cli else False
        result = zot.create_collections(
            [{"name": cluster.name, "parentCollection": _parent_key_cli if _parent_key_cli else False}]
        )
        successful = (result or {}).get("successful", {}) if isinstance(result, dict) else {}
        first = next(iter(successful.values()), None) if successful else None
        new_key = (first or {}).get("key") or (first or {}).get("data", {}).get("key")
        if not new_key:
            print(f"Could not create fresh Zotero collection: {result}", file=sys.stderr)
            return 1
        registry.bind(slug, zotero_collection_key=new_key, sync_zotero=False, force_shared=False)
        note_dois = {
            str(_read_doi_from_frontmatter(note_path) or "").strip().lower()
            for note_path in list_cluster_notes(slug, cfg.raw)
        }
        note_dois.discard("")
        moved = 0
        for item in list_zotero_collection_items(zot, key):
            data = item.get("data", {})
            doi = str(data.get("DOI", "") or "").strip().lower()
            if not doi or doi not in note_dois:
                continue
            current = zot.item(item.get("key") or item.get("data", {}).get("key"))
            current_data = current.get("data", {})
            collections = list(current_data.get("collections", []))
            if new_key not in collections:
                collections.append(new_key)
                current_data["collections"] = collections
                zot.update_item(current_data)
                moved += 1
        print(f"Created {new_key} and added it to {moved} matching item(s).")
        return 0

    target = registry.get(target_slug or "")
    if target is None:
        print(f"Cluster not found: {target_slug}", file=sys.stderr)
        return 2
    if target.slug == slug:
        print("--into target must differ from the source cluster", file=sys.stderr)
        return 2
    if not force_shared:
        print("--into requires --force-shared", file=sys.stderr)
        return 2
    if (target.zotero_collection_key or "").strip() != key:
        print(
            f"{target.slug} is not bound to the colliding key {key!r}",
            file=sys.stderr,
        )
        return 2
    registry.bind(slug, zotero_collection_key="", sync_zotero=False)
    print(f"Removed Zotero binding from {slug}; {target.slug} keeps {key}.")
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


def _clusters_scaffold_missing() -> int:
    cfg = require_config()
    from research_hub.topic import scaffold_cluster_hub

    registry = ClusterRegistry(cfg.clusters_file)
    summaries: list[dict[str, str]] = []
    for cluster in registry.list():
        try:
            summaries.append(scaffold_cluster_hub(cfg, cluster.slug))
        except Exception as exc:
            print(f"  ! {cluster.slug}: {exc}", file=sys.stderr)
    created_count = sum(
        1
        for summary in summaries
        if summary.get("overview") == "created"
        or summary.get("crystals_dir") == "created"
        or summary.get("memory_json") == "created"
    )
    print(
        f"Scaffolded {created_count} of {len(summaries)} clusters "
        "(others already had complete hub structure)."
    )
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
