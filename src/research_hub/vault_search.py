"""Search helpers for local vault notes."""

from __future__ import annotations

from pathlib import Path

from research_hub.clusters import slugify
from research_hub.config import get_config
from research_hub.operations import _frontmatter_value


def _iter_notes(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    return sorted(raw_dir.rglob("*.md"))


def search_vault(
    query: str,
    cluster: str | None = None,
    status: str | None = None,
    full_text: bool = False,
    limit: int = 20,
) -> list[dict]:
    """Search notes in the configured raw/ vault."""
    cfg = get_config()
    query_lower = query.lower()
    query_tokens = [token for token in slugify(query).split("-") if token]
    results: list[dict] = []

    for note_path in _iter_notes(cfg.raw):
        title = _frontmatter_value(note_path, "title") or note_path.stem
        note_cluster = _frontmatter_value(note_path, "topic_cluster")
        note_status = _frontmatter_value(note_path, "status") or "unread"
        if cluster and note_cluster != cluster:
            continue
        if status and note_status != status:
            continue

        if full_text:
            matched = query_lower in note_path.read_text(encoding="utf-8", errors="ignore").lower()
        else:
            title_slug = slugify(title)
            matched = any(token in title_slug for token in query_tokens)
        if not matched:
            continue
        results.append(
            {
                "slug": note_path.stem,
                "title": title,
                "cluster": note_cluster,
                "status": note_status,
                "path": str(note_path),
            }
        )
        if len(results) >= limit:
            break
    return results
