"""Vault CLI handlers for Research Hub."""

from __future__ import annotations

from pathlib import Path
import sys

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.cli_common import _emit_cli_json


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

def _vault_graph_colors(refresh: bool) -> int:
    from research_hub.vault.graph_config import refresh_graph_from_vault

    if not refresh:
        print("Nothing to do. Pass --refresh.", file=sys.stderr)
        return 2
    cfg = get_config()
    count = refresh_graph_from_vault(cfg)
    print(f"Refreshed graph colors: {count} groups")
    return 0

def _vault_hub_backlink_migrate(
    *,
    cluster_slug: str | None,
    dry_run: bool,
    emit_json: bool = False,
) -> int:
    """Backfill ## Hub backlink section into existing paper notes (v0.88 §5)."""
    from collections import Counter

    from research_hub.clusters import ClusterRegistry
    from research_hub.vault.hub_backlink_migrate import migrate_all

    cfg = get_config()
    # Pre-build cluster_slug -> moc_links map so backfill honours explicit
    # `LLM-Agents-*` / `Water-Resources-*` overrides set in clusters.yaml.
    registry = ClusterRegistry(cfg.clusters_file)
    cluster_moc_links_map = {
        (c.slug or "").strip(): list(getattr(c, "moc_links", []) or [])
        for c in registry.list()
        if (c.slug or "").strip()
    }
    results = migrate_all(
        Path(cfg.root),
        cluster_slug_filter=cluster_slug,
        dry_run=dry_run,
        cluster_moc_links_map=cluster_moc_links_map,
    )
    counts = Counter(r.action for r in results)
    if emit_json:
        _emit_cli_json(
            "vault hub-backlink-migrate",
            0,
            {
                "cluster_filter": cluster_slug,
                "dry_run": dry_run,
                "counts": dict(counts),
                "results": results,
            },
        )
        return 0
    mode = "dry-run" if dry_run else "applied"
    print(f"vault hub-backlink-migrate ({mode}): scanned {len(results)} notes")
    for action in (
        "added", "already_present",
        "skipped_no_topic_cluster", "skipped_no_frontmatter",
    ):
        if counts.get(action):
            print(f"  {action:30s}  {counts[action]}")
    if dry_run and counts.get("added"):
        print("\nRe-run with --apply to write the changes.")
    return 0

def _vault_install_theme(*, theme: str, force: bool, uninstall: bool) -> int:
    """v0.88.13: install or remove a bundled Obsidian CSS theme."""
    from research_hub.vault.install_theme import install_theme, uninstall_theme

    cfg = get_config()
    vault_root = Path(cfg.root)
    if uninstall:
        result = uninstall_theme(vault_root, theme=theme)
    else:
        result = install_theme(vault_root, theme=theme, force=force)

    for err in result.errors:
        print(f"  [ERROR] {err}")

    if result.css_path:
        print(f"  snippet path: {result.css_path}")
    if result.appearance_path:
        print(f"  appearance:   {result.appearance_path}")
    print(f"  action: {result.action}")
    if result.action == "skipped_exists":
        print("    (file already present — re-run with --force to overwrite)")
    print(f"  enabled: {result.enabled}")

    if result.action == "installed" and not result.errors:
        print(
            "\nDone. Restart Obsidian to load the snippet "
            "(Settings → Appearance → CSS snippets should already show it enabled)."
        )
    if result.action == "uninstalled":
        print("\nUninstalled. Restart Obsidian to drop the styling.")

    return 0 if not result.errors else 1

def _vault_cleanup_frontmatter(
    *,
    cluster_slug: str | None,
    dry_run: bool,
    emit_json: bool = False,
) -> int:
    """v0.88.12: dedupe list-valued frontmatter fields across all paper notes.

    Mirrors the pattern of tag-migrate / hub-backlink-migrate /
    summarize-status-migrate so the user gets a consistent dry-run +
    --apply UX across the v0.87/v0.88 migration tools.
    """
    from collections import Counter

    from research_hub.vault.frontmatter_dedupe import migrate_all

    cfg = get_config()
    results = migrate_all(
        Path(cfg.root),
        cluster_slug_filter=cluster_slug,
        dry_run=dry_run,
    )
    counts = Counter(r.action for r in results)
    if emit_json:
        _emit_cli_json(
            "vault cleanup-frontmatter",
            0,
            {
                "cluster_filter": cluster_slug,
                "dry_run": dry_run,
                "counts": dict(counts),
                "results": results,
            },
        )
        return 0
    mode = "dry-run" if dry_run else "applied"
    print(f"vault cleanup-frontmatter ({mode}): scanned {len(results)} notes")
    for action in ("deduped", "clean", "skipped_no_lists", "skipped_no_frontmatter"):
        if counts.get(action):
            print(f"  {action:30s}  {counts[action]}")
    deduped_results = [r for r in results if r.action == "deduped"]
    if deduped_results:
        print("\nDetails:")
        for r in deduped_results:
            shrinks = ", ".join(
                f"{f}: {r.before[f]}→{r.after[f]}" for f in r.fields_deduped
            )
            print(f"  {r.path.name}: {shrinks}")
    if dry_run and counts.get("deduped"):
        print("\nRe-run with --apply to write the changes.")
    return 0

def _vault_tag_migrate(
    *,
    cluster_slug: str | None,
    dry_run: bool,
    emit_json: bool = False,
) -> int:
    """Backfill topic:<slug> tag into existing paper notes (v0.87.1 §6)."""
    from collections import Counter

    from research_hub.vault.tag_migrate import migrate_all

    cfg = get_config()
    results = migrate_all(
        Path(cfg.root),
        cluster_slug_filter=cluster_slug,
        dry_run=dry_run,
    )
    counts = Counter(r.action for r in results)
    if emit_json:
        _emit_cli_json(
            "vault tag-migrate",
            0,
            {
                "cluster_filter": cluster_slug,
                "dry_run": dry_run,
                "counts": dict(counts),
                "results": results,
            },
        )
        return 0
    mode = "dry-run" if dry_run else "applied"
    print(f"vault tag-migrate ({mode}): scanned {len(results)} notes")
    for action in ("added", "already_present", "skipped_no_topic_cluster", "skipped_no_tags_line", "skipped_no_frontmatter"):
        if counts.get(action):
            print(f"  {action:30s}  {counts[action]}")
    if dry_run and counts.get("added"):
        print("\nRe-run with --apply to write the changes.")
    return 0

def _vault_rebuild_overviews(
    *,
    cluster_slug: str | None,
    force_rebuild: bool = False,
    emit_json: bool = False,
) -> int:
    """Re-run populate_overview + ensure_moc for every cluster (v0.87.1 §5)."""
    from research_hub.vault.hub_overview import populate_all_overviews

    cfg = get_config()
    results = populate_all_overviews(
        cfg,
        cluster_slug_filter=cluster_slug,
        force_rebuild=force_rebuild,
    )
    if not results:
        if emit_json:
            _emit_cli_json(
                "vault rebuild-overviews",
                0,
                {
                    "cluster_filter": cluster_slug,
                    "force_rebuild": force_rebuild,
                    "results": [],
                },
            )
            return 0
        print("(no clusters processed)")
        return 0
    errors = 0
    json_results: list[dict[str, object]] = []
    for slug, path in results:
        marker = "[OK]"
        path_str = str(path)
        if path_str.startswith("<error:"):
            marker = "[FAIL]"
            errors += 1
        json_results.append({"cluster_slug": slug, "path": path_str, "ok": marker == "[OK]"})
        if emit_json:
            continue
        print(f"  {marker}  {slug}  {path_str}")
    rc = 0 if errors == 0 else 1
    if emit_json:
        _emit_cli_json(
            "vault rebuild-overviews",
            rc,
            {
                "cluster_filter": cluster_slug,
                "force_rebuild": force_rebuild,
                "results": json_results,
            },
        )
        return rc
    return rc

def _vault_polish_markdown(*, cluster: str | None, dry_run: bool) -> int:
    """Upgrade paper notes to v0.42 callout + block-ID conventions."""
    from research_hub.markdown_conventions import upgrade_paper_body

    cfg = get_config()
    raw_root = cfg.raw
    if not raw_root.exists():
        print(f"  [WARN] raw folder not found: {raw_root}")
        return 1
    candidates: list[Path] = []
    if cluster:
        target = raw_root / cluster
        if not target.exists():
            print(f"  [ERR] cluster folder not found: {target}")
            return 1
        candidates.extend(target.rglob("*.md"))
    else:
        candidates.extend(raw_root.rglob("*.md"))

    changed = 0
    scanned = 0
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        scanned += 1
        upgraded = upgrade_paper_body(text)
        if upgraded == text:
            continue
        changed += 1
        rel = path.relative_to(raw_root)
        if dry_run:
            print(f"  [would upgrade] {rel}")
        else:
            path.write_text(upgraded, encoding="utf-8")
            print(f"  [upgraded]    {rel}")

    verb = "would upgrade" if dry_run else "upgraded"
    print(f"\n{scanned} note(s) scanned, {changed} {verb}.")
    if dry_run and changed:
        print("Run again with --apply to write changes.")
    return 0

def _bases_emit(*, cluster_slug: str, stdout: bool, force: bool, emit_json: bool = False) -> int:
    from research_hub.obsidian_bases import (
        ClusterBaseInputs,
        build_cluster_base,
        write_cluster_base,
    )

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        if emit_json:
            _emit_cli_json(
                "bases emit",
                1,
                {
                    "cluster_slug": cluster_slug,
                    "stdout": stdout,
                    "force": force,
                    "error": f"Cluster not found: {cluster_slug}",
                },
            )
            return 1
        print(f"  [ERR] Cluster not found: {cluster_slug}")
        return 1

    if stdout:
        content = build_cluster_base(
            ClusterBaseInputs(
                cluster_slug=cluster_slug,
                cluster_name=cluster.name,
                obsidian_subfolder=cluster.obsidian_subfolder,
            )
        )
        if emit_json:
            _emit_cli_json(
                "bases emit",
                0,
                {
                    "cluster_slug": cluster_slug,
                    "stdout": True,
                    "force": force,
                    "path": None,
                    "content": content,
                },
            )
            return 0
        print(content)
        return 0

    path, written = write_cluster_base(
        hub_root=Path(cfg.hub),
        cluster_slug=cluster_slug,
        cluster_name=cluster.name,
        obsidian_subfolder=cluster.obsidian_subfolder,
        force=force,
    )
    if emit_json:
        _emit_cli_json(
            "bases emit",
            0,
            {
                "cluster_slug": cluster_slug,
                "stdout": False,
                "force": force,
                "path": path,
                "written": written,
            },
        )
        return 0
    if written:
        print(f"  [OK] Wrote {path}")
    else:
        print(f"  [SKIP] Already exists: {path}  (use --force to overwrite)")
    return 0
