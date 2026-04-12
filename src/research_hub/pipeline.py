from __future__ import annotations

import argparse
import json
import os
import re
import time
import traceback
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.dedup import DedupHit, DedupIndex, build_from_obsidian, build_from_zotero
from research_hub.manifest import Manifest, new_entry
from research_hub.verify import VerificationResult, VerifyCache, verify_arxiv, verify_doi, verify_paper
from research_hub.vault.link_updater import update_cluster_links
from research_hub.zotero.client import add_note, check_duplicate, get_client
from research_hub.zotero.fetch import make_raw_md


def _validate_paper_input(pp: dict, idx: int) -> list[str]:
    """Validate one paper entry before any Zotero writes."""
    errors: list[str] = []
    required = ["title", "doi", "authors", "year"]
    for field in required:
        if field not in pp:
            errors.append(f"Paper {idx}: missing required field '{field}'")
    if "authors" in pp:
        if not isinstance(pp["authors"], list):
            errors.append(f"Paper {idx}: 'authors' must be a list")
        else:
            for author_index, author in enumerate(pp["authors"]):
                if isinstance(author, dict):
                    if "creatorType" not in author:
                        errors.append(
                            f"Paper {idx}, author {author_index}: dict authors must have "
                            f"'creatorType' (use 'author', 'editor', etc. - required by Zotero API)"
                        )
                    if not (author.get("name") or author.get("lastName")):
                        errors.append(
                            f"Paper {idx}, author {author_index}: dict authors need 'name' "
                            f"or 'lastName'"
                        )
                elif not isinstance(author, str):
                    errors.append(
                        f"Paper {idx}, author {author_index}: must be string or dict, got "
                        f"{type(author).__name__}"
                    )
    return errors


def _write_error_log(logs_dir: Path, errors: list[dict]) -> Path:
    log_path = logs_dir / f"pipeline_errors_{int(time.time())}.jsonl"
    with log_path.open("w", encoding="utf-8") as error_file:
        for err in errors:
            error_file.write(json.dumps(err, ensure_ascii=False) + "\n")
    return log_path


def _resolve_log_path(preferred_logs_dir: Path) -> Path:
    preferred_log_path = preferred_logs_dir / "pipeline_log.txt"
    try:
        preferred_logs_dir.mkdir(parents=True, exist_ok=True)
        with preferred_log_path.open("a", encoding="utf-8"):
            pass
        return preferred_log_path
    except PermissionError:
        fallback_logs_dir = Path.cwd() / ".research_hub_logs"
        fallback_logs_dir.mkdir(parents=True, exist_ok=True)
        return fallback_logs_dir / "pipeline_log.txt"


def append_cluster_query_to_existing(
    note_path: Path,
    query: str,
    *,
    topic_cluster: str = "",
) -> bool:
    """Append query to cluster_queries in a note frontmatter, idempotently.

    If the note pre-dates v0.3.0 and lacks the ``cluster_queries`` field,
    the missing v0.3.0 fields (``cluster_queries``, ``topic_cluster``,
    ``verified``, ``status``) are inserted before the closing ``---``.
    """
    if not note_path.exists():
        return False
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end < 0:
        return False
    frontmatter = text[3:end]
    pattern = re.compile(r"^cluster_queries:\s*\[(.*?)\]$", re.MULTILINE)
    match = pattern.search(frontmatter)
    if match:
        current = [
            value.strip().strip('"').strip("'")
            for value in match.group(1).split(",")
            if value.strip()
        ]
        if query in current:
            return False
        updated = current + [query]
        replacement = "cluster_queries: [" + ", ".join(f'"{value}"' for value in updated) + "]"
        updated_frontmatter = pattern.sub(replacement, frontmatter, count=1)
    else:
        # Legacy note (pre-v0.3.0): append the new v0.3.0 fields.
        new_fields_lines = [""]
        if not re.search(r"^topic_cluster:", frontmatter, re.MULTILINE):
            new_fields_lines.append(f'topic_cluster: "{topic_cluster}"')
        new_fields_lines.append(f'cluster_queries: ["{query}"]')
        if not re.search(r"^verified:", frontmatter, re.MULTILINE):
            new_fields_lines.append("verified: false")
        if not re.search(r"^status:", frontmatter, re.MULTILINE):
            new_fields_lines.append("status: unread")
        updated_frontmatter = frontmatter.rstrip() + "\n".join(new_fields_lines)
    note_path.write_text(text[:3] + updated_frontmatter + text[end:], encoding="utf-8")
    return True


def _query_for_paper(paper: dict, query: str | None = None) -> str:
    return query or paper.get("query") or paper.get("search_query") or paper["title"]


def _extract_arxiv_id_from_url_or_doi(url: str, doi: str) -> str:
    text = f"{url or ''} {doi or ''}"
    match = re.search(r"(?:arxiv(?:\.org/abs/|[.:/])|/abs/)(\d{4}\.\d{4,5}(?:v\d+)?)", text, re.IGNORECASE)
    return match.group(1) if match else ""


def _folder_for_paper(cfg, paper: dict, cluster_slug: str | None) -> Path:
    if cluster_slug:
        return cfg.raw / cluster_slug
    return cfg.root / "raw" / paper["sub_category"]


def _load_or_build_dedup(cfg, zot=None, *, dry_run: bool) -> DedupIndex:
    dedup_path = cfg.research_hub_dir / "dedup_index.json"
    dedup = DedupIndex.load(dedup_path)
    if dedup.doi_to_hits or dedup.title_to_hits:
        return dedup
    for hit in build_from_obsidian(cfg.raw):
        dedup.add(hit)
    if not dry_run and zot is not None and cfg.zotero_library_id and hasattr(zot, "items"):
        for hit in build_from_zotero(zot, cfg.zotero_library_id):
            dedup.add(hit)
    return dedup


def _render_obsidian_note(
    pp: dict,
    collection_name: str,
    cluster_slug: str | None,
    query: str | None,
) -> str:
    # Build authors_str from either authors_str field, list of strings,
    # or list of {creatorType, firstName, lastName} dicts (Zotero format).
    authors_strs: list[str] = []
    if pp.get("authors_str"):
        authors_strs = [pp["authors_str"]]
    elif pp.get("authors"):
        for a in pp["authors"]:
            if isinstance(a, str):
                authors_strs.append(a)
            elif isinstance(a, dict):
                last = a.get("lastName", "")
                first = a.get("firstName", "")
                if last:
                    authors_strs.append(f"{last}, {first}" if first else last)
                elif a.get("name"):
                    authors_strs.append(a["name"])
    item_data = {
        "key": pp.get("zotero_key", ""),
        "title": pp["title"],
        "authors": authors_strs,
        "year": pp["year"],
        "journal": pp["journal"],
        "volume": pp.get("volume", ""),
        "issue": pp.get("issue", ""),
        "pages": pp.get("pages", ""),
        "doi": pp["doi"],
        "abstract": pp["abstract"],
        "tags": pp["tags"],
    }
    content = make_raw_md(
        item_data,
        [collection_name],
        [],
        topic_cluster=cluster_slug or "",
        cluster_queries=[_query_for_paper(pp, query)] if cluster_slug else [],
        verified=pp.get("verified"),
        verified_at=pp.get("verified_at", ""),
    )
    content += (
        "\n## Summary\n\n"
        + pp["summary"]
        + "\n\n## Key Findings\n\n"
        + "".join("- " + finding + "\n" for finding in pp["key_findings"])
        + "\n## Methodology\n\n"
        + pp["methodology"]
        + "\n\n## Relevance\n\n"
        + pp["relevance"]
        + "\n"
    )
    return content


def run_pipeline(
    dry_run: bool = False,
    *,
    cluster_slug: str | None = None,
    query: str | None = None,
    verify: bool = False,
) -> int:
    cfg = get_config()
    kb = str(cfg.root)
    collection_key = cfg.zotero_default_collection
    no_zotero = os.environ.get("RESEARCH_HUB_NO_ZOTERO", "").lower() in ("1", "true", "yes")
    if collection_key is None and not dry_run and not no_zotero:
        raise RuntimeError(
            "Set zotero.default_collection in config.json or "
            "RESEARCH_HUB_DEFAULT_COLLECTION env var. "
            "Or set RESEARCH_HUB_NO_ZOTERO=1 to skip Zotero entirely "
            "(data analyst mode: Obsidian + NotebookLM only)."
        )

    log_path = _resolve_log_path(cfg.logs)
    out_path = cfg.logs / "pipeline_output.json"
    papers_json = cfg.root / "papers_input.json"
    collection_name = (
        cfg.zotero_collections.get(collection_key, {}).get("name", collection_key)
        if collection_key is not None
        else "<unconfigured>"
    )
    clusters = ClusterRegistry(cfg.clusters_file)
    if cluster_slug is not None and clusters.get(cluster_slug) is None:
        raise ValueError("Cluster not found - use 'research-hub clusters new' first")
    if query is None and cluster_slug is not None:
        cluster_obj = clusters.get(cluster_slug)
        if cluster_obj is not None and cluster_obj.first_query:
            query = cluster_obj.first_query
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")
    dedup_path = cfg.research_hub_dir / "dedup_index.json"

    with log_path.open("w", encoding="utf-8") as log:
        def p(message: str) -> None:
            log.write(message + "\n")
            log.flush()

        p("=== PIPELINE START ===")
        if dry_run:
            p("DRY RUN MODE - no writes will be made")
            p(f"Config root: {kb}")
            if not papers_json.exists():
                p(f"NOTE: {papers_json} not found - this is expected in a fresh setup.")
                p("DRY RUN: Config and imports OK. Ready to run. Exiting.")
                return 0

        with papers_json.open("r", encoding="utf-8") as file_obj:
            papers = json.load(file_obj)
        p(f"Loaded {len(papers)} papers")

        if not no_zotero:
            all_errors: list[str] = []
            for idx, paper in enumerate(papers):
                all_errors.extend(_validate_paper_input(paper, idx))
            if all_errors:
                p("\n=== INPUT VALIDATION FAILED ===")
                for err in all_errors:
                    p(f"  !!{err}")
                p(f"\nFix papers_input.json and re-run. {len(all_errors)} errors total.")
                return 1

        dedup = _load_or_build_dedup(cfg, dry_run=dry_run)

        if dry_run:
            if cluster_slug:
                for paper in papers:
                    manifest.append(
                        new_entry(
                            cluster=cluster_slug,
                            query=_query_for_paper(paper, query),
                            action="new",
                            doi=paper.get("doi", ""),
                            title=paper.get("title", ""),
                        )
                    )
            p(f"DRY RUN: would process {len(papers)} papers. Config OK. Exiting.")
            return 0

        if no_zotero:
            zot = None
            dedup = _load_or_build_dedup(cfg, None, dry_run=False)
            p("RESEARCH_HUB_NO_ZOTERO=1 — skipping Zotero, using Obsidian-only mode")
        else:
            zot = get_client()
            dedup = _load_or_build_dedup(cfg, zot, dry_run=False)
            p("Zotero client ready")

        zr = []
        obr = []
        dr = []
        errors = []
        papers_for_notes = []

        for i, pp in enumerate(papers):
            p(f"\n--- Paper {i+1}: {pp['title'][:60]}...")
            query_text = _query_for_paper(pp, query)
            try:
                is_duplicate, dedup_hits = dedup.check({"doi": pp["doi"], "title": pp["title"]})
                if is_duplicate:
                    obsidian_hit = next((hit for hit in dedup_hits if hit.source == "obsidian"), None)
                    zotero_hit = next((hit for hit in dedup_hits if hit.source == "zotero"), None)
                    if obsidian_hit and obsidian_hit.obsidian_path:
                        append_cluster_query_to_existing(
                            Path(obsidian_hit.obsidian_path),
                            query_text,
                            topic_cluster=cluster_slug or "",
                        )
                        if cluster_slug:
                            update_cluster_links(
                                Path(obsidian_hit.obsidian_path),
                                cfg.raw,
                                cluster_slug,
                            )
                        manifest.append(
                            new_entry(
                                cluster=cluster_slug or "",
                                query=query_text,
                                action="dup-obsidian",
                                doi=pp["doi"],
                                title=pp["title"],
                                zotero_key=obsidian_hit.zotero_key or "",
                                obsidian_path=obsidian_hit.obsidian_path,
                            )
                        )
                        p("  SKIPPED dup in Obsidian")
                        zr.append(
                            {
                                "title": pp["title"],
                                "status": "SKIPPED_DUPLICATE",
                                "key": obsidian_hit.zotero_key or "",
                            }
                        )
                        continue
                    if zotero_hit:
                        cluster = clusters.get(cluster_slug) if cluster_slug else None
                        if cluster and cluster.zotero_collection_key:
                            move = getattr(zot, "move_to_collection", None)
                            if callable(move) and zotero_hit.zotero_key:
                                move(zotero_hit.zotero_key, cluster.zotero_collection_key)
                        manifest.append(
                            new_entry(
                                cluster=cluster_slug or "",
                                query=query_text,
                                action="dup-zotero",
                                doi=pp["doi"],
                                title=pp["title"],
                                zotero_key=zotero_hit.zotero_key or "",
                            )
                        )
                        p("  SKIPPED dup in Zotero")
                        zr.append(
                            {
                                "title": pp["title"],
                                "status": "SKIPPED_DUPLICATE",
                                "key": zotero_hit.zotero_key or "",
                            }
                        )
                        continue
                if no_zotero:
                    dup = False
                else:
                    dup = check_duplicate(zot, pp["title"], pp["doi"])
            except Exception:
                dup = False
            if dup:
                p("  SKIPPED dup")
                zr.append({"title": pp["title"], "status": "SKIPPED_DUPLICATE", "key": ""})
                continue

            if no_zotero:
                p("  SKIPPED Zotero (no-zotero mode)")
                pp["zotero_key"] = ""
                zr.append({"title": pp["title"], "status": "SKIPPED_NO_ZOTERO", "key": ""})
                papers_for_notes.append(pp)
                time.sleep(0.1)
                continue

            t = zot.item_template("journalArticle")
            t["title"] = pp["title"]
            t["creators"] = pp["authors"]
            t["date"] = pp["year"]
            t["DOI"] = pp["doi"]
            t["url"] = pp["url"]
            t["publicationTitle"] = pp.get("journal", "")
            t["volume"] = pp.get("volume", "")
            t["issue"] = pp.get("issue", "")
            t["pages"] = pp.get("pages", "")
            t["abstractNote"] = pp["abstract"]
            t["tags"] = [{"tag": x} for x in pp["tags"]]
            t["collections"] = [collection_key]
            try:
                resp = zot.create_items([t])
                if resp.get("successful"):
                    key = list(resp["successful"].values())[0]["key"]
                    p(f"  CREATED: {key}")
                    pp["zotero_key"] = key
                    zr.append({"title": pp["title"], "status": "CREATED", "key": key})
                    nh = "<h1>Summary</h1><p>" + pp["summary"] + "</p>"
                    nh += "<h2>Key Findings</h2><ul>" + "".join(
                        "<li>" + x + "</li>" for x in pp["key_findings"]
                    ) + "</ul>"
                    nh += "<h2>Methodology</h2><p>" + pp["methodology"] + "</p>"
                    nh += "<h2>Relevance</h2><p>" + pp["relevance"] + "</p>"
                    ok = add_note(zot, key, nh)
                    p(f"  Note: {'OK' if ok else 'FAIL'}")
                    papers_for_notes.append(pp)
                else:
                    p(f"  RESP: {resp}")
                    zr.append({"title": pp["title"], "status": "FAILED", "key": ""})
            except Exception as exc:
                p(f"  ERR: {exc}")
                zr.append({"title": pp["title"], "status": "ERROR", "key": ""})
                errors.append(
                    {
                        "paper": pp["title"],
                        "step": "zotero",
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
            time.sleep(1)

        p("\n=== DOI VALIDATION ===")
        verify_cache = VerifyCache(cfg.research_hub_dir / "verify_cache.json") if verify else None
        for pp in papers:
            title = pp["title"]
            doi = pp["doi"]
            url = pp.get("url", "")
            authors = [
                f"{author.get('firstName', '')} {author.get('lastName', '')}".strip()
                or author.get("name", "")
                for author in pp.get("authors", [])
            ]
            year_value = pp.get("year")
            try:
                year = int(year_value) if year_value not in (None, "") else None
            except (TypeError, ValueError):
                year = None
            arxiv_id = _extract_arxiv_id_from_url_or_doi(url, doi)

            if not verify:
                result = VerificationResult(
                    ok=False,
                    source="unresolved",
                    reason="verification skipped",
                )
                pp["verified"] = None
                pp["verified_at"] = ""
            else:
                result: VerificationResult | None = None
                if arxiv_id:
                    result = verify_arxiv(arxiv_id, cache=verify_cache)
                if (not result or not result.ok) and doi:
                    result = verify_doi(doi, cache=verify_cache)
                if (not result or not result.ok) and title:
                    result = verify_paper(title, authors=authors, year=year, cache=verify_cache)
                if result is None:
                    result = VerificationResult(ok=False, source="unresolved", reason="no identifier")
                pp["verified"] = result.ok
                pp["verified_at"] = result.cached_at

            best = result.resolved_url or (f"https://doi.org/{doi}" if doi else "")
            typ = {
                "doi.org": "DOI",
                "arxiv.org": "arXiv",
                "semantic-scholar": "S2",
                "unresolved": "NONE",
            }[result.source]
            ok = result.ok
            dr.append(
                {
                    "title": title[:50],
                    "best_url": best,
                    "type": typ,
                    "accessible": ok,
                    "verification_reason": result.reason,
                }
            )
            p(f"  [{'OK' if ok else 'WALL'}] {title[:50]}... -> {typ} ({result.reason})")

        p("\n=== OBSIDIAN NOTES ===")
        for pp in papers_for_notes:
            folder = _folder_for_paper(cfg, pp, cluster_slug)
            folder.mkdir(parents=True, exist_ok=True)
            file_path = folder / f"{pp['slug']}.md"
            zotero_key = pp.get("zotero_key", "")
            try:
                file_path.write_text(
                    _render_obsidian_note(pp, collection_name, cluster_slug, query),
                    encoding="utf-8",
                )
                p(f"  OK: {file_path}")
                obr.append({"file": str(file_path), "status": "CREATED"})
                dedup.add(
                    DedupHit(
                        source="obsidian",
                        doi=pp["doi"],
                        title=pp["title"],
                        zotero_key=zotero_key or None,
                        obsidian_path=str(file_path),
                    )
                )
                if cluster_slug:
                    update_cluster_links(file_path, cfg.raw, cluster_slug)
                manifest.append(
                    new_entry(
                        cluster=cluster_slug or "",
                        query=_query_for_paper(pp, query),
                        action="new",
                        doi=pp["doi"],
                        title=pp["title"],
                        zotero_key=zotero_key,
                        obsidian_path=str(file_path),
                    )
                )
            except Exception as exc:
                p(f"  ERR: {file_path} {exc}")
                obr.append({"file": str(file_path), "status": "ERROR"})
                manifest.append(
                    new_entry(
                        cluster=cluster_slug or "",
                        query=_query_for_paper(pp, query),
                        action="error",
                        doi=pp.get("doi", ""),
                        title=pp.get("title", ""),
                        zotero_key=zotero_key,
                        obsidian_path=str(file_path),
                        error=str(exc),
                    )
                )
                errors.append(
                    {
                        "paper": pp["title"],
                        "step": "obsidian",
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )

        cr = sum(1 for r in zr if r["status"] == "CREATED")
        sk = sum(1 for r in zr if r["status"] == "SKIPPED_DUPLICATE")
        fl = sum(1 for r in zr if r["status"] in ("FAILED", "ERROR"))
        oc = sum(1 for r in obr if r["status"] == "CREATED")
        da = sum(1 for r in dr if r["accessible"])
        p(
            f"\n=== SUMMARY ===\nPapers: {len(papers)}\nZotero created: {cr}\nZotero skipped: {sk}\nZotero failed: {fl}\nObsidian created: {oc}\nDOIs accessible: {da}"
        )
        if not dry_run:
            p("\n=== INTEGRATION SUGGESTIONS ===")
            try:
                from research_hub.suggest import (
                    PaperInput,
                    suggest_cluster_for_paper,
                    suggest_related_papers,
                )

                registry = clusters
                for pp in papers:
                    if pp.get("_status") == "SKIPPED_DUPLICATE":
                        continue
                    paper_in = PaperInput(
                        title=pp["title"],
                        doi=pp.get("doi", ""),
                        authors=[
                            f"{a.get('firstName', '')} {a.get('lastName', '')}".strip()
                            or a.get("name", "")
                            for a in pp.get("authors", [])
                        ],
                        year=pp.get("year"),
                        venue=pp.get("journal", ""),
                        tags=pp.get("tags", []),
                    )
                    cluster_hits = suggest_cluster_for_paper(paper_in, registry, dedup)
                    related = suggest_related_papers(paper_in, dedup, registry, top_n=3)
                    p(f"\n  Paper: {pp['title'][:60]}")
                    for cs in cluster_hits[:2]:
                        p(f"    ->cluster: {cs.cluster_slug} (score {cs.score:.1f})")
                    for rp in related:
                        p(f"    ->related: {rp.title[:50]} (score {rp.score:.1f})")
            except Exception as exc:
                p(f"  [warn] suggestion failed: {exc}")
        out = {
            "zotero_results": zr,
            "obsidian_results": obr,
            "doi_results": dr,
            "papers": [
                {
                    "title": paper["title"],
                    "slug": paper["slug"],
                    "zotero_key": paper.get("zotero_key", ""),
                    "sub_category": paper["sub_category"],
                }
                for paper in papers
            ],
        }
        with out_path.open("w", encoding="utf-8") as file_obj:
            json.dump(out, file_obj, indent=2, ensure_ascii=False)
        dedup.save(dedup_path)
        if errors:
            errors_log = _write_error_log(cfg.logs, errors)
            p(f"Errors logged: {errors_log}")
        p(f"JSON: {out_path}\n=== DONE ===")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Validate config and input, no writes")
    parser.add_argument("--cluster", default=None, help="Cluster slug for ingestion")
    parser.add_argument("--query", default=None, help="Query text for cluster_queries")
    args = parser.parse_args(argv)
    try:
        return run_pipeline(dry_run=args.dry_run, cluster_slug=args.cluster, query=args.query)
    except Exception:
        log_path = _resolve_log_path(get_config().logs)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(traceback.format_exc() + "\n")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
