"""Bidirectional wikilink updater for the Obsidian vault."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


RELATED_SECTION_HEADER = "## Related Papers in This Cluster"
SECTION_PATTERN = re.compile(
    r"(## Related Papers in This Cluster\n)(.*?)(\n## |\n---\n|\Z)",
    re.DOTALL,
)


@dataclass
class NoteMeta:
    """Minimal note metadata used for related-paper linking."""

    path: Path
    title: str
    tags: list[str]
    topic_cluster: str

    @property
    def slug(self) -> str:
        """Obsidian page slug."""
        return self.path.stem


def parse_frontmatter(md_path: Path) -> NoteMeta | None:
    """Extract title, tags, and cluster from note frontmatter."""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    frontmatter = text[3:end]
    title_match = re.search(r'^title:\s*"([^"]+)"', frontmatter, re.MULTILINE)
    tags_match = re.search(r"^tags:\s*\[(.*?)\]", frontmatter, re.MULTILINE | re.DOTALL)
    cluster_match = re.search(
        r'^topic_cluster:\s*["\']?([^"\n\']*)["\']?',
        frontmatter,
        re.MULTILINE,
    )
    tags: list[str] = []
    if tags_match:
        tags = [tag.strip().strip('"').strip("'") for tag in tags_match.group(1).split(",") if tag.strip()]
    return NoteMeta(
        path=md_path,
        title=title_match.group(1) if title_match else md_path.stem,
        tags=tags,
        topic_cluster=cluster_match.group(1).strip() if cluster_match else "",
    )


def find_related_in_cluster(
    new_note: NoteMeta,
    all_notes: list[NoteMeta],
    min_tag_overlap: int = 1,
) -> list[NoteMeta]:
    """Find same-cluster notes ordered by descending tag overlap (at most 10).

    When ``new_note`` has a ``topic_cluster`` set, cluster membership
    alone is sufficient — notes in the same cluster are included even
    when tag overlap is zero. Tag overlap only affects ranking so the
    most topically-similar papers appear first. When ``new_note`` has
    no cluster, fall back to the tag-overlap threshold.

    The result is capped at 10 entries to prevent mega-hub nodes in the
    Obsidian graph view when a cluster grows large.
    """
    related: list[tuple[int, NoteMeta]] = []
    new_tag_set = set(new_note.tags)
    in_cluster = bool(new_note.topic_cluster)
    for other in all_notes:
        if other.path == new_note.path:
            continue
        if in_cluster:
            if other.topic_cluster != new_note.topic_cluster:
                continue
            overlap = len(new_tag_set & set(other.tags))
            related.append((overlap, other))
        else:
            overlap = len(new_tag_set & set(other.tags))
            if overlap >= min_tag_overlap:
                related.append((overlap, other))
    related.sort(key=lambda item: (-item[0], item[1].slug))
    return [item[1] for item in related][:10]


def add_wikilinks_to_note(
    note_path: Path,
    related_slugs: list[str],
    existing_stems: set[str] | None = None,
) -> bool:
    """Create or replace the related-papers section idempotently.

    v0.84.0: When ``existing_stems`` is provided, filter ``related_slugs`` to
    only include slugs that correspond to actual files in the vault. This
    prevents broken `[[wikilink]]` phantom mega-hubs in the Obsidian graph
    view (root cause of the 2026-05-11 graph hygiene audit — 1,199 broken
    cross-refs were found from historical slug-formula divergence between
    `safe_filename()` and `slugify(title)[:60]`).

    When ``existing_stems`` is None, behavior is unchanged for backward
    compat. Callers that have a NoteMeta list should always pass
    ``{note.path.stem for note in all_notes}`` to enforce the safety net.
    """
    if not note_path.exists():
        return False
    if existing_stems is not None:
        related_slugs = [slug for slug in related_slugs if slug in existing_stems]
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    unique_slugs = list(dict.fromkeys(slug for slug in related_slugs if slug))
    new_section = RELATED_SECTION_HEADER + "\n" + "\n".join(
        f"- [[{slug}]]" for slug in unique_slugs
    ) + "\n"
    if SECTION_PATTERN.search(text):
        new_text = SECTION_PATTERN.sub(lambda match: new_section + match.group(3), text, count=1)
    else:
        new_text = text.rstrip() + "\n\n" + new_section
    if new_text == text:
        return False
    note_path.write_text(new_text, encoding="utf-8")
    return True


def update_cluster_links(
    new_note_path: Path,
    vault_raw_dir: Path,
    cluster_slug: str,
    bidirectional: bool = True,
) -> dict[str, int]:
    """Wire a new note into existing notes in the same cluster."""
    new_meta = parse_frontmatter(new_note_path)
    if new_meta is None:
        return {"forward": 0, "backward": 0, "scanned": 0}

    all_notes: list[NoteMeta] = []
    for md_path in vault_raw_dir.rglob("*.md"):
        meta = parse_frontmatter(md_path)
        if meta and meta.topic_cluster == cluster_slug:
            all_notes.append(meta)

    # v0.84.0: pass existing_stems as safety net to prevent broken wikilinks.
    existing_stems = {note.path.stem for note in all_notes} | {new_meta.slug}
    related = find_related_in_cluster(new_meta, all_notes)
    forward = 1 if add_wikilinks_to_note(
        new_note_path, [note.slug for note in related], existing_stems
    ) else 0
    backward = 0

    if bidirectional:
        for other in related:
            text = other.path.read_text(encoding="utf-8", errors="ignore")
            match = SECTION_PATTERN.search(text)
            if match:
                existing_slugs = re.findall(r"\[\[([^\]]+)\]\]", match.group(2))
                if new_meta.slug in existing_slugs:
                    continue
                new_slugs = existing_slugs + [new_meta.slug]
            else:
                new_slugs = [new_meta.slug]
            if add_wikilinks_to_note(other.path, new_slugs, existing_stems):
                backward += 1

    return {"forward": forward, "backward": backward, "scanned": len(all_notes)}


def remove_paper_links(
    removed_slug: str,
    vault_raw_dir: Path,
    cluster_slug: str,
) -> int:
    """Scrub *removed_slug* from every Related Papers section in *cluster_slug*.

    Called after a note is deleted so sibling notes don't accumulate phantom
    wikilinks.  Returns the number of notes that were actually modified.
    """
    modified = 0
    # Build existing_stems once so add_wikilinks_to_note's v0.84.0 safety net
    # can filter out any slugs that no longer exist on disk.
    existing_stems = {p.stem for p in vault_raw_dir.rglob("*.md")}
    for md_path in vault_raw_dir.rglob("*.md"):
        meta = parse_frontmatter(md_path)
        if meta is None or meta.topic_cluster != cluster_slug:
            continue
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        match = SECTION_PATTERN.search(text)
        if not match:
            continue
        existing_slugs = re.findall(r"\[\[([^\]]+)\]\]", match.group(2))
        if removed_slug not in existing_slugs:
            continue
        new_slugs = [slug for slug in existing_slugs if slug != removed_slug]
        if not new_slugs:
            # Last entry removed — delete the entire Related section so we
            # don't leave an empty "## Related Papers in This Cluster" header.
            text = md_path.read_text(encoding="utf-8", errors="ignore")
            new_text = SECTION_PATTERN.sub(lambda m: m.group(3), text, count=1)
            if new_text != text:
                md_path.write_text(new_text, encoding="utf-8")
                modified += 1
        elif add_wikilinks_to_note(md_path, new_slugs, existing_stems):
            modified += 1
    return modified
