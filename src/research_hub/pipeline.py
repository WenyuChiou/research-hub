from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from research_hub.clusters import ClusterRegistry
from research_hub.config import get_config
from research_hub.dedup import (
    DedupHit,
    DedupIndex,
    build_from_obsidian,
    build_from_zotero,
    normalize_title,
)
from research_hub.manifest import Manifest, new_entry
from research_hub.utils.doi import extract_arxiv_id, normalize_doi
from research_hub.verify import VerificationResult, VerifyCache, verify_arxiv, verify_doi, verify_paper
from research_hub.ingest_diff import compute_ingest_gap, write_gap_sidecar
from research_hub.vault.hub_overview import derive_moc_links, ensure_moc, populate_overview
from research_hub.vault.link_updater import update_cluster_links
from research_hub.zotero.client import add_note, check_duplicate, get_client
from research_hub.zotero.fetch import make_raw_md


REQUIRED_FIELDS_CORE = ["title", "authors", "year"]
REQUIRED_FIELDS_ZOTERO = ["abstract", "journal"]
REQUIRED_FIELDS_NOTE = ["summary", "key_findings", "methodology", "relevance"]
logger = logging.getLogger(__name__)
ZOTERO_BATCH_SIZE = 50


def _compose_hub_tags(pp: dict, cluster_slug: str | None, batch_label: str = "") -> list[str]:
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
    # v0.68.4: default to journalArticle when the search backend didn't
    # supply a doc_type — the pipeline always creates journalArticle items
    # (see pipeline.py zot.item_template call), so this matches reality.
    doc_type = pp.get("doc_type") or pp.get("publication_type") or "journalArticle"
    hub_tags.append(f"type/{doc_type}")
    # Phase D (v1.1): surface the Phase A fit_score as a compact tag so
    # the relevance verdict is visible in Zotero too (Obsidian gets the
    # full provenance block). Omit entirely when no numeric score —
    # never tag legacy / unscored papers with a bogus fit/ value.
    prov = pp.get("provenance")
    fit_score = prov.get("fit_score") if isinstance(prov, dict) else pp.get("fit_score")
    if isinstance(fit_score, (int, float)) and not isinstance(fit_score, bool):
        bucket = "high" if fit_score >= 5 else "mid" if fit_score >= 3 else "low"
        hub_tags.append(f"fit/{bucket}")
    backend = pp.get("source") or pp.get("found_in")
    if backend:
        hub_tags.append(f"src/{backend}")
    if batch_label:
        hub_tags.append(f"batch:{batch_label}")
    existing = pp.get("tags") or []
    return list(dict.fromkeys(existing + hub_tags))


def _zotero_item_type(pp: dict) -> str:
    """Map a candidate paper to a Zotero itemType (Phase D, v1.1).

    Search backends set doc_type / publication_type / source but
    never item_type, so historically the pipeline filed EVERY paper
    as a journalArticle — wrong BibTeX export for arXiv / preprint /
    conference items. This is the type-aware fallback for
    ``pp.get("item_type", "") or _zotero_item_type(pp)``; an
    explicitly-supplied pp["item_type"] still wins (no behaviour
    change for that path). Pure dict reads + string match — no LLM
    (L5 invariant) and no new Zotero schema.
    """
    raw = " ".join(
        str(pp.get(key, "") or "")
        for key in ("item_type", "doc_type", "publication_type", "source", "found_in")
    ).lower()
    if any(
        t in raw
        for t in ("arxiv", "biorxiv", "medrxiv", "preprint", "posted-content", "ssrn", "osf")
    ):
        # "posted-content" is Crossref's type for preprints.
        return "preprint"
    if any(t in raw for t in ("conference", "proceedings", "inproceedings")):
        return "conferencePaper"
    if any(t in raw for t in ("thesis", "dissertation", "phdthesis", "mastersthesis")):
        return "thesis"
    if any(t in raw for t in ("report", "techreport", "working paper", "white paper")):
        return "report"
    if "book" in raw and any(t in raw for t in ("section", "chapter")):
        return "bookSection"
    if "book" in raw:
        return "book"
    return "journalArticle"


def _slugify(text: str) -> str:
    from research_hub.clusters import slugify

    return slugify(text)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_today_yyyymmdd() -> str:
    return _utc_now().strftime("%Y%m%d")


def _utc_now_yyyymmdd_hhmmss() -> str:
    return _utc_now().strftime("%Y%m%d-%H%M%S")


def resolve_batch_label(query: str | None, batch_label: str | None) -> str:
    if batch_label is not None:
        return str(batch_label).strip()
    if query:
        return f"{_utc_today_yyyymmdd()}-{_slugify(query)[:30]}".strip("-")
    return f"manual-{_utc_now_yyyymmdd_hhmmss()}"


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
    # Phase D (v1.1): mirror the Phase A provenance summary into the
    # Zotero child note (Obsidian frontmatter already carries the full
    # block). Pure dict reads + string join — no LLM (L5 invariant),
    # no new Zotero item fields. Skipped entirely when absent.
    prov = pp.get("provenance")
    if isinstance(prov, dict) and prov:
        resolved_via = str(prov.get("resolved_via", "") or "")
        corroboration = str(prov.get("corroboration", "") or "")
        checked_at = str(prov.get("doi_checked_at", "") or "")
        fit_score = prov.get("fit_score")
        parts: list[str] = []
        if resolved_via:
            parts.append("resolved via " + resolved_via)
        if corroboration:
            parts.append(corroboration)
        if isinstance(fit_score, (int, float)) and not isinstance(fit_score, bool):
            parts.append("fit score " + str(fit_score))
        if checked_at:
            parts.append("DOI checked " + checked_at)
        if parts:
            note += "<h2>Provenance</h2><p>" + "; ".join(parts) + "</p>"
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
        # v0.84.0: use canonical make_paper_slug (matches safe_filename) instead
        # of long divergent slugify(title)[:60] format. Prevents broken cross-ref
        # wikilinks when papers are renamed/migrated.
        from research_hub.zotero.fetch import make_paper_slug
        generated = make_paper_slug(first_author, year, title)
        pp["slug"] = generated or f"paper-{year}".strip("-")

    if "sub_category" not in pp or not pp.get("sub_category"):
        pp["sub_category"] = cluster_slug or "uncategorized"


_HTML_TEXT_FIELDS = ("title", "journal", "abstract", "publicationTitle", "abstractNote")


def _unescape_html_in_paper(pp: dict) -> None:
    """Decode HTML entities in user-visible string fields, in-place.

    Search backends (Crossref, OpenAlex, Semantic Scholar) sometimes
    return HTML-escaped strings in journal names, titles, and abstracts —
    e.g. "AI &amp; SOCIETY", "Computers &amp; Education". Decoding once
    at the pipeline layer keeps Zotero items + Obsidian frontmatter clean
    regardless of which backend supplied the data.
    """
    import html as _html

    for field in _HTML_TEXT_FIELDS:
        value = pp.get(field)
        if isinstance(value, str) and "&" in value:
            decoded = _html.unescape(value)
            if decoded != value:
                pp[field] = decoded
    # Authors are a list of dicts (creatorType, firstName, lastName, name);
    # decode the name parts too (publishers occasionally HTML-escape
    # diacritics in author names).
    authors = pp.get("authors") or []
    if isinstance(authors, list):
        for author in authors:
            if not isinstance(author, dict):
                continue
            for name_field in ("firstName", "lastName", "name"):
                v = author.get(name_field)
                if isinstance(v, str) and "&" in v:
                    decoded = _html.unescape(v)
                    if decoded != v:
                        author[name_field] = decoded


def _normalize_paper_metadata(pp: dict) -> None:
    """Fix common backend metadata quirks before validation."""
    doi = (pp.get("doi") or "").strip().lower()
    is_arxiv = doi.startswith("10.48550/arxiv.")

    journal = (pp.get("journal") or "").strip()
    if journal.lower() == "preprint":
        pp["journal"] = "arXiv" if is_arxiv else ""
    elif not journal and is_arxiv:
        pp["journal"] = "arXiv"

    volume = (pp.get("volume") or "").strip()
    if volume and re.match(r"^(abs|pdf)/", volume):
        pp["volume"] = ""


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

    def _is_anon_author(author) -> bool:
        if isinstance(author, dict):
            value = (author.get("name") or author.get("lastName") or "").strip().lower()
        elif isinstance(author, str):
            value = author.strip().lower()
        else:
            return True
        return value in {"", "anonymous", "anon", "unknown", "n/a", "none"}

    authors_list = pp.get("authors") or []
    if isinstance(authors_list, list) and authors_list and all(
        _is_anon_author(author) for author in authors_list
    ):
        errors.append(
            f"Paper {idx}: WARN -- all authors are anonymous/unknown. "
            f"Source: DOI={pp.get('doi', '?')}. The paper will still ingest "
            f"but check whether you really want it; some preprint DOIs "
            f"return 'Anonymous' before metadata is finalized."
        )
    return errors


def _only_missing_required_field_errors(errors: list[str]) -> bool:
    """True iff every error in *errors* is a "missing required field 'X'"
    error from _validate_paper_input.

    Used to classify a paper as "skip but don't abort the batch" when the
    search backend returned an entry missing one of REQUIRED_FIELDS_CORE
    (e.g., a CrossRef record with empty authors, or an OpenAlex entry
    missing year). The remaining valid papers in the same batch still
    write to Zotero/Obsidian; this skip is real-run only -- dry_run
    keeps the strict surfacing of all validation issues.
    """
    return bool(errors) and all("missing required field" in err for err in errors)


def _is_nonfatal_paper_error(err: str) -> bool:
    return ("missing field '" in err and "pipeline will KeyError" in err) or "WARN --" in err


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


def _flush_batch(
    zot,
    batch_templates: list[dict],
    batch_papers: list[dict],
    zr: list[dict],
    errors: list[dict],
    p,
    papers_for_notes: list[dict],
) -> None:
    """Create Zotero items in one batch, falling back to per-paper on exception."""
    if not batch_templates:
        return

    def _handle_success(paper: dict, key: str, *, batched: bool) -> None:
        paper["zotero_key"] = key
        zr.append({"title": paper["title"], "status": "CREATED", "key": key})
        p(f"  {'CREATED (batched)' if batched else 'CREATED'}: {key}")
        ok = add_note(zot, key, _build_note_html(paper))
        p(f"  Note: {'OK' if ok else 'FAIL'}")
        papers_for_notes.append(paper)

    def _handle_failure(paper: dict, exc: Exception) -> None:
        p(f"  ERR: {exc}")
        zr.append({"title": paper["title"], "status": "ERROR", "key": ""})
        errors.append(
            {
                "paper": paper["title"],
                "step": "zotero",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )

    def _retry_single(template: dict, paper: dict) -> None:
        """Create one item on its own. Never borrow another paper's key (STAB-1)."""
        try:
            r = zot.create_items([template])
            single = (r or {}).get("successful") or {}
            key = ""
            if single:
                meta = list(single.values())[0]
                key = meta.get("key") or meta.get("data", {}).get("key") or ""
            if key:
                _handle_success(paper, key, batched=False)
            else:
                p(f"  RESP: {r}")
                zr.append({"title": paper["title"], "status": "FAILED", "key": ""})
        except Exception as exc:
            _handle_failure(paper, exc)

    try:
        resp = zot.create_items(batch_templates)
    except Exception:
        for template, paper in zip(batch_templates, batch_papers):
            _retry_single(template, paper)
        return

    successful = (resp or {}).get("successful") or {}
    successful_indexes = set()
    for idx_str, item_meta in successful.items():
        idx = int(idx_str)
        successful_indexes.add(idx)
        paper = batch_papers[idx]
        key = item_meta.get("key") or item_meta.get("data", {}).get("key")
        if key:
            _handle_success(paper, key, batched=True)

    failed = (resp or {}).get("failed") or {}
    for idx, (template, paper) in enumerate(zip(batch_templates, batch_papers)):
        if idx in successful_indexes:
            continue
        if str(idx) in failed:
            p(f"  RESP: {failed[str(idx)]}")
            zr.append({"title": paper["title"], "status": "FAILED", "key": ""})
            continue
        # Index absent from BOTH `successful` and `failed` (a sparse response
        # under load, or pyzotero's `unchanged` bucket): retry this item on its
        # own so it gets its OWN key. NEVER reuse another paper's key — doing so
        # silently cross-links distinct papers onto one Zotero item (STAB-1).
        _retry_single(template, paper)


def _collection_field(collection: dict, field: str) -> str:
    if not isinstance(collection, dict):
        return ""
    data = collection.get("data", {})
    if isinstance(data, dict) and data.get(field):
        return str(data.get(field) or "")
    return str(collection.get(field, "") or "")


def _list_subcollections(zot, *, cluster_coll: str) -> list[dict]:
    web = getattr(zot, "web", None) or zot
    collections_sub = getattr(web, "collections_sub", None)
    if callable(collections_sub):
        try:
            return list(collections_sub(cluster_coll) or [])
        except Exception:
            pass

    collections = getattr(web, "collections", None)
    if not callable(collections):
        return []
    try:
        all_collections = collections() or []
    except Exception:
        return []
    return [
        coll
        for coll in all_collections
        if _collection_field(coll, "parentCollection") == cluster_coll
    ]


def _extract_created_collection_key(result) -> str:
    successful = (result or {}).get("successful", {}) if isinstance(result, dict) else {}
    first = next(iter(successful.values()), None) if successful else None
    return (first or {}).get("key") or (first or {}).get("data", {}).get("key") or ""


def _next_batch_label(zot, *, cluster_coll: str, batch_label: str) -> str:
    existing_names = {
        _collection_field(collection, "name")
        for collection in _list_subcollections(zot, cluster_coll=cluster_coll)
    }
    if batch_label not in existing_names:
        return batch_label
    suffix = 2
    while f"{batch_label}-{suffix}" in existing_names:
        suffix += 1
    return f"{batch_label}-{suffix}"


def _ensure_batch_subcollection(
    zot,
    *,
    cluster_coll: str,
    batch_label: str,
    log: Callable[[str], None],
) -> str:
    if not cluster_coll or not batch_label:
        return ""

    for collection in _list_subcollections(zot, cluster_coll=cluster_coll):
        if _collection_field(collection, "name") == batch_label:
            return _collection_field(collection, "key")

    try:
        # get_client() returns raw pyzotero.Zotero (which has
        # create_collections(payload_list)), but ZoteroDualClient wraps it
        # as create_collection(name, parent_key=...). Probe for both.
        if hasattr(zot, "create_collections"):
            result = zot.create_collections(
                [{"name": batch_label, "parentCollection": cluster_coll}]
            )
        elif hasattr(zot, "create_collection"):
            result = zot.create_collection(batch_label, parent_key=cluster_coll)
        else:
            log(f"[warn] zot has no create_collection(s) method")
            return ""
        key = _extract_created_collection_key(result)
        if key:
            return key
        log(f"[warn] batch sub-collection create returned no key for {batch_label!r}: {result}")
    except Exception as exc:
        log(f"[warn] could not create batch sub-collection {batch_label!r}: {exc}")
    return ""


def write_papers_to_zotero(
    zot,
    papers: list[dict],
    cluster_slug: str | None,
    cluster_coll: str | None,
    batch_coll: str | None = None,
    batch_label: str = "",
    *,
    zotero_batch_size: int = ZOTERO_BATCH_SIZE,
    log: Callable[[str], None] = print,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Build Zotero item templates and flush them in batches."""
    zr: list[dict] = []
    papers_for_notes: list[dict] = []
    errors: list[dict] = []
    batch_templates: list[dict] = []
    batch_papers: list[dict] = []
    target_collection = (cluster_coll or "").strip()

    from research_hub.zotero.doi_overrides import apply_doi_prefix_overrides

    for pp in papers:
        # v0.87.1 #1: apply DOI-prefix overrides so wrong venues from
        # search backends (e.g. ASCE paper tagged "arXiv", Zenodo dataset
        # tagged "Open MIND" journal) get fixed before they reach Zotero.
        apply_doi_prefix_overrides(pp)
        item_type = pp.get("item_type", "") or _zotero_item_type(pp)
        template = zot.item_template(item_type)
        template["title"] = pp["title"]
        template["creators"] = pp["authors"]
        template["date"] = pp["year"]
        template["DOI"] = pp["doi"]
        template["url"] = pp.get("url", "")
        template["publicationTitle"] = pp.get("journal", "")
        template["volume"] = pp.get("volume", "")
        template["issue"] = pp.get("issue", "")
        template["pages"] = pp.get("pages", "")
        template["abstractNote"] = pp["abstract"]
        template["tags"] = [
            {"tag": tag}
            for tag in _compose_hub_tags(pp, cluster_slug, batch_label=batch_label)
        ]
        collections = [target_collection] if target_collection else []
        if batch_coll and batch_coll not in collections:
            collections.append(batch_coll)
        template["collections"] = collections
        if len(collections) == 1:
            log(f"  Routing to collection: {collections[0]} (cluster={cluster_slug or 'none'})")
        else:
            route = ", ".join(collections) if collections else "<none>"
            log(f"  Routing to collection(s): {route} (cluster={cluster_slug or 'none'})")
        batch_templates.append(template)
        batch_papers.append(pp)
        if len(batch_templates) >= zotero_batch_size:
            _flush_batch(zot, batch_templates, batch_papers, zr, errors, log, papers_for_notes)
            batch_templates = []
            batch_papers = []
            time.sleep(1)

    if batch_templates:
        _flush_batch(zot, batch_templates, batch_papers, zr, errors, log, papers_for_notes)

    return zr, papers_for_notes, errors


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
    cluster_moc_links: list[str] | None = None,
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
        "provenance": pp.get("provenance"),
    }
    cluster_queries_for_note = [_query_for_paper(pp, query)] if cluster_slug else []
    # v0.88 #5: derive MOC backlinks at note-creation time so every paper
    # gets a `## Hub` section linking up to its cluster overview + MOCs.
    # Pass cluster.moc_links so explicit `LLM-Agents-*` / `Water-Resources-*`
    # overrides set in clusters.yaml take effect HERE too — without this,
    # the paper note's `## Hub` would still emit the auto-derived sub-MOC
    # while the cluster `00_overview.md` (which DOES pass moc_links via
    # `_sync_hub_overview`) shows the override. End state: overview wikilink
    # and paper-note wikilink disagree.
    moc_links_for_note: list[str] = []
    if cluster_slug:
        moc_links_for_note = derive_moc_links(
            cluster_slug,
            cluster_queries=cluster_queries_for_note,
            moc_links=list(cluster_moc_links or []),
        )
    content = make_raw_md(
        item_data,
        [collection_name],
        [],
        topic_cluster=cluster_slug or "",
        cluster_queries=cluster_queries_for_note,
        verified=pp.get("verified"),
        verified_at=pp.get("verified_at", ""),
        include_pending_summary_sections=False,
        moc_links=moc_links_for_note,
        provenance=pp.get("provenance"),
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
    zotero_batch_size: int = ZOTERO_BATCH_SIZE,
    batch_label: str | None = None,
    with_pdfs: bool = False,
    allow_archived_cluster: bool = False,
    papers_json: str | Path | None = None,
) -> int:
    del no_fit_check_auto_labels
    cfg = get_config()
    kb = str(cfg.root)
    no_zotero = os.environ.get("RESEARCH_HUB_NO_ZOTERO", "").lower() in ("1", "true", "yes")
    clusters = ClusterRegistry(cfg.clusters_file)
    cluster_obj = clusters.get(cluster_slug) if cluster_slug else None
    if cluster_slug is not None and cluster_obj is None:
        raise ValueError("Cluster not found - use 'research-hub clusters new' first")
    if (
        cluster_obj is not None
        and getattr(cluster_obj, "status", "active") == "archived"
        and not allow_archived_cluster
    ):
        print(
            f"Cluster '{cluster_obj.slug}' is archived; skipping ingest. "
            "Pass an explicit --cluster value to override."
        )
        return 0
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
    pdf_attach_summary_json: dict[str, object] | None = None
    # WF-2: honor an explicit per-run input path (passed by auto_pipeline) so
    # concurrent runs cannot clobber each other via the shared default file.
    papers_json = Path(papers_json) if papers_json else cfg.root / "papers_input.json"
    collection_name = (
        cfg.zotero_collections.get(collection_key, {}).get("name", collection_key)
        if collection_key is not None
        else "<unconfigured>"
    )
    if query is None and cluster_slug is not None:
        if cluster_obj is not None and cluster_obj.first_query:
            query = cluster_obj.first_query
    requested_batch_label = batch_label
    if requested_batch_label is None:
        env_batch_label = str(os.environ.get("RESEARCH_HUB_BATCH_LABEL", "") or "").strip()
        requested_batch_label = env_batch_label or None
    resolved_batch_label = resolve_batch_label(query, requested_batch_label)
    explicit_batch_label = requested_batch_label is not None
    manifest = Manifest(cfg.research_hub_dir / "manifest.jsonl")
    dedup_path = cfg.research_hub_dir / "dedup_index.json"
    fit_warnings = 0
    fit_accepted = 0
    fit_rejected = 0
    fit_candidates_in = 0
    in_batch_collapsed = 0
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
                _unescape_html_in_paper(paper)
                _normalize_paper_metadata(paper)
                paper_errors = _validate_paper_input(paper, idx)
                # PR-C: a paper missing one or more required core fields
                # (e.g. CrossRef returning an entry with empty `authors`) is
                # skipped from THIS batch, not allowed to abort the whole
                # ingest. Dry-run keeps the strict surfacing so all
                # validation issues stay visible.
                if not dry_run and _only_missing_required_field_errors(paper_errors):
                    skipped_invalid.append((idx, paper, paper_errors))
                    continue
                valid_papers.append(paper)
                if dry_run:
                    for err in paper_errors:
                        if _is_nonfatal_paper_error(err):
                            nonfatal_errors.append(err)
                        else:
                            all_errors.append(err)
                else:
                    nonfatal_errors.extend(
                        err for err in paper_errors if _is_nonfatal_paper_error(err)
                    )
                    all_errors.extend(
                        err for err in paper_errors if not _is_nonfatal_paper_error(err)
                    )
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
                if dry_run:
                    p(
                        f"\nContinuing dry-run with {len(nonfatal_errors)} non-fatal warnings. "
                        "A real ingest would fail before any writes."
                    )
                else:
                    p(f"\nContinuing ingest with {len(nonfatal_errors)} non-fatal warnings.")

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
                            batch_label=resolved_batch_label,
                        )
                    )
            p(f"DRY RUN: would process {len(papers)} papers. Config OK. Exiting.")
            return 0

        cluster_coll = cluster_obj.zotero_collection_key if cluster_obj else None
        batch_coll = ""
        zotero_batch_label = ""
        if no_zotero:
            zot = None
            dedup = _load_or_build_dedup(cfg, None, dry_run=False)
            p("RESEARCH_HUB_NO_ZOTERO=1 - skipping Zotero, using Obsidian-only mode")
            if cluster_slug:
                print(
                    "\n".join(
                        [
                            "=" * 60,
                            "WARNING: Zotero writes DISABLED (RESEARCH_HUB_NO_ZOTERO=1)",
                            f"This run will write Obsidian notes only. Cluster '{cluster_slug}'",
                            "Zotero collection will NOT receive these papers. Unset the",
                            "env var to re-enable Zotero writes.",
                            "=" * 60,
                        ]
                    ),
                    file=sys.stderr,
                )
        else:
            zot = get_client()
            dedup = _load_or_build_dedup(cfg, zot, dry_run=False)
            p("Zotero client ready")
            if cluster_slug and cluster_coll:
                if not explicit_batch_label:
                    resolved_batch_label = _next_batch_label(
                        zot,
                        cluster_coll=cluster_coll,
                        batch_label=resolved_batch_label,
                    )
                batch_coll = _ensure_batch_subcollection(
                    zot,
                    cluster_coll=cluster_coll,
                    batch_label=resolved_batch_label,
                    log=p,
                )
                zotero_batch_label = resolved_batch_label

        zr: list[dict] = []
        obr: list[dict] = []
        dr: list[dict] = []
        errors: list[dict] = []
        papers_for_notes: list[dict] = []
        pending_zotero_papers: list[dict] = []
        # Papers whose Zotero item already exists (dedup zotero_hit): the item
        # is reused (no duplicate created) but the paper is STILL ingested into
        # research-hub. Collected separately because write_papers_to_zotero
        # reassigns papers_for_notes below, which would discard direct appends.
        reused_zotero_papers: list[dict] = []
        target_collection_key = cluster_coll or collection_key

        from research_hub.authenticity import verify_authenticity

        fit_candidates_in = len(papers) if fit_check else 0
        accepted_papers, quarantined_papers = verify_authenticity(
            papers,
            cfg,
            cluster_slug=cluster_slug,
            do_fit_check=fit_check,
            fit_check_threshold=fit_check_threshold,
        )
        papers = accepted_papers
        p(
            f"\n=== AUTHENTICITY GATE ===\n"
            f"accepted: {len(accepted_papers)}; quarantined: {len(quarantined_papers)}"
        )
        for item in quarantined_papers:
            p(
                "  QUARANTINED "
                f"{item.get('slug', '(unknown)')} "
                f"{item.get('layer', '')}:{item.get('reason', '')}"
            )
            if fit_check and item.get("layer") == "L4":
                fit_rejected += 1
            manifest.append(
                new_entry(
                    cluster=str(item.get("cluster") or cluster_slug or ""),
                    query=_query_for_paper(item.get("raw_candidate", {}), query),
                    action="quarantine",
                    doi=item.get("raw_candidate", {}).get("doi", ""),
                    title=item.get("raw_candidate", {}).get("title", ""),
                    error=str(item.get("reason", "")),
                    batch_label=resolved_batch_label,
                )
            )

        # --- In-batch dedup -------------------------------------------------
        # Two backends can return the SAME paper under different DOIs (e.g. a
        # journal DOI vs a repository/preprint DOI). Search-merge dedup is
        # DOI-keyed, so it keeps both; each would then get its own Zotero item
        # and the two notes would collide on an identical filename slug (one
        # silently overwrites the other). dedup.check() in the loop below
        # cannot catch this either: dedup.add() runs only in the note-writing
        # loop, so in-batch siblings stay invisible during Zotero creation.
        # Collapse them here, keeping the first occurrence.
        deduped_papers: list[dict] = []
        seen_dois: set[str] = set()
        seen_titles: set[str] = set()
        for pp in papers:
            ndoi = normalize_doi(pp.get("doi", ""))
            # A real DOI is "10.<registrant>/<suffix>". Sentinel placeholders
            # some backends emit for an unknown DOI ("N/A", "none", "-") also
            # normalize to a truthy string; keying on those would false-
            # collapse genuinely distinct papers. Require the 10./ shape.
            doi_key = ndoi if (ndoi.startswith("10.") and "/" in ndoi) else ""
            ntitle = normalize_title(pp.get("title"))
            # Mirror DedupIndex.add(): only title-match on titles long enough
            # to be distinctive (>15 normalized chars) to avoid false merges.
            title_key = ntitle if len(ntitle) > 15 else ""
            if (doi_key and doi_key in seen_dois) or (
                title_key and title_key in seen_titles
            ):
                p(
                    f"  [in-batch dup] {pp.get('title', '')[:55]}... "
                    "collapsed (matches an earlier candidate)"
                )
                manifest.append(
                    new_entry(
                        cluster=cluster_slug or "",
                        query=_query_for_paper(pp, query),
                        action="dup-in-batch",
                        doi=pp.get("doi", ""),
                        title=pp.get("title", ""),
                        batch_label=resolved_batch_label,
                    )
                )
                continue
            deduped_papers.append(pp)
            if doi_key:
                seen_dois.add(doi_key)
            if title_key:
                seen_titles.add(title_key)
        in_batch_collapsed = len(papers) - len(deduped_papers)
        if in_batch_collapsed:
            p(
                f"  [in-batch dedup] collapsed "
                f"{in_batch_collapsed} same-paper duplicate(s)"
            )
        papers = deduped_papers

        for i, pp in enumerate(papers):
            p(f"\n--- Paper {i+1}: {pp['title'][:60]}...")
            query_text = _query_for_paper(pp, query)
            if pp.get("year_drift_warning"):
                p(
                    f"  [warn] year-drift: {pp['slug']} "
                    f"ingest={pp.get('year')} doi-lookup={pp.get('metadata_year')}"
                )
            if fit_check:
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
                    # Only treat an obsidian_hit as a true duplicate (skip)
                    # when the note file ACTUALLY EXISTS. A stale dedup-index
                    # entry pointing at a deleted note must NOT cause a skip;
                    # fall through so the paper is ingested fresh.
                    if (
                        obsidian_hit
                        and obsidian_hit.obsidian_path
                        and Path(obsidian_hit.obsidian_path).exists()
                    ):
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
                                batch_label=resolved_batch_label,
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
                    if zotero_hit and no_zotero:
                        # no_zotero mode: zot is None, so the Zotero-item
                        # reuse ops below would fail. Still ingest the
                        # note; treat it like any other no_zotero paper.
                        pp["zotero_key"] = ""
                        zr.append(
                            {"title": pp["title"],
                             "status": "SKIPPED_NO_ZOTERO", "key": ""}
                        )
                        papers_for_notes.append(pp)
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
                                hub_tags = set(
                                    _compose_hub_tags(
                                        pp,
                                        cluster_slug,
                                        batch_label=zotero_batch_label,
                                    )
                                )
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
                        # The Zotero item already exists — its useful work is
                        # done above (moved into the cluster collection, hub
                        # tags + note added; NO duplicate Zotero item created).
                        # The paper is NOT skipped: it must still be ingested
                        # into research-hub. Reuse the existing Zotero key and
                        # defer to Obsidian-note creation downstream.
                        pp["zotero_key"] = zotero_hit.zotero_key or ""
                        manifest.append(
                            new_entry(
                                cluster=cluster_slug or "",
                                query=query_text,
                                action="ingest-reuse-zotero",
                                doi=pp["doi"],
                                title=pp["title"],
                                zotero_key=zotero_hit.zotero_key or "",
                                batch_label=resolved_batch_label,
                            )
                        )
                        p("  REUSING existing Zotero item; ingesting into cluster")
                        reused_zotero_papers.append(pp)
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

            pending_zotero_papers.append(pp)

        if not no_zotero and pending_zotero_papers:
            zr, papers_for_notes, zotero_errors = write_papers_to_zotero(
                zot,
                pending_zotero_papers,
                cluster_slug,
                target_collection_key,
                batch_coll=batch_coll or None,
                batch_label=zotero_batch_label,
                zotero_batch_size=zotero_batch_size,
                log=p,
            )
            errors.extend(zotero_errors)

        # write_papers_to_zotero reassigns papers_for_notes, so add the
        # reused-Zotero papers AFTER it: they reuse an existing Zotero item but
        # still need an Obsidian note + cluster binding created downstream.
        papers_for_notes.extend(reused_zotero_papers)

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
                        cluster_moc_links=(
                            list(getattr(cluster_obj, "moc_links", []) or [])
                            if cluster_obj
                            else None
                        ),
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
                        batch_label=resolved_batch_label,
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
                        batch_label=resolved_batch_label,
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

        if with_pdfs and not no_zotero:
            from research_hub.zotero.pdf_attach import (
                attach_pdfs,
                format_pdf_attach_summary,
                plan_attach_for_items,
                summarize_pdf_attach,
            )

            oa_email = (
                getattr(cfg, "unpaywall_email", "")
                or (
                    cfg.zotero.get("unpaywall_email", "")
                    if isinstance(getattr(cfg, "zotero", None), dict)
                    else ""
                )
            )
            just_added_keys = [pp["zotero_key"] for pp in papers_for_notes if pp.get("zotero_key")]
            if just_added_keys:
                try:
                    items = [zot.item(key) for key in just_added_keys]
                    plans = plan_attach_for_items(items, unpaywall_email=oa_email)
                    pdf_results = attach_pdfs(zot, plans, rate_limit_rps=2.0, cfg=cfg)
                    slug_by_key = {
                        pp.get("zotero_key", ""): pp.get("slug", "")
                        for pp in papers_for_notes
                        if pp.get("zotero_key")
                    }
                    pdf_attach_summary = summarize_pdf_attach(
                        plans,
                        pdf_results,
                        slug_by_key=slug_by_key,
                    )
                    pdf_attach_summary_json = pdf_attach_summary.to_json()
                    for line in format_pdf_attach_summary(pdf_attach_summary).splitlines():
                        p(line)
                    if cluster_slug:
                        pdf_batch_label = f"pdf-attach-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
                        papers_by_key = {
                            pp.get("zotero_key", ""): pp
                            for pp in papers_for_notes
                            if pp.get("zotero_key")
                        }
                        for item_key, status in pdf_results.items():
                            if status != "ok":
                                continue
                            paper = papers_by_key.get(item_key)
                            if paper is None:
                                continue
                            manifest.append(
                                new_entry(
                                    cluster=cluster_slug,
                                    query=_query_for_paper(paper, query),
                                    action="pdf-attach",
                                    doi=paper.get("doi", ""),
                                    title=paper.get("title", ""),
                                    zotero_key=item_key,
                                    batch_label=pdf_batch_label,
                                )
                            )
                except Exception as exc:
                    p(f"  [warn] PDF attach failed: {exc}")

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
                f"fit-check: {fit_candidates_in} in, {fit_accepted} accepted, "
                f"{fit_rejected} rejected, {fit_warnings} warnings"
                + (
                    f", {in_batch_collapsed} in-batch-collapsed"
                    if in_batch_collapsed
                    else ""
                )
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
        if pdf_attach_summary_json is not None:
            out["pdf_attach_summary"] = pdf_attach_summary_json
        with out_path.open("w", encoding="utf-8") as file_obj:
            json.dump(out, file_obj, indent=2, ensure_ascii=False)
        dedup.save(dedup_path)
        if errors:
            errors_log = _write_error_log(cfg.logs, errors)
            p(f"Errors logged: {errors_log}")
        if cluster_obj is not None:
            try:
                hub_result = _sync_hub_overview(cfg, cluster_obj)
                if hub_result["moc_links"]:
                    p("MOCs: " + ", ".join(hub_result["moc_links"]))
                p(f"Hub overview: {hub_result['overview_path']}")
            except Exception as exc:
                p(f"  [warn] hub overview population failed: {exc}")
            try:
                gap_report = compute_ingest_gap(
                    cluster_slug=cluster_obj.slug,
                    vault_root=Path(cfg.root),
                )
                write_gap_sidecar(
                    cluster_slug=cluster_obj.slug,
                    vault_root=Path(cfg.root),
                    gap_report=gap_report,
                )
                if gap_report["gap_count"] > 0:
                    p(
                        f"  [warn] ingest gap: {gap_report['gap_count']} of "
                        f"{gap_report['accepted_count']} fit-check-accepted papers "
                        f"did not reach raw/{cluster_obj.slug}/"
                    )
                    for entry in gap_report["gap"][:5]:
                        p(f"    - {entry['doi']}  {entry['title'][:80]}")
                    if gap_report["gap_count"] > 5:
                        p(f"    (+{gap_report['gap_count'] - 5} more in .ingest_gap.json)")
            except Exception as exc:
                p(f"  [warn] ingest-gap reporting failed: {exc}")
        p(f"JSON: {out_path}\n=== DONE ===")

    if cluster_obj is not None:
        _refresh_cluster_base(cfg, cluster_obj)
    if no_zotero and cluster_slug and not dry_run:
        print(f"[no-zotero] wrote {oc} obsidian notes; 0 zotero items", file=sys.stderr)
    return 0


def _sync_hub_overview(cfg, cluster) -> dict[str, object]:
    cluster_queries = [str(getattr(cluster, "first_query", "") or "")]
    moc_links = derive_moc_links(
        cluster.slug,
        cluster_queries=cluster_queries,
        moc_links=list(getattr(cluster, "moc_links", []) or []),
    )
    for name in moc_links:
        ensure_moc(Path(cfg.root), name)
    overview_path = populate_overview(
        cluster_slug=cluster.slug,
        vault_root=Path(cfg.root),
        moc_links=moc_links,
    )
    return {"overview_path": overview_path, "moc_links": moc_links}


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
