"""Zotero CLI handlers for Research Hub."""

from __future__ import annotations

import sys

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config


def _zotero_mark_kept(
    *,
    all_orphans: bool,
    add_keys: list[str] | None,
    remove_keys: list[str] | None,
    show_list: bool,
    note: str | None,
    show_counts: bool = False,
    by_pattern: str | None = None,
) -> int:
    """Manage the per-vault kept-collection list used by `zotero gc --respect-kept`."""
    import re

    cfg = get_config()
    from research_hub.zotero.gc import (
        is_orphan_candidate,
        kept_file_path,
        load_kept_keys,
        lookup_collection_names_and_counts,
        save_kept_keys,
        scan_zotero_for_gc,
    )

    current = load_kept_keys(cfg.research_hub_dir)
    if show_list:
        if not current:
            print("(no kept Zotero collections recorded)")
            return 0

        # v0.88 #10: --show-counts enriches the opaque 8-char keys with
        # Zotero collection name + item count. --by-pattern filters by
        # the human-readable name (regex, case-insensitive).
        details: dict[str, dict] = {}
        pattern_re = None
        if by_pattern:
            try:
                pattern_re = re.compile(by_pattern, re.IGNORECASE)
            except re.error as exc:
                print(f"  [ERR] invalid --by-pattern regex: {exc}", file=sys.stderr)
                return 2

        if show_counts or pattern_re is not None:
            from research_hub.zotero.client import get_client
            zot = get_client()
            details = lookup_collection_names_and_counts(zot, current)
            print("key       items  name")
            print("--------  -----  ----")
            shown = 0
            for key in sorted(current):
                d = details.get(key, {})
                name = d.get("name", "(unknown)")
                if pattern_re is not None and not pattern_re.search(name):
                    continue
                items_count = d.get("num_items", 0)
                print(f"{key:8}  {items_count:5d}  {name}")
                shown += 1
            print(f"\nfile: {kept_file_path(cfg.research_hub_dir)}")
            print(f"shown: {shown} / total kept: {len(current)}")
            return 0

        for key in sorted(current):
            print(key)
        print(f"\nfile: {kept_file_path(cfg.research_hub_dir)}")
        return 0

    if all_orphans:
        from research_hub.clusters import slugify
        from research_hub.zotero.client import get_client

        registry = ClusterRegistry(cfg.clusters_file)
        clusters = registry.list()
        vault_keys = {
            (cluster.zotero_collection_key or "").strip()
            for cluster in clusters
            if (cluster.zotero_collection_key or "").strip()
        }
        vault_name_slugs = {
            slugify(cluster.name)
            for cluster in clusters
            if (cluster.name or "").strip()
        } | {
            (cluster.slug or "").strip()
            for cluster in clusters
            if (cluster.slug or "").strip()
        }
        zot = get_client()
        # respect_kept=False here so we re-detect the full orphan set
        # age_days only affects the "empty>Nd" reason, not orphan-from-vault,
        # so the default 30 is fine for orphan bulk-marking.
        candidates = scan_zotero_for_gc(
            zot,
            vault_keys,
            include_test_pattern=False,
            age_days=30,
            kept_keys=set(),
            vault_name_slugs=vault_name_slugs,
        )
        # PR-A: include BOTH orphan reasons. A non-empty orphan
        # (`orphan-with-items(N)`) is exactly the real-data collection a
        # user most wants `--all-orphans` to protect from future gc noise;
        # keying on the bare "orphan-from-vault" string would silently drop
        # it now that the reason is split.
        new_keys = {c.key for c in candidates if is_orphan_candidate(c)}
        merged = current | new_keys
        save_kept_keys(cfg.research_hub_dir, merged, note=note)
        added = len(merged) - len(current)
        print(f"marked {added} additional collection(s) as kept (total: {len(merged)})")
        return 0

    if add_keys:
        merged = current | {k.strip() for k in add_keys if k.strip()}
        save_kept_keys(cfg.research_hub_dir, merged, note=note)
        added = len(merged) - len(current)
        print(f"marked {added} collection(s) as kept (total: {len(merged)})")
        return 0

    if remove_keys:
        to_remove = {k.strip() for k in remove_keys if k.strip()}
        merged = current - to_remove
        save_kept_keys(cfg.research_hub_dir, merged, note=note)
        removed = len(current) - len(merged)
        print(f"removed {removed} collection(s) from kept list (total: {len(merged)})")
        return 0

    print("Usage: research-hub zotero mark-kept --all-orphans | --collection KEY | --remove KEY | --list", file=sys.stderr)
    return 2

def _zotero_reparent_clusters(*, parent: str, apply: bool) -> int:
    """Nest existing cluster Zotero collections under a parent ("mother") collection.

    DRY-RUN (default, ``--apply`` not passed): lists each cluster with its
    current parentCollection and what action would be taken.  The parent
    collection is NOT created in dry-run mode.

    ``--apply``: ensures the parent exists (creates if missing), then calls
    ``update_collection`` for any cluster collection not yet nested under it.
    Already-nested collections are skipped (idempotent).  Never deletes
    anything.
    """
    cfg = get_config()
    from research_hub.zotero.client import ZoteroDualClient, ensure_parent_collection

    registry = ClusterRegistry(cfg.clusters_file)
    clusters = [c for c in registry.list() if (c.zotero_collection_key or "").strip()]

    if not clusters:
        print("No clusters with Zotero collection keys found.")
        return 0

    if not parent:
        print("ERROR: --parent is empty; pass a non-empty collection name.", file=sys.stderr)
        return 2

    if not apply:
        # Dry-run: resolve parent key only if possible via listing, do NOT create
        print(f"DRY-RUN: would reparent {len(clusters)} cluster collection(s) under '{parent}'")
        print(f"{'cluster':<40} {'key':<12} {'current_parent':<20} {'action'}")
        print("-" * 90)
        # Best-effort: try to read current parent data without writes
        try:
            dual = ZoteroDualClient()
            web = dual.web
            # Build map of collection key -> data
            coll_map: dict[str, dict] = {}
            start = 0
            while True:
                chunk = web.collections(limit=100, start=start)
                if not chunk:
                    break
                for c in chunk:
                    d = c.get("data", {})
                    coll_map[d.get("key", "")] = d
                if len(chunk) < 100:
                    break
                start += 100
            # Find parent key in existing collections
            parent_key_dr: str | None = next(
                (
                    d["key"]
                    for d in coll_map.values()
                    if d.get("parentCollection") is False and d.get("name") == parent
                ),
                None,
            )
            for cluster in clusters:
                key = (cluster.zotero_collection_key or "").strip()
                d = coll_map.get(key, {})
                current_parent = d.get("parentCollection", "?")
                if parent_key_dr and current_parent == parent_key_dr:
                    action = "already nested (skip)"
                elif parent_key_dr is None:
                    action = f"would create '{parent}' then nest"
                else:
                    action = f"would move under {parent_key_dr}"
                print(f"{cluster.slug:<40} {key:<12} {str(current_parent):<20} {action}")
        except Exception as exc:
            print(f"(could not fetch Zotero collections for preview: {exc})")
            for cluster in clusters:
                key = (cluster.zotero_collection_key or "").strip()
                print(f"{cluster.slug:<40} {key:<12} {'?':<20} would reparent")
        print()
        print("Re-run with --apply to execute.")
        return 0

    # --- Apply mode ---
    dual = ZoteroDualClient()
    parent_key = ensure_parent_collection(dual, parent)
    if not parent_key:
        print(f"ERROR: Could not find or create parent collection '{parent}'.", file=sys.stderr)
        return 1

    web = dual.web
    # Build current collection data map
    coll_map_apply: dict[str, dict] = {}
    start = 0
    while True:
        chunk = web.collections(limit=100, start=start)
        if not chunk:
            break
        for c in chunk:
            d = c.get("data", {})
            coll_map_apply[d.get("key", "")] = d
        if len(chunk) < 100:
            break
        start += 100

    moved = 0
    skipped = 0
    errors = 0
    for cluster in clusters:
        key = (cluster.zotero_collection_key or "").strip()
        d = coll_map_apply.get(key, {})
        current_parent = d.get("parentCollection")
        if current_parent == parent_key:
            print(f"  [skip] {cluster.slug} ({key}) already nested under {parent_key}")
            skipped += 1
            continue
        try:
            dual.update_collection(key, parent_key=parent_key)
            print(f"  [ok]   {cluster.slug} ({key}) reparented under {parent_key}")
            moved += 1
        except Exception as exc:
            print(f"  [err]  {cluster.slug} ({key}): {exc}", file=sys.stderr)
            errors += 1

    print(f"\nDone: {moved} moved, {skipped} already nested, {errors} error(s).")
    return 0 if errors == 0 else 1

def _zotero_gc(
    *,
    apply: bool,
    yes: bool,
    no_test_pattern: bool,
    age_days: int,
    respect_kept: bool = True,
) -> int:
    cfg = get_config()
    from research_hub.clusters import slugify
    from research_hub.zotero.client import get_client
    from research_hub.zotero.gc import (
        delete_candidates,
        load_kept_keys,
        scan_zotero_for_gc,
    )

    registry = ClusterRegistry(cfg.clusters_file)
    clusters = registry.list()
    vault_keys = {
        (cluster.zotero_collection_key or "").strip()
        for cluster in clusters
        if (cluster.zotero_collection_key or "").strip()
    }
    vault_name_slugs = {
        slugify(cluster.name)
        for cluster in clusters
        if (cluster.name or "").strip()
    } | {
        (cluster.slug or "").strip()
        for cluster in clusters
        if (cluster.slug or "").strip()
    }
    kept_keys = load_kept_keys(cfg.research_hub_dir) if respect_kept else set()
    zot = get_client()
    candidates = scan_zotero_for_gc(
        zot,
        vault_keys,
        include_test_pattern=not no_test_pattern,
        age_days=age_days,
        kept_keys=kept_keys,
        vault_name_slugs=vault_name_slugs,
    )
    if not candidates:
        print("No Zotero GC candidates found.")
        return 0

    def _is_non_empty(c) -> bool:
        return c.num_items > 0 or c.num_collections > 0

    junk = [c for c in candidates if not _is_non_empty(c)]
    non_empty = [c for c in candidates if _is_non_empty(c)]

    def _print_rows(rows) -> None:
        for candidate in rows:
            print(
                f"{candidate.key}\t{candidate.name}\t{candidate.num_items}\t"
                f"{candidate.num_collections}\t{', '.join(candidate.reasons)}"
            )

    print("key\tname\titems\tsubcollections\treasons")
    _print_rows(junk)
    if non_empty:
        print("")
        print(
            f"-- NON-EMPTY ORPHANS ({len(non_empty)}) -- review only; gc "
            f"CANNOT delete these (hard-skipped at the delete layer). If "
            f"they are stale duplicates, reconcile via cluster rebind/merge --"
        )
        _print_rows(non_empty)
    if not apply:
        print("")
        print("Preview only. Re-run with --apply to delete candidates.")
        return 0

    # `delete_candidates` already hard-skips any non-empty collection
    # (gc.py). PR-A makes that pre-existing guarantee *honest* at the
    # selection layer too: non-empty orphans are never even offered for
    # deletion (no misleading "type name to delete" prompt that the
    # delete layer would then refuse) — they are listed for review only.
    # Reuse the partition computed above for the grouped display.
    non_empty_skipped = len(non_empty)
    deletable = junk

    if not yes:
        kept: list = []
        for candidate in deletable:
            answer = input(
                f"Delete {candidate.name} ({candidate.key})? [y/N] "
            ).strip().lower()
            if answer in {"y", "yes"}:
                kept.append(candidate)
        selected = kept
    else:
        # --yes auto-selects only safe junk: empty + test-pattern +
        # orphan-from-vault, all three (on the already non-empty-filtered set).
        selected = [
            candidate
            for candidate in deletable
            if any(reason.startswith("empty>") for reason in candidate.reasons)
            and any(reason.startswith("test-pattern(") for reason in candidate.reasons)
            and "orphan-from-vault" in candidate.reasons
        ]
    if non_empty_skipped:
        print(
            f"Skipped {non_empty_skipped} non-empty orphan(s) -- gc cannot "
            f"delete these (hard-skipped at the delete layer). Reconcile via "
            f"cluster rebind/merge if they are stale duplicates."
        )
    results = delete_candidates(zot, selected)
    ok_count = sum(1 for status in results.values() if status == "ok")
    print(f"Deleted {ok_count}/{len(selected)} collection(s).")
    return 0

def _zotero_backfill(args) -> int:
    from research_hub.zotero_hygiene import run_backfill

    cfg = get_config()
    cluster_slugs = [args.cluster] if args.cluster else None
    report = run_backfill(
        cfg,
        cluster_slugs=cluster_slugs,
        do_tags=args.tags,
        do_notes=args.notes,
        apply=args.apply,
        progress=print,
    )
    print(report.summary())
    if args.apply and report.report_path:
        print(f"Markdown report saved: {report.report_path}")
    return 0

def _load_zotero_if_configured():
    """Lazy-load Zotero client. Returns None if not configured.

    v0.90.0 G1#1 fix: distinguish "not configured" (silent None) from
    "configured but broken" (warn to stderr, still return None). Pre-fix,
    the bare ``except Exception`` made auth failures, network outages, and
    missing imports all look identical to "no Zotero set up", so users
    saw zero ingestion and assumed they hadn't configured Zotero when in
    reality the client was broken.
    """
    try:
        from research_hub.errors import MissingCredential
        from research_hub.zotero.client import get_client

        return get_client()
    except MissingCredential:
        # Truly unconfigured -- silent None preserves lazy-mode UX
        return None
    except Exception as exc:
        # Configured but broken -- surface root cause so user can act
        print(
            f"  [zotero] WARN credentials present but client init failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None
