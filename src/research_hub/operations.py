"""Paper-level vault operations."""

from __future__ import annotations

import re
from pathlib import Path

from research_hub.config import get_config
from research_hub.dedup import DedupIndex, normalize_doi

VALID_STATUSES = {"unread", "reading", "deep-read", "cited"}


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
