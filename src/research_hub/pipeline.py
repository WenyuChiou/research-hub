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
from research_hub.vault.link_updater import update_cluster_links
from research_hub.zotero.client import add_note, check_duplicate, get_client
from research_hub.zotero.fetch import make_raw_md


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


def append_cluster_query_to_existing(note_path: Path, query: str) -> bool:
    """Append query to cluster_queries in a note frontmatter, idempotently."""
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
    if not match:
        return False
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
    note_path.write_text(text[:3] + updated_frontmatter + text[end:], encoding="utf-8")
    return True


def _query_for_paper(paper: dict, query: str | None = None) -> str:
    return query or paper.get("query") or paper.get("search_query") or paper["title"]


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
    item_data = {
        "key": pp.get("zotero_key", ""),
        "title": pp["title"],
        "authors": [pp["authors_str"]] if pp.get("authors_str") else [],
        "year": pp["year"],
        "journal": pp["journal"],
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
) -> int:
    cfg = get_config()
    kb = str(cfg.root)
    collection_key = cfg.zotero_default_collection
    if collection_key is None and not dry_run:
        raise RuntimeError(
            "Set zotero.default_collection in config.json or "
            "RESEARCH_HUB_DEFAULT_COLLECTION env var"
        )

    log_path = _resolve_log_path(cfg.logs)
    out_path = cfg.root / "pipeline_test_output.json"
    papers_json = cfg.root / "papers_input.json"
    collection_name = (
        cfg.zotero_collections.get(collection_key, {}).get("name", collection_key)
        if collection_key is not None
        else "<unconfigured>"
    )
    clusters = ClusterRegistry(cfg.clusters_file)
    if cluster_slug is not None and clusters.get(cluster_slug) is None:
        raise ValueError("Cluster not found - use 'research-hub clusters new' first")
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
                        append_cluster_query_to_existing(Path(obsidian_hit.obsidian_path), query_text)
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
                dup = check_duplicate(zot, pp["title"], pp["doi"])
            except Exception:
                dup = False
            if dup:
                p("  SKIPPED dup")
                zr.append({"title": pp["title"], "status": "SKIPPED_DUPLICATE", "key": ""})
                continue

            t = zot.item_template("journalArticle")
            t["title"] = pp["title"]
            t["creators"] = pp["authors"]
            t["date"] = pp["year"]
            t["DOI"] = pp["doi"]
            t["url"] = pp["url"]
            t["publicationTitle"] = pp["journal"]
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

        p("\n=== DOI VALIDATION ===")
        for pp in papers:
            doi = pp["doi"]
            url = pp.get("url", "")
            if "arxiv.org" in url:
                best, typ, ok = url, "arXiv", True
            elif pp.get("pdf_url") and "doi.org" not in pp.get("pdf_url", ""):
                best, typ, ok = pp["pdf_url"], "Direct", True
            elif doi:
                best, typ, ok = "https://doi.org/" + doi, "DOI", "48550" in doi
            else:
                best, typ, ok = "", "NONE", False
            dr.append(
                {"title": pp["title"][:50], "best_url": best, "type": typ, "accessible": ok}
            )
            p(f"  [{'OK' if ok else 'WALL'}] {pp['title'][:50]}... -> {typ}")

        cr = sum(1 for r in zr if r["status"] == "CREATED")
        sk = sum(1 for r in zr if r["status"] == "SKIPPED_DUPLICATE")
        fl = sum(1 for r in zr if r["status"] in ("FAILED", "ERROR"))
        oc = sum(1 for r in obr if r["status"] == "CREATED")
        da = sum(1 for r in dr if r["accessible"])
        p(
            f"\n=== SUMMARY ===\nPapers: {len(papers)}\nZotero created: {cr}\nZotero skipped: {sk}\nZotero failed: {fl}\nObsidian created: {oc}\nDOIs accessible: {da}"
        )
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
