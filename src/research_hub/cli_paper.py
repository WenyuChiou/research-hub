"""Paper CLI handlers for Research Hub (ARCH-2 split from cli.py)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import subprocess
import sys
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config, require_config
from research_hub.operations import add_paper, mark_paper, move_paper, remove_paper
from research_hub.security import ValidationError, safe_join, validate_slug
from research_hub.vault_search import search_vault
from research_hub.verify import verify_arxiv, verify_doi, verify_paper
from research_hub.cli_common import (
    _emit_cli_json,
    _read_zotero_key_from_frontmatter,
)

_PAPER_FRONTMATTER_RE = re.compile(r"\A(---\r?\n)(.*?)(\r?\n---)(.*)\Z", re.DOTALL)


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


def _quarantine(args) -> int:
    from research_hub.authenticity import list_quarantine, restore_quarantine, show_quarantine

    cfg = get_config()
    if args.quarantine_command == "list":
        rows = list_quarantine(cfg, cluster=getattr(args, "cluster", None))
        if not rows:
            print("no quarantined candidates")
            return 0
        print(f"{'cluster':24} {'slug':32} {'layer':6} {'reason':24} date")
        for row in rows:
            print(
                f"{row['cluster'][:24]:24} "
                f"{row['slug'][:32]:32} "
                f"{row['layer'][:6]:6} "
                f"{row['reason'][:24]:24} "
                f"{row['date']}"
            )
        return 0
    if args.quarantine_command == "show":
        try:
            payload = show_quarantine(cfg, args.slug, cluster=getattr(args, "cluster", None))
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.quarantine_command == "restore":
        try:
            result = restore_quarantine(cfg, args.slug, args.cluster)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"restored {result['slug']} to {result['papers_input']}")
        return 0
    return 2


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


def _parse_bulk_slugs(slugs_arg: str | None, slugs_file: str | None) -> list[str]:
    values: list[str] = []
    if slugs_arg:
        values.extend(slug.strip() for slug in slugs_arg.split(","))
    if slugs_file:
        text = Path(slugs_file).read_text(encoding="utf-8")
        for line in text.splitlines():
            values.extend(part.strip() for part in line.split(","))
    return [slug for slug in values if slug]


def _manifest_batch_label(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"


def _paper_enrich_existing(
    cluster_slug: str,
    *,
    limit: int,
    apply: bool,
    rate_limit: float,
) -> int:
    cfg = get_config()
    from research_hub.manifest import Manifest, new_entry
    from research_hub.vault.sync import list_zotero_collection_items
    from research_hub.zotero.client import get_client
    from research_hub.zotero.enrich import apply_enrichment, plan_enrichment

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        print(f"Cluster not found: {cluster_slug}", file=sys.stderr)
        return 2
    if not cluster.zotero_collection_key:
        print(f"{cluster_slug} has no Zotero collection binding", file=sys.stderr)
        return 2

    zot = get_client()
    items = list_zotero_collection_items(zot, cluster.zotero_collection_key)
    if limit > 0:
        items = items[:limit]
    pdfs_dir = cfg.root / "pdfs"
    plans = plan_enrichment(
        items,
        pdfs_dir=pdfs_dir,
        disable_pdf_fallback=getattr(cfg, "disable_pdf_fallback", False),
    )
    if not plans:
        print("No enrichment candidates found.")
        return 0

    print("item_key\ttitle\tdoi\tfields")
    for plan in plans:
        print(
            f"{plan.item_key}\t{plan.title}\t{plan.doi}\t"
            f"{', '.join(sorted(plan.fields_to_fill))}"
        )
    if not apply:
        print("")
        print("Preview only. Re-run with --apply to write metadata back to Zotero.")
        return 0

    try:
        results = apply_enrichment(
            zot,
            plans,
            rate_limit_rps=rate_limit,
            cfg=cfg,
            cluster_slug=cluster_slug,
        )
    except TypeError as exc:
        if "unexpected keyword" not in str(exc):
            raise
        results = apply_enrichment(zot, plans, rate_limit_rps=rate_limit)
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")
    batch_label = _manifest_batch_label("enrich")
    ok_count = 0
    for plan in plans:
        status = results.get(plan.item_key, "")
        if status != "ok":
            continue
        ok_count += 1
        manifest.append(
            new_entry(
                cluster=cluster_slug,
                query=cluster.first_query or cluster.name,
                action="enrich-existing",
                doi=plan.doi,
                title=plan.title,
                zotero_key=plan.item_key,
                batch_label=batch_label,
            )
        )
    print(f"Applied enrichment to {ok_count}/{len(plans)} item(s).")
    return 0


def _paper_attach_pdfs(
    cluster_slug: str,
    *,
    limit: int,
    apply: bool,
    rate_limit: float,
    include_publisher_link: bool = False,
    keep_url_fallback: bool = False,
    max_pdf_size_mb: int = 25,
) -> int:
    cfg = get_config()
    from research_hub.manifest import Manifest, new_entry
    from research_hub.vault.sync import list_zotero_collection_items
    from research_hub.zotero.client import get_client
    from research_hub.zotero.pdf_attach import attach_pdfs, plan_attach_for_items

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        print(f"Cluster not found: {cluster_slug}", file=sys.stderr)
        return 2
    if not cluster.zotero_collection_key:
        print(f"{cluster_slug} has no Zotero collection binding", file=sys.stderr)
        return 2

    zot = get_client()
    items = list_zotero_collection_items(zot, cluster.zotero_collection_key)
    if limit > 0:
        items = items[:limit]
    plans = plan_attach_for_items(
        items,
        unpaywall_email=getattr(cfg, "unpaywall_email", ""),
        include_publisher_link=include_publisher_link,
    )

    print("item_key\tsource\turl\ttitle")
    for plan in plans:
        chosen_url = plan.pdf_url or plan.publisher_url or "-"
        print(f"{plan.item_key}\t{plan.source or '-'}\t{chosen_url}\t{plan.title}")
    if not apply:
        print("")
        print("Preview only. Re-run with --apply to attach PDFs.")
        return 0

    results = attach_pdfs(
        zot,
        plans,
        rate_limit_rps=rate_limit,
        keep_url_fallback=keep_url_fallback,
        max_pdf_size_mb=max_pdf_size_mb,
        cfg=cfg,
    )
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")
    batch_label = _manifest_batch_label("pdf-attach")
    ok_count = 0
    title_by_key = {item.get("key", ""): str(item.get("data", {}).get("title", "") or "") for item in items}
    doi_by_key = {item.get("key", ""): str(item.get("data", {}).get("DOI", "") or "") for item in items}
    for item_key, status in results.items():
        if not status.startswith("ok"):
            continue
        ok_count += 1
        manifest.append(
            new_entry(
                cluster=cluster_slug,
                query=cluster.first_query or cluster.name,
                action="pdf-attach",
                doi=doi_by_key.get(item_key, ""),
                title=title_by_key.get(item_key, ""),
                zotero_key=item_key,
                batch_label=batch_label,
            )
        )
    print(f"Attached PDFs to {ok_count}/{len(plans)} item(s).")
    return 0


def _summary_block_has_todo(md_path: Path) -> bool:
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    match = re.search(r"^##\s+Summary\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return False
    summary_block = match.group(1)
    return "[TODO]" in summary_block or "[TODO:" in summary_block


def _paper_upgrade_pdfs(
    cluster_slug: str,
    *,
    apply: bool,
    limit: int,
) -> int:
    cfg = get_config()
    from research_hub.zotero.client import get_client
    from research_hub.zotero.pdf_attach import upgrade_pdfs_in_cluster

    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        print(f"Cluster not found: {cluster_slug}", file=sys.stderr)
        return 2
    if not cluster.zotero_collection_key:
        print(f"{cluster_slug} has no Zotero collection binding", file=sys.stderr)
        return 2

    zot = get_client()
    upgrade_pdfs_in_cluster(
        zot,
        cluster.zotero_collection_key,
        apply=apply,
        limit=limit,
    )
    return 0


def _paper_resummarize(
    cluster_slug: str,
    *,
    apply: bool,
    llm_cli: str | None,
) -> int:
    from research_hub import summarize as summarize_mod

    cfg = get_config()
    registry = ClusterRegistry(cfg.clusters_file)
    cluster = registry.get(cluster_slug)
    if cluster is None:
        print(f"Cluster not found: {cluster_slug}", file=sys.stderr)
        return 2

    cluster_dir = Path(cfg.raw) / (cluster.obsidian_subfolder or cluster.slug)
    if not cluster_dir.exists():
        print(f"Cluster note directory not found: {cluster_dir}", file=sys.stderr)
        return 2

    paper_keys: list[str] = []
    for note_path in sorted(cluster_dir.glob("*.md")):
        if note_path.name in {"00_overview.md", "index.md"}:
            continue
        if not _summary_block_has_todo(note_path):
            continue
        zotero_key = _read_zotero_key_from_frontmatter(note_path)
        if zotero_key:
            paper_keys.append(zotero_key)

    if not paper_keys:
        print("No papers with [TODO] summary blocks found.")
        return 0

    report = summarize_mod.summarize_cluster(
        cfg,
        cluster_slug,
        llm_cli=llm_cli,
        apply=apply,
        paper_keys=paper_keys,
    )
    if not report.ok:
        print(f"resummarize failed: {report.error}", file=sys.stderr)
        return 1
    if report.prompt_path:
        print(f"no LLM CLI on PATH; prompt saved to {report.prompt_path}")
        print("pipe it through your LLM CLI and re-run with --apply")
        return 0
    print(f"cli used: {report.cli_used}")
    if not apply:
        print(f"(dry-run on {len(paper_keys)} paper(s); pass --apply to write to Obsidian + Zotero)")
        return 0
    apply_result = report.apply_result
    if apply_result is None:
        print("no apply result returned")
        return 1
    print(
        f"applied: {len(apply_result.applied)}  "
        f"skipped: {len(apply_result.skipped)}  "
        f"errors: {len(apply_result.errors)}"
    )
    print(f"obsidian writes: {apply_result.obsidian_writes}, zotero writes: {apply_result.zotero_writes}")
    for skip in apply_result.skipped:
        print(f"  SKIP {skip}")
    for err in apply_result.errors:
        print(f"  ERROR {err}", file=sys.stderr)
    return 0 if not apply_result.errors else 1


def _read_paper_frontmatter(text: str) -> dict:
    """Read a markdown YAML frontmatter block into a dict."""
    match = _PAPER_FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        import yaml

        parsed = yaml.safe_load(match.group(2)) or {}
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _update_paper_frontmatter(text: str, updates: dict) -> str:
    """Update a markdown YAML frontmatter block while preserving body text."""
    import yaml

    match = _PAPER_FRONTMATTER_RE.match(text)
    if not match:
        frontmatter = yaml.safe_dump(
            updates,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip()
        return f"---\n{frontmatter}\n---\n{text}"
    frontmatter = _read_paper_frontmatter(text)
    frontmatter.update(updates)
    new_frontmatter = yaml.safe_dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip()
    return f"{match.group(1)}{new_frontmatter}{match.group(3)}{match.group(4)}"


def _frontmatter_field_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_frontmatter_field_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_frontmatter_field_text(item) for item in value)
    return str(value)


def _topic_cluster_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _iter_raw_cluster_dirs(cfg, cluster_slug: str | None = None) -> list[tuple[str, Path]]:
    raw_root = Path(cfg.raw)
    if cluster_slug:
        return [(cluster_slug, safe_join(raw_root, cluster_slug))]
    if not raw_root.exists():
        return []
    return [
        (path.name, path)
        for path in sorted(raw_root.iterdir(), key=lambda p: p.name)
        if path.is_dir() and not path.name.startswith(".") and not path.name.startswith("_")
    ]


def _display_paper_path(cfg, path: Path) -> str:
    roots: list[Path] = []
    if getattr(cfg, "root", None) is not None:
        roots.append(Path(cfg.root))
    if getattr(cfg, "raw", None) is not None:
        roots.append(Path(cfg.raw).parent)
    for root in roots:
        try:
            return str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
    return str(path).replace("\\", "/")


def _find_paper_by_slug_or_doi(cfg, slug_or_doi: str) -> tuple[str, Path, dict, str] | None:
    """Find a paper by filename stem or DOI across all cluster dirs.

    If the same stem/DOI appears in multiple clusters, a warning is printed to
    stderr (listing all matches) and the first alphabetical match is returned.
    Callers can disambiguate by passing a --cluster flag (not handled here).
    """
    needle = str(slug_or_doi).strip()
    needle_lower = needle.lower()
    all_matches: list[tuple[str, Path, dict, str]] = []
    for cluster_slug, cluster_dir in _iter_raw_cluster_dirs(cfg):
        if not cluster_dir.exists():
            continue
        for paper_path in sorted(cluster_dir.glob("*.md"), key=lambda p: p.name):
            try:
                text = paper_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            frontmatter = _read_paper_frontmatter(text)
            doi = str(frontmatter.get("doi", "") or "").strip().lower()
            if paper_path.stem == needle or doi == needle_lower:
                all_matches.append((cluster_slug, paper_path, frontmatter, text))
    if not all_matches:
        return None
    if len(all_matches) > 1:
        locs = ", ".join(f"{m[0]}/{m[1].name}" for m in all_matches)
        print(
            f"Warning: '{needle}' matched in {len(all_matches)} clusters: {locs}. "
            "Using first match. Pass a more specific identifier to disambiguate.",
            file=sys.stderr,
        )
    return all_matches[0]


def _cmd_paper_find(cfg, args) -> None:
    """Handle `paper find` command. cfg: HubConfig, args: argparse namespace."""
    query = str(args.query).strip()
    query_lower = query.lower()
    by = getattr(args, "by", "any")
    matches: list[tuple[str, Path, dict]] = []

    for cluster_slug, cluster_dir in _iter_raw_cluster_dirs(cfg, getattr(args, "cluster", None)):
        if not cluster_dir.exists():
            continue
        for paper_path in sorted(cluster_dir.glob("*.md"), key=lambda p: p.name):
            try:
                text = paper_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            frontmatter = _read_paper_frontmatter(text)
            fields: list[str] = []
            if by in {"title", "any"}:
                fields.append(_frontmatter_field_text(frontmatter.get("title")))
            if by in {"doi", "any"}:
                fields.append(_frontmatter_field_text(frontmatter.get("doi")))
            if by in {"author", "any"}:
                fields.append(_frontmatter_field_text(frontmatter.get("author")))
                fields.append(_frontmatter_field_text(frontmatter.get("authors")))
            if any(query_lower in field.lower() for field in fields if field):
                matches.append((cluster_slug, paper_path, frontmatter))

    if not matches:
        print(f"No papers matched '{query}'.")
    for cluster_slug, paper_path, frontmatter in matches:
        print(f"[{cluster_slug}] {_display_paper_path(cfg, paper_path)}")
        print(f"  Title: {_frontmatter_field_text(frontmatter.get('title'))}")
        print(f"  DOI: {_frontmatter_field_text(frontmatter.get('doi'))}")
    print(f"Found {len(matches)} paper(s).")


def _cmd_paper_add_to_cluster(cfg, args) -> None:
    """Handle `paper add-to-cluster` command."""
    target_cluster = str(args.target_cluster).strip()
    try:
        target_cluster = validate_slug(target_cluster, field="--cluster")
    except ValidationError as exc:
        print(f"Invalid cluster name: {exc}", file=sys.stderr)
        return
    match = _find_paper_by_slug_or_doi(cfg, args.slug_or_doi)
    if match is None:
        print(f"No paper matching '{args.slug_or_doi}' found in any cluster.")
        return

    _, paper_path, frontmatter, text = match
    clusters = _topic_cluster_list(frontmatter.get("topic_cluster"))
    if target_cluster in clusters:
        print(f"Already in cluster '{target_cluster}', no change needed.")
        return

    updated_clusters = [*clusters, target_cluster]
    updated_text = _update_paper_frontmatter(text, {"topic_cluster": updated_clusters})
    display_path = _display_paper_path(cfg, paper_path)
    if getattr(args, "dry_run", False):
        print(f"Would add topic_cluster: [{target_cluster}] to {display_path}")
        return

    paper_path.write_text(updated_text, encoding="utf-8")
    print(f"Added topic_cluster: [{target_cluster}] to {display_path}")


def _cmd_paper_gaps(cfg, args) -> None:
    """Handle `paper gaps` command — research gap analysis for a cluster."""
    from research_hub.gap_analysis import (
        build_cluster_digest,
        emit_gap_prompt,
        apply_gap_results,
        save_gap_prompt,
        emit_cross_cluster_gap_prompt,
        cross_cluster_gap,
    )
    from research_hub.llm_cli import detect_llm_cli, invoke_llm_cli

    slug = str(args.cluster).strip()
    no_llm = bool(getattr(args, "no_llm", False))
    forced_cli = getattr(args, "llm_cli", None)
    compare_slug = getattr(args, "compare_cluster", None)

    # F4b: Cross-cluster gap analysis
    if compare_slug:
        digest_a = build_cluster_digest(cfg, slug)
        digest_b = build_cluster_digest(cfg, compare_slug)
        # Require both clusters to have at least some papers for a meaningful cross-analysis
        if digest_a.paper_count == 0 or digest_b.paper_count == 0:
            empty = slug if digest_a.paper_count == 0 else compare_slug
            print(
                f"[gaps] Cluster '{empty}' has no papers. "
                "Cannot run cross-cluster analysis.",
                file=sys.stderr,
            )
            return
        cross_prompt = emit_cross_cluster_gap_prompt(digest_a, digest_b)
        cross_prompt_path = save_gap_prompt(cfg, f"{slug}-x-{compare_slug}", cross_prompt)
        cli_name = None if no_llm else (forced_cli or detect_llm_cli())
        if cli_name is None:
            print(
                f"[gaps] No LLM CLI detected (or --no-llm).\n"
                f"[gaps] Cross-cluster prompt saved to: {cross_prompt_path}"
            )
            return
        print(f"[gaps] Invoking {cli_name} for cross-cluster analysis ({slug} x {compare_slug})...")
        try:
            gap_text = invoke_llm_cli(cli_name, cross_prompt, timeout_sec=300)
        except Exception as exc:
            print(f"[gaps] LLM invocation failed: {exc}", file=sys.stderr)
            print(f"[gaps] Prompt saved: {cross_prompt_path}", file=sys.stderr)
            return
        if not gap_text.strip():
            print("[gaps] LLM returned empty response.", file=sys.stderr)
            print(f"[gaps] Prompt saved: {cross_prompt_path}", file=sys.stderr)
            return
        result = cross_cluster_gap(cfg, slug, compare_slug, gap_text)
        if result.written:
            print(f"[gaps] Cross-cluster gap file: {result.gap_path}")
        return

    print(f"[gaps] Building digest for cluster '{slug}'...")
    digest = build_cluster_digest(cfg, slug)
    if digest.paper_count == 0:
        print(f"No papers found in cluster '{slug}'. Nothing to analyze.", file=sys.stderr)
        return

    print(f"[gaps] {digest.paper_count} papers found. Generating prompt...")
    prompt = emit_gap_prompt(digest)

    # Save prompt for manual use regardless of LLM availability
    prompt_path = save_gap_prompt(cfg, slug, prompt)

    # Determine whether to invoke an LLM CLI
    cli_name = None if no_llm else (forced_cli or detect_llm_cli())

    if cli_name is None:
        print(
            f"[gaps] No LLM CLI detected (or --no-llm).\n"
            f"[gaps] Prompt saved to: {prompt_path}\n"
            f"[gaps] To run manually:\n"
            f"  1. <llm-cli> < {prompt_path} > /tmp/gap-result.md\n"
            f"  2. Copy /tmp/gap-result.md to your hub/{slug}/ directory as research-gaps.md"
        )
        return

    print(f"[gaps] Invoking {cli_name}...")
    try:
        gap_text = invoke_llm_cli(cli_name, prompt, timeout_sec=300)
    except Exception as exc:
        print(f"[gaps] LLM invocation failed: {exc}", file=sys.stderr)
        print(f"[gaps] Prompt saved for manual use: {prompt_path}")
        return

    if not gap_text.strip():
        print(
            "[gaps] LLM returned empty response.",
            file=sys.stderr,
        )
        print(f"[gaps] Prompt saved for manual use: {prompt_path}")
        return

    print("[gaps] Writing research-gaps.md...")
    result = apply_gap_results(cfg, slug, gap_text)
    if result.written:
        print(f"[gaps] Written: {result.research_gaps_path}")
        if result.overview_updated:
            print("[gaps] Updated 00_overview.md with gap summary.")
    else:
        print("[gaps] Failed to write output.", file=sys.stderr)


def _paper_command(args) -> int:
    emit_json = bool(getattr(args, "json", False))
    if args.paper_command == "find":
        cfg = require_config()
        _cmd_paper_find(cfg, args)
        return 0
    if args.paper_command == "add-to-cluster":
        cfg = require_config()
        _cmd_paper_add_to_cluster(cfg, args)
        return 0
    if args.paper_command == "gaps":
        cfg = require_config()
        _cmd_paper_gaps(cfg, args)
        return 0
    if args.paper_command == "lookup-doi":
        from research_hub.doi_lookup import batch_lookup_missing_dois, lookup_doi_for_slug

        cfg = get_config()
        if args.batch:
            if not args.cluster:
                print("--batch requires --cluster", file=sys.stderr)
                return 2
            # v0.65: warn about Zotero auto-sync side effect. Each rewrite
            # of an Obsidian frontmatter file triggers Zotero desktop's file
            # watcher, which can cascade into repeated re-auth prompts that
            # open https://www.zotero.org/settings/keys in your browser.
            print(
                "Note: --batch will rewrite Obsidian notes for any paper "
                "with a Crossref match. If Zotero desktop is running with "
                "file watcher / auto-sync, you may see "
                "zotero.org/settings/keys re-auth prompts during the run. "
                "Pause Zotero auto-sync first, or use single-paper "
                "`research-hub paper lookup-doi <slug>` instead."
            )
            result = batch_lookup_missing_dois(cfg, args.cluster)
            updated = sum(1 for item in result["results"] if item.get("status") == "updated")
            print(f"updated: {updated}")
            print(f"log: {result['log_path']}")
            return 0
        if not args.slug:
            print("Usage: research-hub paper lookup-doi <slug>", file=sys.stderr)
            return 2
        try:
            result = lookup_doi_for_slug(cfg, args.slug)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if result["status"] == "updated":
            print(f"updated: {result['slug']} -> {result['doi']}")
            return 0
        print(f"{result['slug']}: {result.get('reason', result['status'])}")
        return 1 if result["status"] == "no-match" else 0
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
    if args.paper_command == "bulk-relabel":
        from research_hub.paper import bulk_relabel

        cfg = get_config()
        result = bulk_relabel(
            cfg,
            args.from_label,
            args.to_label,
            cluster_slug=args.cluster,
            dry_run=not args.apply,
        )
        if emit_json:
            _emit_cli_json("paper bulk-relabel", 0, result)
            return 0
        action = "would relabel" if not args.apply else "relabeled"
        print(f"{action} {len(result['changed'])} paper(s)")
        for change in result["changed"]:
            print(f"  - {change['slug']} ({change['cluster']})")
        if result.get("zotero_errors"):
            for error in result["zotero_errors"]:
                print(f"  Zotero warning: {error['error']}", file=sys.stderr)
        return 0
    if args.paper_command == "bulk-move":
        from research_hub.paper import bulk_move

        cfg = get_config()
        slugs = _parse_bulk_slugs(args.slugs, args.slugs_file)
        try:
            result = bulk_move(
                cfg,
                slugs,
                args.to_cluster,
                dry_run=not args.apply,
            )
        except ValueError as exc:
            if emit_json:
                _emit_cli_json(
                    "paper bulk-move",
                    2,
                    {
                        "slugs": slugs,
                        "to_cluster": args.to_cluster,
                        "error": str(exc),
                    },
                )
                return 2
            print(str(exc), file=sys.stderr)
            return 2
        rc = 0 if not result["missing"] else 1
        if emit_json:
            _emit_cli_json("paper bulk-move", rc, result)
            return rc
        action = "would move" if not args.apply else "moved"
        print(f"{action} {len(result['would_move']) if not args.apply else len(result['moved'])} paper(s)")
        if result["missing"]:
            print(f"missing: {', '.join(result['missing'])}")
        for skipped in result["skipped"]:
            print(f"skipped: {skipped['slug']} ({skipped['reason']})")
        if result.get("zotero_errors"):
            for error in result["zotero_errors"]:
                print(f"  Zotero warning: {error['error']}", file=sys.stderr)
        return rc
    if args.paper_command == "bulk-delete":
        from research_hub.paper import bulk_delete_by_tag

        cfg = get_config()
        result = bulk_delete_by_tag(
            cfg,
            args.by_tag,
            dry_run=not args.apply,
        )
        if emit_json:
            _emit_cli_json("paper bulk-delete", 0, result)
            return 0
        action = "would delete" if not args.apply else "deleted"
        count = len(result["would_delete"]) if not args.apply else len(result["deleted"])
        print(f"{action} {count} paper(s) tagged {args.by_tag!r}")
        for candidate in result["would_delete"]:
            print(f"  - {candidate['slug']} ({candidate['cluster']})")
        if result.get("zotero_errors"):
            for error in result["zotero_errors"]:
                print(f"  Zotero warning: {error['error']}", file=sys.stderr)
        return 0
    if args.paper_command == "retype":
        from research_hub.paper import retype_paper

        cfg = get_config()
        report = retype_paper(
            cfg,
            args.slug,
            target_type=args.to_type,
            dry_run=not args.apply,
        )
        mode = "dry-run" if not args.apply else "applied"
        rc = 1 if report.get("errors") else 0
        if emit_json:
            _emit_cli_json("paper retype", rc, report)
            return rc
        print(f"paper retype ({mode}): {report['slug']}")
        if report.get("errors"):
            for err in report["errors"]:
                print(f"  [ERR] {err}", file=sys.stderr)
            return rc
        print(f"  from: {report['from_type']}")
        print(f"  to:   {report['to_type']}")
        print(f"  old zotero-key: {report['old_zotero_key']}")
        if report.get("new_zotero_key"):
            print(f"  new zotero-key: {report['new_zotero_key']}")
        print(f"  fields copied:  {len(report['fields_copied'])}")
        if report.get("fields_dropped"):
            print(f"  fields dropped: {report['fields_dropped']}")
        if not args.apply:
            print("\nRe-run with --apply to perform the change.")
        return rc
    if args.paper_command == "enrich-existing":
        return _paper_enrich_existing(
            args.cluster,
            limit=args.limit,
            apply=args.apply,
            rate_limit=args.rate_limit,
        )
    if args.paper_command == "attach-pdfs":
        return _paper_attach_pdfs(
            args.cluster,
            limit=args.limit,
            apply=args.apply,
            rate_limit=args.rate_limit,
            include_publisher_link=getattr(args, "include_publisher_link", False),
            keep_url_fallback=getattr(args, "keep_url_fallback", False),
            max_pdf_size_mb=getattr(args, "max_pdf_size_mb", 25),
        )
    if args.paper_command == "upgrade-pdfs":
        return _paper_upgrade_pdfs(
            args.cluster,
            apply=args.apply,
            limit=args.limit,
        )
    if args.paper_command == "resummarize":
        return _paper_resummarize(
            args.cluster,
            apply=args.apply,
            llm_cli=args.llm_cli,
        )
    if args.paper_command == "summarize":
        return _paper_summarize_pending(args)
    return 2


def _paper_summarize_pending(args) -> int:
    from collections import Counter

    from research_hub.paper_summarize import summarize_pending

    if not args.pending:
        print("Specify --pending to run the summarize queue.", file=sys.stderr)
        return 2
    cfg = get_config()
    try:
        results = summarize_pending(
            cfg,
            cluster_slug_filter=args.cluster,
            backend=args.cli,
            max_papers=args.max_papers,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"paper summarize failed: {exc}", file=sys.stderr)
        return 1

    counts = Counter(result.action for result in results)
    print(
        f"processed: {len(results)}  "
        f"done: {counts.get('done', 0)}  "
        f"failed_no_abstract: {counts.get('failed_no_abstract', 0)}  "
        f"errors: {counts.get('error', 0)}"
    )
    if args.dry_run:
        print(
            f"dry-run: would_summarize={counts.get('would_summarize', 0)}  "
            f"would_fail_no_abstract={counts.get('would_fail_no_abstract', 0)}"
        )
    for result in results:
        if result.error:
            print(f"  ERROR {result.path}: {result.error}", file=sys.stderr)
    return 0 if not counts.get("error", 0) else 1
