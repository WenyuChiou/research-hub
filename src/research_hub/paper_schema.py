"""Frontmatter schema validator for paper notes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from research_hub.topic import _parse_frontmatter, _strip_frontmatter

REQUIRED_FRONTMATTER_FIELDS = (
    "title",
    "doi",
    "authors",
    "year",
    "topic_cluster",
    "status",
    "ingested_at",
)

REQUIRED_BODY_SECTIONS = ("Summary", "Key Findings", "Methodology", "Relevance")


@dataclass
class NoteValidationResult:
    path: Path
    missing_frontmatter: list[str]
    empty_sections: list[str]
    todo_placeholders: list[str]

    @property
    def ok(self) -> bool:
        return not (self.missing_frontmatter or self.empty_sections or self.todo_placeholders)

    @property
    def severity(self) -> str:
        if self.ok:
            return "ok"
        if self.missing_frontmatter:
            return "fail"
        return "warn"


def validate_paper_note(path: Path) -> NoteValidationResult:
    """Validate a single paper note."""
    text = path.read_text(encoding="utf-8")
    meta = _parse_frontmatter(text)
    body = _strip_frontmatter(text)

    missing_frontmatter = [field for field in REQUIRED_FRONTMATTER_FIELDS if _is_missing(meta.get(field))]
    empty_sections: list[str] = []
    todo_placeholders: list[str] = []

    for section in REQUIRED_BODY_SECTIONS:
        content = _extract_section(body, section)
        if not content:
            empty_sections.append(section)
            continue
        if "[TODO:" in content:
            todo_placeholders.append(section)

    return NoteValidationResult(
        path=path,
        missing_frontmatter=missing_frontmatter,
        empty_sections=empty_sections,
        todo_placeholders=todo_placeholders,
    )


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return not any(str(item).strip() for item in value)
    return not str(value).strip()


def _extract_section(body: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()
