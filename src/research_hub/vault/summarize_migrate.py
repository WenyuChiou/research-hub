"""Migration for v0.87.2 paper summary status frontmatter."""

from __future__ import annotations

from pathlib import Path

from research_hub.paper import _parse_frontmatter, _split_frontmatter
from research_hub.paper_summarize import (
    extract_markdown_section,
    has_sticky_placeholder,
    is_bad_abstract,
    replace_summary_sections_with_pending_callouts,
    sections_are_substantive,
    set_frontmatter_fields,
)


def migrate_existing_to_pending_status(
    vault_root,
    *,
    cluster_slug_filter: str | None = None,
    dry_run: bool = True,
) -> list[tuple[Path, str]]:
    """Backfill summarize_status on existing raw paper notes.

    Returns ``(path, action)`` tuples. Actions include ``already_set``,
    ``pending``, ``done``, ``failed_no_abstract``, and skip reasons.
    """

    root = Path(vault_root)
    raw_root = root / "raw"
    results: list[tuple[Path, str]] = []
    if not raw_root.exists():
        return results

    cluster_dirs = [raw_root / cluster_slug_filter] if cluster_slug_filter else sorted(raw_root.iterdir())
    for cluster_dir in cluster_dirs:
        if not cluster_dir.is_dir() or cluster_dir.name.startswith("_"):
            continue
        for note_path in sorted(cluster_dir.glob("*.md")):
            if note_path.name in {"00_overview.md", "index.md"}:
                continue
            action = migrate_one_note(note_path, dry_run=dry_run)
            results.append((note_path, action))
    return results


def migrate_one_note(note_path: Path, *, dry_run: bool = True) -> str:
    text = note_path.read_text(encoding="utf-8")
    if _split_frontmatter(text) is None:
        return "skipped_no_frontmatter"
    meta = _parse_frontmatter(text)
    if str(meta.get("summarize_status", "") or "").strip():
        return "already_set"

    abstract = extract_markdown_section(text, "Abstract")
    if is_bad_abstract(abstract):
        action = "failed_no_abstract"
        updated = replace_summary_sections_with_pending_callouts(text) if has_sticky_placeholder(text) else text
        updated = set_frontmatter_fields(updated, {"summarize_status": action})
    elif has_sticky_placeholder(text):
        action = "pending"
        updated = replace_summary_sections_with_pending_callouts(text)
        updated = set_frontmatter_fields(updated, {"summarize_status": action})
    elif sections_are_substantive(text):
        action = "done"
        updated = set_frontmatter_fields(text, {"summarize_status": action})
    else:
        action = "pending"
        updated = replace_summary_sections_with_pending_callouts(text)
        updated = set_frontmatter_fields(updated, {"summarize_status": action})

    if not dry_run and updated != text:
        with note_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
    return action
