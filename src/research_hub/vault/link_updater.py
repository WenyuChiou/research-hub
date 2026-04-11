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
    """Find same-cluster notes ordered by descending tag overlap."""
    related: list[tuple[int, NoteMeta]] = []
    new_tag_set = set(new_note.tags)
    for other in all_notes:
        if other.path == new_note.path:
            continue
        if new_note.topic_cluster:
            if other.topic_cluster != new_note.topic_cluster:
                continue
        overlap = len(new_tag_set & set(other.tags))
        if overlap >= min_tag_overlap:
            related.append((overlap, other))
    related.sort(key=lambda item: (-item[0], item[1].slug))
    return [item[1] for item in related]


def add_wikilinks_to_note(note_path: Path, related_slugs: list[str]) -> bool:
    """Create or replace the related-papers section idempotently."""
    if not note_path.exists():
        return False
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

    related = find_related_in_cluster(new_meta, all_notes)
    forward = 1 if add_wikilinks_to_note(new_note_path, [note.slug for note in related]) else 0
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
            if add_wikilinks_to_note(other.path, new_slugs):
                backward += 1

    return {"forward": forward, "backward": backward, "scanned": len(all_notes)}
