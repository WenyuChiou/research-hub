"""Paper-level vault operations."""

from __future__ import annotations

import html
import json
import logging
import re
from copy import copy
from pathlib import Path

from research_hub.config import get_config
from research_hub.dedup import DedupHit, DedupIndex, normalize_doi
from research_hub.fsops import robust_move
from research_hub.security import ValidationError, safe_join
from research_hub._useragent import user_agent

logger = logging.getLogger(__name__)

VALID_STATUSES = {"unread", "reading", "deep-read", "cited"}
_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,6}(?:v\d+)?$")
_ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(\d{4}\.\d{4,6}(?:v\d+)?)$", re.IGNORECASE)
_HUB_SECTION_RE = re.compile(
    r"^## Hub\s*\n.*?(?=^##\s+|\n---\n|\Z)",
    re.MULTILINE | re.DOTALL,
)


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


def _update_frontmatter_field(
    md_path: Path, field: str, value: str, *, insert_if_absent: bool = False
) -> bool:
    """Replace a YAML frontmatter field value in-place.

    When ``insert_if_absent`` is True and the field is missing from an existing
    frontmatter block, the field is appended instead of being treated as a
    no-op. (Default False preserves the no-op contract that the ``status`` and
    unbind callers rely on.) A note with no frontmatter block at all still
    returns False — the caller cannot safely synthesise a whole block.
    """
    parsed = _read_frontmatter_text(md_path)
    if parsed is None:
        return False
    _, frontmatter, tail = parsed
    pattern = rf'^({re.escape(field)}:\s*).*$'
    quoted = f'"{value}"' if value == "" or any(ch.isspace() for ch in value) else value
    new_frontmatter, count = re.subn(pattern, rf"\g<1>{quoted}", frontmatter, flags=re.MULTILINE)
    if count == 0:
        if not insert_if_absent:
            return False
        # Append the missing field to the existing block (frontmatter ends
        # without a trailing newline; the closing "\n---" lives in `tail`).
        new_frontmatter = f'{frontmatter.rstrip(chr(10))}\n{field}: {quoted}'
    md_path.write_text(f"---{new_frontmatter}{tail}", encoding="utf-8")
    return True


def _read_title(md_path: Path) -> str:
    title = _frontmatter_value(md_path, "title")
    return title or md_path.stem


def _moc_links_for_cluster(cfg, cluster_slug: str) -> list[str]:
    try:
        from research_hub.clusters import ClusterRegistry
        from research_hub.vault.hub_overview import derive_moc_links

        cluster = ClusterRegistry(cfg.clusters_file).get(cluster_slug)
        if cluster is None:
            return derive_moc_links(cluster_slug, for_paper_note=True)
        return derive_moc_links(
            cluster_slug,
            cluster_queries=[str(cluster.first_query or "")],
            moc_links=list(cluster.moc_links or []),
            for_paper_note=True,
        )
    except (ImportError, OSError, ValueError, TypeError) as exc:
        logger.warning("could not derive MOC links for %s: %s", cluster_slug, exc)
        return []


def _render_hub_block(cluster_slug: str, moc_links: list[str]) -> str:
    lines = [f"- Cluster: [[{cluster_slug}/00_overview|{cluster_slug}]]"]
    lines.extend(f"- MOC: [[{moc}]]" for moc in moc_links if str(moc).strip())
    return "## Hub\n\n" + "\n".join(lines) + "\n\n"


def _retarget_body_refs(md_path: Path, old_cluster: str, to_cluster: str, cfg) -> bool:
    text = md_path.read_text(encoding="utf-8")
    hub_block = _render_hub_block(to_cluster, _moc_links_for_cluster(cfg, to_cluster))
    if _HUB_SECTION_RE.search(text):
        updated = _HUB_SECTION_RE.sub(hub_block, text, count=1)
    else:
        footer = re.search(r"\n---\n\*Source:", text)
        if footer:
            updated = text[: footer.start()] + "\n" + hub_block + text[footer.start():]
        else:
            updated = text.rstrip() + "\n\n" + hub_block

    if old_cluster:
        updated = updated.replace(f"topic:{old_cluster}", f"topic:{to_cluster}")

    if updated == text:
        return False
    md_path.write_text(updated, encoding="utf-8")
    return True


def _sync_related_paper_links(slug: str, target_path: Path, old_cluster: str, to_cluster: str, cfg) -> dict:
    from research_hub.vault.link_updater import remove_paper_links, update_cluster_links

    cleaned = 0
    if old_cluster and old_cluster != to_cluster:
        cleaned = remove_paper_links(removed_slug=slug, vault_raw_dir=cfg.raw, cluster_slug=old_cluster)
    target_result = update_cluster_links(
        new_note_path=target_path,
        vault_raw_dir=cfg.raw,
        cluster_slug=to_cluster,
    )
    return {"old_links_cleaned": cleaned, "target_links": target_result}


def _sync_dedup_path(old_path: Path, new_path: Path, cfg) -> dict[str, int | bool]:
    index_path = cfg.research_hub_dir / "dedup_index.json"
    if not index_path.exists():
        return {"dedup_synced": False, "dedup_removed": 0}
    index = DedupIndex.load(index_path)
    removed = index.invalidate_obsidian_path(str(old_path))
    removed += index.invalidate_obsidian_path(str(new_path))
    zotero_key = _frontmatter_value(new_path, "zotero-key") or None
    if zotero_key == "null":
        zotero_key = None
    index.add(
        DedupHit(
            source="obsidian",
            doi=_frontmatter_value(new_path, "doi"),
            title=_frontmatter_value(new_path, "title"),
            zotero_key=zotero_key,
            obsidian_path=str(new_path),
        )
    )
    index.save(index_path)
    return {"dedup_synced": True, "dedup_removed": removed}


def remove_paper(identifier: str, include_zotero: bool = False, dry_run: bool = False) -> dict:
    """Remove one or more notes resolved by DOI or slug."""
    from research_hub.vault.link_updater import remove_paper_links

    removed_files: list[str] = []
    zotero_deleted = False
    links_cleaned: int = 0
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
        slug = md_path.stem
        cluster_slug = _frontmatter_value(md_path, "topic_cluster")
        removed_files.append(str(md_path))
        if not dry_run and md_path.exists():
            md_path.unlink()
            # Cascade: scrub backward wikilinks in sibling notes.
            # Vault layout: raw/<cluster>/<note>.md → parent.parent = cfg.raw
            if cluster_slug:
                links_cleaned += remove_paper_links(slug, md_path.parent.parent, cluster_slug)
    if removed_files and not dry_run:
        _save_index_without_paths([Path(path) for path in removed_files])
    return {
        "removed_files": removed_files,
        "zotero_deleted": zotero_deleted,
        "links_cleaned": links_cleaned,
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


def move_paper(
    slug: str,
    to_cluster: str,
    *,
    source_path: str | Path | None = None,
    raw_root: str | Path | None = None,
) -> dict:
    """Move a note into a different raw/ cluster folder and sync vault indexes.

    When ``source_path`` is provided the caller already knows exactly which file
    to move and it is used verbatim. Otherwise the note is resolved by slug
    across the whole vault (``rglob``). Callers moving a note OUT of a SPECIFIC
    cluster (cluster merge / split) MUST pass ``source_path``: resolving by slug
    alone returns the alphabetically-first match, which silently moves the WRONG
    file when the same slug exists in more than one cluster.
    """
    cfg = get_config()
    raw_dir = (Path(raw_root) if raw_root is not None else Path(cfg.raw)).resolve()
    if raw_root is not None:
        # Keep file moves and their note/link helpers on the caller's raw root,
        # without mutating the process-cached HubConfig object.
        cfg = copy(cfg)
        cfg.raw = raw_dir
    if source_path is not None:
        src = Path(source_path)
    else:
        matches = sorted(raw_dir.rglob(f"{slug}.md"))
        if not matches:
            raise FileNotFoundError(f"Paper not found: {slug}")
        src = matches[0]
    try:
        relative_source = src.absolute().relative_to(raw_dir)
    except ValueError as exc:
        raise ValidationError(f"source path {src} is outside raw root {raw_dir}") from exc
    src = safe_join(raw_dir, *relative_source.parts, reject_symlinks=True)
    if not src.exists():
        raise FileNotFoundError(f"Paper not found: {src}")
    old_cluster = _frontmatter_value(src, "topic_cluster")
    target_path = safe_join(
        raw_dir, to_cluster, f"{slug}.md", reject_symlinks=True
    )
    target_dir = target_path.parent
    if old_cluster == to_cluster and src == target_path:
        # No-op move: return the full dict shape so callers can always index
        # old_cluster / sync_warnings / dedup_* without a KeyError.
        return {
            "from": str(src),
            "to": str(target_path),
            "cluster": to_cluster,
            "old_cluster": old_cluster,
            "frontmatter_updated": False,
            "body_refs_updated": False,
            "old_links_cleaned": 0,
            "target_links": {"forward": 0, "backward": 0, "scanned": 0},
            "dedup_synced": False,
            "dedup_removed": 0,
            "sync_warnings": [],
        }
    target_dir.mkdir(parents=True, exist_ok=True)
    robust_move(str(src), str(target_path))

    sync_warnings: list[str] = []
    frontmatter_updated = _update_frontmatter_field(
        target_path, "topic_cluster", to_cluster, insert_if_absent=True
    )
    if not frontmatter_updated:
        sync_warnings.append("topic_cluster frontmatter field missing or unchanged")

    body_refs_updated = False
    related_links: dict = {"old_links_cleaned": 0, "target_links": {"forward": 0, "backward": 0, "scanned": 0}}
    dedup_result: dict[str, int | bool] = {"dedup_synced": False, "dedup_removed": 0}

    try:
        body_refs_updated = _retarget_body_refs(target_path, old_cluster, to_cluster, cfg)
    except OSError as exc:
        msg = f"body refs not fully retargeted: {exc}"
        sync_warnings.append(msg)
        logger.warning("move_paper(%s): %s", slug, msg)

    try:
        related_links = _sync_related_paper_links(slug, target_path, old_cluster, to_cluster, cfg)
    except (OSError, ImportError) as exc:
        msg = f"related-paper links not fully synced: {exc}"
        sync_warnings.append(msg)
        logger.warning("move_paper(%s): %s", slug, msg)

    try:
        dedup_result = _sync_dedup_path(src, target_path, cfg)
    except (OSError, ValueError, TypeError) as exc:
        msg = f"dedup index not fully synced: {exc}"
        sync_warnings.append(msg)
        logger.warning("move_paper(%s): %s", slug, msg)

    return {
        "from": str(src),
        "to": str(target_path),
        "cluster": to_cluster,
        "old_cluster": old_cluster,
        "frontmatter_updated": frontmatter_updated,
        "body_refs_updated": body_refs_updated,
        **related_links,
        **dedup_result,
        "sync_warnings": sync_warnings,
    }


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
                headers={"User-Agent": user_agent(None)},
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
    # v0.84.0: use canonical make_paper_slug (matches safe_filename) instead of
    # raw re.sub(...)[:60] long format that caused broken cross-ref wikilinks.
    from research_hub.zotero.fetch import make_paper_slug
    slug = make_paper_slug(last_name, paper.year, paper.title)
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
