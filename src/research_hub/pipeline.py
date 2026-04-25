from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import traceback
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.dedup import DedupHit, DedupIndex, build_from_obsidian, build_from_zotero
from research_hub.manifest import Manifest, new_entry
from research_hub.utils.doi import extract_arxiv_id
from research_hub.verify import VerificationResult, VerifyCache, verify_arxiv, verify_doi, verify_paper
from research_hub.vault.link_updater import update_cluster_links
from research_hub.zotero.client import add_note, check_duplicate, get_client
from research_hub.zotero.fetch import make_raw_md


REQUIRED_FIELDS_CORE = ["title", "doi", "authors", "year"]
REQUIRED_FIELDS_ZOTERO = ["abstract", "journal"]
REQUIRED_FIELDS_NOTE = ["summary", "key_findings", "methodology", "relevance"]
logger = logging.getLogger(__name__)


def _compose_hub_tags(pp: dict, cluster_slug: str | None) -> list[str]:
    """Compose research-hub namespace tags from a paper dict + cluster slug.

    Always includes 'research-hub'. Adds 'cluster/<slug>', 'type/<doc_type>',
    and 'src/<backend>' if available. Merges with any pre-existing pp['tags']
    while preserving order and de-duplicating.
    """
    hub_tags = ["research-hub"]
    # v0.65: guard against literal "None"/"none"/"null" strings and
    # whitespace-only slugs that would produce a bogus "cluster/None" tag.
    cluster_token = (str(cluster_slug).strip() if cluster_slug is not None else "")
    if cluster_token and cluster_token.lower() not in {"none", "null"}:
        hub_tags.append(f"cluster/{cluster_token}")
    doc_type = pp.get("doc_type") or pp.get("publication_type")
    if doc_type:
        hub_tags.append(f"type/{doc_type}")
    backend = pp.get("source") or pp.get("found_in")
    if backend:
        hub_tags.append(f"src/{backend}")
    existing = pp.get("tags") or []
    return list(dict.fromkeys(existing + hub_tags))


def _slugify(text: str) -> str:
    from research_hub.clusters import slugify

    return slugify(text)


def _build_note_html(pp: dict) -> str:
    summary = str(pp.get("summary", "") or "")
    findings = pp.get("key_findings", []) or []
    methodology = str(pp.get("methodology", "") or "")
    relevance = str(pp.get("relevance", "") or "")
    note = "<h1>Summary</h1><p>" + summary + "</p>"
    note += "<h2>Key Findings</h2><ul>"
    note += "".join("<li>" + str(item) + "</li>" for item in findings)
    note += "</ul>"
    note += "<h2>Methodology</h2><p>" + methodology + "</p>"
    note += "<h2>Relevance</h2><p>" + relevance + "</p>"
    return note


def _auto_generate_missing_fields(pp: dict, cluster_slug: str | None) -> None:
    """Fill ingest fields that can be derived from existing metadata."""
    if "slug" not in pp or not pp.get("slug"):
        first_author = ""
        authors = pp.get("authors") or []
        if authors and isinstance(authors[0], dict):
            first_author = authors[0].get("lastName", "") or authors[0].get("name", "")
        elif authors and isinstance(authors[0], str):
            first_author = authors[0].split(",")[0].strip().split(" ")[-1]
        year = str(pp.get("year", ""))
        title = pp.get("title", "")
        generated = f"{_slugify(first_author)}{year}-{_slugify(title)[:60]}".strip("-")
        pp["slug"] = generated or f"paper-{year}".strip("-")

    if "sub_category" not in pp or not pp.get("sub_category"):
        pp["sub_category"] = cluster_slug or "uncategorized"


def _validate_paper_input(pp: dict, idx: int) -> list[str]:
    """Validate one paper entry before any Zotero writes."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS_CORE:
        if field not in pp or pp.get(field) in (None, "", []):
            errors.append(
                f"Paper {idx}: missing required field '{field}' - add "
                f"'{field}: <value>' to the paper entry in papers_input.json"
            )
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
    for field in REQUIRED_FIELDS_ZOTERO + REQUIRED_FIELDS_NOTE:
        if field not in pp or pp.get(field) in (None, "", []):
            errors.append(
                f"Paper {idx}: missing field '{field}' - pipeline will KeyError "
                f"during Zotero/Obsidian write. Add '{field}: <value>' or a sensible placeholder."
            )
    if "key_findings" in pp and not isinstance(pp["key_findings"], list):
        errors.append(
            f"Paper {idx}: 'key_findings' must be a list of strings "
            f"(got {type(pp['key_findings']).__name__})"
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
    return extract_arxiv_id(f"{url or ''} {doi or ''}")


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
    *,
    fit_warning: bool = False,
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
        "tags": pp.get("tags", []),
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
    if fit_warning:
        content = content.replace('verified_at: "', 'fit_warning: true\nverified_at: "', 1)
    from research_hub.markdown_conventions import summary_section_to_callout

    content += "\n" + summary_section_to_callout(
        summary=pp["summary"],
        key_findings=pp["key_findings"],
        methodology=pp["methodology"],
        relevance=pp["relevance"],
    )
    return content


def _load_fit_check_rejections(cfg, cluster_slug: str | None) -> tuple[dict[str, dict], dict[str, dict]]:
    if not cluster_slug:
        return {}, {}
    from research_hub.topic import hub_cluster_dir

    path = hub_cluster_dir(cfg, cluster_slug) / ".fit_check_rejected.json"
    if not path.exists():
        return {}, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}, {}

    by_doi: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    for item in payload.get("rejected", []):
        doi = str(item.get("doi", "") or "").strip().lower()
        title = str(item.get("title", "") or "").strip().lower()
        if doi:
            by_doi[doi] = item
        if title:
            by_title[title] = item
    return by_doi, by_title


def run_pipeline(
    dry_run: bool = False,
    *,
    cluster_slug: str | None = None,
    query: str | None = None,
    verify: bool = False,
    allow_library_duplicates: bool = False,
    fit_check: bool = False,
    fit_check_threshold: int = 3,
    no_fit_check_auto_labels: bool = False,
) -> int:
    del no_fit_check_auto_labels
    cfg = get_config()
    kb = str(cfg.root)
    no_zotero = os.environ.get("RESEARCH_HUB_NO_ZOTERO", "").lower() in ("1", "true", "yes")
    clusters = ClusterRegistry(cfg.clusters_file)
    cluster_obj = clusters.get(cluster_slug) if cluster_slug else None
    collection_key = (
        cluster_obj.zotero_collection_key
        if cluster_obj and cluster_obj.zotero_collection_key
        else cfg.zotero_default_collection
    )
    if collection_key is None and not dry_run and not no_zotero:
        raise RuntimeError(
            "Set cluster.zotero_collection_key for this cluster, zotero.default_collection "
            "in config.json, or "
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
    if cluster_slug is not None and clusters.get(cluster_slug) is None:
        raise ValueError("Cluster not found - use 'research-hub clusters new' first")
    if query is None and cluster_slug is not None:
        if cluster_obj is not None and cluster_obj.first_query:
            query = cluster_obj.first_query
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")
    dedup_path = cfg.research_hub_dir / "dedup_index.json"
    fit_rejected_by_doi, fit_rejected_by_title = _load_fit_check_rejections(cfg, cluster_slug)
    fit_warnings = 0
    fit_accepted = 0
    fit_rejected = 0
    fit_key_terms: list[str] = []
    if fit_check and cluster_slug:
        from research_hub.fit_check import _extract_key_terms, _read_definition_from_overview

        fit_key_terms = _extract_key_terms(_read_definition_from_overview(cfg, cluster_slug) or "")

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
        if isinstance(papers, dict) and "papers" in papers:
            papers = papers["papers"]
        if not isinstance(papers, list):
            raise ValueError(
                "papers_input.json must be either a top-level JSON array or "
                'an object like {"papers": [...]}'
            )
        p(f"Loaded {len(papers)} papers")

        if not no_zotero:
            all_errors: list[str] = []
            nonfatal_errors: list[str] = []
            valid_papers: list[dict] = []
            skipped_invalid: list[tuple[int, dict, list[str]]] = []
            for idx, paper in enumerate(papers):
                _auto_generate_missing_fields(paper, cluster_slug)
                paper_errors = _validate_paper_input(paper, idx)
                missing_doi_only = (
                    not dry_run
                    and paper_errors
                    and all("missing required field 'doi'" in err for err in paper_errors)
                )
                if missing_doi_only:
                    skipped_invalid.append((idx, paper, paper_errors))
                    continue
                valid_papers.append(paper)
                if dry_run:
                    for err in paper_errors:
                        if "missing field '" in err and "pipeline will KeyError" in err:
                            nonfatal_errors.append(err)
                        else:
                            all_errors.append(err)
                else:
                    all_errors.extend(paper_errors)
            if all_errors:
                p("\n=== INPUT VALIDATION FAILED ===")
                for err in all_errors:
                    p(f"  !!{err}")
                p(f"\nFix papers_input.json and re-run. {len(all_errors)} errors total.")
                return 1
            if skipped_invalid:
                p("\n=== INPUT VALIDATION SKIPS ===")
                for idx, paper, paper_errors in skipped_invalid:
                    p(f"  SKIPPED invalid input Paper {idx}: {paper.get('title', '(untitled)')}")
                    for err in paper_errors:
                        p(f"    !!{err}")
                papers = valid_papers
            if nonfatal_errors:
                p("\n=== INPUT VALIDATION WARNINGS ===")
                for err in nonfatal_errors:
                    p(f"  !!{err}")
                p(
                    f"\nContinuing dry-run with {len(nonfatal_errors)} non-fatal warnings. "
                    "A real ingest would fail before any writes."
                )

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
            cluster_obj = clusters.get(cluster_slug) if cluster_slug else None
            cluster_coll = cluster_obj.zotero_collection_key if cluster_obj else None
            if fit_check:
                doi_key = str(pp.get("doi", "") or "").strip().lower()
                title_key = str(pp.get("title", "") or "").strip().lower()
                rejected_item = fit_rejected_by_doi.get(doi_key) or fit_rejected_by_title.get(title_key)
                if rejected_item is not None and int(rejected_item.get("score", 0)) < fit_check_threshold:
                    fit_rejected += 1
                    p("  SKIPPED fit-check below threshold")
                    manifest.append(
                        new_entry(
                            cluster=cluster_slug or "",
                            query=query_text,
                            action="skip-fit-check",
                            doi=pp.get("doi", ""),
                            title=pp.get("title", ""),
                            error="below fit-check threshold",
                        )
                    )
                    zr.append({"title": pp["title"], "status": "SKIPPED_FIT_CHECK", "key": ""})
                    continue
                fit_accepted += 1
                if fit_key_terms:
                    from research_hub.fit_check import term_overlap

                    pp["_fit_warning"] = term_overlap(pp.get("abstract", ""), fit_key_terms) == 0.0
                    if pp["_fit_warning"]:
                        fit_warnings += 1
                        p("  WARN fit-check term overlap is zero")
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
                        if zotero_hit.zotero_key:
                            try:
                                existing_item = zot.item(zotero_hit.zotero_key)
                                existing_tags = {
                                    tag["tag"]
                                    for tag in existing_item.get("data", {}).get("tags", [])
                                    if "tag" in tag
                                }
                                hub_tags = set(_compose_hub_tags(pp, cluster_slug))
                                new_tags = hub_tags - existing_tags
                                if new_tags:
                                    existing_data = existing_item["data"]
                                    existing_data["tags"] = [
                                        *existing_data.get("tags", []),
                                        *[{"tag": tag} for tag in sorted(new_tags)],
                                    ]
                                    zot.update_item(existing_data)
                                children = zot.children(zotero_hit.zotero_key)
                                has_note = any(
                                    child.get("data", {}).get("itemType") == "note"
                                    for child in (children or [])
                                )
                                if not has_note:
                                    add_note(zot, zotero_hit.zotero_key, _build_note_html(pp))
                            except Exception as exc:
                                p(f"  WARN dedup note-add failed: {exc}")
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
                    dup = check_duplicate(
                        zot,
                        pp["title"],
                        pp["doi"],
                        collection_key=cluster_coll,
                        allow_library_duplicates=allow_library_duplicates,
                    )
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
            t["url"] = pp.get("url", "")
            t["publicationTitle"] = pp.get("journal", "")
            t["volume"] = pp.get("volume", "")
            t["issue"] = pp.get("issue", "")
            t["pages"] = pp.get("pages", "")
            t["abstractNote"] = pp["abstract"]
            t["tags"] = [{"tag": x} for x in _compose_hub_tags(pp, cluster_slug)]
            t["collections"] = [cluster_coll or collection_key]
            try:
                p(
                    f"  Routing to collection: {cluster_coll or collection_key} "
                    f"(cluster={cluster_slug or 'none'})"
                )
                resp = zot.create_items([t])
                if resp.get("successful"):
                    key = list(resp["successful"].values())[0]["key"]
                    p(f"  CREATED: {key}")
                    pp["zotero_key"] = key
                    zr.append({"title": pp["title"], "status": "CREATED", "key": key})
                    ok = add_note(zot, key, _build_note_html(pp))
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
                    _render_obsidian_note(
                        pp,
                        collection_name,
                        cluster_slug,
                        query,
                        fit_warning=bool(pp.get("_fit_warning")),
                    ),
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
        if fit_check:
            p(
                f"fit-check: {len(papers)} in, {fit_accepted} accepted, "
                f"{fit_rejected} rejected, {fit_warnings} warnings"
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

    if cluster_obj is not None:
        _refresh_cluster_base(cfg, cluster_obj)
    return 0


def _refresh_cluster_base(cfg, cluster) -> None:
    from research_hub.obsidian_bases import write_cluster_base

    try:
        write_cluster_base(
            hub_root=Path(cfg.hub),
            cluster_slug=cluster.slug,
            cluster_name=cluster.name,
            obsidian_subfolder=cluster.obsidian_subfolder,
            force=True,
        )
    except Exception as exc:
        logger.warning("Could not refresh .base for %s: %s", cluster.slug, exc)


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
