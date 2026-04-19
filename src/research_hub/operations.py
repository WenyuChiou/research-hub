"""Paper-level vault operations."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from research_hub.config import get_config
from research_hub.dedup import DedupIndex, normalize_doi

VALID_STATUSES = {"unread", "reading", "deep-read", "cited"}
_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,6}(?:v\d+)?$")
_ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(\d{4}\.\d{4,6}(?:v\d+)?)$", re.IGNORECASE)


def _read_frontmatter_text(md_path: Path) -> tuple[str, str, str] | None:
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text, text[3:end], text[end:]


def _frontmatter_value(md_path: Path, field: str) -> str:
    parsed = _read_frontmatter_text(md_path)
    if parsed is None:
        return ""
    _, frontmatter, _ = parsed
    match = re.search(rf'^{re.escape(field)}:\s*["\']?([^"\n\']*)["\']?', frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _find_note_paths(identifier: str) -> list[Path]:
    cfg = get_config()
    matches: list[Path] = []
    index = DedupIndex.load(cfg.research_hub_dir / "dedup_index.json")
    normalized = normalize_doi(identifier)
    for hit in index.doi_to_hits.get(normalized, []):
        if hit.obsidian_path:
            path = Path(hit.obsidian_path)
            if path.exists() and path not in matches:
                matches.append(path)
    for path in sorted(cfg.raw.rglob(f"{identifier}.md")):
        if path not in matches:
            matches.append(path)
    return matches


def _save_index_without_paths(paths: list[Path]) -> None:
    cfg = get_config()
    index_path = cfg.research_hub_dir / "dedup_index.json"
    index = DedupIndex.load(index_path)
    removed = {str(path) for path in paths}

    def keep_hits(mapping: dict[str, list]) -> dict[str, list]:
        filtered: dict[str, list] = {}
        for key, hits in mapping.items():
            kept = [hit for hit in hits if hit.obsidian_path not in removed]
            if kept:
                filtered[key] = kept
        return filtered

    index.doi_to_hits = keep_hits(index.doi_to_hits)
    index.title_to_hits = keep_hits(index.title_to_hits)
    index.save(index_path)


def _update_frontmatter_field(md_path: Path, field: str, value: str) -> bool:
    """Replace a YAML frontmatter field value in-place."""
    parsed = _read_frontmatter_text(md_path)
    if parsed is None:
        return False
    _, frontmatter, tail = parsed
    pattern = rf'^({re.escape(field)}:\s*).*$'
    quoted = f'"{value}"' if value == "" or any(ch.isspace() for ch in value) else value
    new_frontmatter, count = re.subn(pattern, rf"\g<1>{quoted}", frontmatter, flags=re.MULTILINE)
    if count == 0:
        return False
    md_path.write_text(f"---{new_frontmatter}{tail}", encoding="utf-8")
    return True


def _read_title(md_path: Path) -> str:
    title = _frontmatter_value(md_path, "title")
    return title or md_path.stem


def remove_paper(identifier: str, include_zotero: bool = False, dry_run: bool = False) -> dict:
    """Remove one or more notes resolved by DOI or slug."""
    removed_files: list[str] = []
    zotero_deleted = False
    for md_path in _find_note_paths(identifier):
        if include_zotero:
            zotero_key = _frontmatter_value(md_path, "zotero-key")
            if zotero_key:
                try:
                    from research_hub.zotero.client import ZoteroDualClient

                    ZoteroDualClient().delete_item(zotero_key)
                    zotero_deleted = True
                except Exception:
                    pass
        removed_files.append(str(md_path))
        if not dry_run and md_path.exists():
            md_path.unlink()
    if removed_files and not dry_run:
        _save_index_without_paths([Path(path) for path in removed_files])
    return {
        "removed_files": removed_files,
        "zotero_deleted": zotero_deleted,
        "dry_run": dry_run,
    }


def mark_paper(slug: str | None, status: str, cluster: str | None = None) -> dict:
    """Update reading status for a note or every note in a cluster."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    cfg = get_config()
    if slug:
        paths = sorted(cfg.raw.rglob(f"{slug}.md"))
    elif cluster:
        paths = sorted((cfg.raw / cluster).glob("*.md"))
    else:
        raise ValueError("Provide either a slug or a cluster")
    updated = [str(path) for path in paths if _update_frontmatter_field(path, "status", status)]
    return {"updated": updated, "status": status}


def move_paper(slug: str, to_cluster: str) -> dict:
    """Move a note into a different raw/ cluster folder and update frontmatter."""
    cfg = get_config()
    matches = sorted(cfg.raw.rglob(f"{slug}.md"))
    if not matches:
        raise FileNotFoundError(f"Paper not found: {slug}")
    source_path = matches[0]
    old_cluster = _frontmatter_value(source_path, "topic_cluster")
    target_dir = cfg.raw / to_cluster
    target_path = target_dir / f"{slug}.md"
    if old_cluster == to_cluster and source_path == target_path:
        return {"from": str(source_path), "to": str(target_path), "cluster": to_cluster}
    target_dir.mkdir(parents=True, exist_ok=True)
    source_path.replace(target_path)
    _update_frontmatter_field(target_path, "topic_cluster", to_cluster)
    return {"from": str(source_path), "to": str(target_path), "cluster": to_cluster}


def note_matches_query(md_path: Path, query: str) -> bool:
    """Return True when at least two query tokens overlap with a note title."""
    from research_hub.clusters import slugify

    title_tokens = set(slugify(_read_title(md_path)).split("-"))
    query_tokens = [token for token in slugify(query).split("-") if token]
    overlap = sum(1 for token in query_tokens if token in title_tokens)
    return overlap >= 2


def _extract_arxiv_identifier(identifier: str) -> str:
    text = (identifier or "").strip()
    doi_match = _ARXIV_DOI_RE.fullmatch(text)
    if doi_match:
        return doi_match.group(1)
    if _ARXIV_ID_RE.fullmatch(text):
        return text
    return ""


def add_paper(
    identifier: str,
    cluster: str | None = None,
    *,
    no_zotero: bool = False,
    skip_verify: bool = False,
) -> dict:
    """Fetch a single paper by DOI/arXiv ID and ingest it."""
    import os

    import requests

    from research_hub.pipeline import run_pipeline
    from research_hub.search import ArxivBackend, SemanticScholarClient
    from research_hub.search.semantic_scholar import RateLimitError

    cfg = get_config()
    s2 = SemanticScholarClient()
    arxiv_id = _extract_arxiv_identifier(identifier)
    resolved_identifier = f"ArXiv:{arxiv_id}" if arxiv_id else identifier
    paper = None
    s2_failed = False
    try:
        paper = s2.get_paper(resolved_identifier)
    except RateLimitError:
        s2_failed = True

    if paper is None and arxiv_id:
        paper = ArxivBackend().get_paper(arxiv_id)

    if paper is None:
        if arxiv_id:
            return {
                "status": "error",
                "reason": (
                    f"Could not resolve {identifier} via Semantic Scholar"
                    f"{' (rate limited)' if s2_failed else ''} or arXiv"
                ),
            }
        return {
            "status": "error",
            "reason": f"Could not resolve {identifier} via Semantic Scholar",
        }

    cr_data: dict = {}
    if paper.doi and paper.doi.startswith("10."):
        try:
            response = requests.get(
                f"https://api.crossref.org/works/{paper.doi}",
                timeout=10,
                headers={"User-Agent": "research-hub/0.9.0"},
            )
            if response.status_code == 200:
                cr_data = response.json().get("message", {}) or {}
        except Exception:
            cr_data = {}

    authors: list[dict[str, str]] = []
    if cr_data.get("author"):
        for author in cr_data["author"]:
            authors.append(
                {
                    "creatorType": "author",
                    "firstName": author.get("given", ""),
                    "lastName": author.get("family", ""),
                }
            )
    else:
        for name in paper.authors:
            parts = name.split()
            if len(parts) >= 2:
                authors.append(
                    {
                        "creatorType": "author",
                        "firstName": " ".join(parts[:-1]),
                        "lastName": parts[-1],
                    }
                )
            else:
                authors.append({"creatorType": "author", "name": name})

    container_titles = cr_data.get("container-title") or []
    journal = html.unescape(container_titles[0] if container_titles else (paper.venue or ""))
    volume = str(cr_data.get("volume", "") or "")
    issue = str(cr_data.get("issue", "") or "")
    pages = str(cr_data.get("page", "") or "")

    last_name = authors[0].get("lastName", "unknown") if authors else "unknown"
    last_clean = re.sub(r"[^a-zA-Z]", "", last_name).lower() or "unknown"
    title_slug = re.sub(r"[^a-z0-9]+", "-", paper.title.lower()).strip("-")[:60]
    slug = f"{last_clean}{paper.year}-{title_slug}"
    abstract = paper.abstract or ""
    paper_arxiv_id = str(getattr(paper, "arxiv_id", "") or "")
    derived_doi = f"10.48550/arxiv.{paper_arxiv_id}" if paper_arxiv_id else ""
    doi = paper.doi or derived_doi or identifier
    url = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else "")
    entry = {
        "title": html.unescape(paper.title),
        "doi": doi,
        "authors": authors,
        "year": paper.year,
        "journal": journal,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "abstract": abstract,
        "pdf_url": paper.pdf_url or "",
        "url": url,
        "tags": [],
        "slug": slug,
        "sub_category": cluster or "",
        "summary": abstract[:600],
        "key_findings": [],
        "methodology": "",
        "relevance": "",
    }

    papers_path = cfg.root / "papers_input.json"
    backup_text = papers_path.read_text(encoding="utf-8") if papers_path.exists() else None
    papers_path.write_text(json.dumps([entry], indent=2, ensure_ascii=False), encoding="utf-8")

    previous_no_zotero = os.environ.get("RESEARCH_HUB_NO_ZOTERO")
    try:
        if no_zotero:
            os.environ["RESEARCH_HUB_NO_ZOTERO"] = "1"
        rc = run_pipeline(cluster_slug=cluster, verify=not skip_verify)
    finally:
        if backup_text is None:
            if papers_path.exists():
                papers_path.unlink()
        else:
            papers_path.write_text(backup_text, encoding="utf-8")
        if no_zotero:
            if previous_no_zotero is None:
                os.environ.pop("RESEARCH_HUB_NO_ZOTERO", None)
            else:
                os.environ["RESEARCH_HUB_NO_ZOTERO"] = previous_no_zotero

    obsidian_path = (
        cfg.raw / cluster / f"{slug}.md" if cluster else cfg.root / "raw" / f"{slug}.md"
    )
    return {
        "status": "ok" if rc == 0 else "error",
        "title": entry["title"],
        "doi": entry["doi"],
        "slug": slug,
        "cluster": cluster,
        "zotero_key": "",
        "obsidian_path": str(obsidian_path),
    }
